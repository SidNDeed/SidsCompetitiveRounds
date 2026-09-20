using System;
using System.Collections.Generic;
using Photon.Pun;
using UnityEngine;
using PhotonPlayer = Photon.Realtime.Player;

namespace CompetitiveRounds
{
    /// <summary>
    /// Aug 6 item 13 (spectator mode), PHASE 0 — the single classification
    /// authority for "who in this Photon room is actually playing".
    ///
    /// Every existing direct read of PhotonNetwork.PlayerList / PlayerCount in
    /// the mod means one of two different things, and they only LOOK the same
    /// today because every actor is a fighter:
    ///   (a) "how many people are playing"  -> ActiveFighterCount()
    ///   (b) "how many actors are connected" -> PhotonNetwork.CurrentRoom.PlayerCount
    /// Once a spectator can join, (a) and (b) diverge, and every site that
    /// meant (a) but reads (b) becomes a bug: a spectator would satisfy a
    /// 2-player match-start check, prevent an FFA below-minimum shutdown,
    /// count as a sync peer, be elected reporter, or be mistaken for the
    /// opponent.
    ///
    /// ── THE INERTNESS GUARANTEE ────────────────────────────────────────
    /// When no actor carries the spectator role property AND no roster is
    /// frozen, EVERY helper here returns exactly what the raw Photon call
    /// returns, in the same ORDER (ActorNumber ascending — reporter election
    /// and slot mapping depend on ordering determinism). BOTH conditions are
    /// load-bearing: this paragraph originally named the spectator one alone,
    /// which the PRECISION line and the 2026-09-17 correction below already
    /// contradict, and a reader who stopped here would have believed it
    /// (headline corrected 2026-09-18, Codex b4yssbnuh).
    ///
    /// So migrating a call site here is a provable no-op only in a room that
    /// is BOTH spectator-free and unfrozen — which is not a competitive
    /// match, since every one of those freezes its roster.
    ///
    /// PRECISION: the fast path is "no spectator AND no frozen roster".
    ///
    /// CORRECTED 2026-09-17 — the inertness half of this note is no longer
    /// true and had outlived the build it described. It read "nothing calls
    /// FreezeFighterRoster in the shipped build, so RosterFrozen is false
    /// everywhere". Three sites call it today:
    /// GameStateWatcher.cs:1572, :5006 and :6398. Spectators are likewise
    /// live — SpectatorSession.cs:419 stages cr_spec as a pre-join property.
    ///
    /// So BOTH conjuncts of the fast path now go false in ordinary play, and
    /// these helpers really do diverge from raw PlayerList in a shipped
    /// build. That divergence is the POINT of freezing — once a roster is
    /// frozen, a non-spectator actor is a fighter only if it is ON that
    /// roster — but it is no longer correct to read any of this as inert, and
    /// anything reasoning about these helpers must assume both filters fire.
    ///
    /// Classification is CACHED BY ActorNumber at first sight and is
    /// immutable for the lifetime of the room (design §3.2): an actor that
    /// joined as a spectator can never later clear its property and be
    /// treated as a fighter. Photon does not reuse an ActorNumber within a
    /// room, so the cache cannot alias.
    ///
    /// The role property is CLASSIFICATION, NOT AUTHENTICATION. Claiming
    /// "spectator" only ever grants FEWER privileges, so a forged claim is
    /// harmless; the server's lease check is what authorises the seat.
    /// </summary>
    internal static class RoomActors
    {
        // Pre-join player property carrying the spectator protocol version.
        // Staged BEFORE JoinRoom so it rides the join operation itself and is
        // therefore never observable-after-use (#287): any client that can act
        // on actor V has already processed V's join payload/EV_JOIN, so it has
        // held this property for V's entire in-room lifetime. An in-room
        // SetCustomProperties would be eventually-consistent and could not
        // carry this guarantee (#280).
        internal const string SPEC_PROP = "cr_spec";
        internal const string SPEC_LEASE_PROP = "cr_spec_lease";

        // ActorNumber -> is-spectator, frozen at first classification.
        private static readonly Dictionary<int, bool> _roleByActor = new Dictionary<int, bool>();
        // Room the cache belongs to; a room change wipes it.
        private static string _cacheRoom = "";

