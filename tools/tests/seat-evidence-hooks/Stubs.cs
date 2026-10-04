// Stubs for the throwing-collector harness. The patch classes under test are
// copied VERBATIM from plugin/HitEvidence.cs, plugin/SeatEvidence.cs and
// plugin/PoisonSync.cs by run_hooks.py; everything they call into is defined
// here. Every collector (HitEvidence, SeatEvidence, PointEvidence) THROWS from
// every member, so a hook passes only when it contains its own faults.
using System;
using System.Collections.Generic;
using System.Reflection;

namespace UnityEngine
{
    public struct Vector2
    {
        public float x, y;
        public static Vector2 zero { get { return default(Vector2); } }
        public static bool operator ==(Vector2 a, Vector2 b) { return a.x == b.x && a.y == b.y; }
        public static bool operator !=(Vector2 a, Vector2 b) { return !(a == b); }
        public override bool Equals(object o) { return o is Vector2 && (Vector2)o == this; }
        public override int GetHashCode() { return 0; }
    }
    public struct Vector3 { public float x, y, z; }
    public class Component { }
}

namespace ExitGames.Client.Photon
{
    public class Hashtable : Dictionary<object, object> { }
}

namespace Photon.Realtime
{
    public class Player { public int ActorNumber; }
}

namespace Photon.Pun
{
    public enum RpcTarget { All, Others, MasterClient, AllBuffered, OthersBuffered, AllViaServer, AllBufferedViaServer }
    public class PhotonView : UnityEngine.Component { public int ViewID; }
    public static class PhotonNetwork
    {
        internal static void ExecuteRpc(ExitGames.Client.Photon.Hashtable rpcData, Photon.Realtime.Player sender) { }
        internal static void RPC(PhotonView view, string methodName, RpcTarget target, Photon.Realtime.Player player, bool encrypt, params object[] parameters) { }
    }
}

namespace HarmonyLib
{
    [AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true)]
    public class HarmonyPatch : Attribute
    {
        public HarmonyPatch() { }
        public HarmonyPatch(Type t, string m) { }
        public HarmonyPatch(Type t, string m, Type[] args) { }
    }
    public class HarmonyPrefix : Attribute { }
    public class HarmonyPostfix : Attribute { }
    public class HarmonyFinalizer : Attribute { }
    public static class AccessTools
    {
        public static MethodInfo Method(Type t, string name, Type[] args = null)
        {
            const BindingFlags all = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;
            return args == null ? t.GetMethod(name, all) : t.GetMethod(name, all, null, args, null);
        }
    }
}

// -- game types (global namespace, as in Assembly-CSharp) ----------------------------
public class HealthHandler : UnityEngine.Component { }
public class Block : UnityEngine.Component { public float sinceBlock; }
public class ProjectileHit : UnityEngine.Component { }
public class ProjectileInit : UnityEngine.Component { }
public class GM_ArmsRace : UnityEngine.Component { }
public class Saw : UnityEngine.Component { }
public class Player : UnityEngine.Component { }
public class BlockTrigger { public enum BlockTriggerType { Default, ShieldCharge, Echo, Empower, None } }

namespace CompetitiveRounds
{
    using ExitGames.Client.Photon;
    using Photon.Pun;
    using UnityEngine;

    internal static class Planted
    {
        internal static int Calls;
        internal static Exception Fault() { Calls++; return new InvalidOperationException("planted collector fault"); }
    }

    internal static class HitEvidence
    {
        internal static int RpcSender;
        internal static void NoteDamage(HealthHandler h, Vector2 d) { throw Planted.Fault(); }
        internal static void NoteForce(HealthHandler h, Vector2 f) { throw Planted.Fault(); }
        internal static void NoteDot(HealthHandler h, Vector2 d, Player p, bool r) { throw Planted.Fault(); }
        internal static void NoteBlock(Block b) { throw Planted.Fault(); }
        internal static void NoteSpawn(Component c, int k) { throw Planted.Fault(); }
        internal static int ProjectileId(ProjectileHit p) { throw Planted.Fault(); }
        internal static void NoteImpact(int a, int b, bool c) { throw Planted.Fault(); }
        internal static void GameEnd(int p) { throw Planted.Fault(); }
    }

    internal static class SeatEvidence
    {
        internal static int EnterRpc(Hashtable d, Photon.Realtime.Player s) { throw Planted.Fault(); }
        internal static void ExitRpc(int depth) { throw Planted.Fault(); }
        internal static bool DamageGate(HealthHandler h, bool nonzero) { throw Planted.Fault(); }
        internal static void DamageArrived(HealthHandler h, bool g, bool completed) { throw Planted.Fault(); }
        internal static int BlockEnter(Block b, bool f, BlockTrigger.BlockTriggerType t, bool o) { throw Planted.Fault(); }
        internal static void BlockExit(int i) { throw Planted.Fault(); }
        internal static void ShotArrived(Component c, int k) { throw Planted.Fault(); }
        internal static int HitEnter(ProjectileHit p, int pid, int v, bool b) { throw Planted.Fault(); }
        internal static void HitExit(int i) { throw Planted.Fault(); }
        internal static void BlockSent(PhotonView v, string m, RpcTarget t) { throw Planted.Fault(); }
        internal static void UnkeyedReset(Block b) { throw Planted.Fault(); }
    }

    // the combat evidence collector the shared RPC send hook also calls (contained beside BlockSent)
    internal static class CombatEvidence
    {
        internal static void RpcSent(PhotonView v, string m, RpcTarget t) { throw Planted.Fault(); }
    }

    internal static class PointEvidence
    {
        internal static int Point { get { throw Planted.Fault(); } }
        internal static void SawBefore() { throw Planted.Fault(); }
        internal static void SawAfter() { throw Planted.Fault(); }
        internal static void PointEnd() { throw Planted.Fault(); }
        internal static void GameOverCheck(GM_ArmsRace gm) { throw Planted.Fault(); }
    }
}
