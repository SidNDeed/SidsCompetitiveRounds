# Sid's Competitive ROUNDS — Installer

## What It Does

This installer automatically sets up BepInEx and the Competitive ROUNDS mod for you. No manual file copying needed.

## How To Use

1. Download and run `CompetitiveRoundsInstaller.exe`
2. It will automatically find your ROUNDS install folder
3. Press **[4]** to install everything
4. Press **[5]** to launch ROUNDS
5. That's it — you're ready to play

## What Each Option Does

- **[1] Set ROUNDS install path** — Only needed if the installer can't find ROUNDS automatically. It checks the default Steam location and any additional Steam library folders.
- **[2] Install BepInEx** — Downloads BepInEx 5.4.1901 (the mod framework) from Thunderstore and installs it to your ROUNDS folder. If BepInEx is already installed, it skips this step.
- **[3] Install / Update Competitive ROUNDS mod** — Downloads the latest CompetitiveRounds.dll from GitHub. If you already have the mod installed, it compares your version to the latest release and only downloads if there's an update. Your old DLL is backed up automatically.
- **[4] Install Everything** — Does [2] then [3] in one step. This is what most people should use.
- **[5] Launch ROUNDS** — Launches ROUNDS through Steam so the Steam overlay works normally.
- **[6] Uninstall** — Choose to remove just the mod (keeps BepInEx for other mods) or remove everything (BepInEx + mod, returns ROUNDS to vanilla). Asks for confirmation before deleting anything.

## Status Display

When you launch the installer, it shows you the current state:

```
ROUNDS Path:     C:\Program Files (x86)\Steam\steamapps\common\ROUNDS
BepInEx:         INSTALLED
Competitive DLL: v1.18.4  (up to date)
```

If an update is available, it tells you:

```
Competitive DLL: v1.18.2  (latest: v1.18.4 — update available!)
```

## Updating The Mod

When a new version comes out, just run the installer again and press **[3]**. It checks the latest version on GitHub and updates if needed.

## Uninstalling

Use option **[6]** in the installer, or manually delete these from your ROUNDS folder:
- The `BepInEx` folder
- `winhttp.dll`
- `doorstop_config.ini`
- `.doorstop_version`

ROUNDS will go back to vanilla.
