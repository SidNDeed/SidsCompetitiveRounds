using System;
using System.Collections.Generic;
using System.Globalization;

namespace CompetitiveRounds
{
    /// <summary>Which surviving seat reports a mid-series 2v2 disconnect (bugs
    /// #384/#385; v1.41.0 beta review round 2, finding 2). Plugin's
    /// OnPlayerLeftRoom reads the room and asks ShouldReport; nothing here
    /// touches Photon or Unity, so the rule the room runs is the rule the
    /// sentinel below exercises, and both also run outside the game.
    ///
    /// The server accepts a DC report only from a member of the team that did
    /// NOT lose a player (team/series/{id}/report-dc, the F6 gate), and it
    /// settles the series once: the first accepted report settles it and every
    /// later one finds it settled. So the property that matters is "at least
    /// one ACCEPTABLE seat reports", and an extra report costs one request and
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

        /// <summary>Does THIS seat report the disconnect?
        /// myVal: my own Steam id. myTeam / dcTeam: ParseTeamId of my own `t_id`
        /// and of the leaver's. peers: every OTHER surviving fighter, never the
        /// leaver and never me.
        ///
        /// Three reasons to report, OR'd, so the election can never do worse
        /// than the room-wide rule it grew out of:
        ///   lowestOverall  - no peer with a parseable id is lower than mine. True
        ///                    on at least one surviving seat whatever anyone
        ///                    advertises.
        ///   lowestOnMyTeam - both teams are known, I am on the team that did not
        ///                    lose a player, and no peer KNOWN to be on my team
        ///                    has a lower id.
        ///   teams unknown  - I cannot read my own team or the leaver's. Then I
        ///                    cannot tell whether the server will accept me, and
        ///                    the room-wide floor is not enough on its own: when
        ///                    the lowest id in the room is the DC'd player's own
        ///                    teammate the server refuses it (400), and with the
        ///                    teams unknown on every seat no other seat had any
        ///                    reason to report, so nothing closed the series
        ///                    (round 2 finding 2). A teams-unknown seat therefore
        ///                    REPORTS: the unhandled case fails toward reporting,
        ///                    never toward standing down. The seats the server
        ///                    refuses cost a 400 each and change nothing.
        ///
        /// Deferring to a lower peer happens only when both teams are known.
        /// With a team unknown, my own team reads -1 and so does every peer whose
        /// `t_id` is unreadable, and "same team" would be two unknowns agreeing.
        ///
        /// THE BOUND, stated honestly. At least one reporter the server accepts
        /// whenever every `t_id` in the room is either unreadable or true:
        /// unreadable teams make every seat that meets them report, and true
        /// teams elect the lowest seat of the team that stayed. A readable but
        /// WRONG `t_id` (a seat advertising a team the series does not record it
        /// on) can still leave no acceptable reporter, because no seat can tell a
        /// wrong team from a right one. At most two reporters only while every
        /// survivor advertises a parseable `u_id` and can read both teams: a seat
        /// whose `u_id` is unreadable is invisible to its peers' census, so they
        /// cannot defer to it, and a seat that cannot read the teams reports
        /// unconditionally. In the worst case every survivor reports, and the
        /// duplicates no-op on the server.</summary>
        internal static bool ShouldReport(long myVal, int myTeam, int dcTeam,
            IEnumerable<Peer> peers, out bool lowestOverall, out bool teamsKnown)
        {
            teamsKnown = dcTeam >= 0 && myTeam >= 0;
            lowestOverall = true;
            bool lowestOnMyTeam = !teamsKnown || myTeam != dcTeam;
            if (peers != null)
            {
                foreach (var pp in peers)
                {
                    if (string.IsNullOrEmpty(pp.SteamId) || pp.SteamId.StartsWith("photon_", StringComparison.Ordinal)) continue;
                    long ppVal;
                    if (!long.TryParse(pp.SteamId, NumberStyles.Integer, CultureInfo.InvariantCulture, out ppVal) || ppVal >= myVal) continue;
                    lowestOverall = false;
                    // Defer the TEAM claim only to a peer that also looks eligible,
                    // and only when both teams are known (see the summary).
                    if (teamsKnown && lowestOnMyTeam && pp.Team == myTeam) lowestOnMyTeam = false;
                    if (!lowestOverall && !lowestOnMyTeam) break;
                }
            }
            return lowestOverall || lowestOnMyTeam;
        }

        // ── Sentinel ────────────────────────────────────────────────────────
        //
        // Runs the election on every survivor of synthetic four-seat rooms and
        // counts the reports the server's F6 gate would ACCEPT (a reporter on the
        // team that did not lose the player, judged by the seat's REAL team, not
        // the one it advertises). Nothing is sent anywhere. Plugin's
        // DevReporterElectionSentinelTest logs the line RunSentinel returns.

