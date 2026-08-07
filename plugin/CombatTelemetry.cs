using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Aug 6 items 1+4 — expanded combat telemetry. All NEW capture hooks live
    /// here (one file, one concern) and feed GameStateWatcher's per-match
    /// fields; the pre-existing FFA damage tracker in VanillaFixes.cs is
    /// untouched (Harmony runs both postfixes on DealtDamage independently).
    ///
    /// Captured:
    ///  - damage dealt (all modes, dealer-side, DOT/explosions included per
    ///    #137's attribution model — same rule the FFA tracker uses)
    ///  - highest single damage event dealt
    ///  - death classification for EVERY player death this client simulates
    ///    (normal / out-of-bounds / own-bullet), consumed per-side by the
    ///    match reporter (#4: only one client reports, so the reporter's
    ///    LOCAL observations must cover both seats)
    ///  - bullet bounce count at kill time ("most bounces before a
    ///    successful non-self kill")
    ///
    /// None of this touches any HMAC canonical — every new report field rides
    /// outside the signed string (hard rule: the 7/10/11-field canonicals are
    /// frozen).
    /// </summary>
    internal static class CombatTelemetry
    {
        // ── death-stamp table ──
        // Last APPLIED damage per player viewID: kind + wall-clock. Written by
        // the DoDamage health-delta pair below, read by the RPCA_Die prefix.
        // Bounded: entries are overwritten per viewID and the table is cleared
        // on match start (GameStateWatcher.ResetCombatTelemetry).
        internal struct DamageStamp
        {
            public int kind;      // 0 normal, 1 out-of-bounds, 2 own bullet
            public float time;    // Time.unscaledTime
        }
        internal static readonly Dictionary<int, DamageStamp> LastDamageByView =
            new Dictionary<int, DamageStamp>();

        // How fresh a stamp must be to explain a death. OOB kills apply damage
        // and die in the same call chain; DOT deaths tick within 1s windows.
        private const float STAMP_FRESH_SECONDS = 2f;

        internal static void ClearMatchState()
        {
            try { LastDamageByView.Clear(); } catch { }
        }

        // ─────────────────────────────────────────────────────────────────
        /// <summary>Dealer-side damage tracking for ALL modes. Same hook +
        /// attribution semantics as the FFA tracker (VanillaFixes.cs): fires
        /// once per unit of damage that actually landed, DOT included, on the
        /// DEALER's stats component. Local dealer only — every client tracks
        /// its own dealt damage and it reaches the server via the report /
        /// cr_gstats peer channel.</summary>
        [HarmonyPatch(typeof(CharacterStatModifiers), "DealtDamage")]
        internal static class DamageDealtLocalTrackerPatch
        {
            [HarmonyPostfix]
            private static void AfterDealtDamage(CharacterStatModifiers __instance, Vector2 damage,
                                                 bool selfDamage, Player damagedPlayer)
            {
                try
                {
                    if (selfDamage || damagedPlayer == null) return;
                    if (!VanillaFixSupport.AnyGameScope()) return;
                    var dealer = __instance != null ? __instance.GetComponent<Player>() : null;
                    if (dealer == null || dealer.data == null || dealer.data.view == null) return;
                    if (!dealer.data.view.IsMine) return;
                    // Same-team damage (2v2 friendly fire) still shouldn't
                    // count toward DPS — mirror the FFA tracker's foe gate.
                    if (damagedPlayer.TeamID == dealer.TeamID) return;
                    GameStateWatcher.RecordLocalDamageDealt(damage.magnitude);
                }
                catch { }
            }
        }

        // ─────────────────────────────────────────────────────────────────
        /// <summary>Damage-source stamp on HealthHandler.DoDamage, written in
        /// the PREFIX and retracted in the Postfix if nothing landed.
        ///
        /// Codex round 2 (MEDIUM) — the ORDERING is the whole point. This
        /// originally stamped in the Postfix on a health delta, which reads
        /// correctly and is wrong: vanilla calls
        /// <c>data.view.RPC("RPCA_Die", RpcTarget.All, ...)</c> from INSIDE
        /// DoDamage (HealthHandler.cs:294), and PUN invokes an All-target RPC
        /// locally before returning. So the death classifier ran BEFORE the
        /// Postfix ever stamped, saw no entry for that view, and recorded
        /// kind=0. A boundary death is typically a single lethal 51-damage
        /// hit with no prior stamp — so self-death %, the entire point of the
        /// classification, could never count the boundary deaths it exists to
        /// measure.
        ///
        /// Stamping in the Prefix fixes the order. The #256 concern (a bare
        /// Postfix credits the early-returned calls too) is handled by
        /// RETRACTING the stamp when health did not actually drop, which is
        /// strictly better: a blocked hit leaves no residue at all, where the
        /// old shape left the PREVIOUS stamp in place to be misread by a
        /// later death.</summary>
        [HarmonyPatch(typeof(HealthHandler), "DoDamage")]
        internal static class DamageStampPatch
        {
            [HarmonyPrefix]
            private static void Prefix(HealthHandler __instance, Player damagingPlayer,
                                       HealthHandler.DamageSource damageSource, out float __state)
            {
                __state = float.MinValue;
                try
                {
                    // Assembly-CSharp is fully publicized — direct field access.
                    var data = __instance != null ? __instance.data : null;
                    if (data == null || data.view == null) return;
                    __state = data.health;
                    if (!VanillaFixSupport.AnyGameScope()) return;
                    var victim = data.player;
                    int kind = 0;
                    if (damageSource == HealthHandler.DamageSource.OutOfBounds) kind = 1;
                    else if (damagingPlayer != null && victim != null && damagingPlayer == victim) kind = 2;
                    LastDamageByView[data.view.ViewID] = new DamageStamp
                    {
                        kind = kind,
                        time = Time.unscaledTime,
                    };
                }
                catch { }
            }

            [HarmonyPostfix]
            private static void Postfix(HealthHandler __instance, float __state)
            {
                try
                {
                    if (__state == float.MinValue) return;
                    var data = __instance != null ? __instance.data : null;
                    if (data == null || data.view == null) return;
                    // Nothing landed (blocked / not playing / already dead):
                    // retract the speculative stamp so it can never explain a
                    // LATER death. A death that really happened has already
                    // read it synchronously inside the vanilla body above.
                    if (data.health >= __state)
                        LastDamageByView.Remove(data.view.ViewID);
                }
                catch { }
            }
        }

        /// <summary>Death classifier — every death this client simulates, both
        /// seats. RPCA_Die fires on all clients (RpcTarget.All), so the match
        /// REPORTER's local observation covers the opponent too.</summary>
        [HarmonyPatch(typeof(HealthHandler), "RPCA_Die")]
        internal static class DeathClassifierPatch
        {
            [HarmonyPrefix]
            private static void Prefix(HealthHandler __instance)
            {
                try
                {
                    if (!VanillaFixSupport.AnyGameScope()) return;
                    var data = __instance != null ? __instance.data : null;
                    if (data == null || data.view == null) return;

                    // Codex round 1 (HIGH): mirror vanilla's own dedup guard.
                    // RPCA_Die opens with `if (data.isPlaying && !data.dead)`
                    // (HealthHandler.cs:368) precisely because the RPC arrives
                    // more than once: every replica runs DoDamage for the same
                    // RpcTarget.All hit, each crosses zero, and each broadcasts
                    // its own RPCA_Die(All). Vanilla accepts the first and
                    // ignores the rest — a Prefix that counts BEFORE the guard
                    // multiplies every real death by the number of replicas
                    // that broadcast it, which in a 1v1 doubles the death
                    // counts feeding self-death %.
                    if (!data.isPlaying || data.dead) return;

                    int kind = 0;
                    DamageStamp stamp;
                    if (LastDamageByView.TryGetValue(data.view.ViewID, out stamp)
                        && Time.unscaledTime - stamp.time < STAMP_FRESH_SECONDS)
                        kind = stamp.kind;
                    GameStateWatcher.RecordDeathObserved(data.view.IsMine, kind);

                }
                catch { }
            }
        }

        // ─────────────────────────────────────────────────────────────────
        /* ── BOUNCE-KILL TRACKING IS CUT FROM THIS RELEASE ──────────────
         *
         * "Most bounces before a kill" needed to answer one question — did
         * THIS bounced shot kill them — and two attempts both got it wrong in
         * a way that writes a PERMANENT career record
         * (players.record_bounce_kill is a GREATEST update; a false credit can
         * never be walked back):
         *
         *   1. Predict lethality from the projectile's raw damage. Wrong:
         *      vanilla scales by the shooter's bullet-damage multiplier and
         *      percentage modifiers before touching health, so a sub-1
         *      multiplier banked kills on players who survived, and
         *      percentage damage produced the inverse miss (r3).
         *   2. Record the bounce as pending and confirm it at the death.
         *      Wrong: that proves temporal PROXIMITY, not causation — a
         *      non-lethal bounce followed within the window by a direct kill
         *      shot credits the bounce (r4).
         *
         * A correct version has to bind the credit to the actual terminal
         * damage event and clear it on any intervening damage, i.e. it needs
         * the damage pipeline this file deliberately does not reimplement.
         * That is a real piece of work for a leaderboard nicety, so the stat
         * is cut rather than shipped wrong: no capture, nothing reported, and
         * the server column stays unused and NULL.
         *
         * Everything else in this file — damage dealt, max single hit, max
         * health, death classification — is unaffected.
         */
    }
}
