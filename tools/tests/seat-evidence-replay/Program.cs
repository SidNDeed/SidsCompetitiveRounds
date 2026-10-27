using System;
using System.Collections.Generic;
using System.IO;
using System.Globalization;
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
            SetField("_stale", false);
            SetField("_spoolChecked", false);
            SetField("_nextPumpMs", 0L);
            SetField("_inFlight", false);
            var kept = Field("_spoolKept");
            kept.GetType().GetMethod("Clear").Invoke(kept, null);
        }

        /// <summary>The closing files the quitting path wrote (F3).</summary>
        private static string[] SpoolFiles()
        {
            return Directory.GetFiles(BepInEx.Paths.ConfigPath, "CompetitiveRounds.seat-evidence.closing-*.jsonl");
        }

        private static int Attempts(System.Collections.IList q, int i)
        {
            return ((SeatEvidenceCore.Pending)q[i]).Attempts;
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
            var rec = JsonDocument.Parse(env.GetProperty("record").GetString()).RootElement;
            // contract A2, on every record a replay builds: hit_recv is path 0
            // only (path 1 is shooter-only) and a path-0 key has pid 0
            foreach (var e in rec.GetProperty("hit_recv").EnumerateArray())
                Check(e[0].GetInt64() == 0 && e[2].GetInt64() == 0, "A2: a built record lists hit_recv " + e.GetRawText());
            return rec;
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
            Eq("[[0,2000300,0,0,200,0,2000000,3,0,1],[1,2000400,78,0,250,0,2000000,3,0,1],[0,2000500,0,0,50,1,0,-1,0,2]]",
               Arr(rec, "hit_sent"), "hit_sent: path 0 and path 1 keys, keyed (reset 1), then unkeyed (reset 2) after the unkeyed reset");
            B7Holds(rec);
            Eq(1L, rec.GetProperty("blk_faults").GetInt64(), "blk_faults");
            Eq("[0,1]", Arr(rec, "unpair"), "unpair: the path-1 hit with no damage envelope");
            Eq("[2,1]", Arr(rec, "dec"), "dec counts path-0 decisions");
            bool path1 = false;
            foreach (var e in rec.GetProperty("hit_sent").EnumerateArray()) if (e[0].GetInt32() == 1) path1 = true;
            Check(path1, "D2: the shooter lists its one-sided path-1 entry");
        }

        /// <summary>Amended B7 (contract AMENDMENT 2026-10-04) on every hit_sent
        /// entry of a record: ten elements; reset 0 none = since_ms -1 and
        /// [0,-1,0]; 1 keyed = since_ms 0 or more and last_kind 0..9; 2 unkeyed
        /// = since_ms 0 or more and [0,-1,0]. Nothing else.</summary>
        private static void B7Holds(JsonElement rec)
        {
            foreach (var e in rec.GetProperty("hit_sent").EnumerateArray())
            {
                string t = e.GetRawText();
                Eq(10, e.GetArrayLength(), "ten elements: " + t);
                long since = e[4].GetInt64(), tb = e[6].GetInt64(), kind = e[7].GetInt64(), ord = e[8].GetInt64(), reset = e[9].GetInt64();
                bool sentinel = tb == 0 && kind == -1 && ord == 0;
                bool ok = reset == 0 ? since == -1 && sentinel
                        : reset == 1 ? since >= 0 && kind >= 0 && kind <= 9
                        : reset == 2 && since >= 0 && sentinel;
                Check(ok, "B7 refuses " + t);
            }
        }

        /// <summary>Round 5 M6/B7: the copy's last-reset state on the wire, in
        /// every transition. A hit before any reset is none; after a keyed
        /// block RPC it is keyed with that block; after a blocked impact's
        /// unkeyed reset (the reviewer's scenario) it is unkeyed with since_ms
        /// counting from that reset, on path 0 and path 1; a later keyed block
        /// makes it keyed again; a block window neither path keys makes it
        /// unkeyed again; a copy with no Block is not decided here.</summary>
        private static void LastResetStates()
        {
            SeatEvidence.BeginGame(true, true);
            var mine = Proj(801, ME, true);
            _opp.Block.sinceBlock = 3.0f;                                                    // no reset seen this game
            Rpc(801, 4000150, "RPCA_DoHit", ME, () => Hit(mine, 1, _opp, false));            // none
            _opp.Block.sinceBlock = 0f;
            SeatEvidence.UnkeyedReset(_opp.Block);                                            // a blocked impact, the first reset
            _opp.Block.sinceBlock = 0.07f;
            Rpc(801, 4000180, "RPCA_DoHit", ME, () => Hit(mine, 3, _opp, true));             // unkeyed, path 0 (round 5)
            PhotonNetwork.ServerTimestamp = 4000250;
            Rpc(_opp.View.ViewID, 4000200, "RPCAO_DoBlock", OPP, () => DoBlock(_opp, true, BlockTrigger.BlockTriggerType.Default, false, true));
            _opp.Block.sinceBlock = 0.1f;
            Rpc(801, 4000300, "RPCA_DoHit", ME, () => Hit(mine, 2, _opp, false));            // keyed on (4000200, 0, 0)
            _opp.Block.sinceBlock = 0f;
            SeatEvidence.UnkeyedReset(_opp.Block);                                            // a blocked impact after a keyed one
            _opp.Block.sinceBlock = 0.05f;
            Hit(mine, 4, _opp, false, () => Rpc(_opp.View.ViewID, 4000450, "RPCA_SendTakeDamage", ME, () => Damage(_opp)));   // unkeyed, path 1
            PhotonNetwork.ServerTimestamp = 4000550;
            Rpc(_opp.View.ViewID, 4000500, "RPCAO_DoBlock", OPP, () => DoBlock(_opp, true, BlockTrigger.BlockTriggerType.Default, false, true));
            _opp.Block.sinceBlock = 0.125f;
            Rpc(801, 4000600, "RPCA_DoHit", ME, () => Hit(mine, 5, _opp, false));            // keyed again on (4000500, 0, 0)
            DoBlock(_opp, false, BlockTrigger.BlockTriggerType.Default, false, true);         // a window neither path keys
            _opp.Block.sinceBlock = 0.3f;
            Rpc(801, 4000700, "RPCA_DoHit", ME, () => Hit(mine, 6, _opp, false));            // unkeyed again
            _opp.Data.block = null;
            Rpc(801, 4000750, "RPCA_DoHit", ME, () => Hit(mine, 7, _opp, false));            // no Block: no state, not decided
            _opp.Data.block = _opp.Block;
            Dispatch(2, 1, ROOM + "_123456_r4");
            string attach;
            var rec = LastRecord(out attach);
            Eq("[[0,4000150,0,0,-1,0,0,-1,0,0],[0,4000180,0,0,70,1,0,-1,0,2],[0,4000300,0,0,100,0,4000200,0,0,1],"
               + "[1,4000450,4,0,50,0,0,-1,0,2],[0,4000600,0,0,125,0,4000500,0,0,1],[0,4000700,0,0,300,0,0,-1,0,2]]",
               Arr(rec, "hit_sent"), "hit_sent: none, unkeyed (first reset), keyed, unkeyed (path 1), keyed, unkeyed (window)");
            Eq("[5,1]", Arr(rec, "dec"), "dec: the five path-0 decisions on a copy with a Block");
            Eq("[1,0]", Arr(rec, "unpair"), "unpair: the window neither path keys");
            B7Holds(rec);
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
            // the quit hook while a battle is live in this frame (F3): the
            // capture, then the flush (no later frame comes)
            GameManager.instance.battleOngoing = true;
            SeatEvidence.Dispatch(SEAT, OTHER, ROOM + "_123456_r4", 3, 1, true);
            SeatEvidence.FlushOnQuit();
            GameManager.instance.battleOngoing = false;
            Eq(0, ApiClient.Posts.Count, "nothing sent while closing");
            Eq(false, (bool)Field("_loaded"), "no queue load on the quitting path");
            Check(!File.Exists(QueueFile()) && !File.Exists(QueueFile() + ".tmp"), "no queue write on the quitting path");
            var spool = SpoolFiles();
            Eq(1, spool.Length, "the record in its own closing file");
            var sc = SeatEvidenceCore.ParseQueue(File.ReadAllText(spool[0]), false);
            Check(sc.Whole && sc.Items.Count == 1, "the closing file is whole");
            Eq(0, sc.Items[0].Attempts, "no attempt counted on the quitting path");
            string body = sc.Items[0].Body;
            var env = JsonDocument.Parse(body).RootElement;
            Eq("closing", JsonDocument.Parse(env.GetProperty("record").GetString()).RootElement.GetProperty("end").GetString(), "end kind closing");
            // the next launch: a fresh in-memory queue, the api up with a session;
            // its first load, outside combat, moves the closing file into the queue
            NextLaunch();
            ApiUp();
            SeatEvidence.Tick();
            Eq(0, SpoolFiles().Length, "the closing file removed once the queue holds it");
            Eq(1, QueueLines().Length, "moved into the queue file");
            Eq(body, BodyOf(QueueLines()[0]), "its bytes unchanged");
            SetField("_nextPumpMs", 0L);
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
            // F4: the collectors are taken by reference and replaced, nothing aggregated
            var cap = ((System.Collections.IList)Field("_captures"))[0];
            Func<string, object> cf = n => cap.GetType().GetField(n, BindingFlags.NonPublic | BindingFlags.Instance).GetValue(cap);
            Eq(false, (bool)cf("Aggregated"), "nothing aggregated inside the dispatch");
            Check(cf("HitRecv") != null && !ReferenceEquals(cf("HitRecv"), Field("_hitRecv")), "the event list taken and a fresh one handed over");
            Check(cf("Samples") != null && !ReferenceEquals(cf("Samples"), Field("_samples")), "the sample log taken and a fresh one handed over");
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

        /// <summary>F6: the pre-send write decides the send. No copy holds the
        /// spent attempt (ABSENT): nothing leaves and no recoverable attempt
        /// exists. The attempt is whole only in the temporary copy (IN_TEMP):
        /// the request leaves, and the next load recovers that attempt.</summary>
        private static void SendStage()
        {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            WriteQueue(new List<SeatEvidenceCore.Pending> { new SeatEvidenceCore.Pending { Route = "e", Body = "{\"x\":1}", FirstUnix = now } }, 5);
            ApiUp();
            string tmp = QueueFile() + ".tmp";
            // ABSENT: the temporary copy cannot be created (a directory stands in its place)
            Directory.CreateDirectory(tmp);
            SendOnce();
            Eq(0, ApiClient.Posts.Count, "nothing left when no copy holds the spent attempt");
            Eq("0", Fields(QueueLines()[0])[2], "the file holds no spent attempt");
            Eq(0, Attempts((System.Collections.IList)Field("_queue"), 0), "memory holds no spent attempt");
            Directory.Delete(tmp);
            // IN_TEMP: the temporary copy is written, the primary cannot be replaced
            SetField("_inFlight", false);
            string atSend = null;
            using (new FileStream(QueueFile(), FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                ApiClient.OnSend = () => { atSend = File.ReadAllText(tmp); };
                ApiClient.AnswerOk = false;
                ApiClient.Answer = "Cannot resolve destination host";
                SendOnce();
                ApiClient.OnSend = null;
            }
            Eq(1, ApiClient.Posts.Count, "sent: the spent attempt is whole in the temporary copy");
            var t = SeatEvidenceCore.ParseQueue(atSend ?? "", false);
            Check(t.Whole && t.Items.Count == 1 && t.Items[0].Attempts == 1, "the temporary copy held attempt 1 when the bytes left");
            NextLaunch();
            SeatEvidence.Tick();
            var q = (System.Collections.IList)Field("_queue");
            Eq(1, q.Count, "one request after the restart");
            Check(Attempts(q, 0) >= 1, "the attempt recovered from the temporary copy");
        }

        /// <summary>F8: after a write that did not replace the primary, the
        /// next writer merges the newest whole copy first: a record whose
        /// write reached only the temporary copy is kept by an unrelated
        /// writer's write, and its own retry does not add it twice.</summary>
        private static void StaleMerge()
        {
            WriteQueue(new List<SeatEvidenceCore.Pending>(), 1);
            SeatEvidence.BeginGame(true, true);
            using (new FileStream(QueueFile(), FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                Dispatch(2, 1, ROOM + "_123456_r3");
            }
            Eq(0, Logged("record queued"), "not reported queued: the primary was not replaced");
            Eq(true, (bool)Field("_stale"), "memory marked stale");
            Eq(0, ((System.Collections.IList)Field("_queue")).Count, "memory unchanged");
            // an unrelated writer, before the record's own retry
            SeatEvidence.NoteCompat("not_run", new string[0]);
            SeatEvidence.CompatTick();
            Eq(1, RouteCount("c"), "the other writer's request written");
            Eq(1, RecordCount(), "and the record from the temporary copy kept");
            SetField("_nextCaptureTryMs", 0L);
            SeatEvidence.Tick();
            Eq(1, Logged("record queued"), "the retry reports it queued");
            Eq(1, RecordCount(), "not added twice");
            Eq(1, RouteCount("c"), "the other request still there");
        }

        // -- fix pass 3, F8: whole-generation recovery and exact-presence spool deletion --

        private static SeatEvidenceCore.Pending P(string route, string body, long first)
        {
            return new SeatEvidenceCore.Pending { Route = route, Body = body, FirstUnix = first };
        }

        private static int BodyCount(string body)
        {
            int n = 0;
            foreach (var l in QueueLines()) if (BodyOf(l) == body) n++;
            return n;
        }

        /// <summary>A full queue (QUEUE_CAP requests) on disk as generation 1.</summary>
        private static List<SeatEvidenceCore.Pending> FullQueue(long now, string tag)
        {
            var l = new List<SeatEvidenceCore.Pending>();
            for (int i = 0; i < 64; i++) l.Add(P("k", "{\"" + tag + "\":" + i.ToString(CultureInfo.InvariantCulture) + "}", now));
            return l;
        }

        /// <summary>F8: a request settled by a write that reached only the
        /// temporary copy is not brought back by the next writer: the newest
        /// whole generation's removal survives.</summary>
        private static void StaleRemoval()
        {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            var gone = P("e", "{\"settled\":1}", now - SeatEvidenceCore.EXPIRY_S - 10);
            var kept = P("k", "{\"kept\":1}", now);
            WriteQueue(new List<SeatEvidenceCore.Pending> { gone, kept }, 1);
            ApiUp();
            // the pump settles the expired request; the primary cannot be replaced
            using (new FileStream(QueueFile(), FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                SendOnce();
            }
            Eq(0, ApiClient.Posts.Count, "an expired request is settled, not sent");
            var t = SeatEvidenceCore.ParseQueue(File.ReadAllText(QueueFile() + ".tmp"), false);
            Check(t.Whole && t.Items.Count == 1 && t.Items[0].Body == kept.Body, "the temporary copy holds the removal");
            Eq(true, (bool)Field("_stale"), "memory marked stale");
            Eq(2, ((System.Collections.IList)Field("_queue")).Count, "memory still holds the settled request");
            // an unrelated writer, with no session (nothing is sent)
            ApiClient.Base = "";
            SeatEvidence.BeginGame(true, true);
            Dispatch(2, 1, ROOM + "_123456_r3");
            Eq(1, Logged("record queued"), "the record queued");
            Eq(0, BodyCount(gone.Body), "the settled request is not brought back");
            Eq(1, BodyCount(kept.Body), "the other request kept");
            Eq(2, QueueLines().Length, "the kept request and the record");
        }

        /// <summary>F8: at a full queue, a request the newest whole generation
        /// added (its write reached only the temporary copy) survives the next
        /// writer, and the request that generation evicted stays evicted.</summary>
        private static void StaleAdditionAtCap()
        {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            var full = FullQueue(now, "q");
            WriteQueue(full, 1);
            // memory as the launch loaded generation 1
            var mem = (System.Collections.IList)Field("_queue");
            foreach (var p in full) mem.Add(p.Clone());
            SetField("_loaded", true); SetField("_spoolChecked", true); SetField("_gen", 1L);
            // generation 2, whole only in the temporary copy: the oldest evicted, one added
            var gen2 = new List<SeatEvidenceCore.Pending>(full);
            gen2.RemoveAt(0);
            var added = P("k", "{\"added\":1}", now);
            gen2.Add(added);
            WriteQueue(gen2, 2, QueueFile() + ".tmp");
            SetField("_stale", true);
            SeatEvidence.BeginGame(true, true);
            Dispatch(2, 1, ROOM + "_123456_r3");
            Eq(1, Logged("record queued"), "the record queued");
            Eq(64, QueueLines().Length, "the queue at its cap");
            Eq(1, BodyCount(added.Body), "the addition kept at the cap");
            Eq(0, BodyCount(full[0].Body), "the eviction kept");
            Eq(0, BodyCount(full[1].Body), "the record evicted the next oldest");
            Eq(1, RecordCount(), "the record in the file");
        }

        /// <summary>F8: a closing record at a full queue is admitted (the
        /// oldest queued request evicted, as Enqueue does) and its file is
        /// deleted only once the saved queue holds it.</summary>
        private static void ClosingAtCap()
        {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            var full = FullQueue(now, "q");
            WriteQueue(full, 1);
            Check(SeatEvidence.SpoolClosing("e", "{\"closing\":1}"), "the closing file written");
            NextLaunch();
            ApiUp();
            SeatEvidence.Tick();
            Eq(0, SpoolFiles().Length, "the closing file removed once the queue holds it");
            Eq(64, QueueLines().Length, "the queue at its cap");
            Eq(1, BodyCount("{\"closing\":1}"), "the closing record in the queue");
            Eq(0, BodyCount(full[0].Body), "the oldest evicted for it");
            Eq(1, Logged("oldest queued request(s) dropped for closing records"), "the eviction logged");
        }

        /// <summary>Identity-clock fix pass 2: the quit flush is POSITIVE. A
        /// game live in this frame reaches the quit handler; the identity
        /// flush (IdentityClockCore.FlushCaptures, the loop FlushOnQuit runs,
        /// handed the real SeatEvidence.SpoolClosing under route "i" exactly as
        /// FlushOnQuit hands it) writes ONE capture to the closing file, never
        /// the queue, and logs it kept plus one summary; the next launch's first
        /// load promotes that file into the queue under route "i", bytes unchanged.</summary>
        private static void IdentityClosingNextBoot()
        {
            const string ENV = "{\"contract\":2,\"record\":\"identity-quit\",\"sig\":\"00\"}";
            GameManager.instance.battleOngoing = true;      // the quit hook while a battle is live
            var caps = new List<string> { "game-at-quit" };
            IdentityClockCore.EnvBuilder<string> build = (string c, out string text) => { text = "record-of-" + c; return ENV; };
            int kept = IdentityClockCore.FlushCaptures(caps, 4, build, env => SeatEvidence.SpoolClosing("i", env),
                (c, t) => t.Length + " bytes", s => Plugin.Log.LogInfo("[IDENTITY-CLOCK]" + s),
                s => Plugin.Log.LogWarning("[IDENTITY-CLOCK]" + s), () => { });
            GameManager.instance.battleOngoing = false;
            Eq(1, kept, "one capture kept");
            Eq(0, caps.Count, "the capture taken");
            Eq(1, Logged("record kept for the next launch: " + "record-of-game-at-quit".Length + " bytes"), "the kept line");
            Eq(1, Logged("quit flush ran: 1 capture(s), 1 kept for the next launch"), "the summary line");
            Eq(0, ApiClient.Posts.Count, "nothing sent while closing");
            Eq(false, (bool)Field("_loaded"), "no queue load on the quitting path");
            Check(!File.Exists(QueueFile()) && !File.Exists(QueueFile() + ".tmp"), "no queue write on the quitting path");
            var spool = SpoolFiles();
            Eq(1, spool.Length, "the capture in its own closing file");
            var sc = SeatEvidenceCore.ParseQueue(File.ReadAllText(spool[0]), false);
            Check(sc.Whole && sc.Items.Count == 1, "the closing file is whole");
            Eq("i", sc.Items[0].Route, "route i");
            Eq(ENV, sc.Items[0].Body, "the envelope in the closing file");
            NextLaunch();
            ApiUp();
            SeatEvidence.Tick();
            Eq(0, SpoolFiles().Length, "the closing file removed once the queue holds it");
            Eq(1, RouteCount("i"), "promoted into the queue under route i");
            Eq(1, BodyCount(ENV), "its bytes unchanged");
        }

#if IC_REAL_EVIDENCE
        /// <summary>Identity-clock fix pass 3 (QF1): the PRODUCTION capture and
        /// quit flush, through the REAL plugin/IdentityClockEvidence.cs. A ranked
        /// 1v1 game opens (BeginGame, as GameStateWatcher calls it at game
        /// start); the quit-time cut captures it while a battle is live
        /// (Dispatch, with the arguments SeatEvidenceCut passes); the production
        /// FlushOnQuit (the call the registered quit handler makes; its order
        /// in the handler is the harness's quit wiring check) runs BuildAtQuit
        /// (the game-over census, then the signed envelope) and the real
        /// SeatEvidence.SpoolClosing under route "i". Required: one envelope of
        /// THIS capture in the closing file, never the queue, signed over its
        /// record; the next launch promotes it under route "i", bytes unchanged.</summary>
        private static void IdentityProductionQuitFlush()
        {
            string attach = ROOM + "_123456_r7";
            GameStateWatcher.T0 = 1234567; GameStateWatcher.T0FromToken = false;
            BepInEx.Bootstrap.Chainloader.PluginInfos[Plugin.ModId] = new BepInEx.PluginInfo();
            IdentityClockEvidence.BeginGame(true, true);
            GameManager.instance.battleOngoing = true;          // the quit while a battle is live
            IdentityClockEvidence.Dispatch(SEAT, OTHER, attach, true);
            IdentityClockEvidence.FlushOnQuit();
            GameManager.instance.battleOngoing = false;
            Eq(1, Logged("quit flush ran: 1 capture(s), 1 kept for the next launch"), "the summary line");
            Eq(1, Logged("record kept for the next launch"), "the kept line");
            Eq(0, ApiClient.Posts.Count, "nothing sent while closing");
            Check(!File.Exists(QueueFile()) && !File.Exists(QueueFile() + ".tmp"), "no queue write on the quitting path");
            var spool = SpoolFiles();
            Eq(1, spool.Length, "the capture in its own closing file");
            var sc = SeatEvidenceCore.ParseQueue(File.ReadAllText(spool[0]), false);
            Check(sc.Whole && sc.Items.Count == 1, "the closing file is whole");
            Eq("i", sc.Items[0].Route, "route i");
            string env = sc.Items[0].Body;
            using (var d = JsonDocument.Parse(env))
            {
                var r = d.RootElement;
                Eq(2, r.GetProperty("contract").GetInt32(), "contract 2");
                Eq(SEAT, r.GetProperty("seat_steam_id").GetString(), "this seat");
                Eq(OTHER, r.GetProperty("other_steam_id").GetString(), "the other seat");
                Eq(attach, r.GetProperty("attach_key").GetString(), "the captured game's attach key");
                string rec = r.GetProperty("record").GetString();
                Check(rec.StartsWith("{\"schema\":1,\"consts\":1,\"t0\":1234567,", StringComparison.Ordinal),
                      "the record of this capture (t0 from its game start): " + rec.Substring(0, Math.Min(80, rec.Length)));
                string stable = SeatEvidence.StableOf(attach);
                string sig = ApiClient.SeatEvidenceSig(IdentityClockCore.Canonical(SEAT, OTHER, stable, attach, rec));
                Eq(sig, r.GetProperty("sig").GetString(), "signed over this record");
            }
            NextLaunch();
            ApiUp();
            SeatEvidence.Tick();
            Eq(0, SpoolFiles().Length, "the closing file removed once the queue holds it");
            Eq(1, RouteCount("i"), "promoted into the queue under route i");
            Eq(1, BodyCount(env), "its bytes unchanged");
        }
#endif

        /// <summary>F8: a closing file whose exact requests are not all in the
        /// queue the write saved (65 in one file, one past the cap) is kept
        /// for the next launch, and this launch's later pass (17 files: two
        /// passes) does not admit it again, so it never evicts the closing
        /// records whose files were already deleted.</summary>
        private static void ClosingKeptUnlessHeld()
        {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            var many = FullQueue(now, "c");
            many.Add(P("e", "{\"c\":64}", now));
            string file = Path.Combine(BepInEx.Paths.ConfigPath, "CompetitiveRounds.seat-evidence.closing-0000000000000000001-0001.jsonl");
            WriteQueue(many, 1, file);
            for (int i = 0; i < 16; i++)
                Check(SeatEvidence.SpoolClosing("e", "{\"s\":" + i.ToString(CultureInfo.InvariantCulture) + "}"), "closing file " + i);
            NextLaunch();
            ApiUp();
            SeatEvidence.Tick();
            Eq(2, Logged("closing file(s) moved"), "two passes: 16 files, then the 17th");
            Eq(1, Logged("15 closing file(s) moved"), "the first pass moved the 15 singles it held");
            Eq(1, Logged(" 1 closing file(s) moved"), "the second pass moved the last single");
            Eq(64, QueueLines().Length, "the queue at its cap");
            Eq(0, BodyCount(many[0].Body), "a request of the big file not in the saved queue");
            Check(File.Exists(file), "the big file kept: not every request it holds was saved");
            Eq(1, SpoolFiles().Length, "only the big file left");
            for (int i = 0; i < 16; i++)
                Eq(1, BodyCount("{\"s\":" + i.ToString(CultureInfo.InvariantCulture) + "}"), "closing record " + i + " in the queue");
        }

        /// <summary>Fix pass 4, F8: a closing file whose text a write cut off.</summary>
        private static string ClosingPath() { return Path.Combine(BepInEx.Paths.ConfigPath, "CompetitiveRounds.seat-evidence.closing-0000000000000000001-0001.jsonl"); }

        /// <summary>Fix pass 4, F8: the promotion, then an unrelated successful
        /// save, then the next launch: the file's parsable requests are in the
        /// saved queue and the file itself survives unchanged (set aside, out
        /// of the listing), never deleted, never admitted twice.</summary>
        private static void ClosingNotWhole(string text, string what)
        {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            var q = P("k", "{\"q\":1}", now);
            WriteQueue(new List<SeatEvidenceCore.Pending> { q }, 1);
            string file = ClosingPath();
            File.WriteAllText(file, text);
            var parsed = SeatEvidenceCore.ParseQueue(text, false);
            Check(!parsed.Whole && parsed.Items.Count == 2, what + ": not whole, two parsable requests");
            NextLaunch();
            ApiUp();
            SeatEvidence.Tick();
            Eq(1, BodyCount("{\"u\":1}"), what + ": the first parsable request in the saved queue");
            Eq(1, BodyCount("{\"u\":2}"), what + ": the second parsable request in the saved queue");
            Eq(1, BodyCount(q.Body), what + ": the queued request kept");
            Check(File.Exists(file + ".unverified") && File.ReadAllText(file + ".unverified") == text, what + ": the file kept unchanged");
            Eq(0, SpoolFiles().Length, what + ": out of the promotion's listing");
            Eq(1, Logged("closing file(s) without a verified trailer"), what + ": set aside, logged");
            // an unrelated successful save
            SeatEvidence.BeginGame(true, true);
            Dispatch(2, 1, ROOM + "_123456_r3");
            Eq(1, Logged("record queued"), what + ": the unrelated record queued");
            Eq(1, RecordCount() - 2, what + ": the record saved beside the two closing requests");
            Eq(1, BodyCount("{\"u\":1}"), what + ": still saved after the unrelated save");
            Eq(1, BodyCount("{\"u\":2}"), what + ": still saved after the unrelated save");
            Check(File.Exists(file + ".unverified") && File.ReadAllText(file + ".unverified") == text, what + ": the file survives the unrelated save");
            // the next launch lists nothing to admit again
            NextLaunch();
            SeatEvidence.Tick();
            Eq(0, SpoolFiles().Length, what + ": nothing listed at the next launch");
            Check(BodyCount("{\"u\":1}") <= 1 && BodyCount("{\"u\":2}") <= 1, what + ": never admitted twice");
        }

        private static List<SeatEvidenceCore.Pending> TwoClosing()
        {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            return new List<SeatEvidenceCore.Pending> { P("e", "{\"u\":1}", now), P("e", "{\"u\":2}", now) };
        }

        /// <summary>Fix pass 4, F8: parsable lines, no trailer, a torn last line.</summary>
        private static void ClosingNoTrailer()
        {
            string t = SeatEvidenceCore.QueueText(TwoClosing(), 1);
            string body = t.Substring(0, t.LastIndexOf(SeatEvidenceCore.QUEUE_TRAILER, StringComparison.Ordinal));
            // a third request's line, cut after its second field (where a write stopped)
            var third = new List<SeatEvidenceCore.Pending> { P("e", "{\"u\":3}", DateTimeOffset.UtcNow.ToUnixTimeSeconds()) };
            string l3 = SeatEvidenceCore.QueueText(third, 1);
            string torn = l3.Substring(0, l3.IndexOf('\t', l3.IndexOf('\t') + 1));
            Check(SeatEvidenceCore.ParseLine(torn) == null, "the torn line does not parse");
            ClosingNotWhole(body + torn, "no trailer");
        }

        /// <summary>Merge pass 6, item 2: a stand-in server that answers every
        /// evidence route (record "e", card record "k", compat outcome "c") with
        /// not-found, with a refusal and with no answer, against a queue at its
        /// cap, pumped three times as often as it holds requests. Required:
        /// not-found sends each request once per launch and keeps it; a game
        /// at the cap adds one record (the oldest evicted) and one send; a
        /// refusal sends each once and settles it; no answer sends each once
        /// per next-eligible time and MAX_ATTEMPTS times in all; nothing goes
        /// while a battle is live; closing files are admitted at most SPOOL_CAP
        /// per pass and the queue never holds more than QUEUE_CAP.</summary>
        private static void StandinBounds()
        {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            const BindingFlags S = BindingFlags.NonPublic | BindingFlags.Static;
            int cap = (int)typeof(SeatEvidence).GetField("QUEUE_CAP", S).GetRawConstantValue();
            int spoolCap = (int)typeof(SeatEvidence).GetField("SPOOL_CAP", S).GetRawConstantValue();
            Eq(64, cap, "the queue cap this case fills");
            Func<int, List<SeatEvidenceCore.Pending>> full = tag =>
            {
                var l = new List<SeatEvidenceCore.Pending>();
                for (int i = 0; i < cap; i++)
                    l.Add(new SeatEvidenceCore.Pending { Route = i % 8 == 7 ? "c" : (i % 2 == 0 ? "e" : "k"),
                                                         Body = "{\"t\":" + tag + ",\"n\":" + i + "}", FirstUnix = now - 10 });
                return l;
            };
            Action pumpMany = () => { for (int i = 0; i < 3 * cap; i++) SendOnce(); };
            ApiUp();
            ApiClient.AnswerOk = false;

            // 1. not-found on every route
            ApiClient.Answer = "HTTP 404: {\"detail\":\"Not Found\"}";
            WriteQueue(full(1), 10);
            NextLaunch();
            pumpMany();
            Eq(cap, ApiClient.Posts.Count, "not-found: each queued request once in this launch");
            Eq(cap, QueueLines().Length, "not-found: every request kept for the next launch");
            NextLaunch();
            pumpMany();
            Eq(2 * cap, ApiClient.Posts.Count, "not-found: each once more in the next launch, no more");
            SeatEvidence.BeginGame(true, true);
            Dispatch(2, 1, ROOM + "_123456_r3");
            Eq(cap, QueueLines().Length, "a game at the cap: the queue stays at its cap");
            pumpMany();
            Eq(2 * cap + 1, ApiClient.Posts.Count, "not-found: the game's record once in this launch");
            NextLaunch();
            GameManager.instance.battleOngoing = true;
            pumpMany();
            Eq(2 * cap + 1, ApiClient.Posts.Count, "nothing is sent while a battle is live");
            GameManager.instance.battleOngoing = false;

            // 2. a refusal on every route: each once, then settled
            ApiClient.Posts.Clear();
            ApiClient.Answer = "HTTP 400: {\"detail\":\"malformed\"}";
            WriteQueue(full(2), 20);
            NextLaunch();
            pumpMany();
            Eq(cap, ApiClient.Posts.Count, "refusal: each request once");
            Eq(0, QueueLines().Length, "refusal: every request settled");
            NextLaunch();
            pumpMany();
            Eq(cap, ApiClient.Posts.Count, "refusal: nothing in the next launch");

            // 3. no answer: once per next-eligible time, MAX_ATTEMPTS in all
            ApiClient.Posts.Clear();
            ApiClient.Answer = "Cannot resolve destination host";
            WriteQueue(full(3), 30);
            NextLaunch();
            pumpMany();
            Eq(cap, ApiClient.Posts.Count, "no answer: each once until its next-eligible time");
            for (int round = 0; round < SeatEvidenceCore.MAX_ATTEMPTS + 2; round++)
            {
                NextLaunch();
                SendOnce();     // the load; nothing is due yet
                foreach (SeatEvidenceCore.Pending p in (System.Collections.IList)Field("_queue")) p.NotBeforeUnix = 0;
                pumpMany();
            }
            Eq(cap * SeatEvidenceCore.MAX_ATTEMPTS, ApiClient.Posts.Count, "no answer: MAX_ATTEMPTS transmissions per request in all");
            Eq(0, QueueLines().Length, "no answer: every request settled as spent");

            // 4. closing files on a full queue: SPOOL_CAP per pass, the queue at its cap
            ApiClient.Posts.Clear();
            ApiClient.Answer = "HTTP 404: {\"detail\":\"Not Found\"}";
            WriteQueue(full(4), 40);
            NextLaunch();
            for (int i = 0; i < spoolCap + 4; i++) Check(SeatEvidence.SpoolClosing("e", "{\"closing\":" + i + "}"), "closing file written");
            Eq(spoolCap + 4, SpoolFiles().Length, "the closing files");
            var load = typeof(SeatEvidence).GetMethod("Load", S);
            Check((bool)load.Invoke(null, null), "the first load of the launch");
            Eq(4, SpoolFiles().Length, "one pass admits SPOOL_CAP closing files");
            Eq(cap, QueueLines().Length, "the queue stays at its cap");
            Check((bool)load.Invoke(null, null), "the next load");
            Eq(0, SpoolFiles().Length, "the next pass admits the rest");
            Eq(cap, QueueLines().Length, "the queue still at its cap");
            SendOnce();
            Eq(1, ApiClient.Posts.Count, "one send per pump");
        }

        /// <summary>Merge pass 7, SE-L1, against an ASYNCHRONOUS server: request
        /// A leaves and gets no answer within FLIGHT_LIMIT_MS, so the slot is
        /// freed and B leaves; then A's answer arrives while B is in flight, as
        /// a 2xx, a refusal and a not-found in turn. A's answer is dropped and
        /// counted and B is untouched (still in flight, no answer stored, its
        /// queue line unchanged) until B's own answer settles B alone. A is
        /// never POSTed twice in one launch, even once due again, and in the
        /// next launch it leaves once more and its own answer decides it.</summary>
        private static void LateAnswerIdentity()
        {
            const BindingFlags S = BindingFlags.NonPublic | BindingFlags.Static;
            long limit = (long)typeof(SeatEvidence).GetField("FLIGHT_LIMIT_MS", S).GetRawConstantValue();
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            string[] names = { "2xx", "refusal", "not-found" };
            bool[] oks = { true, false, false };
            string[] texts = { "{\"status\":\"recorded\"}", "HTTP 400: {\"detail\":\"malformed\"}", "HTTP 404: {\"detail\":\"Not Found\"}" };
            Func<string, string> lineOf = body =>
            {
                foreach (var l in QueueLines()) if (BodyOf(l) == body) return l;
                return null;
            };
            ApiUp();
            int dropped = 0;
            for (int k = 0; k < names.Length; k++)
            {
                string n = names[k] + ": ";
                ApiClient.Posts.Clear();
                ApiClient.Held.Clear();
                ApiClient.Deferred = true;
                string bodyA = "{\"late\":\"" + names[k] + "\",\"req\":\"A\"}";
                string bodyB = "{\"late\":\"" + names[k] + "\",\"req\":\"B\"}";
                WriteQueue(new List<SeatEvidenceCore.Pending>
                {
                    new SeatEvidenceCore.Pending { Route = "e", Body = bodyA, FirstUnix = now - 10 },
                    new SeatEvidenceCore.Pending { Route = "e", Body = bodyB, FirstUnix = now - 10 },
                }, 1000 * (k + 1));
                NextLaunch();

                SendOnce();
                Eq(1, ApiClient.Posts.Count, n + "A left");
                Eq(bodyA, ApiClient.Posts[0].Value, n + "the first request out is A");
                Eq(true, (bool)Field("_inFlight"), n + "A in flight, unanswered");

                // no answer within the limit: A abandoned, B leaves on the same tick
                SetField("_flightAtMs", SeatEvidence.SwMs - limit - 1000);
                SendOnce();
                Eq(2, ApiClient.Posts.Count, n + "B left after A was abandoned");
                Eq(bodyB, ApiClient.Posts[1].Value, n + "the second request out is B");
                string aLine = lineOf(bodyA), bLine = lineOf(bodyB);
                Check(aLine != null && bLine != null, n + "both requests queued while B is in flight");

                // A's late answer arrives while B is in flight
                ApiClient.Deliver(0, oks[k], texts[k]);
                dropped++;
                Eq(dropped, (int)Field("_lateAnswersDropped"), n + "A's late answer dropped and counted");
                Eq(true, (bool)Field("_inFlight"), n + "B still in flight");
                Eq(bodyB, (string)Field("_flightBody"), n + "the flight is still B's");
                Eq(false, (bool)Field("_answered"), n + "no answer stored for B");
                SendOnce();
                Eq(2, ApiClient.Posts.Count, n + "nothing else left");
                Eq(2, QueueLines().Length, n + "neither request settled by A's answer");
                Eq(aLine, lineOf(bodyA), n + "A's queue line unchanged by its late answer");
                Eq(bLine, lineOf(bodyB), n + "B's queue line untouched by A's answer");

                // B's own answer settles B alone
                ApiClient.Deliver(1, true, "{\"status\":\"recorded\"}");
                SendOnce();
                Eq(1, QueueLines().Length, n + "B settled by its own answer");
                Eq(aLine, lineOf(bodyA), n + "A kept as it was");

                // the bound, unconditionally: A is due again and still not POSTed in this launch
                foreach (SeatEvidenceCore.Pending p in (System.Collections.IList)Field("_queue")) p.NotBeforeUnix = 0;
                for (int i = 0; i < 10; i++) SendOnce();
                Eq(2, ApiClient.Posts.Count, n + "at most one POST per queued request in this launch");

                // the next launch: A leaves once more, under a new flight, and its own answer decides it
                ApiClient.Deferred = false;
                ApiClient.AnswerOk = oks[k];
                ApiClient.Answer = texts[k];
                NextLaunch();
                // the backoff BeforeSend persisted for A's first send is on disk;
                // load the next launch's queue and make A due, so the count below
                // measures the per-launch bound, not the backoff
                Check((bool)typeof(SeatEvidence).GetMethod("Load", S).Invoke(null, null), n + "the next launch loads the queue");
                foreach (SeatEvidenceCore.Pending p in (System.Collections.IList)Field("_queue")) p.NotBeforeUnix = 0;
                for (int i = 0; i < 10; i++) SendOnce();
                Eq(3, ApiClient.Posts.Count, n + "A once in the next launch, no more");
                Eq(bodyA, ApiClient.Posts[2].Value, n + "the next launch's request is A");
                Eq(k == 2 ? 1 : 0, QueueLines().Length, n + "A's own answer decides A");
                Eq(dropped, (int)Field("_lateAnswersDropped"), n + "no answer dropped in the next launch");
            }
            ApiClient.Deferred = false;
            Check(Logged("that is no longer in flight was dropped") == 3, "one log line per dropped answer");
            Check(Logged("held for the next launch") >= 3, "one log line per abandoned flight");
        }

        /// <summary>Fix pass 4, F8: parsable lines under a trailer that does not verify.</summary>
        private static void ClosingBadTrailer()
        {
            string t = SeatEvidenceCore.QueueText(TwoClosing(), 1);
            int h = t.LastIndexOf('\t') + 1;
            string bad = t.Substring(0, h) + (t[h] == '0' ? '1' : '0') + t.Substring(h + 1);
            ClosingNotWhole(bad, "invalid trailer");
        }

        /// <summary>F4: the opponent sample (a room lookup and a property
        /// enumeration) runs on the tick only while no battle is live; the
        /// round-trip sample is taken in combat too.</summary>
        private static void OpponentSampleOutsideCombat()
        {
            PhotonNetwork.CurrentRoom.Players[OPP].CustomProperties["cr_gstats"] = "10|5|3|2|0|60|144|0|0|0|0|40";
            SeatEvidence.BeginGame(true, true);
            GameManager.instance.battleOngoing = true;
            SeatEvidence.Tick();
            Check(Field("_oppPub") == null, "no opponent sample while combat is live");
            Eq(true, (bool)Field("_oppSampleDue"), "the opponent sample is due");
            Check((long)Field("_rttN") >= 1, "the round-trip sample taken in combat");
            GameManager.instance.battleOngoing = false;
            SeatEvidence.Tick();
            var pub = (long[])Field("_oppPub");
            Check(pub != null && pub[0] == 144, "sampled once no battle is live");
            Eq(false, (bool)Field("_oppSampleDue"), "taken");
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
            { "victim_block_hit", VictimBlockHit }, { "shooter_paths", ShooterPaths }, { "last_reset_states", LastResetStates },
            { "unkeyed_and_nesting", UnkeyedAndNesting }, { "cut_left", CutLeft }, { "cut_guards", CutGuards },
            { "closing_next_boot", ClosingNextBoot }, { "compat_sender", CompatSender }, { "compat_bounds", CompatBounds },
            { "cut_422_kept", Cut422Kept }, { "path1_unstamped", Path1Unstamped },
            { "disabled_seat_records", DisabledSeatRecords }, { "compat_once_per_launch", CompatOncePerLaunch },
            { "attempt_accounting", AttemptAccounting }, { "combat_gate", CombatGate }, { "dispatch_defers", DispatchDefers },
            { "identity_pending", IdentityPending }, { "queue_recovery", QueueRecovery }, { "queue_save_fails", QueueSaveFails },
            { "damage_predicate", DamagePredicate },
            // fix pass 2
            { "send_stage", SendStage }, { "stale_merge", StaleMerge },
            // fix pass 3
            { "stale_removal", StaleRemoval }, { "stale_addition_at_cap", StaleAdditionAtCap },
            { "closing_at_cap", ClosingAtCap }, { "closing_kept_unless_held", ClosingKeptUnlessHeld },
            { "opponent_sample_outside_combat", OpponentSampleOutsideCombat },
            // fix pass 4
            { "closing_no_trailer", ClosingNoTrailer }, { "closing_bad_trailer", ClosingBadTrailer },
            // merge pass 6, item 2
            { "standin_bounds", StandinBounds },
            // merge pass 7, SE-L1
            { "late_answer_identity", LateAnswerIdentity },
            // identity-clock fix pass 2
            { "identity_closing_next_boot", IdentityClosingNextBoot },
#if IC_REAL_EVIDENCE
            // identity-clock fix pass 3 (QF1): the production capture and quit flush
            { "identity_production_quit_flush", IdentityProductionQuitFlush },
#endif
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
