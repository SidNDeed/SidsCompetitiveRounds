using System;
using System.Collections.Generic;
using System.Globalization;

namespace CompetitiveRounds
{
    /// <summary>Which surviving seat reports a mid-series 2v2 disconnect (bugs
    /// #384/#385; v1.41.0 beta review round 2, finding 2, and round 3, finding
    /// 2). Plugin's OnPlayerLeftRoom reads the room and asks ShouldReport;
    /// nothing here touches Photon or Unity, so the rule the room runs is the
    /// rule the sentinel below exercises, and both also run outside the game.
    ///
    /// The server accepts a DC report only from a member of the team that did
    /// NOT lose a player (team/series/{id}/report-dc, the F6 gate, which reads
    /// both teams from the series row and never from a `t_id`), and it settles
    /// the series once: the first accepted report settles it and every later
    /// one finds it settled. So the property that matters is "at least one
    /// ACCEPTABLE seat reports", and an extra report costs one request and
    /// changes nothing.</summary>
    internal static class DcReporterElection
    {
        /// <summary>A surviving peer as the census sees it: its advertised u_id,
        /// and its team as ParseTeamId read it (-1 = unknown).</summary>
        internal struct Peer
        {
            public string SteamId;
            public int Team;
            public Peer(string steamId, int team) { SteamId = steamId; Team = team; }
        }

        /// <summary>An advertised `t_id` as the election reads it: 0 or 1.
        /// Anything else is -1, UNKNOWN: missing, unparseable, or a stale value
        /// from an earlier FFA room (2, 3, 4...), which taken at face value
        /// would make each such seat its own one-member team (r3 finding).</summary>
        internal static int ParseTeamId(object v)
        {
            if (v == null) return -1;
            int t;
            if (!int.TryParse(v.ToString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out t)) return -1;
            return (t == 0 || t == 1) ? t : -1;
        }

        /// <summary>How many of the lowest ids among the survivors report
        /// whatever any `t_id` says: the floor (see ShouldReport).</summary>
        internal const int FloorSeats = 2;

