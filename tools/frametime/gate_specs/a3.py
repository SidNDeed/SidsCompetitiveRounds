# a3.py: the A3 inventory (ruling FRAME-TIME-ROUND-R1-A1, route D; METHOD-V4.1 section 0): one row per survivor
# read live in tools/frametime/SURVIVORS.md (S01 to S36, each exactly once; test_ft_parse checks the two agree):
# (name, survivor id, "dependent" | "drained" | "zero", reason).
#   dependent  its live reads cost more or less with its content: registered in FtA3 under the same name (refill and
#              capacity from the code constants), its a3 line required in every measured game and its calibration at
#              every game start; it adds r_k_max x d_k to A3.
#   drained    a queue or ring SURVIVORS.md finds emptied between points: the build probes it EMPTY at the boundary
#              of every point's first live frame (FtA3.PointStart) and its a3drain line must report nonempty 0; it
#              adds nothing because nothing written before a point reaches that point's live reads.
#   zero       its live reads cost the same whatever its content; the reason says why (from SURVIVORS.md's
#              READ-COST DEPENDENCE column).
A3 = [
    ("CE_Top", "S01", "dependent", ""),
    ("CE_Ht", "S02", "dependent", ""),
    ("CE_Ping", "S03", "dependent", ""),
    ("CE_lhat_cache", "S04", "zero", "DrainAim does one compare and one int read per frame whatever the values; the value feeds S05's window, which CE_Pos calibrates"),
    ("CE_Pos", "S05", "dependent", ""),
    ("CE_Recent", "S06", "dependent", ""),
    ("CE_Wait", "S07", "drained", "DrainWaits runs on the non-live frames between points and every carried entry is due one frame later"),
    ("CE_Rings", "S08", "drained", "the Mask/Aim/Res/Pack drains run TICK_ROWS_CAP rows per frame on the non-live frames between points too"),
    ("CE_anchor", "S09", "zero", "every live read indexes one slot (a CappedMap probe, constructed at capacity) or one key pid & 255; no live loop walks these tables"),
    ("CE_Gun", "S10", "drained", "PointEnd drains the whole gun ring (DrainVolleys with RING_CAP)"),
    ("CE_B5c", "S11", "dependent", ""),
    ("CE_counters", "S12", "zero", "each live access is one indexed increment; the flagged loops iterate the mask bits or the rings (S08), not these arrays"),
    ("CE_scratch", "S13", "zero", "scalar reads and writes and fixed-width scratch rows fully overwritten before each read"),
    ("CE_gun_scalars", "S14", "zero", "scalar reads and writes per gun hook"),
    ("CE_gun_account", "S15", "zero", "O(1) appends below fixed per-group caps; CloseCycle's loop is GAP_COUNT iterations whatever the content"),
    ("CE_aimset", "S16", "zero", "AimSet.Add is one bin search over a constant edge table plus scalar sums"),
    ("CE_capture", "S17", "zero", "scalar reads and one indexed increment per hook"),
    ("CE_perf_probe", "S18", "zero", "inert unless Debug.CombatEvidencePerfProbe is menu or match, and FtArm.Common refuses to arm then (perf_probe), so no sitting game runs with it on"),
    ("SE_Hw", "S19", "dependent", ""),
    ("SE_Logs", "S20", "dependent", ""),
    ("SE_ordinals", "S21", "zero", "Ordinals.Next is one Dictionary probe plus a ring eviction, O(1); the Dictionary is constructed at KEEP and never grows"),
    ("SE_frames", "S22", "zero", "push, pop and top-of-stack reads, O(1); a frame is written before it is read"),
    ("SE_scalars", "S23", "zero", "scalar reads and one indexed increment per hook; _impDistinct's HashSet growth is counted under SE_Logs"),
    ("HE_Flush", "S24", "drained", "HoldPoint fills the flush queue at the point end and the next Drain empties it"),
    ("HE_game", "S25", "zero", "CappedMap TryGetValue / Admit (constructed at capacity), scalar increments and a capped HashSet Add"),
    ("HE_point", "S26", "zero", "the tallies are new each point, so nothing an earlier point wrote is read; their loops run in Drain after the point end"),
    ("HE_sender", "S27", "zero", "one int read"),
    ("PE_Rec", "S28", "drained", "DrainOwn sets _recCount to 0 on the first tick after the point end"),
    ("PE_map", "S29", "zero", "CappedMap Set / TryGetValue, O(1); _before is cleared in each Saw frame"),
    ("IC_Rpc", "S30", "dependent", ""),
    ("IC_Clock", "S31", "dependent", ""),
    ("IC_scalars", "S32", "zero", "scalar reads and one indexed increment per package; Survey.Step returns at its combat gate"),
    ("IC_point", "S33", "zero", "live code reaches only CurO / CurS, new at each point start; PointPkg loops over the constant rung table"),
    ("IC_game", "S34", "zero", "scalar reads"),
    ("CD_notes", "S35", "zero", "DrainNotes loops the COLLECTORS slots every tick and nulls a note once logged; EnsureCensusDump reads one flag"),
    ("PB_printed", "S36", "zero", "Tick runs once per SCAN_INTERVAL_S with one Dictionary probe per other player; the loop is over the room's players"),
]
