using System;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// The harness's half of CosmeticCarrierLedger and PickBodyRepaintRules
    /// (ask 3), suite `cosmeticcarrier`. It lives here, not in plugin/, so the
    /// shipped DLL carries no fixture. Every case prints its name and a
    /// measurement whatever its verdict. The skus are synthetic.
    /// </summary>
    internal static class CosmeticCarrierLedgerCases
    {
        internal sealed class Result
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private static readonly string TrailFull = CosmeticCarrierLedger.TrailValue("trail_comet", "#33CCFF", 1200);
        private static readonly string TrailEmpty = CosmeticCarrierLedger.TrailValue(null, null, 0);
        private static readonly string TrailOther = CosmeticCarrierLedger.TrailValue("trail_comet", "#FF3366", 1200);
        private static readonly string ColorFull = CosmeticCarrierLedger.ColorValue("pcolor_teal", "#2AB3A6");
        private static readonly string ColorEmpty = CosmeticCarrierLedger.ColorValue(null, null);
        private static readonly string ColorOther = CosmeticCarrierLedger.ColorValue("pcolor_rose", "#E0457B");
        private static readonly string EffectFull = CosmeticCarrierLedger.EffectValue("effect_embers");
        private static readonly string EffectEmpty = CosmeticCarrierLedger.EffectValue(null);
        private static readonly string EffectOther = CosmeticCarrierLedger.EffectValue("effect_frost");
        private static readonly string NametagFull = CosmeticCarrierLedger.NametagValue(new[] { "nametag_bold", "nametag_color_gold" });
        private static readonly string NametagEmpty = CosmeticCarrierLedger.NametagValue(null);
        private static readonly string NametagOther = CosmeticCarrierLedger.NametagValue(new[] { "nametag_bold" });
        private static readonly string CursorFull = CosmeticCarrierLedger.CursorValue("cursor_lime", "#B6FF3A");
        private static readonly string CursorEmpty = CosmeticCarrierLedger.CursorValue(null, null);
        private static readonly string CursorOther = CosmeticCarrierLedger.CursorValue("cursor_lime", "#FFFFFF");

        internal static Result SelfTest()
        {
            var res = new Result();
            const CosmeticCarrier T = CosmeticCarrier.Trail, C = CosmeticCarrier.Color, E = CosmeticCarrier.Effect,
                                  N = CosmeticCarrier.Nametag, K = CosmeticCarrier.Cursor;

            // -- the found sequence: a full write, a write from an empty cache, the refill --
            FoundSequence(res, "trail: a write from an empty cache, then the refill of the same value, is owed", T, TrailFull, TrailEmpty);
            FoundSequence(res, "color: a write from an empty cache, then the refill of the same value, is owed", C, ColorFull, ColorEmpty);
            FoundSequence(res, "effect: a write from an empty cache, then the refill of the same value, is owed", E, EffectFull, EffectEmpty);
            FoundSequence(res, "nametag: a write from an empty cache, then the refill of the same value, is owed", N, NametagFull, NametagEmpty);
            FoundSequence(res, "cursor: a write from an empty cache, then the refill of the same value, is owed", K, CursorFull, CursorEmpty);

            // -- the same refill after a full write owes nothing (no network blip) --
            SameRefill(res, "trail: the same value after a full write owes nothing", T, TrailFull);
            SameRefill(res, "color: the same value after a full write owes nothing", C, ColorFull);
            SameRefill(res, "effect: the same value after a full write owes nothing", E, EffectFull);
            SameRefill(res, "nametag: the same value after a full write owes nothing", N, NametagFull);
            SameRefill(res, "cursor: the same value after a full write owes nothing", K, CursorFull);

            // -- a changed value is owed --
            Changed(res, "trail: a changed value is owed", T, TrailFull, TrailOther);
            Changed(res, "color: a changed value is owed", C, ColorFull, ColorOther);
            Changed(res, "effect: a changed value is owed", E, EffectFull, EffectOther);
            Changed(res, "nametag: a changed value is owed", N, NametagFull, NametagOther);
            Changed(res, "cursor: a changed value is owed", K, CursorFull, CursorOther);

            // -- nothing written yet: the first refresh publishes every carrier --
            Fresh(res, "trail: nothing written yet is owed, an empty value included", T, TrailEmpty);
            Fresh(res, "color: nothing written yet is owed, an empty value included", C, ColorEmpty);
            Fresh(res, "effect: nothing written yet is owed, an empty value included", E, EffectEmpty);
            Fresh(res, "nametag: nothing written yet is owed, an empty value included", N, NametagEmpty);
            Fresh(res, "cursor: nothing written yet is owed, an empty value included", K, CursorEmpty);

            // -- a spectator owes no room carrier; its cursor is local and still owed --
            Spectator(res, "trail: a spectator owes nothing, written or not", T, TrailFull, TrailOther, false);
            Spectator(res, "color: a spectator owes nothing, written or not", C, ColorFull, ColorOther, false);
            Spectator(res, "effect: a spectator owes nothing, written or not", E, EffectFull, EffectOther, false);
            Spectator(res, "nametag: a spectator owes nothing, written or not", N, NametagFull, NametagOther, false);
            Spectator(res, "cursor: a spectator's cursor is local, so it is still owed", K, CursorFull, CursorOther, true);

            // -- an account switch --
            {
                var l = new CosmeticCarrierLedger();
                l.Wrote(C, ColorFull);    // account A's colour
                l.Wrote(C, ColorEmpty);   // the identity changes, the cache empties, a pre-join publishes ""
                bool owed = l.Owes(C, ColorFull, false);  // account B equips the same colour
                Check(res, "an account switch through an empty cache is owed, even when the new account's value equals the old one's",
                      owed, "owed=" + owed + " written=" + Show(l.Written(C)));
            }
            {
                var l = new CosmeticCarrierLedger();
                l.Wrote(C, ColorFull);    // account A's colour, and no write while the cache was empty
                bool owed = l.Owes(C, ColorFull, false);  // account B's equal value: the room already holds it
                Check(res, "an account switch with no write while empty owes nothing when the values are equal",
                      !owed, "owed=" + owed + " written=" + Show(l.Written(C)));
            }

            // -- a clear (the spectator staging) forgets the room carriers, not the cursor --
            {
                var l = new CosmeticCarrierLedger();
                l.Wrote(T, TrailFull); l.Wrote(C, ColorFull); l.Wrote(E, EffectFull); l.Wrote(N, NametagFull); l.Wrote(K, CursorFull);
                l.ForgetRoomCarriers();
                bool rooms = l.Owes(T, TrailFull, false) && l.Owes(C, ColorFull, false) && l.Owes(E, EffectFull, false) && l.Owes(N, NametagFull, false);
                bool cursor = l.Owes(K, CursorFull, false);
                Check(res, "a clear of the room carriers makes each one owed again, and leaves the cursor's record",
                      rooms && !cursor, "rooms owed=" + rooms + " cursor owed=" + cursor);
            }

            // -- the values: one string per field list, and no two lists collide --
            {
                bool a = TrailFull != CosmeticCarrierLedger.TrailValue("trail_comet", "#33CCFF", 1201);
                Check(res, "the trail's value changes with its price", a, "differs=" + a);
            }
            {
                bool a = CosmeticCarrierLedger.ColorValue("ab", "") != CosmeticCarrierLedger.ColorValue("a", "b");
                bool b = CosmeticCarrierLedger.NametagValue(new[] { "a,b" }) != CosmeticCarrierLedger.NametagValue(new[] { "a", "b" });
                Check(res, "two different field lists never join to the same value", a && b, "colour differs=" + a + " nametag differs=" + b);
            }
            {
                bool a = CosmeticCarrierLedger.ColorValue(null, null) == CosmeticCarrierLedger.ColorValue("", "");
                bool b = CosmeticCarrierLedger.NametagValue(null) == CosmeticCarrierLedger.NametagValue(new string[0]);
                Check(res, "a missing field reads as the empty string the publisher writes", a && b, "colour equal=" + a + " nametag equal=" + b);
            }

            // -- the defect's model: the old rule kept one signature, recorded by the refresh alone --
            {
                string sig = ColorFull;                    // refresh 1 publishes and records the signature
                // a room join publishes "" from the empty cache and records nothing
                bool oldPublishes = ColorFull != sig;      // the refill matches the signature
                var l = new CosmeticCarrierLedger();
                l.Wrote(C, ColorFull); l.Wrote(C, ColorEmpty);
                bool newPublishes = l.Owes(C, ColorFull, false);
                Check(res, "the old rule (only the refresh records) misses the found sequence, and the ledger does not",
                      !oldPublishes && newPublishes, "old publishes=" + oldPublishes + " ledger publishes=" + newPublishes);
            }

            // -- S2: a colour change repaints the pick body on screen --
            Repaint(res, "a colour change of the picker on screen repaints the pick body, whoever wrote it", 7, true, true, 7, true, true);
            Repaint(res, "another player's colour change does not repaint the pick body", 7, true, true, 8, true, false);
            Repaint(res, "a change with no colour key does not repaint the pick body", 7, true, true, 7, false, false);
            Repaint(res, "a change before the first paint does not repaint: the first paint reads the newest value", 7, true, false, 7, true, false);
            Repaint(res, "a change after the popup closed or moved on does not repaint", 7, false, true, 7, true, false);
            Repaint(res, "no picker on screen repaints nothing", -1, true, true, -1, true, false);

            // -- R1 (H2): the binding a Show starts, and a Show or a Hide ends --
            {
                var b = new PickBodyBinding();
                int g = b.BeginShow();
                bool bound = b.TryBind(g, 7);
                b.FirstPaintFinished(g);
                bool got = b.ShouldRepaint(true, 7, true);
                Check(res, "a Show's own coroutine binds its body, and after the first paint a colour change repaints it", bound && got, "bound=" + bound + " repaint=" + got);
            }
            {
                var b = new PickBodyBinding();
                b.BeginShow();
                bool got = b.ShouldRepaint(true, 7, true);
                Check(res, "a colour change while the Show's coroutine waits repaints nothing: nothing is bound yet", !got, "repaint=" + got);
            }
            {
                var b = new PickBodyBinding();
                int g1 = b.BeginShow();
                b.TryBind(g1, 7);
                b.FirstPaintFinished(g1);
                b.BeginShow();
                bool old = b.ShouldRepaint(true, 7, true);
                bool rebound = b.TryBind(g1, 7);
                Check(res, "a later Show unbinds the earlier body at once, and the earlier coroutine binds nothing", !old && !rebound, "old repaint=" + old + " old coroutine binds=" + rebound);
            }
            {
                var b = new PickBodyBinding();
                int g = b.BeginShow();
                b.TryBind(g, 7);
                b.FirstPaintFinished(g);
                b.Hide();
                bool got = b.ShouldRepaint(true, 7, true);
                Check(res, "a Hide unbinds the body, and a later colour change repaints nothing", !got, "repaint=" + got);
            }
            {
                var b = new PickBodyBinding();
                int g = b.BeginShow();
                b.Hide();
                bool binds = b.TryBind(g, 7);
                bool got = b.ShouldRepaint(true, 7, true);
                Check(res, "a coroutine still waiting when the popup is hidden binds nothing", !binds && !got, "binds=" + binds + " repaint=" + got);
            }
            {
                var b = new PickBodyBinding();
                int g1 = b.BeginShow();
                b.TryBind(g1, 7);
                int g2 = b.BeginShow();
                b.TryBind(g2, 8);
                b.FirstPaintFinished(g1);
                bool early = b.ShouldRepaint(true, 8, true);
                b.FirstPaintFinished(g2);
                bool late = b.ShouldRepaint(true, 8, true);
                Check(res, "a superseded Show's first paint marks nothing; the current one's does", !early && late, "after the old paint=" + early + " after its own=" + late);
            }
            {
                var b = new PickBodyBinding();
                int g = b.BeginShow();
                int none = b.BoundActor;
                b.TryBind(g, 7);
                int bound = b.BoundActor;
                b.BeginShow();
                int afterShow = b.BoundActor;
                int g2 = b.BeginShow();
                b.TryBind(g2, 9);
                b.Hide();
                int afterHide = b.BoundActor;
                Check(res, "the bound picker is the current binding's, and none after a Show or a Hide", none == -1 && bound == 7 && afterShow == -1 && afterHide == -1,
                      "before=" + none + " bound=" + bound + " after Show=" + afterShow + " after Hide=" + afterHide);
            }

            // -- R2: negative inputs through the binding itself, after a bind and a first paint --
            {
                var b = new PickBodyBinding();
                int g = b.BeginShow();
                b.TryBind(g, 7);
                b.FirstPaintFinished(g);
                bool other = b.ShouldRepaint(true, 8, true);
                Check(res, "a bound, painted body does not repaint for another player's colour change", !other, "repaint=" + other);
            }
            {
                var b = new PickBodyBinding();
                int g = b.BeginShow();
                b.TryBind(g, 7);
                b.FirstPaintFinished(g);
                bool noKey = b.ShouldRepaint(true, 7, false);
                Check(res, "a bound, painted body does not repaint for a change with no colour key", !noKey, "repaint=" + noKey);
            }
            {
                var b = new PickBodyBinding();
                int g = b.BeginShow();
                b.TryBind(g, 7);
                b.FirstPaintFinished(g);
                bool gone = b.ShouldRepaint(false, 7, true);
                Check(res, "a bound, painted body that is gone does not repaint", !gone, "repaint=" + gone);
            }
            {
                var b = new PickBodyBinding();
                int g = b.BeginShow();
                b.TryBind(g, 7);
                bool early = b.ShouldRepaint(true, 7, true);
                Check(res, "a bound body before its first paint does not repaint", !early, "repaint=" + early);
            }

            // -- R2: one carrier forgotten --
            {
                var l = new CosmeticCarrierLedger();
                l.Wrote(CosmeticCarrier.Nametag, NametagFull);
                l.Wrote(CosmeticCarrier.Color, ColorFull);
                l.Forget(CosmeticCarrier.Nametag);
                bool owed = l.Owes(CosmeticCarrier.Nametag, NametagFull, false);
                bool kept = !l.Owes(CosmeticCarrier.Color, ColorFull, false);
                Check(res, "a forgotten carrier is owed though the cache equals its old record, and the others keep theirs", owed && kept, "nametag owed=" + owed + " colour kept=" + kept);
            }

            return res;
        }

        private static void FoundSequence(Result res, string name, CosmeticCarrier c, string full, string empty)
        {
            var l = new CosmeticCarrierLedger();
            l.Wrote(c, full);      // a refresh publishes the equipped value
            l.Wrote(c, empty);     // the cache empties, and a room join publishes from it
            bool owed = l.Owes(c, full, false);   // the refetch brings the same value back
            Check(res, name, owed, "owed=" + owed + " written=" + Show(l.Written(c)));
        }

        private static void SameRefill(Result res, string name, CosmeticCarrier c, string full)
        {
            var l = new CosmeticCarrierLedger();
            l.Wrote(c, full);
            bool owed = l.Owes(c, full, false);
            Check(res, name, !owed, "owed=" + owed);
        }

        private static void Changed(Result res, string name, CosmeticCarrier c, string full, string other)
        {
            var l = new CosmeticCarrierLedger();
            l.Wrote(c, full);
            bool owed = l.Owes(c, other, false);
            Check(res, name, owed, "owed=" + owed);
        }

        private static void Fresh(Result res, string name, CosmeticCarrier c, string empty)
        {
            var l = new CosmeticCarrierLedger();
            bool owed = l.Owes(c, empty, false);
            Check(res, name, owed && l.Written(c) == null, "owed=" + owed + " written=" + Show(l.Written(c)));
        }

        private static void Spectator(Result res, string name, CosmeticCarrier c, string full, string other, bool expectOwed)
        {
            var l = new CosmeticCarrierLedger();
            bool unwritten = l.Owes(c, full, true);
            l.Wrote(c, full);
            bool changed = l.Owes(c, other, true);
            bool ok = expectOwed ? (unwritten && changed) : (!unwritten && !changed);
            Check(res, name, ok, "unwritten owed=" + unwritten + " changed owed=" + changed);
        }

        private static void Repaint(Result res, string name, int shown, bool alive, bool painted, int changed, bool colourKey, bool expect)
        {
            bool got = PickBodyRepaintRules.ShouldRepaint(shown, alive, painted, changed, colourKey);
            Check(res, name, got == expect, "repaint=" + got);
        }

        private static string Show(string v) => v == null ? "(none)" : "'" + v.Replace(((char)0x1f).ToString(), "|") + "'";

        private static void Check(Result r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