        // Actors this room REJECTED locally (unauthorized entrants, impostor
        // duplicates). LOCAL knowledge only — seats with a frozen roster
        // know more than seats without one, and that is fine because this
        // cache only ever ADDS suppression. The cross-client-CONSISTENT
        // question ("is this departing actor a fighter whose leave should
        // tear the match down?") is answered by the PROP-DERIVED rules below
        // (HasReplicatedFighterIdentity / IsImpostorReplicated), which every
        // seat computes identically from replicated data with no
        // announcements. (An announced-verdict room property was tried in
        // an earlier round and DELETED: client-writable room state is an
        // attack surface — a hostile actor could suppress a real fighter's
        // DC teardown by pre-writing their ActorNumber — and its delivery
        // could never be made monotonic against Photon's property cache.)
        private static readonly HashSet<int> _rejectedActors = new HashSet<int>();

        // ActorNumber -> "has been seen carrying a u_id". Seeded at first
        // classification and PROMOTABLE (r10 find 1): a false entry re-reads
        // live props on each query and can only move to true — so a fighter
        // whose u_id arrived post-join is never mistaken for a non-fighter
        // at departure. PUN retains the leaving actor's props through the
        // leave callback, so the live re-read works there too.
        private static readonly Dictionary<int, bool> _hasUidByActor = new Dictionary<int, bool>();

        /// <summary>Frozen fighter roster (steam ids), set at match assembly.
        /// Empty = not yet frozen, in which case "expected fighter" degrades
        /// to "not a spectator", which is the pre-spectator behaviour.</summary>
        private static readonly HashSet<string> _fighterSteamIds =
            new HashSet<string>(StringComparer.Ordinal);

        private static readonly PhotonPlayer[] _emptyActors = new PhotonPlayer[0];

        // ── cache lifecycle ──────────────────────────────────────────────

        private static void EnsureCacheRoom()
        {
            string room = "";
            try { room = PhotonNetwork.CurrentRoom != null ? (PhotonNetwork.CurrentRoom.Name ?? "") : ""; }
            catch { }
            if (room != _cacheRoom)
            {
                _roleByActor.Clear();
                _rejectedActors.Clear();
                _hasUidByActor.Clear();
                _cacheRoom = room;
                // Deliberately NOT clearing _fighterSteamIds here: the roster
                // is frozen by the match-assembly path, which owns its own
                // lifetime (a room change without a re-freeze must not
                // silently widen the roster to "everyone").
            }
        }

        /// <summary>Called on room leave / match teardown.</summary>
        internal static void Reset()
        {
            _roleByActor.Clear();
            _rejectedActors.Clear();
            _hasUidByActor.Clear();
            _cacheRoom = "";
            _fighterSteamIds.Clear();
            _fighterCacheFrame = -1;
            _fighterCache = null;
        }

        /// <summary>Record an actor this room has rejected (unauthorized
        /// entrant / impostor). Called on EVERY client the moment the actor
        /// is classified unauthorized — before the master's CloseConnection
        /// lands — so its later departure is provably not a fighter leaving.</summary>
        internal static void RecordRejected(PhotonPlayer actor)
        {
            if (actor == null) return;
            try
            {
                EnsureCacheRoom();
                _rejectedActors.Add(actor.ActorNumber);
            }
            catch { }
        }

        /// <summary>True if this actor was recorded as rejected in this room
        /// (LOCAL knowledge — additive suppression only; the cross-client
        /// rule is the prop-derived pair below). Survives the actor's
        /// property teardown at departure.</summary>
        internal static bool IsRejected(PhotonPlayer actor)
        {
            if (actor == null) return false;
            try
            {
                EnsureCacheRoom();
                return _rejectedActors.Contains(actor.ActorNumber);
            }
            catch { return false; }
        }

