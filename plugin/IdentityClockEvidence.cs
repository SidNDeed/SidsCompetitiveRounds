using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using BepInEx;
using BepInEx.Bootstrap;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;
using C = CompetitiveRounds.SeatEvidenceCore;
using I = CompetitiveRounds.IdentityClockCore;

namespace CompetitiveRounds
{
    /// <summary>IDENTITY, CLOCK AND CONNECTION EVIDENCE, the game half (design
    /// IDENTITY-CLOCK-EVIDENCE-DESIGN-V1.md, its design report, the server
    /// lane's wire at 00608251). One record per seat per ranked 1v1 game,
    /// posted on the seat evidence queue as route "i" with the X-Seat-Clock
    /// header stamped at each send.
    ///
    /// Containment (design 9.1): every hook is a void prefix/postfix or a
    /// finalizer that returns the exception it was given; each collector runs
    /// inside its own try with a fault counter and a cost row; nothing here
    /// writes a field the game reads, creates or destroys a Unity object,
    /// starts a coroutine or uses the game's random generator.
    ///
    /// The disk survey (gdig, ldir, aload) runs ONLY on this tick and ONLY in a
    /// frame where no battle is live (SeatEvidence.CombatLive, read in the same
    /// frame): there is no worker thread, so no survey or hashing work can
    /// overlap combat; each tick does at most a bounded number of bounded
    /// units. The io_in_combat counter is the witness: every disk call
    /// re-reads the battle state itself and counts a call made while a battle
    /// is live (it must stay 0).</summary>
    internal static class IdentityClockEvidence
    {
        private const string TAG = "[IDENTITY-CLOCK]";
        private static readonly Stopwatch _sw = Stopwatch.StartNew();
        internal static long SwMs { get { return _sw.ElapsedMilliseconds; } }
        private static long SwUs { get { return _sw.ElapsedTicks * 1000000L / Stopwatch.Frequency; } }

        // collectors (design 9.2 rows; ids are the cost rows' ids)
        internal const int K1X = 0, K6X = 1, K7X = 2, N7 = 3, N8 = 4, T2 = 5, C1 = 6, C2 = 7, G1 = 8, BOOT = 9;
        private static readonly I.Cost[] _cost = NewCosts();
        private static I.Cost[] NewCosts()
        {
            var a = new I.Cost[10];
            for (int i = 0; i < a.Length; i++) a[i] = new I.Cost(i);
            return a;
        }

        private static I.ProcLedger _proc;
        private static I.Privacy _priv;
        internal static long IoInCombat;

        private static I.ProcLedger Proc
        {
            get
            {
                if (_proc == null)
                {
                    var b = new byte[6];
                    using (var rng = RandomNumberGenerator.Create()) rng.GetBytes(b);
                    _proc = new I.ProcLedger(I.ProcLedger.NewProcId(b));
                }
                return _proc;
            }
        }

        /// <summary>The local privacy needles (report L5): the account, machine
        /// and domain names and the profile folder's name. Read once; they
        /// only ever decide what is hashed, and never leave this process.</summary>
        private static I.Privacy Priv
        {
            get
            {
                if (_priv == null)
                {
                    var n = new List<string>();
                    try { n.Add(Environment.UserName); } catch { }
                    try { n.Add(Environment.MachineName); } catch { }
                    try { n.Add(Environment.UserDomainName); } catch { }
                    try { n.Add(Path.GetFileName(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile).TrimEnd('\\', '/'))); } catch { }
                    _priv = new I.Privacy(n);
                }
                return _priv;
            }
        }

        private static long ProcMs()
        {
            try { return (long)(Time.realtimeSinceStartup * 1000.0); } catch { return SwMs; }
        }

        // -- boot (moment 0; report L1) -------------------------------------------------------

        /// <summary>From DoInitialize, at EVERY execution of the other-plug-in
        /// gate (a persistent-host respawn runs it again in the same process):
        /// one boot occurrence with its ordinal and process time. Evidence
        /// only; the gate's own behaviour is unchanged.</summary>
        internal static void BootCheck(string outcome, IList<string> guids)
        {
            long t0 = SwUs;
            try
            {
                int o = outcome == "finding" ? I.FINDING : (outcome == "pass" ? I.PASS : I.NOT_RUN);
                Proc.Boot(ProcMs(), o, guids, Priv);
            }
            catch { _cost[BOOT].Fault(); }
            _cost[BOOT].Add(SwUs - t0);
        }

        // -- the game window ------------------------------------------------------------------

