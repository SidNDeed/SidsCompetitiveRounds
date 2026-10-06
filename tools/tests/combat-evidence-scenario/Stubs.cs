// Working stand-ins for the Unity, Photon, Harmony, ROUNDS and plug-in members
// that plugin/CombatEvidence.cs and CombatEvidencePerf.cs touch, so the REAL
// files can be driven by a scripted 1v1. Each stand-in holds plain state the
// driver sets; the queue side of SeatEvidence only records what it was given;
// the shared RPC frame (SeatEvidence.RpcTop) is whatever the driver pushed.
// Nothing here decides anything.
using System;
using System.Collections.Generic;
using System.Reflection;

namespace UnityEngine
{
    public struct Vector3
    {
        public float x, y, z;
        public Vector3(float x, float y, float z) { this.x = x; this.y = y; this.z = z; }
        public Vector3(float x, float y) { this.x = x; this.y = y; z = 0f; }
        public static Vector3 zero { get { return new Vector3(0f, 0f, 0f); } }
        public static Vector3 up { get { return new Vector3(0f, 1f, 0f); } }
        public float magnitude { get { return (float)Math.Sqrt((double)x * x + (double)y * y + (double)z * z); } }
        public static Vector3 operator +(Vector3 a, Vector3 b) { return new Vector3(a.x + b.x, a.y + b.y, a.z + b.z); }
        public static Vector3 operator -(Vector3 a, Vector3 b) { return new Vector3(a.x - b.x, a.y - b.y, a.z - b.z); }
        public static Vector3 operator *(Vector3 a, float d) { return new Vector3(a.x * d, a.y * d, a.z * d); }
        public static Vector3 operator /(Vector3 a, float d) { return new Vector3(a.x / d, a.y / d, a.z / d); }
        public static bool operator ==(Vector3 a, Vector3 b) { return a.x == b.x && a.y == b.y && a.z == b.z; }
        public static bool operator !=(Vector3 a, Vector3 b) { return !(a == b); }
        public override bool Equals(object o) { return o is Vector3 && (Vector3)o == this; }
        public override int GetHashCode() { return 0; }
        public static implicit operator Vector2(Vector3 v) { return new Vector2(v.x, v.y); }
        public static implicit operator Vector3(Vector2 v) { return new Vector3(v.x, v.y, 0f); }
    }

    public struct Vector2
    {
        public float x, y;
        public Vector2(float x, float y) { this.x = x; this.y = y; }
        public static Vector2 zero { get { return new Vector2(0f, 0f); } }
        public float magnitude { get { return (float)Math.Sqrt((double)x * x + (double)y * y); } }
        public Vector2 normalized { get { float m = magnitude; return m > 0f ? new Vector2(x / m, y / m) : zero; } }
        public static float Distance(Vector2 a, Vector2 b) { return (a - b).magnitude; }
        public static Vector2 operator +(Vector2 a, Vector2 b) { return new Vector2(a.x + b.x, a.y + b.y); }
        public static Vector2 operator -(Vector2 a, Vector2 b) { return new Vector2(a.x - b.x, a.y - b.y); }
        public static Vector2 operator *(Vector2 a, float d) { return new Vector2(a.x * d, a.y * d); }
        public static Vector2 operator /(Vector2 a, float d) { return new Vector2(a.x / d, a.y / d); }
        public static bool operator ==(Vector2 a, Vector2 b) { return a.x == b.x && a.y == b.y; }
        public static bool operator !=(Vector2 a, Vector2 b) { return !(a == b); }
        public override bool Equals(object o) { return o is Vector2 && (Vector2)o == this; }
        public override int GetHashCode() { return 0; }
    }

    public struct Bounds { public Vector3 extents; }

    public static class Mathf
    {
        public static float Clamp(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }
        public static int Clamp(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }
        public static int RoundToInt(float f) { return (int)Math.Round(f, MidpointRounding.ToEven); }
    }

    public static class Time
    {
        public static int frameCount;
        public static float deltaTime = 1f / 60f, unscaledDeltaTime = 1f / 60f;
    }

    public class Object { }

