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
//   mutation misindex : F10 must FAIL; F11 control must PASS
//   mutation unread   : F14 must FAIL; F15 control must PASS
//   mutation capkey   : C1 must FAIL;  C2 control must PASS
//   mutation reason   : S1 must FAIL;  S2 control must PASS
//   mutation sqrange  : F16 must FAIL; F3a control must PASS
//   mutation fighterkeys : K1 must FAIL; K2 control must PASS
//   mutation prefixwrite : P2 must FAIL; P1 control must PASS
//   mutation anyselect  : F5 must FAIL;  F2 control must PASS
//   mutation ffaskip    : F18 must FAIL; F14 control must PASS
//   mutation gatereason : G4 must FAIL;  G2 control must PASS
//   mutation chainlast  : P3 must FAIL;  P1 control must PASS
//   mutation wire-spec  : W1 must FAIL;  W5 control must PASS
//   mutation wire-prop  : W2 must FAIL;  W5 control must PASS
//   mutation wire-gen   : W3 must FAIL;  W5 control must PASS
//   mutation wire-doc   : W8 must FAIL;  W1 control must PASS
//   mutation wire-msb   : W10 must FAIL; W1 control must PASS
//
// THE SELECTION BRANCH IS CHOSEN PER MODE, because vanilla has more than one
// rule and this mod replaces one of them in FFA only. Tests that describe an FFA
// board use NearestEnemyFfa; tests that describe 2v2 or 1v2 use
// NearestEnemyTeam. Using the wrong one here would assert a rule the trigger
// never evaluated in that mode.
//
// THE W CASES READ THE SHIPPED SOURCES, because half of several closures lives
// in files this harness cannot compile - they carry Unity, Photon and MSBuild.
// A mutant of the seam cannot reach the foreach in SpectatorSession that clears
// the capability, the clause in Plugin that moves the census key, or the
// condition in the csproj that keeps a music-less build green, so before these
// cases existed those halves could be deleted with the suite still reporting
// green (#391/#342). Each W case asserts its anchor occurs EXACTLY ONCE inside
// the named method's own span, never file-wide (#432), and each has a mutant
// that deletes it from a COPY of the tree. What they prove is that the shipped
// wiring is present and unique; what they do NOT prove is its runtime effect,
// which needs the room witness that stays owed.

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
        return c;
    }

    /// <summary>A candidate with a z offset, for the predicate tests.</summary>
    private static ProximityCandidate P3(int id, int team, float x, float y, float z, bool dead)
    {
        var c = P(id, team, x, y, dead);
        c.Z = z;
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

    /// <summary>Root the W cases read the shipped sources from. The runner sets
    /// it to the repo for every seam run and to a one-line-mutated COPY for a
    /// wiring mutant. Unset is a FAILURE and never a skip: a check that quietly
    /// does nothing is the state in which the wiring it guards can be deleted
    /// with the suite still green.</summary>
    private static readonly string SourceRoot = Environment.GetEnvironmentVariable("BUG389_SOURCE_ROOT");

    private static string LoadSource(string relative)
    {
        if (string.IsNullOrEmpty(SourceRoot)) return null;
        string path = System.IO.Path.Combine(SourceRoot, relative.Replace('/', System.IO.Path.DirectorySeparatorChar));
        if (!System.IO.File.Exists(path)) return null;
        return System.IO.File.ReadAllText(path);
    }

    private static int CountOf(string text, string needle)
    {
        int n = 0, i = 0;
        while (true)
        {
            int at = text.IndexOf(needle, i, StringComparison.Ordinal);
            if (at < 0) return n;
            n++;
            i = at + needle.Length;
        }
    }

    /// <summary>Index of the brace closing the one that opens at `open`, skipping
    /// comments, strings, verbatim strings and character literals - all four of
    /// which carry braces in these files, and any of which would otherwise end the
    /// span early and let an anchor outside the method read as inside it.</summary>
    private static int MatchingBrace(string text, int open)
    {
        int depth = 0;
        int i = open;
        while (i < text.Length)
        {
            char ch = text[i];
            if (ch == '/' && i + 1 < text.Length && text[i + 1] == '/')
            { while (i < text.Length && text[i] != '\n') i++; continue; }
            if (ch == '/' && i + 1 < text.Length && text[i + 1] == '*')
            { i += 2; while (i + 1 < text.Length && !(text[i] == '*' && text[i + 1] == '/')) i++; i += 2; continue; }
            if (ch == '@' && i + 1 < text.Length && text[i + 1] == '"')
            {
                i += 2;
                while (i < text.Length)
                {
                    if (text[i] == '"')
                    {
                        if (i + 1 < text.Length && text[i + 1] == '"') { i += 2; continue; }
                        i++; break;
                    }
                    i++;
                }
                continue;
            }
            if (ch == '"')
            {
                i++;
                while (i < text.Length)
                {
                    if (text[i] == '\\') { i += 2; continue; }
                    if (text[i] == '"') { i++; break; }
                    i++;
                }
                continue;
            }
            if (ch == '\'')
            {
                i++;
                while (i < text.Length)
                {
                    if (text[i] == '\\') { i += 2; continue; }
                    if (text[i] == '\'') { i++; break; }
                    i++;
                }
                continue;
            }
            if (ch == '{') depth++;
            else if (ch == '}') { depth--; if (depth == 0) return i; }
            i++;
        }
        return -1;
    }

    /// <summary>The anchor must appear exactly once INSIDE the named member's own
    /// braces. File-wide counting is the check that passes on a line that moved
    /// somewhere else entirely (#432), which is precisely the defect the doc case
    /// W8 exists for.</summary>
    private static void CheckAnchorInMember(string name, string relative, string signature, string anchor)
    {
        string text = LoadSource(relative);
        if (text == null)
        {
            Check(name, false, "cannot read " + relative + " under BUG389_SOURCE_ROOT='"
                + (SourceRoot ?? "<unset>") + "' - the shipped wiring cannot be checked, which is a failure and not a skip");
            return;
        }
        int sigs = CountOf(text, signature);
        if (sigs != 1) { Check(name, false, "member signature found " + sigs + " time(s) (want 1) in " + relative + ": " + signature); return; }
        int sig = text.IndexOf(signature, StringComparison.Ordinal);
        int open = text.IndexOf('{', sig);
        int close = open < 0 ? -1 : MatchingBrace(text, open);
        if (open < 0 || close < 0) { Check(name, false, "could not bound the member span in " + relative + ": " + signature); return; }
        string span = text.Substring(open, close - open + 1);
        int inSpan = CountOf(span, anchor);
        Check(name, inSpan == 1,
            "anchor occurs " + inSpan + " time(s) inside " + signature + " (want 1), " + CountOf(text, anchor)
            + " time(s) in " + relative + ": " + anchor);
    }

    /// <summary>For wiring that is a COUNT rather than a placement - the three
    /// pre-join staging sites, the three prefix returns - where the sites live in
    /// different members and the number is the claim.</summary>
    private static void CheckAnchorCount(string name, string relative, string anchor, int want)
    {
        string text = LoadSource(relative);
        if (text == null)
        {
            Check(name, false, "cannot read " + relative + " under BUG389_SOURCE_ROOT='"
                + (SourceRoot ?? "<unset>") + "' - the shipped wiring cannot be checked, which is a failure and not a skip");
            return;
        }
        int n = CountOf(text, anchor);
        Check(name, n == want, "anchor occurs " + n + " time(s) in " + relative + " (want " + want + "): " + anchor);
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

        // ---- F5: an Any-target ring is not this seam's question. ---------------
        // RED under the "anyselect" mutation, which treats an Any ring as though
        // the ring's rule were the effect's rule.
        //
        // The ring's TargetType.Any selection is GetClosestPlayer, which excludes
        // nobody but the dead (PlayerManager.cs:63-78). The effect the ring fires
        // resolves its own victim through GetOtherPlayer (DealDamageToPlayer.cs
        // :33-38, StunPlayer.cs:19-25, TeleportToOpponent.cs:19-22) - a different
        // function, whose answer can be a different player. On the board below the
        // ring's nearest is the holder's own TEAMMATE while the effect's own rule
        // resolves the opponent, so answering with the ring's player would drain a
        // friendly where an unpatched build drains an enemy.
        //
        // Defer, not None: vanilla applies this tick to its own resolved victim,
        // so refusing would drop damage vanilla deals. The stale-cache defect
        // survives on that path; no shipped content reaches it (all three shipped
        // rings are targetType 1) and it is recorded as a deviation.
        const int h6 = 600;
        var anyRing = new List<ProximityCandidate> {
            P(h6, 0, 0f, 0f, false),      // holder
            P(601, 0, 1f, 0f, false),     // the holder's teammate - the ring's nearest
            P(602, 1, 2f, 0f, false) };   // the opponent the effect's own rule resolves
        int anyAnswer = ProximityVictim.Choose(anyRing, h6, 0, ProximitySelection.NearestAny,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F5 Victim_DefersWhenTheRingMatchesAnyone",
            anyAnswer == ProximityVictim.Defer,
            "got " + anyAnswer + " (want Defer; 601 is a teammate, 602 is the effect's own answer)");

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
            ProximityVictim.ShouldRepair(ProximityGateState.RoomNotAllCapable, true) == false,
            "a room that does not all carry the fix must stay on vanilla");

        // ---- G2: NEGATIVE CONTROL for the gate mutation. -------------------
        // The own-player branch has no cross-player lookup and no defect, so it
        // stays vanilla whatever the room advertises. Survives a mutation that
        // drops the capability term.
        Check("G2 Gate_RefusesWhenEffectTargetsOwnPlayer",
            ProximityVictim.ShouldRepair(ProximityGateState.Capable, false) == false,
            "the own-player branch caches data.player and must stay vanilla");

        Check("G3 Gate_AllowsWhenCapableAndTargetingOther",
            ProximityVictim.ShouldRepair(ProximityGateState.Capable, true), "should repair");

        // ---- G4: every cause of an inactive call names ITSELF. -----------------
        // RED under the "gatereason" mutation, which gives two states one line.
        //
        // Five different facts leave the repair inactive and only one of them is
        // about the peers. The reason is also the budget key (SignalKey), so two
        // causes sharing a line means the second is never printed at all and the
        // reader is told the first one instead - which is how "the room does not
        // all carry the repair" came to be printed for a patch that failed to
        // attach locally, and in the main menu, where there is no room (#430).
        var gateStates = (ProximityGateState[])Enum.GetValues(typeof(ProximityGateState));
        var reasonOwner = new Dictionary<string, string>();
        bool reasonsDistinct = true;
        string reasonCollision = "";
        foreach (var gs in gateStates)
        {
            string reason = ProximityVictim.InactiveReason(gs, true);
            if (string.IsNullOrEmpty(reason))
            { reasonsDistinct = false; reasonCollision = gs + " has no reason line"; break; }
            if (reasonOwner.ContainsKey(reason))
            { reasonsDistinct = false; reasonCollision = gs + " shares a line with " + reasonOwner[reason] + ": " + reason; break; }
            reasonOwner[reason] = gs.ToString();
        }
        string ownPlayerReason = ProximityVictim.InactiveReason(ProximityGateState.Capable, false);
        Check("G4 Gate_EveryInactiveCauseHasItsOwnReason",
            reasonsDistinct && gateStates.Length == 6 && !reasonOwner.ContainsKey(ownPlayerReason),
            "states=" + gateStates.Length + " (want 6) "
            + (reasonCollision.Length > 0 ? reasonCollision : "own-player line collides with a gate line: " + ownPlayerReason));

        // ---- G5: the failure direction, over the whole cross product. ----------
        // Anything that is not Capable refuses, and so does the own-player
        // polarity - so every unhandled combination falls toward vanilla-unchanged
        // rather than toward applying something (#276/#430).
        bool onlyCapableRepairs = true;
        string repairLeak = "";
        foreach (var gs in gateStates)
            foreach (bool other in new[] { true, false })
            {
                bool repairs = ProximityVictim.ShouldRepair(gs, other);
                bool wanted = gs == ProximityGateState.Capable && other;
                if (repairs != wanted)
                { onlyCapableRepairs = false; repairLeak = gs + "/targetsOther=" + other + " -> " + repairs; break; }
            }
        Check("G5 Gate_OnlyACapableRoomAndAnOpponentEffectRepairs",
            onlyCapableRepairs, "wrong answer at " + repairLeak);


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

        // ---- F18: the unreadable bound holds on the FFA branch too, and is ----
        // STRICTER there than the function it reproduces. RED under "ffaskip".
        //
        // NearestEnemyTeam reproduces stock GetClosestPlayerInTeam, which reads
        // players[i].data.dead with no null guard and would have THROWN on an
        // entry like this (PlayerManager.cs:113-115). NearestEnemyFfa reproduces
        // this mod's FfaTargeting.NearestOpponent, which does NOT throw: it skips
        // the entry and answers with the nearest of the rest (FfaMode.cs:3812).
        // So on this branch the seam deliberately declines an answer vanilla-as-
        // patched would have given - a bound rather than a per-branch mechanism
        // (#310), costing one tick of the stale cached target, which is today's
        // shipped behaviour. The mutation puts the skip in, and this case says so.
        const int h18 = 1800;
        var ffaUnreadable = new List<ProximityCandidate> {
            P(h18,  0, 0f, 0f, false),
            PUnreadable(1801),
            P(1802, 2, 2f, 0f, false) };
        int ffaUnread = ProximityVictim.Choose(ffaUnreadable, h18, 0, ProximitySelection.NearestEnemyFfa,
            0f, 0f, 0f, 0f, 0f, 4f, SeesAll);
        Check("F18 Victim_DefersInFfaWhenARosterEntryIsUnreadable",
            ffaUnread == ProximityVictim.Defer,
            "got " + ffaUnread + " (want Defer; 1802 is what NearestOpponent's skip would have answered)");

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
        // RED under the "chainlast" mutation, which makes the composition keep
        // only the last prefix's answer.
        //
        // StunPlayer.Go carries a second, unrelated prefix
        // (PerfPatches.StunPlayerGoNullGuard) and neither declares a priority, so
        // their order is undefined. HarmonyX calls EVERY prefix regardless of what
        // a sibling returned and ANDs the returns into __runOriginal (#352). This
        // composes the seam's model of that fold - RunOriginalAfter - in BOTH
        // orders, over the real decision function and the real prefix return, for
        // every resolution and every sibling answer, and compares the runs.
        //
        // WHAT THIS CASE USED TO BE. It compared `oursRuns && siblingRuns` with
        // `siblingRuns && oursRuns`: the same expression with its operands
        // swapped, true for every input, measuring nothing about order while the
        // commit body said the two orders were exercised. A case that cannot fail
        // is worse than no case (#441/#431), and the mutation is what demonstrates
        // this one can: fold only the last answer and the two orders disagree
        // wherever the two prefixes disagree.
        bool orderStable = true;
        bool writeOnlyOnAccept = true;
        string firstDivergence = "";
        var resolutions = new[] { ProximityResolution.Victim, ProximityResolution.Refuse, ProximityResolution.Defer };
        foreach (var res in resolutions)
            foreach (bool known in new[] { true, false })
                foreach (bool siblingReturn in new[] { true, false })
                {
                    ProximityPrefixAction act = ProximityVictim.PrefixAction(res, known);
                    bool ours = ProximityVictim.PrefixReturn(act);

                    // Harmony starts from "the original runs" and folds each
                    // prefix's answer in, in whatever order it called them.
                    bool oursFirst = ProximityVictim.RunOriginalAfter(
                        ProximityVictim.RunOriginalAfter(true, ours), siblingReturn);
                    bool siblingFirst = ProximityVictim.RunOriginalAfter(
                        ProximityVictim.RunOriginalAfter(true, siblingReturn), ours);
                    if (oursFirst != siblingFirst)
                    {
                        orderStable = false;
                        if (firstDivergence.Length == 0)
                            firstDivergence = res + "/victimKnown=" + known + "/sibling=" + siblingReturn
                                + " ours-first=" + oursFirst + " sibling-first=" + siblingFirst;
                    }
                    if (act == ProximityPrefixAction.WriteVictimAndRun && !(res == ProximityResolution.Victim && known))
                        writeOnlyOnAccept = false;
                }
        Check("P3 Prefix_RunDecisionIsOrderIndependentWithASiblingPrefix",
            orderStable && writeOnlyOnAccept,
            "orderStable=" + orderStable + " writeOnlyOnAccept=" + writeOnlyOnAccept
            + (firstDivergence.Length == 0 ? "" : " first divergence: " + firstDivergence));

        // ---- W1..W10: the shipped wiring this harness cannot compile. ----------
        // Each closure whose other half lives in a Unity, Photon or MSBuild file
        // gets an anchor here, asserted to occur exactly once inside the member
        // that must carry it. Before these existed, deleting the foreach in
        // SpectatorSession or the cr_prox1 clause in Plugin left the suite at a
        // clean green with every seam mutant still reddening its own case.

        // W1 - the spectator pre-join merge clears the fighter capability (L3).
        CheckAnchorInMember("W1 Wiring_SpectatorStagingClearsTheCapabilityKeys",
            "plugin/SpectatorSession.cs",
            "internal static bool StagePreJoinProperties(string localSteamId)",
            "foreach (var capabilityKey in ProximityVictim.FighterCapabilityKeys)");

        // W2 - a cr_prox1 delivery moves the census key (H2). Without it a key
        // that lands inside a frame cannot reach the cached census answer.
        CheckAnchorInMember("W2 Wiring_CapabilityDeliveryMovesTheRosterGeneration",
            "plugin/Plugin.cs",
            "public void OnPlayerPropertiesUpdate(Photon.Realtime.Player target, ExitGames.Client.Photon.Hashtable changedProps)",
            "|| changedProps.ContainsKey(ProximityVictim.CapabilityProp))");

        // W3 - a room change moves it too: every actor is replaced.
        CheckAnchorInMember("W3 Wiring_ARoomChangeMovesTheRosterGeneration",
            "plugin/RoomActors.cs",
            "private static void EnsureCacheRoom()",
            "                _rosterGeneration++;");

        // W4 - and so does an enter/leave callback.
        CheckAnchorInMember("W4 Wiring_ARosterCallbackMovesTheRosterGeneration",
            "plugin/RoomActors.cs",
            "internal static void InvalidateFighterCache()",
            "NoteRosterIdentityChange();");

        // W5 - the census cache is keyed on that counter and not on the frame
        // alone. CONTROL for every wiring mutation in another file.
        CheckAnchorInMember("W5 Wiring_TheCensusCacheIsKeyedOnTheRosterGeneration",
            "plugin/ProximityVictimPatches.cs",
            "internal static ProximityGateState GateState()",
            "RoomActors.RosterGeneration");

        // W6 - the advert is written only where attachment has been proven (#83).
        CheckAnchorInMember("W6 Wiring_TheAdvertIsStagedOnlyWhenPatchesAreLive",
            "plugin/ProximityVictimPatches.cs",
            "internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)",
            "prejoin[ProximityVictim.CapabilityProp] = ProximityVictim.CapabilityValue;");

        // W7 - three pre-join sites carry the advert, and no post-join site does.
        CheckAnchorCount("W7 Wiring_TheAdvertRidesTheThreePreJoinSites",
            "plugin/ApiClient.cs", "ProximityVictimGate.StageInto(prejoin);", 3);

        // W8 - the no-owning-trigger reasoning sits on the branch that implements
        // it, not on the diagnostic sink it drifted onto.
        CheckAnchorInMember("W8 Wiring_TheNoTriggerReasoningSitsOnTheNoTriggerBranch",
            "plugin/ProximityVictimPatches.cs",
            "internal static ProximityResolution ResolveFromTrigger(PlayerInRangeTrigger trigger, string site, out Player victim)",
            "NO OWNING TRIGGER - AND THEREFORE NO REPAIR.");

        // W9 - all three prefixes answer Harmony through the one seam function.
        CheckAnchorCount("W9 Wiring_EveryPrefixReturnsThroughTheSeam",
            "plugin/ProximityVictimPatches.cs", "return ProximityVictim.PrefixReturn(action);", 3);

        // W10 - the provenance build stays green on a checkout without the music
        // tree: the literal manifest Include is existence-conditioned, so the copy
        // step cannot fail a build whose assembly is already written.
        CheckAnchorCount("W10 Wiring_TheMusicManifestCopyIsExistenceConditioned",
            "plugin/CompetitiveRounds.csproj",
            "<MusicManifestToCopy Include=\"music\\manifest.json\" Condition=\"Exists('music\\manifest.json')\" />", 1);

        Console.WriteLine("=== passed=" + _passed + " failed=" + _failed + " ===");
        return _failed == 0 ? 0 : 1;
    }
}
