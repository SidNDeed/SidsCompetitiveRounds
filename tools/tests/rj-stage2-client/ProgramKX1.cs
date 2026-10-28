using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;
    using N = TeamHoldNet;

    internal static partial class Program
    {
        // ── KX1: the bound transport, the session gate, the join pin, the
        //    answers in the server half's shapes ────────────────────────────

        /// <summary>A fake of ApiClient's shared path: records every call it
        /// was handed and answers with <paramref name="reply"/>.</summary>
        private sealed class SharedFake
        {
            internal readonly List<string> Calls = new List<string>();
            internal Func<string, Tuple<bool, string>> Reply = path => Tuple.Create(true, "{\"status\":\"ok\"}");
            internal void Send(string method, string path, string body, Action<bool, string> answer)
            {
                Calls.Add(method + " " + path);
                var r = Reply(path);
                answer(r.Item1, r.Item2);
            }
        }

        private static N.Transport BindFake(SharedFake f, string token, bool carries = true)
        {
            return N.Bound(() => token, p => carries, f.Send);
        }

        /// <summary>The writer of T2.9's form over the BOUND transport: a
        /// drop, the open posted through N.Call, its answer parsed.</summary>
        private static WriterRig OpenThroughCall()
        {
            var rig = new WriterRig();
            rig.Answer = op =>
            {
                int st = -1; string body = null;
                N.Call("POST", N.PathOpen, "{}", (s, b) => { st = s; body = b; });
                N.OpenAnswer oa; N.TryParseOpen(st, body, out oa);
                return Tuple.Create(st, (object)oa);
            };
            rig.Run(0, rig.W.OnDrop(0, 1, 0, "g-7", 2, "req-kx1"));
            return rig;
        }

        private const string OpenedBody = "{\"hold_id\":\"h1\",\"game_id\":\"g-7\",\"mode\":\"team\",\"room_name\":\"team_ab12\",\"slot\":1,\"team\":0,\"n\":1,"
                                        + "\"state\":\"opened\",\"seq\":0,\"deadline_s\":110,\"hold_s\":110,\"bound_actor\":null,\"closed_at\":null,"
                                        + "\"closed_reason\":null,\"status\":\"opened\",\"repeat\":false}";

        private static void RegisterKX1()
        {
            // (a): no session token: nothing is sent and the call answers
            // NoTransport, so the writer ends at once toward today.
            Add("tx1_no_token_today", () =>
            {
                var f = new SharedFake();
                N.Send = BindFake(f, "");
                var rig = OpenThroughCall();
                int st = -1; N.Call("GET", N.PathMine, null, (s, b) => st = s);
                var g = new SharedFake();
                N.Send = BindFake(g, "tok", carries: false);
                int st2 = -1; N.Call("GET", N.PathMine, null, (s, b) => st2 = s);
                return All(Expect("calls sent", f.Calls.Count, 0), Expect("status", st, N.NoTransport),
                           Expect("writer x", rig.LastState(), 'x'), Expect("writer at once", rig.DoneAt, 0.0),
                           Expect("withheld transport sent", g.Calls.Count, 0), Expect("withheld status", st2, N.NoTransport));
            });
            // (a): with the token the call reaches the route, and the open
            // answer in the server's shape opens the hold.
            Add("tx1_token_reaches_route", () =>
            {
                var f = new SharedFake { Reply = p => Tuple.Create(true, OpenedBody) };
                N.Send = BindFake(f, "tok");
                var rig = OpenThroughCall();
                return All(Expect("calls", string.Join(",", f.Calls), "POST " + N.PathOpen),
                           Expect("writer o", rig.LastState(), 'o'), Expect("writer done", rig.DoneAt, -1.0));
            });
            // (a): a 401 session_required ends toward today exactly as no
            // transport does.
            Add("tx1_401_today", () =>
            {
                var f = new SharedFake { Reply = p => Tuple.Create(false, "HTTP 401: {\"detail\":\"session_required\"}") };
                N.Send = BindFake(f, "tok");
                var rig = OpenThroughCall();
                int st = -1; string body = null;
                N.Call("GET", N.PathMine, null, (s, b) => { st = s; body = b; });
                return All(Expect("sent", f.Calls.Count, 2), Expect("status", st, N.NoTransport), Expect("body", body, N.SessionRequired),
                           Expect("writer x", rig.LastState(), 'x'), Expect("writer at once", rig.DoneAt, 0.0));
            });
            // The shared path's text mapped to a status: a refusal keeps its
            // code and body (the Retry-After line dropped); a timeout is no answer.
            Add("tx1_map_codes", () =>
            {
                int a, b, c, d; string ba, bb, bc, bd;
                N.MapShared(false, "HTTP 404: {\"detail\":\"no such hold\"}\nRetry-After: 5", out a, out ba);
                N.MapShared(false, "Cannot connect to destination host", out b, out bb);
                N.MapShared(true, "{\"status\":\"ok\"}", out c, out bc);
                N.MapShared(false, "HTTP 403: {\"detail\":\"Invalid hold-open signature\"}", out d, out bd);
                return All(Expect("404", a, 404), Expect("404 body", ba, "{\"detail\":\"no such hold\"}"),
                           Expect("timeout", b, N.NoTransport), Expect("ok", c, 200), Expect("ok body", bc, "{\"status\":\"ok\"}"),
                           Expect("403", d, 403));
            });
            // T1.6 end to end, client half: a room issued with one member
            // lacking rjs1 answers hold false (or, before the server's join
            // routes carry it, no hold at all): the pin is false and every
            // departure runs today. The same answer with hold true flags the
            // room and admits a roster member (the positive control), and
            // never a stranger.
            Add("t16_join_pin_today", () =>
            {
                R.ClearPins(); R.HoldGate.Clear();
                var roster = new[] { "1001", "1002", "1003", "1004" };
                N.PinFromJoin("{\"status\":\"ready_join\",\"room_name\":\"team_ab12\",\"hold\":false}", R.MODE_TEAM, "team_ab12", "series-1", roster);
                N.PinFromJoin("{\"status\":\"ready_join\",\"room_name\":\"team_cd34\"}", R.MODE_TEAM, "team_cd34", "series-2", roster);
                bool any = false;
                for (int actor = 1; actor <= 4; actor++)
                {
                    var i = Admitted(R.PinFor(actor % 2 == 0 ? "team_ab12" : "team_cd34"));
                    any |= R.HoldGate.DecideOnce(actor, () => i);
                }
                N.PinFromJoin("{\"status\":\"ready_join\",\"room_name\":\"ovt_ef56\",\"hold\":true}", R.MODE_OVT, "ovt_ef56", "series-3", new[] { "1001", "1002", "1003" });
                var member = Admitted(R.PinFor("ovt_ef56"));
                var stranger = Admitted(R.PinFor("ovt_ef56")); stranger.Uid = "1009";
                N.PinFromJoin("{\"hold\":false}", R.MODE_OVT, "ovt_ef56", "series-3", new[] { "1001" });
                return All(Expect("flag false", R.Flagged("team_ab12"), false), Expect("no hold", R.Flagged("team_cd34"), false),
                           Expect("suppressed", any, false), Expect("flagged", R.Flagged("ovt_ef56"), true),
                           Expect("member", R.HoldGate.Decide(member), true), Expect("stranger", R.HoldGate.Decide(stranger), false),
                           Expect("pin written once", R.Flagged("ovt_ef56"), true));
            });
            // (c): the answers in the server half's shapes (match_hold.py at
            // fe0ab988): status words, the opened state, the tally array, a
            // claim or entry refused with HTTP 200.
            Add("tx1_server_shapes", () =>
            {
                N.OpenAnswer oa; N.StateAnswer sa; N.MineAnswer ma; N.ClaimAnswer ca, cr; bool bound; string br, er, er2;
                bool open = N.TryParseOpen(200, OpenedBody, out oa);
                bool refusedOpen = N.TryParseOpen(200, "{\"status\":\"refused\",\"reason\":\"no_presence\"}", out var ro);
                bool state = N.TryParseState(200, OpenedBody, out sa);
                N.TryParseMine(200, "{\"readmissible\":1,\"hold_id\":\"h1\",\"game_id\":\"g-7\",\"mode\":\"ovt\",\"room_name\":\"ovt_ef56\",\"slot\":2,"
                                    + "\"team\":1,\"n\":1,\"state\":\"opened\",\"seq\":0,\"deadline_s\":80,\"hold_s\":80,\"room_region\":\"eu\","
                                    + "\"series_tally\":[2, 1]}", out ma);
                N.TryParseClaim(200, "{\"status\":\"refused\",\"reason\":\"other_mode\"}", out cr);
                N.TryParseClaim(200, ClaimBody, out ca);
                N.TryParseBind(200, "{\"status\":\"refused\",\"reason\":\"uncorroborated\"}", out bound, out br);
                bool entered = N.TryParseEntered(200, "{\"status\":\"entered\",\"state\":\"entered\"}", out er);
                bool enteredRefused = N.TryParseEntered(200, "{\"status\":\"refused\",\"reason\":\"actor_mismatch\"}", out er2);
                return All(Expect("open", open && oa.Opened && oa.HoldId == "h1" && oa.HoldS == 110, true),
                           Expect("open refused", refusedOpen && !ro.Opened && ro.Reason == "no_presence", true),
                           Expect("state o", state ? sa.State : '?', 'o'),
                           Expect("mine", ma.Readmissible && ma.W0 == 2 && ma.W1 == 1 && ma.Mode == R.MODE_OVT, true),
                           Expect("claim refused", !cr.Ok && cr.Reason == "other_mode", true),
                           Expect("claim", ca.Ok && ca.Token == "tok-genuine" && ca.Hold, true),
                           Expect("bind retry", !bound && br == "uncorroborated", true),
                           Expect("entered", entered, true), Expect("entered refused", !enteredRefused && er2 == "actor_mismatch", true));
            });
        }
    }
}
