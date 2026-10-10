using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Photon.Pun;
using UnityEngine;
using RPlayer = Photon.Realtime.Player;

namespace CompetitiveRounds
{
    /// <summary>Item 19 fix pass 2: the PRODUCTION probe. It compiles the
    /// unedited plugin/AvatarDefaults.cs and plugin/AvatarDefaultRules.cs of
    /// a tree against Stubs.cs and drives the real evaluator through its own
    /// entry points (AvatarDefaults.Evaluate, AvatarDefaults.Tick), reading
    /// the outcome at the sinks a player would see: the selection write, the
    /// remembered config int, the log line, the toast, the ring sprite.
    ///
    /// It binds what the rules-only controls could not (Codex BUILD round 2):
    /// H6, each production liveness assignment (ReadLiveness); H9 and M3, the
    /// confirmed exit with missing character data and the deferred edge;
    /// BR-M4, the staged room read (ReadFacing); M8, both arms of the
    /// classification-line guard; L1, the sprite sink and the announcement
    /// sink. Each line is "PROBE id PASS|FAIL | detail". It uses only entry
    /// points both the round 2 tree and the fix tip have, so the same probe
    /// runs against either. Exit 0 always: the verdicts are the output.</summary>
    internal static class ProdProbe
    {
        internal static readonly string[] Ids =
            { "H6a", "H6b", "H6c", "H9c", "H9s", "M3t", "BRM4", "M8apply", "M8room", "L1sprite", "L1announce" };

        internal static void SelectFacePostfix(int faceID)
        {
            var m = typeof(AvatarSelectFacePatch).GetMethod("Postfix", BindingFlags.NonPublic | BindingFlags.Static);
            m.Invoke(null, new object[] { faceID });
        }

        private static PlayerFace F(int e, int m, int d, int d2) => new PlayerFace { eyeID = e, mouthID = m, detailID = d, detail2ID = d2 };

        private static PlayerFace[] Faces()
        {
            var faces = new PlayerFace[10];
            faces[0] = F(0, 0, 0, 0);                    // never authored
            for (int i = 1; i < 10; i++) faces[i] = F(i, i, i, i);
            faces[5] = F(1001, 5, 5, 5);                 // a custom eye: not vanilla-clean
            return faces;
        }

        private static CharacterCreatorHandler Cch => CharacterCreatorHandler.instance;
        private static int LiveSel => Cch.selectedFaceID[0];
        private static int Home => Plugin.AvatarHomeSlot.Value;
        private static bool Logged(string needle) => Plugin.Log.Lines.Any(l => l.Contains(needle));

        /// <summary>The menu, no room, nobody playing; live selection `live`;
        /// both defaults named (modded 2, vanilla 1), automatic switching on.</summary>
        private static void Reset(int live)
        {
            World.All.Clear();
            Time.frameCount = 1;
            GameManager.instance = new GameManager();
            PhotonNetwork.InRoomFn = () => false;
            PhotonNetwork.OfflineFn = () => false;
            PhotonNetwork.CurrentRoom = null;
            RoomActors.LocalIsSpectator = false;
            RoomActors.Fighters = () => new List<RPlayer>();
            CompetitiveRoomDetect.Issued = false;
            Plugin.Log.Lines.Clear();
            CompetitiveUI.Shown.Clear();
            UIFactory.Sprites.Clear();
            Plugin.AvatarAutoSwitch.Value = true;
            Plugin.AvatarModdedPreset.Value = 2;
            Plugin.AvatarVanillaPreset.Value = 1;
            Plugin.AvatarHomeSlot.Value = -1;
            var faces = Faces();
            var cch = new CharacterCreatorHandler { playerFaces = faces };
            cch.selectedFaceID[0] = live;
            cch.selectedPlayerFaces[0] = faces[live];
            CharacterCreatorHandler.instance = cch;
            var items = Enumerable.Range(0, 20).Select(_ => new CharacterItem()).ToArray();
            CharacterCreatorItemLoader.instance = new CharacterCreatorItemLoader { eyes = items, mouths = items, accessories = items };
            PlayerManager.instance = new PlayerManager();
        }

