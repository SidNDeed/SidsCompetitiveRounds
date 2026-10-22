// RJ readmission P1 (T1.1, T1.2): working stand-ins for the Unity, Photon and
// plug-in members the REAL ApplyManifestPick touches. Every member the reducer
// can observe or write is recorded by Trace, with a snapshot of the state the
// reducer owns, so two reducers are compared element by element (V3 P1).
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace CompetitiveRounds
{
    internal struct Color
    {
        internal float r, g, b;
        internal Color(float r, float g, float b) { this.r = r; this.g = g; this.b = b; }
    }

    internal class GameObject { public string name; public GameObject(string n) { name = n; } }

    internal sealed class OwnerStub { public string NickName; }

    internal sealed class PhotonView { public bool IsMine; public OwnerStub Owner; public int OwnerActorNr; }

    internal sealed class ObjectsToSpawn { public GameObject effect; public GameObject AddToProjectile; }

    internal sealed class Gun
    {
        public ObjectsToSpawn[] objectsToSpawn = new ObjectsToSpawn[0];
        public float slow;
        public int numberOfProjectiles = 1;
    }

    internal sealed class Holdable { public Gun gun; public T GetComponent<T>() where T : class { return gun as T; } }

    internal sealed class Holding { public Holdable holdable; }

    internal sealed class WeaponHandler
    {
        private readonly Gun _gun = new Gun();
        public Gun gun
        {
            get
            {
                if (Trace.Inject == "audit") throw new InvalidOperationException("injected audit");
                return _gun;
            }
        }
    }

    internal sealed class CharacterData
    {
        public PhotonView view;
        public WeaponHandler weaponHandler = new WeaponHandler();
        public Holding holding = new Holding();
        public T GetComponent<T>() where T : class { return holding as T; }
    }

    internal sealed class Player
    {
        public int PlayerID;
        public int TeamID;
        public GameObject gameObject;
        public CharacterData data;
    }

    internal sealed class CardInfo
    {
        public enum Rarity { Common, Uncommon, Rare }
        public GameObject gameObject;
        public Rarity rarity;
        public CardInfo(string name) { gameObject = new GameObject(name); }
    }

    internal sealed class CardChoice
    {
        public static CardChoice instance;
        public CardInfo[] cards;
    }

    internal sealed class LogStub
    {
        public void LogInfo(object m) { Trace.Event("info " + m); }
        public void LogWarning(object m) { Trace.Event("warn " + m); }
    }

    internal static class Plugin { internal static readonly LogStub Log = new LogStub(); }

    internal static class I18n
    {
        public static string TrF(string template, params object[] args) { return string.Format(template, args); }
    }

    internal static class CompetitiveUI
    {
        internal static void ShowNotification(string message, Color color, float seconds) { }
        public struct NotifSetItem
        {
            public string text;
            public Color color;
            public NotifSetItem(string text, Color color) { this.text = text; this.color = color; }
        }
    }

    internal static class MatchTracker
    {
        public class CardPickData
        {
            public string CardName;
            public string CardRarity;
            public int PickOrder;
            public int RoundNumber;
            public bool Rolled;
        }
    }

    internal static class CardRarityLookup
    {
        internal static string GetCanonicalName(string raw) { return raw == null ? null : raw.ToUpperInvariant(); }
    }

    internal static class CardTextLocalizer
    {
        internal static string PrettyNameIfCached(string canon, string raw) { return canon; }
    }

    internal static class GameStateWatcher
    {
        internal static string StripRichText(string s) { return s; }
        // The cr_cards publication rides this call (the local-pick bookkeeping).
        internal static void RecordFfaLocalPick(string card, int round) { Trace.Event("cr_cards " + card + " r" + round); }
    }

    internal static class FfaLateEntry
    {
        internal static int OwnerOf(Player p) { return p?.data?.view?.OwnerActorNr ?? -1; }
        internal static readonly HashSet<int> Quarantined = new HashSet<int>();
        internal static bool IsQuarantined(Player p) { return p != null && Quarantined.Contains(p.PlayerID); }
        internal static void Refused(string site, Player p) { Trace.Event("refused " + site + " " + (p == null ? -1 : p.PlayerID)); }
        internal static void MarkDigestDirty() { Trace.Event("digest_dirty"); }
    }

    internal static class PhotonNetwork
    {
        internal static object CurrentRoom = new object();
    }

    internal static class FfaAssembly
    {
        internal static bool ReadmitLobby = true;
        internal static object Granted = new object();
        internal static object CurrentGate() { return new object(); }
        internal static string RoomLobbyId = "lobbyA";
        internal static string RoomName = "roomA";
        internal static string CurrentRoomName() { return RoomName; }
        internal static int LateEntered;
        internal static void ClearOwedToast() { }
        internal static void ReceiptThen(string lobby, string phase, string payload, Action<bool> done)
        {
            LateEntered++;
            done(true);
        }
    }

    internal static class FfaMode { internal static int GameNumber = 1; }
    internal static class FfaReadmit
    {
        internal static bool Readmitted = true;
        internal static int Entered;
        internal static bool ReadmittedInto(string lobby) { return Readmitted; }
        internal static void LadderEntered() { }
        internal static void PostEntered(int game) { Entered++; }
    }
    internal static class JoinTimeline
    {
        internal static void Step(string name, string detail) { }
        internal static void Disarm(string name) { }
    }
    internal sealed class RaiseEventOptions { internal int[] TargetActors; }
    internal sealed class EventData { internal int Sender; internal object CustomData; }
    internal static class FfaLateRules
    {
        internal sealed class Proposal { internal string Lobby8, Chain; internal int G, K, N, From; }
        internal static bool AllAcks = true, KeptThrows;
        internal static string Refusal;
        internal static bool KeptActorValue(object gate, bool holdsGrant, int actor, object grants, object record, int epoch)
        {
            if (KeptThrows) throw new InvalidOperationException("kept");
            return true;
        }
        internal static string ValidateEpoch(Proposal p, int master, bool kept, string lobby, object record,
            int applied, string chain, int game, int point, bool known, List<int> present) { return Refusal; }
        internal static bool AckComplete(List<int> barrier, List<int> present, List<Proposal> acks,
            Proposal proposal, int self, out List<int> missing)
        {
            missing = new List<int>();
            return AllAcks;
        }
    }
    internal class ReadmitAdmissionBase
    {
        internal sealed class LastHold { internal int G, K; internal bool Done; }
        internal static LastHold _lastHold;
        internal static FfaLateRules.Proposal _replayProposal;
        internal static Func<bool> _replayAck;
        internal static bool HoldsGrant = true, LateArmed, _lateEntered, Lagged, ActorKept = true;
        internal static int _snapK = -1, PointK, PointEpoch = 1, EpochApplied, _pendingSelfKeptGame;
        internal static string Lobby8 = "lobbyA", AppliedChain = "0", AdmittedLateLobby = "lobbyA";
        internal static object Record = new object();
        internal static readonly Dictionary<long, bool> _ackSent = new Dictionary<long, bool>();
        internal static readonly List<FfaLateRules.Proposal> _acks = new List<FfaLateRules.Proposal>();
        internal const byte EVT_EPOCH_ACK = 56;
        internal static Func<bool> Prepared;
        internal static int AckCount;
        internal static bool LagOutNow() { return Lagged; }
        internal static int MasterActor() { return 3; }
        internal static bool MasterKept() { return true; }
        internal static List<int> PresentActors() { return new List<int> { 3, 7 }; }
        internal static int OwnActor() { return 7; }
        internal static bool Kept(int actor) { return ActorKept; }
        internal static bool ReadmitActorPrepared(int actor, int epoch) { return Prepared(); }
        internal static bool PrepareReadmitEpochCore(int epoch) { return Prepared(); }
        internal static long Key(int game, int point) { return ((long)game << 32) | (uint)point; }
        internal static string I(int value) { return value.ToString(); }
        internal static string S(object[] data, int at) { return data[at] as string; }
        internal static int N(object[] data, int at, int fallback) { return data[at] is int value ? value : fallback; }
        internal static EventData ProposalEvent()
        {
            return new EventData { Sender = 3, CustomData = new object[] { "lobbyA", 1, "c1", 1, 0 } };
        }
        internal static bool Raise(byte kind, object[] data, RaiseEventOptions options)
        {
            AckCount++;
            return true;
        }
        internal static void ResetAdmission(Func<bool> prepared)
        {
            _lastHold = null;
            _replayAck = null;
            _replayProposal = new FfaLateRules.Proposal { Lobby8 = "lobbyA", Chain = "c1", N = 1, G = 1, K = 0, From = 3 };
            HoldsGrant = true; LateArmed = false; _lateEntered = false; Lagged = false; ActorKept = true;
            _snapK = -1; PointK = 0; PointEpoch = 1; EpochApplied = 0; _pendingSelfKeptGame = 1;
            Prepared = prepared; AckCount = 0; _ackSent.Clear(); _acks.Clear();
            FfaLateRules.AllAcks = true; FfaLateRules.Refusal = null; FfaLateRules.KeptThrows = false;
            FfaAssembly.ReadmitLobby = true;
            FfaReadmit.Readmitted = true; FfaReadmit.Entered = 0; FfaAssembly.LateEntered = 0;
        }
    }

    internal static class VanillaFixSupport
    {
        internal static void DiagLimited(string key, string msg, int n) { Trace.Event("diag " + key + " " + msg); }
    }

    internal static class SpawnOnImpactFieldDiagPatch { internal const string FfaAuditFailKey = "FfaGunAudit-failed"; }

    internal static class ApiClient
    {
        public class TeamQueueMember { public string steam_id; public string display_name; }
        public static List<TeamQueueMember> FfaLockedRoster;
    }

    /// <summary>The members FfaMode declares that the reducer reads or calls,
    /// as one shared base: the generated reducers derive from it, so their
    /// extracted bodies bind these names exactly as they bind FfaMode's.</summary>
    internal class ReducerBase
    {
        public static int CardCap = 5;
        protected static readonly Dictionary<int, List<CardInfo>> decks = new Dictionary<int, List<CardInfo>>();
        protected static readonly Dictionary<int, List<MatchTracker.CardPickData>> pickHistory =
            new Dictionary<int, List<MatchTracker.CardPickData>>();
        protected static readonly HashSet<int> deckViewRebuilds = new HashSet<int>();
        protected static readonly List<CompetitiveUI.NotifSetItem> _cycleToasts = new List<CompetitiveUI.NotifSetItem>(12);
        internal static readonly Dictionary<int, Player> Fighters = new Dictionary<int, Player>();

        internal static Player ResolveFighter(int pid) { Player p; return Fighters.TryGetValue(pid, out p) ? p : null; }
        protected static int RoundsTotalAll() { return 3; }
        protected static void CaptureBaselineIfNeeded(Player p) { Trace.Event("baseline " + Id(p)); }
        protected static IEnumerator RollingResetAndReplay(Player p, List<CardInfo> survivors)
        {
            Trace.Event("replay_start " + Id(p) + " [" + string.Join(",", survivors.Select(c => c.gameObject.name)) + "]");
            if (Trace.Inject == "replay") throw new InvalidOperationException("injected replay");
            yield return null;
            Trace.Event("replay_end " + Id(p));
        }
        protected static void ApplyCardTo(Player p, CardInfo prefab)
        {
            Trace.Event("apply_card " + Id(p) + " " + prefab.gameObject.name);
            if (Trace.Inject == "apply") throw new InvalidOperationException("injected apply");
        }
        protected static void RebuildDeckViews(Player p, List<CardInfo> deck)
        {
            Trace.Event("rebuild_views " + Id(p) + " [" + string.Join(",", deck.Select(c => c.gameObject.name)) + "]");
            if (Trace.Inject == "rebuild") throw new InvalidOperationException("injected rebuild");
        }
        private static string Id(Player p) { return p == null ? "null" : p.PlayerID.ToString(); }

        internal static void ResetState()
        {
            CardCap = 5;
            decks.Clear(); pickHistory.Clear(); deckViewRebuilds.Clear(); _cycleToasts.Clear();
            Fighters.Clear(); FfaLateEntry.Quarantined.Clear();
        }

        internal static void SeedDeck(int pid, IEnumerable<CardInfo> cards) { decks[pid] = cards.ToList(); }
        internal static void SeedHistory(int pid, IEnumerable<string> names)
        {
            var h = new List<MatchTracker.CardPickData>();
            foreach (var n in names) h.Add(new MatchTracker.CardPickData { CardName = n, PickOrder = h.Count + 1, RoundNumber = h.Count + 1 });
            pickHistory[pid] = h;
        }

        /// <summary>The state the reducer owns, as one line.</summary>
        internal static string Snapshot()
        {
            var sb = new StringBuilder();
            sb.Append("decks{");
            foreach (var kv in decks.OrderBy(k => k.Key))
                sb.Append(kv.Key).Append(':').Append(string.Join(",", kv.Value.Select(c => c.gameObject.name))).Append(';');
            sb.Append("} hist{");
            foreach (var kv in pickHistory.OrderBy(k => k.Key))
                sb.Append(kv.Key).Append(':').Append(string.Join(",", kv.Value.Select(
                    h => h.CardName + "/" + h.CardRarity + "/" + h.PickOrder + "/" + h.RoundNumber + (h.Rolled ? "/R" : "")))).Append(';');
            sb.Append("} toasts[").Append(string.Join("|", _cycleToasts.Select(t => t.text))).Append("] rebuilds[")
              .Append(string.Join(",", deckViewRebuilds.OrderBy(x => x))).Append(']');
            return sb.ToString();
        }
    }

    /// <summary>The ordered effect trace: every observable event, each with the
    /// state snapshot at that instant.</summary>
    internal static class Trace
    {
        internal static string Inject = "";
        internal static readonly List<string> Events = new List<string>();
        internal static void Event(string e) { Events.Add(e + " || " + ReducerBase.Snapshot()); }
    }
}
