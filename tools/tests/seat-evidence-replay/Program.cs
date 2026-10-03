using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text.Json;
using CompetitiveRounds;
using ExitGames.Client.Photon;
using Photon.Pun;

namespace SeatEvidenceReplay
{
    /// <summary>Scripted replays through the REAL plugin/SeatEvidence.cs (its
    /// Unity-side classification: block kinds and keys, started and faults,
    /// last_*, the hit paths, dmg marking, the unpaired counts, the frozen
    /// window and end kinds, the queue across a launch, the compat sender).
    /// Each case runs in its own process:
    ///   ReplayTests CASE DIR      (DIR: an empty directory for the queue file)
    /// Exit 0 only when the case passes.</summary>
    internal static class Program
    {
        private const int ME = 1, OPP = 2;
        private const string SEAT = "76561190000000001", OTHER = "76561190000000002";
        private const string ROOM = "ranked_room1";

        private static void Check(bool ok, string what) { if (!ok) throw new Exception(what); }
        private static void Eq<T>(T want, T got, string what)
        {
            if (!EqualityComparer<T>.Default.Equals(want, got)) throw new Exception(what + ": want " + want + ", got " + got);
        }

        // -- the world ------------------------------------------------------------------

        private sealed class Ch { internal PhotonView View; internal CharacterData Data; internal Block Block; internal HealthHandler Hh; }

        private static Ch Char(int viewId, int owner, bool mine)
        {
            var c = new Ch { View = new PhotonView { ViewID = viewId, OwnerActorNr = owner, IsMine = mine },
                             Data = new CharacterData(), Block = new Block(), Hh = new HealthHandler() };
            c.Data.view = c.View; c.Data.block = c.Block;
            foreach (UnityEngine.Component a in new UnityEngine.Component[] { c.View, c.Data, c.Block, c.Hh })
                foreach (UnityEngine.Component b in new UnityEngine.Component[] { c.View, c.Data, c.Block, c.Hh })
                    if (!ReferenceEquals(a, b)) a.Attach(b);
            PhotonNetwork.Views[viewId] = c.View;
            return c;
        }

        private static ProjectileHit Proj(int viewId, int owner, bool mine)
        {
            var ph = new ProjectileHit();
            var v = new PhotonView { ViewID = viewId, OwnerActorNr = owner, IsMine = mine };
            ph.Attach(v); v.Attach(ph);
            PhotonNetwork.Views[viewId] = v;
            return ph;
        }

        private static Ch _me, _opp;

        private static void World(string dir)
        {
            BepInEx.Paths.ConfigPath = dir;
            PhotonNetwork.LocalPlayer = new Photon.Realtime.Player { ActorNumber = ME };
            var oppP = new Photon.Realtime.Player { ActorNumber = OPP };
            PhotonNetwork.CurrentRoom = new Photon.Realtime.Room { Name = ROOM };
            PhotonNetwork.CurrentRoom.Players[OPP] = oppP;
            RoomActors.Others = new[] { oppP };
            PhotonNetwork.ServerTimestamp = 1000000;
            _me = Char(1001, ME, true);
            _opp = Char(2001, OPP, false);
            // the boot hash (F7): a build waits for it, so the world starts with it done
            SeatEvidence.StartHashing();
            for (int i = 0; i < 200 && !SeatEvidence.IdentityReady; i++) System.Threading.Thread.Sleep(50);
            Check(SeatEvidence.IdentityReady, "the boot hash completed");
        }

        /// <summary>One RPC executed on this seat, as PhotonNetwork.ExecuteRpc
        /// runs it under the evidence prefix and finalizer.</summary>
        private static void Rpc(int viewId, int stamp, string method, int sender, Action body)
        {
            var h = new Hashtable();
            h[(byte)0] = viewId; h[(byte)2] = stamp; h[(byte)3] = method;
            int d = SeatEvidence.EnterRpc(h, new Photon.Realtime.Player { ActorNumber = sender });
            try { body(); } finally { SeatEvidence.ExitRpc(d); }
        }

        /// <summary>Block.RPCA_DoBlock under its evidence prefix and finalizer;
        /// `resets` is whether the body's synchronous part resets sinceBlock.</summary>
        private static void DoBlock(Ch c, bool first, BlockTrigger.BlockTriggerType trig, bool onlyEffects, bool resets)
        {
            int idx = SeatEvidence.BlockEnter(c.Block, first, trig, onlyEffects);
            if (resets && !onlyEffects) c.Block.sinceBlock = 0f;
            SeatEvidence.BlockExit(idx);
        }

        private static void Hit(ProjectileHit ph, int pid, Ch target, bool blocked, Action inside = null)
        {
            int idx = SeatEvidence.HitEnter(ph, pid, target.View.ViewID, blocked);
            if (inside != null) inside();
            SeatEvidence.HitExit(idx);
        }

        /// <summary>HealthHandler.RPCA_SendTakeDamage under its evidence prefix
        /// and finalizer: `nonzero` is the envelope's damage, `completed`
        /// whether the method ran to its end without an exception.</summary>
        private static void Damage(Ch c, bool nonzero = true, bool completed = true)
        {
            bool g = SeatEvidence.DamageGate(c.Hh, nonzero);
            SeatEvidence.DamageArrived(c.Hh, g, completed);
        }

        // -- the queue file and the record ------------------------------------------------

        private static string QueueFile() { return Path.Combine(BepInEx.Paths.ConfigPath, "CompetitiveRounds.seat-evidence.jsonl"); }