        /// <summary>True in rooms where PRE-JOIN u_id staging is GUARANTEED
        /// for every fighter (Aug 10 r10 finds 1+2 scoped the no-u_id rule
        /// here): the team_/ovt_/ffa_ lobby paths stage u_id before joining
        /// — verified at their three prejoin sites — and those rooms are
        /// mod-issued, so no vanilla actor can legitimately lack it. Ranked
        /// 1v1 / code / casual rooms get u_id POST-join from vanilla's own
        /// publish (or never, for unmodded quickplay peers), so the rule
        /// must stay inactive there — a genuine fighter's or vanilla peer's
        /// departure must run vanilla teardown. Room NAME is replicated:
        /// every seat evaluates this identically.</summary>
        internal static bool ReplicatedIdentityGuaranteed()
        {
            try
            {
                var room = PhotonNetwork.CurrentRoom;
                string n = room != null ? (room.Name ?? "") : "";
                return n.StartsWith("team_", StringComparison.Ordinal)
                    || n.StartsWith("ovt_", StringComparison.Ordinal)
                    || n.StartsWith("ffa_", StringComparison.Ordinal);
            }
            catch { return false; }
        }

        /// <summary>REPLICATED-CONSISTENT fighter-identity test. ONLY
        /// meaningful where ReplicatedIdentityGuaranteed() — callers gate on
        /// it (r10 find 2). The cache is PROMOTABLE (r10 find 1): a false
        /// latched before a later u_id publish re-checks live props and
        /// promotes, never demotes — so the answer can only move toward
        /// "fighter", the vanilla-teardown direction.</summary>
        internal static bool HasReplicatedFighterIdentity(PhotonPlayer actor)
        {
            if (actor == null) return false;
            try
            {
                EnsureCacheRoom();
                bool cached;
                if (_hasUidByActor.TryGetValue(actor.ActorNumber, out cached) && cached) return true;
                bool has = !string.IsNullOrEmpty(SteamIdOf(actor));
                _hasUidByActor[actor.ActorNumber] = has;
                return has;
            }
            catch { return true; }   // unknown -> treat as fighter (vanilla behavior)
        }

        /// <summary>REPLICATED-CONSISTENT impostor test (r9): an actor whose
        /// u_id duplicates an EARLIER, still-present actor's u_id is a copy,
        /// not a fighter — computable identically on every seat from
        /// replicated props + ActorNumber ordering, with NO roster
        /// dependence (the roster-gated duplicate rule in IsUnauthorized
        /// remains for seats that know more). A genuine reconnect is
        /// unaffected: the old actor has already left, so no duplicate
        /// exists.</summary>
        internal static bool IsImpostorReplicated(PhotonPlayer actor)
        {
            if (actor == null) return false;
            try
            {
                string sid = SteamIdOf(actor);
                if (string.IsNullOrEmpty(sid)) return false;
                var room = PhotonNetwork.CurrentRoom;
                if (room == null || room.Players == null) return false;
                foreach (var kv in room.Players)
                {
                    var other = kv.Value;
                    if (other == null || other.ActorNumber == actor.ActorNumber) continue;
                    if (other.ActorNumber < actor.ActorNumber
                        && !IsSpectator(other)
                        && string.Equals(SteamIdOf(other), sid, StringComparison.Ordinal))
                        return true;
                }
                return false;
            }
            catch { return false; }
        }

        /// <summary>Called from OnJoinedRoom on EVERY client: a new room means
        /// any previous room's frozen roster is stale (EnsureCacheRoom
        /// deliberately does not clear it — see its comment — so the join
        /// callback owns this). Without it, a roster frozen in match A would
        /// filter the fighters of match B (Codex r1 find 1 family).</summary>
        internal static void OnJoinedNewRoom()
        {
            _fighterSteamIds.Clear();
        }

        /// <summary>Freeze the fighter roster at match assembly (design §3.2).
        /// After this, a later-arriving actor is a spectator (if it carries
        /// the role property) or unauthorized (if it does not) — never a new
        /// fighter.</summary>
        internal static void FreezeFighterRoster(IEnumerable<string> steamIds)
        {
            _fighterSteamIds.Clear();
            if (steamIds == null) return;
            foreach (var s in steamIds)
                if (!string.IsNullOrEmpty(s)) _fighterSteamIds.Add(s);
        }

        internal static bool RosterFrozen => _fighterSteamIds.Count > 0;

        // ── classification ───────────────────────────────────────────────

