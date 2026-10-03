"""Combat evidence: the public description of one ranked game's combat records.

What this module holds, on the server side, in one place:

  * the WIRE LAYOUT of the combat record: the one record bound, every list
    cap, every field's bounds, the budgeter's tiers (COMBAT_WIRE, pinned by
    the no-tunables guard);
  * the reference byte BUDGETER and its maximum-width proof (the client must
    produce byte-identical output; a shared fixture set pins it);
  * the CYCLE REBUILD of each gun from that gun's shot and refill stream;
  * the PAIRING of the two seats' records of one game and one canonical seat
    pair, with what one record alone can and cannot show;
  * the public MEASURES over that pairing, registered in the review
    vocabulary with per-entry semantic fingerprints;
  * the reference INTEGRATOR of an unsteered projectile and the residual
    encoding the bullet-path evidence uses;
  * the descriptive SECTIONS a seat fills only when the whole room carries
    the capability (the `caps` bits): each push applied by a hit, the owner's
    own changes of its projectiles' velocity and target-bounce selections,
    the chain of a hit from the shooter's decision to the victim's screen,
    and each boundary death with the hits that preceded it. A section the
    record did not fill reads NOT-RUN (not collected), never empty-and-fine.

Everything here DESCRIBES. The comparisons it makes (rounds fired beyond a
magazine and its regeneration, a refill sooner than the stated reload) are
the game's own rule arithmetic, used to label a cycle and to decide what a
full record keeps; none of them opens a review item. Which description meets
which operator, at what value and with what words, is a rules revision that
is not part of this repository. A measure whose input is missing, trimmed,
or of an incompatible measurement version answers None and the view names
the reason (NOT-RUN); it never answers zero and never passes.
"""

from __future__ import annotations

import json
import math
import struct
from collections import Counter

import review_measures as rm

# The wire layout. Field tuples are (name, lowest, highest); every value on
# the wire is an integer inside its bounds, every string ASCII. Kinds:
#   int, enum            a scalar
#   row                  one fixed-length integer array
#   rows                 a fixed number of fixed-length integer arrays
#   hist                 a fixed-length integer array (histogram bins)
#   list                 at most `cap` rows; `tier` names the budgeter tier
#                        (zero: never trimmed, only truncated to its cap)
#   groups               at most `cap` cycle groups [header, shots, regens]
#   omit                 entries removed per list, keys in list order
COMBAT_WIRE = {
    "contract": 1,
    "schema": 1,
    "consts_known": (1,),
    "record_max_bytes": 16384,
    "seat_hourly_cap": 40,
    "sign_prefix": "combat-evidence:v1:",
    "collectors": 13,
    "gap_count": 3,
    "group_parts": 3,
    "spec": (
        ("schema", ("int", 1, 1)),
        ("consts", ("int", 1, 999)),
        ("caps", ("int", 0, 15)),
        ("t0", ("int", -2147483648, 2147483647)),
        ("t0_src", ("enum", ("m", "o"))),
        ("frame_p50_us", ("int", 0, 1000000)),
        ("cost", ("rows", 13, (("calls", 0, 99999999), ("total_us", 0, 2147483647),
                               ("max_us", 0, 99999999), ("faults", 0, 99999999)))),
        ("l_hat", ("int", -1, 600000)),
        ("tb_tot", ("row", (("real", 0, 99999999), ("game", 0, 99999999),
                            ("srv", -99999999, 99999999), ("frames", 0, 99999999),
                            ("slow", 0, 99999999), ("ramp", 0, 99999999), ("clamp", 0, 99999999),
                            ("base_changes", 0, 9999), ("points", 0, 9999)))),
        ("tb", ("list", 27, 3, (("pt", 0, 99), ("ps", -2147483648, 2147483647),
                                ("real", 0, 3600000), ("game", 0, 3600000),
                                ("srv", -3600000, 3600000), ("frames", 0, 1000000),
                                ("slow", 0, 3600000), ("ramp", 0, 3600000), ("clamp", 0, 3600000),
                                ("dt_med_us", 0, 9999999), ("dt_max_us", 0, 99999999),
                                ("base", 0, 10000)))),
        ("a1s", ("hist", 16, 0, 99999)),
        ("a1p", ("hist", 16, 0, 99999)),
        ("a1m", ("hist", 16, 0, 99999)),
        ("a1n", ("hist", 16, 0, 99999)),
        ("a1sum", ("rows", 4, (("n", 0, 99999), ("mean", -3142, 3142), ("sd", 0, 3142),
                               ("no_sight", 0, 99999)))),
        ("rx_s", ("list", 48, 1, (("onset", -2147483648, 2147483647), ("aim_on", -1, 600000),
                                  ("first", -1, 600000), ("err", 0, 3142)))),
        ("rx_o", ("list", 48, 1, (("onset", -2147483648, 2147483647), ("aim_on", -1, 600000),
                                  ("first", -1, 600000), ("err", 0, 3142)))),
        ("gun_s", ("list", 10, 0, (("pt", 0, 99), ("mag", 1, 90), ("rt", 0, 600000),
                                   ("rta", -600000, 600000), ("rtm", 0, 1000000), ("rexp", 0, 600000),
                                   ("as", 0, 600000), ("mult", 0, 1000000), ("cexp", 0, 600000),
                                   ("nproj", 0, 999), ("bursts", 0, 999), ("tbb", 0, 600000),
                                   ("regen", 0, 1000000), ("auto", 0, 1), ("refresh", 0, 1),
                                   ("charge", 0, 1), ("lock", 0, 1), ("spr", 0, 3142),
                                   ("tmpl", 1, 99)))),
        ("gun_o", ("list", 10, 0, (("pt", 0, 99), ("mag", 1, 90), ("rt", 0, 600000),
                                   ("rta", -600000, 600000), ("rtm", 0, 1000000), ("rexp", 0, 600000),
                                   ("as", 0, 600000), ("mult", 0, 1000000), ("cexp", 0, 600000),
                                   ("nproj", 0, 999), ("bursts", 0, 999), ("tbb", 0, 600000),
                                   ("regen", 0, 1000000), ("auto", 0, 1), ("refresh", 0, 1),
                                   ("charge", 0, 1), ("lock", 0, 1), ("spr", 0, 3142),
                                   ("tmpl", 1, 99)))),
        ("tot_s", ("row", (("cycles", 0, 99999), ("volleys", 0, 9999999), ("units", 0, 9999999),
                           ("noammo", 0, 9999999), ("separate", 0, 9999999), ("gate", 0, 9999999),
                           ("emit", 0, 9999999), ("atk_msg", 0, 9999999), ("atk_noinit", 0, 9999999),
                           ("inits_rl", 0, 9999999), ("why_over_mag", 0, 99999),
                           ("why_in_reload", 0, 99999), ("why_short_gap", 0, 99999),
                           ("why_found_reloading", 0, 99999), ("why_gate_reloading", 0, 99999),
                           ("sum_excess", 0, 9999999), ("gap_minus_rexp_min", -600001, 600000),
                           ("cx_n", 0, 99999), ("cx_volleys", 0, 9999999), ("cx_units", 0, 9999999),
                           ("rf_idle", 0, 99999)))),
        ("tot_o", ("row", (("cycles", 0, 99999), ("volleys", 0, 9999999), ("units", 0, 9999999),
                           ("noammo", 0, 9999999), ("separate", 0, 9999999), ("gate", 0, 9999999),
                           ("emit", 0, 9999999), ("atk_msg", 0, 9999999), ("atk_noinit", 0, 9999999),
                           ("inits_rl", 0, 9999999), ("why_over_mag", 0, 99999),
                           ("why_in_reload", 0, 99999), ("why_short_gap", 0, 99999),
                           ("why_found_reloading", 0, 99999), ("why_gate_reloading", 0, 99999),
                           ("sum_excess", 0, 9999999), ("gap_minus_rexp_min", -600001, 600000),
                           ("cx_n", 0, 99999), ("cx_volleys", 0, 9999999), ("cx_units", 0, 9999999),
                           ("rf_idle", 0, 99999)))),
        ("ivl_s", ("list", 27, 0, (("pt", 0, 99), ("gmin", -1, 600000), ("cexp_min", -1, 600000),
                                   ("vmax", 0, 9999), ("vexp", 0, 9999), ("refreshes", 0, 9999)))),
        ("ivl_o", ("list", 27, 0, (("pt", 0, 99), ("gmin", -1, 600000), ("cexp_min", -1, 600000),
                                   ("vmax", 0, 9999), ("vexp", 0, 9999), ("refreshes", 0, 9999)))),
        ("cx_s", ("list", 24, 0, (("s0", -2147483648, 2147483647), ("units", 0, 9999),
                                  ("vol", 0, 9999), ("mag", 1, 90), ("regen", 0, 9999),
                                  ("exh", -1, 600000), ("in_rl", 0, 9999), ("tail", 0, 9999),
                                  ("gap_first", -1, 600000), ("gap_second", -1, 600000),
                                  ("gap_third", -1, 600000), ("rexp", 0, 600000), ("end", 0, 4),
                                  ("why", 0, 31)))),
        ("cx_o", ("list", 24, 0, (("s0", -2147483648, 2147483647), ("units", 0, 9999),
                                  ("vol", 0, 9999), ("mag", 1, 90), ("regen", 0, 9999),
                                  ("exh", -1, 600000), ("in_rl", 0, 9999), ("tail", 0, 9999),
                                  ("gap_first", -1, 600000), ("gap_second", -1, 600000),
                                  ("gap_third", -1, 600000), ("rexp", 0, 600000), ("end", 0, 4),
                                  ("why", 0, 31)))),
        ("sh_s", ("groups", 160, 3,
                  (("s0", -2147483648, 2147483647), ("pid0", 0, 2147483647), ("n", 1, 99999),
                   ("pt", 0, 99), ("end", 0, 4), ("src", 0, 2), ("amt", -1, 999),
                   ("st_end", -2147483648, 2147483647), ("rl_g", -1, 600000), ("rl_s", -1, 600000),
                   ("rl_r", -1, 600000), ("rg", 0, 99999), ("nrg", 0, 99999)),
                  32,
                  (("dpid", -2147483647, 2147483647), ("dt", -600000, 600000),
                   ("ammo_before", -999, 999), ("reloading", 0, 1), ("counter", -1, 600000),
                   ("rep", -1, 999), ("since", -1, 600000), ("fl", 0, 31)),
                  32,
                  (("k", 0, 99999), ("amt", 1, 999), ("st", -2147483648, 2147483647),
                   ("gap_g", -1, 600000), ("gap_s", -1, 600000), ("gap_r", -1, 600000)))),
        ("sh_o", ("groups", 160, 3,
                  (("s0", -2147483648, 2147483647), ("pid0", 0, 2147483647), ("n", 1, 99999),
                   ("pt", 0, 99), ("end", 0, 4), ("src", 0, 2), ("amt", -1, 999),
                   ("st_end", -2147483648, 2147483647), ("rl_g", -1, 600000), ("rl_s", -1, 600000),
                   ("rl_r", -1, 600000), ("rg", 0, 99999), ("nrg", 0, 99999)),
                  32,
                  (("dpid", -2147483647, 2147483647), ("dt", -600000, 600000),
                   ("ammo_before", -999, 999), ("reloading", 0, 1), ("counter", -1, 600000),
                   ("am", -1, 600000)),
                  32,
                  (("k", 0, 99999), ("amt", 1, 999), ("st", -2147483648, 2147483647),
                   ("gap_g", -1, 600000), ("gap_s", -1, 600000), ("gap_r", -1, 600000)))),
        ("p3n", ("row", (("seen", 0, 9999999), ("steer", 0, 9999999), ("hits_checked", 0, 9999999),
                         ("edge", 0, 9999999), ("target", 0, 9999999), ("sync", 0, 9999999),
                         ("evicted", 0, 9999999)))),
        ("p3dp0", ("hist", 14, 0, 99999)),
        ("p3an0", ("hist", 14, 0, 99999)),
        ("p3dp1", ("hist", 14, 0, 99999)),
        ("p3an1", ("hist", 14, 0, 99999)),
        ("p3hm", ("hist", 10, 0, 99999)),
        ("p3self", ("row", (("own", 0, 9999999), ("steer_a", 0, 9999999), ("steer_b", 0, 9999999),
                            ("steer_c", 0, 9999999), ("steer_d", 0, 9999999),
                            ("steer_e", 0, 9999999), ("steer_f", 0, 9999999),
                            ("steer_g", 0, 9999999), ("steer_h", 0, 9999999),
                            ("own_target_bounces", 0, 9999999)))),
        ("p3top", ("list", 32, 1, (("pid", 0, 2147483647), ("s_rel", -2147483648, 2147483647),
                                   ("d_perp", 0, 9999999), ("d_along", -9999999, 9999999),
                                   ("ang", 0, 3142), ("dt", 0, 600000), ("speed", 0, 999999),
                                   ("mask", 0, 255)))),
        ("p3tb", ("list", 32, 1, (("pid", 0, 2147483647), ("s_init", -2147483648, 2147483647),
                                  ("s_rel", -2147483648, 2147483647),
                                  ("gap", -1, 600000), ("has_retarget", 0, 1), ("ang_to_me", 0, 3142)))),
        ("p3ht", ("list", 16, 1, (("pid", 0, 2147483647), ("s_rel", -2147483648, 2147483647),
                                  ("ratio_pm", 0, 99999), ("n", 0, 99999)))),
        ("b5_tot", ("row", (("own_blocks", 0, 9999999), ("other_blocks", 0, 9999999),
                            ("own_refused", 0, 9999999), ("own_gaps_below_cd", 0, 9999999),
                            ("other_gaps_below_cd", 0, 9999999), ("copy_starts_failed", 0, 9999999),
                            ("contacts", 0, 9999999), ("contacts_in_own_window", 0, 9999999)))),
        ("b5_s", ("list", 80, 2, (("tb", -2147483648, 2147483647), ("kind", 0, 9), ("ord", 0, 255),
                                  ("press", -600000, 600000), ("open", -600000, 600000),
                                  ("len", -1, 600000), ("len_g", -1, 600000), ("reopen", 0, 1),
                                  ("scale_pm", 0, 10000), ("cd", 0, 600000), ("gap_prev", -1, 600000),
                                  ("fr", 0, 60000)))),
        ("b5_o", ("list", 80, 2, (("tb", -2147483648, 2147483647), ("kind", 0, 9), ("ord", 0, 255),
                                  ("ta", -600000, 600000), ("open_c", -600000, 600000),
                                  ("started", 0, 1), ("len_c", -1, 600000), ("len_cg", -1, 600000),
                                  ("reopen_c", 0, 1), ("o_pred", -600000, 600000), ("cd_c", 0, 600000),
                                  ("gap_prev_s", -1, 600000), ("fr", 0, 60000)))),
        ("b5_h", ("list", 80, 1, (("path", 0, 1), ("stamp", -2147483648, 2147483647),
                                  ("pid", 0, 2147483647), ("s_init", -2147483648, 2147483647),
                                  ("cord", 0, 255), ("ord", 0, 255), ("since_ms", -1, 600000),
                                  ("pred_since", -600000, 600000)))),
        ("b5_c", ("list", 64, 2, (("pid", 0, 2147483647), ("s_init", -2147483648, 2147483647),
                                  ("cord", 0, 255), ("tc", -2147483648, 2147483647),
                                  ("since_c", -1, 600000), ("h_stamp", -2147483648, 2147483647),
                                  ("own_since", -2, 600000)))),
        ("b5_r", ("list", 32, 2, (("rel", -2147483648, 2147483647), ("since_prev", -1, 600000),
                                  ("cd", 0, 600000)))),
        ("r_tot", ("row", (("push_own", 0, 9999999), ("push_other", 0, 9999999),
                           ("vchg", 0, 9999999), ("bsel", 0, 9999999), ("chain_own", 0, 9999999),
                           ("chain_other", 0, 9999999), ("death_own", 0, 9999),
                           ("death_other", 0, 9999)))),
        ("push_s", ("list", 64, 2, (("pid", 0, 2147483647), ("s_init", -2147483648, 2147483647),
                                    ("cord", 0, 255), ("tc", -2147483648, 2147483647),
                                    ("fx", -99999999, 99999999), ("fy", -99999999, 99999999),
                                    ("mass", 0, 99999999),
                                    ("vbx", -9999999, 9999999), ("vby", -9999999, 9999999),
                                    ("vax", -9999999, 9999999), ("vay", -9999999, 9999999),
                                    ("pbx", -9999999, 9999999), ("pby", -9999999, 9999999),
                                    ("pax", -9999999, 9999999), ("pay", -9999999, 9999999)))),
        ("push_o", ("list", 64, 2, (("pid", 0, 2147483647), ("s_init", -2147483648, 2147483647),
                                    ("cord", 0, 255), ("tc", -2147483648, 2147483647),
                                    ("fx", -99999999, 99999999), ("fy", -99999999, 99999999),
                                    ("mass", 0, 99999999),
                                    ("vbx", -9999999, 9999999), ("vby", -9999999, 9999999),
                                    ("vax", -9999999, 9999999), ("vay", -9999999, 9999999),
                                    ("pbx", -9999999, 9999999), ("pby", -9999999, 9999999),
                                    ("pax", -9999999, 9999999), ("pay", -9999999, 9999999)))),
        ("vchg", ("list", 96, 1, (("pid", 0, 2147483647), ("s_init", -2147483648, 2147483647),
                                  ("stamp", -2147483648, 2147483647), ("cause", 1, 63),
                                  ("ovx", -9999999, 9999999), ("ovy", -9999999, 9999999),
                                  ("nvx", -9999999, 9999999), ("nvy", -9999999, 9999999)))),
        ("bsel", ("list", 32, 1, (("pid", 0, 2147483647), ("s_init", -2147483648, 2147483647),
                                  ("stamp", -2147483648, 2147483647), ("target", 0, 2),
                                  ("d_self", -1, 9999999), ("los_self", -1, 1),
                                  ("d_other", -1, 9999999), ("los_other", -1, 1)))),
        ("ch_s", ("list", 64, 2, (("pid", 0, 2147483647), ("s_init", -2147483648, 2147483647),
                                  ("cord", 0, 255), ("t_rcv", -2147483648, 2147483647),
                                  ("t_dmg_rcv", -2147483648, 2147483647),
                                  ("t_hp", -2147483648, 2147483647),
                                  ("t_frame", -2147483648, 2147483647), ("hp_d", -99999, 99999)))),
        ("ch_o", ("list", 64, 2, (("pid", 0, 2147483647), ("s_init", -2147483648, 2147483647),
                                  ("cord", 0, 255), ("t_dec", -2147483648, 2147483647),
                                  ("t_msg", -2147483648, 2147483647),
                                  ("t_dmg", -2147483648, 2147483647)))),
        ("bd_s", ("list", 16, 2, (("ord", 0, 255), ("stamp", -2147483648, 2147483647),
                                  ("cause", 0, 3), ("edge", 0, 4),
                                  ("px", -9999999, 9999999), ("py", -9999999, 9999999),
                                  ("vx", -9999999, 9999999), ("vy", -9999999, 9999999),
                                  ("h1_pid", -1, 2147483647), ("h1_s_init", -2147483648, 2147483647),
                                  ("h1_cord", -1, 255), ("h1_age", -1, 600000),
                                  ("h2_pid", -1, 2147483647), ("h2_s_init", -2147483648, 2147483647),
                                  ("h2_cord", -1, 255), ("h2_age", -1, 600000),
                                  ("h3_pid", -1, 2147483647), ("h3_s_init", -2147483648, 2147483647),
                                  ("h3_cord", -1, 255), ("h3_age", -1, 600000)))),
        ("bd_o", ("list", 16, 2, (("ord", 0, 255), ("stamp", -2147483648, 2147483647),
                                  ("cause", 0, 3), ("edge", 0, 4),
                                  ("px", -9999999, 9999999), ("py", -9999999, 9999999),
                                  ("vx", -9999999, 9999999), ("vy", -9999999, 9999999),
                                  ("h1_pid", -1, 2147483647), ("h1_s_init", -2147483648, 2147483647),
                                  ("h1_cord", -1, 255), ("h1_age", -1, 600000),
                                  ("h2_pid", -1, 2147483647), ("h2_s_init", -2147483648, 2147483647),
                                  ("h2_cord", -1, 255), ("h2_age", -1, 600000),
                                  ("h3_pid", -1, 2147483647), ("h3_s_init", -2147483648, 2147483647),
                                  ("h3_cord", -1, 255), ("h3_age", -1, 600000)))),
        ("omit", ("omit", 0, 9999999)),
    ),
    "tier_order": (("b5_h", "rx_o", "rx_s", "p3tb", "p3top", "p3ht", "vchg", "bsel"),
                   ("b5_r", "b5_o", "b5_s", "b5_c", "ch_o", "ch_s", "push_o", "push_s",
                    "bd_o", "bd_s"),
                   ("tb", "sh_s", "sh_o")),
    "caps": {"push": 1, "vchg": 2, "chain": 4, "death": 8},
    "sections": (("push", (("push_s", "push_own"), ("push_o", "push_other"))),
                 ("vchg", (("vchg", "vchg"), ("bsel", "bsel"))),
                 ("chain", (("ch_s", "chain_own"), ("ch_o", "chain_other"))),
                 ("death", (("bd_s", "death_own"), ("bd_o", "death_other")))),
    "cause": {"collider": 1, "surface": 2, "gravity": 4, "steering": 8, "retarget": 16,
              "destruction": 32},
    "death_cause": {"unknown": 0, "out_of_bounds": 1, "damage": 2, "other": 3},
    "edge": {"none": 0, "left": 1, "right": 2, "top": 3, "bottom": 4},
    "bounce_target": {"none": 0, "self": 1, "other": 2},
    "recent_hits": 3,
    "protect": (("sh_s", "cx_s"), ("sh_o", "cx_o")),
    "end": {"point": 0, "timer": 1, "automatic": 2, "external": 3, "redraw": 4},
    "src": {"none": 0, "card": 1, "revive": 2},
    "regen_kind": 5,
    "why": {"over_mag": 1, "in_reload": 2, "short_gap": 4, "found_reloading": 8,
            "gate_reloading": 16},
    "fl": {"forced": 1, "use_ammo": 2, "reloading": 4, "no_ammo_init": 8, "separate": 16},
    "gap_none": -600001,
    "own_since_none": -2,
    "steer_bits": {"homing": 1, "target_bounce": 2, "edge_bounce": 4, "remote": 8, "dodge": 16,
                   "local": 32, "drill": 64, "accelerate": 128},
    "move": {"dt_clamp": 0.02, "speed_floor": 2.0},
    "homing": {"force_scale": 0.025, "cone_deg": 70.0},
    "bounce": {"wait_s": 0.1, "nudge": 0.1, "comp_scale": 0.012, "comp_pow": 2.06},
    "centi": 100,
}

