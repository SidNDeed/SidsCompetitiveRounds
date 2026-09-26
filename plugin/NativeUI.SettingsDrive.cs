using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Item 13, round 2: the settings page's DRIVEN-INPUT harness. The
    /// round-1 self-test measures the page; this drives it. A pressed key is
    /// handed to the page's own keyboard poll on its next frame
    /// (SettingsReadKey), so the modal gate, the settings-tab gate and the
    /// dispatch all run exactly as they do for a real key; a click goes
    /// through the control's own handler. It runs only through the broadcast
    /// seat's TestOpenTab lever ("5:drive" for every scenario,
    /// "5:drive:&lt;id&gt;,&lt;id&gt;" for some), one scenario at a time, each
    /// printing its own PASS or FAIL lines and putting back what it changed.
    /// While any settings test runs, the delete row's confirmation reaches a
    /// stub and no deletion request is ever sent.
    /// </summary>
    public static partial class NativeUI
    {
        private static readonly Stack<IEnumerator> drvStack = new Stack<IEnumerator>();
        private static float settingsDriveWaitUntil;
        private static int drvPass, drvFail, drvSavedTab;
        private static string drvIds = "", drvCurrent = "";

        /// <summary>The key the harness has pressed, handed to the page's
        /// poll on its next frame; None when no press is pending.</summary>
        private static SettingsModel.SettingsKey settingsDriveKey = SettingsModel.SettingsKey.None;
        private static bool settingsDriveKeyTaken;

        /// <summary>The controller button the harness has pressed (a joystick
        /// button number), handed to the page's pad poll on its next frame;
        /// -1 when none is pending.</summary>
        private static int settingsDrivePad = -1;
        private static bool settingsDrivePadTaken;

        /// <summary>Confirmations the delete row reached while a settings test
        /// ran. Each one would otherwise have been a deletion request.</summary>
        internal static int settingsDeleteStubCalls;

        internal static bool SettingsDriveRunning => drvStack.Count > 0;

        /// <summary>True while a settings test runs (the self-test or this
        /// harness): the delete row's confirmation then reaches the stub.</summary>
        internal static bool SettingsTestRunning => SettingsDriveRunning || SettingsSelfTestRunning;

        /// <summary>The scenarios, in the order "5:drive" runs them.</summary>
        private static readonly string[] SettingsDriveScenarios = { "m1", "l3", "l2", "l11" };

        private static void DrvOk(string m) { drvPass++; Plugin.Log.LogInfo("[SETTINGS-DRIVE] PASS " + m); }
        private static void DrvBad(string m) { drvFail++; Plugin.Log.LogWarning("[SETTINGS-DRIVE] FAIL " + m); }
        private static void DrvNote(string m) { Plugin.Log.LogInfo("[SETTINGS-DRIVE] " + m); }

        private static void SettingsDriveStart(string ids)
        {
            if (SettingsDriveRunning || stPhase >= 0) { Plugin.Log.LogInfo("[SETTINGS-DRIVE] a settings test is already running"); return; }
            ids = (ids ?? "").Trim().ToLowerInvariant();
            var list = new List<string>();
            if (ids.Length == 0 || ids == "all") list.AddRange(SettingsDriveScenarios);
            else
            {
                foreach (var s in ids.Split(','))
                {
                    string t = s.Trim();
                    if (Array.IndexOf(SettingsDriveScenarios, t) < 0)
                    {
                        Plugin.Log.LogWarning("[SETTINGS-DRIVE] unknown scenario '" + t + "'; known: " + string.Join(",", SettingsDriveScenarios));
                        return;
                    }
                    list.Add(t);
                }
            }
            drvIds = string.Join(",", list.ToArray());
            drvPass = 0;
            drvFail = 0;
            drvSavedTab = settingsSubTab;
            settingsDriveKey = SettingsModel.SettingsKey.None;
            settingsDrivePad = -1;
            Plugin.Log.LogInfo("[SETTINGS-DRIVE] START " + drvIds + " screen " + Screen.width + "x" + Screen.height + " locale " + I18n.Locale);
            settingsDriveWaitUntil = 0f;
            drvStack.Push(DriveRun(list));
        }

        /// <summary>Called first in every NativeUI.Tick, before the page's own
        /// open gate, so a scenario that closes or rebuilds the page keeps
        /// running. A scenario yields a number (a wait in seconds) or another
        /// scenario step (run to its end first). A step that throws is
        /// reported and abandoned; its caller carries on.</summary>
        internal static void SettingsDriveTick()
        {
            if (drvStack.Count == 0 || Time.unscaledTime < settingsDriveWaitUntil) return;
            for (int guard = 0; drvStack.Count > 0 && guard < 256; guard++)
            {
                var top = drvStack.Peek();
                bool more;
                try { more = top.MoveNext(); }
                catch (Exception e)
                {
                    DrvBad(drvCurrent + " threw: " + e.GetType().Name + " " + e.Message);
                    drvStack.Pop();
                    continue;
                }
                if (!more) { drvStack.Pop(); continue; }
                object cur = top.Current;
                var nested = cur as IEnumerator;
                if (nested != null) { drvStack.Push(nested); continue; }
                settingsDriveWaitUntil = Time.unscaledTime + (cur is float ? (float)cur : 0f);
                return;
            }
            if (drvStack.Count == 0) SettingsDriveFinish();
        }

        private static void SettingsDriveFinish()
        {
            drvStack.Clear();
            settingsDriveKey = SettingsModel.SettingsKey.None;
            settingsDrivePad = -1;
            try
            {
                if (isOpen && pageBuilt && currentTab == TAB_SETTINGS)
                    SettingsSwitchSubTab(Mathf.Clamp(drvSavedTab, 0, SETTINGS_TABS - 1));
            }
            catch { }
            Plugin.Log.LogInfo("[SETTINGS-DRIVE] DONE " + drvIds + " pass=" + drvPass + " fail=" + drvFail);
        }

        private static IEnumerator DriveRun(List<string> ids)
        {
            foreach (var id in ids)
            {
                drvCurrent = id;
                DrvNote("scenario " + id);
                yield return DrvOpenSettings();
                yield return DriveScenario(id);
            }
        }

        private static IEnumerator DriveScenario(string id)
        {
            switch (id)
            {
                case "m1": return DriveM1();
                case "l3": return DriveL3();
                case "l2": return DriveL2();
                case "l11": return DriveL11();
            }
            return DriveNothing();
        }

        private static IEnumerator DriveNothing() { yield break; }

        /// <summary>The pending harness key, taken once by the page's poll.</summary>
        private static bool SettingsTakeDriveKey(out SettingsModel.SettingsKey key)
        {
            key = settingsDriveKey;
            if (key == SettingsModel.SettingsKey.None) return false;
            settingsDriveKey = SettingsModel.SettingsKey.None;
            settingsDriveKeyTaken = true;
            return true;
        }

        /// <summary>The pending harness pad button, taken once by the page's
        /// pad poll; -1 when none.</summary>
        private static int SettingsTakeDrivePad()
        {
            int b = settingsDrivePad;
            if (b < 0) return -1;
            settingsDrivePad = -1;
            settingsDrivePadTaken = true;
            return b;
        }

        /// <summary>Press one controller button, exactly like DrvPress.</summary>
        private static IEnumerator DrvPad(int button, float settle)
        {
            settingsDrivePadTaken = false;
            settingsDrivePad = button;
            float until = Time.unscaledTime + 3f;
            while (!settingsDrivePadTaken && Time.unscaledTime < until) yield return 0f;
            if (!settingsDrivePadTaken)
            {
                settingsDrivePad = -1;
                DrvNote(drvCurrent + ": the page's pad poll did not take button " + button + " within 3 s");
            }
            yield return settle;
        }

        /// <summary>Press one key and wait for the page's poll to take it
        /// (at most 3 s), then settle. A key the poll never takes is
        /// withdrawn, so it cannot land later on a different state.</summary>
        private static IEnumerator DrvPress(SettingsModel.SettingsKey k, float settle)
        {
            settingsDriveKeyTaken = false;
            settingsDriveKey = k;
            float until = Time.unscaledTime + 3f;
            while (!settingsDriveKeyTaken && Time.unscaledTime < until) yield return 0f;
            if (!settingsDriveKeyTaken)
            {
                settingsDriveKey = SettingsModel.SettingsKey.None;
                DrvNote(drvCurrent + ": the page's poll did not take " + k + " within 3 s");
            }
            yield return settle;
        }

        /// <summary>Open the page on the settings tab and wait for it.</summary>
        private static IEnumerator DrvOpenSettings()
        {
            for (int i = 0; i < 20; i++)
            {
                if (isOpen && pageBuilt && currentTab == TAB_SETTINGS && settingsBodies[0] != null) yield break;
                if (!isOpen || currentTab != TAB_SETTINGS) DevOpenTab(TAB_SETTINGS);
                yield return 0.5f;
            }
            DrvBad("the settings page did not open");
        }

        private static bool DrvFocusIs(string key, string tag)
        {
            var f = SettingsFocusedRec();
            if (f != null && f.Key == key) return true;
            DrvBad(tag + " could not focus " + key + " (focused " + (f != null ? f.Key : "nothing") + ")");
            return false;
        }

        private static void DrvDisarm()
        {
            deleteArmed = false;
            SettingsPaintDeleteState(false);
            dirty = true;
        }

        /// <summary>MEDIUM-1 (design 6.3): an armed delete row confirms only
        /// with Enter, and Space neither arms nor confirms it. Every
        /// confirmation lands on the stub (settingsDeleteStubCalls).</summary>
        private static IEnumerator DriveM1()
        {
            // (a) Space on the disarmed row never arms it.
            DrvDisarm();
            SettingsSelectKey("SDR");
            yield return 0.6f;
            if (!DrvFocusIs("SDR", "M1")) yield break;
            yield return DrvPress(SettingsModel.SettingsKey.Space, 1.2f);
            if (!deleteArmed) DrvOk("M1 Space on the disarmed delete row: still not armed");
            else DrvBad("M1 Space on the disarmed delete row ARMED it");

            // (b) Space twice, 1.2 s apart, on the armed row reaches nothing.
            DrvDisarm();
            yield return 0.6f;
            yield return DrvPress(SettingsModel.SettingsKey.Enter, 1.2f);
            if (!deleteArmed) DrvBad("M1 precondition: Enter did not arm the delete row");
            else
            {
                int before = settingsDeleteStubCalls;
                yield return DrvPress(SettingsModel.SettingsKey.Space, 1.2f);
                yield return DrvPress(SettingsModel.SettingsKey.Space, 0.6f);
                int calls = settingsDeleteStubCalls - before;
                if (calls == 0 && deleteArmed)
                    DrvOk("M1 Space twice 1.2 s apart on the armed delete row: 0 confirmation calls, the row still armed");
                else
                    DrvBad("M1 Space twice 1.2 s apart on the armed delete row: " + calls + " confirmation call(s), armed=" + deleteArmed);
            }

            // (c) control: Enter confirms the armed row, and reaches the stub.
            DrvDisarm();
            yield return 0.6f;
            yield return DrvPress(SettingsModel.SettingsKey.Enter, 1.2f);
            int before2 = settingsDeleteStubCalls;
            yield return DrvPress(SettingsModel.SettingsKey.Enter, 0.6f);
            int calls2 = settingsDeleteStubCalls - before2;
            if (calls2 == 1 && !deleteArmed)
                DrvOk("M1 control: Enter on the row armed 1.2 s: 1 confirmation call, reaching the stub (no request sent)");
            else
                DrvBad("M1 control: Enter on the row armed 1.2 s: " + calls2 + " confirmation call(s), armed=" + deleteArmed);
            DrvDisarm();
        }

        /// <summary>LOW-3 (design 6.3): a disclosure steps with Left and Right
        /// only; Enter and Space never toggle it, while they still open a
        /// DROPDOWN and activate an ACTION row.</summary>
        private static IEnumerator DriveL3()
        {
            SettingsRowRec perfH;
            if (!settingsByKey.TryGetValue("SPerfH", out perfH) || perfH.Toggle == null)
            {
                DrvBad("L3 the Performance disclosure SPerfH was not built");
                yield break;
            }
            bool orig = _perfSectionOpen;
            SettingsSelectKey("SPerfH");
            yield return 0.6f;
            if (!DrvFocusIs("SPerfH", "L3")) yield break;
            yield return DrvPress(SettingsModel.SettingsKey.Enter, 0.6f);
            bool afterEnter = _perfSectionOpen;
            SettingsSelectKey("SPerfH");
            yield return 0.3f;
            yield return DrvPress(SettingsModel.SettingsKey.Space, 0.6f);
            bool afterSpace = _perfSectionOpen;
            if (afterEnter == orig && afterSpace == orig)
                DrvOk("L3 Enter and Space on the Performance disclosure: it stays " + (orig ? "expanded" : "collapsed"));
            else
                DrvBad("L3 Enter or Space toggled the Performance disclosure: " + (orig ? "expanded" : "collapsed")
                    + ", after Enter " + (afterEnter ? "expanded" : "collapsed") + ", after Space " + (afterSpace ? "expanded" : "collapsed"));

            // The control: Left collapses it and Right expands it.
            SettingsSelectKey("SPerfH");
            yield return 0.3f;
            yield return DrvPress(SettingsModel.SettingsKey.Left, 0.6f);
            bool afterLeft = _perfSectionOpen;
            SettingsSelectKey("SPerfH");
            yield return 0.3f;
            yield return DrvPress(SettingsModel.SettingsKey.Right, 0.6f);
            bool afterRight = _perfSectionOpen;
            if (!afterLeft && afterRight) DrvOk("L3 control: Left collapses the Performance disclosure and Right expands it");
            else DrvBad("L3 control: after Left " + (afterLeft ? "expanded" : "collapsed") + ", after Right "
                + (afterRight ? "expanded" : "collapsed") + " (want collapsed, then expanded)");
            if (_perfSectionOpen != orig) perfH.Toggle();
            yield return 0.3f;

            // The control: Enter and Space still open a DROPDOWN...
            foreach (var k in new[] { SettingsModel.SettingsKey.Enter, SettingsModel.SettingsKey.Space })
            {
                SettingsSelectKey("SDateFmt");
                yield return 0.6f;
                if (!DrvFocusIs("SDateFmt", "L3")) yield break;
                yield return DrvPress(k, 0.6f);
                bool open = CompetitiveUI.ArtistPromptOpen;
                if (open) DrvOk("L3 control: " + k + " opens the SDateFmt dropdown");
                else DrvBad("L3 control: " + k + " did not open the SDateFmt dropdown");
                if (open) { try { CompetitiveUI.ConsumePromptEscape(); } catch { } }
                yield return 0.6f;
            }

            // ...and activate an ACTION row (SInfoOpen opens the Info tab).
            foreach (var k in new[] { SettingsModel.SettingsKey.Enter, SettingsModel.SettingsKey.Space })
            {
                SettingsSelectKey("SInfoOpen");
                yield return 0.6f;
                if (!DrvFocusIs("SInfoOpen", "L3")) yield break;
                yield return DrvPress(k, 0.6f);
                if (currentTab == TAB_INFO) DrvOk("L3 control: " + k + " on the SInfoOpen action opens the Info tab");
                else DrvBad("L3 control: " + k + " on the SInfoOpen action left the page on tab " + currentTab);
                yield return DrvOpenSettings();
            }
        }

        /// <summary>LOW-2 (design 6.3, W7's source route): the controller's
        /// shoulders move between the sub-tabs and its activate button
        /// activates an ACTION row and opens a DROPDOWN, but neither arms nor
        /// confirms the delete row. Pressed through the page's own pad poll;
        /// no controller is attached, which is why W7 itself stays open.</summary>
        private static IEnumerator DriveL2()
        {
            SettingsSwitchSubTab(3);
            yield return 0.6f;
            yield return DrvPad(SettingsModel.PadNextTabButton, 0.6f);
            int afterNext = settingsSubTab;
            yield return DrvPad(SettingsModel.PadPrevTabButton, 0.6f);
            int afterPrev = settingsSubTab;
            if (afterNext == 4 && afterPrev == 3) DrvOk("L2 the right shoulder moves sub-tab 3 -> 4 and the left shoulder back 4 -> 3");
            else DrvBad("L2 shoulders: from sub-tab 3 the right shoulder reached " + afterNext + " and the left shoulder " + afterPrev + " (want 4, then 3)");

            SettingsSelectKey("SInfoOpen");
            yield return 0.6f;
            if (DrvFocusIs("SInfoOpen", "L2"))
            {
                yield return DrvPad(SettingsModel.PadActivateButton, 0.6f);
                if (currentTab == TAB_INFO) DrvOk("L2 the activate button on the SInfoOpen action opens the Info tab");
                else DrvBad("L2 the activate button on the SInfoOpen action left the page on tab " + currentTab);
                yield return DrvOpenSettings();
            }

            SettingsSelectKey("SDateFmt");
            yield return 0.6f;
            if (DrvFocusIs("SDateFmt", "L2"))
            {
                yield return DrvPad(SettingsModel.PadActivateButton, 0.6f);
                bool open = CompetitiveUI.ArtistPromptOpen;
                if (open) DrvOk("L2 the activate button opens the SDateFmt dropdown");
                else DrvBad("L2 the activate button did not open the SDateFmt dropdown");
                if (open) { try { CompetitiveUI.ConsumePromptEscape(); } catch { } }
                yield return 0.6f;
            }

            // The delete row: the activate button is held to Enter-only.
            DrvDisarm();
            SettingsSelectKey("SDR");
            yield return 0.6f;
            if (!DrvFocusIs("SDR", "L2")) yield break;
            yield return DrvPad(SettingsModel.PadActivateButton, 1.2f);
            if (!deleteArmed) DrvOk("L2 the activate button on the disarmed delete row: still not armed");
            else DrvBad("L2 the activate button ARMED the delete row");
            DrvDisarm();
            yield return 0.6f;
            yield return DrvPress(SettingsModel.SettingsKey.Enter, 1.2f);
            if (!deleteArmed) DrvBad("L2 precondition: Enter did not arm the delete row");
            else
            {
                int before = settingsDeleteStubCalls;
                yield return DrvPad(SettingsModel.PadActivateButton, 0.6f);
                int calls = settingsDeleteStubCalls - before;
                if (calls == 0 && deleteArmed) DrvOk("L2 the activate button on the row armed 1.2 s: 0 confirmation calls, still armed");
                else DrvBad("L2 the activate button on the armed delete row: " + calls + " confirmation call(s), armed=" + deleteArmed);
            }
            DrvDisarm();
        }

        /// <summary>LOW-11 (design S16 Q3): the language row's Detected line
        /// names the OS-suggested language as a word ("Detected: Svenska"),
        /// the same word as its Recommended line. The OS suggestion is
        /// I18n.SuggestFromOs, which reads this thread's UI culture: the
        /// scenario sets it to sv-SE and then en-US for the pane's repaint and
        /// puts the original back. F1 pins the row first, so a row under the
        /// mouse cannot take the pane.</summary>
        private static IEnumerator DriveL11()
        {
            SettingsSelectKey("SLang");
            yield return 0.6f;
            if (!DrvFocusIs("SLang", "L11")) yield break;
            string savedPin = settingsPinnedKey;
            settingsPinnedKey = null;
            var thread = System.Threading.Thread.CurrentThread;
            var savedCulture = thread.CurrentUICulture;
            try
            {
                yield return DrvPress(SettingsModel.SettingsKey.Pin, 0.4f);
                if (settingsPinnedKey != "SLang")
                {
                    DrvBad("L11 F1 did not pin the language row (pinned " + (settingsPinnedKey ?? "nothing") + ")");
                    yield break;
                }
                foreach (var culture in new[] { "sv-SE", "en-US" })
                {
                    thread.CurrentUICulture = new CultureInfo(culture);
                    string id = I18n.SuggestFromOs();
                    settingsPaneDirty = true;
                    yield return 0.6f;
                    string det = SettingsModel.StripTags(UIFactory.GetTmpText(setDetDetectedTxt) ?? "");
                    string recd = SettingsModel.StripTags(UIFactory.GetTmpText(setDetRecTxt) ?? "");
                    string wantDet = SettingsModel.StripTags(I18n.TrF("Detected: {0}", LanguageName(id)));
                    string wantRec = SettingsModel.StripTags(I18n.TrF("Recommended: {0}", LanguageName(id)));
                    if (det == wantDet) DrvOk("L11 OS culture " + culture + " (suggests " + id + "): the Detected line reads '" + det + "'");
                    else DrvBad("L11 OS culture " + culture + " (suggests " + id + "): the Detected line reads '" + det + "', want '" + wantDet + "'");
                    if (recd == wantRec) DrvOk("L11 control: OS culture " + culture + ": the Recommended line reads '" + recd + "'");
                    else DrvBad("L11 control: OS culture " + culture + ": the Recommended line reads '" + recd + "', want '" + wantRec + "'");
                }
            }
            finally
            {
                thread.CurrentUICulture = savedCulture;
                settingsPinnedKey = savedPin;
                settingsPaneDirty = true;
            }
        }
    }
}