        /// <summary>True if this actor joined as a spectator. Cached by
        /// ActorNumber at first sight and immutable thereafter.</summary>
        internal static bool IsSpectator(PhotonPlayer actor)
        {
            if (actor == null) return false;
            try
            {
                EnsureCacheRoom();
                bool cached;
                if (_roleByActor.TryGetValue(actor.ActorNumber, out cached)) return cached;
                bool isSpec = false;
                var props = actor.CustomProperties;
                if (props != null && props.ContainsKey(SPEC_PROP))
                {
                    // Presence is the signal; the value is the protocol
                    // version (used later for compatibility gating).
                    isSpec = true;
                }
                _roleByActor[actor.ActorNumber] = isSpec;
                // Piggyback the u_id-presence cache (r9): classification is
                // the one point every entry path passes through while the
                // actor's props are certainly readable.
                if (!_hasUidByActor.ContainsKey(actor.ActorNumber))
                    _hasUidByActor[actor.ActorNumber] = !string.IsNullOrEmpty(SteamIdOf(actor));
                return isSpec;
            }
            catch { return false; }
        }

        /// <summary>The same question as <see cref="IsSpectator"/>, answered from
        /// the REPLICATED property on every call instead of from a first-sight
        /// cache.
        ///
        /// <para>WHY BOTH EXIST. <see cref="IsSpectator"/> writes its answer into
        /// <c>_roleByActor</c> the first time any caller ON THIS SEAT touches an
        /// actor and never re-reads the property afterwards, so what it returns
        /// is a function of when this seat happened to look — per-seat local
        /// state. Every caller that only needs a local classification can keep
        /// it. A caller whose answer has to AGREE with another seat's cannot: two
        /// seats that first touch an actor at different moments can cache
        /// different answers and then hold them for the whole room, and a
        /// cross-seat rule computed from two different rosters is two rules.</para>
        ///
        /// <para>READING IT EVERY TIME IS SOUND because the role is immutable
        /// inside a room: it is staged pre-join, and
        /// <c>SpectatorSession.ClearStagedProperties</c> refuses to clear it
        /// while in one (design §3.2 — converting a live spectator actor into a
        /// fighter is exactly what that rule forbids). So this answer and the
        /// cached one can only differ for an actor whose property payload is not
        /// readable yet, and there this one SELF-HEALS on the next call, where
        /// the cache keeps its wrong answer for the rest of the room (#276).</para>
        ///
        /// <para>WHICH ONE A CALLER WANTS. Use this where the answer must AGREE
        /// with another seat's and a wrong answer only ever REFUSES something —
        /// capability quorums, the DC census. Keep <see cref="IsSpectator"/>
        /// where the answer GRANTS a role or an authority (PoisonSync's
        /// authority roster, the master-client rule): there the cache is doing
        /// real work, because it holds "joined as a spectator" fixed even if the
        /// property were to vanish mid-room, which design §3.2 forbids but this
        /// read could not tell from a legitimate fighter.</para></summary>
        internal static bool IsSpectatorReplicated(PhotonPlayer actor)
        {
            try
            {
                if (actor == null) return false;
                var props = actor.CustomProperties;
                return props != null && props.ContainsKey(SPEC_PROP);
            }
            catch { return false; }
        }

        /// <summary>The local client's own role. Cheap and allocation-free —
        /// safe to call from per-frame paths.</summary>
        internal static bool LocalIsSpectator
        {
            get
            {
                try { return SpectatorSession.IsLocalSpectator; }
                catch { return false; }
            }
        }

        /// <summary>An actor that is neither a frozen-roster fighter nor a
        /// declared spectator. Only meaningful once the roster is frozen;
        /// returns false before that (pre-spectator behaviour).</summary>
        internal static bool IsUnauthorized(PhotonPlayer actor)
        {
            if (actor == null) return false;
            // Once rejected, always rejected — the cache outlives the actor's
            // properties (design-review blocker 2).
            if (IsRejected(actor)) return true;
            if (!RosterFrozen) return false;
            if (IsSpectator(actor)) return false;
            try
            {
                string sid = SteamIdOf(actor);
                // FAIL CLOSED (Codex r1 find 1): once the roster is frozen,
                // an actor whose identity cannot be read is NOT one of the
                // fighters we froze — every fighter staged u_id pre-join.
                // "Unknown -> never accuse" would let a stranger dodge the
                // firewall by simply not publishing an identity.
                if (string.IsNullOrEmpty(sid)) return true;
                if (!_fighterSteamIds.Contains(sid)) return true;
                // DUPLICATE-IDENTITY rule (Codex r3 CRITICAL): a roster
                // fighter's identity belongs to the EARLIEST actor carrying
                // it. A later actor claiming the same u_id while the real one
                // is still present is an impostor — without this, a modified
                // grantee could join as a copy of a live fighter and then
                // LEAVE, making honest clients file a DC report that moves
                // real ratings/gold. A genuine reconnect is unaffected: the
                // old actor has already left the room, so no duplicate exists.
                var room = PhotonNetwork.CurrentRoom;
                if (room != null && room.Players != null)
                {
                    foreach (var kv in room.Players)
                    {
                        var other = kv.Value;
                        if (other == null || other.ActorNumber == actor.ActorNumber) continue;
                        if (other.ActorNumber < actor.ActorNumber
                            && !IsSpectator(other)
                            && string.Equals(SteamIdOf(other), sid, StringComparison.Ordinal))
                            return true;
                    }
                }
                return false;
            }
            catch { return false; }
        }

