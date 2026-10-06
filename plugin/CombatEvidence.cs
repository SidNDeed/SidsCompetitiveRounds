using HarmonyLib;
using Photon.Pun;
using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;
using C = CompetitiveRounds.SeatEvidenceCore;
using E = CompetitiveRounds.CombatEvidenceCore;
using W = CompetitiveRounds.CombatEvidenceWire;

namespace CompetitiveRounds
{
    /// <summary>Combat evidence (design V2: B1 aim, B2 firing logic, B3 bullet
    /// behaviour, B5 blocks), the game side. Both seats record what they saw;
    /// the server compares; every flag is advisory and decided server-side.
    ///
    /// What the hooks may do (design 11.1): read game state and write numbers
    /// into this class's own fixed arrays. No hook changes a hit, a block, a
    /// push, a gun, an ammunition count, a timer or a time scale; each body is
    /// its own method in try/catch with a fault counter and a cost row; the
    /// patches are void prefixes, postfixes that leave __result alone and
    /// finalizers that return __exception unchanged. Every step whose cost
    /// grows with the game (aim and path arithmetic, line-of-sight casts,
    /// component scans, budgeting, hashing, the queue) runs on the polling
    /// tick, and the build runs only outside combat.
    ///
    /// The client carries no threshold and no judging rule: the cycle labels
    /// are the game's own rule arithmetic the server repeats from the shot
    /// groups, and the histogram edges are measurement constants (consts 1).</summary>
    internal static class CombatEvidence
    {
        internal const string TAG = "[COMBAT-EV]";

        // -- cost rows (design 11.2 order, then the addendum's collectors) ------------------------
        internal const int K1 = 0, K2 = 1, K3 = 2, K4 = 3, K5 = 4, N1 = 5, N2 = 6, N3 = 7, N4 = 8, N5 = 9, N6 = 10, N7 = 11, T = 12;
        /// <summary>The addendum's collectors: P1 the push (HealthHandler.RPCA_SendTakeForce),
        /// D1 the damage message and health change (RPCA_SendTakeDamage), X1 a death
        /// (RPCA_Die, RPCA_Die_Phoenix), S1 the owner's target choice
        /// (BounceEffectRetarget.FindTarget), H1 the hit message's end (RPCA_DoHit
        /// finalizer), E1 the edge bounce's end, RX the reaction sampler on the tick.
        /// The unamended record carries rows 0..12 in `cost`; the A1 record also
        /// carries these seven in `cost_a1`.</summary>
        internal const int P1 = 13, D1 = 14, X1 = 15, S1 = 16, H1 = 17, E1 = 18, RX = 19;
        internal const int COST_ALL = 20;
        private const int COST_CAP = COST_ALL;
        private static readonly long[] _calls = new long[COST_ALL], _ticks = new long[COST_ALL],
                                       _maxTicks = new long[COST_ALL], _faults = new long[COST_ALL];
        private static readonly bool[] _faultLogged = new bool[COST_ALL];
        private static readonly string[] _faultNote = new string[COST_ALL];

        /// <summary>The wire amendment A1 is emitted only when this is set. It stays
        /// false in this build: the server takes A1 in its own amendment pass, and
        /// until then every record is the current layout byte for byte. The
        /// scenario harness sets it to generate the amended fixtures.</summary>
        internal static bool A1Live;

        internal static long Stamp() { return System.Diagnostics.Stopwatch.GetTimestamp(); }

        internal static void Cost(int i, long t0)
        {
            long d = System.Diagnostics.Stopwatch.GetTimestamp() - t0;
            _calls[i]++; _ticks[i] += d; if (d > _maxTicks[i]) _maxTicks[i] = d;
        }

        internal static void Fault(int i, Exception ex)
        {
            _faults[i]++;
            if (!_faultLogged[i]) { _faultLogged[i] = true; _faultNote[i] = ex != null ? ex.GetType().Name : "fault"; }
        }

        private static long Us(long ticks) { return (long)(ticks * 1000000.0 / System.Diagnostics.Stopwatch.Frequency); }

        // -- the game window -----------------------------------------------------------------------

        private static bool _open, _frozen;
        private static long _frozenAtMs;
        private static string _room = "";
        private static int _oppActor, _localActor;
        private static Player _ownP, _oppP;
        private static Game _g;
        /// <summary>The R-section producers whose patches the boot census proved attached (W.CAPS_*).</summary>
        internal static long Producers;

        private static int ServerNow() { try { return PhotonNetwork.ServerTimestamp; } catch { return 0; } }
        private static long SwMs { get { return SeatEvidence.SwMs; } }

        internal static bool Open { get { return _open; } }

        /// <summary>Beside SeatEvidence.BeginGame (GameStateWatcher's start block):
        /// a game with exactly two fighters opens the window; every collector of
        /// the game is allocated here, before combat.</summary>
        internal static void BeginGame(bool oneVOne)
        {
            try
            {
                _open = false; _frozen = false; _g = null;
                CombatEvidencePerf.Contaminated = false;
                for (int i = 0; i < COST_ALL; i++) { _calls[i] = 0; _ticks[i] = 0; _maxTicks[i] = 0; _faults[i] = 0; _faultLogged[i] = false; }
                if (!oneVOne) return;
                try { _room = PhotonNetwork.CurrentRoom != null ? (PhotonNetwork.CurrentRoom.Name ?? "") : ""; } catch { _room = ""; }
                try { _localActor = PhotonNetwork.LocalPlayer != null ? PhotonNetwork.LocalPlayer.ActorNumber : 0; } catch { _localActor = 0; }
                var others = RoomActors.OtherActiveFighters();
                _oppActor = others != null && others.Length == 1 && others[0] != null ? others[0].ActorNumber : 0;
                if (_oppActor == 0 || _localActor == 0) return;
                _ownP = null; _oppP = null;
                ResolvePlayers();
                _g = new Game();
                _open = true;
            }
            catch { _open = false; _g = null; }
        }

        private static void ResolvePlayers()
        {
            var pm = PlayerManager.instance;
            if (pm == null) return;
            if (_ownP == null) _ownP = pm.GetPlayerWithActorID(_localActor);
            if (_oppP == null) _oppP = pm.GetPlayerWithActorID(_oppActor);
        }

        /// <summary>Room exit (beside SeatEvidence.RoomExit): the window stops and
        /// is frozen as it stands, for a dispatch of the same room to take.</summary>
        internal static void RoomExit()
        {
            try
            {
                if (_open)
                {
                    if (_g != null && _g.PointLive) PointEnd(_g, ServerNow());
                    _open = false; _frozen = true; _frozenAtMs = SwMs;
                }
            }
            catch { }
        }

        // -- per-game collectors -------------------------------------------------------------------

        private const int RECENT_CAP = W.RECENT_HITS;
        /// <summary>Rows of each deferred ring one tick works off (component scans, sight casts and path
        /// integration are spread over frames; a ring that fills counts its drops).</summary>
        private const int TICK_ROWS_CAP = 16;
        private const int MASK_BIT_CAP = 8;          // the steering mask's bits (W.STEER_BITS_*)
        internal const int ANCHOR_CAP = 256, RING_CAP = 128, POS_CAP = 64, PING_CAP = 600, TOP_CAP = 32, HT_CAP = 16;
        /// <summary>The received-hit pairing window: a hit message pairs to the oldest
        /// unmatched contact among the last PAIR_CAP contact rows (M6).</summary>
        internal const int PAIR_CAP = 8;
        /// <summary>The gun stat block's width (gun_s).</summary>
        internal const int STAT_CAP = 19;
        /// <summary>Ping samples are binned per millisecond up to PING_BIN_CAP; the
        /// lower median is exact below it (no sort in combat, M8).</summary>
        internal const int PING_BIN_CAP = 2000;
        /// <summary>Rows a ranked list may hold (the largest list cap of the layout's top lists).</summary>
        private const int ROWS_CAP = TOP_CAP;
        /// <summary>Entries waiting for a later rendered frame (push after-positions, chain frame stamps).</summary>
        internal const int WAIT_CAP = 16;
        /// <summary>Non-alloc line-of-sight buffer (a full buffer is counted, A1 drop `ray_full`).</summary>
        internal const int RAY_CAP = 8;
        /// <summary>Reaction sampler period (ms) and the angular radius floor's distance guard.</summary>
        internal const int RX_PERIOD_MS = 33;
        /// <summary>The ranked map's out-of-bounds edges (OutOfBoundsHandler.LateUpdate: InverseLerp over
        /// x -35.56..35.56 and y -20..20 of the player's transform; the FFA scale is not a 1v1 path).</summary>
        internal const float OOB_X = 35.56f, OOB_Y = 20f;
        /// <summary>The R-section producers this build carries (W.CAPS_*): a bit reaches a
        /// record only when the boot census proved every patch that section's rows
        /// depend on attached, and no producer of it faulted or met an unkeyed event
        /// in the game. A seat's own bit does not depend on the other seat: the
        /// server pairs two records only when both carry the bit.</summary>
        internal const long PRODUCERS = W.CAPS_PUSH | W.CAPS_VCHG | W.CAPS_CHAIN | W.CAPS_DEATH;

        /// <summary>One gun copy's live state on this seat (own main gun or the
        /// other seat's main gun as this seat holds it).</summary>
        private sealed class GunState
        {
            internal readonly E.GunAccount Acct;
            internal Gun G; internal GunAmmo A;
            internal int LastAmmo = int.MinValue, LastMax;
            internal long LastEvtStamp, LastEvtSw; internal double LastEvtGame; internal bool HasEvt;
            internal bool RlOpen; internal float RlCounter; internal int RlStamp; internal long RlSw;
            // B2 emissions
            internal bool InAttack, AttackFirstSeen; internal int AttackEmits, SavedEmits;
            internal bool FirstPending; internal long Rep, Since, Fl, SavedSince, SavedFl;
            internal bool MsgPending; internal int MsgStamp;
            // per point intervals
            internal long Gmin = -1, CexpMin = -1, Vmax, Vexp, Refreshes;
            internal bool HasVolley; internal int LastVolley;
            internal readonly int[] Ring = new int[RING_CAP]; internal int RingHead, RingN;
            internal readonly int[] Win = new int[RING_CAP]; internal int WinHead, WinN;
            /// <summary>The last stat block emitted (HasStat) and the scratch the next one is read into.</summary>
            internal readonly long[] Stat = new long[STAT_CAP], StatNew = new long[STAT_CAP]; internal bool HasStat;
            internal GunState(bool own) { Acct = new E.GunAccount(own); }
        }

        private sealed class Game
        {
            internal readonly GunState Own = new GunState(true);
            internal readonly GunState Opp = new GunState(false);
            internal readonly E.FixedRows GunS = new E.FixedRows("gun_s");
            internal readonly E.FixedRows GunO = new E.FixedRows("gun_o");
            internal readonly E.FixedRows IvlS = new E.FixedRows("ivl_s");
            internal readonly E.FixedRows IvlO = new E.FixedRows("ivl_o");
            internal readonly E.FixedRows Tb = new E.FixedRows("tb");
            internal readonly E.FixedRows P3tb = new E.FixedRows("p3tb");
            internal readonly E.FixedRows B5s = new E.FixedRows("b5_s");
            internal readonly E.FixedRows B5o = new E.FixedRows("b5_o");
            internal readonly E.FixedRows B5h = new E.FixedRows("b5_h");
            internal readonly E.FixedRows B5c = new E.FixedRows("b5_c");
            internal readonly E.FixedRows B5r = new E.FixedRows("b5_r");
            internal readonly E.AimSet A1s = new E.AimSet(), A1p = new E.AimSet(), A1m = new E.AimSet(), A1n = new E.AimSet();
            internal readonly long[] P3n = new long[7], P3self = new long[10], B5tot = new long[8];
            internal readonly long[] P3dp0 = new long[14], P3an0 = new long[14], P3dp1 = new long[14], P3an1 = new long[14], P3hm = new long[10];
            internal long P3topSeen, P3htSeen;
            internal readonly long[] Top = new long[TOP_CAP * 8]; internal int TopN;
            internal readonly long[] Ht = new long[HT_CAP * 4]; internal int HtN;
            // time base
            internal E.PointClock Pc; internal bool PointLive; internal long BaseChanges, Points; internal float LastBase = -1f;
            internal readonly E.PointClock PcStore = new E.PointClock();
            internal readonly long[] TbRow = new long[12];
            internal readonly E.FrameHist Frames = new E.FrameHist();
            internal int PingN; internal long NextPingMs;
            internal readonly int[] PingBin = new int[PING_BIN_CAP + 1];
            // scratch for the residual drain and the ranked lists (no allocation in combat)
            internal readonly long[] ResOut = new long[3], TopEntry = new long[8], HtEntry = new long[4];
            internal readonly RaycastHit2D[] Ray = new RaycastHit2D[RAY_CAP];
            // A1: per-buffer losses and never-trimmed totals
            internal readonly long[] Drop = new long[E.DROP_FIELDS.Length];
            internal readonly long[] A1Tot = new long[E.A1TOT_FIELDS.Length];
            // the addendum's sections (R1 push, R2 velocity changes and bounce selections,
            // R3 the hit chain, R5 deaths), keyed by hit or projectile identity
            internal readonly E.FixedRows PushS = new E.FixedRows("push_s"), PushO = new E.FixedRows("push_o");
            internal readonly E.FixedRows Vchg = new E.FixedRows("vchg"), Bsel = new E.FixedRows("bsel");
            internal readonly E.FixedRows ChS = new E.FixedRows("ch_s"), ChO = new E.FixedRows("ch_o");
            internal readonly E.FixedRows BdS = new E.FixedRows("bd_s"), BdO = new E.FixedRows("bd_o");
            internal readonly E.FixedRows RxS = new E.FixedRows("rx_s"), RxO = new E.FixedRows("rx_o");
            /// <summary>The R-sections a producer fault or an unkeyed event voids for this game (W.CAPS_* bits).</summary>
            internal long Void;
            // hit identity: the victim's received-message ordinal per anchor slot
            internal readonly int[] AMsgCord = new int[ANCHOR_CAP];
            // own projectiles: the decision stamp of the latest own contact on the other player
            internal readonly int[] OwnDec = new int[ANCHOR_CAP]; internal readonly bool[] OwnDecOn = new bool[ANCHOR_CAP];
            // A1 F4: an edge bounce since the slot's anchor
            internal readonly bool[] AEdge = new bool[ANCHOR_CAP];
            // the shooter's scope inside its own RPCA_DoHit on the other player (side 0)
            internal bool ScOn; internal int ScPid, ScSInit, ScCord, ScChRow = -1; internal bool ScPush, ScDmg;
            // the victim's pending received hit (side 1): valid until consumed, replaced or the next tick
            internal bool VcOn; internal int VcPid, VcSInit, VcCord, VcChRow = -1, VcFrame; internal bool VcPush, VcDmg;
            // own projectile velocity before its own hit message, for vchg
            internal bool HvOn; internal float HvX, HvY; internal int HvPid, HvSInit, HvStamp, HvView;
            // own edge bounce velocity before
            internal bool EvOn; internal float EvX, EvY; internal int EvPid, EvSInit, EvStamp;
            // pending bounce selections, per own projectile slot (k = pid & mask)
            internal readonly bool[] BsOn = new bool[ANCHOR_CAP]; internal readonly int[] BsPid = new int[ANCHOR_CAP];
            internal readonly long[] Bs = new long[ANCHOR_CAP * 5];
            // waits for a later rendered frame: kind 0 push after-position (row offset), kind 1 chain t_frame
            internal readonly int[] WKind = new int[WAIT_CAP], WRow = new int[WAIT_CAP], WFrame = new int[WAIT_CAP], WPlayer = new int[WAIT_CAP];
            internal readonly E.FixedRows[] WList = new E.FixedRows[WAIT_CAP];
            internal int WHead, WN;
            // damage: health before the message, per side; last damage source per side (1 OOB, 2 other)
            internal float DmgHpBefore; internal bool DmgOn; internal int DmgRow = -1;
            internal int LastSrcOwn, LastSrcOpp;
            internal int DeathOrdOwn, DeathOrdOpp;
            // recent hits per player (victim side keyed by AMsgCord, shooter side by OwnCord): pid, s_init, cord, stamp
            internal readonly int[] RhOwn = new int[RECENT_CAP * 4], RhOpp = new int[RECENT_CAP * 4];
            internal int RhOwnN, RhOwnHead, RhOppN, RhOppHead;
            // reaction sampler
            internal long RxNextMs; internal bool RxVis = true, RxRun;
            internal int RxRowS = -1, RxRowO = -1; internal long RxOnsetSw; internal int RxOnset;
            // own positions on the shared clock (a1m, a1n)
            internal readonly int[] PosT = new int[POS_CAP]; internal readonly float[] PosX = new float[POS_CAP], PosY = new float[POS_CAP];
            internal int PosHead, PosN;
            // projectile anchors (B3), keyed by PhotonView id
            internal readonly C.CappedMap<int, int> Slot = new C.CappedMap<int, int>(ANCHOR_CAP);
            internal readonly int[] APid = new int[ANCHOR_CAP], ASInit = new int[ANCHOR_CAP], AAge = new int[ANCHOR_CAP], ALastHit = new int[ANCHOR_CAP];
            internal readonly int[] AMask = new int[ANCHOR_CAP], ACord = new int[ANCHOR_CAP], AHomN = new int[ANCHOR_CAP];
            internal readonly bool[] ALive = new bool[ANCHOR_CAP], AHasHit = new bool[ANCHOR_CAP], AHomChecked = new bool[ANCHOR_CAP], AHasPack = new bool[ANCHOR_CAP];
            internal readonly float[] AHomForce = new float[ANCHOR_CAP], AHomAmount = new float[ANCHOR_CAP], APvx = new float[ANCHOR_CAP], APvy = new float[ANCHOR_CAP];
            internal readonly long[] AHomMax = new long[ANCHOR_CAP];
            internal readonly GameObject[] AObj = new GameObject[ANCHOR_CAP];
            internal int ANext;
            // own projectiles' init stamps (b5_h), direct-mapped by view id
            internal readonly int[] OwnPid = new int[ANCHOR_CAP], OwnSInit = new int[ANCHOR_CAP], OwnCord = new int[ANCHOR_CAP];
            // deferred work for the tick (fixed rings; a full ring counts the drop)
            internal readonly Ring Mask = new Ring(RING_CAP, 2);
            internal readonly Ring Aim = new Ring(RING_CAP, 7);
            internal readonly Ring Res = new Ring(RING_CAP, 21);
            internal readonly Ring Pack = new Ring(RING_CAP * 2, 4);
            internal readonly GameObject[] MaskObj = new GameObject[RING_CAP];
            internal readonly SyncProjectile[] PackObj = new SyncProjectile[RING_CAP * 2];
            /// <summary>Per-anchor: the steering mask was scanned (A1: an unscanned mask is UNKNOWN, never 0).</summary>
            internal readonly bool[] AMaskKnown = new bool[ANCHOR_CAP];
            // B5 open windows
            internal int OwnWin = -1, OppWin = -1; internal int OwnWinStamp, OppWinStamp; internal int OwnWinFrames, OppWinFrames; internal long OwnWinSw;
            internal bool OwnPressPending, OwnOpened, OwnPressKeyed, OwnPressDone; internal int OwnPressStamp, OwnPressRow = -1; internal long OwnPressGap, OwnPressCd;
            internal bool HasOwnTb, HasOppTb; internal int LastOwnTb, LastOppTb; internal int OwnOrd, OppOrd; internal int OwnOrdTb = int.MinValue, OppOrdTb = int.MinValue;
            internal bool HasOPred; internal int OPred;
        }

