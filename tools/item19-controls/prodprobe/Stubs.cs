using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

// Item 19 fix pass 2: the stand-ins the PRODUCTION file plugin/AvatarDefaults.cs
// compiles against in the production probe (ProdProbe.cs). Each one carries
// only the members that file names, with the behaviour the probe needs to
// observe its sinks: the selection write, the config ints, the log, the toast,
// the ring sprite. Nothing here decides a face; the decisions are the real
// AvatarDefaults.cs and AvatarDefaultRules.cs, copied unedited (or with ONE
// mutation) next to this file by tools/item19-controls/item19_controls.py and
// by backend/tests/test_client_avatar_defaults.py (S35).

namespace UnityEngine
{
    public enum HideFlags { None = 0, HideAndDontSave = 61 }
    public enum TextureFormat { ARGB32 = 5 }
    public enum FilterMode { Point, Bilinear }
    public enum TextureWrapMode { Repeat, Clamp }
    public enum SpriteMeshType { FullRect, Tight }

    public struct Color
    {
        public float r, g, b, a;
        public Color(float r, float g, float b) : this(r, g, b, 1f) { }
        public Color(float r, float g, float b, float a) { this.r = r; this.g = g; this.b = b; this.a = a; }
        public static Color white => new Color(1f, 1f, 1f, 1f);
        public override string ToString() =>
            string.Format(CultureInfo.InvariantCulture, "({0:F3},{1:F3},{2:F3},{3:F3})", r, g, b, a);
    }

    public struct Vector2 { public float x, y; public Vector2(float x, float y) { this.x = x; this.y = y; } }
    public struct Vector3 { public float x, y, z; public Vector3(float x, float y, float z) { this.x = x; this.y = y; this.z = z; } }
    public struct Vector4 { public float x, y, z, w; public Vector4(float x, float y, float z, float w) { this.x = x; this.y = y; this.z = z; this.w = w; } }

    public struct Rect
    {
        public float x, y, width, height;
        public Rect(float x, float y, float w, float h) { this.x = x; this.y = y; width = w; height = h; }
        public Vector2 center => new Vector2(x + width / 2f, y + height / 2f);
        public float yMin => y;
    }

    public struct Scene { public bool IsValid() => true; }

    public class Object
    {
        public string name;
        public HideFlags hideFlags;
    }

    /// <summary>Every component the probe creates, for FindObjectsOfTypeAll.</summary>
    internal static class World
    {
        internal static readonly List<Component> All = new List<Component>();
    }

    public class GameObject : Object
    {
        internal bool active = true;
        internal readonly List<Component> comps = new List<Component>();
        private readonly RectTransform rt;

        public GameObject(string name)
        {
            this.name = name;
            rt = new RectTransform { gameObject = this };
        }

        public Transform transform => rt;
        public Scene scene => new Scene();

        public bool activeInHierarchy
        {
            get
            {
                for (Transform t = rt; t != null; t = t.parent)
                    if (!t.gameObject.active) return false;
                return true;
            }
        }

        public void SetActive(bool v) { active = v; }

        public Component GetComponent(Type t)
        {
            if (t.IsInstanceOfType(rt)) return rt;
            foreach (var c in comps) if (t.IsInstanceOfType(c)) return c;
            return null;
        }

        public T GetComponent<T>()
        {
            var c = GetComponent(typeof(T));
            return c is T v ? v : default(T);
        }

        public Component AddComponent(Type t)
        {
            var c = (Component)Activator.CreateInstance(t, true);
            c.gameObject = this;
            comps.Add(c);
            World.All.Add(c);
            return c;
        }

        internal IEnumerable<Component> AllComponents()
        {
            yield return rt;
            foreach (var c in comps) yield return c;
        }
    }

    public class Component : Object
    {
        public GameObject gameObject;
        public Transform transform => gameObject != null ? gameObject.transform : null;
        public T GetComponent<T>() => gameObject.GetComponent<T>();
        public T[] GetComponents<T>() => gameObject.AllComponents().OfType<T>().ToArray();
        public T GetComponentInChildren<T>() => GetComponentInChildren<T>(false);

        public T GetComponentInChildren<T>(bool includeInactive)
        {
            var stack = new Stack<Transform>();
            stack.Push(transform);
            while (stack.Count > 0)
            {
                var t = stack.Pop();
                foreach (var c in t.gameObject.AllComponents()) if (c is T v) return v;
                foreach (var ch in t.children) stack.Push(ch);
            }
            return default(T);
        }
    }

    public class Behaviour : Component { }
    public class MonoBehaviour : Behaviour { }

