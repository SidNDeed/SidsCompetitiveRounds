using System;
using System.Collections.Generic;
using CompetitiveRounds;

// Bug 389 - console harness for the pure victim-choice seam.
// Compiles the real ProximityVictimSeam.cs (or a mutant copy) and runs it.
// Exit code 0 = all pass, 1 = some failed.
//
// Every test uses its OWN holder id, so the "restore the cache" mutation - which
// memoises per holder - cannot leak an answer from one test into another and
// manufacture a pass or a failure that the test did not measure.
//
//   mutation cache    : F1 must FAIL;  F2 control must PASS
//   mutation gate     : G1 must FAIL;  G2 control must PASS
//   mutation range    : F3a must FAIL; F3b control must PASS
//   mutation flat     : F8 must FAIL;  F3a control must PASS
//   mutation selpos   : F9 must FAIL;  F5 control must PASS
//   mutation misindex : F10 must FAIL; F11 control must PASS
//   mutation unread   : F14 must FAIL; F15 control must PASS
//   mutation capkey   : C1 must FAIL;  C2 control must PASS
//   mutation reason   : S1 must FAIL;  S2 control must PASS
//   mutation sqrange  : F16 must FAIL; F3a control must PASS
//   mutation fighterkeys : K1 must FAIL; K2 control must PASS
//   mutation prefixwrite : P2 must FAIL; P1 control must PASS
//
// THE SELECTION BRANCH IS CHOSEN PER MODE, because vanilla has more than one
// rule and this mod replaces one of them in FFA only. Tests that describe an FFA
// board use NearestEnemyFfa; tests that describe 2v2 or 1v2 use
// NearestEnemyTeam. Using the wrong one here would assert a rule the trigger
// never evaluated in that mode.

internal static class Program
{
    private static int _failed;
    private static int _passed;

    private static void Check(string name, bool ok, string detail)
    {
        if (ok) { _passed++; Console.WriteLine("PASS  " + name); }
        else { _failed++; Console.WriteLine("FAIL  " + name + "  -- " + detail); }
    }

    private static ProximityCandidate P(int id, int team, float x, float y, bool dead)
    {
        var c = new ProximityCandidate();
        c.Id = id; c.Team = team; c.X = x; c.Y = y; c.Z = 0f; c.Dead = dead;
        c.AnyX = x; c.AnyY = y;
        return c;
    }

    /// <summary>A candidate with a z offset, for the predicate tests.</summary>
    private static ProximityCandidate P3(int id, int team, float x, float y, float z, bool dead)
    {
        var c = P(id, team, x, y, dead);
        c.Z = z;
        return c;
    }

    /// <summary>A candidate whose rigidbody position differs from its transform
    /// position, for the NearestAny selection test.</summary>
    private static ProximityCandidate PV(int id, int team, float x, float y, float ax, float ay)
    {
        var c = P(id, team, x, y, false);
        c.AnyX = ax; c.AnyY = ay;
        return c;
    }

    /// <summary>Vanilla's CanSeePlayer is a live scene query, so the seam takes
    /// three answers rather than a bool: it can say yes, it can say no, and it
    /// can fail to answer. Only the last one defers.</summary>
    private static readonly Func<int, ProximityVision> SeesAll =
        delegate (int id) { return ProximityVision.Visible; };

    /// <summary>A candidate the marshaller could not read. It keeps its SLOT in
    /// the roster - the team branch indexes positionally - and every other field
    /// stays at its default, which is exactly what must never reach a
    /// selection.</summary>
    private static ProximityCandidate PUnreadable(int id)
    {
        var c = new ProximityCandidate();
        c.Id = id;
        c.Unreadable = true;
        return c;
    }