W = COMBAT_WIRE
SPEC = dict(W["spec"])
KEYS = tuple(k for k, _s in W["spec"])
LISTS = tuple(k for k, s in W["spec"] if s[0] in ("list", "groups"))
OMIT_KEYS = LISTS
RECORD_MAX_BYTES = W["record_max_bytes"]
PER_MILLE = 1000


class Refusal(Exception):
    """A record outside the layout: `field` names the first key that failed."""

    def __init__(self, field: str):
        super().__init__(field)
        self.field = field


def _fields(spec):
    kind = spec[0]
    if kind == "row":
        return spec[1]
    if kind == "rows":
        return spec[2]
    if kind == "list":
        return spec[3]
    return ()


def _index(fields):
    return {f[0]: i for i, f in enumerate(fields)}


IX = {k: _index(_fields(s)) for k, s in W["spec"]}
HDR = _index(SPEC["sh_s"][3])
SHOT = {"s": _index(SPEC["sh_s"][5]), "o": _index(SPEC["sh_o"][5])}
REGEN = _index(SPEC["sh_s"][7])
GUN = IX["gun_s"]
TOT = IX["tot_s"]
CX = IX["cx_s"]
TB = IX["tb"]
END = W["end"]
WHY = W["why"]
FL = W["fl"]


# -- shape ------------------------------------------------------------------------

def _int_ok(v, lo, hi) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _row_ok(v, fields) -> bool:
    return (isinstance(v, list) and len(v) == len(fields)
            and all(_int_ok(x, f[1], f[2]) for x, f in zip(v, fields)))


def _group_ok(g, spec) -> bool:
    if not (isinstance(g, list) and len(g) == W["group_parts"]):
        return False
    hdr, shots, regens = g
    if not _row_ok(hdr, spec[3]):
        return False
    if not (isinstance(shots, list) and 1 <= len(shots) <= spec[4]
            and all(_row_ok(x, spec[5]) for x in shots)):
        return False
    if not (isinstance(regens, list) and len(regens) <= spec[6]
            and all(_row_ok(x, spec[7]) for x in regens)):
        return False
    n, nrg = hdr[HDR["n"]], hdr[HDR["nrg"]]
    ks = [r[REGEN["k"]] for r in regens]
    return len(shots) <= n and len(regens) <= nrg and ks == sorted(ks) and all(k <= n for k in ks)


def check_field(key, v) -> bool:
    s = SPEC[key]
    kind = s[0]
    if kind == "int":
        return _int_ok(v, s[1], s[2])
    if kind == "enum":
        return isinstance(v, str) and v in s[1]
    if kind == "row":
        return _row_ok(v, s[1])
    if kind == "rows":
        return isinstance(v, list) and len(v) == s[1] and all(_row_ok(x, s[2]) for x in v)
    if kind == "hist":
        return isinstance(v, list) and len(v) == s[1] and all(_int_ok(x, s[2], s[3]) for x in v)
    if kind == "list":
        return isinstance(v, list) and len(v) <= s[1] and all(_row_ok(x, s[3]) for x in v)
    if kind == "groups":
        return isinstance(v, list) and len(v) <= s[1] and all(_group_ok(g, s) for g in v)
    if kind == "omit":
        return (isinstance(v, dict) and list(v.keys()) == list(OMIT_KEYS)
                and all(_int_ok(v[k], s[1], s[2]) for k in OMIT_KEYS))
    return False


def check_record(rec) -> None:
    """Raise Refusal(<key>) for the first key outside the layout, or a key set
    or key order other than the layout's."""
    if not isinstance(rec, dict):
        raise Refusal("record")
    keys = list(rec.keys())
    if keys != list(KEYS):
        missing = [k for k in KEYS if k not in rec]
        extra = [k for k in keys if k not in KEYS]
        raise Refusal((missing or extra or ["key_order"])[0])
    for key in KEYS:
        if not check_field(key, rec[key]):
            raise Refusal(key)


# -- serialization, the budgeter and its byte proof ---------------------------------