        /// <summary>A fixed ring of numeric rows the hooks write and the tick drains.</summary>
        private sealed class Ring
        {
            internal readonly int Cap, Width; internal readonly double[] V; internal int Head, N;
            internal Ring(int cap, int width) { Cap = cap; Width = width; V = new double[cap * width]; }
            /// <summary>The offset of a new row, or -1 when full.</summary>
            internal int PushRow() { if (N >= Cap) return -1; int o = ((Head + N) % Cap) * Width; N++; return o; }
            internal int PushSlot() { if (N >= Cap) return -1; int i = (Head + N) % Cap; N++; return i; }
            internal int PopRow() { if (N == 0) return -1; int o = Head * Width; Head = (Head + 1) % Cap; N--; return o; }
            internal int PopSlot() { if (N == 0) return -1; int i = Head; Head = (Head + 1) % Cap; N--; return i; }
        }

        // -- shared helpers (fixed cost) ------------------------------------------------------------

        /// <summary>The RPC on top of the shared send stack; a fault is counted on the
        /// caller's row and reads as "no RPC on top".</summary>
        private static bool RpcTop(int row, out int stamp, out int sender, out int viewId, out string method)
        {
            try { return SeatEvidence.RpcTop(out stamp, out sender, out viewId, out method); }
            catch (Exception ex) { Fault(row, ex); stamp = 0; sender = 0; viewId = 0; method = null; return false; }
        }

        // A1 drop counters, in E.DROP_FIELDS order (the scenario harness holds each equal to E.DropIx(name)).
        internal const int D_MASK = 0, D_AIM = 1, D_RES = 2, D_PACK = 3, D_VOL_S = 4, D_VOL_O = 5, D_WAIT = 6, D_C_UNPAIRED = 7,
                           D_C_OUTSIDE = 8, D_PUSH_EXPIRED = 9, D_FORCE_UNKEYED = 10, D_UNKEYED = 11, D_RAY_FULL = 12,
                           D_RES_MASK_UNKNOWN = 13, D_RES_INCOMPARABLE = 14, D_MASK_UNSCANNED = 15;
        /// <summary>Older contact rows a received hit message outside the pairing window is looked for in.</summary>
        private const int OUTSIDE_SCAN_CAP = 64;

        /// <summary>The one position source for evidence about a player (M2): the
        /// body the game moves and every game reader uses (PlayerVelocity.position,
        /// which reads the player's transform). A missing body reads as absent.</summary>
        private static bool PosOf(Player p, out Vector2 pos)
        {
            pos = default(Vector2);
            if (p == null || p.data == null || p.data.playerVel == null) return false;
            pos = p.data.playerVel.position;
            return true;
        }

        private static GunState GunOf(Gun gun)
        {
            var g = _g;
            if (g == null || gun == null) return null;
            ResolvePlayers();
            if (_ownP != null && _ownP.data != null && _ownP.data.weaponHandler != null && gun == _ownP.data.weaponHandler.gun) return g.Own;
            if (_oppP != null && _oppP.data != null && _oppP.data.weaponHandler != null && gun == _oppP.data.weaponHandler.gun) return g.Opp;
            return null;
        }

        private static GunState GunOfActor(int actor)
        {
            var g = _g;
            if (g == null) return null;
            if (actor == _localActor) return g.Own;
            if (actor == _oppActor) return g.Opp;
            return null;
        }

        private static void Bind(GunState s, bool own)
        {
            ResolvePlayers();
            var p = own ? _ownP : _oppP;
            var gun = p != null && p.data != null && p.data.weaponHandler != null ? p.data.weaponHandler.gun : null;
            if (gun != s.G) { s.G = gun; s.A = gun != null ? gun.gunAmmo : null; s.LastAmmo = int.MinValue; }
        }

        private static int Ms(float seconds) { return (int)Math.Round(seconds * 1000.0, MidpointRounding.ToEven); }

        private static void Mark(GunState s, int stamp)
        {
            s.LastEvtStamp = stamp; s.LastEvtSw = SwMs; s.LastEvtGame = _gameMs; s.HasEvt = true;
        }

        private static double _gameMs;

        /// <summary>The ammunition change since this gun copy's last known count,
        /// classified by the game's own code paths (GunAmmo.Update): a refill to
        /// the magazine while not reloading with automatic reload due ends the
        /// cycle (automatic); a magazine size change redraws (redraw); any other
        /// rise is a regeneration. Fixed cost; from the tick and the init prefix.</summary>
        private static void Reconcile(GunState s)
        {
            if (s.A == null || s.G == null) return;
            int now = s.A.currentAmmo, max = s.A.maxAmmo;
            if (s.LastAmmo == int.MinValue) { s.LastAmmo = now; s.LastMax = max; return; }
            int stamp = ServerNow();
            if (max != s.LastMax)
            {
                s.LastMax = max;
                if (now == max && now != s.LastAmmo)
                    s.Acct.CloseCycle(W.END_REDRAW, W.SRC_NONE, Math.Max(-1, now - s.LastAmmo), stamp, -1, -1, -1);
                s.LastAmmo = now; Mark(s, stamp);
                return;
            }
            if (now > s.LastAmmo)
            {
                bool auto = !s.G.isReloading && now == max && s.G.player != null && s.G.player.data != null
                            && s.G.player.data.stats != null && s.G.player.data.stats.automaticReload
                            && s.A.freeReloadCounter > s.A.ReloadTime();
                if (auto) s.Acct.CloseCycle(W.END_AUTOMATIC, W.SRC_NONE, now - s.LastAmmo, stamp, -1, -1, -1);
                else
                {
                    long gg = s.HasEvt ? (long)Math.Round(_gameMs - s.LastEvtGame) : -1;
                    long gs = s.HasEvt ? C.WrapDiff(stamp, (int)s.LastEvtStamp) : -1;
                    long gr = s.HasEvt ? SwMs - s.LastEvtSw : -1;
                    s.Acct.AddRegen(now - s.LastAmmo, stamp, gg, gs, gr);
                }
                Mark(s, stamp);
            }
            s.LastAmmo = now;
        }

        // -- K1: an RPC this seat sends (SeatEvidence_RpcSendPatch postfix) --------------------------

        /// <summary>This seat's own `Shoot` to Others: an emission of the own
        /// gun, stamped by the envelope PUN just filled. Own block RPCs: the
        /// block's key for b5_s.</summary>
        internal static void RpcSent(PhotonView view, string method, RpcTarget target)
        {
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try { RpcSentBody(view, method, target); } catch (Exception ex) { Fault(K1, ex); }
            Cost(K1, t0);
        }

        private static readonly object KV = (byte)0, KS = (byte)2;

        private static void RpcSentBody(PhotonView view, string method, RpcTarget target)
        {
            var g = _g;
            if (g == null || view == null || !view.IsMine || method == null) return;
            if (method == "Shoot" && target == RpcTarget.Others)
            {
                // One accepted attack's emissions, synchronous (inside Gun.Attack) and
                // from the DoAttacks coroutine alike, take consecutive ordinals from
                // zero: the counter is reset only by an accepted attack (M4).
                var s = g.Own;
                s.Rep = Math.Min(999, s.AttackEmits);
                if (s.AttackEmits < 999) s.AttackEmits++;
                s.FirstPending = true;
                if (s.Rep != 0) { s.Since = -1; s.Fl = 0; }
                return;
            }
            if ((method == "RPCAO_DoBlock" || method == "RPCA_DoBlock") && g.OwnPressPending)
            {
                var ev = PhotonNetwork.rpcEvent;
                if (ev == null) return;
                object v = ev[KV], st = ev[KS];
                if (!(v is int) || (int)v != view.ViewID || !(st is int)) return;
                g.OwnPressPending = false;
                OwnBlockKeyed(g, g.OwnPressRow, (int)st);
            }
        }

        // -- N1: Gun.Attack prefix + postfix ----------------------------------------------------------

        internal static void AttackEnter(Gun gun, bool forceAttack, bool useAmmo, out long state)
        {
            state = 0;
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try { state = AttackEnterBody(gun, forceAttack, useAmmo); } catch (Exception ex) { Fault(N1, ex); }
            Cost(N1, t0);
        }

        private static long AttackEnterBody(Gun gun, bool forceAttack, bool useAmmo)
        {
            var s = GunOf(gun);
            if (s == null) return 0;
            if (s == _g.Own)
            {
                if (s.InAttack) return 0;            // a nested call (a card firing inside an attack) is not a gate
                // the counter restarts for this call; a refused call restores it (AttackExit),
                // so a refused press never renumbers the previous attack's coroutine emissions
                s.InAttack = true; s.AttackFirstSeen = false; s.SavedEmits = s.AttackEmits; s.SavedSince = s.Since; s.SavedFl = s.Fl; s.AttackEmits = 0;
                long since = (long)Math.Round(Math.Min(gun.sinceAttack * 1000.0, E.SINCE_CAP_MS));
                s.Since = since < 0 ? -1 : since;
                s.Fl = (forceAttack ? W.FL_FORCED : 0) | (useAmmo ? W.FL_USE_AMMO : 0) | (gun.isReloading ? W.FL_RELOADING : 0);
                return 1;
            }
            // the other seat's gun on this seat: a received attack message runs Attack(0, forced) inside Shoot
            int stamp, sender, view; string method;
            if (RpcTop(N1, out stamp, out sender, out view, out method) && method == "Shoot" && sender == _oppActor)
            {
                if (s.MsgPending) s.Acct.AddNoInit();
                s.MsgPending = true; s.MsgStamp = stamp;
                ReadCexp(s);
            }
            return 0;
        }

        internal static void AttackExit(Gun gun, bool result, bool forceAttack, long state)
        {
            if (!_open || state == 0) return;
            long t0 = Stamp();
            try { AttackExitBody(gun, result, forceAttack); } catch (Exception ex) { Fault(N1, ex); }
            Cost(N1, t0);
        }

        private static void AttackExitBody(Gun gun, bool result, bool forceAttack)
        {
            var g = _g;
            if (g == null) return;
            var s = g.Own;
            s.InAttack = false;
            if (!result)
            {
                if (s.AttackEmits == 0) { s.AttackEmits = s.SavedEmits; s.Since = s.SavedSince; s.Fl = s.SavedFl; }
                return;
            }
            // the rep 0 emission's ammo init runs synchronously inside the accepted call
            if (!s.AttackFirstSeen) s.Acct.AddNoInit();
            ReadCexp(s);
            // aim source: the gun's shoot point and direction (the muzzle, not a player position; M2 sweep)
            if (!forceAttack && _oppP != null && gun.shootPosition != null)
            {
                int o = g.Aim.PushRow();
                if (o < 0) { g.Drop[D_AIM]++; return; }
                var p = gun.shootPosition.position; var f = gun.shootPosition.forward;
                g.Aim.V[o] = 1; g.Aim.V[o + 1] = ServerNow(); g.Aim.V[o + 2] = p.x; g.Aim.V[o + 3] = p.y; g.Aim.V[o + 4] = f.x; g.Aim.V[o + 5] = f.y; g.Aim.V[o + 6] = 0;
            }
        }

        private static void ReadCexp(GunState s)
        {
            var gun = s.G;
            if (gun == null || gun.attackSpeedMultiplier <= 0f) return;
            long c = (long)Math.Round(gun.usedCooldown / gun.attackSpeedMultiplier * 1000.0);
            if (s.CexpMin < 0 || c < s.CexpMin) s.CexpMin = c;
        }

        // -- K2: ProjectileInit.RPCA_Init* prefix + finalizer -------------------------------------------

        /// <summary>Init prefix: the copy's ammunition, reload state and counter
        /// before Shoot (kind 0 ammo, 1 no-ammo, 2 separate gun). Returns the
        /// state the finalizer needs (bit 0: this gun copy was reloading).</summary>
        internal static int InitEnter(ProjectileInit init, int senderID, int kind)
        {
            if (!_open || PerfSuspend) return 0;
            long t0 = Stamp();
            int r = 0;
            try { r = InitEnterBody(init, senderID, kind); } catch (Exception ex) { Fault(K2, ex); }
            Cost(K2, t0);
            return r;
        }

        private static readonly string[] INIT_METHODS = { "RPCA_Init", "RPCA_Init_noAmmoUse", "RPCA_Init_SeparateGun" };

        private static int InitEnterBody(ProjectileInit init, int senderID, int kind)
        {
            var g = _g;
            if (g == null || init == null) return 0;
            var pv = init.GetComponent<PhotonView>();
            if (pv == null) return 0;
            int stamp, sender, view; string method;
            if (!RpcTop(K2, out stamp, out sender, out view, out method) || view != pv.ViewID || method != INIT_METHODS[kind]) return 0;
            var s = GunOfActor(sender);
            if (s == null || senderID != sender) return 0;
            bool own = s == g.Own;
            Bind(s, own);
            // volley stamps for the per-point intervals (ammo and no-ammo inits of the main gun)
            if (kind != 2 && (!s.HasVolley || stamp != s.LastVolley))
            {
                s.HasVolley = true; s.LastVolley = stamp;
                if (s.RingN < RING_CAP) { s.Ring[(s.RingHead + s.RingN) % RING_CAP] = stamp; s.RingN++; } else g.Drop[own ? D_VOL_S : D_VOL_O]++;
                // aim (B1): the first projectile of each volley, read on the tick; the
                // source is the projectile's own spawn point and direction (M2 sweep)
                int o = g.Aim.PushRow();
                if (o >= 0)
                {
                    var tr = init.transform; var p = tr.position; var f = tr.forward;
                    g.Aim.V[o] = own ? 0 : 2; g.Aim.V[o + 1] = stamp; g.Aim.V[o + 2] = p.x; g.Aim.V[o + 3] = p.y; g.Aim.V[o + 4] = f.x; g.Aim.V[o + 5] = f.y; g.Aim.V[o + 6] = 0;
                }
                else g.Drop[D_AIM]++;
                RxVolley(g, own, stamp);
            }
            // B3 anchors and steering masks (the scan is the tick's)
            NoteAnchor(g, init.gameObject, pv.ViewID, stamp, own);
            if (kind != 0) { s.Acct.AddKind(kind == 1); return 0; }
            if (s.A == null) return 0;
            Reconcile(s);
            int ammo = s.A.currentAmmo;
            bool rl = s.G.isReloading;
            long counter = rl ? (long)Math.Round(s.A.reloadCounter * 1000.0) : -1;
            long rep = -1, since = -1, fl = 0, am = -1;
            if (own)
            {
                if (s.FirstPending)
                {
                    s.FirstPending = false; rep = s.Rep;
                    if (rep == 0) { since = s.Since; fl = s.Fl; if (s.InAttack) s.AttackFirstSeen = true; }
                }
            }
            else if (s.MsgPending) { s.MsgPending = false; am = C.WrapDiff(stamp, s.MsgStamp); }
            s.Acct.AddShot(pv.ViewID, stamp, ammo, rl, counter, rep, since, fl, am);
            s.LastAmmo = ammo - 1;
            Mark(s, stamp);
            return 1 | (rl ? 2 : 0) | (own ? 4 : 0);
        }

        /// <summary>Init finalizer: a reload this Shoot started (the counter it set, for rl_g).</summary>
        internal static void InitExit(ProjectileInit init, int state)
        {
            if (!_open || (state & 1) == 0) return;
            long t0 = Stamp();
            try
            {
                var g = _g;
                var s = g == null ? null : ((state & 4) != 0 ? g.Own : g.Opp);
                if (s != null && s.G != null && s.A != null && (state & 2) == 0 && s.G.isReloading)
                {
                    s.RlOpen = true; s.RlCounter = s.A.reloadCounter; s.RlStamp = ServerNow(); s.RlSw = SwMs;
                }
            }
            catch (Exception ex) { Fault(K2, ex); }
            Cost(K2, t0);
        }

        private static void NoteAnchor(Game g, GameObject obj, int pid, int stamp, bool own)
        {
            int slot;
            if (!own)
            {
                g.P3n[0]++;
                if (!g.Slot.TryGetValue(pid, out slot))
                {
                    slot = g.ANext; g.ANext = (g.ANext + 1) % ANCHOR_CAP;
                    if (g.ALive[slot]) { g.Slot.Remove(g.APid[slot]); g.P3n[6]++; }
                    if (!g.Slot.Set(pid, slot)) return;
                }
                g.ALive[slot] = true; g.APid[slot] = pid; g.ASInit[slot] = stamp; g.AAge[slot] = C.WrapDiff(ServerNow(), stamp);
                g.AMask[slot] = 0; g.AMaskKnown[slot] = false; g.ACord[slot] = 0; g.AMsgCord[slot] = 0; g.AEdge[slot] = false;
                g.AHasHit[slot] = false; g.AHomChecked[slot] = false; g.AHasPack[slot] = false;
                g.AHomN[slot] = 0; g.AHomMax[slot] = -1; g.AObj[slot] = obj;
            }
            else
            {
                g.P3self[0]++; slot = -1;
                int k = pid & (ANCHOR_CAP - 1);
                g.OwnPid[k] = pid; g.OwnSInit[k] = stamp; g.OwnCord[k] = 0; g.OwnDecOn[k] = false; g.BsOn[k] = false;
            }
            int i = g.Mask.PushSlot();
            if (i < 0) { g.Drop[D_MASK]++; return; }
            g.Mask.V[i * 2] = slot; g.Mask.V[i * 2 + 1] = own ? 1 : 0; g.MaskObj[i] = obj;
        }