        private sealed class Game
        {
            internal bool Ranked, OneVOne;
            internal long Gen;
            internal I.ClockBook Book;
            internal I.GameRuns Runs = new I.GameRuns();
            internal I.RpcNames Rpc = new I.RpcNames();
            internal HashSet<string> AsmAtStart;
            internal int SendStart = -1, SerStart = -1, SerChanges;
            internal int OppActor;
        }

        private static Game _g;
        private static long _gen;
        private static bool _wasPicking, _wasPlaying, _anyDead, _haveOwn;
        private static long _lastTickUs;
        private static long _nextFpsReadMs;

        /// <summary>From GameStateWatcher, where the seat lane opens its window.</summary>
        internal static void BeginGame(bool oneVOne, bool ranked)
        {
            long t0 = SwUs;
            try
            {
                bool fromToken;
                int gt0 = GameStateWatcher.SeatEvidenceT0(out fromToken);
                _g = new Game { Ranked = ranked, OneVOne = oneVOne, Gen = ++_gen, Book = new I.ClockBook(gt0) };
                _wasPicking = false; _wasPlaying = false; _anyDead = false; _haveOwn = false;
                try { _g.SendStart = PhotonNetwork.SendRate; _g.SerStart = PhotonNetwork.SerializationRate; } catch { }
                try { PostBoot.ArmFromFile(); } catch { }
                CheckRun(I.MOMENT_START, true);
            }
            catch { _cost[K7X].Fault(); }
            _cost[K7X].Add(SwUs - t0);
        }

        // -- the census (moments 1-3; C1) -------------------------------------------------------

        private sealed class CensusOut
        {
            internal List<object> Asm, AsmN, Hp, HpAll;
            internal HashSet<string> Names;
        }
        private static CensusOut _lastCensus;

        /// <summary>The loader's live key set, read at every run, plus the
        /// after-boot fixture's keys (PostBoot).</summary>
        private static readonly I.KeySource Keys = new I.KeySource(() =>
        {
            var infos = Chainloader.PluginInfos;
            return infos == null ? null : new List<string>(infos.Keys);
        });

        /// <summary>One check run and census at a moment: plug-in keys, loaded
        /// assemblies, Harmony owners. Main thread, in-memory reads only.
        /// Evidence only: nothing in the game or the mod changes, whatever it
        /// finds. A run that throws is not_run.</summary>
        private static void CheckRun(int moment, bool atStart)
        {
            long t0 = SwUs;
            try
            {
                var g = _g;
                if (g == null) return;
                var run = new I.Run { Moment = moment, TMs = ProcMs() };
                if (moment == I.MOMENT_PICK) run.Ordinal = Math.Min(g.Runs.Picks++, I.ORDINAL_MAX);
                var others = new List<string>();
                bool threw;
                var keys = Keys.Read(out threw);
                run.Outcome = I.Outcome(keys, Plugin.ModId, threw, others);
                var c = new CensusOut();
                try
                {
                    var asms = ReadAssemblies();
                    I.Census(asms, atStart ? null : g.AsmAtStart, Priv, out c.Asm, out c.AsmN, out c.Names);
                    if (atStart) g.AsmAtStart = c.Names;
                    run.NAsm = asms.Count;
                    long nf;
                    I.Patches(ReadPatches(), Plugin.ModId, Priv, out c.Hp, out c.HpAll, out nf);
                    run.NForeign = nf;
                    _lastCensus = c;
                }
                catch { if (run.Outcome != I.FINDING) { run.Outcome = I.NOT_RUN; others.Clear(); } _cost[C1].Fault(); }
                Proc.Count(run, others, Priv);
                g.Runs.Add(run);
            }
            catch { _cost[C1].Fault(); }
            _cost[C1].Add(SwUs - t0);
        }

        private static List<I.AsmIn> ReadAssemblies()
        {
            string managed = "", core = "", plugins = "", patchers = "";
            try { managed = Paths.ManagedPath; core = Paths.BepInExAssemblyDirectory; plugins = Paths.PluginPath; patchers = Paths.PatcherPluginPath; } catch { }
            var l = new List<I.AsmIn>();
            foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
            {
                var e = new I.AsmIn();
                try { var n = a.GetName(); e.Name = n.Name; e.Version = n.Version != null ? n.Version.ToString() : ""; } catch { e.Name = ""; e.Version = ""; }
                bool dyn = false, unreadable = false; string loc = null;
                try { dyn = a.IsDynamic; } catch { }
                if (!dyn) { try { loc = a.Location; } catch { unreadable = true; } }
                e.Dynamic = dyn;
                e.Origin = I.Origin(dyn, unreadable, loc, managed, core, plugins, patchers);
                l.Add(e);
            }
            return l;
        }

