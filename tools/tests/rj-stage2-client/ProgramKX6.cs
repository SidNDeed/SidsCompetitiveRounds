using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;

    internal static partial class Program
    {
        // ── KX6: the reports after a return (V3 S5, client half) ─────────────

        private static void RegisterKX6()
        {
            // T5.5: after a return every present fighter files G. The
            // continuous seat with the lowest id (1001) drops at the
            // game-over edge and files nothing; the three others still file,
            // so the server has a report to settle. A room not flagged keeps
            // the election of today (only the lowest files).
            Add("t55_every_present_files", () =>
            {
                R.ClearPins(); R.PinRoom("team_ab12", true, R.MODE_TEAM, "series-1", new[] { "1001", "1002", "1003", "1004" });
                var census = new[] { "1001", "1002", "1003", "1004" };
                string lowest = census.OrderBy(s => long.Parse(s)).First();
                int filed = new[] { "1002", "1003", "1004" }.Count(me => R.Files("team_ab12", me, lowest));
                int today = census.Count(me => R.Files("team_other", me, lowest));
                return All(Expect("filed", filed, 3), Expect("today", today, 1));
            });
            // T5.7 client half: a game-over during a hold counts the held seat
            // from the pinned roster (2v2 four, 1v2 three); a stranger, a seat
            // off the roster or a census short by two is the census of today.
            Add("t57_held_census", () =>
            {
                R.ClearPins();
                R.PinRoom("team_ab12", true, R.MODE_TEAM, "series-1", new[] { "1001", "1002", "1003", "1004" });
                R.PinRoom("ovt_ef56", true, R.MODE_OVT, "series-3", new[] { "1001", "1002", "1003" });
                string team = R.HeldCensusSeat("team_ab12", new[] { "1001", "1003", "1004" }, "1002", 4);
                string ovt = R.HeldCensusSeat("ovt_ef56", new[] { "1001", "1003" }, "1002", 3);
                string stranger = R.HeldCensusSeat("team_ab12", new[] { "1001", "1003", "1009" }, "1002", 4);
                string two = R.HeldCensusSeat("team_ab12", new[] { "1001", "1003" }, "1002", 4);
                string unflagged = R.HeldCensusSeat("team_other", new[] { "1001", "1003", "1004" }, "1002", 4);
                return All(Expect("team", team, "1002"), Expect("ovt", ovt, "1002"), Expect("stranger", stranger, null),
                           Expect("two short", two, null), Expect("unflagged", unflagged, null));
            });
            Add("tx6_route_ovt_held", () =>
            {
                GameOverReportRouter.Reset("ovt_ef56", true, R.MODE_OVT, new[] { "1001", "1003" }, "1002", "1003", false, false);
                GameOverReportRouter.Run();
                return All(Expect("builder called", GameOverReportRouter.OvtCalls, 1),
                           Expect("held census reported", GameOverReportRouter.Reported, true));
            });
            Add("tx6_route_team_held", () =>
            {
                GameOverReportRouter.Reset("team_ab12", true, R.MODE_TEAM, new[] { "1001", "1003", "1004" }, "1002", "1004", false, false);
                GameOverReportRouter.Run();
                return All(Expect("builder called", GameOverReportRouter.TeamCalls, 1),
                           Expect("held census reported", GameOverReportRouter.Reported, true));
            });
            Add("tx6_route_every_returned_filer", () =>
            {
                foreach (string mode in new[] { R.MODE_OVT, R.MODE_TEAM })
                {
                    bool ovt = mode == R.MODE_OVT;
                    var present = ovt ? new[] { "1001", "1002", "1003" } : new[] { "1001", "1002", "1003", "1004" };
                    foreach (string me in present)
                    {
                        GameOverReportRouter.Reset(ovt ? "ovt_ef56" : "team_ab12", true, mode, present, null, me, false, me == "1001");
                        GameOverReportRouter.Run();
                        string why = All(Expect("builder called for " + me, ovt ? GameOverReportRouter.OvtCalls : GameOverReportRouter.TeamCalls, 1),
                                         Expect("filer " + me, GameOverReportRouter.Reported, true));
                        if (why != null) return why;
                    }
                }
                return null;
            });
            Add("tx6_route_offline", () =>
            {
                foreach (bool elected in new[] { false, true })
                {
                    GameOverReportRouter.Reset("team_ab12", true, R.MODE_TEAM, new[] { "1001", "1002", "1003", "1004" }, null,
                                               "1004", true, elected);
                    GameOverReportRouter.Run();
                    string why = All(Expect("offline builder calls", GameOverReportRouter.TeamCalls, 0),
                                     Expect("offline reports", GameOverReportRouter.Reported, false));
                    if (why != null) return why;
                }
                return null;
            });
            Add("tx6_route_unflagged_election", () =>
            {
                foreach (bool elected in new[] { false, true })
                {
                    GameOverReportRouter.Reset("team_other", false, R.MODE_TEAM, new[] { "1001", "1002", "1003", "1004" }, null,
                                               elected ? "1001" : "1004", false, elected);
                    GameOverReportRouter.Run();
                    string why = All(Expect("legacy builder calls", GameOverReportRouter.TeamCalls, elected ? 1 : 0),
                                     Expect("legacy filer", GameOverReportRouter.Reported, elected));
                    if (why != null) return why;
                }
                return null;
            });
            Add("tx6_route_invalid_short", () =>
            {
                foreach (var present in new[] { new[] { "1001", "1003" }, new[] { "1001", "1003", "1009" } })
                {
                    GameOverReportRouter.Reset("team_ab12", true, R.MODE_TEAM, present, "1002", "1003", false, false);
                    GameOverReportRouter.Run();
                    string why = All(Expect("builder validates short census", GameOverReportRouter.TeamCalls, 1),
                                     Expect("invalid short census rejected", GameOverReportRouter.Reported, false));
                    if (why != null) return why;
                }
                GameOverReportRouter.Reset("ovt_ef56", true, R.MODE_OVT, new[] { "1001" }, "1002", "1001", false, true);
                GameOverReportRouter.Run();
                string ovtWhy = All(Expect("ovt builder validates short census", GameOverReportRouter.OvtCalls, 1),
                                    Expect("ovt short by two rejected", GameOverReportRouter.Reported, false));
                if (ovtWhy != null) return ovtWhy;
                foreach (bool flagged in new[] { false, true })
                {
                    GameOverReportRouter.Reset("team_ab12", flagged, R.MODE_TEAM, new[] { "1001", "1003", "1004" },
                                               flagged ? "1009" : "1002", "1001", false, true);
                    GameOverReportRouter.Run();
                    string why = All(Expect("builder checks pinned roster", GameOverReportRouter.TeamCalls, 1),
                                     Expect("unflagged or off-roster hold rejected", GameOverReportRouter.Reported, false));
                    if (why != null) return why;
                }
                return null;
            });
            // The advisory game id: its own canonical, fields only in a
            // flagged room with a G and a signature.
            Add("tx6_game_id", () =>
            {
                R.ClearPins(); R.PinRoom("team_ab12", true, R.MODE_TEAM, "series-1", new[] { "1001" });
                return All(Expect("canonical", R.GameIdCanonical("g-8", "1002", "team_ab12"), "game-id:g-8:1002:team_ab12"),
                           Expect("fields", R.GameIdFields("team_ab12", "g-8", "abc"), "\"game_id\":\"g-8\",\"game_id_sig\":\"abc\","),
                           Expect("no sig", R.GameIdFields("team_ab12", "g-8", ""), ""),
                           Expect("unflagged", R.GameIdFields("team_other", "g-8", "abc"), ""));
            });
            // The 202 journaled answer is terminal for the outbox (no
            // re-queue); a failure is not.
            Add("tx6_journaled_terminal", () =>
            {
                string body = "{\"status\": \"journaled\", \"cls\": \"c\"}";
                return All(Expect("journaled", R.Journaled(body), true), Expect("terminal", R.ReportTerminal(true, body), true),
                           Expect("failure", R.ReportTerminal(false, "HTTP 503: {}"), false), Expect("settled", R.Journaled("{\"status\":\"settled\"}"), false));
            });
        }
    }

    // The runner extracts the route blocks, builder census prefixes, filer
    // checks and HeldCensusSid from GameStateWatcher into the derived class.
    // These stubs provide room state and record dispatch without networking.
    internal class GameOverReportRouterBase
    {
        protected static string rn1, reportRoomId = "report", localSteamId;
        protected static bool isOfflineMatch, electedReporter, hasSeries, localWon, isTracking, matchIsRanked;
        protected static int duration;
        internal static int OvtCalls, TeamCalls;
        internal static bool Reported;
        protected static Photon.Realtime.Player[] Fighters;
        protected static string Lowest;
        internal static void Reset(string room, bool flagged, string mode, string[] present, string held, string me, bool offline, bool elected)
        {
            TeamHoldRules.ClearPins();
            string[] roster = mode == TeamHoldRules.MODE_OVT ? new[] { "1001", "1002", "1003" } : new[] { "1001", "1002", "1003", "1004" };
            TeamHoldRules.PinRoom(room, flagged, mode, "series", roster);
            rn1 = room; localSteamId = me; isOfflineMatch = offline; electedReporter = elected;
            hasSeries = isTracking = matchIsRanked = true;
            localWon = false; duration = 1; OvtCalls = TeamCalls = 0; Reported = false; Lowest = "1001";
            Fighters = present.Select(s => new Photon.Realtime.Player { Sid = s }).ToArray();
            TeamHold.Cut = held == null ? null : new HeldCut { LeaverUid = held, Slot = 1 };
        }
        protected static void EvaluateAchievements(bool won) { }
        protected static string ResolvePhotonSteamId(Photon.Realtime.Player player) { return player.Sid; }
        protected sealed class TeamReportPayload
        {
            internal string ReporterSteam;
            internal bool LocalIsReporter;
        }
        protected static class Photon
        {
            internal static class Realtime { internal sealed class Player { internal string Sid; } }
        }
        protected static class RoomActors
        {
            internal static Photon.Realtime.Player[] ActiveFighters() { return Fighters; }
            internal static int ActiveFighterCount() { return Fighters.Length; }
        }
        protected sealed class HeldCut { internal string LeaverUid; internal int Slot; }
        protected static class TeamHold
        {
            internal const string TAG = "hold";
            internal static HeldCut Cut;
        }
        protected static class TeamHoldWriter
        {
            internal static string CurrentRoom() { return rn1; }
            internal static string RoomProp(string key)
            {
                return TeamHold.Cut == null ? "" : new TeamHoldRules.HoldKey { HoldId = "hold", Slot = 1, Team = 0, G = "game", State = 'o', Seq = 1 }.Format();
            }
        }
        protected static class Plugin
        {
            internal static readonly Logger Log = new Logger();
            internal sealed class Logger
            {
                internal void LogInfo(string line) { }
                internal void LogWarning(string line) { }
            }
        }
    }
}
