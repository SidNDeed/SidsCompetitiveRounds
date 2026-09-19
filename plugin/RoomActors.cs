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
    /// When no actor in the room carries the spectator role property, EVERY
    /// helper here returns exactly what the raw Photon call returns, in the
    /// same ORDER (ActorNumber ascending — reporter election and slot
    /// mapping depend on ordering determinism). `AnySpectatorPresent()` is
    /// the O(n) fast path all of them take first, so migrating a call site
    /// to RoomActors is a provable no-op until a spectator actually joins.
    /// That is what makes it safe to migrate the ~40 sites listed in the
    /// design doc BEFORE the spectator seat itself exists.
    ///
    /// PRECISION (Codex round 2): the fast path is "no spectator AND no frozen
    /// roster". CORRECTED — the "nothing freezes a roster, so RosterFrozen is
    /// false everywhere" that stood here was true when it was written and has
    /// not been true for releases. Three sites freeze today, all in
    /// GameStateWatcher: the match-assembly freeze (:1572), the late
    /// identity-resolution freeze (:5052), and the per-game FFA refreeze
    /// (:6457). So the fast path is NOT taken in a frozen room, and these
    /// helpers do additionally exclude actors that are not ON the roster —
    /// which is the point of freezing, and is a deliberate divergence from raw
    /// PlayerList rather than a violation of the inertness claim. Read the
    /// inertness guarantee as covering an UNFROZEN room only.
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

        // Actors RecordRejected declined to latch because they are on the
        // frozen roster (RJ-2). Log-once bookkeeping only: nothing reads it as
        // a verdict, and it shares the rejected set's lifetime so the line
        // reappears in a new room rather than being suppressed forever.
        private static readonly HashSet<int> _rosterLatchDeclined = new HashSet<int>();

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
                _rosterLatchDeclined.Clear();
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
            _rosterLatchDeclined.Clear();
            _hasUidByActor.Clear();
            _cacheRoom = "";
            _fighterSteamIds.Clear();
            _fighterCacheFrame = -1;
            _fighterCache = null;
        }

        /// <summary>Record an actor this room has rejected (unauthorized
        /// entrant / impostor). Called on EVERY client the moment the actor
        /// is classified unauthorized — before the master's CloseConnection
        /// lands — so its later departure is provably not a fighter leaving.
        ///
        /// RJ-2: a seat whose Steam ID is ON the frozen roster is NOT latched.
        /// The latch outlives the actor's properties — it is cleared by a room
        /// change, by Reset(), or by a roster write that now covers the seat
        /// (ReleaseLatchesTheRosterNowCovers) — and it exists for an UNKNOWN
        /// entrant, so latching a known fighter outlives the condition that
        /// produced it: a roster snapshot taken while that fighter happened to
        /// be absent. The live rules in IsUnauthorized still apply to them on
        /// every call, so this declines the PERMANENCE, not the rejection.
        ///
        /// This rule can only be applied with the roster THIS CALL can see. A
        /// seat rejected before the roster widened to include it is the same
        /// defect one step later in time, and the release at the roster write
        /// is where that half is closed.
        ///
        /// The impostor case keeps its latch. An actor duplicating a live
        /// roster fighter's u_id is on the roster BY STEAM ID and would
        /// otherwise be waved through here, and the latch is exactly what
        /// survives its property teardown at departure — the point being that
        /// its leave must not be read as a fighter's leave.</summary>
        internal static void RecordRejected(PhotonPlayer actor)
        {
            if (actor == null) return;
            try
            {
                EnsureCacheRoom();
                if (RosterFrozen && !IsImpostorReplicated(actor))
                {
                    string sid = SteamIdOf(actor);
                    if (!string.IsNullOrEmpty(sid) && _fighterSteamIds.Contains(sid))
                    {
                        if (_rosterLatchDeclined.Add(actor.ActorNumber))
                            Plugin.Log.LogInfo($"[ROSTER] not latching actor {actor.ActorNumber} — on the frozen roster");
                        return;
                    }
                }
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
            if (steamIds == null) { ReleaseLatchesTheRosterNowCovers(); return; }
            foreach (var s in steamIds)
                if (!string.IsNullOrEmpty(s)) _fighterSteamIds.Add(s);
            ReleaseLatchesTheRosterNowCovers();
        }

        /// <summary>Widen the frozen roster without narrowing it (RJ-2). For a
        /// mode that re-freezes per GAME rather than per room: FFA runs several
        /// games in one room, and the per-game snapshot is "who is present at
        /// this instant", so a seat between games — loading, alt-tabbed, on a
        /// slow rejoin — was dropped from the roster it was already on. From
        /// there IsUnauthorized reads true (fail-closed by design), the seat is
        /// rejected and closed, and ActiveFighters() stops returning it on
        /// every client in the room.
        ///
        /// Replace is still right for the modes that freeze ONCE per room, so
        /// they keep calling FreezeFighterRoster: a 1v1/2v2 roster taken at
        /// match start is the whole truth for that room's lifetime, and
        /// widening it there would admit entrants the freeze exists to refuse.
        ///
        /// Growth is bounded by the room: the union only ever accumulates
        /// Steam IDs that ActiveFighters() returned — i.e. seats already
        /// admitted by this room's own rules — and OnJoinedNewRoom() clears it,
        /// so nothing crosses a room boundary.</summary>
        internal static void UnionFighterRoster(IEnumerable<string> steamIds)
        {
            if (steamIds == null) return;
            foreach (var s in steamIds)
                if (!string.IsNullOrEmpty(s)) _fighterSteamIds.Add(s);
            ReleaseLatchesTheRosterNowCovers();
        }

        /// <summary>Re-evaluate every rejection latch against the roster AS IT
        /// NOW STANDS. Called from both roster writers, because the latch is a
        /// conclusion drawn from a roster and a roster change is exactly the
        /// event that can invalidate it.
        ///
        /// The defect this closes: RecordRejected (RJ-2) declines to latch a
        /// seat already ON the roster, but it can only apply that rule with the
        /// roster it has at rejection time. A seat rejected while the roster
        /// was thin — mid-load, alt-tabbed, a slow rejoin, or simply a first
        /// game it sat out — stayed latched after the next game's union added
        /// it, and IsUnauthorized tests the latch BEFORE membership, so it
        /// never got its membership tested again. The latch cleared only on a
        /// room change or Reset, so that seat was unauthorized for the rest of
        /// the room on every client.
        ///
        /// The release predicate is RecordRejected's own, re-read: on the
        /// roster, by a readable identity, and not an impostor. So this cannot
        /// admit anything the live rules in IsUnauthorized would refuse:
        ///   * unreadable identity — no release. IsUnauthorized reads an
        ///     unreadable identity as unauthorized once the roster is frozen,
        ///     so the latch and the live rule agree; nothing is lost.
        ///   * impostor — no release, same carve-out RecordRejected keeps: an
        ///     actor duplicating a live fighter's u_id is on the roster by
        ///     Steam ID and the latch is precisely what survives its property
        ///     teardown at departure.
        ///   * not in the room any more — never considered. A departed actor's
        ///     latch is what proves its leave was not a fighter's leave, and
        ///     its identity is no longer resolvable to test anyway.
        /// A narrowing freeze is handled by the same predicate for free: it
        /// asks about the roster that now exists, not about the change.</summary>
        private static void ReleaseLatchesTheRosterNowCovers()
        {
            try
            {
                EnsureCacheRoom();
                if (_rejectedActors.Count == 0) return;
                var room = PhotonNetwork.CurrentRoom;
                var players = room != null ? room.Players : null;
                if (players == null) return;
                List<int> release = null;
                foreach (var kv in players)
                {
                    var actor = kv.Value;
                    if (actor == null) continue;
                    if (!_rejectedActors.Contains(actor.ActorNumber)) continue;
                    if (IsImpostorReplicated(actor)) continue;
                    string sid = SteamIdOf(actor);
                    if (string.IsNullOrEmpty(sid)) continue;
                    if (!_fighterSteamIds.Contains(sid)) continue;
                    if (release == null) release = new List<int>();
                    release.Add(actor.ActorNumber);
                }
                if (release == null) return;
                foreach (int actorNumber in release)
                {
                    _rejectedActors.Remove(actorNumber);
                    // Not log-once: a release is a state change worth one line
                    // every time it happens, and it can legitimately happen
                    // more than once in a room.
                    Plugin.Log.LogInfo($"[ROSTER] releasing the rejection latch on actor {actorNumber} — the roster now covers them");
                }
            }
            catch { }
        }

        /// <summary>The whole per-GAME roster rule, in one place so the call
        /// site cannot hold half of it: the first roster of a room is FROZEN
        /// from a snapshot of at least two resolvable fighters, and every
        /// later game of the same room UNIONS.
        ///
        /// The two-name bar governs the freeze and not the union, and the
        /// asymmetry is the point. Freezing a one-name roster would make
        /// RosterFrozen true and turn every other seat in the room
        /// unauthorized, so the bar protects the room from a thin snapshot; a
        /// union cannot narrow anything, so a thin snapshot there is merely
        /// uninformative.</summary>
        internal static void RefreezeFighterRosterForGame(List<string> presentSteamIds)
        {
            if (RosterFrozen) UnionFighterRoster(presentSteamIds);
            else if (presentSteamIds != null && presentSteamIds.Count >= 2)
                FreezeFighterRoster(presentSteamIds);
        }

        /// <summary>The frozen roster, for logging and diagnosis. Never a
        /// membership test — IsUnauthorized carries the rule set.</summary>
        internal static int FrozenRosterSize { get { return _fighterSteamIds.Count; } }

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
            // Rejected stays rejected until the ROSTER says otherwise — the
            // cache outlives the actor's properties (design-review blocker 2),
            // which is what makes a departure provably not a fighter's. It is
            // re-evaluated at exactly one event, a roster write
            // (ReleaseLatchesTheRosterNowCovers), because that is the only
            // thing that can invalidate the conclusion. Tested BEFORE
            // membership on purpose: after departure there are no properties
            // left to test membership with.
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
        /// spectator role. Every helper below short-circuits on this, so with
        /// no spectator present they are byte-for-byte equivalent to the raw
        /// Photon reads they replace.
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
        /// Identical to PhotonNetwork.PlayerList when no spectator is in the
        /// room (including the SAME array instance, so no allocation).</summary>
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
                // for. Still fully inert in the shipped build: nothing calls
                // FreezeFighterRoster, so RosterFrozen is false everywhere.
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
}