        /// <summary>The request lines (the trailer line excluded).</summary>
        private static string[] QueueLines()
        {
            var all = File.Exists(QueueFile()) ? File.ReadAllLines(QueueFile()) : new string[0];
            var l = new List<string>();
            foreach (var x in all) if (x.Length > 0 && !x.StartsWith("#", StringComparison.Ordinal)) l.Add(x);
            return l.ToArray();
        }

        private static string[] Fields(string line) { return line.Split(new[] { '\t' }, 7); }

        private static string BodyOf(string line) { return Fields(line)[6]; }

        private static SeatEvidenceCore.QueueCopy ReadQueue()
        {
            return SeatEvidenceCore.ParseQueue(File.Exists(QueueFile()) ? File.ReadAllText(QueueFile()) : "", true);
        }

        /// <summary>Writes the queue file as a launch would have left it.</summary>
        private static void WriteQueue(List<SeatEvidenceCore.Pending> items, long gen, string path = null)
        {
            File.WriteAllText(path ?? QueueFile(), SeatEvidenceCore.QueueText(items, gen));
        }

        /// <summary>A new launch: the in-memory queue forgotten, the file re-read.</summary>
        private static void NextLaunch()
        {
            ((System.Collections.IList)Field("_queue")).Clear();
            SetField("_loaded", false);
            SetField("_nextPumpMs", 0L);
            SetField("_inFlight", false);
        }

        /// <summary>One send (the pump's spacing waived) and the tick that
        /// takes its answer.</summary>
        private static void SendOnce()
        {
            SetField("_nextPumpMs", 0L);
            SeatEvidence.Tick();
            SeatEvidence.Tick();
        }

        private static void ApiUp()
        {
            ApiClient.Base = "https://replay.invalid:8444";
            SteamAuth.SessionToken = "session-for-the-replay";
        }

        private static int Logged(string text)
        {
            int n = 0;
            foreach (var l in Plugin.Log.Lines) if (l.Contains(text)) n++;
            return n;
        }

        private static string QueuedRecord(long firstUnix, int attempts, long notBefore)
        {
            return SeatEvidenceCore.Line(new SeatEvidenceCore.Pending { Route = "e", Body = "{\"x\":1}", FirstUnix = firstUnix, Attempts = attempts, NotBeforeUnix = notBefore });
        }

        private static JsonElement LastRecord(out string attach)
        {
            var lines = QueueLines();
            Check(lines.Length > 0, "a record was queued");
            string body = BodyOf(lines[lines.Length - 1]);
            var env = JsonDocument.Parse(body).RootElement;
            attach = env.GetProperty("attach_key").GetString();
            return JsonDocument.Parse(env.GetProperty("record").GetString()).RootElement;
        }

        private static string Arr(JsonElement rec, string key) { return rec.GetProperty(key).GetRawText(); }

        private static int RouteCount(string route)
        {
            int n = 0;
            foreach (var l in QueueLines()) { var f = Fields(l); if (f.Length == 7 && f[5] == route) n++; }
            return n;
        }

        private static int RecordCount() { return RouteCount("e"); }

        /// <summary>The game-over dispatch (a capture, F4) and the tick that
        /// builds and persists its record.</summary>
        private static void Dispatch(int self, int other, string attach)
        {
            SeatEvidence.Dispatch(SEAT, OTHER, attach, self, other, true);
            SeatEvidence.Tick();
        }

        private static object Field(string name)
        {
            return typeof(SeatEvidence).GetField(name, BindingFlags.NonPublic | BindingFlags.Static).GetValue(null);
        }

        private static void SetField(string name, object v)
        {
            typeof(SeatEvidence).GetField(name, BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, v);
        }

        // -- cases ---------------------------------------------------------------------------

        /// <summary>This seat is the victim: its own block opened by a direct
        /// Default press keys on the stamp PUN wrote into its outgoing
        /// RPCAO_DoBlock (Others); hits from the other seat list with own_since
        /// read before the body; dmg marks the hit its damage envelope
        /// follows; a damage envelope no hit keys counts in unpair[1]; the
        /// victim never lists path 1 (D2).</summary>
        private static void VictimBlockHit()
        {
            SeatEvidence.BeginGame(true, true);
            var ph = Proj(901, OPP, false);
            DoBlock(_me, true, BlockTrigger.BlockTriggerType.Default, false, true);
            PhotonNetwork.ServerTimestamp = 1000005;
            PhotonNetwork.rpcEvent = new Hashtable();
            PhotonNetwork.rpcEvent[(byte)0] = _me.View.ViewID; PhotonNetwork.rpcEvent[(byte)2] = 1000008;
            SeatEvidence.BlockSent(_me.View, "RPCAO_DoBlock", RpcTarget.All);       // not the Others send: ignored
            PhotonNetwork.rpcEvent[(byte)2] = 1000010;
            SeatEvidence.BlockSent(_me.View, "RPCAO_DoBlock", RpcTarget.Others);
            _me.Block.sinceBlock = 0.123f;
            PhotonNetwork.ServerTimestamp = 1000150;
            Rpc(901, 1000140, "RPCA_DoHit", OPP, () => Hit(ph, 55, _me, true));
            _me.Block.sinceBlock = 0.5f;
            PhotonNetwork.ServerTimestamp = 1000610;
            Rpc(901, 1000600, "RPCA_DoHit", OPP, () => Hit(ph, 56, _me, false));
            Rpc(_me.View.ViewID, 1000601, "RPCA_SendTakeDamage", OPP, () => Damage(_me));
            Rpc(_me.View.ViewID, 1000700, "RPCA_SendTakeDamage", OPP, () => Damage(_me));   // no hit keys it
            Dispatch(2, 1, ROOM + "_123456_r3");
            string attach;
            var rec = LastRecord(out attach);
            Eq(ROOM + "_123456_r3", attach, "attach key");
            Eq("[[1000010,0,0,-10]]", Arr(rec, "blk_sent"), "blk_sent: the Others envelope's stamp, own_open rel ms");
            Eq("[[0,1000140,0,0,1000150,1,0,123],[0,1000600,0,0,1000610,0,1,500]]", Arr(rec, "hit_recv"),
               "hit_recv: path 0, own_since before the body, dmg on the hit the damage followed");
            Eq("[2,1,1]", Arr(rec, "imp"), "imp: n, blocked, distinct unblocked projectiles");
            Eq("[0,1]", Arr(rec, "unpair"), "unpair: the damage envelope no hit keys");
            Check(!rec.TryGetProperty("end", out _), "a game this seat saw over carries no end key");
            foreach (var e in rec.GetProperty("hit_recv").EnumerateArray())
                Check(e[0].GetInt32() == 0, "D2: the victim never lists path 1");
        }

