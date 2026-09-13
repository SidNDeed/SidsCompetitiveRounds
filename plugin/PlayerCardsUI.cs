using System;
using System.Collections;
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
        private const int TILES_PER_ROW = 5, BINDER_ROWS = 2;   // 5 x 236 px fits the 1240-wide binder column
        private const int REVEAL_TILES = 5;                     // one pack = five prints
        private const int PAGE = TILES_PER_ROW * BINDER_ROWS;
        // The tile IS the server-rendered face (375x525, v22 section 1.6): 236 x 330
        // keeps its 5:7. The text block below is what a tile shows when no face
        // could be had (an api without the renderer, a refused fetch).
        private const float TILE_W = 236f, TILE_H = 330f;
        private const int MAX_PACK_ROWS = 12;
        private const float INTENT_NOT_FOUND_RETIRE_S = 600f;     // design §6: not-found after 10 min = never claimed
        private const char INTENT_SEP = '~';                      // c6: one journal entry per owner, joined by '~'
        private const int INTENT_MAX_ENTRIES = 8;                 // c6: bound on the entries kept on one PC
        private const int UNPARSEABLE_RETIRE_STRIKES = 3;         // c6: a 2xx the client cannot read, this many times running, retires the intent

        private class Tile
        {
            public GameObject root, actions, btnDiscard, btnDupes;
            public GameObject face, textBlock;   // exactly one of the two is active
            public GameObject faceMarkGO;        // the DISCARDED stamp over a face that is still cached
            public int bindSeq;                  // v22 section 5.2: a face answer that misses this paints nothing
            public object txtName, txtTitle, txtL1, txtL2, txtL3, txtL4, txtMark, txtSign, btnDiscardTxt, btnDupesTxt, faceMark;
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
        private static GameObject btnPrev, btnNext, btnSort;
        private static object btnSortTxt;
        /// <summary>Binder orders (2026-09-13): the header button cycles them.
        /// Position is the leaderboard position printed on the card
        /// (board_rank); a card of a player who was off the board that day
        /// sorts last under it.</summary>
        private enum Sort { Name, Rarity, Edition, Date, Position }
        private static Sort binderSort = Sort.Name;
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
        private static int unparseableStrikes;   // consecutive 2xx answers the client could not read (c6)
        private static ApiClient.PcPackAnswer lastPack;
        private static string lastMsg; private static Color lastMsgColor; private static float lastMsgAt;
        // settings rows
        private static GameObject btnPublic, btnAnnounce, btnPreset, presetPreview, presetPreviewRow;
        private static object btnPublicTxt, btnAnnounceTxt, btnPresetTxt, txtPicNote;
        private static int previewShown = -1;   // PortraitRender.PreviewSerial the preview sprite was made from
        private static Sprite previewSprite;
        private static bool setInFlight; private static float setAt;
        // identity fence (c4): every callback captures uiEpoch at dispatch and
        // returns when an identity edge advanced it; priceChangedAt gates a
        // repeat purchase until /pc/me has answered after a price_changed.
        private static int uiEpoch;
        /// <summary>Advances on every identity edge (and on a consent revoke): a
        /// callback that captured an older value commits nothing.</summary>
        internal static int Epoch => uiEpoch;
        private static float priceChangedAt = -1f;

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

        /* The name arrives as the server's PUBLIC RENDER NAME (v22 2.4): the
         * producer tag set already stripped to a fixed point, controls already
         * normalised, and null when nothing readable is left. So it is DRAWN,
         * not re-processed.
         *
         * It used to go through StripRichText, the blanket <.*?> matcher --
         * which is what turns the name "AC<DC>Fan" into "ACFan" (bug 259, and
         * the lesson is recorded beside that method). The server keeps those
         * brackets on purpose and the card draws them; this made the tile
         * disagree with the picture on it.
         *
         * An empty name is not a deleted account. The server answers null for
         * a name that projects to nothing at all -- the Steam-ID constructor
         * fallback among them -- and a live player with no name got the
         * deletion label while the face beside it drew the neutral one. */
        private static string SafeName(ApiClient.PcPrint p)
        {
            if (p == null) return "";
            string n = p.subject_name ?? "";
            if (n.Length == 0) return I18n.Tr(p.subject_deleted ? "[deleted]" : "Unnamed player");
            if (n.Length > 24) n = n.Substring(0, 24);
            return n;
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
        // One entry PER OWNER (c6): "kind|ref|pay|price|unix|owner" entries joined
        // by INTENT_SEP. Another account on this PC neither recovers, clears nor
        // overwrites an entry that is not its own, so no fence and no expiry are
        // needed - the c5 fence traded a lock-out against a loss; a journal keyed
        // by owner has neither. Malformed or unowned entries are nobody's: dropped.
        /// <summary>An intent of the CURRENT identity exists.</summary>
        private static bool HasIntent() { string k, r; float a; return ReadIntent(out k, out r, out a); }
        /// <summary>Every well-formed owned entry; <paramref name="dirty"/> when a
        /// malformed one was dropped (the caller rewrites the journal).</summary>
        private static List<string[]> ReadIntents(out bool dirty)
        {
            var list = new List<string[]>(); dirty = false;
            string v = null;
            try { v = Plugin.PcOpenIntent?.Value; } catch { }
            if (string.IsNullOrEmpty(v)) return list;
            foreach (var raw in v.Split(INTENT_SEP))
            {
                if (raw.Length == 0) continue;
                var parts = raw.Split('|');
                long unix;
                bool ok = parts.Length == 6 && (parts[0] == "buy" || parts[0] == "pack") && parts[1].Length > 0
                          && long.TryParse(parts[4], out unix) && parts[5].Length > 0;
                if (!ok) { dirty = true; Plugin.Log.LogWarning("[PC] malformed or unowned intent discarded"); continue; }
                list.Add(parts);
            }
            return list;
        }
        private static string JoinIntents(List<string[]> list)
        {
            var sb = new System.Text.StringBuilder();
            foreach (var p in list) { if (sb.Length > 0) sb.Append(INTENT_SEP); sb.Append(string.Join("|", p)); }
            return sb.ToString();
        }
        /// <summary>Write the journal and read it back; false when the write did not take.</summary>
        private static bool WriteIntents(List<string[]> list)
        {
            string v = JoinIntents(list);
            try
            {
                if (Plugin.PcOpenIntent == null) return false;
                Plugin.PcOpenIntent.Value = v;
                return Plugin.PcOpenIntent.Value == v;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PC] intent write failed: {ex.Message}"); return false; }
        }
        /// <summary>Persist THIS identity's intent BEFORE the request leaves. False
        /// when the config write did not take: the caller must not send the request -
        /// a purchase whose answer could not be recovered is the worse failure (c4).
        /// Other owners' entries are carried unchanged; the oldest goes only past
        /// INTENT_MAX_ENTRIES.</summary>
        private static bool WriteIntent(string kind, string reference, string pay, int price)
        {
            string owner = LocalId();
            if (string.IsNullOrEmpty(owner)) return false;   // an intent without an owner is nobody's to recover (c5)
            bool dirty;
            var list = ReadIntents(out dirty);
            list.RemoveAll(p => p[5] == owner);
            while (list.Count >= INTENT_MAX_ENTRIES)
            {
                int oldest = 0;
                for (int i = 1; i < list.Count; i++) if (long.Parse(list[i][4]) < long.Parse(list[oldest][4])) oldest = i;
                list.RemoveAt(oldest);
            }
            long unix = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            list.Add(new[] { kind, reference, pay, price.ToString(), unix.ToString(), owner });
            return WriteIntents(list);
        }
        /// <summary>Retire THIS identity's entry only.</summary>
        private static void ClearIntent()
        {
            string owner = LocalId();
            bool dirty;
            var list = ReadIntents(out dirty);
            int n = list.RemoveAll(p => owner != null && p[5] == owner);
            if (n > 0 || dirty) WriteIntents(list);
        }
        /// <summary>This identity's entry, if any. Another identity's entries are left
        /// untouched (c4/c6); malformed ones are dropped on the way (c5).</summary>
        private static bool ReadIntent(out string kind, out string reference, out float ageS)
        {
            kind = null; reference = null; ageS = 0f;
            bool dirty;
            var list = ReadIntents(out dirty);
            if (dirty) WriteIntents(list);
            string owner = LocalId();
            if (owner == null) return false;
            foreach (var p in list)
            {
                if (p[5] != owner) continue;
                kind = p[0]; reference = p[1];
                long unix = long.Parse(p[4]);
                ageS = (float)(DateTimeOffset.UtcNow.ToUnixTimeSeconds() - unix);
                return true;
            }
            return false;
        }

        /// <summary>Identity edge (c4): nothing of the previous identity's
        /// Player Cards state survives — the last pack, the message, the armed
        /// discard, the in-flight flags — and every in-flight callback lands
        /// into the void (uiEpoch). The persisted intent is per identity and is
        /// left alone. Called from the edge that clears ApiClient's caches.</summary>
        internal static void OnIdentityChanged()
        {
            uiEpoch++;
            try { HideCardPopup(); } catch { }
            try { PlayerCardFaces.Clear(); } catch { }
            try { PortraitRender.OnIdentityChanged(); } catch { }
            lastPack = null; lastMsg = null;
            HistoryReset();
            openInFlight = claimInFlight = recoverInFlight = discardInFlight = setInFlight = false;
            portraitWaitUntil = -1f; portraitWaitedAt = -100f; pendingVisit = false;
            settingsVisited = false;   // the next Settings look checks the picture again (r5 L12)
            // the previous account's character, as a Sprite over a texture
            // PortraitRender has just destroyed
            if (previewSprite != null) { try { UnityEngine.Object.Destroy(previewSprite); } catch { } previewSprite = null; }
            previewShown = -1;
            if (presetPreview != null) { try { PlayerCardFaces.SetFace(presetPreview, null); } catch { } }
            discardQueue.Clear(); armedPrintId = null; priceChangedAt = -1f;
            recoverAt = 0f; meRefreshAt = 0f; unparseableStrikes = 0;
            try { NativeUI.MarkDirty(); } catch { }
        }

        // ── NativeUI entry points ────────────────────────────────────────────
        private static bool pendingVisit;
        private static bool settingsVisited;   // one picture check per Settings visit (2026-09-13)

        /// <summary>Every close path of the F5 page (#369). Two jobs:
        ///
        /// the full-screen card popup is a persistent overlay child, so a close
        /// that did not hide it left it painting over live gameplay and eating
        /// the clicks meant for the game; and reopening the page with Collection
        /// ALREADY current never re-entered the tab, so a character changed
        /// while the page was closed was never checked or uploaded. Arming the
        /// visit here is what makes the next open a visit.</summary>
        internal static void OnOverlayClosed()
        {
            try { HideCardPopup(); } catch { }
            pendingVisit = true; settingsVisited = false;
        }

        /// <summary>The card view is a full-screen uGUI surface: it owns input
        /// while it is up (CompetitiveUI's single ModalBlockInput writer reads
        /// this), and its own backdrop carries bypassModalBlock so the dismiss
        /// still runs. Without it, a backdrop click closed the popup AND
        /// reached the armed Discard beneath in the same click (#141/#200).</summary>
        internal static bool CardPopupOpen { get { return cardPopupGO != null; } }

        internal static void OnTabEntered()
        {
            var id = LocalId();
            if (id == null) return;
            ApiClient.FetchPlayerStats(id);
            ApiClient.FetchPcMe(id, true);
            ApiClient.FetchPcCollection(id);
            meRefreshAt = Time.unscaledTime + 30f;
            try { PortraitRender.OnTabVisit(); } catch { }   // v22 §3.1: one picture check per visit
            MaybeRecover(true);
        }

        /// <param name="onTab">the Collection tab is the current one</param>
        /// <param name="onSettings">the Settings tab is the current one — the
        /// picture and preset controls and the preview live THERE, not on
        /// Collection. The portrait ticker used to run on Collection only, so
        /// cycling the preset from Settings relabelled the button, debounced a
        /// refresh, and then nothing ever came to act on it: no render, no
        /// preview, no upload, and no error either.</param>
        internal static void MaybeTick(bool onTab, bool onSettings)
        {
            // The Settings edge is tracked on EVERY call (NativeUI.Tick, each
            // frame), ahead of the two-second throttle (r7 L3): a leave-and-
            // return inside one throttle window never ran an off-Settings tick,
            // so the visit check stayed disarmed for the second entry.
            if (!onSettings) settingsVisited = false;   // leaving Settings re-arms its one check for the next entry (r6 L12)
            if (Time.unscaledTime < tickAt) return;
            tickAt = Time.unscaledTime + 2f;
            var id = LocalId();
            if (id == null) return;
            if (HasIntent()) MaybeRecover(false);
            if (onTab && pendingVisit) { pendingVisit = false; OnTabEntered(); }
            if (!onTab && !onSettings) return;
            try { PlayerCardFaces.Tick(); } catch { }
            try { PortraitRender.Tick(); } catch (Exception ex) { Plugin.Log.LogWarning($"[PC] portrait tick threw: {ex.Message}"); }
            if (onSettings)
            {
                // The preset row draws from these two and the renderer refuses
                // without them; Settings has no fetch chain of its own.
                if (ApiClient.CachedPcMe == null) ApiClient.FetchPcMe(id, false);
                if (ApiClient.CachedPlayerStats == null) ApiClient.FetchPlayerStats(id);
                // One picture check per Settings visit as well (2026-09-13): the
                // preview only appeared after a preset change because nothing
                // rendered while the stored picture was current. The check now
                // draws the preview in that case (PortraitRender.Tick).
                if (!settingsVisited) { settingsVisited = true; try { PortraitRender.OnTabVisit(); } catch { } }
                return;
            }
            if (Time.unscaledTime >= meRefreshAt) { meRefreshAt = Time.unscaledTime + 30f; ApiClient.FetchPcMe(id, true); }
            // the binder after an identity edge (c5): an empty cache without an error is refetched (throttled by ApiClient)
            if (view == View.Binder && ApiClient.CachedPcCollection == null && ApiClient.PcCollectionError == null) ApiClient.FetchPcCollection(id);
            if (armedPrintId != null && Now - armedAt > 6f) { armedPrintId = null; NativeUI.MarkDirty(); }
            if (lastMsg != null && Now - lastMsgAt > 15f) { lastMsg = null; NativeUI.MarkDirty(); }
            if (openInFlight && Now - openAt > 25f) { openInFlight = false; NativeUI.MarkDirty(); }
            if (claimInFlight && Now - claimAt > 25f) { claimInFlight = false; NativeUI.MarkDirty(); }
        }

        private static void ViewButton(int i, GameObject b)
        {
            if (UIFactory.tLE != null)
            {
                var el = b.GetComponent(UIFactory.tLE);
                if (el != null) UnityEngine.Object.Destroy(el as UnityEngine.Object);
            }
            UIFactory.AddLE(b, prefH: 26, minH: 26, flexW: 1, flexH: 0);
            viewBtns[i] = b; viewTxts[i] = UIFactory.GetButtonText(b);
        }

        internal static void BuildInto(Transform parent)
        {
            HookHistorySignals();
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
            // Three literal sites (c4): a label must sit AT a harvested
            // CreateButton call for the key catalogue to carry it.
            ViewButton(0, UIFactory.CreateButton("PcView0", bar.transform, "Open Packs", 14f, C_LABEL, C_BTN,
                () => { view = (View)0; NativeUI.MarkDirty(); }, sizeDelta: new Vector2(0, 26)));
            ViewButton(1, UIFactory.CreateButton("PcView1", bar.transform, "Binder", 14f, C_LABEL, C_BTN,
                () => { view = (View)1; NativeUI.MarkDirty(); }, sizeDelta: new Vector2(0, 26)));
            ViewButton(2, UIFactory.CreateButton("PcView2", bar.transform, "Get packs", 14f, C_LABEL, C_BTN,
                () => { view = (View)2; NativeUI.MarkDirty(); }, sizeDelta: new Vector2(0, 26)));
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
            // The strip is a pager over the pack history (Sid, 2026-09-12): the
            // header row carries the title, then older / position / newer.
            var hdrRow = new GameObject("PcLastHdrRow");
            hdrRow.transform.SetParent(box4.transform, false);
            hdrRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(hdrRow, spacing: 8, forceExpandH: false);
            UIFactory.AddLE(hdrRow, prefH: 26, minH: 26, flexH: 0);
            txtLastHdr = UIFactory.CreateText("PcLastHdr", hdrRow.transform, "Your packs", 17f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(700, 24));
            UIFactory.SetOverflowMode(txtLastHdr, 2); UIFactory.SetWordWrap(txtLastHdr, false);
            var hdrGO = (txtLastHdr as Component)?.gameObject;
            if (hdrGO != null) UIFactory.AddLE(hdrGO, flexW: 1);
            btnHistOlder = UIFactory.CreateButton("PcHistOlder", hdrRow.transform, "< Older", 12f, C_WHITE, C_BTN, () => PageHistory(+1), sizeDelta: new Vector2(76, 22));
            txtHistPos = UIFactory.CreateText("PcHistPos", hdrRow.transform, "", 13f, C_LABEL, UIFactory.AlignMidCenter, sizeDelta: new Vector2(120, 22));
            btnHistNewer = UIFactory.CreateButton("PcHistNewer", hdrRow.transform, "Newer >", 12f, C_WHITE, C_BTN, () => PageHistory(-1), sizeDelta: new Vector2(76, 22));
            foreach (var o in new[] { UIFactory.GetButtonText(btnHistOlder), UIFactory.GetButtonText(btnHistNewer), txtHistPos })
                if (o != null) { UIFactory.SetOverflowMode(o, 2); UIFactory.SetWordWrap(o, false); }
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
            btnSort = UIFactory.CreateButton("PcBSort", hdr.transform, "", 13f, C_WHITE, C_BTN, CycleSort, sizeDelta: new Vector2(220, 24));
            btnSortTxt = UIFactory.GetButtonText(btnSort);
            if (btnSortTxt != null) { UIFactory.SetOverflowMode(btnSortTxt, 2); UIFactory.SetWordWrap(btnSortTxt, false); }

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
            // Click-to-view (2026-09-13): the tiles have no View button; the
            // picture and the text block open the card, and this line says so.
            UIFactory.CreateText("PcBHint", binderRoot.transform, "Click a card to view it", 12f, C_DIM, UIFactory.AlignMidCenter, sizeDelta: new Vector2(600, 18));
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
            // The face slot: an Image the fetched sprite is set on, aspect-preserving
            // and click-through (the tile's own buttons keep every click).
            t.face = UIFactory.CreatePanel(name + "_f", inner.transform, C_CARD);
            // Preferred size ZERO, explicitly: a UI Image reports its sprite's
            // pixel size as its preferred size, so once a 375x525 face landed
            // the slot asked the tile for 525 px, the layout went over budget,
            // and the 22 px action row below it was crushed to a sliver whose
            // labels then blanked under Truncate (Sid's binder screenshot,
            // 2026-09-12). With 0 the slot is purely flexible and takes what
            // is left after the row; preserveAspect letterboxes the picture.
            UIFactory.AddLE(t.face, prefW: 0, prefH: 0, flexH: 1, flexW: 1);
            PlayerCardFaces.SetFace(t.face, null);
            // The DISCARDED stamp: a centred label over the picture, shown only
            // for a discarded print whose face is still in the cache.
            t.faceMark = UIFactory.CreateText(name + "_fm", t.face.transform, "", 14f, C_WARN, UIFactory.AlignMidCenter, sizeDelta: new Vector2(TILE_W - 24, 40));
            UIFactory.SetOverflowMode(t.faceMark, 2); UIFactory.SetWordWrap(t.faceMark, true);
            t.faceMarkGO = (t.faceMark as Component)?.gameObject;
            if (t.faceMarkGO != null) t.faceMarkGO.SetActive(false);
            t.face.SetActive(false);
            t.textBlock = new GameObject(name + "_tb");
            t.textBlock.transform.SetParent(inner.transform, false);
            t.textBlock.AddComponent<RectTransform>();
            UIFactory.AddVLG(t.textBlock, spacing: 1);
            UIFactory.AddLE(t.textBlock, flexH: 1);
            // Click-to-view (2026-09-13): the picture and the text block open
            // the card (exactly one of the two is active). The handlers sit on
            // those two and not on the tile root, so the action row below
            // keeps its own buttons; ClickHandler hit-tests its own rect and
            // honours the scroll view's mask like every other handler.
            var tile = t;
            foreach (var go in new[] { t.face, t.textBlock })
            {
                var ch = go.AddComponent<ClickHandler>();
                ch.onClick = () => OnTileClick(tile);
            }
            var tb = t.textBlock.transform;
            float w = TILE_W - 18f;
            t.txtName = UIFactory.CreateText(name + "_n", tb, "", 15f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 20));
            t.txtTitle = UIFactory.CreateText(name + "_t", tb, "", 12f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 16));
            t.txtL1 = UIFactory.CreateText(name + "_1", tb, "", 12f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 16));
            t.txtL2 = UIFactory.CreateText(name + "_2", tb, "", 12f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 16));
            t.txtL3 = UIFactory.CreateText(name + "_3", tb, "", 12f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 16));
            t.txtL4 = UIFactory.CreateText(name + "_4", tb, "", 11f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 16));
            t.txtMark = UIFactory.CreateText(name + "_m", tb, "", 12f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(w, 16));
            t.txtSign = UIFactory.CreateText(name + "_s", tb, "", 13f, C_SIGN, UIFactory.AlignMidCenter, sizeDelta: new Vector2(w, 18));
            // No Truncate at these heights (c4): a taller fallback font (Cyrillic,
            // Greek) must not blank a line — MailUI's rule.
            foreach (var o in new[] { t.txtName, t.txtTitle, t.txtL1, t.txtL2, t.txtL3, t.txtL4, t.txtMark, t.txtSign })
            {
                // TMP Masking (c5): a long line is clipped at its cell, never painted
                // over the neighbour (Overflow) and never blanked (the c4 concern)
                UIFactory.SetOverflowMode(o, 2); UIFactory.SetWordWrap(o, false);
            }
            if (withActions)
            {
                t.actions = new GameObject(name + "_a");
                t.actions.transform.SetParent(inner.transform, false);
                t.actions.AddComponent<RectTransform>();
                UIFactory.AddHLG(t.actions, spacing: 4, forceExpandH: true);
                // minH as well as prefH: a row with no minimum is the first
                // thing a layout over budget shrinks to nothing (#449's rule).
                UIFactory.AddLE(t.actions, prefH: 22, minH: 22, flexH: 0);
                t.btnDiscard = UIFactory.CreateButton(name + "_d", t.actions.transform, "Discard", 11f, C_WHITE, C_DANGER, () => OnDiscardClick(tile, false), sizeDelta: new Vector2(76, 20));
                t.btnDiscardTxt = UIFactory.GetButtonText(t.btnDiscard);
                t.btnDupes = UIFactory.CreateButton(name + "_dd", t.actions.transform, "", 11f, C_WHITE, C_DANGER, () => OnDiscardClick(tile, true), sizeDelta: new Vector2(84, 20));
                t.btnDupesTxt = UIFactory.GetButtonText(t.btnDupes);
                // Masking, never Truncate, on the two labels: the tile's own
                // text lines opted out above and the buttons had not (c4/c5).
                foreach (var o in new[] { t.btnDiscardTxt, t.btnDupesTxt })
                    if (o != null) { UIFactory.SetOverflowMode(o, 2); UIFactory.SetWordWrap(o, false); }
            }
            t.root.SetActive(false);
            return t;
        }

        private static string RatingLine(ApiClient.PcPrint p)
        {
            // a subject without a recorded peak (null on the wire) peaks at their rating (c4)
            float peak = p.peak_rating > 0f ? Mathf.Max(p.rating, p.peak_rating) : p.rating;
            return I18n.TrF("Rating {0} | peak {1}", Mathf.RoundToInt(p.rating), Mathf.RoundToInt(peak));
        }

        private static string RankLine(ApiClient.PcPrint p) => p.board_rank > 0
            ? I18n.TrF("Rank #{0} | {1}W {2}L", p.board_rank, p.series_wins, p.series_losses)
            : I18n.TrF("Unranked | {0}W {1}L", p.series_wins, p.series_losses);   // off the board = "Unranked" (design v4 §2)

        /// <summary>Design v4 §10 "tile actions: view": the full card in the
        /// info popup. Raw body — the subject's name never passes I18n.Tr
        /// (#602); the labels are translated line by line.</summary>
        private static GameObject cardPopupGO, cardPopupImg;
        private static int cardPopupSeq;
        private static int cardPopupFrame = -1;   // the frame the popup last opened or closed on (OnTileClick)

        /// <summary>The card view (v22 §5.6): the print's own 750x1050 face at fit
        /// height on the mod's overlay canvas, click anywhere to close. A print with
        /// no face revision, or a face that could not be had, falls back to the text
        /// popup below.</summary>
        private static void ShowCard(Tile t)
        {
            var p = t?.print;
            if (p == null) return;
            if (string.IsNullOrEmpty(p.face_rev)) { ShowCardText(p); return; }
            try
            {
                HideCardPopup();
                var overlay = NativeUI.OverlayRoot;
                if (overlay == null) { ShowCardText(p); return; }
                cardPopupGO = new GameObject("CR_PcCard");
                cardPopupFrame = Time.frameCount;
                cardPopupGO.hideFlags = HideFlags.HideAndDontSave;
                cardPopupGO.transform.SetParent(overlay, false);
                var rt = cardPopupGO.AddComponent<RectTransform>();
                rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one;
                rt.offsetMin = Vector2.zero; rt.offsetMax = Vector2.zero;
                var bd = UIFactory.CreatePanel("BD", cardPopupGO.transform, new Color(0f, 0f, 0f, 0.72f));
                var bdRT = bd.GetComponent<RectTransform>();
                bdRT.anchorMin = Vector2.zero; bdRT.anchorMax = Vector2.one;
                bdRT.offsetMin = Vector2.zero; bdRT.offsetMax = Vector2.zero;
                var bdClick = bd.AddComponent<ClickHandler>();
                bdClick.bypassModalBlock = true;
                // Not on the frame that opened it: the tile's handler and this
                // one both poll the same mouse-down (OnTileClick).
                bdClick.onClick = () => { if (Time.frameCount != cardPopupFrame && ClickGuard.Claim(bd)) HideCardPopup(); };
                var img = UIFactory.CreatePanel("Face", cardPopupGO.transform, C_CARD);
                var irt = img.GetComponent<RectTransform>();
                irt.anchorMin = new Vector2(0.5f, 0.5f); irt.anchorMax = new Vector2(0.5f, 0.5f);
                irt.pivot = new Vector2(0.5f, 0.5f);
                float h = 1010f;
                try
                {
                    var crt = overlay.GetComponent<RectTransform>();
                    if (crt != null && crt.rect.height > 200f) h = Mathf.Min(1010f, crt.rect.height - 40f);
                }
                catch { }
                irt.sizeDelta = new Vector2(h * PlayerCardFaces.CARD_W / PlayerCardFaces.CARD_H, h);
                cardPopupImg = img;
                PlayerCardFaces.SetFace(img, null);
                int seq = ++cardPopupSeq, ep = uiEpoch, gen = PlayerCardFaces.Generation;
                var hit = PlayerCardFaces.Cached(p.print_id, p.face_rev, p.face_locale, "card");
                if (hit != null) { PlayerCardFaces.SetFace(img, hit); return; }
                var print = p;
                PlayerCardFaces.Get(p.print_id, p.face_rev, p.face_locale, "card", spr =>
                {
                    if (seq != cardPopupSeq || ep != uiEpoch || gen != PlayerCardFaces.Generation) return;
                    if (spr == null) { HideCardPopup(); ShowCardText(print); return; }
                    if (cardPopupImg != null) PlayerCardFaces.SetFace(cardPopupImg, spr);
                });
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[PC] card view failed: {ex.Message}");
                HideCardPopup();
                ShowCardText(p);
            }
        }

        /// <summary>Click-to-view (2026-09-13). The frame check is the same-frame
        /// guard: ClickHandler polls the mouse-down, so the backdrop a click
        /// creates would see the same press in its own Update, and the press
        /// that closes the popup reaches the tile beneath in the frame the
        /// modal block lifts.</summary>
        private static void OnTileClick(Tile t)
        {
            if (t == null || t.print == null || Time.frameCount == cardPopupFrame) return;
            if (!ClickGuard.Claim(t.root)) return;
            ShowCard(t);
        }

        internal static void HideCardPopup()
        {
            cardPopupSeq++;
            cardPopupImg = null;
            if (cardPopupGO != null) { cardPopupFrame = Time.frameCount; try { UnityEngine.Object.Destroy(cardPopupGO); } catch { } cardPopupGO = null; }
        }

        /// <summary>The rarity strip a card shows wherever it is drawn: band,
        /// FOIL, SIGNED, and the pull's own copy count.
        ///
        /// One function because two call sites drew this strip and only one of
        /// them would have gained the copy count -- the popup and the tile would
        /// then disagree about the same print. `dup_at_pull` is the count the
        /// server took at mint, sequentially, BEFORE this slot's own insert
        /// (v22 7): 0 is NEW, n is DUPLICATE +n. The collection grid carries no
        /// such field and an answer from an api that predates it carries -1;
        /// both say nothing here rather than calling every card new.</summary>
        /// <summary>The tier the card draws in its RANK slot, then the equipped
        /// shop title when the player wears one (the server sends `title` only
        /// for a real shop title; rank-title wearers get null). Each half is
        /// translated on its own: the tier is a catalogue value, and the shop
        /// title goes through the same runtime lookup the Shop list and the
        /// profile card use for catalogue names (a catalogue miss reads as
        /// the English the server sent).</summary>
        private static string TitleLine(ApiClient.PcPrint p)
        {
            string tier = string.IsNullOrEmpty(p.rank_name) ? "" : I18n.Tr(p.rank_name);
            string shop = string.IsNullOrEmpty(p.title) ? "" : I18n.Tr(p.title);
            if (shop.Length == 0) return tier;
            return tier.Length > 0 ? tier + "  ·  " + shop : shop;
        }

        private static string DiscardedLine(ApiClient.PcPrint p)
        {
            return p.discard_shards > 0
                ? I18n.TrF("DISCARDED (+{0} shards)", p.discard_shards)
                : I18n.TrC("pack open", "DISCARDED");
        }

        private static string MarkLine(ApiClient.PcPrint p)
        {
            string mark = RarityLabel(p.rarity);
            if (p.foil) mark += " | " + I18n.Tr("FOIL");
            if (p.signed) mark += " | " + I18n.Tr("SIGNED");
            // Contextual keys: bare "NEW" and "DUPLICATE" agree with "card" in
            // most of the locales we carry, and the same two English words are
            // reused elsewhere with a different gender and number -- the card
            // rarity column learned this already (Sept 6 item e).
            if (p.dup_at_pull == 0) mark += " | " + I18n.TrC("pack open", "NEW");
            else if (p.dup_at_pull > 0) mark += " | " + I18n.TrCF("pack open", "DUPLICATE +{0}", p.dup_at_pull);
            return mark;
        }

        private static void ShowCardText(ApiClient.PcPrint p)
        {
            if (p == null) return;
            string name = SafeName(p);
            var lines = new List<string>();
            string mark = MarkLine(p);
            lines.Add(mark);
            string title = TitleLine(p);
            if (title.Length > 0) lines.Add(title);
            lines.Add(RatingLine(p));
            lines.Add(RankLine(p));
            string tc = p.top_card ?? "";
            try { tc = GameStateWatcher.StripRichText(tc); } catch { }
            if (tc.Length > 0) lines.Add(I18n.TrF("Top card: {0}", tc));
            lines.Add(I18n.TrF("Pool #{0} | Ed. {1} | {2}", p.pool_rank, p.edition_id ?? "", DateOnly(p.minted_at).Replace('-', '/')));
            lines.Add(I18n.TrF("Print {0}", p.print_id ?? ""));
            if (p.signed) lines.Add("~ " + name + " ~");
            try { NativeUI.ShowInfoPopupRaw(name, string.Join("\n\n", lines.ToArray())); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PC] card view failed: {ex.Message}"); }
        }

        private static void FillTile(Tile t, ApiClient.PcPrint p, int dupes)
        {
            if (t == null || t.root == null) return;
            t.print = p; t.dupes = dupes;
            t.bindSeq++;
            if (p == null) { ShowTileText(t); t.root.SetActive(false); return; }
            t.root.SetActive(true);
            UIFactory.SetImageColor(t.root, FrameColor(p.rarity, p.foil));
            BindFace(t, p);
            string name = SafeName(p);
            UIFactory.SetTextRaw(t.txtName, name);
            UIFactory.SetTextRaw(t.txtTitle, TitleLine(p));
            UIFactory.SetTextRaw(t.txtL1, RatingLine(p));
            UIFactory.SetTextRaw(t.txtL2, RankLine(p));
            string tc = p.top_card ?? "";
            try { tc = GameStateWatcher.StripRichText(tc); } catch { }
            if (tc.Length > 18) tc = tc.Substring(0, 18);
            UIFactory.SetTextRaw(t.txtL3, tc.Length > 0 ? I18n.TrF("Top card: {0}", tc) : "");
            UIFactory.SetTextRaw(t.txtL4, I18n.TrF("Pool #{0} | Ed. {1} | {2}", p.pool_rank, p.edition_id ?? "", DateOnly(p.minted_at).Replace('-', '/')));
            // A discarded print stays where it was pulled, stamped (Sid,
            // 2026-09-12): the mark line says so in the text block, the same
            // words sit over the picture when the face is still cached, and the
            // picture is dimmed so the stamp reads on any band colour.
            string mark = p.discarded ? DiscardedLine(p) : MarkLine(p);
            UIFactory.SetTextRaw(t.txtMark, mark);
            if (t.faceMark != null) UIFactory.SetTextRaw(t.faceMark, p.discarded ? "<b>" + DiscardedLine(p) + "</b>" : "");
            if (t.faceMarkGO != null) t.faceMarkGO.SetActive(p.discarded);
            UIFactory.SetImageColor(t.face, p.discarded ? new Color(0.42f, 0.42f, 0.48f, 1f) : Color.white);
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

        /// <summary>The face of this print at tile size, if the server has one:
        /// the cache paints it now, else the fetch paints it when it lands AND the
        /// binding still holds (tile sequence, print id, UI epoch, cache
        /// generation). Until then — and for good on a failure — the text block
        /// shows, so a tile is never blank.</summary>
        private static void BindFace(Tile t, ApiClient.PcPrint p)
        {
            if (string.IsNullOrEmpty(p.face_rev)) { ShowTileText(t); return; }
            var hit = PlayerCardFaces.Cached(p.print_id, p.face_rev, p.face_locale, "tile");
            if (hit != null) { ShowTileFace(t, hit); return; }
            // The face route answers 404 for a discarded print by design (its
            // picture is not fetchable once the card is gone), and the strip
            // used to ask three times and fall to text anyway. Cached = shown,
            // stamped; not cached = the text block, stamped. Never a fetch.
            if (p.discarded) { ShowTileText(t); return; }
            ShowTileText(t);
            int seq = t.bindSeq, ep = uiEpoch, gen = PlayerCardFaces.Generation;
            var tile = t; string pid = p.print_id;
            PlayerCardFaces.Get(p.print_id, p.face_rev, p.face_locale, "tile", spr =>
            {
                if (spr == null || seq != tile.bindSeq || ep != uiEpoch || gen != PlayerCardFaces.Generation) return;
                if (tile.print == null || tile.print.print_id != pid) return;
                ShowTileFace(tile, spr);
            });
        }

        private static void ShowTileFace(Tile t, Sprite spr)
        {
            if (t.face == null) return;
            PlayerCardFaces.SetFace(t.face, spr);
            t.face.SetActive(true);
            if (t.textBlock != null) t.textBlock.SetActive(false);
        }

        private static void ShowTileText(Tile t)
        {
            if (t.face != null) { PlayerCardFaces.SetFace(t.face, null); t.face.SetActive(false); }
            if (t.textBlock != null) t.textBlock.SetActive(true);
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

            if (view == View.Open && me != null) EnsureHistory(id);
            if (pendingHistoryIndex >= 0 && !historyInFlight)
            {
                // the page a click asked for has landed (or failed): land on it if it exists
                if (pendingHistoryIndex < packHistory.Count) historyIndex = pendingHistoryIndex;
                pendingHistoryIndex = -1;
            }
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
                UIFactory.SetTextRaw(txtPaid, me.paid_cap_exempt
                    ? I18n.TrF("{0} paid packs today - no daily limit on this account - {1} cards each", me.paid_today, me.prints_per_pack)
                    : I18n.TrF("{0} of {1} paid packs today - {2} cards each", me.paid_today, me.paid_packs_per_day, me.prints_per_pack));
                bool capped = !me.paid_cap_exempt && me.paid_today >= me.paid_packs_per_day;
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
            // reveal strip = the pack-history pager (index 0 is the newest)
            if (historyIndex >= packHistory.Count) historyIndex = Math.Max(0, packHistory.Count - 1);
            var shown = packHistory.Count > 0 ? packHistory[historyIndex] : null;
            bool hasLast = shown != null && shown.prints != null && shown.prints.Count > 0;
            if (lastStrip != null) lastStrip.transform.parent.gameObject.SetActive(hasLast || historyInFlight);
            if (hasLast)
            {
                int total = Math.Max(historyTotal, packHistory.Count);
                int ordinal = total - historyIndex;   // packs count up from the oldest
                UIFactory.SetTextRaw(txtLastHdr, historyIndex == 0
                    ? I18n.TrF("Your last pack ({0}) - {1}", PackSourceLabel(shown), DateOnly(shown.opened_at))
                    : I18n.TrF("Pack {0} of {1} ({2}) - {3}", ordinal, total, PackSourceLabel(shown), DateOnly(shown.opened_at)));
                UIFactory.SetTextRaw(txtHistPos, I18n.TrF("{0} / {1}", ordinal, total));
                bool olderExists = historyIndex + 1 < packHistory.Count || (!string.IsNullOrEmpty(historyNextBefore) && !historyExhausted);
                UIFactory.SetImageColor(btnHistOlder, olderExists && !historyInFlight ? C_BTN : C_PANEL);
                UIFactory.SetImageColor(btnHistNewer, historyIndex > 0 ? C_BTN : C_PANEL);
                for (int i = 0; i < revealTiles.Length; i++)
                    FillTile(revealTiles[i], i < shown.prints.Count ? shown.prints[i] : null, 0);
            }
            else if (historyInFlight)
            {
                UIFactory.SetTextRaw(txtLastHdr, I18n.Tr("Loading your packs..."));
                UIFactory.SetTextRaw(txtHistPos, "");
                for (int i = 0; i < revealTiles.Length; i++) FillTile(revealTiles[i], null, 0);
            }
        }

        // ── pack history (the strip's pager) ──────────────────────────────
        // Newest first; index 0 is what "Your last pack" always showed. A pack
        // this client opens is inserted at once (it is the answer the open
        // produced), where the server's order puts it -- the head, unless a
        // newer pack from another device is already loaded; the server's
        // pages fill in behind it, deduped by pack_id, one page per click past
        // the loaded end. The list keeps the server's own order, (opened_at,
        // id) DESC -- the keyset pair its cursor pages by -- on every
        // insertion path, so a merged page lands where the server has it.
        private static readonly List<ApiClient.PcPackAnswer> packHistory = new List<ApiClient.PcPackAnswer>();
        private static string historyNextBefore;
        private static bool historyLoaded, historyInFlight, historyExhausted;
        private static int historyIndex, historyTotal;
        // The chain's count is its FIRST page's total, kept for the chain's
        // life: a later page's total can count a pack opened on another
        // device since, which this anchored chain never reaches (its cursor
        // pages backwards from the head it started at). That first page's
        // head is the anchor a head insert is counted against: a pack this
        // client opens after it is one more; a delayed open answer for a
        // pack older than it was already in that total, loaded rows or not.
        private static bool historyAnchored;
        private static ApiClient.PcPackAnswer historyAnchor;
        private static float historyFailedAt = -100f;
        private static GameObject btnHistOlder, btnHistNewer;
        private static object txtHistPos;
        private static int pendingHistoryIndex = -1;
        // Which server page each loaded pack came from: pack_id -> the cursor
        // that page was asked with ("" for the newest page), so the page that
        // holds a tile can be asked for again. A pack this client inserted at
        // the head has no entry and counts as the newest page.
        private static readonly Dictionary<string, string> historyPageOf = new Dictionary<string, string>(StringComparer.Ordinal);
        // The cursors with a refetch on its way; the face keys
        // (print|revision|locale) waiting on one, each with the cursor it
        // waits on; and the keys that already spent their one refetch. A key
        // is spent when its page comes back CARRYING the print -- never at
        // the ask -- so a page that comes back without it (the print moved
        // past the page's end) leaves the key free for the chain loaded again.
        private static readonly HashSet<string> historyRefetching = new HashSet<string>(StringComparer.Ordinal);
        private sealed class FaceRefetch { internal string key, printId, cursor; }
        private static readonly List<FaceRefetch> faceRefetchPending = new List<FaceRefetch>();
        private static readonly HashSet<string> faceRefetched = new HashSet<string>(StringComparer.Ordinal);
        // Bumped by every reset (an identity edge, a language change): a page
        // answer that left before the reset is dropped on landing instead of
        // merging the old locale's face keys into the new list.
        private static int historyGen;
        private static bool historyHooked;

        /// <summary>Once, from the first build: the two signals the loaded
        /// history reacts to. The server keys a print's face revision under
        /// the answer's locale, so a language change drops the loaded pages
        /// and the next Open-tab paint loads them again in the new language;
        /// a face answer of 404 for a print the history holds means that
        /// revision moved on (the name and the picture on a card are live)
        /// and its page is asked for again. Signals, not a timer: nothing
        /// here polls.</summary>
        private static void HookHistorySignals()
        {
            if (historyHooked) return;
            historyHooked = true;
            try { I18n.LocaleChanged += OnHistoryLocaleChanged; } catch (Exception ex) { Plugin.Log.LogWarning("[PC] locale hook failed: " + ex.Message); }
            try { ApiClient.PcFaceNotFound += OnHistoryFaceNotFound; } catch (Exception ex) { Plugin.Log.LogWarning("[PC] face hook failed: " + ex.Message); }
        }

        private static void OnHistoryLocaleChanged()
        {
            HistoryReset();
            try { NativeUI.MarkDirty(); } catch { }
        }

        private static string FaceRefetchKey(string printId, string faceRev, string locale)
            => printId + "|" + faceRev + "|" + (string.IsNullOrEmpty(locale) ? "en" : locale);

        /// <summary>A face request answered 404. When a loaded history page
        /// holds that print under exactly that revision and locale, the page
        /// is fetched again and the strip repaints from the fresh revisions.
        /// The key spends its one refetch when that page comes back CARRYING
        /// the print -- under a new revision, or still the old one, which is
        /// a revision the face box does not serve yet and costs one page
        /// fetch and not a loop. A page that comes back WITHOUT the print (a
        /// pack opened on another device pushed it past the newest page's
        /// end, where the anchored chain cannot follow) spends nothing: the
        /// chain is dropped and the next paint loads it again from the head,
        /// every page fresh, so the print is refreshed by whichever page
        /// holds it. A key already waiting on a page is not asked twice; a
        /// failed refetch is asked again no sooner than the pager's own 30 s.
        /// A discarded print's face answers 404 by design and never gets
        /// here; a history not loaded yet has its first load still ahead of
        /// it.</summary>
        private static void OnHistoryFaceNotFound(string printId, string faceRev, string locale)
        {
            if (string.IsNullOrEmpty(printId) || string.IsNullOrEmpty(faceRev) || !historyLoaded) return;
            var id = LocalId();
            if (id == null || !SessionReady) return;
            string want = string.IsNullOrEmpty(locale) ? "en" : locale;
            string cursor = null; bool held = false;
            foreach (var a in packHistory)
            {
                if (a.prints == null) continue;
                foreach (var p in a.prints)
                {
                    if (p.print_id != printId || p.face_rev != faceRev || p.discarded) continue;
                    if ((string.IsNullOrEmpty(p.face_locale) ? "en" : p.face_locale) != want) continue;
                    held = true;
                    historyPageOf.TryGetValue(a.pack_id ?? "", out cursor);
                    break;
                }
                if (held) break;
            }
            if (!held) return;
            string key = FaceRefetchKey(printId, faceRev, locale);
            if (faceRefetched.Contains(key) || FaceRefetchWaiting(key)) return;
            if (Now - historyFailedAt < 30f) return;
            faceRefetchPending.Add(new FaceRefetch { key = key, printId = printId, cursor = cursor ?? "" });
            RefetchHistoryPage(id, cursor ?? "");
        }

        private static bool FaceRefetchWaiting(string key)
        {
            for (int i = 0; i < faceRefetchPending.Count; i++) if (faceRefetchPending[i].key == key) return true;
            return false;
        }

        /// <summary>One more fetch of a page already loaded, merged in place;
        /// the pager's cursor and end are left alone. A page already on its
        /// way is not asked for twice -- its answer covers every key that
        /// pointed at it.</summary>
        private static void RefetchHistoryPage(string id, string cursor)
        {
            if (!historyRefetching.Add(cursor)) return;
            int ep = uiEpoch, gen = historyGen;
            ApiClient.FetchPcPacks(id, cursor.Length == 0 ? null : cursor, (ok, resp, h) =>
            {
                if (ep != uiEpoch || gen != historyGen) return;   // reset since: the sets went with it
                historyRefetching.Remove(cursor);
                if (!ok || h == null)
                {
                    Plugin.Log.LogWarning("[PC] pack history refetch failed: " + ApiClient.PcErrorCode(resp));
                    historyFailedAt = Now;
                    faceRefetchPending.RemoveAll(r => r.cursor == cursor);   // unspent: the next 404 asks again after the pager's 30 s
                    return;
                }
                MergeHistoryPage(h, cursor);
                SettleFaceRefetches(h, cursor);
                NativeUI.MarkDirty();
            });
        }

        /// <summary>A refetched page landed: every key that waited on it is
        /// settled against the answer. The answer carries the print: the key
        /// is spent (a new revision has a new key of its own; the old one
        /// would only ask this same page again). It does not: the print
        /// moved past this page's end, so the chain is dropped and loaded
        /// again from the head -- the reset clears the key with the rest,
        /// and the fresh page that holds the print brings its revision.</summary>
        private static void SettleFaceRefetches(ApiClient.PcPackHistory h, string cursor)
        {
            bool moved = false;
            for (int i = faceRefetchPending.Count - 1; i >= 0; i--)
            {
                var r = faceRefetchPending[i];
                if (r.cursor != cursor) continue;
                faceRefetchPending.RemoveAt(i);
                if (AnswerHoldsPrint(h, r.printId)) faceRefetched.Add(r.key); else moved = true;
            }
            if (!moved) return;
            Plugin.Log.LogInfo("[PC] pack history: a refetched page no longer holds its print; loading the history again from the head");
            HistoryReset();
        }

        private static bool AnswerHoldsPrint(ApiClient.PcPackHistory h, string printId)
        {
            foreach (var a in h.packs)
            {
                if (a == null || a.prints == null) continue;
                foreach (var p in a.prints) if (p.print_id == printId) return true;
            }
            return false;
        }

        /// <summary>The server's order: (opened_at, id) DESC, the pair its
        /// keyset cursor pages by. Pack ids are canonical lowercase UUID text
        /// and opened_at is the server's own ISO text, so an ordinal compare
        /// on each agrees with the database. Never the timestamp alone: two
        /// packs opened in the same instant would then trade places between
        /// one page and the next.</summary>
        private static int ServerOrder(ApiClient.PcPackAnswer x, ApiClient.PcPackAnswer y)
        {
            int c = string.CompareOrdinal(y.opened_at ?? "", x.opened_at ?? "");
            return c != 0 ? c : string.CompareOrdinal(y.pack_id ?? "", x.pack_id ?? "");
        }

        /// <summary>A page answer into the list: a pack the list holds is
        /// replaced by the fresh copy (new face revisions, the server's
        /// discard marks), one it does not hold is added, and the list is put
        /// back in the server's order. Every pack remembers the cursor of the
        /// page that brought it. The first page anchors the chain: its total
        /// is the chain's count and its head the anchor (see the fields); a
        /// later page's total is not adopted.</summary>
        private static void MergeHistoryPage(ApiClient.PcPackHistory h, string cursor)
        {
            foreach (var a in h.packs)
            {
                if (a == null || string.IsNullOrEmpty(a.pack_id)) continue;
                int at = packHistory.FindIndex(x => x.pack_id == a.pack_id);
                if (at >= 0) packHistory[at] = a; else packHistory.Add(a);
                historyPageOf[a.pack_id] = cursor ?? "";
            }
            packHistory.Sort(ServerOrder);
            if (!historyAnchored)
            {
                historyAnchored = true;
                historyTotal = h.total;
                historyAnchor = null;
                foreach (var a in h.packs)
                    if (a != null && !string.IsNullOrEmpty(a.pack_id) && (historyAnchor == null || ServerOrder(a, historyAnchor) < 0)) historyAnchor = a;
            }
            lastPack = packHistory.Count > 0 ? packHistory[0] : lastPack;
        }

        /// <summary>A pack this client opened, or a recovered open answer,
        /// into the list where the server's order puts it -- a newer pack from
        /// another device may already sit above it (a refetched newest page
        /// brings one), and index 0 would then put the list out of the order
        /// nothing else repairs. The strip lands on it. For the count: a pack
        /// the list already held moves and the total stays; one it did not
        /// hold is one more only when it is newer than the chain's anchor,
        /// since a delayed answer for a pack older than the anchor was already
        /// in the first page's total whether or not its row is loaded. Before
        /// the chain is anchored nothing is counted here: the first page's
        /// total is what counts.</summary>
        private static void HistoryInsertHead(ApiClient.PcPackAnswer a)
        {
            if (a == null || string.IsNullOrEmpty(a.pack_id)) return;
            bool absent = packHistory.RemoveAll(x => x.pack_id == a.pack_id) == 0;
            int at = 0;
            while (at < packHistory.Count && ServerOrder(packHistory[at], a) < 0) at++;
            packHistory.Insert(at, a);
            historyIndex = at;
            if (absent && historyAnchored && (historyAnchor == null || ServerOrder(a, historyAnchor) < 0)) historyTotal++;
        }

        private static void HistoryReset()
        {
            historyGen++;
            packHistory.Clear(); historyNextBefore = null;
            historyPageOf.Clear(); historyRefetching.Clear(); faceRefetched.Clear(); faceRefetchPending.Clear();
            historyLoaded = historyInFlight = historyExhausted = false;
            historyAnchored = false; historyAnchor = null;
            historyIndex = historyTotal = 0; historyFailedAt = -100f; pendingHistoryIndex = -1;
        }

        /// <summary>First page on the first Open-tab paint with a session; one
        /// retry per 30 s after a failure, never a loop.</summary>
        private static void EnsureHistory(string id)
        {
            if (historyLoaded || historyInFlight || id == null || !SessionReady) return;
            if (Now - historyFailedAt < 30f) return;
            LoadHistoryPage(id);
        }

        private static void LoadHistoryPage(string id)
        {
            if (historyInFlight) return;
            string before = historyLoaded ? historyNextBefore : null;
            if (historyLoaded && string.IsNullOrEmpty(before)) { historyExhausted = true; return; }
            historyInFlight = true;
            int ep = uiEpoch, gen = historyGen;
            NativeUI.MarkDirty();
            ApiClient.FetchPcPacks(id, before, (ok, resp, h) =>
            {
                if (ep != uiEpoch || gen != historyGen) return;   // reset since: its flags went with it
                historyInFlight = false;
                if (!ok || h == null)
                {
                    historyFailedAt = Now;
                    Plugin.Log.LogWarning("[PC] pack history page failed: " + ApiClient.PcErrorCode(resp));
                    NativeUI.MarkDirty();
                    return;
                }
                MergeHistoryPage(h, before ?? "");
                historyNextBefore = h.next_before;
                historyExhausted = string.IsNullOrEmpty(h.next_before);
                historyLoaded = true;
                NativeUI.MarkDirty();
            });
        }

        private static void PageHistory(int delta)
        {
            var id = LocalId();
            int next = historyIndex + delta;
            if (next < 0) return;
            if (next >= packHistory.Count)
            {
                // past the loaded end: fetch the next page, then land on it
                if (historyExhausted || historyInFlight || id == null) return;
                int want = next;
                LoadHistoryPage(id);
                pendingHistoryIndex = want;
                return;
            }
            historyIndex = next;
            NativeUI.MarkDirty();
        }

        /// <summary>A print this client discarded, wherever the history holds
        /// it: stamped in place, never removed (Sid, 2026-09-12).</summary>
        private static void HistoryMarkDiscarded(string printId, int shards)
        {
            if (string.IsNullOrEmpty(printId)) return;
            foreach (var a in packHistory)
                if (a.prints != null)
                    foreach (var p in a.prints)
                        if (p.print_id == printId) { p.discarded = true; if (shards > 0) p.discard_shards = shards; }
            if (lastPack != null && lastPack.prints != null)
                foreach (var p in lastPack.prints)
                    if (p.print_id == printId) { p.discarded = true; if (shards > 0) p.discard_shards = shards; }
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

        private static void CycleSort()
        {
            binderSort = (Sort)(((int)binderSort + 1) % 5);
            binderPage = 0;
            NativeUI.MarkDirty();
        }

        private static string SortLabel(Sort s)
        {
            switch (s)
            {
                case Sort.Rarity: return I18n.Tr("Rarity");
                case Sort.Edition: return I18n.Tr("Edition");
                case Sort.Date: return I18n.Tr("Date obtained");
                case Sort.Position: return I18n.Tr("Position");
                default: return I18n.Tr("Name");
            }
        }

        private static int EditionNo(ApiClient.PcPrint p) { int e; return int.TryParse(p.edition_id ?? "", out e) ? e : int.MaxValue; }
        private static int BoardKey(ApiClient.PcPrint p) { return p.board_rank > 0 ? p.board_rank : int.MaxValue; }

        /// <summary>The binder order: the chosen key first, then the name order
        /// as the tiebreaker under every mode (and the whole order under Name),
        /// down to the print id so the order is total.</summary>
        private static int CompareForBinder(ApiClient.PcPrint a, ApiClient.PcPrint b)
        {
            int c;
            switch (binderSort)
            {
                case Sort.Rarity:
                    c = RarityOrder(a.rarity).CompareTo(RarityOrder(b.rarity)); if (c != 0) return c;
                    c = (b.foil ? 1 : 0).CompareTo(a.foil ? 1 : 0); if (c != 0) return c;
                    c = (b.signed ? 1 : 0).CompareTo(a.signed ? 1 : 0); if (c != 0) return c;
                    break;
                case Sort.Edition:
                    c = EditionNo(a).CompareTo(EditionNo(b)); if (c != 0) return c;
                    c = string.CompareOrdinal(a.edition_id ?? "", b.edition_id ?? ""); if (c != 0) return c;
                    c = RarityOrder(a.rarity).CompareTo(RarityOrder(b.rarity)); if (c != 0) return c;
                    break;
                case Sort.Date:
                    c = string.CompareOrdinal(b.minted_at ?? "", a.minted_at ?? ""); if (c != 0) return c;   // newest first
                    break;
                case Sort.Position:
                    c = BoardKey(a).CompareTo(BoardKey(b)); if (c != 0) return c;
                    c = a.pool_rank.CompareTo(b.pool_rank); if (c != 0) return c;
                    break;
            }
            c = string.Compare(SafeName(a), SafeName(b), StringComparison.OrdinalIgnoreCase); if (c != 0) return c;
            c = string.CompareOrdinal(a.card_id ?? "", b.card_id ?? ""); if (c != 0) return c;
            c = RarityOrder(a.rarity).CompareTo(RarityOrder(b.rarity)); if (c != 0) return c;
            c = (b.foil ? 1 : 0).CompareTo(a.foil ? 1 : 0); if (c != 0) return c;
            c = (b.signed ? 1 : 0).CompareTo(a.signed ? 1 : 0); if (c != 0) return c;
            c = string.CompareOrdinal(a.minted_at ?? "", b.minted_at ?? "");
            return c != 0 ? c : string.CompareOrdinal(a.print_id, b.print_id);
        }

        private static void RefreshBinder(ApiClient.PcMe me)
        {
            var col = ApiClient.CachedPcCollection;
            sorted.Clear(); faceCounts.Clear();
            if (col != null)
            {
                sorted.AddRange(col.prints);
                sorted.Sort(CompareForBinder);
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
            if (btnSortTxt != null) UIFactory.SetTextRaw(btnSortTxt, I18n.Tr("Sort:") + " " + SortLabel(binderSort));
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
                + (me != null && me.paid_cap_exempt
                    ? I18n.TrF("- Buy one for {0} gold or {1} shards. No daily limit on this account.", gold, shards)
                    : I18n.TrF("- Buy one for {0} gold or {1} shards, up to {2} paid packs a day.", gold, shards, cap)) + "\n\n"
                + I18n.TrF("Each pack holds {0} cards. A card's rarity is its player's rank in the card pool on the day of the pull: Legendary = #1, Epic #2-10, Rare #11-20, Uncommon #21-40, Common #41 and below. Odds per card: Common 60%, Uncommon 25%, Rare 11%, Epic 3.5%, Legendary 0.5%. Every card also rolls Foil (1 in 200) and Signed (1 in 2000) on its own.", per) + "\n\n"
                + I18n.Tr("Discarding a card gives shards by its rarity: Common 5, Uncommon 15, Rare 40, Epic 150, Legendary 600. Shards buy packs. Discards are one card at a time; the Dupes button discards every other copy of that exact card.") + "\n\n"
                + I18n.Tr("A card freezes its player's title, rating, record and rank as the leaderboard had them on the day it was pulled; the name and the picture stay live (a renamed player shows their new name). Every registered player who is not banned can be pulled; a public binder and pull announcements are your Settings, and deleting your data removes every card of you from every binder.");
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
            int ep = uiEpoch;
            ApiClient.PcClaimDaily(id, NewNonce(), (ok, resp) =>
            {
                if (ep != uiEpoch) return;   // identity changed meanwhile (c4)
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

        // A deadline, not a flag. Clearing it was the coroutine's last act, and
        // that coroutine is hosted on a behaviour ROUNDS destroys at a scene
        // change: the clear never ran, WaitForPortrait then answered "a wait is
        // already running" to every later click, and Buy and Open did nothing
        // at all for the rest of the process with no message and no error
        // (#508). One second past the coroutine's own cap, so in the normal
        // case the coroutine still clears it first.
        private static float portraitWaitUntil = -1f;
        private static bool PortraitWaiting { get { return Time.realtimeSinceStartup <= portraitWaitUntil; } }
        // When the last wait finished. The coroutine's last act is to call the
        // action that asked for the wait, and that action asks again — so
        // without this, a condition still true at the cap waits forever, five
        // seconds at a time, and the player's click never becomes anything.
        private static float portraitWaitedAt = -100f;
        private const float PORTRAIT_WAIT_ONCE = 10f;

        /// <summary>A pack opened while this client is still preparing its
        /// character picture would reveal against the initial disc, so the open
        /// waits — at most five seconds, then goes regardless (v22 §5.5).</summary>
        private static bool WaitForPortrait(Action go)
        {
            if (PortraitWaiting) return true;              // a wait is already running
            if (Now - portraitWaitedAt < PORTRAIT_WAIT_ONCE) return false;   // one wait per action
            if (!PortraitRender.Preparing || Plugin.Instance == null) return false;
            portraitWaitUntil = Time.realtimeSinceStartup + 6f;
            Say(I18n.Tr("Preparing your card picture..."));
            Plugin.Instance.StartCoroutine(PortraitWaitCo(uiEpoch, go));
            return true;
        }

        private static IEnumerator PortraitWaitCo(int ep, Action go)
        {
            float t0 = Now;
            while (PortraitRender.Preparing && Now - t0 < 5f) yield return null;
            portraitWaitUntil = -1f; portraitWaitedAt = Now;
            if (ep != uiEpoch) yield break;
            // The click authorised an action on a surface the player was
            // LOOKING at. Five seconds later they may have closed the page or
            // moved to another tab, and spending gold or opening a pack there
            // is not something they can see, undo, or connect to anything they
            // did. Refusing costs one more click when they come back.
            if (!NativeUI.PlayerCardsVisible)
            {
                Say(I18n.Tr("The picture was not ready in time - try again"), C_WARN);
                NativeUI.MarkDirty();
                yield break;
            }
            lastMsg = null;
            try { go(); } catch (Exception ex) { Plugin.Log.LogWarning($"[PC] open after portrait threw: {ex.Message}"); }
        }

        private static void BeginBuy(string pay)
        {
            var id = LocalId(); var me = ApiClient.CachedPcMe;
            if (id == null || me == null) { if (id != null) ApiClient.FetchPcMe(id, true); return; }
            if (!SessionReady) { Say(ReasonText("session_required"), C_WARN); return; }
            if (WaitForPortrait(() => BeginBuy(pay))) return;
            if (openInFlight && Now - openAt < 25f) return;
            if (HasIntent()) { Say(I18n.Tr("A pack is still being resolved - hold on"), C_WARN); MaybeRecover(true); return; }
            if (priceChangedAt >= 0f && ApiClient.PcMeDispatchedAt <= priceChangedAt)
            {
                // the price the server answered is not the one we hold: refresh first (c4);
                // the /pc/me that produced the cache must have LEFT after the change (c5)
                Say(I18n.Tr("Prices changed - refreshing them first"), C_WARN);
                ApiClient.FetchPcMe(id, true);
                return;
            }
            if (!me.paid_cap_exempt && me.paid_today >= me.paid_packs_per_day) { Say(ReasonText("daily_cap")); return; }
            int price = pay == "gold" ? me.price_gold : me.price_shards;
            string nonce = NewNonce();
            if (!WriteIntent("buy", nonce, pay, price))
            {
                Say(I18n.Tr("Could not record the purchase on this PC - nothing was sent to the server"), C_WARN);
                return;
            }
            openInFlight = true; openAt = Now; lastMsg = null;
            NativeUI.MarkDirty();
            int ep = uiEpoch;
            ApiClient.PcOpenPack(id, nonce, pay, price, (ok, resp) => { if (ep != uiEpoch) return; openInFlight = false; HandleAnswer(ok, resp, false); });
        }

        private static void BeginOpenHeld(string packId)
        {
            var id = LocalId();
            if (id == null || string.IsNullOrEmpty(packId)) return;
            if (!SessionReady) { Say(ReasonText("session_required"), C_WARN); return; }
            if (WaitForPortrait(() => BeginOpenHeld(packId))) return;
            if (openInFlight && Now - openAt < 25f) return;
            if (HasIntent()) { Say(I18n.Tr("A pack is still being resolved - hold on"), C_WARN); MaybeRecover(true); return; }
            if (!WriteIntent("pack", packId, "-", 0))
            {
                Say(I18n.Tr("Could not record the pack open on this PC - nothing was sent to the server"), C_WARN);
                return;
            }
            openInFlight = true; openAt = Now; lastMsg = null;
            NativeUI.MarkDirty();
            int ep = uiEpoch;
            ApiClient.PcOpenUnopened(id, packId, (ok, resp) => { if (ep != uiEpoch) return; openInFlight = false; HandleAnswer(ok, resp, false); });
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
                if (a != null) unparseableStrikes = 0;
                if (a == null)
                {
                    // A 2xx the client cannot read (c5/c6): the server answered from
                    // a committed row, so the intent's job - no second purchase of a
                    // pack in flight - is done. One or two are given to a transient
                    // truncation; the third retires the intent and points at the
                    // binder, where the prints are. Gold is never at stake here.
                    unparseableStrikes++;
                    Plugin.Log.LogWarning($"[PC] unparseable pack answer ({unparseableStrikes}): {(resp != null && resp.Length > 200 ? resp.Substring(0, 200) : resp)}");
                    if (unparseableStrikes >= UNPARSEABLE_RETIRE_STRIKES)
                    {
                        unparseableStrikes = 0; ClearIntent();
                        Say(I18n.Tr("Your pack was opened but its answer could not be read - check your binder"), C_WARN);
                    }
                    else Say(I18n.Tr("The pack answer could not be read - checking again shortly"), C_WARN);
                }
                else if (a.status == "done")
                {
                    lastPack = a; HistoryInsertHead(a); ClearIntent();
                    Say(I18n.TrF("Pack opened - {0} new cards", a.prints.Count), C_OK);
                    try { CompetitiveUI.ShowNotification(I18n.TrF("Pack opened - {0} new cards", a.prints.Count), C_OK, 3f); } catch { }
                    if (view == View.Binder) view = View.Open;
                }
                else if (a.status == "rejected")
                {
                    ClearIntent();
                    if (a.reason == "price_changed") priceChangedAt = Now;   // the refetch below re-arms BeginBuy (c4)
                    Say(ReasonText(a.reason ?? "http"), C_WARN);
                }
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
                        else if (http == 410)
                        {
                            // a plain 410 is the deleted account (a voided pack answers
                            // a named code): nothing of it remains to recover (c5)
                            ClearIntent(); Say(I18n.Tr("This account was deleted - there is no pack to recover"), C_WARN);
                        }
                        // Any other HTTP failure leaves the server's decision
                        // unknown: the intent stays, however long it takes (c4);
                        // only a committed answer, the not-found rule or the
                        // deleted account retires it.
                        else Say(I18n.Tr("The server could not answer about your pack - checking again shortly"), C_WARN);
                        break;
                    default:
                        {
                            // A named code retires the intent only when it is the
                            // COMMITTED row's own state (rejected / unopened /
                            // voided); anything else keeps it for recovery (c4).
                            string st = ApiClient.PcErrorStr(resp, "status");
                            if (st == "rejected" || st == "unopened" || st == "voided") ClearIntent();
                            if (code == "price_changed") priceChangedAt = Now;   // the refetch below re-arms BeginBuy (c4)
                            Say(ReasonText(code), C_WARN);
                            break;
                        }
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
            int ep = uiEpoch;
            ApiClient.PcPackResult(id, kind == "buy" ? reference : null, kind == "pack" ? reference : null,
                (ok, resp) => { if (ep != uiEpoch) return; recoverInFlight = false; HandleAnswer(ok, resp, true); });
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
            int ep = uiEpoch;
            ApiClient.PcDiscard(id, pid, (ok, resp) =>
            {
                if (ep != uiEpoch) return;   // identity changed meanwhile (c4)
                if (ok)
                {
                    discardDone++;
                    int gained = ApiClient.PcInt(ApiClient.PcTopLevel(resp, "shards_gained"));
                    discardShards += gained;
                    var col = ApiClient.CachedPcCollection;
                    if (col != null) col.prints.RemoveAll(x => x.print_id == pid);
                    HistoryMarkDiscarded(pid, gained);
                    DiscardNext(id);
                }
                else FinishDiscard(id, ApiClient.PcErrorCode(resp));
            });
        }

        private static void FinishDiscard(string id, string errorCode)
        {
            discardInFlight = false; discardQueue.Clear();
            // One line for both halves: what was discarded stays reported when
            // the next discard fails (c4).
            if (discardDone > 0 && errorCode != null)
                Say(I18n.TrF("Discarded {0} card(s) for {1} shards; then: {2}", discardDone, discardShards, ReasonText(errorCode)), C_WARN);
            else if (discardDone > 0)
                Say(I18n.TrF("Discarded {0} card(s) for {1} shards", discardDone, discardShards), C_OK);
            else if (errorCode != null) Say(ReasonText(errorCode), C_WARN);
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
                    dup_at_pull = i == 0 ? 0 : (i == 3 ? 2 : -1),   // one NEW, one DUPLICATE +2, the rest silent
                    discarded = i == 4, discard_shards = i == 4 ? 3 : -1,   // one DISCARDED stamp, for the screenshot
                });
            lastPack = a;
            HistoryInsertHead(a);
            historyLoaded = true; historyExhausted = true;   // the pager shows this one; no server page behind it
            view = mode == "binder" ? View.Binder : (mode == "info" ? View.Info : View.Open);
            if (mode == "binder" || mode == "binder-faces")
            {
                // A synthetic binder (this seat's account is a service account:
                // 403 on the collection): ten prints, two of them copies of one
                // card, so the Dupes button shows too. "binder-faces" also puts
                // a synthetic 375x525 face in the cache for every print — the
                // exact sprite size a fetched face has, so the action row is
                // verified under the same layout pressure the live binder has.
                var col = new ApiClient.PcCollection { owner_steam_id = "dev", owner_name = "Sid", is_public = true };
                string[] rar2 = { "legendary", "epic", "rare", "uncommon", "common", "common", "rare", "uncommon", "common", "common" };
                for (int i = 0; i < 10; i++)
                {
                    int subj = i == 9 ? 8 : i;   // the last two are the same card
                    col.prints.Add(new ApiClient.PcPrint
                    {
                        print_id = "devb" + i, card_id = "cardb" + subj, subject_player_id = "pb" + subj, subject_name = i == 0 ? "Sid" : "Player " + subj,
                        edition_id = "1", minted_at = "2026-09-12T00:00:00", rarity = rar2[i], foil = i == 2, signed = i == 0,
                        pool_rank = i + 1, rating = 1900 - i * 40, peak_rating = 1950 - i * 40, board_rank = i < 5 ? i + 1 : 0,
                        series_wins = 40 - i * 3, series_losses = 10 + i, top_card = "Bombs Away", title = i == 1 ? "Champion" : "", rank_name = "Advanced I",
                        source = "bought", slot = i % 5, dup_at_pull = -1,
                        face_rev = mode == "binder-faces" ? "dev" : null,
                    });
                }
                if (mode == "binder-faces")
                    for (int i = 0; i < col.prints.Count; i++)
                        PlayerCardFaces.DevPut(col.prints[i].print_id, "dev", "en", "tile", DevSprite(FrameColor(col.prints[i].rarity, false)), 375L * 525L * 4L);
                col.count = col.prints.Count;
                ApiClient.DevSetCollection(col);
                view = View.Binder;
            }
            Plugin.Log.LogInfo("[PC] synthetic tiles seeded (dev lever, mode=" + mode + ")");
            NativeUI.MarkDirty();
        }

        /// <summary>A 375x525 sprite for the dev lever: the band colour fading
        /// to black, so a tile shows a picture-shaped picture.</summary>
        private static Sprite DevSprite(Color c)
        {
            const int w = 375, h = 525;
            var tex = new Texture2D(w, h, TextureFormat.RGBA32, false);
            var px = new Color32[w * h];
            for (int y = 0; y < h; y++)
            {
                var row = Color.Lerp(c, Color.black, 0.65f * (1f - y / (float)(h - 1)));
                for (int x = 0; x < w; x++) px[y * w + x] = row;
            }
            tex.SetPixels32(px); tex.Apply(false, false);
            return PlayerCardFaces.SpriteOf(tex);
        }

        /// <summary>Broadcast-seat lever `act:<what>` (identity-gated by the
        /// caller): presses the REAL buttons against the live api, because a
        /// synthetic click never reaches the overlay (#420). "daily" is the
        /// daily button (claim, or open the claimed pack), "open" the first
        /// waiting pack, "card:N" the Nth binder tile's card view, and
        /// "view:open|binder|info" the view switch, with nothing seeded.</summary>
        internal static void DevAct(string what)
        {
            what = what ?? "";
            if (what == "daily") { ClaimDaily(); Plugin.Log.LogInfo("[PC] act: daily"); return; }
            if (what == "open")
            {
                var me = ApiClient.CachedPcMe;
                if (me == null || me.unopened == null || me.unopened.Count == 0) { Plugin.Log.LogInfo("[PC] act: open - no pack waiting"); return; }
                Plugin.Log.LogInfo("[PC] act: open " + me.unopened[0].pack_id);
                BeginOpenHeld(me.unopened[0].pack_id);
                return;
            }
            if (what.StartsWith("card:"))
            {
                int n;
                if (!int.TryParse(what.Substring(5), out n) || binderTiles == null || n < 0 || n >= binderTiles.Length || binderTiles[n] == null || binderTiles[n].print == null)
                { Plugin.Log.LogInfo("[PC] act: card - no such tile"); return; }
                Plugin.Log.LogInfo("[PC] act: card " + n + " " + binderTiles[n].print.print_id);
                ShowCard(binderTiles[n]);
                return;
            }
            if (what.StartsWith("view:"))
            {
                string v = what.Substring(5);
                view = v == "binder" ? View.Binder : (v == "info" ? View.Info : View.Open);
                Plugin.Log.LogInfo("[PC] act: view " + view);
                NativeUI.MarkDirty();
                return;
            }
            Plugin.Log.LogInfo("[PC] act: unknown '" + what + "'");
        }


        // ── Settings tab rows (design v4 §12 wording; no opt-out and no picture
        // choice since 2026-09-13: every registered player is in the pool, the
        // card shows the Steam profile picture until this PC has sent the
        // in-game character, and only deleting all data removes the cards) ──
        internal static void BuildSettingsRows(Transform parent)
        {
            UIFactory.CreateText("SPcHdr", parent, "Player Cards", 15f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(700, 22));
            var info = UIFactory.CreateText("SPcInfo", parent,
                "Other players can pull, collect and trade a card of you showing your name, rank title, rating and ranked record - the same things the leaderboard shows. Its picture is your Steam profile picture until this PC has sent your in-game character - the same body, face, colour and effect you play with, drawn here and sent once. Deleting your data (below) removes every card of you from every binder.",
                13f, C_DIM, sizeDelta: new Vector2(700, 36));
            // wrap + auto height, the Info body's shape: CreateText defaults to a
            // single Truncate line, and this caption is longer than the column
            UIFactory.SetWordWrap(info, true); UIFactory.SetTextAutoHeight(info, 36f);
            btnPublic = SettingsRow(parent, "SPcPub", () => ToggleSetting("collection_public"),
                "Lets others see which cards you hold, in the mod and in Discord.", 18f);
            btnPublicTxt = UIFactory.GetButtonText(btnPublic);
            btnAnnounce = SettingsRow(parent, "SPcAnn", () => ToggleSetting("announce"),
                "Rare pulls may be posted to the Discord gambler chat with your name.", 18f);
            btnAnnounceTxt = UIFactory.GetButtonText(btnAnnounce);
            btnPreset = SettingsRow(parent, "SPcPre", CyclePreset,
                "Which character your picture shows: Follow uses the one you have selected in the character menu, or pin a saved preset. The preview below is what your card will show.", 18f);
            btnPresetTxt = UIFactory.GetButtonText(btnPreset);
            // The preview in its own left-aligned row: dropped straight into
            // the settings column it was stretched to the column's width and
            // its picture centred in that ("too far to the right", Sid,
            // 2026-09-13). It shows as soon as a render exists, which the
            // Settings tab now asks for itself (MaybeTick -> OnTabVisit).
            presetPreviewRow = new GameObject("SPcPrevRow");
            presetPreviewRow.transform.SetParent(parent, false);
            presetPreviewRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(presetPreviewRow, spacing: 8, forceExpandW: false, forceExpandH: false);
            UIFactory.AddLE(presetPreviewRow, prefH: 118, minH: 118, flexH: 0);
            presetPreview = UIFactory.CreatePanel("SPcPrev", presetPreviewRow.transform, C_CARD);
            UIFactory.AddLE(presetPreview, prefW: 118, minW: 118, prefH: 118, minH: 118, flexW: 0, flexH: 0);
            PlayerCardFaces.SetFace(presetPreview, null);
            presetPreviewRow.SetActive(false);
            // The renderer's last word (rendered / uploading / picture current /
            // why it refused), the diagnostic the picture row used to carry.
            txtPicNote = UIFactory.CreateText("SPcPicN", parent, "", 12f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(700, 16));
        }

        private static string PresetLabel()
        {
            int v = PortraitRender.CurrentPreset();
            // v is the slot INDEX; players count slots from one.
            return v < 0 ? I18n.Tr("Follow my character") : I18n.TrF("Preset {0}", v + 1);
        }

        /// <summary>Follow → 1 → … → 10 → Follow. Local only (the picture itself is
        /// what reaches the server), debounced by the renderer.</summary>
        private static void CyclePreset()
        {
            try
            {
                var cfg = Plugin.PortraitPreset;
                if (cfg == null) return;
                // -1 → 0 → … → 9 → -1
                cfg.Value = ((Mathf.Clamp(cfg.Value, -1, 9) + 2) % 11) - 1;
                PortraitRender.RequestRefresh("preset");
                NativeUI.MarkDirty();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PC] preset cycle threw: {ex.Message}"); }
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
            var d = UIFactory.CreateText(name + "_d", group.transform, desc, 13f, C_DIM, sizeDelta: new Vector2(700, descH));
            // wrap + auto height (2026-09-13): a caption longer than the column, or
            // a translation of one, folds instead of running off the edge
            UIFactory.SetWordWrap(d, true); UIFactory.SetTextAutoHeight(d, descH);
            return btn;
        }

        internal static void RefreshSettingsRows()
        {
            if (btnPublicTxt == null) return;
            var id = LocalId();
            var me = ApiClient.CachedPcMe;
            if (me == null && id != null) ApiClient.FetchPcMe(id);   // throttled inside (10 s)
            if (me == null)
            {
                UIFactory.SetText(btnPublicTxt, "My collection is public: <color=#888>...</color>");
                UIFactory.SetText(btnAnnounceTxt, "Announce my pulls: <color=#888>...</color>");
            }
            else
            {
                UIFactory.SetText(btnPublicTxt, me.collection_public
                    ? "My collection is public: <color=#88FF88>ON</color>"
                    : "My collection is public: <color=#FF9966>OFF</color>");
                UIFactory.SetText(btnAnnounceTxt, me.announce
                    ? "Announce my pulls: <color=#88FF88>ON</color>"
                    : "Announce my pulls: <color=#FF9966>OFF</color>");
            }
            RefreshPictureRows();
        }

        /// <summary>The preset row and its preview are local (the preset is a
        /// config value and the preview this PC's own render), so they refresh
        /// whether or not /pc/me has answered.</summary>
        private static void RefreshPictureRows()
        {
            if (btnPresetTxt == null) return;
            UIFactory.SetTextRaw(btnPresetTxt, I18n.Tr("Character preset") + ": <color=#CCCCCC>" + PresetLabel() + "</color>");
            string note = PortraitRender.LastResult;
            UIFactory.SetTextRaw(txtPicNote, string.IsNullOrEmpty(note) ? "" : "(" + note + ")");
            if (presetPreviewRow == null || presetPreview == null) return;
            bool show = PortraitRender.PreviewTex != null;
            presetPreviewRow.SetActive(show);
            if (show && previewShown != PortraitRender.PreviewSerial)
            {
                previewShown = PortraitRender.PreviewSerial;
                var old = previewSprite;
                previewSprite = PlayerCardFaces.SpriteOf(PortraitRender.PreviewTex);
                PlayerCardFaces.SetFace(presetPreview, previewSprite);
                if (old != null) { try { UnityEngine.Object.Destroy(old); } catch { } }
            }
        }

        private static bool SettingValue(ApiClient.PcMe me, string key)
        {
            return key == "collection_public" ? me.collection_public : me.announce;
        }
        private static void ApplySetting(ApiClient.PcMe me, string key, bool v)
        {
            if (me == null) return;
            if (key == "collection_public") me.collection_public = v; else me.announce = v;
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
            int ep = uiEpoch;
            ApiClient.PcSetSetting(id, NewNonce(), revision, key, after ? 1 : 0, (ok, resp) =>
            {
                if (ep != uiEpoch) return;   // identity changed meanwhile (c4)
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
