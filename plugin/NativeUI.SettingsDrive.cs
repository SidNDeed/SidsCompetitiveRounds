using System;
using System.Collections;
using System.Collections.Generic;
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

        /// <summary>Confirmations the delete row reached while a settings test
        /// ran. Each one would otherwise have been a deletion request.</summary>
        internal static int settingsDeleteStubCalls;

        internal static bool SettingsDriveRunning => drvStack.Count > 0;

        /// <summary>True while a settings test runs (the self-test or this
        /// harness): the delete row's confirmation then reaches the stub.</summary>
        internal static bool SettingsTestRunning => SettingsDriveRunning || SettingsSelfTestRunning;

        /// <summary>The scenarios, in the order "5:drive" runs them.</summary>
        private static readonly string[] SettingsDriveScenarios = { "m1" };

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
    }
}
