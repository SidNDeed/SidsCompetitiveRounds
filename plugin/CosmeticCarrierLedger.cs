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

    /// <summary>Ask 3 R1 (H2): which pick body a paint may touch. A Show replaces
    /// the body and a Hide closes the popup, and each starts a new generation,
    /// so neither a Show's pending coroutine nor a property callback acts on a
    /// body that a later Show or a Hide superseded. Pure: the tinter keeps the
    /// body object, this keeps the decisions.</summary>
    internal sealed class PickBodyBinding
    {
        private int _generation;
        private int _boundGeneration = -1;
        private int _actor = -1;
        private bool _firstPaintDone;

        /// <summary>A Show: nothing is bound until this Show's own coroutine
        /// binds. Returns the Show's generation.</summary>
        internal int BeginShow()
        {
            unchecked { _generation++; }
            Unbind();
            return _generation;
        }

        /// <summary>A Hide: the popup shows no body, so nothing stays bound.</summary>
        internal void Hide()
        {
            unchecked { _generation++; }
            Unbind();
        }

        /// <summary>The Show's coroutine, after its wait: it binds only when no
        /// later Show or Hide came.</summary>
        internal bool TryBind(int generation, int actor)
        {
            if (generation != _generation) return false;
            _boundGeneration = generation;
            _actor = actor;
            _firstPaintDone = false;
            return true;
        }

        /// <summary>The bound body's first paint finished; a superseded Show's
        /// report changes nothing.</summary>
        internal void FirstPaintFinished(int generation)
        {
            if (generation == _generation && generation == _boundGeneration) _firstPaintDone = true;
        }

        /// <summary>The bound body's picker, or -1 when nothing is bound.</summary>
        internal int BoundActor => _boundGeneration == _generation ? _actor : -1;

        /// <summary>Whether a property change repaints the bound body.</summary>
        internal bool ShouldRepaint(bool bodyAlive, int changedActor, bool colourKeyChanged)
        {
            if (_boundGeneration != _generation) return false;
            return PickBodyRepaintRules.ShouldRepaint(_actor, bodyAlive, _firstPaintDone, changedActor, colourKeyChanged);
        }

        private void Unbind()
        {
            _boundGeneration = -1;
            _actor = -1;
            _firstPaintDone = false;
        }
    }
}