        /// <summary>Does THIS seat report the disconnect?
        /// myVal: my own Steam id. myTeam / dcTeam: ParseTeamId of my own `t_id`
        /// and of the leaver's. peers: every OTHER surviving fighter, never the
        /// leaver and never me.
        ///
        /// Two reasons to report, OR'd:
        ///   the floor      - at most one peer with a parseable id is lower than
        ///                    mine: I am one of the TWO lowest ids among the
        ///                    survivors. No `t_id` is read. A 2v2 leave has three
        ///                    survivors and the server refuses exactly one of
        ///                    them, the leaver's teammate, so two distinct
        ///                    reporters always include one it accepts (round 3
        ///                    finding 2). One team-blind seat is not enough: the
        ///                    room-wide lowest id is refused whenever it is the
        ///                    leaver's teammate, and a readable but WRONG `t_id`
        ///                    (the leaver advertising the team that stayed, or
        ///                    the leaver's teammate advertising it) can make both
        ///                    seats that stayed stand down on their team claim,
        ///                    which is how round 2's rule, whose floor was the
        ///                    room-wide lowest id alone, could elect nobody the
        ///                    server accepts.
        ///   the team claim - I cannot read my own team or the leaver's (round 2
        ///                    finding 2: that case reports rather than stands
        ///                    down), or both are known, I am on the team that did
        ///                    not lose a player, and no peer KNOWN to be on my
        ///                    team has a lower id. With every `t_id` true and
        ///                    every `u_id` readable it names a seat the floor
        ///                    already names (the lower of the two seats that
        ///                    stayed is at worst the second-lowest survivor), so
        ///                    it adds a reporter only when a team or a `u_id` is
        ///                    unreadable or a `t_id` is wrong.
        ///
        /// Outside a consistent view (THE CONSISTENT VIEW, below), deferring to
        /// a lower peer happens only in the team claim, and only
        /// when both teams are known: with a team unknown, my own team reads -1
        /// and so does every peer whose `t_id` is unreadable, and "same team"
        /// would be two unknowns agreeing. The floor defers to nobody.
        ///
        /// THE BOUND, stated honestly. At least one reporter the server accepts,
        /// whatever any `t_id` says, whenever the census is the other survivors
        /// of the leave (the fighters left in the room: the leaver's teammate and
        /// the two seats that stayed). A seat counts only the peers whose `u_id`
        /// it can read, so an unreadable `u_id` makes a seat count FEWER lower
        /// peers: it can only add reporters, and the true two lowest always
        /// report. A census holding a fighter that is not one of those three is
        /// outside the floor's count, and there the team claim is what remains.
        /// Reporters: exactly two while every `t_id` is true and every `u_id`
        /// readable; up to every survivor otherwise. The duplicates no-op on the
        /// server, and a refused seat costs one 400 and changes nothing.
        ///
        /// THE CONSISTENT VIEW (v1.41.0 merge pass 1, follow-up 6, the
        /// integrator's ruling on the 886bed8 lane's L3 stand-down). The
        /// requirement: at least one seat the server accepts reports, and when
        /// several seats are eligible exactly one of them does, the lowest Steam
        /// id (the project's reporter rule). The floor alone cannot give the
        /// second half: with the leaver's teammate the highest id, both seats
        /// that stayed are the two lowest and both report. So when this seat's
        /// view is CONSISTENT (ConsistentView: both teams known, exactly two
        /// peers, every peer's `u_id` parseable and distinct and its `t_id`
        /// readable, and exactly one survivor advertising the leaver's team),
        /// the rule is instead: the seat advertising the leaver's team reports,
        /// and of the two seats advertising the other team only the lower id
        /// reports; the other one stands down. That is the L3 stand-down as
        /// ruled: it applies only to an eligible seat that is not the lowest
        /// eligible one. The leaver's advertised teammate does NOT stand down,
        /// and that is what keeps the first half. A consistent view can still be
        /// wrong: the leaver and one survivor can advertise each other's teams
        /// in a clean 2/2 split, and then the seat advertising the leaver's team
        /// is one of the two that stayed. Either it is (it reports and is
        /// accepted) or the advertised split is true (the lower of the two that
        /// stayed reports and is accepted). Every view this seat cannot check
        /// runs the floor and the team claim as above, so the bound above holds
        /// for it unchanged, and the sweep below covers seats whose views differ
        /// (one seat's `u_id` unreadable to the others while it reads theirs).
        /// With every `t_id` true and every `u_id` readable this names exactly
        /// two reporters, the leaver's teammate (refused) and the lowest id of
        /// the team that stayed, so exactly one report is accepted. The
        /// sentinel's sweep checks both halves, and a twin rule carrying the
        /// lane's first cut of the stand-down (a seat advertising the leaver's
        /// team stands down while another looks eligible) must leave some state
        /// with no accepted reporter, or the sweep could not tell them apart.
        /// Like the floor, this counts only seats running this rule: a survivor
        /// on an older build runs its own.</summary>
        internal static bool ShouldReport(long myVal, int myTeam, int dcTeam,
            IEnumerable<Peer> peers, out bool onFloor, out bool teamsKnown, out bool consistentView)
        {
            teamsKnown = dcTeam >= 0 && myTeam >= 0;
            bool lowerLooksEligible;
            consistentView = ConsistentView(myVal, myTeam, dcTeam, peers, out lowerLooksEligible);
            if (consistentView)
            {
                onFloor = false;
                return myTeam == dcTeam || !lowerLooksEligible;
            }
            int lowerPeers = 0;
            bool lowestOnMyTeam = !teamsKnown || myTeam != dcTeam;
            if (peers != null)
            {
                foreach (var pp in peers)
                {
                    if (string.IsNullOrEmpty(pp.SteamId) || pp.SteamId.StartsWith("photon_", StringComparison.Ordinal)) continue;
                    long ppVal;
                    if (!long.TryParse(pp.SteamId, NumberStyles.Integer, CultureInfo.InvariantCulture, out ppVal) || ppVal >= myVal) continue;
                    lowerPeers++;
                    // Defer the TEAM claim only to a peer that also looks eligible,
                    // and only when both teams are known (see the summary). The
                    // floor reads no team, so nothing here can talk it down.
                    if (teamsKnown && lowestOnMyTeam && pp.Team == myTeam) lowestOnMyTeam = false;
                    if (lowerPeers >= FloorSeats && !lowestOnMyTeam) break;
                }
            }
            onFloor = lowerPeers < FloorSeats;
            return onFloor || lowestOnMyTeam;
        }