    public class Transform : Component
    {
        private Transform par;
        internal readonly List<Transform> children = new List<Transform>();
        public Vector3 position;

        public Transform parent
        {
            get => par;
            set { if (par != null) par.children.Remove(this); par = value; if (value != null) value.children.Add(this); }
        }

        public int childCount => children.Count;

        public Transform Find(string n)
        {
            foreach (var c in children) if (c.gameObject.name == n) return c;
            return null;
        }

        public int GetSiblingIndex() => par == null ? 0 : par.children.IndexOf(this);

        public void SetAsLastSibling()
        {
            if (par == null) return;
            par.children.Remove(this);
            par.children.Add(this);
        }

        public Vector3 TransformPoint(Vector3 v) => v;
    }

    public class RectTransform : Transform
    {
        public Vector2 offsetMin, offsetMax, pivot;
        public Rect rect => new Rect(0f, 0f, 600f, 300f);
    }

    public class Texture2D : Object
    {
        public readonly int width, height;
        public FilterMode filterMode;
        public TextureWrapMode wrapMode;
        internal Color[] pixels;

        public Texture2D(int w, int h, TextureFormat f, bool mip) { width = w; height = h; pixels = new Color[w * h]; }
        public void SetPixels(Color[] px) { pixels = (Color[])px.Clone(); }
        public void Apply(bool updateMipmaps, bool makeNoLongerReadable) { }
        public Color GetPixel(int x, int y) => pixels[y * width + x];
    }

    public class Sprite : Object
    {
        public Texture2D texture;
        public static Sprite Create(Texture2D t, Rect r, Vector2 pivot, float pixelsPerUnit, uint extrude, SpriteMeshType mesh, Vector4 border)
            => new Sprite { texture = t };
    }

    public static class Resources
    {
        public static T[] FindObjectsOfTypeAll<T>() => World.All.OfType<T>().ToArray();
    }

    public static class Time
    {
        public static int frameCount;
    }
}

namespace HarmonyLib
{
    [AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true)]
    public class HarmonyPatch : Attribute { public HarmonyPatch(Type t, string method) { } }

    [AttributeUsage(AttributeTargets.Class | AttributeTargets.Method)]
    public class HarmonyPriority : Attribute { public HarmonyPriority(int p) { } }

    public static class Priority { public const int VeryHigh = 700; }
}

namespace Photon.Realtime
{
    public class Room
    {
        public string Name = "probe-room";
        public Hashtable CustomProperties = new Hashtable();
    }

    public class Player
    {
        public bool IsLocal;
        public int ActorNumber;
        public Hashtable CustomProperties;
    }
}

namespace Photon.Pun
{
    public class PhotonView : UnityEngine.MonoBehaviour { public bool IsMine; }

    /// <summary>Each getter is a delegate so a probe case can make one of
    /// them throw (BR-M4: the first room getter succeeds, the second throws).</summary>
    public static class PhotonNetwork
    {
        public static Func<bool> InRoomFn = () => false;
        public static Func<bool> OfflineFn = () => false;
        public static bool InRoom => InRoomFn();
        public static bool OfflineMode => OfflineFn();
        public static Photon.Realtime.Room CurrentRoom;
    }
}

// The game's own types (global namespace, as in Assembly-CSharp).

public class GameManager
{
    public static GameManager instance;
    public bool isPlaying, battleOngoing;
}

public class PlayerFace
{
    public int eyeID, mouthID, detailID, detail2ID;
}

public class CharacterItem { }

public class CharacterCreatorItemLoader
{
    public static CharacterCreatorItemLoader instance;
    public CharacterItem[] eyes, mouths, accessories;
}

public class CharacterCreatorHandler
{
    public static CharacterCreatorHandler instance;
    public int[] selectedFaceID = new int[4];
    public PlayerFace[] playerFaces;
    public PlayerFace[] selectedPlayerFaces = new PlayerFace[4];
    internal int SelectCalls;

    // Fix pass 3 (H9, M3, M8): how the next selects end, each a count of the
    // selects it applies to. ThrowBeforeCommit: the select throws before it
    // writes the selection. NoCommit: it returns without writing it (the
    // read-back shows the selection unmoved). ThrowAfterCommit: it writes the
    // selection, the postfix runs, then it throws (vanilla's ClickButton
    // repainting the portrait frames after the select).
    //
    // Fix pass 4 (H9, M3): a select that returns NORMALLY runs the postfix
    // whether or not it wrote the selection, as Harmony runs a postfix
    // whenever the original returns normally; so NoCommit now runs it too.
    // NoCommitNoPostfix is the fix pass 3 form (it returned before the
    // postfix, which hid the postfix's re-entry from the probe), kept only
    // as the separately named negative (H9rmask, M3xmask).
    // PersistentNoCommit: every select returns normally without writing (a
    // persistent no-op), postfix included.
    internal static int ThrowBeforeCommit, NoCommit, ThrowAfterCommit, NoCommitNoPostfix;
    internal static bool PersistentNoCommit;