        /// <summary>This seat is the shooter: the other seat's block RPC lists
        /// as blk_recv kind 0 with started; an Echo under it keys on the root
        /// stamp as kind 3; path 0 hit_sent names the window that last reset the
        /// copy; path 1 takes the stamp of the damage envelope sent inside the
        /// hit; a path-1 hit with no damage envelope is unpaired; an unkeyed
        /// reset clears last_*; a block whose reset did not run is a fault.</summary>
        private static void ShooterPaths()
        {
            SeatEvidence.BeginGame(true, true);
            var mine = Proj(801, ME, true);
            PhotonNetwork.ServerTimestamp = 2000050;
            Rpc(_opp.View.ViewID, 2000000, "RPCAO_DoBlock", OPP, () => DoBlock(_opp, true, BlockTrigger.BlockTriggerType.Default, false, true));
            PhotonNetwork.ServerTimestamp = 2000060;
            DoBlock(_opp, false, BlockTrigger.BlockTriggerType.Echo, false, true);
            _opp.Block.sinceBlock = 0.2f;
            Rpc(801, 2000300, "RPCA_DoHit", ME, () => Hit(mine, 77, _opp, false));
            _opp.Block.sinceBlock = 0.25f;
            Hit(mine, 78, _opp, false, () => Rpc(_opp.View.ViewID, 2000400, "RPCA_SendTakeDamage", ME, () => Damage(_opp)));
            Hit(mine, 79, _opp, false);                                   // path 1, no damage envelope
            _opp.Block.sinceBlock = 0f;
            SeatEvidence.UnkeyedReset(_opp.Block);
            _opp.Block.sinceBlock = 0.05f;
            Rpc(801, 2000500, "RPCA_DoHit", ME, () => Hit(mine, 80, _opp, true));
            _opp.Block.sinceBlock = 1.0f;
            PhotonNetwork.ServerTimestamp = 2001020;
            Rpc(_opp.View.ViewID, 2001000, "RPCAO_DoBlock", OPP, () => DoBlock(_opp, true, BlockTrigger.BlockTriggerType.Default, false, false));
            Dispatch(3, 2, ROOM + "_123456_r5");
            string attach;
            var rec = LastRecord(out attach);
            Eq("[[2000000,0,0,2000050,1],[2000000,3,0,2000060,1],[2001000,0,0,2001020,0]]", Arr(rec, "blk_recv"),
               "blk_recv: kind 0, its Echo as kind 3 on the root, a block whose reset did not run");
            Eq("[[0,2000300,0,0,200,0,2000000,3,0],[1,2000400,78,0,250,0,2000000,3,0],[0,2000500,0,0,50,1,0,-1,0]]",
               Arr(rec, "hit_sent"), "hit_sent: path 0 and path 1 keys, last_* named then cleared by the unkeyed reset");
            Eq(1L, rec.GetProperty("blk_faults").GetInt64(), "blk_faults");
            Eq("[0,1]", Arr(rec, "unpair"), "unpair: the path-1 hit with no damage envelope");
            Eq("[2,1]", Arr(rec, "dec"), "dec counts path-0 decisions");
            bool path1 = false;
            foreach (var e in rec.GetProperty("hit_sent").EnumerateArray()) if (e[0].GetInt32() == 1) path1 = true;
            Check(path1, "D2: the shooter lists its one-sided path-1 entry");
        }

        /// <summary>A path-1 hit with no damage envelope has no stamp: it counts
        /// in unpair[1] and is never listed, even when a later block of the
        /// other seat would admit a stamp of 0 into its window.</summary>
        private static void Path1Unstamped()
        {
            SeatEvidence.BeginGame(true, true);
            var mine = Proj(801, ME, true);
            Hit(mine, 79, _opp, false);                                   // path 1, no damage envelope
            PhotonNetwork.ServerTimestamp = 70;
            Rpc(_opp.View.ViewID, 50, "RPCAO_DoBlock", OPP, () => DoBlock(_opp, true, BlockTrigger.BlockTriggerType.Default, false, true));
            Dispatch(1, 0, ROOM + "_123456_r1");
            string attach;
            var rec = LastRecord(out attach);
            Eq(1, rec.GetProperty("blk_recv").GetArrayLength(), "the block near stamp 0 is listed");
            Eq("[]", Arr(rec, "hit_sent"), "the unstamped hit is never listed");
            Eq("[0,1]", Arr(rec, "unpair"), "it counts in unpair[1]");
        }

