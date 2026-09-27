using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
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
    /// While any settings test runs, the delete row's confirmation, the
    /// Leave-all-queues press and the mail settings PUTs reach stubs, so no
    /// deletion, queue or mail request is ever sent.
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
        private static readonly string[] SettingsDriveScenarios =
            { "m1", "l3", "l2", "l11", "r4", "t5d", "t4", "t5a", "t5b", "t5c", "t5e", "t5f", "t5g", "t5h", "t7" };

        /// <summary>Scenarios that run only when named: design T7-b's two
        /// launches ("t7b", then "t7r-&lt;picked&gt;-&lt;previous&gt;-&lt;found&gt;"),
        /// the probe of T7-b's premise ("ppwt", then "ppwr"), the witness
        /// captures of design section 11 (they change the resolution or the
        /// language, and each capture needs the runner watching) and LOW-6's
        /// live config session ("l6", which closes the page).</summary>
        private static readonly string[] SettingsDriveNamed =
            { "t7b", "ppwt", "ppwr", "w1", "w2", "w3", "w3b", "w3c", "w4", "w5", "w6", "w9", "w9b", "w10", "l6" };

        private static bool SettingsDriveNamedOnly(string id)
        {
            return Array.IndexOf(SettingsDriveNamed, id) >= 0 || id.StartsWith("t7r-", StringComparison.Ordinal);
        }

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
                    if (Array.IndexOf(SettingsDriveScenarios, t) < 0 && !SettingsDriveNamedOnly(t))
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
            drvScreenPrefs0 = DrvScreenPrefs();
            Plugin.Log.LogInfo("[SETTINGS-DRIVE] START " + drvIds + " screen " + Screen.width + "x" + Screen.height + " " + Screen.fullScreenMode
                + " locale " + I18n.Locale + "; resolution prefs " + drvScreenPrefs0);
            try { DrvNote("PlayerPrefs at the start: " + DrvPrefSummary(DrvPrefState())); } catch { }
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
            if (settingsPutStubDue.Count > 0) SettingsStubDeliver();
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
            drvForceRows = false;
            settingsDriveMouseSet = false;
            DrvPutBackBlocks();
            dirty = true;
            try
            {
                if (isOpen && pageBuilt && currentTab == TAB_SETTINGS)
                    SettingsSwitchSubTab(Mathf.Clamp(drvSavedTab, 0, SETTINGS_TABS - 1));
            }
            catch { }
            try { DrvNote("PlayerPrefs at the end: " + DrvPrefSummary(DrvPrefState())); } catch { }
            DrvNote("stubs reached: delete " + settingsDeleteStubCalls + ", queue leave " + settingsEscapeStubCalls
                + ", mail PUT " + settingsPutStubCalls);
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
                case "r4": return DriveR4();
                case "t5d": return DriveT5d();
                case "t4": return DriveT4();
                case "t5a": return DriveT5a();
                case "t5b": return DriveT5b();
                case "t5c": return DriveT5c();
                case "t5e": return DriveT5e();
                case "t5f": return DriveT5f();
                case "t5g": return DriveT5g();
                case "t5h": return DriveT5h();
                case "t7": return DriveT7();
                case "t7b": return DriveT7b();
                case "ppwt": return DrivePpwt();
                case "ppwr": return DrivePpwr();
                case "w1": return DriveW1();
                case "w2": return DriveW2();
                case "w3": return DriveW3();
                case "w3b": return DriveW3b();
                case "w3c": return DriveW3c();
                case "w4": return DriveW4();
                case "w5": return DriveW5();
                case "w6": return DriveW6();
                case "w9": return DriveW9();
                case "w9b": return DriveW9b();
                case "w10": return DriveW10();
                case "l6": return DriveL6();
            }
            if (id.StartsWith("t7r-", StringComparison.Ordinal)) return DriveT7r(id.Substring(4));
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

        private static IEnumerator DrvPress(SettingsModel.SettingsKey k, float settle) { return DrvPress(k, settle, 3f); }

        /// <summary>Press one key and wait for the page's poll to take it
        /// (at most `take` seconds), then settle. A key the poll never takes
        /// is withdrawn, so it cannot land later on a different state.</summary>
        private static IEnumerator DrvPress(SettingsModel.SettingsKey k, float settle, float take)
        {
            settingsDriveKeyTaken = false;
            settingsDriveKey = k;
            float until = Time.unscaledTime + take;
            while (!settingsDriveKeyTaken && Time.unscaledTime < until) yield return 0f;
            if (!settingsDriveKeyTaken)
            {
                settingsDriveKey = SettingsModel.SettingsKey.None;
                DrvNote(drvCurrent + ": the page's poll did not take " + k + " within "
                    + take.ToString("0.#", CultureInfo.InvariantCulture) + " s");
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

        /// <summary>Round-2 R4: the mail relay switch paints neutral (a dim
        /// track, a dim knob at the centre) while its value is not known -
        /// before the first status poll, or with no linked Discord - and on
        /// or off by its value otherwise. Each case sets the two session facts
        /// (MailClient.StatusEverSeen and DiscordLinked, never persisted) and,
        /// where the case needs one, the row's getter; lets the page repaint;
        /// and reads what was rendered: the track colour, the knob colour and
        /// position, and the value word. The two unknown cases force the
        /// cached value ON, the value the round-1 switch painted green beside
        /// "checking...". Everything is put back; the relay's writer is never
        /// called, so nothing is sent and no preference is written. Then the
        /// class (DrvR4Class): every switch row on the page.</summary>
        private static IEnumerator DriveR4()
        {
            SettingsRowRec rec;
            if (!settingsByKey.TryGetValue("SMailRelay", out rec) || rec.Track == null || rec.Knob == null)
            {
                DrvBad("R4 the relay switch row is not built");
                yield break;
            }
            SettingsSwitchSubTab(rec.Tab);
            yield return 0.6f;
            bool seen0 = MailClient.StatusEverSeen, linked0 = MailClient.DiscordLinked;
            var get0 = rec.GetBool;
            bool real = false;
            try { real = get0 != null && get0(); } catch { }
            bool english = I18n.Locale == "en";
            string[] names = { "not yet polled, cached ON", "no linked Discord, cached ON",
                               "known, the row's own value", "known, the other value (painter control)" };
            bool[] seens = { false, true, true, true };
            bool[] linkeds = { true, false, true, true };
            int[] forced = { 1, 1, -1, real ? 0 : 1 };
            string[] needles = { "checking", "link Discord first", real ? "On" : "Off", null };
            try
            {
                for (int i = 0; i < names.Length; i++)
                {
                    MailClient.StatusEverSeen = seens[i];
                    MailClient.DiscordLinked = linkeds[i];
                    if (forced[i] < 0) rec.GetBool = get0;
                    else { bool v = forced[i] == 1; rec.GetBool = () => v; }
                    dirty = true;
                    yield return 0.6f;
                    bool neutral = i < 2;
                    bool on = forced[i] < 0 ? real : forced[i] == 1;
                    Color track = UIFactory.GetImageColor(rec.Track);
                    Color knob = UIFactory.GetImageColor(rec.Knob);
                    float kx = rec.Knob.GetComponent<RectTransform>().anchoredPosition.x;
                    string word = SettingsModel.StripTags(UIFactory.GetTmpText(rec.Word) ?? "");
                    Color wantTrack = neutral ? SW_NA : on ? SW_ON : SW_OFF;
                    Color wantKnob = neutral ? SW_KNOB_NA : SW_KNOB;
                    float wantX = neutral ? 14f : on ? 26f : 2f;
                    string seenAs = "track " + DrvColor(track) + ", knob " + DrvColor(knob) + " at x="
                        + kx.ToString("0", CultureInfo.InvariantCulture) + ", word '" + word + "'";
                    string wantAs = (neutral ? "neutral" : on ? "on" : "off") + " (track " + DrvColor(wantTrack)
                        + ", knob " + DrvColor(wantKnob) + " at x=" + wantX.ToString("0", CultureInfo.InvariantCulture) + ")";
                    bool painted = DrvSameColor(track, wantTrack) && DrvSameColor(knob, wantKnob) && Mathf.Abs(kx - wantX) < 0.5f;
                    bool worded = needles[i] == null || !english || word.IndexOf(needles[i], StringComparison.Ordinal) >= 0;
                    string tag = (i < 2 ? "R4 " : "R4 control: ") + names[i] + ": ";
                    if (painted && worded) DrvOk(tag + seenAs + " = " + wantAs);
                    else DrvBad(tag + seenAs + ", want " + wantAs
                        + (!worded ? " and a word containing '" + needles[i] + "'" : ""));
                }
            }
            finally
            {
                MailClient.StatusEverSeen = seen0;
                MailClient.DiscordLinked = linked0;
                rec.GetBool = get0;
                dirty = true;
            }
            yield return DrvR4Class();
        }

        /// <summary>Round-2 R4 is a class, not the relay's line: the W1
        /// witness of the Privacy tab showed Show Discord green beside "link
        /// Discord first" and both Player Cards switches off beside "...".
        /// Every switch row on the page is swept in the states of the cached
        /// answers those switches read: as they stand; with the player stats
        /// not answered (the property cleared, put back after unless a newer
        /// answer landed meanwhile); and, when this account has no linked
        /// Discord, with one linked in memory and Show Discord on, then off
        /// (the stats object's own fields, put back after). A repaint can
        /// start a stats fetch whose answer ends a state, so each sweep checks
        /// its state still holds when it reads, and a phase is tried up to
        /// three times. No row is clicked and no writer reads these fields,
        /// so nothing is sent. This account never has a /pc/me answer (a
        /// service account), so the Player Cards rows are swept in their
        /// not-known state only.</summary>
        private static IEnumerator DrvR4Class()
        {
            yield return DrvR4Sweep("as the cached answers stand", null);
            var prop = typeof(ApiClient).GetProperty("CachedPlayerStats", BindingFlags.Public | BindingFlags.Static);
            if (prop == null || !prop.CanWrite) { DrvBad("R4 class: ApiClient.CachedPlayerStats cannot be set"); yield break; }
            if (ApiClient.CachedPlayerStats == null) { DrvNote("R4 class: the stats have not answered, so the sweep above was that state; the linked states are not reachable"); yield break; }
            for (int attempt = 1; attempt <= 3; attempt++)
            {
                var st0 = ApiClient.CachedPlayerStats;
                try
                {
                    try { prop.SetValue(null, null, null); } catch (Exception e) { DrvBad("R4 class: clearing the stats: " + e.Message); }
                    yield return DrvR4Sweep("with the stats not answered", () => ApiClient.CachedPlayerStats == null);
                }
                finally
                {
                    if (ApiClient.CachedPlayerStats == null) { try { prop.SetValue(null, st0, null); } catch { } }
                    dirty = true;
                }
                DrvNote("R4 class: the stats are " + (ApiClient.CachedPlayerStats == st0 ? "put back"
                    : ApiClient.CachedPlayerStats != null ? "a newer answer (a fetch landed meanwhile)" : "STILL clear"));
                if (drvR4Held) break;
                if (attempt == 3) DrvBad("R4 class: the stats-not-answered state did not hold until the read in three attempts");
                yield return 1f;
            }
            if (ApiClient.CachedPlayerStats == null) { DrvBad("R4 class: the stats are still clear"); yield break; }
            if (StatsDiscordLinked()) { DrvNote("R4 class: this account has a linked Discord, so the first sweep was the linked state"); yield break; }
            for (int k = 0; k < 2; k++)
            {
                string state = "with a Discord linked in memory, Show Discord " + (k == 0 ? "on" : "off");
                for (int attempt = 1; attempt <= 3; attempt++)
                {
                    var st1 = ApiClient.CachedPlayerStats;
                    if (st1 == null) { DrvBad("R4 class: the stats went away, " + state + " is not reachable"); yield break; }
                    string user0 = st1.discord_username;
                    bool show0 = st1.show_discord;
                    try
                    {
                        st1.discord_username = "item13-witness";
                        st1.show_discord = k == 0;
                        yield return DrvR4Sweep(state, () => ApiClient.CachedPlayerStats == st1);
                    }
                    finally
                    {
                        st1.discord_username = user0;
                        st1.show_discord = show0;
                        dirty = true;
                    }
                    if (drvR4Held) break;
                    if (attempt == 3) DrvBad("R4 class: " + state + " did not hold until the read in three attempts");
                }
            }
            yield return 0.6f;   // the page repaints with every answer put back
        }

        private static bool drvR4Held;

        /// <summary>After a repaint, every switch row's widget says what its
        /// label's value word says: neutral (not known) beside a grey word -
        /// "checking...", "link Discord first", "..." - on beside a green
        /// word and off beside an orange one. The word's state is read from
        /// its colour tag, which every locale keeps. <paramref name="held"/>,
        /// when given, is the state's own condition, checked in the frame of
        /// the read (drvR4Held says whether it held).</summary>
        private static IEnumerator DrvR4Sweep(string state, Func<bool> held)
        {
            dirty = true;
            yield return 0.6f;
            drvR4Held = held == null || held();
            if (!drvR4Held) { DrvNote("R4 class, " + state + ": the state did not hold until the read (a newer stats answer landed)"); yield break; }
            int n = 0, agree = 0;
            foreach (var list in settingsTabRows)
                foreach (var rec in list)
                {
                    if (rec.Kind != SettingsKind.Switch || rec.Track == null || rec.Knob == null) continue;
                    n++;
                    string said = DrvWordState(rec.LastValue);
                    Color track = UIFactory.GetImageColor(rec.Track);
                    Color knob = UIFactory.GetImageColor(rec.Knob);
                    float kx = rec.Knob.GetComponent<RectTransform>().anchoredPosition.x;
                    string shown = DrvSameColor(track, SW_NA) && DrvSameColor(knob, SW_KNOB_NA) && Mathf.Abs(kx - 14f) < 0.5f ? "not known"
                        : DrvSameColor(track, SW_ON) && DrvSameColor(knob, SW_KNOB) && Mathf.Abs(kx - 26f) < 0.5f ? "on"
                        : DrvSameColor(track, SW_OFF) && DrvSameColor(knob, SW_KNOB) && Mathf.Abs(kx - 2f) < 0.5f ? "off"
                        : "no switch state (track " + DrvColor(track) + ", knob " + DrvColor(knob) + " at x="
                            + kx.ToString("0", CultureInfo.InvariantCulture) + ")";
                    string line = "R4 class, " + state + ": " + rec.Key + " word '" + SettingsModel.StripTags(rec.LastValue ?? "")
                        + "' says " + said + ", the switch shows " + shown;
                    if (said == shown) { agree++; DrvOk(line); }
                    else DrvBad(line);
                }
            if (n == 0) DrvBad("R4 class, " + state + ": no switch row was found");
            DrvNote("R4 class, " + state + ": " + agree + " of " + n + " switch rows agree with their label");
        }

        /// <summary>The state a row's value word claims, from its colour tag:
        /// #88FF88 on, #FF9966 off, any grey (equal channels) not known.</summary>
        private static string DrvWordState(string v)
        {
            int i = v == null ? -1 : v.IndexOf("<color=#", StringComparison.OrdinalIgnoreCase);
            int j = i < 0 ? -1 : v.IndexOf('>', i);
            if (j < 0) return "no state colour";
            string hex = v.Substring(i + 8, j - i - 8).ToUpperInvariant();
            if (hex.Length == 3) hex = new string(new[] { hex[0], hex[0], hex[1], hex[1], hex[2], hex[2] });
            if (hex == "88FF88") return "on";
            if (hex == "FF9966") return "off";
            if (hex.Length == 6 && hex.Substring(0, 2) == hex.Substring(2, 2) && hex.Substring(2, 2) == hex.Substring(4, 2)) return "not known";
            return "colour #" + hex;
        }

        /// <summary>Round-3 L5 (design T5-d): a stub seat for a same-stack
        /// read of cr_cmute. In a room PUN applies a player property to the
        /// seat that set it only on the server's echo (learning #428), and
        /// the publisher returns in offline mode, so neither gives a
        /// same-stack read. For ONE synchronous call this makes
        /// PhotonNetwork.InRoom true - the client's state FIELD set to
        /// Joined, never its State setter, whose StateChanged event would run
        /// - and PhotonNetwork.LocalPlayer a local Player the test created
        /// with no room reference, so the publisher's own
        /// local.SetCustomProperties(h) takes PUN's branch for a local player
        /// with no room: it merges the table into that player's
        /// CustomProperties and sends nothing. The test reads cr_cmute from
        /// that table. Both are put back in a finally before the call
        /// returns, so no frame - no PUN dispatch, no game tick - ever sees
        /// them. Refused while the seat is in a real room or in offline
        /// mode.</summary>
        private static FieldInfo drvSeatState;
        private static MethodInfo drvSeatSetLocal;
        private static ConstructorInfo drvSeatPlayer;

        private static string DrvStubSeatReady()
        {
            try
            {
                if (Photon.Pun.PhotonNetwork.NetworkingClient == null) return "PhotonNetwork.NetworkingClient is null";
                if (Photon.Pun.PhotonNetwork.OfflineMode) return "the seat is in offline mode";
                if (Photon.Pun.PhotonNetwork.InRoom) return "the seat is in a room";
                var lbc = typeof(Photon.Realtime.LoadBalancingClient);
                drvSeatState = lbc.GetField("state", BindingFlags.NonPublic | BindingFlags.Instance);
                var lp = lbc.GetProperty("LocalPlayer", BindingFlags.Public | BindingFlags.Instance);
                drvSeatSetLocal = lp != null ? lp.GetSetMethod(true) : null;
                drvSeatPlayer = typeof(Photon.Realtime.Player).GetConstructor(BindingFlags.NonPublic | BindingFlags.Instance, null,
                    new[] { typeof(string), typeof(int), typeof(bool) }, null);
                if (drvSeatState == null || drvSeatState.FieldType != typeof(Photon.Realtime.ClientState)) return "LoadBalancingClient.state was not found";
                if (drvSeatSetLocal == null) return "the LoadBalancingClient.LocalPlayer setter was not found";
                if (drvSeatPlayer == null) return "the Player(string, int, bool) constructor was not found";
                return null;
            }
            catch (Exception e) { return "the stub seat could not be prepared (" + e.GetType().Name + ")"; }
        }

        /// <summary>A local Player with no room, its cr_cmute planted: a boxed
        /// value the caller keeps, so "untouched" is reference identity.</summary>
        private static Photon.Realtime.Player DrvStubPlayer(object planted)
        {
            var p = (Photon.Realtime.Player)drvSeatPlayer.Invoke(new object[] { "item13-t5d-stub", 1, true });
            if (planted != null) p.CustomProperties[CompetitiveUI.CHAT_MUTE_PROP] = planted;
            return p;
        }

        private static object DrvCmute(Photon.Realtime.Player p)
        {
            object v = null;
            if (p != null && p.CustomProperties != null) p.CustomProperties.TryGetValue(CompetitiveUI.CHAT_MUTE_PROP, out v);
            return v;
        }

        private static int DrvMarker(CompetitiveUI.ChatOverlayMode m) { return m == CompetitiveUI.ChatOverlayMode.Muted ? 1 : 0; }

        private static string DrvShow(object v)
        {
            if (v == null) return "absent";
            if (v is int) return ((int)v).ToString(CultureInfo.InvariantCulture);
            return v.GetType().Name + " " + v;
        }

        /// <summary>act() in ONE call with the stub seat in place: InRoom true
        /// when joined, LocalPlayer the given player (null allowed). Returns
        /// what the call threw to its caller ("" for nothing); firstChance
        /// counts the exceptions raised on this thread inside it, caught or
        /// not (meaningful only when DriveT5d's probe counted its one).</summary>
        private static string DrvWithStubSeat(bool joined, Photon.Realtime.Player player, Action act, out int firstChance)
        {
            var nc = Photon.Pun.PhotonNetwork.NetworkingClient;
            object state0 = drvSeatState.GetValue(nc);
            var local0 = nc.LocalPlayer;
            int n = 0, tid = System.Threading.Thread.CurrentThread.ManagedThreadId;
            EventHandler<System.Runtime.ExceptionServices.FirstChanceExceptionEventArgs> fc = (s, e) =>
            {
                if (System.Threading.Thread.CurrentThread.ManagedThreadId == tid) n++;
            };
            string threw = "";
            AppDomain.CurrentDomain.FirstChanceException += fc;
            try
            {
                if (joined) drvSeatState.SetValue(nc, Photon.Realtime.ClientState.Joined);
                drvSeatSetLocal.Invoke(nc, new object[] { player });
                act();
            }
            catch (Exception e) { threw = e.GetType().Name; }
            finally
            {
                AppDomain.CurrentDomain.FirstChanceException -= fc;
                try { drvSeatState.SetValue(nc, state0); } catch { }
                try { drvSeatSetLocal.Invoke(nc, new object[] { local0 }); } catch { }
            }
            firstChance = n;
            if (!Equals(drvSeatState.GetValue(nc), state0) || !ReferenceEquals(nc.LocalPlayer, local0))
                threw += (threw.Length > 0 ? "; " : "") + "the seat was NOT put back";
            return threw;
        }

        private static string DrvThrew(string threw, int fc, bool fcLive)
        {
            string s = threw.Length > 0 ? "; the call THREW " + threw : "; the call threw nothing";
            if (fcLive) s += ", " + fc + " exception(s) raised inside it";
            return s;
        }

        private static ClickHandler DrvChatOption(SettingsRowRec rec, CompetitiveUI.ChatOverlayMode m)
        {
            int i = Array.IndexOf(rec.Ids, m.ToString());
            ClickHandler ch = i >= 0 && rec.Opts[i] != null ? rec.Opts[i].GetComponent<ClickHandler>() : null;
            return ch != null && ch.onClick != null ? ch : null;
        }

        /// <summary>Round-3 L5 (design T5-d): a click on a segmented SIgChat
        /// option republishes this seat's chat-mute marker IN THE SAME CALL
        /// STACK, never only through the 2 s reconciler in CompetitiveUI.Tick.
        /// Each click runs with the stub seat in place (DrvWithStubSeat), its
        /// cr_cmute planted at the marker of the mode the click leaves, and
        /// the property is read from the stub player's own table the moment
        /// the click returns: it must carry the new marker, and where the
        /// marker does not change the publisher must leave the planted value
        /// untouched (the same object). The reconciler's clock is read on both
        /// sides of the click. 2.5 s after each click the reconciler's publish
        /// (its body, run under the same stub) shows whether anything was
        /// left to repair: a repair is never the pass. Then each early return
        /// - an unchanged mode (a click on the lit option), no room (InRoom
        /// false) and no local player (LocalPlayer null) - leaves the property
        /// untouched, and no click throws. The mode found is put back by the
        /// last click, and the seat's own player property is checked
        /// untouched.</summary>
        private static IEnumerator DriveT5d()
        {
            SettingsRowRec rec;
            if (!settingsByKey.TryGetValue("SIgChat", out rec) || rec.Opts == null || rec.Ids == null
                || rec.Opts.Length != rec.Ids.Length)
            {
                DrvBad("T5-d the SIgChat row was not built");
                yield break;
            }
            var clock = typeof(CompetitiveUI).GetField("chatMutePublishTickAt", BindingFlags.NonPublic | BindingFlags.Static);
            if (clock == null)
            {
                DrvBad("T5-d the reconciler clock CompetitiveUI.chatMutePublishTickAt was not found");
                yield break;
            }
            string why = DrvStubSeatReady();
            if (why != null)
            {
                DrvBad("T5-d no stub seat: " + why);
                yield break;
            }
            // The first-chance count means something only if this runtime
            // raises the event: a probe whose only purpose is to be counted.
            int probe;
            string probeThrew = DrvWithStubSeat(false, null, () =>
            {
                try { throw new InvalidOperationException("item13 t5d first-chance probe"); }
                catch (InvalidOperationException) { }
            }, out probe);
            bool fcLive = probe == 1 && probeThrew.Length == 0;
            DrvNote("T5-d first-chance probe: one exception thrown and caught inside a stub-seat call counted " + probe
                + (fcLive ? "; every click below also counts the exceptions raised inside it, caught or not"
                          : "; this runtime raises no first-chance events, so a click shows only what it threw to its caller"));
            var real = Photon.Pun.PhotonNetwork.LocalPlayer;
            object real0 = DrvCmute(real);
            SettingsSwitchSubTab(rec.Tab);
            yield return 0.6f;
            var start = CompetitiveUI.CurrentChatOverlayMode();
            var order = new List<CompetitiveUI.ChatOverlayMode>();
            if (start != CompetitiveUI.ChatOverlayMode.Muted) order.Add(CompetitiveUI.ChatOverlayMode.Muted);
            foreach (var m in new[] { CompetitiveUI.ChatOverlayMode.Normal, CompetitiveUI.ChatOverlayMode.Pinned })
                if (m != start) order.Add(m);
            order.Add(start);
            DrvNote("T5-d the mode found: " + start + "; " + order.Count + " clicks, each a change, the last back to it; then the three early returns");
            foreach (var target in order)
            {
                ClickHandler ch = DrvChatOption(rec, target);
                if (ch == null)
                {
                    DrvBad("T5-d the SIgChat option " + target + " has no click handler");
                    yield break;
                }
                var from = CompetitiveUI.CurrentChatOverlayMode();
                int prev = DrvMarker(from), want = DrvMarker(target);
                object planted = prev;
                var seat = DrvStubPlayer(planted);
                int fc;
                // One call stack: clock, the click on the stub seat, clock, read.
                float t0 = (float)clock.GetValue(null);
                string threw = DrvWithStubSeat(true, seat, () => ch.onClick(), out fc);
                float t1 = (float)clock.GetValue(null);
                object got = DrvCmute(seat);
                var now = CompetitiveUI.CurrentChatOverlayMode();
                string step = "T5-d " + from + " -> " + target + ": ";
                string seen = "cr_cmute read from the stub seat when the click returned: " + DrvShow(got) + " (planted " + prev
                    + (ReferenceEquals(got, planted) ? ", the same object" : "") + "); the reconciler clock "
                    + (t1 == t0 ? "did not move" : "MOVED") + DrvThrew(threw, fc, fcLive);
                if (now != target) DrvBad(step + "the click did not reach the writer (the mode is " + now + ")");
                else if (t1 != t0) DrvBad(step + seen + " - a reconciler tick ran inside the click");
                else if (threw.Length > 0 || (fcLive && fc != 0)) DrvBad(step + seen + " - the click threw");
                else if (prev != want && got is int && (int)got == want)
                    DrvOk(step + seen + " = the new marker " + want + ", published in the click's call stack");
                else if (prev == want && ReferenceEquals(got, planted))
                    DrvOk(step + seen + " - the marker does not change (" + want + ") and the publisher's unchanged-value return left it untouched");
                else DrvBad(step + seen + ", want " + (prev == want ? "the planted " + prev + " untouched" : "the new marker " + want));
                yield return 2.5f;
                object before = DrvCmute(seat);
                int fc2;
                string threw2 = DrvWithStubSeat(true, seat, () => CompetitiveUI.PublishChatMuteState(), out fc2);
                object after = DrvCmute(seat);
                string what = ReferenceEquals(before, after) ? " - nothing to repair"
                    : after is int && (int)after == want ? " - it REPAIRED a publish the click did not make, which is NOT a pass"
                    : "";
                DrvNote(step + "2.5 s later the reconciler's publish (its body, run under the same stub seat) found " + DrvShow(before)
                    + " and left " + DrvShow(after) + what + DrvThrew(threw2, fc2, fcLive));
            }
            // The early returns: none may publish or throw.
            var cur = CompetitiveUI.CurrentChatOverlayMode();
            yield return DrvT5dEarly("unchanged mode (a click on the lit option " + cur + ")", rec, cur, true, true, fcLive);
            var away = cur != CompetitiveUI.ChatOverlayMode.Muted ? CompetitiveUI.ChatOverlayMode.Muted : CompetitiveUI.ChatOverlayMode.Normal;
            yield return DrvT5dEarly("no room (InRoom false)", rec, away, false, true, fcLive);
            yield return DrvT5dEarly("no local player (LocalPlayer null)", rec, start, true, false, fcLive);
            object real1 = DrvCmute(Photon.Pun.PhotonNetwork.LocalPlayer);
            if (ReferenceEquals(Photon.Pun.PhotonNetwork.LocalPlayer, real) && ReferenceEquals(real1, real0))
                DrvOk("T5-d the seat's own local player is in place and its cr_cmute untouched (" + DrvShow(real0) + ")");
            else DrvBad("T5-d the seat's own local player " + (ReferenceEquals(Photon.Pun.PhotonNetwork.LocalPlayer, real) ? "is in place" : "was NOT put back")
                + "; its cr_cmute " + DrvShow(real0) + " -> " + DrvShow(real1));
            if (CompetitiveUI.CurrentChatOverlayMode() != start) DrvBad("T5-d the mode found (" + start + ") was not put back: " + CompetitiveUI.CurrentChatOverlayMode());
        }

        /// <summary>One early return of the chat-mute publish (T5-d): a click on
        /// target with the stub seat in the given state. The planted value
        /// must be the same object when the click returns, and the click must
        /// not throw; with no local player there is no table to plant, so the
        /// click is judged by what it threw (and the seat's own player by
        /// DriveT5d's last check).</summary>
        private static IEnumerator DrvT5dEarly(string what, SettingsRowRec rec, CompetitiveUI.ChatOverlayMode target, bool joined,
            bool withPlayer, bool fcLive)
        {
            ClickHandler ch = DrvChatOption(rec, target);
            if (ch == null)
            {
                DrvBad("T5-d early return, " + what + ": the SIgChat option " + target + " has no click handler");
                yield break;
            }
            var from = CompetitiveUI.CurrentChatOverlayMode();
            object planted = DrvMarker(from);
            var seat = withPlayer ? DrvStubPlayer(planted) : null;
            int fc;
            string threw = DrvWithStubSeat(joined, seat, () => ch.onClick(), out fc);
            object got = DrvCmute(seat);
            var now = CompetitiveUI.CurrentChatOverlayMode();
            string step = "T5-d early return, " + what + ", " + from + " -> " + target + ": ";
            string seen = (withPlayer ? "cr_cmute " + DrvShow(got) + " (planted " + DrvShow(planted) + (ReferenceEquals(got, planted) ? ", the same object" : "") + ")"
                : "no local player, so no table") + DrvThrew(threw, fc, fcLive);
            if (now != target) DrvBad(step + "the mode is " + now + " after the click, want " + target);
            else if (threw.Length > 0 || (fcLive && fc != 0)) DrvBad(step + seen + " - the click threw");
            else if (withPlayer && !ReferenceEquals(got, planted)) DrvBad(step + seen + " - the property was written");
            else DrvOk(step + seen + " - nothing published, nothing thrown");
            yield return 0.4f;
        }

        // ---------------------------------------------------------------
        // Round-2 MEDIUM-3: the design's section-10 tests that need a
        // running client - T4, T5-a/b/c/e/f/g/h and T7 - driven here.
        // ---------------------------------------------------------------

        /// <summary>Presses of the Leave-all-queues row while a settings test
        /// ran (design T5-a). Each would otherwise have been a request.</summary>
        internal static int settingsEscapeStubCalls;

        /// <summary>Mail settings PUTs that reached the stub while a settings
        /// test ran (design T5-e, T7-c). Each is answered ok 1.5 s later - one
        /// round trip - through the caller's own callback; nothing is sent.</summary>
        internal static int settingsPutStubCalls;
        private static readonly List<KeyValuePair<float, Action<bool, string>>> settingsPutStubDue =
            new List<KeyValuePair<float, Action<bool, string>>>();

        internal static void SettingsStubPut(string what, Action<bool, string> cb)
        {
            settingsPutStubCalls++;
            Plugin.Log.LogInfo("[SETTINGS-DRIVE] mail PUT " + settingsPutStubCalls + " reached the stub (" + what + "; not sent)");
            settingsPutStubDue.Add(new KeyValuePair<float, Action<bool, string>>(Time.unscaledTime + 1.5f, cb));
        }

        /// <summary>Answers the stubbed PUTs whose round trip is over, in order.</summary>
        private static void SettingsStubDeliver()
        {
            float now = Time.unscaledTime;
            while (settingsPutStubDue.Count > 0 && settingsPutStubDue[0].Key <= now)
            {
                var cb = settingsPutStubDue[0].Value;
                settingsPutStubDue.RemoveAt(0);
                try { if (cb != null) cb(true, "{}"); }
                catch (Exception e) { Plugin.Log.LogWarning("[SETTINGS-DRIVE] a stub answer threw: " + e.Message); }
            }
        }

        /// <summary>The frame the harness pressed Escape in (design T5-b).</summary>
        private static int settingsDriveEscFrame = -1;

        /// <summary>Escape as NativeUI.Tick reads it: the real key, or a press
        /// the driven-input harness made in this frame. Tick reads it at every
        /// point it read Input.GetKeyDown(KeyCode.Escape), so a driven press
        /// meets the surfaces that own Escape in the same order a real one
        /// does.</summary>
        private static bool EscDown()
        {
            return settingsDriveEscFrame == Time.frameCount || Input.GetKeyDown(KeyCode.Escape);
        }

        /// <summary>One Escape press, read by the rest of this frame's Tick
        /// (SettingsDriveTick runs first in it), then a settle.</summary>
        private static IEnumerator DrvEscape()
        {
            settingsDriveEscFrame = Time.frameCount;
            yield return 0.6f;
        }

        /// <summary>A capture point: the runner that launched the game takes a
        /// screenshot while this state is held (12 s: the runner polls the log,
        /// then starts its capture script). The line says whether this
        /// seat is in a live online room, so a capture taken during a match is
        /// known and discarded.</summary>
        private static IEnumerator DrvCapture(string name)
        {
            bool room = false;
            try { room = OverlayIdleClose.InLiveOnlineRoom; } catch { }
            DrvNote("CAPTURE " + name + " screen " + Screen.width + "x" + Screen.height
                + " (live online room: " + (room ? "YES - discard this capture" : "none") + ")");
            yield return 12f;
        }

        private const BindingFlags DrvPriv = BindingFlags.NonPublic | BindingFlags.Static;

        private static SettingsRowRec DrvRec(string key)
        {
            SettingsRowRec r;
            return key != null && settingsByKey.TryGetValue(key, out r) ? r : null;
        }

        /// <summary>A click through the control's own click handler - the
        /// path a mouse click takes once its hit test has passed.</summary>
        private static bool DrvClick(GameObject go)
        {
            var ch = go != null ? go.GetComponent<ClickHandler>() : null;
            if (ch == null || ch.onClick == null) return false;
            ch.onClick();
            return true;
        }

        /// <summary>Wait until the page is open on the settings tab with its
        /// latest build painted and no rebuild for `quiet` seconds (at most
        /// 15 s).</summary>
        private static IEnumerator DrvSettle(float quiet)
        {
            float limit = Time.unscaledTime + 15f, since = Time.unscaledTime;
            int gen = settingsBuildGen;
            while (Time.unscaledTime < limit)
            {
                bool ready = isOpen && pageBuilt && currentTab == TAB_SETTINGS && settingsPaintedGen == settingsBuildGen;
                if (!ready || settingsBuildGen != gen) { gen = settingsBuildGen; since = Time.unscaledTime; }
                else if (Time.unscaledTime - since >= quiet) yield break;
                yield return 0.1f;
            }
            DrvNote(drvCurrent + ": the page did not settle within 15 s");
        }

        /// <summary>Move the keyboard focus onto a row with the arrow keys,
        /// through the page's own poll.</summary>
        private static IEnumerator DrvArrowFocus(string key, string tag)
        {
            var r = DrvRec(key);
            if (r == null) { DrvBad(tag + " the " + key + " row was not built"); yield break; }
            if (settingsSubTab != r.Tab) { SettingsSwitchSubTab(r.Tab); yield return 0.3f; }
            for (int guard = 0; guard < 40; guard++)
            {
                var list = SettingsFocusList(settingsSubTab);
                int want = list.IndexOf(r);
                if (want < 0) { DrvBad(tag + " " + key + " is not in its sub-tab's focus list"); yield break; }
                int cur = Mathf.Clamp(settingsFocusRow[settingsSubTab], 0, list.Count - 1);
                if (cur == want) yield break;
                yield return DrvPress(want > cur ? SettingsModel.SettingsKey.Down : SettingsModel.SettingsKey.Up, 0.1f);
            }
        }

        private static bool DrvPickerOpen()
        {
            var f = typeof(CompetitiveUI).GetField("artistPickerOpen", DrvPriv);
            return f != null && (bool)f.GetValue(null);
        }

        /// <summary>The open picker's own Use / Clear branch (DrawArtistPicker):
        /// close it, drop its callback, then hand the callback the id - what a
        /// click on the IMGUI button does once its hit test has passed.</summary>
        private static bool DrvPickerChoose(string id)
        {
            var fOpen = typeof(CompetitiveUI).GetField("artistPickerOpen", DrvPriv);
            var fCb = typeof(CompetitiveUI).GetField("artistPickerOnPick", DrvPriv);
            if (fOpen == null || fCb == null || !(bool)fOpen.GetValue(null)) return false;
            var cb = fCb.GetValue(null) as Action<string>;
            fOpen.SetValue(null, false);
            fCb.SetValue(null, null);
            try { if (cb != null) cb(id); }
            catch (Exception e) { Plugin.Log.LogWarning("[SETTINGS-DRIVE] picker choice threw: " + e.Message); }
            return true;
        }

        private static string DrvNum(float f) { return f.ToString("0.###", CultureInfo.InvariantCulture); }

        /// <summary>A row's value as a string: a switch "True"/"False", a
        /// segmented or dropdown row its id, a slider its stop's number; null
        /// for a row that stores nothing.</summary>
        private static string DrvValue(SettingsRowRec r)
        {
            if (r == null) return null;
            try
            {
                switch (r.Kind)
                {
                    case SettingsKind.Switch: return r.GetBool != null ? (r.GetBool() ? "True" : "False") : null;
                    case SettingsKind.Segmented:
                    case SettingsKind.Dropdown: return r.Current != null ? r.Current() : null;
                    case SettingsKind.Slider:
                        if (r.Index == null || r.Stops == null || r.Stops.Length == 0) return null;
                        return DrvNum(r.Stops[Mathf.Clamp(r.Index(), 0, r.Stops.Length - 1)]);
                }
            }
            catch { }
            return null;
        }

        /// <summary>A reset operand in DrvValue's form.</summary>
        private static string DrvOperand(object o)
        {
            if (o == null) return null;
            if (o is bool) return (bool)o ? "True" : "False";
            if (o is float) return DrvNum((float)o);
            if (o is int) return ((int)o).ToString(CultureInfo.InvariantCulture);
            return o.ToString();
        }

        private static string[] DrvOptions(SettingsRowRec r)
        {
            if (r == null) return null;
            switch (r.Kind)
            {
                case SettingsKind.Switch: return new[] { "True", "False" };
                case SettingsKind.Segmented: return r.Ids;
                case SettingsKind.Dropdown: try { return r.IdsF != null ? r.IdsF() : null; } catch { return null; }
                case SettingsKind.Slider:
                    if (r.Stops == null) return null;
                    var s = new string[r.Stops.Length];
                    for (int i = 0; i < s.Length; i++) s[i] = DrvNum(r.Stops[i]);
                    return s;
            }
            return null;
        }

        /// <summary>The row's last option that differs from v.</summary>
        private static string DrvAway(SettingsRowRec r, string v)
        {
            var o = DrvOptions(r);
            if (o == null) return null;
            for (int i = o.Length - 1; i >= 0; i--) if (o[i] != v) return o[i];
            return null;
        }

        /// <summary>Set a row to a value through its own control: a switch's
        /// track, a segmented option, a dropdown opened by its face and chosen
        /// in the picker, a slider moved to the stop.</summary>
        private static bool DrvSetValue(SettingsRowRec r, string v)
        {
            if (r == null || v == null) return false;
            if (DrvValue(r) == v) return true;
            switch (r.Kind)
            {
                case SettingsKind.Switch: return DrvClick(r.Track);
                case SettingsKind.Segmented:
                    int i = r.Ids != null ? Array.IndexOf(r.Ids, v) : -1;
                    return i >= 0 && r.Opts != null && DrvClick(r.Opts[i]);
                case SettingsKind.Dropdown:
                    if (!DrvClick(r.Face) || !DrvPickerOpen()) return false;
                    return DrvPickerChoose(v);
                case SettingsKind.Slider:
                    var o = DrvOptions(r);
                    int k = o != null ? Array.IndexOf(o, v) : -1;
                    if (k < 0) return false;
                    SettingsSetSliderIndex(r, k);
                    return true;
            }
            return false;
        }

        /// <summary>Every value-storing row's value, by key.</summary>
        private static Dictionary<string, string> DrvSnapshot()
        {
            var d = new Dictionary<string, string>();
            foreach (var desc in SettingsDescriptors.All)
            {
                string v = DrvValue(DrvRec(desc.Key));
                if (v != null) d[desc.Key] = v;
            }
            return d;
        }

        private static List<string> DrvChanged(Dictionary<string, string> a, Dictionary<string, string> b)
        {
            var l = new List<string>();
            foreach (var kv in b) { string v; if (!a.TryGetValue(kv.Key, out v) || v != kv.Value) l.Add(kv.Key); }
            foreach (var kv in a) if (!b.ContainsKey(kv.Key)) l.Add(kv.Key);
            l.Sort(StringComparer.Ordinal);
            return l;
        }

        private static string DrvList(IEnumerable<string> l)
        {
            return "[" + string.Join(",", new List<string>(l).ToArray()) + "]";
        }

        // --- the PlayerPrefs a settings test can move ---------------------

        private static bool DrvPrefIsInt(string k)
        {
            return k == "OPTION_LANGUAGE" || k.StartsWith("CR_Mail_Relay_", StringComparison.Ordinal);
        }

        private static string DrvPrefLabel(string k)
        {
            return k.StartsWith("CR_Mail_", StringComparison.Ordinal) ? k.Substring(0, k.LastIndexOf('_')) + "_<steamid>" : k;
        }

        private static string DrvPrefRead(string k)
        {
            if (!PlayerPrefs.HasKey(k)) return null;
            return DrvPrefIsInt(k) ? PlayerPrefs.GetInt(k).ToString(CultureInfo.InvariantCulture) : PlayerPrefs.GetString(k);
        }

        /// <summary>The PlayerPrefs a settings test can move: the cursor
        /// shape, the two mail caches and the game's language (which
        /// I18n.SetLocale writes), as stored; null: not stored.</summary>
        private static List<KeyValuePair<string, string>> DrvPrefState()
        {
            var l = new List<KeyValuePair<string, string>>();
            foreach (var k in new[] { "cr_cursor_shape", MailClient.PrefKey("From"), MailClient.PrefKey("Relay"), "OPTION_LANGUAGE" })
                l.Add(new KeyValuePair<string, string>(k, DrvPrefRead(k)));
            return l;
        }

        private static string DrvPrefSummary(List<KeyValuePair<string, string>> st)
        {
            var parts = new List<string>();
            foreach (var kv in st) parts.Add(DrvPrefLabel(kv.Key) + " " + (kv.Value == null ? "not stored" : "'" + kv.Value + "'"));
            return string.Join("; ", parts.ToArray());
        }

        /// <summary>Put those PlayerPrefs back exactly as found - a key that
        /// was not stored is removed again - and say so.</summary>
        private static void DrvPrefRestore(List<KeyValuePair<string, string>> saved, string tag)
        {
            var moved = new List<string>();
            bool ok = true;
            foreach (var kv in saved)
            {
                string cur = DrvPrefRead(kv.Key);
                if (cur == kv.Value) continue;
                if (kv.Value == null) PlayerPrefs.DeleteKey(kv.Key);
                else if (DrvPrefIsInt(kv.Key)) PlayerPrefs.SetInt(kv.Key, int.Parse(kv.Value, CultureInfo.InvariantCulture));
                else PlayerPrefs.SetString(kv.Key, kv.Value);
                moved.Add(DrvPrefLabel(kv.Key));
                if (DrvPrefRead(kv.Key) != kv.Value) ok = false;
            }
            try { PlayerPrefs.Save(); } catch { }
            string msg = tag + " PlayerPrefs as found: " + DrvPrefSummary(DrvPrefState())
                + (moved.Count == 0 ? " (none moved)" : " (put back: " + string.Join(", ", moved.ToArray()) + ")");
            if (ok) DrvNote(msg); else DrvBad(tag + " PlayerPrefs NOT as found: " + DrvPrefSummary(DrvPrefState()));
        }

        // --- T4: the six rebuild routes -----------------------------------

        /// <summary>MEDIUM-3 / design T4: every rebuild route lands on the
        /// remembered sub-tab (A7) with every label painted, and the tab is
        /// then measured (A5, A8) exactly as the self-test measures a tab. The
        /// remembered sub-tab is 4 (Performance). Each route is entered at its
        /// own entry point: the closed page re-parented, then opened (Open's
        /// re-parent test); the page host deactivated under the open page
        /// (Tick's host recovery), then the page opened; a catalogue install
        /// (RequestCatalogueRebuild); the first-run language prompt's button;
        /// the language row's picker; the heavy-font switch, and once more to
        /// put it back. Both language routes choose the language in use, so
        /// the locale never changes; the stored language and the game's
        /// language pref are put back exactly.</summary>
        private static IEnumerator DriveT4()
        {
            const int want = 4;
            string[] routes = { "open/re-parent", "host recovery", "catalogue install", "first-run language prompt",
                                "language row", "heavy-font switch", "heavy-font switch back" };
            var prefs0 = DrvPrefState();
            string savedLang = Plugin.ModLanguage != null ? Plugin.ModLanguage.Value : null;
            for (int ri = 0; ri < routes.Length; ri++)
            {
                string tag = "T4 " + routes[ri] + ": ";
                yield return DrvOpenSettings();
                yield return DrvSettle(0.6f);
                SettingsSwitchSubTab(want);
                yield return 0.4f;
                int g0 = settingsBuildGen;
                int id0 = pageGO != null ? pageGO.GetInstanceID() : 0;
                bool entered = true;
                switch (ri)
                {
                    case 0:
                        Close();
                        if (pageGO != null) pageGO.transform.SetParent(null, false);
                        DevOpenTab(TAB_SETTINGS);
                        break;
                    case 1:
                        if (pageGO != null) pageGO.SetActive(false);
                        yield return 0.5f;
                        if (isOpen) DrvNote(tag + "the page still counted as open after its host went inactive");
                        DevOpenTab(TAB_SETTINGS);
                        break;
                    case 2:
                        RequestCatalogueRebuild();
                        break;
                    case 3:
                        entered = DrvPromptRoute(tag);
                        break;
                    case 4:
                        var lang = DrvRec("SLang");
                        entered = lang != null && DrvClick(lang.Face) && DrvPickerOpen() && DrvPickerChoose(I18n.Locale);
                        break;
                    default:
                        var hf = DrvRec("SHeavyFont");
                        entered = hf != null && DrvClick(hf.Track);
                        break;
                }
                if (!entered) { DrvBad(tag + "the route could not be entered"); continue; }
                yield return DrvSettle(1.0f);
                bool rebuilt = settingsBuildGen > g0 && pageGO != null && pageGO.GetInstanceID() != id0;
                if (!rebuilt)
                {
                    DrvBad(tag + "the page was not rebuilt (build " + g0 + " -> " + settingsBuildGen + ")");
                    continue;
                }
                DrvNote(tag + "a new page, build " + g0 + " -> " + settingsBuildGen);
                DrvCheckA7(tag, want);
                DrvMeasureA5A8(tag);
            }
            if (Plugin.ModLanguage != null && savedLang != null && Plugin.ModLanguage.Value != savedLang)
            {
                DrvPutBackStoredLanguage(savedLang);
                DrvNote("T4 the stored language was put back");
            }
            DrvPrefRestore(prefs0, "T4");
        }

        /// <summary>T4's fourth route: with the stored language unset, the
        /// first-run prompt shows; its button for the language in use is
        /// clicked.</summary>
        private static bool DrvPromptRoute(string tag)
        {
            if (Plugin.ModLanguage == null) return false;
            string code = I18n.Locale;
            DrvClearStoredLanguage();
            MaybeShowLanguagePrompt();
            var btn = langPromptGO != null ? SettingsFindDeep(langPromptGO.transform, "LP_" + code) : null;
            if (btn != null) return DrvClick(btn.gameObject);
            DrvBad(tag + "the prompt showed no button for '" + code + "'");
            try { if (langPromptGO != null) UnityEngine.Object.Destroy(langPromptGO); } catch { }
            langPromptGO = null;
            return false;
        }

        /// <summary>T4's fourth route needs the first-run state, the stored
        /// language unset, before MaybeShowLanguagePrompt builds the prompt;
        /// the prompt's button then stores the choice through SetModLanguage.
        /// This clear and DrvPutBackStoredLanguage are the harness's writes of
        /// the entry outside its writer, and the single-writer gate
        /// (backend/tests/test_settings_single_writer.py) names both as
        /// exceptions. Neither switches the locale or rebuilds the page.</summary>
        private static void DrvClearStoredLanguage()
        {
            Plugin.ModLanguage.Value = I18n.LOCALE_UNSET;
        }

        /// <summary>Puts the stored language back as T4 found it; the locale
        /// in use is not touched.</summary>
        private static void DrvPutBackStoredLanguage(string saved)
        {
            Plugin.ModLanguage.Value = saved;
        }

        private static void DrvCheckA7(string tag, int want)
        {
            bool bodiesOk = true;
            for (int i = 0; i < SETTINGS_TABS; i++)
                if (settingsBodies[i] != null && settingsBodies[i].activeSelf != (i == want)) bodiesOk = false;
            if (settingsSubTab == want && bodiesOk) DrvOk(tag + "A7 the remembered sub-tab " + want + " is the one shown (active bodies [" + SelfTestActiveBodies() + "])");
            else DrvBad(tag + "A7 sub-tab " + settingsSubTab + ", active bodies [" + SelfTestActiveBodies() + "], want exactly body " + want);
            var empty = new List<string>();
            foreach (var d in SettingsDescriptors.All)
            {
                SettingsRowRec r;
                if (!settingsByKey.TryGetValue(d.Key, out r) || string.IsNullOrEmpty(r.LastPainted)) empty.Add(d.Key);
            }
            if (empty.Count == 0) DrvOk(tag + "A7 all " + SettingsDescriptors.All.Length + " labels painted");
            else DrvBad(tag + "A7 unpainted: " + string.Join(",", empty.ToArray()));
        }

        /// <summary>A5 and A8 on the tab on screen, measured exactly as the
        /// self-test measures a tab (SettingsCheckA5A8 is the self-test's own
        /// check).</summary>
        private static void DrvMeasureA5A8(string tag, List<string> obs = null)
        {
            int tab = Mathf.Clamp(settingsSubTab, 0, SETTINGS_TABS - 1);
            SettingsForceLayout();
            SettingsUpdateHint();
            SettingsForceLayout();
            float tol = 1.0f * SettingsCanvasScale();
            var rows = SettingsFocusList(tab);
            float content = SettingsActiveContentHeight();
            float vpNoHint = SettingsViewportNoHint();
            bool over = content > vpNoHint + 0.5f;
            string home = SettingsModel.SubTabHomes[tab];
            SettingsCheckA5A8(home, rows, content, vpNoHint, over, tol,
                m => DrvOk(tag + m), m => DrvBad(tag + m),
                m => { DrvNote(tag + m); if (obs != null && m.StartsWith("OBSERVATION A5b ", StringComparison.Ordinal)) obs.Add(home); });
        }

        // --- T5-a: modal press-through ------------------------------------

        /// <summary>MEDIUM-3 / design T5-a: with the focus arrowed onto the
        /// Leave-all-queues row (SEBtn), open the bug report, then press
        /// Space, Left, Right and Down - handed to the page's own poll as a
        /// real key is. Nothing may reach the page: the poll takes no key, the
        /// queue leave does not run (its press reaches the stub,
        /// settingsEscapeStubCalls, so a press that got through is counted and
        /// never sent), the focus does not move and no setting changes. Then
        /// again with a dropdown open.</summary>
        private static IEnumerator DriveT5a()
        {
            var keys = new[] { SettingsModel.SettingsKey.Space, SettingsModel.SettingsKey.Left,
                               SettingsModel.SettingsKey.Right, SettingsModel.SettingsKey.Down };
            for (int pass = 0; pass < 2; pass++)
            {
                string what = pass == 0 ? "the bug report open" : "the SDateFmt dropdown open";
                yield return DrvArrowFocus("SEBtn", "T5-a");
                if (!DrvFocusIs("SEBtn", "T5-a")) yield break;
                if (pass == 0) CompetitiveUI.OpenBugReportModal();
                else
                {
                    var df = DrvRec("SDateFmt");
                    if (df != null) SettingsOpenDropdown(df);
                    if (!DrvPickerOpen()) { DrvBad("T5-a the SDateFmt dropdown did not open"); continue; }
                }
                yield return 0.4f;
                if (!CompetitiveUI.KeyboardInputOwnedByModal)
                {
                    DrvBad("T5-a precondition: with " + what + " no modal owns the keyboard");
                    DrvT5aClose(pass);
                    continue;
                }
                var before = DrvSnapshot();
                int esc0 = settingsEscapeStubCalls, taken = 0;
                foreach (var k in keys)
                {
                    yield return DrvPress(k, 0.2f, 0.8f);
                    if (settingsDriveKeyTaken) taken++;
                }
                var f = SettingsFocusedRec();
                string focus = f != null ? f.Key : "nothing";
                int esc = settingsEscapeStubCalls - esc0;
                var changed = DrvChanged(before, DrvSnapshot());
                if (taken == 0 && esc == 0 && focus == "SEBtn" && changed.Count == 0)
                    DrvOk("T5-a with " + what + ": the page's poll took 0 of " + keys.Length
                        + " keys (Space, Left, Right, Down); 0 queue leaves; the focus stays on SEBtn; no setting changed");
                else
                    DrvBad("T5-a with " + what + ": the poll took " + taken + " of " + keys.Length + " keys; " + esc
                        + " queue leave(s) reached the stub; the focus is on " + focus + "; changed " + DrvList(changed));
                DrvT5aClose(pass);
                yield return 0.5f;
            }
        }

        private static void DrvT5aClose(int pass)
        {
            if (pass == 0)
            {
                var f = typeof(CompetitiveUI).GetField("bugModalOpen", DrvPriv);
                if (f != null) f.SetValue(null, false);
            }
            else if (DrvPickerOpen()) CompetitiveUI.ConsumePromptEscape();
        }

        // --- T5-b: Escape ownership ---------------------------------------

        /// <summary>MEDIUM-3 / design T5-b: with a dropdown open, Escape closes
        /// the dropdown, writes nothing and leaves the settings page open; a
        /// second Escape closes the page. The press is read where Tick reads
        /// Escape (EscDown), so it meets the same owners in the same order.</summary>
        private static IEnumerator DriveT5b()
        {
            var df = DrvRec("SDateFmt");
            if (df == null) { DrvBad("T5-b the SDateFmt row was not built"); yield break; }
            SettingsSwitchSubTab(df.Tab);
            yield return 0.4f;
            if (!DrvClick(df.Face) || !DrvPickerOpen()) { DrvBad("T5-b the SDateFmt dropdown did not open"); yield break; }
            yield return 0.4f;
            var before = DrvSnapshot();
            yield return DrvEscape();
            bool pickerOpen = DrvPickerOpen(), pageOpen = isOpen && currentTab == TAB_SETTINGS;
            var changed = DrvChanged(before, DrvSnapshot());
            if (!pickerOpen && pageOpen && changed.Count == 0)
                DrvOk("T5-b the first Escape closed the dropdown, wrote nothing and left the settings page open");
            else
                DrvBad("T5-b after the first Escape: the dropdown " + (pickerOpen ? "open" : "closed") + ", the page "
                    + (pageOpen ? "open" : "CLOSED") + ", changed " + DrvList(changed));
            if (!pageOpen)
            {
                if (DrvPickerOpen()) CompetitiveUI.ConsumePromptEscape();
                yield return DrvOpenSettings();
                yield break;
            }
            yield return DrvEscape();
            if (!isOpen) DrvOk("T5-b control: the second Escape closed the page");
            else DrvBad("T5-b control: the second Escape left the page open");
            yield return DrvOpenSettings();
        }

        // --- T5-c: the dropdown call contract -----------------------------

        /// <summary>MEDIUM-3 / design T5-c. Stage 1: an open settings dropdown
        /// draws no Clear button - DrawArtistPicker draws "Clear (house)" when
        /// its showClear flag is set, and the page passes false; the state is
        /// held at a capture point. Stage 2: a Clear - the picker's Clear
        /// branch, the callback handed an empty id - reaches no setter,
        /// because the page's callback drops an empty pick. The row's setter
        /// is wrapped for the case so what it receives is recorded; the row's
        /// value is read before and after.</summary>
        private static IEnumerator DriveT5c()
        {
            var r = DrvRec("SDateFmt");
            if (r == null) { DrvBad("T5-c the SDateFmt row was not built"); yield break; }
            SettingsSwitchSubTab(r.Tab);
            yield return 0.4f;
            var pick0 = r.Pick;
            var got = new List<string>();
            r.Pick = id => { got.Add(id == null ? "(null)" : "'" + id + "'"); if (pick0 != null) pick0(id); };
            try
            {
                string v0 = DrvValue(r);
                if (!DrvClick(r.Face) || !DrvPickerOpen()) { DrvBad("T5-c the SDateFmt dropdown did not open"); yield break; }
                yield return 0.3f;
                var fClear = typeof(CompetitiveUI).GetField("artistPickerShowClear", DrvPriv);
                bool clear = fClear != null && (bool)fClear.GetValue(null);
                if (fClear == null) DrvBad("T5-c the picker's showClear flag was not found");
                else if (!clear) DrvOk("T5-c stage 1: the open SDateFmt dropdown draws 2 buttons (Cancel, Use) and no Clear (house)");
                else DrvBad("T5-c stage 1: the open SDateFmt dropdown draws 3 buttons, Clear (house) among them");
                yield return DrvCapture("t5c-picker");
                DrvPickerChoose("");
                yield return 0.5f;
                string v1 = DrvValue(r);
                if (got.Count == 0 && v1 == v0) DrvOk("T5-c stage 2: a Clear reached no setter; the row still reads " + v0);
                else DrvBad("T5-c stage 2: the setter received " + DrvList(got) + "; the row reads " + v1 + " (was " + v0 + ")");
            }
            finally
            {
                r.Pick = pick0;
                if (DrvPickerOpen()) CompetitiveUI.ConsumePromptEscape();
            }
        }

        // --- T5-e: the two server setters --------------------------------

        /// <summary>MEDIUM-3 / design T5-e. Two SMailFrom picks inside one round
        /// trip send exactly one PUT, and the value stored is the first pick;
        /// SMailRelay with no linked Discord sends no PUT and shows the
        /// existing notice. Every PUT reaches the stub (answered ok after one
        /// round trip, nothing sent). The session facts the relay reads are
        /// set for the case and put back; the mail caches are put back
        /// exactly.</summary>
        private static IEnumerator DriveT5e()
        {
            var prefs0 = DrvPrefState();
            var mf = DrvRec("SMailFrom");
            if (mf == null) { DrvBad("T5-e the SMailFrom row was not built"); yield break; }
            SettingsSwitchSubTab(mf.Tab);
            yield return 0.4f;
            string orig = MailClient.MailFrom;
            var others = new List<string>();
            foreach (var v in MailClient.MAIL_FROM_VALUES) if (v != orig) others.Add(v);
            int put0 = settingsPutStubCalls;
            bool a = DrvSetValue(mf, others[0]);
            yield return 0.3f;
            bool b = DrvSetValue(DrvRec("SMailFrom"), others[1]);
            int puts = settingsPutStubCalls - put0;
            yield return 2.2f;
            string stored = MailClient.MailFrom;
            if (a && b && puts == 1 && stored == others[0])
                DrvOk("T5-e two SMailFrom picks inside one round trip ('" + others[0] + "', then '" + others[1]
                    + "'): 1 PUT, and the stored value is the first pick ('" + stored + "')");
            else
                DrvBad("T5-e two SMailFrom picks inside one round trip: " + puts + " PUT(s), stored '" + stored + "'"
                    + (a && b ? "" : "; a pick did not go through (" + a + ", " + b + ")"));
            if (MailClient.MailFrom != orig)
            {
                DrvSetValue(DrvRec("SMailFrom"), orig);
                yield return 2.2f;
            }

            var mr = DrvRec("SMailRelay");
            if (mr == null) { DrvBad("T5-e the SMailRelay row was not built"); DrvPrefRestore(prefs0, "T5-e"); yield break; }
            bool seen0 = MailClient.StatusEverSeen, linked0 = MailClient.DiscordLinked, relay0 = MailClient.DiscordRelay;
            var fNotif = typeof(CompetitiveUI).GetField("notifText", DrvPriv);
            bool notifOn = Plugin.ShowNotifications != null && Plugin.ShowNotifications.Value;
            string linkFirst = "Link your Discord first: Home tab -> Get Link Code, then !link YOUR_CODE in Discord.";
            string wantNotice = I18n.Tr(linkFirst);
            try
            {
                MailClient.StatusEverSeen = true;
                MailClient.DiscordLinked = false;
                if (fNotif != null) fNotif.SetValue(null, "");
                int p0 = settingsPutStubCalls;
                bool clicked = DrvClick(mr.Track);
                int p = settingsPutStubCalls - p0;
                string notice = fNotif != null ? (fNotif.GetValue(null) as string ?? "") : "";
                bool said = notifOn ? notice == wantNotice : notice.Length == 0;
                if (clicked && p == 0 && said)
                    DrvOk("T5-e SMailRelay clicked with no linked Discord: 0 PUTs; "
                        + (notifOn ? "the notice is the existing one: '" + notice + "'" : "notices are off (SNT), so none is shown"));
                else
                    DrvBad("T5-e SMailRelay clicked with no linked Discord: " + p + " PUT(s), the notice '" + notice + "'"
                        + (clicked ? "" : " (the click did not reach the switch)"));
            }
            finally
            {
                MailClient.StatusEverSeen = seen0;
                MailClient.DiscordLinked = linked0;
            }
            yield return 2.2f;
            if (MailClient.DiscordRelay != relay0) MailClient.DiscordRelay = relay0;
            DrvPrefRestore(prefs0, "T5-e");
            dirty = true;
        }

        // --- T5-f: canonical writes and live effects ----------------------

        private static BepInEx.Configuration.ConfigEntryBase DrvCfgEntry(string key)
        {
            switch (key)
            {
                case "SMenuMus": return Plugin.MenuMusicMode;
                case "SBloom": return Plugin.BloomStrength;
                case "SShake": return Plugin.ScreenShakeStrength;
                case "SHpPrec":
                    var m = typeof(TabStatsOverlay.HealthPrecisionSetting).GetMethod("Entry", DrvPriv);
                    return m != null ? m.Invoke(null, null) as BepInEx.Configuration.ConfigEntryBase : null;
            }
            return null;
        }

        /// <summary>The entry's value as the .cfg file on disk holds it (the
        /// config saves on every set). Only that one line is read out.</summary>
        private static string DrvCfgOnDisk(BepInEx.Configuration.ConfigEntryBase e)
        {
            if (e == null) return "(no entry)";
            try
            {
                string sect = null;
                foreach (var raw in System.IO.File.ReadAllLines(e.ConfigFile.ConfigFilePath))
                {
                    string l = raw.Trim();
                    if (l.StartsWith("[", StringComparison.Ordinal) && l.EndsWith("]", StringComparison.Ordinal))
                    {
                        sect = l.Substring(1, l.Length - 2);
                        continue;
                    }
                    if (sect != e.Definition.Section || l.StartsWith("#", StringComparison.Ordinal)) continue;
                    int eq = l.IndexOf('=');
                    if (eq > 0 && l.Substring(0, eq).Trim() == e.Definition.Key) return l.Substring(eq + 1).Trim();
                }
            }
            catch (Exception ex) { return "(unreadable: " + ex.GetType().Name + ")"; }
            return "(no line)";
        }

        /// <summary>Every live Bloom the renderer reads (a volume's own profile
        /// where it has one, else its shared one - never creating one): on or
        /// off and its intensity. Empty when no volume carries a Bloom.</summary>
        private static string DrvBloomState()
        {
            var parts = new List<string>();
            try
            {
                foreach (var vol in UnityEngine.Object.FindObjectsOfType<UnityEngine.Rendering.PostProcessing.PostProcessVolume>())
                {
                    if (vol == null) continue;
                    var p = vol.HasInstantiatedProfile() ? vol.profile : vol.sharedProfile;
                    UnityEngine.Rendering.PostProcessing.Bloom b;
                    if (p == null || !p.TryGetSettings(out b) || b == null) continue;
                    parts.Add((b.active ? "on " : "off ") + b.intensity.value.ToString("0.###", CultureInfo.InvariantCulture));
                }
            }
            catch (Exception e) { return "(unreadable: " + e.GetType().Name + ")"; }
            return string.Join(" | ", parts.ToArray());
        }

        /// <summary>MEDIUM-3 / design T5-f: a segmented click on SMenuMus,
        /// SBloom, SShake and SHpPrec leaves the canonical id in the .cfg on
        /// disk, and the live effect has run: the music engine's mode follows
        /// SMenuMus in the click's own call stack, and the live bloom changes
        /// with SBloom. SShake and SHpPrec have no apply step (the level is
        /// read where it is used), so their .cfg line is their assertion.
        /// Each row is put back.</summary>
        private static IEnumerator DriveT5f()
        {
            foreach (var key in new[] { "SMenuMus", "SBloom", "SShake", "SHpPrec" })
            {
                var r = DrvRec(key);
                if (r == null || r.Kind != SettingsKind.Segmented) { DrvBad("T5-f the " + key + " row was not built as segmented"); continue; }
                SettingsSwitchSubTab(r.Tab);
                yield return 0.4f;
                string orig = DrvValue(r);
                string target = key == "SMenuMus" ? (orig == "silent" ? "vanilla" : "silent") : DrvAway(r, orig);
                var cfg = DrvCfgEntry(key);
                string bloom0 = key == "SBloom" ? DrvBloomState() : null;
                var mode0 = MusicEngine.Mode;
                bool clicked = DrvSetValue(r, target);
                var mode = MusicEngine.Mode;
                yield return 0.5f;
                string disk = DrvCfgOnDisk(cfg);
                string tag = "T5-f " + key + " " + orig + " -> " + target + ": ";
                if (clicked && disk == target) DrvOk(tag + "the .cfg on disk holds '" + disk + "', the canonical id");
                else DrvBad(tag + "the .cfg on disk holds '" + disk + "', want the canonical id '" + target + "'" + (clicked ? "" : " (the click did not land)"));
                if (key == "SMenuMus")
                {
                    var wantMode = target == "silent" ? MusicEngine.MusicMode.MutedByChoice : MusicEngine.MusicMode.Vanilla;
                    if (mode == wantMode) DrvOk(tag + "the music engine's mode is " + mode + " in the click's own call stack (was " + mode0 + ")");
                    else DrvBad(tag + "the music engine's mode is " + mode + " in the click's own call stack (was " + mode0 + "), want " + wantMode);
                }
                else if (key == "SBloom")
                {
                    string bloom1 = DrvBloomState();
                    if (string.IsNullOrEmpty(bloom0)) DrvNote(tag + "no volume in this scene carries a Bloom, so the live half is not observable here");
                    else if (bloom1 != bloom0) DrvOk(tag + "the live bloom changed: " + bloom0 + " -> " + bloom1);
                    else DrvBad(tag + "the live bloom did not change: " + bloom0);
                }
                else DrvNote(tag + "no apply step; the level is read where it is used");
                DrvSetValue(DrvRec(key), orig);
                yield return 0.5f;
                string back = DrvCfgOnDisk(cfg);
                if (back == orig) DrvNote(tag + "put back ('" + back + "' on disk)");
                else DrvBad(tag + "not put back: the .cfg holds '" + back + "', want '" + orig + "'");
            }
        }

        // --- T5-g: reset scope, per tab, the effect half ------------------

        /// <summary>Design section 6.4's per-tab reset sets on the LANE tree,
        /// stated here rather than read from the descriptors the reset uses.</summary>
        private static readonly Dictionary<string, string[]> DrvLaneResetSets = new Dictionary<string, string[]>
        {
            { "ingame", new[] { "SBlkDbg", "SHpPrec", "SInpOv", "SLagNotice", "SPing" } },
            { "chatmail", new[] { "SChatTtl", "SIgChat", "SNT" } },
            { "sound", new[] { "SMenuMus", "SMusCredit", "SMuteBg" } },
            { "visuals", new[] { "SAnimCos", "SBloom", "SChromAb", "SCursor", "SLight", "SPColor", "SShad", "SShake", "STrail" } },
            { "perf", new[] { "SDeepIdle", "SFPS", "SFPSCap", "SPerf_BulletCap", "SPerf_EdgeBn", "SPerf_HitSnd", "SPerf_Master",
                              "SPerf_Menu", "SPerf_OOB", "SPerf_PoolInit", "SPerf_Stun" } },
            { "langmenus", new[] { "SHeavyFont", "SInactiveLb" } },
            { "privacy", new string[0] },
        };

        /// <summary>Rows T5-g does not set by hand, and why: a server row with
        /// no test stub would send a request; the relay needs a linked Discord
        /// (T5-e covers its refusal); the consent switch changes what the mod
        /// reports; the card preset's refresh re-renders the card portrait.</summary>
        private static readonly string[] DrvHandSetSkip =
            { "SPrefSC", "SAllowSpec", "SAppOff", "SPcAnn", "SPcPub", "SShowDc", "SMailRelay", "SCT", "SPcPre" };

        private static readonly string[] DrvPerfIds = { "Stun", "OOB", "HitSnd", "EdgeBn", "Menu", "BulletCap", "PoolInit" };

        private static BepInEx.Configuration.ConfigEntry<bool> DrvPerfEntry(string id)
        {
            switch (id)
            {
                case "Stun": return Plugin.PerfStunPlayerNullGuard;
                case "OOB": return Plugin.PerfDespawnOffscreenBullets;
                case "HitSnd": return Plugin.PerfSwallowHitSoundNREs;
                case "EdgeBn": return Plugin.PerfSwallowEdgeBounceNREs;
                case "Menu": return Plugin.PerfSkipMenuUpdateInMatch;
                case "BulletCap": return Plugin.PerfBulletHitParticleCap;
                case "PoolInit": return Plugin.PerfClampObjectPoolInit;
            }
            return null;
        }

        /// <summary>The mail status T5-g saw when it last set SMailFrom by
        /// hand. The status poll (MailClient.DoPoll, every 60 s) stores the
        /// server's mail_from; while a test runs the PUT reaches a stub, so
        /// the server keeps the value as found and a poll puts it back.</summary>
        private static object mailSetLast;

        /// <summary>Whether a mail status poll has answered since `seen` was
        /// read: each answer is a new MailClient.Last.</summary>
        private static bool DrvMailPolledSince(object seen)
        {
            return !ReferenceEquals(MailClient.Last, seen);
        }

        /// <summary>Why a control is not active in the hierarchy: no control,
        /// a destroyed one, its own flag, or the nearest inactive parent.</summary>
        private static string DrvWhyHidden(GameObject go)
        {
            if ((object)go == null) return "no control";
            if (go == null) return "the control was destroyed";
            if (!go.activeSelf) return "the control itself is inactive";
            var t = go.transform.parent;
            while (t != null)
            {
                if (!t.gameObject.activeSelf) return "parent " + t.gameObject.name + " is inactive";
                t = t.parent;
            }
            return "active in the hierarchy";
        }

        /// <summary>Set a row through its own control and wait out whatever
        /// the write started (a page rebuild, a stubbed PUT).</summary>
        private static IEnumerator DrvSetAndSettle(string key, string v, List<string> failed)
        {
            var r = DrvRec(key);
            if (r == null || DrvValue(r) == v) yield break;
            SettingsSwitchSubTab(r.Tab);
            if (!DrvSetValue(r, v)) { failed.Add(key); yield break; }
            yield return 0.35f;
            if (key == "SLang") yield return DrvSettle(2.5f);
            else if (key == "SHeavyFont") yield return DrvSettle(1.0f);
            else if (key == "SMailFrom") yield return 2.0f;
        }

        /// <summary>MEDIUM-3 / design T5-g, the effect half on the built
        /// client. Every row that can be is first set away from its
        /// recommendation through its own control. Then, tab by tab, the
        /// footer's Reset and Confirm are clicked and the rows whose value
        /// changed are read back: the changed set must be exactly the tab's
        /// set in design 6.4 (lane tree, stated above), each changed row must
        /// hold its reset operand, and the tab's live effect must have run -
        /// the chat-mute publish in Confirm's own call stack (Chat and mail),
        /// the music engine's mode in it (Sound), the live bloom (Visuals),
        /// each performance patch's gate (Performance), the page rebuilt with
        /// the heavy font (Language and menus); Privacy's reset writes nothing.
        /// Every row and the page's PlayerPrefs are put back afterwards.</summary>
        private static IEnumerator DriveT5g()
        {
            yield return DrvSettle(0.6f);
            var prefs0 = DrvPrefState();
            var orig = DrvSnapshot();
            var order = new List<string>();
            foreach (var d in SettingsDescriptors.All)
                if (orig.ContainsKey(d.Key) && d.Key != "SLang" && d.Key != "SHeavyFont") order.Add(d.Key);
            order.Add("SLang");
            order.Add("SHeavyFont");
            var handSet = new List<string>();
            var skipped = new List<string>();
            var failed = new List<string>();
            foreach (var key in order)
            {
                if (!orig.ContainsKey(key)) continue;
                if (Array.IndexOf(DrvHandSetSkip, key) >= 0) { skipped.Add(key); continue; }
                string rec = DrvOperand(SettingsDescriptorWriters.RecommendedOperand(key));
                string away = rec != null ? DrvAway(DrvRec(key), rec) : null;
                if (away == null) { skipped.Add(key); continue; }
                yield return DrvSetAndSettle(key, away, failed);
                if (key == "SMailFrom") mailSetLast = MailClient.Last;
                handSet.Add(key);
            }
            yield return DrvSettle(1.0f);
            var cur = DrvSnapshot();
            var notAway = new List<string>();
            foreach (var key in handSet)
            {
                string v;
                if (!cur.TryGetValue(key, out v) || v == DrvOperand(SettingsDescriptorWriters.RecommendedOperand(key))) notAway.Add(key);
            }
            if (notAway.Contains("SMailFrom") && DrvMailPolledSince(mailSetLast))
            {
                notAway.Remove("SMailFrom");
                DrvNote("T5-g SMailFrom went back to the server's value with a mail status poll that answered after it was set"
                    + " (its PUT reached the stub, so the server still holds the value as found); it is set again before its tab's reset");
            }
            if (notAway.Count == 0 && failed.Count == 0)
                DrvNote("T5-g " + handSet.Count + " rows set away from their recommendation; not set by hand: " + DrvList(skipped));
            else DrvBad("T5-g rows not away from their recommendation: " + DrvList(notAway) + "; set failed: " + DrvList(failed));

            int sum = 0;
            for (int tab = 0; tab < SETTINGS_TABS; tab++)
            {
                string home = SettingsModel.SubTabHomes[tab];
                string tag = "T5-g " + home + ": ";
                string[] wantSet;
                if (!DrvLaneResetSets.TryGetValue(home, out wantSet)) { DrvBad(tag + "no stated set for this sub-tab"); continue; }
                yield return DrvOpenSettings();
                yield return DrvSettle(1.0f);
                SettingsSwitchSubTab(tab);
                yield return 0.4f;
                var drift = new List<string>();
                foreach (var key in handSet)
                {
                    var hr = DrvRec(key);
                    if (hr != null && hr.Tab == tab && DrvValue(hr) == DrvOperand(SettingsDescriptorWriters.RecommendedOperand(key))) drift.Add(key);
                }
                if (drift.Contains("SMailFrom") && DrvMailPolledSince(mailSetLast))
                {
                    drift.Remove("SMailFrom");
                    yield return DrvSetAndSettle("SMailFrom", DrvAway(DrvRec("SMailFrom"), "everyone"), failed);
                    mailSetLast = MailClient.Last;
                    var mr = DrvRec("SMailFrom");
                    if (mr != null && DrvValue(mr) != "everyone") DrvNote(tag + "SMailFrom set again before the reset ('" + DrvValue(mr) + "'): a mail status poll had put back the server's value");
                    else drift.Add("SMailFrom");
                    yield return DrvOpenSettings();
                    yield return DrvSettle(1.0f);
                    SettingsSwitchSubTab(tab);
                    yield return 0.4f;
                }
                if (drift.Count > 0) DrvBad(tag + "rows set by hand are back at their recommendation before the reset: " + DrvList(drift));
                object mail0 = MailClient.Last;
                int put0 = settingsPutStubCalls;
                var before = DrvSnapshot();
                string bloom0 = home == "visuals" ? DrvBloomState() : null;
                int g0 = settingsBuildGen;
                bool armClicked = DrvClick(setResetBtn);
                bool armed = settingsResetArmed;
                bool confirmAtArm = setResetConfirmBtn != null && setResetConfirmBtn.activeInHierarchy;
                yield return 0.3f;
                bool confirmShown = setResetConfirmBtn != null && setResetConfirmBtn.activeInHierarchy;
                string hiddenWhy = confirmShown ? null : DrvWhyHidden(setResetConfirmBtn) + "; at the arm click " + (confirmAtArm ? "shown" : "hidden")
                    + "; open " + isOpen + ", built " + pageBuilt + ", tab " + currentTab + ", sub-tab " + settingsSubTab
                    + ", armed now " + settingsResetArmed + ", builds since " + (settingsBuildGen - g0);
                // Round-3 L5: the chatmail tab's SIgChat write is read on the
                // stub seat (DriveT5d) - cr_cmute planted at the marker of the
                // mode Confirm leaves, read the moment Confirm returns.
                Photon.Realtime.Player seat = null;
                object seatPlanted = null;
                string seatWhy = home == "chatmail" ? DrvStubSeatReady() : "not this tab", seatThrew = "";
                int seatFc = 0;
                bool confirmClicked = false;
                if (home == "chatmail" && seatWhy == null)
                {
                    seatPlanted = DrvMarker(CompetitiveUI.CurrentChatOverlayMode());
                    seat = DrvStubPlayer(seatPlanted);
                    seatThrew = DrvWithStubSeat(true, seat, () => { confirmClicked = DrvClick(setResetConfirmBtn); }, out seatFc);
                }
                else confirmClicked = DrvClick(setResetConfirmBtn);
                var mode = MusicEngine.Mode;
                object seatGot = DrvCmute(seat);
                var gates = new List<string>();
                foreach (var id in DrvPerfIds) gates.Add(id + "=" + (PerfGate.Check(DrvPerfEntry(id)) ? "on" : "off"));
                yield return DrvSettle(1.0f);
                var after = DrvSnapshot();
                var written = DrvChanged(before, after);
                int puts = settingsPutStubCalls - put0;
                if (written.Contains("SMailFrom") && puts == 0 && DrvMailPolledSince(mail0))
                {
                    written.Remove("SMailFrom");
                    DrvNote(tag + "SMailFrom moved with a mail status poll that answered inside the window, and no mail PUT was made:"
                        + " the server's value, not a write by the reset");
                }
                else if (puts > 0) DrvNote(tag + "the reset made " + puts + " mail PUT(s)");
                var want = new List<string>(wantSet);
                want.Sort(StringComparer.Ordinal);
                sum += written.Count;
                if (home == "privacy")
                {
                    if (!armed && !confirmShown && written.Count == 0)
                        DrvOk(tag + "Reset does not arm on Privacy (no Confirm shown) and 0 rows changed");
                    else DrvBad(tag + "Reset armed " + armed + ", Confirm " + (confirmShown ? "shown" : "hidden") + ", changed " + DrvList(written) + ", want none");
                    continue;
                }
                if (!armClicked || !armed || !confirmClicked || !confirmShown)
                {
                    DrvBad(tag + "the footer did not arm and confirm (Reset clicked " + armClicked + ", armed " + armed
                        + ", Confirm shown " + confirmShown + ", clicked " + confirmClicked + ")"
                        + (hiddenWhy != null ? "; Confirm hidden: " + hiddenWhy : ""));
                    continue;
                }
                if (string.Join(",", written.ToArray()) == string.Join(",", want.ToArray()))
                    DrvOk(tag + "the changed set is exactly the tab's " + want.Count + ": " + DrvList(written));
                else
                    DrvBad(tag + "changed " + DrvList(written) + ", want exactly " + DrvList(want));
                var wrongValue = new List<string>();
                foreach (var key in written)
                {
                    string op = DrvOperand(SettingsDescriptorWriters.RecommendedOperand(key));
                    string v;
                    if (op == null || !after.TryGetValue(key, out v) || v != op)
                        wrongValue.Add(key + "=" + (after.ContainsKey(key) ? after[key] : "?") + " (operand " + (op ?? "none") + ")");
                }
                if (wrongValue.Count == 0) DrvOk(tag + "every changed row holds its reset operand");
                else DrvBad(tag + "rows not at their operand: " + DrvList(wrongValue));
                switch (home)
                {
                    case "chatmail":
                        if (seatWhy != null) DrvBad(tag + "no stub seat for the cr_cmute read: " + seatWhy);
                        else if (!(seatPlanted is int) || (int)seatPlanted != 1)
                            DrvBad(tag + "the chat mode before Confirm carried marker " + DrvShow(seatPlanted) + ", want 1 (Muted, set by hand above), so the read cannot show a publish");
                        else if (seatThrew.Length > 0) DrvBad(tag + "Confirm THREW " + seatThrew + " with the stub seat in place");
                        else if (seatGot is int && (int)seatGot == 0)
                            DrvOk(tag + "the SIgChat write published cr_cmute 0 in Confirm's own call stack: the stub seat's property 1 -> 0");
                        else DrvBad(tag + "the stub seat's cr_cmute when Confirm returned is " + DrvShow(seatGot) + ", want 0 (planted 1)");
                        break;
                    case "sound":
                        if (mode == MusicEngine.MusicMode.Vanilla) DrvOk(tag + "the music engine is in " + mode + " in Confirm's own call stack (SMenuMus vanilla)");
                        else DrvBad(tag + "the music engine is in " + mode + " in Confirm's call stack, want Vanilla (SMenuMus vanilla)");
                        break;
                    case "visuals":
                        string bloom1 = DrvBloomState();
                        if (string.IsNullOrEmpty(bloom0)) DrvNote(tag + "no volume in this scene carries a Bloom; the live bloom is not observable here");
                        else if (bloom1 != bloom0) DrvOk(tag + "the live bloom was re-applied: " + bloom0 + " -> " + bloom1);
                        else DrvBad(tag + "the live bloom did not change: " + bloom0);
                        break;
                    case "perf":
                        bool gatesOk = true;
                        foreach (var g in gates)
                        {
                            string id = g.Substring(0, g.IndexOf('='));
                            if (g != id + (id == "OOB" ? "=off" : "=on")) gatesOk = false;
                        }
                        if (gatesOk) DrvOk(tag + "each patch's live gate after Confirm: " + DrvList(gates) + " (the master on, OOB off, the rest on)");
                        else DrvBad(tag + "patch gates after Confirm " + DrvList(gates) + "; want the master on, OOB off, the rest on");
                        break;
                    case "langmenus":
                        int rebuilds = settingsBuildGen - g0;
                        string font = after.ContainsKey("SHeavyFont") ? after["SHeavyFont"] : "?";
                        if (rebuilds >= 1 && font == "True") DrvOk(tag + "the heavy font is on and the page was rebuilt after the reset (" + rebuilds + " build(s))");
                        else DrvBad(tag + "heavy font " + font + ", " + rebuilds + " rebuild(s) after the reset");
                        break;
                }
            }
            DrvNote("T5-g rows changed across the seven resets: " + sum + " (the sum of the seven sets, for information only)");

            // Put every row back, the two rebuilding rows last.
            yield return DrvOpenSettings();
            yield return DrvSettle(0.6f);
            var back = new List<string>();
            foreach (var key in handSet) if (key != "SLang" && key != "SHeavyFont") back.Add(key);
            if (handSet.Contains("SLang")) back.Add("SLang");
            if (handSet.Contains("SHeavyFont")) back.Add("SHeavyFont");
            var failedBack = new List<string>();
            foreach (var key in back) yield return DrvSetAndSettle(key, orig[key], failedBack);
            yield return DrvSettle(1.0f);
            var fin = DrvSnapshot();
            var notBack = new List<string>();
            foreach (var key in handSet) { string v; if (!fin.TryGetValue(key, out v) || v != orig[key]) notBack.Add(key); }
            if (notBack.Count == 0) DrvNote("T5-g all " + handSet.Count + " rows set by hand are back at their values as found");
            else DrvBad("T5-g rows not put back: " + DrvList(notBack));
            DrvPrefRestore(prefs0, "T5-g");
        }

        // --- T5-h: mechanics unchanged ------------------------------------

        private static int DrvPerfRows(out int active)
        {
            int n = 0;
            active = 0;
            foreach (var kv in settingsByKey)
            {
                if (!kv.Key.StartsWith("SPerf_", StringComparison.Ordinal) || kv.Value.Row == null) continue;
                n++;
                if (kv.Value.Row.activeInHierarchy) active++;
            }
            return n;
        }

        /// <summary>MEDIUM-3 / design T5-h, four mechanics: the Performance
        /// disclosure collapses and re-expands its eight rows; one SDBtn click
        /// hides SDBtn and shows SDCBtn and SDXBtn; the delete row is the last
        /// child of the Privacy body and its two buttons keep their two reds;
        /// one drag of SChatTtl from stop 0 to stop 5, driven through the
        /// slider component's own value one frame at a time, calls the row's
        /// writer (Plugin.SetChatOverlaySeconds, the one writer of
        /// UI/ChatOverlaySeconds) at most six times, each storing a
        /// CHAT_TTL_CYCLE value. Everything is put back.</summary>
        private static IEnumerator DriveT5h()
        {
            // (1) the disclosure
            var ph = DrvRec("SPerfH");
            if (ph == null || ph.Glyph == null) { DrvBad("T5-h the SPerfH row was not built"); yield break; }
            SettingsSwitchSubTab(ph.Tab);
            yield return 0.4f;
            bool open0 = _perfSectionOpen;
            if (!_perfSectionOpen) { DrvClick(DrvRec("SPerfH").Glyph); yield return 0.4f; }
            int a0, a1, a2;
            int n = DrvPerfRows(out a0);
            DrvClick(DrvRec("SPerfH").Glyph);
            yield return 0.4f;
            DrvPerfRows(out a1);
            DrvClick(DrvRec("SPerfH").Glyph);
            yield return 0.4f;
            DrvPerfRows(out a2);
            if (n == 8 && a0 == 8 && a1 == 0 && a2 == 8)
                DrvOk("T5-h two SPerfH clicks: 8 of 8 SPerf_* rows active -> 0 -> 8");
            else DrvBad("T5-h two SPerfH clicks: " + n + " SPerf_* rows, active " + a0 + " -> " + a1 + " -> " + a2 + " (want 8 -> 0 -> 8)");
            if (_perfSectionOpen != open0) { DrvClick(DrvRec("SPerfH").Glyph); yield return 0.4f; }

            // (2) SDBtn hides itself and shows SDCBtn + SDXBtn
            SettingsSwitchSubTab(SettingsModel.SubTabIndex("privacy"));
            DrvDisarm();
            yield return 0.6f;
            bool clicked = DrvClick(deleteBtn);
            yield return 0.6f;
            bool dA = deleteBtn != null && deleteBtn.activeSelf, cA = confirmDeleteBtn != null && confirmDeleteBtn.activeSelf,
                 xA = cancelDelBtn != null && cancelDelBtn.activeSelf;
            if (clicked && deleteArmed && !dA && cA && xA) DrvOk("T5-h one SDBtn click: SDBtn hidden, SDCBtn and SDXBtn shown");
            else DrvBad("T5-h one SDBtn click: armed " + deleteArmed + ", SDBtn " + (dA ? "shown" : "hidden") + ", SDCBtn "
                + (cA ? "shown" : "hidden") + ", SDXBtn " + (xA ? "shown" : "hidden") + " (want hidden, shown, shown)");
            DrvDisarm();
            yield return 0.6f;

            // (3) the delete row is last on Privacy, in its two reds
            var sdr = DrvRec("SDR");
            Transform tr = sdr != null && sdr.Row != null ? sdr.Row.transform : null;
            string parent = tr != null && tr.parent != null ? tr.parent.name : "?";
            int idx = tr != null ? tr.GetSiblingIndex() : -1, last = tr != null && tr.parent != null ? tr.parent.childCount - 1 : -2;
            Color dc = UIFactory.GetImageColor(deleteBtn), cc = UIFactory.GetImageColor(confirmDeleteBtn);
            Color wantD = new Color(0.45f, 0.18f, 0.18f, 0.9f), wantC = new Color(0.7f, 0.15f, 0.15f, 0.95f);
            string seen = "SDR is child " + idx + " of " + (last + 1) + " under " + parent + "; SDBtn " + DrvColor(dc) + ", SDCBtn " + DrvColor(cc);
            if (parent == "SubPrivacy" && idx == last && DrvSameColor(dc, wantD) && DrvSameColor(cc, wantC)) DrvOk("T5-h " + seen);
            else DrvBad("T5-h " + seen + " (want the last child of SubPrivacy, " + DrvColor(wantD) + " and " + DrvColor(wantC) + ")");

            // (4) one slider drag, stop 0 -> stop 5
            var sl = DrvRec("SChatTtl");
            Component slider = null;
            if (sl != null && sl.Slider != null && sl.Slider.go != null)
                foreach (var c in sl.Slider.go.GetComponents<Component>())
                    if (c != null && c.GetType().FullName == "UnityEngine.UI.Slider") slider = c;
            var pVal = slider != null ? slider.GetType().GetProperty("value") : null;
            if (sl == null || pVal == null || sl.Stops == null || sl.Stops.Length != 6) { DrvBad("T5-h the SChatTtl slider was not built as six stops"); yield break; }
            SettingsSwitchSubTab(sl.Tab);
            yield return 0.4f;
            int idx0 = Mathf.Clamp(sl.Index(), 0, sl.Stops.Length - 1);
            SettingsSetSliderIndex(sl, 0);
            yield return 0.3f;
            var set0 = sl.SetStop;
            int writes = 0;
            var stored = new List<string>();
            var outside = new List<string>();
            sl.SetStop = x =>
            {
                writes++;
                if (set0 != null) set0(x);
                float s = Plugin.ChatOverlaySeconds != null ? Plugin.ChatOverlaySeconds.Value : -1f;
                stored.Add(DrvNum(s));
                if (Array.IndexOf(Plugin.CHAT_TTL_CYCLE, s) < 0) outside.Add(DrvNum(s));
            };
            const int frames = 40;
            try
            {
                for (int fr = 1; fr <= frames; fr++)
                {
                    pVal.SetValue(slider, fr / (float)frames, null);
                    yield return 0f;
                }
            }
            finally { sl.SetStop = set0; }
            int end = Mathf.Clamp(sl.Index(), 0, sl.Stops.Length - 1);
            if (writes <= 6 && outside.Count == 0 && end == 5)
                DrvOk("T5-h one drag of SChatTtl from stop 0 to stop 5 over " + frames + " frames: " + writes + " writer call(s), stored "
                    + DrvList(stored) + ", each a CHAT_TTL_CYCLE value");
            else DrvBad("T5-h one drag of SChatTtl over " + frames + " frames: " + writes + " writer call(s) (want at most 6), outside the cycle "
                + DrvList(outside) + ", ended at stop " + end + " (want 5)");
            SettingsSetSliderIndex(DrvRec("SChatTtl"), idx0);
            yield return 0.3f;
        }

        // --- T7: the exact stored targets ----------------------------------

        /// <summary>MEDIUM-3 / design T7 (a) and (c): after choosing Arrow in
        /// SCursor, cr_cursor_shape reads exactly "arrow" (Shapes[1]); after
        /// choosing Nobody in SMailFrom (its PUT answered by the stub),
        /// CR_Mail_From_&lt;steamid&gt; reads exactly "nobody". An exact
        /// target, never "changed": the mail case starts from "played", stored
        /// directly, so a write that changed the value to anything else would
        /// pass a changed-check and still fail here. Both prefs are put back
        /// exactly.</summary>
        private static IEnumerator DriveT7()
        {
            var prefs0 = DrvPrefState();
            var cr = DrvRec("SCursor");
            if (cr == null) { DrvBad("T7 the SCursor row was not built"); yield break; }
            SettingsSwitchSubTab(cr.Tab);
            yield return 0.4f;
            if (DrvValue(cr) == "arrow") { DrvSetValue(cr, "dot"); yield return 0.4f; }
            string p0 = DrvPrefRead("cr_cursor_shape");
            bool picked = DrvSetValue(DrvRec("SCursor"), "arrow");
            string pref = DrvPrefRead("cr_cursor_shape");
            if (picked && pref == "arrow") DrvOk("T7-a SCursor -> Arrow: cr_cursor_shape reads 'arrow' exactly (Shapes[1])");
            else DrvBad("T7-a SCursor -> Arrow: cr_cursor_shape reads " + (pref == null ? "nothing" : "'" + pref + "'") + ", want exactly 'arrow'"
                + (pref != p0 ? " - a changed-check would have passed" : ""));
            yield return 0.4f;

            var mf = DrvRec("SMailFrom");
            if (mf == null) { DrvBad("T7 the SMailFrom row was not built"); DrvPrefRestore(prefs0, "T7"); yield break; }
            SettingsSwitchSubTab(mf.Tab);
            yield return 0.4f;
            MailClient.MailFrom = "played";
            dirty = true;
            yield return 0.4f;
            bool p2 = DrvSetValue(DrvRec("SMailFrom"), "nobody");
            yield return 2.2f;
            string mpref = DrvPrefRead(MailClient.PrefKey("From"));
            if (p2 && mpref == "nobody")
                DrvOk("T7-c SMailFrom played -> Nobody, its PUT answered by the stub: CR_Mail_From_<steamid> reads 'nobody' exactly, a member of MAIL_FROM_VALUES");
            else DrvBad("T7-c SMailFrom played -> Nobody: CR_Mail_From_<steamid> reads " + (mpref == null ? "nothing" : "'" + mpref + "'")
                + ", want exactly 'nobody'" + (mpref != "played" ? " - a changed-check would have passed" : ""));
            DrvPrefRestore(prefs0, "T7");
            dirty = true;
        }

        /// <summary>Design T7 (b), the first launch. The previous value must
        /// exist: a missing Save() leaves a stored key stale, never absent,
        /// so when the pref holds no shape id this launch first stores 'dot'
        /// with a saved write, as on a seat that had set a cursor shape. Then
        /// the SCursor row picks another shape, and the runner ends the
        /// process with no graceful quit. The second launch
        /// ("t7r-&lt;picked&gt;-&lt;previous&gt;-&lt;found&gt;") reads the
        /// pref the killed process left and puts back what this launch
        /// found.</summary>
        private static IEnumerator DriveT7b()
        {
            var cr = DrvRec("SCursor");
            if (cr == null) { DrvBad("T7-b the SCursor row was not built"); yield break; }
            SettingsSwitchSubTab(cr.Tab);
            yield return 0.4f;
            string found = DrvPrefRead("cr_cursor_shape");
            string prev = found;
            if (prev == null || Array.IndexOf(CursorColorCosmetic.Shapes, prev) < 0)
            {
                prev = "dot";
                PlayerPrefs.SetString("cr_cursor_shape", prev);
                PlayerPrefs.Save();
                DrvNote("T7-b the pref held " + (found == null ? "nothing" : "'" + found + "'")
                    + "; 'dot' is stored first with a saved write, as on a seat that had set a cursor shape");
            }
            string target = prev == "arrow" ? "crosshair" : "arrow";
            bool picked = DrvSetValue(cr, target);
            DrvNote("T7-b the previous value is '" + prev + "'; the SCursor row picked '" + target + "' ("
                + (picked ? "written" : "NOT written") + "); the runner ends the process next, with no graceful quit;"
                + " read it back with t7r-" + target + "-" + prev + "-" + (found ?? "absent"));
        }

        /// <summary>Design T7 (b), the second launch: the pref the killed
        /// process left must hold exactly the picked shape; a pick that was
        /// never saved leaves exactly the previous value. Then what the first
        /// launch found is put back ("absent": not stored).</summary>
        private static IEnumerator DriveT7r(string arg)
        {
            var parts = arg.Split('-');
            string want = parts[0], prev = parts.Length > 1 ? parts[1] : "", found = parts.Length > 2 ? parts[2] : "";
            string now = DrvPrefRead("cr_cursor_shape");
            string seen = now == null ? "nothing" : "'" + now + "'";
            if (now == want) DrvOk("T7-b read-back after the hard kill: cr_cursor_shape holds exactly '" + want + "', the shape picked before it");
            else DrvBad("T7-b read-back after the hard kill: cr_cursor_shape holds " + seen + ", want exactly '" + want + "'"
                + (now == prev ? " - exactly the previous value '" + prev + "': the pick was never saved" : ""));
            if (found == "absent") { if (now != null) PlayerPrefs.DeleteKey("cr_cursor_shape"); }
            else if (found.Length > 0 && now != found)
            {
                var cr = DrvRec("SCursor");
                if (cr != null) { SettingsSwitchSubTab(cr.Tab); yield return 0.4f; DrvSetValue(DrvRec("SCursor"), found); }
                if (DrvPrefRead("cr_cursor_shape") != found) PlayerPrefs.SetString("cr_cursor_shape", found);
            }
            try { PlayerPrefs.Save(); } catch { }
            yield return 0.3f;
            string after = DrvPrefRead("cr_cursor_shape");
            DrvNote("T7-b put back: cr_cursor_shape holds " + (after == null ? "nothing" : "'" + after + "'"));
        }

        /// <summary>Round-2 LOW-6 (design section 8 item 4): the session of
        /// the live config byte-compare - open the settings page, open every
        /// sub-tab through its own button, then close the page. Only the
        /// sub-tab buttons are clicked (the remembered sub-tab is a field in
        /// memory); the runner compares the config files this session leaves
        /// with the ones the build before item 13 left.</summary>
        private static IEnumerator DriveL6()
        {
            yield return DrvOpenSettings();
            yield return DrvSettle(0.6f);
            for (int t = 0; t < SETTINGS_TABS; t++)
            {
                if (settingsSubBtns[t] == null || !DrvClick(settingsSubBtns[t])) { DrvBad("L6 sub-tab " + t + " could not be clicked"); continue; }
                yield return 0.8f;
                if (settingsSubTab == t) DrvOk("L6 opened sub-tab " + t + " (" + SettingsModel.SubTabHomes[t] + ") through its button");
                else DrvBad("L6 the click on sub-tab " + t + " left sub-tab " + settingsSubTab + " open");
            }
            Close();
            yield return 1f;
            if (!isOpen) DrvOk("L6 the page is closed");
            else DrvBad("L6 the page is still open");
        }

        private const string DrvProbeKey = "cr_item13_ppwt";

        /// <summary>Design T7 (b)'s premise, probed: one PlayerPrefs write
        /// with no Save(), then this process ends in the same frame, so no
        /// other code runs between the write and the end. "ppwr", in the next
        /// launch, reads the key back and removes it. The note goes out 3 s
        /// before the write: the log file is flushed on a timer, and a line
        /// written in the frame of the end never reaches it.</summary>
        private static IEnumerator DrivePpwt()
        {
            if (PlayerPrefs.HasKey(DrvProbeKey)) { PlayerPrefs.DeleteKey(DrvProbeKey); PlayerPrefs.Save(); yield return 0.5f; }
            DrvNote("PPWT " + DrvProbeKey + " is " + (PlayerPrefs.HasKey(DrvProbeKey) ? "STILL stored" : "not stored")
                + "; in 3 s this writes 'unsaved' with no Save() and ends this process in the same frame");
            yield return 3f;
            PlayerPrefs.SetString(DrvProbeKey, "unsaved");
            System.Diagnostics.Process.GetCurrentProcess().Kill();
        }

        private static IEnumerator DrivePpwr()
        {
            string v = DrvPrefRead(DrvProbeKey);
            DrvNote("PPWR after the same-frame end: " + DrvProbeKey + " "
                + (v == null ? "is not stored: the unsaved write was lost" : "holds '" + v + "': the write reached the store with no Save()"));
            PlayerPrefs.DeleteKey(DrvProbeKey);
            PlayerPrefs.Save();
            yield return 0.3f;
            DrvNote("PPWR removed " + DrvProbeKey + ": " + (PlayerPrefs.HasKey(DrvProbeKey) ? "STILL stored" : "not stored"));
        }

        // --- Witness captures (design section 11; round-2 brief section 5) ---
        //
        // Named-only scenarios. A capture is a CAPTURE line naming the screen
        // size; the runner takes it with the pinned screenshot runner and crops
        // it to the game's client area. The driven pointer is parked off the
        // list for the whole scenario, so wherever the real cursor rests it
        // cannot pick the row the pane shows (the pane follows the pinned row,
        // then the hovered row, then the focused row). Every scenario puts back
        // what it moved: the resolution with the game's resolution prefs read
        // back, the language with the cfg and PlayerPrefs hashed before and
        // after, a stepped value through its own row.

        private static readonly string[] DrvLocales = { "es", "ru", "uk", "sv" };
        private static string drvScreenPrefs0 = "";
        private static bool drvForceRows;

        /// <summary>The driven pointer: while set, the page's hover poll reads
        /// this screen point in place of Input.mousePosition.</summary>
        private static bool settingsDriveMouseSet;
        private static Vector2 settingsDriveMouse;

        /// <summary>W3b, W3c, W10: the three optional rows under the title
        /// (server status, standing alert, tournament game) held active in
        /// place of their refreshers (RefreshCurrentTab), with witness text;
        /// nothing is fetched for them meanwhile.</summary>
        internal static bool SettingsWitnessRows => drvForceRows && SettingsDriveRunning;

        internal static void SettingsWitnessShowRows()
        {
            if (srvStatusRow != null)
            {
                UIFactory.SetTextRaw(txtServerStatus, "<color=#FF8866>* Server reconnecting... (witness row)</color>");
                srvStatusRow.SetActive(true);
            }
            if (alertBannerRow != null)
            {
                UIFactory.SetTextRaw(txtAlertBanner, "<color=#FF6055>* [OUTAGE] Witness alert row: a standing alert as long as the banner line carries  <color=#8899AA>- Admin 09-26 12:00 UTC</color></color>");
                alertBannerRow.SetActive(true);
            }
            if (tournamentIndRow != null)
            {
                UIFactory.SetTextRaw(txtTournamentGame, "<color=#FFD94D>* SWISS TOURNAMENT GAME - vs opponent  (results auto-recorded)</color>");
                tournamentIndRow.SetActive(true);
            }
        }

        private static string DrvRowsState()
        {
            return "SrvRow " + (srvStatusRow != null && srvStatusRow.activeSelf ? "active" : "inactive")
                + ", AlertRow " + (alertBannerRow != null && alertBannerRow.activeSelf ? "active" : "inactive")
                + ", TournIndRow " + (tournamentIndRow != null && tournamentIndRow.activeSelf ? "active" : "inactive");
        }

        private static IEnumerator DrvForceRows(bool on)
        {
            drvForceRows = on;
            if (on) SettingsWitnessShowRows();
            dirty = true;
            yield return DrvSettle(0.5f);
            SettingsForceLayout();
            SettingsUpdateHint();
            SettingsForceLayout();
            DrvNote((on ? "the three optional rows held active: " : "the optional rows back to their own refreshers: ") + DrvRowsState());
        }

        private static void DrvParkPointer()
        {
            settingsDriveMouse = new Vector2(2f, 2f);
            settingsDriveMouseSet = true;
            settingsHoverKey = null;
            settingsPaneDirty = true;
        }

        private static void DrvPointAt(GameObject go)
        {
            if (go == null) return;
            settingsDriveMouse = SettingsWorldRect(go).center;
            settingsDriveMouseSet = true;
        }

        /// <summary>The key the pane renders: the pinned row, else the
        /// hovered row, else the focused row (SettingsRenderPane).</summary>
        private static string DrvPaneKey()
        {
            string key = settingsPinnedKey ?? settingsHoverKey;
            if (key == null) { var f = SettingsFocusedRec(); key = f != null ? f.Key : null; }
            return key;
        }

        private static string DrvScreenPrefs()
        {
            var sb = new System.Text.StringBuilder();
            foreach (var k in new[] { "Screenmanager Resolution Width", "Screenmanager Resolution Height", "Screenmanager Fullscreen mode" })
            {
                if (sb.Length > 0) sb.Append("; ");
                sb.Append(k.Substring(14)).Append('=');
                try { sb.Append(PlayerPrefs.HasKey(k) ? PlayerPrefs.GetInt(k, -1).ToString(CultureInfo.InvariantCulture) : "not stored"); }
                catch { sb.Append("?"); }
            }
            return sb.ToString();
        }

        /// <summary>Ask for a windowed resolution, wait until the game reports
        /// it (at most 8 s) and the page has settled, and say what it got.</summary>
        private static IEnumerator DrvResolution(int w, int h)
        {
            return DrvResolutionMode(w, h, FullScreenMode.Windowed);
        }

        /// <summary>DrvResolution in a named full-screen mode (round-3 L2:
        /// W3c asks 5120x1440 in every mode, because a windowed surface is
        /// capped at the desktop).</summary>
        private static IEnumerator DrvResolutionMode(int w, int h, FullScreenMode mode)
        {
            if (Screen.width != w || Screen.height != h || Screen.fullScreenMode != mode)
                Screen.SetResolution(w, h, mode);
            float until = Time.unscaledTime + 8f;
            while (Time.unscaledTime < until && (Screen.width != w || Screen.height != h || Screen.fullScreenMode != mode)) yield return 0.2f;
            yield return 1.0f;
            dirty = true;
            yield return DrvSettle(0.5f);
            SettingsForceLayout();
            SettingsUpdateHint();
            SettingsForceLayout();
            DrvNote("resolution " + w + "x" + h + (mode == FullScreenMode.Windowed ? "" : " " + mode) + " asked: " + DrvScreenState());
        }

        /// <summary>Round-3 L2: a windowed w x h, or - when the display is
        /// narrower than w - the largest surface of the SAME aspect the
        /// display holds (its width, the height scaled with it), with a line
        /// naming both. The page's canvas matches WIDTH, so that surface has
        /// the logical canvas w x h would give (810 at 21:9, 540 at 32:9):
        /// the geometry these scenarios measure. Needed because an exclusive
        /// full-screen surface, once left, puts the display back in its
        /// stored mode, which can be narrower than the desktop was. While a
        /// full-screen surface is up the display reports ITS mode, so that
        /// surface is left first (windowed 1920x1080, the restore size) and
        /// the display is read after.</summary>
        private static IEnumerator DrvResolutionAspect(int w, int h)
        {
            if (Screen.fullScreenMode != FullScreenMode.Windowed) yield return DrvResolution(1920, 1080);
            int dw = Screen.currentResolution.width, dh = Screen.currentResolution.height;
            if (dw <= 0 || dw >= w)
            {
                yield return DrvResolution(w, h);
                yield break;
            }
            int fh = (int)Math.Round((double)h * dw / w);
            DrvNote(w + "x" + h + " does not fit the " + dw + "x" + dh + " display: the same aspect is asked at " + dw + "x" + fh
                + " (the canvas matches width, so its logical canvas is the one " + w + "x" + h + " gives)");
            yield return DrvResolution(dw, fh);
        }

        /// <summary>What the game reports: its surface, the display's mode,
        /// and the page's canvas scale and logical height.</summary>
        private static string DrvScreenState()
        {
            return "Screen " + Screen.width + "x" + Screen.height + " " + Screen.fullScreenMode
                + ", display " + Screen.currentResolution.width + "x" + Screen.currentResolution.height
                + ", canvas scale " + DrvNum(SettingsCanvasScale()) + ", logical canvas height " + DrvNum(SettingsCanvasHeight());
        }

        /// <summary>The display's largest mode, how many modes it lists, and
        /// whether one of them is w x h.</summary>
        private static string DrvDisplayModes(int w, int h)
        {
            Resolution[] all;
            try { all = Screen.resolutions; } catch { all = null; }
            if (all == null || all.Length == 0) return "the display lists no modes";
            Resolution big = all[0];
            bool has = false;
            foreach (var r in all)
            {
                if ((long)r.width * r.height > (long)big.width * big.height) big = r;
                if (r.width == w && r.height == h) has = true;
            }
            return "the display lists " + all.Length + " mode(s), the largest " + big.width + "x" + big.height + "@"
                + big.refreshRateRatio.value.ToString("0.##", CultureInfo.InvariantCulture)
                + "; " + w + "x" + h + " " + (has ? "is" : "is NOT") + " among them";
        }

        /// <summary>The screen arguments this process was launched with (the
        /// -screen-*, -window-mode and -popupwindow flags only; nothing else
        /// on the command line is printed).</summary>
        private static string DrvScreenArgs()
        {
            var l = new List<string>();
            try
            {
                var a = Environment.GetCommandLineArgs();
                for (int i = 1; i < a.Length; i++)
                {
                    string s = a[i] ?? "";
                    if (s.StartsWith("-screen-", StringComparison.OrdinalIgnoreCase) || s.Equals("-window-mode", StringComparison.OrdinalIgnoreCase))
                    {
                        l.Add(s);
                        if (i + 1 < a.Length) l.Add(a[++i]);
                    }
                    else if (s.Equals("-popupwindow", StringComparison.OrdinalIgnoreCase)) l.Add(s);
                }
            }
            catch { }
            return l.Count == 0 ? "no screen arguments" : string.Join(" ", l.ToArray());
        }

        /// <summary>The restore proof: 1920x1080 windowed again, and the
        /// game's own resolution prefs reading exactly as at the start.</summary>
        private static IEnumerator DrvResolutionRestore(string tag)
        {
            yield return DrvResolution(1920, 1080);
            string prefs = DrvScreenPrefs();
            if (Screen.width == 1920 && Screen.height == 1080 && Screen.fullScreenMode == FullScreenMode.Windowed && prefs == drvScreenPrefs0)
                DrvOk(tag + " restore: Screen 1920x1080 Windowed; the game's resolution prefs read as at the start (" + prefs + ")");
            else DrvBad(tag + " restore: Screen " + Screen.width + "x" + Screen.height + " " + Screen.fullScreenMode
                + ", prefs " + prefs + " (at the start: " + drvScreenPrefs0 + ")");
        }

        /// <summary>Change the mod language through the SLang row's own
        /// dropdown, then wait for the rebuilt page.</summary>
        private static IEnumerator DrvLanguage(string loc)
        {
            string now = Plugin.ModLanguage != null ? Plugin.ModLanguage.Value : "";
            if (now == loc) yield break;
            var r = DrvRec("SLang");
            if (r == null) { DrvBad("the SLang row was not built"); yield break; }
            SettingsSwitchSubTab(r.Tab);
            yield return 0.3f;
            if (!DrvSetValue(r, loc)) { DrvBad("the SLang dropdown did not take '" + loc + "'"); yield break; }
            yield return DrvSettle(1.0f);
            DrvNote("language '" + now + "' -> '" + loc + "' through the SLang dropdown; the page reads locale " + I18n.Locale);
        }

        private static string DrvHex(byte[] data)
        {
            byte[] h;
            using (var sha = System.Security.Cryptography.SHA256.Create()) h = sha.ComputeHash(data);
            var sb = new System.Text.StringBuilder();
            for (int i = 0; i < 8; i++) sb.Append(h[i].ToString("x2", CultureInfo.InvariantCulture));
            return sb.ToString();
        }

        private static string DrvCfgHash()
        {
            try { return DrvHex(System.IO.File.ReadAllBytes(Plugin.ModLanguage.ConfigFile.ConfigFilePath)); }
            catch (Exception e) { return "unreadable (" + e.GetType().Name + ")"; }
        }

        private static byte[] DrvCfgBytes()
        {
            try { return System.IO.File.ReadAllBytes(Plugin.ModLanguage.ConfigFile.ConfigFilePath); }
            catch { return null; }
        }

        /// <summary>What the config file stores: every "[Section] Key = value"
        /// line, sorted; comments and blank lines dropped.</summary>
        private static List<string> DrvCfgEntries(byte[] raw)
        {
            var l = new List<string>();
            if (raw == null) return l;
            string sect = "";
            foreach (var line0 in System.Text.Encoding.UTF8.GetString(raw).Split('\n'))
            {
                string line = line0.Trim().TrimStart('\uFEFF');
                if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal)) continue;
                if (line.StartsWith("[", StringComparison.Ordinal) && line.EndsWith("]", StringComparison.Ordinal)) { sect = line; continue; }
                int eq = line.IndexOf('=');
                if (eq <= 0) continue;
                l.Add(sect + " " + line.Substring(0, eq).Trim() + " = " + line.Substring(eq + 1).Trim());
            }
            l.Sort(StringComparer.Ordinal);
            return l;
        }

        /// <summary>Per "[Section] Key": its place in its section and how many
        /// comment lines BepInEx wrote right before it. BepInEx writes an entry
        /// no code has bound yet (its value kept from the file) with no
        /// description, after the bound ones; a first Bind later in the run
        /// rewrites the file with that entry's description, in bound order.</summary>
        private static Dictionary<string, string> DrvCfgLayout(byte[] raw)
        {
            var d = new Dictionary<string, string>();
            if (raw == null) return d;
            string sect = "";
            int n = 0, comments = 0;
            foreach (var line0 in System.Text.Encoding.UTF8.GetString(raw).Split('\n'))
            {
                string line = line0.Trim().TrimStart('\uFEFF');
                if (line.Length == 0) continue;
                if (line.StartsWith("#", StringComparison.Ordinal)) { comments++; continue; }
                if (line.StartsWith("[", StringComparison.Ordinal) && line.EndsWith("]", StringComparison.Ordinal)) { sect = line; n = 0; comments = 0; continue; }
                int eq = line.IndexOf('=');
                if (eq <= 0) { comments = 0; continue; }
                d[sect + " " + line.Substring(0, eq).Trim()] = "#" + n + " with " + comments + " comment line(s)";
                n++;
                comments = 0;
            }
            return d;
        }

        /// <summary>"[Section] Key" of every entry bound in this process, in
        /// bind order: the config file's own entry table. BepInEx writes an
        /// entry no code has bound yet bare (its value kept from the file,
        /// no description) after the bound ones, and the first Bind of an
        /// entry saves the whole file again with that entry's description
        /// (ConfigFile.Bind calls Save when SaveOnConfigSet is set).</summary>
        private static List<string> DrvCfgBound()
        {
            var l = new List<string>();
            try
            {
                var cf = Plugin.ConfigFileForLevers;
                if (cf != null) foreach (var d in cf.Keys) l.Add("[" + d.Section + "] " + d.Key);
            }
            catch { }
            return l;
        }

        /// <summary>The config file before and after a witness run, both read
        /// IN THIS PROCESS: 0 when the bytes are identical; 1 when they differ
        /// only where an entry was first bound during the run (a lazy Bind
        /// saved the file with the entry's description: BepInEx's own write,
        /// no stored value changed); 2 for any other difference. Every
        /// difference is named (an entry by name, never its value), with the
        /// entries first bound during the run. Round-3 L3: only identical
        /// bytes are a restore. The contract is the raw byte comparison of
        /// the file AT REST - before the launch and after the process has
        /// quit - which the runner makes; a 1 here is reported to it, never
        /// passed.</summary>
        private static int DrvCfgRestored(string tag, byte[] raw0, byte[] raw1, List<string> bound0)
        {
            if (raw0 == null || raw1 == null) { DrvNote(tag + " the config file could not be read"); return 2; }
            string h0 = DrvHex(raw0), h1 = DrvHex(raw1);
            var bound1 = DrvCfgBound();
            var firstBound = new List<string>();
            var was = new HashSet<string>(bound0 ?? new List<string>(), StringComparer.Ordinal);
            foreach (var k in bound1) if (!was.Contains(k)) firstBound.Add(k);
            string binds = "entries bound in this process: " + (bound0 != null ? bound0.Count : 0) + " at the start, " + bound1.Count
                + " now; first bound during the run: " + DrvList(firstBound);
            if (h0 == h1) { DrvNote(tag + " in this process: config file byte-identical, sha256 " + h1 + "; " + binds); return 0; }
            var e0 = DrvCfgEntries(raw0);
            var e1 = DrvCfgEntries(raw1);
            var s0 = new HashSet<string>(e0);
            var s1 = new HashSet<string>(e1);
            var changed = new SortedSet<string>(StringComparer.Ordinal);
            foreach (var x in e0) if (!s1.Contains(x)) changed.Add(x.Substring(0, x.IndexOf(" = ", StringComparison.Ordinal)));
            foreach (var x in e1) if (!s0.Contains(x)) changed.Add(x.Substring(0, x.IndexOf(" = ", StringComparison.Ordinal)));
            var l0 = DrvCfgLayout(raw0);
            var l1 = DrvCfgLayout(raw1);
            var moved = new List<string>();
            var movedOther = new List<string>();
            var fb = new HashSet<string>(firstBound, StringComparer.Ordinal);
            foreach (var kv in l0)
            {
                string other;
                if (l1.TryGetValue(kv.Key, out other) && other != kv.Value && !changed.Contains(kv.Key))
                {
                    moved.Add(kv.Key + " (" + kv.Value + " -> " + other + ")");
                    if (!fb.Contains(kv.Key)) movedOther.Add(kv.Key);
                }
            }
            moved.Sort(StringComparer.Ordinal);
            string eh0 = DrvHex(System.Text.Encoding.UTF8.GetBytes(string.Join("\n", e0.ToArray())));
            string eh1 = DrvHex(System.Text.Encoding.UTF8.GetBytes(string.Join("\n", e1.ToArray())));
            DrvNote(tag + " in this process: config file bytes differ (sha256 " + h0 + " -> " + h1 + "): " + e0.Count + " -> " + e1.Count
                + " stored entries (entries sha256 " + eh0 + " -> " + eh1 + "); " + changed.Count + " stored entr" + (changed.Count == 1 ? "y" : "ies")
                + " differ" + (changed.Count > 0 ? " (" + string.Join(", ", new List<string>(changed).ToArray()) + ")" : "")
                + "; " + moved.Count + " laid out differently" + (moved.Count > 0 ? ": " + string.Join("; ", moved.ToArray()) : "")
                + "; of those, not first bound during the run: " + DrvList(movedOther) + "; " + binds);
            return changed.Count == 0 && eh0 == eh1 && moved.Count > 0 && movedOther.Count == 0 ? 1 : 2;
        }

        /// <summary>The config half of a witness restore (W2, W3), read in this
        /// process: a PASS only for identical bytes; a lazy first bind is
        /// reported for the runner's at-rest byte comparison, never passed;
        /// any other difference fails.</summary>
        private static void DrvCfgVerdict(string tag, int r)
        {
            if (r == 0) DrvOk(tag + " restore, config file: byte-identical in this process");
            else if (r == 1) DrvNote(tag + " restore, config file: NOT a byte restore in this process - the bytes differ only where an entry was first bound during the run (above);"
                + " the verdict is the runner's raw byte comparison of the file at rest, before the launch and after the quit");
            else DrvBad(tag + " restore, config file: NOT restored (see the line above)");
        }

        /// <summary>The PlayerPrefs a witness run can move, by name: PlayerPrefs
        /// cannot be listed from inside the game, so the hash covers these.</summary>
        private static readonly string[] DrvWitnessPrefNames =
            { "cr_cursor_shape", "OPTION_LANGUAGE", "selected-locale", "Screenmanager Resolution Width",
              "Screenmanager Resolution Height", "Screenmanager Fullscreen mode" };

        private static string DrvPrefHash()
        {
            var sb = new System.Text.StringBuilder();
            var keys = new List<string>(DrvWitnessPrefNames) { MailClient.PrefKey("From"), MailClient.PrefKey("Relay") };
            foreach (var k in keys)
            {
                sb.Append(k).Append('=');
                try
                {
                    if (!PlayerPrefs.HasKey(k)) sb.Append("-");
                    else sb.Append("i").Append(PlayerPrefs.GetInt(k, int.MinValue).ToString(CultureInfo.InvariantCulture))
                        .Append("s").Append(PlayerPrefs.GetString(k, ""));
                }
                catch { sb.Append("?"); }
                sb.Append('\n');
            }
            return DrvHex(System.Text.Encoding.UTF8.GetBytes(sb.ToString()));
        }

        /// <summary>One sub-tab shown from its top with its first row focused
        /// and nothing pinned: the pane shows that row.</summary>
        private static IEnumerator DrvShowTab(int t)
        {
            SettingsSwitchSubTab(t);
            settingsFocusRow[t] = 0;
            settingsPinnedKey = null;
            SettingsUpdateFocusHighlight();
            settingsPaneDirty = true;
            SettingsRenderPane();
            yield return DrvSettle(0.5f);
            SettingsScrollListTo(1f);
            yield return 0.2f;
        }

        private static IEnumerator DrvShootTabs(string prefix)
        {
            for (int t = 0; t < SETTINGS_TABS; t++)
            {
                yield return DrvShowTab(t);
                yield return DrvCapture(prefix + "-" + (t + 1) + "-" + SettingsModel.SubTabHomes[t]);
            }
        }

        /// <summary>W1: one shot per sub-tab, 1920x1080, en (W11 is the
        /// Privacy shot's footer).</summary>
        private static IEnumerator DriveW1()
        {
            DrvParkPointer();
            yield return DrvShootTabs("w1");
        }

        /// <summary>W2's and W3's restore of the language and the named
        /// PlayerPrefs (the config file is DrvCfgVerdict's).</summary>
        private static void DrvLangPrefsVerdict(string tag, string lang0, string pp0)
        {
            string lang1 = Plugin.ModLanguage != null ? Plugin.ModLanguage.Value : "?";
            string pp1 = DrvPrefHash();
            if (lang1 == lang0) DrvOk(tag + " restore, language: back on '" + lang1 + "'");
            else DrvBad(tag + " restore, language: '" + lang1 + "', want '" + lang0 + "'");
            if (pp1 == pp0) DrvOk(tag + " restore, PlayerPrefs: sha256 " + pp1 + " matches the value before the switches");
            else DrvBad(tag + " restore, PlayerPrefs: sha256 " + pp0 + " -> " + pp1);
        }

        /// <summary>W2: the seven sub-tabs in es, ru, uk and sv; the cfg and
        /// the named PlayerPrefs hashed before the first switch and after the
        /// return to the starting language must match - the cfg as raw bytes
        /// (design residual 5's byte comparison): in this process, and at
        /// rest by the runner, before the launch and after the quit.</summary>
        private static IEnumerator DriveW2()
        {
            DrvParkPointer();
            string lang0 = Plugin.ModLanguage != null ? Plugin.ModLanguage.Value : "";
            yield return DrvPrimeBinds("W2");
            byte[] raw0 = DrvCfgBytes();
            var bound0 = DrvCfgBound();
            string cfg0 = raw0 != null ? DrvHex(raw0) : "unreadable", pp0 = DrvPrefHash();
            DrvNote("W2 before the switches: language '" + lang0 + "', cfg sha256 " + cfg0 + ", PlayerPrefs sha256 " + pp0);
            yield return DrvStoreSnapshot("w2-before");
            foreach (var loc in DrvLocales)
            {
                yield return DrvLanguage(loc);
                yield return DrvShootTabs("w2-" + loc);
            }
            yield return DrvLanguage(lang0);
            yield return 1.0f;
            DrvCfgVerdict("W2", DrvCfgRestored("W2", raw0, DrvCfgBytes(), bound0));
            DrvLangPrefsVerdict("W2", lang0, pp0);
            yield return DrvStoreSnapshot("w2-after");
        }

        /// <summary>Round-3 L3: every sub-tab shown once, in the starting
        /// language, before a witness takes its "before" copy of the config
        /// file, so an entry that is bound lazily the first time its row or
        /// its page runs (a first Bind saves the whole file, the entry now
        /// with its description) has been bound on BOTH sides of the
        /// comparison. The entries this binds are named.</summary>
        private static IEnumerator DrvPrimeBinds(string tag)
        {
            var b0 = DrvCfgBound();
            int t0 = settingsSubTab;
            for (int t = 0; t < SETTINGS_TABS; t++) yield return DrvShowTab(t);
            yield return DrvShowTab(t0);
            yield return 0.5f;
            var b1 = DrvCfgBound();
            var was = new HashSet<string>(b0, StringComparer.Ordinal);
            var first = new List<string>();
            foreach (var k in b1) if (!was.Contains(k)) first.Add(k);
            DrvNote(tag + " before its first copy of the config file: every sub-tab shown once; entries first bound by that: "
                + DrvList(first) + " (" + b1.Count + " bound in this process)");
        }

        /// <summary>Round-3 L3: a point where the runner snapshots the config
        /// file and the whole PlayerPrefs store (the registry key the game
        /// writes) while this process runs; the harness waits for it.</summary>
        private static IEnumerator DrvStoreSnapshot(string name)
        {
            DrvNote("SNAPSHOT " + name + " - the runner snapshots the config file and the PlayerPrefs store now");
            yield return 3.0f;
        }

        private static string DrvR(float f) { return (Mathf.Round(f * 10f) / 10f).ToString("0.0", CultureInfo.InvariantCulture); }

        /// <summary>W3: the settings panel's geometry in logical canvas units -
        /// every active RectTransform under it, as its path and its rect in
        /// the canvas's own space, to 0.1.</summary>
        private static List<string> DrvLayoutRects()
        {
            var l = new List<string>();
            var panel = tabPanels != null && tabPanels.Length > TAB_SETTINGS ? tabPanels[TAB_SETTINGS] : null;
            if (panel == null || overlayCanvasGO == null) return l;
            var root = overlayCanvasGO.transform;
            var c = new Vector3[4];
            foreach (var rt in panel.GetComponentsInChildren<RectTransform>(false))
            {
                rt.GetWorldCorners(c);
                Vector3 a = root.InverseTransformPoint(c[0]), b = root.InverseTransformPoint(c[2]);
                string path = rt.name;
                for (var p = rt.parent; p != null && p != panel.transform; p = p.parent) path = p.name + "/" + path;
                l.Add(path + " " + DrvR(a.x) + "," + DrvR(a.y) + "," + DrvR(b.x - a.x) + "," + DrvR(b.y - a.y));
            }
            return l;
        }

        /// <summary>W3: ru at 1920x1080, then at 1280x720 with no IMGUI surface
        /// up; each sub-tab's layout must be identical in logical units, and
        /// each is captured at 1280x720.</summary>
        private static IEnumerator DriveW3()
        {
            DrvParkPointer();
            string lang0 = Plugin.ModLanguage != null ? Plugin.ModLanguage.Value : "";
            yield return DrvPrimeBinds("W3");
            byte[] raw0 = DrvCfgBytes();
            var bound0 = DrvCfgBound();
            string pp0 = DrvPrefHash();
            yield return DrvStoreSnapshot("w3-before");
            yield return DrvLanguage("ru");
            var at1080 = new List<string>[SETTINGS_TABS];
            for (int t = 0; t < SETTINGS_TABS; t++)
            {
                yield return DrvShowTab(t);
                SettingsForceLayout();
                at1080[t] = DrvLayoutRects();
            }
            yield return DrvResolution(1280, 720);
            for (int t = 0; t < SETTINGS_TABS; t++)
            {
                yield return DrvShowTab(t);
                SettingsForceLayout();
                var now = DrvLayoutRects();
                var diff = new List<string>();
                for (int i = 0; i < Mathf.Max(now.Count, at1080[t].Count); i++)
                {
                    string x = i < at1080[t].Count ? at1080[t][i] : "(none)", y = i < now.Count ? now[i] : "(none)";
                    if (x != y && diff.Count < 4) diff.Add(x + " | " + y);
                }
                string home = SettingsModel.SubTabHomes[t];
                if (DrvPickerOpen()) DrvBad("W3 " + home + ": a dropdown is open; W3 takes the page only");
                if (diff.Count == 0 && now.Count > 0)
                    DrvOk("W3 " + home + ": " + now.Count + " rects at 1280x720 identical to 1920x1080 in logical units (sha256 "
                        + DrvHex(System.Text.Encoding.UTF8.GetBytes(string.Join("\n", now.ToArray()))) + ")");
                else DrvBad("W3 " + home + ": " + now.Count + " rects, " + at1080[t].Count + " at 1920x1080; first differences " + DrvList(diff));
                yield return DrvCapture("w3-" + (t + 1) + "-" + home);
            }
            yield return DrvResolutionRestore("W3");
            yield return DrvLanguage(lang0);
            yield return 1.0f;
            DrvCfgVerdict("W3", DrvCfgRestored("W3", raw0, DrvCfgBytes(), bound0));
            DrvLangPrefsVerdict("W3", lang0, pp0);
            yield return DrvStoreSnapshot("w3-after");
        }

        /// <summary>A1's horizontal leg for every row of the active sub-tab,
        /// named rows added (the blocked senders): each row lies inside the
        /// list viewport's width.</summary>
        private static void DrvNoClip(string tag, IEnumerable<GameObject> extra)
        {
            int tab = Mathf.Clamp(settingsSubTab, 0, SETTINGS_TABS - 1);
            float tol = 1.0f * SettingsCanvasScale();
            Rect vr = SettingsWorldRect(setListViewport);
            int n = 0;
            var bad = new List<string>();
            var gos = new List<GameObject>();
            foreach (var r in SettingsFocusList(tab)) if (r.Row != null) gos.Add(r.Row);
            if (extra != null) gos.AddRange(extra);
            foreach (var go in gos)
            {
                if (go == null || !go.activeInHierarchy) continue;
                Rect rr = SettingsWorldRect(go);
                n++;
                if (rr.xMin < vr.xMin - tol || rr.xMax > vr.xMax + tol) bad.Add(go.name);
            }
            if (bad.Count == 0) DrvOk(tag + "no clipped row: " + n + " rows inside the viewport's width");
            else DrvBad(tag + "rows past the viewport's width: " + DrvList(bad));
        }

        /// <summary>W3b: the seven sub-tabs at 2560x1080 (21:9), or the largest
        /// 21:9 surface a narrower display holds (the same 810 px logical
        /// canvas), with the three optional rows active - section 3.1's 506 px
        /// worst case - each unscrolled, with A5a, A5b and A8 measured.</summary>
        private static IEnumerator DriveW3b()
        {
            DrvParkPointer();
            bool perf0 = _perfSectionOpen;
            yield return DrvResolutionAspect(2560, 1080);
            yield return DrvForceRows(true);
            SettingsExpandTab(SettingsModel.SubTabIndex("perf"));
            for (int t = 0; t < SETTINGS_TABS; t++)
            {
                yield return DrvShowTab(t);
                DrvMeasureA5A8("W3b ");
                DrvNoClip("W3b " + SettingsModel.SubTabHomes[t] + ": ", null);
                SettingsScrollListTo(1f);
                yield return 0.3f;
                yield return DrvCapture("w3b-" + (t + 1) + "-" + SettingsModel.SubTabHomes[t]);
            }
            DrvPerfSection(perf0);
            yield return DrvForceRows(false);
            yield return DrvResolutionRestore("W3b");
        }

        private static void DrvPerfSection(bool open)
        {
            if (_perfSectionOpen == open) return;
            _perfSectionOpen = open;
            if (_perfSectionBody != null) _perfSectionBody.SetActive(open);
            dirty = true;
        }

        /// <summary>W3c: 5120x1440 (32:9) with the three optional rows active,
        /// past the supported bound (design section 11). Round-3 L2: a
        /// windowed surface is capped at the desktop, so 5120x1440 is sought
        /// by every method this process has, each result logged: the launch's
        /// own screen arguments (read at entry; the runner can launch with
        /// -screen-width 5120 -screen-height 1440), then SetResolution in
        /// Windowed, FullScreenWindow and ExclusiveFullScreen. Reached by any
        /// of them, W3c runs there. Reached by none, the bound is logged with
        /// the display's own mode list, and the same checks run at 2560x720,
        /// or the largest 32:9 surface a narrower display holds (the same
        /// aspect and 540 px logical canvas), as a SUBSTITUTE, every line
        /// tagged W3c-sub and every capture w3csub-, never filed as W3c.
        /// A5b's control: exactly five observations, named.
        /// Performance is captured unscrolled and after a scroll to the end.</summary>
        private static IEnumerator DriveW3c()
        {
            DrvParkPointer();
            bool perf0 = _perfSectionOpen;
            const int w = 5120, h = 1440;
            DrvNote("W3c at entry: " + DrvScreenState() + "; launched with " + DrvScreenArgs() + "; " + DrvDisplayModes(w, h));
            bool reached = Screen.width == w && Screen.height == h;
            if (reached) DrvNote("W3c: the launch's screen arguments gave " + w + "x" + h + "; no SetResolution call is made");
            var modes = new[] { FullScreenMode.Windowed, FullScreenMode.FullScreenWindow, FullScreenMode.ExclusiveFullScreen };
            for (int i = 0; i < modes.Length && !reached; i++)
            {
                yield return DrvResolutionMode(w, h, modes[i]);
                reached = Screen.width == w && Screen.height == h;
                DrvNote("W3c attempt " + (i + 1) + " of " + modes.Length + " (SetResolution " + w + "x" + h + " " + modes[i] + "): "
                    + (reached ? "REACHED - " : "not reached - ") + DrvScreenState());
            }
            string tag = reached ? "W3c" : "W3c-sub", shot = reached ? "w3c-" : "w3csub-";
            if (!reached)
            {
                DrvNote("W3c NOT REACHED: no method gave a " + w + "x" + h + " surface (" + DrvDisplayModes(w, h)
                    + "); the bound is a residual, and the 32:9 run below (2560x720, or the largest 32:9 surface the display holds) is a SUBSTITUTE, tagged W3c-sub, never W3c");
                yield return DrvResolutionAspect(2560, 720);
            }
            yield return DrvForceRows(true);
            SettingsExpandTab(SettingsModel.SubTabIndex("perf"));
            var obs = new List<string>();
            int perf = SettingsModel.SubTabIndex("perf");
            for (int t = 0; t < SETTINGS_TABS; t++)
            {
                yield return DrvShowTab(t);
                DrvMeasureA5A8(tag + " ", obs);
                DrvNoClip(tag + " " + SettingsModel.SubTabHomes[t] + ": ", null);
                if (t != perf) continue;
                SettingsScrollListTo(1f);
                yield return 0.3f;
                yield return DrvCapture(shot + "1-perf-top");
                SettingsScrollListTo(0f);
                yield return 0.3f;
                yield return DrvCapture(shot + "2-perf-end");
                SettingsScrollListTo(1f);
            }
            var want = new List<string> { "ingame", "visuals", "perf", "langmenus", "privacy" };
            obs.Sort(StringComparer.Ordinal);
            want.Sort(StringComparer.Ordinal);
            if (string.Join(",", obs.ToArray()) == string.Join(",", want.ToArray()))
                DrvOk(tag + " A5b's control: exactly five observations at " + Screen.width + "x" + Screen.height + ": " + DrvList(obs));
            else DrvBad(tag + " A5b's control: " + obs.Count + " observation(s) " + DrvList(obs) + ", want exactly " + DrvList(want));
            DrvPerfSection(perf0);
            yield return DrvForceRows(false);
            yield return DrvResolutionRestore(tag);
        }

        // blocked senders, as the page paints a server answer (W4, W10)
        private static readonly FieldInfo DrvBlocksF = typeof(MailUI).GetField("blocks", DrvPriv);
        private static readonly FieldInfo DrvBlocksExpF = typeof(MailUI).GetField("blocksExpanded", DrvPriv);
        private static readonly FieldInfo DrvBlocksVerF = typeof(MailUI).GetField("blocksVersion", DrvPriv);
        private static object drvBlocksSaved;
        private static bool drvBlocksExpSaved, drvBlocksHeld;

        /// <summary>The blocked-senders list holding n placeholder entries (no
        /// ids; nothing fetched, nothing sent), expanded; n = 0 is the empty
        /// answer. DrvPutBackBlocks restores what was there.</summary>
        private static IEnumerator DrvFakeBlocks(int n)
        {
            if (DrvBlocksF == null || DrvBlocksExpF == null || DrvBlocksVerF == null) { DrvBad("the blocked-senders fields were not found"); yield break; }
            if (!drvBlocksHeld)
            {
                drvBlocksSaved = DrvBlocksF.GetValue(null);
                drvBlocksExpSaved = (bool)DrvBlocksExpF.GetValue(null);
                drvBlocksHeld = true;
            }
            var l = new List<MailClient.Block>();
            for (int i = 1; i <= n; i++) l.Add(new MailClient.Block { name = "Blocked sender " + i });
            DrvBlocksF.SetValue(null, l);
            DrvBlocksExpF.SetValue(null, true);
            DrvBlocksVerF.SetValue(null, (int)DrvBlocksVerF.GetValue(null) + 1);
            dirty = true;
            yield return DrvSettle(0.5f);
            SettingsForceLayout();
            SettingsUpdateHint();
            SettingsForceLayout();
        }

        private static void DrvPutBackBlocks()
        {
            if (!drvBlocksHeld || DrvBlocksF == null) return;
            DrvBlocksF.SetValue(null, drvBlocksSaved);
            DrvBlocksExpF.SetValue(null, drvBlocksExpSaved);
            DrvBlocksVerF.SetValue(null, (int)DrvBlocksVerF.GetValue(null) + 1);
            drvBlocksHeld = false;
            dirty = true;
        }

        private static List<GameObject> DrvBlockRows()
        {
            var l = new List<GameObject>();
            var pr = pageGO != null ? pageGO.transform : null;
            for (int i = 0; i < 64; i++)
            {
                var t = SettingsFindDeep(pr, "SMailBlk" + i);
                if (t == null) break;
                l.Add(t.gameObject);
            }
            return l;
        }

        /// <summary>W10: Chat & mail at 2560x1080, or the largest 21:9 surface a
        /// narrower display holds (the same 810 px logical canvas), with the
        /// three optional rows active and twelve blocked senders: the hint
        /// active, no clipped row, and the twelfth sender inside the viewport
        /// after a scroll to the end.</summary>
        private static IEnumerator DriveW10()
        {
            DrvParkPointer();
            int cm = SettingsModel.SubTabIndex("chatmail");
            yield return DrvResolutionAspect(2560, 1080);
            yield return DrvForceRows(true);
            yield return DrvShowTab(cm);
            yield return DrvFakeBlocks(12);
            var rows = DrvBlockRows();
            bool hint = setListHint != null && setListHint.activeSelf;
            if (hint) DrvOk("W10 chatmail: " + rows.Count + " blocked-sender rows painted; the scroll hint is active");
            else DrvBad("W10 chatmail: " + rows.Count + " blocked-sender rows painted; the scroll hint is INACTIVE");
            DrvMeasureA5A8("W10 ");
            DrvNoClip("W10 chatmail: ", rows);
            SettingsScrollListTo(1f);
            yield return 0.3f;
            yield return DrvCapture("w10-1-chatmail-top");
            SettingsScrollListTo(0f);
            SettingsForceLayout();
            yield return 0.3f;
            Rect vr = SettingsWorldRect(setListViewport);
            float tol = 1.0f * SettingsCanvasScale();
            if (rows.Count == 12 && SettingsInside(vr, SettingsWorldRect(rows[11]), tol))
                DrvOk("W10 chatmail: after a scroll to the end the twelfth sender (SMailBlk11) lies inside the viewport");
            else DrvBad("W10 chatmail: after a scroll to the end the twelfth sender is " + (rows.Count < 12 ? "missing" : "outside the viewport"));
            yield return DrvCapture("w10-2-chatmail-end");
            SettingsScrollListTo(1f);
            DrvPutBackBlocks();
            yield return DrvForceRows(false);
            yield return DrvResolutionRestore("W10");
        }

        /// <summary>W9 / W9b: the SLang dropdown open, with the picker's own
        /// geometry (DrawArtistPicker: 540 wide, 118 + list, centred, in
        /// device pixels) checked inside the screen.</summary>
        private static IEnumerator DrvShootPicker(string name)
        {
            var r = DrvRec("SLang");
            if (r == null) { DrvBad(name + ": the SLang row was not built"); yield break; }
            SettingsSelectKey("SLang");
            yield return DrvSettle(0.3f);
            if (!DrvClick(r.Face) || !DrvPickerOpen()) { DrvBad(name + ": the SLang dropdown did not open"); yield break; }
            yield return 0.5f;
            var fNames = typeof(CompetitiveUI).GetField("artistPickerNames", DrvPriv);
            var names = fNames != null ? fNames.GetValue(null) as string[] : null;
            int n = names != null ? names.Length : 0;
            float listH = Mathf.Min(n * 32f + 4f, 330f), w = 540f, h = 118f + listH;
            float x = (Screen.width - w) / 2f, y = (Screen.height - h) / 2f;
            string at = DrvNum(w + 16f) + "x" + DrvNum(h + 16f) + " at (" + DrvNum(x - 8f) + "," + DrvNum(y - 8f) + ")";
            if (n > 0 && x - 8f >= 0f && y - 8f >= 0f && x + w + 8f <= Screen.width && y + h + 8f <= Screen.height)
                DrvOk(name + ": the dropdown's " + n + " rows are drawn in " + at + ", inside the " + Screen.width + "x" + Screen.height + " screen");
            else DrvBad(name + ": the dropdown (" + n + " rows) " + at + " is not inside the " + Screen.width + "x" + Screen.height + " screen");
            yield return DrvCapture(name);
            CompetitiveUI.ConsumePromptEscape();
            yield return 0.3f;
            if (DrvPickerOpen()) DrvBad(name + ": the dropdown did not close");
        }

        private static IEnumerator DriveW9()
        {
            DrvParkPointer();
            yield return DrvShootPicker("w9-1-dropdown-1920x1080");
            yield return DrvResolution(1280, 720);
            yield return DrvShootPicker("w9-2-dropdown-1280x720");
            yield return DrvResolutionRestore("W9");
        }

        private static IEnumerator DriveW9b()
        {
            DrvParkPointer();
            yield return DrvResolutionAspect(2560, 1080);
            yield return DrvShootPicker("w9b-dropdown-" + Screen.width + "x" + Screen.height);
            yield return DrvResolutionRestore("W9b");
        }

        /// <summary>Select a row as a click on its "?" does, then shoot.</summary>
        private static IEnumerator DrvShootRow(string key, string name)
        {
            var r = DrvRec(key);
            if (r == null) { DrvBad(name + ": the " + key + " row was not built"); yield break; }
            SettingsSelectKey(key);
            yield return DrvSettle(0.3f);
            SettingsEnsureVisible(DrvRec(key));
            yield return 0.2f;
            string pk = DrvPaneKey();
            if (pk == key || (key.StartsWith("SD", StringComparison.Ordinal) && pk == "SDR")) DrvNote(name + ": the pane shows " + pk);
            else DrvBad(name + ": the pane shows " + (pk ?? "nothing") + ", want " + key);
            yield return DrvCapture(name);
        }

        /// <summary>W4: one shot per widget kind with the pane open.</summary>
        private static IEnumerator DriveW4()
        {
            DrvParkPointer();
            bool perf0 = _perfSectionOpen;
            yield return DrvShootRow("SPing", "w4-01-switch");
            yield return DrvShootRow("SHpPrec", "w4-02-segmented");

            // the slider, mid-drag through the UI slider's own value, then at stop 0
            var sl = DrvRec("SChatTtl");
            Component slider = null;
            if (sl != null && sl.Slider != null && sl.Slider.go != null)
                foreach (var c in sl.Slider.go.GetComponents<Component>())
                    if (c != null && c.GetType().FullName == "UnityEngine.UI.Slider") slider = c;
            var pVal = slider != null ? slider.GetType().GetProperty("value") : null;
            if (sl == null || pVal == null || sl.Stops == null) DrvBad("w4: the SChatTtl slider was not found");
            else
            {
                int idx0 = Mathf.Clamp(sl.Index(), 0, sl.Stops.Length - 1);
                SettingsSelectKey("SChatTtl");
                yield return DrvSettle(0.3f);
                for (int fr = 1; fr <= 12; fr++) { pVal.SetValue(slider, 0.1f + 0.4f * fr / 12f, null); yield return 0f; }
                DrvNote("w4-03: the SChatTtl slider held mid-drag at value " + DrvNum((float)pVal.GetValue(slider, null)) + ", stop " + sl.Index());
                yield return DrvCapture("w4-03-slider-middrag");
                SettingsSetSliderIndex(DrvRec("SChatTtl"), 0);
                yield return DrvSettle(0.3f);
                yield return DrvCapture("w4-04-slider-stop0");
                SettingsSetSliderIndex(DrvRec("SChatTtl"), idx0);
                yield return DrvSettle(0.3f);
                DrvNote("w4: SChatTtl put back at stop " + idx0 + " (" + DrvValue(DrvRec("SChatTtl")) + ")");
            }

            // a dropdown open
            var dd = DrvRec("SDateFmt");
            if (dd == null) DrvBad("w4: the SDateFmt row was not built");
            else
            {
                SettingsSelectKey("SDateFmt");
                yield return DrvSettle(0.3f);
                if (!DrvClick(dd.Face) || !DrvPickerOpen()) DrvBad("w4-05: the SDateFmt dropdown did not open");
                else
                {
                    yield return 0.5f;
                    yield return DrvCapture("w4-05-dropdown-open");
                    CompetitiveUI.ConsumePromptEscape();
                    yield return 0.3f;
                }
            }

            yield return DrvShootRow("SEBtn", "w4-06-action");

            // the delete row armed (its confirmation would reach the stub), then disarmed
            if (deleteBtn == null) DrvBad("w4-07: the SDBtn button was not built");
            else
            {
                SettingsSelectKey("SDR");
                yield return DrvSettle(0.3f);
                DrvClick(deleteBtn);
                yield return 0.4f;
                if (deleteArmed) DrvNote("w4-07: the delete row is armed (" + settingsDeleteStubCalls + " confirmation(s) reached the stub)");
                else DrvBad("w4-07: the SDBtn click did not arm the delete row");
                SettingsEnsureVisible(DrvRec("SDR"));
                yield return DrvCapture("w4-07-destructive-armed");
                DrvDisarm();
                yield return DrvSettle(0.3f);
            }
            yield return DrvShootRow("SDR", "w4-08-destructive-pane");
            if (deleteArmed) DrvBad("w4-08: the delete row is armed; the combined pane shot wants it NOT armed");

            // disclosure expanded: Performance
            DrvPerfSection(true);
            yield return DrvShootRow("SPerfH", "w4-09-disclosure-perf");
            DrvPerfSection(perf0);

            // disclosure expanded: blocked senders, three, then none
            int cm = SettingsModel.SubTabIndex("chatmail");
            yield return DrvShowTab(cm);
            yield return DrvFakeBlocks(3);
            yield return DrvShootRow("SMailBlocked", "w4-10-blocked-three");
            yield return DrvFakeBlocks(0);
            var none = pageGO != null ? SettingsFindDeep(pageGO.transform, "SMailBlockedNone") : null;
            if (none != null && none.gameObject.activeInHierarchy) DrvNote("w4-11: SMailBlockedNone is shown");
            else DrvBad("w4-11: SMailBlockedNone is not shown for an empty list");
            yield return DrvShootRow("SMailBlocked", "w4-11-blocked-empty");
            DrvPutBackBlocks();
            yield return DrvSettle(0.3f);

            // the preview: the renderer's own preview path (a render, never an upload)
            if (PortraitRender.PreviewTex == null)
            {
                PortraitRender.DevRun("preview");
                float until = Time.unscaledTime + 45f;
                while (PortraitRender.PreviewTex == null && Time.unscaledTime < until) yield return 0.5f;
            }
            DrvNote("w4-12: the preview " + (PortraitRender.PreviewTex != null ? "holds a render" : "has no render") + " (renderer: " + PortraitRender.LastResult + ")");
            yield return DrvShootRow("SPcPre", "w4-12-preview");
        }

        /// <summary>W5: the pane follows the pointer - hover one row, then a
        /// "?" on a different one (the pointer moves onto that "?"); neither
        /// is the focused first row.</summary>
        private static IEnumerator DriveW5()
        {
            DrvParkPointer();
            var a = DrvRec("SShad");
            var b = DrvRec("SChromAb");
            if (a == null || b == null || a.Row == null || b.Help == null) { DrvBad("W5 the SShad / SChromAb rows were not built"); yield break; }
            yield return DrvShowTab(a.Tab);
            DrvPointAt(a.Row);
            yield return 0.5f;
            settingsPaneDirty = true;
            yield return 0.3f;
            if (settingsHoverKey == a.Key && DrvPaneKey() == a.Key) DrvOk("W5 hover: the pointer over " + a.Key + " (focused " + SettingsFocusedRec().Key + "); the pane shows " + a.Key);
            else DrvBad("W5 hover: hovered " + (settingsHoverKey ?? "nothing") + ", the pane shows " + (DrvPaneKey() ?? "nothing") + ", want " + a.Key);
            yield return DrvCapture("w5-1-hover");
            DrvPointAt(b.Help);
            yield return 0.3f;
            DrvClick(b.Help);
            yield return 0.4f;
            if (DrvPaneKey() == b.Key && SettingsFocusedRec() == DrvRec(b.Key)) DrvOk("W5 help: a click on " + b.Key + "'s ? moves the focus and the pane to " + b.Key);
            else DrvBad("W5 help: the pane shows " + (DrvPaneKey() ?? "nothing") + ", want " + b.Key);
            yield return DrvCapture("w5-2-help");
            DrvParkPointer();
        }

        /// <summary>W6: keyboard only (the pointer parked, no click): arrow to
        /// the third Visuals row, step a segmented control, Tab to the next
        /// sub-tab. The stepped value is put back through its own row after.</summary>
        private static IEnumerator DriveW6()
        {
            DrvParkPointer();
            int vis = SettingsModel.SubTabIndex("visuals");
            yield return DrvShowTab(vis);
            yield return DrvPress(SettingsModel.SettingsKey.Down, 0.2f);
            yield return DrvPress(SettingsModel.SettingsKey.Down, 0.3f);
            var list = SettingsFocusList(vis);
            var f = SettingsFocusedRec();
            if (list.IndexOf(f) == 2) DrvOk("W6 two Down presses: the focus is on the third Visuals row, " + f.Key + " (" + f.Kind + "); the pane shows " + DrvPaneKey());
            else DrvBad("W6 two Down presses: the focus is on " + (f != null ? f.Key : "nothing") + " (index " + list.IndexOf(f) + ")");
            yield return DrvCapture("w6-1-third-row");
            SettingsRowRec seg = null;
            for (int i = Mathf.Max(0, list.IndexOf(f)); i < list.Count; i++) if (list[i].Kind == SettingsKind.Segmented) { seg = list[i]; break; }
            if (seg == null) { DrvBad("W6 no segmented row at or below the third Visuals row"); yield break; }
            for (int guard = 0; guard < 12 && SettingsFocusedRec() != seg; guard++) yield return DrvPress(SettingsModel.SettingsKey.Down, 0.2f);
            string v0 = DrvValue(seg);
            int at = seg.Ids != null ? Array.IndexOf(seg.Ids, v0) : -1;
            var dir = seg.Ids != null && at == seg.Ids.Length - 1 ? SettingsModel.SettingsKey.Left : SettingsModel.SettingsKey.Right;
            yield return DrvPress(dir, 0.5f);
            string v1 = DrvValue(DrvRec(seg.Key));
            if (v1 != null && v1 != v0) DrvOk("W6 " + dir + " on " + seg.Key + ": " + v0 + " -> " + v1);
            else DrvBad("W6 " + dir + " on " + seg.Key + ": the value stayed " + v0);
            yield return DrvCapture("w6-2-segmented-step");
            yield return DrvPress(SettingsModel.SettingsKey.Tab, 0.5f);
            if (settingsSubTab == vis + 1) DrvOk("W6 Tab: the page moved to the next sub-tab, " + SettingsModel.SubTabHomes[settingsSubTab]);
            else DrvBad("W6 Tab: the page is on sub-tab " + settingsSubTab + ", want " + (vis + 1));
            yield return DrvCapture("w6-3-tab-next");
            var back = DrvRec(seg.Key);
            if (back != null && DrvValue(back) != v0)
            {
                SettingsSwitchSubTab(back.Tab);
                yield return 0.3f;
                DrvSetValue(back, v0);
                yield return DrvSettle(0.3f);
            }
            DrvNote("W6 put back: " + seg.Key + " reads " + DrvValue(DrvRec(seg.Key)) + " (was " + v0 + ")");
        }

        private static string DrvColor(Color c)
        {
            var inv = CultureInfo.InvariantCulture;
            return "(" + c.r.ToString("0.00", inv) + "," + c.g.ToString("0.00", inv) + ","
                + c.b.ToString("0.00", inv) + "," + c.a.ToString("0.00", inv) + ")";
        }

        private static bool DrvSameColor(Color a, Color b)
        {
            return Mathf.Abs(a.r - b.r) < 0.01f && Mathf.Abs(a.g - b.g) < 0.01f
                && Mathf.Abs(a.b - b.b) < 0.01f && Mathf.Abs(a.a - b.a) < 0.01f;
        }
    }
}
