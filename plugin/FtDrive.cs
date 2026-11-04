#if SCR_FRAMETIME
using System;
using System.Diagnostics;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>FrameTime part c (FORMAT-M-PLAN.md V2 section 4), the self-drive loop. It drives the local fighter
    /// through the game's own input object (a postfix on GeneralInput.Update that respects GameManager.lockInput,
    /// so menus and chat still block it): a seeded random walk with jumps, aim at the opponent with seeded jitter,
    /// fire in seeded bursts, block on a seeded schedule and when an opponent projectile is near (checked at most
    /// every 0.1 s). Card picks go through a prefix on CardChoice.DoPlayerSelect that acts only for the local
    /// picker: it highlights the seeded card and, after 2 s, picks it and clears pickrID as vanilla's confirm
    /// does [F04]. Lesson 221: the loop exists only in this configuration, draws a banner every frame while it
    /// drives, logs at arming and disarming, keeps its schedule on Stopwatch time (never the scaled Time.time),
    /// drives only while FtArm.Armed holds, disarms on Escape, and after game LAST_GAME disarms, leaves the room
    /// and logs "sitting complete". Its own cost runs in both arms (base load, not a component).</summary>
    internal static class FtDrive
    {
        internal const int LAST_GAME = 16;
        internal const string BANNER = "FRAME-TIME SELF-DRIVE: inputs are automated";

        internal static bool Escaped, Complete;
        private static bool _wasActive;
        private static int _lastFrame = -1;
        private static readonly Stopwatch _sw = Stopwatch.StartNew();
        private static System.Random _rng = new System.Random(0);
        private static int _rngGame = int.MinValue;
        private static double _nextMoveS, _nextJumpS, _burstEndS, _nextBurstS, _nextBlockS, _nextProjS;
        private static Vector3 _move;
        private static float _jitter;
        private static bool _projNear, _wasFiring;
        private static double _pickStartS = -1;
        private static GameObject _pickFirst;
        private static int _pickIndex;

        internal static bool Active => FtArm.Armed && !Escaped && !Complete && !FtRematch.TimedOut;

        private static double Now => _sw.Elapsed.TotalSeconds;

        private static System.Random Rng()
        {
            if (_rngGame != FtSchedule.Game)
            {
                _rngGame = FtSchedule.Game;
                _rng = new System.Random(unchecked(FtConfig.Seed * 7919 + FtSchedule.Game));
            }
            return _rng;
        }

        private static void Log(string what) { Plugin.Log.LogInfo("[FRAME-TIME] self-drive " + what); }

        /// <summary>Once per frame, from the first GeneralInput.Update postfix of the frame.</summary>
        internal static void FrameTick()
        {
            int f = Time.frameCount;
            if (f == _lastFrame) return;
            _lastFrame = f;
            if (!Escaped && FtArm.Armed && Input.GetKeyDown(KeyCode.Escape)) Escaped = true;
            bool a = Active;
            if (a != _wasActive)
                Log(a ? "armed: inputs are automated"
                      : "disarmed: " + (Escaped ? "escape" : Complete ? "sitting complete" : FtRematch.TimedOut ? "rematch timeout" : "input=" + FtArm.Why));
            _wasActive = a;
        }

        private static double _nextJoinS;

        /// <summary>The self-drive's first act: outside any room, stage this build's own ft_ room through the
        /// existing named-room join with FT_REGION (part b), at most every 30 s, never over a staged pending room.
        /// The sentinel key join=0 suppresses it (the menu self-check runs with no second seat).</summary>
        internal static void JoinTick()
        {
            if (!FtConfig.Present || Escaped || Complete || FtRematch.TimedOut || FtArm.Latched) return;   // F6: a latched disarm stops the joins
            double now = Now;
            if (now < _nextJoinS) return;
            _nextJoinS = now + 30.0;
            if (FtConfig.Menu || FtConfig.Get("join", "1") == "0") return;   // the menu self-check has no room
            try
            {
                if (Photon.Pun.PhotonNetwork.InRoom || Photon.Pun.PhotonNetwork.OfflineMode) return;
                if (!string.IsNullOrEmpty(Plugin.PendingRankedRoom)) return;
                string room = FtArm.ExpectedRoom();
                if (room == null) return;
                FtArm.StageOwnDll();   // F7: the own DLL marker rides the join (lesson 287)
                Plugin.Log.LogInfo("[FRAME-TIME] self-drive join room=" + room + " region=" + FtArm.FT_REGION);
                Plugin.SetPendingRoom(room, FtArm.FT_REGION);
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] self-drive join failed: " + ex.Message); }
        }

        private static int _spawnPa;
        private static int _spawnTries;
        private static double _spawnSince = -1, _nextSpawnS;
        private static string _spawnSaid = "";

        private static void SpawnSay(string what)
        {
            if (what == _spawnSaid) return;
            _spawnSaid = what;
            if (what.StartsWith("spawn gave up", StringComparison.Ordinal) || what.StartsWith("spawn refused", StringComparison.Ordinal))
                Plugin.Log.LogWarning("[FRAME-TIME] self-drive " + what);
            else Log(what);
        }

        /// <summary>The self-drive's second act (ruling R6-A3.7, DESIGN-R6A37-JOIN.md): in the armed room, create the
        /// local fighter through the same direct vanilla call the join press reaches (PlayerAssigner.CreatePlayer(null),
        /// the keyboard player; DanceStep0Probe.cs and the 2v2 auto-spawn make the same call), never synthetic input
        /// (lesson 420). It runs from FtSchedule.Boundary every frame because the GeneralInput postfix exists only once
        /// a body does. The moment, read live every frame: armed, in the room with both actors, the game mode awake
        /// (playersCanJoin, set by GM_ArmsRace.OnEnable), vanilla's own not-created and not-full refusals clear, the
        /// game not yet playing, all held 1.0 s on Stopwatch time. Once per seat by vanilla's hasCreatedLocalPlayer on
        /// this PlayerAssigner instance; a call that leaves it false is retried at most 5 times, 2 s apart, then the
        /// tick warns "spawn gave up" once. A rematch keeps the bodies (lesson 138), so the tick does nothing then.</summary>
        internal static void SpawnTick()
        {
            if (!FtArm.Armed || Escaped || Complete || FtRematch.TimedOut)
            {
                _spawnSince = -1;
                if (FtArm.Why == "peer") SpawnSay("spawn waiting why=peer");
                return;
            }
            try
            {
                var pa = PlayerAssigner.instance;
                if (pa == null) { _spawnSince = -1; SpawnSay("spawn waiting why=assigner actors=-1"); return; }
                int id = pa.GetInstanceID();
                if (id != _spawnPa) { _spawnPa = id; _spawnTries = 0; _spawnSince = -1; _spawnSaid = ""; }
                if (pa.hasCreatedLocalPlayer) return;
                var room = Photon.Pun.PhotonNetwork.CurrentRoom;
                int actors = Photon.Pun.PhotonNetwork.InRoom && room != null ? room.PlayerCount : -1;
                string why = actors != 2 ? "actors"
                    : !pa.playersCanJoin ? "join-closed"
                    : pa.players != null && pa.players.Count >= pa.maxPlayers ? "full"
                    : GameManager.instance == null ? "game-manager"
                    : GameManager.instance.isPlaying ? "playing"
                    : null;
                if (why != null) { _spawnSince = -1; SpawnSay("spawn waiting why=" + why + " actors=" + actors); return; }
                if (SpectatorSession.IsLocalSpectator) { SpawnSay("spawn refused why=spectator"); return; }
                double now = Now;
                if (_spawnSince < 0) _spawnSince = now;
                if (now - _spawnSince < 1.0 || now < _nextSpawnS) return;
                if (_spawnTries >= 5) { SpawnSay("spawn gave up tries=" + _spawnTries); return; }
                _spawnTries++;
                _nextSpawnS = now + 2.0;
                Log("spawn try=" + _spawnTries + " master=" + (Photon.Pun.PhotonNetwork.IsMasterClient ? 1 : 0) + " actors=" + actors);
                try { pa.CreatePlayer(null); }
                catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] self-drive spawn threw: " + ex.Message); }
                Log("spawn result created=" + (pa.hasCreatedLocalPlayer ? 1 : 0) + " players=" + (pa.players != null ? pa.players.Count : -1));
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] self-drive spawn tick failed: " + ex.Message); }
        }

        /// <summary>FtSchedule.GameOver: after the last measured game the sitting ends.</summary>
        internal static void GameOver(int game)
        {
            if (game < LAST_GAME || Complete) return;
            Complete = true;
            Plugin.Log.LogInfo("[FRAME-TIME] sitting complete g=" + game);
            try { NetworkConnectionHandler.instance?.NetworkRestart(); } catch { }
        }

        internal static void Banner()
        {
            if (!Active) return;
            var style = new GUIStyle(GUI.skin.label) { fontSize = 22, fontStyle = FontStyle.Bold };
            style.normal.textColor = Color.red;
            GUI.Label(new Rect(20, 8, 900, 40), BANNER, style);
        }

        internal static void Drive(GeneralInput gi, CharacterData data)
        {
            var r = Rng();
            double now = Now;
            if (now >= _nextMoveS)
            {
                _move = new Vector3((float)(r.NextDouble() * 2.0 - 1.0), 0f, 0f);
                _jitter = (float)(r.NextDouble() - 0.5) * 0.3f;
                _nextMoveS = now + 0.5 + r.NextDouble();
            }
            gi.direction = _move;
            bool jump = now >= _nextJumpS;
            if (jump) _nextJumpS = now + 0.8 + 1.5 * r.NextDouble();
            gi.jumpWasPressed = jump;
            gi.jumpIsPressed = jump;
            Player opp = Opponent(data);
            if (opp != null)
            {
                Vector3 d = opp.transform.position - data.transform.position;
                d.z = 0f;
                if (d.sqrMagnitude > 1e-6f)
                {
                    d.Normalize();
                    gi.aimDirection = (d + new Vector3(-d.y, d.x, 0f) * _jitter).normalized;
                }
            }
            bool firing = now < _burstEndS;
            if (!firing && now >= _nextBurstS)
            {
                _burstEndS = now + 0.3 + 0.7 * r.NextDouble();
                _nextBurstS = _burstEndS + 0.3 + 1.2 * r.NextDouble();
                firing = true;
                gi.shootWasPressed = true;
            }
            gi.shootIsPressed = firing;
            if (!firing && _wasFiring) gi.shootWasReleased = true;
            _wasFiring = firing;
            if (now >= _nextProjS) { _nextProjS = now + 0.1; _projNear = ProjectileNear(data); }
            if (now >= _nextBlockS || _projNear)
            {
                gi.shieldWasPressed = true;
                _nextBlockS = now + 2.0 + 3.0 * r.NextDouble();
                _projNear = false;
            }
        }

        private static Player Opponent(CharacterData data)
        {
            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null) return null;
            foreach (var p in pm.players)
                if (p != null && p.data != null && p.data != data && !p.data.dead) return p;
            return null;
        }

        private static bool ProjectileNear(CharacterData data)
        {
            Vector3 me = data.transform.position;
            foreach (var h in UnityEngine.Object.FindObjectsOfType<ProjectileHit>())
            {
                if (h == null || h.ownPlayer == null || h.ownPlayer == data.player) continue;
                Vector3 d = h.transform.position - me;
                d.z = 0f;
                if (d.sqrMagnitude < 36f) return true;
            }
            return false;
        }

        /// <summary>The local picker's pick: false skips vanilla's DoPlayerSelect for this frame.</summary>
        internal static bool Pick(CardChoice cc)
        {
            var pm = PlayerManager.instance;
            Player picker = pm != null && cc.pickrID >= 0 ? pm.GetPlayerWithID(cc.pickrID) : null;
            if (picker == null || picker.data == null || picker.data.view == null || !picker.data.view.IsMine) return true;
            var cards = cc.spawnedCards;
            if (cards == null || cards.Count == 0 || cards[0] == null) return true;
            if (_pickStartS < 0 || !ReferenceEquals(_pickFirst, cards[0]))
            {
                _pickFirst = cards[0];
                _pickStartS = Now;
                _pickIndex = Rng().Next(cards.Count);
            }
            if (_pickIndex >= cards.Count) _pickIndex = cards.Count - 1;
            cc.currentlySelectedCard = _pickIndex;
            if (Now - _pickStartS >= 2.0 && cards[_pickIndex] != null)
            {
                _pickStartS = -1;
                Plugin.Log.LogInfo("[FRAME-TIME] self-drive pick index=" + _pickIndex);
                cc.Pick(cards[_pickIndex]);
                cc.pickrID = -1;
            }
            return false;
        }
    }

    [HarmonyPatch(typeof(GeneralInput), "Update")]
    internal static class FtDrive_InputPatch
    {
        [HarmonyPostfix]
        private static void Postfix(GeneralInput __instance)
        {
            try
            {
                FtDrive.FrameTick();
                if (!FtDrive.Active || __instance == null || __instance.controlledElseWhere) return;
                if (GameManager.lockInput) return;
                var data = __instance.data;
                if (data == null || data.view == null || !data.view.IsMine || data.dead) return;
                FtDrive.Drive(__instance, data);
            }
            catch { }   // fail open: the seat keeps its own inputs
        }
    }

    [HarmonyPatch(typeof(CardChoice), "DoPlayerSelect")]
    internal static class FtDrive_PickPatch
    {
        [HarmonyPrefix]
        private static bool Prefix(CardChoice __instance, bool __runOriginal)
        {
            if (!__runOriginal) return false;   // a guard before this one (chat, a menu) owns the frame
            try { return !FtDrive.Active || FtDrive.Pick(__instance); }
            catch { return true; }
        }
    }
}
#endif
