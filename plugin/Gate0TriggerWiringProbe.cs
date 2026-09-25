using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text;
using HarmonyLib;
using UnityEngine;
using UnityEngine.Events;

namespace CompetitiveRounds
{
    /// <summary>
    /// Bug 389 Gate 0 — prove the prefab wiring before any fix is written.
    ///
    /// The bug 389 diagnosis says LIFESTEALER's proximity ring
    /// (PlayerInRangeTrigger) invokes DealDamageToPlayer.Go, and that
    /// DealDamageToPlayer caches its victim on the first call
    /// (DealDamageToPlayer.cs:24,33-40) so the drain keeps landing on whoever was
    /// nearest the FIRST time the card ever fired. The cache is read straight off
    /// the decompile and is not in doubt. The WIRING was the open question: the
    /// persistent-call list lives in a serialized prefab, so the link between the
    /// ring and the damage component was a reading, not a measurement, on the seat
    /// that reports the bug (#405 — verify reachability before logic; #286 — do
    /// not reason about a path without checking it is the one that runs).
    ///
    /// This class measures it in a running game. It is a Postfix on
    /// PlayerInRangeTrigger.Start that reads the event's persistent-call list and
    /// prints it once per distinct wiring. It CHANGES NO BEHAVIOUR: it writes
    /// nothing, gates nothing, returns nothing to vanilla, and every statement in
    /// it is inside a catch-all so a diagnostic can never alter vanilla control
    /// flow.
    ///
    /// It is deliberately UNGATED by mode or room (the same choice
    /// RadarVisualLifetimePatch documents): a log line cannot desynchronise a
    /// simulation, and gating a probe on the feature it is meant to characterise
    /// would inherit that feature's dead zone (#272). It IS bounded — see
    /// Gate0WiringFormat.MaxWirings, and the overflow is announced rather than
    /// silent.
    ///
    /// ACCEPTANCE: in a real match where LIFESTEALER is picked, LogOutput.log
    /// carries a line matching
    /// `SCR_GATE0_389=1.*A_Lifestealer.*DealDamageToPlayer\.Go`. The bare token on
    /// its own is NOT the acceptance — it matches the sibling A_ChillingPresence
    /// ring too. See Gate0WiringFormat.FormatWiring.
    ///
    /// WHAT THE IN-GAME RUN ADDS. The wiring question itself was settled offline
    /// from the shipped assets (ai-collab/bugs/BUG389-GATE0-OFFLINE.md, CONFIRMED
    /// by two independent passes: trigger 10029 on A_Lifestealer, 7 persistent
    /// calls, [6] to DealDamageToPlayer.Go). What that read cannot show is
    /// REACHABILITY — that this component starts, and this event carries that list,
    /// on the seat that plays the match. That is what this probe measures, and it
    /// is why it exists after the offline answer rather than instead of it.
    ///
    /// ATTACHMENT: a diagnostic patch can silently fail to attach and produce zero
    /// data for release cycles (#83). Two INDEPENDENT defences: the target is
    /// resolved explicitly and a miss THROWS, which the per-class patch loop in
    /// Plugin.cs reports as "[HARMONY] Failed to patch Gate0TriggerWiringProbe";
    /// and SCR_GATE0_389_ATTACH=1 is emitted from [HarmonyCleanup] on a null
    /// exception — i.e. only once Harmony has finished installing the wrapper.
    /// Emitting it from TargetMethod() instead would time it at target RESOLUTION,
    /// before the wrapper is generated, so a failure in that later step would print
    /// the attach line and install nothing: the second defence would be a restating
    /// of the first rather than independent of it.
    /// </summary>
    [HarmonyPatch]
    internal static class Gate0TriggerWiringProbe
    {
        /// <summary>DiagLimited budget key. Not reset at any room edge on purpose:
        /// the wiring of a prefab cannot change between rooms, so one sitting's
        /// budget is the whole answer and a per-room reset would only re-print what
        /// was already printed.</summary>
        internal const string DiagKey = "Gate0Wiring389";

        /// <summary>A SEPARATE budget key for the overflow line, with a maximum of
        /// one. It must not share DiagKey: by the time the cap overflows, DiagKey's
        /// own budget is exhausted by construction, so an overflow line billed to it
        /// could never be printed — the announcement would be swallowed by the very
        /// exhaustion it exists to announce.</summary>
        internal const string OverflowDiagKey = "Gate0Wiring389Overflow";

        private static readonly Gate0WiringBudget Budget = new Gate0WiringBudget();

