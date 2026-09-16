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
    ///                                [,rawlegs][,nopin][,pinall][,grade=compiled|file|identity][,swaprb]
    ///                                [,lightprobe][,poseprobe][,psinfo][,sweep=S:S:...][,salts=N:N:...]
    ///   TestPlayerCards = portrait:gradebake[,ungraded]     (PortraitGrade.cs; `ungraded` is a negative control and never writes a table)
    ///   TestPlayerCards = portrait:gradeswatch[,x=F][,y=F][,secs=N][,grade=compiled|file][,swaprb]
    ///   TestPlayerCards = portrait:upload | portrait:preview   (the product path, started by the lever)
    /// Every verb is refused at dispatch by DevLeverBlocked, and every coroutine a
    /// verb starts asks it again after each of its yields and ends there on a
    /// refusal (its finally tears down, unless a successor holds the claim after
    /// a force-abort). The coroutine host's destruction and a scene unload that
    /// destroys the rig release everything at once (ForceAbort).
    /// Output: BepInEx/pc_portrait_{lit,unlit,alpha}.png, pc_portrait_report.txt,
    /// pc_portrait_dump.txt; with `sweep`, pc_portrait_{tag}_sim{S}_s{N}.png and
    /// pc_portrait_sweep_{tag}.tsv (see SweepEntry). A sweep runs only at the
    /// product size and within its work cap (SweepRefusal).
    ///
    /// `rawlegs`, `nopin` and `pinall` are negative controls: `rawlegs` builds the
    /// rig with the IK legs left as the prefab has them (move prediction and
    /// stepping on), `nopin` skips the pre-capture pinning of the particles and
    /// the animated face frames (the gun is pinned regardless, #629), and
    /// `pinall` restarts every active particle system, the ones that were not
    /// live included (the pin as first written). None is reachable from the
    /// product path.
    /// </summary>
    internal static partial class PortraitRender
    {
        private static readonly Vector3 PARK = new Vector3(4000f, 4000f, 0f);
        private const int DEFAULT_SIZE = 1180;         // 2x the 590 px portrait window (v21 §9)
        private const float DEFAULT_SETTLE = 1.0f;     // the settle wait only; the particle snapshot length is PARTICLE_SIM_SECS
        private const int PORTRAIT_ACTOR = -7777;      // synthetic actor id for the cosmetic classes
        private const byte PROBE_FLOOR = 8;

        private static readonly HashSet<string> DISABLE_ON_RIG = new HashSet<string>(StringComparer.Ordinal)
        {
            "Player", "GeneralInput", "Aim", "PlayerCollision", "HoldingObject", "CopyChildren",
            "PlayerSounds", "PlayerJump", "PlayerAPI", "WeaponHandler",
            // HUD-ish and network-bound bits: name tag (reads PhotonView.Owner), chat bubble,
            // health bar canvases, the out-of-bounds indicator, the IsMine collider event
            "PlayerName", "PlayerChat", "HealthBar", "Canvas", "OutOfBoundsHandler", "IsMineEvent",
            "SetTeamColorFromSpawnedAttack",
            // the in-match hover spring: its FixedUpdate raycasts the floor under each
            // leg and pushes the body up off it (LegRaycasters.HitGround)
            "LegRaycasters"
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

            /// <summary>The claim is held, and by generation `gen`.</summary>
            internal bool Owns(int gen) { return gen == _gen && Held; }

            /// <summary>The claim is held by a generation other than `gen`: a
            /// successor's rig and objects, which `gen`'s finally must not touch.</summary>
            internal bool HeldByOther(int gen) { return gen != _gen && Held; }

            /// <summary>Held, by a run `host` drives. Compared by reference, so
            /// it answers from inside the host's own OnDestroy.</summary>
            internal bool HeldBy(MonoBehaviour host)
            {
                return !ReferenceEquals(host, null) && ReferenceEquals(_host, host) && Time.realtimeSinceStartup <= _until;
            }

            internal int Take(MonoBehaviour host, float budget)
            {
                _host = host;
                _until = Time.realtimeSinceStartup + budget;
                return ++_gen;
            }

            /// <summary>Extend from inside the running coroutine. A stale
            /// generation cannot extend its successor's claim, and a claim that
            /// was cleared stays cleared.</summary>
            internal void Beat(int gen, float budget)
            {
                if (gen == _gen && !ReferenceEquals(_host, null)) _until = Time.realtimeSinceStartup + budget;
            }

            internal void Drop(int gen)
            {
                if (gen != _gen) return;
                _host = null;
                _until = -1f;
            }

            /// <summary>Releases the claim whichever generation holds it (a
            /// force-abort). The generation is kept, so the aborted run's own
            /// late Drop or Beat cannot touch a successor's claim.</summary>
            internal void Clear()
            {
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
        private static Holding _hold;   // the clone's Holding, cached in AfterActivate with the gun it spawned
        private static readonly List<GameObject> _unparented = new List<GameObject>();
        private static RenderTexture _rt;
        private static readonly List<Material> _madeMats = new List<Material>();
        // The rig's IK legs, cached in BuildRig while the clone is still whole:
        // Unparent lifts LegNew out of the clone at the first LateUpdate, after
        // which a GetComponentsInChildren on the clone no longer finds them.
        private static readonly List<IkLeg> _legs = new List<IkLeg>();
        private static float _groundTop = float.NaN;   // world y of MakeGround's floor surface; NaN when there is no floor
        private static string _legSummary = "";
        private static string _gunSummary = "";
        private static string _particleSummary = "";

        // exception capture during the run
        private static int _errCount;
        private static readonly List<string> _errs = new List<string>();

        internal static void DevRun(string spec)
        {
            spec = (spec ?? "").Trim();
            EnsureSceneHook();
            Reclaim();
            // Rendering is held by every render, product or dev, and by both grade
            // levers, so no lever starts beside one. UploadInFlight also keeps the
            // `upload` verb from starting a second upload beside one in flight.
            if (Rendering || UploadInFlight) { Plugin.Log.LogInfo("[PORTRAIT] busy; ignoring '" + spec + "'"); return; }
            if (Plugin.Instance == null) { Plugin.Log.LogWarning("[PORTRAIT] no Plugin.Instance"); return; }
            // One predicate for every verb, before anything starts: no lever runs in
            // or into a room, a spectate or a game (DevLeverBlocked). Each coroutine
            // started below asks it again after every yield.
            string blocked = DevLeverBlocked(0);
            if (blocked != null) { Plugin.Log.LogInfo("[PORTRAIT] refused: " + blocked + "; ignoring '" + spec + "'"); return; }
            if (spec.Equals("upload", StringComparison.OrdinalIgnoreCase)) { StartProduct("lever", true, true); return; }   // the production path once (v22 §5.7)
            if (spec.Equals("preview", StringComparison.OrdinalIgnoreCase)) { StartProduct("lever-preview", false, true); return; }   // the same path without the upload: fills the Settings preview (2026-09-13)
            string verb = spec.Split(',')[0].Trim().ToLowerInvariant();
            if (verb == "gradebake") { Plugin.Instance.StartCoroutine(GradeBakeRun(spec, _renderClaim.Take(Plugin.Instance, DEV_BUDGET))); return; }
            if (verb == "gradeswatch") { Plugin.Instance.StartCoroutine(GradeSwatchRun(spec, _renderClaim.Take(Plugin.Instance, DEV_BUDGET))); return; }
            Plugin.Instance.StartCoroutine(Run(spec, _renderClaim.Take(Plugin.Instance, DEV_BUDGET)));
        }

        /// <summary>Why a dev lever may not start, or a lever-started run may not
        /// continue, now; null when it may. Checked by DevRun before any verb
        /// starts (`gen` 0) and by every coroutine a verb starts after each of
        /// its yields (`gen` its render claim).
        ///
        /// Every term reads the state it names at the moment of the call --
        /// Photon's own room and client state, the spectator session's role and
        /// join flags, the game's GameManager and PlayerManager -- never a value
        /// a poll copied earlier. GameStateWatcher.IsInMatch, the mod's own
        /// match tracking, is one more refusal and never the only one. Any
        /// exception refuses. Allowed only: offline mode, or an online client
        /// that is in no room and whose client state is one of PeerCreated,
        /// Disconnected, ConnectedToMasterServer or JoinedLobby; and no
        /// spectator role, no spectate join in flight, no game started in this
        /// scene and no player spawned. For a run: its claim still held by
        /// its own generation (a force-abort or a successor ends it) and its rig
        /// not destroyed under it.</summary>
        internal static string DevLeverBlocked(int gen)
        {
            try
            {
                if (gen != 0)
                {
                    if (!_renderClaim.Owns(gen)) return "the run no longer holds its claim (aborted or superseded)";
                    if (RigLost()) return "the rig was destroyed";
                }
                if (!Photon.Pun.PhotonNetwork.OfflineMode)
                {
                    if (Photon.Pun.PhotonNetwork.InRoom) return "in an online room";
                    var cs = Photon.Pun.PhotonNetwork.NetworkClientState;
                    if (cs != Photon.Realtime.ClientState.PeerCreated && cs != Photon.Realtime.ClientState.Disconnected
                        && cs != Photon.Realtime.ClientState.ConnectedToMasterServer && cs != Photon.Realtime.ClientState.JoinedLobby)
                        return "the Photon client is " + cs + ", which may be entering or leaving a room";
                }
                if (SpectatorSession.IsLocalSpectator) return "spectating";
                if (SpectatorJoiner.JoinOpUnsettled) return "a spectate join is in flight";
                if (GameStateWatcher.IsInMatch) return "a match is tracked";
                var gm = GameManager.instance;
                if (gm != null && (gm.isPlaying || gm.battleOngoing)) return "a game has started in this scene";
                var pm = PlayerManager.instance;
                if (pm != null && pm.players != null && pm.players.Count > 0) return pm.players.Count + " player(s) spawned";
                return null;
            }
            catch (Exception ex) { return "state unreadable (" + ex.GetType().Name + ")"; }
        }

        // ── product path (v22 §3.4, §5.7 items 1–8; r18 dispositions) ────────
        // One coroutine at most, from the main menu only (no match tracked);
        // after every yield the run ends when RunEnded says so (its claim or rig
        // gone; for a lever's run, DevLeverBlocked) and abandons when the state
        // key (identity, UI epoch, the match predicate, the pixel inputs) moved,
        // with the teardown in finally. The matte PNG is the upload; its
        // reduce(4) is the settings-row preview.
        // Bump when the rig, framing, matte, pin or grade changes (descriptor r=).
        // 2: pinned IK legs, the gun root at its hand with its frame-time springs
        // at rest, the free arm at rest, animated frames, particles re-simulated
        // for PARTICLE_SIM_SECS from path-derived seeds in local space, and the
        // straight colour graded through the calibrated table (PortraitGrade.cs).
        // 3: the particle pin also restarts every active sub-emitter a pinned
        // system reaches, steps all of them together in PARTICLE_STEP_MS increments with
        // Unity's fixed-timestep option off and prewarm off, and seeds each from
        // its own path with no collision bump. The table and the length are
        // RECIPE 2's.
        // A change to any of these once ANY picture is stored under this RECIPE
        // (a dev build's upload included) needs a bump: check the stored
        // descriptors before folding one under the same number.
        internal const int RECIPE = 3;
        // The particle snapshot length: the live particle systems on the rig and
        // every sub-emitter they reach are re-simulated from a restart for this
        // long, in PARTICLE_STEP_MS increments, with prewarm off (PinParticles).
        // It is its own constant, not DEFAULT_SETTLE: the settle waits for the
        // pose, this decides the look, and tuning one must not move the other.
        // 5.5 was picked in game with the dev `sweep` option (lengths 0.5..30 s,
        // salts 0..2), against the default skin's body luminance averaged over
        // 36 in-game frames of the same character, under RECIPE 2's simulation:
        // one Simulate call on Unity's fixed-timestep option, the body
        // prewarmed. That skin is a looping particle system whose look differs
        // from one snapshot to the next, so a length selects one snapshot; it is
        // not a converged state. RECIPE 3 restarts the body with prewarm off, so
        // it starts from no particles and is simulated for this length, longer
        // than its 3 s start lifetime (per `psinfo`).
        // backend/tests/test_portrait_grade_recipe.py ledgers the length next to
        // the grade digest and refuses a length below the longest aura start
        // lifetime; that ledger is the only control on it (there is no runtime
        // "provisional" state: lengths are explored with `sweep` and `preview`,
        // which store nothing).
        internal const float PARTICLE_SIM_SECS = 5.5f;
        // The grade table this RECIPE renders with: the GRADE_LUT_FNV digest of
        // the table pasted into PortraitGrade.cs, 0 while that is the placeholder.
        // LoadGrade refuses any table whose digest is not this value, so a pasted
        // bake is not used until this line names it. A stored portrait whose
        // descriptor matches is never re-rendered, so naming a DIFFERENT table
        // here than one a released build shipped at this RECIPE also needs a
        // RECIPE bump; backend/tests/test_portrait_grade_recipe.py holds the
        // RECIPE -> digest ledger, and fails when a table is named at a RECIPE
        // whose ledger entry is a different table.
        internal const uint RECIPE_GRADE_FNV = 0xfad306d7u;
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
            ForceAbort("reclaimed a run that did not unwind");
        }

        /// <summary>Everything a run or a grade lever holds, released now: the
        /// render claim, the log hook, the rig and its camera, RenderTexture and
        /// materials, the synthetic cosmetic state, the light probe's
        /// Camera.onPreRender subscription (Teardown) and the grade levers'
        /// objects. Idempotent. A coroutine that is still alive afterwards finds
        /// its claim gone at its next yield (DevLeverBlocked for a lever's
        /// coroutine, RunEnded for a player's render) and ends; its finally
        /// skips the teardown only while a successor holds the claim.</summary>
        private static void ForceAbort(string why)
        {
            _renderClaim.Clear();
            _cleanupOwed = false;
            try { Application.logMessageReceived -= OnLog; } catch { }
            try { Teardown(new StringBuilder()); } catch { }
            try { DestroyGradeObjects(); } catch { }
            try { Plugin.Log.LogInfo("[PORTRAIT] force-abort: " + why); } catch { }
        }

        /// <summary>The coroutine host's OnDestroy (Plugin.cs). Unity stops the
        /// host's coroutines without running their finally blocks (#508), so a
        /// run the host drove -- or one no live host holds while its cleanup is
        /// still owed -- is released here, in the same call, instead of waiting
        /// for a later Reclaim. A claim another live host holds is left alone.</summary>
        internal static void OnHostDestroyed(MonoBehaviour host)
        {
            try
            {
                if (_renderClaim.HeldBy(host) || (_cleanupOwed && !_renderClaim.Held))
                    ForceAbort("the coroutine host was destroyed");
            }
            catch { }
        }

        private static bool _sceneHooked;

        /// <summary>Subscribes OnSceneUnloaded once for the process.</summary>
        private static void EnsureSceneHook()
        {
            if (_sceneHooked) return;
            try { SceneManager.sceneUnloaded += OnSceneUnloaded; _sceneHooked = true; } catch { }
        }

        /// <summary>A scene unloaded. When the rig was destroyed with it (a
        /// reference this class still holds now reads as destroyed), or a run
        /// that never unwound still owes its cleanup, everything is released at
        /// once. A rig that survived the unload is left to its run.</summary>
        private static void OnSceneUnloaded(Scene scene)
        {
            try
            {
                if (RigLost() || (_cleanupOwed && !_renderClaim.Held)) ForceAbort("a scene unloaded under the rig");
            }
            catch { }
        }

        /// <summary>A rig object this class holds a reference to -- the clone,
        /// the gun, the floor, the camera, a subtree lifted out of the clone --
        /// has been destroyed (Unity reports it as null while the reference is
        /// still set). Teardown drops every such reference, so this is false
        /// between runs.</summary>
        private static bool RigLost()
        {
            if (Gone(_clone) || Gone(_holdable) || Gone(_ground) || Gone(_camGO)) return true;
            foreach (var u in _unparented) if (Gone(u)) return true;
            return false;
        }

        private static bool Gone(UnityEngine.Object o) { return !ReferenceEquals(o, null) && o == null; }

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
            return StartProduct(why, upload, false);
        }

        /// <summary>`lever`: started by DevRun's `upload` or `preview` verb, so
        /// the run also asks DevLeverBlocked after every yield.</summary>
        private static bool StartProduct(string why, bool upload, bool lever)
        {
            EnsureSceneHook();
            Reclaim();
            if (Rendering || Plugin.Instance == null) return false;
            if (GameStateWatcher.IsInMatch) { LastResult = "skipped: in a match"; return false; }
            if (PlayerAssigner.instance == null || PlayerAssigner.instance.playerPrefab == null) { LastResult = "skipped: no player prefab yet"; return false; }
            if (string.IsNullOrEmpty(MatchTracker.LocalSteamId) || MatchTracker.LocalSteamId == "unknown") { LastResult = "skipped: no identity"; return false; }
            int gen = _renderClaim.Take(Plugin.Instance, RENDER_BUDGET);
            Plugin.Instance.StartCoroutine(ProductRun(why, upload, gen, lever));
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
                 + "|" + (GameStateWatcher.IsInMatch ? 1 : 0)
                 + "|" + LiveInputsKey();
        }

        private static bool Stale(string key) { return key != StateKey(); }

        /// <summary>The pixel inputs as they are NOW -- the selected face's
        /// ids and offsets, the animated-cosmetics setting, the equipped colour
        /// and effect -- as the key's last segment (r6 M4; the setting joined
        /// it in r7 M1: as a segment of its own it was seen by Stale but not by
        /// Abandon, so a change of it aborted the render without asking for a
        /// fresh one): a change of any of them across a yield abandons the
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
            string gear = (AnimatedOn() ? "1" : "0") + ":"
                        + (s == null ? "" : (s.active_player_color_sku ?? "") + ":" + (s.active_player_color_hex ?? "") + ":" + (s.active_player_effect_sku ?? ""));
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
        // A non-finite offset is its own value in the key (r7 L2): written as "0"
        // it was indistinguishable from a real zero, so a capture taken at zero
        // rode through a yield across which the offset had become NaN -- which a
        // fresh Capture refuses (Finite). Capture never writes these: it refuses first.
        private static string R(float x) => float.IsNaN(x) ? "nan" : float.IsPositiveInfinity(x) ? "inf" : float.IsNegativeInfinity(x) ? "-inf" : x.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
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

        /// <summary>Why ProductRun `gen` must end at this yield, or null. Every
        /// run: its claim is no longer its own (a force-abort cleared it, or a
        /// successor holds it), or a rig object it holds was destroyed. A run a
        /// lever started (`lever`): anything DevLeverBlocked refuses, which asks
        /// those two as well.</summary>
        private static string RunEnded(int gen, bool lever)
        {
            if (lever) return DevLeverBlocked(gen);
            if (!_renderClaim.Owns(gen)) return "the run no longer holds its claim (aborted or superseded)";
            if (RigLost()) return "the rig was destroyed";
            return null;
        }

        private static IEnumerator ProductRun(string why, bool upload, int gen, bool lever)
        {
            var rep = new StringBuilder();
            _errCount = 0; _errs.Clear();
            _cleanupOwed = true;
            Application.logMessageReceived -= OnLog;
            Application.logMessageReceived += OnLog;
            float t0 = Time.realtimeSinceStartup;
            _legSummary = "";                                // never a previous run's pose in this run's log line
            _gunSummary = "";
            _particleSummary = "";
            string key = StateKey();
            int preset = CurrentPreset();
            var inp = Capture(preset);
            string descriptor = inp.descriptor;
            byte[] matte = null; float lit = 0f, partial = 0f;
            GameObject[] rootsBefore = null;
            string ended;
            try
            {
                if (inp.refusal != null) { LastResult = "no picture: " + inp.refusal; yield break; }
                yield return new WaitForEndOfFrame();
                _renderClaim.Beat(gen, RENDER_BUDGET);
                if ((ended = RunEnded(gen, lever)) != null) { LastResult = "aborted: " + ended; yield break; }
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
                if ((ended = RunEnded(gen, lever)) != null) { LastResult = "aborted: " + ended; yield break; }
                if (Stale(key)) { Abandon(key); yield break; }
                int colour = ApplyColorExact(rep, clone, inp.colorSku, inp.colorHex);
                var aura = ApplyEffectExact(rep, clone, inp.effectSku);
                // Before the settle, so the arm IK and the leg renderer settle on
                // inputs that no longer move.
                PinRig(rep, true);
                float ts = Time.realtimeSinceStartup; int frames = 0, gunStill = 0;
                var watch = new ParticleWatch();
                while (Time.realtimeSinceStartup - ts < DEFAULT_SETTLE || frames < 10)
                {
                    frames++;
                    yield return null;
                    _renderClaim.Beat(gen, RENDER_BUDGET);
                    if ((ended = RunEnded(gen, lever)) != null) { LastResult = "aborted: " + ended; yield break; }
                    if (Stale(key)) { Abandon(key); yield break; }
                    gunStill = HoldGun() ? gunStill + 1 : 0;   // every frame, so the arm IK has seen the root and the free arm where they are captured
                    watch.Read();                                // every settle frame; below, the capture is refused unless every reading matched the first
                }
                Stamp(clone); if (_holdable != null) Stamp(_holdable);
                var rig = PinRig(rep, true);
                _gunSummary = rig.Summary(gunStill);
                watch.Read();
                var particles = PinParticles(rep, PlanParticles(false), PARTICLE_SIM_SECS, 0, false);
                _particleSummary = particles.Summary() + " watch " + watch.Summary();
                // A refusal below keeps the previous picture: nothing is uploaded.
                if (!watch.Steady) { LastResult = "render failed: particles changed during the settle " + watch.Summary(); yield break; }
                if (!particles.Ok) { LastResult = "render failed: particles not pinned " + _particleSummary; yield break; }
                if (!ColourReady(inp.colorHex, colour)) { LastResult = "render failed: colour not applied as captured"; yield break; }
                if (!EffectReady(inp.effectSku, aura, clone)) { LastResult = "render failed: effect not applied as captured"; yield break; }
                if (!LegsPlanted(out _legSummary)) { LastResult = "render failed: legs not planted " + _legSummary; yield break; }
                if (!rig.Pinned(gunStill)) { LastResult = "render failed: rig not pinned " + _gunSummary; yield break; }
                Bounds b;
                if (!ComputeBounds(rep, clone, 1.3f, out b)) { LastResult = "render failed: no bounds"; yield break; }
                var cam = MakeCamera(b, DEFAULT_SIZE);
                Color32[] px;
                matte = MatteBytes(cam, DEFAULT_SIZE, GradeTable, out lit, out partial, out px);
                if (matte == null) { LastResult = "render failed: matte"; yield break; }
                LogGradeProbe();
                if (lit < 0.02f || lit > 0.60f) { LastResult = "render discarded: lit " + (100f * lit).ToString("F1") + "%"; matte = null; yield break; }
                var prev = PreviewTex;
                PreviewTex = Reduce4(px, DEFAULT_SIZE); PreviewSerial++;
                if (prev != null) UnityEngine.Object.Destroy(prev);
                Teardown(rep);
                yield return null;                           // deferred Destroy lands
                _renderClaim.Beat(gen, RENDER_BUDGET);
                if ((ended = RunEnded(gen, lever)) != null) { LastResult = "aborted: " + ended; matte = null; yield break; }
                CompareRoots(rep, rootsBefore);
            }
            finally
            {
                // After a force-abort a successor may hold the claim: the rig, the
                // log hook and the owed cleanup are then its own.
                if (!_renderClaim.HeldByOther(gen))
                {
                    _cleanupOwed = false;
                    Application.logMessageReceived -= OnLog;
                    Teardown(rep);
                }
                Plugin.Log.LogInfo("[PORTRAIT] " + why + ": render " + (matte != null ? "ok" : "none") + " lit=" + (100f * lit).ToString("F1")
                                   + "% partial=" + (100f * partial).ToString("F1") + "% bytes=" + (matte != null ? matte.Length : 0)
                                   + " sha=" + (matte != null ? Sha12(matte) : "-") + " legs=" + _legSummary + " rig=" + _gunSummary
                                   + " particles=" + PARTICLE_SIM_SECS.ToString("R", System.Globalization.CultureInfo.InvariantCulture) + "s " + _particleSummary
                                   + " recipe=" + RECIPE + " grade=" + GradeTag()
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
            // Every upload, the retry included, passes here. A build whose grade
            // table is still the identity placeholder, or whose compiled table
            // LoadGrade rejected (length, digest, marker, or not the table
            // RECIPE_GRADE_FNV names), renders ungraded pixels, and the server
            // would store them as current under this RECIPE -- and a stored
            // descriptor that matches is never re-rendered. So such a build never
            // sends.
            if (!GradeBaked)
            {
                LastResult = "not sent: this build has no baked colour grade table";
                Plugin.Log.LogWarning("[PORTRAIT] " + LastResult + " (" + GradeTag() + ")");
                return;
            }
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
            bool rawlegs = false, nopin = false, pinall = false, swaprb = false, lightprobe = false, poseprobe = false, psinfo = false;
            float pad = 1.3f;
            List<int> sweep = null; List<int> salts = null;
            string colorOverride = null, effectOverride = null, faceOverride = null, tag = "run", grade = "compiled";
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
                else if (p == "rawlegs") rawlegs = true; // negative control: the prefab's leg IK, unpinned
                else if (p == "nopin") nopin = true;     // negative control: no particle/frame pinning (the gun is pinned regardless, #629)
                else if (p == "pinall") pinall = true;   // negative control: the particle pin restarts the systems that were not live too
                else if (p.StartsWith("grade=")) grade = p.Substring(6);   // compiled | file | identity: the table the _graded PNG uses
                else if (p == "swaprb") swaprb = true;   // negative control: that table with its red and blue outputs swapped
                else if (p == "lightprobe") lightprobe = true;   // log the SFSS lighting globals each camera renders with
                else if (p == "poseprobe") poseprobe = true;     // every rig transform at full precision before the capture
                else if (p == "psinfo") psinfo = true;           // one line per pinned particle system: its modules and counts
                else if (p.StartsWith("sweep=")) sweep = ParseMillis(p.Substring(6), 100, 60000, SWEEP_MAX_LENGTHS, rep);   // particle snapshot lengths in seconds, S:S:... (whole ms)
                else if (p.StartsWith("salts=")) salts = ParseInts(p.Substring(6), 0, 9999, SWEEP_MAX_SALTS, rep);         // seed salts for the sweep, N:N:... (0 = the product seed)
                else if (p.StartsWith("color=")) colorOverride = p.Substring(6);
                else if (p.StartsWith("effect=")) effectOverride = p.Substring(7);
                else if (p.StartsWith("face=")) faceOverride = p.Substring(5);   // e:m:d:d2[:dx:dy] item ids (+ detail offset)
                else if (p.StartsWith("tag=")) tag = SafeTag(p.Substring(4));
                else rep.Append("unknown option: ").Append(p).Append('\n');
            }
            rep.Append("portrait spike ").Append(DateTime.UtcNow.ToString("u"))
               .Append(" verb=").Append(verb).Append(" tag=").Append(tag).Append(" size=").Append(size).Append(" settle=").Append(settle).Append(" pad=").Append(pad)
               .Append(" preset=").Append(preset).Append(" ground=").Append(ground).Append(" color=").Append(color)
               .Append(" effect=").Append(effect).Append(" unlit=").Append(unlit)
               .Append(" rawlegs=").Append(rawlegs).Append(" nopin=").Append(nopin).Append(" pinall=").Append(pinall).Append(" grade=").Append(grade).Append(" swaprb=").Append(swaprb)
               .Append(" poseprobe=").Append(poseprobe).Append(" psinfo=").Append(psinfo)
               .Append(" sweep=").Append(sweep == null ? "none" : string.Join(":", sweep.ConvertAll(SecsOfMs).ToArray()))
               .Append(" salts=").Append(salts == null ? "default(0)" : string.Join(":", salts.ConvertAll(x => x.ToString()).ToArray()))
               .Append(" recipe=").Append(RECIPE).Append(" particle-secs=").Append(Secs(PARTICLE_SIM_SECS)).Append(" particle-step-ms=").Append(PARTICLE_STEP_MS).Append('\n');

            GameObject[] rootsBefore = null;
            string reportName = verb == "dump" ? "pc_portrait_dump.txt" : "pc_portrait_report_" + tag + ".txt";
            string blocked;
            try
            {
                yield return new WaitForEndOfFrame();
                _renderClaim.Beat(gen, DEV_BUDGET);
                if ((blocked = DevLeverBlocked(gen)) != null) { rep.Append("aborted: ").Append(blocked).Append('\n'); yield break; }
                Color bg = SampleBackground(rep);
                rootsBefore = SafeRoots();

                if (verb == "dump") { DumpAll(rep); yield break; }
                if (verb != "run") { rep.Append("unknown verb\n"); yield break; }
                // The whole run is refused over the sweep's work cap, before the rig is
                // built: every sweep, `nopin` included, whose entries are skipped below.
                string sweepRefused = sweep != null ? SweepRefusal(size, sweep, salts) : null;
                if (sweepRefused != null) { rep.Append("sweep refused: ").Append(sweepRefused).Append('\n'); yield break; }

                if (lightprobe) StartLightProbe();
                GameObject clone; CharacterData data;
                string err = BuildRig(rep, out clone, out data, !rawlegs);
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
                _renderClaim.Beat(gen, DEV_BUDGET);
                if ((blocked = DevLeverBlocked(gen)) != null) { rep.Append("aborted: ").Append(blocked).Append('\n'); yield break; }

                int colour = color ? ApplyColor(rep, clone, colorOverride) : 0;
                string effectSku = "";
                GameObject aura = effect ? ApplyEffect(rep, clone, effectOverride, out effectSku) : null;
                PinRig(rep, !nopin);                         // the gun always (#629); frames only when pinning
                rep.Append("legs start: ").Append(LegTrace()).Append('\n');

                float ts = Time.realtimeSinceStartup; int frames = 0, gunStill = 0;
                var watch = new ParticleWatch();
                while (Time.realtimeSinceStartup - ts < settle || frames < 10)
                {
                    frames++;
                    yield return null;
                    _renderClaim.Beat(gen, DEV_BUDGET);
                    if ((blocked = DevLeverBlocked(gen)) != null) { rep.Append("aborted: ").Append(blocked).Append('\n'); yield break; }
                    gunStill = HoldGun() ? gunStill + 1 : 0;   // the gun always (#629), as the product path does
                    watch.Read();                                // every settle frame, after the gun as in the product; this run reports the watch and refuses nothing on it
                    // The leg trace: per-leg move delta, foot target relative to the rig
                    // and the surface its ray is on, for the first frames of the settle --
                    // where a spawn read as a sideways move shows up.
                    if (frames <= 8) rep.Append("legs f").Append(frames).Append(": ").Append(LegTrace()).Append('\n');
                }
                rep.Append("settled frames=").Append(frames).Append(" secs=")
                   .Append((Time.realtimeSinceStartup - ts).ToString("F2")).Append('\n');
                Stamp(clone); if (_holdable != null) Stamp(_holdable);
                var rig = PinRig(rep, !nopin);
                rep.Append("rig pinned=").Append(rig.Pinned(gunStill)).Append(' ').Append(rig.Summary(gunStill)).Append('\n');
                watch.Read();
                rep.Append("particle watch steady=").Append(watch.Steady).Append(' ').Append(watch.Summary()).Append('\n');
                // One plan for the run: the sweep's entries and the restore after it
                // pin exactly the systems this pin chose (`pinall` included).
                ParticlePlan plan = nopin ? null : PlanParticles(pinall);
                if (plan != null) rep.Append("particles ok=").Append(PinParticles(rep, plan, PARTICLE_SIM_SECS, 0, psinfo).Ok).Append('\n');
                rep.Append("legs end: ").Append(LegTrace()).Append('\n');
                string ls; rep.Append("legs planted=").Append(LegsPlanted(out ls)).Append(' ').Append(ls).Append('\n');
                rep.Append("colour ready=").Append(colour != 0 && PlayerColorCosmetic.PortraitFrameReady(PORTRAIT_ACTOR, colour))
                   .Append(colour == 0 ? " (no colour applied)" : "").Append('\n');
                rep.Append("effect ready=").Append(EffectReady(effectSku, aura, clone))
                   .Append(effectSku.Length == 0 ? " (no effect applied)" : "").Append('\n');
                RigStatus(rep, clone, data);
                if (poseprobe) PoseProbe(rep);

                Bounds b;
                if (!ComputeBounds(rep, clone, pad, out b)) { rep.Append("NO BOUNDS\n"); yield break; }
                var cam = MakeCamera(b, size);

                // The vanilla materials DO render on the isolated camera (cycle 2, 2026-09-11):
                // the SFSoftShadow sprites and the Particles/Standard Unlit skin both drew at
                // their true colours, so the original materials are the product render.
                RenderTo(cam, bg, size, tag, rep);
                RenderTo(cam, new Color(0f, 0f, 0f, 0f), size, tag + "_alpha", rep);   // destination-alpha render (diagnostic: SFSoftShadow sprites write none)
                string gradeName; byte[] devTable = DevGradeTable(grade, swaprb, rep, out gradeName);
                RenderMatte(cam, size, tag, rep, devTable, gradeName);                 // _matte (ungraded, this rig's pinned pose) and _graded, from one capture
                if (!nopin) rep.Append(ParticlePinReport());
                rep.Append(GradeProbeLine()).Append('\n');
                if (sweep != null && nopin) rep.Append("sweep: skipped (nopin leaves the particles unpinned)\n");
                else if (sweep != null)
                {
                    // One rig, one camera: only the particle length and seed salt vary.
                    // Each entry pins and captures without a frame in between, then
                    // yields so the sweep does not hold the game for its whole length.
                    if (salts == null) salts = new List<int> { 0 };
                    // gun_held: this entry's gun pin met the rig contract and moved nothing (GunPin.Pinned
                    // with the still-frame term satisfied: the settle's count is not re-measured per entry);
                    // particles_ok: this entry's particle pin completed (ParticlePin.Ok)
                    var tsv = new StringBuilder("secs\tsalt\tbody_lum\tbody_px\tcore_cx\tcore_cy_top\tlit_pct\tgun_held\tparticles_ok\tsha\tsystems\tfile\n");
                    var buffers = new MeasureBuffers(size);   // one set of work arrays for every entry
                    int done = 0;
                    for (int si = 0; si < sweep.Count; si++)
                        for (int ki = 0; ki < salts.Count; ki++)
                        {
                            yield return null;
                            _renderClaim.Beat(gen, DEV_BUDGET);
                            if ((blocked = DevLeverBlocked(gen)) != null) { rep.Append("sweep aborted after ").Append(done).Append(" entries: ").Append(blocked).Append('\n'); yield break; }
                            HoldGun();
                            SweepEntry(rep, tsv, buffers, cam, size, tag, devTable, gradeName, plan, sweep[si], salts[ki]);
                            done++;
                        }
                    try
                    {
                        string tsvPath = Path.Combine(BepInEx.Paths.BepInExRootPath, "pc_portrait_sweep_" + tag + ".tsv");
                        File.WriteAllText(tsvPath, tsv.ToString());
                        rep.Append("sweep: ").Append(done).Append(" entries -> ").Append(tsvPath).Append('\n');
                    }
                    catch (Exception ex) { rep.Append("sweep tsv write threw: ").Append(ex.Message).Append('\n'); }
                    // The run's own pin again -- the same plan (the same systems, `pinall`
                    // included), PARTICLE_SIM_SECS and salt 0 -- so the `unlit` render below
                    // shows the snapshot the _matte render above captured. With `pinall` that
                    // is the negative control's particle state, not the product's.
                    PinParticles(rep, plan, PARTICLE_SIM_SECS, 0, false);
                }
                if (unlit)
                {
                    // Diagnostic only. Cycle 2 showed the swap LOSES the skin particles and the
                    // gun sprites, so it is never the product path (learning #139 does not
                    // apply to the player prefab's own materials).
                    SwapUnlit(rep, clone);
                    yield return null;
                    _renderClaim.Beat(gen, DEV_BUDGET);
                    if ((blocked = DevLeverBlocked(gen)) != null) { rep.Append("aborted: ").Append(blocked).Append('\n'); yield break; }
                    Stamp(clone); if (_holdable != null) Stamp(_holdable);
                    RenderTo(cam, bg, size, tag + "_unlit", rep);
                }

                Teardown(rep);
                yield return null;                           // deferred Destroy lands
                _renderClaim.Beat(gen, DEV_BUDGET);
                if ((blocked = DevLeverBlocked(gen)) != null) { rep.Append("aborted: ").Append(blocked).Append('\n'); yield break; }
                CompareRoots(rep, rootsBefore);
            }
            finally
            {
                // After a force-abort a successor may hold the claim: the rig, the
                // log hook and the owed cleanup are then its own.
                if (!_renderClaim.HeldByOther(gen))
                {
                    _cleanupOwed = false;
                    Application.logMessageReceived -= OnLog;
                    Teardown(rep);
                }
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

        /// <summary>`pinLegs` is false only for the dev negative control
        /// (`rawlegs`); the product path always pins.</summary>
        private static string BuildRig(StringBuilder rep, out GameObject clone, out CharacterData data, bool pinLegs = true)
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
                // isGrounded true keeps the legs off their airborne branch. The writers that
                // clear it in the decompile are CharacterData.Ground, which returns at once
                // while isPlaying is false, and PlayerJump, disabled on this rig.
                if (data != null) { data.isPlaying = false; data.isGrounded = true; data.aimDirection = Vector3.right; }
                int rbs = 0;
                foreach (var rb in clone.GetComponentsInChildren<Rigidbody2D>(true)) { rb.simulated = false; rbs++; }
                rep.Append("rig: data=").Append(data != null).Append(" player=").Append(player != null).Append(" vel=").Append(vel != null).Append(" rigidbodies_off=").Append(rbs).Append('\n');

                // The rig never moves, so its legs get no move prediction and no stepping.
                // IkLeg.lastPos starts at (0,0), so with the prefab's values the first
                // FixedUpdate reads the spawn at PARK as a run of thousands of units and
                // aims the foot rays sideways. With these three set before activation
                // (no FixedUpdate has run yet), SetValuesFixed never writes deltaPos, the
                // ray is Vector2.down onto MakeGround's floor, and footDownTime never
                // passes 1, so no step starts. LegsPlanted checks the outcome.
                _legs.Clear();
                foreach (var leg in clone.GetComponentsInChildren<IkLeg>(true))
                {
                    if (leg == null) continue;
                    _legs.Add(leg);
                    if (!pinLegs) continue;
                    leg.moveDeltaTransform = null;
                    leg.prediction = 0f;
                    leg.stepSpeed = 0f;
                }
                rep.Append("ik legs=").Append(_legs.Count).Append(" pinned=").Append(pinLegs).Append('\n');
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
                // Holding.Awake replaces its holdable -- a reference to the gun PREFAB
                // -- with a scene instance of it. A holdable in no scene is that prefab
                // asset (Awake did not run), and everything below and in the pins
                // would change the asset every later player's gun is spawned from, so
                // it is not taken; the product run then refuses on the gun pin.
                bool instance = h != null && h.gameObject.scene.IsValid();
                _hold = instance ? hold : null;
                _holdable = instance ? h.gameObject : null;
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
                else if (h != null) rep.Append("gun: prefab reference, not taken (Holding.Awake did not run)\n");
                else rep.Append("gun: none (Holding=").Append(hold != null).Append(", holdable null)\n");

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
                _groundTop = top;                            // the collider's upper face: centre top - 0.5, height 1
                rep.Append("ground top at y-offset ").Append((top - PARK.y).ToString("F3")).Append(" (foot targets ").Append(targets).Append(" lowest ").Append((minY - PARK.y).ToString("F3")).Append(")\n");
            }
            catch (Exception ex) { rep.Append("ground threw: ").Append(ex.Message).Append('\n'); }
        }

        /// <summary>The dev-lever form: reads what is equipped right now. Returns
        /// ApplyColorExact's token.</summary>
        private static int ApplyColor(StringBuilder rep, GameObject clone, string overrideHex)
        {
            var s = ApiClient.CachedPlayerStats;
            string sku = s != null ? (s.active_player_color_sku ?? "") : "";
            string hex = overrideHex ?? (s != null ? (s.active_player_color_hex ?? "") : "");
            if (overrideHex != null && string.IsNullOrEmpty(sku)) sku = "portrait-override";
            return ApplyColorExact(rep, clone, sku, hex);
        }

        /// <summary>The product form: draws exactly what the captured inputs
        /// name. The product path must NOT re-read the equipment here -- that
        /// read happens after several yields, and a cosmetic changed in between
        /// produced pixels the descriptor did not describe. Returns the token
        /// PlayerColorCosmetic.ApplyForPortrait gave this application; 0 when
        /// nothing was applied (no colour equipped, or the apply failed).</summary>
        private static int ApplyColorExact(StringBuilder rep, GameObject clone, string sku, string hex)
        {
            try
            {
                if (string.IsNullOrEmpty(hex)) { rep.Append("colour: none equipped\n"); return 0; }
                int token = PlayerColorCosmetic.ApplyForPortrait(clone.transform, PORTRAIT_ACTOR, sku, hex);
                rep.Append("colour applied sku=").Append(sku).Append(" hex=").Append(hex).Append(" token=").Append(token).Append('\n');
                return token;
            }
            catch (Exception ex) { rep.Append("colour threw: ").Append(ex.Message).Append('\n'); return 0; }
        }

        /// <summary>The captured colour is on the rig as the descriptor names
        /// it: with no colour captured, nothing was applied; with one, the
        /// application `token` names is still the portrait actor's state, with
        /// its targets tinted and, for an animated sku, its pinned frame written
        /// (PlayerColorCosmetic.PortraitFrameReady).</summary>
        private static bool ColourReady(string hex, int token)
        {
            if (string.IsNullOrEmpty(hex)) return token == 0;
            return token != 0 && PlayerColorCosmetic.PortraitFrameReady(PORTRAIT_ACTOR, token);
        }

        /// <summary>The dev-lever form: reads what is equipped right now. `sku`:
        /// the sku it applied. Returns ApplyEffectExact's aura.</summary>
        private static GameObject ApplyEffect(StringBuilder rep, GameObject clone, string overrideSku, out string sku)
        {
            var s = ApiClient.CachedPlayerStats;
            sku = overrideSku ?? (s != null ? (s.active_player_effect_sku ?? "") : "");
            return ApplyEffectExact(rep, clone, sku);
        }

        /// <summary>The product form: exactly the captured effect sku. Returns
        /// the aura this call made PlayerEffectCosmetic register for the
        /// portrait actor; null when no effect is equipped, when nothing was
        /// registered (its apply returned before building one, or caught a throw
        /// while building it), when the registered aura is the one registered
        /// before the call, or when the call threw.</summary>
        private static GameObject ApplyEffectExact(StringBuilder rep, GameObject clone, string sku)
        {
            try
            {
                if (string.IsNullOrEmpty(sku)) { rep.Append("effect: none equipped\n"); return null; }
                var before = RegisteredAura(PORTRAIT_ACTOR);
                // In-game material path (the rig's own particle material is already unlit and
                // renders here); the aura sits a little behind the body for this camera, which
                // looks down +z: in-game its sortingFudge does that job against the main camera.
                PlayerEffectCosmetic.ApplyForPortrait(clone.transform, PORTRAIT_ACTOR, sku, false);
                var aura = RegisteredAura(PORTRAIT_ACTOR);
                if (ReferenceEquals(aura, before)) aura = null;
                if (aura != null) aura.transform.localPosition = new Vector3(0f, 0f, 0.6f);
                rep.Append("effect applied sku=").Append(sku).Append(" aura=").Append(aura != null).Append('\n');
                return aura;
            }
            catch (Exception ex) { rep.Append("effect threw: ").Append(ex.Message).Append('\n'); return null; }
        }

        // PlayerEffectCosmetic's registry of the aura it built for each actor.
        // ApplyToPlayer writes an actor's entry only after that aura is fully
        // built, and OnMatchEnd (reached from the Settings colour toggle too)
        // clears every entry, the portrait actor's included, so the registry is
        // what says whether the aura a capture is about to take is still the
        // one its apply built. It is private to that class, which does not
        // expose it, so it is read by reflection: when the field cannot be
        // read, no aura is registered and every effect capture refuses.
        private static readonly FieldInfo EFFECT_AURAS =
            typeof(PlayerEffectCosmetic).GetField("auraByActor", BindingFlags.NonPublic | BindingFlags.Static);

        /// <summary>The aura PlayerEffectCosmetic has registered for `actor`
        /// now, or null (none registered, or the registry unreadable).</summary>
        private static GameObject RegisteredAura(int actor)
        {
            try
            {
                var auras = EFFECT_AURAS != null ? EFFECT_AURAS.GetValue(null) as Dictionary<int, GameObject> : null;
                GameObject go;
                return auras != null && auras.TryGetValue(actor, out go) ? go : null;
            }
            catch { return null; }
        }

        /// <summary>The captured effect is on the rig as the descriptor names
        /// it: with no effect captured, no aura was applied; with one, `aura`
        /// (ApplyEffectExact's result) is a live object that is still the
        /// portrait actor's registered aura, parented to the rig's clone and
        /// active, and its particle system is one the last particle pin
        /// completed (ProductRun pins right before it asks).</summary>
        private static bool EffectReady(string sku, GameObject aura, GameObject clone)
        {
            if (string.IsNullOrEmpty(sku)) return ReferenceEquals(aura, null);
            if (aura == null || clone == null) return false;
            if (!ReferenceEquals(RegisteredAura(PORTRAIT_ACTOR), aura)) return false;
            if (aura.transform.parent != clone.transform || !aura.activeInHierarchy) return false;
            var ps = aura.GetComponent<ParticleSystem>();
            if (ps == null) return false;
            foreach (var p in _pinned) if (ReferenceEquals(p.ps, ps)) return true;
            return false;
        }

        // ── pinning: the captured state depends on the inputs only ─────────
        // No settle length, frame rate or random seed may reach the pixels: the
        // legs are pinned in BuildRig, and these pin the gun (root, springs), the
        // free arm, the animated face frames and the particle systems before the
        // capture. The pins cover what the default character and the cosmetics
        // exercised so far carry; a component that integrates the frame delta
        // and is none of these is not pinned by anything here.

        /// <summary>Every root the rig owns: the clone, the spawned gun (a scene
        /// root of its own), and the subtrees Unparent lifts out of the clone.</summary>
        private static IEnumerable<GameObject> RigRoots()
        {
            if (_clone != null) yield return _clone;
            if (_holdable != null) yield return _holdable;
            foreach (var u in _unparented) if (u != null) yield return u;
        }

        /// <summary>What one gun pin did, audited against the rig contract
        /// (RIG_ARMS, RIG_MIRROR_SPRINGS). `hand`: the Holding's cached hand
        /// resolved and the gun root was written to it. `moved`: that write
        /// changed the root's pose (beyond GUN_STILL_EPS). `arms`: IKArmMove
        /// components found under the rig roots. `gunSide`: arms Update binds to
        /// the gun root, left to it (it writes their target straight to the root,
        /// with no frame delta). `free`: arms written to their rest point.
        /// `skipped`: arms with a field their Update needs unresolved (target,
        /// holding, rig, parent), or with no gun rig to decide their side by --
        /// Update would spring every arm free then, which is not the pose of a
        /// character holding its gun. `armMoved`: a free-arm write changed its
        /// target (beyond GUN_STILL_EPS), its velocity or its raise.
        /// `mirror`/`rot`: frame-time springs written to their rest pose and
        /// disabled. `inert`: mirror springs with no holdable or no holder, left
        /// alone. `live`: springs still enabled that would integrate the frame
        /// delta after the pass.</summary>
        private struct GunPin
        {
            internal bool hand, moved, armMoved;
            internal int arms, gunSide, free, skipped;
            internal int mirror, rot, inert, live;
            internal string error;

            /// <summary>The capture may take this gun: the hand resolved; this
            /// final write moved neither the root nor the free arm; both were
            /// already still for the last GUN_STILL_FRAMES settle frames (HoldGun,
            /// so the arm IK solved on them); exactly the contract's arms were
            /// found, one bound to the gun and one written free, none skipped;
            /// exactly the contract's mirror springs were written, none inert and
            /// no spring left live; and nothing threw.</summary>
            internal bool Pinned(int stillFrames)
            {
                return hand && !moved && !armMoved && stillFrames >= GUN_STILL_FRAMES
                    && arms == RIG_ARMS && gunSide == 1 && free == 1 && skipped == 0
                    && mirror == RIG_MIRROR_SPRINGS && inert == 0 && live == 0 && error == null;
            }

            internal string Summary(int stillFrames)
            {
                var sb = new StringBuilder();
                sb.Append("hand=").Append(hand ? 1 : 0).Append(" moved=").Append(moved ? 1 : 0);
                if (stillFrames >= 0) sb.Append(" still=").Append(stillFrames);
                sb.Append(" arms=").Append(arms).Append(" gun-side=").Append(gunSide).Append(" free=").Append(free)
                  .Append(" skipped=").Append(skipped).Append(" arm-moved=").Append(armMoved ? 1 : 0)
                  .Append(" mirror=").Append(mirror).Append(" rot=").Append(rot).Append(" inert=").Append(inert)
                  .Append(" live=").Append(live);
                if (error != null) sb.Append(" threw=").Append(error);
                return sb.ToString();
            }
        }

        // The arm IK reads the gun root in Update and its bones are solved after
        // that, so a picture taken right after a root write would show the arm
        // where the root was a frame or two before. The root must already have
        // been at the hand for this many consecutive settle frames.
        private const int GUN_STILL_FRAMES = 2;
        private const float GUN_STILL_EPS = 1e-4f;   // world units, and the same on the root's unit axes
        // The rig contract GunPin is audited against. The player prefab has two
        // arms, each driven by an IKArmMove: with the gun held, Update binds one
        // arm's target to the gun root and springs the other free (the dev run's
        // gun pin line has counted one free arm on every rig so far). The default
        // gun carries five RightLeftMirrorSpring (that line counts mirror=5). The
        // rig carries no RotSpring; one that appeared would be written to its
        // target and disabled like the mirror springs, so the RotSpring count is
        // reported and not part of the contract.
        private const int RIG_ARMS = 2;
        private const int RIG_MIRROR_SPRINGS = 5;

        /// <summary>The gun root where Holding.FixedUpdate rests it when the
        /// character is still -- at the hand, rotated to the hand's forward --
        /// with Holding off and the rigidbody stopped and unsimulated (#629), so
        /// nothing moves it after. The hand is Holding's own cached field, set in
        /// Awake while HoldingObject was still under the clone: Unparent lifts
        /// HoldingObject out of the clone at its first LateUpdate, after which a
        /// search of the clone for HandPos finds nothing. False when there is no
        /// gun or no hand; `moved` when the write changed the pose.</summary>
        private static bool WriteGunRoot(out bool moved)
        {
            moved = false;
            if (_holdable == null || _hold == null) return false;
            var hand = _hold.handPos;
            if (hand == null) return false;
            _hold.enabled = false;
            var rb = _holdable.GetComponent<Rigidbody2D>();
            if (rb != null) { rb.velocity = Vector2.zero; rb.angularVelocity = 0f; rb.simulated = false; }
            var t = _holdable.transform;
            Vector3 p = hand.position;
            Quaternion q = Quaternion.LookRotation(Vector3.forward, hand.forward);
            float e2 = GUN_STILL_EPS * GUN_STILL_EPS;
            moved = (t.position - p).sqrMagnitude > e2
                    || (t.rotation * Vector3.up - q * Vector3.up).sqrMagnitude > e2
                    || (t.rotation * Vector3.right - q * Vector3.right).sqrMagnitude > e2;
            t.position = p;
            t.rotation = q;
            return true;
        }

        /// <summary>Every IKArmMove under the rig roots, classified the way its
        /// Update decides: an arm on the gun rig's side is bound to the gun root
        /// and left to Update (counted gun-side); the other is written to the
        /// point Update pulls it to when the character is still (its parent's
        /// TransformPoint(startPos), no raise) with its velocity zeroed, so its
        /// frame-delta spring has nothing to integrate (counted free, and
        /// `armMoved` when that write changed anything). An arm whose Update
        /// fields are unresolved, or that has no gun rig to be classified by, is
        /// not written and counted skipped.</summary>
        private static void PinFreeArms(ref GunPin g)
        {
            float e2 = GUN_STILL_EPS * GUN_STILL_EPS;
            var seen = new HashSet<IKArmMove>();
            foreach (var root in RigRoots())
                foreach (var a in root.GetComponentsInChildren<IKArmMove>(true))
                {
                    if (a == null || !seen.Add(a)) continue;
                    g.arms++;
                    if (a.target == null || a.holding == null || a.rig == null || a.transform.parent == null) { g.skipped++; continue; }
                    var h = a.holding.holdable;
                    if (h == null || h.rig == null) { g.skipped++; continue; }
                    float rx = a.rig.transform.position.x;
                    if ((h.rig.transform.position.x > rx) == (a.transform.position.x > rx)) { g.gunSide++; continue; }   // the gun side, as Update decides it
                    Vector3 rest = a.transform.parent.TransformPoint(a.startPos);
                    if ((a.target.position - rest).sqrMagnitude > e2 || a.velolcity.sqrMagnitude > e2 || a.sinceRaise < 0.3f) g.armMoved = true;
                    a.target.position = rest;
                    a.velolcity = Vector3.zero;
                    if (a.sinceRaise < 0.3f) a.sinceRaise = 0.3f;
                    g.free++;
                }
        }

        /// <summary>The frame-time springs on every rig root at rest, stopped.
        /// RightLeftMirrorSpring (5 on WeaponBase, among them the Handle) and
        /// RotSpring integrate the frame delta in Update, so a capture during
        /// their approach caught them part-way, at a residual that depended on
        /// how many frames of what length had run.
        ///
        /// A mirror spring with a holdable and a holder is written to the fixed
        /// point of its Update -- the side Update would pick for the root where it
        /// is now, that side's local position and rotation -- with its velocities
        /// zeroed, and disabled. A mirror spring with no holdable (Start not run,
        /// or its root carries no Holdable) or no holder does nothing in Update:
        /// it is left alone and counted inert (which GunPin.Pinned refuses). A
        /// RotSpring always pulls toward its target, so every one is written
        /// there and disabled. Then every spring still enabled that would
        /// integrate is counted as live.</summary>
        private static void PinGunSprings(ref GunPin g)
        {
            foreach (var root in RigRoots())
            {
                foreach (var s in root.GetComponentsInChildren<RightLeftMirrorSpring>(true))
                {
                    if (s == null) continue;
                    var h = s.holdable;
                    if (h == null || h.holder == null) { g.inert++; continue; }
                    bool left = s.transform.root.position.x - 0.1f < h.holder.transform.position.x;
                    float r = left ? s.leftRot : s.rightRot;
                    s.posVel = Vector3.zero; s.rotVel = 0f; s.currentRot = r;
                    s.transform.localPosition = left ? s.leftPos : s.rightPos;
                    s.transform.localEulerAngles = new Vector3(0f, 0f, r);
                    s.enabled = false;
                    g.mirror++;
                }
                foreach (var s in root.GetComponentsInChildren<RotSpring>(true))
                {
                    if (s == null) continue;
                    s.vel = 0f; s.currentValue = s.target;
                    s.transform.localEulerAngles = new Vector3(s.x ? s.target : 0f, s.y ? s.target : 0f, s.z ? s.target : 0f);
                    s.enabled = false;
                    g.rot++;
                }
            }
            foreach (var root in RigRoots())
            {
                foreach (var s in root.GetComponentsInChildren<RightLeftMirrorSpring>(true))
                    if (s != null && s.enabled && s.holdable != null && s.holdable.holder != null) g.live++;
                foreach (var s in root.GetComponentsInChildren<RotSpring>(true))
                    if (s != null && s.enabled) g.live++;
            }
        }

        /// <summary>The whole gun pin: root, arms, springs. `rep` may be null
        /// (the sweep re-pins quietly).</summary>
        private static GunPin PinGun(StringBuilder rep)
        {
            var g = new GunPin();
            try
            {
                g.hand = WriteGunRoot(out g.moved);
                PinFreeArms(ref g);
                PinGunSprings(ref g);
            }
            catch (Exception ex) { g.error = ex.GetType().Name + ": " + Trunc(ex.Message, 120); }
            if (rep != null) rep.Append("gun pin: ").Append(g.Summary(-1)).Append('\n');
            return g;
        }

        /// <summary>One settle frame: the gun root back at the hand and the free
        /// arm at rest. True when the hand resolved, the arms met the contract
        /// (one bound to the gun, one free, none skipped) and neither write
        /// moved anything (both were already there); the callers count
        /// consecutive trues.</summary>
        private static bool HoldGun()
        {
            try
            {
                var g = new GunPin();
                g.hand = WriteGunRoot(out g.moved);
                PinFreeArms(ref g);
                return g.hand && !g.moved && !g.armMoved && g.arms == RIG_ARMS && g.gunSide == 1 && g.free == 1 && g.skipped == 0;
            }
            catch { return false; }   // a false resets the count, so the product run refuses unless the last frames held
        }

        /// <summary>What one face-frame pin did. `found`: CosmeticFrameCycler
        /// components under the rig roots, active or not, each once. `pinned`:
        /// disabled, with their SpriteRenderer on frame 0 (read back). `still`:
        /// disabled, with no frames (their Update draws nothing). `failed`: a
        /// destroyed cycler, one with frames and no SpriteRenderer, a write that
        /// threw, or one that does not read back as disabled on frame 0 -- the
        /// pass goes on to the next cycler either way. `ran`: the pass enumerated
        /// the rig to the end.</summary>
        private struct FramePin
        {
            internal bool ran;
            internal int found, pinned, still, failed;
            internal string error;   // the first failure

            /// <summary>Every cycler found is disabled on its frame 0 (or has no
            /// frames), and none failed.</summary>
            internal bool Pinned()
            {
                return ran && failed == 0 && pinned + still == found;
            }

            internal string Summary()
            {
                var sb = new StringBuilder();
                sb.Append("frames ran=").Append(ran ? 1 : 0).Append(" found=").Append(found).Append(" pinned=").Append(pinned)
                  .Append(" still=").Append(still).Append(" failed=").Append(failed);
                if (error != null) sb.Append(" first-failure=").Append(error);
                return sb.ToString();
            }
        }

        private static void FrameFailed(ref FramePin f, string why)
        {
            f.failed++;
            if (f.error == null) f.error = why;
        }

        /// <summary>Every animated face item on the rig on its first frame (the
        /// static-mode frame), its cycler off.</summary>
        private static FramePin PinFrames()
        {
            var f = new FramePin();
            try
            {
                var cyclers = new List<CustomCosmetics.CosmeticFrameCycler>();
                var seen = new HashSet<CustomCosmetics.CosmeticFrameCycler>();
                foreach (var root in RigRoots())
                    foreach (var c in root.GetComponentsInChildren<CustomCosmetics.CosmeticFrameCycler>(true))
                        if (!ReferenceEquals(c, null) && seen.Add(c)) cyclers.Add(c);
                f.found = cyclers.Count;
                foreach (var c in cyclers)
                {
                    try
                    {
                        if (c == null) { FrameFailed(ref f, "a destroyed cycler"); continue; }
                        c.enabled = false;
                        if (c.frames == null || c.frames.Length == 0)
                        {
                            if (!c.enabled) f.still++; else FrameFailed(ref f, c.name + " did not disable");
                            continue;
                        }
                        var sr = c.GetComponent<SpriteRenderer>();
                        if (sr == null) { FrameFailed(ref f, c.name + " has frames and no SpriteRenderer"); continue; }
                        sr.sprite = c.frames[0];
                        if (!c.enabled && sr.sprite == c.frames[0]) f.pinned++;
                        else FrameFailed(ref f, c.name + " does not read back disabled on frame 0");
                    }
                    catch (Exception ex) { FrameFailed(ref f, ex.GetType().Name + ": " + Trunc(ex.Message, 80)); }
                }
                f.ran = true;
            }
            catch (Exception ex) { FrameFailed(ref f, "enumeration threw " + ex.GetType().Name + ": " + Trunc(ex.Message, 80)); }
            return f;
        }

        /// <summary>One rig pin: the gun (GunPin) and, with `frames`, the face
        /// frames (FramePin; not run without it, so Pinned is false).</summary>
        private struct RigPin
        {
            internal GunPin gun;
            internal FramePin frames;

            internal bool Pinned(int stillFrames)
            {
                return gun.Pinned(stillFrames) && frames.Pinned();
            }

            internal string Summary(int stillFrames)
            {
                return gun.Summary(stillFrames) + " " + frames.Summary();
            }
        }

        /// <summary>The gun always; with `frames`, every animated face item on
        /// its first frame with its cycler off. Returns both results.</summary>
        private static RigPin PinRig(StringBuilder rep, bool frames)
        {
            var r = new RigPin();
            r.gun = PinGun(rep);
            if (frames) r.frames = PinFrames();
            if (rep != null) rep.Append(r.frames.Summary()).Append('\n');
            return r;
        }

        // ── particles ───────────────────────────────────────────────────────
        // The particle pin's step: every pinned system advances in steps of this
        // many milliseconds (a length that is not a multiple ends on one shorter
        // step), with Unity's fixed-timestep option off, so the step sequence is
        // a function of the length alone and never of Time.fixedDeltaTime. The
        // pin also turns every pinned system's prewarm off before its restart: a
        // prewarmed system comes out of a restart already advanced (under
        // RECIPE 2 the default body held rate x lifetime particles 0.5 s after
        // one) by a pass whose steps Unity does not document, so with prewarm
        // off the steps below are the only simulation the pin asks for.
        internal const int PARTICLE_STEP_MS = 20;
        // Time.maximumParticleDeltaTime while a pin steps, restored after: Unity's
        // default, above the step. Whether Simulate subdivides a step by that
        // global is not documented, so a pin does not leave it to whatever value
        // another mod set.
        private const float PARTICLE_MAX_DELTA = 0.03f;

        private struct PinnedParticle
        {
            internal ParticleSystem ps;
            internal string name;
            internal string path;     // RigPath, with "#k" for the k-th repeat of a path in hierarchy order
            internal bool live;       // read before the pass touched anything
            internal bool sub;        // some planned system's sub-emitter
            internal int before;
            internal uint seed;       // set by the pin; 0 for a system it did not pin
        }

        /// <summary>What PlanParticles found and what a pin of it will touch. A
        /// plan only reads the rig.</summary>
        private sealed class ParticlePlan
        {
            // The pin order: every sub-emitter before each system that triggers it.
            internal readonly List<PinnedParticle> order = new List<PinnedParticle>();
            // Active systems neither live nor reached from a planned system: left as they were.
            internal readonly List<PinnedParticle> left = new List<PinnedParticle>();
            internal int inventory;      // particle systems under the rig roots, active or not, each once
            internal int active;         // of those, active in the hierarchy
            internal int dups;           // systems whose hierarchy path repeats an earlier one
            internal int inactiveSubs;   // sub-emitter slots naming an inactive system (it draws nothing): not pinned
            internal string failure;     // why this plan cannot be pinned; null when it can
        }

        /// <summary>What one particle pin did. `planned`: the plan's systems.
        /// `pinned`: stopped, cleared, set to local space, prewarm off and
        /// seeded. `completed`: stepped, paused and read back not playing,
        /// seeded, local and not prewarmed. `respaced`/`unprewarmed`: pinned
        /// systems whose space or prewarm the pin changed. `failure`: the first
        /// thing that went wrong, the plan's own included; a pass that fails
        /// stops there.</summary>
        private struct ParticlePin
        {
            internal int inventory, planned, pinned, completed, left, subs, respaced, unprewarmed, dups, steps;
            internal string failure;

            /// <summary>The capture may take these particles: nothing failed, the
            /// plan was not empty (the character's body is a live particle
            /// system), and every planned system completed.</summary>
            internal bool Ok { get { return failure == null && planned > 0 && completed == planned; } }

            internal string Summary()
            {
                var sb = new StringBuilder();
                sb.Append("inventory=").Append(inventory).Append(" planned=").Append(planned).Append(" pinned=").Append(pinned)
                  .Append(" completed=").Append(completed).Append(" subs=").Append(subs).Append(" left=").Append(left)
                  .Append(" respaced=").Append(respaced).Append(" unprewarmed=").Append(unprewarmed)
                  .Append(" path-dups=").Append(dups).Append(" steps=").Append(steps);
                if (failure != null) sb.Append(" failure=").Append(failure);
                return sb.ToString();
            }
        }

        private static readonly List<PinnedParticle> _pinned = new List<PinnedParticle>();    // the last pin's systems, for the dev report
        private static readonly List<PinnedParticle> _leftOut = new List<PinnedParticle>();   // the last pin's plan's left systems

        /// <summary>The particle plan's liveness inputs, read on every frame of a
        /// settle: every ParticleSystem under the rig roots, each once, with
        /// whether it is active in the hierarchy and, when it is, whether it is
        /// live -- read as PlanParticles reads them. The first reading is the
        /// reference. A later reading whose systems or states differ from it
        /// counts as a change, and so does a reading that throws. The plan also
        /// reads hierarchy paths and sub-emitter slots; the watch does not.
        ///
        /// The product reads on every settle frame, then once more directly
        /// before its plan, and refuses the capture unless every reading matched
        /// the first; its plan then reads the systems, activity and liveness that
        /// every one of those readings saw. Two captures of one rig that both
        /// pass read the same ones when the rig's state changes only on fixed
        /// frames after its activation, since both read every frame from the same
        /// first settle frame on. They also do when the state changes once, at a
        /// fixed real time after the activation, provided each capture's first
        /// settle frame comes within DEFAULT_SETTLE of the activation in real
        /// time: a capture's last reading comes at least DEFAULT_SETTLE of real
        /// time after its settle starts, which is after the activation, so a
        /// change after one capture's last reading also comes after the other's
        /// first reading, and the other capture either sees it or reads the state
        /// before it as well. A state that changes and changes back between two
        /// readings is not seen.</summary>
        private sealed class ParticleWatch
        {
            private readonly Dictionary<ParticleSystem, int> _first = new Dictionary<ParticleSystem, int>();
            internal int reads, changes;
            internal string change;   // the first change, for the summary

            /// <summary>At least two readings and no change: no reading threw, and
            /// none differed from the first.</summary>
            internal bool Steady { get { return reads >= 2 && changes == 0; } }

            internal void Read()
            {
                reads++;
                try
                {
                    var owned = new HashSet<ParticleSystem>();
                    string diff = null;
                    foreach (var root in RigRoots())
                        foreach (var ps in root.GetComponentsInChildren<ParticleSystem>(true))
                        {
                            if (ReferenceEquals(ps, null) || ps == null || !owned.Add(ps)) continue;
                            int state = !ps.gameObject.activeInHierarchy ? 0 : (ps.isStopped && ps.particleCount == 0) ? 1 : 2;
                            int was;
                            if (reads == 1) _first[ps] = state;
                            else if (!_first.TryGetValue(ps, out was)) { if (diff == null) diff = "a new system " + PsName(ps); }
                            else if (was != state) { if (diff == null) diff = PsName(ps) + " " + was + "->" + state; }
                        }
                    if (reads > 1 && diff == null && owned.Count != _first.Count) diff = "a system is gone";
                    if (diff != null) Changed(diff);
                }
                catch (Exception ex) { Changed("threw " + ex.GetType().Name + ": " + Trunc(ex.Message, 80)); }
            }

            private void Changed(string what)
            {
                changes++;
                if (change == null) change = "reading " + reads + ": " + what;
            }

            internal string Summary()
            {
                return "reads=" + reads + " systems=" + _first.Count + " changes=" + changes + (change != null ? " first=" + change : "");
            }
        }

        /// <summary>Plans a pin of the particle systems that are LIVE now, and of
        /// every system they reach as sub-emitters. Live is anything but stopped
        /// with no particles: playing, or paused holding a simulated state (a
        /// static aura). Every system's liveness is read before the plan is
        /// built, and nothing is written.
        ///
        /// The inventory is every ParticleSystem under the rig roots, active or
        /// not, each once. Only active systems are planned (an inactive one
        /// draws nothing). From each live active system (every active one with
        /// `all`, the dev negative control), in hierarchy order, the enabled
        /// sub-emitter modules are followed: a slot naming a system outside the
        /// inventory fails the plan, as does a cycle; an empty slot emits nothing;
        /// a slot naming an inactive system is counted and not followed. Each
        /// system is planned once, after every sub-emitter it reaches.
        ///
        /// A system that is not live and that no planned system reaches is left
        /// as it is. Restarting a stopped system fires its t=0 burst, which would
        /// put an effect the character is not having into the picture: the
        /// player prefab carries one-shot status and movement systems with
        /// playOnAwake off (frost snow, landing and jump smoke, block status)
        /// that sit stopped and empty unless something plays them.
        ///
        /// Paths: RigPath, and a "#k" suffix on the k-th later system (hierarchy
        /// order over the whole inventory) with the same path, so a path, and the
        /// seed derived from it, depend on the hierarchy alone -- never on which
        /// systems are live or planned.</summary>
        private static ParticlePlan PlanParticles(bool all)
        {
            var plan = new ParticlePlan();
            try
            {
                var inventory = new List<ParticleSystem>();
                var owned = new HashSet<ParticleSystem>();
                foreach (var root in RigRoots())
                    foreach (var ps in root.GetComponentsInChildren<ParticleSystem>(true))
                        if (!ReferenceEquals(ps, null) && ps != null && owned.Add(ps)) inventory.Add(ps);
                plan.inventory = inventory.Count;
                var paths = new Dictionary<ParticleSystem, string>();
                var seenPaths = new Dictionary<string, int>(StringComparer.Ordinal);
                var live = new Dictionary<ParticleSystem, bool>();
                foreach (var ps in inventory)
                {
                    string path = RigPath(ps.transform);
                    int dup;
                    if (seenPaths.TryGetValue(path, out dup)) { seenPaths[path] = dup + 1; path += "#" + (dup + 1); plan.dups++; }
                    else seenPaths[path] = 0;
                    paths[ps] = path;
                    if (ps.gameObject.activeInHierarchy) live[ps] = !(ps.isStopped && ps.particleCount == 0);
                }
                plan.active = live.Count;
                var state = new Dictionary<ParticleSystem, int>();   // 1: being planned, 2: planned
                var subs = new HashSet<ParticleSystem>();
                foreach (var ps in inventory)
                {
                    bool isLive;
                    if (!live.TryGetValue(ps, out isLive) || !(isLive || all)) continue;
                    if (!PlanVisit(ps, plan, owned, live, paths, state, subs)) break;
                }
                if (plan.failure == null)
                {
                    for (int k = 0; k < plan.order.Count; k++)
                    {
                        var p = plan.order[k];
                        p.sub = subs.Contains(p.ps);
                        plan.order[k] = p;
                    }
                    foreach (var ps in inventory)
                        if (live.ContainsKey(ps) && !state.ContainsKey(ps))
                            plan.left.Add(new PinnedParticle { ps = ps, name = PsName(ps), path = paths[ps], live = live[ps], before = ps.particleCount });
                }
            }
            catch (Exception ex) { plan.failure = "plan threw " + ex.GetType().Name + ": " + Trunc(ex.Message, 120); }
            return plan;
        }

        /// <summary>Plans `ps` after every sub-emitter it reaches (post-order).
        /// False when the plan failed; plan.failure says why.</summary>
        private static bool PlanVisit(ParticleSystem ps, ParticlePlan plan, HashSet<ParticleSystem> owned, Dictionary<ParticleSystem, bool> live,
                                      Dictionary<ParticleSystem, string> paths, Dictionary<ParticleSystem, int> state, HashSet<ParticleSystem> subs)
        {
            int s;
            if (state.TryGetValue(ps, out s))
            {
                if (s == 1) { plan.failure = "a sub-emitter cycle through " + paths[ps]; return false; }
                return true;
            }
            state[ps] = 1;
            var se = ps.subEmitters;
            if (se.enabled)
            {
                int n = se.subEmittersCount;
                for (int i = 0; i < n; i++)
                {
                    var sub = se.GetSubEmitterSystem(i);
                    if (ReferenceEquals(sub, null) || sub == null) continue;   // an empty slot emits nothing
                    if (!owned.Contains(sub)) { plan.failure = "a sub-emitter of " + paths[ps] + " is outside the rig (" + sub.name + ")"; return false; }
                    if (!live.ContainsKey(sub)) { plan.inactiveSubs++; continue; }
                    subs.Add(sub);
                    if (!PlanVisit(sub, plan, owned, live, paths, state, subs)) return false;
                }
            }
            state[ps] = 2;
            plan.order.Add(new PinnedParticle { ps = ps, name = PsName(ps), path = paths[ps], live = live[ps], before = ps.particleCount });
            return true;
        }

        private static string PsName(ParticleSystem ps)
        {
            var parent = ps.transform.parent;
            return (parent != null ? parent.name + "/" : "") + ps.name;
        }

        /// <summary>Pins `plan`: every planned system is stopped and cleared, set
        /// to local simulation space, given prewarm off and the seed
        /// ParticleSeed derives from its path (and `salt`) -- each exactly once;
        /// then all of them are re-simulated from a restart for `simSecs`
        /// together, one step of PARTICLE_STEP_MS at a time (the length taken to
        /// whole milliseconds, a shorter last step for the remainder), with the
        /// fixed-timestep option off; then each is paused and read back. In each
        /// step, every planned system's own Simulate is called once
        /// (withChildren false), in plan order: a sub-emitter's call comes before
        /// the call of every system that triggers it, so on the restart step each
        /// sub-emitter is restarted before anything that triggers it has been
        /// advanced. The product passes PlanParticles(false), PARTICLE_SIM_SECS
        /// and salt 0.
        ///
        /// Local space whatever it was: forcing Local makes the snapshot
        /// independent of the animated-cosmetics setting, which sets an aura's
        /// space (World when on, Local when off) and which the descriptor also
        /// records as anim=. The vanilla skin is already local. A local-space
        /// aura is not guaranteed to look like the World-space one an animating
        /// viewer sees in game, so that belongs to the look check, not to
        /// determinism.
        ///
        /// Prewarm off whatever it was: see PARTICLE_STEP_MS. The default body's
        /// system reports prewarm on (`psinfo`), and under RECIPE 2, which left
        /// prewarm alone, a restart of it held its rate x lifetime (75 particles)
        /// at 0.5 s. With prewarm off it starts from no particles, so its count
        /// depends on the length; `psinfo` prints each pinned system's count after
        /// the pin, and `steady` (rate x lifetime) when both are constant.
        ///
        /// Two systems may share a seed (their paths hash alike): a seed is a
        /// function of the system's own path, never of the others.
        ///
        /// A failure ends the pass where it happens and is the result's failure;
        /// what it leaves depends on where that is. No plan, the plan's own
        /// failure, or a length whose rounded milliseconds are not positive: no
        /// system is touched. In the configure pass, a destroyed planned system
        /// or a throw: the systems before it are configured, the one that threw
        /// may be configured part of the way, the systems after it are not
        /// touched, and none is stepped. During the steps, a throw: every planned
        /// system is configured and stepped as far as the steps got for it (none,
        /// part or all of the length), and none is paused or read back. In the
        /// read-back pass, a read-back that fails or a throw: every planned system
        /// is configured and stepped in full, and the systems after it are
        /// neither paused nor read back. Time.maximumParticleDeltaTime is
        /// restored whenever the pass set it. `detail` (dev only) adds one line
        /// per pinned system. `rep` may be null.</summary>
        private static ParticlePin PinParticles(StringBuilder rep, ParticlePlan plan, float simSecs, int salt, bool detail)
        {
            var r = new ParticlePin();
            _pinned.Clear(); _leftOut.Clear();
            float heldMax = 0f;
            bool held = false;
            try
            {
                if (plan == null) r.failure = "no plan";
                else
                {
                    r.inventory = plan.inventory; r.planned = plan.order.Count; r.left = plan.left.Count; r.dups = plan.dups;
                    _leftOut.AddRange(plan.left);
                    int totalMs = Mathf.RoundToInt(simSecs * 1000f);
                    if (plan.failure != null) r.failure = plan.failure;
                    else if (totalMs <= 0) r.failure = "length " + Secs(simSecs) + " s is not positive";
                    else
                    {
                        var systems = new ParticleSystem[plan.order.Count];
                        var seeds = new uint[plan.order.Count];
                        for (int k = 0; k < plan.order.Count && r.failure == null; k++)
                        {
                            var p = plan.order[k];
                            if (p.sub) r.subs++;
                            if (p.ps == null) { r.failure = "a planned system was destroyed: " + p.path; break; }
                            systems[k] = p.ps;
                            seeds[k] = ParticleSeed(p.path, salt);
                            p.ps.Stop(false, ParticleSystemStopBehavior.StopEmittingAndClear);   // the seed can only be set on a stopped system
                            var main = p.ps.main;
                            if (main.simulationSpace != ParticleSystemSimulationSpace.Local) { main.simulationSpace = ParticleSystemSimulationSpace.Local; r.respaced++; }
                            if (main.prewarm) { main.prewarm = false; r.unprewarmed++; }
                            p.ps.useAutoRandomSeed = false;
                            p.ps.randomSeed = seeds[k];
                            r.pinned++;
                        }
                        if (r.failure == null)
                        {
                            int full = totalMs / PARTICLE_STEP_MS, remMs = totalMs % PARTICLE_STEP_MS;
                            int stepCount = full + (remMs > 0 ? 1 : 0);
                            float step = PARTICLE_STEP_MS / 1000f, last = remMs / 1000f;
                            heldMax = Time.maximumParticleDeltaTime;
                            held = true;
                            Time.maximumParticleDeltaTime = PARTICLE_MAX_DELTA;
                            for (int s = 0; s < stepCount; s++)
                            {
                                float dt = s < full ? step : last;
                                for (int k = 0; k < systems.Length; k++)
                                    systems[k].Simulate(dt, false, s == 0, false);
                                r.steps++;
                            }
                            for (int k = 0; k < systems.Length; k++)
                            {
                                var p = plan.order[k];
                                systems[k].Pause(false);
                                var main = systems[k].main;
                                if (systems[k].isPlaying || systems[k].useAutoRandomSeed || systems[k].randomSeed != seeds[k]
                                    || main.simulationSpace != ParticleSystemSimulationSpace.Local || main.prewarm)
                                { r.failure = "read-back failed on " + p.path; break; }
                                p.seed = seeds[k];
                                _pinned.Add(p);
                                r.completed++;
                                if (detail && rep != null) rep.Append(ParticleDetail(p)).Append('\n');
                            }
                        }
                    }
                }
            }
            catch (Exception ex) { r.failure = "threw " + ex.GetType().Name + ": " + Trunc(ex.Message, 120); }
            finally { if (held) Time.maximumParticleDeltaTime = heldMax; }
            if (rep != null)
                rep.Append("particles ").Append(r.Summary()).Append(" secs=").Append(Secs(simSecs)).Append(" salt=").Append(salt).Append('\n');
            return r;
        }

        /// <summary>The seed a pinned system gets: FNV-1a of its path, then of
        /// the salt's four bytes when the salt is not 0.</summary>
        private static uint ParticleSeed(string path, int salt)
        {
            uint h = Fnv32(Encoding.UTF8.GetBytes(path ?? ""));
            if (salt != 0) h = Fnv32(new[] { (byte)salt, (byte)(salt >> 8), (byte)(salt >> 16), (byte)(salt >> 24) }, h);
            return h;
        }

        /// <summary>Names from the transform's scene root down to it, '/'-joined.</summary>
        private static string RigPath(Transform t)
        {
            var parts = new List<string>();
            for (var q = t; q != null; q = q.parent) parts.Add(q.name);
            parts.Reverse();
            return string.Join("/", parts.ToArray());
        }

        /// <summary>Dev (`psinfo`): a pinned system's modules and counts. For a
        /// system with constant rate and lifetime that is not prewarmed, `steady`
        /// is rate x lifetime: about the count a looping system emitting at that
        /// rate holds once it has run longer than its lifetime (bursts, a start
        /// delay or a lower max change it).</summary>
        private static string ParticleDetail(PinnedParticle p)
        {
            var sb = new StringBuilder();
            try
            {
                var ps = p.ps; var mm = ps.main; var em = ps.emission;
                sb.Append("ps ").Append(p.path).Append(" seed=").Append(p.seed.ToString("x8")).Append(" sub=").Append(p.sub).Append(" dur=").Append(mm.duration).Append(" loop=").Append(mm.loop).Append(" prewarm=").Append(mm.prewarm)
                  .Append(" life=").Append(mm.startLifetime.constantMin).Append("..").Append(mm.startLifetime.constantMax).Append(" lifeMode=").Append(mm.startLifetime.mode)
                  .Append(" rate=").Append(em.rateOverTime.constant).Append(" rateMode=").Append(em.rateOverTime.mode).Append(" bursts=").Append(em.burstCount)
                  .Append(" max=").Append(mm.maxParticles).Append(" colMode=").Append(mm.startColor.mode)
                  .Append(" count=").Append(ps.particleCount);
                if (!mm.prewarm && mm.startLifetime.mode == ParticleSystemCurveMode.Constant && em.rateOverTime.mode == ParticleSystemCurveMode.Constant)
                    sb.Append(" steady=").Append((em.rateOverTime.constant * mm.startLifetime.constant).ToString("F1"));
            }
            catch (Exception ex) { sb.Append("ps ").Append(p.path).Append(" threw: ").Append(ex.Message); }
            return sb.ToString();
        }

        /// <summary>Dev report, read after the capture: one line per system the
        /// last pin pinned (live, particles before the pin, particles now, seed)
        /// and per system its plan left alone, then the count of left systems
        /// holding particles now (want 0: a left system is stopped and empty). A
        /// pinned system may hold none now: a burst whose particles all died
        /// inside the simulated length.</summary>
        private static string ParticlePinReport()
        {
            var sb = new StringBuilder();
            int live = 0, liveHolding = 0, leftHolding = 0;
            foreach (var p in _pinned)
            {
                int now = -1;
                try { if (p.ps != null) now = p.ps.particleCount; } catch { }
                if (p.live) { live++; if (now > 0) liveHolding++; }
                sb.Append("particle ").Append(p.name).Append(" pinned live=").Append(p.live).Append(" sub=").Append(p.sub).Append(" before=").Append(p.before).Append(" after=").Append(now)
                  .Append(" seed=").Append(p.seed.ToString("x8")).Append('\n');
            }
            foreach (var p in _leftOut)
            {
                int now = -1;
                try { if (p.ps != null) now = p.ps.particleCount; } catch { }
                if (now > 0) leftHolding++;
                sb.Append("particle ").Append(p.name).Append(" left live=").Append(p.live).Append(" before=").Append(p.before).Append(" after=").Append(now).Append('\n');
            }
            sb.Append("particles after capture: pinned=").Append(_pinned.Count).Append(" live=").Append(live).Append(" live-holding=").Append(liveHolding)
              .Append(" left=").Append(_leftOut.Count).Append(" left-holding=").Append(leftHolding).Append(" (want 0)\n");
            return sb.ToString();
        }

        /// <summary>True when there are exactly two legs and each foot target
        /// sits on MakeGround's floor surface (within 0.05) and under the rig
        /// (within 0.5 in x). `summary` names each foot relative to PARK, with
        /// '!' after any foot that failed.</summary>
        private static bool LegsPlanted(out string summary)
        {
            var sb = new StringBuilder();
            bool ok = _legs.Count == 2 && !float.IsNaN(_groundTop);
            if (_legs.Count != 2) sb.Append("count=").Append(_legs.Count).Append(' ');
            if (float.IsNaN(_groundTop)) sb.Append("nofloor ");
            foreach (var leg in _legs)
            {
                if (leg == null || leg.footTarget == null) { ok = false; sb.Append("null! "); continue; }
                Vector3 f = leg.footTarget.position;
                bool p = !float.IsNaN(_groundTop) && Mathf.Abs(f.y - _groundTop) <= 0.05f && Mathf.Abs(f.x - PARK.x) <= 0.5f;
                ok &= p;
                sb.Append(leg.name).Append(V(f - PARK)).Append(p ? " " : "! ");
            }
            summary = sb.ToString().Trim();
            return ok;
        }

        // ── dev: the pose probe and the particle-length sweep ───────────────
        private const int SWEEP_MAX_LENGTHS = 16;
        private const int SWEEP_MAX_SALTS = 4;
        // The sweep's work cap, checked before the rig is built (SweepRefusal).
        // Each entry re-simulates every planned particle system for its length in
        // PARTICLE_STEP_MS steps, renders the camera twice and reads both back,
        // encodes a PNG and measures the body over every pixel (BodyLuminance:
        // fifteen erosion passes and one labelling pass), all in one frame; the
        // entries are a frame apart.
        private const int SWEEP_MAX_ENTRIES = 24;          // lengths x salts
        private const int SWEEP_MAX_SIM_MS = 240000;       // every entry's length, summed

        /// <summary>Dev probe (`poseprobe`): every transform under the rig roots,
        /// position relative to PARK, rotation and lossy scale, at full float
        /// precision, for diffing two runs that should be identical.</summary>
        private static void PoseProbe(StringBuilder rep)
        {
            try
            {
                var inv = System.Globalization.CultureInfo.InvariantCulture;
                foreach (var root in RigRoots())
                    foreach (var t in root.GetComponentsInChildren<Transform>(true))
                    {
                        Vector3 p = t.position - PARK; Quaternion r = t.rotation; Vector3 s = t.lossyScale;
                        rep.Append("pose ").Append(RigPath(t)).Append(" act=").Append(t.gameObject.activeInHierarchy ? 1 : 0)
                           .Append(" p=").Append(p.x.ToString("R", inv)).Append(',').Append(p.y.ToString("R", inv)).Append(',').Append(p.z.ToString("R", inv))
                           .Append(" q=").Append(r.x.ToString("R", inv)).Append(',').Append(r.y.ToString("R", inv)).Append(',').Append(r.z.ToString("R", inv)).Append(',').Append(r.w.ToString("R", inv))
                           .Append(" s=").Append(s.x.ToString("R", inv)).Append(',').Append(s.y.ToString("R", inv)).Append(',').Append(s.z.ToString("R", inv))
                           .Append('\n');
                    }
            }
            catch (Exception ex) { rep.Append("pose probe threw: ").Append(ex.Message).Append('\n'); }
        }

        private static string Secs(float s) { return s.ToString("0.###", System.Globalization.CultureInfo.InvariantCulture); }

        /// <summary>Whole milliseconds as seconds, from the integer: no trailing
        /// zeros and no point for a whole second (5500 -> "5.5", 10000 -> "10"),
        /// so two different values never print alike.</summary>
        private static string SecsOfMs(int ms)
        {
            int whole = ms / 1000, frac = ms % 1000;
            if (frac == 0) return whole.ToString(System.Globalization.CultureInfo.InvariantCulture);
            return whole.ToString(System.Globalization.CultureInfo.InvariantCulture) + "." + frac.ToString("000", System.Globalization.CultureInfo.InvariantCulture).TrimEnd('0');
        }

        /// <summary>Sweep lengths "S:S:..." in seconds, each rounded to whole
        /// milliseconds and kept in the order given. A value outside
        /// minMs..maxMs, or one that rounds to a length already kept, is
        /// reported and dropped, so no two entries share a file name or a TSV
        /// label.</summary>
        private static List<int> ParseMillis(string list, int minMs, int maxMs, int cap, StringBuilder rep)
        {
            var o = new List<int>();
            foreach (var part in list.Split(':'))
            {
                double v;
                if (!double.TryParse(part.Trim(), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out v)
                    || double.IsNaN(v) || double.IsInfinity(v) || Math.Round(v * 1000.0) < minMs || Math.Round(v * 1000.0) > maxMs)
                { rep.Append("sweep: ignored '").Append(part).Append("' (want ").Append(SecsOfMs(minMs)).Append("..").Append(SecsOfMs(maxMs)).Append(")\n"); continue; }
                int ms = (int)Math.Round(v * 1000.0);
                if (o.Contains(ms)) { rep.Append("sweep: dropped '").Append(part).Append("', the same length as ").Append(SecsOfMs(ms)).Append('\n'); continue; }
                if (o.Count >= cap) { rep.Append("sweep: more than ").Append(cap).Append(" values, the rest ignored\n"); break; }
                o.Add(ms);
            }
            return o.Count > 0 ? o : null;
        }

        /// <summary>Seed salts "N:N:...", kept in the order given; a value out of
        /// range or already kept is reported and dropped.</summary>
        private static List<int> ParseInts(string list, int min, int max, int cap, StringBuilder rep)
        {
            var o = new List<int>();
            foreach (var part in list.Split(':'))
            {
                int v;
                if (!int.TryParse(part.Trim(), out v) || v < min || v > max)
                { rep.Append("salts: ignored '").Append(part).Append("' (want ").Append(min).Append("..").Append(max).Append(")\n"); continue; }
                if (o.Contains(v)) { rep.Append("salts: dropped a repeat of ").Append(v).Append('\n'); continue; }
                if (o.Count >= cap) { rep.Append("salts: more than ").Append(cap).Append(" values, the rest ignored\n"); break; }
                o.Add(v);
            }
            return o.Count > 0 ? o : null;
        }

        /// <summary>Why a sweep of `lengths` (ms) x `salts` (null: salt 0 only) at
        /// `size` is refused, or null. At any size but the product's: the body
        /// measure erodes a fixed 14 px, which is calibrated on the product
        /// size. Over SWEEP_MAX_ENTRIES entries, or over SWEEP_MAX_SIM_MS of
        /// particle simulation summed over the entries.</summary>
        private static string SweepRefusal(int size, List<int> lengths, List<int> salts)
        {
            int saltCount = salts == null ? 1 : salts.Count;
            long entries = (long)lengths.Count * saltCount;
            long simMs = 0;
            foreach (var ms in lengths) simMs += (long)ms * saltCount;
            if (size != DEFAULT_SIZE) return "size=" + size + " is not the product size " + DEFAULT_SIZE + " the body measure is calibrated on";
            if (entries > SWEEP_MAX_ENTRIES) return entries + " entries (lengths x salts), over the cap of " + SWEEP_MAX_ENTRIES;
            if (simMs > SWEEP_MAX_SIM_MS) return SecsOfMs((int)Math.Min(simMs, int.MaxValue)) + " s of particle simulation over all entries, over the cap of " + SecsOfMs(SWEEP_MAX_SIM_MS) + " s";
            return null;
        }

        /// <summary>Dev (`sweep`): one particle length (ms) and seed salt on the
        /// settled rig. Re-pins the gun quietly, pins `plan` at that length with
        /// `salt`, captures the matte through `table` exactly as the product
        /// does (ungraded when `table` is null), writes
        /// pc_portrait_{tag}_sim{secs}_s{salt}.png, and appends the body
        /// luminance (BodyLuminance, on `buffers`) and each pinned system's
        /// particle count to `tsv` and the report. Salt 0 at PARTICLE_SIM_SECS
        /// repeats the run's own snapshot, so its sha is expected to equal the
        /// run's _graded sha; a difference means something on the rig moved
        /// between the two captures.</summary>
        private static void SweepEntry(StringBuilder rep, StringBuilder tsv, MeasureBuffers buffers, Camera cam, int size, string tag, byte[] table, string tableName,
                                       ParticlePlan plan, int ms, int salt)
        {
            var inv = System.Globalization.CultureInfo.InvariantCulture;
            string secs = SecsOfMs(ms);
            try
            {
                var g = PinGun(null);
                var pp = PinParticles(null, plan, ms / 1000f, salt, false);
                float lit, partial;
                var px = MattePixels(cam, size, out lit, out partial);
                if (table != null) GradePixels(px, table);
                byte[] png = EncodePng(px, size);
                string file = "pc_portrait_" + tag + "_sim" + secs + "_s" + salt + ".png";
                File.WriteAllBytes(Path.Combine(BepInEx.Paths.BepInExRootPath, file), png);
                int bodyPx; float cx, cyTop;
                double lum = BodyLuminance(px, buffers, out bodyPx, out cx, out cyTop);
                var systems = new StringBuilder();
                foreach (var p in _pinned)
                {
                    int now = -1; try { if (p.ps != null) now = p.ps.particleCount; } catch { }
                    if (systems.Length > 0) systems.Append(';');
                    systems.Append(p.path).Append('=').Append(now);
                }
                string sha = Sha12(png);
                tsv.Append(secs).Append('\t').Append(salt).Append('\t').Append(lum.ToString("F4", inv)).Append('\t').Append(bodyPx)
                   .Append('\t').Append(cx.ToString("F1", inv)).Append('\t').Append(cyTop.ToString("F1", inv)).Append('\t').Append((100f * lit).ToString("F2", inv))
                   .Append('\t').Append(g.Pinned(GUN_STILL_FRAMES) ? 1 : 0).Append('\t').Append(pp.Ok ? 1 : 0).Append('\t').Append(sha).Append('\t').Append(systems).Append('\t').Append(file).Append('\n');
                rep.Append("sweep secs=").Append(secs).Append(" salt=").Append(salt).Append(" table=").Append(tableName ?? "none")
                   .Append(" body_lum=").Append(lum.ToString("F4", inv)).Append(" body_px=").Append(bodyPx).Append(" sha=").Append(sha)
                   .Append(" gun=").Append(g.Summary(-1)).Append(" particles=").Append(pp.Summary()).Append(" systems=").Append(systems).Append(" -> ").Append(file).Append('\n');
            }
            catch (Exception ex) { rep.Append("sweep secs=").Append(secs).Append(" salt=").Append(salt).Append(" threw: ").Append(ex.Message).Append('\n'); }
        }

        /// <summary>The body measure's work arrays for one size, allocated once
        /// per sweep and reused by every entry.</summary>
        private sealed class MeasureBuffers
        {
            internal readonly int size;
            internal readonly bool[] a, b, c;
            internal readonly int[] label, queue;

            internal MeasureBuffers(int size)
            {
                this.size = size;
                int n = size * size;
                a = new bool[n]; b = new bool[n]; c = new bool[n];
                label = new int[n]; queue = new int[n];
            }
        }

        /// <summary>Dev measure: the body luminance of a straight-colour matte,
        /// by the algorithm of `portrait()` + `lum()` in
        /// ai-collab/sept14-gacha/portrait-render/verify/measure_look.py, which
        /// judged round 1: the solid mask is opaque (a = 255), not near-white
        /// (min channel &lt;= 200) and not dark (max channel &gt;= 70); it is eroded 14
        /// times (4-neighbour, the image edge does not erode), its largest
        /// 4-connected component kept and eroded once more; the mean sRGB of
        /// those pixels, each channel rounded to 0.1 as that script stores it, is
        /// linearised per channel and weighted 0.2126/0.7152/0.0722. The two
        /// agree up to rounding (a channel mean at a 0.05 midpoint may round
        /// the other way) except when two components tie for largest (the pixel
        /// rows run the other way here); sweep_measure.py re-measures the PNGs
        /// with the script itself. NaN when no body is found. `cx`/`cyTop`: the
        /// component's centroid, y from the top like the PNG. Works in `buf`,
        /// whose arrays it overwrites.</summary>
        private static double BodyLuminance(Color32[] px, MeasureBuffers buf, out int bodyPx, out float cx, out float cyTop)
        {
            bodyPx = 0; cx = float.NaN; cyTop = float.NaN;
            int size = buf.size, n = size * size;
            var solid = buf.a;
            for (int i = 0; i < n; i++)
            {
                var c = px[i];
                int mn = Math.Min(c.r, Math.Min(c.g, c.b)), mx = Math.Max(c.r, Math.Max(c.g, c.b));
                solid[i] = c.a == 255 && mn <= 200 && mx >= 70;
            }
            var eroded = Erode(solid, buf.b, size, 14);           // in a or b
            var core = buf.c;
            LargestComponent(eroded, core, buf.label, buf.queue, size);
            long sx = 0, sy = 0; int cn = 0;
            for (int i = 0; i < n; i++) if (core[i]) { sx += i % size; sy += i / size; cn++; }
            if (cn == 0) return double.NaN;
            cx = (float)((double)sx / cn); cyTop = (float)(size - 1 - (double)sy / cn);
            var body = Erode(core, eroded, size, 1);              // one pass: written into `eroded`, which the core no longer needs
            long r = 0, g = 0, b = 0;
            for (int i = 0; i < n; i++) if (body[i]) { r += px[i].r; g += px[i].g; b += px[i].b; bodyPx++; }
            if (bodyPx == 0) return double.NaN;
            double mr = Math.Round((double)r / bodyPx, 1), mg = Math.Round((double)g / bodyPx, 1), mb = Math.Round((double)b / bodyPx, 1);
            return 0.2126 * Lin(mr) + 0.7152 * Lin(mg) + 0.0722 * Lin(mb);
        }

        private static double Lin(double c8)
        {
            double c = c8 / 255.0;
            return c <= 0.04045 ? c / 12.92 : Math.Pow((c + 0.055) / 1.055, 2.4);
        }

        /// <summary>`passes` 4-neighbour erosions of `m`, alternating between `m`
        /// and `scratch` (both are overwritten); returns the one holding the
        /// result.</summary>
        private static bool[] Erode(bool[] m, bool[] scratch, int size, int passes)
        {
            var cur = m;
            var next = scratch;
            for (int k = 0; k < passes; k++)
            {
                for (int y = 0; y < size; y++)
                {
                    int row = y * size;
                    for (int x = 0; x < size; x++)
                    {
                        int i = row + x;
                        bool v = cur[i];
                        if (v && y > 0) v = cur[i - size];
                        if (v && y < size - 1) v = cur[i + size];
                        if (v && x > 0) v = cur[i - 1];
                        if (v && x < size - 1) v = cur[i + 1];
                        next[i] = v;
                    }
                }
                var t = cur; cur = next; next = t;
            }
            return cur;
        }

        /// <summary>The largest 4-connected component of `m` into `o` (every
        /// element written; the first found wins a tie), labelling in `label` and
        /// `queue`.</summary>
        private static void LargestComponent(bool[] m, bool[] o, int[] label, int[] queue, int size)
        {
            int n = m.Length;
            Array.Clear(label, 0, n);
            int bestLabel = 0, bestCount = 0, next = 0;
            for (int s = 0; s < n; s++)
            {
                if (!m[s] || label[s] != 0) continue;
                next++;
                int head = 0, tail = 0;
                queue[tail++] = s; label[s] = next;
                while (head < tail)
                {
                    int i = queue[head++], x = i % size;
                    if (i >= size && m[i - size] && label[i - size] == 0) { label[i - size] = next; queue[tail++] = i - size; }
                    if (i + size < n && m[i + size] && label[i + size] == 0) { label[i + size] = next; queue[tail++] = i + size; }
                    if (x > 0 && m[i - 1] && label[i - 1] == 0) { label[i - 1] = next; queue[tail++] = i - 1; }
                    if (x < size - 1 && m[i + 1] && label[i + 1] == 0) { label[i + 1] = next; queue[tail++] = i + 1; }
                }
                if (tail > bestCount) { bestCount = tail; bestLabel = next; }
            }
            for (int i = 0; i < n; i++) o[i] = bestLabel != 0 && label[i] == bestLabel;
        }

        /// <summary>Dev probe: per leg, the move delta IkLeg aims its ray with,
        /// the foot target relative to the rig, and the surface the ray is on.</summary>
        private static string LegTrace()
        {
            var sb = new StringBuilder();
            try
            {
                Vector3 rig = _clone != null ? _clone.transform.position : PARK;
                foreach (var leg in _legs)
                {
                    if (leg == null) { sb.Append("null "); continue; }
                    sb.Append(leg.name).Append(" d=(").Append(leg.deltaPos.x.ToString("F2")).Append(',').Append(leg.deltaPos.y.ToString("F2")).Append(')')
                      .Append(" foot=").Append(leg.footTarget != null ? V(leg.footTarget.position - rig) : "null")
                      .Append(" ray=").Append(leg.raycastTransform != null ? leg.raycastTransform.name : "none")
                      .Append(" down=").Append(leg.footDown).Append(" pred=").Append(leg.prediction.ToString("F1"))
                      .Append(" | ");
                }
            }
            catch (Exception ex) { sb.Append("trace threw: ").Append(ex.Message); }
            return sb.ToString();
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
        /// <summary>Dev form: ONE matte capture written twice --
        /// pc_portrait_{tag}_matte.png ungraded (this rig's pose, with legs,
        /// gun, frames and particles pinned as the run's options say -- so not
        /// the RECIPE 1 picture) and
        /// pc_portrait_{tag}_graded.png through `lut` -- so the A/B pair comes
        /// from the same pixels. The report counts alpha bytes that differ
        /// between the two (GradePixels must leave alpha untouched: expect 0).</summary>
        private static void RenderMatte(Camera cam, int size, string tag, StringBuilder rep, byte[] lut, string lutName)
        {
            float lit, partial;
            Color32[] px = null;
            try { px = MattePixels(cam, size, out lit, out partial); }
            catch (Exception ex) { rep.Append("render ").Append(tag).Append("_matte threw: ").Append(ex.Message).Append('\n'); return; }
            try
            {
                byte[] bytes = EncodePng(px, size);
                string file = Path.Combine(BepInEx.Paths.BepInExRootPath, "pc_portrait_" + tag + "_matte.png");
                File.WriteAllBytes(file, bytes);
                rep.Append("render ").Append(tag).Append("_matte: lit=").Append((100f * lit).ToString("F1"))
                   .Append("% partial-alpha=").Append((100f * partial).ToString("F1"))
                   .Append("% bytes=").Append(bytes.Length).Append(" sha=").Append(Sha12(bytes)).Append(" -> ").Append(file).Append('\n');
                if (lut == null) { rep.Append("render ").Append(tag).Append("_graded: skipped (no table: ").Append(lutName).Append(")\n"); return; }
                var graded = (Color32[])px.Clone();
                GradePixels(graded, lut);
                int alphaDiff = 0;
                for (int i = 0; i < px.Length; i++) if (px[i].a != graded[i].a) alphaDiff++;
                byte[] gbytes = EncodePng(graded, size);
                string gfile = Path.Combine(BepInEx.Paths.BepInExRootPath, "pc_portrait_" + tag + "_graded.png");
                File.WriteAllBytes(gfile, gbytes);
                rep.Append("render ").Append(tag).Append("_graded: table=").Append(lutName).Append(" alpha-bytes-changed=").Append(alphaDiff)
                   .Append(" bytes=").Append(gbytes.Length).Append(" sha=").Append(Sha12(gbytes)).Append(" -> ").Append(gfile).Append('\n');
            }
            catch (Exception ex) { rep.Append("render ").Append(tag).Append(" write threw: ").Append(ex.Message).Append('\n'); }
        }

        /// <summary>The matte graded through `lut` as PNG bytes, plus its lit
        /// and partial-alpha fractions and the graded pixels (for the preview);
        /// null when a step threw. Every product picture is graded: GradePixels
        /// throws on a missing or wrong-size table, so there is no ungraded
        /// path through here (the dev renders grade on their own). The fractions
        /// read alpha only, which grading never writes.</summary>
        private static byte[] MatteBytes(Camera cam, int size, byte[] lut, out float lit, out float partial, out Color32[] pixels)
        {
            lit = 0f; partial = 0f; pixels = null;
            try
            {
                var o = MattePixels(cam, size, out lit, out partial);
                GradePixels(o, lut);                           // straight colour, after the matte, where a > 0
                pixels = o;
                return EncodePng(o, size);
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[PORTRAIT] matte threw: " + ex.Message); return null; }
        }

        private static byte[] EncodePng(Color32[] px, int size)
        {
            Texture2D outTex = null;
            try
            {
                outTex = new Texture2D(size, size, TextureFormat.RGBA32, false);
                outTex.SetPixels32(px); outTex.Apply();
                return outTex.EncodeToPNG();
            }
            finally { if (outTex != null) UnityEngine.Object.Destroy(outTex); }
        }

        /// <summary>The #630 difference matte as straight (un-premultiplied)
        /// RGBA; throws on a failed step (the callers own the reporting).</summary>
        private static Color32[] MattePixels(Camera cam, int size, out float lit, out float partial)
        {
            lit = 0f; partial = 0f;
            Texture2D texB = null, texW = null;
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
                lit = (float)nLit / Mathf.Max(1, b.Length);
                partial = (float)nPartial / Mathf.Max(1, b.Length);
                return o;
            }
            finally { foreach (var t in new[] { texB, texW }) if (t != null) UnityEngine.Object.Destroy(t); }
        }

        /// <summary>First 6 bytes of the PNG's SHA-256 in hex (the upload
        /// signs the full digest, ApiClient.PcPortraitUpload).</summary>
        private static string Sha12(byte[] png)
        {
            if (png == null) return "-";
            using (var h = System.Security.Cryptography.SHA256.Create())
                return BitConverter.ToString(h.ComputeHash(png), 0, 6).Replace("-", "").ToLowerInvariant();
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

        /// <summary>Releases everything a run holds. Idempotent, and callable
        /// from anywhere (ForceAbort included). The synthetic cosmetic state of
        /// PORTRAIT_ACTOR is cleared on every call (both calls are no-ops when
        /// there is none), and every rig reference is dropped even when its
        /// object is already destroyed, so a reference Unity reports as
        /// destroyed never outlives the run (RigLost reads those
        /// references).</summary>
        private static void Teardown(StringBuilder rep)
        {
            try { PlayerColorCosmetic.RevertPlayer(PORTRAIT_ACTOR); } catch (Exception ex) { rep.Append("colour revert threw: ").Append(ex.Message).Append('\n'); }
            try { PlayerEffectCosmetic.ClearForPortrait(_clone != null ? _clone.transform : null, PORTRAIT_ACTOR); } catch (Exception ex) { rep.Append("effect clear threw: ").Append(ex.Message).Append('\n'); }
            try { foreach (var m in _madeMats) if (m != null) UnityEngine.Object.Destroy(m); } catch { }
            _madeMats.Clear();
            try { if (_camGO != null) { var c = _camGO.GetComponent<Camera>(); if (c != null) c.targetTexture = null; UnityEngine.Object.Destroy(_camGO); } } catch { }
            _camGO = null;
            try { if (_rt != null) { _rt.Release(); UnityEngine.Object.Destroy(_rt); } } catch { }
            _rt = null;
            try { if (_holdable != null) UnityEngine.Object.Destroy(_holdable); } catch { }
            _holdable = null;
            _hold = null;
            try { if (_ground != null) UnityEngine.Object.Destroy(_ground); } catch { }
            _ground = null;
            try { foreach (var u in _unparented) if (u != null) UnityEngine.Object.Destroy(u); } catch { }
            _unparented.Clear();
            try { if (_clone != null) UnityEngine.Object.Destroy(_clone); } catch { }
            _clone = null;
            try { if (_root != null) UnityEngine.Object.Destroy(_root); } catch { }
            _root = null;
            _legs.Clear(); _groundTop = float.NaN; _pinned.Clear(); _leftOut.Clear();
            try { StopLightProbe(); } catch { }
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
