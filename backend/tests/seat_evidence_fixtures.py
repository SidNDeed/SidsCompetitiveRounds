"""Seat-evidence record fixtures (contract V2 section 2): a well-formed record
builder, the worst-case record for the byte budgeter, and signed envelopes.

Steam ids here are 16-digit synthetic values (inside the contract's 15-20
digit bound); none is a Steam account id."""

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import seat_evidence as se  # noqa: E402

SEAT_A = "1000000000000101"
SEAT_B = "1000000000000102"
SEAT_C = "1000000000000103"
KEY = "test-hmac-key-seat-evidence"
T0 = 2_000_000_000


def base_record(**over) -> dict:
    rec = {
        "schema": 2,
        "t0": T0,
        "t0_src": "m",
        "master": 1,
        "ranked": 1,
        "rounds": [5, 3],
        "build": ["1.41.0", "STANDALONE", "abcdef123456"],
        "dll": ["a" * 64, "ok"],
        "game_dll": ["b" * 64, "ok"],
        "compat": "pass",
        "foreign": [0, 0],
        "rtt": [40, 90],
        "offset": [3, 12],
        "clk_ppm": [5, -3, 2],
        "mono_send": 123456789,
        "age": {"view": [30, 50, 120, 900], "rpc": [32, 55, 130, 300],
                "hit": [33, 60, 40], "blk": [31, 50, 20]},
        "age_b": [],
        "drift": [100, 30, 0],
        "cad": [33, 33, 33, 33, 3000],
        "obs": [0] * 10,
        "other_build": "1.41.0|STANDALONE|abcdef123456",
        "other_caps": ["cr_build", "cr_game_token_v"],
        "other_pub": [60, 45, 100, 20, 30, 25],
        "shots": [100, 0, 0],
        "fire_floor": 0,
        "imp": [20, 3, 20],
        "dec": [21, 2],
        "push": [20, 20, 20, 0, 0, 0, 0],
        "blk_sent": [],
        "hit_recv": [],
        "blk_recv": [],
        "hit_sent": [],
        "blk_faults": 0,
        "unpair": [0, 0],
        "omit": {k: 0 for k in se.LIST_ORDER},
    }
    for k, v in over.items():
        rec[k] = v
    return rec


def worst_case_record(n=400) -> dict:
    """Every scalar at its widest legal text, and every list far past the cap
    with full-width signed stamps (the L6 failing input: four 160-entry lists
    of int32-minimum stamps already pass 12 KiB). Every entry is CONTRACT
    -VALID, cross-field invariants included (check_events): own_open is one
    of its two states, hit_recv is path 0 with pid 0, and a hit_sent naming
    a block carries that block's last_* tuple and the keyed last-reset state
    (amended B7: the tenth element, one digit whatever its value)."""
    lo = se.I32_MIN
    rec = base_record(
        t0=lo, rounds=[9, 9],
        build=["9" * 16, "V" * 16, "c" * 12],
        dll=["f" * 64, "ok"], game_dll=["e" * 64, "ok"],
        compat="not_run", foreign=[9999, 9999], rtt=[60000, 60000],
        offset=[1000000, 1000000], clk_ppm=[-1000000, -1000000, -1000000],
        mono_send=2 ** 63 - 1,
        age={"view": [-600000] * 3 + [se.BIG], "rpc": [-600000] * 3 + [se.BIG],
             "hit": [-600000, -600000, se.BIG], "blk": [-600000, -600000, se.BIG]},
        drift=[-100000000, se.BIG, se.BIG],
        cad=[600000] * 5, obs=[se.BIG] * 10,
        other_build="9" * 16 + "|" + "V" * 16 + "|" + "c" * 12,
        other_caps=["C" * 32] * 64,
        other_pub=[se.BIG] * 6, shots=[se.BIG] * 3, fire_floor=se.BIG,
        imp=[se.BIG] * 3, dec=[se.BIG] * 2, push=[se.BIG] * 7,
        blk_faults=se.BIG, unpair=[se.BIG, se.BIG],
    )
    rec["blk_sent"] = [[lo, 9, 255, -200] for _ in range(n)]
    rec["hit_recv"] = [[0, lo, 0, 255, lo, 1, 1, 600000] for _ in range(n)]
    rec["blk_recv"] = [[lo, 9, 255, lo, 1] for _ in range(n)]
    rec["hit_sent"] = [[1, lo, se.I32_MAX, 255, 600000, 1, lo, 9, 255, 1] for _ in range(n)]
    rec["age_b"] = [[720, 1000000, 1000000, se.BIG, -600000, -600000] for _ in range(n)]
    return rec


