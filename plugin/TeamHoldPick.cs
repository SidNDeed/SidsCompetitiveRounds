using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;
using Hashtable = ExitGames.Client.Photon.Hashtable;

namespace CompetitiveRounds
{
    /// <summary>
    /// Stage 2 S4 client: the absent seat's deal, the grant writer and
    /// applier, the record-late fallback and the audit hook. The record is
    /// read through TeamHoldRules.RecordEntry0, bound by KX5 to the cr_toff
    /// record of the phase (the FFA P2 record's codec and ledger): no
    /// record, no card, everywhere.
    /// </summary>
    internal static class TeamHoldPick
    {
        private static string _phaseKey;
        private static readonly HashSet<string> _granted = new HashSet<string>(StringComparer.Ordinal);
        private static string _donePickingFor;

        private static bool Flagged() { return TeamHoldRules.Flagged(TeamHoldWriter.CurrentRoom()); }

        private static string Th() { return TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TH); }

        // ── KX5: the record (S4 steps 2, 3 and 6) ─────────────────────────

        private static string _offBuiltFor, _spendG;
        private static readonly FfaReadmitRules.SpendState _spend = new FfaReadmitRules.SpendState();
        private static List<string> _preLedger = new List<string>();
        /// <summary>The deal index each listed slot was at when the phase's
        /// record was built or adopted: its first deal of the phase is the
        /// record's, a later one (the 1v2 solo's extra deal) has no entry.</summary>
        private static readonly Dictionary<int, int> _baseK = new Dictionary<int, int>();

        static TeamHoldPick()
        {
            TeamHoldRules.RecordEntry0 = RecordEntry0Now;
            Audit = AuditNow;
        }

