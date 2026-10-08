using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

// The binder orders used to be a private enum here. Item 20 moved the member
// set, the cycler and the comparator into BinderSortRules so a plain compiler
// (tools/client-rules-harness) can RUN them; the alias keeps every switch site
// in this file reading as it always has, and keeps ONE definition of the set
// the cycle length is derived from.
using Sort = CompetitiveRounds.BinderSortRules.Mode;

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
        private static readonly Color C_SELECT = new Color(0.35f, 0.92f, 1f, 1f);   // a binder tile picked for Shard selected (no rarity band uses cyan)

        // Trades (v1.41.0) is appended AFTER Info, so Open/Binder/Info keep
        // 0/1/2 and the index casts at the view buttons stay what they were.
        private enum View { Open, Binder, Info, Trades }
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
            public GameObject topBack, topArt;   // the Top card overlay (Sept 14 batch, C3): the real card art over the badge
            public Sprite topSprite;             // the art sprite currently set on topArt (a re-set only on change)
            public int bindSeq;                  // v22 section 5.2: a face answer that misses this paints nothing
            public object txtName, txtTitle, txtL1, txtL2, txtL3, txtL4, txtMark, txtSign, btnDiscardTxt, btnDupesTxt, faceMark;
            public ApiClient.PcPrint print;   // the row's CURRENT binding — callbacks read this, never a captured print (#265)
            public int dupes;
            // item 18: true for the pull strip's five tiles, whose Discard
            // button shards that one card (PcQuickShardRules); false for the
            // binder's, which keep their own Discard. Set once in CreateTile.
            public bool quickSurface;
            // card trading (v1.41.0): the In a trade / Traded badge over the
            // tile, a click that replaces the card view (the compose pickers),
            // and the mini form the trade lists draw
            public GameObject badgeGO;
            public object badge;
            public Action<Tile> click;
            public bool mini;
        }
        private class PackRow { public GameObject root, btnOpen; public object txt; public ApiClient.PcUnopened pack; }

        // tab
        private static GameObject tabRoot, openRoot, binderRoot, infoRoot;
        private static readonly GameObject[] viewBtns = new GameObject[4];
        private static readonly object[] viewTxts = new object[4];
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
        /// sorts last under it. Rating position (item 20) asks the different
        /// question — where that player stands on the same board TODAY — and
        /// is offered only while the collection answer carries standings.
        ///
        /// The members themselves are BinderSortRules.Mode (aliased to `Sort`
        /// at the top of this file): Unity-free, so the cycler and the
        /// comparator are EXECUTED by tools/client-rules-harness rather than
        /// described by a source test.</summary>
        private static Sort binderSort = Sort.Name;
        /// <summary>A sort read out of the config file that has not been
        /// applied yet.
        ///
        /// The binder's FIRST paint of a session always happens before the
        /// collection fetch has answered — OnTabEntered only STARTS the fetch
        /// and RefreshBinder then paints the col == null branch — so resolving
        /// a stored "RatingPosition" there would coerce it to Name on every
        /// launch. It is held instead, and BinderSortRules.Resolve decides on
        /// each paint whether to apply it, drop it for this session, or keep
        /// waiting. None of the three writes the config back: the config is
        /// written by CycleSort, an explicit click, and by nothing else.</summary>
        private static Sort? pendingBinderSort;
        private static Tile[] binderTiles;
        private static GameObject[] binderRows;
        private static int binderPage;
        private static string armedPrintId; private static bool armedDupes; private static float armedAt;
        private static bool discardInFlight; private static readonly List<string> discardQueue = new List<string>();
        // The run latch's give-up (the settings card latch's rule, carried
        // item ii): discardSentAt is when the run's CURRENT step began - a
        // request sent, or the end of a server-asked pause - and a run whose
        // step has had no answer 25 s later is ended by RetireStuckLatches.
        // discardSerial names the run; every answer and every resumed pause
        // checks it before touching run state, so a late answer to a run that
        // was given up (or a pause of one) cannot drive a newer run.
        private static float discardSentAt; private static int discardSerial;
        private static int discardDone, discardShards;
        // The copies that have already had their ONE wait-and-retry, keyed
        // by print id.
        //
        // This was a run-wide bool that DiscardAfter cleared on every
        // resumption, which made it mean "one retry IN FLIGHT" while the
        // comment beside it said "one retry per copy". The difference is not
        // academic: with the default 3 s pause, one stubborn copy could be
        // re-asked six times over on its own and spend the entire run budget,
        // so the copies queued behind it never got the retry the rule
        // promised them. Per copy, the latch is set once and never cleared
        // until the run ends.
        private static readonly HashSet<string> discardRetriedIds = new HashSet<string>();
        private static float discardWaited;   // seconds THIS run has already spent waiting a refusal out
        // Ceiling on the waiting a single discard run may do, ACROSS copies.
        // The per-copy latch bounds how often ONE copy may be re-asked; this
        // bounds the RUN, so a long queue of individually-once-retried copies
        // cannot leave the binder saying "discarding..." indefinitely with the
        // button dead and nothing said. Past the budget the run finishes, and
        // it reports the exhausted budget as its own reason rather than as a
        // plain refusal - those are different events to the player.
        private const float DiscardWaitBudget = 20f;
        // info
        private static object txtInfo;
        // state
        private static bool openInFlight, claimInFlight, recoverInFlight;
        private static float openAt, claimAt, recoverAt, tickAt, meRefreshAt;
        // recoverAt is the RETRY throttle; recoverSentAt is when the request in
        // flight was sent (its 25 s give-up), recoverSerial the request.
        private static float recoverSentAt; private static int recoverSerial;
        private static int unparseableStrikes;   // consecutive 2xx answers the client could not read (c6)
        private static ApiClient.PcPackAnswer lastPack;
        private static string lastMsg; private static Color lastMsgColor; private static float lastMsgAt;
        // settings rows
        private static GameObject btnPublic, btnAnnounce, btnPreset, presetPreview, presetPreviewRow;
        private static object btnPublicTxt, btnAnnounceTxt, btnPresetTxt, txtPicNote;
        // the Card trading row (v1.41.0, V8 2.1/6.1): the settings page's row,
        // its label, and the object that gets hidden (the row itself)
        private static GameObject btnTrades, tradesRowGroup;
        private static object btnTradesTxt;
        private static string tradesRowSig;   // the last settings-row state logged
        private static int previewShown = -1;   // PortraitRender.PreviewSerial the preview sprite was made from
        private static Sprite previewSprite;
        // Board row 24: the Settings preview is the WHOLE card as other players
        // see it -- the server's own drawing (ApiClient.PcFacePreview), owned
        // here and never the face cache's. While a new look is on its way the
        // slot shows the live picture above with a pending note instead.
        private const float SETTINGS_CARD_W = 240f, SETTINGS_CARD_H = 336f;   // the 750x1050 card at 0.32, its 5:7 kept
        private const float SETTINGS_CAP_W = 420f;                            // the line beside it; 240 + 12 + 420 fits the 700 column
        private const int SC_NONE = 0, SC_CARD = 1, SC_NOT_IN_POOL = 2, SC_UNAVAILABLE = 3;
        private static object txtSettingsCardCap;
        private static Texture2D settingsCardTex;
        private static Sprite settingsCardSprite, settingsCardBound;
        private static string settingsCardKey;           // identity epoch | stored portrait hash | locale the card was drawn for
        private static bool settingsCardInFlight;
        // When the fetch in flight was sent, and its serial: a fetch with no
        // answer 25 s on (past the 20 s transport timeout) is given up and
        // its latch released, and an answer whose serial is not the latest
        // commits nothing (asks-b round 2, L4).
        private static float settingsCardSentAt;
        private static int settingsCardSerial;
        private static float settingsCardRetryAt, settingsCardAt = -1000f;
        private static int settingsCardState = SC_NONE;
        // Board row 25: the batch shard (a whole pack from its result, or a
        // binder selection), one server transaction per click.
        private static GameObject btnShardPack, btnSelect, btnShardSel;
        private static object btnShardPackTxt, btnSelectTxt, btnShardSelTxt, txtBinderHint, txtBinderSelHint;
        private static bool selecting;                                        // the binder's Select mode
        private static readonly List<string> selectedIds = new List<string>();  // in the order they were clicked
        private static string armedShard; private static float armedShardAt;   // the exact request the first click armed
        // Item 18 fix pass 1 (F2): the one batch shard in flight -- its latch,
        // its generation, the pack or strip card it is for -- and a strip
        // card's nonce (kept until an answer, PcQuickShardRules.KeepKeyAfter,
        // so the same card asked again after a lost answer is a replay) have
        // ONE writer, PcShardFlight: a retired generation's late answer
        // changes nothing (SendShard).
        private static readonly PcShardFlight shardFlight = new PcShardFlight();
        private static bool shardInFlight => shardFlight.InFlight;
        private static string shardPackId => shardFlight.PackId;    // the pack a Shard pack in flight came from (null: a selection)
        private static string shardQuickId => shardFlight.QuickId;  // the strip card a one-card shard is for
        private static string shardKey, shardKeyFor;   // a selection's nonce and the exact request it was made for (#172)
        // Prints the server named as no longer this account's (a refused
        // batch), kept out of the next Shard pack; and packs whose key an
        // earlier batch already used with other cards, whose button stays
        // down (single discards and the binder selection still reach them).
        private static readonly HashSet<string> shardGone = new HashSet<string>(StringComparer.Ordinal);
        private static readonly HashSet<string> packShardBurned = new HashSet<string>(StringComparer.Ordinal);
        private static bool setInFlight; private static float setAt;
        // the dance row (dance cards S5.8): the choice lives on the server; a
        // click only moves the pending choice, sent after a short pause
        private static GameObject btnDance;
        private static object btnDanceTxt;
        private static long danceChoice = -1;   // the shop item id a click chose, -1 when nothing is pending
        private static float danceChoiceAt, danceSentAt;
        private static bool danceInFlight;
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
                case "rate_limited": return I18n.Tr("Too many requests at once - wait a few seconds and try again");
                // Distinct from the line above ON PURPOSE. "Too many requests"
                // describes a refusal the player can retry straight away; this
                // one means we already waited, for as long as a run may, and
                // the queue did not drain. Folding them together told a player
                // who had been waiting twenty seconds to wait a few seconds.
                case "rate_limit_waited": return I18n.Tr("The server kept asking us to pause - we waited as long as we can; the rest are still in your binder");
                // card trading (v1.41.0): one line per refusal code the trade
                // routes answer as built (V8 2.7, 3.4-3.7, 3.13)
                case "trading_off": return I18n.Tr("Trading is paused");
                case "trading_unavailable": return I18n.Tr("Trading is not available yet");
                case "bad_request": return I18n.Tr("The server could not read that trade request - update the mod or try again");
                case "self_trade": return I18n.Tr("You cannot trade with yourself");
                case "bad_terms": return I18n.Tr("That trade has changed - check it again before answering");
                case "bad_terms_local": return I18n.Tr("Those cards cannot be sent in a trade - choose them again");
                case "already_processed": return I18n.Tr("That trade was already answered");
                case "counterparty_unavailable": return I18n.Tr("That player cannot trade");
                case "counterparty_not_eligible": return I18n.Tr("That player cannot trade yet");
                case "not_eligible":
                    {
                        var tb = ApiClient.CachedPcTrades;
                        return tb != null && tb.bounds.min_mod_age_days > 0
                            ? I18n.TrF("You cannot trade yet - trading needs {0} days with the mod and {1} completed ranked series", tb.bounds.min_mod_age_days, tb.bounds.min_ranked_series)
                            : I18n.Tr("You cannot trade yet");
                    }
                case "private": return I18n.Tr("That player's binder is private - they can still propose a trade to you");
                case "busy": return I18n.Tr("The server is busy with that trade - try again in a moment");
                case "trading_closed": return I18n.Tr("Your card trading is off - turn it on in Settings");
                case "counterparty_closed": return I18n.Tr("That player has card trading turned off");
                case "print_gone": return I18n.Tr("A card in that trade is no longer there");
                case "subject_unavailable": return I18n.Tr("A card in that trade shows a player who can no longer be traded");
                case "print_offered_elsewhere": return I18n.Tr("One of your cards is already offered in another trade");
                case "recently_traded": return I18n.Tr("A card in that trade changed hands moments ago - try again later");
                case "cap_open_sent": return I18n.Tr("You have too many proposals waiting - cancel one first");
                case "cap_open_received": return I18n.Tr("That player has too many proposals waiting - try again later");
                case "cap_proposals_day": return I18n.Tr("You have sent all the proposals allowed today - try again after midnight UTC");
                case "cooldown_declined": return I18n.Tr("That player declined your last proposal - wait before proposing to them again");
                case "cooldown_reversal": return I18n.Tr("A trade between you was reversed - wait before trading again");
                case "pair_busy": return I18n.Tr("You already have an open trade with that player");
                case "not_found": return I18n.Tr("That trade no longer exists");
                case "wrong_party": return I18n.Tr("That trade is not yours to answer");
                case "expired": return I18n.Tr("That trade has expired");
                case "declined": return I18n.Tr("That trade was declined");
                case "cancelled": return I18n.Tr("That trade was cancelled");
                case "void": return I18n.Tr("That trade is no longer possible");
                case "reversed": return I18n.Tr("That trade was reversed by an admin");
                case "cap_executed_day": return I18n.Tr("You have made all the trades allowed today - try again after midnight UTC");
                case "cap_executed_pair_day": return I18n.Tr("You two have made all the trades allowed today - try again after midnight UTC");
                case "transfer_conflict": return I18n.Tr("The cards changed while the trade ran - nothing moved, check your binder");
                case "service_account_forbidden": return I18n.Tr("This account cannot trade cards");
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
            try { PlayerCardMotion.Clear(); } catch { }
            try { PortraitRender.OnIdentityChanged(); } catch { }
            lastPack = null; lastMsg = null;
            HistoryReset();
            openInFlight = claimInFlight = recoverInFlight = discardInFlight = setInFlight = false;
            danceChoice = -1; danceInFlight = false;   // the previous account's pending dance choice is never sent
            portraitWaitUntil = -1f; portraitWaitedAt = -100f; pendingVisit = false;
            settingsVisited = false;   // the next Settings look checks the picture again (r5 L12)
            // the previous account's character, as a Sprite over a texture
            // PortraitRender has just destroyed
            if (previewSprite != null) { try { UnityEngine.Object.Destroy(previewSprite); } catch { } previewSprite = null; }
            previewShown = -1;
            if (presetPreview != null) { try { PlayerCardFaces.SetFace(presetPreview, null); } catch { } }
            // Board row 24: the previous account's full card is not this one's.
            // A fetch still in flight is dropped by its epoch check.
            SettingsCardDrop();
            settingsCardInFlight = false; settingsCardRetryAt = 0f; settingsCardAt = -1000f;
            // Board row 25: a selection names the previous account's prints,
            // and an answer still in flight is dropped by its epoch check.
            selecting = false; selectedIds.Clear();
            armedShard = null; armedShardAt = 0f;
            shardFlight.Reset(); shardKey = null; shardKeyFor = null;
            shardGone.Clear(); packShardBurned.Clear();
            // FinishDiscard is not on this path, so the run state it clears
            // is cleared here too. A per-copy retry latch left populated
            // would be carried into the NEXT account's run, where those
            // print ids are not even its own; and discardInFlight left true
            // WEDGES the surface outright - the binder goes on saying
            // "discarding..." and the button stays dead for an account that
            // never started a run. The epoch check drops the answer that would
            // have cleared it; only RetireStuckLatches' 25 s give-up would,
            // and that is 25 s of a dead surface.
            discardInFlight = false;
            discardQueue.Clear(); discardRetriedIds.Clear(); discardWaited = 0f;
            armedPrintId = null; priceChangedAt = -1f;
            recoverAt = 0f; meRefreshAt = 0f; unparseableStrikes = 0;
            ResetTrades();
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
            try { PlayerCardMotion.Stop(); } catch { }   // every overlay stops (S5.7)
            pendingVisit = true; settingsVisited = false;
            tradesEdge.OverlayClosed();   // the Trades view survives a close: the reopen is an entry (TC-L2)
        }

        /// <summary>The card view is a full-screen uGUI surface: it owns input
        /// while it is up (CompetitiveUI's single ModalBlockInput writer reads
        /// this), and its own backdrop carries bypassModalBlock so the dismiss
        /// still runs. Without it, a backdrop click closed the popup AND
        /// reached the armed Discard beneath in the same click (#141/#200).</summary>
        internal static bool CardPopupOpen { get { return cardPopupGO != null; } }

        internal static void OnTabEntered()
        {
            try { PlayerCardMotion.TabEntered(); } catch { }   // a new visit for the playback (S5.3)
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
            tradesEdge.Frame(onTab && view == View.Trades);   // and a frame off the Trades view re-arms its entry read (TC-L2)
            if (danceChoice >= 0) { try { MaybeSendDance(); } catch (Exception ex) { danceChoice = -1; danceInFlight = false; Plugin.Log.LogWarning($"[PC] dance selection threw: {ex.Message}"); } }
            if (onTab || cardPopupTile != null) { try { PlaceTopCards(); } catch { } }   // every frame: the overlays follow the layout and the snapshots (C3)
            // Dance cards playback (design S5.7): every call, before the throttle
            // below -- the clock is real time and the overlays follow the layout.
            try { MotionTick(onTab); }
            catch (Exception ex) { if (Time.unscaledTime >= motionWarnAt) { motionWarnAt = Time.unscaledTime + 10f; Plugin.Log.LogWarning($"[MOTION] tick threw: {ex.Message}"); } }
            if (Time.unscaledTime < tickAt) return;
            tickAt = Time.unscaledTime + 2f;
            var id = LocalId();
            // Above every early return: a latch stuck while the tab is shut
            // (or on Settings) is retired all the same.
            RetireStuckLatches(id);
            if (id == null) return;
            if (HasIntent()) MaybeRecover(false);
            // Card trading (V8 6.4): ABOVE the early return below, so the
            // 120 s summary runs whichever tab is current while the overlay
            // is up, as MaybeRecover does.
            TickTrades(id, onTab);
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
                // Board row 24: the full card the slot shows, asked for here
                // (Settings has no fetch chain of its own).
                try { SettingsCardTick(id); } catch (Exception ex) { Plugin.Log.LogWarning($"[PC] settings card tick threw: {ex.Message}"); }
                return;
            }
            if (Time.unscaledTime >= meRefreshAt) { meRefreshAt = Time.unscaledTime + 30f; ApiClient.FetchPcMe(id, true); }
            // the binder after an identity edge (c5): an empty cache without an error is refetched (throttled by ApiClient)
            if (view == View.Binder && ApiClient.CachedPcCollection == null && ApiClient.PcCollectionError == null) ApiClient.FetchPcCollection(id);
            if (armedPrintId != null && Now - armedAt > 6f) { armedPrintId = null; NativeUI.MarkDirty(); }
            if (armedShard != null && Now - armedShardAt > 6f) { armedShard = null; NativeUI.MarkDirty(); }
            // Past the 20 s transport timeout, the other latches' rule: an answer
            // that never came back does not leave both shard buttons dead.
            // The give-up retires the request's generation (F2): an answer that
            // does arrive later settles nothing and writes no balance.
            bool quick;
            if (shardFlight.GiveUp(Now, 25f, out quick))
            {
                // Item 18: a strip shard given up has an unknown outcome, so
                // the collection and the balance are read back (its key is
                // kept: the same card asked again is a replay).
                if (quick)
                {
                    Plugin.Log.LogWarning("[PC] quick shard: no answer 25 s after the request; given up, read back");
                    if (PcQuickShardRules.ReadBackAfter("given_up")) { ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true); }
                }
                NativeUI.MarkDirty();
            }
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
            EndCompose(); tradesLabelPainted = null;
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
            // Four literal sites (c4): a label must sit AT a harvested
            // CreateButton call for the key catalogue to carry it.
            ViewButton(0, UIFactory.CreateButton("PcView0", bar.transform, "Open Packs", 14f, C_LABEL, C_BTN,
                () => { view = (View)0; NativeUI.MarkDirty(); }, sizeDelta: new Vector2(0, 26)));
            ViewButton(1, UIFactory.CreateButton("PcView1", bar.transform, "Binder", 14f, C_LABEL, C_BTN,
                () => { view = (View)1; NativeUI.MarkDirty(); }, sizeDelta: new Vector2(0, 26)));
            ViewButton(2, UIFactory.CreateButton("PcView2", bar.transform, "Get packs", 14f, C_LABEL, C_BTN,
                () => { view = (View)2; NativeUI.MarkDirty(); }, sizeDelta: new Vector2(0, 26)));
            ViewButton(3, UIFactory.CreateButton("PcView3", bar.transform, "Trades", 14f, C_LABEL, C_BTN,
                () => { view = (View)3; NativeUI.MarkDirty(); }, sizeDelta: new Vector2(0, 26)));
            // hidden until a first view=summary read says the server trades (V8 6.9)
            if (viewBtns[3] != null) viewBtns[3].SetActive(PcTradeRules.TabShown(tradeDiscovery));
            txtStatus = UIFactory.CreateText("PcStatus", tabRoot.transform, "", 14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(1000, 22));

            BuildOpenView(tabRoot.transform);
            BuildBinderView(tabRoot.transform);
            BuildInfoView(tabRoot.transform);
            BuildTradesView(tabRoot.transform);
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
            // Board row 25: shard every card of the pack on show that is still
            // yours, in one server transaction (two clicks: the first names the
            // total and any card that is your only copy). CreateButton routes
            // the click through ClickGuard.
            btnShardPack = UIFactory.CreateButton("PcShardPack", hdrRow.transform, "", 12f, C_WHITE, C_DANGER, OnShardPackClick, sizeDelta: new Vector2(170, 22));
            btnShardPackTxt = UIFactory.GetButtonText(btnShardPack);
            if (btnShardPackTxt != null) { UIFactory.SetOverflowMode(btnShardPackTxt, 2); UIFactory.SetWordWrap(btnShardPackTxt, false); }
            btnShardPack.SetActive(false);
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
            // Item 18: the strip's tiles carry the binder's action row, and its
            // Discard shards that one card (OnQuickShardClick).
            for (int i = 0; i < REVEAL_TILES; i++) revealTiles[i] = CreateTile(lastStrip.transform, "PcRv" + i, true, true);
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
            btnPrev = UIFactory.CreateButton("PcBPrev", hdr.transform, "<", 14f, C_WHITE, C_BTN, BinderPrev, sizeDelta: new Vector2(40, 24));
            txtBinderPage = UIFactory.CreateText("PcBPage", hdr.transform, "", 13f, C_LABEL, UIFactory.AlignMidCenter, sizeDelta: new Vector2(160, 24));
            btnNext = UIFactory.CreateButton("PcBNext", hdr.transform, ">", 14f, C_WHITE, C_BTN, BinderNext, sizeDelta: new Vector2(40, 24));
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
            txtBinderHint = UIFactory.CreateText("PcBHint", binderRoot.transform, "Click a card to view it", 12f, C_DIM, UIFactory.AlignMidCenter, sizeDelta: new Vector2(600, 18));
            // Board row 25: a row below it carries Select (a click then picks a
            // card instead of opening it; the line above gives way to this
            // row's own line saying so) and Shard selected, which shards the
            // picked cards in one server transaction (two clicks, as Shard pack).
            var foot = new GameObject("PcBFoot"); foot.transform.SetParent(binderRoot.transform, false); foot.AddComponent<RectTransform>();
            UIFactory.AddHLG(foot, spacing: 10, forceExpandH: false); UIFactory.AddLE(foot, prefH: 24, minH: 24, flexH: 0);
            UIFactory.SetHLGChildAlignMiddle(foot);
            txtBinderSelHint = UIFactory.CreateText("PcBSelHint", foot.transform, "", 12f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(600, 18));
            var hintGO = (txtBinderSelHint as Component)?.gameObject;
            if (hintGO != null) UIFactory.AddLE(hintGO, flexW: 1);
            btnSelect = UIFactory.CreateButton("PcBSelect", foot.transform, "Select", 12f, C_WHITE, C_BTN, OnSelectClick, sizeDelta: new Vector2(140, 22));
            btnSelectTxt = UIFactory.GetButtonText(btnSelect);
            btnShardSel = UIFactory.CreateButton("PcBShardSel", foot.transform, "", 12f, C_WHITE, C_DANGER, OnShardSelectedClick, sizeDelta: new Vector2(200, 22));
            btnShardSelTxt = UIFactory.GetButtonText(btnShardSel);
            foreach (var o in new[] { btnSelectTxt, btnShardSelTxt })
                if (o != null) { UIFactory.SetOverflowMode(o, 2); UIFactory.SetWordWrap(o, false); }
            btnShardSel.SetActive(false);
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

        private static Tile CreateTile(Transform parent, string name, bool withActions, bool quickSurface = false)
        {
            var t = new Tile();
            t.quickSurface = quickSurface;
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
            // The Top card overlay (Sept 14 batch, C3): the face carries a
            // generic badge; in game the actual ROUNDS card art is laid over
            // its silhouette (a backing in the badge's own dark, the art above
            // it), both created here and sized, shown or hidden by PlaceTopCard.
            // Created BEFORE the stamp so the stamp stays on top.
            t.topBack = CreatePanelCentred(name + "_tcb", t.face.transform, C_BADGE_DARK);
            t.topArt = CreatePanelCentred(name + "_tca", t.face.transform, Color.white);
            // The DISCARDED stamp: a centred label over the picture, shown for
            // a discarded print whose face is showing.
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
                // The strip's Discard shards the one card through the batch
                // shard's route (item 18); the binder's keeps its own path.
                t.btnDiscard = UIFactory.CreateButton(name + "_d", t.actions.transform, "Discard", 11f, C_WHITE, C_DANGER,
                    quickSurface ? (UnityEngine.Events.UnityAction)(() => OnQuickShardClick(tile)) : () => OnDiscardClick(tile, false), sizeDelta: new Vector2(76, 20));
                t.btnDiscardTxt = UIFactory.GetButtonText(t.btnDiscard);
                t.btnDupes = UIFactory.CreateButton(name + "_dd", t.actions.transform, "", 11f, C_WHITE, C_DANGER, () => OnDiscardClick(tile, true), sizeDelta: new Vector2(84, 20));
                t.btnDupesTxt = UIFactory.GetButtonText(t.btnDupes);
                // Masking, never Truncate, on the two labels: the tile's own
                // text lines opted out above and the buttons had not (c4/c5).
                foreach (var o in new[] { t.btnDiscardTxt, t.btnDupesTxt })
                    if (o != null) { UIFactory.SetOverflowMode(o, 2); UIFactory.SetWordWrap(o, false); }
                // the binder's In a trade / Traded badge (V8 6.1), created last so it draws on
                // top, just above the 22 px action row (root pad 3 + inner pad 4 below that row)
                AddBadge(t, name + "_bd", TILE_W - 24f, 13f, 3f + 4f + 22f + 4f);
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
        private static Tile cardPopupTile;   // the card view's print + its Top card overlay children (C3); face set when the picture lands
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
                // The card view carries the Top card overlay too (C3), and a
                // discarded print's stamp over its dimmed face (C1): the
                // owner's own history shows the card, marked, at every size.
                // The pseudo-tile's face is set when the picture lands, so the
                // overlay never sits over an empty popup.
                var popupTile = new Tile { print = p };
                popupTile.topBack = CreatePanelCentred("TcB", img.transform, C_BADGE_DARK);
                popupTile.topArt = CreatePanelCentred("TcA", img.transform, Color.white);
                if (p.discarded)
                {
                    var mk = UIFactory.CreateText("TcMark", img.transform, "<b>" + DiscardedLine(p) + "</b>", 30f, C_WARN, UIFactory.AlignMidCenter,
                                                  sizeDelta: new Vector2(h * 0.6f, 80f));
                    UIFactory.SetOverflowMode(mk, 2); UIFactory.SetWordWrap(mk, true);
                }
                cardPopupTile = popupTile;
                MaybeAddOfferButton(p, h);   // card trading (V8 6.1): Offer in a trade
                int seq = ++cardPopupSeq, ep = uiEpoch, gen = PlayerCardFaces.Generation;
                var hit = PlayerCardFaces.Cached(p.print_id, p.face_rev, p.face_locale, "card");
                if (hit != null) { PopupFaceLanded(img, p, hit, popupTile); return; }
                var print = p;
                PlayerCardFaces.Get(p.print_id, p.face_rev, p.face_locale, "card", spr =>
                {
                    if (seq != cardPopupSeq || ep != uiEpoch || gen != PlayerCardFaces.Generation) return;
                    if (spr == null) { HideCardPopup(); ShowCardText(print); return; }
                    if (cardPopupImg != null) PopupFaceLanded(cardPopupImg, print, spr, popupTile);
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
            if (t.print.gone) return;   // a print a data deletion removed (card trading): nothing to open or pick
            if (!ClickGuard.Claim(t.root)) return;
            // a compose picker's tile selects instead of opening the card (card trading)
            if (t.click != null) { t.click(t); return; }
            // Board row 25: in Select mode a binder tile (the one with an action
            // row) is picked or dropped instead of opened. The reveal strip's
            // tiles still open their card.
            if (selecting && view == View.Binder && t.actions != null) { ToggleSelected(t.print); return; }
            ShowCard(t);
        }

        private static void PopupFaceLanded(GameObject img, ApiClient.PcPrint p, Sprite spr, Tile popupTile)
        {
            PlayerCardFaces.SetFace(img, spr);
            if (p.discarded) UIFactory.SetImageColor(img, C_FACE_DIM);
            if (popupTile != null && cardPopupTile == popupTile) { popupTile.face = img; PlaceTopCard(popupTile); }
        }

        internal static void HideCardPopup()
        {
            cardPopupSeq++;
            cardPopupImg = null;
            cardPopupTile = null;
            try { PlayerCardMotion.PopupClosed(); } catch { }   // the popup's overlay goes with it; the clip state stays (S5.7)
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
            MaybeAddTextOfferButton(p);   // card trading (V8 6.1): the text view offers the card too
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
            // Board row 25: a binder tile picked for Shard selected wears a cyan
            // frame and a "Selected" stamp (the DISCARDED stamp's slot: the
            // binder holds no discarded print), and its mark line says so too
            // for a tile showing its text block.
            bool picked = selecting && t.actions != null && !t.quickSurface && !p.discarded && selectedIds.Contains(p.print_id);
            if (picked) { UIFactory.SetImageColor(t.root, C_SELECT); mark = I18n.Tr("Selected") + " | " + mark; }
            UIFactory.SetTextRaw(t.txtMark, mark);
            if (t.faceMark != null) UIFactory.SetTextRaw(t.faceMark, p.discarded ? "<b>" + DiscardedLine(p) + "</b>" : (picked ? "<b>" + I18n.Tr("Selected") + "</b>" : ""));
            if (t.faceMarkGO != null) t.faceMarkGO.SetActive(p.discarded || picked);
            UIFactory.SetImageColor(t.face, p.discarded || picked ? new Color(0.42f, 0.42f, 0.48f, 1f) : Color.white);
            UIFactory.SetTextRaw(t.txtSign, p.signed ? "<i>~ " + name + " ~</i>" : "");
            if (t.actions != null)
            {
                bool gone = p.print_id != null && shardGone.Contains(p.print_id);
                // Select mode picks binder cards; the binder's per-card buttons
                // wait until it ends. The strip's rule is its own (item 18).
                t.btnDiscard.SetActive(PcQuickShardRules.DiscardOffered(t.quickSurface, p.discarded, gone, selecting));
                if (t.quickSurface)
                {
                    // Item 18: armed by the batch shard's arming (one card's
                    // set), "sharding..." while this card's request is out,
                    // and dimmed while any shard or discard is out (a click
                    // then is refused at the entry).
                    bool busyThis = shardInFlight && shardQuickId == p.print_id;
                    bool armedQ = armedShard != null && armedShard == PcQuickShardRules.ArmSet(p.print_id) && Now - armedShardAt <= 6f;
                    if (busyThis) UIFactory.SetTextRaw(t.btnDiscardTxt, I18n.Tr("sharding..."));
                    else UIFactory.SetText(t.btnDiscardTxt, armedQ ? "Sure? Discard" : "Discard");
                    UIFactory.SetImageColor(t.btnDiscard, SessionReady && !shardInFlight && !discardInFlight ? C_DANGER : C_BTN);
                    t.btnDupes.SetActive(false);
                    PaintTileBadge(t, p);
                    return;
                }
                bool armedThis = armedPrintId == p.print_id && !armedDupes;
                UIFactory.SetText(t.btnDiscardTxt, armedThis ? "Sure? Discard" : "Discard");
                bool showDupes = dupes > 1 && !selecting;
                t.btnDupes.SetActive(showDupes);
                if (showDupes)
                {
                    bool armedD = armedPrintId == p.print_id && armedDupes;
                    UIFactory.SetTextRaw(t.btnDupesTxt, armedD ? I18n.Tr("Sure? Discard dupes") : I18n.TrF("Dupes ({0})", dupes - 1));
                }
            }
            PaintTileBadge(t, p);   // display only: Discard stays live on a print in a trade (V8 1.2)
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
            // A discarded print's face is fetched like a live one: the face
            // route serves it since the Sept 14 batch (S3), so the owner's
            // pack history keeps the picture under the DISCARDED stamp instead
            // of falling to the text block once the cache let go (Sid,
            // 2026-09-13, item 4).
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
            PlaceTopCard(t);
        }

        private static void ShowTileText(Tile t)
        {
            if (t.face != null) { PlayerCardFaces.SetFace(t.face, null); t.face.SetActive(false); }
            if (t.textBlock != null) t.textBlock.SetActive(true);
            PlaceTopCard(t);
        }

        // ── the Top card overlay (Sept 14 batch, C3; regeometried for 9a) ────
        // The face draws its Top card badge at [58,642,178,754] of 750x1050
        // (backend face_layout_v1.json). Since 9a that badge is a NAME COLUMN
        // up the left -- the ROUNDS card's own name, sideways, in the card's
        // theme colour -- and an empty ART AREA beside it, which is what this
        // overlay fills with the real card art from CardSnapshot. Outside the
        // game (Discord, the bot) the badge stands as drawn: name, framed
        // empty area.
        //
        // The box is [100,651,167,745] -- 67x94 -- and the backing plate is
        // the same rect. Two constraints place it, and both hold at once:
        //
        // 1. It starts 4 px right of the NAME COLUMN, not of one name's ink.
        //    The layout's badge_name rect is [64,654,96,742], and a long card
        //    name fills that column to x=96, so the art starts at x=100
        //    (backend/tests/test_client_top_card_overlay.py pins it).
        // 2. It keeps at least 2 px from every pixel of BadgeFrame.png, the
        //    rounded corners included. The frame's opening is transparent
        //    over x 62-174 and rows 646-750; the rails occupy x 175-178, rows
        //    642-645 and rows 751-754, and the opening's inner corners are
        //    rounded (~12 px radius: on the right, the rail's inner edge is at
        //    x=163 on row 646 and x=172 on row 652, mirrored at the bottom as
        //    x=163 on row 750 and x=170 on row 746). Both overlays are opaque
        //    rectangles -- the plate in C_BADGE_DARK, and the capture
        //    composited over its backing colour at alpha 255 -- so any overlap
        //    paints over the frame. The pre-inset rects (the backing at
        //    [92,646] 80x104, the art box at [94,646] 78x104) did exactly that
        //    on the right-hand corners: 44 frame pixels under the backing and
        //    34 under the drawn card, counted by pixel centre over the frame's
        //    alpha. Here the nearest frame pixel is 2.00 px from the box, at
        //    the top-right corner; the straight rails are 5 px above, 8 px to
        //    the right and 6 px below.
        //
        // The size follows from those two. 94 px is the least height that
        // still claims 90% of the clear area's 104 px, which the same test
        // requires, and 67 px is the widest box of that height starting at
        // x=100 that keeps 2 px from both right-hand corners: a 68 px box
        // comes within 1.41 px of one wherever it sits vertically.
        //
        // The fit is therefore WIDTH-limited. The vanilla card body
        // (Canvas/Front/Background, the rect the four corner marks sit on)
        // measures 351.9 x 479.9, aspect 0.7333; the box is 67/94 = 0.7128,
        // narrower than the card, so preserveAspect draws the card 67 px wide
        // and 91.37 px tall, from y=652.31 to y=743.69, and the plate shows
        // 1.31 px above and below it in the badge's own dark. The ~1.9 px the
        // box is short of a height-limited width is slack, so a small error
        // in the measured card aspect cannot flip the fit. Rail contact
        // without covering the frame needs a per-pixel trim of the capture's
        // corners -- the pre-composite alpha kept per card and a thumbnail
        // texture of its own, since the thumbnail shares the full sprite's
        // texture -- and that is a follow-up, not this.
        //
        // preserveAspect (CreatePanelCentred) does the scaling, and what it
        // scales is CardSnapshot's THUMBNAIL: the capture cropped to the
        // card's corner band, not the whole 380x600 render. That crop is
        // what lines the corner marks up with this box -- the full render
        // carries the camera's 8% wobble pad and the letterbox the fixed RT
        // aspect adds, and fitting THAT lands the card's own edge ~9-10 px
        // inside the box (observation 1, 2026-09-21).
        //
        // Before 9a these were 60x77 and 50x73, inset and offset up-left
        // inside the old silhouette; the art did not reach the box edges.
        //
        // A pre-9a server face draws its badge_mark in [92,654,144,722]. The
        // earlier rects started the plate at x=92 so that it covered the
        // mark's left sliver (observation 2, 2026-09-21); from x=100 the
        // plate leaves the mark's x 92-100 strip visible on such a face. The
        // name column, which every 9a face draws, takes precedence.
        // Fractions of the face, top-left origin.
        private const float TC_BACK_X = 100f / 750f, TC_BACK_Y = 651f / 1050f, TC_BACK_W = 67f / 750f, TC_BACK_H = 94f / 1050f;
        private const float TC_ART_X = 100f / 750f, TC_ART_Y = 651f / 1050f, TC_ART_W = 67f / 750f, TC_ART_H = 94f / 1050f;
        private static readonly Color C_BADGE_DARK = new Color(0.08f, 0.08f, 0.10f, 1f);
        private static readonly Color C_FACE_DIM = new Color(0.42f, 0.42f, 0.48f, 1f);

        /// <summary>An Image child anchored at its parent's centre, click-through,
        /// aspect-preserving, inactive until placed.</summary>
        private static GameObject CreatePanelCentred(string name, Transform parent, Color c)
        {
            var go = UIFactory.CreatePanel(name, parent, c);
            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0.5f, 0.5f); rt.anchorMax = new Vector2(0.5f, 0.5f); rt.pivot = new Vector2(0.5f, 0.5f);
            rt.anchoredPosition = Vector2.zero; rt.sizeDelta = Vector2.zero;
            try
            {
                var img = UIFactory.tImage != null ? go.GetComponent(UIFactory.tImage) : null;
                var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance;
                if (img != null)
                {
                    UIFactory.tImage.GetProperty("raycastTarget", bf)?.SetValue(img, false);
                    UIFactory.tImage.GetProperty("preserveAspect", bf)?.SetValue(img, true);
                }
            }
            catch { }
            go.SetActive(false);
            return go;
        }

        /// <summary>Lay one overlay child over a fraction box of the face. The
        /// face Image preserves the 5:7 aspect inside its own rect, so the drawn
        /// picture is the largest 5:7 box centred in it; the child's anchors are
        /// the rect's centre, so this holds for any pivot and any slot shape.</summary>
        private static void PlaceOverFace(GameObject face, GameObject child, float fx, float fy, float fw, float fh)
        {
            if (face == null || child == null) return;
            var frt = face.GetComponent<RectTransform>(); var crt = child.GetComponent<RectTransform>();
            if (frt == null || crt == null) return;
            Rect r = frt.rect;
            float s = Mathf.Min(r.width / PlayerCardFaces.CARD_W, r.height / PlayerCardFaces.CARD_H);
            if (s <= 0f) { crt.sizeDelta = Vector2.zero; return; }
            float pw = PlayerCardFaces.CARD_W * s, ph = PlayerCardFaces.CARD_H * s;
            crt.anchoredPosition = new Vector2((fx + fw / 2f - 0.5f) * pw, (0.5f - fy - fh / 2f) * ph);
            crt.sizeDelta = new Vector2(fw * pw, fh * ph);
        }

        /// <summary>Show the tile's Top card art when its face is showing, the
        /// print names a top card and CardSnapshot has the sprite (asked for
        /// when it has not); otherwise the face's own badge stands. Called when
        /// a face is shown or hidden and every frame while the tab is up: the
        /// snapshot lands later, the layout settles later, and a snapshot
        /// generation change can void a sprite under the overlay.</summary>
        private static void PlaceTopCard(Tile t)
        {
            if (t == null || t.face == null || t.topArt == null || t.topBack == null) return;
            var p = t.print;
            string card = (p != null && t.face.activeSelf) ? p.top_card : null;
            Sprite spr = null;
            // The THUMBNAIL, not the full snapshot: cropped to the card's
            // corner band so the card's own edge -- the rect its corner
            // marks sit on -- is what preserveAspect fits into this box, and
            // the card's own name plate stays out of a ~91 px picture. The
            // full sprite is unchanged for every other
            // consumer (CardImageLoader, TabStatsOverlay, the card preview).
            bool show = !string.IsNullOrEmpty(card) && CardSnapshot.TryGetThumbSprite(card, out spr) && spr != null;
            if (!show)
            {
                if (!string.IsNullOrEmpty(card) && !CardSnapshot.IsFailed(card)) CardSnapshot.RequestSnapshot(card, false);
                if (t.topArt.activeSelf) t.topArt.SetActive(false);
                if (t.topBack.activeSelf) t.topBack.SetActive(false);
                t.topSprite = null;
                return;
            }
            if (t.topSprite != spr)
            {
                UIFactory.SetImageSprite(t.topArt, spr);
                t.topSprite = spr;
                UIFactory.SetImageColor(t.topArt, p.discarded ? C_FACE_DIM : Color.white);
            }
            PlaceOverFace(t.face, t.topBack, TC_BACK_X, TC_BACK_Y, TC_BACK_W, TC_BACK_H);
            PlaceOverFace(t.face, t.topArt, TC_ART_X, TC_ART_Y, TC_ART_W, TC_ART_H);
            if (!t.topBack.activeSelf) t.topBack.SetActive(true);
            if (!t.topArt.activeSelf) t.topArt.SetActive(true);
        }

        private static void PlaceTopCards()
        {
            if (revealTiles != null) foreach (var t in revealTiles) PlaceTopCard(t);
            if (binderTiles != null) foreach (var t in binderTiles) PlaceTopCard(t);
            PlaceTopCard(cardPopupTile);
        }

        // -- dance cards playback (design S5.5, S5.7) --------------------------------

        /// <summary>The dance overlay of one face: the existing centred,
        /// click-through, aspect-preserving panel, moved to be the FIRST child
        /// of the face so the Top card overlay and the discarded stamp stay
        /// above it. Inactive until placed.</summary>
        internal static GameObject CreateMotionOverlay(GameObject face)
        {
            if (face == null) return null;
            var go = CreatePanelCentred("DcMo", face.transform, Color.white);
            go.transform.SetAsFirstSibling();
            return go;
        }

        /// <summary>Lay the overlay over the face's portrait window, through the
        /// same letterbox-aware fraction box PlaceTopCard uses.</summary>
        internal static void PlaceMotionOverlay(GameObject face, GameObject child)
        {
            if (PlayerCardMotion.DevT51AnchorToRect) { PlayerCardMotion.DevPlaceByRect(face, child); return; }
            PlaceOverFace(face, child, PlayerCardMotionCore.WIN_X, PlayerCardMotionCore.WIN_Y, PlayerCardMotionCore.WIN_W, PlayerCardMotionCore.WIN_H);
        }

        private static float motionWarnAt;
        private static readonly List<PlayerCardMotion.Slot> motionTiles = new List<PlayerCardMotion.Slot>();
        private static readonly List<PlayerCardMotion.Slot> motionPool = new List<PlayerCardMotion.Slot>();
        private static readonly PlayerCardMotion.Slot motionPopup = new PlayerCardMotion.Slot();
        // The playback's view names, one per View value and indexed by it,
        // derived from the enum itself so a view added later has its entry
        // (bug 405: a hand-written list of three threw on every Trades frame).
        private static readonly string[] MotionViews = MotionViewNames();

        private static string[] MotionViewNames()
        {
            var values = (View[])Enum.GetValues(typeof(View));
            int top = 0;
            foreach (var v in values) top = Math.Max(top, (int)v);
            var names = new string[top + 1];
            for (int i = 0; i < names.Length; i++) names[i] = "view" + i;   // a gap in the values still has an entry
            foreach (var v in values) if ((int)v >= 0) names[(int)v] = v.ToString().ToLowerInvariant();
            return names;
        }
        private static string motionKey, motionKeyPack;
        private static int motionKeyView = -1, motionKeyPage = int.MinValue;

        /// <summary>The playback's view of this tab each tick: the shown page's
        /// active tiles, the popup, the subview and the page identity (a binder
        /// page number, or the history pack shown). Allocates only when the page
        /// identity changes.</summary>
        private static void MotionTick(bool onTab)
        {
            bool popup = cardPopupTile != null;
            motionTiles.Clear();
            int used = 0;
            string key = null;
            if (onTab)
            {
                if (view == View.Binder) { MotionAdd(binderTiles, ref used); key = MotionPageKey(1, binderPage, null); }
                else if (view == View.Open)
                {
                    var shown = historyIndex >= 0 && historyIndex < packHistory.Count ? packHistory[historyIndex] : null;
                    if (lastStrip != null && lastStrip.activeInHierarchy) MotionAdd(revealTiles, ref used);
                    key = MotionPageKey(0, historyIndex, shown != null ? shown.pack_id : null);
                }
                else key = MotionPageKey((int)view, 0, null);
            }
            PlayerCardMotion.Slot pop = null;
            if (popup)
            {
                motionPopup.Face = cardPopupTile.face; motionPopup.Print = cardPopupTile.print; motionPopup.BindSeq = cardPopupSeq;
                pop = motionPopup;
            }
            PlayerCardMotion.Tick(onTab || popup, pendingVisit, MotionViews[(int)view], key, motionTiles, pop);
        }

        private static void MotionAdd(Tile[] tiles, ref int used)
        {
            if (tiles == null) return;
            for (int i = 0; i < tiles.Length; i++)
            {
                var t = tiles[i];
                if (t == null || t.root == null || t.print == null || !t.root.activeInHierarchy) continue;
                if (used == motionPool.Count) motionPool.Add(new PlayerCardMotion.Slot());
                var s = motionPool[used++];
                s.Face = t.face; s.Print = t.print; s.BindSeq = t.bindSeq;
                motionTiles.Add(s);
            }
        }

        private static string MotionPageKey(int v, int page, string pack)
        {
            if (motionKey == null || v != motionKeyView || page != motionKeyPage || !string.Equals(pack, motionKeyPack, StringComparison.Ordinal))
            {
                motionKeyView = v; motionKeyPage = page; motionKeyPack = pack;
                motionKey = v.ToString(System.Globalization.CultureInfo.InvariantCulture) + ":" + page.ToString(System.Globalization.CultureInfo.InvariantCulture) + ":" + (pack ?? "");
            }
            return motionKey;
        }

        /// <summary>The playback levers' hands on this tab (PlayerCardMotionDev,
        /// broadcast identity only): each verb is the product's own action for
        /// that event, on a synthetic binder -- nothing is sent to the api.</summary>
        internal static void DevMotionAct(string what, int arg)
        {
            switch (what)
            {
                case "seed": DevSeedMotionPrints(arg); break;
                case "card": DevMotionCard(arg); break;
                case "close": HideCardPopup(); break;
                case "tab": PlayerCardMotion.TabEntered(); break;
                case "next": BinderNext(); break;
                case "prev": BinderPrev(); break;
                case "page0": view = View.Binder; binderPage = 0; NativeUI.MarkDirty(); break;
                case "view": view = View.Open; NativeUI.MarkDirty(); break;
                case "binder": view = View.Binder; NativeUI.MarkDirty(); break;
                case "repaint": NativeUI.MarkDirty(); break;
                case "refresh": { var col = ApiClient.CachedPcCollection; if (col != null) ApiClient.DevSetCollection(col); NativeUI.MarkDirty(); } break;
                case "sort": CycleSort(); break;
                case "overlay-close": OnOverlayClosed(); PlayerCardMotion.Clear(); break;
            }
        }

        internal static string DevMotionFirstPrint()
        {
            var t = binderTiles != null && binderTiles.Length > 0 ? binderTiles[0] : null;
            return t != null && t.print != null ? t.print.print_id : null;
        }

        internal static GameObject DevMotionFirstFace()
        {
            var t = binderTiles != null && binderTiles.Length > 0 ? binderTiles[0] : null;
            return t != null ? t.face : null;
        }

        private static void DevSeedMotionPrints(int n)
        {
            n = Mathf.Clamp(n, 1, 40);
            var col = new ApiClient.PcCollection { owner_steam_id = "dev", owner_name = "Sid", is_public = true };
            string[] rar = { "legendary", "epic", "rare", "uncommon", "common" };
            for (int i = 0; i < n; i++)
            {
                var p = new ApiClient.PcPrint
                {
                    print_id = "dvm" + i.ToString("D2", System.Globalization.CultureInfo.InvariantCulture), card_id = "dvmc" + i, subject_player_id = "dvmp" + i,
                    subject_name = "Player " + i.ToString("D2", System.Globalization.CultureInfo.InvariantCulture), edition_id = "1", minted_at = "2026-09-27T00:00:00",
                    rarity = rar[i % rar.Length], pool_rank = i + 1, rating = 1800 - i * 10, peak_rating = 1850 - i * 10, rank_name = "Advanced I",
                    source = "bought", slot = i % 5, dup_at_pull = -1, face_rev = "dev", top_card = "",
                };
                col.prints.Add(p);
                if (PlayerCardFaces.Cached(p.print_id, "dev", "en", "tile") == null)
                    PlayerCardFaces.DevPut(p.print_id, "dev", "en", "tile", DevSprite(FrameColor(p.rarity, false)), 375L * 525L * 4L);
            }
            col.count = col.prints.Count;
            ApiClient.DevSetCollection(col);
            binderSort = Sort.Name;
            view = View.Binder; binderPage = 0;
            NativeUI.MarkDirty();
        }

        private static void DevMotionCard(int i)
        {
            var t = binderTiles != null && i >= 0 && i < binderTiles.Length ? binderTiles[i] : null;
            var p = t != null ? t.print : null;
            if (p == null) return;
            if (PlayerCardFaces.Cached(p.print_id, p.face_rev, p.face_locale, "card") == null)
                PlayerCardFaces.DevPut(p.print_id, p.face_rev, p.face_locale, "card", DevSprite(FrameColor(p.rarity, false)), 750L * 1050L * 4L);
            ShowCard(new Tile { print = p });
        }

        // ── repaint ──────────────────────────────────────────────────────────
        internal static void Refresh()
        {
            if (tabRoot == null) return;
            var id = LocalId();
            var me = ApiClient.CachedPcMe;
            var st = ApiClient.CachedPlayerStats;
            // The Trades view exists only while the server trades (V8 6.9): a
            // 404 or no answer yet hides it, and a view left on it falls back.
            bool tradesShown = PcTradeRules.TabShown(tradeDiscovery);
            if (!tradesShown && view == View.Trades) { view = View.Open; EndCompose(); }
            if (viewBtns[3] != null && viewBtns[3].activeSelf != tradesShown) viewBtns[3].SetActive(tradesShown);
            PaintTradesLabel();
            for (int i = 0; i < viewBtns.Length; i++)
            {
                if (viewBtns[i] != null) UIFactory.SetImageColor(viewBtns[i], (int)view == i ? C_BTNACT : C_BTN);
                if (viewTxts[i] != null) UIFactory.SetColor(viewTxts[i], (int)view == i ? C_WHITE : C_LABEL);
            }
            if (openRoot != null) openRoot.SetActive(view == View.Open);
            if (binderRoot != null) binderRoot.SetActive(view == View.Binder);
            if (infoRoot != null) infoRoot.SetActive(view == View.Info);
            if (tradesRoot != null) tradesRoot.SetActive(view == View.Trades);

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
            else if (view == View.Trades) RefreshTrades(id);
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
                RefreshShardPackButton(shown);
            }
            else if (historyInFlight)
            {
                UIFactory.SetTextRaw(txtLastHdr, I18n.Tr("Loading your packs..."));
                UIFactory.SetTextRaw(txtHistPos, "");
                for (int i = 0; i < revealTiles.Length; i++) FillTile(revealTiles[i], null, 0);
                RefreshShardPackButton(null);
            }
            else RefreshShardPackButton(null);
        }

        /// <summary>Board row 25: the Shard pack button on the pack on show --
        /// up while the pack still holds a card of yours this client has not
        /// seen discarded, labelled with the total those cards pay (the second
        /// click's label once armed), "sharding..." while a batch is out.</summary>
        private static void RefreshShardPackButton(ApiClient.PcPackAnswer shown)
        {
            if (btnShardPack == null) return;
            var ids = PackShardIds(shown);
            bool up = ids.Count > 0 && ids.Count <= ApiClient.PC_DISCARD_BATCH_CAP
                      && !packShardBurned.Contains(shown.pack_id);
            bool busy = shardInFlight && shown != null && shardPackId == shown.pack_id;
            btnShardPack.SetActive(up || busy);
            if (!up && !busy) return;
            int total = ShardTotal(shown.prints, ids);
            bool armed = armedShard != null && armedShard == PackShardSet(shown.pack_id, ids) && Now - armedShardAt <= 6f;
            UIFactory.SetTextRaw(btnShardPackTxt, busy ? I18n.Tr("sharding...")
                : armed ? I18n.TrF("Sure? +{0} shards", total) : I18n.TrF("Shard pack (+{0})", total));
            UIFactory.SetImageColor(btnShardPack, SessionReady && !shardInFlight && !discardInFlight ? C_DANGER : C_BTN);
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
        // historyGen names a HISTORY (bumped by HistoryReset); historySerial
        // names a page REQUEST (bumped by its 25 s give-up as well), so a
        // late page cannot land after the request was given up.
        private static float historySentAt; private static int historySerial;
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
        /// A discarded print's face is served like a live one (Sept 14
        /// batch, S3), so its 404 means the same moved revision; a history
        /// not loaded yet has its first load still ahead of it.</summary>
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
                    if (p.print_id != printId || p.face_rev != faceRev) continue;
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
            historySentAt = Now;
            int ep = uiEpoch, gen = historyGen, serial = ++historySerial;
            NativeUI.MarkDirty();
            ApiClient.FetchPcPacks(id, before, (ok, resp, h) =>
            {
                if (ep != uiEpoch || gen != historyGen) return;   // reset since: its flags went with it
                if (serial != historySerial)
                {
                    Plugin.Log.LogInfo($"[PC] pack history: answer to serial {serial} dropped (given up)");
                    return;
                }
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

        // The binder's page buttons: a page change asked for, which the playback
        // counts as a new visit once the shown page moves (S5.3).
        private static void BinderPrev()
        {
            if (binderPage <= 0) return;
            binderPage--;
            try { PlayerCardMotion.NavRequested(); } catch { }
            NativeUI.MarkDirty();
        }

        private static void BinderNext()
        {
            binderPage++;
            try { PlayerCardMotion.NavRequested(); } catch { }
            NativeUI.MarkDirty();
        }

        private static void PageHistory(int delta)
        {
            var id = LocalId();
            int next = historyIndex + delta;
            if (next < 0) return;
            try { PlayerCardMotion.NavRequested(); } catch { }
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

        /// <summary>What this session knows about the subjects' standings.
        /// Three values, because "no answer has been read yet" and "an answer
        /// was read and carried none" must not decide the same way (#430) —
        /// the cycler may treat them alike, the restore may not.</summary>
        private static BinderSortRules.Standings CurrentStandings()
        {
            var col = ApiClient.CachedPcCollection;
            if (col == null) return BinderSortRules.Standings.Unknown;
            return col.subject_standings
                ? BinderSortRules.Standings.Present
                : BinderSortRules.Standings.Absent;
        }

        /// <summary>The header button. The next mode comes from
        /// BinderSortRules, which derives the cycle length from the enum — the
        /// "% 5" that stood here was right for exactly as long as there were
        /// five sorts — and steps over a mode the current answer cannot serve.
        ///
        /// This is the ONLY writer of the stored sort: an explicit click. No
        /// paint path, no fallback and no availability test writes it, so a
        /// session that cannot offer the rating sort costs the player that
        /// session's ordering and never the preference itself.</summary>
        private static void CycleSort()
        {
            binderSort = BinderSortRules.Next(binderSort, CurrentStandings());
            pendingBinderSort = null;   // an explicit choice supersedes a restore still waiting
            if (Plugin.BinderSort != null) Plugin.BinderSort.Value = BinderSortRules.NameOf(binderSort);
            binderPage = 0;
            try { PlayerCardMotion.Rebase(); } catch { }   // a reorder, never a visit (S5.3)
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
                case Sort.RatingPosition: return I18n.Tr("Rating position");
                default: return I18n.Tr("Name");
            }
        }

        /// <summary>Plugin.Awake hands over the stored sort once. Parsing is
        /// BinderSortRules' job (a member NAME, never an ordinal; an
        /// unrecognised one falls back to Name) and applying it is deferred —
        /// see pendingBinderSort.</summary>
        internal static void RestoreBinderSort(string stored)
        {
            pendingBinderSort = BinderSortRules.Parse(stored, Sort.Name);
        }

        private static int EditionNo(ApiClient.PcPrint p) { int e; return int.TryParse(p.edition_id ?? "", out e) ? e : int.MaxValue; }

        /// <summary>One print reduced to the keys the order reads. Everything
        /// locale- or Unity-dependent is resolved HERE — SafeName goes through
        /// I18n, RarityOrder is already a number — so BinderSortRules stays
        /// free of both and can be run under a plain compiler.</summary>
        private static BinderSortRules.Subject SortKey(ApiClient.PcPrint p)
        {
            return new BinderSortRules.Subject
            {
                PrintId = p.print_id,
                CardId = p.card_id,
                EditionId = p.edition_id,
                MintedAt = p.minted_at,
                Name = SafeName(p),
                RarityOrder = RarityOrder(p.rarity),
                Foil = p.foil,
                Signed = p.signed,
                EditionNo = EditionNo(p),
                PoolRank = p.pool_rank,
                MintBoardRank = p.board_rank,       // the number on the card face
                SubjectId = p.subject_player_id,
                Rank = p.subject_board_rank,        // where that player stands today
                Inactive = p.subject_inactive,
                Rated = p.subject_rated,
                Rating = p.subject_rating,
            };
        }

        /// <summary>The binder order. The rule itself is BinderSortRules.Compare,
        /// which the harness runs: the chosen key first, then the name order as
        /// the tiebreaker under every mode (and the whole order under Name),
        /// down to the print id so the order is total.</summary>
        private static int CompareForBinder(ApiClient.PcPrint a, ApiClient.PcPrint b)
        {
            return BinderSortRules.Compare(SortKey(a), SortKey(b), binderSort);
        }

        private static void RefreshBinder(ApiClient.PcMe me)
        {
            var col = ApiClient.CachedPcCollection;
            // The deferred restore (item 20), BEFORE the sort, off the same
            // `col` this paint reads. Unknown keeps it waiting; only an answer
            // that was actually read decides, and neither outcome touches the
            // stored value.
            if (pendingBinderSort.HasValue)
            {
                switch (BinderSortRules.Resolve(pendingBinderSort.Value, CurrentStandings()))
                {
                    case BinderSortRules.Restore.Apply:
                        binderSort = pendingBinderSort.Value;
                        pendingBinderSort = null;
                        binderPage = 0;
                        break;
                    case BinderSortRules.Restore.DropForSession:
                        pendingBinderSort = null;
                        break;
                    // Keep: the fetch has not answered yet; try again next paint.
                }
            }
            sorted.Clear(); faceCounts.Clear();
            if (col != null)
            {
                sorted.AddRange(col.prints);
                sorted.Sort(CompareForBinder);
                foreach (var p in sorted) { string k = FaceKey(p); int n; faceCounts.TryGetValue(k, out n); faceCounts[k] = n + 1; }
                // Board row 25: a picked card that left the collection (a
                // refetch, a discard, another device) is no longer picked.
                if (selectedIds.Count > 0)
                {
                    var held = new HashSet<string>(StringComparer.Ordinal);
                    foreach (var p in col.prints) if (p != null && p.print_id != null) held.Add(p.print_id);
                    selectedIds.RemoveAll(x => !held.Contains(x));
                }
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
            else if (shardInFlight) hdr += "  -  " + I18n.Tr("sharding...");
            UIFactory.SetTextRaw(txtBinderHdr, hdr);
            RefreshSelectRow(col);
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
            LogBadges(sorted);
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
                + I18n.Tr("- Ranked wins: winning a ranked series - or a ranked FFA match - rolls a 20% chance of a pack. The same chance in every mode, whatever the score line. Earned packs wait here until you open them.") + "\n"
                + (me != null && me.paid_cap_exempt
                    ? I18n.TrF("- Buy one for {0} gold or {1} shards. No daily limit on this account.", gold, shards)
                    : I18n.TrF("- Buy one for {0} gold or {1} shards, up to {2} paid packs a day.", gold, shards, cap)) + "\n\n"
                + I18n.TrF("Each pack holds {0} cards. A card's rarity is its player's rank in the card pool on the day of the pull: Legendary = #1-2, Epic #3-10, Rare #11-20, Uncommon #21-40, Common #41 and below. Odds per card: Common 60%, Uncommon 25%, Rare 11%, Epic 3.5%, Legendary 0.5%. Every card also rolls Foil (1 in 200) and Signed (1 in 2000) on its own.", per) + "\n\n"
                + I18n.Tr("Discarding a card gives shards by its rarity: Common 5, Uncommon 15, Rare 40, Epic 150, Legendary 600. Shards buy packs. Discard takes one card and the Dupes button every other copy of that exact card; Shard pack (on a pack you opened) and Select (in the binder) shard up to 40 cards in one go.") + "\n"
                // its own literal, right after the discard sentence (V8 6.7, F13; the
                // batch shard lane reworded that sentence, this one is unchanged)
                + I18n.Tr("Cards received in a trade may give fewer shards when discarded.") + "\n\n"
                + I18n.Tr("A card freezes its player's title, rating, record and rank as the leaderboard had them on the day it was pulled; the name and the picture stay live (a renamed player shows their new name). Every player who has run the mod from a Steam account and is not banned can be pulled; a public binder and pull announcements are your Settings, and deleting your data removes every card of you from every binder.");
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
            recoverSentAt = Now;
            int ep = uiEpoch, serial = ++recoverSerial;
            Plugin.Log.LogInfo($"[PC] recovering {kind} intent (age {age:F0}s, serial {serial})");
            ApiClient.PcPackResult(id, kind == "buy" ? reference : null, kind == "pack" ? reference : null,
                (ok, resp) =>
                {
                    if (ep != uiEpoch) return;   // identity changed meanwhile (c4)
                    if (serial != recoverSerial)
                    {
                        // The intent is still on disk, so nothing is lost: the
                        // next recovery asks the same idempotent question again.
                        Plugin.Log.LogInfo($"[PC] recovery: answer to serial {serial} dropped (given up)");
                        return;
                    }
                    recoverInFlight = false;
                    HandleAnswer(ok, resp, true);
                });
        }

        /// <summary>The 25 s give-up for the three latches that had none
        /// (carried item ii, the settings card latch's rule from asks-b round
        /// 2): past ApiClient's 20 s transport timeout an answer that has not
        /// come is not coming - a request whose coroutine was stopped (the
        /// persistent host respawned, Plugin.cs OnDestroy) never runs its
        /// callback, and the latch would otherwise hold for the session. Each
        /// give-up bumps that latch's serial, so an answer that does arrive
        /// later commits nothing. Runs on every 2 s tick, above the tick's
        /// early returns.</summary>
        private static void RetireStuckLatches(string id)
        {
            if (historyInFlight && Now - historySentAt > 25f)
            {
                historyInFlight = false;
                historySerial++;
                historyFailedAt = Now;   // EnsureHistory's own 30 s retry, as after a failed page
                Plugin.Log.LogWarning("[PC] pack history: no answer 25 s after the request; given up");
                NativeUI.MarkDirty();
            }
            if (recoverInFlight && Now - recoverSentAt > 25f)
            {
                recoverInFlight = false;
                recoverSerial++;
                Plugin.Log.LogWarning("[PC] recovery: no answer 25 s after the request; given up, the intent is kept");
                NativeUI.MarkDirty();
            }
            if (discardInFlight && Now - discardSentAt > 25f)
            {
                discardSerial++;
                Plugin.Log.LogWarning($"[PC] discard: no answer 25 s into the run's step ({discardDone} done); run given up");
                // Whether the unanswered discard applied is unknown, so the
                // binder and the balance are re-read ("transport" alone skips
                // that refetch - it is the code for an answer that FAILED).
                FinishDiscard(id, "transport");
                if (id != null) { ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true); }
            }
        }

        private static void OnDiscardClick(Tile t, bool dupes)
        {
            var p = t?.print; var id = LocalId();
            if (p == null || id == null || discardInFlight || shardInFlight) return;
            if (!SessionReady) { Say(ReasonText("session_required"), C_WARN); return; }
            if (armedPrintId != p.print_id || armedDupes != dupes || Now - armedAt > 6f)
            {
                armedPrintId = p.print_id; armedDupes = dupes; armedAt = Now;
                string ask = dupes ? I18n.Tr("Click Dupes again to discard every other copy of that card") : I18n.Tr("Click Discard again to discard that card for shards");
                // Board row 25 (b): the last copy of a card is the player's
                // call, so the first click says so and the second still
                // discards it. Dupes always keeps the copy it was clicked on.
                if (!dupes && t.dupes <= 1) ask += " - " + I18n.TrF("this is your only copy of {0}", SafeName(p));
                Say(ask);
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
            discardDone = 0; discardShards = 0; discardWaited = 0f; discardRetriedIds.Clear(); discardInFlight = true;
            int serial = ++discardSerial;
            NativeUI.MarkDirty();
            DiscardNext(id, serial);
        }

        private static void DiscardNext(string id, int serial)
        {
            if (discardQueue.Count == 0) { FinishDiscard(id, null); return; }
            string pid = discardQueue[0]; discardQueue.RemoveAt(0);
            int ep = uiEpoch;
            discardSentAt = Now;
            ApiClient.PcDiscard(id, pid, (ok, resp) =>
            {
                if (ep != uiEpoch) return;   // identity changed meanwhile (c4)
                if (serial != discardSerial)
                {
                    Plugin.Log.LogInfo($"[PC] discard: answer for run {serial} dropped (given up)");
                    return;
                }
                if (ok)
                {
                    discardDone++;
                    int gained = ApiClient.PcInt(ApiClient.PcTopLevel(resp, "shards_gained"));
                    discardShards += gained;
                    var col = ApiClient.CachedPcCollection;
                    if (col != null) col.prints.RemoveAll(x => x.print_id == pid);
                    HistoryMarkDiscarded(pid, gained);
                    DiscardNext(id, serial);
                    return;
                }
                string code = ApiClient.PcErrorCode(resp);
                float wait = ApiClient.PcRetryAfter(resp, 3);
                // A dupes discard is one request per copy, and the card routes
                // carry a request budget of their own that one request per copy
                // stays inside: a rate-limited answer is waited out and the same
                // copy asked again, once per copy; not a refusal, and not a
                // chain of refetches on top of the limit. The waiting a run may
                // do is capped by DiscardWaitBudget - past it the run ends and
                // says so instead of retrying without a ceiling.
                if (code == "rate_limited" && !discardRetriedIds.Contains(pid))
                {
                    if (discardWaited + wait <= DiscardWaitBudget)
                    {
                        discardRetriedIds.Add(pid);
                        discardWaited += wait;
                        discardQueue.Insert(0, pid);
                        Say(I18n.TrF("Slowing down - the server asked for a {0} s pause", (int)wait), C_WARN);
                        // The step's give-up counts from the END of the pause:
                        // the pause is ours, not an unanswered request. A
                        // pause whose coroutine never resumes (the host
                        // respawned) is still given up 25 s after it ends.
                        discardSentAt = Now + wait;
                        Plugin.Instance.StartCoroutine(DiscardAfter(id, wait, ep, serial));
                        return;
                    }
                    // This copy still had its retry; the RUN has no waiting
                    // time left. Reported as its own reason - a player who has
                    // just watched us wait out two pauses is not being told
                    // the same thing as one whose first request was refused.
                    FinishDiscard(id, "rate_limit_waited");
                    return;
                }
                FinishDiscard(id, code);
            });
        }

        private static IEnumerator DiscardAfter(string id, float seconds, int ep, int serial)
        {
            yield return new WaitForSecondsRealtime(seconds);
            // serial: a pause of a run that was given up must not resume a
            // NEWER run (discardInFlight alone is true again for that one).
            if (ep != uiEpoch || !discardInFlight || serial != discardSerial) yield break;
            // DELIBERATELY does not clear the per-copy latch. Resuming IS the
            // retry; clearing it here was what turned "one retry per copy"
            // into "one retry in flight" and let a single copy loop until the
            // run budget ran out.
            //
            // CORRECTED (Codex client r2 LOW): "cleared only by FinishDiscard"
            // was not the whole list, and the omissions are exactly the two a
            // reader needs in order to decide whether a stale latch can
            // survive. THREE sites clear it, and every one of them ends a RUN:
            // FinishDiscard (the run finished or gave up), the new-run
            // initialisation in the discard entry point (a fresh run starts
            // with no copy already retried), and the identity change (another
            // account's run must not inherit this one's retries). What no site
            // does is clear it MID-RUN — that is the property this comment is
            // actually here for.
            DiscardNext(id, serial);
        }

        private static void FinishDiscard(string id, string errorCode)
        {
            discardInFlight = false; discardQueue.Clear(); discardRetriedIds.Clear(); discardWaited = 0f;
            // One line for both halves: what was discarded stays reported when
            // the next discard fails (c4).
            if (discardDone > 0 && errorCode != null)
                Say(I18n.TrF("Discarded {0} card(s) for {1} shards; then: {2}", discardDone, discardShards, ReasonText(errorCode)), C_WARN);
            else if (discardDone > 0)
                Say(I18n.TrF("Discarded {0} card(s) for {1} shards", discardDone, discardShards), C_OK);
            else if (errorCode != null) Say(ReasonText(errorCode), C_WARN);
            // The collection and the balance were updated from each discard's
            // own answer, so a clean run needs no refetch (Sept 14 batch, C2:
            // the two refetches after every discard were what the rate limit
            // saw first). A refusal other than the limit itself re-reads both,
            // since the local copy may be what was wrong (not_owned).
            // rate_limit_waited is excluded for the same reason rate_limited
            // is: two refetches on top of a limit that is already refusing us
            // are exactly what C2 removed. A budget we exhausted is the one
            // moment we most need to stop asking.
            if (id != null && errorCode != null && errorCode != "rate_limited"
                && errorCode != "rate_limit_waited" && errorCode != "transport")
            {
                ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true);
            }
            NativeUI.MarkDirty();
        }


        // -- Board row 25: the batch shard ---------------------------------------
        // One server transaction per click (ApiClient.PcDiscardBatch): up to
        // PC_DISCARD_BATCH_CAP prints, all discarded or none, the credit one
        // delta, keyed by the pack id (Shard pack) or by a nonce kept for the
        // exact selection until an answer arrives (Shard selected), so a retry
        // after a lost answer is answered the stored total and never pays
        // twice. Two clicks, as Discard: the first names the total and every
        // card the batch would take the last copy of (the player's call, not a
        // server block), the second sends. The Dupes button keeps its own
        // one-request-per-copy loop on the single route.

        /// <summary>The shards a discard pays by rarity: PC_ECONOMY["shards"] in
        /// backend/api/player_cards.py, pinned equal by test_pc_shard_client.
        /// Only the confirmation's total reads it; what is credited is the
        /// server's own figure, which the toast reports.</summary>
        private static int ShardValue(string rarity)
        {
            switch (rarity)
            {
                case "legendary": return 600;
                case "epic": return 150;
                case "rare": return 40;
                case "uncommon": return 15;
                default: return 5;
            }
        }

        /// <summary>The batch shard met card trading in the v1.41.0 beta (merge
        /// pass 2): a print ever received by trade (pc_prints.acquired_by_trade,
        /// the own binder's permanent `traded` flag) is paid
        /// PC_TRADE["traded_discard_shards"] whatever its rarity, not its
        /// rarity's value. The client hardcodes no trade value, so such a print
        /// is counted at the bound the last full trades read carried, and at 0
        /// while no read has; the question then says such cards may give fewer
        /// shards (TradedNote). The flag is read from the print or, for a pack
        /// answer's print, which does not carry it, from the collection by id.
        /// Every other print is counted at its rarity (ShardValue).</summary>
        private static int ShardValueOf(ApiClient.PcPrint p, HashSet<string> tradedIds)
        {
            if (p == null) return 0;
            if (p.traded || (p.print_id != null && tradedIds.Contains(p.print_id)))
            {
                var full = ApiClient.CachedPcTrades;
                return full != null && full.bounds != null ? Math.Max(0, full.bounds.traded_discard_shards) : 0;
            }
            return ShardValue(p.rarity);
        }

        /// <summary>The print ids the cached own collection marks as received by trade.</summary>
        private static HashSet<string> TradedIds()
        {
            var s = new HashSet<string>(StringComparer.Ordinal);
            var col = ApiClient.CachedPcCollection;
            if (col != null)
                foreach (var p in col.prints)
                    if (p != null && p.traded && p.print_id != null) s.Add(p.print_id);
            return s;
        }

        private static int ShardTotal(List<ApiClient.PcPrint> prints, List<string> ids)
        {
            int traded;
            return ShardTotal(prints, ids, out traded);
        }

        /// <summary>The confirmation's total over the batch, and how many of its
        /// prints were received by trade (ShardValueOf).</summary>
        private static int ShardTotal(List<ApiClient.PcPrint> prints, List<string> ids, out int traded)
        {
            int total = 0;
            traded = 0;
            if (prints == null || ids == null) return 0;
            var want = new HashSet<string>(ids, StringComparer.Ordinal);
            var tradedIds = TradedIds();
            foreach (var p in prints)
                if (p != null && p.print_id != null && want.Remove(p.print_id))
                {
                    if (p.traded || tradedIds.Contains(p.print_id)) traded++;
                    total += ShardValueOf(p, tradedIds);
                }
            return total;
        }

        /// <summary>The question's line for a batch holding a print received by
        /// trade: the Info page's own sentence, so the two never disagree.</summary>
        private static string TradedNote(int traded)
        {
            return traded > 0 ? " - " + I18n.Tr("Cards received in a trade may give fewer shards when discarded.") : "";
        }

        private static ApiClient.PcPackAnswer ShownPack()
        {
            if (packHistory.Count == 0) return null;
            return packHistory[Math.Min(Math.Max(historyIndex, 0), packHistory.Count - 1)];
        }

        /// <summary>The server's key rule ([A-Za-z0-9-], 8 to 64 characters),
        /// which also covers the JSON body ApiClient writes ids into verbatim.</summary>
        private static bool ShardToken(string s)
        {
            if (string.IsNullOrEmpty(s) || s.Length < 8 || s.Length > 64) return false;
            foreach (char c in s)
                if (!(c == '-' || (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'))) return false;
            return true;
        }

        /// <summary>What a Shard pack sends: every print of the pack this client
        /// has not seen discarded and the server has not named as gone, sorted
        /// (the request is armed and keyed by the exact set). Empty for a pack
        /// without a usable id.</summary>
        private static List<string> PackShardIds(ApiClient.PcPackAnswer pack)
        {
            var ids = new List<string>();
            if (pack == null || pack.prints == null || !ShardToken(pack.pack_id)) return ids;
            foreach (var p in pack.prints)
                if (p != null && !p.discarded && ShardToken(p.print_id) && !shardGone.Contains(p.print_id) && !ids.Contains(p.print_id))
                    ids.Add(p.print_id);
            ids.Sort(StringComparer.Ordinal);
            return ids;
        }

        private static string PackShardSet(string packId, List<string> ids) { return "pack|" + packId + "|" + string.Join(",", ids.ToArray()); }
        private static string SelShardSet(List<string> ids) { return "sel|" + string.Join(",", ids.ToArray()); }

        /// <summary>The first click arms the exact request and answers false; a
        /// second click on the same request inside six seconds answers true.</summary>
        private static bool ShardConfirmed(string set)
        {
            if (armedShard == set && Now - armedShardAt <= 6f) { armedShard = null; return true; }
            armedShard = set; armedShardAt = Now;
            NativeUI.MarkDirty();
            return false;
        }

        /// <summary>" - this is your only copy of X, Y" for every card the batch
        /// would take the last copy of, counted by the exact card (FaceKey, the
        /// Dupes rule) over the collection AND the batch's own prints, so a pack
        /// opened after the collection was read still counts its own copies.
        /// The names are the subjects' as drawn, never translated (#602).</summary>
        private static string OnlyCopyNote(List<ApiClient.PcPrint> batch, ApiClient.PcCollection col)
        {
            var copies = new Dictionary<string, HashSet<string>>(StringComparer.Ordinal);
            System.Action<ApiClient.PcPrint> count = p =>
            {
                if (p == null || p.print_id == null || p.discarded) return;
                string k = FaceKey(p);
                HashSet<string> s;
                if (!copies.TryGetValue(k, out s)) { s = new HashSet<string>(StringComparer.Ordinal); copies[k] = s; }
                s.Add(p.print_id);
            };
            if (col != null) foreach (var p in col.prints) count(p);
            foreach (var p in batch) count(p);
            var taking = new Dictionary<string, int>(StringComparer.Ordinal);
            foreach (var p in batch) { string k = FaceKey(p); int n; taking.TryGetValue(k, out n); taking[k] = n + 1; }
            var names = new List<string>();
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var p in batch)
            {
                string k = FaceKey(p);
                HashSet<string> s;
                if (seen.Add(k) && copies.TryGetValue(k, out s) && taking[k] >= s.Count) names.Add(SafeName(p));
            }
            if (names.Count == 0) return "";
            string list = names.Count <= 3 ? string.Join(", ", names.ToArray())
                : string.Join(", ", names.GetRange(0, 3).ToArray()) + ", +" + (names.Count - 3);
            return " - " + I18n.TrF("this is your only copy of {0}", list);
        }

        private static void OnShardPackClick()
        {
            var id = LocalId();
            if (id == null || shardInFlight || discardInFlight) return;
            if (!SessionReady) { Say(ReasonText("session_required"), C_WARN); return; }
            var shown = ShownPack();
            var ids = PackShardIds(shown);
            if (ids.Count == 0 || packShardBurned.Contains(shown.pack_id)) return;
            if (ids.Count > ApiClient.PC_DISCARD_BATCH_CAP) { Say(I18n.TrF("You can shard up to {0} cards at once", ApiClient.PC_DISCARD_BATCH_CAP), C_WARN); return; }
            var col = ApiClient.CachedPcCollection;
            if (col == null) { ApiClient.FetchPcCollection(id, true); Say(I18n.Tr("Loading your binder - try again in a moment"), C_WARN); return; }
            var batch = new List<ApiClient.PcPrint>();
            var want = new HashSet<string>(ids, StringComparer.Ordinal);
            foreach (var p in shown.prints) if (p != null && p.print_id != null && want.Remove(p.print_id)) batch.Add(p);
            int traded;
            int total = ShardTotal(batch, ids, out traded);
            if (!ShardConfirmed(PackShardSet(shown.pack_id, ids)))
            {
                Say(I18n.TrF("Click Shard pack again to shard {0} cards for {1} shards", ids.Count, total) + OnlyCopyNote(batch, col) + TradedNote(traded), C_WARN);
                return;
            }
            SendShard(id, shown.pack_id, ids, shown.pack_id);
        }

        private static void OnSelectClick()
        {
            if (shardInFlight) return;
            selecting = !selecting;
            armedShard = null;
            if (!selecting) selectedIds.Clear();
            Plugin.Log.LogInfo("[PC] binder select " + (selecting ? "on" : "off"));
            NativeUI.MarkDirty();
        }

        private static void ToggleSelected(ApiClient.PcPrint p)
        {
            if (p == null || p.discarded || !ShardToken(p.print_id) || shardInFlight) return;
            if (!selectedIds.Remove(p.print_id))
            {
                if (selectedIds.Count >= ApiClient.PC_DISCARD_BATCH_CAP)
                {
                    Say(I18n.TrF("You can shard up to {0} cards at once", ApiClient.PC_DISCARD_BATCH_CAP), C_WARN);
                    return;
                }
                selectedIds.Add(p.print_id);
            }
            armedShard = null;   // another set: the next Shard selected asks again
            NativeUI.MarkDirty();
        }

        private static void OnShardSelectedClick()
        {
            var id = LocalId();
            if (id == null || shardInFlight || discardInFlight) return;
            if (!SessionReady) { Say(ReasonText("session_required"), C_WARN); return; }
            var col = ApiClient.CachedPcCollection;
            if (col == null) { ApiClient.FetchPcCollection(id, true); Say(I18n.Tr("Loading your binder - try again in a moment"), C_WARN); return; }
            var byId = new Dictionary<string, ApiClient.PcPrint>(StringComparer.Ordinal);
            foreach (var p in col.prints) if (p != null && p.print_id != null) byId[p.print_id] = p;
            selectedIds.RemoveAll(x => !byId.ContainsKey(x));
            if (selectedIds.Count == 0) { Say(I18n.Tr("Select cards first - click the cards you want to shard"), C_WARN); return; }
            if (selectedIds.Count > ApiClient.PC_DISCARD_BATCH_CAP) { Say(I18n.TrF("You can shard up to {0} cards at once", ApiClient.PC_DISCARD_BATCH_CAP), C_WARN); return; }
            var ids = new List<string>(selectedIds);
            ids.Sort(StringComparer.Ordinal);
            var batch = new List<ApiClient.PcPrint>();
            foreach (var x in ids) batch.Add(byId[x]);
            int traded;
            int total = ShardTotal(batch, ids, out traded);
            string set = SelShardSet(ids);
            if (!ShardConfirmed(set))
            {
                Say(I18n.TrF("Click Shard selected again to shard {0} cards for {1} shards", ids.Count, total) + OnlyCopyNote(batch, col) + TradedNote(traded), C_WARN);
                return;
            }
            // The nonce belongs to this exact selection until an answer arrives:
            // the same cards asked again after a lost answer are the same key,
            // which the server answers from its stored row (#172).
            if (shardKeyFor != set || string.IsNullOrEmpty(shardKey)) { shardKey = NewNonce(); shardKeyFor = set; }
            SendShard(id, shardKey, ids, null);
        }

        /// <summary>Item 18: the pull strip's Discard. Two clicks inside six
        /// seconds, as every shard control: the first names what the card
        /// pays and, when it is the player's last copy of that card, says so
        /// (the player's call, never a block); the second sends ONE request,
        /// the batch shard's route with this one print, keyed by a nonce kept
        /// for this card until an answer arrives. Nothing on screen changes
        /// until the server answers: the stamp and the balance come from the
        /// answer (FinishShard and ApiClient.PcDiscardBatch).</summary>
        private static void OnQuickShardClick(Tile t)
        {
            var p = t?.print; var id = LocalId();
            if (p == null || id == null || p.discarded || shardInFlight || discardInFlight) return;
            if (!SessionReady) { Say(ReasonText("session_required"), C_WARN); return; }
            if (!ShardToken(p.print_id) || shardGone.Contains(p.print_id)) return;
            // The last-copy count reads the collection: a positive signal, not
            // a guess from the pack alone (the Shard pack's own rule).
            var col = ApiClient.CachedPcCollection;
            if (col == null) { ApiClient.FetchPcCollection(id, true); Say(I18n.Tr("Loading your binder - try again in a moment"), C_WARN); return; }
            var one = new List<ApiClient.PcPrint> { p };
            var ids = new List<string> { p.print_id };
            string set = PcQuickShardRules.ArmSet(p.print_id);
            if (!ShardConfirmed(set))
            {
                int traded;
                int value = ShardTotal(one, ids, out traded);
                Say(I18n.Tr("Click Discard again to discard that card for shards") + " (+" + value + ")"
                    + OnlyCopyNote(one, col) + TradedNote(traded), C_WARN);
                return;
            }
            string key = shardFlight.KeyFor(set, () => NewNonce());
            SendShard(id, key, ids, null, p.print_id);
        }

        private static void RefreshSelectRow(ApiClient.PcCollection col)
        {
            if (btnSelect == null) return;
            btnSelect.SetActive(selecting || (col != null && col.prints.Count > 0));
            UIFactory.SetTextRaw(btnSelectTxt, selecting ? I18n.Tr("Stop selecting") : I18n.Tr("Select"));
            // The view line (its text set once, where it was built) gives way to
            // the select line while Select is on.
            var viewHint = (txtBinderHint as Component)?.gameObject;
            if (viewHint != null) viewHint.SetActive(!selecting);
            UIFactory.SetTextRaw(txtBinderSelHint, selecting ? I18n.Tr("Click cards to select them for shards") : "");
            if (btnShardSel == null) return;
            btnShardSel.SetActive(selecting);
            if (!selecting) return;
            var ids = new List<string>(selectedIds);
            ids.Sort(StringComparer.Ordinal);
            int total = col != null ? ShardTotal(col.prints, ids) : 0;
            bool armed = armedShard != null && ids.Count > 0 && armedShard == SelShardSet(ids) && Now - armedShardAt <= 6f;
            UIFactory.SetTextRaw(btnShardSelTxt, shardInFlight && shardPackId == null ? I18n.Tr("sharding...")
                : armed ? I18n.TrF("Sure? +{0} shards", total) : I18n.TrF("Shard selected ({0})", ids.Count));
            UIFactory.SetImageColor(btnShardSel, ids.Count > 0 && SessionReady && !shardInFlight && !discardInFlight ? C_DANGER : C_BTN);
        }

        /// <summary>quickPrintId: the pull-strip card a one-card shard is for
        /// (item 18), null for a pack or a selection.</summary>
        private static void SendShard(string id, string key, List<string> ids, string packId, string quickPrintId = null)
        {
            // F2: the request's generation. Its answer is checked against it
            // twice: by ApiClient before the balance is written into the
            // cache, and here before anything else is touched.
            int serial = shardFlight.Begin(Now, packId, quickPrintId);
            NativeUI.MarkDirty();
            int ep = uiEpoch;
            Plugin.Log.LogInfo($"[PC] shard {(quickPrintId != null ? "quick" : packId != null ? "pack" : "selection")}: {ids.Count} card(s)");
            ApiClient.PcDiscardBatch(id, key, ids, () => ep == uiEpoch && shardFlight.IsCurrent(serial), (ok, resp) =>
            {
                if (ep != uiEpoch) return;   // identity changed meanwhile (c4)
                string code = ok ? null : resp == "not ready" ? "not_ready" : ApiClient.PcErrorCode(resp);
                if (!shardFlight.Settle(serial, code))
                {
                    Plugin.Log.LogInfo($"[PC] shard: answer for request {serial} dropped (given up)");
                    return;
                }
                if (ok) FinishShard(id, resp, ids, packId, quickPrintId != null);
                else FailShard(id, resp, packId, quickPrintId != null);
                NativeUI.MarkDirty();
            });
        }

        /// <summary>A batch the server did: every print it lists leaves the
        /// collection and is stamped in the pack history with what it paid, and
        /// the toast names the total the server credited (the balance in the
        /// answer was written into the cache by ApiClient). An answer that does
        /// not list exactly what was sent reads both back.</summary>
        private static void FinishShard(string id, string resp, List<string> sent, string packId, bool quick = false)
        {
            var results = ApiClient.PcBatchResults(resp);
            int total = ApiClient.PcInt(ApiClient.PcTopLevel(resp, "shards_gained"));
            int n = ApiClient.PcInt(ApiClient.PcTopLevel(resp, "prints"));
            var col = ApiClient.CachedPcCollection;
            var done = new HashSet<string>(StringComparer.Ordinal);
            foreach (var r in results)
            {
                done.Add(r.Key);
                if (col != null) col.prints.RemoveAll(x => x.print_id == r.Key);
                HistoryMarkDiscarded(r.Key, r.Value);
            }
            selectedIds.RemoveAll(x => done.Contains(x));
            // a strip card's nonce was ended by PcShardFlight.Settle (a success)
            if (!quick) { if (packId == null) { shardKey = null; shardKeyFor = null; } }
            if (results.Count != sent.Count) { ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true); }
            if (n <= 0) n = results.Count;
            string msg = I18n.TrF("Sharded {0} cards for {1} shards", n, total);
            Plugin.Log.LogInfo($"[PC] shard done: {n} card(s), +{total} shards{(ApiClient.PcBool(ApiClient.PcTopLevel(resp, "replayed")) ? " (replayed)" : "")}");
            Say(msg, C_OK);
            try { CompetitiveUI.ShowNotification(msg, C_OK, 4f); } catch { }
        }

        private static readonly System.Text.RegularExpressions.Regex ShardUuid =
            new System.Text.RegularExpressions.Regex("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");

        /// <summary>The print ids a not_owned refusal names (its print_ids list).</summary>
        private static List<string> NamedPrintIds(string resp)
        {
            var list = new List<string>();
            int at = string.IsNullOrEmpty(resp) ? -1 : resp.IndexOf("\"print_ids\"", StringComparison.Ordinal);
            if (at < 0) return list;
            foreach (System.Text.RegularExpressions.Match m in ShardUuid.Matches(resp.Substring(at))) list.Add(m.Value.ToLowerInvariant());
            return list;
        }

        /// <summary>A batch the server refused: nothing was discarded and
        /// nothing credited (all or none). A lost answer or a rate limit keeps
        /// the key, so asking again is a replay; a refusal that says the local
        /// copy is wrong reads the collection and the balance again.</summary>
        private static void FailShard(string id, string resp, string packId, bool quick = false)
        {
            string code = ApiClient.PcErrorCode(resp);
            bool reread = false;
            if (quick)
            {
                // Item 18: a strip card's refusal. Nothing on screen changed
                // before the answer, so the card and the balance are still as
                // they were; PcQuickShardRules says whether they are read
                // back (every code but the rate limit and an unsent request:
                // a lost answer included, whose outcome is unknown) and
                // whether the card's key is kept for a replay.
                // ApiClient refused to build the request (its "not ready"),
                // which PcErrorCode would read as transport: nothing was sent.
                // The card's nonce was kept or dropped by PcShardFlight.Settle
                // (PcQuickShardRules.KeepKeyAfter) before this ran.
                if (resp == "not ready") code = "not_ready";
                if (code == "not_owned") foreach (var g in NamedPrintIds(resp)) { shardGone.Add(g); selectedIds.Remove(g); }
                string say;
                if (code == "not_owned") say = I18n.Tr("One of those cards is no longer in your collection - nothing was sharded; your binder has been refreshed");
                else if (code == "key_reused") say = I18n.Tr("That shard was already done with other cards - your binder has been refreshed");
                else if (code == "shard_batch_unavailable" || (code == "http" && ApiClient.PcHttpCode(resp) == 404))
                    say = I18n.Tr("Shard pack is not available on this server yet - discard one card at a time for now");
                else say = ReasonText(code);
                Say(say, C_WARN);
                Plugin.Log.LogInfo($"[PC] quick shard refused: {code}");
                if (PcQuickShardRules.ReadBackAfter(code) && id != null) { ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true); }
                return;
            }
            switch (code)
            {
                case "not_owned":
                    foreach (var g in NamedPrintIds(resp)) { shardGone.Add(g); selectedIds.Remove(g); }
                    Say(I18n.Tr("One of those cards is no longer in your collection - nothing was sharded; your binder has been refreshed"), C_WARN);
                    reread = true;
                    break;
                case "key_reused":
                    if (packId != null) packShardBurned.Add(packId);
                    else { shardKey = null; shardKeyFor = null; }
                    Say(I18n.Tr("That shard was already done with other cards - your binder has been refreshed"), C_WARN);
                    reread = true;
                    break;
                case "too_many":
                    Say(I18n.TrF("You can shard up to {0} cards at once", ApiClient.PC_DISCARD_BATCH_CAP), C_WARN);
                    break;
                case "shard_batch_unavailable":
                    Say(I18n.Tr("Shard pack is not available on this server yet - discard one card at a time for now"), C_WARN);
                    break;
                default:
                    // An api without the route answers FastAPI's plain 404.
                    if (code == "http" && ApiClient.PcHttpCode(resp) == 404)
                    {
                        Say(I18n.Tr("Shard pack is not available on this server yet - discard one card at a time for now"), C_WARN);
                        break;
                    }
                    Say(ReasonText(code), C_WARN);
                    reread = code != "transport" && code != "rate_limited" && code != "session_required";
                    break;
            }
            Plugin.Log.LogInfo($"[PC] shard refused: {code}");
            if (reread && id != null) { ApiClient.FetchPcCollection(id, true); ApiClient.FetchPcMe(id, true); }
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
            // The Top Card thumbnail is a picture of a DIFFERENT card prefab
            // per print, so a lever that seeds one card everywhere can only
            // ever measure that one card's art and that one card's name
            // plate. These three are a one-word name, a two-word name and the
            // card the first witness used, so a measurement can be repeated
            // across names rather than asserted to generalise from one.
            string[] tops = { "Poison", "Wind Up", "Bombs Away" };
            // "card" opens the first print; "card:N" opens print N, so the
            // witness can measure a second card's art without a second build.
            const string CARD_AT = "card:";
            bool cardMode = mode == "card" || mode.StartsWith(CARD_AT);
            int cardIndex = 0;
            if (cardMode && mode.Length > CARD_AT.Length)
                int.TryParse(mode.Substring(CARD_AT.Length), out cardIndex);
            var a = new ApiClient.PcPackAnswer { pack_id = "dev", status = "done", source = "bought", pay = "gold", price = 100, opened_at = "2026-09-11T00:00:00" };
            for (int i = 0; i < 5; i++)
                a.prints.Add(new ApiClient.PcPrint
                {
                    print_id = "dev" + i, card_id = "card" + i, subject_player_id = "p" + i, subject_name = names[i],
                    edition_id = "1", minted_at = "2026-09-11T00:00:00", rarity = rar[i], foil = i == 1, signed = i == 0,
                    pool_rank = i == 0 ? 1 : i * 9, rating = 1850 - i * 120, peak_rating = 1900 - i * 100, board_rank = i == 0 ? 1 : i * 9,
                    series_wins = 60 - i * 8, series_losses = 12 + i * 3, top_card = tops[i % tops.Length], title = i == 0 ? "Grandmaster" : "", rank_name = "Diamond", source = "bought", slot = i,
                    dup_at_pull = i == 0 ? 0 : (i == 3 ? 2 : -1),   // one NEW, one DUPLICATE +2, the rest silent
                    discarded = i == 4, discard_shards = i == 4 ? 3 : -1,   // one DISCARDED stamp, for the screenshot
                });
            lastPack = a;
            HistoryInsertHead(a);
            historyLoaded = true; historyExhausted = true;   // the pager shows this one; no server page behind it
            view = mode == "binder" ? View.Binder : (mode == "info" ? View.Info : View.Open);
            if (mode == "binder" || mode == "binder-faces" || cardMode)
            {
                // A synthetic binder (this seat's account is a service account:
                // 403 on the collection): ten prints, two of them copies of one
                // card, so the Dupes button shows too. "binder-faces" also puts
                // a synthetic 375x525 face in the cache for every print — the
                // exact sprite size a fetched face has, so the action row is
                // verified under the same layout pressure the live binder has.
                var col = new ApiClient.PcCollection { owner_steam_id = "dev", owner_name = "Sid", is_public = true, subject_standings = true };
                string[] rar2 = { "legendary", "epic", "rare", "uncommon", "common", "common", "rare", "uncommon", "common", "common" };
                // Item 20's witness set, per SUBJECT: the front group, both
                // sides of the 100/101 boundary, a rank-5 subject who has gone
                // quiet (highest rating of the ten, and still at the back), and
                // two unrated subjects behind every rated one. subject_rank 0
                // is "off the board today".
                int[] subjRank = { 1, 2, 100, 101, 5, 0, 0, 0, 0 };
                bool[] subjQuiet = { false, false, false, false, true, false, false, false, false };
                bool[] subjRated = { true, true, true, true, true, true, true, false, false };
                float[] subjRating = { 1900f, 1860f, 1500f, 1820f, 2400f, 1700f, 1300f, 0f, 0f };
                for (int i = 0; i < 10; i++)
                {
                    int subj = i == 9 ? 8 : i;   // the last two are the same card
                    col.prints.Add(new ApiClient.PcPrint
                    {
                        print_id = "devb" + i, card_id = "cardb" + subj, subject_player_id = "pb" + subj, subject_name = i == 0 ? "Sid" : "Player " + subj,
                        edition_id = "1", minted_at = "2026-09-12T00:00:00", rarity = rar2[i], foil = i == 2, signed = i == 0,
                        pool_rank = i + 1, rating = 1900 - i * 40, peak_rating = 1950 - i * 40, board_rank = i < 5 ? i + 1 : 0,
                        series_wins = 40 - i * 3, series_losses = 10 + i, top_card = tops[i % tops.Length], title = i == 1 ? "Champion" : "", rank_name = "Advanced I",
                        source = "bought", slot = i % 5, dup_at_pull = -1,
                        subject_board_rank = subjRank[subj], subject_inactive = subjQuiet[subj],
                        subject_rated = subjRated[subj], subject_rating = subjRating[subj],
                        face_rev = (mode == "binder-faces" || cardMode) ? "dev" : null,
                    });
                }
                if (mode == "binder-faces" || cardMode)
                    for (int i = 0; i < col.prints.Count; i++)
                        PlayerCardFaces.DevPut(col.prints[i].print_id, "dev", "en", "tile", DevSprite(FrameColor(col.prints[i].rarity, false)), 375L * 525L * 4L);
                col.count = col.prints.Count;
                ApiClient.DevSetCollection(col);
                view = View.Binder;
                // "card" also opens the full-size card view on the first
                // print, and "card:N" on print N — the prints carry different
                // top cards, so N is how a second card's art gets measured.
                // The Top card overlay is ~94/1050 of the face, so
                // on a binder tile it is ~33 px tall and on this popup it is
                // ~93 px: the popup is the only surface on this seat where
                // the corner marks can be measured against the box edges to
                // the pixel. Needs a face at the "card" size too — without
                // one ShowCard asks the server, which answers 403 for this
                // service account and falls back to the text view.
                if (cardMode && col.prints.Count > 0)
                {
                    int idx = Mathf.Clamp(cardIndex, 0, col.prints.Count - 1);
                    PlayerCardFaces.DevPut(col.prints[idx].print_id, "dev", "en", "card",
                                           DevSprite(FrameColor(col.prints[idx].rarity, false)), 750L * 1050L * 4L);
                    ShowCard(new Tile { print = col.prints[idx] });
                    Plugin.Log.LogInfo("[PC] dev card view: print " + idx + " top_card='" + col.prints[idx].top_card + "'");
                }
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
        /// synthetic click never reaches the overlay (#420). The full list of
        /// what it takes, each with nothing seeded:
        ///   "daily"         the daily button (claim, or open the claimed pack);
        ///   "open"          the first waiting pack;
        ///   "card:N"        the Nth binder tile's card view;
        ///   "view:open|binder|info|trades"  the view switch (any other value
        ///                   selects the Open view);
        ///   "setting:collection_public|announce|trades_open"  that server
        ///                   row's toggle (ToggleSetting); any other key is
        ///                   logged and ignored;
        ///   "shardpack"     the Shard pack button on the pack on show (board
        ///                   row 25: the first press arms and names the total,
        ///                   a second press inside six seconds sends);
        ///   "killhost"      the persistent host destroyed and respawned (board
        ///                   row 24, round 2);
        ///   "trade:..."     the card-trading verbs, handed to DevTrade (listed
        ///                   there).
        /// A "/n" suffix is dropped before matching, so a repeated press can
        /// carry a distinct value. Anything else is logged as unknown.</summary>
        internal static void DevAct(string what)
        {
            what = what ?? "";
            // The lever fires once per distinct value, so a repeated press (the
            // second click that confirms an armed Accept) carries a "/n" suffix.
            int slash = what.IndexOf('/');
            if (slash >= 0) what = what.Substring(0, slash);
            if (what.StartsWith("trade:")) { DevTrade(what.Substring(6)); return; }
            if (what.StartsWith("setting:"))
            {
                string key = what.Substring(8);
                if (key == "collection_public" || key == "announce" || key == "trades_open") { Plugin.Log.LogInfo("[PC] act: setting " + key); ToggleSetting(key); }
                else Plugin.Log.LogInfo("[PC] act: setting - unknown key");
                return;
            }
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
            if (what == "shardpack") { Plugin.Log.LogInfo("[PC] act: shardpack"); OnShardPackClick(); return; }
            if (what == "killhost")
            {
                // Board row 24, round 2 (L4): destroy the persistent host the
                // way a scene teardown does, so the coroutines it runs (a
                // Settings card fetch among them) stop without their callbacks
                // and its OnDestroy respawns it.
                Plugin.Log.LogInfo("[PC] act: killhost (settings card in flight: " + settingsCardInFlight + ", serial " + settingsCardSerial + ")");
                var host = Plugin.Instance;
                if (host != null) UnityEngine.Object.Destroy(host.gameObject);
                return;
            }
            if (what.StartsWith("view:"))
            {
                string v = what.Substring(5);
                view = v == "binder" ? View.Binder : (v == "info" ? View.Info : (v == "trades" ? View.Trades : View.Open));
                Plugin.Log.LogInfo("[PC] act: view " + view);
                NativeUI.MarkDirty();
                return;
            }
            Plugin.Log.LogInfo("[PC] act: unknown '" + what + "'");
        }

        /// <summary>The trade half of the act lever (card trading witness):
        /// poll, new, pick:STEAM, offer:STEAM (the open card view's print, then
        /// that player), give:N / get:N (the Nth card on the picker page), send,
        /// back, accept:N / decline:N (the Nth Incoming row), cancel:N (the Nth
        /// Sent row). Each presses the same handler the real control does.</summary>
        private static void DevTrade(string w)
        {
            var id = LocalId();
            string[] a = w.Split(':');
            string verb = a[0];
            int n = -1;
            if (a.Length > 1 && verb != "pick" && verb != "offer" && !int.TryParse(a[1], out n)) n = -1;   // pick/offer carry a Steam id, not an index
            switch (verb)
            {
                case "poll": tradeSummaryAt = 0f; if (id != null) ReadTrades(id, true); break;
                case "new": StartTradeSearch(null); break;
                case "pick": if (a.Length > 1) StartCompose(a[1], null, null); break;
                case "offer":
                    {
                        // the Offer button showing on a card view (face or text), then that player
                        if (offerBtnGO == null || offerBtnPid == null || a.Length < 2) { Plugin.Log.LogInfo("[PC] act: trade offer - no Offer button showing"); return; }
                        string pid = offerBtnPid;
                        try { offerBtnHide?.Invoke(); } catch { }
                        StartCompose(a[1], null, pid);
                        break;
                    }
                case "give": DevToggle(givePickTiles, n, true); break;
                case "get": DevToggle(getPickTiles, n, false); break;
                case "send": SendProposal(); break;
                case "back": OnComposeBack(); break;
                case "accept": if (n >= 0 && n < inRows.Count && inRows[n].trade != null) OnAcceptClick(inRows[n]); break;
                case "decline": if (n >= 0 && n < inRows.Count && inRows[n].trade != null) OnCloseClick(inRows[n], "decline"); break;
                case "cancel": if (n >= 0 && n < sentRows.Count && sentRows[n].trade != null) OnCloseClick(sentRows[n], "cancel"); break;
                default: Plugin.Log.LogInfo("[PC] act: trade - unknown verb"); return;
            }
            Plugin.Log.LogInfo("[PC] act: trade " + verb + (n >= 0 ? " " + n : ""));
            NativeUI.MarkDirty();
        }

        private static void DevToggle(Tile[] tiles, int n, bool mine)
        {
            if (tiles == null || n < 0 || n >= tiles.Length || tiles[n] == null || tiles[n].print == null)
            { Plugin.Log.LogInfo("[PC] act: trade - no such picker card"); return; }
            ToggleComposeCard(tiles[n], mine);
        }

        // -- Card trading (v1.41.0, design V8 section 6) ----------------------
        // The Trades view (the fourth view), the proposal flow, the inbox, the
        // card view's Offer in a trade, the binder badges, the polling and the
        // discovery gate. The server is the only authority (6.6): every list,
        // badge and count here is drawn from its answers and gates no write -
        // a click reaches the server, whose refusal is shown and then re-read.
        // Sentinel lines ([PC-TRADE-SENTINEL]) carry counts and codes only,
        // never a Steam id, a trade id or a name.

        private const float MINI_W = 90f, MINI_H = 126f;   // a mini face: 5:7, like the tile
        private const int SIDE_TILES = 3;                  // faces drawn per side of a row; more read "+n"
        private const int PICK_PAGE = 10;                  // faces per compose picker page
        private const float NOTIFY_WAIT_S = 30f;           // a new-proposal toast waits this long for its name
        private static readonly Color C_PICKED = new Color(0.30f, 0.90f, 1.00f, 1f);

        private class TradeRow
        {
            public GameObject root, btnA, btnB;
            public object txtWho, txtWhen, txtNote, btnATxt, txtGiveMore, txtGetMore;
            public Tile[] give, get;
            public ApiClient.PcTrade trade;   // the row's CURRENT binding - handlers read this, never a captured trade (#265)
        }

        private static GameObject tradesRoot, tradeListsBox, composeBox, btnNewTrade, inBox, sentBox, recentBox;
        private static object txtTradesHdr, txtInHdr, txtSentHdr, txtRecentHdr;
        private static readonly List<TradeRow> inRows = new List<TradeRow>(), sentRows = new List<TradeRow>();
        private static readonly List<object> recentTxts = new List<object>();
        private static bool tradesBuilt;
        private static PcTradeRules.Discovery tradeDiscovery = PcTradeRules.Discovery.Unknown;
        private static float tradeSummaryAt, tradesFullAt;
        private static float processedSummaryAt = -1f, processedFullAt = -1f;
        private static List<string> lastReceivedOpen;   // null until the session's first summary: that one announces nothing
        private static readonly List<string> pendingNotify = new List<string>();
        private static float pendingNotifyAt;
        private static HashSet<string> offeredIds = new HashSet<string>(StringComparer.Ordinal);
        private static string armedTradeId; private static float armedTradeAt;
        private static bool tradeActInFlight; private static float tradeActAt;
        private static readonly Dictionary<string, string> actNonces = new Dictionary<string, string>();
        private static bool tradeSelfChecked;
        // the Trades view's entry edge (C12, TC-L2): every entry forces the full read
        private static readonly PcTradeRules.TradesEntryEdge tradesEdge = new PcTradeRules.TradesEntryEdge();
        private static GameObject offerBtnGO; private static string offerBtnPid; private static Action offerBtnHide;   // the card view's Offer button
        private static string tradePanelSig, tradeBadgeSig, tradesLabelPainted, collectionLabelPainted;
        private static object collectionLabelObj;
        // compose (V8 6.2)
        private static bool composing, composeTheirsLoading;
        private static int composeSeq, giveCardPage, getCardPage;
        private static string composeTo, composeToName, composeNonce, composeNonceKey, composeTheirsError;
        private static ApiClient.PcCollection composeTheirs;
        private static readonly List<string> composeGive = new List<string>(), composeGet = new List<string>();
        private static readonly List<ApiClient.PcPrint> theirPickList = new List<ApiClient.PcPrint>(), ownPickList = new List<ApiClient.PcPrint>();
        private static object txtComposeHdr, txtComposeWarn, txtComposeExpiry, txtGetPickHdr, txtGivePickHdr,
                              txtTheirNote, txtOwnNote, txtGetPage, txtGivePage, composeGiveMore, composeGetMore;
        private static GameObject btnSendProposal;
        private static Tile[] giveSelTiles, getSelTiles, getPickTiles, givePickTiles;

        /// <summary>An identity edge (or a consent revoke) drops every trade
        /// state this client holds: the lists were the previous account's.</summary>
        private static void ResetTrades()
        {
            tradeDiscovery = PcTradeRules.Discovery.Unknown;
            tradeSummaryAt = 0f; tradesFullAt = 0f;
            processedSummaryAt = -1f; processedFullAt = -1f;
            lastReceivedOpen = null; pendingNotify.Clear();
            offeredIds = new HashSet<string>(StringComparer.Ordinal);
            armedTradeId = null; tradeActInFlight = false; actNonces.Clear();
            tradesEdge.Reset();
            offerBtnGO = null; offerBtnPid = null; offerBtnHide = null;
            tradePanelSig = null; tradeBadgeSig = null; tradesLabelPainted = null; collectionLabelPainted = null;
            EndCompose();
        }

        // -- polling (V8 6.4) and discovery (6.9) ------------------------------

        /// <summary>Called from MaybeTick every two seconds while the overlay is
        /// up, BEFORE its early return for other tabs.</summary>
        private static void TickTrades(string id, bool onTab)
        {
            if (!tradeSelfChecked)
            {
                // the startup banner: the digest rule run on the server's own vectors
                tradeSelfChecked = true;
                string got = ""; bool pass = false;
                try { pass = PcTradeRules.DigestSelfCheck(out got); } catch (Exception ex) { got = ex.GetType().Name; }
                Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] digest self-check " + (pass ? "PASS" : "FAIL") + " got=" + got);
            }
            ProcessTradeAnswers();
            // entering = the Trades view became visible (the tab AND the view):
            // that read is forced, and owed until it is issued. The edge is
            // re-armed by a frame off the view (MaybeTick) and by the overlay
            // closing (OnOverlayClosed); the five-second gap stays behind them
            // as a secondary guard (TC-L2).
            bool onTrades = onTab && view == View.Trades;
            float sinceTick = Now - tradesEdge.LastTickAt;
            bool owed = tradesEdge.Tick(onTrades, Now);
            if (armedTradeId != null && Now - armedTradeAt > PcTradeRules.ArmWindowSeconds) { armedTradeId = null; NativeUI.MarkDirty(); }
            if (tradeActInFlight && Now - tradeActAt > 25f) { tradeActInFlight = false; NativeUI.MarkDirty(); }
            if (pendingNotify.Count > 0 && Now - pendingNotifyAt > NOTIFY_WAIT_S) NotifyNew(null);
            if (!SessionReady) return;
            if (Now >= tradeSummaryAt)
            {
                tradeSummaryAt = Now + PcTradeRules.NextSummaryDelay(tradeDiscovery);
                int ep = uiEpoch;
                ApiClient.PcTradeSummary(id, false, (ok, resp) => { if (ep == uiEpoch) TradeReadLanded("summary", ok, resp); });
            }
            if (PcTradeRules.FullReadDue(onTrades, PcTradeRules.ReadsAllowed(tradeDiscovery), owed, Now, tradesFullAt))
            {
                if (owed) Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] trades entered forced_read=1 since_tick_ms=" + Mathf.RoundToInt(sinceTick * 1000f));
                ReadTrades(id, owed);
                tradesEdge.ReadIssued();
            }
        }

        private static void ReadTrades(string id, bool force)
        {
            if (id == null) return;
            tradesFullAt = Now + PcTradeRules.FullPollSeconds;
            int ep = uiEpoch;
            ApiClient.PcTrades(id, force, (ok, resp) => { if (ep == uiEpoch) TradeReadLanded("full", ok, resp); });
        }

        /// <summary>A failed read classifies the discovery state (404 absent,
        /// 503 trading_unavailable unavailable, anything else keeps it); a read
        /// that landed is acted on by ProcessTradeAnswers. An answer the trades
        /// fence kept out (ApiClient.PcStaleOrder) is ignored like a stale
        /// identity: a newer answer is already held (TC-L5).</summary>
        private static void TradeReadLanded(string kind, bool ok, string resp)
        {
            if (!ok && (resp == null || resp == "in-flight" || resp == "no-id" || resp == "stale-identity" || resp == ApiClient.PcStaleOrder)) return;
            if (!ok)
            {
                string code = ApiClient.PcTradeErrorCode(resp);
                int http = ApiClient.PcHttpCode(resp);
                var before = tradeDiscovery;
                tradeDiscovery = PcTradeRules.Classify(tradeDiscovery, false, false, http, code);
                Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] " + kind + " ok=0 http=" + http + " code=" + (code ?? "-") + " discovery=" + tradeDiscovery);
                if (tradeDiscovery != before)
                {
                    tradeSummaryAt = Now + PcTradeRules.NextSummaryDelay(tradeDiscovery);
                    NativeUI.MarkDirty();
                }
                if (kind == "full" && pendingNotify.Count > 0) NotifyNew(null);   // the read failed: no name (F14)
                return;
            }
            ProcessTradeAnswers();
        }

        /// <summary>Acts once on each answer that landed (the cache stamps say
        /// which). The summary sets the discovery state and finds new incoming
        /// ids against the last summary; the full read (which carries every
        /// summary field too) names them and rebuilds the set of prints held
        /// by the player's own open offers.</summary>
        private static void ProcessTradeAnswers()
        {
            var s = ApiClient.CachedPcTradeSummary;
            if (s != null && ApiClient.PcTradeSummaryFetchedAt != processedSummaryAt)
            {
                processedSummaryAt = ApiClient.PcTradeSummaryFetchedAt;
                tradeDiscovery = PcTradeRules.Classify(tradeDiscovery, true, s.enabled, 200, null);
                var fresh = PcTradeRules.NewIds(lastReceivedOpen, s.receivedOpen);
                lastReceivedOpen = new List<string>(s.receivedOpen);
                if (fresh.Count > 0)
                {
                    if (pendingNotify.Count == 0) pendingNotifyAt = Now;
                    foreach (var f in fresh) if (!pendingNotify.Contains(f)) pendingNotify.Add(f);
                }
                bool fromFull = ApiClient.CachedPcTrades != null && ApiClient.PcTradesFetchedAt == ApiClient.PcTradeSummaryFetchedAt;
                Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] summary ok=1 enabled=" + (s.enabled ? 1 : 0) + " trades_open=" + (s.tradesOpen ? 1 : 0)
                    + " received=" + s.receivedOpen.Count + " sent=" + s.sentOpen.Count + " new=" + fresh.Count
                    + " discovery=" + tradeDiscovery + " tab=" + (PcTradeRules.TabShown(tradeDiscovery) ? 1 : 0) + " from_full=" + (fromFull ? 1 : 0));
                // a new proposal forces one full read for its name; a sent set the
                // cached full read does not match forces one for the badges
                if (!fromFull && PcTradeRules.ReadsAllowed(tradeDiscovery) && (fresh.Count > 0 || !SentOpenMatches(s)))
                    ReadTrades(LocalId(), true);
                NativeUI.MarkDirty();
            }
            var full = ApiClient.CachedPcTrades;
            if (full != null && ApiClient.PcTradesFetchedAt != processedFullAt)
            {
                processedFullAt = ApiClient.PcTradesFetchedAt;
                var refs = new List<PcTradeRules.TradeRef>();
                foreach (var t in full.offers) refs.Add(new PcTradeRules.TradeRef(t.role, t.state, PrintIdsOf(t.give)));
                offeredIds = PcTradeRules.OfferedPrintIds(refs);
                Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] full ok=1 offers=" + full.offers.Count + " recent=" + full.recent.Count
                    + " offered_prints=" + offeredIds.Count + " side_max=" + full.bounds.prints_per_side_max + " ttl_h=" + full.bounds.ttl_hours
                    + " today=" + full.bounds.executed_today + "/" + full.bounds.executed_per_day);
                if (pendingNotify.Count > 0) NotifyNew(full);
                NativeUI.MarkDirty();
            }
        }

        private static List<string> PrintIdsOf(List<ApiClient.PcPrint> prints)
        {
            var outp = new List<string>();
            if (prints != null) foreach (var p in prints) if (p != null && !string.IsNullOrEmpty(p.print_id)) outp.Add(p.print_id);
            return outp;
        }

        /// <summary>The summary's sent_open (TRADE ids) against the cached full
        /// read's own sent proposals: a difference means the badges and the
        /// card view's offered set are stale.</summary>
        private static bool SentOpenMatches(ApiClient.PcTradeSummaryAnswer s)
        {
            var full = ApiClient.CachedPcTrades;
            var have = new HashSet<string>(StringComparer.Ordinal);
            if (full != null)
                foreach (var t in full.offers)
                    if (t.role == "sent" && t.state == "proposed" && !string.IsNullOrEmpty(t.trade_id)) have.Add(t.trade_id);
            if (have.Count != s.sentOpen.Count) return false;
            foreach (var tid in s.sentOpen) if (!have.Contains(tid)) return false;
            return true;
        }

        /// <summary>One toast for the new proposals (V8 6.4). It names the
        /// proposer from the full read's server-derived counterparty_name when
        /// every new proposal is from one player; otherwise, or when the read
        /// failed or never came, the separate unnamed line - never an empty
        /// {0} (F14). New ids the read no longer lists as open are dropped.</summary>
        private static void NotifyNew(ApiClient.PcTradeFull full)
        {
            var ids = new List<string>(pendingNotify);
            pendingNotify.Clear();
            string name = null; bool oneName = true; int found = 0;
            if (full != null)
            {
                foreach (var tid in ids)
                {
                    var t = full.offers.Find(x => x.trade_id == tid);
                    if (t == null) continue;
                    found++;
                    string n = TradeName(t);
                    if (n.Length == 0) oneName = false;
                    else if (name == null) name = n;
                    else if (name != n) oneName = false;
                }
                if (found == 0) { Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] notify new=0 dropped=" + ids.Count); return; }
            }
            bool named = full != null && name != null && oneName;
            string msg = named ? I18n.TrF("New trade proposal from {0}", name) : I18n.Tr("New trade proposal");
            try { CompetitiveUI.ShowNotification(msg, C_GOLD, 5f); } catch { }
            Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] notify new=" + (full != null ? found : ids.Count) + " named=" + (named ? 1 : 0));
            NativeUI.MarkDirty();
        }

        private static string TradeName(ApiClient.PcTrade t)
        {
            string n = t != null ? (t.counterparty_name ?? "") : "";
            return n.Length > 24 ? n.Substring(0, 24) : n;
        }

        private static string TradeState()
        {
            switch (tradeDiscovery)
            {
                case PcTradeRules.Discovery.Enabled: return "";
                case PcTradeRules.Discovery.Paused: return I18n.Tr("Trading is paused");
                case PcTradeRules.Discovery.Unknown: return I18n.Tr("Loading...");
                default: return I18n.Tr("Trading is not available yet");
            }
        }

        /// <summary>The summary says the player's OWN Card trading switch is
        /// off: a proposal would be refused (trading_closed), so none is
        /// offered. Display only - the server decides.</summary>
        private static bool OwnTradingClosed()
        {
            var s = ApiClient.CachedPcTradeSummary;
            return s != null && !s.tradesOpen;
        }

        /// <summary>Open incoming proposals: the Trades button's and the
        /// Collection sub-tab's count ("raises the tab badge", V8 6.4).</summary>
        private static int IncomingOpenCount()
        {
            var s = ApiClient.CachedPcTradeSummary;
            return s != null && PcTradeRules.ReadsAllowed(tradeDiscovery) ? s.receivedOpen.Count : 0;
        }

        private static void PaintTradesLabel()
        {
            if (viewTxts[3] == null) return;
            int n = IncomingOpenCount();
            string label = n > 0 ? I18n.Tr("Trades") + " (" + n + ")" : I18n.Tr("Trades");
            if (label == tradesLabelPainted) return;
            tradesLabelPainted = label;
            UIFactory.SetTextRaw(viewTxts[3], label);
        }

        /// <summary>NativeUI's sub-tab bar calls this on each repaint with the
        /// Collection sub-tab's label: "Collection (n)" while n proposals wait.</summary>
        internal static void PaintCollectionTabLabel(object txt)
        {
            if (txt == null) return;
            int n = IncomingOpenCount();
            string label = n > 0 ? I18n.Tr("Collection") + " (" + n + ")" : I18n.Tr("Collection");
            if (txt == collectionLabelObj && label == collectionLabelPainted) return;
            collectionLabelObj = txt; collectionLabelPainted = label;
            UIFactory.SetTextRaw(txt, label);
        }

        private static void OnTradesOpenToggled(string id)
        {
            tradeSummaryAt = 0f;
            if (PcTradeRules.ReadsAllowed(tradeDiscovery)) ReadTrades(id, true);
        }

        // -- the view (V8 6.1, 6.3) --------------------------------------------

        /// <summary>The fourth view's root and header. The lists and the compose
        /// screen are built on its first paint (EnsureTradesBuilt): a player who
        /// never opens Trades never pays for them.</summary>
        private static void BuildTradesView(Transform parent)
        {
            tradesBuilt = false;
            inRows.Clear(); sentRows.Clear(); recentTxts.Clear();
            giveSelTiles = null; getSelTiles = null; getPickTiles = null; givePickTiles = null;
            tradePanelSig = null;
            tradesRoot = new GameObject("PcTrades");
            tradesRoot.transform.SetParent(parent, false);
            tradesRoot.AddComponent<RectTransform>();
            UIFactory.AddVLG(tradesRoot, spacing: 6);
            UIFactory.AddLE(tradesRoot, flexH: 1);
            var hdr = new GameObject("PcTHdr"); hdr.transform.SetParent(tradesRoot.transform, false); hdr.AddComponent<RectTransform>();
            UIFactory.AddHLG(hdr, spacing: 10, forceExpandH: true); UIFactory.AddLE(hdr, prefH: 28, flexH: 0);
            txtTradesHdr = UIFactory.CreateText("PcTHdrTxt", hdr.transform, "", 15f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(760, 26));
            UIFactory.SetOverflowMode(txtTradesHdr, 2); UIFactory.SetWordWrap(txtTradesHdr, false);
            var sp = new GameObject("PcTSp"); sp.transform.SetParent(hdr.transform, false); sp.AddComponent<RectTransform>(); UIFactory.AddLE(sp, flexW: 1);
            btnNewTrade = UIFactory.CreateButton("PcTNew", hdr.transform, "New trade", 14f, C_WHITE, C_BUY, () => StartTradeSearch(null), sizeDelta: new Vector2(180, 26));
            btnNewTrade.SetActive(false);
            tradesRoot.SetActive(false);
        }

        private static void EnsureTradesBuilt()
        {
            if (tradesBuilt || tradesRoot == null) return;
            tradesBuilt = true;
            // The three lists: ONE scroll with three headed sections (C4's
            // choice), so a long Incoming never hides Sent behind a second bar.
            var sv = UIFactory.CreateScrollView("PcTSV", tradesRoot.transform, spacing: 6);
            UIFactory.AddLE(sv.scrollGO, flexH: 1);
            tradeListsBox = sv.scrollGO;
            var c = sv.content.transform;
            inBox = ListSection(c, "PcTIn", out txtInHdr);
            sentBox = ListSection(c, "PcTSent", out txtSentHdr);
            recentBox = ListSection(c, "PcTRec", out txtRecentHdr);
            BuildCompose();
        }

        private static GameObject ListSection(Transform parent, string name, out object hdr)
        {
            var box = UIFactory.CreatePanel(name, parent, C_PANEL);
            UIFactory.AddVLG(box, spacing: 4, padL: 10, padR: 10, padT: 6, padB: 6);
            UIFactory.AddLE(box, flexH: 0);
            hdr = UIFactory.CreateText(name + "H", box.transform, "", 16f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(900, 24));
            return box;
        }

        private static GameObject Column(Transform parent, string name, float w)
        {
            var go = new GameObject(name); go.transform.SetParent(parent, false); go.AddComponent<RectTransform>();
            UIFactory.AddVLG(go, spacing: 4);
            UIFactory.AddLE(go, prefW: w, minW: w, flexW: 0);
            return go;
        }

        /// <summary>A labelled strip of mini faces: "You give" / "You get".</summary>
        private static Tile[] SideStrip(Transform parent, string name, string label, out object more, int count, Action<Tile> click, bool withBadge)
        {
            var col = Column(parent, name, count * (MINI_W + 4f) + 34f);
            UIFactory.CreateText(name + "_h", col.transform, label, 13f, C_SUB, UIFactory.AlignMidLeft, sizeDelta: new Vector2(240, 18));
            var strip = new GameObject(name + "_s"); strip.transform.SetParent(col.transform, false); strip.AddComponent<RectTransform>();
            UIFactory.AddHLG(strip, spacing: 4, forceExpandH: false);
            UIFactory.AddLE(strip, prefH: MINI_H, minH: MINI_H, flexH: 0);
            var tiles = new Tile[count];
            for (int i = 0; i < count; i++) tiles[i] = CreateMiniTile(strip.transform, name + i, click, withBadge);
            more = UIFactory.CreateText(name + "_m", strip.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(30, 20));
            return tiles;
        }

        /// <summary>A small card: the server face through the existing face
        /// cache (PlayerCardFaces, the "tile" size scaled down), or the name and
        /// the rarity line when no face could be had. A click opens the card
        /// view, or runs `click` (the compose pickers).</summary>
        private static Tile CreateMiniTile(Transform parent, string name, Action<Tile> click, bool withBadge)
        {
            var t = new Tile { mini = true, click = click };
            t.root = UIFactory.CreatePanel(name, parent, FrameColor("common", false));
            UIFactory.AddVLG(t.root, spacing: 0, padL: 2, padR: 2, padT: 2, padB: 2);
            UIFactory.AddLE(t.root, prefW: MINI_W, minW: MINI_W, prefH: MINI_H, minH: MINI_H, flexW: 0, flexH: 0);
            t.face = UIFactory.CreatePanel(name + "_f", t.root.transform, C_CARD);
            UIFactory.AddLE(t.face, prefW: 0, prefH: 0, flexH: 1, flexW: 1);
            PlayerCardFaces.SetFace(t.face, null);
            t.face.SetActive(false);
            t.textBlock = UIFactory.CreatePanel(name + "_tb", t.root.transform, C_CARD);
            UIFactory.AddVLG(t.textBlock, spacing: 2, padL: 4, padR: 4, padT: 4, padB: 4);
            UIFactory.AddLE(t.textBlock, prefW: 0, prefH: 0, flexH: 1, flexW: 1);
            t.txtName = UIFactory.CreateText(name + "_n", t.textBlock.transform, "", 12f, C_WHITE, UIFactory.AlignTopLeft, sizeDelta: new Vector2(MINI_W - 12f, 48));
            t.txtMark = UIFactory.CreateText(name + "_m", t.textBlock.transform, "", 12f, C_GOLD, UIFactory.AlignTopLeft, sizeDelta: new Vector2(MINI_W - 12f, 48));
            foreach (var o in new[] { t.txtName, t.txtMark }) { UIFactory.SetOverflowMode(o, 2); UIFactory.SetWordWrap(o, true); }
            var tile = t;
            foreach (var go in new[] { t.face, t.textBlock })
            {
                var ch = go.AddComponent<ClickHandler>();
                ch.onClick = () => OnTileClick(tile);
            }
            if (withBadge) AddBadge(t, name + "_bd", MINI_W - 6f, 12f, 4f);
            t.root.SetActive(false);
            return t;
        }

        /// <summary>The badge strip along the bottom of a tile, `bottom` above its
        /// lower edge (on a binder tile, just above the action row), clear of the
        /// name at the top: out of the tile's layout (ignoreLayout) and
        /// click-through, hidden until painted.</summary>
        private static void AddBadge(Tile t, string name, float w, float fontSize, float bottom)
        {
            var go = UIFactory.CreatePanel(name, t.root.transform, new Color(0f, 0f, 0f, 0.80f));
            try
            {
                var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance;
                if (UIFactory.tLE != null)
                {
                    var le = go.AddComponent(UIFactory.tLE);
                    UIFactory.tLE.GetProperty("ignoreLayout", bf)?.SetValue(le, true);
                }
                var img = UIFactory.tImage != null ? go.GetComponent(UIFactory.tImage) : null;
                if (img != null) UIFactory.tImage.GetProperty("raycastTarget", bf)?.SetValue(img, false);
            }
            catch { }
            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0.5f, 0f); rt.anchorMax = new Vector2(0.5f, 0f); rt.pivot = new Vector2(0.5f, 0f);
            rt.anchoredPosition = new Vector2(0f, bottom); rt.sizeDelta = new Vector2(w, fontSize + 8f);
            t.badge = UIFactory.CreateText(name + "_t", go.transform, "", fontSize, C_WARN, UIFactory.AlignMidCenter, sizeDelta: Vector2.zero);
            var tc = t.badge as Component;
            var trt = tc != null ? tc.GetComponent<RectTransform>() : null;
            if (trt != null) { trt.anchorMin = Vector2.zero; trt.anchorMax = Vector2.one; trt.offsetMin = Vector2.zero; trt.offsetMax = Vector2.zero; }
            UIFactory.SetOverflowMode(t.badge, 2); UIFactory.SetWordWrap(t.badge, false);
            t.badgeGO = go;
            go.SetActive(false);
        }

        private static bool IsOffered(string printId)
        {
            string c = PcTradeRules.CanonicalId(printId);
            return c != null && offeredIds.Contains(c);
        }

        /// <summary>V8 6.1 badges: In a trade (held by one of the player's own
        /// open offers, from the cached full read - no request per tile) and
        /// Traded (the print's own server flag, permanent). Display only.</summary>
        private static void PaintTileBadge(Tile t, ApiClient.PcPrint p)
        {
            if (t == null || t.badgeGO == null) return;
            string b = "";
            if (p != null && !p.discarded && !p.gone)
            {
                bool held = IsOffered(p.print_id);
                if (held && p.traded && !t.mini) b = I18n.Tr("In a trade") + " | " + I18n.Tr("Traded");
                else if (held) b = I18n.Tr("In a trade");
                else if (p.traded) b = I18n.Tr("Traded");
            }
            bool on = b.Length > 0;
            if (t.badgeGO.activeSelf != on) t.badgeGO.SetActive(on);
            if (on) UIFactory.SetTextRaw(t.badge, b);
        }

        private static void LogBadges(List<ApiClient.PcPrint> prints)
        {
            int held = 0, traded = 0;
            foreach (var p in prints)
            {
                if (p == null || p.discarded) continue;
                if (IsOffered(p.print_id)) held++;
                if (p.traded) traded++;
            }
            string sig = held + "/" + traded;
            if (sig == tradeBadgeSig) return;
            tradeBadgeSig = sig;
            Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] badges held=" + held + " traded=" + traded);
        }

        private static void FillMiniTile(Tile t, ApiClient.PcPrint p, bool picked)
        {
            if (t == null || t.root == null) return;
            t.print = p; t.dupes = 0;
            t.bindSeq++;
            if (p == null) { ShowTileText(t); t.root.SetActive(false); return; }
            if (!t.root.activeSelf) t.root.SetActive(true);
            UIFactory.SetImageColor(t.root, picked ? C_PICKED : (p.gone ? C_DIM : FrameColor(p.rarity, p.foil)));
            UIFactory.SetTextRaw(t.txtName, p.gone ? I18n.Tr("[deleted]") : SafeName(p));
            UIFactory.SetTextRaw(t.txtMark, p.gone ? "" : MarkLine(p));
            if (p.gone) ShowTileText(t); else BindFace(t, p);
            PaintTileBadge(t, p);
        }

        private static void FillSide(Tile[] tiles, object more, List<ApiClient.PcPrint> prints)
        {
            int n = prints != null ? prints.Count : 0;
            for (int i = 0; i < tiles.Length; i++) FillMiniTile(tiles[i], i < n ? prints[i] : null, false);
            UIFactory.SetTextRaw(more, n > tiles.Length ? "+" + (n - tiles.Length) : "");
        }

        private static TradeRow CreateTradeRow(Transform parent, string name, bool incoming)
        {
            var r = new TradeRow();
            r.root = UIFactory.CreatePanel(name, parent, C_CARD);
            UIFactory.AddHLG(r.root, spacing: 10, padL: 8, padR: 8, padT: 6, padB: 6, forceExpandH: false);
            UIFactory.AddLE(r.root, prefH: MINI_H + 36f, minH: MINI_H + 36f, flexH: 0);
            var info = Column(r.root.transform, name + "_i", 250f);
            r.txtWho = UIFactory.CreateText(name + "_w", info.transform, "", 15f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(250, 22));
            r.txtWhen = UIFactory.CreateText(name + "_e", info.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(250, 20));
            r.txtNote = UIFactory.CreateText(name + "_o", info.transform, "", 12f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(250, 20));
            foreach (var o in new[] { r.txtWho, r.txtWhen, r.txtNote }) { UIFactory.SetOverflowMode(o, 2); UIFactory.SetWordWrap(o, false); }
            r.give = SideStrip(r.root.transform, name + "_g", I18n.Tr("You give"), out r.txtGiveMore, SIDE_TILES, null, false);
            r.get = SideStrip(r.root.transform, name + "_t", I18n.Tr("You get"), out r.txtGetMore, SIDE_TILES, null, false);
            var sp = new GameObject(name + "_sp"); sp.transform.SetParent(r.root.transform, false); sp.AddComponent<RectTransform>(); UIFactory.AddLE(sp, flexW: 1);
            var act = Column(r.root.transform, name + "_a", 170f);
            var row = r;
            if (incoming)
            {
                r.btnA = UIFactory.CreateButton(name + "_ok", act.transform, "Accept", 13f, C_WHITE, C_BUY, () => OnAcceptClick(row), sizeDelta: new Vector2(170, 28));
                r.btnB = UIFactory.CreateButton(name + "_no", act.transform, "Decline", 13f, C_WHITE, C_DANGER, () => OnCloseClick(row, "decline"), sizeDelta: new Vector2(170, 28));
            }
            else
                r.btnA = UIFactory.CreateButton(name + "_cx", act.transform, "Cancel", 13f, C_WHITE, C_DANGER, () => OnCloseClick(row, "cancel"), sizeDelta: new Vector2(170, 28));
            r.btnATxt = UIFactory.GetButtonText(r.btnA);
            r.root.SetActive(false);
            return r;
        }

        private static void RefreshTrades(string id)
        {
            if (tradesRoot == null) return;
            EnsureTradesBuilt();
            var sum = ApiClient.CachedPcTradeSummary;
            var full = ApiClient.CachedPcTrades;
            bool reads = PcTradeRules.ReadsAllowed(tradeDiscovery), propose = PcTradeRules.ProposeAllowed(tradeDiscovery);
            if (composing && !propose) EndCompose();   // paused (or gone) under an open compose: propose is not offered
            string hdr; Color hc = C_WHITE;
            if (tradeDiscovery == PcTradeRules.Discovery.Unknown) hdr = I18n.Tr("Loading...");
            else if (!propose) { hdr = TradeState(); hc = C_WARN; }
            else if (sum != null && !sum.tradesOpen) { hdr = ReasonText("trading_closed"); hc = C_WARN; }
            else if (full != null) hdr = I18n.TrF("Trades today: {0}/{1}", full.bounds.executed_today, full.bounds.executed_per_day);
            else if (ApiClient.PcTradesError != null) { hdr = ReasonText(ApiClient.PcTradeErrorCode(ApiClient.PcTradesError)); hc = C_WARN; }
            else hdr = I18n.Tr("Loading...");
            UIFactory.SetTextRaw(txtTradesHdr, hdr);
            UIFactory.SetColor(txtTradesHdr, hc);
            bool showNew = propose && !composing && !OwnTradingClosed();
            if (btnNewTrade != null && btnNewTrade.activeSelf != showNew) btnNewTrade.SetActive(showNew);
            bool showLists = reads && !composing;
            if (tradeListsBox != null && tradeListsBox.activeSelf != showLists) tradeListsBox.SetActive(showLists);
            if (composeBox != null && composeBox.activeSelf != composing) composeBox.SetActive(composing);
            int inc = 0, snt = 0;
            if (composing) RefreshCompose();
            else if (reads) RefreshTradeLists(full, out inc, out snt);
            string sig = (composing ? "compose" : (reads ? "lists" : "blocked")) + " discovery=" + tradeDiscovery
                + " in=" + inc + " sent=" + snt + " recent=" + (full != null ? full.recent.Count : 0) + " new_trade=" + (showNew ? 1 : 0)
                + (composing ? " give=" + composeGive.Count + " get=" + composeGet.Count + " theirs=" + (composeTheirs != null ? composeTheirs.prints.Count : -1) + " err=" + (composeTheirsError ?? "-") : "");
            if (sig != tradePanelSig) { tradePanelSig = sig; Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] panel " + sig); }
        }

        private static void RefreshTradeLists(ApiClient.PcTradeFull full, out int incCount, out int sentCount)
        {
            var inc = new List<ApiClient.PcTrade>(); var snt = new List<ApiClient.PcTrade>(); var rec = new List<ApiClient.PcTrade>();
            if (full != null)
            {
                foreach (var t in full.offers)
                {
                    var b = PcTradeRules.BucketOf(t.role, t.state);
                    if (b == PcTradeRules.Bucket.Incoming) inc.Add(t);
                    else if (b == PcTradeRules.Bucket.Sent) snt.Add(t);
                    else rec.Add(t);
                }
                rec.AddRange(full.recent);
            }
            incCount = inc.Count; sentCount = snt.Count;
            UIFactory.SetTextRaw(txtInHdr, I18n.Tr("Incoming") + " (" + inc.Count + ")");
            UIFactory.SetTextRaw(txtSentHdr, I18n.Tr("Sent") + " (" + snt.Count + ")");
            UIFactory.SetTextRaw(txtRecentHdr, I18n.Tr("Recent") + " (" + rec.Count + ")");
            PaintRows(inRows, inBox, "PcTI", inc, true, full);
            PaintRows(sentRows, sentBox, "PcTS", snt, false, full);
            while (recentTxts.Count < rec.Count)
            {
                var o = UIFactory.CreateText("PcTR" + recentTxts.Count, recentBox.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(1100, 20));
                UIFactory.SetOverflowMode(o, 2); UIFactory.SetWordWrap(o, false);
                recentTxts.Add(o);
            }
            for (int i = 0; i < recentTxts.Count; i++)
            {
                var go = (recentTxts[i] as Component) != null ? ((Component)recentTxts[i]).gameObject : null;
                bool on = i < rec.Count;
                if (go != null && go.activeSelf != on) go.SetActive(on);
                if (on) UIFactory.SetTextRaw(recentTxts[i], RecentLine(rec[i]));
            }
        }

        /// <summary>Rows are created as the lists need them (lazily, and never
        /// more than the longest list seen), so no bound is hardcoded here.</summary>
        private static void PaintRows(List<TradeRow> rows, GameObject box, string prefix, List<ApiClient.PcTrade> list, bool incoming, ApiClient.PcTradeFull full)
        {
            while (rows.Count < list.Count) rows.Add(CreateTradeRow(box.transform, prefix + rows.Count, incoming));
            for (int i = 0; i < rows.Count; i++)
            {
                if (i < list.Count) FillTradeRow(rows[i], list[i], incoming, full);
                else { rows[i].trade = null; if (rows[i].root.activeSelf) rows[i].root.SetActive(false); }
            }
        }

        private static void FillTradeRow(TradeRow r, ApiClient.PcTrade t, bool incoming, ApiClient.PcTradeFull full)
        {
            r.trade = t;
            if (!r.root.activeSelf) r.root.SetActive(true);
            string name = TradeName(t);
            if (name.Length == 0) name = I18n.Tr("Unnamed player");
            string who = incoming ? I18n.TrF("From {0}", name) : I18n.TrF("To {0}", name);
            if (t.counterparty_rating.HasValue) who += "  (" + Mathf.RoundToInt(t.counterparty_rating.Value) + ")";
            UIFactory.SetTextRaw(r.txtWho, who);
            if (!t.possible)
            {
                UIFactory.SetTextRaw(r.txtWhen, I18n.Tr("No longer possible"));
                UIFactory.SetColor(r.txtWhen, C_WARN);
            }
            else
            {
                // the server's clock, never this PC's (V8 1.6)
                double left = PcTradeRules.SecondsLeft(t.expires_at, full != null ? full.serverNow : null, Now - ApiClient.PcTradesFetchedAt);
                UIFactory.SetTextRaw(r.txtWhen, I18n.TrF("Expires in {0}", PcTradeRules.TimeLeftText(left)));
                UIFactory.SetColor(r.txtWhen, C_LABEL);
            }
            UIFactory.SetTextRaw(r.txtNote, incoming ? "" : I18n.Tr("Waiting for their answer"));
            FillSide(r.give, r.txtGiveMore, t.give);
            FillSide(r.get, r.txtGetMore, t.get);
            if (incoming)
            {
                // A row that is no longer possible, or trading paused: no Accept (V8 1.4, 6.9)
                bool canAccept = t.possible && PcTradeRules.ProposeAllowed(tradeDiscovery);
                if (r.btnA.activeSelf != canAccept) r.btnA.SetActive(canAccept);
                bool armed = PcTradeRules.ConfirmsArmed(armedTradeId, armedTradeAt, t.trade_id, Now);
                UIFactory.SetText(r.btnATxt, armed ? "Confirm accept" : "Accept");
            }
            UIFactory.SetImageColor(r.btnA, tradeActInFlight ? C_BTN : (incoming ? C_BUY : C_DANGER));
        }

        private static string RecentLine(ApiClient.PcTrade t)
        {
            string outcome;
            switch (t.state)
            {
                case "executed": outcome = I18n.Tr("Trade completed"); break;
                case "declined": outcome = I18n.Tr("Trade declined"); break;
                case "cancelled": outcome = I18n.Tr("Trade cancelled"); break;
                case "expired": outcome = I18n.Tr("Trade expired"); break;
                case "reversed": outcome = ReasonText("reversed"); break;
                default: outcome = I18n.Tr("No longer possible"); break;   // void, and any state this build does not know
            }
            string name = TradeName(t);
            if (name.Length == 0) name = I18n.Tr("Unnamed player");
            string line = outcome + "  -  " + (t.role == "sent" ? I18n.TrF("To {0}", name) : I18n.TrF("From {0}", name))
                + "  -  " + DateOnly(!string.IsNullOrEmpty(t.closed_at) ? t.closed_at : t.expires_at);
            if (!string.IsNullOrEmpty(t.reason)) line += "  -  " + ReasonText(t.reason);
            line += "  -  " + I18n.Tr("You give") + ": " + CardList(t.give) + "  |  " + I18n.Tr("You get") + ": " + CardList(t.get);
            return line;
        }

        private static string CardList(List<ApiClient.PcPrint> prints)
        {
            var parts = new List<string>();
            if (prints != null)
                foreach (var p in prints)
                    parts.Add(p == null || p.gone ? I18n.Tr("[deleted]") : SafeName(p) + " (" + RarityLabel(p.rarity) + ")");
            return string.Join(", ", parts.ToArray());
        }

        // -- the inbox's actions (V8 1.4-1.5, 6.3, 6.6) ------------------------

        /// <summary>Accept is armed by the first click and confirmed by a second
        /// inside six seconds, Discard's rule, on its OWN armed pair: the
        /// binder's armedPrintId would collide with it.</summary>
        private static void OnAcceptClick(TradeRow r)
        {
            var t = r != null ? r.trade : null; var id = LocalId();
            if (t == null || id == null) return;
            if (!SessionReady) { Say(ReasonText("session_required"), C_WARN); return; }
            if (tradeActInFlight) return;
            if (!PcTradeRules.ProposeAllowed(tradeDiscovery)) { Say(TradeState(), C_WARN); return; }
            if (!PcTradeRules.ConfirmsArmed(armedTradeId, armedTradeAt, t.trade_id, Now))
            {
                armedTradeId = t.trade_id; armedTradeAt = Now;
                NativeUI.MarkDirty();
                return;
            }
            armedTradeId = null;
            TradeAct("accept", id, t, false);
        }

        private static void OnCloseClick(TradeRow r, string action)
        {
            var t = r != null ? r.trade : null; var id = LocalId();
            if (t == null || id == null) return;
            if (!SessionReady) { Say(ReasonText("session_required"), C_WARN); return; }
            if (tradeActInFlight) return;
            TradeAct(action, id, t, false);
        }

        /// <summary>One nonce per (action, trade) for the life of the attempt: a
        /// retry after a lost answer re-sends it and gets the stored row.</summary>
        private static string ActNonce(string action, string tradeId)
        {
            string k = action + "|" + tradeId, n;
            if (!actNonces.TryGetValue(k, out n)) { n = NewNonce(); actNonces[k] = n; }
            return n;
        }

        /// <summary>No answer, or a refusal that turned the request away before
        /// it was read: the attempt keeps its nonce.</summary>
        private static bool KeepsNonce(string code)
        {
            return code == "transport" || code == "rate_limited" || code == "busy";
        }

        private static void TradeAct(string action, string id, ApiClient.PcTrade t, bool isRetry)
        {
            string tid = t.trade_id, dg = t.digest, nonce = ActNonce(action, tid);
            tradeActInFlight = true; tradeActAt = Now;
            NativeUI.MarkDirty();
            int ep = uiEpoch;
            ApiClient.PcTradeAct(action, id, nonce, tid, dg, (ok, resp) =>
            {
                if (ep != uiEpoch) return;
                tradeActInFlight = false;
                string code = ok ? null : ApiClient.PcTradeErrorCode(resp);
                Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] " + action + " ok=" + (ok ? 1 : 0) + " code=" + (code ?? "-") + (isRetry ? " retry=1" : ""));
                if (!ok && PcTradeRules.RetryBusy(code, isRetry))
                {
                    // V8 1.4: busy is retried once, after two seconds, before it is shown
                    tradeActInFlight = true; tradeActAt = Now;
                    Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] busy-retry action=" + action);
                    RetryLater(ep, PcTradeRules.NoComposeFence, null, () => TradeAct(action, id, t, true), null);
                    return;
                }
                if (ok || !KeepsNonce(code)) actNonces.Remove(action + "|" + tid);
                if (ok)
                {
                    if (action == "accept") { DrawReceived(resp); Say(I18n.Tr("Trade completed"), C_OK); }
                    else if (action == "decline") Say(I18n.Tr("Trade declined"), C_OK);
                    else Say(I18n.Tr("Trade cancelled"), C_OK);
                    AfterTradeAction(id);
                }
                else
                {
                    Say(ReasonText(code), C_WARN);
                    if (PcTradeRules.RefetchAfterRefusal(code)) AfterTradeAction(id);
                }
                NativeUI.MarkDirty();
            });
        }

        /// <summary>After every action, and after every refusal
        /// PcTradeRules.RefetchAfterRefusal names (all but busy, retried
        /// instead, and transport, no answer; a rate limit included): the
        /// trade list AND the binder are re-read from the server, since this
        /// client's copy may be what was wrong (V8 6.4, 6.6).</summary>
        private static void AfterTradeAction(string id)
        {
            if (id == null) return;
            ReadTrades(id, true);
            ApiClient.FetchPcCollection(id, true);
        }

        /// <summary>Runs a retry after BusyRetrySeconds (the busy retry, V8 1.4,
        /// and the binder read's in-flight retry) behind the fence
        /// PcTradeRules.RetryCheck decides, consulted BEFORE the retry runs
        /// (TC-M1): an identity edge drops it silently (ResetTrades already
        /// released the attempt), and a compose that ended, was replaced or no
        /// longer holds the armed terms drops it through `dropped`, which
        /// releases what the attempt still holds. `seq` is
        /// PcTradeRules.NoComposeFence for a retry that belongs to no compose,
        /// and `terms` is null for one that carries none.</summary>
        private static void RetryLater(int ep, int seq, string terms, Action a, Action dropped)
        {
            try { Plugin.Instance.StartCoroutine(RetryCo(ep, seq, terms, a, dropped)); }
            catch (Exception ex) { tradeActInFlight = false; Plugin.Log.LogWarning("[PC] trade retry not scheduled: " + ex.Message); }
        }

        private static IEnumerator RetryCo(int ep, int seq, string terms, Action a, Action dropped)
        {
            yield return new WaitForSecondsRealtime(PcTradeRules.BusyRetrySeconds);
            string termsNow = terms == null ? null : PcTradeRules.TermsKey(composeTo, composeGive, composeGet);
            var verdict = PcTradeRules.RetryCheck(ep, uiEpoch, seq, composeSeq, terms, termsNow);
            if (verdict == PcTradeRules.RetryVerdict.IdentityChanged) yield break;
            if (verdict == PcTradeRules.RetryVerdict.ComposeChanged)
            {
                try { if (dropped != null) dropped(); }
                catch (Exception ex) { tradeActInFlight = false; Plugin.Log.LogWarning("[PC] trade retry drop threw: " + ex.Message); }
                yield break;
            }
            try { a(); }
            catch (Exception ex) { tradeActInFlight = false; Plugin.Log.LogWarning("[PC] trade retry threw: " + ex.Message); }
        }

        /// <summary>An executed accept draws the answer's received prints into
        /// the binder at once (and drops the given ones); the forced binder read
        /// that follows (AfterTradeAction) replaces the cache with the server's
        /// word (V8 6.6).</summary>
        private static void DrawReceived(string resp)
        {
            var col = ApiClient.CachedPcCollection;
            var ans = ApiClient.ParsePcTrade(resp, col != null ? col.locale : "en");
            if (col == null || ans == null) return;
            var gave = new HashSet<string>(StringComparer.Ordinal);
            foreach (var p in ans.give) if (p != null && !string.IsNullOrEmpty(p.print_id)) gave.Add(p.print_id);
            col.prints.RemoveAll(p => p != null && gave.Contains(p.print_id));
            int drawn = 0;
            foreach (var p in ans.get)
                if (p != null && !p.gone && !string.IsNullOrEmpty(p.print_id) && !col.prints.Exists(x => x.print_id == p.print_id)) { col.prints.Add(p); drawn++; }
            Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] accept drew received=" + drawn + " gave=" + gave.Count);
        }

        // -- the card view's entry (V8 6.1) ------------------------------------

        /// <summary>Offer in a trade, beside the card: an own, live print, while
        /// trading is on, and not already held by one of the player's open
        /// offers (from the cached full read's own sent proposals - sent_open
        /// carries TRADE ids, never print ids).</summary>
        private static void MaybeAddOfferButton(ApiClient.PcPrint p, float h)
        {
            if (cardPopupGO == null || !OfferAllowed(p)) return;
            float fw = h * PlayerCardFaces.CARD_W / PlayerCardFaces.CARD_H;
            AddOfferButton(cardPopupGO.transform, p.print_id, fw / 2f + 24f, HideCardPopup, "face");
        }

        private static bool OfferAllowed(ApiClient.PcPrint p)
        {
            if (p == null || p.discarded || !PcTradeRules.ProposeAllowed(tradeDiscovery) || OwnTradingClosed()) return false;
            var own = ApiClient.CachedPcCollection;
            if (own == null || !own.prints.Exists(x => x.print_id == p.print_id && !x.discarded)) return false;
            return !IsOffered(p.print_id);
        }

        /// <summary>The text card view (a print with no face to show) is
        /// NativeUI's info popup: Offer in a trade sits to the right of its box,
        /// as it does beside a face, parented to that popup so closing the popup
        /// removes it. The newest popup is the last child of that name: one
        /// closed this frame may not be destroyed yet.</summary>
        private static void MaybeAddTextOfferButton(ApiClient.PcPrint p)
        {
            if (!OfferAllowed(p)) return;
            Transform pop = null;
            try
            {
                var overlay = NativeUI.OverlayRoot;
                for (int i = overlay != null ? overlay.childCount - 1 : -1; i >= 0 && pop == null; i--)
                {
                    var c = overlay.GetChild(i);
                    if (c != null && c.name == "CR_InfoPopup") pop = c;
                }
            }
            catch { }
            if (pop == null) return;
            float bw = 960f;
            var box = pop.Find("Box") as RectTransform;
            if (box != null && box.sizeDelta.x > 0f) bw = box.sizeDelta.x;
            AddOfferButton(pop, p.print_id, bw / 2f + 24f, NativeUI.HideInfoPopup, "text");
        }

        private static void AddOfferButton(Transform parent, string pid, float x, Action hide, string kind)
        {
            var btn = UIFactory.CreateButton("Offer", parent, "Offer in a trade", 16f, C_WHITE, C_BUY,
                () => { hide(); StartTradeSearch(pid); NativeUI.MarkDirty(); }, sizeDelta: new Vector2(260, 40));
            var rt = btn.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0.5f, 0.5f); rt.anchorMax = new Vector2(0.5f, 0.5f); rt.pivot = new Vector2(0f, 0.5f);
            rt.anchoredPosition = new Vector2(x, 0f);
            // the popup's own control, like its backdrop: it must work while the popup holds the input
            var ch = btn.GetComponent<ClickHandler>();
            if (ch != null) ch.bypassModalBlock = true;
            offerBtnGO = btn; offerBtnPid = pid; offerBtnHide = hide;
            Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] offer-button shown=1 view=" + kind);
        }

        // -- the proposal flow (V8 6.2) ----------------------------------------

        /// <summary>New trade: the existing general player search (C5 - called
        /// into, not rebuilt), then the compose screen. `preselect` is one of
        /// the player's own prints, from the card view.</summary>
        private static void StartTradeSearch(string preselect)
        {
            if (tradeActInFlight) { FrozenInput("search"); return; }
            if (!PcTradeRules.ProposeAllowed(tradeDiscovery)) { Say(TradeState(), C_WARN); return; }
            if (OwnTradingClosed()) { Say(ReasonText("trading_closed"), C_WARN); return; }
            int ep = uiEpoch;
            try
            {
                CompetitiveUI.OpenPlayerSearch(I18n.Tr("Search for a player by name"), (sid, name) =>
                {
                    if (ep != uiEpoch) return;
                    StartCompose(sid, name, preselect);
                });
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[PC] trade search failed: " + ex.Message); }
        }

        private static void StartCompose(string toSteamId, string name, string preselect)
        {
            var id = LocalId();
            if (id == null || string.IsNullOrEmpty(toSteamId)) return;
            if (tradeActInFlight) { FrozenInput("new"); return; }
            if (toSteamId == id) { Say(ReasonText("self_trade"), C_WARN); return; }
            if (!PcTradeRules.ProposeAllowed(tradeDiscovery)) { Say(TradeState(), C_WARN); return; }
            EndCompose();
            composing = true; view = View.Trades;
            composeTo = toSteamId;
            composeToName = string.IsNullOrEmpty(name) ? null : name;
            if (!string.IsNullOrEmpty(preselect)) composeGive.Add(preselect);
            if (ApiClient.CachedPcTrades == null) ReadTrades(id, true);   // the bounds: the side cap and the expiry
            if (ApiClient.CachedPcCollection == null) ApiClient.FetchPcCollection(id);
            FetchTheirBinder(id, composeSeq);
            Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] compose start preselected=" + composeGive.Count);
            NativeUI.MarkDirty();
        }

        /// <summary>The compose is frozen while an attempt is pending (TC-M1):
        /// from Send's own commit through its answer, or through the busy
        /// retry's answer, Back, the pickers and a new compose are ignored -
        /// the `if (tradeActInFlight)` rule OnAcceptClick and OnCloseClick
        /// already follow. The refused input is logged for the witness.</summary>
        private static void FrozenInput(string input)
        {
            Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] compose frozen input=" + input);
        }

        /// <summary>The compose's Back button, and the lever's "back".</summary>
        private static void OnComposeBack()
        {
            if (tradeActInFlight) { FrozenInput("back"); return; }
            EndCompose();
            NativeUI.MarkDirty();
        }

        private static void EndCompose()
        {
            composing = false; composeSeq++;
            composeTo = null; composeToName = null;
            composeTheirs = null; composeTheirsError = null; composeTheirsLoading = false;
            composeGive.Clear(); composeGet.Clear();
            composeNonce = null; composeNonceKey = null;
            giveCardPage = 0; getCardPage = 0;
        }

        /// <summary>Their binder through /pc/collection?subject= (a private one
        /// answers 403 private). One request in flight at a time: a compose
        /// started while the last one's is still out asks again shortly.</summary>
        private static void FetchTheirBinder(string id, int seq)
        {
            if (!composing || id == null || seq != composeSeq) return;
            composeTheirsLoading = true;
            int ep = uiEpoch; string to = composeTo;
            ApiClient.FetchPcCollectionOf(id, to, (ok, resp) =>
            {
                if (ep != uiEpoch || seq != composeSeq) return;
                if (!ok && resp == "in-flight") { RetryLater(ep, seq, null, () => FetchTheirBinder(id, seq), null); return; }
                composeTheirsLoading = false;
                string code = ok ? null : ApiClient.PcTradeErrorCode(resp);
                if (ok)
                {
                    var col = ApiClient.ParsePcCollection(resp);
                    if (col == null) composeTheirsError = "parse";
                    else
                    {
                        composeTheirs = col; composeTheirsError = null;
                        if (!string.IsNullOrEmpty(col.owner_name)) composeToName = col.owner_name;   // the server's render name
                    }
                }
                else composeTheirsError = code;
                Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] collection-of ok=" + (composeTheirs != null ? 1 : 0) + " code=" + (composeTheirsError ?? "-")
                    + " prints=" + (composeTheirs != null ? composeTheirs.prints.Count : 0));
                NativeUI.MarkDirty();
            });
        }

        private static int SideMax()
        {
            var f = ApiClient.CachedPcTrades;
            return f != null ? f.bounds.prints_per_side_max : 0;
        }

        /// <summary>A picker click (or a chosen card's click, to drop it). The
        /// cap is the server's prints_per_side_max; unknown until the full read
        /// has answered, and then nothing is chosen.</summary>
        private static void ToggleComposeCard(Tile t, bool mine)
        {
            var p = t != null ? t.print : null;
            if (p == null || !composing || string.IsNullOrEmpty(p.print_id)) return;
            if (tradeActInFlight) { FrozenInput("pick"); return; }
            var side = mine ? composeGive : composeGet;
            if (side.Contains(p.print_id)) side.Remove(p.print_id);
            else
            {
                int max = SideMax();
                if (!PcTradeRules.CanAddToSide(side.Count, max))
                {
                    if (max <= 0) Say(I18n.Tr("Loading..."));
                    else if (mine) Say(I18n.TrF("Choose up to {0} of your cards", max), C_WARN);
                    else Say(I18n.TrF("Choose up to {0} of their cards", max), C_WARN);
                    return;
                }
                side.Add(p.print_id);
            }
            NativeUI.MarkDirty();
        }

        private static void PageCompose(bool mine, int delta)
        {
            if (mine) giveCardPage += delta; else getCardPage += delta;
            NativeUI.MarkDirty();
        }

        private static void BuildCompose()
        {
            composeBox = new GameObject("PcTCompose");
            composeBox.transform.SetParent(tradesRoot.transform, false);
            composeBox.AddComponent<RectTransform>();
            UIFactory.AddVLG(composeBox, spacing: 6);
            UIFactory.AddLE(composeBox, flexH: 1);
            var hdr = new GameObject("PcTCHdr"); hdr.transform.SetParent(composeBox.transform, false); hdr.AddComponent<RectTransform>();
            UIFactory.AddHLG(hdr, spacing: 10, forceExpandH: true); UIFactory.AddLE(hdr, prefH: 28, flexH: 0);
            txtComposeHdr = UIFactory.CreateText("PcTCHdrT", hdr.transform, "", 16f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(700, 26));
            var sp = new GameObject("PcTCSp"); sp.transform.SetParent(hdr.transform, false); sp.AddComponent<RectTransform>(); UIFactory.AddLE(sp, flexW: 1);
            UIFactory.CreateButton("PcTCBack", hdr.transform, "Back", 14f, C_WHITE, C_BTN, OnComposeBack, sizeDelta: new Vector2(120, 26));
            var sv = UIFactory.CreateScrollView("PcTCSV", composeBox.transform, spacing: 6);
            UIFactory.AddLE(sv.scrollGO, flexH: 1);
            var c = sv.content.transform;
            // the review panel: both sides as faces, the only-copy warning, the expiry, Send
            var rev = UIFactory.CreatePanel("PcTCRev", c, C_PANEL);
            UIFactory.AddHLG(rev, spacing: 14, padL: 10, padR: 10, padT: 6, padB: 6, forceExpandH: false);
            UIFactory.AddLE(rev, prefH: MINI_H + 36f, minH: MINI_H + 36f, flexH: 0);
            giveSelTiles = SideStrip(rev.transform, "PcTCGv", I18n.Tr("You give"), out composeGiveMore, SIDE_TILES, t => ToggleComposeCard(t, true), false);
            getSelTiles = SideStrip(rev.transform, "PcTCGt", I18n.Tr("You get"), out composeGetMore, SIDE_TILES, t => ToggleComposeCard(t, false), false);
            var info = Column(rev.transform, "PcTCInfo", 420f);
            txtComposeWarn = UIFactory.CreateText("PcTCWarn", info.transform, "", 13f, C_WARN, UIFactory.AlignMidLeft, sizeDelta: new Vector2(420, 20));
            txtComposeExpiry = UIFactory.CreateText("PcTCExp", info.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(420, 20));
            btnSendProposal = UIFactory.CreateButton("PcTCSend", info.transform, "Send proposal", 14f, C_WHITE, C_BUY, SendProposal, sizeDelta: new Vector2(240, 30));
            // their cards first (what is asked for), then the player's own
            getPickTiles = PickerSection(c, "PcTCTh", out txtGetPickHdr, out txtGetPage, out txtTheirNote,
                () => PageCompose(false, -1), () => PageCompose(false, +1), t => ToggleComposeCard(t, false));
            givePickTiles = PickerSection(c, "PcTCMy", out txtGivePickHdr, out txtGivePage, out txtOwnNote,
                () => PageCompose(true, -1), () => PageCompose(true, +1), t => ToggleComposeCard(t, true));
            composeBox.SetActive(false);
        }

        private static Tile[] PickerSection(Transform parent, string name, out object hdr, out object page, out object note,
            UnityEngine.Events.UnityAction prev, UnityEngine.Events.UnityAction next, Action<Tile> click)
        {
            var box = UIFactory.CreatePanel(name, parent, C_PANEL);
            UIFactory.AddVLG(box, spacing: 4, padL: 10, padR: 10, padT: 6, padB: 6);
            UIFactory.AddLE(box, flexH: 0);
            var hr = new GameObject(name + "_hr"); hr.transform.SetParent(box.transform, false); hr.AddComponent<RectTransform>();
            UIFactory.AddHLG(hr, spacing: 8, forceExpandH: true); UIFactory.AddLE(hr, prefH: 26, flexH: 0);
            hdr = UIFactory.CreateText(name + "_h", hr.transform, "", 14f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(600, 24));
            var sp = new GameObject(name + "_sp"); sp.transform.SetParent(hr.transform, false); sp.AddComponent<RectTransform>(); UIFactory.AddLE(sp, flexW: 1);
            UIFactory.CreateButton(name + "_p", hr.transform, "<", 14f, C_WHITE, C_BTN, prev, sizeDelta: new Vector2(40, 24));
            page = UIFactory.CreateText(name + "_pg", hr.transform, "", 13f, C_LABEL, UIFactory.AlignMidCenter, sizeDelta: new Vector2(140, 24));
            UIFactory.CreateButton(name + "_n", hr.transform, ">", 14f, C_WHITE, C_BTN, next, sizeDelta: new Vector2(40, 24));
            note = UIFactory.CreateText(name + "_no", box.transform, "", 13f, C_WARN, UIFactory.AlignMidLeft, sizeDelta: new Vector2(1000, 20));
            UIFactory.SetWordWrap(note, true); UIFactory.SetTextAutoHeight(note, 20f);
            var strip = new GameObject(name + "_s"); strip.transform.SetParent(box.transform, false); strip.AddComponent<RectTransform>();
            UIFactory.AddHLG(strip, spacing: 4, forceExpandH: false);
            UIFactory.AddLE(strip, prefH: MINI_H, minH: MINI_H, flexH: 0);
            var tiles = new Tile[PICK_PAGE];
            for (int i = 0; i < PICK_PAGE; i++) tiles[i] = CreateMiniTile(strip.transform, name + i, click, true);
            return tiles;
        }

        private static int ComparePick(ApiClient.PcPrint a, ApiClient.PcPrint b)
        {
            int c = RarityOrder(a.rarity).CompareTo(RarityOrder(b.rarity));
            if (c != 0) return c;
            c = string.Compare(SafeName(a), SafeName(b), StringComparison.OrdinalIgnoreCase);
            if (c != 0) return c;
            return string.CompareOrdinal(a.print_id ?? "", b.print_id ?? "");
        }

        /// <summary>A chosen card that is gone from the binder it came from (a
        /// refetch after a refusal, a discard elsewhere) is dropped.</summary>
        private static void PruneCompose()
        {
            var own = ApiClient.CachedPcCollection;
            if (own != null) composeGive.RemoveAll(pid => !own.prints.Exists(p => p.print_id == pid && !p.discarded));
            if (composeTheirs != null) composeGet.RemoveAll(pid => !composeTheirs.prints.Exists(p => p.print_id == pid && !p.discarded));
        }

        private static void RefreshCompose()
        {
            PruneCompose();
            var own = ApiClient.CachedPcCollection;
            var full = ApiClient.CachedPcTrades;
            int max = SideMax();
            string name = !string.IsNullOrEmpty(composeToName) ? composeToName : I18n.Tr("Unnamed player");
            if (name.Length > 24) name = name.Substring(0, 24);
            UIFactory.SetTextRaw(txtComposeHdr, I18n.TrF("To {0}", name));
            theirPickList.Clear();
            if (composeTheirs != null) foreach (var p in composeTheirs.prints) if (p != null && !p.discarded) theirPickList.Add(p);
            theirPickList.Sort(ComparePick);
            ownPickList.Clear();
            if (own != null) foreach (var p in own.prints) if (p != null && !p.discarded) ownPickList.Add(p);
            ownPickList.Sort(ComparePick);
            string theirNote;
            if (composeTheirsError == "private") theirNote = I18n.TrF("{0}'s binder is private - they can still propose a trade to you", name);
            else if (composeTheirsError != null) theirNote = ReasonText(composeTheirsError);
            else if (composeTheirs == null || composeTheirsLoading) theirNote = I18n.Tr("Loading...");
            else theirNote = "";
            UIFactory.SetTextRaw(txtTheirNote, theirNote);
            UIFactory.SetTextRaw(txtOwnNote, own == null ? (ApiClient.PcCollectionError != null ? ReasonText(ApiClient.PcErrorCode(ApiClient.PcCollectionError)) : I18n.Tr("Loading...")) : "");
            UIFactory.SetTextRaw(txtGetPickHdr, max > 0 ? I18n.TrF("Choose up to {0} of their cards", max) : I18n.Tr("Loading..."));
            UIFactory.SetTextRaw(txtGivePickHdr, max > 0 ? I18n.TrF("Choose up to {0} of your cards", max) : I18n.Tr("Loading..."));
            PaintPicker(getPickTiles, theirPickList, ref getCardPage, txtGetPage, composeGet);
            PaintPicker(givePickTiles, ownPickList, ref giveCardPage, txtGivePage, composeGive);
            FillChosen(giveSelTiles, composeGiveMore, composeGive, own != null ? own.prints : null);
            FillChosen(getSelTiles, composeGetMore, composeGet, composeTheirs != null ? composeTheirs.prints : null);
            UIFactory.SetTextRaw(txtComposeWarn, OnlyCopyGiven(own) ? I18n.Tr("This is your only copy of this card") : "");
            UIFactory.SetTextRaw(txtComposeExpiry, full != null && full.bounds.ttl_hours > 0
                ? I18n.TrF("Expires in {0}", PcTradeRules.TimeLeftText(full.bounds.ttl_hours * 3600.0)) : "");
            bool canSend = composeGive.Count > 0 && composeGet.Count > 0 && PcTradeRules.ProposeAllowed(tradeDiscovery) && !tradeActInFlight;
            UIFactory.SetImageColor(btnSendProposal, canSend ? C_BUY : C_BTN);
        }

        private static void PaintPicker(Tile[] tiles, List<ApiClient.PcPrint> list, ref int page, object pageTxt, List<string> chosen)
        {
            if (tiles == null) return;
            int pages = Math.Max(1, (list.Count + PICK_PAGE - 1) / PICK_PAGE);
            if (page >= pages) page = pages - 1;
            if (page < 0) page = 0;
            UIFactory.SetTextRaw(pageTxt, I18n.TrF("Page {0} of {1}", page + 1, pages));
            for (int i = 0; i < tiles.Length; i++)
            {
                int idx = page * PICK_PAGE + i;
                var p = idx < list.Count ? list[idx] : null;
                FillMiniTile(tiles[i], p, p != null && chosen.Contains(p.print_id));
            }
        }

        private static void FillChosen(Tile[] tiles, object more, List<string> ids, List<ApiClient.PcPrint> pool)
        {
            if (tiles == null) return;
            for (int i = 0; i < tiles.Length; i++)
            {
                ApiClient.PcPrint p = null;
                if (i < ids.Count && pool != null) { string want = ids[i]; p = pool.Find(x => x.print_id == want); }
                FillMiniTile(tiles[i], p, false);
            }
            UIFactory.SetTextRaw(more, ids.Count > tiles.Length ? "+" + (ids.Count - tiles.Length) : "");
        }

        /// <summary>The only-copy warning (V8 6.2), advisory: a chosen card with
        /// no other live, unchosen copy of the same card in the cached binder.</summary>
        private static bool OnlyCopyGiven(ApiClient.PcCollection own)
        {
            if (own == null) return false;
            foreach (var pid in composeGive)
            {
                var p = own.prints.Find(x => x.print_id == pid);
                if (p == null) continue;
                bool other = own.prints.Exists(x => x.print_id != pid && x.card_id == p.card_id && !x.discarded && !composeGive.Contains(x.print_id));
                if (!other) return true;
            }
            return false;
        }

        /// <summary>Send (V8 6.2): the digest and the signed terms are built by
        /// ApiClient.PcTradePropose from PcTradeRules. The nonce is bound to the
        /// terms: the same terms re-sent after a lost answer re-send the same
        /// nonce and get the stored row; changed terms start a new attempt.</summary>
        private static void SendProposal()
        {
            var id = LocalId();
            if (id == null || !composing) return;
            if (!SessionReady) { Say(ReasonText("session_required"), C_WARN); return; }
            if (!PcTradeRules.ProposeAllowed(tradeDiscovery)) { Say(TradeState(), C_WARN); return; }
            if (tradeActInFlight || composeGive.Count == 0 || composeGet.Count == 0) return;
            var give = new List<string>(composeGive); give.Sort(StringComparer.Ordinal);
            var get = new List<string>(composeGet); get.Sort(StringComparer.Ordinal);
            string key = PcTradeRules.TermsKey(composeTo, give, get);
            if (composeNonce == null || composeNonceKey != key) { composeNonce = NewNonce(); composeNonceKey = key; }
            ProposeNow(id, composeTo, give, get, composeNonce, composeSeq, false);
        }

        private static void ProposeNow(string id, string to, List<string> give, List<string> get, string nonce, int seq, bool isRetry)
        {
            tradeActInFlight = true; tradeActAt = Now;
            NativeUI.MarkDirty();
            int ep = uiEpoch;
            ApiClient.PcTradePropose(id, nonce, to, give, get, (ok, resp) =>
            {
                if (ep != uiEpoch) return;
                tradeActInFlight = false;
                string code = ok ? null : ApiClient.PcTradeErrorCode(resp);
                Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] propose ok=" + (ok ? 1 : 0) + " code=" + (code ?? "-") + (isRetry ? " retry=1" : "")
                    + " give=" + give.Count + " get=" + get.Count);
                if (!ok && PcTradeRules.RetryBusy(code, isRetry))
                {
                    tradeActInFlight = true; tradeActAt = Now;
                    Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] busy-retry action=propose");
                    RetryLater(ep, seq, PcTradeRules.TermsKey(to, give, get),
                               () => ProposeNow(id, to, give, get, nonce, seq, true), ProposeRetryDropped);
                    return;
                }
                if (ok)
                {
                    // committed: the new proposal is in Sent after the forced read
                    if (seq == composeSeq) EndCompose();
                    view = View.Trades;
                    AfterTradeAction(id);
                }
                else
                {
                    if (!KeepsNonce(code) && seq == composeSeq) { composeNonce = null; composeNonceKey = null; }
                    Say(ReasonText(code), C_WARN);
                    if (PcTradeRules.RefetchAfterRefusal(code))
                    {
                        AfterTradeAction(id);
                        if (composing && seq == composeSeq) FetchTheirBinder(id, seq);
                    }
                }
                NativeUI.MarkDirty();
            });
        }

        /// <summary>A busy proposal's retry, dropped by the fence (TC-M1): the
        /// first answer stands. Busy turned the request away before it was
        /// read (the reason the attempt keeps its nonce), so nothing is
        /// pending any more: the freeze is released and the busy reason is
        /// shown, as it would have been had the retry been refused too.</summary>
        private static void ProposeRetryDropped()
        {
            tradeActInFlight = false;
            Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] busy-retry dropped action=propose reason=compose-changed");
            Say(ReasonText("busy"), C_WARN);
            NativeUI.MarkDirty();
        }


        // ── Settings tab rows (design v4 §12 wording; no opt-out and no picture
        // choice since 2026-09-13: nobody leaves the pool by choice, the card
        // shows the Steam profile picture until this PC has sent the in-game
        // character, and only deleting all data removes the cards). Who IS in
        // the pool is the server's word, and since the 2026-09-15 merge that is
        // every unbanned player who has run the mod from a Steam account -- not
        // every registered player, which is what this comment said until the
        // 2026-09-16 coherence pass. ──
        /// <summary>Round-2 R4: the two Player Cards switches are neutral until
        /// /pc/me answers; their labels say "..." until then.</summary>
        private static bool PcMeKnown() { return ApiClient.CachedPcMe != null; }

        internal static void BuildSettingsRows(Transform parent)
        {
            UIFactory.CreateText("SPcHdr", parent, "Player Cards", 15f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(700, 22));
            btnPublic = NativeUI.SettingsSwitch(parent, "SPcPub",
                I18n.Tr("Lets others see which cards you hold, in the mod and in Discord."),
                () => ApiClient.CachedPcMe != null && ApiClient.CachedPcMe.collection_public,
                () => ToggleSetting("collection_public"),
                PcMeKnown);
            btnPublicTxt = UIFactory.GetButtonText(btnPublic);
            btnAnnounce = NativeUI.SettingsSwitch(parent, "SPcAnn",
                I18n.Tr("Rare pulls may be posted to the Discord gambler chat with your name."),
                () => ApiClient.CachedPcMe != null && ApiClient.CachedPcMe.announce,
                () => ToggleSetting("announce"),
                PcMeKnown);
            btnAnnounceTxt = UIFactory.GetButtonText(btnAnnounce);
            // Card trading (v1.41.0, V8 2.1/6.1): after the announcements row.
            // Shown only while /pc/me's settings carry trades_open (F3), which
            // PaintTradesRow decides on every settings repaint; hidden until then.
            // Its value is known only while the key is present: an answer without
            // it (a server before the trading schema) is not OFF.
            btnTrades = NativeUI.SettingsSwitch(parent, "SPcTrd",
                I18n.Tr("Other players can send you card-for-card trade proposals. Nothing moves until you accept. Turning this off ends your open proposals."),
                () => ApiClient.CachedPcMe != null && ApiClient.CachedPcMe.has_trades_open && ApiClient.CachedPcMe.trades_open,
                () => ToggleSetting("trades_open"),
                () => ApiClient.CachedPcMe != null && ApiClient.CachedPcMe.has_trades_open);
            btnTradesTxt = UIFactory.GetButtonText(btnTrades);
            tradesRowGroup = btnTrades;   // the settings page's row itself is what gets hidden
            tradesRowSig = null;
            TradesRowVisible(false);
            btnPreset = NativeUI.SettingsDropdown(parent, "SPcPre",
                I18n.Tr("Which character your picture shows: Follow uses the one you have selected in the character menu, or pin a saved preset. The preview below is what your card will show."),
                PresetOptionIds, () => PortraitRender.CurrentPreset().ToString(System.Globalization.CultureInfo.InvariantCulture),
                id => { SetPreset(ParsePresetId(id)); });
            btnPresetTxt = UIFactory.GetButtonText(btnPreset);
            // Dance cards (design S5.8): the dance the card performs, after the
            // preset row. Shown only while /pc/me carries the dance keys (a
            // server with dance cards), which RefreshDanceRow decides on every
            // settings repaint; hidden until then. A pick is a pending choice
            // (SetDance) that MaybeSendDance sends; nothing is stored here.
            btnDance = NativeUI.SettingsDropdown(parent, "SPcDnc",
                I18n.Tr("The dance your card performs: it plays once each time your card is shown in a binder or a pack, drawn from your own character on this PC. Pick one you own; None keeps your card still."),
                DanceOptionIds, DanceCurrentId, id => { SetDance(ParseDanceId(id)); });
            btnDanceTxt = UIFactory.GetButtonText(btnDance);
            btnDance.SetActive(false);   // the settings page's row itself; shown once /pc/me says the server has dance cards
        }

        /// <summary>Item 13: the Player Cards texts that are not rows -- the
        /// block's explainer, the preset preview and the renderer's note --
        /// built into the settings pane (NativeUI's SetDetail), where they
        /// show beside the rows they explain. <paramref name="infoParent"/>
        /// takes the explainer, <paramref name="previewParent"/> the preview
        /// row and the note (the pane's SDetPrev slot).</summary>
        internal static GameObject BuildSettingsPaneExtras(Transform infoParent, Transform previewParent)
        {
            var info = UIFactory.CreateText("SPcInfo", infoParent,
                "Other players can pull, collect and trade a card of you showing your name, rank title, rating and ranked record - the same things the leaderboard shows. Its picture is your Steam profile picture until this PC has sent your in-game character - the same body, face, colour and effect you play with, drawn here and sent once. Deleting your data (below) removes every card of you from every binder.",
                13f, C_DIM, sizeDelta: new Vector2(700, 36));
            // wrap + auto height, the Info body's shape: CreateText defaults to a
            // single Truncate line, and this caption is longer than the column
            UIFactory.SetWordWrap(info, true); UIFactory.SetTextAutoHeight(info, 36f);
            UIFactory.SetMinH(((Component)info).gameObject, 0f);
            // The preview in its own left-aligned row, so its picture is not
            // centred in a stretched cell ("too far to the right", Sid,
            // 2026-09-13). It shows as soon as a render exists, which the
            // Settings tab asks for itself (MaybeTick -> OnTabVisit).
            //
            // Board row 24: the row is the WHOLE card as other players see it
            // -- frame, band, name, title, numbers and picture, drawn by the
            // server (SettingsCardTick) -- in a card-shaped slot, with a line
            // beside it saying which picture is showing and why. The picture
            // fills the slot's own rect (CreatePanel stretches a child and the
            // slot has no layout group), so the card lands edge to edge and the
            // square live picture letterboxes on the slot's dark ground.
            presetPreviewRow = new GameObject("SPcPrevRow");
            presetPreviewRow.transform.SetParent(previewParent, false);
            presetPreviewRow.AddComponent<RectTransform>();
            UIFactory.AddHLG(presetPreviewRow, spacing: 12, forceExpandW: false, forceExpandH: false);
            UIFactory.SetHLGChildAlignMiddle(presetPreviewRow);
            UIFactory.AddLE(presetPreviewRow, prefH: SETTINGS_CARD_H, minH: SETTINGS_CARD_H, flexH: 0);
            var slot = UIFactory.CreatePanel("SPcCard", presetPreviewRow.transform, C_CARD);
            UIFactory.AddLE(slot, prefW: SETTINGS_CARD_W, minW: SETTINGS_CARD_W, prefH: SETTINGS_CARD_H, minH: SETTINGS_CARD_H, flexW: 0, flexH: 0);
            presetPreview = UIFactory.CreatePanel("SPcPrev", slot.transform, C_CARD);
            PlayerCardFaces.SetFace(presetPreview, null);
            settingsCardBound = null;
            txtSettingsCardCap = UIFactory.CreateText("SPcCardCap", presetPreviewRow.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(SETTINGS_CAP_W, 60));
            UIFactory.SetWordWrap(txtSettingsCardCap, true);
            var capGO = (txtSettingsCardCap as Component)?.gameObject;
            if (capGO != null) UIFactory.AddLE(capGO, prefW: SETTINGS_CAP_W, minW: SETTINGS_CAP_W, flexW: 0);
            presetPreviewRow.SetActive(false);
            // The renderer's last word (rendered / uploading / picture current /
            // why it refused), the diagnostic the picture row used to carry.
            txtPicNote = UIFactory.CreateText("SPcPicN", previewParent, "", 12f, C_DIM, UIFactory.AlignMidLeft, sizeDelta: new Vector2(700, 16));
            return ((Component)info).gameObject;
        }

        /// <summary>The preset slots a player can pick: Follow (-1) and every
        /// AUTHORABLE slot (bug #370: PresetSlotCount, not the array length).</summary>
        private static string[] PresetOptionIds()
        {
            int slots = PortraitRender.PresetSlotCount();
            var ids = new string[slots + 1];
            for (int i = -1; i < slots; i++)
                ids[i + 1] = i.ToString(System.Globalization.CultureInfo.InvariantCulture);
            return ids;
        }

        private static int ParsePresetId(string id)
        {
            int v;
            return int.TryParse(id, System.Globalization.NumberStyles.Integer, System.Globalization.CultureInfo.InvariantCulture, out v) ? v : -1;
        }

        private static string PresetLabel() => PresetLabel(PortraitRender.CurrentPreset());

        /// <summary>Item 13: the label of a GIVEN slot index, so the settings
        /// pane can render the recommended value (Follow, -1) without it being
        /// the live one. v is the slot INDEX; players count slots from one.</summary>
        internal static string PresetLabel(int v)
        {
            return v < 0 ? I18n.Tr("Follow my character") : I18n.TrF("Preset {0}", v + 1);
        }

        /// <summary>Follow → 1 → … → the last AUTHORABLE slot → Follow. Local only (the
        /// picture itself is what reaches the server), debounced by the renderer.
        ///
        /// <para>The upper bound is <see cref="PortraitRender.PresetSlotCount"/>, not
        /// <c>playerFaces.Length</c> (bug #370): the array holds ten entries but the
        /// character creator only lets you fill the first eight, and the two that cannot
        /// be filled used to be offered here and rendered an empty face.</para></summary>
        private static void CyclePreset()
        {
            try
            {
                var cfg = Plugin.PortraitPreset;
                if (cfg == null) return;
                // -1 → 0 → … → slots-1 → -1, over slots+1 states.
                int slots = PortraitRender.PresetSlotCount();
                SetPreset(((Mathf.Clamp(cfg.Value, -1, slots - 1) + 2) % (slots + 1)) - 1);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PC] preset cycle threw: {ex.Message}"); }
        }

        /// <summary>Item 13: the value-taking writer of the preset row (the
        /// settings page's dropdown). The slot is clamped to Follow (-1)
        /// through the last AUTHORABLE slot (bug #370), so an out-of-range id
        /// cannot select an unfillable slot. Local only; the renderer is asked
        /// for a new picture, debounced on its side.</summary>
        internal static void SetPreset(int v)
        {
            try
            {
                var cfg = Plugin.PortraitPreset;
                if (cfg == null) return;
                int slots = PortraitRender.PresetSlotCount();
                int next = Mathf.Clamp(v, -1, slots - 1);
                if (next == cfg.Value) return;                 // already stored: no refresh request
                cfg.Value = next;
                PortraitRender.RequestRefresh("preset");
                NativeUI.MarkDirty();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PC] preset set threw: {ex.Message}"); }
        }

        /// <summary>Item 13: the server rows' paint as a function of the value
        /// (null = /pc/me has not answered yet), so the settings pane can render
        /// the recommended value through the same literals. There are THREE
        /// server rows, each with its own painter: collection_public
        /// (PaintCollectionPublic), announce (PaintAnnounce) and trades_open
        /// (PaintTrades, the card-trading row SPcTrd that merge pass 1 added).</summary>
        internal static void PaintCollectionPublic(object t, bool? on)
        {
            UIFactory.SetText(t, on == null
                ? "My collection is public: <color=#888>...</color>"
                : on.Value
                    ? "My collection is public: <color=#88FF88>ON</color>"
                    : "My collection is public: <color=#FF9966>OFF</color>");
        }

        internal static void PaintAnnounce(object t, bool? on)
        {
            UIFactory.SetText(t, on == null
                ? "Announce my pulls: <color=#888>...</color>"
                : on.Value
                    ? "Announce my pulls: <color=#88FF88>ON</color>"
                    : "Announce my pulls: <color=#FF9966>OFF</color>");
        }

        /// <summary>The Card trading row's paint as a function of the value
        /// (null = /pc/me has not answered, or answered without trades_open),
        /// the same literals the row showed before the settings page moved.</summary>
        internal static void PaintTrades(object t, bool? on)
        {
            UIFactory.SetText(t, on == null
                ? "Card trading: <color=#888>...</color>"
                : on.Value
                    ? "Card trading: <color=#88FF88>ON</color>"
                    : "Card trading: <color=#FF9966>OFF</color>");
        }

        internal static void PaintPreset(object t, int v)
        {
            UIFactory.SetTextRaw(t, I18n.Tr("Character preset") + ": <color=#CCCCCC>" + PresetLabel(v) + "</color>");
        }

        internal static void RefreshSettingsRows()
        {
            if (btnPublicTxt == null) return;
            var id = LocalId();
            var me = ApiClient.CachedPcMe;
            if (me == null && id != null) ApiClient.FetchPcMe(id);   // throttled inside (10 s)
            PaintCollectionPublic(btnPublicTxt, me == null ? (bool?)null : me.collection_public);
            PaintAnnounce(btnAnnounceTxt, me == null ? (bool?)null : me.announce);
            PaintTrades(btnTradesTxt, me == null || !me.has_trades_open ? (bool?)null : me.trades_open);
            PaintTradesRow(me);
            RefreshDanceRow(me);
            RefreshPictureRows();
        }

        /// <summary>The Card trading row is shown only while /pc/me's settings
        /// carry trades_open (V8 6.1, F3). Three states, never two: /pc/me not
        /// answered yet (hidden, waiting), answered WITH the key (shown, ON or
        /// OFF), answered WITHOUT it - a server before the trading schema
        /// (hidden). Absent is never read as OFF: that would offer a switch the
        /// server refuses.</summary>
        private static void PaintTradesRow(ApiClient.PcMe me)
        {
            string state = me == null ? "unknown" : (me.has_trades_open ? "present" : "absent");
            TradesRowVisible(state == "present");
            string value = state == "present" ? (me.trades_open ? "on" : "off") : "-";
            string sig = state + "|" + value;
            if (sig == tradesRowSig) return;
            tradesRowSig = sig;
            Plugin.Log.LogInfo("[PC-TRADE-SENTINEL] settings-row state=" + state + " value=" + value);
        }

        private static void TradesRowVisible(bool on)
        {
            if (tradesRowGroup != null && tradesRowGroup.activeSelf != on) tradesRowGroup.SetActive(on);
        }

        // -- the dance row (dance cards design S5.8) -----------------------------------

        /// <summary>The dances this player owns that this client can capture,
        /// in the wheel's order; null while the shop list has not been read.</summary>
        private static List<ApiClient.ShopItemData> OwnedDanceItems()
        {
            var items = ApiClient.CachedShopItems;
            if (items == null) return null;
            var list = new List<ApiClient.ShopItemData>();
            foreach (var d in DanceEmotes.Defs)
                foreach (var it in items)
                    if (it != null && it.owned && it.kind == "dance" && string.Equals(it.sku, d.Sku, StringComparison.Ordinal)) { list.Add(it); break; }
            return list;
        }

        private static string DanceItemLabel(long item, ApiClient.PcMe me)
        {
            if (item <= 0) return I18n.Tr("None");
            var items = ApiClient.CachedShopItems;
            if (items != null)
                foreach (var it in items)
                    if (it != null && it.id == item && !string.IsNullOrEmpty(it.name)) return I18n.Tr(it.name);
            if (me != null && item == me.pc_dance_item && !string.IsNullOrEmpty(me.pc_dance_sku))
                foreach (var d in DanceEmotes.Defs)
                    if (d.Sku == me.pc_dance_sku) return I18n.Tr(d.Name);
            return "#" + item.ToString(System.Globalization.CultureInfo.InvariantCulture);
        }

        /// <summary>Shown only when /pc/me carries the dance keys (a server with
        /// dance cards); the label is the pending choice while one is waiting,
        /// else the server's selection. Painted on EVERY settings pass, shown or
        /// not (item 13's T2b paints each key once per pass), as the trading
        /// row is; hidden, it shows the unknown word. The settings page's row
        /// is itself what is hidden (SettingsDropdown returns the row).</summary>
        private static void RefreshDanceRow(ApiClient.PcMe me)
        {
            if (btnDance == null || btnDanceTxt == null) return;
            bool show = me != null && me.dance_supported;
            if (btnDance.activeSelf != show) btnDance.SetActive(show);
            if (!show) { PaintDance(btnDanceTxt, "..."); return; }
            long item = danceChoice >= 0 ? danceChoice : me.pc_dance_item;
            PaintDance(btnDanceTxt, DanceItemLabel(item, me) + (danceChoice >= 0 || danceInFlight ? " ..." : ""));
        }

        /// <summary>The dance row's paint as a function of the label (item 13:
        /// the settings page renders an option's word and the recommended
        /// None through it).</summary>
        internal static void PaintDance(object t, string label)
        {
            UIFactory.SetTextRaw(t, I18n.TrF("Dance on my card: {0}", "<color=#CCCCCC>" + label + "</color>"));
        }

        /// <summary>Item 13: the label of a GIVEN option id (a shop item id,
        /// "0" for None), so the page can name each option and the
        /// recommended value without it being the live one.</summary>
        internal static string DanceOptionLabel(string id)
        {
            return DanceItemLabel(ParseDanceId(id), ApiClient.CachedPcMe);
        }

        private static long ParseDanceId(string id)
        {
            long v;
            return long.TryParse(id, System.Globalization.NumberStyles.Integer, System.Globalization.CultureInfo.InvariantCulture, out v) && v > 0 ? v : 0;
        }

        /// <summary>The dropdown's options: None, then each owned dance this
        /// client can capture, in the wheel's order. Null (the dropdown does
        /// not open) until the selection can be sent: no /pc/me with the dance
        /// keys, no session, or the shop list not read yet, which it asks for.</summary>
        private static string[] DanceOptionIds()
        {
            var id = LocalId(); var me = ApiClient.CachedPcMe;
            if (id == null || me == null || !me.dance_supported) return null;
            if (!SessionReady) { try { CompetitiveUI.ShowNotification(ReasonText("session_required"), C_WARN, 3f); } catch { } return null; }
            var owned = OwnedDanceItems();
            if (owned == null)
            {
                try { ApiClient.FetchShopItems(id); } catch { }
                try { CompetitiveUI.ShowNotification(I18n.Tr("Loading your dances..."), C_LABEL, 2f); } catch { }
                return null;
            }
            var ids = new string[owned.Count + 1];
            ids[0] = "0";
            for (int i = 0; i < owned.Count; i++) ids[i + 1] = owned[i].id.ToString(System.Globalization.CultureInfo.InvariantCulture);
            return ids;
        }

        private static string DanceCurrentId()
        {
            var me = ApiClient.CachedPcMe;
            long cur = danceChoice >= 0 ? danceChoice : (me != null ? me.pc_dance_item : 0);
            return (cur > 0 ? cur : 0).ToString(System.Globalization.CultureInfo.InvariantCulture);
        }

        /// <summary>Item 13: the dance row's writer (the settings page's
        /// dropdown). Only the pending choice moves here; MaybeSendDance sends
        /// it after a 1.5 s pause, so a run of picks costs one selection.
        /// Nothing is written to the config: the selection is the server's
        /// (S2.10). 0 is None.</summary>
        internal static void SetDance(long item)
        {
            var id = LocalId(); var me = ApiClient.CachedPcMe;
            if (id == null || me == null || !me.dance_supported) return;
            if (!SessionReady) { try { CompetitiveUI.ShowNotification(ReasonText("session_required"), C_WARN, 3f); } catch { } return; }
            danceChoice = item > 0 ? item : 0;
            danceChoiceAt = Time.unscaledTime;
            NativeUI.MarkDirty();
        }

        /// <summary>Called on every PlayerCardsUI tick: the pending choice goes
        /// to the selection route once the clicks pause, then /pc/me is read
        /// again (the sku and the motion state) and the picture is checked.</summary>
        private static void MaybeSendDance()
        {
            if (danceChoice < 0) return;
            if (danceInFlight && Time.unscaledTime - danceSentAt < 25f) return;   // past the 20 s transport timeout
            if (Time.unscaledTime - danceChoiceAt < 1.5f) return;
            var id = LocalId(); var me = ApiClient.CachedPcMe;
            if (id == null || me == null || !me.dance_supported) { danceChoice = -1; danceInFlight = false; return; }
            long item = danceChoice;
            if (item == me.pc_dance_item) { danceChoice = -1; NativeUI.MarkDirty(); return; }   // back to where it was: nothing to send
            danceInFlight = true; danceSentAt = Time.unscaledTime;
            int ep = uiEpoch;
            Plugin.Log.LogInfo($"[PC] dance selection -> item {item}");
            ApiClient.PcDanceSelect(id, NewNonce(), item, (ok, resp) =>
            {
                if (ep != uiEpoch) return;   // identity changed meanwhile (c4)
                danceInFlight = false;
                if (danceChoice == item) danceChoice = -1;   // a newer click keeps its own pending choice
                if (!ok)
                {
                    try { CompetitiveUI.ShowNotification(ReasonText(ApiClient.PcErrorCode(resp)), C_WARN, 3f); } catch { }
                    NativeUI.MarkDirty();
                    return;
                }
                ApiClient.FetchPcMe(id, true, (ok2, r2) =>
                {
                    if (ep != uiEpoch) return;
                    try { PortraitRender.OnTabVisit(); } catch { }   // the picture check (S5.8): a dance picture, or the still without one
                    NativeUI.MarkDirty();
                });
                NativeUI.MarkDirty();
            });
        }

        /// <summary>The preset row and its preview are local (the preset is a
        /// config value and the preview this PC's own render), so they refresh
        /// whether or not /pc/me has answered.</summary>
        private static void RefreshPictureRows()
        {
            if (btnPresetTxt == null) return;
            PaintPreset(btnPresetTxt, PortraitRender.CurrentPreset());
            string note = PortraitRender.LastResult;
            UIFactory.SetTextRaw(txtPicNote, string.IsNullOrEmpty(note) ? "" : "(" + note + ")");
            if (presetPreviewRow == null || presetPreview == null) return;
            // The live picture's Sprite follows the renderer's serial, as it
            // always has; a Sprite that is on the slot is taken off BEFORE it
            // is destroyed, so the Image never holds a dead one.
            if (previewShown != PortraitRender.PreviewSerial)
            {
                previewShown = PortraitRender.PreviewSerial;
                var old = previewSprite;
                previewSprite = PlayerCardFaces.SpriteOf(PortraitRender.PreviewTex);
                if (old != null)
                {
                    if (settingsCardBound == old) { PlayerCardFaces.SetFace(presetPreview, null); settingsCardBound = null; }
                    try { UnityEngine.Object.Destroy(old); } catch { }
                }
            }
            Sprite show; string cap;
            SettingsCardView(out show, out cap);
            presetPreviewRow.SetActive(show != null || cap != null);
            if (show != settingsCardBound) { PlayerCardFaces.SetFace(presetPreview, show); settingsCardBound = show; }
            UIFactory.SetTextRaw(txtSettingsCardCap, cap ?? "");
        }

        // -- Board row 24: the Settings full card ------------------------------
        // The slot shows the card the server draws for this player -- the same
        // drawing the Discord /card preview shows, from the portrait the server
        // HOLDS -- because that is what other players see. The one time it is
        // not the truth to show is while a new look is on its way (a preset
        // change still settling, a render that will upload, the upload itself):
        // the server's card is then the OLD picture, so the slot shows the live
        // picture with a pending line, and the upload's answer (which writes the
        // new portrait hash into /pc/me) changes the key below, which fetches
        // the new card.

        /// <summary>What a fetched card is good for: the identity epoch, the
        /// portrait the server holds, and the language its labels are drawn in.
        /// A change to any of them asks the server again.</summary>
        private static string SettingsCardWant(ApiClient.PcMe me)
        {
            return uiEpoch + "|" + (me != null ? me.portrait_hash ?? "" : "") + "|" + (string.IsNullOrEmpty(I18n.Locale) ? "en" : I18n.Locale);
        }

        /// <summary>From MaybeTick while Settings is the current tab (every two
        /// seconds). Asks for the card when the one held is for another key or
        /// five minutes old (the numbers on it move with the daily snapshot and
        /// every ranked result), never before a refusal's retry time, and never
        /// while a new look is on its way (the server would draw the picture it
        /// still holds; the upload's answer changes the key anyway). One fetch
        /// at a time; an answer from before an identity edge commits nothing.
        /// A fetch with no answer 25 s after it was sent is given up (the
        /// other latches' rule, past the 20 s transport timeout): when the
        /// persistent host that ran its coroutine is destroyed and respawned
        /// (Plugin.cs OnDestroy), the coroutine stops and its callback never
        /// runs, so the latch would otherwise hold for the rest of the
        /// session. An answer that does arrive after it was given up commits
        /// nothing: its serial is no longer the latest.</summary>
        private static void SettingsCardTick(string id)
        {
            var me = ApiClient.CachedPcMe;
            if (settingsCardInFlight && Now - settingsCardSentAt > 25f)
            {
                settingsCardInFlight = false;
                settingsCardSerial++;
                Plugin.Log.LogWarning("[PC] settings card: no answer 25 s after the request; given up, asking again");
            }
            if (id == null || me == null || !SessionReady || settingsCardInFlight || presetPreview == null) return;
            if (PortraitRender.LookPending) return;
            string want = SettingsCardWant(me);
            bool stale = want != settingsCardKey || Now - settingsCardAt > 300f;
            if (!stale || Now < settingsCardRetryAt) return;
            settingsCardInFlight = true;
            settingsCardSentAt = Now;
            int ep = uiEpoch, serial = ++settingsCardSerial;
            Plugin.Log.LogInfo($"[PC] settings card: requested (serial {serial})");
            ApiClient.PcFacePreview(id, (ok, data, code) =>
            {
                if (ep != uiEpoch) return;   // identity changed meanwhile (c4)
                if (serial != settingsCardSerial)
                {
                    Plugin.Log.LogInfo($"[PC] settings card: answer to serial {serial} dropped (given up)");
                    return;
                }
                settingsCardInFlight = false;
                Texture2D tex = ok ? PlayerCardFaces.DecodeOwned(data, "card", true) : null;
                if (tex != null)
                {
                    var spr = PlayerCardFaces.SpriteOf(tex);
                    if (spr == null) { try { UnityEngine.Object.Destroy(tex); } catch { } }
                    else
                    {
                        SettingsCardDrop();
                        settingsCardTex = tex; settingsCardSprite = spr;
                        settingsCardKey = want; settingsCardState = SC_CARD; settingsCardRetryAt = 0f;
                        settingsCardAt = Now;
                        Plugin.Log.LogInfo($"[PC] settings card: {tex.width}x{tex.height} ({want})");
                        NativeUI.MarkDirty();
                        return;
                    }
                }
                if (ok || code != 404)
                {
                    // Not drawn, or drawn but not the card size. settingsCardAt
                    // stays the time of the last card DRAWN, so a failed refresh
                    // of a held card leaves it stale and the next try comes at
                    // the retry time, thirty seconds out (asks-b round 2, L3).
                    // A card already held stays up, captioned as not loaded
                    // (SettingsCardView) until a fetch succeeds.
                    settingsCardState = SC_UNAVAILABLE;
                    settingsCardRetryAt = Now + 30f;
                    Plugin.Log.LogWarning($"[PC] settings card: not drawn (HTTP {code}); retry in 30 s");
                }
                else
                {
                    // No row in the pool snapshot in force: there is no card of
                    // this player to show until the next snapshot takes them.
                    SettingsCardDrop();
                    settingsCardKey = want; settingsCardState = SC_NOT_IN_POOL;
                    settingsCardAt = Now;
                    settingsCardRetryAt = Now + 300f;
                    Plugin.Log.LogInfo("[PC] settings card: not in the pool yet");
                }
                NativeUI.MarkDirty();
            });
        }

        /// <summary>The held card, off the slot first and then destroyed.</summary>
        private static void SettingsCardDrop()
        {
            if (settingsCardSprite != null && settingsCardBound == settingsCardSprite)
            {
                if (presetPreview != null) { try { PlayerCardFaces.SetFace(presetPreview, null); } catch { } }
                settingsCardBound = null;
            }
            if (settingsCardSprite != null) { try { UnityEngine.Object.Destroy(settingsCardSprite); } catch { } settingsCardSprite = null; }
            if (settingsCardTex != null) { try { UnityEngine.Object.Destroy(settingsCardTex); } catch { } settingsCardTex = null; }
            settingsCardKey = null; settingsCardState = SC_NONE;
        }

        /// <summary>What the slot shows and the line beside it.
        ///
        /// A new look on its way: the live picture (the held card until a
        /// render exists), with the pending line. Otherwise the server's card
        /// whenever the one held is for the current key -- with a line saying
        /// it could not be loaded when its last refresh failed, or that other
        /// players still see it when the picture on screen differs from
        /// the one the server holds (a render that was not sent; the note below
        /// the row says why). No card for this key: not in the pool, a refused
        /// fetch, or one still on its way, each with its own line, over the
        /// live picture when there is one.</summary>
        private static void SettingsCardView(out Sprite show, out string cap)
        {
            var me = ApiClient.CachedPcMe;
            Sprite live = previewSprite;
            Sprite held = settingsCardSprite;
            if (me == null && ApiClient.PcMeError != null && held == null) { show = live; cap = live != null ? "" : null; return; }
            if (!SessionReady && held == null) { show = live; cap = ReasonText("session_required"); return; }
            if (PortraitRender.LookPending)
            {
                show = live ?? held;
                cap = I18n.Tr("Saving your new picture - your card updates here once it has been sent.");
                return;
            }
            if (held != null && me != null && settingsCardKey == SettingsCardWant(me))
            {
                show = held;
                if (settingsCardState == SC_UNAVAILABLE)
                {
                    // Its last refresh failed (asks-b round 2, L3): the card
                    // on show is the last one drawn, not known to be current,
                    // and the tick asks again at the retry time.
                    cap = I18n.Tr("Your card could not be loaded right now - it is tried again shortly.");
                    return;
                }
                string ld = PortraitRender.PreviewDescriptor;
                bool unsent = live != null && ld != null && ld != (me.portrait_descriptor ?? "");
                cap = unsent
                    ? I18n.Tr("Other players still see this card: your new picture was not sent (the note below says why).")
                    : I18n.Tr("Your card as other players see it.");
                return;
            }
            if (settingsCardState == SC_NOT_IN_POOL)
            {
                show = live;
                cap = I18n.Tr("You are not in the card pool yet, so there is no card to show - this is your picture.");
                return;
            }
            show = live ?? held;
            cap = settingsCardState == SC_UNAVAILABLE && !settingsCardInFlight
                ? I18n.Tr("Your card could not be loaded right now - it is tried again shortly.")
                : I18n.Tr("Loading your card...");
        }

        // Three keys, three branches (V8 6.1, M20): a third key must never read
        // or write the second one's value, which the old two-way form did for
        // every key that was not collection_public.
        private static bool SettingValue(ApiClient.PcMe me, string key)
        {
            if (key == "collection_public") return me.collection_public;
            if (key == "announce") return me.announce;
            return me.trades_open;
        }
        private static void ApplySetting(ApiClient.PcMe me, string key, bool v)
        {
            if (me == null) return;
            if (key == "collection_public") me.collection_public = v;
            else if (key == "announce") me.announce = v;
            else me.trades_open = v;
        }

        private static void ToggleSetting(string key)
        {
            var me = ApiClient.CachedPcMe;
            if (me == null) { var lid = LocalId(); if (lid != null) ApiClient.FetchPcMe(lid, true); return; }
            SetSetting(key, !SettingValue(me, key));
        }

        /// <summary>Item 13: the value-taking writer of the three server rows
        /// (the settings page's switches): collection_public, announce and
        /// trades_open, the three branches of SettingValue and ApplySetting;
        /// only trades_open re-reads the open proposals after a successful
        /// write (OnTradesOpenToggled). A value equal to the cached one
        /// sends nothing. Everything else is the toggle's contract unchanged:
        /// single flight, optimistic, rolled back on failure.</summary>
        internal static void SetSetting(string key, bool value)
        {
            var id = LocalId(); var me = ApiClient.CachedPcMe;
            if (id == null) return;
            if (me == null) { ApiClient.FetchPcMe(id, true); return; }
            if (SettingValue(me, key) == value) { NativeUI.MarkDirty(); return; }
            if (!SessionReady) { try { CompetitiveUI.ShowNotification(ReasonText("session_required"), C_WARN, 3f); } catch { } return; }
            // Single-flight with a 25 s latch (past the 20 s transport timeout,
            // the same rule as the same-cards preference): the value that
            // persists is the one the label shows; a failed write rolls the
            // optimistic flip back.
            if (setInFlight && Now - setAt < 25f) return;
            setInFlight = true; setAt = Now;
            bool before = SettingValue(me, key);
            bool after = value;
            int revision = me.revision;
            ApplySetting(me, key, after);
            NativeUI.MarkDirty();
            Plugin.Log.LogInfo($"[PC] setting {key} -> {(after ? 1 : 0)} (rev {revision})");
            int ep = uiEpoch;
            ApiClient.PcSetSetting(id, NewNonce(), revision, key, after ? 1 : 0, (ok, resp) =>
            {
                if (ep != uiEpoch) return;   // identity changed meanwhile (c4)
                setInFlight = false;
                // switching trading off ends the open proposals (V8 2.1): re-read them
                if (ok && key == "trades_open") OnTradesOpenToggled(id);
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