    // Fix pass 4 (H9): the selects in progress (a postfix that selects again
    // from inside a select nests one deeper), the deepest nesting seen, and
    // the bound: a select nested past MaxDepth throws, so a re-entry without
    // a bound ends in a counted fault the caller catches instead of a stack
    // overflow, and DeepestDepth shows it.
    internal static int Depth, DeepestDepth;
    internal const int MaxDepth = 8;

    /// <summary>Vanilla's single writer of the selection, then item 19's
    /// Harmony postfix on it (edge E9), exactly as the patched game runs it.</summary>
    internal void SelectFace(int faceID, PlayerFace selectedFace, int faceSlot)
    {
        SelectCalls++;
        Depth++;
        try
        {
            if (Depth > DeepestDepth) DeepestDepth = Depth;
            if (Depth > MaxDepth) throw new InvalidOperationException("probe: the select re-entered past the depth bound " + MaxDepth);
            if (ThrowBeforeCommit > 0) { ThrowBeforeCommit--; throw new NullReferenceException("probe: the select threw before it committed"); }
            if (NoCommitNoPostfix > 0) { NoCommitNoPostfix--; return; }
            bool commit = true;
            if (PersistentNoCommit) commit = false;
            else if (NoCommit > 0) { NoCommit--; commit = false; }
            if (commit)
            {
                selectedFaceID[faceID] = faceSlot;
                selectedPlayerFaces[faceID] = selectedFace;
            }
            CompetitiveRounds.ProdProbe.SelectFacePostfix(faceID);
            if (commit && ThrowAfterCommit > 0) { ThrowAfterCommit--; throw new NullReferenceException("probe: the frame repaint threw after the select committed"); }
        }
        finally { Depth--; }
    }
}

public class CharacterCreatorPortrait : UnityEngine.MonoBehaviour
{
    public int playerId = -1;
    public PlayerFace myFace;
    internal int Clicks;                               // bug 444: how often the apply went through this portrait
    public void ClickButton() { Clicks++; CharacterCreatorHandler.instance.SelectFace(0, myFace, transform.GetSiblingIndex()); }
}

public class CharacterCreatorItemEquipper : UnityEngine.MonoBehaviour
{
    internal int Equips;
    public void EquipFace(PlayerFace f) { Equips++; }
}

public class CharacterData { public Photon.Pun.PhotonView view; }

public class Player : UnityEngine.MonoBehaviour { public CharacterData data; }

public class PlayerManager
{
    public static PlayerManager instance;
    public List<Player> players = new List<Player>();
}

public class PlayerAssigner { }

namespace CompetitiveRounds
{
    internal sealed class ConfigEntry<T> { public T Value { get; set; } }

    // Bug 434: AvatarDefaults.TickPortraits counts its grid scans on the
    // per-match PERF line (PerfPatches.cs). The probe only needs the name.
    internal static class PerfGate
    {
        public static void Hit(string patch) { }
    }

    internal sealed class ProbeLog
    {
        internal readonly List<string> Lines = new List<string>();
        public void LogInfo(object m) { Lines.Add("INFO " + m); }
        public void LogWarning(object m) { Lines.Add("WARN " + m); }
    }

    internal static class Plugin
    {
        internal static ProbeLog Log = new ProbeLog();
        internal static ConfigEntry<bool> AvatarAutoSwitch = new ConfigEntry<bool>();
        internal static ConfigEntry<int> AvatarModdedPreset = new ConfigEntry<int>();
        internal static ConfigEntry<int> AvatarVanillaPreset = new ConfigEntry<int>();
        internal static ConfigEntry<int> AvatarHomeSlot = new ConfigEntry<int>();
    }

