using System;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
using System.Text;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Item 13 (v1.41.0): the consent row's value-taking writer (design
    /// section 2.1). The row is a switch now, so the writer takes the state
    /// to store rather than flipping whatever is there; the effect is the one
    /// the old toggle had, applied on every call.
    /// </summary>
    internal static class ConsentSetting
    {
        internal static void Set(bool granted)
        {
            if (Plugin.DataConsent == null) return;
            Plugin.DataConsent.Value = granted ? "granted" : "denied";
            ApiClient.OnConsentChanged();
        }
    }

    /// <summary>
    /// Item 13 (v1.41.0, the settings page reorganisation): the page's chrome
    /// and machinery. BuildSettingsTab (NativeUI.cs) builds every row through
    /// the typed constructors below, so the keyset instrument reads the whole
    /// page from that one method; this file owns what the rows are made of:
    /// the sub-tab bar, the list and help columns, the row shell and its
    /// widgets, the paint hook that splits a painted string into the label
    /// column and the control, the help pane and its reset footer, the
    /// keyboard poll, and the self-test behind SCR_SETTINGS_SELFTEST.
    ///
    /// The rows are painted exactly as before: RefreshSettings writes one
    /// whole string per row through UIFactory.SetText / SetTextRaw into the
    /// row's label text. The paint hook recognises those writes by the text
    /// object, splits the string at its first colon outside a tag (the label
    /// half goes to the label column, the value half to the control) and
    /// counts the paint. No catalogue key changes shape.
    /// </summary>
    public static partial class NativeUI
    {
        internal enum SettingsKind { Switch, Segmented, Dropdown, Slider, Action, Disclosure, Destructive }

        /// <summary>One settings row (or, for the delete row, one of its
        /// three buttons; the row itself is the group record "SDR").</summary>
        private sealed class SettingsRowRec
        {
            internal string Key;
            internal SettingsKind Kind;
            internal string Desc;
            internal int Tab = -1;
            internal GameObject Row, Help, Cell;
            internal object Label;
            internal int Paints;
            internal string LastPainted = "", LastLabel = "", LastValue = "";
            // switch
            internal Func<bool> GetBool;
            internal UnityEngine.Events.UnityAction Toggle;
            internal GameObject Track, Knob;
            internal object Word;
            // Round-2 R4: false while the row cannot know its own value (the
            // mail relay before its first status poll, or with no linked
            // Discord); the switch then paints neither on nor off.
            internal Func<bool> Known;
            // segmented / dropdown
            internal string[] Ids;
            internal Func<string[]> IdsF, NamesF;
            internal Func<string> Current;
            internal Action<string> Pick;
            internal string Title;
            internal GameObject[] Opts;
            internal object[] OptTxts;
            internal GameObject Face;
            internal object FaceTxt;
            // slider
            internal float[] Stops;
            internal Func<int> Index;
            internal Action<float> SetStop;
            internal UIFactory.SliderHandle Slider;
            internal object Readout;
            internal int LastIdx = -1;
            // action / disclosure / destructive
            internal UnityEngine.Events.UnityAction Act;
            internal Func<bool> Expanded;
            internal GameObject Glyph;
            internal object GlyphTxt;
            internal GameObject Button;
            internal object ButtonTxt;
            internal Vector2 ButtonSize;
            internal List<SettingsRowRec> Members;
        }

        /// <summary>Reference identity for the text-object registry: a TMP
        /// component's own Equals must never decide which row a write is for.</summary>
        private sealed class SettingsRefEq : IEqualityComparer<object>
        {
            bool IEqualityComparer<object>.Equals(object a, object b) { return ReferenceEquals(a, b); }
            int IEqualityComparer<object>.GetHashCode(object o) { return System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(o); }
        }

        private const int SETTINGS_TABS = 7;
        // The help pane's scroll content spacing: built with it, and A2b's
        // content leg sums the children with it.
        private const float SetDetBodySpacing = 8f;
        private static readonly Color SW_ON = new Color(0.22f, 0.55f, 0.30f, 0.95f);
        private static readonly Color SW_OFF = new Color(0.30f, 0.30f, 0.34f, 0.95f);
        // Round-2 R4: the neutral switch, for a row whose Known is false - a
        // dim track and a dim knob at the centre, so the widget never reads
        // on or off beside a label that says the value is not known.
        private static readonly Color SW_NA = new Color(0.16f, 0.16f, 0.19f, 0.60f);
        private static readonly Color SW_KNOB = new Color(0.92f, 0.92f, 0.95f, 1f);
        private static readonly Color SW_KNOB_NA = new Color(0.50f, 0.50f, 0.54f, 0.85f);

        private static readonly Dictionary<object, SettingsRowRec> settingsRegistry = new Dictionary<object, SettingsRowRec>(new SettingsRefEq());
        private static readonly Dictionary<string, SettingsRowRec> settingsByKey = new Dictionary<string, SettingsRowRec>();
        private static readonly List<SettingsRowRec>[] settingsTabRows = NewSettingsTabRows();
        private static readonly Dictionary<Transform, int> settingsZebraCount = new Dictionary<Transform, int>();
        private static readonly GameObject[] settingsBodies = new GameObject[SETTINGS_TABS];
        private static readonly GameObject[] settingsSubBtns = new GameObject[SETTINGS_TABS];

        /// <summary>The active sub-tab. Static on purpose: it outlives pageGO,
        /// so every rebuild route lands the player back where they were
        /// (ApplyRememberedSubTab at the end of BuildSettingsTab).</summary>
        private static int settingsSubTab;
        /// <summary>The focused row per sub-tab, as an index into that tab's
        /// visible rows (design section 6.2).</summary>
        private static readonly int[] settingsFocusRow = new int[SETTINGS_TABS];
        private static string settingsHoverKey, settingsPinnedKey;
        private static float settingsHoverPollAt, settingsHintPollAt;
        private static bool settingsPaneDirty;

        private static object escBtnTxt, infoOpenTxt, portalTxt;
        private static object settingsDeleteStateTxt;
        private static float settingsDeleteArmedAt = -1f;

        // chrome
        private static GameObject setListHint, setListViewport, settingsColsGO, setListGO;
        private static RectTransform setListContentRT;
        private static GameObject setDetailGO, setDetCurGO, setDetRecGO, setDetDetectedGO, setDetExtrasGO, setDetPrevGO;
        private static GameObject setDetMoreBtn, setResetBtn, setResetConfirmBtn, setResetCancelBtn, setDetSkipGO;
        private static object setDetTitleTxt, setDetCurTxt, setDetRecTxt, setDetReasonTxt, setDetDetectedTxt, setDetBodyTxt;
        private static GameObject setExtraSCS, setExtraSDD, setExtraSDD2, setExtraSDS, setExtraLangNote, setExtraPcInfo;
        private static string settingsMoreKey;

        // reset
        private static bool settingsResetArmed;
        private static int settingsResetDepth;
        private static bool settingsRebuildOwed;

        // capture of a painter's string for a value that is not the live one
        private static object settingsCaptureSentinel;
        private static string settingsCaptureResult;

        // self-test switches (T2b's controls)
        private static bool settingsSelfTestSuppressRaw;
        private static string settingsSelfTestSkipKey;

        // controller edge detector
        private static int settingsAxisX, settingsAxisY;
        private static bool settingsAxisBroken;

        private static List<SettingsRowRec>[] NewSettingsTabRows()
        {
            var a = new List<SettingsRowRec>[SETTINGS_TABS];
            for (int i = 0; i < SETTINGS_TABS; i++) a[i] = new List<SettingsRowRec>();
            return a;
        }

        // ---------------------------------------------------------------
        // Build
        // ---------------------------------------------------------------

        /// <summary>Called first by BuildSettingsTab: every rebuild route
        /// (language, heavy font, catalogue, host recovery, re-parent) starts
        /// from an empty registry, so no row of a destroyed page can be
        /// painted or focused.</summary>
        private static void SettingsBeginBuild()
        {
            settingsBuildGen++;
            UIFactory.PaintHook = SettingsPaintHook;
            settingsRegistry.Clear();
            settingsByKey.Clear();
            settingsZebraCount.Clear();
            for (int i = 0; i < SETTINGS_TABS; i++)
            {
                settingsTabRows[i].Clear();
                settingsBodies[i] = null;
                settingsSubBtns[i] = null;
            }
            settingsHoverKey = null;
            settingsPinnedKey = null;
            settingsResetArmed = false;
            settingsPaneDirty = true;
            escBtnTxt = infoOpenTxt = portalTxt = settingsDeleteStateTxt = null;
            setListHint = setListViewport = settingsColsGO = setListGO = null;
            setListContentRT = null;
            setDetailGO = setDetCurGO = setDetRecGO = setDetDetectedGO = setDetExtrasGO = setDetPrevGO = null;
            setDetMoreBtn = setResetBtn = setResetConfirmBtn = setResetCancelBtn = setDetSkipGO = null;
            setExtraSCS = setExtraSDD = setExtraSDD2 = setExtraSDS = setExtraLangNote = setExtraPcInfo = null;
        }

        /// <summary>The page frame: the sub-tab bar, then the two columns. The
        /// list column's scroll content is returned; BuildSettingsTab puts the
        /// "Settings" root and the seven bodies under it.</summary>
        private static Transform BuildSettingsChrome(GameObject outer)
        {
            // -- sub-tab bar (design section 3.2) --
            var bar = new GameObject("SSubBar");
            bar.transform.SetParent(outer.transform, false);
            bar.AddComponent<RectTransform>();
            UIFactory.AddHLG(bar, spacing: 6, padL: 8, forceExpandW: false, forceExpandH: false);
            UIFactory.SetHLGChildAlignMiddle(bar);
            UIFactory.AddLE(bar, minH: 26, prefH: 26, flexH: 0, flexW: 1);
            for (int i = 0; i < SETTINGS_TABS; i++)
            {
                int idx = i;
                string home = SettingsModel.SubTabHomes[i];
                var b = UIFactory.CreateButton("SSub_" + home, bar.transform, "", 13f, C_WHITE, C_TAB,
                    () => SettingsSwitchSubTab(idx), new Vector2(168, 24));
                UIFactory.SetMinW(b, 168);
                UIFactory.SetTextNoHook(UIFactory.GetButtonText(b), SettingsDescriptors.SubTabLabelTr(home));
                settingsSubBtns[i] = b;
            }
            var barSp = new GameObject("SSubSp");
            barSp.transform.SetParent(bar.transform, false);
            barSp.AddComponent<RectTransform>();
            UIFactory.AddLE(barSp, flexW: 1);
            // The trilingual pointer a lost player scans for (it used to head
            // the language box): it opens Language & menus on the language row.
            var langPtr = UIFactory.CreateButton("SLangL", bar.transform,
                "Language / Idioma / \u042f\u0437\u044b\u043a / \u041c\u043e\u0432\u0430 / Spr\u00e5k", 13f,
                new Color(0.7f, 0.85f, 1f), C_BTN, () => SettingsSelectKey("SLang"), new Vector2(330, 24));
            UIFactory.SetMinW(langPtr, 330);

            // -- the two columns --
            var cols = new GameObject("SettingsCols");
            cols.transform.SetParent(outer.transform, false);
            cols.AddComponent<RectTransform>();
            UIFactory.AddHLG(cols, spacing: 12, padL: 8, padR: 8, forceExpandW: false, forceExpandH: true);
            UIFactory.AddLE(cols, flexH: 1, flexW: 1);
            settingsColsGO = cols;

            var list = UIFactory.CreatePanel("SetList", cols.transform, C_PANEL);
            UIFactory.AddVLG(list, spacing: 0);
            UIFactory.AddLE(list, minW: 1020, prefW: 1020, flexW: 0, flexH: 1);
            setListGO = list;
            var sv = UIFactory.CreateScrollView("SetListSV", list.transform, spacing: 0);
            UIFactory.AddLE(sv.scrollGO, flexH: 1);
            settingsScrollGO = sv.scrollGO;
            setListContentRT = sv.contentRT;
            var vpT = sv.scrollGO.transform.Find("Viewport");
            setListViewport = vpT != null ? vpT.gameObject : null;
            // The mod's own scroll affordance (the CmpScrollHint pattern): no
            // Unity Scrollbar, a hint line that is active only while the
            // active sub-tab's rows overflow the viewport (design A8).
            var hint = UIFactory.CreateText("SetListScrollHint", list.transform,
                "<color=#777><i>hover the panel and scroll for more</i></color>", 12f, C_DIM,
                UIFactory.AlignMidCenter, sizeDelta: new Vector2(1000, 16));
            setListHint = ((Component)hint).gameObject;
            setListHint.SetActive(false);

            var det = UIFactory.CreatePanel("SetDetail", cols.transform, C_PANEL);
            UIFactory.AddVLG(det, spacing: 6, padL: 24, padR: 24, padT: 18, padB: 18);
            UIFactory.AddLE(det, minW: 796, prefW: 796, flexW: 0, flexH: 1);
            setDetailGO = det;
            setDetTitleTxt = UIFactory.CreateText("SetDetTitle", det.transform, "", 22f, C_GOLD,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(748, 32));
            UIFactory.FitOneLine(setDetTitleTxt);
            setDetCurTxt = UIFactory.CreateText("SetDetCur", det.transform, "", 14f, C_LABEL,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(748, 22));
            UIFactory.FitOneLine(setDetCurTxt);
            setDetCurGO = ((Component)setDetCurTxt).gameObject;

            var band = UIFactory.CreatePanel("SetDetRec", det.transform, new Color(0.14f, 0.20f, 0.30f, 0.60f));
            UIFactory.AddVLG(band, spacing: 2, padL: 10, padR: 10, padT: 6, padB: 6);
            UIFactory.AddLE(band, flexH: 0);
            setDetRecGO = band;
            setDetRecTxt = UIFactory.CreateText("SetDetRecTxt", band.transform, "", 14f, C_WHITE,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(728, 22));
            UIFactory.SetWordWrap(setDetRecTxt, true);
            UIFactory.SetOverflowMode(setDetRecTxt, 0);
            UIFactory.SetTextAutoHeight(setDetRecTxt, 22f);
            setDetReasonTxt = UIFactory.CreateText("SetDetReason", band.transform, "", 13f, C_LABEL,
                UIFactory.AlignTopLeft, sizeDelta: new Vector2(728, 18));
            UIFactory.SetWordWrap(setDetReasonTxt, true);
            UIFactory.SetOverflowMode(setDetReasonTxt, 0);
            UIFactory.SetTextAutoHeight(setDetReasonTxt, 18f);

            setDetDetectedTxt = UIFactory.CreateText("SetDetDetected", det.transform, "", 13f, C_DIM,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(748, 18));
            UIFactory.FitOneLine(setDetDetectedTxt);
            setDetDetectedGO = ((Component)setDetDetectedTxt).gameObject;
            setDetDetectedGO.SetActive(false);

            var bodySV = UIFactory.CreateScrollView("SetDetBodySV", det.transform, spacing: SetDetBodySpacing);
            UIFactory.AddLE(bodySV.scrollGO, flexH: 1);
            setDetBodyTxt = UIFactory.CreateText("SetDetBody", bodySV.content.transform, "", 15f, C_WHITE,
                UIFactory.AlignTopLeft, sizeDelta: new Vector2(748, 20));
            UIFactory.SetWordWrap(setDetBodyTxt, true);
            UIFactory.SetOverflowMode(setDetBodyTxt, 0);
            UIFactory.SetTextAutoHeight(setDetBodyTxt, 0f);
            // CreateText bakes minH = sizeDelta.y as its compression guard,
            // which inside scroll content RESERVES that height under a short
            // body (the BuildInfoTab lesson, design section 6.1 item 4).
            UIFactory.SetMinH(((Component)setDetBodyTxt).gameObject, 0f);
            var extras = new GameObject("SetDetExtras");
            extras.transform.SetParent(bodySV.content.transform, false);
            extras.AddComponent<RectTransform>();
            UIFactory.AddVLG(extras, spacing: 6);
            UIFactory.AddLE(extras, flexH: 0);
            setDetExtrasGO = extras;

            var prev = new GameObject("SDetPrev");
            prev.transform.SetParent(det.transform, false);
            prev.AddComponent<RectTransform>();
            UIFactory.AddVLG(prev, spacing: 4);
            UIFactory.AddLE(prev, flexH: 0);
            setDetPrevGO = prev;

            BuildSettingsPaneTexts(extras.transform);
            setExtraSCS = SettingsTextGO(txtConsentStatus);
            setExtraSDS = SettingsTextGO(txtDeleteStatus);
            var ex = extras.transform;
            setExtraSDD = ex.Find("SDD") != null ? ex.Find("SDD").gameObject : null;
            setExtraSDD2 = ex.Find("SDD2") != null ? ex.Find("SDD2").gameObject : null;
            setExtraLangNote = ex.Find("SLangChatNote") != null ? ex.Find("SLangChatNote").gameObject : null;
            try { setExtraPcInfo = PlayerCardsUI.BuildSettingsPaneExtras(extras.transform, prev.transform); }
            catch (Exception e) { Plugin.Log.LogWarning("[SETTINGS] player-cards pane extras: " + e.Message); }
            prev.SetActive(false);

            // -- footer --
            var foot = new GameObject("SetDetFoot");
            foot.transform.SetParent(det.transform, false);
            foot.AddComponent<RectTransform>();
            UIFactory.AddHLG(foot, spacing: 8, forceExpandW: false, forceExpandH: false);
            UIFactory.SetHLGChildAlignMiddle(foot);
            UIFactory.AddLE(foot, minH: 28, prefH: 28, flexH: 0);
            setDetMoreBtn = UIFactory.CreateButton("SetDetMore", foot.transform, "Read more", 14f, C_WHITE,
                new Color(0.20f, 0.34f, 0.55f, 0.92f), SettingsReadMoreClicked, new Vector2(140, 26));
            var footSp = new GameObject("SetDetFootSp");
            footSp.transform.SetParent(foot.transform, false);
            footSp.AddComponent<RectTransform>();
            UIFactory.AddLE(footSp, flexW: 1);
            var skip = UIFactory.CreateText("SetDetSkip", foot.transform, "Skipped: server settings", 13f, C_DIM,
                UIFactory.AlignMidRight, sizeDelta: new Vector2(220, 26));
            UIFactory.FitOneLine(skip);
            setDetSkipGO = ((Component)skip).gameObject;
            setResetBtn = UIFactory.CreateButton("SResetTab", foot.transform, "Reset this tab to recommended", 14f,
                C_WHITE, C_BTN, SettingsResetClicked, new Vector2(300, 26));
            setResetConfirmBtn = UIFactory.CreateButton("SResetTabC", foot.transform, "Confirm", 14f, C_WHITE,
                new Color(0.55f, 0.35f, 0.12f, 0.95f), SettingsResetConfirm, new Vector2(110, 26));
            setResetCancelBtn = UIFactory.CreateButton("SResetTabX", foot.transform, "Cancel", 14f, C_LABEL,
                C_BTN, SettingsResetCancel, new Vector2(100, 26));
            setResetConfirmBtn.SetActive(false);
            setResetCancelBtn.SetActive(false);
            setDetSkipGO.SetActive(false);

            return sv.content.transform;
        }

        private static GameObject SettingsTextGO(object tmp)
        {
            try { return tmp != null ? ((Component)tmp).gameObject : null; } catch { return null; }
        }

        /// <summary>The root every sub-tab body hangs under (the name the
        /// keyset instrument stops its ancestry walk at).</summary>
        private static void SettingsPanelInit(GameObject panel)
        {
            panel.AddComponent<RectTransform>();
            UIFactory.AddVLG(panel, spacing: 0);
            UIFactory.AddLE(panel, flexH: 0);
        }

        /// <summary>One sub-tab body: rows at spacing 4 inside 12/12/8/8, so a
        /// row is 996 px wide in the 1020 px list (design section 3.2).</summary>
        private static void SettingsBodyInit(GameObject body, int idx)
        {
            body.AddComponent<RectTransform>();
            UIFactory.AddVLG(body, spacing: 4, padL: 12, padR: 12, padT: 8, padB: 8);
            UIFactory.AddLE(body, flexH: 0);
            if (idx >= 0 && idx < SETTINGS_TABS) settingsBodies[idx] = body;
        }

        private static int SettingsTabOf(Transform t)
        {
            for (var a = t; a != null; a = a.parent)
                for (int i = 0; i < SETTINGS_TABS; i++)
                    if (settingsBodies[i] != null && settingsBodies[i].transform == a) return i;
            return -1;
        }

        /// <summary>Alternating row background, alpha 0.00 / 0.04, counted
        /// per parent so a nested list (the performance rows) starts fresh.</summary>
        private static Color SettingsZebra(Transform parent)
        {
            int n;
            settingsZebraCount.TryGetValue(parent, out n);
            settingsZebraCount[parent] = n + 1;
            return new Color(1f, 1f, 1f, (n % 2 == 1) ? 0.04f : 0f);
        }

        /// <summary>The row: HLG spacing 10, pad 6/6, 34 px (design 3.3).</summary>
        private static void SettingsRowLayout(GameObject row)
        {
            UIFactory.AddHLG(row, spacing: 10, padL: 6, padR: 6, forceExpandW: false, forceExpandH: false);
            UIFactory.SetHLGChildAlignMiddle(row);
            UIFactory.AddLE(row, minH: 34, prefH: 34, flexH: 0, flexW: 0);
        }

        /// <summary>The help button and the label column. The delete row's
        /// decoration also creates its group record: its three buttons share
        /// one row, one help button and one combined pane (design 6.1).</summary>
        private static object SettingsDecorateRow(GameObject row, string key)
        {
            var q = UIFactory.CreateButton(key + "_q", row.transform, "", 14f, C_WHITE, C_BTN,
                () => SettingsHelpClicked(key), new Vector2(26, 26));
            UIFactory.SetMinW(q, 26);
            UIFactory.SetMinH(q, 26);
            UIFactory.SetTextNoHook(UIFactory.GetButtonText(q), "?");
            var l = UIFactory.CreateText(key + "_l", row.transform, "", 14f, C_WHITE,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(340, 26));
            UIFactory.SetMinW(((Component)l).gameObject, 340);
            UIFactory.FitOneLine(l);
            if (key == "SDR")
            {
                var grp = new SettingsRowRec
                {
                    Key = "SDR", Kind = SettingsKind.Destructive, Row = row, Help = q, Label = l,
                    Tab = SettingsTabOf(row.transform), Members = new List<SettingsRowRec>()
                };
                settingsByKey["SDR"] = grp;
                if (grp.Tab >= 0) settingsTabRows[grp.Tab].Add(grp);
                settingsDeleteStateTxt = l;
            }
            return l;
        }

        /// <summary>The control cell: everything right of the label, 598 px
        /// on a 996 px row, children middle-aligned.</summary>
        private static void SettingsCellLayout(GameObject cell)
        {
            cell.AddComponent<RectTransform>();
            UIFactory.AddHLG(cell, spacing: 6, forceExpandW: false, forceExpandH: false);
            UIFactory.SetHLGChildAlignMiddle(cell);
            UIFactory.AddLE(cell, minH: 26, prefH: 26, flexW: 1);
        }

        private static SettingsRowRec SettingsNewRow(Transform parent, string key, SettingsKind kind, string desc)
        {
            var row = UIFactory.CreatePanel(key, parent, SettingsZebra(parent));
            SettingsRowLayout(row);
            var label = SettingsDecorateRow(row, key);
            var cell = new GameObject(key + "_c");
            cell.transform.SetParent(row.transform, false);
            SettingsCellLayout(cell);
            var q = row.transform.Find(key + "_q");
            var rec = new SettingsRowRec
            {
                Key = key, Kind = kind, Desc = desc, Row = row, Label = label, Cell = cell,
                Help = q != null ? q.gameObject : null, Tab = SettingsTabOf(parent)
            };
            if (label != null) settingsRegistry[label] = rec;
            settingsByKey[key] = rec;
            if (rec.Tab >= 0) settingsTabRows[rec.Tab].Add(rec);
            return rec;
        }

        // ---------------------------------------------------------------
        // The typed constructors (design section 5). Each returns the ROW;
        // UIFactory.GetButtonText(row) is its label text, which is where the
        // row's painter writes.
        // ---------------------------------------------------------------

        internal static GameObject SettingsSwitch(Transform parent, string key, string desc, Func<bool> get,
            UnityEngine.Events.UnityAction toggle, Func<bool> known = null)
        {
            var rec = SettingsNewRow(parent, key, SettingsKind.Switch, desc);
            rec.GetBool = get;
            rec.Toggle = toggle;
            rec.Known = known;
            var track = UIFactory.CreatePanel(key + "_t", rec.Cell.transform, SW_OFF, new Vector2(46, 22));
            UIFactory.AddLE(track, minW: 46, minH: 22, prefW: 46, prefH: 22, flexW: 0, flexH: 0);
            var knob = UIFactory.CreatePanel(key + "_k", track.transform, SW_KNOB);
            var krt = knob.GetComponent<RectTransform>();
            krt.anchorMin = new Vector2(0f, 0.5f);
            krt.anchorMax = new Vector2(0f, 0.5f);
            krt.pivot = new Vector2(0f, 0.5f);
            krt.sizeDelta = new Vector2(18, 18);
            krt.anchoredPosition = new Vector2(2, 0);
            UIFactory.AddClick(track, () => { SettingsSelectRec(rec); if (rec.Toggle != null) rec.Toggle(); });
            rec.Track = track;
            rec.Knob = knob;
            var w = UIFactory.CreateText(key + "_w", rec.Cell.transform, "", 14f, C_WHITE,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(240, 26));
            UIFactory.FitOneLine(w);
            rec.Word = w;
            return rec.Row;
        }

        internal static GameObject SettingsSegmented(Transform parent, string key, string desc, string[] ids,
            Func<string> current, Action<string> pick)
        {
            var rec = SettingsNewRow(parent, key, SettingsKind.Segmented, desc);
            rec.Ids = ids ?? new string[0];
            rec.Current = current;
            rec.Pick = pick;
            rec.Opts = new GameObject[rec.Ids.Length];
            rec.OptTxts = new object[rec.Ids.Length];
            for (int i = 0; i < rec.Ids.Length; i++)
            {
                string id = rec.Ids[i];
                var b = UIFactory.CreateButton(key + "_o" + i, rec.Cell.transform, "", 13f, C_WHITE, C_BTN,
                    () => { SettingsSelectRec(rec); SettingsPickValue(rec, id); }, new Vector2(150, 24));
                UIFactory.SetMinW(b, 150);
                rec.Opts[i] = b;
                rec.OptTxts[i] = UIFactory.GetButtonText(b);
                UIFactory.SetTextNoHook(rec.OptTxts[i], SettingsOptionWord(key, id));
            }
            return rec.Row;
        }

        internal static GameObject SettingsDropdown(Transform parent, string key, string desc, Func<string[]> ids,
            Func<string> current, Action<string> pick, Func<string[]> names = null, string title = null)
        {
            var rec = SettingsNewRow(parent, key, SettingsKind.Dropdown, desc);
            rec.IdsF = ids;
            rec.Current = current;
            rec.Pick = pick;
            rec.NamesF = names;
            rec.Title = title;
            var face = UIFactory.CreateButton(key + "_f", rec.Cell.transform, "", 14f, C_WHITE, C_BTN,
                () => { SettingsSelectRec(rec); SettingsOpenDropdown(rec); }, new Vector2(320, 26));
            UIFactory.SetMinW(face, 320);
            rec.Face = face;
            rec.FaceTxt = UIFactory.GetButtonText(face);
            UIFactory.SetAlign(rec.FaceTxt, UIFactory.AlignMidLeft);
            try
            {
                var ftr = ((Component)rec.FaceTxt).GetComponent<RectTransform>();
                ftr.offsetMin = new Vector2(8, 0);
                ftr.offsetMax = new Vector2(-8, 0);
            }
            catch { }
            return rec.Row;
        }

        internal static GameObject SettingsSlider(Transform parent, string key, string desc, float[] stops,
            Func<int> index, Action<float> set)
        {
            var rec = SettingsNewRow(parent, key, SettingsKind.Slider, desc);
            rec.Stops = (stops != null && stops.Length > 0) ? stops : new float[] { 0f };
            rec.Index = index;
            rec.SetStop = set;
            const float sw = 340f;
            var h = UIFactory.CreateSlider(rec.Cell.transform, key + "_s", sw, 20, v => SettingsSliderMoved(rec, v));
            rec.Slider = h;
            int n = rec.Stops.Length;
            if (h != null && n > 1)
            {
                // One tick per stop, hanging below the track, at the handle's
                // travel (the handle area is inset 6 px each side).
                for (int i = 0; i < n; i++)
                {
                    float x = 6f + i * (sw - 12f) / (n - 1);
                    var tk = UIFactory.CreatePanel(key + "_s_t" + i, h.go.transform, new Color(0.6f, 0.6f, 0.66f, 0.9f));
                    var trt = tk.GetComponent<RectTransform>();
                    trt.anchorMin = new Vector2(x / sw, 0f);
                    trt.anchorMax = new Vector2(x / sw, 0f);
                    trt.pivot = new Vector2(0.5f, 1f);
                    trt.sizeDelta = new Vector2(2, 6);
                    trt.anchoredPosition = Vector2.zero;
                }
            }
            var ro = UIFactory.CreateText(key + "_v", rec.Cell.transform, "", 14f, C_WHITE,
                UIFactory.AlignMidLeft, sizeDelta: new Vector2(230, 26));
            UIFactory.FitOneLine(ro);
            rec.Readout = ro;
            return rec.Row;
        }

        internal static GameObject SettingsAction(Transform parent, string key, string desc,
            UnityEngine.Events.UnityAction act, Color glyphBg)
        {
            var rec = SettingsNewRow(parent, key, SettingsKind.Action, desc);
            rec.Act = act;
            var g = UIFactory.CreateButton(key + "_g", rec.Cell.transform, "", 16f, C_WHITE, glyphBg,
                () => { SettingsSelectRec(rec); if (rec.Act != null) rec.Act(); }, new Vector2(44, 26));
            UIFactory.SetMinW(g, 44);
            rec.Glyph = g;
            rec.GlyphTxt = UIFactory.GetButtonText(g);
            UIFactory.SetTextNoHook(rec.GlyphTxt, ">");
            return rec.Row;
        }

        internal static GameObject SettingsDisclosure(Transform parent, string key, string desc, Func<bool> expanded,
            UnityEngine.Events.UnityAction toggle)
        {
            var rec = SettingsNewRow(parent, key, SettingsKind.Disclosure, desc);
            rec.Expanded = expanded;
            rec.Toggle = toggle;
            var g = UIFactory.CreateButton(key + "_g", rec.Cell.transform, "", 16f, C_WHITE, C_BTN,
                () => { SettingsSelectRec(rec); if (rec.Toggle != null) rec.Toggle(); }, new Vector2(44, 26));
            UIFactory.SetMinW(g, 44);
            rec.Glyph = g;
            rec.GlyphTxt = UIFactory.GetButtonText(g);
            UIFactory.SetTextNoHook(rec.GlyphTxt, ">");
            return rec.Row;
        }

        /// <summary>One of the delete row's three buttons, built into the
        /// shared SDR cell. Its painter writes the button's own face.</summary>
        internal static GameObject SettingsDestructive(Transform cell, string key, string label, Color textColor,
            Color bgColor, Vector2 size, UnityEngine.Events.UnityAction onClick)
        {
            SettingsRowRec rec = null;
            var b = UIFactory.CreateButton(key, cell, label ?? "", 14f, textColor, bgColor,
                () => { SettingsSelectGroupOf(rec); if (onClick != null) onClick(); }, size);
            UIFactory.SetMinW(b, size.x);
            rec = new SettingsRowRec
            {
                Key = key, Kind = SettingsKind.Destructive, Button = b, ButtonTxt = UIFactory.GetButtonText(b),
                ButtonSize = size, Cell = cell.gameObject, Row = cell.parent != null ? cell.parent.gameObject : null,
                Tab = SettingsTabOf(cell), Act = onClick
            };
            if (rec.ButtonTxt != null) settingsRegistry[rec.ButtonTxt] = rec;
            settingsByKey[key] = rec;
            SettingsRowRec grp;
            if (settingsByKey.TryGetValue("SDR", out grp) && grp.Members != null) grp.Members.Add(rec);
            return b;
        }

        // ---------------------------------------------------------------
        // Paint hook, capture and the per-key bridge
        // ---------------------------------------------------------------

        /// <summary>UIFactory.SetText / SetTextRaw call this with every write.
        /// True means the write was handled here. Only the settings rows'
        /// own text objects (and a capture sentinel) are handled.</summary>
        private static bool SettingsPaintHook(object t, string s, bool raw)
        {
            if (t == null) return false;
            if (settingsCaptureSentinel != null && ReferenceEquals(t, settingsCaptureSentinel))
            {
                settingsCaptureResult = s ?? "";
                return true;
            }
            if (settingsRegistry.Count == 0) return false;
            SettingsRowRec rec;
            if (!settingsRegistry.TryGetValue(t, out rec)) return false;
            if (raw && settingsSelfTestSuppressRaw) return true;
            if (settingsSelfTestSkipKey != null && rec.Key == settingsSelfTestSkipKey) return true;
            SettingsPaintRow(rec, s ?? "");
            return true;
        }

        private static bool SettingsSplits(SettingsKind k)
        {
            return k == SettingsKind.Switch || k == SettingsKind.Segmented || k == SettingsKind.Dropdown || k == SettingsKind.Slider;
        }

        /// <summary>Classification is by the row's KIND, never by whether the
        /// string happens to contain a colon (design 3.3): the four value
        /// kinds split, ACTION / DISCLOSURE / DESTRUCTIVE keep it whole.</summary>
        private static void SettingsPaintRow(SettingsRowRec rec, string s)
        {
            rec.Paints++;
            rec.LastPainted = s;
            if (SettingsSplits(rec.Kind))
            {
                string lab, val;
                if (!SettingsModel.SplitSettingLabel(s, out lab, out val)) { lab = ""; val = s; }
                rec.LastLabel = lab;
                rec.LastValue = val;
                UIFactory.SetTextNoHook(rec.Label, lab);
            }
            else if (rec.Kind == SettingsKind.Destructive)
            {
                rec.LastLabel = SettingsWholeTitle(s);
                rec.LastValue = "";
                UIFactory.SetTextNoHook(rec.ButtonTxt, s);
            }
            else
            {
                rec.LastLabel = SettingsWholeTitle(s);
                rec.LastValue = "";
                UIFactory.SetTextNoHook(rec.Label, s);
            }
            SettingsSyncWidget(rec);
            settingsPaneDirty = true;
        }

        /// <summary>A whole-kind row's title: the painted face without tags
        /// and without its disclosure arrow.</summary>
        private static string SettingsWholeTitle(string s)
        {
            string t = SettingsModel.StripTags(s ?? "");
            if (t.StartsWith("v ", StringComparison.Ordinal) || t.StartsWith("> ", StringComparison.Ordinal)) t = t.Substring(2).TrimStart();
            t = t.TrimEnd();
            if (t.EndsWith(" ^", StringComparison.Ordinal) || t.EndsWith(" v", StringComparison.Ordinal)) t = t.Substring(0, t.Length - 2).TrimEnd();
            return t;
        }

        private static void SettingsSyncWidget(SettingsRowRec rec)
        {
            try
            {
                switch (rec.Kind)
                {
                    case SettingsKind.Switch:
                    {
                        bool on = false, known = true;
                        try { on = rec.GetBool != null && rec.GetBool(); } catch { }
                        try { known = rec.Known == null || rec.Known(); } catch { known = false; }
                        UIFactory.SetImageColor(rec.Track, !known ? SW_NA : on ? SW_ON : SW_OFF);
                        UIFactory.SetImageColor(rec.Knob, known ? SW_KNOB : SW_KNOB_NA);
                        if (rec.Knob != null) rec.Knob.GetComponent<RectTransform>().anchoredPosition = new Vector2(!known ? 14f : on ? 26f : 2f, 0f);
                        UIFactory.SetTextNoHook(rec.Word, rec.LastValue);
                        break;
                    }
                    case SettingsKind.Segmented:
                    {
                        string cur = null;
                        try { cur = rec.Current != null ? rec.Current() : null; } catch { }
                        for (int i = 0; i < rec.Opts.Length; i++)
                            UIFactory.SetImageColor(rec.Opts[i],
                                string.Equals(rec.Ids[i], cur, StringComparison.OrdinalIgnoreCase) ? C_TABACT : C_BTN);
                        break;
                    }
                    case SettingsKind.Dropdown:
                        UIFactory.SetTextNoHook(rec.FaceTxt, rec.LastValue + "  v");
                        break;
                    case SettingsKind.Slider:
                    {
                        int idx = 0;
                        try { idx = rec.Index != null ? rec.Index() : 0; } catch { }
                        idx = Mathf.Clamp(idx, 0, rec.Stops.Length - 1);
                        rec.LastIdx = idx;
                        if (rec.Slider != null && rec.Stops.Length > 1) rec.Slider.SetSilent(idx / (float)(rec.Stops.Length - 1));
                        UIFactory.SetTextNoHook(rec.Readout, rec.LastValue);
                        break;
                    }
                    case SettingsKind.Disclosure:
                    {
                        bool ex = false;
                        try { ex = rec.Expanded != null && rec.Expanded(); } catch { }
                        UIFactory.SetTextNoHook(rec.GlyphTxt, ex ? "v" : ">");
                        break;
                    }
                }
            }
            catch (Exception e) { Plugin.Log.LogWarning("[SETTINGS] sync " + rec.Key + ": " + e.Message); }
        }

        /// <summary>The string the row's own painter produces for a value that
        /// is not the live one (the recommended value, an option's word):
        /// the painter writes into a sentinel the hook captures. Re-entrant.</summary>
        private static string SettingsCapture(string key, object v)
        {
            var prevS = settingsCaptureSentinel;
            var prevR = settingsCaptureResult;
            var sentinel = new object();
            settingsCaptureSentinel = sentinel;
            settingsCaptureResult = null;
            string got = null;
            try { if (SettingsPaintValue(key, sentinel, v)) got = settingsCaptureResult; }
            catch (Exception e) { Plugin.Log.LogWarning("[SETTINGS] capture " + key + ": " + e.Message); }
            finally { settingsCaptureSentinel = prevS; settingsCaptureResult = prevR; }
            return got;
        }

        /// <summary>The value half of the painter's string for v.</summary>
        private static string SettingsCaptureValue(string key, object v)
        {
            string s = SettingsCapture(key, v);
            if (s == null) return null;
            string lab, val;
            return SettingsModel.SplitSettingLabel(s, out lab, out val) ? val : s;
        }

        private static string SettingsOptionWord(string key, string id)
        {
            string v = SettingsCaptureValue(key, id);
            return string.IsNullOrEmpty(v) ? id : SettingsModel.StripTags(v);
        }

        private static bool SettingsAsBool(object v)
        {
            if (v is bool) return (bool)v;
            if (v is int) return (int)v != 0;
            var s = v as string;
            if (s == null) return false;
            s = s.Trim();
            return s == "1" || string.Equals(s, "true", StringComparison.OrdinalIgnoreCase)
                || string.Equals(s, "on", StringComparison.OrdinalIgnoreCase)
                || string.Equals(s, "granted", StringComparison.OrdinalIgnoreCase);
        }

        private static string SettingsAsStr(object v)
        {
            if (v == null) return "";
            var s = v as string;
            return s ?? Convert.ToString(v, CultureInfo.InvariantCulture);
        }

        private static float SettingsAsFloat(object v)
        {
            if (v is float) return (float)v;
            if (v is double) return (float)(double)v;
            if (v is int) return (int)v;
            float f;
            var s = v as string;
            if (s != null && float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out f)) return f;
            return 0f;
        }

        private static int SettingsAsInt(object v)
        {
            if (v is int) return (int)v;
            if (v is float) return (int)(float)v;
            int i;
            var s = v as string;
            if (s != null && int.TryParse(s, NumberStyles.Integer, CultureInfo.InvariantCulture, out i)) return i;
            return -1;
        }

        private static CompetitiveUI.ChatOverlayMode SettingsAsChatMode(object v)
        {
            if (v is CompetitiveUI.ChatOverlayMode) return (CompetitiveUI.ChatOverlayMode)v;
            var s = v as string;
            CompetitiveUI.ChatOverlayMode m;
            if (s != null && Enum.TryParse(s.Trim(), true, out m)) return m;
            return CompetitiveUI.ChatOverlayMode.Normal;
        }

        /// <summary>Every key's painter as a function of a value. The server
        /// rows are rendered in their ordinary context (the status known, a
        /// Discord linked), which is the state a recommendation is about.</summary>
        private static bool SettingsPaintValue(string key, object t, object v)
        {
            if (key == null) return false;
            if (key.StartsWith("SPerf_", StringComparison.Ordinal))
            {
                PaintPerfRow(t, SettingsAsBool(v), PerfRowLabel(key.Substring(6)));
                return true;
            }
            switch (key)
            {
                case "SCT": PaintConsent(t, SettingsAsBool(v)); return true;
                case "SAppOff": PaintAppearOffline(t, SettingsAsBool(v)); return true;
                case "SPrefSC": PaintPrefSameCards(t, SettingsAsBool(v)); return true;
                case "SShowDc": PaintShowDiscord(t, true, SettingsAsBool(v)); return true;
                case "SAllowSpec": PaintAllowSpectators(t, SettingsAsBool(v)); return true;
                case "SAutoLog": PaintAutoLog(t, SettingsAsBool(v)); return true;
                case "SPcPub": PlayerCardsUI.PaintCollectionPublic(t, SettingsAsBool(v)); return true;
                case "SPcAnn": PlayerCardsUI.PaintAnnounce(t, SettingsAsBool(v)); return true;
                case "SPcTrd": PlayerCardsUI.PaintTrades(t, SettingsAsBool(v)); return true;
                case "SPcPre": PlayerCardsUI.PaintPreset(t, SettingsAsInt(v)); return true;
                case "SPcDnc": PlayerCardsUI.PaintDance(t, PlayerCardsUI.DanceOptionLabel(SettingsAsStr(v))); return true;
                case "SMailFrom": MailUI.PaintMailFrom(t, SettingsAsStr(v)); return true;
                case "SMailRelay": MailUI.PaintMailRelay(t, true, true, SettingsAsBool(v)); return true;
                case "SFPS": PaintShowFps(t, SettingsAsBool(v)); return true;
                case "SFPSCap": PaintCapFps(t, SettingsAsBool(v)); return true;
                case "SDeepIdle": PaintDeepIdle(t, SettingsAsBool(v)); return true;
                case "SMuteBg": PaintMuteBg(t, SettingsAsBool(v)); return true;
                case "SMenuMus": PaintMenuMusic(t, SettingsAsStr(v)); return true;
                case "SMusCredit": PaintMusicCredit(t, SettingsAsBool(v)); return true;
                case "SPing": PaintRegionPing(t, SettingsAsBool(v)); return true;
                case "SInactiveLb": PaintInactiveBoards(t, SettingsAsBool(v)); return true;
                case "SLagNotice": PaintLagNotices(t, SettingsAsBool(v)); return true;
                case "SIgChat": PaintIngameChat(t, SettingsAsChatMode(v)); return true;
                case "SChatTtl": PaintChatTtl(t, SettingsAsFloat(v)); return true;
                case "SNT": PaintNotifications(t, SettingsAsBool(v)); return true;
                case "SInpOv": PaintInputOverlay(t, SettingsAsBool(v)); return true;
                case "SBlkDbg": PaintBlockDebug(t, SettingsAsBool(v)); return true;
                case "SCursor": PaintCursorShape(t, SettingsAsStr(v)); return true;
                case "SAvAuto": PaintAvatarAuto(t, SettingsAsBool(v)); return true;
                case "SAvMod": PaintAvatarModded(t, SettingsAsInt(v)); return true;
                case "SAvVan": PaintAvatarVanilla(t, SettingsAsInt(v)); return true;
                case "STrail": PaintTrails(t, SettingsAsBool(v)); return true;
                case "SPColor": PaintPlayerColors(t, SettingsAsBool(v)); return true;
                case "SAnimCos": PaintAnimCos(t, SettingsAsBool(v)); return true;
                case "SBloom": PaintBloom(t, SettingsAsStr(v)); return true;
                case "SShake": PaintScreenShake(t, SettingsAsStr(v)); return true;
                case "SHpPrec": PaintHealthPrecision(t, SettingsAsStr(v)); return true;
                case "SChromAb": PaintChromAb(t, SettingsAsBool(v)); return true;
                case "SLight": PaintMapLighting(t, SettingsAsBool(v)); return true;
                case "SShad": PaintMapShadows(t, SettingsAsBool(v)); return true;
                case "SLang": PaintLanguage(t, SettingsAsStr(v)); return true;
                case "SDateFmt": PaintDateFormat(t, SettingsAsStr(v)); return true;
                case "SHeavyFont": PaintHeavyFont(t, SettingsAsBool(v)); return true;
            }
            return false;
        }

        /// <summary>The recommended value, rendered by the row's own painter
        /// from the descriptor's operand and split (design 6.1 item 3).</summary>
        private static string SettingsRecommendedValue(string key)
        {
            object op = null;
            try { op = SettingsDescriptorWriters.RecommendedOperand(key); } catch { }
            if (op == null) return "";
            return SettingsCaptureValue(key, op) ?? "";
        }

        // ---------------------------------------------------------------
        // Widget actions
        // ---------------------------------------------------------------

        private static void SettingsPickValue(SettingsRowRec rec, string id)
        {
            try { if (rec.Pick != null) rec.Pick(id); }
            catch (Exception e) { Plugin.Log.LogWarning("[SETTINGS] pick " + rec.Key + ": " + e.Message); }
            dirty = true;
            settingsPaneDirty = true;
        }

        private static void SettingsOpenDropdown(SettingsRowRec rec)
        {
            string[] ids = null;
            try { ids = rec.IdsF != null ? rec.IdsF() : null; } catch { }
            if (ids == null || ids.Length == 0) return;
            string[] names = null;
            try { names = rec.NamesF != null ? rec.NamesF() : null; } catch { }
            if (names == null || names.Length != ids.Length)
            {
                names = new string[ids.Length];
                for (int i = 0; i < ids.Length; i++) names[i] = SettingsOptionWord(rec.Key, ids[i]);
            }
            string cur = null;
            try { cur = rec.Current != null ? rec.Current() : null; } catch { }
            string title = rec.Title ?? (string.IsNullOrEmpty(rec.LastLabel) ? rec.Key : rec.LastLabel);
            var r = rec;
            CompetitiveUI.OpenArtistPicker(title, names, ids,
                picked => { if (!string.IsNullOrEmpty(picked)) SettingsPickValue(r, picked); },
                actionLabel: I18n.Tr("Use"), showClear: false, itemNoun: "", selectedId: cur, showIds: false);
        }

        /// <summary>A drag writes only when the stop changes, never flips the
        /// page's dirty flag (a repaint mid-drag would fight the handle), and
        /// paints the readout at once through the row's own painter.</summary>
        private static void SettingsSliderMoved(SettingsRowRec rec, float v)
        {
            int n = rec.Stops.Length;
            int idx = n > 1 ? Mathf.Clamp(Mathf.RoundToInt(v * (n - 1)), 0, n - 1) : 0;
            if (rec.Slider != null && n > 1) rec.Slider.SetSilent(idx / (float)(n - 1));
            if (idx == rec.LastIdx) return;
            SettingsSetSliderIndex(rec, idx);
        }

        private static void SettingsSetSliderIndex(SettingsRowRec rec, int idx)
        {
            int n = rec.Stops.Length;
            idx = Mathf.Clamp(idx, 0, n - 1);
            rec.LastIdx = idx;
            SettingsSelectRec(rec);
            try { if (rec.SetStop != null) rec.SetStop(rec.Stops[idx]); }
            catch (Exception e) { Plugin.Log.LogWarning("[SETTINGS] slider " + rec.Key + ": " + e.Message); }
            if (rec.Slider != null && n > 1) rec.Slider.SetSilent(idx / (float)(n - 1));
            string val = SettingsCaptureValue(rec.Key, rec.Stops[idx]);
            if (val != null) { rec.LastValue = val; UIFactory.SetTextNoHook(rec.Readout, val); }
            settingsPaneDirty = true;
        }

        // ---------------------------------------------------------------
        // Selection, sub-tabs, hover
        // ---------------------------------------------------------------

        private static List<SettingsRowRec> SettingsFocusList(int tab)
        {
            var list = new List<SettingsRowRec>();
            if (tab < 0 || tab >= SETTINGS_TABS) return list;
            foreach (var r in settingsTabRows[tab])
                if (r.Row != null && r.Row.activeInHierarchy) list.Add(r);
            return list;
        }

        private static SettingsRowRec SettingsFocusedRec()
        {
            var list = SettingsFocusList(settingsSubTab);
            if (list.Count == 0) return null;
            int i = Mathf.Clamp(settingsFocusRow[settingsSubTab], 0, list.Count - 1);
            return list[i];
        }

        private static void SettingsSelectRec(SettingsRowRec rec)
        {
            if (rec == null) return;
            if (rec.Kind == SettingsKind.Destructive && rec.Members == null) { SettingsSelectGroupOf(rec); return; }
            int tab = rec.Tab;
            if (tab < 0 || tab >= SETTINGS_TABS) return;
            var list = SettingsFocusList(tab);
            int idx = list.IndexOf(rec);
            if (idx >= 0) settingsFocusRow[tab] = idx;
            if (settingsPinnedKey != null && settingsPinnedKey != rec.Key) settingsPinnedKey = null;
            SettingsUpdateFocusHighlight();
            settingsPaneDirty = true;
        }

        private static void SettingsSelectGroupOf(SettingsRowRec member)
        {
            SettingsRowRec grp;
            if (settingsByKey.TryGetValue("SDR", out grp)) SettingsSelectRec(grp);
        }

        private static void SettingsHelpClicked(string key)
        {
            SettingsRowRec rec;
            if (!settingsByKey.TryGetValue(key, out rec)) return;
            SettingsSelectRec(rec);
            SettingsRenderPane();
        }

        private static void SettingsUpdateFocusHighlight()
        {
            var f = SettingsFocusedRec();
            foreach (var r in settingsTabRows[Mathf.Clamp(settingsSubTab, 0, SETTINGS_TABS - 1)])
                if (r.Help != null) UIFactory.SetImageColor(r.Help, r == f ? C_TABACT : C_BTN);
        }

        private static void SettingsSwitchSubTab(int idx)
        {
            if (idx < 0 || idx >= SETTINGS_TABS) return;
            settingsSubTab = idx;
            for (int i = 0; i < SETTINGS_TABS; i++)
            {
                if (settingsBodies[i] != null) settingsBodies[i].SetActive(i == idx);
                if (settingsSubBtns[i] != null) UIFactory.SetImageColor(settingsSubBtns[i], i == idx ? C_TABACT : C_TAB);
            }
            settingsHoverKey = null;
            settingsPinnedKey = null;
            settingsResetArmed = false;
            SettingsScrollListTo(1f);
            SettingsUpdateFocusHighlight();
            SettingsUpdateHint();
            settingsPaneDirty = true;
            SettingsRenderPane();
        }

        /// <summary>The last statement of BuildSettingsTab: every rebuild
        /// route lands on the remembered sub-tab (design T4 / A7).</summary>
        private static void ApplyRememberedSubTab()
        {
            // Self-test mutation a7-noremember: skip exactly one restore.
            if (settingsSelfTestSkipRemember) { settingsSelfTestSkipRemember = false; return; }
            SettingsSwitchSubTab(Mathf.Clamp(settingsSubTab, 0, SETTINGS_TABS - 1));
        }

        private static void SettingsSelectKey(string key)
        {
            SettingsRowRec rec;
            if (key == null || !settingsByKey.TryGetValue(key, out rec)) return;
            if (rec.Kind == SettingsKind.Destructive && rec.Members == null) settingsByKey.TryGetValue("SDR", out rec);
            if (rec == null || rec.Tab < 0) return;
            if (rec.Tab != settingsSubTab) SettingsSwitchSubTab(rec.Tab);
            if (rec.Row != null && !rec.Row.activeInHierarchy && rec.Tab == SettingsModel.SubTabIndex("perf")) SettingsExpandTab(rec.Tab);
            SettingsSelectRec(rec);
            SettingsRenderPane();
        }

        private static void SettingsExpandTab(int idx)
        {
            if (idx == SettingsModel.SubTabIndex("perf") && !_perfSectionOpen)
            {
                _perfSectionOpen = true;
                if (_perfSectionBody != null) _perfSectionBody.SetActive(true);
                dirty = true;
            }
        }

        private static void SettingsScrollListTo(float normalized)
        {
            try
            {
                if (settingsScrollGO == null || UIFactory.tScrollRect == null) return;
                var sr = settingsScrollGO.GetComponent(UIFactory.tScrollRect);
                var p = UIFactory.tScrollRect.GetProperty("verticalNormalizedPosition", BindingFlags.Public | BindingFlags.Instance);
                if (sr != null && p != null) p.SetValue(sr, Mathf.Clamp01(normalized));
            }
            catch { }
        }

        private static float SettingsActiveContentHeight()
        {
            var b = (settingsSubTab >= 0 && settingsSubTab < SETTINGS_TABS) ? settingsBodies[settingsSubTab] : null;
            if (b == null) return 0f;
            return b.GetComponent<RectTransform>().rect.height;
        }

        /// <summary>The viewport height as if the hint were inactive, so the
        /// hint's own 16 px cannot flip the decision it depends on.</summary>
        private static float SettingsViewportNoHint()
        {
            if (setListViewport == null) return 0f;
            float h = setListViewport.GetComponent<RectTransform>().rect.height;
            if (setListHint != null && setListHint.activeSelf) h += 16f;
            return h;
        }

        private static void SettingsUpdateHint()
        {
            if (setListHint == null || setListViewport == null) return;
            bool over = SettingsActiveContentHeight() > SettingsViewportNoHint() + 0.5f;
            if (setListHint.activeSelf != over) setListHint.SetActive(over);
        }

        private static bool SettingsScreenContains(RectTransform rt, Vector2 p)
        {
            if (rt == null) return false;
            var c = new Vector3[4];
            rt.GetWorldCorners(c);
            return p.x >= c[0].x && p.x <= c[2].x && p.y >= c[0].y && p.y <= c[2].y;
        }

        /// <summary>Hover previews a row's help without moving the selection;
        /// a polled rect test at 10 Hz (the card tooltips' shape), never an
        /// EventTrigger: those interfaces need the UI assembly (design 6.2).</summary>
        private static void SettingsPollHover()
        {
            if (Time.unscaledTime < settingsHoverPollAt) return;
            settingsHoverPollAt = Time.unscaledTime + 0.1f;
            string hk = null;
            if (setListViewport != null)
            {
                // The driven pointer (witness W5 and the parked pointer of every
                // witness scenario) stands in for the mouse while a drive runs.
                Vector2 mp = settingsDriveMouseSet && SettingsDriveRunning ? settingsDriveMouse : (Vector2)Input.mousePosition;
                if (SettingsScreenContains(setListViewport.GetComponent<RectTransform>(), mp))
                    foreach (var r in SettingsFocusList(settingsSubTab))
                        if (r.Row != null && SettingsScreenContains(r.Row.GetComponent<RectTransform>(), mp)) { hk = r.Key; break; }
            }
            if (hk != settingsHoverKey) { settingsHoverKey = hk; settingsPaneDirty = true; }
        }

        // ---------------------------------------------------------------
        // The help pane (design section 6.1)
        // ---------------------------------------------------------------

        private static string SettingsReadMoreArticle(string key)
        {
            string k = null;
            switch (key)
            {
                case "SPing": case "SLagNotice": k = "netcode"; break;
                case "SBlkDbg": k = "blocking"; break;
                case "SAllowSpec": k = "spectating"; break;
                case "SCT": case "SAutoLog": k = "tracking"; break;
                case "SPcPub": case "SPcAnn": case "SPcTrd": k = "cards"; break;
                case "SPcPre": case "SPcDnc": k = "cards-pictures"; break;
                case "SAnimCos": case "STrail": case "SCursor": case "SAvAuto": case "SAvMod": case "SAvVan": k = "cosmetics"; break;
                case "SPColor": k = "colors"; break;
            }
            try { return (k != null && InfoLibrary.Find(k) != null) ? k : null; } catch { return null; }
        }

        private static void SettingsReadMoreClicked()
        {
            string k = settingsMoreKey;
            if (k == null) return;
            SwitchTab(TAB_INFO);
            SelectInfoArticle(k);
        }

        private static void SettingsSetActive(GameObject go, bool on)
        {
            if (go != null && go.activeSelf != on) go.SetActive(on);
        }

        private static void SettingsRenderPane()
        {
            settingsPaneDirty = false;
            if (setDetailGO == null) return;
            int privacy = SettingsModel.SubTabIndex("privacy");
            bool onPrivacy = settingsSubTab == privacy;
            // footer
            SettingsSetActive(setResetBtn, !settingsResetArmed);
            SettingsSetActive(setResetConfirmBtn, settingsResetArmed);
            SettingsSetActive(setResetCancelBtn, settingsResetArmed);
            SettingsSetActive(setDetSkipGO, onPrivacy && !settingsResetArmed);
            if (setResetBtn != null)
            {
                UIFactory.SetImageColor(setResetBtn, onPrivacy ? new Color(0.14f, 0.15f, 0.18f, 0.6f) : C_BTN);
                UIFactory.SetColor(UIFactory.GetButtonText(setResetBtn), onPrivacy ? C_DIM : C_WHITE);
            }

            string key = settingsPinnedKey ?? settingsHoverKey;
            if (key == null) { var f = SettingsFocusedRec(); key = f != null ? f.Key : null; }
            SettingsRowRec rec = null;
            if (key != null) settingsByKey.TryGetValue(key, out rec);

            if (settingsResetArmed) { SettingsRenderResetPrompt(); return; }
            if (rec == null)
            {
                UIFactory.SetTextNoHook(setDetTitleTxt, "");
                SettingsSetActive(setDetCurGO, false);
                SettingsSetActive(setDetRecGO, false);
                SettingsSetActive(setDetDetectedGO, false);
                UIFactory.SetTextNoHook(setDetBodyTxt, "");
                SettingsShowExtras(null);
                SettingsSetActive(setDetMoreBtn, false);
                return;
            }
            if (rec.Key == "SDR") { SettingsRenderDestructivePane(rec); return; }

            string title = SettingsSplits(rec.Kind) ? rec.LastLabel : rec.LastLabel;
            if (string.IsNullOrEmpty(title)) title = SettingsModel.StripTags(SettingsSplits(rec.Kind) ? rec.LastValue : rec.LastPainted);
            UIFactory.SetTextNoHook(setDetTitleTxt, title);

            // Currently: the value half; a disclosure's state word; nothing
            // for a pure action (design 6.1 item 2, section 16 Q4).
            if (rec.Kind == SettingsKind.Action) SettingsSetActive(setDetCurGO, false);
            else
            {
                string cv;
                if (rec.Kind == SettingsKind.Disclosure)
                {
                    bool ex = false;
                    try { ex = rec.Expanded != null && rec.Expanded(); } catch { }
                    cv = ex ? I18n.Tr("Expanded") : I18n.Tr("Collapsed");
                }
                else cv = rec.LastValue;
                UIFactory.SetTextNoHook(setDetCurTxt, I18n.TrF("Currently: {0}", cv));
                SettingsSetActive(setDetCurGO, true);
            }

            var d = SettingsDescriptors.Find(rec.Key);
            SettingsSetActive(setDetRecGO, true);
            if (d != null && d.StoresValue)
                UIFactory.SetTextNoHook(setDetRecTxt, I18n.TrF("Recommended: {0}", SettingsRecommendedValue(rec.Key)));
            else
                UIFactory.SetTextNoHook(setDetRecTxt, I18n.TrF("When to press this: {0}", SettingsDescriptors.WhenToPressTr(rec.Key) ?? ""));
            UIFactory.SetTextNoHook(setDetReasonTxt, SettingsDescriptors.ReasonTr(rec.Key) ?? "");

            bool isLang = rec.Key == "SLang";
            if (isLang)
            {
                // Round-2 L11: the detected language as a word, the same word the
                // Recommended line shows (design S16 Q3: "Detected: Svenska").
                // Design S5's raw-id rule is superseded for this one row.
                string det = "en";
                try { det = I18n.SuggestFromOs(); } catch { }
                UIFactory.SetTextNoHook(setDetDetectedTxt, I18n.TrF("Detected: {0}", LanguageName(det)));
            }
            SettingsSetActive(setDetDetectedGO, isLang);

            UIFactory.SetTextNoHook(setDetBodyTxt, SettingsBodyFor(rec));
            SettingsShowExtras(rec.Key);
            settingsMoreKey = SettingsReadMoreArticle(rec.Key);
            SettingsSetActive(setDetMoreBtn, settingsMoreKey != null);
        }

        private static string SettingsBodyFor(SettingsRowRec rec)
        {
            string hb = SettingsDescriptors.HelpBodyTr(rec.Key);
            string desc = rec.Desc ?? "";
            if (hb == null) return desc;
            return desc.Length == 0 ? hb : hb + "\n\n" + desc;
        }

        private static void SettingsShowExtras(string key)
        {
            bool pc = key == "SPcPub" || key == "SPcAnn" || key == "SPcTrd" || key == "SPcPre" || key == "SPcDnc";
            SettingsSetActive(setExtraSCS, key == "SCT");
            SettingsSetActive(setExtraSDD, key == "SDR");
            SettingsSetActive(setExtraSDD2, key == "SDR");
            SettingsSetActive(setExtraSDS, key == "SDR");
            SettingsSetActive(setExtraLangNote, key == "SLang");
            SettingsSetActive(setExtraPcInfo, pc);
            SettingsSetActive(setDetPrevGO, key == "SPcPre");
            bool any = key == "SCT" || key == "SDR" || key == "SLang" || pc;
            SettingsSetActive(setDetExtrasGO, any);
        }

        /// <summary>The one combined destructive pane: three entries, each
        /// with its title, when-to-press and reason, readable without
        /// arming, confirming or cancelling anything (design 6.1).</summary>
        private static void SettingsRenderDestructivePane(SettingsRowRec grp)
        {
            UIFactory.SetTextNoHook(setDetTitleTxt, I18n.Tr("Delete My Data"));
            UIFactory.SetTextNoHook(setDetCurTxt, I18n.TrF("Currently: {0}", deleteArmed ? I18n.Tr("Armed") : I18n.Tr("Not armed")));
            SettingsSetActive(setDetCurGO, true);
            SettingsSetActive(setDetRecGO, false);
            SettingsSetActive(setDetDetectedGO, false);
            var sb = new StringBuilder();
            if (grp.Members != null)
                foreach (var m in grp.Members)
                {
                    if (sb.Length > 0) sb.Append("\n\n");
                    string t = string.IsNullOrEmpty(m.LastLabel) ? m.Key : m.LastLabel;
                    sb.Append("<b>").Append(t).Append("</b>\n");
                    sb.Append(I18n.TrF("When to press this: {0}", SettingsDescriptors.WhenToPressTr(m.Key) ?? "")).Append('\n');
                    sb.Append(SettingsDescriptors.ReasonTr(m.Key) ?? "");
                    string hb = SettingsDescriptors.HelpBodyTr(m.Key);
                    if (!string.IsNullOrEmpty(hb)) sb.Append('\n').Append(hb);
                }
            UIFactory.SetTextNoHook(setDetBodyTxt, sb.ToString());
            SettingsShowExtras("SDR");
            settingsMoreKey = null;
            SettingsSetActive(setDetMoreBtn, false);
        }

        private static void SettingsPaintDeleteState(bool armed)
        {
            // The keyboard confirm guard counts from the moment the armed
            // state was first painted, whichever input armed it, so a mouse
            // arm cannot leave a stale or missing timestamp behind.
            if (armed) { if (settingsDeleteArmedAt < 0f) settingsDeleteArmedAt = Time.unscaledTime; }
            else settingsDeleteArmedAt = -1f;
            if (settingsDeleteStateTxt != null)
                UIFactory.SetTextNoHook(settingsDeleteStateTxt, armed ? I18n.Tr("Armed") : I18n.Tr("Not armed"));
        }

        // ---------------------------------------------------------------
        // Reset this tab to recommended (design section 6.4)
        // ---------------------------------------------------------------

        private static void SettingsRenderResetPrompt()
        {
            string home = SettingsModel.SubTabHomes[Mathf.Clamp(settingsSubTab, 0, SETTINGS_TABS - 1)];
            UIFactory.SetTextNoHook(setDetTitleTxt, SettingsDescriptors.SubTabLabelTr(home));
            SettingsSetActive(setDetCurGO, false);
            SettingsSetActive(setDetRecGO, false);
            SettingsSetActive(setDetDetectedGO, false);
            var sb = new StringBuilder();
            sb.Append(I18n.Tr("Reset this tab to recommended?"));
            foreach (var d in SettingsDescriptors.All)
            {
                if (d.Home != home || d.BulkReset) continue;
                string why = SettingsDescriptors.ExclusionReasonTr(d.Key);
                if (string.IsNullOrEmpty(why)) continue;
                SettingsRowRec r;
                string name = d.Key;
                if (settingsByKey.TryGetValue(d.Key, out r) && !string.IsNullOrEmpty(r.LastLabel)) name = r.LastLabel;
                sb.Append("\n\n<b>").Append(name).Append("</b>: ").Append(why);
            }
            UIFactory.SetTextNoHook(setDetBodyTxt, sb.ToString());
            SettingsShowExtras(null);
            SettingsSetActive(setDetMoreBtn, false);
        }

        private static void SettingsResetClicked()
        {
            if (settingsSubTab == SettingsModel.SubTabIndex("privacy")) return;   // drawn disabled: nothing here is bulk-written
            settingsResetArmed = true;
            SettingsRenderPane();
        }

        private static void SettingsResetCancel()
        {
            settingsResetArmed = false;
            SettingsRenderPane();
        }

        /// <summary>Writes exactly the active tab's bulk rows, through each
        /// row's named writer with its typed operand (SettingsModel.ResetSet,
        /// SettingsDescriptorWriters.InvokeReset). A writer that rebuilds the
        /// page defers the rebuild to after the last write.</summary>
        private static void SettingsResetConfirm()
        {
            if (!settingsResetArmed) return;
            settingsResetArmed = false;
            string home = SettingsModel.SubTabHomes[Mathf.Clamp(settingsSubTab, 0, SETTINGS_TABS - 1)];
            var keys = SettingsModel.ResetSet(home);
            int wrote = 0;
            settingsResetDepth++;
            try
            {
                foreach (var k in keys)
                {
                    try { if (SettingsDescriptorWriters.InvokeReset(k)) wrote++; }
                    catch (Exception e) { Plugin.Log.LogWarning("[SETTINGS] reset " + k + ": " + e.Message); }
                }
            }
            finally { settingsResetDepth--; }
            Plugin.Log.LogInfo("[SETTINGS] reset tab " + home + ": wrote " + wrote + " of " + keys.Count
                + " [" + string.Join(",", keys.ToArray()) + "]");
            dirty = true;
            settingsPaneDirty = true;
            if (settingsRebuildOwed && settingsResetDepth == 0)
            {
                settingsRebuildOwed = false;
                SettingsRebuildPage();
            }
        }

        /// <summary>The public page path every in-tab rebuild takes (Close,
        /// destroy, pageBuilt=false, Open, back to the tab), never a bare
        /// pageBuilt flip: Tick's early return would strand Escape.</summary>
        internal static void SettingsRebuildPage()
        {
            int backTo = currentTab;
            Close();
            if (pageGO != null) UnityEngine.Object.Destroy(pageGO);
            pageBuilt = false;
            Open();
            SwitchTab(backTo);
        }

        // ---------------------------------------------------------------
        // Keyboard and controller (design section 6.3)
        // ---------------------------------------------------------------

        /// <summary>Per frame while the settings tab is the active tab. Modal
        /// input ownership is read FIRST and live: nothing absorbs a raw
        /// keystroke, so a space typed into the bug report must never reach
        /// a row (design 6.3, T5-a).</summary>
        internal static void TickSettingsInput()
        {
            if (CompetitiveUI.KeyboardInputOwnedByModal) return;
            if (CompetitiveUI.ChatTypingOwnsKeyboard) return;
            if (!isOpen || !pageBuilt || currentTab != TAB_SETTINGS) return;
            SettingsPollHover();
            if (Time.unscaledTime >= settingsHintPollAt)
            {
                settingsHintPollAt = Time.unscaledTime + 0.1f;
                SettingsUpdateHint();
            }
            SettingsDispatchKey(SettingsReadKey());
            SettingsPollAxes();
            SettingsPollPad();
            if (settingsPaneDirty) SettingsRenderPane();
        }

        /// <summary>The controller's buttons (SettingsModel.PadKey): the
        /// shoulders move between the sub-tabs and the bottom face button
        /// activates the focused row as a pad press. Read through Unity's
        /// joystick button codes; a button the driven-input harness pressed
        /// counts as held down this frame. Whether a real pad reaches these
        /// codes on this build is witness W7.</summary>
        private static void SettingsPollPad()
        {
            int driven = SettingsTakeDrivePad();
            bool prev, next, act;
            try
            {
                prev = driven == SettingsModel.PadPrevTabButton || Input.GetKeyDown(SettingsPadCode(SettingsModel.PadPrevTabButton));
                next = driven == SettingsModel.PadNextTabButton || Input.GetKeyDown(SettingsPadCode(SettingsModel.PadNextTabButton));
                act = driven == SettingsModel.PadActivateButton || Input.GetKeyDown(SettingsPadCode(SettingsModel.PadActivateButton));
            }
            catch { return; }
            SettingsDispatchKey(SettingsModel.PadKey(prev, next, act));
        }

        private static KeyCode SettingsPadCode(int button) { return (KeyCode)((int)KeyCode.JoystickButton0 + button); }

        /// <summary>This frame's key, one per frame in the order the page
        /// has always read them; a key the driven-input harness pressed is
        /// taken first, so it passes the same gates a real key does. Enter
        /// (either Return or the keypad's) and Space come back as DIFFERENT
        /// keys: a destructive row takes Enter only (design 6.3), so the
        /// source must survive to the row.</summary>
        private static SettingsModel.SettingsKey SettingsReadKey()
        {
            SettingsModel.SettingsKey driven;
            if (SettingsTakeDriveKey(out driven)) return driven;   // the driven-input harness's press
            bool shift = Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift);
            if (Input.GetKeyDown(KeyCode.Tab)) return shift ? SettingsModel.SettingsKey.ShiftTab : SettingsModel.SettingsKey.Tab;
            if (Input.GetKeyDown(KeyCode.UpArrow)) return SettingsModel.SettingsKey.Up;
            if (Input.GetKeyDown(KeyCode.DownArrow)) return SettingsModel.SettingsKey.Down;
            if (Input.GetKeyDown(KeyCode.LeftArrow)) return SettingsModel.SettingsKey.Left;
            if (Input.GetKeyDown(KeyCode.RightArrow)) return SettingsModel.SettingsKey.Right;
            if (Input.GetKeyDown(KeyCode.Return) || Input.GetKeyDown(KeyCode.KeypadEnter)) return SettingsModel.SettingsKey.Enter;
            if (Input.GetKeyDown(KeyCode.Space)) return SettingsModel.SettingsKey.Space;
            if (Input.GetKeyDown(KeyCode.F1)) return SettingsModel.SettingsKey.Pin;
            return SettingsModel.SettingsKey.None;
        }

        /// <summary>One key onto the page (SettingsModel.DispatchKey). The
        /// keyboard poll and the driven-input harness both come through here.</summary>
        private static void SettingsDispatchKey(SettingsModel.SettingsKey key)
        {
            if (key == SettingsModel.SettingsKey.None) return;
            SettingsModel.DispatchKey(key, settingsSubTab, SETTINGS_TABS,
                SettingsSwitchSubTab, SettingsMoveFocus, SettingsStep, SettingsActivate, SettingsTogglePin);
        }

        /// <summary>Stick/pad axes through an edge detector, read only while no
        /// key is held so the arrows (which drive the same axes) never count
        /// twice. Whether this build's pad produces these axes is witness W7.</summary>
        private static void SettingsPollAxes()
        {
            if (settingsAxisBroken) return;
            if (Input.anyKey) { settingsAxisX = 0; settingsAxisY = 0; return; }
            float ax, ay;
            try { ax = Input.GetAxisRaw("Horizontal"); ay = Input.GetAxisRaw("Vertical"); }
            catch { settingsAxisBroken = true; return; }
            int sx = ax > 0.6f ? 1 : ax < -0.6f ? -1 : 0;
            int sy = ay > 0.6f ? 1 : ay < -0.6f ? -1 : 0;
            if (sy != 0 && sy != settingsAxisY) SettingsMoveFocus(-sy);
            if (sx != 0 && sx != settingsAxisX) SettingsStep(sx);
            settingsAxisX = sx;
            settingsAxisY = sy;
        }

        private static void SettingsMoveFocus(int delta)
        {
            var list = SettingsFocusList(settingsSubTab);
            if (list.Count == 0) return;
            int i = Mathf.Clamp(settingsFocusRow[settingsSubTab] + delta, 0, list.Count - 1);
            settingsFocusRow[settingsSubTab] = i;
            settingsPinnedKey = null;
            SettingsUpdateFocusHighlight();
            SettingsEnsureVisible(list[i]);
            settingsPaneDirty = true;
        }

        private static void SettingsEnsureVisible(SettingsRowRec rec)
        {
            try
            {
                if (rec == null || rec.Row == null || setListViewport == null || setListContentRT == null) return;
                var vp = setListViewport.GetComponent<RectTransform>();
                var rc = new Vector3[4]; rec.Row.GetComponent<RectTransform>().GetWorldCorners(rc);
                var vc = new Vector3[4]; vp.GetWorldCorners(vc);
                float scale = vp.lossyScale.y > 0f ? vp.lossyScale.y : 1f;
                var pos = setListContentRT.anchoredPosition;
                if (rc[1].y > vc[1].y) pos.y -= (rc[1].y - vc[1].y) / scale;
                else if (rc[0].y < vc[0].y) pos.y += (vc[0].y - rc[0].y) / scale;
                else return;
                float maxY = Mathf.Max(0f, setListContentRT.rect.height - vp.rect.height);
                pos.y = Mathf.Clamp(pos.y, 0f, maxY);
                setListContentRT.anchoredPosition = pos;
            }
            catch { }
        }

        private static void SettingsStep(int dir)
        {
            var rec = SettingsFocusedRec();
            if (rec == null) return;
            switch (rec.Kind)
            {
                case SettingsKind.Switch:
                {
                    bool on = false;
                    try { on = rec.GetBool != null && rec.GetBool(); } catch { }
                    if ((dir > 0) != on && rec.Toggle != null) rec.Toggle();
                    break;
                }
                case SettingsKind.Segmented:
                {
                    string cur = null;
                    try { cur = rec.Current != null ? rec.Current() : null; } catch { }
                    int i = 0;
                    for (int k = 0; k < rec.Ids.Length; k++)
                        if (string.Equals(rec.Ids[k], cur, StringComparison.OrdinalIgnoreCase)) { i = k; break; }
                    int j = Mathf.Clamp(i + dir, 0, rec.Ids.Length - 1);
                    if (j != i) SettingsPickValue(rec, rec.Ids[j]);
                    break;
                }
                case SettingsKind.Slider:
                {
                    int cur = rec.LastIdx >= 0 ? rec.LastIdx : 0;
                    int j = Mathf.Clamp(cur + dir, 0, rec.Stops.Length - 1);
                    if (j != cur) SettingsSetSliderIndex(rec, j);
                    break;
                }
                case SettingsKind.Dropdown:
                    SettingsOpenDropdown(rec);
                    break;
                case SettingsKind.Disclosure:
                {
                    bool ex = false;
                    try { ex = rec.Expanded != null && rec.Expanded(); } catch { }
                    if ((dir > 0) != ex && rec.Toggle != null) rec.Toggle();
                    break;
                }
                // ACTION: nothing to step. DESTRUCTIVE: excluded by rule.
            }
            settingsPaneDirty = true;
        }

        /// <summary>The descriptor's kind word for a row kind ("DESTRUCTIVE").</summary>
        private static string SettingsKindWord(SettingsKind kind) { return kind.ToString().ToUpperInvariant(); }

        /// <summary>Activate the focused row from one source. Which kinds take
        /// which source is SettingsModel.ActivationAccepts (design 6.3): a
        /// destructive row refuses anything but Enter, so a Space press on it
        /// does nothing at the arm and nothing at the confirm.</summary>
        private static void SettingsActivate(SettingsModel.SettingsActivation source)
        {
            var rec = SettingsFocusedRec();
            if (rec == null) return;
            if (!SettingsModel.ActivationAccepts(SettingsKindWord(rec.Kind), source)) return;
            switch (rec.Kind)
            {
                case SettingsKind.Action:
                    if (rec.Act != null) rec.Act();
                    break;
                case SettingsKind.Dropdown:
                    SettingsOpenDropdown(rec);
                    break;
                case SettingsKind.Destructive:
                    SettingsActivateDelete(rec);
                    break;
                // DISCLOSURE: Left and Right only (SettingsStep), never Enter or Space.
            }
            settingsPaneDirty = true;
        }

        /// <summary>Enter on the delete row arms it; Enter again confirms, and
        /// only once the armed state has been on screen for a full second, so
        /// a held or doubled key cannot arm and confirm in one gesture. Only
        /// Enter reaches this method: SettingsActivate refuses every other
        /// source on a destructive row before it gets here.</summary>
        private static void SettingsActivateDelete(SettingsRowRec grp)
        {
            if (grp.Members == null) return;
            SettingsRowRec arm = null, confirm = null;
            foreach (var m in grp.Members)
            {
                if (m.Key == "SDBtn") arm = m;
                else if (m.Key == "SDCBtn") confirm = m;
            }
            if (!deleteArmed)
            {
                if (arm != null && arm.Act != null) { arm.Act(); settingsDeleteArmedAt = Time.unscaledTime; }
            }
            else if (settingsDeleteArmedAt >= 0f && Time.unscaledTime - settingsDeleteArmedAt >= 1f)
            {
                if (confirm != null && confirm.Act != null) confirm.Act();
            }
        }

        private static void SettingsTogglePin()
        {
            var f = SettingsFocusedRec();
            if (f == null) return;
            settingsPinnedKey = settingsPinnedKey == f.Key ? null : f.Key;
            settingsPaneDirty = true;
        }

        /// <summary>The TestOpenTab lever's settings grammar (broadcast seat):
        /// "selftest", "drive", "drive:&lt;id&gt;[,&lt;id&gt;]", "&lt;sub-tab&gt;",
        /// "&lt;sub-tab&gt;:expand", "&lt;sub-tab&gt;:&lt;key&gt;". A sub-tab is its
        /// home id, its body name or its index.</summary>
        internal static void DevSettingsDirective(string d)
        {
            try
            {
                d = (d ?? "").Trim();
                if (d.Length == 0) return;
                if (string.Equals(d, "selftest", StringComparison.OrdinalIgnoreCase)) { SettingsSelfTestStart("lever"); return; }
                if (d.StartsWith("selftest:", StringComparison.OrdinalIgnoreCase)) { SettingsSelfTestStart("lever", d.Substring(9)); return; }
                if (string.Equals(d, "drive", StringComparison.OrdinalIgnoreCase)) { SettingsDriveStart(""); return; }
                if (d.StartsWith("drive:", StringComparison.OrdinalIgnoreCase)) { SettingsDriveStart(d.Substring(6)); return; }
                string[] p = d.Split(':');
                int idx = SettingsModel.SubTabIndex(p[0].Trim());
                int n;
                if (idx < 0 && int.TryParse(p[0].Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out n) && n >= 0 && n < SETTINGS_TABS) idx = n;
                if (idx < 0) { Plugin.Log.LogWarning("[SETTINGS] lever: unknown sub-tab '" + p[0] + "'"); return; }
                SettingsSwitchSubTab(idx);
                if (p.Length > 1)
                {
                    string a = p[1].Trim();
                    if (string.Equals(a, "expand", StringComparison.OrdinalIgnoreCase)) SettingsExpandTab(idx);
                    else SettingsSelectKey(a);
                }
                Plugin.Log.LogInfo("[SETTINGS] lever -> sub-tab " + SettingsModel.SubTabHomes[idx] + (p.Length > 1 ? " (" + p[1].Trim() + ")" : ""));
            }
            catch (Exception e) { Plugin.Log.LogWarning("[SETTINGS] lever failed: " + e.Message); }
        }

        /// <summary>Paint readiness (round-2 M2). settingsBuildGen counts page
        /// builds (SettingsBeginBuild); settingsPaintedGen is the build the
        /// last COMPLETE RefreshSettings pass painted (SettingsAfterRefresh is
        /// its last step, so a pass that throws part-way never counts).
        /// Between a rebuild and the new page's first paint pass every row's
        /// text is still empty - and a language pack that lands after a
        /// locale switch rebuilds the page on its own clock (I18n.ApplyPack ->
        /// RequestCatalogueRebuild), so the self-test measures only a page
        /// whose two numbers match.</summary>
        private static int settingsBuildGen, settingsPaintedGen = -1;

        /// <summary>The last step of every RefreshSettings pass.</summary>
        private static void SettingsAfterRefresh()
        {
            settingsPaintedGen = settingsBuildGen;
            SettingsPaintDeleteState(deleteArmed);
            SettingsUpdateHint();
            SettingsRenderPane();
            if (!settingsSelfTestEnvChecked)
            {
                settingsSelfTestEnvChecked = true;
                string env = null;
                try { env = Environment.GetEnvironmentVariable("SCR_SETTINGS_SELFTEST"); } catch { }
                if (env == "1") SettingsSelfTestStart("env");
            }
        }

        // ---------------------------------------------------------------
        // Self-test (design section 10, T2b and T3; gated on the
        // SCR_SETTINGS_SELFTEST=1 environment variable or the lever)
        // ---------------------------------------------------------------

        private static bool settingsSelfTestEnvChecked;
        private static int stPhase = -1, stTab, stPass, stFail, stSavedTab, stRetry;
        private static float stWaitUntil;
        private static bool stSavedPerfOpen;

        /// <summary>The self-test's mutation switch (lever "5:selftest:NAME"),
        /// empty for the control run. Each named mutation breaks exactly one
        /// assertion's subject at run time, so that assertion must red while
        /// the others stay green. Only the control run sweeps the four other
        /// locales for A2a (design residual 3) - and the two A2a sweep
        /// fixtures (round-2 M2), which are inputs rather than mutations:
        /// "a2a-blank" empties 12 of the Swedish pass's In-game cells at
        /// measurement time, the count the round-1 sweep hid, and
        /// "a2a-rebuild" rebuilds the page in the Tick just before that
        /// measurement, the race a late language pack creates.</summary>
        private static string stMutation = "";
        private static readonly string[] SettingsSelfTestMutations =
            { "a1-shift", "a2a-zero", "a2a-narrow", "a2b-short", "a5-tall", "a7-noremember", "a8-nohint", "s15-long",
              "a2a-blank", "a2a-rebuild" };
        private static bool SettingsSweepRuns => stMutation.Length == 0 || stMutation == "a2a-blank" || stMutation == "a2a-rebuild";

        /// <summary>A2a's denominator (round-2 M2): the cells the base pass
        /// measured on each sub-tab, by id ("SIgChat/label", "SIgChat/opt1").
        /// Every locale pass must measure the same set, so a cell that drops
        /// out of the loop is named rather than silently uncounted.</summary>
        private static readonly List<string>[] stBaseCells = new List<string>[SETTINGS_TABS];
        private static int stReadyRetry;
        private static bool stRebuildFixtureDone;
        private static readonly string[] SettingsSweepLocales = { "es", "ru", "uk", "sv" };
        private static int stSweepIdx, stPrefBefore;
        private static string stOrigLocale;
        private static bool settingsSelfTestSkipRemember;

        /// <summary>The sweep's repaint proof: the base pass records every row
        /// label and sub-tab label as painted in the original locale, and each
        /// locale pass counts how many now read differently, so a pass that
        /// measured a page still painted in English cannot report green.</summary>
        private static readonly Dictionary<string, string> stBaseLabels = new Dictionary<string, string>();
        private static readonly string[] stBaseSubLabels = new string[SETTINGS_TABS];
        private static int stSweepDiffer, stSweepRows, stSweepSubDiffer;

        /// <summary>True while the settings self-test runs. The broadcast
        /// seat's idle-close reads it: a self-test is an operator session,
        /// and a page closed under it stalls the run mid-phase.</summary>
        internal static bool SettingsSelfTestRunning => stPhase >= 0;

        /// <summary>Design section 15 (Sid's ruling): measurement decides
        /// whether a segmented row stays segmented. Every A2a pass records
        /// each row's widest option word against the segment width; SBloom
        /// and SShake change kind together, the other three decide alone.
        /// The widest word and the locale it was measured in are kept so the
        /// verdict can name them.</summary>
        private static readonly string[] SettingsSegFitRows = { "SBloom", "SShake", "SMenuMus", "SIgChat", "SHpPrec" };
        private const float SettingsSegmentWidth = 142f;
        private static readonly Dictionary<string, float> stSegMax = new Dictionary<string, float>();
        private static readonly Dictionary<string, string> stSegWidest = new Dictionary<string, string>();
        private static readonly HashSet<string> stSegLocales = new HashSet<string>();

        /// <summary>The keys the page paints through SetTextRaw (T2b control
        /// a): the lane's twenty (design 3.3) plus SCT, whose new painter
        /// composes its state word after translation and so writes raw, plus
        /// SPcDnc (dance cards, merge pass 3), whose label carries a colour tag.</summary>
        private static readonly string[] SettingsRawPainted =
        {
            "SCT", "SChatTtl", "SCursor", "SBloom", "SShake", "SHpPrec", "SLang", "SDateFmt", "SPerfH",
            "SPerf_Master", "SPerf_Stun", "SPerf_OOB", "SPerf_HitSnd", "SPerf_EdgeBn", "SPerf_Menu",
            "SPerf_BulletCap", "SPerf_PoolInit", "SMailFrom", "SMailRelay", "SMailBlocked", "SPcPre",
            "SPcDnc", "SAvMod", "SAvVan",
        };

        private static void SettingsSelfTestStart(string why, string mutation = "")
        {
            if (stPhase >= 0 || SettingsDriveRunning) { Plugin.Log.LogInfo("[SETTINGS-SELFTEST] a settings test is already running"); return; }
            mutation = (mutation ?? "").Trim().ToLowerInvariant();
            if (mutation.Length > 0 && Array.IndexOf(SettingsSelfTestMutations, mutation) < 0)
            {
                Plugin.Log.LogWarning("[SETTINGS-SELFTEST] unknown mutation '" + mutation + "'; known: " + string.Join(",", SettingsSelfTestMutations));
                return;
            }
            stMutation = mutation;
            stSegMax.Clear(); stSegWidest.Clear(); stSegLocales.Clear();
            for (int i = 0; i < SETTINGS_TABS; i++) stBaseCells[i] = null;
            stReadyRetry = 0; stRebuildFixtureDone = false;
            stPhase = 0; stTab = 0; stPass = 0; stFail = 0; stRetry = 0; stWaitUntil = 0f; stSweepIdx = 0;
            stSavedTab = settingsSubTab;
            stSavedPerfOpen = _perfSectionOpen;
            string lang = "?";
            try { lang = Plugin.ModLanguage != null ? Plugin.ModLanguage.Value : "?"; } catch { }
            Plugin.Log.LogInfo("[SETTINGS-SELFTEST] START (" + why + ") screen " + Screen.width + "x" + Screen.height
                + " canvas " + SettingsCanvasHeight().ToString("0", CultureInfo.InvariantCulture) + " locale " + lang
                + (stMutation.Length > 0 ? " MUTATION " + stMutation : " (control run)"));
        }

        private static void StOk(string msg) { stPass++; Plugin.Log.LogInfo("[SETTINGS-LAYOUT] PASS " + msg); }
        private static void StBad(string msg) { stFail++; Plugin.Log.LogWarning("[SETTINGS-LAYOUT] FAIL " + msg); }
        private static void StNote(string msg) { Plugin.Log.LogInfo("[SETTINGS-LAYOUT] " + msg); }

        private static void SettingsForceLayout()
        {
            try { UIFactory.tCanvas?.GetMethod("ForceUpdateCanvases", BindingFlags.Public | BindingFlags.Static)?.Invoke(null, null); } catch { }
        }

        private static float SettingsCanvasHeight()
        {
            try { return overlayCanvasGO != null ? overlayCanvasGO.GetComponent<RectTransform>().rect.height : 0f; } catch { return 0f; }
        }

        private static float SettingsCanvasScale()
        {
            try { float s = overlayCanvasGO != null ? overlayCanvasGO.transform.lossyScale.x : 1f; return s > 0f ? s : 1f; } catch { return 1f; }
        }

        private static Rect SettingsWorldRect(GameObject go)
        {
            var c = new Vector3[4];
            go.GetComponent<RectTransform>().GetWorldCorners(c);
            return Rect.MinMaxRect(c[0].x, c[0].y, c[2].x, c[2].y);
        }

        private static bool SettingsInside(Rect outer, Rect inner, float tol)
        {
            return inner.xMin >= outer.xMin - tol && inner.xMax <= outer.xMax + tol
                && inner.yMin >= outer.yMin - tol && inner.yMax <= outer.yMax + tol;
        }

        private static Transform SettingsFindDeep(Transform root, string name)
        {
            if (root == null) return null;
            if (root.name == name) return root;
            for (int i = 0; i < root.childCount; i++)
            {
                var f = SettingsFindDeep(root.GetChild(i), name);
                if (f != null) return f;
            }
            return null;
        }

        private static int SettingsCountDeep(Transform root, string name)
        {
            if (root == null) return 0;
            int n = root.name == name ? 1 : 0;
            for (int i = 0; i < root.childCount; i++) n += SettingsCountDeep(root.GetChild(i), name);
            return n;
        }

        private static bool SettingsUnder(Transform t, Transform ancestor)
        {
            for (var a = t; a != null; a = a.parent) if (a == ancestor) return true;
            return false;
        }

        internal static void SettingsSelfTestTick()
        {
            if (stPhase < 0) return;
            if (Time.unscaledTime < stWaitUntil) return;
            try
            {
                switch (stPhase)
                {
                    case 0: SelfTestStatic(); stPhase = 1; stTab = 0; break;
                    case 1: SelfTestOpenTab(); stPhase = 2; stWaitUntil = Time.unscaledTime + 0.6f; break;
                    case 2:
                        if (!SelfTestPaintReady("A2a " + SettingsModel.SubTabHomes[stTab])) break;
                        SelfTestCheckTab();
                        stTab++;
                        stPhase = stTab < SETTINGS_TABS ? 1 : 3;
                        break;
                    case 3:
                        // A7: rebuild through the catalogue route with a
                        // non-zero sub-tab remembered.
                        _perfSectionOpen = stSavedPerfOpen;
                        if (_perfSectionBody != null) _perfSectionBody.SetActive(_perfSectionOpen);
                        SettingsSwitchSubTab(3);
                        settingsSelfTestSkipRemember = stMutation == "a7-noremember";
                        RequestCatalogueRebuild();
                        stPhase = 4;
                        stWaitUntil = Time.unscaledTime + 2.5f;
                        break;
                    case 4: SelfTestAfterRebuild(); break;
                    case 5: SelfTestSweepNext(); break;
                    case 6: SelfTestSweepOpenTab(); break;
                    case 7: SelfTestSweepCheckTab(); break;
                    case 8: SelfTestSweepRestored(); break;
                }
            }
            catch (Exception e)
            {
                StBad("self-test threw in phase " + stPhase + ": " + e.GetType().Name + " " + e.Message);
                SelfTestFinish();
            }
        }

        private static void SelfTestFinish()
        {
            // A throw mid-sweep must not leave the player on a locale they
            // did not pick: put the original back through the same route.
            if (stOrigLocale != null && I18n.Locale != stOrigLocale)
            {
                try { I18n.SetLocale(stOrigLocale); RequestCatalogueRebuild(); } catch { }
            }
            stOrigLocale = null;
            settingsSelfTestSkipRemember = false;
            _perfSectionOpen = stSavedPerfOpen;
            if (_perfSectionBody != null) _perfSectionBody.SetActive(_perfSectionOpen);
            Plugin.Log.LogInfo("[SETTINGS-SELFTEST] DONE" + (stMutation.Length > 0 ? " MUTATION " + stMutation : " (control run)")
                + " pass=" + stPass + " fail=" + stFail);
            stPhase = -1;
            stMutation = "";
            try { SettingsSwitchSubTab(Mathf.Clamp(stSavedTab, 0, SETTINGS_TABS - 1)); } catch { }
        }

        private static void SelfTestResetCounts()
        {
            foreach (var r in settingsByKey.Values) r.Paints = 0;
        }

        private static List<string> SelfTestZeroSet()
        {
            var z = new List<string>();
            foreach (var d in SettingsDescriptors.All)
            {
                SettingsRowRec r;
                if (!settingsByKey.TryGetValue(d.Key, out r) || r.Paints == 0) z.Add(d.Key);
            }
            z.Sort(StringComparer.Ordinal);
            return z;
        }

        private static string SelfTestJoin(List<string> a) { return a.Count == 0 ? "-" : string.Join(",", a.ToArray()); }

        /// <summary>T2b and its two controls, A4, A6 and A3: everything that
        /// needs no sub-tab switch.</summary>
        private static void SelfTestStatic()
        {
            // T2b: one RefreshSettings pass paints every key exactly once.
            SelfTestResetCounts();
            RefreshSettings();
            int ok = 0;
            foreach (var d in SettingsDescriptors.All)
            {
                SettingsRowRec r;
                int n = settingsByKey.TryGetValue(d.Key, out r) ? r.Paints : -1;
                if (n == 1) ok++;
                else StBad("T2b " + d.Key + ": painted " + n + " time(s) in one pass, expected 1");
            }
            if (ok == SettingsDescriptors.All.Length) StOk("T2b " + ok + " of " + SettingsDescriptors.All.Length + " keys painted exactly once");
            // control (a): every SetTextRaw write suppressed -> exactly the raw set is at zero.
            SelfTestResetCounts();
            settingsSelfTestSuppressRaw = true;
            try { RefreshSettings(); } finally { settingsSelfTestSuppressRaw = false; }
            var zeroA = SelfTestZeroSet();
            var expA = new List<string>(SettingsRawPainted);
            expA.Sort(StringComparer.Ordinal);
            if (SelfTestJoin(zeroA) == SelfTestJoin(expA)) StOk("T2b control (a): SetTextRaw suppressed -> " + zeroA.Count + " keys at 0, the declared raw set");
            else StBad("T2b control (a): zero set [" + SelfTestJoin(zeroA) + "] expected [" + SelfTestJoin(expA) + "]");
            // control (b): one painter skipped -> exactly that key at zero.
            SelfTestResetCounts();
            settingsSelfTestSkipKey = "SPerf_Stun";
            try { RefreshSettings(); } finally { settingsSelfTestSkipKey = null; }
            var zeroB = SelfTestZeroSet();
            if (SelfTestJoin(zeroB) == "SPerf_Stun") StOk("T2b control (b): SPerf_Stun's paint skipped -> exactly SPerf_Stun at 0");
            else StBad("T2b control (b): zero set [" + SelfTestJoin(zeroB) + "] expected [SPerf_Stun]");
            RefreshSettings();

            // A4: every key resolves to exactly one body, its descriptor's home.
            var root = (settingsBodies[0] != null) ? settingsBodies[0].transform.parent : null;
            int a4 = 0;
            foreach (var d in SettingsDescriptors.All)
            {
                SettingsRowRec r;
                if (!settingsByKey.TryGetValue(d.Key, out r)) { StBad("A4 " + d.Key + ": no row built"); continue; }
                var go = r.Kind == SettingsKind.Destructive && r.Button != null ? r.Button : r.Row;
                int home = SettingsModel.SubTabIndex(d.Home);
                int bodies = 0, at = -1;
                for (int i = 0; i < SETTINGS_TABS; i++)
                    if (settingsBodies[i] != null && go != null && SettingsUnder(go.transform, settingsBodies[i].transform)) { bodies++; at = i; }
                int named = SettingsCountDeep(root, d.Key);
                if (bodies == 1 && at == home && named == 1) a4++;
                else StBad("A4 " + d.Key + ": " + bodies + " bodies (at " + (at >= 0 ? SettingsModel.SubTabBodies[at] : "-") + "), home "
                    + d.Home + ", " + named + " object(s) named " + d.Key);
            }
            if (a4 == SettingsDescriptors.All.Length) StOk("A4 " + a4 + " keys, each under exactly one body, its descriptor's home");

            // A6: help, recommendation-or-when, reason, byte-equality, help target.
            int a6 = 0;
            foreach (var d in SettingsDescriptors.All)
            {
                SettingsRowRec r;
                settingsByKey.TryGetValue(d.Key, out r);
                string why = null;
                bool destructive = d.Kind == "DESTRUCTIVE";
                string body = r != null ? SettingsBodyFor(r) : "";
                if (string.IsNullOrEmpty(body) && destructive && setExtraSDD != null) body = "SDD";
                if (string.IsNullOrEmpty(body)) why = "empty help body";
                else if (string.IsNullOrEmpty(SettingsDescriptors.ReasonTr(d.Key))) why = "empty reason";
                else if (d.StoresValue)
                {
                    string got = SettingsModel.StripTags(SettingsRecommendedValue(d.Key));
                    string want = null;
                    try { want = SettingsDescriptorWriters.RenderExpression(d.Key); } catch { }
                    if (want == null) want = d.RecValue;
                    if (string.IsNullOrEmpty(got)) why = "recommended value renders empty";
                    else if (want == null) why = "no recommended value on the descriptor";
                    else if (got != want && got != I18n.Tr(want) && got != SettingsModel.StripTags(I18n.Tr(want)))
                        why = "recommended '" + got + "' is not byte-equal to the painter's '" + want + "'";
                }
                else if (string.IsNullOrEmpty(SettingsDescriptors.WhenToPressTr(d.Key))) why = "empty when-to-press";
                if (why == null && (string.IsNullOrEmpty(d.HelpTargetId) || d.HelpTargetId == d.Key)) why = "help target is the key's own actuating control";
                if (why == null && root != null && SettingsFindDeep(root, d.HelpTargetId) == null) why = "help target " + d.HelpTargetId + " not built";
                if (why == null) a6++;
                else StBad("A6 " + d.Key + ": " + why);
            }
            if (a6 == SettingsDescriptors.All.Length) StOk("A6 " + a6 + " keys: help, recommendation or when-to-press, reason, byte-equal values, help targets");

            // A3: the two columns fill the row.
            SettingsForceLayout();
            if (settingsColsGO != null && setListGO != null && setDetailGO != null)
            {
                float cw = settingsColsGO.GetComponent<RectTransform>().rect.width;
                float occ = setListGO.GetComponent<RectTransform>().rect.width + setDetailGO.GetComponent<RectTransform>().rect.width;
                float ratio = cw > 0f ? occ / cw : 0f;
                string m = "A3 columns " + occ.ToString("0", CultureInfo.InvariantCulture) + " / " + cw.ToString("0", CultureInfo.InvariantCulture)
                    + " = " + ratio.ToString("0.000", CultureInfo.InvariantCulture);
                if (ratio >= 0.95f) StOk(m); else StBad(m);
            }
            else StBad("A3 columns not built");
        }

        private static void SelfTestOpenTab()
        {
            if (stTab == SettingsModel.SubTabIndex("perf") && !_perfSectionOpen)
            {
                _perfSectionOpen = true;
                if (_perfSectionBody != null) _perfSectionBody.SetActive(true);
            }
            SettingsSwitchSubTab(stTab);
            dirty = true;
        }

        private static void SelfTestCheckTab()
        {
            string home = SettingsModel.SubTabHomes[stTab];
            GameObject tall = null;
            if (stMutation == "a5-tall" && settingsBodies[stTab] != null)
            {
                tall = new GameObject("SelfTestTall");
                tall.transform.SetParent(settingsBodies[stTab].transform, false);
                tall.transform.SetAsFirstSibling();
                tall.AddComponent<RectTransform>();
                UIFactory.AddLE(tall, minH: 900f, prefH: 900f);
            }
            SettingsForceLayout();
            SettingsUpdateHint();
            SettingsForceLayout();
            if (stMutation == "a8-nohint" && setListHint != null) setListHint.SetActive(!setListHint.activeSelf);
            float scale = SettingsCanvasScale();
            float tol = 1.0f * scale;
            var rows = SettingsFocusList(stTab);
            float content = SettingsActiveContentHeight();
            float vpNoHint = SettingsViewportNoHint();
            bool over = content > vpNoHint + 0.5f;
            Rect vpRect = setListViewport != null ? SettingsWorldRect(setListViewport) : new Rect();

            // A1: containment, three legs.
            Transform shiftCell = null;
            Vector3 shiftPos = Vector3.zero;
            if (stMutation == "a1-shift" && rows.Count > 0 && rows[0].Row != null)
            {
                shiftCell = rows[0].Row.transform.Find(rows[0].Key + "_c");
                if (shiftCell != null) { shiftPos = shiftCell.localPosition; shiftCell.localPosition = shiftPos + new Vector3(3000f, 0f, 0f); }
            }
            int a1 = 0;
            foreach (var r in rows)
            {
                if (r.Row == null) continue;
                Rect rr = SettingsWorldRect(r.Row);
                string bad = null;
                var q = r.Row.transform.Find(r.Key + "_q");
                var l = r.Row.transform.Find(r.Key + "_l");
                var c = r.Row.transform.Find(r.Key + "_c");
                if (q == null || l == null || c == null) bad = "missing a cell";
                else
                {
                    Rect qr = SettingsWorldRect(q.gameObject), lr = SettingsWorldRect(l.gameObject), cr = SettingsWorldRect(c.gameObject);
                    if (!SettingsInside(rr, qr, tol) || !SettingsInside(rr, lr, tol) || !SettingsInside(rr, cr, tol)) bad = "a cell lies outside its row";
                    else if (qr.xMax > lr.xMin + tol || lr.xMax > cr.xMin + tol) bad = "cells overlap";
                    else if (rr.xMin < vpRect.xMin - tol || rr.xMax > vpRect.xMax + tol)
                        bad = (rr.width / scale).ToString("0", CultureInfo.InvariantCulture) + " px wide, viewport "
                            + (vpRect.width / scale).ToString("0", CultureInfo.InvariantCulture);
                    else if (!over && (rr.yMin < vpRect.yMin - tol || rr.yMax > vpRect.yMax + tol)) bad = "row lies outside the viewport vertically";
                }
                if (bad == null) a1++; else StBad("A1 row " + r.Key + ": " + bad);
            }
            if (shiftCell != null) shiftCell.localPosition = shiftPos;
            if (a1 == rows.Count) StOk("A1 " + home + ": " + a1 + " rows contained" + (over ? " (vertical leg deferred to A8: the tab scrolls)" : ""));

            SelfTestA2a(home, rows, null);
            if (stTab == 0) SelfTestA2aChrome(null);

            // A2b: the help body is as tall as its text, for every row's pane.
            SelfTestA2b(home, rows);

            SelfTestA5A8(home, rows, content, vpNoHint, over, tol);
            if (tall != null) { UnityEngine.Object.DestroyImmediate(tall); SettingsForceLayout(); }
            if (tall != null || stMutation == "a8-nohint") SettingsUpdateHint();
        }

        /// <summary>A2a: one-line cells; an unmeasurable cell is a failure.
        /// `loc` names the locale of a sweep pass (null in the base pass, so
        /// the base lines keep their plain A2a prefix).</summary>
        private static void SelfTestA2a(string home, List<SettingsRowRec> rows, string loc)
        {
            string tag = loc == null ? "A2a" : "A2a[" + loc + "]";
            foreach (var r in rows)
            {
                if (r.Label == null) continue;
                string painted = UIFactory.GetTmpText(r.Label) ?? "";
                string baseText;
                if (loc == null) stBaseLabels[r.Key] = painted;
                else if (stBaseLabels.TryGetValue(r.Key, out baseText))
                {
                    stSweepRows++;
                    if (painted != baseText) stSweepDiffer++;
                }
            }
            // Every one-line cell of every active row (design S10 A2a, round-2
            // M2): the label, a switch's state word, each segment word, a
            // dropdown face, a slider readout, an action or disclosure glyph,
            // and each delete-row button face, shown or hidden (a hidden face
            // must still fit when it shows). A cell that is not built, is
            // empty or cannot be measured FAILS and stays in the denominator;
            // no cell leaves the count.
            var cells = SelfTestA2aCells(rows);
            bool blank = stMutation == "a2a-blank" && loc == "sv" && home == "ingame";
            int a2 = 0, a2n = 0, blanked = 0;
            var measured = new List<string>();
            foreach (var c in cells)
            {
                if (blank && blanked < 12 && c.Obj != null) { UIFactory.SetTextNoHook(c.Obj, ""); blanked++; }
                a2n++;
                measured.Add(c.Id);
                if (c.Obj == null) { StBad(tag + " " + c.Id + ": cell not built"); continue; }
                string text = UIFactory.GetTmpText(c.Obj);
                if (string.IsNullOrEmpty(SettingsModel.StripTags(text))) { StBad(tag + " " + c.Id + ": measurement unavailable (empty text)"); continue; }
                float w = stMutation == "a2a-zero" ? 0f : UIFactory.MeasureTextWidth(c.Obj, text);
                if (w <= 0f) StBad(tag + " " + c.Id + ": measurement unavailable");
                else if (w > c.Width + 0.5f) StBad(tag + " " + c.Id + ": '" + SettingsModel.StripTags(text) + "' measures "
                    + w.ToString("0", CultureInfo.InvariantCulture) + " px in a " + c.Width.ToString("0", CultureInfo.InvariantCulture) + " px cell");
                else a2++;
            }
            if (blanked > 0) { StNote(tag + " fixture a2a-blank emptied " + blanked + " of " + home + "'s cells before measuring"); dirty = true; }
            // The denominator is the base pass's own cell set: each locale pass
            // must measure every cell the base pass measured on this sub-tab.
            int tabIdx = SettingsModel.SubTabIndex(home);
            bool covered = true;
            string baseNote = "";
            if (loc == null)
            {
                if (tabIdx >= 0) stBaseCells[tabIdx] = measured;
                StNote(tag + " " + home + " cells: " + string.Join(", ", measured.ToArray()));
            }
            else if (tabIdx >= 0 && stBaseCells[tabIdx] != null)
            {
                var seen = new HashSet<string>(measured);
                foreach (var id in stBaseCells[tabIdx])
                    if (!seen.Contains(id)) { covered = false; StBad(tag + " " + id + ": not measured in this pass (the base pass measured it)"); }
                if (a2n != stBaseCells[tabIdx].Count) covered = false;
                baseNote = " (base pass " + stBaseCells[tabIdx].Count + ")";
            }
            else if (tabIdx >= 0) { covered = false; baseNote = " (no base pass to compare)"; }
            string sum = tag + " " + home + ": " + a2 + " of " + a2n + " one-line cells fit" + baseNote;
            if (a2 == a2n && covered) StOk(sum); else StBad(sum);

            // Section 15: each segmented row's widest option word in this
            // pass. The s15-long mutation lengthens one SBloom word for this
            // record only (A2a above measured the real word), so the pair's
            // decision must flip to dropdown and the S15 verdict must red.
            string passLoc = loc ?? I18n.Locale;
            foreach (var r in rows)
            {
                if (r.Kind != SettingsKind.Segmented || r.OptTxts == null || Array.IndexOf(SettingsSegFitRows, r.Key) < 0) continue;
                stSegLocales.Add(passLoc);
                for (int i = 0; i < r.OptTxts.Length; i++)
                {
                    if (r.OptTxts[i] == null) continue;
                    string text = UIFactory.GetTmpText(r.OptTxts[i]) ?? "";
                    if (stMutation == "s15-long" && r.Key == "SBloom" && i == 0) text = "REDUCED REDUCED REDUCED";
                    float w = UIFactory.MeasureTextWidth(r.OptTxts[i], text);
                    float cur;
                    if (!stSegMax.TryGetValue(r.Key, out cur) || w > cur)
                    {
                        stSegMax[r.Key] = w;
                        stSegWidest[r.Key] = "'" + SettingsModel.StripTags(text) + "' " + w.ToString("0", CultureInfo.InvariantCulture) + " px in " + passLoc;
                    }
                }
            }
        }

        /// <summary>A2a over the chrome: every sub-tab label and every footer
        /// button face fits its button, 8 px of padding allowed. The footer's
        /// confirm and cancel faces are measured while hidden: their text is
        /// set at build, and a hidden face must still fit when it shows.</summary>
        private static void SelfTestA2aChrome(string loc)
        {
            string tag = loc == null ? "A2a chrome" : "A2a[" + loc + "] chrome";
            for (int i = 0; i < SETTINGS_TABS; i++)
            {
                if (settingsSubBtns[i] == null) continue;
                string painted = UIFactory.GetTmpText(UIFactory.GetButtonText(settingsSubBtns[i])) ?? "";
                if (loc == null) stBaseSubLabels[i] = painted;
                else if (stBaseSubLabels[i] != null && painted != stBaseSubLabels[i]) stSweepSubDiffer++;
            }
            // Round-2 M2, same class as the rows: a face that was never built
            // is named and failed, never left out of the count.
            var names = new List<string>();
            var cells = new List<KeyValuePair<GameObject, float>>();
            for (int i = 0; i < SETTINGS_TABS; i++) { names.Add("sub-tab " + SettingsModel.SubTabHomes[i]); cells.Add(new KeyValuePair<GameObject, float>(settingsSubBtns[i], 160f)); }
            names.Add("details more"); cells.Add(new KeyValuePair<GameObject, float>(setDetMoreBtn, 132f));
            names.Add("reset"); cells.Add(new KeyValuePair<GameObject, float>(setResetBtn, 292f));
            names.Add("reset confirm"); cells.Add(new KeyValuePair<GameObject, float>(setResetConfirmBtn, 102f));
            names.Add("reset cancel"); cells.Add(new KeyValuePair<GameObject, float>(setResetCancelBtn, 92f));
            int ok = 0;
            for (int k = 0; k < cells.Count; k++)
            {
                var kv = cells[k];
                if (kv.Key == null) { StBad(tag + " " + names[k] + ": not built"); continue; }
                var t = UIFactory.GetButtonText(kv.Key);
                string text = UIFactory.GetTmpText(t);
                if (t == null || string.IsNullOrEmpty(SettingsModel.StripTags(text))) { StBad(tag + " " + kv.Key.name + ": empty face"); continue; }
                float w = stMutation == "a2a-zero" ? 0f : UIFactory.MeasureTextWidth(t, text);
                if (w <= 0f) StBad(tag + " " + kv.Key.name + ": measurement unavailable");
                else if (w > kv.Value + 0.5f) StBad(tag + " " + kv.Key.name + ": '" + SettingsModel.StripTags(text) + "' measures "
                    + w.ToString("0", CultureInfo.InvariantCulture) + " px in a " + kv.Value.ToString("0", CultureInfo.InvariantCulture) + " px face");
                else ok++;
            }
            string sum = tag + ": " + ok + " of " + cells.Count + " button faces fit";
            if (ok == cells.Count) StOk(sum); else StBad(sum);
        }

        /// <summary>One A2a cell: its id ("SIgChat/opt1"), its text object
        /// (null when the row never built it) and the width it must fit.</summary>
        private struct SettingsA2aCell
        {
            internal string Id;
            internal object Obj;
            internal float Width;
            internal SettingsA2aCell(string id, object obj, float width) { Id = id; Obj = obj; Width = width; }
        }

        /// <summary>A2a's cell list for a sub-tab's active rows (round-2 M2):
        /// every one-line cell each row's kind builds, whether or not its text
        /// object exists, so a cell the row failed to build is failed by id.</summary>
        private static List<SettingsA2aCell> SelfTestA2aCells(List<SettingsRowRec> rows)
        {
            var cells = new List<SettingsA2aCell>();
            foreach (var r in rows)
            {
                float labelW = stMutation == "a2a-narrow" && r.Key == "SPerf_PoolInit" ? 40f : 340f;
                cells.Add(new SettingsA2aCell(r.Key + "/label", r.Label, labelW));
                switch (r.Kind)
                {
                    case SettingsKind.Switch:
                        cells.Add(new SettingsA2aCell(r.Key + "/word", r.Word, 240f));
                        break;
                    case SettingsKind.Segmented:
                        int n = r.Ids != null ? r.Ids.Length : 0;
                        for (int i = 0; i < n; i++)
                            cells.Add(new SettingsA2aCell(r.Key + "/opt" + i, r.OptTxts != null && i < r.OptTxts.Length ? r.OptTxts[i] : null, 142f));
                        if (n == 0) cells.Add(new SettingsA2aCell(r.Key + "/opt", null, 142f));
                        break;
                    case SettingsKind.Dropdown:
                        cells.Add(new SettingsA2aCell(r.Key + "/face", r.FaceTxt, 312f));
                        break;
                    case SettingsKind.Slider:
                        cells.Add(new SettingsA2aCell(r.Key + "/readout", r.Readout, 222f));
                        break;
                    case SettingsKind.Action:
                    case SettingsKind.Disclosure:
                        cells.Add(new SettingsA2aCell(r.Key + "/glyph", r.GlyphTxt, 36f));
                        break;
                    case SettingsKind.Destructive:
                        if (r.Members == null || r.Members.Count == 0) cells.Add(new SettingsA2aCell(r.Key + "/buttons", null, 0f));
                        else foreach (var m in r.Members) cells.Add(new SettingsA2aCell(m.Key + "/button", m.ButtonTxt, m.ButtonSize.x - 8f));
                        break;
                }
            }
            return cells;
        }

        /// <summary>Round-2 M2: the self-test measures only a page its own
        /// paint pass has painted (settingsPaintedGen == settingsBuildGen).
        /// The wait is bounded - 20 x 0.25 s - and a page that never completes
        /// a pass fails; it is then measured anyway, so its empty cells fail
        /// by id. Returns false while waiting (the caller retries the phase).</summary>
        private static bool SelfTestPaintReady(string tag)
        {
            if (settingsPaintedGen == settingsBuildGen)
            {
                if (stReadyRetry > 0)
                    StNote(tag + ": waited " + (stReadyRetry * 0.25f).ToString("0.00", CultureInfo.InvariantCulture)
                        + " s for the page's paint pass after build " + settingsBuildGen);
                stReadyRetry = 0;
                return true;
            }
            if (stReadyRetry++ < 20) { stWaitUntil = Time.unscaledTime + 0.25f; return false; }
            StBad(tag + ": the page never completed a paint pass after build " + settingsBuildGen + " (last painted " + settingsPaintedGen + ")");
            stReadyRetry = 0;
            return true;
        }

        /// <summary>A2b (design section 10): the help body's scroll content is
        /// as tall as its children's own preferred heights at the measured
        /// width, within 1 px. Two legs: the body is exactly as tall as its
        /// text - never shorter (clipped) and never taller (a reserved
        /// minimum: CreateText bakes minH = sizeDelta.y, which the pane zeroes,
        /// learning #449) - and the content is exactly its active children's
        /// heights plus the group's spacing. Round 1 asserted only the lower
        /// bound, which the design's own mutation (the pane's SetMinH(0)
        /// omitted) could never red: a one-line body is 18 px of text on a
        /// 20 px floor (round-2 LOW-7).</summary>
        private static void SelfTestA2b(string home, List<SettingsRowRec> rows)
        {
            int b2 = 0;
            foreach (var r in rows)
            {
                settingsPinnedKey = r.Key;
                SettingsRenderPane();
                SettingsForceLayout();
                var brt = ((Component)setDetBodyTxt).GetComponent<RectTransform>();
                var crt = brt.parent as RectTransform;
                string text = UIFactory.GetTmpText(setDetBodyTxt);
                if (string.IsNullOrEmpty(text)) { StBad("A2b " + r.Key + ": empty help body"); continue; }
                float need = UIFactory.MeasureTextHeight(setDetBodyTxt, text, brt.rect.width);
                float keepH = brt.rect.height;
                if (stMutation == "a2b-short") brt.SetSizeWithCurrentAnchors(RectTransform.Axis.Vertical, 10f);
                float body = brt.rect.height, sum = 0f;
                int n = 0;
                if (crt != null)
                    for (int i = 0; i < crt.childCount; i++)
                    {
                        var ch = crt.GetChild(i) as RectTransform;
                        if (ch == null || !ch.gameObject.activeSelf) continue;
                        n++;
                        sum += ch.rect.height;
                    }
                float want = sum + (n > 1 ? (n - 1) * SetDetBodySpacing : 0f);
                float content = crt != null ? crt.rect.height : -1f;
                if (need <= 0f) StBad("A2b " + r.Key + ": measurement unavailable");
                else if (Mathf.Abs(body - need) > 1f) StBad("A2b " + r.Key + ": body " + body.ToString("0", CultureInfo.InvariantCulture)
                    + " px, its text " + need.ToString("0", CultureInfo.InvariantCulture) + " px (" + (body > need ? "a reserved minimum" : "clipped") + ")");
                else if (crt == null || Mathf.Abs(content - want) > 1f) StBad("A2b " + r.Key + ": content " + content.ToString("0", CultureInfo.InvariantCulture)
                    + " px, its " + n + " children and their spacing " + want.ToString("0", CultureInfo.InvariantCulture) + " px");
                else b2++;
                if (stMutation == "a2b-short") brt.SetSizeWithCurrentAnchors(RectTransform.Axis.Vertical, keepH);
            }
            settingsPinnedKey = null;
            settingsPaneDirty = true;
            if (b2 == rows.Count) StOk("A2b " + home + ": " + b2 + " help bodies sized to their text");
        }

        private static void SelfTestA5A8(string home, List<SettingsRowRec> rows, float content, float vpNoHint, bool over, float tol)
        {
            SettingsCheckA5A8(home, rows, content, vpNoHint, over, tol, StOk, StBad, StNote);
        }

        /// <summary>A5 and A8 on one measured tab. The self-test reports
        /// through its own lines; the driven-input harness (design T4) runs
        /// the same check after each rebuild route.</summary>
        private static void SettingsCheckA5A8(string home, List<SettingsRowRec> rows, float content, float vpNoHint, bool over, float tol,
            Action<string> ok, Action<string> bad, Action<string> note)
        {
            // A5a / A5b: unscrolled at the worst case (Chat & mail scrolls by design).
            int inactive = 0;
            var pr = pageGO != null ? pageGO.transform : null;
            foreach (var nm in new[] { "SrvRow", "AlertRow", "TournIndRow" })
            {
                var t = SettingsFindDeep(pr, nm);
                if (t != null && !t.gameObject.activeSelf) inactive++;
            }
            float canvasH = SettingsCanvasHeight();
            float hWorst = vpNoHint - 26f * inactive - (canvasH - 810f);
            string nums = "content " + content.ToString("0", CultureInfo.InvariantCulture) + ", viewport " + vpNoHint.ToString("0", CultureInfo.InvariantCulture)
                + ", H_worst " + hWorst.ToString("0", CultureInfo.InvariantCulture) + " (" + inactive + " optional rows inactive, canvas "
                + canvasH.ToString("0", CultureInfo.InvariantCulture) + ")";
            if (home == "chatmail") note("A5 chatmail: exempt, scrolls by design; " + nums);
            else
            {
                if (content <= hWorst + 0.5f) ok("A5a " + home + ": " + nums); else bad("A5a " + home + ": " + nums);
                if (content <= vpNoHint + 0.5f) ok("A5b " + home + ": fits the measured viewport");
                // The supported bound is 21:9 as design section 3.1 sizes it:
                // 2560x1080 (64:27, the 810 px canvas), inclusive. The literal
                // 21/9 put that case past the bound, so A5b could not fail at
                // the aspect its own mutation names (round-2 LOW-7).
                else if (Screen.height > 0 && Screen.width / (float)Screen.height > 64f / 27f + 0.01f)
                    note("OBSERVATION A5b " + home + ": content " + content.ToString("0", CultureInfo.InvariantCulture) + " > viewport "
                        + vpNoHint.ToString("0", CultureInfo.InvariantCulture) + " at " + Screen.width + "x" + Screen.height + " (past the supported 21:9 bound)");
                else bad("A5b " + home + ": content exceeds the measured viewport at " + Screen.width + "x" + Screen.height + "; " + nums);
            }

            // A8: hint active iff the tab overflows; the last row reachable.
            bool hint = setListHint != null && setListHint.activeSelf;
            if (hint != over) bad("A8 " + home + ": hint " + (hint ? "active" : "inactive") + " but content " + (over ? "overflows" : "fits"));
            else if (!over) ok("A8 " + home + ": fits, hint inactive");
            else
            {
                SettingsScrollListTo(0f);
                SettingsForceLayout();
                var last = rows.Count > 0 ? rows[rows.Count - 1] : null;
                Rect vr = SettingsWorldRect(setListViewport);
                if (last != null && SettingsInside(vr, SettingsWorldRect(last.Row), tol)) ok("A8 " + home + ": overflows, hint active, last row " + last.Key + " reachable");
                else bad("A8 " + home + ": last row not inside the viewport after a scroll to the end");
                SettingsScrollListTo(1f);
            }
        }

        private static void SelfTestAfterRebuild()
        {
            if (!isOpen || currentTab != TAB_SETTINGS || settingsBodies[3] == null)
            {
                if (stRetry++ < 4) { stWaitUntil = Time.unscaledTime + 1f; return; }
                StBad("A7 the settings page did not come back after the rebuild");
                SelfTestFinish();
                return;
            }
            bool bodiesOk = true;
            for (int i = 0; i < SETTINGS_TABS; i++)
                if (settingsBodies[i] != null && settingsBodies[i].activeSelf != (i == 3)) bodiesOk = false;
            var empty = new List<string>();
            foreach (var d in SettingsDescriptors.All)
            {
                SettingsRowRec r;
                if (!settingsByKey.TryGetValue(d.Key, out r) || string.IsNullOrEmpty(r.LastPainted)) empty.Add(d.Key);
            }
            if (empty.Count > 0 && stRetry++ < 4) { stWaitUntil = Time.unscaledTime + 1f; return; }
            if (settingsSubTab == 3 && bodiesOk) StOk("A7 restored sub-tab 3 after the catalogue rebuild");
            else StBad("A7 after the rebuild: sub-tab " + settingsSubTab + ", active bodies [" + SelfTestActiveBodies() + "], expected exactly body 3");
            if (empty.Count == 0) StOk("A7 all " + SettingsDescriptors.All.Length + " labels painted after the rebuild");
            else StBad("A7 unpainted after the rebuild: " + string.Join(",", empty.ToArray()));
            if (SettingsSweepRuns)
            {
                stOrigLocale = I18n.Locale;
                stPrefBefore = SettingsGameLanguagePref();
                stSweepIdx = 0;
                stPhase = 5;
                return;
            }
            SelfTestS15();
            SelfTestFinish();
        }

        /// <summary>Design section 15: the decision the measurement makes
        /// and the kind each row is built as must agree. The pair SBloom and
        /// SShake is one decision - if either row's widest word overflows its
        /// segment in any measured locale, both rows must be dropdowns - and
        /// SMenuMus, SIgChat and SHpPrec each decide alone.</summary>
        private static void SelfTestS15()
        {
            string over = stSegLocales.Count + " locale pass(es) [" + string.Join(",", new List<string>(stSegLocales).ToArray()) + "]";
            string seg = SettingsSegmentWidth.ToString("0", CultureInfo.InvariantCulture);
            SettingsRowRec bloom, shake;
            float wb, ws;
            if (!settingsByKey.TryGetValue("SBloom", out bloom) || !settingsByKey.TryGetValue("SShake", out shake)
                || !stSegMax.TryGetValue("SBloom", out wb) || !stSegMax.TryGetValue("SShake", out ws))
                StBad("S15 the pair SBloom+SShake was not measured");
            else
            {
                var want = wb <= SettingsSegmentWidth + 0.5f && ws <= SettingsSegmentWidth + 0.5f ? SettingsKind.Segmented : SettingsKind.Dropdown;
                string rep = "widest SBloom " + stSegWidest["SBloom"] + ", widest SShake " + stSegWidest["SShake"] + ", segment " + seg + " px, " + over;
                if (bloom.Kind == want && shake.Kind == want) StOk("S15 pair SBloom+SShake: measured " + want + ", built " + bloom.Kind + " and " + shake.Kind + "; " + rep);
                else StBad("S15 pair SBloom+SShake: measured " + want + " but built " + bloom.Kind + " and " + shake.Kind + " (the pair changes kind together); " + rep);
            }
            foreach (string key in new[] { "SMenuMus", "SIgChat", "SHpPrec" })
            {
                SettingsRowRec r;
                float w;
                if (!settingsByKey.TryGetValue(key, out r) || !stSegMax.TryGetValue(key, out w)) { StBad("S15 " + key + " was not measured"); continue; }
                var want = w <= SettingsSegmentWidth + 0.5f ? SettingsKind.Segmented : SettingsKind.Dropdown;
                if (r.Kind == want) StOk("S15 " + key + ": measured " + want + ", built " + r.Kind + "; widest " + stSegWidest[key] + ", segment " + seg + " px, " + over);
                else StBad("S15 " + key + ": measured " + want + " but built " + r.Kind + "; widest " + stSegWidest[key] + ", segment " + seg + " px");
            }
        }

        private static string SelfTestActiveBodies()
        {
            var on = new List<string>();
            for (int i = 0; i < SETTINGS_TABS; i++)
                if (settingsBodies[i] != null && settingsBodies[i].activeSelf) on.Add(i.ToString(CultureInfo.InvariantCulture));
            return string.Join(",", on.ToArray());
        }

        /// <summary>The game's own language pref, which I18n.SetLocale writes.</summary>
        private static int SettingsGameLanguagePref()
        {
            try { return PlayerPrefs.GetInt("OPTION_LANGUAGE", -1); } catch { return -2; }
        }

        /// <summary>The A2a sweep (design residual 3: A2a in en, es, ru, uk and
        /// sv). Each pass makes the switch a player makes - I18n.SetLocale,
        /// then the page rebuilt through the catalogue route - measures every
        /// sub-tab, and the original locale is restored the same way at the
        /// end. SetLocale writes the game's language pref, so the pref is read
        /// before the sweep and must read the same after it.</summary>
        private static void SelfTestSweepNext()
        {
            if (stSweepIdx >= SettingsSweepLocales.Length)
            {
                I18n.SetLocale(stOrigLocale);
                RequestCatalogueRebuild();
                stRetry = 0;
                stPhase = 8;
                stWaitUntil = Time.unscaledTime + 2.5f;
                return;
            }
            string loc = SettingsSweepLocales[stSweepIdx];
            stSweepDiffer = 0; stSweepRows = 0; stSweepSubDiffer = 0;
            StNote("A2a sweep: switching to " + loc);
            I18n.SetLocale(loc);
            RequestCatalogueRebuild();
            stTab = 0;
            stRetry = 0;
            stPhase = 6;
            stWaitUntil = Time.unscaledTime + 2.5f;
        }

        private static void SelfTestSweepOpenTab()
        {
            if (!isOpen || currentTab != TAB_SETTINGS || settingsBodies[stTab] == null || I18n.Locale != SettingsSweepLocales[stSweepIdx])
            {
                if (stRetry++ < 6) { stWaitUntil = Time.unscaledTime + 1f; return; }
                StBad("A2a[" + SettingsSweepLocales[stSweepIdx] + "] the settings page did not come back after the locale switch");
                stSweepIdx++;
                stPhase = 5;
                return;
            }
            SelfTestOpenTab();
            stPhase = 7;
            stWaitUntil = Time.unscaledTime + 0.6f;
        }

        private static void SelfTestSweepCheckTab()
        {
            string sweepLoc = SettingsSweepLocales[stSweepIdx];
            // Fixture "a2a-rebuild" (round-2 M2): ask for a catalogue rebuild
            // and stay in this phase, so the next Tick rebuilds the page and
            // the one after reaches this measurement before the new page's
            // first paint pass - the race a language pack landing after the
            // locale switch creates, made deterministic.
            if (stMutation == "a2a-rebuild" && sweepLoc == "sv" && stTab == 0 && !stRebuildFixtureDone)
            {
                stRebuildFixtureDone = true;
                RequestCatalogueRebuild();
                StNote("A2a[" + sweepLoc + "] fixture a2a-rebuild: the page rebuilds just before the "
                    + SettingsModel.SubTabHomes[stTab] + " measurement (build " + settingsBuildGen + ")");
                return;
            }
            if (!SelfTestPaintReady("A2a[" + sweepLoc + "] " + SettingsModel.SubTabHomes[stTab])) return;
            SettingsForceLayout();
            SelfTestA2a(SettingsModel.SubTabHomes[stTab], SettingsFocusList(stTab), SettingsSweepLocales[stSweepIdx]);
            if (stTab == 0) SelfTestA2aChrome(SettingsSweepLocales[stSweepIdx]);
            stTab++;
            if (stTab < SETTINGS_TABS) { stPhase = 6; return; }
            string loc = SettingsSweepLocales[stSweepIdx];
            string rep = stSweepDiffer + " of " + stSweepRows + " row labels and " + stSweepSubDiffer + " of " + SETTINGS_TABS
                + " sub-tab labels read differently from the " + stOrigLocale + " pass";
            if (stSweepDiffer > 0 && stSweepSubDiffer == SETTINGS_TABS) StOk("A2a[" + loc + "] repainted: " + rep);
            else StBad("A2a[" + loc + "] the page did not repaint in " + loc + ": " + rep);
            stSweepIdx++;
            stPhase = 5;
        }

        private static void SelfTestSweepRestored()
        {
            if ((!isOpen || currentTab != TAB_SETTINGS || settingsBodies[0] == null) && stRetry++ < 6)
            {
                stWaitUntil = Time.unscaledTime + 1f;
                return;
            }
            int after = SettingsGameLanguagePref();
            if (I18n.Locale == stOrigLocale && after == stPrefBefore)
                StOk("A2a sweep: locale restored to " + stOrigLocale + ", game language pref " + after + " as before");
            else StBad("A2a sweep: locale " + I18n.Locale + " (was " + stOrigLocale + "), game language pref " + after + " (was " + stPrefBefore + ")");
            stOrigLocale = null;
            SelfTestS15();
            SelfTestFinish();
        }
    }
}
