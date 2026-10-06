// Stubs for the combat evidence hook harness. The eighteen patch classes under
// test are copied VERBATIM from plugin/CombatEvidence.cs by run_hooks.py;
// everything they call into is defined here. Every collector THROWS after
// recording the arguments it was given, so a hook passes only when it contains
// its own fault and forwards its own arguments.
using System;
using System.Collections.Generic;

namespace UnityEngine
{
    public struct Vector2
    {
        public float x, y;
        public Vector2(float x, float y) { this.x = x; this.y = y; }
        public override bool Equals(object o) { return o is Vector2 && ((Vector2)o).x == x && ((Vector2)o).y == y; }
        public override int GetHashCode() { return 0; }
    }
}

namespace Photon.Pun
{
    public class PhotonStream { }
    public class SyncProjectile { }
}

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
    public static class Priority { public const int Last = 0, VeryLow = 100, Low = 200, LowerThanNormal = 300, Normal = 400, First = 800; }
    public class HarmonyPrefix : Attribute { }
    public class HarmonyPostfix : Attribute { }
    public class HarmonyFinalizer : Attribute { }
}

// -- game types (global namespace, as in Assembly-CSharp) ----------------------------
public class Gun { }
public class GunAmmo { }
public class ProjectileInit { }
public class ProjectileHit { }
public class HitInfo { }
public class Block { }
public class CharacterStatModifiers { }
public class BounceEffectRetarget { }
public class ScreenEdgeBounce { }
public class Player { }
public class HealthHandler
{
    public enum DamageSource { Player, OutOfBounds }
}

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

    // out parameters are never recorded (a throwing collector never assigns them)
    internal static class CombatEvidence
    {
        internal static void AttackEnter(Gun g, bool forceAttack, bool useAmmo, out long state) { throw Planted.Fault("AttackEnter", g, forceAttack, useAmmo); }
        internal static void AttackExit(Gun g, bool result, bool forceAttack, long state) { throw Planted.Fault("AttackExit", g, result, forceAttack, state); }
        internal static int InitEnter(ProjectileInit i, int senderID, int kind) { throw Planted.Fault("InitEnter", i, senderID, kind); }
        internal static void InitExit(ProjectileInit i, int state) { throw Planted.Fault("InitExit", i, state); }
        internal static void ReloadEnter(GunAmmo a, bool playSound) { throw Planted.Fault("ReloadEnter", a, playSound); }
        internal static void HitEnter(ProjectileHit p, UnityEngine.Vector2 point, UnityEngine.Vector2 vel, int viewID, bool wasBlocked, out long state) { throw Planted.Fault("HitEnter", p, point, vel, viewID, wasBlocked); }
        internal static void HitExit(ProjectileHit p, long state) { throw Planted.Fault("HitExit", p, state); }
        internal static void ContactEnter(ProjectileHit p, HitInfo hit) { throw Planted.Fault("ContactEnter", p, hit); }
        internal static void BlockDone(Block b) { throw Planted.Fault("BlockDone", b); }
        internal static void TryBlockEnter(Block b, out long state) { throw Planted.Fault("TryBlockEnter", b); }
        internal static void TryBlockExit(Block b, long state) { throw Planted.Fault("TryBlockExit", b, state); }
        internal static void Dealt(CharacterStatModifiers s) { throw Planted.Fault("Dealt", s); }
        internal static void TargetBounce(BounceEffectRetarget r, UnityEngine.Vector2 newVel) { throw Planted.Fault("TargetBounce", r, newVel); }
        internal static void FindTarget(BounceEffectRetarget r, HitInfo hit, Player result) { throw Planted.Fault("FindTarget", r, hit, result); }
        internal static void EdgeBounce(ScreenEdgeBounce b, out long state) { throw Planted.Fault("EdgeBounce", b); }
        internal static void EdgeBounceExit(ScreenEdgeBounce b, long state) { throw Planted.Fault("EdgeBounceExit", b, state); }
        internal static void SyncRead(Photon.Pun.SyncProjectile sp, Photon.Pun.PhotonStream stream) { throw Planted.Fault("SyncRead", sp, stream); }
        internal static void ForceEnter(HealthHandler h, UnityEngine.Vector2 force, out long state) { throw Planted.Fault("ForceEnter", h, force); }
        internal static void ForceExit(HealthHandler h, long state) { throw Planted.Fault("ForceExit", h, state); }
        internal static void DamageEnter(HealthHandler h, UnityEngine.Vector2 damage, bool outOfBounds, out long state) { throw Planted.Fault("DamageEnter", h, damage, outOfBounds); }
        internal static void DamageExit(HealthHandler h, long state) { throw Planted.Fault("DamageExit", h, state); }
        internal static void Die(HealthHandler h) { throw Planted.Fault("Die", h); }
    }
}
