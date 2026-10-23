"""RJ readmission client lane (design V3): the harness runner.

Suites:
  apply   P1 twin run (T1.1, T1.2): the REAL ApplyManifestPick at the lane base
          and from the tree under test, extracted into one generated file and
          compiled against apply-trace/Stubs.cs; traces equal element by element.
  rules   the REAL plugin rule files (FfaReadmitRules.cs, FfaReportRules.cs,
          FfaLateRules.cs, FfaNumberingRules.cs) under a plain compiler: one
          named case per falsifiable sentence (rules/Cases*.cs).

Mutants are planted into COPIES of the plugin files under the work folder (the
tracked files are never written). Each mutant must turn its target case red
and leave its control case green (#391). Exit 0 only when every baseline case
passes, every mutant is caught, every control holds and the source files are
unchanged by the run.

    python tools/tests/rj-readmit-client/run_rj.py --work <dir>
        [--tree <dir>] [--wt <dir>] [--suite apply|rules|all] [--only <id>,...]
        [--stub-kinds]

--stub-kinds checks declaration kinds and their in-memory mutants only; it
does not create the required --work folder or invoke a compiler.

--tree DIR: the source tree to test (plugin/ and this folder), default the
repository holding this script. --wt DIR: the git worktree whose commit and
state head the log, default the tree. Every source file read is printed with
its sha256, so a log names exactly what ran.
"""
import argparse
import glob
import hashlib
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TREE = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BASE = "bf81f4fe"  # the lane base: the pre-split reducer is read from here
REL = os.path.join("tools", "tests", "rj-readmit-client")

APPLY_CASES = ["rolling", "local", "remote", "unknown", "quarantined", "nobody",
               "rolling_local", "throw_replay", "throw_apply", "throw_audit", "throw_rebuild",
               "bodiless", "bodiless_plain", "H1.delayed", "H1.empty", "H1.missing",
               "H1.apply_throw", "H1.apply_false", "H1.reset_throw", "H1.room_change",
               "H1.body_replaced", "H1.body_missing", "H1.invalidated", "H1.deck_changed", "H1.identity",
               "H1.admitted_grant", "H1.room_incarnation", "H1.replaced_work", "H1.entered", "H1.ack",
               "H1.master_ack", "H1.normal_late", "H1.prepare_throw", "H1.legacy_kept_exception", "H1.ack_identity"]

# file -> MSBuild property naming its copy, per suite
SUITE_FILES = {
    "apply": {"FfaMode.cs": None, "FfaLateEntry.cs": None, "FfaReadmitRules.cs": "RulesSource"},
    "rules": {"FfaReadmitRules.cs": "RulesSource", "FfaReportRules.cs": "ReportSource",
              "FfaLateRules.cs": "LateSource", "FfaReadmitEntryRules.cs": "EntrySource",
              "RosterCensusRules.cs": "CensusSource", "FfaReadmit.cs": None,
              "FfaAssembly.cs": None, "ApiClient.cs": None, "FfaLateEntry.cs": None},
}

RELEASE_ROUTE_TARGET = "C4.F2D.release_route_census"
F2E_ROUTE_TARGET = "C4.F2E.release_route_census"
RELEASE_ROUTES = (
    ("escape", "ApiClient.cs", "private static void TearDownAllQueueBeliefs(",
     "FfaReadmit.Abandon(null, all: true);", ("IsFfaQueuePolling = false;", "ActiveFfaLobbyId = null;")),
    ("leave", "ApiClient.cs", "public static void FfaLeaveQueue(",
     "FfaReadmit.Abandon(expectedLobby);", ("FfaClientClears();",)),
    ("release", "FfaAssembly.cs", "internal static void Release(",
     "FfaReadmit.Abandon(lobby);", ("ApiClient.FfaClientClears();",)),
    ("depart", "FfaAssembly.cs", "internal static void OnRoomLeft(",
     "FfaReadmit.Abandon(room, byRoom: true);", ("StartHoldActive = false;", "FfaLateEntry.OnRoomLeft(room);")),
    ("refusal", "FfaReadmit.cs", "private static void Refusal(",
     "Abandon(State.Lobby);", ("PhotonNetwork.LeaveRoom();", "ApiClient.FfaLeaveQueue(")),
)

# Legacy site mutants retain their target name and gain the same per-route
# judgment as the new mutants: only their named row may turn RED.
MUTANT_ROUTES = {
    "M-F2D-site-release": "release", "M-F2D-site-leave": "leave", "M-F2D-site-depart": "depart",
    "M-F2E-site-escape": "escape", "M-F2E-site-leave": "leave", "M-F2E-site-release": "release",
    "M-F2E-site-depart": "depart", "M-F2E-site-refusal": "refusal", "M-F2E-site-entryfact": "entry-fact",
}

