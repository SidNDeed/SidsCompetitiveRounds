using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>Ask 9 stage B rounds 1 and 2: the kill-credit rules executed by
    /// the client harness as suite "killcredit". The witnesses the rounds asked
    /// for: the two-source negative (an earlier record by Alpha must not become
    /// the kill), the frame lock alone (an old-frame record still applying), and
    /// the exception-then-later-hit case (a depth left open heals at the next
    /// call). A wrong credit is red BY NAME in got=.</summary>
    internal static partial class KillCreditRules
    {
        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private const int ALPHA = 1, BRAVO = 2, CHARLIE = 3, DELTA = 4;   // Photon actors

        private static string Name(int actor)
        {
            if (actor == ALPHA) return "Alpha";
            if (actor == BRAVO) return "Bravo";
            if (actor == CHARLIE) return "Charlie";
            if (actor == DELTA) return "Delta";
            return actor < 0 ? "nobody" : "actor " + actor;
        }

        private static string Wrong(int got, int wrong, string what)
        {
            return got == wrong ? "WRONG: " + Name(wrong) + " credited " + what : Name(got);
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            // A 2v2: Alpha + Bravo (team 0) against Charlie + Delta (team 1); the victim is Charlie.
            int[] actors2v2 = { ALPHA, BRAVO, CHARLIE, DELTA };
            int[] teams2v2 = { 0, 0, 1, 1 };
            int sole2v2 = SoleOpponent(actors2v2, teams2v2, CHARLIE, 1);
            // A 1v2: Alpha solo (team 0) against Bravo + Charlie (team 1); a null roster entry; the victim is Charlie.
            int[] actors1v2 = { ALPHA, BRAVO, CHARLIE, -1 };
            int[] teams1v2 = { 0, 1, 1, -1 };
            int sole1v2 = SoleOpponent(actors1v2, teams1v2, CHARLIE, 1);
            // A 1v1: Alpha (team 0) against Bravo (team 1); the victim is Bravo.
            int[] actors1v1 = { ALPHA, BRAVO };
            int[] teams1v1 = { 0, 1 };
            int sole1v1 = SoleOpponent(actors1v1, teams1v1, BRAVO, 1);

            // 1. The health-zero frame's own foe record, its call still applying, is the kill.
            int c1 = Credit(0, true, 105, 105, true, BRAVO, 0, 1, sole2v2);
            Check(r, "credit: the health-zero frame's own foe record is the kill", c1 == BRAVO, Name(c1));

            // 2. Two sources: Alpha's hit in frame 100 is on record and finished; Bravo's saw
            //    killed Charlie on another replica and the death RPC arrives in frame 105, Bravo's
            //    hit never simulated here. Alpha is NOT the killer (a 2v2: nobody is). Nor is a
            //    same-frame record whose call has already returned (a saw tick that did not kill
            //    here, then the death another client sent in the same frame).
            int c2 = Credit(0, true, 100, 105, false, ALPHA, 0, 1, sole2v2);
            int c2b = Credit(0, true, 105, 105, false, ALPHA, 0, 1, sole2v2);
            Check(r, "credit: two sources - an earlier frame's record does not credit its author (the bystander stays unnamed)",
                  c2 == -1 && c2b == -1,
                  "frame 100 " + Wrong(c2, ALPHA, "for a frame-100 hit at a frame-105 death")
                  + "; finished same-frame " + Wrong(c2b, ALPHA, "for a finished same-frame hit"));

            // 3. The frame lock alone (round 2 LOW): a record of an earlier frame whose call is
            //    somehow still applying is not the lethal event either.
            int c3 = Credit(0, true, 100, 105, true, ALPHA, 0, 1, sole2v2);
            Check(r, "credit: an old-frame record still applying credits nobody (the frame lock alone)",
                  c3 == -1, Wrong(c3, ALPHA, "for a frame-100 record still applying at a frame-105 death"));

            // 4. A same-frame applying record by a teammate (Delta, team 1) or by the victim explains
            //    the death: nobody is credited, and in the 1v1 shape the victim's own hit does not
            //    fall through to the opponent.
            int c4a = Credit(0, true, 200, 200, true, DELTA, 1, 1, sole2v2);
            int c4b = Credit(0, true, 200, 200, true, CHARLIE, 1, 1, sole2v2);
            int c4c = Credit(0, true, 200, 200, true, BRAVO, 1, 1, sole1v1);
            Check(r, "credit: a same-frame record by a teammate or the victim credits nobody and does not fall through",
                  c4a == -1 && c4b == -1 && c4c == -1 && sole1v1 == ALPHA,
                  "teammate " + Name(c4a) + ", self " + Name(c4b) + ", 1v1 self " + Wrong(c4c, ALPHA, "for the victim's own hit"));

            // 5. A same-frame applying record without a source (a physics object, a bounce) is
            //    unattributed: the opponent in the 1v1 shape, nobody with three or more fighters.
            int c5a = Credit(0, true, 300, 300, true, -1, -1, 1, sole1v1);
            int c5b = Credit(0, true, 300, 300, true, -1, -1, 1, sole1v2);
            int c5c = Credit(0, true, 300, 300, true, -1, -1, 1, sole2v2);
            Check(r, "credit: a same-frame record without a source is unattributed: the 1v1 opponent, else nobody",
                  c5a == ALPHA && c5b == -1 && c5c == -1,
                  "1v1 " + Name(c5a) + ", 1v2 duo " + Wrong(c5b, ALPHA, "for a 1v2 duo member's unattributed death") + ", 2v2 " + Name(c5c));

            // 6. No record at all: the opponent in the 1v1 shape; nobody in a 1v2 (the duo member's
            //    death may be a teammate's under friendly fire) or a 2v2.
            //    The round-2 teamkill: duo Bravo's saw ticked Charlie here in frame 104 (the record,
            //    finished), Bravo's saw killed Charlie on another replica, the death arrives in frame
            //    105 - solo Alpha is NOT credited.
            int c6a = Credit(0, false, 0, 400, false, -1, -1, 1, sole1v1);
            int c6b = Credit(0, false, 0, 400, false, -1, -1, 1, sole1v2);
            int c6c = Credit(0, false, 0, 400, false, -1, -1, 1, sole2v2);
            int c6d = Credit(0, true, 104, 105, false, BRAVO, 1, 1, sole1v2);
            Check(r, "credit: no record at all credits the 1v1 opponent and nobody in a 1v2 or 2v2",
                  c6a == ALPHA && c6b == -1 && c6c == -1 && c6d == -1,
                  "1v1 " + Name(c6a) + ", 1v2 duo " + Wrong(c6b, ALPHA, "for a 1v2 duo member's death the solo may not have caused")
                  + ", 2v2 " + Name(c6c) + ", 1v2 teamkill by saw " + Wrong(c6d, ALPHA, "for a duo member's death that was the teammate's saw kill"));

            // 7. A boundary (kind 1) or own-bullet (kind 2) death credits nobody whatever the record.
            int c7a = Credit(1, true, 500, 500, true, ALPHA, 0, 1, sole1v1);
            int c7b = Credit(2, true, 500, 500, true, ALPHA, 0, 1, sole1v1);
            Check(r, "credit: a boundary or own-bullet death credits nobody whatever the record",
                  c7a == -1 && c7b == -1, "boundary " + Name(c7a) + ", own bullet " + Name(c7b));

            // 8. The sole opponent needs exactly two fighters on two teams with the victim among them;
            //    repeats and negative actors are not fighters; a 2v2 after one departure is three.
            int s8a = SoleOpponent(new int[] { ALPHA, ALPHA, -1, BRAVO }, new int[] { 0, 0, 0, 1 }, BRAVO, 1);
            int s8b = SoleOpponent(new int[] { ALPHA, BRAVO, CHARLIE }, new int[] { 0, 1, 0 }, BRAVO, 1);
            int s8c = SoleOpponent(new int[] { ALPHA, BRAVO, DELTA }, new int[] { 0, 0, 1 }, DELTA, 1);
            int s8d = SoleOpponent(new int[] { ALPHA, BRAVO, DELTA }, new int[] { 0, 0, 1 }, BRAVO, 0);
            int s8e = SoleOpponent(new int[] { ALPHA, CHARLIE }, new int[] { 0, 1 }, BRAVO, 1);
            int s8f = SoleOpponent(new int[] { ALPHA, BRAVO }, new int[] { 0, 0 }, BRAVO, 0);
            Check(r, "credit: the sole opponent needs exactly two fighters on two teams, the victim among them",
                  s8a == ALPHA && s8b == -1 && s8c == -1 && s8d == -1 && s8e == -1 && s8f == -1
                  && SoleOpponent(null, null, BRAVO, 1) == -1,
                  "repeats " + Name(s8a) + ", three fighters " + Name(s8b) + ", a 2v2 after one departure "
                  + Wrong(s8c, ALPHA, "as the lone fighter's sole opponent") + "/" + Wrong(s8d, DELTA, "as a duo member's sole opponent")
                  + ", victim absent " + Name(s8e) + ", one team " + Name(s8f));

            // 9. A call left open by an exception (no Exit) is still applying in its own frame (the
            //    game's finalizer closes that), heals at the next call in a later frame, and a death
            //    in that later frame after the call returned credits nobody.
            var st = new ApplyingState();
            st.Enter(7, 100);
            bool openSameFrame = st.IsApplying(7, 100);
            st.Enter(7, 105);
            bool duringLater = st.IsApplying(7, 105);
            st.Exit(7);
            bool afterLater = st.IsApplying(7, 105);
            int c9 = Credit(0, true, 105, 105, afterLater, ALPHA, 0, 1, sole2v2);
            Check(r, "applying: a call left open by an exception is healed at the next call in a later frame, and a death that frame credits nobody",
                  openSameFrame && duringLater && !afterLater && c9 == -1,
                  "open in its frame " + openSameFrame + ", during the later call " + duringLater + ", after it " + afterLater
                  + ", credit " + Wrong(c9, ALPHA, "after a leaked depth"));

            // 10. Nesting: a call for another view inside the victim's call does not end the victim's.
            var st2 = new ApplyingState();
            st2.Enter(7, 200);
            st2.Enter(8, 200);
            st2.Exit(8);
            bool victimStill = st2.IsApplying(7, 200);
            bool otherDone = st2.IsApplying(8, 200);
            st2.Exit(7);
            bool victimDone = st2.IsApplying(7, 200);
            Check(r, "applying: a nested call for another view keeps the victim's call applying until its own exit",
                  victimStill && !otherDone && !victimDone,
                  "victim during the nest " + victimStill + ", other after its exit " + otherDone + ", victim after its exit " + victimDone);

            // 11. A held 2v2 departure (round 2 HIGH 2's sibling): Charlie left; Alpha + Bravo (team 0)
            //     against Delta (team 1). Bravo's unattributed death does not credit Delta as a "sole"
            //     opponent, and Delta's does not credit either duo member: the remainder is a 2v2.
            int[] actorsHeld = { ALPHA, BRAVO, DELTA };
            int[] teamsHeld = { 0, 0, 1 };
            int c11a = Credit(0, false, 0, 600, false, -1, -1, 0, SoleOpponent(actorsHeld, teamsHeld, BRAVO, 0));
            int c11b = Credit(0, true, 600, 600, true, -1, -1, 1, SoleOpponent(actorsHeld, teamsHeld, DELTA, 1));
            Check(r, "credit: after a held 2v2 departure an unattributed death credits nobody (the remainder is still a 2v2)",
                  c11a == -1 && c11b == -1,
                  "duo member's death " + Wrong(c11a, DELTA, "as the remaining opponent after a held departure")
                  + ", lone fighter's death " + Wrong(c11b, ALPHA, "as a duo member") + "/" + Wrong(c11b, BRAVO, "as a duo member"));
            return r;
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
