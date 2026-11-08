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
    /// credited by KillCreditRules (round 1 F1/F5): the damage record of the
    /// health-zero frame itself, else the victim's sole opponent, else nobody;
    /// a boundary or own-bullet death credits nobody, which is the server's
    /// 1v1 convention (_report_1v1_kills), so `kills` reads the same in every
    /// mode. A held seat's return moves its facts to the new actor (Rebind,
    /// round 1 F3); every seat samples every tick from the first, a seat
    /// created later backfilled to the shared origin (round 1 F4).
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
        private static int ticks;                 // samples taken since Reset: the shared origin

        internal static void Reset()
        {
            try { seats.Clear(); ticks = 0; } catch { }
        }

        private static Seat SeatFor(int actor)
        {
            Seat s;
            if (!seats.TryGetValue(actor, out s))
            {
                s = new Seat();
                // Round 1 F4: a seat first seen after the first tick (a late
                // Player object, a mid-game join) is backfilled with zeros, one
                // per tick already taken, so every series shares one origin and
                // one length and the loader never stretches a short one. The
                // decimation is by count (DecimatedList), so the backfill lands
                // on the same stride as the seats sampled from the start.
                for (int i = 0; i < ticks; i++) s.KillTimeline.Add(0);
                seats[actor] = s;
            }
            return s;
        }

        /// <summary>A held seat's return (TeamHoldLoop, state 'b'): the facts
        /// recorded under the seat's old Photon actor move to the actor that
        /// now holds it, merged with anything recorded under the new actor
        /// since it joined (round 1 F3: a return stranded the earlier kills,
        /// deaths and marks under an actor no builder reads).</summary>
        internal static void Rebind(int oldActor, int newActor)
        {
            try
            {
                Seat old;
                // Photon actors are positive; the hold key's "no actor" is 0.
                if (oldActor <= 0 || newActor <= 0 || oldActor == newActor || !seats.TryGetValue(oldActor, out old)) return;
                Seat cur;
                if (seats.TryGetValue(newActor, out cur) && !ReferenceEquals(cur, old))
                {
                    old.Kills += cur.Kills;
                    old.Deaths += cur.Deaths;
                    old.DamageDealt += cur.DamageDealt;
                    for (int i = 0; i < cur.DeathTimes.Count && old.DeathTimes.Count < DEATH_MARKS_CAP; i++) old.DeathTimes.Add(cur.DeathTimes[i]);
                    old.DeathTimes.Sort();
                }
                seats.Remove(oldActor);
                seats[newActor] = old;
            }
            catch { }
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

        /// <summary>One cumulative kills sample per SEAT on the 3 s tick: a
        /// seat for every present player first (a new one backfilled to the
        /// shared origin), then every seat samples, present or not, so the
        /// series share one x-axis and one length whatever the kill order and
        /// whenever a Player object appears or goes (round 1 F4).</summary>
        internal static void Sample()
        {
            try
            {
                var pm = PlayerManager.instance;
                if (pm != null && pm.players != null)
                    for (int i = 0; i < pm.players.Count; i++)
                    {
                        var p = pm.players[i];
                        if (p == null || p.data == null || p.data.view == null) continue;
                        SeatFor(p.data.view.OwnerActorNr);
                    }
                foreach (var kv in seats) kv.Value.KillTimeline.Add(kv.Value.Kills);
                ticks++;
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