# (id, piece, suite, file, [(old, new), ...], target case, control case)
# Each old string occurs exactly once in the file it names.
MUTANTS = [
    # ---- C1 (P1)
    ("M1.1", "C1", "apply", "FfaMode.cs",
     [("            if (!bodiless) ApplyCardTo(player, prefab);\n",
       "            try { GameStateWatcher.RecordFfaLocalPick(cardName, RoundsTotalAll()); } catch { }\n"
       "            if (!bodiless) ApplyCardTo(player, prefab);\n")],
     "throw_apply", "unknown"),
    ("M1.2", "C1", "apply", "FfaMode.cs",
     [("                if (!bodiless)\n                {\n                    deckViewRebuilds.Add(pid);\n",
       "                deck.Clear();\n                deck.AddRange(survivors);\n"
       "                if (!bodiless)\n                {\n                    deckViewRebuilds.Add(pid);\n")],
     "rolling", "remote"),
    ("M1.3", "C1", "apply", "FfaMode.cs",
     [("                Plugin.Log.LogWarning($\"[FFA] apply skipped — player {pid} gone (card {cardName})\");\n"
       "                yield break;\n",
       "                bodiless = true;\n")],
     "nobody", "rolling"),
    ("M1.4", "C1", "apply", "FfaReadmitRules.cs",
     [("plan.Survivors = deck.Skip(count - (cardCap - 1)).ToList();",
       "plan.Survivors = deck.Take(cardCap - 1).ToList();")],
     "rolling", "remote"),
    # ---- merged H1: production replay and admission outcome controls
    ("M-H1c-ffa", "H1", "apply", "FfaMode.cs",
     [("                    if (!applied) yield break;\n", "                    if (!applied) { replay.State = ReadmitReplayState.Completed; yield break; }\n")],
     "H1.apply_false", "H1.empty"),
    ("M-H1d", "H1", "apply", "FfaMode.cs",
     [("                bool moved;\n", "                replay.State = ReadmitReplayState.Completed;\n                bool moved;\n")],
     "H1.delayed", "H1.identity"),
    ("M-H1e-ffa", "H1", "apply", "FfaLateEntry.cs",
     [("            if (!ReadmitEnteredReady(FfaReadmit.ReadmittedInto(AdmittedLateLobby), Kept(OwnActor()),\n"
       "                                    ReadmitActorPrepared(OwnActor(), PointEpoch))) return;\n", "")],
     "H1.entered", "H1.identity"),
    ("M-H1f-ffa", "H1", "apply", "FfaMode.cs",
     [("                && replay.Lobby == FfaAssembly.RoomLobbyId && replay.Room == FfaAssembly.CurrentRoomName()\n", "")],
     "H1.room_change", "H1.empty"),
    ("M-H1-ack", "H1", "apply", "FfaLateEntry.cs",
     [("            if (!ReadmitBoundaryReady(PrepareReadmitEpoch(p.N))) return;\n", "")],
     "H1.ack", "H1.identity"),
    ("M-H1-ackref", "H1", "apply", "FfaLateEntry.cs",
     [("                if (!string.Equals(held.Lobby8, p.Lobby8, StringComparison.Ordinal)\n"
       "                    || held.N != p.N || !string.Equals(held.Chain, p.Chain, StringComparison.Ordinal)\n"
       "                    || held.G != p.G || held.K != p.K || held.From != p.From || e.Sender != p.From) return false;\n",
       "                if (!object.ReferenceEquals(_replayProposal, p) || e.Sender != p.From) return false;\n")],
     "H1.ack_identity", "H1.identity"),
    ("M-H1-master", "H1", "apply", "FfaLateEntry.cs",
     [("                        && ReadmitBoundaryReady(prepared);\n", "                        ;\n")],
     "H1.master_ack", "H1.identity"),
    ("M-H1-missing", "H1", "apply", "FfaMode.cs",
     [("                            && ResolveCard(card.gameObject.name) != null && apply(card);\n", "                            && apply(card);\n")],
     "H1.missing", "H1.empty"),
    ("M-H1-quarantine", "H1", "apply", "FfaLateEntry.cs",
     [("                try { if (!ReadmitActorPrepared(actor, PointEpoch)) return false; }\n"
       "                catch { return false; }\n",
       "                try { if (!ReadmitActorPrepared(actor, PointEpoch)) return false; }\n"
       "                catch { return true; }\n")],
     "H1.prepare_throw", "H1.identity"),
    ("M-H1-prep-failure", "H1", "apply", "FfaLateEntry.cs",
     [("            try { return PrepareReadmitEpochCore(epoch); }\n            catch { return false; }\n",
       "            return PrepareReadmitEpochCore(epoch);\n")],
     "H1.prepare_throw", "H1.identity"),
    # ---- C2 (P2)
    ("M2.1", "C2", "rules", "FfaReadmitRules.cs",
     [("                string first = held.FirstOf(pid);\n",
       "                var l1 = held.ListOf(pid);\n                string first = l1 != null && l1.Count > 1 ? l1[1] : null;\n")],
     "C2.T2.1.twin_rule_s_ledger", "C2.T2.3.opening_draw_raw_entry"),
    ("M2.2", "C2", "rules", "FfaReadmitRules.cs",
     [("(seq.UsedNoRepeatFold.Contains(cn) || ledger.Contains(cn))",
       "(seq.UsedNoRepeatFold.Contains(cn) || new HashSet<string>().Contains(cn))")],
     "C2.T2.2.ledger_substitute_never_reoffered", "C2.T2.3.opening_draw_raw_entry"),
    ("M2.3", "C2", "rules", "FfaReadmitRules.cs",
     [("                            if (pool.NoRepeat.Contains(sub.Name)) ledger.Add(sub.Name);\n", ""),
      ("        internal static void NoteApplied(SpendState spend, int pid, string card)\n        {\n",
       "        internal static void NoteApplied(SpendState spend, int pid, string card)\n        {\n"
       "            if (!spend.Ledger.Contains(card)) spend.Ledger.Add(card);\n")],
     "C2.T2.2.ledger_substitute_never_reoffered", "C2.T2.3.opening_draw_raw_entry"),
    ("M2.4", "C2", "rules", "FfaReadmitRules.cs",
     [("bool openingDraw = k <= seq.OpeningDraws;", "bool openingDraw = false;")],
     "C2.T2.3.opening_draw_raw_entry", "C2.T2.2.ledger_substitute_never_reoffered"),
    ("M2.5", "C2", "rules", "FfaReadmitRules.cs",
     [("                if (got.ContainsKey(pid)) continue;\n                string first",
       "                if (view.HasKeptBody(pid)) continue;\n                string first")],
     "C2.T2.4.walk_seat_leaves", "C2.T2.1.twin_rule_s_ledger"),
    ("M2.6", "C2", "rules", "FfaReadmitRules.cs",
     [("                if (got.ContainsKey(pid)) continue;\n                string first",
       "                if (got.ContainsKey(pid) || view.HasKeptBody(pid)) continue;\n                string first")],
     "C2.T2.5.present_missed_gets_entry0", "C2.T2.4.walk_seat_leaves"),
    ("M2.7", "C2", "rules", "FfaReadmitRules.cs",
     [("return v != null && v.Pin != null && v.Pin.Flag && !string.IsNullOrEmpty(v.Room) && v.Room == v.Pin.Room;",
       "return v != null && v.PresentAllAdvertise();")],
     "C2.T2.6.gate_pinned_at_lock", "C2.T2.1.twin_rule_s_ledger"),
    ("M2.8", "C2", "rules", "FfaReadmitRules.cs",
     [("        internal static FfaOfferRecord AfterAudit(FfaOfferRecord published, FfaOfferRecord recomputed)\n"
       "        {\n            return published;\n",
       "        internal static FfaOfferRecord AfterAudit(FfaOfferRecord published, FfaOfferRecord recomputed)\n"
       "        {\n            return recomputed ?? published;\n")],
     "C2.T2.7.master_mutation_audited", "C2.T2.1.twin_rule_s_ledger"),
    # ---- C3 (P3 client half)
    ("M3.5", "C3", "rules", "FfaReportRules.cs",
     [("            if (readmitLobby) return localSid;\n", "")],
     "C3.T3.2.lag_publication_lost_both_file", "C3.T3.6.flag_false_matrix_equals_base"),
    # ---- C4 (P4 client half)
    ("M4.12", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("return new FfaLateRules.EpochEntry(slot, actor, k, game < 0 ? -1 : game, 2,",
       "return new FfaLateRules.EpochEntry(slot, actor, 'l', -1, 2,")],
     "C4.T4.5.epoch_v2_parsed_with_kind_and_game", "C4.T4.5.every_refusal_reason_mapped"),
    ("M4.15", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("return TokenMatches(senderRdt, r) ? LateReq.Accept : LateReq.RefuseToken;",
       "return LateReq.Accept;")],
     "C4.T4.6.token_checked_at_master", "C4.T4.6.identity_duplicate_refused"),
    ("M4.16", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("            return r.Actor != actor;\n", "            return null;\n")],
     "C4.T4.6.identity_duplicate_refused", "C4.T4.6.token_checked_at_master"),
    ("M4.17", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("            if (readmitLobby && rosterCount > 0) return rosterCount;\n", "")],
     "C4.T4.7.held_highest_slot_carried", "C4.T4.11.three_way_game_agreement"),
    ("M4.18", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("            if (readmitLobby && rosterCount > 0)\n            {\n                for (int s = 0;",
       "            if (false && readmitLobby && rosterCount > 0)\n            {\n                for (int s = 0;")],
     "C4.T4.8.each_mutation_fails_the_gate", "C4.T4.11.three_way_game_agreement"),
    ("M4.19", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("if (!v.VictimPresent || v.VictimDead", "if (v.VictimPresent || v.VictimDead")],
     "C4.T4.9.departure_credits_exactly_staying", "C4.T4.11.three_way_game_agreement"),
    ("M4.20", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("            return at;\n", "            return newId;\n")],
     "C4.T4.10.same_position_any_purge_timing", "C4.T4.11.three_way_game_agreement"),
    ("M4.21", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("return tailGame > 0 && tailGame == serverGame && tailGame == cycGame;", "return tailGame > 0;")],
     "C4.T4.11.three_way_game_agreement", "C4.T4.10.same_position_any_purge_timing"),
    ("M4.22", "C4", "rules", "FfaReadmitEntryRules.cs",
     [("            return readmitLobby;\n", "            return false;\n")],
     "C4.T4.12.kind_r_grant_releases_latch", "C4.T4.11.three_way_game_agreement"),
    # ---- merged H2: pair identity and actual discovery/poll adapters
    ('M-H2a', 'H2', 'rules', 'FfaReadmitEntryRules.cs',
     [('c.State == RdmState.Entered && c.Lobby == lobby && n <= c.N',
       'c.State == RdmState.Entered && n <= c.N')],
     'C4.H2.cross_lobby_first_hold', 'C4.H2.same_lobby_terminal'),
    ('M-H2b', 'H2', 'rules', 'FfaReadmitEntryRules.cs',
     [('c.State == RdmState.Entered && c.Lobby == lobby && n <= c.N',
       'c.State == RdmState.Entered && c.Lobby == lobby && false')],
     'C4.H2.same_lobby_terminal', 'C4.H2.cross_lobby_first_hold'),
    ('M-H2c', 'H2', 'rules', 'FfaReadmitEntryRules.cs',
     [('            if (c.State == RdmState.Claiming || c.State == RdmState.Claimed\n                || c.State == RdmState.Binding || c.State == RdmState.Admitted)\n                return sameOffer ? RdmOffer.Held : RdmOffer.Rejected;\n',
       '')],
     'C4.H2.active_claim_preserved', 'C4.H2.cross_lobby_first_hold'),
    ('M-H2d', 'H2', 'rules', 'FfaReadmit.cs',
     [('offered = SuppressesDiscoveryProbe(Offer(lobby, slot, n, holdS, "discovery"));',
       'Offer(lobby, slot, n, holdS, "discovery"); offered = true;')],
     'C4.H2.discovery_fallback', 'C4.H2.poll_result'),
    # ---- merged fix 2d: terminal abandonment and lifecycle callback fences
    ('M-F2D-abandon', 'H1', 'rules', 'FfaReadmit.cs',
     [('        internal static bool Abandon(string identity, bool byRoom = false, bool all = false)\n'
       '        {\n'
       '            if (!FfaReadmitEntryRules.MatchesRelease(State, identity, byRoom, all)) return false;\n'
       '            if (FfaReadmitEntryRules.KeepEntered(State, FfaLateEntry.ReadmitEntryCompleted(State.Lobby, State.Game))) return false;\n'
       '            InvalidateMatchingWork();\n'
       '            return FfaReadmitEntryRules.Abandon(State, identity, byRoom, all);\n'
       '        }\n',
       '        internal static bool Abandon(string identity, bool byRoom = false, bool all = false)\n'
       '        {\n'
       '            return false;\n'
       '        }\n')],
     'C4.F2D.admitted_release_cross_lobby', 'C4.H2.active_claim_preserved'),
    ('M-F2D-discfence', 'H1', 'rules', 'FfaReadmit.cs',
     [('                if (generation != _lifecycleGeneration) return;\n'
       '                _discoveryInFlight = false;\n',
       '                _discoveryInFlight = false;\n')],
     'C4.F2D.old_discovery_callback', 'C4.H2.active_claim_preserved'),
    ('M-F2D-postfence', 'H1', 'rules', 'FfaReadmit.cs',
     [('                if (generation != _lifecycleGeneration) return;\n'
       '                _postInFlight = false;\n',
       '                _postInFlight = false;\n')],
     'C4.F2D.old_post_callback', 'C4.H2.active_claim_preserved'),
    ('M-F2D-site-release', 'H1', 'rules', 'FfaAssembly.cs',
     [('            FfaReadmit.Abandon(lobby);\n', '')],
     RELEASE_ROUTE_TARGET, 'C4.H2.active_claim_preserved'),
    ('M-F2D-site-leave', 'H1', 'rules', 'ApiClient.cs',
     [('            FfaReadmit.Abandon(expectedLobby);\n', '')],
     RELEASE_ROUTE_TARGET, 'C4.H2.active_claim_preserved'),
    ('M-F2D-site-depart', 'H1', 'rules', 'FfaAssembly.cs',
     [('            FfaReadmit.Abandon(room, byRoom: true);\n', '')],
     RELEASE_ROUTE_TARGET, 'C4.H2.active_claim_preserved'),
    # ---- merged fix 2e: state-independent invalidation and playing entry
    ('M-F2E-site-escape', 'H1', 'rules', 'ApiClient.cs',
     [('                FfaReadmit.Abandon(null, all: true);\n', '')],
     F2E_ROUTE_TARGET + '.escape', 'C4.F2E.playing_readmission_kept'),
    ('M-F2E-site-leave', 'H1', 'rules', 'ApiClient.cs',
     [('            FfaReadmit.Abandon(expectedLobby);\n', '')],
     F2E_ROUTE_TARGET + '.leave', 'C4.F2E.playing_readmission_kept'),
    ('M-F2E-site-release', 'H1', 'rules', 'FfaAssembly.cs',
     [('            FfaReadmit.Abandon(lobby);\n', '')],
     F2E_ROUTE_TARGET + '.release', 'C4.F2E.playing_readmission_kept'),
    ('M-F2E-site-depart', 'H1', 'rules', 'FfaAssembly.cs',
     [('            FfaReadmit.Abandon(room, byRoom: true);\n', '')],
     F2E_ROUTE_TARGET + '.depart', 'C4.F2E.playing_readmission_kept'),
    ('M-F2E-site-refusal', 'H1', 'rules', 'FfaReadmit.cs',
     [('            Abandon(State.Lobby);\n', '')],
     F2E_ROUTE_TARGET + '.refusal', 'C4.H2.active_claim_preserved'),
    ('M-F2E-entrykeep', 'H1', 'rules', 'FfaReadmit.cs',
     [('            if (FfaReadmitEntryRules.KeepEntered(State, FfaLateEntry.ReadmitEntryCompleted(State.Lobby, State.Game))) return false;\n', '')],
     'C4.F2E.playing_readmission_kept', 'C4.F2E.escape_roomless_claim'),
    ('M-F2E-split', 'H1', 'rules', 'FfaReadmit.cs',
     [('            InvalidateMatchingWork();\n'
       '            return FfaReadmitEntryRules.Abandon(State, identity, byRoom, all);\n',
       '            if (!FfaReadmitEntryRules.Abandon(State, identity, byRoom, all)) return false;\n'
       '            InvalidateMatchingWork();\n'
       '            return true;\n')],
     'C4.F2E.lapse_refused_bind', 'C4.H2.active_claim_preserved'),
    ('M-F2E-site-entryfact', 'H1', 'rules', 'FfaLateEntry.cs',
     [('            _readmitEnteredLobby = AdmittedLateLobby;\n', '')],
     F2E_ROUTE_TARGET + '.entry-fact', 'C4.F2E.playing_readmission_kept'),
    # ---- C5 (P5 client rungs of the positive ladder)
    ("M5.c1", "C5", "rules", "FfaReadmitEntryRules.cs",
     [("            if (after == before) return null;\n", "")],
     "C5.T5.ladder_repeats_add_no_line", "C5.T5.ladder_each_rung_once_in_order"),
    ("M5.c2", "C5", "rules", "FfaReadmitEntryRules.cs",
     [("if (selfKept) return after == RdmState.Admitted || after == RdmState.Entered ? \"entered\" : null;",
       "if (selfKept) return \"entered\";")],
     "C5.T4.13.flag_false_no_rung", "C5.T5.ladder_each_rung_once_in_order"),
    ("M5.c3", "C5", "rules", "FfaReadmitEntryRules.cs",
     [("                case RdmState.Admitted: return \"bound\";\n", "                case RdmState.Binding: return \"bound\";\n")],
     "C5.T5.ladder_each_rung_once_in_order", "C5.T4.13.flag_false_no_rung"),
    # ---- C4z (P4.6 the capability flip)
    ("M4z.1", "C4z", "rules", "FfaReadmitEntryRules.cs",
     [('            if (asm && adm) return asmToken + "," + admToken + "," + RdmCapsToken;\n',
       '            if (asm && adm) return asmToken + "," + admToken;\n')],
     "C4z.T4.6.adm_sends_all_three", "C4z.T4.6.asm_alone_no_rdm"),
    ("M4z.2", "C4z", "rules", "FfaReadmitEntryRules.cs",
     [('            if (asm) return asmToken;\n',
       '            if (asm) return asmToken + "," + RdmCapsToken;\n')],
     "C4z.T4.6.asm_alone_no_rdm", "C4z.T4.6.adm_sends_all_three"),
    ("M4z.3", "C4z", "rules", "FfaReadmitEntryRules.cs",
     [('        internal const string RdmCapsToken = "ffa_rdm1";\n',
       '        internal const string RdmCapsToken = "ffa_rdm0";\n')],
     "C4z.T4.6.adm_sends_all_three", "C4z.T4.6.asm_alone_no_rdm"),
]


