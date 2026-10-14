using System;
using System.Collections.Generic;
using CompetitiveRounds;

// Bugs 437-439 - executable checks over the SHIPPED FFA enemy resolver.
//
// This harness compiles plugin/FfaTargetingSeam.cs and plugin/ProximityVictimSeam.cs
// as they ship. Resolve() below is the same loop FfaTargeting.NearestOpponent runs
// (FfaMode.cs) with the Unity reads replaced by a plain roster; every decision in
// it is a call into the seam, so a mutant of the seam reaches every case.
//
// THE SITE TABLE is every vanilla card-effect site that asks for its enemy through
// one of the two lookups FfaMode prefixes (decompiled game 1.1.2):
//   GetOtherPlayer(asker)                     -> asker named, identity exclusion
//   GetClosestPlayerInTeam(pos, GetOtherTeam) -> bare position, positional exclusion
// A CACHED site keeps its first answer in a field; the proximity-victim repair
// re-asks it on every activation when ProximityVictim.VictimAction says
// WriteVictimAndRun, and the simulation below takes that decision from the seam.
//
// THE SHAPE every T case uses (the brief's): five players, the effect source in
// the middle, one opponent inside the effect radius and three outside it. The
// team-0 player is placed OUTSIDE the radius on purpose: vanilla's two-team
// lookup (GetOtherTeam returns 0 for every team but 0) would aim the source at
// that player wherever it stands, which is the fixed-player symptom.
//
// MUTANTS (run-tests.ps1), each with the case that must redden and its control:
//   twoteam    (FfaTargetingSeam: restore the GetOtherTeam rule) : T* must FAIL; C1 must PASS
//   positional (FfaTargetingSeam: positional skip even with identity): P1 must FAIL; P2 must PASS
//   noreask    (ProximityVictimSeam: VictimAction never re-asks)   : T* for cached sites must FAIL; C1 must PASS
//   noredirect (ProximityVictimSeam: IsRedirect always false)      : A3 must FAIL; A2 must PASS
// R1 is a REPRODUCTION, not a fix check: under the gate the reported room had
// (RoomNotAllCapable) the cached site must keep its first victim, exactly as the
// three reports describe. It must PASS clean and under every mutant except
// twoteam, which replaces the FFA rule R1 is built on.

internal sealed class Seat
{
    public int Id;
    public int Team;
    public float X;
    public float Y;
    public bool Dead;
    public bool Visible = true;
    public Seat(int id, int team, float x, float y) { Id = id; Team = team; X = x; Y = y; }
}

internal enum Shape { OtherPlayer, ClosestInOtherTeam }

internal sealed class Site
{
    public string Name;
    public Shape Shape;
    public bool NeedVision;
    public bool Cached;
    public Site(string name, Shape shape, bool needVision, bool cached)
    { Name = name; Shape = shape; NeedVision = needVision; Cached = cached; }
}

internal static class Program
{
    private static int _failed;
    private static int _passed;

    private static void Check(string name, bool ok, string detail)
    {
        if (ok) { _passed++; Console.WriteLine("PASS " + name); }
        else { _failed++; Console.WriteLine("FAIL " + name + " :: " + detail); }
    }

    private static float Dist(float ax, float ay, float bx, float by)
    {
        float dx = ax - bx, dy = ay - by;
        return (float)Math.Sqrt(dx * dx + dy * dy);
    }

    /// The loop of FfaTargeting.NearestOpponent with the roster read replaced.
    private static int Resolve(List<Seat> roster, float qx, float qy, int excludeTeam,
                               Seat excludePlayer, bool needVision)
    {
        int best = -1;
        FfaPick pick = FfaTargetingSeam.Begin();
        int index = 0;
        foreach (var p in roster)
        {
            int i = index++;
            float d = Dist(qx, qy, p.X, p.Y);
            if (!FfaTargetingSeam.Improves(ref pick, p.Team, p.Dead, d, excludeTeam,
                                           excludePlayer != null && p == excludePlayer,
                                           excludePlayer != null))
                continue;
            if (needVision && !p.Visible) continue;
            FfaTargetingSeam.Take(ref pick, i, d);
            best = p.Id;
        }
        return best;
    }

    /// What the site asks, in the shape vanilla asks it.
    private static int Ask(Site site, List<Seat> roster, Seat source)
    {
        if (site.Shape == Shape.OtherPlayer)
            return Resolve(roster, source.X, source.Y, source.Team, source, site.NeedVision);
        return Resolve(roster, source.X, source.Y, -1, null, site.NeedVision);
    }

