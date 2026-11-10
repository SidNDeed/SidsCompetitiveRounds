using System;
using System.Collections.Generic;
using System.Globalization;

namespace CompetitiveRounds
{
    /// <summary>The five cosmetic carriers a stats refresh keeps in step with
    /// the stats cache. The first four are written to the room (player
    /// properties, and the NickName for the nametag); the cursor is applied
    /// on this seat only.</summary>
    internal enum CosmeticCarrier
    {
        Trail = 0,
        Color = 1,
        Effect = 2,
        Nametag = 3,
        Cursor = 4,
    }

    /// <summary>
    /// Ask 3: what each cosmetic carrier last wrote, so that a stats refresh
    /// publishes exactly the carriers whose cached value differs from what was
    /// written, whichever route wrote it.
    ///
    /// The refresh used to publish every carrier when a signature of the cache
    /// changed, and it was the only writer that recorded that signature. The
    /// other routes (the room join, the queues' pre-join publishes, the shop
    /// equip, the spectator staging) wrote without recording. A route that
    /// published while the cache was empty therefore put "" in the room; the
    /// refetch that refilled the cache matched the recorded signature, and the
    /// carrier stayed empty for the rest of the room. The card-pick avatar then
    /// showed the team colour on every seat.
    ///
    /// Each carrier's own publisher records here after it writes, so every
    /// route records, a route added later included, and a clear of the
    /// carriers forgets them. Pure: no Unity, no Photon. The harness suite
    /// `cosmeticcarrier` executes it.
    /// </summary>
    internal sealed class CosmeticCarrierLedger
    {
        internal const int CarrierCount = 5;

        /// <summary>The plugin's one ledger. The harness builds its own.</summary>
        internal static readonly CosmeticCarrierLedger Shared = new CosmeticCarrierLedger();

        // null: nothing is known to be written (the start, or after a clear).
        private readonly string[] _written = new string[CarrierCount];

        /// <summary>The cursor is applied on this seat only; the other four
        /// are room carriers.</summary>
        internal static bool IsRoomCarrier(CosmeticCarrier c) => c != CosmeticCarrier.Cursor;

        /// <summary>Record the value a carrier's publisher has just written,
        /// an empty cache's "" included.</summary>
        internal void Wrote(CosmeticCarrier c, string value)
        {
            _written[Index(c)] = value ?? "";
        }

        /// <summary>The room carriers were removed (the spectator staging
        /// clears them), so nothing of theirs is known to be written.</summary>
        internal void ForgetRoomCarriers()
        {
            for (int i = 0; i < CarrierCount; i++)
                if (IsRoomCarrier((CosmeticCarrier)i)) _written[i] = null;
        }

        /// <summary>The value last written, or null when none is known.</summary>
        internal string Written(CosmeticCarrier c) => _written[Index(c)];

        /// <summary>Whether a refresh publishes this carrier: the cached value
        /// differs from the one last written, or none is known. A spectator
        /// owes no room carrier, because it publishes nothing to a watched
        /// room (design 3.5); its cursor is still owed.</summary>
        internal bool Owes(CosmeticCarrier c, string cachedValue, bool spectator)
        {
            if (spectator && IsRoomCarrier(c)) return false;
            string w = _written[Index(c)];
            return w == null || !string.Equals(w, cachedValue ?? "", StringComparison.Ordinal);
        }

        // -- each carrier's value: the cached fields its publisher writes ----

        internal static string TrailValue(string sku, string color, int price) =>
            Join(sku, color, price.ToString(CultureInfo.InvariantCulture));

        internal static string ColorValue(string sku, string hex) => Join(sku, hex);

        internal static string EffectValue(string sku) => sku ?? "";

        /// <summary>The nametag's value is its style list. Its base name is
        /// the Steam name, which the cache does not hold.</summary>
        internal static string NametagValue(IList<string> skus)
        {
            if (skus == null || skus.Count == 0) return "";
            var parts = new string[skus.Count];
            for (int i = 0; i < skus.Count; i++) parts[i] = skus[i];
            return Join(parts);
        }

        internal static string CursorValue(string sku, string hex) => Join(sku, hex);

        // The unit separator (U+001F): no sku, hex or price contains it, so
        // two different field lists never join to the same value.
        private const string Sep = "\u001f";

        private static string Join(params string[] parts)
        {
            var clean = new string[parts.Length];
            for (int i = 0; i < parts.Length; i++) clean[i] = parts[i] ?? "";
            return string.Join(Sep, clean);
        }

        private static int Index(CosmeticCarrier c)
        {
            int i = (int)c;
            if (i < 0 || i >= CarrierCount) throw new ArgumentOutOfRangeException(nameof(c));
            return i;
        }
    }

    /// <summary>Ask 3 (S2): whether a change of a player's colour property
    /// repaints the card-pick body on screen. The pick body reads the room
    /// property for every picker, the local one included, so it shows what the
    /// room shows. It used to read it once per Show, so a republish that landed
    /// while the popup was up never reached it.</summary>
    internal static class PickBodyRepaintRules
    {
        internal static bool ShouldRepaint(int shownActor, bool bodyAlive, bool firstPaintDone,
                                           int changedActor, bool colourKeyChanged)
        {
            if (!colourKeyChanged) return false;
            // Before the first paint there is nothing to repaint: the first
            // paint reads the newest value itself.
            if (!bodyAlive || !firstPaintDone) return false;
            return shownActor > 0 && changedActor == shownActor;
        }
    }
}