def _blank_csharp(text):
    """Blank comments and literals while preserving offsets and newlines."""
    chars, size = list(text), len(text)

    def comment(at):
        if text.startswith('//', at):
            end = text.find('\n', at + 2)
            return size if end < 0 else end
        if text.startswith('/*', at):
            end = text.find('*/', at + 2)
            if end < 0:
                raise ValueError('unclosed C# comment')
            return end + 2
        return None

    def literal(at):
        start = at
        while at < size and text[at] in '$@':
            at += 1
        if at >= size or text[at] not in '\"\'':
            return None
        quote, prefix = text[at], text[start:at]
        verbatim, interpolated = '@' in prefix, '$' in prefix
        if quote == '\"' and not verbatim and text.startswith('\"\"\"', at):
            raise ValueError('raw C# literal requires lexer support')
        at += 1
        while at < size:
            if text[at] == quote:
                if verbatim and at + 1 < size and text[at + 1] == quote:
                    at += 2
                    continue
                return at + 1
            if not verbatim and text[at] == '\\':
                at += 2
                continue
            if interpolated and text[at] == '{':
                if text.startswith('{{', at):
                    at += 2
                    continue
                depth = 1
                at += 1
                while at < size and depth:
                    end = comment(at)
                    if end is None:
                        end = literal(at)
                    if end is not None:
                        at = end
                        continue
                    depth += (text[at] == '{') - (text[at] == '}')
                    at += 1
                continue
            at += 1
        raise ValueError('unclosed C# literal')

    at = 0
    while at < size:
        end = comment(at)
        if end is None:
            end = literal(at)
        if end is None:
            at += 1
            continue
        for pos in range(at, end):
            if chars[pos] not in '\r\n':
                chars[pos] = ' '
        at = end
    return ''.join(chars)


