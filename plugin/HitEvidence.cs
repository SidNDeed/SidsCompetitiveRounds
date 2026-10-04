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

        // Hook-owned maps (seat evidence fix pass 4, F4): each is a CappedMap,
        // created at its cap, so no insert resizes it; a new key at the cap is
        // refused and counted (Drain logs the counts on the tick); every reset
        // or hand-over is bounded by the cap. No room holds this many remote
        // actors.
        private const int ACTOR_KEY_CAP = 16;
        private static SeatEvidenceCore.CappedMap<int, HitEvidenceCore.PointTally> _point = new SeatEvidenceCore.CappedMap<int, HitEvidenceCore.PointTally>(ACTOR_KEY_CAP);
        private static SeatEvidenceCore.CappedMap<int, HitEvidenceCore.GameTally> _game = new SeatEvidenceCore.CappedMap<int, HitEvidenceCore.GameTally>(ACTOR_KEY_CAP);
        private static readonly SeatEvidenceCore.CappedMap<int, bool> _projAmmo = new SeatEvidenceCore.CappedMap<int, bool>(HitEvidenceCore.PROJ_CAP);
        private static int _refusedPoint, _refusedGame;   // refusals of maps handed over or dropped, until Drain logs them
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
            if (_point.TryGetValue(actor, out t)) return t;
            if (!_point.Admit(actor)) return null;
            t = new HitEvidenceCore.PointTally();
            _point.Set(actor, t);
            return t;
        }

        private static HitEvidenceCore.GameTally G(int actor)
        {
            HitEvidenceCore.GameTally t;
            if (_game.TryGetValue(actor, out t)) return t;
            if (!_game.Admit(actor)) return null;
            t = new HitEvidenceCore.GameTally();
            _game.Set(actor, t);
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
                var p = P(actor);
                if (p != null) p.AddDirect(Time.realtimeSinceStartup, damage.magnitude, converted);
                var g = G(actor);
                if (g == null) return;
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
                var p = P(actor);
                if (p != null) p.AddForce(Time.realtimeSinceStartup, force.magnitude, inert);
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
                var p = P(actor);
                if (p != null) p.AddDot(damage.magnitude);
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
                if (g != null) { if (kind == 0) g.SpawnAmmo++; else if (kind == 1) g.SpawnNoAmmo++; else g.SpawnSeparate++; }
                var pv = init.GetComponent<PhotonView>();
                if (pv == null) return;
                _projAmmo.Set(pv.ViewID, kind == 0);
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
                var g = G(actor);
                if (g != null) g.AddImpact(projectile, wasBlocked, ammo);
            }
            catch { }
        }

        // -- flushes: captured while the game waits, logged on the tick (F4) -----

        // The point-end and game-end hooks run inside the game's own methods
        // (the point-decided RPC, StartGame). They only HAND OVER the tallies:
        // the filled dictionary moves into a preallocated slot and a spare one
        // takes its place, a fixed number of operations per remote actor and no
        // allocation once the spares exist (at most FLUSH_CAP + 1 of each kind,
        // ever). The pairing, the lines and the push into seat evidence run in
        // Drain, from Plugin's tick.
        private const int FLUSH_CAP = 16;
        private static readonly int[] _fNum = new int[FLUSH_CAP];
        private static readonly SeatEvidenceCore.CappedMap<int, HitEvidenceCore.PointTally>[] _fPoint = new SeatEvidenceCore.CappedMap<int, HitEvidenceCore.PointTally>[FLUSH_CAP];
        private static readonly SeatEvidenceCore.CappedMap<int, HitEvidenceCore.GameTally>[] _fGame = new SeatEvidenceCore.CappedMap<int, HitEvidenceCore.GameTally>[FLUSH_CAP];
        private static int _fCount, _fDropped;
        private static readonly Stack<SeatEvidenceCore.CappedMap<int, HitEvidenceCore.PointTally>> _spareP = new Stack<SeatEvidenceCore.CappedMap<int, HitEvidenceCore.PointTally>>(FLUSH_CAP + 1);
        private static readonly Stack<SeatEvidenceCore.CappedMap<int, HitEvidenceCore.GameTally>> _spareG = new Stack<SeatEvidenceCore.CappedMap<int, HitEvidenceCore.GameTally>>(FLUSH_CAP + 1);

        // Hook-path scans are hard-capped (seat evidence fix pass 2, F4): one
        // tally per actor, and no room holds this many.
        private const int ACTOR_SCAN_CAP = 64;

        private static bool AnyPoint()
        {
            var e = _point.GetEnumerator();
            for (int n = 0; n < ACTOR_SCAN_CAP && e.MoveNext(); n++) if (e.Current.Value.Any) return true;
            return false;
        }

        private static bool AnyGame()
        {
            var e = _game.GetEnumerator();
            for (int n = 0; n < ACTOR_SCAN_CAP && e.MoveNext(); n++) if (e.Current.Value.Any) return true;
            return false;
        }

        /// <summary>Moves this point's tallies into a slot (or counts a drop
        /// when every slot is waiting).</summary>
        private static void HoldPoint(int point)
        {
            if (_fCount >= FLUSH_CAP) { _fDropped++; _refusedPoint += _point.TakeRefused(); _point.Clear(); return; }
            _fNum[_fCount] = point; _fPoint[_fCount] = _point; _fGame[_fCount] = null; _fCount++;
            _point = _spareP.Count > 0 ? _spareP.Pop() : new SeatEvidenceCore.CappedMap<int, HitEvidenceCore.PointTally>(ACTOR_KEY_CAP);
        }

        private static void HoldGame(int game)
        {
            if (_fCount >= FLUSH_CAP) { _fDropped++; _refusedGame += _game.TakeRefused(); _game.Clear(); return; }
            _fNum[_fCount] = game; _fPoint[_fCount] = null; _fGame[_fCount] = _game; _fCount++;
            _game = _spareG.Count > 0 ? _spareG.Pop() : new SeatEvidenceCore.CappedMap<int, HitEvidenceCore.GameTally>(ACTOR_KEY_CAP);
        }

        /// <summary>From PointEvidence.PointEnd, with its point number:
        /// captures only.</summary>
        internal static void PointEnd(int point)
        {
            try
            {
                if (AnyPoint()) HoldPoint(point);
                else { _refusedPoint += _point.TakeRefused(); _point.Clear(); }
            }
            catch { }
            _blockedThisPoint = false;
        }

        /// <summary>At game over, at the next game's start and at room exit
        /// (whichever comes first carries the lines; the others find nothing).
        /// Captures only.</summary>
        internal static void GameEnd(int point)
        {
            try
            {
                if (AnyPoint()) HoldPoint(point);
                if (AnyGame()) { _games++; HoldGame(_games); }
            }
            catch { }
            _refusedPoint += _point.TakeRefused(); _refusedGame += _game.TakeRefused();
            _point.Clear(); _game.Clear(); _projAmmo.Clear(); _blockedThisPoint = false;
        }

        /// <summary>From Plugin's tick (through PointEvidence.Drain) and from
        /// the room-exit reset, outside any game method: the lines and seat
        /// evidence's push counts for every captured flush, in capture order.</summary>
        internal static void Drain()
        {
            int n = _fCount;
            for (int i = 0; i < n; i++)
            {
                var p = _fPoint[i];
                var g = _fGame[i];
                int num = _fNum[i];
                _fPoint[i] = null; _fGame[i] = null;
                try
                {
                    if (p != null)
                    {
                        foreach (var kv in p)
                            if (kv.Value.Any) Plugin.Log.LogInfo(HitEvidenceCore.HitRecvLine(num, kv.Key, kv.Value));
                        PushToSeatEvidence(p);
                    }
                    if (g != null)
                        foreach (var kv in g)
                        {
                            if (!kv.Value.Any) continue;
                            Plugin.Log.LogInfo(HitEvidenceCore.ShotObsLine(num, kv.Key, kv.Value));
                            Plugin.Log.LogInfo(HitEvidenceCore.BlockMissLine(num, kv.Key, kv.Value));
                        }
                }
                catch { }
                // a spare goes back only while the pool is below its bound (FLUSH_CAP + 1 of each kind)
                if (p != null) { _refusedPoint += p.TakeRefused(); p.Clear(); if (_spareP.Count <= FLUSH_CAP) _spareP.Push(p); }
                if (g != null) { _refusedGame += g.TakeRefused(); g.Clear(); if (_spareG.Count <= FLUSH_CAP) _spareG.Push(g); }
            }
            _fCount = 0;
            if (_fDropped > 0)
            {
                int d = _fDropped; _fDropped = 0;
                try { Plugin.Log.LogWarning("[HIT-EVIDENCE] " + d + " flushes not logged: every slot was waiting"); } catch { }
            }
            int a = _refusedPoint + _point.TakeRefused(), b = _refusedGame + _game.TakeRefused(), c = _projAmmo.TakeRefused();
            _refusedPoint = 0; _refusedGame = 0;
            if (a > 0 || b > 0 || c > 0)
            {
                try
                {
                    Plugin.Log.LogWarning("[HIT-EVIDENCE] keys refused at the caps: " + a + " point tally actor(s), " + b
                        + " game tally actor(s) (cap " + ACTOR_KEY_CAP + "), " + c + " projectile(s) (cap " + HitEvidenceCore.PROJ_CAP + ")");
                }
                catch { }
            }
        }

        /// <summary>Seat evidence's push counts: one point's pairing of the
        /// damage and knockback messages, per sending actor.</summary>
        private static void PushToSeatEvidence(SeatEvidenceCore.CappedMap<int, HitEvidenceCore.PointTally> point)
        {
            foreach (var kv in point)
            {
                var t = kv.Value;
                if (!t.Any) continue;
                int paired, dmgAlone, forceAlone;
                HitEvidenceCore.Pair(t.DirectT, t.ForceT, HitEvidenceCore.PAIR_WINDOW_S, out paired, out dmgAlone, out forceAlone);
                try { SeatEvidence.AddPush(kv.Key, t.Direct, t.Force, paired, dmgAlone, forceAlone, t.ForceInert, t.Dot); } catch { }
            }
        }

        /// <summary>Room exit, from PoisonSync's tick: the game's last capture,
        /// its lines and push counts (while the seat evidence window is still
        /// open), then the window freezes.</summary>
        internal static void ResetForRoomExit(int point)
        {
            GameEnd(point);
            try { Drain(); } catch { }
            _games = 0;
            RpcSender = 0;
            try { SeatEvidence.RoomExit(); } catch { }
            try { CardDrawEvidence.RoomExit(); } catch { }
            try { CombatEvidence.RoomExit(); } catch { }
        }
    }

    /// <summary>The sender of every RPC this seat executes. The prefix only
    /// records it and the finalizer restores the previous value (RPCs can nest)
    /// and returns the exception it was given; neither changes the call.
    /// Seat evidence: the prefix also copies the envelope's view, stamp and
    /// method into a nesting-safe frame (one long __state carries both the
    /// previous sender and the frame depth to restore).</summary>
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
        private static void Prefix(ExitGames.Client.Photon.Hashtable __0, Photon.Realtime.Player __1, out long __state)
        {
            int prev = HitEvidence.RpcSender;
            int depth = -1;
            try { depth = SeatEvidence.EnterRpc(__0, __1); } catch { }
            __state = (long)(uint)prev | ((long)depth << 32);
            try { HitEvidence.RpcSender = __1 != null ? __1.ActorNumber : 0; } catch { HitEvidence.RpcSender = 0; }
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(long __state, Exception __exception)
        {
            HitEvidence.RpcSender = (int)(uint)(__state & 0xFFFFFFFFL);
            try { SeatEvidence.ExitRpc((int)(__state >> 32)); } catch { }
            return __exception;
        }
    }

    /// <summary>D1/D3: a damage message arrived (counted even if the body
    /// throws or a prefix elsewhere skips it: it ARRIVED).</summary>
    [HarmonyPatch(typeof(HealthHandler), "RPCA_SendTakeDamage")]
    internal static class HitEvidence_DamagePatch
    {
        /// <summary>Seat evidence: whether this envelope's nonzero damage
        /// passes the game's predicate here, read before the body applies it.</summary>
        [HarmonyPrefix]
        private static void Prefix(HealthHandler __instance, Vector2 damage, out bool __state)
        {
            __state = false;
            try { __state = SeatEvidence.DamageGate(__instance, damage != Vector2.zero); } catch { }
        }

        /// <summary>dmg is marked only when the method completed without an
        /// exception of its own (`__exception == null`).</summary>
        [HarmonyFinalizer]
        private static Exception Finalizer(HealthHandler __instance, Vector2 damage, bool __state, Exception __exception)
        {
            try { HitEvidence.NoteDamage(__instance, damage); } catch { }
            try { SeatEvidence.DamageArrived(__instance, __state, __exception == null); } catch { }
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
            try { HitEvidence.NoteForce(__instance, force); } catch { }
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
            try { HitEvidence.NoteDot(__instance, damage, damagingPlayer, healthRemoval); } catch { }
            return __exception;
        }
    }

    /// <summary>D3: the local player's block began this point. Seat evidence:
    /// the prefix classifies the window (the RPC that carried it, an Echo
    /// under its root, or unkeyed) and the finalizer reads whether the copy's
    /// sinceBlock reset ran in the synchronous part.</summary>
    [HarmonyPatch(typeof(Block), "RPCA_DoBlock")]
    internal static class HitEvidence_BlockPatch
    {
        [HarmonyPrefix]
        private static void Prefix(Block __instance, bool __0, BlockTrigger.BlockTriggerType __2, bool __4, out int __state)
        {
            __state = -1;
            try { __state = SeatEvidence.BlockEnter(__instance, __0, __2, __4); } catch { }
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(Block __instance, int __state, Exception __exception)
        {
            try { HitEvidence.NoteBlock(__instance); } catch { }
            try { SeatEvidence.BlockExit(__state); } catch { }
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
            try { HitEvidence.NoteSpawn(__instance, 0); } catch { }
            try { SeatEvidence.ShotArrived(__instance, 0); } catch { }
            return __exception;
        }
    }

    [HarmonyPatch(typeof(ProjectileInit), "RPCA_Init_noAmmoUse")]
    internal static class HitEvidence_SpawnNoAmmoPatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(ProjectileInit __instance, Exception __exception)
        {
            try { HitEvidence.NoteSpawn(__instance, 1); } catch { }
            try { SeatEvidence.ShotArrived(__instance, 1); } catch { }
            return __exception;
        }
    }

    [HarmonyPatch(typeof(ProjectileInit), "RPCA_Init_SeparateGun")]
    internal static class HitEvidence_SpawnSeparatePatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(ProjectileInit __instance, Exception __exception)
        {
            try { HitEvidence.NoteSpawn(__instance, 2); } catch { }
            try { SeatEvidence.ShotArrived(__instance, 2); } catch { }
            return __exception;
        }
    }

    /// <summary>D2: a remote projectile's impact arrived. The projectile's id is
    /// read before the body (a killing or destroying impact can tear the view
    /// down inside it); the prefix only records it. Seat evidence: the prefix
    /// also reads the hit copy's sinceBlock before the body can reset it and
    /// opens a frame for a direct (path 1) decision; one long __state carries
    /// the projectile id and that frame.</summary>
    [HarmonyPatch(typeof(ProjectileHit), "RPCA_DoHit")]
    internal static class HitEvidence_ImpactPatch
    {
        [HarmonyPrefix]
        private static void Prefix(ProjectileHit __instance, int __3, bool __5, out long __state)
        {
            int pid = 0, frame = -1;
            try { pid = HitEvidence.ProjectileId(__instance); } catch { }
            try { frame = SeatEvidence.HitEnter(__instance, pid, __3, __5); } catch { }
            __state = (long)(uint)pid | ((long)frame << 32);
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(long __state, int viewID, bool wasBlocked, Exception __exception)
        {
            try { HitEvidence.NoteImpact((int)(uint)(__state & 0xFFFFFFFFL), viewID, wasBlocked); } catch { }
            try { SeatEvidence.HitExit((int)(__state >> 32)); } catch { }
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
            try { HitEvidence.GameEnd(PointEvidence.Point); } catch { }
            return __exception;
        }
    }
}