        /// <summary>Can this seat check the whole leave from its own view (see
        /// THE CONSISTENT VIEW in ShouldReport)? True only when both teams are
        /// known, there are exactly two peers, each has a parseable `u_id` that
        /// is neither mine nor the other peer's and a readable `t_id`, and
        /// exactly one survivor (me or a peer) advertises the leaver's team.
        /// lowerLooksEligible: a peer advertising the other team has a lower id
        /// than mine. It means something only when this returns true.</summary>
        private static bool ConsistentView(long myVal, int myTeam, int dcTeam,
            IEnumerable<Peer> peers, out bool lowerLooksEligible)
        {
            lowerLooksEligible = false;
            if (dcTeam < 0 || myTeam < 0 || peers == null) return false;
            int count = 0, dcLooking = myTeam == dcTeam ? 1 : 0;
            long firstPeer = 0;
            foreach (var pp in peers)
            {
                long ppVal;
                if (pp.Team < 0 || string.IsNullOrEmpty(pp.SteamId)
                    || pp.SteamId.StartsWith("photon_", StringComparison.Ordinal)
                    || !long.TryParse(pp.SteamId, NumberStyles.Integer, CultureInfo.InvariantCulture, out ppVal)
                    || ppVal == myVal || (count == 1 && ppVal == firstPeer)) return false;
                count++;
                if (count > 2) return false;
                if (count == 1) firstPeer = ppVal;
                if (pp.Team == dcTeam) dcLooking++;
                else if (ppVal < myVal) lowerLooksEligible = true;
            }
            return count == 2 && dcLooking == 1;
        }

        // -- Sentinel --------------------------------------------------------
        //
        // Runs the election on every survivor of synthetic four-seat rooms and
        // counts the reports the server's F6 gate would ACCEPT (a reporter on the
        // team that did not lose the player, judged by the seat's REAL team, not
        // the one it advertises). Nothing is sent anywhere. Plugin's
        // DevReporterElectionSentinelTest logs the line RunSentinel returns.

        internal const string SentinelTag = "[REPORTER-ELECTION-SENTINEL]";

        private struct Seat
        {
            public long Id; public int RealTeam; public object Advertised; public string Uid;
            public Seat(long id, int realTeam, object advertised, string uid)
            { Id = id; RealTeam = realTeam; Advertised = advertised; Uid = uid; }
        }

        private delegate bool Rule(long myVal, int myTeam, int dcTeam, IEnumerable<Peer> peers);

        private static bool CurrentRule(long myVal, int myTeam, int dcTeam, IEnumerable<Peer> peers)
        {
            bool onFloor, teamsKnown, consistentView;
            return ShouldReport(myVal, myTeam, dcTeam, peers, out onFloor, out teamsKnown, out consistentView);
        }

        // The 886bed8 lane's first cut of the L3 stand-down, put back on top of
        // the current rule: a seat advertising the leaver's team stands down
        // whenever another survivor with a readable id looks eligible. Kept ONLY
        // so the sweep can show it leaves states with no accepted reporter (a
        // wrong `t_id` makes the seat that stands down one of the two that
        // stayed). If this twin stopped missing, the sweep could not tell the
        // ruled stand-down from the unconditional one.
        private static bool LaneStandDownRule(long myVal, int myTeam, int dcTeam, IEnumerable<Peer> peers)
        {
            if (dcTeam >= 0 && myTeam >= 0 && myTeam == dcTeam)
                foreach (var pp in peers)
                    if (!string.IsNullOrEmpty(pp.SteamId) && pp.Team >= 0 && pp.Team != dcTeam) return false;
            return CurrentRule(myVal, myTeam, dcTeam, peers);
        }

        // The rule as it stood before round 2 (lane pin ef276d8), kept ONLY so the
        // sentinel can show that its failing states really fail under it. If this
        // copy stopped failing them, the scenarios below would prove nothing.
        private static bool PreRound2Rule(long myVal, int myTeam, int dcTeam, IEnumerable<Peer> peers)
        {
            bool teamsKnown = dcTeam >= 0 && myTeam >= 0;
            bool lowestOverall = true;
            bool lowestOnMyTeam = teamsKnown && myTeam != dcTeam;
            foreach (var pp in peers)
            {
                if (string.IsNullOrEmpty(pp.SteamId) || pp.SteamId.StartsWith("photon_", StringComparison.Ordinal)) continue;
                long ppVal;
                if (!long.TryParse(pp.SteamId, NumberStyles.Integer, CultureInfo.InvariantCulture, out ppVal) || ppVal >= myVal) continue;
                lowestOverall = false;
                if (lowestOnMyTeam && pp.Team == myTeam) lowestOnMyTeam = false;
                if (!lowestOverall && !lowestOnMyTeam) break;
            }
            return lowestOverall || lowestOnMyTeam;
        }

