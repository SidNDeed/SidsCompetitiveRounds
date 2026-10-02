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
using System.Reflection;
using UnityEngine;

namespace CompetitiveRounds
{
    internal static class PoisonSync
    {
        // ── Protocol identity ─────────────────────────────────────────────
        //
        // The KEY carries the protocol version. cr_pois1 meant "I speak the
        // room-global-mode protocol" and must NEVER be reused — a client
        // advertising that key answers a different question. Additive wire
        // fields are fine within a key because unknown trailing elements are
        // ignored by the length checks below, and unknown kinds are dropped.
        //
        // cr_pois3 (convergence v3, bugs 406/407) is ADDITIVE: it is staged in
        // the same pre-join write as cr_pois2, needs no MIN_MOD_VERSION raise,
        // and is read per decision. v3 adds a room-common life epoch on the
        // header (two trailing elements), an end-of-stream catch-up (TYPE 3),
        // the drill-window start claim (TYPE 2) and the activation handshake
        // (TYPE 4/5). A victim stamps a v3 header and a summary, and a seat
        // sends or accepts a claim, only while V3On() holds: an ACTIVATE from
        // the master naming an exact roster, an ACK from every roster actor,
        // the room closed for joins, and every present actor carrying integer
        // cr_pois3=1. Otherwise the victim sends today's bytes. A v3 header or
        // summary that does arrive goes to the ledger on any seat that has not
        // marked its epoch broken; a seat without cr_pois3 reads the header as
        // today's 15 elements and drops the unknown kinds.
        internal const string CapabilityProp = "cr_pois2";
        internal const string CapabilityPropV3 = "cr_pois3";
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

        /// <summary>The five v3 patches, each set by its own Harmony cleanup only
        /// when it attached (#83): the RPC send-stamp bracket, the
        /// ProjectileHit.Hit bracket, the RayHitPoison.DoHitEffect arm, the
        /// Phoenix boundary and the RPCA_Die catch-up flush. cr_pois3 is staged
        /// as 1 only when all five are live.</summary>
        internal static bool RpcStampLive, HitBracketLive, PoisonArmLive, PhoenixBoundaryLive, DeathFlushLive;
        internal static bool V3PatchesLive
        {
            get
            {
                return PatchesLive && RpcStampLive && HitBracketLive && PoisonArmLive && PhoenixBoundaryLive
                    && DeathFlushLive;
            }
        }

        private static bool _staged;
        private static bool _stageFailedPermanently;
        private static bool _deferLogged;
        private static int _stateWaitLines;

        /// <summary>Stage the capability property BEFORE ever joining a room, so it
        /// rides the join operation itself. Called from Plugin.Awake (after Harmony
        /// patching, so PatchesLive is known) and retried from the persistent tick.
        ///
        /// The two state rules here are load-bearing:
        ///
        ///  * REFUSE while in a room. An in-room write is a network op that arrives
        ///    on peers at some later time — exactly the eventual-consistency hole
        ///    this design exists to avoid.
        ///  * Retry only from an IDLE client state. `!InRoom` is ALSO true mid-join,
        ///    and a merge landing after LoadBalancingClient snapshots
        ///    enterRoomParamsCache but before room entry would be present locally
        ///    and NEVER delivered to peers — a silently false-capable client, which
        ///    is the worst state this protocol can be in. The idle set is
        ///    Disconnected, PeerCreated, ConnectedToMasterServer and JoinedLobby:
        ///    the first two provably precede any connect, and in the other two no
        ///    join is in flight, so a local merge rides the next join op's own
        ///    snapshot. The first two ALONE were correct only while this staged at
        ///    Awake; see the gate itself for why the post-verdict tick made them a
        ///    trap.</summary>
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

                // AND NOT BEFORE THE COMPATIBILITY VERDICT. Awake stages this, and
                // the verdict lands about three seconds later; a seat that joined a
                // room inside that window and was then disabled could only withdraw
                // the advertisement with an IN-ROOM write, the racy path this
                // protocol forbids. The tick retry above runs only after
                // DoInitialize, so the verdict is always in by the time it stages —
                // this gate closes the Awake path, and only that one. Deliberately
                // BELOW the PatchesLive arm so the loud "did NOT attach" failure
                // still fires at Awake rather than a few seconds later (#83).
                // Swept here although the review flagged cr_dc2 and cr_saw1: a flag
                // names a line and the defect is the operation (#432).
                if (!Plugin.compatCheckComplete)
                {
                    if (!_deferLogged)
                    {
                        _deferLogged = true;
                        Plugin.Log.LogInfo("[POISON-CAP] deferred staging " + CapabilityProp
                            + " (" + source + ") — the compatibility verdict is not in yet; "
                            + "the first post-verdict tick stages it");
                    }
                    return;
                }

                if (PhotonNetwork.InRoom)
                {
                    Plugin.Log.LogError("[POISON-CAP] refusing to stage while in a room ("
                        + source + ") — an in-room write is the racy path this protocol forbids");
                    return;
                }

                // Disconnected/PeerCreated alone was the right set while this staged
                // at Awake and nowhere else. It became a trap the moment the gate
                // above moved staging to the first POST-VERDICT tick: the verdict
                // lands about three seconds in, by which time ROUNDS is normally
                // sitting on the master server or in the lobby. Those two states are
                // equally safe — no join is in flight, and the local merge rides the
                // next join op's snapshot — but the old pair excluded them, so every
                // tick from then on returned here, _deferLogged had already been
                // spent on the deferral line, and the capability never staged for the
                // whole session with nothing in the log saying so. The three siblings
                // that were always tick-staged (GrowNormalize, SawTargetSync,
                // DcReportSync) admit all four; this one now matches them (#432 — the
                // flag named a line, the defect was the operation).
                ClientState st = PhotonNetwork.NetworkClientState;
                if (st != ClientState.Disconnected && st != ClientState.PeerCreated
                    && st != ClientState.ConnectedToMasterServer && st != ClientState.JoinedLobby)
                {
                    // Bounded, and deliberately NOT sharing _deferLogged: a silent
                    // return is exactly how the failure above stayed invisible. This
                    // line is the only thing that tells "still waiting for a clean
                    // moment" apart from "staged" in a bundle.
                    if (_stateWaitLines < 3)
                    {
                        _stateWaitLines++;
                        Plugin.Log.LogInfo("[POISON-CAP] holding " + CapabilityProp + " (" + source
                            + ") — client state is " + st + ", which may be mid-join; a later tick "
                            + "stages it from an idle state ("
                            + _stateWaitLines.ToString(System.Globalization.CultureInfo.InvariantCulture)
                            + "/3)");
                    }
                    return;
                }

                var local = PhotonNetwork.LocalPlayer;
                if (local == null) return;

