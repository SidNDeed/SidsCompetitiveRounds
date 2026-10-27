// Identity-clock fix pass 3 (QF1): the further stand-ins the REAL
// plugin/IdentityClockEvidence.cs needs, so the replay can compile it as it
// ships (build property IcRealEvidence=true, define IC_REAL_EVIDENCE) and drive
// the production capture, census, build and quit flush. Types only, plain state
// the case sets; nothing here decides anything. The members these types add to
// the shared stand-ins (Time, PhotonNetwork, Paths, Harmony, AccessTools,
// PlayerManager, CharacterData, LogSink) live in Stubs.cs beside them.
using System;
using System.Collections.Generic;

namespace UnityEngine
{
    public struct Vector3
    {
        public float x, y, z;
        public Vector3(float x, float y, float z) { this.x = x; this.y = y; this.z = z; }
        public static Vector3 zero { get { return new Vector3(0f, 0f, 0f); } }
        public static bool operator ==(Vector3 a, Vector3 b) { return a.x == b.x && a.y == b.y && a.z == b.z; }
        public static bool operator !=(Vector3 a, Vector3 b) { return !(a == b); }
        public override bool Equals(object o) { return o is Vector3 && (Vector3)o == this; }
        public override int GetHashCode() { return x.GetHashCode() ^ y.GetHashCode() ^ z.GetHashCode(); }
    }
    public struct Keyframe { public float time, value; }
    public class AnimationCurve { public Keyframe[] keys = new Keyframe[0]; }
}

namespace Photon.Pun
{
    public class PhotonStream { public bool IsReading; }
    public struct PhotonMessageInfo { public int SentServerTimestamp; }
}

namespace BepInEx
{
    public class PluginInfo { }
}

namespace BepInEx.Bootstrap
{
    public static class Chainloader
    {
        public static Dictionary<string, BepInEx.PluginInfo> PluginInfos = new Dictionary<string, BepInEx.PluginInfo>();
    }
}

namespace HarmonyLib
{
    public class Patch
    {
        public string owner = "";
        public System.Reflection.MethodInfo PatchMethod;
    }
    public class HarmonyMethod
    {
        public HarmonyMethod(Type t, string name) { }
    }
}

// -- game types (global namespace, as in Assembly-CSharp) ----------------------------
public class GeneralInput { public UnityEngine.Vector3 direction; }
public class CardChoice { public static CardChoice instance; public bool IsPicking; }
public class SpawnPoint { public UnityEngine.Vector3 localStartPos; }
public class MapManager { }
public class SyncPlayerMovement
{
    public class Package
    {
        public UnityEngine.Vector3 pos, vel, dir, aim;
        public bool jump, holdJump;
        public float timeDelta;
    }
    public Photon.Pun.PhotonView photonView;
    public List<Package> syncPackages = new List<Package>();
}