        /// <summary>Unkeyed windows count, never list; nested RPC frames
        /// restore the outer frame (an inner RPC does not hide the outer block's
        /// key); a remote frame from another view keys nothing.</summary>
        private static void UnkeyedAndNesting()
        {
            SeatEvidence.BeginGame(true, true);
            DoBlock(_opp, false, BlockTrigger.BlockTriggerType.Echo, false, true);              // Echo with no root
            DoBlock(_me, false, BlockTrigger.BlockTriggerType.Default, false, true);            // a derived own window
            PhotonNetwork.ServerTimestamp = 3000040;
            Rpc(_opp.View.ViewID, 3000000, "RPCAO_DoBlock", OPP, () =>
            {
                Rpc(_opp.View.ViewID, 3000001, "RPCA_SomethingElse", OPP, () => { });
                DoBlock(_opp, true, BlockTrigger.BlockTriggerType.Default, false, true);
            });
            Rpc(999, 3000100, "RPCAO_DoBlock", OPP, () => DoBlock(_opp, true, BlockTrigger.BlockTriggerType.Default, false, true));
            Dispatch(1, 1, ROOM + "_123456_r2");
            string attach;
            var rec = LastRecord(out attach);
            Eq("[[3000000,0,0,3000040,1]]", Arr(rec, "blk_recv"), "the outer frame keys the block after an inner RPC");
            Eq("[3,0]", Arr(rec, "unpair"), "unpair: Echo without root, a derived window, a frame of another view");
            Eq("[]", Arr(rec, "blk_sent"), "nothing listed for unkeyed own windows");
        }

        /// <summary>A game cut short: the room exit freezes the window (nothing
        /// after it is collected), the noted end kind rides in the record
        /// right after rounds, and the lists collected up to the exit are kept.</summary>
        private static void CutLeft()
        {
            SeatEvidence.BeginGame(true, true);
            PhotonNetwork.ServerTimestamp = 4000030;
            Rpc(_opp.View.ViewID, 4000000, "RPCAO_DoBlock", OPP, () => DoBlock(_opp, true, BlockTrigger.BlockTriggerType.Default, false, true));
            SeatEvidence.RoomExit();
            Rpc(_opp.View.ViewID, 4000500, "RPCAO_DoBlock", OPP, () => DoBlock(_opp, true, BlockTrigger.BlockTriggerType.Default, false, true));
            SeatEvidence.NoteEnd("left");
            Dispatch(4, 5, ROOM + "_654321_r9");
            string attach;
            var rec = LastRecord(out attach);
            Eq("left", rec.GetProperty("end").GetString(), "end kind");
            Eq("[[4000000,0,0,4000030,1]]", Arr(rec, "blk_recv"), "collected up to the exit, nothing after");
            string text = rec.GetRawText();
            Check(text.Contains("\"rounds\":[4,5],\"end\":\"left\",\"build\":"), "end follows rounds: " + text.Substring(0, 120));
            Eq(1, RecordCount(), "one record");
            Dispatch(4, 5, ROOM + "_654321_r9");
            Eq(1, RecordCount(), "a window is taken once");
        }

        /// <summary>The frozen window's guards: another room's dispatch takes
        /// nothing; a frozen window older than FROZEN_MS is never a record; the
        /// first noted end is kept; ClearEnd forgets an end that no longer holds.</summary>
        private static void CutGuards()
        {
            SeatEvidence.BeginGame(true, true);
            SeatEvidence.RoomExit();
            Dispatch(1, 0, "ranked_other_123456_r1");
            Eq(0, RecordCount(), "another room's dispatch takes nothing");
            SeatEvidence.BeginGame(true, true);
            SeatEvidence.RoomExit();
            SetField("_frozenAtMs", SeatEvidence.SwMs - SeatEvidence.FROZEN_MS - 5000);
            Dispatch(1, 0, ROOM + "_123456_r1");
            Eq(0, RecordCount(), "an expired frozen window is never a record");
            SeatEvidence.BeginGame(true, true);
            SeatEvidence.NoteEnd("other_left");
            SeatEvidence.NoteEnd("left");
            SeatEvidence.RoomExit();
            Dispatch(4, 2, ROOM + "_123456_r6");
            string attach;
            Eq("other_left", LastRecord(out attach).GetProperty("end").GetString(), "the first noted end is kept");
            SeatEvidence.BeginGame(true, true);
            SeatEvidence.NoteEnd("other_left");
            SeatEvidence.ClearEnd();
            SeatEvidence.RoomExit();
            SeatEvidence.NoteEnd("left");
            SeatEvidence.NoteEnd("bogus");
            Dispatch(2, 2, ROOM + "_123456_r4");
            Eq("left", LastRecord(out attach).GetProperty("end").GetString(), "a cleared end is forgotten");
            Eq(2, RecordCount(), "two records in all");
        }

        /// <summary>A game still live while the game closes: the record is
        /// written to the queue file and nothing is sent; at the next launch
        /// the file is loaded and the identical bytes are sent.</summary>
        private static void ClosingNextBoot()
        {
            SeatEvidence.BeginGame(true, true);
            PhotonNetwork.ServerTimestamp = 5000030;
            Rpc(_opp.View.ViewID, 5000000, "RPCAO_DoBlock", OPP, () => DoBlock(_opp, true, BlockTrigger.BlockTriggerType.Default, false, true));
            SeatEvidence.NoteEnd("closing");
            // the quit hook: the capture, then the flush (no later frame comes)
            SeatEvidence.Dispatch(SEAT, OTHER, ROOM + "_123456_r4", 3, 1, true);
            SeatEvidence.FlushOnQuit();
            Eq(0, ApiClient.Posts.Count, "nothing sent while closing");
            var lines = QueueLines();
            Eq(1, lines.Length, "persisted to the queue file");
            string body = BodyOf(lines[0]);
            string attach;
            Eq("closing", LastRecord(out attach).GetProperty("end").GetString(), "end kind closing");
            // the next launch: a fresh in-memory queue, the api up with a session
            NextLaunch();
            ApiUp();
            SendOnce();
            Eq(1, ApiClient.Posts.Count, "sent at the next launch");
            Eq("/api/v1/matches/seat-evidence", ApiClient.Posts[0].Key, "the record route");
            Eq(body, ApiClient.Posts[0].Value, "the identical bytes");
            Eq(0, QueueLines().Length, "dropped from the file after recorded");
        }

