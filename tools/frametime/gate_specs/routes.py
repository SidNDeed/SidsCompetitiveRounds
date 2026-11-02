# routes.py: part b item 5 at the three System.Net downloads, which the UnityWebRequest choke point
# (plugin/FtRoute.cs) does not see. Each refusal throws inside the site's own try, so the site's catch handles
# it as a transport failure; nothing is requested. Applied by entry_insert.py.

THROW = "throw new System.Net.WebException(\"frametime: refused\");"
SPECS = [
    ("plugin/CustomCosmetics.cs", "internal static class CustomCosmetics", "private static void ArtDownloadWorker()",
     "before:using (var wc = new System.Net.WebClient())",
     ["if (FtUpload.Closed) { FtUpload.RefuseQuiet(\"route\", \"GET_cosmetics-zip\"); " + THROW + " }"]),
    ("plugin/EmojiSprites.cs", "internal static class EmojiSprites", "private static bool DownloadOnce(string url,",
     "before:var req = (System.Net.HttpWebRequest)System.Net.WebRequest.Create(url);",
     ["if (FtUpload.Closed) { FtUpload.RefuseQuiet(\"route\", \"GET_emoji-sheet\"); " + THROW + " }"]),
    ("plugin/MusicAssets.cs", "internal static class MusicAssets", "private static DlOutcome DownloadWithCap(string url,",
     "before:var req = (System.Net.HttpWebRequest)System.Net.WebRequest.Create(url);",
     ["if (FtUpload.Closed) { FtUpload.RefuseQuiet(\"route\", \"GET_music-asset\"); " + THROW + " }"]),
]
