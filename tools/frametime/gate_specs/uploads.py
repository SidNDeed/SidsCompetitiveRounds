# uploads.py: part b's upload refusals (FORMAT-M-PLAN.md V2 section 3, items 1 to 4 and chat), applied by
# entry_insert.py. Every branch reads FtUpload.Closed (always true in this variant) and counts the refusal.

SE, AC, CC = "plugin/SeatEvidence.cs", "plugin/ApiClient.cs", "plugin/ChatClient.cs"
SEC = "internal static class SeatEvidence"
ACC = "public static class ApiClient"
SPECS = [
    # 1. the seat-evidence queue: as on success, nothing loaded or saved, nothing evicted
    (SE, SEC, "private static bool Enqueue(string route, string body)", "entry",
     ["if (FtUpload.Closed) { FtUpload.Refuse(\"queue\", route); return true; }"]),
    # CompatTick's queued line: no line claims a queued record [F19]
    (SE, SEC, "internal static void CompatTick()", "pair:Plugin.Log.LogInfo(TAG + \" compat outcome queued: \"",
     ["Plugin.Log.LogInfo(TAG + \" compat outcome refused: \" + outcome + \" plugins=\" + _compatPlugins.Count.ToString(CultureInfo.InvariantCulture));"]),
    # 2. the closing files: as on success for a valid record, nothing written
    (SE, SEC, "internal static bool SpoolClosing(string route, string body)",
     "before:var p = new C.Pending { Route = route, Body = body, FirstUnix = UnixNow() };",
     ["if (FtUpload.Closed) { FtUpload.Refuse(\"closing\", route); return true; }"]),
    # 3. the pump, and the queue's Load before it touches disk
    (SE, SEC, "private static void Pump(long nowMs)", "entry", ["if (FtUpload.Closed) { FtUpload.Refuse(\"pump\", null); return; }"]),
    (SE, SEC, "private static bool Load()", "entry", ["if (FtUpload.Closed) { FtUpload.Refuse(\"load\", null); return false; }"]),
    # 4. the report outbox: nothing kept, read or written
    (AC, ACC, "public static void EnqueueFailedReport(string url, string json)", "entry",
     ["if (FtUpload.Closed) { FtUpload.Refuse(\"outbox\", \"enqueue\"); return; }"]),
    (AC, ACC, "private static void PersistOutbox()", "entry", ["if (FtUpload.Closed) { FtUpload.Refuse(\"outbox\", \"persist\"); return; }"]),
    (AC, ACC, "private static void LoadOutbox()", "entry", ["if (FtUpload.Closed) { FtUpload.Refuse(\"outbox\", \"load\"); return; }"]),
    (AC, ACC, "internal static void OutboxTick()", "entry", ["if (FtUpload.Closed) return;"]),
    # chat: Connect returns at entry with one refused line
    (CC, "public static class ChatClient", "public static void Connect()", "entry",
     ["if (FtUpload.Closed) { FtUpload.Refuse(\"chat\", \"connect\"); return; }"]),
]

# The log sources [F01]: no LogOutput-prev copy at quit (the runner restores the log files around the sitting),
# and no automatic log upload at a room exit during the sitting itself.
SPECS += [
    ("plugin/Plugin.cs", "public class Plugin : BaseUnityPlugin", "private void Awake()",
     "before:string src = CompetitiveUI.BepInExLogPathPublic();",
     ["if (FtUpload.Closed) { FtUpload.Refuse(\"log\", \"prev-copy\"); FtUpload.LogCounts(\"quit\"); return; }"]),
    ("plugin/AutoLogUpload.cs", "internal static class AutoLogUpload", "internal static void OnRoomLeft()", "entry",
     ["if (FtUpload.Closed) { FtUpload.Refuse(\"autolog\", \"room-left\"); return; }"]),
]