        /// <summary>A server without amendment A1 answers a cut game's record
        /// 422: the record stays in the queue file, is not sent again in this
        /// launch, and the next launch sends the identical bytes.</summary>
        private static void Cut422Kept()
        {
            SeatEvidence.BeginGame(true, true);
            SeatEvidence.RoomExit();
            SeatEvidence.NoteEnd("lost");
            Dispatch(2, 1, ROOM + "_123456_r3");
            Eq(1, RecordCount(), "the cut game's record is queued");
            ApiUp();
            ApiClient.AnswerOk = false;
            ApiClient.Answer = "HTTP 422: {\"detail\":\"end\"}";
            SendOnce();
            Eq(1, ApiClient.Posts.Count, "sent once");
            Eq(1, RecordCount(), "kept in the queue file after the 422");
            SendOnce();
            Eq(1, ApiClient.Posts.Count, "held: not sent again in this launch");
            // the next launch, against a server that now takes the key
            NextLaunch();
            ApiClient.AnswerOk = true;
            ApiClient.Answer = "{\"status\":\"recorded\"}";
            SendOnce();
            Eq(2, ApiClient.Posts.Count, "sent again at the next launch");
            Eq(ApiClient.Posts[0].Value, ApiClient.Posts[1].Value, "the identical bytes");
            Eq(0, QueueLines().Length, "dropped from the file after recorded");
        }

        /// <summary>F5, the seat the finding disabled: it points the api at the
        /// configured base and obtains a session through the Steam ticket path
        /// for this seat's own id; then the queue's own pump sends EVERY queued
        /// request, the game record queued earlier as well as the compat
        /// outcome, exactly as on an enabled seat.</summary>
        private static void CompatSender()
        {
            SeatEvidence.BeginGame(true, true);
            Dispatch(1, 0, ROOM + "_123456_r1");                    // a queued game record from earlier
            Eq(1, RecordCount(), "the game record is queued");
            Plugin.modDisabled = true;
            SeatEvidence.NoteCompat("finding", new[] { "other.plugin", "two_2" });
            SteamAuth.GrantAfter = 1;
            for (int i = 0; i < 5; i++) SeatEvidence.CompatTick();
            Eq("https://replay.invalid:8444", ApiClient.Base, "base set");
            Eq(SEAT, SteamAuth.FallbackIdentity, "the exchange is for this seat's own id");
            Eq(1, SteamAuth.Refreshes, "one ticket request");
            Eq(0, ApiClient.Posts.Count, "the session step sends nothing itself");
            for (int i = 0; i < 4; i++) SendOnce();
            Eq(2, ApiClient.Posts.Count, "both queued requests sent");
            Eq("/api/v1/matches/seat-evidence", ApiClient.Posts[0].Key, "the game record (queued first)");
            Eq("/api/v1/client/compat-outcome", ApiClient.Posts[1].Key, "then the compat outcome");
            Check(ApiClient.Posts[1].Value.Contains("\"outcome\":\"finding\""), "the finding outcome");
            Eq(0, QueueLines().Length, "both settled");
        }

        /// <summary>F5: a disabled seat with no compat outcome this launch but a
        /// game record an earlier launch queued still obtains a session and
        /// sends it.</summary>
        private static void DisabledSeatRecords()
        {
            SeatEvidence.BeginGame(true, true);
            Dispatch(2, 1, ROOM + "_123456_r3");
            Eq(1, RecordCount(), "queued by an earlier launch");
            NextLaunch();
            Plugin.modDisabled = true;
            SteamAuth.GrantAfter = 1;
            for (int i = 0; i < 3; i++) SeatEvidence.CompatTick();
            Eq(1, SteamAuth.Refreshes, "one ticket request for the queued record");
            SendOnce();
            Eq(1, ApiClient.Posts.Count, "the record sends while the mod stays disabled");
            Eq("/api/v1/matches/seat-evidence", ApiClient.Posts[0].Key, "the record route");
            Eq(0, RecordCount(), "settled");
        }

        /// <summary>F9: one compat-route POST per launch; after a failure the
        /// outcome stays queued and waits for a later launch.</summary>
        private static void CompatOncePerLaunch()
        {
            SeatEvidence.NoteCompat("not_run", new string[0]);
            SeatEvidence.CompatTick();
            Eq(1, RouteCount("c"), "the compat outcome is queued");
            ApiUp();
            ApiClient.AnswerOk = false;
            ApiClient.Answer = "HTTP 503: {\"error\":\"seat_evidence_off\"}";
            SendOnce();
            Eq(1, ApiClient.Posts.Count, "one compat POST");
            foreach (SeatEvidenceCore.Pending p in (System.Collections.IList)Field("_queue")) p.NotBeforeUnix = 0;
            for (int i = 0; i < 3; i++) SendOnce();
            Eq(1, ApiClient.Posts.Count, "no second compat POST in this launch, even with its retry time waived");
            Eq(1, RouteCount("c"), "it stays queued after the failure");
            // a later launch, past its next-eligible time
            var q = ReadQueue();
            foreach (var p in q.Items) p.NotBeforeUnix = 0;
            WriteQueue(q.Items, q.Generation + 1);
            NextLaunch();
            ApiClient.AnswerOk = true;
            ApiClient.Answer = "{\"status\":\"recorded\"}";
            SendOnce();
            Eq(2, ApiClient.Posts.Count, "sent again at a later launch");
            Eq(0, RouteCount("c"), "settled");
        }

