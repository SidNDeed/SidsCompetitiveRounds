using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Threading;

namespace CompetitiveRoundsInstaller
{
    class Program
    {
        // ── Constants ──────────────────────────────────────────────
        const string BEPINEX_URL = "https://thunderstore.io/package/download/BepInEx/BepInExPack_ROUNDS/5.4.1901/";
        const string GITHUB_API_LATEST = "https://api.github.com/repos/SidNDeed/SidsCompetitiveRounds/releases/latest";
        const string MOD_DLL_NAME = "CompetitiveRounds.dll";
        const string DEFAULT_ROUNDS_PATH = @"C:\Program Files (x86)\Steam\steamapps\common\ROUNDS";

        static string roundsPath = "";
        static string pluginsPath = "";
        static string bepinexPath = "";

        static void Main(string[] args)
        {
            Console.Title = "Sid's Competitive ROUNDS — Installer";
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;

            while (true)
            {
                Console.Clear();
                PrintHeader();
                DetectInstallation();
                PrintStatus();
                PrintMenu();

                var key = Console.ReadKey(true).Key;
                switch (key)
                {
                    case ConsoleKey.D1:
                    case ConsoleKey.NumPad1:
                        SetRoundsPath();
                        break;
                    case ConsoleKey.D2:
                    case ConsoleKey.NumPad2:
                        InstallBepInEx();
                        break;
                    case ConsoleKey.D3:
                    case ConsoleKey.NumPad3:
                        InstallOrUpdateMod();
                        break;
                    case ConsoleKey.D4:
                    case ConsoleKey.NumPad4:
                        InstallEverything();
                        break;
                    case ConsoleKey.D5:
                    case ConsoleKey.NumPad5:
                        LaunchRounds();
                        break;
                    case ConsoleKey.D6:
                    case ConsoleKey.NumPad6:
                        UninstallMenu();
                        break;
                    case ConsoleKey.Q:
                    case ConsoleKey.Escape:
                        return;
                }
            }
        }

        // ── UI ─────────────────────────────────────────────────────

        static void PrintHeader()
        {
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine(@"  ╔══════════════════════════════════════════════════════╗");
            Console.WriteLine(@"  ║      SID'S COMPETITIVE ROUNDS  —  INSTALLER         ║");
            Console.WriteLine(@"  ╚══════════════════════════════════════════════════════╝");
            Console.ResetColor();
            Console.WriteLine();
        }

        static string cachedLatestVersion = null;

        static void PrintStatus()
        {
            Console.ForegroundColor = ConsoleColor.White;
            Console.Write("  ROUNDS Path:    ");
            if (!string.IsNullOrEmpty(roundsPath) && Directory.Exists(roundsPath))
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine(roundsPath);
            }
            else
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("NOT FOUND");
            }