    internal static class FacePublisher
    {
        public const string PROP_FACE = "cr_face";
        internal static int Publishes;
        internal static int Throws;                    // fix pass 3 (M8): the next N publishes throw
        // Bug 444: the outcome the production writer (Plugin.cs, FacePublisher)
        // decides for the face this seat has selected, through the same rule
        // over the same input, selectedPlayerFaces[0]. Keep until a publish.
        internal static FaceCarrierAction LastAction = FaceCarrierAction.Keep;
        public static FaceCarrierAction PublishLocal()
        {
            Publishes++;
            if (Throws > 0) { Throws--; throw new InvalidOperationException("probe: the carrier publish threw"); }
            var cch = CharacterCreatorHandler.instance;
            bool listed = cch != null && cch.selectedPlayerFaces != null && cch.selectedPlayerFaces.Length > 0;
            var face = listed ? cch.selectedPlayerFaces[0] : null;
            var ids = face != null ? AvatarFaceIds.Of(face.eyeID, face.mouthID, face.detailID, face.detail2ID) : new AvatarFaceIds();
            LastAction = new AvatarRules().CarrierAction(false, cch != null, true, listed, ids);
            return LastAction;
        }
    }

    /// <summary>Fix pass 3: the bounded diagnostic budget the evaluator's E13
    /// lines draw on (VanillaFixes.cs), with its semantics: a key's count up
    /// to its maximum, dropped by ResetDiag.</summary>
    internal static class VanillaFixSupport
    {
        internal static readonly Dictionary<string, int> Counts = new Dictionary<string, int>();
        internal static bool TryReserveDiag(string key, int maximum)
        {
            if (string.IsNullOrEmpty(key) || maximum <= 0) return false;
            int n;
            Counts.TryGetValue(key, out n);
            if (n >= maximum) return false;
            Counts[key] = n + 1;
            return true;
        }
        internal static void ResetDiag(string key) { if (!string.IsNullOrEmpty(key)) Counts.Remove(key); }
    }

    internal static class FaceResync
    {
        internal static int Sends;
        internal static bool TrySendLocalFace(string tag) { Sends++; return true; }
    }

    internal static class CompetitiveRoomDetect
    {
        internal static bool Issued;
        internal static bool IsModIssuedRoom(string name, object props) => Issued;
    }

    internal static class RoomActors
    {
        internal static bool LocalIsSpectator;
        internal static Func<IEnumerable<Photon.Realtime.Player>> Fighters = () => new List<Photon.Realtime.Player>();
        internal static IEnumerable<Photon.Realtime.Player> ActiveFighters() => Fighters();
    }

    internal static class I18n
    {
        internal static string Tr(string s) => s;
        internal static string TrF(string f, params object[] a) => string.Format(CultureInfo.InvariantCulture, f, a);
    }

    /// <summary>The toast surface: the announcement sink.</summary>
    internal static class CompetitiveUI
    {
        internal static readonly List<string> Shown = new List<string>();
        internal static bool IsShowing(string m) => false;
        internal static void ShowNotification(string m, UnityEngine.Color c, float seconds) { Shown.Add(m); }
    }

    internal static class PortraitRender
    {
        internal static int PresetSlotCount() => 10;
    }

    internal sealed class StubImage : UnityEngine.MonoBehaviour { public bool raycastTarget { get; set; } = true; }
    internal sealed class StubLayoutElement : UnityEngine.MonoBehaviour { public bool ignoreLayout { get; set; } }
    internal sealed class TextMeshProUGUI : UnityEngine.MonoBehaviour { public string text; }

    /// <summary>The reflection UI factory: the ring sprite sink.</summary>
    internal static class UIFactory
    {
        internal static readonly Type tImage = typeof(StubImage);
        internal static readonly Type tLE = typeof(StubLayoutElement);
        internal static readonly int AlignTopCenter = 0;
        internal static readonly List<KeyValuePair<UnityEngine.GameObject, UnityEngine.Sprite>> Sprites =
            new List<KeyValuePair<UnityEngine.GameObject, UnityEngine.Sprite>>();

        internal static UnityEngine.GameObject CreatePanel(string name, UnityEngine.Transform parent, UnityEngine.Color c)
        {
            var go = new UnityEngine.GameObject(name);
            go.transform.parent = parent;
            go.AddComponent(tImage);
            return go;
        }

        internal static void SetImageSprite(UnityEngine.GameObject go, UnityEngine.Sprite s)
        {
            Sprites.Add(new KeyValuePair<UnityEngine.GameObject, UnityEngine.Sprite>(go, s));
        }

        internal static object CreateText(string name, UnityEngine.Transform parent, string text, float size, UnityEngine.Color c,
                                          int align, UnityEngine.Vector2 sizeDelta = default(UnityEngine.Vector2))
        {
            var go = new UnityEngine.GameObject(name);
            go.transform.parent = parent;
            return go.AddComponent(typeof(TextMeshProUGUI));
        }

        internal static void SetTextRaw(object t, string s) { ((TextMeshProUGUI)t).text = s; }
    }
}