        /// <summary>The public dependency list (method_id = index): every
        /// method the evidence lanes and gameplay repairs patch or rely on,
        /// matched by declaring type name and method name (any overload).</summary>
        internal static readonly string[] DEPENDENCY = {
            "PhotonNetwork.ExecuteRpc", "PhotonNetwork.RPC", "ProjectileHit.RPCA_DoHit", "ProjectileHit.Hit",
            "HealthHandler.RPCA_SendTakeDamage", "HealthHandler.RPCA_SendTakeForce", "HealthHandler.CallTakeDamage",
            "Block.RPCA_DoBlock", "Block.TryBlock", "Block.IsBlocking", "Gun.Attack", "GunAmmo.ReloadAmmo",
            "ProjectileInit.RPCA_Init", "ProjectileInit.RPCA_Init_noAmmoUse", "ProjectileInit.RPCA_Init_SeparateGun",
            "MoveTransform.Update", "SyncProjectile.OnPhotonSerializeView", "SyncPlayerMovement.OnPhotonSerializeView",
            "GeneralInput.Update", "PlayerVelocity.FixedUpdate", "TimeHandler.Update", "PhotonHandler.FixedUpdate",
            "PhotonHandler.LateUpdate", "MapManager.RPCA_CallInNewMapAndMovePlayers", "PlayerManager.MovePlayers",
            "ApplyCardStats.ApplyStats", "CharacterStatModifiers.DealtDamage", "GM_ArmsRace.StartGame" };

        private static List<I.PatchedIn> ReadPatches()
        {
            var l = new List<I.PatchedIn>();
            foreach (var m in Harmony.GetAllPatchedMethods())
            {
                if (m == null) continue;
                var p = new I.PatchedIn();
                string key = (m.DeclaringType != null ? m.DeclaringType.Name : "") + "." + m.Name;
                p.MethodId = Array.IndexOf(DEPENDENCY, key);
                var info = Harmony.GetPatchInfo(m);
                if (info != null)
                {
                    foreach (var x in info.Prefixes) p.Patches.Add(new KeyValuePair<int, string>(0, x.owner));
                    foreach (var x in info.Postfixes) p.Patches.Add(new KeyValuePair<int, string>(1, x.owner));
                    foreach (var x in info.Transpilers) p.Patches.Add(new KeyValuePair<int, string>(2, x.owner));
                    foreach (var x in info.Finalizers) p.Patches.Add(new KeyValuePair<int, string>(3, x.owner));
                }
                l.Add(p);
            }
            return l;
        }

        // -- post-boot seam (report L6) -----------------------------------------------------------

        /// <summary>The after-boot fixture: a test plug-in present at launch is
        /// found at boot and disables the mod by design, so later moments and
        /// foreign Harmony ownership are exercised after a clean boot instead.
        /// ADDITIVE ONLY: what it adds is reported like anything else the
        /// census finds; it can never remove or hide a key, an assembly or an
        /// owner. Armed at game start by the presence of the file
        /// BepInEx/config/scr-ic-postboot.txt (lines "plugin &lt;guid&gt;" and
        /// "harmony &lt;method_id&gt;"): a plug-in key is added to the key set
        /// the moment runs read, and a no-op postfix is applied to a listed
        /// method under the owner id "scr.ic.postboot".</summary>
        internal static class PostBoot
        {
            internal const string OWNER = "scr.ic.postboot";
            internal static readonly List<string> Plugins = new List<string>();
            private static bool _armed;

            internal static void ArmFromFile()
            {
                if (_armed) return;
                string path;
                try { path = Path.Combine(Paths.ConfigPath, "scr-ic-postboot.txt"); } catch { return; }
                if (!File.Exists(path)) return;
                _armed = true;
                string[] lines;
                try { lines = File.ReadAllLines(path); } catch { return; }
                int n = 0;
                foreach (var raw in lines)
                {
                    if (++n > 8) break;
                    var p = (raw ?? "").Trim().Split(' ');
                    if (p.Length != 2) continue;
                    if (p[0] == "plugin" && Plugins.Count < 4) { Plugins.Add(p[1]); Keys.PostBoot.Add(p[1]); }
                    else if (p[0] == "harmony")
                    {
                        int id;
                        if (int.TryParse(p[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out id) && id >= 0 && id < DEPENDENCY.Length)
                            PatchListed(DEPENDENCY[id]);
                    }
                }
                try { Plugin.Log.LogInfo(TAG + " post-boot fixture armed: " + Plugins.Count + " key(s)"); } catch { }
            }

            private static void PatchListed(string key)
            {
                try
                {
                    int dot = key.IndexOf('.');
                    var t = AccessTools.TypeByName(key.Substring(0, dot));
                    if (t == null) return;
                    MethodBase target = null;
                    foreach (var m in AccessTools.GetDeclaredMethods(t)) if (m.Name == key.Substring(dot + 1)) { target = m; break; }
                    if (target == null) return;
                    new Harmony(OWNER).Patch(target, postfix: new HarmonyMethod(typeof(PostBoot), nameof(Noop)));
                }
                catch { }
            }

            private static void Noop() { }
        }

