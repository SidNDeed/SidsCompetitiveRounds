# fence.py: part b's room rules (FORMAT-M-PLAN.md V2 section 3, F03, F12), applied by entry_insert.py.
# The opponent ranked check returns false without its request inside any ft_ room; the sentinel key
# ranked_hook=1 is the build round's control (a hook answering ranked=true, never reached behind the skip; the
# mutant without the skip turns matchIsRanked true and FtArm disarms with input=matchIsRanked). The broadcast
# fence exempts exactly this build's own ft_ room at its three join points, only while the sentinel is present.

PL, AC, BM = "plugin/Plugin.cs", "plugin/ApiClient.cs", "plugin/BroadcastMode.cs"
BMC = "internal static class BroadcastMode"
SPECS = [
    (AC, "public static class ApiClient", "public static void CheckOpponentRanked(string steamId, Action<bool> callback)",
     "entry",
     ["if (FtArm.InFtRoom()) { Plugin.Log.LogInfo(\"[FRAME-TIME] ranked-check skipped\"); callback(false); return; }",
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