        // The rule as round 2 left it (lane tip b5ff8a9): its only team-blind
        // reporter was the room-wide lowest id. Kept ONLY so the sentinel can show
        // that round 3's failing states, a readable but wrong `t_id`, really fail
        // under it.
        private static bool Round2Rule(long myVal, int myTeam, int dcTeam, IEnumerable<Peer> peers)
        {
            bool teamsKnown = dcTeam >= 0 && myTeam >= 0;
            bool lowestOverall = true;
            bool lowestOnMyTeam = !teamsKnown || myTeam != dcTeam;
            foreach (var pp in peers)
            {
                if (string.IsNullOrEmpty(pp.SteamId) || pp.SteamId.StartsWith("photon_", StringComparison.Ordinal)) continue;
                long ppVal;
                if (!long.TryParse(pp.SteamId, NumberStyles.Integer, CultureInfo.InvariantCulture, out ppVal) || ppVal >= myVal) continue;
                lowestOverall = false;
                if (teamsKnown && lowestOnMyTeam && pp.Team == myTeam) lowestOnMyTeam = false;
                if (!lowestOverall && !lowestOnMyTeam) break;
            }
            return lowestOverall || lowestOnMyTeam;
        }

        private static void Simulate(Seat[] room, int leaver, Rule rule, List<Peer> scratch,
            out int reporters, out int accepted)
        {
            reporters = 0; accepted = 0;
            int dcTeam = ParseTeamId(room[leaver].Advertised);
            for (int me = 0; me < room.Length; me++)
            {
                if (me == leaver) continue;
                scratch.Clear();
                for (int o = 0; o < room.Length; o++)
                    if (o != me && o != leaver)
                        scratch.Add(new Peer(room[o].Uid, ParseTeamId(room[o].Advertised)));
                // A seat's own id is its local Steam id; only what it ADVERTISES
                // (its u_id) can be unreadable to the others.
                if (!rule(room[me].Id, ParseTeamId(room[me].Advertised), dcTeam, scratch)) continue;
                reporters++;
                if (room[me].RealTeam != room[leaver].RealTeam) accepted++;
            }
        }

        private static Seat Readable(long id, int realTeam, object advertised)
        {
            return new Seat(id, realTeam, advertised, id.ToString(CultureInfo.InvariantCulture));
        }

        private static Seat[] Room(long a, long b, long c, long d, object ta, object tb, object tc, object td)
        {
            // Seats 0 and 1 really play on team 0, seats 2 and 3 on team 1; every
            // u_id is readable.
            return new[] { Readable(a, 0, ta), Readable(b, 0, tb), Readable(c, 1, tc), Readable(d, 1, td) };
        }

