using System;
using System.Collections.Generic;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Same Cards in the vanilla-pick modes — ranked/casual 1v1, 2v2 and 1v2
    /// (room rules design §6). The FFA engine (FfaCardSequence) is reused
    /// unchanged: one global sequence S1,S2,…; a player's k-th DEAL offers Sk
    /// whenever it happens. Only three things are mode-specific, and they
    /// live here:
    ///
    ///   1. WHEN the per-game seed is published and the capability advertised:
    ///      GM_ArmsRace.DoStartGame, which runs on EVERY client for EVERY game
    ///      including same-room rematches (IDoRematch calls it directly, #138),
    ///      so every seat's game counter agrees.
    ///   2. WHEN the local picker's draw index advances: once per DEAL, in the
    ///      CardChoice.ReplaceCards call that still has picks &gt; 0 (vanilla's
    ///      own "deal again" predicate; picks == 0 is the RPCA_DonePicking
    ///      call). ReplaceCards only ever runs on the client that OWNS the
    ///      picker — Pick and IDoEndPick both gate it on data.view.IsMine — so
    ///      no seat computes another player's hand.
    ///   3. WHICH prefab each of vanilla's five slots spawns:
    ///      CardChoice.SpawnUniqueCard. The prefix spawns the engine's
    ///      candidate through vanilla's own Spawn (PhotonNetwork.Instantiate by
    ///      prefab path), so every other client sees an ordinary spawn, the
    ///      caller's spawnedCards.Add / PublicInt bookkeeping is untouched and
    ///      the #309 slot invariant holds — nothing here compacts, reorders or
    ///      reads spawnedCards.
    ///
    /// Picks travel by PhotonView id (RPCA_DoEndPick), so a seat on private
    /// rolls cannot desync anyone: a mixed room degrades to today's behaviour
    /// exactly as FFA does, with one log line per game. The census, the seed,
    /// the pool hash and the 8 s pending budget are the engine's (§7e).
    /// Unlike the FFA pick coroutine, a prefix cannot wait for the latch, so
    /// the latch is retried at every deal until it verdicts; a deal that
    /// starts while it is still pending is a private deal for that player,
    /// and the index still advances (consume-on-deal, FFA §4c.3) so their
    /// later deals stay on Sk.
    /// </summary>
    internal static class VanillaCardSequence
    {
        /// <summary>Vanilla's deal: the five card slots under CardChoice
        /// (children.Length; the self-test checks the live count).</summary>
        public const int DealSize = 5;
        /// <summary>The game-start pick phase: one deal per player, identical
        /// for everyone with no per-player substitution (FFA §1c). The 1v2
        /// solo extra pick is deal 2 and is a normal draw.</summary>
        public const int OpeningDraws = 1;

        private static int _game;
        private static List<CardInfo> _deal;
        private static int _dealPos;
        private static int _dealGame = -1;
        private static int _sharedDeals, _privateDeals, _sharedSlots, _vanillaSlots;
        private static bool _verdictLogged;

        public static int Game => _game;

        /// <summary>A fighter seat in an online, non-FFA room. FFA runs the
        /// engine from its own lifecycle; a spectator never deals; an offline
        /// room has no rules record.</summary>
        private static bool InVanillaRoom()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return false;
                if (FfaMode.EngineActive()) return false;
                if (RoomActors.LocalIsSpectator) return false;
                return true;
            }
            catch { return false; }
        }

        /// <summary>DoStartGame, every client, every game: counts the game,
        /// resets the engine and — when the room plays Same Cards — publishes
        /// the in-room capability advert (every seat) and the seed (master).
        /// The counter runs whatever the rule, so a room's games number the
        /// same on every seat.</summary>
        public static void OnGameStart()
        {
            if (!InVanillaRoom()) return;
            LogCounters("previous game");
            _game++;
            _deal = null; _dealPos = 0; _dealGame = -1;
            _sharedDeals = _privateDeals = _sharedSlots = _vanillaSlots = 0;
            _verdictLogged = false;
            FfaCardSequence.OnGameStart();
            if (!RoomRules.SameCards) return;
            FfaCardSequence.PublishCapabilityWithHash();
            FfaCardSequence.MasterPublishSeed(_game);
            Plugin.Log.LogInfo($"[SC] game {_game}: same cards ON — capability advertised"
                               + (PhotonNetwork.IsMasterClient ? ", seed published" : ""));
        }

        /// <summary>DoPick, every client, every picker. The pick phase follows
        /// vanilla's sync-up, so every seat's game-start advert and the
        /// master's seed have propagated (Photon keeps one sender's property
        /// writes and RPCs in order). Re-asserts the seed — a master handoff
        /// republishes the identical derived value — and latches.</summary>
        public static void OnPickPhase()
        {
            if (!InVanillaRoom() || !RoomRules.SameCards) return;
            FfaCardSequence.MasterPublishSeed(_game);
            FfaCardSequence.LatchForGame(_game);
            LogVerdictOnce();
        }

        /// <summary>ReplaceCards on the owning client: one DEAL when picks &gt; 0.
        /// Consumes the local picker's draw index whatever the verdict, then
        /// computes this deal's shared candidates for SpawnUniqueCard to serve
        /// slot by slot.</summary>
        public static void OnDeal(CardChoice choice)
        {
            _deal = null; _dealPos = 0;
            if (choice == null || !InVanillaRoom() || !RoomRules.SameCards) return;
            if (choice.picks <= 0) return;
            var picker = ResolvePicker(choice);
            if (picker == null || picker.data == null || picker.data.view == null || !picker.data.view.IsMine) return;
            FfaCardSequence.MasterPublishSeed(_game);
            FfaCardSequence.LatchForGame(_game);   // retries a pending latch; a no-op once verdicted
            LogVerdictOnce();
            FfaCardSequence.ConsumeOffers(new List<int> { picker.PlayerID });
            var cands = new List<CardInfo>();
            bool shared = false;
            try { shared = FfaCardSequence.TryGetCandidates(picker, DealSize, cands); }
            catch (Exception ex) { Plugin.Log.LogWarning("[SC] shared draw failed: " + ex.Message); cands.Clear(); }
            if (shared && cands.Count > 0)
            {
                _deal = cands; _dealPos = 0; _dealGame = _game; _sharedDeals++;
                Plugin.Log.LogInfo($"[SC] game {_game}: deal for player {picker.PlayerID} — {cands.Count} shared candidate(s)"
                                   + (cands.Count < DealSize ? $" ({DealSize - cands.Count} slot(s) vanilla)" : ""));
            }
            else
            {
                _privateDeals++;
                if (_privateDeals == 1)
                {
                    string why = FfaCardSequence.ActiveThisGame ? "engine active, no candidates"
                        : FfaCardSequence.IsLatchedFor(_game) ? "engine fell back this game" : "latch still pending";
                    Plugin.Log.LogInfo($"[SC] game {_game}: private deal for player {picker.PlayerID} ({why})");
                }
            }
        }

        /// <summary>SpawnUniqueCard: serve the deal's next shared candidate
        /// through vanilla's Spawn. False = vanilla rolls this slot (no deal in
        /// progress, the deal's list exhausted, or the spawn failed — vanilla's
        /// uniqueness loop then sees our sourceCard stamps and avoids them).</summary>
        public static bool TrySpawnShared(CardChoice choice, Vector3 pos, Quaternion rot, out GameObject result)
        {
            result = null;
            if (choice == null || _deal == null || _dealGame != _game) return false;
            if (_dealPos >= _deal.Count) { _deal = null; _vanillaSlots++; return false; }
            var card = _deal[_dealPos++];
            if (card == null) { _vanillaSlots++; return false; }
            var obj = choice.Spawn(card.gameObject, pos, rot);
            if (obj == null) { _vanillaSlots++; return false; }
            // Vanilla's own two post-spawn lines (SpawnUniqueCard's tail): the
            // source stamp its uniqueness loop compares, and the pick collider.
            var info = obj.GetComponent<CardInfo>();
            if (info != null) info.sourceCard = card;
            var dmg = obj.GetComponentInChildren<DamagableEvent>();
            var col = dmg != null ? dmg.GetComponent<Collider2D>() : null;
            if (col != null) col.enabled = false;
            _sharedSlots++;
            result = obj;
            return true;
        }

        /// <summary>Left-room / disconnect edge. Idempotent; also resets the
        /// engine (FFA does the same from its own room-left).</summary>
        public static void OnRoomLeft()
        {
            LogCounters("room left");
            _game = 0;
            _deal = null; _dealPos = 0; _dealGame = -1;
            _sharedDeals = _privateDeals = _sharedSlots = _vanillaSlots = 0;
            _verdictLogged = false;
            try { FfaCardSequence.OnRoomLeft(); } catch { }
        }

        /// <summary>Vanilla's own picker resolution (SpawnUniqueCard's head),
        /// null-safe: a team picker is the team's first player; a player picker
        /// is looked up by id rather than indexed (#195: the players list is
        /// PlayerID-indexed by construction but padded with nulls mid-spawn,
        /// and vanilla clears pickrID to -1 between the deals of one sequence —
        /// the 1v2 extra-deal repair runs before this prefix).</summary>
        private static Player ResolvePicker(CardChoice choice)
        {
            try
            {
                var pm = PlayerManager.instance;
                if (pm == null || choice.pickrID < 0) return null;
                if (choice.pickerType == PickerType.Team)
                {
                    var team = pm.GetPlayersInTeam(choice.pickrID);
                    return team != null && team.Length > 0 ? team[0] : null;
                }
                return pm.GetPlayerWithID(choice.pickrID);
            }
            catch { return null; }
        }

        private static void LogVerdictOnce()
        {
            try
            {
                if (_verdictLogged || !FfaCardSequence.IsLatchedFor(_game)) return;
                _verdictLogged = true;
                Plugin.Log.LogInfo($"[SC] game {_game}: verdict — "
                                   + (FfaCardSequence.ActiveThisGame ? "shared sequence" : "private rolls (see the [FFA-SEQ] line)"));
            }
            catch { }
        }

        private static void LogCounters(string when)
        {
            if (_sharedDeals + _privateDeals == 0) return;
            Plugin.Log.LogInfo($"[SC] {when} (game {_game}): shared deals={_sharedDeals} private deals={_privateDeals}"
                               + $" shared slots={_sharedSlots} vanilla slots={_vanillaSlots}");
        }

        // ── self-test (menu, cfg-gated) ─────────────────────────────────────
        private static bool _selfTestDone;
        private static BepInEx.Configuration.ConfigEntry<bool> _selfTestLever;
        internal const int SELFTEST_CASES = 5;

        /// <summary>Once per process from Plugin's persistent tick, at the menu
        /// (never beside a live game). Binds [Debug] SameCardsSelfTest and,
        /// when it is true, checks the vanilla-mode seams against the live
        /// game — the card pool and its five slots, the patch targets, and a
        /// deterministic dry run of the engine at vanilla's deal size — logging
        /// one [SC-SELFTEST] line per case plus a summary. A FAIL is logged at
        /// Error so a level-filtered scan cannot read it as clean.</summary>
        internal static void EnsureSelfTest()
        {
            if (_selfTestDone) return;
            if (CardChoice.instance == null) return;   // re-arm until the pool object exists
            if (PhotonNetwork.InRoom) return;
            _selfTestDone = true;
            try
            {
                BepInEx.Configuration.ConfigFile cf = Plugin.ConfigFileForLevers;
                if (cf != null)
                    _selfTestLever = cf.Bind(
                        "Debug", "SameCardsSelfTest", false,
                        "Development only: once at startup, check the vanilla-mode Same Cards seams against the live game (card pool and slots, patch targets, a deterministic dry run) and log one [SC-SELFTEST] line per case plus a summary. Nothing is shown, sent or persisted.");
            }
            catch (Exception ex) { Plugin.Log?.LogWarning("[SC-SELFTEST] bind failed: " + ex.Message); }
            bool run = false;
            try { run = _selfTestLever != null && _selfTestLever.Value; } catch { }
            if (!run) return;
            try
            {
                int fail;
                int ran = SelfTest(s => Plugin.Log?.LogInfo(s), out fail);
                if (fail > 0 || ran != SELFTEST_CASES)
                    Plugin.Log?.LogError($"[SC-SELFTEST] FAILED: ran {ran}/{SELFTEST_CASES}, {fail} case(s) failed");
                else
                    Plugin.Log?.LogInfo($"[SC-SELFTEST] PASS: {ran}/{SELFTEST_CASES} cases");
            }
            catch (Exception ex)
            { Plugin.Log?.LogWarning("[SC-SELFTEST] failed to run: " + ex.GetType().Name + ": " + ex.Message); }
        }

        /// <summary>Returns the number of cases RUN and sets <paramref name="fail"/>;
        /// a run passes when run == SELFTEST_CASES and fail == 0. The last case
        /// is the negative control (#391): a different seed must change the
        /// dry run, so the determinism case cannot pass vacuously.</summary>
        internal static int SelfTest(Action<string> log, out int fail)
        {
            int failed = 0, ran = 0;
            void Case(string name, Func<bool> check, Func<string> detail)
            {
                ran++;
                bool ok = false;
                string d = "";
                try { ok = check(); d = detail != null ? (detail() ?? "") : ""; }
                catch (Exception ex) { ok = false; d = ex.GetType().Name + ": " + ex.Message; }
                if (!ok) failed++;
                log($"[SC-SELFTEST] {(ok ? "ok  " : "FAIL")} {name}" + (d.Length > 0 ? " — " + d : ""));
            }
            var cc = CardChoice.instance;
            Case("card pool present",
                 () => cc != null && cc.cards != null && cc.cards.Length > 0,
                 () => (cc != null && cc.cards != null ? cc.cards.Length : 0) + " cards");
            Case("five deal slots",
                 () => cc != null && cc.transform.childCount == DealSize,
                 () => "childCount=" + (cc != null ? cc.transform.childCount.ToString() : "-"));
            Case("patch targets resolve",
                 () => AccessTools.Method(typeof(CardChoice), "SpawnUniqueCard", new[] { typeof(Vector3), typeof(Quaternion) }) != null
                       && AccessTools.Method(typeof(CardChoice), "ReplaceCards") != null
                       && AccessTools.Method(typeof(CardChoice), "DoPick") != null
                       && AccessTools.Method(typeof(CardChoice), "Spawn", new[] { typeof(GameObject), typeof(Vector3), typeof(Quaternion) }) != null
                       && AccessTools.Method(typeof(GM_ArmsRace), "DoStartGame") != null,
                 null);
            string a = null, b = null, c = null;
            Case("dry run deterministic at the vanilla deal size",
                 () => { a = FfaCardSequence.DryRun(12345u, DealSize, 3); b = FfaCardSequence.DryRun(12345u, DealSize, 3); return a != null && a == b; },
                 () => a);
            Case("dry run seed-sensitive (negative control)",
                 () => { c = FfaCardSequence.DryRun(54321u, DealSize, 3); return c != null && a != null && c != a; },
                 () => c);
            fail = failed;
            return ran;
        }
    }

    /// <summary>Third prefix on DoStartGame (FfaMode.cs replaces the flow in
    /// FFA; SpectatorPatches.cs suppresses it on a spectator). Every sibling
    /// runs whatever the others return (#352), so this one carries its own FFA
    /// and spectator gates (InVanillaRoom) and depends on no ordering — the
    /// explicit priority only makes the order deterministic for log reading.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "DoStartGame")]
    [HarmonyPriority(Priority.Low)]
    static class GMArmsRace_DoStartGame_SameCards_Patch
    {
        static void Prefix()
        {
            try { VanillaCardSequence.OnGameStart(); }
            catch (Exception ex) { Plugin.Log.LogWarning("[SC] game start: " + ex.Message); }
        }
    }

    /// <summary>Every client, every picker: latch the game's verdict at the
    /// first pick phase (retried until it verdicts).</summary>
    [HarmonyPatch(typeof(CardChoice), "DoPick")]
    static class CardChoice_DoPick_SameCards_Patch
    {
        static void Prefix()
        {
            try { VanillaCardSequence.OnPickPhase(); }
            catch (Exception ex) { Plugin.Log.LogWarning("[SC] pick phase: " + ex.Message); }
        }
    }

    /// <summary>One deal. Runs after OvtExtraPickRestorePickerPatch (Plugin.cs,
    /// Normal) has repaired pickrID for the 1v2 extra deal and before
    /// CardChoiceStaleSpawnedCardsPatch (VanillaFixes.cs, Last) records the
    /// state the body receives. Neither sibling touches picks; this one
    /// touches neither pickrID nor spawnedCards.</summary>
    [HarmonyPatch(typeof(CardChoice), "ReplaceCards")]
    [HarmonyPriority(Priority.Low)]
    static class CardChoice_ReplaceCards_SameCards_Patch
    {
        static void Prefix(CardChoice __instance)
        {
            try { VanillaCardSequence.OnDeal(__instance); }
            catch (Exception ex) { Plugin.Log.LogWarning("[SC] deal: " + ex.Message); }
        }
    }

    /// <summary>One slot: the engine's candidate through vanilla's Spawn, or
    /// vanilla's own roll when there is nothing to serve.</summary>
    [HarmonyPatch(typeof(CardChoice), "SpawnUniqueCard")]
    static class CardChoice_SpawnUniqueCard_SameCards_Patch
    {
        static bool Prefix(CardChoice __instance, Vector3 pos, Quaternion rot, ref GameObject __result)
        {
            try
            {
                GameObject obj;
                if (VanillaCardSequence.TrySpawnShared(__instance, pos, rot, out obj))
                {
                    __result = obj;
                    return false;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[SC] spawn: " + ex.Message); }
            return true;
        }
    }
}
