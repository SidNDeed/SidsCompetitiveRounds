using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Aug 6 item 7 — an equipped body color becomes the player's TEAM IDENTITY.
    ///
    /// Sid: "When someone equips a body color, they should be that color in-game in
    /// more aspects. Their name and point/half point colors, their 'team name' so
    /// when they get a point it doesn't say Orange got a point but Mustard."
    ///
    /// This class is the single resolver. Every surface (the point announcement, the
    /// vanilla round-counter dots, the in-game nametag, the FFA score strip) asks it
    /// for "what is team N called and what colour is it", and it answers from state
    /// that is REPLICATED to every client.
    ///
    /// ── The contract, stated precisely (Codex round 1) ────────────────────────
    /// The earlier wording here claimed "all clients render the same thing" full
    /// stop, and that is NOT what the code does: a client with the "show player
    /// colours" setting OFF returns no identity at all and renders vanilla
    /// Orange/Blue while its peers render Mustard. That is DELIBERATE — with
    /// vanilla-coloured bodies on screen, announcing a colour the player cannot
    /// see is worse than not announcing it — and it is safe because everything
    /// this class feeds is a LABEL or a TINT: an announcement string, counter
    /// dots, a nametag colour, a score-strip row. None of it is gameplay, none of
    /// it is reported, and the divergence is exactly the local preference the
    /// player chose. The accurate contract is therefore:
    ///
    ///   Among clients that have the feature ENABLED, the resolved name and
    ///   colour for a given team are identical, because every input is
    ///   replicated. A client with it disabled opts out entirely and sees
    ///   vanilla.
    ///
    /// Anything added here that is NOT purely cosmetic must not take that
    /// local-preference early-out.
    ///
    /// ── Inputs, and why they are the same everywhere ──────────────────────────
    ///  * <c>Player.TeamID</c> — assigned by vanilla's networked player assignment.
    ///  * Photon PLAYER custom properties <c>cr_pcolor_sku</c> / <c>cr_pcolor_color</c>,
    ///    published by <see cref="PlayerColorCosmetic.PublishLocalProps"/>. Photon
    ///    replicates player properties to everyone in the room.
    ///  * Photon <c>ActorNumber</c> — assigned by the Photon SERVER, identical on
    ///    every client and stable for the room's lifetime.
    /// Nothing local-only feeds a resolved identity, with ONE deliberate exception
    /// noted at <see cref="TryReadEquipped"/>: if our OWN prop has not landed yet we
    /// fall back to the local cached stats, so our own body/name/announcement agree
    /// with each other during the publish window. That is the same asymmetry
    /// PlayerColorCosmetic.DelayedApplyAll already has for the body tint itself.
    ///
    /// Properties are EVENTUALLY consistent (#280/#287), so identities are resolved
    /// at announcement/draw time and never latched at match start, and a missing or
    /// unparseable property degrades to "no identity" = untouched vanilla behaviour.
    /// </summary>
    internal static class TeamColorIdentity
    {
        private const string PROP_SKU   = "cr_pcolor_sku";
        private const string PROP_COLOR = "cr_pcolor_color";

        public struct TeamIdentity
        {
            public bool Valid;
            /// <summary>Bare shop name, e.g. "Mustard".</summary>
            public string ColorName;
            /// <summary>Display form — bare name, or "Mustard (Stan)" when another
            /// team holds the same colour.</summary>
            public string Name;
            /// <summary>Announcement form — colour part upper-cased to match
            /// vanilla's shouty point text, player suffix left as typed.</summary>
            public string AnnounceName;
            /// <summary>Raw equipped colour (the body tint).</summary>
            public Color Color;
            /// <summary>Same hue, lifted to stay legible as text/dots on a dark scene.</summary>
            public Color TextColor;
            public string Sku;
            public int OwnerActor;
        }

        private sealed class Entry
        {
            public int Actor;
            public string Sku;
            public Color Color;
            public string OwnerName;
        }

        private static readonly Dictionary<int, TeamIdentity> _byTeam = new Dictionary<int, TeamIdentity>();
        private static readonly Dictionary<int, Entry> _bestByTeam = new Dictionary<int, Entry>();
        private static readonly Dictionary<string, int> _nameCounts =
            new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        private static float _cachedAt = -999f;

        // ── Public API ────────────────────────────────────────────────────────

        /// <summary>The team's colour identity, or Valid=false when nobody on that
        /// team has a body colour equipped (every caller then leaves vanilla alone).</summary>
        public static bool TryGet(int teamId, out TeamIdentity identity)
        {
            identity = default(TeamIdentity);
            try
            {
                Rebuild();
                TeamIdentity found;
                if (!_byTeam.TryGetValue(teamId, out found)) return false;
                identity = found;
                return found.Valid;
            }
            catch { return false; }
        }

        /// <summary>Convenience for the surfaces that only need the colour.</summary>
        public static bool TryGetColor(int teamId, out Color color)
        {
            TeamIdentity id;
            if (TryGet(teamId, out id)) { color = id.Color; return true; }
            color = Color.white;
            return false;
        }

        /// <summary>Lift a colour so it stays readable as text or a small dot against
        /// ROUNDS' dark scene. Charcoal/Obsidian bodies are near-black; drawn raw they
        /// would be an invisible point announcement.</summary>
        public static Color ReadableOnDark(Color c)
        {
            float max = Mathf.Max(c.r, Mathf.Max(c.g, c.b));
            if (max < 0.001f) return new Color(0.74f, 0.74f, 0.80f, 1f);
            if (max < 0.55f)
            {
                float k = 0.55f / max;
                return new Color(Mathf.Clamp01(c.r * k), Mathf.Clamp01(c.g * k), Mathf.Clamp01(c.b * k), 1f);
            }
            return new Color(c.r, c.g, c.b, 1f);
        }

        /// <summary>Shop display name for a body-colour sku. Every pcolor sku in the
        /// catalogue is the snake_case of its shop name (pcolor_neon_pink -> "Neon
        /// Pink"), so deriving beats a hand-maintained table that would silently miss
        /// the next sku the server adds (#183's lesson, applied preventively).</summary>
        public static string DisplayNameForSku(string sku)
        {
            if (string.IsNullOrEmpty(sku)) return null;
            if (!sku.StartsWith("pcolor_", StringComparison.OrdinalIgnoreCase)) return null;
            string body = sku.Substring("pcolor_".Length);
            if (body.Length == 0) return null;
            var sb = new System.Text.StringBuilder(body.Length + 2);
            bool startOfWord = true;
            foreach (char ch in body)
            {
                if (ch == '_') { sb.Append(' '); startOfWord = true; continue; }
                if (ch > 127) return null;               // ASCII only (#47)
                sb.Append(startOfWord ? char.ToUpperInvariant(ch) : ch);
                startOfWord = false;
            }
            return sb.ToString();
        }

        // ── Resolution ────────────────────────────────────────────────────────

        private static void Rebuild()
        {
            float now = Time.realtimeSinceStartup;
            // Short TTL: the inputs only change on a prop publish or a player
            // join/leave, and every consumer here is a low-frequency UI path.
            if (now - _cachedAt < 0.25f) return;
            _cachedAt = now;
            _byTeam.Clear();
            _bestByTeam.Clear();
            _nameCounts.Clear();

            // The user's own "hide player colours" preference turns the whole
            // feature off locally: with vanilla bodies on screen a "Mustard got a
            // point" announcement would name a colour they cannot see.
            if (Plugin.ShowPlayerColors != null && !Plugin.ShowPlayerColors.Value) return;

            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null) return;

            foreach (var p in pm.players)
            {
                if (p == null || p.gameObject == null || p.data == null) continue;
                PhotonView pv = null;
                try { pv = p.data.view; } catch { }
                if (pv == null) { try { pv = p.GetComponent<PhotonView>(); } catch { } }
                if (pv == null) continue;

                string sku;
                Color color;
                if (!TryReadEquipped(pv, out sku, out color)) continue;

                int actor = 0;
                try { actor = pv.OwnerActorNr; } catch { }
                int team = p.TeamID;

                Entry cur;
                // ── The "coin flip", made deterministic ──
                // Sid asked for a coin flip when both members of a team have a
                // colour. A real random would give the two players DIFFERENT
                // announcements, so the tie-break is the lowest Photon
                // ActorNumber: server-assigned, identical on every client, stable
                // for the room's lifetime, and always present (unlike a steam id,
                // which rides a property that can be missing).
                if (_bestByTeam.TryGetValue(team, out cur) && cur != null && cur.Actor <= actor) continue;

                string ownerName = null;
                try { ownerName = NametagStyler.Clean(pv.Owner != null ? pv.Owner.NickName : null); }
                catch { }
                if (string.IsNullOrEmpty(ownerName)) ownerName = "P" + p.PlayerID;
                if (ownerName.Length > 14) ownerName = ownerName.Substring(0, 14);

                _bestByTeam[team] = new Entry
                {
                    Actor = actor,
                    Sku = sku,
                    Color = color,
                    OwnerName = ownerName,
                };
            }

            if (_bestByTeam.Count == 0) return;

            // How many DISTINCT teams claim each colour name? Two teams wearing
            // "Mustard" both get "(Owner)" appended so the announcement can never
            // be ambiguous about which side scored.
            foreach (var kv in _bestByTeam)
            {
                string nm = DisplayNameForSku(kv.Value.Sku);
                if (string.IsNullOrEmpty(nm)) continue;
                int n;
                _nameCounts.TryGetValue(nm, out n);
                _nameCounts[nm] = n + 1;
            }

            foreach (var kv in _bestByTeam)
            {
                var e = kv.Value;
                string colorName = DisplayNameForSku(e.Sku);
                if (string.IsNullOrEmpty(colorName)) continue;   // unknown sku shape -> vanilla
                int n;
                bool shared = _nameCounts.TryGetValue(colorName, out n) && n > 1;
                var id = new TeamIdentity
                {
                    Valid = true,
                    Sku = e.Sku,
                    ColorName = colorName,
                    Name = shared ? colorName + " (" + e.OwnerName + ")" : colorName,
                    AnnounceName = shared
                        ? colorName.ToUpperInvariant() + " (" + e.OwnerName + ")"
                        : colorName.ToUpperInvariant(),
                    Color = e.Color,
                    TextColor = ReadableOnDark(e.Color),
                    OwnerActor = e.Actor,
                };
                _byTeam[kv.Key] = id;
            }
        }

        /// <summary>Read one player's equipped body colour from the replicated props.
        ///
        /// Local fallback: our OWN props are published on a stats refresh, so during
        /// the first moments of a session they can be empty while
        /// ApiClient.CachedPlayerStats already knows the answer — and
        /// PlayerColorCosmetic.DelayedApplyAll tints our body from exactly that cache.
        /// Falling back keeps our body, our name and our announcement in agreement.
        /// It is the ONLY non-replicated input, it only ever applies to the local
        /// player, and it closes the moment the publish lands.</summary>
        public static bool TryReadEquipped(PhotonView pv, out string sku, out Color color)
        {
            sku = null;
            color = Color.white;
            string hex = null;
            try
            {
                var owner = pv.Owner;
                if (owner != null && owner.CustomProperties != null)
                {
                    object v;
                    if (owner.CustomProperties.TryGetValue(PROP_SKU, out v)) sku = v == null ? null : v.ToString();
                    if (owner.CustomProperties.TryGetValue(PROP_COLOR, out v)) hex = v == null ? null : v.ToString();
                }
            }
            catch { }

            if (string.IsNullOrEmpty(sku))
            {
                bool mine = false;
                try { mine = pv.IsMine; } catch { }
                if (!mine) return false;
                var s = ApiClient.CachedPlayerStats;
                if (s == null) return false;
                sku = s.active_player_color_sku;
                hex = s.active_player_color_hex;
                if (string.IsNullOrEmpty(sku)) return false;
            }

            Color parsed;
            if (!TryParseHex(hex, out parsed)) return false;
            color = parsed;
            return true;
        }

        private static bool TryParseHex(string hex, out Color color)
        {
            color = Color.white;
            if (string.IsNullOrEmpty(hex)) return false;
            if (hex[0] == '#') hex = hex.Substring(1);
            if (hex.Length != 6) return false;
            try
            {
                int r = Convert.ToInt32(hex.Substring(0, 2), 16);
                int g = Convert.ToInt32(hex.Substring(2, 2), 16);
                int b = Convert.ToInt32(hex.Substring(4, 2), 16);
                color = new Color(r / 255f, g / 255f, b / 255f, 1f);
                return true;
            }
            catch { return false; }
        }

        // ── Reflection helpers ────────────────────────────────────────────────
        // The csproj deliberately references NEITHER UnityEngine.UI NOR TMPro
        // (learning #15), so uGUI Image and TMP label colours are reached by name.

        private static readonly Dictionary<Type, PropertyInfo> _colorProps = new Dictionary<Type, PropertyInfo>();

        private static PropertyInfo ColorPropFor(Type t)
        {
            if (t == null) return null;
            PropertyInfo pi;
            if (_colorProps.TryGetValue(t, out pi)) return pi;
            pi = null;
            try { pi = t.GetProperty("color", BindingFlags.Public | BindingFlags.Instance); }
            catch { }
            if (pi != null && (pi.PropertyType != typeof(Color) || !pi.CanWrite)) pi = null;
            _colorProps[t] = pi;
            return pi;
        }

        /// <summary>Set <c>.color</c> on any component that exposes it (uGUI Graphic,
        /// TMP_Text). Returns the previous value through <paramref name="previous"/>.</summary>
        public static bool TrySetComponentColor(Component c, Color value, out Color previous)
        {
            previous = Color.white;
            if (c == null) return false;
            var pi = ColorPropFor(c.GetType());
            if (pi == null) return false;
            try
            {
                previous = (Color)pi.GetValue(c, null);
                pi.SetValue(c, value, null);
                return true;
            }
            catch { return false; }
        }

        /// <summary>First uGUI Image under <paramref name="root"/> (mirrors vanilla's
        /// own <c>GetComponentInChildren&lt;Image&gt;()</c> without the reference).</summary>
        public static Component FindImage(Transform root)
        {
            return FindImage(root, includeInactive: false);
        }

        /// <summary>Find the uGUI Image under <paramref name="root"/>.
        ///
        /// Aug 7: the default is now includeInactive:FALSE so this matches
        /// vanilla's own `GetComponentInChildren&lt;Image&gt;()` semantics
        /// exactly. It previously searched INACTIVE children too, which is a
        /// different object set — a dot whose hierarchy contains a disabled
        /// Image ahead of the visible one had the disabled one recoloured and
        /// the player saw no change at all. Any site that genuinely wants the
        /// inactive ones must ask for them explicitly.</summary>
        public static Component FindImage(Transform root, bool includeInactive)
        {
            if (root == null) return null;
            try
            {
                // Codex Aug-7 (MEDIUM): this used `GetType().Name == "Image"`,
                // which is EXACT type-name equality and therefore rejects every
                // SUBCLASS of Image — including `ProceduralImage`
                // (UnityEngine.UI.ProceduralImage, used across ROUNDS' own UI,
                // e.g. AbyssalCountdown.cs:27/:29). Vanilla's
                // GetComponentInChildren<Image>() matches subclasses, so this
                // was never the equivalent it claimed to be.
                //
                // The consequence was total, not partial: the review found a
                // real log line from this build reading
                // "round-counter dots ... painted=0 missed=1" — BOTH colour
                // surfaces were finding nothing and silently doing nothing,
                // while the one-shot diagnostic reported success. A diagnostic
                // that fires on a no-op is worse than none (#83/#286), so the
                // counter below now distinguishes "found and painted" from
                // "found nothing".
                var imageType = UIFactory.tImage;
                var comps = root.GetComponentsInChildren<Component>(includeInactive);
                foreach (var c in comps)
                {
                    if (c == null) continue;
                    if (imageType != null)
                    {
                        if (imageType.IsInstanceOfType(c)) return c;
                        continue;
                    }
                    // Fallback only if the Image type never resolved: walk the
                    // base chain by name so a subclass is still matched.
                    for (var t = c.GetType(); t != null; t = t.BaseType)
                        if (t.Name == "Image") return c;
                }
            }
            catch { }
            return null;
        }

        /// <summary>The TMP label behind a <c>UILocalizedString</c>. Reached by
        /// reflection because the property's return type is <c>TextMeshProUGUI</c> and
        /// TMPro is deliberately not a csproj reference (#15) — naming it in source
        /// would be CS0012.</summary>
        private static PropertyInfo _ulsTextProp;
        private static bool _ulsTextResolved;
        public static Component TmpOf(UILocalizedString uls)
        {
            if (uls == null) return null;
            if (!_ulsTextResolved)
            {
                _ulsTextResolved = true;
                try
                {
                    _ulsTextProp = typeof(UILocalizedString)
                        .GetProperty("Text", BindingFlags.Public | BindingFlags.Instance);
                }
                catch { }
            }
            if (_ulsTextProp == null) return null;
            try { return _ulsTextProp.GetValue(uls, null) as Component; }
            catch { return null; }
        }

        /// <summary>Current <c>.text</c> of any TMP-ish component, or null.</summary>
        public static string TextOf(Component c)
        {
            if (c == null) return null;
            try
            {
                var p = c.GetType().GetProperty("text", BindingFlags.Public | BindingFlags.Instance);
                return p == null ? null : p.GetValue(c, null) as string;
            }
            catch { return null; }
        }

        /// <summary>First TMP label at or above <paramref name="from"/> — the shape
        /// vanilla <c>PlayerName.Start</c> uses (<c>GetComponentInParent</c>).</summary>
        public static Component FindTmpInParents(Transform from)
        {
            for (Transform t = from; t != null; t = t.parent)
            {
                Component[] comps;
                try { comps = t.GetComponents<Component>(); }
                catch { continue; }
                foreach (var c in comps)
                {
                    if (c == null) continue;
                    string n = c.GetType().Name;
                    if (n == "TextMeshProUGUI" || n == "TextMeshPro") return c;
                }
            }
            return null;
        }
    }

    /// <summary>
    /// Aug 6 item 7 — the point / half-point announcement.
    ///
    /// Vanilla <c>PointVisualizer.DoShowPoints</c> (PointVisualizer.cs:233-264) picks
    /// one of four <c>LocalizedString</c> references (HalfOrange / RoundOrange /
    /// HalfBlue / RoundBlue) and colours the label with
    /// <c>PlayerSkinBank.GetPlayerSkinColors(0|1).winText</c> (:239-243). This Postfix
    /// replaces BOTH when the scoring team has a colour identity, and does nothing at
    /// all when it does not — so a lobby with no body colours equipped is byte-for-byte
    /// vanilla.
    ///
    /// Interaction with <c>PlayerSkinBank_GetPlayerSkinColors_2v2_Patch</c>
    /// (Plugin.cs:3616): that Prefix walks the call stack and remaps slot->team ONLY
    /// for body callers; PointVisualizer is deliberately NOT in its <c>_bodyCallers</c>
    /// set, so vanilla's 0/1 reaches the skin bank unchanged. We never touch that
    /// method — we overwrite the label AFTER vanilla has finished with it — so the two
    /// patches cannot fight: the 2v2 Prefix decides what the skin bank returns, and
    /// this Postfix decides what is finally drawn.
    ///
    /// <c>ResetReference(string)</c> is vanilla's own "just show this literal" entry
    /// point (UILocalizedString.cs:88-93): it clears the localized reference first, so
    /// no late <c>StringChanged</c> callback can resolve over the top of us.
    /// </summary>
    [HarmonyPatch(typeof(PointVisualizer), "DoShowPoints")]
    internal static class PointVisualizerTeamColorPatch
    {
        [HarmonyPostfix]
        private static void AfterDoShowPoints(PointVisualizer __instance,
                                              int currentOrange, int currentBlue, bool orangeWinner)
        {
            try
            {
                if (__instance == null || __instance.m_localizedText == null) return;
                int team = orangeWinner ? 0 : 1;
                TeamColorIdentity.TeamIdentity id;
                if (!TeamColorIdentity.TryGet(team, out id)) return;   // vanilla untouched

                // Same half-vs-round selection vanilla just made, from the same
                // args (DoShowPoints picks Round* when that side's point counter
                // is >1, Half* otherwise — PointVisualizer.cs:245-263). Wording
                // follows the mod's established player-facing language: two HALF
                // POINTS make a POINT (see the FfaMode class doc).
                bool roundWin = orangeWinner ? currentOrange > 1 : currentBlue > 1;
                string text = roundWin
                    ? I18n.TrF("{0} GOT A POINT", id.AnnounceName)
                    : I18n.TrF("{0} GOT HALF A POINT", id.AnnounceName);

                Apply(__instance, text, id.TextColor);
                if (Plugin.Instance != null)
                    Plugin.Instance.StartCoroutine(HoldText(__instance, text, id.TextColor));
            }
            catch (Exception ex) { VanillaFixSupport.LogError("PointVisualizerTeamColor", ex); }
        }

        private static void Apply(PointVisualizer pv, string text, Color color)
        {
            try { pv.m_localizedText.ResetReference(text); } catch { }
            try
            {
                Color ignored;
                TeamColorIdentity.TrySetComponentColor(
                    TeamColorIdentity.TmpOf(pv.m_localizedText), color, out ignored);
            }
            catch { }
        }

        /// <summary>Re-assert for a few frames in case Unity Localization delivers a
        /// stale async <c>StringChanged</c> for the reference vanilla set one frame
        /// earlier. Bounded by <c>bg.activeSelf</c>, which vanilla's <c>Close()</c>
        /// clears (PointVisualizer.cs:266-272) — DoWinSequence calls DoShowPoints(0,0)
        /// and Close() back to back, and without that guard this loop would paint the
        /// announcement back over the card-pick screen.</summary>
        private static IEnumerator HoldText(PointVisualizer pv, string text, Color color)
        {
            for (int i = 0; i < 8; i++)
            {
                yield return null;
                if (pv == null || pv.bg == null || !pv.bg.activeSelf) yield break;
                string current = null;
                try { current = TeamColorIdentity.TextOf(TeamColorIdentity.TmpOf(pv.m_localizedText)); }
                catch { }
                if (current == text) continue;
                Apply(pv, text, color);
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("PointVisualizerTeamColor", exception);
        }
    }

    /// <summary>
    /// Aug 6 item 7 — the small round-counter dots.
    ///
    /// Vanilla <c>RoundCounter.ReDraw</c> (RoundCounter.cs:99-133) colours each LIT dot
    /// with <c>GetPlayerSkinColors(0|1).winText</c> and leaves unlit dots on
    /// <c>offColor</c>. This Postfix re-paints only the lit dots, mirroring vanilla's
    /// own <c>rounds + points > i</c> condition, and only for a team that has an
    /// identity. FFA never reaches here — CompetitiveUI hides the vanilla counter and
    /// draws its own strip.
    /// </summary>
    [HarmonyPatch(typeof(RoundCounter), "ReDraw")]
    internal static class RoundCounterTeamColorPatch
    {
        [HarmonyPostfix]
        private static void AfterReDraw(RoundCounter __instance)
        {
            try
            {
                if (__instance == null) return;
                Recolor(__instance.p1Parent, 0, __instance.p1Rounds + __instance.p1Points);
                Recolor(__instance.p2Parent, 1, __instance.p2Rounds + __instance.p2Points);
            }
            catch (Exception ex) { VanillaFixSupport.LogError("RoundCounterTeamColor", ex); }
        }

        private static bool _loggedOnce;

        private static void Recolor(Transform parent, int team, int litCount)
        {
            if (parent == null || litCount <= 0) return;
            TeamColorIdentity.TeamIdentity id;
            if (!TeamColorIdentity.TryGet(team, out id)) return;
            int n = Mathf.Min(litCount, parent.childCount);
            int painted = 0, missed = 0;
            for (int i = 0; i < n; i++)
            {
                var img = TeamColorIdentity.FindImage(parent.GetChild(i));
                if (img == null) { missed++; continue; }
                Color ignored;
                TeamColorIdentity.TrySetComponentColor(img, id.TextColor, out ignored);
                painted++;
            }
            /* Aug 7: one-shot proof that this surface actually BINDS.
             *
             * Sid reported the point ANNOUNCEMENT showing his colour while the
             * top-left counter stayed vanilla blue/orange — and this patch was
             * already live, so it was running and changing nothing visible.
             * The cause was FindImage searching INACTIVE children too, which
             * is a different object set from vanilla's own
             * GetComponentInChildren<Image>() (RoundCounter.cs:105/:121): on a
             * dot whose hierarchy holds a disabled Image first, the disabled
             * one got the colour. FindImage is now active-only.
             *
             * `missed` is the tell if it ever regresses: dots with no Image
             * found at all means the hierarchy changed, not that the colour
             * is wrong (#83/#286 — prove the surface is reached before
             * debugging its logic). */
            if (!_loggedOnce && (painted > 0 || missed > 0))
            {
                _loggedOnce = true;
                Plugin.Log?.LogInfo(
                    $"[TEAMCOLOR] round-counter dots team={team} painted={painted} missed={missed} " +
                    $"color={id.ColorName}");
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("RoundCounterTeamColor", exception);
        }
    }

    /// <summary>
    /// Aug 6 item 7 — the in-game nametag follows the body colour.
    ///
    /// Vanilla <c>PlayerName.Start</c> (PlayerName.cs:7-22) writes the owner's
    /// NickName into the TMP label in its parents. The name COLOUR has until now come
    /// only from the <c>nametag_color_*</c> / neon / rainbow / gradient cosmetics,
    /// which <see cref="NametagStyler"/> bakes into the NickName as inline
    /// <c>&lt;color=&gt;</c> rich text.
    ///
    /// PRECEDENCE (deliberate): a paid nametag colour always wins. We only tint the
    /// label when the published NickName carries NO <c>&lt;color</c> tag, which covers
    /// every name-recolouring sku in one test — plain colours, neon, rainbow and the
    /// gradients all emit colour tags. Inline tags would override the base vertex
    /// colour anyway, so this is belt AND braces.
    ///
    /// Local render only (like the glow and typeface renderers): nothing is written to
    /// the NickName, so unmodded clients are unaffected and no state can leak into
    /// another room.
    /// </summary>
    [HarmonyPatch(typeof(PlayerName), "Start")]
    internal static class PlayerNameTeamColorPatch
    {
        [HarmonyPostfix]
        private static void AfterStart(PlayerName __instance)
        {
            try
            {
                if (__instance == null) return;
                if (__instance.GetComponent<TeamColorNametagTint>() != null) return;
                __instance.gameObject.AddComponent<TeamColorNametagTint>();
                // Diagnostic, capped: PlayerName lives on a prefab and nothing in
                // vanilla CALLS it, so "is the in-game nametag actually this
                // component" is a claim only a log line can settle (#83/#286 —
                // establish reachability before debugging behaviour).
                VanillaFixSupport.DiagLimited(
                    "TeamColorNametag-attached",
                    "TeamColorNametagTint attached to a PlayerName label", 6);
            }
            catch (Exception ex) { VanillaFixSupport.LogError("PlayerNameTeamColor", ex); }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("PlayerNameTeamColor", exception);
        }
    }

    /// <summary>Re-asserts the nametag tint on a slow tick so equipping/unequipping a
    /// body colour mid-match is picked up, and restores the original colour when the
    /// player unequips. Lives on the PlayerName GameObject, so it dies with the player
    /// — no lifetime bookkeeping, nothing to strand (#16).</summary>
    internal class TeamColorNametagTint : MonoBehaviour
    {
        private Component _label;
        private PhotonView _view;
        private global::Player _player;
        private bool _captured;
        private Color _original;
        private bool _applied;
        private float _next;

        private void Start()
        {
            try
            {
                _label = TeamColorIdentity.FindTmpInParents(transform);
                _view = GetComponentInParent<PhotonView>();
                _player = GetComponentInParent<global::Player>();
            }
            catch { }
            _next = 0f;
        }

        private void Update()
        {
            if (Time.unscaledTime < _next) return;
            _next = Time.unscaledTime + 0.5f;
            if (_label == null || _player == null) return;
            try
            {
                bool wantTint = false;
                Color tint = Color.white;

                // An explicitly equipped nametag colour wins — see the class doc.
                string nick = null;
                try { nick = _view != null && _view.Owner != null ? _view.Owner.NickName : null; }
                catch { }
                bool explicitNameColor = !string.IsNullOrEmpty(nick)
                    && nick.IndexOf("<color", StringComparison.OrdinalIgnoreCase) >= 0;

                if (!explicitNameColor && Plugin.ShowPlayerColors != null && Plugin.ShowPlayerColors.Value)
                {
                    // The name follows THIS player's OWN equipped colour, never the
                    // team's. Sid allowed a colourless teammate to "adopt the actual
                    // body colour of their teammate OR just adopt the team name" —
                    // adopting only the NAME is the option taken, because
                    // PlayerColorCosmetic leaves that teammate's BODY vanilla and a
                    // nametag in a colour their body is not would read as a bug.
                    string sku;
                    Color own;
                    if (_view != null && TeamColorIdentity.TryReadEquipped(_view, out sku, out own))
                    {
                        wantTint = true;
                        tint = TeamColorIdentity.ReadableOnDark(own);
                    }
                }

                if (wantTint)
                {
                    Color prev;
                    if (TeamColorIdentity.TrySetComponentColor(_label, tint, out prev))
                    {
                        if (!_captured) { _original = prev; _captured = true; }
                        _applied = true;
                    }
                }
                else if (_applied && _captured)
                {
                    Color ignored;
                    TeamColorIdentity.TrySetComponentColor(_label, _original, out ignored);
                    _applied = false;
                }
            }
            catch { }
        }
    }

    /// <summary>
    /// Aug 7 item 3 — the in-game CARD ABBREVIATION BAR follows the owner's
    /// equipped body colour.
    ///
    /// Sid: "can you now make the card abbreviation preview box showing in the
    /// top right ingame mustard as well?"
    ///
    /// ── What this is painting ─────────────────────────────────────────────
    /// Vanilla `CardBarHandler.AddCard(int teamId, CardInfo card)`
    /// (CardBarHandler.cs:126-129) forwards to `cardBars[teamId].AddCard(...)`,
    /// and despite the parameter name that index is a PLAYER ID — both call
    /// sites pass `playerToUpgrade.PlayerID` (ApplyCardStats.cs:50 and :61).
    /// `CardBar.AddCard` (CardBar.cs:43-64) clones its `m_source` template,
    /// truncates the card name to two characters, and inserts the clone at
    /// visual index 0.
    ///
    /// The orange/blue of those boxes comes from NOWHERE IN CODE: a grep of the
    /// whole decompile finds no `GetPlayerSkinColors` call in any CardBar file,
    /// and `SetTeamColor` only handles Sprite/Mesh/Line renderers and particle
    /// systems, never a uGUI Image. It is serialized prefab data on the
    /// template. So there is no vanilla call to patch — the colour has to be
    /// painted onto the instantiated buttons.
    ///
    /// ── Why a periodic sweep rather than a Postfix on AddCard ─────────────
    /// The buttons are destroyed wholesale by `CardBar.ClearBar()`
    /// (CardBar.cs:33-41) on every game reset (GM_ArmsRace.cs:398,
    /// PlayerManager.cs:425), the 2v2/1v2 bars are CLONES the mod builds at
    /// runtime (Plugin.cs:2754-2789), and FFA re-routes every pick into
    /// bars[0] through a Prefix that skips vanilla entirely
    /// (FfaMode.cs:2821-2840). A paint-the-new-clone Postfix would miss all
    /// three. A cheap idempotent sweep survives every one of them.
    ///
    /// ── Per-PLAYER, not per-team ──────────────────────────────────────────
    /// Uses <see cref="TeamColorIdentity.TryReadEquipped"/> against the owning
    /// player's own view, NOT `TryGet(team)`. In 2v2 the team identity resolves
    /// to the lowest-ActorNumber holder, so a team-keyed lookup would paint
    /// both teammates' bars with one player's colour.
    ///
    /// Inert when: the feature is off, nobody has a colour equipped, or the
    /// handler/bars are absent. Never touches a bar whose owner has no colour,
    /// so vanilla bars keep their authored hue.
    /// </summary>
    internal static class CardBarTeamColor
    {
        private static float _next;
        private const float TICK_SECONDS = 0.5f;
        private static bool _loggedOnce;

        /// <summary>Driven from the persistent behaviour's Update (BepInEx 5
        /// never calls Plugin.Update — #17).</summary>
        internal static void Tick()
        {
            if (Time.unscaledTime < _next) return;
            _next = Time.unscaledTime + TICK_SECONDS;
            try
            {
                /* Codex Aug-7 r2 (LOW): returning here left cards that were
                 * ALREADY tinted stuck in the old colour when the player turned
                 * the setting off mid-match — bodies revert instantly, so the
                 * bar disagreed with everything else until it next cleared.
                 * Restore first, then return. `_tinted` is only non-empty if we
                 * actually painted something, so this is a no-op in the common
                 * case. */
                bool showColors = Plugin.ShowPlayerColors == null || Plugin.ShowPlayerColors.Value;
                if (!showColors)
                {
                    RestoreTinted();
                    return;
                }
                if (!PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode) { RestoreTinted(); return; }
                var cbh = CardBarHandler.instance;
                if (cbh == null || cbh.cardBars == null) return;
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return;

                // Codex Aug-7 (MEDIUM): PlayerID is the bar index in 1v1/2v2/1v2,
                // but NOT in FFA. FfaMode's CardBarHandler.AddCard Prefix
                // (FfaMode.cs:2829-2835) skips every non-local player and routes
                // the LOCAL fighter's cards into bars[0] regardless of their
                // PlayerID — so indexing by PlayerID there either skips the only
                // populated bar or paints it with the wrong player's colour.
                bool ffa = false;
                try { ffa = FfaMode.EngineActive(); } catch { }
                foreach (var p in pm.players)
                {
                    if (p == null || p.gameObject == null || p.data == null) continue;
                    int pid = p.PlayerID;
                    int barIndex = pid;
                    if (ffa)
                    {
                        // FFA renders ONLY the local fighter's bar, at index 0.
                        bool isLocal = false;
                        try { isLocal = p.data.view != null && p.data.view.IsMine; } catch { }
                        if (!isLocal) continue;
                        barIndex = 0;
                    }
                    if (barIndex < 0 || barIndex >= cbh.cardBars.Length) continue;
                    var bar = cbh.cardBars[barIndex];
                    if (bar == null) continue;

                    PhotonView pv = null;
                    try { pv = p.data.view; } catch { }
                    if (pv == null) { try { pv = p.GetComponent<PhotonView>(); } catch { } }
                    if (pv == null) continue;

                    string sku; Color equipped;
                    if (!TeamColorIdentity.TryReadEquipped(pv, out sku, out equipped))
                    {
                        // Codex Aug-7 r3 (LOW): this used to `continue`, which is
                        // correct for "never had a colour" and WRONG for "just
                        // unequipped one" — the two are indistinguishable here,
                        // and in the second case the cards this sweep already
                        // painted stayed tinted for the rest of the room while
                        // the body reverted immediately. Restoring this bar's own
                        // children covers the unequip without needing per-player
                        // bookkeeping, and is a no-op when nothing was painted.
                        RestoreTintedUnder(bar.transform);
                        continue;
                    }
                    Color tint = TeamColorIdentity.ReadableOnDark(equipped);

                    // Paint every live button under this bar. Index 0 of the
                    // bar is the hidden m_source TEMPLATE (CardBar.cs:30) —
                    // painting it would leak the colour into the next clone
                    // made from it, so only ACTIVE children are touched, which
                    // is also what the player can actually see.
                    var t = bar.transform;
                    int painted = 0, noImage = 0;
                    for (int i = 0; i < t.childCount; i++)
                    {
                        var child = t.GetChild(i);
                        if (child == null || !child.gameObject.activeSelf) continue;
                        var img = TeamColorIdentity.FindImage(child);
                        if (img == null) { noImage++; continue; }
                        Color prev;
                        TeamColorIdentity.TrySetComponentColor(img, tint, out prev);
                        // Remember the ORIGINAL only the first time we touch
                        // this Image — re-recording on a later sweep would save
                        // our own tint as the "original".
                        int iid = img.GetInstanceID();
                        if (!_tinted.ContainsKey(iid))
                            _tinted[iid] = new KeyValuePair<Component, Color>(img, prev);
                        painted++;
                    }

                    // Codex Aug-7: the old version of this line announced
                    // "tint active" merely because the sweep RAN, and it was
                    // firing on a build where FindImage matched nothing at all.
                    // A diagnostic that reports success on a no-op actively
                    // misleads (#83/#286), so it now reports what was PAINTED
                    // and only claims success when that is non-zero.
                    if (!_loggedOnce && (painted > 0 || noImage > 0))
                    {
                        _loggedOnce = true;
                        Plugin.Log?.LogInfo(
                            $"[TEAMCOLOR] card bar pid={pid} bar={barIndex} sku={sku} " +
                            $"painted={painted} noImage={noImage} " +
                            (painted > 0 ? "— bound OK" : "— NOTHING PAINTED, surface not bound"));
                    }
                }
            }
            catch (Exception ex)
            {
                if (!_loggedOnce)
                {
                    _loggedOnce = true;
                    Plugin.Log?.LogWarning($"[TEAMCOLOR] card bar tint failed: {ex.Message}");
                }
            }
        }

        /// <summary>Images this sweep has painted, with the colour they had
        /// BEFORE we touched them, so the tint can be undone when the player
        /// disables the feature or leaves the room. Keyed by instance id;
        /// entries for destroyed Images are dropped on restore.</summary>
        private static readonly Dictionary<int, KeyValuePair<Component, Color>> _tinted =
            new Dictionary<int, KeyValuePair<Component, Color>>();

        private static void RestoreTinted()
        {
            if (_tinted.Count == 0) return;
            foreach (var kv in _tinted)
            {
                try
                {
                    var comp = kv.Value.Key;
                    if (comp == null) continue;   // Unity fake-null: bar cleared
                    Color ignored;
                    TeamColorIdentity.TrySetComponentColor(comp, kv.Value.Value, out ignored);
                }
                catch { }
            }
            _tinted.Clear();
        }

        /// <summary>Undo the tint on the Images under one bar only, and forget
        /// them. Used when a player turns out to have no equipped colour, where
        /// a global restore would wrongly revert everyone else's still-valid
        /// tint. Also drops entries whose Image Unity has destroyed — without
        /// that sweep, _tinted accumulates dead card buttons every rematch
        /// (Codex Aug-7 r3) since nothing else prunes it inside a room.</summary>
        private static void RestoreTintedUnder(Transform bar)
        {
            if (bar == null || _tinted.Count == 0) return;
            List<int> drop = null;
            for (int i = 0; i < bar.childCount; i++)
            {
                var child = bar.GetChild(i);
                if (child == null) continue;
                var img = TeamColorIdentity.FindImage(child);
                if (img == null) continue;
                int iid = img.GetInstanceID();
                KeyValuePair<Component, Color> rec;
                if (!_tinted.TryGetValue(iid, out rec)) continue;
                try
                {
                    Color ignored;
                    TeamColorIdentity.TrySetComponentColor(img, rec.Value, out ignored);
                }
                catch { }
                (drop ?? (drop = new List<int>())).Add(iid);
            }
            // Prune destroyed Images in the same pass — cheap, and it bounds the
            // dictionary across a long sitting.
            foreach (var kv in _tinted)
                if (kv.Value.Key == null)
                    (drop ?? (drop = new List<int>())).Add(kv.Key);
            if (drop != null)
                foreach (int iid in drop) _tinted.Remove(iid);
        }

        internal static void Reset()
        {
            _next = 0f;
            _loggedOnce = false;
            _tinted.Clear();
        }
    }
}