            Console.ForegroundColor = ConsoleColor.White;
            Console.Write("  BepInEx:        ");
            if (IsBepInExInstalled())
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("INSTALLED");
            }
            else
            {
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.WriteLine("NOT INSTALLED");
            }

            Console.ForegroundColor = ConsoleColor.White;
            Console.Write("  Competitive DLL: ");
            string ver = GetInstalledModVersion();
            if (ver != null)
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.Write($"v{ver}");

                // Compare to latest
                if (cachedLatestVersion == null)
                {
                    try
                    {
                        using (var wc = new WebClient())
                        {
                            wc.Headers.Add("User-Agent", "CompetitiveRoundsInstaller/1.0");
                            string json = wc.DownloadString(GITHUB_API_LATEST);
                            string tag = ExtractJsonValue(json, "tag_name") ?? "";
                            cachedLatestVersion = tag.TrimStart('v', 'V');
                        }
                    }
                    catch { cachedLatestVersion = ""; }
                }

                if (!string.IsNullOrEmpty(cachedLatestVersion) && cachedLatestVersion != ver)
                {
                    Console.ForegroundColor = ConsoleColor.Yellow;
                    Console.Write($"  (latest: v{cachedLatestVersion} — update available!)");
                }
                else if (!string.IsNullOrEmpty(cachedLatestVersion))
                {
                    Console.ForegroundColor = ConsoleColor.DarkGray;
                    Console.Write("  (up to date)");
                }
                Console.WriteLine();
            }
            else
            {
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.WriteLine("NOT INSTALLED");
            }

            Console.ResetColor();
            Console.WriteLine();
        }

        static void PrintMenu()
        {
            Console.ForegroundColor = ConsoleColor.White;
            Console.WriteLine("  ─────────────────────────────────────────────────────");
            Console.WriteLine();
            Console.WriteLine("  [1]  Set ROUNDS install path");
            Console.WriteLine("  [2]  Install BepInEx");
            Console.WriteLine("  [3]  Install / Update Competitive ROUNDS mod");
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine("  [4]  Install Everything (BepInEx + mod)");
            Console.ForegroundColor = ConsoleColor.White;
            Console.WriteLine("  [5]  Launch ROUNDS");
            Console.ForegroundColor = ConsoleColor.DarkRed;
            Console.WriteLine("  [6]  Uninstall");
            Console.ForegroundColor = ConsoleColor.DarkGray;
            Console.WriteLine("  [Q]  Quit");
            Console.ResetColor();
            Console.WriteLine();
            Console.Write("  > ");
        }

        static void WaitForKey(string msg = "Press any key to continue...")
        {
            Console.ForegroundColor = ConsoleColor.DarkGray;
            Console.WriteLine($"\n  {msg}");
            Console.ResetColor();
            Console.ReadKey(true);
        }

        static void PrintSuccess(string msg)
        {
            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine($"  ✓ {msg}");
            Console.ResetColor();
        }

        static void PrintError(string msg)
        {
            Console.ForegroundColor = ConsoleColor.Red;
            Console.WriteLine($"  ✗ {msg}");
            Console.ResetColor();
        }

        static void PrintInfo(string msg)
        {
            Console.ForegroundColor = ConsoleColor.Gray;
            Console.WriteLine($"  · {msg}");
            Console.ResetColor();
        }

        // ── Detection ──────────────────────────────────────────────

        static void DetectInstallation()
        {
            if (!string.IsNullOrEmpty(roundsPath) && Directory.Exists(roundsPath))
                return; // Already set manually

            // Check default path
            if (Directory.Exists(DEFAULT_ROUNDS_PATH) &&
                File.Exists(Path.Combine(DEFAULT_ROUNDS_PATH, "Rounds.exe")))
            {
                roundsPath = DEFAULT_ROUNDS_PATH;
                UpdatePaths();
                return;
            }

            // Search Steam library folders
            string steamPath = @"C:\Program Files (x86)\Steam";
            string libFile = Path.Combine(steamPath, "steamapps", "libraryfolders.vdf");
            if (File.Exists(libFile))
            {
                try
                {
                    string content = File.ReadAllText(libFile);
                    // Parse "path" values from VDF
                    var matches = Regex.Matches(content, @"""path""\s+""([^""]+)""");
                    foreach (Match m in matches)
                    {
                        string libPath = m.Groups[1].Value.Replace(@"\\", @"\");
                        string candidate = Path.Combine(libPath, "steamapps", "common", "ROUNDS");
                        if (Directory.Exists(candidate) &&
                            File.Exists(Path.Combine(candidate, "Rounds.exe")))
                        {
                            roundsPath = candidate;
                            UpdatePaths();
                            return;
                        }
                    }
                }
                catch { }
            }
        }

        static void UpdatePaths()
        {
            bepinexPath = Path.Combine(roundsPath, "BepInEx");
            pluginsPath = Path.Combine(bepinexPath, "plugins");
        }

        static bool IsBepInExInstalled()
        {
            if (string.IsNullOrEmpty(roundsPath)) return false;
            // Check for winhttp.dll (BepInEx doorstop) and BepInEx folder
            return File.Exists(Path.Combine(roundsPath, "winhttp.dll")) &&
                   Directory.Exists(bepinexPath) &&
                   Directory.Exists(Path.Combine(bepinexPath, "core"));
        }

        static string GetModDllPath()
        {
            if (string.IsNullOrEmpty(pluginsPath) || !Directory.Exists(pluginsPath))
                return null;

            // Check subfolder first (standard install), then root plugins
            string subPath = Path.Combine(pluginsPath, "CompetitiveRounds", MOD_DLL_NAME);
            if (File.Exists(subPath)) return subPath;

            string rootPath = Path.Combine(pluginsPath, MOD_DLL_NAME);
            if (File.Exists(rootPath)) return rootPath;

            return null;
        }

        static string GetInstalledModVersion()
        {
            string dllPath = GetModDllPath();
            if (dllPath == null) return null;

            try
            {
                // The mod version is in the BepInPlugin attribute as a string literal,
                // not in AssemblyVersion. Scan the DLL bytes for our version pattern.
                byte[] bytes = File.ReadAllBytes(dllPath);
                string content = System.Text.Encoding.UTF8.GetString(bytes);

                // Custom attribute blobs in .NET metadata serialize string args as
                // length-prefixed UTF-8 in order. BepInPlugin(ModId, ModName, ModVersion)
                // stores them as: <len>"com.competitiverounds.mod" <len>"Competitive ROUNDS"
                // <len>"1.X.Y". Anchor on the ModName since it's unique to our DLL and
                // the ModVersion is GUARANTEED to be the next short string after it
                // (separated only by a 1-byte length prefix). Skips the dependent-
                // assembly version refs (netstandard 2.1.0, BepInEx 5.4.1901, etc.) that
                // the previous broad-window regex was picking up.
                var match = Regex.Match(content, @"Competitive ROUNDS.{0,2}(\d+\.\d{1,2}\.\d{1,2})");
                if (match.Success) return match.Groups[1].Value;
            }
            catch { }

            return "unknown";
        }

        // ── Actions ────────────────────────────────────────────────

        static void SetRoundsPath()
        {
            Console.Clear();
            PrintHeader();
            Console.WriteLine("  Enter the full path to your ROUNDS install folder:");
            Console.WriteLine("  (e.g., C:\\Program Files (x86)\\Steam\\steamapps\\common\\ROUNDS)");
            Console.WriteLine();
            Console.Write("  > ");
            string input = Console.ReadLine()?.Trim().Trim('"');

            if (string.IsNullOrEmpty(input))
                return;

            if (!Directory.Exists(input))
            {
                PrintError($"Directory not found: {input}");
                WaitForKey();
                return;
            }

            if (!File.Exists(Path.Combine(input, "Rounds.exe")))
            {
                PrintError("Rounds.exe not found in that directory.");
                WaitForKey();
                return;
            }

            roundsPath = input;
            UpdatePaths();
            PrintSuccess($"ROUNDS path set to: {roundsPath}");
            WaitForKey();
        }

        static void InstallBepInEx()
        {
            Console.Clear();
            PrintHeader();

            if (string.IsNullOrEmpty(roundsPath))
            {
                PrintError("ROUNDS path not set. Use option [1] first.");
                WaitForKey();
                return;
            }

            if (IsBepInExInstalled())
            {
                PrintSuccess("BepInEx is already installed — no action needed.");
                WaitForKey();
                return;
            }

            string tempZip = Path.Combine(Path.GetTempPath(), "BepInExPack_ROUNDS.zip");
            string tempDir = Path.Combine(Path.GetTempPath(), "BepInExPack_ROUNDS_extract");

            try
            {
                PrintInfo("Downloading BepInEx 5.4.1901 from Thunderstore...");
                using (var wc = new WebClient())
                {
                    wc.Headers.Add("User-Agent", "CompetitiveRoundsInstaller/1.0");
                    wc.DownloadFile(BEPINEX_URL, tempZip);
                }
                PrintSuccess("Download complete.");

                // Extract
                PrintInfo("Extracting...");
                if (Directory.Exists(tempDir))
                    Directory.Delete(tempDir, true);
                ZipFile.ExtractToDirectory(tempZip, tempDir);

                // Find the BepInExPack_ROUNDS subfolder inside the zip
                string packFolder = Path.Combine(tempDir, "BepInExPack_ROUNDS");
                if (!Directory.Exists(packFolder))
                {
                    // Try finding it
                    var dirs = Directory.GetDirectories(tempDir);
                    packFolder = dirs.FirstOrDefault(d =>
                        d.IndexOf("BepInEx", StringComparison.OrdinalIgnoreCase) >= 0) ?? tempDir;
                }

                // Copy contents to ROUNDS folder
                PrintInfo($"Installing to {roundsPath}...");
                CopyDirectory(packFolder, roundsPath);
                PrintSuccess("BepInEx installed successfully!");

                // Ensure plugins folder exists
                if (!Directory.Exists(pluginsPath))
                    Directory.CreateDirectory(pluginsPath);
            }
            catch (Exception ex)
            {
                PrintError($"Installation failed: {ex.Message}");
            }
            finally
            {
                try { if (File.Exists(tempZip)) File.Delete(tempZip); } catch { }
                try { if (Directory.Exists(tempDir)) Directory.Delete(tempDir, true); } catch { }
            }

            WaitForKey();
        }

        static void InstallOrUpdateMod()
        {
            Console.Clear();
            PrintHeader();

            if (string.IsNullOrEmpty(roundsPath))
            {
                PrintError("ROUNDS path not set. Use option [1] first.");
                WaitForKey();
                return;
            }

            if (!IsBepInExInstalled())
            {
                PrintError("BepInEx is not installed. Install it first (option [2]).");
                WaitForKey();
                return;
            }

            try
            {
                // Check latest version on GitHub
                PrintInfo("Checking latest version on GitHub...");
                string releaseJson;
                using (var wc = new WebClient())
                {
                    wc.Headers.Add("User-Agent", "CompetitiveRoundsInstaller/1.0");
                    releaseJson = wc.DownloadString(GITHUB_API_LATEST);
                }

                // Parse tag_name for version
                string latestTag = ExtractJsonValue(releaseJson, "tag_name") ?? "unknown";
                string latestVersion = latestTag.TrimStart('v', 'V');
                PrintInfo($"Latest release: {latestTag}");

                string currentVersion = GetInstalledModVersion();
                if (currentVersion != null)
                {
                    PrintInfo($"Installed version: v{currentVersion}");
                    if (currentVersion == latestVersion)
                    {
                        PrintSuccess("Already up to date!");
                        WaitForKey();
                        return;
                    }
                    Console.ForegroundColor = ConsoleColor.Yellow;
                    Console.WriteLine($"  Update available: v{currentVersion} → v{latestVersion}");
                    Console.ResetColor();
                }

                // Find the DLL asset download URL
                string dllUrl = FindDllAssetUrl(releaseJson);
                if (dllUrl == null)
                {
                    // No DLL asset — try the zip asset
                    string zipUrl = FindZipAssetUrl(releaseJson);
                    if (zipUrl != null)
                    {
                        PrintInfo("Downloading release zip...");
                        InstallFromZipRelease(zipUrl);
                    }
                    else
                    {
                        PrintError("Could not find a downloadable DLL or zip in the latest release.");
                        PrintInfo("Check: https://github.com/SidNDeed/SidsCompetitiveRounds/releases");
                    }
                    WaitForKey();
                    return;
                }

                // Download the DLL directly
                PrintInfo("Downloading CompetitiveRounds.dll...");

                // Use existing location if found, otherwise default to subfolder
                string existingPath = GetModDllPath();
                string modFolder = Path.Combine(pluginsPath, "CompetitiveRounds");
                string dllDest = existingPath ?? Path.Combine(modFolder, MOD_DLL_NAME);

                // Ensure target folder exists
                string destDir = Path.GetDirectoryName(dllDest);
                if (!Directory.Exists(destDir))
                    Directory.CreateDirectory(destDir);

                // Backup existing
                if (File.Exists(dllDest))
                {
                    string backup = dllDest + ".bak";
                    try { File.Copy(dllDest, backup, true); } catch { }
                }

                using (var wc = new WebClient())
                {
                    wc.Headers.Add("User-Agent", "CompetitiveRoundsInstaller/1.0");
                    wc.DownloadFile(dllUrl, dllDest);
                }

                PrintSuccess($"Competitive ROUNDS v{latestVersion} installed!");
                cachedLatestVersion = null; // refresh on next status display
            }
            catch (Exception ex)
            {
                PrintError($"Installation failed: {ex.Message}");
            }

            WaitForKey();
        }

        static void InstallEverything()
        {
            Console.Clear();
            PrintHeader();

            if (string.IsNullOrEmpty(roundsPath))
            {
                PrintError("ROUNDS path not set. Use option [1] first.");
                WaitForKey();
                return;
            }

            if (!IsBepInExInstalled())
            {
                InstallBepInEx();
                Console.Clear();
                PrintHeader();
            }
            else
            {
                PrintSuccess("BepInEx already installed — skipping.");
            }

            if (IsBepInExInstalled())
            {
                InstallOrUpdateMod();
            }
        }

        static void LaunchRounds()
        {
            if (string.IsNullOrEmpty(roundsPath))
            {
                PrintError("ROUNDS path not set.");
                WaitForKey();
                return;
            }

            try
            {
                Process.Start("steam://rungameid/1557740");
                PrintSuccess("Launching ROUNDS via Steam...");
                Thread.Sleep(1500);
            }
            catch
            {
                try
                {
                    string exe = Path.Combine(roundsPath, "Rounds.exe");
                    if (File.Exists(exe))
                    {
                        Process.Start(exe);
                        PrintSuccess("Launching ROUNDS...");
                        Thread.Sleep(1500);
                    }
                    else
                    {
                        PrintError("Rounds.exe not found.");
                        WaitForKey();
                    }
                }
                catch (Exception ex)
                {
                    PrintError($"Launch failed: {ex.Message}");
                    WaitForKey();
                }
            }
        }

        static void UninstallMenu()
        {
            Console.Clear();
            PrintHeader();

            if (string.IsNullOrEmpty(roundsPath))
            {
                PrintError("ROUNDS path not set. Use option [1] first.");
                WaitForKey();
                return;
            }

            Console.ForegroundColor = ConsoleColor.White;
            Console.WriteLine("  What would you like to uninstall?");
            Console.WriteLine();
            Console.WriteLine("  [1]  Competitive ROUNDS mod only (keep BepInEx)");
            Console.WriteLine("  [2]  Everything (BepInEx + mod)");
            Console.ForegroundColor = ConsoleColor.DarkGray;
            Console.WriteLine("  [Q]  Cancel");
            Console.ResetColor();
            Console.WriteLine();
            Console.Write("  > ");

            var key = Console.ReadKey(true).Key;
            switch (key)
            {
                case ConsoleKey.D1:
                case ConsoleKey.NumPad1:
                    UninstallMod();
                    break;
                case ConsoleKey.D2:
                case ConsoleKey.NumPad2:
                    UninstallEverything();
                    break;
            }
        }

        static void UninstallMod()
        {
            Console.WriteLine();
            string dllPath = GetModDllPath();
            if (dllPath == null)
            {
                PrintError("Competitive ROUNDS is not installed.");
                WaitForKey();
                return;
            }

            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine($"  This will delete: {dllPath}");
            Console.WriteLine("  Continue? (Y/N)");
            Console.ResetColor();
            if (Console.ReadKey(true).Key != ConsoleKey.Y) return;

            try
            {
                File.Delete(dllPath);

                // Remove subfolder if empty
                string dir = Path.GetDirectoryName(dllPath);
                if (dir != pluginsPath && Directory.Exists(dir) && Directory.GetFiles(dir).Length == 0)
                    Directory.Delete(dir);

                PrintSuccess("Competitive ROUNDS mod removed.");
                cachedLatestVersion = null;
            }
            catch (Exception ex)
            {
                PrintError($"Failed: {ex.Message}");
            }
            WaitForKey();
        }

        static void UninstallEverything()
        {
            Console.WriteLine();
            Console.ForegroundColor = ConsoleColor.Red;
            Console.WriteLine("  This will delete:");
            Console.ForegroundColor = ConsoleColor.White;
            Console.WriteLine($"    - {bepinexPath}\\  (entire folder)");
            Console.WriteLine($"    - {Path.Combine(roundsPath, "winhttp.dll")}");
            Console.WriteLine($"    - {Path.Combine(roundsPath, "doorstop_config.ini")}");
            Console.WriteLine($"    - {Path.Combine(roundsPath, ".doorstop_version")}");
            Console.ForegroundColor = ConsoleColor.Red;
            Console.WriteLine();
            Console.WriteLine("  ROUNDS will return to vanilla. Continue? (Y/N)");
            Console.ResetColor();
            if (Console.ReadKey(true).Key != ConsoleKey.Y) return;

            try
            {
                if (Directory.Exists(bepinexPath))
                {
                    Directory.Delete(bepinexPath, true);
                    PrintSuccess("BepInEx folder deleted.");
                }

                string[] filesToDelete = { "winhttp.dll", "doorstop_config.ini", ".doorstop_version" };
                foreach (var f in filesToDelete)
                {
                    string path = Path.Combine(roundsPath, f);
                    if (File.Exists(path))
                    {
                        File.Delete(path);
                        PrintInfo($"Deleted {f}");
                    }
                }

                PrintSuccess("Uninstall complete — ROUNDS is now vanilla.");
                cachedLatestVersion = null;
            }
            catch (Exception ex)
            {
                PrintError($"Failed: {ex.Message}");
                PrintInfo("Make sure ROUNDS is not running.");
            }
            WaitForKey();
        }

        // ── Helpers ────────────────────────────────────────────────

        static void InstallFromZipRelease(string zipUrl)
        {
            string tempZip = Path.Combine(Path.GetTempPath(), "CompetitiveRounds_release.zip");
            string tempDir = Path.Combine(Path.GetTempPath(), "CompetitiveRounds_extract");

            try
            {
                using (var wc = new WebClient())
                {
                    wc.Headers.Add("User-Agent", "CompetitiveRoundsInstaller/1.0");
                    wc.DownloadFile(zipUrl, tempZip);
                }

                if (Directory.Exists(tempDir))
                    Directory.Delete(tempDir, true);
                ZipFile.ExtractToDirectory(tempZip, tempDir);

                // Find the DLL in the extracted contents
                var dlls = Directory.GetFiles(tempDir, MOD_DLL_NAME, SearchOption.AllDirectories);
                if (dlls.Length > 0)
                {
                    string dest = Path.Combine(pluginsPath, MOD_DLL_NAME);
                    if (File.Exists(dest))
                        File.Copy(dest, dest + ".bak", true);
                    File.Copy(dlls[0], dest, true);
                    PrintSuccess("Competitive ROUNDS installed from release zip!");
                }
                else
                {
                    PrintError("CompetitiveRounds.dll not found in the release zip.");
                }
            }
            catch (Exception ex)
            {
                PrintError($"Zip install failed: {ex.Message}");
            }
            finally
            {
                try { if (File.Exists(tempZip)) File.Delete(tempZip); } catch { }
                try { if (Directory.Exists(tempDir)) Directory.Delete(tempDir, true); } catch { }
            }
        }

        static string FindDllAssetUrl(string json)
        {
            // Look for a .dll asset in the release
            var matches = Regex.Matches(json, @"""browser_download_url""\s*:\s*""([^""]+\.dll)""");
            foreach (Match m in matches)
            {
                string url = m.Groups[1].Value;
                if (url.IndexOf("CompetitiveRounds", StringComparison.OrdinalIgnoreCase) >= 0)
                    return url;
            }
            // Any .dll
            if (matches.Count > 0) return matches[0].Groups[1].Value;
            return null;
        }

        static string FindZipAssetUrl(string json)
        {
            var matches = Regex.Matches(json, @"""browser_download_url""\s*:\s*""([^""]+\.zip)""");
            foreach (Match m in matches)
                return m.Groups[1].Value;
            return null;
        }

        static string ExtractJsonValue(string json, string key)
        {
            var match = Regex.Match(json, $@"""{key}""\s*:\s*""([^""]+)""");
            return match.Success ? match.Groups[1].Value : null;
        }

        static void CopyDirectory(string source, string dest)
        {
            if (!Directory.Exists(dest))
                Directory.CreateDirectory(dest);

            foreach (string file in Directory.GetFiles(source))
            {
                string destFile = Path.Combine(dest, Path.GetFileName(file));
                File.Copy(file, destFile, true);
            }

            foreach (string dir in Directory.GetDirectories(source))
            {
                string destDir = Path.Combine(dest, Path.GetDirectoryName(dir + Path.DirectorySeparatorChar)
                    .Split(Path.DirectorySeparatorChar).Last());
                CopyDirectory(dir, destDir);
            }
        }
    }
}
