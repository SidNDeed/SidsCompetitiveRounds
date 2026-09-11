using System;
using System.Collections.Generic;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Player Cards (Sept 10 batch, WP-E): the Collection tab (Open
    /// Packs / Binder / Get packs), the Settings-tab consent rows and the
    /// persisted open intent with result recovery. Frames, foil and signed
    /// marks are drawn programmatically. NativeUI owns the tab slot and calls
    /// in: BuildInto (tab body), Refresh (dirty repaint), OnTabEntered (fetch
    /// chain), MaybeTick (per-frame ticker), BuildSettingsRows /
    /// RefreshSettingsRows (Settings tab).
    ///
    /// Money rule: a purchase writes its intent (kind, nonce, pay, price) to
    /// the config BEFORE the request leaves and clears it only after the
    /// committed answer was shown. A lost answer is recovered through
    /// /pc/packs/result with the same nonce (the server answers the committed
    /// row); a 404 there after 10 minutes means no claim ever committed and
    /// the nonce is retired. Until the intent is cleared no second purchase
    /// starts, so a retry can never buy twice.</summary>
    internal static class PlayerCardsUI
    {
        private static readonly Color C_PANEL = new Color(0.10f, 0.11f, 0.14f, 0.92f);
        private static readonly Color C_CARD = new Color(0.07f, 0.08f, 0.10f, 0.97f);
        private static readonly Color C_WHITE = Color.white;
        private static readonly Color C_SUB = new Color(0.8f, 0.85f, 1f);
        private static readonly Color C_LABEL = new Color(0.7f, 0.7f, 0.75f);
        private static readonly Color C_DIM = new Color(0.5f, 0.5f, 0.55f);
        private static readonly Color C_GOLD = new Color(1f, 0.85f, 0.3f);
        private static readonly Color C_BTN = new Color(0.18f, 0.20f, 0.26f, 0.92f);
        private static readonly Color C_BTNACT = new Color(0.22f, 0.38f, 0.65f, 0.95f);
        private static readonly Color C_BUY = new Color(0.15f, 0.45f, 0.25f, 0.95f);
        private static readonly Color C_DANGER = new Color(0.50f, 0.15f, 0.15f, 0.95f);
        private static readonly Color C_SIGN = new Color(1f, 0.95f, 0.75f);
        private static readonly Color C_OK = new Color(0.55f, 1f, 0.55f);
        private static readonly Color C_WARN = new Color(1f, 0.85f, 0.3f);

        private enum View { Open, Binder, Info }
        private static View view = View.Open;
        private const int TILES_PER_ROW = 4, BINDER_ROWS = 8;   // 4 x 236 px fits a 1280-wide layout
        private const int REVEAL_TILES = 5;                     // one pack = five prints
        private const int PAGE = TILES_PER_ROW * BINDER_ROWS;
        private const float TILE_W = 236f, TILE_H = 184f;
        private const int MAX_PACK_ROWS = 12;
        private const float INTENT_NOT_FOUND_RETIRE_S = 600f;     // design §6: not-found after 10 min = never claimed
        private const float INTENT_HARD_RETIRE_S = 3600f;         // an intent that keeps failing for an hour is shown and dropped

        private class Tile
        {
            public GameObject root, actions, btnDiscard, btnDupes;
            public object txtName, txtTitle, txtL1, txtL2, txtL3, txtL4, txtMark, txtSign, btnDiscardTxt, btnDupesTxt;
            public ApiClient.PcPrint print;   // the row's CURRENT binding — callbacks read this, never a captured print (#265)
            public int dupes;
        }
        private class PackRow { public GameObject root, btnOpen; public object txt; public ApiClient.PcUnopened pack; }

        // tab
        private static GameObject tabRoot, openRoot, binderRoot, infoRoot;
        private static readonly GameObject[] viewBtns = new GameObject[3];
        private static readonly object[] viewTxts = new object[3];
        private static object txtBalance, txtStatus;
        // open packs
        private static object txtDaily, txtPaid, txtPool, txtLastHdr, txtPacksHdr;
        private static GameObject btnDaily, btnBuyGold, btnBuyShards, lastStrip, packsBox;
        private static object btnDailyTxt, btnBuyGoldTxt, btnBuyShardsTxt;
        private static Tile[] revealTiles;
        private static PackRow[] packRows;
        // binder
        private static object txtBinderHdr, txtBinderPage;
        private static GameObject btnPrev, btnNext;
        private static Tile[] binderTiles;
        private static GameObject[] binderRows;
        private static int binderPage;
        private static string armedPrintId; private static bool armedDupes; private static float armedAt;
        private static bool discardInFlight; private static readonly List<string> discardQueue = new List<string>();
        private static int discardDone, discardShards;
        // info
        private static object txtInfo;
        // state
        private static bool openInFlight, claimInFlight, recoverInFlight;
        private static float openAt, claimAt, recoverAt, tickAt, meRefreshAt;
        private static ApiClient.PcPackAnswer lastPack;
        private static string lastMsg; private static Color lastMsgColor; private static float lastMsgAt;
        // settings rows
        private static GameObject btnBeCard, btnPublic, btnAnnounce;
        private static object btnBeCardTxt, btnPublicTxt, btnAnnounceTxt;
        private static bool setInFlight; private static float setAt;

        // ── helpers ──────────────────────────────────────────────────────────
        private static string LocalId()
        {
            var id = MatchTracker.LocalSteamId;
            return string.IsNullOrEmpty(id) || id == "unknown" ? null : id;
        }
        private static bool SessionReady => !string.IsNullOrEmpty(SteamAuth.SessionToken);
        private static string NewNonce() => Guid.NewGuid().ToString("N");
        private static float Now => Time.realtimeSinceStartup;

        private static void Say(string msg, Color? color = null)
        {
            lastMsg = msg; lastMsgColor = color ?? C_LABEL; lastMsgAt = Now;
            NativeUI.MarkDirty();
        }

        private static string SafeName(ApiClient.PcPrint p)
        {
            if (p == null) return "";
            if (p.subject_deleted && string.IsNullOrEmpty(p.subject_name)) return I18n.Tr("[deleted]");
            string n = p.subject_name ?? "";
            try { n = GameStateWatcher.StripRichText(n); } catch { }
            if (n.Length > 24) n = n.Substring(0, 24);
            return string.IsNullOrEmpty(n) ? I18n.Tr("[deleted]") : n;
        }

        private static int RarityOrder(string r)
        {
            switch (r) { case "legendary": return 0; case "epic": return 1; case "rare": return 2; case "uncommon": return 3; default: return 4; }
        }
        private static string RarityLabel(string r)
        {
            switch (r)
            {
                case "legendary": return I18n.Tr("Legendary");
                case "epic": return I18n.Tr("Epic");
                case "rare": return I18n.Tr("Rare");
                case "uncommon": return I18n.Tr("Uncommon");
                default: return I18n.Tr("Common");
            }
        }
        private static Color FrameColor(string r, bool foil)
        {
            Color c;
            switch (r)
            {
                case "legendary": c = new Color(1f, 0.72f, 0.18f, 1f); break;
                case "epic": c = new Color(0.62f, 0.32f, 0.92f, 1f); break;
                case "rare": c = new Color(0.25f, 0.55f, 0.98f, 1f); break;
                case "uncommon": c = new Color(0.30f, 0.72f, 0.38f, 1f); break;
                default: c = new Color(0.50f, 0.52f, 0.58f, 1f); break;
            }
            // Foil: the same hue lifted towards white, so a foil copy reads as a
            // brighter frame beside its plain twin.
            return foil ? Color.Lerp(c, Color.white, 0.35f) : c;
        }
        private static string FaceKey(ApiClient.PcPrint p) => $"{p.card_id}|{p.rarity}|{(p.foil ? 1 : 0)}|{(p.signed ? 1 : 0)}";
        private static string DateOnly(string iso) => string.IsNullOrEmpty(iso) ? "" : (iso.Length >= 10 ? iso.Substring(0, 10) : iso);

        private static string ReasonText(string code)
        {
            switch (code)
            {
                case "session_required": return I18n.Tr("Player Cards need your Steam sign-in - try again in a moment");
                case "price_changed": return I18n.Tr("The pack price changed - check the new price and try again");
                case "insufficient_gold": return I18n.Tr("Not enough gold for a pack");
                case "insufficient_shards": return I18n.Tr("Not enough shards for a pack");
                case "daily_cap": return I18n.Tr("Daily limit reached - paid packs reset at midnight UTC");
                case "pool_empty": return I18n.Tr("Nobody is in the card pool right now - try again later");
                case "pool_changed": return I18n.Tr("The pool changed while your pack was opening - nothing was charged, try again");
                case "in_progress": return I18n.Tr("That pack is still opening - hold on");
                case "voided": return I18n.Tr("That pack was voided - the series it came from was reversed");
                case "already_claimed": return I18n.Tr("Today's free pack is already claimed");
                case "not_owned": return I18n.Tr("That card is no longer in your collection");
                case "stale_revision": return I18n.Tr("Your Player Cards settings changed elsewhere - refreshed, try again");
                case "no_edition": return I18n.Tr("Player Cards are not open yet - no edition is running");
                case "no-consent": return I18n.Tr("Grant data consent first (Settings)");
                case "outdated": return I18n.Tr("Update the mod first");
                case "transport": return I18n.Tr("No answer from the server - try again in a moment");
                default: return I18n.Tr("The server refused that - try again in a moment");
            }
        }

        // ── open intent (persisted BEFORE the request, cleared AFTER the answer) ──
        private static bool HasIntent() { try { return Plugin.PcOpenIntent != null && !string.IsNullOrEmpty(Plugin.PcOpenIntent.Value); } catch { return false; } }
        private static void WriteIntent(string kind, string reference, string pay, int price)
        {
            long unix = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            try { Plugin.PcOpenIntent.Value = $"{kind}|{reference}|{pay}|{price}|{unix}"; }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PC] intent write failed: {ex.Message}"); }
        }
        private static void ClearIntent() { try { if (Plugin.PcOpenIntent != null) Plugin.PcOpenIntent.Value = ""; } catch { } }
        private static bool ReadIntent(out string kind, out string reference, out float ageS)
        {
            kind = null; reference = null; ageS = 0f;
            string v = null;
            try { v = Plugin.PcOpenIntent?.Value; } catch { }
            if (string.IsNullOrEmpty(v)) return false;
            var parts = v.Split('|');
            if (parts.Length < 5) { ClearIntent(); return false; }
            kind = parts[0]; reference = parts[1];
            long unix; if (!long.TryParse(parts[4], out unix)) unix = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            ageS = (float)(DateTimeOffset.UtcNow.ToUnixTimeSeconds() - unix);
            if ((kind != "buy" && kind != "pack") || string.IsNullOrEmpty(reference)) { ClearIntent(); return false; }
            return true;
        }

        // ── NativeUI entry points ────────────────────────────────────────────
        internal static void OnTabEntered()
        {
            var id = LocalId();
            if (id == null) return;
            ApiClient.FetchPlayerStats(id);
            ApiClient.FetchPcMe(id, true);
            ApiClient.FetchPcCollection(id);
            meRefreshAt = Time.unscaledTime + 30f;
            MaybeRecover(true);
        }

        internal static void MaybeTick(bool onTab)
        {
            if (Time.unscaledTime < tickAt) return;
            tickAt = Time.unscaledTime + 2f;
            var id = LocalId();
            if (id == null) return;
            if (HasIntent()) MaybeRecover(false);
            if (!onTab) return;
            if (Time.unscaledTime >= meRefreshAt) { meRefreshAt = Time.unscaledTime + 30f; ApiClient.FetchPcMe(id, true); }
            if (armedPrintId != null && Now - armedAt > 6f) { armedPrintId = null; NativeUI.MarkDirty(); }
            if (lastMsg != null && Now - lastMsgAt > 15f) { lastMsg = null; NativeUI.MarkDirty(); }
            if (openInFlight && Now - openAt > 25f) { openInFlight = false; NativeUI.MarkDirty(); }
            if (claimInFlight && Now - claimAt > 25f) { claimInFlight = false; NativeUI.MarkDirty(); }
        }

        internal static void BuildInto(Transform parent)
        {
            view = View.Open; binderPage = 0; armedPrintId = null;
            tabRoot = new GameObject("PcRoot");
            tabRoot.transform.SetParent(parent, false);
            tabRoot.AddComponent<RectTransform>();
            UIFactory.AddVLG(tabRoot, spacing: 6);
            UIFactory.AddLE(tabRoot, flexH: 1);

            var header = new GameObject("PcHdr");
            header.transform.SetParent(tabRoot.transform, false);
            header.AddComponent<RectTransform>();
            UIFactory.AddHLG(header, spacing: 14, forceExpandH: true);
            UIFactory.AddLE(header, prefH: 32, flexH: 0);
            UIFactory.CreateText("PcTitle", header.transform, "Player Cards", 22f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(300, 30));
            var sp = new GameObject("PcSp"); sp.transform.SetParent(header.transform, false); sp.AddComponent<RectTransform>(); UIFactory.AddLE(sp, flexW: 1);
            txtBalance = UIFactory.CreateText("PcBal", header.transform, "", 16f, C_GOLD, UIFactory.AlignMidRight, sizeDelta: new Vector2(420, 30));
            UIFactory.SetBold(txtBalance, true);

            // view bar (same shape as the Shop's category bar)
            var bar = new GameObject("PcViews");
            bar.transform.SetParent(tabRoot.transform, false);
            bar.AddComponent<RectTransform>();
            UIFactory.AddHLG(bar, spacing: 6, forceExpandH: true);
            UIFactory.AddLE(bar, prefH: 30, minH: 30, flexH: 0);
            string[] names = { "Open Packs", "Binder", "Get packs" };
            for (int i = 0; i < 3; i++)
            {
                int idx = i;
                var b = UIFactory.CreateButton($"PcView{i}", bar.transform, names[i], 14f, C_LABEL, C_BTN,
                    () => { view = (View)idx; NativeUI.MarkDirty(); }, sizeDelta: new Vector2(0, 26));
                if (UIFactory.tLE != null)
                {
                    var el = b.GetComponent(UIFactory.tLE);
                    if (el != null) UnityEngine.Object.Destroy(el as UnityEngine.Object);
                }
                UIFactory.AddLE(b, prefH: 26, minH: 26, flexW: 1, flexH: 0);
                viewBtns[i] = b; viewTxts[i] = UIFactory.GetButtonText(b);
            }
            txtStatus = UIFactory.CreateText("PcStatus", tabRoot.transform, "", 14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(1000, 22));

            BuildOpenView(tabRoot.transform);
            BuildBinderView(tabRoot.transform);
            BuildInfoView(tabRoot.transform);
        }

        private static void BuildOpenView(Transform parent)
        {
            openRoot = new GameObject("PcOpen");
            openRoot.transform.SetParent(parent, false);
            openRoot.AddComponent<RectTransform>();
            UIFactory.AddVLG(openRoot, spacing: 6);
            UIFactory.AddLE(openRoot, flexH: 1);
            var sv = UIFactory.CreateScrollView("PcOpenSV", openRoot.transform, spacing: 8);
            UIFactory.AddLE(sv.scrollGO, flexH: 1);
            var c = sv.content.transform;

            // daily
            var box1 = UIFactory.CreatePanel("PcDailyBox", c, C_PANEL);
            UIFactory.AddVLG(box1, spacing: 6, padL: 12, padR: 12, padT: 8, padB: 8);
            UIFactory.AddLE(box1, flexH: 0);
            UIFactory.CreateText("PcDailyHdr", box1.transform, "Free pack", 17f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 24));
            var r1 = new GameObject("PcDailyRow"); r1.transform.SetParent(box1.transform, false); r1.AddComponent<RectTransform>();
            UIFactory.AddHLG(r1, spacing: 12, forceExpandH: true); UIFactory.AddLE(r1, prefH: 30, flexH: 0);
            btnDaily = UIFactory.CreateButton("PcDailyBtn", r1.transform, "Claim today's free pack", 14f, C_WHITE, C_BUY, ClaimDaily, sizeDelta: new Vector2(260, 28));
            btnDailyTxt = UIFactory.GetButtonText(btnDaily);
            txtDaily = UIFactory.CreateText("PcDailyTxt", r1.transform, "", 14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(600, 28));

            // buy
            var box2 = UIFactory.CreatePanel("PcBuyBox", c, C_PANEL);
            UIFactory.AddVLG(box2, spacing: 6, padL: 12, padR: 12, padT: 8, padB: 8);
            UIFactory.AddLE(box2, flexH: 0);
            UIFactory.CreateText("PcBuyHdr", box2.transform, "Open a pack", 17f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 24));
            var r2 = new GameObject("PcBuyRow"); r2.transform.SetParent(box2.transform, false); r2.AddComponent<RectTransform>();
            UIFactory.AddHLG(r2, spacing: 12, forceExpandH: true); UIFactory.AddLE(r2, prefH: 30, flexH: 0);
            btnBuyGold = UIFactory.CreateButton("PcBuyGold", r2.transform, "", 14f, C_WHITE, C_BUY, () => BeginBuy("gold"), sizeDelta: new Vector2(220, 28));
            btnBuyGoldTxt = UIFactory.GetButtonText(btnBuyGold);
            btnBuyShards = UIFactory.CreateButton("PcBuyShards", r2.transform, "", 14f, C_WHITE, C_BUY, () => BeginBuy("shards"), sizeDelta: new Vector2(220, 28));
            btnBuyShardsTxt = UIFactory.GetButtonText(btnBuyShards);
            txtPaid = UIFactory.CreateText("PcPaid", r2.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(420, 28));
            txtPool = UIFactory.CreateText("PcPool", box2.transform, "", 13f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 20));

            // packs waiting
            packsBox = UIFactory.CreatePanel("PcPacksBox", c, C_PANEL);
            UIFactory.AddVLG(packsBox, spacing: 4, padL: 12, padR: 12, padT: 8, padB: 8);
            UIFactory.AddLE(packsBox, flexH: 0);
            txtPacksHdr = UIFactory.CreateText("PcPacksHdr", packsBox.transform, "Packs waiting to be opened", 17f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 24));
            packRows = new PackRow[MAX_PACK_ROWS];
            for (int i = 0; i < MAX_PACK_ROWS; i++)
            {
                var row = new PackRow();
                row.root = new GameObject($"PcPackRow{i}");
                row.root.transform.SetParent(packsBox.transform, false);
                row.root.AddComponent<RectTransform>();
                UIFactory.AddHLG(row.root, spacing: 10, forceExpandH: true);
                UIFactory.AddLE(row.root, prefH: 26, flexH: 0);
                var r = row;
                row.btnOpen = UIFactory.CreateButton($"PcPackOpen{i}", row.root.transform, "Open", 13f, C_WHITE, C_BUY,
                    () => { var pk = r.pack; if (pk != null) BeginOpenHeld(pk.pack_id); }, sizeDelta: new Vector2(90, 24));
                row.txt = UIFactory.CreateText($"PcPackTxt{i}", row.root.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(700, 24));
                row.root.SetActive(false);
                packRows[i] = row;
            }

            // reveal strip
            var box4 = UIFactory.CreatePanel("PcLastBox", c, C_PANEL);
            UIFactory.AddVLG(box4, spacing: 6, padL: 12, padR: 12, padT: 8, padB: 8);
            UIFactory.AddLE(box4, flexH: 0);
            txtLastHdr = UIFactory.CreateText("PcLastHdr", box4.transform, "Your last pack", 17f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 24));
            lastStrip = new GameObject("PcLastStrip");
            lastStrip.transform.SetParent(box4.transform, false);
            lastStrip.AddComponent<RectTransform>();
            UIFactory.AddHLG(lastStrip, spacing: 8, forceExpandH: false);
            UIFactory.AddLE(lastStrip, prefH: TILE_H, minH: TILE_H, flexH: 0);
            revealTiles = new Tile[REVEAL_TILES];
            for (int i = 0; i < REVEAL_TILES; i++) revealTiles[i] = CreateTile(lastStrip.transform, "PcRv" + i, false);
        }

        private static void BuildBinderView(Transform parent)
        {
            binderRoot = new GameObject("PcBinder");
            binderRoot.transform.SetParent(parent, false);
            binderRoot.AddComponent<RectTransform>();
            UIFactory.AddVLG(binderRoot, spacing: 6);
            UIFactory.AddLE(binderRoot, flexH: 1);
            var hdr = new GameObject("PcBHdr"); hdr.transform.SetParent(binderRoot.transform, false); hdr.AddComponent<RectTransform>();
            UIFactory.AddHLG(hdr, spacing: 10, forceExpandH: true); UIFactory.AddLE(hdr, prefH: 28, flexH: 0);
            txtBinderHdr = UIFactory.CreateText("PcBHdrTxt", hdr.transform, "", 15f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(520, 26));
            btnPrev = UIFactory.CreateButton("PcBPrev", hdr.transform, "<", 14f, C_WHITE, C_BTN, () => { if (binderPage > 0) { binderPage--; NativeUI.MarkDirty(); } }, sizeDelta: new Vector2(40, 24));
            txtBinderPage = UIFactory.CreateText("PcBPage", hdr.transform, "", 13f, C_LABEL, UIFactory.AlignMidCenter, sizeDelta: new Vector2(160, 24));
            btnNext = UIFactory.CreateButton("PcBNext", hdr.transform, ">", 14f, C_WHITE, C_BTN, () => { binderPage++; NativeUI.MarkDirty(); }, sizeDelta: new Vector2(40, 24));
            var sp = new GameObject("PcBSp"); sp.transform.SetParent(hdr.transform, false); sp.AddComponent<RectTransform>(); UIFactory.AddLE(sp, flexW: 1);

            var sv = UIFactory.CreateScrollView("PcBSV", binderRoot.transform, spacing: 8);
            UIFactory.AddLE(sv.scrollGO, flexH: 1);
            binderRows = new GameObject[BINDER_ROWS];
            binderTiles = new Tile[PAGE];
            for (int r = 0; r < BINDER_ROWS; r++)
            {
                var row = new GameObject("PcBRow" + r);
                row.transform.SetParent(sv.content.transform, false);
                row.AddComponent<RectTransform>();
                UIFactory.AddHLG(row, spacing: 8, forceExpandH: false);
                UIFactory.AddLE(row, prefH: TILE_H, minH: TILE_H, flexH: 0);
                binderRows[r] = row;
                for (int k = 0; k < TILES_PER_ROW; k++)
                    binderTiles[r * TILES_PER_ROW + k] = CreateTile(row.transform, $"PcB{r}_{k}", true);
            }
        }

        private static void BuildInfoView(Transform parent)
        {
            infoRoot = new GameObject("PcInfo");
            infoRoot.transform.SetParent(parent, false);
            infoRoot.AddComponent<RectTransform>();
            UIFactory.AddVLG(infoRoot, spacing: 6);
            UIFactory.AddLE(infoRoot, flexH: 1);
            var sv = UIFactory.CreateScrollView("PcISV", infoRoot.transform, spacing: 6);
            UIFactory.AddLE(sv.scrollGO, flexH: 1);
            var box = UIFactory.CreatePanel("PcInfoBox", sv.content.transform, C_PANEL);
            UIFactory.AddVLG(box, spacing: 6, padL: 14, padR: 14, padT: 10, padB: 10);
            UIFactory.AddLE(box, flexH: 0);
            txtInfo = UIFactory.CreateText("PcInfoTxt", box.transform, "", 14f, C_LABEL, UIFactory.AlignTopLeft, sizeDelta: new Vector2(960, 40));
            UIFactory.SetWordWrap(txtInfo, true);       // the Info article body's shape: wrap + auto height
            UIFactory.SetTextAutoHeight(txtInfo, 40f);   // scroll content: auto height, no baked floor (#449)
        }

        private static Tile CreateTile(Transform parent, string name, bool withActions)
        {
            var t = new Tile();
            t.root = UIFactory.CreatePanel(name, parent, FrameColor("common", false));
            UIFactory.AddVLG(t.root, spacing: 0, padL: 3, padR: 3, padT: 3, padB: 3);
            UIFactory.AddLE(t.root, prefW: TILE_W, minW: TILE_W, prefH: TILE_H, minH: TILE_H, flexW: 0, flexH: 0);
            var inner = UIFactory.CreatePanel(name + "_in", t.root.transform, C_CARD);
            UIFactory.AddVLG(inner, spacing: 1, padL: 6, padR: 6, padT: 4, padB: 4);
            UIFactory.AddLE(inner, flexH: 1);
            float w = TILE_W - 18f;
            t.txtName = UIFactory.CreateText(name + "_n", inner.transform, "", 15f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 20));
            t.txtTitle = UIFactory.CreateText(name + "_t", inner.transform, "", 12f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 16));
            t.txtL1 = UIFactory.CreateText(name + "_1", inner.transform, "", 12f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 16));
            t.txtL2 = UIFactory.CreateText(name + "_2", inner.transform, "", 12f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 16));
            t.txtL3 = UIFactory.CreateText(name + "_3", inner.transform, "", 12f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 16));
            t.txtL4 = UIFactory.CreateText(name + "_4", inner.transform, "", 11f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 16));
            t.txtMark = UIFactory.CreateText(name + "_m", inner.transform, "", 12f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 16));
            t.txtSign = UIFactory.CreateText(name + "_s", inner.transform, "", 13f, C_SIGN, UIFactory.AlignMidCenter, sizeDelta: new Vector2(w, 18));
            if (withActions)
            {
                t.actions = new GameObject(name + "_a");
                t.actions.transform.SetParent(inner.transform, false);
                t.actions.AddComponent<RectTransform>();
                UIFactory.AddHLG(t.actions, spacing: 4, forceExpandH: true);
                UIFactory.AddLE(t.actions, prefH: 22, flexH: 0);
                var tile = t;
                t.btnDiscard = UIFactory.CreateButton(name + "_d", t.actions.transform, "Discard", 11f, C_WHITE, C_DANGER, () => OnDiscardClick(tile, false), sizeDelta: new Vector2(80, 20));
                t.btnDiscardTxt = UIFactory.GetButtonText(t.btnDiscard);
                t.btnDupes = UIFactory.CreateButton(name + "_dd", t.actions.transform, "", 11f, C_WHITE, C_DANGER, () => OnDiscardClick(tile, true), sizeDelta: new Vector2(84, 20));
                t.btnDupesTxt = UIFactory.GetButtonText(t.btnDupes);
            }
            t.root.SetActive(false);
            return t;
        }

        private static void FillTile(Tile t, ApiClient.PcPrint p, int dupes)
        {
            if (t == null || t.root == null) return;
            t.print = p; t.dupes = dupes;
            if (p == null) { t.root.SetActive(false); return; }
            t.root.SetActive(true);
            UIFactory.SetImageColor(t.root, FrameColor(p.rarity, p.foil));
            string name = SafeName(p);
            UIFactory.SetTextRaw(t.txtName, name);
            string title = !string.IsNullOrEmpty(p.title) ? p.title : (p.rank_name ?? "");
            UIFactory.SetTextRaw(t.txtTitle, title);
            UIFactory.SetTextRaw(t.txtL1, I18n.TrF("Rating {0} | peak {1}", Mathf.RoundToInt(p.rating), Mathf.RoundToInt(p.peak_rating)));
            UIFactory.SetTextRaw(t.txtL2, p.board_rank > 0
                ? I18n.TrF("Rank #{0} | {1}W {2}L", p.board_rank, p.series_wins, p.series_losses)
                : I18n.TrF("Record {0}W {1}L", p.series_wins, p.series_losses));
            string tc = p.top_card ?? "";
            try { tc = GameStateWatcher.StripRichText(tc); } catch { }
            if (tc.Length > 18) tc = tc.Substring(0, 18);
            UIFactory.SetTextRaw(t.txtL3, tc.Length > 0 ? I18n.TrF("Top card: {0}", tc) : "");
            UIFactory.SetTextRaw(t.txtL4, I18n.TrF("Pool #{0} | Ed. {1} | {2}", p.pool_rank, p.edition_id ?? "", DateOnly(p.minted_at).Replace('-', '/')));
            string mark = RarityLabel(p.rarity);
            if (p.foil) mark += " | " + I18n.Tr("FOIL");
            if (p.signed) mark += " | " + I18n.Tr("SIGNED");
            UIFactory.SetTextRaw(t.txtMark, mark);
            UIFactory.SetTextRaw(t.txtSign, p.signed ? "<i>~ " + name + " ~</i>" : "");
            if (t.actions != null)
            {
                bool armedThis = armedPrintId == p.print_id && !armedDupes;
                UIFactory.SetText(t.btnDiscardTxt, armedThis ? "Sure? Discard" : "Discard");
                bool showDupes = dupes > 1;
                t.btnDupes.SetActive(showDupes);
                if (showDupes)
                {
                    bool armedD = armedPrintId == p.print_id && armedDupes;
                    UIFactory.SetTextRaw(t.btnDupesTxt, armedD ? I18n.Tr("Sure? Discard dupes") : I18n.TrF("Dupes ({0})", dupes - 1));
                }
            }
        }

        // ── repaint ──────────────────────────────────────────────────────────
        internal static void Refresh()
        {
            if (tabRoot == null) return;
            var id = LocalId();
            var me = ApiClient.CachedPcMe;
            var st = ApiClient.CachedPlayerStats;
            for (int i = 0; i < 3; i++)
            {
                if (viewBtns[i] != null) UIFactory.SetImageColor(viewBtns[i], (int)view == i ? C_BTNACT : C_BTN);
                if (viewTxts[i] != null) UIFactory.SetColor(viewTxts[i], (int)view == i ? C_WHITE : C_LABEL);
            }
            if (openRoot != null) openRoot.SetActive(view == View.Open);
            if (binderRoot != null) binderRoot.SetActive(view == View.Binder);
            if (infoRoot != null) infoRoot.SetActive(view == View.Info);

            string bal = st != null ? I18n.TrF("{0} gold", st.gold_earned - st.gold_spent) : "";   // the Shop's balance rule
            if (me != null) bal += (bal.Length > 0 ? "  -  " : "") + I18n.TrF("{0} shards", me.shards);
            UIFactory.SetTextRaw(txtBalance, bal);

            string status; Color sc = C_LABEL;
            if (id == null) status = I18n.Tr("Steam identity not ready yet");
            else if (!SessionReady) { status = I18n.Tr("Waiting for your Steam sign-in - Player Cards need it"); sc = C_WARN; }
            else if (lastMsg != null) { status = lastMsg; sc = lastMsgColor; }
            else if (openInFlight) status = I18n.Tr("Opening your pack...");
            else if (HasIntent()) status = I18n.Tr("A pack is still being resolved - it will be checked again shortly");
            else if (me == null)
            {
                string err = ApiClient.PcMeError;
                if (err == null) status = I18n.Tr("Loading...");
                else if (ApiClient.PcHttpCode(err) == 404) { status = I18n.Tr("Player Cards are not enabled on this server yet"); sc = C_WARN; }
                else { status = ReasonText(ApiClient.PcErrorCode(err)); sc = C_WARN; }
            }
            else status = "";
            UIFactory.SetTextRaw(txtStatus, status);
            UIFactory.SetColor(txtStatus, sc);

            if (view == View.Open) RefreshOpen(me);
            else if (view == View.Binder) RefreshBinder(me);
            else RefreshInfo(me);
        }

        private static void RefreshOpen(ApiClient.PcMe me)
        {
            bool canAct = me != null && SessionReady && !openInFlight && !HasIntent();
            // daily
            string daily;
            if (me == null) daily = "";
            else if (me.daily_claimed)
            {
                string reset = ResetCountdown(me.next_reset_utc);
                daily = reset.Length > 0 ? I18n.TrF("Claimed - the next one unlocks in {0}", reset) : I18n.Tr("Claimed for today");
            }
            else daily = I18n.Tr("One free pack a day (resets at midnight UTC) - also /daily in Discord");
            UIFactory.SetTextRaw(txtDaily, daily);
            bool dailyOpen = me != null && me.daily_claimed && !string.IsNullOrEmpty(me.daily_pack_id) && HasUnopened(me, me.daily_pack_id);
            UIFactory.SetText(btnDailyTxt, dailyOpen ? "Open today's free pack" : (claimInFlight ? "Claiming..." : "Claim today's free pack"));
            UIFactory.SetImageColor(btnDaily, canAct && !claimInFlight && (dailyOpen || !(me?.daily_claimed ?? true)) ? C_BUY : C_BTN);
            // buy
            if (me != null)
            {
                UIFactory.SetTextRaw(btnBuyGoldTxt, I18n.TrF("Open for {0} gold", me.price_gold));
                UIFactory.SetTextRaw(btnBuyShardsTxt, I18n.TrF("Open for {0} shards", me.price_shards));
                UIFactory.SetTextRaw(txtPaid, I18n.TrF("{0} of {1} paid packs today - {2} cards each", me.paid_today, me.paid_packs_per_day, me.prints_per_pack));
                bool capped = me.paid_today >= me.paid_packs_per_day;
                UIFactory.SetImageColor(btnBuyGold, canAct && !capped ? C_BUY : C_BTN);
                UIFactory.SetImageColor(btnBuyShards, canAct && !capped ? C_BUY : C_BTN);
                UIFactory.SetTextRaw(txtPool, me.pool_member_count > 0
                    ? I18n.TrF("Card pool: {0} players (snapshot {1}) - {2} cards in your binder", me.pool_member_count, DateOnly(me.pool_taken_at), me.prints)
                    : I18n.Tr("Card pool: no snapshot yet"));
            }
            else
            {
                UIFactory.SetTextRaw(btnBuyGoldTxt, I18n.Tr("Open with gold"));
                UIFactory.SetTextRaw(btnBuyShardsTxt, I18n.Tr("Open with shards"));
                UIFactory.SetTextRaw(txtPaid, "");
                UIFactory.SetTextRaw(txtPool, "");
                UIFactory.SetImageColor(btnBuyGold, C_BTN);
                UIFactory.SetImageColor(btnBuyShards, C_BTN);
            }
            // packs waiting
            int n = 0;
            if (me != null)
                for (int i = 0; i < me.unopened.Count && n < MAX_PACK_ROWS; i++)
                {
                    var u = me.unopened[i];
                    var row = packRows[n++];
                    row.pack = u;
                    row.root.SetActive(true);
                    UIFactory.SetTextRaw(row.txt, PackLabel(u));
                    UIFactory.SetImageColor(row.btnOpen, canAct ? C_BUY : C_BTN);
                }
            for (int i = n; i < MAX_PACK_ROWS; i++) { packRows[i].pack = null; packRows[i].root.SetActive(false); }
            if (packsBox != null) packsBox.SetActive(n > 0);
            // reveal strip
            bool hasLast = lastPack != null && lastPack.prints != null && lastPack.prints.Count > 0;
            if (lastStrip != null) lastStrip.transform.parent.gameObject.SetActive(hasLast);
            if (hasLast)
            {
                UIFactory.SetTextRaw(txtLastHdr, I18n.TrF("Your last pack ({0}) - {1}", PackSourceLabel(lastPack), DateOnly(lastPack.opened_at)));
                for (int i = 0; i < revealTiles.Length; i++)
                    FillTile(revealTiles[i], i < lastPack.prints.Count ? lastPack.prints[i] : null, 0);
            }
        }

        private static bool HasUnopened(ApiClient.PcMe me, string packId)
        {
            if (me == null || string.IsNullOrEmpty(packId)) return false;
            for (int i = 0; i < me.unopened.Count; i++) if (me.unopened[i].pack_id == packId) return true;
            return false;
        }

        private static string PackLabel(ApiClient.PcUnopened u)
        {
            string src;
            switch (u.source)
            {
                case "daily": src = I18n.Tr("Free daily pack"); break;
                case "earned":
                    src = u.kind == "sweep" ? I18n.Tr("Earned pack (sweep)") : I18n.Tr("Earned pack (ranked win)");
                    if (!string.IsNullOrEmpty(u.mode)) src += " - " + ModeLabel(u.mode);
                    break;
                default: src = I18n.Tr("Pack"); break;
            }
            return src + "  " + DateOnly(u.created_at);
        }
        private static string ModeLabel(string mode)
        {
            switch (mode) { case "1v1": return I18n.Tr("1v1"); case "team": return I18n.Tr("2v2"); case "ovt": return I18n.Tr("1v2"); case "ffa": return I18n.Tr("FFA"); default: return mode; }
        }
        private static string PackSourceLabel(ApiClient.PcPackAnswer a)
        {
            if (a == null) return "";
            switch (a.source)
            {
                case "bought": return a.pay == "shards" ? I18n.Tr("bought with shards") : I18n.Tr("bought with gold");
                case "daily": return I18n.Tr("free daily pack");
                case "earned": return a.kind == "sweep" ? I18n.Tr("earned - sweep") : I18n.Tr("earned - ranked win");
                default: return a.source ?? "";
            }
        }

        private static string ResetCountdown(string iso)
        {
            if (string.IsNullOrEmpty(iso)) return "";
            DateTime dt;
            if (!DateTime.TryParse(iso, System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.AssumeUniversal | System.Globalization.DateTimeStyles.AdjustToUniversal, out dt)) return "";
            var left = dt - DateTime.UtcNow;
            if (left.TotalSeconds <= 0) return "";
            int h = (int)left.TotalHours, m = left.Minutes;
            return h > 0 ? I18n.TrF("{0}h {1}m", h, m) : I18n.TrF("{0}m", Math.Max(1, m));
        }

        private static readonly List<ApiClient.PcPrint> sorted = new List<ApiClient.PcPrint>();
        private static readonly Dictionary<string, int> faceCounts = new Dictionary<string, int>();

        private static void RefreshBinder(ApiClient.PcMe me)
        {
            var col = ApiClient.CachedPcCollection;
            sorted.Clear(); faceCounts.Clear();
            if (col != null)
            {
                sorted.AddRange(col.prints);
                sorted.Sort((a, b) =>
                {
                    int c = string.Compare(SafeName(a), SafeName(b), StringComparison.OrdinalIgnoreCase);
                    if (c != 0) return c;
                    c = string.CompareOrdinal(a.card_id ?? "", b.card_id ?? "");
                    if (c != 0) return c;
                    c = RarityOrder(a.rarity).CompareTo(RarityOrder(b.rarity));
                    if (c != 0) return c;
                    c = (b.foil ? 1 : 0).CompareTo(a.foil ? 1 : 0);
                    if (c != 0) return c;
                    c = (b.signed ? 1 : 0).CompareTo(a.signed ? 1 : 0);
                    if (c != 0) return c;
                    c = string.CompareOrdinal(a.minted_at ?? "", b.minted_at ?? "");
                    return c != 0 ? c : string.CompareOrdinal(a.print_id, b.print_id);
                });
                foreach (var p in sorted) { string k = FaceKey(p); int n; faceCounts.TryGetValue(k, out n); faceCounts[k] = n + 1; }
            }
            int total = sorted.Count;
            int pages = Math.Max(1, (total + PAGE - 1) / PAGE);
            if (binderPage >= pages) binderPage = pages - 1;
            if (binderPage < 0) binderPage = 0;
            string hdr;
            if (col == null) hdr = ApiClient.PcCollectionError != null ? ReasonText(ApiClient.PcErrorCode(ApiClient.PcCollectionError)) : I18n.Tr("Loading your binder...");
            else if (total == 0) hdr = I18n.Tr("No cards yet - open a pack");
            else hdr = I18n.TrF("{0} cards", total);
            if (discardInFlight) hdr += "  -  " + I18n.Tr("discarding...");
            UIFactory.SetTextRaw(txtBinderHdr, hdr);
            UIFactory.SetTextRaw(txtBinderPage, I18n.TrF("Page {0} of {1}", binderPage + 1, pages));
            if (btnPrev != null) btnPrev.SetActive(pages > 1);
            if (btnNext != null) btnNext.SetActive(pages > 1);
            int start = binderPage * PAGE;
            for (int i = 0; i < PAGE; i++)
            {
                int idx = start + i;
                var p = idx < total ? sorted[idx] : null;
                int d = 0;
                if (p != null) faceCounts.TryGetValue(FaceKey(p), out d);
                FillTile(binderTiles[i], p, d);
            }
            for (int r = 0; r < BINDER_ROWS; r++)
                if (binderRows[r] != null) binderRows[r].SetActive(start + r * TILES_PER_ROW < total);
        }

        private static void RefreshInfo(ApiClient.PcMe me)
        {
            int gold = me != null ? me.price_gold : 100, shards = me != null ? me.price_shards : 100;
            int cap = me != null ? me.paid_packs_per_day : 5, per = me != null ? me.prints_per_pack : 5;
            // The odds and shard values below mirror PC_ECONOMY in
            // backend/api/player_cards.py (pinned by test_player_cards_client_text);
            // the prices come from the server's answer.
            string body = I18n.Tr("How to get packs") + "\n"
                + I18n.Tr("- One free pack every day (resets at midnight UTC). Claim it on the Open Packs page or with /daily in Discord.") + "\n"
                + I18n.Tr("- Ranked wins: every ranked 1v1 series you win rolls a 20% chance of a pack (a 2-0 sweep: 100%). 2v2, 1v2 and FFA wins roll 10% (a sweep: 50%). Earned packs wait here until you open them.") + "\n"
                + I18n.TrF("- Buy one for {0} gold or {1} shards, up to {2} paid packs a day.", gold, shards, cap) + "\n\n"
                + I18n.TrF("Each pack holds {0} cards. A card's rarity is its player's rank in the card pool on the day of the pull: Legendary = #1, Epic #2-10, Rare #11-20, Uncommon #21-40, Common #41 and below. Odds per card: Common 60%, Uncommon 25%, Rare 11%, Epic 3.5%, Legendary 0.5%. Every card also rolls Foil (1 in 200) and Signed (1 in 2000) on its own.", per) + "\n\n"
                + I18n.Tr("Discarding a card gives shards by its rarity: Common 5, Uncommon 15, Rare 40, Epic 150, Legendary 600. Shards buy packs. Discards are one card at a time; the Dupes button discards every other copy of that exact card.") + "\n\n"
                + I18n.Tr("A card shows its player as the leaderboard did on the day it was pulled - name, title, rating, record and rank - and never changes afterwards (a renamed player shows their new name). Anyone with the mod can be pulled unless they turn it off in Settings; your own settings for being a card, a public binder and pull announcements live there too.");
            UIFactory.SetTextRaw(txtInfo, body);
        }

        // ── actions ──────────────────────────────────────────────────────────
        private static void ClaimDaily()
        {
            var id = LocalId(); var me = ApiClient.CachedPcMe;
            if (id == null || me == null) { if (id != null) ApiClient.FetchPcMe(id, true); return; }
            if (!SessionReady) { Say(ReasonText("session_required"), C_WARN); return; }
            if (openInFlight || (claimInFlight && Now - claimAt < 25f)) return;
            if (HasIntent()) { Say(I18n.Tr("A pack is still being resolved - hold on"), C_WARN); MaybeRecover(true); return; }
            if (me.daily_claimed)
            {
                if (!string.IsNullOrEmpty(me.daily_pack_id) && HasUnopened(me, me.daily_pack_id)) { BeginOpenHeld(me.daily_pack_id); return; }
                Say(ReasonText("already_claimed"));
                return;
            }
            claimInFlight = true; claimAt = Now;
            NativeUI.MarkDirty();
            ApiClient.PcClaimDaily(id, NewNonce(), (ok, resp) =>
            {
                claimInFlight = false;
                if (ok)
                {
                    string pack = ApiClient.PcStr(ApiClient.PcTopLevel(resp, "pack_id"));
                    if (!string.IsNullOrEmpty(pack)) BeginOpenHeld(pack);
                    else ApiClient.FetchPcMe(id, true);
                }
                else
                {
                    string code = ApiClient.PcErrorCode(resp);
                    Say(ReasonText(code), code == "already_claimed" ? C_LABEL : C_WARN);
                    ApiClient.FetchPcMe(id, true);
                }
                NativeUI.MarkDirty();
            });
        }

        private static void BeginBuy(string pay)
        {
            var id = LocalId(); var me = ApiClient.CachedPcMe;
            if (id == null || me == null) { if (id != null) ApiClient.FetchPcMe(id, true); return; }
            if (!SessionReady) { Say(ReasonText("session_required"), C_WARN); return; }
            if (openInFlight && Now - openAt < 25f) return;
            if (HasIntent()) { Say(I18n.Tr("A pack is still being resolved - hold on"), C_WARN); MaybeRecover(true); return; }
            if (me.paid_today >= me.paid_packs_per_day) { Say(ReasonText("daily_cap")); return; }
            int price = pay == "gold" ? me.price_gold : me.price_shards;
            string nonce = NewNonce();
            WriteIntent("buy", nonce, pay, price);
            openInFlight = true; openAt = Now; lastMsg = null;
            NativeUI.MarkDirty();
            ApiClient.PcOpenPack(id, nonce, pay, price, (ok, resp) => { openInFlight = false; HandleAnswer(ok, resp, false); });
        }

        private static void BeginOpenHeld(string packId)
        {
            var id = LocalId();
            if (id == null || string.IsNullOrEmpty(packId)) return;
            if (!SessionReady) { Say(ReasonText("session_required"), C_WARN); return; }
            if (openInFlight && Now - openAt < 25f) return;
            if (HasIntent()) { Say(I18n.Tr("A pack is still being resolved - hold on"), C_WARN); MaybeRecover(true); return; }
            WriteIntent("pack", packId, "-", 0);
            openInFlight = true; openAt = Now; lastMsg = null;
            NativeUI.MarkDirty();
            ApiClient.PcOpenUnopened(id, packId, (ok, resp) => { openInFlight = false; HandleAnswer(ok, resp, false); });
        }

        /// <summary>One handler for the open call and for result recovery. A
        /// committed answer (done / rejected / unopened / voided) retires the
        /// intent; anything that leaves the server's decision unknown (no
        /// answer, 401, in_progress, pending) keeps it for the next recovery.</summary>
        private static void HandleAnswer(bool ok, string resp, bool recovery)
        {
            var id = LocalId();
            string kind, reference; float age;
            ReadIntent(out kind, out reference, out age);
            if (ok)
            {
                var a = ApiClient.ParsePcPackAnswer(resp);
                if (a == null)
                {
                    ClearIntent();
                    Say(I18n.Tr("The pack answer could not be read - check your binder"), C_WARN);
                    Plugin.Log.LogWarning($"[PC] unparseable pack answer: {(resp != null && resp.Length > 200 ? resp.Substring(0, 200) : resp)}");
                }
                else if (a.status == "done")
                {
                    lastPack = a; ClearIntent();
                    Say(I18n.TrF("Pack opened - {0} new cards", a.prints.Count), C_OK);
                    try { CompetitiveUI.ShowNotification(I18n.TrF("Pack opened - {0} new cards", a.prints.Count), C_OK, 3f); } catch { }
                    if (view == View.Binder) view = View.Open;
                }
                else if (a.status == "rejected") { ClearIntent(); Say(ReasonText(a.reason ?? "http"), C_WARN); }
                else if (a.status == "unopened")
                {
                    ClearIntent();
                    Say(a.last_attempt_reason != null ? ReasonText(a.last_attempt_reason) : I18n.Tr("The pack is still yours to open"), C_WARN);
                }
                else if (a.status == "voided") { ClearIntent(); Say(ReasonText("voided"), C_WARN); }
                else Say(I18n.Tr("Still opening - checking again shortly"));   // pending / opening: keep the intent
            }
            else
            {
                string code = ApiClient.PcErrorCode(resp);
                int http = ApiClient.PcHttpCode(resp);
                switch (code)
                {
                    case "transport":
                        Say(I18n.Tr("No answer from the server - your pack will be checked again shortly"), C_WARN);
                        break;
                    case "session_required":
                        recoverAt = Time.unscaledTime + 60f;
                        Say(ReasonText(code), C_WARN);
                        break;
                    case "in_progress":
                        Say(ReasonText(code));
                        break;
                    case "http":
                        if (http == 404)
                        {
                            // Open call: the pack is not the player's (or gone) -
                            // nothing to recover. Result call: no claim committed;
                            // retire the nonce after the 10-minute window.
                            if (!recovery || age > INTENT_NOT_FOUND_RETIRE_S) { ClearIntent(); Say(recovery ? I18n.Tr("That pack purchase never went through - nothing was charged") : I18n.Tr("That pack is not available any more"), C_WARN); }
                            else Say(I18n.Tr("Still waiting for the server to record your pack - checking again shortly"), C_WARN);
                        }
                        else if (age > INTENT_HARD_RETIRE_S)
                        {
                            ClearIntent();
                            Say(I18n.Tr("Your pack could not be resolved for an hour - check your binder and gold; contact Sid on Discord if something is missing"), C_WARN);
                        }
                        else Say(ReasonText(code), C_WARN);
                        break;
                    default:
                        // A named rejection is a committed row: the nonce is spent
                        // and nothing was charged.
                        ClearIntent();
                        Say(ReasonText(code), C_WARN);
                        break;
                }
            }
            if (id != null)
            {
                ApiClient.FetchPcMe(id, true);
                ApiClient.FetchPcCollection(id, true);
                ApiClient.FetchPlayerStats(id, true);
            }
            NativeUI.MarkDirty();
        }

        private static void MaybeRecover(bool force)
        {
            var id = LocalId();
            if (id == null || openInFlight || recoverInFlight) return;
            string kind, reference; float age;
            if (!ReadIntent(out kind, out reference, out age)) return;
            if (!SessionReady) return;
            if (!force && Time.unscaledTime < recoverAt) return;
            recoverAt = Time.unscaledTime + 15f;
            recoverInFlight = true;
            Plugin.Log.LogInfo($"[PC] recovering {kind} intent (age {age:F0}s)");
            ApiClient.PcPackResult(id, kind == "buy" ? reference : null, kind == "pack" ? reference : null,
                (ok, resp) => { recoverInFlight = false; HandleAnswer(ok, resp, true); });
        }

        private static void OnDiscardClick(Tile t, bool dupes)
        {
            var p = t?.print; var id = LocalId();
            if (p == null || id == null || discardInFlight) return;
            if (!SessionReady) { Say(ReasonText("session_required"), C_WARN); return; }
            if (armedPrintId != p.print_id || armedDupes != dupes || Now - armedAt > 6f)
            {
                armedPrintId = p.print_id; armedDupes = dupes; armedAt = Now;
                Say(dupes ? I18n.Tr("Click Dupes again to discard every other copy of that card") : I18n.Tr("Click Discard again to discard that card for shards"));
                return;
            }
            armedPrintId = null;
            discardQueue.Clear();
            if (!dupes) discardQueue.Add(p.print_id);
            else
            {
                string key = FaceKey(p);
                var col = ApiClient.CachedPcCollection;
                if (col != null)
                    foreach (var o in col.prints)
                        if (o.print_id != p.print_id && FaceKey(o) == key) discardQueue.Add(o.print_id);
            }
            if (discardQueue.Count == 0) return;
            discardDone = 0; discardShards = 0; discardInFlight = true;
            NativeUI.MarkDirty();
            DiscardNext(id);
        }

        private static void DiscardNext(string id)
        {
            if (discardQueue.Count == 0) { FinishDiscard(id, null); return; }
            string pid = discardQueue[0]; discardQueue.RemoveAt(0);
            ApiClient.PcDiscard(id, pid, (ok, resp) =>
            {
                if (ok)
                {
                    discardDone++;
                    discardShards += ApiClient.PcInt(ApiClient.PcTopLevel(resp, "shards_gained"));
                    var col = ApiClient.CachedPcCollection;
                    if (col != null) col.prints.RemoveAll(x => x.print_id == pid);
                    DiscardNext(id);
                }
                else FinishDiscard(id, ApiClient.PcErrorCode(resp));
            });
        }

        private static void FinishDiscard(string id, string errorCode)
        {
            discardInFlight = false; discardQueue.Clear();
            if (discardDone > 0)
                Say(I18n.TrF("Discarded {0} card(s) for {1} shards", discardDone, discardShards), C_OK);
            if (errorCode != null) Say(ReasonText(errorCode), C_WARN);
            if (id != null) { ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true); }
            NativeUI.MarkDirty();
        }


        /// <summary>Broadcast-seat lever ([Broadcast] TestPlayerCards): seed the
        /// reveal strip with five synthetic prints (one per rarity, one foil,
        /// one signed) so the card face can be screenshotted on a seat whose
        /// server does not carry the routes yet. Identity-gated by the caller;
        /// never touches the server or the intent.</summary>
        internal static void DevSeedTiles(string mode)
        {
            string[] rar = { "legendary", "epic", "rare", "uncommon", "common" };
            string[] names = { "Sid", "Rival", "Challenger", "Contender", "Newcomer" };
            var a = new ApiClient.PcPackAnswer { pack_id = "dev", status = "done", source = "bought", pay = "gold", price = 100, opened_at = "2026-09-11T00:00:00" };
            for (int i = 0; i < 5; i++)
                a.prints.Add(new ApiClient.PcPrint
                {
                    print_id = "dev" + i, card_id = "card" + i, subject_player_id = "p" + i, subject_name = names[i],
                    edition_id = "1", minted_at = "2026-09-11T00:00:00", rarity = rar[i], foil = i == 1, signed = i == 0,
                    pool_rank = i == 0 ? 1 : i * 9, rating = 1850 - i * 120, peak_rating = 1900 - i * 100, board_rank = i == 0 ? 1 : i * 9,
                    series_wins = 60 - i * 8, series_losses = 12 + i * 3, top_card = "Bombs Away", title = i == 0 ? "Grandmaster" : "", rank_name = "Diamond", source = "bought", slot = i,
                });
            lastPack = a;
            view = mode == "binder" ? View.Binder : (mode == "info" ? View.Info : View.Open);
            Plugin.Log.LogInfo("[PC] synthetic tiles seeded (dev lever)");
            NativeUI.MarkDirty();
        }

        // ── Settings tab rows (design v4 §12 wording) ─────────────────────────
        internal static void BuildSettingsRows(Transform parent)
        {
            UIFactory.CreateText("SPcHdr", parent, "Player Cards", 15f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(700, 22));
            btnBeCard = SettingsRow(parent, "SPcBe", () => ToggleSetting("opted_out"),
                "Other players can pull, collect and trade a card of you showing your name, rank title, rating and ranked record - the same things the leaderboard shows. Turn this off and no new copies are printed; copies already pulled stay in their owners' collections.", 36f);
            btnBeCardTxt = UIFactory.GetButtonText(btnBeCard);
            btnPublic = SettingsRow(parent, "SPcPub", () => ToggleSetting("collection_public"),
                "Lets others see which cards you hold, in the mod and in Discord.", 18f);
            btnPublicTxt = UIFactory.GetButtonText(btnPublic);
            btnAnnounce = SettingsRow(parent, "SPcAnn", () => ToggleSetting("announce"),
                "Rare pulls may be posted to the Discord announcements channel with your name.", 18f);
            btnAnnounceTxt = UIFactory.GetButtonText(btnAnnounce);
        }

        private static GameObject SettingsRow(Transform parent, string name, UnityEngine.Events.UnityAction onClick, string desc, float descH)
        {
            // One setting = one [button + caption below] group (Bug 87), the
            // same shape as NativeUI's SettingsToggle.
            var group = new GameObject(name + "_grp");
            group.transform.SetParent(parent, false);
            group.AddComponent<RectTransform>();
            UIFactory.AddVLG(group, spacing: 1);
            UIFactory.AddLE(group, flexH: 0);
            var btn = NativeUI.SettingsButton(group.transform, name, "", C_WHITE, C_BTN, new Vector2(340, 28), onClick);
            UIFactory.CreateText(name + "_d", group.transform, desc, 13f, C_DIM, sizeDelta: new Vector2(700, descH));
            return btn;
        }

        internal static void RefreshSettingsRows()
        {
            if (btnBeCardTxt == null) return;
            var id = LocalId();
            var me = ApiClient.CachedPcMe;
            if (me == null && id != null) ApiClient.FetchPcMe(id);   // throttled inside (10 s)
            if (me == null)
            {
                UIFactory.SetText(btnBeCardTxt, "I can be a Player Card: <color=#888>...</color>");
                UIFactory.SetText(btnPublicTxt, "My collection is public: <color=#888>...</color>");
                UIFactory.SetText(btnAnnounceTxt, "Announce my pulls: <color=#888>...</color>");
                return;
            }
            UIFactory.SetText(btnBeCardTxt, !me.opted_out
                ? "I can be a Player Card: <color=#88FF88>ON</color>"
                : "I can be a Player Card: <color=#FF9966>OFF</color>");
            UIFactory.SetText(btnPublicTxt, me.collection_public
                ? "My collection is public: <color=#88FF88>ON</color>"
                : "My collection is public: <color=#FF9966>OFF</color>");
            UIFactory.SetText(btnAnnounceTxt, me.announce
                ? "Announce my pulls: <color=#88FF88>ON</color>"
                : "Announce my pulls: <color=#FF9966>OFF</color>");
        }

        private static bool SettingValue(ApiClient.PcMe me, string key)
        {
            switch (key) { case "opted_out": return me.opted_out; case "collection_public": return me.collection_public; default: return me.announce; }
        }
        private static void ApplySetting(ApiClient.PcMe me, string key, bool v)
        {
            if (me == null) return;
            switch (key) { case "opted_out": me.opted_out = v; break; case "collection_public": me.collection_public = v; break; default: me.announce = v; break; }
        }

        private static void ToggleSetting(string key)
        {
            var id = LocalId(); var me = ApiClient.CachedPcMe;
            if (id == null) return;
            if (me == null) { ApiClient.FetchPcMe(id, true); return; }
            if (!SessionReady) { try { CompetitiveUI.ShowNotification(ReasonText("session_required"), C_WARN, 3f); } catch { } return; }
            // Single-flight with a 25 s latch (past the 20 s transport timeout,
            // the same rule as the same-cards preference): the value that
            // persists is the one the label shows; a failed write rolls the
            // optimistic flip back.
            if (setInFlight && Now - setAt < 25f) return;
            setInFlight = true; setAt = Now;
            bool before = SettingValue(me, key);
            bool after = !before;
            int revision = me.revision;
            ApplySetting(me, key, after);
            NativeUI.MarkDirty();
            Plugin.Log.LogInfo($"[PC] setting {key} -> {(after ? 1 : 0)} (rev {revision})");
            ApiClient.PcSetSetting(id, NewNonce(), revision, key, after ? 1 : 0, (ok, resp) =>
            {
                setInFlight = false;
                if (!ok)
                {
                    var cur = ApiClient.CachedPcMe;
                    if (cur != null) ApplySetting(cur, key, before);
                    string code = ApiClient.PcErrorCode(resp);
                    if (code == "stale_revision") ApiClient.FetchPcMe(id, true);
                    try { CompetitiveUI.ShowNotification(ReasonText(code), Color.yellow, 3f); } catch { }
                }
                NativeUI.MarkDirty();
            });
        }
    }
}
