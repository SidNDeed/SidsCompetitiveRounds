using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>The Player Cards label table (v22 §1.3).
    ///
    /// The identifiers are the source of truth on BOTH sides: this table and
    /// the server's `backend/api/assets/pc/catalogue.json` carry the same
    /// keys with the same English, and a test asserts the two sets are equal.
    ///
    /// Each entry is a literal contextual-translation call taking the
    /// identifier as its context, which is what makes the keys EXIST: the
    /// extractor harvests that shape into
    /// `tools/i18n_source.json`, `sync-keys` creates the client-namespace rows
    /// whose `msgctxt` is `english + U+0004 + identifier`, and the face route
    /// resolves its labels by exactly that composite. Without these call sites
    /// the server's query matched nothing and every card rendered in English
    /// whatever locale was asked for.
    ///
    /// Two identifiers may share their English text on purpose — `pc.foil` and
    /// `pc.foil_short` are both "FOIL", `pc.band.epic` and `pc.band_short.epic`
    /// both "EPIC" — and the composite is what keeps them separate rows, so a
    /// language can hold a long form and an abbreviation at once.
    ///
    /// GENERATED from catalogue.json; edit that and re-run the generator
    /// rather than retyping a string here.</summary>
    internal static class PcLabels
    {
        /// <summary>Identifier -> the English source string. The same pairs the
        /// `Tr` switch below passes to the contextual lookup.</summary>
        internal static readonly Dictionary<string, string> English = new Dictionary<string, string>
        {
            { "pc.band.common", "COMMON" },
            { "pc.band.uncommon", "UNCOMMON" },
            { "pc.band.rare", "RARE" },
            { "pc.band.epic", "EPIC" },
            { "pc.band.legendary", "LEGENDARY" },
            { "pc.band_short.common", "COM" },
            { "pc.band_short.uncommon", "UNC" },
            { "pc.band_short.rare", "RARE" },
            { "pc.band_short.epic", "EPIC" },
            { "pc.band_short.legendary", "LEG" },
            { "pc.foil", "FOIL" },
            { "pc.foil_short", "FOIL" },
            { "pc.signed", "SIGNED" },
            { "pc.stat.rank", "RANK" },
            { "pc.stat.rating", "RATING" },
            { "pc.stat.pool", "POOL" },
            { "pc.stat.board", "BOARD" },
            { "pc.stat.record", "RECORD" },
            { "pc.preview_footer", "PREVIEW · NOT A PRINT" },
            { "pc.unnamed", "Unnamed player" },
            { "pc.edition", "Edition" },
            { "pc.unranked", "Unranked" },
        };

        /// <summary>This label in the active locale, or the identifier itself
        /// for one this build does not know (a server that gained a label
        /// before the client did).</summary>
        internal static string Tr(string identifier)
        {
            switch (identifier)
            {
                case "pc.band.common": return I18n.TrC("pc.band.common", "COMMON");
                case "pc.band.uncommon": return I18n.TrC("pc.band.uncommon", "UNCOMMON");
                case "pc.band.rare": return I18n.TrC("pc.band.rare", "RARE");
                case "pc.band.epic": return I18n.TrC("pc.band.epic", "EPIC");
                case "pc.band.legendary": return I18n.TrC("pc.band.legendary", "LEGENDARY");
                case "pc.band_short.common": return I18n.TrC("pc.band_short.common", "COM");
                case "pc.band_short.uncommon": return I18n.TrC("pc.band_short.uncommon", "UNC");
                case "pc.band_short.rare": return I18n.TrC("pc.band_short.rare", "RARE");
                case "pc.band_short.epic": return I18n.TrC("pc.band_short.epic", "EPIC");
                case "pc.band_short.legendary": return I18n.TrC("pc.band_short.legendary", "LEG");
                case "pc.foil": return I18n.TrC("pc.foil", "FOIL");
                case "pc.foil_short": return I18n.TrC("pc.foil_short", "FOIL");
                case "pc.signed": return I18n.TrC("pc.signed", "SIGNED");
                case "pc.stat.rank": return I18n.TrC("pc.stat.rank", "RANK");
                case "pc.stat.rating": return I18n.TrC("pc.stat.rating", "RATING");
                case "pc.stat.pool": return I18n.TrC("pc.stat.pool", "POOL");
                case "pc.stat.board": return I18n.TrC("pc.stat.board", "BOARD");
                case "pc.stat.record": return I18n.TrC("pc.stat.record", "RECORD");
                case "pc.preview_footer": return I18n.TrC("pc.preview_footer", "PREVIEW · NOT A PRINT");
                case "pc.unnamed": return I18n.TrC("pc.unnamed", "Unnamed player");
                case "pc.edition": return I18n.TrC("pc.edition", "Edition");
                case "pc.unranked": return I18n.TrC("pc.unranked", "Unranked");
                default: return identifier;
            }
        }
    }
}