                // cr_pois3 rides the SAME hashtable, so the two keys arrive
                // together in the join op. It is 1 only when every v3 patch
                // attached (V3PatchesLive): a seat that cannot stamp the epoch,
                // bracket the hit or arm the claim must read as v3-incapable.
                int v3 = V3PatchesLive ? CapabilityValue : 0;
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable
                {
                    { CapabilityProp, CapabilityValue },
                    { CapabilityPropV3, v3 }
                });
                _staged = true;
                Plugin.Log.LogInfo("[POISON-CAP] staged " + CapabilityProp + "=" + CapabilityValue
                    + " " + CapabilityPropV3 + "=" + v3
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
                    { CapabilityProp, 0 },
                    { CapabilityPropV3, 0 }
                });
                Plugin.Log.LogWarning("[POISON-CAP] revoked " + CapabilityProp + " and " + CapabilityPropV3
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

                // v3: deferred ticks are filled on the first frame their replica
                // is live, not at the next one-second scan.
                FillPendingAll();

                if (Time.unscaledTime - _lastScan < 1f) return;
                _lastScan = Time.unscaledTime;

                V3Upkeep();

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

        // THE FILTER IS THE REPLICATED READ, NOT THE FIRST-SIGHT CACHE.
        //
        // Both helpers below feed ScanRoster, whose output is a fail-closed
        // capability REFUSAL: an actor in this list that does not advertise the
        // poison capability makes THIS seat sticky-incapable, arms the roster
        // quarantine, and stops it honouring blocks. Those are cross-seat
        // decisions — they only behave if every seat reaches the same one from
        // the same bytes — and RoomActors.IsSpectator cannot deliver that: it
        // writes its answer into _roleByActor at THIS seat's FIRST SIGHT of an
        // actor and never re-reads the property, so what it returns is a
        // function of when this seat happened to look. Two seats that first
        // touch an actor at different moments hold different rosters for the
        // whole room, and a rule computed from two rosters is two rules — which
        // reaches fighter damage through block honouring.
        //
        // These two sites were argued the other way one round ago, on the
        // reading that this roster GRANTS authority and the cache therefore
        // usefully holds "joined as a spectator" fixed. It does not grant: it
        // refuses. Where the replicated read is wrong it is wrong on every seat
        // at once and self-heals on the next call, and it errs toward counting an
        // actor as a FIGHTER, which is the fail-closed direction here (#276).
        private static int RawNonSpectatorCount()
        {
            try
            {
                var list = PhotonNetwork.PlayerList;
                if (list == null) return 0;
                int n = 0;
                for (int i = 0; i < list.Length; i++)
                    if (list[i] != null && !RoomActors.IsSpectatorReplicated(list[i])) n++;
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
                    if (list[i] != null && !RoomActors.IsSpectatorReplicated(list[i])) keep.Add(list[i]);
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
            // v3 evidence: this seat owns the victim's view.
            public bool Own;
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

        // ── Late-verdict evidence (bugs 406/407, C1) ──────────────────────
        // EVIDENCE ONLY: nothing here applies, withholds or reorders damage.
        // When this seat's ShadowDot has reported [POISON-SILENT] for an
        // actor, the first verdict that actor's stream then delivers here is
        // logged once as [POISON-LATE] with the stream, the tick and how late
        // it came (server clock, from the shadow's arming and from the silence
        // report). A silence no verdict ever answered is logged once at the
        // point end. One record per actor, the earliest silence kept, so the
        // lines are bounded by the [POISON-SILENT] lines themselves.
        private struct SilenceRec { internal int ViewId, ArmedTs, ReportedTs; }
        private static readonly Dictionary<int, SilenceRec> _silence = new Dictionary<int, SilenceRec>();

        private static void NoteSilence(int actor, int viewId, int armedTs)
        {
            try
            {
                if (_silence.ContainsKey(actor)) return;
                _silence[actor] = new SilenceRec { ViewId = viewId, ArmedTs = armedTs, ReportedTs = PhotonNetwork.ServerTimestamp };
            }
            catch { }
        }

        private static void NoteVerdictAfterSilence(int actor, int viewId, int streamId, int tick)
        {
            try
            {
                SilenceRec s;
                if (_silence.Count == 0 || !_silence.TryGetValue(actor, out s)) return;
                _silence.Remove(actor);
                int now = PhotonNetwork.ServerTimestamp;
                int fromArm, fromReport;
                unchecked { fromArm = now - s.ArmedTs; fromReport = now - s.ReportedTs; }
                Plugin.Log.LogInfo("[POISON-LATE] verdict after silence: view=" + viewId + " stream=" + streamId + " tick=" + tick
                    + " silent_view=" + s.ViewId + " delay_from_arm_ms=" + fromArm + " delay_from_silence_ms=" + fromReport);
            }
            catch { }
        }

        /// <summary>Point end: every silence still unanswered, once, then
        /// forgotten (the revive that follows restarts every stream).</summary>
        internal static void ReportUnansweredSilences()
        {
            try
            {
                if (_silence.Count == 0) return;
                int now = PhotonNetwork.ServerTimestamp;
                foreach (var kv in _silence)
                {
                    int fromArm; unchecked { fromArm = now - kv.Value.ArmedTs; }
                    Plugin.Log.LogInfo("[POISON-LATE] no verdict after silence by the point end: view=" + kv.Value.ViewId
                        + " delay_from_arm_ms=" + fromArm);
                }
                _silence.Clear();
            }
            catch { }
        }

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
                _silence.Clear();
                PointEvidence.ResetForRoomExit();
                _reviveServerTs.Clear();
                _sawIncapablePeer = false;
                _rosterRoom = "";
                _lastRosterChange = -999f;
                _recSeq = 0;
                // v3: every held record retires with its evidence line, then
                // all room state goes (actor numbers and view ids are per room).
                _ledger.Clear();
                DrainRetired();
                _openV3.Clear();   // the room is gone: no one to send a catch-up to
                _claims.Clear();
                _act.Clear();
                _epochBroken = false;
                _v3LogLines = 0;
                _v3LastState = null;
                _lastActivateSent = -999f;
                _witnessClosed = false;
                _hitStack.Clear();
                if (_claimDropSuppressed > 0)
                    Plugin.Log.LogInfo("[POISON-CLAIM] recv drop lines suppressed this room: " + _claimDropSuppressed);
                _claimDropLines = 0;
                _claimDropSuppressed = 0;
                _skipLines = 0;
                _refusedLines = 0;
            }
            catch { }
        }

        // ── Convergence v3 (bugs 406/407): the shell around PoisonLedgerCore ──
        //
        // Every decision is made in PoisonLedgerCore.cs (pure; executed by
        // tools/tests/poison-ledger). This section feeds it what the game and
        // the network say and carries out what it returns. Record:
        // POISON-CONVERGENCE-AMENDMENTS-V3.md (local notes).
        //
        //  TYPE 2 claim:    2, PROTO, victimViewId, projViewId, claimId, hitTs,
        //                   nPoison(byte), epochTs, epochSet          (9, to the victim's owner)
        //  TYPE 3 summary:  3, PROTO, viewId, streamId, epochTs, epochSet,
        //                   sliceX, sliceY, colR, colG, colB, attackerPlayerId,
        //                   lethal, damageSource, ticks, committed(byte[]),
        //                   blocked(byte[]), seq                      (18, to others)
        //  TYPE 4 activate: 4, PROTO, aid, roster(int[])              (4, master to all)
        //  TYPE 5 ack:      5, PROTO, aid, masterActor                (4, to all)
        private const byte TypeClaim = 2;
        private const byte TypeSummary = 3;
        private const byte TypeActivate = 4;
        private const byte TypeAck = 5;

        private static readonly PoisonLedgerCore _ledger = new PoisonLedgerCore();
        private static readonly ClaimCore _claims = new ClaimCore();
        private static readonly ActivationCore _act = new ActivationCore();
        private static readonly LedgerApplier _applier = new LedgerApplier();

        // A boundary RPC seen without its send stamp leaves this seat unable to
        // name lives the way the others do, so for the rest of the room it
        // stamps no v3 header, sends and accepts no claim, and handles v3
        // headers by today's path.
        private static bool _epochBroken;
        private const int V3LineCap = 24;
        private static int _v3LogLines;
        private static string _v3LastState;
        private static int _activateSeq;
        private static float _lastActivateSent = -999f;
        private static bool _witnessClosed;
        private static bool _witnessBound;
        private static BepInEx.Configuration.ConfigEntry<bool> _witnessLever;

        private static long NowMs() { return (long)(Time.realtimeSinceStartup * 1000f); }

        private static int LocalActor()
        {
            try { return PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : -1; }
            catch { return -1; }
        }

        /// <summary>Bounded v3 state lines (per room).</summary>
        private static void V3Line(string text)
        {
            if (_v3LogLines >= V3LineCap) return;
            _v3LogLines++;
            Plugin.Log.LogInfo("[POISON-LEDGER] " + text);
        }

        private static int[] PresentActors()
        {
            var keep = new List<int>(4);
            try
            {
                var list = PhotonNetwork.PlayerList;
                if (list != null)
                    for (int i = 0; i < list.Length; i++)
                        if (list[i] != null) keep.Add(list[i].ActorNumber);
            }
            catch { }
            return keep.ToArray();
        }

        /// <summary>Raw replicated read of cr_pois3 on a present actor
        /// (spectators included): integer 1 or not capable.</summary>
        private static bool HasCap3(int actor)
        {
            try
            {
                var list = PhotonNetwork.PlayerList;
                if (list == null) return false;
                for (int i = 0; i < list.Length; i++)
                {
                    var p = list[i];
                    if (p == null || p.ActorNumber != actor) continue;
                    object v;
                    return p.CustomProperties != null && p.CustomProperties.TryGetValue(CapabilityPropV3, out v)
                        && v is int && (int)v == CapabilityValue;
                }
            }
            catch { }
            return false;
        }

        /// <summary>THE v3 GATE (amendment A2), re-read at every decision: the
        /// header stamp, a claim send, a claim accept. Off means today's bytes
        /// and today's paths.</summary>
        internal static bool V3On(out string why)
        {
            why = "unknown";
            try
            {
                if (!V3PatchesLive) { why = "patches"; return false; }
                if (Plugin.modDisabled) { why = "mod-disabled"; return false; }
                if (_epochBroken) { why = "epoch-broken"; return false; }
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode || PhotonNetwork.CurrentRoom == null)
                { why = "no-room"; return false; }
                return _act.Evaluate(!PhotonNetwork.CurrentRoom.IsOpen, PresentActors(), HasCap3, NowMs(), out why);
            }
            catch (Exception ex) { why = "error:" + ex.GetType().Name; return false; }
        }

        /// <summary>Once a second: the witness lever, the state line, and the
        /// master's activation offer while the room is closed.</summary>
        private static void V3Upkeep()
        {
            try
            {
                WitnessLever();
                string why;
                bool on = V3On(out why);
                string state = on ? "v3 " + why : "v3 off why=" + why;
                if (state != _v3LastState) { _v3LastState = state; V3Line(state); }

                if (!PhotonNetwork.IsMasterClient || _act.Live || _epochBroken || !V3PatchesLive) return;
                var room = PhotonNetwork.CurrentRoom;
                if (room == null || room.IsOpen) return;
                if (Time.unscaledTime - _lastRosterChange < RosterQuarantineSeconds) return;
                if (Time.unscaledTime - _lastActivateSent < 10f) return;
                int[] present = PresentActors();
                if (present.Length == 0) return;
                foreach (int a in present) if (!HasCap3(a)) return;
                _lastActivateSent = Time.unscaledTime;
                int aid = ++_activateSeq;
                bool ok = RaiseTo(new object[] { TypeActivate, Protocol, aid, present }, ReceiverGroup.All, null);
                V3Line("activation " + (ok ? "sent" : "send-failed") + " a=" + aid + " roster=" + present.Length);
            }
            catch { }
        }

        /// <summary>Two-seat witness only (default off): the master seat closes
        /// its room for joins once a game is running and never reopens it. A
        /// closed room refuses every later join, spectators included, which is
        /// why production does not do this (question for Sid).</summary>
        private static void WitnessLever()
        {
            if (_witnessClosed) return;
            if (!_witnessBound)
            {
                _witnessBound = true;
                try
                {
                    var cf = Plugin.ConfigFileForLevers;
                    if (cf != null)
                        _witnessLever = cf.Bind("Poison", "V3WitnessCloseRoom", false,
                            "Two-seat witness only: while this seat is the room's master and a game is running, "
                            + "close the room for joins (never reopened) so poison convergence v3 can activate. "
                            + "A closed room refuses every later join, spectators included.");
                }
                catch { }
            }
            if (_witnessLever == null || !_witnessLever.Value) return;
            var room = PhotonNetwork.CurrentRoom;
            if (!PhotonNetwork.IsMasterClient || room == null || !room.IsOpen) return;
            if (GameManager.instance == null || !GameManager.instance.battleOngoing) return;
            room.IsOpen = false;
            _witnessClosed = true;
            V3Line("witness lever: this seat closed the room for joins");
        }

        private static bool RaiseTo(object[] payload, ReceiverGroup group, int[] targets)
        {
            try
            {
                var o = new RaiseEventOptions();
                if (targets != null) o.TargetActors = targets;
                else o.Receivers = group;
                return PhotonNetwork.RaiseEvent(EventCode, payload, o, SendOptions.SendReliable);
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[POISON-AUTH] raise threw: " + ex.Message);
                return false;
            }
        }

        private static void OnActivate(int sender, object[] a)
        {
            try
            {
                if (a.Length < 4 || !(a[2] is int) || !(a[3] is int[])) return;
                int aid = (int)a[2];
                var roster = (int[])a[3];
                int master = PhotonNetwork.MasterClient != null ? PhotonNetwork.MasterClient.ActorNumber : -1;
                if (!_act.OnActivate(sender, master, aid, roster, NowMs()))
                {
                    V3Line("activation ignored a=" + aid + " from=" + sender + " (not the master)");
                    return;
                }
                var room = PhotonNetwork.CurrentRoom;
                bool closed = room != null && !room.IsOpen;
                bool ack = !_epochBroken && V3PatchesLive && _act.ShouldAck(closed, PresentActors(), HasCap3);
                bool sent = ack && RaiseTo(new object[] { TypeAck, Protocol, aid, sender }, ReceiverGroup.All, null);
                V3Line("activation received a=" + aid + " from=" + sender + " roster=" + roster.Length
                    + " ack=" + (ack ? (sent ? "sent" : "send-failed") : "refused"));
            }
            catch { }
        }

        private static void OnAck(int sender, object[] a)
        {
            try
            {
                if (a.Length < 4 || !(a[2] is int) || !(a[3] is int)) return;
                _act.OnAck(sender, (int)a[3], (int)a[2]);
            }
            catch { }
        }

        /// <summary>The ledger's view of "this replica can take a tick now":
        /// the gates that silently eat a DoDamage call (HealthHandler.cs:269)
        /// and, on a fighter seat, EndScreenKill's refusal window.</summary>
        private static bool LiveReplica(PhotonView view)
        {
            try
            {
                if (view == null) return false;
                var cd = view.GetComponent<CharacterData>();
                var hh = view.GetComponent<HealthHandler>();
                if (cd == null || hh == null) return false;
                if (!cd.isPlaying || cd.dead || hh.isRespawning) return false;
                if (!RoomActors.LocalIsSpectator && EndScreenKillPatch.RefusesNow()) return false;
                return true;
            }
            catch { return false; }
        }

        /// <summary>Header data from a TYPE 0 (offset 5) or TYPE 3 (offset 6).</summary>
        private static StreamRec RecFrom(object[] a, int o, bool own)
        {
            return new StreamRec
            {
                Slice = new Vector2((float)a[o], (float)a[o + 1]),
                Color = new Color((float)a[o + 2], (float)a[o + 3], (float)a[o + 4], 1f),
                AttackerId = (int)a[o + 5],
                Lethal = (bool)a[o + 6],
                DamageSource = (byte)a[o + 7],
                Seq = ++_recSeq,
                Own = own,
            };
        }

        private static void OnSummaryV3(PhotonView view, object[] a, int viewId, int streamId)
        {
            if (_epochBroken) return;
            if (!(a[4] is int) || !(a[5] is bool) || !(a[14] is int)) return;
            var epoch = (bool)a[5] ? LifeEpoch.At((int)a[4]) : default(LifeEpoch);
            var held = _ledger.OnSummary(viewId, streamId, epoch, (int)a[14], a[15] as byte[], a[16] as byte[],
                RecFrom(a, 6, view.IsMine), LiveReplica(view), _applier);
            if (held == null) LedgerRefused(viewId, streamId);
            DrainRetired();
        }

        /// <summary>A v3 stream this seat is the authority for, from its
        /// header until its catch-up summary is sent.</summary>
        private sealed class OpenV3
        {
            internal int View, Stream, AttackerId, DamageSource;
            internal LifeEpoch Epoch;
            internal Vector2 Slice;
            internal Color Color;
            internal bool Lethal;
            internal readonly List<int> Committed = new List<int>();
            internal readonly List<int> Blocked = new List<int>();
        }
        private static readonly Dictionary<long, OpenV3> _openV3 = new Dictionary<long, OpenV3>();

        /// <summary>Sends the stream's catch-up once and forgets it. Called at
        /// every exit of AuthoritativeDot and, for a coroutine stopped by
        /// dot.StopAllCoroutines() (RPCA_Die, RPCA_Die_Phoenix, Revive), by
        /// FlushOpenV3 from those methods' postfixes.</summary>
        private static void CloseV3(long key)
        {
            try
            {
                OpenV3 o;
                if (!_openV3.TryGetValue(key, out o)) return;
                _openV3.Remove(key);
                int ticks = 0;
                foreach (int k in o.Committed) if (k + 1 > ticks) ticks = k + 1;
                foreach (int k in o.Blocked) if (k + 1 > ticks) ticks = k + 1;
                bool ok = RaiseTo(new object[]
                {
                    TypeSummary, Protocol, o.View, o.Stream, o.Epoch.Ts, o.Epoch.Set,
                    o.Slice.x, o.Slice.y, o.Color.r, o.Color.g, o.Color.b, o.AttackerId, o.Lethal, (byte)o.DamageSource,
                    ticks, PoisonLedgerCore.Mask(o.Committed, ticks), PoisonLedgerCore.Mask(o.Blocked, ticks), _nextSeq++
                }, ReceiverGroup.Others, null);
                if (!ok)
                    Plugin.Log.LogWarning("[POISON-AUTH] SUMMARY SEND FAILED v" + o.View + "/s" + o.Stream
                        + " — no catch-up for seats that missed this stream");
            }
            catch { }
        }

        /// <summary>The view's DamageOverTime coroutines were just stopped:
        /// close every open v3 stream of that view.</summary>
        internal static void FlushOpenV3(int viewId)
        {
            try
            {
                if (_openV3.Count == 0) return;
                var keys = new List<long>();
                foreach (var kv in _openV3) if (kv.Value.View == viewId) keys.Add(kv.Key);
                foreach (long k in keys) CloseV3(k);
            }
            catch { }
        }

        private static int _refusedLines;
        private static void LedgerRefused(int viewId, int streamId)
        {
            if (_refusedLines >= 10) return;
            _refusedLines++;
            Plugin.Log.LogWarning("[POISON-LEDGER] v" + viewId + "/s" + streamId
                + " refused: this seat already holds the per-view ceiling of open records");
        }

        /// <summary>One evidence line per v3 record, at its retirement.</summary>
        private static void DrainRetired()
        {
            try
            {
                var log = _ledger.RetiredLog;
                if (log.Count == 0) return;
                bool spect = false;
                try { spect = RoomActors.LocalIsSpectator; } catch { }
                foreach (var r in log)
                {
                    var p = r.Payload as StreamRec;
                    Plugin.Log.LogInfo("[POISON-LEDGER] v" + r.View + "/s" + r.Stream
                        + " epoch=" + r.Life
                        + " own=" + (p != null && p.Own ? 1 : 0)
                        + " spectator=" + (spect ? 1 : 0)
                        + " cls0=" + ClassLetter(r.Cls0)
                        + " committed=" + r.Committed.Count
                        + " blocked=" + r.Blocked.Count
                        + " applied=" + r.Applied.Count
                        + " filled=" + r.Filled
                        + " catchup=" + r.CatchUp
                        + " pending_dropped=" + r.PendingDropped
                        + " after_signal=" + r.AfterSignal
                        + " summary=" + (r.SummarySeen ? 1 : 0)
                        + " dups=" + r.Duplicates
                        + " exceptions=" + r.Exceptions
                        + " retired=" + r.Retired);
                }
                log.Clear();
            }
            catch { }
        }

        private static string ClassLetter(LifeClass c)
        {
            return c == LifeClass.Current ? "C" : c == LifeClass.Next ? "N" : c == LifeClass.Ending ? "E" : "S";
        }

        /// <summary>Per frame: corrective application of deferred ticks for
        /// every view whose replica is live again.</summary>
        private static void FillPendingAll()
        {
            try
            {
                if (_ledger.Count == 0) return;
                foreach (int v in _ledger.ViewsWithPending())
                {
                    var view = PhotonView.Find(v);
                    if (view == null) continue;
                    _ledger.Fill(v, LiveReplica(view), _applier);
                }
                DrainRetired();
            }
            catch { }
        }

        internal static void OnLocalRevive(int viewId)
        {
            try { _ledger.OnRevive(viewId); DrainRetired(); } catch { }
        }

        private static void EpochBroken(string why)
        {
            if (_epochBroken) return;
            _epochBroken = true;
            V3Line("epoch-broken for this room: " + why + " (today's rules from here)");
        }

        /// <summary>The master's point-over, stamped with PUN's own send stamp
        /// for that RPC (one value on every seat).</summary>
        internal static void NotePointBoundary(GM_ArmsRace gm)
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return;
                int ts;
                if (gm != null && gm.view != null && PoisonRpcStampPatch.TryFor(gm.view.ViewID, out ts))
                    _ledger.NotePointBoundary(ts);
                else EpochBroken("point-over without its RPC stamp");
            }
            catch { }
        }

        internal static void NotePhoenixBoundary(HealthHandler hh)
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return;
                var v = hh != null ? hh.GetComponent<PhotonView>() : null;
                int ts;
                if (v != null && PoisonRpcStampPatch.TryFor(v.ViewID, out ts)) _ledger.NotePhoenixBoundary(v.ViewID, ts);
                else EpochBroken("Phoenix without its RPC stamp");
            }
            catch { }
        }

        /// <summary>The ledger's two ways to move health. Regular is today's
        /// application; Corrective is the funnel.</summary>
        private sealed class LedgerApplier : ILedgerApplier
        {
            public void Regular(PoisonLedgerCore.Rec r, int tick)
            {
                var view = PhotonView.Find(r.View);
                var rec = r.Payload as StreamRec;
                if (view == null || rec == null) return;
                rec.Accepted++;
                ApplyCommitted(view, rec, r.View, r.Stream, tick, true);
            }

            public void Corrective(PoisonLedgerCore.Rec r, int tick)
            {
                var view = PhotonView.Find(r.View);
                var rec = r.Payload as StreamRec;
                if (view == null || rec == null) return;
                ApplyCorrective(view, rec);
            }
        }

        private static Player FindPlayer(int playerId)
        {
            try
            {
                if (playerId >= 0 && PlayerManager.instance != null)
                    foreach (var p in PlayerManager.instance.players)
                        if (p != null && p.PlayerID == playerId) return p;
            }
            catch { }
            return null;
        }

        /// <summary>THE CORRECTION FUNNEL (amendment A3), the only way a late
        /// tick moves health, on fighter and spectator seats alike. It lowers
        /// this replica's health by the slice, never below min(health, 1), and
        /// arms the victim's own health-bar segment. It does not call DoDamage,
        /// so no DealtDamage chain runs (no lifesteal, refresh or card effect
        /// that spawns objects or deals more damage), no WasDealtDamage, no
        /// StopAllCoroutines and no RPC; it cannot raise a death and cannot
        /// raise health. A tick DamageRulesGate refuses is consumed.</summary>
        private static void ApplyCorrective(PhotonView view, StreamRec rec)
        {
            var cd = view.GetComponent<CharacterData>();
            var hh = view.GetComponent<HealthHandler>();
            if (cd == null || hh == null) return;
            if (DamageRulesGate.Refuses(hh, FindPlayer(rec.AttackerId))) return;
            float pre = cd.health;
            float floor = pre < 1f ? pre : 1f;
            float nh = pre - rec.Slice.magnitude;
            cd.health = nh < floor ? floor : nh;
            if (cd.health < pre)
            {
                rec.Applied++;
                try
                {
                    var bar = view.GetComponentInChildren<HealthBar>(true);
                    if (bar != null) bar.TakeDamage(default, false);
                }
                catch { }
            }
        }

        // ── The start claim (amendments A5, A6, A8, A9) ──────────────────

        /// <summary>One ProjectileHit.Hit call on this seat: whether it runs the
        /// hit locally without broadcasting it (the drill window,
        /// ProjectileHit.cs:187 reads sendCollisions), and which victims it
        /// has already armed a claim for.</summary>
        private sealed class HitFrame
        {
            internal ProjectileHit Hit;
            internal bool LocalOnly;
            internal readonly Dictionary<int, int> Armed = new Dictionary<int, int>();
        }
        private static readonly List<HitFrame> _hitStack = new List<HitFrame>();
        private static int _currentArmClaim;
        private static int _claimStartDepth;
        private static int _skipLines;

        internal static void HitEnter(ProjectileHit ph)
        {
            try
            {
                var f = new HitFrame { Hit = ph };
                f.LocalOnly = ph != null && ph.view != null && ph.view.IsMine && !ph.sendCollisions;
                _hitStack.Add(f);
            }
            catch { }
        }

        internal static void HitExit(ProjectileHit ph)
        {
            try
            {
                for (int i = _hitStack.Count - 1; i >= 0; i--)
                    if (ReferenceEquals(_hitStack[i].Hit, ph)) { _hitStack.RemoveRange(i, _hitStack.Count - i); return; }
            }
            catch { }
        }

        private static HitFrame FrameFor(ProjectileHit ph)
        {
            for (int i = _hitStack.Count - 1; i >= 0; i--)
                if (ReferenceEquals(_hitStack[i].Hit, ph)) return _hitStack[i];
            return null;
        }

        /// <summary>RayHitPoison.DoHitEffect's prefix. On the VICTIM's seat, a
        /// broadcast hit by another seat's bullet takes the shared TryStart and
        /// loses only its poison to a claim that already started the pair. On
        /// the SHOOTER's seat, a hit this seat ran locally without
        /// broadcasting arms one claim per Hit call and victim. False skips
        /// this poison effect only.</summary>
        internal static bool PoisonEffectEnter(RayHitPoison fx, HitInfo hit, out int prevArm)
        {
            prevArm = _currentArmClaim;
            if (fx == null || hit == null || hit.transform == null) return true;
            var ph = fx.GetComponentInParent<ProjectileHit>();
            var vv = hit.transform.GetComponent<PhotonView>();
            if (ph == null || vv == null) return true;
            var pv = ph.view;

            if (vv.IsMine && pv != null && !pv.IsMine && _claimStartDepth == 0)
            {
                if (_claims.TryStart(ph.GetInstanceID(), vv.ViewID, StartPath.Broadcast)) return true;
                if (_skipLines < 20)
                {
                    _skipLines++;
                    Plugin.Log.LogInfo("[POISON-CLAIM] broadcast poison skipped proj=" + pv.ViewID + " victim=" + vv.ViewID
                        + ": a claim already started this bullet's poison on this victim");
                }
                return false;
            }

            HitFrame f = FrameFor(ph);
            if (f == null || !f.LocalOnly || vv.IsMine) return true;
            if (hit.transform.GetComponent<DamageOverTime>() == null) return true;
            int armed;
            if (f.Armed.TryGetValue(vv.ViewID, out armed)) { _currentArmClaim = armed; return true; }
            armed = ShooterArm(ph, pv, vv);
            f.Armed[vv.ViewID] = armed;
            _currentArmClaim = armed;
            return true;
        }

        internal static void PoisonEffectExit(int prevArm) { _currentArmClaim = prevArm; }

        /// <summary>One local-only poison arm: exactly one terminal line.</summary>
        private static int ShooterArm(ProjectileHit ph, PhotonView pv, PhotonView vv)
        {
            string why;
            bool on = V3On(out why);
            LifeEpoch ep;
            bool known = _ledger.FenceOf(vv.ViewID, out ep);
            int claimId;
            string drop = _claims.ShooterArm(on, why, known, ph.GetInstanceID(), vv.ViewID, NowMs(), out claimId);
            int projView = pv != null ? pv.ViewID : -1;
            string head = "[POISON-CLAIM] arm from=" + LocalActor() + " c=" + claimId + " proj=" + projView
                + " victim=" + vv.ViewID + " outcome=";
            if (drop != null) { Plugin.Log.LogInfo(head + "drop reason=" + drop); return claimId; }
            int owner = vv.Owner != null ? vv.Owner.ActorNumber : -1;
            int nPoison = 0;
            try { nPoison = ph.GetComponentsInChildren<RayHitPoison>(true).Length; } catch { }
            bool sent = owner > 0 && RaiseTo(new object[]
            {
                TypeClaim, Protocol, vv.ViewID, projView, claimId, PhotonNetwork.ServerTimestamp,
                (byte)Math.Min(nPoison, 255), ep.Ts, ep.Set
            }, ReceiverGroup.Others, new[] { owner });
            Plugin.Log.LogInfo(head + (sent ? "sent" : "send-failed"));
            return claimId;
        }

        /// <summary>Drop lines on the victim's seat are capped per room; past
        /// the cap they are counted and the count is written once at room exit.</summary>
        private const int ClaimDropLineCap = 256;
        private static int _claimDropLines, _claimDropSuppressed;

        private static void ClaimDropLine(string line)
        {
            if (_claimDropLines < ClaimDropLineCap) { _claimDropLines++; Plugin.Log.LogInfo(line); }
            else _claimDropSuppressed++;
        }

        /// <summary>The victim's seat: every syntactically valid claim gets
        /// exactly one terminal result, and one terminal line until the
        /// per-room drop-line cap.</summary>
        private static void OnClaim(int sender, object[] a)
        {
            try
            {
                if (a.Length < 9 || !(a[2] is int) || !(a[3] is int) || !(a[4] is int) || !(a[5] is int)
                    || !(a[6] is byte) || !(a[7] is int) || !(a[8] is bool)) return;
                int victimView = (int)a[2], projView = (int)a[3], claimId = (int)a[4];
                var f = new ClaimFacts
                {
                    Sender = sender, ClaimId = claimId, VictimView = victimView, NowMs = NowMs(),
                    ShooterEpoch = (bool)a[8] ? LifeEpoch.At((int)a[7]) : default(LifeEpoch),
                };
                string why;
                f.GateOn = V3On(out why);
                f.GateWhy = why;
                PhotonView vv = PhotonView.Find(victimView);
                f.VictimFound = vv != null;
                f.VictimIsMine = vv != null && vv.IsMine;
                PhotonView pv = PhotonView.Find(projView);
                ProjectileHit ph = pv != null ? pv.GetComponent<ProjectileHit>() : null;
                f.ProjFound = ph != null;
                f.ProjOwner = pv != null && pv.Owner != null ? pv.Owner.ActorNumber : -1;
                RayHitPoison[] poisons = ph != null ? ph.GetComponentsInChildren<RayHitPoison>(true) : null;
                f.PoisonChildren = poisons != null ? poisons.Length : 0;
                f.ProjInstance = ph != null ? ph.GetInstanceID() : 0;
                f.Live = vv != null && LiveReplica(vv);
                LifeEpoch ve;
                f.VictimFenceKnown = _ledger.FenceOf(victimView, out ve);
                f.VictimEpoch = ve;

                string result = _claims.VictimDecide(f);
                string head = "[POISON-CLAIM] recv from=" + sender + " c=" + claimId + " proj=" + projView
                    + " victim=" + victimView + " outcome=";
                if (result != "started") { ClaimDropLine(head + "drop reason=" + result); return; }

                int first = _nextStream;
                _claimStartDepth++;
                try
                {
                    var hit = new HitInfo { transform = vv.transform, point = vv.transform.position };
                    foreach (var c in poisons)
                    {
                        if (c == null) continue;
                        try { c.DoHitEffect(hit); }
                        catch (Exception ex) { Plugin.Log.LogWarning("[POISON-CLAIM] start threw c=" + claimId + ": " + ex.Message); }
                    }
                }
                finally { _claimStartDepth--; }
                var sb = new System.Text.StringBuilder();
                for (int s = first; s < _nextStream; s++) sb.Append(sb.Length > 0 ? "," : "").Append('s').Append(s);
                Plugin.Log.LogInfo(head + "started streams=" + (sb.Length > 0 ? sb.ToString() : "none"));
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[POISON-CLAIM] handler failed: " + ex.Message); }
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
                if (a == null || a.Length < 4) return;
                if (!(a[0] is byte) || !(a[1] is byte)) return;
                if ((byte)a[1] != Protocol) return;

                byte kind = (byte)a[0];
                // v3 messages that are not the victim's own verdicts: the start
                // claim (sender = the shooter, checked in OnClaim) and the
                // activation handshake (sender = master, or a roster actor).
                if (kind == TypeClaim) { OnClaim(e.Sender, a); return; }
                if (kind == TypeActivate) { OnActivate(e.Sender, a); return; }
                if (kind == TypeAck) { OnAck(e.Sender, a); return; }

                // Length must be validated for THIS kind before any indexed read
                // below — the seq read alone is at index 14 on a header.
                if (kind == TypeHeader) { if (a.Length < 15) return; }
                else if (kind == TypeTick) { if (a.Length < 7) return; }
                else if (kind == TypeSummary) { if (a.Length < 18) return; }
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

                int seq = (int)a[kind == TypeHeader ? 14 : (kind == TypeSummary ? 17 : 6)];
                int last;
                if (_lastSeq.TryGetValue(e.Sender, out last) && !SeqAfter(seq, last)) return;
                _lastSeq[e.Sender] = seq;
                NoteVerdictAfterSilence(e.Sender, viewId, streamId, kind == TypeHeader ? 0 : (kind == TypeTick ? (int)a[4] : -1));

                long key = StreamKey(viewId, streamId);
                StreamRec rec;

                // v3 catch-up: the victim's end-of-stream summary (A1).
                if (kind == TypeSummary) { OnSummaryV3(view, a, viewId, streamId); return; }

                if (kind == TypeHeader)
                {
                    // v3 header: the victim stamped its life epoch (indexes 15
                    // and 16, both typed). It goes to the ledger, which replaces
                    // the revive fence below with the room-common life fence.
                    // A seat that saw a boundary without a common stamp handles
                    // it by today's path instead.
                    LifeEpoch epoch;
                    if (!_epochBroken && PoisonLedgerCore.TryV3Epoch(a.Length,
                            a.Length > 15 ? a[15] : null, a.Length > 16 ? a[16] : null, out epoch))
                    {
                        _lastHeardServerTs[e.Sender] = PhotonNetwork.ServerTimestamp;
                        var held = _ledger.OnHeader(viewId, streamId, epoch, (bool)a[13],
                            RecFrom(a, 5, view.IsMine), LiveReplica(view), _applier);
                        if (held == null) LedgerRefused(viewId, streamId);
                        DrainRetired();
                        return;
                    }

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

                if (_ledger.Find(viewId, streamId) != null)
                {
                    _lastHeardServerTs[e.Sender] = PhotonNetwork.ServerTimestamp;
                    _ledger.OnTick(viewId, streamId, (int)a[4], (bool)a[5], LiveReplica(view), _applier);
                    DrainRetired();
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
            ApplyCommitted(view, rec, viewId, streamId, tick, false);
        }

        /// <summary>One committed tick, on time: today's application. The v3
        /// ledger calls it for a tick it releases while the replica is live
        /// (v3=true changes only the spectator path's room-rule refusal, which
        /// then shares DamageRulesGate's own predicate).</summary>
        private static void ApplyCommitted(PhotonView view, StreamRec rec,
                                           int viewId, int streamId, int tick, bool v3)
        {
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
                    // Room rules (§5.3, addendum A2): a teammate's tick in a
                    // friendly-fire-OFF room moves no health on the fighter
                    // seats — the DoDamage gate skips the whole body, DealtDamage
                    // included — so the observer consumes the SAME verdict and
                    // renders nothing: no health change, no bar tick, no
                    // lifesteal credit. Consumed (not deferred): the tick is
                    // accounted for exactly as on a fighter seat.
                    // v3 streams (amendments 4.8): the spectator consumes every
                    // tick DamageRulesGate refuses on the fighter seats
                    // (quarantine and sudden death too), not friendly fire alone.
                    bool ffSuppressed = false;
                    try
                    {
                        ffSuppressed = cds != null && (v3
                            ? DamageRulesGate.Refuses(hh, attacker)
                            : RoomRules.SuppressTeammateDamage(attacker, view.GetComponent<Player>()));
                    }
                    catch { ffSuppressed = false; }
                    if (cds != null && !ffSuppressed)
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

                        float preTick = cds.health;
                        float nh = cds.health - rec.Slice.magnitude;
                        cds.health = nh < 1f ? 1f : nh;
                        rec.Applied++;
                        // Owner item 3 (Aug 30): the red "recently lost"
                        // trailing segment. The ONLY thing the fighter-seat
                        // damage path does to the health bar is
                        // HealthBar.TakeDamage — a single sinceDamage=0
                        // write (HealthBar.cs:54-57) — so calling it here
                        // gives exact fighter parity (vanilla DOT ticks it
                        // once per DoDamage too). Display-only: touches no
                        // state beyond the bar's own timer, so the #338
                        // observer fence above is untouched. Gated on an
                        // ACTUAL drop (design review, Aug 30): at the 1-HP
                        // clamp nothing was lost, and arming the timer there
                        // would paint a phantom red segment.
                        try
                        {
                            if (cds.health < preTick)
                            {
                                var hbBar = view.GetComponentInChildren<HealthBar>(true);
                                if (hbBar != null) hbBar.TakeDamage(default, false);
                            }
                        }
                        catch { }
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
                        // Bug 241: also render the attacker's REFRESH (block
                        // back when dealing damage). Same class as the
                        // lifesteal above: on fighter seats the
                        // DoDamage->DealtDamage chain fires the card's
                        // DealtDamageTrigger -> ResetBlock.Go() ->
                        // Block.ResetCD, so the holder's block came back on
                        // every DOT tick everywhere EXCEPT this seat — with
                        // Poison builds virtually ALL damage rides the DOT
                        // path, so spectators watched a block that never
                        // recharged (Spirit's report). Deliberately OUTSIDE
                        // the lifesteal's attacker!=victim guard (client
                        // review find 3): vanilla's DealtDamageTrigger fires
                        // on SELF-damage too (only lifesteal gates on
                        // !selfDamage), so a reflected self-DOT resets block
                        // on fighter seats and must here as well. ResetCD is
                        // pure local cooldown-display state: spawns nothing,
                        // damages nothing (#338 untouched), and keeps the
                        // full-chain rejection above intact.
                        try
                        {
                            if (attacker != null && attacker.data != null)
                            {
                                var blk = attacker.data.block;
                                if (blk != null)
                                    foreach (var rb in attacker.GetComponentsInChildren<ResetBlock>())
                                        if (rb != null) { blk.ResetCD(false); break; }
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
            // Room rules (§5.3): a teammate's tick in a friendly-fire-OFF room
            // is refused inside DoDamage by DamageRulesGate (the attacker rides
            // the call), so this seat and the observer seat above reach the
            // same verdict from the same predicate; hpBefore/Applied below
            // then read "no movement", which is the truth.
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
            // publish time. Its live consumer is the receive path's REVIVE FENCE
            // (drop verdicts from a stream that began before the victim's latest
            // revive). The watchdog this stamp originally served was deleted —
            // see the design record at the top of this file.
            int streamStartTs = PhotonNetwork.ServerTimestamp;

            float damageToDeal = Quantise(damage.magnitude);
            float dpt = damageToDeal / time * interval;
            if (dpt <= 0f) yield break;

            Vector2 slice = damage.normalized * dpt;
            float damageDealt = 0f;
            int tick = 0, blockedCount = 0, failedSends = 0;
            bool honor = HonorBlock();

            // v3 (amendments A1, A2, A4): decided ONCE per stream, here, by the
            // victim, and carried in the header, so every receiver treats this
            // stream the same way. It needs the activation (V3On), this seat's
            // own life epoch for its view, and a free slot under the
            // authority-side bound on concurrently open v3 streams.
            string v3Why;
            LifeEpoch epoch = default(LifeEpoch);
            bool v3 = V3On(out v3Why);
            if (v3 && !_ledger.FenceOf(viewId, out epoch)) v3 = false;
            if (v3)
            {
                long now = NowMs();
                long span = (long)(time / Mathf.Max(TimeHandler.timeScale, 0.01f) * 1000f) + 1000L;
                if (!_ledger.AdmitV3Stream(now, now + span)) v3 = false;
            }
            long openKey = StreamKey(viewId, stream);
            OpenV3 ov = null;
            if (v3)
            {
                ov = new OpenV3
                {
                    View = viewId, Stream = stream, Epoch = epoch, Slice = slice, Color = color,
                    AttackerId = attackerId, Lethal = lethal, DamageSource = damageSource,
                };
                _openV3[openKey] = ov;
            }

            while (damageDealt < damageToDeal)
            {
                // A v3 stream sends its catch-up at every exit (CloseV3); a
                // stop by dot.StopAllCoroutines() is closed by FlushOpenV3.
                if (host == null || data == null || view == null) { CloseV3(openKey); yield break; }
                // Narrow the emit-then-die race to sub-frame. Receivers also
                // no-op via DoDamage's own guard, but not emitting is cheaper.
                if (data.dead || !data.isPlaying) { CloseV3(openKey); yield break; }

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
                if (tick == 0 && v3)
                {
                    // 17 elements: today's 15, then the life epoch (stamp, set).
                    // Old receivers read the first 15 and ignore the rest.
                    sent = Raise(new object[]
                    {
                        TypeHeader, Protocol, viewId, stream, streamStartTs,
                        slice.x, slice.y, color.r, color.g, color.b,
                        attackerId, lethal, (byte)damageSource, blocked, _nextSeq++,
                        epoch.Ts, epoch.Set
                    });
                }
                else if (tick == 0)
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
                // The catch-up names only ticks that went out: a failed send was
                // lost for every seat, the victim's own echo included.
                if (ov != null && sent) (blocked ? ov.Blocked : ov.Committed).Add(tick);

                tick++;
                yield return new WaitForSeconds(interval / TimeHandler.timeScale);
            }

            CloseV3(openKey);

            StreamRec rec;
            _streams.TryGetValue(StreamKey(viewId, stream), out rec);
            var lrec = v3 ? _ledger.Find(viewId, stream) : null;
            int recvAccepted = lrec != null ? lrec.Committed.Count : (rec != null ? rec.Accepted : -1);
            int recvBlocked = lrec != null ? lrec.Blocked.Count : (rec != null ? rec.Blocked : -1);
            var lpay = lrec != null ? lrec.Payload as StreamRec : null;
            int hpApplied = lpay != null ? lpay.Applied : (rec != null ? rec.Applied : -1);
            Plugin.Log.LogInfo("[POISON-SYNC] COMPLETE v" + viewId + "/s" + stream
                + " honor=" + honor + " v3=" + (v3 ? 1 : 0) + " epoch=" + (v3 ? epoch.ToString() : "-")
                + " sent=" + tick + " blocked=" + blockedCount
                + " failedSends=" + failedSends
                + " recvAccepted=" + recvAccepted
                + " recvBlocked=" + recvBlocked
                + " hpApplied=" + hpApplied);
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
            // Bar P1 (amendment A9): whether this shadow was armed by a
            // local-only poison arm (its claim id) or by any other hit.
            int armClaim = _currentArmClaim;

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
                            // Local observation ONLY (Codex, bug-321 audit): this seat can
                            // prove it RECEIVED nothing, never that nothing was published or
                            // that other seats withheld damage — a victim-side stall, a
                            // relay/path delivery stall, and THIS seat's own receive lag all
                            // print the identical line (the bundle's arrivalGap=13s with
                            // senderGap=0.3s was a delivery stall, not a sender freeze).
                            Plugin.Log.LogWarning("[POISON-SILENT] no verdict received on THIS seat from capable victim view=" + viewId
                                + " actor=" + actor + " within " + SilenceReportMs
                                + "ms of a damage-over-time stream — sender/path/receiver undetermined; "
                                + "damage state on other seats unknown. Correlate across seats before "
                                + "blaming the victim's client."
                                + (armClaim > 0 ? " arm=local-only c=" + armClaim : " arm=broadcast-or-direct"));
                            NoteSilence(actor, viewId, anchor);

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
                if (v != null)
                {
                    PoisonSync.FlushOpenV3(v.ViewID);     // v3: Revive stopped this view's streams
                    PoisonSync.OnLocalRevive(v.ViewID);   // v3 life fence (records of other lives retire)
                    PoisonSync.ResetForView(v.ViewID);    // today's records and fence, unchanged
                }
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
    /// order, so splitting them would let whichever ran first decide the shared
    /// state the other reads.
    ///
    /// NOT because a false return suppresses the sibling: it does not. HarmonyX
    /// runs EVERY prefix on a target and merely ANDs their results into
    /// __runOriginal, so a separate guard prefix returning false could never have
    /// stopped this one running, and each prefix must carry its own guard. An
    /// earlier version of this comment asserted the opposite, which would have
    /// pointed the next maintainer at an unsafe split (VanillaFixes.cs states the
    /// correct rule).</summary>
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

    /// <summary>Bugs 406/407, EVIDENCE ONLY (C2, C3): per point, what THIS seat
    /// holds. Nothing here changes damage, health or timing -- it reads.
    ///
    /// C2: at every point end, one [HP-POINT-END] line with every player's
    /// health and max health as this seat holds them (player id and team, no
    /// account identity). Two seats' lines for the same point differing is the
    /// divergence the reports describe; equal lines rule it out for that point.
    ///
    /// C3: the Saw card deals its damage on each seat from that seat's own
    /// locally spawned saw (VanillaFixes.SawDeadTargetPatch's notes). Every
    /// Saw.Update is bracketed and the health each player LOST inside it is
    /// summed per point; at the point end one [SAW-POINT] line carries the
    /// sums (only when a saw dealt anything). A heal inside the bracket
    /// (lifesteal) is not netted against it: only drops are counted.</summary>
    internal static class PointEvidence
    {
        private static readonly Dictionary<int, float> _sawLost = new Dictionary<int, float>();
        private static readonly Dictionary<int, float> _before = new Dictionary<int, float>();
        private static int _sawFrames;
        private static int _point;

        internal static int Point { get { return _point; } }

        internal static void ResetForRoomExit()
        {
            HitEvidence.ResetForRoomExit(_point);   // item D: a game cut short still reports what arrived
            _sawLost.Clear(); _before.Clear(); _sawFrames = 0; _point = 0;
        }

        /// <summary>Item D's per-game flush when this point decided the game.</summary>
        internal static void GameOverCheck(GM_ArmsRace gm)
        {
            try
            {
                if (gm != null && (gm.p1Rounds >= gm.roundsToWinGame || gm.p2Rounds >= gm.roundsToWinGame))
                    HitEvidence.GameEnd(_point);
            }
            catch { }
        }

        internal static void SawBefore()
        {
            try
            {
                _before.Clear();
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return;
                foreach (var p in pm.players)
                    if (p != null && p.data != null) _before[p.PlayerID] = p.data.health;
            }
            catch { }
        }

        internal static void SawAfter()
        {
            try
            {
                if (_before.Count == 0) return;
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return;
                bool any = false;
                foreach (var p in pm.players)
                {
                    if (p == null || p.data == null) continue;
                    float was;
                    if (!_before.TryGetValue(p.PlayerID, out was)) continue;
                    float lost = was - p.data.health;
                    if (lost <= 0f) continue;
                    float sum;
                    _sawLost.TryGetValue(p.PlayerID, out sum);
                    _sawLost[p.PlayerID] = sum + lost;
                    any = true;
                }
                if (any) _sawFrames++;
                _before.Clear();
            }
            catch { }
        }

        internal static void PointEnd()
        {
            try
            {
                _point++;
                var sb = new System.Text.StringBuilder();
                var pm = PlayerManager.instance;
                if (pm != null && pm.players != null)
                    foreach (var p in pm.players)
                    {
                        if (p == null || p.data == null) continue;
                        sb.Append(" p").Append(p.PlayerID).Append("(team ").Append(p.TeamID).Append(")=")
                          .Append(p.data.health.ToString("0.00", System.Globalization.CultureInfo.InvariantCulture)).Append('/')
                          .Append(p.data.MaxHealth.ToString("0.00", System.Globalization.CultureInfo.InvariantCulture))
                          .Append(p.data.dead ? " dead" : "");
                    }
                Plugin.Log.LogInfo("[HP-POINT-END] point=" + _point + " spectator=" + (RoomActors.LocalIsSpectator ? 1 : 0) + sb);
                if (_sawLost.Count > 0)
                {
                    var s = new System.Text.StringBuilder();
                    foreach (var kv in _sawLost)
                        s.Append(" p").Append(kv.Key).Append('=').Append(kv.Value.ToString("0.00", System.Globalization.CultureInfo.InvariantCulture));
                    Plugin.Log.LogInfo("[SAW-POINT] point=" + _point + " frames=" + _sawFrames + " lost" + s);
                }
                _sawLost.Clear(); _sawFrames = 0;
                HitEvidence.PointEnd(_point);
                PoisonSync.ReportUnansweredSilences();
            }
            catch { }
        }
    }

    /// <summary>C3's bracket: the health each player loses inside one
    /// Saw.Update on this seat. A prefix and a finalizer (which runs whether or
    /// not the update threw, and rethrows what it was given), neither of which
    /// changes anything.</summary>
    [HarmonyPatch(typeof(Saw), "Update")]
    internal static class SawPointEvidencePatch
    {
        [HarmonyPrefix]
        private static void Before() { PointEvidence.SawBefore(); }

        [HarmonyFinalizer]
        private static Exception After(Exception __exception)
        {
            PointEvidence.SawAfter();
            return __exception;
        }
    }

    /// <summary>C2's trigger: the point-decided broadcast, which runs in every
    /// mode (FFA's prefix replaces the body, postfixes still run).</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "RPCA_NextRound", new Type[] { typeof(int), typeof(int), typeof(int), typeof(int), typeof(int), typeof(int) })]
    internal static class PointEndEvidencePatch
    {
        [HarmonyPostfix]
        private static void After(GM_ArmsRace __instance)
        {
            PointEvidence.PointEnd();
            PointEvidence.GameOverCheck(__instance);
            PoisonSync.NotePointBoundary(__instance);   // v3: the room-common boundary stamp
        }
    }

    /// <summary>Convergence v3 (A1): the view id and PUN send stamp of the RPC
    /// this seat is executing. PUN writes the sender's ServerTimestamp into
    /// every RPC (key 2) and an RpcTarget.All sender executes that same
    /// hashtable locally, so a boundary RPC carries one stamp on every seat.
    /// The prefix records, the finalizer restores the enclosing value (RPCs
    /// nest); neither changes the call.</summary>
    [HarmonyPatch]
    internal static class PoisonRpcStampPatch
    {
        private struct Frame { internal bool Has; internal int View; internal int Ts; }
        private static Frame _cur;

        /// <summary>The executing RPC's send stamp, only when that RPC targets
        /// this view (so a direct call nested in another RPC never borrows
        /// that RPC's stamp).</summary>
        internal static bool TryFor(int viewId, out int ts)
        {
            ts = _cur.Ts;
            return _cur.Has && _cur.View == viewId;
        }

        private static MethodBase TargetMethod()
        {
            var m = AccessTools.Method(typeof(PhotonNetwork), "ExecuteRpc",
                new[] { typeof(ExitGames.Client.Photon.Hashtable), typeof(Photon.Realtime.Player) });
            if (m == null) throw new Exception("PhotonNetwork.ExecuteRpc(Hashtable, Player) not found - poison v3 has no boundary stamp");
            return m;
        }

        [HarmonyPrefix]
        private static void Prefix(ExitGames.Client.Photon.Hashtable __0, out Frame __state)
        {
            __state = _cur;
            var f = new Frame();
            try
            {
                object v, t;
                if (__0 != null && __0.TryGetValue((byte)0, out v) && v is int
                    && __0.TryGetValue((byte)2, out t) && t is int)
                { f.Has = true; f.View = (int)v; f.Ts = (int)t; }
            }
            catch { }
            _cur = f;
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(Frame __state, Exception __exception)
        {
            _cur = __state;
            return __exception;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) PoisonSync.RpcStampLive = true;
            return exception;
        }
    }

    /// <summary>Convergence v3 (A1): a Phoenix death is a boundary for its view.</summary>
    [HarmonyPatch(typeof(HealthHandler), "RPCA_Die_Phoenix")]
    internal static class PoisonPhoenixBoundaryPatch
    {
        [HarmonyPostfix]
        private static void After(HealthHandler __instance)
        {
            PoisonSync.NotePhoenixBoundary(__instance);
            var v = __instance != null ? __instance.GetComponent<PhotonView>() : null;
            if (v != null) PoisonSync.FlushOpenV3(v.ViewID);   // the method stopped this view's streams
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) PoisonSync.PhoenixBoundaryLive = true;
            return exception;
        }
    }

    /// <summary>Convergence v3 (A1): RPCA_Die stops the view's damage-over-time
    /// coroutines (HealthHandler.cs:377) before any stream reaches its own
    /// exit, so the victim's seat sends those streams' catch-up here.</summary>
    [HarmonyPatch(typeof(HealthHandler), "RPCA_Die")]
    internal static class PoisonDeathFlushPatch
    {
        [HarmonyPostfix]
        private static void After(HealthHandler __instance)
        {
            try
            {
                var v = __instance != null ? __instance.GetComponent<PhotonView>() : null;
                if (v != null) PoisonSync.FlushOpenV3(v.ViewID);
            }
            catch { }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) PoisonSync.DeathFlushLive = true;
            return exception;
        }
    }

    /// <summary>Convergence v3 (A9): brackets ProjectileHit.Hit so the poison
    /// arm below knows whether THIS call runs the hit locally without
    /// broadcasting it (view.IsMine and sendCollisions false, the field
    /// ProjectileHit.cs:187 reads; nothing in :146-186 writes it). Records
    /// only; the finalizer pops and returns the exception it was given.</summary>
    [HarmonyPatch(typeof(ProjectileHit), "Hit")]
    internal static class PoisonHitBracketPatch
    {
        [HarmonyPrefix]
        private static void Prefix(ProjectileHit __instance) { PoisonSync.HitEnter(__instance); }

        [HarmonyFinalizer]
        private static Exception Finalizer(ProjectileHit __instance, Exception __exception)
        {
            PoisonSync.HitExit(__instance);
            return __exception;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) PoisonSync.HitBracketLive = true;
            return exception;
        }
    }

    /// <summary>Convergence v3 (A5, A9): the poison effect's own entry. The
    /// claim is raised only here, so only from an actually entered
    /// RayHitPoison.DoHitEffect; the victim seat's shared TryStart is taken
    /// here too. Returning false skips this one poison effect.</summary>
    [HarmonyPatch(typeof(RayHitPoison), "DoHitEffect")]
    internal static class PoisonArmPatch
    {
        [HarmonyPrefix]
        private static bool Prefix(RayHitPoison __instance, HitInfo hit, out int __state)
        {
            __state = 0;
            try { return PoisonSync.PoisonEffectEnter(__instance, hit, out __state); }
            catch { return true; }
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(int __state, Exception __exception)
        {
            PoisonSync.PoisonEffectExit(__state);
            return __exception;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) PoisonSync.PoisonArmLive = true;
            return exception;
        }
    }
}