        /// <summary>F6: only requests that leave count; the count and the next
        /// time are in the file before the bytes leave; the next time holds
        /// across a restart; the 20-attempt and seven-day limits hold before
        /// every transmission whatever the answers (404, 401) and restarts.</summary>
        private static void AttemptAccounting()
        {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            SeatEvidence.BeginGame(true, true);
            Dispatch(2, 1, ROOM + "_123456_r3");
            ApiUp();
            Plugin.Consent = false;
            SendOnce();
            Plugin.Consent = true;
            ApiClient.RefuseInside = true;
            SendOnce();
            ApiClient.RefuseInside = false;
            Eq(0, ApiClient.Posts.Count, "nothing left the client");
            Eq("0", Fields(QueueLines()[0])[2], "no attempt counted for requests that did not leave");
            string atSend = null;
            ApiClient.OnSend = () => { atSend = QueueLines()[0]; };
            ApiClient.AnswerOk = false;
            ApiClient.Answer = "Cannot resolve destination host";
            SendOnce();
            ApiClient.OnSend = null;
            Eq(1, ApiClient.Posts.Count, "sent");
            Check(atSend != null, "the file was read as the bytes left");
            Eq("1", Fields(atSend)[2], "the file held attempt 1 when the bytes left");
            Check(long.Parse(Fields(atSend)[4]) > now, "and a future next-eligible time");
            NextLaunch();
            SendOnce();
            Eq(1, ApiClient.Posts.Count, "not before its next-eligible time, across a restart");
            // 19 spent; a 404 (kept for the next launch); a restart
            var spent = new SeatEvidenceCore.Pending { Route = "e", Body = "{\"x\":1}", FirstUnix = now - 10, Attempts = 19 };
            WriteQueue(new List<SeatEvidenceCore.Pending> { spent }, 50);
            NextLaunch();
            ApiClient.Answer = "HTTP 404: {}";
            SendOnce();
            Eq(2, ApiClient.Posts.Count, "the 20th transmission");
            NextLaunch();
            SendOnce(); SendOnce();
            Eq(2, ApiClient.Posts.Count, "no 21st after a 404 and a restart");
            Eq(0, QueueLines().Length, "settled as spent");
            // 19 spent; a 401 (session refresh): no 21st in the same launch either
            WriteQueue(new List<SeatEvidenceCore.Pending> { spent.Clone() }, 60);
            NextLaunch();
            ApiClient.Answer = "HTTP 401: {\"detail\":\"session_required\"}";
            SendOnce();
            Eq(3, ApiClient.Posts.Count, "the 20th transmission");
            foreach (SeatEvidenceCore.Pending p in (System.Collections.IList)Field("_queue")) p.NotBeforeUnix = 0;
            SendOnce(); SendOnce();
            Eq(3, ApiClient.Posts.Count, "no 21st after a 401");
            Eq(0, QueueLines().Length, "settled as spent");
            // seven days: never sent
            WriteQueue(new List<SeatEvidenceCore.Pending> { new SeatEvidenceCore.Pending { Route = "e", Body = "{\"x\":1}", FirstUnix = now - SeatEvidenceCore.EXPIRY_S } }, 70);
            NextLaunch();
            SendOnce();
            Eq(3, ApiClient.Posts.Count, "an expired request never leaves");
            Eq(0, QueueLines().Length, "settled as expired");
        }

        /// <summary>F3: a battle live in THIS frame (the game's own flag) holds
        /// every queue action before any load, save, attempt accounting or
        /// request setup, while the diagnostics flag (refreshed later in the
        /// frame) is still stale; the diagnostics flag alone holds it too.</summary>
        private static void CombatGate()
        {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            WriteQueue(new List<SeatEvidenceCore.Pending> { new SeatEvidenceCore.Pending { Route = "e", Body = "{\"x\":1}", FirstUnix = now } }, 3);
            byte[] before = File.ReadAllBytes(QueueFile());
            SeatEvidence.BeginGame(true, true);
            ApiUp();
            GameManager.instance.battleOngoing = true;
            NetworkReplicaDiagnostics.BattleActive = false;
            SeatEvidence.Dispatch(SEAT, OTHER, ROOM + "_123456_r2", 1, 1, true);
            for (int i = 0; i < 3; i++) SendOnce();
            Eq(false, (bool)Field("_loaded"), "no load while the battle is live");
            Check(Convert.ToBase64String(before) == Convert.ToBase64String(File.ReadAllBytes(QueueFile())), "the queue file untouched");
            Eq(0, ApiClient.Posts.Count, "nothing sent");
            Eq(0, Logged("record queued"), "no build while the battle is live");
            GameManager.instance.battleOngoing = false;
            NetworkReplicaDiagnostics.BattleActive = true;
            SendOnce();
            Eq(false, (bool)Field("_loaded"), "the diagnostics flag alone also holds it");
            Eq(0, ApiClient.Posts.Count, "nothing sent");
            NetworkReplicaDiagnostics.BattleActive = false;
            SendOnce();
            Eq(1, Logged("record queued"), "built once the battle ended");
            Eq(1, ApiClient.Posts.Count, "and the queue sends");
        }

