using System;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>Ask 5: the avatar-preset picker's rules executed by the client
    /// harness as suite "avatarpicker". Every case prints its measurement in
    /// got=, so a wrong ring, a live button on a dead slot, a wrong action or a
    /// wrong rect is red by its value, not only by PASS/FAIL.</summary>
    internal static partial class AvatarPickerRules
    {
        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();

            // 1. Labels: players count presets from one.
            var labels = new StringBuilder();
            for (int s = 0; s < Tiles; s++)
            {
                var t = Tile(s, true, true, true, -1, -1);
                if (s > 0) labels.Append(',');
                labels.Append(t.Label);
            }
            Check(r, "tile: the eight labels count presets from one", labels.ToString() == "1,2,3,4,5,6,7,8", labels.ToString());

            // 2. Empty: absent or never authored.
            var absent = Tile(2, false, false, false, -1, -1);
            var unauthored = Tile(3, true, false, true, -1, -1);
            Check(r, "tile: an absent or never-authored slot is empty, wears no ring and has no live button",
                absent.Empty && unauthored.Empty
                && absent.Ring == PickerRing.None && unauthored.Ring == PickerRing.None
                && !absent.ModdedEnabled && !absent.VanillaEnabled && !unauthored.ModdedEnabled && !unauthored.VanillaEnabled,
                "absent empty=" + absent.Empty + " ring=" + absent.Ring + " buttons=" + absent.ModdedEnabled + "/" + absent.VanillaEnabled
                + "; unauthored empty=" + unauthored.Empty + " ring=" + unauthored.Ring + " buttons=" + unauthored.ModdedEnabled + "/" + unauthored.VanillaEnabled);

            // 3. Rings follow the two choices.
            var gold = Tile(0, true, true, true, 0, 5);
            var blue = Tile(5, true, true, true, 0, 5);
            var none = Tile(1, true, true, true, 0, 5);
            Check(r, "tile: the modded choice wears the gold ring, the vanilla choice the blue, the others none",
                gold.Ring == PickerRing.Gold && gold.IsModded && !gold.IsVanilla
                && blue.Ring == PickerRing.Blue && blue.IsVanilla && !blue.IsModded
                && none.Ring == PickerRing.None,
                "slot1=" + gold.Ring + " slot6=" + blue.Ring + " slot2=" + none.Ring);

            // 4. One slot, both choices.
            var both = Tile(4, true, true, true, 4, 4);
            Check(r, "tile: a slot that is both choices wears both rings",
                both.Ring == PickerRing.Both && both.IsModded && both.IsVanilla, "ring=" + both.Ring);

            // 5. A dirty slot: red ring, dead vanilla button, live modded button.
            var dirty = Tile(6, true, true, false, -1, -1);
            Check(r, "tile: a slot with items an unmodded player cannot see wears the red ring, its vanilla button dead and its modded button live",
                dirty.Dirty && !dirty.Empty && dirty.Ring == PickerRing.Red && !dirty.VanillaEnabled && dirty.ModdedEnabled,
                "dirty=" + dirty.Dirty + " ring=" + dirty.Ring + " vanilla=" + dirty.VanillaEnabled + " modded=" + dirty.ModdedEnabled);

            // 6. A dirty slot that is the modded choice: the choice ring wins, the vanilla button stays dead.
            var dirtyGold = Tile(6, true, true, false, 6, -1);
            Check(r, "tile: a dirty slot that is the modded choice keeps the gold ring over the red",
                dirtyGold.Ring == PickerRing.Gold && dirtyGold.Dirty && !dirtyGold.VanillaEnabled,
                "ring=" + dirtyGold.Ring + " vanilla=" + dirtyGold.VanillaEnabled);

            // 7. The Modded button.
            var fresh = Tile(1, true, true, true, 0, -1);
            var current = Tile(0, true, true, true, 0, -1);
            var emptyTile = Tile(7, true, false, true, 0, -1);
            var a1 = ModdedClick(fresh);
            var a2 = ModdedClick(current);
            var a3 = ModdedClick(emptyTile);
            Check(r, "click: modded on a fresh slot sets it, on the current choice clears it, on an empty slot is refused",
                a1 == PickerAction.SetModded && a2 == PickerAction.ClearModded && a3 == PickerAction.Refused,
                "fresh=" + a1 + " current=" + a2 + " empty=" + a3);

            // 8. The Vanilla button.
            var cleanFresh = Tile(2, true, true, true, -1, 5);
            var cleanCurrent = Tile(5, true, true, true, -1, 5);
            var dirtyTile = Tile(6, true, true, false, -1, 5);
            var b1 = VanillaClick(cleanFresh);
            var b2 = VanillaClick(cleanCurrent);
            var b3 = VanillaClick(dirtyTile);
            var b4 = VanillaClick(emptyTile);
            Check(r, "click: vanilla on a clean slot sets it, on the current choice clears it, on a dirty or empty slot is refused",
                b1 == PickerAction.SetVanilla && b2 == PickerAction.ClearVanilla && b3 == PickerAction.Refused && b4 == PickerAction.Refused,
                "clean=" + b1 + " current=" + b2 + " dirty=" + b3 + " empty=" + b4);

            // 9. Calibration.
            float k1 = Calibration(2.5f, 250f, 180f, 75f);
            float k2 = Calibration(0f, 250f, 180f, 75f);
            float k3 = Calibration(2.5f, 0f, 180f, 75f);
            float fb = FallbackK(180f);
            Check(r, "layout: calibration follows a live portrait's scale and background width, else the fallback",
                Near(k1, 1.8f) && Near(k2, 75f) && Near(k3, 75f) && Near(fb, 75f),
                "k=" + F(k1) + " noScale=" + F(k2) + " noBg=" + F(k3) + " fallback(180)=" + F(fb));

            // 10. A part's rect: vanilla's SpawnItem math with a centred pivot.
            float w, h, x, y;
            PartRect(1.2f, 0.8f, 0.5f, 0.5f, 0.5f, 0.1f, 0.2f, 0.3f, -0.1f, 100f, out w, out h, out x, out y);
            Check(r, "layout: a part's rect is vanilla's SpawnItem math, the face offset added to the item offset and everything scaled by k",
                Near(w, 60f) && Near(h, 40f) && Near(x, 40f) && Near(y, 10f),
                "w=" + F(w) + " h=" + F(h) + " x=" + F(x) + " y=" + F(y));

            // 11. A sprite pivoted at its bottom centre is lifted by half its height.
            float w2, h2, x2, y2;
            PartRect(1.0f, 1.0f, 0.5f, 0f, 1f, 0f, 0f, 0f, 0f, 100f, out w2, out h2, out x2, out y2);
            Check(r, "layout: a bottom-pivoted sprite is shifted so its pivot, not its centre, sits on the part's point",
                Near(w2, 100f) && Near(h2, 100f) && Near(x2, 0f) && Near(y2, 50f),
                "w=" + F(w2) + " h=" + F(h2) + " x=" + F(x2) + " y=" + F(y2));

            // 11b. A sprite pivoted at its left edge is shifted right by half its width.
            float w3, h3, x3, y3;
            PartRect(1.0f, 1.0f, 0f, 0.5f, 1f, 0f, 0f, 0f, 0f, 100f, out w3, out h3, out x3, out y3);
            Check(r, "layout: a left-pivoted sprite is shifted so its pivot, not its centre, sits on the part's point",
                Near(w3, 100f) && Near(h3, 100f) && Near(x3, 50f) && Near(y3, 0f),
                "w=" + F(w3) + " h=" + F(h3) + " x=" + F(x3) + " y=" + F(y3));

            // 12b. The write gate (H1).
            bool g1 = WriteAllowed(false, false, -1);
            bool g2 = WriteAllowed(true, false, -1);
            bool g3 = WriteAllowed(false, true, -1);
            bool g4 = WriteAllowed(false, false, 3);
            Check(r, "gate: a nomination runs only in a confirmed menu state with no restoration owed; a room, an unreadable room state or a held home face refuses",
                g1 && !g2 && !g3 && !g4,
                "menu=" + g1 + " room=" + g2 + " unreadable=" + g3 + " heldHome=" + g4);

            // 12. The grid.
            var grid = new StringBuilder();
            for (int s = 0; s < Tiles; s++)
            {
                if (s > 0) grid.Append(' ');
                grid.Append(Row(s)).Append(':').Append(Column(s));
            }
            Check(r, "layout: eight tiles fill four columns and two rows in slot order",
                grid.ToString() == "0:0 0:1 0:2 0:3 1:0 1:1 1:2 1:3", grid.ToString());

            return r;
        }

        private static bool Near(float a, float b)
        {
            return Math.Abs(a - b) < 0.0005f;
        }

        private static string F(float v)
        {
            return v.ToString("0.###", CultureInfo.InvariantCulture);
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
