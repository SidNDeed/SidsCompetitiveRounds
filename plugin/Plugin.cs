using BepInEx;
using BepInEx.Bootstrap;
using BepInEx.Configuration;
using BepInEx.Logging;
using HarmonyLib;
using Photon.Pun;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using InControl;
using UnityEngine;
using UnityEngine.Rendering.PostProcessing;

namespace CompetitiveRounds
{
    [BepInPlugin(ModId, ModName, ModVersion)]
    [BepInProcess("Rounds.exe")]
    public class Plugin : BaseUnityPlugin
    {
        public const string ModId = "com.competitiverounds.mod";
        public const string ModName = "Competitive ROUNDS";
        public const string ModVersion = "1.41.0";   // Sep 25: v1.41.0 BETA for testers - the v1.41.0 client lane merged with main (c2d14ad); no release, tag or upload until the testers have seen it. At 1.41.0 the server admits this client to non-default room rules (ROOM_RULES_MIN_VERSION); every other floor is met by 1.40.3 already. Previous (1.40.3, Sep 8-9): the ranked room's region. A client refreshed its Photon ping map only when older than 300 s while the server refuses any map stamped more than 180 s before the room is issued, and the one trigger that could refresh mid-queue required a Photon connection the main menu does not have -- so the maps that were supposed to decide the room were routinely too old to be used. A ranked-only session was worse off still: PUN builds its region list only from an OpGetRegions response, which a forced ranked connect skips, so those players had no list to ping at all and the measurement never ran once. The client now refreshes on a 60 s join threshold and a 90 s queue cadence that no longer asks Photon's connection state, and fetches its own region list from the NameServer when PUN has none. Also: a region left behind by the Sandbox's offline mode is no longer reported as the region you are on. Bug 351 (the thicker-menu-text toggle bricking chat) and bug 350 (a spectator's point orb opening already full) ride along, with match reports no longer failing on untyped interval parameters. Previous (1.40.2, Sep 8): one Session button per sitting; the Grow competitive clock 240 -> 120 FPS. Floors riding this release: DANCES_MIN_VERSION=1.39.7, MUSIC_PURCHASE_MIN_VERSION=1.40.0 -- both satisfied.
        public const string RequiredGameVersion = "1.1.2";

        // API endpoint migration (2026-07-26). LegacyApiUrl is the exact string
        // every pre-TLS install has written into its BepInEx config; it is matched
        // literally by the one-time migration in Awake and must NEVER change. Plain
        // 8443 keeps serving until MIN_MOD_VERSION is raised past this release.
        internal const string LegacyApiUrl  = "http://competitive-rounds.duckdns.org:8443";
        internal const string DefaultApiUrl = "https://competitive-rounds.duckdns.org:8444";

        internal static ManualLogSource Log;
        internal static CompetitiveRoundsBehaviour Instance;
        internal static Harmony HarmonyInstance;

        // Config entries
        internal static ConfigEntry<string> ApiBaseUrl;
        internal static ConfigEntry<string> ModLanguage;      // L10n v1 (D2)
        internal static ConfigEntry<bool> PseudoLocaleEnabled;
        // Security A2: admin HMAC secret — NEVER compiled into the DLL. Empty
        // for every normal player; a server admin pastes the value (delivered
        // out-of-band, matches the server's ADMIN_HMAC_SECRET) into their own
        // BepInEx cfg. Signing admin actions with the shipped mod secret let
        // anyone who unzipped the mod forge admin requests.
        internal static ConfigEntry<string> AdminHmacSecret;
        internal static ConfigEntry<bool> HttpsMigrationDone;
        internal static ConfigEntry<float> SecureRetryMinutes;   // [API] board row 27: minutes between secure-route checks while the session runs on the backup
        internal static ConfigEntry<bool> RankedEnabled;
        internal static ConfigEntry<bool> RankedDisabledByConsent;
        internal static ConfigEntry<bool> ShowNotifications;
        internal static ConfigEntry<bool> ShowFps;
        internal static ConfigEntry<bool> CapFpsUnfocused;
        internal static ConfigEntry<bool> MuteAudioInBackground;
        internal static ConfigEntry<bool> DeepIdleUnfocused;
        internal static ConfigEntry<bool> BroadcastIdleFpsCap;
        internal static ConfigEntry<int> BroadcastFpsCap;
        internal static ConfigEntry<bool> BroadcastWindowed1080;
        internal static ConfigEntry<bool> ShowRegionPing;
        internal static ConfigEntry<bool> ShowRoomRulesIndicator;   // [UI] item 22: the standing room-rules strip, default on
        internal static ConfigEntry<bool> ShowInactiveOnBoards;   // [UI] item d: default off -- boards hide players the server counts as inactive (its leaderboard_active_days)
        internal static ConfigEntry<bool> LagNoticesEnabled;   // [Network] LagNotices — Release B §4, default off
        // [Data] AutoLogUpload — v1.41.0 item (a). Opt-IN, default off. Named
        // ...Enabled rather than AutoLogUpload so the entry and the
        // AutoLogUpload class that reads it cannot be mistaken for each other.
        internal static ConfigEntry<bool> AutoLogUploadEnabled;
        // Streamed-playback measurement (MusicStreamProbe), both in [Music].
        // Opt-in, default off; the command names the track and the mode.
        internal static ConfigEntry<bool> MusicProbeEnabled;
        internal static ConfigEntry<string> MusicProbeRun;
        internal static ConfigEntry<string> MusicTestScript;
        internal static ConfigEntry<bool> ShowIngameChat;
        // Bug 211/213 (Sid's chosen design): M cycles the in-game chat overlay
        // through Normal -> Pinned -> Muted. The on/off half of that state IS
        // ShowIngameChat (so the Settings toggle and the hotkey can never
        // disagree); this is only the "pinned" half. Normal = (show, !pinned),
        // Pinned = (show, pinned), Muted = (!show, !pinned).
        internal static ConfigEntry<bool> ChatOverlayPinned;
        // Item 4: how long a chat line stays fully opaque in the overlay before
        // the (still hardcoded) 10s fade begins. Float so the value can be
        // hand-edited in the cfg to anything; the in-game control (item 13: a
        // slider since the settings page reorganisation) is quantised to a
        // fixed set of stops, CHAT_TTL_CYCLE, and writes only those.
        // 0 (and any value <= 0) is a MODE, not a duration — see
        // ChatOverlayHiddenDuringPlay.
        internal static ConfigEntry<float> ChatOverlaySeconds;
        internal static ConfigEntry<bool> ShowTrails;
        internal static ConfigEntry<bool> ShowBlockDebug;
        internal static ConfigEntry<bool> ShowPlayerColors;
        internal static ConfigEntry<bool> ShowInputOverlay;
        // Item 19 (two default avatars): the setting (three keys) and the ONE
        // remembered value, the pre-switch own selection (-1 = none).
        internal static ConfigEntry<bool> AvatarAutoSwitch;
        internal static ConfigEntry<int> AvatarModdedPreset;
        internal static ConfigEntry<int> AvatarVanillaPreset;
        internal static ConfigEntry<int> AvatarHomeSlot;
        // v1.32 items 7+8 — standalone accessibility/FPS toggles. Deliberately
        // NOT under the Performance master switch: these are user preferences
        // that should survive a perf-master flip (map note, settings tab).
        internal static ConfigEntry<bool> ScreenShakeEnabled;      // legacy, migration source only
        internal static ConfigEntry<string> ScreenShakeStrength;
        // Sept 10 (Player Cards): the persisted pack-open intent (PlayerCardsUI).
        internal static ConfigEntry<string> PcOpenIntent;
        internal static ConfigEntry<bool> MapLightingEnabled;
        internal static ConfigEntry<bool> MapShadowsEnabled;
        internal static ConfigEntry<bool> AnimatedCosmetics;
        internal static ConfigEntry<bool> ChromaticAberrationEnabled;
        // Bloom strength: "Full" | "Reduced" | "Off". String, not an enum —
        // TournamentDateFormat is the codebase's 3-state precedent and a plain
        // string round-trips through BepInEx's TOML without a converter.
        internal static ConfigEntry<string> BloomStrength;
        internal static ConfigEntry<bool> AutoRequeueOnMatchmakingBug;
        // Performance pass — master + 7 per-patch flags so users can disable
        // any individual port without giving up the rest. Mirrors the
        // granularity the original "Performance Improvements" mod offered.
        internal static ConfigEntry<bool> PerfOptimizations;
        internal static ConfigEntry<bool> PerfStunPlayerNullGuard;
        internal static ConfigEntry<bool> PerfDespawnOffscreenBullets;
        internal static ConfigEntry<bool> PerfSwallowHitSoundNREs;
        internal static ConfigEntry<bool> PerfSwallowEdgeBounceNREs;
        internal static ConfigEntry<bool> PerfSkipMenuUpdateInMatch;
        // v1.26.9 — user-noticeable batch (cap-style perf wins).
        internal static ConfigEntry<bool> PerfBulletHitParticleCap;
        internal static ConfigEntry<bool> PerfClampObjectPoolInit;
        // PerfPauseCardPickParticles REMOVED v1.28.3 — the "skin preview particle
        // system" it paused IS the picker's body; pausing it the frame it spawns
        // rendered the pick-phase character invisible (bug #29).
        // Preferred timezone for tournament time display. Values: "Local" (use OS),
        // "UTC", or an IANA / Windows tz ID that TimeZoneInfo.FindSystemTimeZoneById
        // resolves. Persisted so it survives restarts; applies only to tournament UI.
        internal static ConfigEntry<string> TournamentTimezone;
        // Preferred date/time format. Values:
        //   "ISO" = 2026-04-24 14:30       (unambiguous, ASCII, 24h)
        //   "US"  = Sat 04/24 2:30 PM      (Anglophone default)
        //   "EU"  = Sat 24/04 14:30        (most of Europe + others)
        // All formats emit ASCII-only using CultureInfo.InvariantCulture so the
        // Gravity SDF font renders them cleanly regardless of OS locale.
        internal static ConfigEntry<string> TournamentDateFormat;
        internal static ConfigEntry<string> UiDateFormat;       // MDY | DMY | YMD (Sid Aug-3 item 9)
        internal static ConfigEntry<string> RatingGraphAxisMode; // updates | calendar | since_first (Sept 6 item f) — RatingGraphAxis.cs
        internal static ConfigEntry<bool> UiHeavyFont;          // bug #159: thicker SCR menu text
        internal static ConfigEntry<float> UiFontWeight;        // how much thicker (SDF weight delta)
        internal static ConfigEntry<string> ChatDisplayChannel; // all | global | es | ru | uk | sv (item 5)
        internal static ConfigEntry<string> ChatSendChannel;    // "" = follow language | global | es | ru | uk | sv (item 13)
        // Pipe-delimited list of muted display names — local mute, doesn't leave the client.
        // Mutated via /mute and /unmute commands typed in the F5 chat input.
        internal static ConfigEntry<string> MutedChatNames;
        // Tri-state "" (unset — ask at launch) / "granted" / "denied".
        // Gates ALL outbound API traffic except the mod-version probe and consent-revocation calls.
        internal static ConfigEntry<string> DataConsent;

        // ── Music (ai-collab/music-feature design v3) ────────────────────
        // Stored as the DESELECTED track set (albumSku/trackIndex pairs,
        // comma-delimited) so newly shipped content defaults to selected.
        internal static ConfigEntry<string> MusicDeselected;
        internal static ConfigEntry<bool> MusicShuffle;
        internal static ConfigEntry<bool> MusicLoop;
        internal static ConfigEntry<int> MusicVolume;        // engine-local %, on top of the game's own music slider
        internal static ConfigEntry<bool> MusicVolumeMigrated; // one-shot marker for the 1.41.0 MusicVolume migration (MusicLevels.MigratedPercent)
        internal static ConfigEntry<bool> MenuMusicEnabled;  // legacy bool (§8) — superseded by MenuMusicMode, kept per #190
        internal static ConfigEntry<string> MenuMusicMode;   // "vanilla" / "custom" / "silent" (Sept 2 feedback)
        internal static ConfigEntry<bool> MenuMusicModeMigrated; // one-shot marker for the MenuMusicEnabled→MenuMusicMode migration
        internal static ConfigEntry<bool> MusicCreditToast;  // opt-in (§8)

        // ── SCR Broadcast (ai-collab/broadcast-architecture.md) ──────────
        // Enabled gates ONLY the director (§3a). The §2c service-account
        // fence and §7.1 log masking are IDENTITY-latched inside
        // BroadcastMode and cannot be turned off here by design.
        internal static ConfigEntry<bool> BroadcastEnabled;
        internal static ConfigEntry<string> BroadcastStatusPath;   // §3b lease file
        internal static ConfigEntry<bool> BroadcastHideChatPane;   // broadcast seat only
        internal static ConfigEntry<bool> BroadcastCustomMusic;    // broadcast seat only — custom album autoplay + credit (music v3 §7)
        internal static ConfigEntry<string> BroadcastTestMapSkin;  // broadcast seat only — map-skin test lever
        internal static ConfigEntry<bool> BroadcastTestMapSkinSandbox;    // broadcast seat only — auto LOCAL→SANDBOX for the lever
        internal static ConfigEntry<int> BroadcastTestMapSkinTourSeconds; // broadcast seat only — advance a comma list every N s
        internal static ConfigEntry<string> BroadcastTestOpenTab;        // broadcast seat only — "tab[:shopScroll]" opens the F5 overlay there
        internal static ConfigEntry<string> BroadcastTestQuit;           // broadcast seat only — any new non-empty value quits the game (Sept 6)
        internal static ConfigEntry<string> BroadcastTestPress;          // broadcast seat only -- "ObjectName[:nonce]" presses a named F5 overlay button once per new value (board row 27 witnesses)
        internal static ConfigEntry<string> BroadcastTestSecureUrl;      // broadcast seat only -- an https address the secure-route check probes instead of the default one (board row 27 witnesses)
        internal static ConfigEntry<string> BroadcastTestBackupUrl;      // broadcast seat only -- a plaintext address that replaces the backup for one launch: the local witness harness of board row 27 round 2
        internal static ConfigEntry<string> BroadcastTestQueueReport;    // broadcast seat only -- each new value posts BepInEx/config/scr-portal-report.json as a match report through the real send and outbox path (board row 27 round 2 harness)
        internal static ConfigEntry<string> BroadcastTestStaleToken;     // broadcast seat only -- each new value replaces the held session token with one the server never issued (board row 27 round 2 witness)
        internal static ConfigEntry<string> BroadcastTestGstatsSentinel; // broadcast seat only — any new value runs the cr_gstats W1-sentinel self-test once
        internal static ConfigEntry<string> BroadcastTestReporterElectionSentinel; // broadcast seat only — any new value runs the 2v2 DC reporter-election self-test once
        internal static ConfigEntry<string> BroadcastTestAutoLogConsentSentinel; // broadcast seat only — any new value runs the automatic-log consent-abort self-test once
        internal static ConfigEntry<string> BroadcastTestChatRevokeSentinel; // broadcast seat only -- any new value runs the consent-revoke chat-discard self-test once
        internal static ConfigEntry<string> BroadcastTestHeartbeatAbortSentinel; // broadcast seat only -- any new value runs the aborted-send heartbeat self-test once
        internal static ConfigEntry<string> BroadcastTestPresetSlotSentinel; // broadcast seat only -- any new value runs the provisional preset-slot count self-test once
        internal static ConfigEntry<string> BroadcastTestTeamGameNumberSentinel; // broadcast seat only -- any new value runs the 2v2 game-number self-test once
        internal static ConfigEntry<string> BroadcastTestPlayerCards;   // broadcast seat only — any new value seeds synthetic Player Card tiles (Sept 10)
        internal static ConfigEntry<int> PortraitPreset;                 // Player Cards (v22 section 6): -1 = follow the selected character, 0..PortraitRender.PresetSlotCount()-1 = the saved face slot (#370 — NOT 0-9; playerFaces has ten entries but only eight are authorable). Anything outside that range resolves to -1, and is rewritten to -1 once the real slot count has been discovered — it is NOT clamped to the top slot (that silently re-rendered someone else's face onto the card).
        internal static ConfigEntry<string> BinderSort;                  // Player Cards (item 20): the binder order, stored as the BinderSortRules.Mode member NAME (never the ordinal, which changes meaning when a mode is inserted). Written by the header button alone; an unrecognised name falls back to Name.
        internal static ConfigEntry<bool> BroadcastTestSilence;          // broadcast seat only, offline/sandbox — apply 3s of silence to a bot for indicator verification
        internal static ConfigEntry<string> BroadcastTestQuickChatWheel; // broadcast seat only — pin the quick-chat wheel open for layout screenshots
        internal static ConfigEntry<string> BroadcastTestDance;         // broadcast seat only — "wheel" | "preview:<sku>" | "play:<idx>" dance verification
        internal static ConfigEntry<string> BroadcastTestRoomRules;     // broadcast seat only, offline: latch a rules pair (ff=X;sc=Y) so the standing room-rules strip can be verified
        internal static ConfigEntry<float> BroadcastShowcaseMetricSeconds; // broadcast seat only -- board row 31: the idle showcase's dwell per Compare category
        internal static ConfigEntry<string> BroadcastTestShowcase;         // broadcast seat only -- any new value plays one showcase rotation with the stream-live gate lifted
        internal static ConfigEntry<float> BroadcastSessionReportPageSeconds; // broadcast seat only -- board row 30g: the post-set session report's dwell per page
        internal static ConfigEntry<string> BroadcastTestWatchedSet;       // broadcast seat only -- a NEW spectate game id replays that recorded set through the post-set report
        internal static ConfigEntry<string> BroadcastTestSessionReport;    // broadcast seat only -- "<selector>:<key>[:<page>]" opens that set's F5 session report at a page; "close" closes it
        internal static BepInEx.Configuration.ConfigFile ConfigFileForLevers;
        // BroadcastHudOffsetX/Y retired Aug 18: the 1v1 panels moved from the
        // bottom sides to the top corners under the card bars (measured
        // anchor in BroadcastHud.TopAnchorY) — orphan cfg entries are inert.

        public static bool DataConsentGranted => DataConsent != null && DataConsent.Value == "granted";
        public static bool DataConsentAsked   => DataConsent != null && !string.IsNullOrEmpty(DataConsent.Value);

        // ── Item 4: chat-overlay message TTL ─────────────────────────────
        // Item 13: the Settings row is a SLIDER over the stops below
        // (UIFactory.CreateSlider), and it writes through
        // SetChatOverlaySeconds, which quantises to the nearest stop, so the
        // stored value is always one of them. The cycling button this
        // paragraph used to describe is gone; CycleChatOverlaySeconds stays
        // as the stepping wrapper over the same writer. Both the Settings tab
        // and the M hotkey read the same ConfigEntry, so they cannot disagree.
        //
        // The cycle is deliberately bounded, but NOT for the reason a reader
        // might assume: the overlay renders at most the last 8 entries
        // (CopyChatTail(_, 8)) out of a ring capped at CHAT_LOG_MAX = 60, so
        // panel height is bounded by those 8 lines no matter how long the TTL
        // is — a longer TTL cannot walk the panel into the HUD (#199/#245),
        // and it cannot resurrect a line the ring already evicted. 90s is the
        // ceiling simply because past that "recent messages" stops meaning
        // anything; "never fades" is the PINNED state, not a TTL value.
        //
        // ZERO IS A REAL SETTING, NOT A DEGENERATE ONE (Sid, Aug 13): 0 means
        // the overlay never shows during play at all. It is deliberately NOT
        // the same thing as the M key's Muted state — Muted also publishes a
        // marker telling the room this seat cannot read chat (bug 213), and a
        // player who simply wants a clean screen should not be advertising
        // that. So 0 hides the overlay locally and says nothing to anyone.
        //
        // The floor value must therefore be read as a MODE by the draw path,
        // never clamped up into the fade arithmetic — see
        // ChatOverlayHiddenDuringPlay, which is the single place that
        // decision lives.
        internal static readonly float[] CHAT_TTL_CYCLE = { 0f, 5f, 10f, 25f, 45f, 90f };

        /// <summary>Advance the chat-overlay TTL to the next value in
        /// CHAT_TTL_CYCLE, through SetChatOverlaySeconds. A stored value
        /// outside the cycle (hand-edited cfg) lands on the first entry, as it
        /// always has.</summary>
        public static void CycleChatOverlaySeconds()
        {
            if (ChatOverlaySeconds == null) return;
            int idx = -1;
            for (int i = 0; i < CHAT_TTL_CYCLE.Length; i++)
                if (Mathf.Approximately(CHAT_TTL_CYCLE[i], ChatOverlaySeconds.Value)) { idx = i; break; }
            SetChatOverlaySeconds(CHAT_TTL_CYCLE[(idx + 1) % CHAT_TTL_CYCLE.Length]);
        }

        /// <summary>Item 13: the value-taking writer (the settings slider, and
        /// the per-tab reset). The value is quantised to the NEAREST stop of
        /// CHAT_TTL_CYCLE, so nothing but a stop is ever stored: a hand-edited
        /// 30 written back through here becomes 25, never 0 ("hidden in
        /// game"), which is where the old cycler sent an out-of-set value.
        /// Null entry (pre-Awake) writes nothing.</summary>
        public static void SetChatOverlaySeconds(float s)
        {
            if (ChatOverlaySeconds == null) return;
            int best = 0;
            for (int i = 1; i < CHAT_TTL_CYCLE.Length; i++)
                if (Mathf.Abs(CHAT_TTL_CYCLE[i] - s) < Mathf.Abs(CHAT_TTL_CYCLE[best] - s)) best = i;
            ChatOverlaySeconds.Value = CHAT_TTL_CYCLE[best];
            Log.LogInfo($"[SETTINGS] Chat overlay TTL -> {ChatOverlaySeconds.Value}s");
        }

        /// <summary>Item 13: the index of the stop nearest the stored value
        /// (the slider's handle position). A hand-edited out-of-set value shows
        /// at its nearest stop; nothing is written until the handle moves.</summary>
        public static int ChatOverlaySecondsIndex()
        {
            float v = ChatOverlaySeconds != null ? ChatOverlaySeconds.Value : 25f;
            int best = 0;
            for (int i = 1; i < CHAT_TTL_CYCLE.Length; i++)
                if (Mathf.Abs(CHAT_TTL_CYCLE[i] - v) < Mathf.Abs(CHAT_TTL_CYCLE[best] - v)) best = i;
            return best;
        }

        /// <summary>True when the player has set the TTL to 0, i.e. the in-game
        /// chat overlay must not be drawn during play at all.
        ///
        /// This is the ONE definition of what 0 means; every consumer asks here
        /// rather than testing the float, so nobody can re-derive it as
        /// "clamp to 1 second" and quietly resurrect a 10-second fade the
        /// player asked not to see. `&lt;= 0` rather than `== 0` because the
        /// value is a float in a hand-editable cfg — a negative would otherwise
        /// reach the fade arithmetic, where it renders every line as already
        /// fading and would eventually produce a negative alpha.
        ///
        /// Null entry (pre-Awake init order) is FALSE, matching the shipped
        /// default of 25s — never hide chat because config binding has not run
        /// yet.
        ///
        /// ORDER AGAINST PINNED, flagged rather than decided quietly: the draw
        /// path should test this BEFORE the Pinned branch, which is Sid's rule
        /// read literally ("0 = never shows during play"). The cost is that
        /// pressing M to Pin then announces "messages stay on screen" and
        /// nothing appears. The alternative — Pinned wins, on the grounds that
        /// it is a deliberate announced action and the TTL is a background
        /// preference — is a product call, not a code one. Only reachable when
        /// a player has set both, and whichever way it goes the toast wording
        /// should match.</summary>
        public static bool ChatOverlayHiddenDuringPlay =>
            ChatOverlaySeconds != null && ChatOverlaySeconds.Value <= 0f;

        /// <summary>Display token for the current TTL, e.g. "25s", and "0s" at
        /// the floor. Deliberately NOT translated and deliberately not a word:
        /// a digit+unit token is under the extractor's 3-letter floor (#295c)
        /// and reads the same in every locale, so the caller wraps it in its
        /// own translated template rather than composing translated fragments.
        ///
        /// "0s" is left as a number on purpose. The Settings row reads
        /// "Chat fade after: 0s", which is literally true of the setting and
        /// needs no new translated word; substituting "Off" here would put an
        /// untranslated English word inside a translated line for every locale
        /// (and the on/off vocabulary already belongs to the row above, which
        /// is the actual overlay ON / PINNED / OFF control).</summary>
        public static string ChatOverlaySecondsLabel()
        {
            return ChatOverlaySecondsLabel(ChatOverlaySeconds != null ? ChatOverlaySeconds.Value : 25f);
        }

        /// <summary>Item 13: the same token for a GIVEN value, so the settings
        /// pane can render the recommended value (25s) without it being the
        /// live one. The zero-argument form above is this over the live value.</summary>
        public static string ChatOverlaySecondsLabel(float v)
        {
            if (v <= 0f) return "0s";
            return Mathf.RoundToInt(v).ToString(System.Globalization.CultureInfo.InvariantCulture) + "s";
        }

        private static bool spawned = false;
        internal static bool modDisabled = false;
        /// <summary>True once DoInitialize's other-mods check has produced its
        /// verdict (either way). GrowNormalize refuses to advertise cr_grow2
        /// before this — an advertise-then-revoke-in-room sequence reaches
        /// peers late (Codex Grow code review find 6).</summary>
        internal static bool compatCheckComplete = false;

        // Ranked queue auto-join state (on Plugin so it survives scene changes)
        private static string pendingRankedRoom = null;
        private static string pendingRankedRegion = null;
        private static bool pendingRoomLeaving = false;
        private static float pendingRoomLogTimer = 0f;
        public static string PendingRankedRoom => pendingRankedRoom;
        public static string PendingRankedRegion => pendingRankedRegion;

        /// <summary>Two-argument form: a caller that carries no issued rules
        /// (tournament dispatch, FFA lobby, an older server). Re-staging the
        /// SAME room (the tournament region resolve) keeps whatever rules were
        /// staged with it; a different room starts from "defaults expected".</summary>
        public static void SetPendingRoom(string roomName, string region = null, bool gated = false)
        {
            bool sameRoom = roomName != null && string.Equals(roomName, pendingRankedRoom, StringComparison.Ordinal);
            SetPendingRoom(roomName, region,
                           sameRoom ? RoomRules.PendingProp : null,
                           sameRoom ? RoomRules.PendingSrc : null);
            // V11 D3: JoinGate is true only while the pending room was set by a
            // gated FFA lock. The four-argument form clears it for every other
            // caller, and ClearPendingRoom clears it with the room.
            if (gated && !string.IsNullOrEmpty(roomName)
                && string.Equals(pendingRankedRoom, roomName, StringComparison.Ordinal))
                QueueRoomJoiner.JoinGate = true;
        }

        /// <summary>Room rules (01-room-rules §5.1): the rules the server issued
        /// for this room ride the pending tuple and die with it — cleared exactly
        /// when the pending room is cleared, never earlier. A null prop means
        /// "the defaults are expected" (see RoomRules.LatchOnJoin).</summary>
        public static void SetPendingRoom(string roomName, string region, string rulesProp, string rulesSrc)
        {
            // §2c identity fence (Codex mod-r1 F4): the broadcast service
            // account never stages a FIGHTER room. Every auto-join dispatch
            // path (queue ready_join, tournament heartbeat + tab dispatch,
            // hosted-lobby start) funnels through here, so the discard is
            // structural — QueueRoomJoiner never sees a pending room, and the
            // raw room/region below are never stored or logged on this seat.
            if (BroadcastMode.FenceBlocksFighterPath("pending-fighter-room")) return;
            pendingRankedRoom = roomName;
            pendingRankedRegion = region;
            QueueRoomJoiner.JoinGate = false;
            RoomRules.StagePending(rulesProp, rulesSrc);
            Log.LogInfo($"[QUEUE] Pending ranked room set: {roomName} (region: {region ?? "auto"}, rules: {rulesProp ?? "default"}{(rulesSrc != null ? " src=" + rulesSrc : "")})");
            JoinTimeline.Step("pending_set");
        }

        public static void ClearPendingRoom()
        {
            pendingRankedRoom = null;
            pendingRankedRegion = null;
            pendingRoomLeaving = false;
            QueueRoomJoiner.JoinGate = false;
            RoomRules.ClearPending();
        }

        // 2v2 slot 0-3 the server-side balancer assigned to us. Set when the
        // poll returns ready_join (computed from team_assigned + steam-id sort
        // within team). Read by PlayerAssigner_CreatePlayer_2v2_Patch to give
        // each of the 4 players a unique m_playerId — vanilla ROUNDS hardcodes
        // 0 for master, 1 for everyone else, which makes all 3 non-masters
        // collide on slot 1 and overwrite each other in PlayerManager.players.
        // Reset on room leave or series end.
        private static int pending2v2Slot = -1;
        public static int Pending2v2Slot => pending2v2Slot;
        public static void SetPending2v2Slot(int slot)
        {
            pending2v2Slot = slot;
            Log.LogInfo($"[2v2] Pending slot set: {slot} (team={(slot < 2 ? 1 : 2)})");
        }
        public static void ClearPending2v2Slot()
        {
            if (pending2v2Slot >= 0) Log.LogInfo("[2v2] Pending slot cleared");
            pending2v2Slot = -1;
        }

        // 1v2 slot 0-2 assigned at ovt queue lock: 0 = solo (team 0), 1/2 = duo
        // (team 1, in the server's duo_a/duo_b order so all three clients agree).
        // Same lifecycle as Pending2v2Slot: set on ready_join, cleared on queue
        // leave / poll expiry / series end. Read by the CreatePlayer override.
        private static int pendingOvtSlot = -1;
        public static int PendingOvtSlot => pendingOvtSlot;
        public static void SetPendingOvtSlot(int slot)
        {
            pendingOvtSlot = slot;
            Log.LogInfo($"[1v2] Pending slot set: {slot} ({(slot == 0 ? "solo/team0" : "duo/team1")})");
        }
        public static void ClearPendingOvtSlot()
        {
            if (pendingOvtSlot >= 0) Log.LogInfo("[1v2] Pending slot cleared");
            pendingOvtSlot = -1;
        }

        // FFA slot 0..N-1 assigned at ffa queue lock (steam-ordinal order, so
        // every client derives the identical mapping). In FFA each player is
        // their own ROUNDS team: TeamID = slot. pendingFfaCount is the locked
        // lobby size N (3-10) — playersNeededToStart for the room. Same
        // lifecycle as the other pending slots (set on ready_join, cleared on
        // queue leave / mismatch join / room leave).
        private static int pendingFfaSlot = -1;
        private static int pendingFfaCount = 0;
        public static int PendingFfaSlot => pendingFfaSlot;
        public static int PendingFfaCount => pendingFfaCount;
        public static void SetPendingFfaSlot(int slot, int playerCount)
        {
            pendingFfaSlot = slot;
            pendingFfaCount = playerCount;
            Log.LogInfo($"[FFA] Pending slot set: {slot} of {playerCount}");
        }
        public static void ClearPendingFfaSlot()
        {
            if (pendingFfaSlot >= 0) Log.LogInfo("[FFA] Pending slot cleared");
            pendingFfaSlot = -1;
            pendingFfaCount = 0;
        }

        /// <summary>The ONE list of components every persistent host carries.
        /// Called from the initial spawn AND CompetitiveRoundsBehaviour's
        /// OnDestroy respawn (Aug 17 review round-4 finding 3: the respawn
        /// used to recreate only the main behaviour, so a mid-session
        /// persistent-object destruction silently stripped the nickname
        /// repair driver, trail Photon callbacks, both nametag renderers and
        /// Cr2v2DiagCallbacks — including the reliable room-join reset that
        /// bugs 232/233 depend on — for the rest of the session). Any future
        /// persistent companion is added HERE, never at one call site.</summary>
        internal static void AttachPersistentCompanions(GameObject go)
        {
            // Bug 234: retry vanilla's transient Steam-persona nickname repair and
            // repaint one-shot PlayerName labels when Photon actor key 255 changes.
            // The driver is ungated and self-throttled; it never touches gameplay.
            go.AddComponent<PlayerNicknameRepairDriver>();
            // Sibling component that receives Photon IInRoomCallbacks — used by the cosmetic
            // trail system to re-attach opponents' trails when their cr_trail_* props arrive
            // after OnMatchStart has already iterated.
            go.AddComponent<TrailPhotonCallbacks>();
            // Local-only nametag renderers. Both poll scene TMP labels every 0.5s. Font
            // renderer is attached FIRST so its coroutine runs before the glow renderer
            // each cycle — glow clones its material from the label's current sharedMaterial,
            // which changes after a font swap, so the glow rebuild needs to see the swapped
            // material to reapply correctly. Order here is load-bearing.
            go.AddComponent<NametagFontRenderer>();
            go.AddComponent<NametagGlowRenderer>();
            // 2v2 diagnostics — Photon callback target. Logs every
            // PlayerEntered / PlayerLeft / Disconnect / LeftRoom / etc.
            // when in (or recently in) a cr_ff room. Also owns the reliable
            // room-join edge (resumed-score reset + stash consume, bug 232/233;
            // NetworkReplicaDiagnostics room lifecycle, bug 235).
            go.AddComponent<Cr2v2DiagCallbacks>();
            // v1.41.0 item 21: the damage-number driver - flushes and ages the
            // labels every frame whether or not anything is drawn. Ungated,
            // local, whole body guarded; it never touches gameplay.
            go.AddComponent<DamageNumberDriver>();
            // Letterbox ghost fix: the whole-window clearing camera, a child of
            // this host so it lives exactly as long as the host does. Visual and
            // local only, never gated (LetterboxClear.cs).
            LetterboxClear.CreateClearCamera(go);
        }

        private void Awake()
        {
            Log = Logger;
            // The thread every [LOG-BUNDLE] line compares its compose thread
            // against: Awake runs on Unity's main thread.
            try { LogBundleCore.RegisterMainThread(); } catch { }

            // BepInEx 5 defaults AppendLog=false, which truncates LogOutput.log
            // on every launch — meaning if a player crashes and reopens to file
            // a bug report, the crash log is gone. Hook Application.quitting
            // to snapshot the current session's log to LogOutput-prev.log
            // BEFORE BepInEx truncates the next run. Best-effort; failures are
            // swallowed (file lock / disk-full) so plugin load can't be blocked.
            try
            {
                UnityEngine.Application.quitting += () =>
                {
                    try
                    {
                        string src = CompetitiveUI.BepInExLogPathPublic();
                        string dst = CompetitiveUI.BepInExLogPreviousPath();
                        if (!string.IsNullOrEmpty(src) && !string.IsNullOrEmpty(dst) && System.IO.File.Exists(src))
                        {
                            System.IO.File.Copy(src, dst, overwrite: true);
                            Log.LogInfo($"[BUG-REPORT] log snapshot saved: {dst}");
                        }
                    }
                    catch (Exception ex) { Log.LogWarning($"[BUG-REPORT] quit-time log copy failed: {ex.Message}"); }
                };
                // Seat evidence: a game still live while the game closes is
                // captured, then built and queued to its file now (no later
                // frame comes) and sent at the next launch.
                UnityEngine.Application.quitting += () =>
                {
                    try { PointEvidence.Drain(); } catch { }
                    try { GameStateWatcher.SeatEvidenceOnQuit(); } catch { }
                    try { SeatEvidence.FlushOnQuit(); } catch { }
                    try { CardDrawEvidence.FlushOnQuit(); } catch { }
                    try { CombatEvidence.FlushOnQuit(); } catch { }
                    try { IdentityClockEvidence.FlushOnQuit(); } catch { }
                };
            }
            catch (Exception ex) { Log.LogWarning($"[BUG-REPORT] quit hook bind failed: {ex.Message}"); }

            // TLS is served on 8444 (80/443 on this WAN IP belong to an unrelated
            // device, so the cert is issued via DNS-01 and served on a high port —
            // a cert is port-agnostic). Plain 8443 stays up until MIN_MOD_VERSION
            // is raised past this release, so an un-migrated client keeps working.
            ConfigFileForLevers = Config;   // the broadcast-seat levers re-read the file (Config is an instance member)
            ApiBaseUrl = Config.Bind(
                "API", "BaseUrl",
                DefaultApiUrl,
                "Base URL of the Competitive ROUNDS API server"
            );

            AdminHmacSecret = Config.Bind(
                "API", "AdminSecret",
                "",
                "Admin HMAC secret. Leave empty unless you are a server admin - " +
                "admins receive the value out-of-band and it must match the " +
                "server's ADMIN_HMAC_SECRET. Admin menu actions are rejected " +
                "without it."
            );

            // Board row 27: while the session runs on the plaintext backup (the
            // secure check at boot failed), the secure route is checked again
            // every this-many minutes, and on the Translate portal button. A
            // NEW key, so no existing default changes (#190); clamped to
            // 0.25..60 where it is read (ApiClient.SecureRetrySeconds).
            SecureRetryMinutes = Config.Bind(
                "API", "SecureRetryMinutes", 5f,
                "Minutes between automatic checks of the secure connection while the game is running on the backup connection (0.25 to 60). The Translate portal button also checks it on demand."
            );

            // One-time HTTPS migration. Config.Bind writes its default to
            // BepInEx/config/com.competitiverounds.mod.cfg on FIRST run and never
            // revisits it, so changing the default alone migrates nobody — every
            // existing install would stay pinned to plaintext forever.
            //
            // Only the EXACT pre-TLS default is rewritten. A user (or Sid) pointing
            // at a LAN IP or any other host chose that deliberately and is left
            // alone. Comparison is trim + trailing-slash tolerant because the value
            // is hand-editable; assigning .Value persists it back to the .cfg.
            // Gated on a ONE-SHOT flag, not just the value comparison. Without it
            // the rewrite re-runs every Awake, which would silently undo the only
            // per-player support lever there is ("set BaseUrl back to the old
            // endpoint") on the very next launch.
            HttpsMigrationDone = Config.Bind(
                "API", "HttpsMigrationDone", false,
                "Internal: set once the one-time HTTPS endpoint migration has run. " +
                "Clear it only if you also want BaseUrl re-migrated on next launch."
            );
            try
            {
                if (!HttpsMigrationDone.Value)
                {
                    string cur = (ApiBaseUrl.Value ?? "").Trim().TrimEnd('/');
                    if (string.Equals(cur, LegacyApiUrl, StringComparison.OrdinalIgnoreCase))
                    {
                        ApiBaseUrl.Value = DefaultApiUrl;
                        Log.LogInfo($"[API] BaseUrl migrated to HTTPS: {DefaultApiUrl}");
                    }
                    HttpsMigrationDone.Value = true;
                }
            }
            catch (Exception ex) { Log.LogWarning($"[API] BaseUrl migration skipped: {ex.Message}"); }

            // Adds TLS 1.2 to the ServicePointManager protocol set for the two
            // System.Net.WebClient art downloads (CardImageLoader, CustomCosmetics),
            // which previously each set it themselves inside code paths that only
            // run when art is missing — so a normal session never executed it.
            //
            // It does NOT affect the API or chat, despite the obvious assumption:
            // UnityWebRequest uses Unity's native TLS stack, and ROUNDS' Mono
            // ClientWebSocket hardcodes `SslProtocols.Tls|Tls11|Tls12` when it
            // builds its SslStream (verified by decompiling ROUNDS_Data/Managed/
            // System.dll, WebSocketHandle.ConnectAsyncCore) — it never reads
            // ServicePointManager. Do not "fix" a chat TLS problem by changing
            // this line; it cannot be the cause.
            try
            {
                System.Net.ServicePointManager.SecurityProtocol |=
                    System.Net.SecurityProtocolType.Tls12;
            }
            catch (Exception ex) { Log.LogWarning($"[API] TLS 1.2 enable failed: {ex.Message}"); }

            RankedEnabled = Config.Bind(
                "Ranked", "Enabled",
                true,
                "Whether ranked tracking is active"
            );

            // Set when a consent REVOKE auto-disabled ranked (vs. the user clicking
            // Disable). On the next consent grant, ranked is restored automatically —
            // without this, a decline/revoke silently left ranked off forever and the
            // startup sync kept pushing ranked_enabled=false, so every game vs that
            // player recorded casual (bug #47's "opponents have ranked disabled and
            // I'm not sure they intended it").
            RankedDisabledByConsent = Config.Bind(
                "Ranked", "DisabledByConsentRevoke",
                false,
                "Internal: ranked was auto-disabled by a data-consent revoke, not by the user"
            );

            // Sept 10 (Player Cards): a pack purchase writes an entry
            // "kind|ref|pay|price|unix|owner" here BEFORE the request leaves and
            // clears it after the committed answer was shown, so a lost answer is
            // recovered instead of re-bought. One entry per owner (the Steam id
            // that wrote it), joined by '~': another account on this PC neither
            // recovers, clears nor overwrites it (c4/c5/c6).
            PcOpenIntent = Config.Bind(
                "Internal", "PlayerCardsOpenIntent",
                "",
                "Internal: a Player Cards pack open that has not been answered yet. Do not edit."
            );

            ShowNotifications = Config.Bind(
                "UI", "ShowNotifications",
                true,
                "Show in-game notifications for match results"
            );

            // Localization v1 (D2: asked once, changeable in Settings). The
            // "unset" sentinel drives the one-time first-launch prompt with
            // the OS-culture suggestion pre-selected; the prompt writes the
            // choice here and it is never asked again. Values: en, es, ru,
            // uk, sv (qps = pseudo-locale, dev-only via PseudoLocale below).
            ModLanguage = Config.Bind(
                "UI", "Language",
                I18n.LOCALE_UNSET,
                "Mod display language: en, es, ru, uk, sv (unset = ask on next launch)"
            );
            PseudoLocaleEnabled = Config.Bind(
                "UI", "PseudoLocale",
                false,
                "Dev: render every catalogued string bracketed+widened to surface untranslated/overflowing text"
            );
            try
            {
                I18nCatalogues.Install();
                if (PseudoLocaleEnabled.Value) I18n.SetLocale(I18n.LOCALE_PSEUDO);
                else if (ModLanguage.Value != I18n.LOCALE_UNSET) I18n.SetLocale(ModLanguage.Value);
                // unset -> stays English until the ask-once prompt answers.
                // Server-pack overlay (§2.2): cached copy immediately (works
                // offline); the fresh fetch rides ApiClient's init below.
                I18n.LoadCachedPack();
            }
            catch (Exception i18nEx) { Log.LogWarning("[I18N] init: " + i18nEx.Message); }

            ShowFps = Config.Bind(
                "UI", "ShowFps",
                true,
                "Show FPS counter in the top-left corner"
            );

            CapFpsUnfocused = Config.Bind(
                "Performance", "CapFpsUnfocused",
                true,
                "Cap the frame rate at 120 FPS while the game window is not focused (Aug 6 item 8). Saves GPU/CPU for alt-tabbed players without affecting gameplay; the cap is lifted the moment focus returns."
            );

            MuteAudioInBackground = Config.Bind(
                "Performance", "MuteAudioInBackground",
                false,
                "Mute game audio while the window is unfocused in an online Photon room. Audio stays on at the menu, and the broadcast seat always ignores this setting. Also togglable in the F5 Settings tab."
            );
            // Aug 23 (Stan, Discord): default flipped true -> false — most
            // players want their audio while tabbed out. #190: a changed
            // default migrates nobody, and the feature is ONE day old
            // (v1.39.1), so the `true` sitting in every cfg is the old
            // default, not a choice. One-shot flip, gated so a player who
            // re-enables afterwards keeps it; the new Settings toggle makes
            // re-enabling one click.
            var muteFlip = Config.Bind(
                "Performance", "MuteAudioInBackgroundDefaultMigrated",
                false,
                "Internal one-time marker for the Aug 23 default change (true -> false). Do not edit."
            );
            if (!muteFlip.Value)
            {
                if (MuteAudioInBackground.Value) MuteAudioInBackground.Value = false;
                muteFlip.Value = true;
            }

            // Aug 7 item 2: a NEW key, not a repurposed CapFpsUnfocused — that
            // key's on-disk description promises "no gameplay effect" and #190
            // means existing installs would never see a changed meaning anyway.
            DeepIdleUnfocused = Config.Bind(
                "Performance", "DeepIdleUnfocused",
                true,
                "After 60 seconds continuously unfocused AND outside any online room/battle/queue-match, drop the engine to 15 FPS (deep idle). Restores instantly on focus, on match found, or on joining a room. Never active during online play."
            );

            // Sid, Aug 18: the broadcast VM's game runs 24/7 and the
            // focus-gated deep idle never engages there (the seat's window
            // HOLDS focus — nothing else runs on that machine). Inert for
            // regular players: the arm is additionally gated on the broadcast
            // identity, so this key only means anything on the bot account.
            BroadcastIdleFpsCap = Config.Bind(
                "Performance", "BroadcastIdleFpsCap",
                true,
                "Broadcast seat only: after 16 minutes continuously idle (no spectate session, no room, nothing pending), drop the engine to 15 FPS regardless of window focus. Restores instantly when a broadcast target appears."
            );

            // Aug 23 (Sid: "GPU temps are kind of high"): the seat rendered
            // 300-390 FPS against a 60 FPS encode — everything above ~144 is
            // pure heat. Applies whenever the DIRECTOR is active (idle stages
            // still drop far lower); manual play with the director disabled is
            // untouched. 0 disables.
            BroadcastFpsCap = Config.Bind(
                "Performance", "BroadcastFpsCap",
                144,
                "Broadcast seat only: cap the engine frame rate while the broadcast director is active (the stream encodes at 60 FPS; rendering above ~144 is pure GPU heat). 0 = uncapped."
            );

            BroadcastWindowed1080 = Config.Bind(
                "Broadcast", "BroadcastWindowed1080",
                true,
                "Broadcast seat only: pin the game to windowed 1920x1080 (the capture geometry OBS expects), re-asserted every 30 seconds. The VM's RDP display exposes no resolution list, so the in-game picker cannot do this."
            );

            ShowRegionPing = Config.Bind(
                "UI", "ShowRegionPing",
                true,
                "Show Photon ping and region alongside FPS when in a room"
            );

            // v1.41.0 item 22: the standing room-rules strip names every
            // game-changing rule a room plays for the whole game. A NEW key with
            // a TRUE default: Config.Bind writes a default once (#190), so every
            // install, existing and fresh, shows the strip until the player
            // turns it off here. Hides the strip only, never the game-start toast.
            ShowRoomRulesIndicator = Config.Bind(
                "UI", "ShowRoomRulesIndicator",
                true,
                "Show the small top-centre line naming the room's rules (friendly fire off, same cards) for the whole game. The game-start notice is not affected."
            );

            // Sept 6 item d: a NEW key with a false default -- Config.Bind writes a
            // default once and never revisits it (#190), so this ships off for
            // every install. ApiClient appends include_inactive=true to the four
            // board fetches while it is on. The description states no day
            // count: it is written into the .cfg at startup, before the server
            // can have said what its window is, and the window is a server
            // setting (leaderboard_active_days on /api/v1/mod-version).
            ShowInactiveOnBoards = Config.Bind(
                "UI", "ShowInactiveOnBoards",
                false,
                "Show inactive players on the leaderboards (the server sets how many days without playing count as inactive)"
            );

            // Release B §4 (bug 332): opt-in lag notices. A NEW key with a
            // false default — Config.Bind writes a default once and never
            // revisits it (#190), so this ships off for every install.
            LagNoticesEnabled = Config.Bind(
                "Network", "LagNotices",
                false,
                "Show short corner notices when this seat measures dropped frames, high ping to the relay, or late-arriving opponent updates. 1v1 fighter seats only; informational, nothing is sent."
            );

            // v1.41.0 item (a): opt-IN automatic log upload. A NEW key with a
            // false default — Config.Bind writes a default once and never
            // revisits it (#190) — so it ships OFF for every existing install
            // as well as every fresh one, and a config that has never seen the
            // key gets the false.
            AutoLogUploadEnabled = Config.Bind(
                "Data", "AutoLogUpload",
                false,
                "Off by default. When on, the mod sends the same log bundle the bug-report form sends (this session's BepInEx log, the previous session's, and Unity's) to the community server after you leave a room where a game was played. Local paths and this machine's Windows account name are removed before anything is sent. At most one upload every five minutes."
            );

            ShowIngameChat = Config.Bind(
                "UI", "ShowIngameChat",
                true,
                "Show the in-game chat overlay while outside the F5 menu"
            );

            // NEW keys, never a repurposed one: Config.Bind writes a default
            // exactly once and never revisits it (#190), so changing an
            // existing key's meaning migrates nobody.
            ChatOverlayPinned = Config.Bind(
                "UI", "ChatOverlayPinned",
                false,
                "Pin the in-game chat overlay so messages never fade out. Cycled in-game with M (Normal -> Pinned -> Muted); Muted is stored as ShowIngameChat=false."
            );

            ChatOverlaySeconds = Config.Bind(
                "UI", "ChatOverlaySeconds",
                25f,
                "How many seconds an in-game chat line stays fully visible before it starts fading (the fade itself takes a further 10 seconds). 0 hides the overlay during play entirely. Ignored while the overlay is pinned."
            );

            ShowTrails = Config.Bind(
                "UI", "ShowTrails",
                true,
                "Show cosmetic trails behind players during matches (including your own and opponents')"
            );

            ShowBlockDebug = Config.Bind(
                "UI", "ShowBlockDebug",
                false,
                "Show the Block Debug overlay (top-right corner) during matches. Displays live counts of block activations vs successful absorbs, dedup drops, and per-hit timing ('too early' / 'too slow') so you can see why a block didn't land."
            );

            ShowPlayerColors = Config.Bind(
                "UI", "ShowPlayerColors",
                true,
                "Render custom player body colors (purchased from the Body Color shop tab) — your own and other modded players'. Off = everyone falls back to the default orange/blue team colors."
            );

            ShowInputOverlay = Config.Bind(
                "UI", "ShowInputOverlay",
                false,
                "Show a bottom-left visualizer of your movement, jump, shoot and block controls during matches. Keys glow red when pressed."
            );

            // Item 19: two default avatars chosen by the kind of room. New keys
            // only; nothing above is renamed, retyped or moved.
            AvatarAutoSwitch = Config.Bind(
                "UI", "AvatarAutoSwitch",
                true,
                "Wear your vanilla avatar preset in games where somebody does not have the mod, and your modded preset where everyone does. Does nothing until the presets below are set."
            );
            AvatarModdedPreset = Config.Bind(
                "UI", "AvatarModdedPreset",
                -1,
                "Character preset slot (0-based) worn where everyone has the mod. -1 = not set."
            );
            AvatarVanillaPreset = Config.Bind(
                "UI", "AvatarVanillaPreset",
                -1,
                "Character preset slot (0-based) worn where somebody does not have the mod; only presets made from base-game items can be used. -1 = not set."
            );
            AvatarHomeSlot = Config.Bind(
                "UI", "AvatarHomeSlot",
                -1,
                "Written by the mod: the preset you were wearing before a room switched it, given back when the room ends. -1 = none. Do not edit."
            );

            // LEGACY. Kept bound so the one-time migration below can read what the
            // player already chose; no longer consulted for enforcement.
            ScreenShakeEnabled = Config.Bind(
                "UI", "ScreenShakeEnabled",
                true,
                "(Legacy — superseded by ScreenShakeStrength.) Camera screen shake on hits/deaths/shots."
            );
            ScreenShakeStrength = Config.Bind(
                "UI", "ScreenShakeStrength",
                "Full",
                "Camera screen shake on hits/deaths/shots. Full = vanilla. Reduced = softer. Off = none. "
                + "Local only — opponents still see theirs. Valid values: Full, Reduced, Off."
            );
            // One-shot migration. A Config.Bind default is written to disk on first
            // launch and never revisited (learning #190), so a player who had already
            // turned shake OFF would silently get Full back the moment the new key
            // appeared. Carry their choice across, exactly once.
            try
            {
                if (!ScreenShakeEnabled.Value
                    && string.Equals(ScreenShakeStrength.Value, "Full", StringComparison.OrdinalIgnoreCase))
                {
                    ScreenShakeStrength.Value = "Off";
                    ScreenShakeEnabled.Value = true;   // consume it, so this cannot re-fire
                    Log.LogInfo("[SETTINGS] migrated ScreenShakeEnabled=false -> ScreenShakeStrength=Off");
                }
            }
            catch (Exception ex) { Log.LogWarning($"[SETTINGS] shake migration: {ex.Message}"); }
            MapLightingEnabled = Config.Bind(
                "UI", "MapLightingEnabled",
                true,
                "The map lighting pass (SFSS). Turn OFF for a flat, full-bright scene — skips the whole per-frame lightmap render for extra FPS."
            );
            MapShadowsEnabled = Config.Bind(
                "UI", "MapShadowsEnabled",
                true,
                "Soft shadow beams cast by map lighting. Turn OFF to skip the shadow render pass (lighting stays) for extra FPS."
            );
            AnimatedCosmetics = Config.Bind(
                "UI", "AnimatedCosmetics",
                true,
                "Animated cosmetics (prismatic/chrome body colors, prism trail hue cycle, player effects, map-skin sparkle shimmer, animated face items). Turn OFF to freeze them all to a static frame instantly."
            );
            ChromaticAberrationEnabled = Config.Bind(
                "UI", "ChromaticAberrationEnabled",
                true,
                "The RGB color-fringing distortion that pulses on shots/hits/deaths. Turn OFF for crisp edges and a tiny FPS gain (local only)."
            );
            // Default MUST be "Full": a Config.Bind default is written to disk on
            // first launch and never revisited (learning #190), so this is the one
            // shot at what every existing install gets. Full = today's rendering.
            BloomStrength = Config.Bind(
                "UI", "BloomStrength",
                "Full",
                "Strength of the post-processing GLOW (bloom) — the soft halo around bright cosmetics, map art and effects. "
                + "Full = vanilla. Reduced = smaller, dimmer halo. Off = no halo at all. Local only, and it never hides "
                + "anything: the cosmetic/map itself still renders exactly the same, only the halo around it changes. "
                + "Note that a few cosmetics have their glow PAINTED INTO the artwork (energy orbs, shooting star) — that "
                + "part is pixels, not an effect, so it stays visible at any setting. Valid values: Full, Reduced, Off."
            );
            AutoRequeueOnMatchmakingBug = Config.Bind(
                "UI", "AutoRequeueOnMatchmakingBug",
                true,
                "When the vanilla 'Press Jump to Join over a dead connection' matchmaking bug is detected, automatically restart and put you back in the quickplay queue (OFF = fast return to menu instead)."
            );

            PerfOptimizations = Config.Bind(
                "Performance", "Enabled",
                true,
                "Master switch for the v1.26.8 performance pass. Turn OFF to disable ALL patches below in one click. Individual patches below also have their own toggle for granular control."
            );
            PerfStunPlayerNullGuard = Config.Bind(
                "Performance", "StunPlayerNullGuard",
                true,
                "Null-guard StunPlayer.Go so a destroyed parent Player reference doesn't NRE every frame. Pure error suppression, no visual change."
            );
            // DEFAULT OFF as of v1.36.0. Projectiles are POOLED: the pool hands
            // back the same managed object with the same instance id and no
            // observable marker for "this is a new lifetime", so no guard keyed
            // on identity or elapsed time can reliably tell a re-fired bullet
            // from a still-flying one. Destroying one before its pool wrapper
            // has initialised makes BulletPoolInstancer.OnDestroy throw inside
            // PrefabPool.Release and corrupts the pool for the whole session
            // (learning #94) — a far worse outcome than the modest Photon
            // bandwidth this saves. Left available for anyone who wants it.
            PerfDespawnOffscreenBullets = Config.Bind(
                "Performance", "DespawnOffscreenBullets",
                false,
                "Host of each projectile despawns it once it flies outside the camera viewport (0.5s throttle). Saves a little bandwidth on long rounds. OFF by default: these projectiles are pooled, and destroying one before the engine has finished setting it up can corrupt the bullet pool for the rest of the session."
            );
            /* ONE-SHOT MIGRATION (learning #190). The default above only
             * applies to installs that have never written this key; every
             * upgrade from 1.35.5 or earlier still has `true` on disk, which is
             * exactly the population the new default exists to protect. Rewrite
             * the stored value ONCE, and only when it is still the old default
             * — a player who deliberately turns it back on afterwards keeps it,
             * because the flag below is already set by then. */
            var _despawnMigrated = Config.Bind(
                "Internal", "DespawnOffscreenBulletsMigratedV136", false,
                "Set automatically once the unsafe-by-default off-screen bullet despawn has been turned off for an upgrading install. Do not edit.");
            if (!_despawnMigrated.Value)
            {
                /* PAYLOAD FIRST, COMPLETION FLAG LAST (Codex r6 find 2).
                 * BepInEx persists on every Value assignment, so setting the
                 * flag first meant a crash or a failed save between the two
                 * writes left "migrated" recorded with the unsafe value still
                 * on disk — and every future launch would then skip the rewrite
                 * forever. Ordered this way the worst case is doing the same
                 * safe rewrite twice, which is a no-op. */
                if (PerfDespawnOffscreenBullets.Value)
                {
                    PerfDespawnOffscreenBullets.Value = false;
                    Log.LogInfo("[CONFIG] DespawnOffscreenBullets turned OFF for this upgrade "
                              + "(pooled projectiles: destroying one before its pool wrapper is "
                              + "ready can corrupt the bullet pool for the session). Re-enable it "
                              + "in Settings if you want it back.");
                }
                _despawnMigrated.Value = true;
            }
            PerfSwallowHitSoundNREs = Config.Bind(
                "Performance", "SwallowHitSoundNREs",
                true,
                "Catch the NullReferenceException that fires from RayHitBulletSound.DoHitEffect when its parent is destroyed mid-frame, and destroy the now-dead instance. Reduces BepInEx log spam, no visual change."
            );
            // (v1.28.2) AutoCleanupColorGhosts bind removed — current ROUNDS'
            // ChangeColor is an empty MonoBehaviour (no Start to patch, no
            // Update tick to save); hit effects are pooled via PrefabPool now.
            PerfSwallowEdgeBounceNREs = Config.Bind(
                "Performance", "SwallowEdgeBounceNREs",
                true,
                "Catch NullReferenceExceptions from ScreenEdgeBounce.DoHit and ScreenEdgeBounce.Update when a parent bullet was destroyed mid-frame. Reduces log spam, no visual change."
            );
            // (v1.28.2) TagSpawnedObjectsForCleanup bind removed — the 3-arg
            // SpawnObject overload is void (the patch could never compile its
            // __result Postfix), and the 8-arg overload returns POOLED
            // PoolableWrappers that a RemoveAfterSeconds Destroy would corrupt.
            PerfSkipMenuUpdateInMatch = Config.Bind(
                "Performance", "SkipMenuUpdateInMatch",
                true,
                "Skip MenuControllerHandler.Update during an active match (menu controller input routing isn't needed during gameplay). Modest CPU win, no visible change."
            );
            // v1.26.9 — actual frame-time wins.
            PerfBulletHitParticleCap = Config.Bind(
                "Performance", "BulletHitParticleCap",
                true,
                "Cap bullet-hit particle explosions at 2 per frame. In a heavy firefight (BombsAway / Echo / Mayhem) a single frame can spawn 20+ explosion bursts — the cap drops GC and render cost noticeably. Missed bursts are silent: the damage already registered, you just don't see every visual."
            );
            PerfClampObjectPoolInit = Config.Bind(
                "Performance", "ClampObjectPoolInit",
                true,
                "Clamp ObjectPool initial-spawn to 4 instances while in a match (lazy growth instead of pre-allocating 30+ up-front). Reduces frame stutter when new pools are constructed mid-game."
            );
            TournamentTimezone = Config.Bind(
                "Tournaments", "Timezone",
                "Local",
                "Timezone used to display tournament times. One of: Local, UTC, PT, MT, CT, ET, UK, CET, EET, MSK, JST, AEST, or a system timezone ID."
            );

            TournamentDateFormat = Config.Bind(
                "Tournaments", "DateFormat",
                "ISO",
                "Date/time display format: ISO (2026-04-24 14:30), US (Sat 04/24 2:30 PM), or EU (Sat 24/04 14:30). All formats emit ASCII-only so any locale renders cleanly."
            );

            // Sid Aug-3 item 9: GLOBAL date-order setting for every plain date
            // display in the mod (DateFmt.cs routes all sites through it).
            // Digits-only formats, so every locale renders cleanly (#47).
            // Tournament slot TIMES keep their own richer ISO/US/EU setting
            // above. New key => no #190 migration concern.
            UiDateFormat = Config.Bind(
                "UI", "DateOrder",
                "MDY",
                "Order for dates shown in the mod: MDY (8/23/2026, US default), DMY (23/8/2026), or YMD (2026-08-23). Short dates follow the same order."
            );
            // Sept 6 (item f): x axis of the rating graphs (leaderboard profile
            // graph and the Compare tab's Elo charts). "updates" = one point per
            // rating update (what the graphs always drew), "calendar" = real
            // dates, "since_first" = days since each player's first plotted
            // update so every line starts at x = 0. Written by the buttons on the
            // graphs themselves; RatingGraphAxis.cs sanitises the value.
            RatingGraphAxisMode = Config.Bind(
                "UI", "RatingGraphAxis",
                "updates",
                "X axis for the rating graphs: updates (one point per rating update), calendar (dates), or since_first (days since each player's first plotted update)."
            );
            // Bug #159: Sid asked for the game's own font at the Russian
            // fallback face's weight. Defaults ON at his request ("it looks
            // better and should be the default"); the toggle in Settings
            // restores the original thickness. Affects only the mod's own
            // labels — ROUNDS' UI is untouched.
            UiHeavyFont = Config.Bind(
                "UI", "HeavyMenuFont", true,
                "Render the mod's menu text at a heavier weight (the game's own font, thickened). Turn off for the original thickness."
            );
            UiFontWeight = Config.Bind(
                "UI", "MenuFontWeightBoost", 0.30f,
                "How much heavier, as an SDF weight delta. 0 = unchanged, 0.5 = maximum. Only used when HeavyMenuFont is on."
            );

            // Sid Aug-3 item 5: which chat channel the Home tab shows.
            // "all" = merged view of every subscribed channel (the historical
            // behavior); "global"/"es"/"ru"/"uk"/"sv" show only that channel.
            // The SEND channel defaults to the mod language's channel and is
            // changed from the same Home dropdown or with a tap of Alt while typing.
            // The description text below is cosmetic for existing installs
            // (#190: Config.Bind writes the default once and never revisits a
            // written entry) — the uk/sv values are legal regardless.
            ChatDisplayChannel = Config.Bind(
                "UI", "ChatDisplayChannel",
                "all",
                "Home-tab chat filter: all (merged), global, es, ru, uk, or sv."
            );

            // Sid Aug-3 item 13: the TYPING target is now its OWN setting,
            // separate from the display filter above. Empty = follow the mod
            // language (Spanish -> es, Russian -> ru, Ukrainian -> uk,
            // Swedish -> sv, everything else -> global/English). A concrete
            // value here is an explicit player pick made from the Home tab or
            // by tapping Alt while typing.
            // "all" is deliberately not a legal value — you cannot type into
            // the merged view. NEW key (#190: changing ChatDisplayChannel's
            // meaning would have migrated nobody, since its value is already
            // written to every existing install's config).
            ChatSendChannel = Config.Bind(
                "UI", "ChatSendChannel",
                "",
                "Chat channel you type into: empty (follow the mod language), global, es, ru, uk, or sv."
            );

            MutedChatNames = Config.Bind(
                "UI", "MutedChatNames",
                "",
                "Pipe-delimited list of display names whose chat messages are hidden from your in-game chat log. Use /mute name and /unmute name in chat."
            );

            DataConsent = Config.Bind(
                "Privacy", "DataConsent",
                "",
                "Consent to report match data to the leaderboard. Values: \"\" (unset — you'll be asked at launch), \"granted\", or \"denied\"."
            );

            // ── Music (ai-collab/music-feature design v3) ────────────────
            // All NEW keys (#190): these defaults land in every install's
            // cfg on first launch and are never revisited — they are final.
            MusicDeselected = Config.Bind(
                "Music", "MusicDeselected",
                "",
                "Tracks removed from your custom-music playlist, as albumSku/trackIndex pairs (comma-separated). Stored as the DESELECTED set so newly added tracks default to selected. Managed from the F5 Music tab."
            );
            MusicProbeEnabled = Config.Bind(
                "Music", "StreamProbe", false,
                "Diagnostic, off by default. Measures STREAMED music playback on this machine and writes [MUSIC-PROBE] lines to the BepInEx log; it plays on its own private audio source and never touches your music settings. Only useful if you have been asked for a measurement. Refused inside an online room. Set this to true and RESTART — the file is only read at startup while the probe is off. Once it is on, both keys are re-read from disk every 2 seconds, so turning this back to false ends a run in progress."
            );
            MusicProbeRun = Config.Bind(
                "Music", "StreamProbeRun", "",
                "What StreamProbe measures: '<albumSku>:<trackIndex>' plays that track streamed for 120 s. Add ':stress' for 600 s plus busy threads (only inside a live offline Sandbox round) or ':churn' for ten open/close cycles. Whatever is set here runs once when the probe turns on, including at startup; set a different value to run again. Ignored unless StreamProbe is true."
            );
            MusicTestScript = Config.Bind(
                "Music", "TestScript", "",
                "A ';'-separated music-engine exercise (Sept 7 design v2 section 2.5), run once per distinct value (including the value present at startup) and logged as [MUSIC-SELFTEST] lines. Named steps s1..s6, s4neg, s6neg and openall, plus album:<sku>, play:<sku>/<idx>, preview:<sku>/<idx>, fail:<sku>/<idx>, seek:len-<n>, loop:on|off, shuffle:on|off, select:<sku>:<i,j,..>|all, stall, unstall, wait:<sec>, stop, reset. Broadcast seat only, except a script of nothing but openall (the design v3 D12 gate), which runs on any seat; clear it when done."
            );
            MusicShuffle = Config.Bind(
                "Music", "MusicShuffle", false,
                "Shuffle the custom-music playlist (dispersion shuffle: no repeats within a cycle, cycle boundaries stay distinct)."
            );
            MusicLoop = Config.Bind(
                "Music", "MusicLoop", true,
                "Loop the custom-music playlist when it reaches the end."
            );
            MusicVolume = Config.Bind(
                "Music", "MusicVolume", MusicLevels.DEFAULT_PERCENT,
                "Custom-music volume percent (0-100, set with the Music tab's volume slider; any hand-edited value is used as-is, clamped). "
                + MusicLevels.DEFAULT_PERCENT + " plays the custom albums at the level of the game's own soundtrack; 100 is about 6 dB louder. "
                + "Applied on top of the game's own music slider, which keeps working."
            );
            // One-shot MusicVolume migration (1.41.0 item 23a), the
            // MenuMusicModeMigrated pattern below: Config.Bind never revisits
            // a written default (#190). 1.41.0 lowered the slider's whole
            // range (MusicLevels.VOLUME_CEILING) and put the default below the
            // top, and 100 was the default before, so a stored 100 is read as
            // never chosen and becomes the new default, once. Gated on its own
            // marker key, so a 100 chosen afterwards is kept; MigratedPercent
            // returns every other stored value unchanged.
            MusicVolumeMigrated = Config.Bind(
                "Music", "MusicVolumeMigrated", false,
                "Internal: set once the one-time 1.41.0 MusicVolume migration has run (a stored "
                + MusicLevels.LEGACY_DEFAULT_PERCENT + ", the old default, became " + MusicLevels.DEFAULT_PERCENT
                + "; no other value is changed). Clearing it runs the migration again on next launch."
            );
            try
            {
                if (!MusicVolumeMigrated.Value)
                {
                    int storedVolume = MusicVolume.Value;
                    int migratedVolume = MusicLevels.MigratedPercent(storedVolume, false);
                    if (migratedVolume != storedVolume) MusicVolume.Value = migratedVolume;
                    MusicVolumeMigrated.Value = true;
                    Log.LogInfo("[MUSIC] MusicVolume migration ran once: stored " + storedVolume + " -> " + migratedVolume
                                + " (only a stored " + MusicLevels.LEGACY_DEFAULT_PERCENT + " moves)");
                }
            }
            catch (Exception ex) { Log.LogWarning($"[MUSIC] MusicVolume migration skipped: {ex.Message}"); }
            MenuMusicEnabled = Config.Bind(
                "Music", "MenuMusicEnabled", false,
                "Superseded by MenuMusicMode - value migrated once, no longer consulted except as a pre-migration fallback."
            );
            MenuMusicMode = Config.Bind(
                "Music", "MenuMusicMode", "vanilla",
                "What plays in the main menu. Values: \"vanilla\" (ROUNDS' own menu music), \"custom\" (your selected custom-music playlist), \"silent\" (no menu music at all)."
            );
            // One-shot MenuMusicEnabled -> MenuMusicMode migration (the
            // HttpsMigrationDone pattern): Config.Bind never revisits a
            // written default (#190), so an existing opt-in install would
            // otherwise stay on "vanilla" forever. Gated on its own marker
            // key, not the value comparison, so a player who later hand-sets
            // the mode back to "vanilla" is never re-migrated on next launch.
            MenuMusicModeMigrated = Config.Bind(
                "Music", "MenuMusicModeMigrated", false,
                "Internal: set once the one-time MenuMusicEnabled -> MenuMusicMode migration has run. " +
                "Clear it only if you also want MenuMusicMode re-derived from MenuMusicEnabled on next launch."
            );
            try
            {
                if (!MenuMusicModeMigrated.Value)
                {
                    if (MenuMusicEnabled.Value)
                    {
                        MenuMusicMode.Value = "custom";
                        Log.LogInfo("[MUSIC] MenuMusicMode migrated from legacy MenuMusicEnabled=true: custom");
                    }
                    MenuMusicModeMigrated.Value = true;
                }
            }
            catch (Exception ex) { Log.LogWarning($"[MUSIC] MenuMusicMode migration skipped: {ex.Message}"); }
            MusicCreditToast = Config.Bind(
                "Music", "MusicCreditToast", false,
                "Show a small Now Playing credit line while custom music plays (opt-in). The broadcast seat shows its credit regardless of this key."
            );

            // ── SCR Broadcast (design doc §3a/§3b/§4) ────────────────────
            // Inert for every normal install: the director additionally
            // requires the broadcast account's steam id, and the §2c fence /
            // §7.1 masking key on that identity alone — this flag cannot
            // enable them elsewhere or disable them on the bot.
            BroadcastEnabled = Config.Bind(
                "Broadcast", "Enabled", false,
                "Run the broadcast director (auto-spectate rotation for the stream bot). Only functions on the broadcast service account; harmless elsewhere."
            );
            BroadcastStatusPath = Config.Bind(
                "Broadcast", "StatusPath", @"C:\broadcast\state\status.json",
                "Where the director writes its ~1s status lease (JSON) for the VM broadcast bot. Never contains room names or regions."
            );
            BroadcastHideChatPane = Config.Bind(
                "Broadcast", "HideChatPane", true,
                "Hide the floating in-game chat pane on the broadcast seat so stream frames stay clean. Only consulted on the broadcast identity."
            );
            BroadcastCustomMusic = Config.Bind(
                "Broadcast", "BroadcastCustomMusic", true,
                "Broadcast seat only: play the custom album pack instead of vanilla music, with the permanent on-stream credit line. Overrides SELECTION and ownership only - the seat's normal Music shuffle/loop settings still apply. Only consulted on the broadcast identity; grants nothing to players."
            );
            BroadcastTestMapSkin = Config.Bind(
                "Broadcast", "TestMapSkin", "",
                "Broadcast seat only: render a specific map skin without owning or equipping it, so the broadcast look can be checked outside a live spectate session. "
                + "Empty = off (normal behaviour). A sku name (e.g. mapcolor_soft) pins that skin. The word 'cycle' runs the broadcast night-pack auto-cycle on this seat. "
                + "Ignored entirely unless the local Steam account IS the broadcast identity, so it grants nothing to players. "
                + "A comma-separated list of skus is a TOUR (see TestMapSkinTourSeconds)."
            );
            BroadcastTestMapSkinSandbox = Config.Bind(
                "Broadcast", "TestMapSkinSandbox", false,
                "Broadcast seat only, with TestMapSkin set: enter LOCAL > SANDBOX automatically once the main menu is up, so the pinned skin renders on a map with nobody at the seat. Clear it (and TestMapSkin) when done."
            );
            BroadcastTestOpenTab = Config.Bind(
                "Broadcast", "TestOpenTab", "",
                "Broadcast seat only: open the F5 overlay on a tab index (0 My Stats, 1 Leaderboard, 2 Cards, 3 Achievements, 4 Shop, 5 Settings, 7 Tournaments, 8 2v2, 11 1v2, 12 FFA, 13 Home, 15 Info, 16 Music), optionally ':fraction' to scroll the Shop list (0 top .. 1 bottom) or, for tab 15, ':article-key' to open an Info article (e.g. 15:rewards). '4:cat<N>' selects a Shop category; after it, 'fixture[:line]', 'ladder:<line>', 'close' or 'live' drives the Titles section's ladder dropdown (fixture = BepInEx/config/scr-ladder-fixture.json). Re-applied whenever the value changes; clear when done."
            );
            BroadcastTestQuit = Config.Bind(
                "Broadcast", "TestQuit", "",
                "Broadcast seat only: set to any value that differs from the value at launch (e.g. quit-<timestamp>) to quit the game — Application.Quit, then a hard exit if the process is still alive 8 s later. Clear it afterwards; the value present at launch is the baseline and never fires."
            );
            BroadcastTestPress = Config.Bind(
                "Broadcast", "TestPress", "",
                "Broadcast seat only: 'ObjectName[:nonce]' presses the named button on the open F5 overlay through the button's own click path (e.g. SPortal:1 for the Translate portal button, ScrMod:1 for the scrmod.com link). The value at launch is the baseline and never fires; each later different non-empty value presses once. Clear it when done."
            );
            BroadcastTestSecureUrl = Config.Bind(
                "Broadcast", "TestSecureUrl", "",
                "Broadcast seat only: an https address the secure-connection check probes instead of the default one, so a witness can make the secure route unreachable (a closed port or an unroutable host) without touching BaseUrl. Empty = the default address. Read at every check; clear it when done."
            );
            BroadcastTestBackupUrl = Config.Bind(
                "Broadcast", "TestBackupUrl", "",
                "Broadcast seat only, local witness harness: a plaintext http address that replaces the backup connection for this launch. While set, BaseUrl is the route's own address even when it is not the default, TestSecureUrl may also name a plaintext loopback address (http://127.0.0.1:port), and empty TestSecureUrl means BaseUrl. Point BaseUrl at a local api when using it. Read once at launch; clear it when done."
            );
            BroadcastTestQueueReport = Config.Bind(
                "Broadcast", "TestQueueReport", "",
                "Broadcast seat only, local witness harness: each new non-empty value (the value at launch never fires) posts the match report in BepInEx/config/scr-portal-report.json to the current api through the same send, failure and outbox path a finished 1v1 game uses. Only while TestBackupUrl is set. Clear it when done."
            );
            BroadcastTestStaleToken = Config.Bind(
                "Broadcast", "TestStaleToken", "",
                "Broadcast seat only: each new non-empty value (the value at launch never fires) replaces the held session token with a random one the server never issued, keeping its local expiry, so a witness can press the portal button with a token the server refuses. Clear it when done."
            );
            BroadcastTestPlayerCards = Config.Bind(
                "Broadcast", "TestPlayerCards", "",
                "Broadcast seat only: set to any value that differs from the previous one to fill the Collection tab's reveal strip with five synthetic Player Cards (layout screenshots on a seat whose server has no Player Cards yet). No server call, nothing persisted."
            );
            // Item 20. The EXISTING "Player Cards" section (with the space) —
            // binding under a second, near-identical heading would give every
            // player two Player Cards blocks in CompetitiveRounds.cfg. The
            // value is the enum member name; applying it is deferred until a
            // collection answer has been read (PlayerCardsUI.pendingBinderSort),
            // and nothing but the header button ever writes it back.
            BinderSort = Config.Bind(
                "Player Cards", "BinderSort", "Name",
                "How your binder is ordered: Name, Rarity, Edition, Date, Position (the rank printed on the card) or RatingPosition (where the player stands on the leaderboard today). Set by the Sort button on the binder page; an unrecognised value reads as Name."
            );
            PlayerCardsUI.RestoreBinderSort(BinderSort.Value);
            PortraitPreset = Config.Bind(
                "Player Cards", "PortraitPreset", -1,
                "Which character your card picture shows: -1 follows the character you have selected, or pin one of your saved character slots by its index counting from 0 (the button counts them from 1). Only slots the character creator lets you fill can be pinned; any other value falls back to following your selected character, and is reset to -1 once the game has told us how many slots there really are. Changing it re-renders the picture next time the Collection tab or Settings is open."
            );
            BroadcastTestGstatsSentinel = Config.Bind(
                "Broadcast", "TestGstatsSentinel", "",
                "Broadcast seat only: set to any NEW value to run the cr_gstats self-tests once: the W1 sentinel (design v6 section 1) and the freeze-counting epoch check; the results are logged as [GSTATS-SENTINEL] and [FREEZE-EPOCH-SENTINEL] PASS/FAIL. A value present at startup never runs."
            );
            BroadcastTestReporterElectionSentinel = Config.Bind(
                "Broadcast", "TestReporterElectionSentinel", "",
                "Broadcast seat only: set to any NEW value to run the 2v2 disconnect reporter-election self-test once (synthetic rooms only, nothing is sent); the result is logged as [REPORTER-ELECTION-SENTINEL] PASS/FAIL. A value present at startup never runs."
            );
            BroadcastTestHeartbeatAbortSentinel = Config.Bind(
                "Broadcast", "TestHeartbeatAbortSentinel", "",
                "Broadcast seat only: set to any NEW value to run the aborted-send heartbeat self-test once (one"
                + " request to a loopback discard address, aborted before it can be answered; the heartbeat fields"
                + " are put back afterwards); the result is logged as [HEARTBEAT-ABORT-SENTINEL] PASS/FAIL. A value"
                + " present at startup never runs."
            );
            BroadcastTestPresetSlotSentinel = Config.Bind(
                "Broadcast", "TestPresetSlotSentinel", "",
                "Broadcast seat only: set to any NEW value to run the preset-slot count self-test once (it derives"
                + " the count from the game's own portrait row and checks that a partial row's count is derived"
                + " again rather than kept; the cached count is put back afterwards); the result is logged as"
                + " [PRESET-SLOT-SENTINEL] PASS/FAIL. A value present at startup never runs."
            );
            BroadcastTestTeamGameNumberSentinel = Config.Bind(
                "Broadcast", "TestTeamGameNumberSentinel", "",
                "Broadcast seat only: set to any NEW value to run the 2v2 game-number self-test once (synthetic"
                + " series against a model of the server's filing rule, on trackers of its own: nothing is sent,"
                + " and the seat's own tracker is never touched); the result is logged as"
                + " [TEAM-GAME-NUMBER-SENTINEL] PASS/FAIL. A value present at startup never runs."
            );
            BroadcastTestChatRevokeSentinel = Config.Bind(
                "Broadcast", "TestChatRevokeSentinel", "",
                "Broadcast seat only: set to any NEW value to run the consent-revoke chat self-test once (synthetic text in the open chat line and the held draft, put back afterwards; nothing is sent); the result is logged as [CHAT-REVOKE-SENTINEL] PASS/FAIL. A value present at startup never runs."
            );
            BroadcastTestAutoLogConsentSentinel = Config.Bind(
                "Broadcast", "TestAutoLogConsentSentinel", "",
                "Broadcast seat only: set to any NEW value to run the automatic-log consent self-test once (synthetic bundles against a stub transport: nothing is sent, and the real setting and data consent are read but never written); the result is logged as [AUTO-LOG-CONSENT-SENTINEL] PASS/FAIL. A value present at startup never runs."
            );
            BroadcastTestMapSkinTourSeconds = Config.Bind(
                "Broadcast", "TestMapSkinTourSeconds", 0,
                "Broadcast seat only, with a comma-separated TestMapSkin list: advance to the next skin every N seconds while a map is up (0 = stay on the first). Each advance logs [MAPCOLOR-TOUR]."
            );
            BroadcastTestSilence = Config.Bind(
                "Broadcast", "TestSilence", false,
                "Broadcast seat only, OFFLINE/sandbox only: set silenceTime=3s on the last non-local player (a spawned bot; falls back to the local player) so the silence indicator can be verified with nobody at the seat. Applies once per flip to true; set false then true again to re-fire."
            );
            BroadcastTestQuickChatWheel = Config.Bind(
                "Broadcast", "TestQuickChatWheel", "",
                "Broadcast seat only: 'main' or 'more' pins the quick-chat wheel open for layout screenshots (paint-only — sends still refuse outside a room). Clear to close."
            );
            BroadcastTestDance = Config.Bind(
                "Broadcast", "TestDance", "",
                "Broadcast seat only. 'wheel' pins the dance wheel open, 'preview:<sku>' toggles the shop puppet, 'play:<idx>' dev-installs a dance on the local sandbox body (offline only). Empty closes the wheel + puppet; an installed play simply expires on its own.");
            BroadcastTestRoomRules = Config.Bind(
                "Broadcast", "TestRoomRules", "",
                "Broadcast seat only, outside any online room: a rules pair in the room grammar (ff=0;sc=1, ff=0;sc=0, ff=1;sc=1) latches those rules on this seat so the standing room-rules strip can be checked with nobody at the seat; logged as [ROOM-RULES] test lever lines. Applied once per distinct value; empty releases a latch this lever made. Refused inside a room.");
            BroadcastShowcaseMetricSeconds = Config.Bind(
                "Broadcast", "ShowcaseMetricSeconds", 15f,
                "Broadcast seat only: how many seconds the idle showcase shows each Compare tab category; it walks every category in the tab's own order. 0 or less means the default (15); other values are held between 3 and 300. Applies from the next rotation.");
            BroadcastTestShowcase = Config.Bind(
                "Broadcast", "TestShowcase", "",
                "Broadcast seat only: set to any NEW value to play one idle-showcase rotation even when the stream is not live; every other condition still applies (the director idle with nothing to watch, not in an online room, the F5 page free). Each Compare category shown logs a [SHOWCASE] metric line. A value present at startup never runs.");
            BroadcastSessionReportPageSeconds = Config.Bind(
                "Broadcast", "SessionReportPageSeconds", 12f,
                "Broadcast seat only: after a watched set the broadcaster pages through the set's session report; this is how many seconds each page stays up. 0 or less means the default (12); other values are held between 3 and 300. Applies from the next page.");
            BroadcastTestWatchedSet = Config.Bind(
                "Broadcast", "TestWatchedSet", "",
                "Broadcast seat only: set to a NEW spectate game id (a UUID) to replay that recorded set through the post-set report as if the director had just watched it (the server's report status, the settle, the fetches, the session report and its pages), even when the stream is not live. A value present at startup never runs.");
            BroadcastTestSessionReport = Config.Bind(
                "Broadcast", "TestSessionReport", "",
                "Broadcast seat only: set to a NEW '<selector>:<key>' (selector sitting, series, match, session or lobby; key the UUID a history row carries) to open that set's session report on the open F5 page; add ':<page>' (1 is the first page) to show that page, and the same set with another page only turns the page. 'close' closes the report and leaves the F5 page open. A value set while the F5 page is closed waits for it (TestOpenTab opens it). A value present at startup never runs.");
            Log.LogInfo($"{ModName} v{ModVersion} initializing (consent={(string.IsNullOrEmpty(DataConsent.Value) ? "unset" : DataConsent.Value)})...");

            // ── Game version check ──
            string gameVer = Application.version ?? "";
            if (!gameVer.StartsWith(RequiredGameVersion))
            {
                Log.LogError($"[COMPAT] ROUNDS version {gameVer} is NOT supported! This mod requires vanilla ROUNDS v{RequiredGameVersion}.");
                Log.LogError($"[COMPAT] Please switch to the 'Default Public Version' in Steam → ROUNDS → Properties → Betas.");
                Log.LogError($"[COMPAT] Mod DISABLED.");
                return;
            }
            Log.LogInfo($"[COMPAT] Game version OK: {gameVer}");

            // Item 17: the keybind registry - the mapping accessor is resolved and
            // the sixteen Controls entries loaded BEFORE any patch can read them.
            try { Keybinds.Init(Config); }
            catch (Exception ex) { Log.LogError("[KEYBIND] init failed: " + ex.Message); }

            // Patch each [HarmonyPatch] class individually so one bad patch
            // (e.g. parameter-name mismatch with vanilla, missing target method)
            // doesn't abort the rest. v1.25.10-13 silently shipped with a single
            // mis-named Prefix parameter on PlayerSkinBank.GetPlayerSkinColors —
            // PatchAll aborted there, every patch declared after it (including
            // ArtHandler.NextArt for map colors, MapManager spawn-point sort,
            // and several diag patches) never applied for 4 releases. With
            // per-class isolation, we lose just the broken class and keep
            // everything else.
            // MusicSuppressionPatch (MusicEngine.cs) rides this same loop via
            // its class-level [HarmonyPatch] — its prefixes fail open until
            // the engine initializes and are never gated on IsCompetitiveRoom
            // (#286); MusicEngine.Initialize verifies attachment (#83).
            try
            {
                HarmonyInstance = new Harmony(ModId);
                int applied = 0, failed = 0;
                foreach (var type in Assembly.GetExecutingAssembly().GetTypes())
                {
                    var attrs = type.GetCustomAttributes(typeof(HarmonyPatch), true);
                    if (attrs == null || attrs.Length == 0) continue;
                    try
                    {
                        HarmonyInstance.CreateClassProcessor(type).Patch();
                        applied++;
                    }
                    catch (Exception ex)
                    {
                        failed++;
                        Log.LogError($"[HARMONY] Failed to patch {type.Name}: {ex.Message}");
                    }
                }
                Log.LogInfo($"[HARMONY] Patches applied: {applied} ok, {failed} failed");
                // Card draw evidence (B4): one line naming its six patches as attached.
                try { CardDrawEvidence.BootLine(); } catch { }
                // Combat evidence (B1-B5 and the addendum): one line naming every
                // combat patch as attached, and the producers the census proves.
                try { CombatEvidence.BootLine(); } catch { }
                try { IdentityClockEvidence.BootLine(); } catch { }
                // Stage 2: every hold patch named as attached or not (#83).
                try { TeamHoldGlue.BootLine(); } catch { }
                // Item 21: one line naming both damage-number hook pairs as attached (#83).
                try { DamageNumbers.BootLine(); } catch { }
            }
            catch (Exception ex)
            {
                Log.LogWarning($"Harmony patching bootstrap failed (mod will work without it): {ex.Message}");
            }

            // Stage the authoritative-poison capability NOW, before anything can
            // connect. It must ride the Photon join operation itself — that is the
            // entire basis for the protocol needing no activation barrier, because
            // a property delivered with a player's Player object cannot be observed
            // late by anyone who can act on that player. Must run AFTER Harmony
            // patching so PatchesLive is known: advertising an authority we cannot
            // deliver is worse than not advertising at all.
            // Hook() here as well as from the tick: the tick is gated behind
            // modDisabled/startup, and a client that advertises authority but never
            // subscribed to the commit path would never apply its OWN damage.
            try { PoisonSync.StageCapability("Awake"); PoisonSync.Hook(); } catch { }
            // CloseConnection is a COOPERATIVE Photon primitive that stock
            // PUN ships DISABLED on both ends (Aug 10 r9 find 1: every
            // spectator-system "kick" to date was a silent no-op). It is
            // deliberately NOT enabled globally here (r10 find 3: a hostile
            // CURRENT MASTER could then evict honest FIGHTERS — a new
            // competitive-integrity primitive). Instead: SPECTATOR sessions
            // enable the flag for their own lifetime (a spectator is
            // kickable by design — SpectatorSync owns that), and master-side
            // send sites raise it TRANSIENTLY around their own CloseConnection
            // call via RoomActors.CooperativeClose — while WE are master, an
            // incoming event 203 can only be honored from "the master",
            // which is us, so the transient window is not exploitable.
            // cr_grow2 deliberately has NO Awake stage call: GrowNormalize
            // refuses to advertise before the compat verdict (Codex find 6),
            // so its staging rides the persistent tick a few seconds later —
            // still long before any human can join a room.
            // Spectator snapshot protocol: subscribe the Photon event handler
            // before any room can be joined (same reasoning as PoisonSync).
            try { SpectatorSync.Hook(); } catch { }
            // Connect-failure (V11): the timeline banner, the late entry's
            // event handler and the assembly's attach verdicts, after patching.
            JoinTimeline.PrintBanner();
            try { FfaLateEntry.Hook(); } catch (Exception ex) { Log.LogWarning("[FFA-LATE] hook: " + ex.Message); }
            try { FfaAssembly.Init(); } catch (Exception ex) { Log.LogWarning("[FFA-ASM] init: " + ex.Message); }

            // Create persistent object with maximum protection
            if (!spawned)
            {
                var go = new GameObject("CompetitiveRounds_Persistent");
                go.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(go);
                Instance = go.AddComponent<CompetitiveRoundsBehaviour>();
                AttachPersistentCompanions(go);
                spawned = true;
                Log.LogInfo("Created persistent GameObject with DontDestroyOnLoad");
            }

            // Referencing the marker is what puts it in the compiled #US heap
            // (an unreferenced const is folded away and would be unscannable),
            // and it also tells a bug report which variant the player is on.
            Log.LogInfo($"{ModName} v{ModVersion} loaded! [{ApiClient.BuildVariantMarker}]");

            // (AttachPersistentCompanions lives below so BOTH the initial spawn
            // and the OnDestroy respawn attach the same set — Aug 17 review
            // round-4 finding 3: the respawn used to recreate only the main
            // behaviour, silently dropping every companion — the nickname
            // repair driver, trail callbacks, nametag renderers and the 2v2
            // Photon callback target (whose OnJoinedRoom owns the resumed-
            // score reset/consume) — for the rest of the session.)

            // Create a separate tiny object for queue auto-join
            var queueObj = new GameObject("CR_QueueJoiner");
            queueObj.hideFlags = HideFlags.HideAndDontSave;
            UnityEngine.Object.DontDestroyOnLoad(queueObj);
            queueObj.AddComponent<QueueRoomJoiner>();

            // Taskbar flash for alt-tabbed match found notifications
            var flashObj = new GameObject("CR_TaskbarFlash");
            flashObj.hideFlags = HideFlags.HideAndDontSave;
            UnityEngine.Object.DontDestroyOnLoad(flashObj);
            flashObj.AddComponent<TaskbarFlash>();
        }
    }

    /// <summary>
    /// Tiny MonoBehaviour solely for ranked queue auto-join.
    /// Uses ROUNDS' own NetworkConnectionHandler for region connection and room joining.
    /// Requires Krafs.Publicizer for direct access to NCH private members.
    /// </summary>
    public class QueueRoomJoiner : MonoBehaviour
    {
        private enum JoinState { Idle, LeavingRoom, Connecting, WaitingForRoom }
        private JoinState state = JoinState.Idle;
        private float stateTimer = 0f;
        private bool joinInitiated = false;
        private string targetRoom;
        private string targetRegion;
        // One automatic full-sequence retry before giving up (#26 — "matched but
        // failed to auto join"). A slow Photon region connect or a transient
        // disconnect race eats the first 30s window; a second attempt from a
        // clean state recovers it without the player touching anything.
        private int joinAttempts = 0;

        // V11 D3: true only while the pending room was set by a gated FFA lock
        // (SetPendingRoom's gated flag); cleared with the pending room. Every
        // other mode and every ungated room keeps today's joiner line for line.
        internal static bool JoinGate;
        internal static QueueRoomJoiner Instance;
        // V11 D3: the realtime attempt clock beside the scaled stateTimer; every
        // reset point sets both.
        private float stateStartedRt;
        private float Elapsed => JoinGate ? Time.realtimeSinceStartup - stateStartedRt : stateTimer;
        internal string StateName => state.ToString();
        internal int AttemptOrdinal => joinAttempts + 1;
        private Photon.Realtime.ClientState _cstateLast;
        private bool _cstateSeen;

        // ── Tournament (sct-) region gate ────────────────────────────────
        // Server-issued tournament rooms are the one case where "no region"
        // must NOT mean "use whatever the player last picked" — see
        // GateTournamentRegion. Window: hold for GRACE seconds accepting only
        // the per-match region, then also accept the tournament-wide one, then
        // give up. Both bounds are generous against the 20s heartbeat poll, so
        // a single dropped response cannot burn the match.
        private const float SCT_REGION_GRACE_SECONDS = 45f;
        private const float SCT_REGION_GIVEUP_SECONDS = 60f;
        private const float SCT_REGION_REPOLL_SECONDS = 10f;
        private string sctRegionWaitRoom = null;
        private float sctRegionWaitStart = -1f;
        private float sctRegionRepollAt = 0f;
        // Rooms the player has already been told about. Keyed on the room name
        // (stable for the whole match) rather than reset with the window, so
        // the tournament heartbeat re-arming this dispatch every 60s cannot
        // turn either message into a notification storm. Two separate memos
        // because they are two different messages: one memo would let the
        // give-up toast suppress the wait toast on the next cycle, or vice
        // versa, depending on which fired first.
        private string sctRegionWaitNotifiedRoom = null;
        private string sctRegionGaveUpNotifiedRoom = null;

        private void Awake()
        {
            Plugin.Log.LogInfo("[QUEUE-JOINER] Awake, DontDestroyOnLoad set");
            Instance = this;
            JoinTimeline.AttemptOrdinal = () => Instance != null ? Instance.AttemptOrdinal : 1;
        }

        /// <summary>V11 D3: ends the current attempt now, only under JoinGate;
        /// the existing timeout branch runs on the next frame and retries once,
        /// then gives up.</summary>
        internal void EndAttemptNow(string why)
        {
            if (!JoinGate) return;
            stateStartedRt = Time.realtimeSinceStartup - 1000f;
            Plugin.Log.LogWarning("[QUEUE-JOINER] attempt ended now (" + why + ")");
        }

        /// <summary>V11 I1 cstate: the client state's transitions while a join
        /// runs, compared once per frame.</summary>
        private void CstateTick()
        {
            try
            {
                var cs = PhotonNetwork.NetworkClientState;
                if (_cstateSeen && cs == _cstateLast) return;
                string from = _cstateSeen ? _cstateLast.ToString() : "-";
                _cstateLast = cs;
                _cstateSeen = true;
                string cause = "-";
                try { cause = PhotonNetwork.NetworkingClient != null ? PhotonNetwork.NetworkingClient.DisconnectedCause.ToString() : "-"; } catch { }
                JoinTimeline.Step("cstate", "from=" + from + " to=" + cs + " cause=" + cause);
            }
            catch { }
        }

        private static string NormRegion(string r)
        {
            return (r ?? "").Replace("/*", "").Trim().ToLowerInvariant();
        }

        /// <summary>V11 D3: the region check before the join is issued. It logs
        /// in every mode; it ends the attempt (and the join is not issued) only
        /// under JoinGate and while the server advertises join_region_guard.</summary>
        private bool RegionCheck()
        {
            string want = NormRegion(targetRegion);
            string live = NormRegion(ApiClient.LiveOnlineRegion());
            bool match = want.Length == 0 || want == live;
            bool end = !match && JoinGate && ApiClient.ServerJoinRegionGuard;
            if (!match)
                Plugin.Log.LogWarning("[QUEUE-JOINER] region check: live=" + (live.Length == 0 ? "-" : live)
                                      + " want=" + want + " act=" + (end ? "end" : "log"));
            JoinTimeline.Step("region_check", match ? "ok" : "mismatch act=" + (end ? "end" : "log"));
            if (!end) return true;
            EndAttemptNow("region");
            return false;
        }

        private void Update()
        {
            FfaAssembly.Tick();
            string pendingRoom = Plugin.PendingRankedRoom;
            if (string.IsNullOrEmpty(pendingRoom))
            {
                joinInitiated = false;
                state = JoinState.Idle;
                stateTimer = 0f; stateStartedRt = Time.realtimeSinceStartup;
                joinAttempts = 0;
                return;
            }

            stateTimer += Time.deltaTime;
            // V11 I1: the client state's transitions while a join runs.
            if (state != JoinState.Idle) CstateTick();

            // Pending-room replacement fence (lobby impl round 3 find C2): a
            // NEW pending room while this run is bound to the old one means
            // the old target is dead — restart the machine immediately with a
            // fresh budget instead of burning the old room's 30s timeout and
            // retry on a target nobody wants. (Cleared-to-empty is handled by
            // the Idle reset above; the old room's DoActionWhenConnected
            // callback dies on its own capture check.)
            if (state != JoinState.Idle && !string.IsNullOrEmpty(targetRoom)
                && !string.Equals(pendingRoom, targetRoom, StringComparison.Ordinal))
            {
                Plugin.Log.LogWarning($"[QUEUE-JOINER] pending room replaced mid-run ('{targetRoom}' -> '{pendingRoom}') — restarting joiner for the new room");
                // LeavingForRanked stays SET while a deliberate room-leave is
                // still in flight (round-4 find: clearing it mid-LeavingRoom
                // let GameStateWatcher score our own exit as a DC). The
                // leave-completion flow consumes the flag normally.
                if (state != JoinState.LeavingRoom)
                {
                    try { GameStateWatcher.LeavingForRanked = false; } catch { }
                }
                joinInitiated = false;
                state = JoinState.Idle;
                stateTimer = 0f; stateStartedRt = Time.realtimeSinceStartup;
                joinAttempts = 0;
                targetRoom = null;
                targetRegion = null;
                return;
            }

            // Safety timeout — 30s to account for disconnect + NCH connection sequence.
            // Lexia hit this on a slow Photon connect (v1.26.1 logs): pending room set
            // mid-queue from a prior session, timeout fired, but the reset only cleared
            // the room — leaving GameStateWatcher.LeavingForRanked=true (set when we
            // initiated the leave on line where state became LeavingRoom) and stale
            // targetRoom / targetRegion behind. Subsequent matches in the same session
            // could then suppress legitimate DC-win counting. Clear everything.
            if (state != JoinState.Idle && Elapsed > 30f)
            {
                joinAttempts++;
                if (joinAttempts <= 1)
                {
                    // First timeout: retry the whole sequence from a clean slate.
                    // The pending room is still set, so the Idle branch below
                    // re-initiates leave/connect/join on the next frame.
                    Plugin.Log.LogWarning($"[QUEUE-JOINER] Join attempt {joinAttempts} timed out (state={state}, target='{targetRoom}') — retrying once");
                    JoinTimeline.Step("attempt_timeout", "elapsed=" + Elapsed.ToString("F1", System.Globalization.CultureInfo.InvariantCulture)
                                      + " clock=" + (JoinGate ? "rt" : "scaled"));
                    // Keep LeavingForRanked while the deliberate leave is
                    // still in flight (round-5: an early clear here let the
                    // watcher score our own hung exit as a DC). The join-
                    // success path and the leave-event consumer own it.
                    bool leaveStillInFlight = state == JoinState.LeavingRoom;
                    joinInitiated = false;
                    state = JoinState.Idle;
                    stateTimer = 0f; stateStartedRt = Time.realtimeSinceStartup;
                    if (!leaveStillInFlight)
                    {
                        try { GameStateWatcher.LeavingForRanked = false; } catch { }
                    }
                    CompetitiveUI.ShowNotification("Slow connection — still trying to join the match...", new Color(1f, 0.8f, 0.3f), 6f);
                    return;
                }
                Plugin.Log.LogWarning($"[QUEUE-JOINER] Timed out waiting for room join after {joinAttempts} attempts (state={state}, target='{targetRoom}'), resetting all queue state");
                // V11 I1/I2: give_up, its failed receipt under JoinGate, and
                // the timeline's disarm.
                bool gatedGiveUp = JoinGate;
                JoinTimeline.Step("give_up");
                if (gatedGiveUp)
                {
                    try { FfaAssembly.PostFailed("join", int.MinValue); } catch { }
                }
                JoinTimeline.Disarm("give_up");
                // 1v2: a failed join must dissolve the lock server-side, or the
                // three 'ready_join' rows + the 'active' series persist as a
                // husk that re-feeds this dead room on every future Join click.
                // OvtLeaveQueue also resets the local lock state (status,
                // lineup, pending slot) that would otherwise leave the tab
                // showing "Match found! Joining…" over a live Join button.
                bool wasOvt = (targetRoom ?? "").StartsWith("ovt_") || (pendingRoom ?? "").StartsWith("ovt_");
                bool wasFfa = (targetRoom ?? "").StartsWith("ffa_") || (pendingRoom ?? "").StartsWith("ffa_");
                bool giveUpLeaveInFlight = state == JoinState.LeavingRoom;
                Plugin.ClearPendingRoom();
                joinInitiated = false;
                state = JoinState.Idle;
                stateTimer = 0f; stateStartedRt = Time.realtimeSinceStartup;
                joinAttempts = 0;
                targetRoom = null;
                targetRegion = null;
                // We may have set this when state went to LeavingRoom — clear so a
                // future legitimate leave doesn't mistakenly cancel match-result
                // counting. Round-5 refinement: NOT while the deliberate leave is
                // itself still in flight (the leave-event consumer or the next
                // successful ranked join owns it then; a hung leave that never
                // lands leaves the flag for the join-success clear — accepted
                // residual, favors the innocent player).
                if (!giveUpLeaveInFlight)
                {
                    try { GameStateWatcher.LeavingForRanked = false; } catch { }
                }
                if (wasOvt)
                {
                    try { ApiClient.OvtLeaveQueue(); } catch { }
                    CompetitiveUI.ShowNotificationCritical("Couldn't join the 1v2 match — your lobby was dissolved. Please requeue.", new Color(1f, 0.4f, 0.4f), 8f);
                }
                else if (wasFfa)
                {
                    // Same #150 lifecycle as 1v2: a failed join must dissolve the
                    // FFA lobby server-side or the husk re-feeds this dead room.
                    // Bug 392 sweep: stays UNTAGGED. The room was never
                    // entered, so there is no in-room exit to attest, and an
                    // in-room tag here would veto the dissolution this call
                    // exists to cause. The cause store is dropped for the same
                    // reason — a failed join is a plausible neighbour of a
                    // transport failure, and it must not inherit one.
                    try { TransportExit.ClearCause(); } catch { }
                    try { ApiClient.FfaLeaveQueue(label: "join_gave_up"); } catch { }
                    // V11 D3 (D-Q6): under JoinGate the others may start short
                    // or re-form without this seat, so today's text is untrue.
                    if (gatedGiveUp)
                        CompetitiveUI.ShowNotificationCritical("You could not connect in time. No penalty. Queue again when ready.", new Color(1f, 0.4f, 0.4f), 8f);
                    else
                        CompetitiveUI.ShowNotificationCritical("Couldn't join the FFA match — your lobby was dissolved. Please requeue.", new Color(1f, 0.4f, 0.4f), 8f);
                }
                else
                {
                    CompetitiveUI.ShowNotificationCritical("Couldn't join the ranked match — please requeue.", new Color(1f, 0.4f, 0.4f), 8f);
                }
                return;
            }

            // Tournament rooms only: refuse to START a run without a
            // server-supplied region. Deliberately gated on Idle + not yet
            // initiated so it can never interfere with a join already in
            // flight, and placed here rather than inside StartNCHConnect so
            // the hold has its own bounded window instead of silently parking
            // the state machine at Idle forever (#98/#272).
            if (state == JoinState.Idle && !joinInitiated && !GateTournamentRegion(pendingRoom)) return;

            switch (state)
            {
                case JoinState.Idle:
                    if (joinInitiated) return;

                    // If already in the correct room, done
                    if (PhotonNetwork.InRoom)
                    {
                        string currentRoom = PhotonNetwork.CurrentRoom?.Name ?? "";
                        if (currentRoom == pendingRoom)
                        {
                            OnJoinedRankedRoom(currentRoom);
                            return;
                        }
                        // In a different room — need to leave first
                        // Fresh retry budget for a NEW target (round-4 find
                        // C2: after room A's first timeout the machine idles
                        // with joinAttempts=1, and a replacement B arriving
                        // then inherited A's consumed budget).
                        if (!string.Equals(pendingRoom, targetRoom, StringComparison.Ordinal)) joinAttempts = 0;
                        targetRoom = pendingRoom;
                        targetRegion = Plugin.PendingRankedRegion;
                        joinInitiated = true;
                        GameStateWatcher.LeavingForRanked = true;
                        // July 22 item 2: flag the deliberate leave so observers'
                        // leaver banner says "left for a ranked match" instead of
                        // implying a rage-quit. Best-effort — prop may not
                        // replicate before the leave lands on slow links.
                        try
                        {
                            var lvProps = new ExitGames.Client.Photon.Hashtable();
                            lvProps["cr_lv_rk"] = "1";
                            PhotonNetwork.LocalPlayer?.SetCustomProperties(lvProps);
                        }
                        catch { }
                        PhotonNetwork.LeaveRoom();
                        Plugin.Log.LogInfo("[QUEUE-JOINER] Leaving current room before ranked join...");
                        JoinTimeline.Step("leave_room", "from=" + JoinTimeline.Nonce(currentRoom));
                        state = JoinState.LeavingRoom;
                        if (JoinGate) FfaAssembly.PostAttempt(joinAttempts + 1, "leave");
                        stateTimer = 0f; stateStartedRt = Time.realtimeSinceStartup;
                        return;
                    }

                    // Not in a room — go straight to connecting
                    // Fresh budget on target change (round-4 find C2, same as
                    // the in-room pickup above).
                    if (!string.Equals(pendingRoom, targetRoom, StringComparison.Ordinal)) joinAttempts = 0;
                    targetRoom = pendingRoom;
                    targetRegion = Plugin.PendingRankedRegion;
                    StartNCHConnect();
                    break;

                case JoinState.LeavingRoom:
                    // Wait for Photon to fully leave the room
                    if (!PhotonNetwork.InRoom)
                    {
                        Plugin.Log.LogInfo("[QUEUE-JOINER] Left room, starting NCH connect...");
                        JoinTimeline.Step("left_room");
                        // Small delay to let Photon settle
                        StartNCHConnect();
                    }
                    break;

                case JoinState.Connecting:
                    // NCH coroutine is running, wait for room join
                    if (PhotonNetwork.InRoom)
                    {
                        string cur = PhotonNetwork.CurrentRoom?.Name ?? "";
                        if (cur == targetRoom)
                        {
                            OnJoinedRankedRoom(cur);
                            return;
                        }
                    }
                    break;

                case JoinState.WaitingForRoom:
                    if (PhotonNetwork.InRoom)
                    {
                        string cur = PhotonNetwork.CurrentRoom?.Name ?? "";
                        if (cur == targetRoom)
                        {
                            OnJoinedRankedRoom(cur);
                            return;
                        }
                    }
                    break;
            }
        }

        /// <summary>Gate on the ONE room type where an empty region is a bug
        /// rather than a default. Returns true to let the join proceed, false
        /// to hold this frame.
        ///
        /// WHY THIS EXISTS. StartNCHConnect sets RegionSelector.region only
        /// when the region string is non-empty, and then sets m_ForceRegion
        /// UNCONDITIONALLY — and NCH.WaitForConnect does
        /// `if (hasRegionSelect || m_ForceRegion) ConnectToRegion(RegionSelector.region)`.
        /// So an empty region has never meant "let Photon choose": it means
        /// each client force-connects to whatever its own region dropdown last
        /// held (RegionSelector.region, a static loaded from PlayerPrefs
        /// "Region" when the menu builds). Two tournament opponents with
        /// different dropdowns then create two different rooms with the same
        /// name in two different regions, each sits alone, and both take a
        /// no-show forfeit. That is learning #49 verbatim.
        ///
        /// Do NOT try to fix that by clearing m_ForceRegion: RegionSelector's
        /// own Start sets NCH.hasRegionSelect = true, and the condition is an
        /// OR — so once the main menu has been shown, ROUNDS force-connects to
        /// the dropdown either way. Supplying the region is the only lever.
        ///
        /// The ladder here is the client half of the region design, and every
        /// rung is a value the SERVER sent:
        ///   1. the region the dispatcher passed (per-match, or the
        ///      tournament-wide value from the Tournaments tab);
        ///   2. the per-match region on the active-match row, which the 20s
        ///      heartbeat may have filled in since the dispatch;
        ///   3. after GRACE, the tournament-wide region for that same
        ///      tournament;
        ///   4. give up.
        ///
        /// There is deliberately NO rung that picks a region locally. Not the
        /// dropdown (that is the bug), and not a hardcoded "us" either: the
        /// server's own fallback ladder ends at "us", so a client that also
        /// ends at "us" would agree today and silently disagree the moment the
        /// server's last rung changes — and a disagreement here costs both
        /// players their run. Giving up is the honest outcome, and it is not
        /// permanent: clearing the pending room lets the tournament heartbeat's
        /// 60s re-arm dispatch again, so a region that arrives late still
        /// connects the match.
        ///
        /// Non-tournament rooms are untouched, and that is not an oversight:
        /// every queue-lock path server-side coerces the room's region with
        /// `or "us"`, so a ranked/2v2/1v2/FFA room is never issued without one
        /// and this branch would be dead weight there. The tournament lock
        /// instead takes the MODE of what the signups reported, which is the
        /// hole. Their failure modes differ too — requeue vs forfeit the
        /// bracket.
        ///
        /// KIND: gated on the ROOM PREFIX, so it covers async sct- dispatches
        /// as well. That is deliberate and fails closed: if any async path
        /// still dispatches a room, it holds instead of splitting. Now that
        /// async coordinates its own lobby, the honest outcome for it is "no
        /// auto-connect", which is what this produces — hence the give-up
        /// message says nothing sync-specific.</summary>
        private bool GateTournamentRegion(string pendingRoom)
        {
            if (string.IsNullOrEmpty(pendingRoom)
                || !pendingRoom.StartsWith("sct-", StringComparison.Ordinal))
            {
                sctRegionWaitRoom = null;
                sctRegionWaitStart = -1f;
                return true;
            }

            // Restart the window for a different room (a new bracket round
            // dispatches a new sct- room and must not inherit the old wait).
            if (!string.Equals(sctRegionWaitRoom, pendingRoom, StringComparison.Ordinal))
            {
                sctRegionWaitRoom = pendingRoom;
                sctRegionWaitStart = -1f;
                sctRegionRepollAt = 0f;
            }

            float waited = sctRegionWaitStart >= 0f
                ? Time.unscaledTime - sctRegionWaitStart
                : 0f;

            string region = (Plugin.PendingRankedRegion ?? "").Trim();
            if (region.Length == 0)
            {
                // Rung 2, and rung 3 once the grace window has elapsed.
                bool allowTournamentLevel =
                    sctRegionWaitStart >= 0f && waited >= SCT_REGION_GRACE_SECONDS;
                try
                {
                    region = (ApiClient.TournamentRegionForRoom(pendingRoom, allowTournamentLevel) ?? "").Trim();
                }
                catch { region = ""; }
                if (region.Length > 0)
                {
                    // Record it on the pending room so the state machine below
                    // (and anything else reading PendingRankedRegion) sees the
                    // resolved value. Same room name, so the replacement fence
                    // in Update cannot trip on it.
                    Plugin.SetPendingRoom(pendingRoom, region);
                    Plugin.Log.LogInfo($"[TOURNAMENT-REGION] resolved '{region}' for {pendingRoom} after {waited:F0}s (tournament-level rung allowed: {allowTournamentLevel})");
                }
            }

            if (region.Length > 0)
            {
                sctRegionWaitStart = -1f;
                return true;
            }

            if (sctRegionWaitStart < 0f)
            {
                sctRegionWaitStart = Time.unscaledTime;
                sctRegionRepollAt = 0f;
                Plugin.Log.LogWarning($"[TOURNAMENT-REGION] missing for {pendingRoom} — holding the join and re-polling. NOT falling back to the local region dropdown (#49).");
                if (!string.Equals(sctRegionWaitNotifiedRoom, pendingRoom, StringComparison.Ordinal))
                {
                    sctRegionWaitNotifiedRoom = pendingRoom;
                    CompetitiveUI.ShowNotification("Tournament match found - waiting for the server to pick a region...", new Color(1f, 0.85f, 0.4f), 6f);
                }
                return false;
            }

            if (Time.unscaledTime >= sctRegionRepollAt)
            {
                sctRegionRepollAt = Time.unscaledTime + SCT_REGION_REPOLL_SECONDS;
                try { ApiClient.RepollTournamentRegion(); } catch { }
            }

            if (waited >= SCT_REGION_GIVEUP_SECONDS)
            {
                Plugin.Log.LogError($"[TOURNAMENT-REGION] no server-supplied region for {pendingRoom} after {waited:F0}s — refusing to auto-connect (the heartbeat re-arms this dispatch, so a late region still works)");
                if (!string.Equals(sctRegionGaveUpNotifiedRoom, pendingRoom, StringComparison.Ordinal))
                {
                    sctRegionGaveUpNotifiedRoom = pendingRoom;
                    CompetitiveUI.ShowNotificationCritical("Tournament match can't auto-connect: the server has not set a region. Open the Tournaments tab.", new Color(1f, 0.4f, 0.4f), 12f);
                }
                Plugin.ClearPendingRoom();
                sctRegionWaitRoom = null;
                sctRegionWaitStart = -1f;
            }
            return false;
        }

        private void StartNCHConnect()
        {
            joinInitiated = true;
            var nch = NetworkConnectionHandler.instance;

            if (nch == null)
            {
                Plugin.Log.LogError("[QUEUE-JOINER] NetworkConnectionHandler.instance is null!");
                return;
            }

            try
            {
                // Disconnect fully if still connected (e.g. on master server but not in room)
                if (PhotonNetwork.IsConnected)
                {
                    PhotonNetwork.Disconnect();
                    Plugin.Log.LogInfo("[QUEUE-JOINER] Disconnecting from Photon...");
                }

                // Sept 6 (bug 336 — the "matched but never connected" family, A2):
                // vanilla's WaitForConnect is `while (!isConnectedToMaster)`, and
                // that flag is set by OnConnectedToMaster — which PUN also raises
                // for the OFFLINE menu room: leaving it fires OnLeftRoom (clears
                // the flag) and then OnConnectedToMaster (sets it again). The
                // Disconnect() above ends with DisconnectByClientLogic, a cause
                // vanilla's OnDisconnected deliberately ignores, so the flag
                // reaches this point TRUE with no connection behind it, the wait
                // loop exits in the same frame ConnectToRegion began, and
                // JoinOrCreateRoom fails with "Client is on NameServer ...
                // (State: ConnectingToNameServer)". The retry repeats the same
                // steps, so it fails the same way. Reset it here — after the
                // Disconnect, before the coroutine below runs its first MoveNext
                // synchronously inside StartCoroutine. `was=True` in a field log
                // is the proof of this diagnosis.
                try
                {
                    bool wasConnectedFlag = nch.isConnectedToMaster;
                    nch.isConnectedToMaster = false;
                    Plugin.Log.LogInfo($"[QUEUE-JOINER] connect flag reset (was={wasConnectedFlag}, offline={PhotonNetwork.OfflineMode}, state={PhotonNetwork.NetworkClientState})");
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[QUEUE-JOINER] connect flag reset failed: {ex.Message}"); }

                // Close menus
                try { CharacterCreatorHandler.instance?.CloseMenus(); } catch { }
                try { MainMenuHandler.instance?.Close(); } catch { }

                // Set target region.
                //
                // READ THIS BEFORE CHANGING THE SHAPE: because m_ForceRegion is
                // set unconditionally two lines below, an empty region here does
                // NOT mean "let Photon pick" — it leaves RegionSelector.region
                // at whatever the player's own dropdown last held, and NCH then
                // force-connects there. For a queue-issued room that is a
                // requeue at worst; for a tournament room it is two players in
                // two same-named rooms in two regions and a double forfeit
                // (#49). GateTournamentRegion holds sct- runs at Idle until the
                // server names a region, so this branch should be unreachable
                // for them — and if it is ever reached anyway, abort instead of
                // guessing.
                if (!string.IsNullOrEmpty(targetRegion))
                {
                    RegionSelector.region = targetRegion;
                    Plugin.Log.LogInfo($"[QUEUE-JOINER] Set RegionSelector.region = {targetRegion}");
                }
                else if ((targetRoom ?? "").StartsWith("sct-", StringComparison.Ordinal))
                {
                    Plugin.Log.LogError($"[TOURNAMENT-REGION] StartNCHConnect reached with no region for {targetRoom} — aborting rather than force-connecting to the local dropdown");
                    joinInitiated = false;   // let the gate own the retry
                    return;
                }

                // Force region (via Publicizer)
                nch.m_ForceRegion = true;
                Plugin.Log.LogInfo("[QUEUE-JOINER] Set m_ForceRegion = true");
                // July 21 review fix: clear any stale vanilla search context — the
                // mod owns the connection now. Without this, a quickplay search
                // abandoned for a ranked match leaves m_searchingType=Quickmatch,
                // and a later dead-state recovery would auto-requeue the player
                // into the VANILLA queue instead of returning to menu. Vanilla-
                // safe: readers treat None like "no special search".
                try { nch.m_searchingType = (NetworkConnectionHandler.SearchingType)0; } catch { }

                // Loading screen
                try { TimeHandler.instance.gameStartTime = 1f; } catch { }
                try { LoadingScreen.instance?.StartLoading(); } catch { }

                // NCH handles: disconnect wait → ConnectToRegion → wait for master → execute callback
                string capturedRoom = targetRoom;
                int capturedGen = ++joinGeneration;
                nch.StartCoroutine(nch.DoActionWhenConnected(() =>
                {
                    // Sept 6 (bug 336, A2 second line): vanilla's callback means
                    // "its own connected flag is set", not "the client is on the
                    // master server". The join is issued by JoinWhenMasterReady,
                    // which waits for ClientState.ConnectedToMasterServer with
                    // OfflineMode off (CLAUDE.md hard rule, #21) inside the
                    // joiner's own 30 s attempt budget, and dies silently when a
                    // retry supersedes this attempt.
                    try { nch.StartCoroutine(JoinWhenMasterReady(capturedRoom, capturedGen)); }
                    catch (Exception ex) { Plugin.Log.LogError($"[QUEUE-JOINER] join scheduling failed: {ex.Message}"); }
                }));

                Plugin.Log.LogInfo($"[QUEUE-JOINER] Started NCH connection sequence for room: {targetRoom}");
                JoinTimeline.Step("nch_start", "force=" + (string.IsNullOrEmpty(RegionSelector.region) ? "-" : RegionSelector.region));
                state = JoinState.Connecting;
                if (JoinGate) FfaAssembly.PostAttempt(joinAttempts + 1, "connect");
                stateTimer = 0f; stateStartedRt = Time.realtimeSinceStartup;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[QUEUE-JOINER] StartNCHConnect failed: {ex.Message}");
                joinInitiated = false;
            }
        }

        // Sept 6 (A2): generation stamp — a retry bumps it, and the previous
        // attempt's pending join dies instead of firing a second JoinOrCreate.
        private int joinGeneration = 0;

        /// <summary>Second line of the A2 fix: own the join gate (#21). Vanilla's
        /// DoActionWhenConnected fires when ITS flag says connected; this waits,
        /// frame by frame, for the real client state before issuing the join, and
        /// gives up when a retry (new generation) or a reset (state left Connecting)
        /// owns the connection. A pending-room change falls through to
        /// IssueJoinOrCreate, whose cancellation check decides between abort-to-menu
        /// and dying quietly — exactly as the inline callback did before the split.
        /// Bounded by the joiner's 30 s attempt timer, which resets state to Idle.</summary>
        private System.Collections.IEnumerator JoinWhenMasterReady(string capturedRoom, int gen)
        {
            int waitedFrames = 0;
            string exitKind = "pending_changed";
            while (true)
            {
                // Order matters: a pending-room change falls through to
                // IssueJoinOrCreate FIRST, because the joiner's Update() resets
                // state to Idle in the same frame the room is cleared — and the
                // cleared case must still reach NetworkRestart, the one honest
                // abort-to-menu lever, exactly as the inline callback did.
                if (!string.Equals(Plugin.PendingRankedRoom, capturedRoom, StringComparison.Ordinal)) break;
                if (gen != joinGeneration || state != JoinState.Connecting) yield break;
                bool ready = false;
                string st = "?";
                try
                {
                    st = PhotonNetwork.NetworkClientState.ToString();
                    ready = PhotonNetwork.NetworkClientState == Photon.Realtime.ClientState.ConnectedToMasterServer
                            && !PhotonNetwork.OfflineMode;
                }
                catch { }
                if (ready) { exitKind = "ready"; break; }
                if (waitedFrames == 0)
                {
                    Plugin.Log.LogWarning($"[QUEUE-JOINER] connected callback fired with state={st} offline={PhotonNetwork.OfflineMode} — holding JoinOrCreate until ConnectedToMasterServer");
                    JoinTimeline.Step("master_hold", "state=" + st);
                }
                waitedFrames++;
                yield return null;
            }
            JoinTimeline.Step("master_ready", "frames=" + waitedFrames.ToString(System.Globalization.CultureInfo.InvariantCulture) + " exit=" + exitKind);
            if (waitedFrames > 0)
                Plugin.Log.LogInfo($"[QUEUE-JOINER] master server ready after {waitedFrames} frames — issuing the join");
            IssueJoinOrCreate(capturedRoom);
        }

        /// <summary>The former inline connected-callback body, unchanged apart from
        /// logging the JoinOrCreateRoom result (A2, third line).</summary>
        private void IssueJoinOrCreate(string capturedRoom)
        {
            try
            {
                // Cancellation check (lobby impl review rounds 2+3):
                // the pending-room static is the cancellation token —
                // a Leave (or a replacement lock) clears/repoints it
                // between capture and connect, and a canceled join
                // must NOT still enter the dead room. Applies to all
                // modes. NEVER StopLoading here (round-3 find C1:
                // that is ROUNDS' match-found SUCCESS transition, not
                // a cancel — it can activate gameplay with no room).
                // Cleared -> the player wants OUT: NetworkRestart is
                // the codebase's one honest abort-to-menu lever.
                // Replaced -> the NEW room's joiner run owns the
                // loading screen and connection; this stale callback
                // simply dies.
                if (!string.Equals(Plugin.PendingRankedRoom, capturedRoom, StringComparison.Ordinal))
                {
                    bool cleared = string.IsNullOrEmpty(Plugin.PendingRankedRoom);
                    Plugin.Log.LogWarning($"[QUEUE-JOINER] pending room changed/cleared since capture ('{capturedRoom}' -> '{Plugin.PendingRankedRoom ?? "(none)"}') — aborting join (cleared={cleared})");
                    if (cleared)
                    {
                        try { NetworkConnectionHandler.instance.NetworkRestart(); } catch { }
                    }
                    return;
                }
                // V11 D3: the region check, logged in every mode; it ends the
                // attempt only under JoinGate and the server's guard flag.
                if (!RegionCheck()) return;
                Plugin.Log.LogInfo($"[QUEUE-JOINER] Connected! JoinOrCreate: {capturedRoom}");
                // 2v2 rooms have a `team_` prefix (set by /team/queue/ready
                // server-side). Bump MaxPlayers to 4 and stamp `cr_ff`, the
                // 2v2 ROOM MARKER (GameStateWatcher reads it for ranked
                // detection, #65). It has never meant "friendly fire" — no
                // ProjectileCollision patch exists; the friendly-fire rule
                // rides `cr_rules` (RoomRules), stamped further down.
                bool is2v2 = capturedRoom != null && capturedRoom.StartsWith("team_");
                // 1v2: ovt_ rooms hold 3. Review CRITICAL — without this the
                // room was created MaxPlayers=2 (the 1v1 default) and the
                // third player could never join, so 1v2 could never start.
                bool is1v2 = capturedRoom != null && capturedRoom.StartsWith("ovt_");
                // FFA: ffa_ rooms hold the locked lobby size (3-10) —
                // learning #146a: a missing MaxPlayers branch means the
                // Nth player can never join. The creator stamps the
                // lobby size as a room prop so late joiners (and any
                // client whose queue payload got lost) read one truth.
                bool isFfa = capturedRoom != null && capturedRoom.StartsWith("ffa_");
                int ffaCount = Plugin.PendingFfaCount > 0 ? Plugin.PendingFfaCount : 10;
                var roomProps = new ExitGames.Client.Photon.Hashtable
                {
                    { "C2", capturedRoom }
                };
                if (is2v2) roomProps["cr_ff"] = true;
                // Room rules (§5.2): the creator stamps the string the server
                // issued for this room; every joiner compares it with its own
                // issued string (RoomRules.LatchOnJoin) and leaves on a
                // mismatch. Not stamped when nothing was issued — tournament
                // rooms play the defaults, an FFA room carries its settings on
                // its own property, an older server sends none — and a joiner
                // of such a room expects the defaults and accepts an absent
                // property only then.
                // Read here, inside the pending-room guard above: the tuple is
                // still staged (it is cleared only once InRoom is confirmed),
                // so this is the string issued for THIS pending incarnation.
                string rulesToStamp = RoomRules.PropToStamp();
                if (!string.IsNullOrEmpty(rulesToStamp)) roomProps[RoomRules.PropKey] = rulesToStamp;
                // July 22 item 3: solo-extra-pick flag rides the ROOM
                // props (design doc: room-prop carrier) — all 3 clients
                // got it in the lock payload, so whichever creates the
                // room stamps it and late joiners read one truth.
                if (is1v2 && ApiClient.OvtSoloExtraPick) roomProps["cr_ovt_xp"] = true;
                if (isFfa) roomProps["cr_ffa_n"] = ffaCount;
                // Spectator seats (design §4.1): server-issued rooms
                // reserve SEAT_CAP extra Photon actors above the
                // fighter count. Vanilla match-found fires on a
                // hardcoded PlayerList.Length == 2, and every mod
                // force-start path counts PlayersNeeded — neither
                // reads MaxPlayers, so the bump is start-inert. The
                // grant server only admits spectators once the match
                // is live (all fighters attested "battle"), so a
                // spectator can never occupy a seat pre-assembly.
                int fighterTarget = is2v2 ? 4 : (is1v2 ? 3 : (isFfa ? ffaCount : 2));
                var roomOptions = new Photon.Realtime.RoomOptions
                {
                    MaxPlayers = (byte)(fighterTarget + SpectatorSession.SEAT_CAP),
                    IsOpen = true,
                    // Queue rooms are joined by exact server-issued
                    // name only — never listed, never lobby-matched.
                    // Hidden so the reserved seats cannot be found by
                    // room browsing (design §4.1, Codex r1 find 1).
                    IsVisible = false,
                    CustomRoomProperties = roomProps,
                    CustomRoomPropertiesForLobby = new string[] { "C2" }
                };
                var lobby = new Photon.Realtime.TypedLobby("RoomCodeLobby", Photon.Realtime.LobbyType.SqlLobby);
                // V11 item 6: a re-form's pre-join properties, set here,
                // immediately before JoinOrCreateRoom and outside any room (#287).
                if (isFfa && FfaAssembly.PrejoinAtJoin && FfaAssembly.StagedPrejoin != null && !PhotonNetwork.InRoom)
                {
                    FfaAssembly.PrejoinAtJoin = false;
                    try { PhotonNetwork.LocalPlayer?.SetCustomProperties(FfaAssembly.StagedPrejoin); }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] staged pre-join SetCustomProperties: {ex.Message}"); }
                }
                JoinTimeline.Step("join_issued", "max=" + roomOptions.MaxPlayers.ToString(System.Globalization.CultureInfo.InvariantCulture));
                bool accepted = PhotonNetwork.JoinOrCreateRoom(capturedRoom, roomOptions, lobby);
                JoinTimeline.Step("join_result", accepted ? "ok" : "false offline=" + (PhotonNetwork.OfflineMode ? "true" : "false"));
                // Sept 6 (A2, third line): two attempts that fail identically
                // must be visible as such — vanilla logs the failure text, this
                // logs which attempt and from which client state.
                if (accepted)
                {
                    Plugin.Log.LogInfo($"[QUEUE-JOINER] JoinOrCreateRoom({capturedRoom}) accepted (state={PhotonNetwork.NetworkClientState})");
                }
                else
                {
                    Plugin.Log.LogWarning($"[QUEUE-JOINER] JoinOrCreateRoom({capturedRoom}) returned false (state={PhotonNetwork.NetworkClientState}, offline={PhotonNetwork.OfflineMode})");
                    // V11 D3/I2: under JoinGate the failure ends the attempt now.
                    if (JoinGate)
                    {
                        try { FfaAssembly.PostFailed("join", int.MinValue); } catch { }
                        EndAttemptNow("join_false");
                    }
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[QUEUE-JOINER] JoinOrCreate failed: {ex.Message}");
            }
        }

        private void OnJoinedRankedRoom(string roomName)
        {
            Plugin.Log.LogInfo($"[QUEUE] In ranked room: {roomName}!");
            JoinTimeline.Step("in_ranked_room", "via=" + (state == JoinState.Idle ? "idle" : "joining"));
            // Room rules (§5.2): compare the room's stamped rules with the
            // issued expectation BEFORE the pending tuple is cleared. A
            // mismatch is terminal for this seat: leave now (the joiner's own
            // abort-to-menu lever), and the existing abandon / no-show paths
            // settle the sitting. Nothing is played under rules this seat was
            // not admitted to.
            var rulesVerdict = RoomRules.LatchVerdict.Defaults;
            try { rulesVerdict = RoomRules.LatchOnJoin(PhotonNetwork.CurrentRoom, "fighter"); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[ROOM-RULES] latch threw: {ex.Message}"); }
            if (rulesVerdict == RoomRules.LatchVerdict.Mismatch)
            {
                try { CompetitiveUI.ShowNotificationCritical(I18n.Tr("Room settings did not match — left the room"), new Color(1f, 0.4f, 0.4f), 8f); } catch { }
                Plugin.ClearPendingRoom();
                joinInitiated = false;
                state = JoinState.Idle;
                stateTimer = 0f; stateStartedRt = Time.realtimeSinceStartup;
                joinAttempts = 0;
                try { GameStateWatcher.LeavingForRanked = false; } catch { }
                try { NetworkConnectionHandler.instance.NetworkRestart(); } catch { }
                return;
            }
            Plugin.ClearPendingRoom();
            joinInitiated = false;
            state = JoinState.Idle;
            stateTimer = 0f; stateStartedRt = Time.realtimeSinceStartup;
            joinAttempts = 0;
            // The leave-for-ranked is COMPLETE once we're in the target room —
            // consume the flag here too (lobby impl round 5: an exit path that
            // skipped GameStateWatcher's consumer left it set, and the next
            // GENUINE opponent DC in this room was misclassified as our own
            // leave-for-ranked).
            try { GameStateWatcher.LeavingForRanked = false; } catch { }

            // Clear force region flag so NCH works normally for vanilla play afterward
            try
            {
                var nch = NetworkConnectionHandler.instance;
                if (nch != null)
                    nch.m_ForceRegion = false;
            }
            catch { }

            CompetitiveUI.ShowNotification("Joined the match!", Color.green, 5f);
            CompetitiveRoundsBehaviour.HideMainMenu();

            string steamId = GameStateWatcher.LocalSteamId;
            if (!string.IsNullOrEmpty(steamId) && steamId != "unknown")
                ApiClient.LeaveQueue(steamId);

            // The 1v2 queue phase ends the moment the room join lands — reset
            // the status so the tab doesn't keep saying "Match found! Joining…"
            // after the series (the lock lineup stays cached for the HUD).
            if (roomName != null && roomName.StartsWith("ovt_"))
                ApiClient.OvtQueueStatus = "";
            if (roomName != null && roomName.StartsWith("ffa_"))
                ApiClient.FfaQueueStatus = "";

            // 2v2 / 1v2: bypass ROUNDS' character-select press-any-key gate.
            // Vanilla PlayerAssigner.Update polls input devices and only fires
            // CreatePlayer when the user mashes a key — but the character-select
            // widget container only has 2 child slots, so players assigned to
            // slots 2/3 don't see a prompt and never trigger their local
            // CreatePlayer. Result: 2 of N spawn correctly, the rest sit on the
            // menu while the room sits empty from their perspective. Auto-fire
            // CreatePlayer ourselves (which routes through the CreatePlayer
            // override and uses the server-issued slot).
            // V11 item 1: a gated room's arrival (the identity check, the
            // arrived POST, the assembly loop). In an admission room the spawn
            // waits for the server's permission; in a fallback room it runs as
            // today.
            bool gatedRoom = FfaAssembly.IsGatedRoom(roomName);
            if (gatedRoom)
            {
                try { FfaAssembly.OnArrived(roomName); }
                catch (Exception ex) { Plugin.Log.LogWarning("[FFA-ASM] arrival: " + ex.Message); }
            }
            if (Plugin.Pending2v2Slot >= 0 || Plugin.PendingOvtSlot >= 0 || Plugin.PendingFfaSlot >= 0)
            {
                if (gatedRoom && FfaAssembly.IsAdmissionRoom(roomName))
                    StartCoroutine(FfaAssembly.GatedSpawn(Auto2v2SpawnCoroutine));
                else
                    StartCoroutine(Auto2v2SpawnCoroutine());
            }
        }

        private System.Collections.IEnumerator Auto2v2SpawnCoroutine()
        {
            // Wait briefly for scene + PlayerAssigner to spin up. The scene
            // reload to "Main" happens around the same time as the Photon room
            // join, so PlayerAssigner.instance is usually null for ~1 second.
            float spawnStartRt = Time.realtimeSinceStartup;
            float deadline = Time.realtimeSinceStartup + 12f;
            int tickLogCount = 0;
            while (Time.realtimeSinceStartup < deadline)
            {
                if (Plugin.Pending2v2Slot < 0 && Plugin.PendingOvtSlot < 0 && Plugin.PendingFfaSlot < 0)
                {
                    Plugin.Log.LogInfo("[2v2] Auto-spawn aborted — pending slot cleared mid-wait");
                    yield break;
                }
                if (!PhotonNetwork.InRoom)
                {
                    Plugin.Log.LogInfo("[2v2] Auto-spawn aborted — not in Photon room mid-wait");
                    yield break;
                }
                var pa = PlayerAssigner.instance;
                if (pa != null && !pa.hasCreatedLocalPlayer)
                {
                    InputDevice device = null;
                    try
                    {
                        if (InputManager.ActiveDevices != null && InputManager.ActiveDevices.Count > 0)
                            device = InputManager.ActiveDevices[0];
                    }
                    catch { }
                    Plugin.Log.LogInfo($"[2v2] Auto-spawning local player (slot={Diag2v2.PendingSlot()}, device={(device != null ? "keyboard" : "null")})");
                    bool ok = false;
                    try { pa.CreatePlayer(device, false); ok = true; }
                    catch (Exception ex) { Plugin.Log.LogError($"[2v2] Auto-spawn CreatePlayer failed: {ex.Message}"); }
                    if (ok)
                    {
                        JoinTimeline.Step("spawned", "after_ms=" + ((int)((Time.realtimeSinceStartup - spawnStartRt) * 1000f)).ToString(System.Globalization.CultureInfo.InvariantCulture));
                        // Tell server we spawned, so it can detect when fewer than
                        // 4 of 4 confirm within the assembly deadline and cancel.
                        try
                        {
                            string sid = MatchTracker.LocalSteamId;
                            string seriesId = ApiClient.ActiveTeamSeriesId;
                            if (!string.IsNullOrEmpty(sid) && !string.IsNullOrEmpty(seriesId))
                                ApiClient.SendTeamSpawnConfirm(seriesId, sid);
                        }
                        catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] spawn-confirm send error: {ex.Message}"); }
                        yield break;
                    }
                }
                else if (tickLogCount < 6)
                {
                    string reason = pa == null ? "PlayerAssigner.instance == null"
                                  : pa.hasCreatedLocalPlayer ? "local player already exists"
                                  : "?";
                    Plugin.Log.LogInfo($"[2v2] Auto-spawn waiting: {reason} (tick {tickLogCount})");
                    tickLogCount++;
                }
                yield return new WaitForSeconds(0.5f);
            }
            if (PlayerAssigner.instance == null || !PlayerAssigner.instance.hasCreatedLocalPlayer)
            {
                Plugin.Log.LogWarning("[2v2] Auto-spawn timed out — PlayerAssigner never initialized or local player never spawned");
                JoinTimeline.Step("spawn_timeout", "after_ms=" + ((int)((Time.realtimeSinceStartup - spawnStartRt) * 1000f)).ToString(System.Globalization.CultureInfo.InvariantCulture));
                // V11 I2: failed phase=spawn, telemetry only (the body rule decides).
                if (FfaAssembly.IsGatedRoom(FfaAssembly.CurrentRoomName()))
                {
                    try { FfaAssembly.PostFailed("spawn", int.MinValue); } catch { }
                }
            }
        }
    }

    public class CompetitiveRoundsBehaviour : MonoBehaviour
    {
        private bool initialized = false;
        private float startupTimer = 0f;
        private bool startupComplete = false;

        /* FPS governor state (Aug 23 rewrite — review r2 M3/M4). Three
         * stages want a frame cap: the unfocused cap (Aug 6, 120), deep idle
         * (Aug 7 / Aug 18, 15) and the broadcast-seat render cap (Aug 23,
         * BroadcastFpsCap while the director is active). They used to be
         * three independent save/restore latches layered on each other, and
         * that layering lost the true baseline: a stage could save a value a
         * DEEPER stage had written, and a stage could clear its latch while
         * its restore was masked — so the player's real targetFrameRate was
         * gone for the session (M3). ONE ownership record instead: the
         * baseline is captured exactly once, when no stage owns the values,
         * and restored (value-checked, only what is still ours) when no
         * stage wants a cap. Stages only ever compute "desired".
         *
         * STATIC on purpose: the persistent host is replaced via OnDestroy
         * respawn (a fresh CompetitiveRoundsBehaviour) while Unity still
         * holds whatever the old instance wrote — instance fields would read
         * "nothing applied" and the baseline could never be restored (the
         * second M3 trigger). unfocusedSinceRt is static for the same
         * reason (a respawn must not restart the 60s deep-idle clock).
         *
         * Vanilla never touches targetFrameRate (only vSyncCount,
         * Optionshandler.cs:75), so -1/uncapped is the common baseline. */
        private static bool fpsOwning = false;            // we hold the engine values
        private static int fpsBaseTarget = -1;            // pre-ownership targetFrameRate
        private static int fpsBaseVsync = 0;              // pre-ownership vSyncCount
        private static int fpsWrittenTarget = 0;          // the target we last wrote
        private static int fpsDesiredLast = 0;            // last desired cap (0 = none)
        // A player video-settings change while a NON-broadcast stage owned the
        // values wins: we stand down until the wanted cap changes again.
        private static bool fpsExternalOverride = false;
        private static float fpsReassertLogRt = -999f;
        private static float unfocusedSinceRt = -1f;

        // Ranked queue room joining — now handled by Plugin.Update()
        // (Plugin's MonoBehaviour survives scene changes via BepInEx)

        private void Awake()
        {
            hideFlags = HideFlags.HideAndDontSave;
            gameObject.hideFlags = HideFlags.HideAndDontSave;
            DontDestroyOnLoad(gameObject);
            Plugin.Log.LogInfo("[PERSIST] Behaviour Awake, DontDestroyOnLoad set");
        }

        /// <summary>Aug 7 item 2: all five deep-idle gates in one place. Any
        /// gate failing wakes the engine within one frame (≤67ms at 15fps)
        /// because this ticks first in Update. The pending-slot gate is
        /// load-bearing, not a nicety: queue auto-join fires while unfocused BY
        /// DESIGN (TaskbarFlash exists for that flow) and the Photon handshake
        /// should run at stage-1 speed — the predicate flips BEFORE the room
        /// join begins, exactly when we want to wake.</summary>
        /* Sid, Aug 18 (v1.39.0): pin the broadcast seat's game to WINDOWED
         * 1920x1080. Why a mod-side pin and not settings: ROUNDS' own options
         * system (OptionsData.ApplyScreen -> Screen.SetResolution) reapplies
         * its saved video mode at boot and clamps every choice to
         * Screen.resolutions — which the VM's RDP virtual display enumerates
         * as EMPTY, so neither the in-game picker nor Unity's screenmanager
         * registry values can produce 1920x1080 there. Windowed mode accepts
         * arbitrary sizes regardless of the display's mode list, OBS
         * window-capture reads the client area even when the window clips
         * off a 1080p desktop, and the 30s re-assert outlives any late
         * ApplyScreen from vanilla's options load. Broadcast identity +
         * config gated — inert for every regular player. */
        private float bcastResNextCheckRt;
        private void TickBroadcastWindowPin()
        {
            try
            {
                if (Plugin.modDisabled) return;
                if (Plugin.BroadcastWindowed1080 == null || !Plugin.BroadcastWindowed1080.Value) return;
                // Identity check BEFORE the cooldown stamp (r3 finding 5):
                // stamping first burned the whole first 30s window while the
                // broadcast identity was still resolving at boot, leaving the
                // seat at the wrong capture geometry exactly when the
                // director might already be acquiring a target.
                if (!BroadcastMode.DirectorActive) return;
                if (Time.realtimeSinceStartup < bcastResNextCheckRt) return;
                bcastResNextCheckRt = Time.realtimeSinceStartup + 30f;
                if (Screen.width == 1920 && Screen.height == 1080
                    && Screen.fullScreenMode == FullScreenMode.Windowed) return;
                int oldW = Screen.width, oldH = Screen.height;
                var oldMode = Screen.fullScreenMode;
                Screen.SetResolution(1920, 1080, FullScreenMode.Windowed);
                Plugin.Log.LogInfo($"[BROADCAST] window pinned to 1920x1080 windowed (was {oldW}x{oldH} {oldMode})");
            }
            catch { }
        }

        private bool WantDeepIdle()
        {
            if (Plugin.modDisabled) return false;                       // disabled mod may only restore
            if (Plugin.DeepIdleUnfocused == null || !Plugin.DeepIdleUnfocused.Value) return false;
            if (unfocusedSinceRt < 0f) return false;
            if (Time.realtimeSinceStartup - unfocusedSinceRt < 60f) return false;
            return OutOfPlayForIdle();
        }

        /// <summary>The shared out-of-play gates for BOTH idle arms. Any gate
        /// failing wakes the engine within one frame (≤67ms at 15fps).</summary>
        private bool OutOfPlayForIdle()
        {
            // Aug 11 playtest item 5: a spectator seat is blind to BOTH room
            // gates below — the session quiesces GameStateWatcher before
            // PollRoomState ever writes wasInRoom, and battleOngoing is only
            // set by the suppressed participant lifecycle — so deep idle
            // engaged mid-spectate (proven twice in the Aug 10 log). The
            // IsLocalSpectator gate also covers the joiner window; the direct
            // InRoom check fixes the CLASS for any future watcher-sleeping
            // seat (#122 semantics without depending on wasInRoom).
            try { if (SpectatorSession.IsLocalSpectator) return false; } catch { }
            // r3 finding 10: a granted-but-not-yet-joined broadcast target
            // passed every gate below for up to 15s — the throttle must lift
            // the moment the director leaves Idle, not when the spectator
            // session finally exists. Always false for regular players.
            try { if (BroadcastMode.DirectorBusy) return false; } catch { }
            try { if (PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode) return false; } catch { }
            if (GameStateWatcher.IsInOnlineRoom) return false;          // never in online play (#122-safe accessor)
            try { if (GameManager.instance != null && GameManager.instance.battleOngoing) return false; } catch { }
            if (!string.IsNullOrEmpty(Plugin.PendingRankedRoom)) return false;
            if (Plugin.Pending2v2Slot >= 0 || Plugin.PendingOvtSlot >= 0 || Plugin.PendingFfaSlot >= 0) return false;
            return true;
        }

        /* Sid, Aug 18 ("hibernate the game if it's running too long without
         * viewing/broadcasting a match"): the broadcast VM's game runs 24/7
         * and the focus-gated arm above never engages there — the seat's
         * window HOLDS focus, because nothing else runs on that machine.
         * This arm is focus-INDEPENDENT: broadcast identity + config + the
         * same out-of-play gates, continuously true for 16 minutes.
         *
         * Why a frame throttle and not close/suspend/minimize: the mod is
         * the only credentialed actor that can DISCOVER a match to broadcast
         * (the VM bot has no server credentials by design), a closed game
         * would read as a stale status lease and trigger the bot's fenced
         * ROUNDS replacement, and OBS window-capture stops producing frames
         * for a minimized window. 15 FPS keeps the status-lease writer, the
         * /broadcast/target poll and Photon keepalives all healthy (same
         * analysis as the deep-idle constant above).
         *
         * Why 960s: the director stops public outputs after 900s idle
         * (idle_stop_seconds). Engaging strictly AFTER that means the
         * throttle can never interact with a live output scene, whatever
         * the OBS scene layout captures. */
        // STATIC (review r3 find 3): the FPS ownership it feeds is static, so an
        // instance clock here would reset the 16-minute idle timer on every
        // host respawn and bounce the owned 15 back up to the seat cap.
        private static float broadcastIdleGatesPassRt = -1f;
        private bool WantBroadcastIdle()
        {
            if (Plugin.modDisabled) return false;
            if (Plugin.BroadcastIdleFpsCap == null || !Plugin.BroadcastIdleFpsCap.Value) return false;
            bool seat = false;
            try { seat = BroadcastMode.DirectorActive; } catch { }
            if (!seat) { broadcastIdleGatesPassRt = -1f; return false; }
            if (!OutOfPlayForIdle()) { broadcastIdleGatesPassRt = -1f; return false; }
            if (broadcastIdleGatesPassRt < 0f) { broadcastIdleGatesPassRt = Time.realtimeSinceStartup; return false; }
            return Time.realtimeSinceStartup - broadcastIdleGatesPassRt >= 960f;
        }

        /// <summary>Current display refresh in Hz, 0 if unknown.</summary>
        private static int DisplayRefreshHz()
        {
            try
            {
                double hz = Screen.currentResolution.refreshRateRatio.value;
                if (hz > 1.0 && hz < 1000.0) return (int)Math.Round(hz);
            }
            catch { }
            return 0;
        }

        // design v6 §1 / r7 LOW 9: [Broadcast] TestGstatsSentinel — one run per
        // distinct NEW value; the value present at startup is the baseline and
        // never runs (the same rule as the click directive). Reads the cfg the
        // TestOpenTab tick reloads every 2 s.
        private static string _lastTestGstatsSentinel;
        private void TickTestGstatsSentinel()
        {
            if (Plugin.BroadcastTestGstatsSentinel == null || !BroadcastMode.IsBroadcastIdentity) return;
            string raw = (Plugin.BroadcastTestGstatsSentinel.Value ?? "").Trim();
            if (_lastTestGstatsSentinel == null) { _lastTestGstatsSentinel = raw; return; }
            if (raw == _lastTestGstatsSentinel) return;
            _lastTestGstatsSentinel = raw;
            if (raw.Length == 0) return;
            try { GameStateWatcher.DevGstatsSentinelTest(); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[GSTATS-SENTINEL] FAIL: lever threw {ex.Message}"); }
            // Round 2 finding 3: the freeze-counting epoch rides the same payload.
            GameStateWatcher.DevFreezeEpochSentinelTest();
        }

        // v1.41.0 beta round 2 finding 2: [Broadcast] TestReporterElectionSentinel,
        // the same once-per-distinct-NEW-value grammar and identity gate as the
        // TestGstatsSentinel lever above.
        private static string _lastTestReporterElectionSentinel;
        private void TickTestReporterElectionSentinel()
        {
            if (Plugin.BroadcastTestReporterElectionSentinel == null || !BroadcastMode.IsBroadcastIdentity) return;
            string raw = (Plugin.BroadcastTestReporterElectionSentinel.Value ?? "").Trim();
            if (_lastTestReporterElectionSentinel == null) { _lastTestReporterElectionSentinel = raw; return; }
            if (raw == _lastTestReporterElectionSentinel) return;
            _lastTestReporterElectionSentinel = raw;
            if (raw.Length == 0) return;
            DevReporterElectionSentinelTest();
        }

        // v1.41.0 beta round 2 finding 4: [Broadcast] TestAutoLogConsentSentinel,
        // the same grammar and identity gate as the two levers above.
        private static string _lastTestAutoLogConsentSentinel;
        private void TickTestAutoLogConsentSentinel()
        {
            if (Plugin.BroadcastTestAutoLogConsentSentinel == null || !BroadcastMode.IsBroadcastIdentity) return;
            string raw = (Plugin.BroadcastTestAutoLogConsentSentinel.Value ?? "").Trim();
            if (_lastTestAutoLogConsentSentinel == null) { _lastTestAutoLogConsentSentinel = raw; return; }
            if (raw == _lastTestAutoLogConsentSentinel) return;
            _lastTestAutoLogConsentSentinel = raw;
            if (raw.Length == 0) return;
            AutoLogUpload.DevConsentSentinelTest();
        }

        // v1.41.0 beta round 3 finding 9: [Broadcast] TestChatRevokeSentinel,
        // the same grammar and identity gate as the levers above.
        private static string _lastTestChatRevokeSentinel;
        private void TickTestChatRevokeSentinel()
        {
            if (Plugin.BroadcastTestChatRevokeSentinel == null || !BroadcastMode.IsBroadcastIdentity) return;
            string raw = (Plugin.BroadcastTestChatRevokeSentinel.Value ?? "").Trim();
            if (_lastTestChatRevokeSentinel == null) { _lastTestChatRevokeSentinel = raw; return; }
            if (raw == _lastTestChatRevokeSentinel) return;
            _lastTestChatRevokeSentinel = raw;
            if (raw.Length == 0) return;
            CompetitiveUI.DevChatRevokeSentinelTest();
        }

        // v1.41.0 beta round 3 finding 20: [Broadcast] TestHeartbeatAbortSentinel,
        // the same grammar and identity gate as the levers above.
        private static string _lastTestHeartbeatAbortSentinel;
        private void TickTestHeartbeatAbortSentinel()
        {
            if (Plugin.BroadcastTestHeartbeatAbortSentinel == null || !BroadcastMode.IsBroadcastIdentity) return;
            string raw = (Plugin.BroadcastTestHeartbeatAbortSentinel.Value ?? "").Trim();
            if (_lastTestHeartbeatAbortSentinel == null) { _lastTestHeartbeatAbortSentinel = raw; return; }
            if (raw == _lastTestHeartbeatAbortSentinel) return;
            _lastTestHeartbeatAbortSentinel = raw;
            if (raw.Length == 0) return;
            ApiClient.DevHeartbeatAbortSentinelTest();
        }

        // v1.41.0 beta round 3 finding 10: [Broadcast] TestPresetSlotSentinel,
        // the same grammar and identity gate as the levers above.
        private static string _lastTestPresetSlotSentinel;
        private void TickTestPresetSlotSentinel()
        {
            if (Plugin.BroadcastTestPresetSlotSentinel == null || !BroadcastMode.IsBroadcastIdentity) return;
            string raw = (Plugin.BroadcastTestPresetSlotSentinel.Value ?? "").Trim();
            if (_lastTestPresetSlotSentinel == null) { _lastTestPresetSlotSentinel = raw; return; }
            if (raw == _lastTestPresetSlotSentinel) return;
            _lastTestPresetSlotSentinel = raw;
            if (raw.Length == 0) return;
            PortraitRender.DevPresetSlotSentinelTest();
        }

        // v1.41.0 beta round 4 finding 1: [Broadcast] TestTeamGameNumberSentinel,
        // the same grammar and identity gate as the levers above.
        private static string _lastTestTeamGameNumberSentinel;
        private void TickTestTeamGameNumberSentinel()
        {
            if (Plugin.BroadcastTestTeamGameNumberSentinel == null || !BroadcastMode.IsBroadcastIdentity) return;
            string raw = (Plugin.BroadcastTestTeamGameNumberSentinel.Value ?? "").Trim();
            if (_lastTestTeamGameNumberSentinel == null) { _lastTestTeamGameNumberSentinel = raw; return; }
            if (raw == _lastTestTeamGameNumberSentinel) return;
            _lastTestTeamGameNumberSentinel = raw;
            if (raw.Length == 0) return;
            DevTeamGameNumberSentinelTest();
        }

        /// <summary>The 2v2 game-number self-test (round 3 finding 1, client
        /// half, round 4). Runs TeamGameNumber.RunSentinel: synthetic series
        /// against a model of the server's filing rule, under the Tracker the
        /// seat runs and three kept rules this round did not build, plus direct
        /// checks of the tracker, the bounds and both canonicals. Round 5
        /// (finding F25) adds the physical game's token: the reviewer's
        /// scenario and its neighbours on two Trackers (a host and a peer)
        /// against the server's token rule and the rule before it, direct
        /// checks of taking, dropping and publishing a token, and the token's
        /// canonicals and pin. Nothing is sent, no room property is written, and
        /// TeamGameNumber.Live is never touched. Logs
        /// [TEAM-GAME-NUMBER-SENTINEL] PASS/FAIL.</summary>
        internal static void DevTeamGameNumberSentinelTest()
        {
            try
            {
                bool pass;
                string line = TeamGameNumber.RunSentinel(out pass);
                if (pass) Plugin.Log.LogInfo(line); else Plugin.Log.LogWarning(line);
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"{TeamGameNumber.SentinelTag} FAIL: threw {ex.Message}");
            }
        }

        /// <summary>The 2v2 DC reporter election's self-test (round 2 finding 2,
        /// round 3 finding 2). Runs every survivor of synthetic four-seat rooms
        /// through DcReporterElection.ShouldReport, the rule OnPlayerLeftRoom runs,
        /// and checks that the failing states from both reviews (no survivor can
        /// read the teams; a readable but wrong `t_id`; in each, the lowest id in
        /// the room is the leaver's own teammate) leave a reporter the server
        /// accepts, as does every state of a four-seat room in its sweep, and that
        /// rooms whose teams are readable and true elect exactly two seats, exactly
        /// one of which the server accepts (merge pass 1, follow-up 6).
        /// Nothing is sent. Logs [REPORTER-ELECTION-SENTINEL] PASS/FAIL.</summary>
        internal static void DevReporterElectionSentinelTest()
        {
            try
            {
                bool pass;
                string line = DcReporterElection.RunSentinel(out pass);
                if (pass) Plugin.Log.LogInfo(line); else Plugin.Log.LogWarning(line);
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"{DcReporterElection.SentinelTag} FAIL: threw {ex.Message}");
            }
        }

        // Sept 10: synthetic Player Card tiles (PlayerCardsUI.DevSeedTiles), same
        // once-per-distinct-value grammar and identity gate as the sentinel lever.
        private static string _lastTestPlayerCards;
        private void TickTestPlayerCards()
        {
            if (Plugin.BroadcastTestPlayerCards == null || !BroadcastMode.IsBroadcastIdentity) return;
            string raw = (Plugin.BroadcastTestPlayerCards.Value ?? "").Trim();
            if (_lastTestPlayerCards == null) { _lastTestPlayerCards = raw; return; }
            if (raw == _lastTestPlayerCards) return;
            _lastTestPlayerCards = raw;
            if (raw.Length == 0) return;
            if (raw.StartsWith("portrait:", StringComparison.OrdinalIgnoreCase)) { PortraitRender.DevRun(raw.Substring(9)); return; }   // portrait renderer (v22 section 5.7)
            if (raw.StartsWith("shot:", StringComparison.OrdinalIgnoreCase)) { PortraitRender.DevShot(raw.Substring(5)); return; }        // window capture from this seat (#622)
            if (raw.StartsWith("motion:", StringComparison.OrdinalIgnoreCase)) { PlayerCardMotion.DevRun(raw.Substring(7)); return; }     // dance cards playback levers (design S8)
            if (raw.StartsWith("ui:", StringComparison.OrdinalIgnoreCase))
            {
                // open the mod page on a tab so the seat can screenshot its own UI
                string what = raw.Substring(3).Trim().ToLowerInvariant();
                if (what == "close") { try { NativeUI.Close(); } catch { } return; }
                NativeUI.DevOpenTab(what == "settings" ? 5 : NativeUI.TAB_COLLECTION);
                return;
            }
            if (raw.StartsWith("act:", StringComparison.OrdinalIgnoreCase))
            {
                // press a real button (daily claim / first waiting pack / a binder tile's card / a view) — live api, this seat's identity
                try { PlayerCardsUI.DevAct(raw.Substring(4).Trim().ToLowerInvariant()); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[PC] FAIL: act lever threw {ex.Message}"); }
                return;
            }
            try { PlayerCardsUI.DevSeedTiles(raw.ToLowerInvariant()); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[PC] FAIL: tiles lever threw {ex.Message}"); }
        }

        // Broadcast-seat UI verification lever: "tab[:shopScroll]". Applied once
        // per distinct value (re-applied after a change), identity-gated.
        private static string _lastTestOpenTab;
        private static float _testOpenTabAt = -1f;
        private static float _testOpenTabCfgReloadAt = -1f;
        // TestQuit lever state (Sept 6, TickTestQuit): the directive's value at
        // its first read is the BASELINE — a value already present at launch
        // never fires; only a later, different, non-empty value quits, and at
        // most once per process (_testQuitFired). Live state, not a leftover.
        private static string _testQuitBaseline;
        private static bool _testQuitFired;
        // The "16:click:prepare:<nonce>" directive (lag-332 W6-A, with its
        // per-process nonce and startup baseline) was removed with the click
        // decode it drove (Sept 7 design v2 §7 Item 2): a streamed engine has
        // no preparation click, and the engine exercise is [Music] TestScript.

        /// <summary>Sept 6: the seat's own way to close the game. The elevated
        /// ROUNDS on the broadcast VM stopped honouring WM_CLOSE from a
        /// non-elevated shell (it had, #450), synthetic mouse input never
        /// reached the menu (#420) and Enter submits the EventSystem's
        /// selection rather than the highlighted ListMenu item — so a
        /// verify cycle could not relaunch the game without Sid. Same lever
        /// grammar as TestOpenTab: the value at launch is the baseline and
        /// never fires; any different non-empty value quits once. Runs only
        /// on the broadcast identity (the caller has already checked) and
        /// after the same 2 s cfg reload.</summary>
        private void TickTestQuit()
        {
            try
            {
                if (Plugin.BroadcastTestQuit == null || _testQuitFired) return;
                string want = (Plugin.BroadcastTestQuit.Value ?? "").Trim();
                if (_testQuitBaseline == null) { _testQuitBaseline = want; return; }
                if (want.Length == 0 || string.Equals(want, _testQuitBaseline, StringComparison.Ordinal)) return;
                _testQuitFired = true;
                Plugin.Log.LogWarning($"[UI] TestQuit lever fired ({want}) — quitting the game");
                QuitThenKill();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[UI] TestQuit lever failed: {ex.Message}"); }
        }

        // TestPress lever state (board row 27 witnesses): the value at its
        // first read is the baseline and never fires; each later different
        // non-empty value presses once.
        private static string _testPressLast;

        /// <summary>Board row 27 and 33a witnesses: press a named button on the
        /// open F5 overlay through the ClickHandler a real click runs (#420:
        /// synthetic mouse input never reaches the overlay on this VM). The
        /// TestQuit grammar, except that every new value fires once rather than
        /// once per process. Broadcast identity only (the caller has already
        /// checked), after the same 2 s cfg reload.</summary>
        private void TickTestPress()
        {
            try
            {
                if (Plugin.BroadcastTestPress == null) return;
                string want = (Plugin.BroadcastTestPress.Value ?? "").Trim();
                if (_testPressLast == null) { _testPressLast = want; return; }
                if (string.Equals(want, _testPressLast, StringComparison.Ordinal)) return;
                _testPressLast = want;
                if (want.Length == 0) return;
                int colon = want.IndexOf(':');
                string name = colon >= 0 ? want.Substring(0, colon).Trim() : want;
                Plugin.Log.LogInfo($"[UI] TestPress -> {name}: {NativeUI.DevPressButton(name)}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[UI] TestPress lever failed: {ex.Message}"); }
        }

        private static void QuitThenKill()
        {
            // r5 review M5: the hard-kill watchdog must not live on Unity's
            // main thread -- Application.quitting can block (this mod copies
            // the log there) and a coroutine would then never resume. A
            // background thread ends the process 8 s after the quit request
            // whatever the main thread is doing; if the quit succeeds first the
            // process is gone and the thread with it.
            try
            {
                var watchdog = new System.Threading.Thread(() =>
                {
                    System.Threading.Thread.Sleep(8000);
                    try { System.Diagnostics.Process.GetCurrentProcess().Kill(); } catch { }
                }) { IsBackground = true, Name = "scr-testquit-watchdog" };
                watchdog.Start();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[UI] TestQuit watchdog thread failed: {ex.Message}"); }
            try { Application.Quit(); } catch (Exception ex) { Plugin.Log.LogWarning($"[UI] TestQuit Application.Quit threw: {ex.Message}"); }
        }

        private void TickTestOpenTab()
        {
            if (Plugin.BroadcastTestOpenTab == null || !BroadcastMode.IsBroadcastIdentity) return;
            // Re-read the cfg file every 2s so the lever can be driven without
            // a relaunch (Config.Bind values never track disk edits, #190).
            if (Time.realtimeSinceStartup - _testOpenTabCfgReloadAt > 2f)
            {
                _testOpenTabCfgReloadAt = Time.realtimeSinceStartup;
                try { Plugin.ConfigFileForLevers?.Reload(); } catch { }
            }
            TickTestQuit();
            TickTestPress();
            ApiClient.TickTestQueueReport();
            ApiClient.TickTestStaleToken();
            string raw = (Plugin.BroadcastTestOpenTab.Value ?? "").Trim();
            if (raw == _lastTestOpenTab) return;
            if (Time.realtimeSinceStartup < 6f) return;   // let the menu and the overlay's page build settle
            if (_testOpenTabAt < 0f) { _testOpenTabAt = Time.realtimeSinceStartup; return; }
            if (Time.realtimeSinceStartup - _testOpenTabAt < 1.5f) return;   // two ticks apart: Toggle then scroll
            _lastTestOpenTab = raw;
            _testOpenTabAt = -1f;
            if (raw.Length == 0) return;
            string[] parts = raw.Split(':');
            int idx; float scroll = -1f; string infoKey = null;
            if (!int.TryParse(parts[0].Trim(), out idx)) return;
            // Aug 23: for the Info tab (15) EVERYTHING after the first ':' is
            // the article directive (e.g. "15:rewards", "15:search:poison",
            // "15:linktest") — NativeUI.DevOpenTab owns that grammar, and a
            // bare Split(':') would eat the query half of "search:<q>".
            // Screenshots of specific articles need this lever since
            // synthetic clicks can't reach the overlay (#420). Other tabs
            // keep the float scroll meaning.
            string compareMetric = null; int shopCat = -1; string ladderDirective = null;
            if (parts.Length > 1)
            {
                if (idx == 15) infoKey = raw.Substring(raw.IndexOf(':') + 1).Trim();
                // Aug 31: "9:<metric name>" opens Compare on a named metric
                // (metric names contain spaces/digits — everything after the
                // first ':' is the name, byte-matched by DevSetCompareMetricByName;
                // Sept 1: card metrics match too and flip the sub-tab).
                else if (idx == 9) compareMetric = raw.Substring(raw.IndexOf(':') + 1).Trim();
                // Sept 1: "4:cat<N>" selects a Shop category tab (e.g. 4:cat10
                // = Dances); a bare float keeps the scroll meaning.
                else if (idx == 4 && parts[1].Trim().StartsWith("cat", StringComparison.OrdinalIgnoreCase))
                {
                    int.TryParse(parts[1].Trim().Substring(3), out shopCat);
                    // Sept 23 (item 12 follow-up): anything after "4:catN:" drives the
                    // Titles section's ladder entries and their tier dropdown, e.g.
                    // "4:cat4:fixture:cat" (TitleLaddersUI.DevDirective owns the grammar).
                    if (parts.Length > 2) ladderDirective = string.Join(":", parts, 2, parts.Length - 2);
                }
                // Item 13: "5:<sub-tab>[:<key>]" opens a Settings sub-tab (and
                // selects a row on it), "5:<sub-tab>:expand" also opens that
                // tab's list, and "5:selftest" runs the settings self-test;
                // NativeUI.DevSettingsDirective owns that grammar. A bare float
                // keeps the scroll meaning.
                else if (idx == 5 && !float.TryParse(parts[1].Trim(), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out scroll))
                {
                    scroll = -1f;
                    infoKey = raw.Substring(raw.IndexOf(':') + 1).Trim();
                }
                else float.TryParse(parts[1].Trim(), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out scroll);
            }
            // A "16:click:..." value (the retired preparation-click directive)
            // now opens tab 16 like any other "16" value: "click" is not a
            // scroll float, so the scroll stays -1.
            Plugin.Log.LogInfo($"[UI] TestOpenTab -> tab {idx} scroll {scroll} article {infoKey ?? "-"} metric {compareMetric ?? "-"} shopCat {shopCat}");
            NativeUI.ReleaseShowcaseOwnership();   // r1 LOW 9: the lever takes the page over from the showcase
            NativeUI.DevOpenTab(idx, scroll, infoKey);
            if (!string.IsNullOrEmpty(compareMetric)) NativeUI.DevSetCompareMetricByName(compareMetric);
            if (shopCat >= 0) NativeUI.DevSetShopCategory(shopCat);
            if (!string.IsNullOrEmpty(ladderDirective)) TitleLaddersUI.DevDirective(ladderDirective);
        }

        // ── [Broadcast] TestQuickChatWheel: wheel layout screenshots ──
        private static string _lastTestWheel = "";
        private void TickTestQuickChatWheel()
        {
            if (Plugin.BroadcastTestQuickChatWheel == null || !BroadcastMode.IsBroadcastIdentity) return;
            string v = (Plugin.BroadcastTestQuickChatWheel.Value ?? "").Trim().ToLowerInvariant();
            if (v == _lastTestWheel) return;
            _lastTestWheel = v;
            if (v == "main") CompetitiveUI.DevForceQuickChatWheel(0);
            else if (v == "more") CompetitiveUI.DevForceQuickChatWheel(1);
            // Sept 1: "send:<id>" fires a real QuickChat.Send — the vanilla
            // chat RPC path end to end (in the offline sandbox the RPC loops
            // back locally and the bubble renders above the local body, so
            // the transport swap is verifiable on one seat, #420).
            else if (v.StartsWith("send:"))
            {
                int qid;
                if (int.TryParse(v.Substring(5), out qid))
                    Plugin.Log.LogInfo($"[QUICKCHAT] test send id {qid} -> {QuickChat.Send(qid)} refusal='{QuickChat.LastRefusal}'");
            }
            else CompetitiveUI.DevReleaseQuickChatWheel();
        }

        // [Broadcast] TestRoomRules (v1.41.0 item 22): latch a rules pair on the
        // broadcast seat, OFFLINE only, so the standing room-rules strip paints
        // with nobody at the seat. One application per distinct value; the value
        // present at startup is applied too (unlike the sentinels, it runs no
        // test, it only sets a state). Empty releases a latch this lever made
        // and never one a room made (RoomRules.DevReleaseTest checks the source).
        private static string _lastTestRoomRules;
        private void TickTestRoomRules()
        {
            if (Plugin.BroadcastTestRoomRules == null || !BroadcastMode.IsBroadcastIdentity) return;
            string raw = (Plugin.BroadcastTestRoomRules.Value ?? "").Trim();
            if (raw == _lastTestRoomRules) return;
            _lastTestRoomRules = raw;
            if (raw.Length == 0)
            {
                bool released = RoomRules.DevReleaseTest();
                Plugin.Log.LogInfo("[ROOM-RULES] test lever: cleared (released=" + released + ")");
                return;
            }
            bool ok = RoomRules.DevLatchForTest(raw);
            Plugin.Log.LogInfo("[ROOM-RULES] test lever: '" + raw + "' "
                + (ok ? "latched ff=" + (RoomRules.FriendlyFire ? 1 : 0) + " sc=" + (RoomRules.SameCards ? 1 : 0)
                      : "refused (inside a room, or not the ff=X;sc=Y grammar)"));
        }

        // ── [Broadcast] TestDance: headless dance verification (Aug 31 item 5) ──
        // "wheel" pins the E wheel open over ALL defined dances (layout
        // screenshot; sends still refuse unowned). "preview:<sku>" toggles
        // the shop puppet. "play:<idx>" installs the dance on the local
        // sandbox body via the same active-map the real receive path fills —
        // OFFLINE ONLY, so nothing can leak into a real room.
        private static string _lastTestDance = "";
        private void TickTestDance()
        {
            if (Plugin.BroadcastTestDance == null || !BroadcastMode.IsBroadcastIdentity) return;
            string v = (Plugin.BroadcastTestDance.Value ?? "").Trim();   // cfg reload rides TickTestOpenTab's 2s Reload
            if (v == _lastTestDance) return;
            _lastTestDance = v;
            if (v.Length == 0)
            {
                CompetitiveUI.DevReleaseDanceWheel();
                DanceEmotes.StopPreview();
                return;
            }
            // Any non-"wheel" value releases the paint pin too (round-3 LOW:
            // wheel -> preview:/play: left the pin armed past DwClose, so a
            // later disconnect could bypass the room-loss close).
            CompetitiveUI.DevReleaseDanceWheel();
            if (v == "wheel") { CompetitiveUI.DevForceDanceWheel(); return; }
            if (v.StartsWith("preview:", StringComparison.Ordinal))
            { DanceEmotes.TogglePreview(v.Substring(8).Trim()); return; }
            // Dance cards build step 0 (design S11.1): the live body-channel
            // probe, Floss on the local sandbox body. OFFLINE ONLY (the probe
            // refuses otherwise). "bodyprobe" or "bodyprobe:<tag>".
            if (v == "bodyprobe" || v.StartsWith("bodyprobe:", StringComparison.Ordinal))
            {
                var ptag = new System.Text.StringBuilder();
                foreach (char ch in (v.Length > 10 ? v.Substring(10) : ""))
                    if (ptag.Length < 24 && ((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch == '-' || ch == '_')) ptag.Append(ch);
                StartCoroutine(DanceStep0Probe.BodyProbe(ptag.Length == 0 ? "live" : ptag.ToString()));
                return;
            }
            if (v.StartsWith("play:", StringComparison.Ordinal))
            {
                int idx;
                if (int.TryParse(v.Substring(5).Trim(), out idx))
                {
                    bool ok = DanceEmotes.DevInstallLocal(idx);
                    Plugin.Log.LogInfo($"[DANCE] TestDance play:{idx} -> {(ok ? "installed" : "refused")}");
                    if (ok) StartCoroutine(ProbeDancePose());
                }
            }
        }

        // Board row 31: [Broadcast] TestShowcase - one idle-showcase rotation
        // with only the stream-live gate lifted, for the in-game witness (each
        // Compare metric shown logs a [SHOWCASE] metric line). The sentinel
        // levers' grammar and identity gate: the value present at startup is
        // the baseline and never runs; each distinct NEW value runs once.
        private static string _lastTestShowcase;
        private void TickTestShowcase()
        {
            if (Plugin.BroadcastTestShowcase == null || !BroadcastMode.IsBroadcastIdentity) return;
            string raw = (Plugin.BroadcastTestShowcase.Value ?? "").Trim();   // cfg reload rides TickTestOpenTab's 2s Reload
            if (_lastTestShowcase == null) { _lastTestShowcase = raw; return; }
            if (raw == _lastTestShowcase) return;
            _lastTestShowcase = raw;
            if (raw.Length == 0) return;
            IdleShowcase.DevRunOneRotation();
        }

        // Board row 30g: [Broadcast] TestWatchedSet - a recorded set replayed
        // through the post-set report (PostSessionReport.DevWatchSet) for the
        // in-game witness, a watched set not being available on demand. The
        // sentinel levers' grammar and identity gate.
        private static string _lastTestWatchedSet;
        private void TickTestWatchedSet()
        {
            if (Plugin.BroadcastTestWatchedSet == null || !BroadcastMode.IsBroadcastIdentity) return;
            string raw = (Plugin.BroadcastTestWatchedSet.Value ?? "").Trim();   // cfg reload rides TickTestOpenTab's 2s Reload
            if (_lastTestWatchedSet == null) { _lastTestWatchedSet = raw; return; }
            if (raw == _lastTestWatchedSet) return;
            _lastTestWatchedSet = raw;
            if (raw.Length == 0) return;
            // Round 2 M4: the lever replays a recorded set as if the seat had
            // watched it, so it runs only against a local test api; while the
            // configured API is production (or any other non-local host) it
            // refuses and says so.
            string apiHost;
            if (!SessionReportRules.DevLeverApiAllowed(ApiClient.BaseUrl, out apiHost))
            {
                try { Plugin.Log?.LogWarning("[REPORT] test watched set refused: the configured API (" + apiHost + ") is production or another non-local server; this lever runs only against a local test api (localhost / 127.0.0.1)"); } catch { }
                return;
            }
            PostSessionReport.DevWatchSet(raw);
        }

        // Board row 30f: [Broadcast] TestSessionReport - the F5 session report
        // opened on a set and turned to a page for the in-game witness: the
        // history row's Session button is a click the witness cannot give the
        // overlay (#420), and a named page ties each screenshot to its page.
        // The levers' identity gate and new-value grammar; a value that arrives
        // while the F5 page is closed waits for it instead of being spent.
        private static string _lastTestSessionReport;
        private void TickTestSessionReport()
        {
            if (Plugin.BroadcastTestSessionReport == null || !BroadcastMode.IsBroadcastIdentity) return;
            string raw = (Plugin.BroadcastTestSessionReport.Value ?? "").Trim();   // cfg reload rides TickTestOpenTab's 2s Reload
            if (_lastTestSessionReport == null) { _lastTestSessionReport = raw; return; }
            if (raw == _lastTestSessionReport) return;
            if (raw.Length > 0 && !NativeUI.IsOpen) return;   // wait for the F5 page
            _lastTestSessionReport = raw;
            if (raw.Length == 0) return;
            NativeUI.ReleaseShowcaseOwnership();   // as TestOpenTab: the lever takes the page over from the showcase
            SessionReportView.DevDirective(raw);
        }

        // ── [Broadcast] TestSilence: headless silence-indicator verification ──
        // Sets data.silenceTime on a sandbox bot and lets vanilla
        // SilenceHandler.Update discover it — the same code path a real
        // Silence-card explosion drives (RPCA_AddSilence also just raises
        // silenceTime), so the X the screenshot shows is the X players get.
        // OFFLINE-ONLY: this must never touch an online room's players.
        private static bool _testSilenceArmed;
        private void TickTestSilence()
        {
            if (Plugin.BroadcastTestSilence == null || !BroadcastMode.IsBroadcastIdentity) return;
            bool want = Plugin.BroadcastTestSilence.Value;   // cfg reload rides TickTestOpenTab's 2s Reload
            if (!want) { _testSilenceArmed = false; return; }
            if (_testSilenceArmed) return;
            if (!PhotonNetwork.OfflineMode) return;
            try
            {
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null || pm.players.Count == 0) return;
                Player target = null;
                for (int i = 0; i < pm.players.Count; i++)
                {
                    var p = pm.players[i];
                    if (p == null || p.data == null) continue;
                    // Review r1 find 12: never latch against a dead/inactive
                    // candidate — SilenceHandler.Update only runs on an
                    // active player, so silencing a corpse renders nothing
                    // and burns the one-shot. Verification prefers the FIRST
                    // live player (the stationary local one): sandbox bots
                    // wander off the kill boundary and die mid-window, and a
                    // death's RPCA_Die correctly StopSilences (trace-proven),
                    // eating the visual before a screenshot can land.
                    try { if (!p.gameObject.activeInHierarchy || p.data.dead) continue; } catch { continue; }
                    target = p; break;
                }
                if (target == null) return;
                _testSilenceArmed = true;
                MaybeRigDump();   // dance-design probe rides the same sandbox session
                target.data.silenceTime = 3f;
                Plugin.Log.LogInfo($"[SILENCE-X] TestSilence: applied 3s silence to player id {target.PlayerID}");
                StartCoroutine(ProbeSilenceScale(target));
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[SILENCE-X] TestSilence failed: {ex.Message}"); }
        }

        // Dance verification probe: samples the WOBBLE transform (the visual
        // body the dance offsets — the physics root never moves) + one arm
        // target for 2s, so the choreography is provable from the log even
        // when orange-on-orange screenshots are ambiguous.
        private System.Collections.IEnumerator ProbeDancePose()
        {
            Player me = null;
            try
            {
                var pm = PlayerManager.instance;
                if (pm != null && pm.players != null)
                    foreach (var p in pm.players)
                        if (p != null && p.data != null && p.data.view != null && p.data.view.IsMine) { me = p; break; }
            }
            catch { }
            if (me == null) { Plugin.Log.LogInfo("[DANCE] probe: no local player"); yield break; }
            Transform wob = null, arm = null;
            try
            {
                var w = me.GetComponentInChildren<PlayerWobblePosition>(true);
                if (w != null) wob = w.transform;
                var a = me.GetComponentInChildren<IKArmMove>(true);
                if (a != null) arm = a.target;
            }
            catch { }
            for (int i = 0; i < 10; i++)
            {
                try
                {
                    bool bo = false; try { bo = GameManager.instance != null && GameManager.instance.battleOngoing; } catch { }
                    Plugin.Log.LogInfo($"[DANCE] probe t={i * 0.2f:F1} wobble={(wob != null ? wob.position.ToString("F2") : "-")} armTarget={(arm != null ? arm.position.ToString("F2") : "-")} win={DanceEmotes.WindowOpen()} battle={bo} active={DanceEmotes.ActiveCount} dead={DanceEmotes.WobbleChannelDead}/{DanceEmotes.ArmChannelDead}");
                }
                catch { }
                yield return new WaitForSecondsRealtime(0.2f);
            }
        }

        // ── [Broadcast] TestRigDump: one-shot player-rig hierarchy dump ──
        // The dance design review's blocking unknown: which transforms host
        // IKArmMove/IkLeg/PlayerWobblePosition, their targets and ancestry.
        private static bool _rigDumped;
        internal static void MaybeRigDump()
        {
            if (_rigDumped) return;
            try
            {
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null || pm.players.Count == 0) return;
                var p = pm.players[0];
                if (p == null) return;
                _rigDumped = true;
                var sb = new System.Text.StringBuilder("[RIG-DUMP] player 0 tree:\n");
                void Walk(Transform t, int depth)
                {
                    if (t == null || depth > 6) return;
                    var comps = t.GetComponents<Component>();
                    var names = new System.Text.StringBuilder();
                    foreach (var c in comps) { if (c != null) names.Append(c.GetType().Name).Append(','); }
                    sb.Append(new string(' ', depth * 2)).Append(t.name)
                      .Append(" [").Append(names).Append("] lp=").Append(t.localPosition.ToString("F2")).Append('\n');
                    for (int i = 0; i < t.childCount; i++) Walk(t.GetChild(i), depth + 1);
                }
                Walk(p.transform, 0);
                foreach (var arm in p.GetComponentsInChildren<IKArmMove>(true))
                    sb.Append($"IKArmMove on {arm.transform.name}: target={(arm.target != null ? arm.target.name + "@" + arm.target.localPosition.ToString("F2") : "null")}\n");
                foreach (var leg in p.GetComponentsInChildren<IkLeg>(true))
                    sb.Append($"IkLeg on {leg.transform.name}: footTarget={(leg.footTarget != null ? leg.footTarget.name + "@" + leg.footTarget.localPosition.ToString("F2") : "null")}\n");
                var wob = p.GetComponentInChildren<PlayerWobblePosition>(true);
                sb.Append($"PlayerWobblePosition: {(wob != null ? wob.transform.name + " children=" + wob.transform.childCount : "none")}\n");
                Plugin.Log.LogInfo(sb.ToString());
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[RIG-DUMP] failed: " + ex.Message); }
        }

        // TestSilence companion probe: the indicator's scale over the silence
        // window, so a log alone can say whether the X actually grew.
        private System.Collections.IEnumerator ProbeSilenceScale(Player target)
        {
            for (int i = 0; i < 6; i++)
            {
                yield return new WaitForSecondsRealtime(0.5f);
                try
                {
                    var h = target != null ? target.GetComponent<SilenceHandler>() : null;
                    var ca = h != null ? h.codeAnim : null;
                    if (ca == null) { Plugin.Log.LogInfo("[SILENCE-X] probe: codeAnim gone"); yield break; }
                    Plugin.Log.LogInfo($"[SILENCE-X] probe t+{(i + 1) * 0.5f:F1}s scale={ca.transform.localScale} playing={ca.isPlaying} state={ca.currentState} silenced={(target.data != null && target.data.isSilenced)}");
                }
                catch { }
            }
        }

        private static void FpsWrite(int target)
        {
            // vSync overrides targetFrameRate, so every cap write zeroes it.
            if (QualitySettings.vSyncCount != 0) QualitySettings.vSyncCount = 0;
            if (Application.targetFrameRate != target) Application.targetFrameRate = target;
            fpsWrittenTarget = target;
        }

        private void TickUnfocusedFpsCap()
        {
            try
            {
                bool unfocused = !Application.isFocused;
                if (!unfocused) unfocusedSinceRt = -1f;
                else if (unfocusedSinceRt < 0f) unfocusedSinceRt = Time.realtimeSinceStartup;

                int curTarget = Application.targetFrameRate;   // -1/0 = uncapped
                int curVsync = QualitySettings.vSyncCount;
                // The player's/vanilla's chosen values: live while nobody owns
                // them, the saved pair while we do. Every stage decides from
                // THIS, never from a value another stage wrote (M3).
                int baseTarget = fpsOwning ? fpsBaseTarget : curTarget;
                int baseVsync = fpsOwning ? fpsBaseVsync : curVsync;
                bool external = fpsOwning && (curTarget != fpsWrittenTarget || curVsync != 0);

                // ── Broadcast-seat render cap (Aug 23, Sid: "GPU temps are kind
                // of high"): while the DIRECTOR is active this seat exists to
                // feed a 60 FPS encode; the 300-390 FPS it rendered otherwise
                // is pure GPU heat. Manual VM use (director disabled) is
                // untouched. ──
                int seatCap = (!Plugin.modDisabled && Plugin.BroadcastFpsCap != null) ? Plugin.BroadcastFpsCap.Value : 0;
                // broadcastSeat = the director is active on THIS seat (nobody
                // plays here then); seatActive = that AND a render cap is
                // configured. The re-assert / no-stand-down exemptions key on
                // the SEAT, not the cap value (review r4 find 1: with
                // BroadcastFpsCap=0 the independent 16-min idle throttle was
                // stranded behind the player-wins latch after a scene reload
                // restored vSync).
                bool broadcastSeat = false;
                try { broadcastSeat = BroadcastMode.DirectorActive; } catch { }
                bool seatActive = seatCap > 0 && broadcastSeat;

                int desired = 0;
                string why = null;
                // ── Deep idle: unfocused players 60s out of play, or the
                // broadcast seat's focus-independent 16-minute idle (Aug 18).
                // Overrides vSync by design: 15 is below any refresh rate. ──
                bool broadcastIdle = WantBroadcastIdle();
                bool wantDeep = (unfocused && WantDeepIdle()) || broadcastIdle;
                if (wantDeep)
                {
                    desired = 15;
                    why = broadcastIdle ? "deep idle (broadcast seat 16min+ idle)"
                                        : "deep idle (60s+ unfocused, out of room)";
                }
                else
                {
                    // ── Unfocused cap (Aug 6). Only when it would REDUCE the
                    // rate: an existing cap at or below 120 stays untouched.
                    // Codex round 1 (LOW): vSync is the OTHER cap, and killing
                    // it can RAISE the effective rate (targetFrameRate=-1,
                    // vSyncCount=1, 60 Hz display = 60 fps; zeroing vSync and
                    // setting 120 would DOUBLE it). Leave vSync-capped clients
                    // alone: their refresh rate is already the cap. ──
                    bool wantCap = Plugin.CapFpsUnfocused != null && Plugin.CapFpsUnfocused.Value
                                   && !Plugin.modDisabled && unfocused
                                   && !(baseTarget > 0 && baseTarget <= 120)
                                   && baseVsync == 0;
                    if (wantCap) { desired = 120; why = "unfocused cap"; }
                }
                if (seatActive)
                {
                    // r2 M4: with vSync on, the effective rate follows the
                    // DISPLAY (240 Hz renders 240) whatever targetFrameRate
                    // says — so a vSync-on baseline needs ownership when the
                    // display's refresh EXCEEDS the cap. r3 find 2: and ONLY
                    // then — on a 60 Hz display vSync already holds 60, and
                    // writing vSync=0 + 144 would RAISE the rate, the inverse
                    // of the feature. The written target never exceeds the
                    // display rate or a lower existing cap.
                    int displayHz = DisplayRefreshHz();
                    bool vsyncHolds = baseVsync > 0 && displayHz > 0 && displayHz <= seatCap;
                    bool capNeeded = !vsyncHolds
                                     && (baseTarget <= 0 || baseTarget > seatCap || baseVsync > 0);
                    if (capNeeded)
                    {
                        int capTarget = (baseTarget > 0 && baseTarget < seatCap) ? baseTarget : seatCap;
                        if (baseVsync > 0 && displayHz > 0 && displayHz < capTarget) capTarget = displayHz;
                        if (desired == 0 || capTarget < desired)
                        {
                            desired = capTarget;
                            why = $"broadcast seat render cap ({seatCap} fps)";
                        }
                    }
                }

                if (desired == 0)
                {
                    if (fpsOwning)
                    {
                        // Value-checked restore, targetFrameRate before vSync —
                        // only undo what is still OURS (player changes win).
                        if (curTarget == fpsWrittenTarget) Application.targetFrameRate = fpsBaseTarget;
                        if (curVsync == 0) QualitySettings.vSyncCount = fpsBaseVsync;
                        fpsOwning = false;
                        Plugin.Log.LogInfo($"[FPSCAP] released (restored target={fpsBaseTarget} vsync={fpsBaseVsync}, focused={Application.isFocused})");
                    }
                    fpsExternalOverride = false;
                    fpsDesiredLast = 0;
                    return;
                }

                if (!fpsOwning)
                {
                    // A player override stands until the wanted cap CHANGES
                    // (a different stage engaging) — never overridden on the
                    // broadcast seat, where nobody plays with the director on.
                    if (fpsExternalOverride && !broadcastSeat && desired == fpsDesiredLast) return;
                    fpsBaseTarget = curTarget;
                    fpsBaseVsync = curVsync;
                    fpsOwning = true;
                    fpsExternalOverride = false;
                    FpsWrite(desired);
                    fpsDesiredLast = desired;
                    Plugin.Log.LogInfo($"[FPSCAP] engaged {why}: target={desired} (baseline target={fpsBaseTarget} vsync={fpsBaseVsync})");
                    return;
                }

                if (external)
                {
                    if (broadcastSeat)
                    {
                        // Re-assert (review r1 find 8): a vanilla vSync change
                        // while the director is active would otherwise defeat
                        // the cap silently. Throttled log.
                        FpsWrite(desired);
                        if (Time.realtimeSinceStartup - fpsReassertLogRt > 30f)
                        {
                            fpsReassertLogRt = Time.realtimeSinceStartup;
                            Plugin.Log.LogInfo($"[FPSCAP] re-asserted {why} over an external change (target={curTarget} vsync={curVsync})");
                        }
                    }
                    else
                    {
                        // The player changed video settings while we owned the
                        // values: theirs win. r3 find 1: a PARTIAL change
                        // (vanilla's vSync callback touches only vSync) must
                        // not strand the half we wrote — restore whatever is
                        // still OURS to the baseline, keep whatever they
                        // changed, then stand down until the wanted cap
                        // changes.
                        if (curTarget == fpsWrittenTarget) Application.targetFrameRate = fpsBaseTarget;
                        if (curVsync == 0) QualitySettings.vSyncCount = fpsBaseVsync;
                        fpsOwning = false;
                        fpsExternalOverride = true;
                        fpsDesiredLast = desired;
                        Plugin.Log.LogInfo($"[FPSCAP] released (external video-settings change adopted: target={Application.targetFrameRate} vsync={QualitySettings.vSyncCount})");
                    }
                    return;
                }

                if (desired != fpsWrittenTarget)
                {
                    // Stage change while owning (e.g. deep idle lifting back to
                    // the broadcast cap, or the cap engaging under the
                    // unfocused cap): the baseline is untouched, only the
                    // written target moves.
                    FpsWrite(desired);
                    Plugin.Log.LogInfo($"[FPSCAP] {why}: target={desired}");
                }
                fpsDesiredLast = desired;
            }
            catch { }
        }

        private void Update()
        {
            // Aug 6 item 8 / Aug 7 item 2: the fps tick runs BEFORE the
            // modDisabled return — the compat check flips modDisabled ~3s after
            // launch, and the old order left an applied cap stuck for the whole
            // session if the launch happened unfocused (cosmetic at 120, a
            // ruined session at 15). Apply paths gate on !modDisabled inside;
            // a disabled mod can only ever RESTORE.
            TickUnfocusedFpsCap();
            TickBroadcastWindowPin();
            // Letterbox clear camera: per-frame scene check, depth re-adapted
            // every 2 s. Above the modDisabled return like the fps tick: the
            // camera is created with the host whatever the mod's state, and a
            // stale depth would draw the clear OVER the game, so its upkeep must
            // run whenever the camera exists.
            LetterboxClear.Upkeep(gameObject);

            // Bug 389: the proximity-victim capability withdrawal runs here for
            // the same reason the fps tick does - ABOVE the modDisabled return.
            // A guard keyed on a feature's enable-condition and then placed
            // inside a tick that returns on that same condition inherits the
            // feature's dead zone, and this withdrawal exists for exactly the
            // state the return covers: a seat that staged the key and has since
            // been disabled. Below the return it could never run on the only seat
            // that needs it (#272/#98).
            //
            // Safe above it on the same rule the comment above states: a disabled
            // mod may only ever RESTORE. This call returns on its first line
            // unless this seat actually advertised, and it can only ever write
            // the NOT-capable value - it moves the room toward vanilla and can
            // apply nothing (#276/#430).
            try { ProximityVictimGate.RepublishCapability(); } catch { }

            // [PEER-BUILD] evidence, also ABOVE the modDisabled return: stage
            // this seat's cr_build statement once, pre-join, and print one line
            // per remote seat per room join (again when its values change). No
            // setting, lever or room-kind check is in front of it, because
            // evidence a player can dispute ships in every client build. It
            // reads the room and writes only this seat's own statement.
            try { PeerBuild.StageBuildProp("tick"); PeerBuild.Tick(); } catch { }

            // Seat evidence: a pending compat outcome is signed and persisted
            // once the Steam id is known. Above the return because a finding
            // is exactly the state that disables the mod; it only writes this
            // seat's own queue file.
            try { SeatEvidence.CompatTick(); } catch { }
            // Evidence work the hooks deferred out of the game's methods: the
            // point-end lines and push counts first (before GameStateWatcher's
            // tick captures a record), then seat evidence's own clocks, the
            // record builds and the queue, then the card draw builds, then the
            // combat record builds. Above
            // the return: previously queued evidence sends whatever the mod's
            // state, under consent, a session, retry timing and no live
            // combat. No setting in front of any of it.
            try { PointEvidence.Drain(); } catch { }
            try { SeatEvidence.Tick(); } catch { }
            try { CardDrawEvidence.Tick(); } catch { }
            try { CombatEvidence.Tick(); } catch { }
            try { IdentityClockEvidence.Tick(); } catch { }

            if (Plugin.modDisabled) return;

            // Stage 2 (2v2 and 1v2 readmission): the seat log's point-start
            // probe and the hold upkeep.
            try { TeamHoldGlue.Tick(); } catch { }

            // Menu injection runs independently
            try { MainMenuInjector.TryInject(); } catch { }

            // Base-game locale injector (uk/sv) state machine. Static and
            // lifecycle-durable (localization-design §6.3, r2 find 8):
            // stepping from THIS persistent tick — not a coroutine on a
            // destroyable host — means a scene-transition respawn resumes
            // activation wherever it was. One enum compare when no activation
            // is in flight (en/es/ru sessions).
            //
            // r3 find 4: Awake requests activation, but the injector stays
            // INERT until DoInitialize clears the other-mod compat check ~3s
            // in — because modDisabled returns above this line, a Step() that
            // had already acquired handles or committed a provider could never
            // be stepped again, and its options-init postfix would keep
            // re-asserting a locale for a mod that reports itself disabled.
            // The compat-fail branch in DoInitialize calls Shutdown() instead.
            try { GameLocaleInjector.Step(); } catch { }

            // Delayed initialization (wait for game to be fully loaded)
            if (!startupComplete)
            {
                startupTimer += Time.deltaTime;
                if (startupTimer >= 3f)
                {
                    startupComplete = true;
                    DoInitialize();
                }
                return;
            }

            if (!initialized) return;

            // Canvas UI tick (notifications, match status, session refresh)
            try { CompetitiveUI.Tick(); } catch { }

            // Re-arm the report retry driver if it stopped. Self-throttled, and
            // a no-op with an empty queue. On a tick rather than only on an
            // enqueue because a session that has stopped enqueueing is the one
            // whose queue would otherwise stay put.
            try { ApiClient.OutboxTick(); } catch { }

            // Board row 27: the secure-route re-check while the session runs on
            // the plaintext backup. Self-throttled (once a second) and a no-op
            // unless the boot check fell back to the backup.
            try { ApiClient.SecureRouteTick(); } catch { }

            // Item 17: the keybind capture's expiry and page check, and the
            // in-game self-test's frame step, once a frame.
            try { Keybinds.FrameTick(); } catch { }

            // F5 input (no log spam — just toggle). Item 17 (question 1): the
            // menu row is rebindable and F5 stays a permanent rescue read, so no
            // binding can lock a player out of this menu. One toggle per frame
            // whichever fired; a keybind capture owns the keyboard while armed.
            bool menuF5 = false, menuRow = false;
            try { menuF5 = Input.GetKeyDown(KeyCode.F5) && !Keybinds.CaptureOwnsInput; } catch { }
            try { menuRow = Keybinds.Down(KeybindRules.MenuToggle); } catch { }
            if (menuF5 || menuRow)
            {
                CompetitiveUI.ToggleOverlay();
            }

            // Item 19: the avatar-default rings on the character menu's portrait
            // grid. Here, not in NativeUI.Tick, because this tick runs with the
            // mod's overlay closed (the F5 read above can only open it from here).
            try { AvatarDefaults.Tick(); } catch { }
            // Item 19 fix pass 3 (H3): retries an owed card-pick popup face
            // whose carrier is held, and stops owing it past the bound.
            try { PopupCarriers.Tick(); } catch { }

            // Per-frame FPS sampling (active only while a match is being tracked).
            try { GameStateWatcher.TickFrame(); } catch { }

            // Aug 7 item 3: card-bar tint (self-throttled to 0.5s internally).
            try { CardBarTeamColor.Tick(); } catch { }

            // Poll game state
            try
            {
                GameStateWatcher.Poll();
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"Poll error: {ex.Message}");
            }
            // Release B §1: the in-room head-to-head line. Reads the opponent
            // id Poll's TryResolveOpponent just resolved; self-gated to one
            // request per room incarnation.
            try { H2HSummary.Tick(); } catch { }
            // Dance cards S2F5 (round two): the capture path's one discarded
            // warm-up per process, from boot. Driven from THIS persistent tick,
            // not NativeUI.Tick (which returns at once unless a page is open),
            // so it can run before the first real capture wherever the player goes.
            try { PortraitRender.DanceWarmTick(); } catch { }

            /* [FONT] HeavyTextSelfTest (bug #351). Driven from THIS persistent
             * tick and not from NativeUI.Tick, which early-returns unless the
             * settings page is already open — the whole point is to reach the
             * toggle path without a click. Self-gating: one run per process,
             * and it returns immediately unless the cfg lever is on. */
            try { UIFactory.EnsureWeightSelfTest(); } catch { }
            // [SC-SELFTEST] (room rules §6): the vanilla-mode Same Cards seams
            // against the live game, once per process, only with its cfg lever.
            try { VanillaCardSequence.EnsureSelfTest(); } catch { }
            // [CARD-EV] census dump (B4): this seat's pool census, once per
            // process, only with its cfg lever, never in a room.
            try { CardDrawEvidence.EnsureCensusDump(); } catch { }

            // SCR Broadcast director + §2c identity fence (design §3a). Runs
            // from THIS persistent tick — never a coroutine host that
            // NetworkRestart can destroy (#16/#270c). Self-gating: one
            // latched-identity check and out on every non-broadcast install.
            try { BroadcastMode.Step(); } catch { }
            // Map-skin test lever tour / auto-Sandbox (broadcast identity only).
            try { ArtHandlerNextArtPatch.TickTestLever(); } catch { }
            try { TickTestOpenTab(); } catch { }
            // Overlay left open with nobody at the seat (broadcast identity only;
            // the player-seat branch was cut in review — see the class comment).
            try { OverlayIdleClose.Tick(); } catch { }
            try { MusicStreamProbe.Tick(); } catch { }
            try { RegionPingSweep.Tick(); } catch { }   // Sept 7 item 3: 250 ms self-throttled main-thread poll
            try { RegionCatalog.Tick(); } catch { }     // D2: services a live NameServer fetch every call
            // D13: a host-less music engine has no Update of its own; this
            // persistent poll respawns the host once the dying one is observed
            // destroyed — stateless, uncapped, every frame.
            try { MusicEngine.PollHost(); } catch { }
            try { MusicEngine.TickTestScript(); } catch { }
            try { SpectatorTeardownProbe.Tick(); } catch { }
            try { EmojiSprites.Tick(); } catch { }   // bug 333 step 2: 1 Hz self-throttled; decode only at a safe menu state
            try { TickTestGstatsSentinel(); } catch { }
            try { TickTestReporterElectionSentinel(); } catch { }
            try { TickTestAutoLogConsentSentinel(); } catch { }
            try { TickTestChatRevokeSentinel(); } catch { }
            try { TickTestHeartbeatAbortSentinel(); } catch { }
            try { TickTestPresetSlotSentinel(); } catch { }
            try { TickTestTeamGameNumberSentinel(); } catch { }
            try { TickTestPlayerCards(); } catch { }
            try { TickTestSilence(); } catch { }
            try { TickTestQuickChatWheel(); } catch { }
            try { TickTestDance(); } catch { }
            try { TickTestRoomRules(); } catch { }
            try { TickTestShowcase(); } catch { }
            try { TickTestWatchedSet(); } catch { }
            try { TickTestSessionReport(); } catch { }

            // Poll ranked queue if searching
            if (ApiClient.IsQueuePolling)
            {
                try
                {
                    ApiClient.UpdateQueuePoll(GameStateWatcher.LocalSteamId);
                }
                catch { }
            }

            // Poll 2v2 queue if searching
            if (ApiClient.IsTeamQueuePolling)
            {
                try { ApiClient.UpdateTeamQueuePoll(GameStateWatcher.LocalSteamId); }
                catch { }
            }

            // Stuck-Leaving watchdog (Codex verify finding 1): must live HERE,
            // in the persistent loop — the Leaving UI hides the very buttons
            // whose handlers used to be the only recovery path, and the leave
            // callback dies with its coroutine host on NetworkRestart.
            try { ApiClient.TickLeaveRecovery(); }
            catch { }

            // Poison protocol upkeep (#143/#151). Both are idempotent and cheap:
            // Hook() attaches the Photon event listener once per session, and
            // Tick() retries the pre-join capability stage and keeps the roster
            // view fresh. Driven from the always-on tick rather than a join hook
            // so no join path can forget it.
            try { PoisonSync.Hook(); PoisonSync.Tick(); }
            catch { }
            // Grow capability stage retry (one-shot; compat-gated, so the
            // first successful stage happens a few ticks after startup), plus
            // the ranked-intent re-sync (idle states only; the pre-join fence
            // patch covers the ordering the polling cannot).
            try { GrowNormalize.StageCapability("tick"); GrowNormalize.SyncRankedIntent("tick"); }
            catch { }
            // Weapon-cooldown reset capability stage retry (#379): the same
            // one-shot, compat-gated, idle-states-only staging the two above
            // use, on the same always-on tick for the same reason.
            try { WeaponCooldownReset.StageCapability("tick"); } catch { }
            // Same one-shot pre-join stage for the saw-targeting capability
            // (bug #380's gated half). Self-guarded, so this is free once staged.
            try { SawTargetSync.StageCapability("tick"); } catch { }
            // ...and for the 2v2 DC election generation (cr_dc2). A survivor that
            // does not advertise it drops its room to the floor election, so the
            // stage has to happen for every seat that can play 2v2, not only the
            // ones that reach a vanilla-fix path.
            try { DcReportSync.StageCapability("tick"); } catch { }
            // Automatic post-match log upload (item a): keeps the room
            // snapshot the room-exit callback needs, because OnLeftRoom runs
            // after PhotonNetwork has already let go of the room.
            try { AutoLogUpload.Tick(); } catch { }
            // The bug form's bundle is built on a worker; its finished body is
            // handed to the request here, on the always-on tick, so a report
            // whose page closed while it was building is still sent.
            try { CompetitiveUI.PumpBugFormBundle(); } catch { }
            // [CLOCK]: one time line a minute, so every mod line can be placed
            // within a minute and two seats aligned on the Photon server clock.
            try { LogClock.Tick(); } catch { }
            // Quick-chat sends through the vanilla chat RPC since Sept 1 and
            // needs no receive hook (event code 48 is retired, never shipped).
            // Dance emotes (Aug 31 item 5) ride event code 49; Tick runs the
            // combat-edge cancellation + expiry sweep every frame.
            try { DanceEmotes.Hook(); DanceEmotes.Tick(); } catch { }

            // Poll 1v2 queue if searching. Must run here (not just from the
            // F5 tab ticker) — a player who queues and closes the menu would
            // otherwise never receive ready_join, and their stale row would
            // strand the other two at 2/3 until the server prunes it.
            if (ApiClient.IsOvtQueuePolling)
            {
                try { ApiClient.UpdateOvtQueuePoll(false); }
                catch { }
            }

            // Poll FFA queue if searching — same always-on rationale as 1v2
            // (ready_join must land with the menu closed).
            if (ApiClient.IsFfaQueuePolling)
            {
                try { ApiClient.UpdateFfaQueuePoll(false); }
                catch { }
            }

            // Poll queue count when competitive page is open (every 10s)
            if (NativeUI.IsOpen)
            {
                try { ApiClient.UpdateQueueCount(); }
                catch { }
                try { ApiClient.UpdateTeamQueueCount(); }
                catch { }
                // Auto-refresh Live Ranked Games while the Leaderboard tab is open. Cheaply
                // gated by the 10s timer in NativeUI.MaybeRefreshLiveSeries so we're not
                // hammering /series/active every frame.
                try { NativeUI.MaybeRefreshLiveSeries(); }
                catch { }
            }
        }

        private void DoInitialize()
        {
            Plugin.Log.LogInfo("[PERSIST] Delayed initialization starting...");

            // Seat evidence: hash this DLL and the game's off the main thread.
            try { SeatEvidence.StartHashing(); } catch { }

            // ── Other mods check (Chainloader is complete by now) ──
            try
            {
                var plugins = Chainloader.PluginInfos;
                if (plugins != null && plugins.Count > 1)
                {
                    var otherMods = new List<string>();
                    foreach (var kvp in plugins)
                    {
                        if (kvp.Key != Plugin.ModId)
                            otherMods.Add($"{kvp.Value.Metadata.Name} ({kvp.Key})");
                    }
                    if (otherMods.Count > 0)
                    {
                        Plugin.Log.LogError($"[COMPAT] {otherMods.Count} other mod(s) detected! This mod requires vanilla ROUNDS with no other plugins.");
                        foreach (var m in otherMods)
                            Plugin.Log.LogError($"[COMPAT]   - {m}");
                        Plugin.Log.LogError("[COMPAT] Mod DISABLED to ensure competitive integrity.");
                        try
                        {
                            var guids = new List<string>();
                            foreach (var kvp in plugins) if (kvp.Key != Plugin.ModId) guids.Add(kvp.Key);
                            SeatEvidence.NoteCompat("finding", guids);
                            // Identity-clock evidence: this execution of the gate is one boot occurrence.
                            try { IdentityClockEvidence.BootCheck("finding", guids); } catch { }
                        }
                        catch { }
                        Plugin.modDisabled = true;
                        Plugin.compatCheckComplete = true;
                        // Awake already staged the poison-authority capability, and
                        // modDisabled stops the tick that would subscribe us to the
                        // commit path — withdraw it so peers do not wait on verdicts
                        // this client will never publish.
                        try { PoisonSync.RevokeCapability(); } catch { }
                        try { GrowNormalize.RevokeCapability(); } catch { }
                        // Bug 389: NOT the same shape as the two above.
                        // This call is a no-op on a first initialisation.
                        // cr_prox1 is
                        // staged PRE-JOIN from the queue poll, which cannot run
                        // before ApiClient.Initialize below - and this branch
                        // returns above that call - so nothing has been advertised
                        // yet and RepublishCapability returns on its first line.
                        // (PoisonSync stages at Awake and GrowNormalize from the
                        // tick, so their latches ARE set here; W18 holds this
                        // ordering.) It can only withdraw on a SECOND DoInitialize,
                        // after a persistent-host respawn whose compat read differs
                        // from the first, and it is kept for that case: a seat that
                        // advertises a repair its own gate now refuses leaves every
                        // peer re-resolving the victim while this seat drains the
                        // stale one - the same damage tick debiting different
                        // players on different screens. The transition that covers
                        // a seat already in a room is the persistent tick, not this
                        // site; "[PROX-CAP] withdrew" is not a line a plain compat
                        // disable produces.
                        try { ProximityVictimGate.RepublishCapability(); } catch { }
                        try { WeaponCooldownReset.RevokeCapability(); } catch { }
                        try { SawTargetSync.RevokeCapability(); } catch { }
                        // Same for the DC-election capability: a disabled mod runs no
                        // election at all, and a peer counting us as a census seat
                        // would hold a room-wide claim that is false on this seat.
                        try { DcReportSync.RevokeCapability(); } catch { }
                        // r3 find 4: same shape for the base-game locale
                        // injector. It has been inert (activation is gated on
                        // the compat clear below), but Shutdown is idempotent
                        // and is the only thing that can restore a vanilla
                        // locale + drop the provider/subscriber/handles if a
                        // future ordering change ever lets it commit first.
                        try { GameLocaleInjector.Shutdown("other mods detected"); } catch { }
                        return;
                    }
                }
                Plugin.Log.LogInfo("[COMPAT] No other mods detected — OK");
                try { SeatEvidence.NoteCompat("pass", null); } catch { }
                try { IdentityClockEvidence.BootCheck("pass", null); } catch { }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[COMPAT] Could not check other mods: {ex.Message}");
                // A check that threw reports not_run, never pass.
                try { SeatEvidence.NoteCompat("not_run", null); } catch { }
                try { IdentityClockEvidence.BootCheck("not_run", null); } catch { }
            }
            Plugin.compatCheckComplete = true;
            // r3 find 4: releases the injector's activation gate. Everything
            // it does before this is a no-op, so a uk/sv session that is
            // about to be disabled never acquires a handle or installs
            // anything. Reached on the check's exception path too — a compat
            // check we could not run is treated as passing, exactly like
            // every other feature below.
            try { GameLocaleInjector.OnCompatCleared(); } catch { }

            ApiClient.Initialize(Plugin.ApiBaseUrl.Value);
            GameStateWatcher.Initialize();
            CardImageLoader.Initialize();
            try { CustomCosmetics.Initialize(); } catch (Exception ex) { Plugin.Log.LogWarning($"[COSMETIC] init failed: {ex.Message}"); }
            // Music: assets FIRST (tier-tree resolution + stale-revision/orphan
            // sweep must finish before the engine creates any AudioSource —
            // MusicAssets contract), then the engine's static init/host spawn.
            try { MusicAssets.Initialize(); } catch (Exception ex) { Plugin.Log.LogWarning($"[MUSIC] assets init failed: {ex.Message}"); }
            try { MusicEngine.Initialize(); } catch (Exception ex) { Plugin.Log.LogWarning($"[MUSIC] engine init failed: {ex.Message}"); }
            // Bug 333 step 2: colour-emoji atlas (levers, cache dir, starting state; no decode or download here).
            try { EmojiSprites.Initialize(); } catch (Exception ex) { Plugin.Log.LogWarning($"[EMOJI] init failed: {ex.Message}"); }
            CompetitiveUI.CacheRaycasters(); // No-op but kept for compat
            initialized = true;

            // Initialize UI type cache for native menu integration
            try { UIFactory.InitTypes(); UIFactory.InitFont(); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[UI] Type init deferred: {ex.Message}"); }

            // Fetch initial data so overlay has content before first F5.
            // Steamworks resolution is racy — on first launch, GetSteamID()
            // routinely returns 0 ("unknown") for the first second or so.
            // Without a retry path, ToggleRanked + FetchPlayerStats etc.
            // never fire and the player's server-side ranked_enabled stays
            // at its default false. Fix the new-install "casual instead of
            // ranked" bug by spawning a coroutine that polls until Steam
            // resolves, then runs the same one-shot init.
            Plugin.Instance.StartCoroutine(InitWhenSteamReady());

            // Wire the chat pipe so incoming messages reach the UI log.
            ChatClient.OnMessage = NativeUI.OnChatMessage;
            // §2.6: a mid-session locale switch re-declares the socket's
            // channel set and refetches scrollback for the new channel.
            I18n.LocaleChanged += ChatClient.ResubscribeAndRefresh;
            // §2.2: fetch the pack overlay for the (possibly new) locale.
            // ApplyPack deliberately does NOT re-fire LocaleChanged, so this
            // cannot recurse.
            I18n.LocaleChanged += ApiClient.FetchI18nPack;
            ApiClient.FetchI18nPack();

            // If the user already granted consent in a previous session, open the chat WS now.
            // Fresh installs stay offline until the consent modal gets a Yes.
            if (Plugin.DataConsentGranted)
                ChatClient.Connect();

            // One-shot: log every TMP_FontAsset currently loaded so we can see which fonts
            // are actually available for in-game use (OS-font path is broken, see comments
            // in NametagFontRenderer). Useful for choosing target fonts to map typeface SKUs
            // onto in a follow-up pass.
            try { NametagFontRenderer.LogAvailableTmpFonts(); } catch { }

            Plugin.Log.LogInfo("[PERSIST] All systems active! Press F5 for overlay.");
        }

        // Polls until LocalSteamId resolves (Steamworks isn't always ready by
        // the time DoInitialize runs on first launch), then fires the same
        // one-shot init the inline guard used to do — ToggleRanked,
        // FetchPlayerStats, FetchMatchHistory, FetchBlockedPlayers,
        // CheckAdminStatus. Without this, a brand-new install whose
        // Steamworks resolve loses the race never calls ToggleRanked, leaves
        // their server-side ranked_enabled at false, and is matched as
        // casual by every opponent until they restart the game.
        private static bool _initSteamRanFired = false;
        private System.Collections.IEnumerator InitWhenSteamReady()
        {
            float deadline = Time.unscaledTime + 30f;  // give up after 30s; logs warn
            int tries = 0;
            while (!_initSteamRanFired && Time.unscaledTime < deadline)
            {
                tries++;
                string sid = GameStateWatcher.LocalSteamId;
                if (!string.IsNullOrEmpty(sid) && sid != "unknown")
                {
                    _initSteamRanFired = true;
                    Plugin.Log.LogInfo($"[INIT] Steam resolved on try {tries} (sid={sid}); firing one-shot init");
                    try { ApiClient.ToggleRanked(sid, Plugin.RankedEnabled.Value); } catch (Exception ex) { Plugin.Log.LogWarning($"[INIT] ToggleRanked failed: {ex.Message}"); }
                    try { ApiClient.FetchPlayerStats(sid); } catch { }
                    try { ApiClient.FetchMatchHistory(sid); } catch { }
                    try { ApiClient.FetchBlockedPlayers(sid); } catch { }
                    try { ApiClient.CheckAdminStatus(sid); } catch { }
                    // Warm the shop cache so the character editor knows owned
                    // cosmetics even if the F5 page was never opened this session.
                    try { ApiClient.FetchShopItems(sid); } catch { }
                    // Broadcast identity resolution site (music contract): the
                    // broadcast predicate is undecidable until the steam id
                    // resolves — kick the engine once here so the broadcast
                    // seat's bootstrap (full-tier fetch + custom autoplay)
                    // fires without waiting for a tab open. A no-op mode
                    // recompute on every other seat.
                    try { MusicEngine.Reconcile("broadcast-identity"); } catch { }
                    yield break;
                }
                yield return new WaitForSeconds(0.5f);
            }
            if (!_initSteamRanFired)
                Plugin.Log.LogWarning($"[INIT] Steam ID never resolved after {tries} tries / 30s. Server-side ranked_enabled may be stale until next launch.");
        }

        private void OnGUI()
        {
            if (!initialized || Plugin.modDisabled) return;
            CompetitiveUI.DrawUI();
            // RJ Stage 2 (S2): the non-modal hold banner; draws nothing
            // unless this client holds or just ended a hold.
            try { TeamHoldBanner.Draw(); } catch { }
            // RJ Stage 2 (S3): the rejoin offer and its outcome line.
            try { TeamHoldReturn.DrawOffer(); } catch { }
        }

        /// <summary>
        /// Hides the main menu UI after auto-joining a ranked room.
        /// Our Photon connect bypasses ROUNDS' normal scene transition,
        /// so the main menu stays rendered over the game.
        /// </summary>
        internal static void HideMainMenu()
        {
            try
            {
                // Log loaded scenes for debugging
                for (int i = 0; i < UnityEngine.SceneManagement.SceneManager.sceneCount; i++)
                {
                    var scene = UnityEngine.SceneManagement.SceneManager.GetSceneAt(i);
                    Plugin.Log.LogInfo($"[QUEUE] Loaded scene: {scene.name} (index {scene.buildIndex})");
                }

                // Hide the main menu the way VANILLA hides it on its own room
                // joins (NCH.cs:140/415/465): Close() deactivates only the
                // visual child. The old SetActive(false) on the HANDLER's
                // GameObject also killed ListMenu — they share the
                // 'UI_MainMenu' host — so every esc-menu open in a queue room
                // failed its SelectButton coroutines ("Coroutine couldn't be
                // started because 'UI_MainMenu' is inactive") and the menu
                // rendered with NO selection bar or bolding (the Button's own
                // ColorTint hover feedback still worked — so the dead focus
                // machinery is a PLAUSIBLE contributor to the Aug 12 stray
                // click on the disconnect-wired MAIN MENU button, not a
                // proven cause; EscMenuLeaveGuard is the actual protection).
                // The follow-up "disable all ListMenu objects" loop below it
                // was dead code from day one: FindObjectsOfType cannot see
                // the already-inactive host (its log line never printed once
                // in any session log).
                var mainMenuHandler = UnityEngine.Object.FindObjectOfType<MainMenuHandler>();
                if (mainMenuHandler != null)
                {
                    mainMenuHandler.Close();
                    Plugin.Log.LogInfo("[QUEUE] Main menu hidden (vanilla Close)");
                }

                // Disable CharacterSelectionInstance if present
                var charSelect = UnityEngine.Object.FindObjectOfType<CharacterSelectionInstance>();
                if (charSelect != null)
                {
                    charSelect.transform.root.gameObject.SetActive(false);
                    Plugin.Log.LogInfo("[QUEUE] Disabled character selection");
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[QUEUE] HideMainMenu error: {ex.Message}");
            }
        }

        private void OnDestroy()
        {
            // First, and on its own: the portrait renderer releases a run this
            // host drove (its coroutines stop here without their finally).
            try { PortraitRender.OnHostDestroyed(this); } catch { }
            // The animated player-colour loop, when this host runs it, stops here too.
            try { PlayerColorCosmetic.OnHostDestroyed(this); } catch { }
            Plugin.Log.LogWarning("[PERSIST] Destroyed! Attempting respawn...");
            MainMenuInjector.Reset();

            try
            {
                var go = new GameObject("CompetitiveRounds_Respawn");
                go.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(go);
                var newInstance = go.AddComponent<CompetitiveRoundsBehaviour>();
                Plugin.Instance = newInstance;
                // Round-4 finding 3: the respawn must carry the SAME companion
                // set as the initial spawn, through the one shared helper.
                Plugin.AttachPersistentCompanions(go);
                // Animated player colours, if any, resume from the new host.
                try { PlayerColorCosmetic.OnHostRespawned(); } catch { }
                Plugin.Log.LogInfo("[PERSIST] Respawned with DontDestroyOnLoad!");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[PERSIST] Respawn failed: {ex.Message}");
            }
        }

    }

    // ── Harmony Patches ────────────────────────────────────────

    // NOTE: LobbyRedirectPatch was added in v1.18.3 for Thunderstore compliance.
    // It redirects vanilla quickmatch to a mod-only Photon lobby ("QuickmatchCompLobby")
    // so mod users never match with vanilla players.
    // Currently DISABLED for direct distribution — Landfall permission pending.
    // To re-enable: uncomment this patch. No other changes needed.
    // See HANDOFF.md "Landfall / Thunderstore Situation" for full context.
    //
    // [HarmonyPatch(typeof(NetworkConnectionHandler), "Awake")]
    // class LobbyRedirectPatch
    // {
    //     private static readonly Photon.Realtime.TypedLobby LOBBY_QUICKMATCH_COMP =
    //         new Photon.Realtime.TypedLobby("QuickmatchCompLobby", Photon.Realtime.LobbyType.SqlLobby);
    //
    //     static void Postfix()
    //     {
    //         NetworkConnectionHandler.LOBBY_QUICKMATCH = LOBBY_QUICKMATCH_COMP;
    //         Plugin.Log.LogInfo("[HARMONY] Quickmatch lobby redirected to CompLobby (mod-only matchmaking)");
    //     }
    // }

    [HarmonyPatch(typeof(GM_ArmsRace), "Awake")]
    class GMArmsRaceAwakePatch
    {
        static void Postfix(GM_ArmsRace __instance)
        {
            Plugin.Log.LogInfo("[HARMONY] GM_ArmsRace.Awake fired! Harmony is WORKING!");
            CardRarityLookup.ScanAll();
            if (CardRarityLookup.Count == 0)
                Plugin.Log.LogInfo("[HARMONY] No cards found yet — will retry on match start");
        }
    }

    /// <summary>
    /// Force GM_ArmsRace.playersNeededToStart = 4 in 2v2 rooms. Vanilla OnEnable
    /// hardcodes it to 2 — the rest of the engine handles 4 players fine (there's
    /// even a debug keybind on '4' that toggles this exact field), but our normal
    /// game-start would fire as soon as 2 players joined, leaving the 3rd + 4th
    /// dangling without GameObjects → RPCO_RequestSyncUp targets a viewID that
    /// doesn't exist locally → MapManager.UnloadAfterSeconds throws on the bad
    /// scene state → Photon network restart → all 4 drop. Setting it to 4 makes
    /// the engine wait for all 4 before StartGame fires, which is what 4-player
    /// mode in vanilla local play does.
    ///
    /// Detection: the Photon room's `cr_ff` custom property (set by QueueJoiner
    /// when the room name starts with `team_`) doubles as a 2v2-mode signal.
    /// </summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "OnEnable")]
    class GMArmsRaceOnEnable_4Player_Patch
    {
        static void Postfix(GM_ArmsRace __instance)
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return;
                var props = PhotonNetwork.CurrentRoom.CustomProperties;
                string rn = PhotonNetwork.CurrentRoom.Name ?? "";
                // 1v2 (ovt_) rooms need 3; 2v2 (cr_ff) rooms need 4. Same engine
                // path — the CharacterSelectionMenu slot-overflow guard below
                // already tolerates the extra players generically.
                bool isOvt = rn.StartsWith("ovt_");
                // Trust-gated (review find 10): forcing playersNeededToStart to
                // the FFA lobby size in an untrusted room named "ffa_..." would
                // wedge a custom lobby that can never reach that count.
                bool isFfa = rn.StartsWith("ffa_") && FfaMode.EngineActive();
                bool isFf = props != null && props.ContainsKey("cr_ff");
                if (!isOvt && !isFf && !isFfa) return;
                int need = isFfa ? Diag2v2.PlayersNeeded() : (isOvt ? 3 : 4);
                __instance.playersNeededToStart = need;
                if (PlayerAssigner.instance != null)
                    PlayerAssigner.instance.maxPlayers = need;
                Plugin.Log.LogInfo($"[MODE] Forced playersNeededToStart={need} ({(isFfa ? "ffa_ FFA" : isOvt ? "ovt_ 1v2" : "cr_ff 2v2")} room)");
            }
            catch (Exception ex) { Plugin.Log.LogError($"[2v2] OnEnable patch error: {ex.Message}"); }
        }
    }

    /// <summary>
    /// Don't crash on the 3rd / 4th player joining a 2v2 room. Vanilla
    /// CharacterSelectionMenu.PlayerJoined does:
    ///   transform.GetChild(0).GetChild(players.Count - 1).GetComponent&lt;…&gt;().StartPicking(p)
    /// The container at GetChild(0) only has 2 children (one per 1v1 slot), so
    /// when players.Count hits 3, GetChild(2) throws "Transform child out of
    /// bounds". The exception aborts PlayerJoined's multicast invocation,
    /// meaning GM_ArmsRace.PlayerJoined never fires for players 3 and 4 →
    /// playersNeededToStart=4 never gets reached → StartGame never fires.
    /// Players 3 and 4 don't get the face-customization step (they spawn
    /// with their last-saved face) but the game continues normally.
    /// </summary>
    [HarmonyPatch(typeof(CharacterSelectionMenu), "PlayerJoined")]
    class CharacterSelectionMenu_PlayerJoined_2v2_Patch
    {
        static bool Prefix(CharacterSelectionMenu __instance)
        {
            try
            {
                if (__instance == null || __instance.transform.childCount == 0) return true;
                int slot = (PlayerManager.instance != null && PlayerManager.instance.players != null)
                    ? PlayerManager.instance.players.Count - 1 : -1;
                var container = __instance.transform.GetChild(0);
                if (slot < 0 || slot >= container.childCount)
                {
                    Plugin.Log.LogInfo($"[2v2] CharacterSelectionMenu skipped (slot={slot} >= children={container.childCount})");
                    return false;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] CharacterSelectionMenu prefix error: {ex.Message}"); }
            return true;
        }
    }

    // NetworkConnectionHandler_OnPlayerLeftRoom_2v2_Patch removed in v1.25.9.
    // Originally added in v1.25.5 to suppress vanilla's cascade-DC during the
    // 2v2 spawn race (where 2 of 4 bailed mid-spawn and dragged the others).
    // Spawn race is fixed by v1.25.4–v1.25.8 (PlayerAssigner slot collision,
    // late-joiner GM_ArmsRace activation, character-select OOB, auto-spawn).
    // Now when a player leaves mid-game we want vanilla's DoDisconnect →
    // NetworkRestart → GoToMenu cascade to fire so the remaining 3 don't sit
    // forever — matches user-reported expectation that a quit ends the match
    // for everyone.

    /// <summary>
    /// Skip-and-replace PlayerAssigner.CreatePlayer in 2v2 rooms. Vanilla logic
    /// hardcodes m_playerId = 0 for master / 1 for everyone else, so all 3 non-
    /// master clients collide on slot 1 in PlayerManager.players (RegisterPlayer
    /// does `players[forceIndex] = player`, overwriting). This patch uses the
    /// server-issued slot 0-3 (Plugin.Pending2v2Slot, set when /queue/poll
    /// returns ready_join) so each of the 4 players lands at a unique slot and
    /// the team mapping (slot/2 = team 0 or 1) matches the balancer's output.
    ///
    /// Critical ordering: we set VAR_PLAYERID + VAR_TEAMID custom properties on
    /// LocalPlayer BEFORE PhotonNetwork.Instantiate, so the message order on
    /// remote clients is "props update → instantiate" — when their Player.Start
    /// runs ReadPlayerID/ReadTeamID, the right values are already on Owner.
    /// </summary>
    [HarmonyPatch(typeof(PlayerAssigner), "CreatePlayer")]
    class PlayerAssigner_CreatePlayer_2v2_Patch
    {
        // Throttle for the spawn-guard warning (LateUpdate can call CreatePlayer
        // every frame while an input device is waiting, so the bad-state window
        // would otherwise spam the log).
        static float _lastSpawnGuardLog = -999f;
        // First moment of the CURRENT continuous suppression episode (-1 = not
        // suppressing). Drives the #37 watchdog below.
        static float _suppressEpisodeStart = -1f;

        static bool Prefix(PlayerAssigner __instance, InputDevice inputDevice, bool isAI)
        {
            // ── Spawn guard (v1.28): "no space to ready up" freeze ──────────────
            // Vanilla CreatePlayer does PhotonNetwork.Instantiate(...).GetComponent
            // <CharacterData>(). When the client is NOT in a room (e.g. mid region-
            // reconnect / quickplay churn — Photon state ConnectingToMasterServer),
            // Instantiate returns NULL and the GetComponent NREs, so the local
            // player never spawns → no ready ring → the player is stuck unable to
            // ready up (Sid's report, 2026-06-02 casual quickplay logs). Skip the
            // call entirely until we're actually in a room (or OfflineMode, where
            // Instantiate works fine). PlayerAssigner.LateUpdate keeps polling the
            // waiting input device, so vanilla CreatePlayer runs cleanly and spawns
            // the player as soon as the connection settles. Applies to ALL modes
            // (1v1 casual/ranked + 2v2) since the race is in vanilla networking.
            if (!PhotonNetwork.OfflineMode &&
                (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null))
            {
                try
                {
                    if (Time.unscaledTime - _lastSpawnGuardLog > 2f)
                    {
                        _lastSpawnGuardLog = Time.unscaledTime;
                        Plugin.Log.LogWarning(
                            "[SPAWN-GUARD] CreatePlayer suppressed — client not in a room " +
                            $"(state={PhotonNetwork.NetworkClientState}). Will retry when connected.");
                    }
                    // ── #37 watchdog: the guard can be CORRECT forever ──────────
                    // Bug #37's log: casual quickplay left the room, a region-ping
                    // sweep + Network restart followed, and a stale game scene kept
                    // polling CreatePlayer with no room for the rest of the session
                    // — guard suppressing each time, "Press jump to join" dead. The
                    // suppressed state can't self-heal without a room, so after 30s
                    // of CONTINUOUS suppression, pull the vanilla ripcord
                    // (NetworkRestart → clean return to menu) instead of letting
                    // the player sit on an unjoinable screen.
                    if (_suppressEpisodeStart < 0f) _suppressEpisodeStart = Time.unscaledTime;
                    else if (Time.unscaledTime - _suppressEpisodeStart > 30f)
                    {
                        _suppressEpisodeStart = -1f;  // one shot per episode
                        Plugin.Log.LogWarning("[SPAWN-GUARD] stuck >30s with no room — NetworkRestart back to menu");
                        try { CompetitiveUI.ShowNotification("Connection was lost — returning to menu.", new Color(1f, 0.8f, 0.3f), 6f); } catch { }
                        try { NetworkConnectionHandler.instance.NetworkRestart(); } catch { }
                    }
                }
                catch { }
                return false;  // skip vanilla; LateUpdate retries next frame
            }
            _suppressEpisodeStart = -1f;  // in a room (or offline) — episode over

            if (PhotonNetwork.OfflineMode) return true;
            if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return true;
            // Strict mode-matching: an ovt_ room only honors the ovt slot and a
            // cr_ff room only honors the 2v2 slot, so a stale pending slot from
            // the OTHER mode can never mis-map teams.
            var roomProps = PhotonNetwork.CurrentRoom.CustomProperties;
            bool isOvtRoom = (PhotonNetwork.CurrentRoom.Name ?? "").StartsWith("ovt_");
            bool isFfaRoom = (PhotonNetwork.CurrentRoom.Name ?? "").StartsWith("ffa_");
            bool isFfRoom = roomProps != null && roomProps.ContainsKey("cr_ff");
            int slot = isOvtRoom ? Plugin.PendingOvtSlot
                     : isFfaRoom ? Plugin.PendingFfaSlot
                     : isFfRoom ? Plugin.Pending2v2Slot
                     : -1;
            if (slot < 0) return true;                              // not a team-mode spawn
            if (__instance.hasCreatedLocalPlayer) return false;     // already done

            int teamID = Diag2v2.SlotToTeam(slot);   // 2v2: slot/2 · 1v2: solo=0, duo=1
            int playerID = slot;

            try
            {
                var fM_playerId = typeof(PlayerAssigner).GetField("m_playerId",
                    BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Public);
                fM_playerId?.SetValue(__instance, slot);
                __instance.hasCreatedLocalPlayer = true;

                // Pre-set Photon LocalPlayer custom props so remote clients reading
                // VAR_PLAYERID / VAR_TEAMID inside Player.Start (after they receive
                // our Instantiate message) see the right values. Photon serializes
                // operations: SetCustomProperties → Instantiate guarantees props
                // arrive first.
                var pre = new ExitGames.Client.Photon.Hashtable();
                pre[Player.VAR_PLAYERID] = playerID;
                pre[Player.VAR_TEAMID] = teamID;
                // Also publish u_id (our Steam ID). Vanilla CreatePlayer relies on
                // AssignUserID() to do this; our 2v2 override skips that to avoid
                // pulling in ROUNDS identity machinery. Without u_id, peers can't
                // resolve actor→Steam ID at match-end and TryReportTeamMatch
                // aborts → match falls through to the 1v1 casual report path.
                // (The /queue/poll ready_join handler also publishes u_id before
                // room join — this is belt-and-suspenders for the CreatePlayer
                // path.)
                try
                {
                    string mySid = MatchTracker.LocalSteamId;
                    if (!string.IsNullOrEmpty(mySid) && mySid != "unknown")
                        pre["u_id"] = mySid;
                }
                catch { }
                PhotonNetwork.LocalPlayer.SetCustomProperties(pre);

                Vector3 position = Vector3.up * 100f;
                var component = PhotonNetwork.Instantiate(
                    __instance.playerPrefab.name, position, Quaternion.identity, 0
                ).GetComponent<CharacterData>();

                // Online 4-player ranked is keyboard-only (no split-screen). Vanilla
                // CreatePlayer chooses keyboard/controller based on inputDevice; for
                // our ranked path everyone is keyboard.
                component.input.inputType = GeneralInput.InputType.Keyboard;
                component.playerActions = PlayerActions.CreateWithKeyboardBindings();
                component.playerActions.Device = inputDevice;
                __instance.players.Add(component);

                int forceIndex = playerID;
                PlayerManager.RegisterPlayer(component.player, forceIndex);
                component.player.AssignPlayerID(playerID);
                component.player.AssignTeamID(teamID);
                // Skip Platform/UserID/UnityID assignments — they're identity metadata
                // for cross-platform matchmaking + the in-game block-list. Not required
                // for a ranked 4-player match to function. Optional best-effort attempt
                // via reflection so we don't pull in extra ROUNDS namespaces here.
                try
                {
                    var t = typeof(Player);
                    foreach (var (name, val) in new (string, object)[] {
                        ("AssignPlatform", null),
                        ("AssignUserID", null),
                        ("AssignUnityID", null),
                    })
                    {
                        var m = t.GetMethod(name);
                        if (m != null && val != null) m.Invoke(component.player, new[] { val });
                    }
                }
                catch { }

                // Force PlayerSkinHandler to re-bake using the correct PlayerID.
                // PlayerSkinHandler.Init() reads `data.player.PlayerID` and instantiates
                // a skin GameObject keyed off it. If Init runs DURING PhotonNetwork.Instantiate
                // (before our AssignPlayerID call lands), m_playerID is the field-default 0
                // and every local 2v2 player ends up rendered with skin index 0 (orange).
                // That's why the user reported themselves as orange but their teammate as
                // blue — local was wrong, remote was right (Player.Start.ReadPlayerID sets
                // it correctly for non-mine players before PlayerSkinHandler.Start runs).
                try
                {
                    var psh = component.GetComponentInChildren<PlayerSkinHandler>(true);
                    if (psh != null)
                    {
                        // Destroy whatever skin GameObject was already baked
                        for (int i = psh.transform.childCount - 1; i >= 0; i--)
                        {
                            var ch = psh.transform.GetChild(i);
                            if (ch != null) UnityEngine.Object.Destroy(ch.gameObject);
                        }
                        psh.inited = false;
                        var initMethod = typeof(PlayerSkinHandler).GetMethod("Init",
                            BindingFlags.NonPublic | BindingFlags.Instance);
                        initMethod?.Invoke(psh, null);
                        Plugin.Log.LogInfo($"[2v2] Re-baked local PlayerSkin for slot={slot} (post-AssignPlayerID)");
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] PlayerSkin re-bake failed: {ex.Message}"); }

                // Bug #224: our face RPC just went out via vanilla's one
                // UNBUFFERED RpcTarget.All (Player.Start's IsMine branch,
                // fired during the Instantiate above) — any peer still
                // mid-join missed it forever (#226). Re-send once the room
                // settles. Schedule gates on team_/ovt_ itself: the FFA
                // spawn path lands here too, but FfaMode.ResyncLocalFace
                // owns ffa_ rooms (it re-sends at every game start).
                try { FaceResync.Schedule("local-spawn"); } catch { }

                Plugin.Log.LogInfo($"[{(isFfaRoom ? "FFA" : isOvtRoom ? "1v2" : "2v2")}] CreatePlayer override: slot={slot} team={teamID} pid={playerID}");
                return false;  // skip vanilla
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[2v2] CreatePlayer override failed: {ex.Message} — falling back to vanilla");
                return true;  // fall back to vanilla CreatePlayer (still wrong but at least game runs)
            }
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Bug #79 — the "Press Jump to Join does nothing" quickplay race. Vanilla's
    // 15s region-churn timer (NetworkConnectionHandler.Update) ticks whenever
    // `m_searchingType` is neither HostRoom nor FriendInvite, the client is
    // InRoom online, and GM_ArmsRace.instance is null. (An earlier version of
    // this note said "gated only on InRoom and no GM_ArmsRace", which hid the
    // search-type gate — and with it the fact that None, the value the mod's
    // joiner sets, is NOT exempt: bugs 335/340, ModRoomChurnFreezePatch below.)
    // GM_ArmsRace activates ~2.5s AFTER
    // an opponent joins (the MATCH FOUND jingle runs first). OnPlayerEnteredRoom
    // never resets the timer, so if the opponent arrives in the last ~2.5s of
    // the window, PlayOnBestActiveRegion() leaves the just-matched room mid-
    // animation → a 16-region ping sweep (~25s) → "PRESS JUMP TO JOIN" shown
    // with no room and no opponent. Always-on (vanilla race, all modes).
    // ─────────────────────────────────────────────────────────────────────────
    [HarmonyPatch(typeof(NetworkConnectionHandler), "OnPlayerEnteredRoom")]
    class QuickplayChurnFreezePatch
    {
        static void Postfix(Photon.Realtime.Player newPlayer)
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return;
                // A spectator entering is not a match-found signal — the
                // census below already keeps the freeze correct, but skipping
                // outright also silences the misleading "opponent joined" log
                // on every spectator entry (Aug 10 playtest noise).
                if (RoomActors.IsSpectator(newPlayer)) return;
                // Census: "match found" means a second FIGHTER — a lone
                // searcher plus a spectator must not freeze the churn timer
                // (the client would sit in an empty room believing a match
                // was found; recon's highest-risk Plugin pair).
                if (RoomActors.ActiveFighterCount() < 2) return;
                var nch = NetworkConnectionHandler.instance;
                if (nch == null) return;
                // Publicized private field — freeze the churn timer the moment a
                // match is found. Vanilla re-arms it to 15f in OnJoinedRoom on the
                // next search, so no un-freeze bookkeeping is needed.
                nch.untilTryOtherRegionCounter = float.MaxValue;
                Plugin.Log.LogInfo("[QUICKPLAY-GUARD] opponent joined — region-churn timer frozen");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[QUICKPLAY-GUARD] freeze failed: {ex.Message}"); }
        }
    }

    // ----------------------------------------------------------------------
    // Sept 6 — bugs 335/340 (A1): the first player into a queue-issued room was
    // evicted after 15 s. Vanilla's churn timer ticks whenever m_searchingType
    // is neither HostRoom nor FriendInvite, the client is InRoom online, and
    // GM_ArmsRace.instance is null; OnJoinedRoom re-arms it to 15f on every
    // online join. The joiner sets the search type to None, which is NOT
    // exempt, and the two bug-79 guards around this class only engage once a
    // second fighter is present — so a partner who needed more than ~15 s (a
    // slow connect, a room to leave first, or the A2 failure burning 30 s per
    // attempt) found an empty room, while the waiter had been swept into a
    // public quick-match search and, in bug 340, into a casual game against a
    // random unmodded player. Freeze the timer on join for every mod-issued
    // room; GameStateWatcher's [QUEUE-STALL] watchdog (toast, then a clean
    // return to menu with no penalty) is the only eviction there. Room-code
    // private games keep vanilla timing — out of scope by design. Positive
    // field signal (#438): the log line below on every mod-room join.
    // ----------------------------------------------------------------------
    [HarmonyPatch(typeof(NetworkConnectionHandler), "OnJoinedRoom")]
    class ModRoomChurnFreezePatch
    {
        static void Postfix(NetworkConnectionHandler __instance)
        {
            try
            {
                if (__instance == null || !PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null || PhotonNetwork.OfflineMode) return;
                string name = PhotonNetwork.CurrentRoom.Name ?? "";
                if (!CompetitiveRoomDetect.IsModIssuedRoom(name, PhotonNetwork.CurrentRoom.CustomProperties)) return;
                // Postfix: runs after vanilla's `untilTryOtherRegionCounter = 15f`.
                __instance.untilTryOtherRegionCounter = float.MaxValue;
                Plugin.Log.LogInfo($"[QUICKPLAY-GUARD] churn timer frozen - mod-issued room {name}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[QUICKPLAY-GUARD] mod-room freeze failed: {ex.Message}"); }
        }
    }

    [HarmonyPatch(typeof(NetworkConnectionHandler), "PlayOnBestActiveRegion")]
    class QuickplayChurnAbandonGuardPatch
    {
        // Second freeze point: covers the JOINER seat (which never receives
        // OnPlayerEnteredRoom — Photon routes the local join to OnJoinedRoom,
        // so its churn timer is never frozen by the Postfix above) and any
        // failure of that Postfix. Never abandon a room that already has a
        // full match in it; only skip at 2+ players — lone searchers
        // legitimately rotate regions. CRITICAL: re-arm the counter when
        // suppressing — vanilla's Update never resets it after firing, so a
        // bare suppression would re-trigger (and log) every frame while the
        // counter sits expired. Re-arming to 15s also preserves vanilla's
        // stalled-full-room escape at a delay instead of removing it.
        //
        // July 21 item 3: the running sweep coroutine is WRAPPED so the
        // requeue watchdog can (a) know a sweep is in flight (a sweep never
        // coexists with an active GM_ArmsRace except via the bug-79 race) and
        // (b) ABORT it before NetworkRestart — restarting mid-sweep is the
        // bug-#37 livelock (WaitForRestart's IsConnected wait is perpetually
        // re-satisfied by the sweep's next ConnectToRegion and m_restarting
        // is consumed forever).
        internal static volatile bool SweepActive = false;
        internal static volatile bool AbortSweep = false;

        static bool Prefix(ref System.Collections.IEnumerator __result)
        {
            try
            {
                // Sept 6 (bugs 335/340, A1 second line): a mod-issued room is never
                // rotated out of by vanilla's timer, whatever the fighter count —
                // the OnJoinedRoom postfix may not have been reached (#83), and a
                // lone waiter is exactly the seat these reports lost. Freeze
                // rather than re-arm: GameStateWatcher's [QUEUE-STALL] watchdog
                // owns the exit from a mod-issued room, with its own toast and
                // its own clock.
                if (PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null &&
                    CompetitiveRoomDetect.IsModIssuedRoom(PhotonNetwork.CurrentRoom.Name, PhotonNetwork.CurrentRoom.CustomProperties))
                {
                    Plugin.Log.LogWarning($"[QUICKPLAY-GUARD] PlayOnBestActiveRegion suppressed — mod-issued room {PhotonNetwork.CurrentRoom.Name}");
                    try { NetworkConnectionHandler.instance.untilTryOtherRegionCounter = float.MaxValue; } catch { }
                    __result = EmptyRoutine();
                    return false;
                }
                if (PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null &&
                    RoomActors.ActiveFighterCount() >= 2)   // census: see churn-freeze twin above
                {
                    Plugin.Log.LogWarning("[QUICKPLAY-GUARD] PlayOnBestActiveRegion suppressed — match already found in this room");
                    try { NetworkConnectionHandler.instance.untilTryOtherRegionCounter = 15f; } catch { }
                    __result = EmptyRoutine();
                    return false;
                }
            }
            catch { }
            return true;
        }

        static void Postfix(ref System.Collections.IEnumerator __result)
        {
            __result = Track(__result);
        }

        static System.Collections.IEnumerator Track(System.Collections.IEnumerator orig)
        {
            SweepActive = true; AbortSweep = false;
            try
            {
                while (!AbortSweep && orig.MoveNext())
                    yield return orig.Current;
            }
            finally
            {
                SweepActive = false;
                if (AbortSweep) Plugin.Log.LogWarning("[QUICKPLAY-GUARD] region sweep aborted by requeue watchdog");
            }
        }

        static System.Collections.IEnumerator EmptyRoutine() { yield break; }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // 2v2 diagnostics — heavy logging gated on Pending2v2Slot >= 0 OR cr_ff
    // room presence. Goal: when a 4-player attempt fails, the BepInEx log
    // names exactly who triggered the disconnect / room-leave / restart.
    // Remove when 2v2 is stable.
    // ─────────────────────────────────────────────────────────────────────────

    internal static class Diag2v2
    {
        // "Active" = any multi-player team-mode context: 2v2 (cr_ff room prop /
        // pending 2v2 slot) OR 1v2 (ovt_ room / pending ovt slot). Every patch
        // gated here is join/spawn/skin/crown machinery that a 3-player ovt
        // room needs exactly like a 4-player cr_ff room — vanilla is 2-player-
        // shaped in all of those places. Mode differences (player count, slot→
        // team mapping) go through PlayersNeeded()/SlotToTeam() below.
        public static bool IsActive()
        {
            if (Plugin.Pending2v2Slot >= 0 || Plugin.PendingOvtSlot >= 0 || Plugin.PendingFfaSlot >= 0) return true;
            try
            {
                if (PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null)
                {
                    var p = PhotonNetwork.CurrentRoom.CustomProperties;
                    if (p != null && p.ContainsKey("cr_ff")) return true;
                    string rn = PhotonNetwork.CurrentRoom.Name ?? "";
                    if (rn.StartsWith("ovt_")) return true;
                    // FFA needs TRUST, not just the prefix (review find 10).
                    if (rn.StartsWith("ffa_") && FfaMode.EngineActive()) return true;
                }
            }
            catch { }
            return false;
        }

        /// <summary>True in the 1v2 context. When in a room, the room's name is
        /// authoritative (a stale pending slot from the OTHER mode must never
        /// flip the mapping); outside a room, the pending ovt slot covers the
        /// pre-join window.</summary>
        public static bool IsOvt()
        {
            try
            {
                if (PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null)
                    return (PhotonNetwork.CurrentRoom.Name ?? "").StartsWith("ovt_");
            }
            catch { }
            return Plugin.PendingOvtSlot >= 0;
        }

        /// <summary>True in the FFA context. In a room this requires TRUST,
        /// not just the name (review find 10): a hand-made room called
        /// "ffa_test" must not activate the multi-player join/spawn/skin
        /// machinery or ban the normal report routes while the engine itself
        /// (FfaMode.EngineActive) correctly stays off. Trust = the same proof
        /// the engine uses: a live queue lobby id or the creator-stamped
        /// cr_ffa_n room prop. Outside a room the pending slot covers the
        /// bounded pre-join window.</summary>
        public static bool IsFfa()
        {
            try
            {
                if (PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null)
                    return FfaMode.EngineActive();
            }
            catch { }
            return Plugin.PendingFfaSlot >= 0;
        }

        /// <summary>Server-issued slot → ROUNDS TeamID. 2v2: slots 0,1 = team 0,
        /// slots 2,3 = team 1. 1v2: slot 0 = solo = team 0, slots 1,2 = duo =
        /// team 1 (vanilla two-team scoring carries straight through). FFA:
        /// every player is their own team (TeamID = slot).</summary>
        public static int SlotToTeam(int slot)
        {
            if (IsFfa()) return slot;
            return IsOvt() ? (slot == 0 ? 0 : 1) : slot / 2;
        }

        /// <summary>Players required for the mode's game to start: 3 in an ovt_
        /// room, 4 in a cr_ff room, the locked lobby size (3-10) in an ffa_
        /// room (from the cr_ffa_n room prop stamped by the creator, falling
        /// back to the queue payload count).</summary>
        public static int PlayersNeeded()
        {
            if (IsFfa())
            {
                try
                {
                    var p = PhotonNetwork.InRoom ? PhotonNetwork.CurrentRoom?.CustomProperties : null;
                    if (p != null && p.ContainsKey("cr_ffa_n"))
                    {
                        int n = Convert.ToInt32(p["cr_ffa_n"]);
                        if (n >= 2 && n <= 10) return n;
                    }
                }
                catch { }
                return Plugin.PendingFfaCount > 0 ? Plugin.PendingFfaCount : 10;
            }
            return IsOvt() ? 3 : 4;
        }

        /// <summary>The local pending slot regardless of mode (-1 when neither
        /// queue has issued one). 1v2/FFA win when multiple are somehow set —
        /// theirs is always the more recent lock (2v2 slots persist through
        /// series end only until cleared).</summary>
        public static int PendingSlot()
        {
            if (Plugin.PendingFfaSlot >= 0) return Plugin.PendingFfaSlot;
            if (Plugin.PendingOvtSlot >= 0) return Plugin.PendingOvtSlot;
            return Plugin.Pending2v2Slot;
        }

        public static string ShortStack()
        {
            try
            {
                var st = new System.Diagnostics.StackTrace(2, false);
                var sb = new System.Text.StringBuilder();
                int n = Math.Min(st.FrameCount, 8);
                for (int i = 0; i < n; i++)
                {
                    var m = st.GetFrame(i)?.GetMethod();
                    if (m == null) continue;
                    sb.Append(m.DeclaringType?.Name ?? "?").Append('.').Append(m.Name);
                    if (i < n - 1) sb.Append(" <- ");
                }
                return sb.ToString();
            }
            catch { return "<stack-unavailable>"; }
        }

        public static string DescribeRoom()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return "(not in room)";
                var r = PhotonNetwork.CurrentRoom;
                int pcount = r.PlayerCount;
                int max = r.MaxPlayers;
                // §7.1 (SCR Broadcast): on the broadcast seat the room name is
                // a credential and never reaches a log — every DescribeRoom
                // consumer (NCH-DIAG NetworkRestart/LeaveRoom, 2v2-DIAG) is
                // masked here at the source. Identity-latched, not config.
                // Non-broadcast seats keep today's raw form exactly.
                if (BroadcastMode.IsBroadcastIdentity)
                    return $"room={BroadcastMode.SafeRoomDesc()} players={pcount}/{max}";
                return $"room={r.Name} players={pcount}/{max}";
            }
            catch { return "(room-describe failed)"; }
        }
    }

    /// <summary>Photon callback target for 2v2 diagnostics. Logs every player
    /// enter/leave/disconnect with the relevant Photon state so we can trace
    /// which client dropped first and why.</summary>
    public class Cr2v2DiagCallbacks : MonoBehaviour,
        Photon.Realtime.IInRoomCallbacks,
        Photon.Realtime.IConnectionCallbacks,
        Photon.Realtime.IMatchmakingCallbacks
    {
        void OnEnable()  { try { PhotonNetwork.AddCallbackTarget(this); } catch { } }
        void OnDisable() { try { PhotonNetwork.RemoveCallbackTarget(this); } catch { } }

        public void OnPlayerEnteredRoom(Photon.Realtime.Player p)
        {
            // Roster changed: drop the same-frame fighter cache (r3).
            try { RoomActors.InvalidateFighterCache(); } catch { }
            // Poison convergence v3 (A2b): any entry, spectators included.
            try { PoisonSync.V3RoomEvent("player-entered", p); } catch { }
            // Item 19 edge E3: the roster grew, so the room's facing may have moved.
            AvatarDefaults.Evaluate("E3-entered");

            // Local classification cache. Best effort and LOCAL by design
            // (r9 deleted the announced-verdict property): the cross-client
            // consistent leave rule is prop-derived (no-u_id / impostor),
            // and this cache only adds suppression on seats that classified.
            bool entrantIsSpectator = false;
            try
            {
                if (RoomActors.IsSpectator(p)) entrantIsSpectator = true;
                else if (RoomActors.IsUnauthorized(p)) RoomActors.RecordRejected(p);
            }
            catch { }

            // Poison protocol: arm the roster quarantine on a REPLICATED
            // basis only (r8 find 2): every seat must make the identical
            // decision from the identical data, and the only replicated
            // discriminator is the cr_spec role prop. A declared spectator
            // never changes the fighter census (design-review blocker 1); an
            // UNMARKED intruder arms the 3s quarantine on EVERY seat
            // symmetrically — fair and fail-closed — until the master's
            // close removes it. Never gate this on IsUnauthorized: that
            // reads the LOCAL frozen roster, which seats legally disagree on.
            //
            // ...and for the same reason not on the line above either. The
            // paragraph said REPLICATED while the gate read `entrantIsSpectator`,
            // which is RoomActors.IsSpectator — a first-sight cache, i.e. the
            // per-seat timing dependence this whole rule exists to remove, one
            // layer up from the property it names (#302: the comment was a claim
            // the code below it did not keep). The cache is still computed above,
            // because the RecordRejected arm beside it is genuinely local; the
            // POISON arm now reads the property.
            bool entrantIsSpectatorReplicated = false;
            try { entrantIsSpectatorReplicated = RoomActors.IsSpectatorReplicated(p); } catch { }
            try { if (!entrantIsSpectatorReplicated) PoisonSync.NoteRosterChange("PlayerEntered"); } catch { }

            // Spectator entry: the master validates the claimed lease with the
            // server immediately (design §6.6) — invalid actors get kicked,
            // valid names go up as cr_spec_roster for the roster display.
            // MasterNoteSpectatorEntered seeds the 90s never-validated clock
            // and closes incompatible-protocol seats on the spot (Aug 10 r2
            // blocker 2 / find 9).
            try
            {
                if (RoomActors.IsSpectator(p) && Photon.Pun.PhotonNetwork.IsMasterClient)
                {
                    SpectatorSync.MasterNoteSpectatorEntered(p);
                    ApiClient.SpectateValidateActors();
                }
            }
            catch { }
            // Playtest #169b: vanilla sends faces via an UNBUFFERED RPC at
            // spawn (#226) — a late-joining spectator missed it, so bodies
            // rendered faceless. Every fighter re-sends its OWN face when a
            // spectator arrives (the proven FFA resync pattern; EquipFace is
            // idempotent, so fighters receiving the echo are unaffected).
            try
            {
                if (RoomActors.IsSpectator(p) && !RoomActors.LocalIsSpectator && Plugin.Instance != null)
                    Plugin.Instance.StartCoroutine(ResendLocalFaceForSpectator());
            }
            catch { }
            // Bug #224: same #226 class for team_/ovt_ entrants — under the
            // hosted-lobby flow the LAST joiner is the norm, and vanilla's
            // one UNBUFFERED RpcTarget.All face send at spawn means they
            // missed every earlier joiner's face for the whole sitting.
            // Every earlier seat re-sends its own face once the entrant
            // settles (coalesced inside Schedule; no-op outside team/ovt
            // rooms and on spectator seats). A spectator entrant in these
            // rooms also triggers the block above — the double send is
            // deliberate slack, idempotent per #226.
            try { FaceResync.Schedule("player-entered"); } catch { }
            // UNAUTHORIZED entrant (frozen roster, no spectator role, not a
            // fighter we froze): the master closes the connection at the door
            // (Codex r1 find 1 — the reserved seats must admit only granted
            // spectators). Inert until a roster is frozen. The rejection was
            // already CACHED above on every client, so the closed actor's
            // departure is suppressed everywhere (design-review blocker 2).
            try
            {
                if (FfaLateEntry.MasterMaySend() && !entrantIsSpectator && RoomActors.IsRejected(p))
                {
                    // BEST-EFFORT ONLY (r9 find 1): cooperative — the target
                    // complies only if ITS EnableCloseConnection is true (our
                    // spectator clients set it; hostile/vanilla clients keep
                    // their socket). Containment for a non-complying actor is
                    // the registration firewall, the fail-closed quorums and
                    // the scoped leave rules — not this call. The master
                    // sweep retries on its cadence (covers handoffs).
                    Plugin.Log.LogWarning($"[SPECTATE] close requested for unauthorized entrant actor {p?.ActorNumber} (cooperative)");
                    RoomActors.CooperativeClose(p);
                }
            }
            catch { }

            // Republish our cr_face every time a new player joins the room.
            // This fixes the "two characters missing in card-pick" bug where
            // a peer joined after our OnJoinedRoom-time publish so they never
            // received the cr_face property update.
            // Spectator: never publishes cosmetics (side-effect shutdown,
            // design §3.5) — but fighters DO republish when a spectator
            // arrives, which is exactly how the spectator learns their faces.
            try
            {
                if (CompetitiveRoomDetect.IsCompetitiveRoom() && !RoomActors.LocalIsSpectator)
                    FacePublisher.PublishLocal();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[POPUP] PlayerEntered face republish: {ex.Message}"); }

            if (!Diag2v2.IsActive()) return;
            try
            {
                int slot = -1, team = -1;
                if (p.CustomProperties != null)
                {
                    if (p.CustomProperties.ContainsKey("p_id")) int.TryParse(p.CustomProperties["p_id"].ToString(), out slot);
                    if (p.CustomProperties.ContainsKey(Player.VAR_TEAMID)) int.TryParse(p.CustomProperties[Player.VAR_TEAMID].ToString(), out team);
                }
                Plugin.Log.LogInfo($"[2v2-DIAG] PlayerEntered: nick='{p.NickName}' actor={p.ActorNumber} p_id={slot} t_id={team} {Diag2v2.DescribeRoom()}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2-DIAG] PlayerEntered log error: {ex.Message}"); }
        }

        /// <summary>The 2v2 team a seat advertises (`t_id`), or -1 when it does not say
        /// anything a 2v2 team can be. Same prop the leaver banner and DetermineLocalTeam
        /// read, so every seat in the room answers this identically. -1 means UNKNOWN,
        /// never "team 0".
        ///
        /// <para>A 2v2 `t_id` is 0 or 1 and nothing else. The prop is not 2v2's alone —
        /// FFA writes the player's own SLOT into it ("every player own team"), so a seat
        /// carrying a stale value from a previous FFA room can advertise 2, 3, 4. Taking
        /// any non-negative integer at face value turned each of those into its own
        /// one-member team, and a one-member team is always its own lowest id: every such
        /// seat elected itself and the reporter count could reach every survivor in the
        /// room instead of the two the election is designed to allow (r3 finding).
        /// Anything outside {0,1} is UNKNOWN. A seat that meets an unknown team, its
        /// own or the leaver's, reports the disconnect itself rather than trusting
        /// the room-wide rule to find a seat the server accepts (round 2 finding 2;
        /// DcReporterElection holds the rule and the parse).</para></summary>
        private static int TeamIdOf(Photon.Realtime.Player pl)
        {
            try
            {
                if (pl == null || pl.CustomProperties == null) return -1;
                object v;
                if (!pl.CustomProperties.TryGetValue(Player.VAR_TEAMID, out v)) return -1;
                return DcReporterElection.ParseTeamId(v);
            }
            catch { return -1; }
        }

        /// <summary>The Steam id a seat advertises (`u_id`, `unity_id` is NOT
        /// consulted here), or -1 when it advertises nothing a reporter election
        /// can compare. Replicated, so every seat reads the same value for the
        /// same actor — which is the whole reason the election uses it rather
        /// than anything locally derived.
        ///
        /// <para>A `photon_`-prefixed value is Photon's own placeholder for an
        /// actor with no Steam identity, never a Steam id, and it must not
        /// order against real ones.</para></summary>
        private static long SteamIdOf(Photon.Realtime.Player pl)
        {
            try
            {
                if (pl == null || pl.CustomProperties == null) return -1;
                object v;
                if (!pl.CustomProperties.TryGetValue("u_id", out v) || v == null) return -1;
                string s = v.ToString();
                if (string.IsNullOrEmpty(s) || s.StartsWith("photon_")) return -1;
                long n;
                if (!long.TryParse(s, out n) || n <= 0) return -1;
                return n;
            }
            catch { return -1; }
        }

        public void OnPlayerLeftRoom(Photon.Realtime.Player p)
        {
            // Roster changed: same-frame reads must not see the cached view
            // (Codex r3 — two same-frame departures vs the DC reporter).
            try { RoomActors.InvalidateFighterCache(); } catch { }
            // Poison convergence v3 (A2b): any departure, spectators included.
            try { PoisonSync.V3RoomEvent("player-left", p); } catch { }
            // Item 19 edge E11: a departure raises no property update, so this
            // is the only edge on which the facing can return to Modded.
            AvatarDefaults.Evaluate("E11-left");

            // A 2v2 DC fallback watch, if one is armed, is watching for exactly
            // this: the ELECTED seat leaving. Before any of the classification
            // below, because the watch reads the property payload Photon still
            // has on the departing actor, and because its answer ("it dispatched
            // nothing", "it left with a request in flight") does not depend on
            // whether this leaver is a fighter, a spectator or an impostor.
            try { DcReportSync.NoteActorLeft(p); } catch { }

            // A SPECTATOR (or unauthorized impostor — r3 CRITICAL: a copied
            // u_id leaving must never read as the REAL fighter's DC) leaving
            // is invisible to the match (design §3.6): no leaver banner, no
            // DC reporting, no FFA leaver ledger. The vanilla teardown
            // cascade is already suppressed by Spectator_LeaveIsInvisible;
            // this covers the MOD's own leave bookkeeping in the same
            // callback. PoisonSync's roster note still runs below — its scan
            // excludes spectators, and a missed roster-change note is worse
            // than a redundant one.
            // The no-u_id arm applies ONLY where pre-join staging is
            // guaranteed (r10 finds 1+2: in ranked 1v1 / casual rooms u_id
            // arrives post-join or never, so a genuine fighter's or vanilla
            // peer's departure must run vanilla teardown).
            bool leaverIsSpectator = false;
            try
            {
                leaverIsSpectator = RoomActors.IsSpectator(p)
                    || (RoomActors.ReplicatedIdentityGuaranteed()
                        && !RoomActors.HasReplicatedFighterIdentity(p))
                    || RoomActors.IsImpostorReplicated(p)
                    || RoomActors.IsRejected(p) || RoomActors.IsUnauthorized(p);
            }
            catch { }
            // Poison's leave note uses the REPLICATED subset only (r8 find
            // 2, r9): cr_spec, the SCOPED u_id-absence rule and the
            // impostor-duplicate rule are computed from replicated data
            // identically on every seat; the local caches are not consulted.
            // The cr_spec term said that and called IsSpectator, which IS a
            // local cache — the same divergence as the entry gate above, and
            // corrected the same way (#302, #432: the flag named one line, the
            // defect is the operation).
            bool leaverIsSpectatorReplicated = false;
            try
            {
                leaverIsSpectatorReplicated = RoomActors.IsSpectatorReplicated(p)
                    || (RoomActors.ReplicatedIdentityGuaranteed()
                        && !RoomActors.HasReplicatedFighterIdentity(p))
                    || RoomActors.IsImpostorReplicated(p);
            }
            catch { }

            // July 22 item 2 (bug #81): universal leaver banner — BEFORE the
            // Diag2v2 gate so casual/ranked 1v1 rooms get it too. Photon fires
            // this on every remaining seat, so the ally AND both opponents all
            // see who left. Display-only; every report path below is untouched.
            try { if (!leaverIsSpectator) GameStateWatcher.NotifyPlayerLeftRoom(p); } catch { }
            // Poison protocol: arm the roster quarantine — FIGHTER departures
            // only (design-review blocker 1: a spectator leaving never changes
            // the fighter census, and the 3s quarantine it armed disabled
            // block honouring for any poison stream starting inside it). The
            // sticky incapable flag is untouched either way.
            try { if (!leaverIsSpectatorReplicated) PoisonSync.NoteRosterChange("PlayerLeft"); } catch { }
            bool diagActive = Diag2v2.IsActive();
            if (diagActive)
            {
                try { Plugin.Log.LogInfo($"[2v2-DIAG] PlayerLeft: nick='{p?.NickName}' actor={p?.ActorNumber} {Diag2v2.DescribeRoom()}"); }
                catch { }
            }

            // 2v2 DC reporting: when a player drops mid-series, the surviving seats
            // the election below picks report the DC to the server: ONE elected
            // survivor on the non-DC team wherever the census proves the rule
            // room-wide, otherwise every seat DcReporterElection.ShouldReport names.
            //
            // THE DEPLOYED CONTRACT, restated from main.py's own
            // team_series_report_dc rather than from memory (r2 LOW). Two
            // outcomes: the whole SERIES completes to the non-DC team with full
            // Glicko and gold (no XP) only when that team had ALREADY won at
            // least one game AND the abandoned game holds >= 2 total points;
            // otherwise the series flips to status='dc_incomplete' with
            // invalidation_reason='dc_manual_pending' for manual resolution in
            // the admin panel. There is no 5-minute grace window on this path —
            // that is the legacy dc_paused flow, which only the state poll's
            // expiry sweep still reads. What DOES exist is the bug-245 resume:
            // if the same four re-queue within roughly thirty minutes the
            // matcher re-locks them onto THIS series with its scores kept and
            // clears the pending flag.
            //
            // This tree's server half (v1.41.0 beta round 2 finding 1; rounds 5
            // to 8, findings F25 to F31) reads the two points from its own
            // per-game record, never from the totals a report carries, and
            // settles a lead-forfeit only for a report that carries the physical
            // game's token, which ApiClient.ReportTeamSeriesDc reads as the
            // report is built.
            //
            // STRICTLY 2v2: the widened IsActive() also fires this callback in
            // ovt_ rooms, where ActiveTeamSeriesId can be a STALE id from an
            // earlier 2v2 sitting (it's only cleared on the reporter's client
            // at series completion). A rage-quit in a 1v2 game would otherwise
            // post report-dc against that old 2v2 series — whose membership
            // checks PASS when the trio overlaps the old roster — applying
            // real 2v2 Glicko/gold from a 1v2 game's points. 1v2 has no DC
            // path yet by design (unscored beta; the match report handles the
            // recorded outcome). FFA likewise: leavers are recorded in the
            // normal FFA report (left_early), never via the 2v2 DC pipeline.
            //
            // RJ Stage 2 (S1 step 9): a departure the hold classifier admits is
            // held. This seat's plan is built in the leave frame and latched in
            // the drop cut, unexecuted; the expiry runs it from the cut. Every
            // other departure, and any exception, takes the path of today:
            // build the plan and execute it in the same frame. The hold runs
            // ahead of the Diag2v2 gate because the cascade prefix
            // (NCH_OnPlayerLeftRoom_Hold_Patch) reads the same memo whatever
            // that gate says: a suppressed cascade always gets its cut.
            bool held = false;
            try
            {
                held = TeamHold.OnLeave(p, cut =>
                {
                    var pl = BuildDcPlan(p, leaverIsSpectator);
                    cut.Eligibility = pl != null ? pl.Kind : TeamHoldRules.DcKind.Nothing;
                    return pl;
                });
            }
            catch { held = false; }
            if (held || !diagActive) return;
            try { ExecuteDcPlan(BuildDcPlan(p, leaverIsSpectator)); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2-DC] report error: {ex.Message}"); }
        }

        /// <summary>One seat's 2v2 DC outcome of a departure, decided and not
        /// yet executed: the report fields, the watched seat and the log lines
        /// in the order the decision produced them. Built in the leave frame;
        /// executed in that frame, or by the RJ Stage 2 expiry from the drop
        /// cut.</summary>
        internal sealed class DcPlan
        {
            internal TeamHoldRules.DcKind Kind = TeamHoldRules.DcKind.Nothing;
            internal string SeriesId, MyId, DcSteamId, ObservedRoom;
            internal int T1Points, T2Points;
            internal bool Census;
            internal Photon.Realtime.Player Elected;
            internal List<Photon.Realtime.Player> Survivors;
            internal readonly List<string> Logs = new List<string>();
        }

        /// <summary>Executes a plan: its log lines in order, then the report
        /// (prompt or floor) or the fallback watch. Nothing, a stand-down and a
        /// null plan do nothing.</summary>
        internal static void ExecuteDcPlan(DcPlan plan)
        {
            if (plan == null) return;
            foreach (var line in plan.Logs) Plugin.Log.LogInfo(line);
            switch (plan.Kind)
            {
                case TeamHoldRules.DcKind.Fallback:
                    // `Survivors` is the fighter seats present at the drop — the
                    // same census list arm (1) elected from. ArmFallback takes the
                    // OUTCOME-protocol quorum over it and refuses, audibly, in a
                    // room where any of them is running a different one.
                    DcReportSync.ArmFallback(plan.SeriesId, plan.Elected, plan.MyId, plan.DcSteamId,
                                             plan.ObservedRoom, plan.Survivors);
                    return;
                case TeamHoldRules.DcKind.Prompt:
                case TeamHoldRules.DcKind.Floor:
                    // Every seat reaching this line is posting PROMPTLY: the census
                    // arm's elected reporter, or a floor-election seat. The physical
                    // game's token (v1.41.0 beta round 5, F25; round 6, F27 and F28)
                    // is read inside ApiClient.ReportTeamSeriesDc as the report is
                    // built, for a prompt report only, and logged there.
                    ApiClient.ReportTeamSeriesDc(plan.SeriesId, plan.MyId, plan.DcSteamId, plan.T1Points, plan.T2Points,
                                                 plan.ObservedRoom, false);
                    Plugin.Log.LogInfo($"[2v2-DC] reporter={plan.MyId} dc={plan.DcSteamId} series={plan.SeriesId} "
                        + $"pts={plan.T1Points}/{plan.T2Points} census={plan.Census} room={plan.ObservedRoom} (prompt)");
                    return;
                default:
                    return;
            }
        }

        /// <summary>The 2v2 DC decision of a departure, exactly the rule the
        /// leave callback ran in place before RJ Stage 2 split it from its
        /// execution. Null: no DC pipeline for this departure (a 1v2 or FFA
        /// room, a spectator, no series, the assembly phase, no ids).</summary>
        private DcPlan BuildDcPlan(Photon.Realtime.Player p, bool leaverIsSpectator)
        {
            if (!Diag2v2.IsActive()) return null;
            if (Diag2v2.IsOvt() || Diag2v2.IsFfa()) return null;
            if (leaverIsSpectator) return null;   // spectator exit: no DC pipeline
            {
                if (p == null) return null;
                string seriesId = ApiClient.ActiveTeamSeriesId;
                if (string.IsNullOrEmpty(seriesId)) return null;

                // Suppress DC reports during the assembly phase (between Photon
                // room join and "Round 1 active"). Two real testers (4-player
                // 2v2 sessions, v1.26.3 logs) hit this: when the slowest client
                // takes 25+ seconds to spawn-confirm, ANY transient leave by
                // another peer fires our OnPlayerLeftRoom which posts report-dc,
                // which races against the server's assembly_timeout cancel and
                // turns into a cascading DC storm — every remaining player's
                // OnPlayerLeftRoom fires when the others leave the now-cancelled
                // room, and the cascade kicks all 4 back to the menu. The
                // server's own assembly_timeout handler resolves stuck assemblies
                // without our help; we only want to report DCs once gameplay
                // has actually started.
                if (!GameStateWatcher.IsInMatch)
                {
                    Plugin.Log.LogInfo($"[2v2-DC] suppressed during assembly phase " +
                        $"(IsInMatch=false), leaver='{p?.NickName}' actor={p?.ActorNumber}");
                    return null;
                }

                // Resolve the DC'd player's Steam ID from their custom props.
                string dcSteamId = null;
                if (p.CustomProperties != null)
                {
                    if (p.CustomProperties.ContainsKey("u_id")) dcSteamId = p.CustomProperties["u_id"]?.ToString();
                    if (string.IsNullOrEmpty(dcSteamId) && p.CustomProperties.ContainsKey("unity_id"))
                        dcSteamId = p.CustomProperties["unity_id"]?.ToString();
                }
                if (string.IsNullOrEmpty(dcSteamId) && !string.IsNullOrEmpty(p.UserId)) dcSteamId = p.UserId;
                if (string.IsNullOrEmpty(dcSteamId) || dcSteamId.StartsWith("photon_")) return null;

                // Reporter election: exactly ONE PROMPT report wherever the rule can
                // be proven ROOM-WIDE, delayed redundancy behind it, and this seat's
                // honest point snapshot in every case.
                //
                // Bugs #384/#385 and the r2 HIGH above them. The server accepts a DC
                // report only from a member of the non-DC team
                // (team/series/{id}/report-dc: "reporter must be a member of the
                // non-DC team"). The original election picked the lowest id in the
                // ROOM — a different rule that agreed with the server's only by
                // luck, so the series was never closed, every survivor kept a live
                // 2v2 hold, and further 2v2 joins were refused until the lease TTL
                // ran out. The first repair OR'd the old room-wide elector with a
                // team-aware one to guarantee at least one report; that guarantee is
                // kept, but the OR could elect TWO seats, and two reports are NOT
                // equivalent:
                //
                //   `t1_points_total` / `t2_points_total` ride the query string,
                //   OUTSIDE the DC signature, as ONE seat's snapshot of a game that
                //   never produced a team_matches row. The deployed endpoint gates
                //   its lead-forfeit branch on `total_points >= 2` and settles on the
                //   FIRST accepted report (`WHERE status IN ('active','dc_paused')`).
                //   So two HONEST survivors whose snapshots straddle two points
                //   decide a rated series completion — ratings and gold — versus
                //   `dc_incomplete`, by which request took the row lock first. No
                //   dishonest client is required.
                //
                // Two arms, in this order:
                //
                //  (1) CENSUS, and only where the rule is ROOM-WIDE. A four-seat
                //      census (three survivors plus the leaver); every seat
                //      advertising a parseable and DISTINCT `u_id`; the four `t_id`
                //      values forming an exact 2/2 split with the leaver's team
                //      known; AND every survivor advertising `cr_dc2`, i.e. every
                //      seat that could report is evaluating THIS rule
                //      (RoomActors.DcReportSync). Then the lower `u_id` of the
                //      non-DC team's two survivors is the reporter, it is the same
                //      seat on every seat, and it posts at once. Its team-mate does
                //      NOT post a second report and does NOT arm a timer: it arms a
                //      watch on that seat's TERMINAL OUTCOME (DcReportSync.ArmFallback
                //      — the `cr_dcr` property the prompt seat publishes, and ONLY
                //      that) and posts nothing at all until one is known. It also
                //      requires every fighter seat to advertise `cr_dc3`, the outcome
                //      protocol's own key: a room running two outcome protocols is a
                //      room where a `cr_dcr` value does not mean what this build reads
                //      it as, and the watch is not armed there at all.
                //
                //      DEPARTURE IS NOT A TRIGGER — it STANDS THE WATCH DOWN. This
                //      note used to name "that seat leaving the room having dispatched
                //      nothing" as a second terminal signal, and the tree has not done
                //      that since the round that wrote the rule: the elected seat's
                //      departure is ITSELF a disconnect in this same series, the
                //      election runs again for it in the very next statements of this
                //      method, and a REAL-TOTALS report about it is composed in a
                //      process this watch holds no property from. Firing on the
                //      departure would put a zero-total post beside that report. The
                //      watch stands down instead and posts nothing (RoomActors
                //      DcReportSync.Evaluate, the `_watchGone` arm, checked BEFORE the
                //      failure arm).
                //
                //      An earlier cut of this arm armed a DELAYED post at +45 s, sized
                //      against the prompt seat's nominal retry budget; that is an
                //      elapsed-time guess about another seat's transaction, Unity's
                //      request timeout is not a hard ceiling under a stalled socket,
                //      and a last attempt landing after the delayed post decides a
                //      rated completion versus `dc_incomplete` by arrival order — the
                //      very defect this arm exists to remove. When the watch does fire
                //      it posts ZERO point totals, the one form the deployed endpoint
                //      can only record as `dc_incomplete`, so a fallback can never BE
                //      the report that rates a series.
                //
                //      THAT IS THE WHOLE CLAIM, AND IT IS NARROWER THAN THE ONE THIS
                //      NOTE USED TO MAKE. "No ordering of the two can select the rated
                //      completion" is FALSE and was withdrawn: a zero-total fallback
                //      that takes the row lock FIRST writes `dc_incomplete`, and a
                //      real-totals report behind it is answered `{"ignored": true}` —
                //      a rated lead-forfeit lost. The client-side table removes every
                //      schedule one seat can observe; a SECOND disconnect on a
                //      different seat is not orderable from inside any one client.
                //      NARROWING it is the SERVER lane's half, and narrowing is the
                //      word: this client sends `is_fallback=true` on exactly its
                //      fallback reports, and a server carrying the deferral rule
                //      records the fallback without settling, so a later real-totals
                //      report can still rate the series INSIDE A BOUND — one that is
                //      stated once, in full, at the `is_fallback` site in
                //      ApiClient.ReportTeamSeriesDc, and does not hold outside it.
                //      Against a server that does not carry the rule the parameter is
                //      ignored (#266) and the residual above stands unchanged — which
                //      is why it is written here as a residual and not as a closure.
                //      What neither covers is a refusal that would apply
                //      to both seats (a room the series no longer names, a series
                //      already gone): that is the endpoint's answer, not a delivery
                //      failure, and the watch reads it as terminal and stands down.
                //
                //  (2) EVERYTHING ELSE — a seat without `u_id`, duplicate ids, a
                //      `t_id` outside {0,1}, a census that is not 2/2, a roster
                //      mid-change, or one peer on a build that does not advertise
                //      `cr_dc2`. The FLOOR election runs: DcReporterElection's two
                //      lowest ids plus its team claim (v1.41.0 beta round 3 finding
                //      2), or, in a view it can check, the lowest id advertising the
                //      team that stayed plus the seat advertising the leaver's team
                //      (merge pass 1, follow-up 6); at least one report the server
                //      accepts, always, because
                //      zero reporters is the one outcome worse than the bug (#276).
                //      A peer on an older build runs its own older rule, and the
                //      two-seat bound holds only over the seats running this one.
                //      Its residual is the straddle described above. This tree's
                //      server half no longer reads the totals, so what can still
                //      differ between two honest reports is whether each carries
                //      the game's token (ApiClient.ReportTeamSeriesDc). An election is
                //      a property of the ROOM, and no client-side rule can be
                //      room-wide while a peer evaluates a different one — which is
                //      why arm (1) asks the room first instead of assuming it.
                //
                // THE REPORT ALWAYS CARRIES THIS SEAT'S HONEST SNAPSHOT. An earlier
                // cut of this election sent ZEROS from arm (2), on the reasoning that
                // `total_points = 0` cannot reach the lead-forfeit branch and is
                // therefore conservative. It is conservative for the SERVER and not
                // for the abandoned team: it converts a forfeit they have already
                // earned into `dc_incomplete`. Worse, it was reachable by the one
                // party with a motive — the leaver's own surviving team-mate omitting
                // `u_id`, or advertising a `t_id` outside {0,1}, fails the census on
                // EVERY seat and zeroes the totals for the whole room. And it bought
                // nothing against a liar, because every census input is
                // self-advertised: a client willing to lie satisfies arm (1) and
                // sends whatever totals it likes.
                //
                // WHAT A LYING CLIENT GAINS under THIS rule, enumerated (#283):
                //   * Faking `t_id` to look non-DC: nothing. The server resolves team
                //     membership from the series row, not from the report, and refuses
                //     a DC-team member with a 400.
                //   * Faking a low `u_id` to win arm (1): it must still be an actual
                //     non-DC member for the server to accept it, and such a seat was
                //     entitled to report anyway.
                //   * Breaking the census on purpose (an inconsistent `t_id`, a
                //     withheld `u_id`, a withheld `cr_dc2`): arm (2), the floor
                //     election every seat falls back to. It no longer changes
                //     WHAT is reported, only which seats report it — that is the
                //     whole reason the zeros are gone.
                //   * Going silent after winning arm (1): its team-mate's watch sees
                //     ONE terminal outcome — a published `cr_dcr=no`, i.e. every
                //     attempt answered and refused, or nothing ever dispatched — and
                //     closes the series with a zero-total report. Leaving the room is
                //     NOT that outcome and never was in the shipped rule: a departure
                //     stands the watch DOWN, because it is a fresh disconnect that the
                //     election closes with a real-totals report. Both seats are on the
                //     non-DC team, so the only party who can reach that downgrade is
                //     the abandoned team itself, and it downgrades its OWN forfeit;
                //     the leaver's side has no lever on it (#283). A seat that
                //     dispatches and then goes
                //     silent WITHOUT a terminal answer is the one state where its
                //     team-mate posts nothing at all, because a request may still be
                //     in flight and a fallback beside it would decide the series by
                //     arrival order again.
                //   * Submitting inflated points while legitimately elected: unchanged
                //     by this election and NOT closable from the client — the totals
                //     are client-attested and ride outside the signature. The server
                //     needed a per-game fact of its own (the server-contract note in
                //     the r2 notes), and this tree's server half has it: it decides
                //     from its own per-game record and only logs the totals (v1.41.0
                //     beta round 2 finding 1).
                string myId = MatchTracker.LocalSteamId;
                if (string.IsNullOrEmpty(myId)) return null;
                long myVal; if (!long.TryParse(myId, out myVal)) return null;

                int dcTeam = TeamIdOf(p);
                int myTeam = TeamIdOf(PhotonNetwork.LocalPlayer);

                bool teamsKnown = dcTeam >= 0 && myTeam >= 0;

                // CENSUS BASIS: the raw PlayerList filtered by the replicated
                // spectator prop, read from the property on every call.
                //
                // NOT RoomActors.ActiveFighters(): that filter consults the frozen
                // roster, which is LOCAL state — two seats freezing at different
                // moments classify a prop-less actor differently, and an election two
                // seats compute differently is exactly the duplicate this arm exists
                // to rule out.
                //
                // NOT RoomActors.IsSpectator() either, which is the correction this
                // round makes: that helper caches its answer by ActorNumber at FIRST
                // SIGHT and never re-reads the property, so it too is per-seat state
                // whose answer depends on when this seat happened to look. The role
                // itself is immutable inside a room (staged pre-join, never cleared
                // mid-room), so the uncached read is the one that actually delivers
                // the "same bytes on every seat" this arm needs, and it self-heals
                // for an actor whose payload was not readable yet instead of fixing
                // the wrong answer in place for the rest of the room.
                //
                // Either misclassification costs the same thing and no more: the
                // survivor count stops being 3, arm (1) is refused, and the room runs
                // the floor election. Even the pair of them at once — one fighter read
                // as a spectator while one spectator is read as a fighter, which keeps
                // the count at 3 — lands in the same place, because a spectator clears
                // `t_id` when it stages its role and an actor with no team fails the
                // 2/2 split below.
                //
                // Photon has already removed the leaver from PlayerList by the time
                // this callback runs, so `survivors` never contains `p`.
                var survivors = new List<Photon.Realtime.Player>();
                try
                {
                    var all = PhotonNetwork.PlayerList;
                    if (all != null)
                        for (int i = 0; i < all.Length; i++)
                        {
                            var a = all[i];
                            if (a == null || a.ActorNumber == p.ActorNumber) continue;
                            if (RoomActors.IsSpectatorReplicated(a)) continue;
                            survivors.Add(a);
                        }
                }
                catch { survivors.Clear(); }

                // Arm (1)'s preconditions. Every one is read from a replicated
                // property, and the last one asks whether the OTHER seats are even
                // running this rule: without it, "exactly one reporter" would be a
                // property of this process rather than of the room, and a peer on the
                // previous build would post its own report beside ours anyway.
                int missingCap = -1;
                bool roomWide = DcReportSync.AllCapable(survivors, out missingCap);
                // The arm (1) census and the floor election are one pure rule,
                // TeamHoldRules.DecideDc (the RJ Stage 2 harness runs it): four
                // distinct readable ids, readable teams, this seat among the
                // survivors as itself, and a 2/2 split. A 2v2 sitting is 2/2;
                // anything else means at least one seat is advertising a team it
                // is not on, and the split is the cheapest replicated cross-check
                // that catches it.
                var census1 = new List<TeamHoldRules.DcSurvivor>();
                for (int i = 0; i < survivors.Count; i++)
                    census1.Add(new TeamHoldRules.DcSurvivor(SteamIdOf(survivors[i]), TeamIdOf(survivors[i]),
                                                             survivors[i].IsLocal, survivors[i].ActorNumber));

                // The room is a fact of the OBSERVATION, not of the dispatch — read
                // it HERE, before either arm can leave the room. A delayed or
                // watch-driven post reading `PhotonNetwork.CurrentRoom` at send time
                // would hand the server an empty hint, losing the bug-245 fence that
                // stops a report about an abandoned room lead-forfeiting the sitting
                // that resumed it.
                string observedRoom = "";
                try { observedRoom = PhotonNetwork.InRoom ? (PhotonNetwork.CurrentRoom?.Name ?? "") : ""; } catch { }

                var plan = new DcPlan
                {
                    SeriesId = seriesId, MyId = myId, DcSteamId = dcSteamId, ObservedRoom = observedRoom,
                    Survivors = survivors,
                };
                // The floor census is enumerated only when arm (1) is refused.
                var d = TeamHoldRules.DecideDc(myVal, myTeam, dcTeam, SteamIdOf(p), roomWide, missingCap,
                                               census1, FloorCensus(p));
                plan.Kind = d.Kind;
                plan.Census = d.Unique;
                if (d.Unique)
                {
                    if (d.Kind == TeamHoldRules.DcKind.StandDown) return plan;   // the other team elects
                    if (d.Kind == TeamHoldRules.DcKind.Prompt)
                        plan.Logs.Add("[2v2-DC] elected from the replicated census "
                            + "(2/2 teams, four distinct ids, every survivor advertising "
                            + DcReportSync.CapabilityProp + ") — the one prompt reporter");
                    else
                    {
                        // The other non-DC survivor. NO TIMER, and no report now: it
                        // watches the elected seat's transaction and acts only on a
                        // terminal outcome of it. See DcReportSync's protocol note for
                        // why an elapsed-time net was the wrong instrument and what
                        // "terminal" means here.
                        Photon.Realtime.Player elected = null;
                        for (int i = 0; i < survivors.Count; i++)
                            if (survivors[i].ActorNumber == d.ElectedActor) { elected = survivors[i]; break; }
                        plan.Elected = elected;
                        plan.Logs.Add("[2v2-DC] not the elected seat — watching actor "
                            + (elected != null ? elected.ActorNumber.ToString() : "?")
                            + " for a terminal outcome of its report (" + DcReportSync.OutcomeProp
                            + "); this seat posts NOTHING until one is known");
                        return plan;
                    }
                }
                else
                {
                    if (teamsKnown && survivors.Count == 3 && !roomWide)
                        plan.Logs.Add("[2v2-DC] census arm refused: "
                            + (missingCap >= 0 ? $"actor {missingCap}" : "a survivor")
                            + $" does not advertise {DcReportSync.CapabilityProp} — floor election "
                            + "(that seat runs its own build's rule)");
                    // FLOOR ELECTION: DcReporterElection.ShouldReport, the same code
                    // its sentinel runs (v1.41.0 beta round 2 finding 2, round 3
                    // finding 2). At least one report the server ACCEPTS, always:
                    // the floor is the TWO lowest ids among the survivors, whatever
                    // any `t_id` says, and of the three survivors the server refuses
                    // exactly one, the leaver's teammate. The team claim can only ADD
                    // a report, and a seat that cannot read the teams reports as
                    // well. Duplicates are cheap: the first accepted report settles
                    // the series and the rest no-op.
                    //
                    // It replaces the floor both lanes carried before they met. The
                    // room-wide lowest id alone is refused whenever it is the
                    // leaver's teammate. The 886bed8 lane's first cut of the L3
                    // stand-down (a seat that looks like the leaver's teammate
                    // defers while another survivor looks eligible) reaches ZERO
                    // accepted reports when the leaver advertises the team that
                    // stayed: with real teams {L,A} and {B,C}, A < B < C, and L
                    // advertising B's team, A looks eligible and reports -- refused,
                    // it is L's real teammate -- while B and C both read as the
                    // leaver's team and stand down. Zero reporters is the one
                    // outcome worse than the bug (#276).
                    //
                    // THE STAND-DOWN AS RULED (v1.41.0 merge pass 1, follow-up 6):
                    // exactly one of the eligible seats reports, the lowest id, and
                    // the stand-down belongs to an eligible seat that is not the
                    // lowest eligible one. ShouldReport applies it only in a view it
                    // can check (every survivor's `u_id` and `t_id` readable and the
                    // advertised split 2/2), where the seat advertising the leaver's
                    // team still reports; in the example above the view is not 2/2
                    // (three seats advertise B's team) and the floor decides.
                    //
                    // Its census is the fighter view (RoomActors.ActiveFighters), as
                    // it was where this rule was certified. That view is LOCAL state,
                    // which is why arm (1) above may not use it; the floor needs no
                    // agreement between seats, only that each seat's census is the
                    // leave's other survivors, and once the roster is frozen the
                    // fighter view keeps a spectator or a stranger out of it. The
                    // bound, and what it does not cover, is stated once in
                    // DcReporterElection.ShouldReport.
                    // The census is FloorCensus below, DecideDc enumerates it here.
                    if (d.Kind != TeamHoldRules.DcKind.Floor) return plan;
                    if (d.ConsistentView)
                        plan.Logs.Add(myTeam == dcTeam
                            ? "[2v2-DC] reporting from a consistent 2/2 view as the seat advertising the leaver's team "
                              + "(the server refuses it if that team is true; the lower id of the other team reports as well)"
                            : "[2v2-DC] reporting from a consistent 2/2 view as the lower id of the team that stayed");
                    else if (!teamsKnown)
                        plan.Logs.Add($"[2v2-DC] reporting with the teams unreadable (my t_id={myTeam}, "
                            + $"leaver t_id={dcTeam}); the server accepts only the team that stayed");
                    else if (!d.OnFloor)
                        plan.Logs.Add("[2v2-DC] reporting as the non-disconnected team's lowest id "
                            + "(the two lowest ids in the room report as well)");
                }

                // Point totals: this seat's honest snapshot in BOTH arms. See the
                // paragraph above for why the arm-(2) zeros are gone. They ride
                // along for the server's log and the forfeit row's history: this
                // tree's server decides whether the abandoned game saw real play
                // from its own per-game record, never from these (v1.41.0 beta
                // round 2 finding 1).
                // Latched with the decision, in the leave frame: the points of the
                // drop, whether the plan runs now or at an RJ Stage 2 expiry. The
                // watch arm returned above without a report, so there is no delay
                // parameter left to get wrong.
                plan.T1Points = GameStateWatcher.LastP1Points;
                plan.T2Points = GameStateWatcher.LastP2Points;
                return plan;
            }
        }

        /// <summary>The floor election's census: the fighter view
        /// (RoomActors.ActiveFighters) without the leaver and this seat, read
        /// lazily so it is enumerated only when arm (1) is refused.</summary>
        private static IEnumerable<DcReporterElection.Peer> FloorCensus(Photon.Realtime.Player p)
        {
            foreach (var pp in RoomActors.ActiveFighters())   // census: reporter election over fighters only
            {
                if (pp == null || pp.ActorNumber == p.ActorNumber) continue;  // skip the leaver
                if (pp.IsLocal) continue;
                string ppSid = null;
                if (pp.CustomProperties != null && pp.CustomProperties.ContainsKey("u_id"))
                    ppSid = pp.CustomProperties["u_id"]?.ToString();
                yield return new DcReporterElection.Peer(ppSid, TeamIdOf(pp));
            }
        }

        /// <summary>Fighter-side face re-send for a just-joined spectator
        /// (playtest #169b). Send mechanics — including the all-zero-face
        /// guard from FFA review find 13 — live in the shared
        /// FaceResync.TrySendLocalFace (bug #224 factored them out).</summary>
        private static System.Collections.IEnumerator ResendLocalFaceForSpectator()
        {
            yield return new WaitForSecondsRealtime(2f);   // let the join settle
            FaceResync.TrySendLocalFace("SPECTATE");
        }

        public void OnPlayerPropertiesUpdate(Photon.Realtime.Player target, ExitGames.Client.Photon.Hashtable changedProps)
        {
            // The elected 2v2 DC reporter announces where its report has got to
            // through this callback (cr_dcr). FIRST statement: the very next
            // block returns from the whole method on a null payload, and this
            // one reads the actor, not the payload — a coalesced update that
            // arrives with nothing we recognise still carries the actor's
            // current properties.
            try { DcReportSync.NoteActorProps(target); } catch { }
            // Poison convergence v3 (A2b): a cr_pois3 change on any actor.
            try { PoisonSync.V3PropsChanged(target, changedProps); } catch { }
            // Item 19 fix pass 3 (H3): a remote picker's face carrier ARRIVED
            // (the join snapshot never comes through here); the card-pick popup
            // applies it only when it is that picker's value for this pick.
            try { PopupCarriers.Arrived(target, changedProps); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[POPUP] carrier arrival failed: {ex.Message}"); }
            // Item 19 edge E4: a peer's cr_* properties (or this seat's own role)
            // may have arrived, which can move the room's facing either way.
            AvatarDefaults.Evaluate("E4-props");

            // r8 M4: identity and role are what the lag-notice window keys on,
            // and both of them change through this callback. A change that
            // lands and reverts between two frames leaves nothing behind in
            // the key itself, so the generation counter is the trace. Only the
            // properties that participate in that key — bumping on every card
            // or cosmetic property would discard usable windows for nothing.
            //
            // cr_prox1 joins that set (bug 389). The proximity-victim census
            // asks whether EVERY fighter advertises it, caches the answer, and
            // keys that cache on this counter; a seat whose key arrives after
            // the census ran would otherwise leave one seat re-resolving the
            // victim while another drains a stale one on the same damage tick.
            // The two spectator keys above already move the counter, and they
            // are the other half of that census's denominator.
            try
            {
                if (changedProps == null) return;
                if (changedProps.ContainsKey("u_id")
                    || changedProps.ContainsKey(RoomActors.SPEC_PROP)
                    || changedProps.ContainsKey(RoomActors.SPEC_LEASE_PROP)
                    || changedProps.ContainsKey(ProximityVictim.CapabilityProp))
                    RoomActors.NoteRosterIdentityChange();
            }
            catch { }
        }
        public void OnRoomPropertiesUpdate(ExitGames.Client.Photon.Hashtable propertiesThatChanged)
        {
            // Item 19 edge E12: cr_ff (read by IsModIssuedRoom) is a ROOM
            // property that can land after the join. It triggers a fresh
            // evaluation and is logged; it never decides the face (fix pass 1,
            // BR-H1: only the every-fighter census can answer Modded).
            AvatarDefaults.Evaluate("E12-roomprops");
            // RJ Stage 2 (S4 step 5): an absent seat's grant (cr_tap) is
            // applied through the one seat-log writer on every client.
            try { TeamHoldPick.OnRoomProps(propertiesThatChanged); } catch { }
        }
        public void OnMasterClientSwitched(Photon.Realtime.Player newMasterClient)
        {
            // Bug #269: a handoff revokes our authority to speak for the room,
            // so any unconsumed map-scale publish ticket dies here — before
            // the spectator-transfer block below, which can return early.
            try { FfaMapScale.OnMasterClientSwitched(); } catch { }
            // RJ-DRIFT change 3: a handoff invalidates N1's ticket (this
            // seat's memory of its own confirmed cr_ffa_cyc write).
            try { FfaMode.OnMasterClientSwitched(); } catch { }
            // V11 item 13: the switch's telemetry (EVT_MASTER), then the
            // authority fence. A fenced master hands the role on itself, so
            // the spectator hand-off below runs only when the fence did not.
            try { FfaLateEntry.OnMasterSwitched(newMasterClient); } catch { }
            // Master authority must never rest on a spectator (design §3.6):
            // simulation ownership on a client with no characters and no
            // stake. Photon assigns the LOWEST ActorNumber, and spectators
            // join later (higher numbers), so this is a rare-churn case —
            // but a long FFA can reach it. Only the new master itself can
            // call SetMasterClient, so the handoff runs on the spectator's
            // own client, targeted at the lowest fighter.
            try
            {
                // FenceMaster() runs first at every switch (it catches its own
                // faults); true means it handed the role on itself.
                if (!FfaLateEntry.FenceMaster() && newMasterClient != null && newMasterClient.IsLocal
                    && SpectatorSession.IsLocalSpectator)
                {
                    var fighters = RoomActors.ActiveFighters();
                    if (fighters.Length > 0)
                    {
                        Plugin.Log.LogWarning($"[SPECTATE] became master — transferring to fighter actor {fighters[0].ActorNumber}");
                        Photon.Pun.PhotonNetwork.SetMasterClient(fighters[0]);
                    }
                    else
                    {
                        // No fighter can accept: the match is over. Leave.
                        SpectatorSync.LeaveToMenu("no fighter to hold master");
                    }
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[SPECTATE] master handoff: {ex.Message}"); }

            if (!Diag2v2.IsActive()) return;
            try { Plugin.Log.LogInfo($"[2v2-DIAG] MasterClientSwitched: new='{newMasterClient?.NickName}' actor={newMasterClient?.ActorNumber}"); }
            catch { }
        }

        public void OnConnected() { }
        public void OnConnectedToMaster()
        {
            // Sept 7 item 3: trigger (a) of the region ping sweep — ignored in
            // OfflineMode inside, scheduled 3 s out. JoinWhenMasterReady is untouched.
            try { RegionPingSweep.NoteConnectedToMaster(); } catch { }
        }
        public void OnDisconnected(Photon.Realtime.DisconnectCause cause)
        {
            // Bug 392 items A(2)+B: this is the ONLY place the DisconnectCause
            // exists on this client, and it was logged and dropped — so no
            // exit hook could tell a transport failure from a player who chose
            // to leave, and the player was told nothing about why the game
            // ended. Record it before anything below can return early. The
            // store keeps ONLY involuntary causes, only for a short validity
            // window, and any other cause clears it.
            //
            // The notice is HANDED OVER here, not torn down. An earlier
            // version cleared it and left the explaining to the room-exit
            // toast, which is a surface that can decline the message: it
            // renders nothing when the player has notifications switched off,
            // and nothing while a critical cue still owns the slot, reporting
            // both by returning false. The amber line is deliberately not
            // behind the [Network] opt-in so that it reaches the player it is
            // for, so clearing it and promising a toast instead moved the one
            // guaranteed message onto the one that is not — and removed it a
            // full hold window before it would have expired. A player with
            // notifications off then saw the warning vanish and nothing take
            // its place, which is the complaint this item exists to fix.
            //
            // So: an involuntary cause REPLACES the "you may be dropped"
            // warning with the one that says it happened, on the same
            // surface; a cause the player chose clears it as before, because
            // someone who pressed Leave needs no explanation.
            try
            {
                double nowS = TransportExit.NowSeconds();
                string dcCause = cause.ToString();
                TransportExit.NoteDisconnect(dcCause, nowS);
                bool noticeRaised = TransportExit.NoteDisconnectNotice(dcCause, nowS);
                // The handover decision is LOGGED rather than discarded,
                // for the reason the room-exit toast logs which surface
                // spoke: the amber line is drawn only from
                // CompetitiveUI.DrawLagNotices, which returns on the
                // broadcast identity and on a spectator seat BEFORE it
                // computes the line. On those seats the notice is raised
                // and never drawn, so a screen reading cannot witness this
                // item there at all, and an acceptance row that can only
                // be read off the screen is unsatisfiable on them by
                // construction (#476/#570: confirm the gate admits the
                // seat the acceptance needs).
                //
                // seatCanDraw reports those same two gates as they read
                // HERE, at the disconnect - it is a reading, not a claim
                // about a later repaint. It is independent of the
                // [Network] notices opt-in, which the transport line
                // deliberately does not sit behind.
                bool seatCanDraw = false;
                try
                {
                    seatCanDraw = !BroadcastMode.IsBroadcastIdentity
                                  && !RoomActors.LocalIsSpectator;
                }
                catch { }
                Plugin.Log.LogInfo(
                    $"[LAG-DIAG] transport notice handover cause={dcCause} " +
                    $"raised={noticeRaised} seatCanDraw={seatCanDraw}");
            }
            catch { }
            // Release B §1: the head-to-head line dies with the room — first
            // statement, so an in-flight response can never bind to the next
            // room. Idempotent.
            try { H2HSummary.Invalidate(); } catch { }
            try { GameStateWatcher.ClearSessionUuid(); } catch { }   // Sept 6 item c: the id dies with the room
            try { SawTargetSync.ResetForRoomChange(); } catch { }    // and so does its verdict line (see OnJoinedRoom)
            // ...and the 2v2 DC fallback watch, which is a fact of ONE room and
            // one series: a watch carried across a room edge would be waiting on an
            // actor number that now names somebody else.
            try { DcReportSync.ResetForRoomChange(); } catch { }
            try { CardDrawEvidence.FreezeRoomFacts(); } catch { }     // the card record's room facts, before the reset (CD-M2)
            try { RoomRules.ResetLatched(); } catch { }              // room rules die with the room (§5.2)
            try { VanillaCardSequence.OnRoomLeft(); } catch { }      // and the vanilla-mode card sequence with them (§6)
            // Item 19 edge E7: a disconnect may produce no OnLeftRoom. Never inside
            // an InRoom test: the census reads InRoom itself, and an evaluation
            // with no room is where a forced face is given back, even while the
            // old GameManager still reports a game (fix pass 1, M3).
            AvatarDefaults.Evaluate("E7-disconnect");
            // lag-332 W1 (impl-review r5 MEDIUM 7): a disconnect that produces no
            // OnLeftRoom must still close the room/game telemetry — first
            // statement, before any early return below. Idempotent: with no
            // room active it only re-bases per-room state.
            try { NetworkReplicaDiagnostics.OnRoomLeft(); } catch { }
            // Broadcast r2 find 1: a full disconnect terminally resolves any
            // in-flight spectate JoinRoom op (the socket is gone; nothing can
            // deliver it). Must run before the diag early-return below.
            try { SpectatorJoiner.NoteJoinSettled($"disconnected ({cause})"); } catch { }
            // A teardown window is bound to the room it was opened in, and a
            // socket loss reaches here WITHOUT an OnLeftRoom (the same
            // asymmetry the telemetry close above is here for). Without this
            // the window survives to its horizon and can sample menu teardown,
            // or a fast join into the next room, under the old seat. Before
            // the early return below, and idempotent.
            try { SpectatorTeardownProbe.CloseWindow("disconnected"); } catch { }
            if (Diag2v2.PendingSlot() < 0) return;
            try { Plugin.Log.LogWarning($"[2v2-DIAG] Disconnected: cause={cause} stack={Diag2v2.ShortStack()}"); }
            catch { }
        }
        public void OnRegionListReceived(Photon.Realtime.RegionHandler regionHandler) { }
        public void OnCustomAuthenticationResponse(System.Collections.Generic.Dictionary<string, object> data) { }
        public void OnCustomAuthenticationFailed(string debugMessage) { }

        public void OnFriendListUpdate(System.Collections.Generic.List<Photon.Realtime.FriendInfo> friendList) { }
        public void OnCreatedRoom() { }
        public void OnCreateRoomFailed(short returnCode, string message)
        {
            if (Diag2v2.PendingSlot() < 0) return;
            Plugin.Log.LogWarning($"[2v2-DIAG] CreateRoomFailed: code={returnCode} msg={message}");
        }
        public void OnJoinedRoom()
        {
            // v1.41.0 beta round 7, finding F29: every join, a rejoin of the
            // same room included, breaks the physical-game ordinal and the
            // game token this seat held (the poll can miss a leave+join inside
            // one tick, so the reliable Photon edge does it). Only a host's
            // publish grounds them again (TeamGameNumber, "Which physical
            // game").
            try
            {
                string tgnLine = TeamGameNumber.Live.NoteRoomJoined(PhotonNetwork.CurrentRoom?.Name ?? "");
                if (tgnLine != null) Plugin.Log.LogInfo(tgnLine);
            }
            catch { }
            // Item 19 edge E2: the join. The room's facing is derived from the
            // room and its fighters' published properties, on every edge.
            AvatarDefaults.Evaluate("E2-joined");
            // V11 I1: joined_room, for every join.
            try
            {
                var jr = PhotonNetwork.CurrentRoom;
                JoinTimeline.Step("joined_room", "actors=" + (jr != null ? jr.PlayerCount : 0) + "/" + (jr != null ? jr.MaxPlayers : 0)
                                  + " master=" + (PhotonNetwork.IsMasterClient ? "true" : "false")
                                  + " actor=" + (PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : 0));
            }
            catch { }
            // Bug 392: a new room starts with no inherited transport state.
            // The cause store has its own validity window, but a window is a
            // soft bound and a room edge is a hard one — without this, a
            // disconnect recorded seconds before a fast rejoin could tag the
            // NEXT room's exit as involuntary (#430: a cached flag on a lossy
            // edge inherited by the next room). Same for a silence notice left
            // on screen from the previous room.
            try { TransportExit.ResetAll(); } catch { }
            // Bug 235 diagnostics bind to the reliable Photon room edge so a
            // fast leave+rejoin cannot merge two sittings' counters/budgets.
            try { NetworkReplicaDiagnostics.OnRoomJoined(); } catch { }
            // The saw-targeting verdict line is per ROOM, and until this call
            // existed it was per PROCESS: SawTargetSync.ResetForRoomChange had no
            // caller at all, so its de-duplication key survived every room and the
            // second sitting of a session logged nothing. A bundle then cannot tell
            // "the quorum was evaluated and applied in that room" from "the patch
            // never attached", which is the one question the line is there to
            // answer (#342 — a diagnostic that cannot speak proves nothing).
            try { SawTargetSync.ResetForRoomChange(); } catch { }
            try { DcReportSync.ResetForRoomChange(); } catch { }   // same room-scoped lifetime
            // Sept 6 item c: the reliable join edge mints the session id too (the
            // poll can miss a leave+join inside one tick); no game precedes either.
            try { GameStateWatcher.MintSessionUuid(); } catch { }
            // The music probe's private source must not survive a room entry.
            // Its own tick asks the same question, but a join can land after
            // that tick has already read "menu", so the reliable Photon edge is
            // what makes "never inside an online room" true rather than true by
            // the next poll. Offline joins are not an end — the Sandbox is
            // where the probe runs.
            try { MusicStreamProbe.OnRoomJoined(); } catch { }
            // THE join transition, before anything below can return early.
            // Both occupancy counters move, the queue's pairing is retired
            // against the line's counter, and the series record is stamped or
            // dropped against the series counter — one ordering, one body, in
            // H2HRules where the self-test executes it.
            //
            // The room name is read into locals FIRST and the read has its own
            // guard: passing a Photon expression in the argument list would
            // mean a throw skips the bumps as well, leaving the previous
            // occupancy's records standing, which is the unsafe direction. A
            // join we cannot name still moves both counters and drops the
            // binding — we joined something, and we cannot prove it is the
            // room the id was published for.
            //
            // This used to be two sites forty-one lines apart with the
            // broadcast fence's `return` between them, so a seat that took
            // that fence retired its pairing and never moved the series
            // counter at all.
            string joinedRoomName = null;
            bool joinedRoomNameKnown = false;
            try
            {
                joinedRoomName = Photon.Pun.PhotonNetwork.CurrentRoom?.Name;
                joinedRoomNameKnown = joinedRoomName != null;
            }
            catch { }
            try { ApiClient.OnRoomJoined(joinedRoomName, joinedRoomNameKnown); } catch { }
            // Release B §1: the head-to-head line's per-incarnation cache,
            // cleared after the transition above has moved the counter it is
            // keyed by. The request itself is gated on the fighter/1v1 rule at
            // tick time.
            try { H2HSummary.OnJoinedRoom(); } catch { }
            // Join-op settlement bookkeeping BEFORE anything can early-return
            // (broadcast r2 find 1): a room entry terminally resolves the one
            // spectate JoinRoom op that can be in flight. Pure flag clear;
            // no-op when no op is outstanding.
            try { SpectatorJoiner.NoteJoinSettled("joined"); } catch { }
            // §2c fence FIRST among the branches (Codex mod-r1 F2): on the
            // broadcast identity, a join without an active spectator session
            // (raw/vanilla join, or a cancelled spectate join landing late —
            // r1 F1) must abort BEFORE any fighter setup below runs (face
            // publish, 2v2 GM activation/force-start). BroadcastMode.FenceTick
            // remains the periodic backup. No-op on every other install.
            try { if (BroadcastMode.OnJoinedRoomFence()) return; } catch { }
            // Fresh room: the previous room's frozen fighter roster and the
            // master's spectator-admission state are both stale (Codex r1
            // find 1 family). Runs for every role, before any branch.
            try { RoomActors.OnJoinedNewRoom(); } catch { }
            try { SpectatorSync.MasterResetSpectatorState(); } catch { }
            // Bug 213: republish this seat's chat-mute marker for the new room.
            // Photon player properties PERSIST across rooms (#182), so a value
            // written in a previous room would otherwise be carried in
            // unrefreshed — and the state can legitimately have changed (via M
            // or the Settings toggle) while we were at the menu. Runs for every
            // role, before the spectator branch returns: a spectator can mute
            // chat too, and the fighters should see that.
            try { CompetitiveUI.PublishChatMuteState(); } catch { }
            // Callback-bound edge reset (Aug 10 r2 find 8) — the poll's
            // wasInRoom sampling can miss a fast leave+join.
            try { GameStateWatcher.ResetSpectateAttestEdges(alsoRoomTally: true); } catch { }
            // Tournament banner: clear-then-seed on the CALLBACK, not only
            // the 10 Hz polled join edge (Codex tournament r1 find 5 — a
            // leave+join between polls keeps inRoom=true, so the polled
            // clear/seed never runs and a stale tournament flag could leak
            // into this room, or an sct- room
            // could miss its banner seed entirely). Runs for every role;
            // spectators just carry a cleared context.
            try
            {
                // The incarnation bump and the series record's join both ran
                // here until 2026-09-06. They now run in ApiClient.OnRoomJoined
                // at the top of this method, above the broadcast fence's
                // return, together with the pairing retirement they have to be
                // ordered against.
                GameStateWatcher.ClearTournamentContext();
                string _rn = Photon.Pun.PhotonNetwork.CurrentRoom?.Name ?? "";
                if (_rn.StartsWith("sct-", StringComparison.Ordinal)
                    && !SpectatorSession.IsLocalSpectator)
                    GameStateWatcher.SetTournamentContext(true, "");
            }
            catch { }
            // Esc-menu leave confirm. Disarm FIRST, unconditionally (r4 find
            // 2): if both room-exit observers missed a fast transition and
            // the same scene button survived, an armed guard would otherwise
            // carry into a CASUAL or spectated room and make its MAIN MENU
            // button ask for two clicks where one is correct. Disarm is a
            // no-op when not armed. Then arm if this room qualifies — the
            // callback ATTEMPTS it on the join frame (discovery or reflection
            // can abort); the recurring poll tick retries and re-arms.
            try { EscMenuLeaveGuard.Disarm(); } catch { }
            // LEAVE MATCH row: bump the room generation + reset its confirm on
            // EVERY join (same-name rejoin included); the recurring poll
            // reconciles visibility/injection afterwards.
            try { EscLeaveRow.OnRoomJoined(); } catch { }
            try
            {
                if (!SpectatorSession.IsLocalSpectator && CompetitiveRoomDetect.IsCompetitiveRoom())
                    EscMenuLeaveGuard.Arm();
            }
            catch { }

            // SPECTATOR BRANCH (design §3.3): before ANY fighter work. A
            // spectator client runs none of the fighter setup below — no
            // face publish, no cosmetic reapply, no 2v2 GM activation or
            // force-start, no pending-slot logic. SpectatorSync owns the
            // session from here.
            try
            {
                if (SpectatorSession.IsLocalSpectator)
                {
                    SpectatorSync.OnJoinedSpectatorRoom();
                    // Bug 243 (client review find 2): this early return sits
                    // BEFORE the fighter-side coroutine launcher, so the
                    // spectator card-bar extension was structurally
                    // unreachable — start it here. The coroutine's own gates
                    // handle everything else (FFA yields break, 1v2 targets 3
                    // bars, non-team rooms exit via Diag2v2.IsActive-shaped
                    // mode reads which are room-identity-based, #149).
                    try
                    {
                        if (Diag2v2.IsActive() && Plugin.Instance != null)
                            Plugin.Instance.StartCoroutine(Setup4PlayerCardBarsWhenReady());
                    }
                    catch (Exception cex) { Plugin.Log.LogWarning($"[SPECTATE] card-bar setup start: {cex.Message}"); }
                    return;
                }
            }
            catch (Exception ex) { Plugin.Log.LogError($"[SPECTATE] joined-room branch: {ex.Message}"); }

            // Stale-slot hygiene: a pending team-mode slot only makes sense for
            // the room it was issued for. Joining any OTHER kind of room means
            // that pending join was abandoned — without this clear, the stale
            // slot keeps Diag2v2.IsActive() true in casual/1v1 rooms, which
            // activates the slot→team skin mapping there (both players would
            // bake skin 0). The slot is published pre-join, so the MATCHING
            // room always arrives with it intact and never hits this branch.
            try
            {
                string rn = PhotonNetwork.CurrentRoom?.Name ?? "";
                var rpj = PhotonNetwork.CurrentRoom?.CustomProperties;
                bool ffRoom = rpj != null && rpj.ContainsKey("cr_ff");
                if (Plugin.Pending2v2Slot >= 0 && !ffRoom && !rn.StartsWith("team_"))
                    Plugin.ClearPending2v2Slot();
                if (Plugin.PendingOvtSlot >= 0 && !rn.StartsWith("ovt_"))
                    Plugin.ClearPendingOvtSlot();
                if (Plugin.PendingFfaSlot >= 0 && !rn.StartsWith("ffa_"))
                    Plugin.ClearPendingFfaSlot();
            }
            catch { }
            // July 22 item 2: fresh room, stale leaver banner (and our own
            // left-for-ranked flag) must not carry over.
            try { CompetitiveUI.ClearLeaverBanner(); } catch { }
            try
            {
                var myProps = PhotonNetwork.LocalPlayer?.CustomProperties;
                if (myProps != null && myProps.ContainsKey("cr_lv_rk"))
                {
                    var clr = new ExitGames.Client.Photon.Hashtable();
                    clr["cr_lv_rk"] = "0";
                    PhotonNetwork.LocalPlayer.SetCustomProperties(clr);
                }
            }
            catch { }

            // Competitive-wide setup runs for any mod-issued ranked room
            // (1v1 ranked / 2v2 / sync tournament). Cosmetic late-prop reapply
            // helps every flow — opponents' custom colors / trails sometimes
            // miss the OnPlayerPropertiesUpdate event when their props were
            // already cached at room-join time. Face publish is also useful
            // as a fallback for the CardChoiceVisuals RPC timing race.
            bool isCompetitive = CompetitiveRoomDetect.IsCompetitiveRoom();
            if (isCompetitive)
            {
                try { FacePublisher.PublishLocal(); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[POPUP] Face publish hook error: {ex.Message}"); }

                if (Plugin.Instance != null)
                {
                    Plugin.Instance.StartCoroutine(RepeatedCompetitiveCosmeticReapply());
                }
            }

            // Everything below is 2v2-specific: GM_ArmsRace late-joiner
            // activation, LoadingScreen clear, force-StartGame fallback,
            // 4-player card bars, assembly state poll. None of these
            // matter for 1v1 (vanilla path handles it) or for tournaments
            // (sync tournaments are 1v1-shaped).
            if (!Diag2v2.IsActive()) return;
            try { Plugin.Log.LogInfo($"[2v2-DIAG] JoinedRoom: {Diag2v2.DescribeRoom()} masterClient={(PhotonNetwork.LocalPlayer?.IsMasterClient ?? false)}"); }
            catch { }

            // Activate GM_ArmsRace.gameObject ASAP (in the same Photon callback,
            // BEFORE remote-player Photon Instantiations fire Player.Start). In
            // vanilla, NetworkConnectionHandler.OnPlayerEnteredRoom fires
            // RPCA_FoundGame (RpcTarget.All, NOT AllBuffered) when
            // PlayerList.Length == MAX_PLAYERS (vanilla const = 2). That RPC is
            // the *only* path that calls LoadingScreen.StopLoading() →
            // gameMode.SetActive(true) → GM_ArmsRace activated. In a 4-player
            // room, the master fires the RPC the moment player #2 joins; players
            // 3 and 4 (joining later) miss it forever. So their GM_ArmsRace stays
            // inactive → instance is null → NCH.Update's untilTryOtherRegionCounter
            // timer (gated on !GM_ArmsRace.instance) ticks → PlayOnBestActiveRegion
            // → LeaveRoom. Plus PlayerJoined never subscribes to PlayerManager's
            // events, so StartGame never fires either. Idempotent for early joiners
            // (vanilla activates first, our SetActive is a no-op).
            try
            {
                var gm = UnityEngine.Object.FindObjectOfType<GM_ArmsRace>(true);
                if (gm != null && !gm.gameObject.activeInHierarchy)
                {
                    gm.gameObject.SetActive(true);
                    Plugin.Log.LogInfo("[2v2] Force-activated GM_ArmsRace.gameObject (vanilla path missed late joiner)");
                }
            }
            catch (Exception ex) { Plugin.Log.LogError($"[2v2] GM_ArmsRace activate failed: {ex.Message}"); }

            // Clear LoadingScreen state so the giant "Searching" overlay disappears
            // for late joiners. RPCA_FoundGame normally calls LoadingScreen.StopLoading
            // (which sets m_isLoading=false + stops the searching particle systems +
            // hides the cancel text) but late joiners miss that RPC. Do it manually.
            try
            {
                var ls = LoadingScreen.instance;
                if (ls != null)
                {
                    try { ls.searchingSystem?.Stop(); } catch { }
                    try { ls.matchFoundSystem?.Stop(); } catch { }
                    if (ls.playerNamesSystem != null)
                        foreach (var pns in ls.playerNamesSystem)
                            try { pns?.Stop(); } catch { }
                    try { if (ls.m_cancelText != null) ls.m_cancelText.SetActive(false); } catch { }
                    var fIsLoading = typeof(LoadingScreen).GetField("m_isLoading",
                        BindingFlags.NonPublic | BindingFlags.Instance);
                    fIsLoading?.SetValue(ls, false);
                    Plugin.Log.LogInfo("[2v2] Cleared LoadingScreen searching overlay (late joiner)");
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] LoadingScreen clear failed: {ex.Message}"); }

            // Kick off a fallback that manually invokes GM_ArmsRace.StartGame
            // once all 4 players are spawned. Belt-and-suspenders: if any
            // Player.Start fires BEFORE our SetActive lands (race), GM_ArmsRace
            // wouldn't have subscribed PlayerJoined yet for that player and the
            // count won't reach 4 organically.
            if (Plugin.Instance != null)
            {
                Plugin.Instance.StartCoroutine(Force2v2StartGameWhenReady());
                Plugin.Instance.StartCoroutine(Setup4PlayerCardBarsWhenReady());
                Plugin.Instance.StartCoroutine(PollAssemblyStateLoop());
            }
        }

        /// <summary>Poll /team/series/{id}/state every 2s for the first ~20s
        /// after joining a cr_ff room. THE ONLY PERMITTED CALLER of the mutating
        /// route (ApiClient.PollTeamSeriesStateAssemblyOnly) — everything else
        /// reads series status through the read-only route.
        ///
        /// <para>The server cancels the series when the row has been issued for
        /// more than 180 SECONDS (main.py `_ASSEMBLY_DEADLINE_SECONDS` on
        /// production 0cc7f75) with fewer than 4 of 4 spawn-confirms and no
        /// live-game evidence. This comment said 15 seconds for months; 15 s is
        /// not a bound this loop or the server has ever had, and the number
        /// mattered because it made the loop look like the thing that outlives
        /// the deadline when in fact the opposite is true: 3 s + 22 s of loop
        /// life is entirely inside 180 s, which is exactly why this caller
        /// cannot reach the cancel arm. The loop's duration bounds only the
        /// loop; it does not bound the ROW's age, which is measured from
        /// `room_issued_at` on the server and can already be hours old on the
        /// first read after a bug-245 resume relock.</para>
        ///
        /// <para>When we see status='canceled' with reason 'assembly_timeout',
        /// show a notification and leave the room — saves the remaining clients
        /// from sitting on the ready screen until our 30s force-StartGame
        /// timeout.</para></summary>
        private static System.Collections.IEnumerator PollAssemblyStateLoop()
        {
            yield return new WaitForSeconds(3f);
            float deadline = Time.realtimeSinceStartup + 22f;
            while (Time.realtimeSinceStartup < deadline)
            {
                if (Plugin.Pending2v2Slot < 0) yield break;
                if (!PhotonNetwork.InRoom) yield break;
                string sid = ApiClient.ActiveTeamSeriesId;
                if (string.IsNullOrEmpty(sid)) yield break;

                bool gotResponse = false;
                ApiClient.PollTeamSeriesStateAssemblyOnly(sid, (status, reason, conf) =>
                {
                    gotResponse = true;
                    if (status == "canceled" && reason == "assembly_timeout")
                    {
                        Plugin.Log.LogWarning($"[2v2] Server canceled series (assembly_timeout, {conf}/4 confirmed) — leaving room");
                        try
                        {
                            CompetitiveUI.ShowNotification(
                                $"Match couldn't assemble — only {conf} of 4 connected. Returning to menu.",
                                new Color(1f, 0.55f, 0.2f), 6f);
                        }
                        catch { }
                        try
                        {
                            Plugin.ClearPending2v2Slot();
                            if (PhotonNetwork.InRoom) PhotonNetwork.LeaveRoom();
                        }
                        catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] LeaveRoom on assembly cancel failed: {ex.Message}"); }
                    }
                    else if (status == "active" && conf >= 4)
                    {
                        // All 4 confirmed — assembly succeeded, no need to keep polling.
                    }
                });
                // Wait for response or timeout, then sleep before next poll.
                float waitUntil = Time.realtimeSinceStartup + 1.5f;
                while (!gotResponse && Time.realtimeSinceStartup < waitUntil) yield return null;
                // Codex r2 f8: the LastSeriesState* globals survive across
                // series, so a failed FIRST poll of a new series used to let
                // the PREVIOUS series' "active/4" terminate this loop
                // permanently — that seat then never learned its colour stamp
                // or an assembly cancel. Trust the cache only when it names
                // THIS series (a late old-series callback still overwrites
                // the value fields — the id compare is the whole guard).
                if (ApiClient.LastSeriesStateForId == sid)
                {
                    // If status is 'canceled' or assembly succeeded we can stop early.
                    if (ApiClient.LastSeriesStateStatus == "canceled") yield break;
                    if (ApiClient.LastSeriesStateStatus == "active" && ApiClient.LastSeriesStateConfirmations >= 4)
                        yield break;
                }
                yield return new WaitForSeconds(2f);
            }
        }

        /// <summary>Aggressively re-apply PlayerColorCosmetic AND TrailCosmetic for
        /// every non-local actor in the room over the first ~12 seconds after
        /// joining ANY mod-issued competitive room (1v1 ranked, 2v2, sync
        /// tournament). Photon's `OnPlayerPropertiesUpdate` callback fires on PROP
        /// UPDATES only — but late joiners receive the room's existing player prop
        /// state without an update event, so cosmetic apply paths are never
        /// triggered for them. Result: some clients see opponents' custom body
        /// colors as "white" (no tint applied because cr_pcolor_color was empty
        /// when the initial DelayedApplyAll ran), and trails simply don't appear.
        /// Polling re-apply catches the late arrivals AND nudges the PCOLOR
        /// animation tick into existence for animated SKUs. Originally added for
        /// 2v2 but generalized to all competitive paths in v1.25.14.</summary>
        private static System.Collections.IEnumerator RepeatedCompetitiveCosmeticReapply()
        {
            // Wait for the spawned player GameObjects to settle.
            yield return new WaitForSeconds(2f);
            float deadline = Time.realtimeSinceStartup + 12f;
            while (Time.realtimeSinceStartup < deadline)
            {
                if (!CompetitiveRoomDetect.IsCompetitiveRoom()) yield break;
                if (!PhotonNetwork.InRoom) yield break;
                try
                {
                    var list = RoomActors.ActiveFighters();   // census: only fighters carry body cosmetics
                    if (list != null)
                    {
                        foreach (var pp in list)
                        {
                            if (pp == null) continue;
                            if (PhotonNetwork.LocalPlayer != null && pp.ActorNumber == PhotonNetwork.LocalPlayer.ActorNumber) continue;
                            PlayerColorCosmetic.ReapplyForActor(pp.ActorNumber);
                            TrailCosmetic.ReattachForActor(pp.ActorNumber);
                            try { PlayerEffectCosmetic.ReapplyForActor(pp.ActorNumber); } catch { }
                        }
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[POPUP] cosmetic reapply tick error: {ex.Message}"); }
                yield return new WaitForSeconds(2f);
            }
        }

        /// <summary>Extend CardBarHandler.cardBars to length 4 in cr_ff rooms so
        /// each of the 4 players gets their own card-pick bar. Vanilla prefab is
        /// 1v1-shaped (2 CardBars: cardBars[0]=team 0/left, cardBars[1]=team 1/right).
        /// CardBarHandler.AddCard(int teamId, ...) at vanilla call site receives
        /// PlayerID, so PlayerID 2 and 3 hit IndexOutOfRange and their picks
        /// vanish. Strategy: try includeInactive children first (in case the
        /// prefab actually has 4 slots that 1v1 mode hides); else clone bars
        /// 0 and 1 with a vertical offset so all 4 are visible.</summary>
        private static System.Collections.IEnumerator Setup4PlayerCardBarsWhenReady()
        {
            float deadline = Time.realtimeSinceStartup + 15f;
            while (Time.realtimeSinceStartup < deadline)
            {
                // FFA doesn't extend bars — up to 10 stacked bars is unusable.
                // FfaMode's CardBarHandler.AddCard guard renders only the local
                // player's own bar; the hold-Tab board is the everyone view.
                if (Diag2v2.IsFfa()) yield break;
                // 1v2 needs this too: pid 2 (duo_b) overflows the vanilla
                // 2-slot cardBars array exactly like 2v2's pids 2/3. Extending
                // to 4 covers both modes (the 4th bar just stays unused in ovt).
                // Bug 243: SPECTATOR seats have no pending slot but render the
                // same PlayerID-indexed bars — without the extension, pids 2/3
                // (team 2) index out of range and every spectator saw only one
                // team's cards. The mode checks above/below all read in-room
                // identity (#149), so they work on a spectator seat.
                bool spectatorSeat = false;
                try { spectatorSeat = RoomActors.LocalIsSpectator; } catch { }
                if (Diag2v2.PendingSlot() < 0 && !spectatorSeat) yield break;
                if (!PhotonNetwork.InRoom) yield break;
                var cbh = CardBarHandler.instance;
                if (cbh == null || cbh.cardBars == null || cbh.cardBars.Length < 2)
                {
                    yield return new WaitForSeconds(0.5f);
                    continue;
                }

                // Already extended for this mode? bail (3 bars cover 1v2's
                // pids 0-2; 4 cover 2v2's 0-3).
                if (cbh.cardBars.Length >= (Diag2v2.IsOvt() ? 3 : 4))
                {
                    Plugin.Log.LogInfo($"[2v2] CardBars already {cbh.cardBars.Length} — no extension needed");
                    yield break;
                }

                try
                {
                    // Probe the prefab tree for any inactive CardBars first — vanilla
                    // 4-player local mode might have 4 in the hierarchy with 2 hidden.
                    var allInTree = cbh.GetComponentsInChildren<CardBar>(true);
                    if (allInTree != null && allInTree.Length >= 4)
                    {
                        foreach (var b in allInTree)
                            if (b != null && !b.gameObject.activeSelf) b.gameObject.SetActive(true);
                        cbh.cardBars = allInTree;
                        Plugin.Log.LogInfo($"[2v2] CardBars: found {allInTree.Length} in tree (incl. inactive), activated all");
                        yield break;
                    }

                    // Prefab only has 2 — clone with a vertical offset.
                    var bar0 = cbh.cardBars[0];
                    var bar1 = cbh.cardBars[1];
                    if (bar0 == null || bar1 == null)
                    {
                        Plugin.Log.LogWarning("[2v2] CardBars: original bar0/bar1 is null, skipping extension");
                        yield break;
                    }

                    // The array is indexed by PlayerID at vanilla's AddCard call
                    // site, so its ORDER must mirror the mode's slot→team map.
                    // 1v2 (pid 0 = solo/left, pids 1,2 = duo/right): one clone of
                    // the RIGHT bar — [bar0, bar1, clone1]. The 2v2-shaped order
                    // would put duo_a's (pid 1) cards in a left-side clone under
                    // the solo's bar, misreading as "solo + A vs B".
                    if (Diag2v2.IsOvt())
                    {
                        var cloneObj = UnityEngine.Object.Instantiate(bar1.gameObject, bar1.transform.parent);
                        cloneObj.name = bar1.gameObject.name + "_1v2_duoB";
                        OffsetBar(cloneObj.transform, new Vector2(0f, -180f));
                        var cloneCB = cloneObj.GetComponent<CardBar>();
                        if (cloneCB == null)
                        {
                            Plugin.Log.LogWarning("[1v2] CardBars: clone missing CardBar component");
                            yield break;
                        }
                        cbh.cardBars = new CardBar[] { bar0, bar1, cloneCB };
                        Plugin.Log.LogInfo("[1v2] CardBars: extended to 3 entries [solo_left, duoA_right, duoB_right_low]");
                        yield break;
                    }

                    var clone0Obj = UnityEngine.Object.Instantiate(bar0.gameObject, bar0.transform.parent);
                    var clone1Obj = UnityEngine.Object.Instantiate(bar1.gameObject, bar1.transform.parent);
                    clone0Obj.name = bar0.gameObject.name + "_2v2_p1";
                    clone1Obj.name = bar1.gameObject.name + "_2v2_p3";

                    // Offset clones vertically so they don't overlap originals.
                    // ROUNDS' bars use RectTransform anchored to top corners.
                    OffsetBar(clone0Obj.transform, new Vector2(0f, -180f));
                    OffsetBar(clone1Obj.transform, new Vector2(0f, -180f));

                    var clone0CB = clone0Obj.GetComponent<CardBar>();
                    var clone1CB = clone1Obj.GetComponent<CardBar>();
                    if (clone0CB == null || clone1CB == null)
                    {
                        Plugin.Log.LogWarning("[2v2] CardBars: clone missing CardBar component");
                        yield break;
                    }

                    cbh.cardBars = new CardBar[] { bar0, clone0CB, bar1, clone1CB };
                    Plugin.Log.LogInfo("[2v2] CardBars: cloned to 4 entries [team0_p0, team0_p1, team1_p2, team1_p3]");
                }
                catch (Exception ex)
                {
                    Plugin.Log.LogError($"[2v2] CardBar extension failed: {ex.Message}");
                }
                yield break;
            }
            Plugin.Log.LogWarning("[2v2] CardBar setup timed out — CardBarHandler.instance never appeared");
        }

        private static void OffsetBar(Transform t, Vector2 offset)
        {
            var rt = t as RectTransform;
            if (rt != null) rt.anchoredPosition += offset;
            else t.localPosition += new Vector3(offset.x, offset.y, 0f);
        }

        private static System.Collections.IEnumerator Force2v2StartGameWhenReady()
        {
            float deadline = Time.realtimeSinceStartup + 30f;
            while (Time.realtimeSinceStartup < deadline)
            {
                if (Diag2v2.PendingSlot() < 0) yield break;
                if (!PhotonNetwork.InRoom) yield break;
                // Vanilla path took over and the game is rolling — exit success.
                // Without this, the coroutine loops until deadline and emits a
                // misleading "never reached N spawned players" warning even
                // when the match is mid-play.
                try { if (GameManager.instance != null && GameManager.instance.isPlaying) yield break; } catch { }
                int need = Diag2v2.PlayersNeeded();   // 3 in ovt_, 4 in cr_ff
                var gm = GM_ArmsRace.instance;
                if (gm != null && gm.gameObject.activeInHierarchy && PlayerManager.instance != null)
                {
                    int counted = 0;
                    foreach (var p in PlayerManager.instance.players) if (p != null) counted++;
                    if (counted >= need)
                    {
                        Plugin.Log.LogInfo($"[2v2] Force-invoking GM_ArmsRace.StartGame (counted={counted}/{need})");
                        try { gm.StartGame(); }
                        catch (Exception ex) { Plugin.Log.LogError($"[2v2] StartGame invoke failed: {ex.Message}"); }
                        yield break;
                    }
                }
                yield return new WaitForSeconds(0.5f);
            }

            // ── Aug 6, bug #167: don't give up SILENTLY ──────────────────
            // This warning used to be the whole handling. Root cause from
            // Sid's Aug-6 log: the FFA lobby locked with a roster of 5 but
            // only 4 ever reached the Photon room (one player never
            // connected), so `counted >= need` was never true, the loop hit
            // its deadline, logged this line, and stopped. Nothing recovered
            // and nothing on screen explained it, so from a player's seat it
            // is indistinguishable from the old press-jump freeze.
            //
            // SCOPE, deliberately cut after Codex round 1 (CRITICAL 2).
            // The first version of this also force-STARTED the match with
            // whoever had arrived. That is not a safe thing to do from here
            // and the review was right to kill it:
            //   * this deadline is LOCAL, so each replica would fire at a
            //     different wall-clock moment and start the game at a
            //     different time;
            //   * StartGame() invoked locally is not a networked decision —
            //     there is no agreement that the game began;
            //   * the room stays open, so the missing player can still walk
            //     in mid-match; and
            //   * the report path cannot represent a member who never
            //     arrived at all, so a permanently absent player yields a
            //     short roster and a server rejection — no rating, no XP, no
            //     gold for anyone.
            // Starting a real ranked FFA on four independent guesses is
            // strictly worse than not starting it (#280's ship criterion:
            // the failure mode must be no worse than what it replaces).
            //
            // What ships is the half that actually addresses the report:
            // TELL THEM. A proper partial-start needs a master-authoritative
            // decision plus a server-side absent-member report path, which is
            // its own piece of work.
            int present = 0;
            try
            {
                if (PlayerManager.instance != null)
                    foreach (var p in PlayerManager.instance.players) if (p != null) present++;
            }
            catch { }
            int wanted = Diag2v2.PlayersNeeded();
            Plugin.Log.LogWarning($"[2v2] Force-StartGame timed out — never reached {wanted} spawned players (present={present})");
            // V11 item 3: while the assembly's suppression lease holds, the
            // one-shot toast is owed (shown when the lease ends), never dropped.
            bool owe = FfaAssembly.SuppressGuardToast;
            JoinTimeline.Step("guard_timeout", "present=" + present + " wanted=" + wanted + " toast=" + (owe ? "owed" : "shown"));
            if (owe)
            {
                FfaAssembly.OweGuardToast(present, wanted);
                yield break;
            }
            ShowGuardToast(present, wanted);
        }

        /// <summary>The guard's one-shot toast; V11 item 3 also shows it when
        /// an owed toast's suppression lease ends (FfaAssembly).</summary>
        internal static void ShowGuardToast(int present, int wanted)
        {
            try
            {
                // Critical: terminal one-shot instruction — this coroutine
                // ends here with no retry and no automatic exit, so a dropped
                // cue leaves the player stalled in the room with no recovery
                // advice (Aug 12 review r4 find 1).
                CompetitiveUI.ShowNotificationCritical(
                    I18n.TrF("Match could not start — only {0} of {1} players connected. Leave to the menu to requeue.", present, wanted),
                    new Color(1f, 0.5f, 0.3f), 12f);
            }
            catch { }
        }
        public void OnJoinRoomFailed(short returnCode, string message)
        {
            // Spectator join refused (room gone / full / expired grant):
            // clean up and return to menu — no room event ever occurred.
            try { SpectatorJoiner.OnJoinRoomFailed(returnCode, message); } catch { }
            if (Diag2v2.PendingSlot() < 0) return;
            Plugin.Log.LogWarning($"[2v2-DIAG] JoinRoomFailed: code={returnCode} msg={message}");
            JoinTimeline.Step("join_failed", "code=" + returnCode);
            if (QueueRoomJoiner.JoinGate)
            {
                try { FfaAssembly.PostFailed("join", returnCode); } catch { }
                try { QueueRoomJoiner.Instance?.EndAttemptNow("join_failed"); } catch { }
            }
        }
        public void OnJoinRandomFailed(short returnCode, string message) { }
        public void OnLeftRoom()
        {
            // Bug 392 item B: a silence notice belongs to the room it was
            // raised in. On a clean leave the sample loop stops without ever
            // seeing a recovered sample, so the notice would sit in the MENU
            // until its hold horizon expired — a warning about a match this
            // seat is no longer in. The horizon bounds that to seconds; this
            // makes it none. The cause store is NOT cleared here: the exit
            // hooks read it immediately after a disconnect-driven leave, and
            // the join edge plus the validity window are what bound it.
            try { TransportExit.ClearSilence(); } catch { }
            // Release B §1: the head-to-head line dies with the room — first
            // statement (same reason as OnDisconnected). Idempotent.
            try { H2HSummary.Invalidate(); } catch { }
            try { GameStateWatcher.ClearSessionUuid(); } catch { }   // Sept 6 item c: the id dies with the room
            try { SawTargetSync.ResetForRoomChange(); } catch { }    // and so does its verdict line (see OnJoinedRoom)
            // ...and the 2v2 DC fallback watch, which is a fact of ONE room and
            // one series: a watch carried across a room edge would be waiting on an
            // actor number that now names somebody else.
            try { DcReportSync.ResetForRoomChange(); } catch { }
            try { CardDrawEvidence.FreezeRoomFacts(); } catch { }     // the card record's room facts, before the reset (CD-M2)
            try { RoomRules.ResetLatched(); } catch { }              // room rules die with the room (§5.2)
            try { VanillaCardSequence.OnRoomLeft(); } catch { }      // and the vanilla-mode card sequence with them (§6)
            // Item 19 edge E6: never inside an InRoom test - the InRoom poll turns
            // false during Leaving, before this callback. The census reads it,
            // and a confirmed no-room outranks a still-live manager (fix pass 1, H9).
            AvatarDefaults.Evaluate("E6-left");
            // A teardown window is bound to the room it was opened in. Without
            // this a seat that leaves between the round call-in and the call-in
            // of new players carries the open window across the room boundary
            // and folds the next room's first frames into it (review r9).
            try { SpectatorTeardownProbe.CloseWindow("room-left"); } catch { }
            // Bug #269: the map-scale publish ticket must die on the RELIABLE
            // leave edge, not only through FfaMode's room poll — a leave and a
            // fast rejoin to a same-named recreated room can land between poll
            // samples, and the rejoin resets actor numbering so the old ticket
            // would pass every identity check. First statement, before any of
            // the branches below can return.
            try { FfaMapScale.OnRoomLeft(); } catch { }
            // Flush the active/aborted game and room totals before role/session
            // state is cleared. Do not use the InRoom poll here: it turns false
            // during Leaving, before queued receive work and this callback.
            try { NetworkReplicaDiagnostics.OnRoomLeft(); } catch { }
            // Esc-menu leave confirm: callback-bound disarm ATTEMPTS to
            // restore the vanilla wiring on the ACTUAL room exit (it catches
            // restore failure; the next successful Arm repairs that button).
            // The poll's Left-room branch is the lossy backup.
            try { EscMenuLeaveGuard.Disarm(); } catch { }
            try { EscLeaveRow.OnRoomLeft(); } catch { }
            // Spectator room exit observed — the point where the session's
            // statics are actually dropped (#249: clear local state in the
            // response/observation handler, never optimistically before).
            try
            {
                if (SpectatorSession.IsLocalSpectator)
                {
                    SpectatorSession.EndSession("left room");
                    SpectatorSync.OnLeftSpectatorRoom();
                }
            }
            catch { }
            // Dance emotes die with the room (round-2 review B-low: active
            // poses and receive throttles are actor-number-keyed, and actor
            // numbers alias across room incarnations).
            try { DanceEmotes.OnRoomLeft(); } catch { }
            // Role/roster caches die with the room, on every client.
            try { RoomActors.Reset(); } catch { }
            try { SpectatorSync.MasterResetSpectatorState(); } catch { }
            // Callback-bound edge reset (Aug 10 r2 find 8).
            try { GameStateWatcher.ResetSpectateAttestEdges(alsoRoomTally: false); } catch { }
            // Per-sitting diagnostic budgets refresh on the RELIABLE exit
            // edge (bug-216/217 review r4: the poll-detected exit can miss a
            // leave+rejoin that lands between samples; this callback cannot).
            // The poll's Left-room branch keeps a lossy backup copy.
            try { VanillaFixSupport.ResetDiag(StaleProjectileSweepPatch.DiagKey); } catch { }
            try { VanillaFixSupport.ResetDiag(RoundSoundSweep.DiagKey); } catch { }
            // #379: same per-sitting budgets, same reliable edge — and the
            // gate's log dedup key goes with them, so the next room states its
            // verdict instead of inheriting the previous room's line.
            try { VanillaFixSupport.ResetDiag(WeaponCooldownReset.DiagKey); } catch { }
            try { VanillaFixSupport.ResetDiag(WeaponCooldownReset.PhoenixDiagKey); } catch { }
            try { WeaponCooldownReset.ResetForRoomChange(); } catch { }
            // A ghost loop at the MENU is the most audible variant of the
            // sound leak — sweep once on the reliable exit edge (Aug 22).
            try { RoundSoundSweep.Schedule("room-leave"); } catch { }
            try { SpawnOnImpactFieldDiagPatch.ResetBudgets(); } catch { }
            // Tournament banner dies with the room on the reliable edge too
            // (Codex tournament r1 find 5 — the polled exit is the lossy
            // backup), and the incarnation bump retires every in-flight
            // preflight from the room we just left (r2 find 2 — a later
            // same-CODE room must not receive them).
            try { ApiClient.OnRoomLeftReliableEdge(); } catch { }
            try { GameStateWatcher.ClearTournamentContext(); } catch { }
            // r3 find 3: the series id is room-bound state, and clearing it on
            // the RELIABLE edge closes the fast same-code leave/rejoin where a
            // stale id suppressed the new room's preflight and posted the new
            // game's live points into the old pairing. The polled exit clears
            // it too (GameStateWatcher's Left-room branch, which #347's
            // documented casual→ranked flow relies on). That clear is now part
            // of OnRoomLeftReliableEdge above, with the counter bumps it has to
            // be ordered against, rather than a second statement here that
            // could be dropped on its own. Menu-time queue-staged ids are
            // untouched: no room exit fires for them, same as today.
            // Codex r5 f3: the card-bar tint bookkeeping + the owned outline
            // materials die with the room too — Reset() previously had NO
            // caller, so the flush the r4 cap depends on never ran and a
            // filled cache stayed capped for the rest of the process.
            try { CardBarTeamColor.Reset(); } catch { }
            // Automatic post-match log upload (item a). On the RELIABLE edge,
            // not the room-state poll: the poll turns false during Leaving and
            // cannot see a leave+rejoin that lands between two samples. It sits
            // ABOVE the Diag2v2 early return below, which would otherwise skip
            // it on every seat that has no pending 2v2 slot — i.e. almost all
            // of them. Off unless the player opted in; it clears its own
            // room-bound snapshot on every path, including the refusals.
            try { AutoLogUpload.OnRoomLeft(); } catch { }
            // (A room-leave flush of the #308 birth tally was tried here and
            // REMOVED in review r3 find 3: it neither reset nor marked the tally,
            // so leaving room A and joining room B emitted the same numbers twice
            // and broke the "once per generation" contract the summary depends on.
            // The tally is emitted by NewGeneration alone.)
            if (Diag2v2.PendingSlot() < 0) return;
            try { Plugin.Log.LogWarning($"[2v2-DIAG] LeftRoom (Photon callback) stack={Diag2v2.ShortStack()}"); }
            catch { }
        }
    }

    /// <summary>Vanilla `NetworkConnectionHandler.OnJoinedRoom` resets
    /// `PhotonNetwork.LocalPlayer.NickName` to the Steam persona name. That
    /// happens AFTER our pre-join `NametagStyler.PublishToPhoton()` (which
    /// set the styled rich-text version), so by the time remote clients see
    /// our actor's join broadcast they get the unstyled persona name. This
    /// Postfix re-publishes the styled NickName immediately after vanilla's
    /// reset, racing as little as possible against the remote actor-join
    /// broadcasts on other clients.</summary>
    [HarmonyPatch(typeof(NetworkConnectionHandler), "OnJoinedRoom")]
    class NetworkConnectionHandler_OnJoinedRoom_RestyleNick_Patch
    {
        static void Postfix()
        {
            try
            {
                if (!CompetitiveRoomDetect.IsCompetitiveRoom()) return;
                NametagStyler.PublishToPhoton();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[POPUP] OnJoinedRoom restyle failed: {ex.Message}"); }
        }
    }

    /// <summary>Patches NetworkRestart to log entry with caller context. Vanilla
    /// flips m_restarting=true and bails on subsequent calls, so we only see the
    /// first trigger — but that's the one we want.</summary>
    [HarmonyPatch(typeof(NetworkConnectionHandler), "NetworkRestart")]
    class NetworkConnectionHandler_NetworkRestart_Diag_Patch
    {
        static void Prefix()
        {
            // UNGATED (learning #286's tracer gap): this used to early-return
            // outside CompetitiveRoomDetect.IsCompetitiveRoom(), which made the
            // tracer silent in room-code rooms — exactly where bug 228's
            // post-match room deaths needed it. The FIRST call per restart is
            // the one that names the trigger; while m_restarting is already
            // true, vanilla bails internally but only AFTER this prefix runs —
            // and paths like NetworkConnectionHandler.Update can re-call every
            // frame during a conflicted join, so a full stack capture here
            // would burn ~60 warning allocations/sec (Codex tournament r1
            // find 11). Return BEFORE the stack capture on repeat calls.
            try
            {
                var nch = NetworkConnectionHandler.instance;
                if (nch != null && nch.m_restarting) return;
                string restartStack = Diag2v2.ShortStack();
                Plugin.Log.LogWarning($"[NCH-DIAG] NetworkRestart() entered {Diag2v2.DescribeRoom()} stack={restartStack}");
                int cut = restartStack.IndexOf(" <- ", StringComparison.Ordinal);
                JoinTimeline.Step("restart", "caller=" + (cut >= 0 ? restartStack.Substring(0, cut) : restartStack));
            }
            catch { }
        }
    }

    /// <summary>Patches PhotonNetwork.LeaveRoom to log the caller. Catches any
    /// non-vanilla code path that yanks us out of the room.</summary>
    [HarmonyPatch(typeof(PhotonNetwork), "LeaveRoom", new Type[] { typeof(bool) })]
    class PhotonNetwork_LeaveRoom_Diag_Patch
    {
        static void Prefix(bool becomeInactive)
        {
            // UNGATED, same reasoning as the NetworkRestart tracer above
            // (#286's tracer gap, bug 228): LeaveRoom fires a handful of times
            // per session — room exits are user/flow events, never a burst
            // path — and the room-code rooms the old IsCompetitiveRoom gate
            // silenced are precisely where the post-match death forensics were
            // needed.
            try { Plugin.Log.LogWarning($"[NCH-DIAG] PhotonNetwork.LeaveRoom(becomeInactive={becomeInactive}) {Diag2v2.DescribeRoom()} stack={Diag2v2.ShortStack()}"); }
            catch { }
        }
    }

    /// <summary>Patch GM_ArmsRace.PlayerJoined to log every fire so we can see
    /// where the count gets stuck. Vanilla does:
    ///   if (num &lt; playersNeededToStart) return;
    ///   StartGame();
    /// — if `num` never reaches 4, StartGame never fires.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "PlayerJoined")]
    class GMArmsRace_PlayerJoined_Diag_Patch
    {
        static void Prefix(GM_ArmsRace __instance, global::Player player)
        {
            if (!Diag2v2.IsActive()) return;
            try
            {
                int num = 0;
                int total = 0;
                if (PlayerManager.instance != null && PlayerManager.instance.players != null)
                {
                    total = PlayerManager.instance.players.Count;
                    foreach (var p in PlayerManager.instance.players) if (p != null) num++;
                }
                int needed = __instance.playersNeededToStart;
                Plugin.Log.LogInfo($"[2v2-DIAG] GM_ArmsRace.PlayerJoined fired: counted={num} listSize={total} playersNeededToStart={needed}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2-DIAG] GM_ArmsRace.PlayerJoined log error: {ex.Message}"); }
        }
    }

    /// <summary>Log when GM_ArmsRace.StartGame fires — if all 4 join but this
    /// never triggers, the gating in PlayerJoined is the problem.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "StartGame")]
    class GMArmsRace_StartGame_Diag_Patch
    {
        static void Prefix()
        {
            if (!Diag2v2.IsActive()) return;
            try { Plugin.Log.LogInfo($"[2v2-DIAG] GM_ArmsRace.StartGame() fired {Diag2v2.DescribeRoom()}"); }
            catch { }
        }
    }

    /// <summary>Player.Start sets PlayerID/TeamID from custom properties. Log
    /// the values we see so we can confirm slots/teams arrive correctly on
    /// remote clients.</summary>
    [HarmonyPatch(typeof(global::Player), "Start")]
    class Player_Start_Diag_Patch
    {
        static void Postfix(global::Player __instance)
        {
            if (!Diag2v2.IsActive()) return;
            try
            {
                bool isLocal = false;
                int actor = -1;
                try { isLocal = __instance.data?.view?.IsMine ?? false; } catch { }
                try { actor = __instance.data?.view?.OwnerActorNr ?? -1; } catch { }
                Plugin.Log.LogInfo($"[2v2-DIAG] Player.Start: pid={__instance.PlayerID} team={__instance.TeamID} isLocal={isLocal} actor={actor}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2-DIAG] Player.Start log error: {ex.Message}"); }
        }
    }

    /// <summary>Bug #224: mode-agnostic local-face re-send for team_/ovt_
    /// rooms — learning #226's class, third instance. Vanilla sends each
    /// player's face exactly ONCE, via an UNBUFFERED RpcTarget.All fired
    /// from Player.Start's IsMine branch at spawn (decompiled Player.cs);
    /// any peer still mid-join drops it forever. Under the hosted-lobby
    /// flow the LAST joiner is the NORM, so they saw default faces on
    /// every earlier joiner for the whole sitting. FFA already re-sends at
    /// its own game start (FfaMode.ResyncLocalFace, bug #102) and a
    /// spectator entry already triggers a fighter re-send (playtest #169b)
    /// — this covers the two team modes whose game start is vanilla-driven,
    /// from two triggers: the local spawn (covers peers who were mid-join
    /// when vanilla's RPC fired) and every remote entrant (the earlier
    /// seats re-send for the late arrival). Idempotent: EquipFace just
    /// re-equips (#226). TrySendLocalFace is the SINGLE send
    /// implementation, shared by the FFA and spectator-entry paths too.</summary>
    internal static class FaceResync
    {
        // Coalescing (#98/#272-family bounding): a burst of triggers
        // (staggered joiners at room assembly) produces ONE send, and every
        // new trigger PUSHES the send out so the newest entrant still gets
        // a full settle window before the RPC. A fixed-delay coroutine per
        // trigger could fire 0.1s after a later entrant joined and lose the
        // exact mid-join race this exists to close.
        private const float SettleSeconds = 2.5f;
        private static bool pending;
        private static float dueAt;

        /// <summary>2v2/1v2 room? Name prefix, plus the cr_ff room prop for
        /// 2v2 (the same discriminator Diag2v2.IsActive uses — a cr_ff room
        /// is definitionally a 2v2 context whatever its name). ffa_ rooms
        /// are deliberately excluded: FfaMode.ResyncLocalFace owns those
        /// (task requirement — never double-cover the FFA resync).</summary>
        internal static bool InTeamOrOvtRoom()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return false;
                string rn = PhotonNetwork.CurrentRoom.Name ?? "";
                if (rn.StartsWith("team_") || rn.StartsWith("ovt_")) return true;
                var props = PhotonNetwork.CurrentRoom.CustomProperties;
                return props != null && props.ContainsKey("cr_ff");
            }
            catch { return false; }
        }

        /// <summary>Schedule a coalesced re-send. Safe to call from any
        /// trigger in any room — every guard lives here so the call sites
        /// stay one-liners.</summary>
        internal static void Schedule(string reason)
        {
            try
            {
                // Spectators publish no cosmetics (design §3.5) — and have
                // no IsMine Player to send from anyway (defense in depth).
                if (RoomActors.LocalIsSpectator) return;
                if (!InTeamOrOvtRoom()) return;
                if (Plugin.Instance == null) return;
                dueAt = Time.realtimeSinceStartup + SettleSeconds;
                if (pending) return;   // runner re-reads dueAt — the push above extends its wait
                pending = true;
                VanillaFixSupport.DiagLimited("face-resync-sched",
                    $"face resync scheduled ({reason})", 20);
                Plugin.Instance.StartCoroutine(Run());
            }
            catch { }
        }

        private static IEnumerator Run()
        {
            // Loop-on-dueAt rather than a fixed wait: Schedule pushes dueAt
            // forward on every trigger. No yield sits between the loop exit
            // and the pending reset, so a same-frame Schedule either
            // extends this loop or starts a fresh runner — never lost.
            while (Time.realtimeSinceStartup < dueAt) yield return null;
            pending = false;
            // Re-check after the wait: the coroutine is hosted on the
            // persistent Plugin.Instance, so the room can have changed (or
            // been left) underneath it.
            if (RoomActors.LocalIsSpectator || !InTeamOrOvtRoom()) yield break;
            TrySendLocalFace("FACE-RESYNC");
        }

        /// <summary>The shared send mechanics (one implementation for the
        /// FFA game-start, spectator-entry and team/ovt paths): resolve the
        /// local player by IsMine view, refuse the all-zero default face
        /// (FFA review find 13 — an account that never opened the character
        /// creator has an all-zero face, and re-sending that WIPES the
        /// stock face on every other screen; the cr_face publisher rejects
        /// the identical payload), then re-fire vanilla's own face RPC at
        /// the others. Custom cosmetic ids ride along — they resolve
        /// through the GetItem prefix on every client (#124). Returns
        /// false, silently, when the local player has not spawned yet —
        /// a later trigger covers that entrant.</summary>
        internal static bool TrySendLocalFace(string tag)
        {
            try
            {
                if (!PhotonNetwork.InRoom) return false;
                if (RoomActors.LocalIsSpectator) return false;   // §3.5, guarded at the source
                global::Player lp = null;
                var players = PlayerManager.instance?.players;
                if (players != null)
                    foreach (var pl in players)
                        if (pl != null && pl.gameObject != null && pl.data != null
                            && pl.data.view != null && pl.data.view.IsMine) { lp = pl; break; }
                if (lp == null) return false;
                var face = CharacterCreatorHandler.instance.selectedPlayerFaces[0];
                if (face.eyeID == 0 && face.mouthID == 0 && face.detailID == 0 && face.detail2ID == 0)
                {
                    VanillaFixSupport.DiagLimited("face-resync-zero",
                        $"[{tag}] face resync skipped — all-zero default face", 5);
                    return false;
                }
                lp.data.view.RPC("RPCA_SetFace", RpcTarget.Others,
                    face.eyeID, face.eyeOffset, face.mouthID, face.mouthOffset,
                    face.detailID, face.detailOffset, face.detail2ID, face.detail2Offset);
                Plugin.Log.LogInfo($"[{tag}] face resync sent (#226)");
                return true;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[{tag}] face resync: {ex.Message}");
                return false;
            }
        }
    }

    /// <summary>Publishes the local player's selected face to a Photon LocalPlayer
    /// custom property `cr_face` so that every client can apply any other
    /// player's face on the card-pick popup without depending on RPC timing.
    /// Vanilla's CardChoiceVisuals.Show fires `RPCA_SetFace` with `RpcTarget.All`
    /// only from the picker's client — in 2v2 with 4 sequential pickers, the RPC
    /// for picker N can arrive AFTER picker N+1's Show() has already torn down and
    /// re-rendered the visualizer locally, so remote clients see "yesterday's
    /// picker" or no face at all. A property has its own race, the other way
    /// round: a seat's copy of a remote carrier is the last update it received,
    /// which can belong to an earlier pick. So the popup never reads that copy
    /// (item 19 fix pass 3, H3): the picker BINDS the publish it makes at its
    /// own popup to that popup's pick (fix pass 4: the game and rounds every
    /// seat derives from the same events), and a remote seat applies a face or
    /// a clear only when it is bound to the pick of the popup it shows
    /// (PopupCarrierLedger, through PopupCarriers).</summary>
    internal static class FacePublisher
    {
        public const string PROP_FACE = "cr_face";

        /// <summary>The one publish-or-clear helper behind all four callers
        /// (item 19 fix pass 1, H3). Every attempt ends in exactly one of three
        /// outcomes, decided by AvatarRules.CarrierAction: the current valid
        /// face is published; or the attempt reached a definitive "no valid
        /// face" (no face list, a null face, an all-zero face) and the carrier
        /// is CLEARED (once that write arrives, a remote seat's popup stops
        /// owing this face and vanilla's RPC stays in charge); or nothing is written (a
        /// spectator, no handler yet, no local player). A write reaches the
        /// local cache only on the server's echo, so it is not observable in
        /// the pass that made it: see the overload below (fix pass 2, H3).</summary>
        public static FaceCarrierAction PublishLocal() => PublishLocal(out _);

        /// <summary>The same attempt, also handing back the exact value it
        /// published (null when it cleared or kept the carrier). Fix pass 2,
        /// H3: PUN updates the local player's cached properties only on the
        /// server's echo, so a caller that needs its own face in the same pass
        /// uses this value and never rereads the cache. Fix pass 3, H3: forPick
        /// is the card-pick popup's own publish (the local picker's Show). Fix
        /// pass 4, H3: that one value is BOUND to the pick of the popup the
        /// picker shows (PopupCarriers.PickNow): a face carries the pick as a
        /// 13th field (PopupCarrierLedger.BoundFace), a clear is the tombstone
        /// "clear|" + the pick (PopupCarrierLedger.BoundClear). A remote seat
        /// applies either only to its popup of that same pick. When this seat
        /// has no pick identity (no game start seen in this room) the publish
        /// goes out unbound. Every other publish stays the 12 fields it always
        /// was, and a clear outside a pick still removes the key.</summary>
        public static FaceCarrierAction PublishLocal(out string published, bool forPick = false)
        {
            published = null;
            try
            {
                // Spectator: publishes NO cosmetic properties (design §3.5) —
                // guarded here at the source so no call site can leak one. No
                // reader consults a spectator's carrier (the popup applies only
                // the carrier of the picker it shows, and a spectator never
                // picks), so Keep leaves nothing readable.
                bool spectator = RoomActors.LocalIsSpectator;
                var cch = CharacterCreatorHandler.instance;
                bool listed = cch != null && cch.selectedPlayerFaces != null && cch.selectedPlayerFaces.Length > 0;
                var face = listed ? cch.selectedPlayerFaces[0] : null;
                var ids = face != null ? AvatarFaceIds.Of(face.eyeID, face.mouthID, face.detailID, face.detail2ID) : new AvatarFaceIds();
                var action = new AvatarRules().CarrierAction(spectator, cch != null, PhotonNetwork.LocalPlayer != null, listed, ids);
                if (action == FaceCarrierAction.Keep)
                {
                    if (spectator) return action;
                    Plugin.Log.LogInfo(cch == null
                        ? "[POPUP-DIAG] PublishLocal skipped: CharacterCreatorHandler.instance is null (game state not ready)"
                        : "[POPUP-DIAG] PublishLocal skipped: LocalPlayer is null");
                    return action;
                }
                // Fix pass 4 (H3): the card-pick popup's own publish is bound to
                // the pick that popup shows; null outside a pick, or when this
                // seat has no pick identity (the publish then goes out unbound).
                string pick = forPick ? PopupCarriers.PickNow() : null;
                if (forPick && pick == null)
                    Plugin.Log.LogInfo("[POPUP] card-pick publish unbound: this seat has seen no game start in this room, so no remote popup applies it");
                if (action == FaceCarrierAction.Clear)
                {
                    // No valid face to publish: selectedPlayerFaces empty, face[0]
                    // null, or a fully default face (all four item IDs zero).
                    // Accounts that never opened the character creator have an
                    // uninitialized face — publishing all-zeros causes
                    // CharacterCreatorItemEquipper.EquipFace to call Equip(null)
                    // on each slot, which destroys the visualizer's stock face
                    // entirely and renders a featureless body ("2 of 4 missing in
                    // card-pick phase", alts that never customized their face).
                    // Without a carrier, vanilla's RPCA_SetFace on the picker's
                    // client falls back to the local visualizer's saved face. The
                    // clear removes a carrier an earlier attempt published, which
                    // returning here used to leave in place for the popup. Fix
                    // pass 4 (H3): at a pick the clear is the tombstone bound to
                    // the popup's pick, so a remote popup of that pick stops
                    // owing a face at once; the key stays present until the next
                    // publish (the facing census skips the carrier key by name,
                    // AvatarRules.CarriesModSignature), and a reader that needs 12
                    // fields (a 1.40.3 seat) refuses it and applies nothing.
                    var clear = new ExitGames.Client.Photon.Hashtable();
                    if (pick == null) clear[PROP_FACE] = null;
                    else clear[PROP_FACE] = PopupCarrierLedger.BoundClear(pick);
                    PhotonNetwork.LocalPlayer.SetCustomProperties(clear);
                    Plugin.Log.LogInfo("[2v2] FacePublisher: cleared the face carrier ("
                        + (!listed ? "selectedPlayerFaces empty" : face == null ? "face[0] is null" : "face is all-zero defaults")
                        + (pick != null ? ", bound to " + pick : "") + " — let vanilla RPC handle it)");
                    return action;
                }

                string serialized = string.Join("|", new[] {
                    face.eyeID.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    face.eyeOffset.x.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.eyeOffset.y.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.mouthID.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    face.mouthOffset.x.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.mouthOffset.y.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.detailID.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    face.detailOffset.x.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.detailOffset.y.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.detail2ID.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    face.detail2Offset.x.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                    face.detail2Offset.y.ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
                });
                if (pick != null) serialized = PopupCarrierLedger.BoundFace(serialized, pick);
                var props = new ExitGames.Client.Photon.Hashtable();
                props[PROP_FACE] = serialized;
                PhotonNetwork.LocalPlayer.SetCustomProperties(props);
                Plugin.Log.LogInfo($"[2v2] Published local face to Photon: {serialized}");
                published = serialized;
                return FaceCarrierAction.Publish;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] Face publish failed: {ex.Message}"); return FaceCarrierAction.Keep; }
        }

        /// <summary>Equip a serialized face on the popup's visualizer. A null
        /// or empty value applies nothing (vanilla's RPC stays in charge).</summary>
        public static bool ApplySerialized(string s, int pickerActorNumber, GameObject visualizerRoot)
        {
            try
            {
                if (string.IsNullOrEmpty(s)) return false;
                var parts = s.Split('|');
                if (parts.Length < 12)
                {
                    Plugin.Log.LogInfo($"[POPUP-DIAG] Face apply skipped actor={pickerActorNumber}: cr_face has {parts.Length} parts (expected 12) — likely truncated");
                    return false;
                }
                var ic = System.Globalization.CultureInfo.InvariantCulture;
                int eyeID = int.Parse(parts[0], ic);
                float eOx = float.Parse(parts[1], ic), eOy = float.Parse(parts[2], ic);
                int mouthID = int.Parse(parts[3], ic);
                float mOx = float.Parse(parts[4], ic), mOy = float.Parse(parts[5], ic);
                int detailID = int.Parse(parts[6], ic);
                float dOx = float.Parse(parts[7], ic), dOy = float.Parse(parts[8], ic);
                int detail2ID = int.Parse(parts[9], ic);
                float d2Ox = float.Parse(parts[10], ic), d2Oy = float.Parse(parts[11], ic);
                // Skip all-zero faces (uninitialized accounts). Applying a
                // default face wipes the visualizer's stock face. Caller will
                // see ApplySerialized return false and won't log "applied".
                if (eyeID == 0 && mouthID == 0 && detailID == 0 && detail2ID == 0) return false;
                var face = PlayerFace.CreateFace(
                    eyeID, new Vector2(eOx, eOy),
                    mouthID, new Vector2(mOx, mOy),
                    detailID, new Vector2(dOx, dOy),
                    detail2ID, new Vector2(d2Ox, d2Oy)
                );
                var equipper = visualizerRoot?.GetComponentInChildren<CharacterCreatorItemEquipper>(true);
                if (equipper == null) return false;
                equipper.EquipFace(face);
                return true;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[2v2] Face apply failed: {ex.Message}");
                return false;
            }
        }
    }

    /// <summary>Item 19 fix pass 3 (H3, the remote arm), bound in fix pass 4:
    /// the Unity and Photon half of PopupCarrierLedger (AvatarDefaultRules.cs).
    /// The card-pick popup (CardChoiceVisuals_Show_Competitive_Patch) applies
    /// the picker's face from the cr_face carrier after vanilla's RPC-broadcast
    /// attempt, which has timing races in 2v2 (only the picker's client fires
    /// it; a remote seat can show the previous picker's face, or none, when the
    /// RPC lands after the next picker's Show re-instantiated the skin). The
    /// local picker applies the value it has just published (fix pass 2, H3).
    /// A remote picker's face is the value that picker published BOUND to the
    /// pick this popup shows (fix pass 4, H3: the pick identity PickNow, which
    /// every seat derives from the same two events, the game start it saw in
    /// the room and the rounds the master's RPCA_NextRound set): applied at
    /// Show when it has arrived, and on arrival when it has not; a value bound
    /// to another pick, or to none, is never applied. This class feeds the
    /// ledger from the places that move it (the DoStartGame prefix, the Show
    /// postfix, the property callback, the Hide postfix, the behaviour's tick),
    /// applies what it hands back, and logs each decision as [POPUP]. Every
    /// entry point runs on the main thread.</summary>
    internal static class PopupCarriers
    {
        private static readonly PopupCarrierLedger Ledger = new PopupCarrierLedger(new AvatarRules());

        private static object Room()
        {
            try { return PhotonNetwork.CurrentRoom; } catch { return null; }
        }

        private static double Now() => Time.realtimeSinceStartup;

        private static void Say()
        {
            string n = Ledger.Note;
            if (n != null) Plugin.Log.LogInfo("[POPUP] " + n);
        }

        /// <summary>The rounds completed in the current game on this seat
        /// (GM_ArmsRace.p1Rounds + p2Rounds: zeroed for a game start by a new
        /// GM or ResetMatch, and set on every seat by RPCA_NextRound before
        /// that round's picks), or -1 when there is no game to read.</summary>
        private static int Rounds()
        {
            try
            {
                var gm = GM_ArmsRace.instance;
                return gm != null ? gm.p1Rounds + gm.p2Rounds : -1;
            }
            catch { return -1; }
        }

        /// <summary>The identity of the pick a card-pick popup opening now
        /// shows (fix pass 4, H3): "pick" + the games this seat saw start in
        /// the room + "." + the rounds completed; null when this seat has none.
        /// The picker binds its card-pick publish to it (FacePublisher.PublishLocal)
        /// and a remote seat's popup of that pick derives the same value.</summary>
        internal static string PickNow()
        {
            string pick = Ledger.PopupPick(Room(), Rounds());
            Say();
            return pick;
        }

        /// <summary>GM_ArmsRace.DoStartGame on a fighter seat (the first game
        /// through StartGame, every same-room rematch through IDoRematch, #138).</summary>
        internal static void GameStarted()
        {
            Ledger.GameStarted(Room());
            Say();
        }

        /// <summary>The popup's remote arm (AvatarRules.PopupFace calls it for
        /// a remote picker only): the value that picker published bound to the
        /// pick this popup shows, or null while it has not arrived (the apply
        /// is owed) or when nothing can be applied.</summary>
        internal static string ForShow(int actor)
        {
            string pick = PickNow();
            string v = Ledger.Show(Room(), actor, pick, Now());
            Say();
            return v;
        }

        /// <summary>The Show postfix applied a value ForShow handed it.</summary>
        internal static void Applied(int actor, bool committed)
        {
            Ledger.Applied(actor, committed, Now());
            Say();
        }

        /// <summary>The popup moved to the local picker, or was hidden.</summary>
        internal static void Ended()
        {
            Ledger.EndSession(Room());
            Say();
        }

        /// <summary>OnPlayerPropertiesUpdate: a carrier update from a remote
        /// actor ARRIVED (a bound clear arrives as the tombstone, a removed key
        /// as null). The join snapshot never comes through here, so it is never
        /// taken for a pick's value. This is the one read of a carrier VALUE
        /// (fix pass 4, H3): the ledger applies it only through the binding
        /// check, AvatarRules.BoundToPopup.</summary>
        internal static void Arrived(Photon.Realtime.Player target, ExitGames.Client.Photon.Hashtable changed)
        {
            if (target == null || target.IsLocal || changed == null || !changed.ContainsKey(FacePublisher.PROP_FACE)) return;
            string v = Ledger.Arrived(Room(), target.ActorNumber, changed[FacePublisher.PROP_FACE] as string, PickNow(), Now());
            Say();
            if (v != null) ApplyNow(target.ActorNumber, v, "on arrival");
        }

        /// <summary>The behaviour's tick, every 15 frames: retries an owed
        /// apply whose value is held, and drops one past the bound.</summary>
        internal static void Tick()
        {
            if (Time.frameCount % 15 != 0) return;
            string v = Ledger.Tick(Room(), Now());
            Say();
            if (v != null) ApplyNow(Ledger.Shown, v, "on retry");
        }

        private static void ApplyNow(int actor, string value, string when)
        {
            var vis = CardChoiceVisuals.instance;
            bool ok = vis != null && FacePublisher.ApplySerialized(value, actor, vis.gameObject);
            Ledger.Applied(actor, ok, Now());
            Say();
            if (ok) Plugin.Log.LogInfo($"[POPUP] CardChoiceVisuals: applied picker face (the value its picker published bound to this pick, {when}) (actor={actor})");
        }
    }

    /// <summary>Re-tint the card-pick visualizer body to match the picker's
    /// actual team. Vanilla CardChoiceVisuals spawns a skin clone that displays
    /// fine in 1v1, but in 2v2 our PlayerSkinBank patch can't reach the visualizer
    /// because the body's color is baked at clone time from a path that runs
    /// before children spawn. User report: "Sid4 was on blue, his character
    /// color showed as orange at the card pick screen" while in-game body
    /// renders blue correctly. Fix: wait a couple frames for the visualizer
    /// hierarchy to populate, then walk SpriteRenderer + ParticleSystem and
    /// recolor anything that looks team-baseline (the wrong team's hue).</summary>
    internal static class CardPickBodyTinter
    {
        // Vanilla ROUNDS team colors. These match the in-game player body for
        // each team — used as both the "wrong-team baseline to detect" and
        // the "right-team color to apply" depending on which side we're on.
        // Read from PlayerSkinBank.instance.skins[] at first call so the values
        // track whatever ROUNDS ships rather than hardcoded hex.
        private static Color teamColor0 = new Color(0.95f, 0.45f, 0.32f); // orange-ish fallback
        private static Color teamColor1 = new Color(0.45f, 0.62f, 0.95f); // blue-ish fallback
        private static bool teamColorsResolved = false;

        // Public accessors so the skin-rebake guard (PlayerSkinHandlerInitRebakeGuard)
        // can compare a baked body against the real team colors.
        public static Color TeamColor0 { get { return teamColor0; } }
        public static Color TeamColor1 { get { return teamColor1; } }
        public static void EnsureTeamColors() { TryResolveTeamColors(); }

        private static void TryResolveTeamColors()
        {
            if (teamColorsResolved) return;
            try
            {
                // v1.28 fix: the OLD code reflected over PlayerSkinBank.skins[] entries
                // looking for the "most-saturated Color FIELD". But skins[] is a
                // PlayerSkinInstance[] whose team color lives at
                // .currentPlayerSkin.color (a NESTED object) — the top-level struct has
                // NO Color field, so the sniff found nothing and returned Color.white for
                // BOTH teams (logs: "t0=#FFFFFF t1=#FFFFFF"). The card-pick retint then
                // matched nothing (IsCloseHue vs white) and was a total no-op, so a body
                // that rendered the wrong team color never got corrected. Read the REAL
                // color via PlayerSkinBank.GetPlayerSkinColors(team).color through
                // reflection (no direct PlayerSkin type ref — all-reflection rule), with
                // the skins[].currentPlayerSkin.color path as the fallback.
                Color? c0 = ResolveTeamColor(0);
                Color? c1 = ResolveTeamColor(1);
                // Saturation floor: only accept a resolved color if it's actually
                // colored (not white/grey). Otherwise keep the sane hardcoded fallback
                // so the retint still has two distinct hues to work with.
                if (c0.HasValue && ColorSat(c0.Value) > 0.12f) teamColor0 = c0.Value;
                if (c1.HasValue && ColorSat(c1.Value) > 0.12f) teamColor1 = c1.Value;
                teamColorsResolved = true;
                Plugin.Log.LogInfo($"[CARDPICK-TINT] resolved team colors: t0={ColorHex(teamColor0)} t1={ColorHex(teamColor1)} (raw c0={(c0.HasValue?ColorHex(c0.Value):"null")} c1={(c1.HasValue?ColorHex(c1.Value):"null")})");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CARDPICK-TINT] resolve failed: {ex.Message}"); }
        }

        private static float ColorSat(Color c)
        {
            float mx = Math.Max(c.r, Math.Max(c.g, c.b));
            float mn = Math.Min(c.r, Math.Min(c.g, c.b));
            return mx <= 0.001f ? 0f : (mx - mn) / mx;
        }

        /// <summary>Resolve a team's real body color. Primary path:
        /// PlayerSkinBank.GetPlayerSkinColors(team) → PlayerSkin whose `.color` field
        /// is the team body color. Fallback: instance.skins[team].currentPlayerSkin.color.
        /// All reflection so we keep zero direct PlayerSkin/PlayerSkinBank type refs.</summary>
        private static Color? ResolveTeamColor(int team)
        {
            try
            {
                var bankType = typeof(PlayerSkinBank);
                // Static PlayerSkinBank.GetPlayerSkinColors(int) → PlayerSkin
                var mGet = bankType.GetMethod("GetPlayerSkinColors",
                    BindingFlags.Public | BindingFlags.Static);
                object skin = null;
                if (mGet != null)
                {
                    try { skin = mGet.Invoke(null, new object[] { team }); } catch { }
                }
                // Fallback: instance.skins[team].currentPlayerSkin
                if (skin == null)
                {
                    var bank = PlayerSkinBank.instance;
                    if (bank == null) return null;
                    var fSkins = bankType.GetField("skins",
                        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                    var arr = fSkins?.GetValue(bank) as System.Array;
                    if (arr == null || arr.Length <= team) return null;
                    var inst = arr.GetValue(team);
                    var fCur = inst?.GetType().GetField("currentPlayerSkin",
                        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                    skin = fCur?.GetValue(inst);
                }
                if (skin == null) return null;
                var fColor = skin.GetType().GetField("color",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (fColor == null || fColor.FieldType != typeof(Color)) return null;
                return (Color)fColor.GetValue(skin);
            }
            catch { return null; }
        }

        private static string ColorHex(Color c) =>
            $"#{(int)(c.r * 255):X2}{(int)(c.g * 255):X2}{(int)(c.b * 255):X2}";

        public static IEnumerator RetintAfterChildrenSpawn(GameObject visualizer, int pickerTeamID, int pickerID, int pickerActor = -1)
        {
            // NO position mutation here — ever. The clone lives under
            // CardChoiceVisuals' root, which vanilla scales to 33x when shown
            // (CurveAnimation animates it through arbitrary values), so ANY
            // localPosition offset gets multiplied by the parent's current scale:
            // the old (pickerID-1.5)*4 anti-stack spread put picker 0 at world
            // X=-198 and picker 1 at X=-66 on every solo pick — the "body
            // missing, cosmetics still show" bug (#58, proven in the 7/12 log:
            // 34/34 solo picks off-screen). The spread guarded against a
            // stacking scenario that cannot happen — vanilla destroys
            // currentSkin on every Show, so only ONE picker body exists at a
            // time and vanilla's own stage-center placement is correct for it.
            // Wait for vanilla's child-spawn pass, then only recolor in place.
            for (int i = 0; i < 10; i++)
            {
                if (visualizer == null) yield break;
                yield return null;
            }
            if (visualizer == null) yield break;

            TryResolveTeamColors();
            Color desired = (pickerTeamID == 1) ? teamColor1 : teamColor0;
            Color wrongTeam = (pickerTeamID == 1) ? teamColor0 : teamColor1;

            // v1.30 (#58 "wrong avatar"): if the picker has a CUSTOM body color
            // equipped (cr_pcolor_color Photon prop), that — not the vanilla team
            // hue — is what their body should read as. In that case both vanilla
            // team baselines count as "wrong" and get repainted to the custom color.
            bool hasCustom = false;
            try
            {
                // Honor the local "Show Player Colors" toggle exactly like the
                // in-match body pipeline (review r1 find 11: with the toggle
                // off, physical bodies render vanilla team colors — the pick
                // body must not read the custom prop and disagree).
                bool colorsHidden = Plugin.ShowPlayerColors != null && !Plugin.ShowPlayerColors.Value;
                if (pickerActor > 0 && !colorsHidden)
                {
                    foreach (var pl in RoomActors.ActiveFighters())   // census: a picker is always a fighter
                    {
                        if (pl == null || pl.ActorNumber != pickerActor) continue;
                        if (pl.CustomProperties != null && pl.CustomProperties.ContainsKey("cr_pcolor_color"))
                        {
                            string hex = pl.CustomProperties["cr_pcolor_color"] as string;
                            Color cc;
                            if (!string.IsNullOrEmpty(hex) && ColorUtility.TryParseHtmlString(hex, out cc))
                            {
                                desired = cc;
                                hasCustom = true;
                            }
                        }
                        break;
                    }
                }
            }
            catch { }

            int sprites = 0, particles = 0, skinFields = 0;
            try
            {
                Func<Color, bool> looksWrong = c =>
                    hasCustom ? (IsCloseHue(c, teamColor0) || IsCloseHue(c, teamColor1))
                              : IsCloseHue(c, wrongTeam);

                // 1) Replace SpriteRenderer colors that look like the WRONG team's hue.
                var sprs = visualizer.GetComponentsInChildren<SpriteRenderer>(true);
                foreach (var sr in sprs)
                {
                    if (sr == null) continue;
                    if (looksWrong(sr.color))
                    {
                        sr.color = new Color(desired.r, desired.g, desired.b, sr.color.a);
                        sprites++;
                    }
                }

                // 2) ParticleSystems — main module + colorOverLifetime.
                var pss = visualizer.GetComponentsInChildren<ParticleSystem>(true);
                foreach (var ps in pss)
                {
                    if (ps == null) continue;
                    var main = ps.main;
                    var sc = main.startColor;
                    Color current = sc.color;
                    if (looksWrong(current))
                    {
                        sc.color = new Color(desired.r, desired.g, desired.b, current.a);
                        main.startColor = sc;
                        particles++;
                    }
                }

                // 3) PlayerSkin / PlayerSkinHandler MonoBehaviours within the visualizer.
                //    Some hue propagation goes via these field-color reads at render time,
                //    not via the spawned sprites — set the fields too.
                var comps = visualizer.GetComponentsInChildren<MonoBehaviour>(true);
                foreach (var c in comps)
                {
                    if (c == null) continue;
                    var t = c.GetType();
                    if (t.Name != "PlayerSkin" && t.Name != "PlayerSkinHandler") continue;
                    foreach (var f in t.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                    {
                        if (f.FieldType != typeof(Color)) continue;
                        try
                        {
                            var v = (Color)f.GetValue(c);
                            if (looksWrong(v))
                            {
                                f.SetValue(c, new Color(desired.r, desired.g, desired.b, v.a));
                                skinFields++;
                            }
                        }
                        catch { }
                    }
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CARDPICK-TINT] retint failed: {ex.Message}"); }

            // Always log (Aug 22): a zero-repaint completion used to be silent,
            // which made "retint ran but painted nothing" (custom=False
            // resolution, filter miss) indistinguishable from "retint never
            // ran" — the #83/#286 prove-the-surface-is-reached rule. One line
            // per pick, alongside the existing [CARDPICK-DIAG]/[CARDPICK-BODY].
            Plugin.Log.LogInfo($"[CARDPICK-TINT] pickerID={pickerID} team={pickerTeamID} custom={hasCustom} retinted: sprites={sprites} particles={particles} skinFields={skinFields}");

            // v1.30 (#58 "no body, cosmetics still show"): the picker's body IS the
            // clone's root particle system (learning #96 — vanilla Play()s exactly
            // one PS at Show-time, before children spawn). If it isn't emitting by
            // now, kick it — and ALWAYS log its state so the next report tells us
            // which layer failed instead of guessing. Never Pause/Stop/Clear (#96/#108).
            try
            {
                var bodyPs = visualizer.GetComponent<ParticleSystem>() ?? visualizer.GetComponentInChildren<ParticleSystem>(true);
                if (bodyPs != null)
                {
                    bool wasPlaying = bodyPs.isPlaying;
                    if (!wasPlaying) bodyPs.Play(true);
                    Plugin.Log.LogInfo($"[CARDPICK-BODY] pickerID={pickerID} ps={bodyPs.gameObject.name} wasPlaying={wasPlaying} count={bodyPs.particleCount} activeInHierarchy={bodyPs.gameObject.activeInHierarchy} worldPos={bodyPs.transform.position}");
                }
                else
                {
                    Plugin.Log.LogWarning($"[CARDPICK-BODY] pickerID={pickerID} NO ParticleSystem found on visualizer — body cannot render");
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CARDPICK-BODY] check failed: {ex.Message}"); }

        }

        // RGB distance — works for any hue without needing to convert to HSV.
        // Threshold 0.35 matches PlayerColorCosmetic.IsTeamLike so we get the
        // same "look like the team's color, not face/gun/accent" filter.
        private static bool IsCloseHue(Color a, Color b)
        {
            float dr = a.r - b.r, dg = a.g - b.g, db = a.b - b.b;
            return Mathf.Sqrt(dr * dr + dg * dg + db * db) < 0.35f;
        }
    }

    [HarmonyPatch(typeof(CardChoiceVisuals), "Show")]
    class CardChoiceVisuals_Show_Competitive_Patch
    {
        /// <summary>players[] index the visualizer is currently displaying
        /// (-1 = none). Read by MultiPickerShowVisualsPatch so a sequential
        /// picker is only re-Shown when the body on screen isn't already
        /// theirs. Recorded in EVERY room so the value can't go stale.</summary>
        internal static int LastShownPickerIndex = -1;

        /// <summary>Review find 1: PointVisualizer.DoWinSequence runs CONCURRENTLY
        /// with RoundTransition and is never awaited, so its
        /// `Show(orangeWinner ? 1 : 0)` can land AFTER we corrected the body for
        /// the real picker — destroying that skin and re-showing players[teamId]
        /// (in 2v2, a player from the wrong team) for the rest of the pick.
        /// Re-Showing in the StartPick prefix alone can't win that race. So:
        /// while a pick is actually in progress, ANY incoming Show is retargeted
        /// to the active picker. Outside a live pick (notably DoStartGame's own
        /// per-picker Show, which runs before StartPick) this is a no-op.</summary>
        static void Prefix(ref int pickerID)
        {
            try
            {
                if (PhotonNetwork.OfflineMode) return;
                if (!Diag2v2.IsActive() || Diag2v2.IsFfa()) return;
                var cc = CardChoice.instance;
                if (cc == null || !cc.IsPicking) return;
                int activePid = cc.pickrID;          // PlayerID, not an index
                if (activePid < 0) return;
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return;
                int idx = -1;
                for (int i = 0; i < pm.players.Count; i++)
                    if (pm.players[i] != null && pm.players[i].PlayerID == activePid) { idx = i; break; }
                if (idx < 0 || idx == pickerID) return;
                var p = pm.players[idx];
                if (p.data == null || p.data.view == null) return;
                Plugin.Log.LogInfo($"[CARDPICK-BODY] retargeted a late Show({pickerID}) to the active picker idx={idx} pid={activePid}");
                pickerID = idx;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CARDPICK-BODY] Show retarget failed: {ex.Message}"); }
        }

        static void Postfix(CardChoiceVisuals __instance, int pickerID)
        {
            LastShownPickerIndex = pickerID;
            // Item 19 fix pass 3 (H3): set once this Show reached the carrier
            // ledger as a REMOTE picker's popup; every other Show (the local
            // picker, offline, or any early return or fault below) ends the
            // ledger's popup session in the finally, so a carrier arriving
            // later is never equipped onto a skin that is not its picker's.
            bool remoteShown = false;
            try
            {
                // Bug: "my skin wasn't Mustard during card pick" (casual room,
                // Aug 22). This gate was IsCompetitiveRoom() — learning #286's
                // exact shape left behind on the cosmetic surface: room-code
                // casual (and room-code RATED) rooms never matched, so the
                // pick-body custom-color retint, the cr_face fallback apply and
                // every [CARDPICK-*] diagnostic were structurally unreachable
                // in the rooms most play happens in. Everything below is local,
                // idempotent, per-seat cosmetic work — the sanctioned gate is
                // the AnyGameScope shape (VanillaFixes.cs:25-34): any online
                // room. Offline keeps vanilla's separate Show branch untouched.
                if (PhotonNetwork.OfflineMode || !PhotonNetwork.InRoom) return;
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null || pickerID < 0 || pickerID >= pm.players.Count) return;
                var picker = pm.players[pickerID];
                if (picker == null) return;
                var pv = picker.GetComponent<PhotonView>();
                if (pv == null || pv.Owner == null) return;

                // If THIS client is the picker, republish our cr_face right
                // before the visualizer renders. Tester report (Sid2's logs)
                // showed multiple players' face publish never reached remote
                // clients despite OnJoinedRoom firing — likely a replication
                // race between OnJoinedRoom and the first card-pick on a peer.
                // A republish here gives the remote a fresh property right
                // before they need it.
                // Item 19 fix pass 2 (H3): the local cache takes that write only
                // on the server's echo, so this pass uses the value it has just
                // published (or nothing when the attempt cleared or kept the
                // carrier) and never rereads the cache. Fix pass 3 (H3, the
                // remote arm), bound in fix pass 4: that publish is bound to
                // the pick this popup shows (PopupCarriers.PickNow), and a
                // remote picker's face is the value it published bound to the
                // pick THIS seat's popup shows, never this seat's cached copy
                // and never a value bound to another pick or to none:
                // PopupCarriers.ForShow hands it over when it has arrived, and
                // otherwise owes the apply, which
                // PopupCarriers.Arrived completes. AvatarRules.PopupFace decides
                // which arm runs.
                string freshFace = null;
                var carrier = picker.IsLocal ? FacePublisher.PublishLocal(out freshFace, forPick: true) : FaceCarrierAction.Keep;
                // Instinct achievement (v1.30): remember whose pick popup this is
                // so the RPCA_SetCurrentSelected postfix only counts LOCAL scrolls.
                CardPickSelectionTracker.CurrentPickerIsLocal = picker.IsLocal;

                int pickerActor = pv.Owner.ActorNumber;
                string popupFace = new AvatarRules().PopupFace(picker.IsLocal, carrier, freshFace,
                    () => { string v = PopupCarriers.ForShow(pickerActor); remoteShown = true; return v; });
                bool ok = FacePublisher.ApplySerialized(popupFace, pickerActor, __instance.gameObject);
                if (remoteShown && popupFace != null) PopupCarriers.Applied(pickerActor, ok);
                if (ok)
                    Plugin.Log.LogInfo($"[POPUP] CardChoiceVisuals: applied picker face ({(picker.IsLocal ? "the value this pass published" : "the value its picker published bound to this pick")}) (pickerID={pickerID}, actor={pickerActor})");
                else if (picker.IsLocal && carrier != FaceCarrierAction.Publish)
                    Plugin.Log.LogInfo($"[POPUP] CardChoiceVisuals: local picker carrier {carrier}, no face applied; vanilla's RPC in charge (pickerID={pickerID})");

                // Diagnostic for "2 of 4 pickers don't show a character" bug.
                // Log currentSkin state + transform so we can tell if the GO
                // exists, is active, has children, and where it's positioned.
                try
                {
                    var fSkin = typeof(CardChoiceVisuals).GetField("currentSkin",
                        BindingFlags.NonPublic | BindingFlags.Instance);
                    var skin = fSkin?.GetValue(__instance) as GameObject;
                    string skinDesc;
                    if (skin == null) skinDesc = "(null)";
                    else
                    {
                        var lp = skin.transform.localPosition;
                        var ls = skin.transform.localScale;
                        int childCount = skin.transform.childCount;
                        skinDesc = $"name={skin.name} active={skin.activeInHierarchy} layer={skin.layer} children={childCount} localPos=({lp.x:F1},{lp.y:F1},{lp.z:F1}) localScale=({ls.x:F2},{ls.y:F2},{ls.z:F2})";

                        // Deferred re-tint + body health-check only. The clone must be
                        // left at vanilla's stage-center placement: it sits under the
                        // 33x-scaled CardChoiceVisuals root, so any local offset lands
                        // at offset*33 world units — the retired 2v2 anti-stack spread
                        // (v1.27-v1.30.1) was exactly that, parking solo-pick bodies at
                        // world X=-198/-66, i.e. bug #58's "no body, cosmetics show".
                        // Only one picker body exists at a time (vanilla destroys
                        // currentSkin on every Show), so no spread is ever needed.
                        if (Plugin.Instance != null && skin != null)
                        {
                            Plugin.Instance.StartCoroutine(
                                CardPickBodyTinter.RetintAfterChildrenSpawn(skin, picker.TeamID, pickerID, pv.Owner.ActorNumber));
                        }
                    }
                    Plugin.Log.LogInfo($"[CARDPICK-DIAG] pickerID={pickerID} actor={pv.Owner.ActorNumber} pid={picker.PlayerID} team={picker.TeamID} isLocal={picker.IsLocal} currentSkin: {skinDesc}");
                }
                catch (Exception dex) { Plugin.Log.LogWarning($"[CARDPICK-DIAG] log error: {dex.Message}"); }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[POPUP] CardChoiceVisuals.Show postfix error: {ex.Message}"); }
            finally
            {
                if (!remoteShown)
                {
                    try { PopupCarriers.Ended(); }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[POPUP] carrier ledger end failed: {ex.Message}"); }
                }
            }
        }
    }

    /// <summary>Item 19 fix pass 3 (H3): a hidden popup shows no picker, so the
    /// carrier ledger's popup session ends here (what it held for that picker
    /// belongs to the pick that just ended, see PopupCarrierLedger). A postfix,
    /// so it runs also when InactiveVisualsHidePatch skips vanilla's Hide on an
    /// inactive visualizer, which shows no picker either.</summary>
    [HarmonyPatch(typeof(CardChoiceVisuals), "Hide")]
    class CardChoiceVisuals_Hide_PopupCarrier_Patch
    {
        static void Postfix()
        {
            try { PopupCarriers.Ended(); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[POPUP] Hide postfix error: {ex.Message}"); }
        }
    }

    /// <summary>Item 19 fix pass 4 (H3): the game half of the pick identity.
    /// GM_ArmsRace.DoStartGame runs on every fighter seat once per game (the
    /// first game through StartGame, every same-room rematch through
    /// IDoRematch, #138; never from RoundTransition), so the games each seat
    /// counts in a room agree across the seats that saw them start. A void
    /// prefix: it runs whatever a sibling prefix returns (#352) and changes
    /// nothing the game reads. A spectator is not counted (its popups get no
    /// identity, so no carrier is applied there and vanilla's face stands).</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "DoStartGame")]
    internal static class GMArmsRace_DoStartGame_PopupCarrier_Patch
    {
        private static void Prefix()
        {
            try
            {
                if (PhotonNetwork.OfflineMode || RoomActors.LocalIsSpectator) return;
                PopupCarriers.GameStarted();
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[POPUP] carrier ledger game start failed: " + ex.Message); }
        }
    }

    // (Aug 23 round 2: the broadcast pick-phase skin swap briefly lived here
    // as a CardChoiceVisuals.Show postfix — moved to
    // SpectatorSync.PlayPointSequence's round-conversion branch after Codex
    // r1 find 2 proved Show never reaches a spectator seat outside the 1v1
    // DoWinSequence path. See ArtHandlerNextArtPatch.OnPickPhaseObserved.)

    /// <summary>Instinct achievement tracker (v1.30). ROUNDS broadcasts every
    /// card-selection change through CardChoiceVisuals.RPCA_SetCurrentSelected;
    /// selection starts at index 0 (the left-most card). If the LOCAL player's
    /// own pick popup ever moves off index 0, they "viewed the other cards" and
    /// the match's Instinct run is broken. GameStateWatcher resets the flag per
    /// match and evaluates it at game over.</summary>
    internal static class CardPickSelectionTracker
    {
        public static bool CurrentPickerIsLocal;
    }

    /// <summary>Deep End achievement tracker (v1.30, July 12 spec). ROUNDS routes
    /// every Abyssal Countdown activation through AbyssalCountdown.RPCA_Activate
    /// (a ChildRPC that fires on ALL clients). Count only the LOCAL player's
    /// activations; GameStateWatcher banks them per round and requires one in
    /// every round of a won game.</summary>
    [HarmonyPatch(typeof(AbyssalCountdown), "RPCA_Activate")]
    class AbyssalCountdown_Activate_DeepEnd_Patch
    {
        static void Postfix(AbyssalCountdown __instance)
        {
            try
            {
                var cd = __instance.GetComponentInParent<CharacterData>();
                if (cd != null && cd.view != null && cd.view.IsMine)
                    GameStateWatcher.OnAbyssalActivatedLocal();
            }
            catch { }
        }
    }

    [HarmonyPatch(typeof(CardChoiceVisuals), "RPCA_SetCurrentSelected")]
    class CardChoiceVisuals_SetSelected_Instinct_Patch
    {
        static void Postfix(int toSet)
        {
            try
            {
                if (!CompetitiveRoomDetect.IsCompetitiveRoom()) return;
                if (!CardPickSelectionTracker.CurrentPickerIsLocal) return;
                if (toSet != 0 && !GameStateWatcher.achLeftmostViolated)
                {
                    GameStateWatcher.achLeftmostViolated = true;
                    Plugin.Log.LogInfo("[ACH] Instinct run broken — selection moved off the left-most card");
                }
            }
            catch { }
        }
    }

    /// <summary>2v2 crown fix (bug #59). Vanilla GameCrownHandler is hard-coded
    /// 1v1: one crown GameObject whose LateUpdate lerps strictly between
    /// players[0] and players[1] head positions — in a 4-player cr_ff room the
    /// crown can only ever sit on ONE player, and never on players[2]/[3] at
    /// all. This prefix fully replaces LateUpdate in cr_ff rooms: it computes
    /// the leading TEAM from GM_ArmsRace rounds→points (same precedence as
    /// vanilla PointOver), then parks the vanilla crown on one member and a
    /// clone ("cr_mate_crown") on the other. The clone lives as a SIBLING of
    /// the handler (not a child) so positioning the handler on player A can't
    /// drag it, and it dies with the scene — re-created lazily per map.
    /// 1v1 rooms return true and run vanilla untouched.</summary>
    [HarmonyPatch(typeof(GameCrownHandler), "LateUpdate")]
    class GameCrownHandler2v2Patch
    {
        private static GameObject mateCrown;   // Unity fake-null after scene unload → lazily re-cloned
        // Bug #166: has the FFA crown's entrance animation been fired for the
        // current leader-present stretch? Reset whenever the crown goes away
        // (no leader / tie) so the next leader gets a fresh entrance, and on
        // game start so a new map's crown animates in again.
        private static bool _ffaCrownAnimatedIn;

        static bool Prefix(GameCrownHandler __instance)
        {
            // Bug 251 + bug 257 (ALL seats, non-FFA): vanilla's LateUpdate
            // dereferences BOTH players[0]/players[1] CrownPos every frame
            // once a holder is latched. A severed anchor (spectator body
            // reset, OR a departed opponent's destroyed player lingering in
            // the list during v1.39.0's longer post-game windows) turned
            // into a per-frame "NO CROWN POS!?" error storm — 6,007 lines
            // in one bug-257 bundle, on FIGHTER seats, eating the capture
            // budget. Originally spectator-gated; bug 257's version
            // correlation (0 in every 1.38.5 bundle, storms in every
            // 1.39.0 one) proved fighter seats hit the identical state.
            // Severed or undersized roster: freeze the crown this frame
            // instead (no error, no teleport to up*1000; an undersized
            // list would even index-crash vanilla's Lerp). Healthy state
            // falls through to the normal paths below.
            try
            {
                // FFA exempt (client review find 4): the FFA branch below
                // never Lerps players[0]/players[1] — it has its own leader
                // logic with its own anchor guard — and an FFA seat
                // legitimately carries fake-null entries at low slots after
                // a departure, so this guard would freeze the FFA crown
                // permanently.
                if (!Diag2v2.IsFfa())
                {
                    var ps = PlayerManager.instance != null ? PlayerManager.instance.players : null;
                    if (ps == null || ps.Count < 2) return false;
                    var d0 = ps[0] != null ? ps[0].data : null;
                    var d1 = ps[1] != null ? ps[1].data : null;
                    if (d0 == null || d1 == null || d0.crownPos == null || d1.crownPos == null)
                        return false;
                }
            }
            catch { }
            if (!Diag2v2.IsActive()) return true;
            try
            {
                var gm = __instance.gm != null ? __instance.gm : __instance.GetComponentInParent<GM_ArmsRace>();
                if (gm == null || PlayerManager.instance == null || PlayerManager.instance.players == null)
                    return false;

                GameObject ffaCrown = __instance.transform.childCount > 0
                    ? __instance.transform.GetChild(0).gameObject : null;
                if (Diag2v2.IsFfa())
                {
                    // FFA: single crown on the current overall leader (rounds,
                    // then points, from FfaMode's own score table — the vanilla
                    // p1/p2 fields never move in FFA). Ties = no crown.
                    if (ffaCrown == null) return false;
                    var leader = FfaMode.CurrentLeader();
                    if (mateCrown != null && mateCrown.activeSelf) mateCrown.SetActive(false);
                    // Bug 251 verify round: the leader's own crown ANCHOR can
                    // be severed (spectator between-games FullReset) while the
                    // player object stays live — CurrentLeader() checks
                    // player/gameObject/data, never data.crownPos, and the
                    // spectator guard at the top of this prefix deliberately
                    // exempts FFA. Validate the anchor HERE, on the one player
                    // this branch dereferences, and hide the crown instead of
                    // erroring every frame.
                    if (leader == null || !leader.gameObject.activeInHierarchy
                        || leader.data == null || leader.data.crownPos == null)
                    {
                        if (ffaCrown.activeSelf) ffaCrown.SetActive(false);
                        _ffaCrownAnimatedIn = false;   // re-arm for the next leader
                        return false;
                    }
                    if (!ffaCrown.activeSelf) ffaCrown.SetActive(true);

                    // ── Bug #166: "there's no crown on 1st in FFA" ─────────
                    // SetActive alone is NOT enough. Vanilla's crown is
                    // animated IN by CurveAnimation.PlayIn(), which vanilla
                    // calls from GameCrownHandler.PointOver — and that method
                    // is only ever reached through GM_ArmsRace.pointOverAction
                    // (GameCrownHandler.cs:19 subscribes it; GM_ArmsRace.cs
                    // invokes it at :556/:568/:574/:581, all inside
                    // RPCA_NextRound).
                    //
                    // FFA REPLACES RPCA_NextRound wholesale (FfaMode.
                    // HandleNextRound via a Prefix returning false), so
                    // pointOverAction is never invoked in FFA — grep confirms
                    // neither FfaMode nor Plugin raises it. The crown object
                    // therefore stays in its un-animated initial state:
                    // active, positioned correctly, and visually absent.
                    // That is exactly the reported symptom, and it is why the
                    // 2v2 crown (which runs vanilla's round flow, so PointOver
                    // fires) has always worked while FFA's never did.
                    //
                    // Fire the entrance ourselves, once per leader-emergence.
                    if (!_ffaCrownAnimatedIn)
                    {
                        _ffaCrownAnimatedIn = true;
                        try
                        {
                            var anim = __instance.GetComponent<CurveAnimation>();
                            if (anim != null) anim.PlayIn();
                        }
                        catch (Exception ex)
                        {
                            Plugin.Log.LogWarning($"[FFA] crown PlayIn failed: {ex.Message}");
                        }
                    }
                    __instance.transform.position = leader.data.GetCrownPos();
                    return false;
                }

                // Leading team: rounds first, points as tiebreak (vanilla PointOver order).
                int lead = -1;
                if (gm.p1Rounds != gm.p2Rounds) lead = gm.p1Rounds > gm.p2Rounds ? 0 : 1;
                else if (gm.p1Points != gm.p2Points) lead = gm.p1Points > gm.p2Points ? 0 : 1;

                GameObject crown = __instance.transform.childCount > 0
                    ? __instance.transform.GetChild(0).gameObject : null;
                if (crown == null) return false;

                if (lead == -1)
                {
                    // Tied — no crown for anyone (vanilla shows none until a first leader too).
                    if (crown.activeSelf) crown.SetActive(false);
                    if (mateCrown != null && mateCrown.activeSelf) mateCrown.SetActive(false);
                    return false;
                }

                Player a = null, b = null;
                foreach (var p in PlayerManager.instance.players)
                {
                    if (p == null || p.data == null || p.TeamID != lead) continue;
                    if (a == null) a = p; else if (b == null) { b = p; break; }
                }
                if (a == null)
                {
                    if (crown.activeSelf) crown.SetActive(false);
                    if (mateCrown != null && mateCrown.activeSelf) mateCrown.SetActive(false);
                    return false;
                }

                bool aVisible = a.gameObject.activeInHierarchy;
                if (crown.activeSelf != aVisible) crown.SetActive(aVisible);
                if (aVisible) __instance.transform.position = a.data.GetCrownPos();

                if (b != null)
                {
                    if (mateCrown == null)
                    {
                        mateCrown = UnityEngine.Object.Instantiate(crown, __instance.transform.parent);
                        mateCrown.name = "cr_mate_crown";
                        // Match the handler chain's world scale — the clone's new parent
                        // is one level up, so inherit the handler's local scale too.
                        mateCrown.transform.localScale = Vector3.Scale(
                            __instance.transform.localScale, crown.transform.localScale);
                        Plugin.Log.LogInfo("[2v2-CROWN] mate crown cloned");
                    }
                    bool bVisible = b.gameObject.activeInHierarchy;
                    if (mateCrown.activeSelf != bVisible) mateCrown.SetActive(bVisible);
                    if (bVisible)
                    {
                        // The vanilla crown renders at handlerPos + its child-local
                        // offset; mirror that exact world offset on the clone so both
                        // crowns float at the same height above their player.
                        Vector3 childOfs = crown.transform.position - __instance.transform.position;
                        mateCrown.transform.position = b.data.GetCrownPos() + childOfs;
                    }
                }
                else if (mateCrown != null && mateCrown.activeSelf)
                {
                    mateCrown.SetActive(false);
                }
                return false;
            }
            catch (Exception ex)
            {
                // Never break the round over a cosmetic — fall through to vanilla.
                Plugin.Log.LogWarning($"[2v2-CROWN] prefix error: {ex.Message}");
                return true;
            }
        }
    }

    /// <summary>True when we're in a mod-issued competitive room — 2v2 (cr_ff /
    /// team_*), 1v1 ranked (ranked_*), sync tournament (sct-*), 1v2 (ovt_*), or
    /// FFA (ffa_* with the engine active). Used to scope behaviors that should
    /// apply uniformly across competitive paths but NOT to vanilla casual/private
    /// rooms (which may have mixed mod / non-mod players).
    /// </summary>
    internal static class CompetitiveRoomDetect
    {
        public static bool IsCompetitiveRoom()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.CurrentRoom == null) return false;
                var props = PhotonNetwork.CurrentRoom.CustomProperties;
                if (props != null && props.ContainsKey("cr_ff")) return true;
                string n = PhotonNetwork.CurrentRoom.Name ?? "";
                return n.StartsWith("ranked_") || n.StartsWith("team_") || n.StartsWith("sct-")
                    || n.StartsWith("ovt_")
                    || (n.StartsWith("ffa_") && FfaMode.EngineActive());
            }
            catch { return false; }
        }

        /// <summary>Mod-issued room by PRE-JOIN facts alone (Sept 6, A1): the
        /// server-issued name prefix or the 2v2 friendly-fire property. Unlike
        /// IsCompetitiveRoom this does not consult FfaMode.EngineActive() — at
        /// OnJoinedRoom the FFA engine has not decided yet, and the churn freeze
        /// must hold from the first frame in the room. Not a replacement for
        /// IsCompetitiveRoom, which is load-bearing elsewhere (see the note on
        /// VanillaFixSupport.GameplayScope).</summary>
        public static bool IsModIssuedRoom(string name, ExitGames.Client.Photon.Hashtable props)
        {
            try
            {
                if (props != null && props.ContainsKey("cr_ff")) return true;
                string n = name ?? "";
                return n.StartsWith("ranked_", StringComparison.Ordinal) || n.StartsWith("team_", StringComparison.Ordinal)
                    || n.StartsWith("sct-", StringComparison.Ordinal) || n.StartsWith("ovt_", StringComparison.Ordinal)
                    || n.StartsWith("ffa_", StringComparison.Ordinal);
            }
            catch { return false; }
        }
    }

    /// <summary>Bug #64 — per-game card baseline for the hold-Tab board. Vanilla's
    /// rematch flow (GM_ArmsRace.IDoRematch → PlayerManager.ResetCharacters →
    /// Player.FullReset) resets gun/stats/block but never clears data.currentCards,
    /// so the list accumulates across all games in a room. FullReset firing IS the
    /// "new game in same room" signal — snapshot the count so TabStatsOverlay can
    /// render only cards picked since.</summary>
    [HarmonyPatch(typeof(global::Player), "FullReset")]
    class Player_FullReset_CardBaseline_Patch
    {
        static void Postfix(global::Player __instance)
        {
            try { TabStatsOverlay.RecordCardBaseline(__instance); } catch { }
        }
    }

    /// <summary>Auto-confirm the post-game "Continue?" popup so all clients advance
    /// together. Vanilla `PopUpHandler.StartPicking` waits for the local-mine player
    /// to press Jump on a directional Yes/No selector — there's no network sync of
    /// the choice, each client decides independently. In 2v2 with 4 sequential
    /// pickers this caused desync (player 1 hits Yes → DoContinue locally → next
    /// round on their client; others stuck). Even in 1v1, players found the prompt
    /// annoying and "really don't like hitting Yes". Bypass: Prefix fires the
    /// supplied callback with `Yes` immediately and skips the picker setup.
    /// Gated to MOD-ISSUED ROOMS ONLY (ranked_*, team_*, sct-*, ovt_, ffa_,
    /// cr_ff). Rated room-code games keep the vanilla prompt — see below.
    ///
    /// KNOWN ISSUE — bug 228 (post-match room deaths in RATED ROOM-CODE
    /// games) is deliberately NOT fixed here. Four review rounds (Codex
    /// tournament r1-r4, Aug 15) killed every attempt to widen this gate
    /// beyond mod-issued rooms, each on a real mechanism: (r1) MatchIsRanked
    /// / series-id predicates are seat-asymmetric; (r2/r3) a seat-local
    /// latch is unsafe because vanilla's Yes (GM_ArmsRace.IDoRematch,
    /// decompile :345-376) starts a 10-SECOND timer that NetworkRestarts
    /// the answering seat BY ITSELF when the peer doesn't also answer —
    /// an unanswered popup, by contrast, waits indefinitely — so a
    /// one-sided auto-Yes actively kills the auto-answering seat; (r4)
    /// even a replicated-prop handshake fails asymmetrically when one
    /// seat's SetCustomProperties publish fails while its local latch is
    /// retained. The revised bug-228 mechanism is vanilla's 10s timer
    /// racing two HUMAN answers. A real fix needs a peer-coordinated
    /// commit protocol with an acknowledgment barrier (both seats confirm
    /// intent, then both answer inside one exchange) — design it as its
    /// own pass; do not bolt another seat-local predicate onto this gate.</summary>
    [HarmonyPatch(typeof(PopUpHandler), "StartPicking")]
    class PopUpHandler_StartPicking_Competitive_Patch
    {
        static bool Prefix(global::Player player, Action<PopUpHandler.YesNo> functionToCall)
        {
            try
            {
                // Spectator: never answers a rematch/continue prompt (design
                // §2 census — the auto-confirm would make the spectator
                // release every player immediately). Defense in depth: the
                // GM lifecycle that opens the prompt is already suppressed.
                if (RoomActors.LocalIsSpectator) return false;
                // Mod-issued rooms ONLY — see the KNOWN ISSUE in the class
                // comment before widening this (r4 pre-committed cut).
                if (!CompetitiveRoomDetect.IsCompetitiveRoom()) return true;
                Plugin.Log.LogInfo("[POPUP] Auto-confirming Continue prompt (competitive room bypass)");
                try { functionToCall?.Invoke(PopUpHandler.YesNo.Yes); }
                catch (Exception ex) { Plugin.Log.LogError($"[POPUP] Continue auto-invoke failed: {ex.Message}"); }
                return false;  // skip vanilla picker setup entirely
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[POPUP] StartPicking prefix error: {ex.Message}");
                return true;
            }
        }
    }

    /// <summary>Sort the SpawnPoint[] array left-to-right by X position in cr_ff
    /// rooms. PlayerManager.MovePlayers indexes spawnPoints[i] for players[i],
    /// but the prefab child order isn't guaranteed to be left-then-right. With
    /// our slot mapping (slots 0/1 = team 0, slots 2/3 = team 1), sorting X
    /// ascending puts team 0 on the left half, team 1 on the right half — same
    /// layout as 1v1.</summary>
    [HarmonyPatch(typeof(MapManager), "GetSpawnPoints")]
    class MapManager_GetSpawnPoints_2v2_Patch
    {
        static void Postfix(ref SpawnPoint[] __result)
        {
            try
            {
                if (__result == null || __result.Length < 2) return;
                if (!Diag2v2.IsActive()) return;
                Array.Sort(__result, (a, b) =>
                    (a == null ? 0f : a.localStartPos.x).CompareTo(b == null ? 0f : b.localStartPos.x));
                // 1v2 (bug #91 comment 1: "the second duo person kept spawning
                // where my teammate would, next to me, instead of next to his
                // ally"). PlayerManager.MovePlayers pairs spawnPoints[i] with
                // players[i], and players is slot-indexed (0=solo, 1=duo_a,
                // 2=duo_b), so a plain left-to-right sort hands the solo AND
                // duo_a the two LEFT-half points and strands duo_b alone on the
                // right. Every vanilla map ships exactly 4 points, two per half
                // (verified across all 70 map scenes), so give the solo the
                // outer-left point and the duo the whole right half. The unused
                // inner-left point is parked at the tail to keep the length.
                if (Diag2v2.IsOvt() && __result.Length >= 4)
                {
                    var s = __result;
                    __result = new[] { s[0], s[2], s[3], s[1] };
                }
                // FFA: maps ship ~2-4 spawn points; PlayerManager.MovePlayers
                // indexes spawnPoints[i] per player, so an N-player lobby on a
                // smaller map would IndexOutOfRange mid-transition. Pad by
                // REUSING existing points cyclically — exact duplicates are
                // guaranteed-valid positions (physics separates the overlap in
                // the first frames; a synthesized offset could land inside a
                // wall — Codex design find 22).
                if (Diag2v2.IsFfa())
                {
                    int need = Diag2v2.PlayersNeeded();
                    if (__result.Length < need)
                    {
                        var padded = new SpawnPoint[need];
                        for (int i = 0; i < need; i++)
                            padded[i] = __result[i % __result.Length];
                        __result = padded;
                    }
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] SpawnPoint sort failed: {ex.Message}"); }
        }
    }

    /// <summary>In cr_ff rooms, force teammates to share a team color. Vanilla
    /// PlayerSkinBank.GetPlayerSkinColors(playerID) returns a different skin
    /// per slot (orange/pink/blue/something), so 2v2 ends up with 4 visually
    /// distinct players. Map slot → team-base (slots 0,1 → 0; slots 2,3 → 2)
    /// so both team-0 players look orange and both team-1 players look blue.
    /// PlayerColorCosmetic's custom body-color override still applies on top.</summary>
    [HarmonyPatch(typeof(PlayerSkinBank), "GetPlayerSkinColors")]
    class PlayerSkinBank_GetPlayerSkinColors_2v2_Patch
    {
        // CRITICAL: the parameter MUST be named `team` to match vanilla's
        // signature — HarmonyX binds Prefix parameters by NAME. v1.25.10
        // shipped this with `playerID` which broke `PatchAll()` entirely.

        // Class names whose calls to GetPlayerSkinColors should map slot→team_skin
        // in 2v2. UI code (PointVisualizer, UIHandler) passes literal team-index
        // values (0 or 1) and shouldn't be mapped — that's what made the round
        // counter fill BOTH dots orange in v1.25.14 (team 1's `1` got mapped to
        // `0` and returned orange instead of blue).
        private static readonly System.Collections.Generic.HashSet<string> _bodyCallers =
            new System.Collections.Generic.HashSet<string>
        {
            "PlayerSkinHandler",   // body skin instantiate
            "Player",              // SetColors / GetTeamColors / SetCardLevelTeam
            "PlayerAssigner",      // initial body color setup
            "HealthHandler",       // hp sprite + death effect colors
            "CharacterData",       // any direct player-data path
            "Holdable",            // gun/block trail colors
            "DeathEffect",         // death particle colors
            "PlayerSkinParticle",  // body particle colors
            "DamageHandler",       // hit-blink / damage flash
            "CardChoiceVisuals",   // card-pick body skin
        };

        private static readonly System.Collections.Generic.HashSet<string> _loggedKeys =
            new System.Collections.Generic.HashSet<string>();
        private static float _lastClear;

        static void Prefix(ref int team)
        {
            try
            {
                if (!Diag2v2.IsActive()) return;
                // FFA: PlayerIDs run 0..9 but the vanilla skins array has 4
                // entries — ANY unclamped call (ours or vanilla's own
                // GetColorFromTeam) would IndexOutOfRange. Colors repeat
                // (slot % 4); nametags keep duplicates distinguishable.
                if (Diag2v2.IsFfa())
                {
                    if (team > 3) team = ((team % 4) + 4) % 4;
                    return;
                }
                if (team < 0 || team > 3) return;

                // Walk a few stack frames up to determine if this call is for a
                // player BODY (where we want slot→team_skin mapping) vs a UI
                // ELEMENT (where the input is already a team index). UI bypass
                // is what restores the round-counter blue fill.
                bool isBodyCaller = false;
                try
                {
                    var st = new System.Diagnostics.StackTrace(1, false);
                    int n = Math.Min(st.FrameCount, 6);
                    for (int i = 0; i < n; i++)
                    {
                        var m = st.GetFrame(i)?.GetMethod();
                        if (m == null) continue;
                        string typeName = m.DeclaringType?.Name ?? "";
                        if (_bodyCallers.Contains(typeName)) { isBodyCaller = true; break; }
                    }
                }
                catch { }
                if (!isBodyCaller) return;

                int original = team;
                team = Diag2v2.SlotToTeam(team);   // 2v2: slot/2 · 1v2: solo=0, duo=1

                if (Time.realtimeSinceStartup - _lastClear > 5f)
                {
                    _loggedKeys.Clear();
                    _lastClear = Time.realtimeSinceStartup;
                }
                string key = $"{original}→{team}";
                if (_loggedKeys.Add(key))
                    Plugin.Log.LogInfo($"[2v2-COLOR] body-call mapped {key}");
            }
            catch { }
        }
    }

    /// <summary>v1.28 — remote-player skin re-bake guard (the OTHER half of the
    /// both-orange bug). PlayerSkinHandler.Init reads data.player.PlayerID and
    /// bakes PlayerSkinBank.GetPlayerSkinColors(PlayerID). In a cr_ff room, if
    /// Init runs before the player's PlayerID is assigned (it defaults to 0),
    /// the body bakes with team-0's skin (orange) regardless of the real team.
    /// The existing CreatePlayer override re-bakes the LOCAL player, but REMOTE
    /// players have no equivalent — they rely on the ReadPlayerID→Start ordering,
    /// which races. This Postfix runs a deferred check on EVERY PlayerSkinHandler
    /// in a cr_ff room: a few frames after Init, if the player's PlayerID is now
    /// known and the baked skin doesn't match PlayerID/2's team, force a re-bake.
    /// Self-correcting for both local and remote, idempotent (only re-bakes on
    /// mismatch). Gated strictly to cr_ff so 1v1 / casual are untouched.</summary>
    [HarmonyPatch(typeof(PlayerSkinHandler), "Init")]
    class PlayerSkinHandlerInitRebakeGuard
    {
        static void Postfix(PlayerSkinHandler __instance)
        {
            try
            {
                if (!Diag2v2.IsActive()) return;
                if (__instance == null || Plugin.Instance == null) return;
                Plugin.Instance.StartCoroutine(VerifyAndRebake(__instance));
            }
            catch { }
        }

        private static System.Collections.IEnumerator VerifyAndRebake(PlayerSkinHandler psh)
        {
            // Let PlayerID assignment + the initial bake settle.
            for (int i = 0; i < 8; i++) yield return null;
            if (psh == null) yield break;
            int rebakes = 0;
            try
            {
                // Resolve this skin handler's owning player + PlayerID via reflection.
                var fData = typeof(PlayerSkinHandler).GetField("data",
                    BindingFlags.NonPublic | BindingFlags.Instance);
                var data = fData?.GetValue(psh);
                if (data == null) yield break;
                var pPlayer = data.GetType().GetField("player",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)?.GetValue(data);
                if (pPlayer == null) yield break;
                var pidProp = pPlayer.GetType().GetProperty("PlayerID",
                    BindingFlags.Public | BindingFlags.Instance);
                if (pidProp == null) yield break;
                int playerID = (int)pidProp.GetValue(pPlayer);
                if (playerID < 0 || playerID > 3) yield break;

                // Expected team skin index after our GetPlayerSkinColors SlotToTeam
                // Prefix: the baked child should correspond to the slot's team.
                int expectedTeam = Diag2v2.SlotToTeam(playerID);
                // Heuristic for "baked wrong": the child skin GO carries no reliable
                // team marker, so instead we detect the known failure — a non-team-0
                // player (playerID >= 2, i.e. team 1) whose body still reads team-0
                // (orange) baseline. We re-bake whenever the player is team 1 but the
                // first body sprite's color is closer to team 0's color than team 1's.
                var sr = psh.GetComponentInChildren<SpriteRenderer>(true);
                if (sr == null) yield break;
                CardPickBodyTinter.EnsureTeamColors();
                Color c0 = CardPickBodyTinter.TeamColor0;
                Color c1 = CardPickBodyTinter.TeamColor1;
                Color want = (expectedTeam == 1) ? c1 : c0;
                Color other = (expectedTeam == 1) ? c0 : c1;
                float dWant = ColorDist(sr.color, want);
                float dOther = ColorDist(sr.color, other);
                // Only re-bake when the body clearly matches the WRONG team.
                if (dOther + 0.08f < dWant)
                {
                    var fInited = typeof(PlayerSkinHandler).GetField("inited",
                        BindingFlags.NonPublic | BindingFlags.Instance);
                    for (int i = psh.transform.childCount - 1; i >= 0; i--)
                    {
                        var ch = psh.transform.GetChild(i);
                        if (ch != null) UnityEngine.Object.Destroy(ch.gameObject);
                    }
                    fInited?.SetValue(psh, false);
                    var initMethod = typeof(PlayerSkinHandler).GetMethod("Init",
                        BindingFlags.NonPublic | BindingFlags.Instance);
                    initMethod?.Invoke(psh, null);
                    rebakes++;
                    Plugin.Log.LogInfo($"[2v2-COLOR] Re-baked skin for PlayerID={playerID} (expectedTeam={expectedTeam}, body matched wrong team)");
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2-COLOR] rebake guard error: {ex.Message}"); }
        }

        private static float ColorDist(Color a, Color b)
        {
            float dr = a.r - b.r, dg = a.g - b.g, db = a.b - b.b;
            return (float)Math.Sqrt(dr * dr + dg * dg + db * db);
        }
    }

    /// <summary>MapManager.UnloadAfterSeconds was the original v1.25.4-era crash
    /// site (NRE on a missing PhotonView). Wrap to catch and log instead of
    /// letting the throw propagate into Photon's network restart path.</summary>
    [HarmonyPatch(typeof(MapManager), "UnloadAfterSeconds")]
    class MapManager_UnloadAfterSeconds_Diag_Patch
    {
        static Exception Finalizer(Exception __exception)
        {
            if (__exception != null && Diag2v2.IsActive())
            {
                try { Plugin.Log.LogError($"[2v2-DIAG] MapManager.UnloadAfterSeconds threw: {__exception.GetType().Name}: {__exception.Message}"); }
                catch { }
            }
            return __exception;  // rethrow normally — don't swallow
        }
    }

    /// <summary>Bug #91 comment 4: "when duos picked cards, the second person
    /// to pick did not have a player avatar/character during their turn".
    ///
    /// Vanilla only ever Shows the card-pick body in two places. GM_ArmsRace.
    /// DoStartGame Shows once PER PICKER inside its loop, so game-start picks
    /// are fine. But RoundTransition's pick loop Shows NOTHING — the only
    /// round-pick Show is PointVisualizer.DoWinSequence's single
    /// `Show(orangeWinner ? 1 : 0)`, which passes the losing TEAM id as a
    /// players[] INDEX. With a one-player losing team (vanilla 1v1) that's
    /// correct by luck. With a 2-player losing team (a 1v2 duo), picker B
    /// never gets a Show, and picker A's DoPick already ran
    /// CardChoiceVisuals.Hide() — whose DelayHide deactivates
    /// transform.GetChild(0) — so B picks in front of an empty stage.
    /// (Same root cause makes 2v2's first picker render the WRONG body: when
    /// team 1 loses, Show(1) displays players[1], a team-0 player.)
    ///
    /// Fix: re-issue vanilla's own Show for each incoming picker, exactly as
    /// DoStartGame does, unless the visualizer is already showing them. Show
    /// calls StopAllCoroutines + re-activates the child, so it also cancels
    /// the previous picker's in-flight DelayHide.</summary>
    [HarmonyPatch(typeof(CardChoice), "StartPick")]
    class MultiPickerShowVisualsPatch
    {
        static void Prefix(int pickerIDToSet)
        {
            try
            {
                // 2v2 + 1v2 only. 1v1/quickplay never has a multi-player losing
                // team; FFA replaces the pick phase and never calls StartPick.
                // Offline is excluded because vanilla Show takes a different
                // branch there (CharacterCreatorHandler.selectedPlayerFaces
                // indexed by pickerID), and a stale pending slot can leave
                // IsActive() true at the menu after Sandbox (learning #122).
                if (PhotonNetwork.OfflineMode) return;
                if (!Diag2v2.IsActive() || Diag2v2.IsFfa()) return;
                var vis = CardChoiceVisuals.instance;
                var pm = PlayerManager.instance;
                if (vis == null || pm == null || pm.players == null) return;
                // Show's parameter is a players[] INDEX (it dereferences
                // players[pickerID].data.view.IsMine). Resolve PlayerID -> index
                // rather than assuming they match.
                int idx = -1;
                for (int i = 0; i < pm.players.Count; i++)
                    if (pm.players[i] != null && pm.players[i].PlayerID == pickerIDToSet) { idx = i; break; }
                if (idx < 0) return;
                if (CardChoiceVisuals_Show_Competitive_Patch.LastShownPickerIndex == idx) return;
                var p = pm.players[idx];
                if (p.data == null || p.data.view == null) return;   // Show would NRE
                vis.Show(idx, animateIn: true);
                Plugin.Log.LogInfo($"[CARDPICK-BODY] re-Show for sequential picker idx={idx} pid={pickerIDToSet}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[CARDPICK-BODY] re-Show failed: {ex.Message}"); }
        }
    }

    /// <summary>
    /// July 22 item 3 — 1v2 Solo Extra Initial Pick. Vanilla's pick loop is
    /// natively multi-pick (StartPick sets `picks`; ReplaceCards re-deals while
    /// picks > 0, all driven on the PICKER's client only, so a flag mismatch
    /// can never stall the WaitForSyncUp barrier — remote clients just watch
    /// replicated card spawns until RPCA_DonePicking). We bump the SOLO
    /// player's INITIAL draw from 1 to 2 picks when the series has the toggle.
    /// Initial-draw discriminator: all four GM_ArmsRace score fields are 0
    /// (round picks always run after RPCA_NextRound incremented rounds; holds
    /// for same-room rematches too since ResetMatch zeroes scores first).
    /// Flag carrier: cr_ovt_xp ROOM prop (stamped by the room creator from the
    /// lock payload) with the local lock cache as fallback.
    /// FIRST-PLAYTEST-PENDING: vanilla online never passes picks>1, so the
    /// second ReplaceCards round-trip is unproven in the wild (learning #145).
    /// </summary>
    [HarmonyPatch(typeof(CardChoice), "StartPick")]
    class OvtExtraPickPatch
    {
        /// <summary>PlayerID we granted the extra pick to, or -1. Read by
        /// OvtExtraPickRestorePickerPatch.</summary>
        internal static int ActivePickerId = -1;

        static void Prefix(ref int picksToSet, int pickerIDToSet)
        {
            // Any new pick sequence invalidates a previous grant.
            ActivePickerId = -1;
            try
            {
                if (picksToSet != 1) return;
                if (PhotonNetwork.OfflineMode || !PhotonNetwork.InRoom) return;
                string rn = PhotonNetwork.CurrentRoom?.Name ?? "";
                if (!rn.StartsWith("ovt_")) return;
                // Flag: room prop first, local lock cache as fallback.
                bool extra = false;
                var rp = PhotonNetwork.CurrentRoom.CustomProperties;
                if (rp != null && rp.ContainsKey("cr_ovt_xp"))
                    extra = rp["cr_ovt_xp"] is bool b ? b : rp["cr_ovt_xp"]?.ToString() == "True";
                else
                    extra = ApiClient.OvtSoloExtraPick;
                if (!extra) return;
                // Initial draw only: every score field still zero.
                var gm = GM_ArmsRace.instance;
                if (gm == null) return;
                if (gm.p1Points != 0 || gm.p2Points != 0 || gm.p1Rounds != 0 || gm.p2Rounds != 0) return;
                // Picker must be the SOLO side = the ROUNDS team with exactly
                // one player (same detection TryReportOvtMatch trusts).
                var picker = PlayerManager.instance?.GetPlayerWithID(pickerIDToSet);
                if (picker == null) return;
                int teamSize = 0;
                foreach (var po in PlayerManager.instance.players)
                    if (po != null && po.TeamID == picker.TeamID) teamSize++;
                if (teamSize != 1) return;
                picksToSet = 2;
                // Remember who we granted it to — OvtExtraPickRestorePickerPatch
                // needs it to undo vanilla's mid-sequence pickrID wipe. Cleared
                // when the pick sequence ends.
                ActivePickerId = pickerIDToSet;
                Plugin.Log.LogInfo($"[1v2-EXTRAPICK] solo picker {pickerIDToSet} (team {picker.TeamID}) gets 2 initial picks");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[1v2-EXTRAPICK] prefix failed: {ex.Message}");
            }
        }
    }

    /// <summary>THE 1v2 extra-pick crash fix (bugs #85/#86).
    ///
    /// Vanilla clears the picker the instant a card is chosen:
    ///     Pick(spawnedCards[currentlySelectedCard]);
    ///     pickrID = -1;                       // CardChoice.DoPlayerSelect
    /// With vanilla's picks==1 that is harmless — the follow-up ReplaceCards
    /// takes the `picks &lt;= 0` branch and just RPCs RPCA_DonePicking. Our extra
    /// pick is the ONLY online path that ever leaves picks &gt; 0 here, so it is
    /// the first thing to run the next branch, which calls SpawnUniqueCard:
    ///     player = PlayerManager.instance.players[pickrID];   // pickrID == -1
    ///     for (...) { if (pickrID != -1) {                    // guard, 4 lines too late
    /// -&gt; ArgumentOutOfRangeException ("Must be NON-NEGATIVE and less than the
    /// size of the collection" — the wording is the tell, it is index -1, not an
    /// ordering problem). The throw kills the ReplaceCards coroutine before
    /// RPCA_DonePicking, so IsPicking stays true, DoPick never returns, the round
    /// never advances, and the solo eventually gets dropped — which the other two
    /// see as "opponent disconnected".
    ///
    /// Restoring pickrID is also what makes the second pick SELECTABLE at all:
    /// CardChoice.Update only calls DoPlayerSelect when `pickrID != -1`, so
    /// without this the player could not choose the second card even if the cards
    /// spawned.
    ///
    /// Scope: only fires when WE granted an extra pick (ActivePickerId >= 0) and
    /// vanilla has picks left, so no vanilla 1v1/2v2 flow is touched.</summary>
    [HarmonyPatch(typeof(CardChoice), "ReplaceCards")]
    class OvtExtraPickRestorePickerPatch
    {
        static void Prefix(CardChoice __instance)
        {
            try
            {
                if (OvtExtraPickPatch.ActivePickerId < 0) return;
                // picks > 0 means another deal is coming (the branch that calls
                // SpawnUniqueCard). picks == 0 means this call only sends
                // RPCA_DonePicking, which does not need a picker.
                if (__instance.picks <= 0) { OvtExtraPickPatch.ActivePickerId = -1; return; }
                if (__instance.pickrID != -1) return;      // vanilla state still intact
                __instance.pickrID = OvtExtraPickPatch.ActivePickerId;
                Plugin.Log.LogInfo(
                    $"[1v2-EXTRAPICK] restored pickrID={__instance.pickrID} for the extra deal " +
                    $"(vanilla cleared it to -1 on pick; picks left={__instance.picks})");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[1v2-EXTRAPICK] restore failed: {ex.Message}"); }
        }
    }

    /// <summary>
    /// Hooks CardChoice.Pick to capture LOCAL card picks with full CardInfo.
    /// Pick only fires for the local player's selection.
    /// Used to confirm local picks and extract rarity data.
    /// </summary>
    [HarmonyPatch(typeof(CardChoice), "Pick")]
    class CardChoicePickPatch
    {
        static void Prefix(GameObject pickedCard, bool clear)
        {
            try
            {
                if (pickedCard == null) return;

                CardInfo cardInfo = pickedCard.GetComponent<CardInfo>();
                if (cardInfo == null)
                    cardInfo = pickedCard.GetComponentInChildren<CardInfo>();
                if (cardInfo == null) return;

                string cardName = null;
                try
                {
                    var flags = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;
                    var nameField = typeof(CardInfo).GetField("cardName", flags);
                    if (nameField != null)
                        cardName = nameField.GetValue(cardInfo) as string;
                }
                catch { }

                if (string.IsNullOrEmpty(cardName))
                    cardName = pickedCard.name.Replace("(Clone)", "").Trim();

                if (string.IsNullOrEmpty(cardName)) return;

                int pickerID = -1;
                try { pickerID = CardChoice.instance.pickrID; } catch { }

                Plugin.Log.LogInfo($"[HARMONY-CARD] Local Pick: card={cardName}, pickerID={pickerID}");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[HARMONY-CARD] Pick hook error: {ex.Message}");
            }
        }
    }

    /// <summary>
    /// Hooks CardChoice.RPCA_DoEndPick — the Photon RPC that fires on ALL clients
    /// for ALL player card picks (local AND opponent).
    /// 
    /// Verified from diagnostics:
    ///   pickId = player index (0 or 1), matches localTeam
    ///   targetCardID = Photon ViewID of the picked card GameObject
    ///   theInt = card position in the pick UI (not player-related)
    /// </summary>
    [HarmonyPatch(typeof(CardChoice), "RPCA_DoEndPick")]
    class CardChoiceEndPickPatch
    {
        // Buffer for picks that arrive before localTeam is resolved
        private static List<PendingPick> pendingPicks = new List<PendingPick>();

        private struct PendingPick
        {
            public string CardName;
            public string Rarity;
            public int PickId;
        }

        /// <summary>
        /// Called by GameStateWatcher once localTeam is known.
        /// Flushes any buffered picks that were opponent cards.
        /// </summary>
        public static void FlushPendingPicks(int localTeam)
        {
            if (pendingPicks.Count == 0) return;

            foreach (var pick in pendingPicks)
            {
                if (pick.PickId != localTeam && !string.IsNullOrEmpty(pick.CardName))
                {
                    Plugin.Log.LogInfo($"[HARMONY-CARD] Flushing pre-match opp card: {pick.CardName} ({pick.Rarity})");
                    GameStateWatcher.OnOpponentCardPicked(pick.CardName, pick.Rarity);
                }
            }
            pendingPicks.Clear();
        }

        public static void ClearPending()
        {
            pendingPicks.Clear();
        }

        static void Prefix(int[] cardIDs, int targetCardID, int theInt, int pickId)
        {
            try
            {
                // Spectator: observe-only clients must not feed pick tracking
                // at all (design-review find 12: buffered "localTeam unknown"
                // picks from a WATCHED match survive the session and would
                // flush into the next FIGHTER match's opponent telemetry).
                if (SpectatorSession.IsLocalSpectator) return;

                // Instinct (bug #60): the scroll tracker alone can miss a pick
                // (stale CurrentPickerIsLocal, RPC ordering), so also verify the
                // card actually TAKEN. theInt is the pick-UI slot index, 0 =
                // left-most. Resolve "is this my pick" via the player's own
                // PhotonView instead of localTeam so pre-match picks (localTeam
                // not yet resolved) are covered too.
                try
                {
                    if (theInt != 0 && CompetitiveRoomDetect.IsCompetitiveRoom())
                    {
                        var pkr = PlayerManager.instance != null ? PlayerManager.instance.GetPlayerWithID(pickId) : null;
                        if (pkr != null && pkr.data != null && pkr.data.view != null && pkr.data.view.IsMine
                            && !GameStateWatcher.achLeftmostViolated)
                        {
                            GameStateWatcher.achLeftmostViolated = true;
                            Plugin.Log.LogInfo($"[ACH] Instinct run broken — took card slot {theInt} (not the left-most)");
                        }
                    }
                }
                catch { }

                int localTeam = GameStateWatcher.LocalTeamId;

                // Resolve card name via Photon ViewID
                string cardName = null;
                string rarity = "Unknown";

                try
                {
                    var photonView = PhotonView.Find(targetCardID);
                    if (photonView != null)
                    {
                        var cardInfo = photonView.GetComponent<CardInfo>();
                        if (cardInfo == null)
                            cardInfo = photonView.GetComponentInChildren<CardInfo>();

                        if (cardInfo != null)
                        {
                            var flags = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;
                            var nameField = typeof(CardInfo).GetField("cardName", flags);
                            if (nameField != null)
                                cardName = nameField.GetValue(cardInfo) as string;

                            var rarityField = typeof(CardInfo).GetField("rarity", flags);
                            if (rarityField != null)
                            {
                                var rarVal = rarityField.GetValue(cardInfo);
                                rarity = rarVal?.ToString() ?? "Unknown";
                            }
                        }

                        if (string.IsNullOrEmpty(cardName))
                            cardName = photonView.gameObject.name.Replace("(Clone)", "").Trim();
                    }
                }
                catch { }

                // Canonicalize before anything downstream consumes it. The cardInfo.cardName
                // field and GameObject name can diverge (e.g. "Poison" vs "Poison Bullets",
                // "Prisitne Perseverence" vs "Pristine Perseverence") — without this, match
                // reports leak the non-canonical form and split the card in stats.
                if (!string.IsNullOrEmpty(cardName))
                    cardName = CardRarityLookup.GetCanonicalName(cardName);

                if (!string.IsNullOrEmpty(cardName) && rarity == "Unknown")
                    rarity = CardRarityLookup.GetRarity(cardName);

                // If localTeam not yet resolved, buffer the pick for later
                if (localTeam < 0)
                {
                    if (!string.IsNullOrEmpty(cardName))
                    {
                        pendingPicks.Add(new PendingPick { CardName = cardName, Rarity = rarity, PickId = pickId });
                        Plugin.Log.LogInfo($"[HARMONY-CARD] Buffered pick: card={cardName}, pickId={pickId} (localTeam unknown)");
                    }
                    return;
                }

                bool isOpponent = (pickId != localTeam);
                Plugin.Log.LogInfo($"[HARMONY-CARD] EndPick: card={cardName ?? "(unresolved)"}, pickId(player)={pickId}, localTeam={localTeam}, isOpp={isOpponent}");

                if (isOpponent && !string.IsNullOrEmpty(cardName))
                {
                    Plugin.Log.LogInfo($"[HARMONY-CARD] Opponent picked: {cardName} ({rarity})");
                    GameStateWatcher.OnOpponentCardPicked(cardName, rarity);
                }

                // Pass-tracking: if LOCAL was the picker, capture every card on offer.
                // cardIDs[] is the full set shown in the pick UI; targetCardID is the chosen one.
                if (!isOpponent && cardIDs != null && cardIDs.Length > 0)
                {
                    int round = GameStateWatcher.CurrentRound;
                    int localOffersSnapshot = GameStateWatcher.LocalOffersCount;
                    var bflags = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;
                    var cnField = typeof(CardInfo).GetField("cardName", bflags);
                    foreach (int cid in cardIDs)
                    {
                        try
                        {
                            var pv = PhotonView.Find(cid);
                            if (pv == null) continue;
                            string cn = null;
                            var ci = pv.GetComponent<CardInfo>();
                            if (ci == null) ci = pv.GetComponentInChildren<CardInfo>();
                            if (ci != null && cnField != null)
                                cn = cnField.GetValue(ci) as string;
                            if (string.IsNullOrEmpty(cn))
                                cn = pv.gameObject.name.Replace("(Clone)", "").Trim();
                            cn = CardRarityLookup.GetCanonicalName(cn);
                            if (string.IsNullOrEmpty(cn)) continue;
                            bool wasPicked = cid == targetCardID;
                            GameStateWatcher.OnLocalCardOffered(cn, wasPicked, round);
                            if (wasPicked)
                                Plugin.Log.LogInfo($"[HARMONY-CARD] offer marked picked: card={cn} cid={cid} target={targetCardID} round={round}");
                        }
                        catch (Exception ex)
                        {
                            Plugin.Log.LogWarning($"[HARMONY-CARD] offer loop error on cid={cid}: {ex.Message}");
                        }
                    }
                    // Safety net: if none of the cardIDs[] entries resolved to a "picked"
                    // offer (PhotonView.Find returned null for all, or targetCardID wasn't
                    // present in the array — e.g. reroll / special card paths), manually add
                    // one was_picked=true offer so pass_rate doesn't stay at 100%. The
                    // fallback uses whatever card name GameStateWatcher already captured from
                    // the Unity log "Picking Card:" line for this round, which is the
                    // canonical source of truth for "what did the local player actually take."
                    int newOffers = GameStateWatcher.LocalOffersCount - localOffersSnapshot;
                    bool anyPickedRecorded = GameStateWatcher.LocalOffersPickedIn(localOffersSnapshot);
                    if (!anyPickedRecorded)
                    {
                        string fallbackName = GameStateWatcher.LastLocalPickedCardName;
                        if (!string.IsNullOrEmpty(fallbackName))
                        {
                            GameStateWatcher.OnLocalCardOffered(fallbackName, true, round);
                            Plugin.Log.LogInfo($"[HARMONY-CARD] offer fallback picked: card={fallbackName} round={round} (newOffers={newOffers}, no picked row in cardIDs[])");
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[HARMONY-CARD] EndPick error: {ex.Message}");
            }
        }
    }

    /// <summary>
    /// Injects a "COMPETITIVE" button into the main menu's ListMenu.
    /// Runs from Update() — checks once per scene if injection is needed.
    /// </summary>
    public static class MainMenuInjector
    {
        private static bool injected = false;
        private static float checkTimer = 0f;
        private static GameObject injectedButton = null;
        private static int retryCount = 0;
        private static int maxRetries = 30; // 30 seconds of trying — enough for slow scene loads
        private static bool loggedFirstInjection = false; // Suppress verbose re-injection logs, not warnings
        private static bool wasInRoomLastCheck = false;   // detect room-exit → fresh retry budget
        private static bool loggedBudgetExhausted = false;

        /// <summary>
        /// Resets injector state — called when persistent object respawns
        /// so the button gets re-injected on the new scene.
        /// </summary>
        public static void Reset()
        {
            injected = false;
            injectedButton = null;
            retryCount = 0;
            // Keep loggedFirstInjection to avoid re-logging verbose info
        }

        public static void TryInject()
        {
            // Don't spam checks — once per second
            checkTimer += Time.deltaTime;
            if (checkTimer < 1f) return;
            checkTimer = 0f;

            // Only inject when not in a Photon room (i.e., on main menu). This
            // check MUST come before the retry accounting: the old order burned
            // the whole 30-try budget at 1/sec while the player was mid-match
            // (button destroyed on room join → injected=false → tick, tick,
            // tick...), so after any game longer than 30s the button never came
            // back for the rest of the session (bug #27, "menu item always
            // disappears after a few games"). In-room ticks are free now, and
            // leaving a room refreshes the budget.
            // Bug #46/#122 (Spirit, Aug 27): the OfflineMode exemption is
            // load-bearing. Photon's Sandbox simulates a room and KEEPS
            // InRoom==true at the main menu after leaving it, so a bare
            // InRoom test here parked this gate permanently after any
            // Sandbox visit and the menu button never reappeared (F5 kept
            // working — it has no room check).
            bool inRoomNow = false;
            try { inRoomNow = Photon.Pun.PhotonNetwork.InRoom && !Photon.Pun.PhotonNetwork.OfflineMode; } catch { }
            if (inRoomNow)
            {
                wasInRoomLastCheck = true;
                return;
            }
            if (wasInRoomLastCheck)
            {
                wasInRoomLastCheck = false;
                retryCount = 0;          // fresh budget back at the menu
                loggedBudgetExhausted = false;
            }

            // Already injected and button still exists
            if (injected && injectedButton != null) return;

            // Button was destroyed (scene change) — allow re-injection
            if (injected && injectedButton == null)
            {
                injected = false;
                retryCount = 0;
                // Don't re-log on re-injection — already logged once
            }

            // After the budget, don't stop forever — degrade to a slow retry
            // (every ~10s) as a self-healing failsafe. A menu that exists but
            // briefly lacked its QUIT button (mid-rebuild) used to strand us.
            if (retryCount >= maxRetries)
            {
                if (!loggedBudgetExhausted)
                {
                    loggedBudgetExhausted = true;
                    Plugin.Log.LogWarning($"[MENU] Injection still failing after {maxRetries} attempts — dropping to slow retry (10s)");
                }
                if (retryCount % 10 != 0) { retryCount++; return; }
            }
            retryCount++;

            try
            {
                DoInject();
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[MENU] Injection failed: {ex.Message}");
            }
        }

        private static System.Type cachedTmpType = null;

        private static void DoInject()
        {
            // Cache TMP_Text type for text reading
            if (cachedTmpType == null)
            {
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    cachedTmpType = asm.GetType("TMPro.TMP_Text");
                    if (cachedTmpType != null) break;
                }
                if (cachedTmpType == null)
                {
                    Plugin.Log.LogWarning("[MENU] TMPro.TMP_Text not found");
                    return;
                }
            }

            var textProp = cachedTmpType.GetProperty("text",
                System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
            if (textProp == null) return;

            // Find ALL ListMenuButtons in the scene
            var allButtons = UnityEngine.Object.FindObjectsOfType<ListMenuButton>();
            if (allButtons == null || allButtons.Length == 0) return;

            // Anchor on the QuitButton COMPONENT, not the rendered text:
            // ROUNDS localizes the label (ru/ja/es render as their own words)
            // and auto-selects locale from the OS culture, so the old
            // text=="QUIT" match returned null on every non-English install —
            // the mod's menu entry was never created and those players never
            // found F5 either. The component is locale-independent and the
            // mod already knows it (it destroys it on the clone below).
            ListMenuButton quitButton = null;
            foreach (var btn in allButtons)
            {
                try
                {
                    if (btn != null && btn.GetComponent<QuitButton>() != null)
                    {
                        quitButton = btn;
                        break;
                    }
                }
                catch { }
            }
            if (quitButton == null)
            {
                // Literal-text fallback (pre-fix behavior) in case a future
                // game build moves the component off the ListMenuButton GO.
                foreach (var btn in allButtons)
                {
                    try
                    {
                        var tmpComp = btn.GetComponentInChildren(cachedTmpType, true);
                        if (tmpComp == null) continue;
                        string text = (textProp.GetValue(tmpComp) as string ?? "").Trim().ToUpper();
                        if (text == "QUIT")
                        {
                            quitButton = btn;
                            break;
                        }
                    }
                    catch { }
                }
            }

            if (quitButton == null)
            {
                // Only warn once per injection cycle
                if (!loggedFirstInjection)
                    Plugin.Log.LogWarning("[MENU] Could not find QUIT button in main menu");
                return;
            }

            Transform templateTransform = quitButton.transform;
            Transform container = templateTransform.parent;

            // Only log first injection
            if (!loggedFirstInjection)
                Plugin.Log.LogInfo($"[MENU] Found QUIT button at {templateTransform.name}, parent: {container.name}");

            // Clone the QUIT button
            var clone = UnityEngine.Object.Instantiate(templateTransform.gameObject, container);
            clone.name = "CompetitiveRoundsButton";

            // Insert above QUIT — layout group will handle spacing automatically
            clone.transform.SetSiblingIndex(templateTransform.GetSiblingIndex());

            // Change the text (short label for the menu)
            bool textSet = false;
            try
            {
                var tmpComponent = clone.GetComponentInChildren(cachedTmpType);
                if (tmpComponent != null)
                {
                    textProp.SetValue(tmpComponent, "SID'S COMPETITIVE ROUNDS");
                    textSet = true;
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[MENU] TMP text change failed: {ex.Message}");
            }

            if (!textSet)
                Plugin.Log.LogWarning("[MENU] Could not set button text");

            // ── FIX: Keep ListMenuButton for hover highlight ──
            // ListMenuButton is purely visual — it handles text color, hover bar animation,
            // font sizing. It has NO page/action fields (verified from Assembly-CSharp.dll).
            // The actual click behavior comes from QuitButton, GoBack, and Button.onClick,
            // which we remove/override below. Keeping ListMenuButton = orange hover bar works!

            // CRITICAL: Remove QuitButton component — without this, clicking quits the game
            try
            {
                var quitComp = clone.GetComponent<QuitButton>();
                if (quitComp != null)
                    UnityEngine.Object.Destroy(quitComp);
            }
            catch { }

            // Also remove GoBack if present
            try
            {
                var goBack = clone.GetComponent<GoBack>();
                if (goBack != null)
                    UnityEngine.Object.Destroy(goBack);
            }
            catch { }

            // Add our click handler component
            clone.AddComponent<CompetitiveMenuButton>();

            injectedButton = clone;
            injected = true;
            if (!loggedFirstInjection)
            {
                Plugin.Log.LogInfo("[MENU] Competitive button injected into main menu!");
                loggedFirstInjection = true;
            }
        }
    }

    /// <summary>
    /// Simple MonoBehaviour attached to the injected menu button.
    /// Detects pointer clicks and opens the overlay.
    /// </summary>
    public class CompetitiveMenuButton : MonoBehaviour
    {
        private const string BUTTON_TEXT = "SID'S COMPETITIVE ROUNDS";
        private object cachedTmpComponent = null;
        private System.Reflection.PropertyInfo cachedTextProp = null;
        private bool textEnforcementReady = false;

        private void Start()
        {
            // Cache the TMP component and text property for text enforcement
            CacheTmpReferences();

            // Try to wire into the Unity Button onClick via reflection
            try
            {
                System.Type buttonType = null;
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    buttonType = asm.GetType("UnityEngine.UI.Button");
                    if (buttonType != null) break;
                }

                if (buttonType != null)
                {
                    var btn = GetComponent(buttonType);
                    if (btn != null)
                    {
                        // Clear existing listeners
                        var onClickProp = buttonType.GetProperty("onClick",
                            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                        if (onClickProp != null)
                        {
                            var onClick = onClickProp.GetValue(btn);
                            // RemoveAllListeners
                            var removeAll = onClick.GetType().GetMethod("RemoveAllListeners");
                            if (removeAll != null) removeAll.Invoke(onClick, null);

                            // AddListener with our action
                            var addListener = onClick.GetType().GetMethod("AddListener");
                            if (addListener != null)
                            {
                                var action = (UnityEngine.Events.UnityAction)OnButtonClick;
                                addListener.Invoke(onClick, new object[] { action });
                                Plugin.Log.LogInfo("[MENU] Button onClick wired successfully");
                            }
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[MENU] Button wiring failed: {ex.Message}");
            }
        }

        private void CacheTmpReferences()
        {
            try
            {
                System.Type tmpType = null;
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    tmpType = asm.GetType("TMPro.TMP_Text");
                    if (tmpType != null) break;
                }
                if (tmpType == null) return;

                cachedTmpComponent = GetComponentInChildren(tmpType);
                if (cachedTmpComponent == null) return;

                cachedTextProp = tmpType.GetProperty("text",
                    System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);

                textEnforcementReady = (cachedTextProp != null);
            }
            catch { }
        }

        /// <summary>
        /// ROUNDS' ListMenuButton re-initializes after submenu navigation and resets
        /// the TMP text back to "QUIT". LateUpdate catches this and re-applies our text.
        /// </summary>
        private void LateUpdate()
        {
            if (!textEnforcementReady) return;

            try
            {
                string current = cachedTextProp.GetValue(cachedTmpComponent) as string;
                if (current != BUTTON_TEXT)
                {
                    cachedTextProp.SetValue(cachedTmpComponent, BUTTON_TEXT);
                }
            }
            catch { }
        }

        private void OnButtonClick()
        {
            Plugin.Log.LogInfo("[MENU] Competitive button clicked!");
            CompetitiveUI.ToggleOverlay();
        }
    }

    /// <summary>
    /// Static lookup table for card name → rarity.
    /// Built by Harmony hook on GM_ArmsRace.Awake.
    /// </summary>
    public static class CardRarityLookup
    {
        private static readonly Dictionary<string, string> lookup = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private static readonly Dictionary<string, string> canonical = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        // Known mismatches between GameObject name (log capture) and cardName field.
        // Maps input (either form) → canonical card name used in the DB. Dictionary is
        // OrdinalIgnoreCase so "abyssalcountdown" finds the same entry as "AbyssalCountdown",
        // but both forms must still route through GetCanonicalName() to be normalized —
        // several paths historically skipped the call (fixed one more in this pass:
        // OnOpponentCardPicked). Entries cover every ROUNDS rename / typo / CamelCase
        // compression we've observed producing near-duplicates in the DB.
        private static readonly Dictionary<string, string> hardAliases = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            // Letter typos
            { "Leach", "Leech" },
            { "Riccochet", "Ricochet" },
            // CamelCase / no-space GameObject-name variants → spaced display-name canonical
            { "BombsAway", "Bombs Away" },
            { "Glasscannon", "Glass Cannon" },
            { "ShieldCharge", "Shield Charge" },
            { "AbyssalCountdown", "Abyssal Countdown" },
            { "ChillingPresence", "Chilling Presence" },
            { "DrillAmmo", "Drill Ammo" },
            { "RadarShot", "Radar Shot" },
            { "TargetBounce", "Target Bounce" },
            { "TasteOfBlood", "Taste Of Blood" },
            { "Fastball", "Fast Ball" },
            // "Poison Bullets" was the old pre-rename name for what ROUNDS now displays as
            // just "Poison" — reverse the previous alias so every variant canonicalizes to
            // the in-game display (migration 043 merged historical rows).
            { "Poison Bullets", "Poison" },
            { "PoisonBullets",  "Poison" },
            // Pristine Perseverance had two independent typos accumulating: the previous
            // canonical was itself misspelled ("Perseverence"), and at least one code path
            // missed the alias and wrote both typos raw ("Prisitne Perseverence"). Canonical
            // is now the correct in-game spelling; aliases below cover every observed typo.
            { "Prisitne Perseverence", "Pristine Perseverance" },
            { "Pristine Perseverence", "Pristine Perseverance" },
            { "PristinePerseverance", "Pristine Perseverance" },
            { "PristinePerseverence", "Pristine Perseverance" },
        };

        public static void Register(string cardName, string rarity)
        {
            if (!string.IsNullOrEmpty(cardName))
            {
                lookup[cardName] = rarity;
                if (!canonical.ContainsKey(cardName))
                    canonical[cardName] = cardName;
            }
        }

        public static string GetRarity(string cardName)
        {
            if (string.IsNullOrEmpty(cardName)) return "Unknown";
            if (lookup.TryGetValue(cardName, out string rarity))
                return rarity;
            // Try alias
            string norm = GetCanonicalName(cardName);
            if (norm != cardName && lookup.TryGetValue(norm, out rarity))
                return rarity;
            return "Unknown";
        }

        /// <summary>
        /// Maps a log-captured card name to the canonical CardInfo name.
        /// Returns title-cased canonical name for display.
        /// </summary>
        public static string GetCanonicalName(string name)
        {
            if (string.IsNullOrEmpty(name)) return name;
            // Hard alias first
            if (hardAliases.TryGetValue(name, out string alias))
                name = alias;
            // Canonical map (populated during ScanAll)
            if (canonical.TryGetValue(name, out string canon))
                return ToTitleCase(canon);
            return name;
        }

        /// <summary>Every RAW in-game spelling that canonicalizes to
        /// <paramref name="canonicalName"/>, including the canonical itself.
        ///
        /// GetCanonicalName is DB-facing and deliberately CORRECTS ROUNDS'
        /// own typos ("Leach" -> "Leech", "Riccochet" -> "Ricochet",
        /// "Poison bullets" -> "Poison"), so for exactly those cards the
        /// canonical name matches NOTHING in the game's CardInfo registry.
        /// Anything resolving a live prefab from a stored name (the native
        /// card snapshot, the card-stats cell) has to walk the alias map
        /// BACKWARDS — that is bug #155's "no CardInfo prefab matches
        /// 'Ricochet'" and the reason those cards always served the PNG.
        ///
        /// Built once, lazily; hardAliases is a readonly literal so the
        /// reverse index can never go stale.</summary>
        private static Dictionary<string, List<string>> _reverseAliases;
        public static List<string> RawNamesFor(string canonicalName)
        {
            var outp = new List<string>();
            if (string.IsNullOrEmpty(canonicalName)) return outp;
            outp.Add(canonicalName);
            try
            {
                if (_reverseAliases == null)
                {
                    var rev = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);
                    foreach (var kv in hardAliases)
                    {
                        if (!rev.TryGetValue(kv.Value, out var l))
                            rev[kv.Value] = l = new List<string>();
                        l.Add(kv.Key);
                    }
                    _reverseAliases = rev;
                }
                if (_reverseAliases.TryGetValue(canonicalName, out var raws))
                    foreach (var r in raws)
                        if (!outp.Contains(r)) outp.Add(r);
            }
            catch { }
            return outp;
        }

        /* Aug 7 item 2 — INVARIANT casing, not the current culture's (#47 family).
         * `ToLower()`/`char.ToUpper()` are culture-sensitive: on a tr-TR client
         * "WIND UP".ToLower() yields "wınd up" with U+0131 DOTLESS I, so that
         * client reported (and the DB stored) "Wınd Up" as a card name entirely
         * separate from "Wind Up" — 19 such twins accumulated in match_cards and
         * 21 in card_offers, all resolving to rarity Unknown because they match
         * nothing in the live CardInfo registry. Card names are DB keys, so they
         * must never depend on the player's locale. Migration 195 merges the rows
         * this produced. */
        private static string ToTitleCase(string input)
        {
            if (string.IsNullOrEmpty(input)) return input;
            var words = input.ToLowerInvariant().Split(' ');
            for (int i = 0; i < words.Length; i++)
                if (words[i].Length > 0)
                    words[i] = char.ToUpperInvariant(words[i][0]) + words[i].Substring(1);
            return string.Join(" ", words);
        }

        public static int Count => lookup.Count;

        /// <summary>
        /// Scan all CardInfo objects in the scene and build the rarity lookup.
        /// Registers BOTH the cardName field and the GameObject name as lookup keys,
        /// mapping both to the canonical cardName.
        /// </summary>
        public static void ScanAll()
        {
            if (lookup.Count > 0) return; // Already populated

            try
            {
                var cardInfoType = typeof(CardInfo);
                var flags = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;

                var nameField = cardInfoType.GetField("cardName", flags);
                var rarityField = cardInfoType.GetField("rarity", flags);
                var nameProp = cardInfoType.GetProperty("CardName", flags);

                var allCards = Resources.FindObjectsOfTypeAll<CardInfo>();

                foreach (var ci in allCards)
                {
                    try
                    {
                        string cardName = null;
                        if (nameField != null)
                            cardName = nameField.GetValue(ci) as string;
                        else if (nameProp != null)
                            cardName = nameProp.GetValue(ci) as string;

                        if (string.IsNullOrEmpty(cardName))
                            cardName = ci.gameObject.name.Replace("(Clone)", "").Trim();

                        if (string.IsNullOrEmpty(cardName)) continue;

                        string rarity = "Unknown";
                        if (rarityField != null)
                        {
                            var rarVal = rarityField.GetValue(ci);
                            rarity = rarVal?.ToString() ?? "Unknown";
                        }

                        // Register canonical cardName
                        Register(cardName, rarity);

                        // Also register by GameObject name (log capture uses this)
                        string goName = ci.gameObject.name.Replace("(Clone)", "").Trim();
                        if (!string.IsNullOrEmpty(goName))
                        {
                            lookup[goName] = rarity;
                            canonical[goName] = cardName; // maps GO name → canonical
                        }
                    }
                    catch { }
                }

                // Register hard aliases
                foreach (var kvp in hardAliases)
                {
                    if (lookup.TryGetValue(kvp.Value, out string r))
                    {
                        lookup[kvp.Key] = r;
                        canonical[kvp.Key] = kvp.Value;
                    }
                }

                if (lookup.Count > 0)
                    Plugin.Log.LogInfo($"[RARITY] Card rarity lookup built: {lookup.Count} entries ({allCards.Length} CardInfo objects scanned)");
                // Warm the localized card-text cache HERE (menu-time, right
                // after the canonical map it keys off exists) so the in-match
                // hold-Tab path never pays the first localized-table load.
                try { CardTextLocalizer.Prime(); } catch { }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[RARITY] Card scan failed: {ex.Message}");
            }
        }

        public static string GetSampleEntries(int max)
        {
            var samples = new List<string>();
            int i = 0;
            foreach (var kvp in lookup)
            {
                samples.Add($"{kvp.Key}={kvp.Value}");
                if (++i >= max) break;
            }
            return string.Join(", ", samples.ToArray());
        }
    }

    /// <summary>
    /// Flashes the ROUNDS taskbar icon when the window is not focused.
    /// Used for ranked match found notifications when alt-tabbed.
    /// Based on code contributed by lopidav.
    /// </summary>
    public class TaskbarFlash : MonoBehaviour
    {
        private const uint FLASHW_STOP = 0;
        private const uint FLASHW_ALL = 3;
        private const uint FLASHW_TIMERNOFG = 12;

        [StructLayout(LayoutKind.Sequential)]
        private struct FLASHWINFO
        {
            public uint cbSize;
            public IntPtr hwnd;
            public uint dwFlags;
            public uint uCount;
            public uint dwTimeout;
        }

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool FlashWindowEx(ref FLASHWINFO pwfi);

        [DllImport("user32.dll")]
        private static extern IntPtr FindWindow(string lpClassName, string lpWindowName);

        private bool shouldFlash = false;
        private bool isFlashing = false;
        private IntPtr gameWindowHandle = IntPtr.Zero;

        private static TaskbarFlash instance;

        private void Awake()
        {
            if (instance != null && instance != this)
            {
                Destroy(gameObject);
                return;
            }
            instance = this;
        }

        private void Update()
        {
            // Resolve window handle (try multiple methods)
            if (gameWindowHandle == IntPtr.Zero)
            {
                try
                {
                    gameWindowHandle = Process.GetCurrentProcess().MainWindowHandle;
                }
                catch { }

                // Fallback: find Unity window by class name
                if (gameWindowHandle == IntPtr.Zero)
                {
                    try { gameWindowHandle = FindWindow("UnityWndClass", null); } catch { }
                }

                if (gameWindowHandle == IntPtr.Zero) return;
                Plugin.Log.LogInfo($"[FLASH] Window handle resolved: {gameWindowHandle}");
            }

            // Use Unity's own focus detection — more reliable than Win32 GetForegroundWindow
            bool isWindowInFocus = Application.isFocused;

            if (shouldFlash && !isFlashing && !isWindowInFocus)
                StartFlashing();

            if (shouldFlash && isWindowInFocus)
                shouldFlash = false;

            if (isFlashing && (!shouldFlash || isWindowInFocus))
                StopFlashing();
        }

        /// <summary>Call this to trigger a taskbar flash (only flashes if window is not focused).</summary>
        public static void Flash()
        {
            if (instance != null)
            {
                instance.shouldFlash = true;
                Plugin.Log.LogInfo($"[FLASH] Flash requested (focused={Application.isFocused}, handle={instance.gameWindowHandle})");
            }
            else
            {
                Plugin.Log.LogWarning("[FLASH] Flash requested but no instance");
            }
        }

        private void StartFlashing()
        {
            if (isFlashing) return;
            FLASHWINFO fInfo = new FLASHWINFO();
            fInfo.cbSize = (uint)Marshal.SizeOf(fInfo);
            fInfo.hwnd = gameWindowHandle;
            fInfo.dwFlags = FLASHW_ALL | FLASHW_TIMERNOFG;
            fInfo.uCount = uint.MaxValue;
            fInfo.dwTimeout = 0;
            bool result = FlashWindowEx(ref fInfo);
            isFlashing = true;
            shouldFlash = true;
            Plugin.Log.LogInfo($"[FLASH] Started flashing (result={result})");
        }

        private void StopFlashing()
        {
            if (!isFlashing) return;
            FLASHWINFO fInfo = new FLASHWINFO();
            fInfo.cbSize = (uint)Marshal.SizeOf(fInfo);
            fInfo.hwnd = gameWindowHandle;
            fInfo.dwFlags = FLASHW_STOP;
            fInfo.uCount = 0;
            fInfo.dwTimeout = 0;
            FlashWindowEx(ref fInfo);
            isFlashing = false;
            shouldFlash = false;
        }
    }

    // ── F5 click-block: stop the LOCAL player from shooting/blocking while the
    //    competitive menu is open. Without this, clicks on Settings buttons fire
    //    the gun in the game world too. uGUI raycast blockers don't help because
    //    Gun.Attack/Block.TryBlock are called from gameplay code reading Input directly.
    //    Only the LOCAL player is gated (PhotonView.IsMine) so opponent shots still render.

    [HarmonyPatch(typeof(Gun), "Attack")]
    class GunAttackBlockOnF5Patch
    {
        static bool Prefix(Gun __instance)
        {
            // Visibility-backed predicate (Aug 30 design review): a wedged
            // isOpen flag with no visible page must never suppress firing.
            if (!NativeUI.InputCaptureActive) return true;
            try
            {
                var pv = __instance != null ? __instance.GetComponentInParent<PhotonView>() : null;
                if (pv == null || !pv.IsMine) return true;  // never block opponents — only the local player
            }
            catch { return true; }
            return false;  // skip the original Attack — local shot suppressed while F5 is open
        }

        // THE COUNTER POSTFIX WAS DELETED (bug #308, review r3 find 1).
        // Its only remaining job was one-shot reject diagnostics, and it was an
        // unguarded log on a live combat path: BepInEx 5 dispatches listeners
        // without exception isolation, so a throwing listener inside it could
        // propagate out of a NESTED forced Attack and stop the outer DoAttack from
        // ever constructing its FireBurst — losing the player's volley. A
        // diagnostic is never worth that. The denominator it used to own now lives
        // at the projectile's birth (GunApplyPlayerStuffProvenancePatch); nothing
        // here needs to run at all. The Prefix above stays — it is the F5
        // click-block and has a real job.
    }

    [HarmonyPatch(typeof(Block), "TryBlock")]
    class BlockTryBlockOnF5Patch
    {
        static bool Prefix(Block __instance)
        {
            if (!NativeUI.InputCaptureActive) return true;   // visibility-backed (Aug 30)
            try
            {
                var pv = __instance != null ? __instance.GetComponentInParent<PhotonView>() : null;
                if (pv == null || !pv.IsMine) return true;
            }
            catch { return true; }
            return false;
        }
    }

    // ── Hit % / Block % tracking (v1.23) ───────────────────────────────────
    //
    // Separate patches from the F5 input-gate above because the gate short-circuits the
    // original with `return false` when F5 is open, and we must NOT count suppressed
    // actions. The BLOCK counters still guard themselves with NativeUI.IsOpen. The
    // BULLET counters no longer need to: the denominator is taken at the projectile's
    // birth (GunApplyPlayerStuffProvenancePatch), and a suppressed Attack never runs
    // the original, so no projectile is ever born to count.
    //
    // Only the LOCAL player is tracked (PhotonView.IsMine on the Gun / Block / target).
    // See learnings.md #4: only the lower Steam ID reports matches, so these counters
    // accumulate on whichever side reports. The backend stores them on the reporter.

    // HISTORICAL NOTE, kept because it records two dead ends. bullets_fired once
    // reused the mouse-click counter (LocalShotsThisMatch), i.e. one "shot" per
    // trigger pull regardless of how many projectiles it birthed; it later became a
    // Gun.Attack Postfix computing numberOfProjectiles * bursts * attacks. Both are
    // gone. The denominator now counts ACTUAL PROJECTILE BIRTHS at
    // GunApplyPlayerStuffProvenancePatch, which is the only form that agrees with
    // the numerator — see the bug #308 block near the end of this file.

    [HarmonyPatch]
    class HealthHandlerTakeDamageCounterPatch
    {
        // HealthHandler.TakeDamage has multiple overloads in ROUNDS (a public canonical one
        // with 8 params and at least one shorter shim), which makes `[HarmonyPatch(typeof(X),
        // "TakeDamage")]` without explicit args throw "Ambiguous match" — that aborts the
        // entire PatchAll() call and nothing else in this assembly gets patched either.
        // Resolve the target ourselves by picking the overload with the most parameters,
        // which is the canonical damage path (damage, position, color, weapon, player, ...).
        static MethodBase TargetMethod()
        {
            var t = typeof(HealthHandler);
            MethodInfo best = null;
            int bestPc = -1;
            foreach (var m in t.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.NonPublic))
            {
                if (m.Name != "TakeDamage") continue;
                int pc = m.GetParameters().Length;
                if (pc > bestPc) { bestPc = pc; best = m; }
            }
            return best;
        }

        // Room rules (Sept 10): the friendly-fire GATE is DamageRulesGate
        // (VanillaFixes.cs) reading RoomRules.FriendlyFire; this probe stays
        // the opt-in per-hit trace it always was (cr_ff = the 2v2 marker).
        // FF-DIAG: in 2v2 rooms (cr_ff Photon room property = true), log when a teammate's
        // damage REACHES TakeDamage. If we see it: the team-filter is downstream of TakeDamage
        // (we'd patch HealthHandler.CallTakeDamage's bail-out). If we DON'T: filter is upstream
        // (in ProjectileCollision / MoveTransform). Opt-in with Block Debug and capped.
        private static int _ffDiagRemaining = 8;
        static void Postfix(HealthHandler __instance, Vector2 damage, GameObject damagingWeapon, Player damagingPlayer)
        {
            try
            {
                if (damagingPlayer == null) return;
                if (damage.magnitude <= 0.01f) return;  // non-damage events (e.g. block-only pings)

                // FF telemetry — fires on any damage event so we can see ALL hits in a 2v2,
                // not just enemy ones. Enabled when cr_ff Photon room property is true.
                try
                {
                    if (Plugin.ShowBlockDebug != null && Plugin.ShowBlockDebug.Value
                        && PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null
                        && PhotonNetwork.CurrentRoom.CustomProperties != null
                        && PhotonNetwork.CurrentRoom.CustomProperties.ContainsKey("cr_ff")
                        && _ffDiagRemaining > 0)
                    {
                        var srcCD = damagingPlayer != null ? damagingPlayer.GetComponent<CharacterData>() : null;
                        var tgtCD = __instance != null ? __instance.GetComponentInParent<CharacterData>() : null;
                        // Player.TeamID via CharacterData.player -- CharacterData has
                        // no teamID field of its own, so the reflection this replaced
                        // resolved to null on every call and BOTH teams read -1, which
                        // made same_team permanently false. A friendly-fire diagnostic
                        // that cannot ever report friendly fire is worse than none
                        // (#441). Decompile: CharacterData.player is a public Player
                        // field; Player.TeamID is a public getter over m_teamID.
                        int srcTeam = (srcCD != null && srcCD.player != null) ? srcCD.player.TeamID : -1;
                        int tgtTeam = (tgtCD != null && tgtCD.player != null) ? tgtCD.player.TeamID : -1;
                        bool sameTeam = (srcTeam >= 0 && srcTeam == tgtTeam);
                        _ffDiagRemaining--;
                        Plugin.Log.LogInfo($"[FF-DIAG] dmg={damage.magnitude:F1} src_team={srcTeam} tgt_team={tgtTeam} same_team={sameTeam} weapon='{(damagingWeapon != null ? damagingWeapon.name : "(null)")}'");
                    }
                }
                catch { }

                var damagerPV = damagingPlayer.data?.view ?? damagingPlayer.GetComponent<PhotonView>();
                var targetPV = __instance != null ? __instance.GetComponentInParent<PhotonView>() : null;

                // Block-debug: if WE are the target and the damager is someone else, record
                // the hit so the overlay can classify it against the last activation time.
                // Owned by the target client — damagerPV.IsMine check is from the wrong side.
                try
                {
                    if (targetPV != null && targetPV.IsMine && damagerPV != null && !damagerPV.IsMine)
                    {
                        GameStateWatcher.OnLocalPlayerHit(damage.magnitude);
                    }
                }
                catch { }

                if (damagerPV == null || !damagerPV.IsMine) return;
                // Self-damage (rebounds, own explosions) shouldn't count toward Hit %.
                if (targetPV != null && targetPV.IsMine) return;

                // Hit counting moved to ProjectileHit_DirectHitCounter_Patch (bug #69).
                // The HIT-DIAG data settled the question this postfix was waiting on:
                // TakeDamage's damagingWeapon is always the GUN (WeaponBase), for DOT
                // ticks too (damage=1.2 events carried the same weapon), so no filter
                // here can separate direct hits from poison/burn ticks. The relaxed
                // count let DOT pump bullets_hit up to the _hitsRemaining cap — i.e.
                // hits == fired == "100% accuracy" for any DOT build (Stan's report).
                // Direct impacts are counted at ProjectileHit.RPCA_DoHit instead, the
                // single funnel every real bullet impact passes through and DOT never
                // does. This postfix still owns the damage timeline and the opt-in
                // block-debug hit signal.
            }
            catch { }
        }
    }

    /// <summary>Bug #69 — precise Hit % numerator. ProjectileHit.RPCA_DoHit is the
    /// one path every direct bullet impact takes (local, remote, and RPC'd), and
    /// DOT/explosion/thorns damage never routes through it. Count an unblocked
    /// impact on an enemy player, owner-side only. The _hitsRemaining budget in
    /// GameStateWatcher still bounds hits ≤ fired.</summary>
    [HarmonyPatch(typeof(ProjectileHit), "RPCA_DoHit")]
    class ProjectileHit_DirectHitCounter_Patch
    {
        // PREFIX, not Postfix (bugs #77/#80): a killing blow's vanilla body runs
        // damage → death → SetActive(false) on the target's ROOT GameObject
        // synchronously, after which GetComponentInParent<Player>() returns null
        // (inactive GO) and the kill shot read as "hit a box". A Postfix also
        // never runs at all if the body throws mid-teardown. Counting up front
        // sees the target while it is still alive; wasBlocked arrives as an
        // argument so the block gate is unaffected.
        static void Prefix(ProjectileHit __instance, int viewID, bool wasBlocked)
        {
            try
            {
                if (wasBlocked) return;               // absorbed — not a hit
                if (viewID == -1) return;             // terrain/map collider
                var own = __instance != null ? __instance.ownPlayer : null;
                if (own == null || own.data == null || own.data.view == null || !own.data.view.IsMine) return;
                var targetView = PhotonNetwork.GetPhotonView(viewID);
                if (targetView == null) return;
                // GetComponent (unlike GetComponentInParent) also works on inactive
                // GameObjects — the Player component lives on the PhotonView's root.
                var targetPlayer = targetView.GetComponent<global::Player>();
                if (targetPlayer == null) targetPlayer = targetView.GetComponentInParent<global::Player>();
                if (targetPlayer == null) return;     // hit a box or other damagable, not a player
                if (targetPlayer.TeamID == own.TeamID) return;  // self or teammate (2v2)

                // NO WINDOW CHECK HERE, deliberately (review r2 find 1). An
                // earlier version gated the hit on battleOngoing too, reasoning
                // that "the same window at both ends" made the halves agree. It
                // did the opposite: a projectile fired DURING battle is counted
                // as fired, but if the point ends while it is still in flight —
                // another player's faster shot decides the round — its landing
                // was then rejected, so fired counted and the hit did not. That
                // is the original asymmetry inverted, and a regression against
                // the numerator that shipped.
                //
                // Eligibility is frozen ONCE, at birth, in TagState.FiredCounted.
                // That is the fact both halves agree on; Generation already
                // rejects a projectile from an earlier match. The window belongs
                // at the birth site only.

                // Provenance + first-hit credit, in one call. Rejects a projectile
                // that was not born of a deliberate player-initiated volley
                // (unknown provenance is NOT counted — fail-closed), and rejects a
                // SECOND impact from a projectile already credited. That second
                // guard matters: RayHitReflect returns hasToReturn, so one bullet
                // can survive its first impact and hit again — two impacts from
                // one projectile would otherwise report 2/2 = 100% off a single
                // hit. Hit% means "projectiles that hit at least one enemy", which
                // is the semantic the hit<=fired cap already implies.
                if (!ShotProvenance.TryConsumeHit(__instance)) return;

                // Observe acceptance, exactly as the birth side does. TryConsumeHit
                // has already burned this projectile's ONE credit, but
                // OnLocalBulletHit has its own gates (isTracking, and the
                // _hitsRemaining budget) and can still refuse. Without this the
                // credit is spent on an impact that was never counted, and the
                // projectile can never score again — under-reporting only, but it
                // made "both halves decided by the same fact" true of eligibility
                // and not of acceptance. Completeness audit, post-r4.
                int hitBefore = GameStateWatcher.LocalBulletsHitThisMatch;
                try { GameStateWatcher.OnLocalBulletHit(); }
                catch { /* observed via the delta below */ }
                bool hitTaken;
                try { hitTaken = GameStateWatcher.LocalBulletsHitThisMatch > hitBefore; }
                catch { hitTaken = false; }
                if (!hitTaken) ShotProvenance.ReleaseHitCredit(__instance);
            }
            catch { /* never break vanilla's hit path */ }
        }
    }

    // Block.TryBlock counter — drives LocalBlocksActivatedThisMatch (the blocks_activated
    // denominator). Full-decompile fact: TryBlock has exactly ONE caller — Block.Update on
    // user block input — so this hook IS the right-click counter (the old comment claiming
    // Shields Up/Empower invoke TryBlock was wrong; every card block goes straight to
    // RPCA_DoBlock). Denominator = right-clicks that fired while off cooldown.
    // ── Block-chain classification (July 21 item 1, Stan's community spec) ──
    // Count ONLY right-click-activated blocks: one right-click = one activation,
    // and its Echo / Shield Charge follow-on auto-blocks inherit the same
    // activation (max 1 success credit). Blocks with NO right-click origin
    // (Abyssal Countdown's BlinkStep, ExtraBlock/Shields Up wiring, revive
    // blocks) count NOWHERE. Verified against the full decompile:
    //  - Block.TryBlock has exactly ONE caller — Block.Update on user input.
    //    (The old comment claiming Shields Up/Empower call TryBlock was wrong.)
    //  - Every block funnels through RPCA_DoBlock(firstBlock, dontSetCD,
    //    triggerType, ...); Echo follow-ons are triggerType=Echo scheduled only
    //    from Default+firstBlock events; ShieldCharge dashes start from any
    //    non-ShieldCharge block event and fire triggerType=ShieldCharge.
    //  - So origin inheritance by TRIGGER TYPE is exact — no time windows:
    //    Default -> user iff called inside TryBlock (re-entrancy flag);
    //    Echo -> status of the last Default+firstBlock; ShieldCharge -> status
    //    of the last non-ShieldCharge event.
    internal static class BlockChain
    {
        internal static bool InTryBlock;
        // TIMESTAMPS, not last-writer-wins booleans (review finding): interleaved
        // auto-blocks (Abyssal BlinkStep fires Default+firstBlock every 0.29s;
        // ExtraBlock-style wiring fires inside the user's own IDoBlock) would
        // otherwise CLOSE a still-open user absorb window and drop the user's
        // legitimate success. Auto events can never close a user window now;
        // the worst case flips to slightly user-FAVORABLE attribution, which
        // _activationSuccessCredited caps at 1 credit per right-click anyway.
        internal static float LastUserWindowTime = -999f;   // any user-chain block event (opens a 0.3s absorb window)
        internal static float LastUserDefaultTime = -999f;  // user right-click (Default+firstBlock) — echo scheduler origin
        internal static void Reset() { InTryBlock = false; LastUserWindowTime = LastUserDefaultTime = -999f; }
        // The absorb event arrives ONE NETWORK ROUND-TRIP after our local
        // block stamp (wasBlocked is decided on the bullet owner's client and
        // RPC'd back), on top of the 0.3s vanilla window — July 21 playtest
        // showed real user absorbs dropped at 0.35s. 0.8s covers window + RTT;
        // over-crediting is bounded by the 1-credit-per-right-click cap.
        internal static bool AbsorbIsUserChain() => Time.time - LastUserWindowTime <= 0.8f;
    }

    [HarmonyPatch(typeof(Block), "RPCA_DoBlock")]
    class BlockRpcaDoBlockChainClassifierPatch
    {
        static void Prefix(Block __instance, bool firstBlock,
                           BlockTrigger.BlockTriggerType triggerType, bool onlyBlockEffects)
        {
            try
            {
                var pv = __instance != null ? __instance.GetComponentInParent<PhotonView>() : null;
                if (pv == null || !pv.IsMine) return;   // local player's block only
                if (onlyBlockEffects) return;           // Empower bullet-site: opens no absorb window
                bool user;
                switch (triggerType)
                {
                    case BlockTrigger.BlockTriggerType.Default:
                        user = firstBlock && BlockChain.InTryBlock;   // BlinkStep/ExtraBlock/ShieldsUp/revive → false
                        if (user) BlockChain.LastUserDefaultTime = Time.time;
                        break;
                    case BlockTrigger.BlockTriggerType.Echo:
                        // Echoes schedule at 0.2s steps from their Default+firstBlock
                        // origin; stacked Echo cards reach ~1s. 1.5s horizon covers it.
                        user = Time.time - BlockChain.LastUserDefaultTime <= 1.5f;
                        break;
                    case BlockTrigger.BlockTriggerType.ShieldCharge:
                        // Dash blocks belong to whatever user-chain event started the
                        // dash; dashes run a couple seconds at high levels.
                        user = Time.time - BlockChain.LastUserWindowTime <= 3.0f;
                        break;
                    default:
                        user = false;
                        break;
                }
                if (user) BlockChain.LastUserWindowTime = Time.time;
                if (GameStateWatcher.IsTracking
                    && Plugin.ShowBlockDebug != null && Plugin.ShowBlockDebug.Value)
                    Plugin.Log.LogInfo($"[BLOCK-DBG] WINDOW type={triggerType} first={firstBlock} user={user}");
            }
            catch { }
        }
    }

    [HarmonyPatch(typeof(Block), "TryBlock")]
    class BlockTryBlockCounterPatch
    {
        // Readiness gate: vanilla activates on `counter >= Cooldown()` which is
        // (cooldown + cdAdd) * cdMultiplier — the old reflection read of the raw
        // `cooldown` field mis-gated whenever a block-CD-modifying card was held.
        // Both members are publicized; read them directly.
        static void Prefix(Block __instance, out bool __state)
        {
            __state = false;
            try { __state = !(__instance.counter < __instance.Cooldown()); }
            catch { __state = true; }
            BlockChain.InTryBlock = true;   // re-entrancy marker: RPCA_DoBlock fired inside this frame = right-click
        }

        static System.Exception Finalizer(System.Exception __exception)
        {
            BlockChain.InTryBlock = false;  // never leave the flag stuck
            return __exception;
        }

        static void Postfix(Block __instance, bool __state, bool __runOriginal)
        {
            if (NativeUI.IsOpen) return;  // F5 Prefix blocked the call; don't credit it
            // Aug 8 (bug-180 audit incidental): when ANY Prefix skipped
            // vanilla TryBlock — the FFA spawn-grace suppressor
            // (Block_FfaSpawnGrace_Patch) returns false during the no-combat
            // window — no block could possibly happen, so crediting an
            // ATTEMPT here inflated the FFA block-% denominator every round
            // start. __runOriginal is Harmony's own "did vanilla run" flag.
            if (!__runOriginal) return;
            try
            {
                var pv = __instance != null ? __instance.GetComponentInParent<PhotonView>() : null;
                if (pv == null || !pv.IsMine) return;

                // [BLOCK-TEAM] diagnostic for the "right-click block fails on non-host" report.
                // Logs EVERY TryBlock attempt by the local player — ready or on cooldown — so
                // we can confirm whether the bug correlates with team / playerId / IsMasterClient.
                // Captures only competitive (mod-issued) rooms so the noise is bounded.
                try
                {
                    if (Plugin.ShowBlockDebug != null && Plugin.ShowBlockDebug.Value
                        && CompetitiveRoomDetect.IsCompetitiveRoom() && !_diagThrottled())
                    {
                        var p = __instance.GetComponentInParent<global::Player>();
                        int team = -1, playerId = -1;
                        try { team = p != null ? p.TeamID : -1; } catch { }
                        try { playerId = p != null ? p.PlayerID : -1; } catch { }
                        int actor = -1;
                        bool isMaster = false;
                        try { actor = PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : -1; } catch { }
                        try { isMaster = PhotonNetwork.IsMasterClient; } catch { }
                        Plugin.Log.LogInfo($"[BLOCK-TEAM] tryBlock ready={__state} team={team} playerID={playerId} actor={actor} isMaster={isMaster}");
                    }
                }
                catch { }

                if (!__state) return;          // block was on cooldown — TryBlock didn't actually activate
                GameStateWatcher.OnLocalBlockActivated();
            }
            catch { }
        }

        // Per-second throttle so a 6-second-cooldown spam doesn't write 200 log lines.
        private static float _lastDiagLogTime;
        private static bool _diagThrottled()
        {
            float now = Time.unscaledTime;
            if (now - _lastDiagLogTime < 0.5f) return true;
            _lastDiagLogTime = now;
            return false;
        }
    }

    [HarmonyPatch]
    class BlockDoBlockCounterPatch
    {
        // Block.DoBlock has multiple overloads across ROUNDS revisions. Target the one with
        // the most parameters (the canonical path). Previously we filtered on
        // triggerType=Default to exclude ShieldCharge/Echo, but empirically this suppresses
        // real bullet-absorb events too (the engine fires DoBlock with various trigger types
        // depending on the source of the hit, not reliably Default for projectiles). Count
        // ANY DoBlock on the local player's block — it represents "your block timed right and
        // stopped something," which matches the user-facing meaning of "successful block."
        static MethodBase TargetMethod()
        {
            var t = typeof(Block);
            MethodInfo best = null;
            int bestPc = -1;
            foreach (var m in t.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.NonPublic))
            {
                if (m.Name != "DoBlock") continue;
                int pc = m.GetParameters().Length;
                if (pc > bestPc) { bestPc = pc; best = m; }
            }
            return best;
        }

        private static bool _firstEntry;
        static void Postfix(Block __instance)
        {
            if (!_firstEntry) { _firstEntry = true; Plugin.Log.LogInfo("[BLOCK] DoBlock Postfix first invocation (patch attached)"); }
            try
            {
                var pv = __instance != null ? __instance.GetComponentInParent<PhotonView>() : null;
                if (pv == null || !pv.IsMine) return;
                // July 21 item 1: the absorb credits the chain that opened a
                // window RECENTLY — user right-click chains (incl. Echo/
                // ShieldCharge follow-ons) count; pure auto-blocks (Abyssal
                // etc.) count nowhere. Time-based so an interleaved auto event
                // can't close a still-open user window.
                GameStateWatcher.OnLocalBlockSuccessful(BlockChain.AbsorbIsUserChain());
            }
            catch { }
        }
    }

    // ── Diagnostic: ConnectToRegion call-site tracer (v1.26.3) ─────────────
    // Lopi reported (v1.26.1 logs): joined ranked room successfully, sat
    // there ~15 seconds with the F5 menu open, then suddenly the vanilla
    // Photon flow fired `connectToRegion us` → Left room → joined a vanilla
    // EU casual room. Match was abandoned; Lexia stuck in the empty ranked
    // room. We don't yet know what triggered NCH.ConnectToRegion mid-room
    // — our QueueJoiner shouldn't fire it once already in the target room,
    // and MainMenuHandler was disabled so vanilla quickmatch shouldn't be
    // reachable. This Prefix logs every call to ConnectToRegion along with
    // a partial managed stack-trace (top 12 frames) when we're in a
    // competitive room, so the next reproduction tells us exactly which
    // code path is calling it.
    //
    // v1.28: the original `[HarmonyPatch(typeof(NetworkConnectionHandler),
    // "ConnectToRegion")]` NEVER ATTACHED — HarmonyX logged "Could not find
    // method for type NetworkConnectionHandler and name ConnectToRegion", so we
    // got zero trace data for ~2 release cycles. ROUNDS routes region switching
    // through Photon's `PhotonNetwork.ConnectToRegion(string)` (a PUN static),
    // not an NCH method of that name. Resolve the target dynamically across both
    // types and read the region via __args so we're agnostic to the exact
    // signature/overload. The expensive stack capture is gated to competitive
    // rooms only — the region-select ping screen calls ConnectToRegion ~17× in a
    // burst and we don't want to trace those.
    class NCHConnectToRegionDiagPatch
    {
        static IEnumerable<MethodBase> TargetMethods()
        {
            var seen = new HashSet<MethodBase>();
            foreach (var t in new[] { typeof(NetworkConnectionHandler), typeof(PhotonNetwork) })
            {
                if (t == null) continue;
                List<MethodInfo> methods = null;
                try { methods = AccessTools.GetDeclaredMethods(t); }
                catch { methods = null; }
                if (methods == null) continue;
                foreach (var m in methods)
                    if (m != null && m.Name == "ConnectToRegion" && seen.Add(m))
                        yield return m;
            }
        }

        static void Prefix(object[] __args)
        {
            try
            {
                // Only trace calls that happen while we're sitting in a competitive
                // room — that's the abandoned-ranked-room bug (Lopi/Lexia). Normal
                // region pinging from the menu is expected and not worth logging.
                if (!CompetitiveRoomDetect.IsCompetitiveRoom()) return;

                string region = "?";
                if (__args != null)
                    foreach (var a in __args) if (a is string s) { region = s; break; }
                string roomName = "(none)";
                try { roomName = PhotonNetwork.CurrentRoom?.Name ?? "(none)"; } catch { }
                // §7.1 (SCR Broadcast): this diagnostic logs room AND region —
                // both are masked on the broadcast seat (identity-latched;
                // r2-F2 forbids deterministic derivatives too, so no hash).
                if (BroadcastMode.IsBroadcastIdentity)
                {
                    region = "(masked)";
                    roomName = BroadcastMode.SafeRoomDesc();
                }
                // Trim the stack-trace to a manageable size — the top frames
                // are what matter.
                var st = new System.Diagnostics.StackTrace(1, false);
                var sb = new System.Text.StringBuilder();
                int n = Math.Min(st.FrameCount, 12);
                for (int i = 0; i < n; i++)
                {
                    var m = st.GetFrame(i)?.GetMethod();
                    if (m == null) continue;
                    sb.Append("  at ").Append(m.DeclaringType?.FullName ?? "?")
                      .Append('.').Append(m.Name).Append('\n');
                }
                Plugin.Log.LogWarning($"[NCH-DIAG] ConnectToRegion('{region}') called " +
                    $"while in comp room='{roomName}'. Stack:\n{sb}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[NCH-DIAG] log error: {ex.Message}"); }
        }
    }

    // ── Block trigger null-safety (v1.26.3) ────────────────────────────────
    // Vanilla Block.IDoBlock iterates Block.triggers and calls DoBlock on each.
    // The iteration does NOT null-check before invoking, but card teardowns
    // between rounds can leave references to destroyed BlockTrigger instances
    // in the list. Vanilla's BlockTrigger.DoBlock reads `this.gameObject`
    // early, which throws NRE on a destroyed Component. The exception
    // propagates out of the IDoBlock coroutine, abandoning the remaining
    // triggers — so a single dangling reference silently breaks ALL of the
    // player's blocks for the rest of the round.
    //
    // Reproduced in Lexia's v1.26.1 logs: 9 BLOCK-DBG ACTIVATED events in a
    // single round, each followed by the same NRE (BlockTrigger.DoBlock
    // [0x0002a]). Block effect never registered for any of them. Adding a
    // Prefix that bails on a destroyed __instance restores the rest of
    // the iteration. Vanilla bug; we're patching the missing null-check.
    [HarmonyPatch(typeof(BlockTrigger), "DoBlock")]
    class BlockTriggerDoBlockNullSafetyPatch
    {
        // Original v1.26.3 patch silently swallowed destroyed-trigger NREs so
        // Block.IDoBlock's iterator could continue with remaining triggers.
        // That fixed Lexia's "9 NREs in one round" cascade but masked an
        // upstream bug where SOME players (Sir Blender, NotHoly reported
        // post-v1.26.3) end up with their MAIN block-effect trigger destroyed
        // — meaning the cascade-skip works as intended, but the visual /
        // damage-absorb that lived on the destroyed trigger never fires and
        // the player's block "doesn't proc". v1.26.5 expands the patch to
        // capture per-call diagnostic context (player ActorNumber + trigger
        // info) so the next reproduction tells us which trigger is being
        // destroyed and from where, AND adds a Finalizer backstop in case
        // vanilla NREs even when __instance looks alive (some sub-component
        // destroyed under it).
        static bool Prefix(BlockTrigger __instance, BlockTrigger.BlockTriggerType triggerType)
        {
            if (__instance == null)
            {
                // Try to figure out which player owned this trigger so the log
                // tells us "Sid's block missed its main trigger" not just
                // "some block trigger somewhere died."
                string ownerInfo = "?";
                try
                {
                    // __instance is fake-null but the wrapper still has a
                    // type — try to introspect. transform/gameObject access
                    // will themselves throw on a destroyed object, so wrap.
                    ownerInfo = "(GameObject destroyed)";
                }
                catch { }
                Plugin.Log.LogWarning($"[BLOCK-SAFETY] DoBlock skipped: triggerType={triggerType} owner={ownerInfo}. " +
                    "If a player's block isn't proccing this round, this is the cause — main BlockTrigger was destroyed.");
                return false;
            }
            return true;
        }

        // Backstop: if vanilla still NREs after the Prefix lets it through
        // (e.g., a child Component on a live BlockTrigger is destroyed),
        // swallow the exception so Block.IDoBlock's iterator continues with
        // the remaining triggers instead of aborting the whole block.
        static Exception Finalizer(Exception __exception, BlockTrigger __instance, BlockTrigger.BlockTriggerType triggerType)
        {
            // MissingReferenceException is what Unity actually throws when a
            // destroyed component's members are touched (zombie DoBlock reads
            // base.gameObject.name) — it does NOT derive from NRE.
            if (__exception is NullReferenceException || __exception is UnityEngine.MissingReferenceException)
            {
                string state = "alive";
                try { if (__instance == null) state = "destroyed"; } catch { state = "introspection-failed"; }
                Plugin.Log.LogWarning($"[BLOCK-SAFETY] NRE inside vanilla DoBlock " +
                    $"(triggerType={triggerType} instance={state}) — swallowed so iterator continues. " +
                    "Stack: " + (__exception.StackTrace ?? "(none)").Replace("\n", " | "));
                return null;
            }
            return __exception;
        }
    }

    // ── Block zombie-delegate scrub (v1.28.2) ──────────────────────────────
    // THE ranked no-block / infinite-empower root cause, established from the
    // CURRENT game decompile (logs-snapshot/decompiled/), not the old-game PI
    // source. There is NO `Block.triggers` list in ROUNDS 1.1.2 — the previous
    // ScrubNullTriggers reflected a field that does not exist and was a silent
    // no-op forever ("scrubbed 0" was structural, not evidence).
    //
    // Real mechanism: card components (Empower, ShieldCharge, BlockTrigger,
    // …) Delegate.Combine their handlers onto Block/Gun/HealthHandler action
    // fields in Start() and Delegate.Remove them in OnDestroy(). But their
    // OnDestroy bodies dereference the parent chain FIRST (e.g. ShieldCharge:
    // `data.GetComponent<PlayerCollision>()` line 1; Empower:
    // `GetComponentInParent<Player>().data.healthHandler`). During the
    // between-games teardown (our auto-Continue rematch) destruction order is
    // arbitrary; those lookups NRE (proven: lopi's log shows
    // ShieldCharge.OnDestroy + EmpowerStopBlockObjectFollow.OnDestroy NREs at
    // LOADING SCENE), OnDestroy aborts, and the dead component's handlers stay
    // subscribed as ZOMBIES:
    //   • zombie BlockTrigger/ShieldCharge handler → MissingReferenceException
    //     inside Block.IDoBlock (which runs synchronously) → coroutine dies
    //     BEFORE `sinceBlock = 0f` → cooldown engages, no effects, no
    //     absorption = "block broken after game 1" (#15/#19/#23/#24). Each
    //     client simulates BOTH players' blocks from replicated input, so a
    //     zombie on the opponent's replica breaks your block on THEIR screen
    //     only ("effects show but nothing blocks").
    //   • zombie Empower.Block/Empower.Attack → invisible infinite empower,
    //     ×2 damage after each block, no particles, no card shown (#25).
    //
    // Fix: surgically remove ONLY invocation-list entries whose Target is a
    // destroyed UnityEngine.Object. Live subscribers are never touched; no
    // wholesale nulling, no re-running Start() (the old rebuild re-Started
    // INACTIVE template triggers vanilla never starts — the #15 regression).
    internal static class BlockReflect
    {
        private static System.Reflection.FieldInfo _fCounter;
        private static System.Reflection.FieldInfo _fCooldown;
        private static bool _resolved;
        private static void Resolve()
        {
            if (_resolved) return;
            try
            {
                var t = typeof(Block);
                var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;
                _fCounter  = t.GetField("counter", bf);
                _fCooldown = t.GetField("cooldown", bf);
            }
            catch { }
            _resolved = true;
        }

        // Per-type cache of delegate-typed instance fields (Block has 6,
        // Gun/HealthHandler/PlayerCollision a few each). Walks the inheritance
        // chain so subclass fields are covered too.
        private static readonly System.Collections.Generic.Dictionary<System.Type, System.Reflection.FieldInfo[]> _delFieldCache
            = new System.Collections.Generic.Dictionary<System.Type, System.Reflection.FieldInfo[]>();

        public static int ScrubDeadDelegateFields(UnityEngine.Component c)
        {
            if (c == null) return 0;
            int removed = 0;
            try
            {
                var t = c.GetType();
                System.Reflection.FieldInfo[] fields;
                if (!_delFieldCache.TryGetValue(t, out fields))
                {
                    var acc = new System.Collections.Generic.List<System.Reflection.FieldInfo>();
                    var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic
                           | System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.DeclaredOnly;
                    for (var cur = t; cur != null && cur != typeof(UnityEngine.MonoBehaviour) && cur != typeof(UnityEngine.Behaviour) && cur != typeof(object); cur = cur.BaseType)
                        foreach (var f in cur.GetFields(bf))
                            if (typeof(System.Delegate).IsAssignableFrom(f.FieldType)) acc.Add(f);
                    fields = acc.ToArray();
                    _delFieldCache[t] = fields;
                }
                foreach (var f in fields)
                {
                    var del = f.GetValue(c) as System.Delegate;
                    if (del == null) continue;
                    var inv = del.GetInvocationList();
                    System.Delegate rebuilt = null;
                    int dead = 0;
                    foreach (var d in inv)
                    {
                        // Unity fake-null: the managed wrapper survives while the
                        // native object is destroyed — exactly the zombie state an
                        // aborted OnDestroy leaves behind. Static handlers
                        // (Target == null) and plain managed targets are kept.
                        var uo = d.Target as UnityEngine.Object;
                        bool zombie = !object.ReferenceEquals(uo, null) && uo == null;
                        if (zombie) { dead++; continue; }
                        rebuilt = System.Delegate.Combine(rebuilt, d);
                    }
                    if (dead > 0)
                    {
                        f.SetValue(c, rebuilt);
                        removed += dead;
                    }
                }
            }
            catch { }
            return removed;
        }

        /// <summary>Scrub ChildRPC's string→delegate DICTIONARIES (bug #39/#40).
        /// Card components register RPC handlers by Dictionary.Add with a fixed
        /// key ("ShieldChargeCollide" etc.) in Start() and Remove them in
        /// OnDestroy(). When OnDestroy aborts mid-teardown (the same #92 NRE —
        /// proven in lopi's log: ShieldCharge.OnDestroy threw, then next game
        /// ShieldCharge.Start threw ArgumentException 'same key already added'
        /// and ABORTED BEFORE its SuperFirstBlockAction subscription — so
        /// blocking worked but the charge never fired), the stale key blocks
        /// the next game's re-registration. Remove entries whose delegate
        /// targets are ALL destroyed objects; live or mixed entries are kept.</summary>
        public static int ScrubChildRpcDictionaries(UnityEngine.Component rpc)
        {
            if (rpc == null) return 0;
            int removed = 0;
            try
            {
                var bf = System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic
                       | System.Reflection.BindingFlags.Instance;
                foreach (var f in rpc.GetType().GetFields(bf))
                {
                    var dict = f.GetValue(rpc) as System.Collections.IDictionary;
                    if (dict == null || dict.Count == 0) continue;
                    System.Collections.Generic.List<object> deadKeys = null;
                    foreach (System.Collections.DictionaryEntry e in dict)
                    {
                        var del = e.Value as System.Delegate;
                        if (del == null) continue;
                        bool anyLive = false, anyDead = false;
                        foreach (var d in del.GetInvocationList())
                        {
                            var uo = d.Target as UnityEngine.Object;
                            bool zombie = !object.ReferenceEquals(uo, null) && uo == null;
                            if (zombie) anyDead = true; else anyLive = true;
                        }
                        if (anyDead && !anyLive)
                        {
                            if (deadKeys == null) deadKeys = new System.Collections.Generic.List<object>();
                            deadKeys.Add(e.Key);
                        }
                    }
                    if (deadKeys != null)
                        foreach (var k in deadKeys)
                        {
                            dict.Remove(k);
                            removed++;
                            Plugin.Log.LogWarning($"[BLOCK-RESET] removed stale ChildRPC key '{k}' (dead card handler — aborted OnDestroy)");
                        }
                }
            }
            catch { }
            return removed;
        }

        // Scrub every delegate holder a card can hook on a player. Covers the
        // confirmed zombie hosts (Block actions, Gun.ShootPojectileAction,
        // HealthHandler.reviveAction, PlayerCollision.collideWithPlayerAction)
        // plus CharacterData/stats for the same pattern on other cards, and
        // the ChildRPC dictionaries (stale keys abort card Start()s, #39/#40).
        public static int ScrubPlayerDelegates(Player p)
        {
            int n = 0;
            try
            {
                if (p == null || p.data == null) return 0;
                n += ScrubDeadDelegateFields(p.data);
                n += ScrubDeadDelegateFields(p.data.block);
                n += ScrubDeadDelegateFields(p.data.healthHandler);
                n += ScrubDeadDelegateFields(p.data.stats);
                if (p.data.weaponHandler != null)
                    n += ScrubDeadDelegateFields(p.data.weaponHandler.gun);
                n += ScrubDeadDelegateFields(p.GetComponent<PlayerCollision>());
                n += ScrubDeadDelegateFields(p.GetComponent<PlayerVelocity>());
                var childRpc = (UnityEngine.Component)p.GetComponentInChildren<ChildRPC>(true)
                            ?? p.GetComponentInParent<ChildRPC>();
                n += ScrubChildRpcDictionaries(childRpc);
            }
            catch { }
            return n;
        }
        public static void ForceReady(Block b)
        {
            if (b == null) return;
            Resolve();
            try
            {
                if (_fCounter != null && _fCooldown != null)
                {
                    float cd = (float)_fCooldown.GetValue(b);
                    _fCounter.SetValue(b, cd);
                }
            }
            catch { }
        }

    }

    [HarmonyPatch(typeof(Block), "RPCA_DoBlock")]
    class BlockRpcaDoBlockZombieScrubPatch
    {
        // RPCA_DoBlock is the single gateway into IDoBlock for EVERY block
        // path: local TryBlock, remote replicas driven by replicated input,
        // and card-forced CallDoBlock RPCs. Scrubbing zombie delegate entries
        // here guarantees the action chain holds only live subscribers at the
        // moment vanilla invokes it — IDoBlock runs synchronously, so one
        // throwing zombie would otherwise kill `sinceBlock = 0f` (absorption)
        // for that block press. UNGATED: casual in-room rematches hit the
        // same vanilla teardown bug, and removing provably-dead entries is
        // side-effect-free.
        static void Prefix(Block __instance)
        {
            int removed = BlockReflect.ScrubDeadDelegateFields(__instance);
            // Same sweep for this player's Gun + HealthHandler: a zombie
            // Empower deals its ×2 damage via gun.ShootPojectileAction on the
            // first SHOT after a block — scrubbing the gun at block time kills
            // it before it can ever buff a bullet, even if it formed mid-game.
            try
            {
                var data = __instance.GetComponent<CharacterData>();
                if (data != null)
                {
                    if (data.weaponHandler != null)
                        removed += BlockReflect.ScrubDeadDelegateFields(data.weaponHandler.gun);
                    removed += BlockReflect.ScrubDeadDelegateFields(data.healthHandler);
                }
            }
            catch { }
            if (removed > 0)
                Plugin.Log.LogWarning($"[BLOCK-DBG] ZOMBIE-SCRUB removed {removed} dead delegate entry(ies) at block time (an earlier card OnDestroy aborted mid-teardown)");
        }
    }

    [HarmonyPatch(typeof(GM_ArmsRace), "StartGame")]
    class GMArmsRaceStartGameBlockResetPatch
    {
        // Sweep every player's delegate holders — Block actions,
        // Gun.ShootPojectileAction (zombie Empower.Attack = the invisible ×2
        // damage of #25), HealthHandler.reviveAction,
        // PlayerCollision.collideWithPlayerAction (zombie ShieldCharge) — and
        // drop only destroyed-target entries. UNGATED: the scrub is pure
        // repair and the same vanilla bug exists in casual in-room rematches.
        // ForceReady stays competitive-gated: it changes gameplay (block
        // ready at game start) and that behavior was only ever promised for
        // mod-issued rooms.
        //
        // TWO hooks share this body. GM_ArmsRace.StartGame only fires on FRESH
        // room assembly — vanilla's rematch flow (GetRematchYesNo→IDoRematch)
        // calls DoStartGame directly and BYPASSES StartGame, proven in the
        // 7/12 logs: a 7-game ranked 2v2 sitting logged exactly ONE
        // [BLOCK-RESET] line. So games 2+ of every sitting were getting no
        // sweep and no ChildRPC stale-key scrub (the #39/#40 Shield Charge
        // fix), which is why "block/card effects broken" reports kept coming
        // from mid-session games. PlayerManager.ResetCharacters is the
        // rematch-path hook: it fires in IDoRematch right before DoStartGame,
        // i.e. after the teardown that created the zombies and before the new
        // game's card Start() calls re-register ChildRPC keys.
        internal static void RunSweep(string source)
        {
            try
            {
                int dead = 0, players = 0;
                var pm = PlayerManager.instance;
                if (pm != null && pm.players != null)
                {
                    foreach (var p in pm.players)
                    {
                        if (p == null) continue;
                        dead += BlockReflect.ScrubPlayerDelegates(p);
                        players++;
                    }
                }
                bool comp = CompetitiveRoomDetect.IsCompetitiveRoom();
                if (comp)
                {
                    var blocks = UnityEngine.Object.FindObjectsOfType<Block>();
                    if (blocks != null)
                        foreach (var b in blocks) BlockReflect.ForceReady(b);
                }
                Plugin.Log.LogInfo($"[BLOCK-RESET] {source}: scrubbed {dead} zombie delegate entry(ies) across {players} player(s) (competitive={comp})");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[BLOCK-RESET] error: {ex.Message}"); }
        }

        // The __state false->true transition dance that used to live here existed
        // ONLY to protect the old per-game poison latch from GM_ArmsRace.StartGame
        // being re-entered by PlayerJoined on every join (#143). The rewritten
        // protocol has nothing to latch — capability is per-room and immutable, and
        // per-stream state resets at Revive — so the transition detection went with
        // it. The block sweep below is idempotent and wants to run on every call.
        static void Postfix()
        {
            RunSweep("StartGame v2");
        }
    }

    /// <summary>Rematch-path half of the block sweep (see RunSweep comment).
    /// Same-room rematches never fire StartGame; ResetCharacters is the hook
    /// vanilla's IDoRematch DOES call. The sweep is idempotent, so
    /// double-firing alongside StartGame on fresh rooms is fine.
    ///
    /// <para>DEFERRED ONE FRAME, and that is the whole fix for reports #142 and
    /// #144 ("shield charge did nothing all game"). The sweep only removes
    /// entries whose delegate target is a DESTROYED object — but the teardown
    /// it is cleaning up after is <c>CharacterStatModifiers.ResetStats</c>,
    /// which calls <c>Object.Destroy</c> on every card-created host, and Unity
    /// defers that to END OF FRAME. Running synchronously in this Postfix
    /// therefore inspects components that are all still Unity-live, finds
    /// nothing dead, and reports "scrubbed 0" — which is exactly what both
    /// reporters' logs show immediately before the failure. The destroys then
    /// run, <c>ShieldCharge.OnDestroy</c> NREs partway through (its unguarded
    /// parent lookups), and its <c>"ShieldChargeCollide"</c> ChildRPC key
    /// survives. Next game's <c>ShieldCharge.Start</c> does a plain
    /// <c>Dictionary.Add</c> on that key, throws ArgumentException, and aborts
    /// BEFORE its <c>Block.SuperFirstBlockAction += DoBlock</c> on the very
    /// next line — so ordinary blocking still works and the charge never does.
    ///
    /// <para>The previous comment here asserted this hook ran "after the
    /// teardown that created the zombies". It runs after the teardown CALL and
    /// before the teardown's EFFECTS. The FFA rolling-removal path already had
    /// this right — it yields a frame before sweeping, with a comment saying
    /// why — so this is that same choreography, finally applied to the 1v1/2v2
    /// rematch path. Timing budget is ample: IDoRematch starts DoStartGame
    /// immediately, but DoStartGame waits 0.25s, loads a map, then waits
    /// another second before the first pick.</para></summary>
    [HarmonyPatch(typeof(PlayerManager), "ResetCharacters")]
    class PlayerManagerResetCharactersBlockResetPatch
    {
        static void Postfix()
        {
            // Hosted on Plugin.Instance, never on a player or the PlayerManager:
            // those are exactly the objects being torn down, and a coroutine on a
            // destroyed host silently never resumes (#85).
            try { Plugin.Instance.StartCoroutine(SweepNextFrame()); }
            catch { GMArmsRaceStartGameBlockResetPatch.RunSweep("ResetCharacters (rematch, immediate fallback)"); }
        }

        static System.Collections.IEnumerator SweepNextFrame()
        {
            yield return null;   // let Unity run the deferred OnDestroy chain
            GMArmsRaceStartGameBlockResetPatch.RunSweep("ResetCharacters (rematch, post-destroy)");
            // Aug 22 (Mustard-at-card-pick family, fix 3): the rematch teardown
            // can respawn team-colored sprites (vanilla revive re-bakes
            // hpSprite from the SkinBank — HealthHandler.Revive), and no
            // cosmetic path hung off the rematch boundary — OnMatchStarted
            // deliberately fires only at combat start, AFTER the new game's
            // first pick phase. Re-assert body cosmetics here; DelayedApplyAll
            // is idempotent and defers on inactive players, so double-applying
            // with the later match-start pass is safe.
            try { PlayerColorCosmetic.OnRoundStart(); } catch { }
            try { PlayerEffectCosmetic.OnRoundStart(); } catch { }
        }
    }

    // ── Map color override (v1.22) ─────────────────────────────────────────
    // ROUNDS' ArtHandler.Update polls for LeftShift in Update and calls NextArt() which
    // picks a random art from arts[]. For users who own a "color" cosmetic AND have one
    // active, we patch NextArt to instead apply their saved selection. SetSpecificArt
    // already exists and matches by ArtInstance.profile.name.
    //
    // The Awake postfix logs every art profile name on first load — Sid uses this to
    // identify which art-name maps to which shop SKU. Map mappings live in the static
    // dict below; SKUs not in the dict fall through to vanilla cycling.

    [HarmonyPatch(typeof(ArtHandler), "Awake")]
    class ArtHandlerAwakePatch
    {
        static void Postfix(ArtHandler __instance)
        {
            // NOTE: the csproj references Unity.Postprocessing.Runtime directly these
            // days (added for CustomMapColors), so typed PostProcessProfile access is
            // fine — this diagnostic predates that and keeps its reflection harmlessly.
            try
            {
                if (__instance.arts == null) return;
                var profileField = typeof(ArtInstance).GetField("profile",
                    System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                for (int i = 0; i < __instance.arts.Length; i++)
                {
                    var art = __instance.arts[i];
                    if (art == null) continue;
                    object profileObj = profileField?.GetValue(art);
                    string profileName = "<no profile>";
                    if (profileObj is UnityEngine.Object uo) profileName = uo.name;
                    Plugin.Log.LogInfo($"[MAPCOLOR] arts[{i}] profile.name = '{profileName}'");
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] Awake log failed: {ex.Message}"); }
            // Item 8: assert the chromatic-aberration toggle on every art profile
            // as soon as the scene's ArtHandler exists (per-scene coverage).
            try { MapPhysicalColorPatch.ChromaticAberrationSetting.Apply(); } catch { }
            try { MapPhysicalColorPatch.BloomStrengthSetting.Apply(); } catch { }
        }
    }

    // Tints the physical map block renderers per the active custom-color SKU. Each Map
    // instance is spawned per round, so this Postfix runs once per round. We use
    // renderer.material (capital M, auto-clones) so we never poison the shared MapMaterial
    // across maps or rounds. A null MapBlockColor (vanilla SKUs / mapcolor_default) is a no-op.
    // Map block tint per active custom-color SKU. Last attempt set material.color but the map's
    // visible blocks are SpriteRenderers — for those, .color on the renderer is the actual tint
    // (material.color does nothing because the sprite shader samples sprite.color * vertex color).
    // Now sets BOTH SpriteRenderer.color AND multiple known shader properties on the cloned
    // material so we cover sprite, mesh, and any custom-shader renderer ROUNDS uses.
    // Tints map blocks per active custom-color SKU. The walls/floors in ROUNDS are NOT child
    // Renderers of the Map GameObject — they're siblings in the scene OR they use an asset-
    // referenced shared Material (Map.MapMaterial) that we need to tint via a CLONE to not
    // leak across rounds. Strategy here:
    //   1. Clone Map.MapMaterial per-SKU (cached) and reassign it to __instance.MapMaterial
    //      AND to every child Renderer whose sharedMaterial matches the original MapMaterial.
    //   2. Also set SpriteRenderer.color on every sprite child (for moving boxes — these don't
    //      use the shared material).
    // Tints map blocks per active custom-color SKU. Logs verbosely so we can diagnose
    // why walls/floors weren't getting tinted. Strategy:
    //   1. Always tint every SpriteRenderer.color (catches moving boxes + many wall sprites).
    //   2. Walk every renderer in the entire scene (NOT just Map's children) and re-assign
    //      shared materials whose name matches the map material — walls/floors are sometimes
    //      siblings of Map, not children.
    //   3. Cache cloned materials per (sku, original-material-name) so we don't churn.
    // We re-run on every round (Map.Start is per-round). The "glitch" between two patterns
    // probably means another system is reassigning the original material each round — by
    // hooking Start (which fires AFTER ROUNDS' own setup) we should win.
    /// <summary>Shared current-sku holder so the post-process cycle (ArtHandler.NextArt)
    /// and the physical-tint pass (Map.Start + cycle re-apply) agree on which equipped
    /// color is live. Before this existed, Map.Start read the legacy single-value
    /// active_color_sku and the cycle would update post-process alone — walls stuck on
    /// the first sku while color grading rotated through the rest.</summary>
    internal static class MapColorState
    {
        public static string CurrentSku;

        // Bottom-screen toast shown for a few seconds when the player Shift-cycles to a
        // new map skin (so they can find a specific one by name). Read by CompetitiveUI.
        public static string ToastText = "";
        public static float ToastUntil = -999f;
        public static void ShowToast(string name)
        {
            try { ToastText = name ?? ""; ToastUntil = Time.unscaledTime + 2.5f; } catch { }
        }

        /// <summary>Spectator-session teardown (W6, D1 delta f4). The map-skin
        /// auto-cycle is spectator-owned state that must not leak into the local
        /// player's next fighter room (#353 class: state written while spectating
        /// leaking into the next sitting). Supersedes any sleeping deferred tint
        /// pass, clears the live sku (the next Map.Start then falls back to the
        /// player's own equipped sku / vanilla restore), and resets the cycle so a
        /// new sitting starts fresh at the top of the list. The integrator wires
        /// the call into SpectatorSession.EndSession — the one teardown that runs
        /// in EVERY session-end path.</summary>
        public static void OnSpectatorSessionEnd()
        {
            try
            {
                MapPhysicalColorPatch.SupersedePendingTints();
                CurrentSku = null;
                // Same leak as the vanilla fallthrough: the spectator's last skin
                // painted LightCamera's clear, and this seat goes back to the menu
                // where no Map.Start runs to restore it.
                MapPhysicalColorPatch.RestoreVanillaBackdrop("spectator session end");
                ArtHandlerNextArtPatch.ResetSpectatorCycle();
            }
            catch { }
        }
    }

    [HarmonyPatch(typeof(Map), "Start")]
    class MapPhysicalColorPatch
    {
        // Cached tinted materials, keyed by "{sku}|{originalMaterialName}".
        private static readonly Dictionary<string, Material> _matCache = new Dictionary<string, Material>();
        private static bool _loggedTypes;

        // Per-PS vanilla startColor cache. Read once on the first time we touch each
        // ParticleSystem (when its color is still vanilla, before our patch has mutated
        // it); subsequent applies pull from cache so we don't compound the tint by
        // re-reading our own already-multiplied value. Keyed by GetInstanceID — each
        // round's new PS instances populate fresh entries on their first apply.
        private static readonly Dictionary<int, Color> _vanillaPSColorCache = new Dictionary<int, Color>(512);
        // The FULL authored startColor, kept alongside the flattened colour above.
        // `startColor.color` samples a gradient down to one Color (and throws to white
        // on some ROUNDS presets), which is fine for the luminance the tint maths wants
        // but destroys a gradient-mode system on RESTORE — vanilla would come back as a
        // flat colour, permanently (Codex r4 #5). Restores read this; tints read the
        // flattened one.
        private static readonly Dictionary<int, ParticleSystem.MinMaxGradient> _vanillaPSGradientCache =
            new Dictionary<int, ParticleSystem.MinMaxGradient>(512);

        /// <summary>Returns the vanilla startColor for a particle system, caching on
        /// first encounter. Subsequent calls for the same instance return the cached
        /// vanilla value even after we've mutated its current startColor. Falls back
        /// to white if reading the .color property throws (which can happen for
        /// gradient-mode startColors on some ROUNDS art presets).</summary>
        private static Color GetCachedVanillaColor(ParticleSystem ps)
        {
            int id;
            try { id = ps.GetInstanceID(); }
            catch { return Color.white; }
            if (_vanillaPSColorCache.TryGetValue(id, out var cached)) return cached;
            try { _vanillaPSGradientCache[id] = ps.main.startColor; } catch { }
            Color current;
            try { current = ps.main.startColor.color; }
            catch { current = Color.white; }
            _vanillaPSColorCache[id] = current;
            return current;
        }

        // Timestamp of the most recent Map.Start. ROUNDS runs Map.Start INSIDE
        // MapTransition.Move (the coroutine that repositions players each round), and it
        // also fires ArtHandler.NextArt during that same window. So for ~the transition
        // duration after Map.Start, any particle mutation risks the MapTransition NRE
        // (learning #45). NextArt uses this to decide defer-vs-apply-now.
        public static float LastMapStartTime = -999f;

        /// <summary>The authoritative "are we inside MapTransition.Move" test.
        ///
        /// `MapTransition.isTransitioning` is a public static that vanilla sets true
        /// for the whole move and false at the end (decompile: MapTransition.Move).
        /// Every earlier version of this guard inferred the answer from
        /// LastMapStartTime instead, and that stamp is the PREVIOUS map's until the
        /// incoming Map.Start writes it — so every "am I safe to touch particles"
        /// check in this file has been answering FALSE inside the very window it
        /// exists to protect. Keep the stamp test as a second condition (it covers
        /// the tail after isTransitioning clears, which #45 measured at ~0.9s of
        /// move plus a longer round-won animation), but lead with the real signal.</summary>
        public static bool InMapTransition()
        {
            try { if (MapTransition.isTransitioning) return true; } catch { }
            return Time.time - LastMapStartTime < MapTransitionGuardSec;
        }
        // How long after Map.Start we treat the scene as "still transitioning" and must
        // NOT mutate particles. The move itself is ~0.9s; 2.0s is the proven-safe buffer
        // from learning #45 (v1.26.9 cut it to 0.4s and reintroduced the player-freeze /
        // off-screen bug — opponents on the shipped build hit it every round).
        public const float MapTransitionGuardSec = 2.0f;

        // Recolor a particle system's LIVE particles in place (#28, final form).
        // History: a bare Clear(true) killed burst-emission walls until next
        // round (invisible Velvet walls); the v1.28.3 attempt (Clear +
        // Simulate(0, restart) + Play) was supposed to re-fire the burst, but
        // Sid's retest showed burst systems can still come back EMPTY — Unity
        // doesn't reliably re-fire a t=0 burst from a zero-length Simulate. So
        // stop depending on re-emission entirely: rewrite the CURRENT
        // particles' startColor via GetParticles/SetParticles (positions,
        // lifetimes, per-particle alpha untouched) and let main.startColor
        // (set by the caller) cover everything emitted afterwards. Nothing is
        // cleared, so nothing can go invisible — on any emitter type.
        private static ParticleSystem.Particle[] _retintBuf;
        private static void RetintLiveParticles(ParticleSystem ps, Color tinted, Color? sparkle = null, uint tick = 0)
        {
            try
            {
                int live = ps.particleCount;
                if (live <= 0) return;
                if (_retintBuf == null || _retintBuf.Length < live)
                    _retintBuf = new ParticleSystem.Particle[Mathf.Max(live, 256)];
                int n = ps.GetParticles(_retintBuf);
                var rgb = new Color32(
                    (byte)Mathf.Clamp(Mathf.RoundToInt(tinted.r * 255f), 0, 255),
                    (byte)Mathf.Clamp(Mathf.RoundToInt(tinted.g * 255f), 0, 255),
                    (byte)Mathf.Clamp(Mathf.RoundToInt(tinted.b * 255f), 0, 255),
                    0);
                // Premium sparkle: live particles alternate between the base and the
                // glint color by a stable per-particle key (randomSeed), matching the
                // random-between-two-colors look of new emissions.
                Color32 rgb2 = rgb;
                bool twoTone = sparkle.HasValue;
                if (twoTone)
                {
                    var sp = sparkle.Value;
                    rgb2 = new Color32(
                        (byte)Mathf.Clamp(Mathf.RoundToInt(sp.r * 255f), 0, 255),
                        (byte)Mathf.Clamp(Mathf.RoundToInt(sp.g * 255f), 0, 255),
                        (byte)Mathf.Clamp(Mathf.RoundToInt(sp.b * 255f), 0, 255),
                        0);
                }
                for (int i = 0; i < n; i++)
                {
                    Color32 cur = _retintBuf[i].startColor;
                    // tick rotates which particles carry the glint (the twinkle loop);
                    // tick=0 gives the stable emission-matching split. Only 1-in-3
                    // particles glint at a time — a sparse drift, not a strobe.
                    var pick = twoTone && (((_retintBuf[i].randomSeed + tick) % 3u) == 0u) ? rgb2 : rgb;
                    _retintBuf[i].startColor = new Color32(pick.r, pick.g, pick.b, cur.a);
                }
                if (n > 0) ps.SetParticles(_retintBuf, n);
            }
            catch { }
        }

        // ── Post_Main gain compensation (bug 249) ─────────────────────────────
        // Everything MainCamera draws is graded by the 'Default' profile on the
        // Post_Main volume (layer 8): gain (1.00, 0.644, 0.309), postExposure
        // +1.50 EV, contrast +45, ACES. That gain is strongly red-weighted, and it
        // is vanilla — every ROUNDS art absorbs it inside its own HDR grading. Ours
        // cannot: we force LowDefinitionRange, where postExposure does not exist.
        // Uncompensated it pulls every background toward orange, which is a defect
        // and not taste for the skins that are deliberately NEUTRAL — Monochrome
        // (designed 0.28,0.28,0.30) measured (0.78, 0.68, 0.60) on screen, a warm
        // beige. Partially invert the gain so a designed grey renders grey; only
        // partially, because the rest of the scene still carries the warm cast and
        // a fully-corrected sky would not sit with it.
        // MEASURED, not modelled. Post_Main's authored gain is (1.00, 0.644, 0.309),
        // but that is not the transfer the sky actually sees: the correction reaches
        // the screen through the SFSS lightmap and then an ACES tonemap with contrast
        // +45, both of which compress it. Inverting the authored numbers overshot into
        // lavender. These factors were solved from the render instead — Monochrome
        // measured (0.79,0.69,0.61) with no correction and (0.65,0.67,0.83) with the
        // authored inverse, giving the per-channel response, and these are the values
        // that put all three channels on the green channel's level.
        private static readonly Vector3 NEUTRAL_CORRECTION = new Vector3(0.563f, 1.000f, 1.277f);
        private const float GAIN_COMP_STRENGTH = 1.00f;
        // Full correction from this luminance up; proportionally less below it. The
        // warm cast is proportional to brightness, so a very dark neutral does not need
        // correcting and must not GET it — Charcoal already measured a 0.034 spread on
        // its own and a flat correction pushed it to 0.116 blue.
        private const float NEUTRAL_LUM_FULL = 0.35f;

        /// <summary>Pre-divide a colour by Post_Main's red-weighted gain (normalised
        /// so overall brightness is unchanged), SCALED BY HOW NEUTRAL THE COLOUR IS.
        ///
        /// The rule this encodes: a colour the designer made GREY must render grey; a
        /// colour they made saturated keeps its own hue and the scene's warm cast with
        /// it. Monochrome (0.28,0.28,0.30), Charcoal (0.07,0.07,0.08) and Platinum
        /// (0.24,0.26,0.29) are deliberately neutral and were rendering as warm beige
        /// — measured (0.77,0.67,0.60) for Mono — purely because Post_Main's
        /// gain (1.00, 0.644, 0.309) tints everything MainCamera draws. Correcting
        /// every skin equally would have cooled the 20 coloured ones too, which nobody
        /// asked for; correcting in proportion to (1 - chroma) fixes exactly the skins
        /// that are supposed to be grey and leaves Magma/Abyss/Soft within a percent
        /// of where they were.
        ///
        /// chroma = (max-min)/max, so 0 is a perfect grey. Full correction at 0,
        /// none from 0.4 up (Soft sits at 0.36, Magma at 0.91).</summary>
        /// APPLIED EXACTLY ONCE PER PIXEL (Codex r3 #4). The scene composites as
        /// sprite x lightmap, so correcting the surface colour AND the SFSS light
        /// applied the inverse gain twice and over-shot into blue — Platinum measured
        /// -0.20 skew. The correction now lives on the two things that each cover a
        /// path exactly once: the SFSS light/ambient (which multiplies every lit
        /// sprite) and the LightCamera clear (which the lightmap never touches).
        /// Surface particle colours are left alone.
        ///
        /// HEADROOM RULE. Correcting a neutral for a 0.309 blue gain needs blue at
        /// 3.2x, and a channel stops at 1.0 — so full correction is only possible for
        /// colours dark enough to have the room. Rather than clip (which railed
        /// Monochrome to pure white, neutral only by accident) or cap (which dimmed
        /// the SFSS light and rendered Mono and Charcoal near-black), back the
        /// correction off to exactly the strength that FITS: never clip, never
        /// brighten past 1.0, and take as much neutrality as the headroom allows.
        /// Dark skins get almost all of it, bright ones get what is physically
        /// available. One rule, no tuned ceiling.
        /// <summary>True when the SFSS lighting pass is running. With it OFF the light
        /// carries no correction (SFRenderer is disabled and the shader globals are
        /// pinned white), so the SURFACE colours have to carry it instead — otherwise
        /// "disable map lighting" brings the warm cast straight back (Codex r4 #6).
        /// Exactly one of the two paths corrects, never both.</summary>
        internal static bool MapLightingActive()
        {
            try { return Plugin.MapLightingEnabled == null || Plugin.MapLightingEnabled.Value; }
            catch { return true; }
        }

        /// <summary>Correct a SURFACE colour only when the light is not doing it.</summary>
        private static Color CompensateSurfaceIfUnlit(Color c)
        {
            return MapLightingActive() ? c : CompensatePostMain(c);
        }

        private static Color CompensatePostMain(Color c)
        {
            try
            {
                float mx = Mathf.Max(c.r, Mathf.Max(c.g, c.b));
                float mn = Mathf.Min(c.r, Mathf.Min(c.g, c.b));
                float chroma = mx > 0.001f ? (mx - mn) / mx : 0f;
                float lum = 0.299f * c.r + 0.587f * c.g + 0.114f * c.b;
                float strength = GAIN_COMP_STRENGTH
                                 * Mathf.Clamp01(1f - chroma * 2.5f)          // only near-neutrals
                                 * Mathf.Clamp01(lum / NEUTRAL_LUM_FULL);     // only bright enough ones
                if (strength <= 0.001f) return c;

                float fr = NEUTRAL_CORRECTION.x;
                float fg = NEUTRAL_CORRECTION.y;
                float fb = NEUTRAL_CORRECTION.z;

                // Largest strength s for which no channel exceeds 1.0. Each channel is
                // c * Lerp(1, f, s), linear in s, so solve per channel and take the min.
                float fit = strength;
                fit = Mathf.Min(fit, FitStrength(c.r, fr, strength));
                fit = Mathf.Min(fit, FitStrength(c.g, fg, strength));
                fit = Mathf.Min(fit, FitStrength(c.b, fb, strength));
                if (fit <= 0.001f) return c;

                return new Color(c.r * Mathf.Lerp(1f, fr, fit),
                                 c.g * Mathf.Lerp(1f, fg, fit),
                                 c.b * Mathf.Lerp(1f, fb, fit), c.a);
            }
            catch { return c; }
        }

        /// <summary>Strength at which `value * Lerp(1, factor, s)` reaches 1.0,
        /// clamped to [0, want]. Returns `want` when the channel never gets there.</summary>
        private static float FitStrength(float value, float factor, float want)
        {
            if (value <= 0.0001f || factor <= 1f) return want;      // shrinking channels cannot clip
            float atWant = value * Mathf.Lerp(1f, factor, want);
            if (atWant <= 1f) return want;
            float s = ((1f / value) - 1f) / (factor - 1f);
            return Mathf.Clamp(s, 0f, want);
        }

        // ── Backdrop vs wall classification (bug 249) ─────────────────────────
        // BACKDROP = "the background camera draws it", i.e. the system's layer is in
        // that camera's cullingMask. Nothing else is behind the map: LightCamera's
        // mask is 512 (layer 9) and MainCamera's 2522423 excludes layer 9, so layer 9
        // is exactly the set that renders under everything, and every other art part
        // (Sky, SkyBG, Paint, Samsung, 'Purple pink', NightSky, the Rainbow parts) is
        // layer 14 and is drawn by MainCamera in FRONT — those are the skin's walls
        // and keep the designed primary/secondary two-tone.
        //
        // An earlier revision classified by renderer bounds ("wider than the ~71-unit
        // play area = sky"). Codex killed it, correctly, on two grounds: every
        // observed system measures 91-130 units so the wall branch was DEAD (a silent
        // removal of the two-tone wall feature), and 'Purple pink' is a layer-14
        // foreground part that measures 130x109 and would have been mislabelled. The
        // camera mask is the ground truth the bounds were only a proxy for, and it
        // does not breathe frame to frame the way a live-particle AABB does — which
        // also removes the between-round colour flicker risk that failed approaches
        // #1 and #2 (see the history above) were about.
        private static int _backdropLayerMask = 0;
        private static int _backdropMaskThisPass = 0;
        /// <summary>The recorded background-camera culling mask (0 until the first
        /// tint pass has seen a camera). MapSkinEffects derives its render layer
        /// from this instead of hardcoding layer 9.</summary>
        internal static int BackdropLayerMask => _backdropLayerMask;
        private static readonly HashSet<int> _loggedClass = new HashSet<int>();

        /// <summary>Records the culling mask of the camera(s) painting the canvas, so
        /// the backdrop set is read from the scene instead of hardcoded. Accumulated
        /// WITHIN a pass and then REPLACED, never OR'd across the session (Codex r2
        /// #7): a camera that exists only in one scene — a menu rig, another mod's —
        /// would otherwise widen the mask permanently and start labelling layer-14
        /// walls as backdrop for the rest of the process.</summary>
        private static void NoteBackdropCamera(Camera cam)
        {
            try { if (cam != null) _backdropMaskThisPass |= cam.cullingMask; } catch { }
        }

        private static void CommitBackdropMask()
        {
            if (_backdropMaskThisPass != 0 && _backdropMaskThisPass != _backdropLayerMask)
            {
                _backdropLayerMask = _backdropMaskThisPass;
                _loggedClass.Clear();     // re-log the classification under the new mask
                Plugin.Log.LogInfo($"[MAPCOLOR-CLASS] backdrop layer mask = {_backdropLayerMask}");
            }
            else if (_backdropMaskThisPass != 0)
            {
                _backdropLayerMask = _backdropMaskThisPass;
            }
        }

        private static bool IsBackdropSystem(ParticleSystem ps)
        {
            try
            {
                // Fall back to layer 9 only if ApplyCameraBackground has not run yet;
                // it runs before every tint pass, so this is a first-frame guard.
                int mask = _backdropLayerMask != 0 ? _backdropLayerMask : (1 << 9);
                bool verdict = ((1 << ps.gameObject.layer) & mask) != 0;
                int id = ps.GetInstanceID();
                if (_loggedClass.Add(id))
                    Plugin.Log.LogInfo($"[MAPCOLOR-CLASS] '{ps.gameObject.name}' layer={ps.gameObject.layer} → {(verdict ? "BACKDROP" : "wall")}");
                return verdict;
            }
            catch { return false; }
        }

        // Cap a lifted color's brightest channel so bright hues can't blow out
        // into HDR bloom (Sid: platinum/gilded were "blindingly shiny" — silver
        // × 1.6 lift = 1.4+ per channel = nuclear bloom). 1.15 keeps a gentle
        // glow for dark hues (Magma's molten look) without the white-out.
        private static Color CapBrightness(Color c, float maxChannel = 1.15f)
        {
            float mx = Mathf.Max(c.r, Mathf.Max(c.g, c.b));
            if (mx <= maxChannel || mx <= 0f) return c;
            float s = maxChannel / mx;
            return new Color(c.r * s, c.g * s, c.b * s, c.a);
        }

        // Push a color away from grey toward full saturation by `mult` (1 = unchanged).
        // Keeps luminance roughly stable so brightness is set by the lift, not this.
        private static Color SaturateColor(Color c, float mult)
        {
            float g = c.r * 0.299f + c.g * 0.587f + c.b * 0.114f; // perceived grey level
            return new Color(
                Mathf.Clamp01(g + (c.r - g) * mult),
                Mathf.Clamp01(g + (c.g - g) * mult),
                Mathf.Clamp01(g + (c.b - g) * mult),
                c.a);
        }

        static void Postfix(Map __instance)
        {
            LastMapStartTime = Time.time;
            // v1.32 item 7: lighting/shadow disable settings survive scene reloads —
            // fresh SFRenderer instances spawn with vanilla state every map load.
            // Field flips are transition-safe (not particle mutations), so this
            // does NOT need the MapTransitionGuardSec defer.
            RenderPerfSettings.Apply();
            ChromaticAberrationSetting.Apply();
            BloomStrengthSetting.Apply();
            // Use whatever sku is currently live after the cycle (ArtHandlerNextArtPatch sets
            // MapColorState.CurrentSku on every cycle advance). Fall back to the legacy single
            // field when the cycle hasn't run yet (fresh map load before any Shift press).
            string sku = MapColorState.CurrentSku;
            if (string.IsNullOrEmpty(sku))
                sku = ApiClient.CachedPlayerStats?.active_color_sku;
            if (string.IsNullOrEmpty(sku) || !CustomMapColors.IsCustomSku(sku))
            {
                // Vanilla/default skin active — un-tint the persistent sky object +
                // the background camera clear so a previous custom skin's backdrop
                // doesn't linger. Restoring the clear is what hands the canvas back
                // to the vanilla art's own grading (which recolours it via hueShift).
                // Map.Start runs INSIDE MapTransition.Move, so the sky restore must
                // be deferred — RestoreVanillaBackdrop handles the split and ends
                // with RenderPerfSettings.ApplyBackdrop so a lighting-off flat
                // backdrop still wins over the restored raw dark sky.
                RestoreVanillaBackdrop("map start, vanilla sku");
                return;
            }
            // Defer past the transition before touching particles (see MapTransitionGuardSec).
            // Hosted on the persistent Plugin object, NOT the Map — the Map can be destroyed
            // mid-transition, which would kill a Map-hosted coroutine before it applies.
            ScheduleDeferredTints(sku);   // its apply ends with ApplyBackdropNow
        }

        // Schedule the wall/atmosphere particle tint to run AFTER the MapTransition window.
        // Always hosted on Plugin.Instance so it survives Map destruction during the move.
        //
        // COALESCED (bug 221/222 follow-up, shaped by review round 1): Map.Start's
        // postfix AND the per-round NextArt prefix both schedule a deferred pass
        // for the SAME map load, so every point transition ran the full
        // renderer+particle walk TWICE back-to-back — measured 324 passes over
        // 159 transitions in the bug-221 log and 154/73 in bug-217's, on every
        // client with a map skin, at exactly the transition moments players
        // report hitches. One pending pass suffices — but three rules from the
        // review are load-bearing:
        //  * EVERY request pushes the shared not-before deadline past ITS OWN
        //    transition window (r1 HIGH: map B starting <2s after map A must not
        //    inherit A's earlier deadline — a pass firing inside B's guard is
        //    the proven MapTransition mid-move NRE, #85);
        //  * a superseded GENERATION exits before applying (r1 find 4: an
        //    A→B→A Shift cycle otherwise applies A twice);
        //  * the slot claim carries a TTL (r1 find 3: the persistent host can
        //    be destroyed mid-wait, killing the coroutine before it clears the
        //    slot — #16/#270c class; a wedged claim self-heals instead of
        //    suppressing deferred tints for the rest of the process).
        private static string _pendingTintSku;
        private static int _pendingTintGen;
        private static float _tintNotBefore;              // Time.time deadline (scaled, matches the guard convention)
        private static int _pendingTintHostId;            // owner of the claim — see ScheduleDeferredTints

        /// <summary>An IMMEDIATE tint apply (the mid-round manual-Shift branch)
        /// supersedes whatever deferred pass is pending — review r2 MEDIUM: a
        /// Shift B then back to A while an A coroutine sleeps in the deadline
        /// tail otherwise passes both guards and walks the full tint twice.
        /// The immediate apply reflects the CURRENT selection by definition,
        /// so any pending pass is stale the moment it runs.</summary>
        public static void SupersedePendingTints()
        {
            _pendingTintGen++;
            _pendingTintSku = null;
        }

        public static void ScheduleDeferredTints(string sku)
        {
            if (string.IsNullOrEmpty(sku) || !CustomMapColors.IsCustomSku(sku)) return;
            float notBefore = Time.time + MapTransitionGuardSec;
            if (notBefore > _tintNotBefore) _tintNotBefore = notBefore;
            var host = Plugin.Instance;
            if (host == null) return;
            // Ownership, not a wall-clock TTL (Codex r5 #5). Plugin.Instance is a
            // HideAndDontSave object ROUNDS' scene changes destroy and we respawn; its
            // coroutines die with it. A TTL was wrong in both directions — too long
            // stranded a real request behind a dead claim for up to 15s (the map simply
            // never got tinted), too short let two coroutines paint at once. The claim
            // now belongs to the host that made it, so a replacement host is never
            // blocked and the old host's coroutine bows out on the generation check.
            int hostId = host.GetInstanceID();
            bool samePending = string.Equals(_pendingTintSku, sku, StringComparison.OrdinalIgnoreCase)
                && _pendingTintHostId == hostId;
            if (samePending) return;   // the pending pass now honors the pushed deadline
            _pendingTintSku = sku;
            _pendingTintHostId = hostId;
            int gen = ++_pendingTintGen;
            host.StartCoroutine(DelayedApplyTints(sku, gen));
        }

        private static System.Collections.IEnumerator DelayedApplyTints(string sku, int gen)
        {
            // Wait for the LATEST requested deadline — it is pushed while we
            // sleep whenever another map load requests the same sku. ALSO
            // re-check the transition state at wake (Codex v1.39.3 r1 find 1):
            // the deadline is only pushed by NextArt CALLS, and MapTransition
            // can begin Move up to ~0.1s before its switchMapEvent fires
            // NextArt — a deadline expiring inside that window used to apply
            // particles mid-Move (the #45/#85 stall class). InMapTransition()
            // covers both the live flag and the 2s post-Map.Start tail, and
            // always clears, so this cannot wedge the pass.
            while (Time.time < _tintNotBefore || InMapTransition()) yield return null;
            // Superseded generation: a later Shift claimed the slot (including
            // an A→B→A cycle). The newest coroutine owns the slot AND the
            // apply — exit before the current-sku check, never apply.
            if (gen != _pendingTintGen) yield break;
            _pendingTintSku = null;
            // Stale-apply guard: if the player Shift-cycled again during the wait,
            // this scheduled apply is for an OLD sku — proven in Sid's log
            // ("burgundy" tints landing right after "pine" was selected). Skip;
            // the newer selection has its own apply in flight.
            if (!string.Equals(MapColorState.CurrentSku, sku, StringComparison.OrdinalIgnoreCase))
            {
                Plugin.Log.LogInfo($"[MAPCOLOR] skipped stale deferred tint for {sku} (current={MapColorState.CurrentSku})");
                yield break;
            }
            ApplyPhysicalTintsForSku(null, sku); // null → finds the active Map itself
        }

        /// <summary>Apply the SKU's wall / sprite / particle tints to the current scene. Shared
        /// between Map.Start (one-shot on map load) and the Shift cycle (invoked after each
        /// NextArt call, so walls and post-process stay in sync when the player cycles).
        /// Falls through gracefully for vanilla skus and null.</summary>
        public static void ApplyPhysicalTintsForSku(Map mapInstance, string sku)
        {
            if (mapInstance == null)
            {
                // Shift cycle path — find the active Map to operate on.
                mapInstance = UnityEngine.Object.FindObjectOfType<Map>();
                if (mapInstance == null) return;
            }
            try
            {
                if (string.IsNullOrEmpty(sku) || !CustomMapColors.IsCustomSku(sku))
                {
                    return;
                }
                Color? tintN = CustomMapColors.GetMapBlockColor(sku);
                if (!tintN.HasValue)
                {
                    Plugin.Log.LogInfo($"[MAPCOLOR] Map.Start sku={sku} but no MapBlockColor → SpriteRenderer-only path");
                }
                Color c = tintN ?? Color.white;

                // Tint ONLY the walls (OutOfBounds particle systems, Step 3 below) and the
                // art-instance atmosphere particles (Step 4). Previously also tinted every
                // SpriteRenderer under Map/* (the 49 moving physics boxes) and every scene
                // SpriteRenderer that wasn't a player/bullet/UI — both passes also caught
                // the brown boxes and their background variants, making the whole map read
                // as a monotone color block. User feedback: "It should only be the map
                // background and the two wall colors" — i.e. just walls + atmosphere.
                if (!tintN.HasValue) return;
                // v1.26.9 final approach — MULTIPLY vanilla startColor by our preset
                // tint instead of replacing it. Vanilla has many particle systems with
                // subtly-different per-PS colors layered to produce texture; multiplying
                // preserves that variation while shifting the overall hue into our preset.
                //
                // Cache vanilla colors per PS instance ID — the FIRST read captures the
                // vanilla value (before our patch has mutated it); subsequent reads on
                // re-apply pull from the cache so we don't compound our tint by re-reading
                // our own already-tinted value and re-multiplying.
                //
                // History of failed approaches (kept here so I don't repeat them):
                //   1. Per-PS alternation by enumeration index — flashed between rounds.
                //   2. Stable-sort by position — still flashed (random map per round).
                //   3. MinMaxGradient TwoColors — gameplay-wide shimmer (per-particle).
                //   4. Single primary on walls — flat (lost vanilla variation).
                //   5. No mutation, post-process only — vanilla colors leaked through.
                // Walls: kill the texture-flicker via STABLE draw order (v1.26.10).
                // The OutOfBounds boundary is built from several OVERLAPPING semi-transparent
                // particle systems. Unity sorts transparent particles by camera distance; when
                // overlapping systems sit at ~equal depth their relative draw order flips frame to
                // frame, so the visible sprite alternates between systems — the "flickering between
                // textures" the user reported (DISTINCT from per-particle brightness shimmer, which
                // is vanilla and fine). It's invisible in vanilla because the systems carry distinct
                // colors that read as depth, and it vanishes with "1 solid object" because a single
                // draw can't fight itself. Fix without collapsing to one object: give each system a
                // distinct, STABLE sortingFudge so the inter-system draw order is fixed every frame.
                // Assignment is ordered by transform path (deterministic across frames AND rounds)
                // so the order never changes mid-session. We also two-tone the colors (primary /
                // secondary by path parity) so both colors land in the walls as requested.
                // ── v1.29 round 6: the "OutOfBounds/" pass is RETIRED (learning #118).
                // Sid's WALLDIAG log proved those 14 systems are the two PLAYERS'
                // out-of-bounds WARNING effects (OutOfBounds/Particles/Wall, Burst,
                // ShieldWall, Warning... — 7 per player, playing=False by design,
                // played by OutOfBoundsHandler only near the boundary). They were
                // never map walls: the old Clear/Restart code force-played them into
                // permanent visibility (our "colored border beams"), and clearing
                // them mid-shift was the ACTUAL invisible-walls bug. They now stay
                // vanilla (red warnings, gameplay-readable). The visible "walls" of
                // a skin are the base art's glow slabs — the atmosphere pass below
                // carries the PRIMARY/SECONDARY two-tone there instead.
                // ArtInstance atmosphere particles — THE VISIBLE WALLS of a skin
                // (learning #118): the base art's glow slabs hugging the map
                // geometry. They now carry the skin's PRIMARY/SECONDARY two-tone
                // (alternating per system) while the BACKGROUND is carried by the
                // SFSS light + ambient. That's the wall/background separation Sid
                // asked for: walls get their designed colors, backdrop its own.
                int artParts = 0;
                _twinkleSystems.Clear();
                try
                {
                    Color secondary = CustomMapColors.GetSecondaryColor(sku);
                    string baseArt = CustomMapColors.GetBaseArt(sku);
                    var ah = ArtHandler.instance;
                    if (ah != null && ah.arts != null)
                    {
                        var partsField = typeof(ArtInstance).GetField("parts",
                            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                        var profileField = typeof(ArtInstance).GetField("profile",
                            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                        // ⚠ ARTS SHARE PARTICLE SYSTEMS — the reason every skin's background
                        // went flat two seconds into every round (bug 249). Parsed from
                        // level0, ArtInstance.parts is:
                        //   arts[0] RainbowSeq [Clouds*, RainbowSequence]
                        //   arts[1] Rainbow    [Clouds*, Rainbow, ...]
                        //   arts[2] Sweden     [Swe, den, Clouds*]
                        //   arts[3] Gold       [Samsung, NightSky, Clouds*]
                        //   arts[4] Soviet     [Clouds*, Purple pink]
                        //   arts[5] Poison     [Clouds*, Poison, PoisonBG]
                        //   arts[6] Gold       [Clouds*, NightSky, Gold]
                        //   arts[7] Sky        [FireClouds*, Sky, SkyBG]
                        //   arts[8] Poison     [Paint, PoisonBG, FireClouds*]
                        // (* = layer 9, the ONLY layer the background camera renders; every
                        // other part is layer 14 and is drawn by MainCamera in front.)
                        // `Clouds` belongs to seven arts and `FireClouds` to two, so calling
                        // TogglePart(false) on a non-base art SetActive(false)'d the base
                        // art's own layer-9 renderer. Nothing ever switched it back on, so
                        // after this pass the background camera had NO renderer at all and
                        // the canvas was left bare — log-proven by the same system reporting
                        // size=106x85 on one pass and size=0x0 on the next.
                        //
                        // Also: arts[] has duplicate profile names (arts[3]/arts[6] 'Gold',
                        // arts[5]/arts[8] 'Poison') and ROUNDS' SetSpecificArt(string) BREAKS
                        // on the first match, so only the first same-named art is ever live.
                        // Claim that one as base; disable the others' EXCLUSIVE systems only.
                        var baseSystems = new HashSet<int>();
                        ArtInstance baseArtInstance = null;
                        foreach (var art in ah.arts)
                        {
                            if (art == null) continue;
                            try
                            {
                                var prof = profileField?.GetValue(art) as UnityEngine.Object;
                                if (prof == null || string.IsNullOrEmpty(baseArt)
                                    || !string.Equals(prof.name, baseArt, StringComparison.OrdinalIgnoreCase)) continue;
                            }
                            catch { continue; }
                            baseArtInstance = art;
                            var bp = partsField?.GetValue(art) as ParticleSystem[];
                            if (bp != null)
                                foreach (var ps in bp) if (ps != null) baseSystems.Add(ps.GetInstanceID());
                            break;   // first match only — that is the one SetSpecificArt lit
                        }

                        // If the base art could not be resolved (reflection failure, a
                        // renamed profile), DO NOT run the disable pass: with no protected
                        // set every system would be switched off and the background would
                        // go black. Leaving the arts as ROUNDS left them is the safe miss.
                        bool canDisable = baseArtInstance != null && baseSystems.Count > 0;
                        if (!canDisable)
                            Plugin.Log.LogWarning($"[MAPCOLOR] base art '{baseArt}' unresolved or empty for {sku} — skipping the art-disable pass (never blank the background on a lookup miss)");
                        foreach (var art in ah.arts)
                        {
                            if (art == null || !canDisable) continue;
                            var partsArr = partsField?.GetValue(art) as ParticleSystem[];
                            if (partsArr == null) continue;
                            // Only the SKU's base art should paint the sky. Any other art left
                            // playing (e.g. the Rainbow arts) bleeds purple/pink into the
                            // background — Magma's "sky is purple and pink". Turn the others
                            // off, but NEVER a system the base art also owns.
                            bool isBase = ReferenceEquals(art, baseArtInstance);
                            if (!isBase)
                            {
                                foreach (var ps in partsArr)
                                {
                                    if (ps == null) continue;
                                    if (baseSystems.Contains(ps.GetInstanceID())) continue;  // shared with the live art
                                    try { ps.gameObject.SetActive(false); }
                                    catch (Exception tx) { Plugin.Log.LogWarning($"[MAPCOLOR] art off failed: {tx.Message}"); }
                                }
                                continue;
                            }
                            // Premium sparkle skins: the atmosphere particles ARE the visible
                            // glitter (the wall border systems are thin edge strips), so they
                            // get the full-brightness two-color glint instead of the dim haze.
                            Color? atmoSparkle = CustomMapColors.GetSparkleColor(sku);
                            for (int i = 0; i < partsArr.Length; i++)
                            {
                                var ps = partsArr[i];
                                if (ps == null) continue;
                                try
                                {
                                    Color vanilla = GetCachedVanillaColor(ps);
                                    float lum = vanilla.r * 0.299f + vanilla.g * 0.587f + vanilla.b * 0.114f;
                                    var main = ps.main;
                                    if (atmoSparkle.HasValue && !IsBackdropSystem(ps))
                                    {
                                        // Premium: primary-colored slabs at SUB-BLOOM brightness
                                        // (Sid: "way too flashy") + a subtle glint. The visible
                                        // twinkle comes from the shimmer loop re-rolling which
                                        // particles are glinted a few times a second.
                                        Color baseHue = SaturateColor(c, 1.15f);
                                        float gLift = 0.62f + 0.28f * Mathf.Clamp01(lum);
                                        // Both endpoints take the unlit correction, once, AFTER
                                        // they are final — the twinkle loop re-applies these exact
                                        // colours every 1.6s, so an uncorrected pair would keep
                                        // repainting the warm cast back in with lighting off
                                        // (Codex r5 #2).
                                        Color gA = CompensateSurfaceIfUnlit(CapBrightness(
                                            new Color(baseHue.r * gLift, baseHue.g * gLift, baseHue.b * gLift, vanilla.a), 0.85f));
                                        Color glintHue = Color.Lerp(gA, SaturateColor(atmoSparkle.Value, 1.0f), 0.5f);
                                        Color gB = CompensateSurfaceIfUnlit(CapBrightness(
                                            new Color(glintHue.r * 1.15f, glintHue.g * 1.15f, glintHue.b * 1.15f, vanilla.a), 0.95f));
                                        main.startColor = new ParticleSystem.MinMaxGradient(gA, gB);
                                        RetintLiveParticles(ps, gA, gB);
                                        _twinkleSystems.Add(new TwinkleEntry { ps = ps, baseColor = gA, glintColor = gB });
                                    }
                                    else if (IsBackdropSystem(ps))
                                    {
                                        // BACKDROP SLAB (bug 249). These systems are 91-130
                                        // world units across against a ~71-unit play area
                                        // (OutOfBoundsHandler x span [-35.56, 35.56]) — they
                                        // ARE the sky, not walls, and painting them with the
                                        // wall pair is what "spectators see a different map
                                        // skin background than the map skin has set" actually
                                        // was. Measured: skin Soft put its SECONDARY (peach
                                        // 0.92,0.66,0.48) on the 115x95 'Sky' slab, saturated
                                        // x1.30 and lifted to 0.89 -> #DF925D, a salmon
                                        // covering the whole screen. 17 of the 23 skins in the
                                        // spectator cycle have a warm primary or secondary,
                                        // which is the reported "8 out of 10 are pinkish".
                                        // Now they carry the skin's DESIGNED background, at
                                        // the same exposure as the canvas behind them so the
                                        // two agree, two-toned toward the accent so the
                                        // layered depth Sid asked for survives.
                                        Color bgBase = CustomMapColors.GetBackgroundColor(sku) ?? c;
                                        Color layer = (i % 2 == 0)
                                            ? bgBase
                                            : Color.Lerp(bgBase, secondary, 0.40f);
                                        Color hue = SaturateColor(layer, 1.10f);
                                        // Backdrop brightness, measured on this seat, not guessed.
                                        // Everything these slabs draw is graded by Post_Main
                                        // (layer 14): postExposure +1.50 EV = x2.83, contrast
                                        // +45, ACES. At the old 0.45-0.80 band a designed
                                        // (0.62,0.50,0.40) came out of the tonemapper at
                                        // (0.87,0.73,0.58) — a washed cream. The 0.19-0.34 band
                                        // lands it on the authored value after that x2.83.
                                        float lift = (0.19f + 0.15f * Mathf.Clamp01(lum))
                                                     * CustomMapColors.GetBackgroundExposureMultiplier(sku);
                                        Color tinted = CapBrightness(CompensateSurfaceIfUnlit(
                                            new Color(hue.r * lift, hue.g * lift, hue.b * lift, vanilla.a)), 1.0f);
                                        main.startColor = new ParticleSystem.MinMaxGradient(tinted);
                                        RetintLiveParticles(ps, tinted);
                                    }
                                    else
                                    {
                                        // Two-tone: even systems PRIMARY, odd SECONDARY — the
                                        // designed wall pair, independent of the backdrop.
                                        // Brightness kept BELOW the bloom threshold (Sid: glow
                                        // "right above 0") — the faint remaining glow comes
                                        // from the neutered bloom pass, not HDR colors.
                                        Color layer = (i % 2 == 0) ? c : secondary;
                                        Color hue = SaturateColor(layer, 1.30f);
                                        float lift = 0.70f + 0.30f * Mathf.Clamp01(lum);
                                        Color tinted = CapBrightness(CompensateSurfaceIfUnlit(
                                            new Color(hue.r * lift, hue.g * lift, hue.b * lift, vanilla.a)), 1.0f);
                                        main.startColor = new ParticleSystem.MinMaxGradient(tinted);
                                        RetintLiveParticles(ps, tinted);
                                    }
                                    // Green-hunt diagnostic: name every art part with its vanilla
                                    // + applied color so any hue that still looks wrong on screen
                                    // is attributable to a specific object from one log line.
                                    //
                                    // BOUNDED since report #359. The captured bundle holds 216
                                    // [MAPCOLOR-ART] lines, but the bundle MIRRORS every write into
                                    // two captured sections, so that is 108 emissions counted twice
                                    // — the same double-count this batch corrected in the freeze
                                    // counters, in the same report. The cap is not sized against 216;
                                    // it is sized so one map's worth of parts is attributable and no
                                    // more. The hunt it was built for is over, and a per-part,
                                    // per-map-load line with no ceiling is a standing cost in every
                                    // player's bundle. The budget is per PROCESS — nothing calls
                                    // ResetDiag on this key — so it covers roughly one map's worth
                                    // of parts after launch: enough to attribute a wrong hue, not
                                    // enough to drown the report it is attached to. Reserve BEFORE
                                    // building the message; the interpolation is the expensive half.
                                    try
                                    {
                                        if (VanillaFixSupport.TryReserveDiag("mapcolor-art", 24))
                                        {
                                            var psr0 = ps.GetComponent<ParticleSystemRenderer>();
                                            var b = psr0 != null ? psr0.bounds.size : Vector3.zero;
                                            Color applied = ps.main.startColor.color;
                                            VanillaFixSupport.WriteReservedDiag($"[MAPCOLOR-ART] part='{ps.gameObject.name}' vanilla=#{(int)(vanilla.r*255):X2}{(int)(vanilla.g*255):X2}{(int)(vanilla.b*255):X2} applied=#{(int)(Mathf.Clamp01(applied.r)*255):X2}{(int)(Mathf.Clamp01(applied.g)*255):X2}{(int)(Mathf.Clamp01(applied.b)*255):X2} size={b.x:F0}x{b.y:F0}");
                                        }
                                    }
                                    catch { }
                                }
                                catch { }
                                artParts++;
                            }
                        }
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] art-particle tint failed: {ex.Message}"); }

                // v1.29: tint the ACTUAL sky. ArtHandler carries a dedicated
                // m_background GameObject that the particle passes never touched —
                // its vanilla (blue-leaning) art is what kept showing through and
                // made even green skins read blue once the colorFilter stopped
                // masking it (Sid: "Pine/Forest turned blue").
                int skyParts = TintArtBackground(sku);
                // And the flat backdrop itself: color-clearing cameras + per-map
                // backdrop quads (learning #116 v2 — MainCam clears Depth only, so
                // whatever is under it paints the sky).
                ApplyCameraBackground(sku);
                // The strongest lever: SFSS light + ambient carry the sky and the
                // shadow beams (learning #116 v3).
                ApplyLighting(sku);
                // Ambient effect layer (embers / rain) — its own persistent emitter
                // on the backdrop layer, never a Map-owned system (Aug 23 pack).
                MapSkinEffects.Apply(sku);

                EnsureTwinkleLoop();
                Plugin.Log.LogInfo($"[MAPCOLOR] sku={sku}: {artParts} two-tone wall slab system(s) + {skyParts} sky renderer(s) + lighting; OOB player-warning effects untouched (vanilla)");
                LogBackgroundLayerState(sku);
                LogLiveColorGrading(sku, "settled");
                // LAST, always: a lighting-off flat backdrop must win over the tint
                // we just applied, and this is the only pass guaranteed to be the
                // settled one (Codex r2 #2).
                RenderPerfSettings.ApplyBackdropNow();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] Map tint failed: {ex.Message}"); }
        }

        private static bool _loggedScenePaths;

        // ── Background-layer proof line (bug 249 diagnostic) ──────────────────
        // `size=0x0` on a ParticleSystemRenderer is ambiguous (an emitter with no
        // live particles reads the same as a disabled one), and that ambiguity is
        // exactly what hid the shared-particle-system bug for four releases. Log
        // activeInHierarchy + particleCount instead, for the seven children of
        // ArtHandler.m_background — the only renderers the background camera can
        // draw. If every one reads active=False, the canvas is bare and whatever
        // colour is on screen came from the camera clear plus the grading.
        // Emitted once per sku so a spectator session's log stays readable.
        private static readonly HashSet<string> _loggedL9Skus = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        private static void LogBackgroundLayerState(string sku)
        {
            try
            {
                if (!_loggedL9Skus.Add(sku)) return;
                var ah = ArtHandler.instance;
                var bgGO = ah != null ? ah.m_background : null;
                if (bgGO == null) { Plugin.Log.LogInfo($"[MAPCOLOR-L9] {sku}: m_background is null"); return; }
                var sb = new System.Text.StringBuilder();
                int live = 0;
                foreach (var ps in bgGO.GetComponentsInChildren<ParticleSystem>(true))
                {
                    if (ps == null) continue;
                    bool act = false; int n = 0; Color c = Color.white;
                    try { act = ps.gameObject.activeInHierarchy; n = ps.particleCount; c = ps.main.startColor.color; } catch { }
                    if (act && n > 0) live++;
                    sb.Append($" {ps.gameObject.name}(active={act},n={n},#{(int)(Mathf.Clamp01(c.r)*255):X2}{(int)(Mathf.Clamp01(c.g)*255):X2}{(int)(Mathf.Clamp01(c.b)*255):X2})");
                }
                Plugin.Log.LogInfo($"[MAPCOLOR-L9] {sku}: {live} live background system(s) —{sb}");
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR-L9] failed: {ex.Message}"); }
        }

        // ── Live ColorGrading bundle dump (bug 249 diagnostic) ────────────────
        // Reads the values off the LAYER's bundle, not off our own settings object.
        // Unity never resets a bundle whose base setting is disabled (see the note
        // in CustomMapColors.BuildOrGetClone), so the bundle is the only place the
        // residue is visible — a non-zero hueShift here means a previous profile's
        // grading is still rotating our background. Reflection because
        // PostProcessLayer.GetBundle is internal.
        private static readonly HashSet<string> _loggedCgKeys = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        internal static void LogLiveColorGrading(string sku, string phase)
        {
            try
            {
                if (!_loggedCgKeys.Add(sku + "|" + phase)) return;
                foreach (var layer in UnityEngine.Object.FindObjectsOfType<PostProcessLayer>())
                {
                    if (layer == null) continue;
                    var mi = typeof(PostProcessLayer).GetMethod("GetBundle",
                        System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public
                        | System.Reflection.BindingFlags.NonPublic,
                        null, new Type[] { typeof(Type) }, null);
                    if (mi == null) { Plugin.Log.LogInfo("[MAPCOLOR-CG] GetBundle not found"); return; }
                    var bundle = mi.Invoke(layer, new object[] { typeof(ColorGrading) });
                    if (bundle == null) continue;
                    var settings = bundle.GetType().GetProperty("settings")?.GetValue(bundle) as ColorGrading;
                    if (settings == null) continue;
                    Plugin.Log.LogInfo($"[MAPCOLOR-CG] {sku} ({phase}) on '{layer.gameObject.name}': mode={settings.gradingMode.value} "
                        + $"filter={settings.colorFilter.value} hue={settings.hueShift.value:F1} sat={settings.saturation.value:F1} "
                        + $"temp={settings.temperature.value:F1} tint={settings.tint.value:F1} con={settings.contrast.value:F1} "
                        + $"postExp={settings.postExposure.value:F2} bright={settings.brightness.value:F1} "
                        + $"lift={settings.lift.value} gain={settings.gain.value} lut={(settings.ldrLut.value != null ? settings.ldrLut.value.name : "none")}");
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR-CG] failed: {ex.Message}"); }
        }

        // ── Camera clear color = THE background (bug 249, v4) ─────────────────
        // THE BACKGROUND CANVAS IS 'LightCamera' AND ITS VANILLA CLEAR IS PURE RED.
        //
        // Scene facts, read straight out of Rounds_Data/level0 (not inferred):
        //   MainCamera   depth +1, clearFlags=Depth,      cullingMask 2522423 (bit 9 CLEAR)
        //   LightCamera  depth -1, clearFlags=SolidColor, backgroundColor RGBA(1,0,0,0),
        //                cullingMask 512 (= layer 9 "Lighting"), targetTexture NULL
        // Layer 9 holds the whole backdrop: the SFLight, ArtHandler.m_background
        // ("BackgroudParticles" and its 7 children — the same 7 renderers
        // TintArtBackground walks), and "Game/Visual/Post/Post_Background", which
        // is the GameObject carrying ArtHandler AND the PostProcessVolume that
        // ArtHandler.volume points at. LightCamera's PostProcessLayer.volumeLayer
        // is 0x200 (layer 9) and MainCamera's is 0x100 (layer 8 = Post_Main).
        //
        // So: LightCamera clears the screen to RED, draws the layer-9 backdrop on
        // top, and grades the result with whatever profile ArtHandler.volume holds
        // — i.e. with OUR clone. The red is not a buffer artifact; it is the canvas
        // the art profile is REQUIRED to recolour. Every vanilla art does exactly
        // that with a big hueShift (Sky -61, Gold -52, Poison -95, Soviet -48,
        // Sweden -65, Rainbow -80 degrees) plus -2.2..-5.0 EV in HDR/ACES; none of
        // them overrides colorFilter at all.
        //
        // Bug 249: our clone throws the vanilla ColorGrading away and installs one
        // that only drives saturation/temperature/colorFilter. colorFilter is a
        // per-channel MULTIPLY, and the canvas is (1,0,0) — so the green and blue
        // halves of every designed background colour are multiplied by zero and the
        // backdrop can only ever be red. All 23 skins collapse to colorFilter.r in
        // [0.46, 0.68]: one hue, a few percent of brightness apart. That is the
        // "8 out of 10 map skins have a pinkish background, and it never changes".
        //
        // Fix: paint the canvas itself. Tinting LightCamera.backgroundColor gives
        // every skin its designed background with hueShift left at 0, so the RGB
        // tints we put on the wall/atmosphere particles still read true.
        //
        // Learning #119 forbade this ("LightCamera renders the SFSS light TEXTURE
        // and RGBA(1,0,0,0) is the buffer's required init value"). That premise is
        // WRONG and is corrected in this pass: the decompiled SFRenderer never
        // reads Camera.backgroundColor — it allocates its lightmap/shadowmap via
        // RenderTexture.GetTemporary in OnPreRender and clears them itself with
        // GL.Clear(_ambientLight) — and LightCamera has no targetTexture, so it
        // renders to the backbuffer. What round 4..7 actually got wrong was writing
        // the clear at ALPHA 1; vanilla's is alpha 0 and MainCamera composites over
        // it, so an opaque clear changes the composite. We preserve the camera's own
        // vanilla alpha and only ever touch its RGB.
        private static readonly Dictionary<int, Color> _vanillaCamClears = new Dictionary<int, Color>();
        private static readonly Dictionary<int, CameraClearFlags> _vanillaCamFlags = new Dictionary<int, CameraClearFlags>();
        private static bool _loggedCams;
        // sku the clear currently carries, per camera — so the [MAPCOLOR-CAMS]
        // write line is emitted once per (camera, sku) instead of every apply.
        private static readonly Dictionary<int, string> _camClearSku = new Dictionary<int, string>();

        public static void ApplyCameraBackground(string sku)
        {
            try
            {
                Color? bgN = CustomMapColors.GetBackgroundColor(sku) ?? CustomMapColors.GetMapBlockColor(sku);
                if (!bgN.HasValue) return;
                Color bg = bgN.Value;
                _backdropMaskThisPass = 0;
                var cams = UnityEngine.Object.FindObjectsOfType<Camera>();
                foreach (var cam in cams)
                {
                    if (cam == null) continue;
                    // The letterbox clear camera is an on-screen SolidColor
                    // camera too, but it must stay opaque black: painting it
                    // would colour the strips outside ROUNDS' viewport.
                    if (LetterboxClear.IsOurs(cam)) continue;
                    if (!_loggedCams)
                        Plugin.Log.LogInfo($"[MAPCOLOR-CAMS] '{cam.gameObject.name}' depth={cam.depth} flags={cam.clearFlags} bg={cam.backgroundColor} rt={(cam.targetTexture != null)} mask={cam.cullingMask}");
                    // Only genuinely OFF-SCREEN cameras are off limits — the ones
                    // rendering into a RenderTexture (our own card/cosmetic preview
                    // rigs, CardSnapshot / NativeUI, which both set targetTexture).
                    // The name-based "Light" test that used to live here is gone: it
                    // excluded the one camera that actually paints the background.
                    bool offscreen = cam.targetTexture != null;
                    int id = cam.GetInstanceID();
                    if (offscreen)
                    {
                        if (_vanillaCamClears.TryGetValue(id, out var v))
                        {
                            cam.backgroundColor = v;
                            _vanillaCamClears.Remove(id);
                            _camClearSku.Remove(id);
                            Plugin.Log.LogInfo($"[MAPCOLOR-CAMS] restored off-screen camera '{cam.gameObject.name}' clear to {v}");
                        }
                        continue;
                    }
                    // Only cameras that actually CLEAR to a color paint backdrop.
                    // MainCamera clears Depth only and is correctly skipped here.
                    if (cam.clearFlags != CameraClearFlags.SolidColor && cam.clearFlags != CameraClearFlags.Skybox)
                        continue;
                    if (!_vanillaCamClears.ContainsKey(id))
                    {
                        _vanillaCamClears[id] = cam.backgroundColor;
                        _vanillaCamFlags[id] = cam.clearFlags;   // Skybox->SolidColor below must be reversible
                    }
                    // ALPHA IS LOAD-BEARING: keep the camera's own vanilla alpha
                    // (LightCamera's is 0). Writing alpha 1 here is what the v1.29
                    // round-4..7 cast actually was.
                    float a = _vanillaCamClears[id].a;
                    // Brightness, measured rather than guessed. The canvas passes
                    // through our colorFilter (~0.55) and then through Post_Main's
                    // 'Default' grade on MainCamera (postExposure +1.50 EV = x2.83,
                    // contrast +45, gain (1.00, 0.64, 0.31), ACES) — all vanilla, all
                    // outside our control. Painting the clear with the raw designed
                    // colour was measured on this seat at (0.925, 0.811, 0.658) for a
                    // designed (0.62, 0.50, 0.40): a net gain of ~1.59. CLEAR_GAIN_COMP
                    // cancels that so the screen lands on the authored value, and the
                    // per-skin exposure multiplier restores the design's -0.30..-0.72 EV
                    // "background mood" band, which has been inert since v1.29 because
                    // LDR grading never reads postExposure.
                    const float CLEAR_GAIN_COMP = 0.48f;
                    float lift = CLEAR_GAIN_COMP * CustomMapColors.GetBackgroundExposureMultiplier(sku);
                    Color canvas = CompensatePostMain(new Color(bg.r * lift, bg.g * lift, bg.b * lift, 1f));
                    cam.backgroundColor = new Color(
                        Mathf.Clamp01(canvas.r), Mathf.Clamp01(canvas.g), Mathf.Clamp01(canvas.b), a);
                    if (cam.clearFlags == CameraClearFlags.Skybox)
                        cam.clearFlags = CameraClearFlags.SolidColor;
                    // This camera paints the canvas, so its cullingMask IS the
                    // backdrop set — see IsBackdropSystem.
                    NoteBackdropCamera(cam);
                    // One line per (camera, sku): proves from a single session log
                    // that the canvas is actually being repainted per skin, which is
                    // the whole claim of this fix.
                    string had;
                    if (!_camClearSku.TryGetValue(id, out had) || !string.Equals(had, sku, StringComparison.OrdinalIgnoreCase))
                    {
                        _camClearSku[id] = sku;
                        Plugin.Log.LogInfo($"[MAPCOLOR-CAMS] painted '{cam.gameObject.name}' clear for {sku}: {cam.backgroundColor} (vanilla was {_vanillaCamClears[id]})");
                    }
                }
                _loggedCams = true;
                CommitBackdropMask();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] camera bg failed: {ex.Message}"); }
        }

        public static void RestoreCameraBackground()
        {
            try
            {
                foreach (var cam in UnityEngine.Object.FindObjectsOfType<Camera>())
                {
                    if (cam == null) continue;
                    int id = cam.GetInstanceID();
                    if (_vanillaCamClears.TryGetValue(id, out var v))
                    {
                        cam.backgroundColor = v;
                        if (_vanillaCamFlags.TryGetValue(id, out var vf)) cam.clearFlags = vf;
                        _camClearSku.Remove(id);
                    }
                }
            }
            catch { }
        }

        // ── Premium twinkle loop (v1.29 round 6) ──────────────────────────────
        // Static two-color gradients only vary at EMISSION — big slow slabs never
        // visibly "sparkle". This loop re-rolls WHICH particles carry the glint a
        // few times a second (stable per-particle randomSeed + a rolling tick),
        // producing an actual twinkle at sub-bloom brightness.
        internal struct TwinkleEntry { public ParticleSystem ps; public Color baseColor; public Color glintColor; }
        internal static readonly List<TwinkleEntry> _twinkleSystems = new List<TwinkleEntry>();
        private static bool _twinkleLoopRunning;
        private static int _twinkleHostId;
        private static uint _twinkleTick;

        internal static void EnsureTwinkleLoop()
        {
            var host = Plugin.Instance;
            if (host == null) return;
            // Keyed on the HOST, not a bare bool: the persistent object is destroyed and
            // respawned across ROUNDS' scene changes, which kills the coroutine while
            // leaving the flag true — after which every later call returned and premium
            // shimmer was gone for the rest of the process (Codex r5 #9).
            int hostId = host.GetInstanceID();
            if (_twinkleLoopRunning && _twinkleHostId == hostId) return;
            _twinkleLoopRunning = true;
            _twinkleHostId = hostId;
            host.StartCoroutine(TwinkleLoop(hostId));
        }

        private static System.Collections.IEnumerator TwinkleLoop(int hostId)
        {
            // 1.6s between re-rolls (was 0.45s — Sid: "premium colors are
            // shifting too fast"). A slow drift of which particles glint reads
            // as shimmer; the old rate read as strobing.
            var wait = new WaitForSeconds(1.6f);
            while (true)
            {
                yield return wait;
                if (_twinkleHostId != hostId) yield break;   // a newer host owns the loop
                if (_twinkleSystems.Count == 0) continue;
                // NEVER inside the MapTransition window. This loop calls SetParticles
                // (via RetintLiveParticles) every 1.6s — SHORTER than the 2.0s guard —
                // so on a premium skin it was reaching into MapTransition.Move on every
                // single round change: the #45/#85 move-stall, from a path nobody had
                // connected to it because the list survives the transition intact.
                // Also require a live battle, so it cannot tick over the menu.
                if (MapPhysicalColorPatch.InMapTransition()) continue;
                // isPlaying, NOT battleOngoing: spectators suppress the participant
                // writes to battleOngoing, so gating on it silently killed premium
                // shimmer on the broadcast seat — the one seat whose whole job is
                // looking good (Codex r3 #8). isPlaying is forced true on the
                // spectator join path and is false in the menus, which is the only
                // thing this guard is actually for.
                bool playing = false;
                try { playing = GameManager.instance != null && GameManager.instance.isPlaying; } catch { }
                if (!playing) continue;
                // v1.32 item 8: static-cosmetics mode — stop re-rolling the glint.
                // The tick=0 emission gradient already gives a stable two-tone
                // pattern, so skipping here freezes the shimmer in place. Gate the
                // BODY, not the loop start: the loop is while(true) and started at
                // most once per session, so a start-site gate would never re-arm.
                if (Plugin.AnimatedCosmetics != null && !Plugin.AnimatedCosmetics.Value) continue;
                _twinkleTick++;
                for (int i = 0; i < _twinkleSystems.Count; i++)
                {
                    var e = _twinkleSystems[i];
                    try
                    {
                        if (e.ps == null) continue;
                        RetintLiveParticles(e.ps, e.baseColor, e.glintColor, _twinkleTick);
                    }
                    catch { }
                }
            }
        }

        // ── SFSS lighting = the REAL background system (learning #116 v3) ─────
        // The scene composite is: sprites × lightmap, where lightmap = SFLight
        // glow + SFRenderer._ambientLight everywhere else. The "sky" is a
        // backdrop lit by the big light; the shadow beams are ambient-only
        // regions ("a darker grey, BLUE..." per the asset's own tooltip — the
        // ever-blue tone). Tint the big light toward a bright version of the
        // skin background and the ambient toward a dark version: sky and
        // shadows become the designed hue, walls/geometry sprites keep their
        // own colors. Small lights (muzzle flashes etc.) are left alone.
        private static readonly Dictionary<int, Color> _vanillaLightColors = new Dictionary<int, Color>();
        private static readonly Dictionary<int, Color> _vanillaAmbient = new Dictionary<int, Color>();
        private static bool _loggedLights;

        public static void ApplyLighting(string sku)
        {
            try
            {
                Color? bgN = CustomMapColors.GetBackgroundColor(sku) ?? CustomMapColors.GetMapBlockColor(sku);
                if (!bgN.HasValue) return;
                Color bg = SaturateColor(bgN.Value, 1.10f);
                // Lit areas = bright designed hue; shadowed areas = deep shade of it.
                // v1.29.1: the +0.22 brightness floor is now LUMINANCE-SCALED. The
                // fixed floor meant even a pitch-black background rendered as a
                // grey sky (0.22 minimum) — the dark skins (charcoal/obsidian/
                // blackwood/abyss) could never go actually dark (Sid: "Charcoal
                // should be pretty dark"). Backgrounds at luminance >= 0.25 keep
                // the exact old math (floor 0.22, zero visual change for the
                // mid/light skins); below that the floor sinks toward 0.04 so a
                // near-black value reads as pitch-black smoke instead of fog.
                float bgLum = 0.299f * bg.r + 0.587f * bg.g + 0.114f * bg.b;
                float skyFloor = Mathf.Lerp(0.04f, 0.22f, Mathf.InverseLerp(0.04f, 0.25f, bgLum));
                Color lit = CapBrightness(CompensatePostMain(new Color(
                    skyFloor + bg.r * 0.95f, skyFloor + bg.g * 0.95f, skyFloor + bg.b * 0.95f, 1f)), 1.0f);
                // Alpha 0.85 matches the vanilla ambient's alpha (its meaning is
                // internal to the SFSS shader — keep the semantics identical).
                Color amb = CompensatePostMain(new Color(bg.r * 0.45f, bg.g * 0.45f, bg.b * 0.45f, 0.85f));
                amb.a = 0.85f;   // alpha carries SFSS meaning — never let the compensation touch it

                foreach (var rend in UnityEngine.Object.FindObjectsOfType<SFRenderer>())
                {
                    if (rend == null) continue;
                    int id = rend.GetInstanceID();
                    if (!_vanillaAmbient.ContainsKey(id))
                    {
                        _vanillaAmbient[id] = rend.ambientLight;
                        Plugin.Log.LogInfo($"[MAPCOLOR-LIGHT] SFRenderer '{rend.gameObject.name}' vanilla ambient={rend.ambientLight}");
                    }
                    rend.ambientLight = amb;
                }
                if (SFLight._lights != null)
                    foreach (var l in SFLight._lights)
                    {
                        if (l == null) continue;
                        if (!_loggedLights)
                            Plugin.Log.LogInfo($"[MAPCOLOR-LIGHT] SFLight '{l.gameObject.name}' color={l._color} intensity={l._intensity} radius={l._radius} parallax={l._parallaxLight}");
                        // Scene light detection: Sid's log shows THE sun-light is
                        // radius=0.5, intensity=10, vanilla color PURE BLUE — the
                        // radius>=20 filter skipped exactly the light that paints the
                        // sky. Key on intensity/parallax instead; gameplay flashes are
                        // low-intensity.
                        if (!l._parallaxLight && l._intensity < 5f) continue;
                        int id = l.GetInstanceID();
                        if (!_vanillaLightColors.ContainsKey(id)) _vanillaLightColors[id] = l._color;
                        l._color = lit;
                    }
                _loggedLights = true;
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] lighting tint failed: {ex.Message}"); }
        }

        public static void RestoreLighting()
        {
            try
            {
                foreach (var rend in UnityEngine.Object.FindObjectsOfType<SFRenderer>())
                {
                    if (rend == null) continue;
                    if (_vanillaAmbient.TryGetValue(rend.GetInstanceID(), out var a))
                        rend.ambientLight = a;
                }
                if (SFLight._lights != null)
                    foreach (var l in SFLight._lights)
                    {
                        if (l == null) continue;
                        if (_vanillaLightColors.TryGetValue(l.GetInstanceID(), out var c))
                            l._color = c;
                    }
            }
            catch { }
        }

        // ── v1.32 item 7: FPS settings — map lighting / shadows kill-switches ──
        // Mechanics (full-game decompile SFRenderer.cs, on the 'LightCamera'):
        //  • Shadows off (_shadows=false) skips the WHOLE shadow pass — CullPolys +
        //    a second lightmap RT + per-light shadow meshes. Big win, scene stays
        //    fully lit and correctly colored. This is the safe perf toggle.
        //  • Lighting off (enabled=false) stops OnPreRender, so no lightmap is built.
        //    We set the SFSS shader globals to white so scene SPRITES (players,
        //    walls) render full-bright and clearly. BUT the map's SKY COLOR *is* the
        //    lighting: the scene composites as sprites × lightmap, and the backdrop
        //    sprite art (ArtHandler.m_background) is a fixed DARK texture that the
        //    lightmap normally brightens/tints into the per-map sky (learning #117).
        //    White light on a dark backdrop = dark → the constant "dark purple"
        //    Sid saw regardless of map (v1.32 round 2). There is NO way to recover
        //    the coloured sky without the lighting, so lighting-off deliberately
        //    paints m_background a flat neutral slate (ApplyBackdrop) — a clean
        //    minimal backdrop that reads as an intentional perf/accessibility mode.
        // Vanilla state cached per instance id; re-applied every Map.Start / NextArt
        // because scene reloads spawn fresh renderers.
        internal static class RenderPerfSettings
        {
            /// <summary>Item 13: the named writers of the two map-render rows
            /// (the settings page and its per-tab reset). Each writes its entry
            /// by name and then runs the same live effect the row's handler used
            /// to run inline: re-apply the renderers, re-queue the backdrop, and
            /// re-tint a live custom skin, because which side carries the
            /// inverse gain depends on whether SFSS lighting is on (Codex r5
            /// #1). Deferred, so it never lands mid-transition.</summary>
            internal static void SetLighting(bool on)
            {
                if (Plugin.MapLightingEnabled == null) return;
                Plugin.MapLightingEnabled.Value = on;
                ApplyLive();
            }

            internal static void SetShadows(bool on)
            {
                if (Plugin.MapShadowsEnabled == null) return;
                Plugin.MapShadowsEnabled.Value = on;
                ApplyLive();
            }

            private static void ApplyLive()
            {
                try
                {
                    Apply();
                    ApplyBackdrop();
                    var liveSku = MapColorState.CurrentSku;
                    if (!string.IsNullOrEmpty(liveSku) && CustomMapColors.IsCustomSku(liveSku))
                        MapPhysicalColorPatch.ScheduleDeferredTints(liveSku);
                }
                catch { }
            }

            private static readonly Dictionary<int, bool> _vanillaShadows = new Dictionary<int, bool>();
            private static readonly Dictionary<int, bool> _vanillaEnabled = new Dictionary<int, bool>();
            // Flat backdrop shown while lighting is disabled (matches the mod's UI
            // panel slate so it looks deliberate). Kept opaque; per-sprite vanilla
            // alpha is preserved at paint time.
            private static readonly Color FLAT_BACKDROP = new Color(0.09f, 0.10f, 0.13f, 1f);
            private static bool _flatBackdropActive = false;

            // Renderer enable + shadow flags + shader globals. Safe to run early in
            // the Map.Start postfix (field flips, not particle mutation — no
            // MapTransitionGuardSec needed). Does NOT touch the backdrop; that must
            // run LAST (ApplyBackdrop) so the postfix's own RestoreVanillaSky for
            // default maps can't undo it.
            internal static void Apply()
            {
                try
                {
                    bool light = Plugin.MapLightingEnabled == null || Plugin.MapLightingEnabled.Value;
                    bool shadow = Plugin.MapShadowsEnabled == null || Plugin.MapShadowsEnabled.Value;
                    foreach (var rend in UnityEngine.Object.FindObjectsOfType<SFRenderer>())
                    {
                        if (rend == null) continue;
                        int id = rend.GetInstanceID();
                        if (!_vanillaShadows.ContainsKey(id)) _vanillaShadows[id] = rend._shadows;
                        if (!_vanillaEnabled.ContainsKey(id)) _vanillaEnabled[id] = rend.enabled;
                        rend._shadows = shadow ? _vanillaShadows[id] : false;
                        rend.enabled = light ? _vanillaEnabled[id] : false;
                    }
                    if (!light)
                    {
                        // A disabled SFRenderer never runs OnPostRender, so the SFSS
                        // shader globals keep pointing at the previous scene's released
                        // lightmap RTs. Pin them to vanilla's OnPostRender identity
                        // (white ambient/exposure/lightmaps) so scene sprites stay
                        // full-bright and stable.
                        Shader.SetGlobalColor("_SFAmbientLight", Color.white);
                        Shader.SetGlobalFloat("_SFExposure", 1f);
                        Shader.SetGlobalTexture("_SFLightMap", Texture2D.whiteTexture);
                        Shader.SetGlobalTexture("_SFLightMapWithShadows", Texture2D.whiteTexture);
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[RENDERPERF] apply failed: {ex.Message}"); }
            }

            /// <summary>Public entry point. MUTATES PARTICLES, so it can never run
            /// straight out of Map.Start: that postfix executes inside
            /// MapTransition.Move and SetParticles there is the #45/#85 move-stall.
            /// It also has to run AFTER whichever tint/restore wins the deferred slot,
            /// or the 2s-later pass silently overwrites the flat backdrop and the
            /// "disable map lighting" setting stops visually working. Both problems
            /// have the same answer: hand it to the deferred slot, whose winners call
            /// ApplyBackdropNow() as their last act.</summary>
            internal static void ApplyBackdrop()
            {
                // ALWAYS deferred. Testing `inTransition` here repeats the mistake this
                // whole batch is about: LastMapStartTime is the PREVIOUS map stamp until
                // the incoming Map.Start writes it, so toggling Map Lighting in the F5
                // menu during a move reads "not in transition" and mutates particles
                // mid-move. A settings toggle is never urgent.
                ScheduleDeferredBackdrop();
            }

            internal static void ApplyBackdropNow()
            {
                try
                {
                    bool light = Plugin.MapLightingEnabled == null || Plugin.MapLightingEnabled.Value;
                    if (!light)
                    {
                        PaintFlatBackdrop();
                        _flatBackdropActive = true;
                    }
                    else if (_flatBackdropActive)
                    {
                        // Lighting came back on — bring the real sky back. Restore the
                        // vanilla backdrop, then re-tint if a custom map skin is active
                        // (its sky is a direct sprite tint, independent of lighting).
                        // Particle mutation, but ApplyBackdropNow is only ever reached
                        // from a settled deferred pass or from outside the guard window.
                        RestoreVanillaSky();
                        var sku = MapColorState.CurrentSku;
                        if (!string.IsNullOrEmpty(sku) && CustomMapColors.IsCustomSku(sku))
                            TintArtBackground(sku);
                        _flatBackdropActive = false;
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[RENDERPERF] backdrop failed: {ex.Message}"); }
            }

            // Paint ArtHandler.m_background a flat neutral slate. Captures true vanilla
            // into the SAME caches the skin-tint pass uses (_vanillaSkyColors for
            // sprites, GetCachedVanillaColor for particles), so RestoreVanillaSky
            // brings the real sky back and the skin-tint pass reads correct vanilla.
            private static void PaintFlatBackdrop()
            {
                var ah = ArtHandler.instance;
                var bgGO = ah != null ? ah.m_background : null;
                if (bgGO == null) return;
                foreach (var sr in bgGO.GetComponentsInChildren<SpriteRenderer>(true))
                {
                    if (sr == null) continue;
                    int id = sr.GetInstanceID();
                    if (!_vanillaSkyColors.TryGetValue(id, out var vanilla))
                    {
                        vanilla = sr.color;
                        _vanillaSkyColors[id] = vanilla;
                    }
                    var flatSr = CompensateSurfaceIfUnlit(FLAT_BACKDROP);
                    sr.color = new Color(flatSr.r, flatSr.g, flatSr.b, vanilla.a);
                }
                foreach (var ps in bgGO.GetComponentsInChildren<ParticleSystem>(true))
                {
                    if (ps == null) continue;
                    Color vanilla = GetCachedVanillaColor(ps);
                    Color flatC = CompensateSurfaceIfUnlit(FLAT_BACKDROP);
                    Color flat = new Color(flatC.r, flatC.g, flatC.b, vanilla.a);
                    var main = ps.main;
                    main.startColor = new ParticleSystem.MinMaxGradient(flat);
                    RetintLiveParticles(ps, flat);
                }
            }
        }

        // Item 8 (July 20): chromatic aberration toggle. CA lives as a
        // ChromaticAberration settings object on every art's shared
        // PostProcessProfile (baseline) plus vanilla's ChomaticAberrationFeeler
        // (sic) writing intensity pulses each frame. Zeroing intensity loses to
        // the feeler's per-frame writes; flipping `active` wins outright —
        // PostProcessLayer.OverrideSettings skips inactive effects and re-blends
        // from profiles every frame, so the flip is instant both directions and
        // needs no vanilla-value caching (default true, vanilla never writes it).
        // Profiles are session-long shared assets, so every apply site must
        // assert the CURRENT toggle value, and the CustomMapColors clone cache
        // must be swept too (clones deep-copy the CA settings object).
        internal static class ChromaticAberrationSetting
        {
            internal static void Apply()
            {
                try
                {
                    bool on = Plugin.ChromaticAberrationEnabled == null || Plugin.ChromaticAberrationEnabled.Value;
                    // Report #141: the toggle did nothing, and this list is why.
                    // ArtHandler's profiles are NOT where the rendered aberration
                    // lives. Vanilla's ChomaticAberrationFeeler grabs its settings
                    // object in OnAwake from the volume IT is attached to — the
                    // permanently-Default `Post_Main`, not the per-art
                    // `Post_Background` — and then writes intensity every Update.
                    // Sweeping only the art profiles is learning #262's bloom trap
                    // repeated exactly: the BloomStrengthSetting note directly
                    // below this class already warns that "the obvious
                    // ChromaticAberrationSetting-shaped implementation ... changes
                    // nothing at all", and that warning was about this code.
                    //
                    // So enumerate every LIVE volume instead of guessing which one
                    // matters. `.profile` not `.sharedProfile` for the reason in
                    // that same note: the Feeler's own `.profile` call has already
                    // forced an internal clone, so writes to the shared asset are
                    // invisible to the renderer.
                    int touched = 0;
                    foreach (var vol in UnityEngine.Object.FindObjectsOfType<PostProcessVolume>())
                    {
                        if (vol == null) continue;
                        if (Set(vol.profile, on)) touched++;
                    }
                    var ah = ArtHandler.instance;
                    if (ah != null)
                    {
                        // Kept: arts not currently mounted on a live volume still
                        // need the flag asserted before they are swapped in.
                        try { if (Set(ah.volume != null ? ah.volume.profile : null, on)) touched++; } catch { }
                        try { if (Set(ah.menuArt != null ? ah.menuArt.profile : null, on)) touched++; } catch { }
                        try { if (ah.arts != null) foreach (var a in ah.arts) if (Set(a != null ? a.profile : null, on)) touched++; } catch { }
                    }
                    foreach (var clone in CustomMapColors.CachedClones) if (Set(clone, on)) touched++;
                    if (!_caLogged)
                    {
                        _caLogged = true;
                        Plugin.Log.LogInfo($"[CA-TOGGLE] on={on}; {touched} profile(s) carrying a ChromaticAberration found");
                        if (touched == 0)
                            Plugin.Log.LogWarning("[CA-TOGGLE] no ChromaticAberration found on any profile — the toggle will do nothing");
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[CA-TOGGLE] apply failed: {ex.Message}"); }
            }

            private static bool _caLogged;

            private static bool Set(PostProcessProfile p, bool on)
            {
                if (p == null) return false;
                try
                {
                    if (p.TryGetSettings<ChromaticAberration>(out var ca) && ca != null)
                    {
                        // `active`, not intensity: the Feeler rewrites
                        // intensity.value every Update and would win, whereas
                        // PostProcessLayer.OverrideSettings skips an inactive
                        // effect outright, so the flip is instant both ways and
                        // needs no vanilla-value caching.
                        ca.active = on;
                        return true;
                    }
                }
                catch { }
                return false;
            }

            /// <summary>Item 13: the value-taking writer the settings page and
            /// its per-tab reset call. Writes the entry by name, then re-applies
            /// every live profile, which is what the row's handler used to do
            /// inline. It stays BELOW the private Set(PostProcessProfile, bool):
            /// the item-13 keyset instrument resolves a call to a bare Set by
            /// the first Set declared in this file, and that must remain the
            /// overload that writes no ConfigEntry.</summary>
            internal static void Set(bool on)
            {
                if (Plugin.ChromaticAberrationEnabled == null) return;
                Plugin.ChromaticAberrationEnabled.Value = on;
                try { Apply(); } catch { }
            }
        }

        /// <summary>Bloom strength (Sid's "cosmetics are illuminated and the effect is quite
        /// large for some people"). Full / Reduced / Off, local to this client.
        ///
        /// <para>TARGETING NOTE — this is the whole reason the setting works. ROUNDS runs TWO
        /// PostProcessVolumes: `Post_Background`, whose profile ArtHandler swaps per art, and
        /// `Post_Main`, which permanently holds the `Default` profile. Every one of the nine ART
        /// profiles ships Bloom with <c>active = false</c>, and
        /// <c>PostProcessLayer.OverrideSettings</c> opens with
        /// <c>if (!baseSetting.active || !baseSetting.enabled) continue;</c> — so those Blooms are
        /// inert. The bloom that actually renders is `Default`'s: active, intensity 35,
        /// threshold 1.20, diffusion 7. Writing to the ArtHandler profiles (which is what the
        /// obvious ChromaticAberrationSetting-shaped implementation would do, and what
        /// CustomMapColors has been doing since v1.29) changes nothing at all — learning #91's
        /// silent-forever-no-op, one layer up. So we enumerate every live PostProcessVolume
        /// instead of assuming which one matters.</para>
        ///
        /// <para>Knobs, from the decompiled BloomRenderer: brightness is
        /// <c>Exp2(intensity/10) - 1</c> (35 -> 10.3x, 21 -> 3.3x); halo EXTENT is
        /// <c>2^(diffusion-10)</c>, so each -1 halves the radius; <c>threshold</c> decides which
        /// pixels qualify at all. "Quite large" is the diffusion knob, which is why Reduced
        /// leans on it hardest.</para>
        ///
        /// <para>Nothing here touches a renderer, material, colour, particle or equipped state,
        /// so no cosmetic can be hidden or broken by any level (cf. #96 / #29). Off removes the
        /// halo and leaves the object itself pixel-identical. It cannot remove glow that an
        /// artist PAINTED into their PNG (energy orbs, shooting star) — that is art, not an
        /// effect.</para></summary>
        internal static class BloomStrengthSetting
        {
            private struct Authored
            {
                public bool active;
                public float intensity, threshold, diffusion;
                public bool oIntensity, oThreshold, oDiffusion;
            }
            private static readonly Dictionary<int, Authored> _authored = new Dictionary<int, Authored>();
            private static bool _logged;

            internal static string Level
            {
                get
                {
                    string v = Plugin.BloomStrength != null ? (Plugin.BloomStrength.Value ?? "") : "";
                    v = v.Trim();
                    if (string.Equals(v, "Off", StringComparison.OrdinalIgnoreCase)) return "Off";
                    if (string.Equals(v, "Reduced", StringComparison.OrdinalIgnoreCase)) return "Reduced";
                    return "Full";
                }
            }

            /// <summary>Cycles Full -> Reduced -> Off -> Full through Set.</summary>
            internal static void Cycle()
            {
                Set(Level == "Full" ? "Reduced" : Level == "Reduced" ? "Off" : "Full");
            }

            /// <summary>Item 13: the value-taking writer (the settings page's
            /// segmented row and its per-tab reset). The level is canonicalised
            /// to Full / Reduced / Off the same way Level reads it, so a caller
            /// cannot store a display word; null or unknown writes Full. Applies
            /// immediately. Declared BEFORE the private Set(PostProcessProfile,
            /// string, string) below, so it is the first Set of this class.</summary>
            internal static void Set(string level)
            {
                string v = (level ?? "").Trim();
                string next = string.Equals(v, "Off", StringComparison.OrdinalIgnoreCase) ? "Off"
                    : string.Equals(v, "Reduced", StringComparison.OrdinalIgnoreCase) ? "Reduced"
                    : "Full";
                if (Plugin.BloomStrength != null) Plugin.BloomStrength.Value = next;
                Apply();
            }

            internal static void Apply()
            {
                try
                {
                    string lvl = Level;
                    int touched = 0;
                    // Enumerate the live volumes rather than trusting ArtHandler's — see the
                    // targeting note above.
                    //
                    // `.profile`, NOT `.sharedProfile` — and this is the second no-op trap in
                    // the same feature (review find, confirmed against the decompile). What the
                    // renderer reads is `PostProcessVolume.profileRef`, which returns
                    // `m_InternalProfile` when one exists and only falls back to `sharedProfile`
                    // otherwise. Vanilla `ChomaticAberrationFeeler.OnAwake` does
                    // `GetComponent<PostProcessVolume>().profile.TryGetSettings<ChromaticAberration>(…)`
                    // on the volume that carries the LIVE bloom, and the `.profile` getter
                    // CREATES `m_InternalProfile` — so by the time we run, that volume is always
                    // reading the internal clone and writes to the shared asset are invisible.
                    // Using `.profile` also means we never mutate the on-disk asset.
                    foreach (var vol in UnityEngine.Object.FindObjectsOfType<PostProcessVolume>())
                    {
                        if (vol == null) continue;
                        if (Set(vol.profile, lvl, vol.name)) touched++;
                    }
                    // Our own map-skin clones, so a custom skin doesn't reinstate full bloom.
                    foreach (var clone in CustomMapColors.CachedClones)
                        if (Set(clone, lvl, "cr-clone")) touched++;
                    if (!_logged)
                    {
                        _logged = true;
                        Plugin.Log.LogInfo($"[BLOOM] level={lvl}; {touched} profile(s) carrying a Bloom found");
                        if (touched == 0)
                            Plugin.Log.LogWarning("[BLOOM] no Bloom settings found on any volume — "
                                                  + "the strength setting will do nothing");
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[BLOOM] apply failed: {ex.Message}"); }
            }

            private static bool Set(PostProcessProfile p, string lvl, string who)
            {
                if (p == null) return false;
                try
                {
                    UnityEngine.Rendering.PostProcessing.Bloom b;
                    if (!p.TryGetSettings(out b) || b == null) return false;
                    int id = p.GetInstanceID();
                    if (!_authored.ContainsKey(id))
                    {
                        _authored[id] = new Authored
                        {
                            active = b.active,
                            intensity = b.intensity.value,
                            threshold = b.threshold.value,
                            diffusion = b.diffusion.value,
                            oIntensity = b.intensity.overrideState,
                            oThreshold = b.threshold.overrideState,
                            oDiffusion = b.diffusion.overrideState,
                        };
                        // Log only the profile that actually renders — the inert ones are noise.
                        if (b.active)
                            Plugin.Log.LogInfo($"[BLOOM] live bloom on '{p.name}' (volume {who}): "
                                + $"intensity={b.intensity.value:F1} threshold={b.threshold.value:F2} "
                                + $"diffusion={b.diffusion.value:F1}");
                    }
                    var a = _authored[id];
                    if (lvl == "Off")
                    {
                        b.active = false;
                        return a.active;   // only count profiles that were ever going to render
                    }
                    b.active = a.active;
                    if (lvl == "Reduced")
                    {
                        // Extent first (that is the reported complaint): -2 diffusion = a
                        // QUARTER of the radius. Then a real but not total brightness cut, and
                        // a higher threshold so fewer pixels qualify at all.
                        b.intensity.Override(a.intensity * 0.6f);
                        b.threshold.Override(Mathf.Max(a.threshold, 1.5f));
                        b.diffusion.Override(Mathf.Max(1f, a.diffusion - 2f));
                    }
                    else
                    {
                        // Full: restore the authored values AND their override states, so we
                        // leave the profile exactly as we found it.
                        b.intensity.value = a.intensity; b.intensity.overrideState = a.oIntensity;
                        b.threshold.value = a.threshold; b.threshold.overrideState = a.oThreshold;
                        b.diffusion.value = a.diffusion; b.diffusion.overrideState = a.oDiffusion;
                    }
                    return a.active;
                }
                catch { return false; }
            }
        }

        // ── TOMBSTONE: the "backdrop quad" pass is RETIRED (bug 249) ──────────
        // It hunted a NON-particle SpriteRenderer at least 60x25 world units and
        // tinted it, on the theory that a per-map full-screen quad painted the
        // backdrop. ROUNDS has no such object: the backdrop is LightCamera's clear
        // (now painted by ApplyCameraBackground), ArtHandler.m_background's seven
        // layer-9 particle systems (TintArtBackground), the active art's own
        // particles, and the SFSS light (ApplyLighting). Every [MAPCOLOR-BG] line
        // this pass ever emitted named something else entirely — 'Bullet_Base
        // (Clone)/A_Homing(Clone)/Anim/SpritePivot/Hard' and
        // 'UI_CardChoice/CardChoiceVisuals/Card Choice Face/Face/...' — i.e. its
        // only real effect was recolouring Homing bullets and the card-choice face
        // to the map skin. Zero coverage lost, one gameplay-visual bug removed.
        // Do not resurrect it without an object that is actually the backdrop.

        // ── Sky (ArtHandler.m_background) tint, v1.29 ─────────────────────────
        // The real backdrop is a dedicated GameObject on ArtHandler, separate
        // from the art particles. Colorize its SpriteRenderers + ParticleSystems
        // toward the skin's BackgroundColor (luminance-preserving, like walls but
        // dimmer), caching vanilla colors per instance so vanilla skins restore.
        private static readonly Dictionary<int, Color> _vanillaSkyColors = new Dictionary<int, Color>();

        private static int TintArtBackground(string sku)
        {
            int touched = 0;
            try
            {
                var ah = ArtHandler.instance;
                var bgGO = ah != null ? ah.m_background : null;
                if (bgGO == null) return 0;
                Color? bgN = CustomMapColors.GetBackgroundColor(sku) ?? CustomMapColors.GetMapBlockColor(sku);
                if (!bgN.HasValue) return 0;
                Color bg = SaturateColor(bgN.Value, 1.15f);

                foreach (var sr in bgGO.GetComponentsInChildren<SpriteRenderer>(true))
                {
                    if (sr == null) continue;
                    int id = sr.GetInstanceID();
                    if (!_vanillaSkyColors.TryGetValue(id, out var vanilla))
                    {
                        vanilla = sr.color;
                        _vanillaSkyColors[id] = vanilla;
                    }
                    float lum = vanilla.r * 0.299f + vanilla.g * 0.587f + vanilla.b * 0.114f;
                    float lift = 0.45f + 0.60f * Mathf.Clamp01(lum);
                    sr.color = new Color(bg.r * lift, bg.g * lift, bg.b * lift, vanilla.a);
                    touched++;
                }
                Color? skySparkle = CustomMapColors.GetSparkleColor(sku);
                foreach (var ps in bgGO.GetComponentsInChildren<ParticleSystem>(true))
                {
                    if (ps == null) continue;
                    Color vanilla = GetCachedVanillaColor(ps);
                    float lum = vanilla.r * 0.299f + vanilla.g * 0.587f + vanilla.b * 0.114f;
                    float lift = 0.45f + 0.60f * Mathf.Clamp01(lum);
                    Color tinted = new Color(bg.r * lift, bg.g * lift, bg.b * lift, vanilla.a);
                    var main = ps.main;
                    if (skySparkle.HasValue)
                    {
                        // Premium skins: sky particles glint gently between the backdrop
                        // tint and a slightly brighter sparkle — star-field, not floodlight.
                        Color glint = CapBrightness(
                            Color.Lerp(tinted, skySparkle.Value, 0.5f) * 1.10f, 1.0f);
                        glint.a = vanilla.a;
                        main.startColor = new ParticleSystem.MinMaxGradient(tinted, glint);
                        RetintLiveParticles(ps, tinted, glint);
                    }
                    else
                    {
                        main.startColor = new ParticleSystem.MinMaxGradient(tinted);
                        RetintLiveParticles(ps, tinted);
                    }
                    touched++;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] sky tint failed: {ex.Message}"); }
            return touched;
        }

        /// <summary>Restore the sky renderers to their cached vanilla colors —
        /// called when a vanilla/default skin becomes active so a previous custom
        /// skin's sky tint doesn't linger (the background object persists).
        ///
        /// ⚠ MUTATES PARTICLES (SetParticles) — never call this directly from
        /// Map.Start or the NextArt prefix; go through RestoreVanillaBackdrop, which
        /// defers it past the MapTransition window (#45/#85).
        ///
        /// The old `_vanillaSkyColors.Count == 0` gate was wrong and silently made the
        /// whole restore a no-op: m_background's seven children are ParticleSystems,
        /// whose vanilla colours live in _vanillaPSColorCache, while _vanillaSkyColors
        /// only ever holds SpriteRenderers — of which this object has none. Restore
        /// per object from whichever cache actually owns it, and touch a particle ONLY
        /// if its true vanilla colour was captured before we ever tinted it (otherwise
        /// GetCachedVanillaColor would latch our own tint as "vanilla").</summary>
        public static void RestoreVanillaSky()
        {
            try
            {
                var ah = ArtHandler.instance;
                var bgGO = ah != null ? ah.m_background : null;
                if (bgGO == null) return;
                int restored = 0;
                foreach (var sr in bgGO.GetComponentsInChildren<SpriteRenderer>(true))
                {
                    if (sr == null) continue;
                    if (_vanillaSkyColors.TryGetValue(sr.GetInstanceID(), out var vanilla))
                    {
                        sr.color = vanilla;
                        restored++;
                    }
                }
                foreach (var ps in bgGO.GetComponentsInChildren<ParticleSystem>(true))
                {
                    if (ps == null) continue;
                    // Only systems whose PRE-TINT state we actually captured.
                    int sid = ps.GetInstanceID();
                    if (!_vanillaPSColorCache.TryGetValue(sid, out var vanilla)) continue;
                    var main = ps.main;
                    bool haveGradient = _vanillaPSGradientCache.TryGetValue(sid, out var vg);
                    main.startColor = haveGradient ? vg : new ParticleSystem.MinMaxGradient(vanilla);
                    // Only repaint the LIVE particles when the authored startColor was a
                    // single colour. Painting a gradient-mode system's live particles with
                    // one sampled colour is not a restore, it is a different kind of damage
                    // (Codex r5 #3) — those particles age out on their own within a round.
                    if (!haveGradient || vg.mode == ParticleSystemGradientMode.Color)
                        RetintLiveParticles(ps, vanilla);
                    restored++;
                }
                if (restored > 0) Plugin.Log.LogInfo($"[MAPCOLOR] restored vanilla sky ({restored} renderer(s))");
            }
            catch { }
        }

        /// <summary>Un-tint the ART particles — the other half of what a skin repaints,
        /// which nothing ever put back, so switching from a custom skin to a vanilla one
        /// left Sky/SkyBG/Paint and friends wearing the old colours until the next map
        /// load happened to re-tint them (Codex r2 #4). Restores only systems whose TRUE
        /// pre-tint colour we captured, deduplicated because the arts share systems
        /// (Clouds belongs to seven of them).
        ///
        /// SEPARATE from RestoreVanillaSky on purpose (Codex r3 #3): the "map lighting
        /// came back on" path wants ONLY the m_background restore, because it re-tints
        /// only m_background afterwards — restoring the art parts there would strand the
        /// walls on vanilla while the sky went back to the skin.
        ///
        /// MUTATES PARTICLES — deferred callers only.</summary>
        public static void RestoreVanillaArtParts()
        {
            try
            {
                var ah = ArtHandler.instance;
                if (ah == null || ah.arts == null) return;
                var partsField = typeof(ArtInstance).GetField("parts",
                    System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                var seen = new HashSet<int>();
                int restored = 0;
                foreach (var art in ah.arts)
                {
                    if (art == null) continue;
                    var partsArr = partsField?.GetValue(art) as ParticleSystem[];
                    if (partsArr == null) continue;
                    foreach (var ps in partsArr)
                    {
                        if (ps == null) continue;
                        int pid = ps.GetInstanceID();
                        if (!seen.Add(pid)) continue;
                        if (!_vanillaPSColorCache.TryGetValue(pid, out var pv)) continue;
                        try
                        {
                            var pm = ps.main;
                            bool havePg = _vanillaPSGradientCache.TryGetValue(pid, out var pg);
                            pm.startColor = havePg ? pg : new ParticleSystem.MinMaxGradient(pv);
                            if (!havePg || pg.mode == ParticleSystemGradientMode.Color)
                                RetintLiveParticles(ps, pv);
                            restored++;
                        }
                        catch { }
                    }
                }
                if (restored > 0) Plugin.Log.LogInfo($"[MAPCOLOR] restored vanilla art parts ({restored} system(s))");
            }
            catch { }
        }

        /// <summary>THE single "hand the backdrop back to vanilla" entry point
        /// (Codex review of bug 249, findings 4/5/6). Every path that makes a
        /// non-custom art live must call this, or the last skin's canvas, lighting
        /// and sky particles sit under a vanilla art that expects the untouched
        /// pure-red clear it grades with its own hueShift.
        ///
        /// Split by safety: the camera clear and the SFSS light/ambient are field
        /// writes and are safe anywhere, including inside MapTransition.Move. The
        /// sky restore calls SetParticles and is NOT — it goes through the same
        /// deferred slot (and the same generation counter) as the tint passes, so a
        /// skin selected while the restore is asleep supersedes it instead of racing
        /// it (#45/#85).</summary>
        public static void RestoreVanillaBackdrop(string why)
        {
            try
            {
                RestoreCameraBackground();
                RestoreLighting();
                _twinkleSystems.Clear();
                MapSkinEffects.Clear(why);   // touches only our own emitter — safe in any window
                // ALWAYS deferred, never conditional on inTransition (Codex r2 #1).
                // `LastMapStartTime` is stale whenever NextArt lands BEFORE the new
                // Map.Start stamps it, so `inTransition` reads false while we are in
                // fact inside MapTransition.Move — the exact window whose particle
                // mutation stalls the move and strands players off-screen (#45/#85).
                // Nothing about a restore is urgent, so the safe branch is the only
                // branch.
                ScheduleDeferredVanillaSky(why);   // ends with ApplyBackdropNow
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] vanilla restore ({why}) failed: {ex.Message}"); }
        }

        /// <summary>Backdrop-only deferred pass, for a settings toggle that lands
        /// inside the transition window with no tint or restore of its own to ride.
        /// Deliberately does NOT take the generation slot: it neither tints nor
        /// restores, so it must not be able to cancel a pass that does.</summary>
        private static bool _backdropPassPending;
        private static int _backdropPassHostId;

        internal static void ScheduleDeferredBackdrop()
        {
            var host = Plugin.Instance;
            if (host == null) return;
            // PUSH THE DEADLINE FIRST, ALWAYS — before any coalescing return. This is
            // the same rule the tint scheduler already carries: a request arriving
            // during a LATER transition must move the shared deadline past ITS OWN
            // window, or the already-sleeping coroutine wakes inside that move and
            // mutates particles (Codex r4 #1).
            float notBefore = Time.time + MapTransitionGuardSec;
            if (notBefore > _tintNotBefore) _tintNotBefore = notBefore;

            // Claim ownership by HOST INSTANCE, not by a wall-clock TTL. Plugin.Instance
            // is a HideAndDontSave object that ROUNDS' scene changes destroy and we
            // respawn; its coroutines die with it. A TTL either strands a real request
            // (too long) or lets two coroutines paint at once (too short) — binding the
            // claim to the host that owns it does neither (Codex r4 #7).
            int hostId = host.GetInstanceID();
            if (_backdropPassPending && _backdropPassHostId == hostId) return;
            _backdropPassPending = true;
            _backdropPassHostId = hostId;
            host.StartCoroutine(DelayedBackdrop(hostId));
        }

        private static System.Collections.IEnumerator DelayedBackdrop(int hostId)
        {
            while (Time.time < _tintNotBefore) yield return null;
            // A newer host claimed the slot while we slept — it owns the apply.
            if (_backdropPassHostId != hostId) yield break;
            _backdropPassPending = false;
            RenderPerfSettings.ApplyBackdropNow();
        }

        private static void ScheduleDeferredVanillaSky(string why)
        {
            var host = Plugin.Instance;
            if (host == null) return;
            float notBefore = Time.time + MapTransitionGuardSec;
            if (notBefore > _tintNotBefore) _tintNotBefore = notBefore;
            _pendingTintSku = null;
            int gen = ++_pendingTintGen;
            host.StartCoroutine(DelayedRestoreVanillaSky(gen, why));
        }

        private static System.Collections.IEnumerator DelayedRestoreVanillaSky(int gen, string why)
        {
            while (Time.time < _tintNotBefore) yield return null;
            if (gen != _pendingTintGen) yield break;          // a skin claimed the slot
            var live = MapColorState.CurrentSku;
            if (!string.IsNullOrEmpty(live) && CustomMapColors.IsCustomSku(live)) yield break;
            Plugin.Log.LogInfo($"[MAPCOLOR] deferred vanilla restore ({why})");
            RestoreVanillaSky();
            RestoreVanillaArtParts();
            RenderPerfSettings.ApplyBackdropNow();   // runs last — see ApplyBackdrop
        }

        // Deterministic 0/1 bucket for a transform path, used to two-tone the wall
        // particle systems. FNV-1a (not string.GetHashCode, which is salted per process
        // run in modern .NET) so the SAME wall path maps to the SAME color on every map
        // load — no between-round color flipping.
        private static int StablePathParity(string s)
        {
            uint h = 2166136261u;
            for (int i = 0; i < s.Length; i++) { h ^= s[i]; h *= 16777619u; }
            return (int)(h & 1u);
        }

        private static string GetTransformPath(Transform t)
        {
            if (t == null) return "";
            var sb = new System.Text.StringBuilder(t.name);
            var p = t.parent;
            while (p != null)
            {
                sb.Insert(0, p.name + "/");
                p = p.parent;
            }
            return sb.ToString();
        }
    }

    [HarmonyPatch(typeof(ArtHandler), "NextArt")]
    class ArtHandlerNextArtPatch
    {
        // SKU → ROUNDS art profile name. Names confirmed via the [MAPCOLOR] Awake postfix log:
        //   arts[0..8] = RainbowSequence, Rainbow, Sweden, Gold, Soviet, Poison, Gold, Sky, Poison
        // SKUs not in this dict fall through to vanilla random behavior.
        private static readonly Dictionary<string, string> SKU_TO_ART = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            { "mapcolor_default", "" },          // empty → fall through to original NextArt
            { "mapcolor_sweden",  "Sweden" },
            { "mapcolor_sky",     "Sky" },
            { "mapcolor_poison",  "Poison" },
            { "mapcolor_gold",    "Gold" },
            { "mapcolor_soviet",  "Soviet" },
            { "mapcolor_rainbow", "Rainbow" },
        };

        // Index into the player's active_color_skus list. Advances by one per NextArt
        // invocation (which ROUNDS fires on Left Shift). Resets to 0 when the equipped
        // list changes so a newly-added color appears immediately instead of being
        // skipped while the index points past the end.
        private static int _cycleIndex = 0;
        private static int _cycleLastListHash = 0;

        // Last-known non-empty filtered equipped list. CachedPlayerStats can briefly
        // become null during a stats refresh or a consent flip; we don't want a Shift
        // press in that window to leak a vanilla random art into the rotation. Once
        // the user has equipped at least one custom color this session we stay on
        // that list until a NEW non-empty list replaces it.
        private static List<string> _lastEquippedFiltered;

        // ── W6: broadcast-seat map-skin cycling ─────────────────────────────
        // Aug 23 round 2 (Sid): the auto-cycle is BROADCAST-ONLY now — a
        // normal spectator keeps their own equipped skins + manual Shift (the
        // fighter branch below), exactly like when they play. And the
        // broadcast pool is the 9-skin Aug 23 night pack ("the new dark
        // series") ONLY, "for the foreseeable future" — the old 23-sku
        // full-catalogue rotation was retired with it, deliberately. Explicit
        // ordered array, never dictionary enumeration order (D1 delta f5);
        // verified entry-by-entry against CustomMapColors._presets.
        private static readonly string[] BroadcastCycleSkus = new string[]
        {
            "mapcolor_forest_fire", "mapcolor_moonlit",  "mapcolor_eclipse",
            "mapcolor_underworld",  "mapcolor_night_city", "mapcolor_night_park",
            "mapcolor_rainy_day",   "mapcolor_midnight", "mapcolor_blood_moon",
        };

        // Spectator cycle state — deliberately SEPARATE from the fighter-seat
        // statics (_cycleIndex / _cycleLastListHash / _lastEquippedFiltered) so
        // spectating never perturbs the player's own equipped rotation.
        private static int _specCycleIndex = -1;   // -1 = fresh; first advance lands on [0]
        // LastMapStartTime value latched at the last adopt/advance (the
        // once-per-map-load debounce — NextArt fires 2-3x per round start).
        // Sentinel NegativeInfinity = fresh cycle, no stamp adopted yet; it can
        // never collide with a real value (LastMapStartTime is -999f before the
        // first map, then Time.time >= 0). R1 f19: the stamp latch is the ONLY
        // debounce — no wall-clock term (see NextSpectatorCycleSku).
        private static float _specAdvanceMapStamp = float.NegativeInfinity;
        private static string _specCycleRoom;

        // Last value seen from Broadcast.TestMapSkin, so a set→unset edge can release
        // the pinned skin instead of leaving MapColorState.CurrentSku pointing at it.
        private static string _lastTestSkin;

        // ── Test-lever TOUR (Aug 23): TestMapSkin may hold a comma-separated LIST
        // of skus; TestMapSkinTourSeconds > 0 advances through it on this seat by
        // firing ArtHandler.NextArt (the same entry the Shift key uses), so one
        // launch screenshots a whole pack. Broadcast identity only, like the lever.
        private static int _tourIndex;
        private static float _tourLastRt = -1f;
        private static string _tourListKey;

        /// <summary>Resolve the pinned test sku: a single sku, or the current tour
        /// element of a comma list. Unknown elements are dropped with a warning.</summary>
        private static string ResolveTestSkin(string raw)
        {
            if (raw.IndexOf(',') < 0) return raw;
            var parts = new List<string>();
            foreach (var piece in raw.Split(','))
            {
                string t = piece.Trim();
                if (t.Length == 0) continue;
                if (CustomMapColors.IsCustomSku(t)) parts.Add(t);
                else Plugin.Log.LogWarning($"[MAPCOLOR] Broadcast.TestMapSkin list element '{t}' is not a known sku — dropped");
            }
            if (parts.Count == 0) return null;
            if (_tourListKey != raw) { _tourListKey = raw; _tourIndex = 0; }
            return parts[_tourIndex % parts.Count];
        }

        /// <summary>Per-frame tick from the persistent Update: advance the tour
        /// and, when asked, drive the menu into Sandbox so the skin renders on a
        /// map without a human at the seat.</summary>
        internal static void TickTestLever()
        {
            try
            {
                if (!BroadcastMode.IsBroadcastIdentity || Plugin.BroadcastTestMapSkin == null) return;
                string raw = (Plugin.BroadcastTestMapSkin.Value ?? "").Trim();
                if (raw.Length == 0) { _tourLastRt = -1f; _sandboxLaunched = false; return; }

                // Auto-Sandbox: one PlaySandbox() once the main menu exists and the
                // seat is not in any room. Vanilla's own button does exactly this.
                if (Plugin.BroadcastTestMapSkinSandbox != null && Plugin.BroadcastTestMapSkinSandbox.Value && !_sandboxLaunched)
                {
                    if (Time.realtimeSinceStartup > 8f && MainMenuHandler.instance != null
                        && !PhotonNetwork.InRoom && (GameManager.instance == null || !GameManager.instance.isPlaying))
                    {
                        _sandboxLaunched = true;
                        Plugin.Log.LogInfo("[MAPCOLOR] TestMapSkinSandbox: entering Sandbox");
                        MainMenuHandler.instance.PlaySandbox();
                    }
                }

                int every = Plugin.BroadcastTestMapSkinTourSeconds != null ? Plugin.BroadcastTestMapSkinTourSeconds.Value : 0;
                if (every <= 0 || raw.IndexOf(',') < 0) return;
                // Floor (review r3 find 9): each advance pushes the deferred
                // tint deadline by MapTransitionGuardSec, so an interval under
                // it starves the physical/effect pass forever and tours only
                // the grading. 5s leaves the pass ~3s to settle.
                if (every < 5) every = 5;
                if (GameManager.instance == null || !GameManager.instance.isPlaying) return;
                if (MapPhysicalColorPatch.InMapTransition()) return;
                float now = Time.realtimeSinceStartup;
                if (_tourLastRt < 0f) { _tourLastRt = now; return; }
                if (now - _tourLastRt < every) return;
                _tourLastRt = now;
                _tourIndex++;
                var ah = ArtHandler.instance;
                if (ah != null)
                {
                    Plugin.Log.LogInfo($"[MAPCOLOR-TOUR] advancing to element {_tourIndex}");
                    ah.NextArt();    // routes through the NextArt prefix → the pinned sku applies
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] test lever tick failed: {ex.Message}"); }
        }
        private static bool _sandboxLaunched;

        /// <summary>Resets the spectator cycle to its fresh state. Called on room
        /// change (a new sitting starts the cycle from the top) and from
        /// MapColorState.OnSpectatorSessionEnd (session teardown).</summary>
        public static void ResetSpectatorCycle()
        {
            _specCycleIndex = -1;
            _specAdvanceMapStamp = float.NegativeInfinity;
            _specCycleRoom = null;
        }

        /// <summary>Broadcast-seat sku selection. Aug 23 round 2 (Sid): the
        /// advance moved from "one per MAP LOAD" to "one per CARD PICK PHASE"
        /// (OnPickPhaseObserved below), so viewers see the swap over the pick
        /// screen instead of seconds into the next battle. This method only
        /// RESOLVES the current sku, keeping it stable across the 2-3 NextArt
        /// calls each round start fires. EXCEPTION — FFA rooms: their pick
        /// phase is the custom simultaneous protocol (no CardChoiceVisuals
        /// Show on any seat), so FFA keeps the old one-advance-per-map-load
        /// behaviour, stamp-latched exactly as before. Never returns
        /// null/vanilla — every entry is a CustomMapColors preset sku.</summary>
        private static string NextSpectatorCycleSku()
        {
            // New room = new sitting → start the cycle fresh.
            string room = null;
            try { room = PhotonNetwork.CurrentRoom != null ? PhotonNetwork.CurrentRoom.Name : null; } catch { }
            if (!string.Equals(room, _specCycleRoom, StringComparison.Ordinal))
            {
                ResetSpectatorCycle();
                _specCycleRoom = room;
            }
            float stamp = MapPhysicalColorPatch.LastMapStartTime;
            bool advanced = false;
            if (float.IsNegativeInfinity(_specAdvanceMapStamp))
            {
                // Fresh cycle (room change / ResetSpectatorCycle): adopt without
                // advancing (bug-233's burst-straddle: NextArt can run on EITHER
                // side of Map.Start's stamp within one load — adopt-first closes
                // the double-advance with no clock at all).
                _specAdvanceMapStamp = stamp;
            }
            else if (stamp != _specAdvanceMapStamp && IsFfaRoomName(room))
            {
                // FFA fallback only — round modes advance in OnPickPhaseObserved.
                _specCycleIndex = (_specCycleIndex + 1) % BroadcastCycleSkus.Length;
                _specAdvanceMapStamp = stamp;
                advanced = true;
            }
            string sku = BroadcastCycleSkus[Mathf.Max(_specCycleIndex, 0) % BroadcastCycleSkus.Length];
            Plugin.Log.LogInfo($"[MAPCOLOR] broadcast {(advanced ? "cycle" : "keep")} → {sku} (index {Mathf.Max(_specCycleIndex, 0)}/{BroadcastCycleSkus.Length})");
            return sku;
        }

        /// <summary>Room-NAME test, deliberately not FfaMode.EngineActive():
        /// the engine predicate is seat-scoped state this cosmetic timing
        /// choice must not depend on — a spectator seat only ever holds a
        /// lease into real mod lobbies, so the prefix is trustworthy here.</summary>
        private static bool IsFfaRoomName(string room)
            => !string.IsNullOrEmpty(room) && room.StartsWith("ffa_", StringComparison.OrdinalIgnoreCase);

        /// <summary>Pick-phase swap trigger (Aug 23 round 2). Called from
        /// SpectatorSync.PlayPointSequence when the observed point is a round
        /// CONVERSION — the one observer-side event that a pick phase is
        /// beginning in EVERY round mode. (Codex r1 find 2 killed the first
        /// design: a CardChoiceVisuals.Show postfix — on a spectator seat
        /// Show fires only from the 1v1 DoWinSequence path; team modes run
        /// DoSequence and game-start runs a suppressed DoStartGame, so
        /// 2v2/1v2 rotations froze on skin [0].) Everything but the
        /// broadcast spectator seat returns on the first lines.
        /// Debounce: one advance per LastMapStartTime stamp — every round's
        /// final point loaded its own map, so duplicate observations within
        /// one round share the stamp and are no-ops.
        /// Known quiet edges, accepted (all self-heal at the next round):
        /// game-START picks (game 2+ of a sitting) have no observer signal,
        /// so the skin simply carries over until that game's first round
        /// conversion; FFA advances per map load instead (its pick protocol
        /// has no conversion event on the observer path either — see
        /// NextSpectatorCycleSku); and a conversion observed while
        /// MapTransition.isTransitioning (fast next point / lagging
        /// catch-up) is discarded without retry, keeping the previous skin
        /// one extra round (Codex r2 LOW, accepted).</summary>
        internal static void OnPickPhaseObserved()
        {
            try
            {
                if (!BroadcastMode.IsBroadcastIdentity) return;
                if (!RoomActors.LocalIsSpectator) return;
                try
                {
                    var t = Plugin.BroadcastTestMapSkin != null ? (Plugin.BroadcastTestMapSkin.Value ?? "").Trim() : "";
                    // A pinned/tour test skin owns the seat — no auto-swap
                    // under it. ('cycle' deliberately falls through: it asks
                    // for the real rotation.)
                    if (t.Length > 0 && !string.Equals(t, "cycle", StringComparison.OrdinalIgnoreCase)) return;
                }
                catch { }
                if (PhotonNetwork.OfflineMode) return;
                string room = null;
                try { room = PhotonNetwork.CurrentRoom != null ? PhotonNetwork.CurrentRoom.Name : null; } catch { }
                if (IsFfaRoomName(room)) return;   // FFA advances per map load (see NextSpectatorCycleSku)
                // Only the AUTHORITATIVE transition flag here — NOT the
                // stamp-tail InMapTransition() (Codex r1 find 3: a fast map
                // load puts the whole pick window inside the 2s tail, and a
                // rejected conversion has no retry, freezing the rotation).
                // Proceeding during the tail is safe: the immediate work is
                // volume-only grading, and the particle pass defers AND
                // re-checks InMapTransition() at wake (DelayedApplyTints).
                try { if (MapTransition.isTransitioning) return; } catch { }
                float stamp = MapPhysicalColorPatch.LastMapStartTime;
                if (!float.IsNegativeInfinity(_specAdvanceMapStamp) && stamp == _specAdvanceMapStamp) return;
                // Keep the room binding fresh BEFORE advancing, or the first
                // pick of a new sitting advances a stale cycle and the
                // NextArt below resets it (room-change check) — losing the
                // advance and double-logging.
                if (!string.Equals(room, _specCycleRoom, StringComparison.Ordinal))
                {
                    ResetSpectatorCycle();
                    _specCycleRoom = room;
                }
                _specCycleIndex = (_specCycleIndex + 1) % BroadcastCycleSkus.Length;
                _specAdvanceMapStamp = stamp;
                Plugin.Log.LogInfo($"[MAPCOLOR] broadcast pick-phase swap → index {_specCycleIndex}/{BroadcastCycleSkus.Length}");
                // Apply through the normal entry (same route as the tour and
                // a manual Shift): the prefix resolves the freshly-advanced
                // index. Grading/backdrop swap same-frame; the particle pass
                // defers a couple seconds (spectator seats always defer) —
                // both land inside the pick window.
                var ah = ArtHandler.instance;
                if (ah != null) ah.NextArt();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[MAPCOLOR] pick-phase swap failed: {ex.Message}"); }
        }

        static bool Prefix(ArtHandler __instance)
        {
            try
            {
                // W6 — spectator seats. `spectatorSeat` feeds the DEFER decision
                // (every spectator always defers particle mutation — D1 delta f3);
                // `broadcastAutoCycle` picks the sku BRANCH. Aug 23 round 2 (Sid):
                // the night-pack auto-cycle is BROADCAST-IDENTITY-ONLY — a normal
                // spectator falls through to the fighter branch below and keeps
                // their own equipped skins + manual Shift, like when they play.
                bool spectatorSeat = RoomActors.LocalIsSpectator;
                bool broadcastAutoCycle = spectatorSeat && BroadcastMode.IsBroadcastIdentity;
                // Set only by the fighter branch, and only for a REAL Shift keypress.
                // The synchronous particle path is gated on it — see the defer decision.
                bool manualShiftNow = false;

                // Broadcast-seat map-skin test lever (bug 249). The broadcast account owns
                // no map colours, and the spectator cycle only runs inside a live spectate
                // session, so before this there was NO way to look at a skin on the seat
                // that renders the stream — every background theory had to be argued from
                // logs. Gated on the broadcast identity, so it is not a free-cosmetics
                // switch for players; the skin is a purely local render either way.
                string testSkin = null;
                try
                {
                    if (BroadcastMode.IsBroadcastIdentity && Plugin.BroadcastTestMapSkin != null)
                        testSkin = (Plugin.BroadcastTestMapSkin.Value ?? "").Trim();
                }
                catch { }
                if (!string.IsNullOrEmpty(testSkin))
                {
                    if (string.Equals(testSkin, "cycle", StringComparison.OrdinalIgnoreCase))
                    {
                        spectatorSeat = true;          // exercise the real spectator path
                        broadcastAutoCycle = true;     // (lever is already identity-gated above)
                    }
                    else
                    {
                        testSkin = ResolveTestSkin(testSkin);   // single sku or the tour element
                        if (!string.IsNullOrEmpty(testSkin) && !CustomMapColors.IsCustomSku(testSkin))
                        {
                            Plugin.Log.LogWarning($"[MAPCOLOR] Broadcast.TestMapSkin='{testSkin}' is not a known sku — ignoring");
                            testSkin = null;
                        }
                    }
                }
                // Turning the lever OFF has to actually let go: MapColorState.CurrentSku
                // still holds the test sku, so the next Map.Start would re-apply it and
                // the seat would look "stuck" on a skin nobody selected (Codex finding 6).
                if (string.IsNullOrEmpty(testSkin) && !string.IsNullOrEmpty(_lastTestSkin))
                {
                    Plugin.Log.LogInfo($"[MAPCOLOR] Broadcast.TestMapSkin cleared (was '{_lastTestSkin}') — releasing the pinned skin");
                    MapColorState.CurrentSku = null;
                    MapPhysicalColorPatch.SupersedePendingTints();
                    ResetSpectatorCycle();
                    MapPhysicalColorPatch.RestoreVanillaBackdrop("test skin cleared");
                }
                _lastTestSkin = testSkin;

                string sku = null;
                if (!string.IsNullOrEmpty(testSkin) && !string.Equals(testSkin, "cycle", StringComparison.OrdinalIgnoreCase))
                {
                    sku = testSkin;
                    Plugin.Log.LogInfo($"[MAPCOLOR] Broadcast.TestMapSkin pinned → {sku}");
                }
                else if (broadcastAutoCycle)
                {
                    sku = NextSpectatorCycleSku();
                }
                else
                {
                var s = ApiClient.CachedPlayerStats;
                // Multi-equip: pick the next sku in the equipped-colors list on each press.
                // Filter null/empty entries so a corrupted server response doesn't
                // promote vanilla into the cycle.
                var rawEquipped = s?.active_color_skus;
                List<string> equipped = null;
                if (rawEquipped != null && rawEquipped.Count > 0)
                {
                    equipped = new List<string>(rawEquipped.Count);
                    for (int i = 0; i < rawEquipped.Count; i++)
                    {
                        var e = rawEquipped[i];
                        if (!string.IsNullOrEmpty(e)) equipped.Add(e);
                    }
                }
                // The last-known-good list exists to survive mid-session stats CHURN —
                // CachedPlayerStats briefly going null during a refresh or a consent
                // flip — so a Shift in that window doesn't leak a vanilla random art
                // into the rotation.
                //
                // It must NOT survive the user UNEQUIPPING their last map colour. The
                // old test treated "no stats" and "stats say you have none equipped"
                // identically, so taking the final skin off in the shop left it
                // rendering until the game restarted, and there was no way to get back
                // to vanilla at all. Distinguish the two: a PRESENT list is
                // authoritative even when it is empty; only an ABSENT snapshot (or an
                // absent list field, which an older server shape could produce) falls
                // back to the cache.
                // NOT `rawEquipped != null`: ApiClient allocates active_color_skus
                // unconditionally (ApiClient.cs, "Parse active_color_skus"), so the list
                // is never null and that test would call EVERY response authoritative —
                // including one where the field was absent or the parse threw, which
                // would drop the player's skin mid-session and reintroduce the exact bug
                // the last-known-good cache exists to prevent. Use the parser's own
                // "the array was there and I read it" flag instead.
                bool snapshotAuthoritative = s != null && s.active_color_skus_present;
                if (equipped == null || equipped.Count == 0)
                {
                    if (snapshotAuthoritative)
                    {
                        if (_lastEquippedFiltered != null)
                            Plugin.Log.LogInfo("[MAPCOLOR] equipped list is authoritatively EMPTY — dropping the cached list and returning to vanilla");
                        _lastEquippedFiltered = null;
                        _cycleLastListHash = 0;
                        _cycleIndex = 0;
                        equipped = null;
                        // Retire the LIVE selection too, or nothing actually changes:
                        // the deferred vanilla restore bails when MapColorState.CurrentSku
                        // still names a custom skin, and the next Map.Start reads that same
                        // sku and re-applies it — so unequipping your last colour looked
                        // like it did nothing (Codex r3 #2). A non-custom SENTINEL rather
                        // than null, because null makes Map.Start fall back to the legacy
                        // active_color_sku scalar, which can still be the custom sku.
                        MapColorState.CurrentSku = "mapcolor_default";
                    }
                    else if (_lastEquippedFiltered != null)
                    {
                        equipped = _lastEquippedFiltered;
                        Plugin.Log.LogInfo($"[MAPCOLOR] stats snapshot unavailable, reusing last-known list ({equipped.Count} skus)");
                    }
                }
                else
                {
                    _lastEquippedFiltered = equipped;
                }
                if (equipped != null && equipped.Count > 0)
                {
                    int listHash = 0;
                    for (int i = 0; i < equipped.Count; i++) listHash = (listHash * 31) + (equipped[i]?.GetHashCode() ?? 0);
                    if (listHash != _cycleLastListHash)
                    {
                        _cycleIndex = 0;
                        _cycleLastListHash = listHash;
                    }
                    // Advance the cycle ONLY on a real Left-Shift press. ROUNDS also calls
                    // NextArt automatically every round (often 2-3× at round start), and
                    // advancing on those made the skin auto-shuffle unpredictably — Sid kept
                    // landing on the dull brown/grey ones over and over and saw a multi-color
                    // FLICKER as several skus applied in a burst. Gating on Shift keeps the
                    // chosen skin STABLE per round; the player deliberately cycles with Shift.
                    bool manualShift = false;
                    // Item 17: the bound MapSkinCycle control (question 8: its default
                    // is Left Shift alone - the transpiled ArtHandler read is the same row).
                    try { manualShift = Keybinds.Held(KeybindRules.MapSkinCycle); } catch { }
                    manualShiftNow = manualShift;   // consumed by the defer decision below
                    if (manualShift)
                        _cycleIndex = (_cycleIndex + 1) % equipped.Count;
                    sku = equipped[_cycleIndex % equipped.Count];
                    Plugin.Log.LogInfo($"[MAPCOLOR] {(manualShift ? "Shift cycle" : "auto-keep")} → {sku} (index {_cycleIndex}/{equipped.Count})");
                    // Toast the friendly skin name on a manual cycle so the player can find a
                    // specific skin (e.g. Magma) by sight.
                    if (manualShift) MapColorState.ShowToast(CustomMapColors.FriendlyName(sku));
                }
                // Backward compat: fall back to the legacy single-value active_color_sku
                // ONLY when the list field was absent from the response (an older server
                // shape). If the server sent the list and it was empty, that is the
                // authoritative answer and the scalar must not resurrect a skin the
                // player just unequipped (Codex r3 #6).
                if (string.IsNullOrEmpty(sku) && !snapshotAuthoritative) sku = s?.active_color_sku;
                }
                if (string.IsNullOrEmpty(sku))
                {
                    // A vanilla art is about to become live and it grades the canvas
                    // itself (hueShift on the red clear). Hand the clear back, or the
                    // last skin's canvas stays under it — a NEW leak introduced by
                    // painting the clear at all, and the only path that reaches the
                    // menu, where no Map.Start ever fires to restore it.
                    // Retire the live selection first, or the restore we are about to
                    // schedule sees a custom CurrentSku and cancels itself, and the next
                    // Map.Start re-applies the skin (Codex r5 #8 — same shape as r3 #2,
                    // reachable here through the older no-list/no-scalar response).
                    MapColorState.CurrentSku = "mapcolor_default";
                    MapPhysicalColorPatch.RestoreVanillaBackdrop("no sku resolved");
                    Plugin.Log.LogInfo("[MAPCOLOR] No custom sku resolved — falling through to vanilla NextArt");
                    return true;
                }
                // Record the cycle-selected sku so Map.Start / physical-tint re-apply reads the
                // same sku the post-process path is using.
                MapColorState.CurrentSku = sku;

                // Custom-profile path: SetSpecificArt(baseArt) so the vanilla particle bg AND
                // base profile (bloom, vignette, etc.) load. Then ApplyPost(clonedProfile) where
                // the clone is baseArt.profile + our ColorGrading override. Cloning is critical:
                // mutating volume.profile in place corrupts the SHARED art profile for the rest
                // of the session — Sky's vanilla look would gain our tint permanently. The clone
                // is cached per SKU in CustomMapColors.
                if (CustomMapColors.IsCustomSku(sku))
                {
                    string baseArt = CustomMapColors.GetBaseArt(sku);
                    if (string.IsNullOrEmpty(baseArt)) return true;
                    // ROUNDS' ApplyArt (reached via SetSpecificArt) does NOT deactivate the
                    // previously-active art — only NextArt/SetMenuArt call the private TurnArtsOff
                    // first. Calling SetSpecificArt directly therefore leaves the OLD art's
                    // particles Play()-ing alongside the new one → two overlapping art layers (a
                    // second source of texture-flicker, confirmed by decompiling ArtHandler).
                    // Replicate TurnArtsOff via the public ArtInstance.TogglePart so only our
                    // chosen art stays active.
                    // Per-art try/catch, NOT one around the loop: ArtInstance.TogglePart
                    // dereferences every entry of its own parts[] array, so one null or
                    // destroyed part in ANY art used to abort the whole sweep and leave
                    // every later art still playing — including the two Rainbow arts,
                    // which is the exact "purple/pink bleeding into the background" this
                    // loop exists to prevent. The deferred pass below already isolates
                    // per art; match it here.
                    if (__instance.arts != null)
                        foreach (var a in __instance.arts)
                        {
                            try { a?.TogglePart(false); }
                            catch (Exception tx) { Plugin.Log.LogWarning($"[MAPCOLOR] TogglePart(false) failed on an art: {tx.Message}"); }
                        }
                    __instance.SetSpecificArt(baseArt);
                    var basePr = __instance.volume != null ? __instance.volume.profile : null;
                    if (basePr == null)
                    {
                        Plugin.Log.LogWarning($"[MAPCOLOR] sku={sku} — volume.profile null after SetSpecificArt({baseArt})");
                        return false;
                    }
                    var clone = CustomMapColors.BuildOrGetClone(sku, basePr);
                    if (clone == null)
                    {
                        Plugin.Log.LogWarning($"[MAPCOLOR] sku={sku} — clone build failed, leaving base art active");
                        return false;
                    }
                    __instance.ApplyPost(clone);
                    // Backdrop levers that are safe mid-transition (no particle
                    // mutation): camera clears + SFSS light/ambient. Applying here
                    // makes Shift visibly swap the background on the same frame.
                    MapPhysicalColorPatch.ApplyCameraBackground(sku);
                    MapPhysicalColorPatch.ApplyLighting(sku);
                    // Proof line for the grading state actually in effect (residue check).
                    MapPhysicalColorPatch.LogLiveColorGrading(sku, "at-apply");
                    // v1.32 item 7: lighting/shadow disable settings re-assert after
                    // the skin's own lighting pass touched the renderers.
                    MapPhysicalColorPatch.RenderPerfSettings.Apply();
                    // Freshly-built skin clones carry a copied CA object — assert
                    // the toggle on it same-frame.
                    MapPhysicalColorPatch.ChromaticAberrationSetting.Apply();
                    MapPhysicalColorPatch.BloomStrengthSetting.Apply();
                    // Instant/sharp swap (v1.26.10): ROUNDS fades the post-process volume in
                    // gradually, which reads as the map "sliding" into the next skin on Shift.
                    // Force the volume to full weight on the same frame so the new ColorGrading
                    // snaps in immediately instead of lerping. Harmless if ROUNDS already had it
                    // at 1. Wrapped in try/catch since volume is reflected ROUNDS internals.
                    try { if (__instance.volume != null) __instance.volume.weight = 1f; } catch { }
                    // Re-apply wall / atmosphere particle tints for the new sku. CRITICAL: ROUNDS
                    // calls NextArt every round FROM INSIDE MapTransition.Move; mutating particles
                    // then NREs MapTransition+<Move>d__15 and the move STALLS — players don't get
                    // repositioned (stuck mid-screen, then off-screen next round — the freeze).
                    // So defer the particle work past the transition window. A genuine mid-round
                    // MANUAL Shift (well after Map.Start) is safe to apply immediately for snappy
                    // cycling. ColorGrading (ApplyPost, above) is volume-only and stays immediate.
                    bool inTransition = Time.time - MapPhysicalColorPatch.LastMapStartTime
                                        < MapPhysicalColorPatch.MapTransitionGuardSec;
                    // Spectator seat: ALWAYS defer (D1 delta f3). bug-233's log proved
                    // NextArt can run inside MapTransition.Move with this inTransition
                    // test FALSE (the call landed before Map.Start stamped
                    // LastMapStartTime), so the synchronous branch is never safe here —
                    // and there is no manual Shift on this seat to need it. Only the
                    // index ADVANCE is debounced: ScheduleDeferredTints pushes
                    // _tintNotBefore on EVERY call, so each duplicate NextArt request
                    // still pushes the deadline past its own transition window (#365).
                    // WHO MAY MUTATE PARTICLES SYNCHRONOUSLY: only a real, mid-battle
                    // Shift press. Everything else defers.
                    //
                    // `inTransition` alone was never a sufficient test and this is the
                    // bug it hid: ROUNDS fires NextArt from MapTransition's switchMapEvent,
                    // which can land BEFORE the incoming Map.Start stamps LastMapStartTime,
                    // so the stamp is the PREVIOUS map's and `inTransition` reads FALSE
                    // while we are squarely inside MapTransition.Move. The synchronous
                    // branch then calls SetParticles mid-move — the #45/#85 stall that
                    // leaves players unmoved, then off-screen the next round.
                    // bug-235.txt:594-603 catches a fighter doing exactly this today.
                    //
                    // The original intent was always "immediate ONLY for a genuine
                    // mid-round manual Shift" (see the note below); this makes the code
                    // say that, instead of inferring it from a timestamp that lies.
                    bool testPinned = !string.IsNullOrEmpty(testSkin);
                    bool battleOngoing = false;
                    try { battleOngoing = GameManager.instance != null && GameManager.instance.battleOngoing; } catch { }
                    // `Input.GetKey` reports key STATE, not call ORIGIN: a player holding
                    // Shift while ROUNDS fires its own transition-owned NextArt looks
                    // identical to a deliberate press. That is only safe because the
                    // authoritative transition test below rejects the automatic call —
                    // the stale-stamp `inTransition` alone did not (Codex r4 #3, which
                    // reproduces on the FFA start path where battleOngoing is already
                    // true before the move finishes).
                    bool immediateOk = manualShiftNow && battleOngoing && !inTransition
                                       && !MapPhysicalColorPatch.InMapTransition()
                                       && !spectatorSeat && !testPinned;
                    bool deferParticles = !immediateOk;
                    if (deferParticles)
                        MapPhysicalColorPatch.ScheduleDeferredTints(sku);
                    else
                    {
                        // Immediate apply retires any sleeping deferred pass
                        // (review r2 MEDIUM — see SupersedePendingTints).
                        MapPhysicalColorPatch.SupersedePendingTints();
                        MapPhysicalColorPatch.ApplyPhysicalTintsForSku(null, sku);
                    }
                    Plugin.Log.LogInfo($"[MAPCOLOR] applied custom sku={sku} on base='{baseArt}' (deferParticles={deferParticles})");
                    return false;
                }

                // Broadcast auto-cycle never reaches the branches below:
                // BroadcastCycleSkus holds only CustomMapColors preset skus
                // (IsCustomSku is true by construction), so the SKU_TO_ART /
                // vanilla fallthrough — including the explicit-"default"
                // restore — stays fighter/normal-spectator-only.
                // Every branch below hands the scene to a VANILLA art, which grades the
                // untouched red clear with its own hueShift. Whatever the previous
                // custom skin painted — canvas, SFSS light/ambient, sky particles —
                // has to go back first, or a fighter who Shifts from Abyss to Sky sees
                // Abyss's canvas under Sky's grading (Codex finding 5).
                MapPhysicalColorPatch.RestoreVanillaBackdrop($"vanilla-styled sku {sku}");
                // Record the SELECTED sku rather than nulling (Codex r2 #5): a null
                // makes Map.Start fall back to the legacy active_color_sku, which can
                // be a CUSTOM skin — that schedules a tint generation which cancels
                // this restore and then skips itself on the CurrentSku check, so
                // neither lands and the previous skin's background survives. Every
                // consumer already gates on IsCustomSku, and no vanilla-styled sku is
                // in the preset table, so storing it reads as "vanilla" everywhere.
                MapColorState.CurrentSku = sku;
                if (!SKU_TO_ART.TryGetValue(sku, out string artName))
                {
                    Plugin.Log.LogWarning($"[MAPCOLOR] Unknown sku '{sku}' — not in CustomMapColors presets, not in vanilla SKU_TO_ART. Equipped but not renderable; falling through to vanilla.");
                    return true;
                }
                if (string.IsNullOrEmpty(artName)) return true;        // explicit "default" sku

                // Safety: only override if the named art actually exists on this ArtHandler
                // instance. Earlier shipped a dict with guessed names that didn't match — the
                // SetSpecificArt no-op left the map invisible because we'd already short-
                // circuited the original NextArt. Now we fall through to vanilla random when
                // the name isn't found, so a stale config can never blank the map again.
                bool found = false;
                if (__instance.arts != null)
                {
                    var profileField = typeof(ArtInstance).GetField("profile",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                    foreach (var art in __instance.arts)
                    {
                        if (art == null) continue;
                        var profileObj = profileField?.GetValue(art) as UnityEngine.Object;
                        if (profileObj != null && profileObj.name == artName) { found = true; break; }
                    }
                }
                if (!found)
                {
                    Plugin.Log.LogWarning($"[MAPCOLOR] sku={sku} mapped to art='{artName}' but no matching art on this ArtHandler — falling through to vanilla random");
                    return true;
                }
                // ROUNDS' SetSpecificArt reaches ApplyArt, which does NOT turn the
                // other arts off (only NextArt/SetMenuArt do). Without this, picking a
                // vanilla-styled skin layers it on top of whatever art the previous
                // skin lit — the same overlap the custom branch above already guards
                // against (Codex r2 #4). SetActive/Play only, no particle mutation, so
                // this is safe in the synchronous path exactly as it is up there.
                if (__instance.arts != null)
                    foreach (var a in __instance.arts)
                    {
                        try { a?.TogglePart(false); }
                        catch (Exception tx) { Plugin.Log.LogWarning($"[MAPCOLOR] TogglePart(false) failed on an art: {tx.Message}"); }
                    }
                __instance.SetSpecificArt(artName);
                return false;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[MAPCOLOR] NextArt prefix failed: {ex.Message}");
                return true;
            }
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Bug #308 — Hit% saturating at exactly 100%.
    //
    // THE DEFECT. The two halves of the accuracy fraction were filtered
    // asymmetrically. The DENOMINATOR (Gun.Attack Postfix) rejected every
    // forceAttack volley — card-driven rings, spawned shooters — on the owner's
    // ruling that those are not "shots". The NUMERATOR (ProjectileHit.RPCA_DoHit
    // Prefix) had NO origin test at all and counted any unblocked enemy impact by
    // any projectile the local player owned. _hitsRemaining is mutated during an
    // active tracking epoch at exactly two sites (plus its per-match resets), so
    // within a match it equals fired - hit, and every uncounted-fired projectile
    // that lands eats budget a real trigger pull paid for. Once it
    // reaches zero, hit == fired and the display SATURATES at exactly 100%,
    // indistinguishable from perfect aim. Regression datable: the numerator moved
    // to RPCA_DoHit in v1.31.0 while both halves still counted forced volleys, and
    // v1.34.0 added the forceAttack reject to the denominator ONLY.
    //
    // THE SHAPE THAT SURVIVED DESIGN REVIEW:
    //   verified input attack -> captured intent -> DoAttacks iterator ->
    //   FireBurst iterator -> ApplyPlayerStuff birth record + fired count ->
    //   FIRST qualifying ProjectileHit credit
    //
    // Both halves are now decided by the SAME fact, recorded at the SAME moment: a
    // bullet may score only if its birth was ACCEPTED into the denominator
    // (TagState.FiredCounted). "Deliberate" alone is NOT enough — that was review
    // find 1, and it left the original asymmetry reachable. Fixing
    // only the numerator would have pushed honest players' accuracy DOWN, which is
    // visibly harmful; birth-time eligibility for both sides keeps the fraction
    // symmetric.
    //
    // FAIL-CLOSED. Unknown provenance contributes NEITHER a fired bullet NOR a
    // hit. `!forceAttack` alone is not a provenance token — its actual vanilla
    // guarantee is only "bypass cooldown/reload", so a future or third-party card
    // calling gun.Attack(0f) without it would be tagged deliberate. Intent is
    // therefore captured at WeaponHandler.Attack (the verified player-input
    // funnel, and the only NON-FORCED gun.Attack found in the vanilla assembly —
    // the forced callers include BulletPoint, GeneralShooter, RadarShot,
    // RotatingShooter, SpawnObjectEffect and SyncPlayerMovement's Shoot RPC; that
    // list is what was observed, not a proof of exhaustiveness) and
    // carried through the two iterators. Remote peers run the ProjectileInit RPC
    // handlers with no FireBurst context and so record false — correct, and
    // harmless because the hit patch already rejects projectiles whose ownPlayer
    // is not local.
    //
    // COMPLETE as of this batch. Parts 5a (split bullet/block floors), 6 (the
    // cr_gstats semantic epoch, incl. the derived opp_hit_timeline and the
    // 2v2/1v2/FFA peer path) and 7 (the asymmetric fired-side gate) have all
    // landed. The original text is kept below because the REASONING is still
    // the reason the epoch exists -- only the "must NOT be released" status has
    // changed, and leaving a stale ship-block in place is its own hazard.
    //
    // HISTORICAL, the design review's requirement: this had to ship as ONE
    // statistics epoch with two further parts that live outside this file: a lifetime
    // bullets_fired/bullets_hit reset behind a NEW bullet-specific clean-version
    // floor (the existing STATS_CLEAN_MIN_VERSION is "1.34.0" — the very release
    // that opened this leak — and it also gates block counters, so the floors must
    // be split), and a semantic epoch on the cr_gstats peer broadcast so a fixed
    // client renders an old peer's Hit% as unknown rather than blending two
    // definitions. Until those land this must NOT be released, or it publishes a
    // third mutually-incompatible Hit% era.
    internal static class ShotProvenance
    {
        internal sealed class TagState
        {
            /// <summary>Born of a verified player-initiated volley.</summary>
            internal bool Deliberate;
            /// <summary>This projectile was ACCEPTED into the denominator. Review
            /// find 1 (HIGH): provenance alone is not eligibility. A deliberate
            /// bullet whose fired count was refused — by the combat window, by
            /// ownership, or by GameStateWatcher's own inner gate — must never be
            /// allowed to score a hit, or it consumes budget belonging to a
            /// projectile that WAS counted and re-creates the exact asymmetry this
            /// whole change exists to remove. Reachable in stock play: a burst's
            /// later FireBurst iterations can birth bullets after the point ends,
            /// be refused the fired count, survive map cleanup into the next
            /// round, and then land.</summary>
            internal bool FiredCounted;
            /// <summary>First qualifying enemy impact only.</summary>
            internal bool HitCredited;
            /// <summary>Projectile-lifetime generation. NOT the cr_gstats
            /// statistics epoch of part 6 — different concept, different
            /// lifetime; conflating them was review find 5.</summary>
            internal int Generation;
        }

        // Aggregate, SATURATING, reason-coded rejection counters (review find 4;
        // saturation added in r2 find 3 — they were described as capped while
        // every update was an unrestricted ++).
        // Without these, "the patch attached but provenance never arrived" is
        // indistinguishable from an intentional fail-closed exclusion — the #83
        // ambiguity. Summed per generation and emitted once, never per projectile.
        internal static int RejNoProvenance;   // ActiveGun mismatch / no volley context
        internal static int RejNotOwner;       // deliberate, but not our projectile
        internal static int RejWindowClosed;   // deliberate + ours, but battle not ongoing
        internal static int RejFiredRefused;   // denominator call did not take it
        internal static int AcceptedFired;     // counted into the denominator

        private static readonly System.Runtime.CompilerServices.ConditionalWeakTable<ProjectileHit, TagState> _tags =
            new System.Runtime.CompilerServices.ConditionalWeakTable<ProjectileHit, TagState>();

        // Keyed by the ProjectileHit itself, never by instance id: an id-keyed
        // dictionary cannot survive Unity id reuse by an object that never passes
        // through BulletInit, which would hand a stale `true` to an untagged
        // projectile. The weak table dies with the object and cannot alias.
        // The generation is belt: a POOLED ProjectileHit that reached the hit
        // path across a match boundary without a fresh BulletInit fails closed.
        internal static int Generation;

        // Set while WeaponHandler.Attack is on the stack — the player-input funnel.
        internal static Gun InputAttackGun;
        // Set by the Gun.Attack prefix and read when vanilla constructs the
        // DoAttacks iterator, which happens inside that same Attack call. (The
        // synchronous-first-MoveNext detail matters one layer down, for carrying
        // the context into FireBurst — not for constructing DoAttacks.)
        internal static Gun PendingGun;
        internal static bool PendingDeliberate;
        // Live only around a FireBurst MoveNext, which is where bullets are born.
        internal static Gun ActiveGun;
        internal static bool ActiveDeliberate;

        /// <summary>The combat window, applied at BIRTH ONLY — deliberately not at
        /// the hit (review r2 find 1: gating both ends rejected the landing of a
        /// projectile fired during battle whose point ended mid-flight, which is
        /// the asymmetry inverted). Eligibility is frozen once, in
        /// TagState.FiredCounted; do not re-add a window check on the hit side.
        ///
        /// `inPickPhase` was rejected in design review as the predicate: it is
        /// driven by debug-log TEXT, it is explicitly false from "Round over" until
        /// "PICK PHASE" (~2.3s later, so post-round impacts still counted), and it
        /// is never true for point transitions without card selection.
        /// battleOngoing is real game state.</summary>
        internal static bool WindowOpen()
        {
            try { return GameManager.instance != null && GameManager.instance.battleOngoing; }
            catch { return false; }
        }

        internal static TagState Tag(ProjectileHit ph, bool deliberate)
        {
            if (ph == null) return null;
            TagState s;
            if (!_tags.TryGetValue(ph, out s))
            {
                s = new TagState();
                _tags.Add(ph, s);
            }
            // ALWAYS overwrite, never conditionally: bullets are pooled, and an
            // unconditional write is the only thing that makes reuse safe.
            s.Deliberate = deliberate;
            s.FiredCounted = false;     // earned at the denominator, not here
            s.HitCredited = false;
            s.Generation = Generation;
            return s;
        }

        /// <summary>Marks a birth as ACCEPTED into the denominator. Only a
        /// projectile that reaches this may ever score a hit.</summary>
        internal static void MarkFiredCounted(ProjectileHit ph)
        {
            if (ph == null) return;
            TagState s;
            if (_tags.TryGetValue(ph, out s)) s.FiredCounted = true;
        }

        /// <summary>Hands back the one hit credit when the counter refused the
        /// impact, so a later legitimate impact from the same projectile can still
        /// score. Only ever called after TryConsumeHit returned true.</summary>
        internal static void ReleaseHitCredit(ProjectileHit ph)
        {
            if (ph == null) return;
            TagState s;
            if (_tags.TryGetValue(ph, out s)) s.HitCredited = false;
        }

        internal static bool TryConsumeHit(ProjectileHit ph)
        {
            if (ph == null) return false;
            TagState s;
            if (!_tags.TryGetValue(ph, out s)) return false;   // unknown -> not counted
            if (!s.Deliberate || s.Generation != Generation) return false;
            // The symmetry guard. Not merely "was it deliberate" but "was it
            // actually counted as fired" — see TagState.FiredCounted.
            if (!s.FiredCounted) return false;
            if (s.HitCredited) return false;                    // first enemy impact only
            s.HitCredited = true;
            return true;
        }

        /// <summary>Saturating, so a pathological session cannot wrap a counter
        /// into a misleading value (review r2 find 3).</summary>
        private static void Bump(ref int counter)
        {
            if (counter < int.MaxValue) counter++;
        }

        internal static void Bump(Reason r)
        {
            switch (r)
            {
                case Reason.NoProvenance:    Bump(ref RejNoProvenance); break;
                case Reason.NotOwner:        Bump(ref RejNotOwner); break;
                case Reason.WindowClosed:    Bump(ref RejWindowClosed); break;
                case Reason.FiredRefused:    Bump(ref RejFiredRefused); break;
                case Reason.Accepted:        Bump(ref AcceptedFired); break;
            }
        }

        internal enum Reason { NoProvenance, NotOwner, WindowClosed, FiredRefused, Accepted }

        /// <summary>Logging that can never escape into a combat path. BepInEx 5's
        /// logger dispatches listeners without exception isolation, so a throwing
        /// third-party listener propagates straight back into the caller — which,
        /// on a correctness path, is how a diagnostic silently becomes a gameplay
        /// defect (review r2 find 2).</summary>
        internal static void SafeLog(string msg)
        {
            try { Plugin.Log.LogInfo(msg); } catch { }
        }

        private static string SummaryLine(string why)
        {
            if (AcceptedFired == 0 && RejNoProvenance == 0 && RejNotOwner == 0
                && RejWindowClosed == 0 && RejFiredRefused == 0)
                return null;
            return $"[HIT-PROV] gen {Generation} births ({why}): counted={AcceptedFired}" +
                   $" rejected(no-provenance={RejNoProvenance} not-owner={RejNotOwner}" +
                   $" window-closed={RejWindowClosed} fired-refused={RejFiredRefused})";
        }

        internal static void NewGeneration(string why)
        {
            // STATE FIRST, LOGGING LAST (review r2 find 2). An earlier version
            // logged the outgoing tally before resetting and incrementing; a
            // throwing log listener then meant the generation never advanced, and
            // a live tag from the previous match stayed eligible to consume the
            // new match's hit budget. Nothing below this line may gate the bump.
            string summary = null;
            try { summary = SummaryLine(why); } catch { }

            RejNoProvenance = RejNotOwner = RejWindowClosed = 0;
            RejFiredRefused = AcceptedFired = 0;
            unchecked { Generation++; }

            if (summary != null) SafeLog(summary);
            SafeLog($"[HIT-PROV] projectile generation -> {Generation} ({why})");
        }
    }

    /// <summary>Marks the player-input attack funnel. WeaponHandler.Attack
    /// (WeaponHandler.cs:115) is the only NON-FORCED gun.Attack found in the vanilla
    /// assembly; the forced callers observed are BulletPoint, GeneralShooter,
    /// RadarShot, RotatingShooter, SpawnObjectEffect and SyncPlayerMovement's Shoot
    /// RPC. That list is what was observed, not a proof of exhaustiveness — which is
    /// exactly why provenance is fail-closed rather than a denylist. Finalizer, not
    /// Postfix, so the marker is restored even if vanilla throws.</summary>
    [HarmonyPatch(typeof(WeaponHandler), "Attack")]
    class WeaponHandlerAttackIntentPatch
    {
        static void Prefix(WeaponHandler __instance, out Gun __state)
        {
            __state = ShotProvenance.InputAttackGun;
            try { ShotProvenance.InputAttackGun = __instance != null ? __instance.gun : null; }
            catch { ShotProvenance.InputAttackGun = null; }
        }

        static void Finalizer(Gun __state)
        {
            ShotProvenance.InputAttackGun = __state;   // restore, never blind-clear
        }
    }

    /// <summary>Captures whether THIS Attack is deliberate, for the DoAttacks
    /// iterator that vanilla is about to construct. Deliberate requires both
    /// !forceAttack AND that we are inside WeaponHandler.Attack for this same gun.</summary>
    [HarmonyPatch(typeof(Gun), "Attack")]
    class GunAttackIntentCapturePatch
    {
        // __state saves the OUTER pending context; the Finalizer restores it.
        // Review find 3: overwriting it unconditionally is not re-entrancy-safe.
        // Gun.DoAttack invokes attackAction() immediately before constructing its
        // FireBurst, and AddAttackAction is public — so a nested forced Attack can
        // run between an outer deliberate Attack and the FireBurst that carries its
        // intent. Without save/restore the nested call's DoAttacks postfix consumes
        // and clears Pending, and the OUTER player-fired projectiles are then
        // excluded from BOTH halves. A Finalizer also cleans up the cooldown/reload
        // `false` return and the F5 suppression path, neither of which reaches a
        // DoAttacks postfix to consume the value.
        [HarmonyPriority(Priority.First)]
        static void Prefix(Gun __instance, bool forceAttack, out ValueTuple<Gun, bool> __state)
        {
            __state = new ValueTuple<Gun, bool>(ShotProvenance.PendingGun, ShotProvenance.PendingDeliberate);
            try
            {
                ShotProvenance.PendingGun = __instance;
                ShotProvenance.PendingDeliberate =
                    !forceAttack && ReferenceEquals(ShotProvenance.InputAttackGun, __instance);
            }
            catch { ShotProvenance.PendingGun = null; ShotProvenance.PendingDeliberate = false; }
        }

        static void Finalizer(ValueTuple<Gun, bool> __state)
        {
            ShotProvenance.PendingGun = __state.Item1;
            ShotProvenance.PendingDeliberate = __state.Item2;
        }
    }

    /// <summary>Carries the captured intent through the DoAttacks iterator, which
    /// spans frames (it waits 0.3s/attacks between charge volleys).</summary>
    [HarmonyPatch(typeof(Gun), "DoAttacks")]
    class GunDoAttacksIntentPatch
    {
        static void Postfix(Gun __instance, ref IEnumerator __result)
        {
            try
            {
                if (__result == null) return;
                bool deliberate = ShotProvenance.PendingDeliberate
                                  && ReferenceEquals(ShotProvenance.PendingGun, __instance);
                ShotProvenance.PendingGun = null;          // consume
                ShotProvenance.PendingDeliberate = false;
                __result = Carry(__instance, deliberate, __result);
            }
            catch (Exception ex) { ShotProvenance.SafeLog($"[HIT-PROV] DoAttacks wrap failed: {ex.Message}"); }
        }

        static IEnumerator Carry(Gun gun, bool deliberate, IEnumerator inner)
        {
            while (true)
            {
                bool moved;
                var pg = ShotProvenance.PendingGun;
                var pd = ShotProvenance.PendingDeliberate;
                ShotProvenance.PendingGun = gun;
                ShotProvenance.PendingDeliberate = deliberate;
                try { moved = inner.MoveNext(); }
                finally { ShotProvenance.PendingGun = pg; ShotProvenance.PendingDeliberate = pd; }
                if (!moved) yield break;
                yield return inner.Current;
            }
        }
    }

    /// <summary>The layer that actually matters: bullets are born inside
    /// FireBurst's MoveNext. Save/set/finally/restore rather than blind-clear, so a
    /// forced volley nested inside a deliberate one restores the outer context
    /// instead of destroying it. (The Pending layer needed the same treatment and
    /// lacked it until review find 3 — it is now saved and restored by the
    /// Gun.Attack prefix/finalizer pair.) Note the vanilla wait at Gun.cs:498-500 is per
    /// BURST, not per bullet — one MoveNext can birth a whole batch.</summary>
    [HarmonyPatch(typeof(Gun), "FireBurst")]
    class GunFireBurstProvenancePatch
    {
        static void Postfix(Gun __instance, ref IEnumerator __result)
        {
            try
            {
                if (__result == null) return;
                bool deliberate = ShotProvenance.PendingDeliberate
                                  && ReferenceEquals(ShotProvenance.PendingGun, __instance);
                __result = Bracket(__instance, deliberate, __result);
            }
            catch (Exception ex) { ShotProvenance.SafeLog($"[HIT-PROV] FireBurst wrap failed: {ex.Message}"); }
        }

        static IEnumerator Bracket(Gun gun, bool deliberate, IEnumerator inner)
        {
            while (true)
            {
                bool moved;
                var ag = ShotProvenance.ActiveGun;
                var ad = ShotProvenance.ActiveDeliberate;
                ShotProvenance.ActiveGun = gun;
                ShotProvenance.ActiveDeliberate = deliberate;
                try { moved = inner.MoveNext(); }
                finally { ShotProvenance.ActiveGun = ag; ShotProvenance.ActiveDeliberate = ad; }
                if (!moved) yield break;
                yield return inner.Current;
            }
        }
    }

    /// <summary>Birth record AND the denominator. The counting boundary is a
    /// projectile that successfully reached OWNERSHIP ASSIGNMENT in
    /// ApplyPlayerStuff — not "a successful BulletInit" (review r4 find 3): later
    /// work in BulletInit, a ShootPojectileAction subscriber or gunAmmo.Shoot, may
    /// still fail afterwards. Counting it anyway is correct, because by that point
    /// the projectile exists, has its stats applied and has an owner, so it is a
    /// real birth capable of hitting. Counting births is what makes the denominator
    /// correct for free:
    /// vanilla births bursts x projectiles.Length x (numberOfProjectiles +
    /// RoundToInt(chargeNumberOfProjectilesTo * charge)), clamped and overridden to
    /// 1 by lockGunToDefault (Gun.cs:423, 433-437). The old Attack-time formula
    /// computed numberOfProjectiles * bursts * attacks — it omitted the prefab
    /// array and the charge term (under-counting, so accuracy read HIGH) and
    /// over-counted lock-to-default guns. Counting births also handles spawn
    /// failures for free.</summary>
    // Hooked on ApplyPlayerStuff, NOT on BulletInit (review r3 find 2). Vanilla's
    // order inside BulletInit is:
    //     ApplyPlayerStuff(bullet);          <- ownPlayer is now set
    //     if (ShootPojectileAction != null) ShootPojectileAction(bullet);
    //     gunAmmo.Shoot(bullet);
    // A BulletInit POSTFIX therefore tags AFTER ShootPojectileAction, which is a
    // public synchronous extension seam cards subscribe to. A subscriber that makes
    // the just-initialised projectile hit an enemy synchronously would reach
    // RPCA_DoHit while the projectile is still UNTAGGED: the hit is refused, then
    // the Postfix accepts the fired count — fired +1, hit +0, the asymmetry again.
    // ApplyPlayerStuff is private with exactly ONE caller (Gun.cs:524), so a
    // Postfix on it lands after ownPlayer is assigned and before that seam can run.
    [HarmonyPatch(typeof(Gun), "ApplyPlayerStuff")]
    class GunApplyPlayerStuffProvenancePatch
    {
        private static bool _firstDeliberateLogged;

        static void Postfix(Gun __instance, GameObject obj)
        {
            var bullet = obj;
            try
            {
                if (bullet == null) return;
                var ph = bullet.GetComponent<ProjectileHit>();
                // Defensive only — NOT a diagnostic bucket (review r4 find 2).
                // Vanilla dereferences ProjectileHit in ApplyProjectileStats
                // (Gun.cs:563) and in ApplyPlayerStuff itself (Gun.cs:551), so a
                // bullet without one makes the ORIGINAL throw before any Postfix
                // of ours runs. A counter here could never be non-zero.
                if (ph == null) return;

                bool deliberate = ShotProvenance.ActiveDeliberate
                                  && ReferenceEquals(ShotProvenance.ActiveGun, __instance);
                // Tag every birth unconditionally — pooled reuse is only safe
                // because this always overwrites. FiredCounted starts false and is
                // EARNED below; provenance is not eligibility (review find 1).
                ShotProvenance.Tag(ph, deliberate);
                if (!deliberate) { ShotProvenance.Bump(ShotProvenance.Reason.NoProvenance); return; }

                // Owner-side only, and only inside the BIRTH-TIME combat window
                // (never re-add a window check on the hit side — review r2 find 1).
                var pv = __instance != null && __instance.player != null
                    ? __instance.player.data?.view : null;
                if (pv == null || !pv.IsMine) { ShotProvenance.Bump(ShotProvenance.Reason.NotOwner); return; }
                if (!ShotProvenance.WindowOpen()) { ShotProvenance.Bump(ShotProvenance.Reason.WindowClosed); return; }

                // Did the denominator ACTUALLY take it? OnLocalBulletFired is void
                // and carries its own inner gate (isTracking, and historically inPickPhase) which
                // lives in a file this change cannot edit, so acceptance is
                // observed rather than assumed: the counter is read either side of
                // the synchronous call. Only an accepted birth may later score.
                int before = GameStateWatcher.LocalBulletsFiredThisMatch;
                // The call is wrapped and the after-read ALWAYS happens (review r2
                // find 2). If the denominator throws part-way — or a log listener
                // inside it does — the counter may still have moved, and the tag
                // must reflect what the counter actually says rather than whether
                // control reached the next line. Anything else lets the denominator
                // accept a projectile whose tag denies it, which is finding 1 in
                // yet another disguise.
                try { GameStateWatcher.OnLocalBulletFired(1); }
                catch { /* observed via the delta below */ }

                bool accepted;
                try { accepted = GameStateWatcher.LocalBulletsFiredThisMatch > before; }
                catch { accepted = false; }

                if (!accepted)
                {
                    ShotProvenance.Bump(ShotProvenance.Reason.FiredRefused);
                    return;                       // stays FiredCounted == false
                }
                ShotProvenance.MarkFiredCounted(ph);
                ShotProvenance.Bump(ShotProvenance.Reason.Accepted);
                if (!_firstDeliberateLogged)
                {
                    _firstDeliberateLogged = true;
                    ShotProvenance.SafeLog("[HIT-PROV] first deliberate bullet counted at ApplyPlayerStuff");
                }
            }
            catch (Exception ex) { ShotProvenance.SafeLog($"[HIT-PROV] ApplyPlayerStuff tag failed: {ex.Message}"); }
        }
    }

    /// <summary>Bumps the PROJECTILE-LIFETIME GENERATION so a pooled projectile
    /// cannot carry a deliberate tag across a match boundary. This is NOT the
    /// cr_gstats statistics epoch that part 6 still owes — different concept,
    /// different lifetime, and conflating the two was review find 5. Both hooks are
    /// needed: GM_ArmsRace.StartGame does NOT fire on same-room rematches
    /// (learning #138), PlayerManager.ResetCharacters does.</summary>
    [HarmonyPatch]
    class ShotProvenanceEpochPatch
    {
        // GM_ArmsRace.StartGame's whole body is `if (!GameManager.instance.isPlaying)`,
        // and PlayerJoined calls it whenever the registered-player count meets the
        // threshold — so a legitimate reconnect mid-round invokes a NO-OP StartGame.
        // Harmony still runs the postfix, so bumping unconditionally would stale
        // every live projectile tag and silently drop their legitimate hits
        // (review find 2; the same trap as learning #280). Bump only on a real
        // false -> true transition.
        [HarmonyPrefix]
        [HarmonyPatch(typeof(GM_ArmsRace), "StartGame")]
        static void BeforeStartGame(out bool __state)
        {
            __state = false;
            try { __state = GameManager.instance != null && GameManager.instance.isPlaying; } catch { }
        }

        [HarmonyPostfix]
        [HarmonyPatch(typeof(GM_ArmsRace), "StartGame")]
        static void AfterStartGame(bool __state, bool __runOriginal)
        {
            try
            {
                // __runOriginal (review r4 find 1). NOTE the reason, because an
                // earlier version of this comment — and the review finding it came
                // from — stated it backwards: a Priority.First suppressor does NOT
                // stop sibling prefixes. Per learning #352, verified against the
                // shipped 0Harmony.dll, HarmonyX runs EVERY prefix and `return
                // false` skips only the ORIGINAL. So the Prefix above does run and
                // __state is accurate. What the suppressor removes is the original
                // body — so isPlaying never flips, and this call must not be read
                // as a false -> true transition even though __state says false.
                if (!__runOriginal) return;
                if (__state) return;                     // was already playing: no-op call
                if (GameManager.instance == null || !GameManager.instance.isPlaying) return;
                ShotProvenance.NewGeneration("StartGame");
            }
            catch { }
        }

        [HarmonyPostfix]
        [HarmonyPatch(typeof(PlayerManager), "ResetCharacters")]
        static void AfterResetCharacters() { try { ShotProvenance.NewGeneration("ResetCharacters"); } catch { } }
    }
}
