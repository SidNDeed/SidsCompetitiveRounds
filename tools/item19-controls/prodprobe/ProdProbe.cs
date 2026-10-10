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
    /// runs against either. Exit 0 always: the verdicts are the output.
    ///
    /// Fix pass 3 (Codex BUILD round 3) adds H9 and M3 with a restoring
    /// select that throws or does not commit (H9t, H9r, M3x), M8's line on
    /// every exit (M8e2, M8e3, M8def, M8exc) and H3's remote arm (H3remote,
    /// the tree's ledger reached by reflection, so the probe still compiles
    /// against a tree without one).</summary>
    internal static class ProdProbe
    {
        internal static readonly string[] Ids =
            { "H6a", "H6b", "H6c", "H9c", "H9s", "M3t", "BRM4", "M8apply", "M8room", "L1sprite", "L1announce",
              "H9t", "H9r", "M3x", "M8e2", "M8e3", "M8def", "M8exc", "H3remote" };

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

        /// <summary>One log line carrying every needle (fix pass 3: the
        /// classification line and its missing-data tail are one line).</summary>
        private static bool LoggedLine(params string[] needles) =>
            Plugin.Log.Lines.Any(l => needles.All(n => l.Contains(n)));

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
            CharacterCreatorHandler.ThrowBeforeCommit = 0;     // fix pass 3: every select commits
            CharacterCreatorHandler.NoCommit = 0;
            CharacterCreatorHandler.ThrowAfterCommit = 0;
            FacePublisher.Throws = 0;                          // and every carrier publish completes
            VanillaFixSupport.Counts.Clear();                  // E13's line budget starts full
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
            bool deferredLine = LoggedLine("[AVATAR] E6-left", "restoration deferred (");
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

        // ---- H9 and M3 (fix pass 3): a debt is cleared only on a committed read-back --

        private static bool ok9x;

        /// <summary>A confirmed exit whose restoring select does not commit
        /// (fail arms the stub's failure for that one select), then the
        /// throttled tick with the select working again.</summary>
        private static string NotCommitted(Action fail, string what)
        {
            Reset(3);
            Room(false);
            AvatarDefaults.Evaluate("E2-joined");              // 3 -> 1, home 3
            int forced = LiveSel, held = Home;
            Leave();
            fail();
            AvatarDefaults.Evaluate("E6-left");                // restores 3: the select fails
            int liveExit = LiveSel, homeExit = Home;
            bool named = LoggedLine("[AVATAR] E6-left slot 3 not committed");
            int selectsBefore = Cch.SelectCalls;
            Time.frameCount = 30;
            AvatarDefaults.Tick();                             // E13: the debt is still owed
            int liveAfter = LiveSel, homeAfter = Home, applied = Cch.SelectCalls - selectsBefore;
            ok9x = forced == 1 && held == 3 && liveExit == 1 && homeExit == 3 && named
                && liveAfter == 3 && homeAfter == -1 && applied == 1;
            return what + ": forced live=" + forced + " home=" + held
                + " | the exit's select fails: live " + liveExit + " home " + homeExit
                + (homeExit == 3 ? "" : " (the debt was cleared before the selection committed)")
                + ", not-committed line=" + named
                + " | the tick: live " + liveAfter + " home " + homeAfter + " selections " + applied
                + (liveAfter == 3 ? "" : " (the remembered selection is never given back)");
        }

        private static bool ok3x;

        /// <summary>M3: repeated confirmed exits, each failing differently
        /// (missing data, a throwing select, an uncommitted select), keep the
        /// one record (Home 3) until the tick repays it once.</summary>
        private static string RepeatedExits()
        {
            Reset(3);
            Room(false);
            AvatarDefaults.Evaluate("E2-joined");              // 3 -> 1, home 3
            Leave();
            GameManager.instance.isPlaying = true;             // the old manager still reports a game
            var saved = Cch;
            CharacterCreatorHandler.instance = null;           // no character controller
            AvatarDefaults.Evaluate("E6-left");
            int h1 = Home;
            CharacterCreatorHandler.instance = saved;
            CharacterCreatorHandler.ThrowBeforeCommit = 1;
            AvatarDefaults.Evaluate("E7-disconnect");          // the select throws before it commits
            int h2 = Home, l2 = LiveSel;
            CharacterCreatorHandler.NoCommit = 1;
            AvatarDefaults.Evaluate("E6-left");                // the select returns without committing
            int h3 = Home, l3 = LiveSel;
            int selectsBefore = Cch.SelectCalls;
            Time.frameCount = 30;
            AvatarDefaults.Tick();
            int liveAfter = LiveSel, homeAfter = Home, applied = Cch.SelectCalls - selectsBefore;
            Time.frameCount = 45;
            AvatarDefaults.Tick();
            int again = Cch.SelectCalls - selectsBefore - applied;
            ok3x = h1 == 3 && h2 == 3 && h3 == 3 && l2 == 1 && l3 == 1
                && liveAfter == 3 && homeAfter == -1 && applied == 1 && again == 0;
            return "exit with no controller: home " + h1 + " | exit whose select throws: home " + h2 + " live " + l2
                + " | exit whose select does not commit: home " + h3 + " live " + l3
                + " (one record, 3, through every edge) | the tick: live " + liveAfter + " home " + homeAfter
                + " selections " + applied + " | a second tick: selections " + again;
        }

        // ---- H3 (fix pass 3): the popup's remote arm applies only this pick's value --

        /// <summary>A carrier value as a picker publishes it: 12 fields.</summary>
        private static string Wire(int id)
        {
            string i = id.ToString(System.Globalization.CultureInfo.InvariantCulture);
            return string.Join("|", new[] { i, "0.000", "0.000", i, "0.000", "0.000", i, "0.000", "0.000", i, "0.000", "0.000" });
        }

        private static string Short(string v) => v == null ? "nothing" : "face " + v.Split('|')[0] + (v.Split('|').Length == 13 ? " (" + v.Split('|')[12] + ")" : " (untagged)");

        private static object Call(object target, string name, params object[] args)
        {
            var m = target.GetType().GetMethod(name, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
            if (m == null) throw new MissingMethodException(target.GetType().Name, name);
            return m.Invoke(target, args);
        }

        private static string Note(object ledger)
        {
            var p = ledger.GetType().GetProperty("Note", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
            return p != null ? (string)p.GetValue(ledger) : null;
        }

        private static bool ok3r;

        /// <summary>The remote arm against this seat's settled copy of an
        /// actor's carrier (its face from an earlier pick) and the actor's
        /// publish for THIS pick arriving after the popup opened. The tree's
        /// own rules decide (PopupFace, and PopupCarrierLedger when the tree
        /// has one; reflection, so the same probe compiles against a tree
        /// without it). The remote arm's wiring in Plugin.cs, the ledger
        /// through PopupCarriers.ForShow and never a read of the copy, is
        /// bound by the tree's pytest S33.</summary>
        private static string RemoteArm()
        {
            string settled = Wire(1);                          // this seat's copy: the actor's face at an earlier pick
            string fresh = Wire(4) + "|p2";                    // the actor's publish for THIS pick, arriving late
            var rules = new AvatarRules();
            var t = typeof(AvatarRules).Assembly.GetType("CompetitiveRounds.PopupCarrierLedger");
            if (t == null)
            {
                // No ledger: the remote arm is a read of the copy (round 3:
                // FacePublisher.ReadCarrier), which the popup applies at once.
                string atShow = rules.PopupFace(false, FaceCarrierAction.Keep, null, () => settled);
                ok3r = false;
                return "this tree has no PopupCarrierLedger: its remote arm reads the settled copy, and the popup applies "
                    + Short(atShow) + " at Show, the earlier pick's face; the late publish for this pick (" + Short(fresh)
                    + ") is never applied";
            }
            var ledger = Activator.CreateInstance(t, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public,
                                                  null, new object[] { rules }, null);
            var room = new object();
            // A: the popup opens for actor 7; this seat holds only the settled copy.
            string a = rules.PopupFace(false, FaceCarrierAction.Keep, null, () => (string)Call(ledger, "Show", room, 7, 100.0));
            string noteA = Note(ledger);
            string onEcho = (string)Call(ledger, "Arrived", room, 7, fresh, 100.4);
            Call(ledger, "Applied", 7, true, 100.4);
            string noteApplied = Note(ledger);
            // B: actor 7's next popup; the newest value it sent is the previous pick's.
            Call(ledger, "EndSession", room);
            string b = rules.PopupFace(false, FaceCarrierAction.Keep, null, () => (string)Call(ledger, "Show", room, 7, 160.0));
            // C: an untagged value (a 1.40.3 client's, or a publish outside a pick) arrives while it shows.
            string c = (string)Call(ledger, "Arrived", room, 7, Wire(5), 160.2);
            string noteC = Note(ledger);
            ok3r = a == null && noteA != null && noteA.Contains("deferred") && onEcho == fresh
                && noteApplied != null && noteApplied.Contains("owed popup face applied")
                && b == null && c == null && noteC != null && noteC.Contains("stale-unknown");
            return "settled copy " + Short(settled) + ": at Show the popup applies " + Short(a) + " (deferred=" + (noteA != null && noteA.Contains("deferred"))
                + ") | the late publish arrives: applied " + Short(onEcho) + ", owed apply completed=" + (noteApplied != null && noteApplied.Contains("owed popup face applied"))
                + " | the next popup, previous pick's value newest: " + Short(b)
                + " | an untagged value while it shows: applied " + Short(c) + " (stale-unknown=" + (noteC != null && noteC.Contains("stale-unknown")) + ")";
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

            // ---- fix pass 3 (Codex BUILD round 3: H9, M3, M8, H3) ----

            Case("H9t", () => NotCommitted(() => CharacterCreatorHandler.ThrowBeforeCommit = 1,
                                           "the restoring select throws before it commits"), () => ok9x);
            Case("H9r", () => NotCommitted(() => CharacterCreatorHandler.NoCommit = 1,
                                           "the restoring select returns without committing (the read-back is unmoved)"), () => ok9x);
            Case("M3x", RepeatedExits, () => ok3x);

            // M8: every exit writes the classification line (facing, nominee,
            // other-fighter count) before any fallible step, missing data included.
            bool ok8e2 = false;
            Case("M8e2", () =>
            {
                Reset(3);
                Room(false);
                CharacterCreatorHandler.instance = null;       // no character controller
                AvatarDefaults.Evaluate("E2-joined");
                ok8e2 = LoggedLine("[AVATAR] E2-joined kept slot -1 (facing Vanilla, nominee 1, other fighters 1,",
                                   ": nothing applied (no character controller)");
                return "E2 with no character controller: one line naming facing, nominee, other fighters and what was missing=" + ok8e2;
            }, () => ok8e2);

            bool ok8e3 = false;
            Case("M8e3", () =>
            {
                Reset(2);
                Room(true);
                Cch.selectedFaceID = new int[0];               // no selected face
                AvatarDefaults.Evaluate("E3-entered");
                ok8e3 = LoggedLine("[AVATAR] E3-entered kept slot -1 (facing Modded, nominee 2, other fighters 1,",
                                   ": nothing applied (no selected face)");
                return "E3 with no selected face: one line naming facing, nominee, other fighters and what was missing=" + ok8e3;
            }, () => ok8e3);

            bool ok8d = false;
            Case("M8def", () =>
            {
                Reset(3);
                Room(false);
                AvatarDefaults.Evaluate("E2-joined");          // 3 -> 1, home 3
                Leave();
                Cch.playerFaces = null;                        // no face table
                AvatarDefaults.Evaluate("E6-left");
                bool line = LoggedLine("[AVATAR] E6-left kept slot 1 (facing Undecided, nominee -1, other fighters 0,",
                                       ": restoration deferred (no face table), home 3 kept");
                ok8d = line && Home == 3;
                return "E6 deferring its restoration (no face table): one line naming facing, nominee, other fighters and the deferral="
                    + line + ", home " + Home;
            }, () => ok8d);

            bool ok8x = false;
            Case("M8exc", () =>
            {
                Reset(3);
                Room(false);
                FacePublisher.Throws = 1;                      // the carrier publish throws after the select committed
                AvatarDefaults.Evaluate("E2-joined");
                int livePub = LiveSel;
                bool pub = LoggedLine("[AVATAR] E2-joined applied slot 1 (facing Vanilla, nominee 1, other fighters 1,");
                Reset(3);
                Room(false);
                CharacterCreatorHandler.ThrowAfterCommit = 1;  // the select commits, then throws (vanilla's frame repaint)
                AvatarDefaults.Evaluate("E2-joined");
                int liveSel = LiveSel;
                bool sel = LoggedLine("[AVATAR] E2-joined applied slot 1 (facing Vanilla, nominee 1, other fighters 1,");
                ok8x = pub && sel && livePub == 1 && liveSel == 1;
                return "the carrier publish throws: live " + livePub + ", applied line=" + pub
                    + " | the select throws after committing: live " + liveSel + ", applied line=" + sel;
            }, () => ok8x);

            Case("H3remote", RemoteArm, () => ok3r);
            return 0;
        }
    }
}
