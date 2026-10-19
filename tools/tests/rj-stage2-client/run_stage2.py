"""Stage 2 (2v2 and 1v2 readmission) client rules harness.

Builds the REAL plugin/SeatDeckLog.cs, plugin/TeamHoldRules.cs and
plugin/TeamHoldNet.cs, as they ship, with Program.cs, and runs every scripted
fixture, each in its own process. Then mutants planted into COPIES of those
files (the tracked files are never written): each mutant's target fixture
must FAIL and its negative control fixture must PASS (#391). Exit 0 only when
everything holds.

    python tools/tests/rj-stage2-client/run_stage2.py --work <scratch dir> [--piece K0]

--work is required: every build output and mutant copy goes there, never into
the tree. --piece limits the fixtures and mutants to one piece (K0 to K6);
without it every piece runs. The K0 run also runs the S0 inventory check (the
application sites of RPCA_Pick and OFFLINE_Pick) and its negative control.
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PLUGIN = os.path.join(REPO, "plugin")
PROJ = os.path.join(HERE, "Stage2Tests.csproj")
FILES = {"seat": "SeatDeckLog.cs", "rules": "TeamHoldRules.cs", "net": "TeamHoldNet.cs"}
PROPS = {"seat": "SeatSource", "rules": "RulesSource", "net": "NetSource"}

# Fixture name prefix per piece.
PIECES = {
    "K0": ("t01_", "t02_", "t0_"),
    "K1": ("t11_", "t12_", "t15_", "t16_", "t1_"),
    "K2": ("t23_", "t24_", "t25_", "t26_", "t29_", "t2_"),
    "K3": ("t33_", "t37_", "t38_", "t39_", "t3_"),
    "K4": ("t43_", "t45_", "t4_"),
    "K5": ("t52_", "t56_", "t58_", "t5_"),
    "K6": ("t6_",),
    # The refit lane (claude/rj-stage2-refit), one entry per continuation piece.
    "KX1": ("tx1_", "t16_"),
    "KX2": ("t27_",),
    "KX3": ("t35_", "tx3_"),
    "KX4": ("t34_", "tx4_"),
    "KX5": ("t41_", "t42_", "t44_", "tx5_"),
    "KX6": ("t55_", "t57_", "tx6_"),
    "KX8": ("tx8_", "t16_", "t29_", "t39_", "t58_"),
    "KX9A": ("t16_", "tx9_", "t6_claimed"),
    "KX9B": ("t16_", "t29_", "t36_", "t39_", "t58_", "tx9_"),
}

# (name, piece, file, [(old, new), ...], target fixture, control fixture);
# each old occurs exactly once in the file.
MUTANTS = [
    # K0, S0
    ("M0.1", "K0", "seat", [
        ("            for (int i = 0; i < it.Slots.Length; i++)\n                Commit(ViewKey(it.ViewId), it.Slots[i], it.Name);\n        }",
         "        }"),
        ("internal static void ObserveEndPick(int slot, string name) { }",
         "internal static void ObserveEndPick(int slot, string name) { Commit(\"e\" + SeatOf(slot).Deals, slot, name); }")],
     "t01_opening_2v2", "t02_dup_die"),
    ("M0.2", "K0", "seat", [
        ("_intents.Push(new Intent { ViewId = viewId, Name = name, Slots = slots ?? new int[0] });",
         "_intents.Push(new Intent { ViewId = viewId, Name = name, Slots = slots ?? new int[0] });\n"
         "            foreach (var s in slots ?? new int[0]) Commit(ViewKey(viewId), s, name);")],
     "t01_throw", "t01_opening_2v2"),
    ("M0.3", "K0", "seat", [
        ("internal static void ObserveEndPick(int slot, string name) { }",
         "internal static void ObserveEndPick(int slot, string name) { Commit(\"e\" + SeatOf(slot).Deals, slot, name); }")],
     "t01_duplicate", "t01_opening_2v2"),
    ("M0.4", "K0", "seat", [
        ("internal static void ObserveOfflinePick(int slot, string name) { _replays++; }",
         "internal static void ObserveOfflinePick(int slot, string name) { _replays++; Commit(\"o\" + _replays, slot, name); }")],
     "t01_replay", "t01_opening_2v2"),
    ("M0.5", "K0", "seat", [
        ("var c = TryClaim(slot, tuple, CLAIM_DEPART);",
         "var c = TryClaim(slot, \"departure|\" + tuple, CLAIM_DEPART);")],
     "t02_leave_then_die", "t02_dup_die"),
    ("M0.6", "K0", "seat", [
        ("return TryClaim(slot, tuple, CLAIM_PHOENIX);", "return Claim.Won;")],
     "t02_phoenix_then_leave", "t02_dup_die"),
    # K1, S1
    ("M1.1", "K1", "rules", [
        ("if (i == null || i.Pin == null || !i.Pin.Hold) return false;",
         "if (i == null || i.Pin == null || !(i.Pin.Hold || i.QuorumCapable)) return false;")],
     "t11_quorum_not_flag", "t11_gate_all_true"),
    ("M1.2", "K1", "rules", [
        ("if (i.IsSpec) return false;",
         "if (i.IsSpec) return false;\n                if (i.LocalUnauthorized || !i.LocalInMatch) return false;")],
     "t11_stale_cache", "t11_gate_all_true"),
    ("M1.3", "K1", "rules", [
        ("string mode = i.Pin.Mode;",
         "string mode = (i.RoomName ?? \"\").StartsWith(\"ovt_\") ? MODE_OVT : (i.RoomName ?? \"\").StartsWith(\"team_\") ? MODE_TEAM : \"\";")],
     "t11_hosted_lobby", "t11_gate_all_true"),
    ("M1.4", "K1", "rules", [
        ("catch { r = false; }", "catch { r = true; }")],
     "t12_three_clients_throw", "t11_gate_all_true"),
    ("M1.9", "K1", "rules", [
        ("internal const bool ViaMasterArm = true;", "internal const bool ViaMasterArm = false;")],
     "t15_2v2_team_down", "t15_2v2_partner_alive"),
    ("M1.10", "K1", "rules", [
        ("            if (observed != 'p' && observed != 'o' && observed != 'x') return Resolve.Wait;\n", "")],
     "t15_handover_wait", "t15_2v2_team_down"),
    # K1, lane-added: the extracted election must answer as the base callback did.
    ("M1.E", "K1", "rules", [
        ("int nonDcCount = 0, dcTeamCount = 1;", "int nonDcCount = 0, dcTeamCount = 0;")],
     "t1_dc_equiv", "t11_gate_all_true"),
    # K2, S2
    ("M2.8", "K2", "rules", [
        ("if (room.State == 'p') return Verdict.Act;", "return Verdict.Act;")],
     "t23_forged_b_e_x", "t23_verified_o"),
    ("M2.9", "K2", "rules", [
        ("if (observed != 'p' && observed != 'o' && observed != 'x') return Resolve.Wait;",
         "if (observed == '\\u0001') return Resolve.Wait;")],
     "t24_resolve_waits", "t24_promote_before_p"),
    ("M2.10", "K2", "rules", [
        ("if (P == Phase.Pending && now - PendingAt >= OpenTimeoutS) return End(now, \"no_answer\");", "")],
     "t24_404_by_room_ends", "t24_during_post"),
    ("M2.11", "K2", "rules", [
        ("if (FirstP >= 0 && VerifiedO < 0 && now - FirstP >= PendingS) return true;", "")],
     "t25_pending_ceiling", "t25_bind_ceiling"),
    ("M2.12", "K2", "rules", [
        ("Step.Visualize, Step.Wait1, Step.LoadNext, Step.Wait05, Step.Fence, Step.SyncUp,",
         "Step.Visualize, Step.Wait1, Step.LoadNext, Step.Wait05, Step.SyncUp,")],
     "t26_point_fenced", "t26_round_pick_inside"),
    # K2, lane-added: a state is not refuted before this client's own read answers.
    ("M2.E", "K2", "rules", [
        ("if (server == null) return Verdict.Inert;", "if (server == null) server = new TeamHoldNet.StateAnswer();")],
     "t23_read_pending", "t23_verified_o"),
    # K3, S3
    ("M3.5", "K3", "rules", [
        ("internal static string SnapshotDigest(Snapshot s) { return Fnv64Hex(s.Format()); }",
         "internal static string SnapshotDigest(Snapshot s) { return Fnv64Hex(s.HoldId + \":\" + s.G + \":\" + s.Boundary()); }")],
     "t33_mutations", "t33_honest"),
    ("M3.6", "K3", "rules", [
        ("if (expectedPeers < 1 || present < expectedPeers) return \"digest missing\";",
         "if (expectedPeers < 1 || present < expectedPeers - 1) return \"digest missing\";")],
     "t33_ovt_digest_absent", "t33_honest"),
    ("M3.7", "K3", "rules", [
        ("if (BoundaryDigest(snap.BR0, snap.BR1, snap.BP0, snap.BP1, snap.BNames) != serverBoundaryDigest) return \"boundary checkpoint mismatch\";", "")],
     "t33_colluding_duo", "t33_honest"),
    ("M3.16", "K3", "rules", [
        ("if (string.IsNullOrEmpty(rdt) || string.IsNullOrEmpty(holdId) || string.IsNullOrEmpty(verifierHex)) return false;",
         "return true;")],
     "t37_token", "t37_genuine"),
    # K4, S4
    ("M4.5", "K4", "rules", [
        ("return TryParseHold(th, out k) && IsLive(k.State) && k.Slot == slot;",
         "return !bodyResolves;")],
     "t43_delayed_purge", "t43_before_phase"),
    ("M4.6", "K4", "seat", [
        ("if (seat.Deals > k) { superseded = true; return false; }", "")],
     "t43_after_own_pick", "t43_before_phase"),
    # K5, S5
    ("M5.2", "K5", "rules", [
        ("case DcKind.Floor: r.Add(ExpiryOp.ReportFloor); break;",
         "case DcKind.Floor: case DcKind.StandDown: r.Add(ExpiryOp.ReportFloor); break;")],
     "t52_stand_down_kept", "t56_ovt_no_report"),
    ("M5.3", "K5", "rules", [
        ("                switch (cut.Eligibility)",
         "                if (presentAtExpiry != null && presentAtExpiry.Count < 2 && cut.Eligibility == DcKind.Fallback) { r.Add(ExpiryOp.ReportPrompt); r.Add(ExpiryOp.VanillaLeave); return r; }\n"
         "                switch (cut.Eligibility)")],
     "t52_census_changed", "t52_clean_census"),
    ("M5.9", "K5", "rules", [
        ("            if (cut.Mode == MODE_TEAM)\n            {\n                switch (cut.Eligibility)",
         "            if (cut.Mode == MODE_TEAM || cut.Mode == MODE_OVT)\n            {\n                switch (cut.Eligibility)")],
     "t56_ovt_no_report", "t52_clean_census"),
    # K6, S6 ladder lines (lane-added: each removes or widens one emission).
    ("M6.E1", "K6", "rules", [
        ("                SeatDeckLog.Emit(\"[HOLD] auto grant slot=\" + I(slot) + \" card=\" + card);\n", "")],
     "t6_auto_grant", "t6_grant_superseded"),
    ("M6.E2", "K6", "rules", [
        ("if (r && inputs != null) SeatDeckLog.Emit(", "if (inputs != null) SeatDeckLog.Emit(")],
     "t6_negative", "t6_cascade_suppressed"),
    ("M6.E3", "K6", "rules", [
        ("if (next != 'o' || prev == 'o' || prev == 'c'", "if (next != 'o' || prev == 'c'")],
     "t6_held", "t6_offered"),
    ("M6.E4", "K6", "net", [
        ("if (a.Ok) SeatDeckLog.Emit(\"[HOLD] claimed slot=\"", "SeatDeckLog.Emit(\"[HOLD] claimed slot=\"")],
     "t6_claimed", "t6_bound"),
    ("M6.E5", "K6", "seat", [
        ("            if (first)\n                Emit(\"[SEATLOG] drift slot=\"", "            if (first && slot < 0)\n                Emit(\"[SEATLOG] drift slot=\"")],
     "t6_drift", "t0_drift"),
    # KX1 (lane-added: the transport binding has no V3 mutant row).
    ("MX1.1", "KX1", "net", [
        ("try { carried = !string.IsNullOrEmpty(token()) && carries(path); } catch { carried = false; }",
         "carried = true;")],
     "tx1_no_token_today", "tx1_token_reaches_route"),
    ("MX1.2", "KX1", "net", [
        ("if (code == 401) { body = SessionRequired; return; }", "")],
     "tx1_401_today", "tx1_map_codes"),
    ("MX1.3", "KX1", "net", [
        ("TeamHoldRules.PinRoom(room, BoolField(answer, \"hold\"), mode, seriesId, roster);",
         "TeamHoldRules.PinRoom(room, true, mode, seriesId, roster);")],
     "t16_join_pin_today", "tx1_server_shapes"),
    # KX2, live points (V3 M2.13; MX2.1 and MX2.2 lane-added).
    ("M2.13", "KX2", "rules", [
        ("return !(Held(room) && stamp > _observedAt);", "return true;")],
     "t27_open_delayed_reordered", "t27_no_post_while_held"),
    ("MX2.1", "KX2", "rules", [
        ("                Observe(room, th);\n                if (ThLive(th)) return 0;\n", "                Observe(room, th);\n")],
     "t27_no_post_while_held", "t27_open_delayed_reordered"),
    ("MX2.2", "KX2", "rules", [
        ("else if (_room == room && _g == k.G && _slot == k.Slot) { _observedAt = -1;", "else if (_room == room) { _observedAt = -1;")],
     "t27_lift_and_rooms", "t27_open_delayed_reordered"),
    # KX3, admission (V3 M3.11, M3.12, M3.17; MX3.1 lane-added).
    ("M3.11", "KX3", "rules", [
        ("if (!Flagged(room)) return null;", "return null;")],
     "t35_span_games", "t35_release_at_bind"),
    ("M3.12", "KX3", "rules", [
        ("var ids = new List<string>(pin.Roster);",
         "var ids = new List<string>(pin.Roster); foreach (var u in present()) if (!ids.Contains(u)) ids.Add(u);")],
     "t35_stranger", "t35_span_games"),
    ("M3.17", "KX3", "rules", [
        ("return k.BoundActor <= 0 || actor != k.BoundActor;", "return null;")],
     "tx3_held_seat_identity", "t35_span_games"),
    ("MX3.1", "KX3", "rules", [
        ("if (lastReleased == id) return false;", "")],
     "t35_release_at_bind", "t35_span_games"),
    # KX4, registration (V3 M3.8, M3.9, M3.10; MX4.1 to MX4.3 lane-added).
    ("M3.8", "KX4", "rules", [
        ("            int at = index(ids, newId);\n            if (at < 0) return -1;\n            list.Insert(at, null);\n            return at;\n",
         "            if (ids.Contains(newId)) return -1;\n            return newId;\n")],
     "t34_high_slot", "t34_duplicate_and_today"),
    ("M3.9", "KX4", "rules", [
        ("            list.Insert(at, null);\n", "")],
     "t34_low_slot", "t34_high_slot"),
    ("M3.10", "KX4", "rules", [
        ("list.Insert(at, null);", "list.Insert(at, null); list.Insert(at, null);")],
     "t34_high_slot", "t34_duplicate_and_today"),
    ("MX4.1", "KX4", "rules", [
        ("{ return readmitLobby || Flagged(room); }", "{ return readmitLobby; }")],
     "t34_high_slot", "tx4_seed_plan"),
    ("MX4.2", "KX4", "rules", [
        ("p.DrawIndex = st.Deals;", "p.DrawIndex = st.Deals - 1;")],
     "tx4_seed_plan", "t34_high_slot"),
    ("MX4.3", "KX4", "rules", [
        ("            list.RemoveAll(p => p == null || dead(p));\n", "")],
     "t34_low_slot", "t34_high_slot"),
    # KX5, the record (V3 M4.1, M4.2, M4.3, M4.4, M4.7).
    ("M4.1", "KX5", "rules", [
        ("internal static bool BuildsRecord(bool flagged, bool holdLive) { return flagged; }",
         "internal static bool BuildsRecord(bool flagged, bool holdLive) { return flagged && holdLive; }")],
     "t41_twin_run", "tx5_off_codec"),
    ("M4.2", "KX5", "rules", [
        ("return r != null ? r.FirstOf(slot) : null;",
         "return r != null && r.ListOf(slot) != null && r.ListOf(slot).Count > 1 ? r.ListOf(slot)[1] : null;")],
     "t41_twin_run", "t42_ledger"),
    ("M4.3", "KX5", "rules", [
        ("FfaReadmitRules.AdoptRecord(rec, spend, setDrawIndex);",
         "FfaReadmitRules.AdoptRecord(rec, new FfaReadmitRules.SpendState(), setDrawIndex);")],
     "t42_ledger", "tx5_off_codec"),
    ("M4.4", "KX5", "rules", [
        ("FfaReadmitRules.AdoptRecord(rec, spend, setDrawIndex);", ""),
        ("internal static void NoteGrantApplied(FfaReadmitRules.SpendState spend, string card) { }",
         "internal static void NoteGrantApplied(FfaReadmitRules.SpendState spend, string card) { if (card != null) spend.Ledger.Add(card); }")],
     "t42_ledger", "tx5_off_codec"),
    ("M4.7", "KX5", "rules", [
        ("if (h != null) return h;", "")],
     "t44_rule_p_promotion", "t41_twin_run"),
    # KX6, reports after a return (V3 M5.8; MX6.1 to MX6.4 lane-added).
    ("M5.8", "KX6", "rules", [
        ("            if (Flagged(room)) return true;\n            return me == lowest;\n",
         "            return me == lowest;\n")],
     "t55_every_present_files", "t57_held_census"),
    ("MX6.1", "KX6", "rules", [
        ("presentUids.Count != need - 1", "presentUids.Count > need - 1")],
     "t57_held_census", "t55_every_present_files"),
    ("MX6.2", "KX6", "rules", [
        ("if (u == heldUid || !pin.Roster.Contains(u)) return null;", "if (u == heldUid) return null;")],
     "t57_held_census", "t55_every_present_files"),
    ("MX6.3", "KX6", "rules", [
        ('return "game-id:" + (g ?? "") + ":" + (reporter ?? "") + ":" + (room ?? "");',
         'return "game-id:" + (g ?? "") + ":" + (room ?? "") + ":" + (reporter ?? "");')],
     "tx6_game_id", "t55_every_present_files"),
    ("MX6.4", "KX6", "rules", [
        ('return body != null && body.Replace(" ", "").IndexOf(', 'return body != null || body.Replace(" ", "").IndexOf(')],
     "tx6_journaled_terminal", "t55_every_present_files"),
    # KX8, the capability token (MX8.1 lane-added).
    ("MX8.1", "KX8", "rules", [
        ("return allAttached ? ", "return true ? ")],
     "tx8_caps", "t16_join_pin_today"),
    # KX9 Part A, the request side (MX9.1 to MX9.4 lane-added).
    ("MX9.1", "KX9A", "net", [
        (".Append(\",\\\"series_id\\\":\").Append(Q(seriesId))\n", "\n")],
     "t16_server_model_fields", "t16_join_pin_today"),
    ("MX9.2", "KX9A", "net", [
        ("+ \",\\\"held_steam_id\\\":\" + Q(heldSteam)", "+ \",\\\"held_steam\\\":\" + Q(heldSteam)")],
     "t16_server_model_fields", "t16_join_pin_today"),
    ("MX9.3", "KX9A", "net", [
        ("internal static string ClaimBody(string steamId) { return \"{\\\"steam_id\\\":\" + Q(steamId) + \"}\"; }",
         "internal static string ClaimBody(string steamId) { return \"{}\"; }")],
     "t16_server_model_fields", "t16_join_pin_today"),
    ("MX9.4", "KX9A", "net", [
        ("            return \"refused\";\n        }\n\n        /// <summary>The returner's end",
         "            return local;\n        }\n\n        /// <summary>The returner's end")],
     "t16_end_reasons_server_set", "t16_join_pin_today"),
    ("MX9.5", "KX9A", "net", [
        ("Verifier = Field(body, \"verifier\")", "Verifier = Field(body, \"hand_over_verifier\")")],
     "tx9_verifier_k3", "t16_join_pin_today"),
    # KX9 Part B, the server's landed answers (MX9.6 to MX9.12 lane-added).
    ("MX9.6", "KX9B", "net", [
        ('BoolField(TopLevel(answer), "hold")', 'BoolField(answer, "hold")')],
     "t16_join_hold_top_level", "t16_join_pin_today"),
    ("MX9.7", "KX9B", "net", [
        ("                Roster = RosterIds(body),\n", "                Roster = null,\n")],
     "t39_claim_roster_pins", "t16_join_pin_today"),
    ("MX9.8", "KX9B", "net", [
        ('Slot = IntField(top, "slot", -1)', 'Slot = IntField(body, "slot", -1)')],
     "t39_claim_top_level_slot", "t16_join_pin_today"),
    ("MX9.9", "KX9B", "net", [
        ('return allAttached ? "?rdm=1" : "";', 'return "";')],
     "t39_rdm_poll_belt", "t16_join_pin_today"),
    ("MX9.10", "KX9B", "net", [
        ('Field(TopLevel(body), "status") != "readmissible"', 'Field(TopLevel(body), "status") != "readmissable"')],
     "t39_rdm_poll_belt", "t16_join_pin_today"),
    ("MX9.11", "KX9B", "rules", [
        ("string room = HoldRoomOfReport(reportRoom);", "string room = reportRoom;")],
     "t58_game_id_raw_room", "t16_join_pin_today"),
    ("MX9.12", "KX9B", "rules", [
        ("            return presentUids.Count;\n", "            return -1;\n")],
     "t36_attest_short_roster", "t16_join_pin_today"),
]

# The S0 inventory (V3 S0 step 2): every line under plugin/ that CALLS an
# application (not a patch attribute, a hook-table string or a comment) is in a
# file whose calls are FFA-only or spectator replays. Anything else names a new
# writer the seat log does not see.
CALL = re.compile(r'(\.OFFLINE_Pick\s*\(|\.RPCA_Pick\s*\(|RPC\(\s*"RPCA_Pick")')
ALLOWED_CALLERS = {"plugin/FfaMode.cs", "plugin/SpectatorSync.cs"}


def inventory(lines):
    bad = []
    for ln in lines:
        parts = ln.split(":", 2)
        if len(parts) < 3:
            continue
        path, code = parts[0], parts[2].strip()
        if code.startswith("//") or code.startswith("///") or code.startswith("*"):
            continue
        if CALL.search(code) and path not in ALLOWED_CALLERS:
            bad.append(ln)
    return bad


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build(work, tag, overrides):
    out = os.path.join(work, tag)
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep]
    for key, path in overrides.items():
        cmd.append("-p:" + PROPS[key] + "=" + path)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-4000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "Stage2Tests.dll")


def run_case(dll, case):
    r = subprocess.run(["dotnet", dll, case], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--piece", default=None)
    # The refit lane logs fixtures and mutants apart: fixtures runs every
    # fixture of the piece (and the K0 inventory), mutants every mutant.
    ap.add_argument("--part", choices=("all", "fixtures", "mutants"), default="all")
    a = ap.parse_args()
    work = os.path.abspath(a.work)
    os.makedirs(work, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    print("commit", head)
    print("tree", "clean" if not dirty else "DIRTY:\n" + dirty)
    print("piece", a.piece or "all")
    tracked = [f for f in FILES.values() if os.path.exists(os.path.join(PLUGIN, f))]
    before = {f: sha(os.path.join(PLUGIN, f)) for f in tracked}
    ok = True

    if a.piece in (None, "K0"):
        g = subprocess.run(["git", "-C", REPO, "grep", "-n", r"RPCA_Pick\|OFFLINE_Pick", "--", "plugin/"],
                           capture_output=True, text=True)
        lines = [ln for ln in g.stdout.splitlines() if ln.strip()]
        bad = inventory(lines)
        print("inventory: %d lines name RPCA_Pick or OFFLINE_Pick; %d unexpected application call(s)" % (len(lines), len(bad)))
        for ln in bad:
            print("  UNEXPECTED", ln)
        planted = lines + ["plugin/Plugin.cs:1:                acs.OFFLINE_Pick(new[] { player });"]
        control = inventory(planted)
        control_ok = len(control) == len(bad) + 1
        print("inventory negative control (one planted call in plugin/Plugin.cs): %s" % ("CAUGHT" if control_ok else "MISSED"))
        ok = ok and len(lines) > 0 and not bad and control_ok

    dll = build(work, "base", {})
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    listed = subprocess.run(["dotnet", dll, "--list"], capture_output=True, text=True).stdout.split()
    prefixes = PIECES[a.piece] if a.piece else tuple(p for v in PIECES.values() for p in v)
    cases = [c for c in listed if c.startswith(prefixes)]
    passed = 0
    for case in (cases if a.part != "mutants" else []):
        rc, out = run_case(dll, case)
        print(out)
        passed += rc == 0
        ok = ok and rc == 0
    if a.part != "mutants":
        print("fixtures: %d of %d pass" % (passed, len(cases)))
        ok = ok and len(cases) > 0

    mutants = [m for m in MUTANTS if (a.piece is None or m[1] == a.piece) and a.part != "fixtures"]
    caught = 0
    for name, piece, key, edits, target, control in mutants:
        src = os.path.join(PLUGIN, FILES[key])
        raw = open(src, "rb").read().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw
        good = True
        for old, new in edits:
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            count = text.count(o)
            if count != 1:
                print("BAD mutant %s: anchor occurs %d times" % (name, count))
                good = False
                break
            text = text.replace(o, n)
        if not good:
            ok = False
            continue
        path = os.path.join(work, "mut_" + name.replace(".", "_") + "_" + FILES[key])
        open(path, "wb").write(text.encode("utf-8"))
        mdll = build(work, "mut_" + name.replace(".", "_"), {key: path})
        if mdll is None:
            print("BAD mutant %s: does not build" % name)
            ok = False
            continue
        if target not in listed or control not in listed:
            print("BAD mutant %s: fixture missing" % name)
            ok = False
            continue
        trc, tout = run_case(mdll, target)
        crc, _ = run_case(mdll, control)
        hit = trc != 0 and crc == 0
        caught += hit
        ok = ok and hit
        print("%s mutant %s (%s): target %s=%s; control %s=%s%s" % (
            "CAUGHT" if hit else "MISSED", name, piece, target, "FAIL" if trc else "PASS", control,
            "PASS" if crc == 0 else "FAIL", "" if hit else " (" + tout[-200:] + ")"))
    print("mutants: %d of %d caught" % (caught, len(mutants)))

    unchanged = all(sha(os.path.join(PLUGIN, f)) == before[f] for f in tracked)
    print("tracked plugin files unchanged:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