    /// <summary>A game object: a bag of components, with a parent for the
    /// parent and root searches and children for the child search.</summary>
    public class GameObject : Object
    {
        public string name = "";
        public readonly List<Component> Parts = new List<Component>();
        public GameObject Parent;
        public readonly List<GameObject> Children = new List<GameObject>();
        public Transform transform;
        public GameObject(string n) { name = n; transform = Add<Transform>(); }
        public T Add<T>() where T : Component, new()
        {
            var c = new T();
            c.gameObject = this;
            Parts.Add(c);
            return c;
        }
        public T GetComponent<T>() where T : class
        {
            foreach (var p in Parts) { var t = p as T; if (t != null) return t; }
            return null;
        }
        public T GetComponentInChildren<T>() where T : class
        {
            var t = GetComponent<T>();
            if (t != null) return t;
            foreach (var c in Children) { t = c.GetComponentInChildren<T>(); if (t != null) return t; }
            return null;
        }
        public T GetComponentInParent<T>() where T : class
        {
            for (var g = this; g != null; g = g.Parent) { var t = g.GetComponent<T>(); if (t != null) return t; }
            return null;
        }
    }

    public class Component : Object
    {
        public GameObject gameObject;
        public Transform transform { get { return gameObject.transform; } }
        public T GetComponent<T>() where T : class { return gameObject.GetComponent<T>(); }
        public T GetComponentInChildren<T>() where T : class { return gameObject.GetComponentInChildren<T>(); }
        public T GetComponentInParent<T>() where T : class { return gameObject.GetComponentInParent<T>(); }
    }

    public class Transform : Component
    {
        public Vector3 position;
        public Vector3 forward = new Vector3(1f, 0f, 0f);
        public Transform root { get { var g = gameObject; while (g.Parent != null) g = g.Parent; return g.transform; } }
    }

    public class Collider2D : Component { public Bounds bounds; }

    public struct RaycastHit2D { public Transform transform; }

    public static class Physics2D
    {
        /// <summary>The driver's world: the transforms a cast between two points hits (a blocker list).</summary>
        public static readonly List<Transform> Blockers = new List<Transform>();
        public static int Casts;
        public static int RaycastNonAlloc(Vector2 origin, Vector2 direction, RaycastHit2D[] results, float distance, int layerMask)
        {
            Casts++;
            int n = 0;
            foreach (var t in Blockers)
            {
                if (n >= results.Length) break;
                results[n].transform = t; n++;
            }
            return n;
        }
    }
}

namespace Photon.Realtime
{
    public class Player { public int ActorNumber; }
}

namespace ExitGames.Client.Photon
{
    /// <summary>Photon's hashtable: a missing key reads as null.</summary>
    public class Hashtable : Dictionary<object, object>
    {
        public new object this[object key]
        {
            get { object v; return TryGetValue(key, out v) ? v : null; }
            set { base[key] = value; }
        }
    }
}

namespace Photon.Pun
{
    public enum RpcTarget { All, Others, MasterClient, AllBuffered, OthersBuffered, AllViaServer, AllBufferedViaServer }

    public class PhotonView : UnityEngine.Component
    {
        public int ViewID, OwnerActorNr;
        public bool IsMine;
    }

    public class Room { public string Name = ""; }

    public class PhotonStream { public bool IsWriting; }

    public class ProjectileSyncPackage { public UnityEngine.Vector2 vel; public float timeDelta; }

    public class SyncProjectile : UnityEngine.Component
    {
        public bool active = true;
        public List<ProjectileSyncPackage> syncPackages = new List<ProjectileSyncPackage>();
        public PhotonView photonView;
        public void OnPhotonSerializeView(PhotonStream stream, object info) { }
    }

    public static class PhotonNetwork
    {
        public static int ServerTimestamp;
        public static bool InRoom = true;
        public static Room CurrentRoom = new Room();
        public static Photon.Realtime.Player LocalPlayer = new Photon.Realtime.Player();
        public static ExitGames.Client.Photon.Hashtable rpcEvent;
        public static int Ping = 40;
        public static int GetPing() { return Ping; }
        public static readonly Dictionary<int, PhotonView> Views = new Dictionary<int, PhotonView>();
        public static PhotonView GetPhotonView(int id) { PhotonView v; return Views.TryGetValue(id, out v) ? v : null; }
        public static void ExecuteRpc(object rpcData, object sender) { }
        public static void RPC(PhotonView view, string methodName, RpcTarget target, bool encrypt, params object[] parameters) { }
    }
}

