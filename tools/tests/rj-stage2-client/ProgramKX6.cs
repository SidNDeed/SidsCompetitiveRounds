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
}