        // -- N2: GunAmmo.ReloadAmmo prefix --------------------------------------------------------------

        internal static void ReloadEnter(GunAmmo ammo, bool playSound)
        {
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try { ReloadBody(ammo, playSound); } catch (Exception ex) { Fault(N2, ex); }
            Cost(N2, t0);
        }

        private static void ReloadBody(GunAmmo ammo, bool playSound)
        {
            if (ammo == null) return;
            var s = GunOf(ammo.gun);
            if (s == null) return;
            if (s.A != ammo) { s.A = ammo; s.LastAmmo = int.MinValue; }
            Reconcile(s);
            int stamp = ServerNow();
            int amt = ammo.maxAmmo - ammo.currentAmmo;
            bool timer = playSound && s.G != null && s.G.isReloading && ammo.reloadCounter < 0f;
            if (timer)
            {
                long rlG = s.RlOpen ? (long)Math.Round((s.RlCounter - ammo.reloadCounter) * 1000.0) : -1;
                long rlS = s.RlOpen ? C.WrapDiff(stamp, s.RlStamp) : -1;
                long rlR = s.RlOpen ? SwMs - s.RlSw : -1;
                s.Acct.CloseCycle(W.END_TIMER, W.SRC_NONE, amt, stamp, rlG, rlS, rlR);
            }
            else if (s.Acct.Open || amt > 0)
                s.Acct.CloseCycle(W.END_EXTERNAL, playSound ? W.SRC_CARD : W.SRC_REVIVE, amt, stamp, -1, -1, -1);
            s.RlOpen = false;
            s.LastAmmo = ammo.maxAmmo;
            Mark(s, stamp);
        }

        // -- K3: ProjectileHit.RPCA_DoHit prefix (before :204 overwrites the copy); H1: its finalizer ---------

        /// <summary>The hit message's prefix. Returns the state its finalizer
        /// needs: bit 0 this call opened the shooter's scope (an own projectile's
        /// hit message on the other seat's player), bit 1 an own projectile's
        /// velocity before the message was read (R2).</summary>
        internal static void HitEnter(ProjectileHit ph, Vector2 point, Vector2 vel, int viewID, bool wasBlocked, out long state)
        {
            state = 0;
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try { state = HitBody(ph, point, vel, viewID, wasBlocked); } catch (Exception ex) { Fault(K3, ex); }
            Cost(K3, t0);
        }

        private static bool IsOwnPlayerView(int viewID)
        {
            if (viewID == -1 || _ownP == null || _ownP.data == null) return false;
            var target = PhotonNetwork.GetPhotonView(viewID);
            return target != null && target.IsMine && target == _ownP.data.view;
        }

        private static bool IsOppPlayerView(int viewID)
        {
            if (viewID == -1 || _oppP == null || _oppP.data == null) return false;
            var target = PhotonNetwork.GetPhotonView(viewID);
            return target != null && target.OwnerActorNr == _oppActor && target == _oppP.data.view;
        }

        private static long HitBody(ProjectileHit ph, Vector2 point, Vector2 vel, int viewID, bool wasBlocked)
        {
            var g = _g;
            if (g == null || ph == null) return 0;
            var pv = ph.GetComponent<PhotonView>();
            if (pv == null) return 0;
            int stamp, sender, view; string method;
            if (!RpcTop(K3, out stamp, out sender, out view, out method) || method != "RPCA_DoHit" || view != pv.ViewID) return 0;
            int pid = pv.ViewID;
            if (sender == _oppActor && pv.OwnerActorNr == _oppActor)
            {
                bool onMe = IsOwnPlayerView(viewID);
                int slot;
                if (!g.Slot.TryGetValue(pid, out slot) || !g.ALive[slot])
                {
                    // a hit on this seat's player by a projectile with no anchor cannot be keyed:
                    // the keyed sections are incomplete for this game (counted, bits withheld)
                    if (onMe) { g.Drop[D_UNKEYED]++; g.Void |= W.CAPS_PUSH | W.CAPS_CHAIN; }
                    return 0;
                }
                g.P3n[2]++;
                // the copy's state before the owner's message replaces it, and the owner's
                var mv = ph.move;
                int o = g.Res.PushRow();
                if (o >= 0 && mv != null)
                {
                    var cp = ph.transform.position;
                    var r = g.Res.V;
                    int now = ServerNow();
                    r[o] = slot; r[o + 1] = pid; r[o + 2] = stamp; r[o + 3] = C.WrapDiff(now, stamp) - g.AAge[slot];
                    r[o + 4] = cp.x; r[o + 5] = cp.y; r[o + 6] = mv.velocity.x; r[o + 7] = mv.velocity.y;
                    r[o + 8] = point.x; r[o + 9] = point.y; r[o + 10] = vel.x; r[o + 11] = vel.y;
                    r[o + 12] = mv.gravity; r[o + 13] = mv.drag; r[o + 14] = mv.dragMinSpeed; r[o + 15] = mv.multiplier;
                    r[o + 16] = mv.simulationSpeed; r[o + 17] = mv.allowStop ? 1 : 0; r[o + 18] = mv.simulateGravity; r[o + 19] = TimeHandler.timeScale;
                    // A1 F4: an edge bounce since the anchor makes this residual incomparable
                    r[o + 20] = g.AEdge[slot] ? 1 : 0;
                    // re-anchor: the copy now holds the owner's state at this stamp
                    g.AAge[slot] = C.WrapDiff(now, stamp); g.AEdge[slot] = false;
                }
                else if (o < 0) g.Drop[D_RES]++;
                g.ALastHit[slot] = stamp; g.AHasHit[slot] = true;
                if (onMe)
                {
                    // B5 victim side: the hit message on this seat's own player
                    FillContact(g, pid, stamp);
                    // R1/R3 victim side: this message's identity is the ordinal of the
                    // projectile's hit messages on this player, the shooter's own count
                    int cord = Math.Min(255, g.AMsgCord[slot]);
                    if (g.AMsgCord[slot] < 255) g.AMsgCord[slot]++;
                    VictimHit(g, pid, g.ASInit[slot], cord, wasBlocked);
                }
                return 0;
            }
            if (sender != _localActor || !pv.IsMine) return 0;
            int k = pid & (ANCHOR_CAP - 1);
            bool known = g.OwnPid[k] == pid;
            long st = 0;
            // R2: the owner's velocity before its own hit message (the finalizer reads the after)
            if (known && ph.move != null)
            {
                g.HvOn = true; g.HvX = ph.move.velocity.x; g.HvY = ph.move.velocity.y;
                g.HvPid = pid; g.HvSInit = g.OwnSInit[k]; g.HvStamp = stamp; g.HvView = viewID;
                st |= 2;
            }
            if (!IsOppPlayerView(viewID)) return st;
            // B5 shooter side: this seat's own decision on the other seat's player (path 0)
            if (!known) { g.Drop[D_UNKEYED]++; g.Void |= W.CAPS_PUSH | W.CAPS_CHAIN; }
            int hcord = known ? Math.Min(255, g.OwnCord[k]) : 0;
            if (known && g.OwnCord[k] < 255) g.OwnCord[k]++;
            g.A1Tot[0]++;                                   // A1 F2: the never-trimmed b5_h total
            var blk = _oppP.data.block;
            int ob = g.B5h.NextSlot();
            if (ob >= 0)
            {
                var a = g.B5h.Raw;
                long since = blk == null ? -1 : (long)Math.Round(Math.Min(blk.sinceBlock * 1000.0, 600000.0));
                a[ob] = 0; a[ob + 1] = stamp; a[ob + 2] = pid; a[ob + 3] = known ? g.OwnSInit[k] : 0; a[ob + 4] = hcord; a[ob + 5] = 0;
                a[ob + 6] = since < 0 ? -1 : since;
                a[ob + 7] = g.HasOPred ? E.Clamp(C.WrapDiff(stamp, g.OPred), -600000, 600000) : 600000;
            }
            if (!known) return st;
            RecentHit(g.RhOpp, ref g.RhOppHead, ref g.RhOppN, pid, g.OwnSInit[k], hcord, stamp);
            if (wasBlocked) return st;
            // R1/R3 shooter side: the scope of this message; the damage and force it
            // creates run synchronously inside it (RpcTarget.All executes locally)
            if (g.ScOn) { g.Drop[D_UNKEYED]++; g.Void |= W.CAPS_PUSH | W.CAPS_CHAIN; return st; }
            g.ScOn = true; g.ScPid = pid; g.ScSInit = g.OwnSInit[k]; g.ScCord = hcord; g.ScPush = false; g.ScDmg = false;
            int oc = g.ChO.NextSlot();
            g.ScChRow = oc;
            if (oc >= 0)
            {
                var c = g.ChO.Raw;
                c[oc] = pid; c[oc + 1] = g.ScSInit; c[oc + 2] = hcord;
                c[oc + 3] = g.OwnDecOn[k] ? g.OwnDec[k] : -1; c[oc + 4] = stamp; c[oc + 5] = -1;
            }
            g.OwnDecOn[k] = false;
            return st | 1;
        }

        /// <summary>The hit message's finalizer: the shooter's scope closes; an own
        /// projectile's velocity change by its own hit message is listed (R2).</summary>
        internal static void HitExit(ProjectileHit ph, long state)
        {
            if (!_open || state == 0) return;
            long t0 = Stamp();
            try { HitExitBody(ph, state); } catch (Exception ex) { Fault(H1, ex); }
            Cost(H1, t0);
        }

        private static void HitExitBody(ProjectileHit ph, long state)
        {
            var g = _g;
            if (g == null) return;
            if ((state & 1) != 0) { g.ScOn = false; g.ScChRow = -1; }
            if ((state & 2) == 0 || !g.HvOn) return;
            g.HvOn = false;
            var mv = ph != null ? ph.move : null;
            float nx = mv != null ? mv.velocity.x : g.HvX, ny = mv != null ? mv.velocity.y : g.HvY;
            long cause = 0;
            if (PhotonNetwork.GetPhotonView(g.HvPid) == null) cause |= W.CAUSE_DESTRUCTION;
            if (nx != g.HvX || ny != g.HvY) cause |= g.HvView != -1 ? W.CAUSE_COLLIDER : W.CAUSE_SURFACE;
            if (cause == 0) return;
            if ((cause & (W.CAUSE_COLLIDER | W.CAUSE_SURFACE)) == 0) cause |= g.HvView != -1 ? W.CAUSE_COLLIDER : W.CAUSE_SURFACE;
            VchgRow(g, g.HvPid, g.HvSInit, g.HvStamp, cause, g.HvX, g.HvY, nx, ny);
        }

        private static void VchgRow(Game g, int pid, int sInit, int stamp, long cause, float ox, float oy, float nx, float ny)
        {
            int o = g.Vchg.NextSlot();          // r_tot counts every call (FixedRows.Total)
            if (o < 0) return;
            var a = g.Vchg.Raw;
            a[o] = pid; a[o + 1] = sInit; a[o + 2] = stamp; a[o + 3] = E.Clamp(cause, 1, 63);
            a[o + 4] = Centi(ox, 9999999); a[o + 5] = Centi(oy, 9999999); a[o + 6] = Centi(nx, 9999999); a[o + 7] = Centi(ny, 9999999);
        }

        private static long Centi(double v, long hi) { return E.Clamp(E.RoundEven(v * W.CENTI), -hi, hi); }

        /// <summary>The victim's pending received hit (R1, R3): the push and the damage
        /// the other seat's message creates arrive after it in the same sender's
        /// order and bind to it; it expires at the next tick, or when the next hit
        /// message replaces it. A blocked hit creates no push or damage and opens
        /// nothing (both seats read the same wasBlocked from the message).</summary>
        private static void VictimHit(Game g, int pid, int sInit, int cord, bool wasBlocked)
        {
            RecentHit(g.RhOwn, ref g.RhOwnHead, ref g.RhOwnN, pid, sInit, cord, ServerNow());
            if (g.VcOn && !g.VcPush) g.Drop[D_PUSH_EXPIRED]++;
            g.VcOn = false; g.VcChRow = -1;
            if (wasBlocked) return;
            g.VcOn = true; g.VcPid = pid; g.VcSInit = sInit; g.VcCord = cord; g.VcPush = false; g.VcDmg = false;
            g.VcFrame = Time.frameCount;
            int o = g.ChS.NextSlot();
            g.VcChRow = o;
            if (o < 0) return;
            var a = g.ChS.Raw;
            a[o] = pid; a[o + 1] = sInit; a[o + 2] = cord; a[o + 3] = ServerNow(); a[o + 4] = -1; a[o + 5] = -1; a[o + 6] = -1; a[o + 7] = 0;
        }

        /// <summary>The last RECENT_CAP hits on one player (pid, s_init, cord, stamp), newest last.</summary>
        private static void RecentHit(int[] ring, ref int head, ref int n, int pid, int sInit, int cord, int stamp)
        {
            int i = (head + n) % RECENT_CAP;
            if (n < RECENT_CAP) n++; else head = (head + 1) % RECENT_CAP;
            ring[i * 4] = pid; ring[i * 4 + 1] = sInit; ring[i * 4 + 2] = cord; ring[i * 4 + 3] = stamp;
        }

        /// <summary>A received hit message pairs to the OLDEST unmatched contact of the
        /// same projectile among the last PAIR_CAP contact rows, in send order (M6);
        /// a message with no partner in the window is counted: `c_outside` when an
        /// older unmatched contact of that projectile exists, else `c_unpaired`.</summary>
        private static void FillContact(Game g, int pid, int stamp)
        {
            var raw = g.B5c.Raw;
            int w = g.B5c.Width, count = g.B5c.Count;
            int start = count > PAIR_CAP ? count - PAIR_CAP : 0;
            for (int i = start, n = 0; i < count && n < PAIR_CAP; i++, n++)
            {
                int o = i * w;
                if (raw[o] == pid && raw[o + 6] == W.OWN_SINCE_NONE) { raw[o + 5] = stamp; raw[o + 6] = OwnSinceMs(); return; }
            }
            for (int i = start - 1, n = 0; i >= 0 && n < OUTSIDE_SCAN_CAP; i--, n++)
            {
                int o = i * w;
                if (raw[o] == pid && raw[o + 6] == W.OWN_SINCE_NONE) { g.Drop[D_C_OUTSIDE]++; return; }
            }
            g.Drop[D_C_UNPAIRED]++;
        }

        private static long OwnSinceMs()
        {
            var b = _ownP != null && _ownP.data != null ? _ownP.data.block : null;
            if (b == null) return -1;
            return (long)Math.Round(Math.Min(b.sinceBlock * 1000.0, 600000.0));
        }

        // -- N7: ProjectileHit.Hit prefix (the copy's contact with this seat's player) ------------------

        internal static void ContactEnter(ProjectileHit ph, HitInfo hit)
        {
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try { ContactBody(ph, hit); } catch (Exception ex) { Fault(N7, ex); }
            Cost(N7, t0);
        }

        private static void ContactBody(ProjectileHit ph, HitInfo hit)
        {
            var g = _g;
            if (g == null || ph == null || hit == null || hit.transform == null || _ownP == null) return;
            var pv = ph.GetComponent<PhotonView>();
            if (pv == null) return;
            if (pv.IsMine)
            {
                // R3 shooter side: this seat's own projectile decides a hit on the other
                // seat's player (the decision stamp the next hit message's chain row takes)
                var od = _oppP != null ? hit.transform.GetComponent<CharacterData>() : null;
                if (od == null || od != _oppP.data) return;
                int k = pv.ViewID & (ANCHOR_CAP - 1);
                if (g.OwnPid[k] == pv.ViewID) { g.OwnDec[k] = ServerNow(); g.OwnDecOn[k] = true; }
                return;
            }
            if (pv.OwnerActorNr != _oppActor) return;
            var data = hit.transform.GetComponent<CharacterData>();
            if (data == null || data != _ownP.data) return;
            int pid = pv.ViewID, slot, sInit = 0, cord = 0;
            if (g.Slot.TryGetValue(pid, out slot) && g.ALive[slot]) { sInit = g.ASInit[slot]; cord = Math.Min(255, g.ACord[slot]++); }
            long since = OwnSinceMs();
            g.B5tot[6]++;
            if (since >= 0 && since < 300) g.B5tot[7]++;
            int o = g.B5c.NextSlot();
            if (o < 0) return;
            var a = g.B5c.Raw;
            a[o] = pid; a[o + 1] = sInit; a[o + 2] = cord; a[o + 3] = ServerNow(); a[o + 4] = since; a[o + 5] = 0; a[o + 6] = W.OWN_SINCE_NONE;
        }

        // -- K4: Block.RPCA_DoBlock finalizer; N6: Block.TryBlock prefix + postfix -----------------------

        internal static void BlockDone(Block b)
        {
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try { BlockBody(b); } catch (Exception ex) { Fault(K4, ex); }
            Cost(K4, t0);
        }