    private static Seat ById(List<Seat> roster, int id)
    {
        foreach (var s in roster) if (s.Id == id) return s;
        return null;
    }

    /// One activation of an effect that drains one victim inside `radius`. The
    /// ring (PlayerInRangeTrigger.Update) fires only when the player the lookup
    /// returns is inside the radius; a cached site then damages its FIELD, which
    /// the repair rewrites only when the seam says WriteVictimAndRun.
    /// Returns the id that takes the drain, or -1.
    private static int Activate(Site site, List<Seat> roster, Seat source, float radius,
                                ref int field, ProximityGateState gate)
    {
        int nearest = Ask(site, roster, source);
        if (nearest < 0) return -1;
        Seat n = ById(roster, nearest);
        if (Dist(source.X, source.Y, n.X, n.Y) >= radius) return -1;   // ring does not fire
        if (!site.Cached) return nearest;                               // per-call site: the answer IS the target

        ProximityPrefixAction action = ProximityVictim.VictimAction(gate, true, true, true);
        if (action == ProximityPrefixAction.WriteVictimAndRun) field = nearest;
        else if (field < 0) field = nearest;                            // vanilla: resolve once, keep it
        return field;
    }

    private static List<Seat> FivePlayers()
    {
        // source: team 2 at the centre. Inside radius 5: team 5 at 3. Outside:
        // team 0 at 11 (the two-team lookup's answer), team 1 at 7, team 4 at 15.
        return new List<Seat>
        {
            new Seat(0, 0, 11f, 0f),
            new Seat(1, 1, 0f, 7f),
            new Seat(2, 2, 0f, 0f),
            new Seat(4, 4, -15f, 0f),
            new Seat(5, 5, 0f, -3f),
        };
    }

    private static readonly Site[] Sites =
    {
        new Site("PlayerInRangeTrigger.Update", Shape.OtherPlayer, false, false),
        new Site("DealDamageToPlayer.Go", Shape.OtherPlayer, false, true),
        new Site("StunPlayer.Go", Shape.OtherPlayer, false, true),
        new Site("TeleportToOpponent.Go", Shape.OtherPlayer, false, true),
        new Site("FollowPlayer.LateUpdate", Shape.OtherPlayer, false, false),
        new Site("AimForPlayer.Update", Shape.OtherPlayer, false, false),
        new Site("ActivateSciptWhenCanSeeOtherPlayer.Update", Shape.OtherPlayer, false, false),
        new Site("SpawnObjectEffect.DoEffect", Shape.OtherPlayer, false, false),
        new Site("Chase.Update", Shape.ClosestInOtherTeam, true, false),
        new Site("LineOfSightTrigger.Update", Shape.ClosestInOtherTeam, false, false),
        new Site("RadarShot.Go", Shape.ClosestInOtherTeam, true, false),
        // Hold 5 re-check of the enumeration against the decompiled game: the
        // damager ZapEffect.Start credits (ZapEffect.cs:16, the last argument of
        // TakeDamage) is GetOtherPlayer(the zapped player), asked per call. The
        // notes' table listed only the zap's own team-agnostic GetClosestPlayer
        // (line 13); this lookup reaches the same prefix, so it is one more case
        // here like every other site, not a special one.
        new Site("ZapEffect.Start", Shape.OtherPlayer, false, false),
    };

