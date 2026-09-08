using System;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
using System.Text;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Sept 6 (Sid, Group 4 item b) — in-game mail UI: the F5 Mail body
    /// (inbox / sent / reader / composer; Sept 7 item 1: a popup opened from the
    /// header icon, formerly a tab), the Settings row ("Who can mail me" + the
    /// blocked-sender list), the status-driven toast and the unread count that
    /// feeds the icon badge.
    ///
    /// <para>Mechanics, each the codebase's existing precedent:
    /// uGUI through UIFactory (reflection, #15); text ENTRY is IMGUI drawn over
    /// uGUI anchor panels exactly like CompetitiveUI.DrawCompareSearch — the
    /// anchor reports its live screen rect, the field paints over it, and the
    /// focus flag is reset every draw and set only while the control is drawn
    /// AND focused (so closing F5 clears it by construction, design B-4); the
    /// reader body is a REFLECTED read-only TMP_InputField (selectable +
    /// copyable, design B-L3) with a label + Copy-all fallback that logs the
    /// missing member (#110); player-authored text is escaped at render with
    /// the chat's escape (HomeSan: &lt; → [ , &gt; → ], design B-L1) and the
    /// body components additionally run with richText off.</para></summary>
    internal static class MailUI
    {
        // NativeUI's palette is private; these are the same values.
        private static readonly Color C_PANEL = new Color(0.10f, 0.11f, 0.14f, 0.92f);
        private static readonly Color C_WHITE = Color.white;
        private static readonly Color C_LABEL = new Color(0.7f, 0.7f, 0.75f);
        private static readonly Color C_DIM = new Color(0.5f, 0.5f, 0.55f);
        private static readonly Color C_GOLD = new Color(1f, 0.85f, 0.3f);
        private static readonly Color C_BTN = new Color(0.18f, 0.20f, 0.26f, 0.92f);
        private static readonly Color C_BTNACT = new Color(0.22f, 0.38f, 0.65f, 0.95f);
        private static readonly Color C_ROW = new Color(0.14f, 0.15f, 0.19f, 0.92f);
        private static readonly Color C_ROWUNREAD = new Color(0.17f, 0.21f, 0.30f, 0.95f);
        private static readonly Color C_FIELD = new Color(0.08f, 0.09f, 0.12f, 0.95f);
        private static readonly Color C_SEND = new Color(0.15f, 0.45f, 0.25f, 0.95f);
        private static readonly Color C_DANGER = new Color(0.50f, 0.15f, 0.15f, 0.95f);
        private static readonly Color C_TOAST = new Color(0.6f, 0.85f, 1f);

        private enum View { Inbox, Sent, Reader, Compose }
        private static View view = View.Inbox;

        // ── uGUI refs (rebuilt with the page; BuildTab re-assigns everything) ──
        private static GameObject panelRoot, listRoot, readerRoot, composeRoot, listContent;
        private static GameObject navInbox, navSent, navCompose;
        private static object txtHdrStatus;
        // reader
        private static object txtReaderMeta, txtReaderSubject, txtReaderStatus;
        private static GameObject btnReply, btnReplyAll, btnCopy, btnReport, btnBlock, btnDelete;
        private static object bodyTmp;            // the TMP text that shows the body (field's component, or the fallback label)
        private static object bodyField;          // TMP_InputField when the reflection succeeded
        private static PropertyInfo pBodyFieldText, pTmpText;
        private static GameObject bodyHost;
        // composer
        private static object txtComposeTitle, txtReplyTo, txtReplySubject, txtSubjectCount, txtBodyCount, txtComposeStatus;
        private static GameObject toRow, ccRow, toChips, ccChips, subjectAnchor, subjectLabel, bodyAnchor, btnAddTo, btnAddCc, btnSend;
        // settings
        private static GameObject btnMailFrom, btnBlocked, blockedList;

        // ── list state ──────────────────────────────────────────────────────
        private static readonly List<MailClient.Summary> inboxItems = new List<MailClient.Summary>();
        private static readonly List<MailClient.Summary> sentItems = new List<MailClient.Summary>();
        private static string inboxCursor, sentCursor;
        private static bool inboxLoaded, sentLoaded, listLoading;
        private static string listError;
        private static int listGen, listVersion, listPaintKey = -1;
        private static View listPaintedView = View.Reader;

        // ── reader state ────────────────────────────────────────────────────
        private static MailClient.Message current;
        private static MailClient.Summary readerSummary;
        private static bool readerFromSent, readerLoading;
        private static string readerError;
        private static int readerGen, readerVersion, readerPainted = -1;

        // ── composer state ──────────────────────────────────────────────────
        private static readonly List<MailClient.Person> cTo = new List<MailClient.Person>();
        private static readonly List<MailClient.Person> cCc = new List<MailClient.Person>();
        private static string cSubject = "", cBody = "", cIdem, cStatus = "";
        private static string cReplyToId, cReplyToName, cReplySubject;
        private static bool cReplyAll, cSending;
        private static int cReplyOthers, composeVersion, composePainted = -1, paintedSubjLen = -1, paintedBodyLen = -1;
        private static string cIdemFor;                      // the payload fingerprint cIdem was minted for (review r1 M17)
        private static float sendHoldUntil = -1f;            // realtime clock: the limiter's Retry-After hold (review r1 M14)
        /// <summary>Free-text detail of a report. The wire reason is
        /// "&lt;code&gt;: &lt;detail&gt;", which stays well inside the server's
        /// MAIL_REASON_MAX (test_mail.py pins the two against each other).</summary>
        internal const int REPORT_DETAIL_MAX = 200;

        // ── focus / modal state (read by CompetitiveUI) ─────────────────────
        private static bool fieldFocused, dropFocusPending;
        private const string SUBJ_CTRL = "MailSubjectField", BODY_CTRL = "MailBodyField", REPORT_CTRL = "MailReportField";
        /// <summary>True while an IMGUI text field of this UI has keyboard focus
        /// (composer subject/body, report details). ORed into the chat/hotkey
        /// guards in CompetitiveUI exactly like the search fields (design B-4).</summary>
        public static bool AnyFieldFocused => fieldFocused;
        /// <summary>The report-reason modal is up (joins BackdroplessModalOpen).</summary>
        public static bool ModalOpen => reportOpen;

        private static bool reportOpen, reportSending;
        private static string reportId, reportText = "";
        private static int reportReason;
        private static readonly string[] REPORT_CODES = { "spam", "harassment", "other" };

        // ── status / toast state ────────────────────────────────────────────
        public static int Unread { get; private set; }
        private static bool baselineLoaded;
        private static string lastRevision;                 // null = no baseline yet
        private static DateTime newestSeenUtc = DateTime.MinValue;
        private static string pendingToast;
        private static readonly HashSet<string> toastedIds = new HashSet<string>();
        private static int statusGen;                        // inbox-head fetch generation (review r1 M15)
        private static int pendingToastTries;                // slot refusals of the queued toast (review r1 M16)
        private const int PENDING_TOAST_MAX_TRIES = 36;      // 3 minutes of 5 s ticks outside a match
        private static readonly HashSet<string> readClaims = new HashSet<string>();   // MarkRead in flight, per id (review r1 L4)

        // ── blocked senders (Settings) ──────────────────────────────────────
        private static List<MailClient.Block> blocks;
        private static bool blocksExpanded, blocksLoading;
        private static int blocksVersion, blocksPainted = -1;
        private static string mailFromPending;              // optimistic value while a PUT is in flight

        private static GUIStyle styleField, styleArea, styleHint, styleHintTop, styleModalLabel, styleModalTitle, styleReasonOn, styleReasonOff;
        private static float lastDrawWarnAt = -999f;

        // ═════════════════════════════════════════════════════════════════════
        // Hooks called from NativeUI / CompetitiveUI / MailClient
        // ═════════════════════════════════════════════════════════════════════

        /// <summary>NativeUI.BuildUtilityPopup: the Mail body of the utility
        /// popup (Sept 7 item 1); built once per page build, shown per open.</summary>
        public static GameObject BuildTab(Transform parent)
        {
            // Height budget (impl r1 repair iii). The popup box is sized from
            // the live canvas, h = min(900, canvas.h - 60); a 32:9 window
            // (1920x540 canvas units) gives 480 -> Body 436 (44 px popup
            // header) -> 430 for this root (Body padB 6) -> 410 inside its own
            // padding -> 372 for the active view after the 32 px header row and
            // its 6 px spacing. Each view keeps ONE flexible child (flexH 1,
            // minH <= 120, no prefH) and fixed siblings whose heights plus
            // spacing MUST stay <= 252 (= 372 - 120): reader 180, composer 190,
            // list 0 today. Break the rule and the lower controls render past
            // the box, where a click lands on the backdrop and closes it.
            panelRoot = new GameObject("Mail");
            panelRoot.transform.SetParent(parent, false);
            panelRoot.AddComponent<RectTransform>();
            UIFactory.AddVLG(panelRoot, spacing: 6, padL: 20, padR: 20, padT: 10, padB: 10);
            UIFactory.AddLE(panelRoot, flexH: 1);
            try
            {
                BuildHeader(panelRoot.transform);
                BuildListView(panelRoot.transform);
                BuildReaderView(panelRoot.transform);
                BuildComposerView(panelRoot.transform);
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[MAIL] tab build failed: {ex.GetType().Name}: {ex.Message}");
            }
            listPaintKey = -1; readerPainted = -1; composePainted = -1;
            EnsureSceneHook();
            ApplyView();
            return panelRoot;
        }

        private static bool sceneHooked;
        /// <summary>B-4: a scene change (menu → room, room → menu) releases the
        /// composer's text focus and the report modal, whatever the F5 page does.</summary>
        private static void EnsureSceneHook()
        {
            if (sceneHooked) return;
            sceneHooked = true;
            try
            {
                UnityEngine.SceneManagement.SceneManager.activeSceneChanged += (a, b) => { dropFocusPending = true; reportOpen = false; };
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAIL] scene hook: {ex.Message}"); }
        }

        /// <summary>NativeUI.RefreshCurrentTab (dirty repaint while this tab is current).</summary>
        public static void Refresh()
        {
            if (panelRoot == null) return;
            try
            {
                PaintNav();
                switch (view)
                {
                    case View.Inbox:
                    case View.Sent: PaintList(); break;
                    case View.Reader: PaintReader(); break;
                    case View.Compose: PaintComposer(); break;
                }
                // Bug 230: a paint can spawn fresh buttons, and the popup this
                // body lives in asserts ModalBlockInput — mark them (idempotent).
                NativeUI.MarkPopupChildrenInteractive(panelRoot);
            }
            catch (Exception ex)
            {
                if (Time.unscaledTime - lastDrawWarnAt > 30f)
                {
                    lastDrawWarnAt = Time.unscaledTime;
                    Plugin.Log.LogWarning($"[MAIL] refresh: {ex.GetType().Name}: {ex.Message}");
                }
            }
        }

        /// <summary>Generation of the popup instance (Sept 7 item 1, contract
        /// 7 / 1-3 and impl r1 repair iv): ++ on every open and close. Every
        /// MUTATING request the popup issues — block, delete, report, send /
        /// reply, mark-read — captures it at issue. A completion whose
        /// generation has moved applies its DATA effects only (cached rows,
        /// the unread count, listVersion / blocksVersion, the send hold,
        /// in-flight claims the close path does not reset) and none of its
        /// VIEW effects: no toast, no MarkDirty, no ShowView, no focus drop,
        /// no composer / report state — those belong to the instance that
        /// issued the call. Deferred data reaches a successor on its next
        /// repaint (any MarkDirty, or the status poll's Refresh while the
        /// popup is open). NOT fenced by it: the read fetches (list page,
        /// message body) — they resolve a loading state a successor shows
        /// too, because the view survives a close, and each carries its own
        /// supersession fence (listGen / readerGen / statusGen) — and the
        /// Settings row's own requests (mail-from, blocked-list fetch,
        /// unblock): their completions belong to that row, and the page-wide
        /// dirty mark they set changes nothing visible in the popup, whose
        /// paints are version-keyed.</summary>
        private static int popupGen;

        /// <summary>NativeUI.OpenUtilityPopup(Mail): status poll + list refresh
        /// on entry (the former tab-entry work).</summary>
        public static void OnPopupOpened()
        {
            popupGen++;
            try { MailClient.PollNow(); } catch { }
            if (view == View.Inbox || view == View.Sent) RefreshList(reset: true);
            NativeUI.MarkDirty();
        }

        /// <summary>NativeUI.CloseUtilityPopup (icon, Escape, backdrop, page
        /// close, host recovery): text focus dropped, report modal closed, the
        /// in-flight flags (reportSending, cSending) reset here — a completion
        /// that lands later sees popupGen moved and leaves them, and every
        /// other view effect, alone (see popupGen) — and both CompetitiveUI
        /// prompts cancelled, so a pending confirm's Yes can never issue a
        /// request after the close. The draft survives — the discard confirm
        /// stays the only path that clears it.</summary>
        public static void OnPopupClosed()
        {
            popupGen++;
            dropFocusPending = true;
            reportOpen = false;
            reportSending = false;
            cSending = false;
            try { CompetitiveUI.CancelPrompts(); } catch { }
        }

        /// <summary>NativeUI.Tick, Escape with the mail popup open: the report
        /// modal is the topmost mail surface — one press closes it alone.</summary>
        public static bool ConsumeEscape()
        {
            if (!reportOpen) return false;
            reportOpen = false;
            dropFocusPending = true;
            return true;
        }

        /// <summary>The popup's title: "Mail" or "Mail (3)" (the icon badge
        /// carries the count itself).</summary>
        public static string TabLabel()
            => Unread > 0 ? I18n.TrF("Mail ({0})", Unread) : I18n.Tr("Mail");

        /// <summary>NativeUI.TeardownOverlaySurfaces: every close path of the F5
        /// page (Esc, F5, match-start auto-close, host recovery) releases the
        /// text focus and the report modal (#369: one shared teardown list).</summary>
        public static void OnOverlayClosed()
        {
            dropFocusPending = true;
            reportOpen = false;
        }

        /// <summary>CompetitiveUI.DrawUI: the composer's IMGUI fields (over
        /// their uGUI anchors) and the report modal. First statement resets the
        /// focus flag, so a frame in which nothing is drawn reports no focus.</summary>
        public static void DrawImgui()
        {
            fieldFocused = false;
            try
            {
                if (dropFocusPending)
                {
                    dropFocusPending = false;
                    GUI.FocusControl("");
                    GUIUtility.keyboardControl = 0;
                }
                if (!NativeUI.IsOpen) { reportOpen = false; return; }
                if (reportOpen) { DrawReportModal(); return; }
                if (!NativeUI.UtilityPopupIs(NativeUI.UtilKind.Mail) || view != View.Compose) return;
                if (composeRoot == null || !composeRoot.activeInHierarchy) return;
                // A picker/prompt or a confirm over the composer owns the keyboard;
                // do not paint (or steal focus back) underneath it — this draw
                // runs AFTER DrawConfirm in CompetitiveUI.DrawUI (contract 7 / 1-1b).
                if (CompetitiveUI.ArtistPromptOpen || CompetitiveUI.ConfirmOpen) return;
                DrawComposerFields();
            }
            catch (Exception ex)
            {
                if (Time.unscaledTime - lastDrawWarnAt > 30f)
                {
                    lastDrawWarnAt = Time.unscaledTime;
                    Plugin.Log.LogWarning($"[MAIL] draw: {ex.GetType().Name}: {ex.Message}");
                }
            }
        }

        /// <summary>MailClient status poll result (design B-6). The unread count
        /// repaints the tab label; a REVISION change (not a count change) fetches
        /// inbox page 1 and toasts the newest message once, and only when it is
        /// newer than anything this install has already listed — so a delete
        /// that moves the revision back to an older message stays silent. The
        /// persisted baseline advances to the new revision only once that fetch
        /// has SUCCEEDED (review r1 M15): a timed-out fetch leaves it where it
        /// was, so the next poll carrying the same revision tries again instead
        /// of the toast edge being consumed by the failure.</summary>
        public static void OnStatus(MailClient.Status st)
        {
            if (st == null) return;
            if (st.unread != Unread) { Unread = Math.Max(0, st.unread); NativeUI.MarkDirty(); }
            try { NativeUI.RefreshUtilityStrip(); } catch { }                       // Sept 7 item 1: the icon badge
            if (NativeUI.UtilityPopupIs(NativeUI.UtilKind.Mail)) Refresh();
            if (!baselineLoaded) LoadBaseline();
            string rev = st.revision ?? "";
            if (rev == (lastRevision ?? "")) return;
            if (lastRevision == null || rev.Length == 0 || st.unread <= 0)
            {
                // First poll on this install (baseline only), or a change with
                // nothing unread to announce: nothing is fetched, so the
                // baseline moves at once.
                lastRevision = rev;
                SaveBaseline();
                return;
            }
            int gen = ++statusGen;
            MailClient.FetchInbox(null, (ok, page, err) =>
            {
                if (gen != statusGen) return;              // a newer poll owns the edge
                if (!ok || page == null) return;           // baseline untouched: retried on the next poll
                lastRevision = rev;
                SaveBaseline();
                if (page.items.Count == 0) return;
                // Refresh the inbox list with the fresh head (dedupe against the loaded tail).
                MergeInboxHead(page);
                var newest = page.items[0];
                DateTime created = ParseUtc(newest.createdAt);
                if (created != DateTime.MinValue && created <= newestSeenUtc) return;
                NoteNewestSeen(page.items);
                if (!newest.IsUnread || toastedIds.Contains(newest.id)) return;
                toastedIds.Add(newest.id);
                string who = newest.sender != null ? newest.sender.name : "?";
                pendingToast = I18n.TrF("New mail from {0}: {1}", San(Trunc(who, 24)), San(Trunc(OneLine(newest.subject), 60)));
                pendingToastTries = 0;
                TickPending();
            });
        }

        /// <summary>Called every 5 s from the status loop (and after a toast is
        /// queued): nothing shows while a match is being tracked — the toast
        /// waits until the match ends. The queued line is cleared only once the
        /// notification slot has ACCEPTED it (review r1 M16): a critical cue
        /// owning the slot when the match ends refuses it, and it is offered
        /// again on the next tick — bounded, so it cannot linger for ever.</summary>
        public static void TickPending()
        {
            if (pendingToast == null) return;
            if (GameStateWatcher.IsTracking) return;
            bool wanted = true;
            try { wanted = Plugin.ShowNotifications.Value; } catch { }
            if (!wanted) { pendingToast = null; pendingToastTries = 0; return; }   // toasts are off: nothing to wait for
            bool shown = false;
            try { shown = CompetitiveUI.ShowNotification(pendingToast, C_TOAST, 7f); } catch { }
            if (!shown)
            {
                if (++pendingToastTries < PENDING_TOAST_MAX_TRIES) return;
                Plugin.Log.LogInfo("[MAIL] toast dropped after " + pendingToastTries + " refused attempts");
            }
            pendingToast = null;
            pendingToastTries = 0;
            if (shown) PlayMailSound();
        }

        // ═════════════════════════════════════════════════════════════════════
        // Builders
        // ═════════════════════════════════════════════════════════════════════

        private static void BuildHeader(Transform parent)
        {
            var hdr = Row(parent, "MailHdr", 32, 10);
            var mailTitle = UIFactory.CreateText("MailTitle", hdr.transform, "Mail", 22f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(110, 30));
            // Sept 7 item 1: the page lives inside the utility popup, whose header already
            // carries TabLabel() ("Mail" / "Mail (N)"); the in-body title would repeat it,
            // so it is built (the row keeps its layout) and hidden.
            ((Component)mailTitle).gameObject.SetActive(false);
            navInbox = Btn(hdr.transform, "MailNavInbox", I18n.Tr("Inbox"), () => ShowView(View.Inbox), 150, 26);
            navSent = Btn(hdr.transform, "MailNavSent", I18n.Tr("Sent"), () => ShowView(View.Sent), 110, 26);
            navCompose = Btn(hdr.transform, "MailNavNew", I18n.Tr("New message"), () => OpenCompose(), 160, 26);
            txtHdrStatus = UIFactory.CreateText("MailHdrStatus", hdr.transform, "", 13f, C_LABEL, UIFactory.AlignMidRight, sizeDelta: new Vector2(300, 26));
            UIFactory.SetFlexW(((Component)txtHdrStatus).gameObject, 1);
            UIFactory.FitOneLine(txtHdrStatus);
        }

        private static void BuildListView(Transform parent)
        {
            listRoot = new GameObject("MailList");
            listRoot.transform.SetParent(parent, false);
            listRoot.AddComponent<RectTransform>();
            UIFactory.AddVLG(listRoot, spacing: 4);
            UIFactory.AddLE(listRoot, flexH: 1);
            var sv = UIFactory.CreateScrollView("MailListSV", listRoot.transform, spacing: 3);
            UIFactory.AddLE(sv.scrollGO, flexH: 1);
            listContent = sv.content;
        }

        private static void BuildReaderView(Transform parent)
        {
            readerRoot = new GameObject("MailReader");
            readerRoot.transform.SetParent(parent, false);
            readerRoot.AddComponent<RectTransform>();
            UIFactory.AddVLG(readerRoot, spacing: 6);
            UIFactory.AddLE(readerRoot, flexH: 1);

            var actions = Row(readerRoot.transform, "MailRdActions", 30, 6);
            Btn(actions.transform, "MailRdBack", I18n.Tr("Back"), () => ShowView(readerFromSent ? View.Sent : View.Inbox), 90, 26);
            btnReply = Btn(actions.transform, "MailRdReply", I18n.Tr("Reply"), () => { if (current != null) OpenReply(current, false); }, 100, 26);
            btnReplyAll = Btn(actions.transform, "MailRdReplyAll", I18n.Tr("Reply all"), () => { if (current != null) OpenReply(current, true); }, 110, 26);
            btnCopy = Btn(actions.transform, "MailRdCopy", I18n.Tr("Copy"), CopyCurrent, 90, 26);
            btnReport = Btn(actions.transform, "MailRdReport", I18n.Tr("Report"), () => { if (current != null) OpenReport(current); }, 100, 26);
            btnBlock = Btn(actions.transform, "MailRdBlock", I18n.Tr("Block sender"), BlockCurrentSender, 140, 26);
            btnDelete = Btn(actions.transform, "MailRdDelete", I18n.Tr("Delete"), DeleteCurrent, 100, 26, C_DANGER);

            txtReaderMeta = UIFactory.CreateText("MailRdMeta", readerRoot.transform, "", 13f, C_LABEL, UIFactory.AlignTopLeft, sizeDelta: new Vector2(1000, 74));
            UIFactory.SetWordWrap(txtReaderMeta, true);
            txtReaderSubject = UIFactory.CreateText("MailRdSubject", readerRoot.transform, "", 17f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(1000, 30));
            UIFactory.FitOneLine(txtReaderSubject);
            txtReaderStatus = UIFactory.CreateText("MailRdStatus", readerRoot.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(1000, 22));
            UIFactory.FitOneLine(txtReaderStatus);
            BuildReaderBody(readerRoot.transform);
        }

        /// <summary>Design B-L3: the body is a reflected READ-ONLY TMP_InputField
        /// (selectable, Ctrl+C works, no caret edits). Every reflective step is
        /// checked; on the first missing member the whole thing falls back to a
        /// wrapping label + the Copy button, and the log names the member.</summary>
        private static void BuildReaderBody(Transform parent)
        {
            bodyField = null; pBodyFieldText = null; bodyTmp = null;
            GameObject host = null;
            try
            {
                host = UIFactory.CreatePanel("MailBodyHost", parent, C_FIELD);
                // Repair iii: the reader's ONE flexible child (its siblings are
                // fixed rows) — no prefH, minH 120, flexH 1 — so the body takes
                // whatever the box leaves and the view never outgrows the popup
                // on a wide (32:9) canvas. See the budget note in BuildTab.
                UIFactory.AddLE(host, minH: 120, flexW: 1, flexH: 1);
                host.SetActive(false);                       // configure before the component's OnEnable runs
                var vp = new GameObject("Viewport");
                vp.transform.SetParent(host.transform, false);
                var vpRT = vp.AddComponent<RectTransform>();
                vpRT.anchorMin = Vector2.zero; vpRT.anchorMax = Vector2.one;
                vpRT.offsetMin = new Vector2(10, 8); vpRT.offsetMax = new Vector2(-10, -8);
                if (UIFactory.tRectMask2D != null) vp.AddComponent(UIFactory.tRectMask2D);
                var txt = UIFactory.CreateText("Text", vp.transform, "", 14f, C_WHITE, UIFactory.AlignTopLeft, sizeDelta: Vector2.zero, richText: false);
                var txtC = txt as Component;
                if (txtC == null) throw new MissingMemberException("TextMeshProUGUI");
                var le = UIFactory.tLE != null ? txtC.gameObject.GetComponent(UIFactory.tLE) : null;
                if (le != null) UnityEngine.Object.Destroy(le);
                var tRT = txtC.gameObject.GetComponent<RectTransform>();
                tRT.anchorMin = Vector2.zero; tRT.anchorMax = Vector2.one;
                tRT.offsetMin = Vector2.zero; tRT.offsetMax = Vector2.zero; tRT.pivot = new Vector2(0.5f, 1f);
                UIFactory.SetWordWrap(txt, true);
                UIFactory.SetOverflowMode(txt, 0);
                Type tIF = txt.GetType().Assembly.GetType("TMPro.TMP_InputField");
                if (tIF == null) throw new MissingMemberException("TMPro.TMP_InputField");
                var field = host.AddComponent(tIF);
                SetProp(field, "textViewport", vpRT);
                SetProp(field, "textComponent", txt);
                SetProp(field, "readOnly", true);
                SetProp(field, "richText", false);
                SetEnumProp(field, "lineType", "MultiLineNewline");
                SetProp(field, "characterLimit", 0);
                SetProp(field, "interactable", true);
                TrySetProp(field, "onFocusSelectAll", false);
                TrySetProp(field, "restoreOriginalTextOnEscape", false);
                TrySetProp(field, "scrollSensitivity", 3f);
                // Keep the field out of uGUI keyboard/gamepad navigation: it must never
                // become the EventSystem's nav-selected object behind the page (Aug 30 r2 class).
                try
                {
                    var navProp = tIF.GetProperty("navigation", BindingFlags.Public | BindingFlags.Instance);
                    object nav = navProp?.GetValue(field);
                    var modeProp = nav?.GetType().GetProperty("mode", BindingFlags.Public | BindingFlags.Instance);
                    if (navProp != null && nav != null && modeProp != null)
                    {
                        modeProp.SetValue(nav, Enum.ToObject(modeProp.PropertyType, 0));   // Navigation.Mode.None
                        navProp.SetValue(field, nav);
                    }
                }
                catch { }
                pBodyFieldText = tIF.GetProperty("text", BindingFlags.Public | BindingFlags.Instance);
                if (pBodyFieldText == null || !pBodyFieldText.CanWrite) throw new MissingMemberException("TMP_InputField.text");
                bodyField = field; bodyTmp = txt; bodyHost = host;
                host.SetActive(true);
                Plugin.Log.LogInfo("[MAIL] reader body: read-only TMP_InputField (select + copy)");
                return;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[MAIL] read-only input field unavailable ({ex.GetType().Name}: {ex.Message}) - falling back to a label + Copy");
                if (host != null) { host.SetActive(false); UnityEngine.Object.Destroy(host); }
                bodyField = null; pBodyFieldText = null; bodyTmp = null;
            }
            // Fallback: scroll view + wrapping label (richText off so tags stay literal).
            var fb = UIFactory.CreatePanel("MailBodyHostFb", parent, C_FIELD);
            UIFactory.AddLE(fb, minH: 120, flexW: 1, flexH: 1);   // same shape as the field host above (repair iii)
            var sv = UIFactory.CreateScrollView("MailBodySV", fb.transform, spacing: 0);
            var lbl = UIFactory.CreateText("MailBodyLbl", sv.content.transform, "", 14f, C_WHITE, UIFactory.AlignTopLeft, sizeDelta: new Vector2(900, 40), richText: false);
            UIFactory.SetWordWrap(lbl, true);
            UIFactory.SetOverflowMode(lbl, 0);
            UIFactory.SetTextAutoHeight(lbl, 40f);
            bodyTmp = lbl; bodyHost = fb;
        }

        private static void BuildComposerView(Transform parent)
        {
            composeRoot = new GameObject("MailCompose");
            composeRoot.transform.SetParent(parent, false);
            composeRoot.AddComponent<RectTransform>();
            UIFactory.AddVLG(composeRoot, spacing: 6);
            UIFactory.AddLE(composeRoot, flexH: 1);

            txtComposeTitle = UIFactory.CreateText("MailCpTitle", composeRoot.transform, "New message", 17f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(1000, 28));
            UIFactory.FitOneLine(txtComposeTitle);

            // Reply mode: one line names the addressee(s) (the server derives them, design B-9).
            txtReplyTo = UIFactory.CreateText("MailCpReplyTo", composeRoot.transform, "", 14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(1000, 24));
            UIFactory.FitOneLine(txtReplyTo);

            toRow = Row(composeRoot.transform, "MailCpTo", 24, 6);
            UIFactory.CreateText("MailCpToL", toRow.transform, "To", 14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(70, 24));
            toChips = ChipsBox(toRow.transform, "MailCpToChips");
            btnAddTo = Btn(toRow.transform, "MailCpAddTo", I18n.Tr("+ Add"), () => AddRecipient(cTo), 90, 22);

            ccRow = Row(composeRoot.transform, "MailCpCc", 24, 6);
            UIFactory.CreateText("MailCpCcL", ccRow.transform, "Cc", 14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(70, 24));
            ccChips = ChipsBox(ccRow.transform, "MailCpCcChips");
            btnAddCc = Btn(ccRow.transform, "MailCpAddCc", I18n.Tr("+ Add"), () => AddRecipient(cCc), 90, 22);

            var subjRow = Row(composeRoot.transform, "MailCpSubj", 28, 6);
            subjectLabel = ((Component)UIFactory.CreateText("MailCpSubjL", subjRow.transform, "Subject", 14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(70, 28))).gameObject;
            subjectAnchor = Anchor(subjRow.transform, "MailCpSubjAnchor", 28);
            txtReplySubject = UIFactory.CreateText("MailCpReplySubj", subjRow.transform, "", 14f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(600, 28));
            UIFactory.SetFlexW(((Component)txtReplySubject).gameObject, 1);
            UIFactory.FitOneLine(txtReplySubject);
            txtSubjectCount = UIFactory.CreateText("MailCpSubjN", subjRow.transform, "", 12f, C_DIM, UIFactory.AlignMidRight, sizeDelta: new Vector2(90, 28));

            // Repair iii: the composer's ONE flexible child (no prefH, minH 120,
            // flexH 1; every sibling row is fixed — budget note in BuildTab).
            // The IMGUI TextArea is drawn into this anchor's LIVE screen rect
            // each frame (DrawComposerFields -> ScreenRect -> GetWorldCorners),
            // so it follows the anchor wherever the layout puts it.
            bodyAnchor = UIFactory.CreatePanel("MailCpBodyAnchor", composeRoot.transform, C_FIELD);
            UIFactory.AddLE(bodyAnchor, minH: 120, flexW: 1, flexH: 1);
            var countRow = Row(composeRoot.transform, "MailCpCount", 20, 6);
            txtBodyCount = UIFactory.CreateText("MailCpBodyN", countRow.transform, "", 12f, C_DIM, UIFactory.AlignMidRight, sizeDelta: new Vector2(200, 20));
            UIFactory.SetFlexW(((Component)txtBodyCount).gameObject, 1);

            var actions = Row(composeRoot.transform, "MailCpActions", 30, 8);
            btnSend = Btn(actions.transform, "MailCpSend", I18n.Tr("Send"), SendCurrent, 130, 28, C_SEND);
            Btn(actions.transform, "MailCpDiscard", I18n.Tr("Discard"), DiscardCurrent, 110, 28);
            txtComposeStatus = UIFactory.CreateText("MailCpStatus", actions.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(500, 28));
            UIFactory.SetFlexW(((Component)txtComposeStatus).gameObject, 1);
            UIFactory.FitOneLine(txtComposeStatus);
        }

        // ── Settings row (hooked from NativeUI.BuildSettingsTab / RefreshSettings) ──

        /// <summary>The Data &amp; Privacy row: "Who can mail me" (cycles
        /// everyone → people I have played → nobody, PUT /mail/settings) and the
        /// blocked-sender list with Unblock, so both mail preferences sit together.</summary>
        public static void BuildSettingsRow(Transform parent)
        {
            var group = new GameObject("SMail_grp");
            group.transform.SetParent(parent, false);
            group.AddComponent<RectTransform>();
            UIFactory.AddVLG(group, spacing: 3);
            UIFactory.AddLE(group, flexH: 0);
            // Sept 8 item 4: SettingsButton pins the 340 px width behind a flex spacer;
            // a bare Btn inside this VLG was stretched to the full panel width.
            btnMailFrom = NativeUI.SettingsButton(group.transform, "SMailFrom", "", C_WHITE, C_BTN, new Vector2(340, 28), CycleMailFrom);
            UIFactory.CreateText("SMailFrom_d", group.transform, "Who may send you in-game mail. Blocked senders never reach you.", 13f, C_DIM, sizeDelta: new Vector2(700, 18));
            btnBlocked = NativeUI.SettingsButton(group.transform, "SMailBlocked", "", C_WHITE, C_BTN, new Vector2(340, 28), ToggleBlockedList);
            blockedList = new GameObject("SMailBlockedList");
            blockedList.transform.SetParent(group.transform, false);
            blockedList.AddComponent<RectTransform>();
            UIFactory.AddVLG(blockedList, spacing: 2, padL: 12);
            UIFactory.AddLE(blockedList, flexH: 0);
            blockedList.SetActive(false);
            blocksPainted = -1;
        }

        public static void RefreshSettingsRow()
        {
            if (btnMailFrom == null) return;
            string v = mailFromPending ?? MailClient.MailFrom;
            string label;
            switch (v)
            {
                case "played": label = I18n.Tr("Who can mail me: <color=#FFD94D>People I have played</color>"); break;
                case "nobody": label = I18n.Tr("Who can mail me: <color=#FF9966>Nobody</color>"); break;
                default: label = I18n.Tr("Who can mail me: <color=#88FF88>Everyone</color>"); break;
            }
            UIFactory.SetTextRaw(UIFactory.GetButtonText(btnMailFrom), label);
            if (btnBlocked != null)
            {
                string bl = blocks != null
                    ? I18n.TrF("Blocked senders ({0})", blocks.Count) + (blocksExpanded ? "  ^" : "  v")
                    : (blocksLoading ? I18n.Tr("Blocked senders: loading...") : I18n.Tr("Blocked senders: show"));
                UIFactory.SetTextRaw(UIFactory.GetButtonText(btnBlocked), bl);
            }
            if (blockedList == null) return;
            blockedList.SetActive(blocksExpanded);
            if (!blocksExpanded || blocksPainted == blocksVersion) return;
            blocksPainted = blocksVersion;
            KillChildren(blockedList.transform);
            if (blocks == null) return;
            if (blocks.Count == 0)
            {
                UIFactory.CreateText("SMailBlockedNone", blockedList.transform, "No blocked senders.", 13f, C_DIM, sizeDelta: new Vector2(600, 20));
                return;
            }
            for (int i = 0; i < blocks.Count; i++)
            {
                var b = blocks[i];
                var row = Row(blockedList.transform, $"SMailBlk{i}", 26, 8);
                var nm = UIFactory.CreateText($"SMailBlkN{i}", row.transform, "", 13f, C_WHITE, UIFactory.AlignMidLeft, sizeDelta: new Vector2(300, 24));
                UIFactory.SetTextRaw(nm, San(b.name));
                UIFactory.FitOneLine(nm);
                Btn(row.transform, $"SMailBlkU{i}", "Unblock", () => Unblock(b), 100, 24);
            }
        }

        private static void CycleMailFrom()
        {
            if (mailFromPending != null) return;              // a PUT is in flight
            string cur = MailClient.MailFrom;
            int idx = Array.IndexOf(MailClient.MAIL_FROM_VALUES, cur);
            string next = MailClient.MAIL_FROM_VALUES[(idx + 1) % MailClient.MAIL_FROM_VALUES.Length];
            mailFromPending = next;
            NativeUI.MarkDirty();
            MailClient.PutSettings(next, (ok, r) =>
            {
                mailFromPending = null;
                if (ok) MailClient.MailFrom = next;
                else CompetitiveUI.ShowNotification(MailClient.ErrorDetail(r), Color.yellow, 5f);
                NativeUI.MarkDirty();
            });
        }

        private static void ToggleBlockedList()
        {
            blocksExpanded = !blocksExpanded;
            if (blocksExpanded) FetchBlocks();
            NativeUI.MarkDirty();
        }

        private static void FetchBlocks()
        {
            if (blocksLoading) return;
            blocksLoading = true;
            MailClient.FetchBlocks((ok, list, err) =>
            {
                blocksLoading = false;
                if (ok) { blocks = list ?? new List<MailClient.Block>(); blocksVersion++; }
                else CompetitiveUI.ShowNotification(MailClient.ErrorDetail(err), Color.yellow, 5f);
                NativeUI.MarkDirty();
            });
        }

        private static void Unblock(MailClient.Block b)
        {
            MailClient.RemoveBlock(b.steamId, (ok, r) =>
            {
                if (ok)
                {
                    if (blocks != null) blocks.RemoveAll(x => x.steamId == b.steamId);
                    blocksVersion++;
                    CompetitiveUI.ShowNotification(I18n.TrF("Unblocked {0}.", San(b.name)), C_TOAST, 4f);
                }
                else CompetitiveUI.ShowNotification(MailClient.ErrorDetail(r), Color.yellow, 5f);
                NativeUI.MarkDirty();
            });
        }

        // ═════════════════════════════════════════════════════════════════════
        // Painters (run from Refresh; every one is change-gated)
        // ═════════════════════════════════════════════════════════════════════

        private static void PaintNav()
        {
            bool inInbox = view == View.Inbox || (view == View.Reader && !readerFromSent);
            bool inSent = view == View.Sent || (view == View.Reader && readerFromSent);
            if (navInbox != null)
            {
                UIFactory.SetImageColor(navInbox, inInbox ? C_BTNACT : C_BTN);
                UIFactory.SetTextRaw(UIFactory.GetButtonText(navInbox), Unread > 0 ? I18n.TrF("Inbox ({0})", Unread) : I18n.Tr("Inbox"));
            }
            if (navSent != null) UIFactory.SetImageColor(navSent, inSent ? C_BTNACT : C_BTN);
            if (navCompose != null) UIFactory.SetImageColor(navCompose, view == View.Compose ? C_BTNACT : C_BTN);
            if (txtHdrStatus != null)
                UIFactory.SetTextRaw(txtHdrStatus, Unread > 0 ? I18n.TrF("{0} unread", Unread) : "");
        }

        private static void PaintList()
        {
            if (listContent == null) return;
            var items = view == View.Inbox ? inboxItems : sentItems;
            string cursor = view == View.Inbox ? inboxCursor : sentCursor;
            int key = listVersion * 4 + (listLoading ? 1 : 0) + (listError != null ? 2 : 0);
            if (listPaintedView == view && listPaintKey == key) return;
            listPaintedView = view; listPaintKey = key;
            KillChildren(listContent.transform);
            if (items.Count == 0)
            {
                string msg;
                if (listLoading) msg = I18n.Tr("Loading...");
                else if (listError != null) msg = "<color=#FF6666>" + San(listError) + "</color>";
                else msg = view == View.Inbox ? I18n.Tr("No mail yet.") : I18n.Tr("Nothing sent yet.");
                var t = UIFactory.CreateText("MailEmpty", listContent.transform, "", 14f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(800, 30));
                UIFactory.SetTextRaw(t, msg);
                return;
            }
            for (int i = 0; i < items.Count; i++)
            {
                var s = items[i];
                bool unread = view == View.Inbox && s.IsUnread;
                var row = UIFactory.CreateButton($"MailRow{i}", listContent.transform, "", 13f, unread ? C_WHITE : C_LABEL,
                    unread ? C_ROWUNREAD : C_ROW, () => OpenMessage(s, view == View.Sent), new Vector2(0, 30));
                UIFactory.SetFlexW(row, 1);
                var txt = UIFactory.GetButtonText(row);
                UIFactory.SetAlign(txt, UIFactory.AlignMidLeft);
                UIFactory.FitOneLine(txt);
                var tRT = ((Component)txt).GetComponent<RectTransform>();
                if (tRT != null) { tRT.offsetMin = new Vector2(10, 0); tRT.offsetMax = new Vector2(-10, 0); }
                UIFactory.SetTextRaw(txt, RowLabel(s, unread));
            }
            if (listError != null)
            {
                var t = UIFactory.CreateText("MailListErr", listContent.transform, "", 13f, C_LABEL, UIFactory.AlignMidLeft, sizeDelta: new Vector2(800, 24));
                UIFactory.SetTextRaw(t, "<color=#FF6666>" + San(listError) + "</color>");
            }
            if (!string.IsNullOrEmpty(cursor))
            {
                var more = UIFactory.CreateButton("MailMore", listContent.transform, listLoading ? I18n.Tr("Loading...") : I18n.Tr("More"), 13f, C_WHITE, C_BTN,
                    () => { if (!listLoading) RefreshList(reset: false); }, new Vector2(0, 28));
                UIFactory.SetFlexW(more, 1);
            }
        }

        private static string RowLabel(MailClient.Summary s, bool unread)
        {
            var sb = new StringBuilder(160);
            if (unread) sb.Append("<color=#FFD94D>*</color> ");
            if (s.IsBroadcast) sb.Append("<color=#FFD94D>[").Append(I18n.Tr("Announcement")).Append("]</color> ");
            if (view == View.Inbox)
            {
                string name = s.sender != null ? s.sender.name : "?";
                string col = s.sender != null && IsHexColor(s.sender.titleColor) ? s.sender.titleColor : "#FFFFFF";
                sb.Append("<color=").Append(col).Append('>').Append(San(Trunc(name, 22))).Append("</color>");
            }
            else
            {
                sb.Append(I18n.Tr("To:")).Append(' ').Append(San(AddresseeNames(s.addressees, 2)));
            }
            sb.Append("   ");
            if (unread) sb.Append(San(Trunc(OneLine(s.subject), 70)));
            else sb.Append("<color=#AAAAAA>").Append(San(Trunc(OneLine(s.subject), 70))).Append("</color>");
            sb.Append("   <color=#777777>").Append(FmtTime(s.createdAt)).Append("</color>");
            return sb.ToString();
        }

        private static void PaintReader()
        {
            if (readerPainted == readerVersion) return;
            readerPainted = readerVersion;
            var m = current;
            bool has = m != null;
            if (btnReply != null) btnReply.SetActive(has && !readerFromSent && m.sender != null);
            if (btnReplyAll != null) btnReplyAll.SetActive(has && !readerFromSent && m.sender != null && !m.IsBroadcast && (m.to.Count + m.cc.Count) > 1);
            if (btnCopy != null) btnCopy.SetActive(has);
            if (btnReport != null) btnReport.SetActive(has && !readerFromSent && !m.IsBroadcast && m.sender != null);
            if (btnBlock != null) btnBlock.SetActive(has && !readerFromSent && !m.IsBroadcast && m.sender != null && !string.IsNullOrEmpty(m.sender.steamId));
            if (btnDelete != null) btnDelete.SetActive(has);
            if (txtReaderStatus != null)
            {
                string st = readerLoading ? I18n.Tr("Loading...") : (readerError != null ? "<color=#FF6666>" + San(readerError) + "</color>" : "");
                UIFactory.SetTextRaw(txtReaderStatus, st);
                ((Component)txtReaderStatus).gameObject.SetActive(st.Length > 0);
            }
            if (!has)
            {
                if (txtReaderMeta != null) UIFactory.SetTextRaw(txtReaderMeta, "");
                if (txtReaderSubject != null) UIFactory.SetTextRaw(txtReaderSubject, "");
                SetBodyText("");
                return;
            }
            var sb = new StringBuilder(256);
            string from = readerFromSent ? I18n.Tr("You") : (m.sender != null ? San(m.sender.name) : "?");
            string fromCol = !readerFromSent && m.sender != null && IsHexColor(m.sender.titleColor) ? m.sender.titleColor : "#FFFFFF";
            sb.Append(I18n.Tr("From:")).Append(" <color=").Append(fromCol).Append('>').Append(from).Append("</color>\n");
            sb.Append(I18n.Tr("To:")).Append(' ').Append(San(AddresseeNames(m.to, 8))).Append('\n');
            if (m.cc.Count > 0) sb.Append(I18n.Tr("Cc:")).Append(' ').Append(San(AddresseeNames(m.cc, 8))).Append('\n');
            sb.Append("<color=#777777>").Append(FmtTime(m.createdAt)).Append("</color>");
            if (txtReaderMeta != null) UIFactory.SetTextRaw(txtReaderMeta, sb.ToString());
            string subj = San(OneLine(m.subject));
            if (m.IsBroadcast) subj = "<color=#FFD94D>[" + I18n.Tr("Announcement") + "]</color> " + subj;
            if (txtReaderSubject != null) UIFactory.SetTextRaw(txtReaderSubject, subj);
            SetBodyText(San(m.body));
        }

        private static void PaintComposer()
        {
            bool reply = cReplyToId != null;
            if (composePainted != composeVersion)
            {
                composePainted = composeVersion;
                if (txtComposeTitle != null)
                    UIFactory.SetTextRaw(txtComposeTitle, reply ? (cReplyAll ? I18n.Tr("Reply to all") : I18n.Tr("Reply")) : I18n.Tr("New message"));
                if (txtReplyTo != null)
                {
                    ((Component)txtReplyTo).gameObject.SetActive(reply);
                    if (reply)
                        UIFactory.SetTextRaw(txtReplyTo, cReplyOthers > 0
                            ? I18n.TrF("To: {0} and {1} others", San(cReplyToName ?? "?"), cReplyOthers)
                            : I18n.TrF("To: {0}", San(cReplyToName ?? "?")));
                }
                if (toRow != null) toRow.SetActive(!reply);
                if (ccRow != null) ccRow.SetActive(!reply);
                if (subjectAnchor != null) subjectAnchor.SetActive(!reply);
                if (subjectLabel != null) subjectLabel.SetActive(!reply);
                if (txtReplySubject != null)
                {
                    ((Component)txtReplySubject).gameObject.SetActive(reply);
                    if (reply) UIFactory.SetTextRaw(txtReplySubject, San(OneLine(cReplySubject ?? "")));
                }
                if (txtSubjectCount != null) ((Component)txtSubjectCount).gameObject.SetActive(!reply);
                if (!reply) { PaintChips(toChips, cTo); PaintChips(ccChips, cCc); }
                if (txtComposeStatus != null) UIFactory.SetTextRaw(txtComposeStatus, cStatus ?? "");
                if (btnSend != null) UIFactory.SetImageColor(btnSend, cSending ? C_BTN : C_SEND);
                paintedSubjLen = -1; paintedBodyLen = -1;
            }
            PaintCounts();
        }

        private static void PaintChips(GameObject box, List<MailClient.Person> list)
        {
            if (box == null) return;
            KillChildren(box.transform);
            for (int i = 0; i < list.Count; i++)
            {
                var p = list[i];
                var chip = UIFactory.CreateButton($"Chip{i}", box.transform, "", 12f, C_WHITE, C_BTNACT,
                    () => { list.Remove(p); composeVersion++; NativeUI.MarkDirty(); }, new Vector2(list.Count > 5 ? 96 : 120, 22));
                UIFactory.SetTextRaw(UIFactory.GetButtonText(chip), San(Trunc(p.name, list.Count > 5 ? 9 : 12)) + "  x");
                UIFactory.FitOneLine(UIFactory.GetButtonText(chip));
            }
        }

        private static void PaintCounts()
        {
            int sl = (cSubject ?? "").Length, bl = (cBody ?? "").Length;
            if (sl != paintedSubjLen && txtSubjectCount != null)
            {
                paintedSubjLen = sl;
                UIFactory.SetTextRaw(txtSubjectCount, (sl >= MailClient.SUBJECT_MAX ? "<color=#FF6666>" : "") + sl + "/" + MailClient.SUBJECT_MAX + (sl >= MailClient.SUBJECT_MAX ? "</color>" : ""));
            }
            if (bl != paintedBodyLen && txtBodyCount != null)
            {
                paintedBodyLen = bl;
                UIFactory.SetTextRaw(txtBodyCount, (bl >= MailClient.BODY_MAX ? "<color=#FF6666>" : "") + bl + "/" + MailClient.BODY_MAX + (bl >= MailClient.BODY_MAX ? "</color>" : ""));
            }
        }

        // ═════════════════════════════════════════════════════════════════════
        // Views and lists
        // ═════════════════════════════════════════════════════════════════════

        private static void ShowView(View v)
        {
            if (view == View.Compose && v != View.Compose) dropFocusPending = true;   // B-4: focus cleared on view change
            view = v;
            ApplyView();
            if ((v == View.Inbox && !inboxLoaded) || (v == View.Sent && !sentLoaded)) RefreshList(reset: true);
            listPaintKey = -1;
            NativeUI.MarkDirty();
        }

        private static void ApplyView()
        {
            if (listRoot != null) listRoot.SetActive(view == View.Inbox || view == View.Sent);
            if (readerRoot != null) readerRoot.SetActive(view == View.Reader);
            if (composeRoot != null) composeRoot.SetActive(view == View.Compose);
        }

        private static void RefreshList(bool reset)
        {
            bool inbox = view == View.Inbox;
            if (view == View.Reader || view == View.Compose) return;
            string cursor = reset ? null : (inbox ? inboxCursor : sentCursor);
            int gen = ++listGen;
            listLoading = true; listError = null;
            NativeUI.MarkDirty();
            Action<bool, MailClient.Page, string> cb = (ok, page, err) =>
            {
                if (gen != listGen) return;                     // superseded by a newer request
                listLoading = false;
                if (!ok || page == null)
                {
                    listError = MailClient.ErrorDetail(err);
                    listVersion++; NativeUI.MarkDirty();
                    return;
                }
                var items = inbox ? inboxItems : sentItems;
                if (reset) items.Clear();
                foreach (var s in page.items) if (IndexOfId(items, s.id) < 0) items.Add(s);
                if (inbox) { inboxCursor = page.nextCursor; inboxLoaded = true; NoteNewestSeen(items); }
                else { sentCursor = page.nextCursor; sentLoaded = true; }
                listVersion++; NativeUI.MarkDirty();
            };
            if (inbox) MailClient.FetchInbox(cursor, cb); else MailClient.FetchSent(cursor, cb);
        }

        /// <summary>A fresh page 1 (status-driven): make it the head of the loaded
        /// inbox, keeping any older rows already paged in.</summary>
        private static void MergeInboxHead(MailClient.Page page)
        {
            var merged = new List<MailClient.Summary>(page.items);
            foreach (var old in inboxItems) if (IndexOfId(merged, old.id) < 0) merged.Add(old);
            inboxItems.Clear(); inboxItems.AddRange(merged);
            if (!inboxLoaded) inboxCursor = page.nextCursor;
            inboxLoaded = true;
            listVersion++;
            NativeUI.MarkDirty();
        }

        private static void OpenMessage(MailClient.Summary s, bool fromSent)
        {
            if (s == null) return;
            current = null; readerSummary = s; readerFromSent = fromSent;
            readerLoading = true; readerError = null;
            int gen = ++readerGen;
            readerVersion++;
            ShowView(View.Reader);
            MailClient.FetchMessage(s.id, (ok, msg, err) =>
            {
                if (gen != readerGen) return;
                readerLoading = false;
                if (!ok || msg == null) readerError = MailClient.ErrorDetail(err);
                else
                {
                    current = msg;
                    // One MarkRead in flight per message id and one badge
                    // decrement per message (review r1 L4): a row reopened
                    // before its first callback returns takes no second claim,
                    // and the callback decrements only while the captured row
                    // still reads unread (DeleteCurrent marks it read when IT
                    // takes the decrement).
                    if (!fromSent && s.IsUnread && readClaims.Add(s.id))
                    {
                        int rg = popupGen;                        // repair iv: a mutation — fenced at issue
                        MailClient.MarkRead(s.id, (ok2, r2) =>
                        {
                            readClaims.Remove(s.id);              // in-flight claim: the close path does not reset it
                            if (!ok2) return;
                            // Data effects, whichever popup instance is up now.
                            bool dec = s.IsUnread;
                            s.readAt = "read";
                            int at = IndexOfId(inboxItems, s.id);
                            if (at >= 0) inboxItems[at].readAt = "read";
                            if (dec && Unread > 0) Unread--;
                            listVersion++;
                            // The repaint (row style, "Inbox (n)") only for the issuing instance.
                            if (rg == popupGen) NativeUI.MarkDirty();
                        });
                    }
                }
                readerVersion++;
                NativeUI.MarkDirty();
            });
        }

        // ═════════════════════════════════════════════════════════════════════
        // Reader actions
        // ═════════════════════════════════════════════════════════════════════

        private static void CopyCurrent()
        {
            if (current == null) return;
            try
            {
                GUIUtility.systemCopyBuffer = (current.subject ?? "") + "\n\n" + (current.body ?? "");
                CompetitiveUI.ShowNotification(I18n.Tr("Copied to clipboard."), C_TOAST, 3f);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAIL] copy: {ex.Message}"); }
        }

        private static void BlockCurrentSender()
        {
            var m = current;
            if (m == null || m.sender == null || string.IsNullOrEmpty(m.sender.steamId)) return;
            string sid = m.sender.steamId, name = m.sender.name;
            CompetitiveUI.OpenConfirm(I18n.TrF("Block {0}? Their mail will no longer reach you. You can unblock them in Settings.", San(name)), () =>
            {
                int g = popupGen;                              // repair iv: fenced at issue (the confirm's Yes)
                MailClient.AddBlock(sid, (ok, r) =>
                {
                    if (ok)
                    {
                        // Data effects, whichever popup instance is up now: the
                        // Settings row's cache is stale, and an EXPANDED list
                        // refetches at once (a null cache paints it empty). That
                        // fetch's completion is the Settings row's own — its dirty
                        // mark and any error toast are the row's, exactly as when
                        // the list is toggled there.
                        blocks = null; blocksVersion++;
                        if (blocksExpanded) FetchBlocks();
                    }
                    // View effects — the toast and the repaint — only for the instance that issued the block.
                    if (g != popupGen) return;
                    if (ok) CompetitiveUI.ShowNotification(I18n.TrF("Blocked {0}.", San(name)), C_TOAST, 4f);
                    else CompetitiveUI.ShowNotification(MailClient.ErrorDetail(r), Color.yellow, 5f);
                    NativeUI.MarkDirty();
                });
            });
        }

        private static void DeleteCurrent()
        {
            var m = current;
            if (m == null) return;
            string id = m.id;
            var summary = (readerSummary != null && !readerFromSent) ? readerSummary : null;
            CompetitiveUI.OpenConfirm(I18n.Tr("Delete this message?"), () =>
            {
                int delGen = popupGen;                         // contract 7 / 1-3, repair iv: fenced at issue (the confirm's Yes)
                MailClient.Delete(id, (ok, r) =>
                {
                    bool live = delGen == popupGen;
                    if (!ok) { if (live) CompetitiveUI.ShowNotification(MailClient.ErrorDetail(r), Color.yellow, 5f); return; }
                    // Data effects apply whatever the popup did since.
                    RemoveId(inboxItems, id); RemoveId(sentItems, id);
                    // Judged NOW, not at click time: a MarkRead that landed in
                    // between has already taken this row's decrement (review r1 L4).
                    if (summary != null && summary.IsUnread)
                    {
                        summary.readAt = "read";
                        if (Unread > 0) Unread--;
                    }
                    listVersion++;
                    // View effects — leaving the reader, the error toast above,
                    // the repaint — belong to the instance that issued the
                    // delete; a successor picks the list change up on its next repaint.
                    if (!live) return;
                    if (view == View.Reader && current != null && current.id == id) ShowView(readerFromSent ? View.Sent : View.Inbox);
                    NativeUI.MarkDirty();
                });
            });
        }

        private static void OpenReport(MailClient.Message m)
        {
            reportId = m.id; reportReason = 0; reportText = ""; reportSending = false;
            reportOpen = true;
        }

        private static void SubmitReport()
        {
            if (reportSending || string.IsNullOrEmpty(reportId)) return;
            reportSending = true;
            // The subject's character rule applies to the free text too (the
            // server judges a reason like a body: no C0/C1 controls), then the
            // client-side bound. The wire reason "<code>: <detail>" stays well
            // inside the server's MAIL_REASON_MAX (pinned by test_mail.py).
            string detail = CleanSubject(reportText ?? "").Trim();
            if (detail.Length > REPORT_DETAIL_MAX) detail = detail.Substring(0, REPORT_DETAIL_MAX);
            string reason = REPORT_CODES[Mathf.Clamp(reportReason, 0, REPORT_CODES.Length - 1)] + (detail.Length > 0 ? ": " + detail : "");
            int reportGen = popupGen;                          // contract 7 / 1-3, repair iv: fenced at issue
            MailClient.Report(reportId, reason, (ok, r) =>
            {
                // A report has no data effect. Everything here is a view effect
                // — the modal's flags, the focus drop, the toast — and belongs
                // to the instance that issued it; after a close, OnPopupClosed
                // has already reset the flags.
                if (reportGen != popupGen) return;
                reportSending = false; reportOpen = false; dropFocusPending = true;
                if (ok) CompetitiveUI.ShowNotification(I18n.Tr("Reported - thank you. A moderator will review it."), C_TOAST, 5f);
                else CompetitiveUI.ShowNotification(MailClient.ErrorDetail(r), Color.yellow, 5f);
            });
        }

        // ═════════════════════════════════════════════════════════════════════
        // Composer
        // ═════════════════════════════════════════════════════════════════════

        private static void OpenCompose()
        {
            if (cReplyToId != null) ResetComposer();           // a reply draft does not carry into a new message
            if (cIdem == null) cIdem = Guid.NewGuid().ToString();
            composeVersion++;
            ShowView(View.Compose);
        }

        private static void OpenReply(MailClient.Message m, bool all)
        {
            ResetComposer();
            cReplyToId = m.id; cReplyAll = all;
            cReplyToName = m.sender != null ? m.sender.name : "?";
            string subj = OneLine(m.subject ?? "");
            cReplySubject = subj.StartsWith("Re: ", StringComparison.OrdinalIgnoreCase) ? subj : "Re: " + subj;
            cReplyOthers = all ? Math.Max(0, m.to.Count + m.cc.Count - 1) : 0;
            composeVersion++;
            ShowView(View.Compose);
        }

        private static void ResetComposer()
        {
            cTo.Clear(); cCc.Clear();
            cSubject = ""; cBody = ""; cStatus = "";
            cReplyToId = null; cReplyToName = null; cReplySubject = null; cReplyAll = false; cReplyOthers = 0;
            cSending = false;
            cIdem = Guid.NewGuid().ToString(); cIdemFor = null;  // a fresh key; SendCurrent re-mints it whenever the payload changes (review r1 M17)
            composeVersion++;
        }

        private static void AddRecipient(List<MailClient.Person> list)
        {
            CompetitiveUI.OpenPlayerSearch(I18n.Tr("Add recipient"), (sid, name) =>
            {
                if (string.IsNullOrEmpty(sid)) return;
                if (sid == MatchTracker.LocalSteamId) { CompetitiveUI.ShowNotification(I18n.Tr("That's you - pick someone else."), Color.yellow, 3f); return; }
                if (IndexOfPerson(cTo, sid) >= 0 || IndexOfPerson(cCc, sid) >= 0) { CompetitiveUI.ShowNotification(I18n.Tr("Already a recipient."), Color.yellow, 3f); return; }
                list.Add(new MailClient.Person { steamId = sid, name = name ?? sid });
                composeVersion++;
                NativeUI.MarkDirty();
            });
        }

        private static void SendCurrent()
        {
            if (cSending) return;
            float hold = sendHoldUntil - Time.realtimeSinceStartup;
            if (hold > 0f)
            {
                // The limiter's Retry-After is honoured locally (review r1 M14):
                // nothing is dispatched until it has elapsed, and the status line
                // says how long that is.
                SetComposeStatus(MailClient.RateLimitText((int)Math.Ceiling(hold)), true);
                return;
            }
            bool reply = cReplyToId != null;
            string subj = CleanSubject(cSubject).Trim();
            string body = CleanBody(cBody);
            if (!reply && cTo.Count == 0) { SetComposeStatus(I18n.Tr("Add at least one recipient."), true); return; }
            if (!reply && subj.Length == 0) { SetComposeStatus(I18n.Tr("Add a subject."), true); return; }
            if (body.Trim().Length == 0) { SetComposeStatus(I18n.Tr("Write a message first."), true); return; }
            // The idempotency key identifies ONE payload (review r1 M17): a retry
            // of the identical send reuses it (the server answers with the
            // original id), while any edit since the last attempt mints a new
            // key — so a send whose response was lost after the server committed
            // body A can never be replayed under A's key with body B and be
            // reported as "Sent".
            string fp = Fingerprint(reply, subj, body);
            if (cIdem == null || cIdemFor != fp) { cIdem = Guid.NewGuid().ToString(); cIdemFor = fp; }
            cSending = true;
            SetComposeStatus(I18n.Tr("Sending..."), false);
            dropFocusPending = true;
            int sendGen = popupGen;                            // contract 7 / 1-3, repair iv: fenced at issue
            Action<bool, string, string> cb = (ok, id, err) =>
            {
                // Data effects, whichever popup instance is up now: the Sent
                // list is stale after a success; a 429 carries the real wait
                // (review r1 M14) and that hold is the server's Retry-After for
                // this client, so a successor's Send honours it too (on the
                // unscaled clock).
                if (ok) sentLoaded = false;
                else
                {
                    int wait = MailClient.RetryAfterSeconds(err);
                    if (wait > 0) sendHoldUntil = Time.realtimeSinceStartup + wait;
                }
                if (sendGen != popupGen)
                {
                    // The popup closed (and maybe reopened) since this send left:
                    // no view effect — the successor's flags (OnPopupClosed reset
                    // cSending), focus, draft and status line are its own. An
                    // unchanged re-send reuses the same idempotency key, so the
                    // server answers it with the original id.
                    return;
                }
                cSending = false;
                dropFocusPending = true;                        // B-4: focus cleared on completion AND error
                if (ok)
                {
                    // The client never learns about suppression (design B-7): "Sent" is all it can truthfully say.
                    CompetitiveUI.ShowNotification(I18n.Tr("Sent."), new Color(0.6f, 1f, 0.6f), 3f);
                    ResetComposer();
                    ShowView(View.Sent);
                }
                else
                {
                    // The server's refusal, localised (censor hit, recipient cap,
                    // formatting, or the 429's wait); the key stays bound to this
                    // exact payload for an unchanged retry and is re-minted by
                    // any edit.
                    SetComposeStatus(MailClient.ErrorDetail(err), true);
                }
            };
            if (reply) MailClient.Reply(cReplyToId, body, cReplyAll, cIdem, cb);
            else
            {
                var to = new List<string>(); foreach (var p in cTo) to.Add(p.steamId);
                var cc = new List<string>(); foreach (var p in cCc) cc.Add(p.steamId);
                MailClient.Send(to, cc, subj, body, cIdem, cb);
            }
            composeVersion++;
            NativeUI.MarkDirty();
        }

        /// <summary>Everything the server would store for this send: mode,
        /// reply target, recipients in order, subject and body. Two composer
        /// states with the same fingerprint are the same payload and may share
        /// an idempotency key; any difference is a new send.</summary>
        private static string Fingerprint(bool reply, string subj, string body)
        {
            var to = new List<string>(cTo.Count); foreach (var p in cTo) to.Add(p.steamId);
            var cc = new List<string>(cCc.Count); foreach (var p in cCc) cc.Add(p.steamId);
            return FingerprintOf(reply, cReplyToId, cReplyAll, to, cc, subj, body);
        }

        /// <summary>The pure encoding behind <see cref="Fingerprint"/>, reachable
        /// from the launch self-test. Every field is LENGTH-PREFIXED
        /// ("&lt;len&gt;:&lt;field&gt;;") and each list is preceded by its count,
        /// so the encoding is unambiguous: no character inside a field can move a
        /// boundary. (Review r2 M7: the delimiter-joined form let subject "x|y"
        /// with body "z" and subject "x" with body "y|z" share one key, so a lost
        /// response followed by that edit could be reported as sent.)</summary>
        internal static string FingerprintOf(bool reply, string replyTo, bool replyAll,
                                             IList<string> to, IList<string> cc, string subj, string body)
        {
            var sb = new StringBuilder(64 + (subj?.Length ?? 0) + (body?.Length ?? 0));
            FpField(sb, reply ? "R" : "N");
            FpField(sb, replyTo ?? "");
            FpField(sb, replyAll ? "1" : "0");
            FpField(sb, (to?.Count ?? 0).ToString(CultureInfo.InvariantCulture));
            if (to != null) foreach (var s in to) FpField(sb, s ?? "");
            FpField(sb, (cc?.Count ?? 0).ToString(CultureInfo.InvariantCulture));
            if (cc != null) foreach (var s in cc) FpField(sb, s ?? "");
            FpField(sb, subj ?? "");
            FpField(sb, body ?? "");
            return sb.ToString();
        }

        private static void FpField(StringBuilder sb, string v)
        {
            sb.Append(v.Length.ToString(CultureInfo.InvariantCulture)).Append(':').Append(v).Append(';');
        }

        private static void DiscardCurrent()
        {
            bool empty = cTo.Count == 0 && cCc.Count == 0 && (cSubject ?? "").Trim().Length == 0 && (cBody ?? "").Trim().Length == 0;
            if (empty) { ResetComposer(); ShowView(View.Inbox); return; }
            CompetitiveUI.OpenConfirm(I18n.Tr("Discard this draft?"), () => { ResetComposer(); ShowView(View.Inbox); });
        }

        private static void SetComposeStatus(string s, bool error)
        {
            cStatus = error ? "<color=#FF6666>" + San(s) + "</color>" : San(s);
            composeVersion++;
            NativeUI.MarkDirty();
        }

        // ═════════════════════════════════════════════════════════════════════
        // IMGUI: composer fields over their anchors; report modal
        // ═════════════════════════════════════════════════════════════════════

        private static void EnsureStyles()
        {
            if (styleField != null) return;
            styleField = new GUIStyle(GUI.skin.textField) { fontSize = 14, alignment = TextAnchor.MiddleLeft, richText = false };
            styleArea = new GUIStyle(GUI.skin.textArea) { fontSize = 14, alignment = TextAnchor.UpperLeft, wordWrap = true, richText = false };
            styleHint = new GUIStyle(GUI.skin.label) { fontSize = 13, alignment = TextAnchor.MiddleLeft, richText = true };
            styleHintTop = new GUIStyle(GUI.skin.label) { fontSize = 13, alignment = TextAnchor.UpperLeft, richText = true };
            styleModalLabel = new GUIStyle(GUI.skin.label) { fontSize = 14, richText = true, wordWrap = true };
            styleModalTitle = new GUIStyle(GUI.skin.label) { fontSize = 17, fontStyle = FontStyle.Bold };
            styleReasonOn = new GUIStyle(GUI.skin.button) { fontSize = 14, fontStyle = FontStyle.Bold };
            styleReasonOff = new GUIStyle(GUI.skin.button) { fontSize = 14 };
        }

        private static void DrawComposerFields()
        {
            EnsureStyles();
            // Read-only while a send is in flight (review r1 M17): what the
            // player is looking at is exactly what was dispatched.
            bool prevEnabled = GUI.enabled;
            GUI.enabled = prevEnabled && !cSending;
            if (cReplyToId == null && subjectAnchor != null)
            {
                Rect r = ScreenRect(subjectAnchor);
                if (r.width >= 1f && r.height >= 1f)
                {
                    var fr = new Rect(r.x + 2f, r.y + 2f, r.width - 4f, r.height - 4f);
                    GUI.SetNextControlName(SUBJ_CTRL);
                    string next = GUI.TextField(fr, cSubject ?? "", MailClient.SUBJECT_MAX, styleField);
                    if (GUI.GetNameOfFocusedControl() == SUBJ_CTRL) fieldFocused = true;
                    if (string.IsNullOrEmpty(next))
                        GUI.Label(new Rect(fr.x + 6f, fr.y, fr.width - 8f, fr.height), I18n.Tr("<color=#7788AA><i>subject</i></color>"), styleHint);
                    if (next != cSubject) { cSubject = CleanSubject(next); if (cSubject.Length > MailClient.SUBJECT_MAX) cSubject = cSubject.Substring(0, MailClient.SUBJECT_MAX); }
                }
            }
            if (bodyAnchor != null)
            {
                Rect r = ScreenRect(bodyAnchor);
                if (r.width >= 1f && r.height >= 1f)
                {
                    var fr = new Rect(r.x + 2f, r.y + 2f, r.width - 4f, r.height - 4f);
                    GUI.SetNextControlName(BODY_CTRL);
                    string next = GUI.TextArea(fr, cBody ?? "", MailClient.BODY_MAX, styleArea);
                    if (GUI.GetNameOfFocusedControl() == BODY_CTRL) fieldFocused = true;
                    if (string.IsNullOrEmpty(next))
                        GUI.Label(new Rect(fr.x + 6f, fr.y + 4f, fr.width - 8f, 24f), I18n.Tr("<color=#7788AA><i>write your message... (plain text, no formatting)</i></color>"), styleHintTop);
                    if (next != cBody) { cBody = next.Replace("\t", " "); if (cBody.Length > MailClient.BODY_MAX) cBody = cBody.Substring(0, MailClient.BODY_MAX); }
                }
            }
            GUI.enabled = prevEnabled;
            // Live counts repaint without a full dirty cycle (one string set when a length changes).
            PaintCounts();
        }

        private static void DrawReportModal()
        {
            EnsureStyles();
            var ev = Event.current;
            bool cancel = false;
            if (ev != null && ev.type == EventType.KeyDown && ev.keyCode == KeyCode.Escape) { cancel = true; ev.Use(); }
            float w = 560, h = 300;
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            GUI.DrawTexture(new Rect(x - 8, y - 8, w + 16, h + 16), Texture2D.whiteTexture, ScaleMode.StretchToFill, true, 0, new Color(0, 0, 0, 0.94f), 0, 0);
            GUI.Label(new Rect(x + 12, y + 10, w - 24, 26), I18n.Tr("Report this message"), styleModalTitle);
            GUI.Label(new Rect(x + 12, y + 42, w - 24, 44), I18n.Tr("Tell the moderators why. The message is attached to the report as it was sent."), styleModalLabel);
            GUI.Label(new Rect(x + 12, y + 92, w - 24, 22), I18n.Tr("Reason"), styleModalLabel);
            string[] labels = { I18n.Tr("Spam"), I18n.Tr("Harassment"), I18n.TrC("report reason", "Other") };
            float bw = (w - 24 - 16) / 3f;
            for (int i = 0; i < 3; i++)
                if (GUI.Button(new Rect(x + 12 + i * (bw + 8), y + 116, bw, 30), labels[i], reportReason == i ? styleReasonOn : styleReasonOff))
                    reportReason = i;
            GUI.Label(new Rect(x + 12, y + 156, w - 24, 22), I18n.Tr("Details (optional)"), styleModalLabel);
            GUI.SetNextControlName(REPORT_CTRL);
            reportText = GUI.TextField(new Rect(x + 12, y + 180, w - 24, 28), reportText ?? "", REPORT_DETAIL_MAX, styleField);
            if (GUI.GetNameOfFocusedControl() == REPORT_CTRL) fieldFocused = true;
            if (GUI.Button(new Rect(x + 12, y + h - 44, 130, 32), I18n.Tr("Cancel"))) cancel = true;
            GUI.enabled = !reportSending;
            if (GUI.Button(new Rect(x + w - 172, y + h - 44, 160, 32), reportSending ? I18n.Tr("Sending...") : I18n.Tr("Send report"))) SubmitReport();
            GUI.enabled = true;
            if (cancel) { reportOpen = false; dropFocusPending = true; }
        }

        // ═════════════════════════════════════════════════════════════════════
        // Toast baseline + sound
        // ═════════════════════════════════════════════════════════════════════

        private static void LoadBaseline()
        {
            baselineLoaded = true;
            try
            {
                string k = MailClient.PrefKey("Rev");
                lastRevision = PlayerPrefs.HasKey(k) ? PlayerPrefs.GetString(k, "") : null;
                long ticks;
                if (long.TryParse(PlayerPrefs.GetString(MailClient.PrefKey("Seen"), ""), NumberStyles.Integer, CultureInfo.InvariantCulture, out ticks) && ticks > 0)
                    newestSeenUtc = new DateTime(ticks, DateTimeKind.Utc);
            }
            catch { lastRevision = null; }
        }

        private static void SaveBaseline()
        {
            try
            {
                PlayerPrefs.SetString(MailClient.PrefKey("Rev"), lastRevision ?? "");
                PlayerPrefs.SetString(MailClient.PrefKey("Seen"), newestSeenUtc.Ticks.ToString(CultureInfo.InvariantCulture));
            }
            catch { }
        }

        /// <summary>Whatever the inbox has LISTED is "seen" for toast purposes:
        /// only a message newer than this can raise "New mail".</summary>
        private static void NoteNewestSeen(List<MailClient.Summary> items)
        {
            if (items == null) return;
            DateTime max = newestSeenUtc;
            foreach (var s in items) { DateTime d = ParseUtc(s.createdAt); if (d > max) max = d; }
            if (max != newestSeenUtc) { newestSeenUtc = max; SaveBaseline(); }
        }

        private static AudioClip mailClip;
        private static GameObject mailSoundObj;

        /// <summary>Softer two-tone sibling of CompetitiveUI.PlayMatchFoundSound:
        /// lower pitch, shorter, about half the level.</summary>
        private static void PlayMailSound()
        {
            try
            {
                if (mailClip == null)
                {
                    int rate = 44100;
                    float dur = 0.34f;
                    int n = (int)(rate * dur);
                    mailClip = AudioClip.Create("MailTone", n, 1, rate, false);
                    var data = new float[n];
                    int half = n / 2;
                    for (int i = 0; i < n; i++)
                    {
                        float t = (float)i / rate;
                        float freq = i < half ? 523.25f : 659.25f;
                        float pos = i < half ? (float)i / half : (float)(i - half) / (n - half);
                        float env = Mathf.Clamp01(pos * 10f) * Mathf.Clamp01((1f - pos) * 4f);
                        data[i] = Mathf.Sin(2f * Mathf.PI * freq * t) * 0.18f * env;
                    }
                    mailClip.SetData(data, 0);
                }
                if (mailSoundObj == null)
                {
                    mailSoundObj = new GameObject("CR_MailSound");
                    mailSoundObj.hideFlags = HideFlags.HideAndDontSave;
                    UnityEngine.Object.DontDestroyOnLoad(mailSoundObj);
                }
                var src = mailSoundObj.GetComponent<AudioSource>() ?? mailSoundObj.AddComponent<AudioSource>();
                src.clip = mailClip;
                src.volume = 0.5f;
                src.Play();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAIL] tone failed: {ex.Message}"); }
        }

        // ═════════════════════════════════════════════════════════════════════
        // Helpers
        // ═════════════════════════════════════════════════════════════════════

        /// <summary>The chat's escape (NativeUI.HomeSan): tags cannot form, URLs stay inert text.</summary>
        internal static string San(string s)
            => string.IsNullOrEmpty(s) ? "" : s.Replace("<", "[").Replace(">", "]").Replace("\r", "");

        private static string OneLine(string s)
            => string.IsNullOrEmpty(s) ? "" : s.Replace("\r", " ").Replace("\n", " ");

        private static string Trunc(string s, int n)
            => string.IsNullOrEmpty(s) || s.Length <= n ? (s ?? "") : s.Substring(0, Math.Max(1, n - 2)) + "..";

        /// <summary>Subject rule (B-L1): single line, no C0/C1 controls, no U+0085/U+2028/U+2029.</summary>
        private static string CleanSubject(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder(s.Length);
            foreach (char c in s)
            {
                if (c < 0x20 || (c >= 0x7F && c <= 0x9F) || c == '\u2028' || c == '\u2029') sb.Append(' ');
                else sb.Append(c);
            }
            return sb.ToString();
        }

        /// <summary>Body rule (B-L1): CRLF → LF, no other C0/C1 controls.</summary>
        private static string CleanBody(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            s = s.Replace("\r\n", "\n").Replace('\r', '\n').Replace('\t', ' ');
            var sb = new StringBuilder(s.Length);
            foreach (char c in s)
            {
                if (c == '\n') { sb.Append(c); continue; }
                if (c < 0x20 || (c >= 0x7F && c <= 0x9F)) continue;
                sb.Append(c);
            }
            return sb.ToString();
        }

        private static bool IsHexColor(string s)
        {
            if (string.IsNullOrEmpty(s) || s[0] != '#' || (s.Length != 7 && s.Length != 9)) return false;
            for (int i = 1; i < s.Length; i++) if (!Uri.IsHexDigit(s[i])) return false;
            return true;
        }

        private static string AddresseeNames(List<MailClient.Person> people, int max)
        {
            if (people == null || people.Count == 0) return "-";
            var sb = new StringBuilder();
            int n = Math.Min(max, people.Count);
            for (int i = 0; i < n; i++) { if (i > 0) sb.Append(", "); sb.Append(Trunc(people[i].name, 20)); }
            if (people.Count > n) sb.Append(' ').Append(I18n.TrF("+{0} more", people.Count - n));
            return sb.ToString();
        }

        private static DateTime ParseUtc(string iso)
        {
            DateTime d;
            return !string.IsNullOrEmpty(iso) && DateTime.TryParse(iso, CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out d) ? d : DateTime.MinValue;
        }

        private static string FmtTime(string iso)
        {
            DateTime d = ParseUtc(iso);
            if (d == DateTime.MinValue) return "";
            DateTime l = d.ToLocalTime(), now = DateTime.Now;
            string hm = l.ToString("HH:mm", CultureInfo.InvariantCulture);
            if (l.Date == now.Date) return hm;
            if (l.Year == now.Year) return DateFmt.MonthDay(l) + " " + hm;
            return DateFmt.Short(l);
        }

        private static int IndexOfId(List<MailClient.Summary> items, string id)
        {
            for (int i = 0; i < items.Count; i++) if (items[i].id == id) return i;
            return -1;
        }

        private static void RemoveId(List<MailClient.Summary> items, string id)
        {
            int i = IndexOfId(items, id);
            if (i >= 0) items.RemoveAt(i);
        }

        private static int IndexOfPerson(List<MailClient.Person> list, string sid)
        {
            for (int i = 0; i < list.Count; i++) if (list[i].steamId == sid) return i;
            return -1;
        }

        /// <summary>Deactivate first (a raw-poll ClickHandler never runs on an
        /// inactive GO), then destroy (end-of-frame deferred) — #369b.</summary>
        private static void KillChildren(Transform t)
        {
            if (t == null) return;
            for (int i = t.childCount - 1; i >= 0; i--)
            {
                var c = t.GetChild(i).gameObject;
                c.SetActive(false);
                UnityEngine.Object.Destroy(c);
            }
        }

        private static GameObject Row(Transform parent, string name, float h, float spacing)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.AddComponent<RectTransform>();
            UIFactory.AddHLG(go, spacing: spacing, forceExpandW: false, forceExpandH: true);
            UIFactory.AddLE(go, prefH: h, minH: h, flexW: 1, flexH: 0);
            return go;
        }

        private static GameObject ChipsBox(Transform parent, string name)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.AddComponent<RectTransform>();
            UIFactory.AddHLG(go, spacing: 4, forceExpandW: false, forceExpandH: true);
            UIFactory.AddLE(go, prefH: 22, minH: 22, flexW: 1, flexH: 0);
            return go;
        }

        private static GameObject Anchor(Transform parent, string name, float h)
        {
            var go = UIFactory.CreatePanel(name, parent, C_FIELD);
            UIFactory.AddLE(go, prefH: h, minH: h, flexW: 1, flexH: 0);
            return go;
        }

        private static GameObject Btn(Transform parent, string name, string label, UnityEngine.Events.UnityAction onClick, float w, float h, Color? bg = null)
            => UIFactory.CreateButton(name, parent, label, 13f, C_WHITE, bg ?? C_BTN, onClick, new Vector2(w, h));

        /// <summary>IMGUI rect of a uGUI anchor (ScreenSpaceOverlay canvas: world
        /// corners are screen pixels; IMGUI's Y is top-down). Rect.zero when the
        /// anchor is inactive — GetWorldCorners on an inactive RectTransform
        /// still returns stale corners, so the explicit check is load-bearing.</summary>
        private static Rect ScreenRect(GameObject go)
        {
            try
            {
                if (go == null || !go.activeInHierarchy) return new Rect(0, 0, 0, 0);
                var rt = go.GetComponent<RectTransform>();
                if (rt == null) return new Rect(0, 0, 0, 0);
                var c = new Vector3[4]; rt.GetWorldCorners(c);           // 0=BL,1=TL,2=TR,3=BR
                float x = c[0].x, w = c[2].x - c[0].x, h = c[1].y - c[0].y;
                float guiY = Screen.height - c[1].y;
                if (w < 1f || h < 1f) return new Rect(0, 0, 0, 0);
                return new Rect(x, guiY, w, h);
            }
            catch { return new Rect(0, 0, 0, 0); }
        }

        private static void SetBodyText(string s)
        {
            try { UnicodeFallback.EnsureCharacters(s); } catch { }
            if (bodyField != null && pBodyFieldText != null)
            {
                try
                {
                    pBodyFieldText.SetValue(bodyField, s ?? "");
                    // A new message starts at the top: reset the caret and any scroll
                    // offset the previous (longer) body left on the text component.
                    TrySetProp(bodyField, "stringPosition", 0);
                    TrySetProp(bodyField, "caretPosition", 0);
                    var tc = bodyTmp as Component;
                    var rt = tc != null ? tc.GetComponent<RectTransform>() : null;
                    if (rt != null) rt.anchoredPosition = Vector2.zero;
                    return;
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[MAIL] body field set failed ({ex.GetType().Name}) - using the label"); }
            }
            if (bodyTmp == null) return;
            if (pTmpText == null) pTmpText = bodyTmp.GetType().GetProperty("text", BindingFlags.Public | BindingFlags.Instance);
            pTmpText?.SetValue(bodyTmp, s ?? "");           // raw: the label runs with richText off, no bold wrap
        }

        private static void SetProp(object target, string name, object value)
        {
            var p = target.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
            if (p == null || !p.CanWrite) throw new MissingMemberException(target.GetType().Name + "." + name);
            p.SetValue(target, value);
        }

        private static void TrySetProp(object target, string name, object value)
        {
            try { SetProp(target, name, value); } catch { }
        }

        private static void SetEnumProp(object target, string name, string enumMember)
        {
            var p = target.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
            if (p == null || !p.CanWrite) throw new MissingMemberException(target.GetType().Name + "." + name);
            p.SetValue(target, Enum.Parse(p.PropertyType, enumMember));
        }
    }
}
