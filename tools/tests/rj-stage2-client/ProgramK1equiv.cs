using System;
using System.Collections.Generic;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;

    internal static partial class Program
    {
        /// <summary>The census arm of the 2v2 leave callback as it stood at the
        /// base (B:plugin/Plugin.cs:5257-5326), transcribed statement for
        /// statement over plain values: the answer is the kind and the elected
        /// seat's id. The floor arm is DcReporterElection.ShouldReport itself.</summary>
        private static string BaseElection(long myVal, int myTeam, int dcTeam, long dcId, bool roomWide,
                                           IList<R.DcSurvivor> survivors, List<DcReporterElection.Peer> floor)
        {
            bool teamsKnown = dcTeam >= 0 && myTeam >= 0;
            bool unique = teamsKnown && survivors.Count == 3 && roomWide;
            long lowestNonDc = long.MaxValue;
            int nonDcCount = 0, dcTeamCount = 1;
            var seenIds = new HashSet<long>();
            bool sawSelf = false;
            if (unique)
            {
                if (dcId < 0) unique = false; else seenIds.Add(dcId);
            }
            if (unique)
            {
                for (int i = 0; i < survivors.Count; i++)
                {
                    var s = survivors[i];
                    long sid = s.Sid;
                    int st = s.Team;
                    if (sid < 0 || st < 0 || !seenIds.Add(sid)) { unique = false; break; }
                    if (s.Local) { sawSelf = true; if (sid != myVal) { unique = false; break; } }
                    if (st == dcTeam) dcTeamCount++;
                    else { nonDcCount++; if (sid < lowestNonDc) lowestNonDc = sid; }
                }
            }
            if (unique && (!sawSelf || dcTeamCount != 2 || nonDcCount != 2)) unique = false;
            if (unique)
            {
                if (myTeam == dcTeam) return "StandDown";
                if (myVal == lowestNonDc) return "Prompt";
                int elected = -1;
                for (int i = 0; i < survivors.Count; i++)
                    if (survivors[i].Sid == lowestNonDc) { elected = survivors[i].Actor; break; }
                return "Fallback@" + elected;
            }
            bool onFloor, consistentView;
            if (!DcReporterElection.ShouldReport(myVal, myTeam, dcTeam, floor, out onFloor, out _, out consistentView)) return "Nothing";
            return "Floor/" + onFloor + "/" + consistentView;
        }

        private static string Shown(R.DcResult d)
        {
            if (d.Kind == R.DcKind.Fallback) return "Fallback@" + d.ElectedActor;
            if (d.Kind == R.DcKind.Floor) return "Floor/" + d.OnFloor + "/" + d.ConsistentView;
            return d.Kind.ToString();
        }

        private static void RegisterK1Equiv()
        {
            // S1 step 7: the extracted election (TeamHoldRules.DecideDc) answers
            // what the base leave callback answered, over an enumerated space of
            // censuses: ids readable, duplicated or unreadable; teams readable or
            // not, 2/2 or not; this seat present, absent or mis-advertised; the
            // capability quorum true or false. Every disagreement is a FAIL.
            Add("t1_dc_equiv", () =>
            {
                long[] ids = { 1001, 1002, 1003, 1004, -1 };
                int[] teams = { 0, 1, -1 };
                int cases = 0;
                foreach (long me in new long[] { 1002, 1003, 1004 })
                foreach (int myTeam in teams)
                foreach (int dcTeam in teams)
                foreach (long dcId in new long[] { 1001, -1, 1002 })
                foreach (bool roomWide in new[] { true, false })
                for (int a = 0; a < ids.Length; a++)
                for (int ta = 0; ta < 2; ta++)
                for (int b = 0; b < ids.Length; b++)
                for (int tb = 0; tb < 3; tb++)
                for (int c = 0; c < ids.Length; c++)
                for (int tc = 0; tc < 2; tc++)
                {
                    var surv = new List<R.DcSurvivor>
                    {
                        new R.DcSurvivor(ids[a], teams[ta], ids[a] == me, 10 + a),
                        new R.DcSurvivor(ids[b], teams[tb], ids[b] == me && ids[a] != me, 20 + b),
                        new R.DcSurvivor(ids[c], teams[tc], false, 30 + c),
                    };
                    var floor = new List<DcReporterElection.Peer>();
                    foreach (var s in surv)
                        if (!s.Local) floor.Add(new DcReporterElection.Peer(s.Sid < 0 ? null : s.Sid.ToString(), s.Team));
                    string want = BaseElection(me, myTeam, dcTeam, dcId, roomWide, surv, floor);
                    string got = Shown(R.DecideDc(me, myTeam, dcTeam, dcId, roomWide, roomWide ? -1 : 30, surv, floor));
                    cases++;
                    if (want != got)
                        return "case " + cases + " (me " + me + " t" + myTeam + ", dc t" + dcTeam + " id " + dcId + ", wide " + roomWide
                               + "): base " + want + ", extracted " + got;
                }
                return cases > 10000 ? null : "only " + cases + " cases enumerated";
            });
        }
    }
}
