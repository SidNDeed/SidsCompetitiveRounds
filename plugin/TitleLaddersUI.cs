using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Animal title ladders (v1.41.0 item 12) as ENTRIES OF THE SHOP'S
    /// TITLES SECTION, plus the tier popup a click on an entry opens. The item 12
    /// follow-up (2026-09-23) retired the separate Titles sub-tab: one entry per
    /// line the ladder answer carries now sits beside the ordinary titles, in
    /// their row shape, and its button reads Buy until a tier is held, Upgrade
    /// once one is, and Maxed at the top. NativeUI owns the section and calls in:
    /// BuildShopEntries (page build), OnShopEntered (fetch), PlanShopSection and
    /// PaintShopEntries (every Shop repaint), HidePopup (every close path).
    ///
    /// The DECISIONS live in TitleLadderRules.cs, not here: which lines render
    /// (each once), which listing rows they replace, which tier is held, and
    /// what the button says and why it is disabled. That file is Unity-free so
    /// tools/client-rules-harness executes it; this file resolves the inputs
    /// from the server's answers, hands them over, and paints what comes back.
    ///
    /// ONE PURCHASE PATH. The first rung of a line is an ordinary priced shop
    /// item, and an entry's Buy sends exactly the statement the ordinary Shop
    /// row sends for it (PurchaseItem, no price attestation), so buying an item
    /// still has one wire contract (#159/#325). Rungs above the first are
    /// `rotation_pool='achievement'` and the purchase endpoint refuses them, so
    /// Upgrade toward one of them is disabled and says the tier is earned by
    /// play, instead of offering a button that cannot work. A rendered line's
    /// rungs leave the ordinary title rows, so no rung is listed twice.
    ///
    /// ZERO PROGRESS IS THE NORMAL CASE AT SHIP, and it arrives two ways.
    /// `title_ladder_progress` gains rows only from the completion hook, which
    /// is a separate item, so until it is live nobody advances.
    ///
    ///   * An account the route KNOWS reads back games=0, tier=1 and owns
    ///     nothing. Rendered as NOT STARTED per line: the popup's bar is empty
    ///     and its caption names the entry rung. It is never drawn as "0 of 10
    ///     to Rat Leader", which would promise progress the account cannot make.
    ///   * An account the route does not know AT ALL — no Player row on this
    ///     backend — gets a 404 carrying the route's own marker. That is one
    ///     note row in the section, not a board: EmptyText's "empty" branch.
    ///     Saying "every player reads back games=0" skipped this case
    ///     entirely.
    ///
    /// CORRECTED (Codex client r2 LOW): the second bullet used to say this
    /// 404 is "every account until it buys an entry rung". It is not. Buying
    /// an entry rung is not what creates the row this route looks for; an
    /// account the backend knows, with no ladder progress, gets the 200 of
    /// the FIRST bullet. What the 404 means is that the backend has no Player
    /// row for this Steam ID at all.
    ///
    /// UNAVAILABLE IS NOT ZERO. A server without the route answers 404 too,
    /// WITHOUT the marker, and that is what tells the two apart — see
    /// ApiClient.TitleLadderFailure. No entry is drawn then, and one note row
    /// says so. Entries of zeroes would read as a truthful statement about the
    /// account (#438: acceptance is a POSITIVE signal the feature emits, and
    /// "all zeroes" is what both success and total absence look like).</summary>
    internal static class TitleLaddersUI
    {
        private static readonly Color C_PANEL = new Color(0.10f, 0.11f, 0.14f, 0.92f);
        private static readonly Color C_CARD = new Color(0.07f, 0.08f, 0.10f, 0.97f);
        private static readonly Color C_BOX = new Color(0.10f, 0.12f, 0.16f, 0.97f);
        private static readonly Color C_WHITE = Color.white;
        private static readonly Color C_LABEL = new Color(0.7f, 0.7f, 0.75f);
        private static readonly Color C_DIM = new Color(0.45f, 0.45f, 0.50f);
        private static readonly Color C_GOLD = new Color(1f, 0.85f, 0.3f);
        private static readonly Color C_BTN = new Color(0.18f, 0.20f, 0.26f, 0.92f);
        private static readonly Color C_BARBG = new Color(0.20f, 0.20f, 0.25f, 0.85f);
        private static readonly Color C_OK = new Color(0.55f, 1f, 0.55f);
        private static readonly Color C_WARN = new Color(1f, 0.55f, 0.45f);
        // The Shop row's own button colours (NativeUI.CreateShopRow / ApplyShopRow),
        // so an entry's Buy reads exactly like the ordinary row's beside it.
        private static readonly Color C_BUY = new Color(0.25f, 0.45f, 0.18f, 0.9f);
        private static readonly Color C_BUY_OFF = new Color(0.25f, 0.25f, 0.28f, 0.8f);
        private static readonly Color C_BUY_OFF_TXT = new Color(0.55f, 0.55f, 0.6f);
        private static readonly Color C_WEAR = new Color(0.3f, 0.3f, 0.5f, 0.9f);
        private static readonly Color C_WORN = new Color(0.2f, 0.55f, 0.2f, 0.95f);

        // The catalogue is eight lines; the rat line has six rungs over five
        // tiers. Both pools are built past that so a catalogue that grows by a
        // line or a rung renders whole. A line the entry pool cannot hold is
        // not folded (TitleLadderRules.PlanSection), so its rungs keep their
        // ordinary rows and nothing becomes unreachable; a rung past the popup's
        // pool is logged.
        private const int MAX_LINES = 10;
        private const int MAX_RUNGS = 8;

        /// <summary>One entry of the Titles section: the Shop row's shape
        /// (name + description column, price cell, one button).</summary>
        private class Entry
        {
            public GameObject root, btn;
            public object txtName, txtDesc, txtPrice, btnTxt;
            public bool enabled;   // the button's PAINTED state: the row yields to it only while enabled
            public string line;    // the entry's CURRENT binding — every callback reads this, never a captured line (#265)
            public string sig;     // the last decision logged for this entry, so the log fires on change only
        }

        /// <summary>One tier row of the popup.</summary>
        private class TierRow
        {
            public GameObject root, wearBtn;
            public object txtTier, txtName, txtReq, txtState, wearTxt;
            public ApiClient.TitleLadderRung rung;   // CURRENT binding, read at click time (#265)
            public bool owned;                       // ownership as the rules read it (answer or listing)
        }

        private static readonly List<Entry> entries = new List<Entry>();
        private static GameObject noteRow;
        private static object txtNote;
        private static TitleLadderRules.SectionPlan plan;
        private static string planSig;
        private static int? lastBalance;

        private static GameObject popupGO, popupBox, popupAction;
        private static object popTitle, popHeld, popCaption, popReason, popMsg, popActionTxt;
        private static Component popFill;
        private static TierRow[] popRows;
        private static string popupLine;
        private static int popupFrame = -1;

        private static bool buyInFlight, equipInFlight;
        private static float buyAt, equipAt;
        private static string lastMsg;

        /// <summary>A board loaded by the broadcast-seat lever (DevDirective),
        /// or null. While it is set, nothing is bought or worn from it.</summary>
        private static ApiClient.TitleLadders devBoard;

        private static ApiClient.TitleLadders Board { get { return devBoard ?? ApiClient.CachedTitleLadders; } }

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

        // ── build: the section's entries ─────────────────────────────────

        /// <summary>Builds the entry pool and its one note row inside the
        /// Shop's row container. Fresh objects every page build: the pool is
        /// replaced wholesale rather than appended to, so no entry can survive
        /// pointing at a destroyed page (#147/#149/#150). Everything starts
        /// hidden; PaintShopEntries places and shows it.</summary>
        internal static void BuildShopEntries(Transform container)
        {
            entries.Clear();
            plan = null; planSig = null;
            for (int i = 0; i < MAX_LINES; i++) entries.Add(BuildEntry(container, i));

            noteRow = UIFactory.CreatePanel("TLNote", container, C_PANEL);
            UIFactory.AddHLG(noteRow, spacing: 10, padL: 10, padR: 10, padT: 6, padB: 6, forceExpandH: true);
            UIFactory.AddLE(noteRow, prefH: 44, flexH: 0);
            txtNote = UIFactory.CreateText("TLNoteT", noteRow.transform, "", 15f, C_LABEL,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 30));
            UIFactory.SetBold(txtNote, true);
            UIFactory.FitOneLine(txtNote);
            noteRow.SetActive(false);
        }

        private static Entry BuildEntry(Transform parent, int idx)
        {
            var e = new Entry();
            e.root = UIFactory.CreatePanel($"TLE{idx}", parent, C_PANEL);
            UIFactory.AddHLG(e.root, spacing: 10, padL: 10, padR: 10, padT: 6, padB: 6, forceExpandH: true);
            UIFactory.AddLE(e.root, prefH: 44, flexH: 0);
            // The whole row opens the tier popup. It reads e.line at CLICK
            // time (#265). It yields while the pointer is over the row's own
            // ENABLED button — the row and the button are both raw-poll
            // handlers on one mouse-down, and the button is what the player
            // aimed at (#540). A DISABLED button claims nothing, so pressing
            // it opens the popup, which says why it is disabled. ClickGuard is
            // already applied inside AddClick and CreateButton (#158).
            UIFactory.AddClick(e.root, () =>
            {
                if (e.enabled && NativeUI.PointerOverActive(e.btn)) return;
                OpenPopup(e.line);
            });

            var info = new GameObject("info");
            info.transform.SetParent(e.root.transform, false);
            info.AddComponent<RectTransform>();
            UIFactory.AddVLG(info, spacing: 0);
            UIFactory.AddLE(info, flexW: 1);
            e.txtName = UIFactory.CreateText($"tln{idx}", info.transform, "", 17f, C_WHITE,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(500, 22));
            UIFactory.SetBold(e.txtName, true);
            UIFactory.FitOneLine(e.txtName);
            e.txtDesc = UIFactory.CreateText($"tld{idx}", info.transform, "", 13f, C_DIM,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(500, 18));
            UIFactory.FitOneLine(e.txtDesc);

            e.txtPrice = UIFactory.CreateText($"tlp{idx}", e.root.transform, "", 17f, C_GOLD,
                UIFactory.AlignMidRight, sizeDelta: new Vector2(120, 30));
            UIFactory.SetBold(e.txtPrice, true);

            // 100 wide where the Shop's Buy is 80: this label can also read
            // Upgrade or Maxed, and the longest translations need the room.
            e.btn = UIFactory.CreateButton($"tlb{idx}", e.root.transform, I18n.Tr("Buy"), 14f, C_WHITE, C_BUY,
                () => OnActionClicked(e.line, false), sizeDelta: new Vector2(100, 28));
            UIFactory.AddLE(e.btn, prefW: 100, prefH: 28, flexW: 0, flexH: 0);
            e.btnTxt = UIFactory.GetButtonText(e.btn);
            UIFactory.FitOneLine(e.btnTxt);

            e.root.SetActive(false);
            return e;
        }

        // ── behaviour ────────────────────────────────────────────────────

        /// <summary>Entering the Shop asks for a board; the 20 s floor inside
        /// FetchTitleLadders makes a repeat entry free. Nothing test-shaped
        /// runs here (see the closing note).</summary>
        internal static void OnShopEntered()
        {
            var id = LocalId;
            if (id == null) return;
            ApiClient.FetchTitleLadders(id);
        }

        private static ApiClient.TitleLadderLine FindLine(ApiClient.TitleLadders b, string lineId)
        {
            if (b == null || string.IsNullOrEmpty(lineId)) return null;
            for (int i = 0; i < b.lines.Count; i++)
                if (b.lines[i] != null && b.lines[i].line == lineId) return b.lines[i];
            return null;
        }

        /// <summary>The shop listing as the rules read it: every listed sku and
        /// the price the purchase endpoint charges for it, or null while the
        /// listing has not answered. `owned` collects the listed skus the
        /// listing says the player owns.</summary>
        private static Dictionary<string, int> Listing(out HashSet<string> owned)
        {
            owned = null;
            var items = ApiClient.CachedShopItems;
            if (items == null) return null;
            var d = new Dictionary<string, int>(StringComparer.Ordinal);
            owned = new HashSet<string>(StringComparer.Ordinal);
            foreach (var it in items)
            {
                if (it == null || string.IsNullOrEmpty(it.sku)) continue;
                d[it.sku] = it.price;
                if (it.owned) owned.Add(it.sku);
            }
            return d;
        }

        /// <summary>A line's rungs as the rules read them, index for index
        /// with `ln.rungs`. A rung counts as owned when the ladder answer says
        /// so OR the shop listing does: a purchase refetches the listing
        /// (ApiClient.PurchaseItem), so the entry stops offering what was just
        /// bought even if the forced ladder refetch finds another one already
        /// in flight. Both are the server's statements, and the union can only
        /// withhold a purchase, never enable one. A locally loaded board is
        /// not merged with this account's listing.</summary>
        private static List<TitleLadderRules.Rung> RulesRungs(ApiClient.TitleLadderLine ln, HashSet<string> listedOwned)
        {
            var list = new List<TitleLadderRules.Rung>(ln.rungs.Count);
            for (int i = 0; i < ln.rungs.Count; i++)
            {
                var r = ln.rungs[i];
                if (r == null) { list.Add(new TitleLadderRules.Rung()); continue; }
                bool viaListing = devBoard == null && listedOwned != null
                    && !string.IsNullOrEmpty(r.sku) && listedOwned.Contains(r.sku);
                list.Add(new TitleLadderRules.Rung
                {
                    Tier = r.tier,
                    Sku = r.sku,
                    Price = r.price,
                    Threshold = r.threshold,
                    Owned = r.owned || viaListing,
                    Active = r.active,
                });
            }
            return list;
        }

        /// <summary>The button's decision for one line from everything in hand
        /// NOW. Painting and clicking both call this, so a click acts on the
        /// state at the moment of the click, not on the last repaint.</summary>
        private static TitleLadderRules.Decision DecideFor(ApiClient.TitleLadderLine ln,
                                                           out List<TitleLadderRules.Rung> rungs,
                                                           out Dictionary<string, int> listing)
        {
            HashSet<string> owned;
            listing = Listing(out owned);
            rungs = RulesRungs(ln, owned);
            return TitleLadderRules.Decide(rungs, ln.games, LocalId != null, listing, lastBalance);
        }

        private static string ActionLabel(TitleLadderRules.Decision d)
        {
            if (d.Label == TitleLadderRules.Label.Maxed) return I18n.Tr("Maxed");
            if (d.Label == TitleLadderRules.Label.Upgrade) return I18n.Tr("Upgrade");
            return I18n.Tr("Buy");
        }

        /// <summary>Why the button is disabled, in a few words (the entry's
        /// line). Null when it is enabled or maxed.</summary>
        private static string ReasonText(TitleLadderRules.Decision d)
        {
            switch (d.Reason)
            {
                case TitleLadderRules.Reason.NoRungs: return I18n.Tr("No tiers listed");
                case TitleLadderRules.Reason.NoAccount: return I18n.Tr("No Steam account resolved yet.");
                case TitleLadderRules.Reason.ShopLoading: return I18n.Tr("Shop still loading");
                case TitleLadderRules.Reason.NotOnSale: return I18n.Tr("Not on sale yet");
                case TitleLadderRules.Reason.NotEnoughGold: return I18n.Tr("Not enough gold");
                case TitleLadderRules.Reason.EarnedByPlay: return I18n.TrF("Earned at {0} series", d.Threshold);
            }
            return null;
        }

        /// <summary>The Buy / Upgrade button, on an entry and in the popup.
        /// It re-decides from the answers in hand at CLICK time and buys only
        /// the rung that decision names. ClickGuard is already applied inside
        /// CreateButton, so nothing here re-claims it (#158).</summary>
        private static void OnActionClicked(string lineId, bool fromPopup)
        {
            // The popup's button can sit under the pointer that opened the
            // popup, and a raw-poll handler sees that same mouse-down.
            if (fromPopup && Time.frameCount == popupFrame) return;
            var ln = FindLine(Board, lineId);
            if (ln == null) return;
            List<TitleLadderRules.Rung> rungs;
            Dictionary<string, int> listing;
            var d = DecideFor(ln, out rungs, out listing);
            if (!d.Enabled || string.IsNullOrEmpty(d.TargetSku))
            {
                string why = ReasonText(d);
                if (why != null) SetMsg(why, C_WARN);
                return;
            }
            ApiClient.TitleLadderRung r = null;
            for (int i = 0; i < ln.rungs.Count; i++)
                if (ln.rungs[i] != null && ln.rungs[i].sku == d.TargetSku) { r = ln.rungs[i]; break; }
            if (r == null) return;
            if (devBoard != null)
            {
                Plugin.Log.LogInfo($"[LADDER] local board: purchase of {r.sku} not sent");
                return;
            }
            string id = LocalId;
            if (id == null) return;
            if (buyInFlight && Time.realtimeSinceStartup - buyAt < 10f) return;
            buyInFlight = true; buyAt = Time.realtimeSinceStartup;
            Plugin.Log.LogInfo($"[LADDER] {d.Label} {ln.line} to tier {d.NextTier}: buying {r.sku} at {d.Price}g");
            SetMsgRaw(I18n.TrF("Buying {0}...", LadderName(r.name)));
            // The Shop row's own callback, message for message, plus a forced
            // ladder refetch: the answer in hand predates the purchase.
            Action<bool, string> pcb = (ok, resp) =>
            {
                buyInFlight = false;
                Plugin.Log.LogInfo($"[LADDER] purchase complete ok={ok}");
                if (!ok && resp != null && resp.Contains("price_changed"))
                    SetMsgRaw(I18n.Tr("<color=#FF8888>The price changed - check the new price and buy again.</color>"));
                else
                    SetMsgRaw(ok
                        ? I18n.Tr("<color=#88FF88>Purchased!</color>")
                        : I18n.TrF("<color=#FF8888>Purchase failed: {0}</color>", resp));
                if (ok)
                {
                    var who = LocalId;
                    if (who != null) ApiClient.FetchTitleLadders(who, true);
                }
            };
            // The purchase statement is the ordinary Shop row's, byte for byte
            // (NativeUI.CreateShopRow's non-music branch): one wire contract.
            ApiClient.PurchaseItem(id, r.sku, pcb);   // non-music: no attestation (old contract)
        }

        /// <summary>Set Active on an owned rung in the popup. The equip path is
        /// the one the Titles tab had, unchanged.</summary>
        private static void OnWearClicked(TierRow row)
        {
            if (Time.frameCount == popupFrame) return;
            var r = row == null ? null : row.rung;
            if (r == null || !row.owned || r.active) return;
            if (r.item_id <= 0)
            {
                // The server named no shop row for this sku. Saying so is
                // better than an equip call built on a 0 the server would
                // read as "clear my title" (#430: one refusal must not mean
                // two different things).
                SetMsg(I18n.Tr("This rung has no shop row on the server, so it cannot be worn."), C_WARN);
                return;
            }
            if (devBoard != null)
            {
                Plugin.Log.LogInfo($"[LADDER] local board: equip of {r.sku} not sent");
                return;
            }
            var id = LocalId;
            if (id == null) { SetMsg(I18n.Tr("No Steam account resolved yet."), C_WARN); return; }
            if (equipInFlight && Time.realtimeSinceStartup - equipAt < 10f) return;
            equipInFlight = true; equipAt = Time.realtimeSinceStartup;
            SetMsg(I18n.TrF("Putting on {0}...", LadderName(r.name)), C_LABEL);
            // RAW on purpose: this is the value echoed back into the
            // success message below. Translating it here would translate it
            // twice, since the echo is composed like every other site.
            //
            // CORRECTED (Codex client r2 LOW): it is NOT "the same name the
            // server was asked for". SetActiveTitle sends `item_id` and its
            // authentication fields and no name at all — this string never
            // leaves the client. It is the label THIS screen already had for
            // the rung the player clicked, held so the success line can name
            // the same thing the "putting on" line named.
            string wanted = r.name;
            ApiClient.SetActiveTitle(id, r.item_id, (ok, resp) =>
            {
                equipInFlight = false;
                if (ok)
                {
                    SetMsg(I18n.TrF("{0} is now your title.", LadderName(wanted)), C_OK);
                    // Forced: the 20 s floor is a poll rule, and this is a
                    // demand — the answer in hand predates the equip that made
                    // us ask, so without the force the popup would keep showing
                    // the previous title until the floor expired.
                    var who = LocalId;
                    if (who != null) ApiClient.FetchTitleLadders(who, true);
                }
                else SetMsg(I18n.Tr("The server refused the title change."), C_WARN);
                try { NativeUI.MarkDirty(); } catch { }
            });
        }

        /// <summary>A server-provided ladder name, ready to be COMPOSED into a
        /// larger string.
        ///
        /// Rung and line names arrive from the server as data, so no call site
        /// can carry them as a literal and the extractor cannot harvest them
        /// from this file. They are shop_items rows like every other title and
        /// the Shop already renders them through I18n (NativeUI's own item-name
        /// sites), so the ladder surfaces must too: interpolating the raw
        /// English straight into a translated template is how a Spanish player
        /// read "Puesto: Rat Queen".
        ///
        /// Used ONLY where the name is about to be interpolated. A name passed
        /// WHOLE to UIFactory.SetText is already translated there — SetText is
        /// the L10n chokepoint — and wrapping it here as well would translate
        /// it twice.
        ///
        /// THE FALLBACK IS I18n.Tr'S OWN, and it is the documented behaviour
        /// rather than a happy accident: a key with no catalogue entry comes
        /// back unchanged. So a rung the server adds after this build shipped
        /// renders in English, which is worse than a translation and far better
        /// than blank or missing. The catalogue entries for the 48 names the
        /// catalogue defines today ride in tools/shop_strings.json, which is
        /// where server-data display strings are registered for extraction.
        /// A throw cannot reach the caller: this runs inside repaint.</summary>
        private static string LadderName(string serverName)
        {
            if (string.IsNullOrEmpty(serverName)) return serverName;
            try { return I18n.Tr(serverName); } catch { return serverName; }
        }

        /// <summary>The names of a line's rungs at one tier, each translated
        /// BEFORE the join: the joined string is not a catalogue key and would
        /// never match one. Two rungs share a tier on one line (the rat line's
        /// fourth), which is why this is a join at all.</summary>
        private static string TierNames(ApiClient.TitleLadderLine ln, int tier)
        {
            string s = "";
            for (int i = 0; i < ln.rungs.Count; i++)
            {
                var r = ln.rungs[i];
                if (r == null || r.tier != tier || string.IsNullOrEmpty(r.name)) continue;
                s += (s.Length > 0 ? " / " : "") + LadderName(r.name);
            }
            return s;
        }

        private static string Hex(Color c) { return "#" + ColorUtility.ToHtmlStringRGB(c); }

        /// <summary>One line of feedback, shown in the popup and on the Shop's
        /// own status line. `s` arrives translated (or as the server's text),
        /// so both sinks set it raw.</summary>
        private static void SetMsgRaw(string s)
        {
            lastMsg = s;
            try { NativeUI.SetShopStatus(s ?? ""); } catch { }
            if (popMsg != null) UIFactory.SetTextRaw(popMsg, s ?? "");
            try { NativeUI.MarkDirty(); } catch { }
        }

        private static void SetMsg(string s, Color c)
        {
            SetMsgRaw(string.IsNullOrEmpty(s) ? s : "<color=" + Hex(c) + ">" + s + "</color>");
        }

        // ── repaint: the section ─────────────────────────────────────────

        /// <summary>The section plan for the board in hand, and the listing skus
        /// it folds. NativeUI.RefreshShop calls this BEFORE deciding the Titles
        /// header and removes the folded skus from its ordinary title list: a
        /// rendered line's rungs show inside its entry and nowhere else, and a
        /// section holding only ladders still gets its header. With no board
        /// in hand nothing is folded, so every listed rung keeps its ordinary
        /// row until an entry exists to take it.</summary>
        internal static HashSet<string> PlanShopSection()
        {
            var b = Board;
            List<string> ids = null;
            List<IList<string>> skus = null;
            if (b != null)
            {
                ids = new List<string>(b.lines.Count);
                skus = new List<IList<string>>(b.lines.Count);
                for (int i = 0; i < b.lines.Count; i++)
                {
                    var ln = b.lines[i];
                    ids.Add(ln == null ? null : ln.line);
                    var s = new List<string>();
                    if (ln != null)
                        for (int k = 0; k < ln.rungs.Count; k++)
                            if (ln.rungs[k] != null) s.Add(ln.rungs[k].sku);
                    skus.Add(s);
                }
            }
            plan = TitleLadderRules.PlanSection(ids, skus, entries.Count);
            string sig = $"answer={(b == null ? -1 : b.lines.Count)} rendered={plan.Lines.Count} folded={plan.Folded.Count} unrendered={plan.Unrendered} repeats={plan.Repeats} board={(devBoard != null ? "local" : (b != null ? "server" : "none"))}";
            if (sig != planSig)
            {
                planSig = sig;
                Plugin.Log.LogInfo("[LADDER] shop section: " + sig);
                if (plan.Unrendered > 0)
                    Plugin.Log.LogWarning($"[LADDER] {plan.Unrendered} line(s) past the {entries.Count}-entry pool keep their ordinary rows (raise MAX_LINES)");
            }
            return plan.Folded;
        }

        /// <summary>How many rows the section's ladder part occupies this
        /// repaint: one per rendered entry, or the one note row.</summary>
        internal static int ShopSectionRows
        {
            get
            {
                int n = plan == null ? 0 : plan.Lines.Count;
                if (n > 0) return n;
                return NoteText(Board) != null && noteRow != null ? 1 : 0;
            }
        }

        private static string NoteText(ApiClient.TitleLadders b)
        {
            if (b != null) return null;   // a board in hand renders entries, or (with no lines) nothing
            if (LocalId == null) return null;   // no account resolved yet: nothing was asked for
            return EmptyText();
        }

        /// <summary>Called by NativeUI.RefreshShop right after the Titles header
        /// with the next free sibling index; places the entries (or the note
        /// row) there, ahead of the ordinary titles, and returns the next free
        /// index. `show` is false while the category filter hides the Titles
        /// section. `balance` is the number the Shop header shows, or null
        /// while the player's stats have not answered: the funds check is made
        /// against exactly what the player is looking at.</summary>
        internal static int PaintShopEntries(bool show, int sibling, int? balance)
        {
            lastBalance = balance;
            try
            {
                var b = Board;
                // No answer and no error: the fetch has not been asked for
                // since the page opened on this tab. Rate-limited inside the
                // fetch (20 s floor, one in flight); an error stops it.
                if (b == null && ApiClient.TitleLaddersError == null && LocalId != null && devBoard == null)
                    ApiClient.FetchTitleLadders(LocalId);

                string note = show ? NoteText(b) : null;
                if (noteRow != null)
                {
                    noteRow.SetActive(note != null);
                    if (note != null)
                    {
                        noteRow.transform.SetSiblingIndex(sibling++);
                        UIFactory.SetText(txtNote, note);
                    }
                }

                int n = plan == null || b == null ? 0 : plan.Lines.Count;
                for (int i = 0; i < entries.Count; i++)
                {
                    var e = entries[i];
                    if (e == null || e.root == null) continue;
                    int li = i < n ? plan.Lines[i] : -1;
                    if (!show || li < 0 || li >= b.lines.Count || b.lines[li] == null)
                    {
                        e.line = null;
                        e.enabled = false;
                        e.root.SetActive(false);
                        continue;
                    }
                    var ln = b.lines[li];
                    e.line = ln.line;
                    e.root.SetActive(true);
                    e.root.transform.SetSiblingIndex(sibling++);
                    PaintEntry(e, ln);
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[LADDER] section paint failed: {ex.Message}"); }
            try { RefreshPopup(); } catch (Exception ex) { Plugin.Log.LogWarning($"[LADDER] popup paint failed: {ex.Message}"); }
            return sibling;
        }

        private static void PaintEntry(Entry e, ApiClient.TitleLadderLine ln)
        {
            List<TitleLadderRules.Rung> rungs;
            Dictionary<string, int> listing;
            var d = DecideFor(ln, out rungs, out listing);
            int hi = TitleLadderRules.HeldRungIndex(rungs, d.Held);
            var held = hi >= 0 && hi < ln.rungs.Count ? ln.rungs[hi] : null;

            // Name line: the Shop row's own shape — the name in its colour, a
            // grey parenthetical after it. Composed, so every part is
            // translated on its own and the whole is set raw (#298c).
            string col = held != null ? NativeUI.ReadableNameColor(held.preview_color) : Hex(C_DIM);
            int tiers = ln.max_tier;
            for (int i = 0; i < rungs.Count; i++) if (rungs[i].Tier > tiers) tiers = rungs[i].Tier;
            UIFactory.SetTextRaw(e.txtName,
                $"<color={col}>{LadderName(ln.name ?? ln.line)}</color>  <color=#888>({I18n.TrF("{0} tiers - click to see them all", tiers)})</color>");

            // Description line: the tier held (or none), then why the button
            // is disabled, or where the line stands at the top.
            string heldTxt = held != null
                ? I18n.TrF("Current tier: {0} - {1}", d.Held, LadderName(held.name))
                : I18n.Tr("Not started");
            string detail = d.Label == TitleLadderRules.Label.Maxed
                ? I18n.TrF("{0} series - top of the line.", ln.games)
                : ReasonText(d);
            UIFactory.SetTextRaw(e.txtDesc, string.IsNullOrEmpty(detail) ? heldTxt : heldTxt + "  -  " + detail);
            UIFactory.SetColor(e.txtDesc, d.Enabled || d.Label == TitleLadderRules.Label.Maxed ? C_LABEL : C_DIM);

            // Price cell: the next tier's price where it is sold; where it is
            // earned instead, the series count toward it; nothing at the top.
            if (d.Label == TitleLadderRules.Label.Maxed || d.Reason == TitleLadderRules.Reason.NoRungs)
                UIFactory.SetTextRaw(e.txtPrice, "");
            else if (d.Reason == TitleLadderRules.Reason.EarnedByPlay)
            {
                UIFactory.SetTextRaw(e.txtPrice, $"{ln.games}/{d.Threshold}");
                UIFactory.SetColor(e.txtPrice, C_LABEL);
            }
            else
            {
                UIFactory.SetTextRaw(e.txtPrice, $"{d.Price}g");
                UIFactory.SetColor(e.txtPrice, d.Enabled ? C_GOLD : C_DIM);
            }

            PaintAction(e.btn, e.btnTxt, d);
            e.enabled = d.Enabled;

            string sig = $"held={d.Held} next={d.NextTier} label={d.Label} enabled={d.Enabled} reason={d.Reason} price={d.Price}";
            if (sig != e.sig)
            {
                e.sig = sig;
                Plugin.Log.LogInfo($"[LADDER] entry {ln.line}: {sig}");
            }
        }

        private static void PaintAction(GameObject btn, object txt, TitleLadderRules.Decision d)
        {
            if (btn == null) return;
            UIFactory.SetText(txt, ActionLabel(d));
            UIFactory.SetColor(txt, d.Enabled ? C_WHITE : C_BUY_OFF_TXT);
            UIFactory.SetBold(txt, true);
            UIFactory.SetImageColor(btn, d.Enabled ? C_BUY : C_BUY_OFF);
            // Both input paths: Button.interactable AND the raw-poll
            // ClickHandler (#141), or a disabled button stays clickable.
            NativeUI.SetButtonInteractable(btn, d.Enabled);
        }

        private static string EmptyText()
        {
            string e = ApiClient.TitleLaddersError;
            if (e == null) return I18n.Tr("Loading...");
            if (e == "route")
                // Named for what it is. The alternative — no entries and no
                // word — reads as a claim about the ACCOUNT, and it would be
                // false.
                return I18n.Tr("Ladders unavailable: this server does not serve the ladder route yet.");
            if (e == "empty")
                // A 404 the ROUTE itself answered, PROVED by the route's own
                // marker: the backend has no Player row for this account. It
                // used to render as the "route" line above, telling a new
                // player the service was broken.
                //
                // CORRECTED (Codex client r2 LOW): "every account until it
                // buys an entry rung" was the wrong account model — see the
                // class header. ApiClient.TitleLadderFailure now classifies on
                // the marker alone, so nothing reaching here is presumed.
                return I18n.Tr("No ladder yet - buy a title line in the Shop to start one.");
            if (e == "parse") return I18n.Tr("Ladders unavailable: the server's answer could not be read.");
            return I18n.Tr("Ladders unavailable: the server could not be reached.");
        }

        // ── the tier popup ───────────────────────────────────────────────

        /// <summary>The popup is a full-screen surface on the mod's persistent
        /// overlay canvas (NativeUI.OverlayRoot): a raycast-target backdrop
        /// that uGUI clicks stop at, and a centred box. It owns input while it
        /// is open (CompetitiveUI.OtherModalOwnsInput), so the Shop's raw-poll
        /// rows under it are blocked, and its own controls carry
        /// bypassModalBlock (NativeUI.MarkPopupChildrenInteractive).</summary>
        internal static bool PopupOpen { get { return popupGO != null; } }

        private static void OpenPopup(string lineId)
        {
            if (FindLine(Board, lineId) == null) return;
            try
            {
                HidePopup();
                var overlay = NativeUI.OverlayRoot;
                if (overlay == null) return;
                popupLine = lineId;
                popupFrame = Time.frameCount;
                popupGO = new GameObject("CR_TitleLadderPopup");
                popupGO.hideFlags = HideFlags.HideAndDontSave;
                popupGO.transform.SetParent(overlay, false);
                var rt = popupGO.AddComponent<RectTransform>();
                rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one;
                rt.offsetMin = Vector2.zero; rt.offsetMax = Vector2.zero;

                var bd = UIFactory.CreatePanel("BD", popupGO.transform, new Color(0f, 0f, 0f, 0.62f));
                var bdRT = bd.GetComponent<RectTransform>();
                bdRT.anchorMin = Vector2.zero; bdRT.anchorMax = Vector2.one;
                bdRT.offsetMin = Vector2.zero; bdRT.offsetMax = Vector2.zero;
                var bdImg = UIFactory.tImage != null ? bd.GetComponent(UIFactory.tImage) : null;
                if (bdImg != null)
                    UIFactory.tImage.GetProperty("raycastTarget", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance)?.SetValue(bdImg, true);
                var bdClick = bd.AddComponent<ClickHandler>();
                bdClick.bypassModalBlock = true;
                // A backdrop click closes; a press on the box does not (the
                // raw-poll backdrop sees every press inside its full-screen
                // rect), and neither does the mouse-down that opened the popup.
                bdClick.onClick = () =>
                {
                    if (Time.frameCount == popupFrame) return;
                    if (popupBox != null && NativeUI.PointerOverActive(popupBox)) return;
                    if (ClickGuard.Claim(bd)) HidePopup();
                };

                popupBox = UIFactory.CreatePanel("Box", popupGO.transform, C_BOX);
                var boxRT = popupBox.GetComponent<RectTransform>();
                boxRT.anchorMin = new Vector2(0.5f, 0.5f); boxRT.anchorMax = new Vector2(0.5f, 0.5f);
                boxRT.pivot = new Vector2(0.5f, 0.5f);
                float h = 720f;
                try
                {
                    var crt = overlay.GetComponent<RectTransform>();
                    if (crt != null && crt.rect.height > 200f) h = Mathf.Min(720f, crt.rect.height - 40f);
                }
                catch { }
                boxRT.sizeDelta = new Vector2(920f, h);
                UIFactory.AddVLG(popupBox, spacing: 6, padL: 24, padR: 24, padT: 16, padB: 16);
                // The box takes the height of what it holds. At a fixed 720 a
                // six-tier line left a third of the box empty under the footer.
                // The fitter sets the height from the layout group's preferred
                // height, which counts the ACTIVE tier rows only and the rule
                // sentence at its wrapped height. `h` above stays the size when
                // the fitter type cannot be resolved.
                try
                {
                    var tFit = UIFactory.tImage?.Assembly.GetType("UnityEngine.UI.ContentSizeFitter");
                    var pFit = tFit?.GetProperty("verticalFit", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                    if (tFit != null && pFit != null)
                        pFit.SetValue(popupBox.AddComponent(tFit), Enum.ToObject(pFit.PropertyType, 2));   // FitMode.PreferredSize
                }
                catch { }

                var head = new GameObject("Head");
                head.transform.SetParent(popupBox.transform, false);
                head.AddComponent<RectTransform>();
                UIFactory.AddHLG(head, spacing: 12, forceExpandH: true);
                UIFactory.AddLE(head, prefH: 36, flexH: 0);
                var kicker = UIFactory.CreateText("Kick", head.transform, I18n.Tr("Title Ladders"), 15f, C_LABEL,
                    UIFactory.AlignMidLeft, sizeDelta: new Vector2(150, 34));
                UIFactory.SetBold(kicker, true);
                UIFactory.FitOneLine(kicker);
                popTitle = UIFactory.CreateText("Title", head.transform, "", 26f, C_GOLD,
                    UIFactory.AlignMidLeft, sizeDelta: new Vector2(500, 34));
                UIFactory.SetBold(popTitle, true);
                UIFactory.FitOneLine(popTitle);
                UIFactory.SetFlexW((popTitle as Component)?.gameObject, 1f);
                var close = UIFactory.CreateButton("Close", head.transform, I18n.Tr("Close"), 15f, C_WHITE, C_BTN,
                    () => { if (Time.frameCount != popupFrame) HidePopup(); }, sizeDelta: new Vector2(120, 30));
                UIFactory.AddLE(close, prefW: 120, prefH: 30, flexW: 0, flexH: 0);

                popHeld = UIFactory.CreateText("Held", popupBox.transform, "", 17f, C_WHITE,
                    UIFactory.AlignMidLeft, sizeDelta: new Vector2(870, 26));
                UIFactory.SetBold(popHeld, true);
                UIFactory.FitOneLine(popHeld);

                // The rule, in one sentence. It is the only place that says
                // progress needs a rung WORN, which is the single fact a
                // player cannot deduce from the numbers.
                var expl = UIFactory.CreateText("Expl", popupBox.transform,
                    I18n.Tr("Buy the first rung of a line in the Shop and wear it. Every ranked series you finish while a rung of that line is worn counts one toward the next rung."),
                    14f, C_LABEL, sizeDelta: new Vector2(870, 20));
                UIFactory.SetTextAutoHeight(expl, 20f);

                popFill = UIFactory.CreateFillBar("Bar", popupBox.transform, C_BARBG, C_GOLD, 8f);
                popCaption = UIFactory.CreateText("Cap", popupBox.transform, "", 14f, C_LABEL,
                    UIFactory.AlignMidLeft, sizeDelta: new Vector2(870, 20));
                UIFactory.FitOneLine(popCaption);

                var list = new GameObject("Tiers");
                list.transform.SetParent(popupBox.transform, false);
                list.AddComponent<RectTransform>();
                UIFactory.AddVLG(list, spacing: 4);
                UIFactory.AddLE(list, flexH: 0);
                popRows = new TierRow[MAX_RUNGS];
                for (int i = 0; i < MAX_RUNGS; i++) popRows[i] = BuildTierRow(list.transform, i);

                var foot = new GameObject("Foot");
                foot.transform.SetParent(popupBox.transform, false);
                foot.AddComponent<RectTransform>();
                UIFactory.AddHLG(foot, spacing: 12, forceExpandH: true);
                UIFactory.AddLE(foot, prefH: 36, flexH: 0);
                popReason = UIFactory.CreateText("Why", foot.transform, "", 15f, C_LABEL,
                    UIFactory.AlignMidLeft, sizeDelta: new Vector2(600, 32));
                UIFactory.SetBold(popReason, true);
                UIFactory.FitOneLine(popReason);
                UIFactory.SetFlexW((popReason as Component)?.gameObject, 1f);
                popupAction = UIFactory.CreateButton("Act", foot.transform, I18n.Tr("Buy"), 15f, C_WHITE, C_BUY,
                    () => OnActionClicked(popupLine, true), sizeDelta: new Vector2(160, 32));
                UIFactory.AddLE(popupAction, prefW: 160, prefH: 32, flexW: 0, flexH: 0);
                popActionTxt = UIFactory.GetButtonText(popupAction);
                UIFactory.FitOneLine(popActionTxt);

                popMsg = UIFactory.CreateText("Msg", popupBox.transform, "", 14f, C_LABEL,
                    UIFactory.AlignMidLeft, sizeDelta: new Vector2(870, 22));
                UIFactory.FitOneLine(popMsg);

                // Every control above carries bypassModalBlock: the popup is a
                // modal (PopupOpen feeds CompetitiveUI.OtherModalOwnsInput),
                // and the block would otherwise kill its own buttons (bug 230).
                // The rows are bound on repaint, never rebuilt, so one pass
                // covers every handler the popup will ever have.
                NativeUI.MarkPopupChildrenInteractive(popupGO);
                lastMsg = null;
                RefreshPopup();
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[LADDER] popup failed: {ex.Message}");
                HidePopup();
            }
        }

        private static TierRow BuildTierRow(Transform parent, int idx)
        {
            var tr = new TierRow();
            tr.root = UIFactory.CreatePanel($"TLT{idx}", parent, C_CARD);
            UIFactory.AddHLG(tr.root, spacing: 10, padL: 10, padR: 10, padT: 4, padB: 4, forceExpandH: true);
            UIFactory.AddLE(tr.root, prefH: 36, flexH: 0);
            tr.txtTier = UIFactory.CreateText("Ti", tr.root.transform, "", 15f, C_LABEL,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(90, 28));
            UIFactory.SetBold(tr.txtTier, true);
            UIFactory.FitOneLine(tr.txtTier);
            tr.txtName = UIFactory.CreateText("Nm", tr.root.transform, "", 17f, C_WHITE,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(280, 28));
            UIFactory.SetBold(tr.txtName, true);
            UIFactory.FitOneLine(tr.txtName);
            UIFactory.SetFlexW((tr.txtName as Component)?.gameObject, 1f);
            tr.txtReq = UIFactory.CreateText("Rq", tr.root.transform, "", 15f, C_LABEL,
                UIFactory.AlignMidRight, sizeDelta: new Vector2(200, 28));
            UIFactory.SetBold(tr.txtReq, true);
            UIFactory.FitOneLine(tr.txtReq);
            tr.txtState = UIFactory.CreateText("St", tr.root.transform, "", 14f, C_LABEL,
                UIFactory.AlignMidRight, sizeDelta: new Vector2(140, 28));
            UIFactory.SetBold(tr.txtState, true);
            UIFactory.FitOneLine(tr.txtState);
            // A fixed-width slot so the columns line up whether or not the row
            // has a Set Active button.
            var slot = new GameObject("Slot");
            slot.transform.SetParent(tr.root.transform, false);
            slot.AddComponent<RectTransform>();
            UIFactory.AddLE(slot, minW: 120, prefW: 120, prefH: 26, flexW: 0, flexH: 0);
            tr.wearBtn = UIFactory.CreateButton($"TLW{idx}", slot.transform, I18n.Tr("Set Active"), 13f, C_WHITE, C_WEAR,
                () => OnWearClicked(tr), sizeDelta: new Vector2(120, 26));
            tr.wearTxt = UIFactory.GetButtonText(tr.wearBtn);
            UIFactory.FitOneLine(tr.wearTxt);
            tr.wearBtn.SetActive(false);
            tr.root.SetActive(false);
            return tr;
        }

        /// <summary>Closes the popup. Called by its own close controls, on a tab
        /// switch, and from NativeUI.TeardownOverlaySurfaces on EVERY page close
        /// and recovery path (#369): the popup is parented to the persistent
        /// overlay canvas and outlives the page. SetActive(false) FIRST — the
        /// Destroy is deferred to the end of the frame, and an inactive object's
        /// raw-poll handlers never run, so nothing under a closed popup can
        /// still buy for the rest of the frame (#369 rule b).</summary>
        internal static void HidePopup()
        {
            if (popupGO == null) return;
            var go = popupGO;
            popupGO = null; popupBox = null; popupAction = null;
            popTitle = popHeld = popCaption = popReason = popMsg = popActionTxt = null;
            popFill = null; popRows = null; popupLine = null;
            popupFrame = Time.frameCount;
            try { go.SetActive(false); } catch { }
            try { UnityEngine.Object.Destroy(go); } catch { }
            Plugin.Log.LogInfo("[LADDER] popup closed");
            try { NativeUI.MarkDirty(); } catch { }
        }

        private static void RefreshPopup()
        {
            if (popupGO == null) return;
            var ln = FindLine(Board, popupLine);
            if (ln == null) { HidePopup(); return; }   // the line left the answer (identity change, board dropped)
            List<TitleLadderRules.Rung> rungs;
            Dictionary<string, int> listing;
            var d = DecideFor(ln, out rungs, out listing);

            UIFactory.SetText(popTitle, ln.name ?? ln.line);
            int hi = TitleLadderRules.HeldRungIndex(rungs, d.Held);
            var held = hi >= 0 && hi < ln.rungs.Count ? ln.rungs[hi] : null;
            ApiClient.TitleLadderRung worn = null;
            for (int i = 0; i < ln.rungs.Count; i++) if (ln.rungs[i] != null && ln.rungs[i].active) worn = ln.rungs[i];
            string heldTxt = held != null
                ? I18n.TrF("Current tier: {0} - {1}", d.Held, LadderName(held.name))
                : I18n.Tr("Not started");
            string wornTxt = worn != null
                ? "<color=" + Hex(C_OK) + ">" + I18n.TrF("Worn: {0}", LadderName(worn.name)) + "</color>"
                : (held != null ? I18n.Tr("Owned - not worn") : "");
            UIFactory.SetTextRaw(popHeld, wornTxt.Length > 0 ? heldTxt + "     " + wornTxt : heldTxt);

            UIFactory.SetFill(popFill, TitleLadderRules.Progress(rungs, ln.games, d));
            UIFactory.SetTextRaw(popCaption, Caption(ln, d));
            UIFactory.SetColor(popCaption, d.Held > 0 ? (d.NextTier == 0 ? C_GOLD : C_LABEL) : C_DIM);

            // Every tier in order. The answer sends them in order; this sorts
            // anyway, stably, so the popup never depends on it.
            var order = new List<int>(ln.rungs.Count);
            for (int i = 0; i < ln.rungs.Count; i++) if (ln.rungs[i] != null) order.Add(i);
            order.Sort((a, b) => ln.rungs[a].tier != ln.rungs[b].tier ? ln.rungs[a].tier.CompareTo(ln.rungs[b].tier) : a.CompareTo(b));
            if (order.Count > MAX_RUNGS)
                Plugin.Log.LogWarning($"[LADDER] {ln.line}: {order.Count} rungs for {MAX_RUNGS} popup rows (raise MAX_RUNGS)");
            var states = new List<string>();
            for (int k = 0; k < MAX_RUNGS; k++)
            {
                var row = popRows[k];
                if (row == null) continue;
                if (k >= order.Count) { row.rung = null; row.owned = false; row.root.SetActive(false); continue; }
                int idx = order[k];
                var r = ln.rungs[idx];
                var rr = rungs[idx];
                var st = TitleLadderRules.StateOf(rr, d.Held, d.NextTier);
                states.Add(st.ToString());
                row.rung = r;
                row.owned = rr.Owned;
                row.root.SetActive(true);
                PaintTierRow(row, r, rr, st, listing);
            }

            UIFactory.SetTextRaw(popReason, PopupReason(ln, d));
            UIFactory.SetColor(popReason, d.Enabled ? C_LABEL : C_WARN);
            PaintAction(popupAction, popActionTxt, d);
            UIFactory.SetTextRaw(popMsg, lastMsg ?? "");

            string sig = $"line={ln.line} tiers={order.Count} held={d.Held} next={d.NextTier} label={d.Label} enabled={d.Enabled} reason={d.Reason} rows={string.Join(",", states.ToArray())}";
            if (sig != popSig)
            {
                popSig = sig;
                Plugin.Log.LogInfo("[LADDER] popup: " + sig);
            }
        }

        private static string popSig;

        private static void PaintTierRow(TierRow row, ApiClient.TitleLadderRung r, TitleLadderRules.Rung rr,
                                         TitleLadderRules.TierState st, Dictionary<string, int> listing)
        {
            UIFactory.SetTextRaw(row.txtTier, I18n.TrF("Tier {0}", r.tier));
            Color rc = RungColor(r);
            UIFactory.SetText(row.txtName, r.name ?? r.sku);
            UIFactory.SetColor(row.txtName, rr.Owned ? Color.Lerp(rc, Color.white, 0.35f) : C_DIM);

            // Requirement: the price where the tier is sold (the listing's,
            // which is what the purchase endpoint charges, when it lists the
            // rung), the series threshold where it is earned.
            int listed;
            if (r.price > 0)
                UIFactory.SetTextRaw(row.txtReq, $"{(listing != null && r.sku != null && listing.TryGetValue(r.sku, out listed) ? listed : r.price)}g");
            else
                UIFactory.SetTextRaw(row.txtReq, I18n.TrF("Earned at {0} series", r.threshold));
            UIFactory.SetColor(row.txtReq, rr.Owned ? C_DIM : (r.price > 0 ? C_GOLD : C_LABEL));

            string state; Color sc;
            switch (st)
            {
                case TitleLadderRules.TierState.Current: state = I18n.Tr("Current tier"); sc = C_GOLD; break;
                case TitleLadderRules.TierState.Owned: state = I18n.Tr("Owned"); sc = C_OK; break;
                case TitleLadderRules.TierState.Next: state = I18n.Tr("Next tier"); sc = C_WHITE; break;
                default: state = I18n.Tr("Locked"); sc = C_DIM; break;
            }
            UIFactory.SetTextRaw(row.txtState, state);
            UIFactory.SetColor(row.txtState, sc);
            // The held tier is the highlighted row.
            UIFactory.SetImageColor(row.root, st == TitleLadderRules.TierState.Current ? Dimmed(rc, 0.45f) : C_CARD);

            bool wearable = rr.Owned;
            row.wearBtn.SetActive(wearable);
            if (wearable)
            {
                bool canWear = !r.active && r.item_id > 0;
                UIFactory.SetText(row.wearTxt, r.active ? I18n.Tr("In use") : I18n.Tr("Set Active"));
                UIFactory.SetImageColor(row.wearBtn, r.active ? C_WORN : (canWear ? C_WEAR : C_BUY_OFF));
                UIFactory.SetColor(row.wearTxt, r.active || canWear ? C_WHITE : C_BUY_OFF_TXT);
                NativeUI.SetButtonInteractable(row.wearBtn, canWear);
            }
        }

        /// <summary>The popup's progress caption, from the SAME decision as its
        /// button: the tier the button is about is the tier the caption
        /// counts toward.</summary>
        private static string Caption(ApiClient.TitleLadderLine ln, TitleLadderRules.Decision d)
        {
            // NOT STARTED says what starts the line, and draws an empty bar
            // (TitleLadderRules.Progress). The server reports games=0/tier=1
            // for a KNOWN account with no progress row, and a "0 / 10 to Rat
            // Leader" caption off those numbers would promise a countdown the
            // account is not in.
            if (d.Held <= 0)
            {
                ApiClient.TitleLadderRung entry = null;
                for (int i = 0; i < ln.rungs.Count; i++)
                    if (ln.rungs[i] != null && ln.rungs[i].tier <= 1) { entry = ln.rungs[i]; break; }
                return entry != null
                    ? I18n.TrF("Not started - buy {0} in the Shop to begin this line.", LadderName(entry.name))
                    : I18n.Tr("Not started.");
            }
            if (d.NextTier == 0) return I18n.TrF("{0} series - top of the line.", ln.games);
            string names = TierNames(ln, d.NextTier);
            return string.IsNullOrEmpty(names)
                ? I18n.TrF("{0} series - {1} to go.", ln.games, d.SeriesToGo)
                : I18n.TrF("{0} series - {1} to go to {2}.", ln.games, d.SeriesToGo, names);
        }

        /// <summary>The popup footer's line beside its button: why it is
        /// disabled, spelled out.</summary>
        private static string PopupReason(ApiClient.TitleLadderLine ln, TitleLadderRules.Decision d)
        {
            if (d.Enabled || d.Label == TitleLadderRules.Label.Maxed) return "";
            if (d.Reason == TitleLadderRules.Reason.EarnedByPlay)
            {
                string names = TierNames(ln, d.NextTier);
                if (!string.IsNullOrEmpty(names))
                    return I18n.TrF("{0} is earned at {1} series on this line.", names, d.Threshold);
            }
            return ReasonText(d) ?? "";
        }

        // ── broadcast-seat lever ─────────────────────────────────────────

        /// <summary>Broadcast-seat lever only: Plugin.TickTestOpenTab calls this
        /// behind BroadcastMode.IsBroadcastIdentity, for screenshots of surfaces
        /// synthetic clicks cannot reach (#420). The directive is everything
        /// after "4:catN:" in TestOpenTab:
        ///
        ///   fixture[:line]  read BepInEx/config/scr-ladder-fixture.json through
        ///                   the REAL parser (ApiClient.ParseTitleLadders) as a
        ///                   local board, then optionally open a line's popup.
        ///                   Nothing is ever bought or worn from a local board.
        ///   ladder:line     open a line's popup from the board in hand.
        ///   close           close the popup.
        ///   live            drop the local board.
        ///
        /// The fixture is a file the operator writes on that seat; no ladder
        /// answer ships in this assembly (see the closing note).</summary>
        internal static void DevDirective(string directive)
        {
            try
            {
                string d = (directive ?? "").Trim();
                if (d.Length == 0) return;
                int c = d.IndexOf(':');
                string verb = (c < 0 ? d : d.Substring(0, c)).Trim().ToLowerInvariant();
                string arg = c < 0 ? "" : d.Substring(c + 1).Trim();
                if (verb == "fixture")
                {
                    string path = Path.Combine(BepInEx.Paths.ConfigPath, "scr-ladder-fixture.json");
                    if (!File.Exists(path)) { Plugin.Log.LogWarning("[LADDER] dev: no fixture at " + Path.GetFileName(path)); return; }
                    var b = ApiClient.ParseTitleLadders(File.ReadAllText(path));
                    if (b == null) { Plugin.Log.LogWarning("[LADDER] dev: the fixture did not parse"); return; }
                    HidePopup();
                    devBoard = b;
                    Plugin.Log.LogInfo($"[LADDER] dev: local board loaded, {b.lines.Count} lines");
                    if (arg.Length > 0) OpenPopup(arg);
                }
                else if (verb == "ladder") OpenPopup(arg);
                else if (verb == "close") HidePopup();
                else if (verb == "live") { HidePopup(); devBoard = null; Plugin.Log.LogInfo("[LADDER] dev: local board dropped"); }
                else Plugin.Log.LogWarning("[LADDER] dev: unknown directive " + verb);
                if (arg.Length > 0 && (verb == "fixture" || verb == "ladder") && !PopupOpen)
                    Plugin.Log.LogWarning("[LADDER] dev: no line " + arg + " on the board");
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[LADDER] dev directive failed: " + ex.Message); }
            try { NativeUI.MarkDirty(); } catch { }
        }

        // ── parser self-check: REMOVED FROM THE SHIPPED PATH ─────────────
        //
        // A one-shot fixture used to run here the first time the Titles tab
        // opened, behind a default-off Debug lever. Round two put the lever
        // on it; round three removes the fixture altogether (Codex client
        // r1 LOW / r2 PARTIAL, TitleLaddersUI.cs:239).
        //
        // The lever was not the finding. A check that only a developer who
        // knows it exists can turn on runs in no build anybody ships and in
        // no gate anybody reads, so it was decoration inside a release
        // artifact — synthetic JSON and assertion text in the literal heap
        // of every player's DLL, which is also the heap the privacy scan
        // reads. Its absence is now checkable at the ARTIFACT: the release
        // DLL must carry no `title_ladder_rat_4_queen`, and that scan can
        // fail, which the lever's default could not.
        //
        // The section's own rules follow the same rule: their cases live in
        // tools/client-rules-harness/TitleLadderRulesSelfTest.cs, the
        // harness-only half of TitleLadderRules, and never in this assembly.
        // The broadcast lever above reads a fixture from DISK on one seat; it
        // carries no answer of its own.
        //
        // WHAT IT WAS GUARDING, kept as a statement so the next author does
        // not re-derive it the hard way: a flat whole-body JSON reader
        // answers the LINE's `name`, `tier`, `sku` and `threshold` for every
        // RUNG that repeats those keys (#608), and every shape assertion
        // still passes. ApiClient.ParseTitleLadderRung must therefore read
        // each field from the rung OBJECT it was handed and never from the
        // enclosing text; test_title_ladders_client.py holds that contract.
    }
}
