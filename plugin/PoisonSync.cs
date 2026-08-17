// PoisonSync.cs — victim-authoritative damage-over-time ticks (bug reports #143, #151).
//
// ─────────────────────────────────────────────────────────────────────────────
// THE PROBLEM
//
// Vanilla runs poison as a LOCAL SIMULATION ON EVERY CLIENT. RayHitPoison
// .DoHitEffect executes per replica and each starts its own DamageOverTime
// coroutine; every tick calls HealthHandler.DoDamage(..., ignoreBlock: false),
// which early-returns while THAT replica sees the victim blocking. Block
// activation reaches replicas at different moments (the owner's input fires
// TryBlock; SyncPlayerMovement relays RPCAO_DoBlock to Others, and vanilla can
// delay that by 200ms via delayOtherActions, plus latency). Replicas therefore
// disagree about which ticks landed. data.health is never networked and
// `damageDealt += dpt` runs BEFORE the blockable call, so a dropped tick is
// permanent and never reconciles. That is the ghost-HP desync.
//
// v1.34.5 bought agreement by forcing ignoreBlock = true on every healthRemoval
// tick (VanillaFixes.PoisonGhostPatch). Everyone agreed; blocking stopped
// negating poison at all (#143). Sid has asked for both properties at once.
//
// ─────────────────────────────────────────────────────────────────────────────
// THE DESIGN — "Victim-Keyed Authority"
//
// The victim's own client is the only one that knows its block window with no
// network translation, so it is the authority. It runs the ONLY damage
// coroutine, decides blocked/not-blocked per tick, and publishes each verdict.
// Every client — INCLUDING THE AUTHORITY — applies damage only when that
// published verdict arrives. "The event is the sole commit path" is what stops
// the authority double-applying, and it means a lost packet delays damage
// rather than diverging it (events are reliable, so it arrives).
//
// A blocked tick is CONSUMED, not deferred: vanilla does `damageDealt += dpt`
// BEFORE the blockable call, so blocking permanently erases that slice and the
// poison still ends at its original time. Sid confirmed that reading.
//
// ─────────────────────────────────────────────────────────────────────────────
// WHY THERE IS NO ACTIVATION BARRIER — and why one is not needed
//
// The previous attempt published the mode as a ROOM property decided by the
// master, and was shipped INERT because that is only EVENTUALLY consistent: at
// game start client A could already see AUTH while B still saw nothing, so A
// suppressed its local DOT for a victim publishing no verdicts (or B ran a
// local DOT for a victim whose verdicts A was obeying). Health divergence —
// strictly worse than the compromise it replaced. A proposal/ACK handshake does
// NOT fix that; it just moves the same race onto the "now ACTIVE" broadcast.
//
// So the room-global mode is gone. The protocol selector is a per-player
// property that is DELIVERED INSIDE THE SAME PHOTON OPERATION THAT CREATES THE
// VICTIM'S Player OBJECT:
//
//   * staged BEFORE joining (a pure local Merge — Player.SetCustomProperties
//     takes the RoomReference == null && IsLocal branch and sends nothing), then
//     snapshotted by LoadBalancingClient into the join op as parameter 249;
//   * a client that joins LATER reads it out of the join RESPONSE, in
//     ReadoutProperties for every actor, before OnJoinedRoom fires;
//   * a client already present reads it from EV_JOIN, where CreatePlayer is
//     called WITH the property hashtable — the Player object is constructed
//     with it — before OnPlayerEnteredRoom fires.
//
// Handling a stream on victim V requires V's PhotonView to exist locally, which
// requires having processed V's EV_JOIN. Therefore every client that can act on
// V has necessarily held cap(V) for the entire preceding lifetime of the room.
//
// The mode is not "observed at the same instant" — it is NOT OBSERVABLE BEFORE
// USE, which is strictly stronger and is why this is not the failed handshake
// one level down. There is no epoch, no master, no per-game latch, and nothing
// to re-evaluate — which makes learnings #138 (StartGame skips rematches), #143
// (PlayerJoined re-enters StartGame) and #273 (a master-keyed gate goes stale
// mid-map) inapplicable here rather than merely handled.
//
// Consequence: V never writes the property in-room, so it is immutable for the
// room's lifetime. NEVER add an in-room SetCustomProperties for it.
//
// ─────────────────────────────────────────────────────────────────────────────
// MIXED LOBBIES — HonorBlock()
//
// A client cannot make an unpatched peer stop its local coroutine or honour a
// verdict. So the victim decides whether to HONOUR its own block, per tick:
//
//   * Every peer capable  -> honour. Full protocol; blocking negates ticks and
//     every client applies the identical committed set.
//   * Some peer incapable, in a MOD-ISSUED room -> do NOT honour; publish every
//     tick blocked=false. That peer is running PoisonGhostPatch's forced
//     ignoreBlock, so it applies the full set; capable observers apply the full
//     set from events; the victim applies the full set from its own echo. Same
//     tick SET as v1.35.5 (about one round-trip later, and health converges
//     exactly at stream end).
//   * Some peer incapable, in a PRIVATE room-code game -> honour anyway.
//     PoisonGhostPatch does NOT run there (#151), so that peer is block-AWARE
//     and lands on nearly the same set as the victim; divergence is boundary
//     ticks. Publishing blocked=false instead would make them disagree on the
//     ENTIRE blocked set — strictly worse.
//
// HonorBlock is read by NOBODY but the victim, so a wrong answer cannot
// desynchronise any client's DECISION — it can only shade which verdicts get
// published, which everyone then obeys identically. Its conservative direction
// is therefore free, which is what makes a 3s roster quarantine affordable.
//
// Rollout property, and it is the point: because the fallback is PER-VICTIM
// rather than per-room, this needs no coordination. The moment a room happens
// to contain only patched clients, blocking starts negating poison in it.
//
// ─────────────────────────────────────────────────────────────────────────────
// OUTER SAFETY BOUND
//
// PlayerManager.Move ends with `data.isPlaying = true; data.healthHandler
// .Revive();` and Revive() does health = MaxHealth, dot.StopAllCoroutines() and
// Block.sinceBlock = +Infinity. MovePlayers runs that for EVERY player on EVERY
// client, and RevivePlayers() does the same in both transition paths. NOTHING
// this file can produce survives a round boundary. That is load-bearing.

