using System;
using System.Collections.Generic;
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

        // Stat row description: label + per-player value resolver.
        private struct StatRow
        {
            public string label;
            public Func<Player, string> value;
            public StatRow(string l, Func<Player, string> v) { label = l; value = v; }
        }

        private static readonly StatRow[] ROWS = new[]
        {
            new StatRow("HP",          p => $"{p.data.health:F0}/{p.data.MaxHealth:F0}"),
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

        // Fallback team palette when PlayerSkinBank can't be read (orange/blue
        // first — ROUNDS' default 1v1 pairing).
        private static readonly Color[] FALLBACK = {
            new Color(0.96f, 0.55f, 0.23f), new Color(0.35f, 0.60f, 0.95f),
            new Color(0.90f, 0.30f, 0.30f), new Color(0.40f, 0.85f, 0.45f),
        };

        public static void Draw()
        {
            try
            {
                if (!Input.GetKey(KeyCode.Tab)) return;
                if (NativeUI.IsOpen) return;                    // F5 menu owns the screen
                if (CompetitiveUI.IsChatInputOpen) return;      // typing in chat
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null || pm.players.Count == 0) return;

                // Collect live players sorted by team then player id — TabInfo's order.
                var players = new List<Player>();
                foreach (var p in pm.players)
                    if (p != null && p.data != null) players.Add(p);
                if (players.Count == 0) return;
                players.Sort((a, b) => a.TeamID != b.TeamID ? a.TeamID.CompareTo(b.TeamID)
                                                             : a.PlayerID.CompareTo(b.PlayerID));

                EnsureStyles();

                float labelW = 118f;
                float colW = Mathf.Clamp((Screen.width * 0.62f - labelW) / players.Count, 130f, 210f);
                float w = labelW + colW * players.Count + 24f;
                float rowH = 21f;
                float cardsH = 52f;
                float h = 34f + 26f + ROWS.Length * rowH + cardsH + 16f;
                float x = (Screen.width - w) / 2f;
                float y = Mathf.Max(24f, (Screen.height - h) * 0.42f);

                GUI.DrawTexture(new Rect(x, y, w, h), Texture2D.whiteTexture,
                    ScaleMode.StretchToFill, true, 0, new Color(0f, 0f, 0f, 0.88f), 0, 0);
                GUI.Label(new Rect(x + 12, y + 6, w - 24, 24),
                    "MATCH STATS  <color=#888><size=12>(hold Tab)</size></color>", stTitle);

                // Player name headers, team-colored.
                float cx = x + 12 + labelW;
                foreach (var p in players)
                {
                    Color tc = TeamColor(p);
                    string nm = PlayerName(p);
                    var prev = GUI.contentColor;
                    GUI.contentColor = tc;
                    GUI.Label(new Rect(cx, y + 34, colW - 6, 22), Trunc(nm, 16), stName);
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
                    GUI.Label(new Rect(x + 12, ry, labelW, rowH), ROWS[r].label, stLabel);
                    cx = x + 12 + labelW;
                    foreach (var p in players)
                    {
                        string v;
                        try { v = ROWS[r].value(p); }
                        catch { v = "-"; }
                        GUI.Label(new Rect(cx, ry, colW - 6, rowH), v, stCell);
                        cx += colW;
                    }
                    ry += rowH;
                }

                // Card lists (2 lines per player, truncated with a +N tail).
                ry += 4f;
                GUI.Label(new Rect(x + 12, ry, labelW, cardsH), "Cards", stLabel);
                cx = x + 12 + labelW;
                foreach (var p in players)
                {
                    GUI.Label(new Rect(cx, ry, colW - 8, cardsH), CardLine(p), stCards);
                    cx += colW;
                }
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
            { fontSize = 11, fontStyle = FontStyle.Bold, alignment = TextAnchor.UpperCenter, wordWrap = true };
            stCards.normal.textColor = new Color(0.7f, 0.78f, 0.9f);
        }

        private static string PlayerName(Player p)
        {
            try
            {
                var nick = p.data.view?.Owner?.NickName;
                if (!string.IsNullOrEmpty(nick)) return nick;
            }
            catch { }
            return $"Player {p.PlayerID + 1}";
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

        private static string CardLine(Player p)
        {
            try
            {
                var cards = p.data.currentCards;
                int skip = 0;
                if (cards != null && cardBaseline.TryGetValue(p, out int b) && b > 0 && b <= cards.Count)
                    skip = b;
                if (cards == null || cards.Count - skip <= 0) return "<color=#666>no cards</color>";
                var sb = new StringBuilder();
                int shown = 0;
                for (int i = skip; i < cards.Count && shown < 8; i++)
                {
                    if (cards[i] == null) continue;
                    if (shown > 0) sb.Append(", ");
                    sb.Append(Trunc(cards[i].cardName ?? "?", 12));
                    shown++;
                }
                if (cards.Count - skip > shown) sb.Append($" <color=#888>+{cards.Count - skip - shown}</color>");
                return sb.ToString();
            }
            catch { return "-"; }
        }

        private static string Trunc(string s, int n)
            => string.IsNullOrEmpty(s) ? "" : (s.Length <= n ? s : s.Substring(0, n - 1) + "~");
    }
}