        private static RPlayer Actor(bool local, bool modded)
        {
            var h = new Hashtable();
            if (local) h["cr_face"] = "x";
            else if (modded) h["cr_trail_sku"] = "t";
            else h["pid"] = 1;
            return new RPlayer { IsLocal = local, CustomProperties = h };
        }

        /// <summary>An online room: this seat plus one other fighter per flag
        /// (true = carries the mod's signature).</summary>
        private static void Room(params bool[] othersModded)
        {
            PhotonNetwork.InRoomFn = () => true;
            PhotonNetwork.CurrentRoom = new Photon.Realtime.Room();
            var list = new List<RPlayer> { Actor(true, true) };
            foreach (var m in othersModded) list.Add(Actor(false, m));
            RoomActors.Fighters = () => list;
        }

        private static void Leave()
        {
            PhotonNetwork.InRoomFn = () => false;
            PhotonNetwork.CurrentRoom = null;
            RoomActors.Fighters = () => new List<RPlayer>();
        }

        private static void Line(string id, bool ok, string detail)
        {
            Console.WriteLine("PROBE " + id + " " + (ok ? "PASS" : "FAIL") + " | " + detail);
        }

        private static void Case(string id, Func<string> body, Func<bool> verdict)
        {
            try
            {
                string detail = body();
                Line(id, verdict(), detail);
            }
            catch (Exception ex) { Line(id, false, "THREW " + ex.GetType().Name + ": " + ex.Message); }
        }

        // ---- H6: each production liveness assignment gates on its own ------

        private static bool ok6;

        private static string Liveness(Action makeLive, Action makeDead, string what)
        {
            Reset(3);
            Room(false);                                       // a vanilla room: f names slot 1
            makeLive();
            AvatarDefaults.Evaluate("E4-props");
            int during = LiveSel;
            makeDead();
            AvatarDefaults.Evaluate("E4-props");
            ok6 = during == 3 && LiveSel == 1;
            return what + ": live " + during + " during the game (must stay 3) | after it: live " + LiveSel + " (the same edge moves it to 1)";
        }

        // ---- H9 and M3: a confirmed exit with the character data missing --

        private static bool ok9;

        private static string MissingData(Action drop, Action restore, string what)
        {
            Reset(3);
            Room(false);
            AvatarDefaults.Evaluate("E2-joined");              // 3 -> 1, home 3
            int forced = LiveSel, held = Home;
            Leave();
            GameManager.instance.isPlaying = true;             // the old manager still reports a game
            drop();
            AvatarDefaults.Evaluate("E6-left");
            AvatarDefaults.Evaluate("E7-disconnect");          // a repeated confirmed-exit edge
            int kept = Home;
            bool deferredLine = Logged("E6-left restoration deferred");
            restore();
            int selectsBefore = Cch.SelectCalls;
            Time.frameCount = 30;
            AvatarDefaults.Tick();                             // the throttled tick: no room edge, no LoadFaces
            int liveAfter = LiveSel, homeAfter = Home, applied = Cch.SelectCalls - selectsBefore;
            Time.frameCount = 45;
            AvatarDefaults.Tick();
            int again = Cch.SelectCalls - selectsBefore - applied;
            ok9 = forced == 1 && held == 3 && kept == 3 && deferredLine && liveAfter == 3 && homeAfter == -1 && applied == 1 && again == 0;
            return what + ": forced live=" + forced + " home=" + held + " | exit x2 with the data missing: home " + kept
                + ", deferred line=" + deferredLine + " | the tick with the data back: live " + liveAfter + " home " + homeAfter
                + " selections " + applied + (liveAfter == 3 ? "" : " (the remembered selection is never given back)")
                + " | a second tick: selections " + again;
        }

