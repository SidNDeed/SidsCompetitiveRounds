using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    using N = TeamHoldNet;
    using R = TeamHoldRules;

    internal static partial class Program
    {
        // ── KX9 Part B: the answers the server staging tip lands (NX1 to NX4) ──

        // The claim answer of match_hold.match_hold_claim at the staging tip:
        // _state_payload, then status, token, hold, room_region,
        // boundary_digest, series_id, series_tally and roster ({steam_id,
        // slot, team} per seat in slot order, match_hold._roster).
        private const string ClaimRoster =
            "\"roster\":[{\"steam_id\":\"1001\",\"slot\":0,\"team\":0},{\"steam_id\":\"1002\",\"slot\":1,\"team\":1},"
            + "{\"steam_id\":\"1003\",\"slot\":2,\"team\":0},{\"steam_id\":\"1004\",\"slot\":3,\"team\":1}]";
        private const string ClaimState =
            "\"hold_id\":\"h1\",\"game_id\":\"g-8\",\"mode\":\"team\",\"room_name\":\"team_ab12\",\"slot\":1,\"team\":1,\"n\":1,"
            + "\"state\":\"claimed\",\"seq\":3,\"deadline_s\":50,\"hold_s\":50,\"bound_actor\":null,\"verifier\":\"ab\","
            + "\"closed_at\":null,\"closed_reason\":null";
        private const string ClaimTail =
            "\"status\":\"claimed\",\"token\":\"tok-1\",\"hold\":true,\"room_region\":\"eu\",\"boundary_digest\":\"d1\","
            + "\"series_id\":\"s-1\",\"series_tally\":[1,0]";

        private static void RegisterKX9B()
        {
            // T1.6: the join answers' `hold` is their own top-level field
            // (NX1: TeamQueuePollResponse.hold beside the rules dict and the
            // member lists; the 1v2 locked payload's hold beside solo/duo).
            Add("t16_join_hold_top_level", () =>
            {
                R.ClearPins();
                var roster = new[] { "1001", "1002", "1003", "1004" };
                string team = "{\"status\":\"ready_join\",\"queue_count\":4,\"elo_range\":0,\"series_id\":\"s-1\",\"team_assigned\":1,"
                              + "\"teammates\":[{\"steam_id\":\"1002\",\"display_name\":\"b\",\"hold\":false}],"
                              + "\"opponents\":[{\"steam_id\":\"1003\",\"display_name\":\"c\"},{\"steam_id\":\"1004\",\"display_name\":\"d\"}],"
                              + "\"room_name\":\"team_ab12\",\"room_region\":\"eu\",\"match_age_seconds\":0,\"my_ready\":false,"
                              + "\"rules\":{\"hold\":false},\"rules_prop\":null,\"hold\":true}";
                N.PinFromJoin(team, R.MODE_TEAM, "team_ab12", "s-1", roster);
                string ovt = "{\"status\":\"ready_join\",\"series_id\":\"s-2\",\"side_assigned\":\"duo\",\"room_name\":\"ovt_ef56\","
                             + "\"room_region\":\"eu\",\"rules\":{\"hold\":true},\"rules_prop\":null,\"solo_extra_pick\":false,\"hold\":false,"
                             + "\"solo\":{\"steam_id\":\"1001\",\"display_name\":\"a\"},\"duo\":[{\"steam_id\":\"1002\",\"display_name\":\"b\"}]}";
                N.PinFromJoin(ovt, R.MODE_OVT, "ovt_ef56", "s-2", new[] { "1001", "1002", "1003" });
                return All(Expect("team flagged", R.Flagged("team_ab12"), true),
                           Expect("ovt unflagged", R.Flagged("ovt_ef56"), false),
                           Expect("top level", N.TopLevel("{\"a\":{\"hold\":1},\"b\":[1,{\"c\":2}],\"hold\":true}"), "{\"a\":null,\"b\":null,\"hold\":true}"));
            });

            // T3.9: the claim answer's roster (NX1) pins the series roster.
            Add("t39_claim_roster_pins", () =>
            {
                R.ClearPins();
                N.ClaimAnswer a;
                bool p = N.TryParseClaim(200, "{" + ClaimState + "," + ClaimTail + "," + ClaimRoster + "}", out a);
                if (!p || a == null || !a.Ok) return "claim not parsed";
                R.PinRoom(a.Room, a.Hold, R.MODE_TEAM, a.SeriesId, a.Roster);
                var lr = R.LockRoster("team_ab12", () => new string[0]);
                return All(Expect("roster", a.Roster == null ? "null" : string.Join(",", a.Roster), "1001,1002,1003,1004"),
                           Expect("slot", a.Slot, 1), Expect("team", a.Team, 1), Expect("tally", a.W0 + ":" + a.W1, "1:0"),
                           Expect("flagged", R.Flagged("team_ab12"), true),
                           Expect("lock roster", lr == null ? "null" : string.Join(",", lr), "1001,1002,1003,1004"),
                           Expect("no roster", RosterOrNull("{" + ClaimState + "," + ClaimTail + "}"), "null"));
            });

            // T3.9: the claim's own slot, team and game id are the top-level
            // fields whatever the key order (the roster objects carry slot and
            // team too; JSON key order is no contract).
            Add("t39_claim_top_level_slot", () =>
            {
                N.ClaimAnswer a;
                bool p = N.TryParseClaim(200, "{" + ClaimRoster + "," + ClaimTail + "," + ClaimState + "}", out a);
                if (!p || a == null || !a.Ok) return "claim not parsed";
                return All(Expect("slot", a.Slot, 1), Expect("team", a.Team, 1), Expect("g", a.G, "g-8"),
                           Expect("roster", a.Roster == null ? 0 : a.Roster.Count, 4));
            });

            // T3.9: the rdm=1 poll belt (NX3 _s2_poll_readmissible): the team
            // and 1v2 polls ask with rdm=1 and read a readmissible answer as
            // the discovery answer; a poll of today is not one.
            Add("t39_rdm_poll_belt", () =>
            {
                string rdm = "{\"hold_id\":\"h2\",\"game_id\":\"g-9\",\"mode\":\"ovt\",\"room_name\":\"ovt_ef56\",\"slot\":2,\"team\":1,\"n\":1,"
                             + "\"state\":\"opened\",\"seq\":1,\"deadline_s\":40,\"hold_s\":40,\"bound_actor\":null,\"verifier\":null,"
                             + "\"closed_at\":null,\"closed_reason\":null,\"status\":\"readmissible\",\"readmissible\":1,"
                             + "\"room_region\":\"eu\",\"series_tally\":[0,1]}";
                N.MineAnswer a, b;
                bool yes = N.PollReadmissible(rdm, out a);
                bool no = N.PollReadmissible("{\"status\":\"searching\",\"queue_count\":2,\"elo_range\":100}", out b);
                if (!yes || a == null) return "readmissible poll not read";
                return All(Expect("query on", N.PollQuery(true), "?rdm=1"), Expect("query off", N.PollQuery(false), ""),
                           Expect("hold", a.HoldId, "h2"), Expect("mode", a.Mode, R.MODE_OVT), Expect("room", a.Room, "ovt_ef56"),
                           Expect("slot", a.Slot, 2), Expect("team", a.Team, 1), Expect("hold_s", a.HoldS, 40),
                           Expect("tally", a.W0 + ":" + a.W1, "0:1"), Expect("region", a.Region, "eu"),
                           Expect("today", no, false), Expect("shows", R.DiscoveryShows(a), true));
            });

            // T5.8: the advisory game id names the raw flagged room (NX4: the
            // server verifies game-id:{G}:{reporter}:{room} over the series
            // hold_room), not the per-game report room.
            Add("t58_game_id_raw_room", () =>
            {
                R.ClearPins();
                N.PinFromJoin("{\"status\":\"ready_join\",\"room_name\":\"team_ab12\",\"hold\":true}", R.MODE_TEAM, "team_ab12", "s-1",
                              new[] { "1001", "1002", "1003", "1004" });
                Func<string, string> sign = m => "sig(" + m + ")";
                string got = R.GameIdAdvisoryFor("team_ab12_123456_r3", "team_ab12", "g-8:2", "1002", sign);
                return All(Expect("raw", R.HoldRoomOfReport("team_ab12_123456_r3"), "team_ab12"),
                           Expect("unsuffixed", R.HoldRoomOfReport("team_ab12"), "team_ab12"),
                           Expect("short digits", R.HoldRoomOfReport("team_ab12_12345_r3"), "team_ab12_12345_r3"),
                           Expect("fields", got, "\"game_id\":\"g-8\",\"game_id_sig\":\"sig(game-id:g-8:1002:team_ab12)\","),
                           Expect("other room", R.GameIdAdvisoryFor("team_cd34_123456_r1", "team_ab12", "g-8:2", "1002", sign), ""),
                           Expect("not in room", R.GameIdAdvisoryFor("team_ab12_123456_r3", "", "g-8:2", "1002", sign), ""),
                           Expect("no g", R.GameIdAdvisoryFor("team_ab12_123456_r3", "team_ab12", "", "1002", sign), ""));
            });

            // T3.6: during a hold the three present attest a short roster
            // the server accepts over its held set (NX3); elsewhere today.
            Add("t36_attest_short_roster", () =>
            {
                R.ClearPins();
                N.PinFromJoin("{\"status\":\"ready_join\",\"room_name\":\"team_ab12\",\"hold\":true}", R.MODE_TEAM, "team_ab12", "s-1",
                              new[] { "1001", "1002", "1003", "1004" });
                N.PinFromJoin("{\"status\":\"ready_join\",\"room_name\":\"team_cd34\",\"hold\":false}", R.MODE_TEAM, "team_cd34", "s-2",
                              new[] { "1001", "1002", "1003", "1004" });
                string th = "h1:1:1:g-8:o:2:50:1:0", closed = "h1:1:1:g-8:x:5:0:1:0";
                var three = new List<string> { "1001", "1003", "1004" };
                var four = new List<string> { "1001", "1002", "1003", "1004" };
                var stranger = new List<string> { "1001", "1003", "1009" };
                return All(Expect("short over hold", R.AttestTarget("team_ab12", 4, th, three), 3),
                           Expect("full", R.AttestTarget("team_ab12", 4, th, four), 4),
                           Expect("unflagged", R.AttestTarget("team_cd34", 4, th, three), -1),
                           Expect("no live hold", R.AttestTarget("team_ab12", 4, closed, three), -1),
                           Expect("two short", R.AttestTarget("team_ab12", 4, th, new List<string> { "1001", "1003" }), -1),
                           Expect("stranger", R.AttestTarget("team_ab12", 4, th, stranger), -1),
                           Expect("1v2 full", R.AttestTarget("ovt_x", 3, "", new List<string> { "1", "2", "3" }), 3));
            });
        }

        private static string RosterOrNull(string body)
        {
            var r = N.RosterIds(body);
            return r == null ? "null" : string.Join(",", r);
        }
    }
}
