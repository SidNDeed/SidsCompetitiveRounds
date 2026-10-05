// Working stand-ins for the Unity, Photon, ROUNDS and plug-in members that
// plugin/SeatEvidence.cs touches, so the REAL file (compiled as it ships, with
// plugin/SeatEvidenceCore.cs) can be driven by scripted replays. Each stand-in
// holds plain state the replay sets: the server clock, the views, the block
// timers, the RPC envelope PUN last wrote, the session token. Nothing here
// decides anything; it only answers what the collector asks.
using System;
using System.Collections.Generic;
using System.Reflection;

namespace UnityEngine
{
    public class Component
    {
        private readonly List<object> _parts = new List<object>();
        public Component() { _parts.Add(this); }
        public void Attach(object c) { _parts.Add(c); }
        public T GetComponent<T>() where T : class
        {
            foreach (var p in _parts) { var t = p as T; if (t != null) return t; }
            return null;
        }
    }
    public static class Time { public static float unscaledTime; }
}

namespace ExitGames.Client.Photon
{
    public class Hashtable : Dictionary<object, object>
    {
        public new object this[object key]
        {
            get { object v; return TryGetValue(key, out v) ? v : null; }
            set { base[key] = value; }
        }
    }
    public class PeerBase { internal int serverTimeOffset; }
    public class PhotonPeer { internal PeerBase peerBase = new PeerBase(); }
}

namespace Photon.Realtime
{
    public class Player
    {
        public int ActorNumber;
        public ExitGames.Client.Photon.Hashtable CustomProperties = new ExitGames.Client.Photon.Hashtable();
    }
    public class Room
    {
        public string Name = "";
        public Dictionary<int, Player> Players = new Dictionary<int, Player>();
        public Player GetPlayer(int actor) { Player p; return Players.TryGetValue(actor, out p) ? p : null; }
    }
    public class LoadBalancingPeer : ExitGames.Client.Photon.PhotonPeer { }
    public class LoadBalancingClient { public LoadBalancingPeer LoadBalancingPeer = new LoadBalancingPeer(); }
}

namespace Photon.Pun
{
    public enum RpcTarget { All, Others, MasterClient, AllBuffered, OthersBuffered, AllViaServer, AllBufferedViaServer }

    public class PhotonView : UnityEngine.Component
    {
        public int ViewID;
        public bool IsMine;
        public int OwnerActorNr;
    }

    public class ServerSettings { public List<string> RpcList = new List<string>(); }

    public static class PhotonNetwork
    {
        public static int ServerTimestamp;
        public static bool IsMasterClient;
        public static Photon.Realtime.Player LocalPlayer;
        public static Photon.Realtime.Room CurrentRoom;
        public static ServerSettings PhotonServerSettings = new ServerSettings();
        public static Photon.Realtime.LoadBalancingClient NetworkingClient = new Photon.Realtime.LoadBalancingClient();
        public static ExitGames.Client.Photon.Hashtable rpcEvent = new ExitGames.Client.Photon.Hashtable();
        public static int Ping = 40;
        public static readonly Dictionary<int, PhotonView> Views = new Dictionary<int, PhotonView>();
        public static PhotonView GetPhotonView(int id) { PhotonView v; return Views.TryGetValue(id, out v) ? v : null; }
        public static int GetPing() { return Ping; }
    }
}

namespace Steamworks
{
    public struct CSteamID { public ulong m_SteamID; }
    public static class SteamUser
    {
        public static ulong Id = 76561190000000001UL;
        public static CSteamID GetSteamID() { return new CSteamID { m_SteamID = Id }; }
    }
}

namespace BepInEx
{
    public static class Paths
    {
        public static string ConfigPath = "";
        public static string PluginPath = "";
        public static string PatcherPluginPath = "";
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
    public class Patches { public IEnumerable<string> Owners = new string[0]; }
    public class Harmony
    {
        public static Patches GetPatchInfo(MethodBase m) { return null; }
    }
    public static class AccessTools
    {
        private const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;
        public static MethodInfo Method(Type t, string name, Type[] args = null)
        {
            return args == null ? t.GetMethod(name, All) : t.GetMethod(name, All, null, args, null);
        }
        public static FieldInfo Field(Type t, string name) { return t.GetField(name, All); }
    }
}

// -- game types (global namespace, as in Assembly-CSharp) ----------------------------
public class PlayerVelocity { public bool simulated = true; }
public class Gun
{
    public int bursts = 1, numberOfProjectiles = 1;
    public float timeBetweenBullets = 0f, attackSpeedMultiplier = 1f, usedCooldown = 0.3f;
    public bool useCharge;
}
public class WeaponHandler { public Gun gun = new Gun(); }
public class Block : UnityEngine.Component { public float sinceBlock = 5f; }
public class CharacterData : UnityEngine.Component
{
    public Photon.Pun.PhotonView view;
    public Block block;
    public bool isPlaying = true, dead;
    public PlayerVelocity playerVel = new PlayerVelocity();
    public WeaponHandler weaponHandler = new WeaponHandler();
}
public class HealthHandler : UnityEngine.Component { }
public class ProjectileHit : UnityEngine.Component { }
public class GM_ArmsRace { }
public class Player { public CharacterData data; }
public class PlayerManager
{
    public static PlayerManager instance = new PlayerManager();
    public readonly Dictionary<int, Player> ByActor = new Dictionary<int, Player>();
    public Player GetPlayerWithActorID(int a) { Player p; return ByActor.TryGetValue(a, out p) ? p : null; }
}
public static class TimeHandler { public static float deltaTime; }
public class GameManager { public static GameManager instance = new GameManager(); public bool battleOngoing; }
public class BlockTrigger { public enum BlockTriggerType { Default, ShieldCharge, Echo, Empower, None } }

namespace CompetitiveRounds
{
    public class LogSink
    {
        public readonly List<string> Lines = new List<string>();
        public void LogInfo(object o) { Lines.Add("I " + o); }
        public void LogWarning(object o) { Lines.Add("W " + o); }
    }