def _type_declarations(path, text):
    code = _blank_csharp(text)
    pattern = re.compile(
        r'\bnamespace\s+(?P<namespace>[@\w]+(?:\s*\.\s*[@\w]+)*)\s*(?P<nsend>[{;])'
        r'|(?P<mods>(?:(?:public|private|protected|internal|static|sealed|abstract|partial|new|unsafe|readonly|ref)\s+)*)'
        r'\b(?P<kind>class|struct|enum|interface)\s+(?P<name>@?[A-Za-z_]\w*)'
        r'|(?P<brace>[{}])')
    scopes, rows, pending, file_namespace = [], [], None, ''
    for match in pattern.finditer(code):
        if match.group('namespace'):
            name = re.sub(r'\s+', '', match.group('namespace')).replace('@', '')
            if match.group('nsend') == ';':
                if file_namespace or scopes:
                    raise ValueError('unsupported nested file namespace: ' + path)
                file_namespace = name
            else:
                scopes.append(('namespace', name))
        elif match.group('kind'):
            if pending is not None:
                raise ValueError('type declaration without a body: ' + path)
            nesting = [name for kind, name in scopes if kind == 'type']
            namespace = '.'.join(([file_namespace] if file_namespace else [])
                                 + [name for kind, name in scopes if kind == 'namespace'])
            local = '.'.join(nesting + [match.group('name').lstrip('@')])
            mods, kind = match.group('mods').split(), match.group('kind')
            static = 'static' in mods
            # Static classes compare on static; structs and enums are intrinsically sealed.
            sealed = kind in ('struct', 'enum') or ('sealed' in mods and not static)
            rows.append(dict(path=path, line=code.count('\n', 0, match.start()) + 1,
                             name=(namespace + '.' if namespace else '') + local,
                             local=local, kind=kind, static=static, sealed=sealed, partial='partial' in mods))
            pending = ('type', match.group('name').lstrip('@'))
        elif match.group('brace') == '{':
            scopes.append(pending or ('block', ''))
            pending = None
        else:
            if not scopes:
                raise ValueError('unmatched C# brace: ' + path)
            scopes.pop()
    if scopes or pending:
        raise ValueError('unclosed C# declaration: ' + path)
    return rows


def _kind(row):
    return (row['kind'], row['static'], row['sealed'])


def _kind_text(kind):
    return '%s static=%s sealed=%s' % kind


def _production_sources(tree):
    paths = sorted(glob.glob(os.path.join(tree, 'plugin', '**', '*.cs'), recursive=True))
    return {os.path.relpath(path, tree).replace(os.sep, '/'): open(path, encoding='utf-8-sig').read()
            for path in paths if not {'obj', 'bin'}.intersection(os.path.relpath(path, tree).split(os.sep))}


