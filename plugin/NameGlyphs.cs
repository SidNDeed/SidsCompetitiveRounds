using System;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// The one sanitiser a player-authored name passes through before it
    /// reaches a TMP text element in the list panels (report 3, 2026-09-30:
    /// the Recent Ranked Series panel's page 1 rendered blank while it held a
    /// display name ending in U+13171, an Egyptian hieroglyph from the
    /// supplementary plane that neither the game font nor any runtime fallback
    /// carries; the whole page is one element, so the name took 50 rows with
    /// it). Kept free of Unity, TMP and BepInEx so it runs under a plain
    /// compiler: UnicodeFallback.SafeName hands it the live "can this code
    /// point render" answer, and tools/client-rules-harness EXECUTES the same
    /// rules against fixed answers (#391).
    ///
    /// Glyphs: a code point the font chain cannot render becomes FALLBACK, a
    /// visible ASCII '?' (the game font is Latin-only, learning #30, and the
    /// element's default Bold renders it cleanly, unlike the thin l, i or -);
    /// a surrogate half with no partner -- a pair cut by a truncation, or bad
    /// data -- becomes FALLBACK too; C0/C1 controls and the U+2028/U+2029
    /// separators flatten to a space (TMP treats them as line control, the
    /// FfaSafeRich rule). Safe adds the rich-text neutralisation the Home
    /// panel's names use: '&lt;' and '&gt;' become '[' and ']', so a name can
    /// never open or close a tag in a line built around it. Neither pass ever
    /// makes a string longer, so a caller's width budget still holds.
    ///
    /// No catalogue string lives here (not in the extractor's FILES list).
    /// </summary>
    internal static class NameGlyphs
    {
        internal const char FALLBACK = '?';

        /// <summary>The glyph pass alone (for callers with their own tag
        /// escaping, FfaSafeRich).</summary>
        internal static string Glyphs(string s, Func<int, bool> renderable)
        {
            return Pass(s, renderable, false);
        }

        /// <summary>The glyph pass plus the rich-text neutralisation.</summary>
        internal static string Safe(string s, Func<int, bool> renderable)
        {
            return Pass(s, renderable, true);
        }

        private static string Pass(string s, Func<int, bool> renderable, bool tags)
        {
            if (string.IsNullOrEmpty(s)) return "";
            StringBuilder sb = null;
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                string put = null;
                int width = 1;
                if (char.IsHighSurrogate(c) && i + 1 < s.Length && char.IsLowSurrogate(s[i + 1]))
                {
                    width = 2;
                    int cp = char.ConvertToUtf32(c, s[i + 1]);
                    if (!Renders(renderable, cp)) put = "?";
                }
                else if (char.IsSurrogate(c)) put = "?";
                else if (c < ' ' || (c >= (char)0x7F && c <= (char)0x9F) || c == (char)0x2028 || c == (char)0x2029) put = " ";
                else if (tags && c == '<') put = "[";
                else if (tags && c == '>') put = "]";
                else if (c >= (char)0x80 && !Renders(renderable, c)) put = "?";
                if (put == null)
                {
                    if (sb != null) sb.Append(s, i, width);
                }
                else
                {
                    if (sb == null) { sb = new StringBuilder(s.Length); sb.Append(s, 0, i); }
                    sb.Append(put);
                }
                i += width - 1;
            }
            return sb == null ? s : sb.ToString();
        }

        private static bool Renders(Func<int, bool> renderable, int cp)
        {
            try { return renderable != null && renderable(cp); }
            catch { return false; }
        }

        // -- self-test (EXECUTED by tools/client-rules-harness) --------------

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        /// <summary>The name as the panels passed it before report 3: raw.
        /// Kept as the NEGATIVE CONTROL for the glyph cases -- the measurement
        /// that shows they can fail is that this path fails them (#391). Never
        /// called by anything that paints.</summary>
        private static string Raw(string s) { return s ?? ""; }

        /// <summary>One UTF-16 unit as a string (the cases build every non-ASCII
        /// character this way, so the source stays ASCII).</summary>
        private static string C(int unit) { return ((char)unit).ToString(); }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            // The font chain as the harness models it: ASCII, Latin-1, Cyrillic
            // and one mathematical letter the symbol fallback carries (U+1D544,
            // round-2 item 5's name); nothing else.
            Func<int, bool> chain = cp => cp < 0x80 || (cp >= 0xA0 && cp <= 0x17F) || (cp >= 0x400 && cp <= 0x4FF) || cp == 0x1D544;

            string hiero = "Ra" + char.ConvertFromUtf32(0x13171);
            string emoji = char.ConvertFromUtf32(0x1F600) + "x";
            string math = char.ConvertFromUtf32(0x1D544) + "ax";
            Check(r, "U+13171 (Egyptian hieroglyph, supplementary plane) becomes the fallback",
                  Safe(hiero, chain) == "Ra?", Dump(Safe(hiero, chain)));
            Check(r, "a supplementary-plane emoji (U+1F600) becomes the fallback",
                  Safe(emoji, chain) == "?x", Dump(Safe(emoji, chain)));
            Check(r, "a supplementary-plane letter the chain carries is kept whole",
                  Safe(math, chain) == math, Dump(Safe(math, chain)));
            string ring = C(0x25EF);                              // U+25EF, a basic-plane glyph the chain lacks
            Check(r, "a basic-plane glyph the chain lacks (U+25EF) becomes the fallback",
                  Safe("a" + ring + "b", chain) == "a?b", Dump(Safe("a" + ring + "b", chain)));
            string latin = "Jos" + C(0xE9) + " " + C(0x418) + C(0x432) + C(0x430) + C(0x43D);
            Check(r, "accented Latin and Cyrillic the chain carries are kept",
                  Safe(latin, chain) == latin, Dump(Safe(latin, chain)));
            string cut = hiero.Substring(0, hiero.Length - 1);   // the pair cut by a truncation
            Check(r, "a pair cut by a truncation (lone high surrogate) becomes the fallback",
                  Safe(cut, chain) == "Ra?", Dump(Safe(cut, chain)));
            string low = "a" + C(0xDD71) + "b";
            Check(r, "a lone low surrogate becomes the fallback",
                  Safe(low, chain) == "a?b", Dump(Safe(low, chain)));
            string ctl = "a" + C(0x0A) + "b" + C(0x85) + "c" + C(0x2028) + "d" + C(0x09) + "e";
            Check(r, "controls and the line separators flatten to a space",
                  Safe(ctl, chain) == "a b c d e", Dump(Safe(ctl, chain)));
            Check(r, "a rich-text opener cannot open a tag",
                  Safe("<alpha=#00>Kev</b>", chain) == "[alpha=#00]Kev[/b]", Dump(Safe("<alpha=#00>Kev</b>", chain)));
            Check(r, "the glyph pass alone leaves tag characters to its caller",
                  Glyphs("<b>" + hiero, chain) == "<b>Ra?", Dump(Glyphs("<b>" + hiero, chain)));
            Check(r, "an ASCII name is returned unchanged",
                  Safe("Player 1 [TAG]", chain) == "Player 1 [TAG]", Safe("Player 1 [TAG]", chain));
            Check(r, "null and empty become empty", Safe(null, chain) == "" && Safe("", chain) == "", "ok");
            Check(r, "a throwing font answer counts as not renderable",
                  Safe("a" + C(0xE9), cp => { throw new InvalidOperationException(); }) == "a?", "a?");
            Check(r, "the fallback is visible ASCII and not a thin letter",
                  FALLBACK < 0x80 && FALLBACK > ' ' && "li-.,'|:;!".IndexOf(FALLBACK) < 0, FALLBACK.ToString());

            // Property over a mixed corpus: never longer, no surrogate half left
            // alone, no code point the chain cannot render, no '<'.
            string[] corpus = { hiero, emoji, math, cut, low, "<b>x", latin, ring + ring, "abc" + hiero + "def" + emoji };
            bool ok = true; string bad = "";
            foreach (string s in corpus)
            {
                string o = Safe(s, chain);
                if (o.Length > s.Length || o.IndexOf('<') >= 0 || !AllRender(o, chain)) { ok = false; bad = Dump(s) + " -> " + Dump(o); break; }
            }
            Check(r, "never longer, and every code point left renders", ok, ok ? corpus.Length + " inputs" : bad);

            // Negative control: the raw path keeps U+13171 and the emoji, so the
            // two glyph cases above are real gates.
            Check(r, "the raw name keeps the unrenderable code points (control)",
                  !AllRender(Raw(hiero), chain) && !AllRender(Raw(emoji), chain) && AllRender(Safe(hiero, chain), chain),
                  Dump(Raw(hiero)));
            return r;
        }

        private static bool AllRender(string s, Func<int, bool> renderable)
        {
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (char.IsHighSurrogate(c) && i + 1 < s.Length && char.IsLowSurrogate(s[i + 1]))
                {
                    if (!renderable(char.ConvertToUtf32(c, s[i + 1]))) return false;
                    i++;
                }
                else if (char.IsSurrogate(c) || !renderable(c)) return false;
            }
            return true;
        }

        private static string Dump(string s)
        {
            if (s == null) return "(null)";
            var sb = new StringBuilder();
            foreach (char c in s)
            {
                if (c >= ' ' && c < 0x7F) sb.Append(c);
                else sb.Append("\\u").Append(((int)c).ToString("X4"));
            }
            return sb.ToString();
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