        /// <summary>F4: the dispatch only captures: no file, no log line inside
        /// it (its refusal line too waits); the tick builds, persists and logs.</summary>
        private static void DispatchDefers()
        {
            SeatEvidence.BeginGame(true, true);
            int logs = Plugin.Log.Lines.Count;
            SeatEvidence.Dispatch(SEAT, OTHER, ROOM + "_123456_r2", 1, 1, true);
            Check(!File.Exists(QueueFile()), "no file work inside the dispatch");
            Eq(logs, Plugin.Log.Lines.Count, "no log line inside the dispatch");
            SeatEvidence.BeginGame(true, true);
            SeatEvidence.Dispatch("not-a-seat", OTHER, ROOM + "_123456_r3", 1, 1, true);
            Eq(logs, Plugin.Log.Lines.Count, "a refusal's line waits for the tick too");
            SeatEvidence.Tick();
            Eq(1, RecordCount(), "built and persisted on the tick");
            Eq(1, Logged("record queued"), "logged on the tick");
            Eq(1, Logged("no record: game key or seat ids"), "the refusal logged on the tick");
        }

        /// <summary>F7: no record while the build identity is pending; the
        /// completed identity rides in it. no_location only for an empty
        /// location; an unreadable one is read_failed.</summary>
        private static void IdentityPending()
        {
            SetField("_dllState", SeatEvidence.ID_PENDING);
            SetField("_dllSha", "");
            SeatEvidence.BeginGame(true, true);
            Dispatch(2, 1, ROOM + "_123456_r3");
            SeatEvidence.Tick();
            Eq(0, RecordCount(), "no record while the identity is pending");
            SeatEvidence.CompleteIdentityNow();
            SeatEvidence.Tick();
            string attach;
            var rec = LastRecord(out attach);
            Eq("ok", rec.GetProperty("dll")[1].GetString(), "the completed identity");
            Eq(64, rec.GetProperty("dll")[0].GetString().Length, "its hash");
            var hash = typeof(SeatEvidence).GetMethod("Hash", BindingFlags.NonPublic | BindingFlags.Static);
            Func<string, string> state = path => { var a = new object[] { path, null, null }; hash.Invoke(null, a); return (string)a[2]; };
            Eq("no_location", state(""), "an empty location");
            Eq("read_failed", state(null), "a location that could not be asked for");
            Eq("read_failed", state(Path.Combine(BepInEx.Paths.ConfigPath, "missing.dll")), "an unreadable file");
            Eq("ok", state(typeof(SeatEvidence).Assembly.Location), "a readable file");
        }

        /// <summary>F8: the newer whole temporary copy is recovered; a torn
        /// one never wins over the whole primary.</summary>
        private static void QueueRecovery()
        {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            var a = new SeatEvidenceCore.Pending { Route = "e", Body = "{\"a\":1}", FirstUnix = now };
            var b = new SeatEvidenceCore.Pending { Route = "k", Body = "{\"b\":1}", FirstUnix = now };
            string tmp = QueueFile() + ".tmp";
            WriteQueue(new List<SeatEvidenceCore.Pending> { a }, 1);
            WriteQueue(new List<SeatEvidenceCore.Pending> { a, b }, 2, tmp);     // a replacement that did not complete
            SeatEvidence.BeginGame(true, true);
            Dispatch(2, 1, ROOM + "_123456_r3");
            var q = ReadQueue();
            Check(q.Whole, "the file is whole");
            Eq(3, q.Items.Count, "the newer temporary recovered, then the record added");
            Eq(3L, q.Generation, "written as the next generation");
            Check(!File.Exists(tmp), "the temporary replaced the primary");
            NextLaunch();
            File.WriteAllText(tmp, SeatEvidenceCore.QueueText(new List<SeatEvidenceCore.Pending> { a, b }, 9).Replace("{\"b\":1}", "{\"b\":2}"));
            SeatEvidence.BeginGame(true, true);
            Dispatch(2, 1, ROOM + "_123456_r5");
            q = ReadQueue();
            Eq(4, q.Items.Count, "the whole primary kept, the torn temporary ignored, the record added");
        }

        /// <summary>F8: a record is reported queued only after the queue file
        /// holding it replaced the old one; until then it stays captured and
        /// nothing in memory changes.</summary>
        private static void QueueSaveFails()
        {
            WriteQueue(new List<SeatEvidenceCore.Pending>(), 1);
            SeatEvidence.BeginGame(true, true);
            using (new FileStream(QueueFile(), FileMode.Open, FileAccess.Read, FileShare.None))
            {
                Dispatch(2, 1, ROOM + "_123456_r3");
                Eq(0, Logged("record queued"), "not reported queued while the file cannot be read");
                Eq(1, ((System.Collections.IList)Field("_captures")).Count, "kept captured");
            }
            SetField("_nextCaptureTryMs", 0L);
            SeatEvidence.Tick();
            Eq(1, Logged("record queued"), "queued once the file could be replaced");
            Eq(1, RecordCount(), "in the file");
            string tmp = QueueFile() + ".tmp";
            SeatEvidence.BeginGame(true, true);
            using (new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                Dispatch(1, 1, ROOM + "_123456_r2");
                Eq(1, Logged("record queued"), "a failed replacement is not reported");
                Eq(1, ((System.Collections.IList)Field("_queue")).Count, "nothing in memory changed");
                Eq(1, RecordCount(), "the file still holds the old generation");
                Eq(1, ((System.Collections.IList)Field("_captures")).Count, "kept captured");
            }
            File.Delete(tmp);
            SetField("_nextCaptureTryMs", 0L);
            SeatEvidence.Tick();
            Eq(2, Logged("record queued"), "queued after the replacement succeeded");
            Eq(2, RecordCount(), "both in the file");
        }