def _project_sources(tree, project):
    """Read default Compile property expansions without invoking MSBuild."""
    root = ET.parse(os.path.join(tree, project)).getroot()
    folder = os.path.dirname(os.path.join(tree, project)) + os.sep
    props = {'MSBuildThisFileDirectory': folder}
    for group in root.findall('PropertyGroup'):
        for node in group:
            if node.text is not None and node.tag not in props:
                props[node.tag] = node.text

    def expand(value):
        for _ in range(len(props) + 1):
            updated = re.sub(r'\$\(([^)]+)\)', lambda m: props.get(m.group(1), m.group(0)), value)
            if updated == value:
                return value
            value = updated
        raise ValueError('cyclic project properties: ' + project)

    linked, sources = set(), set()
    for node in root.findall('./ItemGroup/Compile'):
        value = expand(node.attrib.get('Include', '')).replace('\\', os.sep)
        if '$(' in value:
            if value not in ('$(ProductionSource)', '$(GenDir)' + os.sep + 'Reducers.cs'):
                raise ValueError('unresolved Compile source: ' + project)
            continue  # Generated declarations are censused from actual in-memory source below.
        path = os.path.normpath(value if os.path.isabs(value) else os.path.join(folder, value))
        matches = sorted(glob.glob(path))
        if not matches:
            raise ValueError('missing Compile source in ' + project)
        for match in matches:
            relative = os.path.relpath(match, tree).replace(os.sep, '/')
            if relative.startswith('../') or not relative.endswith('.cs'):
                raise ValueError('Compile source outside the C# tree: ' + project)
            sources.add(relative)
            if relative.startswith('plugin/'):
                linked.add(relative)
    return sources, linked


def _stub_kind_rows(stubs, production, mapped, external, harness_only, standins, linked):
    index = {}
    for path, text in sorted(production.items()):
        for row in _type_declarations(path, text):
            index.setdefault(row['name'], []).append(row)

    def resolve(row):
        candidates = [row['name'], 'CompetitiveRounds.' + row['local']]
        parts = row['local'].split('.')
        if len(parts) > 1 and parts[0] in standins:
            candidates += ['CompetitiveRounds.' + standins[parts[0]] + '.' + '.'.join(parts[1:]),
                           'CompetitiveRounds.' + '.'.join(parts[1:])]
        return [name for name in dict.fromkeys(candidates) if name in index]

    result = []
    for path, text in sorted(stubs.items()):
        for row in _type_declarations(path, text):
            matches, name = resolve(row), row['name']
            declared = int(name in mapped) + int(name in external) + int(name in harness_only)
            status, target, expected = 'EQUAL', '-', None
            if declared > 1:
                resolution, status = 'AMBIGUOUS', 'DIFFERS'
            elif path in linked:
                resolution, target = 'PRODUCTION', name
            elif name in mapped:
                resolution, target = 'MAPPED', mapped[name]
                if matches and matches != [target]:
                    status = 'DIFFERS'
            elif name in external or name in harness_only:
                resolution = 'EXTERNAL' if name in external else 'HARNESS-ONLY'
                expected = external.get(name)
                if matches:
                    status, target = 'DIFFERS', 'SHADOW ' + ','.join(matches)
            elif len(matches) == 1:
                resolution, target = 'PRODUCTION', matches[0]
            else:
                resolution, status = ('AMBIGUOUS' if matches else 'UNRESOLVED'), 'DIFFERS'
                target = ','.join(matches) or '-'
            refs = index.get(target, [])
            if resolution in ('PRODUCTION', 'MAPPED'):
                signatures = {_kind(ref) for ref in refs}
                if not refs or len(signatures) != 1 or (len(refs) > 1 and not all(r['partial'] for r in refs)):
                    status = 'DIFFERS'
                else:
                    expected = _kind(refs[0])
            if expected is not None and _kind(row) != expected:
                status = 'DIFFERS'
            result.append(dict(row, resolution=resolution, target=target, expected=expected,
                               production_sites=','.join(r['path'] + ':' + str(r['line']) for r in refs) or '-',
                               status=status))
    return result


def _print_stub_kinds(rows):
    print('stub file:line | qualified name | stub kind | resolution | production file:line | production kind | verdict')
    for row in rows:
        print('%s:%s | %s | %s | %s:%s | %s | %s | %s' % (
            row['path'], row['line'], row['name'], _kind_text(_kind(row)), row['resolution'], row['target'],
            row['production_sites'], _kind_text(row['expected']) if row['expected'] is not None else '-', row['status']))
    counts = {key: sum(r['resolution'] == key for r in rows)
              for key in ('PRODUCTION', 'MAPPED', 'EXTERNAL', 'HARNESS-ONLY', 'UNRESOLVED', 'AMBIGUOUS')}
    print('stub kinds: declarations=%d %s differences=%d' % (
        len(rows), ' '.join('%s=%d' % item for item in counts.items()), sum(r['status'] != 'EQUAL' for r in rows)))


def _stub_kind_control(tree, sources, linked, mapped, external, harness_only, standins, mutants, generated):
    """Run before work-folder creation or build; mutate in-memory copies only."""
    try:
        production = _production_sources(tree)
        stubs = {path: open(os.path.join(tree, path), encoding='utf-8-sig').read() for path in sources}
        stubs.update({path: production[path] for path in linked})
        stubs.update(generated)
        rows = _stub_kind_rows(stubs, production, mapped, external, harness_only, standins, linked)
        _print_stub_kinds(rows)
        baseline = bool(rows) and all(r['status'] == 'EQUAL' for r in rows)
        print('stub-kind control', 'GREEN' if baseline else 'RED')
        ok = baseline
        for mid, side, path, old, new, expected_name in mutants:
            texts = dict(stubs if side == 'stub' else production)
            raw = texts[path]
            if raw.count(old) != 1:
                print('BAD mutant %s: anchor occurs %d times' % (mid, raw.count(old)))
                ok = False
                continue
            texts[path] = raw.replace(old, new, 1)
            changed = _stub_kind_rows(texts if side == 'stub' else stubs,
                                      texts if side == 'production' else production,
                                      mapped, external, harness_only, standins, linked)
            differences = [r for r in changed if r['status'] != 'EQUAL']
            hit = baseline and bool(differences) and any(r['name'] == expected_name for r in differences)
            ok = ok and hit
            print('%s mutant %s (stub kinds): target %s=%s; control=%s' % (
                'CAUGHT' if hit else 'MISSED', mid, expected_name, 'RED' if differences else 'GREEN',
                'GREEN' if baseline else 'RED'))
        return ok
    except (OSError, ValueError, KeyError, ET.ParseError) as exc:
        print('stub-kind control RED:', str(exc))
        return False


