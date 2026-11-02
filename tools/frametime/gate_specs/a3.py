# a3.py: the A3 inventory (ruling FRAME-TIME-ROUND-R1-A1, route D; METHOD-V4.1 section 0), one row per class (iii)
# survivor of tools/frametime/SURVIVORS.md: (name, survivor id, "dependent" | "zero", reason). A "dependent" row's
# live reads cost more or less with its content: the build registers it in FtA3 (capacity from the code constant,
# FtA3.RegisterAll, same name) and the parser requires its a3 line in every measured game and its calibration at
# every game start. A "zero" row's live reads cost the same whatever its content; the reason says why, and it adds
# nothing to A3.
# PROVISIONAL: CombatEvidence Top and Ht only, until the extended sweep's SURVIVORS.md lands; replaced from it.
A3 = [
    ("CE_Top", "S01", "dependent", ""),
    ("CE_Ht", "S02", "dependent", ""),
]