        // -- K1x: the RPC frame (own stack; the other seat's names; shots) -------------------

        private struct Frame { internal int Stamp, Sender; internal bool HasStamp; internal string Method; }
        private const int FRAME_CAP = 16;
        private static readonly Frame[] _frames = new Frame[FRAME_CAP];
        private static int _depth;
        private static readonly object K2 = (byte)2, K3 = (byte)3, K5 = (byte)5;

        internal static int EnterRpc(ExitGames.Client.Photon.Hashtable data, Photon.Realtime.Player sender)
        {
            int before = _depth;
            long t0 = SwUs;
            try
            {
                var f = new Frame();
                if (data != null)
                {
                    object o = data[K2]; f.HasStamp = o is int; f.Stamp = f.HasStamp ? (int)o : 0;
                    o = data[K5];
                    if (o is byte)
                    {
                        int i = (byte)o;
                        var list = PhotonNetwork.PhotonServerSettings != null ? PhotonNetwork.PhotonServerSettings.RpcList : null;
                        f.Method = list != null && i < list.Count ? list[i] : null;
                    }
                    else f.Method = data[K3] as string;
                }
                f.Sender = sender != null ? sender.ActorNumber : 0;
                if (before >= 0 && before < FRAME_CAP) _frames[before] = f;
                _depth = before + 1;
                var g = _g;
                if (g != null && f.Sender != 0)
                {
                    int local = PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : 0;
                    if (f.Sender != local)
                    {
                        if (g.OppActor == 0) g.OppActor = f.Sender;
                        if (f.Sender == g.OppActor)
                        {
                            g.Rpc.Add(f.Method);
                            if (f.Method == "RPCA_Init" && f.HasStamp) g.Book.OtherShot(f.Stamp, PhotonNetwork.ServerTimestamp);
                        }
                    }
                    else if (f.Method == "RPCA_Init" && g.Book.CurS != null) g.Book.CurS.OwnShot(SwMs);
                }
            }
            catch { _cost[K1X].Fault(); }
            _cost[K1X].Add(SwUs - t0);
            return before;
        }

        internal static void ExitRpc(int before) { if (before >= 0) _depth = before; }

        // -- N7, N8: point start and spawn targets --------------------------------------------

        internal static void PointStart()
        {
            long t0 = SwUs;
            try
            {
                var g = _g;
                if (g != null)
                {
                    int top = _depth - 1;
                    bool has = false; int stamp = 0;
                    if (top >= 0 && top < FRAME_CAP && _frames[top].Method == "RPCA_CallInNewMapAndMovePlayers")
                    { has = _frames[top].HasStamp; stamp = _frames[top].Stamp; }
                    g.Book.PointStart(has, stamp, PhotonNetwork.ServerTimestamp, SwMs);
                    _anyDead = false;
                }
            }
            catch { _cost[N7].Fault(); }
            _cost[N7].Add(SwUs - t0);
        }

        internal static void MovePlayers(SpawnPoint[] points)
        {
            long t0 = SwUs;
            try
            {
                var g = _g; var pm = PlayerManager.instance;
                if (g != null && pm != null && points != null)
                    for (int i = 0; i < pm.players.Count && i < points.Length; i++)
                    {
                        var p = pm.players[i];
                        if (p == null || p.data == null || p.data.view == null || p.data.view.IsMine) continue;
                        var v = points[i].localStartPos;
                        g.Book.Target((int)Math.Round(v.x * 100f), (int)Math.Round(v.y * 100f));
                        break;
                    }
            }
            catch { _cost[N8].Fault(); }
            _cost[N8].Add(SwUs - t0);
        }

        // -- K6x: the other seat's player stream ------------------------------------------------

