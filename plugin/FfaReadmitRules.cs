using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.ExceptionServices;

namespace CompetitiveRounds
{
    /// <summary>
    /// FFA mid-game readmission (design V3, ai-collab/rejoin/RJ-READMIT-DESIGN-V3.md):
    /// the pure rules. Nothing in this file touches Unity, Photon or BepInEx,
    /// so tools/tests/rj-readmit-client compiles it under a plain compiler and
    /// RUNS the rules rather than asserting about their source (#391).
    ///
    /// Every behaviour these rules drive is confined to a readmission lobby:
    /// a lobby whose readmit flag the server wrote at lock and every client
    /// pinned for the sitting (V3 P4.6). Outside one, nothing here is called.
    /// </summary>
    internal static class FfaReadmitRules
    {
        // ------------------------------------------------------------------ P1: the apply plan

        /// <summary>The values ApplyManifestPick computes from the deck and the
        /// card name before it writes anything: the prefab, whether the deck
        /// rolls, the survivors and the dropped card's raw name. Computed once,
        /// read at the statements that read them (V3 P1).</summary>
        internal sealed class ApplyPlan<T> where T : class
        {
            internal T Prefab;
            internal bool Rolls;
            internal List<T> Survivors;
            private string _droppedRaw;
            private ExceptionDispatchInfo _droppedFault;

            /// <summary>The raw name of the card that rolls off. A fault while
            /// reading it surfaces HERE, where the pre-split reducer read it,
            /// so a throw stops the reducer at the same statement as before.</summary>
            internal string DroppedRaw()
            {
                if (_droppedFault != null) _droppedFault.Throw();
                return _droppedRaw;
            }

            internal void SetDropped(Func<string> read)
            {
                try { _droppedRaw = read(); }
                catch (Exception ex) { _droppedFault = ExceptionDispatchInfo.Capture(ex); }
            }
        }

        /// <summary>PlanApply: no side effect. The prefab is resolve(cardName);
        /// the deck rolls when it holds cardCap or more cards; the survivors
        /// are its LAST cardCap - 1 entries and the dropped card is entry 0,
        /// "(Clone)" removed. A null deck is an empty one.</summary>
        internal static ApplyPlan<T> PlanApply<T>(IList<T> deck, string cardName, int cardCap,
                                                  Func<string, T> resolve, Func<T, string> rawName) where T : class
        {
            var plan = new ApplyPlan<T> { Prefab = resolve(cardName) };
            int count = deck == null ? 0 : deck.Count;
            if (count >= cardCap)
            {
                plan.Rolls = true;
                plan.Survivors = deck.Skip(count - (cardCap - 1)).ToList();
                var first = deck[0];
                plan.SetDropped(() => rawName(first).Replace("(Clone)", ""));
            }
            return plan;
        }
    }
}
