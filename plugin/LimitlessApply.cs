using System;
using System.Collections.Generic;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Ask 16(a) lane 2: lane 1's four deferrals (v4 section 2). Each acts only
    /// under the fence's record, the one limitless gate. Every patch here
    /// returns first unless LimitlessFence.RecordOpen (a record live or
    /// terminating), so a normal game's numbers and display never change.
    ///
    /// - The clamp applier (an ApplyStats postfix). After every card apply,
    ///   each field of LimitlessBounds' table is held in its range or under its
    ///   cap, and bursts give way to the bullet bound. When a field moved, what
    ///   ApplyStats ran after MaxHealth runs again on the held values:
    ///   ConfigureMassAndSize, WasUpdated, and Revive's two copies (the health
    ///   and the remaining respawns).
    /// - The card bar (a CardBar.AddCard postfix) keeps the newest NewestCards
    ///   icons. The full list stays in Tab stats.
    /// - The broadcast card list: GameStateWatcher.BroadcastCardPick sends the
    ///   reported game's names plus the newest NewestCards
    ///   (LimitlessFenceRules.CappedCards).
    /// - The round pips need no code. The fence writes the target field alone
    ///   (LimitlessFence.SetRecordTarget), and nothing in the mod calls
    ///   SetNumberOfRounds. Vanilla calls it in GM_ArmsRace.Start and in
    ///   DoContinue, which only GameOverContinue reaches, and nothing calls
    ///   GameOverContinue: GameOver takes GameOverTransition (GM_ArmsRace:445).
    ///   Lane 1's RoundPipClamp answers a pip past the last.
    /// </summary>
    internal static class LimitlessApply
    {
        /// <summary>The newest cards a limitless game shows on the card bar and
        /// sends in the broadcast list. A default for Sid's review, like D1's
        /// N.</summary>
        internal const int NewestCards = 12;

        private static bool _unmatchedLogged;

        /// <summary>The clamp applier for one player, run after ApplyStats. It
        /// reads the components the way ApplyStats does and returns how many
        /// fields it moved.</summary>
        internal static int ClampPlayer(Player player)
        {
            if (player == null) return 0;
            Holding holding = player.GetComponent<Holding>();
            Gun gun = holding != null && holding.holdable != null ? holding.holdable.GetComponent<Gun>() : null;
            GunAmmo ammo = gun != null ? gun.GetComponentInChildren<GunAmmo>() : null;
            CharacterData data = player.GetComponent<CharacterData>();
            CharacterStatModifiers stats = player.GetComponent<CharacterStatModifiers>();
            Gravity gravity = player.GetComponent<Gravity>();
            Block block = player.GetComponent<Block>();
            if (gun == null || data == null || stats == null || gravity == null || block == null) return 0;
            float maxBefore = data.MaxHealth;
            int respawnsBefore = stats.respawns;
            int moved = 0, unmatched = 0;
            foreach (LimitlessBounds.Range r in LimitlessBounds.Ranges)
            {
                switch (r.Field)
                {
                    case "GunAmmo.reloadTimeMultiplier": if (ammo != null) ClampField(r, ref ammo.reloadTimeMultiplier, ref moved); break;
                    case "CharacterStatModifiers.sizeMultiplier": ClampField(r, ref stats.sizeMultiplier, ref moved); break;
                    case "CharacterData.maxHealth":
                        {
                            // the MaxHealth property, as ApplyStats writes it
                            float held = LimitlessBounds.Clamp(r, data.MaxHealth);
                            if (held != data.MaxHealth) { data.MaxHealth = held; moved++; }
                            break;
                        }
                    case "CharacterStatModifiers.movementSpeed": ClampField(r, ref stats.movementSpeed, ref moved); break;
                    case "CharacterStatModifiers.jump": ClampField(r, ref stats.jump, ref moved); break;
                    case "Gravity.gravityForce": ClampField(r, ref gravity.gravityForce, ref moved); break;
                    case "Block.cdMultiplier": ClampField(r, ref block.cdMultiplier, ref moved); break;
                    case "Gun.damage": ClampField(r, ref gun.damage, ref moved); break;
                    case "Gun.chargeDamageMultiplier": ClampField(r, ref gun.chargeDamageMultiplier, ref moved); break;
                    case "Gun.knockback": ClampField(r, ref gun.knockback, ref moved); break;
                    case "Gun.projectileSpeed": ClampField(r, ref gun.projectileSpeed, ref moved); break;
                    case "Gun.projectielSimulatonSpeed": ClampField(r, ref gun.projectielSimulatonSpeed, ref moved); break;
                    case "Gun.gravity": ClampField(r, ref gun.gravity, ref moved); break;
                    case "Gun.multiplySpread": ClampField(r, ref gun.multiplySpread, ref moved); break;
                    case "Gun.attackSpeed": ClampField(r, ref gun.attackSpeed, ref moved); break;
                    case "Gun.bodyRecoil": ClampField(r, ref gun.bodyRecoil, ref moved); break;
                    case "Gun.speedMOnBounce": ClampField(r, ref gun.speedMOnBounce, ref moved); break;
                    case "Gun.dmgMOnBounce": ClampField(r, ref gun.dmgMOnBounce, ref moved); break;
                    case "Gun.bulletDamageMultiplier": ClampField(r, ref gun.bulletDamageMultiplier, ref moved); break;
                    case "Gun.damageAfterDistanceMultiplier": ClampField(r, ref gun.damageAfterDistanceMultiplier, ref moved); break;
                    case "Gun.timeToReachFullMovementMultiplier": ClampField(r, ref gun.timeToReachFullMovementMultiplier, ref moved); break;
                    default: unmatched++; break;
                }
            }
            foreach (LimitlessBounds.Cap c in LimitlessBounds.Caps)
            {
                switch (c.Field)
                {
                    case "Gun.numberOfProjectiles": CapField(c, ref gun.numberOfProjectiles, ref moved); break;
                    case "Gun.bursts": CapField(c, ref gun.bursts, ref moved); break;
                    case "Gun.reflects": CapField(c, ref gun.reflects, ref moved); break;
                    case "Gun.smartBounce": CapField(c, ref gun.smartBounce, ref moved); break;
                    case "Gun.randomBounces": CapField(c, ref gun.randomBounces, ref moved); break;
                    case "Gun.bulletPortal": CapField(c, ref gun.bulletPortal, ref moved); break;
                    case "Block.additionalBlocks": CapField(c, ref block.additionalBlocks, ref moved); break;
                    case "CharacterStatModifiers.respawns": CapField(c, ref stats.respawns, ref moved); break;
                    default: unmatched++; break;
                }
            }
            int bursts = LimitlessBounds.BurstsWithin(gun.numberOfProjectiles, gun.bursts);
            if (bursts != gun.bursts) { gun.bursts = bursts; moved++; }
            if (unmatched > 0 && !_unmatchedLogged)
            {
                _unmatchedLogged = true;
                Plugin.Log.LogWarning("[LIMIT] clamp: " + unmatched + " table field(s) without an applier case");
            }
            if (moved == 0) return 0;
            stats.ConfigureMassAndSize();
            stats.WasUpdated();
            if (data.MaxHealth != maxBefore) data.health = data.MaxHealth;
            if (stats.respawns != respawnsBefore) stats.remainingRespawns = stats.respawns;
            Plugin.Log.LogInfo("[LIMIT] clamp: " + moved + " field(s) held, player " + player.PlayerID);
            return moved;
        }

        private static void ClampField(LimitlessBounds.Range r, ref float field, ref int moved)
        {
            float held = LimitlessBounds.Clamp(r, field);
            if (held != field) { field = held; moved++; }
        }

        private static void CapField(LimitlessBounds.Cap c, ref int field, ref int moved)
        {
            int held = LimitlessBounds.Clamp(c, field);
            if (held != field) { field = held; moved++; }
        }

        /// <summary>The card bar keeps the newest NewestCards icons. Vanilla's
        /// AddCard inserts each icon at m_cards[0], so the oldest is last.
        /// Returns how many it removed.</summary>
        internal static int TrimBar(CardBar bar)
        {
            List<CardBarButton> cards = bar != null ? bar.m_cards : null;
            if (cards == null || cards.Count <= NewestCards) return 0;
            if (bar.DoesHover) bar.StopHover();
            int removed = 0;
            while (cards.Count > NewestCards)
            {
                int oldest = cards.Count - 1;
                CardBarButton icon = cards[oldest];
                cards.RemoveAt(oldest);
                if (icon != null) UnityEngine.Object.Destroy(icon.gameObject);
                removed++;
            }
            return removed;
        }
    }

    /// <summary>The clamp applier's hook. Vanilla's ApplyStats runs once per
    /// player a card applies to (RPCA_Pick, OFFLINE_Pick); this postfix holds
    /// that player's fields after it.</summary>
    [HarmonyPatch(typeof(ApplyCardStats), "ApplyStats")]
    internal static class LimitlessApply_ApplyStats_Patch
    {
        private static void Postfix(ApplyCardStats __instance)
        {
            if (!LimitlessFence.RecordOpen) return;
            try { LimitlessApply.ClampPlayer(__instance.playerToUpgrade); }
            catch (Exception ex) { Plugin.Log.LogWarning("[LIMIT] clamp: " + ex.Message); }
        }
    }

    /// <summary>The card bar's hook: after each icon vanilla adds, the bar
    /// keeps the newest NewestCards.</summary>
    [HarmonyPatch(typeof(CardBar), "AddCard")]
    internal static class LimitlessApply_CardBar_Patch
    {
        private static void Postfix(CardBar __instance)
        {
            if (!LimitlessFence.RecordOpen) return;
            try { LimitlessApply.TrimBar(__instance); }
            catch (Exception ex) { Plugin.Log.LogWarning("[LIMIT] card bar: " + ex.Message); }
        }
    }
}
