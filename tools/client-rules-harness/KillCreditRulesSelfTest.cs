using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>Ask 9 stage B round 1 (F1, F5): the kill-credit rules executed
    /// by the client harness as suite "killcredit". The two-source negative is
    /// the round's witness: an earlier frame's record by Alpha must not become
    /// the kill when Bravo's lethal hit was never simulated here; a wrong
    /// credit is red BY NAME in got=.</summary>
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

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            // A 2v2: Alpha + Bravo (team 0) against Charlie + Delta (team 1); the victim is Charlie.
            int[] actors2v2 = { ALPHA, BRAVO, CHARLIE, DELTA };
            int[] teams2v2 = { 0, 0, 1, 1 };
            int sole2v2 = SoleOpponent(actors2v2, teams2v2, CHARLIE, 1);
            // A 1v2: Alpha solo (team 0) against Bravo + Charlie (team 1); a null roster entry.
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
                  (c2 == ALPHA ? "WRONG: " + Name(ALPHA) + " credited for a frame-100 hit at a frame-105 death" : "frame 100 " + Name(c2))
                  + "; " + (c2b == ALPHA ? "WRONG: " + Name(ALPHA) + " credited for a finished same-frame hit" : "finished same-frame " + Name(c2b)));

            // 3. A same-frame record by a teammate (Bravo, team 1) or by the victim explains the
            //    death: nobody is credited and the sole-opponent rule is not reached.
            int c3a = Credit(0, true, 200, 200, true, BRAVO, 1, 1, sole1v2);
            int c3b = Credit(0, true, 200, 200, true, CHARLIE, 1, 1, sole1v2);
            Check(r, "credit: a same-frame record by a teammate or the victim credits nobody and does not fall through",
                  c3a == -1 && c3b == -1 && sole1v2 == ALPHA,
                  "teammate " + Name(c3a) + ", self " + Name(c3b) + ", sole opponent " + Name(sole1v2));

            // 4. A same-frame record without a source (a physics object, a bounce) is unattributed:
            //    the sole opponent for a 1v2 duo member's death, nobody in a 2v2.
            int c4a = Credit(0, true, 300, 300, true, -1, -1, 1, sole1v2);
            int c4b = Credit(0, true, 300, 300, true, -1, -1, 1, sole2v2);
            Check(r, "credit: a same-frame record without a source is unattributed: the sole opponent, or nobody",
                  c4a == ALPHA && c4b == -1, "1v2 " + Name(c4a) + ", 2v2 " + Name(c4b));

            // 5. No record at all: the sole opponent (a 1v1, the 1v2 duo's deaths), nobody facing two.
            int c5a = Credit(0, false, 0, 400, false, -1, -1, 1, sole1v1);
            int c5b = Credit(0, false, 0, 400, false, -1, -1, 1, sole1v2);
            int c5c = Credit(0, false, 0, 400, false, -1, -1, 1, sole2v2);
            int soleSolo = SoleOpponent(actors1v2, teams1v2, ALPHA, 0);   // the 1v2 solo faces two
            Check(r, "credit: no record at all credits the sole opponent (1v1, the 1v2 duo's deaths) and nobody facing two",
                  c5a == ALPHA && c5b == ALPHA && c5c == -1 && soleSolo == -1,
                  "1v1 " + Name(c5a) + ", 1v2 duo " + Name(c5b) + ", 2v2 " + Name(c5c) + ", the 1v2 solo's sole opponent " + Name(soleSolo));

            // 6. A boundary (kind 1) or own-bullet (kind 2) death credits nobody whatever the record.
            int c6a = Credit(1, true, 500, 500, true, ALPHA, 0, 1, sole1v1);
            int c6b = Credit(2, true, 500, 500, true, ALPHA, 0, 1, sole1v1);
            Check(r, "credit: a boundary or own-bullet death credits nobody whatever the record",
                  c6a == -1 && c6b == -1, "boundary " + Name(c6a) + ", own bullet " + Name(c6b));

            // 7. The sole opponent ignores the victim, negative actors and repeats of one actor;
            //    two distinct foes are nobody; a null roster is nobody.
            int s7 = SoleOpponent(new int[] { ALPHA, ALPHA, -1, BRAVO }, new int[] { 0, 0, 0, 1 }, BRAVO, 1);
            int s7b = SoleOpponent(new int[] { ALPHA, BRAVO, CHARLIE }, new int[] { 0, 1, 0 }, BRAVO, 1);
            Check(r, "credit: the sole opponent ignores the victim, negative actors and repeats of one actor",
                  s7 == ALPHA && s7b == -1 && SoleOpponent(null, null, BRAVO, 1) == -1,
                  "repeats " + Name(s7) + ", two foes " + Name(s7b));
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
