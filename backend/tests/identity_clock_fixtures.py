"""Identity-clock record fixtures: a well-formed record builder (both seats of
one game share the point-start stamps, so their points pair), the record at
maximum width for the byte proof, the over-cap record for the budgeter, signed
envelopes and clock headers.

Steam ids are the seat-evidence fixtures' 16-digit synthetic values; none is
a Steam account id. Every number is synthetic and chosen to exercise the
wire, never a reviewing value."""

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import identity_clock_evidence as ice  # noqa: E402
import seat_evidence as se  # noqa: E402
import seat_evidence_fixtures as sfx  # noqa: E402

W = ice.IC_WIRE
SEAT_A, SEAT_B, SEAT_C = sfx.SEAT_A, sfx.SEAT_B, sfx.SEAT_C
KEY = sfx.KEY
PROC_A = "0123456789ab"
PROC_B = "ba9876543210"
PS0 = 1_000_000
PS_STEP = 30_000


def pt_s(i, ps, *, rel=900, mv_t=400, in_first=1300, shot_first=1500, ps_age=40):
    """A seat's own statement about one of its point starts."""
    return [i, ps, ps_age, 0, rel, 21, 17000, mv_t, in_first, shot_first, 3000, 3010]


def pt_o(i, ps, *, inpos=(980, 1000, -1, -1), in_first=1340, move_first=1360, shot_first=1540,
         pub_fps=60, ps_age=45):
    """A seat's observation of the OTHER seat at one point start."""
    return [i, ps, ps_age, [1200, -300], 2400, list(inpos), 1010, 180, 34, 2, 0,
            in_first, in_first + 30, move_first, move_first + 30, 1250, shot_first,
            shot_first + 30, 3000, pub_fps]


def base_record(points=3, proc=PROC_A, **over) -> dict:
    """A record every check accepts: three check runs that passed, two read
    game files, a full disk survey, three paired points."""
    rec = {
        "schema": W["schema"],
        "consts": 1,
        "t0": sfx.T0,
        "t0_src": "m",
        "cost": [[0, 10, 0, 500, 90], [1, 3, 0, 120, 60]],
        "proc": [proc, 1, 3, 0, 0],
        "chk": [[0, 0, 1200, 0, 0, 12, 0], [1, 0, 90000, 0, 0, 12, 0],
                [2, 0, 95000, 0, 0, 12, 0]],
        "plug": [],
        "asm_n": [40, 2, 0, 0],
        "asm": [["CompetitiveRounds", "1.41.0", 2], ["UnityEngine", "0.0.0.0", 0]],
        "gdig": [[0, "a" * 64, 0, 1000], [1, "b" * 64, 0, 2000]],
        "aload": [2, "c" * 32, 0, "c" * 32],
        "ldir": {"plugins": [0, 1, 0, [["CompetitiveRounds.dll", "d" * 64]]],
                 "patchers": [0, 0, 0, []]},
        "hp_all": [120, 2, ["CompetitiveRounds", "UnboundLib"]],
        "hp": [[1, 1, 0, 0, 0, ["CompetitiveRounds"]]],
        "rpc_o": [["RPCA_Fire", 40], ["RPCA_Move", 400]],
        "send_cfg": [30, 30, 30, 30, 0],
        "gclk": [150, 50, 600000],
        "tdg": [100, 0, [90, 10]],
        "cad_b": [[0, 10, 33, 33, 0], [1, 10, 33, 33, 0]],
        "pt_s": [pt_s(i, PS0 + i * PS_STEP) for i in range(points)],
        "pt_o": [pt_o(i, PS0 + i * PS_STEP) for i in range(points)],
        "unpair": [0, 0],
        "omit": {k: 0 for k in ice.IC_TRIM},
    }
    rec.update(over)
    return rec


def clone(rec):
    return copy.deepcopy(rec)


def record_text(rec) -> str:
    return ice.ice_budget_record(rec)


def envelope(rec, *, seat=SEAT_A, other=SEAT_B, stable="room_ic_123456", rounds=8, key=KEY,
             text=None) -> dict:
    rt = text if text is not None else record_text(rec)
    env = {"seat": seat, "other": other, "stable": stable,
           "attach": "%s_r%d" % (stable, rounds), "record_text": rt,
           "record_bytes": rt.encode("ascii")}
    return {"contract": W["contract"], "seat_steam_id": seat, "other_steam_id": other,
            "stable_game_key": stable, "attach_key": env["attach"], "record": rt,
            "sig": ice.ice_sign(key, env)}