        internal static void Package(SyncPlayerMovement spm, int stamp)
        {
            long t0 = SwUs;
            try
            {
                var g = _g;
                if (g != null && spm != null)
                {
                    var view = spm.photonView;
                    var list = spm.syncPackages;
                    if (view != null && !view.IsMine && list != null && list.Count > 0)
                    {
                        var k = list[list.Count - 1];
                        var p = new I.Pkg
                        {
                            Stamp = stamp, ArrServer = PhotonNetwork.ServerTimestamp, ArrSw = SwMs,
                            Px = Cu(k.pos.x), Py = Cu(k.pos.y), Vx = Cu(k.vel.x), Vy = Cu(k.vel.y),
                            Dx = E6(k.dir.x), Dy = E6(k.dir.y), Ax = E6(k.aim.x), Ay = E6(k.aim.y),
                            Jump = k.jump, HoldJump = k.holdJump, TdMs = (int)Math.Round(k.timeDelta * 1000f),
                        };
                        g.Book.Package(p);
                    }
                }
            }
            catch { _cost[K6X].Fault(); }
            _cost[K6X].Add(SwUs - t0);
        }

        private static int Cu(float v) { return (int)I.Clamp((long)Math.Round(v * 100.0), -I.CU_MAX, I.CU_MAX); }
        private static int E6(float v) { return (int)I.Clamp((long)Math.Round(v * 1000000.0), -1000000, 1000000); }

        // -- the tick (T2, the survey, the build) ---------------------------------------------

        private static I.Survey _survey;
        private static IList<I.FileTarget> _files;

        /// <summary>From Plugin's polling tick, every frame.</summary>
        internal static void Tick()
        {
            long now = SwUs;
            long frameUs = _lastTickUs > 0 ? now - _lastTickUs : 0;
            _lastTickUs = now;
            bool combat = SeatEvidence.CombatLive();
            long t0 = SwUs;
            try { Slice(frameUs, combat); } catch { _cost[T2].Fault(); }
            _cost[T2].Add(SwUs - t0);
            if (combat) { if (_survey != null) _survey.Step(true, 0, () => SwUs); return; }
            long t1 = SwUs;
            try
            {
                if (_survey != null && _survey.Running)
                {
                    _survey.Step(false, SURVEY_STEP_US, () => SwUs);
                    _cost[C2].Add(SwUs - t1);
                }
            }
            catch { _cost[C2].Fault(); }
            try { BuildCaptures(); } catch { }
        }

        /// <summary>The survey's per-tick time budget (a cost bound).</summary>
        internal const long SURVEY_STEP_US = 2000;

        private static void Slice(long frameUs, bool combat)
        {
            var g = _g;
            if (g == null) return;
            // moment 2: rising edge of the pick (outside combat by the game's own sequence)
            bool picking = false;
            try { picking = CardChoice.instance != null && CardChoice.instance.IsPicking; } catch { }
            if (picking && !_wasPicking && !combat) { CheckRun(I.MOMENT_PICK, false); RequestSurvey(g); }
            _wasPicking = picking;
            try
            {
                int ser = PhotonNetwork.SerializationRate;
                if (g.SerStart >= 0 && ser != g.SerStart && g.SerChanges < I.SMALL_MAX && ser != _lastSer) g.SerChanges++;
                _lastSer = ser;
            }
            catch { }
            // own body: isPlaying edges, input, deaths, game time
            var pm = PlayerManager.instance;
            Player own = null; bool anyDead = false;
            if (pm != null)
                foreach (var p in pm.players)
                {
                    if (p == null || p.data == null) continue;
                    if (p.data.dead) anyDead = true;
                    if (p.data.view != null && p.data.view.IsMine) own = p;
                }
            var s = g.Book.CurS;
            if (own != null && s != null)
            {
                bool playing = own.data.isPlaying;
                if (_haveOwn && _wasPlaying && !playing) s.MoveStart(SwMs, CurveMs(pm));
                if (!playing) s.MoveFrame(frameUs);
                if (_haveOwn && !_wasPlaying && playing) s.Release(SwMs);
                if (playing) { s.GameTime(TimeHandler.deltaTime * 1000.0); if (own.data.input != null && own.data.input.direction != Vector3.zero) s.OwnInput(SwMs); }
                _wasPlaying = playing; _haveOwn = true;
            }
            if (anyDead && !_anyDead && g.Book.CurO != null) g.Book.EndOfPointSeen(SwMs);
            _anyDead = anyDead;
            // the other seat's published frame rate (cr_gstats field 7), outside combat
            if (!combat && SwMs >= _nextFpsReadMs) { _nextFpsReadMs = SwMs + 1000; ReadPubFps(g); }
        }

        private static int _lastSer = -1;

        private static int CurveMs(PlayerManager pm)
        {
            try
            {
                var keys = pm.playerMoveCurve.keys;
                return keys.Length > 0 ? (int)Math.Round(keys[keys.Length - 1].time * 1000.0) : -1;
            }
            catch { return -1; }
        }

