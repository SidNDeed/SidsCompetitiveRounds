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

    internal sealed class PhotonView { public bool IsMine; public OwnerStub Owner; }

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
        internal static readonly HashSet<int> Quarantined = new HashSet<int>();
        internal static bool IsQuarantined(Player p) { return p != null && Quarantined.Contains(p.PlayerID); }
        internal static void Refused(string site, Player p) { Trace.Event("refused " + site + " " + (p == null ? -1 : p.PlayerID)); }
        internal static void MarkDigestDirty() { Trace.Event("digest_dirty"); }
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