        /// <summary>The protocol version an actor's cr_spec property
        /// advertises, or -1 when absent/unreadable. Classification stays
        /// presence-based (IsSpectator) — an INCOMPATIBLE spectator must
        /// remain a spectator (never fall through as a fighter) right up
        /// until the master closes it (Aug 10 r2 blocker 2).</summary>
        internal static int SpectatorProtocolOf(PhotonPlayer actor)
        {
            try
            {
                var props = actor != null ? actor.CustomProperties : null;
                object v;
                if (props != null && props.TryGetValue(SPEC_PROP, out v) && v is int)
                    return (int)v;
            }
            catch { }
            return -1;
        }

        /// <summary>Steam id an actor advertises via the shared u_id property
        /// (the same key the queue/lobby paths already stage pre-join).</summary>
        internal static string SteamIdOf(PhotonPlayer actor)
        {
            try
            {
                var props = actor != null ? actor.CustomProperties : null;
                if (props != null && props.ContainsKey("u_id"))
                    return props["u_id"] as string ?? "";
            }
            catch { }
            return "";
        }

        // ── the inertness fast path ──────────────────────────────────────

        /// <summary>True only if at least one actor in the room declared the
        /// spectator role. Helpers below short-circuit on this TOGETHER WITH
        /// RosterFrozen: with no spectator present AND no roster frozen they
        /// are byte-for-byte equivalent to the raw Photon reads they replace.
        /// With a roster frozen they are not — and that is the ordinary case
        /// in a competitive match (corrected 2026-09-18, Codex b4yssbnuh).
        ///
        /// ALLOCATION-FREE (Codex r1 find 12): PUN's PlayerList getter sorts
        /// and ToArray()s on every access, so using it here would make every
        /// converted PlayerCount site allocate where it never did. The room's
        /// Players dictionary iterates with a struct enumerator instead.</summary>
        internal static bool AnySpectatorPresent()
        {
            try
            {
                if (!PhotonNetwork.InRoom) return false;
                var room = PhotonNetwork.CurrentRoom;
                if (room == null || room.Players == null) return false;
                foreach (var kv in room.Players)
                    if (IsSpectator(kv.Value)) return true;
                return false;
            }
            catch { return false; }
        }

        // ── fighter views ────────────────────────────────────────────────

        /// <summary>Every actor that is playing, ActorNumber-ascending.
        /// Identical to PhotonNetwork.PlayerList — including the SAME array
        /// instance, so no allocation — only when no spectator is in the room
        /// AND no roster is frozen. A frozen roster takes the filtering branch
        /// and allocates, spectator or not (corrected 2026-09-18, Codex
        /// b4yssbnuh).</summary>
        // Per-frame result cache (Codex r2 find 10): with a roster frozen —
        // every competitive match — the fast path is off, and the 10 Hz
        // pollers would otherwise allocate a PlayerList + filtered array per
        // call. Invalidated on room enter/leave callbacks as well as per
        // frame (Codex r3: two same-frame departures could otherwise let
        // each DC callback see the OTHER departed fighter still cached and
        // defer — nobody reports).
        private static int _fighterCacheFrame = -1;
        private static PhotonPlayer[] _fighterCache;

