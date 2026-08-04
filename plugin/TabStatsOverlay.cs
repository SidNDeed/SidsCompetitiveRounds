using System;
using System.Collections.Generic;
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

        // Stat row description: label + per-player value resolver.
        private struct StatRow
        {
            public string label;
            public Func<Player, string> value;
            public StatRow(string l, Func<Player, string> v) { label = l; value = v; }
        }

        private static readonly StatRow[] ROWS = new[]
        {
            // Clamp at 0 — a dead player's health goes negative internally
            // and "-39/100" on the board reads as a bug (July 28 screenshot).
            new StatRow("HP",          p => $"{Mathf.Max(0f, p.data.health):F0}/{p.data.MaxHealth:F0}"),
            new StatRow("Lives",       p => $"{p.data.stats.remainingRespawns + 1:F0}"),
            // Infoholic's damage formula: gun.damage x bulletDamageMultiplier x 55
            // (55 = vanilla base bullet damage).
            new StatRow("Damage",      p => $"{Gun(p).damage * Gun(p).bulletDamageMultiplier * 55f:F0}"),
            new StatRow("Attack spd",  p => $"{Gun(p).attackSpeed * Gun(p).attackSpeedMultiplier:F2}s"),
            new StatRow("Reload",      p => { var ga = Ammo(p); return $"{(ga.reloadTime + ga.reloadTimeAdd) * ga.reloadTimeMultiplier:F2}s"; }),
            new StatRow("Ammo",        p => $"{Ammo(p).maxAmmo:F0}"),
            new StatRow("Bullets",     p => $"{Gun(p).numberOfProjectiles:F0}"),
            new StatRow("Bursts",      p => $"{Gun(p).bursts:F0}"),
            new StatRow("Bounces",     p => $"{Gun(p).reflects:F0}"),
            new StatRow("Bullet spd",  p => $"{Gun(p).projectileSpeed:F2}"),
            new StatRow("Bullet slow", p => $"{Gun(p).slow:F2}"),
            new StatRow("Knockback",   p => $"{Gun(p).knockback:F2}"),
            new StatRow("Spread",      p => $"{Gun(p).spread:F2}"),
            new StatRow("Life steal",  p => $"{p.data.stats.lifeSteal:F2}"),
            new StatRow("Block CD",    p => $"{p.data.block.Cooldown():F2}s"),
            new StatRow("Blocks",      p => $"{p.data.block.additionalBlocks + 1:F0}"),
            new StatRow("Regen",       p => $"{p.data.healthHandler.regeneration:F1}/s"),
            new StatRow("Move spd",    p => $"{p.data.stats.movementSpeed:F2}"),
            new StatRow("Jump",        p => $"{p.data.stats.jump:F2}"),
            new StatRow("Jumps",       p => $"{p.data.stats.numberOfJumps:F0}"),
            new StatRow("Size",        p => $"{p.data.stats.sizeMultiplier:F2}"),
        };

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

        private static void EnsureLocaleStrings()
        {
            if (trLabels != null) return;
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
                    try { values[r] = ROWS[r].value(p); }
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
                    string shownName = CardTextLocalizer.DisplayNameIfCached(canonicalName) ?? rawName;
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
            Sprite sprite = CardImageLoader.GetSprite(canonicalName);
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
            GUI.DrawTexture(new Rect(x, y, w, h), texture, ScaleMode.ScaleToFit, true);
        }

        private static string Trunc(string s, int n)
            => string.IsNullOrEmpty(s) ? "" : (s.Length <= n ? s : s.Substring(0, n - 1) + "~");
    }
}
