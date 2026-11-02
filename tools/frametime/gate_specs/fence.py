# fence.py: part b's room rules (FORMAT-M-PLAN.md V2 section 3, F03, F12), applied by entry_insert.py.
# The opponent ranked check returns false without its request inside any ft_ room; the sentinel key
# ranked_hook=1 is the build round's control (a hook answering ranked=true, placed BEHIND the skip so it is never
# reached in an ft_ room); the guard's mutant is its own key, ranked_guard_mutant=1, which removes the skip alone,
# so matchIsRanked turns true and FtArm disarms with input=matchIsRanked (round-1 MEDIUM, ApiClient.cs:9557).
# The skip line below carries that key since round 1; the insert ran before it, and the file is the reference. The broadcast
# fence exempts exactly this build's own ft_ room at its three join points, only while the sentinel is present.

PL, AC, BM = "plugin/Plugin.cs", "plugin/ApiClient.cs", "plugin/BroadcastMode.cs"
BMC = "internal static class BroadcastMode"
SPECS = [
    (AC, "public static class ApiClient", "public static void CheckOpponentRanked(string steamId, Action<bool> callback)",
     "entry",
     ["if (FtConfig.Get(\"ranked_guard_mutant\", \"0\") != \"1\" && FtArm.InFtRoom()) { Plugin.Log.LogInfo(\"[FRAME-TIME] ranked-check skipped\"); callback(false); return; }",
      "if (FtConfig.Get(\"ranked_hook\", \"0\") == \"1\") { Plugin.Log.LogInfo(\"[FRAME-TIME] ranked-check test hook answered true\"); callback(true); return; }"]),
    (PL, "public class Plugin : BaseUnityPlugin",
     "public static void SetPendingRoom(string roomName, string region, string rulesProp, string rulesSrc)",
     "pair:if (BroadcastMode.FenceBlocksFighterPath(\"pending-fighter-room\")) return;",
     ["if (!FtArm.FenceExempt(roomName) && BroadcastMode.FenceBlocksFighterPath(\"pending-fighter-room\")) return;"]),
    (BM, BMC, "internal static bool OnJoinedRoomFence()",
     "before:Plugin.Log?.LogWarning($\"[BROADCAST] §2c fence: joined",
     ["if (FtArm.FenceExemptCurrent()) return false;"]),
    (BM, BMC, "private static void FenceTick()", "before:_nextFenceKickAt = Time.realtimeSinceStartup + 5f;",
     ["if (FtArm.FenceExemptCurrent()) return;"]),
]