class NotLiftable(ValueError):
    """A nine-element hit_sent entry the old coupling would have refused."""


def lift_hit_sent(records) -> list:
    """Records whose hit_sent entries have the nine-element shape from before
    the amended B7, lifted to ten elements for the CURRENT code: under the old
    coupling (since_ms -1 if and only if last_* is [0, -1, 0]) such an entry
    is either `none` (since -1, the no-block tuple) or `keyed` (since 0 or
    more, a real block), never `unkeyed`, which that shape could not say. An
    entry the old coupling refused raises NotLiftable: its state is unknown
    and is not invented. Ten-element entries pass unchanged; the input is not
    modified. Used where frozen pre-amendment games are replayed (the private
    equivalence suite) and only there: the server never lifts a stored row."""
    out = copy.deepcopy(records)
    for r in out:
        rec = r["rec"] if "rec" in r else r
        hs = rec.get("hit_sent")
        if not isinstance(hs, list):
            continue
        lifted = []
        for e in hs:
            if len(e) == 10:
                lifted.append(e)
                continue
            if len(e) != 9:
                raise NotLiftable("hit_sent entry of %d elements" % len(e))
            sentinel = (e[6], e[7], e[8]) == se.NO_BLOCK
            if e[4] == se.NO_SINCE and sentinel:
                lifted.append(e + [0])
            elif e[4] != se.NO_SINCE and e[7] != se.NO_BLOCK[1]:
                lifted.append(e + [1])
            else:
                raise NotLiftable("hit_sent entry the old coupling refused: %r" % (e,))
        rec["hit_sent"] = lifted
    return out


RETAINED_PARTS = ("anchor", "details", "line")


def retained_triples(entries, render) -> dict:
    """One sitting result as {identity: (match anchor, stored details,
    rendered line)}. `entries` are the worker's (identity, match anchor,
    stored details) rows; `render` turns stored items into the posted line.
    An identity that appears twice raises: the comparison is per identity."""
    out = {}
    for ident, anchor, stored in entries:
        if ident in out:
            raise AssertionError(("one entry per identity", ident))
        out[ident] = (anchor, stored, render(stored["items"]))
    return out


def retained_moved(base: dict, mut: dict) -> list:
    """Every identity present in both results whose complete triple differs,
    with the parts that moved: [(identity, ["anchor" | "details" | "line"])]."""
    moved = []
    for ident in sorted(set(base) & set(mut)):
        parts = [p for p, a, b in zip(RETAINED_PARTS, base[ident], mut[ident]) if a != b]
        if parts:
            moved.append((ident, parts))
    return moved


def envelope(rec, *, seat=SEAT_A, other=SEAT_B, stable="room_test_123456", rounds=8,
             key=KEY, text=None) -> dict:
    record_text = text if text is not None else se.budget_record(rec)
    env = {"seat": seat, "other": other, "stable": stable,
           "attach": "%s_r%d" % (stable, rounds), "record_text": record_text,
           "record_bytes": record_text.encode("ascii")}
    body = {"contract": 2, "seat_steam_id": seat, "other_steam_id": other,
            "stable_game_key": stable, "attach_key": env["attach"],
            "record": record_text, "sig": se.record_sign(key, env)}
    return body


def body_bytes(body) -> bytes:
    return json.dumps(body).encode()


def clone(rec):
    return copy.deepcopy(rec)
