using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>Ask 9 stage B (migration 403): the reporter's own observation
    /// of every seat's combat facts in one place, keyed by Photon actor number,
    /// for the 2v2, 1v2 and FFA reports. Each client keeps one; only the
    /// elected reporter uploads it, inside the per-seat telemetry blobs.
    ///
    /// Sources: HealthHandler.RPCA_Die (every client simulates every death,
    /// CombatTelemetry.DeathClassifierPatch) for deaths, death marks and kill
    /// credit; CharacterStatModifiers.DealtDamage (runs on every client for
    /// every dealer, #127/#130) for foe damage. A kill is a kind-0 death
    /// credited to the FRESH damager of another team; a boundary or own-bullet
    /// death credits nobody, which is the server's 1v1 convention
    /// (_report_1v1_kills), so `kills` reads the same in every mode.
    ///
    /// The cumulative kills series rides the 3 s telemetry tick with the other
    /// seat series (one x-axis, #318 decimation); the death marks are seconds
    /// since match start on the point markers' clock. Per game: Reset() at both
    /// game-start hooks. Null = not recorded (#257): a seat with no entry
    /// sends nothing.</summary>
    internal static class CombatLedger
    {
        private sealed class Seat
        {
            public int Kills, Deaths;
            public float DamageDealt;
            public readonly List<int> DeathTimes = new List<int>();
            public readonly DecimatedList<int> KillTimeline = new DecimatedList<int>();
        }

        private const int DEATH_MARKS_CAP = 64;   // the point markers' cap
        private static readonly Dictionary<int, Seat> seats = new Dictionary<int, Seat>();

        internal static void Reset()
        {
            try { seats.Clear(); } catch { }
        }

        private static Seat SeatFor(int actor)
        {
            Seat s;
            if (!seats.TryGetValue(actor, out s)) { s = new Seat(); seats[actor] = s; }
            return s;
        }

        /// <summary>A death this client simulated. killerActor is the fresh
        /// foe damager of a kind-0 death, else -1 (nobody's kill).</summary>
        internal static void RecordDeath(int victimActor, int killerActor)
        {
            try
            {
                if (victimActor < 0) return;
                var v = SeatFor(victimActor);
                v.Deaths++;
                if (v.DeathTimes.Count < DEATH_MARKS_CAP)
                    v.DeathTimes.Add(GameStateWatcher.SecondsSinceMatchStart());
                if (killerActor >= 0 && killerActor != victimActor) SeatFor(killerActor).Kills++;
            }
            catch { }
        }

        /// <summary>Foe damage a dealer landed (the caller applies the
        /// same-team gate). Same sanity clamp as the local tracker.</summary>
        internal static void RecordDamage(int dealerActor, float dmg)
        {
            try
            {
                if (dealerActor < 0 || dmg <= 0f || float.IsNaN(dmg) || float.IsInfinity(dmg)) return;
                if (dmg > 100000f) dmg = 100000f;
                SeatFor(dealerActor).DamageDealt += dmg;
            }
            catch { }
        }

        /// <summary>One cumulative kills sample per present player on the 3 s
        /// tick. Every player in the room samples from the first tick, so the
        /// series share one x-axis whatever the kill order.</summary>
        internal static void Sample()
        {
            try
            {
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return;
                for (int i = 0; i < pm.players.Count; i++)
                {
                    var p = pm.players[i];
                    if (p == null || p.data == null || p.data.view == null) continue;
                    var s = SeatFor(p.data.view.OwnerActorNr);
                    s.KillTimeline.Add(s.Kills);
                }
            }
            catch { }
        }

        /// <summary>Copy a seat's facts onto its telemetry blob. deathsOnly for
        /// FFA, whose kills are the signed FfaMode tally and whose damage rides
        /// at entry level. False when the seat has no entry (nothing sent).</summary>
        internal static bool Fill(int actor, ApiClient.TeamTelemetry t, bool deathsOnly = false)
        {
            try
            {
                Seat s;
                if (t == null || !seats.TryGetValue(actor, out s)) return false;
                t.deaths = s.Deaths;
                t.deathTimes = string.Join(",", s.DeathTimes);
                if (deathsOnly) return true;
                t.damageDealt = (int)Math.Round(s.DamageDealt);
                t.kills = s.Kills;
                t.killTimeline = string.Join(",", s.KillTimeline.Items);
                return true;
            }
            catch { return false; }
        }
    }
}