        private static void BlockBody(Block b)
        {
            var g = _g;
            if (g == null || b == null) return;
            var data = b.GetComponent<CharacterData>();
            if (data == null || data.view == null) return;
            bool started = b.sinceBlock == 0f;
            if (data.view.IsMine)
            {
                if (!started) return;
                if (g.OwnWin >= 0) g.B5s.Raw[g.OwnWin + 7] = 1;          // reopened while open
                return;
            }
            if (data.view.OwnerActorNr != _oppActor) return;
            int stamp, sender, view; string method;
            if (!RpcTop(K4, out stamp, out sender, out view, out method) || sender != _oppActor || view != data.view.ViewID
                || (method != "RPCAO_DoBlock" && method != "RPCA_DoBlock")) return;
            int now = ServerNow();
            g.B5tot[1]++;
            if (!started) g.B5tot[5]++;
            int cd = (int)Math.Round(b.Cooldown() * 1000.0);
            long gapPrev = g.HasOppTb ? E.Clamp(C.WrapDiff(stamp, g.LastOppTb), -1, 600000) : -1;
            if (gapPrev >= 0 && gapPrev < cd) g.B5tot[4]++;
            g.HasOppTb = true; g.LastOppTb = stamp;
            if (stamp != g.OppOrdTb) { g.OppOrdTb = stamp; g.OppOrd = 0; } else g.OppOrd = Math.Min(255, g.OppOrd + 1);
            int oPred = b.delayOtherActions ? stamp - 200 : stamp;
            g.HasOPred = true; g.OPred = oPred;
            if (g.OppWin >= 0) g.B5o.Raw[g.OppWin + 8] = 1;
            int o = g.B5o.NextSlot();
            if (o < 0) { g.OppWin = -1; return; }
            var a = g.B5o.Raw;
            long age = E.Clamp(C.WrapDiff(now, stamp), -600000, 600000);
            a[o] = stamp; a[o + 1] = 0; a[o + 2] = g.OppOrd; a[o + 3] = age; a[o + 4] = started ? age : 600000;
            a[o + 5] = started ? 1 : 0; a[o + 6] = -1; a[o + 7] = -1; a[o + 8] = 0; a[o + 9] = C.WrapDiff(oPred, stamp);
            a[o + 10] = E.Clamp(cd, 0, 600000); a[o + 11] = gapPrev; a[o + 12] = 0;
            if (started) { g.OppWin = o; g.OppWinStamp = now; g.OppWinFrames = 0; } else g.OppWin = -1;
        }

        /// <summary>The own press's prefix. An accepted press (the game's own test,
        /// Block.TryBlock: counter not below the cooldown) reserves its b5_s row and
        /// arms the pending key HERE, before the game sends the block (the send runs
        /// inside RPCA_DoBlock, or 0.2 s later with delayOtherActions), so the
        /// emitted stamp binds to this press's own row (M5). A press whose row the
        /// full list omits arms nothing.</summary>
        internal static void TryBlockEnter(Block b, out long state)
        {
            state = 0;
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try
            {
                var data = b != null ? b.GetComponent<CharacterData>() : null;
                if (data != null && data.view != null && data.view.IsMine)
                {
                    bool accepted = !(b.counter < b.Cooldown());
                    long counterMs = (long)Math.Round(Math.Min(b.counter, 600f) * 1000.0);
                    state = 1L | (accepted ? 2L : 0L) | (counterMs << 2);
                    if (accepted) ReserveOwnBlock(b, counterMs);
                }
            }
            catch (Exception ex) { Fault(N6, ex); }
            Cost(N6, t0);
        }

        private static void ReserveOwnBlock(Block b, long counterMs)
        {
            var g = _g;
            if (g == null) return;
            long cd = (long)Math.Round(b.Cooldown() * 1000.0);
            g.B5tot[0]++;
            if (counterMs < cd) g.B5tot[3]++;
            if (g.OwnPressPending) g.Drop[D_UNKEYED]++;       // the previous press's send never came
            g.OwnPressPending = false; g.OwnPressKeyed = false; g.OwnPressDone = false; g.OwnOpened = false;
            g.OwnPressStamp = ServerNow(); g.OwnPressGap = counterMs; g.OwnPressCd = cd;
            int o2 = g.B5s.NextSlot();
            g.OwnPressRow = o2;
            if (o2 < 0) return;
            var r = g.B5s.Raw;
            r[o2] = 0; r[o2 + 1] = 0; r[o2 + 2] = 0; r[o2 + 3] = 0; r[o2 + 4] = 600000; r[o2 + 5] = -1; r[o2 + 6] = -1; r[o2 + 7] = 0;
            r[o2 + 8] = E.Clamp((long)Math.Round(TimeHandler.timeScale * 1000.0), 0, 10000); r[o2 + 9] = E.Clamp(cd, 0, 600000);
            r[o2 + 10] = E.Clamp(counterMs, -1, 600000); r[o2 + 11] = 0;
            g.OwnPressPending = true;
        }

        internal static void TryBlockExit(Block b, long state)
        {
            if (!_open || state == 0) return;
            long t0 = Stamp();
            try { TryBlockBody(b, (state & 2) != 0, state >> 2); } catch (Exception ex) { Fault(N6, ex); }
            Cost(N6, t0);
        }

        private static void TryBlockBody(Block b, bool accepted, long counterMs)
        {
            var g = _g;
            if (g == null || b == null) return;
            if (!accepted)
            {
                long cd = (long)Math.Round(b.Cooldown() * 1000.0);
                g.B5tot[2]++;
                int o = g.B5r.NextSlot();
                if (o >= 0) { var a = g.B5r.Raw; a[o] = ServerNow(); a[o + 1] = E.Clamp(counterMs, -1, 600000); a[o + 2] = E.Clamp(cd, 0, 600000); }
                return;
            }
            // the accepted press's own row: its opening (the window the tick closes)
            g.OwnWin = -1;
            int o2 = g.OwnPressRow;
            bool open = b.sinceBlock == 0f;
            g.OwnOpened = open; g.OwnPressDone = true;
            if (o2 < 0) return;
            if (open)
            {
                var r = g.B5s.Raw;
                if (g.OwnPressKeyed) r[o2 + 4] = r[o2 + 3];
                g.OwnWin = o2; g.OwnWinStamp = g.OwnPressStamp; g.OwnWinFrames = 0; g.OwnWinSw = SwMs;
            }
        }

        /// <summary>The own block's stamp arrived with its outgoing RPC: the
        /// reserved row's key, and its press and opening relative to that stamp.</summary>
        private static void OwnBlockKeyed(Game g, int o, int tb)
        {
            if (o < 0) return;
            var r = g.B5s.Raw;
            if (tb != g.OwnOrdTb) { g.OwnOrdTb = tb; g.OwnOrd = 0; } else g.OwnOrd = Math.Min(255, g.OwnOrd + 1);
            r[o] = tb; r[o + 2] = g.OwnOrd;
            r[o + 3] = E.Clamp(C.WrapDiff(g.OwnPressStamp, tb), -600000, 600000);
            if (g.OwnPressDone && g.OwnOpened) r[o + 4] = r[o + 3];
            g.OwnPressKeyed = true;
            g.HasOwnTb = true; g.LastOwnTb = tb;
        }

        // -- K5: CharacterStatModifiers.DealtDamage postfix -------------------------------------------

        internal static void Dealt(CharacterStatModifiers stats)
        {
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try
            {
                var g = _g;
                if (g != null && stats != null && stats.refreshOnDamage)
                {
                    var data = stats.GetComponent<CharacterData>();
                    if (data != null && _ownP != null && data == _ownP.data) g.Own.Refreshes++;
                    else if (data != null && _oppP != null && data == _oppP.data) g.Opp.Refreshes++;
                }
            }
            catch (Exception ex) { Fault(K5, ex); }
            Cost(K5, t0);
        }

        // -- N3: BounceEffectRetarget.SetNewVel prefix; N4: ScreenEdgeBounce.DoHit prefix + E1 finalizer ---

        internal static void TargetBounce(BounceEffectRetarget r, Vector2 newVel)
        {
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try { TargetBounceBody(r, newVel); } catch (Exception ex) { Fault(N3, ex); }
            Cost(N3, t0);
        }

        private static void TargetBounceBody(BounceEffectRetarget r, Vector2 newVel)
        {
            var g = _g;
            if (g == null || r == null || r.view == null) return;
            int stamp, sender, view; string method;
            if (r.view.IsMine)
            {
                g.P3self[9]++;
                // R2 owner side: the owner's own new velocity, sent under this stamp, and
                // the target choice its DelayMove made (FindTarget) for this projectile
                if (!RpcTop(N3, out stamp, out sender, out view, out method) || method != "RPCA_RecieveFunction"
                    || sender != _localActor || view != r.view.ViewID) return;
                int pid = r.view.ViewID, k = pid & (ANCHOR_CAP - 1);
                if (g.OwnPid[k] != pid) { g.Drop[D_UNKEYED]++; g.Void |= W.CAPS_VCHG; return; }
                float ox = r.move != null ? r.move.velocity.x : newVel.x, oy = r.move != null ? r.move.velocity.y : newVel.y;
                VchgRow(g, pid, g.OwnSInit[k], stamp, W.CAUSE_RETARGET, ox, oy, newVel.x, newVel.y);
                if (!g.BsOn[k] || g.BsPid[k] != pid) { g.Drop[D_UNKEYED]++; g.Void |= W.CAPS_VCHG; return; }
                g.BsOn[k] = false;
                int o = g.Bsel.NextSlot();
                if (o < 0) return;
                var a = g.Bsel.Raw; int b = k * 5;
                a[o] = pid; a[o + 1] = g.OwnSInit[k]; a[o + 2] = stamp; a[o + 3] = g.Bs[b];
                a[o + 4] = g.Bs[b + 1]; a[o + 5] = g.Bs[b + 2]; a[o + 6] = g.Bs[b + 3]; a[o + 7] = g.Bs[b + 4];
                return;
            }
            if (r.view.OwnerActorNr != _oppActor) return;
            g.P3n[4]++;
            int opid = r.view.ViewID, slot, sInit = 0;
            long gap = -1;
            bool keyed = RpcTop(N3, out stamp, out sender, out view, out method) && sender == _oppActor;
            if (g.Slot.TryGetValue(opid, out slot) && g.ALive[slot])
            {
                sInit = g.ASInit[slot];
                if (keyed && g.AHasHit[slot]) gap = E.Clamp(C.WrapDiff(stamp, g.ALastHit[slot]), -1, 600000);
            }
            long has = r.move != null && (r.move.velocity.x != newVel.x || r.move.velocity.y != newVel.y) ? 1 : 0;
            long ang = 0;
            Vector2 me;
            if (PosOf(_ownP, out me))
            {
                var pos = r.transform.position;
                double mx = me.x - pos.x, my = me.y - pos.y;
                ang = E.RoundEven(Math.Abs(Math.Atan2(newVel.x * my - newVel.y * mx, newVel.x * mx + newVel.y * my)) * 1000.0);
            }
            int oo = g.P3tb.NextSlot();
            if (oo < 0) return;
            var aa = g.P3tb.Raw;
            aa[oo] = opid; aa[oo + 1] = sInit; aa[oo + 2] = keyed ? stamp : 0; aa[oo + 3] = gap; aa[oo + 4] = has; aa[oo + 5] = E.Clamp(ang, 0, 3142);
        }

        /// <summary>S1: BounceEffectRetarget.FindTarget postfix, the OWNER's copy only:
        /// the candidates as the owner's own DelayMove computed them (the closest
        /// living player to the bounce point nudged along the normal, its line of
        /// sight from the projectile, the result). Pending per own projectile until
        /// the owner's SetNewVel sends the new velocity under its stamp.</summary>
        internal static void FindTarget(BounceEffectRetarget r, HitInfo hit, Player result)
        {
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try { FindTargetBody(r, hit, result); } catch (Exception ex) { Fault(S1, ex); }
            Cost(S1, t0);
        }

        private static void FindTargetBody(BounceEffectRetarget r, HitInfo hit, Player result)
        {
            var g = _g;
            if (g == null || r == null || r.view == null || !r.view.IsMine || hit == null) return;
            int pid = r.view.ViewID, k = pid & (ANCHOR_CAP - 1);
            if (g.OwnPid[k] != pid) { g.Drop[D_UNKEYED]++; g.Void |= W.CAPS_VCHG; return; }
            var pm = PlayerManager.instance;
            Vector2 refPos = (Vector2)r.transform.position + hit.normal * 0.1f;
            Player closest = pm != null ? pm.GetClosestPlayer(refPos) : null;
            long dSelf = -1, dOther = -1, losSelf = -1, losOther = -1;
            Vector2 p;
            if (_ownP != null && _ownP.data != null && !_ownP.data.dead && PosOf(_ownP, out p)) dSelf = Centi(Vector2.Distance(refPos, p), 9999999);
            if (_oppP != null && _oppP.data != null && !_oppP.data.dead && PosOf(_oppP, out p)) dOther = Centi(Vector2.Distance(refPos, p), 9999999);
            if (closest != null && closest == _ownP) losSelf = result != null ? 1 : 0;
            if (closest != null && closest == _oppP) losOther = result != null ? 1 : 0;
            long target = result == null ? W.BOUNCE_TARGET_NONE : (result == _ownP ? W.BOUNCE_TARGET_SELF : (result == _oppP ? W.BOUNCE_TARGET_OTHER : W.BOUNCE_TARGET_NONE));
            int b = k * 5;
            g.Bs[b] = target; g.Bs[b + 1] = dSelf; g.Bs[b + 2] = losSelf; g.Bs[b + 3] = dOther; g.Bs[b + 4] = losOther;
            g.BsOn[k] = true; g.BsPid[k] = pid;
        }

        /// <summary>N4 prefix: an edge bounce. The other seat's copy marks its anchor
        /// (A1 F4: the residual since is incomparable); the owner's copy reads its
        /// velocity before the reflection for R2. Returns the finalizer's state.</summary>
        internal static void EdgeBounce(ScreenEdgeBounce b, out long state)
        {
            state = 0;
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try { state = EdgeBounceBody(b); } catch (Exception ex) { Fault(N4, ex); }
            Cost(N4, t0);
        }

        private static long EdgeBounceBody(ScreenEdgeBounce b)
        {
            var g = _g;
            var pv = b != null ? b.GetComponentInParent<PhotonView>() : null;
            if (g == null || pv == null) return 0;
            if (!pv.IsMine)
            {
                if (pv.OwnerActorNr != _oppActor) return 0;
                g.P3n[3]++;
                int slot;
                if (g.Slot.TryGetValue(pv.ViewID, out slot) && g.ALive[slot]) g.AEdge[slot] = true;
                return 0;
            }
            int stamp, sender, view; string method;
            if (!RpcTop(N4, out stamp, out sender, out view, out method) || method != "RPCA_RecieveFunction" || sender != _localActor || view != pv.ViewID) return 0;
            int pid = pv.ViewID, k = pid & (ANCHOR_CAP - 1);
            if (g.OwnPid[k] != pid) { g.Drop[D_UNKEYED]++; g.Void |= W.CAPS_VCHG; return 0; }
            var mv = b.projHit != null ? b.projHit.move : null;
            if (mv == null) return 0;
            g.EvOn = true; g.EvX = mv.velocity.x; g.EvY = mv.velocity.y; g.EvPid = pid; g.EvSInit = g.OwnSInit[k]; g.EvStamp = stamp;
            return 1;
        }

        /// <summary>E1: the owner's edge bounce has reflected its velocity (R2, cause surface).</summary>
        internal static void EdgeBounceExit(ScreenEdgeBounce b, long state)
        {
            if (!_open || state == 0) return;
            long t0 = Stamp();
            try
            {
                var g = _g;
                if (g != null && g.EvOn)
                {
                    g.EvOn = false;
                    var mv = b != null && b.projHit != null ? b.projHit.move : null;
                    if (mv != null && (mv.velocity.x != g.EvX || mv.velocity.y != g.EvY))
                        VchgRow(g, g.EvPid, g.EvSInit, g.EvStamp, W.CAUSE_SURFACE, g.EvX, g.EvY, mv.velocity.x, mv.velocity.y);
                }
            }
            catch (Exception ex) { Fault(E1, ex); }
            Cost(E1, t0);
        }

        // -- P1: HealthHandler.RPCA_SendTakeForce prefix + finalizer (R1 push) ---------------------------

        /// <summary>A push as it is applied to a player body on this seat. The
        /// victim's own body (this seat's player, the message from the other seat)
        /// lists push_s under the pending received hit; the shooter's copy of the
        /// other player (the message this seat's own hit message executes locally,
        /// inside its scope) lists push_o. The frame must be RPCA_SendTakeForce on
        /// that player's own view, so a force any other path applies (the game's
        /// own local drag, a block, out-of-bounds) is never listed.</summary>
        internal static void ForceEnter(HealthHandler hh, Vector2 force, out long state)
        {
            state = 0;
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try { state = ForceBody(hh, force); } catch (Exception ex) { Fault(P1, ex); }
            Cost(P1, t0);
        }

        private static long ForceBody(HealthHandler hh, Vector2 force)
        {
            var g = _g;
            if (g == null || hh == null) return 0;
            var data = hh.GetComponent<CharacterData>();
            if (data == null || data.view == null || data.playerVel == null) return 0;
            bool own = _ownP != null && data == _ownP.data, opp = _oppP != null && data == _oppP.data;
            if (!own && !opp) return 0;
            int stamp, sender, view; string method;
            if (!RpcTop(P1, out stamp, out sender, out view, out method) || method != "RPCA_SendTakeForce" || view != data.view.ViewID) return 0;
            E.FixedRows rows; int pid, sInit, cord;
            if (own && sender == _oppActor)
            {
                if (!g.VcOn || g.VcPush) { g.Drop[D_FORCE_UNKEYED]++; return 0; }
                g.VcPush = true; rows = g.PushS; pid = g.VcPid; sInit = g.VcSInit; cord = g.VcCord;
            }
            else if (opp && sender == _localActor)
            {
                if (!g.ScOn || g.ScPush) { g.Drop[D_FORCE_UNKEYED]++; return 0; }
                g.ScPush = true; rows = g.PushO; pid = g.ScPid; sInit = g.ScSInit; cord = g.ScCord;
            }
            else return 0;
            int o = rows.NextSlot();
            if (o < 0) return 0;
            var a = rows.Raw; var pv = data.playerVel; var pos = pv.position;
            a[o] = pid; a[o + 1] = sInit; a[o + 2] = cord; a[o + 3] = stamp;
            a[o + 4] = Centi(force.x, 99999999); a[o + 5] = Centi(force.y, 99999999); a[o + 6] = E.Clamp(E.RoundEven(pv.mass * W.CENTI), 0, 99999999);
            a[o + 7] = Centi(pv.velocity.x, 9999999); a[o + 8] = Centi(pv.velocity.y, 9999999);
            a[o + 9] = a[o + 7]; a[o + 10] = a[o + 8];
            a[o + 11] = Centi(pos.x, 9999999); a[o + 12] = Centi(pos.y, 9999999);
            a[o + 13] = a[o + 11]; a[o + 14] = a[o + 12];
            return ((long)o << 2) | (own ? 0L : 2L) | 1L;
        }

