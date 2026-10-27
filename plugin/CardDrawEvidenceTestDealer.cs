#if SCR_CARD_EVIDENCE_TEST_DEALER
using System;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>TEST ONLY (CD-L3, bar A8). Compiled only with the symbol
    /// SCR_CARD_EVIDENCE_TEST_DEALER, which no build configuration defines.
    /// Once per game, on the picker's own deal, the second slot repeats the
    /// first slot's card, so a casual test game carries a repeated slot for
    /// the record and the server half to show. Never in a ranked match. The
    /// marker string exists only to be probed: tools/tests/card-draw-hooks
    /// byte-scans builds for it and requires it absent from every shipped
    /// configuration.</summary>
    internal static class CardDrawEvidenceTestDealer
    {
        internal static string Marker = "SCR_CARD_EVIDENCE_TEST_DEALER_ON";
        private static int _doneGame = -1;

        internal static bool TryRepeat(CardChoice choice, Vector3 pos, Quaternion rot, out GameObject result)
        {
            result = null;
            if (choice == null || GameStateWatcher.MatchIsRanked) return false;
            int g = VanillaCardSequence.Game;
            if (_doneGame == g) return false;
            var spawned = choice.spawnedCards;
            if (spawned == null || spawned.Count != 1 || spawned[0] == null) return false;
            var first = spawned[0].GetComponent<CardInfo>();
            var card = first != null ? first.sourceCard : null;
            if (card == null) return false;
            var obj = choice.Spawn(card.gameObject, pos, rot);
            if (obj == null) return false;
            // vanilla's own two post-spawn lines, as VanillaCardSequence.TrySpawnShared
            var info = obj.GetComponent<CardInfo>();
            if (info != null) info.sourceCard = card;
            var dmg = obj.GetComponentInChildren<DamagableEvent>();
            var col = dmg != null ? dmg.GetComponent<Collider2D>() : null;
            if (col != null) col.enabled = false;
            _doneGame = g;
            Plugin.Log.LogWarning("[CARD-EV] test dealer repeated slot 0 (" + Marker + ")");
            result = obj;
            return true;
        }
    }

    /// <summary>Last of the SpawnUniqueCard prefixes: acts only when every
    /// earlier prefix left the original to run.</summary>
    [HarmonyPatch(typeof(CardChoice), "SpawnUniqueCard")]
    [HarmonyPriority(Priority.Last)]
    internal static class CardDrawEvidenceTestDealer_SpawnPatch
    {
        [HarmonyPrefix]
        private static bool Prefix(CardChoice __instance, Vector3 pos, Quaternion rot, ref GameObject __result, bool __runOriginal)
        {
            if (!__runOriginal) return false;
            try
            {
                GameObject obj;
                if (CardDrawEvidenceTestDealer.TryRepeat(__instance, pos, rot, out obj)) { __result = obj; return false; }
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[CARD-EV] test dealer: " + ex.GetType().Name); }
            return true;
        }
    }
}
#endif
