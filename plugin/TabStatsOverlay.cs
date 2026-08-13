using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Hold-Tab live scoreboard (bug batch item 3) — a port of the old-ROUNDS
    /// TabInfo/Infoholic idea: one column per player showing their CURRENT
    /// build stats (all live per-frame reads off the game objects, nothing is
    /// accumulated) plus HP/lives and their card list.
    ///
    /// Design notes:
    ///  - IMGUI, drawn from CompetitiveUI.DrawUI — no uGUI, no EventSystem
    ///    interaction, safe during gameplay (matches the mod's overlay rules).
    ///  - HOLD to show (TabInfo toggled; hold can't get stuck open and matches
    ///    the scoreboard convention players already know).
    ///  - Hidden while the F5 menu or chat input is open, and force-hidden when
    ///    no players are spawned (main menu).
    ///  - Every stat read is defensive: a card that nulls a component renders
    ///    "-" for that cell instead of killing the whole board.
    /// </summary>
    internal static class TabStatsOverlay
    {
        private static GUIStyle stTitle, stName, stLabel, stCell, stCards;
        private static readonly List<Player> cachedPlayers = new List<Player>(4);
        private static readonly List<string> cachedNames = new List<string>(4);
        private static readonly List<CardRow> cachedCards = new List<CardRow>(4);
        private static readonly List<Color> cachedColors = new List<Color>(4);
        private static readonly List<string[]> cachedValues = new List<string[]>(4);
        private static readonly Dictionary<string, Texture2D> cardTextures =
            new Dictionary<string, Texture2D>(StringComparer.OrdinalIgnoreCase);
        private static readonly Dictionary<string, float> cardTexRetryAt =
            new Dictionary<string, float>(StringComparer.OrdinalIgnoreCase);
        // CardSnapshot generation this texture cache was filled under — a
        // locale switch (CardSnapshot.InvalidateAll) DESTROYS the native
        // sprites/textures these entries may point at, so a generation
        // change drops the whole cache instead of painting dead textures.
        private static int cardTexGeneration;
        private static int cachedPlayerCount;
        private static float nextSnapshotAt;
        private static bool cardLayoutDirty = true;
        private static float cachedCardLayoutWidth = -1f;
        private static float cachedCardsHeight = 24f;
        private static float cardSeparatorWidth;

        private const int MAX_SHOWN_CARDS = 8;
        private const int MAX_CARD_TOKENS = MAX_SHOWN_CARDS + 1;
        private static readonly GUIContent CARD_SEPARATOR = new GUIContent(", ");

        private sealed class CardDisplay
        {
            public string canonicalName;
            public readonly GUIContent content = new GUIContent();
        }

        private sealed class CardRow
        {
            public readonly CardDisplay[] cards = new CardDisplay[MAX_SHOWN_CARDS];
            public readonly GUIContent message = new GUIContent();
            public readonly GUIContent tail = new GUIContent();
            public readonly float[] nameWidths = new float[MAX_CARD_TOKENS];
            public readonly float[] tokenWidths = new float[MAX_CARD_TOKENS];
            public readonly float[] lineWidths = new float[MAX_CARD_TOKENS];
            public readonly float[] lineX = new float[MAX_CARD_TOKENS];
            public readonly float[] tokenX = new float[MAX_CARD_TOKENS];
            public readonly int[] tokenLines = new int[MAX_CARD_TOKENS];
            public int count, totalCount, visibleCount, lineCount;
            public bool hasTail;

            public CardRow()
            {
                for (int i = 0; i < cards.Length; i++) cards[i] = new CardDisplay();
            }
        }

        // Stat row description: label + the raw numeric read(s) + how the
        // overlay cell renders them.
        //
        // The NUMBERS are the single source of truth: the board renders them
        // through DisplayCell(), and the match-history capture (CaptureBuildStats
        // below) serializes the very same expressions. Before the capture
        // existed each row carried a pre-formatted string, so anything that
        // wanted the raw value had to re-derive it — which is exactly how the
        // two drift apart.
        //
        //   fmt/suffix reproduce the old inline interpolations byte-for-byte:
        //     "F0" + ""    -> "12"        (was $"{x:F0}")
        //     "F2" + "s"   -> "0.75s"     (was $"{x:F2}s")
        //     "F1" + "/s"  -> "1.5/s"     (was $"{x:F1}/s")
        //     number2 set  -> "45/100"    (was $"{a:F0}/{b:F0}")
        //   float.ToString(fmt) resolves the same CurrentCulture the old
        //   interpolated strings did, so the board's on-screen text is
        //   unchanged. The WIRE side formats invariantly instead (#47).
        private struct StatRow
        {
            public string label;
            public string fmt;                     // display numeric format
            public string suffix;                  // display-only unit — never on the wire
            public Func<Player, float> number;     // primary numeric read
            public Func<Player, float> number2;    // secondary read (HP row only), else null
            public StatRow(string l, string f, string sfx,
                           Func<Player, float> n, Func<Player, float> n2 = null)
            { label = l; fmt = f; suffix = sfx; number = n; number2 = n2; }
        }

        // ── WIRE FORMAT LOCK ────────────────────────────────────────────────
        // The order of this table IS the stored match-history build string (see
        // WIRE_V1 below). Inserting, removing or reordering an entry changes the
        // meaning of every build already persisted on the server, so any such
        // edit MUST bump BUILD_STATS_WIRE_VERSION and add a new WIRE_Vn table in
        // the same change — never mutate WIRE_V1, stored rows still decode from
        // it. WireTableValid() fails closed if the two stop lining up.
        private static readonly StatRow[] ROWS = new[]
        {
            // Clamp at 0 — a dead player's health goes negative internally
            // and "-39/100" on the board reads as a bug (July 28 screenshot).
            new StatRow("HP",          "F0", "",   p => Mathf.Max(0f, p.data.health), p => p.data.MaxHealth),
            new StatRow("Lives",       "F0", "",   p => p.data.stats.remainingRespawns + 1),
            // Infoholic's damage formula: gun.damage x bulletDamageMultiplier x 55
            // (55 = vanilla base bullet damage).
            new StatRow("Damage",      "F0", "",   p => Gun(p).damage * Gun(p).bulletDamageMultiplier * 55f),
            new StatRow("Attack spd",  "F2", "s",  p => Gun(p).attackSpeed * Gun(p).attackSpeedMultiplier),
            new StatRow("Reload",      "F2", "s",  p => { var ga = Ammo(p); return (ga.reloadTime + ga.reloadTimeAdd) * ga.reloadTimeMultiplier; }),
            new StatRow("Ammo",        "F0", "",   p => Ammo(p).maxAmmo),
            new StatRow("Bullets",     "F0", "",   p => Gun(p).numberOfProjectiles),
            new StatRow("Bursts",      "F0", "",   p => Gun(p).bursts),
            new StatRow("Bounces",     "F0", "",   p => Gun(p).reflects),
            new StatRow("Bullet spd",  "F2", "",   p => Gun(p).projectileSpeed),
            new StatRow("Bullet slow", "F2", "",   p => Gun(p).slow),
            new StatRow("Knockback",   "F2", "",   p => Gun(p).knockback),
            new StatRow("Spread",      "F2", "",   p => Gun(p).spread),
            new StatRow("Life steal",  "F2", "",   p => p.data.stats.lifeSteal),
            new StatRow("Block CD",    "F2", "s",  p => p.data.block.Cooldown()),
            new StatRow("Blocks",      "F0", "",   p => p.data.block.additionalBlocks + 1),
            new StatRow("Regen",       "F1", "/s", p => p.data.healthHandler.regeneration),
            new StatRow("Move spd",    "F2", "",   p => p.data.stats.movementSpeed),
            new StatRow("Jump",        "F2", "",   p => p.data.stats.jump),
            new StatRow("Jumps",       "F0", "",   p => p.data.stats.numberOfJumps),
            new StatRow("Size",        "F2", "",   p => p.data.stats.sizeMultiplier),
        };

        /// <summary>Renders one board cell from the row's numeric reader(s).
        /// Throws exactly where the old inline lambdas threw (a null gun, a
        /// missing GunAmmo) so RefreshSnapshot's per-row catch still yields
        /// "-" for that cell alone.</summary>
        private static string DisplayCell(StatRow row, Player p)
        {
            float a = row.number(p);
            if (row.number2 == null) return a.ToString(row.fmt) + row.suffix;
            return a.ToString(row.fmt) + "/" + row.number2(p).ToString(row.fmt) + row.suffix;
        }

        private static Gun Gun(Player p) => p.data.weaponHandler.gun;
        private static GunAmmo Ammo(Player p) => p.data.weaponHandler.gun.GetComponentInChildren<GunAmmo>(true);

        // ── L10n (Aug 3 completeness pass): this overlay is per-frame IMGUI, so
        // labels are translated ONCE into cached fields and re-resolved on
        // I18n.LocaleChanged — never per-frame (#162). Every literal sits INSIDE
        // its I18n.Tr call so the extractor harvests it as a key (Tr(variable)
        // harvests NOTHING — learning #295a). The label list below must stay in
        // LOCKSTEP with ROWS; on a length mismatch we fall back to the English
        // ROWS labels rather than mislabeling rows.
        private static string[] trLabels;
        private static string trTitle, trCardsLabel, trNoCards;
        private static bool localeHooked;
        private static int trGen = -1;

        private static void EnsureLocaleStrings()
        {
            /* Codex Aug-4 r2 find 8: keying the memo on the LOCALE alone was
             * not enough — a server pack can correct these strings WITHOUT the
             * locale changing, and this cached array would keep serving the
             * bundled wording for the rest of the session. I18n.CatalogueGeneration
             * moves on every effective data change (pack applied, cached pack
             * loaded, catalogue registered, locale set), so it is the honest key.
             * Kept as a cheap int compare because this runs on the hold-Tab
             * path, which must not allocate per frame (#162). */
            if (trLabels != null && trGen == I18n.CatalogueGeneration) return;
            trGen = I18n.CatalogueGeneration;
            if (!localeHooked)
            {
                localeHooked = true;
                try { I18n.LocaleChanged += () => { trLabels = null; }; } catch { }
            }
            trTitle = I18n.Tr("MATCH STATS  <color=#888><size=12>(hold Tab)</size></color>");
            trCardsLabel = I18n.Tr("Cards");
            trNoCards = I18n.Tr("<color=#666>no cards</color>");
            var labels = new[]
            {
                // "HP" stays English: a 2-letter token sits below the
                // extractor's key floor (looks_translatable) so it can never be
                // a catalogue key — and it is cross-locale gaming shorthand.
                "HP",
                I18n.Tr("Lives"), I18n.Tr("Damage"), I18n.Tr("Attack spd"),
                I18n.Tr("Reload"), I18n.Tr("Ammo"), I18n.Tr("Bullets"),
                I18n.Tr("Bursts"), I18n.Tr("Bounces"), I18n.Tr("Bullet spd"),
                I18n.Tr("Bullet slow"), I18n.Tr("Knockback"), I18n.Tr("Spread"),
                I18n.Tr("Life steal"), I18n.Tr("Block CD"), I18n.Tr("Blocks"),
                I18n.Tr("Regen"), I18n.Tr("Move spd"), I18n.Tr("Jump"),
                I18n.Tr("Jumps"), I18n.Tr("Size"),
            };
            if (labels.Length != ROWS.Length)
            {
                labels = new string[ROWS.Length];
                for (int i = 0; i < ROWS.Length; i++) labels[i] = ROWS[i].label;
            }
            trLabels = labels;
        }

        private static void EnsureLocaleStringsSafe()
        {
            // Decode runs off the match-history render path, outside Draw's
            // blanket catch — a locale/catalogue hiccup must degrade to the
            // English ROWS labels (LabelFor), never throw at the caller.
            try { EnsureLocaleStrings(); } catch { }
        }

        // ══ Build-stat capture (match-history "final build") ═════════════════
        //
        // WIRE FORMAT v1 — exactly 22 pipe-separated fields, positional:
        //   "1|hp|maxhp|dmg|aspd|reload|ammo|bullets|bursts|bounces|bspd|slow|
        //    knock|spread|lifesteal|blockcd|blocks|regen|movespd|jump|jumps|size"
        //
        //  - Leading "1" is the format version.
        //  - Every value is a plain decimal, InvariantCulture, <=7 integer
        //    digits and <=3 decimals, trailing zeros trimmed (#47 — a
        //    Russian/German client must not emit "1,25" into a field the server
        //    and every other client parse as a number). A value that could not
        //    be read, or that will not fit that shape, is the literal "-".
        //  - NO labels and NO localised text cross the wire. Rendering labels
        //    from the receiver's own catalogue keeps the payload injection-proof
        //    (nothing player- or locale-authored is stored) and lets an already
        //    stored build re-render in whatever language the viewer picks.
        //
        // WIRE_V1[] is the ONLY thing that maps a field position to a stat: each
        // entry names the ROWS[] index it reads and which half of that row
        // (second = the HP row's max). ROWS order therefore IS wire order, and
        // reordering ROWS without bumping the version silently relabels every
        // build already stored — hence WireTableValid()'s fail-closed check and
        // the WIRE FORMAT LOCK banner above ROWS.
        //
        // NOTE — the "Lives" row (ROWS[1]) is deliberately absent from v1: the
        // format was specified as 22 fields without it. To add it later:
        //   1. add a WIRE_V2 table = WIRE_V1 plus `new WireField(1, false, "lives")`,
        //   2. add WIRE_V2_TOKEN "2" and point BUILD_STATS_WIRE_VERSION at it,
        //   3. KEEP WIRE_V1 + its token in WireTableFor and give v2 its own
        //      row->field maps — every build already stored is a v1 row and has
        //      to keep rendering.
        private const string WIRE_V1_TOKEN = "1";
        /// <summary>Version token this build writes. One token per shipped
        /// format; capture and WireTableFor both read it, so they can never
        /// disagree about which table produced a string.</summary>
        public const string BUILD_STATS_WIRE_VERSION = WIRE_V1_TOKEN;
        private const string WIRE_MISSING = "-";
        // Hard per-field length bound, DERIVED FROM THE SERVER'S GRAMMAR —
        // do not widen one without the other (Codex cold review, finding 5).
        //
        // The server validates with an ANCHORED regex
        // (main.py _END_STATS_RE):  ^1(?:\|(?:-|-?\d{1,7}(?:\.\d{1,3})?)){21}$
        // so the widest legal numeric field is
        //     1 sign + 7 integer digits + 1 point + 3 decimals = 12 chars,
        // and the whole record is bounded at
        //     1 + 21 * (1 + WIRE_FIELD_MAX) = 274 chars,
        // comfortably under the server's 300-char column bound
        // (schemas.END_STATS_MAX_LEN). The two ends now agree by construction
        // rather than by coincidence.
        //
        // Both bounds fail CLOSED and fail SILENTLY on the far side, which is
        // why the client has to emit exactly the server's shape:
        //   * a record over 300 chars is dropped whole by ApiClient
        //     .AppendEndStats (the format is positional, so truncating would
        //     produce confidently mislabelled history);
        //   * a record with ONE over-wide field — 8 integer digits, say — does
        //     not fail that length check at all; the anchored regex simply
        //     refuses the whole string and the server stores NULL.
        // Either way the player gets no build recorded and nothing says why.
        // Clamping here costs one absurd stat one field ("-", which the
        // grammar already accepts) instead of costing the entire build.
        private const int WIRE_FIELD_MAX = 12;

        private struct WireField
        {
            public readonly int row;      // index into ROWS
            public readonly bool second;  // read StatRow.number2 instead of number
            public readonly string name;  // spec name — documentation only, never sent
            public WireField(int r, bool s, string n) { row = r; second = s; name = n; }
        }

        private static readonly WireField[] WIRE_V1 =
        {
            new WireField(0,  false, "hp"),        new WireField(0,  true,  "maxhp"),
            new WireField(2,  false, "dmg"),       new WireField(3,  false, "aspd"),
            new WireField(4,  false, "reload"),    new WireField(5,  false, "ammo"),
            new WireField(6,  false, "bullets"),   new WireField(7,  false, "bursts"),
            new WireField(8,  false, "bounces"),   new WireField(9,  false, "bspd"),
            new WireField(10, false, "slow"),      new WireField(11, false, "knock"),
            new WireField(12, false, "spread"),    new WireField(13, false, "lifesteal"),
            new WireField(14, false, "blockcd"),   new WireField(15, false, "blocks"),
            new WireField(16, false, "regen"),     new WireField(17, false, "movespd"),
            new WireField(18, false, "jump"),      new WireField(19, false, "jumps"),
            new WireField(20, false, "size"),
        };

        private static bool wireInit, wireValid;
        // ROWS index -> position in the split payload (0 is the version token),
        // -1 when this version does not carry that row. Built once from WIRE_V1
        // so decode never rescans the table per row.
        private static int[] wireFirstAt, wireSecondAt;

        /// <summary>Table self-check. A mismatch between WIRE and ROWS can only
        /// come from an edit that moved a row without bumping the version, and
        /// the wrong answer there is a mislabelled build in someone's history —
        /// so both capture and decode fail closed (no string / no rows).</summary>
        private static bool WireTableValid()
        {
            if (wireInit) return wireValid;
            wireInit = true;
            wireValid = false;
            try
            {
                var first = new int[ROWS.Length];
                var second = new int[ROWS.Length];
                for (int i = 0; i < ROWS.Length; i++) { first[i] = -1; second[i] = -1; }

                for (int i = 0; i < WIRE_V1.Length; i++)
                {
                    var f = WIRE_V1[i];
                    if (f.row < 0 || f.row >= ROWS.Length) { WireBreak("row index out of range at field " + i); return false; }
                    var reader = f.second ? ROWS[f.row].number2 : ROWS[f.row].number;
                    if (reader == null) { WireBreak("no reader for field " + i + " (" + f.name + ")"); return false; }
                    int at = i + 1;                       // +1 skips the version token
                    if (f.second)
                    {
                        if (second[f.row] >= 0) { WireBreak("duplicate second-half field for row " + f.row); return false; }
                        second[f.row] = at;
                    }
                    else
                    {
                        if (first[f.row] >= 0) { WireBreak("duplicate field for row " + f.row); return false; }
                        first[f.row] = at;
                    }
                }
                // A row may carry a second half only if it carries a first.
                for (int r = 0; r < ROWS.Length; r++)
                    if (second[r] >= 0 && first[r] < 0) { WireBreak("orphan second-half field for row " + r); return false; }

                wireFirstAt = first;
                wireSecondAt = second;
                wireValid = true;
            }
            catch { wireValid = false; }
            return wireValid;
        }

        private static void WireBreak(string why)
        {
            // Loud, once, into BepInEx's log (what bug-report bundles capture):
            // a silent no-op here would look exactly like "the server never got
            // the build" and cost a debugging session (#83).
            try { Plugin.Log?.LogWarning("[TABSTATS] build-stat wire table inconsistent (" + why + ") - capture disabled"); }
            catch { }
        }

        /// <summary>Exactly the server's numeric field shape:
        /// <c>-?\d{1,7}(\.\d{1,3})?</c> — the numeric half of _END_STATS_RE.
        /// A length test alone is NOT equivalent: "12345678901" is 11 chars
        /// (inside any sane length bound) and has 11 integer digits, which the
        /// anchored server regex rejects — taking the whole 22-field record
        /// with it. Hand-rolled rather than a Regex so it stays allocation-free
        /// on the game-over frame (#171 forbids delaying finalisation).</summary>
        private static bool WireFieldShapeOk(string s)
        {
            if (string.IsNullOrEmpty(s) || s.Length > WIRE_FIELD_MAX) return false;
            int i = 0;
            if (s[i] == '-') i++;
            int intDigits = 0;
            while (i < s.Length && s[i] >= '0' && s[i] <= '9') { i++; intDigits++; }
            if (intDigits < 1 || intDigits > 7) return false;
            if (i == s.Length) return true;
            if (s[i] != '.') return false;
            i++;
            int decDigits = 0;
            while (i < s.Length && s[i] >= '0' && s[i] <= '9') { i++; decDigits++; }
            if (decDigits < 1 || decDigits > 3) return false;
            return i == s.Length;
        }

        /// <summary>Invariant, at most 7 integer digits and 3 decimals,
        /// trailing zeros trimmed. Anything the server's grammar would refuse
        /// becomes the "-" unavailable token — which that grammar accepts — so
        /// one absurd stat costs one field rather than the whole build.
        /// The check is on the FORMATTED string, not the magnitude: rounding at
        /// the boundary (9999999.6 -> "10000000") crosses the 7-digit limit
        /// after formatting, so a pre-format bound would still emit a record
        /// the server NULLs.</summary>
        private static string WireNum(float v)
        {
            if (float.IsNaN(v) || float.IsInfinity(v)) return WIRE_MISSING;
            if (v == 0f) return "0";                       // also normalises -0
            // Custom numeric format strings never produce exponential notation,
            // so this is always a plain decimal expansion — a float big enough
            // to matter simply fails the shape check below.
            string s = v.ToString("0.###", CultureInfo.InvariantCulture);
            return WireFieldShapeOk(s) ? s : WIRE_MISSING;
        }

        private static string WireValue(WireField f, Player p)
        {
            // Per-FIELD catch, mirroring the board's per-row catch: one stat a
            // card has nulled out renders "-" and the other twenty still land.
            try
            {
                var row = ROWS[f.row];
                var reader = f.second ? row.number2 : row.number;
                return reader == null ? WIRE_MISSING : WireNum(reader(p));
            }
            catch { return WIRE_MISSING; }
        }

        /// <summary>
        /// Encode one player's CURRENT build stats for match history.
        /// Returns null when there is nothing to record (no player / no data /
        /// a broken wire table) — callers omit the field rather than sending
        /// a row of dashes.
        ///
        /// Synchronous and allocation-light (one StringBuilder, 274 chars max)
        /// so it can run in the game-over frame itself. It reads the LIVE
        /// objects, never the 8 Hz overlay snapshot — that cache only refills
        /// while Tab is held, so at game end it is usually stale or empty.
        /// Per #171 the caller must call this from the current frame and never
        /// delay finalisation for it.
        /// </summary>
        public static string CaptureBuildStats(Player p)
        {
            try
            {
                if (p == null || p.data == null) return null;
                if (!WireTableValid()) return null;
                var sb = new StringBuilder(192);
                sb.Append(BUILD_STATS_WIRE_VERSION);
                for (int i = 0; i < WIRE_V1.Length; i++)
                {
                    sb.Append('|');
                    sb.Append(WireValue(WIRE_V1[i], p));
                }
                return sb.ToString();
            }
            catch { return null; }
        }

        /// <summary>
        /// Every currently-spawned player's build stats, keyed by PlayerID.
        /// Never null; a player whose objects are gone is simply absent (#222 —
        /// departed players linger in PlayerManager.players in FFA, and their
        /// entries fake-null out).
        /// </summary>
        public static Dictionary<int, string> CaptureAllBuildStats()
        {
            var byPlayerId = new Dictionary<int, string>(4);
            try
            {
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return byPlayerId;
                foreach (var p in pm.players)
                {
                    if (p == null || p.data == null) continue;
                    string wire = CaptureBuildStats(p);
                    // Indexer, not Add: a duplicated PlayerID during a spawn
                    // race must not throw out of a report path.
                    if (!string.IsNullOrEmpty(wire)) byPlayerId[p.PlayerID] = wire;
                }
            }
            catch { }
            return byPlayerId;
        }

        /// <summary>One decoded stat, ready to render: the overlay's own
        /// localised label plus the value formatted the way the board formats
        /// it ("45/100", "0.75s", "1.5/s", or "-" when it could not be read at
        /// capture time).</summary>
        public struct BuildStatLine
        {
            public string label;
            public string value;
            public BuildStatLine(string l, string v) { label = l; value = v; }
        }

        private static WireField[] WireTableFor(string version)
        {
            // One entry per shipped version. A v2 must ADD a case here, never
            // replace this one — rows stored as v1 have to keep decoding.
            if (version == WIRE_V1_TOKEN) return WIRE_V1;
            return null;
        }

        /// <summary>
        /// Decode a stored build string into ordered label/value pairs, in the
        /// overlay's row order, using the overlay's own localised labels.
        ///
        /// Never null. Returns an EMPTY list — i.e. render no build at all —
        /// for an unknown/absent version prefix or a field-count mismatch:
        /// labelling a payload written by a different version with this
        /// version's table would silently mislabel every stat, which is worse
        /// than showing nothing.
        /// </summary>
        public static List<BuildStatLine> DecodeBuildStats(string wire)
        {
            var lines = new List<BuildStatLine>(ROWS.Length);
            try
            {
                if (string.IsNullOrEmpty(wire)) return lines;
                if (!WireTableValid()) return lines;

                string[] parts = wire.Split('|');   // always >= 1 element
                var table = WireTableFor(parts[0]);
                if (table == null) return lines;                       // unknown/absent version
                // wireFirstAt/wireSecondAt are built from WIRE_V1 only. A future
                // WIRE_V2 must ship its own maps and be selected here — without
                // this fence it would decode against v1's positions, i.e. the
                // exact mislabelling the version token exists to prevent.
                if (table != WIRE_V1) return lines;
                if (parts.Length != table.Length + 1) return lines;    // field-count mismatch

                EnsureLocaleStringsSafe();
                for (int r = 0; r < ROWS.Length; r++)
                {
                    int a = wireFirstAt[r];
                    if (a < 0) continue;                               // row not carried by this version
                    int b = wireSecondAt[r];
                    lines.Add(new BuildStatLine(
                        LabelFor(r),
                        FormatDecodedCell(ROWS[r], parts[a], b >= 0 ? parts[b] : null)));
                }
            }
            catch { lines.Clear(); }
            return lines;
        }

        private static string LabelFor(int r)
        {
            var labels = trLabels;
            if (labels != null && r >= 0 && r < labels.Length && !string.IsNullOrEmpty(labels[r]))
                return labels[r];
            return ROWS[r].label;
        }

        private static string FormatDecodedCell(StatRow row, string a, string b)
        {
            // Parsed invariantly (that is how it was written), re-rendered
            // through the row's own fmt/suffix so a history cell reads like the
            // board cell. NOT a bit-exact round trip and does not claim to be:
            // the wire keeps 3 decimals, the board renders 2, so a value that
            // sits exactly on the 3rd-decimal rounding boundary can land one
            // step off the digit the board showed. Harmless for a build
            // read-out, and storing the full float would spend wire width on
            // digits no surface renders.
            if (!TryParseWire(a, out float fa)) return WIRE_MISSING;
            if (b == null) return fa.ToString(row.fmt) + row.suffix;
            if (!TryParseWire(b, out float fb)) return WIRE_MISSING;
            return fa.ToString(row.fmt) + "/" + fb.ToString(row.fmt) + row.suffix;
        }

        private static bool TryParseWire(string s, out float v)
        {
            v = 0f;
            if (string.IsNullOrEmpty(s) || s == WIRE_MISSING) return false;
            return float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out v);
        }

        // Fallback team palette when PlayerSkinBank can't be read (orange/blue
        // first — ROUNDS' default 1v1 pairing).
        private static readonly Color[] FALLBACK = {
            new Color(0.96f, 0.55f, 0.23f), new Color(0.35f, 0.60f, 0.95f),
            new Color(0.90f, 0.30f, 0.30f), new Color(0.40f, 0.85f, 0.45f),
        };

        private static void RefreshSnapshot(PlayerManager pm)
        {
            nextSnapshotAt = Time.unscaledTime + 0.125f; // 8 Hz stays visually live.
            cachedPlayers.Clear();
            foreach (var p in pm.players)
                if (p != null && p.data != null) cachedPlayers.Add(p);
            cachedPlayers.Sort((a, b) => a.TeamID != b.TeamID ? a.TeamID.CompareTo(b.TeamID)
                                                               : a.PlayerID.CompareTo(b.PlayerID));
            cachedPlayerCount = cachedPlayers.Count;

            while (cachedNames.Count < cachedPlayerCount) cachedNames.Add("");
            while (cachedCards.Count < cachedPlayerCount) cachedCards.Add(new CardRow());
            while (cachedColors.Count < cachedPlayerCount) cachedColors.Add(Color.white);
            while (cachedValues.Count < cachedPlayerCount) cachedValues.Add(new string[ROWS.Length]);

            for (int i = 0; i < cachedPlayerCount; i++)
            {
                var p = cachedPlayers[i];
                cachedNames[i] = Trunc(PlayerName(p), 16);
                RefreshCardRow(cachedCards[i], p);
                cachedColors[i] = TeamColor(p);
                var values = cachedValues[i];
                for (int r = 0; r < ROWS.Length; r++)
                {
                    try { values[r] = DisplayCell(ROWS[r], p); }
                    catch { values[r] = "-"; }
                }
            }
            cardLayoutDirty = true;
        }

        public static void Draw()
        {
            try
            {
                if (Event.current == null || Event.current.type != EventType.Repaint) return;
                if (!Input.GetKey(KeyCode.Tab)) return;
                if (NativeUI.IsOpen) return;                    // F5 menu owns the screen
                if (CompetitiveUI.IsChatInputOpen) return;      // typing in chat
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null || pm.players.Count == 0) return;

                EnsureLocaleStrings();   // before RefreshSnapshot — it reads trNoCards
                if (Time.unscaledTime >= nextSnapshotAt) RefreshSnapshot(pm);
                if (cachedPlayerCount == 0) return;

                EnsureStyles();

                float labelW = 118f;
                float colW = Mathf.Clamp((Screen.width * 0.62f - labelW) / cachedPlayerCount, 130f, 210f);
                float w = labelW + colW * cachedPlayerCount + 24f;
                float rowH = 21f;
                float cardWidth = colW - 8f;
                if (cardLayoutDirty || Mathf.Abs(cachedCardLayoutWidth - cardWidth) > 0.5f)
                {
                    // +3px per line and extra tail slack: the skin's real glyph
                    // height exceeds lineHeight (#143) — see stCards.clipping.
                    float lineH = Mathf.Max(15f, stCards.lineHeight + 3f);
                    int maxLines = 1;
                    for (int i = 0; i < cachedPlayerCount; i++)
                        maxLines = Mathf.Max(maxLines, PrepareCardRowLayout(cachedCards[i], cardWidth, 4));
                    cachedCardsHeight = maxLines * lineH + 8f;
                    cachedCardLayoutWidth = cardWidth;
                    cardLayoutDirty = false;
                }
                float cardsH = cachedCardsHeight;
                float h = 34f + 26f + ROWS.Length * rowH + cardsH + 16f;
                float x = (Screen.width - w) / 2f;
                float y = Mathf.Max(24f, (Screen.height - h) * 0.5f);

                GUI.DrawTexture(new Rect(x, y, w, h), Texture2D.whiteTexture,
                    ScaleMode.StretchToFill, true, 0, new Color(0f, 0f, 0f, 0.88f), 0, 0);
                GUI.Label(new Rect(x + 12, y + 6, w - 24, 24),
                    trTitle ?? "MATCH STATS  <color=#888><size=12>(hold Tab)</size></color>", stTitle);

                // Player name headers, team-colored.
                float cx = x + 12 + labelW;
                for (int i = 0; i < cachedPlayerCount; i++)
                {
                    var prev = GUI.contentColor;
                    GUI.contentColor = cachedColors[i];
                    GUI.Label(new Rect(cx, y + 34, colW - 6, 22), cachedNames[i], stName);
                    GUI.contentColor = prev;
                    cx += colW;
                }

                // Stat rows.
                float ry = y + 34 + 26;
                for (int r = 0; r < ROWS.Length; r++)
                {
                    if ((r & 1) == 0)
                        GUI.DrawTexture(new Rect(x + 6, ry, w - 12, rowH), Texture2D.whiteTexture,
                            ScaleMode.StretchToFill, true, 0, new Color(1f, 1f, 1f, 0.03f), 0, 0);
                    GUI.Label(new Rect(x + 12, ry, labelW, rowH), trLabels[r], stLabel);
                    cx = x + 12 + labelW;
                    for (int i = 0; i < cachedPlayerCount; i++)
                    {
                        GUI.Label(new Rect(cx, ry, colW - 6, rowH), cachedValues[i][r], stCell);
                        cx += colW;
                    }
                    ry += rowH;
                }

                // Card lists (up to 4 wrapped lines, then a +N tail).
                ry += 4f;
                GUI.Label(new Rect(x + 12, ry, labelW, cardsH), trCardsLabel ?? "Cards", stLabel);
                cx = x + 12 + labelW;
                Vector2 mousePosition = Event.current.mousePosition;
                Texture2D hoveredCardTexture = null;
                for (int i = 0; i < cachedPlayerCount; i++)
                {
                    hoveredCardTexture = DrawCardRow(
                        cachedCards[i], new Rect(cx, ry, colW - 8, cardsH),
                        mousePosition, hoveredCardTexture);
                    cx += colW;
                }
                if (hoveredCardTexture != null)
                    DrawHoveredCardArt(hoveredCardTexture, mousePosition);
            }
            catch { /* overlay must never break gameplay */ }
        }

        private static void EnsureStyles()
        {
            if (stTitle != null) return;
            stTitle = new GUIStyle(GUI.skin.label) { fontSize = 16, fontStyle = FontStyle.Bold, richText = true };
            stName = new GUIStyle(GUI.skin.label) { fontSize = 14, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleCenter };
            stLabel = new GUIStyle(GUI.skin.label) { fontSize = 13, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleLeft };
            stLabel.normal.textColor = new Color(0.75f, 0.78f, 0.85f);
            stCell = new GUIStyle(GUI.skin.label) { fontSize = 13, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleCenter };
            stCards = new GUIStyle(GUI.skin.label)
            { fontSize = 11, fontStyle = FontStyle.Bold, alignment = TextAnchor.UpperCenter, wordWrap = true, richText = true };
            // Bug #114 item 5: ROUNDS' IMGUI skin has taller glyph metrics
            // than lineHeight reports (learning #143) — with default Clip the
            // bottom card line rendered only its top half. Overflow + the
            // taller line budget below let full glyphs draw.
            stCards.clipping = TextClipping.Overflow;
            stCards.normal.textColor = new Color(0.7f, 0.78f, 0.9f);
            cardSeparatorWidth = stCards.CalcSize(CARD_SEPARATOR).x;
        }

        private static string PlayerName(Player p)
        {
            try
            {
                // NickName carries the styled nametag (per-char rich-text tags
                // for rainbow/gradient SKUs). This IMGUI surface truncates to
                // 16 chars and team-tints via GUI.contentColor, so markup here
                // renders as literal broken tags AND eats the whole name
                // budget — strip to the plain name.
                var nick = p.data.view?.Owner?.NickName;
                if (!string.IsNullOrEmpty(nick)) return NametagStyler.Clean(nick);
            }
            catch { }
            return I18n.TrF("Player {0}", p.PlayerID + 1);
        }

        private static Color TeamColor(Player p)
        {
            // Aug 11 playtest item 3 ("also a thing for non-spectators"): the
            // equipped team-colour identity wins — the skin bank only knows
            // vanilla orange/blue, so a Midnight team read as "blue" here.
            // Tint surface: honours the Show Player Colors toggle (with tints
            // off the bodies ARE vanilla, so vanilla paint matches).
            try
            {
                TeamColorIdentity.TeamIdentity id;
                if (TeamColorIdentity.TintsEnabled && TeamColorIdentity.TryGet(p.TeamID, out id))
                    return id.TextColor;
            }
            catch { }
            try
            {
                var skin = PlayerSkinBank.GetPlayerSkinColors(p.PlayerID);
                if (skin != null) return skin.color;
            }
            catch { }
            return FALLBACK[Mathf.Abs(p.TeamID) % FALLBACK.Length];
        }

        // Bug #64: vanilla's rematch reset (Player.FullReset) resets gun/stats/block
        // but NEVER clears data.currentCards — the list accumulates across every game
        // in the room until DC. The board must show THIS game's cards, so we snapshot
        // each player's card count when FullReset fires (rematch = new game) and skip
        // that many entries when rendering. Baseline missing (fresh room) => skip 0.
        private static readonly Dictionary<Player, int> cardBaseline = new Dictionary<Player, int>();

        public static void RecordCardBaseline(Player p)
        {
            try { if (p != null && p.data != null && p.data.currentCards != null) cardBaseline[p] = p.data.currentCards.Count; }
            catch { }
        }

        public static void ClearCardBaselines()
        {
            cardBaseline.Clear();
        }

        /// <summary>Cards to skip at the head of p.data.currentCards to get
        /// THIS game's deck (see the #64/#138 note above). Used by the
        /// spectator snapshot so the master serializes the active deck, not
        /// the whole-room accumulation.</summary>
        public static int CardBaselineFor(Player p)
        {
            try
            {
                if (p != null && p.data != null && p.data.currentCards != null
                    && cardBaseline.TryGetValue(p, out int b) && b > 0 && b <= p.data.currentCards.Count)
                    return b;
            }
            catch { }
            return 0;
        }

        private static void RefreshCardRow(CardRow row, Player p)
        {
            try
            {
                var cards = p.data.currentCards;
                int skip = 0;
                if (cards != null && cardBaseline.TryGetValue(p, out int b) && b > 0 && b <= cards.Count)
                    skip = b;
                row.count = 0;
                row.totalCount = 0;
                row.visibleCount = 0;
                row.lineCount = 1;
                row.hasTail = false;
                if (cards == null || cards.Count - skip <= 0)
                {
                    row.message.text = trNoCards ?? "<color=#666>no cards</color>";
                    return;
                }
                row.message.text = "";
                for (int i = skip; i < cards.Count; i++)
                {
                    if (cards[i] == null) continue;
                    row.totalCount++;
                    if (row.count >= MAX_SHOWN_CARDS) continue;
                    string rawName = cards[i].cardName ?? "?";
                    string canonicalName = CardRarityLookup.GetCanonicalName(rawName) ?? rawName;
                    var display = row.cards[row.count++];
                    // Uppercase only the cached GUI text; lookup identity stays canonical.
                    display.canonicalName = canonicalName;
                    // L10n interim: localized display name when the game has
                    // one (cache is primed at menu time — this path renders
                    // mid-match and must never trigger the first table scan).
                    string shownName = CardTextLocalizer.PrettyNameIfCached(canonicalName, rawName);
                    display.content.text = Trunc(shownName, 12).ToUpperInvariant()
                        .Replace("<", "(").Replace(">", ")");
                }
            }
            catch
            {
                row.count = 0;
                row.totalCount = 0;
                row.visibleCount = 0;
                row.lineCount = 1;
                row.hasTail = false;
                row.message.text = "-";
            }
        }

        private static Texture2D GetCardTexture(string canonicalName)
        {
            if (string.IsNullOrEmpty(canonicalName)) return null;
            // Locale switch: CardSnapshot.InvalidateAll destroyed every
            // native sprite/texture — drop the whole cache once per
            // generation change so we never serve a destroyed texture.
            if (cardTexGeneration != CardSnapshot.Generation)
            {
                cardTexGeneration = CardSnapshot.Generation;
                cardTextures.Clear();
                cardTexRetryAt.Clear();
            }
            // F3: consult the native snapshot FIRST on every call (cheap
            // dict hit) so a session-cached PNG texture upgrades the moment
            // the async capture lands — the first non-null texture used to
            // be cached forever. Miss => existing session-cache/PNG flow
            // below, unchanged.
            if (CardSnapshot.TryGetSprite(canonicalName, out var snap) && snap != null)
            {
                var native = snap.texture;
                if (native != null)
                {
                    cardTextures[canonicalName] = native;
                    return native;
                }
            }
            else if (!CardSnapshot.IsFailed(canonicalName))
            {
                // R2-2: the session-cached PNG return below bypasses the
                // CardImageLoader.GetSprite seam (and its RequestSnapshot),
                // so without this a card whose capture was lost — e.g. the
                // pump's coroutine host died — never recovered on the Tab
                // board. Cheap and idempotent per frame (RequestSnapshot is
                // O(1) on the repeat path), and it re-arms EnsurePump.
                CardSnapshot.RequestSnapshot(canonicalName);
            }
            if (cardTextures.TryGetValue(canonicalName, out var texture))
            {
                // Misses are cached, but only for a few seconds — on the
                // build flavor that fetches the art pack on first launch,
                // an early hover would otherwise blank that card's art for
                // the whole session.
                if (texture != null) return texture;
                if (cardTexRetryAt.TryGetValue(canonicalName, out float at) &&
                    Time.realtimeSinceStartup < at)
                    return null;
            }
            Sprite sprite = CardImageLoader.GetSprite(canonicalName, prioritize: true);
            texture = sprite != null ? sprite.texture : null;
            cardTextures[canonicalName] = texture;
            if (texture == null) cardTexRetryAt[canonicalName] = Time.realtimeSinceStartup + 5f;
            return texture;
        }

        private static int PrepareCardRowLayout(CardRow row, float width, int maxLines)
        {
            if (!string.IsNullOrEmpty(row.message.text))
            {
                row.visibleCount = 0;
                row.hasTail = false;
                row.lineCount = 1;
                return 1;
            }

            float separatorW = cardSeparatorWidth;
            int chosenLines = 1;
            for (int visible = row.count; visible >= 0; visible--)
            {
                int hidden = Mathf.Max(0, row.totalCount - visible);
                bool tail = hidden > 0;
                if (tail) row.tail.text = $" <color=#888>+{hidden}</color>";
                int tokenCount = visible + (tail ? 1 : 0);
                if (tokenCount == 0)
                {
                    row.visibleCount = 0;
                    row.hasTail = false;
                    row.lineCount = 1;
                    return 1;
                }

                int line = 0;
                float lineW = 0f;
                for (int t = 0; t < tokenCount; t++)
                {
                    GUIContent content = t < visible ? row.cards[t].content : row.tail;
                    float nameW = stCards.CalcSize(content).x;
                    float tokenW = nameW + (t < visible - 1 ? separatorW : 0f);
                    if (lineW > 0f && lineW + tokenW > width)
                    {
                        row.lineWidths[line] = lineW;
                        line++;
                        lineW = 0f;
                    }
                    row.nameWidths[t] = nameW;
                    row.tokenWidths[t] = tokenW;
                    row.tokenLines[t] = line;
                    lineW += tokenW;
                }
                row.lineWidths[line] = lineW;
                chosenLines = line + 1;
                if (chosenLines <= maxLines || visible == 0)
                {
                    row.visibleCount = visible;
                    row.hasTail = tail;
                    row.lineCount = Mathf.Min(chosenLines, maxLines);
                    int finalTokens = visible + (tail ? 1 : 0);
                    for (int l = 0; l < row.lineCount; l++)
                        row.lineX[l] = Mathf.Max(0f, (width - row.lineWidths[l]) * 0.5f);
                    for (int t = 0; t < finalTokens; t++)
                    {
                        int tokenLine = row.tokenLines[t];
                        row.tokenX[t] = row.lineX[tokenLine];
                        row.lineX[tokenLine] += row.tokenWidths[t];
                    }
                    return row.lineCount;
                }
            }
            return Mathf.Min(chosenLines, maxLines);
        }

        private static Texture2D DrawCardRow(CardRow row, Rect rect, Vector2 mousePosition,
                                             Texture2D hoveredTexture)
        {
            if (!string.IsNullOrEmpty(row.message.text))
            {
                GUI.Label(rect, row.message, stCards);
                return hoveredTexture;
            }

            int tokenCount = row.visibleCount + (row.hasTail ? 1 : 0);
            if (tokenCount == 0) return hoveredTexture;

            float separatorW = cardSeparatorWidth;
            float lineH = Mathf.Max(12f, stCards.lineHeight);
            for (int t = 0; t < tokenCount; t++)
            {
                int line = row.tokenLines[t];
                float y = rect.y + line * lineH;
                if (y >= rect.yMax) continue;
                float drawX = rect.x + row.tokenX[t];
                float nameW = row.nameWidths[t];
                if (t < row.visibleCount)
                {
                    var nameRect = new Rect(drawX, y, nameW, lineH);
                    GUI.Label(nameRect, row.cards[t].content, stCards);
                    if (nameRect.Contains(mousePosition))
                        hoveredTexture = GetCardTexture(row.cards[t].canonicalName);
                    drawX += nameW;
                    if (t < row.visibleCount - 1)
                        GUI.Label(new Rect(drawX, y, separatorW, lineH), CARD_SEPARATOR, stCards);
                }
                else
                {
                    GUI.Label(new Rect(drawX, y, nameW, lineH), row.tail, stCards);
                }
            }
            return hoveredTexture;
        }

        private static void DrawHoveredCardArt(Texture2D texture, Vector2 mousePosition)
        {
            const float baseW = 180f;
            const float baseH = 270f;
            const float edge = 4f;
            const float gap = 16f;
            float scale = Mathf.Min(1f, Mathf.Min(
                Mathf.Max(1f, Screen.width - edge * 2f) / baseW,
                Mathf.Max(1f, Screen.height - edge * 2f) / baseH));
            float w = baseW * scale;
            float h = baseH * scale;
            float x = mousePosition.x + gap;
            float y = mousePosition.y + gap;
            if (x + w > Screen.width - edge) x = mousePosition.x - w - gap;
            if (y + h > Screen.height - edge) y = mousePosition.y - h - gap;
            x = Mathf.Clamp(x, edge, Mathf.Max(edge, Screen.width - w - edge));
            y = Mathf.Clamp(y, edge, Mathf.Max(edge, Screen.height - h - edge));
            // This popup follows the cursor, so it usually composites onto the
            // LIVE MAP rather than onto the stats panel — any transparency in
            // the source then reads as "faint and hard to read" (NativeUI's
            // card popup never shows that because its Image sits on a
            // 0.97-alpha panel). Two guards, both cheap:
            //  - an opaque-enough backdrop plate in the panel's own colour, so
            //    a partly-transparent source (the bundled PNGs, and any
            //    snapshot cached before the capture-side fix) still reads;
            //  - an explicitly white GUI.color. DrawUI leaves it white today
            //    (Unity resets it per OnGUI and DrawFPS never touches it), so
            //    this only pins it against a future sibling overlay leaking a
            //    tint into the card.
            const float pad = 6f;
            float bx = Mathf.Max(0f, x - pad);
            float by = Mathf.Max(0f, y - pad);
            float bw = Mathf.Min(Screen.width - bx, w + pad * 2f);
            float bh = Mathf.Min(Screen.height - by, h + pad * 2f);
            var prevColor = GUI.color;
            GUI.color = Color.white;
            GUI.DrawTexture(new Rect(bx, by, bw, bh), Texture2D.whiteTexture,
                ScaleMode.StretchToFill, true, 0, new Color(0f, 0f, 0f, 0.88f), 0, 0);
            GUI.DrawTexture(new Rect(x, y, w, h), texture, ScaleMode.ScaleToFit, true);
            GUI.color = prevColor;
        }

        private static string Trunc(string s, int n)
            => string.IsNullOrEmpty(s) ? "" : (s.Length <= n ? s : s.Substring(0, n - 1) + "~");
    }
}
