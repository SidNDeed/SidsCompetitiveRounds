using System;
using System.Collections.Generic;
using System.Globalization;
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
    /// ── THE INERTNESS GUARANTEE, AND WHOSE IT IS ───────────────────────
    /// The guarantee is about the FIGHTER views, and precisely about the
    /// three that carry a short-circuit of their own — `ActiveFighters()`,
    /// `ActiveFighterCount()` and `OtherActiveFighterCount()`. While no actor
    /// in the room carries the spectator role property AND no roster is
    /// frozen, each of those three returns exactly what the raw Photon call
    /// it replaced returns, in the same ORDER (ActorNumber ascending —
    /// reporter election and slot mapping depend on ordering determinism), so
    /// migrating such a call site to RoomActors is a provable no-op until a
    /// spectator joins or a match freezes. That is what made it safe to
    /// migrate the ~40 sites listed in the design doc BEFORE the spectator
    /// seat itself existed. `OtherActiveFighters()` has no short-circuit of
    /// its own — it always builds its result from `ActiveFighters()` — so it
    /// inherits the conditions rather than stating them.
    ///
    /// BOTH conditions are load-bearing, and only a room that is BOTH
    /// spectator-free and unfrozen is inert, which is not a competitive
    /// match: every one of those freezes its roster. An earlier headline here
    /// named the spectator condition alone, which the PRECISION line below
    /// already contradicted, and a reader who stopped there would have
    /// believed it (headline corrected 2026-09-18, Codex b4yssbnuh).
    ///
    /// PRECISION (Codex round 2): the fast path is "no spectator AND no frozen
    /// roster". CORRECTED — the inertness claim that used to stand here said
    /// nothing calls FreezeFighterRoster, so RosterFrozen was false everywhere.
    /// That is no longer true and has not been for some time: GameStateWatcher
    /// freezes the roster in OnMatchStarted and in TickSpectateAttest's
    /// code-room catch-up, and again once per FFA game in OnFfaMatchStarted
    /// (the per-game refreeze, which freezes a room not yet frozen and
    /// unions into one that is), so RosterFrozen IS true in
    /// real queue and code rooms and these helpers DO diverge from raw
    /// PlayerList there. Spectators are live as well: cr_spec is staged as a
    /// pre-join property (SpectatorSession.StagePreJoinProperties; corrected
    /// 2026-09-17). The divergence is the point of freezing and is
    /// deliberate — once a roster is frozen, a non-spectator actor is a
    /// fighter only if it is ON that roster — but it is a live behaviour, not
    /// a dormant one, and any
    /// caller reasoning about what these helpers return must assume a frozen
    /// roster rather than the inert case (#302/#351).
    ///
    /// The divergence is fail-CLOSED: an actor off the roster, or one whose
    /// identity cannot be read, is dropped. That is the safe direction for a
    /// rating-bearing roster and the UNSAFE direction for anything that needs
    /// "every actor that could be running X" — such a caller must walk
    /// PlayerList itself rather than reuse this helper under the opposite
    /// polarity (#412).
    ///
    /// It is NOT a claim about the spectator views. `Spectators()`,
    /// `SpectatorCount()` and `MasterIsSpectator()` short-circuit on
    /// `AnySpectatorPresent()` alone and deliberately never test the freeze;
    /// each says so at its own declaration (#302 / #432). An earlier revision
    /// stated the guarantee across all of them without qualification, which
    /// was never true of the spectator three.
    ///
    /// A consumer that must see the RAW roster - the bug-391 roster census
    /// is one - reads PhotonNetwork.PlayerList itself rather than relying on
    /// these helpers being inert.
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

        /// <summary>The ActorNumbers that were IN THE ROOM when the roster was
        /// taken. The roster is the set of seats that snapshot could RESOLVE;
        /// this is the set of actors that were there to be resolved.
        ///
        /// It exists because the two differ, and the difference is the whole
        /// r2 HIGH: a seat mid-load, or one whose u_id had not been delivered
        /// yet, is in the second set and not the first — a fighter the
        /// snapshot could not read, not a late entrant. A seat in NEITHER was
        /// not in the room when the roster was taken, which is what the freeze
        /// means by "late". Photon never reuses an ActorNumber inside a room,
        /// so this cannot alias a later joiner onto an earlier seat.
        ///
        /// Lifetime is the ROOM's, not the roster's: it is cleared on a room
        /// change alongside the rejection latches, because an actor number
        /// from a previous incarnation says nothing about this one. A room
        /// change without a re-freeze therefore leaves the widening able to
        /// re-list roster members and nothing else, which is the fail-closed
        /// direction.</summary>
        private static readonly HashSet<int> _assemblyActors = new HashSet<int>();

        /// <summary>Whether this room's assembly window has been taken. NOT
        /// "is the set non-empty": a window taken in a room the census could
        /// not read is an EMPTY window that has still been taken, and the
        /// difference decides whether a later freeze may re-take it. Cleared
        /// exactly where the set is.</summary>
        private static bool _assemblyCaptured = false;

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
                // Actor numbers belong to ONE room incarnation, so this goes
                // with the latches and not with the roster. Keeping it would
                // let an actor number from the previous room admit a stranger
                // to this one's widening. The flag clears WITH the set: a new
                // room's first freeze must be able to take a new window.
                _assemblyActors.Clear();
                _assemblyCaptured = false;
                _cacheRoom = room;
                // A new room is the largest roster change there is - every
                // actor is replaced - so it moves the generation like any
                // other. A consumer that keys a cached answer on this counter
                // would otherwise be able to carry a previous room's answer
                // across the boundary.
                _rosterGeneration++;
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
            _assemblyActors.Clear();
            _assemblyCaptured = false;
            _cacheRoom = "";
            _fighterSteamIds.Clear();
            _fighterCacheFrame = -1;
            _fighterCache = null;
            // The roster is GONE, which is a change consumers keyed on this
            // counter have to see. Clearing a cache tells the next reader to
            // read again; moving the counter is what tells a reader that
            // CACHED an answer against it that the answer is void.
            NoteRosterIdentityChange();
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
            // The assembly window opens with the room and closes with the
            // FIRST snapshot taken in it: the actors present at that instant
            // are the ones the roster was taken from, whether or not their
            // identity could be read. A later freeze does not re-open it —
            // see CaptureAssemblyActors for why that direction is the unsafe
            // one. The CAPTURE is therefore idempotent after the first; the
            // roster write on the line above is not, and this method still
            // REPLACES the roster every time it is called. Only the per-game
            // widening reads the window, so a second freeze in a 1v1/2v2 room
            // keeping the first window changes nothing there.
            CaptureAssemblyActors();
            if (steamIds == null) { ReleaseLatchesTheRosterNowCovers(); return; }
            foreach (var s in steamIds)
                if (!string.IsNullOrEmpty(s)) _fighterSteamIds.Add(s);
            ReleaseLatchesTheRosterNowCovers();
        }

        /// <summary>Record every actor the room holds right now. Identity is
        /// deliberately NOT required: an actor whose u_id has not arrived is
        /// exactly the seat this set exists to remember.
        ///
        /// ONCE PER ROOM, and the decision is
        /// <see cref="RosterCensusRules.ShouldCaptureAssembly"/>'s so that the
        /// harness RUNS it rather than this file asserting it. The window is a
        /// property of the ROOM's assembly, not of whichever call froze last,
        /// and the widening's entire discriminator is "was this actor here
        /// when the roster was taken". A second freeze re-taking the window
        /// would move that instant FORWARD, and every actor that joined in
        /// between would become admissible at the next game boundary — the
        /// late entrant the freeze exists to refuse. Re-taking is the
        /// fail-OPEN direction and is refused; keeping the first window is
        /// fail-closed and its cost is the stated residual (a seat that joins
        /// after the assembly is never admitted by the widening).</summary>
        private static void CaptureAssemblyActors()
        {
            try
            {
                EnsureCacheRoom();
                if (!RosterCensusRules.ShouldCaptureAssembly(_assemblyCaptured)) return;
                _assemblyCaptured = true;
                _assemblyActors.Clear();
                var room = PhotonNetwork.CurrentRoom;
                var players = room != null ? room.Players : null;
                if (players == null) return;
                foreach (var kv in players)
                    if (kv.Value != null) _assemblyActors.Add(kv.Value.ActorNumber);
            }
            catch { }
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
        /// WHAT BOUNDS THE GROWTH — stated as it now is, not as it was. This
        /// used to read "the union only ever accumulates Steam IDs that
        /// ActiveFighters() returned — i.e. seats already admitted by this
        /// room's own rules". That described a census this method's only
        /// production feeder stopped using in the same commit that wrote the
        /// feeder: RefreezeFighterRosterForGameFromRoom feeds from
        /// <see cref="RawActorCensus"/>, which by design applies NEITHER the
        /// latch test NOR the roster test — being unfiltered is the whole
        /// point of it. Nothing upstream of here filters anything.
        ///
        /// The narrowing that bounds this set is
        /// <see cref="RosterCensusRules.UnionCensus"/>'s, and it lives there:
        /// spectators and impostors out, unreadable identities out, and once
        /// the roster is frozen only actors already ON the roster or present
        /// in the room when the roster was taken. It is NOT redundant
        /// belt-and-braces — delete it and this method admits every actor the
        /// room holds, including one that joined after the freeze, which is
        /// the single thing the freeze exists to refuse (rostercensus case 2,
        /// control r8).
        ///
        /// A room boundary bounds the other axis: OnJoinedNewRoom clears the
        /// roster and EnsureCacheRoom clears the assembly window, so nothing
        /// accumulated here crosses into the next room.</summary>
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
        /// asks about the roster that now exists, not about the change.
        ///
        /// THE CENSUS IS RAW (Codex client r2 HIGH). Both this and the widening
        /// read <see cref="RawActorCensus"/>, which applies no roster test and
        /// no latch test. Reading ActiveFighters() here — or feeding the
        /// widening from it — is the circularity the r2 round named: it filters
        /// through IsUnauthorized, which tests the latch FIRST, so the actor
        /// whose latch is being decided is removed from the evidence before it
        /// is weighed.</summary>
        /// <summary>V3 P4.4: the same release, called by a readmission lobby's
        /// grant change (FfaLateEntry.OnGrantedChanged).</summary>
        internal static void ReleaseCoveredLatches()
        {
            ReleaseLatchesTheRosterNowCovers();
        }

        private static void ReleaseLatchesTheRosterNowCovers()
        {
            try
            {
                EnsureCacheRoom();
                if (_rejectedActors.Count == 0) return;
                // The RAW census, never ActiveFighters(): that view applies
                // IsUnauthorized, which tests the latch first, so it removes
                // the very actor this is deciding about (r2 HIGH). The
                // predicate itself is RosterCensusRules', which the rules
                // harness RUNS.
                var release = RosterCensusRules.LatchesToRelease(
                    RawActorCensus(), _rejectedActors, _fighterSteamIds);
                if (release.Count == 0) return;
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

        /// <summary>Every actor the room holds, reduced to the four facts the
        /// roster rules use. NO roster test and NO latch test: this is the
        /// evidence those two decisions are made FROM, and a census that has
        /// already applied either of them cannot inform the other.</summary>
        private static IList<RosterCensusRules.Actor> RawActorCensus()
        {
            var census = new List<RosterCensusRules.Actor>();
            try
            {
                var room = PhotonNetwork.CurrentRoom;
                var players = room != null ? room.Players : null;
                if (players == null) return census;
                foreach (var kv in players)
                {
                    var actor = kv.Value;
                    if (actor == null) continue;
                    census.Add(new RosterCensusRules.Actor(
                        actor.ActorNumber, SteamIdOf(actor),
                        IsSpectator(actor), IsImpostorReplicated(actor)));
                }
            }
            catch { }
            return census;
        }

        /// <summary>The per-game roster write, census included, so the CALL
        /// SITE cannot hold half the rule — which is exactly how the r2 HIGH
        /// shipped: GameStateWatcher built the census out of ActiveFighters()
        /// and handed it in, and no amount of correctness in here could undo a
        /// census that had already dropped the seat in question.
        ///
        /// Returns the census it used, so the caller's log line reports the
        /// number this actually wrote from rather than one it recomputed.</summary>
        internal static List<string> RefreezeFighterRosterForGameFromRoom()
        {
            var raw = RawActorCensus();
            var census = RosterCensusRules.UnionCensus(
                raw, _fighterSteamIds, _assemblyActors, RosterFrozen);
            RefreezeFighterRosterForGame(census);
            return census;
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
        /// every capability quorum (the saw and grow quorums, the weapon-cooldown
        /// and proximity-victim quorums, PoisonSync's capability census and its
        /// roster-quarantine edge gates), and the DC census. Keep
        /// <see cref="IsSpectator"/> where the answer is LOCAL to
        /// this seat or GRANTS a role that only this seat acts on: the master
        /// client's spectator validation and kick, the face re-send, the
        /// spectator render/ownership predicates. Those are decisions one seat
        /// takes alone, and a seat disagreeing with another about them costs
        /// nothing but this seat's own view.</para>
        ///
        /// <para>PoisonSync USED to be listed here as a cache caller, on the
        /// reading that its roster "grants authority". That was wrong, and the
        /// sentence is corrected rather than quietly deleted (#302):
        /// <c>ScanRoster</c> decides a fail-closed capability REFUSAL — an
        /// unmarked actor makes every seat read INCAPABLE — and a refusal that
        /// must agree across seats is exactly the first case above. Two seats
        /// caching different first-sight answers there split the sticky
        /// incapability flag, the roster quarantine and victim-side block
        /// honouring, which changes fighter damage. It reads the replicated
        /// property now.</para></summary>
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

        /// <summary>The locked roster's slot of a Steam id, -1 when absent.</summary>
        private static int LockedRosterSlotOf(string sid)
        {
            try
            {
                var roster = ApiClient.FfaLockedRoster;
                if (roster == null || string.IsNullOrEmpty(sid)) return -1;
                for (int i = 0; i < roster.Count; i++)
                    if (roster[i] != null && roster[i].steam_id == sid) return i;
            }
            catch { }
            return -1;
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
                // V3 P4.2 identity, the kind r conjunct: in a readmission room an
                // actor whose u_id names a seat with a kind r epoch entry is a
                // fighter only if it is that entry's actor, whether or not the
                // seat's old actor is still present.
                if (FfaAssembly.ReadmitLobby)
                {
                    var kindR = FfaReadmitEntryRules.KindRUnauthorized(actor.ActorNumber, LockedRosterSlotOf(sid),
                                                                       FfaLateEntry.Record);
                    if (kindR.HasValue) return kindR.Value;
                }
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
        /// spectator role.
        ///
        /// WHICH HELPERS TEST WHAT. The FIGHTER views —
        /// <see cref="ActiveFighters"/>, <see cref="ActiveFighterCount"/> and
        /// <see cref="OtherActiveFighterCount"/> — short-circuit on this AND
        /// on an unfrozen roster, so with no spectator present and no frozen
        /// roster they are byte-for-byte equivalent to the raw Photon reads
        /// they replace, and once a match has frozen its roster that
        /// short-circuit stops applying, spectator or no spectator. The
        /// SPECTATOR views — <see cref="Spectators"/>,
        /// <see cref="SpectatorCount"/> and <see cref="MasterIsSpectator"/> —
        /// short-circuit on THIS ALONE and deliberately do not consult the
        /// freeze: a frozen roster does not create or remove a spectator, so
        /// testing it there would narrow an answer that is already correct.
        /// An earlier revision of this remark claimed both conditions for all
        /// of the helpers beneath it, which was never true of the spectator
        /// three; each helper now states its own condition where it stands
        /// (#302 / #432).
        /// With a roster frozen the fighter views are not raw-equivalent, and
        /// that is the ordinary case in a competitive match (corrected
        /// 2026-09-18, Codex b4yssbnuh).
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
        ///
        /// The raw PhotonNetwork.PlayerList array comes back unchanged — the
        /// SAME instance, no allocation — only when no spectator is present AND
        /// the roster is not frozen. This line used to promise that identity
        /// whenever no spectator was in the room, which is false for every
        /// competitive match: FreezeFighterRoster runs from
        /// GameStateWatcher.OnMatchStarted and from TickSpectateAttest's
        /// code-room catch-up, and through the per-game FFA refreeze in
        /// OnFfaMatchStarted when the room is not yet frozen, and a frozen roster takes
        /// the filtering path below, which allocates and can return fewer
        /// actors than PlayerList holds, spectator or not (#302/#351;
        /// corrected 2026-09-18, Codex b4yssbnuh).</summary>
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
                // R3 (LOW): the filter must ALSO apply with a frozen roster -
                // otherwise freezing {A,B} and then admitting a late actor C
                // with no spectator in the room returned C as a fighter,
                // defeating the freeze in exactly the case it exists for
                // (GameStateWatcher freezes at match assembly, OnMatchStarted;
                // at late identity resolution, TickSpectateAttest's code-room
                // catch-up; and once per FFA game, OnFfaMatchStarted; #302).
                // Item 13 (connect-failure V11): while a gated room's game
                // runs, an actor the kept-actor view rejects is no fighter
                // either. The same-instance fast path is gone: with no filter
                // the result is PlayerList's own actors, cached per frame like
                // the filtered one.
                //
                // NOTE FOR ANYONE REACHING FOR THIS AS A CENSUS: the result
                // has IsUnauthorized applied, so it already excludes every
                // latched actor. It is the right answer to "who is playing"
                // and the wrong input to any decision ABOUT a latch or about
                // roster membership - see RoomActors.RawActorCensus and the
                // r2 HIGH it closes.
                bool filter = AnySpectatorPresent() || RosterFrozen || FfaLateEntry.GatedRunning;
                var keep = new List<PhotonPlayer>(10);
                foreach (var actor in PhotonNetwork.PlayerList)
                {
                    if (filter && !FfaLateEntry.IsKeptActor(actor.ActorNumber)) continue;
                    if (filter && IsSpectator(actor)) continue;
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
                    // IsUnauthorized carries the whole rule set: roster
                    // membership, fail-closed identity, AND the duplicate-u_id
                    // impostor exclusion (r3 CRITICAL).
                    if (filter && RosterFrozen && IsUnauthorized(actor)) continue;
                    keep.Add(actor);
                }
                keep.Sort((a, b) => a.ActorNumber.CompareTo(b.ActorNumber));
                var result = keep.ToArray();
                _fighterCache = result;
                _fighterCacheFrame = Time.frameCount;
                return result;
            }
            catch { return _emptyActors; }
        }

        /// <summary>Every present actor that is not a spectator,
        /// ActorNumber-ascending: the room's players with neither the
        /// frozen-roster filter nor the quarantine (connect-failure V11, item
        /// 2's census feed, and the counts a seat that sits out reads).</summary>
        internal static List<PhotonPlayer> PresentNonSpectators()
        {
            var keep = new List<PhotonPlayer>();
            try
            {
                if (!PhotonNetwork.InRoom) return keep;
                var room = PhotonNetwork.CurrentRoom;
                if (room == null || room.Players == null) return keep;
                foreach (var kv in room.Players)
                    if (kv.Value != null && !IsSpectator(kv.Value)) keep.Add(kv.Value);
                keep.Sort((a, b) => a.ActorNumber.CompareTo(b.ActorNumber));
            }
            catch { }
            return keep;
        }

        /// <summary>The kept bodies (item 13): PlayerManager's players whose
        /// current owner actor the kept-actor view accepts, in list order.</summary>
        internal static List<global::Player> KeptPlayers()
        {
            return FfaLateEntry.KeptPlayers();
        }

        /// <summary>Fighter count. THE replacement for
        /// PhotonNetwork.CurrentRoom.PlayerCount at every site that meant
        /// "how many people are playing". Returns room.PlayerCount unchanged
        /// only when no spectator is present AND the roster is unfrozen;
        /// otherwise it counts <see cref="ActiveFighters"/>, which is what
        /// keeps the two in agreement.</summary>
        internal static int ActiveFighterCount()
        {
            try
            {
                if (!PhotonNetwork.InRoom) return 0;
                var room = PhotonNetwork.CurrentRoom;
                if (room == null) return 0;
                // No fast path while a gated room's game runs (item 13).
                if (FfaLateEntry.GatedRunning) return ActiveFighters().Length;
                if (!AnySpectatorPresent() && !RosterFrozen) return room.PlayerCount;   // fast path
                // Same frozen-roster rule as ActiveFighters — this count feeds
                // quorum and start decisions, so the two MUST agree.
                return ActiveFighters().Length;
            }
            catch { return 0; }
        }

        /// <summary>Fighters other than the local client — the "peers I must
        /// wait for / talk to" set. Used by sync-peer counting, opponent
        /// resolution and capability consensus. It has no short-circuit of its
        /// own: it always goes through <see cref="ActiveFighters"/> and
        /// inherits both of that helper's conditions.</summary>
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

        /// <summary>Fighter count excluding the local client. Same pair of
        /// conditions as <see cref="ActiveFighterCount"/>: the PlayerCount
        /// arithmetic is taken only when no spectator is present AND the
        /// roster is unfrozen.</summary>
        internal static int OtherActiveFighterCount()
        {
            try
            {
                if (!PhotonNetwork.InRoom) return 0;
                var room = PhotonNetwork.CurrentRoom;
                if (room == null) return 0;
                // Item 13: while a gated room's game runs, no fast path, and the
                // local seat is subtracted only when it is kept.
                if (FfaLateEntry.GatedRunning)
                    return Math.Max(0, ActiveFighterCount()
                                       - (!LocalIsSpectator && FfaLateEntry.IsKeptActor(PhotonNetwork.LocalPlayer.ActorNumber) ? 1 : 0));
                if (!AnySpectatorPresent() && !RosterFrozen)
                    return Math.Max(0, room.PlayerCount - 1);  // fast path
                return Math.Max(0, ActiveFighterCount() - (LocalIsSpectator ? 0 : 1));
            }
            catch { return 0; }
        }

        /// <summary>Spectator actors, ActorNumber-ascending. Empty in every
        /// room that has none. This helper short-circuits on spectator
        /// absence ALONE and does not consult the frozen roster: a freeze
        /// neither creates nor removes a spectator, so testing it here would
        /// narrow an answer that is already correct.</summary>
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

        /// <summary>Spectator count. Goes through <see cref="Spectators"/>
        /// and inherits its one condition; it does not consult the frozen
        /// roster either.</summary>
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
        /// a spectator, i.e. a transfer is required. Short-circuits on
        /// spectator absence alone, like the other two spectator views, and
        /// does not consult the frozen roster.</summary>
        internal static bool MasterIsSpectator()
        {
            try
            {
                if (!PhotonNetwork.InRoom) return false;
                // Item 13 (connect-failure V11): a master this client does not
                // keep needs the transfer too (the authority fence).
                if (!FfaLateEntry.MasterKept()) return true;
                // Spectator absence alone: with no spectator in the room the
                // master cannot be one. The freeze is not part of this
                // question.
                if (!AnySpectatorPresent()) return false;
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
    /// census". The next ELECTION rule change takes <c>cr_dc4</c> — <c>cr_dc3</c>
    /// is already spent on the outcome protocol below — so a mixed room drops to
    /// the floor election everywhere rather than running two rules at once. There
    /// was no <c>cr_dc1</c>: the number is the election generation, and the
    /// generation before this one advertised nothing at all.</para>
    ///
    /// <para>AND NO GENERATION OF IT HAS SHIPPED. <c>cr_dc2</c> is on no released
    /// tree — not <c>main</c>, not <c>origin/main</c>, not the production pin — so
    /// every build a player can be running today advertises NOTHING on this key.
    /// That is what makes the census arm's own refusal the one that decides a real
    /// mixed room: this build beside any shipped build sees a survivor without
    /// <c>cr_dc2</c>, refuses the census arm, and every seat runs the floor
    /// election. It is written down because the paragraph below used to reason from
    /// the opposite premise (#302).</para>
    ///
    /// <para>TWO KEYS, TWO RULES, AND WHAT THE SECOND ONE DOES AND DOES NOT BUY
    /// TODAY. <c>cr_dc2</c> is the ELECTION generation; <c>cr_dc3</c> is the
    /// OUTCOME-PROTOCOL generation. They are separate because they gate different
    /// things, and folding a wire generation and a capability into one constant is
    /// the shape that broke compatibility in both directions once already (#604).
    /// The previous wording justified the split by saying that re-keying
    /// <c>cr_dc2</c> "would drop rooms to the floor election for no reason" — true
    /// only of a key that has shipped, and this one has not.</para>
    ///
    /// <para>SO, EXACTLY. On this tree both keys are written in ONE
    /// <c>SetCustomProperties</c> merge and withdrawn in one, by the only builds
    /// that have either, so a seat carries BOTH or NEITHER. The outcome quorum is
    /// therefore DOMINATED by the election quorum on the one path that reaches it:
    /// <c>ArmFallback</c> is called only from the census arm, which has already
    /// required <c>cr_dc2</c> of the same seat list, so the outcome quorum cannot
    /// refuse a room the election gate did not already refuse. It is kept because
    /// the gate then belongs to the OPERATION rather than to one caller's
    /// discipline (#432), and because that domination rests on today's single merge
    /// and on nothing stronger — split the two writes, add a caller that arms
    /// outside the census arm, or ship one key ahead of the other, and the outcome
    /// quorum becomes the only thing between two generations' <c>cr_dcr</c> values.
    /// What it is NOT is evidence that a mixed-version 2v2 has been exercised: its
    /// refusal branch is unreachable from any room a player can assemble today, so
    /// the absence of its log line proves nothing (#342). See
    /// <c>OutcomeCapabilityProp</c>.</para>
    ///
    /// <para>FAIL-CLOSED on every arm — a disabled mod, a staging failure, a
    /// survivor without the property, an empty survivor list (every(∅) must not
    /// apply) — and what "closed" costs here is only the floor election, i.e.
    /// the behaviour that shipped (#430).</para></summary>
    internal static class DcReportSync
    {
        internal const string CapabilityProp = "cr_dc2";
        internal const int CapabilityValue = 1;

        /// <summary>The OUTCOME protocol's own whole-room capability: "this seat
        /// runs the round-3 <c>cr_dcr</c> rules". It gates the FALLBACK WATCH and
        /// nothing else.
        ///
        /// <para>WHY THE OUTCOME PROTOCOL NEEDED ITS OWN KEY. The values carried on
        /// <c>cr_dcr</c> changed meaning incompatibly without the property that
        /// advertises them changing, so two generations could read each other's
        /// values as their own. The generation before this one published
        /// <c>no</c> for a report whose attempts went UNANSWERED — a transaction
        /// that may still be running server-side — and this generation treats
        /// <c>no</c> as terminal and fires on it. A watcher on this build reading
        /// that seat's <c>no</c> would post a zero-total report beside a live
        /// transaction, which is the ordering defect the whole protocol exists to
        /// remove. The generation before THAT published nothing at all on this
        /// property and ran an independent +45 s timer, which this build cannot
        /// observe or stand down.</para>
        ///
        /// <para>WHAT THE KEY BUYS, EXACTLY: the watch arms only where every
        /// fighter seat present advertises <c>cr_dc3</c>, so every <c>cr_dcr</c>
        /// value this seat ever ACTS on was written by a process running these
        /// rules. In any mixed room this seat arms nothing and posts nothing, and
        /// says which seat lacked the key.</para>
        ///
        /// <para>AND WHAT IT DOES NOT BUY TODAY: reachability. Neither key is on a
        /// released tree, both are written in one pre-join merge, and the only
        /// caller of <c>ArmFallback</c> has already taken the <c>cr_dc2</c> quorum
        /// over the same seat list — so on this tree the outcome quorum cannot
        /// refuse a room the election quorum did not already refuse. The class note
        /// above states that in full; it is repeated here so this summary is not
        /// read as a certificate that mixed-version rooms were exercised
        /// (#342).</para>
        ///
        /// <para>AND WHAT IT DOES NOT CHANGE: publishing, which stays unconditional.
        /// The reason is simpler than the one this paragraph used to give, and the
        /// old one asserted behaviour of builds in the field that no tree supports.
        /// <c>cr_dcr</c> is parsed by NO released build — the property is on neither
        /// <c>main</c>, nor <c>origin/main</c>, nor the production pin — so against
        /// every build a player can be running today the value published here is one
        /// nobody reads. The only readers of <c>cr_dcr</c> are commits on this
        /// branch, and among those the three-token generation (before <c>unk</c>
        /// existed) reads an unknown token as "nothing published" and posts nothing,
        /// which is the same decision this build makes. Both statements are about
        /// THIS branch's history, not about a deployed parser, because there is no
        /// deployed parser. Once a build carrying <c>cr_dcr</c> does ship, a later
        /// change to this value set must re-derive whether publication may stay
        /// unconditional instead of reading it off here (#302, #351).</para></summary>
        internal const string OutcomeCapabilityProp = "cr_dc3";
        internal const int OutcomeCapabilityValue = 1;

        private static bool _staged, _stageFailedPermanently, _deferLogged;

        /// <summary>Stage PRE-JOIN only. An in-room write is present locally
        /// immediately and may reach peers after they have already evaluated a
        /// census — a silently false-capable seat, which is the one state this
        /// protocol must not be in. Idle client states provably precede the join
        /// op's parameter snapshot (#287, same reasoning as PoisonSync).
        ///
        /// <para>AND NOT BEFORE THE COMPATIBILITY VERDICT. The verdict lands about
        /// three seconds into the process (Plugin.DoInitialize), and a join inside
        /// that window used to snapshot <c>cr_dc2=1</c> from a seat that the verdict
        /// then disabled — leaving the only correction an IN-ROOM revoke, the exact
        /// write this protocol forbids. Staging now WAITS for the verdict: the tick
        /// retry stages it a few ticks later, and a join that beats the verdict
        /// simply plays that room on the floor election. What the refusal costs is
        /// one room's census arm, which is the behaviour every older peer in the
        /// room is running anyway (#430). The deferral is LOGGED rather than
        /// silent — an unstaged capability and a capability whose staging was
        /// refused are different facts (#342), and the deferred line is what a
        /// bundle is read for. Same gate as GrowNormalize.StageCapability, which is
        /// where the shape comes from.</para></summary>
        internal static void StageCapability(string source)
        {
            try
            {
                if (_staged || _stageFailedPermanently) return;
                if (Plugin.modDisabled) { _stageFailedPermanently = true; return; }
                if (!Plugin.compatCheckComplete)
                {
                    if (!_deferLogged)
                    {
                        _deferLogged = true;
                        Plugin.Log.LogInfo("[2v2-DC] deferred staging " + CapabilityProp
                            + " (" + source + ") — the compatibility verdict is not in yet; "
                            + "a room joined before it plays the floor election, and the tick "
                            + "stages this once the verdict clears");
                    }
                    return;
                }
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
                // BOTH keys in ONE merge, so a seat is never visible as capable of
                // one rule and unknown on the other: the two are written by the same
                // process under the same verdict, and a peer that can see one must be
                // able to see the other in the same join snapshot.
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable
                {
                    { CapabilityProp, CapabilityValue },
                    { OutcomeCapabilityProp, OutcomeCapabilityValue }
                });
                _staged = true;
                Plugin.Log.LogInfo("[2v2-DC] staged " + CapabilityProp + "=" + CapabilityValue
                    + " " + OutcomeCapabilityProp + "=" + OutcomeCapabilityValue
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
                    { CapabilityProp, 0 },
                    { OutcomeCapabilityProp, 0 }
                });
                Plugin.Log.LogWarning("[2v2-DC] revoked " + CapabilityProp + " and "
                    + OutcomeCapabilityProp
                    + " — mod disabled, floor election everywhere and no fallback watch");
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[2v2-DC] revoke failed: " + ex.Message); }
        }

        /// <summary>One actor's advertisement of ONE of this class's keys, read from
        /// the replicated property every time. Anything that is not the exact integer
        /// value — absent, null props, a revoked 0, a type we did not write — is NOT
        /// capable. Parameterised by key on purpose: both capabilities are read by
        /// the same rule, so a change to what "capable" means cannot apply to one and
        /// miss the other (#432).</summary>
        internal static bool CapableOf(PhotonPlayer actor, string prop, int value)
        {
            try
            {
                if (actor == null || string.IsNullOrEmpty(prop)) return false;
                var props = actor.CustomProperties;
                if (props == null) return false;
                object v;
                if (!props.TryGetValue(prop, out v)) return false;
                return (v is int) && (int)v == value;
            }
            catch { return false; }
        }

        /// <summary>The ELECTION capability (<c>cr_dc2</c>) for one actor.</summary>
        internal static bool Capable(PhotonPlayer actor)
        {
            return CapableOf(actor, CapabilityProp, CapabilityValue);
        }

        /// <summary>The OUTCOME-PROTOCOL capability (<c>cr_dc3</c>) for one actor.</summary>
        internal static bool OutcomeCapable(PhotonPlayer actor)
        {
            return CapableOf(actor, OutcomeCapabilityProp, OutcomeCapabilityValue);
        }

        /// <summary>True only when EVERY seat in <paramref name="seats"/> advertises
        /// the named key. <paramref name="missingActor"/> names the first that does
        /// not, for the log line — the same shape the other three protocols report.
        /// An empty or null list is NOT capable: every(∅) must not apply.</summary>
        internal static bool AllCapableOf(List<PhotonPlayer> seats, string prop, int value,
                                          out int missingActor)
        {
            missingActor = -1;
            if (seats == null || seats.Count == 0) return false;
            bool all = true;
            for (int i = 0; i < seats.Count; i++)
            {
                var a = seats[i];
                if (a == null) { all = false; continue; }
                if (CapableOf(a, prop, value)) continue;
                all = false;
                if (missingActor < 0) missingActor = a.ActorNumber;
            }
            return all;
        }

        /// <summary>True only when EVERY survivor advertises the ELECTION
        /// capability.</summary>
        internal static bool AllCapable(List<PhotonPlayer> survivors, out int missingActor)
        {
            return AllCapableOf(survivors, CapabilityProp, CapabilityValue, out missingActor);
        }

        /// <summary>True only when EVERY seat listed advertises the OUTCOME-PROTOCOL
        /// capability — the quorum the fallback watch arms on.</summary>
        internal static bool AllOutcomeCapable(List<PhotonPlayer> seats, out int missingActor)
        {
            return AllCapableOf(seats, OutcomeCapabilityProp, OutcomeCapabilityValue,
                                out missingActor);
        }

        // ── the elected seat's prompt-report outcome, and the fallback it gates ──
        //
        // WHY THIS EXISTS AT ALL. The census arm elects exactly one PROMPT
        // reporter, which removes the arrival race — and with it the accidental
        // redundancy the previous OR'd election had. If that one seat's request
        // never lands, the series stays `active` and every survivor keeps a live
        // 2v2 hold until its lease TTL expires. Something has to stand behind it.
        //
        // WHY IT IS NOT A TIMER. The first repair armed the other non-DC survivor
        // with a delayed post at +45 s, chosen to sit past the prompt seat's
        // nominal retry budget (3 x 10 s timeout + 2 x 2 s backoff). That is an
        // ELAPSED-TIME guess about somebody else's transaction, and Unity's
        // `timeout` is not a hard ceiling under a stalled socket: a last attempt
        // completing after the delayed post makes the arrival order decide a rated
        // completion versus `dc_incomplete` again — the exact defect the census
        // arm exists to close. No number is the right number, because the quantity
        // being guessed is not a duration.
        //
        // WHAT REPLACES IT. The fallback fires on a TERMINAL OUTCOME of the
        // elected seat's transaction and on nothing else. The elected seat
        // publishes that outcome as a replicated player property, `cr_dcr`, tagged
        // with the series it describes:
        //
        //   <series>:send  dispatched — a request is or may be in flight. NOT
        //                  terminal: the fallback waits.
        //   <series>:ok    the server ANSWERED (any 2xx — completed,
        //                  dc_incomplete, or ignored because the series was
        //                  already settled or the room fence refused it).
        //                  TERMINAL: the fallback stands down permanently.
        //   <series>:no    every attempt was ANSWERED and refused, or nothing ever
        //                  left that seat's process at all. Nothing landed and
        //                  nothing is still running. TERMINAL the other way: the
        //                  fallback fires.
        //   <series>:unk   at least one attempt was sent and got NO answer. NOT
        //                  terminal, and this is the distinction the first version
        //                  of this table got wrong: `request.timeout` is a
        //                  client-side deadline that abandons our end of the
        //                  connection. It never reaches the server and it does not
        //                  cancel the handler, which goes on running and can commit
        //                  minutes later. A seat that announced `no` on a timeout
        //                  was announcing a terminal outcome of a transaction that
        //                  was still live, and the fallback posted beside it.
        //
        // EVERY OTHER STATE IS SILENCE, AND SILENCE IS NOT A SIGNAL. The elected
        // seat present and saying nothing, and the elected seat LEAVING having said
        // nothing, both leave this seat posting nothing at all. The second of those
        // used to fire, on the reasoning that a seat which never dispatched has
        // nothing in flight. The reasoning is sound and the conclusion is still
        // wrong, because it prices only the transaction this watch was armed on:
        // the elected seat's DEPARTURE IS ITSELF A DISCONNECT. Photon delivers it to
        // every remaining seat, the election runs again for it against the SAME
        // series, and some seat posts a REAL-TOTALS prompt report about it — from a
        // process this watch has no property from and no view into. Firing here puts
        // a zero-total report next to a real one and hands the outcome back to
        // arrival order, which is the defect the whole census arm exists to close.
        //
        // WHERE NO TERMINAL OUTCOME IS KNOWN, THIS SEAT POSTS NOTHING. That is the
        // direction the unhandled case must fail (#276), and what the refusal costs
        // is a series that closes late — the elected seat's own request, or the
        // server's lease expiry and the admin path — rather than one that closes
        // wrongly (#430). The cost is paid in four states now, not one, and each of
        // them says so in the log rather than falling through in silence.
        //
        // AND THE FORM. When it does fire, the fallback posts ZERO point totals.
        // The deployed endpoint reaches its lead-forfeit branch only when
        // `total_points >= 2` (backend/api/main.py at 0cc7f75), so the only row
        // state a fallback can ever reach is `status='dc_incomplete'`: it can never
        // BE the report that rates a series. It bounds the damage; it does not by
        // itself make ordering irrelevant, and the earlier wording here that said it
        // did was overclaiming. A fallback that takes the row lock FIRST writes
        // `dc_incomplete`, and a real-totals report behind it is answered
        // `{"ignored": true}` — a rated lead-forfeit lost. The form and the signal
        // table are two halves of one rule: the table is what keeps a fallback and a
        // prompt report from ever being in flight together, the form is what bounds
        // the outcome if some path this seat cannot see ever puts them there.
        //
        // WHAT THE CLIENT HALF STILL CANNOT CLOSE, named rather than papered over: a
        // SECOND disconnect in the same series opens a prompt-report path this watch
        // was never armed on and holds no property for. The rules above remove every
        // schedule this seat can observe — it will not fire while its own elected
        // seat's transaction may be live, and it will not fire on that seat's
        // departure — but two disconnects arriving close together on DIFFERENT seats
        // are not orderable from inside any one client. Closing that needs the
        // server to refuse to settle on a zero-total report while a real one may
        // still arrive; the rule is written out as a server-lane note with this
        // round (endpoint, lock, predicate, what the check rejects) and is NOT
        // claimed here as though it were already deployed.
        //
        // The zeros withdrawn in the previous round are a different rule and stay
        // withdrawn: those were posted by EVERY seat whenever the census failed on
        // ANY seat, so the leaver's own surviving team-mate could force them for the
        // whole room by withholding one property. This one is reachable only by the
        // elected seat — a member of the ABANDONED team — failing to deliver its own
        // report. The party with a motive to suppress a forfeit is on the other
        // team and has no lever on it (#283).
        internal const string OutcomeProp = "cr_dcr";
        internal const string OutcomeSent = "send";
        internal const string OutcomeAnswered = "ok";
        internal const string OutcomeFailed = "no";
        /// <summary>An attempt went unanswered; a handler may still be running.
        /// The generation that predates this value — an earlier commit on THIS
        /// branch, not a build in the field: <c>cr_dcr</c> is on no released tree —
        /// reads it as none of the three tokens it knows and falls through to "post
        /// nothing", the same decision this build makes. Said as branch history
        /// rather than as a property of a deployed parser, which is what the
        /// previous wording asserted and no tree supports (#302).</summary>
        internal const string OutcomeUnknown = "unk";

        private static string _watchSeries;
        private static int _watchActor = -1;
        private static string _watchReporter, _watchDc, _watchRoom;
        private static string _watchOutcome = "";
        private static bool _watchGone, _watchSettled, _watchHeldLogged, _watchWaitLogged;

        /// <summary>The series tag that scopes an outcome value: the WHOLE
        /// series id, trimmed and lower-cased, never a prefix of it. A `cr_dcr`
        /// written for the PREVIOUS series must never read as an answer about
        /// this one — the property is retained on the actor and a sitting can run
        /// several series.
        ///
        /// <para>The tag used to be the first eight characters, so two distinct
        /// series ids sharing those eight carried the same tag: a retained `ok`
        /// from the earlier series stood this watch down, and a retained `no`
        /// fired it, about a series that value never described. Nothing the
        /// server does makes a shared prefix impossible — its route parses the
        /// id as a UUID, and parsing says nothing about how the id was
        /// generated — so the whole id is the key. Two ids give the same tag
        /// only when they differ in letter case or surrounding whitespace, which
        /// is the same id.</para></summary>
        private static string Tag(string seriesId)
        {
            if (string.IsNullOrEmpty(seriesId)) return "";
            return seriesId.Trim().ToLowerInvariant();
        }

        /// <summary>Elected seat only: announce where its own report has got to.
        /// An in-room write, deliberately — unlike a CAPABILITY, which has to be in
        /// the join snapshot before any peer evaluates a census, this is a fact
        /// PRODUCED in the room, after the event it describes, and the seats that
        /// read it are reacting to its arrival rather than sampling it at a moment
        /// of their own choosing.</summary>
        internal static void PublishOutcome(string seriesId, string outcome)
        {
            try
            {
                string tag = Tag(seriesId);
                if (tag.Length == 0 || string.IsNullOrEmpty(outcome)) return;
                var local = PhotonNetwork.LocalPlayer;
                if (local == null || !PhotonNetwork.InRoom) return;
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable
                {
                    { OutcomeProp, tag + ":" + outcome }
                });
                Plugin.Log.LogInfo("[2v2-DC] published " + OutcomeProp + "=" + tag + ":" + outcome
                    + " — the seats behind this report read their next move from it");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[2v2-DC] publishing " + OutcomeProp + " failed: " + ex.Message);
            }
        }

        /// <summary>This actor's announced outcome FOR THIS SERIES, or "" when it
        /// has announced nothing about it. Anything unparseable, or tagged with
        /// another series, is "" — never a terminal answer. The tag compared is
        /// the whole series id (see <see cref="Tag"/>), so a value published for
        /// a different series that only shares a prefix with this one is "" as
        /// well. The value is split at its LAST colon: no outcome token carries
        /// one, so everything before it is the tag exactly as it was
        /// published.</summary>
        internal static string OutcomeOf(PhotonPlayer actor, string seriesId)
        {
            try
            {
                string tag = Tag(seriesId);
                if (actor == null || tag.Length == 0) return "";
                var props = actor.CustomProperties;
                if (props == null) return "";
                object v;
                if (!props.TryGetValue(OutcomeProp, out v)) return "";
                string s = v as string;
                if (string.IsNullOrEmpty(s)) return "";
                int i = s.LastIndexOf(':');
                if (i <= 0 || i + 1 >= s.Length) return "";
                if (!string.Equals(s.Substring(0, i), tag, StringComparison.Ordinal)) return "";
                string o = s.Substring(i + 1);
                return (o == OutcomeSent || o == OutcomeAnswered
                        || o == OutcomeFailed || o == OutcomeUnknown) ? o : "";
            }
            catch { return ""; }
        }

        /// <summary>The non-elected non-DC survivor arms the watch and posts
        /// NOTHING. Every later move comes from <see cref="Evaluate"/>.
        ///
        /// <para>THE QUORUM IS TAKEN HERE, at the one place a watch can come into
        /// existence, rather than at the call site: a gate that lives in the caller
        /// is a property of that caller's discipline, and the next caller inherits
        /// nothing (#432). <paramref name="fighterSeats"/> is the fighter seats
        /// present when the disconnect was observed — the same census list the
        /// election ran on. A departed seat is deliberately not in it: it can publish
        /// nothing and post nothing, so requiring a key of it would refuse the watch
        /// over a seat that cannot affect the outcome, and a guard is judged by what
        /// its refusal costs (#430).</para></summary>
        internal static void ArmFallback(string seriesId, PhotonPlayer elected,
                                         string reporterSteamId, string dcSteamId,
                                         string observedRoom, List<PhotonPlayer> fighterSeats)
        {
            try
            {
                if (string.IsNullOrEmpty(seriesId) || elected == null
                    || string.IsNullOrEmpty(reporterSteamId) || string.IsNullOrEmpty(dcSteamId))
                {
                    Plugin.Log.LogWarning("[2v2-DC] fallback NOT armed — the elected seat or the "
                        + "report's own fields could not be resolved; this seat posts nothing");
                    return;
                }
                // THE MIXED-ROOM REFUSAL. Arm only where every fighter seat present
                // advertises the OUTCOME-protocol key, so every cr_dcr value this
                // watch can ever act on was written by a process running these rules.
                // A seat without it is either publishing the previous generation's
                // values — where `no` also meant "an attempt went unanswered", a
                // transaction that may still be running — or publishing nothing on
                // this property at all while running a schedule of its own. Neither
                // is observable from here, so the room is not one this watch can be
                // right about.
                //
                // WHAT IT CAN AND CANNOT CATCH TODAY, because this branch is easy to
                // read as proof that a mixed-version 2v2 is handled, and it is not.
                // On this tree cr_dc2 and cr_dc3 are written in ONE merge and
                // withdrawn in one, and NEITHER is on a released tree — so a seat
                // carries both or neither. This method has exactly one caller, the
                // census arm in Plugin.OnPlayerLeftRoom, which has already required
                // cr_dc2 of the SAME seat list. So this refusal cannot fire on a room
                // a player can assemble: the state it names, a peer advertising one
                // key without the other, exists only across commits on this branch.
                // The REAL mixed room — this build beside a shipped one — is decided
                // upstream by the census arm's own refusal, and nothing here
                // contributes to that outcome. Its absence from a bundle is expected
                // and proves nothing either way (#342).
                //
                // It is kept anyway, and not as belt-and-braces: the gate belongs to
                // the OPERATION rather than to one caller's discipline (#432), so a
                // second caller, a split of the staging merge, or one key shipping
                // ahead of the other cannot silently arm this watch on another
                // generation's values.
                //
                // The refusal SPEAKS, once, and names the seat: a watch that was
                // refused and a watch that was never reached are different facts.
                // What it costs is the same cost already paid in four other states —
                // a series that closes on the elected seat's own report, or on the
                // server's lease expiry and the admin path, instead of one that
                // closes wrongly (#276, #430).
                int missingOutcome;
                if (!AllOutcomeCapable(fighterSeats, out missingOutcome))
                {
                    Plugin.Log.LogInfo("[2v2-DC] fallback NOT armed — "
                        + (missingOutcome >= 0
                            ? "actor " + missingOutcome.ToString(CultureInfo.InvariantCulture)
                            : "a fighter seat")
                        + " does not advertise " + OutcomeCapabilityProp + ", so this room is running "
                        + "more than one outcome protocol and a " + OutcomeProp + " value from it "
                        + "would not mean what this build reads it as. This seat posts NOTHING for "
                        + "this series and publishes " + OutcomeProp + " as usual — a property no "
                        + "released build parses at all, so publishing it can mislead nobody");
                    return;
                }
                _watchSeries = seriesId;
                _watchActor = elected.ActorNumber;
                _watchReporter = reporterSteamId;
                _watchDc = dcSteamId;
                _watchRoom = observedRoom ?? "";
                _watchOutcome = OutcomeOf(elected, seriesId);   // it may already have spoken
                _watchGone = false;
                _watchSettled = false;
                _watchHeldLogged = false;
                _watchWaitLogged = false;
                Plugin.Log.LogInfo("[2v2-DC] fallback armed on actor "
                    + _watchActor.ToString(CultureInfo.InvariantCulture) + " — no timer: it fires on ONE "
                    + "signal only, " + OutcomeProp + "=" + OutcomeFailed + " (every attempt of that "
                    + "seat's report answered and refused, or nothing ever left its process), and then "
                    + "only in the zero-total form. WHAT THAT FORM IS RECORDED AS depends on the box "
                    + "that answers and is read out of the answer, never assumed. On the route this "
                    + "client is built against the park is ONE ANSWER AMONG SEVERAL, not a property "
                    + "of the route: three exits are reached before any total is read and NONE of "
                    + "them parks anything — a row already settled, a report naming a room this "
                    + "series does not own, and a roomless report inside the post-resume window — "
                    + "and each of those three says so with ignored=true beside deferred=false. Past "
                    + "all three the route marks the row and answers deferred=true "
                    + "before any total is read, leaving the series open for a real-totals report. "
                    + "A box predating that field answers a 200 with no deferred key, and what "
                    + "it did with the report is not carried in a missing key. " + OutcomeProp + "="
                    + OutcomeUnknown + ", that seat leaving, and that seat staying silent all post "
                    + "NOTHING");
                Evaluate("armed");
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[2v2-DC] arming the fallback failed: " + ex.Message); }
        }

        /// <summary>Wired to OnPlayerPropertiesUpdate: the elected seat has spoken.</summary>
        internal static void NoteActorProps(PhotonPlayer actor)
        {
            try
            {
                if (_watchSeries == null || actor == null || actor.ActorNumber != _watchActor) return;
                string o = OutcomeOf(actor, _watchSeries);
                if (o.Length == 0) return;
                _watchOutcome = o;
                Evaluate("outcome " + o);
            }
            catch { }
        }

        /// <summary>Wired to OnPlayerLeftRoom: the elected seat is gone. Its
        /// property payload is still on the object Photon hands us, so latch the
        /// last thing it said BEFORE deciding what its absence means.</summary>
        internal static void NoteActorLeft(PhotonPlayer actor)
        {
            try
            {
                if (_watchSeries == null || actor == null || actor.ActorNumber != _watchActor) return;
                string o = OutcomeOf(actor, _watchSeries);
                if (o.Length > 0) _watchOutcome = o;
                _watchGone = true;
                Evaluate("the elected seat left the room");
            }
            catch { }
        }

        /// <summary>The watch is a fact of ONE room and one series. Called on every
        /// room edge, the same three the saw verdict line is reset on.</summary>
        internal static void ResetForRoomChange()
        {
            _watchSeries = null; _watchActor = -1;
            _watchReporter = null; _watchDc = null; _watchRoom = null;
            _watchOutcome = ""; _watchGone = false; _watchSettled = false;
            _watchHeldLogged = false; _watchWaitLogged = false;
        }

        private static void Evaluate(string why)
        {
            if (_watchSeries == null || _watchSettled) return;
            if (_watchOutcome == OutcomeAnswered)
            {
                _watchSettled = true;
                Plugin.Log.LogInfo("[2v2-DC] fallback stood down (" + why + ") — the elected seat's "
                    + "report was ANSWERED by the server; the series is settled or the server has "
                    + "refused both seats' reports alike, and a second one changes nothing");
                return;
            }
            if (_watchGone)
            {
                // CHECKED BEFORE OutcomeFailed, not after, and the ordering is the
                // rule rather than a detail. A seat that published `no` and then
                // left is observed in ONE callback — NoteActorLeft latches the last
                // thing it said and reports the departure together — and that
                // departure is itself a disconnect in this same series: the election
                // runs again for it in the very next statements of
                // Plugin.OnPlayerLeftRoom, and a REAL-TOTALS prompt report about it
                // is composed in a process this seat holds no property from. Firing
                // on the stale `no` would put a zero-total post beside that one and
                // hand the outcome back to arrival order. Whatever the seat had
                // said, its absence is now the more recent fact.
                _watchSettled = true;
                Plugin.Log.LogInfo("[2v2-DC] fallback STOOD DOWN (" + why + ") — the elected seat "
                    + "left with " + OutcomeProp + "="
                    + (_watchOutcome.Length == 0 ? "<nothing published>" : _watchOutcome)
                    + ". Its departure is a new disconnect in this same series and the election runs "
                    + "again for it, so a real-totals report is the thing that closes the series now; "
                    + "a zero-total post beside it would decide the outcome by arrival order");
                return;
            }
            if (_watchOutcome == OutcomeFailed)
            {
                _watchSettled = true;
                Fire("the elected seat's report failed on every attempt with every attempt ANSWERED ("
                     + OutcomeProp + "=" + OutcomeFailed + "), and that seat is still in the room, so "
                     + "its departure has not opened a second report path for this series");
                return;
            }
            if (_watchOutcome == OutcomeUnknown)
            {
                // The seat SAID it does not know. An attempt of its report went
                // unanswered, so a handler may still be running on the server and
                // may still write. Not terminal, and never made terminal by waiting.
                if (_watchHeldLogged) return;
                _watchHeldLogged = true;
                Plugin.Log.LogInfo("[2v2-DC] fallback WITHHELD (" + why + ") — the elected seat "
                    + "published " + OutcomeProp + "=" + OutcomeUnknown + ": an attempt of its report "
                    + "went UNANSWERED, so a handler may still be running server-side and may still "
                    + "commit. Its client-side timeout abandoned the connection, it did not cancel "
                    + "the transaction. This seat posts nothing");
                return;
            }
            // The elected seat is still here and has said nothing, or has said only
            // `send`. Enumerated on purpose: a silent fall-through here was a state
            // no bundle could tell apart from a watch that had never been armed.
            if (_watchWaitLogged) return;
            _watchWaitLogged = true;
            Plugin.Log.LogInfo("[2v2-DC] fallback WAITING (" + why + ") — the elected seat is still "
                + "in the room with " + OutcomeProp + "="
                + (_watchOutcome.Length == 0 ? "<nothing published>" : _watchOutcome)
                + ". No terminal outcome is known, so this seat posts nothing and keeps watching. If "
                + "that seat never speaks, the series closes on the server's lease expiry and the "
                + "admin path rather than on a report this seat guessed at");
        }

        /// <summary>Post the fallback. NO PRE-CHECK.
        ///
        /// <para>The previous round asked GET /team/series/{id}/state first, to post
        /// only while the series was still open. That endpoint is not a read: its
        /// first arm cancels a series outright, and every condition it cancels on is
        /// reachable by a healthy, partly-played 2v2 — see the block that replaced
        /// the probe in ApiClient. The pre-check meant to make this safe was the
        /// most destructive thing in the path.</para>
        ///
        /// <para>Nothing replaces it, because the report endpoint already answers
        /// the same question ATOMICALLY and under the row lock: it re-reads the row
        /// FOR NO KEY UPDATE and returns `{"ignored": true}` without writing unless
        /// the status is still active/dc_paused. A separate read could only have
        /// been right about a moment that had already passed by the time the post
        /// went out.</para></summary>
        private static void Fire(string reason)
        {
            string series = _watchSeries, reporter = _watchReporter, dc = _watchDc, room = _watchRoom;
            Plugin.Log.LogInfo("[2v2-DC] fallback POSTING — " + reason
                + ". ZERO point totals, which is the only form the deployed endpoint can record as "
                + "dc_incomplete and can never turn into a rated completion. No status pre-check: the "
                + "report endpoint re-reads the row FOR NO KEY UPDATE and ignores a settled series "
                + "itself, and the state endpoint that looks like a read CANCELS series");
            try
            {
                ApiClient.ReportTeamSeriesDc(series, reporter, dc, 0, 0, room, true);
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[2v2-DC] fallback dispatch failed: " + ex.Message); }
        }
    }
}