        /// <summary>Monotonic count of roster and identity changes this
        /// process has been told about (review r8 MEDIUM 4). A cache
        /// invalidation says "read again"; a reader that only reads again
        /// cannot see a change that ARRIVED AND REVERTED between its two
        /// reads, and one PUN Dispatch can drain an enter, a delivery and a
        /// leave with no frame in between. This counter is the trace that
        /// survives it. It only ever goes up, and it is never reset — a
        /// consumer records the value it opened under and compares.</summary>
        internal static int RosterGeneration { get { return _rosterGeneration; } }
        private static int _rosterGeneration;

        /// <summary>Player properties that decide identity or role changed.
        /// Not a roster change, so it does not touch the fighter cache — but
        /// it moves the key any consumer of RosterGeneration is watching.</summary>
        internal static void NoteRosterIdentityChange()
        {
            _rosterGeneration++;
        }

        /// <summary>Called from the room enter/leave callbacks so a roster
        /// change is visible to every later read in the SAME frame.</summary>
        internal static void InvalidateFighterCache()
        {
            _fighterCacheFrame = -1;
            _fighterCache = null;
            NoteRosterIdentityChange();
        }

        internal static PhotonPlayer[] ActiveFighters()
        {
            try
            {
                if (!PhotonNetwork.InRoom) return _emptyActors;
                if (_fighterCacheFrame == Time.frameCount && _fighterCache != null)
                    return _fighterCache;
                var list = PhotonNetwork.PlayerList;
                if (list == null) return _emptyActors;
                // R3 (LOW): the fast path must ALSO require an unfrozen
                // roster — otherwise freezing {A,B} and then admitting a late
                // actor C with no spectator in the room returned C as a
                // fighter, defeating the freeze in exactly the case it exists
                // for. CORRECTED 2026-09-17: the trailing claim here — "still
                // fully inert in the shipped build: nothing calls
                // FreezeFighterRoster" — is stale. GameStateWatcher.cs:1572,
                // :5006 and :6398 all call it, so this branch is live and the
                // RosterFrozen conjunct is load-bearing, not decorative.
                if (!AnySpectatorPresent() && !RosterFrozen) return list;   // inert: same instance
                var keep = new List<PhotonPlayer>(list.Length);
                for (int i = 0; i < list.Length; i++)
                {
                    if (IsSpectator(list[i])) continue;
                    // Codex round 2 (MEDIUM): once the roster is FROZEN, a
                    // non-spectator actor is only a fighter if it is ON that
                    // roster. Without this, an actor that joins late carrying
                    // no role property at all (a stale client, or someone who
                    // obtained the room name) was counted into fighter quorum,
                    // sync-peer counts and report rosters — the exact hole the
                    // frozen roster exists to close. Fail CLOSED: an actor
                    // whose identity we cannot read is not a fighter either,
                    // because admitting an unidentifiable actor to a rating-
                    // bearing roster is strictly worse than excluding it.
                    if (RosterFrozen)
                    {
                        // IsUnauthorized carries the whole rule set: roster
                        // membership, fail-closed identity, AND the
                        // duplicate-u_id impostor exclusion (r3 CRITICAL) —
                        // an impostor must not appear in fighter views either.
                        if (IsUnauthorized(list[i])) continue;
                    }
                    keep.Add(list[i]);
                }
                keep.Sort((a, b) => a.ActorNumber.CompareTo(b.ActorNumber));
                var result = keep.ToArray();
                _fighterCache = result;
                _fighterCacheFrame = Time.frameCount;
                return result;
            }
            catch { return _emptyActors; }
        }

        /// <summary>Fighter count. THE replacement for
        /// PhotonNetwork.CurrentRoom.PlayerCount at every site that meant
        /// "how many people are playing".</summary>
        internal static int ActiveFighterCount()
        {
            try
            {
                if (!PhotonNetwork.InRoom) return 0;
                var room = PhotonNetwork.CurrentRoom;
                if (room == null) return 0;
                if (!AnySpectatorPresent() && !RosterFrozen) return room.PlayerCount;   // inert
                // Same frozen-roster rule as ActiveFighters — this count feeds
                // quorum and start decisions, so the two MUST agree.
                return ActiveFighters().Length;
            }
            catch { return 0; }
        }

