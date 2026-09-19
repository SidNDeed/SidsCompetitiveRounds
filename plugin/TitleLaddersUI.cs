using System;
using System.Collections.Generic;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Animal title ladders (v1.41.0 item 12): the Titles tab under
    /// the Shop group. Eight lines, six rungs each; a rung chip per rung, a
    /// progress bar toward the next one, and Set Active on any rung the player
    /// owns. NativeUI owns the tab slot and calls in: BuildInto (tab body),
    /// OnTabEntered (fetch), Refresh (dirty repaint).
    ///
    /// WHAT THIS SCREEN DOES NOT DO. There is no Buy button here. The first
    /// rung of a line is an ordinary priced shop item and is bought on its
    /// ordinary Shop row; rungs above it are `rotation_pool='achievement'` and
    /// are not purchasable at all. Two purchase paths for one item is how a
    /// listing rule turns into a believed gate (#159/#325) — so the unowned
    /// entry rung shows its price and a button that DEEP-LINKS to the Shop
    /// tab, and the buying happens in exactly one place.
    ///
    /// ZERO PROGRESS IS THE NORMAL CASE AT SHIP. `title_ladder_progress` gains
    /// rows only from the completion hook, which is a separate item; until it
    /// is live every player reads back games=0, tier=1 and owns nothing. That
    /// is rendered as NOT STARTED per line — the bar is empty and the caption
    /// names the entry rung and its price. It is never drawn as "0 of 10 to
    /// Rat Leader", which would promise progress the account cannot make.
    ///
    /// UNAVAILABLE IS NOT ZERO. A server without the route answers 404. The
    /// board is then hidden entirely and one line says so. A board of zeroes
    /// would read as a truthful statement about the account (#438: acceptance
    /// is a POSITIVE signal the feature emits, and "all zeroes" is what both
    /// success and total absence look like).</summary>
    internal static class TitleLaddersUI
    {
        private static readonly Color C_PANEL = new Color(0.10f, 0.11f, 0.14f, 0.92f);
        private static readonly Color C_CARD = new Color(0.07f, 0.08f, 0.10f, 0.97f);
        private static readonly Color C_WHITE = Color.white;
        private static readonly Color C_LABEL = new Color(0.7f, 0.7f, 0.75f);
        private static readonly Color C_DIM = new Color(0.45f, 0.45f, 0.50f);
        private static readonly Color C_GOLD = new Color(1f, 0.85f, 0.3f);
        private static readonly Color C_BTN = new Color(0.18f, 0.20f, 0.26f, 0.92f);
        private static readonly Color C_LOCKED = new Color(0.16f, 0.17f, 0.21f, 0.95f);
        private static readonly Color C_BARBG = new Color(0.20f, 0.20f, 0.25f, 0.85f);
        private static readonly Color C_OK = new Color(0.55f, 1f, 0.55f);
        private static readonly Color C_WARN = new Color(1f, 0.55f, 0.45f);

        // The catalogue is eight lines of six rungs. Both pools are built one
        // over that so a catalogue that grows by a line or a rung renders
        // whole instead of silently dropping its tail; a row past the answer's
        // length is hidden, never destroyed.
        private const int MAX_LINES = 10;
        private const int MAX_RUNGS = 8;
        private const float CHIP_W = 150f, CHIP_H = 30f;

        private class ChipRow
        {
            public GameObject root;
            public object txt;
            public ApiClient.TitleLadderRung rung;   // the chip's CURRENT binding — the
                                                     // callback reads this field, never a
                                                     // captured rung (#265)
        }

        private class LineCard
        {
            public GameObject root, chipBar;
            public object txtName, txtState, txtCaption;
            public Component fill;
            public ChipRow[] chips;
        }

        private static GameObject tabRoot, boardGO, emptyGO;
        private static object txtHeaderStatus, txtEmpty, txtStatus;
        private static LineCard[] cards;
        private static bool equipInFlight;
        private static float equipAt;
        private static string lastMsg; private static Color lastMsgColor = C_LABEL;

        private static string LocalId
        {
            get { var id = MatchTracker.LocalSteamId; return string.IsNullOrEmpty(id) || id == "unknown" ? null : id; }
        }

        /// <summary>A rung's `preview_color` as a Color, or a neutral slate
        /// when the server sent nothing usable. `preview_color` is the column
        /// that exists — `color` does not, and two shipped endpoints already
        /// learned that the hard way (#219).</summary>
        private static Color RungColor(ApiClient.TitleLadderRung r)
        {
            Color c;
            string hex = r == null ? null : r.preview_color;
            if (string.IsNullOrEmpty(hex) || !ColorUtility.TryParseHtmlString(hex.StartsWith("#") ? hex : "#" + hex, out c))
                return new Color(0.45f, 0.47f, 0.55f);
            c.a = 1f;
            return c;
        }

        private static Color Dimmed(Color c, float f)
        {
            return new Color(c.r * f, c.g * f, c.b * f, 0.95f);
        }

        // ── build ────────────────────────────────────────────────────────

        internal static void BuildInto(Transform parent)
        {
            // Fresh objects every BuildPage: the pools below are rebuilt
            // wholesale rather than appended to, so no entry can survive
            // pointing at a destroyed page (#147/#149/#150).
            tabRoot = new GameObject("TitlesBody");
            tabRoot.transform.SetParent(parent, false);
            tabRoot.AddComponent<RectTransform>();
            UIFactory.AddVLG(tabRoot, spacing: 6);
            UIFactory.AddLE(tabRoot, flexH: 1);

            var header = new GameObject("TLHdr");
            header.transform.SetParent(tabRoot.transform, false);
            header.AddComponent<RectTransform>();
            UIFactory.AddHLG(header, spacing: 12, forceExpandH: true);
            UIFactory.AddLE(header, prefH: 32, flexH: 0);

            var hTitle = UIFactory.CreateText("TLTitle", header.transform, I18n.Tr("Title Ladders"),
                22f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(320, 30));
            UIFactory.SetBold(hTitle, true);
            UIFactory.FitOneLine(hTitle);

            txtHeaderStatus = UIFactory.CreateText("TLHSt", header.transform, "",
                15f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(420, 30));
            UIFactory.SetFlexW((txtHeaderStatus as Component)?.gameObject, 1f);
            UIFactory.FitOneLine(txtHeaderStatus);

            UIFactory.CreateButton("TLShop", header.transform, I18n.Tr("Open the Shop"), 14f, C_WHITE, C_BTN,
                () => NativeUI.SwitchToShopTab(), sizeDelta: new Vector2(150, 26));

            // The rule, in one sentence, above the board. It is the only place
            // that says progress needs the rung WORN, which is the single fact
            // a player cannot deduce from the numbers.
            var expl = UIFactory.CreateText("TLExpl", tabRoot.transform,
                I18n.Tr("Buy the first rung of a line in the Shop and wear it. Every ranked series you finish while a rung of that line is worn counts one toward the next rung."),
                14f, C_LABEL, sizeDelta: new Vector2(1100, 20));
            UIFactory.SetTextAutoHeight(expl, 20f);

            txtStatus = UIFactory.CreateText("TLSt", tabRoot.transform, "", 15f, C_LABEL,
                sizeDelta: new Vector2(1100, 22));
            UIFactory.SetBold(txtStatus, true);
            UIFactory.FitOneLine(txtStatus);

            // The unavailable / loading line. It and the board are mutually
            // exclusive: exactly one is ever active, so there is no state in
            // which a stale board sits under a message contradicting it.
            emptyGO = new GameObject("TLEmpty");
            emptyGO.transform.SetParent(tabRoot.transform, false);
            emptyGO.AddComponent<RectTransform>();
            UIFactory.AddVLG(emptyGO, spacing: 4, padT: 40);
            UIFactory.AddLE(emptyGO, flexH: 1);
            txtEmpty = UIFactory.CreateText("TLEmptyT", emptyGO.transform, I18n.Tr("Loading..."),
                18f, C_LABEL, UIFactory.AlignMidCenter, sizeDelta: new Vector2(1100, 26));
            UIFactory.SetBold(txtEmpty, true);
            UIFactory.SetTextAutoHeight(txtEmpty, 26f);

            var sv = UIFactory.CreateScrollView("TLSV", tabRoot.transform, spacing: 6);
            UIFactory.AddLE(sv.scrollGO, flexH: 1);
            boardGO = sv.scrollGO;
            cards = new LineCard[MAX_LINES];
            for (int i = 0; i < MAX_LINES; i++) cards[i] = BuildLineCard(sv.content.transform, i);

            boardGO.SetActive(false);
        }

        private static LineCard BuildLineCard(Transform parent, int idx)
        {
            var card = new LineCard();
            card.root = UIFactory.CreatePanel($"TLCard{idx}", parent, C_CARD);
            UIFactory.AddVLG(card.root, spacing: 4, padL: 12, padR: 12, padT: 8, padB: 8);
            UIFactory.AddLE(card.root, flexH: 0);

            var top = new GameObject("Top");
            top.transform.SetParent(card.root.transform, false);
            top.AddComponent<RectTransform>();
            UIFactory.AddHLG(top, spacing: 10, forceExpandH: true);
            UIFactory.AddLE(top, prefH: 26, flexH: 0);

            card.txtName = UIFactory.CreateText("Nm", top.transform, "", 18f, C_WHITE,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(200, 24));
            UIFactory.SetBold(card.txtName, true);
            UIFactory.FitOneLine(card.txtName);

            var sp = new GameObject("S");
            sp.transform.SetParent(top.transform, false);
            sp.AddComponent<RectTransform>();
            UIFactory.AddLE(sp, flexW: 1);

            card.txtState = UIFactory.CreateText("St", top.transform, "", 15f, C_LABEL,
                UIFactory.AlignMidRight, sizeDelta: new Vector2(420, 24));
            UIFactory.FitOneLine(card.txtState);

            card.chipBar = new GameObject("Chips");
            card.chipBar.transform.SetParent(card.root.transform, false);
            card.chipBar.AddComponent<RectTransform>();
            UIFactory.AddHLG(card.chipBar, spacing: 6, forceExpandH: true);
            UIFactory.AddLE(card.chipBar, prefH: CHIP_H, flexH: 0);
            card.chips = new ChipRow[MAX_RUNGS];
            for (int r = 0; r < MAX_RUNGS; r++) card.chips[r] = BuildChip(card.chipBar.transform, idx, r);

            card.fill = UIFactory.CreateFillBar($"TLBar{idx}", card.root.transform, C_BARBG, C_GOLD, 8f);

            card.txtCaption = UIFactory.CreateText("Cap", card.root.transform, "", 14f, C_LABEL,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(1060, 20));
            UIFactory.FitOneLine(card.txtCaption);

            card.root.SetActive(false);
            return card;
        }

        private static ChipRow BuildChip(Transform parent, int lineIdx, int rungIdx)
        {
            var chip = new ChipRow();
            // The click reads chip.rung at CLICK time. Capturing the rung here
            // would bind the chip to whatever the board held when the page was
            // BUILT, which is nothing (#265).
            chip.root = UIFactory.CreateButton($"TLChip{lineIdx}_{rungIdx}", parent, "", 13f,
                C_WHITE, C_LOCKED, () => OnChipClicked(chip), sizeDelta: new Vector2(CHIP_W, CHIP_H));
            UIFactory.AddLE(chip.root, prefW: CHIP_W, prefH: CHIP_H, flexW: 1, flexH: 0);
            chip.txt = UIFactory.GetButtonText(chip.root);
            // The rung names are short, but they are shop-catalogue strings and
            // the chip is a fixed 150px cell: overflow rightward rather than
            // letting the whole label be dropped (#297).
            UIFactory.FitOneLine(chip.txt);
            chip.root.SetActive(false);
            return chip;
        }

        // ── behaviour ────────────────────────────────────────────────────

        /// <summary>Entering the tab asks for a board. ClickGuard is already
        /// applied inside CreateButton, so nothing here re-claims it (#158).</summary>
        internal static void OnTabEntered()
        {
            SelfCheckOnce();
            var id = LocalId;
            if (id == null) return;
            ApiClient.FetchTitleLadders(id);
        }

        private static void OnChipClicked(ChipRow chip)
        {
            var r = chip == null ? null : chip.rung;
            if (r == null) return;
            if (!r.owned)
            {
                // An unowned ENTRY rung is a thing the player can act on, and
                // the action lives in the Shop. An unowned rung above it is
                // not for sale at any price — it says what earns it instead of
                // offering a button that cannot work.
                if (r.tier <= 1) { NativeUI.SwitchToShopTab(); return; }
                SetMsg(I18n.TrF("{0} is earned at {1} series on this line.", r.name, r.threshold), C_LABEL);
                return;
            }
            if (r.active) { SetMsg(I18n.TrF("{0} is already your title.", r.name), C_LABEL); return; }
            if (r.item_id <= 0)
            {
                // The server named no shop row for this sku. Saying so is
                // better than an equip call built on a 0 the server would
                // read as "clear my title" (#430: one refusal must not mean
                // two different things).
                SetMsg(I18n.Tr("This rung has no shop row on the server, so it cannot be worn."), C_WARN);
                return;
            }
            var id = LocalId;
            if (id == null) { SetMsg(I18n.Tr("No Steam account resolved yet."), C_WARN); return; }
            if (equipInFlight && Time.realtimeSinceStartup - equipAt < 10f) return;
            equipInFlight = true; equipAt = Time.realtimeSinceStartup;
            SetMsg(I18n.TrF("Putting on {0}...", r.name), C_LABEL);
            string wanted = r.name;
            ApiClient.SetActiveTitle(id, r.item_id, (ok, resp) =>
            {
                equipInFlight = false;
                if (ok)
                {
                    SetMsg(I18n.TrF("{0} is now your title.", wanted), C_OK);
                    // Forced: the 20 s floor is a poll rule, and this is a
                    // demand — the answer in hand predates the equip that made
                    // us ask, so without the force the chip would keep showing
                    // the previous title until the floor expired.
                    var who = LocalId;
                    if (who != null) ApiClient.FetchTitleLadders(who, true);
                }
                else SetMsg(I18n.Tr("The server refused the title change."), C_WARN);
                try { NativeUI.MarkDirty(); } catch { }
            });
        }

        private static void SetMsg(string s, Color c) { lastMsg = s; lastMsgColor = c; try { NativeUI.MarkDirty(); } catch { } }

        // ── repaint ──────────────────────────────────────────────────────

        internal static void Refresh()
        {
            if (tabRoot == null) return;
            UIFactory.SetText(txtStatus, lastMsg ?? "");
            UIFactory.SetColor(txtStatus, lastMsgColor);

            var d = ApiClient.CachedTitleLadders;
            if (d == null || d.lines.Count == 0)
            {
                ShowEmpty(EmptyText());
                UIFactory.SetText(txtHeaderStatus, "");
                return;
            }

            if (LocalId == null)
            {
                ShowEmpty(I18n.Tr("Sign in on Steam to see your ladders."));
                return;
            }

            emptyGO.SetActive(false);
            boardGO.SetActive(true);

            int owned = 0;
            for (int i = 0; i < d.lines.Count && i < MAX_LINES; i++) if (d.lines[i].AnyOwned) owned++;
            UIFactory.SetText(txtHeaderStatus,
                owned == 0
                    ? I18n.Tr("No line started yet.")
                    : I18n.TrF("{0} of {1} lines started.", owned, d.lines.Count));

            for (int i = 0; i < MAX_LINES; i++)
            {
                var card = cards[i];
                if (card == null) continue;
                if (i >= d.lines.Count) { card.root.SetActive(false); continue; }
                card.root.SetActive(true);
                PaintLine(card, d.lines[i]);
            }
        }

        private static string EmptyText()
        {
            string e = ApiClient.TitleLaddersError;
            if (e == null) return I18n.Tr("Loading...");
            if (e == "route")
                // Named for what it is. The alternative — an empty board — is
                // a claim about the ACCOUNT, and it would be false.
                return I18n.Tr("Ladders unavailable: this server does not serve the ladder route yet.");
            if (e == "parse") return I18n.Tr("Ladders unavailable: the server's answer could not be read.");
            return I18n.Tr("Ladders unavailable: the server could not be reached.");
        }

        private static void ShowEmpty(string s)
        {
            if (boardGO != null) boardGO.SetActive(false);
            if (emptyGO != null) emptyGO.SetActive(true);
            UIFactory.SetText(txtEmpty, s);
        }

        private static void PaintLine(LineCard card, ApiClient.TitleLadderLine ln)
        {
            bool started = ln.AnyOwned;

            ApiClient.TitleLadderRung wornHere = null, entry = null;
            for (int i = 0; i < ln.rungs.Count; i++)
            {
                var r = ln.rungs[i];
                if (r.active) wornHere = r;
                if (entry == null && r.tier <= 1) entry = r;
            }

            UIFactory.SetText(card.txtName, ln.name ?? ln.line);
            UIFactory.SetColor(card.txtName, started ? RungColor(wornHere ?? entry) : C_DIM);

            if (wornHere != null)
            {
                UIFactory.SetText(card.txtState, I18n.TrF("Worn: {0}", wornHere.name));
                UIFactory.SetColor(card.txtState, C_OK);
            }
            else if (started)
            {
                UIFactory.SetText(card.txtState, I18n.Tr("Owned - not worn"));
                UIFactory.SetColor(card.txtState, C_LABEL);
            }
            else
            {
                UIFactory.SetText(card.txtState,
                    entry != null && entry.price > 0
                        ? I18n.TrF("In the Shop - {0} g", entry.price)
                        : I18n.Tr("Not started"));
                UIFactory.SetColor(card.txtState, C_GOLD);
            }

            for (int i = 0; i < MAX_RUNGS; i++)
            {
                var chip = card.chips[i];
                if (chip == null) continue;
                if (i >= ln.rungs.Count) { chip.rung = null; chip.root.SetActive(false); continue; }
                var r = ln.rungs[i];
                chip.rung = r;
                chip.root.SetActive(true);
                UIFactory.SetText(chip.txt, r.name ?? r.sku);
                Color rc = RungColor(r);
                if (r.active)
                {
                    UIFactory.SetImageColor(chip.root, rc);
                    UIFactory.SetColor(chip.txt, Color.black);
                    UIFactory.SetBold(chip.txt, true);
                }
                else if (r.owned)
                {
                    UIFactory.SetImageColor(chip.root, Dimmed(rc, 0.55f));
                    UIFactory.SetColor(chip.txt, C_WHITE);
                    UIFactory.SetBold(chip.txt, true);
                }
                else
                {
                    UIFactory.SetImageColor(chip.root, C_LOCKED);
                    UIFactory.SetColor(chip.txt, C_DIM);
                    // Bold by default everywhere: the SDF font renders thin
                    // letters badly otherwise.
                    UIFactory.SetBold(chip.txt, true);
                }
            }

            // NOT STARTED draws an EMPTY bar and says what starts the line.
            // The server reports games=0/tier=1 for an account with no
            // progress row, and a "0 / 10 to Rat Leader" caption off those
            // numbers would promise a countdown the account is not in.
            if (!started)
            {
                UIFactory.SetFill(card.fill, 0f);
                UIFactory.SetText(card.txtCaption,
                    entry != null
                        ? I18n.TrF("Not started - buy {0} in the Shop to begin this line.", entry.name)
                        : I18n.Tr("Not started."));
                UIFactory.SetColor(card.txtCaption, C_DIM);
                return;
            }

            if (!ln.has_next)
            {
                UIFactory.SetFill(card.fill, 1f);
                UIFactory.SetText(card.txtCaption, I18n.TrF("{0} series - top of the line.", ln.games));
                UIFactory.SetColor(card.txtCaption, C_GOLD);
                return;
            }

            // The bar spans THIS tier's threshold to the next one, not 0 to
            // the next one: a player at 80 of 150 with the tier-4 rung has
            // covered a third of that rung, not four fifths of it.
            int floorT = 0;
            for (int i = 0; i < ln.rungs.Count; i++)
                if (ln.rungs[i].tier == ln.tier && ln.rungs[i].threshold > floorT) floorT = ln.rungs[i].threshold;
            int span = ln.next_threshold - floorT;
            float frac = span > 0 ? (float)(ln.games - floorT) / span : 0f;
            UIFactory.SetFill(card.fill, Mathf.Clamp01(frac));

            string nextName = ln.next_names.Length > 0 ? string.Join(" / ", ln.next_names) : "";
            UIFactory.SetText(card.txtCaption,
                string.IsNullOrEmpty(nextName)
                    ? I18n.TrF("{0} series - {1} to go.", ln.games, ln.games_to_next)
                    : I18n.TrF("{0} series - {1} to go to {2}.", ln.games, ln.games_to_next, nextName));
            UIFactory.SetColor(card.txtCaption, C_LABEL);
        }

        // ── parser self-check (acceptance §3) ────────────────────────────

        private static bool selfChecked;

        /// <summary>One shot, first time the tab opens: run a fixture whose
        /// `rungs[]` REPEAT the keys `name`, `tier`, `sku` and `threshold`
        /// through the real parser and log whether each field came back with
        /// the rung's value or the line's.
        ///
        /// This exists because there is no C# test runner on this project, and
        /// the failure it guards is silent by construction: a flat
        /// `ExtractJson*` reader returns the FIRST occurrence in the whole
        /// body, so it would answer "Rat" for a line's name and "Rat" for
        /// every rung's name and every assertion about the shape would still
        /// pass (#608). The check is a POSITIVE signal the feature emits into
        /// the log (#438), and the log line is what the in-game pass reads.</summary>
        private static void SelfCheckOnce()
        {
            if (selfChecked) return;
            selfChecked = true;
            try
            {
                // Deliberately adversarial ordering: the LINE's name/tier come
                // first, and the rungs repeat both. A reader that searches the
                // whole text answers every rung with the line's values.
                const string fixture =
                    "{\"steam_id\":\"7656\",\"active_line\":\"rat\",\"ladders\":[{" +
                    "\"line\":\"rat\",\"name\":\"Rat\",\"games\":30,\"tier\":3,\"max_tier\":5," +
                    "\"next_tier\":4,\"next_threshold\":75,\"next_names\":[\"Rat King\",\"Rat Queen\"]," +
                    "\"games_to_next\":45,\"rungs\":[" +
                    "{\"tier\":1,\"sku\":\"title_ladder_rat_1\",\"item_id\":11,\"name\":\"Rat\"," +
                    "\"description\":\"d1\",\"rarity\":\"rare\",\"preview_color\":\"#9AA0A6\"," +
                    "\"threshold\":0,\"price\":1000,\"owned\":true,\"active\":false}," +
                    "{\"tier\":4,\"sku\":\"title_ladder_rat_4_queen\",\"item_id\":14,\"name\":\"Rat Queen\"," +
                    "\"description\":\"d2\",\"rarity\":\"epic\",\"preview_color\":\"#E0B33A\"," +
                    "\"threshold\":75,\"price\":0,\"owned\":false,\"active\":true}]}]}";

                var d = ApiClient.ParseTitleLadders(fixture);
                var bad = new List<string>();
                if (d == null || d.lines.Count != 1) { Plugin.Log.LogWarning("[LADDER] parser self-check FAILED: no line parsed"); return; }
                var ln = d.lines[0];
                int checks = 0;
                Action<string, bool> want = (field, okv) => { checks++; if (!okv) bad.Add(field); };
                want("line.name", ln.name == "Rat");
                want("line.games", ln.games == 30);
                want("line.tier", ln.tier == 3);
                want("line.max_tier", ln.max_tier == 5);
                want("line.has_next", ln.has_next);
                want("line.next_threshold", ln.next_threshold == 75);
                want("line.games_to_next", ln.games_to_next == 45);
                want("line.next_names", ln.next_names.Length == 2 && ln.next_names[1] == "Rat Queen");
                want("rungs.count", ln.rungs.Count == 2);
                if (ln.rungs.Count == 2)
                {
                    var r0 = ln.rungs[0]; var r1 = ln.rungs[1];
                    want("rung0.sku", r0.sku == "title_ladder_rat_1");
                    want("rung0.name", r0.name == "Rat");
                    want("rung0.owned", r0.owned);
                    want("rung0.price", r0.price == 1000);
                    want("rung1.tier", r1.tier == 4);
                    want("rung1.sku", r1.sku == "title_ladder_rat_4_queen");
                    want("rung1.name", r1.name == "Rat Queen");
                    want("rung1.item_id", r1.item_id == 14L);
                    want("rung1.threshold", r1.threshold == 75);
                    want("rung1.preview_color", r1.preview_color == "#E0B33A");
                    want("rung1.rarity", r1.rarity == "epic");
                    want("rung1.description", r1.description == "d2");
                    want("rung1.active", r1.active);
                    want("rung1.owned-false", !r1.owned);
                }
                // A rung missing its sku must be DROPPED, not rendered blank.
                var missing = ApiClient.ParseTitleLadderRung("{\"tier\":2,\"name\":\"Rat Leader\"}");
                want("rung-without-sku-dropped", missing == null);

                if (bad.Count == 0)
                    Plugin.Log.LogInfo($"[LADDER] parser self-check: {checks}/{checks} fields OK (rungs repeat name/tier/sku/threshold)");
                else
                    Plugin.Log.LogWarning($"[LADDER] parser self-check FAILED on {bad.Count}/{checks}: {string.Join(", ", bad.ToArray())}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[LADDER] parser self-check threw: {ex.Message}"); }
        }
    }
}