        private static void ReadPubFps(Game g)
        {
            try
            {
                if (!PhotonNetwork.InRoom || g.OppActor == 0) return;
                var p = PhotonNetwork.CurrentRoom.GetPlayer(g.OppActor);
                if (p == null || !p.CustomProperties.ContainsKey("cr_gstats")) return;
                var parts = (p.CustomProperties["cr_gstats"] as string ?? "").Split('|');
                int v = 0;
                bool ok = parts.Length >= 11 && int.TryParse(parts[6], NumberStyles.Integer, CultureInfo.InvariantCulture, out v);
                g.Book.LastPubFps = I.PubFps(true, ok ? v : 0);
            }
            catch { }
        }

        private static void RequestSurvey(Game g)
        {
            try
            {
                if (_survey == null)
                {
                    string game = "", root = "";
                    try { game = Paths.ManagedPath; root = Paths.GameRootPath; } catch { }
                    _files = FileList(game, root);
                    string gameAsm = "";
                    try { gameAsm = typeof(GameManager).Assembly.Location; } catch { }
                    _survey = new I.Survey(new DiskFs(), _files, SafePath(() => Paths.PluginPath), SafePath(() => Paths.PatcherPluginPath), gameAsm);
                }
                _survey.Request(g.Gen);
            }
            catch { _cost[C2].Fault(); }
        }

        private static string SafePath(Func<string> f) { try { return f(); } catch { return ""; } }

        /// <summary>The public file list of gdig (file_id = index).</summary>
        internal static readonly string[] GAME_FILES = {
            "Assembly-CSharp.dll", "Assembly-CSharp-firstpass.dll", "Photon3Unity3D.dll", "PhotonRealtime.dll",
            "PhotonUnityNetworking.dll", "PhotonUnityNetworking.Utilities.dll", "UnityEngine.CoreModule.dll",
            "UnityEngine.Physics2DModule.dll" };
        internal static readonly string[] LOADER_FILES = {
            "BepInEx.dll", "BepInEx.Preloader.dll", "0Harmony.dll", "BepInEx.Harmony.dll", "HarmonyXInterop.dll",
            "MonoMod.RuntimeDetour.dll", "MonoMod.Utils.dll", "Mono.Cecil.dll" };
        internal const string DOORSTOP_FILE = "winhttp.dll";

        private static IList<I.FileTarget> FileList(string managed, string root)
        {
            var l = new List<I.FileTarget>();
            int id = 0;
            string core = SafePath(() => Paths.BepInExAssemblyDirectory);
            foreach (var f in GAME_FILES) l.Add(new I.FileTarget { Id = id++, Path = string.IsNullOrEmpty(managed) ? "" : Path.Combine(managed, f) });
            foreach (var f in LOADER_FILES) l.Add(new I.FileTarget { Id = id++, Path = string.IsNullOrEmpty(core) ? "" : Path.Combine(core, f) });
            l.Add(new I.FileTarget { Id = id++, Path = string.IsNullOrEmpty(root) ? "" : Path.Combine(root, DOORSTOP_FILE) });
            return l;
        }

        /// <summary>The survey's disk: each call re-reads the battle state and
        /// counts a call made during a live battle (the witness; it must stay 0).</summary>
        private sealed class DiskFs : I.IFs
        {
            private static void Witness() { try { if (SeatEvidence.CombatLive()) IoInCombat++; } catch { } }

            public int List(string dir, int max, List<I.FsEntry> into)
            {
                Witness();
                try
                {
                    var d = new DirectoryInfo(dir);
                    if (!d.Exists) return 1;
                    foreach (var e in d.EnumerateFileSystemInfos())
                    {
                        if (into.Count > max) break;
                        var a = e.Attributes;
                        into.Add(new I.FsEntry { Path = e.FullName, IsDir = (a & FileAttributes.Directory) != 0, IsReparse = (a & FileAttributes.ReparsePoint) != 0 });
                    }
                    return 0;
                }
                catch { return 2; }
            }

            public Stream Open(string path, out bool missing)
            {
                Witness();
                missing = false;
                try
                {
                    if (string.IsNullOrEmpty(path) || !File.Exists(path)) { missing = true; return null; }
                    if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) return null;
                    return new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 4096);
                }
                catch { return null; }
            }