def stub_kinds(tree, wt):
    prefix = 'CompetitiveRounds.'
    external = {prefix + name: ('class', False, True) for name in (
        'PhotonView', 'ObjectsToSpawn', 'Gun', 'Holdable', 'Holding', 'WeaponHandler',
        'CharacterData', 'Player', 'CardInfo', 'CardChoice', 'RaiseEventOptions', 'EventData')}
    external.update({prefix + 'Color': ('struct', False, True),
                     prefix + 'GameObject': ('class', False, False),
                     prefix + 'CardInfo.Rarity': ('enum', False, True),
                     prefix + 'PhotonNetwork': ('class', True, False),
                     prefix + 'ReadmitOfferAdapterBase.Color': ('struct', False, True),
                     prefix + 'ReadmitOfferAdapterBase.PhotonNetwork': ('class', True, False)})
    harness_only = {prefix + name for name in (
        'OwnerStub', 'LogStub', 'ReadmitAdmissionBase', 'ReducerBase', 'Trace', 'TraceProgram',
        'OldReducer', 'NewReducer', 'FfaReplay', 'FfaReplayAdmission', 'ReadmitOfferAdapter',
        'TraceProgram.Fixture', 'CasesC2', 'CasesC3', 'CasesC3.Seat', 'CasesC4', 'CasesC4.Table',
        'CasesC4z', 'CasesC5', 'CasesC5.Driver', 'CaseFailed', 'Check', 'RulesProgram',
        'ReadmitOfferAdapterBase', 'ReadmitOfferAdapterBase.Plugin.Logger',
        'ReadmitOfferAdapterBase.RoomStub', 'ReadmitOfferAdapterBase.PlayerStub')}
    mapped = {prefix + 'ReadmitAdmissionBase.LastHold': prefix + 'FfaLateEntry.Hold'}
    standins = {'ReadmitAdmissionBase': 'FfaLateEntry', 'ReducerBase': 'FfaMode',
                'ReadmitOfferAdapterBase': 'FfaReadmit', 'ReadmitOfferAdapter': 'FfaReadmit', 'FfaReplay': 'FfaMode'}
    folder = 'tools/tests/rj-readmit-client/'
    try:
        projects = [_project_sources(tree, folder + project)
                    for project in ('apply-trace/ApplyTrace.csproj', 'rules/RjRules.csproj')]
        sources = set().union(*(pair[0] for pair in projects))
        sources.update({folder + 'apply-trace/Stubs.cs', folder + 'apply-trace/TraceProgram.cs'})
        sources.update(os.path.relpath(p, tree).replace(os.sep, '/')
                       for p in glob.glob(os.path.join(tree, folder, 'rules', '*.cs')))
        linked = set().union(*(pair[1] for pair in projects))
        mode = read_text(os.path.join(tree, 'plugin', 'FfaMode.cs'))
        late = read_text(os.path.join(tree, 'plugin', 'FfaLateEntry.cs'))
        adapter = read_text(os.path.join(tree, 'plugin', 'FfaReadmit.cs'))
        generated = {'generated/Reducers.cs': reducer_source(wt, mode, late),
                     'generated/ReadmitOfferAdapter.cs': adapter_source(adapter, late)}
        mutants = [
            ('M-STUB-1', 'stub', folder + 'apply-trace/Stubs.cs',
             'internal struct Proposal', 'internal sealed class Proposal', prefix + 'FfaLateRules.Proposal'),
            ('M-STUB-2', 'production', 'plugin/FfaLateRules.cs',
             'internal struct Proposal', 'internal class Proposal', prefix + 'FfaLateRules.Proposal')]
        return _stub_kind_control(tree, sources, linked, mapped, external, harness_only, standins, mutants, generated)
    except (OSError, ValueError, KeyError, RuntimeError, StopIteration, ET.ParseError) as exc:
        print('stub-kind control RED:', str(exc))
        return False


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def read_text(path):
    return open(path, "rb").read().decode("utf-8")


def extract(text, sig):
    """The member whose declaration line starts with sig, through the first
    following line that is exactly the class-member closing brace."""
    lines = text.splitlines(keepends=True)
    starts = [i for i, l in enumerate(lines) if l.lstrip().startswith(sig)]
    if len(starts) != 1:
        raise RuntimeError("signature %r occurs %d times" % (sig, len(starts)))
    s = starts[0]
    for j in range(s + 1, len(lines)):
        if lines[j].rstrip("\r\n") == "        }":
            return "".join(lines[s:j + 1])
    raise RuntimeError("no end for %r" % sig)


def release_route_census(texts):
    """Census each real synchronous route and the completed-entry fact sites."""
    rows, verdicts = [], {}
    for route, source, signature, call, clears in RELEASE_ROUTES:
        try:
            member = _blank_csharp(extract(texts[source], signature)).replace("\r\n", "\n")
            all_calls = re.findall(r'\b(?:FfaReadmit\s*\.\s*)?Abandon\s*\(', member)
            count = member.count(call)
            correct = len(all_calls) == 1 and count == 1
            before_clear = all(member.count(clear) == 1 and count == 1
                               and member.index(call) < member.index(clear) for clear in clears)
            correct = correct and before_clear
            reason = "calls=%d expected=%d before_clear=%s" % (len(all_calls), count, before_clear)
        except (KeyError, RuntimeError, ValueError) as exc:
            correct, reason = False, str(exc)
        verdicts[route] = correct
        rows.append("%s %s.%s: %s" % ("PASS" if correct else "FAIL", F2E_ROUTE_TARGET, route, reason))
    try:
        late = texts["FfaLateEntry.cs"]
        kept = _blank_csharp(extract(late, "private static void OnSelfKept(")).replace("\r\n", "\n")
        starts = _blank_csharp(extract(late, "internal static void PrepareReadmitEntry(")).replace("\r\n", "\n")
        ends = _blank_csharp(extract(late, "internal static void OnRoomLeft(")).replace("\r\n", "\n")
        completed = "_lateEntered = true;"
        writes = ("_readmitEnteredLobby = AdmittedLateLobby;", "_readmitEnteredGame = _lateGame;")
        post = "FfaReadmit.PostEntered("
        correct = kept.count(completed) == 1 and kept.count(post) == 1
        correct = correct and all(kept.count(write) == 1 and kept.index(completed) < kept.index(write) < kept.index(post)
                                  for write in writes)
        resets = ("_readmitEnteredLobby = null;", "_readmitEnteredGame = 0;")
        correct = correct and all(member.count(reset) == 1 for member in (starts, ends) for reset in resets)
        reason = "write_after_entry_before_post_and_both_resets=" + str(correct)
    except (KeyError, RuntimeError, ValueError) as exc:
        correct, reason = False, str(exc)
    verdicts["entry-fact"] = correct
    rows.append("%s %s.entry-fact: %s" % ("PASS" if correct else "FAIL", F2E_ROUTE_TARGET, reason))
    legacy = all(verdicts[route] for route in ("release", "leave", "depart"))
    rows.append("%s %s: legacy release, leave and depart" % ("PASS" if legacy else "FAIL", RELEASE_ROUTE_TARGET))
    rows.append("release-route census: %d of %d routes pass" % (sum(verdicts.values()), len(verdicts)))
    return verdicts, "\n".join(rows)


def entry_fact_fields(late_text, admission_game=False):
    """Copy the production declarations needed by the extracted OnSelfKept."""
    fields = []
    declarations = ["private static string _readmitEnteredLobby;", "private static int _readmitEnteredGame;"]
    if admission_game:
        declarations.append("private static int _lateGame;")
    for declaration in declarations:
        matches = [line for line in late_text.splitlines() if line.strip() == declaration]
        if len(matches) != 1:
            raise RuntimeError("entry fact declaration must occur once: " + declaration)
        fields.append(matches[0] + "\n")
    return "".join(fields)


