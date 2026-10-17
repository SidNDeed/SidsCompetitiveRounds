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
    /// read through TeamHoldRules.RecordEntry0, which yields no record in
    /// this lane (KX5 binds it): no record, no card, everywhere.
    /// </summary>
    internal static class TeamHoldPick
    {
        private static string _phaseKey;
        private static readonly HashSet<string> _granted = new HashSet<string>(StringComparer.Ordinal);
        private static string _donePickingFor;

        private static bool Flagged() { return TeamHoldRules.Flagged(TeamHoldWriter.CurrentRoom()); }

        private static string Th() { return TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TH); }

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
                if (changed == null || !changed.ContainsKey(TeamHoldRules.KEY_TAP) || !Flagged()) return;
                string g, card; int slot, k;
                if (!TeamHoldRules.TryParseTap(changed[TeamHoldRules.KEY_TAP] as string, out g, out slot, out k, out card)) return;
                string cur;
                TeamHoldRules.GidStarted(TeamHoldWriter.RoomProp(TeamHoldRules.KEY_TGID), out cur);
                var o = TeamHoldRules.ApplyGrant(g, cur, slot, k, card);
                if (o == TeamHoldRules.GrantOutcome.Applied)
                    Plugin.Log.LogInfo(TeamHold.TAG + " auto grant slot=" + slot.ToString(CultureInfo.InvariantCulture) + " card=" + card);
                else if (o == TeamHoldRules.GrantOutcome.Superseded)
                    Plugin.Log.LogInfo(TeamHold.TAG + " grant superseded slot=" + slot.ToString(CultureInfo.InvariantCulture) + " k=" + k.ToString(CultureInfo.InvariantCulture));
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
                if (TeamHoldRules.RecordLate(start, Time.unscaledTime, have))
                {
                    Plugin.Log.LogInfo(TeamHold.TAG + " record late slot=" + slot.ToString(CultureInfo.InvariantCulture));
                    break;
                }
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
            if (match.HasValue)
                Plugin.Log.LogInfo(TeamHold.TAG + " audit slot=" + slot.ToString(CultureInfo.InvariantCulture) + " match=" + (match.Value ? "1" : "0"));
        }

        internal static void OnRoomLeft()
        {
            _phaseKey = null;
            _granted.Clear();
            _donePickingFor = null;
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