        /// <summary>Fighters other than the local client — the "peers I must
        /// wait for / talk to" set. Used by sync-peer counting, opponent
        /// resolution and capability consensus.</summary>
        internal static PhotonPlayer[] OtherActiveFighters()
        {
            try
            {
                var all = ActiveFighters();
                var keep = new List<PhotonPlayer>(all.Length);
                for (int i = 0; i < all.Length; i++)
                    if (!all[i].IsLocal) keep.Add(all[i]);
                return keep.ToArray();
            }
            catch { return _emptyActors; }
        }

        internal static int OtherActiveFighterCount()
        {
            try
            {
                if (!PhotonNetwork.InRoom) return 0;
                var room = PhotonNetwork.CurrentRoom;
                if (room == null) return 0;
                if (!AnySpectatorPresent() && !RosterFrozen)
                    return Math.Max(0, room.PlayerCount - 1);  // inert
                return Math.Max(0, ActiveFighterCount() - (LocalIsSpectator ? 0 : 1));
            }
            catch { return 0; }
        }

        /// <summary>Spectator actors, ActorNumber-ascending. Empty in every
        /// room that has none.</summary>
        internal static PhotonPlayer[] Spectators()
        {
            try
            {
                if (!PhotonNetwork.InRoom) return _emptyActors;
                if (!AnySpectatorPresent()) return _emptyActors;
                var list = PhotonNetwork.PlayerList;
                if (list == null) return _emptyActors;
                var keep = new List<PhotonPlayer>(2);
                for (int i = 0; i < list.Length; i++)
                    if (IsSpectator(list[i])) keep.Add(list[i]);
                keep.Sort((a, b) => a.ActorNumber.CompareTo(b.ActorNumber));
                return keep.ToArray();
            }
            catch { return _emptyActors; }
        }

        internal static int SpectatorCount()
        {
            try { return Spectators().Length; }
            catch { return 0; }
        }

        /// <summary>Master-side cooperative close (r10 find 3): raises the
        /// sender-side EnableCloseConnection flag TRANSIENTLY around the one
        /// call, then restores it. While WE are master, an incoming event
        /// 203 is only honored from "the master" — us — so the window is
        /// not exploitable; and a fighter's steady-state flag stays FALSE,
        /// so a hostile master can never evict an honest fighter (the
        /// vanilla baseline). Spectator clients keep the flag true for
        /// their whole session instead — they are kickable by design.</summary>
        internal static void CooperativeClose(PhotonPlayer actor)
        {
            if (actor == null) return;
            bool prev = false;
            try
            {
                prev = PhotonNetwork.EnableCloseConnection;
                PhotonNetwork.EnableCloseConnection = true;
                PhotonNetwork.CloseConnection(actor);
            }
            catch { }
            finally
            {
                try { PhotonNetwork.EnableCloseConnection = prev; } catch { }
            }
        }

        /// <summary>The MasterClient must always be a fighter — authority on
        /// a spectator would put match simulation on a client with no stake
        /// and no characters (design §5/§7). True when the current master is
        /// a spectator, i.e. a transfer is required.</summary>
        internal static bool MasterIsSpectator()
        {
            try
            {
                if (!PhotonNetwork.InRoom) return false;
                if (!AnySpectatorPresent()) return false;   // inert
                var m = PhotonNetwork.MasterClient;
                return m != null && IsSpectator(m);
            }
            catch { return false; }
        }
    }

    /// <summary>The whole-room capability behind the 2v2 disconnect reporter
    /// election. Same protocol as <c>PoisonSync</c>, <c>GrowNormalize</c> and
    /// <c>SawTargetSync</c>, for the same reason all three have one: the rule
    /// decides what OTHER seats' reports mean, so it may only run where every
    /// seat that could report is running it too.
    ///
    /// <para>WHAT THE ELECTION NEEDS IT FOR. The four-seat census in
    /// <c>Plugin.OnPlayerLeftRoom</c> proves that exactly one seat elects itself
    /// — on the seats evaluating that census. A seat on an older build evaluates
    /// the previous OR'd election instead and posts its own report regardless, so
    /// in a MIXED room "exactly one reporter" would be a property of this seat's
    /// code and not of the room, and the duplicate the census exists to rule out
    /// would still arrive from the peer. <c>cr_dc2</c> is how a seat says "I
    /// elect from the census"; the census arm is entered only when every survivor
    /// says it, and otherwise every seat in the room — old and new — runs the
    /// floor election they already agree on.</para>
    ///
    /// <para>KEY NAMING: <c>cr_dc2</c> means "this seat elects from the four-seat
    /// census". A later rule change takes <c>cr_dc3</c>, so a mixed room drops to
    /// the floor election everywhere rather than running two rules at once. There
    /// was no <c>cr_dc1</c>: the number is the election generation, and the
    /// generation before this one advertised nothing at all.</para>
    ///
    /// <para>FAIL-CLOSED on every arm — a disabled mod, a staging failure, a
    /// survivor without the property, an empty survivor list (every(∅) must not
    /// apply) — and what "closed" costs here is only the floor election, i.e.
    /// the behaviour that shipped (#430).</para></summary>
    internal static class DcReportSync
    {
        internal const string CapabilityProp = "cr_dc2";
        internal const int CapabilityValue = 1;

