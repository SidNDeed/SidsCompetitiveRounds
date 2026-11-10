using System;

namespace CompetitiveRounds
{
    /// <summary>
    /// A value set for the length of one call, with the enclosing value restored
    /// in a finally: after a nested call, and after an exception inside the call.
    /// PoisonRpcStampPatch.RunStamped runs the continuation fence's direct
    /// RPCA_NextRound call under its message's stamp this way (ask 16(a) lane 2,
    /// v4 4.7 step 5). Pure, so the client rules harness runs it (suite
    /// fencerules, the "frame:" cases).
    /// </summary>
    internal static class ScopedFrame
    {
        internal static void RunInFrame<T>(Func<T> get, Action<T> set, T value, Action call)
        {
            T saved = get();
            set(value);
            try { call(); }
            finally { set(saved); }
        }
    }
}