        /// <summary>P1 finalizer: the velocity after the force; the position after is the
        /// first tick in a later frame (the wait ring).</summary>
        internal static void ForceExit(HealthHandler hh, long state)
        {
            if (!_open || state == 0) return;
            long t0 = Stamp();
            try
            {
                var g = _g;
                var data = hh != null ? hh.GetComponent<CharacterData>() : null;
                if (g != null && data != null && data.playerVel != null)
                {
                    var rows = (state & 2) == 0 ? g.PushS : g.PushO;
                    int o = (int)(state >> 2);
                    var a = rows.Raw;
                    a[o + 9] = Centi(data.playerVel.velocity.x, 9999999); a[o + 10] = Centi(data.playerVel.velocity.y, 9999999);
                    Wait(g, 0, rows, o, (state & 2) == 0 ? 0 : 1);
                }
            }
            catch (Exception ex) { Fault(P1, ex); }
            Cost(P1, t0);
        }

        /// <summary>A row waiting for a later tick: kind 0 a push's after-position (player 0 own, 1 other),
        /// kind 1 a chain's first rendered frame. A full ring leaves the row's value as it stands (counted).</summary>
        private static void Wait(Game g, int kind, E.FixedRows rows, int o, int player)
        {
            if (g.WN >= WAIT_CAP) { g.Drop[D_WAIT]++; return; }
            int i = (g.WHead + g.WN) % WAIT_CAP; g.WN++;
            g.WKind[i] = kind; g.WList[i] = rows; g.WRow[i] = o; g.WPlayer[i] = player; g.WFrame[i] = Time.frameCount;
        }

        private static void DrainWaits(Game g, int now)
        {
            int frame = Time.frameCount;
            for (int n = 0; n < WAIT_CAP && g.WN > 0; n++)
            {
                int i = g.WHead;
                int kind = g.WKind[i];
                // a push's after-position: a later frame than the force; a chain's frame: this frame or later
                if (kind == 0 ? frame <= g.WFrame[i] : frame < g.WFrame[i]) return;
                var rows = g.WList[i]; int o = g.WRow[i];
                g.WList[i] = null; g.WHead = (g.WHead + 1) % WAIT_CAP; g.WN--;
                if (rows == null) continue;
                var a = rows.Raw;
                if (kind == 1) { a[o + 6] = now; continue; }
                Vector2 p;
                if (PosOf(g.WPlayer[i] == 0 ? _ownP : _oppP, out p)) { a[o + 13] = Centi(p.x, 9999999); a[o + 14] = Centi(p.y, 9999999); }
            }
        }

        // -- D1: HealthHandler.RPCA_SendTakeDamage prefix + finalizer (R3 chain, R5 cause) -------------------

        /// <summary>A damage message as it executes on a player on this seat. Every
        /// seat records the message's own source for that player (out of bounds or
        /// any other) for the death that may follow. The victim's own player with
        /// the message from the other seat fills the pending hit's chain row
        /// (receipt, then the health change in the finalizer); the shooter's copy
        /// inside its own hit message's scope fills its chain row's damage stamp.</summary>
        internal static void DamageEnter(HealthHandler hh, Vector2 damage, bool outOfBounds, out long state)
        {
            state = 0;
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try { state = DamageBody(hh, damage, outOfBounds); } catch (Exception ex) { Fault(D1, ex); }
            Cost(D1, t0);
        }

        private static long DamageBody(HealthHandler hh, Vector2 damage, bool outOfBounds)
        {
            var g = _g;
            if (g == null || hh == null) return 0;
            var data = hh.GetComponent<CharacterData>();
            if (data == null || data.view == null) return 0;
            bool own = _ownP != null && data == _ownP.data, opp = _oppP != null && data == _oppP.data;
            if (!own && !opp) return 0;
            if (damage == Vector2.zero) return 0;           // the game returns before anything
            int src = outOfBounds ? W.DEATH_CAUSE_OUT_OF_BOUNDS : W.DEATH_CAUSE_DAMAGE;
            if (own) g.LastSrcOwn = src; else g.LastSrcOpp = src;
            int stamp, sender, view; string method;
            if (!RpcTop(D1, out stamp, out sender, out view, out method) || method != "RPCA_SendTakeDamage" || view != data.view.ViewID) return 0;
            if (own && sender == _oppActor && g.VcOn && !g.VcDmg)
            {
                g.VcDmg = true;
                if (g.VcChRow < 0) return 0;
                g.ChS.Raw[g.VcChRow + 4] = ServerNow();
                g.DmgOn = true; g.DmgRow = g.VcChRow; g.DmgHpBefore = data.health;
                return 1;
            }
            if (opp && sender == _localActor && g.ScOn && !g.ScDmg)
            {
                g.ScDmg = true;
                if (g.ScChRow >= 0) g.ChO.Raw[g.ScChRow + 5] = stamp;
            }
            return 0;
        }

        internal static void DamageExit(HealthHandler hh, long state)
        {
            if (!_open || state == 0) return;
            long t0 = Stamp();
            try
            {
                var g = _g;
                var data = hh != null ? hh.GetComponent<CharacterData>() : null;
                if (g != null && g.DmgOn && data != null)
                {
                    g.DmgOn = false;
                    var a = g.ChS.Raw; int o = g.DmgRow;
                    long d = E.RoundEven(g.DmgHpBefore - data.health);
                    a[o + 7] = E.Clamp(d, -99999, 99999);
                    if (data.health != g.DmgHpBefore) { a[o + 5] = ServerNow(); Wait(g, 1, g.ChS, o, 0); }
                }
            }
            catch (Exception ex) { Fault(D1, ex); }
            Cost(D1, t0);
        }

        // -- X1: HealthHandler.RPCA_Die / RPCA_Die_Phoenix prefix (R5 deaths) ------------------------------

        /// <summary>A death as it is applied on this seat (the game's own guard:
        /// playing and not yet dead; a second death message for the same death
        /// fails it and is not listed). The seat's own player lists bd_s, the other
        /// player bd_o; each by that player's death ordinal on this seat, with the
        /// last damage source, the boundary edge the body is past, its position and
        /// velocity, and the last three hits on it.</summary>
        internal static void Die(HealthHandler hh)
        {
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try { DieBody(hh); } catch (Exception ex) { Fault(X1, ex); }
            Cost(X1, t0);
        }

        private static void DieBody(HealthHandler hh)
        {
            var g = _g;
            if (g == null || hh == null) return;
            var data = hh.GetComponent<CharacterData>();
            if (data == null || !data.isPlaying || data.dead || data.playerVel == null) return;
            bool own = _ownP != null && data == _ownP.data, opp = _oppP != null && data == _oppP.data;
            if (!own && !opp) return;
            int now = ServerNow();
            int ord = own ? g.DeathOrdOwn++ : g.DeathOrdOpp++;
            int cause = own ? g.LastSrcOwn : g.LastSrcOpp;
            if (own) g.LastSrcOwn = W.DEATH_CAUSE_UNKNOWN; else g.LastSrcOpp = W.DEATH_CAUSE_UNKNOWN;
            var rows = own ? g.BdS : g.BdO;
            var ring = own ? g.RhOwn : g.RhOpp;
            int head = own ? g.RhOwnHead : g.RhOppHead, n = own ? g.RhOwnN : g.RhOppN;
            if (own) { g.RhOwnN = 0; g.RhOwnHead = 0; } else { g.RhOppN = 0; g.RhOppHead = 0; }
            int o = rows.NextSlot();
            if (o < 0) return;
            var a = rows.Raw; var pos = data.playerVel.position; var vel = data.playerVel.velocity;
            long edge = pos.x <= -OOB_X ? W.EDGE_LEFT : (pos.x >= OOB_X ? W.EDGE_RIGHT : (pos.y >= OOB_Y ? W.EDGE_TOP : (pos.y <= -OOB_Y ? W.EDGE_BOTTOM : W.EDGE_NONE)));
            a[o] = Math.Min(255, ord); a[o + 1] = now; a[o + 2] = cause; a[o + 3] = edge;
            a[o + 4] = Centi(pos.x, 9999999); a[o + 5] = Centi(pos.y, 9999999); a[o + 6] = Centi(vel.x, 9999999); a[o + 7] = Centi(vel.y, 9999999);
            for (int h = 0; h < RECENT_CAP; h++)
            {
                int f = o + 8 + h * 4;
                if (h < n)
                {
                    int i = ((head + n - 1 - h) % RECENT_CAP) * 4;      // h1 = the most recent
                    a[f] = ring[i]; a[f + 1] = ring[i + 1]; a[f + 2] = ring[i + 2];
                    a[f + 3] = E.Clamp(C.WrapDiff(now, ring[i + 3]), 0, 600000);
                }
                else { a[f] = -1; a[f + 1] = 0; a[f + 2] = -1; a[f + 3] = -1; }
            }
        }

        // -- N5: SyncProjectile.OnPhotonSerializeView postfix (reading branch) -------------------------

        internal static void SyncRead(SyncProjectile sp, PhotonStream stream)
        {
            if (!_open || PerfSuspend) return;
            long t0 = Stamp();
            try
            {
                var g = _g;
                if (g != null && sp != null && sp.active && stream != null && !stream.IsWriting)
                {
                    var list = sp.syncPackages;
                    var pv = sp.photonView;
                    if (list != null && list.Count > 0 && pv != null && pv.OwnerActorNr == _oppActor)
                    {
                        g.P3n[5]++;
                        int slot;
                        if (g.Slot.TryGetValue(pv.ViewID, out slot) && g.ALive[slot])
                        {
                            var p = list[list.Count - 1];
                            int i = g.Pack.PushSlot();
                            if (i < 0) g.Drop[D_PACK]++;
                            else
                            {
                                int o = i * 4;
                                g.Pack.V[o] = slot; g.Pack.V[o + 1] = p.vel.x; g.Pack.V[o + 2] = p.vel.y; g.Pack.V[o + 3] = p.timeDelta;
                                g.PackObj[i] = sp;
                            }
                        }
                    }
                }
            }
            catch (Exception ex) { Fault(N5, ex); }
            Cost(N5, t0);
        }

        // -- T: the per-frame tick ------------------------------------------------------------------

        /// <summary>From Plugin's persistent tick. While a game is open: the time
        /// base sums, the two ammunition reads, the own position ring, block
        /// window closes, the reaction sampler, and the deferred arithmetic of the
        /// hooks, each drained under its own per-tick cap. Outside combat only:
        /// the fault notes and the captured records' builds.</summary>
        internal static void Tick()
        {
            try { CombatEvidencePerf.Frame(); } catch { }
            if (_open && !PerfSuspend)
            {
                long t0 = Stamp();
                try { TickBody(); } catch (Exception ex) { Fault(T, ex); }
                Cost(T, t0);
            }
            try
            {
                if (SeatEvidence.CombatLive()) return;
                DrainNotes();
                BuildCaptures(false);
            }
            catch { }
        }

        private static void TickBody()
        {
            var g = _g;
            if (g == null) return;
            ResolvePlayers();
            bool live;
            try { live = SeatEvidence.CombatLive(); } catch (Exception ex) { Fault(T, ex); return; }
            float scale = TimeHandler.timeScale, baseScale = TimeHandler.instance != null ? TimeHandler.instance.baseTimeScale : 1f;
            int now = ServerNow();
            if (live && !g.PointLive) PointStart(g, now, baseScale);
            else if (!live && g.PointLive) PointEnd(g, now);
            // the victim's pending received hit binds only the messages dispatched with it
            if (g.VcOn) { if (!g.VcPush) g.Drop[D_PUSH_EXPIRED]++; g.VcOn = false; g.VcChRow = -1; }
            if (live)
            {
                double unscaled = Time.unscaledDeltaTime, gameDelta = TimeHandler.deltaTime;
                _gameMs += gameDelta * 1000.0;
                g.Pc.Frame(unscaled, gameDelta, Time.deltaTime, scale, baseScale);
                g.Frames.Add((long)(unscaled * 1e6));
                if (g.LastBase >= 0f && baseScale != g.LastBase) g.BaseChanges++;
                g.LastBase = baseScale;
                Bind(g.Own, true); Bind(g.Opp, false);
                Reconcile(g.Own); Reconcile(g.Opp);
                Vector2 p;
                if (PosOf(_ownP, out p))
                {
                    int i = (g.PosHead + g.PosN) % POS_CAP;
                    if (g.PosN < POS_CAP) g.PosN++; else g.PosHead = (g.PosHead + 1) % POS_CAP;
                    g.PosT[i] = now; g.PosX[i] = p.x; g.PosY[i] = p.y;
                }
                CloseWindows(g, now);
                RxSample(now);
            }
            long sw = SwMs;
            if (sw >= g.NextPingMs)
            {
                g.NextPingMs = sw + 1000;
                int ping = PhotonNetwork.GetPing();
                if (ping > 0 && g.PingN < PING_CAP) { g.PingBin[Math.Min(ping, PING_BIN_CAP)]++; g.PingN++; }
            }
            DrainWaits(g, now);
            DrainMasks(g);
            DrainVolleys(g, g.Own, TICK_ROWS_CAP); DrainVolleys(g, g.Opp, TICK_ROWS_CAP);
            DrainAim(g);
            DrainResiduals(g);
            DrainPackages(g);
        }

        private static void PointStart(Game g, int now, float baseScale)
        {
            g.PointLive = true;
            int pt = 0;
            try { pt = PointEvidence.Point; } catch { }
            g.Pc = g.PcStore;
            g.Pc.Reset(pt, now, now, (long)Math.Round(baseScale * 1000.0));
            g.LastBase = baseScale;
            g.RxVis = true; g.RxRowS = -1; g.RxRowO = -1;
            Bind(g.Own, true); Bind(g.Opp, false);
            StatBlock(g, g.Own, g.GunS, pt);
            StatBlock(g, g.Opp, g.GunO, pt);
            PointReset(g.Own, pt);
            PointReset(g.Opp, pt);
        }

        /// <summary>Point end (outside combat): the point's clock row, then every
        /// volley still queued (the whole ring: no combat frame pays for it).</summary>
        private static void PointEnd(Game g, int now)
        {
            g.PointLive = false;
            g.Points++;
            g.RxRowS = -1; g.RxRowO = -1;
            if (g.Pc != null)
            {
                g.Pc.SrvEnd = now;
                int o = g.Tb.NextSlot();
                if (o >= 0) { g.Pc.PointRowInto(0, g.TbRow); Array.Copy(g.TbRow, 0, g.Tb.Raw, o, g.Tb.Width); }
                g.Pc = null;
            }
            DrainVolleys(g, g.Own, RING_CAP); DrainVolleys(g, g.Opp, RING_CAP);
            PointClose(g, g.Own, g.IvlS, now);
            PointClose(g, g.Opp, g.IvlO, now);
        }

        private static void PointReset(GunState s, int pt)
        {
            s.Gmin = -1; s.Vmax = 0; s.Refreshes = 0; s.HasVolley = false; s.WinN = 0; s.WinHead = 0;
            s.CexpMin = -1; ReadCexp(s);
            s.Acct.Point = pt;
        }

        private static void PointClose(Game g, GunState s, E.FixedRows rows, int now)
        {
            {
                s.InAttack = false;
                if (s.MsgPending) { s.MsgPending = false; s.Acct.AddNoInit(); }
                s.FirstPending = false;
                s.Acct.CloseCycle(W.END_POINT, W.SRC_NONE, -1, now, -1, -1, -1);
                s.RlOpen = false;
                int o = rows.NextSlot();
                if (o >= 0)
                {
                    var a = rows.Raw;
                    a[o] = E.Clamp(s.Acct.Point, 0, 99); a[o + 1] = E.Clamp(s.Gmin, -1, 600000); a[o + 2] = E.Clamp(s.CexpMin, -1, 600000);
                    a[o + 3] = E.Clamp(s.Vmax, 0, 9999); a[o + 4] = E.Clamp(s.Vexp, 0, 9999); a[o + 5] = E.Clamp(s.Refreshes, 0, 9999);
                }
            }
        }

        /// <summary>The gun's stat block at point start; an entry only when it
        /// differs from the previous one (design 4.3). The stats the gun lock
        /// discards read as the locked gun fires (M3, Gun.cs): spread 0 (:546
        /// aims along shootPosition.forward), one projectile per template (:423),
        /// one attack (:364), and the cooldown is defaultCooldown (usedCooldown,
        /// :196-205, carried by cexp). `as` stays the raw stat; bursts and the
        /// template count are not changed by the lock.</summary>
        private static void StatBlock(Game g, GunState s, E.FixedRows rows, int pt)
        {
            var gun = s.G; var am = s.A;
            if (gun == null || am == null) return;
            var stats = gun.player != null && gun.player.data != null ? gun.player.data.stats : null;
            bool locked = gun.lockGunToDefault;
            double mult = gun.attackSpeedMultiplier;
            double cexp = mult > 0 ? gun.usedCooldown / mult : 0;
            int attacks = locked ? 1 : (gun.useCharge ? Mathf.Clamp(Mathf.RoundToInt(0.5f / gun.attackSpeed), 1, 10) : 1);
            long spr = 0;
            if (!locked)
            {
                double num2 = gun.spread / ((1f + gun.projectileSpeed * 0.5f) * 0.5f);
                double num = gun.multiplySpread * Math.Max(0.0, 1.0 + (gun.useCharge ? gun.chargeSpreadTo : 0f));
                spr = E.RoundEven(Math.Atan(Math.Abs(num2 * num)) * 1000.0);
            }
            var st = s.StatNew;
            st[0] = pt; st[1] = am.maxAmmo; st[2] = Mil(am.reloadTime); st[3] = Mil(am.reloadTimeAdd); st[4] = Mil(am.reloadTimeMultiplier); st[5] = Mil(am.ReloadTime());
            st[6] = Mil(gun.attackSpeed); st[7] = Mil(mult); st[8] = Mil(cexp); st[9] = locked ? 1 : gun.numberOfProjectiles; st[10] = gun.bursts; st[11] = Mil(gun.timeBetweenBullets); st[12] = Mil(am.ammoReg);
            st[13] = stats != null && stats.automaticReload ? 1 : 0; st[14] = stats != null && stats.refreshOnDamage ? 1 : 0; st[15] = gun.useCharge ? 1 : 0;
            st[16] = locked ? 1 : 0; st[17] = spr; st[18] = gun.projectiles != null ? gun.projectiles.Length : 1;
            var lo = W.LO[E.Ix("gun_s")]; var hi = W.HI[E.Ix("gun_s")];
            for (int i = 0; i < STAT_CAP; i++) st[i] = E.Clamp(st[i], lo[i], hi[i]);
            s.Acct.Mag = st[1]; s.Acct.Rexp = st[5];
            s.Vexp = Math.Max(1, gun.bursts) * (long)attacks;
            bool same = s.HasStat;
            for (int i = 1; same && i < STAT_CAP; i++) if (s.Stat[i] != st[i]) same = false;
            if (same) return;
            s.HasStat = true;
            Array.Copy(st, 0, s.Stat, 0, STAT_CAP);
            int o = rows.NextSlot();
            if (o >= 0) Array.Copy(st, 0, rows.Raw, o, rows.Width);
        }