namespace BepInEx.Configuration
{
    public class ConfigEntry<T> { public T Value; }
    public class ConfigFile
    {
        public readonly Dictionary<string, object> Values = new Dictionary<string, object>();
        public ConfigEntry<T> Bind<T>(string section, string key, T def, string desc)
        {
            object v;
            return new ConfigEntry<T> { Value = Values.TryGetValue(section + "." + key, out v) ? (T)v : def };
        }
    }
}

namespace HarmonyLib
{
    [AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true)]
    public class HarmonyPatch : Attribute
    {
        public readonly Type Target; public readonly string Method;
        public HarmonyPatch(Type t, string m) { Target = t; Method = m; }
    }
    [AttributeUsage(AttributeTargets.Class | AttributeTargets.Method)]
    public class HarmonyPriority : Attribute { public HarmonyPriority(int v) { } }
    public static class Priority { public const int Last = 0, Normal = 400, First = 800; }
    public class HarmonyPrefix : Attribute { }
    public class HarmonyPostfix : Attribute { }
    public class HarmonyFinalizer : Attribute { }
    public class Patch { public MethodInfo PatchMethod; }
    public class Patches
    {
        public List<Patch> Prefixes = new List<Patch>(), Postfixes = new List<Patch>(), Finalizers = new List<Patch>();
    }
    /// <summary>The patch registry as the boot census reads it: the driver fills it
    /// from the patch classes' own attributes (and can leave classes out).</summary>
    public class Harmony
    {
        public static readonly Dictionary<MethodBase, Patches> Registry = new Dictionary<MethodBase, Patches>();
        public static IEnumerable<MethodBase> GetAllPatchedMethods() { return new List<MethodBase>(Registry.Keys); }
        public static Patches GetPatchInfo(MethodBase m) { Patches p; return Registry.TryGetValue(m, out p) ? p : null; }
    }
}