        // ---- L1: the ring sprite sink -------------------------------------

        private static readonly Color Gold = new Color(1f, 0.851f, 0.302f), Blue = new Color(0.498f, 0.831f, 1f), Red = new Color(1f, 0.42f, 0.42f);

        private static bool Near(Color a, Color b) =>
            Math.Abs(a.r - b.r) < 0.01f && Math.Abs(a.g - b.g) < 0.01f && Math.Abs(a.b - b.b) < 0.01f && Math.Abs(a.a - b.a) < 0.01f;

        private static bool Bands(Sprite s, Color outer, Color inner)
        {
            if (s == null || s.texture == null) return false;
            var t = s.texture;
            return Near(t.GetPixel(1, 1), outer) && Near(t.GetPixel(4, 4), inner) && t.GetPixel(32, 32).a == 0f;
        }

        private static List<CharacterCreatorPortrait> Grid(int n)
        {
            var host = new GameObject("CharacterMenu");
            var grid = new GameObject("Grid");
            grid.transform.parent = host.transform;
            var list = new List<CharacterCreatorPortrait>();
            var faces = Cch.playerFaces;
            for (int i = 0; i < n; i++)
            {
                var go = new GameObject("Portrait" + i);
                go.transform.parent = grid.transform;
                var p = (CharacterCreatorPortrait)go.AddComponent(typeof(CharacterCreatorPortrait));
                p.playerId = -1;
                p.myFace = faces[i];
                list.Add(p);
            }
            return list;
        }

        private static Sprite SpriteOn(CharacterCreatorPortrait p)
        {
            Sprite s = null;
            foreach (var kv in UIFactory.Sprites)
                if (kv.Key != null && kv.Key.transform.parent == p.transform) s = kv.Value;
            return s;
        }

        private static bool okL1;

        private static string Rings()
        {
            Reset(3);
            var ps = Grid(6);
            Plugin.AvatarModdedPreset.Value = 1;
            Plugin.AvatarVanillaPreset.Value = 1;              // both defaults on one preset
            Time.frameCount = 15;
            AvatarDefaults.Tick();
            bool both = Bands(SpriteOn(ps[1]), Gold, Blue);
            int first = UIFactory.Sprites.Count;
            UIFactory.Sprites.Clear();
            Plugin.AvatarModdedPreset.Value = 3;
            Plugin.AvatarVanillaPreset.Value = 5;              // preset 5 carries a custom eye
            Time.frameCount = 30;
            AvatarDefaults.Tick();
            bool gold = Bands(SpriteOn(ps[3]), Gold, Gold);
            bool red = Bands(SpriteOn(ps[5]), Red, Red);
            bool none = SpriteOn(ps[0]) == null && SpriteOn(ps[1]) == null && SpriteOn(ps[2]) == null && SpriteOn(ps[4]) == null;
            okL1 = both && gold && red && none && first == 1 && UIFactory.Sprites.Count == 2;
            return "one preset both defaults: dual ring (gold outer, blue inner)=" + both + " sprites " + first
                + " | modded 3, vanilla 5 (not clean): gold=" + gold + " red=" + red + " others bare=" + none
                + " sprites " + UIFactory.Sprites.Count;
        }

