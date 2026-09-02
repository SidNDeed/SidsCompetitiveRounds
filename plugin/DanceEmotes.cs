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
    /// review's CUT list, not the full design: arm-target +
    /// wobble-translation channels only (no legs, no gun/aim motion, no
    /// particles, no audio), NO spectator rendering; v1's hard combat-edge
    /// cancellation is superseded by the v2 contract below).
    ///
    /// BODY MOTION v3 (Sid, Sep 2: "I'm not sure there's any leg/body
    /// movement, it appears to just be arms ... can it not be?"): the body
    /// channel was ALWAYS emitting, but at gameplay zoom (orthoSize ~15 =
    /// 30 world units of screen height, so 1 unit ~ 36px at 1080p) the v1
    /// amplitudes (0.03-0.40) rendered at 1-14px while arm offsets
    /// (0.65-1.5) rendered at 23-54px — sub-perceptual next to the arms.
    /// v3 cranks body translation on all eight routines (hops 0.55-0.62,
    /// sways 0.20-0.48, all under the reviewed MAX_OFFSET clamp) and adds
    /// a third channel: BODY TILT (Z rotation of the wobble transform) on
    /// the six routines where it musically fits, capped at MAX_TILT_DEG.
    ///
    /// MECHANISM (rig-probe-proven, [RIG-DUMP] Aug 31): the visual body
    /// hangs off PlayerWobblePosition ("WobbleObjects"), which rewrites its
    /// transform POSITION absolutely every Update from the physics spring —
    /// so an additive position offset applied in a Postfix needs no
    /// persistence and self-heals the instant we stop. Its ROTATION,
    /// however, vanilla never reads nor writes (decompile: Update touches
    /// only position), so the tilt channel uses the RESTORE-FIRST contract
    /// instead: the Prefix undoes the remembered tilt, vanilla runs, the
    /// Postfix applies (and remembers) the new one — plus the same hard
    /// restores as the arms on every teardown path. The arms are IKArmMove
    /// components on Limbs/ArmStuff/Arm_Left|Right whose `target`
    /// transforms (TargetLeftArm/TargetRightArm) are NOT absolutely
    /// rewritten — the review confirmed free-arm state feeds back — so the
    /// arm channel uses the same RESTORE-FIRST contract: a Prefix undoes
    /// the remembered delta, vanilla runs, the Postfix applies (and
    /// remembers) the new delta.
    ///
    /// CONTRACT v2 (Sid, Sep 1: more dances + "make it so they can't
    /// move/shoot/block for the duration of the dance"): dances may play
    /// MID-COMBAT, and the price is paid by the DANCER ALONE. While YOUR
    /// dance is active, your move/jump/shoot/block inputs are scrubbed
    /// locally — GeneralInput field clears plus owner-only Gun.Attack /
    /// Block.TryBlock belts, the same input layer vanilla's lockInput
    /// suppression uses (#254); never PlayerManager.SetInputActive (#75),
    /// never playerActions.Enabled. The lock is a PURE PREDICATE over the
    /// self-expiring `active` entry (LocalDanceActive, #255): no held flag
    /// exists, so nothing can strand input past the dance's Duration. The
    /// decoy hole (a modified client dancing while still playing) is closed
    /// OBSERVABLY on every seat: an actor's dance render is cancelled the
    /// moment that actor's player visibly moves (sustained velocity, armed
    /// during battle only) or its gun fires, and on death/inactive/
    /// unresolvable bodies. Every seat simulates/receives those same
    /// movements and shots, so all seats cancel near-simultaneously; any
    /// residual cross-seat timing divergence is rendering-only. Nothing
    /// here touches physics, health, aim, or ANOTHER player's input.
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
            new DanceDef("dance_bounce",     "The Bounce",     4.0f),
            new DanceDef("dance_wave",       "The Wave",       4.0f),
            new DanceDef("dance_jacks",      "Jumping Jacks",  4.5f),
            new DanceDef("dance_shimmy",     "The Shimmy",     4.0f),
            new DanceDef("dance_disco",      "Disco Fever",    5.0f),
            new DanceDef("dance_helicopter", "The Helicopter", 5.5f),
            new DanceDef("dance_robot",      "The Robot",      6.0f),
            new DanceDef("dance_floss",      "The Floss",      5.0f),
        };

        private const float MAX_OFFSET = 0.9f;          // hard clamp, world units
        private const float MAX_TILT_DEG = 30f;         // hard clamp, body Z tilt — bounded so no
                                                        // dance can flip a face or spin a gun visual
        private const float SEND_THROTTLE_S = 2.5f;
        private const float RECV_THROTTLE_S = 2.0f;

        // Active dance per room actor: actorNumber -> (danceIdx, startServerTs).
        // Bounded: one entry per actor; cleared on expiry, by the CONTRACT v2
        // observable cancel (Tick sweep + the bullet-birth funnel), and on
        // the reliable room-exit callback (OnRoomLeft).
        private static readonly Dictionary<int, (int idx, int ts)> active = new Dictionary<int, (int, int)>();
        // Arm restore-first bookkeeping: per-target remembered applied delta.
        private static readonly Dictionary<Transform, Vector3> armApplied = new Dictionary<Transform, Vector3>();
        // Body-tilt restore-first bookkeeping: per-wobble-transform remembered
        // applied Z degrees (vanilla never writes wobble rotation, so an
        // applied tilt would otherwise outlive the dance).
        private static readonly Dictionary<Transform, float> bodyRotApplied = new Dictionary<Transform, float>();

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
        /// card pick in progress. Evaluated independently at SEND, RECEIVE
        /// and EVERY FRAME (#352 — no patch may rely on another patch's
        /// gate). CONTRACT v2: there is deliberately NO battle gate here —
        /// dancing mid-combat is allowed; the dancer pays with the local
        /// input lock (LocalDanceActive) and every seat cancels the render
        /// on observable movement/shots (Tick + Dance_ProjectileInit_Patch).</summary>
        internal static bool WindowOpen()
        {
            try
            {
                if (RoomActors.LocalIsSpectator) return false;   // observers never render dances
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

        /// <summary>Per-frame upkeep: the expiry sweep plus the CONTRACT v2
        /// observable cancel (velocity / dead / unresolvable — the shot
        /// cancel lives in Dance_ProjectileInit_Patch, the funnel that runs
        /// on every seat). v1's combat-rising-edge cancel-all is gone: dances now
        /// survive into battle and pay via the input lock instead. Room-exit
        /// teardown lives in OnRoomLeft (the reliable callback), NOT here.
        /// Called from the persistent Update (Plugin.cs) — cheap when idle.</summary>
        internal static void Tick()
        {
            try
            {
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
                }
                if (active.Count > 0) ObservableCancelSweep();
                else
                {
                    if (_velStrikes.Count > 0) _velStrikes.Clear();
                    if (armApplied.Count > 0 || bodyRotApplied.Count > 0) RestoreAllApplied();
                }
            }
            catch { }
        }

        // ── CONTRACT v2: input lock + observable cancel ──────────────────

        /// <summary>TRUE while the LOCAL player's own dance is running. A
        /// PURE COMPUTED predicate over the self-expiring `active` entry
        /// (#255 — no held flag; the entry itself dies at Duration, at
        /// observable cancel, and on room exit), using the same wrap-safe
        /// ServerTimestamp math as TryGetPose. Works offline: Send's local
        /// install path keys by the same LocalPlayer.ActorNumber.</summary>
        internal static bool LocalDanceActive
        {
            get
            {
                try
                {
                    if (active.Count == 0) return false;
                    int a = PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : -1;
                    (int idx, int ts) d;
                    if (!active.TryGetValue(a, out d)) return false;
                    if (d.idx < 0 || d.idx >= Defs.Length) return false;
                    float t = unchecked(PhotonNetwork.ServerTimestamp - d.ts) / 1000f;
                    return t >= 0f && t <= Defs[d.idx].Duration;
                }
                catch { return false; }   // fail OPEN — never lock input on an error
            }
        }

        private const float CANCEL_VEL = 2.5f;    // world units/s; run speed is ~9-11, residual slide decays well below this
        private const int CANCEL_STRIKES = 2;     // consecutive Tick frames over threshold (or unresolvable)
        private const float VEL_GRACE_S = 0.35f;  // pre-dance momentum may still be bleeding off at start
        private static readonly Dictionary<int, int> _velStrikes = new Dictionary<int, int>();

        /// <summary>actor -> live Player body, mirroring TryGetPose's
        /// resolution in reverse (data.view owner, never Player.playerID;
        /// offline maps every IsMine body to the local install key).</summary>
        private static Player ResolveActorPlayer(int actor)
        {
            try
            {
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return null;
                bool offline = PhotonNetwork.OfflineMode;
                int localActor = -1;
                if (offline)
                    try { localActor = PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : -1; } catch { }
                foreach (var p in pm.players)
                {
                    if (p == null || p.data == null || p.data.view == null) continue;
                    if (offline)
                    {
                        if (actor == localActor && p.data.view.IsMine) return p;
                    }
                    else
                    {
                        int owner;
                        try { owner = p.data.view.OwnerActorNr; } catch { continue; }
                        if (owner == actor) return p;
                    }
                }
            }
            catch { }
            return null;
        }

        /// <summary>The observable cancel (CONTRACT v2), every frame for
        /// every active entry, on EVERY seat: stop rendering an actor's
        /// dance when their player (a) visibly moves — sustained velocity
        /// over CANCEL_VEL for CANCEL_STRIKES consecutive ticks, armed only
        /// during a live ONLINE battle (round-transition MovePlayers drags
        /// bodies at speed between rounds, and the offline sandbox keeps
        /// battleOngoing true forever — neither is the decoy window) and
        /// only after VEL_GRACE_S; (b) is dead or inactive (immediate — an
        /// unambiguous state, and RPCA_Die replicates to all seats); or
        /// (c) cannot be resolved for CANCEL_STRIKES consecutive ticks (the
        /// strike tolerance keeps a one-frame spawn/teardown gap from
        /// killing a legitimate dance). Cancelling the LOCAL entry also
        /// releases the input lock — being knocked around mid-dance frees
        /// your controls instead of stranding you. Velocity reads the
        /// publicized CharacterData.playerVel and FAILS OPEN per channel: a
        /// read error never cancels, it just leaves that test inert.</summary>
        private static void ObservableCancelSweep()
        {
            try
            {
                bool battle = false;
                try
                {
                    var gm = GameManager.instance;
                    battle = gm != null && gm.battleOngoing && !PhotonNetwork.OfflineMode;
                }
                catch { }
                List<int> cancel = null;
                foreach (var kv in active)
                {
                    int actor = kv.Key;
                    float age = unchecked(PhotonNetwork.ServerTimestamp - kv.Value.ts) / 1000f;
                    var p = ResolveActorPlayer(actor);
                    if (p == null || p.data == null)
                    {
                        if (Strike(actor)) (cancel = cancel ?? new List<int>()).Add(actor);   // (c)
                        continue;
                    }
                    bool deadOrInactive = false;
                    try { deadOrInactive = p.data.dead || !p.gameObject.activeInHierarchy; } catch { }
                    if (deadOrInactive)
                    {
                        (cancel = cancel ?? new List<int>()).Add(actor);                      // (b)
                        continue;
                    }
                    bool over = false;
                    try
                    {
                        var vel = p.data.playerVel;
                        if (vel != null && vel.simulated)
                            over = ((Vector2)vel.velocity).magnitude > CANCEL_VEL;
                    }
                    catch { }   // velocity channel fail-open
                    if (battle && age >= VEL_GRACE_S && over)
                    {
                        if (Strike(actor)) (cancel = cancel ?? new List<int>()).Add(actor);   // (a)
                    }
                    else _velStrikes.Remove(actor);
                }
                if (cancel != null)
                {
                    foreach (var a in cancel) { active.Remove(a); _velStrikes.Remove(a); }
                    if (active.Count == 0) RestoreAllApplied();
                    // Arms/tilts for still-dancing actors restore via the
                    // restore-first Arm/Wobble prefixes on their next Update.
                }
            }
            catch { }
        }

        private static bool Strike(int actor)
        {
            int n;
            _velStrikes.TryGetValue(actor, out n);
            n++;
            if (n >= CANCEL_STRIKES) { _velStrikes.Remove(actor); return true; }
            _velStrikes[actor] = n;
            return false;
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
                RestoreAllApplied();
                _lastRecvByActor.Clear();
                _velStrikes.Clear();
                _throttleRoom = "";
            }
            catch { }
        }

        /// <summary>Hard restore of every remembered restore-first delta —
        /// arm positions AND body tilts. Each channel is independently
        /// guarded so one failing cannot strand the other. `kv.Key != null`
        /// is the UnityEngine.Object overload: a destroyed transform reads
        /// null and is skipped (its delta died with the object).</summary>
        private static void RestoreAllApplied()
        {
            try
            {
                foreach (var kv in armApplied)
                    if (kv.Key != null) kv.Key.position -= kv.Value;
                armApplied.Clear();
            }
            catch { armApplied.Clear(); }
            try
            {
                foreach (var kv in bodyRotApplied)
                    if (kv.Key != null) kv.Key.rotation = Quaternion.Euler(0f, 0f, -kv.Value) * kv.Key.rotation;
                bodyRotApplied.Clear();
            }
            catch { bodyRotApplied.Clear(); }
        }

        /// <summary>Deterministic choreography: offsets + body Z tilt for
        /// (danceIdx, t). Pure math — same inputs, same pose on every seat.
        /// All outputs clamped by the caller. Body amplitudes are sized for
        /// gameplay zoom (see BODY MOTION v3 in the header): hops over half
        /// a body diameter, sways a third — anything under ~0.15 is
        /// sub-perceptual at orthoSize 15 and exists only as texture.</summary>
        private static void Evaluate(int idx, float t, out Vector2 body, out float bodyRotDeg, out Vector2 armL, out Vector2 armR)
        {
            body = Vector2.zero; bodyRotDeg = 0f; armL = Vector2.zero; armR = Vector2.zero;
            switch (idx)
            {
                case 0:   // The Bounce: body hops at 2Hz (no tilt — a pure
                          // upright hop IS this dance), arms pump alternately
                    body = new Vector2(0f, Mathf.Abs(Mathf.Sin(t * Mathf.PI * 2f)) * 0.55f);
                    armL = new Vector2(0f, Mathf.Max(0f, Mathf.Sin(t * Mathf.PI * 4f)) * 0.65f);
                    armR = new Vector2(0f, Mathf.Max(0f, -Mathf.Sin(t * Mathf.PI * 4f)) * 0.65f);
                    break;
                case 1:   // The Wave: body sways wide and LEANS into the sway
                          // (negative Z = top tips right in Unity 2D, so the
                          // sign opposes x to lean into motion), right arm
                          // waves overhead
                    body = new Vector2(Mathf.Sin(t * Mathf.PI * 3f) * 0.32f, 0.08f + 0.08f * Mathf.Sin(t * Mathf.PI * 6f));
                    bodyRotDeg = -Mathf.Sin(t * Mathf.PI * 3f) * 9f;
                    armR = new Vector2(Mathf.Sin(t * Mathf.PI * 2.4f) * 0.45f, 1.25f);
                    armL = new Vector2(0f, 0.12f + 0.10f * Mathf.Sin(t * Mathf.PI * 3f + 1.2f));
                    break;
                case 2:   // Jumping Jacks: 1.6Hz jack cycle (hops at double
                {         // rate via the abs), arms SNAP down-at-sides <-> up-out;
                          // body stays upright — jacks are a vertical exercise
                    float ph = Mathf.Sin(t * Mathf.PI * 3.2f);
                    float up = ph > 0f ? 1f : 0f;               // hard snap, jack-style
                    body = new Vector2(0f, Mathf.Abs(ph) * 0.62f);
                    armL = Vector2.Lerp(new Vector2(-0.45f, -0.25f), new Vector2(-0.75f, 1.15f), up);
                    armR = Vector2.Lerp(new Vector2(0.45f, -0.25f), new Vector2(0.75f, 1.15f), up);
                    break;
                }
                case 3:   // The Shimmy: rapid lateral vibration + fast shoulder
                {         // wiggle (small tilt at the vibration rate), arms out
                          // at the sides pulsing in counter-phase
                    float pulse = Mathf.Sin(t * Mathf.PI * 8f);
                    body = new Vector2(Mathf.Sin(t * Mathf.PI * 22f) * 0.20f, 0.05f * Mathf.Sin(t * Mathf.PI * 11f));
                    bodyRotDeg = Mathf.Sin(t * Mathf.PI * 22f + 1.0f) * 7f;
                    armL = new Vector2(-(0.85f + 0.25f * pulse), 0.35f + 0.10f * Mathf.Sin(t * Mathf.PI * 8f + 2.6f));
                    armR = new Vector2(0.85f - 0.25f * pulse, 0.35f + 0.10f * Mathf.Sin(t * Mathf.PI * 8f + 5.8f));
                    break;
                }
                case 4:   // Disco Fever: right arm sweeps the diagonal point
                {         // up-right / down-across; body tilts hard on the beat
                          // (the Travolta lean, counter-sign to the point so the
                          // hip juts away from the arm) and bobs on the off-beat
                    float k = Mathf.Sin(t * Mathf.PI * 2.5f);
                    body = new Vector2(Mathf.Cos(t * Mathf.PI * 2.5f) * 0.34f, 0.08f + 0.10f * Mathf.Sin(t * Mathf.PI * 5f));
                    bodyRotDeg = -k * 16f;
                    armR = new Vector2(0.50f + 0.48f * k, 0.30f + 0.82f * k);
                    armL = new Vector2(-0.35f - 0.20f * k, -0.10f - 0.25f * k);
                    break;
                }
                case 5:   // The Helicopter: right arm circles fully overhead,
                {         // body bobs and BANKS in a circle with the rotor —
                          // a lean that orbits (cos term) around a small
                          // steady tilt, reading as the body being dragged
                          // around by the arm
                    float th = t * Mathf.PI * 2f * 1.4f;        // 1.4 revolutions/s
                    body = new Vector2(0.14f * Mathf.Sin(th), Mathf.Abs(Mathf.Sin(t * Mathf.PI * 2.8f)) * 0.30f);
                    bodyRotDeg = Mathf.Cos(th) * 14f - 5f;
                    armR = new Vector2(Mathf.Cos(th) * 0.80f, 0.70f + Mathf.Sin(th) * 0.80f);   // peak |armR| = 1.5
                    armL = new Vector2(-0.25f, -0.15f + 0.06f * Mathf.Sin(t * Mathf.PI * 2.8f));
                    break;
                }
                case 6:   // The Robot: quantized stepped poses (floor'd time)
                {         // including stepped body tilts — the tilt SNAPS
                          // between held angles like everything else; arm/tilt
                          // rates deliberately mismatched so 6s never loops
                    float tq = Mathf.Floor(t * 3f) / 3f;        // 3 poses per second
                    body = new Vector2(0.26f * Mathf.Sin(tq * 2.9f), 0.20f * Mathf.Abs(Mathf.Cos(tq * 2.3f)));
                    bodyRotDeg = Mathf.Sin(tq * 3.7f) * 12f;
                    armL = new Vector2(-0.50f - 0.45f * Mathf.Sin(tq * 2.1f), 0.55f + 0.55f * Mathf.Cos(tq * 1.7f));
                    armR = new Vector2(0.50f + 0.45f * Mathf.Cos(tq * 2.6f), 0.55f + 0.55f * Mathf.Sin(tq * 1.3f));
                    break;
                }
                case 7:   // The Floss: hips sway WIDE while both arms swing
                {         // side-to-side as a pair in OPPOSITION across the
                          // body; the tilt follows the hip push (so hips and
                          // tilt move together, both counter to the arms)
                    float s = Mathf.Sin(t * Mathf.PI * 4.4f);
                    float armX = -s * 1.0f;                     // arms opposite the hips
                    body = new Vector2(s * 0.48f, 0.09f + 0.08f * Mathf.Abs(Mathf.Cos(t * Mathf.PI * 4.4f)));
                    bodyRotDeg = s * 12f;
                    armL = new Vector2(armX - 0.25f, 0.18f + 0.10f * Mathf.Abs(s));
                    armR = new Vector2(armX + 0.25f, 0.18f + 0.10f * Mathf.Abs(s));
                    break;
                }
            }
        }

        /// <summary>Active dance offsets for the player owning `anyChild`, or
        /// false. Resolves the actor via the PhotonView owner — never
        /// Player.playerID, never cached across respawns (review Q3).</summary>
        private static bool TryGetPose(Component anyChild, out Vector2 body, out float bodyRotDeg, out Vector2 armL, out Vector2 armR)
        {
            body = armL = armR = Vector2.zero; bodyRotDeg = 0f;
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
                Evaluate(d.idx, t, out body, out bodyRotDeg, out armL, out armR);
                // NaN/bounds discipline (#434): reject anything non-finite,
                // clamp everything else.
                if (!IsFinite(body) || !IsFinite(armL) || !IsFinite(armR) || !IsFinite(bodyRotDeg)) return false;
                body = Vector2.ClampMagnitude(body, MAX_OFFSET);
                bodyRotDeg = Mathf.Clamp(bodyRotDeg, -MAX_TILT_DEG, MAX_TILT_DEG);
                armL = Vector2.ClampMagnitude(armL, 1.6f);
                armR = Vector2.ClampMagnitude(armR, 1.6f);
                return true;
            }
            catch { return false; }
        }

        private static bool IsFinite(Vector2 v)
            => !(float.IsNaN(v.x) || float.IsNaN(v.y) || float.IsInfinity(v.x) || float.IsInfinity(v.y));

        private static bool IsFinite(float f)
            => !(float.IsNaN(f) || float.IsInfinity(f));

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
        /// same rules as the live channels. False = no preview active.
        /// [N15] The puppet (CompetitiveUI.DrawDancePreview) consumes the full
        /// five-output pose — bodyRotDeg included — so the pre-tilt 4-out
        /// overload left with its last caller.</summary>
        internal static bool TryGetPreviewPose(out string name, out Vector2 body, out float bodyRotDeg, out Vector2 armL, out Vector2 armR)
        {
            name = null; body = armL = armR = Vector2.zero; bodyRotDeg = 0f;
            var sku = PreviewSku;
            if (string.IsNullOrEmpty(sku)) return false;
            int idx = -1;
            for (int i = 0; i < Defs.Length; i++)
                if (string.Equals(Defs[i].Sku, sku, StringComparison.Ordinal)) { idx = i; break; }
            if (idx < 0) { PreviewSku = null; return false; }   // unknown sku (version skew) — self-clear
            name = Defs[idx].Name;
            float t = (Time.unscaledTime - _previewStartedAt) % Defs[idx].Duration;
            Evaluate(idx, t, out body, out bodyRotDeg, out armL, out armR);
            if (!IsFinite(body) || !IsFinite(armL) || !IsFinite(armR) || !IsFinite(bodyRotDeg)) return false;
            body = Vector2.ClampMagnitude(body, MAX_OFFSET);
            bodyRotDeg = Mathf.Clamp(bodyRotDeg, -MAX_TILT_DEG, MAX_TILT_DEG);
            armL = Vector2.ClampMagnitude(armL, 1.6f);
            armR = Vector2.ClampMagnitude(armR, 1.6f);
            return true;
        }

        // ── Frame channels ────────────────────────────────────────────────

        /// <summary>Body channel, two halves with two contracts. POSITION:
        /// PlayerWobblePosition rewrites its transform position ABSOLUTELY
        /// each Update (decompile: transform.position = physicsPos spring),
        /// so the additive Postfix offset self-heals with zero bookkeeping.
        /// TILT: vanilla never writes the wobble transform's rotation, so an
        /// applied tilt would persist forever — the Prefix restores the
        /// remembered tilt (restore-first, the arm contract) and the Postfix
        /// applies + remembers the new one; teardown paths that can outrun
        /// the next Update (room exit, dance-end sweep) hard-restore via
        /// RestoreAllApplied. World-Z pre-multiply composition so restore is
        /// the exact inverse regardless of what else composes rotation.</summary>
        [HarmonyPatch(typeof(PlayerWobblePosition), "Update")]
        internal static class Wobble_DancePatch
        {
            private static void Prefix(PlayerWobblePosition __instance)
            {
                if (_wobbleChannelDead || bodyRotApplied.Count == 0) return;
                try
                {
                    var tr = __instance != null ? __instance.transform : null;
                    float deg;
                    if (tr != null && bodyRotApplied.TryGetValue(tr, out deg))
                    {
                        tr.rotation = Quaternion.Euler(0f, 0f, -deg) * tr.rotation;
                        bodyRotApplied.Remove(tr);
                    }
                }
                catch { _wobbleChannelDead = true; }
            }

            private static void Postfix(PlayerWobblePosition __instance)
            {
                if (_wobbleChannelDead || active.Count == 0) return;
                try
                {
                    if (!WindowOpen()) return;
                    Vector2 body, al, ar; float rot;
                    if (!TryGetPose(__instance, out body, out rot, out al, out ar)) return;
                    if (body != Vector2.zero)
                        __instance.transform.position += new Vector3(body.x, body.y, 0f);
                    if (rot != 0f)
                    {
                        var tr = __instance.transform;
                        tr.rotation = Quaternion.Euler(0f, 0f, rot) * tr.rotation;
                        bodyRotApplied[tr] = rot;
                    }
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
                    Vector2 body, al, ar; float rotUnused;
                    if (!TryGetPose(__instance, out body, out rotUnused, out al, out ar)) return;
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

        // ── CONTRACT v2 input-lock patches ───────────────────────────────

        /// <summary>The dancer's own input scrub (OverlayInputGate's shape:
        /// same field list, same fire-until-neutral latch so a Fire held
        /// across the dance's end cannot discharge a charged shot on the
        /// first free frame). Gated on the LOCAL player only
        /// (!controlledElseWhere + data.view.IsMine — replica fields come
        /// from the sync stream, never local input) and on the pure
        /// LocalDanceActive predicate, so there is no flag to strand (#255).
        /// aimDirection is deliberately untouched (shooting is blocked;
        /// zeroing it risks downstream normalization). Third sibling postfix
        /// on GeneralInput.Update (#352 — each carries its own gate).
        /// Card picks are unaffected: CardChoice.DoPlayerSelect reads
        /// playerActions directly, not these fields (#254).</summary>
        [HarmonyPatch(typeof(GeneralInput), "Update")]
        internal static class Dance_GeneralInput_Patch
        {
            // Keyed by instance; an entry lives only while its latch is armed.
            private static readonly Dictionary<GeneralInput, bool> fireLatch = new Dictionary<GeneralInput, bool>();

            private static bool FireHeldPhysically(GeneralInput gi)
            {
                try
                {
                    var actions = gi.data != null ? gi.data.playerActions : null;
                    var fire = actions != null ? actions.Fire : null;
                    if (fire != null)
                        return fire.IsPressed || fire.WasPressed || fire.WasReleased;
                }
                catch { }
                return gi.shootIsPressed || gi.shootWasPressed || gi.shootWasReleased;
            }

            private static void SweepDeadKeys()
            {
                // Bound the dictionary across an arbitrarily long process
                // session (destroyed Unity keys otherwise accrete).
                if (fireLatch.Count <= 8) return;
                var dead = new List<GeneralInput>();
                foreach (var k in fireLatch.Keys) if (k == null) dead.Add(k);
                foreach (var k in dead) fireLatch.Remove(k);
            }

            private static void Postfix(GeneralInput __instance)
            {
                try
                {
                    if (__instance == null || __instance.controlledElseWhere) return;
                    var data = __instance.data;   // vanilla's own wiring (publicized)
                    if (data == null || data.view == null || !data.view.IsMine) return;
                    if (LocalDanceActive)
                    {
                        if (FireHeldPhysically(__instance)) { SweepDeadKeys(); fireLatch[__instance] = true; }
                        __instance.direction = Vector3.zero;
                        __instance.jumpWasPressed = false;
                        __instance.jumpIsPressed = false;
                        __instance.shootWasPressed = false;
                        __instance.shootIsPressed = false;
                        __instance.shootWasReleased = false;
                        __instance.shieldWasPressed = false;
                        return;
                    }
                    if (fireLatch.Count == 0 || !fireLatch.ContainsKey(__instance)) return;
                    if (!FireHeldPhysically(__instance)) { fireLatch.Remove(__instance); return; }
                    __instance.shootWasPressed = false;
                    __instance.shootIsPressed = false;
                    __instance.shootWasReleased = false;
                }
                catch { }   // fail OPEN — never strand a player unable to act
            }
        }

        /// <summary>LOCAL dancer shoot belt (mirrors GunAttackBlockOnF5Patch):
        /// Gun.Attack only runs on the OWNER's seat for a real shot
        /// (WeaponHandler drives it from GeneralInput's shoot fields, which
        /// replicas never populate — remote shots arrive as an instantiated
        /// bullet + RPCA_Init, never as a remote Attack call; decompile-
        /// verified, the #405 reachability check). So this prefix is purely
        /// the owner-side belt: it covers the update-order race that can
        /// slip a press past the input scrub on the arming frame, and any
        /// card-driven Attack on a gun we own. Suppress WITHOUT cancelling —
        /// a raced press must not end the dance and then fire anyway. The
        /// observable cancel for OTHER seats lives in
        /// Dance_ProjectileInit_Patch, the funnel that actually runs
        /// everywhere.</summary>
        [HarmonyPatch(typeof(Gun), "Attack")]
        internal static class Dance_GunAttack_Patch
        {
            private static bool Prefix(Gun __instance)
            {
                try
                {
                    if (!LocalDanceActive) return true;
                    var pv = __instance != null ? __instance.GetComponentInParent<PhotonView>() : null;
                    if (pv == null || !pv.IsMine) return true;   // never touch another owner's gun
                    return false;
                }
                catch { return true; }   // fail OPEN — never block a shot on an error
            }
        }

        /// <summary>Observable shot cancel at the one funnel every gun fire
        /// passes through on EVERY seat: the bullet's birth RPC.
        /// Gun.FireBurst sends ProjectileInit.RPCA_Init /
        /// RPCA_Init_noAmmoUse / RPCA_Init_SeparateGun with
        /// RpcTarget.All, and each carries the SHOOTER's actor number as
        /// its first argument — so when a dancing actor's gun actually
        /// fires (modified client, or any path that slipped every owner
        /// belt), every honest seat sees the birth and stops rendering
        /// that actor's dance. A compliant dancer never triggers this:
        /// their Attack is suppressed at the owner, so no bullet is ever
        /// born. Postfix + positional __0 binding (#364 — object[] __args
        /// would box on every bullet birth), first-statement bail when
        /// nobody dances. TargetMethods THROWS if any of the three known
        /// overloads fails to resolve — a loud "Failed to patch" at
        /// startup (#83/#320), degrading to velocity/death cancels only,
        /// beats a silently absent probe.</summary>
        [HarmonyPatch]
        internal static class Dance_ProjectileInit_Patch
        {
            private static IEnumerable<System.Reflection.MethodBase> TargetMethods()
            {
                string[] names = { "RPCA_Init", "RPCA_Init_noAmmoUse", "RPCA_Init_SeparateGun" };
                foreach (var n in names)
                {
                    var m = AccessTools.Method(typeof(ProjectileInit), n);
                    if (m == null) throw new MissingMethodException("ProjectileInit." + n + " not found - dance shot-cancel funnel moved");
                    yield return m;
                }
            }

            private static void Postfix(int __0)   // senderID: the shooter's actor number, all three overloads
            {
                try
                {
                    if (active.Count == 0) return;
                    if (active.Remove(__0))
                    {
                        _velStrikes.Remove(__0);
                        if (active.Count == 0) RestoreAllApplied();
                    }
                }
                catch { }   // fail OPEN — a cancel miss is rendering-only
            }
        }

        /// <summary>Owner-only block belt (mirrors Block_FfaSpawnGrace_Patch):
        /// a skipped TryBlock never runs RPCA_DoBlock, so no BlockAction, no
        /// RPC, no replica block anywhere (#268). Remote replicas never reach
        /// TryBlock at all (their shieldWasPressed is never set online), so
        /// no cancel branch is needed here — blocks cannot be observed
        /// through this funnel for other actors.</summary>
        [HarmonyPatch(typeof(Block), "TryBlock")]
        internal static class Dance_BlockTryBlock_Patch
        {
            private static bool Prefix(Block __instance)
            {
                try
                {
                    if (!LocalDanceActive) return true;
                    var data = __instance != null ? __instance.data : null;
                    if (data == null || data.view == null || !data.view.IsMine) return true;
                    return false;
                }
                catch { return true; }   // fail OPEN
            }
        }
    }
}
