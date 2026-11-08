using System.Globalization;

namespace CompetitiveRounds
{
    /// <summary>Ask 5 (2026-11-08, design ai-collab/seat-b/ASK5-DESIGN.md): the
    /// pure rules of the avatar-preset picker, executed by the client rules
    /// harness as suite "avatarpicker". The picker shows the eight character-
    /// creator face slots labelled 1-8 and lets the player nominate item 19's
    /// two defaults (the modded one and the vanilla one); it never changes the
    /// worn face. A tile's state, what a click on it does, and the geometry of
    /// a composed face live here, Unity-free; the UI (AvatarPresetPicker.cs)
    /// only reads the game and draws what these say.</summary>
    internal enum PickerRing { None, Gold, Blue, Both, Red }

    /// <summary>What a click on a tile's button does. Every Set/Clear reaches
    /// item 19's own setters (AvatarDefaults.SetModded / SetVanilla) and
    /// nothing else; Refused writes nothing.</summary>
    internal enum PickerAction { Refused, SetModded, ClearModded, SetVanilla, ClearVanilla }

    internal struct PickerTile
    {
        internal int Slot;
        internal string Label;          // "1".."8": players count presets from one
        internal bool Empty;            // the slot is absent or never authored (all-zero): no live button
        internal bool Dirty;            // authored, with an item an unmodded player cannot see
        internal bool IsModded;         // this slot is the modded choice
        internal bool IsVanilla;        // this slot is the vanilla choice
        internal PickerRing Ring;
        internal bool ModdedEnabled;
        internal bool VanillaEnabled;
    }

    internal static partial class AvatarPickerRules
    {
        /// <summary>The ask's "1-8": eight tiles always, whatever the live
        /// portrait count says (a slot past playerFaces renders empty).</summary>
        internal const int Tiles = 8;
        internal const int Columns = 4;
        /// <summary>World units across a tile when no live portrait calibrates
        /// it: vanilla's default eyes and mouth fit comfortably inside.</summary>
        internal const float FallbackSpan = 2.4f;

        /// <summary>The state of one tile from what the game says about the slot
        /// (present, authored, vanilla-clean) and the two current choices.
        /// Rings: the choices first (both, then gold, then blue), then red for a
        /// dirty slot nobody chose, so a stale choice stays visible as a choice
        /// and item 19's own toasts explain it. The vanilla button is live only
        /// on a clean, authored slot; the modded button on any authored slot.</summary>
        internal static PickerTile Tile(int slot, bool present, bool authored, bool clean, int moddedChoice, int vanillaChoice)
        {
            var t = new PickerTile();
            t.Slot = slot;
            t.Label = (slot + 1).ToString(CultureInfo.InvariantCulture);
            t.Empty = !present || !authored;
            t.Dirty = !t.Empty && !clean;
            t.IsModded = slot >= 0 && slot == moddedChoice;
            t.IsVanilla = slot >= 0 && slot == vanillaChoice;
            if (t.IsModded && t.IsVanilla) t.Ring = PickerRing.Both;
            else if (t.IsModded) t.Ring = PickerRing.Gold;
            else if (t.IsVanilla) t.Ring = PickerRing.Blue;
            else if (t.Dirty) t.Ring = PickerRing.Red;
            else t.Ring = PickerRing.None;
            t.ModdedEnabled = !t.Empty;
            t.VanillaEnabled = !t.Empty && clean;
            return t;
        }

        /// <summary>The Modded button: a fresh slot becomes the choice, the
        /// current choice is cleared (the button is a toggle), an empty slot is
        /// refused.</summary>
        internal static PickerAction ModdedClick(PickerTile t)
        {
            if (t.Empty) return PickerAction.Refused;
            return t.IsModded ? PickerAction.ClearModded : PickerAction.SetModded;
        }

        /// <summary>The Vanilla button: only a clean, authored slot can become
        /// the vanilla choice (the server-side rule item 19 enforces in
        /// SetVanilla as the second lock); the current choice is cleared.</summary>
        internal static PickerAction VanillaClick(PickerTile t)
        {
            if (t.Empty || t.Dirty) return PickerAction.Refused;
            return t.IsVanilla ? PickerAction.ClearVanilla : PickerAction.SetVanilla;
        }

        /// <summary>Tile pixels per world unit. A live main-menu portrait draws
        /// its sprites at scaleM portrait-units per world unit inside a BG of
        /// bgWidth portrait-units, so a tile of tileWidth pixels showing the same
        /// span is scaleM * tileWidth / bgWidth. Without a live portrait, the
        /// fallback.</summary>
        internal static float Calibration(float scaleM, float bgWidth, float tileWidth, float fallback)
        {
            if (scaleM > 0f && bgWidth > 0f && tileWidth > 0f) return scaleM * tileWidth / bgWidth;
            return fallback;
        }

        internal static float FallbackK(float tileWidth)
        {
            return tileWidth > 0f ? tileWidth / FallbackSpan : 0f;
        }

        /// <summary>Vanilla's SpawnItem, in UI terms: a part is drawn at
        /// item.scale * k of its world size and at (item.offset + faceOffset) * k
        /// from the face centre; a sprite whose pivot is not its centre is
        /// shifted so the pivot, not the rect centre, lands on that point (a
        /// SpriteRenderer places its pivot at the transform; an Image fills its
        /// rect).</summary>
        internal static void PartRect(float spriteW, float spriteH, float pivotFracX, float pivotFracY,
                                      float itemScale, float itemOffX, float itemOffY, float faceOffX, float faceOffY, float k,
                                      out float w, out float h, out float x, out float y)
        {
            w = spriteW * itemScale * k;
            h = spriteH * itemScale * k;
            x = (itemOffX + faceOffX) * k + (0.5f - pivotFracX) * w;
            y = (itemOffY + faceOffY) * k + (0.5f - pivotFracY) * h;
        }

        /// <summary>The write gate (Codex r1 H1). Item 19's three setters each
        /// evaluate edge E8, and E8 applies a face in an online room (the room's
        /// nominee) or while the player's own face is held in Home for a
        /// restoration; so the picker runs a setter only in a confirmed menu
        /// state with no restoration owed, read live at the click. Fail closed:
        /// an unreadable room state refuses.</summary>
        internal static bool WriteAllowed(bool inRoom, bool roomUnreadable, int heldHome)
        {
            return !inRoom && !roomUnreadable && heldHome < 0;
        }

        internal static int Row(int slot) { return slot / Columns; }
        internal static int Column(int slot) { return slot % Columns; }
    }
}
