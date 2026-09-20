using System;
using System.Collections.Generic;
using CompetitiveRounds;

// Bug 389 HELD-BACK FIX - scratch harness for the pure victim-choice seam.
// Compiles the real ProximityVictimSeam.cs (or a mutant copy) and runs it.
// Exit code 0 = all pass, 1 = some failed.
//
// Every test uses its OWN holder id, so the "restore the cache" mutation - which
// memoises per holder - cannot leak an answer from one test into another and
// manufacture a pass or a failure that the test did not measure.
//
//   mutation cache : F1 must FAIL; F2 control must PASS
//   mutation gate  : G1 must FAIL; G2 control must PASS
//   mutation range : F3a must FAIL; F3b control must PASS

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

    private static readonly Func<int, bool> SeesAll = delegate (int id) { return true; };

    private static int Main()
    {
        Console.WriteLine("=== bug 389 held-back fix - victim choice and gate ===");

        // ---- F1: the defect itself. RED under the cache mutation. ----------
        // FFA shape: every player is their own team, so the own-team exclusion is
        // a self exclusion. The holder stands still; the nearest opponent changes.
        const int h1 = 100;
        var round1 = new List<ProximityCandidate> {
            P(h1, 0, 0f, 0f, false), P(101, 1, 1f, 0f, false), P(102, 2, 5f, 0f, false) };
        int first = ProximityVictim.Choose(round1, h1, 0, ProximitySelection.NearestEnemy,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        var round2 = new List<ProximityCandidate> {
            P(h1, 0, 0f, 0f, false), P(101, 1, 3f, 0f, false), P(102, 2, 0.5f, 0f, false) };
        int second = ProximityVictim.Choose(round2, h1, 0, ProximitySelection.NearestEnemy,
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
            h2, 0, ProximitySelection.NearestEnemy, 0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        int b = ProximityVictim.Choose(
            new List<ProximityCandidate> { P(h2, 0, 0f, 0f, false), P(201, 1, 2f, 0f, false) },
            h2, 0, ProximitySelection.NearestEnemy, 0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
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
        int outOfRange = ProximityVictim.Choose(split, h3, 0, ProximitySelection.NearestEnemy,
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
        int blocked = ProximityVictim.Choose(unseen, h4, 0, ProximitySelection.NearestEnemy,
            0f, 0f, 0f, 0f, 0f, 4f, delegate (int id) { return id != 401; });
        Check("F3b Victim_DeclinesWhenTheChosenOneIsNotVisible",
            blocked == ProximityVictim.None,
            "got " + blocked + " (want None; picking 402 would drain the one vanilla excluded)");

        // ---- F4: the under-application direction. --------------------------
        // Asserts the conservative failure direction, so a later "helpful"
        // fallback to the holder or to slot 0 reds immediately.
        const int h5 = 500;
        var allDead = new List<ProximityCandidate> {
            P(h5, 0, 0f, 0f, false), P(501, 1, 1f, 0f, true), P(502, 2, 2f, 0f, true) };
        int noneLeft = ProximityVictim.Choose(allDead, h5, 0, ProximitySelection.NearestEnemy,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F4 Victim_ReturnsNoneWhenAllOpponentsDead",
            noneLeft == ProximityVictim.None, "got " + noneLeft);

        // ---- F5: fidelity - the Any branch excludes nobody. ----------------
        // Vanilla's GetClosestPlayer skips only the dead, so a trigger authored as
        // TargetType.Any may legitimately resolve the holder. Narrowing that would
        // be a behaviour change smuggled in under a bug fix.
        const int h6 = 600;
        var anyMode = new List<ProximityCandidate> {
            P(h6, 0, 0f, 0f, false), P(601, 1, 2f, 0f, false) };
        int closest = ProximityVictim.Choose(anyMode, h6, 0, ProximitySelection.NearestAny,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F5 Victim_AnyModeMayResolveTheHolder",
            closest == h6, "got " + closest + " (want the holder, " + h6 + ")");

        // ---- F6: fidelity - team modes exclude the whole friendly team. ----
        // 2v2 and 1v2 keep vanilla's GetClosestPlayerInTeam over the ENEMY team,
        // so a nearer teammate must never be chosen.
        const int h7 = 700;
        var teams = new List<ProximityCandidate> {
            P(h7, 0, 0f, 0f, false), P(701, 0, 0.5f, 0f, false), P(702, 1, 2f, 0f, false) };
        int enemy = ProximityVictim.Choose(teams, h7, 0, ProximitySelection.NearestEnemy,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F6 Victim_EnemyModeExcludesOwnTeam",
            enemy == 702, "got " + enemy + " (want 702, not the nearer teammate 701)");

        // ---- F7: an empty board resolves to None rather than throwing. -----
        int empty = ProximityVictim.Choose(new List<ProximityCandidate>(), 800, 0,
            ProximitySelection.NearestEnemy, 0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
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
        int aboveRange = ProximityVictim.Choose(zOffset, h8, 0, ProximitySelection.NearestEnemy,
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

        Console.WriteLine("=== passed=" + _passed + " failed=" + _failed + " ===");
        return _failed == 0 ? 0 : 1;
    }
}