        internal const string SentinelTag = "[REPORTER-ELECTION-SENTINEL]";

        private struct Seat
        {
            public long Id; public int RealTeam; public object Advertised;
            public Seat(long id, int realTeam, object advertised) { Id = id; RealTeam = realTeam; Advertised = advertised; }
        }

        private delegate bool Rule(long myVal, int myTeam, int dcTeam, IEnumerable<Peer> peers);

        private static bool CurrentRule(long myVal, int myTeam, int dcTeam, IEnumerable<Peer> peers)
        {
            bool lowestOverall, teamsKnown;
            return ShouldReport(myVal, myTeam, dcTeam, peers, out lowestOverall, out teamsKnown);
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

        private static void Simulate(Seat[] room, int leaver, Rule rule, out int reporters, out int accepted)
        {
            reporters = 0; accepted = 0;
            int dcTeam = ParseTeamId(room[leaver].Advertised);
            for (int me = 0; me < room.Length; me++)
            {
                if (me == leaver) continue;
                var peers = new List<Peer>();
                for (int o = 0; o < room.Length; o++)
                    if (o != me && o != leaver)
                        peers.Add(new Peer(room[o].Id.ToString(CultureInfo.InvariantCulture),
                                           ParseTeamId(room[o].Advertised)));
                if (!rule(room[me].Id, ParseTeamId(room[me].Advertised), dcTeam, peers)) continue;
                reporters++;
                if (room[me].RealTeam != room[leaver].RealTeam) accepted++;
            }
        }

        private static Seat[] Room(long a, long b, long c, long d, object ta, object tb, object tc, object td)
        {
            // Seats 0 and 1 really play on team 0, seats 2 and 3 on team 1.
            return new[] { new Seat(a, 0, ta), new Seat(b, 0, tb), new Seat(c, 1, tc), new Seat(d, 1, td) };
        }

        /// <summary>Returns the log line; `pass` is its verdict.</summary>
        internal static string RunSentinel(out bool pass)
        {
            pass = true;
            int checks = 0;
            string detail = "";

            // The report's failing state: seat 3 leaves, and the lowest id in the
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
                Simulate(kv.Value, 3, PreRound2Rule, out r, out a);
                checks++;
                if (a != 0) { pass = false; detail += " " + kv.Key + ":not-a-failing-state(pre accepted=" + a + ")"; }
                Simulate(kv.Value, 3, CurrentRule, out r, out a);
                checks++;
                if (a < 1) { pass = false; detail += " " + kv.Key + ":no-accepted-reporter(reporters=" + r + ")"; }
            }

            // Every leaver, every failing shape: at least one accepted reporter.
            foreach (var kv in failing)
                for (int leaver = 0; leaver < 4; leaver++)
                {
                    int r, a;
                    Simulate(kv.Value, leaver, CurrentRule, out r, out a);
                    checks++;
                    if (a < 1) { pass = false; detail += " " + kv.Key + "/leaver" + leaver + ":no-accepted-reporter"; }
                }

            // Teams KNOWN on every seat: the rule is unchanged from before round 2
            // (same reporters, same accepted count, for every leaver), there is an
            // accepted reporter, and at most two seats report.
            var known = new KeyValuePair<string, Seat[]>[]
            {
                new KeyValuePair<string, Seat[]>("known-lowest-on-dc-team", Room(200, 300, 100, 400, "0", "0", "1", "1")),
                new KeyValuePair<string, Seat[]>("known-lowest-elsewhere",  Room(100, 300, 200, 400, 0, 0, 1, 1)),
            };
            foreach (var kv in known)
                for (int leaver = 0; leaver < 4; leaver++)
                {
                    int rPre, aPre, r, a;
                    Simulate(kv.Value, leaver, PreRound2Rule, out rPre, out aPre);
                    Simulate(kv.Value, leaver, CurrentRule, out r, out a);
                    checks++;
                    if (r != rPre || a != aPre) { pass = false; detail += " " + kv.Key + "/leaver" + leaver + ":changed"; }
                    if (a < 1) { pass = false; detail += " " + kv.Key + "/leaver" + leaver + ":no-accepted-reporter"; }
                    if (r > 2) { pass = false; detail += " " + kv.Key + "/leaver" + leaver + ":reporters=" + r; }
                }

            // ParseTeamId: only 0 and 1 are teams.
            object[] unknown = { null, "", "x", "2", "-1", 5, "1.0" };
            foreach (var v in unknown)
            {
                checks++;
                if (ParseTeamId(v) != -1) { pass = false; detail += " parse:" + (v ?? "null"); }
            }
            checks++;
            if (ParseTeamId("0") != 0 || ParseTeamId(1) != 1) { pass = false; detail += " parse:0/1"; }

            return SentinelTag + " " + (pass ? "PASS" : "FAIL") + ": " + checks + " checks" + detail;
        }
    }
}
