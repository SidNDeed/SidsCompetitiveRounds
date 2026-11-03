# a3.py: the A3 inventory (ruling FRAME-TIME-ROUND-R1-A1, route D; METHOD-V4.1 section 0; ruling FRAME-TIME-ROUND-R2):
# one row per survivor read live in tools/frametime/SURVIVORS.md (each S row exactly once; test_ft_parse and
# survivor_sweep.py check the two agree): (name, survivor id, "dependent" | "drained" | "zero", reason, proof).
# A row's kind is DEFAULT-DENY (ruling FRAME-TIME-ROUND-R2 (1)):
#   zero       only when survivor_sweep.py proves that no write site of any of the row's fields is reachable in the
#              measured span (proof "sweep:no-live-write": the sweep re-derives it on every run and fails when a field
#              of the row has a write inside a live member), or an executed probe shows the fields unwritten at every
#              point's first live frame (proof "probe:..."). It adds nothing.
#   drained    a queue or ring the build probes EMPTY at the boundary of every point's first live frame
#              (FtA3.PointStart; proof "probe:a3drain"): its a3drain line must report nonempty 0 at every point. It
#              adds nothing because nothing written before a point reaches that point's live reads.
#   dependent  every other row: registered in FtA3 under the same name, counted at every live reader member (the sweep
#              checks each carries FtA3.Read(FtA3.<name>)), its a3 line required in every measured game; it adds
#              r_k_max x d_k to A3. The reason of a former zero row says why it is no longer zero. Proof
#              "live:executed", the only proof a dependent row may carry (ruling FRAME-TIME-ROUND-R5, which retires the
#              scratch game-start calibration of every dependent row after five scratch designs failed to reach the
#              costliest content): every live reader method is timed in its own body in game (FtA3.TEnter/TExit), the
#              build writes the row's executed calibration line per game, d_k is read from BOTH seats' logs
#              (ft_parse.a3_live), a row with no executed read in any measured game is withheld, and no planning value
#              and no withheld line may stand in for it.
_LIVE = "default-deny (ruling FRAME-TIME-ROUND-R2 (1)): the sweep finds its fields written in live members, so it is no zero row; "
A3 = [
    ("CE_Top", "S01", "dependent", "", "live:executed"),
    ("CE_Ht", "S02", "dependent", "", "live:executed"),
    ("CE_Ping", "S03", "dependent", "", "live:executed"),
    ("CE_lhat_cache", "S04", "dependent", _LIVE + "DrainAim's cache test and read, calibrated as that test on scratch scalars", "live:executed"),
    ("CE_Pos", "S05", "dependent", "", "live:executed"),
    ("CE_Recent", "S06", "dependent", "", "live:executed"),
    ("CE_Wait", "S07", "drained", "DrainWaits runs on the non-live frames between points and every carried entry is due one frame later", "probe:a3drain"),
    ("CE_Rings", "S08", "drained", "the Mask/Aim/Res/Pack drains run TICK_ROWS_CAP rows per frame on the non-live frames between points too", "probe:a3drain"),
    ("CE_anchor", "S09", "dependent", _LIVE + "the anchor and segment slots and their CappedMap, counted per live reader", "live:executed"),
    ("CE_Gun", "S10", "drained", "PointEnd drains the whole gun ring (DrainVolleys with RING_CAP)", "probe:a3drain"),
    ("CE_B5c", "S11", "dependent", "", "live:executed"),
    ("CE_counters", "S12", "dependent", _LIVE + "indexed counter increments, counted per live reader", "live:executed"),
    ("CE_scratch", "S13", "dependent", _LIVE + "per-hook scratch rows and scalars, counted per live reader", "live:executed"),
    ("CE_gun_scalars", "S14", "dependent", _LIVE + "per-gun scalars, counted per live reader", "live:executed"),
    ("CE_gun_account", "S15", "dependent", _LIVE + "GunAccount appends and CloseCycle, counted per live reader", "live:executed"),
    ("CE_aimset", "S16", "dependent", _LIVE + "AimSet.Add, counted per call", "live:executed"),
    ("CE_capture", "S17", "dependent", _LIVE + "process and capture scalars, counted per live reader", "live:executed"),
    ("CE_perf_probe", "S18", "dependent", _LIVE + "CombatEvidencePerf.Frame calls FtA3.Read on every ON live frame before it returns disabled (FtArm arms only with Debug.CombatEvidencePerfProbe off), so a sitting counts one read per ON live frame (round-3 MEDIUM a3.py:35); the histogram writes need the probe on", "live:executed"),
    ("SE_Hw", "S19", "dependent", "", "live:executed"),
    ("SE_Logs", "S20", "dependent", "", "live:executed"),
    ("SE_ordinals", "S21", "dependent", _LIVE + "Ordinals.Next with its eviction at KEEP (round-2 HIGH 3)", "live:executed"),
    ("SE_frames", "S22", "dependent", _LIVE + "RPC, block and hit frame stacks, counted per live reader", "live:executed"),
    ("SE_scalars", "S23", "dependent", _LIVE + "per-game scalars and the seat Rng, counted per live reader", "live:executed"),
    ("HE_Flush", "S24", "drained", "HoldPoint fills the flush queue at the point end and the next Drain empties it", "probe:a3drain"),
    ("HE_game", "S25", "dependent", _LIVE + "the per-actor CappedMap and GameTally scalars, counted per live reader", "live:executed"),
    ("HE_point", "S26", "dependent", _LIVE + "PointTally adds, their time lists and the pair scans, counted per live reader", "live:executed"),
    ("HE_sender", "S27", "dependent", _LIVE + "the RPC-scoped sender, counted per live reader", "live:executed"),
    ("PE_Rec", "S28", "drained", "DrainOwn sets _recCount to 0 on the first tick after the point end", "probe:a3drain"),
    ("PE_map", "S29", "dependent", _LIVE + "PointEvidence's CappedMap, counted per live reader", "live:executed"),
    ("IC_Rpc", "S30", "dependent", "", "live:executed"),
    ("IC_Clock", "S31", "dependent", "", "live:executed"),
    ("IC_scalars", "S32", "dependent", _LIVE + "package state, RPC frames and cost counters, counted per live reader", "live:executed"),
    ("IC_point", "S33", "dependent", _LIVE + "the point objects CurO / CurS, counted per live reader", "live:executed"),
    ("IC_game", "S34", "dependent", _LIVE + "per-game scalars, counted per live reader", "live:executed"),
    ("CD_notes", "S35", "dependent", _LIVE + "the fault notes and the census flag, counted per live reader", "live:executed"),
    ("PB_printed", "S36", "dependent", _LIVE + "the printed-peer Dictionary and scan scalars, counted per live reader", "live:executed"),
    ("HE_hitset", "S37", "dependent", "", "live:executed"),
]