        private static int Main()
        {
            Case("H6a", () => Liveness(() => GameManager.instance.isPlaying = true, () => GameManager.instance.isPlaying = false,
                                       "isPlaying alone"), () => ok6);
            Case("H6b", () => Liveness(() => GameManager.instance.battleOngoing = true, () => GameManager.instance.battleOngoing = false,
                                       "battleOngoing alone"), () => ok6);
            Case("H6c", () => Liveness(() =>
            {
                GameManager.instance = null;
                var go = new GameObject("body");
                var body = (global::Player)go.AddComponent(typeof(global::Player));
                body.data = new CharacterData { view = new PhotonView { IsMine = true } };
                PlayerManager.instance.players.Add(body);
            }, () => PlayerManager.instance.players.Clear(), "a local body without a manager"), () => ok6);

            CharacterCreatorHandler saved = null;
            Case("H9c", () => MissingData(() => { saved = Cch; CharacterCreatorHandler.instance = null; },
                                          () => CharacterCreatorHandler.instance = saved, "no character controller"), () => ok9);
            Case("H9s", () => MissingData(() => Cch.selectedFaceID = new int[0],
                                          () => Cch.selectedFaceID = new[] { 1, 0, 0, 0 }, "no selected face"), () => ok9);
            PlayerFace[] table = null;
            Case("M3t", () => MissingData(() => { table = Cch.playerFaces; Cch.playerFaces = null; },
                                          () => Cch.playerFaces = table, "no face table"), () => ok9);

            bool ok4 = false;
            Case("BRM4", () =>
            {
                Reset(3);
                Room(false);
                PhotonNetwork.OfflineFn = () => { throw new InvalidOperationException("probe: the second room getter throws"); };
                AvatarDefaults.Evaluate("E2-joined");
                int second = LiveSel;
                Reset(3);
                Room(false);
                PhotonNetwork.InRoomFn = () => { throw new InvalidOperationException("probe: the first room getter throws"); };
                AvatarDefaults.Evaluate("E2-joined");
                int first = LiveSel;
                Reset(3);
                Room(false);
                AvatarDefaults.Evaluate("E2-joined");
                int readable = LiveSel;
                ok4 = second == 3 && first == 3 && readable == 1;
                return "InRoom read, OfflineMode threw: live " + second + " (must stay 3, never the vanilla 1)"
                    + " | InRoom threw: live " + first + " | both read: live " + readable + " (the same room moves it to 1)";
            }, () => ok4);

            bool ok8a = false;
            Case("M8apply", () =>
            {
                Reset(3);
                Room(false);
                AvatarDefaults.Evaluate("E4-props");          // a property edge: it logs only an applied change
                bool line = Logged("[AVATAR] E4-props applied slot 1 (facing Vanilla, nominee 1, other fighters 1,");
                ok8a = LiveSel == 1 && line;
                return "a property edge that applies: live " + LiveSel + ", applied line=" + line;
            }, () => ok8a);

            bool ok8r = false;
            Case("M8room", () =>
            {
                Reset(2);
                Room(true);                                    // a modded room; live is already the modded default
                AvatarDefaults.Evaluate("E2-joined");
                bool kept = Logged("[AVATAR] E2-joined kept slot 2 (facing Modded, nominee 2, other fighters 1,");
                Plugin.Log.Lines.Clear();
                AvatarDefaults.Evaluate("E4-props");
                bool quiet = !Logged("[AVATAR] E4-props");
                ok8r = LiveSel == 2 && kept && quiet;
                return "a room edge that keeps the face: kept line=" + kept + " | a property edge that keeps it: silent=" + quiet;
            }, () => ok8r);

            Case("L1sprite", Rings, () => okL1);

            bool okAn = false;
            Case("L1announce", () =>
            {
                Reset(3);
                Plugin.AvatarVanillaPreset.Value = 5;          // named, but carries a custom eye
                Room(false);
                AvatarDefaults.Evaluate("E2-joined");
                var shown = CompetitiveUI.Shown;
                bool named = shown.Count == 1 && shown[0].Contains("items an unmodded player cannot see");
                bool recovery = shown.Count == 1 && shown[0].Contains(AvatarDefaults.RecoveryInstruction());
                okAn = named && recovery && LiveSel == 3;
                return "an unusable vanilla default in a vanilla room: toasts " + shown.Count + ", reason named=" + named
                    + ", recovery instruction carried=" + recovery + ", live " + LiveSel;
            }, () => okAn);
            return 0;
        }
    }
}