    private static int Main()
    {
        const float radius = 5f;

        // ---- T: per site, five players, no fixed-player resolution. ----------
        foreach (var site in Sites)
        {
            var roster = FivePlayers();
            Seat source = ById(roster, 2);
            int field = -1;

            int first = Activate(site, roster, source, radius, ref field, ProximityGateState.Capable);
            bool ok1 = first == 5;

            // The drained player walks far away; another walks inside the radius.
            ById(roster, 5).Y = -20f;
            ById(roster, 4).X = -2f;
            int second = Activate(site, roster, source, radius, ref field, ProximityGateState.Capable);
            bool ok2 = second == 4;

            // Nobody inside the radius: nobody is drained, wherever the old victim is.
            ById(roster, 4).X = -15f;
            int third = Activate(site, roster, source, radius, ref field, ProximityGateState.Capable);
            bool ok3 = third == -1;

            Check("T " + site.Name + " drains the player inside the radius and nobody outside",
                ok1 && ok2 && ok3,
                "activation answers " + first + ", " + second + ", " + third + " (want 5, 4, -1)");
        }

        // ---- C1: control for twoteam and noreask: a 1v1 shape where the two-team
        // rule and the FFA rule agree, on a per-call site. ------------------------
        {
            var duel = new List<Seat> { new Seat(0, 0, 0f, 0f), new Seat(1, 1, 3f, 0f) };
            int answer = Ask(Sites[0], duel, duel[0]);
            Check("C1 Control_OneVersusOneAgreesUnderEveryRule", answer == 1, "got " + answer);
        }

        // ---- P1: identity known -> an opponent on the asker's exact spot counts.
        // (Pick-phase parking puts several players on identical coordinates.) ----
        {
            var roster = new List<Seat>
            {
                new Seat(2, 2, 0f, 98.86f),
                new Seat(5, 5, 0f, 98.86f),
                new Seat(0, 0, 0f, 100f),
            };
            int answer = Resolve(roster, 0f, 98.86f, 2, roster[0], false);
            Check("P1 Identity_CoLocatedOpponentIsEligible", answer == 5, "got " + answer + " (want 5)");
        }

        // ---- P2: control - bare position, identity unknown: the candidate on the
        // query point is the asker and stays excluded. --------------------------
        {
            var roster = new List<Seat> { new Seat(2, 2, 0f, 0f), new Seat(5, 5, 4f, 0f) };
            int answer = Resolve(roster, 0f, 0f, -1, null, false);
            Check("P2 Control_BarePositionStillExcludesTheAsker", answer == 5, "got " + answer + " (want 5)");
        }

        // ---- V: vision and liveness are per candidate. ------------------------
        {
            var roster = FivePlayers();
            ById(roster, 5).Visible = false;
            int answer = Ask(Sites[8], roster, ById(roster, 2));   // Chase: needs vision
            Check("V1 Vision_HiddenNearestIsSkipped", answer == 1, "got " + answer + " (want 1, the next nearest)");
            ById(roster, 5).Visible = true;
            ById(roster, 5).Dead = true;
            answer = Ask(Sites[0], roster, ById(roster, 2));
            Check("V2 Liveness_DeadNearestIsSkipped", answer == 1, "got " + answer + " (want 1)");
        }

        // ---- R1: REPRODUCTION of the reported room. Gate RoomNotAllCapable (two
        // seats ran a build without the repair): the cached site keeps the first
        // victim, drains it from anywhere, and never the player inside. ----------
        {
            Site ddtp = Sites[1];
            var roster = FivePlayers();
            Seat source = ById(roster, 2);
            int field = -1;
            int first = Activate(ddtp, roster, source, radius, ref field, ProximityGateState.RoomNotAllCapable);
            ById(roster, 5).Y = -20f;
            ById(roster, 4).X = -2f;
            int second = Activate(ddtp, roster, source, radius, ref field, ProximityGateState.RoomNotAllCapable);
            Check("R1 Reproduction_DecliningGateKeepsTheFirstVictim",
                first == 5 && second == 5,
                "got " + first + ", " + second + " (want 5, 5: the reported symptom)");
        }

        // ---- A: the positive signal. ------------------------------------------
        {
            string k1 = ProximityVictim.ActiveSignalKey("DealDamageToPlayer", true);
            string k2 = ProximityVictim.ActiveSignalKey("StunPlayer", true);
            string k3 = ProximityVictim.ActiveSignalKey("DealDamageToPlayer", false);
            Check("A1 Signal_KeyIsPerSiteAndPerKind", k1 != k2 && k1 != k3 && k2 != k3,
                k1 + " | " + k2 + " | " + k3);

            string line = ProximityVictim.ActiveSignalText("DealDamageToPlayer", true, 5, 4);
            Check("A2 Signal_LineNamesSiteKindAndBothIds",
                line.Contains("site=DealDamageToPlayer") && line.Contains("redirected")
                && line.Contains("pid=4") && line.Contains("pid=5") && line.Contains("SCR_PROX_ACTIVE=1"),
                "got " + line);

            Check("A3 Signal_RedirectIsAChangedVictim",
                ProximityVictim.IsRedirect(5, 4) && !ProximityVictim.IsRedirect(-1, 4)
                && !ProximityVictim.IsRedirect(4, 4),
                "IsRedirect must be true only for a changed victim, not a first or a kept one");

            Check("A4 Signal_BoundedToOnePerKey", ProximityVictim.MaxOutcomeSignals == 1,
                "got " + ProximityVictim.MaxOutcomeSignals);
        }

        Console.WriteLine("passed " + _passed + ", failed " + _failed);
        return _failed == 0 ? 0 : 1;
    }
}