// -- game types (global namespace, as in Assembly-CSharp) ----------------------------
public class PlayerVelocity : UnityEngine.Component
{
    public UnityEngine.Vector2 velocity;
    public float mass = 100f;
    public UnityEngine.Vector2 position { get { return transform.position; } set { transform.position = value; } }
}
public class GeneralInput : UnityEngine.Component { public UnityEngine.Vector3 aimDirection; }
public class WeaponHandler : UnityEngine.Component { public Gun gun; }
// The patch targets exist by name (the boot census keys on DeclaringType.Name + "." + Name);
// their bodies are empty: the driver runs each original's effect itself, between the patch parts.
public class CharacterStatModifiers : UnityEngine.Component
{
    public bool automaticReload, refreshOnDamage;
    public void DealtDamage(UnityEngine.Vector2 damage, bool selfDamage, Player damagedPlayer = null) { }
}
public class Block : UnityEngine.Component
{
    public float sinceBlock = 100f, counter = 1000f, cooldown = 4f;
    public bool delayOtherActions;
    public float Cooldown() { return cooldown; }
    public void RPCA_DoBlock(bool firstBlock, bool dontSetCD = false, int blockTriggerType = 0, UnityEngine.Vector3 useBlockPos = default(UnityEngine.Vector3), bool onlyBlockEffects = false) { }
    public void TryBlock() { }
}
public class HealthHandler : UnityEngine.Component
{
    public enum DamageSource { Player, OutOfBounds }
    public void RPCA_SendTakeForce(UnityEngine.Vector2 force, int forceMode, bool forceIgnoreMass = false, bool ignoreBlock = false, float setFlying = 0f) { }
    public void RPCA_SendTakeDamage(UnityEngine.Vector2 damage, UnityEngine.Vector2 position, bool lethal = true, int playerID = -1, DamageSource damageSource = DamageSource.Player) { }
    private void RPCA_Die(UnityEngine.Vector2 deathDirection) { }
    private void RPCA_Die_Phoenix(UnityEngine.Vector2 deathDirection) { }
}
public class CharacterData : UnityEngine.Component
{
    public Photon.Pun.PhotonView view;
    public PlayerVelocity playerVel;
    public WeaponHandler weaponHandler;
    public Block block;
    public CharacterStatModifiers stats;
    public GeneralInput input;
    public UnityEngine.Collider2D mainCol;
    public float health = 100f, maxHealth = 100f;
    public bool dead, isPlaying = true;
    public Player player;
}
public class Player : UnityEngine.Component { public CharacterData data; public int PlayerID; }
public class GunAmmo : UnityEngine.Component
{
    public Gun gun;
    public int currentAmmo = 3, maxAmmo = 3;
    public float reloadCounter, freeReloadCounter, reloadTime = 2f, reloadTimeAdd, reloadTimeMultiplier = 1f, ammoReg;
    public float ReloadTime() { return (reloadTime + reloadTimeAdd) * reloadTimeMultiplier; }
    public void ReloadAmmo(bool playSound = true) { }
}
public class ProjectileTemplate { }
public class Gun : UnityEngine.Component
{
    public Player player;
    public GunAmmo gunAmmo;
    public bool isReloading, lockGunToDefault, useCharge;
    public float sinceAttack = 5f, attackSpeedMultiplier = 1f, usedCooldown = 0.3f, attackSpeed = 0.3f, spread = 0.2f,
                 projectileSpeed = 1f, multiplySpread = 1f, chargeSpreadTo, timeBetweenBullets = 0.1f;
    public int numberOfProjectiles = 2, bursts = 1;
    public ProjectileTemplate[] projectiles = new ProjectileTemplate[1];
    public UnityEngine.Transform shootPosition;
    public bool Attack(float charge, bool forceAttack = false, float damageM = 1f, float recoilMultiplier = 1f, bool useAmmo = true) { return true; }
}
public class MoveTransform : UnityEngine.Component
{
    public UnityEngine.Vector3 velocity, localForce;
    public float gravity = 30f, drag, dragMinSpeed = 1f, multiplier = 1f, simulationSpeed = 1f;
    public bool allowStop;
    public int simulateGravity;
}
public class ProjectileInit : UnityEngine.Component
{
    public void RPCA_Init(int senderID, int nrOfProj, float dmgM, float randomSeed) { }
    public void RPCA_Init_noAmmoUse(int senderID, int nrOfProj, float dmgM, float randomSeed) { }
    public void RPCA_Init_SeparateGun(int senderID, int gunID, int nrOfProj, float dmgM, float randomSeed) { }
}
public class ProjectileHit : UnityEngine.Component
{
    public MoveTransform move;
    public void RPCA_DoHit(UnityEngine.Vector2 hitPoint, UnityEngine.Vector2 hitNormal, UnityEngine.Vector2 vel, int viewID = -1, int colliderID = -1, bool wasBlocked = false) { }
    public void Hit(HitInfo hit, bool forceCall = false) { }
}
public class HitInfo
{
    public UnityEngine.Vector2 point, normal;
    public UnityEngine.Collider2D collider;
    public UnityEngine.Transform transform;
}
public class BounceEffectRetarget : UnityEngine.Component
{
    public Photon.Pun.PhotonView view; public MoveTransform move;
    public void SetNewVel(UnityEngine.Vector2 newVel) { }
    private Player FindTarget(HitInfo hit) { return null; }
}
public class ScreenEdgeBounce : UnityEngine.Component { public ProjectileHit projHit; public void DoHit() { } }
public class SpawnedAttack : UnityEngine.Component { }
public class Homing : UnityEngine.Component { public float amount; }
public class RemoteControl : UnityEngine.Component { }
public class DodgeGround : UnityEngine.Component { }
public class TracerTarget : UnityEngine.Component { }
public class Zop : UnityEngine.Component { }
public class BulletPoint : UnityEngine.Component { }
public class Cos : UnityEngine.Component { }
public class MoveTransformGravity : UnityEngine.Component { }
public class RayHitDrill : UnityEngine.Component { }
public class Accelerate : UnityEngine.Component { }
public class CanSeeInfo { public bool canSee; }
public class TimeHandler
{
    public static TimeHandler instance = new TimeHandler();
    public static float timeScale = 1f, deltaTime = 1f / 60f;
    public float baseTimeScale = 1f;
}
public class PlayerManager
{
    public static PlayerManager instance = new PlayerManager();
    public List<Player> players = new List<Player>();
    public int canSeePlayerMask = 1;
    public Player GetPlayerWithActorID(int a)
    {
        foreach (var p in players) if (p.data != null && p.data.view != null && p.data.view.OwnerActorNr == a) return p;
        return null;
    }
    public Player GetClosestPlayer(UnityEngine.Vector2 refPos, bool needVision = false)
    {
        Player best = null; float bd = float.MaxValue;
        foreach (var p in players)
        {
            if (p.data == null || p.data.dead) continue;
            float d = UnityEngine.Vector2.Distance(refPos, p.data.playerVel.position);
            if (d < bd) { bd = d; best = p; }
        }
        return best;
    }
    /// <summary>The allocating sight check the round-1 client used (kept for the red run).</summary>
    public CanSeeInfo CanSeePlayer(UnityEngine.Vector2 from, Player player)
    {
        return new CanSeeInfo { canSee = UnityEngine.Physics2D.Blockers.Count == 0 };
    }
}