        /// <summary>Returns the log line; `pass` is its verdict.</summary>
        internal static string RunSentinel(out bool pass)
        {
            pass = true;
            int checks = 0;
            string detail = "";
            var scratch = new List<Peer>(4);

            // Round 2's failing states: seat 3 leaves, and the lowest id in the
            // room is seat 2, the leaver's own teammate. Four ways for every
            // survivor to be unable to read the teams: every `t_id` missing,
            // every one unparseable, every one a stale FFA seat index, and only
            // the leaver's missing (each survivor knows its own team, not the
            // leaver's).
            var failing = new KeyValuePair<string, Seat[]>[]
            {
                new KeyValuePair<string, Seat[]>("all-missing",   Room(200, 300, 100, 400, null, null, null, null)),
                new KeyValuePair<string, Seat[]>("all-garbled",   Room(200, 300, 100, 400, "x", "?", "", "t1")),
                new KeyValuePair<string, Seat[]>("all-stale-ffa", Room(200, 300, 100, 400, "2", "3", "4", "5")),
                new KeyValuePair<string, Seat[]>("leaver-missing", Room(200, 300, 100, 400, "0", "0", "1", null)),
            };
            foreach (var kv in failing)
            {
                int r, a;
                Simulate(kv.Value, 3, PreRound2Rule, scratch, out r, out a);
                checks++;
                if (a != 0) { pass = false; detail += " " + kv.Key + ":not-a-failing-state(pre accepted=" + a + ")"; }
                Simulate(kv.Value, 3, CurrentRule, scratch, out r, out a);
                checks++;
                if (a < 1) { pass = false; detail += " " + kv.Key + ":no-accepted-reporter(reporters=" + r + ")"; }
            }

            // Every leaver, every failing shape: at least one accepted reporter.
            foreach (var kv in failing)
                for (int leaver = 0; leaver < 4; leaver++)
                {
                    int r, a;
                    Simulate(kv.Value, leaver, CurrentRule, scratch, out r, out a);
                    checks++;
                    if (a < 1) { pass = false; detail += " " + kv.Key + "/leaver" + leaver + ":no-accepted-reporter"; }
                }

            // Round 3's failing states (finding 2): a READABLE but WRONG `t_id`.
            // Seat 3 leaves and the lowest id is seat 2, its teammate.
            //   leaver-claims-stayed   - the review's example: the leaver advertises
            //                            the team that stayed, so seats 0 and 1 read
            //                            themselves as the leaver's team and stand
            //                            down, and seat 2 reports and is refused.
            //   teammate-claims-stayed - a non-leaver's `t_id` is wrong: seat 2
            //                            advertises the team that stayed, and seats
            //                            0 and 1 defer their team claim to it.
            //   teams-crossed          - two wrong `t_id`s that still read as a
            //                            clean 2 + 2 split (seats 0 and 2 exchanged).
            // Each must fail under round 2's rule and pass under the current one.
            var wrong = new KeyValuePair<string, Seat[]>[]
            {
                new KeyValuePair<string, Seat[]>("leaver-claims-stayed",   Room(200, 300, 100, 400, "0", "0", "1", "0")),
                new KeyValuePair<string, Seat[]>("teammate-claims-stayed", Room(200, 300, 100, 400, "0", "0", "0", "1")),
                new KeyValuePair<string, Seat[]>("teams-crossed",          Room(200, 300, 100, 400, "1", "0", "0", "1")),
            };
            foreach (var kv in wrong)
            {
                int r, a;
                Simulate(kv.Value, 3, Round2Rule, scratch, out r, out a);
                checks++;
                if (a != 0) { pass = false; detail += " " + kv.Key + ":not-a-failing-state(round2 accepted=" + a + ")"; }
                Simulate(kv.Value, 3, CurrentRule, scratch, out r, out a);
                checks++;
                if (a < 1) { pass = false; detail += " " + kv.Key + ":no-accepted-reporter(reporters=" + r + ")"; }
            }

            // Teams KNOWN and TRUE on every seat, every u_id readable: an accepted
            // reporter and exactly two reporters (the floor; the team claim names
            // one of the same two), for every leaver.
            var known = new KeyValuePair<string, Seat[]>[]
            {
                new KeyValuePair<string, Seat[]>("known-lowest-on-dc-team", Room(200, 300, 100, 400, "0", "0", "1", "1")),
                new KeyValuePair<string, Seat[]>("known-lowest-elsewhere",  Room(100, 300, 200, 400, 0, 0, 1, 1)),
            };
            foreach (var kv in known)
                for (int leaver = 0; leaver < 4; leaver++)
                {
                    int r, a;
                    Simulate(kv.Value, leaver, CurrentRule, scratch, out r, out a);
                    checks++;
                    if (a < 1) { pass = false; detail += " " + kv.Key + "/leaver" + leaver + ":no-accepted-reporter"; }
                    if (r != FloorSeats) { pass = false; detail += " " + kv.Key + "/leaver" + leaver + ":reporters=" + r; }
                }

            // Every state of a four-seat room: every leaver, every order of the
            // four ids over the seats, every seat's `t_id` 0, 1 or unreadable, and
            // every seat's `u_id` readable or not. The current rule must leave an
            // accepted reporter in every one. Round 2's rule must miss some of the
            // readable-u_id states, or this sweep could not tell the two apart.
            // Wherever every `t_id` is true (or every one is exchanged, which
            // keeps who plays with whom) and every `u_id` is readable, exactly two
            // seats report and exactly ONE of them is accepted, the lowest id of
            // the team that stayed (THE CONSISTENT VIEW, follow-up 6). The lane's
            // unconditional stand-down (LaneStandDownRule) must miss some state.
            long[] ids = { 100, 200, 300, 400 };
            object[] adv = { "0", "1", null };
            int states = 0, misses = 0, r2states = 0, r2misses = 0, trueStates = 0, trueNotTwo = 0;
            int trueNotOneAccepted = 0, laneMisses = 0;
            var room = new Seat[4];
            var order = new int[4];
            for (int p0 = 0; p0 < 4; p0++)
            for (int p1 = 0; p1 < 4; p1++)
            for (int p2 = 0; p2 < 4; p2++)
            {
                if (p1 == p0 || p2 == p0 || p2 == p1) continue;
                order[0] = p0; order[1] = p1; order[2] = p2; order[3] = 6 - p0 - p1 - p2;
                for (int t = 0; t < 81; t++)
                for (int unreadable = 0; unreadable < 16; unreadable++)
                {
                    int tt = t;
                    bool sameTeams = true, swappedTeams = true;
                    for (int s = 0; s < 4; s++)
                    {
                        object a = adv[tt % 3]; tt /= 3;
                        int real = s < 2 ? 0 : 1;
                        long id = ids[order[s]];
                        string uid = ((unreadable >> s) & 1) != 0 ? null : id.ToString(CultureInfo.InvariantCulture);
                        room[s] = new Seat(id, real, a, uid);
                        int read = ParseTeamId(a);
                        if (read != real) sameTeams = false;
                        if (read != 1 - real) swappedTeams = false;
                    }
                    for (int leaver = 0; leaver < 4; leaver++)
                    {
                        int r, acc;
                        Simulate(room, leaver, CurrentRule, scratch, out r, out acc);
                        states++;
                        if (acc < 1) misses++;
                        if (unreadable == 0)
                        {
                            if (sameTeams || swappedTeams)
                            {
                                trueStates++;
                                if (r != FloorSeats) trueNotTwo++;
                                if (acc != 1) trueNotOneAccepted++;
                            }
                            int r2, acc2;
                            Simulate(room, leaver, Round2Rule, scratch, out r2, out acc2);
                            r2states++;
                            if (acc2 < 1) r2misses++;
                        }
                        int rl, accl;
                        Simulate(room, leaver, LaneStandDownRule, scratch, out rl, out accl);
                        if (accl < 1) laneMisses++;
                    }
                }
            }
            checks++;
            if (misses != 0) { pass = false; detail += " sweep:" + misses + "-of-" + states + "-states-without-an-accepted-reporter"; }
            checks++;
            if (r2misses == 0) { pass = false; detail += " sweep:round2-rule-misses-none(the-sweep-proves-nothing)"; }
            checks++;
            if (trueStates == 0 || trueNotTwo != 0) { pass = false; detail += " sweep:true-team-states=" + trueStates + ",not-two-reporters=" + trueNotTwo; }
            checks++;
            if (trueNotOneAccepted != 0) { pass = false; detail += " sweep:true-team-states-not-one-accepted=" + trueNotOneAccepted; }
            checks++;
            if (laneMisses == 0) { pass = false; detail += " sweep:lane-stand-down-misses-none(the-sweep-proves-nothing)"; }

            // ParseTeamId: only 0 and 1 are teams.
            object[] unknown = { null, "", "x", "2", "-1", 5, "1.0" };
            foreach (var v in unknown)
            {
                checks++;
                if (ParseTeamId(v) != -1) { pass = false; detail += " parse:" + (v ?? "null"); }
            }
            checks++;
            if (ParseTeamId("0") != 0 || ParseTeamId(1) != 1) { pass = false; detail += " parse:0/1"; }

            string sweep = " (sweep: " + states + " states, " + misses + " without an accepted reporter; round 2's rule: "
                + r2misses + " of " + r2states + "; " + trueStates + " true-team states, " + trueNotTwo + " not two reporters, "
                + trueNotOneAccepted + " not one accepted; the lane's unconditional stand-down: " + laneMisses + " without an accepted reporter)";
            return SentinelTag + " " + (pass ? "PASS" : "FAIL") + ": " + checks + " checks" + sweep + detail;
        }
    }
}
