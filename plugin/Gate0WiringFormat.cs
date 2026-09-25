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
    /// DealDamageToPlayer.Go. The prefab that carries that wiring lives in a
    /// serialized asset file, so the link was READ, not PROVEN, on the seat that
    /// reports the bug (#405/#286).
    ///
    /// SCOPE — what this probe can and cannot see. It reads the SERIALIZED
    /// persistent-call list, which is the wiring as authored at build time.
    /// Listeners added at runtime through UnityEvent.AddListener have no public
    /// runtime accessor and are invisible here. So an empty list supports
    /// "there is no PERSISTENT wiring" and NOT "there is no wiring" — the two are
    /// different sentences and the notes state the weaker one (#302). The
    /// offline asset read (BUG389-GATE0-OFFLINE.md) measured zero AddListener
    /// calls on any triggerEvent across the decompiled sources and zero
    /// triggerEvent references in plugin/, which bounds that gap but does not
    /// close it.
    /// </summary>
    internal static class Gate0WiringFormat
    {
        /// <summary>The probe token. It exists for NO other purpose than to be
        /// grepped (#306): it is not a user-visible string, not a translation key,
        /// not a type name, and no feature can ever want it.</summary>
        internal const string Token = "SCR_GATE0_389=1";

        /// <summary>Emitted ONCE, from the patch class's [HarmonyCleanup] and only
        /// when Harmony reports a null exception — i.e. after the wrapper has been
        /// generated and installed, not merely after the target was resolved.
        ///
        /// The distinction is the whole value of the signal. TargetMethod() runs
        /// FIRST and only resolves the MethodBase; the wrapper is built afterwards
        /// and can still fail there (a conflicting patch on the same Unity message,
        /// an IL or Mono failure). A token emitted from TargetMethod() would prove
        /// resolution while being read as attachment, so it could not be the
        /// independent second defence #83 asks for. [HarmonyCleanup] is the shipped
        /// precedent for this signal — VanillaFixSupport.Cleanup uses exactly it.</summary>
        internal const string AttachToken = "SCR_GATE0_389_ATTACH=1";

        /// <summary>Emitted at most ONCE per sitting, the first time the cap refuses
        /// a NEW wiring. Without it, "the budget ran out before this ring started"
        /// and "this ring never started" are the same log (an absent line) while the
        /// witness procedure gives the second one a definite meaning — a check that
        /// cannot distinguish its two outcomes (#342). One line on the first
        /// overflow is bounded by construction, so the bound is not a reason to stay
        /// silent. Deliberately NOT a substring of Token, so the acceptance grep
        /// cannot match it.</summary>
        internal const string OverflowToken = "SCR_GATE0_389_OVERFLOW=1";

        /// <summary>THE BOUND. At most this many DISTINCT wirings are ever reported,
        /// and a wiring that has already been reported is never reported again. A
        /// PlayerInRangeTrigger is constructed once per effect object per round, so
        /// an unbounded probe would print a line every round for every drain card in
        /// the room; with the bound the whole sitting costs at most
        /// MaxWirings + 2 lines (the attach line and the overflow line). The same
        /// number is handed to VanillaFixSupport.DiagLimited as its own budget, so
        /// the log bound holds even if the de-duplicating set is somehow bypassed.</summary>
        internal const int MaxWirings = 24;

        /// <summary>Hard ceiling on how many persistent calls are read off one
        /// event, so a malformed list cannot produce an unbounded line.</summary>
        internal const int MaxCallsPerEvent = 16;

        /// <summary>Hard ceiling on how many ancestors are walked for the path.</summary>
        internal const int MaxPathDepth = 8;

        /// <summary>`triggerEvent` itself was null. A different observation from an
        /// event carrying an empty list, and from a count that could not be read.</summary>
        internal const int CountEventNull = -1;

        /// <summary>GetPersistentEventCount() threw. This is a DEGRADED reading, not
        /// a measurement of the ring: the list may be perfectly well populated. It
        /// is kept distinct from CountEventNull so a reader is never told "the event
        /// field was null" about a ring whose count merely could not be read.</summary>
        internal const int CountReadFailed = -2;

        /// <summary>True when the count represents a failure to measure rather than a
        /// measured number. Such a reading must never stand in for a healthy one —
        /// see Signature.</summary>
        internal static bool IsDegraded(int count)
        {
            return count < 0;
        }

        /// <summary>How a count is rendered, in the line and in the signature, so the
        /// two can never disagree about what was observed.</summary>
        internal static string CountToken(int count)
        {
            if (count == CountEventNull) return "null";
            if (count < 0) return "err";
            return count.ToString(CultureInfo.InvariantCulture);
        }

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

        /// <summary>The de-duplication key. Two triggers with the same ancestor path,
        /// the same COUNT and the same persistent-call list are the same WIRING and
        /// are reported once.
        ///
        /// The count is IN the key, and that is load-bearing rather than redundant.
        /// A reading can be degraded — the event field momentarily null, or the
        /// count unreadable — and produce an empty call list for a ring that is in
        /// fact wired. The ring is destroyed and re-instantiated every round
        /// (CharacterStatModifiers, ApplyCardStats.cs:159), so Start runs again and
        /// a healthy reading of the SAME ring is coming. Keyed on path and call list
        /// alone, the degraded reading would be admitted first and would then
        /// suppress every healthy reading of that ring for the rest of the process,
        /// leaving the witness a line that names the card and names no target — the
        /// exact shape the notes route to "section 2 is refuted". Keying on the
        /// count as well lets the healthy reading through as the distinct
        /// observation it is.</summary>
        internal static string Signature(string path, int count, IList<string> targetTypes, IList<string> methodNames)
        {
            var sb = new StringBuilder();
            sb.Append(Sanitize(path));
            sb.Append('#').Append(CountToken(count));
            int listed = 0;
            if (targetTypes != null) listed = targetTypes.Count;
            if (methodNames != null && methodNames.Count > listed) listed = methodNames.Count;
            for (int i = 0; i < listed; i++)
            {
                sb.Append('|').Append(At(targetTypes, i)).Append('.').Append(At(methodNames, i));
            }
            return sb.ToString();
        }

        /// <summary>The one line Gate 0 exists to print. Shape:
        ///
        ///   SCR_GATE0_389=1 path=Player(Clone)/A_Lifestealer(Clone) calls=7 [0]=... [6]=DealDamageToPlayer.Go
        ///
        /// ACCEPTANCE (stated here so the code and the notes cannot drift, #302).
        /// `path` is emitted BEFORE `calls`, so the whole acceptance is one regex
        /// over the log rather than a human reading:
        ///
        ///   SCR_GATE0_389=1.*A_Lifestealer.*DealDamageToPlayer\.Go
        ///
        /// A bare grep for the token is NOT the acceptance: it matches every wiring
        /// line the probe prints, including the sibling A_ChillingPresence ring, so
        /// it returns non-empty whether or not the Lifestealer ring names the damage
        /// component — a check that cannot fail (#342).
        ///
        /// The object name is matched as a SUBSTRING on purpose: the probe walks a
        /// live instance, and Object.Instantiate appends "(Clone)" to every name on
        /// the chain. The name itself is measured, not assumed — it is read from the
        /// shipped asset in BUG389-GATE0-OFFLINE.md (GameObject "A_Lifestealer",
        /// sharedassets0.assets path id 2577), confirmed by a second independent
        /// pass. If a future game build re-authors the prefab, that document is what
        /// gets re-pinned, and the acceptance regex follows it.
        ///
        /// `calls` is the raw GetPersistentEventCount(): a number when it was read,
        /// `null` when the event field itself was null, and `err` when the count
        /// could not be read. All three are different observations and none may be
        /// collapsed into another.</summary>
        internal static string FormatWiring(string path, int count, IList<string> targetTypes, IList<string> methodNames)
        {
            var sb = new StringBuilder();
            sb.Append(Token);
            sb.Append(" path=").Append(Sanitize(path));
            sb.Append(" calls=").Append(CountToken(count));

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

        /// <summary>The single overflow line. Carries the cap that was hit, so a
        /// reader can tell a budget exhaustion from a silent absence.</summary>
        internal static string FormatOverflow(int admitted)
        {
            return OverflowToken
                + " admitted=" + admitted.ToString(CultureInfo.InvariantCulture)
                + " cap=" + MaxWirings.ToString(CultureInfo.InvariantCulture)
                + " further-distinct-wirings-not-reported";
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
        private bool _overflowReported;

        /// <summary>How many distinct wirings have been reported.</summary>
        internal int Admitted { get { lock (_sync) { return _admitted; } } }

        /// <summary>True once the cap has refused at least one NEW signature.</summary>
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

        /// <summary>Returns true for the FIRST signature the cap refuses, and false
        /// forever after. The caller emits one line on that true, which is how the
        /// overflow becomes visible without becoming a per-tick line source: the
        /// claim is bounded here, at the claim, not at the logging call site.</summary>
        internal bool TryClaimOverflowReport()
        {
            lock (_sync)
            {
                if (!_overflowed || _overflowReported) return false;
                _overflowReported = true;
                return true;
            }
        }
    }
}