    public class ConfigValue<T> { public T Value; }

    internal static class Plugin
    {
        internal const string ModId = "com.scr.competitiverounds";
        internal static LogSink Log = new LogSink();
        internal static bool modDisabled;
        internal static bool Consent = true;
        internal static bool DataConsentGranted { get { return Consent; } }
        internal static ConfigValue<string> ApiBaseUrl = new ConfigValue<string> { Value = "https://replay.invalid:8444" };
    }

    // The identity-clock lane's clock reader, which SeatEvidence's pump hands
    // the evidence POST for route "i" only (no replay case queues route "i").
    internal static class IdentityClockEvidence
    {
        internal static string ClockHeaderNow() { return null; }
    }

    internal static class SteamAuth
    {
        internal static string SessionToken;
        internal static string FallbackIdentity;
        internal static int Refreshes;
        internal static int GrantAfter = -1;   // the Refreshes count at which a session lands; -1 never
        internal static void MaybeRefresh()
        {
            Refreshes++;
            if (GrantAfter >= 0 && Refreshes >= GrantAfter) SessionToken = "session-for-the-replay";
        }
    }

    internal static class ApiClient
    {
        internal static string Base = "";
        internal static readonly List<KeyValuePair<string, string>> Posts = new List<KeyValuePair<string, string>>();
        internal static string Answer = "{\"status\":\"recorded\"}";
        internal static bool AnswerOk = true;
        internal static string SeatEvidenceSig(string canonical)
        {
            return CompetitiveRounds.SeatEvidenceCore.Hmac(System.Text.Encoding.UTF8.GetBytes("replay-key-not-a-secret"), canonical);
        }
        internal static bool SeatEvidenceReady
        {
            get { return !string.IsNullOrEmpty(Base) && !string.IsNullOrEmpty(SteamAuth.SessionToken); }
        }
        // The evidence POST as ApiClient.SeatEvidencePost shapes it: false
        // without a base or consent; a gate inside the api (RefuseInside)
        // answers "not sent" without asking beforeSend; beforeSend false is
        // "not sent" too; only then do the bytes "leave" (OnSend runs at that
        // instant, so a case can read the queue file as it stood).
        internal static bool RefuseInside;
        internal static int NotSent;
        internal static Action OnSend;
        internal static bool SeatEvidencePost(string path, string body, Func<bool> beforeSend, Func<string> clockHeader, Action<bool, bool, string, bool> callback)
        {
            if (string.IsNullOrEmpty(Base) || !Plugin.DataConsentGranted) return false;
            if (RefuseInside) { NotSent++; callback(false, false, "insecure-transport", false); return true; }
            if (beforeSend != null && !beforeSend()) { NotSent++; callback(false, false, "not-sent", false); return true; }
            if (OnSend != null) OnSend();
            Posts.Add(new KeyValuePair<string, string>(path, body));
            callback(true, AnswerOk, Answer, true);
            return true;
        }
        internal static void SeatEvidenceCompatBase(string url)
        {
            if (!string.IsNullOrEmpty(Base) || string.IsNullOrEmpty(url)) return;
            Base = url;
        }
    }

    internal static class GameStateWatcher
    {
        internal static int T0;
        internal static bool T0FromToken;
        internal static int SeatEvidenceT0(out bool fromToken) { fromToken = T0FromToken; return T0; }
    }

    internal static class NetworkReplicaDiagnostics
    {
        internal static bool BattleActive;
        internal struct ObsSnapshot
        {
            public long Gap300, Gap750, Gap1500, MaxGapMs, Excess150, MaxExcessMs, PayloadEqualGaps, ReceiverFrameGaps, PhoenixIntervals, Batches;
        }
        internal static bool TryGetOpponentGameObs(out ObsSnapshot o) { o = default(ObsSnapshot); return false; }
    }

    internal static class PeerBuild { internal static string BuildValue() { return "1.41.0|standalone|0123456789ab"; } }
    internal static class PeerBuildCore { internal const string BuildProp = "cr_build"; }

    internal static class RoomActors
    {
        internal static Photon.Realtime.Player[] Others = new Photon.Realtime.Player[0];
        internal static Photon.Realtime.Player[] OtherActiveFighters() { return Others; }
    }
}
