using System;
using System.Collections.Generic;
using ExitGames.Client.Photon;
using HarmonyLib;
using Photon.Pun;
using Photon.Realtime;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Dance emotes v1 (Sid, Aug 31: "make E an emote wheel...
    /// little dances not too dissimilar to fortnite"; design-reviewed by
    /// Codex the same day — GO-WITH-CHANGES, and this file implements the
    /// review's CUT list, not the full design: TWO routines, arm-target +
    /// wobble-translation channels only (no legs, no gun/aim motion, no
    /// particles, no audio), NO spectator rendering, hard cancellation at
    /// the combat edge).
    ///
    /// MECHANISM (rig-probe-proven, [RIG-DUMP] Aug 31): the visual body
    /// hangs off PlayerWobblePosition ("WobbleObjects"), which rewrites its
    /// transform ABSOLUTELY every Update from the physics spring — so an
    /// additive offset applied in a Postfix needs no persistence and
    /// self-heals the instant we stop. The arms are IKArmMove components on
    /// Limbs/ArmStuff/Arm_Left|Right whose `target` transforms
    /// (TargetLeftArm/TargetRightArm) are NOT absolutely rewritten — the
    /// review confirmed free-arm state feeds back — so the arm channel uses
    /// the RESTORE-FIRST contract: a Prefix undoes the remembered delta,
    /// vanilla runs, the Postfix applies (and remembers) the new delta.
    /// Nothing here touches physics, velocity, input, aim, or health
    /// (#338-family: an emote must be structurally unable to affect play).
    ///
    /// SYNC: Photon RaiseEvent code 49 (registry: 47 poison, 48 quick chat,
    /// 51/52 spectator), payload {byte proto, int actor, byte danceIdx,
    /// int serverTs}. QuickChat's hardening cloned and extended with the
    /// design review's 11-step receive order. Every PARTICIPANT seat
    /// renders the dance deterministically from
    /// (idx, PhotonNetwork.ServerTimestamp - ts) — no per-frame sync;
    /// spectator seats deliberately render nothing (WindowOpen). Late
    /// joiners miss ephemeral dances by design.
    ///
    /// OWNERSHIP (review Q6, accepted residual): the SEND path checks the
    /// local owned-items cache honestly; receivers render any VALID dance id
    /// without verifying the sender's ownership (server state about another
    /// player is unknowable client-side). A modified client can therefore
    /// display an unowned dance — display-tier only, cannot move results,
    /// ratings, gold, or another player's gameplay. The reviewer rejected a
    /// Photon-prop ownership bitmask as equally client-writable.</summary>
    internal static class DanceEmotes
    {
        private const byte EventCode = 49;
        private const byte Protocol = 1;

        internal struct DanceDef
        {
            public string Sku; public string Name; public float Duration;
            public DanceDef(string sku, string name, float dur) { Sku = sku; Name = name; Duration = dur; }
        }

        // Wire id = index. APPEND-ONLY (the QuickChat rule): a mixed-version
        // room must agree what id N dances. Unknown ids no-op on old clients.
        internal static readonly DanceDef[] Defs =
        {
            new DanceDef("dance_bounce", "The Bounce", 4.0f),
            new DanceDef("dance_wave",   "The Wave",   4.0f),
        };

        private const float MAX_OFFSET = 0.9f;          // hard clamp, world units
        private const float SEND_THROTTLE_S = 2.5f;
        private const float RECV_THROTTLE_S = 2.0f;

        // Active dance per room actor: actorNumber -> (danceIdx, startServerTs).
        // Bounded: one entry per actor; cleared on expiry, at the combat
        // edge (Tick), and on the reliable room-exit callback (OnRoomLeft).
        private static readonly Dictionary<int, (int idx, int ts)> active = new Dictionary<int, (int, int)>();
        // Arm restore-first bookkeeping: per-target remembered applied delta.
        private static readonly Dictionary<Transform, Vector3> armApplied = new Dictionary<Transform, Vector3>();

        private static bool _hooked;
        private static float _lastSendAt = -999f;
        private static readonly Dictionary<int, float> _lastRecvByActor = new Dictionary<int, float>();
        private static string _throttleRoom = "";
        private static bool _armChannelDead, _wobbleChannelDead;   // fail-closed per channel (#434 discipline)

        internal static void Hook()
        {
            if (_hooked) return;
            try
            {
                if (PhotonNetwork.NetworkingClient == null) return;
                PhotonNetwork.NetworkingClient.EventReceived += OnEvent;
                _hooked = true;
            }
            catch { }
        }

        /// <summary>The one shared window predicate: participant seat, no
        /// live battle, no card pick in progress. Evaluated independently at
        /// SEND, RECEIVE and EVERY FRAME (#352 — no patch may rely on another
        /// patch's gate).</summary>
        internal static bool WindowOpen()
        {
            try
            {
                if (RoomActors.LocalIsSpectator) return false;   // v1: observers never render dances
                var gm = GameManager.instance;
                // Combat gate is ONLINE-only: sandbox (GM_Test) keeps
                // battleOngoing TRUE for the whole session (probe-proven,
                // [DANCE] probe win=False battle=True — Sept 1), and offline
                // is the solo playground where owners try their dances; a
                // mid-"battle" dance there affects nobody.
                if (gm != null && gm.battleOngoing && !PhotonNetwork.OfflineMode) return false;
                try
                {
                    var cc = CardChoice.instance;
                    if (cc != null && cc.IsPicking) return false;   // pick-phase gate (review blocker 4)
                }
                catch { }
                return true;
            }
            catch { return false; }
        }

        /// <summary>Skus the local player owns, from the annotated shop cache
        /// (owned flag rides /shop/items). Null = cache absent (shop never
        /// fetched) — the wheel shows a hint and triggers a fetch.</summary>
        internal static List<int> OwnedDanceIndexes()
        {
            try
            {
                var items = ApiClient.CachedShopItems;
                if (items == null) return null;
                var owned = new List<int>();
                for (int i = 0; i < Defs.Length; i++)
                    foreach (var it in items)
                        if (it != null && it.owned && it.kind == "dance"
                            && string.Equals(it.sku, Defs[i].Sku, StringComparison.Ordinal))
                        { owned.Add(i); break; }
                return owned;
            }
            catch { return null; }
        }

        internal static bool Send(int danceIdx)
        {
            try
            {
                if (danceIdx < 0 || danceIdx >= Defs.Length) return false;
                if (BroadcastMode.FenceBlocksFighterPath("dance")) return false;
                if (RoomActors.LocalIsSpectator) return false;
                if (!WindowOpen()) return false;
                if (Time.unscaledTime - _lastSendAt < SEND_THROTTLE_S) return false;
                var owned = OwnedDanceIndexes();
                if (owned == null || !owned.Contains(danceIdx)) return false;
                // Offline/sandbox: no network — install locally so the owner
                // can still enjoy/preview it (review Q4: offline needs a local
                // install path; ServerTimestamp is a local monotonic there).
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode)
                {
                    _lastSendAt = Time.unscaledTime;
                    int a = -1;
                    try { a = PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : -1; } catch { }
                    active[a] = (danceIdx, PhotonNetwork.ServerTimestamp);
                    return true;
                }
                _lastSendAt = Time.unscaledTime;
                object[] payload = { Protocol, PhotonNetwork.LocalPlayer.ActorNumber, (byte)danceIdx, PhotonNetwork.ServerTimestamp };
                // ReceiverGroup.All: the sender installs from its own echo,
                // down the same validated path as everyone (#280d). A false
                // return is logged once and never retried, and installs
                // NOTHING locally (#280c — no optimistic state).
                bool ok = PhotonNetwork.RaiseEvent(EventCode, payload,
                    new RaiseEventOptions { Receivers = ReceiverGroup.All },
                    new SendOptions { Reliability = true });
                if (!ok) Plugin.Log?.LogWarning("[DANCE] RaiseEvent returned false — dance not sent");
                return ok;
            }
            catch { return false; }
        }

        /// <summary>Receive: the design review's exact validation order.</summary>
        private static void OnEvent(EventData e)
        {
            try
            {
                if (e == null || e.Code != EventCode) return;                        // 1 filter
                var arr = e.CustomData as object[];
                if (arr == null || arr.Length != 4) return;                          // 2 shape
                if (!(arr[0] is byte) || !(arr[1] is int) || !(arr[2] is byte) || !(arr[3] is int)) return;  // 3 types
                if ((byte)arr[0] != Protocol) return;                                // 4 proto
                int claimed = (int)arr[1];
                if (claimed <= 0 || claimed != e.Sender) return;                     // 5 anti-spoof
                int idx = (byte)arr[2];
                if (idx < 0 || idx >= Defs.Length) return;                           // 6 known id
                int ts = (int)arr[3];
                int age = unchecked(PhotonNetwork.ServerTimestamp - ts);             // 7 wrap-safe age
                if (age < -1500 || age > (int)(Defs[idx].Duration * 1000f) + 1500) return;
                try                                                                  // 8 live actor, not a spectator
                {
                    var room = PhotonNetwork.CurrentRoom;
                    var ph = room != null ? room.GetPlayer(e.Sender) : null;
                    if (ph == null) return;
                    if (ph.CustomProperties != null && ph.CustomProperties.ContainsKey("cr_spec")) return;
                    // Body is resolved lazily per frame (TryGetPose) — never cached here (review Q3).
                }
                catch { return; }
                if (!WindowOpen()) return;                                           // 9 this seat's phase
                string room2 = "";
                try { room2 = PhotonNetwork.CurrentRoom?.Name ?? ""; } catch { }
                if (room2 != _throttleRoom) { _lastRecvByActor.Clear(); _throttleRoom = room2; }
                float last;                                                          // 10 receive throttle
                if (_lastRecvByActor.TryGetValue(e.Sender, out last)
                    && Time.unscaledTime - last < RECV_THROTTLE_S) return;
                _lastRecvByActor[e.Sender] = Time.unscaledTime;
                active[e.Sender] = (idx, ts);                                        // 11 bounded install
            }
            catch { /* malformed hostile events must never log per-event or throw */ }
        }

        /// <summary>Per-frame teardown edges: the combat rising edge and the
        /// expiry sweep. Room-exit teardown lives in OnRoomLeft (the reliable
        /// callback), NOT here. Called from the persistent Update (Plugin.cs)
        /// — cheap when idle.</summary>
        private static bool _lastWindow;
        internal static void Tick()
        {
            try
            {
                bool w = WindowOpen();
                if (!w && _lastWindow)
                {
                    // Hard cancellation at the combat/pick edge (review Q4):
                    // clear state and restore arm deltas NOW — no easing.
                    active.Clear();
                    RestoreAllArms();
                }
                _lastWindow = w;
                // Expiry sweep (bounded dictionary hygiene).
                if (active.Count > 0)
                {
                    List<int> dead = null;
                    foreach (var kv in active)
                    {
                        int age = unchecked(PhotonNetwork.ServerTimestamp - kv.Value.ts);
                        if (age < -2000 || age > (int)(Defs[kv.Value.idx].Duration * 1000f) + 500)
                            (dead = dead ?? new List<int>()).Add(kv.Key);
                    }
                    if (dead != null) foreach (var k in dead) active.Remove(k);
                    if (active.Count == 0) RestoreAllArms();
                }
            }
            catch { }
        }

        /// <summary>Reliable room-exit edge (Plugin.OnLeftRoom): active
        /// poses, arm deltas and receive throttles are all actor-number- or
        /// transform-keyed and MUST die with the room — actor numbers alias
        /// across incarnations and a same-named recreated room defeats the
        /// name-keyed throttle reset (round-2 review B-low pair).</summary>
        internal static void OnRoomLeft()
        {
            try
            {
                active.Clear();
                RestoreAllArms();
                _lastRecvByActor.Clear();
                _throttleRoom = "";
            }
            catch { }
        }

        private static void RestoreAllArms()
        {
            try
            {
                foreach (var kv in armApplied)
                    if (kv.Key != null) kv.Key.position -= kv.Value;
                armApplied.Clear();
            }
            catch { armApplied.Clear(); }
        }

        /// <summary>Deterministic choreography: offsets for (danceIdx, t).
        /// Pure math — same inputs, same pose on every seat. All outputs
        /// clamped by the caller.</summary>
        private static void Evaluate(int idx, float t, out Vector2 body, out Vector2 armL, out Vector2 armR)
        {
            body = Vector2.zero; armL = Vector2.zero; armR = Vector2.zero;
            switch (idx)
            {
                case 0:   // The Bounce: body hops at 2Hz, arms pump alternately
                    body = new Vector2(0f, Mathf.Abs(Mathf.Sin(t * Mathf.PI * 2f)) * 0.30f);
                    armL = new Vector2(0f, Mathf.Max(0f, Mathf.Sin(t * Mathf.PI * 4f)) * 0.65f);
                    armR = new Vector2(0f, Mathf.Max(0f, -Mathf.Sin(t * Mathf.PI * 4f)) * 0.65f);
                    break;
                case 1:   // The Wave: body sways, right arm waves overhead
                    body = new Vector2(Mathf.Sin(t * Mathf.PI * 3f) * 0.14f, 0.05f + 0.05f * Mathf.Sin(t * Mathf.PI * 6f));
                    armR = new Vector2(Mathf.Sin(t * Mathf.PI * 2.4f) * 0.45f, 1.25f);
                    armL = new Vector2(0f, 0.12f + 0.10f * Mathf.Sin(t * Mathf.PI * 3f + 1.2f));
                    break;
            }
        }

        /// <summary>Active dance offsets for the player owning `anyChild`, or
        /// false. Resolves the actor via the PhotonView owner — never
        /// Player.playerID, never cached across respawns (review Q3).</summary>
        private static bool TryGetPose(Component anyChild, out Vector2 body, out Vector2 armL, out Vector2 armR)
        {
            body = armL = armR = Vector2.zero;
            if (active.Count == 0) return false;
            try
            {
                var player = anyChild.GetComponentInParent<Player>();
                if (player == null || player.data == null || player.data.view == null) return false;
                int actor;
                try { actor = player.data.view.OwnerActorNr; } catch { return false; }
                if (PhotonNetwork.OfflineMode)
                {
                    // Offline: every body is "ours"; only the local install key exists.
                    try { actor = PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : -1; } catch { actor = -1; }
                    if (player.data.view != null && !player.data.view.IsMine) return false;
                }
                (int idx, int ts) d;
                if (!active.TryGetValue(actor, out d)) return false;
                float t = unchecked(PhotonNetwork.ServerTimestamp - d.ts) / 1000f;
                if (t < 0f || t > Defs[d.idx].Duration) return false;
                Evaluate(d.idx, t, out body, out armL, out armR);
                // NaN/bounds discipline (#434): reject anything non-finite,
                // clamp everything else.
                if (!IsFinite(body) || !IsFinite(armL) || !IsFinite(armR)) return false;
                body = Vector2.ClampMagnitude(body, MAX_OFFSET);
                armL = Vector2.ClampMagnitude(armL, 1.6f);
                armR = Vector2.ClampMagnitude(armR, 1.6f);
                return true;
            }
            catch { return false; }
        }

        private static bool IsFinite(Vector2 v)
            => !(float.IsNaN(v.x) || float.IsNaN(v.y) || float.IsInfinity(v.x) || float.IsInfinity(v.y));

        // ── Shop preview ─────────────────────────────────────────────────
        // "Accurate like the other items" (Sid's spec) is delivered by
        // CONSTRUCTION: the IMGUI puppet (CompetitiveUI.DrawDancePreview) is
        // driven by the SAME Evaluate() that moves the real body on every
        // seat, so timing and amplitude match 1:1 rather than being a hand-
        // animated approximation. Pure local display state — never networked.
        internal static string PreviewSku { get; private set; }
        private static float _previewStartedAt;

        internal static void TogglePreview(string sku)
        {
            if (string.Equals(PreviewSku, sku, StringComparison.Ordinal)) { PreviewSku = null; return; }
            PreviewSku = sku;
            _previewStartedAt = Time.unscaledTime;
        }

        internal static void StopPreview() { PreviewSku = null; }

        // Probe surface for the TestDance lever — gate-state visibility.
        internal static int ActiveCount => active.Count;
        internal static bool ArmChannelDead => _armChannelDead;
        internal static bool WobbleChannelDead => _wobbleChannelDead;

        /// <summary>Broadcast-seat verification lever (#420 — synthetic input
        /// cannot reach the overlay): install a dance on the LOCAL body,
        /// bypassing the ownership check. OFFLINE ONLY, so it can never show
        /// peers a dance the seat does not own.</summary>
        internal static bool DevInstallLocal(int idx)
        {
            if (idx < 0 || idx >= Defs.Length) return false;
            if (!PhotonNetwork.OfflineMode) return false;
            try
            {
                int a = PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : -1;
                active[a] = (idx, PhotonNetwork.ServerTimestamp);
                return true;
            }
            catch { return false; }
        }

        /// <summary>Looping preview pose for the toggled sku, clamped by the
        /// same rules as the live channels. False = no preview active.</summary>
        internal static bool TryGetPreviewPose(out string name, out Vector2 body, out Vector2 armL, out Vector2 armR)
        {
            name = null; body = armL = armR = Vector2.zero;
            var sku = PreviewSku;
            if (string.IsNullOrEmpty(sku)) return false;
            int idx = -1;
            for (int i = 0; i < Defs.Length; i++)
                if (string.Equals(Defs[i].Sku, sku, StringComparison.Ordinal)) { idx = i; break; }
            if (idx < 0) { PreviewSku = null; return false; }   // unknown sku (version skew) — self-clear
            name = Defs[idx].Name;
            float t = (Time.unscaledTime - _previewStartedAt) % Defs[idx].Duration;
            Evaluate(idx, t, out body, out armL, out armR);
            if (!IsFinite(body) || !IsFinite(armL) || !IsFinite(armR)) return false;
            body = Vector2.ClampMagnitude(body, MAX_OFFSET);
            armL = Vector2.ClampMagnitude(armL, 1.6f);
            armR = Vector2.ClampMagnitude(armR, 1.6f);
            return true;
        }

        // ── Frame channels ────────────────────────────────────────────────

        /// <summary>Body bounce: PlayerWobblePosition rewrites its transform
        /// ABSOLUTELY each Update (decompile: transform.position = physicsPos
        /// spring), so an additive Postfix self-heals with zero bookkeeping.</summary>
        [HarmonyPatch(typeof(PlayerWobblePosition), "Update")]
        internal static class Wobble_DancePatch
        {
            private static void Postfix(PlayerWobblePosition __instance)
            {
                if (_wobbleChannelDead || active.Count == 0) return;
                try
                {
                    if (!WindowOpen()) return;
                    Vector2 body, al, ar;
                    if (!TryGetPose(__instance, out body, out al, out ar)) return;
                    if (body == Vector2.zero) return;
                    __instance.transform.position += new Vector3(body.x, body.y, 0f);
                }
                catch { _wobbleChannelDead = true; }   // fail closed, vanilla pose stands
            }
        }

        /// <summary>Arm channel, restore-first: the arm TARGETS are not
        /// absolutely rewritten by vanilla (free-arm state feeds back), so
        /// the Prefix undoes the remembered delta before vanilla reads
        /// anything, and the Postfix applies + remembers the new one.</summary>
        [HarmonyPatch(typeof(IKArmMove), "Update")]
        internal static class Arm_DancePatch
        {
            private static void Prefix(IKArmMove __instance)
            {
                if (_armChannelDead || armApplied.Count == 0) return;
                try
                {
                    var tgt = __instance != null ? __instance.target : null;
                    Vector3 d;
                    if (tgt != null && armApplied.TryGetValue(tgt, out d))
                    {
                        tgt.position -= d;
                        armApplied.Remove(tgt);
                    }
                }
                catch { _armChannelDead = true; }
            }

            private static void Postfix(IKArmMove __instance)
            {
                if (_armChannelDead || active.Count == 0) return;
                try
                {
                    if (!WindowOpen()) return;
                    var tgt = __instance != null ? __instance.target : null;
                    if (tgt == null) return;
                    Vector2 body, al, ar;
                    if (!TryGetPose(__instance, out body, out al, out ar)) return;
                    bool left = tgt.name.IndexOf("Left", StringComparison.OrdinalIgnoreCase) >= 0;
                    Vector2 off = left ? al : ar;
                    if (off == Vector2.zero) return;
                    var d = new Vector3(off.x, off.y, 0f);
                    tgt.position += d;
                    armApplied[tgt] = d;
                }
                catch { _armChannelDead = true; }
            }
        }
    }
}
