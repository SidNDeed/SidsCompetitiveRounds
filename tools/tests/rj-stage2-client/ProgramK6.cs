using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;
    using N = TeamHoldNet;
    using Stage = TeamHoldRules.ReturnRoute.Stage;

    internal static partial class Program
    {
        // ── K6: S6 client, the ladder lines ───────────────────────────────

        /// <summary>Runs body with the ladder sink bound to a list and
        /// returns every line it emitted; the previous sink is restored.</summary>
        private static List<string> Capture(Action body)
        {
            var lines = new List<string>();
            var prev = SeatDeckLog.Ladder;
            SeatDeckLog.Ladder = l => lines.Add(l);
            try { body(); }
            finally { SeatDeckLog.Ladder = prev; }
            return lines;
        }

        private static string Lines(IEnumerable<string> l) { return string.Join(" | ", l); }

        private static string ExpectLines(List<string> got, params string[] want)
        {
            return Expect("lines", Lines(got), Lines(want));
        }

        private static bool IsLadder(string l)
        {
            return l.StartsWith("[HOLD] ", StringComparison.Ordinal) || l.StartsWith("[SEATLOG] ", StringComparison.Ordinal);
        }

        // The server half's claim answer (match_hold.py match_hold_claim at
        // fe0ab988): the state payload plus status, token, hold, room_region
        // and boundary_digest; no series_tally, series_id or roster.
        private const string ClaimBody = "{\"hold_id\":\"h1\",\"game_id\":\"g-7\",\"mode\":\"team\",\"room_name\":\"team_x\",\"slot\":1,\"team\":0,\"n\":1,"
                                       + "\"state\":\"claimed\",\"seq\":0,\"deadline_s\":90,\"hold_s\":90,\"bound_actor\":null,\"closed_at\":null,\"closed_reason\":null,"
                                       + "\"status\":\"claimed\",\"token\":\"tok-genuine\",\"hold\":true,\"room_region\":\"eu\",\"boundary_digest\":\"d0\"}";

        private static void RegisterK6()
        {
            // The one computation that holds emits once; the memo read of the
            // second caller (prefix or callback) emits nothing.
            Add("t6_cascade_suppressed", () =>
            {
                R.HoldGate.Clear();
                bool a = false, b = false;
                var got = Capture(() =>
                {
                    a = R.HoldGate.DecideOnce(5, () => Admitted(TeamPin()));
                    b = R.HoldGate.DecideOnce(5, () => Admitted(TeamPin()));
                });
                return All(Expect("first", a, true), Expect("memo", b, true), ExpectLines(got, "[HOLD] cascade suppressed slot=1"));
            });
            // The first verified o of a hold; a repeated o and the later
            // states emit nothing.
            Add("t6_held", () =>
            {
                var got = Capture(() =>
                {
                    R.NoteShown('p', 'o', 1);
                    R.NoteShown('o', 'o', 1);
                    R.NoteShown('o', 'c', 1);
                    R.NoteShown('c', 'b', 1);
                    R.NoteShown('b', 'e', 1);
                });
                return ExpectLines(got, "[HOLD] held slot=1");
            });
            Add("t6_offered", () =>
            {
                N.MineAnswer a;
                N.TryParseMine(200, "{\"readmissible\":1,\"hold_id\":\"h1\",\"mode\":\"team\",\"room_name\":\"team_x\",\"slot\":1,\"team\":0,\"hold_s\":100,\"series_tally\":[1, 0]}", out a);
                bool shown = false;
                var got = Capture(() => shown = R.DiscoveryShows(a));
                return All(Expect("shown", shown, true), ExpectLines(got, "[HOLD] offered mode=team slot=1"));
            });
            // A claimed answer emits; a refusal and a malformed answer do not.
            Add("t6_claimed", () =>
            {
                N.ClaimAnswer ok = null, refused = null, bad = null;
                var got = Capture(() =>
                {
                    N.TryParseClaim(200, ClaimBody, out ok);
                    N.TryParseClaim(409, "{\"reason\":\"lapsed\"}", out refused);
                    N.TryParseClaim(200, "{\"room_name\":\"team_x\",\"slot\":1,\"game_id\":\"g-7\"}", out bad);
                });
                return All(Expect("ok", ok != null && ok.Ok, true), Expect("refused", refused != null && !refused.Ok, true),
                           Expect("malformed", bad != null && !bad.Ok, true), ExpectLines(got, "[HOLD] claimed slot=1 g=g-7"));
            });
            Add("t6_bound", () =>
            {
                bool b1 = false, b2 = true; string r1, r2;
                var got = Capture(() =>
                {
                    N.TryParseBind(200, "{\"status\":\"bound\",\"seq\":4}", out b1, out r1);
                    N.TryParseBind(409, "{\"reason\":\"uncorroborated\"}", out b2, out r2);
                });
                return All(Expect("bound", b1, true), Expect("retry", b2, false), ExpectLines(got, "[HOLD] bound"));
            });
            // The in-order Entered stage emits; an out-of-order one ends the
            // route and emits nothing.
            Add("t6_entered", () =>
            {
                var r = new R.ReturnRoute { Slot = 1 };
                var skip = new R.ReturnRoute { Slot = 2 };
                var got = Capture(() =>
                {
                    double t = 0;
                    foreach (var st in new[] { Stage.Claim, Stage.Join, Stage.Bind, Stage.Token, Stage.Latch, Stage.Snapshot, Stage.Register, Stage.Activate, Stage.Entered })
                        r.Done(st, true, t++);
                    skip.Done(Stage.Claim, true, 0);
                    skip.Done(Stage.Entered, true, 1);
                });
                return All(Expect("route", r.S, Stage.Released), Expect("skipped", skip.S, Stage.Ended), ExpectLines(got, "[HOLD] entered slot=1"));
            });
            Add("t6_token_refused", () =>
            {
                string v = Sha256Hex("tok-genuine");
                bool genuine = false, forged = true;
                var got = Capture(() =>
                {
                    genuine = R.TokenCheck("h1:tok-genuine", "h1", v, 6);
                    forged = R.TokenCheck("h1:tok-forged", "h1", v, 7);
                });
                return All(Expect("genuine", genuine, true), Expect("forged", forged, false), ExpectLines(got, "[HOLD] token refused actor=7"));
            });
            Add("t6_record_late", () =>
            {
                var got = Capture(() =>
                {
                    R.RecordLateFor(1, 0, 3.9, false);
                    R.RecordLateFor(1, 0, 9, true);
                    R.RecordLateFor(1, 0, 4.0, false);
                });
                return ExpectLines(got, "[HOLD] record late slot=1");
            });
            Add("t6_audit", () =>
            {
                var got = Capture(() => { R.AuditLine(1, true); R.AuditLine(2, false); });
                return ExpectLines(got, "[HOLD] audit slot=1 match=1", "[HOLD] audit slot=2 match=0");
            });
            // An applied grant emits; a grant of another game emits nothing.
            Add("t6_auto_grant", () =>
            {
                DeckOf(1, "Barrage", "Leech");
                R.GrantOutcome o = R.GrantOutcome.Refused, other = R.GrantOutcome.Applied;
                var got = Capture(() =>
                {
                    o = R.ApplyGrant("g-7", "g-7", 1, 2, "Shield");
                    other = R.ApplyGrant("g-6", "g-7", 1, 3, "Bomb");
                });
                return All(Expect("applied", o, R.GrantOutcome.Applied), Expect("other", other, R.GrantOutcome.Refused),
                           ExpectLines(got, "[HOLD] auto grant slot=1 card=Shield"));
            });
            Add("t6_grant_superseded", () =>
            {
                DeckOf(1, "Barrage", "Leech", "Bomb");
                R.GrantOutcome o = R.GrantOutcome.Applied;
                var got = Capture(() => o = R.ApplyGrant("g-7", "g-7", 1, 2, "Shield"));
                return All(Expect("superseded", o, R.GrantOutcome.Superseded), ExpectLines(got, "[HOLD] grant superseded slot=1 k=2"));
            });
            // The first mismatch per slot per game emits; equal and repeated
            // checks emit nothing.
            Add("t6_drift", () =>
            {
                SeatDeckLog.OnGameStart();
                Apply(800, "A", new[] { 1 });
                var got = Capture(() =>
                {
                    SeatDeckLog.DriftCheck(1, new List<string> { "A" });
                    SeatDeckLog.DriftCheck(1, new List<string> { "A", "B" });
                    SeatDeckLog.DriftCheck(1, new List<string> { "A", "B" });
                });
                return ExpectLines(got, "[SEATLOG] drift slot=1 log=1:0:A body=2");
            });
            // An unbound sink drops the line; a throwing sink never reaches
            // the caller.
            Add("t6_sink_safe", () =>
            {
                DeckOf(1, "Barrage", "Leech");
                SeatDeckLog.Ladder = null;
                var a = R.ApplyGrant("g-7", "g-7", 1, 2, "Shield");
                SeatDeckLog.Ladder = l => { throw new InvalidOperationException("sink"); };
                var b = R.ApplyGrant("g-7", "g-7", 1, 3, "Bomb");
                SeatDeckLog.Ladder = null;
                return All(Expect("unbound", a, R.GrantOutcome.Applied), Expect("throwing", b, R.GrantOutcome.Applied));
            });
            // T1.6, T2.9 and T3.9: no ladder line. Each fixture still passes
            // under the sink; the T3.9 nothing-shown answers emit nothing; the
            // live answer of t39_nothing_shown is the in-case control that the
            // sink was live (exactly one offered line).
            Add("t6_negative", () =>
            {
                foreach (var name in new[] { "t16_unpinned_today", "t29_unbound_transport", "t29_old_box_404" })
                {
                    string why = null;
                    var got = Capture(() => why = Cases[name]());
                    if (why != null) return name + " failed under the sink: " + why;
                    var hit = got.Where(IsLadder).ToList();
                    if (hit.Count > 0) return name + " emitted " + Lines(hit);
                }
                var none = Capture(() =>
                {
                    N.MineAnswer a, b;
                    N.TryParseMine(200, "{\"readmissible\":0}", out a);
                    N.TryParseMine(404, "{\"detail\":\"Not Found\"}", out b);
                    R.DiscoveryShows(a);
                    R.DiscoveryShows(b);
                });
                if (none.Where(IsLadder).Any()) return "T3.9 nothing shown emitted " + Lines(none);
                string w39 = null;
                var control = Capture(() => w39 = Cases["t39_nothing_shown"]());
                return All(Expect("t39", w39, null), ExpectLines(control, "[HOLD] offered mode=team slot=1"));
            });
        }
    }
}
