using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace CompetitiveRounds
{
    /// <summary>
    /// Player Cards portrait SPIKE (design pass 2026-09-11, Nic's request): render the
    /// local player's in-game character — particle body, IK legs, arms, the held gun,
    /// the block orb, face items at their saved offsets, the equipped colour and effect
    /// cosmetics — offscreen into a PNG, from the main menu, with no match running.
    ///
    /// Rig recipe (decompile-verified per component, see the design notes in
    /// ai-collab/sept10-batch/STATE.md "PORTRAIT PIVOT"):
    ///   * PlayerAssigner.instance.playerPrefab is instantiated under an INACTIVE parent
    ///     parked far from the live view, so no Awake/Start runs until the rig is shaped.
    ///   * Every PhotonView is destroyed before activation. Match-time behaviours are
    ///     DISABLED (not destroyed — CharacterData caches them as fields): Player (its
    ///     Start registers with PlayerManager and needs a PhotonView), GeneralInput, Aim,
    ///     PlayerCollision, HoldingObject (derefs CardChoice.instance), CopyChildren,
    ///     PlayerSounds, PlayerJump, PlayerAPI, WeaponHandler, and Gun on the spawned gun
    ///     (its Update derefs GameManager.instance). Player.data is wired by hand because
    ///     Player.Awake no longer runs for us; PlayerVelocity.simulated=false and
    ///     isPlaying=false hold the body still and gate the movement/block/weapon Updates.
    ///   * Kept: CharacterData, Holding (spawns the gun), PlayerSkinHandler (spawns the
    ///     particle body), SetPlayerSpriteLayer (masks), legs/arms IK, Block +
    ///     SetColorByBlockCD (the orb), CharacterCreatorItemEquipper (the face).
    ///   * Team colour = SetTeamColor.TeamColorThis with skin 0 (what Player.SetColors
    ///     does), the face = SpawnPlayerFace(selected preset), cosmetics via the existing
    ///     colour/effect classes, then a settle window, a layer re-stamp (#299 item 4),
    ///     and an isolated orthographic camera into a square RenderTexture.
    ///   * Learning #139: vanilla materials may be SFSS-lit and render nothing on an
    ///     isolated camera, so the spike renders twice — original materials, then every
    ///     renderer swapped to a per-instance unlit material — and reports both.
    ///
    /// Dev lever only (broadcast identity, TickTestPlayerCards):
    ///   TestPlayerCards = portrait:dump
    ///   TestPlayerCards = portrait:run[,size=N][,settle=SECONDS][,preset=N][,noground]
    ///                                [,nocolor][,noeffect][,nolit][,color=RRGGBB][,effect=SKU]
    /// Output: BepInEx/pc_portrait_{lit,unlit,alpha}.png, pc_portrait_report.txt,
    /// pc_portrait_dump.txt. No product surface uses this class yet.
    /// </summary>
    internal static class PortraitRender
    {
        private static readonly Vector3 PARK = new Vector3(4000f, 4000f, 0f);
        private const int DEFAULT_SIZE = 1180;         // 2x the 590 px portrait window (v21 §9)
        private const float DEFAULT_SETTLE = 1.0f;
        private const int PORTRAIT_ACTOR = -7777;      // synthetic actor id for the cosmetic classes
        private const byte PROBE_FLOOR = 8;

        private static readonly HashSet<string> DISABLE_ON_RIG = new HashSet<string>(StringComparer.Ordinal)
        {
            "Player", "GeneralInput", "Aim", "PlayerCollision", "HoldingObject", "CopyChildren",
            "PlayerSounds", "PlayerJump", "PlayerAPI", "WeaponHandler",
            // HUD-ish and network-bound bits: name tag (reads PhotonView.Owner), chat bubble,
            // health bar canvases, the out-of-bounds indicator, the IsMine collider event
            "PlayerName", "PlayerChat", "HealthBar", "Canvas", "OutOfBoundsHandler", "IsMineEvent",
            "SetTeamColorFromSpawnedAttack"
        };
        private static readonly HashSet<string> DISABLE_ON_GUN = new HashSet<string>(StringComparer.Ordinal) { "Gun", "Canvas" };
        /// <summary>Subtrees switched OFF before activation: gameplay indicators (overheat,
        /// stun, silence, out-of-bounds, the destroy poof spawner) and the chat bubble.
        /// Never the health bar canvas: CharacterData.Awake looks up CrownPos beneath it.</summary>
        private static readonly HashSet<string> DEACTIVATE_ON_RIG = new HashSet<string>(StringComparer.Ordinal) { "Effects", "Canvas_Chat" };
        /// <summary>Components declared with [RequireComponent(typeof(PhotonView))] — they go
        /// first or the PhotonView refuses to leave ("Can't remove PhotonView because ...").</summary>
        private static readonly HashSet<string> PHOTON_DEPENDENTS = new HashSet<string>(StringComparer.Ordinal)
        {
            "SyncPlayerMovement", "PhotonTransformView", "PhotonTransformViewClassic", "PhotonRigidbody2DView", "PhotonAnimatorView"
        };

        // ── ownership, in the shape #508 forced ─────────────────────────
        // Never a bool. Unity stops a coroutine when its host GameObject is
        // destroyed, and that stop does NOT run `finally`; this plugin's
        // behaviour is destroyed and respawned by design on scene changes. A
        // bool set at the top and cleared in the finally therefore latches
        // true with nothing running, and every later portrait is refused for
        // the rest of the process. A claim is (host, generation, deadline):
        // a destroyed host reads as null, a late finally can only clear its
        // OWN generation, and a missed heartbeat expires the claim -- a bound,
        // rather than an attempt to enumerate the ways a coroutine can stop
        // without unwinding.
        private sealed class Claim
        {
            private MonoBehaviour _host;
            private int _gen;
            private float _until;

            internal bool Held { get { return _host != null && Time.realtimeSinceStartup <= _until; } }

            internal int Take(MonoBehaviour host, float budget)
            {
                _host = host;
                _until = Time.realtimeSinceStartup + budget;
                return ++_gen;
            }

            /// <summary>Extend from inside the running coroutine. A stale
            /// generation cannot extend its successor's claim.</summary>
            internal void Beat(int gen, float budget)
            {
                if (gen == _gen) _until = Time.realtimeSinceStartup + budget;
            }

            internal void Drop(int gen)
            {
                if (gen != _gen) return;
                _host = null;
                _until = -1f;
            }
        }

        private const float RENDER_BUDGET = 20f;   // re-stamped at every yield
        private const float UPLOAD_BUDGET = 90f;   // one request and its timeout
        private const float DEV_BUDGET = 180f;     // the console lever: settle time is operator-set
        // The claim bounds WHO may render. This bounds what a run that never
        // unwound left behind: the log hook and the rig were also in that
        // finally, and a skipped finally leaves the hook subscribed for the
        // life of the process and the RenderTexture and made Materials
        // allocated (the cloned scene objects die with the scene; those two do
        // not). Owed-and-unclaimed is a state Tick can see, so the cleanup is
        // positive and polled rather than a list of the ways a coroutine can
        // stop -- #276: blocking-by-default needs a cleanup that always runs.
        private static bool _cleanupOwed;
        private static readonly Claim _renderClaim = new Claim();
        private static readonly Claim _uploadClaim = new Claim();
        private static bool Rendering { get { return _renderClaim.Held; } }
        private static int _layer = -1;

        // live objects (static so Teardown is idempotent from anywhere)
        private static GameObject _root, _clone, _ground, _camGO, _holdable;
        private static readonly List<GameObject> _unparented = new List<GameObject>();
        private static RenderTexture _rt;
        private static readonly List<Material> _madeMats = new List<Material>();
        private static bool _colorApplied, _effectApplied;

        // exception capture during the run
        private static int _errCount;
        private static readonly List<string> _errs = new List<string>();

        internal static void DevRun(string spec)
        {
            spec = (spec ?? "").Trim();
            Reclaim();
            if (Rendering) { Plugin.Log.LogInfo("[PORTRAIT] busy; ignoring '" + spec + "'"); return; }
            if (Plugin.Instance == null) { Plugin.Log.LogWarning("[PORTRAIT] no Plugin.Instance"); return; }
            if (spec.Equals("upload", StringComparison.OrdinalIgnoreCase)) { Start("lever", true); return; }   // the production path once (v22 §5.7)
            if (spec.Equals("preview", StringComparison.OrdinalIgnoreCase)) { Start("lever-preview", false); return; }   // the same path without the upload: fills the Settings preview (2026-09-13)
            Plugin.Instance.StartCoroutine(Run(spec, _renderClaim.Take(Plugin.Instance, DEV_BUDGET)));
        }

        // ── product path (v22 §3.4, §5.7 items 1–8; r18 dispositions) ────────
        // One coroutine at most, from the main menu only (no match tracked);
        // identity, UI epoch and the match predicate are re-checked after every
        // yield and abort the run (teardown in finally). The matte PNG is the
        // upload; its reduce(4) is the settings-row preview.
        internal const int RECIPE = 1;                           // bump when the rig, framing or matte changes (descriptor r=)
        private const int UPLOAD_MAX_BYTES = 1024 * 1024;        // the server's PC_PORTRAIT_MAX_BYTES
        internal static bool UploadInFlight { get { return _uploadClaim.Held; } }

        /// <summary>A picture is on its way: the visit check has not run yet,
        /// a preset change is still debouncing, a render is running, or an
        /// upload is in flight.
        ///
        /// The pack-open wait used to read UploadInFlight alone, which is the
        /// LAST of those four. Opening a pack during the first seconds on the
        /// tab -- while /pc/me and the stats were still answering, which is
        /// exactly when a new player opens their first pack -- revealed the
        /// five cards against the initial disc, and those prints keep that face
        /// because the reveal is what the server stored them against.
        ///
        /// Every term expires on its own; nothing here can latch. The caller
        /// caps the wait regardless.</summary>
        internal static bool Preparing
        {
            get { return _pendingCheck || _refreshAt >= 0f || Rendering || UploadInFlight; }
        }
        internal static Texture2D PreviewTex { get; private set; }   // reduce(4) of the last matte (295x295)
        internal static int PreviewSerial { get; private set; }
        internal static string LastResult { get; private set; } = "";
        private static int _visitId, _checkedVisit = -1;
        private static bool _pendingCheck, _retriedThisVisit;
        private static float _refreshAt = -1f;
        private static string _refreshWhy;
        private static byte[] _lastMatte;
        private static string _lastDescriptor;
        private static string _lastKey;

        /// <summary>The Player Cards tab became visible: one portrait check this
        /// visit, after /pc/me and the stats answered (Tick).</summary>
        internal static void OnTabVisit() { _visitId++; _retriedThisVisit = false; _pendingCheck = true; }

        internal static void OnIdentityChanged()
        {
            _visitId++; _pendingCheck = false; _refreshAt = -1f; _retriedThisVisit = false;
            _lastMatte = null; _lastDescriptor = null; _lastKey = null; LastResult = "";
            // The preview is the previous account's character. Bumping the
            // serial is what tells the settings row its Sprite is dead, so the
            // texture is destroyed and the binding invalidated in one step --
            // dropping the reference alone left the old face painted.
            var old = PreviewTex;
            PreviewTex = null; PreviewSerial++;
            if (old != null) { try { UnityEngine.Object.Destroy(old); } catch { } }
        }

        /// <summary>The preset row changed (§3.4): re-render and upload, debounced 1.5 s.</summary>
        internal static void RequestRefresh(string why) { _refreshAt = Time.realtimeSinceStartup + 1.5f; _refreshWhy = why; }

        internal static int CurrentPreset()
        {
            try { var c = Plugin.PortraitPreset; return c != null ? Mathf.Clamp(c.Value, -1, 9) : -1; } catch { return -1; }
        }

        /// <summary>Runs the teardown a coroutine owed but never reached. Safe
        /// to call at any time: it acts only when the claim is free, so it can
        /// never tear down a live run's rig.</summary>
        private static void Reclaim()
        {
            if (!_cleanupOwed || _renderClaim.Held) return;
            _cleanupOwed = false;
            Application.logMessageReceived -= OnLog;
            Plugin.Log.LogInfo("[PORTRAIT] reclaimed a run that did not unwind");
            try { Teardown(new StringBuilder()); } catch { }
        }

        /// <summary>Every UI tick while the tab is visible.</summary>
        internal static void Tick()
        {
            Reclaim();
            if (_refreshAt >= 0f && Time.realtimeSinceStartup >= _refreshAt)
            {
                // Consumed only by an ACCEPTED start (r5 M9, r6 M5): a request
                // that matures while a render or an upload is busy, or that
                // Start refuses (a match, no prefab or identity yet), stays
                // armed and is tried again five seconds later.
                if (Rendering || UploadInFlight || !Start(_refreshWhy ?? "preset", true)) { _refreshAt = Time.realtimeSinceStartup + 5f; return; }
                _refreshAt = -1f;
                return;
            }
            if (!_pendingCheck || Rendering || UploadInFlight) return;
            var me = ApiClient.CachedPcMe; var stats = ApiClient.CachedPlayerStats;
            if (me == null || stats == null) return;                       // the descriptor needs both answers
            _pendingCheck = false;
            if (_checkedVisit == _visitId) return;
            _checkedVisit = _visitId;
            if (!string.IsNullOrEmpty(me.portrait_locked_until)) { LastResult = "picture locked"; return; }
            string want = BuildDescriptor(CurrentPreset());
            // A refused capture leaves LastResult saying why and does NOT
            // render. _pendingCheck is already false, so this visit does not
            // spin; the next visit (or a preset change) tries again, which is
            // what makes "art not loaded yet" self-correcting.
            if (want == null) return;
            if (!string.IsNullOrEmpty(me.portrait_hash) && me.portrait_descriptor == want)
            {
                LastResult = "picture current";
                // The Settings preview still wants a picture to show (2026-09-13):
                // a render without an upload, once per visit like the check.
                if (PreviewTex == null) Start("preview", false);
                return;
            }
            if (!Start("visit", true)) { _refreshAt = Time.realtimeSinceStartup + 5f; _refreshWhy = "visit"; }   // refused: kept armed (r6 M5)
        }

        /// <summary>True when a run was started; false when it was refused
        /// (busy, in a match, no prefab or identity yet) -- the caller keeps
        /// its request armed in that case (r6 M5).</summary>
        private static bool Start(string why, bool upload)
        {
            Reclaim();
            if (Rendering || Plugin.Instance == null) return false;
            if (GameStateWatcher.IsInMatch) { LastResult = "skipped: in a match"; return false; }
            if (PlayerAssigner.instance == null || PlayerAssigner.instance.playerPrefab == null) { LastResult = "skipped: no player prefab yet"; return false; }
            if (string.IsNullOrEmpty(MatchTracker.LocalSteamId) || MatchTracker.LocalSteamId == "unknown") { LastResult = "skipped: no identity"; return false; }
            int gen = _renderClaim.Take(Plugin.Instance, RENDER_BUDGET);
            Plugin.Instance.StartCoroutine(ProductRun(why, upload, gen));
            return true;
        }

        /// <summary>Every input whose change must abandon an in-flight render
        /// or an in-flight upload, as ONE value captured before the first yield
        /// and compared after each one.
        ///
        /// It was identity + UI epoch + in-match, which is three of the six:
        /// changing the preset or a new tab visit rode through a yield and
        /// uploaded the capture taken under the old value. Pairs of ad-hoc
        /// checks are exactly how the next one gets forgotten, so there is one
        /// key and one comparison. (The picture setting was a term until
        /// 2026-09-13; there is no such setting any more.)</summary>
        private static string StateKey()
        {
            return (MatchTracker.LocalSteamId ?? "")
                 + "|" + PlayerCardsUI.Epoch
                 + "|" + _visitId
                 + "|" + CurrentPreset()
                 + "|" + (AnimatedOn() ? 1 : 0)
                 + "|" + (GameStateWatcher.IsInMatch ? 1 : 0)
                 + "|" + LiveInputsKey();
        }

        private static bool Stale(string key) { return key != StateKey(); }

        /// <summary>The pixel inputs as they are NOW -- the selected face's
        /// ids and offsets, the equipped colour and effect -- as the key's last
        /// segment (r6 M4): a change of any of them across a yield abandons the
        /// render or the upload taken under the old ones, and Abandon asks for
        /// a fresh one. Reads what Capture reads, without its validation; no
        /// '|' inside, so the segment can be cut off the key again.</summary>
        private static string LiveInputsKey()
        {
            string face = "";
            try
            {
                var cch = CharacterCreatorHandler.instance;
                PlayerFace f = null;
                int preset = CurrentPreset();
                if (cch != null)
                {
                    if (preset >= 0 && cch.playerFaces != null && preset < cch.playerFaces.Length) f = cch.playerFaces[preset];
                    else if (cch.selectedPlayerFaces != null && cch.selectedPlayerFaces.Length > 0) f = cch.selectedPlayerFaces[0];
                }
                if (f != null)
                    face = f.eyeID + ":" + f.mouthID + ":" + f.detailID + ":" + f.detail2ID + ";"
                         + Off(f.eyeOffset) + ";" + Off(f.mouthOffset) + ";" + Off(f.detailOffset) + ";" + Off(f.detail2Offset);
            }
            catch { face = "?"; }
            var s = ApiClient.CachedPlayerStats;
            string gear = s == null ? "" : (s.active_player_color_sku ?? "") + ":" + (s.active_player_color_hex ?? "") + ":" + (s.active_player_effect_sku ?? "");
            return (face + "~" + gear).Replace('|', '_');
        }

        /// <summary>A run abandoned because the key moved. When the move was in
        /// the pixel inputs the picture on the server is now behind the
        /// character, so a refresh is requested (debounced, retried while busy);
        /// any other move -- identity, a new visit, a match -- has its own
        /// follow-up already.</summary>
        private static void Abandon(string key)
        {
            LastResult = "aborted";
            int i = key.LastIndexOf('|');
            if (i >= 0 && key.Substring(i + 1) != LiveInputsKey()) RequestRefresh("inputs changed");
        }

        /// <summary>The animated-cosmetics setting. It changes the pixels a
        /// capture produces, so it belongs in both the fence and the
        /// descriptor; without it, toggling animation draws a different face
        /// under a descriptor the server already has and the stored portrait
        /// is never refreshed.</summary>
        private static bool AnimatedOn()
        {
            try { var c = Plugin.AnimatedCosmetics; return c == null || c.Value; }
            catch { return true; }
        }

        /// <summary>The descriptor of the portrait INPUTS as this client sees them
        /// now (v22 §3.4, r18 H9): face item ids and offsets ("R" floats), the
        /// equipped colour sku + hex, the effect sku, the skin, the game version
        /// and the recipe. Pure — no render. The server compares the cosmetic
        /// fields with what the account has equipped.</summary>
        /// <summary>Everything the descriptor names and the render draws, read
        /// ONCE. The two used to be read separately -- the descriptor before
        /// the first yield, the colour and effect again inside the rig build
        /// afterwards -- so a cosmetic that changed mid-render produced pixels
        /// from one equipment and a descriptor naming the other, and the server
        /// stored it as the second. There is now one read and one snapshot.
        ///
        /// `refusal` is how this reports an input it cannot describe. Coercing
        /// instead (a truncated sku, a stripped alpha channel, a non-finite
        /// offset written as "0") makes the descriptor claim a picture that is
        /// not the one drawn, and because the claim then MATCHES what the
        /// server holds, nothing ever re-renders to correct it.</summary>
        private sealed class Inputs
        {
            internal int preset;
            internal string faceIds = "0:0:0:0";
            internal string faceOffs = "0,0;0,0;0,0;0,0";
            internal string colorSku = "";
            internal string colorHex = "";
            internal string effectSku = "";
            internal bool animated;
            internal string descriptor;
            internal string refusal;
            internal PlayerFace face;   // the face the descriptor describes, a copy: the render equips THIS (r5 M7/M8)
        }

        /// <summary>#124: an id at or above the custom base resolves through
        /// the loader, and an id whose art has not been built yet resolves to
        /// NULL, which renders an EMPTY slot with no error anywhere. Capturing
        /// that stores a blank face under a descriptor that names the item, and
        /// the descriptor matches from then on -- so the blank picture is
        /// permanent even after the art arrives. Not-ready is therefore a
        /// refusal, and the next tab visit tries again.</summary>
        private static bool ArtReady(int id, CharacterItemType type)
        {
            if (id < CustomCosmetics.CUSTOM_ID_BASE) return true;
            try
            {
                var loader = CharacterCreatorItemLoader.instance;
                if (loader == null) return false;
                return loader.GetItem(id, type) != null;
            }
            catch { return false; }
        }

        private static Inputs Capture(int preset)
        {
            var inp = new Inputs();
            inp.preset = preset;
            inp.animated = AnimatedOn();

            PlayerFace f = null;
            try
            {
                var cch = CharacterCreatorHandler.instance;
                if (cch != null)
                {
                    // the config value IS the index: -1 follows the live selection
                    if (preset >= 0 && cch.playerFaces != null && preset < cch.playerFaces.Length) f = cch.playerFaces[preset];
                    else if (cch.selectedPlayerFaces != null && cch.selectedPlayerFaces.Length > 0) f = cch.selectedPlayerFaces[0];
                }
            }
            catch { f = null; }

            if (f != null)
            {
                if (!ArtReady(f.eyeID, CharacterItemType.Eyes)
                    || !ArtReady(f.mouthID, CharacterItemType.Mouth)
                    || !ArtReady(f.detailID, CharacterItemType.Detail)
                    || !ArtReady(f.detail2ID, CharacterItemType.Detail))
                {
                    inp.refusal = "custom face art is not loaded yet";
                    return inp;
                }
                if (!Finite(f.eyeOffset) || !Finite(f.mouthOffset) || !Finite(f.detailOffset) || !Finite(f.detail2Offset))
                {
                    inp.refusal = "a face offset is not a finite number";
                    return inp;
                }
                // The server's face field is four unsigned groups of at most
                // four digits. A negative or five-digit id completes a capture
                // and a render and is then refused with a 422, leaving the
                // previous card face in place with nothing on screen saying so.
                if (!FaceId(f.eyeID) || !FaceId(f.mouthID) || !FaceId(f.detailID) || !FaceId(f.detail2ID))
                {
                    inp.refusal = "a face item id is outside 0-9999";
                    return inp;
                }
                inp.faceIds = f.eyeID + ":" + f.mouthID + ":" + f.detailID + ":" + f.detail2ID;
                inp.faceOffs = Off(f.eyeOffset) + ";" + Off(f.mouthOffset) + ";" + Off(f.detailOffset) + ";" + Off(f.detail2Offset);
                // A copy of the face the descriptor describes, equipped by the
                // render after its end-of-frame yield: descriptor and pixels come
                // from one snapshot however the character menu moves meanwhile,
                // and slot n is slot n (the render used to look up n - 1).
                try { inp.face = PlayerFace.CreateFace(f.eyeID, f.eyeOffset, f.mouthID, f.mouthOffset, f.detailID, f.detailOffset, f.detail2ID, f.detail2Offset); }
                catch { inp.refusal = "the face could not be copied"; return inp; }   // never the live face (r6 L7)
            }

            var s = ApiClient.CachedPlayerStats;
            string rawColour = s != null ? (s.active_player_color_sku ?? "") : "";
            string rawEffect = s != null ? (s.active_player_effect_sku ?? "") : "";
            string rawHex = s != null ? (s.active_player_color_hex ?? "") : "";

            if (!Representable(rawColour)) { inp.refusal = "the equipped colour sku is not representable"; return inp; }
            if (!Representable(rawEffect)) { inp.refusal = "the equipped effect sku is not representable"; return inp; }
            inp.colorSku = Ident(rawColour);
            inp.effectSku = Ident(rawEffect);

            if (inp.colorSku.Length > 0)
            {
                string hex = (rawHex ?? "").Trim();
                if (hex.StartsWith("#", StringComparison.Ordinal)) hex = hex.Substring(1);
                // Exactly six. `#ff000080` used to become `ff0000`: the alpha
                // was dropped from the NAME while the renderer, unable to parse
                // it, fell back to white -- a descriptor for a picture nobody
                // drew.
                if (hex.Length != 6 || HexOf(hex).Length != 6)
                {
                    inp.refusal = "the equipped colour is not a six-digit hex";
                    return inp;
                }
                inp.colorHex = HexOf(hex);
            }

            inp.descriptor = "v1|face=" + inp.faceIds + "|off=" + inp.faceOffs
                           + "|color=" + inp.colorSku + ":" + inp.colorHex
                           + "|effect=" + inp.effectSku
                           + "|skin=0|anim=" + (inp.animated ? 1 : 0)
                           + "|g=" + GameTag() + "|r=" + RECIPE;

            // The server's cap, checked here rather than after a capture that
            // would only earn a 422 and leave the previous face in place.
            if (System.Text.Encoding.UTF8.GetByteCount(inp.descriptor) > 320)
            {
                inp.refusal = "the descriptor exceeds 320 bytes";
                inp.descriptor = null;
            }
            return inp;
        }

        private static bool FaceId(int id) { return id >= 0 && id <= 9999; }

        private static bool Finite(Vector2 v)
        {
            return !float.IsNaN(v.x) && !float.IsInfinity(v.x) && !float.IsNaN(v.y) && !float.IsInfinity(v.y);
        }

        /// <summary>True when sanitising would not change the value. Every sku
        /// the shop actually issues is lowercase letters and underscores, so
        /// this refuses only things that would otherwise be renamed or
        /// truncated into another sku's identity.</summary>
        private static bool Representable(string sku)
        {
            if (string.IsNullOrEmpty(sku)) return true;
            return sku.Length <= 40 && Ident(sku) == sku.ToLowerInvariant();
        }

        /// <summary>The descriptor of the portrait INPUTS as this client sees
        /// them now, or null when an input cannot be described (the reason is
        /// in `LastResult`). Pure -- no render.</summary>
        internal static string BuildDescriptor(int preset)
        {
            var inp = Capture(preset);
            if (inp.refusal != null) { LastResult = "no picture: " + inp.refusal; return null; }
            return inp.descriptor;
        }

        private static string Off(Vector2 v) => R(v.x) + "," + R(v.y);
        private static string R(float x) => (float.IsNaN(x) || float.IsInfinity(x)) ? "0" : x.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
        private static string Ident(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder();
            foreach (var ch in s.ToLowerInvariant()) if ((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch == '_') sb.Append(ch);
            return sb.Length > 40 ? sb.ToString(0, 40) : sb.ToString();
        }
        private static string HexOf(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder();
            foreach (var ch in s.ToLowerInvariant()) if ((ch >= 'a' && ch <= 'f') || (ch >= '0' && ch <= '9')) sb.Append(ch);
            return sb.Length > 6 ? sb.ToString(0, 6) : sb.ToString();
        }
        /// <summary>The game version, in the server's `g=` alphabet
        /// ([0-9A-Za-z._-], 1-24). Sanitising alone is lossy: two builds whose
        /// versions differ only in stripped punctuation, or only past the 24th
        /// character, produced ONE tag -- and a descriptor that does not change
        /// when the art does is never re-rendered. When the sanitised form is
        /// not the original, a digest of the original is appended, so distinct
        /// versions stay distinct.</summary>
        private static string GameTag()
        {
            string v = ""; try { v = Application.version ?? ""; } catch { }
            var sb = new StringBuilder();
            foreach (var ch in v) if ((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9') || ch == '.' || ch == '_' || ch == '-') sb.Append(ch);
            string clean = sb.ToString();
            if (clean.Length == 0) return "0";
            if (clean == v && clean.Length <= 24) return clean;
            uint h = 2166136261u;                       // FNV-1a over the ORIGINAL
            foreach (var ch in v) { h ^= ch; h *= 16777619u; }
            string tail = "_" + h.ToString("x8").Substring(0, 6);   // 7 of the 24
            if (clean.Length > 17) clean = clean.Substring(0, 17);
            return clean + tail;
        }

        private static IEnumerator ProductRun(string why, bool upload, int gen)
        {
            var rep = new StringBuilder();
            _errCount = 0; _errs.Clear();
            _cleanupOwed = true;
            Application.logMessageReceived -= OnLog;
            Application.logMessageReceived += OnLog;
            float t0 = Time.realtimeSinceStartup;
            string key = StateKey();
            int preset = CurrentPreset();
            var inp = Capture(preset);
            string descriptor = inp.descriptor;
            byte[] matte = null; float lit = 0f, partial = 0f;
            GameObject[] rootsBefore = null;
            try
            {
                if (inp.refusal != null) { LastResult = "no picture: " + inp.refusal; yield break; }
                yield return new WaitForEndOfFrame();
                _renderClaim.Beat(gen, RENDER_BUDGET);
                if (Stale(key)) { Abandon(key); yield break; }
                rootsBefore = SafeRoots();
                GameObject clone; CharacterData data;
                string err = BuildRig(rep, out clone, out data);
                if (err != null) { LastResult = "render failed: " + err; yield break; }
                clone.transform.SetParent(null, true);
                _clone = clone;
                UnityEngine.Object.Destroy(_root); _root = null;
                if (!AfterActivate(rep, clone, data, inp.face, null)) { LastResult = "render failed: the captured face could not be equipped"; yield break; }   // the captured face, never a second lookup; no upload without it (r6 L8)
                MakeGround(rep, clone);
                yield return null;
                _renderClaim.Beat(gen, RENDER_BUDGET);
                if (Stale(key)) { Abandon(key); yield break; }
                ApplyColorExact(rep, clone, inp.colorSku, inp.colorHex);
                ApplyEffectExact(rep, clone, inp.effectSku);
                float ts = Time.realtimeSinceStartup; int frames = 0;
                while (Time.realtimeSinceStartup - ts < DEFAULT_SETTLE || frames < 10)
                {
                    frames++;
                    yield return null;
                    _renderClaim.Beat(gen, RENDER_BUDGET);
                    if (Stale(key)) { Abandon(key); yield break; }
                }
                Stamp(clone); if (_holdable != null) Stamp(_holdable);
                FreezeGun(rep);
                Bounds b;
                if (!ComputeBounds(rep, clone, 1.3f, out b)) { LastResult = "render failed: no bounds"; yield break; }
                var cam = MakeCamera(b, DEFAULT_SIZE);
                Color32[] px;
                matte = MatteBytes(cam, DEFAULT_SIZE, out lit, out partial, out px);
                if (matte == null) { LastResult = "render failed: matte"; yield break; }
                if (lit < 0.02f || lit > 0.60f) { LastResult = "render discarded: lit " + (100f * lit).ToString("F1") + "%"; matte = null; yield break; }
                var prev = PreviewTex;
                PreviewTex = Reduce4(px, DEFAULT_SIZE); PreviewSerial++;
                if (prev != null) UnityEngine.Object.Destroy(prev);
                Teardown(rep);
                yield return null;                           // deferred Destroy lands
                _renderClaim.Beat(gen, RENDER_BUDGET);
                CompareRoots(rep, rootsBefore);
            }
            finally
            {
                _cleanupOwed = false;
                Application.logMessageReceived -= OnLog;
                Teardown(rep);
                Plugin.Log.LogInfo("[PORTRAIT] " + why + ": render " + (matte != null ? "ok" : "none") + " lit=" + (100f * lit).ToString("F1")
                                   + "% partial=" + (100f * partial).ToString("F1") + "% bytes=" + (matte != null ? matte.Length : 0)
                                   + " errors=" + _errCount + " elapsed=" + (Time.realtimeSinceStartup - t0).ToString("F2") + "s"
                                   + (matte == null ? " result=" + LastResult : ""));
                foreach (var e in _errs) Plugin.Log.LogWarning("[PORTRAIT]   " + e);
                _renderClaim.Drop(gen);
                try { NativeUI.MarkDirty(); } catch { }
            }
            if (matte == null || descriptor == null) yield break;
            if (Stale(key)) { Abandon(key); yield break; }
            _lastMatte = matte; _lastDescriptor = descriptor; _lastKey = key;
            if (upload) Upload(key, descriptor, matte, why);
            else LastResult = "rendered";
        }

        private static void Upload(string key, string descriptor, byte[] png, string why)
        {
            if (png.Length > UPLOAD_MAX_BYTES)
            {
                LastResult = "not sent: " + png.Length + " bytes over the cap";
                Plugin.Log.LogWarning("[PORTRAIT] " + LastResult);
                return;
            }
            if (Plugin.Instance == null) { LastResult = "not sent: no host"; return; }
            string id = MatchTracker.LocalSteamId;
            // The claim, not a bool: this callback is the ONLY thing that used
            // to clear the flag, and a scene transition during the request
            // means it never runs at all -- after which every later portrait
            // was suppressed for the life of the process.
            int ugen = _uploadClaim.Take(Plugin.Instance, UPLOAD_BUDGET);
            LastResult = "uploading";
            ApiClient.PcPortraitUpload(id, Guid.NewGuid().ToString("N"), descriptor, png, (ok, resp) =>
            {
                _uploadClaim.Drop(ugen);
                if (Stale(key)) { Abandon(key); return; }
                if (ok)
                {
                    var me = ApiClient.CachedPcMe;
                    string h = ApiClient.PcStr(ApiClient.PcTopLevel(resp, "portrait_hash"));
                    string d = ApiClient.PcStr(ApiClient.PcTopLevel(resp, "portrait_descriptor"));
                    if (me != null) { if (!string.IsNullOrEmpty(h)) me.portrait_hash = h; if (!string.IsNullOrEmpty(d)) me.portrait_descriptor = d; }
                    LastResult = ApiClient.PcBool(ApiClient.PcTopLevel(resp, "applied")) ? "picture updated" : "picture current";
                }
                else
                {
                    string code = ApiClient.PcErrorCode(resp) ?? "";
                    LastResult = "upload refused: " + (code.Length > 0 ? code : Trunc(resp, 80));
                    if (code == "retry_after" && !_retriedThisVisit && Plugin.Instance != null && !Stale(key))
                    {
                        // the 30 s pacing: exactly one retry, with the same bytes
                        _retriedThisVisit = true;
                        int secs = 31;
                        try
                        {
                            var m = System.Text.RegularExpressions.Regex.Match(resp ?? "", "\"retry_after\"\\s*:\\s*(\\d+)");
                            if (m.Success) secs = Mathf.Clamp(int.Parse(m.Groups[1].Value), 1, 120);
                        }
                        catch { }
                        Plugin.Instance.StartCoroutine(RetryAfter(secs + 1, key, why));
                    }
                }
                try { NativeUI.MarkDirty(); } catch { }
            });
        }

        private static IEnumerator RetryAfter(int secs, string key, string why)
        {
            yield return new WaitForSecondsRealtime(secs);
            // The bytes are only resent when they are still the bytes THIS key
            // produced. `_lastMatte` is mutable, so a render that finished
            // while this coroutine slept would otherwise be uploaded under the
            // earlier descriptor.
            if (_lastMatte == null || _lastDescriptor == null || _lastKey != key) yield break;
            if (Rendering || UploadInFlight) yield break;
            if (Stale(key)) { Abandon(key); yield break; }   // the retry's pixels are behind the inputs: a fresh run instead (r6 M4)
            Upload(key, _lastDescriptor, _lastMatte, why + "-retry");
        }

        /// <summary>reduce(4) of the matte: premultiplied 4x4 box average, so
        /// transparent neighbours do not bleed colour into the preview.</summary>
        private static Texture2D Reduce4(Color32[] px, int size)
        {
            int n = size / 4;
            var o = new Color32[n * n];
            for (int y = 0; y < n; y++)
                for (int x = 0; x < n; x++)
                {
                    int r = 0, g = 0, b = 0, a = 0;
                    for (int dy = 0; dy < 4; dy++)
                        for (int dx = 0; dx < 4; dx++)
                        {
                            var c = px[(y * 4 + dy) * size + x * 4 + dx];
                            r += c.r * c.a; g += c.g * c.a; b += c.b * c.a; a += c.a;
                        }
                    o[y * n + x] = a == 0 ? new Color32(0, 0, 0, 0) : new Color32((byte)(r / a), (byte)(g / a), (byte)(b / a), (byte)(a / 16));
                }
            var t = new Texture2D(n, n, TextureFormat.RGBA32, false);
            t.SetPixels32(o); t.Apply(false, true);
            t.filterMode = FilterMode.Bilinear;
            return t;
        }

        /// <summary>Dev lever `shot:&lt;tag&gt;`: the whole game window at the end of
        /// the frame to BepInEx/pc_shot_&lt;tag&gt;.png (this seat cannot be captured
        /// from outside, #622).</summary>
        internal static void DevShot(string tag)
        {
            if (Plugin.Instance == null) return;
            Plugin.Instance.StartCoroutine(ShotCo(SafeTag(tag ?? "")));
        }

        private static IEnumerator ShotCo(string tag)
        {
            yield return new WaitForEndOfFrame();
            Texture2D tex = null;
            try
            {
                int w = Screen.width, h = Screen.height;
                tex = new Texture2D(w, h, TextureFormat.RGB24, false);
                tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
                tex.Apply();
                string file = Path.Combine(BepInEx.Paths.BepInExRootPath, "pc_shot_" + tag + ".png");
                File.WriteAllBytes(file, tex.EncodeToPNG());
                Plugin.Log.LogInfo("[PORTRAIT] shot " + w + "x" + h + " -> " + file);
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[PORTRAIT] shot failed: " + ex.Message); }
            finally { if (tex != null) UnityEngine.Object.Destroy(tex); }
        }

        // ── the run ─────────────────────────────────────────────────────────
        private static IEnumerator Run(string spec, int gen)
        {
            var rep = new StringBuilder();
            _errCount = 0; _errs.Clear();
            _cleanupOwed = true;
            Application.logMessageReceived -= OnLog;
            Application.logMessageReceived += OnLog;
            float t0 = Time.realtimeSinceStartup;

            var parts = spec.Split(',');
            string verb = parts[0].Trim().ToLowerInvariant();
            int size = DEFAULT_SIZE; float settle = DEFAULT_SETTLE; int preset = -1;
            bool ground = true, color = true, effect = true, unlit = false;
            float pad = 1.3f;
            string colorOverride = null, effectOverride = null, faceOverride = null, tag = "run";
            for (int i = 1; i < parts.Length; i++)
            {
                var p = parts[i].Trim().ToLowerInvariant();
                if (p.Length == 0) continue;
                int iv; float fv;
                if (p.StartsWith("size=") && int.TryParse(p.Substring(5), out iv)) size = Mathf.Clamp(iv, 64, 2048);
                else if (p.StartsWith("settle=") && float.TryParse(p.Substring(7), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out fv)) settle = Mathf.Clamp(fv, 0f, 10f);
                else if (p.StartsWith("pad=") && float.TryParse(p.Substring(4), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out fv)) pad = Mathf.Clamp(fv, 1f, 3f);
                else if (p.StartsWith("preset=") && int.TryParse(p.Substring(7), out iv)) preset = iv;
                else if (p == "noground") ground = false;
                else if (p == "nocolor") color = false;
                else if (p == "noeffect") effect = false;
                else if (p == "unlit") unlit = true;     // diagnostic: also render with every material swapped to an unlit build
                else if (p.StartsWith("color=")) colorOverride = p.Substring(6);
                else if (p.StartsWith("effect=")) effectOverride = p.Substring(7);
                else if (p.StartsWith("face=")) faceOverride = p.Substring(5);   // e:m:d:d2[:dx:dy] item ids (+ detail offset)
                else if (p.StartsWith("tag=")) tag = SafeTag(p.Substring(4));
                else rep.Append("unknown option: ").Append(p).Append('\n');
            }
            rep.Append("portrait spike ").Append(DateTime.UtcNow.ToString("u"))
               .Append(" verb=").Append(verb).Append(" tag=").Append(tag).Append(" size=").Append(size).Append(" settle=").Append(settle).Append(" pad=").Append(pad)
               .Append(" preset=").Append(preset).Append(" ground=").Append(ground).Append(" color=").Append(color)
               .Append(" effect=").Append(effect).Append(" unlit=").Append(unlit).Append('\n');

            GameObject[] rootsBefore = null;
            string reportName = verb == "dump" ? "pc_portrait_dump.txt" : "pc_portrait_report_" + tag + ".txt";
            try
            {
                yield return new WaitForEndOfFrame();
                Color bg = SampleBackground(rep);
                rootsBefore = SafeRoots();

                if (verb == "dump") { DumpAll(rep); yield break; }
                if (verb != "run") { rep.Append("unknown verb\n"); yield break; }

                GameObject clone; CharacterData data;
                string err = BuildRig(rep, out clone, out data);
                if (err != null) { rep.Append("BUILD FAILED: ").Append(err).Append('\n'); yield break; }

                // Release the shaped clone as its OWN scene root: vanilla resolves the
                // character through transform.root (FollowInactiveHand, Unparent, the leg
                // raycasters), so it must not stay beneath the holder. Leaving an inactive
                // parent activates it here — Awake runs for every kept component now.
                clone.transform.SetParent(null, true);
                _clone = clone;
                UnityEngine.Object.Destroy(_root); _root = null;
                AfterActivate(rep, clone, data, PickFace(preset, rep), faceOverride);   // same frame: before any Start/Update
                if (ground) MakeGround(rep, clone);
                yield return null;                           // Starts ran (skin body, gun colours, masks)

                if (color) ApplyColor(rep, clone, colorOverride);
                if (effect) ApplyEffect(rep, clone, effectOverride);

                float ts = Time.realtimeSinceStartup; int frames = 0;
                while (Time.realtimeSinceStartup - ts < settle || frames < 10) { frames++; _renderClaim.Beat(gen, DEV_BUDGET); yield return null; }
                rep.Append("settled frames=").Append(frames).Append(" secs=")
                   .Append((Time.realtimeSinceStartup - ts).ToString("F2")).Append('\n');
                Stamp(clone); if (_holdable != null) Stamp(_holdable);
                FreezeGun(rep);                              // the hand-spring keeps nudging it; frame a still gun
                RigStatus(rep, clone, data);

                Bounds b;
                if (!ComputeBounds(rep, clone, pad, out b)) { rep.Append("NO BOUNDS\n"); yield break; }
                var cam = MakeCamera(b, size);

                // The vanilla materials DO render on the isolated camera (cycle 2, 2026-09-11):
                // the SFSoftShadow sprites and the Particles/Standard Unlit skin both drew at
                // their true colours, so the original materials are the product render.
                RenderTo(cam, bg, size, tag, rep);
                RenderTo(cam, new Color(0f, 0f, 0f, 0f), size, tag + "_alpha", rep);   // destination-alpha render (diagnostic: SFSoftShadow sprites write none)
                RenderMatte(cam, size, tag + "_matte", rep);                           // the upload candidate: difference matte over black and white
                if (unlit)
                {
                    // Diagnostic only. Cycle 2 showed the swap LOSES the skin particles and the
                    // gun sprites, so it is never the product path (learning #139 does not
                    // apply to the player prefab's own materials).
                    SwapUnlit(rep, clone);
                    yield return null;
                    Stamp(clone); if (_holdable != null) Stamp(_holdable);
                    RenderTo(cam, bg, size, tag + "_unlit", rep);
                }

                Teardown(rep);
                yield return null;                           // deferred Destroy lands
                CompareRoots(rep, rootsBefore);
            }
            finally
            {
                _cleanupOwed = false;
                Application.logMessageReceived -= OnLog;
                Teardown(rep);
                rep.Append("errors=").Append(_errCount).Append('\n');
                foreach (var e in _errs) rep.Append("  ").Append(e).Append('\n');
                rep.Append("elapsed=").Append((Time.realtimeSinceStartup - t0).ToString("F2")).Append("s\n");
                string path = "";
                try
                {
                    path = Path.Combine(BepInEx.Paths.BepInExRootPath, reportName);
                    File.WriteAllText(path, rep.ToString());
                }
                catch (Exception ex) { Plugin.Log.LogWarning("[PORTRAIT] report write failed: " + ex.Message); }
                Plugin.Log.LogInfo($"[PORTRAIT] done verb={verb} errors={_errCount} report={path}");
                _renderClaim.Drop(gen);
            }
        }

        // ── steps ───────────────────────────────────────────────────────────
        private static Color SampleBackground(StringBuilder rep)
        {
            Color result = new Color(0.10f, 0.12f, 0.20f, 1f);
            Texture2D tex = null;
            try
            {
                int w = Screen.width, h = Screen.height;
                tex = new Texture2D(6, 6, TextureFormat.RGB24, false);
                Color tl = Avg(tex, 6, h - 12), tr = Avg(tex, w - 12, h - 12), bl = Avg(tex, 6, 6), br = Avg(tex, w - 12, 6);
                rep.Append("bg samples TL=").Append(Hex(tl)).Append(" TR=").Append(Hex(tr))
                   .Append(" BL=").Append(Hex(bl)).Append(" BR=").Append(Hex(br))
                   .Append(" screen=").Append(w).Append('x').Append(h).Append('\n');
                result = tr; result.a = 1f;
            }
            catch (Exception ex) { rep.Append("bg sample failed: ").Append(ex.Message).Append('\n'); }
            finally { if (tex != null) UnityEngine.Object.Destroy(tex); }
            return result;
        }

        private static Color Avg(Texture2D tex, int x, int y)
        {
            tex.ReadPixels(new Rect(x, y, 6, 6), 0, 0);
            tex.Apply();
            var px = tex.GetPixels();
            Color s = Color.black;
            for (int i = 0; i < px.Length; i++) s += px[i];
            return px.Length > 0 ? s / px.Length : s;
        }

        private static void DumpAll(StringBuilder rep)
        {
            try
            {
                var pa = PlayerAssigner.instance;
                var prefab = pa != null ? pa.playerPrefab : null;
                rep.Append("PlayerAssigner.instance=").Append(pa != null).Append(" playerPrefab=").Append(prefab != null ? prefab.name : "null").Append('\n');
                if (prefab != null)
                {
                    int lines = 0;
                    rep.Append("== player prefab ==\n");
                    Dump(prefab.transform, "", rep, ref lines, 0);
                    var hold = prefab.GetComponentInChildren<Holding>(true);
                    if (hold != null && hold.holdable != null)
                    {
                        lines = 0;
                        rep.Append("== holdable prefab ==\n");
                        Dump(hold.holdable.transform, "", rep, ref lines, 0);
                    }
                    else rep.Append("no Holding/holdable on prefab\n");
                }
                var skin = PlayerSkinBank.GetPlayerSkinColors(0);
                if (skin != null)
                {
                    int lines = 0;
                    rep.Append("== skin prefab team 0 ==  color=").Append(Hex(skin.color)).Append('\n');
                    Dump(skin.transform, "", rep, ref lines, 0);
                }
                else rep.Append("no skin 0\n");
                var cch = CharacterCreatorHandler.instance;
                if (cch != null)
                {
                    rep.Append("selectedFaceID[0]=").Append(cch.selectedFaceID != null && cch.selectedFaceID.Length > 0 ? cch.selectedFaceID[0] : -1).Append('\n');
                    rep.Append("selected[0]: ").Append(FaceStr(cch.selectedPlayerFaces != null && cch.selectedPlayerFaces.Length > 0 ? cch.selectedPlayerFaces[0] : null)).Append('\n');
                    if (cch.playerFaces != null)
                        for (int i = 0; i < cch.playerFaces.Length; i++)
                            rep.Append("preset").Append(i).Append(": ").Append(FaceStr(cch.playerFaces[i])).Append('\n');
                }
                else rep.Append("CharacterCreatorHandler.instance=null\n");
                rep.Append("CharacterCreatorItemLoader.instance=").Append(CharacterCreatorItemLoader.instance != null).Append('\n');
                var s = ApiClient.CachedPlayerStats;
                rep.Append("cached color sku=").Append(s?.active_player_color_sku ?? "").Append(" hex=").Append(s?.active_player_color_hex ?? "")
                   .Append(" effect sku=").Append(s?.active_player_effect_sku ?? "").Append('\n');
                rep.Append("layers 24-31: ");
                for (int l = 24; l <= 31; l++) rep.Append(l).Append('=').Append(LayerMask.LayerToName(l)).Append(' ');
                rep.Append('\n');
            }
            catch (Exception ex) { rep.Append("dump threw: ").Append(ex).Append('\n'); }
        }

        private static void Dump(Transform t, string indent, StringBuilder sb, ref int lines, int depth)
        {
            if (t == null || lines > 500 || depth > 9) return;
            var comps = t.GetComponents<Component>();
            var names = new List<string>();
            foreach (var c in comps)
            {
                if (c == null) { names.Add("<missing>"); continue; }
                string n = c.GetType().Name;
                var r = c as Renderer;
                if (r != null)
                {
                    var m = r.sharedMaterial;
                    n += "[" + (m == null ? "nomat" : (m.shader == null ? "noshader" : m.shader.name)) + " sl=" + r.sortingLayerName + "/" + r.sortingOrder + "]";
                }
                var b = c as Behaviour;
                if (b != null && !b.enabled) n += "(off)";
                names.Add(n);
            }
            sb.Append(indent).Append(t.name).Append(t.gameObject.activeSelf ? "" : " (inactive)")
              .Append(" L").Append(t.gameObject.layer).Append(" p=").Append(V(t.localPosition)).Append(" s=").Append(V(t.localScale))
              .Append(" : ").Append(string.Join(", ", names.ToArray())).Append('\n');
            lines++;
            for (int i = 0; i < t.childCount; i++) Dump(t.GetChild(i), indent + "  ", sb, ref lines, depth + 1);
        }

        private static string BuildRig(StringBuilder rep, out GameObject clone, out CharacterData data)
        {
            clone = null; data = null;
            try
            {
                var pa = PlayerAssigner.instance;
                var prefab = pa != null ? pa.playerPrefab : null;
                if (prefab == null) return "no PlayerAssigner.instance.playerPrefab";
                if (_layer < 0)
                {
                    _layer = CardSnapshot.PickIsolationLayer();
                    rep.Append("isolation layer ").Append(_layer).Append('\n');
                }
                _root = new GameObject("CR_PortraitRoot");
                _root.hideFlags = HideFlags.HideAndDontSave;
                _root.SetActive(false);
                _root.transform.position = PARK;
                clone = UnityEngine.Object.Instantiate(prefab, _root.transform);
                clone.name = "CR_PortraitRig";
                clone.transform.position = PARK;

                // subtrees off (never awake), then the components that pin the PhotonView
                var deactivated = new List<string>();
                foreach (var t in clone.GetComponentsInChildren<Transform>(true))
                    if (t != clone.transform && DEACTIVATE_ON_RIG.Contains(t.name) && t.gameObject.activeSelf) { t.gameObject.SetActive(false); deactivated.Add(t.name); }
                var dependents = new List<string>();
                foreach (var b in clone.GetComponentsInChildren<Behaviour>(true))
                {
                    if (b == null) continue;
                    string n = b.GetType().Name;
                    if (PHOTON_DEPENDENTS.Contains(n)) { try { UnityEngine.Object.DestroyImmediate(b); dependents.Add(n); } catch (Exception ex) { rep.Append("dependent destroy ").Append(n).Append(": ").Append(ex.Message).Append('\n'); } }
                }
                rep.Append("deactivated: ").Append(string.Join(",", deactivated.ToArray())).Append(" | photon dependents removed: ").Append(string.Join(",", dependents.ToArray())).Append('\n');
                _unparented.Clear();
                foreach (var c in clone.GetComponentsInChildren<Component>(true))
                    if (c != null && c.GetType().Name == "Unparent" && !_unparented.Contains(c.gameObject)) _unparented.Add(c.gameObject);
                rep.Append("unparent carriers: ").Append(_unparented.Count).Append('\n');

                var pvs = clone.GetComponentsInChildren<Photon.Pun.PhotonView>(true);
                int pvN = pvs.Length;
                foreach (var pv in pvs)
                {
                    try { UnityEngine.Object.DestroyImmediate(pv); }
                    catch (Exception ex) { rep.Append("pv destroy: ").Append(ex.Message).Append('\n'); }
                }
                rep.Append("photonviews ").Append(pvN).Append(" -> ").Append(clone.GetComponentsInChildren<Photon.Pun.PhotonView>(true).Length).Append('\n');

                var found = new List<string>();
                foreach (var b in clone.GetComponentsInChildren<Behaviour>(true))
                {
                    if (b == null) continue;
                    string n = b.GetType().Name;
                    if (DISABLE_ON_RIG.Contains(n)) { b.enabled = false; found.Add(n); }
                }
                var missing = new List<string>();
                foreach (var n in DISABLE_ON_RIG) if (!found.Contains(n)) missing.Add(n);
                rep.Append("disabled: ").Append(string.Join(",", found.ToArray())).Append(" | not found: ").Append(string.Join(",", missing.ToArray())).Append('\n');

                data = clone.GetComponent<CharacterData>();
                var player = clone.GetComponent<Player>();
                if (player != null && data != null) player.data = data;   // Player.Awake is what normally sets it
                var vel = clone.GetComponent<PlayerVelocity>();
                if (vel != null)
                {
                    SetField(vel, "simulated", false, rep);
                    SetField(vel, "isKinematic", true, rep);
                }
                if (data != null) { data.isPlaying = false; data.aimDirection = Vector3.right; }
                int rbs = 0;
                foreach (var rb in clone.GetComponentsInChildren<Rigidbody2D>(true)) { rb.simulated = false; rbs++; }
                rep.Append("rig: data=").Append(data != null).Append(" player=").Append(player != null).Append(" vel=").Append(vel != null).Append(" rigidbodies_off=").Append(rbs).Append('\n');
                Stamp(clone);
                return null;
            }
            catch (Exception ex) { return ex.ToString(); }
        }

        /// <summary>Returns false when a face was captured and could not be
        /// equipped (no equipper, or the equip threw): the product run then
        /// aborts before any upload, since the pixels would not be the
        /// descriptor's (r6 L8). The dev path reads the report instead.</summary>
        private static bool AfterActivate(StringBuilder rep, GameObject clone, CharacterData data, PlayerFace captured, string faceOverride)
        {
            bool faceOk = true;
            try
            {
                var hold = clone.GetComponentInChildren<Holding>(true);
                var h = hold != null ? hold.holdable : null;
                _holdable = h != null ? h.gameObject : null;
                if (_holdable != null)
                {
                    int pvN = 0;
                    foreach (var pv in _holdable.GetComponentsInChildren<Photon.Pun.PhotonView>(true)) { pvN++; try { UnityEngine.Object.DestroyImmediate(pv); } catch { } }
                    var off = new List<string>();
                    foreach (var b in _holdable.GetComponentsInChildren<Behaviour>(true))
                    {
                        if (b == null) continue;
                        string n = b.GetType().Name;
                        if (DISABLE_ON_GUN.Contains(n)) { b.enabled = false; off.Add(n); }
                    }
                    Stamp(_holdable);
                    rep.Append("gun: ").Append(_holdable.name).Append(" pvs=").Append(pvN).Append(" off=").Append(string.Join(",", off.ToArray()))
                       .Append(" rig=").Append(h.rig != null).Append(" at=").Append(V(_holdable.transform.position - PARK)).Append('\n');
                }
                else rep.Append("gun: NONE spawned (Holding.Awake did not run or holdable null)\n");

                var ho = clone.GetComponentInChildren<HoldingObject>(true);
                if (ho != null) ho.transform.rotation = Quaternion.LookRotation(Vector3.right);
                rep.Append("holdingObject=").Append(ho != null).Append('\n');

                var skin = PlayerSkinBank.GetPlayerSkinColors(0);
                if (skin != null) SetTeamColor.TeamColorThis(clone, skin);
                rep.Append("team colour applied=").Append(skin != null).Append('\n');

                var eq = clone.GetComponentInChildren<CharacterCreatorItemEquipper>(true);
                var face = faceOverride != null ? ParseFace(faceOverride, rep) : captured;
                if (eq != null && face != null)
                {
                    try { eq.SpawnPlayerFace(face); rep.Append("face equipped\n"); }
                    catch (Exception ex) { faceOk = false; rep.Append("face equip threw: ").Append(ex.Message).Append('\n'); }
                }
                else
                {
                    if (face != null) faceOk = false;   // a face to show and nothing to equip it with
                    rep.Append("face: equipper=").Append(eq != null).Append(" face=").Append(face != null).Append('\n');
                }
                Stamp(clone);
            }
            catch (Exception ex) { faceOk = false; rep.Append("AfterActivate threw: ").Append(ex).Append('\n'); }
            return faceOk;
        }

        /// <summary>Spike-only: "e:m:d:d2[:dx:dy]" item ids with one detail offset, so a
        /// seat whose account never customised a face can still exercise mod cosmetics.</summary>
        private static PlayerFace ParseFace(string spec, StringBuilder rep)
        {
            try
            {
                var s = spec.Split(':');
                int e = 0, m = 0, d = 0, d2 = 0; float dx = 0f, dy = 0f;
                if (s.Length > 0) int.TryParse(s[0], out e);
                if (s.Length > 1) int.TryParse(s[1], out m);
                if (s.Length > 2) int.TryParse(s[2], out d);
                if (s.Length > 3) int.TryParse(s[3], out d2);
                if (s.Length > 4) float.TryParse(s[4], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out dx);
                if (s.Length > 5) float.TryParse(s[5], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out dy);
                var f = PlayerFace.CreateFace(e, Vector2.zero, m, Vector2.zero, d, new Vector2(dx, dy), d2, new Vector2(-dx, dy));
                rep.Append("face (override): ").Append(FaceStr(f)).Append('\n');
                return f;
            }
            catch (Exception ex) { rep.Append("face override parse threw: ").Append(ex.Message).Append('\n'); return null; }
        }

        private static PlayerFace PickFace(int preset, StringBuilder rep)
        {
            var cch = CharacterCreatorHandler.instance;
            if (cch == null) { rep.Append("no CharacterCreatorHandler.instance\n"); return null; }
            PlayerFace f = null;
            if (preset >= 0 && cch.playerFaces != null && preset < cch.playerFaces.Length) f = cch.playerFaces[preset];
            else if (cch.selectedPlayerFaces != null && cch.selectedPlayerFaces.Length > 0) f = cch.selectedPlayerFaces[0];
            rep.Append("face: ").Append(FaceStr(f)).Append('\n');
            return f;
        }

        private static void MakeGround(StringBuilder rep, GameObject clone)
        {
            try
            {
                // Floor at the IK foot targets (TargetLeftLeg/TargetRightLeg): the prefab also
                // carries -10-unit placeholder joints that would put the ground far too low.
                float minY = float.MaxValue; int targets = 0;
                foreach (var t in clone.GetComponentsInChildren<Transform>(true))
                    if (t.name == "TargetLeftLeg" || t.name == "TargetRightLeg") { targets++; if (t.position.y < minY) minY = t.position.y; }
                if (targets == 0) minY = clone.transform.position.y - 1.5f * clone.transform.lossyScale.y;
                float top = minY - 0.05f;
                _ground = new GameObject("CR_PortraitGround");
                _ground.hideFlags = HideFlags.HideAndDontSave;
                _ground.layer = 0;   // Default: what CharacterData.ThereIsGroundBelow masks on
                _ground.transform.position = new Vector3(PARK.x, top - 0.5f, PARK.z);
                var bc = _ground.AddComponent<BoxCollider2D>();
                bc.size = new Vector2(12f, 1f);
                rep.Append("ground top at y-offset ").Append((top - PARK.y).ToString("F3")).Append(" (foot targets ").Append(targets).Append(" lowest ").Append((minY - PARK.y).ToString("F3")).Append(")\n");
            }
            catch (Exception ex) { rep.Append("ground threw: ").Append(ex.Message).Append('\n'); }
        }

        /// <summary>The dev-lever form: reads what is equipped right now.</summary>
        private static void ApplyColor(StringBuilder rep, GameObject clone, string overrideHex)
        {
            var s = ApiClient.CachedPlayerStats;
            string sku = s != null ? (s.active_player_color_sku ?? "") : "";
            string hex = overrideHex ?? (s != null ? (s.active_player_color_hex ?? "") : "");
            if (overrideHex != null && string.IsNullOrEmpty(sku)) sku = "portrait-override";
            ApplyColorExact(rep, clone, sku, hex);
        }

        /// <summary>The product form: draws exactly what the captured inputs
        /// name. The product path must NOT re-read the equipment here -- that
        /// read happens after several yields, and a cosmetic changed in between
        /// produced pixels the descriptor did not describe.</summary>
        private static void ApplyColorExact(StringBuilder rep, GameObject clone, string sku, string hex)
        {
            try
            {
                if (string.IsNullOrEmpty(hex)) { rep.Append("colour: none equipped\n"); return; }
                PlayerColorCosmetic.ApplyForPortrait(clone.transform, PORTRAIT_ACTOR, sku, hex);
                _colorApplied = true;
                rep.Append("colour applied sku=").Append(sku).Append(" hex=").Append(hex).Append('\n');
            }
            catch (Exception ex) { rep.Append("colour threw: ").Append(ex.Message).Append('\n'); }
        }

        /// <summary>The dev-lever form: reads what is equipped right now.</summary>
        private static void ApplyEffect(StringBuilder rep, GameObject clone, string overrideSku)
        {
            var s = ApiClient.CachedPlayerStats;
            ApplyEffectExact(rep, clone, overrideSku ?? (s != null ? (s.active_player_effect_sku ?? "") : ""));
        }

        /// <summary>The product form: exactly the captured effect sku.</summary>
        private static void ApplyEffectExact(StringBuilder rep, GameObject clone, string sku)
        {
            try
            {
                if (string.IsNullOrEmpty(sku)) { rep.Append("effect: none equipped\n"); return; }
                // In-game material path (the rig's own particle material is already unlit and
                // renders here); the aura sits a little behind the body for this camera, which
                // looks down +z: in-game its sortingFudge does that job against the main camera.
                PlayerEffectCosmetic.ApplyForPortrait(clone.transform, PORTRAIT_ACTOR, sku, false);
                _effectApplied = true;
                var aura = clone.transform.Find("cr_effect");
                if (aura != null) aura.localPosition = new Vector3(0f, 0f, 0.6f);
                rep.Append("effect applied sku=").Append(sku).Append(" aura=").Append(aura != null).Append('\n');
            }
            catch (Exception ex) { rep.Append("effect threw: ").Append(ex.Message).Append('\n'); }
        }

        private static void FreezeGun(StringBuilder rep)
        {
            try
            {
                if (_holdable == null) return;
                var rb = _holdable.GetComponent<Rigidbody2D>();
                if (rb != null) { rb.velocity = Vector2.zero; rb.angularVelocity = 0f; rb.simulated = false; }
                var hold = _clone != null ? _clone.GetComponentInChildren<Holding>(true) : null;
                if (hold != null) hold.enabled = false;      // its FixedUpdate would keep writing forces/rotation
            }
            catch (Exception ex) { rep.Append("freeze gun threw: ").Append(ex.Message).Append('\n'); }
        }

        private static void RigStatus(StringBuilder rep, GameObject clone, CharacterData data)
        {
            try
            {
                int ps = 0, alive = 0;
                foreach (var p in clone.GetComponentsInChildren<ParticleSystem>(true)) { ps++; alive += p.particleCount; }
                int sr = 0, lr = 0, mr = 0, psr = 0, masks = 0, other = 0;
                foreach (var r in AllRenderers(clone))
                {
                    if (IsMask(r)) masks++;
                    else if (r is SpriteRenderer) sr++;
                    else if (r is LineRenderer) lr++;
                    else if (r is MeshRenderer) mr++;
                    else if (r is ParticleSystemRenderer) psr++;
                    else other++;
                }
                rep.Append("status: isGrounded=").Append(data != null && data.isGrounded).Append(" particleSystems=").Append(ps).Append(" liveParticles=").Append(alive)
                   .Append(" sprites=").Append(sr).Append(" lines=").Append(lr).Append(" meshes=").Append(mr).Append(" psr=").Append(psr).Append(" masks=").Append(masks).Append(" other=").Append(other);
                if (_holdable != null) rep.Append(" gunAt=").Append(V(_holdable.transform.position - PARK)).Append(" gunRot=").Append(_holdable.transform.rotation.eulerAngles.z.ToString("F0"));
                rep.Append(" rigAt=").Append(V(clone.transform.position - PARK)).Append('\n');
                var shaders = new Dictionary<string, int>();
                foreach (var r in AllRenderers(clone))
                {
                    var m = r.sharedMaterial;
                    string sn = m == null ? "nomat" : (m.shader == null ? "noshader" : m.shader.name);
                    int c; shaders.TryGetValue(sn, out c); shaders[sn] = c + 1;
                }
                rep.Append("shaders:");
                foreach (var kv in shaders) rep.Append(' ').Append(kv.Key).Append('x').Append(kv.Value);
                rep.Append('\n');
            }
            catch (Exception ex) { rep.Append("status threw: ").Append(ex.Message).Append('\n'); }
        }

        private static IEnumerable<Renderer> AllRenderers(GameObject clone)
        {
            foreach (var r in clone.GetComponentsInChildren<Renderer>(true)) if (r != null) yield return r;
            if (_holdable != null) foreach (var r in _holdable.GetComponentsInChildren<Renderer>(true)) if (r != null) yield return r;
        }

        private static bool ComputeBounds(StringBuilder rep, GameObject clone, float pad, out Bounds fit)
        {
            fit = new Bounds(PARK, Vector3.one);
            try
            {
                bool anyA = false, anyB = false;
                Bounds a = new Bounds(), b = new Bounds();
                var outliers = new List<string>();
                Vector3 rigPos = clone.transform.position;
                foreach (var r in AllRenderers(clone))
                {
                    if (IsMask(r) || !r.enabled || !r.gameObject.activeInHierarchy) continue;
                    var rb = r.bounds;
                    // a renderer with no mesh/sprite reports a bounds at the world origin; a
                    // stray far bounds would blow the frame up to thousands of units
                    if (rb.size.x > 500f || rb.size.y > 500f || Vector3.Distance(rb.center, rigPos) > 15f)
                    {
                        if (outliers.Count < 6) outliers.Add(r.name + "@" + V(rb.center - PARK));
                        continue;
                    }
                    if (!anyB) { b = rb; anyB = true; } else b.Encapsulate(rb);
                    if (r is ParticleSystemRenderer) continue;
                    if (!anyA) { a = rb; anyA = true; } else a.Encapsulate(rb);
                }
                // the gun's sprite bounds under-report the drawn weapon (cycle 3 clipped its
                // tip): reserve a box around the weapon root as well
                if (_holdable != null && anyA)
                {
                    var g = _holdable.transform.position;
                    a.Encapsulate(new Bounds(new Vector3(g.x, g.y, rigPos.z), new Vector3(1.4f, 1.0f, 0.1f)));
                }
                rep.Append("bounds solid=").Append(anyA ? (V(a.min - PARK) + ".." + V(a.max - PARK)) : "none")
                   .Append(" all=").Append(anyB ? (V(b.min - PARK) + ".." + V(b.max - PARK)) : "none")
                   .Append(" outliers=").Append(outliers.Count == 0 ? "none" : string.Join(" ", outliers.ToArray())).Append('\n');
                if (!anyA && !anyB) return false;
                // Frame on the SOLID renderers (body, limbs, gun, orb): particle systems report
                // emitter-sized bounds (±6 units here) that would shrink the character to a
                // third of the frame. The aura may bleed past the edge; the body may not.
                var use = anyA ? a : b;
                float side = Mathf.Max(use.size.x, use.size.y, 0.5f) * pad;
                fit = new Bounds(new Vector3(use.center.x, use.center.y, PARK.z), new Vector3(side, side, 1f));
                rep.Append("fit centre=").Append(V(fit.center - PARK)).Append(" side=").Append(side.ToString("F2")).Append('\n');
                return true;
            }
            catch (Exception ex) { rep.Append("bounds threw: ").Append(ex.Message).Append('\n'); return false; }
        }

        private static Camera MakeCamera(Bounds fit, int size)
        {
            _camGO = new GameObject("CR_PortraitCam");
            _camGO.hideFlags = HideFlags.HideAndDontSave;
            _camGO.transform.position = new Vector3(fit.center.x, fit.center.y, PARK.z - 10f);
            var cam = _camGO.AddComponent<Camera>();
            cam.enabled = false;
            cam.orthographic = true;
            cam.aspect = 1f;
            cam.orthographicSize = fit.size.y * 0.5f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.cullingMask = 1 << _layer;
            cam.nearClipPlane = 0.1f;
            cam.farClipPlane = 40f;
            cam.allowHDR = false; cam.allowMSAA = false;
            _rt = new RenderTexture(size, size, 24);
            _rt.antiAliasing = 4;                            // resolved on ReadPixels; smooths the flat-shape edges
            cam.targetTexture = _rt;
            return cam;
        }

        private static void RenderTo(Camera cam, Color bg, int size, string tag, StringBuilder rep)
        {
            Texture2D tex = null;
            try
            {
                cam.backgroundColor = bg;
                cam.targetTexture = _rt;
                cam.Render();
                var prev = RenderTexture.active;
                try
                {
                    RenderTexture.active = _rt;
                    tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
                    tex.ReadPixels(new Rect(0, 0, size, size), 0, 0);
                    tex.Apply();
                }
                finally { RenderTexture.active = prev; }
                var px = tex.GetPixels32();
                int lit = 0, diff = 0, sampled = 0;
                var bg32 = (Color32)bg;
                for (int i = 0; i < px.Length; i += 4)
                {
                    sampled++;
                    var c = px[i];
                    if (c.a > PROBE_FLOOR && (c.r > PROBE_FLOOR || c.g > PROBE_FLOOR || c.b > PROBE_FLOOR)) lit++;
                    if (Math.Abs(c.r - bg32.r) > PROBE_FLOOR || Math.Abs(c.g - bg32.g) > PROBE_FLOOR || Math.Abs(c.b - bg32.b) > PROBE_FLOOR) diff++;
                }
                string file = Path.Combine(BepInEx.Paths.BepInExRootPath, "pc_portrait_" + tag + ".png");
                var bytes = tex.EncodeToPNG();
                File.WriteAllBytes(file, bytes);
                rep.Append("render ").Append(tag).Append(": lit=").Append((100f * lit / Mathf.Max(1, sampled)).ToString("F1")).Append("% differs-from-bg=")
                   .Append((100f * diff / Mathf.Max(1, sampled)).ToString("F1")).Append("% bytes=").Append(bytes.Length).Append(" -> ").Append(file).Append('\n');
            }
            catch (Exception ex) { rep.Append("render ").Append(tag).Append(" threw: ").Append(ex.Message).Append('\n'); }
            finally { if (tex != null) UnityEngine.Object.Destroy(tex); }
        }

        /// <summary>Difference matte: render over opaque black and opaque white; per pixel
        /// a = 1 - (W - B) (mean of the three channels), colour = B / a (un-premultiplied).
        /// Shader-agnostic: a sprite shader that masks destination alpha (the gun's
        /// Sprites/SFSoftShadow) still cuts out, which the transparent-clear render cannot
        /// do (cycle 4: opaque differs-from-bg 10.5 % vs alpha lit 9.7 % — the gap was the gun).
        /// Alpha-blended: B = s*a, W = s*a + (1-a) -> a exact, colour = s. Additive with
        /// contribution c: B = c, W = 1 -> a = c, colour = white (a glow over a dark window).</summary>
        private static void RenderMatte(Camera cam, int size, string tag, StringBuilder rep)
        {
            float lit, partial; Color32[] px;
            var bytes = MatteBytes(cam, size, out lit, out partial, out px);
            if (bytes == null) { rep.Append("render ").Append(tag).Append(" threw (see log)\n"); return; }
            try
            {
                string file = Path.Combine(BepInEx.Paths.BepInExRootPath, "pc_portrait_" + tag + ".png");
                File.WriteAllBytes(file, bytes);
                rep.Append("render ").Append(tag).Append(": lit=").Append((100f * lit).ToString("F1"))
                   .Append("% partial-alpha=").Append((100f * partial).ToString("F1"))
                   .Append("% bytes=").Append(bytes.Length).Append(" -> ").Append(file).Append('\n');
            }
            catch (Exception ex) { rep.Append("render ").Append(tag).Append(" write threw: ").Append(ex.Message).Append('\n'); }
        }

        /// <summary>The matte as PNG bytes plus its lit and partial-alpha
        /// fractions and the raw pixels (for the preview); null when a step threw.</summary>
        private static byte[] MatteBytes(Camera cam, int size, out float lit, out float partial, out Color32[] pixels)
        {
            lit = 0f; partial = 0f; pixels = null;
            Texture2D texB = null, texW = null, outTex = null;
            try
            {
                texB = Grab(cam, Color.black, size);
                texW = Grab(cam, Color.white, size);
                var b = texB.GetPixels32(); var w = texW.GetPixels32();
                var o = new Color32[b.Length];
                int nLit = 0, nPartial = 0;
                for (int i = 0; i < b.Length; i++)
                {
                    int d = (w[i].r - b[i].r) + (w[i].g - b[i].g) + (w[i].b - b[i].b);
                    int a = 255 - d / 3;                       // 255 where opaque, 0 where only the clear colour shows
                    if (a < 0) a = 0; else if (a > 255) a = 255;
                    if (a == 0) { o[i] = new Color32(0, 0, 0, 0); continue; }
                    o[i] = new Color32(Un(b[i].r, a), Un(b[i].g, a), Un(b[i].b, a), (byte)a);
                    if (a > PROBE_FLOOR) nLit++;
                    if (a < 250) nPartial++;
                }
                outTex = new Texture2D(size, size, TextureFormat.RGBA32, false);
                outTex.SetPixels32(o); outTex.Apply();
                lit = (float)nLit / Mathf.Max(1, b.Length);
                partial = (float)nPartial / Mathf.Max(1, b.Length);
                pixels = o;
                return outTex.EncodeToPNG();
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[PORTRAIT] matte threw: " + ex.Message); return null; }
            finally { foreach (var t in new[] { texB, texW, outTex }) if (t != null) UnityEngine.Object.Destroy(t); }
        }

        private static byte Un(int c, int a) { int v = (c * 255 + a / 2) / a; return (byte)(v > 255 ? 255 : v); }

        private static Texture2D Grab(Camera cam, Color bg, int size)
        {
            cam.backgroundColor = bg; cam.targetTexture = _rt; cam.Render();
            var prev = RenderTexture.active;
            try
            {
                RenderTexture.active = _rt;
                // Owned here until it is handed back: a readback that throws
                // used to leave this native texture with no reference anywhere,
                // and the caller's own finally never saw it.
                Texture2D tex = null;
                try
                {
                    tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
                    tex.ReadPixels(new Rect(0, 0, size, size), 0, 0); tex.Apply();
                    var handed = tex; tex = null; return handed;
                }
                finally { if (tex != null) UnityEngine.Object.Destroy(tex); }
            }
            finally { RenderTexture.active = prev; }
        }

        private static void SwapUnlit(StringBuilder rep, GameObject clone)
        {
            try
            {
                var byShader = new Dictionary<string, int>();
                int swapped = 0, skipped = 0;
                foreach (var r in AllRenderers(clone))
                {
                    if (IsMask(r)) { skipped++; continue; }
                    var shared = r.sharedMaterials;
                    if (shared == null || shared.Length == 0) { skipped++; continue; }
                    var newMats = new Material[shared.Length];
                    bool any = false;
                    for (int i = 0; i < shared.Length; i++)
                    {
                        var m = shared[i];
                        if (m == null) { newMats[i] = null; continue; }
                        string sn = m.shader != null ? m.shader.name : "";
                        var sh = PickUnlit(r, sn);
                        if (sh == null) { newMats[i] = m; continue; }
                        var nm = new Material(sh);
                        try { if (m.HasProperty("_MainTex")) nm.mainTexture = m.mainTexture; } catch { }
                        Color c = Color.white;
                        try
                        {
                            if (m.HasProperty("_Color")) c = m.color;
                            else if (m.HasProperty("_TintColor")) c = m.GetColor("_TintColor");
                        }
                        catch { }
                        try
                        {
                            if (nm.HasProperty("_Color")) nm.color = c;
                            if (nm.HasProperty("_TintColor")) nm.SetColor("_TintColor", c);
                        }
                        catch { }
                        newMats[i] = nm; _madeMats.Add(nm); any = true;
                        int cnt; byShader.TryGetValue(sn, out cnt); byShader[sn] = cnt + 1;
                    }
                    if (any) { r.materials = newMats; swapped++; }   // per-instance materials, never sharedMaterials
                }
                rep.Append("unlit swap: renderers=").Append(swapped).Append(" skipped=").Append(skipped).Append(" from:");
                foreach (var kv in byShader) rep.Append(' ').Append(kv.Key).Append('x').Append(kv.Value);
                rep.Append('\n');
            }
            catch (Exception ex) { rep.Append("swap threw: ").Append(ex.Message).Append('\n'); }
        }

        private static Shader PickUnlit(Renderer r, string oldShader)
        {
            Shader sh = null;
            if (r is ParticleSystemRenderer)
            {
                bool additive = oldShader.IndexOf("Additive", StringComparison.OrdinalIgnoreCase) >= 0;
                sh = Shader.Find(additive ? "Legacy Shaders/Particles/Additive" : "Legacy Shaders/Particles/Alpha Blended")
                     ?? Shader.Find("Particles/Standard Unlit");
            }
            return sh ?? Shader.Find("Sprites/Default");
        }

        private static void Teardown(StringBuilder rep)
        {
            try { if (_colorApplied) { PlayerColorCosmetic.RevertPlayer(PORTRAIT_ACTOR); _colorApplied = false; } } catch (Exception ex) { rep.Append("colour revert threw: ").Append(ex.Message).Append('\n'); }
            try { if (_effectApplied) PlayerEffectCosmetic.ClearForPortrait(_clone != null ? _clone.transform : null, PORTRAIT_ACTOR); _effectApplied = false; } catch (Exception ex) { rep.Append("effect clear threw: ").Append(ex.Message).Append('\n'); }
            try { foreach (var m in _madeMats) if (m != null) UnityEngine.Object.Destroy(m); _madeMats.Clear(); } catch { }
            try { if (_camGO != null) { var c = _camGO.GetComponent<Camera>(); if (c != null) c.targetTexture = null; UnityEngine.Object.Destroy(_camGO); _camGO = null; } } catch { }
            try { if (_rt != null) { _rt.Release(); UnityEngine.Object.Destroy(_rt); _rt = null; } } catch { }
            try { if (_holdable != null) { UnityEngine.Object.Destroy(_holdable); _holdable = null; } } catch { }
            try { if (_ground != null) { UnityEngine.Object.Destroy(_ground); _ground = null; } } catch { }
            try { foreach (var u in _unparented) if (u != null) UnityEngine.Object.Destroy(u); _unparented.Clear(); } catch { }
            try { if (_clone != null) { UnityEngine.Object.Destroy(_clone); _clone = null; } } catch { }
            try { if (_root != null) { UnityEngine.Object.Destroy(_root); _root = null; } } catch { }
        }

        private static GameObject[] SafeRoots()
        {
            try { return SceneManager.GetActiveScene().GetRootGameObjects(); } catch { return new GameObject[0]; }
        }

        private static void CompareRoots(StringBuilder rep, GameObject[] before)
        {
            try
            {
                if (before == null) return;
                var set = new HashSet<GameObject>(before);
                var added = new List<string>();
                foreach (var go in SafeRoots()) if (go != null && !set.Contains(go)) added.Add(go.name);
                rep.Append("new scene roots after teardown: ").Append(added.Count == 0 ? "none" : string.Join(",", added.ToArray())).Append('\n');
            }
            catch (Exception ex) { rep.Append("roots compare threw: ").Append(ex.Message).Append('\n'); }
        }

        // ── helpers ─────────────────────────────────────────────────────────
        private static void Stamp(GameObject go) { if (go != null && _layer >= 0) CardSnapshot.SetLayerRecursive(go, _layer); }

        /// <summary>SpriteMask derives from Renderer but lives in a Unity module this
        /// project does not reference; match it by name so masks are never material-swapped.</summary>
        private static bool IsMask(Renderer r) => r != null && r.GetType().Name == "SpriteMask";

        private static void SetField(object o, string name, object value, StringBuilder rep)
        {
            try
            {
                var f = o.GetType().GetField(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (f == null) { rep.Append("field ").Append(name).Append(" not found on ").Append(o.GetType().Name).Append('\n'); return; }
                f.SetValue(o, value);
            }
            catch (Exception ex) { rep.Append("set ").Append(name).Append(" threw: ").Append(ex.Message).Append('\n'); }
        }

        private static void OnLog(string cond, string stack, LogType t)
        {
            if (t != LogType.Exception && t != LogType.Error) return;
            _errCount++;
            if (_errs.Count >= 16) return;
            string first = stack ?? "";
            int nl = first.IndexOf('\n');
            if (nl > 0) first = first.Substring(0, nl);
            string line = t + ": " + Trunc(cond, 220) + " @ " + Trunc(first, 200);
            if (!_errs.Contains(line)) _errs.Add(line);
        }

        private static string Trunc(string s, int n) => string.IsNullOrEmpty(s) ? "" : (s.Length <= n ? s : s.Substring(0, n));
        private static string SafeTag(string s)
        {
            var sb = new StringBuilder();
            foreach (var ch in s) if (char.IsLetterOrDigit(ch) || ch == '-' || ch == '_') sb.Append(ch);
            return sb.Length == 0 ? "run" : sb.ToString();
        }
        private static string Hex(Color c) => ColorUtility.ToHtmlStringRGB(c);
        private static string V(Vector3 v) => "(" + v.x.ToString("F2") + "," + v.y.ToString("F2") + "," + v.z.ToString("F2") + ")";
        private static string FaceStr(PlayerFace f) => f == null ? "null"
            : "eye=" + f.eyeID + "@" + f.eyeOffset + " mouth=" + f.mouthID + "@" + f.mouthOffset
              + " detail=" + f.detailID + "@" + f.detailOffset + " detail2=" + f.detail2ID + "@" + f.detail2Offset;
    }
}