def clock(proc=PROC_A, sw=5_000_000, unity=4_000_000, photon=123_456) -> str:
    return "%s.%d.%d.%d" % (proc, sw, unity, photon)


# -- maximum width (the byte proof) --------------------------------------------

def _maxname(c="N"):
    return c * W["name_max"]


def max_protected_record() -> dict:
    """Every PROTECTED list full to its cap at maximum field width, every
    trimmable list empty: what the budgeter must always keep whole."""
    big, ms, age = W["count_max"], W["ms_point_max"], W["age_max"]
    rec = base_record(points=0)
    rec["consts"] = W["consts_max"]
    rec["t0"] = se.I32_MIN
    rec["cost"] = [[W["collector_max"], big, big, big, big] for _ in range(W["cost_max"])]
    rec["proc"] = ["f" * 12, W["ordinal_max"], big, big // 2, big // 2]
    # outcome `finding` (a `not_run` lists no plug-in, so is narrower)
    rec["chk"] = [[1, W["ordinal_max"], W["ms_day_max"], 1, W["small_max"], W["small_max"],
                   W["small_max"]] for _ in range(W["chk_max"])]
    rec["plug"] = [_maxname(chr(ord("A") + i)) for i in range(W["plug_max"])]
    rec["asm_n"] = [W["small_max"]] * 4
    rec["asm"] = []
    rec["gdig"] = [[i, "f" * 64, 0, se.I32_MAX] for i in range(W["gdig_max"])]
    rec["aload"] = [W["origin_max"], "f" * 32, 0, "f" * 32]
    rec["ldir"] = {"plugins": [0, W["small_max"], 1, []], "patchers": [0, W["small_max"], 1, []]}
    rec["hp_all"] = [W["patched_max"], W["small_max"],
                     [_maxname(chr(ord("a") + i)) for i in range(W["hp_all_owners_max"])]]
    rec["hp"] = []
    rec["rpc_o"] = []
    rec["send_cfg"] = [W["rate_max"]] * 4 + [W["small_max"]]
    rec["gclk"] = [-W["gclk_cppm_max"], big, W["ms_day_max"]]
    # the bins sum to the package count, which is itself bounded
    bins = [big // W["tdg_bins_max"]] * W["tdg_bins_max"]
    rec["tdg"] = [sum(bins), sum(bins), bins]
    rec["cad_b"] = []
    rec["pt_s"] = [[W["id_max"] - i, se.I32_MIN + i, -age, ms, ms, W["frames_max"], W["us_max"],
                    ms, ms, ms, ms, ms] for i in range(W["pt_max"])]
    rec["pt_o"] = [[W["id_max"] - i, se.I32_MIN + i, -age, [-W["cu_max"], -W["cu_max"]],
                    W["cu_max"], [ms] * W["rungs_max"], ms, big, ms, W["td_ms_max"], big,
                    ms, ms, ms, ms, ms, ms, ms, ms, W["fps_max"]] for i in range(W["pt_max"])]
    rec["unpair"] = [W["small_max"], W["small_max"]]
    rec["omit"] = {k: 0 for k in ice.IC_TRIM}
    return rec


def over_cap_record() -> dict:
    """max_protected_record with every TRIMMABLE list over its cap at maximum
    width: the budgeter must cut only these and count every cut."""
    big, ms = W["count_max"], W["ms_point_max"]
    rec = max_protected_record()
    rec["asm"] = [[_maxname(), "99999.99999.99999.9999", W["origin_max"]]
                  for _ in range(W["asm_max"] + 40)]
    rec["asm_n"] = [W["small_max"], W["small_max"], 0, 0]
    rec["hp"] = [[i % (W["id_max"] + 1), W["kind_max"], W["kind_max"], W["kind_max"],
                  W["kind_max"], [_maxname(chr(ord("a") + j)) for j in range(W["hp_owners_max"])]]
                 for i in range(W["hp_max"] + 5)]
    rec["rpc_o"] = [[_maxname(), big] for _ in range(W["rpc_max"] + 5)]
    rec["cad_b"] = [[b, big, ms, W["td_ms_max"], big] for b in range(W["cad_max"] + 9)]
    rec["ldir"] = {
        "plugins": [0, W["small_max"], 1,
                    [[_maxname(), "e" * 64] for _ in range(W["ldir_plugins_max"] + 3)]],
        "patchers": [0, W["small_max"], 1,
                     [[_maxname(), "e" * 64] for _ in range(W["ldir_patchers_max"] + 2)]]}
    return rec


def body_bytes(body) -> bytes:
    return json.dumps(body).encode()