        /// <summary>F1: dmg is 1 only for a nonzero envelope that passes the
        /// game's own predicate and completes without an exception.</summary>
        private static void DamagePredicate()
        {
            SeatEvidence.BeginGame(true, true);
            var ph = Proj(901, OPP, false);
            // the own block's window admits the hits (as in victim_block_hit)
            DoBlock(_me, true, BlockTrigger.BlockTriggerType.Default, false, true);
            PhotonNetwork.ServerTimestamp = 1000005;
            PhotonNetwork.rpcEvent = new Hashtable();
            PhotonNetwork.rpcEvent[(byte)0] = _me.View.ViewID; PhotonNetwork.rpcEvent[(byte)2] = 1000010;
            SeatEvidence.BlockSent(_me.View, "RPCAO_DoBlock", RpcTarget.Others);
            int ts = 1000010;
            for (int k = 0; k < 4; k++)
            {
                ts += 100;
                PhotonNetwork.ServerTimestamp = ts + 10;
                int pid = 60 + k;
                Rpc(901, ts, "RPCA_DoHit", OPP, () => Hit(ph, pid, _me, false));
                if (k == 2) _me.Data.dead = true;
                Rpc(_me.View.ViewID, ts + 1, "RPCA_SendTakeDamage", OPP, () => Damage(_me, k != 0, k != 1));
                _me.Data.dead = false;
            }
            Dispatch(2, 1, ROOM + "_123456_r3");
            string attach;
            var rec = LastRecord(out attach);
            var dmg = new List<int>();
            foreach (var e in rec.GetProperty("hit_recv").EnumerateArray()) dmg.Add(e[6].GetInt32());
            Eq("0,0,0,1", string.Join(",", dmg), "zero damage, a body that threw, a dead victim: 0; a completed nonzero hit: 1");
        }

        /// <summary>The compat sender's bounds: nothing without consent (no
        /// base, no ticket); give up after the bound with the outcome kept; no
        /// activity at all on a seat that is not disabled.</summary>
        private static void CompatBounds()
        {
            // not disabled: nothing
            SeatEvidence.NoteCompat("finding", new[] { "other.plugin" });
            for (int i = 0; i < 3; i++) SeatEvidence.CompatTick();
            Eq(0, SteamAuth.Refreshes, "no ticket on a seat that is not disabled");
            Eq(0, ApiClient.Posts.Count, "no send on a seat that is not disabled");
            // disabled without consent
            Plugin.modDisabled = true; Plugin.Consent = false;
            for (int i = 0; i < 3; i++) SeatEvidence.CompatTick();
            Eq("", ApiClient.Base, "no base without consent");
            Eq(0, SteamAuth.Refreshes, "no ticket without consent");
            Eq(0, ApiClient.Posts.Count, "no send without consent");
            // consent, but the session never lands: give up after the bound
            SetField("_sendPhase", 0);
            Plugin.Consent = true; SteamAuth.GrantAfter = -1;
            SeatEvidence.CompatTick();
            Eq(1, SteamAuth.Refreshes, "a ticket requested");
            SetField("_sendStartMs", SeatEvidence.SwMs - SeatEvidenceCore.COMPAT_SEND_LIMIT_MS - 1000);
            SetField("_nextAuthMs", 0L);
            for (int i = 0; i < 3; i++) SeatEvidence.CompatTick();
            Eq(1, SteamAuth.Refreshes, "no ticket after the bound");
            Eq(0, ApiClient.Posts.Count, "no send after the bound");
            Eq(1, QueueLines().Length, "the outcome stays queued for the next launch");
        }

        private static readonly Dictionary<string, Action> Cases = new Dictionary<string, Action>
        {
            { "victim_block_hit", VictimBlockHit }, { "shooter_paths", ShooterPaths },
            { "unkeyed_and_nesting", UnkeyedAndNesting }, { "cut_left", CutLeft }, { "cut_guards", CutGuards },
            { "closing_next_boot", ClosingNextBoot }, { "compat_sender", CompatSender }, { "compat_bounds", CompatBounds },
            { "cut_422_kept", Cut422Kept }, { "path1_unstamped", Path1Unstamped },
            { "disabled_seat_records", DisabledSeatRecords }, { "compat_once_per_launch", CompatOncePerLaunch },
            { "attempt_accounting", AttemptAccounting }, { "combat_gate", CombatGate }, { "dispatch_defers", DispatchDefers },
            { "identity_pending", IdentityPending }, { "queue_recovery", QueueRecovery }, { "queue_save_fails", QueueSaveFails },
            { "damage_predicate", DamagePredicate },
        };

        private static int Main(string[] args)
        {
            if (args.Length == 1 && args[0] == "list") { foreach (var k in Cases.Keys) Console.WriteLine(k); return 0; }
            if (args.Length != 2) { Console.WriteLine("usage: ReplayTests CASE DIR | list"); return 2; }
            Action a;
            if (!Cases.TryGetValue(args[0], out a)) { Console.WriteLine("UNKNOWN " + args[0]); return 2; }
            try
            {
                Directory.CreateDirectory(args[1]);
                World(args[1]);
                a();
                Console.WriteLine("PASS " + args[0]);
                return 0;
            }
            catch (Exception ex)
            {
                Console.WriteLine("FAIL " + args[0] + ": " + ex.Message);
                return 1;
            }
        }
    }
}