            public string AsmName(string path)
            {
                Witness();
                try { return AssemblyName.GetAssemblyName(path).Name; } catch { return null; }
            }
        }

        // -- dispatch and build (G1) ----------------------------------------------------------------

        private sealed class Capture
        {
            internal Game G; internal string Seat, Other, Attach; internal int T0; internal bool FromToken;
            internal int SendEnd = -1, SerEnd = -1;
            internal bool CensusDone;
        }
        private static readonly List<Capture> _captures = new List<Capture>();
        private const int CAPTURE_CAP = 4;

        /// <summary>From GameStateWatcher beside the seat lane's Dispatch (game
        /// over, a cut game): O(1) capture; the census at moment 3, the build,
        /// the budget, the signature and the queue are the tick's, outside combat.</summary>
        internal static void Dispatch(string seat, string other, string attach, bool rankedNow)
        {
            long t0 = SwUs;
            try
            {
                var g = _g;
                _g = null;
                if (g == null || !rankedNow || !g.OneVOne) return;
                g.Book.ClosePoint(SwMs);
                bool fromToken;
                int gt0 = GameStateWatcher.SeatEvidenceT0(out fromToken);
                var c = new Capture { G = g, Seat = seat, Other = other, Attach = attach, T0 = gt0, FromToken = fromToken };
                try { c.SendEnd = PhotonNetwork.SendRate; c.SerEnd = PhotonNetwork.SerializationRate; } catch { }
                if (_captures.Count >= CAPTURE_CAP) _captures.RemoveAt(0);
                _captures.Add(c);
            }
            catch { _cost[G1].Fault(); }
            _cost[G1].Add(SwUs - t0);
        }

        private static long _nextBuildTryMs;

        private static void BuildCaptures()
        {
            if (_captures.Count == 0 || SwMs < _nextBuildTryMs) return;
            var c = _captures[0];
            long t0 = SwUs;
            try
            {
                if (!c.CensusDone)
                {
                    c.CensusDone = true;
                    var keep = _g; _g = c.G;
                    try { CheckRun(I.MOMENT_OVER, false); RequestSurvey(c.G); } finally { _g = keep; }
                    _nextBuildTryMs = SwMs + 1000;     // the census is this tick's work; the build is the next
                    return;
                }
                string stable = SeatEvidence.StableOf(c.Attach);
                if (stable == null || !C.IsSteamId(c.Seat) || !C.IsSteamId(c.Other)) { _captures.RemoveAt(0); return; }
                var g = c.G;
                var census = _lastCensus ?? new CensusOut { Asm = new List<object>(), AsmN = I.L(0L, 0L, 0L, 0L), Hp = new List<object>(), HpAll = I.L(0L, 0L, new List<object>()) };
                List<object> gdig; C.JObj ldir; int diskState; string mvidDisk;
                I.SurveyFields(_survey != null ? _survey.ResultFor(g.Gen) : null, _files ?? FileList("", ""), Priv, out gdig, out ldir, out diskState, out mvidDisk);
                string mvidLoaded = ""; int loadedOrigin = I.ORIGIN_UNREADABLE;
                try
                {
                    var asm = typeof(GameManager).Assembly;
                    mvidLoaded = asm.ManifestModule.ModuleVersionId.ToString("N");
                    string managed = SafePath(() => Paths.ManagedPath);
                    loadedOrigin = I.Origin(asm.IsDynamic, false, asm.IsDynamic ? null : asm.Location, managed,
                        SafePath(() => Paths.BepInExAssemblyDirectory), SafePath(() => Paths.PluginPath), SafePath(() => Paths.PatcherPluginPath));
                }
                catch { }
                var aload = I.L((long)loadedOrigin, mvidLoaded, (long)diskState, mvidDisk);
                var send = I.L(I.Clamp(g.SendStart, 0, I.RATE_MAX), I.Clamp(g.SerStart, 0, I.RATE_MAX), I.Clamp(c.SendEnd, 0, I.RATE_MAX),
                               I.Clamp(c.SerEnd, 0, I.RATE_MAX), I.Clamp(g.SerChanges, 0, I.SMALL_MAX));
                var rec = I.Record(c.T0, c.FromToken, _cost, Proc, g.Runs, census.AsmN, census.Asm, gdig, aload, ldir,
                                   census.HpAll, census.Hp, g.Rpc.Entries(Priv), g.Rpc.Overflow, send, g.Book);
                string text = I.Budget(rec);
                string sig = ApiClient.SeatEvidenceSig(I.Canonical(c.Seat, c.Other, stable, c.Attach, text));
                string env = I.Envelope(c.Seat, c.Other, stable, c.Attach, text, sig);
                if (env == null) { _captures.RemoveAt(0); Plugin.Log.LogWarning(TAG + " no record: the envelope is outside the contract"); return; }
                if (!SeatEvidence.EnqueueIdentity(env)) { _nextBuildTryMs = SwMs + 5000; return; }
                _captures.RemoveAt(0);
                Plugin.Log.LogInfo(TAG + " record queued: " + text.Length.ToString(CultureInfo.InvariantCulture) + " bytes, points "
                    + g.Book.PtO.Count + ", survey " + (_survey != null && _survey.ResultFor(g.Gen) != null ? "complete" : "not_yet")
                    + ", io_in_combat " + IoInCombat.ToString(CultureInfo.InvariantCulture));
            }
            catch (Exception ex)
            {
                _cost[G1].Fault();
                _captures.RemoveAt(0);
                try { Plugin.Log.LogWarning(TAG + " no record: " + ex.GetType().Name); } catch { }
            }
            _cost[G1].Add(SwUs - t0);
        }

        /// <summary>X-Seat-Clock for this send (ApiClient calls it immediately
        /// before SendWebRequest on route "i").</summary>
        internal static string ClockHeaderNow()
        {
            try
            {
                return I.ClockHeader(Proc.ProcId, SwMs, (long)(Time.unscaledTime * 1000.0), PhotonNetwork.ServerTimestamp);
            }
            catch { return null; }
        }

        /// <summary>One boot line naming the patches attached (bar 1).</summary>
        internal static void BootLine()
        {
            try
            {
                var names = new List<string>();
                foreach (var t in new[] { typeof(IdentityClock_ExecuteRpcPatch), typeof(IdentityClock_PointStartPatch),
                                          typeof(IdentityClock_MovePlayersPatch), typeof(IdentityClock_MovementPatch) })
                    names.Add(t.Name);
                Plugin.Log.LogInfo(TAG + " patches declared: " + string.Join(", ", names.ToArray()));
            }
            catch { }
        }
    }

    /// <summary>K1x: the RPC frame (own stack, nesting-safe) for the point
    /// start's stamp, the other seat's RPC names and the first shots.</summary>
    [HarmonyPatch]
    internal static class IdentityClock_ExecuteRpcPatch
    {
        private static MethodBase TargetMethod()
        {
            var m = AccessTools.Method(typeof(PhotonNetwork), "ExecuteRpc",
                new[] { typeof(ExitGames.Client.Photon.Hashtable), typeof(Photon.Realtime.Player) });
            if (m == null) throw new Exception("PhotonNetwork.ExecuteRpc(Hashtable, Player) not found");
            return m;
        }

        [HarmonyPrefix]
        private static void Prefix(ExitGames.Client.Photon.Hashtable __0, Photon.Realtime.Player __1, out int __state)
        {
            __state = -1;
            try { __state = IdentityClockEvidence.EnterRpc(__0, __1); } catch { }
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(int __state, Exception __exception)
        {
            try { IdentityClockEvidence.ExitRpc(__state); } catch { }
            return __exception;
        }
    }

    /// <summary>N7: the point start executes here.</summary>
    [HarmonyPatch(typeof(MapManager), "RPCA_CallInNewMapAndMovePlayers")]
    internal static class IdentityClock_PointStartPatch
    {
        [HarmonyPrefix]
        private static void Prefix()
        {
            try { IdentityClockEvidence.PointStart(); } catch { }
        }
    }

    /// <summary>N8: the spawn targets of this point's move.</summary>
    [HarmonyPatch(typeof(PlayerManager), "MovePlayers")]
    internal static class IdentityClock_MovePlayersPatch
    {
        [HarmonyPrefix]
        private static void Prefix(SpawnPoint[] __0)
        {
            try { IdentityClockEvidence.MovePlayers(__0); } catch { }
        }
    }

    /// <summary>K6x: the other seat's player stream (read branch only).</summary>
    [HarmonyPatch(typeof(SyncPlayerMovement), "OnPhotonSerializeView")]
    internal static class IdentityClock_MovementPatch
    {
        [HarmonyPrefix]
        private static void Prefix(SyncPlayerMovement __instance, PhotonStream __0, out int __state)
        {
            __state = -1;
            try
            {
                if (__0 == null || !__0.IsReading) return;
                var list = __instance.syncPackages;
                __state = list != null ? list.Count : -1;
            }
            catch { __state = -1; }
        }

        [HarmonyPostfix]
        private static void Postfix(SyncPlayerMovement __instance, PhotonMessageInfo __1, int __state)
        {
            if (__state < 0) return;
            try
            {
                var list = __instance.syncPackages;
                if (list == null || list.Count <= __state) return;
                IdentityClockEvidence.Package(__instance, __1.SentServerTimestamp);
            }
            catch { }
        }
    }
}
