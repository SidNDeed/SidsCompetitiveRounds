using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Stage 2 glue: the Harmony seams and the per-frame upkeep that feed the
    /// pure rules of SeatDeckLog.cs and TeamHoldRules.cs. Every hook is
    /// wrapped so a throw here leaves vanilla running unchanged.
    ///
    /// S0 (no behaviour change): the RPCA_Pick intent, commit and fault seam;
    /// the RPCA_Die_Phoenix ledger claimer; the game-start reset; the point
    /// start drift probe. The RPCA_Die claimer sits inside
    /// CombatTelemetry.DeathClassifierPatch, after the vanilla guard, and the
    /// life advance inside VanillaFixes' SafeRespawn.
    /// </summary>
    internal static class TeamHoldGlue
    {
        internal const string SEATLOG = "[SEATLOG]";

        /// <summary>True when every Stage 2 patch attached at boot (#83). The
        /// capability token is sent only then (KX8).</summary>
        internal static bool AllAttached { get; private set; }

        /// <summary>The rooms S0 records in: online, a fighter or observer
        /// seat, not FFA (FFA keeps its own records). Log-only, so no mode
        /// latch is needed for it.</summary>
        internal static bool SeatLogRoom()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return false;
                if (FfaMode.EngineActive()) return false;
                return true;
            }
            catch { return false; }
        }

        /// <summary>The scoreboard tuple of the running game, the ledger key.</summary>
        internal static string CurrentTuple()
        {
            var gm = GM_ArmsRace.instance;
            if (gm == null) return "";
            return SeatDeckLog.Tuple(gm.p1Rounds, gm.p2Rounds, gm.p1Points, gm.p2Points);
        }

        internal static int SlotOfActor(int actorNr)
        {
            try
            {
                var pm = PlayerManager.instance;
                var p = pm != null ? pm.GetPlayerWithActorID(actorNr) : null;
                return p != null ? p.PlayerID : -1;
            }
            catch { return -1; }
        }

        /// <summary>The canonical name the log stores, from the card prefab
        /// (the same basis as CharacterData.currentCards, so the drift probe
        /// compares like with like).</summary>
        internal static string CardName(CardInfo card)
        {
            if (card == null) return null;
            var src = card.sourceCard != null ? card.sourceCard : card;
            string raw = src.gameObject != null ? src.gameObject.name : src.cardName;
            if (string.IsNullOrEmpty(raw)) return null;
            raw = raw.Replace("(Clone)", "").Trim();
            return CardRarityLookup.GetCanonicalName(raw);
        }

        /// <summary>RPCA_Die after the vanilla guard: the ledger claim. True
        /// means the caller records the observed death as today. Outside the
        /// S0 rooms nothing changes (always true).</summary>
        internal static bool ClaimDieAllowsRecord(HealthHandler hh)
        {
            try
            {
                if (!SeatLogRoom()) return true;
                var pl = hh != null && hh.data != null ? hh.data.player : null;
                if (pl == null) return true;
                return SeatDeckLog.ClaimDie(pl.PlayerID, CurrentTuple()) == SeatDeckLog.Claim.Won;
            }
            catch { return true; }
        }

        /// <summary>SafeRespawn revived the slot: its next death is a new key.</summary>
        internal static void OnPhoenixRevived(int playerId)
        {
            try { if (SeatLogRoom()) SeatDeckLog.AdvanceLife(playerId); } catch { }
        }

        private static bool _battleWas;

        /// <summary>Per frame from the plug-in host (BepInEx never calls
        /// Plugin.Update; the host behaviour polls).</summary>
        internal static void Tick()
        {
            bool battle = false;
            try { battle = GameManager.instance != null && GameManager.instance.battleOngoing; } catch { }
            if (battle && !_battleWas) OnPointStart();
            _battleWas = battle;
            try { TeamHold.Tick(); } catch { }
            try { TeamHoldLoop.Tick(); } catch { }
            try { TeamHoldReturn.Tick(); } catch { }
        }

        /// <summary>The drift probe: each present body's cards against its
        /// slot log, at every point start.</summary>
        private static void OnPointStart()
        {
            try
            {
                if (!SeatLogRoom()) return;
                // S3 step 7: the boundary just passed (the scoreboard and
                // every slot's deck), the held seat's checkpoint source.
                try { TeamHold.NoteBoundary(); } catch { }
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return;
                foreach (var p in pm.players)
                {
                    if (p == null || p.data == null || p.data.currentCards == null) continue;
                    var names = new List<string>();
                    foreach (var c in p.data.currentCards) names.Add(CardName(c) ?? "");
                    if (SeatDeckLog.DriftCheck(p.PlayerID, names))
                        Plugin.Log.LogWarning(SEATLOG + " drift slot=" + p.PlayerID.ToString(CultureInfo.InvariantCulture)
                            + " log=" + SeatDeckLog.Describe(p.PlayerID) + " body=" + names.Count.ToString(CultureInfo.InvariantCulture));
                }
            }
            catch { }
        }

        /// <summary>Room left: nothing of the room survives.</summary>
        internal static void OnRoomLeft()
        {
            try { SeatDeckLog.OnRoomLeft(); } catch { }
            try { TeamHold.OnRoomLeft(); } catch { }
            try { TeamHoldLoop.Reset(); } catch { }
            try { TeamHoldReturn.OnRoomLeft(); } catch { }
            _battleWas = false;
        }

        private static readonly string[][] HOOKS =
        {
            new[] { "S0", "ApplyCardStats", "RPCA_Pick", "TeamHold_PickSeamPatch" },
            new[] { "S0", "ApplyCardStats", "OFFLINE_Pick", "TeamHold_OfflinePickPatch" },
            new[] { "S0", "HealthHandler", "RPCA_Die_Phoenix", "TeamHold_PhoenixClaimPatch" },
            new[] { "S0", "HealthHandler", "RPCA_Die", "DeathClassifierPatch" },
            new[] { "S0", "GM_ArmsRace", "DoStartGame", "TeamHold_GameStartPatch" },
            new[] { "S1", "GM_ArmsRace", "GameOverTransition", "TeamHold_GameOverPatch" },
            new[] { "S1", "NetworkConnectionHandler", "OnPlayerLeftRoom", "NCH_OnPlayerLeftRoom_Hold_Patch" },
            new[] { "S2", "GM_ArmsRace", "PointTransition", "TeamHold_PointTransitionPatch" },
            new[] { "S2", "GM_ArmsRace", "RoundTransition", "TeamHold_RoundTransitionPatch" },
            new[] { "S2", "GM_ArmsRace", "DoStartGame", "TeamHold_RematchFencePatch" },
        };

        private static Type HookType(string name)
        {
            switch (name)
            {
                case "ApplyCardStats": return typeof(ApplyCardStats);
                case "HealthHandler": return typeof(HealthHandler);
                case "GM_ArmsRace": return typeof(GM_ArmsRace);
                case "NetworkConnectionHandler": return typeof(NetworkConnectionHandler);
                case "CardChoice": return typeof(CardChoice);
                default: return null;
            }
        }

        /// <summary>One boot line naming every Stage 2 patch as attached or
        /// not (#83); <see cref="AllAttached"/> is true only when all are.</summary>
        internal static void BootLine()
        {
            try
            {
                var all = new List<string[]>(HOOKS);
                var ok = new List<string>();
                var bad = new List<string>();
                foreach (var h in all)
                {
                    bool attached = false;
                    try
                    {
                        var t = HookType(h[1]);
                        var m = t != null ? AccessTools.Method(t, h[2]) : null;
                        var info = m != null ? Harmony.GetPatchInfo(m) : null;
                        if (info != null)
                            foreach (var p in info.Prefixes.Concat(info.Postfixes).Concat(info.Finalizers))
                                if (p.PatchMethod != null && p.PatchMethod.DeclaringType != null
                                    && p.PatchMethod.DeclaringType.Name == h[3]) attached = true;
                    }
                    catch { attached = false; }
                    (attached ? ok : bad).Add(h[0] + " " + h[1] + "." + h[2]);
                }
                AllAttached = bad.Count == 0;
                string line = "[HOLD] stage 2 patches attached " + ok.Count.ToString(CultureInfo.InvariantCulture)
                              + "/" + all.Count.ToString(CultureInfo.InvariantCulture);
                if (bad.Count == 0) Plugin.Log.LogInfo(line);
                else Plugin.Log.LogError(line + "; NOT attached: " + string.Join(", ", bad.ToArray()));
            }
            catch (Exception ex) { AllAttached = false; Plugin.Log.LogError("[HOLD] boot line failed: " + ex.Message); }
        }
    }

    /// <summary>S0 step 2: the one application seam. The intent prefix runs
    /// first and records the card and its target slots; the postfix commits
    /// only when the original ran; the finalizer drops the intent and marks
    /// the slots when the original threw, and returns the exception unchanged.</summary>
    [HarmonyPatch(typeof(ApplyCardStats), "RPCA_Pick")]
    internal static class TeamHold_PickSeamPatch
    {
        [HarmonyPrefix]
        [HarmonyPriority(Priority.First)]
        private static void Prefix(ApplyCardStats __instance, int[] __0)
        {
            try
            {
                if (!TeamHoldGlue.SeatLogRoom()) return;
                var info = __instance != null ? __instance.GetComponent<CardInfo>() : null;
                string name = TeamHoldGlue.CardName(info);
                var view = __instance != null ? __instance.GetComponent<PhotonView>() : null;
                int[] slots = new int[__0 != null ? __0.Length : 0];
                for (int i = 0; i < slots.Length; i++) slots[i] = TeamHoldGlue.SlotOfActor(__0[i]);
                SeatDeckLog.PickIntent(view != null ? view.ViewID : 0, name, slots);
            }
            catch { }
        }

        // The intent stack pairs the calls: the postfix completes the intent
        // when the original returned (Harmony skips postfixes when it threw);
        // the finalizer runs on every exit and pops, marking an intent no
        // postfix completed. The exception argument is deliberately not the
        // test: the dispatch guard of VanillaFixes may swallow it first. An
        // empty stack (a room S0 does not record in) makes both no-ops.
        [HarmonyPostfix]
        private static void Postfix(bool __runOriginal)
        {
            try { SeatDeckLog.PickCommit(__runOriginal); } catch { }
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(Exception __exception)
        {
            try { SeatDeckLog.PickEnd(); } catch { }
            return __exception;
        }
    }

    /// <summary>S0 step 2: OFFLINE_Pick is a local replay; counted, never written.</summary>
    [HarmonyPatch(typeof(ApplyCardStats), "OFFLINE_Pick")]
    internal static class TeamHold_OfflinePickPatch
    {
        [HarmonyPostfix]
        private static void Postfix(Player[] __0, bool __runOriginal)
        {
            try
            {
                if (!__runOriginal || __0 == null || !TeamHoldGlue.SeatLogRoom()) return;
                for (int i = 0; i < __0.Length; i++)
                    if (__0[i] != null) SeatDeckLog.ObserveOfflinePick(__0[i].PlayerID, null);
            }
            catch { }
        }
    }

    /// <summary>S0 step 3: the Phoenix claimer, beside the evidence prefix.
    /// Mirrors the vanilla guard (isPlaying and not dead) so a duplicate RPC
    /// that vanilla ignores claims nothing.</summary>
    [HarmonyPatch(typeof(HealthHandler), "RPCA_Die_Phoenix")]
    internal static class TeamHold_PhoenixClaimPatch
    {
        [HarmonyPrefix]
        private static void Prefix(HealthHandler __instance)
        {
            try
            {
                if (!TeamHoldGlue.SeatLogRoom()) return;
                var data = __instance != null ? __instance.data : null;
                if (data == null || data.player == null || !data.isPlaying || data.dead) return;
                SeatDeckLog.ClaimPhoenix(data.player.PlayerID, TeamHoldGlue.CurrentTuple());
            }
            catch { }
        }
    }

    /// <summary>S0 step 1: the log resets at every game start, on every
    /// client (DoStartGame runs for rematches too). The prefix only resets
    /// state; it never touches the call.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "DoStartGame")]
    internal static class TeamHold_GameStartPatch
    {
        [HarmonyPrefix]
        private static void Prefix()
        {
            try { if (TeamHoldGlue.SeatLogRoom()) SeatDeckLog.OnGameStart(); } catch { }
            // S1 step 3: the master of a flagged room posts the game start
            // and publishes cr_tgid = {G}:s. Inert in every unflagged room.
            try { TeamHoldWriter.OnGameStart(); } catch { }
        }
    }

    /// <summary>S1 step 3: the game-over edge publishes cr_tgid = {G}:g, so
    /// no hold opens between games. Inert in every unflagged room.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "GameOverTransition")]
    internal static class TeamHold_GameOverPatch
    {
        [HarmonyPrefix]
        private static void Prefix()
        {
            try { TeamHoldWriter.OnGameOver(); } catch { }
        }
    }

    /// <summary>S1 step 5: the vanilla teardown cascade of a held departure
    /// does not run. Low priority, so the spectator prefix
    /// (Spectator_LeaveIsInvisible_Patch) decides first; every prefix runs
    /// even after one returned false (#352), so a departure another prefix
    /// already suppressed stays suppressed and is not classified here. The
    /// classification is the memo the mod leave callback reads.</summary>
    [HarmonyPatch(typeof(NetworkConnectionHandler), "OnPlayerLeftRoom")]
    internal static class NCH_OnPlayerLeftRoom_Hold_Patch
    {
        [HarmonyPrefix]
        [HarmonyPriority(Priority.Low)]
        private static bool Prefix(Photon.Realtime.Player otherPlayer, bool __runOriginal)
        {
            if (!__runOriginal) return false;
            try { return !TeamHold.Classify(otherPlayer) && !TeamHold.HoldsAnother(otherPlayer); }
            catch { return true; }
        }
    }
}
