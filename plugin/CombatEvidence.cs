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

        // -- cost rows (design 11.2 order) -------------------------------------------------------
        private const int COST_CAP = W.COLLECTORS;
        internal const int K1 = 0, K2 = 1, K3 = 2, K4 = 3, K5 = 4, N1 = 5, N2 = 6, N3 = 7, N4 = 8, N5 = 9, N6 = 10, N7 = 11, T = 12;
        private static readonly long[] _calls = new long[W.COLLECTORS], _ticks = new long[W.COLLECTORS],
                                       _maxTicks = new long[W.COLLECTORS], _faults = new long[W.COLLECTORS];
        private static readonly bool[] _faultLogged = new bool[W.COLLECTORS];
        private static readonly string[] _faultNote = new string[W.COLLECTORS];

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
                for (int i = 0; i < W.COLLECTORS; i++) { _calls[i] = 0; _ticks[i] = 0; _maxTicks[i] = 0; _faults[i] = 0; _faultLogged[i] = false; }
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
        internal const int ANCHOR_CAP = 256, RING_CAP = 128, POS_CAP = 64, PING_CAP = 600, TOP_CAP = 32, HT_CAP = 16;

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
            internal bool InAttack, AttackFirstSeen; internal int AttackEmits;
            internal bool FirstPending; internal long Rep, Since, Fl;
            internal bool MsgPending; internal int MsgStamp;
            // per point intervals
            internal long Gmin = -1, CexpMin = -1, Vmax, Vexp, Refreshes;
            internal bool HasVolley; internal int LastVolley;
            internal readonly int[] Ring = new int[RING_CAP]; internal int RingHead, RingN;
            internal readonly int[] Win = new int[RING_CAP]; internal int WinHead, WinN;
            internal long[] Stat;
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
            internal readonly E.FrameHist Frames = new E.FrameHist();
            internal readonly long[] Ping = new long[PING_CAP]; internal int PingN; internal long NextPingMs;
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
            internal readonly Ring Res = new Ring(RING_CAP, 20);
            internal readonly Ring Pack = new Ring(RING_CAP * 2, 4);
            internal readonly GameObject[] MaskObj = new GameObject[RING_CAP];
            internal readonly SyncProjectile[] PackObj = new SyncProjectile[RING_CAP * 2];
            internal long Dropped;
            // B5 open windows
            internal int OwnWin = -1, OppWin = -1; internal int OwnWinStamp, OppWinStamp; internal int OwnWinFrames, OppWinFrames; internal long OwnWinSw;
            internal bool OwnPressPending, OwnOpened; internal int OwnPressStamp; internal long OwnPressGap, OwnPressCd;
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

        private static bool RpcTop(out int stamp, out int sender, out int viewId, out string method)
        {
            return SeatEvidence.RpcTop(out stamp, out sender, out viewId, out method);
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
            if (!_open) return;
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
                var s = g.Own;
                if (s.InAttack) { s.Rep = s.AttackEmits; s.AttackEmits++; }
                else s.Rep = Math.Min(999, Math.Max(1, ++s.AttackEmits));
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
                OwnBlockKeyed(g, (int)st);
            }
        }

        // -- N1: Gun.Attack prefix + postfix ----------------------------------------------------------

        internal static void AttackEnter(Gun gun, bool forceAttack, bool useAmmo, out long state)
        {
            state = 0;
            if (!_open) return;
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
                s.InAttack = true; s.AttackFirstSeen = false; s.AttackEmits = 0;
                long since = (long)Math.Round(Math.Min(gun.sinceAttack * 1000.0, E.SINCE_CAP_MS));
                s.Since = since < 0 ? -1 : since;
                s.Fl = (forceAttack ? W.FL_FORCED : 0) | (useAmmo ? W.FL_USE_AMMO : 0) | (gun.isReloading ? W.FL_RELOADING : 0);
                return 1;
            }
            // the other seat's gun on this seat: a received attack message runs Attack(0, forced) inside Shoot
            int stamp, sender, view; string method;
            if (RpcTop(out stamp, out sender, out view, out method) && method == "Shoot" && sender == _oppActor)
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
            if (!result) return;
            // the rep 0 emission's ammo init runs synchronously inside the accepted call
            if (!s.AttackFirstSeen) s.Acct.AddNoInit();
            ReadCexp(s);
            if (!forceAttack && _oppP != null && gun.shootPosition != null)
            {
                int o = g.Aim.PushRow();
                if (o < 0) { g.Dropped++; return; }
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
            if (!_open) return 0;
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
            if (!RpcTop(out stamp, out sender, out view, out method) || view != pv.ViewID || method != INIT_METHODS[kind]) return 0;
            var s = GunOfActor(sender);
            if (s == null || senderID != sender) return 0;
            bool own = s == g.Own;
            Bind(s, own);
            // volley stamps for the per-point intervals (ammo and no-ammo inits of the main gun)
            if (kind != 2 && (!s.HasVolley || stamp != s.LastVolley))
            {
                s.HasVolley = true; s.LastVolley = stamp;
                if (s.RingN < RING_CAP) { s.Ring[(s.RingHead + s.RingN) % RING_CAP] = stamp; s.RingN++; } else g.Dropped++;
                // aim (B1): the first projectile of each volley, read on the tick
                int o = g.Aim.PushRow();
                if (o >= 0)
                {
                    var tr = init.transform; var p = tr.position; var f = tr.forward;
                    g.Aim.V[o] = own ? 0 : 2; g.Aim.V[o + 1] = stamp; g.Aim.V[o + 2] = p.x; g.Aim.V[o + 3] = p.y; g.Aim.V[o + 4] = f.x; g.Aim.V[o + 5] = f.y; g.Aim.V[o + 6] = 0;
                }
                else g.Dropped++;
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
                g.AMask[slot] = 0; g.ACord[slot] = 0; g.AHasHit[slot] = false; g.AHomChecked[slot] = false; g.AHasPack[slot] = false;
                g.AHomN[slot] = 0; g.AHomMax[slot] = -1; g.AObj[slot] = obj;
            }
            else
            {
                g.P3self[0]++; slot = -1;
                int k = pid & (ANCHOR_CAP - 1);
                g.OwnPid[k] = pid; g.OwnSInit[k] = stamp; g.OwnCord[k] = 0;
            }
            int i = g.Mask.PushSlot();
            if (i < 0) { g.Dropped++; return; }
            g.Mask.V[i * 2] = slot; g.Mask.V[i * 2 + 1] = own ? 1 : 0; g.MaskObj[i] = obj;
        }

        // -- N2: GunAmmo.ReloadAmmo prefix --------------------------------------------------------------

        internal static void ReloadEnter(GunAmmo ammo, bool playSound)
        {
            if (!_open) return;
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

        // -- K3: ProjectileHit.RPCA_DoHit prefix (before :204 overwrites the copy) ---------------------

        internal static void HitEnter(ProjectileHit ph, Vector2 point, Vector2 vel, int viewID, bool wasBlocked)
        {
            if (!_open) return;
            long t0 = Stamp();
            try { HitBody(ph, point, vel, viewID, wasBlocked); } catch (Exception ex) { Fault(K3, ex); }
            Cost(K3, t0);
        }

        private static void HitBody(ProjectileHit ph, Vector2 point, Vector2 vel, int viewID, bool wasBlocked)
        {
            var g = _g;
            if (g == null || ph == null) return;
            var pv = ph.GetComponent<PhotonView>();
            if (pv == null) return;
            int stamp, sender, view; string method;
            if (!RpcTop(out stamp, out sender, out view, out method) || method != "RPCA_DoHit" || view != pv.ViewID) return;
            int pid = pv.ViewID;
            if (sender == _oppActor && pv.OwnerActorNr == _oppActor)
            {
                int slot;
                if (!g.Slot.TryGetValue(pid, out slot) || !g.ALive[slot]) return;
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
                    // re-anchor: the copy now holds the owner's state at this stamp
                    g.AAge[slot] = C.WrapDiff(now, stamp);
                }
                else if (o < 0) g.Dropped++;
                g.ALastHit[slot] = stamp; g.AHasHit[slot] = true;
                // B5 victim side: the hit message on this seat's own player
                if (viewID != -1)
                {
                    var target = PhotonNetwork.GetPhotonView(viewID);
                    if (target != null && target.IsMine && _ownP != null && target == _ownP.data.view) FillContact(g, pid, stamp);
                }
                return;
            }
            // B5 shooter side: this seat's own decision on the other seat's player (path 0)
            if (sender == _localActor && pv.IsMine && viewID != -1)
            {
                var target = PhotonNetwork.GetPhotonView(viewID);
                if (target == null || target.OwnerActorNr != _oppActor || _oppP == null || target != _oppP.data.view) return;
                var blk = _oppP.data.block;
                int o = g.B5h.NextSlot();
                if (o < 0) return;
                var a = g.B5h.Raw;
                long since = blk == null ? -1 : (long)Math.Round(Math.Min(blk.sinceBlock * 1000.0, 600000.0));
                int k = pid & (ANCHOR_CAP - 1);
                bool known = g.OwnPid[k] == pid;
                a[o] = 0; a[o + 1] = stamp; a[o + 2] = pid; a[o + 3] = known ? g.OwnSInit[k] : 0; a[o + 4] = known ? Math.Min(255, g.OwnCord[k]++) : 0; a[o + 5] = 0;
                a[o + 6] = since < 0 ? -1 : since;
                a[o + 7] = g.HasOPred ? E.Clamp(C.WrapDiff(stamp, g.OPred), -600000, 600000) : 600000;
            }
        }

        private static void FillContact(Game g, int pid, int stamp)
        {
            var raw = g.B5c.Raw;
            long own = OwnSinceMs();
            for (int i = g.B5c.Count - 1, n = 0; i >= 0 && n < RECENT_CAP; i--, n++)
            {
                int o = i * g.B5c.Width;
                if (raw[o] == pid && raw[o + 6] == W.OWN_SINCE_NONE) { raw[o + 5] = stamp; raw[o + 6] = own; return; }
            }
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
            if (!_open) return;
            long t0 = Stamp();
            try { ContactBody(ph, hit); } catch (Exception ex) { Fault(N7, ex); }
            Cost(N7, t0);
        }

        private static void ContactBody(ProjectileHit ph, HitInfo hit)
        {
            var g = _g;
            if (g == null || ph == null || hit == null || hit.transform == null || _ownP == null) return;
            var pv = ph.GetComponent<PhotonView>();
            if (pv == null || pv.IsMine || pv.OwnerActorNr != _oppActor) return;
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
            if (!_open) return;
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
            if (!RpcTop(out stamp, out sender, out view, out method) || sender != _oppActor || view != data.view.ViewID
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

        internal static void TryBlockEnter(Block b, out long state)
        {
            state = 0;
            if (!_open) return;
            long t0 = Stamp();
            try
            {
                var data = b != null ? b.GetComponent<CharacterData>() : null;
                if (data != null && data.view != null && data.view.IsMine)
                    state = 1 | (!(b.counter < b.Cooldown()) ? 2 : 0) | ((long)Math.Round(Math.Min(b.counter, 600f) * 1000.0) << 2);
            }
            catch (Exception ex) { Fault(N6, ex); }
            Cost(N6, t0);
        }

        internal static void TryBlockExit(Block b, long state)
        {
            if (!_open || state == 0) return;
            long t0 = Stamp();
            try { TryBlockBody(b, (state & 2) != 0, state >> 2); } catch (Exception ex) { Fault(N6, ex); }
            Cost(N6, t0);
        }

        private static void TryBlockBody(Block b, bool blocked, long counterMs)
        {
            var g = _g;
            if (g == null || b == null) return;
            long cd = (long)Math.Round(b.Cooldown() * 1000.0);
            if (!blocked)
            {
                g.B5tot[2]++;
                int o = g.B5r.NextSlot();
                if (o >= 0) { var a = g.B5r.Raw; a[o] = ServerNow(); a[o + 1] = E.Clamp(counterMs, -1, 600000); a[o + 2] = E.Clamp(cd, 0, 600000); }
                return;
            }
            g.B5tot[0]++;
            if (counterMs < cd) g.B5tot[3]++;
            g.OwnPressPending = true; g.OwnPressStamp = ServerNow(); g.OwnPressGap = counterMs; g.OwnPressCd = cd;
            g.OwnWin = -1;
            int o2 = g.B5s.NextSlot();
            if (o2 < 0) return;
            var r = g.B5s.Raw;
            bool open = b.sinceBlock == 0f;
            g.OwnOpened = open;
            r[o2] = 0; r[o2 + 1] = 0; r[o2 + 2] = 0; r[o2 + 3] = 0; r[o2 + 4] = 600000; r[o2 + 5] = -1; r[o2 + 6] = -1; r[o2 + 7] = 0;
            r[o2 + 8] = E.Clamp((long)Math.Round(TimeHandler.timeScale * 1000.0), 0, 10000); r[o2 + 9] = E.Clamp(cd, 0, 600000);
            r[o2 + 10] = E.Clamp(counterMs, -1, 600000); r[o2 + 11] = 0;
            if (open) { g.OwnWin = o2; g.OwnWinStamp = g.OwnPressStamp; g.OwnWinFrames = 0; g.OwnWinSw = SwMs; }
        }

        /// <summary>The own block's stamp arrived with its outgoing RPC: the
        /// entry's key, and its press and opening relative to that stamp.</summary>
        private static void OwnBlockKeyed(Game g, int tb)
        {
            int last = g.B5s.Count - 1;
            if (last < 0) return;
            var r = g.B5s.Raw;
            int o = last * g.B5s.Width;
            if (tb != g.OwnOrdTb) { g.OwnOrdTb = tb; g.OwnOrd = 0; } else g.OwnOrd = Math.Min(255, g.OwnOrd + 1);
            r[o] = tb; r[o + 2] = g.OwnOrd;
            r[o + 3] = E.Clamp(C.WrapDiff(g.OwnPressStamp, tb), -600000, 600000);
            if (g.OwnOpened) r[o + 4] = E.Clamp(C.WrapDiff(g.OwnPressStamp, tb), -600000, 600000);
            g.HasOwnTb = true; g.LastOwnTb = tb;
        }

        // -- K5: CharacterStatModifiers.DealtDamage postfix -------------------------------------------

        internal static void Dealt(CharacterStatModifiers stats)
        {
            if (!_open) return;
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

        // -- N3: BounceEffectRetarget.SetNewVel prefix; N4: ScreenEdgeBounce.DoHit prefix ---------------

        internal static void TargetBounce(BounceEffectRetarget r, Vector2 newVel)
        {
            if (!_open) return;
            long t0 = Stamp();
            try { TargetBounceBody(r, newVel); } catch (Exception ex) { Fault(N3, ex); }
            Cost(N3, t0);
        }

        private static void TargetBounceBody(BounceEffectRetarget r, Vector2 newVel)
        {
            var g = _g;
            if (g == null || r == null || r.view == null) return;
            if (r.view.IsMine) { g.P3self[9]++; return; }
            if (r.view.OwnerActorNr != _oppActor) return;
            g.P3n[4]++;
            int pid = r.view.ViewID, slot, sInit = 0;
            long gap = -1;
            int stamp, sender, view; string method;
            bool keyed = RpcTop(out stamp, out sender, out view, out method) && sender == _oppActor;
            if (g.Slot.TryGetValue(pid, out slot) && g.ALive[slot])
            {
                sInit = g.ASInit[slot];
                if (keyed && g.AHasHit[slot]) gap = E.Clamp(C.WrapDiff(stamp, g.ALastHit[slot]), -1, 600000);
            }
            long has = r.move != null && (r.move.velocity.x != newVel.x || r.move.velocity.y != newVel.y) ? 1 : 0;
            long ang = 0;
            if (_ownP != null)
            {
                var pos = r.transform.position; var me = _ownP.transform.position;
                double mx = me.x - pos.x, my = me.y - pos.y;
                ang = E.RoundEven(Math.Abs(Math.Atan2(newVel.x * my - newVel.y * mx, newVel.x * mx + newVel.y * my)) * 1000.0);
            }
            int o = g.P3tb.NextSlot();
            if (o < 0) return;
            var a = g.P3tb.Raw;
            a[o] = pid; a[o + 1] = sInit; a[o + 2] = keyed ? stamp : 0; a[o + 3] = gap; a[o + 4] = has; a[o + 5] = E.Clamp(ang, 0, 3142);
        }

        internal static void EdgeBounce(ScreenEdgeBounce b)
        {
            if (!_open) return;
            long t0 = Stamp();
            try
            {
                var g = _g;
                var pv = b != null ? b.GetComponentInParent<PhotonView>() : null;
                if (g != null && pv != null && !pv.IsMine && pv.OwnerActorNr == _oppActor) g.P3n[3]++;
            }
            catch (Exception ex) { Fault(N4, ex); }
            Cost(N4, t0);
        }

        // -- N5: SyncProjectile.OnPhotonSerializeView postfix (reading branch) -------------------------

        internal static void SyncRead(SyncProjectile sp, PhotonStream stream)
        {
            if (!_open) return;
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
                            if (i < 0) g.Dropped++;
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
        /// window closes, and the deferred arithmetic of the hooks (bounded by the
        /// rings). Outside combat only: the captured records' builds.</summary>
        internal static void Tick()
        {
            if (_open)
            {
                long t0 = Stamp();
                try { TickBody(); } catch (Exception ex) { Fault(T, ex); }
                Cost(T, t0);
            }
            try
            {
                DrainNotes();
                if (SeatEvidence.CombatLive()) return;
                BuildCaptures(false);
            }
            catch { }
        }

        private static void TickBody()
        {
            var g = _g;
            if (g == null) return;
            ResolvePlayers();
            bool live = SeatEvidence.CombatLive();
            float scale = TimeHandler.timeScale, baseScale = TimeHandler.instance != null ? TimeHandler.instance.baseTimeScale : 1f;
            int now = ServerNow();
            if (live && !g.PointLive) PointStart(g, now, baseScale);
            else if (!live && g.PointLive) PointEnd(g, now);
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
                if (_ownP != null)
                {
                    var p = _ownP.transform.position;
                    int i = (g.PosHead + g.PosN) % POS_CAP;
                    if (g.PosN < POS_CAP) g.PosN++; else g.PosHead = (g.PosHead + 1) % POS_CAP;
                    g.PosT[i] = now; g.PosX[i] = p.x; g.PosY[i] = p.y;
                }
                CloseWindows(g, now);
            }
            long sw = SwMs;
            if (sw >= g.NextPingMs)
            {
                g.NextPingMs = sw + 1000;
                int ping = PhotonNetwork.GetPing();
                if (ping > 0 && g.PingN < PING_CAP) g.Ping[g.PingN++] = ping;
            }
            DrainMasks(g);
            DrainVolleys(g, g.Own, true); DrainVolleys(g, g.Opp, false);
            DrainAim(g);
            DrainResiduals(g);
            DrainPackages(g);
        }

        private static void PointStart(Game g, int now, float baseScale)
        {
            g.PointLive = true;
            int pt = 0;
            try { pt = PointEvidence.Point; } catch { }
            g.Pc = new E.PointClock { Pt = pt, PsRaw = now, SrvStart = now, Base = (long)Math.Round(baseScale * 1000.0) };
            g.LastBase = baseScale;
            Bind(g.Own, true); Bind(g.Opp, false);
            StatBlock(g, g.Own, g.GunS, pt);
            StatBlock(g, g.Opp, g.GunO, pt);
            PointReset(g.Own, pt);
            PointReset(g.Opp, pt);
        }

        private static void PointEnd(Game g, int now)
        {
            g.PointLive = false;
            g.Points++;
            if (g.Pc != null)
            {
                g.Pc.SrvEnd = now;
                int o = g.Tb.NextSlot();
                if (o >= 0) Array.Copy(g.Pc.PointRow(0), 0, g.Tb.Raw, o, g.Tb.Width);
                g.Pc = null;
            }
            DrainVolleys(g, g.Own, true); DrainVolleys(g, g.Opp, false);
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
        /// differs from the previous one (design 4.3).</summary>
        private static void StatBlock(Game g, GunState s, E.FixedRows rows, int pt)
        {
            var gun = s.G; var am = s.A;
            if (gun == null || am == null) return;
            var stats = gun.player != null && gun.player.data != null ? gun.player.data.stats : null;
            double mult = gun.attackSpeedMultiplier;
            double cexp = mult > 0 ? gun.usedCooldown / mult : 0;
            int attacks = gun.lockGunToDefault ? 1 : (gun.useCharge ? Mathf.Clamp(Mathf.RoundToInt(0.5f / gun.attackSpeed), 1, 10) : 1);
            double num2 = gun.spread / ((1f + gun.projectileSpeed * 0.5f) * 0.5f);
            double num = gun.multiplySpread * Math.Max(0.0, 1.0 + (gun.useCharge ? gun.chargeSpreadTo : 0f));
            long spr = E.RoundEven(Math.Atan(Math.Abs(num2 * num)) * 1000.0);
            var st = new long[]
            {
                pt, am.maxAmmo, Mil(am.reloadTime), Mil(am.reloadTimeAdd), Mil(am.reloadTimeMultiplier), Mil(am.ReloadTime()),
                Mil(gun.attackSpeed), Mil(mult), Mil(cexp), gun.numberOfProjectiles, gun.bursts, Mil(gun.timeBetweenBullets), Mil(am.ammoReg),
                stats != null && stats.automaticReload ? 1 : 0, stats != null && stats.refreshOnDamage ? 1 : 0, gun.useCharge ? 1 : 0,
                gun.lockGunToDefault ? 1 : 0, spr, gun.projectiles != null ? gun.projectiles.Length : 1,
            };
            var lo = W.LO[E.Ix("gun_s")]; var hi = W.HI[E.Ix("gun_s")];
            for (int i = 0; i < st.Length; i++) st[i] = E.Clamp(st[i], lo[i], hi[i]);
            s.Acct.Mag = st[1]; s.Acct.Rexp = st[5];
            s.Vexp = Math.Max(1, gun.bursts) * (long)attacks;
            bool same = s.Stat != null;
            for (int i = 1; same && i < st.Length; i++) if (s.Stat[i] != st[i]) same = false;
            if (same) return;
            s.Stat = st;
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

        private static int LHatMs(Game g)
        {
            if (g.PingN == 0) return -1;
            var a = new long[g.PingN];
            Array.Copy(g.Ping, a, g.PingN);
            Array.Sort(a);
            return (int)(a[(a.Length - 1) / 2] / 2);
        }

        private static int _lHatCache = -1; private static long _lHatAtMs;

        private static void DrainVolleys(Game g, GunState s, bool own)
        {
            long cexp = s.CexpMin;
            for (int n = 0; n < RING_CAP && s.RingN > 0; n++)
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
            for (int n = 0; n < RING_CAP; n++)
            {
                int i = g.Mask.PopSlot();
                if (i < 0) return;
                var obj = g.MaskObj[i]; g.MaskObj[i] = null;
                int slot = (int)g.Mask.V[i * 2]; bool own = g.Mask.V[i * 2 + 1] != 0;
                int mask = obj != null ? SteerMask(obj) : 0;
                if (own)
                {
                    for (int b = 0; b < 8; b++) if ((mask & (1 << b)) != 0) g.P3self[1 + b]++;
                    continue;
                }
                if (slot >= 0 && slot < ANCHOR_CAP && g.ALive[slot] && g.AObj[slot] == obj)
                {
                    g.AMask[slot] = mask;
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
            for (int n = 0; n < RING_CAP; n++)
            {
                int o = g.Aim.PopRow();
                if (o < 0) return;
                var v = g.Aim.V;
                int kind = (int)v[o]; int stamp = (int)v[o + 1];
                double px = v[o + 2], py = v[o + 3], fx = v[o + 4], fy = v[o + 5];
                if (kind == 0 || kind == 1)
                {
                    if (_oppP == null) continue;
                    var t = _oppP.transform.position;
                    bool sight = Sight(new Vector2((float)px, (float)py), _oppP);
                    (kind == 0 ? g.A1s : g.A1p).Add(SignedMrad(fx, fy, t.x - px, t.y - py), !sight);
                    continue;
                }
                if (g.PosN == 0 || _ownP == null) continue;
                // a1m: own position at (stamp - L^); a1n: the nearest over [stamp - 2L^ - W, stamp]
                int want = stamp - lhat, lo = stamp - 2 * lhat - E.A1N_W_MS;
                int best = -1; long bestD = long.MaxValue; long bestErr = 0; bool haveN = false;
                for (int k = 0; k < g.PosN; k++)
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
                bool vis = Sight(new Vector2((float)px, (float)py), _ownP);
                if (best >= 0) g.A1m.Add(SignedMrad(fx, fy, g.PosX[best] - px, g.PosY[best] - py), !vis);
                if (haveN) g.A1n.Add(bestErr, !vis);
            }
        }

        private static bool Sight(Vector2 from, Player p)
        {
            try { return PlayerManager.instance != null && PlayerManager.instance.CanSeePlayer(from, p).canSee; } catch { return true; }
        }

        internal static long SignedMrad(double fx, double fy, double tx, double ty)
        {
            if ((fx == 0 && fy == 0) || (tx == 0 && ty == 0)) return 0;
            return E.Clamp(E.RoundEven(Math.Atan2(tx * fy - ty * fx, tx * fx + ty * fy) * 1000.0), -3142, 3142);
        }

        private static void DrainResiduals(Game g)
        {
            for (int n = 0; n < RING_CAP; n++)
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
                int mask = slot >= 0 && slot < ANCHOR_CAP && g.APid[slot] == pid ? g.AMask[slot] : 0;
                // the side that is behind is flown forward by |dT| x k in fixed steps (design 5.2, M7)
                double span = Math.Abs(dTms) / 1000.0 * k;
                long[] res;
                if (dTms >= 0) res = E.Residual(E.IntegrateSpan(owner, span, E.PRED_STEP_S, prm), copy);
                else res = E.Residual(E.IntegrateSpan(copy, span, E.PRED_STEP_S, prm), owner);
                bool steer = mask != 0;
                (steer ? g.P3dp1 : g.P3dp0)[E.Bin(E.PERP_EDGES, res[0])]++;
                (steer ? g.P3an1 : g.P3an0)[E.Bin(E.ANG_EDGES, res[2])]++;
                long speed = E.RoundEven(E.Hypot(owner.VX, owner.VY) * W.CENTI);
                var entry = new long[] { pid, stamp, E.Clamp(res[0], 0, 9999999), E.Clamp(res[1], -9999999, 9999999), E.Clamp(res[2], 0, 3142),
                                         E.Clamp((long)Math.Round(Math.Abs(dTms)), 0, 600000), E.Clamp(speed, 0, 999999), mask };
                g.P3topSeen++;
                TopInsert(g.Top, ref g.TopN, TOP_CAP, 8, entry, 2);
            }
        }

        /// <summary>Keeps the `cap` rows with the largest field `key` (ties: the
        /// earlier row stays), in descending order.</summary>
        private static void TopInsert(long[] a, ref int n, int cap, int w, long[] e, int key)
        {
            int pos = n;
            for (int i = 0; i < n; i++) if (e[key] > a[i * w + key]) { pos = i; break; }
            if (pos >= cap) return;
            int last = Math.Min(n, cap - 1);
            for (int i = last; i > pos; i--) Array.Copy(a, (i - 1) * w, a, i * w, w);
            Array.Copy(e, 0, a, pos * w, w);
            if (n < cap) n++;
        }

        private static void DrainPackages(Game g)
        {
            for (int n = 0; n < RING_CAP * 2; n++)
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
            for (int i = 0; i < g.HtN; i++)
            {
                if (g.Ht[i * 4] != pid) continue;
                // remove and reinsert at its new rank
                for (int k = i; k < g.HtN - 1; k++) Array.Copy(g.Ht, (k + 1) * 4, g.Ht, k * 4, 4);
                g.HtN--;
                break;
            }
            g.P3htSeen++;
            TopInsert(g.Ht, ref g.HtN, HT_CAP, 4, new long[] { pid, sInit, E.Clamp(ratio, 0, 99999), E.Clamp(n, 0, 99999) }, 2);
        }

        // -- the game-over capture and the build ----------------------------------------------------

        private sealed class Capture
        {
            internal Game G; internal long[][] Cost;
            internal string Seat, Other, Attach, Text, Env; internal int T0; internal bool FromToken;
        }

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
                bool fromToken;
                int t0 = GameStateWatcher.SeatEvidenceT0(out fromToken);
                var cost = new long[COST_CAP][];
                for (int i = 0; i < COST_CAP; i++)
                    cost[i] = new long[] { _calls[i], _ticks[i], _maxTicks[i], _faults[i] };
                if (_captures.Count >= CAPTURE_CAP) { _captures.RemoveAt(0); _note = " a captured record was dropped before it was persisted: too many waiting"; }
                _captures.Add(new Capture { G = g, Cost = cost, Seat = seat, Other = other, Attach = attach, T0 = t0, FromToken = fromToken });
                _nextCaptureTryMs = 0;
            }
            catch { _note = " no record: the capture failed"; }
        }

        private static void DrainNotes()
        {
            for (int i = 0; i < W.COLLECTORS; i++)
            {
                string n = _faultNote[i];
                if (n == null) continue;
                _faultNote[i] = null;
                try { Plugin.Log.LogWarning(TAG + " collector " + i.ToString(CultureInfo.InvariantCulture) + " fault (counted, once per game): " + n); } catch { }
            }
            if (_note != null) { string n = _note; _note = null; try { Plugin.Log.LogWarning(TAG + n); } catch { } }
        }

        /// <summary>The record of a captured game (every layout key, full lists;
        /// the budgeter trims). Close of the last point happens here when the
        /// game ended inside one.</summary>
        private static E.Rec Build(Capture c)
        {
            var g = c.G;
            if (g.PointLive) PointEnd(g, ServerNow());
            var r = E.Empty();
            r["schema"] = (long)W.SCHEMA; r["consts"] = 1L; r["caps"] = 0L;
            r["t0"] = (long)c.T0; r["t0_src"] = c.FromToken ? "m" : "o";
            r["frame_p50_us"] = E.Clamp(g.Frames.Median(), 0, 1000000);
            var cost = new List<long[]>(W.COLLECTORS);
            for (int i = 0; i < W.COLLECTORS; i++)
                cost.Add(new long[] { E.Clamp(c.Cost[i][0], 0, 99999999), E.Clamp(Us(c.Cost[i][1]), 0, 2147483647), E.Clamp(Us(c.Cost[i][2]), 0, 99999999), E.Clamp(c.Cost[i][3], 0, 99999999) });
            r["cost"] = cost;
            r["l_hat"] = (long)LHatMs(g);
            var tb = g.Tb.Rows();
            r["tb_tot"] = E.TbTot(tb, g.BaseChanges, g.Points);
            r["tb"] = tb;
            r["a1s"] = g.A1s.HistClamped(); r["a1p"] = g.A1p.HistClamped(); r["a1m"] = g.A1m.HistClamped(); r["a1n"] = g.A1n.HistClamped();
            r["a1sum"] = new List<long[]> { g.A1s.Summary(), g.A1p.Summary(), g.A1m.Summary(), g.A1n.Summary() };
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
            om[E.OmitPos("gun_s")] = g.GunS.Omitted; om[E.OmitPos("gun_o")] = g.GunO.Omitted;
            om[E.OmitPos("ivl_s")] = g.IvlS.Omitted; om[E.OmitPos("ivl_o")] = g.IvlO.Omitted;
            om[E.OmitPos("tb")] = g.Tb.Omitted;
            om[E.OmitPos("cx_s")] = g.Own.Acct.CxOmitted; om[E.OmitPos("cx_o")] = g.Opp.Acct.CxOmitted;
            om[E.OmitPos("sh_s")] = g.Own.Acct.GroupsOmitted; om[E.OmitPos("sh_o")] = g.Opp.Acct.GroupsOmitted;
            om[E.OmitPos("p3top")] = g.P3topSeen - g.TopN; om[E.OmitPos("p3tb")] = g.P3tb.Omitted;
            om[E.OmitPos("p3ht")] = Math.Max(0, CountDistinctHoming(g) - g.HtN);
            om[E.OmitPos("b5_s")] = g.B5s.Omitted; om[E.OmitPos("b5_o")] = g.B5o.Omitted; om[E.OmitPos("b5_h")] = g.B5h.Omitted;
            om[E.OmitPos("b5_c")] = g.B5c.Omitted; om[E.OmitPos("b5_r")] = g.B5r.Omitted;
            for (int i = 0; i < om.Length; i++) om[i] = E.Clamp(om[i], 0, 99999999);
            return r;
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
                    if (c.Env == null)
                    {
                        string stable = SeatEvidence.StableOf(c.Attach);
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

    /// <summary>K3: the copy before the owner's hit message replaces it.</summary>
    [HarmonyPatch(typeof(ProjectileHit), "RPCA_DoHit")]
    internal static class CombatEvidence_HitPatch
    {
        [HarmonyPrefix]
        private static void Prefix(ProjectileHit __instance, Vector2 hitPoint, Vector2 vel, int viewID, bool wasBlocked)
        {
            try { CombatEvidence.HitEnter(__instance, hitPoint, vel, viewID, wasBlocked); } catch { }
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

    /// <summary>N4: a screen-edge bounce.</summary>
    [HarmonyPatch(typeof(ScreenEdgeBounce), "DoHit")]
    internal static class CombatEvidence_EdgeBouncePatch
    {
        [HarmonyPrefix]
        private static void Prefix(ScreenEdgeBounce __instance)
        {
            try { CombatEvidence.EdgeBounce(__instance); } catch { }
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
}
