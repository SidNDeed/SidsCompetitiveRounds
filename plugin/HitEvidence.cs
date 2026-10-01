using HarmonyLib;
using Photon.Pun;
using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Item D, EVIDENCE ONLY: what THIS seat received about the local
    /// player -- damage messages, knockback messages, damage-over-time ticks,
    /// the remote projectiles it saw spawn and hit, and where each direct hit
    /// fell relative to the local player's own block. Every hook only counts;
    /// nothing here changes damage, force, block or timing. The pure half
    /// (pairing, buckets, the lines) is HitEvidenceCore.
    ///
    /// Attribution is the SENDER of the message as Photon delivered it
    /// (PhotonNetwork.ExecuteRpc's sender, an actor number in the room), so a
    /// knockback message -- which carries no attacker id -- is attributed the
    /// same way as the damage message it should accompany. Messages this seat
    /// sent itself (RpcTarget.All runs locally too) are not counted.
    ///
    /// Lines (HitEvidenceCore builds them; bounded: one per remote actor per
    /// point for D1, two per remote actor per game for D2 and D3, and only
    /// when something was counted).</summary>
    internal static class HitEvidence
    {
        /// <summary>Actor number of the RPC being executed on this seat (0:
        /// none). Set and restored by HitEvidence_ExecuteRpcPatch.</summary>
        internal static int RpcSender;

        private static readonly Dictionary<int, HitEvidenceCore.PointTally> _point = new Dictionary<int, HitEvidenceCore.PointTally>();
        private static readonly Dictionary<int, HitEvidenceCore.GameTally> _game = new Dictionary<int, HitEvidenceCore.GameTally>();
        private static readonly Dictionary<int, bool> _projAmmo = new Dictionary<int, bool>();
        private static bool _blockedThisPoint;
        private static int _games;

        private static int LocalActor()
        {
            try { return PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : 0; }
            catch { return 0; }
        }

        /// <summary>The executing RPC came from another seat.</summary>
        private static bool RemoteSender(out int actor)
        {
            actor = RpcSender;
            return actor != 0 && actor != LocalActor();
        }

        private static bool LocalVictim(Component c, out CharacterData data)
        {
            data = null;
            if (c == null) return false;
            data = c.GetComponent<CharacterData>();
            return data != null && data.view != null && data.view.IsMine;
        }

        private static HitEvidenceCore.PointTally P(int actor)
        {
            HitEvidenceCore.PointTally t;
            if (!_point.TryGetValue(actor, out t)) { t = new HitEvidenceCore.PointTally(); _point[actor] = t; }
            return t;
        }

        private static HitEvidenceCore.GameTally G(int actor)
        {
            HitEvidenceCore.GameTally t;
            if (!_game.TryGetValue(actor, out t)) { t = new HitEvidenceCore.GameTally(); _game[actor] = t; }
            return t;
        }

        // -- D1 / D3: what arrived for the local player -------------------------

        internal static void NoteDamage(HealthHandler hh, Vector2 damage)
        {
            try
            {
                int actor;
                CharacterData data;
                if (damage == Vector2.zero || !RemoteSender(out actor) || !LocalVictim(hh, out data)) return;
                bool converted = data.stats != null && data.stats.secondsToTakeDamageOver != 0f;
                P(actor).AddDirect(Time.realtimeSinceStartup, damage.magnitude, converted);
                var g = G(actor);
                g.Direct++;
                float since = data.block != null ? data.block.sinceBlock : float.PositiveInfinity;
                g.Buckets[(int)HitEvidenceCore.Bucket(_blockedThisPoint, since)]++;
            }
            catch { }
        }

        internal static void NoteForce(HealthHandler hh, Vector2 force)
        {
            try
            {
                int actor;
                CharacterData data;
                if (!RemoteSender(out actor) || !LocalVictim(hh, out data)) return;
                bool inert = !data.isPlaying || data.playerVel == null || !data.playerVel.simulated;
                P(actor).AddForce(Time.realtimeSinceStartup, force.magnitude, inert);
            }
            catch { }
        }

        /// <summary>A damage-over-time tick (DoDamage with healthRemoval: vanilla
        /// DamageOverTime and the poison verdict apply both pass it; a direct
        /// hit's TakeDamage passes false), credited to the damaging player's
        /// actor.</summary>
        internal static void NoteDot(HealthHandler hh, Vector2 damage, Player damagingPlayer, bool healthRemoval)
        {
            try
            {
                CharacterData data;
                if (!healthRemoval || damage == Vector2.zero || damagingPlayer == null || !LocalVictim(hh, out data)) return;
                var dv = damagingPlayer.data != null ? damagingPlayer.data.view : null;
                int actor = dv != null ? dv.OwnerActorNr : 0;
                if (actor == 0 || actor == LocalActor()) return;
                P(actor).AddDot(damage.magnitude);
            }
            catch { }
        }

        internal static void NoteBlock(Block block)
        {
            try
            {
                CharacterData data;
                if (block != null && LocalVictim(block, out data) && block.sinceBlock < HitEvidenceCore.BLOCK_WINDOW_S)
                    _blockedThisPoint = true;
            }
            catch { }
        }

        // -- D2: remote projectiles seen spawning and hitting --------------------

        internal static void NoteSpawn(Component init, int kind)
        {
            try
            {
                int actor;
                if (init == null || !RemoteSender(out actor)) return;
                var g = G(actor);
                if (kind == 0) g.SpawnAmmo++; else if (kind == 1) g.SpawnNoAmmo++; else g.SpawnSeparate++;
                var pv = init.GetComponent<PhotonView>();
                if (pv != null && _projAmmo.Count < HitEvidenceCore.PROJ_CAP) _projAmmo[pv.ViewID] = kind == 0;
            }
            catch { }
        }

        internal static int ProjectileId(ProjectileHit ph)
        {
            try { var pv = ph != null ? ph.GetComponent<PhotonView>() : null; return pv != null ? pv.ViewID : 0; }
            catch { return 0; }
        }

        internal static void NoteImpact(int projectile, int viewID, bool wasBlocked)
        {
            try
            {
                int actor;
                if (projectile == 0 || viewID == -1 || !RemoteSender(out actor)) return;
                var target = PhotonNetwork.GetPhotonView(viewID);
                if (target == null || !target.IsMine || target.GetComponent<CharacterData>() == null) return;
                bool ammo;
                _projAmmo.TryGetValue(projectile, out ammo);
                G(actor).AddImpact(projectile, wasBlocked, ammo);
            }
            catch { }
        }

        // -- flushes -------------------------------------------------------------

        /// <summary>From PointEvidence.PointEnd, with its point number.</summary>
        internal static void PointEnd(int point)
        {
            try
            {
                foreach (var kv in _point)
                    if (kv.Value.Any) Plugin.Log.LogInfo(HitEvidenceCore.HitRecvLine(point, kv.Key, kv.Value));
            }
            catch { }
            _point.Clear();
            _blockedThisPoint = false;
        }

        /// <summary>At game over, at the next game's start and at room exit
        /// (whichever comes first carries the lines; the others find nothing).</summary>
        internal static void GameEnd(int point)
        {
            try
            {
                bool any = false;
                foreach (var kv in _point) any |= kv.Value.Any;
                if (any) PointEnd(point);
                any = false;
                foreach (var kv in _game) any |= kv.Value.Any;
                if (any)
                {
                    _games++;
                    foreach (var kv in _game)
                    {
                        if (!kv.Value.Any) continue;
                        Plugin.Log.LogInfo(HitEvidenceCore.ShotObsLine(_games, kv.Key, kv.Value));
                        Plugin.Log.LogInfo(HitEvidenceCore.BlockMissLine(_games, kv.Key, kv.Value));
                    }
                }
            }
            catch { }
            _point.Clear(); _game.Clear(); _projAmmo.Clear(); _blockedThisPoint = false;
        }

        internal static void ResetForRoomExit(int point)
        {
            GameEnd(point);
            _games = 0;
            RpcSender = 0;
        }
    }

    /// <summary>The sender of every RPC this seat executes. The prefix only
    /// records it and the finalizer restores the previous value (RPCs can nest)
    /// and returns the exception it was given; neither changes the call.</summary>
    [HarmonyPatch]
    internal static class HitEvidence_ExecuteRpcPatch
    {
        private static MethodBase TargetMethod()
        {
            var m = AccessTools.Method(typeof(PhotonNetwork), "ExecuteRpc",
                new[] { typeof(ExitGames.Client.Photon.Hashtable), typeof(Photon.Realtime.Player) });
            if (m == null) throw new Exception("PhotonNetwork.ExecuteRpc(Hashtable, Player) not found - hit evidence has no sender");
            return m;
        }

        [HarmonyPrefix]
        private static void Prefix(Photon.Realtime.Player __1, out int __state)
        {
            __state = HitEvidence.RpcSender;
            try { HitEvidence.RpcSender = __1 != null ? __1.ActorNumber : 0; } catch { HitEvidence.RpcSender = 0; }
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(int __state, Exception __exception)
        {
            HitEvidence.RpcSender = __state;
            return __exception;
        }
    }

    /// <summary>D1/D3: a damage message arrived (counted even if the body
    /// throws or a prefix elsewhere skips it: it ARRIVED).</summary>
    [HarmonyPatch(typeof(HealthHandler), "RPCA_SendTakeDamage")]
    internal static class HitEvidence_DamagePatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(HealthHandler __instance, Vector2 damage, Exception __exception)
        {
            HitEvidence.NoteDamage(__instance, damage);
            return __exception;
        }
    }

    /// <summary>D1: a knockback message arrived.</summary>
    [HarmonyPatch(typeof(HealthHandler), "RPCA_SendTakeForce")]
    internal static class HitEvidence_ForcePatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(HealthHandler __instance, Vector2 force, Exception __exception)
        {
            HitEvidence.NoteForce(__instance, force);
            return __exception;
        }
    }

    /// <summary>D1: damage-over-time ticks on the local player.</summary>
    [HarmonyPatch(typeof(HealthHandler), "DoDamage")]
    internal static class HitEvidence_DotPatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(HealthHandler __instance, Vector2 damage, Player damagingPlayer, bool healthRemoval, Exception __exception)
        {
            HitEvidence.NoteDot(__instance, damage, damagingPlayer, healthRemoval);
            return __exception;
        }
    }

    /// <summary>D3: the local player's block began this point.</summary>
    [HarmonyPatch(typeof(Block), "RPCA_DoBlock")]
    internal static class HitEvidence_BlockPatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(Block __instance, Exception __exception)
        {
            HitEvidence.NoteBlock(__instance);
            return __exception;
        }
    }

    /// <summary>D2: a remote projectile spawned on this seat (one per
    /// PhotonNetwork.Instantiate in Gun.FireBurst, three init variants).</summary>
    [HarmonyPatch(typeof(ProjectileInit), "RPCA_Init")]
    internal static class HitEvidence_SpawnAmmoPatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(ProjectileInit __instance, Exception __exception)
        {
            HitEvidence.NoteSpawn(__instance, 0);
            return __exception;
        }
    }

    [HarmonyPatch(typeof(ProjectileInit), "RPCA_Init_noAmmoUse")]
    internal static class HitEvidence_SpawnNoAmmoPatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(ProjectileInit __instance, Exception __exception)
        {
            HitEvidence.NoteSpawn(__instance, 1);
            return __exception;
        }
    }

    [HarmonyPatch(typeof(ProjectileInit), "RPCA_Init_SeparateGun")]
    internal static class HitEvidence_SpawnSeparatePatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(ProjectileInit __instance, Exception __exception)
        {
            HitEvidence.NoteSpawn(__instance, 2);
            return __exception;
        }
    }

    /// <summary>D2: a remote projectile's impact arrived. The projectile's id is
    /// read before the body (a killing or destroying impact can tear the view
    /// down inside it); the prefix only records it.</summary>
    [HarmonyPatch(typeof(ProjectileHit), "RPCA_DoHit")]
    internal static class HitEvidence_ImpactPatch
    {
        [HarmonyPrefix]
        private static void Prefix(ProjectileHit __instance, out int __state)
        {
            __state = HitEvidence.ProjectileId(__instance);
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(int __state, int viewID, bool wasBlocked, Exception __exception)
        {
            HitEvidence.NoteImpact(__state, viewID, wasBlocked);
            return __exception;
        }
    }

    /// <summary>D2/D3's per-game flush at the next game's start (a game that
    /// ended without a game-over broadcast, e.g. a disconnect).</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "StartGame")]
    internal static class HitEvidence_StartGamePatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(Exception __exception)
        {
            HitEvidence.GameEnd(PointEvidence.Point);
            return __exception;
        }
    }
}