        private static long Mil(double v) { return E.RoundEven(v * 1000.0); }

        private static void CloseWindows(Game g, int now)
        {
            if (g.OwnWin >= 0)
            {
                g.OwnWinFrames++;
                var b = _ownP != null && _ownP.data != null ? _ownP.data.block : null;
                if (b == null || b.sinceBlock >= 0.3f)
                {
                    var r = g.B5s.Raw; int o = g.OwnWin;
                    r[o + 5] = E.Clamp(C.WrapDiff(now, g.OwnWinStamp), -1, 600000);
                    r[o + 6] = b == null ? -1 : E.Clamp((long)Math.Round(b.sinceBlock * 1000.0), -1, 600000);
                    r[o + 11] = E.Clamp(g.OwnWinFrames, 0, 60000);
                    g.OwnWin = -1;
                }
            }
            if (g.OppWin >= 0)
            {
                g.OppWinFrames++;
                var b = _oppP != null && _oppP.data != null ? _oppP.data.block : null;
                if (b == null || b.sinceBlock >= 0.3f)
                {
                    var r = g.B5o.Raw; int o = g.OppWin;
                    r[o + 6] = E.Clamp(C.WrapDiff(now, g.OppWinStamp), -1, 600000);
                    r[o + 7] = b == null ? -1 : E.Clamp((long)Math.Round(b.sinceBlock * 1000.0), -1, 600000);
                    r[o + 12] = E.Clamp(g.OppWinFrames, 0, 60000);
                    g.OppWin = -1;
                }
            }
        }

        /// <summary>Half the lower median ping (the sorted sample at (n-1)/2), read from
        /// the per-millisecond bins: exact below PING_BIN_CAP ms, no sort (M8).</summary>
        private static int LHatMs(Game g)
        {
            if (g.PingN == 0) return -1;
            long k = (g.PingN - 1) / 2, acc = 0;
            for (int i = 0; i <= PING_BIN_CAP; i++)
            {
                acc += g.PingBin[i];
                if (acc > k) return i / 2;
            }
            return PING_BIN_CAP / 2;
        }

        private static int _lHatCache = -1; private static long _lHatAtMs;

        private static void DrainVolleys(Game g, GunState s, int cap)
        {
            long cexp = s.CexpMin;
            for (int n = 0; n < RING_CAP && n < cap && s.RingN > 0; n++)
            {
                int st = s.Ring[s.RingHead]; s.RingHead = (s.RingHead + 1) % RING_CAP; s.RingN--;
                if (s.WinN > 0)
                {
                    int prev = s.Win[(s.WinHead + s.WinN - 1) % RING_CAP];
                    long gap = C.WrapDiff(st, prev);
                    if (gap >= 0 && (s.Gmin < 0 || gap < s.Gmin)) s.Gmin = gap;
                }
                if (s.WinN >= RING_CAP) { s.WinHead = (s.WinHead + 1) % RING_CAP; s.WinN--; }
                s.Win[(s.WinHead + s.WinN) % RING_CAP] = st; s.WinN++;
                for (int k = 0; k < RING_CAP && s.WinN > 0 && cexp >= 0 && C.WrapDiff(st, s.Win[s.WinHead]) >= cexp; k++)
                { s.WinHead = (s.WinHead + 1) % RING_CAP; s.WinN--; }
                if (s.WinN > s.Vmax) s.Vmax = s.WinN;
            }
        }

        private static void DrainMasks(Game g)
        {
            for (int n = 0; n < TICK_ROWS_CAP; n++)
            {
                int i = g.Mask.PopSlot();
                if (i < 0) return;
                var obj = g.MaskObj[i]; g.MaskObj[i] = null;
                int slot = (int)g.Mask.V[i * 2]; bool own = g.Mask.V[i * 2 + 1] != 0;
                if (obj == null) { g.Drop[D_MASK_UNSCANNED]++; continue; }   // gone before its scan: UNKNOWN, never 0
                int mask = SteerMask(obj);
                if (own)
                {
                    for (int b = 0; b < MASK_BIT_CAP; b++) if ((mask & (1 << b)) != 0) g.P3self[1 + b]++;
                    continue;
                }
                if (slot >= 0 && slot < ANCHOR_CAP && g.ALive[slot] && g.AObj[slot] == obj)
                {
                    g.AMask[slot] = mask; g.AMaskKnown[slot] = true;
                    if (mask != 0) g.P3n[1]++;
                }
            }
        }

        /// <summary>The steering components present on a projectile (design 5.1).</summary>
        internal static int SteerMask(GameObject o)
        {
            int m = 0;
            if (o.GetComponentInChildren<Homing>() != null) m |= W.STEER_BITS_HOMING;
            if (o.GetComponentInChildren<BounceEffectRetarget>() != null) m |= W.STEER_BITS_TARGET_BOUNCE;
            if (o.GetComponentInChildren<ScreenEdgeBounce>() != null) m |= W.STEER_BITS_EDGE_BOUNCE;
            if (o.GetComponentInChildren<RemoteControl>() != null) m |= W.STEER_BITS_REMOTE;
            if (o.GetComponentInChildren<DodgeGround>() != null) m |= W.STEER_BITS_DODGE;
            if (o.GetComponentInChildren<TracerTarget>() != null || o.GetComponentInChildren<Zop>() != null || o.GetComponentInChildren<BulletPoint>() != null
                || o.GetComponentInChildren<Cos>() != null || o.GetComponentInChildren<MoveTransformGravity>() != null) m |= W.STEER_BITS_LOCAL;
            if (o.GetComponentInChildren<RayHitDrill>() != null) m |= W.STEER_BITS_DRILL;
            if (o.GetComponentInChildren<Accelerate>() != null) m |= W.STEER_BITS_ACCELERATE;
            return m;
        }

        private static void DrainAim(Game g)
        {
            long sw = SwMs;
            if (sw - _lHatAtMs > 5000 || _lHatCache < 0) { _lHatCache = LHatMs(g); _lHatAtMs = sw; }
            int lhat = _lHatCache < 0 ? 0 : _lHatCache;
            for (int n = 0; n < TICK_ROWS_CAP; n++)
            {
                int o = g.Aim.PopRow();
                if (o < 0) return;
                var v = g.Aim.V;
                int kind = (int)v[o]; int stamp = (int)v[o + 1];
                double px = v[o + 2], py = v[o + 3], fx = v[o + 4], fy = v[o + 5];
                if (kind == 0 || kind == 1)
                {
                    Vector2 t;
                    if (!PosOf(_oppP, out t)) continue;
                    bool sight = Sight(g, new Vector2((float)px, (float)py), _oppP);
                    long err = SignedMrad(fx, fy, t.x - px, t.y - py);
                    if (kind == 0) g.A1s.Add(err, !sight); else g.A1p.Add(err, !sight);
                    continue;
                }
                if (g.PosN == 0 || _ownP == null) continue;
                // a1m: own position at (stamp - L^); a1n: the nearest over [stamp - 2L^ - W, stamp]
                int want = stamp - lhat, lo = stamp - 2 * lhat - E.A1N_W_MS;
                int best = -1; long bestD = long.MaxValue; long bestErr = 0; bool haveN = false;
                for (int k = 0; k < g.PosN && k < POS_CAP; k++)
                {
                    int i = (g.PosHead + k) % POS_CAP;
                    long d = Math.Abs((long)C.WrapDiff(g.PosT[i], want));
                    if (d < bestD) { bestD = d; best = i; }
                    if (C.WrapDiff(g.PosT[i], lo) >= 0 && C.WrapDiff(stamp, g.PosT[i]) >= 0)
                    {
                        long e = SignedMrad(fx, fy, g.PosX[i] - px, g.PosY[i] - py);
                        if (!haveN || Math.Abs(e) < Math.Abs(bestErr)) { bestErr = e; haveN = true; }
                    }
                }
                bool vis = Sight(g, new Vector2((float)px, (float)py), _ownP);
                if (best >= 0) g.A1m.Add(SignedMrad(fx, fy, g.PosX[best] - px, g.PosY[best] - py), !vis);
                if (haveN) g.A1n.Add(bestErr, !vis);
            }
        }

        /// <summary>The game's own line-of-sight rule (PlayerManager.CanSeePlayer: a
        /// cast from `from` to the player's body under canSeePlayerMask, blocked by
        /// any hit whose root is neither a spawned attack nor a player) without its
        /// per-call allocations (M8).</summary>
        private static bool Sight(Game g, Vector2 from, Player p)
        {
            Vector2 to;
            if (!PosOf(p, out to)) return false;
            return Clear(g, from, to);
        }

        private static bool Clear(Game g, Vector2 from, Vector2 to)
        {
            var pm = PlayerManager.instance;
            if (pm == null) return true;
            Vector2 d = to - from;
            float dist = d.magnitude;
            if (!(dist > 0f)) return true;
            int n = Physics2D.RaycastNonAlloc(from, d / dist, g.Ray, dist, pm.canSeePlayerMask);
            if (n >= RAY_CAP) g.Drop[D_RAY_FULL]++;
            for (int i = 0; i < n && i < RAY_CAP; i++)
            {
                var tr = g.Ray[i].transform;
                if (tr == null) continue;
                var root = tr.root;
                if (root.GetComponent<SpawnedAttack>() == null && root.GetComponent<Player>() == null) return false;
            }
            return true;
        }

        internal static long SignedMrad(double fx, double fy, double tx, double ty)
        {
            if ((fx == 0 && fy == 0) || (tx == 0 && ty == 0)) return 0;
            return E.Clamp(E.RoundEven(Math.Atan2(tx * fy - ty * fx, tx * fx + ty * fy) * 1000.0), -3142, 3142);
        }

        // -- RX: the reaction sampler (design V2 B1 reaction; A1 capability bit) ----------------------

        /// <summary>About thirty samples a second while a point is live: one
        /// non-allocating cast between the two bodies under the game's sight rule.
        /// An onset is the first visible sample after a hidden run (the start of a
        /// point counts as visible: no onset until the players first lose sight).
        /// At each onset each side's row opens: the aim error then (mrad, from the
        /// side's aim direction less the game's upward aim term), the time until
        /// the aim is first inside the other body's angular radius, and the time
        /// until that side's first volley. A row closes when sight is lost, a body
        /// is gone, or the point ends.</summary>
        /// The sampler runs only in a build whose A1 sections are live (it costs
        /// a ray per sample and its rows travel only under CAPS_A1). Its time is
        /// also inside row T, which encloses it.
        internal static void RxSample(int now)
        {
            if (!A1Live || _g == null || SwMs < _g.RxNextMs) return;
            long t0 = Stamp();
            try { var g = _g; g.RxNextMs = SwMs + RX_PERIOD_MS; RxBody(g, now); } catch (Exception ex) { Fault(RX, ex); }
            Cost(RX, t0);
        }

        private static void RxBody(Game g, int now)
        {
            Vector2 a, b;
            if (!PosOf(_ownP, out a) || !PosOf(_oppP, out b) || _ownP.data.dead || _oppP.data.dead)
            { g.RxRowS = -1; g.RxRowO = -1; g.RxVis = true; return; }
            g.A1Tot[3]++;
            if (!Clear(g, a, b)) { g.RxRowS = -1; g.RxRowO = -1; g.RxVis = false; return; }
            if (!g.RxVis)
            {
                g.RxVis = true; g.RxOnset = now;
                g.RxRowS = RxOpen(g.RxS, _ownP, a, b, now);
                g.RxRowO = RxOpen(g.RxO, _oppP, b, a, now);
                return;
            }
            RxAim(g, g.RxS, g.RxRowS, _ownP, a, b, now);
            RxAim(g, g.RxO, g.RxRowO, _oppP, b, a, now);
        }

        /// <summary>The aim error (mrad) of player p at `from` toward `to`, and the
        /// other body's angular radius from `from` (mrad); 3142 when p has no aim.</summary>
        private static long AimErr(Player p, Vector2 from, Vector2 to, Player other, out long radius)
        {
            radius = 0;
            var d = p.data;
            double dx = to.x - from.x, dy = to.y - from.y, dist = Math.Sqrt(dx * dx + dy * dy);
            var col = other != null && other.data != null ? other.data.mainCol : null;
            if (col != null && dist > 0) radius = E.RoundEven(Math.Atan2(col.bounds.extents.x, dist) * 1000.0);
            if (d.input == null) return 3142;
            Vector3 aim = d.input.aimDirection;
            if (aim == Vector3.zero) return 3142;
            var gun = d.weaponHandler != null ? d.weaponHandler.gun : null;
            float ps = gun != null ? gun.projectileSpeed : 1f;
            aim -= Vector3.up * 0.13f / Mathf.Clamp(ps, 1f, 100f);
            if (aim.x == 0f && aim.y == 0f) return 3142;
            return Math.Abs(SignedMrad(aim.x, aim.y, dx, dy));
        }

        private static int RxOpen(E.FixedRows rows, Player p, Vector2 from, Vector2 to, int now)
        {
            int o = rows.NextSlot();
            if (o < 0) return -1;
            long radius;
            long err = AimErr(p, from, to, p == _ownP ? _oppP : _ownP, out radius);
            var a = rows.Raw;
            a[o] = now; a[o + 1] = err <= radius ? 0 : -1; a[o + 2] = -1; a[o + 3] = E.Clamp(err, 0, 3142);
            return o;
        }

        private static void RxAim(Game g, E.FixedRows rows, int o, Player p, Vector2 from, Vector2 to, int now)
        {
            if (o < 0) return;
            var a = rows.Raw;
            if (a[o + 1] >= 0) return;
            long radius;
            long err = AimErr(p, from, to, p == _ownP ? _oppP : _ownP, out radius);
            if (err <= radius) a[o + 1] = E.Clamp(C.WrapDiff(now, g.RxOnset), 0, 600000);
        }

        /// <summary>A volley's stamp (from the init prefix): the open row's first volley after the onset.</summary>
        private static void RxVolley(Game g, bool own, int stamp)
        {
            int o = own ? g.RxRowS : g.RxRowO;
            if (o < 0) return;
            var a = own ? g.RxS.Raw : g.RxO.Raw;
            if (a[o + 2] >= 0) return;
            long d = C.WrapDiff(stamp, g.RxOnset);
            if (d >= 0) a[o + 2] = Math.Min(d, 600000);
        }

        // -- the deferred residual and homing arithmetic -------------------------------------------

        private static void DrainResiduals(Game g)
        {
            for (int n = 0; n < TICK_ROWS_CAP; n++)
            {
                int o = g.Res.PopRow();
                if (o < 0) return;
                var r = g.Res.V;
                int slot = (int)r[o]; int pid = (int)r[o + 1]; int stamp = (int)r[o + 2]; double dTms = r[o + 3];
                var copy = new E.St((float)r[o + 4], (float)r[o + 5], (float)r[o + 6], (float)r[o + 7]);
                var owner = new E.St((float)r[o + 8], (float)r[o + 9], (float)r[o + 10], (float)r[o + 11]);
                var prm = new E.MovePrm { Gravity = (float)r[o + 12], Drag = (float)r[o + 13], DragMin = (float)r[o + 14], Mult = (float)r[o + 15],
                                          Sim = (float)r[o + 16], AllowStop = r[o + 17] != 0, SimGravity = (int)r[o + 18] };
                double k = r[o + 19];
                bool edged = r[o + 20] != 0;
                bool slotOk = slot >= 0 && slot < ANCHOR_CAP && g.APid[slot] == pid;
                bool known = slotOk && g.AMaskKnown[slot];
                int mask = slotOk ? g.AMask[slot] : 0;
                // A1: an edge bounce since the anchor leaves no comparable prediction (F4);
                // an unscanned mask is UNKNOWN and the sample joins no steering histogram
                if (A1Live && edged) { g.Drop[D_RES_INCOMPARABLE]++; continue; }
                bool unknown = A1Live && !known;
                if (unknown) g.Drop[D_RES_MASK_UNKNOWN]++;
                // the side that is behind is flown forward by |dT| x k in fixed steps (design 5.2, M7)
                double span = Math.Abs(dTms) / 1000.0 * k;
                var res = g.ResOut;
                if (dTms >= 0) E.ResidualInto(E.IntegrateSpan(owner, span, E.PRED_STEP_S, prm), copy, res);
                else E.ResidualInto(E.IntegrateSpan(copy, span, E.PRED_STEP_S, prm), owner, res);
                if (!unknown)
                {
                    bool steer = mask != 0;
                    (steer ? g.P3dp1 : g.P3dp0)[E.Bin(E.PERP_EDGES, res[0])]++;
                    (steer ? g.P3an1 : g.P3an0)[E.Bin(E.ANG_EDGES, res[2])]++;
                }
                long speed = E.RoundEven(E.Hypot(owner.VX, owner.VY) * W.CENTI);
                var e = g.TopEntry;
                e[0] = pid; e[1] = stamp; e[2] = E.Clamp(res[0], 0, 9999999); e[3] = E.Clamp(res[1], -9999999, 9999999); e[4] = E.Clamp(res[2], 0, 3142);
                e[5] = E.Clamp((long)Math.Round(Math.Abs(dTms)), 0, 600000); e[6] = E.Clamp(speed, 0, 999999); e[7] = unknown ? E.MASK_UNKNOWN : mask;
                g.P3topSeen++;
                TopInsert(g.Top, ref g.TopN, TOP_CAP, 8, e, 2);
            }
        }