def extract_statement(text, start):
    if text.count(start) != 1:
        raise RuntimeError("statement anchor must occur once: " + start)
    begin = text.index(start)
    return text[begin:text.index(";", begin) + 1]


def reducer_source(wt, new_mode_text, late_text):
    base = subprocess.run(["git", "-C", wt, "show", BASE + ":plugin/FfaMode.cs"],
                          capture_output=True).stdout.decode("utf-8")
    if not base:
        raise RuntimeError("cannot read the base reducer at " + BASE)
    amp = "private static IEnumerator ApplyManifestPick("
    rc = "private static CardInfo ResolveCard("
    rd = "private static string RosterDisplayName("
    parts = [
        "using System;\nusing System.Collections;\nusing System.Collections.Generic;\nusing System.Linq;\n\n",
        "namespace CompetitiveRounds\n{\n",
        "    internal sealed class OldReducer : ReducerBase\n    {\n",
        "        internal static IEnumerator Run(int pid, string card, int cycle, bool bodiless) "
        "{ return ApplyManifestPick(pid, card, cycle); }\n\n",
        extract(base, amp), "\n", extract(base, rc), "\n    }\n\n",
        "    internal sealed class NewReducer : ReducerBase\n    {\n",
        "        internal static IEnumerator Run(int pid, string card, int cycle, bool bodiless) "
        "{ return ApplyManifestPick(pid, card, cycle, bodiless); }\n\n",
        extract(new_mode_text, amp), "\n", extract(new_mode_text, rc), "\n", extract(new_mode_text, rd),
        "\n    }\n",
        "    internal sealed class FfaReplay : ReducerBase\n    {\n",
        next(l + "\n" for l in new_mode_text.splitlines() if "internal enum ReadmitReplayState " in l),
        extract(new_mode_text, "internal sealed class ReadmitReplayOutcome"), "\n",
        "        private static int _readmitReplayGeneration = 1;\n",
        "        private static readonly Dictionary<int, ReadmitReplayOutcome> _readmitReplayOwners = new Dictionary<int, ReadmitReplayOutcome>();\n",
        "        internal static bool Current(ReadmitReplayOutcome replay) { return ReadmitReplayCurrent(replay); }\n",
        "        internal static int Generation { get { return _readmitReplayGeneration; } }\n",
        extract(new_mode_text, "internal static void InvalidateReadmitReplays("), "\n",
        extract(new_mode_text, "internal static bool ReadmitReplayReady("), "\n",
        extract(new_mode_text, "internal static bool ReadmitReplayNames("), "\n",
        extract(new_mode_text, "internal static void CancelReadmitReplay("), "\n",
        extract(new_mode_text, "internal static bool CommitReadmitReplay("), "\n",
        extract(new_mode_text, "private static bool ReadmitReplayCurrent("), "\n",
        extract(new_mode_text, "private static bool ReadmitReplayDeckCurrent("), "\n",
        extract(new_mode_text, "internal static bool ReadmitReplayPrepared("), "\n",
        extract(new_mode_text, "internal static IEnumerator ReadmitReplaySteps("), "\n",
        extract(new_mode_text, rc), "\n    }\n",
        "    internal sealed class FfaReplayAdmission : ReadmitAdmissionBase\n    {\n",
        entry_fact_fields(late_text, admission_game=True),
        "        internal static void Ack() { TryAckReadmitProposal(); }\n",
        "        internal static void Propose() { OnProposal(ProposalEvent()); }\n",
        "        internal static void Propose(EventData e) { OnProposal(e); }\n",
        extract(late_text, "private static void OnProposal("), "\n",
        "        internal static void Entered(int game) { OnSelfKept(game); }\n",
        "        internal static bool Prepare(int epoch) { return PrepareReadmitEpoch(epoch); }\n",
        extract(late_text, "internal static bool IsKeptActor("), "\n",
        extract(late_text, "private static bool PrepareReadmitEpoch("), "\n",
        extract(late_text, "internal static bool ReadmitBoundaryReady("), "\n",
        extract(late_text, "internal static bool ReadmitEnteredReady("), "\n",
        extract(late_text, "private static void TryAckReadmitProposal("), "\n",
        extract(late_text, "private static void OnSelfKept("), "\n",
        "        internal static bool MasterAck(bool prepared)\n        {\n",
        "            if (!_replayProposal.HasValue) return false;\n",
        "            var barrier = new List<int>(); var proposal = _replayProposal.Value; int self = OwnActor();\n",
        "            List<int> missing; bool ackComplete;\n",
        extract_statement(late_text, "                    ackComplete = FfaLateRules.AckComplete("), "\n",
        "            return ackComplete;\n        }\n    }\n}\n",
    ]
    return "".join(parts)


def gen_reducers(wt, new_mode_text, late_text, out_dir):
    source = reducer_source(wt, new_mode_text, late_text)
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, "Reducers.cs"), "wb").write(source.encode("utf-8"))


def adapter_source(adapter, late):
    content = "\nnamespace CompetitiveRounds\n{\n    internal sealed class ReadmitOfferAdapter : ReadmitOfferAdapterBase\n    {\n"
    content += "        internal static void SendForTest(string step, int actor, int game) { Send(step, actor, game); }\n"
    content += "        internal static void ActForTest(string step, FfaReadmitEntryRules.RdmNext next) { Act(step, next, null); }\n"
    content += "        internal static void RefusalForTest(string reason, bool leave) { Refusal(reason, leave); }\n"
    content += "        internal static void SetEntryFactForTest(string lobby, int game, bool completed, string admittedLobby) { FfaLateEntry.SetForTest(lobby, game, completed, admittedLobby); }\n"
    for sig in ("internal static bool Abandon(",
                "private static void InvalidateMatchingWork(",
                "internal static void DiscoverThenProbe(",
                "internal static FfaReadmitEntryRules.RdmOffer OfferFromPoll(",
                "internal static bool SuppressesDiscoveryProbe(",
                "private static FfaReadmitEntryRules.RdmOffer Offer(",
                "internal static bool ClaimedFor(",
                "internal static bool ReadmittedInto(",
                "internal static void Accept(",
                "private static void Send(",
                "private static FfaReadmitEntryRules.RdmAnswer ParseAnswer(",
                "private static void Act(",
                "private static void Refusal(",
                "internal static void PostEntered("):
        content += extract(adapter, sig) + "\n"
    content += "        private static class FfaLateEntry\n        {\n"
    content += entry_fact_fields(late)
    content += "        private static bool _lateEntered;\n        private static string AdmittedLateLobby;\n"
    content += extract(late, "internal static bool ReadmitEntryCompleted(") + "\n"
    content += "        internal static void SetForTest(string lobby, int game, bool completed, string admittedLobby)\n"
    content += "        { _readmitEnteredLobby = lobby; _readmitEnteredGame = game; _lateEntered = completed; AdmittedLateLobby = admittedLobby; }\n"
    content += "        internal static void PrepareReadmitEntry() { PrepareCalls++; }\n"
    content += "        internal static void OnAdmittedLate(FfaAssembly.Answer answer) { ArmCalls++; }\n"
    content += "        }\n"
    return content + "    }\n}\n"


