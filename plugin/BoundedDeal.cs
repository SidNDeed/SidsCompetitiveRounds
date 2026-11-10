using System;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Ask 16(a) R4, the game half: the bound on vanilla's card deal.
    /// BoundedDealRules holds the rule. The prefix below asks whether vanilla's
    /// draw can complete the slot; only when it cannot does it take the bounded
    /// path, and only on the seat that owns the picker (vanilla's own
    /// ReplaceCards gate, lesson 603), in a room whose every fighter advertises
    /// cr_deal1. Everywhere else vanilla's deal stands, its recursion included,
    /// as today. Other seats see an ordinary networked spawn: picks travel by
    /// PhotonView id, so no seat reads the hand differently.
    /// </summary>
    internal static class BoundedDeal
    {
        /// <summary>Capability prop. A key is never reused for changed
        /// semantics (the PoisonSync rule): a client advertising cr_deal1 says
        /// "when vanilla's deal cannot complete a slot, I deal it by
        /// BoundedDealRules". A change to that rule takes cr_deal2, and a mixed
        /// room then keeps vanilla's deal on every seat.</summary>
        internal const string CapabilityProp = "cr_deal1";
        internal const int CapabilityValue = 1;

        internal const string DiagKey = "bounded-deal";

        /// <summary>Set by the prefix's Harmony cleanup, and only when it
        /// attached. A client never advertises a rule it cannot run (#83).</summary>
        internal static bool PatchesLive;

        private static bool _staged;
        private static bool _stageFailedPermanently;
        private static string _lastLogKey = "";

        /// <summary>WeaponCooldownReset.StageCapability's state rules: refuse in
        /// a room, merge only from an idle client state, one-shot, retried from
        /// the persistent tick, and only after the compat verdict.</summary>
        internal static void StageCapability(string source)
        {
            try
            {
                if (_staged || _stageFailedPermanently) return;
                if (!PatchesLive)
                {
                    _stageFailedPermanently = true;
                    Plugin.Log.LogError("[DEAL] SpawnUniqueCard patch did NOT attach - "
                        + "the deal's bound is disabled for this session (vanilla everywhere)");
                    return;
                }
                if (!Plugin.compatCheckComplete) return;
                if (Plugin.modDisabled) { _stageFailedPermanently = true; return; }

                if (PhotonNetwork.InRoom)
                {
                    Plugin.Log.LogError("[DEAL] refusing to stage while in a room ("
                        + source + ") - an in-room write is the racy path this protocol forbids");
                    return;
                }

                var st = PhotonNetwork.NetworkClientState;
                if (st != Photon.Realtime.ClientState.Disconnected
                    && st != Photon.Realtime.ClientState.PeerCreated
                    && st != Photon.Realtime.ClientState.ConnectedToMasterServer
                    && st != Photon.Realtime.ClientState.JoinedLobby)
                    return;   // connecting or joining: a merge here can go undelivered

                var local = PhotonNetwork.LocalPlayer;
                if (local == null) return;
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable
                {
                    { CapabilityProp, CapabilityValue }
                });
                _staged = true;
                Plugin.Log.LogInfo("[DEAL] staged " + CapabilityProp + "=" + CapabilityValue
                    + " pre-join (" + source + ", state=" + st + ")");
            }
            catch (Exception ex)
            {
                _stageFailedPermanently = true;
                Plugin.Log.LogError("[DEAL] staging failed, the deal's bound is disabled for this session: "
                    + ex.Message);
            }
        }

        /// <summary>Withdraw on compat-disable, as WeaponCooldownReset does:
        /// peers must not count this seat capable when the patch will not run.</summary>
        internal static void RevokeCapability()
        {
            try
            {
                if (!_staged) return;
                _staged = false;
                _stageFailedPermanently = true;   // never re-stage this session
                var local = PhotonNetwork.LocalPlayer;
                if (local == null) return;
                local.SetCustomProperties(new ExitGames.Client.Photon.Hashtable
                {
                    { CapabilityProp, 0 }
                });
                Plugin.Log.LogWarning("[DEAL] revoked " + CapabilityProp + " - mod disabled, vanilla's deal everywhere");
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[DEAL] revoke failed: " + ex.Message); }
        }

        /// <summary>The whole-room fighter quorum, from replicated inputs only:
        /// the raw PhotonNetwork.PlayerList filtered by the replicated spectator
        /// role (WeaponCooldownReset.AllFightersCapable's basis, and
        /// PoisonSync.ScanRoster's), never RoomActors.ActiveFighters, whose
        /// frozen roster is local state. A missing, unarrived, non-integer or
        /// different value counts as incapable. Empty fails closed.</summary>
        private static bool AllFightersCapable(out int fighterCount, out int missingActor)
        {
            fighterCount = 0;
            missingActor = -1;
            var list = PhotonNetwork.PlayerList;
            if (list == null || list.Length == 0) return false;
            bool all = true;
            for (int i = 0; i < list.Length; i++)
            {
                var actor = list[i];
                if (actor == null) continue;
                if (RoomActors.IsSpectatorReplicated(actor)) continue;
                fighterCount++;
                object v = null;
                var props = actor.CustomProperties;
                if (props != null) props.TryGetValue(CapabilityProp, out v);
                if (!(v is int) || (int)v != CapabilityValue)
                {
                    all = false;
                    if (missingActor < 0) missingActor = actor.ActorNumber;
                }
            }
            if (fighterCount == 0) return false;
            return all;
        }

        /// <summary>Fail-closed on every arm. Evaluated only when vanilla's
        /// draw cannot complete a slot, so a normal deal never reads it.</summary>
        internal static bool ShouldApply()
        {
            try
            {
                if (Plugin.modDisabled || !PatchesLive) return false;

                bool offline = false;
                try { offline = PhotonNetwork.OfflineMode; } catch { }
                if (offline)
                {
                    NoteVerdict("apply", "offline", 1, -1);
                    return true;   // the whole room is this client, by construction
                }
                if (!PhotonNetwork.InRoom) return false;

                int fighters, missing;
                bool all = AllFightersCapable(out fighters, out missing);
                NoteVerdict(all ? "apply" : "vanilla", "online", fighters, missing);
                return all;
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("BoundedDeal", ex);
                return false;
            }
        }

        private static void NoteVerdict(string verdict, string where, int fighters, int missingActor)
        {
            try
            {
                string key = verdict + "|" + where + "|" + fighters + "|" + missingActor;
                if (key == _lastLogKey) return;
                _lastLogKey = key;
                Plugin.Log.LogInfo("[DEAL] " + verdict + " (" + where + ", fighters=" + fighters
                    + (missingActor >= 0 ? ", first actor without " + CapabilityProp + "=" + missingActor : "")
                    + ")");
            }
            catch { }
        }

        internal static void ResetForRoomChange()
        {
            _lastLogKey = "";
        }

        /// <summary>Vanilla GetRandomCard's weights; any other rarity is never
        /// drawn by weight.</summary>
        internal static float Weight(CardInfo card)
        {
            switch (card.rarity)
            {
                case CardInfo.Rarity.Common: return 10f;
                case CardInfo.Rarity.Uncommon: return 4f;
                case CardInfo.Rarity.Rare: return 1f;
                default: return 0f;
            }
        }

        /// <summary>The picker the four rejections read: vanilla's own
        /// resolution (SpawnUniqueCard's head; a team picker is the team's first
        /// player), looked up by id rather than indexed (#195). Null when
        /// pickrID is -1, so players[-1] is never read.</summary>
        private static Player RulesPicker(CardChoice choice)
        {
            var pm = PlayerManager.instance;
            if (pm == null || choice.pickrID < 0) return null;
            if (choice.pickerType == PickerType.Team)
            {
                var team = pm.GetPlayersInTeam(choice.pickrID);
                return team != null && team.Length > 0 ? team[0] : null;
            }
            return pm.GetPlayerWithID(choice.pickrID);
        }

        /// <summary>The slot's pool, as vanilla's four rejections see it: one
        /// candidate per entry of choice.cards, in its order, so a pool index is
        /// a card index. The hand is read from spawnedCards, skipping a
        /// destroyed entry without touching the list, so the stale-list wait's
        /// repair (VanillaFixes, #309) stands.</summary>
        internal static List<BoundedDealRules.Candidate> Describe(CardChoice choice, Player picker)
        {
            var cards = choice.cards;
            var pool = new List<BoundedDealRules.Candidate>(cards.Length);

            var inHand = new HashSet<CardInfo>();
            var spawned = choice.spawnedCards;
            if (spawned != null)
                for (int i = 0; i < spawned.Count; i++)
                {
                    var go = spawned[i];
                    if (go == null) continue;
                    var info = go.GetComponent<CardInfo>();
                    if (info != null && info.sourceCard != null) inHand.Add(info.sourceCard);
                }

            var holding = picker.data.GetComponent<Holding>();
            var holdable = holding != null ? holding.holdable : null;
            var heldGun = holdable != null ? holdable.GetComponent<Gun>() : null;
            bool heldGunLocks = heldGun != null && heldGun.lockGunToDefault;
            var held = picker.data.currentCards;

            for (int c = 0; c < cards.Length; c++)
            {
                var card = cards[c];
                if (card == null)
                {
                    pool.Add(new BoundedDealRules.Candidate(0f, false, false, false, false));
                    continue;
                }
                var cardGun = card.GetComponent<Gun>();
                bool gunLock = heldGunLocks && cardGun != null && cardGun.lockGunToDefault;
                bool blacklisted = false, heldRule = false;
                if (held != null)
                    for (int h = 0; h < held.Count; h++)
                    {
                        var have = held[h];
                        if (have == null) continue;
                        if (!have.allowMultiple && have.name == card.name) heldRule = true;
                        if (have.blacklistedCategories == null || card.categories == null) continue;
                        for (int k = 0; k < have.blacklistedCategories.Length && !blacklisted; k++)
                            for (int l = 0; l < card.categories.Length; l++)
                                if (card.categories[l] == have.blacklistedCategories[k]) { blacklisted = true; break; }
                    }
                pool.Add(new BoundedDealRules.Candidate(Weight(card), inHand.Contains(card), gunLock, blacklisted, heldRule));
            }
            return pool;
        }

        /// <summary>The prefix's body. True only when the bounded path dealt the
        /// slot; every other outcome leaves the slot to vanilla's draw.</summary>
        internal static bool TrySpawnBounded(CardChoice choice, Vector3 pos, Quaternion rot, out GameObject result)
        {
            result = null;
            if (choice == null || choice.cards == null || choice.cards.Length == 0) return false;
            // Vanilla checks nothing for a hand's first slot.
            int handCount = choice.spawnedCards != null ? choice.spawnedCards.Count : 0;
            if (handCount <= 0) return false;
            // The owning seat only: vanilla's ReplaceCards gate (Pick and IDoEndPick).
            if (choice.pickrID < 0) return false;
            var pm = PlayerManager.instance;
            var owner = pm != null ? pm.GetPlayerWithID(choice.pickrID) : null;
            if (owner == null || owner.data == null || owner.data.view == null || !owner.data.view.IsMine) return false;
            var picker = RulesPicker(choice);
            if (picker == null || picker.data == null) return false;

            var pool = Describe(choice, picker);
            var answer = BoundedDealRules.Decide(handCount, pool);
            if (answer == BoundedDealRules.Answer.Vanilla || answer == BoundedDealRules.Answer.NothingDrawable)
                return false;
            if (!ShouldApply()) return false;   // a mixed room keeps vanilla's deal, as today

            int index = BoundedDealRules.Pick(answer, pool, UnityEngine.Random.value);
            if (index < 0) return false;
            var source = choice.cards[index];
            var obj = choice.Spawn(source.gameObject, pos, rot);
            if (obj == null) return false;
            // Vanilla's own two post-spawn lines (SpawnUniqueCard's tail): the
            // source stamp its in-hand rule compares, and the pick collider. The
            // caller's slot bookkeeping (spawnedCards, PublicInt) is untouched.
            var info = obj.GetComponent<CardInfo>();
            if (info != null) info.sourceCard = source;
            var dmg = obj.GetComponentInChildren<DamagableEvent>();
            var col = dmg != null ? dmg.GetComponent<Collider2D>() : null;
            if (col != null) col.enabled = false;
            VanillaFixSupport.DiagLimited(DiagKey, "[DEAL] slot " + handCount.ToString(CultureInfo.InvariantCulture)
                + " dealt by the bounded path at level " + answer + " (held cards "
                + (picker.data.currentCards != null ? picker.data.currentCards.Count : 0).ToString(CultureInfo.InvariantCulture)
                + ")", 6);
            result = obj;
            return true;
        }

        /// <summary>Section 2's row for data.currentCards: no change (vanilla's
        /// pick exclusion reads it), but its length is logged at each game start.</summary>
        internal static void LogHeldCards()
        {
            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null) return;
            var sb = new System.Text.StringBuilder("[DEAL] game start: held cards");
            int n = 0;
            for (int i = 0; i < pm.players.Count; i++)
            {
                var p = pm.players[i];
                if (p == null || p.data == null || p.data.currentCards == null) continue;
                sb.Append(n++ == 0 ? " " : ", ").Append('p').Append(p.playerID.ToString(CultureInfo.InvariantCulture))
                  .Append('=').Append(p.data.currentCards.Count.ToString(CultureInfo.InvariantCulture));
            }
            if (n == 0) sb.Append(" none");
            Plugin.Log.LogInfo(sb.ToString());
        }
    }

    /// <summary>R4, the deal's bound. Low, so it runs after Same Cards'
    /// SpawnUniqueCard prefix (VanillaCardSequence.cs, Normal); it reads
    /// __runOriginal and does nothing when that prefix has dealt the slot.
    /// Its only false return is the bounded path's: on every other answer
    /// vanilla's draw runs unchanged.</summary>
    [HarmonyPatch(typeof(CardChoice), "SpawnUniqueCard")]
    [HarmonyPriority(Priority.Low)]
    internal static class CardChoiceSpawnUniqueCardBoundedDealPatch
    {
        [HarmonyPrefix]
        private static bool BeforeSpawnUniqueCard(CardChoice __instance, Vector3 pos, Quaternion rot,
                                                  ref GameObject __result, bool __runOriginal)
        {
            if (!__runOriginal) return true;   // an earlier prefix has dealt this slot
            try
            {
                GameObject dealt;
                if (BoundedDeal.TrySpawnBounded(__instance, pos, rot, out dealt))
                {
                    __result = dealt;
                    return false;
                }
            }
            catch (Exception ex) { VanillaFixSupport.LogError("BoundedDeal", ex); }
            return true;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) BoundedDeal.PatchesLive = true;
            return VanillaFixSupport.Cleanup("BoundedDeal", exception);
        }
    }

    /// <summary>The held-card log at each game start. A plain prefix: it
    /// changes nothing, and runs whatever its siblings return (#352).</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "DoStartGame")]
    internal static class GMArmsRaceDoStartGameBoundedDealLogPatch
    {
        [HarmonyPrefix]
        private static void BeforeDoStartGame()
        {
            try { BoundedDeal.LogHeldCards(); }
            catch (Exception ex) { VanillaFixSupport.LogError("BoundedDeal game start", ex); }
        }
    }
}