        private static string Off() { return TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TOFF); }

        private static int PhaseNow()
        {
            var gm = GM_ArmsRace.instance;
            return gm != null ? TeamHoldRules.PhaseOf(gm.p1Rounds, gm.p2Rounds) : -1;
        }

        private static int DealsOf(int slot)
        {
            SeatDeckLog.Seat seat;
            return SeatDeckLog.TryGetSeat(slot, out seat) ? seat.Deals : 0;
        }

        private static IList<string> DeckOf(int slot)
        {
            SeatDeckLog.Seat seat;
            return SeatDeckLog.TryGetSeat(slot, out seat) ? (IList<string>)seat.Names : new List<string>();
        }

        private static bool FirstDealOfPhase(int slot, int k)
        {
            int b;
            return _baseK.TryGetValue(slot, out b) && b == k;
        }

        private static string RecordEntry0Now(string g, int slot, int k)
        {
            if (!FirstDealOfPhase(slot, k)) return null;
            return TeamHoldRules.Entry0Of(Off(), g, PhaseNow(), slot);
        }

        /// <summary>The owner screen (S4 step 3): the record list of the
        /// local picker's first deal of the phase, or null (today's deal).</summary>
        internal static List<string> ScreenFor(int slot, out bool ruleS)
        {
            ruleS = false;
            if (!Flagged()) return null;
            string g;
            if (!TeamHoldRules.GidStarted(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TGID), out g)) return null;
            if (!FirstDealOfPhase(slot, DealsOf(slot))) return null;
            var r = TeamHoldRules.OffFor(Off(), g, PhaseNow());
            if (r == null) return null;
            ruleS = r.Rule == 's';
            return r.ListOf(slot);
        }

        private static void NoteBase(FfaReadmitRules.FfaOfferRecord rec)
        {
            _baseK.Clear();
            foreach (var kv in rec.Entries) _baseK[kv.Key] = DealsOf(kv.Key);
        }

        private static void ResetSpendFor(string g)
        {
            if (_spendG == g) return;
            _spendG = g;
            _spend.Reset();
        }

        /// <summary>The master, at the phase's first DoPick (S4 step 2): the
        /// record over the phase's picker set, built once per G and phase (or
        /// adopted when one is already readable), spent into the one ledger
        /// and published as cr_toff. Rule s when the shared engine runs this
        /// game, rule p (its own roll over the deal's cards) when not.</summary>
        internal static void MasterRecord(int pickerId)
        {
            if (!PhotonNetwork.IsMasterClient || !Flagged()) return;
            var gm = GM_ArmsRace.instance;
            string g;
            if (gm == null || !TeamHoldRules.GidStarted(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TGID), out g)) return;
            int phase = PhaseNow();
            string key = g + ":" + phase.ToString(CultureInfo.InvariantCulture);
            if (_offBuiltFor == key) return;
            _offBuiltFor = key;
            ResetSpendFor(g);
            var pin = TeamHoldRules.PinFor(TeamHoldWriter.CurrentRoom());
            string mode = pin != null ? pin.Mode : null;
            bool gameStart = gm.p1Rounds == 0 && gm.p2Rounds == 0 && gm.p1Points == 0 && gm.p2Points == 0;
            bool extra = TeamHoldWriter.RoomProp("cr_ovt_xp") == "True";
            var present = new List<int>();
            if (PlayerManager.instance != null && PlayerManager.instance.players != null)
                foreach (var p in PlayerManager.instance.players) if (p != null) present.Add(p.PlayerID);
            var held = new List<int>();
            TeamHoldRules.HoldKey hk;
            if (TeamHoldRules.TryParseHold(Th(), out hk) && TeamHoldRules.IsLive(hk.State)) held.Add(hk.Slot);
            var manifest = new List<int>();
            foreach (var e in TeamHoldRules.PickerSet(mode, gameStart, TeamHoldRules.SlotToTeam(mode, pickerId), present, held, extra))
                manifest.Add(e.Key);
            var cc = CardChoice.instance;
            bool same = RoomRules.SameCards && FfaCardSequence.ActiveThisGame;
            var rec = TeamHoldRules.MasterOff(Off(), g, phase, () =>
            {
                var pool = same ? FfaCardSequence.OfferPoolNow() : RollPool(cc);
                Func<string> roll = null;
                if (cc != null) roll = () => { var o = cc.GetRandomCard(); return o != null ? o.name : null; };
                return TeamHoldRules.BuildOff(g, phase, manifest, same, s => DealsOf(s) + 1, DeckOf, pool,
                                              same ? FfaCardSequence.SeqStateNow() : null, VanillaCardSequence.DealSize, roll, _spend);
            });
            string v = TeamHoldRules.EncodeOff(rec);
            if (v == null) { Plugin.Log.LogInfo(TeamHold.TAG + " no record for phase " + key); return; }
            TeamHoldRules.AdoptOff(rec, _spend, null);
            NoteBase(rec);
            if (Off() != v) TeamHoldWriter.CasRoomProps(new Hashtable { { TeamHoldRules.KEY_TOFF, v } }, null, null);
            Plugin.Log.LogInfo(TeamHold.TAG + " record phase " + key + " rule " + rec.Rule + " slots " + rec.Entries.Count.ToString(CultureInfo.InvariantCulture));
        }

        /// <summary>Rule p's pool: the deal's own cards, one weight each.</summary>
        private static FfaReadmitRules.OfferPool RollPool(CardChoice cc)
        {
            if (cc == null || cc.cards == null) return null;
            var pool = new FfaReadmitRules.OfferPool();
            foreach (var c in cc.cards) if (c != null && c.gameObject != null) pool.Add(FfaCardSequence.FactsOf(c, 1));
            return pool;
        }

        /// <summary>Every client as cr_toff arrives: the ledger becomes the
        /// record's (the draw index is not adopted, notes row), the deal base
        /// is noted, and a non-master audits each listed slot.</summary>
        private static void OnRecord(string v)
        {
            string g;
            if (!TeamHoldRules.GidStarted(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TGID), out g)) return;
            var rec = TeamHoldRules.OffFor(v, g, PhaseNow());
            if (rec == null) return;
            ResetSpendFor(g);
            if (PhotonNetwork.IsMasterClient) return;   // the master adopted at build
            _preLedger = new List<string>(_spend.Ledger);
            TeamHoldRules.AdoptOff(rec, _spend, null);
            NoteBase(rec);
            foreach (var kv in rec.Entries) RunAudit(g, kv.Key);
        }

        /// <summary>The audit's recompute (S4 step 6): rule s rebuilt from
        /// this client's own engine state and the ledger before the record,
        /// compared name for name; null under rule p or with no engine.</summary>
        private static bool? AuditNow(string g, int slot)
        {
            var pub = TeamHoldRules.OffFor(Off(), g, PhaseNow());
            if (pub == null || pub.Rule != 's' || !FfaCardSequence.ActiveThisGame) return null;
            var spend = new FfaReadmitRules.SpendState();
            spend.Ledger.AddRange(_preLedger);
            var ks = new Dictionary<int, int>();
            foreach (var kv in pub.Entries) ks[kv.Key] = kv.Value.K;
            var mine = FfaReadmitRules.BuildRuleS(pub.Epoch, pub.Game, 0, new List<int>(ks.Keys), s => ks[s], DeckOf,
                                                  FfaCardSequence.OfferPoolNow(), FfaCardSequence.SeqStateNow(), spend);
            foreach (var a in FfaReadmitRules.Audit(pub, mine)) if (a.Key == slot) return a.Value;
            return null;
        }

        /// <summary>The DoPick prefix's test (S4 step 4): a deal of a slot the
        /// room's hold names in a waiting state is skipped on every client.</summary>
        internal static bool SkipDeal(int pickerId)
        {
            if (!Flagged()) return false;
            bool body = false;
            try { body = PlayerManager.instance != null && PlayerManager.instance.GetPlayerWithID(pickerId) != null; } catch { }
            return TeamHoldRules.SkipDeal(pickerId, Th(), body);
        }

        /// <summary>The master's grants for a skipped deal (S4 step 5): one per
        /// deal the slot makes in this phase, card = entry 0 of its record
        /// list. No record: nothing is written.</summary>
        internal static void OnSkipped(int slot)
        {
            Plugin.Log.LogInfo(TeamHold.TAG + " deal skipped slot=" + slot.ToString(CultureInfo.InvariantCulture));
            if (!PhotonNetwork.IsMasterClient) return;
            var gm = GM_ArmsRace.instance;
            string g;
            if (gm == null || !TeamHoldRules.GidStarted(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TGID), out g)) return;
            var pin = TeamHoldRules.PinFor(TeamHoldWriter.CurrentRoom());
            string mode = pin != null ? pin.Mode : null;
            bool gameStart = gm.p1Rounds == 0 && gm.p2Rounds == 0 && gm.p1Points == 0 && gm.p2Points == 0;
            // cr_ovt_xp is a bool room property; RoomProp reads its string form.
            bool extra = TeamHoldWriter.RoomProp("cr_ovt_xp") == "True";
            int deals = 1;
            foreach (var e in TeamHoldRules.PickerSet(mode, gameStart, TeamHoldRules.SlotToTeam(mode, slot), null, new[] { slot }, extra))
                if (e.Key == slot) deals = e.Value;
            string phase = g + ":" + gm.p1Rounds + ":" + gm.p2Rounds + ":" + gm.p1Points + ":" + gm.p2Points;
            if (phase != _phaseKey) { _phaseKey = phase; _granted.Clear(); }
            SeatDeckLog.Seat seat;
            int k0 = SeatDeckLog.TryGetSeat(slot, out seat) ? seat.Deals : 0;
            for (int i = 0; i < deals; i++)
            {
                int k = k0 + i;
                string key = slot.ToString(CultureInfo.InvariantCulture) + ":" + k.ToString(CultureInfo.InvariantCulture);
                if (!_granted.Add(key)) continue;
                string card = TeamHoldRules.Entry0(g, slot, k);
                if (string.IsNullOrEmpty(card)) continue;   // no record, no card
                TeamHoldWriter.CasRoomProps(new Hashtable { { TeamHoldRules.KEY_TAP, TeamHoldRules.TapFormat(g, slot, k, card) } }, null, null);
            }
        }

        /// <summary>Every client, from the room-properties callback: a grant
        /// goes through the one writer (S0); a real pick for that deal
        /// received first is kept.</summary>
        internal static void OnRoomProps(Hashtable changed)
        {
            try
            {
                if (changed == null || !Flagged()) return;
                if (changed.ContainsKey(TeamHoldRules.KEY_TOFF))
                    try { OnRecord(changed[TeamHoldRules.KEY_TOFF] as string); } catch { }
                if (!changed.ContainsKey(TeamHoldRules.KEY_TAP)) return;
                string g, card; int slot, k;
                if (!TeamHoldRules.TryParseTap(changed[TeamHoldRules.KEY_TAP] as string, out g, out slot, out k, out card)) return;
                string cur;
                TeamHoldRules.GidStarted(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TGID), out cur);
                TeamHoldRules.ApplyGrant(g, cur, slot, k, card);
            }
            catch { }
        }

        /// <summary>Per frame: a drop during the own deal of the held slot.
        /// Every client ends the pick locally (vanilla RPCA_DonePicking, no
        /// RPC) once it holds the drop.</summary>
        internal static void Tick()
        {
            try
            {
                var cc = CardChoice.instance;
                if (cc == null || !cc.IsPicking) { _donePickingFor = null; return; }
                if (TeamHold.Cut == null || !Flagged()) return;
                if (!TeamHoldRules.DonePickingLocally(cc.IsPicking, cc.pickrID, Th())) return;
                string key = TeamHold.Cut.G + ":" + cc.pickrID.ToString(CultureInfo.InvariantCulture);
                if (_donePickingFor == key) return;
                _donePickingFor = key;
                Plugin.Log.LogInfo(TeamHold.TAG + " pick ended locally for absent slot=" + cc.pickrID.ToString(CultureInfo.InvariantCulture));
                int slot = cc.pickrID;
                cc.RPCA_DonePicking();
                OnSkipped(slot);
            }
            catch { }
        }

        /// <summary>A present owner's deal waits for the record up to 4 s,
        /// then falls back to today with [HOLD] record late. Only when a
        /// record source is bound (KX5): unbound, the deal is today's at once.</summary>
        internal static IEnumerator WaitRecord(IEnumerator inner, int slot)
        {
            double start = Time.unscaledTime;
            string g;
            TeamHoldRules.GidStarted(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TGID), out g);
            SeatDeckLog.Seat seat;
            int k = SeatDeckLog.TryGetSeat(slot, out seat) ? seat.Deals : 0;
            while (true)
            {
                bool have = TeamHoldRules.Entry0(g, slot, k) != null;
                if (have) break;
                if (TeamHoldRules.RecordLateFor(slot, start, Time.unscaledTime, have)) break;
                yield return null;
            }
            yield return inner;
        }

        /// <summary>The audit hook (S4 step 6): every non-master recomputes
        /// the rule-s record and logs [HOLD] audit. The recompute is the
        /// record's own (KX5); this hook never changes what is applied.</summary>
        internal static Func<string, int, bool?> Audit;

        internal static void RunAudit(string g, int slot)
        {
            var f = Audit;
            if (f == null || PhotonNetwork.IsMasterClient) return;
            bool? match = null;
            try { match = f(g, slot); } catch { }
            if (match.HasValue) TeamHoldRules.AuditLine(slot, match.Value);
        }

        internal static void OnRoomLeft()
        {
            _phaseKey = null;
            _granted.Clear();
            _donePickingFor = null;
            _offBuiltFor = null;
            _spendG = null;
            _spend.Reset();
            _preLedger = new List<string>();
            _baseK.Clear();
        }

        internal static IEnumerator Empty() { yield break; }
    }

    /// <summary>S4 step 4: the held slot's deal is skipped on every client.
    /// Low priority; a DoPick another prefix already replaced is left alone.
    /// The postfix makes a present owner's deal wait for the record (step 3).</summary>
    [HarmonyPatch(typeof(CardChoice), "DoPick")]
    internal static class TeamHold_DoPickPatch
    {
        [HarmonyPrefix]
        [HarmonyPriority(Priority.Low)]
        private static bool Prefix(int picketIDToSet, ref IEnumerator __result, bool __runOriginal)
        {
            if (!__runOriginal) return false;
            try { TeamHoldPick.MasterRecord(picketIDToSet); }
            catch (Exception ex) { Plugin.Log.LogWarning(TeamHold.TAG + " record: " + ex.Message); }
            try
            {
                if (!TeamHoldPick.SkipDeal(picketIDToSet)) return true;
                __result = TeamHoldPick.Empty();
                TeamHoldPick.OnSkipped(picketIDToSet);
                return false;
            }
            catch { return true; }
        }

        [HarmonyPostfix]
        private static void Postfix(int picketIDToSet, ref IEnumerator __result, bool __runOriginal)
        {
            try
            {
                if (!__runOriginal || __result == null || TeamHoldRules.RecordEntry0 == null) return;
                if (!TeamHoldRules.Flagged(TeamHoldWriter.CurrentRoom())) return;
                var p = PlayerManager.instance != null ? PlayerManager.instance.GetPlayerWithID(picketIDToSet) : null;
                if (p == null || p.data == null || p.data.view == null || !p.data.view.IsMine) return;
                __result = TeamHoldPick.WaitRecord(__result, picketIDToSet);
            }
            catch { }
        }
    }
}
