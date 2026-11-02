# drive.py: part c's banner (lesson 221: drawn every frame while the self-drive drives), applied by entry_insert.py.
SPECS = [
    ("plugin/Plugin.cs", "public class Plugin : BaseUnityPlugin", "private void OnGUI()",
     "before:// RJ Stage 2 (S2): the non-modal hold banner", ["try { FtDrive.Banner(); } catch { }"]),
]

# part c's rematch [F04]: in an ft_ room the Continue prompt is held by FtRematch (both seats' ft_rm, 60 s timeout)
SPECS += [
    ("plugin/Plugin.cs", "class PopUpHandler_StartPicking_Competitive_Patch",
     "static bool Prefix(global::Player player, Action<PopUpHandler.YesNo> functionToCall)",
     "before:if (!CompetitiveRoomDetect.IsCompetitiveRoom()) return true;",
     ["if (FtArm.InFtRoom() && FtConfig.Present) { FtRematch.Hold(functionToCall); return false; }"]),
]