        private static bool _staged, _stageFailedPermanently;

        /// <summary>Stage PRE-JOIN only. An in-room write is present locally
        /// immediately and may reach peers after they have already evaluated a
        /// census — a silently false-capable seat, which is the one state this
        /// protocol must not be in. Idle client states provably precede the join
        /// op's parameter snapshot (#287, same reasoning as PoisonSync).</summary>
        internal static void StageCapability(string source)
        {
            try
            {
                if (_staged || _stageFailedPermanently) return;
                if (Plugin.modDisabled) { _stageFailedPermanently = true; return; }
                if (PhotonNetwork.InRoom)
                {
                    Plugin.Log.LogError("[2v2-DC] refusing to stage " + CapabilityProp
                        + " while in a room (" + source + ") — an in-room write is the racy "
                        + "path this protocol forbids");
                    return;
                }
                var st = PhotonNetwork.NetworkClientState;
                if (st != Photon.Realtime.ClientState.Disconnected
                    && st != Photon.Realtime.ClientState.PeerCreated
                    && st != Photon.Realtime.ClientState.ConnectedToMasterServer
                    && st != Photon.Realtime.ClientState.JoinedLobby)
                    return;   // connecting/joining: wait for a clean moment
                var local = PhotonNetwork.LocalPlayer;
                if (local == null) return;
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable
                {
                    { CapabilityProp, CapabilityValue }
                });
                _staged = true;
                Plugin.Log.LogInfo("[2v2-DC] staged " + CapabilityProp + "=" + CapabilityValue
                    + " pre-join (" + source + ", state=" + st + ")");
            }
            catch (Exception ex)
            {
                _stageFailedPermanently = true;
                Plugin.Log.LogWarning("[2v2-DC] staging " + CapabilityProp + " failed; this seat "
                    + "elects with the floor rule for the session: " + ex.Message);
            }
        }

        /// <summary>Withdraw on compat-disable: peers must not count us as
        /// running a rule this process will not run.</summary>
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
                Plugin.Log.LogWarning("[2v2-DC] revoked " + CapabilityProp
                    + " — mod disabled, floor election everywhere");
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[2v2-DC] revoke failed: " + ex.Message); }
        }

        /// <summary>One actor's advertisement, read from the replicated property
        /// every time. Anything that is not the exact integer value — absent,
        /// null props, a revoked 0, a type we did not write — is NOT capable.</summary>
        internal static bool Capable(PhotonPlayer actor)
        {
            try
            {
                if (actor == null) return false;
                var props = actor.CustomProperties;
                if (props == null) return false;
                object v;
                if (!props.TryGetValue(CapabilityProp, out v)) return false;
                return (v is int) && (int)v == CapabilityValue;
            }
            catch { return false; }
        }

        /// <summary>True only when EVERY survivor advertises the capability.
        /// <paramref name="missingActor"/> names the first that does not, for the
        /// log line — the same shape the other three protocols report.</summary>
        internal static bool AllCapable(List<PhotonPlayer> survivors, out int missingActor)
        {
            missingActor = -1;
            if (survivors == null || survivors.Count == 0) return false;
            bool all = true;
            for (int i = 0; i < survivors.Count; i++)
            {
                var a = survivors[i];
                if (a == null) { all = false; continue; }
                if (Capable(a)) continue;
                all = false;
                if (missingActor < 0) missingActor = a.ActorNumber;
            }
            return all;
        }
    }
}
