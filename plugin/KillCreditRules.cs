using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>Ask 9 stage B (Codex round 1 F1 and F5): who a death credits,
    /// as pure rules the client harness executes (suite "killcredit").
    ///
    /// The game's death callback carries no source: HealthHandler.RPCA_Die
    /// takes only a direction (decompile HealthHandler.cs:366), and a client
    /// that receives the RPC after another replica crossed zero never simulates
    /// the lethal hit itself (DoDamage returns on `dead`, :269). So the credit
    /// is bound to the damage record THIS client wrote for the victim, compared
    /// for identity with the health-zero event: a lethal DoDamage sends
    /// RPCA_Die(All) from inside its own body (:294) and PUN runs an All RPC
    /// locally at once, so the lethal event's record is of the death's frame
    /// AND its DoDamage is still applying when the death callback runs. A
    /// record from an earlier frame, or of this frame but with its call already
    /// finished (a saw tick that did not kill, then a death another client sent
    /// in the same frame), is another event and credits nothing by itself -
    /// never a time window (the 2 s one credited a bystander's earlier hit).
    ///
    /// An unattributed normal death (no same-frame record with a source: a
    /// hazard, a bounce, a hit this client never simulated) credits the
    /// victim's SOLE opponent, the only fighter on another team (a 1v1; the
    /// 1v2 duo's deaths go to the solo). That is the server's 1v1 rule (every
    /// non-boundary, non-own-bullet death is the opponent's kill) and stage
    /// A's 1v2 derivation, so `kills` reads the same whether the client sends
    /// it or the server derives it. Facing two or more fighters (2v2, the 1v2
    /// solo, FFA) nobody is credited. A same-frame record by a teammate or by
    /// the victim explains the death and credits nobody.</summary>
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

        /// <summary>The victim's sole opponent: the one actor on another team
        /// among the fighters, -1 when there are none or several. `actors` and
        /// `teams` are parallel; the victim, negative actors and repeats of one
        /// actor are skipped.</summary>
        internal static int SoleOpponent(IList<int> actors, IList<int> teams, int victimActor, int victimTeam)
        {
            if (actors == null || teams == null) return -1;
            int found = -1;
            int n = Math.Min(actors.Count, teams.Count);
            for (int i = 0; i < n; i++)
            {
                int a = actors[i];
                if (a < 0 || a == victimActor || teams[i] == victimTeam) continue;
                if (found >= 0 && found != a) return -1;
                found = a;
            }
            return found;
        }
    }
}