        private static MethodBase TargetMethod()
        {
            MethodBase target = AccessTools.DeclaredMethod(typeof(PlayerInRangeTrigger), "Start");
            if (target == null)
            {
                // Loud, not silent (#83). The per-class processor loop in
                // Plugin.Awake catches this and logs
                // "[HARMONY] Failed to patch Gate0TriggerWiringProbe: ...",
                // which is the grep the witness procedure names.
                throw new MissingMethodException("PlayerInRangeTrigger", "Start");
            }

            // Deliberately silent here. Resolving the target is not attaching to it;
            // the attach signal belongs in Cleanup below.
            return target;
        }

        /// <summary>The positive attach signal, on the same shape as the shipped
        /// VanillaFixSupport.Cleanup patches. Harmony calls this once at class level
        /// with a null `original` after the patch job has run; a null `exception`
        /// there means the wrapper was generated and installed.</summary>
        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            try
            {
                if (exception == null)
                {
                    Plugin.Log.LogInfo("[VANILLA-DIAG] " + Gate0WiringFormat.AttachToken
                        + " target=PlayerInRangeTrigger.Start bound=" + Gate0WiringFormat.MaxWirings);
                }
            }
            catch { }
            return exception;
        }

        /// <summary>Ancestor names from the trigger up to the root, bounded. The
        /// card object (A_Lifestealer / A_ChillingPresence) is somewhere on this
        /// chain but not at a fixed depth, so the whole bounded chain is printed
        /// rather than one guessed level — a probe that looked only at
        /// transform.root would report the Player object on every line and could
        /// never name the card, i.e. a check that cannot answer the question it was
        /// written for (#342).</summary>
        private static string AncestorPath(Transform start)
        {
            var names = new List<string>();
            Transform t = start;
            for (int depth = 0; t != null && depth < Gate0WiringFormat.MaxPathDepth; depth++)
            {
                names.Add(t.name);
                t = t.parent;
            }
            var sb = new StringBuilder();
            for (int i = names.Count - 1; i >= 0; i--)
            {
                if (sb.Length > 0) sb.Append('/');
                sb.Append(names[i]);
            }
            return sb.ToString();
        }

        [HarmonyPostfix]
        private static void AfterStart(PlayerInRangeTrigger __instance)
        {
            try
            {
                if (__instance == null) return;

                string path = AncestorPath(__instance.transform);

                UnityEvent evt = __instance.triggerEvent;
                // Three distinct observations, never collapsed: the event field was
                // null; the count could not be read; the count is a number.
                int count = Gate0WiringFormat.CountEventNull;
                var targetTypes = new List<string>();
                var methodNames = new List<string>();

                if (evt != null)
                {
                    try { count = evt.GetPersistentEventCount(); }
                    catch { count = Gate0WiringFormat.CountReadFailed; }

                    int listed = count;
                    if (listed > Gate0WiringFormat.MaxCallsPerEvent) listed = Gate0WiringFormat.MaxCallsPerEvent;
                    for (int i = 0; i < listed; i++)
                    {
                        string typeName;
                        try
                        {
                            UnityEngine.Object persistentTarget = evt.GetPersistentTarget(i);
                            typeName = persistentTarget == null ? "null" : persistentTarget.GetType().Name;
                        }
                        catch { typeName = "err"; }

                        string methodName;
                        try { methodName = evt.GetPersistentMethodName(i) ?? "null"; }
                        catch { methodName = "err"; }

                        targetTypes.Add(typeName);
                        methodNames.Add(methodName);
                    }
                }

                // The bound, applied before the message is built. The count is part
                // of the signature, so a degraded reading of a ring cannot suppress
                // the healthy reading that the next round's re-instantiation brings.
                if (!Budget.TryAdmit(Gate0WiringFormat.Signature(path, count, targetTypes, methodNames)))
                {
                    // Announce the cap exactly once. An absent wiring line otherwise
                    // means both "the ring never started" and "the budget ran out
                    // first", and the witness procedure gives the first one a
                    // definite meaning (#342).
                    if (Budget.TryClaimOverflowReport())
                    {
                        VanillaFixSupport.DiagLimited(
                            OverflowDiagKey,
                            Gate0WiringFormat.FormatOverflow(Budget.Admitted),
                            1);
                    }
                    return;
                }

                VanillaFixSupport.DiagLimited(
                    DiagKey,
                    Gate0WiringFormat.FormatWiring(path, count, targetTypes, methodNames),
                    Gate0WiringFormat.MaxWirings);
            }
            catch
            {
                // A diagnostic never affects vanilla control flow.
            }
        }
    }
}