namespace CompetitiveRounds
{
    public class LogSink
    {
        public readonly List<string> Lines = new List<string>();
        public void LogInfo(object o) { Lines.Add("I " + o); }
        public void LogWarning(object o) { Lines.Add("W " + o); }
        public void LogError(object o) { Lines.Add("E " + o); }
    }

    internal static class Plugin
    {
        internal static LogSink Log = new LogSink();
        internal static BepInEx.Configuration.ConfigFile ConfigFileForLevers = new BepInEx.Configuration.ConfigFile();
    }

    internal static class RoomActors
    {
        internal static Photon.Realtime.Player[] Others = new Photon.Realtime.Player[0];
        internal static Photon.Realtime.Player[] OtherActiveFighters() { return Others; }
    }

    internal static class PointEvidence { internal static int Point; }

    internal static class GameStateWatcher
    {
        internal static int T0 = 1000;
        internal static int SeatEvidenceT0(out bool fromToken) { fromToken = true; return T0; }
    }

    internal static class ApiClient
    {
        internal static string SeatEvidenceSig(string canonical)
        {
            return SeatEvidenceCore.Hmac(System.Text.Encoding.UTF8.GetBytes("scenario-key-not-a-secret"), canonical);
        }
    }

    /// <summary>The seat evidence side the combat file reads: the combat state,
    /// the shared RPC frame (a stack the driver pushes and pops), the stopwatch
    /// (the driver's clock) and a queue recorder.</summary>
    internal static class SeatEvidence
    {
        internal const long FROZEN_MS = 120000;
        internal static bool Combat;
        internal static bool CombatLive() { return Combat; }
        internal static long Sw;
        internal static long SwMs { get { return Sw; } }
        internal static bool IdentityReady = true;
        internal static void CompleteIdentityNow() { IdentityReady = true; }
        internal static void StartHashing() { }
        internal static readonly List<string> Queued = new List<string>();
        internal static readonly List<string> Spooled = new List<string>();
        internal static bool EnqueueCombat(string body) { Queued.Add(body); return true; }
        internal static bool SpoolClosing(string route, string body) { Spooled.Add(body); return true; }
        internal static string StableOf(string attach)
        {
            if (attach == null) return null;
            int i = attach.LastIndexOf("_r", StringComparison.Ordinal);
            if (i <= 0) return null;
            string stable = attach.Substring(0, i);
            return SeatEvidenceCore.IsAttachKey(stable, attach) ? stable : null;
        }

        internal struct Frame { public int Stamp, Sender, View; public string Method; }
        internal static readonly List<Frame> Frames = new List<Frame>();
        internal static bool RpcTop(out int stamp, out int sender, out int viewId, out string method)
        {
            if (Frames.Count == 0) { stamp = 0; sender = 0; viewId = 0; method = null; return false; }
            var f = Frames[Frames.Count - 1];
            stamp = f.Stamp; sender = f.Sender; viewId = f.View; method = f.Method;
            return true;
        }
    }

    /// <summary>The M1 plant: the throwing build's entries throw when Row names their cost row.</summary>
    internal static class ScenarioPlant { internal static int Row = -1; }

    // the shared RPC frame's own patches (other evidence files in the plug-in); the census reads their names
    internal static class HitEvidence_ExecuteRpcPatch { internal static void Prefix() { } }
    internal static class SeatEvidence_RpcSendPatch { internal static void Postfix() { } }
}