        /// <summary>Keeps the `cap` rows with the largest field `key` (ties: the
        /// earlier row stays), in descending order. Bounded by ROWS_CAP.</summary>
        private static void TopInsert(long[] a, ref int n, int cap, int w, long[] e, int key)
        {
            int pos = n;
            for (int i = 0; i < n && i < ROWS_CAP; i++) if (e[key] > a[i * w + key]) { pos = i; break; }
            if (pos >= cap) return;
            int last = Math.Min(n, cap - 1);
            for (int j = 0, i = last; j < ROWS_CAP && i > pos; j++, i--) Array.Copy(a, (i - 1) * w, a, i * w, w);
            Array.Copy(e, 0, a, pos * w, w);
            if (n < cap) n++;
        }

        private static void DrainPackages(Game g)
        {
            for (int n = 0; n < TICK_ROWS_CAP; n++)
            {
                int i = g.Pack.PopSlot();
                if (i < 0) return;
                var sp = g.PackObj[i]; g.PackObj[i] = null;
                int o = i * 4; var v = g.Pack.V;
                int slot = (int)v[o]; float vx = (float)v[o + 1], vy = (float)v[o + 2], dt = (float)v[o + 3];
                if (slot < 0 || slot >= ANCHOR_CAP || !g.ALive[slot]) continue;
                if (!g.AHomChecked[slot])
                {
                    g.AHomChecked[slot] = true;
                    var h = sp != null ? sp.GetComponentInChildren<Homing>() : null;
                    var mv = sp != null ? sp.GetComponent<MoveTransform>() : null;
                    g.AHomAmount[slot] = h != null ? h.amount : 0f;
                    g.AHomForce[slot] = mv != null ? mv.localForce.magnitude : 0f;
                }
                if (g.AHomAmount[slot] == 0f) continue;
                g.AHomN[slot]++;
                if (g.AHasPack[slot])
                {
                    long ratio = E.HomingRatio(dt, g.APvx[slot], g.APvy[slot], vx, vy, g.AHomForce[slot], g.AHomAmount[slot]);
                    if (ratio >= 0)
                    {
                        g.P3hm[E.Bin(E.HOMING_EDGES, ratio)]++;
                        if (ratio > g.AHomMax[slot]) g.AHomMax[slot] = ratio;
                        HtUpsert(g, g.APid[slot], g.ASInit[slot], g.AHomMax[slot], g.AHomN[slot]);
                    }
                }
                g.AHasPack[slot] = true; g.APvx[slot] = vx; g.APvy[slot] = vy;
            }
        }

        private static void HtUpsert(Game g, int pid, int sInit, long ratio, long n)
        {
            for (int i = 0; i < g.HtN && i < HT_CAP; i++)
            {
                if (g.Ht[i * 4] != pid) continue;
                // remove and reinsert at its new rank
                for (int m = 0, k = i; m < HT_CAP && k < g.HtN - 1; m++, k++) Array.Copy(g.Ht, (k + 1) * 4, g.Ht, k * 4, 4);
                g.HtN--;
                break;
            }
            g.P3htSeen++;
            var e = g.HtEntry;
            e[0] = pid; e[1] = sInit; e[2] = E.Clamp(ratio, 0, 99999); e[3] = E.Clamp(n, 0, 99999);
            TopInsert(g.Ht, ref g.HtN, HT_CAP, 4, e, 2);
        }

        // -- the game-over capture and the build ----------------------------------------------------

        private sealed class Capture
        {
            internal Game G; internal long[][] Cost; internal long Producers; internal bool A1;
            internal string Seat, Other, Attach, Text, Env; internal int T0; internal bool FromToken;
        }

        /// <summary>A14: set by the frame-time probe's B windows (collectors suspended).</summary>
        internal static bool PerfSuspend;

        private const int CAPTURE_CAP = 4;
        private static readonly List<Capture> _captures = new List<Capture>(CAPTURE_CAP + 1);
        private static long _nextCaptureTryMs;
        private static bool _captureFailLogged;
        private static string _note;

        /// <summary>Beside SeatEvidence.Dispatch (game over, a game cut short, the
        /// quit hook). Ranked 1v1 only, both seats. O(1): the game's collectors
        /// are taken by reference and the cost rows copied; the build is the
        /// tick's (or the quitting path's).</summary>
        internal static void Dispatch(string seat, string other, string attach, bool rankedNow)
        {
            try
            {
                bool live = _open;
                bool frozen = !live && _frozen && SwMs - _frozenAtMs <= SeatEvidence.FROZEN_MS
                              && _room.Length > 0 && attach != null && attach.StartsWith(_room + "_", StringComparison.Ordinal);
                if (!live && !frozen) return;
                _open = false; _frozen = false;
                var g = _g; _g = null;
                if (!rankedNow || g == null) return;
                if (CombatEvidencePerf.Contaminated)
                {
                    CombatEvidencePerf.Contaminated = false;
                    _note = " no record: the frame-time probe suspended the collectors in this game";
                    return;
                }
                bool fromToken;
                int t0 = GameStateWatcher.SeatEvidenceT0(out fromToken);
                var cost = new long[COST_CAP][];
                for (int i = 0; i < COST_CAP; i++)
                    cost[i] = new long[] { _calls[i], _ticks[i], _maxTicks[i], _faults[i] };
                if (_captures.Count >= CAPTURE_CAP) { _captures.RemoveAt(0); _note = " a captured record was dropped before it was persisted: too many waiting"; }
                _captures.Add(new Capture { G = g, Cost = cost, Producers = Producers, A1 = A1Live, Seat = seat, Other = other, Attach = attach, T0 = t0, FromToken = fromToken });
                _nextCaptureTryMs = 0;
            }
            catch { _note = " no record: the capture failed"; }
        }

        private static void DrainNotes()
        {
            for (int i = 0; i < COST_ALL; i++)
            {
                string n = _faultNote[i];
                if (n == null) continue;
                _faultNote[i] = null;
                try { Plugin.Log.LogWarning(TAG + " collector " + i.ToString(CultureInfo.InvariantCulture) + " fault (counted, once per game): " + n); } catch { }
            }
            if (_note != null) { string n = _note; _note = null; try { Plugin.Log.LogWarning(TAG + n); } catch { } }
        }

        /// <summary>The cost rows each R-section's rows are produced by: a fault on any
        /// of them in the game withholds that section's bit (its lists may be short).</summary>
        private static readonly int[][] SECTION_ROWS =
        {
            new[] { K2, K3, H1, P1, T },              // push (T reads the after-position through the wait ring)
            new[] { K2, K3, H1, N3, N4, E1, S1 },     // velocity changes and bounce selections
            new[] { K1, K2, K3, H1, D1, N7, N1, T },  // the hit chain (K1 the message stamps, N1 the decision, T the frame)
            new[] { K2, K3, D1, X1 },                 // deaths
        };
        private static readonly long[] SECTION_BITS = { W.CAPS_PUSH, W.CAPS_VCHG, W.CAPS_CHAIN, W.CAPS_DEATH };

        /// <summary>The R-section bits this record states: proved attached at boot,
        /// with no producer fault and no unkeyed event in the game.</summary>
        internal static long SectionCaps(long producers, long voided, long[][] cost)
        {
            long caps = producers & PRODUCERS & ~voided;
            for (int s = 0; s < SECTION_BITS.Length; s++)
                for (int k = 0; k < SECTION_ROWS[s].Length; k++)
                    if (cost[SECTION_ROWS[s][k]][3] > 0) caps &= ~SECTION_BITS[s];
            return caps;
        }

        /// <summary>The record of a captured game (every layout key, full lists;
        /// the budgeter trims). Close of the last point happens here when the
        /// game ended inside one. With A1Live clear the record is the current
        /// layout; with it set, caps carries A1 (and RX when the sampler ran
        /// without a fault) and the A1 part follows omit.</summary>
        private static E.Rec Build(Capture c)
        {
            var g = c.G;
            if (g.PointLive) PointEnd(g, ServerNow());
            var r = E.Empty();
            long caps = SectionCaps(c.Producers, g.Void, c.Cost);
            bool a1 = c.A1;
            // RX: the sampler ran (calls > 0) and neither it nor the tick that drives it faulted
            if (a1) { caps |= E.CAPS_A1; if (c.Cost[RX][0] > 0 && c.Cost[RX][3] == 0 && c.Cost[T][3] == 0) caps |= E.CAPS_RX; }
            r["schema"] = (long)W.SCHEMA; r["consts"] = 1L; r["caps"] = caps;
            r["t0"] = (long)c.T0; r["t0_src"] = c.FromToken ? "m" : "o";
            r["frame_p50_us"] = E.Clamp(g.Frames.Median(), 0, 1000000);
            var cost = new List<long[]>(W.COLLECTORS);
            for (int i = 0; i < W.COLLECTORS; i++) cost.Add(CostRow(c.Cost[i]));
            r["cost"] = cost;
            r["l_hat"] = (long)LHatMs(g);
            var tb = g.Tb.Rows();
            r["tb_tot"] = E.TbTot(tb, g.BaseChanges, g.Points);
            r["tb"] = tb;
            r["a1s"] = g.A1s.HistClamped(); r["a1p"] = g.A1p.HistClamped(); r["a1m"] = g.A1m.HistClamped(); r["a1n"] = g.A1n.HistClamped();
            r["a1sum"] = new List<long[]> { g.A1s.Summary(), g.A1p.Summary(), g.A1m.Summary(), g.A1n.Summary() };
            r["rx_s"] = g.RxS.Rows(); r["rx_o"] = g.RxO.Rows();
            r["gun_s"] = g.GunS.Rows(); r["gun_o"] = g.GunO.Rows();
            r["tot_s"] = g.Own.Acct.TotRow(); r["tot_o"] = g.Opp.Acct.TotRow();
            r["ivl_s"] = g.IvlS.Rows(); r["ivl_o"] = g.IvlO.Rows();
            r["cx_s"] = g.Own.Acct.CxRows(); r["cx_o"] = g.Opp.Acct.CxRows();
            r["sh_s"] = g.Own.Acct.Groups(); r["sh_o"] = g.Opp.Acct.Groups();
            r["p3n"] = Clamped("p3n", g.P3n);
            r["p3dp0"] = Hist(g.P3dp0); r["p3an0"] = Hist(g.P3an0); r["p3dp1"] = Hist(g.P3dp1); r["p3an1"] = Hist(g.P3an1); r["p3hm"] = Hist(g.P3hm);
            r["p3self"] = Clamped("p3self", g.P3self);
            r["p3top"] = Rows(g.Top, g.TopN, 8); r["p3tb"] = g.P3tb.Rows(); r["p3ht"] = Rows(g.Ht, g.HtN, 4);
            r["b5_tot"] = Clamped("b5_tot", g.B5tot);
            r["b5_s"] = g.B5s.Rows(); r["b5_o"] = g.B5o.Rows(); r["b5_h"] = g.B5h.Rows(); r["b5_c"] = g.B5c.Rows(); r["b5_r"] = g.B5r.Rows();
            var om = r.Omit;
            om[E.OmitPos("rx_s")] = g.RxS.Omitted; om[E.OmitPos("rx_o")] = g.RxO.Omitted;
            om[E.OmitPos("gun_s")] = g.GunS.Omitted; om[E.OmitPos("gun_o")] = g.GunO.Omitted;
            om[E.OmitPos("ivl_s")] = g.IvlS.Omitted; om[E.OmitPos("ivl_o")] = g.IvlO.Omitted;
            om[E.OmitPos("tb")] = g.Tb.Omitted;
            om[E.OmitPos("cx_s")] = g.Own.Acct.CxOmitted; om[E.OmitPos("cx_o")] = g.Opp.Acct.CxOmitted;
            om[E.OmitPos("sh_s")] = g.Own.Acct.GroupsOmitted; om[E.OmitPos("sh_o")] = g.Opp.Acct.GroupsOmitted;
            om[E.OmitPos("p3top")] = g.P3topSeen - g.TopN; om[E.OmitPos("p3tb")] = g.P3tb.Omitted;
            om[E.OmitPos("p3ht")] = Math.Max(0, CountDistinctHoming(g) - g.HtN);
            om[E.OmitPos("b5_s")] = g.B5s.Omitted; om[E.OmitPos("b5_o")] = g.B5o.Omitted; om[E.OmitPos("b5_h")] = g.B5h.Omitted;
            om[E.OmitPos("b5_c")] = g.B5c.Omitted; om[E.OmitPos("b5_r")] = g.B5r.Omitted;
            // the addendum's sections: a section whose bit is clear is empty with zero counts
            var rt = new long[8];
            Section(r, rt, caps, W.CAPS_PUSH, "push_s", g.PushS, 0); Section(r, rt, caps, W.CAPS_PUSH, "push_o", g.PushO, 1);
            Section(r, rt, caps, W.CAPS_VCHG, "vchg", g.Vchg, 2); Section(r, rt, caps, W.CAPS_VCHG, "bsel", g.Bsel, 3);
            Section(r, rt, caps, W.CAPS_CHAIN, "ch_s", g.ChS, 4); Section(r, rt, caps, W.CAPS_CHAIN, "ch_o", g.ChO, 5);
            Section(r, rt, caps, W.CAPS_DEATH, "bd_s", g.BdS, 6); Section(r, rt, caps, W.CAPS_DEATH, "bd_o", g.BdO, 7);
            r["r_tot"] = rt;
            if (a1)
            {
                var p = new E.A1Part();
                for (int i = 0; i < p.Drop.Length; i++) p.Drop[i] = E.Clamp(g.Drop[i], 0, E.A1_HI);
                p.Tot[0] = E.Clamp(g.A1Tot[0], 0, E.A1_HI);
                p.Tot[1] = E.Clamp(g.RxS.Total, 0, E.A1_HI); p.Tot[2] = E.Clamp(g.RxO.Total, 0, E.A1_HI);
                p.Tot[3] = E.Clamp(g.A1Tot[3], 0, E.A1_HI);
                for (int i = W.COLLECTORS; i < COST_ALL; i++) p.Cost.Add(CostRow(c.Cost[i]));
                r.A1 = p;
            }
            E.ClampToLayout(r);
            return r;
        }

        private static long[] CostRow(long[] c)
        {
            return new long[] { E.Clamp(c[0], 0, 99999999), E.Clamp(Us(c[1]), 0, 2147483647), E.Clamp(Us(c[2]), 0, 99999999), E.Clamp(c[3], 0, 99999999) };
        }

        /// <summary>One addendum list: with its bit set, the rows the game kept, the
        /// rows its cap omitted, and its whole-game count (every entry the producer
        /// listed, kept or omitted, so len + omit == r_tot); with it clear, nothing.</summary>
        private static void Section(E.Rec r, long[] rt, long caps, long bit, string key, E.FixedRows rows, int ix)
        {
            if ((caps & bit) == 0) { r[key] = new List<long[]>(); r.Omit[E.OmitPos(key)] = 0; rt[ix] = 0; return; }
            r[key] = rows.Rows();
            long total = Math.Min(rows.Total, 9999);
            long omit = Math.Max(0, total - rows.Count);
            r.Omit[E.OmitPos(key)] = omit;
            rt[ix] = total;
        }

        private static long CountDistinctHoming(Game g)
        {
            long n = 0;
            for (int i = 0; i < ANCHOR_CAP; i++) if (g.ALive[i] && g.AHomMax[i] >= 0) n++;
            return Math.Max(n, g.HtN);
        }

        private static long[] Hist(long[] h)
        {
            var o = new long[h.Length];
            for (int i = 0; i < h.Length; i++) o[i] = E.Clamp(h[i], 0, 99999);
            return o;
        }

        private static long[] Clamped(string key, long[] v)
        {
            int k = E.Ix(key);
            var o = new long[v.Length];
            for (int i = 0; i < v.Length; i++) o[i] = E.Clamp(v[i], W.LO[k][i], W.HI[k][i]);
            return o;
        }

        private static List<long[]> Rows(long[] a, int n, int w)
        {
            var o = new List<long[]>(n);
            for (int i = 0; i < n; i++) o.Add(E.Slice(a, i * w, w));
            return o;
        }

        private static void BuildCaptures(bool quitting)
        {
            if (_captures.Count == 0) return;
            if (!quitting && SwMs < _nextCaptureTryMs) return;
            bool ready = false;
            try { ready = SeatEvidence.IdentityReady; } catch { }
            if (!ready)
            {
                if (quitting) { try { SeatEvidence.CompleteIdentityNow(); } catch { } }
                else { try { SeatEvidence.StartHashing(); } catch { } return; }
            }
            int i = 0;
            while (i < _captures.Count)
            {
                var c = _captures[i];
                try
                {
                    string stable = c.Env == null ? SeatEvidence.StableOf(c.Attach) : null;
                    if (c.Env == null)
                    {
                        if (stable == null || !C.IsSteamId(c.Seat) || !C.IsSteamId(c.Other))
                        {
                            _captures.RemoveAt(i);
                            Plugin.Log.LogWarning(TAG + " no record: game key or seat ids outside the contract");
                            continue;
                        }
                        var rec = Build(c);
                        string bad = E.Check(rec);
                        if (bad != null)
                        {
                            _captures.RemoveAt(i);
                            Plugin.Log.LogWarning(TAG + " no record: field outside the layout: " + bad);
                            continue;
                        }
                        string text = E.Budget(rec);
                        string sig = ApiClient.SeatEvidenceSig(E.Canonical(c.Seat, c.Other, stable, c.Attach, text));
                        string env = E.Envelope(c.Seat, c.Other, stable, c.Attach, text, sig);
                        if (env == null)
                        {
                            _captures.RemoveAt(i);
                            Plugin.Log.LogWarning(TAG + " no record: the envelope is outside the contract");
                            continue;
                        }
                        c.Text = text; c.Env = env; c.G = null;
                    }
                    bool persisted = quitting ? SeatEvidence.SpoolClosing("x", c.Env) : SeatEvidence.EnqueueCombat(c.Env);
                    if (!persisted)
                    {
                        _nextCaptureTryMs = SwMs + 5000;
                        if (!_captureFailLogged)
                        {
                            _captureFailLogged = true;
                            Plugin.Log.LogWarning(TAG + " record not persisted yet (the queue file was not replaced): kept and tried again");
                        }
                        return;
                    }
                    _captures.RemoveAt(i);
                    _captureFailLogged = false;
                    Plugin.Log.LogInfo(TAG + (quitting ? " record kept for the next launch: " : " record queued: ")
                        + c.Text.Length.ToString(CultureInfo.InvariantCulture) + " bytes");
                }
                catch (Exception ex)
                {
                    _captures.RemoveAt(i);
                    try { Plugin.Log.LogWarning(TAG + " no record: " + ex.GetType().Name); } catch { }
                }
            }
        }

