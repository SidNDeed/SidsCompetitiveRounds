using System;
using System.Collections.Generic;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// v1.41.0 item 21: damage and heal numbers above players, as a setting
    /// (Off / Me / Everyone, default Off). The Unity-side half: the local
    /// setting, two READ-ONLY hook pairs, the spectator poison notify, the
    /// per-frame tick that stamps anchors and colours onto what
    /// DamageNumberRules flushed, and the IMGUI draw.
    ///
    /// Read-only on health, always. The hooks capture data.health before the
    /// vanilla body and re-read it after; they never return false, never write
    /// __result and never assign through a vanilla reference. Nothing here is
    /// sent anywhere: no RPC, no room property, no report field. The labels
    /// are local IMGUI, so two players in one room with different settings
    /// see different overlays of an identical game, and no whole-room gate is
    /// needed (design section 4).
    ///
    /// Every hook body is one try/catch. A throw in a DoDamage Prefix would
    /// stop the vanilla body and lose the victim's whole health delta on this
    /// client (bug-186, learning #322), and DoDamage deliberately carries no
    /// finalizer, so the guard is the integrity bar, not the scanner.
    /// </summary>
    internal static class DamageNumbers
    {
        internal const string OFF = "Off";
        internal const string ME = "Me";
        internal const string EVERYONE = "Everyone";

        // ------------------------------------------------------------ the setting

        private static BepInEx.Configuration.ConfigEntry<string> _entry;

        /// <summary>Bound here, the file that owns the feature (the
        /// HealthPrecisionSetting pattern). Lazy; a null ConfigFile early in
        /// startup is retried on the next read, never latched.</summary>
        internal static BepInEx.Configuration.ConfigEntry<string> Entry()
        {
            if (_entry != null) return _entry;
            try
            {
                var cf = Plugin.ConfigFileForLevers;
                if (cf == null) return null;
                _entry = cf.Bind(
                    "UI", "DamageNumbers", OFF,
                    "Floating numbers above a player for damage taken and health received: "
                    + "Off, Me (your own fighter; everyone when you are spectating) or Everyone. "
                    + "Uses the same decimals as the HP readout. Local display only - nothing is sent "
                    + "and nothing changes for anyone else in the room.");
            }
            catch { _entry = null; }
            return _entry;
        }

        /// <summary>The current pick, canonicalised. Anything else reads as
        /// Off, today's behaviour.</summary>
        internal static string Level
        {
            get
            {
                string v = "";
                try { var e = Entry(); v = e != null ? (e.Value ?? "") : ""; } catch { }
                return Canonical(v);
            }
        }

        internal static string Canonical(string v)
        {
            v = (v ?? "").Trim();
            if (string.Equals(v, ME, StringComparison.OrdinalIgnoreCase)) return ME;
            if (string.Equals(v, EVERYONE, StringComparison.OrdinalIgnoreCase)) return EVERYONE;
            return OFF;
        }

        /// <summary>The value-taking writer (the settings row and the per-tab
        /// reset). Null or unknown writes Off.</summary>
        internal static void Set(string level)
        {
            string next = Canonical(level);
            try { var e = Entry(); if (e != null) e.Value = next; } catch { }
        }

        internal static DamageNumberRules.Mode ModeOf(string level)
        {
            return level == ME ? DamageNumberRules.Mode.Me
                : level == EVERYONE ? DamageNumberRules.Mode.Everyone
                : DamageNumberRules.Mode.Off;
        }

        /// <summary>The mode, read from the setting once per frame by Tick so
        /// the hooks (Heal runs every frame under regeneration) never touch
        /// the config. Starts Off: nothing is noted before the first tick.</summary>
        private static DamageNumberRules.Mode _mode = DamageNumberRules.Mode.Off;

        internal static DamageNumberRules.Mode CurrentMode { get { return _mode; } }

        // ------------------------------------------------------------ W1: damage

        /// <summary>The damage funnel, resolved with its declaring type written
        /// out: DamagableEvent declares a DoDamage of its own (the destructible
        /// object path, no data field at all), and a target resolved by name
        /// alone could attach there.</summary>
        [HarmonyPatch(typeof(HealthHandler), "DoDamage")]
        internal static class DoDamageHooks
        {
            /// <summary>__state: float.MinValue = not armed (nothing entered);
            /// -Infinity = armed but nested (exit only); finite = armed and
            /// outermost, holding health before the vanilla body.</summary>
            [HarmonyPrefix]
            internal static void DoDamagePrefix(HealthHandler __instance, out float __state)
            {
                try
                {
                    __state = float.MinValue;
                    if (CurrentMode == DamageNumberRules.Mode.Off) return;
                    var data = __instance != null ? __instance.data : null;
                    if (data == null || data.view == null) return;
                    var f = DamageNumberRules.DamageFence.Enter(data.view.ViewID, Time.unscaledTime);
                    __state = f.Outermost ? data.health : float.NegativeInfinity;
                }
                catch { __state = float.MinValue; }
            }

            [HarmonyPostfix]
            internal static void DoDamagePostfix(HealthHandler __instance, float __state)
            {
                try
                {
                    if (__state == float.MinValue) return;
                    var data = __instance != null ? __instance.data : null;
                    int subject = data != null && data.view != null ? data.view.ViewID : 0;
                    try
                    {
                        if (data != null && !float.IsNegativeInfinity(__state))
                        {
                            float drop = __state - data.health;
                            if (drop > 0f) Emit(subject, DamageNumberRules.Kind.Damage, drop, __instance.transform.position);
                        }
                    }
                    finally
                    {
                        DamageNumberRules.DamageFence.Exit(subject);
                    }
                }
                catch { }
            }
        }

        // ------------------------------------------------------------ W2: heal

        /// <summary>The heal funnel. The OBSERVED rise is what prints, never
        /// healAmount: Heal clamps at MaxHealth and early-returns at full
        /// health (learning #256).</summary>
        [HarmonyPatch(typeof(HealthHandler), "Heal")]
        internal static class HealHooks
        {
            [HarmonyPrefix]
            internal static void HealPrefix(HealthHandler __instance, out float __state)
            {
                try
                {
                    __state = float.MinValue;
                    if (CurrentMode == DamageNumberRules.Mode.Off) return;
                    var data = __instance != null ? __instance.data : null;
                    if (data == null || data.view == null) return;
                    var f = DamageNumberRules.HealFence.Enter(data.view.ViewID, Time.unscaledTime);
                    __state = f.Outermost ? data.health : float.NegativeInfinity;
                }
                catch { __state = float.MinValue; }
            }

            [HarmonyPostfix]
            internal static void HealPostfix(HealthHandler __instance, float __state)
            {
                try
                {
                    if (__state == float.MinValue) return;
                    var data = __instance != null ? __instance.data : null;
                    int subject = data != null && data.view != null ? data.view.ViewID : 0;
                    try
                    {
                        if (data != null && !float.IsNegativeInfinity(__state))
                        {
                            float rise = data.health - __state;
                            if (rise > 0f) Emit(subject, DamageNumberRules.Kind.Heal, rise, __instance.transform.position);
                        }
                    }
                    finally
                    {
                        DamageNumberRules.HealFence.Exit(subject);
                    }
                }
                catch { }
            }
        }

        // ------------------------------------------------------------ W3: direct poison writers

        /// <summary>The direct-writer bridge. PoisonSync lowers health in two
        /// places by a direct write that bypasses DoDamage, so W1 never sees
        /// either: the committed tick on a spectator seat (the #338 fence) and
        /// the correction funnel ApplyCorrective, which runs on fighter and
        /// spectator seats alike. Each calls this once, under its own "health
        /// actually dropped" predicate, with health read before and after its
        /// write, in a try of its own ahead of its health-bar companion's try
        /// (build R2 HC): the bar is optional display, and a throw in it can
        /// no longer cost a committed drop its number. The number is the
        /// OBSERVED applied drop (DamageNumberRules.AppliedDrop: the floor
        /// already taken), never the slice magnitude, and the subject is the
        /// victim's own view, the same rule W1 uses.</summary>
        internal static void NoteDirectDrop(PhotonView view, float pre, float post)
        {
            try
            {
                if (view == null) return;
                float applied = DamageNumberRules.AppliedDrop(pre, post);
                if (!(applied > 0f)) return;
                if (CurrentMode == DamageNumberRules.Mode.Off) return;
                Emit(view.ViewID, DamageNumberRules.Kind.Damage, applied, view.transform.position);
            }
            catch { }
        }

        // ------------------------------------------------------------ notify

        private static readonly Dictionary<int, Vector3> _anchors = new Dictionary<int, Vector3>();
        private static int _localView = DamageNumberRules.SpectatorSentinel;
        private static int _expirySeen;

        private static void Emit(int subject, DamageNumberRules.Kind kind, float magnitude, Vector3 bodyPosition)
        {
            if (!DamageNumberRules.ShouldShow(CurrentMode, subject, _localView)) return;
            if (_anchors.Count >= 32 && !_anchors.ContainsKey(subject)) _anchors.Clear();
            _anchors[subject] = bodyPosition + Vector3.up * 0.55f;
            Note(subject, kind, magnitude, Time.unscaledTime);
        }

        /// <summary>The one notify entry point. Both refusals are REPORTED,
        /// never silent: a subject past the cap, and a fence entry that had to
        /// expire (a hook whose Postfix never ran).</summary>
        internal static bool Note(int subject, DamageNumberRules.Kind kind, float magnitude, float now)
        {
            bool ok = DamageNumberRules.Shared.Note(subject, kind, magnitude, now,
                DamageNumberRules.SubjectCapFor(ApiClient.FfaLobbyMaxPlayers));
            if (!ok)
                VanillaFixSupport.DiagLimited("DmgNum-subject-cap",
                    "[DMGNUM] subject cap reached; view " + subject + " refused (refusals "
                    + DamageNumberRules.Shared.Refusals + ")", 20);
            int expired = DamageNumberRules.DamageFence.Expirations + DamageNumberRules.HealFence.Expirations;
            if (expired != _expirySeen)
            {
                _expirySeen = expired;
                VanillaFixSupport.DiagLimited("DmgNum-fence-expired",
                    "[DMGNUM] a hook fence entry expired (total " + expired + ")", 20);
            }
            return ok;
        }

        // ------------------------------------------------------------ tick

        private static readonly Vector3[] _world = new Vector3[DamageNumberRules.MaxLive];
        private static readonly string[] _text = new string[DamageNumberRules.MaxLive];
        private static readonly Color[] _color = new Color[DamageNumberRules.MaxLive];
        private static readonly Color DamageRed = new Color(1f, 0.32f, 0.28f, 1f);
        /// <summary>The health bar's own blue (HealBarOverlay.BLUE), so one
        /// heal language runs across the bar and the numbers.</summary>
        private static readonly Color HealBlue = new Color(0.32f, 0.72f, 1f, 1f);
        private static string _loggedMode;

        /// <summary>Unity-side tick, from DamageNumberDriver.Update every
        /// frame whether or not anything is drawn: the rules flush and format,
        /// this stamps anchor and colour into the ring slot each emission was
        /// placed in. It formats nothing.</summary>
        internal static void Tick(float now)
        {
            string mode = Level;
            _mode = ModeOf(mode);
            if (!string.Equals(mode, _loggedMode, StringComparison.Ordinal))
            {
                _loggedMode = mode;
                Plugin.Log.LogInfo("[DMGNUM] mode " + mode);
            }
            _localView = ResolveLocalView();
            DamageNumberRules.SetFormat(TabStatsOverlay.HealthPrecisionSetting.Fmt);
            var em = DamageNumberRules.Tick(now);
            for (int i = 0; i < em.Length; i++)
            {
                int slot = em[i].Slot;
                if (slot < 0 || slot >= DamageNumberRules.MaxLive) continue;
                Vector3 at;
                if (!_anchors.TryGetValue(em[i].Subject, out at)) { _text[slot] = null; continue; }
                _world[slot] = at;
                _text[slot] = em[i].Text;
                _color[slot] = em[i].Kind == DamageNumberRules.Kind.Damage ? DamageRed : HealBlue;
            }
        }

        /// <summary>The local fighter's view id, or the spectator sentinel when
        /// this seat has none (a spectator, the broadcast seat, an offline
        /// room where every body is local).</summary>
        private static int ResolveLocalView()
        {
            try
            {
                if (PhotonNetwork.OfflineMode) return DamageNumberRules.SpectatorSentinel;
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return DamageNumberRules.SpectatorSentinel;
                for (int i = 0; i < pm.players.Count; i++)
                {
                    var p = pm.players[i];
                    if (p != null && p.data != null && p.data.view != null && p.data.view.IsMine)
                        return p.data.view.ViewID;
                }
            }
            catch { }
            return DamageNumberRules.SpectatorSentinel;
        }

        // ------------------------------------------------------------ draw

        private static GUIStyle _style;
        private static int _styleScreenH = -1;
        private static int _fontSize;
        private const float RisePx = 34f;
        private const float FadeTail = 0.3f;

        /// <summary>From CompetitiveUI.DrawUI, just before the hold-Tab board,
        /// so the board, notifications, chat and every modal paint over it.
        /// Six early returns, then a pure function of time since birth: no
        /// formatting and no allocation per frame (#162).</summary>
        internal static void Draw()
        {
            if (Event.current == null || Event.current.type != EventType.Repaint) return;
            if (CurrentMode == DamageNumberRules.Mode.Off) return;
            if (!VanillaFixSupport.AnyGameScope()) return;
            if (NativeUI.IsOpen) return;
            if (CompetitiveUI.IsChatInputOpen) return;
            bool paused = true;
            try { paused = EscapeMenuHandler.isEscMenu; } catch { paused = true; }
            if (paused) return;
            try
            {
                float now = Time.unscaledTime;
                var ring = DamageNumberRules.Shared.Ring;
                Camera cam = null;
                try { cam = MainCam.instance != null ? MainCam.instance.cam : Camera.main; } catch { cam = null; }
                if (cam == null) return;

                int first = -1;
                for (int i = 0; i < DamageNumberRules.MaxLive; i++)
                    if (_text[i] != null && ring.IsLive(i, now)) { first = i; break; }
                if (first < 0) return;

                // One global scale per Repaint: the camera is orthographic.
                // `a` is also the first live entry's own projection and is
                // reused for it below, so a Repaint at MaxLive live labels
                // makes 2 + (MaxLive - 1) = 25 projections (design: 25).
                Vector3 a = cam.WorldToScreenPoint(_world[first]);
                Vector3 b = cam.WorldToScreenPoint(_world[first] + cam.transform.up);
                float ppu = Mathf.Abs(b.y - a.y);
                int size = Mathf.Clamp(Mathf.RoundToInt(ppu * 0.42f), 14, 28);
                if (_style == null || _styleScreenH != Screen.height)
                {
                    _style = new GUIStyle(GUI.skin.label)
                    {
                        fontStyle = FontStyle.Bold,
                        alignment = TextAnchor.MiddleCenter,
                        wordWrap = false,
                        clipping = TextClipping.Overflow,
                    };
                    _style.normal.textColor = Color.white;
                    _styleScreenH = Screen.height;
                    _fontSize = -1;
                }
                if (_fontSize != size) { _style.fontSize = size; _fontSize = size; }

                // The incoming colour comes back from a finally (build R2 N2,
                // the CompetitiveUI banner shape): the catch below swallows a
                // throw from inside the loop, and a restore placed after the
                // loop would then be skipped, leaking the last tint written
                // here into every surface drawn later in the pass.
                Color keep = GUI.color;
                try
                {
                    for (int i = 0; i < DamageNumberRules.MaxLive; i++)
                    {
                        if (_text[i] == null || !ring.IsLive(i, now)) continue;
                        float age = now - ring.Born[i];
                        Vector3 sp = i == first ? a : cam.WorldToScreenPoint(_world[i]);
                        if (sp.z < 0f) continue;
                        float alpha = age <= DamageNumberRules.Life - FadeTail ? 1f
                            : Mathf.Clamp01((DamageNumberRules.Life - age) / FadeTail);
                        float x = sp.x + (i % 3 - 1) * 16f;
                        float y = Screen.height - sp.y - (age / DamageNumberRules.Life) * RisePx;
                        var rect = new Rect(x - 70f, y - 18f, 140f, 36f);
                        GUI.color = new Color(0f, 0f, 0f, 0.85f * alpha);
                        GUI.Label(new Rect(rect.x + 1f, rect.y + 1f, rect.width, rect.height), _text[i], _style);
                        Color c = _color[i];
                        GUI.color = new Color(c.r, c.g, c.b, alpha);
                        GUI.Label(rect, _text[i], _style);
                    }
                }
                finally { GUI.color = keep; }
            }
            catch (Exception ex) { VanillaFixSupport.DiagLimited("DmgNum-draw", "[DMGNUM] draw failed: " + ex.Message, 3); }
        }

        // ------------------------------------------------------------ attach line

        /// <summary>The positive signal that both hook pairs ATTACHED (#83): a
        /// patch that never attached and a feature correctly set to Off draw
        /// the same nothing, and only this line tells them apart.</summary>
        internal static void BootLine()
        {
            int dd = Attached(AccessTools.Method(typeof(HealthHandler), "DoDamage"), typeof(DoDamageHooks));
            int hl = Attached(AccessTools.Method(typeof(HealthHandler), "Heal"), typeof(HealHooks));
            Plugin.Log.LogInfo("[DMGNUM] hooks attached: DoDamage " + dd + "/2, Heal " + hl + "/2; mode " + Level);
        }

        private static int Attached(System.Reflection.MethodBase m, Type owner)
        {
            int n = 0;
            try
            {
                var info = m != null ? Harmony.GetPatchInfo(m) : null;
                if (info == null) return 0;
                foreach (var p in info.Prefixes) if (p.PatchMethod != null && p.PatchMethod.DeclaringType == owner) n++;
                foreach (var p in info.Postfixes) if (p.PatchMethod != null && p.PatchMethod.DeclaringType == owner) n++;
            }
            catch { }
            return n;
        }
    }

    /// <summary>The driver: the call site of the rules' flush that runs when
    /// nothing is being drawn (Escape menu, chat, NativeUI, a frame with no
    /// Repaint), so a lone hit still becomes a label and ages on schedule.
    /// A component on the mod's persistent companion host - no renderer, no
    /// collider, no OnGUI. Its WHOLE body is one try/catch, the time read
    /// included: a preamble outside the guard that threw would stop every
    /// label for the session.</summary>
    internal sealed class DamageNumberDriver : MonoBehaviour
    {
        private void Update()
        {
            try
            {
                DamageNumbers.Tick(Time.unscaledTime);
            }
            catch (Exception ex)
            {
                VanillaFixSupport.DiagLimited("DmgNum-tick", "[DMGNUM] tick failed: " + ex.Message, 5);
            }
        }
    }
}
