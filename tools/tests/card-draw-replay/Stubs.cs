// Working stand-ins for the Unity, Photon, ROUNDS and plug-in members that
// plugin/CardDrawEvidence.cs touches, so the REAL file (with the REAL cores)
// can be driven by scripted replays. Each stand-in holds plain state the
// replay sets; the queue side of SeatEvidence only records what it was given.
// Nothing here decides anything.
using System;
using System.Collections.Generic;
using System.Reflection;

namespace UnityEngine
{
    public class GameObject { public string name = ""; }
    public class Transform { public int childCount; }
    public class Object { }
    public class Component : Object
    {
        private readonly List<object> _parts = new List<object>();
        public GameObject gameObject = new GameObject();
        public Transform transform = new Transform();
        public Component() { _parts.Add(this); }
        public void Attach(object c) { _parts.Add(c); }
        public T GetComponent<T>() where T : class
        {
            foreach (var p in _parts) { var t = p as T; if (t != null) return t; }
            return null;
        }
    }
    public class ScriptableObject : Object
    {
        private static int _next = 1;
        private readonly int _id = _next++;
        public string name = "";
        public int GetInstanceID() { return _id; }
    }
}

namespace Photon.Pun
{
    public class PhotonView : UnityEngine.Component
    {
        public int ViewID, CreatorActorNr, ControllerActorNr;
        public bool IsMine;
    }

    public class Room
    {
        public string Name = "";
        public Dictionary<object, object> CustomProperties = new Dictionary<object, object>();
    }

    public static class PhotonNetwork
    {
        public static bool InRoom = true, OfflineMode;
        public static Room CurrentRoom = new Room();
        public static readonly Dictionary<int, PhotonView> Views = new Dictionary<int, PhotonView>();
        public static PhotonView GetPhotonView(int id) { PhotonView v; return Views.TryGetValue(id, out v) ? v : null; }
    }
}

namespace BepInEx
{
    public static class Paths { public static string ConfigPath = ""; }
}

namespace BepInEx.Configuration
{
    public class ConfigEntry<T> { public T Value; }
    public class ConfigFile
    {
        public ConfigEntry<T> Bind<T>(string section, string key, T def, string desc) { return new ConfigEntry<T> { Value = def }; }
    }
}

namespace HarmonyLib
{
    [AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true)]
    public class HarmonyPatch : Attribute { public HarmonyPatch(Type t, string m) { } }
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
    public class Harmony { public static Patches GetPatchInfo(MethodBase m) { return null; } }
    public static class AccessTools
    {
        private const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;
        public static MethodInfo Method(Type t, string name) { return t.GetMethod(name, All); }
        public static FieldInfo Field(Type t, string name) { return t.GetField(name, All); }
    }
}

// -- game types (global namespace, as in Assembly-CSharp) ----------------------------
public class CardCategory : UnityEngine.ScriptableObject { }
public class Gun : UnityEngine.Component { public bool lockGunToDefault; }
public class Holding : UnityEngine.Component { public UnityEngine.Component holdable; }
public class CardInfo : UnityEngine.Component
{
    public enum Rarity { Common, Uncommon, Rare }
    public CardInfo sourceCard;
    public Rarity rarity;
    public bool allowMultiple = true;
    public CardCategory[] categories = new CardCategory[0];
    public CardCategory[] blacklistedCategories = new CardCategory[0];
}
public class ApplyCardStats : UnityEngine.Component { }
public class CharacterData : UnityEngine.Component
{
    public Photon.Pun.PhotonView view;
    public List<CardInfo> currentCards = new List<CardInfo>();
}
public class Player
{
    public CharacterData data;
    public int TeamID, PlayerID;
}
public class PlayerManager
{
    public static PlayerManager instance = new PlayerManager();
    public static bool ThrowOnId;     // a fault planted in the first read of C1
    public List<Player> players = new List<Player>();
    public Player GetPlayerWithID(int id)
    {
        if (ThrowOnId) throw new InvalidOperationException("planted read fault");
        foreach (var p in players) if (p.PlayerID == id) return p;
        return null;
    }
    public Player GetPlayerWithActorID(int a)
    {
        foreach (var p in players) if (p.data != null && p.data.view != null && p.data.view.ControllerActorNr == a) return p;
        return null;
    }
}
public class GM_ArmsRace { public static GM_ArmsRace instance = new GM_ArmsRace(); public int p1Rounds, p2Rounds; }
public class GameManager { public static GameManager instance = new GameManager(); public bool battleOngoing; }
public class CardChoice : UnityEngine.Component
{
    public static CardChoice instance;
    public int pickrID, picks = 1;
    public CardInfo[] cards = new CardInfo[0];
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
        internal static BepInEx.Configuration.ConfigFile ConfigFileForLevers;
    }

    internal static class RoomActors
    {
        internal static bool LocalIsSpectator;
        internal static int Fighters = 2;
        internal static int ActiveFighterCount() { return Fighters; }
    }

    internal static class FfaMode { internal static bool EngineActive() { return false; } }

    internal static class VanillaCardSequence
    {
        internal static int GameValue = 1;
        internal static bool ThrowOnGame;   // a fault before the game is known
        internal static int Game { get { if (ThrowOnGame) throw new InvalidOperationException("planted game fault"); return GameValue; } }
        internal static int SharedSlotsServed;
        internal const int OpeningDraws = 1;
    }

    internal static class FfaCardSequence
    {
        internal static bool ActiveThisGame;
        internal static int DrawIndexOf(int playerId) { return -1; }
    }

    internal static class RoomRules
    {
        internal static bool SameCards;
        internal static string LatchedProp = "ff=1;sc=0";
    }

    internal static class HitEvidence { internal static int RpcSender; }

    internal static class CardRarityLookup { internal static string GetCanonicalName(string n) { return n; } }

    internal static class PeerBuild { internal static string BuildValue() { return "1.41.0|STANDALONE|abc1234"; } }

    internal static class ApiClient
    {
        internal static string SeatEvidenceSig(string canonical)
        {
            return SeatEvidenceCore.Hmac(System.Text.Encoding.UTF8.GetBytes("replay-key-not-a-secret"), canonical);
        }
    }

    /// <summary>The queue side of SeatEvidence as a recorder: which path each
    /// card envelope took (the queue on the tick, a closing file on the
    /// quitting path), and the combat and identity state the replay sets.</summary>
    internal static class SeatEvidence
    {
        internal const string ID_PENDING = "pending";
        internal static bool Combat;
        internal static string NotedEndValue;
        internal static string NotedEnd { get { return NotedEndValue; } }
        internal static bool CombatLive() { return Combat; }
        internal static bool IdentityReady = true;
        internal static void CompleteIdentityNow() { IdentityReady = true; }
        internal static void StartHashing() { }
        internal static string GameDllSha = new string('c', 64), GameDllState = "ok";
        internal static string OwnDllSha = new string('d', 64), OwnDllState = "ok";
        internal static readonly List<string> Queued = new List<string>();
        internal static readonly List<string> Spooled = new List<string>();
        internal static bool QueueRefuses;
        internal static bool EnqueueCard(string body) { if (QueueRefuses) return false; Queued.Add(body); return true; }
        internal static bool SpoolClosing(string route, string body) { if (route != "k") return false; Spooled.Add(body); return true; }
        internal static string StableOf(string attach)
        {
            if (attach == null) return null;
            int i = attach.LastIndexOf("_r", StringComparison.Ordinal);
            if (i <= 0) return null;
            string stable = attach.Substring(0, i);
            return SeatEvidenceCore.IsAttachKey(stable, attach) ? stable : null;
        }
    }
}