        /// <summary>Application.quitting, after the seat evidence quit flush.</summary>
        internal static void FlushOnQuit()
        {
            try { DrainNotes(); BuildCaptures(true); } catch { }
        }

        // -- the boot census (L1) ---------------------------------------------------------------------

        /// <summary>Every intended combat patch: patch class, target type, target
        /// method, and the parts it must have attached (p prefix, o postfix, f finalizer).</summary>
        internal static readonly string[][] HOOKS =
        {
            new[] { "CombatEvidence_AttackPatch", "Gun", "Attack", "po" },
            new[] { "CombatEvidence_InitAmmoPatch", "ProjectileInit", "RPCA_Init", "pf" },
            new[] { "CombatEvidence_InitNoAmmoPatch", "ProjectileInit", "RPCA_Init_noAmmoUse", "p" },
            new[] { "CombatEvidence_InitSeparatePatch", "ProjectileInit", "RPCA_Init_SeparateGun", "p" },
            new[] { "CombatEvidence_ReloadPatch", "GunAmmo", "ReloadAmmo", "p" },
            new[] { "CombatEvidence_HitPatch", "ProjectileHit", "RPCA_DoHit", "pf" },
            new[] { "CombatEvidence_ContactPatch", "ProjectileHit", "Hit", "p" },
            new[] { "CombatEvidence_BlockPatch", "Block", "RPCA_DoBlock", "f" },
            new[] { "CombatEvidence_TryBlockPatch", "Block", "TryBlock", "po" },
            new[] { "CombatEvidence_DealtPatch", "CharacterStatModifiers", "DealtDamage", "o" },
            new[] { "CombatEvidence_TargetBouncePatch", "BounceEffectRetarget", "SetNewVel", "p" },
            new[] { "CombatEvidence_EdgeBouncePatch", "ScreenEdgeBounce", "DoHit", "pf" },
            new[] { "CombatEvidence_SyncPatch", "SyncProjectile", "OnPhotonSerializeView", "o" },
            new[] { "CombatEvidence_ForcePatch", "HealthHandler", "RPCA_SendTakeForce", "pf" },
            new[] { "CombatEvidence_DamagePatch", "HealthHandler", "RPCA_SendTakeDamage", "pf" },
            new[] { "CombatEvidence_DiePatch", "HealthHandler", "RPCA_Die", "p" },
            new[] { "CombatEvidence_DiePhoenixPatch", "HealthHandler", "RPCA_Die_Phoenix", "p" },
            new[] { "CombatEvidence_FindTargetPatch", "BounceEffectRetarget", "FindTarget", "o" },
        };

        /// <summary>The shared RPC frame every keyed row reads (RpcTop) and the send hook (RpcSent).</summary>
        internal static readonly string[][] FRAME_HOOKS =
        {
            new[] { "HitEvidence_ExecuteRpcPatch", "PhotonNetwork", "ExecuteRpc", "" },
            new[] { "SeatEvidence_RpcSendPatch", "PhotonNetwork", "RPC", "" },
        };

        /// <summary>The hooks (HOOKS indexes) each R-section's rows depend on, beside the frame.</summary>
        private static readonly int[][] SECTION_HOOKS =
        {
            new[] { 1, 2, 3, 5, 13 },             // push: inits (anchors), the hit message, the force
            new[] { 1, 2, 3, 5, 10, 11, 17 },     // velocity changes and selections
            new[] { 1, 2, 3, 5, 6, 14 },          // the chain: hit message, contact (decision), damage
            new[] { 1, 2, 3, 5, 14, 15, 16 },     // deaths: recent hits, damage source, both deaths
        };

        /// <summary>After Harmony's PatchAll (Plugin.cs, beside the card draw line):
        /// one line naming every combat patch attached N/N with the parts it needs,
        /// the RPC frame, and the R-section producers that census proves (the
        /// capability bits a record may state).</summary>
        internal static void BootLine()
        {
            try
            {
                var have = new HashSet<string>();
                foreach (var m in Harmony.GetAllPatchedMethods())
                {
                    if (m == null || m.DeclaringType == null) continue;
                    var info = Harmony.GetPatchInfo(m);
                    if (info == null) continue;
                    string target = m.DeclaringType.Name + "." + m.Name;
                    foreach (var p in info.Prefixes) Note(have, p, target, "p");
                    foreach (var p in info.Postfixes) Note(have, p, target, "o");
                    foreach (var p in info.Finalizers) Note(have, p, target, "f");
                }
                Producers = Census(have, HOOKS, FRAME_HOOKS);
                var ok = new List<string>(); var bad = new List<string>();
                for (int i = 0; i < HOOKS.Length; i++) (Attached(have, HOOKS[i]) ? ok : bad).Add(HOOKS[i][1] + "." + HOOKS[i][2]);
                int frame = 0;
                for (int i = 0; i < FRAME_HOOKS.Length; i++) if (Attached(have, FRAME_HOOKS[i])) frame++;
                string line = TAG + " combat evidence patches attached " + ok.Count.ToString(CultureInfo.InvariantCulture) + "/" + HOOKS.Length.ToString(CultureInfo.InvariantCulture)
                              + ": " + string.Join(", ", ok.ToArray()) + "; frame " + frame.ToString(CultureInfo.InvariantCulture) + "/" + FRAME_HOOKS.Length.ToString(CultureInfo.InvariantCulture)
                              + "; producers " + ProducerNames(Producers);
                if (bad.Count == 0 && frame == FRAME_HOOKS.Length) Plugin.Log.LogInfo(line);
                else Plugin.Log.LogError(line + "; NOT attached: " + string.Join(", ", bad.ToArray()));
            }
            catch (Exception ex)
            {
                Producers = 0;
                try { Plugin.Log.LogWarning(TAG + " boot line failed: " + ex.GetType().Name); } catch { }
            }
        }

        private static void Note(HashSet<string> have, HarmonyLib.Patch p, string target, string part)
        {
            if (p == null || p.PatchMethod == null || p.PatchMethod.DeclaringType == null) return;
            have.Add(p.PatchMethod.DeclaringType.Name + "|" + target + "|" + part);
        }

        private static bool Attached(HashSet<string> have, string[] h)
        {
            string target = h[1] + "." + h[2];
            if (h[3].Length == 0)
                return have.Contains(h[0] + "|" + target + "|p") || have.Contains(h[0] + "|" + target + "|o") || have.Contains(h[0] + "|" + target + "|f");
            for (int i = 0; i < h[3].Length; i++) if (!have.Contains(h[0] + "|" + target + "|" + h[3][i])) return false;
            return true;
        }

        /// <summary>The producers a census proves: a section's bit needs the frame
        /// and every hook its rows depend on (SECTION_HOOKS).</summary>
        internal static long Census(HashSet<string> have, string[][] hooks, string[][] frameHooks)
        {
            for (int i = 0; i < frameHooks.Length; i++) if (!Attached(have, frameHooks[i])) return 0;
            long caps = 0;
            for (int s = 0; s < SECTION_HOOKS.Length; s++)
            {
                bool all = true;
                for (int k = 0; k < SECTION_HOOKS[s].Length; k++) if (!Attached(have, hooks[SECTION_HOOKS[s][k]])) all = false;
                if (all) caps |= SECTION_BITS[s];
            }
            return caps;
        }

        private static string ProducerNames(long caps)
        {
            if (caps == 0) return "none";
            var n = new List<string>();
            if ((caps & W.CAPS_PUSH) != 0) n.Add("push");
            if ((caps & W.CAPS_VCHG) != 0) n.Add("vchg");
            if ((caps & W.CAPS_CHAIN) != 0) n.Add("chain");
            if ((caps & W.CAPS_DEATH) != 0) n.Add("death");
            return string.Join(" ", n.ToArray());
        }
    }

    // -- the patches (each a contained call: a throwing collector never reaches the game) ----------

    /// <summary>N1: the own gun's gate and the other seat's attack messages.</summary>
    [HarmonyPatch(typeof(Gun), "Attack")]
    internal static class CombatEvidence_AttackPatch
    {
        [HarmonyPrefix]
        private static void Prefix(Gun __instance, bool forceAttack, bool useAmmo, out long __state)
        {
            __state = 0;
            try { CombatEvidence.AttackEnter(__instance, forceAttack, useAmmo, out __state); } catch { }
        }

        [HarmonyPostfix]
        private static void Postfix(Gun __instance, bool __result, bool forceAttack, long __state)
        {
            try { CombatEvidence.AttackExit(__instance, __result, forceAttack, __state); } catch { }
        }
    }

    /// <summary>K2: the copy's ammunition state before Shoot, and the reload a Shoot started.</summary>
    [HarmonyPatch(typeof(ProjectileInit), "RPCA_Init")]
    internal static class CombatEvidence_InitAmmoPatch
    {
        [HarmonyPrefix]
        private static void Prefix(ProjectileInit __instance, int senderID, out int __state)
        {
            __state = 0;
            try { __state = CombatEvidence.InitEnter(__instance, senderID, 0); } catch { }
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(ProjectileInit __instance, int __state, Exception __exception)
        {
            try { CombatEvidence.InitExit(__instance, __state); } catch { }
            return __exception;
        }
    }

    [HarmonyPatch(typeof(ProjectileInit), "RPCA_Init_noAmmoUse")]
    internal static class CombatEvidence_InitNoAmmoPatch
    {
        [HarmonyPrefix]
        private static void Prefix(ProjectileInit __instance, int senderID)
        {
            try { CombatEvidence.InitEnter(__instance, senderID, 1); } catch { }
        }
    }

    [HarmonyPatch(typeof(ProjectileInit), "RPCA_Init_SeparateGun")]
    internal static class CombatEvidence_InitSeparatePatch
    {
        [HarmonyPrefix]
        private static void Prefix(ProjectileInit __instance, int senderID)
        {
            try { CombatEvidence.InitEnter(__instance, senderID, 2); } catch { }
        }
    }

    /// <summary>N2: a refill that ends a cycle (timer, card, revive).</summary>
    [HarmonyPatch(typeof(GunAmmo), "ReloadAmmo")]
    internal static class CombatEvidence_ReloadPatch
    {
        [HarmonyPrefix]
        private static void Prefix(GunAmmo __instance, bool playSound)
        {
            try { CombatEvidence.ReloadEnter(__instance, playSound); } catch { }
        }
    }

    /// <summary>K3: the copy before the owner's hit message replaces it; H1: the
    /// shooter's scope closes and an own projectile's velocity change is listed.</summary>
    [HarmonyPatch(typeof(ProjectileHit), "RPCA_DoHit")]
    internal static class CombatEvidence_HitPatch
    {
        [HarmonyPrefix]
        private static void Prefix(ProjectileHit __instance, Vector2 hitPoint, Vector2 vel, int viewID, bool wasBlocked, out long __state)
        {
            __state = 0;
            try { CombatEvidence.HitEnter(__instance, hitPoint, vel, viewID, wasBlocked, out __state); } catch { }
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(ProjectileHit __instance, long __state, Exception __exception)
        {
            try { CombatEvidence.HitExit(__instance, __state); } catch { }
            return __exception;
        }
    }

    /// <summary>N7: the copy of the other seat's projectile touches this seat's player.</summary>
    [HarmonyPatch(typeof(ProjectileHit), "Hit")]
    internal static class CombatEvidence_ContactPatch
    {
        [HarmonyPrefix]
        private static void Prefix(ProjectileHit __instance, HitInfo hit)
        {
            try { CombatEvidence.ContactEnter(__instance, hit); } catch { }
        }
    }

    /// <summary>K4: a block on either copy (the lane's frame classifies it; this reads the window).</summary>
    [HarmonyPatch(typeof(Block), "RPCA_DoBlock")]
    internal static class CombatEvidence_BlockPatch
    {
        [HarmonyFinalizer]
        private static Exception Finalizer(Block __instance, Exception __exception)
        {
            try { CombatEvidence.BlockDone(__instance); } catch { }
            return __exception;
        }
    }

    /// <summary>N6: the own press, accepted or refused.</summary>
    [HarmonyPatch(typeof(Block), "TryBlock")]
    internal static class CombatEvidence_TryBlockPatch
    {
        [HarmonyPrefix]
        private static void Prefix(Block __instance, out long __state)
        {
            __state = 0;
            try { CombatEvidence.TryBlockEnter(__instance, out __state); } catch { }
        }

        [HarmonyPostfix]
        private static void Postfix(Block __instance, long __state)
        {
            try { CombatEvidence.TryBlockExit(__instance, __state); } catch { }
        }
    }

    /// <summary>K5: damage dealt (cooldown refreshes per point).</summary>
    [HarmonyPatch(typeof(CharacterStatModifiers), "DealtDamage")]
    internal static class CombatEvidence_DealtPatch
    {
        [HarmonyPostfix]
        private static void Postfix(CharacterStatModifiers __instance)
        {
            try { CombatEvidence.Dealt(__instance); } catch { }
        }
    }

    /// <summary>N3: a target bounce's new velocity.</summary>
    [HarmonyPatch(typeof(BounceEffectRetarget), "SetNewVel")]
    internal static class CombatEvidence_TargetBouncePatch
    {
        [HarmonyPrefix]
        private static void Prefix(BounceEffectRetarget __instance, Vector2 newVel)
        {
            try { CombatEvidence.TargetBounce(__instance, newVel); } catch { }
        }
    }

    /// <summary>N4: a screen-edge bounce; E1: the owner's reflected velocity.</summary>
    [HarmonyPatch(typeof(ScreenEdgeBounce), "DoHit")]
    internal static class CombatEvidence_EdgeBouncePatch
    {
        [HarmonyPrefix]
        private static void Prefix(ScreenEdgeBounce __instance, out long __state)
        {
            __state = 0;
            try { CombatEvidence.EdgeBounce(__instance, out __state); } catch { }
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(ScreenEdgeBounce __instance, long __state, Exception __exception)
        {
            try { CombatEvidence.EdgeBounceExit(__instance, __state); } catch { }
            return __exception;
        }
    }

    /// <summary>N5: a received projectile sync package.</summary>
    [HarmonyPatch(typeof(SyncProjectile), "OnPhotonSerializeView")]
    internal static class CombatEvidence_SyncPatch
    {
        [HarmonyPostfix]
        private static void Postfix(SyncProjectile __instance, PhotonStream stream)
        {
            try { CombatEvidence.SyncRead(__instance, stream); } catch { }
        }
    }

    /// <summary>P1: a push applied to a player body (R1).</summary>
    [HarmonyPatch(typeof(HealthHandler), "RPCA_SendTakeForce")]
    internal static class CombatEvidence_ForcePatch
    {
        [HarmonyPrefix]
        private static void Prefix(HealthHandler __instance, Vector2 force, out long __state)
        {
            __state = 0;
            try { CombatEvidence.ForceEnter(__instance, force, out __state); } catch { }
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(HealthHandler __instance, long __state, Exception __exception)
        {
            try { CombatEvidence.ForceExit(__instance, __state); } catch { }
            return __exception;
        }
    }

    /// <summary>D1: a damage message on a player (R3 chain, R5 cause).</summary>
    [HarmonyPatch(typeof(HealthHandler), "RPCA_SendTakeDamage")]
    internal static class CombatEvidence_DamagePatch
    {
        [HarmonyPrefix]
        private static void Prefix(HealthHandler __instance, Vector2 damage, HealthHandler.DamageSource damageSource, out long __state)
        {
            __state = 0;
            try { CombatEvidence.DamageEnter(__instance, damage, damageSource == HealthHandler.DamageSource.OutOfBounds, out __state); } catch { }
        }

        [HarmonyFinalizer]
        private static Exception Finalizer(HealthHandler __instance, long __state, Exception __exception)
        {
            try { CombatEvidence.DamageExit(__instance, __state); } catch { }
            return __exception;
        }
    }

    /// <summary>X1: a death (R5).</summary>
    [HarmonyPatch(typeof(HealthHandler), "RPCA_Die")]
    internal static class CombatEvidence_DiePatch
    {
        [HarmonyPrefix]
        private static void Prefix(HealthHandler __instance)
        {
            try { CombatEvidence.Die(__instance); } catch { }
        }
    }

    /// <summary>X1: a death with a revive left (R5).</summary>
    [HarmonyPatch(typeof(HealthHandler), "RPCA_Die_Phoenix")]
    internal static class CombatEvidence_DiePhoenixPatch
    {
        [HarmonyPrefix]
        private static void Prefix(HealthHandler __instance)
        {
            try { CombatEvidence.Die(__instance); } catch { }
        }
    }

    /// <summary>S1: the owner's target choice for a target bounce (R2).</summary>
    [HarmonyPatch(typeof(BounceEffectRetarget), "FindTarget")]
    internal static class CombatEvidence_FindTargetPatch
    {
        [HarmonyPostfix]
        private static void Postfix(BounceEffectRetarget __instance, HitInfo hit, Player __result)
        {
            try { CombatEvidence.FindTarget(__instance, hit, __result); } catch { }
        }
    }
}