def dumps(obj) -> str:
    """The wire form: no whitespace, ASCII, keys in insertion order."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


def _popcount(v: int) -> int:
    return bin(v).count("1")


def _cx_excess(e) -> int:
    return max(0, e[CX["units"]] - e[CX["mag"]] - e[CX["regen"]] - e[CX["tail"]])


def protected(out) -> dict:
    """The protected tier of a record being budgeted: the cycle groups whose
    first stamp a kept cycle-summary entry of the same gun names, and the
    time base points those kept groups lie in. A point stays protected while
    any kept protected group lies in it."""
    prot = {"points": set()}
    for gk, ck in W["protect"]:
        keys = {e[CX["s0"]] for e in out[ck]}
        idx = [i for i, g in enumerate(out[gk]) if g[0][HDR["s0"]] in keys]
        prot[gk] = idx
        prot["points"].update(out[gk][i][0][HDR["pt"]] for i in idx)
    return prot


def _trim_one(out, omit) -> bool:
    """Remove one entry by the tier rule; False when nothing is removable."""
    tier_one, tier_two, tier_three = W["tier_order"]
    for tier in (tier_one, tier_two):
        best = None
        for k in tier:
            if out[k] and (best is None or len(out[k]) > len(out[best])):
                best = k
        if best is not None:
            out[best] = out[best][:-1]
            omit[best] += 1
            return True
    prot = protected(out)
    removable = {"tb": [i for i, e in enumerate(out["tb"]) if e[TB["pt"]] not in prot["points"]]}
    for gk, _ck in W["protect"]:
        keep = set(prot[gk])
        removable[gk] = [i for i in range(len(out[gk])) if i not in keep]
    best = None
    for k in tier_three:
        if removable[k] and (best is None or len(removable[k]) > len(removable[best])):
            best = k
    if best is not None:
        del out[best][removable[best][-1]]
        omit[best] += 1
        return True
    cands = []
    for pos, (gk, ck) in enumerate(W["protect"]):
        by_s0 = {}
        for e in out[ck]:
            by_s0.setdefault(e[CX["s0"]], e)
        for i in prot[gk]:
            e = by_s0[out[gk][i][0][HDR["s0"]]]
            cands.append(((_popcount(e[CX["why"]]), _cx_excess(e), -i, -pos), gk, i))
    if not cands:
        return False
    _key, gk, i = min(cands)
    del out[gk][i]
    omit[gk] += 1
    return True


def budget_record(rec: dict, limit: int | None = None) -> str:
    """The reference budgeter. `rec` holds every layout key in order with its
    full lists. Returns the record text, at most `limit` bytes:

      one   every list is truncated to its cap (the first entries kept), and
            every cycle group's shots and regenerations to theirs; list
            truncation is counted in `omit`, a group's own truncation is
            carried by its header counts;
      two   serialize (dumps);
      three while above the limit remove ONE entry and re-serialize: from the
            first of tiers one and two that has an entry, the list with the
            most entries (ties: the named order), its last entry; else tier
            three, the list (time base, own gun's groups, other gun's groups)
            with the most REMOVABLE entries, its last removable entry (a group
            is removable when no kept cycle summary names it, a time base
            point when no kept protected group lies in it); else one
            protected group, the one with the fewest reason bits, then the
            smallest excess, then the latest in its list, the other gun's
            before the own gun's on a full tie. Every removal adds one to that
            list's `omit` count.

    Deterministic: the same input gives the same bytes."""
    limit = RECORD_MAX_BYTES if limit is None else limit
    out = {}
    for k in KEYS:
        v = rec[k]
        out[k] = [list(x) if isinstance(x, list) else x for x in v] if isinstance(v, list) else v
    omit = {k: rec["omit"][k] for k in OMIT_KEYS}
    for k in LISTS:
        s = SPEC[k]
        lst = list(out[k])
        if len(lst) > s[1]:
            omit[k] += len(lst) - s[1]
            lst = lst[: s[1]]
        if s[0] == "groups":
            lst = [[list(g[0]), [list(x) for x in g[1][: s[4]]], [list(x) for x in g[2][: s[6]]]]
                   for g in lst]
        out[k] = lst
    out["omit"] = omit
    body = dumps(out)
    while len(body) > limit:
        if not _trim_one(out, omit):
            raise ValueError("the never-trimmed part alone exceeds the record bound")
        body = dumps(out)
    return body


def _widest(lo, hi):
    return lo if len(str(lo)) >= len(str(hi)) else hi


def _max_row(fields):
    return [_widest(f[1], f[2]) for f in fields]


def max_width_record() -> dict:
    """A valid record whose never-trimmed part is as wide as the layout
    allows: every field at its widest bound, every never-trimmed list at its
    cap, every trimmable list empty, every omit count at its widest."""
    out = {}
    for k, s in W["spec"]:
        kind = s[0]
        if kind == "int":
            out[k] = _widest(s[1], s[2])
        elif kind == "enum":
            out[k] = max(s[1], key=len)
        elif kind == "row":
            out[k] = _max_row(s[1])
        elif kind == "rows":
            out[k] = [_max_row(s[2]) for _i in range(s[1])]
        elif kind == "hist":
            out[k] = [_widest(s[2], s[3]) for _i in range(s[1])]
        elif kind == "list":
            out[k] = [_max_row(s[3]) for _i in range(s[1])] if s[2] == 0 else []
        elif kind == "groups":
            out[k] = []
        else:
            out[k] = {o: _widest(s[1], s[2]) for o in OMIT_KEYS}
    return out


def max_width_group(key: str) -> list:
    s = SPEC[key]
    return [_max_row(s[3]), [_max_row(s[5]) for _i in range(s[4])],
            [_max_row(s[7]) for _i in range(s[6])]]


def byte_proof() -> dict:
    """The exact bounds the budgeter guarantees, computed from the layout:

      never_trimmed_max  the largest the never-trimmed part can serialize to;
      group_max          the largest one cycle group can serialize to;
      point_max          the largest one time base entry can serialize to;
      protected_floor    the number of protected cycle groups always kept:
                         removal happens only while the record is over the
                         bound, and with the never-trimmed part at its
                         largest and fewer than this many protected groups
                         (each with its own point and separators) the record
                         is under it."""
    nt = len(dumps(max_width_record()))
    group = max(len(dumps(max_width_group(k))) for k, _c in W["protect"])
    point = len(dumps(_max_row(SPEC["tb"][3])))
    per = group + point + 2
    return {"limit": RECORD_MAX_BYTES, "never_trimmed_max": nt, "group_max": group,
            "point_max": point, "protected_floor": (RECORD_MAX_BYTES - nt) // per}


# -- the cycle rebuild ----------------------------------------------------------------

def wrap(v: int) -> int:
    """v on the wrapping signed thirty-two-bit stamp clock."""
    return ((v + 2 ** 31) % 2 ** 32) - 2 ** 31


def stat_at(gun_list, pt):
    """The stat block in force at a point: the last entry at or before it."""
    best = None
    for e in gun_list:
        if e[GUN["pt"]] <= pt:
            best = e
    return best


def _marker(side, shot) -> bool:
    """True on the first projectile of an emission: an own repeat ordinal
    (own gun) or a received attack message (the other seat's gun)."""
    S = SHOT[side]
    return (shot[S["rep"]] if side == "s" else shot[S["am"]]) != -1


def rebuild_cycle(group, side, gun_list) -> dict:
    """One cycle from its group with the public accounting both seats run:
    the rule count starts at the magazine, each listed regeneration adds its
    units before the shot it precedes, each ammo projectile takes one;
    exhaustion is the projectile that brings the count to zero or below.
    Fields that need a projectile the group no longer lists are None and
    `not_run` names why."""
    S = SHOT[side]
    hdr, entries, regens = group
    pid, st = hdr[HDR["pid0"]], hdr[HDR["s0"]]
    shots = []
    for e in entries:
        pid = pid + e[S["dpid"]]
        st = wrap(st + e[S["dt"]])
        shot = {"pid": pid, "stamp": st, "ammo_before": e[S["ammo_before"]],
                "reloading": e[S["reloading"]], "counter": e[S["counter"]],
                "first_of_emission": _marker(side, e)}
        if side == "s":
            shot.update(rep=e[S["rep"]], since=e[S["since"]], fl=e[S["fl"]])
        else:
            shot["am"] = e[S["am"]]
        shots.append(shot)
    n = hdr[HDR["n"]]
    # The regeneration total is DERIVED from the event stream, never taken from
    # the header: the header's own total is kept beside it (`regen_stated`) and
    # a disagreement is a record fault (rebuild_faults). An event stream the
    # group no longer lists whole gives no total at all.
    events_complete = len(regens) == hdr[HDR["nrg"]]
    complete = len(entries) == n and events_complete
    block = stat_at(gun_list, hdr[HDR["pt"]])
    c = {"s0": hdr[HDR["s0"]], "pid0": hdr[HDR["pid0"]], "pt": hdr[HDR["pt"]], "units": n,
         "listed": len(entries), "complete": complete, "end": hdr[HDR["end"]],
         "src": hdr[HDR["src"]], "amt": hdr[HDR["amt"]], "st_end": hdr[HDR["st_end"]],
         "rl_g": hdr[HDR["rl_g"]], "rl_s": hdr[HDR["rl_s"]], "rl_r": hdr[HDR["rl_r"]],
         "regen": sum(r[REGEN["amt"]] for r in regens) if events_complete else None,
         "regen_stated": hdr[HDR["rg"]], "events_complete": events_complete,
         "regen_events": hdr[HDR["nrg"]],
         "regens": [{"before_shot": r[REGEN["k"]], "kind": W["regen_kind"], "amt": r[REGEN["amt"]],
                     "st": r[REGEN["st"]], "gap_g": r[REGEN["gap_g"]], "gap_s": r[REGEN["gap_s"]],
                     "gap_r": r[REGEN["gap_r"]]} for r in regens],
         "shots": shots, "mag": None, "rexp": None, "vol": None, "exh": None, "exh_index": None,
         "tail": None, "in_rl": None, "gaps": None, "why": None, "excess": None, "not_run": None}
    if block is None:
        c["not_run"] = "no_stat_block"
        return c
    c["mag"], c["rexp"] = block[GUN["mag"]], block[GUN["rexp"]]
    if not complete:
        c["not_run"] = "trimmed"
        return c
    count, ri, exh = c["mag"], 0, None
    for j in range(len(shots)):
        while ri < len(regens) and regens[ri][REGEN["k"]] <= j:
            count += regens[ri][REGEN["amt"]]
            ri += 1
        count -= 1
        if exh is None and count <= 0:
            exh = j
    vol, last = 0, None
    for s in shots:
        if last is None or s["stamp"] != last:
            vol += 1
        last = s["stamp"]
    c["vol"] = vol
    gaps = [-1] * W["gap_count"]
    tail = in_rl = 0
    if exh is not None:
        post = shots[exh + 1:]
        while tail < len(post) and not post[tail]["first_of_emission"]:
            tail += 1
        in_rl = sum(1 for s in post if s["reloading"])
        sx = shots[exh]["stamp"]
        vols = []
        for s in post[tail:]:
            if not vols or s["stamp"] != vols[-1]:
                vols.append(s["stamp"])
        for i, v in enumerate(vols[: W["gap_count"]]):
            gaps[i] = wrap(v - sx)
        c["exh"] = wrap(sx - c["s0"])
        c["exh_index"] = exh
    c["tail"], c["in_rl"], c["gaps"] = tail, in_rl, gaps
    c["excess"] = max(0, n - c["mag"] - c["regen"] - tail)
    why = 0
    if n - tail > c["mag"] + c["regen"]:
        why |= WHY["over_mag"]
    if in_rl > tail:
        why |= WHY["in_reload"]
    if c["end"] == END["timer"] and gaps[0] >= 0 and gaps[0] < c["rexp"]:
        why |= WHY["short_gap"]
    upto = shots if exh is None else shots[: exh + 1]
    if any(s["reloading"] for s in upto):
        why |= WHY["found_reloading"]
    if side == "s" and any(s["rep"] == 0 and s["fl"] & FL["reloading"] and not s["fl"] & FL["forced"]
                           for s in shots):
        why |= WHY["gate_reloading"]
    c["why"] = why
    return c


def rebuild_side(rec: dict, side: str) -> list:
    """Every listed cycle of one gun on one record: side "s" the recording
    seat's own gun, "o" its copy of the other seat's gun."""
    return [rebuild_cycle(g, side, rec["gun_" + side]) for g in rec["sh_" + side]]


def rebuild_faults(rec: dict, side: str) -> list:
    """The rebuild checked against the record's own whole-game totals and
    cycle summaries. A disagreement is a fault of the record (stored, never a
    finding). Totals are compared only where no input was trimmed."""
    tot = rec["tot_" + side]
    gk, ck = "sh_" + side, "cx_" + side
    cycles = rebuild_side(rec, side)
    faults = []
    if len(rec[gk]) + rec["omit"][gk] != tot[TOT["cycles"]]:
        faults.append("cycles")
    if any(c["events_complete"] and c["regen"] != c["regen_stated"] for c in cycles):
        faults.append("regen_total")
    if len(rec[ck]) + rec["omit"][ck] != tot[TOT["cx_n"]]:
        faults.append("cx_count")
    whole = rec["omit"][gk] == 0 and all(c["not_run"] is None for c in cycles)
    if whole:
        if sum(c["units"] for c in cycles) != tot[TOT["units"]]:
            faults.append("units")
        if sum(c["vol"] for c in cycles) != tot[TOT["volleys"]]:
            faults.append("volleys")
        if sum(c["excess"] for c in cycles) != tot[TOT["sum_excess"]]:
            faults.append("sum_excess")
        for name, bit in WHY.items():
            if sum(1 for c in cycles if c["why"] & bit) != tot[TOT["why_" + name]]:
                faults.append("why_" + name)
        if rec["omit"][ck] == 0 and sum(1 for c in cycles if c["why"]) != tot[TOT["cx_n"]]:
            faults.append("cx_n")
        firsts = [s for c in cycles for s in c["shots"] if s["first_of_emission"]]
        if side == "s":
            if len(firsts) != tot[TOT["emit"]]:
                faults.append("emit")
            gate_firsts = sum(1 for s in firsts if s["rep"] == 0)
            if gate_firsts + tot[TOT["atk_noinit"]] != tot[TOT["gate"]]:
                faults.append("gate")
        elif len(firsts) + tot[TOT["atk_noinit"]] != tot[TOT["atk_msg"]]:
            faults.append("atk_msg")
    by_s0 = {c["s0"]: c for c in cycles}
    for e in rec[ck]:
        c = by_s0.get(e[CX["s0"]])
        if c is None or c["not_run"] is not None:
            continue
        mine = (c["units"], c["vol"], c["mag"], c["regen"], c["in_rl"], c["tail"], c["rexp"],
                c["end"], c["why"])
        theirs = (e[CX["units"]], e[CX["vol"]], e[CX["mag"]], e[CX["regen"]], e[CX["in_rl"]],
                  e[CX["tail"]], e[CX["rexp"]], e[CX["end"]], e[CX["why"]])
        if mine != theirs:
            faults.append("cx_entry")
            break
    return faults


# -- the pairing of a game's records ---------------------------------------------

LABEL_SELF = "SELF-STATED"
LABEL_MEAS = "OTHER-SEAT-MEASURED"
CASE_TEXT = {
    "only_measuring": "the other seat's measurement only; the owner's own gun state is unavailable",
    "only_owner": "the owner's self-statement only; it can open a review at most",
    "both_agree": "both accounts agree: consistency, never proof",
    "both_differ": "the two accounts differ; neither is taken as the truth",
    "not_run": "inputs missing, trimmed or of another measurement version: not compared (NOT-RUN)",
}


def consts_ok(*recs) -> bool:
    """Every record is of a measurement version this server reads, and all are
    of the same one."""
    vs = {r["consts"] for r in recs}
    return len(vs) == 1 and vs <= set(W["consts_known"])


def _gun_fields():
    return [f[0] for f in SPEC["gun_s"][3] if f[0] != "pt"]


def _stat_diff(a, b):
    if a is None or b is None:
        return None
    return {"d_" + f: a[GUN[f]] - b[GUN[f]] for f in _gun_fields()}


def _named(row, fields):
    return {f[0]: v for f, v in zip(fields, row)}


def _point_row(rec, pt):
    for e in rec["tb"]:
        if e[TB["pt"]] == pt:
            real = e[TB["real"]]
            return {"pt": pt, "ps": e[TB["ps"]], "real": real, "game": e[TB["game"]],
                    "srv": e[TB["srv"]], "slow": e[TB["slow"]], "ramp": e[TB["ramp"]],
                    "clamp": e[TB["clamp"]], "base": e[TB["base"]], "frames": e[TB["frames"]],
                    "dt_med_us": e[TB["dt_med_us"]], "dt_max_us": e[TB["dt_max_us"]],
                    "game_real_pm": e[TB["game"]] * PER_MILLE // real if real else None,
                    "srv_real_pm": e[TB["srv"]] * PER_MILLE // real if real else None}
    return None


def _shot_key(s):
    return (s["pid"], s["stamp"])


def _trimmed(rec, key) -> bool:
    return rec is not None and rec["omit"][key] > 0


def _incompatible(rows, out):
    """Two records of different (or unread) measurement versions: every
    comparison across them is NOT-RUN; each account's own fields stay."""
    for r in rows:
        r["not_run"], r["refill"], r["differs"], r["differs_by"] = "incompatible", None, False, []
        r["stat"]["diff"] = None
        r["clock"] = None
        for s in r["shots"]:
            s.update(d_ammo=None, d_reloading=None, d_counter=None, absent_in=None,
                     not_run="incompatible")
    for st in out["stat"]:
        st["diff"], st["not_run"] = None, "incompatible"
    out["attacks"]["d_emit_msgs"], out["attacks"]["not_run"] = None, "incompatible"
    out["totals"]["diff"], out["totals"]["not_run"] = None, "incompatible"


# Whole-game totals both accounts of one gun derive the same way (the rebuild's
# own accounting); the owner-only and copy-only counters (gate calls,
# emissions, attack messages, cycle-summary selections) are not among them.
TOTALS_COMPARED = ("cycles", "volleys", "units", "inits_rl", "why_over_mag", "why_in_reload",
                   "why_short_gap", "why_found_reloading", "sum_excess", "gap_minus_rexp_min")
# Reason bits only the owner's own account can carry.
WHY_OWNER_ONLY = WHY["gate_reloading"]
# Cycle fields both accounts state (the header) and derive (the rebuild).
CYCLE_STATED = ("units", "end", "src", "amt", "regen_events")
CYCLE_DERIVED = ("mag", "rexp", "regen", "vol", "exh", "tail", "in_rl", "gaps", "excess")
CLOCKS = ("rl_g", "rl_s", "rl_r")


def _mark(row, what):
    if what not in row["differs_by"]:
        row["differs_by"].append(what)
    row["differs"] = True


def direction(owner_rec, meas_rec, compatible=True) -> dict:
    """One gun, seen from both seats: the owner's own account (SELF-STATED,
    from its record's own gun) and the other seat's account of the same gun
    (OTHER-SEAT-MEASURED, from that seat's copy). Either may be absent.

    The display case is derived from EVERY comparable field: per shot (ammo,
    reloading, reload counter, presence), per cycle (stated and derived
    fields, reason bits without the owner-only bit, the refill events and the
    cycle clocks), the attack count against the emissions, the stat blocks at
    every point and the whole-game totals. Any difference is `both_differ`
    and `differs_by` names its classes. `both_agree` needs something compared
    and nothing differing; with listed cycles that is at least one cycle
    compared. Otherwise `not_run` (every dependency missing, trimmed or of
    another measurement version)."""
    self_c = rebuild_side(owner_rec, "s") if owner_rec is not None else None
    meas_c = rebuild_side(meas_rec, "o") if meas_rec is not None else None
    if owner_rec is not None and meas_rec is not None:
        case = None
    elif meas_rec is not None:
        case = "only_measuring"
    else:
        case = "only_owner"
    self_shots = {_shot_key(s): s for c in (self_c or []) for s in c["shots"]}
    meas_shots = {_shot_key(s): s for c in (meas_c or []) for s in c["shots"]}
    rows = []
    primary = meas_c if meas_c is not None else self_c
    covered = set()
    for c in primary:
        rows.append(_cycle_row(c, owner_rec, meas_rec, self_c, meas_c, self_shots, meas_shots,
                               primary is meas_c))
        covered.update(_shot_key(s) for s in c["shots"])
    if meas_c is not None and self_c is not None:
        for c in self_c:
            if not any(_shot_key(s) in covered for s in c["shots"]):
                rows.append(_cycle_row(c, owner_rec, meas_rec, self_c, meas_c, self_shots,
                                       meas_shots, False))
    # A cycle a kept summary names but whose shot group neither record still
    # lists: shown from its summary, every per-shot comparison NOT-RUN.
    seen = {r["s0"] for r in rows}
    for acct, rec, ck in (("meas", meas_rec, "cx_o"), ("self", owner_rec, "cx_s")):
        if rec is None:
            continue
        for e in rec[ck]:
            if e[CX["s0"]] in seen:
                continue
            seen.add(e[CX["s0"]])
            rows.append({"s0": e[CX["s0"]], "pt": None, "self": None, "meas": None,
                         "summary": {acct: _named(e, SPEC[ck][3])}, "shots": [], "refill": None,
                         "differs": False, "differs_by": [], "clock": None, "not_run": "trimmed",
                         "stat": {"self": None, "meas": None, "diff": None},
                         "time": {"self": None, "meas": None}})
    out = {"case": case, "case_text": None, "cycles": rows,
           "self_label": LABEL_SELF, "meas_label": LABEL_MEAS,
           "self_present": owner_rec is not None, "meas_present": meas_rec is not None}
    out["attacks"] = {
        "owner_gate": owner_rec["tot_s"][TOT["gate"]] if owner_rec else None,
        "owner_emit": owner_rec["tot_s"][TOT["emit"]] if owner_rec else None,
        "meas_msgs": meas_rec["tot_o"][TOT["atk_msg"]] if meas_rec else None,
        "d_emit_msgs": (owner_rec["tot_s"][TOT["emit"]] - meas_rec["tot_o"][TOT["atk_msg"]]
                        if owner_rec and meas_rec else None),
        "not_run": None if owner_rec and meas_rec else "missing_record"}
    out["totals"] = {"self": _named(owner_rec["tot_s"], SPEC["tot_s"][1]) if owner_rec else None,
                     "meas": _named(meas_rec["tot_o"], SPEC["tot_o"][1]) if meas_rec else None,
                     "diff": None, "not_run": None if owner_rec and meas_rec else "missing_record"}
    if owner_rec is not None and meas_rec is not None:
        out["totals"]["diff"] = {"d_" + f: owner_rec["tot_s"][TOT[f]] - meas_rec["tot_o"][TOT[f]]
                                 for f in TOTALS_COMPARED}
    out["cx"] = {"self": [_named(e, SPEC["cx_s"][3]) for e in owner_rec["cx_s"]] if owner_rec else None,
                 "meas": [_named(e, SPEC["cx_o"][3]) for e in meas_rec["cx_o"]] if meas_rec else None,
                 "self_omitted": owner_rec["omit"]["cx_s"] if owner_rec else None,
                 "meas_omitted": meas_rec["omit"]["cx_o"] if meas_rec else None}
    pts = sorted({e[GUN["pt"]] for e in (owner_rec["gun_s"] if owner_rec else [])}
                 | {e[GUN["pt"]] for e in (meas_rec["gun_o"] if meas_rec else [])})
    out["stat"] = []
    for pt in pts:
        a = stat_at(owner_rec["gun_s"], pt) if owner_rec else None
        b = stat_at(meas_rec["gun_o"], pt) if meas_rec else None
        out["stat"].append({"pt": pt, "self": _named(a, SPEC["gun_s"][3]) if a else None,
                            "meas": _named(b, SPEC["gun_o"][3]) if b else None,
                            "diff": _stat_diff(a, b),
                            "not_run": None if a is not None and b is not None else "missing_record"})
    out["differs_by"] = []
    if case is None:
        if not compatible:
            _incompatible(rows, out)
        found = set()
        for r in rows:
            found.update(r["differs_by"])
        if out["attacks"]["d_emit_msgs"]:
            found.add("attacks")
        if out["totals"]["diff"] and any(out["totals"]["diff"].values()):
            found.add("totals")
        if any(st["diff"] and any(st["diff"].values()) for st in out["stat"]):
            found.add("stat")
        cycles_compared = any(r["not_run"] is None for r in rows)
        whole_compared = (out["attacks"]["d_emit_msgs"] is not None
                          or out["totals"]["diff"] is not None
                          or any(st["diff"] is not None for st in out["stat"]))
        compared = cycles_compared if rows else whole_compared
        out["differs_by"] = sorted(found)
        case = "both_differ" if found else ("both_agree" if compared else "not_run")
        out["case"] = case
    out["case_text"] = CASE_TEXT[case]
    return out


def _cycle_row(c, owner_rec, meas_rec, self_c, meas_c, self_shots, meas_shots, primary_is_meas):
    other_c = self_c if primary_is_meas else meas_c
    mine = "meas" if primary_is_meas else "self"
    theirs = "self" if primary_is_meas else "meas"
    other_rec = owner_rec if primary_is_meas else meas_rec
    other_gk = "sh_s" if primary_is_meas else "sh_o"
    other_map = self_shots if primary_is_meas else meas_shots
    partner = None
    if other_c is not None:
        for oc in other_c:
            if oc["s0"] == c["s0"]:
                partner = oc
                break
    row = {"s0": c["s0"], "pt": c["pt"], mine: _cycle_fields(c), theirs: None, "shots": [],
           "refill": None, "differs": False, "differs_by": [], "clock": None, "not_run": None}
    if partner is not None:
        row[theirs] = _cycle_fields(partner)
        # A cycle either account could not rebuild whole (a shot or refill
        # event trimmed, no stat block) is not a compared cycle: the fields
        # both state are still set side by side and a difference among them
        # still counts, but the row never counts toward an agreement.
        row["not_run"] = c["not_run"] or partner["not_run"]
    elif other_rec is None:
        row["not_run"] = "missing_record"
    elif _trimmed(other_rec, other_gk):
        row["not_run"] = "trimmed"
    for s in c["shots"]:
        o = other_map.get(_shot_key(s))
        srow = {"pid": s["pid"], "stamp": s["stamp"], mine: _shot_fields(s), theirs: None,
                "d_ammo": None, "d_reloading": None, "d_counter": None, "not_run": None,
                "absent_in": None}
        if o is not None:
            srow[theirs] = _shot_fields(o)
            sv, mv = (o, s) if primary_is_meas else (s, o)
            srow["d_ammo"] = sv["ammo_before"] - mv["ammo_before"]
            srow["d_reloading"] = sv["reloading"] - mv["reloading"]
            srow["d_counter"] = sv["counter"] - mv["counter"]
            if srow["d_ammo"] or srow["d_reloading"] or srow["d_counter"]:
                _mark(row, "shot")
        elif other_rec is None:
            srow["not_run"] = "missing_record"
        elif _trimmed(other_rec, other_gk) or (partner is not None and not partner["complete"]):
            srow["not_run"] = "trimmed"
        else:
            srow["absent_in"] = theirs
            _mark(row, "shot")
        row["shots"].append(srow)
    if partner is not None:
        # Shots only the other account lists: NOT-RUN when this account's
        # cycle is incomplete or its list was trimmed, else absent here.
        listed = {_shot_key(s) for s in c["shots"]}
        own_rec = meas_rec if primary_is_meas else owner_rec
        own_gk = "sh_o" if primary_is_meas else "sh_s"
        for s in partner["shots"]:
            if _shot_key(s) in listed:
                continue
            srow = {"pid": s["pid"], "stamp": s["stamp"], mine: None, theirs: _shot_fields(s),
                    "d_ammo": None, "d_reloading": None, "d_counter": None, "not_run": None,
                    "absent_in": None}
            if not c["complete"] or _trimmed(own_rec, own_gk):
                srow["not_run"] = "trimmed"
            else:
                srow["absent_in"] = mine
                _mark(row, "shot")
            row["shots"].append(srow)
        a, b = (partner, c) if primary_is_meas else (c, partner)
        _compare_cycles(row, a, b)
    sb = owner_rec and stat_at(owner_rec["gun_s"], c["pt"])
    mb = meas_rec and stat_at(meas_rec["gun_o"], c["pt"])
    row["stat"] = {"self": _named(sb, SPEC["gun_s"][3]) if sb else None,
                   "meas": _named(mb, SPEC["gun_o"][3]) if mb else None,
                   "diff": _stat_diff(sb or None, mb or None)}
    if row["stat"]["diff"] and any(row["stat"]["diff"].values()):
        _mark(row, "stat")
    row["time"] = {"self": _point_row(owner_rec, c["pt"]) if owner_rec else None,
                   "meas": _point_row(meas_rec, c["pt"]) if meas_rec else None}
    return row


def _clock_delta(a, b):
    """The difference of two clock readings, None when either seat has none."""
    return None if a < 0 or b < 0 else a - b


def _compare_cycles(row, self_cycle, meas_cycle):
    """The two accounts of one cycle, field by field: the header fields both
    state, the fields both derive (when both rebuilds ran), the reason bits
    without the owner-only bit, the refill events, and the explicit clock
    deltas (each seat's reload length on its game, shared and real clock,
    the end stamp, the exhaustion and the gaps after it)."""
    for f in CYCLE_STATED:
        if self_cycle[f] != meas_cycle[f]:
            _mark(row, "cycle")
    both = self_cycle["not_run"] is None and meas_cycle["not_run"] is None
    if both:
        for f in CYCLE_DERIVED:
            if self_cycle[f] != meas_cycle[f]:
                _mark(row, "cycle")
        if (self_cycle["why"] & ~WHY_OWNER_ONLY) != (meas_cycle["why"] & ~WHY_OWNER_ONLY):
            _mark(row, "cycle")
    clock = {"d_" + k: _clock_delta(self_cycle[k], meas_cycle[k]) for k in CLOCKS}
    clock["d_st_end"] = wrap(self_cycle["st_end"] - meas_cycle["st_end"])
    clock["d_exh"] = (wrap(self_cycle["exh"] - meas_cycle["exh"])
                      if both and self_cycle["exh"] is not None and meas_cycle["exh"] is not None
                      else None)
    clock["d_gaps"] = ([_clock_delta(x, y) for x, y in zip(self_cycle["gaps"], meas_cycle["gaps"])]
                       if both else None)
    for k in CLOCKS:
        if (self_cycle[k] < 0) != (meas_cycle[k] < 0):
            _mark(row, "clock")
    if any(v for k, v in clock.items() if k != "d_gaps") or any(clock["d_gaps"] or ()):
        _mark(row, "clock")
    row["clock"] = clock
    row["refill"] = _refill_diff(self_cycle, meas_cycle)
    if row["refill"]["differs"]:
        _mark(row, "refill")


def _cycle_fields(c):
    keep = ("units", "listed", "complete", "mag", "regen", "regen_stated", "rexp", "vol", "exh",
            "tail", "in_rl", "gaps", "why", "excess", "end", "src", "amt", "st_end", "rl_g", "rl_s",
            "rl_r", "regen_events", "events_complete", "regens", "not_run")
    return {k: c[k] for k in keep}


def _shot_fields(s):
    return {k: v for k, v in s.items() if k not in ("pid", "stamp")}


def _event_key(r):
    """A refill event's whole identity: the shot it precedes, its kind and
    amount, its stamp and its length on all three clocks."""
    return (r["before_shot"], r["kind"], r["amt"], r["st"], r["gap_g"], r["gap_s"], r["gap_r"])


def _only_in(rows, others):
    """The events of `rows` the multiset `others` does not hold (a repeated
    event counts once per listing)."""
    left = Counter(_event_key(r) for r in others)
    out = []
    for r in rows:
        k = _event_key(r)
        if left[k]:
            left[k] -= 1
        else:
            out.append(r)
    return out


def _refill_diff(self_cycle, meas_cycle) -> dict:
    """The refills of one cycle on both seats: how each account says it
    ended, and every regeneration only one account saw, compared as
    multisets on kind, amount, stamp and all three clocks. When either
    account's event list is incomplete the event comparison is NOT-RUN
    (`trimmed`), never an agreement."""
    ends = {k: (self_cycle[k], meas_cycle[k]) for k in ("end", "src", "amt", "rl_g", "rl_s", "rl_r")}
    ends_differ = any(a != b for a, b in ends.values())
    out = {"end": ends, "owner_only": None, "meas_only": None, "not_run": None,
           "differs": ends_differ}
    if not (self_cycle["events_complete"] and meas_cycle["events_complete"]):
        out["not_run"] = "trimmed"
        return out
    out["owner_only"] = _only_in(self_cycle["regens"], meas_cycle["regens"])
    out["meas_only"] = _only_in(meas_cycle["regens"], self_cycle["regens"])
    out["differs"] = ends_differ or bool(out["owner_only"]) or bool(out["meas_only"])
    return out


def blocks(victim_rec, shooter_rec) -> list:
    """The victim's own block windows against the shooter's copy of them, by
    the block key (stamp, kind, ordinal). The predicted-window difference is
    given with its frame bound: the two seats' recorded frame lengths."""
    if victim_rec is None or shooter_rec is None:
        return []
    S, O = IX["b5_s"], IX["b5_o"]
    theirs = {}
    for e in shooter_rec["b5_o"]:
        theirs.setdefault((e[O["tb"]], e[O["kind"]], e[O["ord"]]), []).append(e)
    rows = []
    for e in victim_rec["b5_s"]:
        key = (e[S["tb"]], e[S["kind"]], e[S["ord"]])
        cand = theirs.get(key, [])
        row = {"tb": key[0], "kind": key[1], "ord": key[2], "d_open": None, "d_len": None,
               "d_len_g": None, "d_pred": None, "d_pred_lo": None, "d_pred_hi": None,
               "self": _named(e, SPEC["b5_s"][3]), "meas": None, "not_run": None}
        if len(cand) != 1:
            row["not_run"] = ("ambiguous" if cand else
                              ("trimmed" if _trimmed(shooter_rec, "b5_o") else "absent"))
        else:
            o = cand[0]
            row["meas"] = _named(o, SPEC["b5_o"][3])
            fb = e[S["fr"]] + o[O["fr"]]
            row["d_open"] = o[O["open_c"]] - e[S["open"]]
            row["d_len"] = (o[O["len_c"]] - e[S["len"]]) if min(o[O["len_c"]], e[S["len"]]) >= 0 else None
            row["d_len_g"] = ((o[O["len_cg"]] - e[S["len_g"]])
                              if min(o[O["len_cg"]], e[S["len_g"]]) >= 0 else None)
            row["d_pred"] = e[S["open"]] - o[O["o_pred"]]
            row["d_pred_lo"], row["d_pred_hi"] = row["d_pred"] - fb, row["d_pred"] + fb
            row["frame_bound"] = fb
        rows.append(row)
    return rows


def contacts(victim_rec, shooter_rec) -> list:
    """Each contact of the shooter's projectile with the victim, keyed on
    both seats by the projectile's init identity (id and init stamp) and the
    contact ordinal. A key that appears more than once in either list, or an
    ordinal whose predecessor is missing on that seat, is ambiguous: its rows
    are NOT-RUN and nothing is paired across it."""
    if victim_rec is None:
        return []
    C, H = IX["b5_c"], IX["b5_h"]
    vic = [(e[C["pid"]], e[C["s_init"]], e[C["cord"]]) for e in victim_rec["b5_c"]]
    sho = ([(e[H["pid"]], e[H["s_init"]], e[H["cord"]]) for e in shooter_rec["b5_h"]]
           if shooter_rec is not None else [])
    bad = _ambiguous(vic) | _ambiguous(sho)
    by_key = {}
    if shooter_rec is not None:
        for k, e in zip(sho, shooter_rec["b5_h"]):
            by_key[k] = e
    rows = []
    for k, e in zip(vic, victim_rec["b5_c"]):
        row = {"pid": k[0], "s_init": k[1], "cord": k[2], "since_c": e[C["since_c"]],
               "own_since": e[C["own_since"]], "tc": e[C["tc"]], "since_ms": None,
               "pred_since": None, "contact_to_decision": None, "not_run": None}
        if (k[0], k[1]) in bad:
            row["not_run"] = "ambiguous"
            row["since_c"] = row["own_since"] = None
        elif shooter_rec is None:
            row["not_run"] = "missing_record"
        elif k not in by_key:
            row["not_run"] = "trimmed" if _trimmed(shooter_rec, "b5_h") else "absent"
        else:
            h = by_key[k]
            row["since_ms"] = h[H["since_ms"]]
            row["pred_since"] = h[H["pred_since"]]
            row["contact_to_decision"] = wrap(h[H["stamp"]] - e[C["tc"]])
        rows.append(row)
    return rows


def _ambiguous(keys) -> set:
    """Projectiles (id, init stamp) whose contact keys repeat, or whose
    ordinals on this seat are not exactly zero up to their count."""
    seen, out = {}, set()
    for pid, s_init, cord in keys:
        seen.setdefault((pid, s_init), []).append(cord)
    for proj, cords in seen.items():
        if sorted(cords) != list(range(len(cords))):
            out.add(proj)
    return out


# -- the addendum sections: push, owner velocity changes, the hit chain, boundary deaths ---

def has_cap(rec, name) -> bool:
    """Whether the recording seat filled a section (the client fills one only
    when the whole room carries the capability)."""
    return rec is not None and bool(rec["caps"] & W["caps"][name])


def section_faults(rec) -> list:
    """Each addendum section against its whole-game count: a section the
    record says it did not fill must be empty, with a zero count and a zero
    omitted count; a filled one lists its entries plus its omitted count up to
    that count."""
    faults = []
    rt = IX["r_tot"]
    for name, parts in W["sections"]:
        for key, count in parts:
            total = rec["r_tot"][rt[count]]
            if not has_cap(rec, name):
                if rec[key] or total or rec["omit"][key]:
                    faults.append("caps_" + key)
            elif len(rec[key]) + rec["omit"][key] != total:
                faults.append(key)
    return faults


def _own_section(rec, name):
    """Why a seat's own section has no rows to show, or None when it has."""
    if rec is None:
        return "missing_record"
    return None if has_cap(rec, name) else "not_collected"


def _keyed(rows, ix, fields=("pid", "s_init", "cord")):
    return [tuple(e[ix[f]] for f in fields) for e in rows]


def _section_not_run(a_rec, b_rec, name):
    if a_rec is None or b_rec is None:
        return "missing_record"
    if not has_cap(a_rec, name) or not has_cap(b_rec, name):
        return "not_collected"
    return None


def pushes(victim_rec, shooter_rec) -> list:
    """Push as data. Each push applied to the victim's own body (its own record) beside
    the shooter's record of the same push on its copy, keyed by the hit
    identity (projectile id, init stamp, contact ordinal)."""
    if victim_rec is None or not has_cap(victim_rec, "push"):
        return []
    P = IX["push_s"]
    fields = [f[0] for f in SPEC["push_s"][3]]
    vic = _keyed(victim_rec["push_s"], P)
    sho = _keyed(shooter_rec["push_o"], P) if shooter_rec is not None else []
    bad = _ambiguous(vic) | _ambiguous(sho)
    by_key = dict(zip(sho, shooter_rec["push_o"])) if shooter_rec is not None else {}
    base = _section_not_run(victim_rec, shooter_rec, "push")
    rows = []
    for k, e in zip(vic, victim_rec["push_s"]):
        row = {"pid": k[0], "s_init": k[1], "cord": k[2], "self": dict(zip(fields, e)),
               "meas": None, "d_fx": None, "d_fy": None, "d_vax": None, "d_vay": None,
               "d_pax": None, "d_pay": None, "not_run": base}
        if base is None:
            if (k[0], k[1]) in bad:
                row["not_run"] = "ambiguous"
            elif k not in by_key:
                row["not_run"] = "trimmed" if _trimmed(shooter_rec, "push_o") else "absent"
            else:
                o = by_key[k]
                row["meas"] = dict(zip(fields, o))
                for f in ("fx", "fy", "vax", "vay", "pax", "pay"):
                    row["d_" + f] = e[P[f]] - o[P[f]]
        rows.append(row)
    return rows


def chains(victim_rec, shooter_rec) -> list:
    """The hit chain. The chain of one hit from the shooter's decision to the victim's
    screen, by hit identity: the shooter's decision, hit message and damage
    and force creation; the victim's receipt of both, its health change and
    the first rendered frame after it. Every interval is on the shared stamp
    clock; one needing the other seat's entry is NOT-RUN without it."""
    if victim_rec is None or not has_cap(victim_rec, "chain"):
        return []
    S, O = IX["ch_s"], IX["ch_o"]
    vic = _keyed(victim_rec["ch_s"], S)
    sho = _keyed(shooter_rec["ch_o"], O) if shooter_rec is not None else []
    bad = _ambiguous(vic) | _ambiguous(sho)
    by_key = dict(zip(sho, shooter_rec["ch_o"])) if shooter_rec is not None else {}
    base = _section_not_run(victim_rec, shooter_rec, "chain")
    rows = []
    for k, e in zip(vic, victim_rec["ch_s"]):
        row = {"pid": k[0], "s_init": k[1], "cord": k[2], "hp_d": e[S["hp_d"]],
               "rcv_to_hp": wrap(e[S["t_hp"]] - e[S["t_rcv"]]),
               "hp_to_frame": wrap(e[S["t_frame"]] - e[S["t_hp"]]),
               "dec_to_msg": None, "msg_transit": None, "dmg_transit": None,
               "decision_to_screen": None, "not_run": base}
        if base is None:
            if (k[0], k[1]) in bad:
                row["not_run"] = "ambiguous"
            elif k not in by_key:
                row["not_run"] = "trimmed" if _trimmed(shooter_rec, "ch_o") else "absent"
            else:
                o = by_key[k]
                row["dec_to_msg"] = wrap(o[O["t_msg"]] - o[O["t_dec"]])
                row["msg_transit"] = wrap(e[S["t_rcv"]] - o[O["t_msg"]])
                row["dmg_transit"] = wrap(e[S["t_dmg_rcv"]] - o[O["t_dmg"]])
                row["decision_to_screen"] = wrap(e[S["t_frame"]] - o[O["t_dec"]])
        rows.append(row)
    return rows


def _turn_mrad(ovx, ovy, nvx, nvy):
    cross = ovx * nvy - ovy * nvx
    dot = ovx * nvx + ovy * nvy
    return round(abs(math.atan2(cross, dot)) * PER_MILLE)


def velocity_changes(owner_rec, meas_rec) -> dict:
    """Owner velocity changes. The owner's own account (SELF-STATED) of every authoritative
    change of its projectiles' velocity, with the cause bits named, and of
    every target-bounce selection with the candidates as the owner computed
    them, beside the other seat's measured target-bounce entry for the same
    projectile when it has one."""
    out = {"changes": [], "bounces": [], "meas_unpaired": [], "label": LABEL_SELF,
           "not_run": None if has_cap(owner_rec, "vchg") else
           ("missing_record" if owner_rec is None else "not_collected")}
    if out["not_run"] is not None:
        return out
    V, Bx = IX["vchg"], IX["bsel"]
    names = sorted(W["cause"], key=lambda n: W["cause"][n])
    for e in owner_rec["vchg"]:
        cause = e[V["cause"]]
        out["changes"].append({
            "pid": e[V["pid"]], "s_init": e[V["s_init"]], "stamp": e[V["stamp"]], "cause": cause,
            "causes": [n for n in names if cause & W["cause"][n]],
            "old": [e[V["ovx"]], e[V["ovy"]]], "new": [e[V["nvx"]], e[V["nvy"]]],
            "turn_mrad": _turn_mrad(e[V["ovx"]], e[V["ovy"]], e[V["nvx"]], e[V["nvy"]])})
    # Each owner selection pairs with the other seat's measured target bounce
    # of the SAME event: projectile id, init stamp and the bounce's sender
    # stamp (the owner's selection stamp is the stamp it sends the new
    # velocity under). A key listed more than once on either side is
    # ambiguous and pairs with nothing.
    T = IX["p3tb"]
    tb_fields = [f[0] for f in SPEC["p3tb"][3]]
    meas_keys = ([(e[T["pid"]], e[T["s_init"]], e[T["s_rel"]]) for e in meas_rec["p3tb"]]
                 if meas_rec is not None else [])
    meas_count = Counter(meas_keys)
    meas_by = dict(zip(meas_keys, meas_rec["p3tb"])) if meas_rec is not None else {}
    own_count = Counter((e[Bx["pid"]], e[Bx["s_init"]], e[Bx["stamp"]]) for e in owner_rec["bsel"])
    for e in owner_rec["bsel"]:
        d_self, d_other = e[Bx["d_self"]], e[Bx["d_other"]]
        nearer = None
        if d_self >= 0 and d_other >= 0:
            nearer = "self" if d_self < d_other else ("other" if d_other < d_self else "equal")
        target = e[Bx["target"]]
        key = (e[Bx["pid"]], e[Bx["s_init"]], e[Bx["stamp"]])
        meas, why = None, None
        if meas_rec is None:
            why = "missing_record"
        elif own_count[key] != 1 or meas_count[key] > 1:
            why = "ambiguous"
        elif meas_count[key] == 1:
            meas = dict(zip(tb_fields, meas_by[key]))
        else:
            why = "trimmed" if _trimmed(meas_rec, "p3tb") else "absent"
        out["bounces"].append({
            "pid": e[Bx["pid"]], "s_init": e[Bx["s_init"]], "stamp": e[Bx["stamp"]],
            "target": next(n for n, v in W["bounce_target"].items() if v == target),
            "d_self": d_self, "los_self": e[Bx["los_self"]],
            "d_other": d_other, "los_other": e[Bx["los_other"]], "nearer": nearer,
            "meas": meas, "meas_not_run": why})
    # Measured target bounces no owner selection names: shown, never paired.
    gap = "trimmed" if _trimmed(owner_rec, "bsel") else "absent"
    out["meas_unpaired"] = [dict(zip(tb_fields, e), not_run="ambiguous" if meas_count[k] > 1 else gap)
                            for k, e in zip(meas_keys, meas_rec["p3tb"] if meas_rec else [])
                            if not own_count[k]]
    return out


def deaths(own_rec, other_rec) -> list:
    """Boundary deaths. Each boundary death of one seat as that seat recorded it, beside
    the other seat's record of the same death (by death ordinal): cause,
    boundary edge, position and velocity before the death, the recent hit
    and force identities (each resolved against the seat's own push list).

    A recent hit's `push_listed` is True when the seat's own push list holds
    it; False only when that list is whole (collected, nothing omitted), so
    absence is proven; otherwise None with `push_not_run` naming why
    (`not_collected`, `trimmed`)."""
    if own_rec is None or not has_cap(own_rec, "death"):
        return []
    D = IX["bd_s"]
    fields = [f[0] for f in SPEC["bd_s"][3]]
    pushes_own = set(_keyed(own_rec["push_s"], IX["push_s"])) if has_cap(own_rec, "push") else None
    push_gap = ("not_collected" if pushes_own is None else
                "trimmed" if _trimmed(own_rec, "push_s") else None)
    theirs = {}
    if other_rec is not None:
        for e in other_rec["bd_o"]:
            theirs.setdefault(e[D["ord"]], []).append(e)
    base = _section_not_run(own_rec, other_rec, "death")
    rows = []
    for e in own_rec["bd_s"]:
        hits = []
        for i in range(W["recent_hits"]):
            p = "h%d_" % (i + 1)
            if e[D[p + "pid"]] < 0:
                continue
            key = (e[D[p + "pid"]], e[D[p + "s_init"]], e[D[p + "cord"]])
            listed = pushes_own is not None and key in pushes_own
            hits.append({"pid": key[0], "s_init": key[1], "cord": key[2], "age": e[D[p + "age"]],
                         "push_listed": True if listed else (None if push_gap else False),
                         "push_not_run": None if listed else push_gap})
        row = {"self": dict(zip(fields, e)), "meas": None, "hits": hits, "d_px": None,
               "d_py": None, "d_vx": None, "d_vy": None, "not_run": base}
        if base is None:
            cand = theirs.get(e[D["ord"]], [])
            if len(cand) != 1:
                row["not_run"] = ("ambiguous" if cand else
                                  ("trimmed" if _trimmed(other_rec, "bd_o") else "absent"))
            else:
                o = cand[0]
                row["meas"] = dict(zip(fields, o))
                for f in ("px", "py", "vx", "vy"):
                    row["d_" + f] = e[D[f]] - o[D[f]]
        rows.append(row)
    return rows


# The whole-record rows a record states once (never trimmed), by wire key.
RECORD_ROWS = ("tb_tot", "tot_s", "tot_o", "p3n", "p3self", "b5_tot", "r_tot")
# The four reaction-and-aim sets, in layout order; `a1sum` holds one row per set.
A1_SETS = tuple(k for k in KEYS if SPEC[k][0] == "hist" and k.startswith("a"))


def _record_row(rec, seat, other, faults):
    """One record's own whole-game statements: frame time, the latency
    estimate, the collectors' cost, the whole-game rows, the summaries of the
    four aim sets, and per list its listed and omitted counts (a list with a
    non-zero omitted count is trimmed: its listed count is no whole count)."""
    cost = [_named(e, SPEC["cost"][2]) for e in rec["cost"]]
    row = {"seat": seat, "other": other, "consts": rec["consts"], "caps": rec["caps"],
           "t0": rec["t0"], "t0_src": rec["t0_src"],
           "frame_p50_us": rec["frame_p50_us"], "l_hat": rec["l_hat"],
           "cost": {f[0]: sum(c[f[0]] for c in cost) for f in SPEC["cost"][2]},
           "a1sum": {s: _named(e, SPEC["a1sum"][2]) for s, e in zip(A1_SETS, rec["a1sum"])},
           "listed": {k: len(rec[k]) for k in LISTS}, "omitted": dict(rec["omit"]),
           "faults": faults}
    for k in RECORD_ROWS:
        row[k] = _named(rec[k], SPEC[k][1])
    return row


def pair_view(records: list) -> dict:
    """The public description of one game's combat records. `records` are
    the stored records of ONE stable game key and ONE canonical seat pair:
    dicts with `seat`, `other` and `rec`. Two records pair only when each
    names the other."""
    by_seat = {r["seat"]: r for r in records}
    two = len(records) == 2 and all(r["other"] in by_seat for r in records)
    seats = sorted({r["seat"] for r in records} | {r["other"] for r in records}, key=str)
    view = {"records": len(records), "paired": two, "seats": [str(s) for s in seats],
            "consts": {str(r["seat"]): r["rec"]["consts"] for r in records},
            "directions": [], "blocks": [], "contacts": [], "points": [], "b3": [], "b1": [],
            "pushes": [], "chains": [], "velocity": [], "deaths": [], "react": [], "interval": [],
            "refused": [], "record": [], "faults": {}}
    for r in records:
        view["faults"][str(r["seat"])] = {"own_gun": rebuild_faults(r["rec"], "s"),
                                         "other_gun": rebuild_faults(r["rec"], "o"),
                                         "sections": section_faults(r["rec"])}
    for owner in seats:
        owner_r = by_seat.get(owner)
        meas_r = next((r for r in records if r["other"] == owner and r["seat"] != owner), None)
        if owner_r is not None and meas_r is not None and owner_r["other"] != meas_r["seat"]:
            meas_r = None
        if owner_r is None and meas_r is None:
            continue
        compat = owner_r is None or meas_r is None or consts_ok(owner_r["rec"], meas_r["rec"])
        d = direction(owner_r["rec"] if owner_r else None, meas_r["rec"] if meas_r else None,
                      compatible=compat)
        d["owner"] = str(owner)
        view["directions"].append(d)
        victim = owner_r
        shooter = meas_r
        b_rows = blocks(victim["rec"] if victim else None, shooter["rec"] if shooter else None)
        c_rows = contacts(victim["rec"] if victim else None, shooter["rec"] if shooter else None)
        if not compat:
            for r in b_rows:
                r.update(d_open=None, d_len=None, d_len_g=None, d_pred=None, d_pred_lo=None,
                         d_pred_hi=None, meas=None, not_run="incompatible")
            for r in c_rows:
                r.update(since_ms=None, pred_since=None, contact_to_decision=None,
                         not_run="incompatible")
        view["blocks"].append({"victim": str(owner), "rows": b_rows,
                               "not_run": (None if victim and shooter and compat else
                                           "incompatible" if victim and shooter else
                                           "missing_record")})
        view["contacts"].append({"victim": str(owner), "rows": c_rows})
        own_rec, other_rec = (owner_r["rec"] if owner_r else None), (meas_r["rec"] if meas_r else None)
        p_rows, ch_rows = pushes(own_rec, other_rec), chains(own_rec, other_rec)
        vel, d_rows = velocity_changes(own_rec, other_rec), deaths(own_rec, other_rec)
        if not compat:
            for r in p_rows:
                r.update(meas=None, d_fx=None, d_fy=None, d_vax=None, d_vay=None, d_pax=None,
                         d_pay=None, not_run="incompatible")
            for r in ch_rows:
                r.update(dec_to_msg=None, msg_transit=None, dmg_transit=None,
                         decision_to_screen=None, not_run="incompatible")
            for r in d_rows:
                r.update(meas=None, d_px=None, d_py=None, d_vx=None, d_vy=None,
                         not_run="incompatible")
            for b in vel["bounces"]:
                b.update(meas=None, meas_not_run="incompatible")
            for b in vel["meas_unpaired"]:
                b["not_run"] = "incompatible"
        view["pushes"].append({"victim": str(owner), "rows": p_rows,
                               "not_run": _own_section(own_rec, "push")})
        view["chains"].append({"victim": str(owner), "rows": ch_rows,
                               "not_run": _own_section(own_rec, "chain")})
        view["velocity"].append(dict(vel, owner=str(owner)))
        view["deaths"].append({"seat": str(owner), "rows": d_rows,
                               "not_run": _own_section(own_rec, "death")})
    for r in records:
        rec = r["rec"]
        seat, other = str(r["seat"]), str(r["other"])
        view["points"].append({"seat": seat,
                               "rows": [_point_row(rec, e[TB["pt"]]) for e in rec["tb"]],
                               "omitted": rec["omit"]["tb"], "label": LABEL_SELF})
        view["b3"].append({"measuring_seat": seat, "subject": other, "label": LABEL_MEAS,
                           "counts": _named(rec["p3n"], SPEC["p3n"][1]),
                           "top": [_named(e, SPEC["p3top"][3]) for e in rec["p3top"]],
                           "target_bounces": [_named(e, SPEC["p3tb"][3]) for e in rec["p3tb"]],
                           "homing_top": [_named(e, SPEC["p3ht"][3]) for e in rec["p3ht"]],
                           "homing_hist": list(rec["p3hm"]),
                           "tb_not_run": "trimmed" if rec["omit"]["p3tb"] else None,
                           "hm_not_run": "trimmed" if rec["omit"]["p3ht"] else None,
                           "omitted": {k: rec["omit"][k] for k in ("p3top", "p3tb", "p3ht")}})
        view["react"].append({"seat": seat, "other": other,
                              "own": [_named(e, SPEC["rx_s"][3]) for e in rec["rx_s"]],
                              "copy": [_named(e, SPEC["rx_o"][3]) for e in rec["rx_o"]],
                              "omitted": {k: rec["omit"][k] for k in ("rx_s", "rx_o")}})
        view["interval"].append({"seat": seat, "other": other,
                                 "own": [_named(e, SPEC["ivl_s"][3]) for e in rec["ivl_s"]],
                                 "copy": [_named(e, SPEC["ivl_o"][3]) for e in rec["ivl_o"]]})
        view["refused"].append({"seat": seat, "label": LABEL_SELF,
                                "rows": [_named(e, SPEC["b5_r"][3]) for e in rec["b5_r"]],
                                "omitted": rec["omit"]["b5_r"]})
        view["record"].append(_record_row(rec, seat, other, view["faults"][seat]))
    for owner in seats:
        own = by_seat.get(owner)
        meas = next((r for r in records if r["other"] == owner and r["seat"] != owner), None)
        row = {"subject": str(owner), "self": None, "meas": None, "not_run": None}
        if own is not None:
            row["self"] = {"a1s": own["rec"]["a1s"], "a1p": own["rec"]["a1p"],
                           "label": LABEL_SELF} if consts_ok(own["rec"]) else None
        if meas is not None:
            row["meas"] = {"a1m": meas["rec"]["a1m"], "a1n": meas["rec"]["a1n"],
                           "label": LABEL_MEAS} if consts_ok(meas["rec"]) else None
        if own is None or meas is None:
            row["not_run"] = "missing_record"
        elif not consts_ok(own["rec"], meas["rec"]):
            row["not_run"] = "incompatible"
        view["b1"].append(row)
    return view


# -- evaluation subjects and the public measures ------------------------------------

class CombatCtx:
    """One row of one subject of one game's pair view."""

    __slots__ = ("i", "row", "view", "module")

    def __init__(self, i, row, view):
        self.i = i
        self.row = row
        self.view = view
        self.module = None


def combat_subjects(view: dict) -> dict:
    """The rows each combat subject evaluates over, from a pair view."""
    out = {name: [] for name in rm.COMBAT_SUBJECTS}

    def add(subject, row):
        out[subject].append(CombatCtx((subject, len(out[subject])), row, view))

    for d in view["directions"]:
        add("combat.direction", d)
        for cyc in d["cycles"]:
            for account in ("self", "meas"):
                if cyc[account] is not None:
                    add("combat.cycle", dict(cyc[account], account=account, owner=d["owner"],
                                             s0=cyc["s0"], pt=cyc["pt"]))
                    for ev in cyc[account]["regens"]:
                        add("combat.regen", dict(ev, account=account, owner=d["owner"],
                                                 s0=cyc["s0"],
                                                 events_complete=cyc[account]["events_complete"]))
            for s in cyc["shots"]:
                add("combat.shot", dict(s, owner=d["owner"], case=d["case"]))
            if cyc["refill"] is not None:
                add("combat.refill", dict(cyc["refill"], owner=d["owner"], s0=cyc["s0"],
                                          meas=cyc["meas"], self=cyc["self"],
                                          clock=cyc["clock"]))
        for st in d["stat"]:
            add("combat.stat", dict(st, owner=d["owner"]))
    for p in view["points"]:
        for r in p["rows"]:
            if r is not None:
                add("combat.point", dict(r, seat=p["seat"]))
    for b in view["blocks"]:
        for r in b["rows"]:
            add("combat.block", dict(r, victim=b["victim"]))
    for c in view["contacts"]:
        for r in c["rows"]:
            add("combat.contact", dict(r, victim=c["victim"]))
    for b in view["b3"]:
        for r in b["top"]:
            add("combat.top", dict(r, measuring_seat=b["measuring_seat"]))
    for r in view["b1"]:
        add("combat.aim", r)
    for p in view["pushes"]:
        for r in p["rows"]:
            add("combat.push", dict(r, victim=p["victim"]))
    for v in view["velocity"]:
        for r in v["changes"]:
            add("combat.vchange", dict(r, owner=v["owner"]))
        for r in v["bounces"]:
            add("combat.bounce", dict(r, owner=v["owner"]))
    for c in view["chains"]:
        for r in c["rows"]:
            add("combat.chain", dict(r, victim=c["victim"]))
    for d in view["deaths"]:
        for r in d["rows"]:
            add("combat.death", dict(r, seat=d["seat"]))
    for b in view["b3"]:
        add("combat.b3", b)
        for r in b["target_bounces"]:
            add("combat.tbounce", dict(r, measuring_seat=b["measuring_seat"], subject=b["subject"]))
        for r in b["homing_top"]:
            add("combat.homing", dict(r, measuring_seat=b["measuring_seat"], subject=b["subject"]))
    for x in view["react"]:
        for account, rows, subject in (("self", x["own"], x["seat"]), ("meas", x["copy"], x["other"])):
            for r in rows:
                add("combat.react", dict(r, seat=x["seat"], account=account, subject=subject))
    for x in view["interval"]:
        for account, rows, subject in (("self", x["own"], x["seat"]), ("meas", x["copy"], x["other"])):
            for r in rows:
                add("combat.interval", dict(r, seat=x["seat"], account=account, subject=subject))
    for x in view["refused"]:
        for r in x["rows"]:
            add("combat.refused", dict(r, seat=x["seat"]))
    for r in view["record"]:
        add("combat.record", r)
    return out


def cmeasure(name, subject, consts=False, field=None):
    """Register a combat measure. `consts` declares that the measure reads an
    input whose meaning depends on the record's measurement version: it then
    answers None unless every record it reads is of a version this server
    reads and, for a two-record input, the same one. `field` names the input
    of a generated measure (one function read at several fields): it is part
    of the entry's data, so each generated entry has its own fingerprint."""
    data = {"consts": bool(consts)}
    if field is not None:
        data["field"] = field

    def deco(fn):
        rm._register(rm.Entry("measure", name, (fn,), subject=subject, data=data))
        return fn
    return deco


def _get(ctx, key):
    v = ctx.row.get(key)
    return v


def _sub(ctx, account, key):
    a = ctx.row.get(account)
    return None if a is None else a.get(key)


def _sum_why(ctx):
    w = ctx.row.get("why")
    return None if w is None else w


@cmeasure("b2.cycle.account", "combat.cycle")
def m_cycle_account(ctx, p):
    return ctx.row["account"]


@cmeasure("b2.cycle.units", "combat.cycle")
def m_cycle_units(ctx, p):
    return _get(ctx, "units")


@cmeasure("b2.cycle.mag_plus_regen", "combat.cycle")
def m_cycle_mag_regen(ctx, p):
    mag, rg = ctx.row.get("mag"), ctx.row.get("regen")
    return None if mag is None or rg is None else mag + rg


@cmeasure("b2.cycle.in_rl", "combat.cycle")
def m_cycle_in_rl(ctx, p):
    return _get(ctx, "in_rl")


@cmeasure("b2.cycle.tail", "combat.cycle")
def m_cycle_tail(ctx, p):
    return _get(ctx, "tail")


@cmeasure("b2.cycle.gap_first", "combat.cycle")
def m_cycle_gap_first(ctx, p):
    g = ctx.row.get("gaps")
    return None if g is None or g[0] < 0 else g[0]


@cmeasure("b2.cycle.gap_second", "combat.cycle")
def m_cycle_gap_second(ctx, p):
    g = ctx.row.get("gaps")
    return None if g is None or g[1] < 0 else g[1]


@cmeasure("b2.cycle.gap_third", "combat.cycle")
def m_cycle_gap_third(ctx, p):
    g = ctx.row.get("gaps")
    return None if g is None or g[2] < 0 else g[2]


@cmeasure("b2.cycle.rexp", "combat.cycle")
def m_cycle_rexp(ctx, p):
    return _get(ctx, "rexp")


@cmeasure("b2.cycle.why", "combat.cycle")
def m_cycle_why(ctx, p):
    return _sum_why(ctx)


@cmeasure("b2.cycle.end", "combat.cycle")
def m_cycle_end(ctx, p):
    return _get(ctx, "end")


@cmeasure("b2.cycle.excess", "combat.cycle")
def m_cycle_excess(ctx, p):
    return _get(ctx, "excess")


@cmeasure("b2.cycle.regen", "combat.cycle")
def m_cycle_regen(ctx, p):
    """Units regenerated in the cycle, derived from its event stream; None
    when that stream is not whole."""
    return _get(ctx, "regen")


@cmeasure("b2.cycle.regen_stated", "combat.cycle")
def m_cycle_regen_stated(ctx, p):
    return _get(ctx, "regen_stated")


@cmeasure("b2.shot.d_ammo", "combat.shot")
def m_shot_d_ammo(ctx, p):
    return _get(ctx, "d_ammo")


@cmeasure("b2.shot.d_reloading", "combat.shot")
def m_shot_d_reloading(ctx, p):
    return _get(ctx, "d_reloading")


@cmeasure("b2.shot.d_counter", "combat.shot")
def m_shot_d_counter(ctx, p):
    return _get(ctx, "d_counter")


@cmeasure("b2.shot.absent", "combat.shot")
def m_shot_absent(ctx, p):
    """Which account lacks this projectile (a count difference), or None."""
    return _get(ctx, "absent_in")


@cmeasure("b2.shot.owner_gate_flags", "combat.shot", consts=True)
def m_shot_owner_flags(ctx, p):
    s = ctx.row.get("self")
    if s is None or s.get("rep") != 0 or not _row_consts_ok(ctx, "owner"):
        return None
    return s["fl"]


@cmeasure("b2.shot.owner_since", "combat.shot", consts=True)
def m_shot_owner_since(ctx, p):
    s = ctx.row.get("self")
    if s is None or s.get("rep") != 0 or not _row_consts_ok(ctx, "owner"):
        return None
    return s["since"]


def _row_consts_ok(ctx, who) -> bool:
    v = ctx.view["consts"].get(ctx.row[who])
    return v is not None and v in W["consts_known"]


@cmeasure("b2.stat.d_mag", "combat.stat")
def m_stat_d_mag(ctx, p):
    d = ctx.row.get("diff")
    return None if d is None else d["d_mag"]


@cmeasure("b2.stat.d_rexp", "combat.stat")
def m_stat_d_rexp(ctx, p):
    d = ctx.row.get("diff")
    return None if d is None else d["d_rexp"]


@cmeasure("b2.stat.d_rtm", "combat.stat")
def m_stat_d_rtm(ctx, p):
    d = ctx.row.get("diff")
    return None if d is None else d["d_rtm"]


@cmeasure("b2.stat.d_cexp", "combat.stat")
def m_stat_d_cexp(ctx, p):
    d = ctx.row.get("diff")
    return None if d is None else d["d_cexp"]


@cmeasure("b2.stat.d_regen", "combat.stat")
def m_stat_d_regen(ctx, p):
    d = ctx.row.get("diff")
    return None if d is None else d["d_regen"]


@cmeasure("b2.stat.d_auto", "combat.stat")
def m_stat_d_auto(ctx, p):
    d = ctx.row.get("diff")
    return None if d is None else d["d_auto"]


@cmeasure("b2.stat.fields_differing", "combat.stat")
def m_stat_fields_differing(ctx, p):
    d = ctx.row.get("diff")
    return None if d is None else sorted(k for k, v in d.items() if v)


def _clock(v):
    """A clock reading, None when the seat has none (the wire's minus one)."""
    return None if v is None or v < 0 else v


@cmeasure("b2.refill.self_rl_g", "combat.refill")
def m_refill_rl_g(ctx, p):
    return _clock(ctx.row["end"]["rl_g"][0])


@cmeasure("b2.refill.self_rl_s", "combat.refill")
def m_refill_rl_s(ctx, p):
    return _clock(ctx.row["end"]["rl_s"][0])


@cmeasure("b2.refill.self_rl_r", "combat.refill")
def m_refill_rl_r(ctx, p):
    return _clock(ctx.row["end"]["rl_r"][0])


@cmeasure("b2.refill.meas_rl_g", "combat.refill")
def m_refill_meas_rl_g(ctx, p):
    return _clock(ctx.row["end"]["rl_g"][1])


@cmeasure("b2.refill.meas_rl_s", "combat.refill")
def m_refill_meas_rl_s(ctx, p):
    return _clock(ctx.row["end"]["rl_s"][1])


@cmeasure("b2.refill.meas_rl_r", "combat.refill")
def m_refill_meas_rl_r(ctx, p):
    return _clock(ctx.row["end"]["rl_r"][1])


def _clock_d(ctx, k):
    c = ctx.row.get("clock")
    return None if c is None else c[k]


@cmeasure("b2.refill.d_rl_g", "combat.refill")
def m_refill_d_rl_g(ctx, p):
    return _clock_d(ctx, "d_rl_g")


@cmeasure("b2.refill.d_rl_s", "combat.refill")
def m_refill_d_rl_s(ctx, p):
    return _clock_d(ctx, "d_rl_s")


@cmeasure("b2.refill.d_rl_r", "combat.refill")
def m_refill_d_rl_r(ctx, p):
    return _clock_d(ctx, "d_rl_r")


@cmeasure("b2.refill.d_st_end", "combat.refill")
def m_refill_d_st_end(ctx, p):
    return _clock_d(ctx, "d_st_end")


@cmeasure("b2.refill.owner_only_units", "combat.refill")
def m_refill_owner_only(ctx, p):
    """Units of the regenerations only the owner's account lists; None
    (NOT-RUN) when either account's event list is incomplete."""
    o = ctx.row["owner_only"]
    return None if o is None else sum(r["amt"] for r in o)


@cmeasure("b2.refill.meas_only_units", "combat.refill")
def m_refill_meas_only(ctx, p):
    o = ctx.row["meas_only"]
    return None if o is None else sum(r["amt"] for r in o)


@cmeasure("b2.regen.amt", "combat.regen")
def m_regen_amt(ctx, p):
    return ctx.row["amt"]


@cmeasure("b2.regen.gap_g", "combat.regen")
def m_regen_gap_g(ctx, p):
    return _clock(ctx.row["gap_g"])


@cmeasure("b2.regen.gap_s", "combat.regen")
def m_regen_gap_s(ctx, p):
    return _clock(ctx.row["gap_s"])


@cmeasure("b2.regen.gap_r", "combat.regen")
def m_regen_gap_r(ctx, p):
    return _clock(ctx.row["gap_r"])


@cmeasure("b2.regen.stream_whole", "combat.regen")
def m_regen_whole(ctx, p):
    """Whether the cycle's refill-event list is whole (every event the
    header counts is listed)."""
    return ctx.row["events_complete"]


@cmeasure("b2.atk.d_count", "combat.direction")
def m_atk_d_count(ctx, p):
    return ctx.row["attacks"]["d_emit_msgs"]


@cmeasure("b2.direction.case", "combat.direction")
def m_direction_case(ctx, p):
    return ctx.row["case"]


@cmeasure("b2.direction.differs_by", "combat.direction")
def m_direction_differs_by(ctx, p):
    """The classes of field the two accounts differ in (shot, cycle, clock,
    refill, stat, attacks, totals); None unless both accounts were compared."""
    return ctx.row["differs_by"] if ctx.row["case"] in ("both_agree", "both_differ") else None


@cmeasure("b2.totals.d_units", "combat.direction")
def m_totals_d_units(ctx, p):
    d = ctx.row["totals"]["diff"]
    return None if d is None else d["d_units"]


@cmeasure("tb.point.game_real", "combat.point")
def m_point_game_real(ctx, p):
    return _get(ctx, "game_real_pm")


@cmeasure("tb.point.srv_real", "combat.point")
def m_point_srv_real(ctx, p):
    return _get(ctx, "srv_real_pm")


@cmeasure("tb.point.base", "combat.point")
def m_point_base(ctx, p):
    return _get(ctx, "base")


@cmeasure("b5.pair.d_open", "combat.block")
def m_block_d_open(ctx, p):
    return _get(ctx, "d_open")


@cmeasure("b5.pair.d_len", "combat.block")
def m_block_d_len(ctx, p):
    return _get(ctx, "d_len")


@cmeasure("b5.pair.d_pred_lo", "combat.block")
def m_block_d_pred_lo(ctx, p):
    return _get(ctx, "d_pred_lo")


@cmeasure("b5.pair.d_pred_hi", "combat.block")
def m_block_d_pred_hi(ctx, p):
    return _get(ctx, "d_pred_hi")


@cmeasure("b5.contact.since_c", "combat.contact")
def m_contact_since_c(ctx, p):
    v = _get(ctx, "since_c")
    return None if v is None or v < 0 else v


@cmeasure("b5.contact.since_ms", "combat.contact")
def m_contact_since_ms(ctx, p):
    v = _get(ctx, "since_ms")
    return None if v is None or v < 0 else v


@cmeasure("b5.contact.own_since", "combat.contact")
def m_contact_own_since(ctx, p):
    v = _get(ctx, "own_since")
    return None if v is None or v < 0 else v


@cmeasure("b3.top.d_perp", "combat.top", consts=True)
def m_top_d_perp(ctx, p):
    if not _row_consts_ok(ctx, "measuring_seat"):
        return None
    return ctx.row["d_perp"]


@cmeasure("b3.top.mask", "combat.top")
def m_top_mask(ctx, p):
    return ctx.row["mask"]


@cmeasure("b3.top.speed", "combat.top")
def m_top_speed(ctx, p):
    return ctx.row["speed"]


@cmeasure("b1.hist.compatible", "combat.aim", consts=True)
def m_aim_compatible(ctx, p):
    """Whether both histograms of this subject can be set side by side: None
    (NOT-RUN) with a record missing, else whether their versions agree."""
    if ctx.row["not_run"] == "missing_record":
        return None
    return ctx.row["not_run"] is None


@cmeasure("b1.hist.meas_volleys", "combat.aim", consts=True)
def m_aim_meas_volleys(ctx, p):
    m = ctx.row.get("meas")
    return None if m is None else sum(m["a1m"])


@cmeasure("b1.hist.self_volleys", "combat.aim", consts=True)
def m_aim_self_volleys(ctx, p):
    s = ctx.row.get("self")
    return None if s is None else sum(s["a1s"])


@cmeasure("b5.push.d_fx", "combat.push")
def m_push_d_fx(ctx, p):
    return _get(ctx, "d_fx")


@cmeasure("b5.push.d_fy", "combat.push")
def m_push_d_fy(ctx, p):
    return _get(ctx, "d_fy")


@cmeasure("b5.push.d_vax", "combat.push")
def m_push_d_vax(ctx, p):
    return _get(ctx, "d_vax")


@cmeasure("b5.push.d_vay", "combat.push")
def m_push_d_vay(ctx, p):
    return _get(ctx, "d_vay")


@cmeasure("b5.push.mass", "combat.push")
def m_push_mass(ctx, p):
    return ctx.row["self"]["mass"]


@cmeasure("b3.vchange.cause", "combat.vchange")
def m_vchange_cause(ctx, p):
    return ctx.row["cause"]


@cmeasure("b3.vchange.turn_mrad", "combat.vchange")
def m_vchange_turn(ctx, p):
    return ctx.row["turn_mrad"]


@cmeasure("b3.bounce.target", "combat.bounce")
def m_bounce_target(ctx, p):
    return ctx.row["target"]


@cmeasure("b3.bounce.nearer", "combat.bounce")
def m_bounce_nearer(ctx, p):
    return ctx.row["nearer"]


@cmeasure("b5.chain.msg_transit", "combat.chain")
def m_chain_msg(ctx, p):
    return _get(ctx, "msg_transit")


@cmeasure("b5.chain.dmg_transit", "combat.chain")
def m_chain_dmg(ctx, p):
    return _get(ctx, "dmg_transit")


@cmeasure("b5.chain.decision_to_screen", "combat.chain")
def m_chain_screen(ctx, p):
    return _get(ctx, "decision_to_screen")


@cmeasure("b5.chain.hp_to_frame", "combat.chain")
def m_chain_frame(ctx, p):
    return _get(ctx, "hp_to_frame")


@cmeasure("death.boundary.cause", "combat.death")
def m_death_cause(ctx, p):
    return ctx.row["self"]["cause"]


@cmeasure("death.boundary.edge", "combat.death")
def m_death_edge(ctx, p):
    return ctx.row["self"]["edge"]


@cmeasure("death.boundary.recent_hits", "combat.death")
def m_death_hits(ctx, p):
    return len(ctx.row["hits"])


@cmeasure("death.boundary.d_px", "combat.death")
def m_death_d_px(ctx, p):
    return _get(ctx, "d_px")


# -- the remaining descriptive inputs: one entry per field, generated -----------------
#
# Each generated entry reads ONE named field of its subject's row; the field
# is in the entry's data (its own fingerprint). A clock or interval field
# whose wire value is minus one (the seat has none) answers None. Rows exist
# only for listed entries: a trimmed list's absence is read through the
# record subject's `rec.listed.<key>` (None while the list is trimmed) and
# `rec.omitted.<key>`.

def _gen(name, subject, key, consts=False, clock=False, sub=None):
    """Register `name` as the value of row field `key` (inside the row's
    `sub` dict when given)."""
    def fn(ctx, p):
        row = ctx.row if sub is None else ctx.row.get(sub)
        v = None if row is None else row.get(key)
        if clock and v is not None and v < 0:
            return None
        if consts and not _row_consts_ok(ctx, "measuring_seat" if "measuring_seat" in ctx.row
                                         else "seat"):
            return None
        return v
    cmeasure(name, subject, consts=consts, field=[sub, key, clock])(fn)
    return fn


for _f in ("slow", "ramp", "clamp", "frames", "dt_med_us", "dt_max_us", "real", "game", "srv",
           "ps"):
    _gen("tb.point." + _f, "combat.point", _f)
for _f in ("cd", "gap_prev", "len_g", "reopen", "scale_pm", "press", "fr"):
    _gen("b5.ctl." + _f, "combat.block", _f, clock=_f in ("gap_prev", "len_g"), sub="self")
for _f in ("cd_c", "gap_prev_s", "len_cg", "started", "reopen_c", "ta", "o_pred"):
    _gen("b5.ctl." + _f, "combat.block", _f, clock=_f in ("gap_prev_s", "len_cg"), sub="meas")
_gen("b5.pair.d_len_g", "combat.block", "d_len_g")
_gen("b5.pair.frame_bound", "combat.block", "frame_bound")
_gen("b5.contact.pred_since", "combat.contact", "pred_since")
_gen("b5.contact.contact_to_decision", "combat.contact", "contact_to_decision")
_gen("b5.refused.since_prev", "combat.refused", "since_prev", clock=True)
_gen("b5.refused.cd", "combat.refused", "cd")
for _f in ("aim_on", "first"):
    _gen("b1.react." + _f, "combat.react", _f, clock=True)
_gen("b1.react.err", "combat.react", "err", consts=True)
_gen("b1.react.account", "combat.react", "account")
for _f in ("gmin", "cexp_min"):
    _gen("b2.ivl." + _f, "combat.interval", _f, clock=True)
for _f in ("vmax", "vexp", "refreshes", "account"):
    _gen("b2.ivl." + _f, "combat.interval", _f)
_gen("b3.tb.gap", "combat.tbounce", "gap", consts=True, clock=True)
_gen("b3.tb.has_retarget", "combat.tbounce", "has_retarget")
_gen("b3.tb.ang_to_me", "combat.tbounce", "ang_to_me", consts=True)
_gen("b3.hm.ratio_pm", "combat.homing", "ratio_pm", consts=True)
_gen("b3.hm.packages", "combat.homing", "n")
_gen("b3.top.d_along", "combat.top", "d_along", consts=True)
_gen("b3.top.ang", "combat.top", "ang", consts=True)
_gen("b3.top.dt", "combat.top", "dt")
for _k in RECORD_ROWS:
    for _fd in SPEC[_k][1]:
        _gen("rec.%s.%s" % (_k, _fd[0]), "combat.record", _fd[0], sub=_k)
for _fd in SPEC["cost"][2]:
    _gen("rec.cost." + _fd[0], "combat.record", _fd[0], sub="cost")
for _k in LISTS:
    _gen("rec.omitted." + _k, "combat.record", _k, sub="omitted")
for _f in ("frame_p50_us", "caps", "t0", "t0_src"):
    _gen("rec." + _f, "combat.record", _f)
for _fd in SPEC["gun_s"][3]:
    if _fd[0] == "pt":
        continue
    _gen("b2.stat.self." + _fd[0], "combat.stat", _fd[0], sub="self")
    _gen("b2.stat.meas." + _fd[0], "combat.stat", _fd[0], sub="meas")
    if "b2.stat.d_" + _fd[0] not in rm.REGISTRY:
        _gen("b2.stat.d_" + _fd[0], "combat.stat", "d_" + _fd[0], sub="diff")
_gen("rec.l_hat", "combat.record", "l_hat", clock=True)


@cmeasure("rec.listed", "combat.record")
def m_rec_listed(ctx, p):
    """Per list: its listed count when the list is whole, None (NOT-RUN)
    while the budgeter trimmed it."""
    return {k: (None if ctx.row["omitted"][k] else n) for k, n in ctx.row["listed"].items()}


@cmeasure("rec.a1sum", "combat.record", consts=True)
def m_rec_a1sum(ctx, p):
    if not _row_consts_ok(ctx, "seat"):
        return None
    return ctx.row["a1sum"]


@cmeasure("rec.faults", "combat.record")
def m_rec_faults(ctx, p):
    """Every rebuild and section fault of the record, flattened and sorted."""
    f = ctx.row["faults"]
    return sorted(f["own_gun"] + f["other_gun"] + f["sections"])


@cmeasure("b3.tb.min_gap", "combat.b3", consts=True)
def m_b3_tb_min_gap(ctx, p):
    """The smallest target-bounce gap the measuring seat listed; None when
    its list was trimmed or holds no gap."""
    if ctx.row["tb_not_run"] or not _row_consts_ok(ctx, "measuring_seat"):
        return None
    gaps = [r["gap"] for r in ctx.row["target_bounces"] if r["gap"] >= 0]
    return min(gaps) if gaps else None


@cmeasure("b3.hm.max_ratio_pm", "combat.b3", consts=True)
def m_b3_hm_max_ratio(ctx, p):
    """The largest homing turn ratio (per mille of the code's bound) the
    measuring seat listed; None when its list was trimmed or is empty."""
    if ctx.row["hm_not_run"] or not _row_consts_ok(ctx, "measuring_seat"):
        return None
    vals = [r["ratio_pm"] for r in ctx.row["homing_top"]]
    return max(vals) if vals else None


@cmeasure("b3.hm.hist", "combat.b3", consts=True)
def m_b3_hm_hist(ctx, p):
    if not _row_consts_ok(ctx, "measuring_seat"):
        return None
    return ctx.row["homing_hist"]


@cmeasure("b3.counts", "combat.b3")
def m_b3_counts(ctx, p):
    return ctx.row["counts"]


@cmeasure("b3.bounce.meas_gap", "combat.bounce", consts=True)
def m_bounce_meas_gap(ctx, p):
    """The other seat's measured gap of this exact bounce; None when that
    entry is missing, trimmed, ambiguous or of another version."""
    m = ctx.row.get("meas")
    if m is None or m["gap"] < 0 or not _row_consts_ok(ctx, "owner"):
        return None
    return m["gap"]


@cmeasure("death.boundary.push_unlisted", "combat.death")
def m_death_push_unlisted(ctx, p):
    """How many recent hits the seat's own push list proves it lacks; None
    when the list cannot prove absence (trimmed or not collected)."""
    hits = ctx.row["hits"]
    if any(h["push_listed"] is None for h in hits):
        return None
    return sum(1 for h in hits if h["push_listed"] is False)


# -- contributions (histograms per game, per subject and source) -----------------------

def contributions(records: list) -> list:
    """Per subject seat: its own statements (SELF) from its own record, and
    the other seat's measurements of it (MEAS) from that seat's record, each
    with the contributing record's measurement version. Sums of different
    versions are never added together."""
    out = []
    for r in records:
        rec = r["rec"]
        out.append({"subject": r["seat"], "source": "self", "consts": rec["consts"],
                    "sums": {"a1s": list(rec["a1s"]), "a1p": list(rec["a1p"])}})
        out.append({"subject": r["other"], "source": "meas", "consts": rec["consts"],
                    "sums": {"a1m": list(rec["a1m"]), "a1n": list(rec["a1n"]),
                             "p3dp0": list(rec["p3dp0"]), "p3an0": list(rec["p3an0"]),
                             "p3dp1": list(rec["p3dp1"]), "p3an1": list(rec["p3an1"])}})
    return out


def add_sums(a: dict, b: dict) -> dict:
    """Bin-wise sum of two contribution sums of the same version."""
    out = {k: list(v) for k, v in a.items()}
    for k, v in b.items():
        if k in out and len(out[k]) == len(v):
            out[k] = [x + y for x, y in zip(out[k], v)]
        else:
            out[k] = list(v)
    return out


# -- the bullet path reference integrator (the game's unsteered flight) -----------------

def f32(x: float) -> float:
    """x rounded to single precision, as the game's float arithmetic rounds."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def integrate(state: dict, frames: list, prm: dict) -> dict:
    """The unsteered flight of one projectile over the given game-time frame
    deltas, step for step as the game's MoveTransform.Update computes it in
    single precision: gravity (when simulated), drag against the clamped
    delta, then the position step. `state`: x, y, vx, vy. `prm`: gravity,
    drag, drag_min, mult, sim, allow_stop, sim_gravity."""
    x, y, vx, vy = f32(state["x"]), f32(state["y"]), f32(state["vx"]), f32(state["vy"])
    g, drag, dmin = f32(prm["gravity"]), f32(prm["drag"]), f32(prm["drag_min"])
    mult, sim = f32(prm["mult"]), f32(prm["sim"])
    clamp, floor = f32(W["move"]["dt_clamp"]), f32(W["move"]["speed_floor"])
    for raw in frames:
        dt = f32(raw)
        num = f32(min(max(dt, f32(0.0)), clamp))
        num = f32(num * sim)
        d = f32(dt * sim)
        if prm["sim_gravity"] == 0:
            vy = f32(vy + f32(f32(f32(g * f32(-1.0)) * d) * mult))
        mag = f32(math.sqrt(f32(f32(vx * vx) + f32(vy * vy))))
        if (mag > floor or prm["allow_stop"]) and mag > dmin:
            k = f32(min(max(f32(f32(drag * num) * min(max(mult, f32(0.0)), f32(1.0))), f32(0.0)),
                        f32(1.0)))
            vx = f32(vx - f32(vx * k))
            vy = f32(vy - f32(vy * k))
        x = f32(x + f32(f32(vx * d) * mult))
        y = f32(y + f32(f32(vy * d) * mult))
    return {"x": x, "y": y, "vx": vx, "vy": vy}


def residual(pred: dict, actual: dict) -> dict:
    """The encoded residual of an observed owner state against the predicted
    unsteered one: perpendicular and along-track distance in hundredths of a
    unit, and the angle between the two velocities in milliradians; each
    rounded half to even from double precision."""
    dx, dy = actual["x"] - pred["x"], actual["y"] - pred["y"]
    speed = math.hypot(pred["vx"], pred["vy"])
    if speed == 0:
        along, perp = math.hypot(dx, dy), 0.0
    else:
        ux, uy = pred["vx"] / speed, pred["vy"] / speed
        along = dx * ux + dy * uy
        perp = abs(dx * uy - dy * ux)
    cross = pred["vx"] * actual["vy"] - pred["vy"] * actual["vx"]
    dot = pred["vx"] * actual["vx"] + pred["vy"] * actual["vy"]
    ang = abs(math.atan2(cross, dot))
    return {"d_perp": round(perp * W["centi"]), "d_along": round(along * W["centi"]),
            "ang": round(ang * PER_MILLE)}


def turn(state: dict, angle: float) -> dict:
    """The state with its velocity turned by `angle` radians (single
    precision): the steering a synthetic trace applies per frame."""
    c, s = f32(math.cos(angle)), f32(math.sin(angle))
    vx, vy = state["vx"], state["vy"]
    return dict(state, vx=f32(f32(vx * c) - f32(vy * s)), vy=f32(f32(vx * s) + f32(vy * c)))


def trace(state: dict, frames: list, prm: dict, turn_per_frame: float | None = None) -> dict:
    """A synthetic owner trace: the unsteered flight, with an optional turn
    applied to the velocity before each frame."""
    for raw in frames:
        if turn_per_frame:
            state = turn(state, turn_per_frame)
        state = integrate(state, [raw], prm)
    return state


# -- the steering references: homing and target bounce, frame by frame -------------
#
# Both follow the game's code step for step in single precision (each
# operation rounded as the game's float arithmetic rounds it); angles are
# taken in double precision and then rounded to single. The canonical
# fixture set pins their exact encoded outputs, so a client measuring the
# same steering produces the same entries.

def _angle_deg(ax, ay, bx, by) -> float:
    """The engine's vector angle: the unsigned angle between two vectors, in degrees;
    zero when either vector is zero."""
    if (ax == 0 and ay == 0) or (bx == 0 and by == 0):
        return 0.0
    return math.degrees(abs(math.atan2(ax * by - ay * bx, ax * bx + ay * by)))


def homing_step(state: dict, target, dt: float, prm: dict):
    """One frame of a homing projectile, as Homing.Update then
    MoveTransform.Update compute it (that order is the reference's): when the
    target lies inside the cone around the flight direction, scaling drag by
    the angle, the homing drag, the clamped pull toward the target scaled by
    the projectile's force, its amount and the code's force scale, and the
    gravity term the homing code adds itself (while homing, the move step
    skips its own gravity). `prm`: the integrator's keys plus amount,
    scaling_drag, h_drag and force. Returns (state, homing_on)."""
    x, y, vx, vy = f32(state["x"]), f32(state["y"]), f32(state["vx"]), f32(state["vy"])
    d = f32(dt)
    tx, ty = f32(f32(target[0]) - x), f32(f32(target[1]) - y)
    ang = f32(_angle_deg(vx, vy, tx, ty))
    on = ang < W["homing"]["cone_deg"]
    if on:
        sd, hd = f32(prm["scaling_drag"]), f32(prm["h_drag"])
        vx = f32(vx - f32(f32(f32(vx * ang) * d) * sd))
        vy = f32(vy - f32(f32(f32(vy * ang) * d) * sd))
        vx = f32(vx - f32(f32(vx * d) * hd))
        vy = f32(vy - f32(f32(vy * d) * hd))
        n = f32(math.sqrt(f32(f32(tx * tx) + f32(ty * ty))))
        cx, cy = (f32(tx / n), f32(ty / n)) if n > 1 else (tx, ty)
        force, scale, amount = f32(prm["force"]), f32(W["homing"]["force_scale"]), f32(prm["amount"])
        vx = f32(vx + f32(f32(f32(f32(cx * d) * force) * scale) * amount))
        vy = f32(vy + f32(f32(f32(f32(cy * d) * force) * scale) * amount))
        vy = f32(vy + f32(f32(d * f32(prm["gravity"])) * f32(prm["mult"])))
    moved = integrate({"x": x, "y": y, "vx": vx, "vy": vy}, [dt],
                      dict(prm, sim_gravity=prm["sim_gravity"] + (1 if on else 0)))
    return moved, on


def homing_trace(state: dict, target, frames: list, prm: dict, sync_every: int,
                 turn_per_frame: float | None = None) -> list:
    """The owner's sync packages of a homing projectile: (time, state) at
    the start and after every `sync_every` frames. `turn_per_frame` adds a
    turn the homing code does not make before each frame (a synthetic
    steering for the mutant comparison)."""
    t, out = f32(0.0), [(f32(0.0), state)]
    for i, raw in enumerate(frames):
        if turn_per_frame:
            state = turn(state, turn_per_frame)
        state, _on = homing_step(state, target, raw, prm)
        t = f32(t + f32(raw))
        if (i + 1) % sync_every == 0:
            out.append((t, state))
    return out


def homing_entry(pid: int, s_rel: int, packages: list, prm: dict) -> list:
    """The encoded `p3ht` entry of one projectile from consecutive sync
    packages: the largest turn rate between two packages as per mille of the
    code's bound (the pull the homing term can add per second over the
    speed at the earlier package), rounded half to even, and the number of
    packages."""
    bound = prm["force"] * W["homing"]["force_scale"] * prm["amount"]
    ratios = []
    for (t0, a), (t1, b) in zip(packages, packages[1:]):
        dt = t1 - t0
        speed = math.hypot(a["vx"], a["vy"])
        if dt <= 0 or speed == 0 or bound == 0:
            continue
        rate = math.radians(_angle_deg(a["vx"], a["vy"], b["vx"], b["vy"])) / dt
        ratios.append(round(rate / (bound / speed) * PER_MILLE))
    return [pid, s_rel, max(ratios) if ratios else 0, len(packages)]


def target_bounce(state: dict, normal, target, me, frames: list, prm: dict,
                  wait_s: float | None = None):
    """One target bounce as the game's code runs it: the reflection off the
    surface (the engine's reflection, then the speed multiplier), the position nudged
    along the new direction, the projectile held still until the wait has
    elapsed in game time, then the owner's new velocity toward the target
    (raised by the upward compensation) at the reflected speed, or the
    reflected velocity unchanged with no target. `state` is at the contact
    point; `me` is the measuring seat's position. Returns the encoded
    entry fields (gap in milliseconds, has_retarget, ang_to_me in
    milliradians, each rounded half to even) and the new velocity, or None
    when the frames end before the wait does. `prm`: gravity, speed_m.
    `wait_s` replaces the code's wait (a synthetic early send for the mutant
    comparison)."""
    x, y, vx, vy = f32(state["x"]), f32(state["y"]), f32(state["vx"]), f32(state["vy"])
    nx, ny = f32(normal[0]), f32(normal[1])
    k = f32(-f32(f32(f32(nx * vx) + f32(ny * vy)) * 2))
    vx, vy = f32(f32(k * nx) + vx), f32(f32(k * ny) + vy)
    sm = f32(prm["speed_m"])
    vx, vy = f32(vx * sm), f32(vy * sm)
    speed = f32(math.sqrt(f32(f32(vx * vx) + f32(vy * vy))))
    nudge = f32(W["bounce"]["nudge"])
    x = f32(x + f32(f32(vx / speed) * nudge))
    y = f32(y + f32(f32(vy / speed) * nudge))
    waited = f32(0.0)
    wait = f32(W["bounce"]["wait_s"] if wait_s is None else wait_s)
    for raw in frames:
        waited = f32(waited + f32(raw))
        if waited >= wait:
            break
    else:
        return None
    if target is None:
        nvx, nvy, has = vx, vy, 0
    else:
        dist = abs(f32(f32(target[0]) - x))
        comp = f32(f32(f32(f32(dist ** f32(W["bounce"]["comp_pow"])) * f32(prm["gravity"])) / speed)
                   * f32(W["bounce"]["comp_scale"]))
        ex, ey = f32(f32(target[0]) - x), f32(f32(f32(target[1]) + comp) - y)
        n = f32(math.sqrt(f32(f32(ex * ex) + f32(ey * ey))))
        nvx, nvy, has = f32(f32(ex / n) * speed), f32(f32(ey / n) * speed), 1
    mx, my = f32(me[0]) - x, f32(me[1]) - y
    ang = abs(math.atan2(nvx * my - nvy * mx, nvx * mx + nvy * my))
    return {"gap": round(waited * PER_MILLE), "has_retarget": has,
            "ang_to_me": round(ang * PER_MILLE), "vx": nvx, "vy": nvy}