def build(proj, out, props):
    cmd = ["dotnet", "build", proj, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep]
    cmd += ["-p:%s=%s" % kv for kv in props.items()]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-6000:], r.stderr[-2000:])
        return None
    name = os.path.splitext(os.path.basename(proj))[0]
    return os.path.join(out, "bin", name + ".dll")


def run_case(dll, case):
    r = subprocess.run(["dotnet", dll, case], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def project(tree, suite):
    return os.path.join(tree, REL, {"apply": os.path.join("apply-trace", "ApplyTrace.csproj"),
                                    "rules": os.path.join("rules", "RjRules.csproj")}[suite])


def prepare(tree, wt, suite, work, tag, texts):
    """Writes this variant's copies and builds it; returns the dll."""
    out = os.path.join(work, suite + "_" + tag)
    os.makedirs(out, exist_ok=True)
    props = {}
    for f, prop in SUITE_FILES[suite].items():
        if prop is None and suite != "rules":
            continue
        p = os.path.join(out, f)
        content = texts[f]
        if suite == "rules" and f == "FfaReadmitEntryRules.cs":
            content += adapter_source(texts["FfaReadmit.cs"], texts["FfaLateEntry.cs"])
        open(p, "wb").write(content.encode("utf-8"))
        if prop is not None:
            props[prop] = p
    if suite == "apply":
        gen_reducers(wt, texts["FfaMode.cs"], texts["FfaLateEntry.cs"], os.path.join(out, "gen"))
        props["GenDir"] = os.path.join(out, "gen")
    return build(project(tree, suite), out, props)


def suite_cases(suite, dll):
    if suite == "apply":
        return APPLY_CASES
    r = subprocess.run(["dotnet", dll, "--list"], capture_output=True, text=True)
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--tree", default=DEFAULT_TREE)
    ap.add_argument("--wt", default="")
    ap.add_argument("--suite", default="all")
    ap.add_argument("--only", default="")
    ap.add_argument("--stub-kinds", action="store_true", help="check all type declarations without building or writing")
    a = ap.parse_args()
    tree = os.path.abspath(a.tree)
    wt = os.path.abspath(a.wt) if a.wt else tree
    kinds_ok = stub_kinds(tree, wt)
    if not kinds_ok or a.stub_kinds:
        print("RESULT", "PASS" if kinds_ok else "FAIL")
        return 0 if kinds_ok else 1
    work = os.path.abspath(a.work)
    os.makedirs(work, exist_ok=True)
    head = subprocess.run(["git", "-C", wt, "log", "--oneline", "-1"], capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", wt, "status", "--porcelain"], capture_output=True, text=True).stdout
    print("worktree", wt)
    print("commit", head)
    print("worktree state", "clean" if not status.strip() else "dirty:\n" + status.rstrip())
    print("tree under test", tree)
    files = sorted(set(f for s in SUITE_FILES.values() for f in s))
    srcs = {f: os.path.join(tree, "plugin", f) for f in files}
    for f in files:
        print("source plugin/%s sha256 %s" % (f, sha(srcs[f])))
    for root, _, names in sorted(os.walk(os.path.join(tree, REL))):
        for n in sorted(names):
            if n.endswith((".cs", ".csproj", ".py")) and os.sep + "bin" not in root and os.sep + "obj" not in root:
                p = os.path.join(root, n)
                print("source %s sha256 %s" % (os.path.relpath(p, tree).replace(os.sep, "/"), sha(p)))
    before = {f: sha(srcs[f]) for f in files}
    texts = {f: read_text(srcs[f]) for f in files}
    suites = ["apply", "rules"] if a.suite == "all" else a.suite.split(",")
    only = set(x for x in a.only.split(",") if x)
    ok = True
    for suite in suites:
        if suite == "rules":
            route_rows, routes_out = release_route_census(texts)
            print(routes_out)
            ok = ok and all(route_rows.values())
        dll = prepare(tree, wt, suite, work, "base", texts)
        if dll is None:
            print("BUILD FAILED (%s base)" % suite)
            ok = False
            continue
        cases = suite_cases(suite, dll)
        passed = 0
        for case in cases:
            rc, out = run_case(dll, case)
            print(out)
            passed += rc == 0
            ok = ok and rc == 0
        print("suite %s: %d of %d cases pass" % (suite, passed, len(cases)))
        if not cases:
            ok = False
        caught = total = 0
        for mid, piece, msuite, mfile, edits, target, control in MUTANTS:
            if msuite != suite or (only and mid not in only):
                continue
            total += 1
            raw = texts[mfile]
            nl = "\r\n" if "\r\n" in raw else "\n"
            text = raw
            good = True
            for old, new in edits:
                o, n = old.replace("\n", nl), new.replace("\n", nl)
                count = text.count(o)
                if count != 1:
                    print("BAD mutant %s: anchor occurs %d times" % (mid, count))
                    good = False
                    break
                text = text.replace(o, n)
            if not good:
                ok = False
                continue
            mtexts = dict(texts)
            mtexts[mfile] = text
            mdll = prepare(tree, wt, suite, work, "mut_" + mid.replace(".", "_"), mtexts)
            if mdll is None:
                print("BAD mutant %s: does not build" % mid)
                ok = False
                continue
            route = MUTANT_ROUTES.get(mid)
            siblings_green = True
            if route is not None:
                route_rows, tout = release_route_census(mtexts)
                trc = 0 if route_rows.get(route, True) else 1
                siblings_green = all(passed for sibling, passed in route_rows.items() if sibling != route)
            else:
                trc, tout = run_case(mdll, target)
            crc, cout = run_case(mdll, control)
            extras_green = True
            extra_cases = []
            if mid == "M-F2E-site-refusal":
                extra_cases = [("C4.F2E.lapse_refused_bind", False)]
            elif mid == "M-F2E-entrykeep":
                extra_cases = [(case, True) for case in (
                    "C4.F2E.lapse_refused_bind", "C4.F2E.delayed_after_leave",
                    "C4.F2E.delayed_after_release", "C4.F2E.delayed_after_depart")]
            for extra, want_green in extra_cases:
                erc, eout = run_case(mdll, extra)
                extras_green = extras_green and ((erc == 0) == want_green)
                print("additional mutant check %s: %s=%s expected=%s" % (
                    mid, extra, "GREEN" if erc == 0 else "RED", "GREEN" if want_green else "RED"))
                if (erc == 0) != want_green:
                    print("   " + eout[-600:])
            hit = trc != 0 and crc == 0 and siblings_green and extras_green
            caught += hit
            ok = ok and hit
            print("%s mutant %s (%s): target %s=%s; control %s=%s" % (
                "CAUGHT" if hit else "MISSED", mid, piece, target, "RED" if trc else "GREEN", control,
                "GREEN" if crc == 0 else "RED"))
            if route is not None:
                print("   route %s: siblings=%s" % (route, "GREEN" if siblings_green else "RED"))
                print("   " + "\n   ".join(tout.splitlines()))
            elif trc:
                print("   " + "\n   ".join(tout.splitlines()[:4]))
            if not hit:
                print("   " + tout[-600:])
                print("   control: " + cout[-600:])
        print("suite %s: mutants %d of %d caught" % (suite, caught, total))
    unchanged = all(sha(srcs[f]) == before[f] for f in files)
    print("source plugin files unchanged by the run:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
