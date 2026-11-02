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

        internal static bool Active => FtArm.Armed && !Escaped && !Complete;

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
                      : "disarmed: " + (Escaped ? "escape" : Complete ? "sitting complete" : "input=" + FtArm.Why));
            _wasActive = a;
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
