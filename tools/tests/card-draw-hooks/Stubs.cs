// Stubs for the card draw evidence hook harness. The patch classes under test
// (and the test gate class) are copied VERBATIM from plugin/CardDrawEvidence.cs
// by run_hooks.py; everything they call into is defined here. Every collector
// THROWS after recording the arguments it was given, so a hook passes only
// when it contains its own faults and forwards its own arguments.
using System;
using System.Collections.Generic;

namespace HarmonyLib
{
    [AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true)]
    public class HarmonyPatch : Attribute
    {
        public readonly Type Target;
        public readonly string Method;
        public HarmonyPatch(Type t, string m) { Target = t; Method = m; }
    }
    [AttributeUsage(AttributeTargets.Class | AttributeTargets.Method)]
    public class HarmonyPriority : Attribute
    {
        public readonly int Value;
        public HarmonyPriority(int v) { Value = v; }
    }
    // HarmonyX's values: Last = 0, Normal = 400, First = 800
    public static class Priority { public const int Last = 0, VeryLow = 100, Low = 200, LowerThanNormal = 300, Normal = 400, First = 800; }
    public class HarmonyPrefix : Attribute { }
    public class HarmonyPostfix : Attribute { }
    public class HarmonyFinalizer : Attribute { }
}

// -- game types (global namespace, as in Assembly-CSharp) ----------------------------
public class CardChoice { }
public class CardInfo { }
public class ApplyCardStats { }
public class Player { }

namespace CompetitiveRounds
{
    internal static class Planted
    {
        internal static int Calls;
        internal static string Collector;
        internal static object[] Args;
        internal static Exception Fault(string collector, params object[] args)
        {
            Calls++;
            Collector = collector;
            Args = args;
            return new InvalidOperationException("planted collector fault");
        }
    }

    internal static class CardDrawEvidence
    {
        internal static void PhaseStarted(CardChoice c) { throw Planted.Fault("PhaseStarted", c); }
        internal static void CardAwake(CardInfo c) { throw Planted.Fault("CardAwake", c); }
        internal static void EndPick(int[] ids, int target, int theInt, int pickId) { throw Planted.Fault("EndPick", ids, target, theInt, pickId); }
        internal static void DonePicking() { throw Planted.Fault("DonePicking"); }
        internal static void PickApplied(ApplyCardStats s, int[] actors, bool runOriginal) { throw Planted.Fault("PickApplied", s, actors, runOriginal); }
        internal static void OfflinePickApplied(ApplyCardStats s, Player[] players, bool runOriginal) { throw Planted.Fault("OfflinePickApplied", s, players, runOriginal); }
    }
}
