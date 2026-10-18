using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;

    internal static partial class Program
    {
        // ── KX3: admission (V3 S3 steps 4 and 5) ─────────────────────────────

        /// <summary>The roster a freeze writes, as RoomActors.FreezeFighterRoster
        /// is fed from GameStateWatcher.GatedFreezeIds: the lock-roster feeder
        /// in a flagged room, else the present fighters (today).</summary>
        private static HashSet<string> Freeze(string room, IEnumerable<string> present)
        {
            var ids = R.LockRoster(room, () => present) ?? present.ToList();
            return new HashSet<string>(ids, StringComparer.Ordinal);
        }

        /// <summary>RoomActors.IsUnauthorized's order for a non-spectator with
        /// a readable identity: off the frozen roster refused; the held-seat
        /// conjunct; then the duplicate rule (an earlier present actor with the
        /// same identity).</summary>
        private static bool Unauthorized(HashSet<string> roster, string room, string th, int actor, string uid,
                                         string heldUid, int heldSlot, IDictionary<int, string> present)
        {
            if (string.IsNullOrEmpty(uid) || !roster.Contains(uid)) return true;
            var held = R.HeldSeatUnauthorized(room, th, actor, uid, heldUid, heldSlot);
            if (held.HasValue) return held.Value;
            foreach (var kv in present) if (kv.Key < actor && kv.Value == uid) return true;
            return false;
        }

        private static void PinTeam(string room)
        {
            R.ClearPins();
            R.PinRoom(room, true, R.MODE_TEAM, "series-1", new[] { "1001", "1002", "1003", "1004" });
        }

        private static string BoundTh(char state, int slot, int bound)
        {
            return new R.HoldKey { HoldId = "h1", Slot = slot, Team = slot / 2, G = "g-8", State = state, Seq = 3, HoldS = 110, Writer = 1, BoundActor = bound }.Format();
        }

        private static void RegisterKX3()
        {
            // T3.5: a hold spanning game N to N+1. Seat 1002 left in game N;
            // the per-game freeze at game N+1 runs while it is away and reads
            // the pinned series roster, so the returner (actor 9, bound) is a
            // fighter at its return.
            Add("t35_span_games", () =>
            {
                PinTeam("team_ab12");
                var roster = Freeze("team_ab12", new[] { "1001", "1003", "1004" });
                var present = new Dictionary<int, string> { { 1, "1001" }, { 3, "1003" }, { 4, "1004" }, { 9, "1002" } };
                bool returner = Unauthorized(roster, "team_ab12", BoundTh('b', 1, 9), 9, "1002", "1002", 1, present);
                return All(Expect("roster size", roster.Count, 4), Expect("returner refused", returner, false));
            });
            // T3.5: a stranger present at the per-game freeze is not on the
            // roster and stays refused; a room not flagged freezes as today.
            Add("t35_stranger", () =>
            {
                PinTeam("team_ab12");
                var roster = Freeze("team_ab12", new[] { "1001", "1003", "1004", "1009" });
                var present = new Dictionary<int, string> { { 1, "1001" }, { 3, "1003" }, { 4, "1004" }, { 7, "1009" } };
                bool stranger = Unauthorized(roster, "team_ab12", BoundTh('o', 1, 0), 7, "1009", "1002", 1, present);
                var today = Freeze("team_other", new[] { "1001", "1009" });
                return All(Expect("stranger refused", stranger, true), Expect("stranger on roster", roster.Contains("1009"), false),
                           Expect("today", today.Count == 2 && today.Contains("1009"), true));
            });
            // T3.5 / S3 step 5: an actor whose identity was unreadable was
            // latched; the release runs once at the verified b (not at o or c,
            // not again at a second b read), and a second hold releases again.
            Add("t35_release_at_bind", () =>
            {
                string last = null;
                var o = BoundTh('o', 1, 0); var c = BoundTh('c', 1, 0); var b = BoundTh('b', 1, 9);
                R.HoldKey ko, kc, kb;
                R.TryParseHold(o, out ko); R.TryParseHold(c, out kc); R.TryParseHold(b, out kb);
                bool atO = R.ReleaseAtBind(ko, ref last), atC = R.ReleaseAtBind(kc, ref last);
                bool atB = R.ReleaseAtBind(kb, ref last), again = R.ReleaseAtBind(kb, ref last);
                R.HoldKey k2; R.TryParseHold(new R.HoldKey { HoldId = "h2", Slot = 2, Team = 1, G = "g-9", State = 'b', Seq = 3, HoldS = 110, Writer = 1, BoundActor = 11 }.Format(), out k2);
                bool second = R.ReleaseAtBind(k2, ref last);
                return All(Expect("o", atO, false), Expect("c", atC, false), Expect("b", atB, true),
                           Expect("again", again, false), Expect("second hold", second, true));
            });
            // T3.7 identity: in a flagged room an actor advertising the held
            // seat's identity is a fighter only if it is X. Before the bind
            // every such actor is refused; after it X passes and a second
            // actor with that identity is refused even once the old actor
            // left (the duplicate rule alone would admit it); another
            // identity is the rules of today.
            Add("tx3_held_seat_identity", () =>
            {
                PinTeam("team_ab12");
                var roster = Freeze("team_ab12", new[] { "1001", "1003", "1004" });
                var present = new Dictionary<int, string> { { 1, "1001" }, { 3, "1003" }, { 4, "1004" }, { 9, "1002" }, { 11, "1002" } };
                bool early = Unauthorized(roster, "team_ab12", BoundTh('c', 1, 0), 9, "1002", "1002", 1, present);
                bool x = Unauthorized(roster, "team_ab12", BoundTh('b', 1, 9), 9, "1002", "1002", 1, present);
                var noOld = new Dictionary<int, string> { { 1, "1001" }, { 3, "1003" }, { 4, "1004" }, { 11, "1002" } };
                bool impostor = Unauthorized(roster, "team_ab12", BoundTh('b', 1, 9), 11, "1002", "1002", 1, noOld);
                bool other = Unauthorized(roster, "team_ab12", BoundTh('b', 1, 9), 3, "1003", "1002", 1, present);
                bool? unflagged = R.HeldSeatUnauthorized("team_other", BoundTh('b', 1, 9), 11, "1002", "1002", 1);
                return All(Expect("before bind", early, true), Expect("X", x, false), Expect("impostor", impostor, true),
                           Expect("other identity", other, false), Expect("unflagged", unflagged.HasValue, false));
            });
        }
    }
}