using HarmonyLib;
using ExitGames.Client.Photon;
using Photon.Pun;
using Photon.Realtime;
using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace CompetitiveRounds
{
    internal static class PoisonSync
    {
        // ── Protocol identity ─────────────────────────────────────────────
        //
        // The KEY carries the protocol version. cr_pois1 meant "I speak the
        // room-global-mode protocol" and must NEVER be reused — a client
        // advertising that key answers a different question. Any future
        // SEMANTIC change gets cr_pois3 plus a MIN_MOD_VERSION raise; additive
        // wire fields are fine within a key because unknown trailing elements
        // are ignored by the length checks below.
        internal const string CapabilityProp = "cr_pois2";
        private const int CapabilityValue = 1;
        private const byte EventCode = 47;          // Photon custom codes are 0-199
        private const byte Protocol = 2;

        // ── THERE IS NO WATCHDOG. This is deliberate; do not add one back. ──
        //
        // Two review rounds were spent on a watchdog that let a replica give up
        // on a silent victim and apply the stream locally. It is not
        // implementable, for a reason that is structural rather than a tuning
        // problem: an observer CANNOT DISTINGUISH "the victim stalled and its
        // header is late" from "the victim started a new stream". Both arrive as
        // a header stamped after the observer gave up. Round 1 caught the late
        // header double-applying the stream; the fix stamped the stream's START
        // instead of its publish time — and round 2 correctly pointed out there
        // is no yield between those two statements, so they are the SAME INSTANT
        // and the fix was vacuous. A doubled stream is not a cosmetic error:
        // HealthHandler.DoDamage RPCs RPCA_Die to ALL from ANY replica whose
        // local health crosses zero, with no ownership check, so an over-damaged
        // observer ends the round for the whole room.
        //
        // What a watchdog was supposed to buy — bounding a modified client that
        // advertises capability and then publishes nothing — it never actually
        // bought: such a client only has to publish ONE verdict per stream to
        // stamp liveness and disarm it, then go quiet.
        //
        // Every honest way a capable victim can stop publishing is ALREADY
        // covered without one:
        //   * disconnects -> its GameObject is Photon-destroyed, ShadowDot exits
        //     on view == null;
        //   * dies -> RPCA_Die is an All-RPC and calls dot.StopAllCoroutines() on
        //     every client, killing the shadow too;
        //   * its patch failed to attach -> it never staged cr_pois2, so
        //     CapableVictim is false and no shadow ever starts;
        //   * it hitches -> the verdicts are LATE, not absent, and they arrive.
        //
        // If a victim does go permanently silent, nobody applies that stream —
        // including the victim, which commits on its own echo. Everyone agrees on
        // "no damage". Under-damage, but CONSISTENT, which is the property that
        // matters and the one the ship criterion is written about.
        //
        // The residual cheat surface is handled by DETECTION instead, and the
        // guarantee is narrower than it first looks — state it precisely rather
        // than let the next reader assume more:
        //
        //   * DETECTED: a victim that goes WHOLLY silent. Liveness is tracked per
        //     ACTOR (_lastHeardServerTs), so this is an actor-level property.
        //   * NOT DETECTED: selective suppression. A victim with two concurrent
        //     streams — trivially reachable, since Decay routes every direct hit
        //     through the DoT path at 0.25s intervals — can publish stream A
        //     honestly while suppressing stream B, and A's verdicts keep B's
        //     observer quiet.
        //
        // Per-STREAM keying would not close that: one forged verdict per stream
        // disarms a per-stream detector too, for the same zero damage and zero
        // log, so it would buy one packet of friction in exchange for putting
        // per-stream correlation bookkeeping back into a coroutine that rounds 1
        // and 2 proved expensive to keep. If selective-suppression detection is
        // ever wanted, the sound place is an aggregate comparison (streams
        // scheduled by observers vs headers ever received per victim) reported to
        // the server, not a per-shadow timer that can only emit a log line.
        //
        // A log line cannot desynchronise anything, which is the whole reason
        // this is the entire extent of the mechanism.
        private const int SilenceReportMs = 1500;

        // A roster change (someone joined or left) may not have propagated to
        // us yet, so for a short window after one we refuse to honour block.
        // Conservative here is free — see the HonorBlock note in the header.
        private const float RosterQuarantineSeconds = 3f;

        // ── Capability: staged once, pre-join, never written in-room ───────

        /// <summary>Set by PoisonDotSchedulerPatch's Harmony cleanup only when the
        /// patch actually attached. Learning #83: a diagnostic — or in this case an
        /// entire authority — can silently fail to attach. Advertising an authority
        /// we cannot deliver would make every peer wait on verdicts we never send,
        /// manufacturing the exact ghost-HP bug this file exists to remove.</summary>
        internal static bool PatchesLive;

        private static bool _staged;
        private static bool _stageFailedPermanently;

        /// <summary>Stage the capability property BEFORE ever joining a room, so it
        /// rides the join operation itself. Called from Plugin.Awake (after Harmony
        /// patching, so PatchesLive is known) and retried from the persistent tick.
        ///
        /// The two state rules here are load-bearing:
        ///
        ///  * REFUSE while in a room. An in-room write is a network op that arrives
        ///    on peers at some later time — exactly the eventual-consistency hole
        ///    this design exists to avoid.
        ///  * Retry ONLY while Disconnected/PeerCreated. `!InRoom` is ALSO true
        ///    mid-join, and a merge landing after LoadBalancingClient snapshots
        ///    enterRoomParamsCache but before room entry would be present locally
        ///    and NEVER delivered to peers — a silently false-capable client, which
        ///    is the worst state this protocol can be in. Disconnected/PeerCreated
        ///    provably precede any connect.</summary>
        internal static void StageCapability(string source)
        {
            try
            {
                if (_staged || _stageFailedPermanently) return;
                if (!PatchesLive)
                {
                    _stageFailedPermanently = true;
                    Plugin.Log.LogError("[POISON-CAP] scheduler patch did NOT attach — "
                        + "authoritative poison disabled for this session (falling back to v1.35.5 behaviour)");
                    return;
                }

                if (PhotonNetwork.InRoom)
                {
                    Plugin.Log.LogError("[POISON-CAP] refusing to stage while in a room ("
                        + source + ") — an in-room write is the racy path this protocol forbids");
                    return;
                }

                ClientState st = PhotonNetwork.NetworkClientState;
                if (st != ClientState.Disconnected && st != ClientState.PeerCreated)
                    return;   // mid-connect: wait for a clean moment, do not merge now

                var local = PhotonNetwork.LocalPlayer;
                if (local == null) return;

                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable
                {
                    { CapabilityProp, CapabilityValue }
                });
                _staged = true;
                Plugin.Log.LogInfo("[POISON-CAP] staged " + CapabilityProp + "=" + CapabilityValue
                    + " pre-join (" + source + ", state=" + st + ")");
            }
            catch (Exception ex)
            {
                _stageFailedPermanently = true;
                Plugin.Log.LogError("[POISON-CAP] staging failed, authoritative poison disabled "
                    + "for this session: " + ex.Message);
            }
        }

        /// <summary>Withdraw the advertisement. Called when the compat check disables
        /// the mod, which happens after Awake has already staged it. Peers must stop
        /// treating us as an authority, or they will suppress their own simulation of
        /// our damage-over-time and wait for verdicts we will never send.</summary>
        internal static void RevokeCapability()
        {
            try
            {
                if (!_staged) return;
                _staged = false;
                _stageFailedPermanently = true;   // never re-stage this session
                var local = PhotonNetwork.LocalPlayer;
                if (local == null) return;
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable
                {
                    { CapabilityProp, 0 }
                });
                Plugin.Log.LogWarning("[POISON-CAP] revoked " + CapabilityProp
                    + " — mod disabled, falling back to vanilla poison entirely");
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[POISON-CAP] revoke failed: " + ex.Message); }
        }

        // Memoised per (room, actor). Actor numbers are per-room, so the cache
        // must be dropped whenever the room changes.
        private static string _capRoom = "";
        private static readonly Dictionary<int, bool> _capCache = new Dictionary<int, bool>();

        /// <summary>Does this view's OWNER speak the authoritative protocol?
        ///
        /// THE ONE INPUT that decides every client's protocol branch. It is a pure
        /// function of a property delivered with the owner's Player object, so every
        /// client — including the owner itself — computes the same answer at every
        /// instant at which it could act. The victim deliberately reads its OWN
        /// capability through this same accessor rather than a private bool, so
        /// "am I authoritative" and "is V authoritative" are literally the same read
        /// of the same delivered value.</summary>
        internal static bool CapableVictim(PhotonView view)
        {
            try
            {
                // If OUR scheduler patch did not attach we cannot participate at
                // all, so every victim must read as incapable to us. That is not a
                // semantic muddle — it is the only self-consistent answer: staging
                // is gated on the same flag, so peers already treat us as incapable,
                // and PoisonGhostPatch must fall through to its v1.35.5 behaviour
                // rather than deferring to a protocol we are not running. Without
                // this, a failed attach means we run vanilla's DoT loop AND apply
                // every committed verdict — 2x damage on this client.
                if (!PatchesLive) return false;
                // Same reasoning for the compat kill-switch. Plugin.modDisabled is
                // set from Update() when another plugin is detected, which is AFTER
                // Awake staged our capability — and modDisabled also stops the tick
                // that calls Hook(), so such a client would advertise authority,
                // suppress vanilla through the scheduler, and never subscribe to its
                // own commit path. Its own poison would then apply on every screen
                // but its own. Reading every victim as incapable puts us fully back
                // on vanilla; RevokeCapability() below stops peers waiting on us.
                if (Plugin.modDisabled) return false;
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return false;
                if (view == null) return false;
                var owner = view.Owner;
                if (owner == null) return false;

                string room = PhotonNetwork.CurrentRoom != null ? (PhotonNetwork.CurrentRoom.Name ?? "") : "";
                if (room != _capRoom) { _capRoom = room; _capCache.Clear(); }

                bool cached;
                if (_capCache.TryGetValue(owner.ActorNumber, out cached)) return cached;

                bool ok = false;
                var props = owner.CustomProperties;
                object v;
                if (props != null && props.TryGetValue(CapabilityProp, out v) && v is int)
                    ok = ((int)v) == CapabilityValue;

                _capCache[owner.ActorNumber] = ok;
                return ok;
            }
            catch { return false; }
        }

        // ── Roster awareness (victim-private, feeds HonorBlock only) ───────
        private static bool _sawIncapablePeer;
        private static float _lastRosterChange = -999f;
        private static string _rosterRoom = "";
        private static string _tickRoom = "";
        private static float _lastScan = -999f;
        private static int _lastRosterCount = -1;

        /// <summary>Per-frame upkeep, driven from the always-on persistent tick so no
        /// join path can forget it.
        ///
        /// Note carefully what does NOT happen here: the periodic re-scan must not
        /// stamp the roster quarantine. Stamping it every tick would hold
        /// HonorBlock() at false forever and silently disable the entire feature —
        /// the quarantine exists to cover the window after a roster CHANGE, not to
        /// be re-armed continuously.</summary>
        internal static void Tick()
        {
            try
            {
                StageCapability("tick");

                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode)
                {
                    // Edge-triggered, not every menu frame.
                    if (_tickRoom != "") ResetForRoomExit();
                    _tickRoom = "";
                    _lastRosterCount = -1;
                    return;
                }

                string room = PhotonNetwork.CurrentRoom != null ? (PhotonNetwork.CurrentRoom.Name ?? "") : "";
                if (room != _tickRoom)
                {
                    // Room-to-room without passing through the menu (rare, but a
                    // rejoin can look like this) — same reset, same reason.
                    if (_tickRoom != "") ResetForRoomExit();
                    _tickRoom = room;
                    _lastRosterCount = RawNonSpectatorCount();   // census basis: see ScanRoster (r8 find 2)
                    NoteRosterChange("room-change");
                    return;
                }

                if (Time.unscaledTime - _lastScan < 1f) return;
                _lastScan = Time.unscaledTime;

                int n = RawNonSpectatorCount();   // census basis: see ScanRoster (r8 find 2)
                if (n != _lastRosterCount)
                {
                    // Belt and braces: we also hook the room callbacks, but a
                    // missed callback must not leave us honouring block with an
                    // unpatched peer present.
                    _lastRosterCount = n;
                    NoteRosterChange("count-change");
                    return;
                }

                ScanRoster("periodic");
            }
            catch { }
        }

        /// <summary>Called from the room callbacks and the persistent tick. The
        /// incapable flag is STICKY for the room: a peer that appears briefly and
        /// leaves must not re-enable block honouring underneath a stream it already
        /// partially simulated.</summary>
        internal static void NoteRosterChange(string why)
        {
            try
            {
                string room = PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null
                    ? (PhotonNetwork.CurrentRoom.Name ?? "") : "";
                if (room != _rosterRoom)
                {
                    _rosterRoom = room;
                    _sawIncapablePeer = false;   // new room, fresh judgement
                    _capCache.Clear();
                    _lastSeq.Clear();
                }
                _lastRosterChange = Time.unscaledTime;
                ScanRoster(why);
            }
            catch { }
        }

        private static int RawNonSpectatorCount()
        {
            try
            {
                var list = PhotonNetwork.PlayerList;
                if (list == null) return 0;
                int n = 0;
                for (int i = 0; i < list.Length; i++)
                    if (list[i] != null && !RoomActors.IsSpectator(list[i])) n++;
                return n;
            }
            catch { return 0; }
        }

        private static List<Photon.Realtime.Player> RawNonSpectators()
        {
            var keep = new List<Photon.Realtime.Player>(4);
            try
            {
                var list = PhotonNetwork.PlayerList;
                if (list == null) return keep;
                for (int i = 0; i < list.Length; i++)
                    if (list[i] != null && !RoomActors.IsSpectator(list[i])) keep.Add(list[i]);
            }
            catch { }
            return keep;
        }

        private static void ScanRoster(string why)
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return;
                // Census basis (Aug 10 r8 find 2, the GrowSync Quorum rule):
                // raw PhotonNetwork.PlayerList filtered ONLY by the
                // replicated cr_spec role prop. RoomActors.ActiveFighters was
                // used here and REJECTED — its frozen-roster filter is LOCAL
                // state, and roster freezing is legally divergent between
                // seats, so an unmarked intruder was excluded on one seat and
                // included on the other: the sticky incapable flag (and with
                // it victim-side block honouring) then split across clients,
                // directly changing fighter damage. With the raw list every
                // seat counts the same actors from the same replicated data;
                // an unmarked intruder reads INCAPABLE on every seat
                // symmetrically — fail-closed, rule-symmetric — until the
                // master's close removes it. Declared spectators (cr_spec,
                // replicated) are excluded identically everywhere; the sticky
                // flag stays deliberately sticky.
                var list = RawNonSpectators();
                if (list == null || list.Count == 0) return;

                bool anyIncapable = false;
                var detail = new List<string>();
                foreach (var p in list)
                {
                    bool ok = false;
                    if (p != null && p.CustomProperties != null)
                    {
                        object v;
                        if (p.CustomProperties.TryGetValue(CapabilityProp, out v) && v is int)
                            ok = ((int)v) == CapabilityValue;
                    }
                    if (!ok) anyIncapable = true;
                    detail.Add((p != null ? p.ActorNumber : -1) + ":" + (ok ? "y" : "n"));
                }

                if (anyIncapable && !_sawIncapablePeer)
                {
                    _sawIncapablePeer = true;
                    // §7.1 (Codex mod-r1 F3): _rosterRoom stays raw for the
                    // room-change comparison above; only the LOG masks it on
                    // the broadcast seat — this line fires while SPECTATING
                    // whenever a watched fighter lacks the capability, and the
                    // room name is a join credential.
                    string roomForLog = BroadcastMode.IsBroadcastIdentity ? BroadcastMode.SafeRoomDesc() : _rosterRoom;
                    Plugin.Log.LogInfo("[POISON-CAP] room=" + roomForLog + " incapable peer present ("
                        + why + ") caps=" + string.Join(",", detail.ToArray()));
                }
            }
            catch { }
        }

        /// <summary>Would an INCAPABLE peer in this room be forcing ignoreBlock?
        ///
        /// Deliberately NOT VanillaFixSupport.GameplayScope(), even though that is
        /// the predicate PoisonGhostPatch itself uses. GameplayScope routes through
        /// CompetitiveRoomDetect.IsCompetitiveRoom(), whose ffa_ arm additionally
        /// requires FfaMode.EngineActive() — LOCAL state. Two victims in one room
        /// could then answer differently, which would make them honour block
        /// differently: not a health divergence (only the victim reads this), but a
        /// fairness inconsistency. The question here is purely about the ROOM'S
        /// IDENTITY, which every client reads identically, so test that directly.</summary>
        private static bool PeerWouldForceBypass()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return false;
                var props = PhotonNetwork.CurrentRoom.CustomProperties;
                if (props != null && props.ContainsKey("cr_ff")) return true;
                string n = PhotonNetwork.CurrentRoom.Name ?? "";
                return n.StartsWith("ranked_") || n.StartsWith("team_") || n.StartsWith("sct-")
                    || n.StartsWith("ovt_") || n.StartsWith("ffa_");
            }
            catch { return false; }
        }

        /// <summary>Victim-private. Consumed by nobody else — see the header note on
        /// why its conservative direction is free.</summary>
        private static bool HonorBlock()
        {
            try
            {
                if (Time.unscaledTime - _lastRosterChange < RosterQuarantineSeconds) return false;
                if (!_sawIncapablePeer) return true;         // everyone speaks the protocol
                return !PeerWouldForceBypass();             // private room: peer is block-aware
            }
            catch { return false; }
        }

        // ── Per-stream state ──────────────────────────────────────────────
        private static int _nextStream = 1;
        private static int _nextSeq = 1;
        private static bool _hooked;

        // Receiver-side high-water dedup, per SENDER. Same-sender reliable
        // channel-0 delivery is FIFO, so one int per sender replaces the old
        // unbounded HashSet + bit-packed key entirely.
        private static readonly Dictionary<int, int> _lastSeq = new Dictionary<int, int>();

        // Receiver-side stream records, keyed (viewId, streamId).
        private sealed class StreamRec
        {
            public Vector2 Slice;
            public Color Color;
            public int AttackerId;
            public bool Lethal;
            public byte DamageSource;
            public int Accepted;
            public int Blocked;
            public int Applied;
            // Creation order, for the spectator-seat eviction below.
            public int Seq;
        }
        private static readonly Dictionary<long, StreamRec> _streams = new Dictionary<long, StreamRec>();

        // Spectator seats never prune records at Revive (the fence is deleted
        // — see ResetForView), so the table has room lifetime there. Bound it
        // (r2 find 4): past the cap, evict the OLDEST streams. A live stream
        // is never near the oldest at this size — poison/Decay streams run
        // seconds, the cap holds hundreds — so eviction only ever drops
        // long-completed records. Fighter seats prune at Revive and stay far
        // below the cap; the eviction simply never fires for them.
        private const int STREAM_RECORD_CAP = 512;
        private static int _recSeq;

        private static void EvictOldestStreams()
        {
            // Spectator seats ONLY (r3 find 2): a fighter seat evicting a
            // live stream would drop real damage ticks — and fighters prune
            // at Revive anyway, so the cap has no job there.
            if (!RoomActors.LocalIsSpectator) return;
            if (_streams.Count <= STREAM_RECORD_CAP) return;
            var keys = new List<long>(_streams.Keys);
            keys.Sort((a, b) => _streams[a].Seq.CompareTo(_streams[b].Seq));
            int drop = _streams.Count - (STREAM_RECORD_CAP * 3 / 4);
            for (int i = 0; i < drop && i < keys.Count; i++) _streams.Remove(keys[i]);
        }

        // Last time (server clock) we heard ANY verdict from this actor.
        private static readonly Dictionary<int, int> _lastHeardServerTs = new Dictionary<int, int>();

        // Revive fence: verdicts whose stream began before the victim's most
        // recent revive are dropped. Defaults to "unset" so a late joiner drops
        // nothing — that absence is exactly the gap that made the old per-life
        // counter unusable.
        private static readonly Dictionary<int, int> _reviveServerTs = new Dictionary<int, int>();

        private static long StreamKey(int viewId, int streamId)
            => ((long)viewId << 32) ^ (uint)streamId;

        /// <summary>Quantise the stream total so the authority, every shadow and the
        /// audio loop all enumerate the SAME number of ticks. RayHitPoison passes
        /// `damage * transform.forward / count` and transform.forward can differ by
        /// an ULP between replicas — enough to flip the final
        /// `while (damageDealt &lt; damageToDeal)` iteration. One helper, so the three
        /// call sites cannot drift apart.</summary>
        internal static float Quantise(float magnitude)
            => Mathf.Round(magnitude * 1000f) / 1000f;

        /// <summary>PhotonNetwork.ServerTimestamp is an int of milliseconds and WRAPS
        /// roughly every 24.8 days. Every comparison must be unchecked subtraction —
        /// `a > b` is wrong across the wrap and would fence off every verdict for
        /// about as long as it takes someone to notice.</summary>
        private static bool ServerTsAfter(int a, int b) { unchecked { return (a - b) > 0; } }

        /// <summary>Sequence-number ordering. Same unchecked-subtraction shape as
        /// ServerTsAfter and for the same reason (a monotonic counter that would wrap
        /// at int.MaxValue), but kept as a separate name because a seq is not a
        /// timestamp and reading `ServerTsAfter(seq, last)` at the call site invited
        /// exactly that confusion.</summary>
        private static bool SeqAfter(int a, int b) { unchecked { return (a - b) > 0; } }

        internal static void ResetForView(int viewId)
        {
            try
            {
                // Aug 11 spectator fix (playtest item 2): a spectator's Revive
                // timeline is DECOUPLED from the victim's — our Move-tail
                // Revive runs LATE (downstream of the map-settle spin), while
                // the victim is still publishing the round's live stream.
                // Stamping "now" and deleting every record here silently
                // dropped that stream's whole tail (and the Revive itself had
                // just reset health to max), which is why poison/Decay never
                // moved health bars for spectators. On a spectator seat the
                // revive fence is DELETED outright — no stamp, no removal
                // (records clear on room exit). Codex r1 killed the tempting
                // middle grounds: fencing on OUR call-in receipt time races
                // streams a fighter starts inside our dispatch lag (their
                // start ts predates our receipt ts), and treating any local
                // Revive as the boundary preserves/deletes wrongly for
                // Phoenix (Revive(false)) and card-apply revives. With no
                // fence the worst case is bounded and tiny: a victim's
                // authority coroutine dies at its own death/revive, so the
                // only stale arrivals are ticks already in flight (~1-2
                // slices within one RTT) — a couple of HP briefly shaved off
                // a just-healed bar, versus whole live streams wrongly
                // killed. Display seat, display-sized error.
                if (RoomActors.LocalIsSpectator)
                {
                    // Eaten-verdict evidence: after bug 216, observer-local
                    // lifecycle bits are advisory and cannot create this gap.
                    // A future hit means component resolution or an exception
                    // still prevented the direct write. Cap keeps repeats cheap.
                    foreach (var kv in _streams)
                    {
                        if ((int)(kv.Key >> 32) != viewId) continue;
                        if (kv.Value.Accepted > kv.Value.Applied)
                            VanillaFixSupport.DiagLimited("spect-eaten",
                                "[POISON-SYNC] SPECT-EATEN v" + viewId + " accepted="
                                + kv.Value.Accepted + " applied=" + kv.Value.Applied, 20);
                    }
                    return;
                }
                _reviveServerTs[viewId] = PhotonNetwork.ServerTimestamp;
                var dead = new List<long>();
                foreach (var kv in _streams)
                    if ((int)(kv.Key >> 32) == viewId) dead.Add(kv.Key);
                foreach (var k in dead) _streams.Remove(k);
            }
            catch { }
        }

        /// <summary>Drop every scrap of per-room state. Actor numbers and ViewIDs are
        /// per-room and BOTH get recycled, so carrying any of this across a room
        /// boundary means attributing one person's capability, sequence numbers or
        /// liveness to a different person. Called on the room-EXIT edge — keying the
        /// reset on the room NAME is not enough, because ROUNDS room codes and
        /// mod-issued names can repeat.</summary>
        private static void ResetForRoomExit()
        {
            try
            {
                _capCache.Clear();
                _capRoom = "";
                _lastSeq.Clear();
                _streams.Clear();
                _lastHeardServerTs.Clear();
                _reviveServerTs.Clear();
                _sawIncapablePeer = false;
                _rosterRoom = "";
                _lastRosterChange = -999f;
                _recSeq = 0;
            }
            catch { }
        }

        // ── Tick sound ────────────────────────────────────────────────────
        // Sonigon (SoundEvent / SoundManager) is deliberately NOT referenced by
        // the csproj — same house rule as UnityEngine.UI and TMPro — so the
        // SoundEvent stays an `object` and is played by reflection.
        //
        // Audio is deliberately NOT authoritative and never rides the commit
        // path. Vanilla plays the sound BEFORE attempting the blockable damage,
        // so a blocked tick still ticks audibly; keeping audio local preserves
        // that for free, and avoids three bugs a cached-per-victim SoundEvent
        // caused in the first draft (overlapping poison and Decay streams
        // overwriting each other, blocked ticks falling silent, and a recycled
        // ViewID replaying a previous occupant's sound).
        private static System.Reflection.MethodInfo _playMi;
        private static object _soundManager;

        private static void PlayTick(object sound, Transform at)
        {
            try
            {
                if (sound == null || at == null) return;
                if (_playMi == null)
                {
                    var smType = AccessTools.TypeByName("Sonigon.SoundManager");
                    if (smType == null) return;
                    var instProp = smType.GetProperty("Instance",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
                    _soundManager = instProp != null ? instProp.GetValue(null) : null;
                    foreach (var mi in smType.GetMethods())
                    {
                        if (mi.Name != "Play") continue;
                        var ps = mi.GetParameters();
                        if (ps.Length == 2 && ps[1].ParameterType == typeof(Transform)) { _playMi = mi; break; }
                    }
                }
                if (_playMi == null || _soundManager == null) return;
                _playMi.Invoke(_soundManager, new object[] { sound, at });
            }
            catch { }
        }

        /// <summary>Local, non-authoritative tick audio — one per replica, same
        /// cadence and same total count as vanilla.</summary>
        internal static IEnumerator LocalTickSound(DamageOverTime host, CharacterData data,
                                                   object sound, float magnitude,
                                                   float total, float interval)
        {
            if (sound == null || interval <= 0f || total <= 0f) yield break;
            // Mirrors vanilla's float accumulation rather than CeilToInt(total /
            // interval): repeated addition of dpt can run one iteration more
            // than the division suggests, so the tidier arithmetic would drop
            // the last tick's sound on some damage values.
            float dealt = 0f;
            float dpt = magnitude / total * interval;
            if (dpt <= 0f) yield break;
            while (dealt < magnitude)
            {
                if (host == null || data == null) yield break;
                dealt += dpt;
                if (data.isPlaying && !data.dead) PlayTick(sound, host.transform);
                yield return new WaitForSeconds(interval / TimeHandler.timeScale);
            }
        }

        // ── Photon event wiring ───────────────────────────────────────────
        internal static void Hook()
        {
            if (_hooked) return;
            try
            {
                PhotonNetwork.NetworkingClient.EventReceived += OnEvent;
                _hooked = true;
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[POISON-SYNC] hook failed: " + ex.Message); }
        }

        private static bool Raise(object[] payload)
        {
            try
            {
                return PhotonNetwork.RaiseEvent(
                    EventCode, payload,
                    // Receivers.All so the AUTHORITY also receives its own event
                    // and commits down the same path as everyone else. Applying
                    // locally at send time instead would give the authority a
                    // different code path, a different ordering, and a second
                    // application when the echo arrives. (Note this is NOT the
                    // same as PUN's RpcTarget.All, which executes locally on the
                    // sender about one round-trip early — a trap next door.)
                    new RaiseEventOptions { Receivers = ReceiverGroup.All },
                    SendOptions.SendReliable);
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[POISON-AUTH] raise threw: " + ex.Message);
                return false;
            }
        }

        // Wire format. TYPE 0 carries the stream header AND tick 0's verdict, so
        // there is no interval between "a stream exists" and "tick 0 is decided"
        // — which is what gives the watchdog its full margin.
        //
        //  TYPE 0: 0, PROTO, viewId, streamId, startTs, sliceX, sliceY,
        //          colR, colG, colB, attackerPlayerId, lethal, damageSource,
        //          blocked0, seq                                      (15)
        //  TYPE 1: 1, PROTO, viewId, streamId, tickIndex, blocked, seq  (7)
        //
        // `position` and `damagingWeapon` are deliberately absent: verified
        // against the decompile, HealthHandler.DoDamage's body never reads
        // either. attackerPlayerId STAYS — it drives DealtDamage, i.e. lifesteal,
        // refreshOnDamage, sinceDealtDamage and lastDamagedPlayer. Real gameplay.
        private const byte TypeHeader = 0;
        private const byte TypeTick = 1;

        private static void OnEvent(EventData e)
        {
            if (e.Code != EventCode) return;
            try
            {
                var a = e.CustomData as object[];
                if (a == null || a.Length < 7) return;
                if (!(a[0] is byte) || !(a[1] is byte)) return;
                if ((byte)a[1] != Protocol) return;

                byte kind = (byte)a[0];
                // Length must be validated for THIS kind before any indexed read
                // below — the seq read alone is at index 14 on a header.
                if (kind == TypeHeader) { if (a.Length < 15) return; }
                else if (kind == TypeTick) { if (a.Length < 7) return; }
                else return;

                int viewId = (int)a[2];
                int streamId = (int)a[3];

                var view = PhotonView.Find(viewId);
                if (view == null) return;

                // Only the victim may speak for the victim. Without this, any
                // client could forge ticks against anyone.
                if (view.Owner == null || view.Owner.ActorNumber != e.Sender)
                {
                    Plugin.Log.LogWarning("[POISON-SYNC] REJECT forged tick: sender=" + e.Sender
                        + " owner=" + (view.Owner != null ? view.Owner.ActorNumber : -1) + " view=" + viewId);
                    return;
                }

                // Fail closed on any capability disagreement. By the atomicity
                // theorem a sender that passes the ownership guard above is read as
                // capable by every receiver, so in the healthy case this is a
                // provable no-op — it exists so that a FUTURE non-atomic read (or a
                // client whose own scheduler failed to attach, which CapableVictim
                // now reports as incapable) drops verdicts instead of applying them
                // on top of a vanilla loop it is also running.
                if (!CapableVictim(view)) return;

                int seq = (int)a[kind == TypeHeader ? 14 : 6];
                int last;
                if (_lastSeq.TryGetValue(e.Sender, out last) && !SeqAfter(seq, last)) return;
                _lastSeq[e.Sender] = seq;

                long key = StreamKey(viewId, streamId);
                StreamRec rec;

                if (kind == TypeHeader)
                {
                    int startTs = (int)a[4];

                    // Revive fence. A verdict raised just before a death can
                    // arrive just after the revive and would otherwise damage a
                    // freshly revived player at full health. One room-wide clock,
                    // seconds of margin (death -> point animation -> MapTransition
                    // -> Revive), and unset by default so a late joiner drops
                    // nothing.
                    int reviveTs;
                    if (_reviveServerTs.TryGetValue(viewId, out reviveTs) && ServerTsAfter(reviveTs, startTs))
                    {
                        Plugin.Log.LogInfo("[POISON-SYNC] revive-fence drop v" + viewId + "/s" + streamId);
                        return;
                    }

                    _lastHeardServerTs[e.Sender] = PhotonNetwork.ServerTimestamp;
                    rec = new StreamRec
                    {
                        Slice = new Vector2((float)a[5], (float)a[6]),
                        Color = new Color((float)a[7], (float)a[8], (float)a[9], 1f),
                        AttackerId = (int)a[10],
                        Lethal = (bool)a[11],
                        DamageSource = (byte)a[12],
                        Seq = ++_recSeq,
                    };
                    _streams[key] = rec;
                    EvictOldestStreams();
                    Apply(view, rec, (bool)a[13], viewId, streamId, 0);
                    return;
                }

                if (!_streams.TryGetValue(key, out rec))
                {
                    // Reliable delivery means this is not a lost header — it was
                    // revive-fenced, orphan-fenced or deduped, so this stream is
                    // deliberately not ours to apply.
                    return;
                }
                _lastHeardServerTs[e.Sender] = PhotonNetwork.ServerTimestamp;
                Apply(view, rec, (bool)a[5], viewId, streamId, (int)a[4]);
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[POISON-SYNC] apply failed: " + ex.Message); }
        }

        private static void Apply(PhotonView view, StreamRec rec, bool blocked,
                                  int viewId, int streamId, int tick)
        {
            if (blocked) { rec.Blocked++; return; }   // consumed, no damage — the vanilla semantic
            rec.Accepted++;

            var hh = view.GetComponent<HealthHandler>();
            if (hh == null)
            {
                // Permanent single-client under-damage with no retry — a failure
                // the pre-protocol baseline structurally could not have. Never
                // swallow this quietly.
                Plugin.Log.LogError("[POISON-SYNC] DROPPED tick v" + viewId + "/s" + streamId
                    + "/t" + tick + ": no HealthHandler — this client will read low on damage");
                return;
            }

            // Aug 11 spectator fix (playtest item 2, r2 HIGH): a spectator
            // seat NEVER calls DoDamage — always the direct display subtract.
            // DoDamage broadcasts the ownerless RPCA_Die(All) from ANY replica
            // whose local health crosses zero (the file-header hazard), and
            // with the revive fence deleted, stale in-flight ticks landing
            // after our belated Revive could accumulate a real fighter's
            // death FROM THE OBSERVER SEAT. Bypassing DoDamage entirely makes
            // that structurally impossible: health is clamped at 1 hp, so a
            // kill is only ever rendered by the fighters' own death RPC. It
            // also fixes the reported symptom — DoDamage's silent gates
            // (!isPlaying during our lagging transitions) ate every verdict
            // and the bar never moved. Cost on this seat only: no damage
            // flash. Attacker LIFESTEAL is rendered explicitly below (bug
            // 202 — the original "no attacker-lifesteal" cost proved
            // unacceptable: a Leech/Parasite build read as pinned at 1 HP).
            Player attacker = null;
            try
            {
                if (rec.AttackerId >= 0 && PlayerManager.instance != null)
                    foreach (var p in PlayerManager.instance.players)
                        if (p != null && p.PlayerID == rec.AttackerId) { attacker = p; break; }
            }
            catch { }

            if (RoomActors.LocalIsSpectator)
            {
                try
                {
                    var cds = view.GetComponent<CharacterData>();
                    if (cds != null)
                    {
                        // Bug 216: an accepted verdict is authenticated above
                        // as coming from THIS victim's owner. Do not veto it on
                        // the observer replica's dead/isRespawning bits: those
                        // bits are local lifecycle state, so one spectator
                        // replica can miss/lag its Revive while the real fighter
                        // is alive and publishing. That produced the exact
                        // per-victim accepted>applied split in SPECT-EATEN.
                        // AuthoritativeDot stops publishing from a dead/non-
                        // playing victim and death/revive stop its host
                        // coroutine; this seat's stale flags add no authority.
                        // The direct subtract plus 1-HP floor remains the #338
                        // structural kill fence — never route this through
                        // DoDamage and never let this display path reach zero.
                        if (cds.dead || hh.isRespawning)
                            VanillaFixSupport.DiagLimited(
                                "spect-local-lifecycle-ignored",
                                "[POISON-SYNC] SPECT-LOCAL-LIFECYCLE v" + viewId
                                + "/s" + streamId + "/t" + tick
                                + " dead=" + (cds.dead ? 1 : 0)
                                + " respawning=" + (hh.isRespawning ? 1 : 0)
                                + " — authoritative display verdict applied",
                                20);

                        float nh = cds.health - rec.Slice.magnitude;
                        cds.health = nh < 1f ? 1f : nh;
                        rec.Applied++;
                        // Bug 202: render the ATTACKER's LIFESTEAL for this
                        // tick — and ONLY lifesteal. Fighter seats get the
                        // full DealtDamage chain via DoDamage, so a
                        // Leech/Parasite build healed on every fighter's
                        // screen while this seat (which deliberately bypasses
                        // DoDamage — see the header hazard) rendered only the
                        // down-ticks: the holder read as pinned at 1 HP all
                        // game. Invoking the FULL DealtDamage chain here was
                        // REJECTED in cross-review (Codex, Aug 11) and
                        // RE-AFFIRMED at the bug-216 fix (Aug 14 — an author
                        // pass tried to "restore" the full chain from a
                        // mis-stated brief; this comment is the record of why
                        // not): it also walks arbitrary DealtDamageEffects,
                        // and SpawnObjectOnDealDamage keeps per-seat THRESHOLD
                        // state before spawning objects and dealing more
                        // damage — a mid-game-join observer's accumulator is
                        // never in sync, so its spawns would diverge, the
                        // exact class this protocol exists to remove. The two
                        // vanilla heal mechanisms are the stats.lifeSteal
                        // float and the LifeSteal DealtDamageEffect
                        // (CharacterStatModifiers.cs:129-131, LifeSteal.cs)
                        // — render both, heal-only. Heal only ADDS health
                        // (#338 untouched) and vanilla gates lifesteal on
                        // !selfDamage, mirrored here.
                        try
                        {
                            var victim = cds.player;
                            if (attacker != null && victim != null
                                && !ReferenceEquals(attacker, victim)
                                && attacker.data != null && attacker.data.stats != null)
                            {
                                float healMag = rec.Slice.magnitude
                                    * attacker.data.stats.lifeSteal;
                                try
                                {
                                    foreach (var lsc in attacker.GetComponentsInChildren<LifeSteal>())
                                        if (lsc != null)
                                            healMag += rec.Slice.magnitude * lsc.multiplier;
                                }
                                catch { }
                                if (healMag > 0f && attacker.data.healthHandler != null)
                                    attacker.data.healthHandler.Heal(healMag);
                            }
                        }
                        catch { }
                    }
                }
                catch { }
                return;
            }

            float hpBefore = 0f;
            try { var cd = view.GetComponent<CharacterData>(); if (cd != null) hpBefore = cd.health; } catch { }

            // ignoreBlock: true — the block decision was already made, once, by
            // the only client entitled to make it. Re-checking here would
            // reintroduce the per-replica disagreement this file exists to remove.
            hh.DoDamage(rec.Slice, Vector2.zero, rec.Color, null, attacker,
                        healthRemoval: true, lethal: rec.Lethal, ignoreBlock: true,
                        damageSource: (HealthHandler.DamageSource)rec.DamageSource);

            // Count APPLIED only when HP actually moved. DoDamage silently no-ops
            // while dead/respawning, and a tally that counts the CALL rather than
            // the EFFECT reads as agreement when there is none.
            try
            {
                var cd2 = view.GetComponent<CharacterData>();
                if (cd2 != null && cd2.health < hpBefore - 0.0001f) rec.Applied++;
            }
            catch { }
        }

        /// <summary>Vanilla's float loop exactly (no rounded tick count, no clamped
        /// final tick) so totals and durations are unchanged. The only difference is
        /// that the block verdict is decided HERE, once, and published — instead of
        /// being re-derived by every replica against its own copy of the block
        /// window.</summary>
        internal static IEnumerator AuthoritativeDot(
            DamageOverTime host, CharacterData data, PhotonView view,
            Vector2 damage, float time, float interval, Color color,
            Player damagingPlayer, bool lethal, int damageSource)
        {
            int stream = _nextStream++;
            int viewId = view.ViewID;
            int attackerId = damagingPlayer != null ? damagingPlayer.PlayerID : -1;

            // STREAM START, captured before the loop and before any raise — NOT the
            // publish time. Load-bearing for the observer's orphan fence: a victim
            // that stalls is precisely the case that trips a watchdog, and a
            // publish-time stamp on the late header would fall AFTER the observer
            // gave up and defeat the fence entirely.
            int streamStartTs = PhotonNetwork.ServerTimestamp;

            float damageToDeal = Quantise(damage.magnitude);
            float dpt = damageToDeal / time * interval;
            if (dpt <= 0f) yield break;

            Vector2 slice = damage.normalized * dpt;
            float damageDealt = 0f;
            int tick = 0, blockedCount = 0, failedSends = 0;
            bool honor = HonorBlock();

            while (damageDealt < damageToDeal)
            {
                if (host == null || data == null || view == null) yield break;
                // Narrow the emit-then-die race to sub-frame. Receivers also
                // no-op via DoDamage's own guard, but not emitting is cheaper.
                if (data.dead || !data.isPlaying) yield break;

                damageDealt += dpt;

                bool blocked = false;
                float sinceBlock = -1f;
                try
                {
                    var block = data.block;
                    if (block != null)
                    {
                        sinceBlock = block.sinceBlock;
                        blocked = block.IsBlocking() && honor;
                    }
                }
                catch { }
                if (blocked) blockedCount++;

                bool sent;
                if (tick == 0)
                {
                    sent = Raise(new object[]
                    {
                        TypeHeader, Protocol, viewId, stream, streamStartTs,
                        slice.x, slice.y, color.r, color.g, color.b,
                        attackerId, lethal, (byte)damageSource, blocked, _nextSeq++
                    });
                }
                else
                {
                    sent = Raise(new object[]
                    {
                        TypeTick, Protocol, viewId, stream, tick, blocked, _nextSeq++
                    });
                }

                if (!sent)
                {
                    // RaiseEvent can return false WITHOUT throwing. The tick is
                    // already consumed and the event is the sole commit path, so
                    // a dropped send is consistent under-damage for EVERYONE
                    // including us. Log it loudly; NEVER fall back to applying
                    // locally, which would damage only this client and recreate
                    // the divergence this whole design exists to remove.
                    failedSends++;
                    Plugin.Log.LogWarning("[POISON-AUTH] SEND FAILED v" + viewId + "/s" + stream
                        + "/t" + tick + " — tick lost for everyone");
                }
                if (blocked)
                    Plugin.Log.LogInfo("[POISON-AUTH] BLOCK v" + viewId + "/s" + stream + "/t" + tick
                        + " sinceBlock=" + sinceBlock.ToString("0.000") + " dmg=" + dpt.ToString("0.00"));

                tick++;
                yield return new WaitForSeconds(interval / TimeHandler.timeScale);
            }

            StreamRec rec;
            _streams.TryGetValue(StreamKey(viewId, stream), out rec);
            Plugin.Log.LogInfo("[POISON-SYNC] COMPLETE v" + viewId + "/s" + stream
                + " honor=" + honor + " sent=" + tick + " blocked=" + blockedCount
                + " failedSends=" + failedSends
                + " recvAccepted=" + (rec != null ? rec.Accepted : -1)
                + " recvBlocked=" + (rec != null ? rec.Blocked : -1)
                + " hpApplied=" + (rec != null ? rec.Applied : -1));
        }

        /// <summary>A replica's PURE OBSERVER for the victim's stream. It applies
        /// NOTHING and it can apply nothing — the committed events are the sole
        /// commit path, which is what makes every client agree by construction.
        ///
        /// Its only job is to notice a capable victim that produces no verdicts at
        /// all and say so once, for the anti-cheat pipeline. A log line cannot
        /// desynchronise anyone, which is exactly why this is the whole of it:
        /// every version of this coroutine that also APPLIED damage was a health
        /// divergence bug (see the SilenceReportMs note at the top of the file).
        ///
        /// It exists as a coroutine rather than a timer because vanilla's RPCA_Die,
        /// RPCA_Die_Phoenix and Revive all call dot.StopAllCoroutines() on the host,
        /// so a stream that legitimately ends early takes its observer with it and
        /// cannot produce a false report.</summary>
        // ── Round-boundary orphan window (bug 221, review-round-1 shape) ──
        // OPENED by StaleProjectileSweepPatch.Schedule (point-over RPC +
        // MovePlayers, the two boundary signals every mode fires — FFA's
        // prefix replaces RPCA_NextRound's body but postfixes still run,
        // #352) with a CEILING, and CLOSED ~1s after the battle actually
        // resumes (GameStateWatcher's battleOngoing rising edge). Review r1
        // killed the flat-window draft: battle can resume ~2s after
        // MovePlayers, so a constant long window suppressed up to ~2.6s of
        // genuine combat evidence, while a short one re-opens the false
        // accusations. The resume edge is the only correct end; the ceiling
        // exists solely so a mode/path that never flips battleOngoing cannot
        // wedge the window open.
        // A DOT stream that ARMS inside the window is a boundary orphan: a
        // leftover hit landing after the revives, which the victim's
        // authority will never honor (its own copy of the bullet never hit,
        // or its publisher gate is closed during the transition).
        private static float _boundaryWindowUntil = -999f;
        private const float BoundaryOrphanCeilingSec = 6f;
        private const float PostResumeGraceSec = 1f;
        // Monotonic boundary counter (bug 225 follow-up): the arming-time
        // window below cannot see a stream that armed in live combat and was
        // then orphaned by the NEXT boundary (the victim's revive kills its
        // publisher mid-stream) — 4 of bug-225's 18 accusations fired during
        // the pick phase for exactly that shape. ShadowDot captures this
        // counter at arming and reports only if no boundary intervened.
        private static int _boundaryGen;
        internal static int BoundaryGen => _boundaryGen;
        internal static void NoteRoundBoundary()
        {
            // ACCEPTED RESIDUAL (review r2 LOW): FFA SPECTATOR seats suppress
            // both engines that flip battleOngoing, so on that one seat the
            // window always runs to the ceiling and early-combat silence
            // telemetry is lost. The fighters' seats — the ones whose reports
            // the anti-cheat pipeline actually needs — are unaffected, and a
            // spectator's shadow report is redundant with theirs.
            _boundaryGen++;
            float until = Time.realtimeSinceStartup + BoundaryOrphanCeilingSec;
            if (until > _boundaryWindowUntil) _boundaryWindowUntil = until;
        }
        internal static void NoteBattleResumed()
        {
            // TIGHTEN only — a resume edge must never extend a window that
            // is already closed or closing sooner.
            float until = Time.realtimeSinceStartup + PostResumeGraceSec;
            if (until < _boundaryWindowUntil) _boundaryWindowUntil = until;
        }
        internal static bool InBoundaryOrphanWindow()
            => Time.realtimeSinceStartup < _boundaryWindowUntil;

        internal static IEnumerator ShadowDot(
            DamageOverTime host, CharacterData data, PhotonView view,
            Vector2 damage, float time, float interval)
        {
            int viewId = view.ViewID;
            int actor = view.Owner != null ? view.Owner.ActorNumber : -1;
            int anchor = PhotonNetwork.ServerTimestamp;
            int boundaryGenAtArm = _boundaryGen;

            // Bug 221 ("knockback but no damage, both clients"): all three
            // production [POISON-SILENT] events sat directly on point
            // transitions, victim identical, PlayerDied adjacent. A stream
            // armed in the boundary window cannot produce a TRUE silence
            // report — the victim's revive killed any real stream it had
            // (this shadow inherits that cleanup only for streams that
            // existed BEFORE the revive), so an orphan's silence is
            // expected and its withheld ticks are vanilla-correct (a DOT
            // cancelled at the boundary deals nothing in vanilla either).
            // Accusing "possible modified client" here was a false
            // positive. Cost: streams armed within ~1s after the battle
            // resumes also skip the report (the resume edge closes the
            // window; a 6s ceiling covers any path with no edge) —
            // acceptable for an anti-cheat telemetry line; genuine
            // mid-battle silence keeps the full accusation path.
            if (InBoundaryOrphanWindow())
            {
                VanillaFixSupport.DiagLimited(
                    "poison-boundary-orphan",
                    "[POISON-BOUNDARY] stream on view=" + viewId
                    + " armed inside the round-boundary window — silence expected, not reported",
                    10);
                yield break;
            }

            float damageToDeal = Quantise(damage.magnitude);
            float dpt = damageToDeal / time * interval;
            if (dpt <= 0f) yield break;

            float damageDealt = 0f;
            bool reported = false;

            while (damageDealt < damageToDeal)
            {
                if (host == null || data == null || view == null) yield break;
                damageDealt += dpt;

                if (!reported)
                {
                    int heard;
                    bool heardSince = _lastHeardServerTs.TryGetValue(actor, out heard)
                                      && ServerTsAfter(heard, anchor);
                    if (!heardSince
                        && ServerTsAfter(PhotonNetwork.ServerTimestamp, unchecked(anchor + SilenceReportMs)))
                    {
                        reported = true;
                        if (boundaryGenAtArm != _boundaryGen)
                        {
                            // A round boundary crossed this stream AFTER it
                            // armed: the victim's publisher was revive-killed
                            // mid-stream (vanilla), so its silence is expected
                            // and the withheld remainder is vanilla-correct —
                            // 4 of bug-225's 18 accusations were exactly this
                            // shape (armed in the final ~1.5s of a point,
                            // reported during the pick phase). The arming-time
                            // window above cannot see this case by definition;
                            // this generation check closes it from the other
                            // side. Genuine mid-battle silence (no boundary
                            // between arming and report) still accuses.
                            VanillaFixSupport.DiagLimited(
                                "poison-boundary-orphan",
                                "[POISON-BOUNDARY] stream on view=" + viewId
                                + " crossed a round boundary after arming — silence expected, not reported",
                                10);
                        }
                        else
                        {
                            Plugin.Log.LogWarning("[POISON-SILENT] capable victim view=" + viewId
                                + " actor=" + actor + " has published no verdict " + SilenceReportMs
                                + "ms into a damage-over-time stream — its damage is not being applied "
                                + "on ANY client. Expected only on a severe client stall; if it repeats "
                                + "for one player, treat as a possible modified client.");
                        }
                    }
                }

                yield return new WaitForSeconds(interval / TimeHandler.timeScale);
            }
        }
    }

    /// <summary>Revive is where health is re-synchronised across every client
    /// anyway, so it is the natural reset point for all per-stream state. It fires
    /// on every client for every player at every round and game start, via
    /// PlayerManager.RevivePlayers() and PlayerManager.Move.</summary>
    [HarmonyPatch(typeof(HealthHandler), "Revive")]
    internal static class PoisonReviveFencePatch
    {
        [HarmonyPostfix]
        private static void AfterRevive(HealthHandler __instance)
        {
            try
            {
                var v = __instance != null ? __instance.GetComponent<PhotonView>() : null;
                if (v != null) PoisonSync.ResetForView(v.ViewID);
            }
            catch { }
        }
    }

    /// <summary>The single scheduler for the ENTIRE damage-over-time surface.
    ///
    /// DamageOverTime.TakeDamageOverTime has exactly two callers in the game —
    /// RayHitPoison.DoHitEffect (poison bullets) and HealthHandler.TakeDamageOverTime
    /// (the Decay branch, which routes EVERY direct hit on a Decay holder through
    /// the DoT path). Both funnel through here, so a capable victim gets both.
    ///
    /// The inactive-GameObject guard that used to be VanillaFixes.DeadPlayerDotPatch
    /// is folded in as step 1. Two prefixes on one method have UNDEFINED relative
    /// order and Harmony skips subsequent prefixes once one returns false, so
    /// splitting them would let whichever ran first silently decide whether the
    /// other ran at all.</summary>
    [HarmonyPatch(typeof(DamageOverTime), "TakeDamageOverTime")]
    internal static class PoisonDotSchedulerPatch
    {
        // object[] __args rather than a typed SoundEvent parameter: Sonigon is
        // not referenced by the csproj, and __args keeps the Prefix
        // signature-agnostic anyway (learning #83).
        private static bool Prefix(DamageOverTime __instance, Vector2 damage,
                                   float time, float interval, Color color,
                                   Player damagingPlayer, bool lethal,
                                   HealthHandler.DamageSource damageSource, object[] __args)
        {
            try
            {
                // 1. Ex-DeadPlayerDotPatch. Unity refuses a StartCoroutine on an
                //    inactive GameObject anyway, so this only removes log noise —
                //    and SetActive(false) rides RPCA_Die, an All-RPC, so every
                //    client agrees on it.
                if (__instance == null || !__instance.gameObject.activeInHierarchy) return false;

                if (time <= 0f || interval <= 0f) return true;

                var view = __instance.GetComponent<PhotonView>();
                var data = __instance.GetComponent<CharacterData>();
                if (view == null || data == null) return true;

                // ─────────────────────────────────────────────────────────────
                // THE BRANCH BELOW IS A PURE FUNCTION OF cap(V) AND MUST STAY
                // THAT WAY. Do not add a roster check, a room check, a "is
                // everyone updated" check, or anything else that different
                // clients can evaluate differently — that is exactly the
                // split-brain that kept the previous version switched off.
                // Whether the VICTIM honours its own block is decided inside
                // AuthoritativeDot (HonorBlock), where only the victim reads it.
                // ─────────────────────────────────────────────────────────────
                // Returning true hands the whole call back to vanilla, INCLUDING its
                // own tick audio — so nothing above this line may have started ours.
                if (!PoisonSync.CapableVictim(view)) return true;   // vanilla + PoisonGhostPatch

                // Tick AUDIO is local and unauthoritative, so every client runs it
                // regardless of who commits the damage — same cadence and count as
                // vanilla, including for blocked ticks (vanilla plays the sound
                // before attempting the blockable damage). Started only now, on the
                // paths that return false and therefore suppress vanilla's own loop.
                object snd = (__args != null && __args.Length > 5) ? __args[5] : null;
                if (snd != null)
                    __instance.StartCoroutine(PoisonSync.LocalTickSound(
                        __instance, data, snd, PoisonSync.Quantise(damage.magnitude), time, interval));

                // Hosted on the DamageOverTime component deliberately: vanilla's
                // RPCA_Die, RPCA_Die_Phoenix and Revive all call
                // dot.StopAllCoroutines(), so our streams inherit that cleanup.
                if (!view.IsMine)
                {
                    __instance.StartCoroutine(PoisonSync.ShadowDot(
                        __instance, data, view, damage, time, interval));
                    return false;
                }

                __instance.StartCoroutine(PoisonSync.AuthoritativeDot(
                    __instance, data, view, damage, time, interval, color,
                    damagingPlayer, lethal, (int)damageSource));
                return false;
            }
            catch (Exception ex)
            {
                // A capable victim must NEVER silently end up with no damage at
                // all. Falling through to vanilla is the self-healing direction.
                Plugin.Log.LogError("[POISON-SYNC] scheduler failed, using vanilla: " + ex.Message);
                return true;
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(System.Reflection.MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null)
            {
                PoisonSync.PatchesLive = true;
                VanillaFixSupport.Cleanup("PoisonDotScheduler", null);
            }
            return exception;
        }
    }
}