    private static int Main()
    {
        Console.WriteLine("=== bug 389 - victim choice and gate ===");

        // ---- F1: the defect itself. RED under the cache mutation. ----------
        // FFA shape: every player is their own team, so the own-team exclusion is
        // a self exclusion. The holder stands still; the nearest opponent changes.
        const int h1 = 100;
        var round1 = new List<ProximityCandidate> {
            P(h1, 0, 0f, 0f, false), P(101, 1, 1f, 0f, false), P(102, 2, 5f, 0f, false) };
        int first = ProximityVictim.Choose(round1, h1, 0, ProximitySelection.NearestEnemyFfa,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        var round2 = new List<ProximityCandidate> {
            P(h1, 0, 0f, 0f, false), P(101, 1, 3f, 0f, false), P(102, 2, 0.5f, 0f, false) };
        int second = ProximityVictim.Choose(round2, h1, 0, ProximitySelection.NearestEnemyFfa,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F1 Victim_FollowsHolderWhenNearestChanges",
            first == 101 && second == 102,
            "first=" + first + " (want 101) second=" + second + " (want 102)");

        // ---- F2: NEGATIVE CONTROL for the cache mutation. ------------------
        // With exactly one opponent the patched and unpatched answers are
        // identical on every call, so this stays green when the cache is put back.
        // That is what proves F1 measures the cache and not merely that Choose
        // returns something.
        const int h2 = 200;
        int a = ProximityVictim.Choose(
            new List<ProximityCandidate> { P(h2, 0, 0f, 0f, false), P(201, 1, 1f, 0f, false) },
            h2, 0, ProximitySelection.NearestEnemyFfa, 0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        int b = ProximityVictim.Choose(
            new List<ProximityCandidate> { P(h2, 0, 0f, 0f, false), P(201, 1, 2f, 0f, false) },
            h2, 0, ProximitySelection.NearestEnemyFfa, 0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F2 Victim_SingleOpponentIsUnchanged",
            a == 201 && b == 201, "a=" + a + " b=" + b + " (want 201 both)");

        // ---- F3a: the range bound. RED under the range mutation. -----------
        // The selection is measured from the HOLDER and the predicate from the
        // TRIGGER, so the nearest-to-holder candidate can be outside the ring
        // while a farther one is inside it. Vanilla evaluates ONE candidate and
        // declines. The answer must be None, NOT the farther player: searching
        // past the rejected candidate would silently widen the card.
        const int h3 = 300;
        var split = new List<ProximityCandidate> {
            P(h3, 0, 0f, 0f, false),
            P(301, 1, 1f, 0f, false),      // nearest to the holder, 9 from the trigger
            P(302, 2, 10.5f, 0f, false) }; // farther from the holder, inside the ring
        int outOfRange = ProximityVictim.Choose(split, h3, 0, ProximitySelection.NearestEnemyFfa,
            0f, 0f, 10f, 0f, 0f, 2f, SeesAll);
        Check("F3a Victim_DeclinesWhenTheChosenOneIsOutOfRange",
            outOfRange == ProximityVictim.None,
            "got " + outOfRange + " (want None; picking 302 would widen the card)");

        // ---- F3b: NEGATIVE CONTROL for the range mutation. -----------------
        // Same shape, refused for VISION instead of range, so it survives a
        // mutation that removes the range bound.
        const int h4 = 400;
        var unseen = new List<ProximityCandidate> {
            P(h4, 0, 0f, 0f, false), P(401, 1, 1f, 0f, false), P(402, 2, 2f, 0f, false) };
        int blocked = ProximityVictim.Choose(unseen, h4, 0, ProximitySelection.NearestEnemyFfa,
            0f, 0f, 0f, 0f, 0f, 4f,
            delegate (int id) { return id == 401 ? ProximityVision.Blocked : ProximityVision.Visible; });
        Check("F3b Victim_DeclinesWhenTheChosenOneIsNotVisible",
            blocked == ProximityVictim.None,
            "got " + blocked + " (want None; picking 402 would drain the one vanilla excluded)");

        // ---- F4: the under-application direction. --------------------------
        // Asserts the conservative failure direction, so a later "helpful"
        // fallback to the holder or to slot 0 reds immediately.
        const int h5 = 500;
        var allDead = new List<ProximityCandidate> {
            P(h5, 0, 0f, 0f, false), P(501, 1, 1f, 0f, true), P(502, 2, 2f, 0f, true) };
        int noneLeft = ProximityVictim.Choose(allDead, h5, 0, ProximitySelection.NearestEnemyFfa,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F4 Victim_ReturnsNoneWhenAllOpponentsDead",
            noneLeft == ProximityVictim.None, "got " + noneLeft);

        // ---- F5: the holder is never an answer. NEGATIVE CONTROL for selpos. ----
        // Vanilla's GetClosestPlayer excludes nobody, so on a TargetType.Any
        // trigger - which sits on the holder's own subtree - the holder really is
        // the nearest candidate, and the SELECTION must not narrow that. What the
        // seam must not do is hand that answer to an effect whose own rule is to
        // act on an opponent: DealDamageToPlayer would then drain the holder with
        // data.player as the damaging player, i.e. self-damage, and LifeSteal does
        // not fire on it. The answer is Defer - run vanilla, which resolves an
        // opponent itself - and NOT None, which would drop a tick vanilla applies.
        //
        // Control duty: both positions of every candidate here coincide, so a
        // mutation that selects by transform instead of velocity cannot be seen.
        const int h6 = 600;
        var anyMode = new List<ProximityCandidate> {
            P(h6, 0, 0f, 0f, false), P(601, 1, 2f, 0f, false) };
        int holderNearest = ProximityVictim.Choose(anyMode, h6, 0, ProximitySelection.NearestAny,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F5 Victim_DefersWhenAnyModeResolvesTheHolder",
            holderNearest == ProximityVictim.Defer,
            "got " + holderNearest + " (want Defer; writing the holder would invert the effect)");

        // ---- F6: fidelity - team modes exclude the whole friendly team. ----
        // 2v2 and 1v2 keep vanilla's GetClosestPlayerInTeam over the ENEMY team,
        // so a nearer teammate must never be chosen.
        const int h7 = 700;
        var teams = new List<ProximityCandidate> {
            P(h7, 0, 0f, 0f, false), P(701, 0, 0.5f, 0f, false), P(702, 1, 2f, 0f, false) };
        int enemy = ProximityVictim.Choose(teams, h7, 0, ProximitySelection.NearestEnemyTeam,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F6 Victim_EnemyModeExcludesOwnTeam",
            enemy == 702, "got " + enemy + " (want 702, not the nearer teammate 701)");

        // ---- F7: an empty board resolves to None rather than throwing. -----
        int empty = ProximityVictim.Choose(new List<ProximityCandidate>(), 800, 0,
            ProximitySelection.NearestEnemyFfa, 0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F7 Victim_EmptyBoardIsNone", empty == ProximityVictim.None, "got " + empty);

        // ---- F8: the predicate is 3D. RED under the "flat predicate" mutation. --
        // Vanilla's range test is Vector3.Distance (PlayerInRangeTrigger.cs:67).
        // Measuring it in the plane can only SHORTEN the distance, so a flat test
        // admits candidates vanilla rejects - the widening direction, which for a
        // repair that decides who takes damage is the one that costs a player the
        // match. Planar distance 3 is inside range 4; the true 3D distance is
        // sqrt(3^2 + 3^2) = 4.24, which is outside it.
        const int h8 = 900;
        var zOffset = new List<ProximityCandidate> {
            P(h8, 0, 0f, 0f, false), P3(901, 1, 3f, 0f, 3f, false) };
        int aboveRange = ProximityVictim.Choose(zOffset, h8, 0, ProximitySelection.NearestEnemyFfa,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F8 Victim_PredicateMeasuresInThreeDimensions",
            aboveRange == ProximityVictim.None,
            "got " + aboveRange + " (want None: planar 3.0 is inside range 4, 3D 4.24 is not)");

        // ---- F9: NearestAny selects on the velocity position. ------------------
        // RED under the "select by transform" mutation. Vanilla's GetClosestPlayer
        // measures data.playerVel.position (PlayerManager.cs:71), not
        // transform.position, and the two differ. 902's transform is nearer, 903's
        // rigidbody is nearer; vanilla picks 903. Both are well inside range, so
        // this test isolates the SELECTION and says nothing about the predicate.
        // The holder's own rigidbody sits far away, so this board does not reach
        // the holder rule that F5 covers.
        const int h9 = 910;
        var velocity = new List<ProximityCandidate> {
            P(h9, 0, 20f, 0f, false),
            PV(902, 1, 1f, 0f, 9f, 0f),
            PV(903, 2, 5f, 0f, 2f, 0f) };
        int byVelocity = ProximityVictim.Choose(velocity, h9, 0, ProximitySelection.NearestAny,
            0f, 0f, 0f, 0f, 0f, 8f, SeesAll);
        Check("F9 Victim_AnySelectionUsesTheVelocityPosition",
            byVelocity == 903,
            "got " + byVelocity + " (want 903: its rigidbody is nearest, though 902's transform is)");

        // ---- F10: the 2v2 selection is vanilla's, mis-index included. -----------
        // RED under the "misindex" mutation, which replaces the roster-positional
        // liveness gate with the per-candidate one a tidier loop would use.
        //
        // Outside FFA the trigger's OtherPlayer branch runs stock
        // GetClosestPlayerInTeam, which walks the ENEMY subset but reads its
        // liveness test from the GLOBAL roster at the same ordinal
        // (PlayerManager.cs:113 vs :115). Roster order here is
        // [0]=holder, [1]=dead teammate, [2]=E1, [3]=E2, so the enemy subset is
        // [E1, E2] and vanilla's loop is:
        //   i=0 -> reads players[0] (the holder, alive) -> E1 IS considered
        //   i=1 -> reads players[1] (the teammate, DEAD) -> E2 is NOT considered
        // E2 is nearer, but the trigger could not have selected it while the
        // teammate is down - the ordinary 2v1 endgame. Answering E2 here would
        // drain a player the ring never matched; answering None when E2 fails
        // vision would drop a tick vanilla applies and log it as a contradiction.
        const int h10 = 1000;
        var misIndex = new List<ProximityCandidate> {
            P(h10,  0, 0f,   0f, false),   // [0] holder, alive
            P(1001, 0, 9f,   0f, true),    // [1] teammate, DEAD
            P(1002, 1, 3.8f, 0f, false),   // [2] E1 - farther, but considered
            P(1003, 1, 2.0f, 0f, false) }; // [3] E2 - nearer, but NOT considered
        int teamPick = ProximityVictim.Choose(misIndex, h10, 0, ProximitySelection.NearestEnemyTeam,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F10 Victim_TeamModeReproducesTheRosterIndexedLivenessGate",
            teamPick == 1002,
            "got " + teamPick + " (want 1002: with roster slot 1 dead, vanilla never considers E2)");

        // ---- F11: NEGATIVE CONTROL for the misindex mutation. ------------------
        // The same board and the same branch with the teammate ALIVE. Both the
        // roster-positional gate and the per-candidate gate then admit E1 and E2
        // alike, so this test cannot tell the two apart and stays green under the
        // mutation - which is what makes F10 a measurement of the indexing
        // specifically rather than of the branch being reachable.
        const int h11 = 1100;
        var bothLive = new List<ProximityCandidate> {
            P(h11,  0, 0f,   0f, false),   // [0] holder, alive
            P(1101, 0, 9f,   0f, false),   // [1] teammate, ALIVE
            P(1102, 1, 3.8f, 0f, false),   // [2] E1
            P(1103, 1, 2.0f, 0f, false) }; // [3] E2 - nearer, and considered
        int bothPick = ProximityVictim.Choose(bothLive, h11, 0, ProximitySelection.NearestEnemyTeam,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F11 Victim_TeamModeTakesTheNearestWhenEveryGateAgrees",
            bothPick == 1103,
            "got " + bothPick + " (want 1103: with the roster whole, E2 is considered and is nearer)");

        // ---- F12: an unidentifiable holder is vanilla's call, not ours. --------
        // The holder must be known for the answer to be provably someone else.
        // When it is not, the honest outcome is Defer - not None, which would
        // cancel a tick, and not a guess.
        var unknownHolder = new List<ProximityCandidate> {
            P(1200, 0, 0f, 0f, false), P(1201, 1, 1f, 0f, false) };
        int noHolder = ProximityVictim.Choose(unknownHolder, ProximityVictim.None, 0,
            ProximitySelection.NearestEnemyFfa, 0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F12 Victim_DefersWhenTheHolderCannotBeIdentified",
            noHolder == ProximityVictim.Defer, "got " + noHolder + " (want Defer)");

        // ---- F13: Defer and None are distinct answers. -------------------------
        // They instruct the caller to do opposite things - run vanilla, or apply
        // nothing - so a refactor that collapses them must red here rather than
        // silently turn every deferral into a dropped tick.
        Check("F13 Sentinels_DeferIsNotNone",
            ProximityVictim.Defer != ProximityVictim.None,
            "Defer=" + ProximityVictim.Defer + " None=" + ProximityVictim.None);

        // ---- G1: the gate is load-bearing. RED under the gate mutation. ----
        // Flip the capability predicate to false and the repair must be inert, so
        // the gate is demonstrably load-bearing rather than decorative.
        Check("G1 Gate_RefusesWhenRoomNotCapable",
            ProximityVictim.ShouldRepair(false, true) == false,
            "a room that does not all carry the fix must stay on vanilla");

        // ---- G2: NEGATIVE CONTROL for the gate mutation. -------------------
        // The own-player branch has no cross-player lookup and no defect, so it
        // stays vanilla whatever the room advertises. Survives a mutation that
        // drops the capability term.
        Check("G2 Gate_RefusesWhenEffectTargetsOwnPlayer",
            ProximityVictim.ShouldRepair(true, false) == false,
            "the own-player branch caches data.player and must stay vanilla");

        Check("G3 Gate_AllowsWhenCapableAndTargetingOther",
            ProximityVictim.ShouldRepair(true, true), "should repair");


        // ---- F14: an unreadable roster entry defers the WHOLE resolution. ------
        // RED under the "unread" mutation, which drops the refusal and lets the
        // entry through at its defaults.
        //
        // This is the r1 HIGH. The marshaller cannot always read a roster entry -
        // a destroyed Player, a missing CharacterData, a missing rigidbody - and
        // an entry that arrives with its fields defaulted is NOT the entry
        // vanilla's own loop read. Team is the sharpest: a defaulted team of zero
        // puts the entry into whichever subset the enemy-team branch walks, so ONE
        // unread entry changes which candidates that branch even considers.
        //
        // Roster here is [0]=holder(t0), [1]=UNREADABLE, [2]=E1(t1) at 3,
        // [3]=E2(t1) at 2. If [1] is admitted at its defaults it reads as an alive
        // team-0 entry, the positional liveness gate then admits E2, and the seam
        // answers E2 - a player it has no evidence the trigger matched. The
        // correct answer is Defer: vanilla resolves its own victim, which costs
        // one tick of today's shipped behaviour and one log line.
        const int h14 = 1400;
        var unreadable = new List<ProximityCandidate> {
            P(h14,  0, 0f,   0f, false),
            PUnreadable(1401),
            P(1402, 1, 3f,   0f, false),
            P(1403, 1, 2f,   0f, false) };
        int unread = ProximityVictim.Choose(unreadable, h14, 0, ProximitySelection.NearestEnemyTeam,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F14 Victim_DefersWhenARosterEntryIsUnreadable",
            unread == ProximityVictim.Defer,
            "got " + unread + " (want Defer; 1403 means a defaulted team decided the subset)");

        // ---- F15: NEGATIVE CONTROL for the unread mutation. --------------------
        // The same board with slot 1 READ - and dead, which is the state the
        // unreadable entry used to be marshalled as. No entry carries the flag, so
        // this test cannot see the mutation, which is what leaves F14 measuring
        // the flag itself rather than the branch being reachable.
        const int h15 = 1500;
        var readable = new List<ProximityCandidate> {
            P(h15,  0, 0f,   0f, false),
            P(1501, 0, 9f,   0f, true),
            P(1502, 1, 3f,   0f, false),
            P(1503, 1, 2f,   0f, false) };
        int readOk = ProximityVictim.Choose(readable, h15, 0, ProximitySelection.NearestEnemyTeam,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F15 Victim_ResolvesNormallyWhenEveryEntryIsReadable",
            readOk == 1502,
            "got " + readOk + " (want 1502: roster slot 1 is dead, so E2 is never considered)");

        // ---- F16: the predicate arms at exact overlap. -------------------------
        // RED under the "sqrange" mutation, which compares squares instead.
        //
        // Vanilla is `Vector3.Distance(...) < range * root.localScale.x`
        // (PlayerInRangeTrigger.cs:58-67). Squaring is monotonic in exact
        // arithmetic but not in float: for a small enough positive range the
        // product underflows to zero, and `0 >= 0` then refuses a candidate
        // standing exactly on the trigger while vanilla's `0 < range` arms. A
        // repair that decides who takes damage answers in vanilla's own domain
        // with vanilla's own operator, rather than one that agrees almost
        // everywhere.
        const int h16 = 1600;
        var overlap = new List<ProximityCandidate> {
            P(h16,  0, 0f, 0f, false),
            P(1601, 1, 5f, 0f, false) };
        int atOverlap = ProximityVictim.Choose(overlap, h16, 0, ProximitySelection.NearestEnemyTeam,
            0f, 0f, 5f, 0f, 0f, 1e-23f, SeesAll);
        Check("F16 Victim_ArmsAtExactOverlapForATinyRange",
            atOverlap == 1601,
            "got " + atOverlap + " (want 1601: distance 0 < range, which vanilla arms on)");

        // ---- F17: an unanswerable vision query defers, it does not refuse. -----
        // "It threw" is a different fact from "it said no". Treating the two
        // alike would suppress a tick vanilla applies and log it as a
        // contradiction, which is a false statement about the call.
        const int h17 = 1700;
        var sightless = new List<ProximityCandidate> {
            P(h17,  0, 0f, 0f, false), P(1701, 1, 1f, 0f, false) };
        int noSight = ProximityVictim.Choose(sightless, h17, 0, ProximitySelection.NearestEnemyTeam,
            0f, 0f, 0f, 0f, 0f, 4f,
            delegate (int id) { return ProximityVision.Unreadable; });
        Check("F17 Victim_DefersWhenTheVisionQueryCannotBeAnswered",
            noSight == ProximityVictim.Defer,
            "got " + noSight + " (want Defer, not None: None would drop a tick vanilla applies)");

        // ---- C1: the capability cache re-derives on a same-frame change. -------
        // RED under the "capkey" mutation, which drops the change stamp from the
        // key and leaves the frame alone.
        //
        // An actor can join, an actor can leave, and a property delivery can land
        // inside one frame - one PUN Dispatch drains several with no frame
        // boundary between them. A cached TRUE that survives such a change says
        // "every seat in this room carries the repair" about a room that has since
        // changed, and this gate decides whether seats re-resolve the victim.
        var cache1 = new ProximityCapabilityCache();
        bool capBefore = cache1.Evaluate(7, 1, delegate { return true; });
        bool capAfter = cache1.Evaluate(7, 2, delegate { return false; });
        Check("C1 Cache_ReDerivesWhenTheRoomChangesInsideAFrame",
            capBefore && !capAfter,
            "before=" + capBefore + " after=" + capAfter + " (want true then false)");

        // ---- C2: NEGATIVE CONTROL for the capkey mutation. ---------------------
        // With BOTH key terms unchanged the answer must be reused, and the census
        // run exactly once. A frame-only key reuses it here too, so this control
        // cannot see the mutation - which is what makes C1 a measurement of the
        // stamp specifically and not of caching in general.
        var cache2 = new ProximityCapabilityCache();
        int censusRuns = 0;
        Func<bool> counting = delegate { censusRuns++; return true; };
        bool reuse1 = cache2.Evaluate(11, 4, counting);
        bool reuse2 = cache2.Evaluate(11, 4, counting);
        Check("C2 Cache_ReusesTheAnswerWhenNothingChanged",
            reuse1 && reuse2 && censusRuns == 1,
            "runs=" + censusRuns + " (want 1) answers=" + reuse1 + "/" + reuse2);

        // ---- C3: a cache with no census answers the inert way. -----------------
        // A missing census is an unreadable input, and the gate's false direction
        // costs one tick of vanilla.
        Check("C3 Cache_WithoutACensusIsInert",
            new ProximityCapabilityCache().Evaluate(1, 1, null) == false,
            "a cache with nothing to ask must not report a capable room");

        // ---- S1: every outcome and every reason gets its own budget. -----------
        // RED under the "reason" mutation, which drops the reason from the key.
        //
        // A feature that is INACTIVE and a feature that is active and declining
        // must not produce the same silence (#438/#443). Three outcomes and one
        // reason each is the whole requirement: a stale-cache fallback has to be
        // distinguishable in the log from a repair with nothing to do.
        string kDefer = ProximityVictim.SignalKey("DealDamageToPlayer", "defer", "a roster entry could not be read");
        string kDefer2 = ProximityVictim.SignalKey("DealDamageToPlayer", "defer", "the holder is not on the roster");
        string kRefuse = ProximityVictim.SignalKey("DealDamageToPlayer", "refuse", "a roster entry could not be read");
        string kInactive = ProximityVictim.SignalKey("DealDamageToPlayer", "inactive", "a roster entry could not be read");
        Check("S1 Signals_EachOutcomeAndReasonGetsItsOwnBudget",
            kDefer != kDefer2 && kDefer != kRefuse && kDefer != kInactive && kRefuse != kInactive,
            "keys collided: " + kDefer + " | " + kDefer2 + " | " + kRefuse + " | " + kInactive);

        // ---- S2: NEGATIVE CONTROL for the reason mutation. ---------------------
        // The LINE keeps naming all three things whatever the key does, so this
        // stays green when the key drops the reason.
        string line = ProximityVictim.SignalText("StunPlayer", "defer", "no owning trigger");
        Check("S2 Signals_TheLineNamesSiteOutcomeAndReason",
            line.Contains("StunPlayer") && line.Contains("defer") && line.Contains("no owning trigger"),
            "got " + line);

        // ---- S3: one line per reason, not one per tick. ------------------------
        Check("S3 Signals_AreBoundedToOnePerReason",
            ProximityVictim.MaxOutcomeSignals == 1,
            "got " + ProximityVictim.MaxOutcomeSignals + " (a per-tick effect may not repeat itself)");

        // ---- K1: the fighter capability list carries this key. -----------------
        // RED under the "fighterkeys" mutation, which empties the list.
        //
        // Photon player properties persist across rooms (#182), so a seat that
        // fought a match and then joins one to watch still advertises whatever it
        // last set. A spectator simulates none of a fighter's effects and is
        // excluded from the census that reads this key, so the key must be cleared
        // in the same pre-join merge that sets the spectator role. The list lives
        // here because the staging code loops over it - a key added here cannot be
        // forgotten there.
        bool carriesProx = false;
        foreach (var key in ProximityVictim.FighterCapabilityKeys)
            if (key == ProximityVictim.CapabilityProp) carriesProx = true;
        Check("K1 Capability_SpectatorStagingClearsTheProximityKey",
            carriesProx && ProximityVictim.FighterCapabilityKeys.Length > 0,
            "the key a spectator must stop advertising is not in the cleared set");

        // ---- K2: NEGATIVE CONTROL for the fighterkeys mutation. ----------------
        // The key's NAME carries the protocol version and is read by peers; it is
        // unaffected by what the cleared set contains, so it survives the
        // mutation.
        Check("K2 Capability_KeyIsTheVersionedName",
            ProximityVictim.CapabilityProp == "cr_prox1" && ProximityVictim.CapabilityValue == 1,
            "got " + ProximityVictim.CapabilityProp + "=" + ProximityVictim.CapabilityValue);

        // ---- P1: Defer runs vanilla untouched. NEGATIVE CONTROL for prefixwrite. --
        // Defer means this seam has no standing to answer, so nothing is written
        // and the original runs. Unaffected by a mutation to the Victim branch.
        Check("P1 Prefix_DeferRunsVanillaUntouched",
            ProximityVictim.PrefixAction(ProximityResolution.Defer, false) == ProximityPrefixAction.RunVanillaUntouched
            && ProximityVictim.PrefixAction(ProximityResolution.Defer, true) == ProximityPrefixAction.RunVanillaUntouched,
            "a deferral must neither write vanilla's field nor skip the original");

        // ---- P2: the field is written ONLY with a victim in hand. --------------
        // RED under the "prefixwrite" mutation, which drops the victim term.
        // Vanilla dereferences the field with no null guard
        // (DealDamageToPlayer.cs:45, StunPlayer.cs:27, TeleportToOpponent.cs:24).
        Check("P2 Prefix_NeverWritesWithoutAVictim",
            ProximityVictim.PrefixAction(ProximityResolution.Victim, false) == ProximityPrefixAction.SkipOriginal
            && ProximityVictim.PrefixAction(ProximityResolution.Refuse, true) == ProximityPrefixAction.SkipOriginal,
            "only a resolved victim may be written into vanilla's own field");

        // ---- P3: the run decision is order-independent against a sibling. ------
        // StunPlayer.Go carries a second, unrelated prefix
        // (PerfPatches.StunPlayerGoNullGuard) and neither declares a priority, so
        // their order is undefined. HarmonyX calls EVERY prefix regardless of what
        // a sibling returned and ANDs the returns into __runOriginal (#352), so
        // the run decision is a conjunction - and a conjunction commutes. This
        // exercises both orders over the real decision function for every
        // resolution, and asserts the only write stays on the accepting branch.
        //
        // It is green by construction rather than a mutation target: what a
        // mutation could reach is the WRITE, which P2 measures. The remaining
        // half - a future edit making either prefix read the field the other
        // writes - is recorded as a residual on the patch class itself.
        bool orderStable = true;
        bool writeOnlyOnAccept = true;
        var resolutions = new[] { ProximityResolution.Victim, ProximityResolution.Refuse, ProximityResolution.Defer };
        foreach (var res in resolutions)
            foreach (bool known in new[] { true, false })
                foreach (bool siblingRuns in new[] { true, false })
                {
                    ProximityPrefixAction act = ProximityVictim.PrefixAction(res, known);
                    bool oursRuns = act != ProximityPrefixAction.SkipOriginal;
                    // HarmonyX ANDs both returns into __runOriginal whichever ran
                    // first; the two orders below are the same conjunction.
                    bool oursFirst = oursRuns && siblingRuns;
                    bool siblingFirst = siblingRuns && oursRuns;
                    if (oursFirst != siblingFirst) orderStable = false;
                    if (act == ProximityPrefixAction.WriteVictimAndRun && !(res == ProximityResolution.Victim && known))
                        writeOnlyOnAccept = false;
                }
        Check("P3 Prefix_RunDecisionIsOrderIndependentWithASiblingPrefix",
            orderStable && writeOnlyOnAccept,
            "orderStable=" + orderStable + " writeOnlyOnAccept=" + writeOnlyOnAccept);

        Console.WriteLine("=== passed=" + _passed + " failed=" + _failed + " ===");
        return _failed == 0 ? 0 : 1;
    }
}
