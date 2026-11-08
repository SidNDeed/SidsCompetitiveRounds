using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>Ask 9 stage B (Codex rounds 1 and 2): who a death credits, as pure
    /// rules the client harness executes (suite "killcredit").
    ///
    /// The game's death callback carries no source: HealthHandler.RPCA_Die
    /// takes only a direction (decompile HealthHandler.cs:366), and a client
    /// that receives the RPC after another replica crossed zero never simulates
    /// the lethal hit itself (DoDamage returns on `dead`, :269). So the credit
    /// is bound to the damage record THIS client wrote for the victim, compared
    /// for identity with the health-zero event: a lethal DoDamage sends
    /// RPCA_Die(All) from inside its own body (:294) and PUN runs an All RPC
    /// locally at once, so the lethal event's record is of the death's frame
    /// AND its DoDamage is still applying (ApplyingState) when the death
    /// callback runs. A record from an earlier frame, or of this frame but with
    /// its call already finished (a saw tick that did not kill, then a death
    /// another client sent in the same frame), is another event and credits
    /// nothing by itself - never a time window.
    ///
    /// An unattributed normal death (no applying same-frame record with a
    /// source: a hazard, a bounce, a hit this client never simulated) credits
    /// the victim's SOLE opponent only when the roster is exactly two fighters
    /// on two teams - the 1v1 shape, where this is the server's own 1v1 rule
    /// (every non-boundary, non-own-bullet death is the opponent's kill). With
    /// three or more fighters nobody is credited: a 1v2 duo member's death may
    /// be a teammate's (friendly fire is on by default) and a 2v2 remainder
    /// after a held departure is still a 2v2 (round 2 HIGH 2); the caller adds
    /// the room's format (a plain 1v1 room only). A same-frame applying record
    /// by a teammate or by the victim explains the death and credits nobody.</summary>
    internal static partial class KillCreditRules
    {
        /// <summary>The actor credited with an accepted death; -1 for nobody.
        /// kind: 0 normal, 1 out of bounds, 2 own bullet (those two credit
        /// nobody, the server's convention). The record is the victim's last
        /// damage record on this client (hasRecord false when none);
        /// recordApplying says its DoDamage is still running.</summary>
        internal static int Credit(int kind, bool hasRecord, int recordFrame, int deathFrame, bool recordApplying,
                                   int recordActor, int recordTeam, int victimTeam, int soleOpponentActor)
        {
            if (kind != 0) return -1;
            if (hasRecord && recordApplying && recordFrame == deathFrame && recordActor >= 0)
                return recordTeam != victimTeam ? recordActor : -1;
            return soleOpponentActor;
        }

        /// <summary>The victim's sole opponent: the one other fighter, on another
        /// team, when the roster is exactly two fighters with the victim among
        /// them; -1 otherwise. `actors` and `teams` are parallel; negative
        /// actors and repeats of one actor are not fighters.</summary>
        internal static int SoleOpponent(IList<int> actors, IList<int> teams, int victimActor, int victimTeam)
        {
            if (actors == null || teams == null) return -1;
            int n = Math.Min(actors.Count, teams.Count);
            int fighters = 0, foe = -1, foeTeam = -1;
            bool victimSeen = false;
            for (int i = 0; i < n; i++)
            {
                int a = actors[i];
                if (a < 0) continue;
                bool seen = false;
                for (int j = 0; j < i; j++) if (actors[j] == a) { seen = true; break; }
                if (seen) continue;
                fighters++;
                if (a == victimActor) victimSeen = true;
                else { foe = a; foeTeam = teams[i]; }
            }
            if (fighters != 2 || !victimSeen || foe < 0 || foeTeam == victimTeam) return -1;
            return foe;
        }

        /// <summary>Which views have a DoDamage call applying right now: a depth
        /// per view (a dealer's effects may nest a call for another view) and
        /// the frame it was entered in. A damage call never spans frames, so a
        /// depth still open from an earlier frame is a leak (a body that threw
        /// before its release) and is healed at the next Enter for that view;
        /// IsApplying is also false for it once the frame has moved on. The
        /// game pairs Enter with a Harmony finalizer's Exit, which runs whether
        /// or not the body throws (round 2 HIGH 1).</summary>
        internal sealed class ApplyingState
        {
            private struct Entry { public int Depth; public int Frame; }
            private readonly Dictionary<int, Entry> byView = new Dictionary<int, Entry>();

            internal void Enter(int view, int frame)
            {
                Entry e;
                if (byView.TryGetValue(view, out e) && e.Frame != frame) e.Depth = 0;
                e.Depth++;
                e.Frame = frame;
                byView[view] = e;
            }

            internal void Exit(int view)
            {
                Entry e;
                if (!byView.TryGetValue(view, out e)) return;
                if (e.Depth <= 1) byView.Remove(view);
                else { e.Depth--; byView[view] = e; }
            }

            internal bool IsApplying(int view, int frame)
            {
                Entry e;
                return byView.TryGetValue(view, out e) && e.Depth > 0 && e.Frame == frame;
            }

            internal void Clear() { byView.Clear(); }
        }
    }
}
