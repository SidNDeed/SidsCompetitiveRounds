using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Bug 389 Gate 0 — the PURE half of the trigger-wiring probe.
    ///
    /// This file deliberately references NOTHING from Unity, Harmony or the rest
    /// of the plugin, so the formatter and the bound can be compiled and executed
    /// by a plain console harness (#340/#465: not reviewed until it has RUN). The
    /// Unity-facing half lives in Gate0TriggerWiringProbe.cs and calls in here.
    ///
    /// What Gate 0 is for: the bug 389 diagnosis reads, from DECOMPILED code, that
    /// A_Lifestealer's PlayerInRangeTrigger.triggerEvent invokes
    /// DealDamageToPlayer.Go. The prefab that carries that wiring lives in an asset
    /// bundle and cannot be read from the decompile, so the link is READ, not
    /// PROVEN, on the seat that reports the bug (#405/#286). No fix code ships
    /// until a real game prints the persistent-call list and it names
    /// DealDamageToPlayer / Go.
    /// </summary>
    internal static class Gate0WiringFormat
    {
        /// <summary>The probe token. It exists for NO other purpose than to be
        /// grepped (#306): it is not a user-visible string, not a translation key,
        /// not a type name, and no feature can ever want it. Acceptance for Gate 0
        /// is a grep of this literal in LogOutput.log.</summary>
        internal const string Token = "SCR_GATE0_389=1";

        /// <summary>Emitted ONCE, at Harmony patch time, when the target method has
        /// actually been resolved. A positive attach signal rather than the absence
        /// of an error (#438/#443), and the thing that distinguishes "attached but
        /// never reached" from "never attached" (#83).</summary>
        internal const string AttachToken = "SCR_GATE0_389_ATTACH=1";

        /// <summary>THE BOUND. At most this many DISTINCT wirings are ever reported,
        /// and a wiring that has already been reported is never reported again. A
        /// PlayerInRangeTrigger is constructed once per effect object per round, so
        /// an unbounded probe would print a line every round for every drain card in
        /// the room; with the bound the whole sitting costs at most
        /// MaxWirings + 1 lines (the attach line is the +1). The same number is
        /// handed to VanillaFixSupport.DiagLimited as its own budget, so the log
        /// bound holds even if the de-duplicating set is somehow bypassed.</summary>
        internal const int MaxWirings = 24;

        /// <summary>Hard ceiling on how many persistent calls are read off one
        /// event, so a malformed list cannot produce an unbounded line.</summary>
        internal const int MaxCallsPerEvent = 16;

        /// <summary>Hard ceiling on how many ancestors are walked for the path.</summary>
        internal const int MaxPathDepth = 8;

        /// <summary>Make one field safe to embed in a space-separated key=value
        /// line. Unity object names are asset names, so this is belt-and-braces
        /// rather than a real hazard — but a name carrying a space or a newline
        /// would split the line and break the acceptance grep.</summary>
        internal static string Sanitize(string value)
        {
            if (string.IsNullOrEmpty(value)) return "?";
            var sb = new StringBuilder(value.Length);
            for (int i = 0; i < value.Length; i++)
            {
                char c = value[i];
                if (c < 0x20 || c == 0x7f) sb.Append('.');
                else if (c == ' ' || c == '\t') sb.Append('_');
                else sb.Append(c);
            }
            return sb.ToString();
        }

        private static string At(IList<string> list, int index)
        {
            if (list == null || index < 0 || index >= list.Count) return "?";
            string v = list[index];
            return string.IsNullOrEmpty(v) ? "?" : Sanitize(v);
        }

        /// <summary>The de-duplication key. Two triggers with the same ancestor path
        /// AND the same persistent-call list are the same WIRING and are reported
        /// once. Deliberately does NOT include the persistent-call COUNT on its own:
        /// the call list already determines it.</summary>
        internal static string Signature(string path, IList<string> targetTypes, IList<string> methodNames)
        {
            var sb = new StringBuilder();
            sb.Append(Sanitize(path));
            int count = 0;
            if (targetTypes != null) count = targetTypes.Count;
            if (methodNames != null && methodNames.Count > count) count = methodNames.Count;
            for (int i = 0; i < count; i++)
            {
                sb.Append('|').Append(At(targetTypes, i)).Append('.').Append(At(methodNames, i));
            }
            return sb.ToString();
        }

        /// <summary>The one line Gate 0 exists to print. Shape:
        ///
        ///   SCR_GATE0_389=1 path=A_Lifestealer/Trigger calls=1 [0]=DealDamageToPlayer.Go
        ///
        /// ACCEPTANCE (stated here so the code and the notes cannot drift, #302):
        /// the line whose path names A_Lifestealer must carry an entry naming
        /// DealDamageToPlayer and Go. If it does not, section 2 of the diagnosis is
        /// refuted and the diagnosis is redone before any fix is written.
        ///
        /// `calls` is the raw GetPersistentEventCount(). A negative count means the
        /// event field itself was null and is printed as `calls=null`, which is a
        /// DIFFERENT observation from `calls=0` (an event with an empty list) and
        /// must not be collapsed into it.</summary>
        internal static string FormatWiring(string path, int count, IList<string> targetTypes, IList<string> methodNames)
        {
            var sb = new StringBuilder();
            sb.Append(Token);
            sb.Append(" path=").Append(Sanitize(path));
            sb.Append(" calls=");
            if (count < 0) sb.Append("null");
            else sb.Append(count.ToString(CultureInfo.InvariantCulture));

            int listed = 0;
            if (targetTypes != null) listed = targetTypes.Count;
            if (methodNames != null && methodNames.Count > listed) listed = methodNames.Count;
            if (listed > MaxCallsPerEvent) listed = MaxCallsPerEvent;

            for (int i = 0; i < listed; i++)
            {
                sb.Append(" [").Append(i.ToString(CultureInfo.InvariantCulture)).Append("]=");
                sb.Append(At(targetTypes, i)).Append('.').Append(At(methodNames, i));
            }
            return sb.ToString();
        }
    }

    /// <summary>The bound, as a testable object. Admits each distinct wiring
    /// signature once and never admits more than Gate0WiringFormat.MaxWirings of
    /// them — so neither a repeated wiring (the ordinary case: one trigger rebuilt
    /// every round) nor an unexpectedly varied one (the pathological case) can
    /// flood the log.</summary>
    internal sealed class Gate0WiringBudget
    {
        private readonly object _sync = new object();
        private readonly HashSet<string> _seen = new HashSet<string>(StringComparer.Ordinal);
        private int _admitted;
        private bool _overflowed;

        /// <summary>How many distinct wirings have been reported.</summary>
        internal int Admitted { get { lock (_sync) { return _admitted; } } }

        /// <summary>True once the cap has refused at least one NEW signature. Read
        /// by the tests; the probe does not log it, because logging the overflow
        /// would itself be an unbounded line source.</summary>
        internal bool Overflowed { get { lock (_sync) { return _overflowed; } } }

        internal bool TryAdmit(string signature)
        {
            if (signature == null) return false;
            lock (_sync)
            {
                if (_seen.Contains(signature)) return false;
                if (_admitted >= Gate0WiringFormat.MaxWirings)
                {
                    _overflowed = true;
                    return false;
                }
                _seen.Add(signature);
                _admitted++;
                return true;
            }
        }
    }
}
