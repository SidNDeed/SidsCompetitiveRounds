"""Identity, clock and connection evidence, server half (migration 372).

What this module holds, and what it never does:

  * the envelope and record checks of the identity-clock route (the seat
    evidence envelope, contract 2, with its own signing prefix and its own
    16384-byte record bound), the clock header parser and the reference
    byte budgeter the client reproduces;
  * storage: the first record per (stable game key, seat), the conflict
    marker, the clock sample of the first post and the connection class the
    route computed (a class word and a range-list revision id; never an
    address);
  * the worker's identity pass on the PRIMARY only: attach records to their
    ranked match, pair the two seats' records and points, fit each seat
    process's clock readings against the api's receive clock, hand the public
    measures to the loaded review rules revision, store findings in shadow
    and post only what the revision arms; the purge;
  * the game-file registry and the admin read.

Judging is not here. Which measure opens a review item, at what value and
with what words is decided by the private rules revision (review_rules); with
none loaded the worker attaches and pairs records and opens nothing.

Outside this lane's own tables (`identity_clock_evidence`,
`identity_clock_games`, `game_file_digests`), statements here read `matches`,
`players`, `seat_evidence`, `mod_release_digests` and `runtime_settings`, and
write only `seat_evidence_findings` (rows in the `identity ` key namespace)
and `flagged_matches` (through the seat lane's posting step: advisory rows,
`auto_invalidated = false`, only for a rule the revision arms). No statement
here touches a match result, a rating or gold.

Every field of a record is a statement by the seat that sent it (the census,
the check runs, its own per point timings) or by that seat about the other
seat (cadence, stated intervals, game clock, arrival times, call names). The
server's own observations are the receive time, the version header as
received and the connection class.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

import identity_clock_measures as icm
import review_measures as rm
import seat_evidence as se

# The wire layout (pinned in the review guard by the digest of its value).
IC_WIRE = {
    "contract": 2, "schema": 1, "record_max_bytes": 16384, "hourly_cap": 40,
    "consts_max": 65535, "cost_max": 16, "collector_max": 63, "chk_max": 32,
    "plug_max": 16, "asm_max": 200, "gdig_max": 24, "ldir_plugins_max": 32,
    "ldir_patchers_max": 16, "hp_max": 48, "hp_owners_max": 4, "hp_all_owners_max": 16,
    "rpc_max": 64, "cad_max": 360, "tdg_bins_max": 32, "pt_max": 32, "rungs_max": 4,
    "name_max": 64, "version_max": 23, "count_max": 10000000, "small_max": 9999,
    "ms_point_max": 600000, "ms_day_max": 86400000, "age_max": 600000, "cu_max": 1000000,
    "us_max": 10000000, "rate_max": 1000, "fps_max": 1000, "td_ms_max": 100,
    "bucket_max": 720, "origin_max": 6, "state_max": 3, "moment_max": 3,
    "ordinal_max": 255, "outcome_max": 2, "id_max": 255, "gclk_cppm_max": 100000000,
    "header_bytes_max": 64, "header_ms_max": 1000000000000, "kind_max": 99,
    "frames_max": 99999, "patched_max": 99999,
}
IC_KEYS = ("schema", "consts", "t0", "t0_src", "cost", "proc", "chk", "plug", "asm_n", "asm",
           "gdig", "aload", "ldir", "hp_all", "hp", "rpc_o", "send_cfg", "gclk", "tdg",
           "cad_b", "pt_s", "pt_o", "unpair", "omit")
# Trimmed by the budgeter, in this order among equals (the longest first).
IC_TRIM = ("asm", "cad_b", "rpc_o", "hp", "ldir")
IC_LDIR_PARTS = ("plugins", "patchers")
RECORD_MAX_BYTES = IC_WIRE["record_max_bytes"]
CLOCK_HEADER = "X-Seat-Clock"
SIGN_PREFIX = "identity-clock-evidence:v1:"
NAMESPACE = "identity "          # findings dedup prefix (a seat stable key holds no space)

ICE_SWITCHES = ("identity_clock_evidence_accept", "identity_clock_evidence_worker",
                "identity_clock_evidence_purge")
ICE_READY_LAG_S = rm.CONTRACT_BOUNDS["ready_lag_s"]
ICE_GAME_EXPIRY_DAYS = 14
ICE_LIST_RETENTION_DAYS = 120
ICE_GAMES_PER_PASS = 500
ICE_FIT_ROWS_MAX = 500
ICE_SEATS = 2
ICE_PURGED_LISTS = ("asm", "ldir", "hp", "rpc_o", "cad_b", "pt_s", "pt_o")

W = IC_WIRE
_I, _A, _L, _S, _O, _ENUM = se._I, se._A, se._L, se._S, se._O, se._ENUM
_NAME = re.compile(r"[A-Za-z0-9_.\-]{1,%d}|h:[0-9a-f]{12}" % W["name_max"])
_VERSION = re.compile(r"(?:\d{1,5}(?:\.\d{1,5}){0,3})?")
_HEX12 = re.compile(r"[0-9a-f]{12}")
_HEX32 = re.compile(r"(?:[0-9a-f]{32})?")
_SHA_OR_EMPTY = re.compile(r"(?:[0-9a-f]{64})?")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_CLOCK = re.compile(r"([0-9a-f]{12})\.(\d{1,13})\.(\d{1,13})\.(-?\d{1,10})")

I32 = se.I32
CNT = _I(0, W["count_max"])
SMALL = _I(0, W["small_max"])
NAME = _S(_NAME, W["name_max"])
NAME_OR_EMPTY = _S(re.compile(r"(?:%s)?" % _NAME.pattern), W["name_max"])
PMS = _I(-1, W["ms_point_max"])          # a point time, -1 unknown
AGE = _I(-W["age_max"], W["age_max"])
STATE = _I(0, W["state_max"])
ORIGIN = _I(0, W["origin_max"])
B01 = _I(0, 1)

ENTRY = {
    "cost": _A(_I(0, W["collector_max"]), CNT, CNT, CNT, CNT),
    "chk": _A(_I(0, W["moment_max"]), _I(0, W["ordinal_max"]), _I(0, W["ms_day_max"]),
              _I(0, W["outcome_max"]), SMALL, SMALL, SMALL),
    "asm": _A(NAME, _S(_VERSION, W["version_max"]), ORIGIN),
    "gdig": _A(_I(0, W["id_max"]), _S(_SHA_OR_EMPTY, 64), STATE, _I(0, se.I32_MAX)),
    "ldir_entry": _A(NAME_OR_EMPTY, _S(_HEX64, 64)),
    "hp": _A(_I(0, W["id_max"]), _I(0, W["kind_max"]), _I(0, W["kind_max"]),
             _I(0, W["kind_max"]), _I(0, W["kind_max"]), _L(NAME, W["hp_owners_max"])),
    "rpc_o": _A(NAME, CNT),
    "cad_b": _A(_I(0, W["bucket_max"]), CNT, PMS, _I(-1, W["td_ms_max"]), CNT),
    "pt_s": _A(_I(0, W["id_max"]), I32, AGE, PMS, PMS, _I(-1, W["frames_max"]),
               _I(-1, W["us_max"]), PMS, PMS, PMS, PMS, PMS),
    "pt_o": _A(_I(0, W["id_max"]), I32, AGE,
               _L(_I(-W["cu_max"], W["cu_max"]), 2), _I(-1, W["cu_max"]),
               _L(PMS, W["rungs_max"]), PMS, CNT, PMS, _I(-1, W["td_ms_max"]), CNT,
               PMS, PMS, PMS, PMS, PMS, PMS, PMS, PMS, _I(-1, W["fps_max"])),
}


def _ldir_part(cap):
    return _A(STATE, SMALL, B01, _L(ENTRY["ldir_entry"], cap))


RECORD_SPEC = (
    ("schema", _I(W["schema"], W["schema"])),
    ("consts", _I(0, W["consts_max"])),
    ("t0", I32),
    ("t0_src", _ENUM("m", "o")),
    ("cost", _L(ENTRY["cost"], W["cost_max"])),
    ("proc", _A(_S(_HEX12, 12), _I(0, W["ordinal_max"]), CNT, CNT, CNT)),
    ("chk", _L(ENTRY["chk"], W["chk_max"])),
    ("plug", _L(NAME, W["plug_max"])),
    ("asm_n", _A(SMALL, SMALL, SMALL, SMALL)),
    ("asm", _L(ENTRY["asm"], W["asm_max"])),
    ("gdig", _L(ENTRY["gdig"], W["gdig_max"])),
    ("aload", _A(ORIGIN, _S(_HEX32, 32), STATE, _S(_HEX32, 32))),
    ("ldir", _O((("plugins", _ldir_part(W["ldir_plugins_max"])),
                 ("patchers", _ldir_part(W["ldir_patchers_max"]))))),
    ("hp_all", _A(_I(0, W["patched_max"]), _I(0, W["small_max"]),
                  _L(NAME, W["hp_all_owners_max"]))),
    ("hp", _L(ENTRY["hp"], W["hp_max"])),
    ("rpc_o", _L(ENTRY["rpc_o"], W["rpc_max"])),
    ("send_cfg", _A(_I(0, W["rate_max"]), _I(0, W["rate_max"]), _I(0, W["rate_max"]),
                    _I(0, W["rate_max"]), SMALL)),
    ("gclk", _A(_I(-W["gclk_cppm_max"], W["gclk_cppm_max"]), CNT, _I(0, W["ms_day_max"]))),
    ("tdg", _A(CNT, CNT, _L(CNT, W["tdg_bins_max"]))),
    ("cad_b", _L(ENTRY["cad_b"], W["cad_max"])),
    ("pt_s", _L(ENTRY["pt_s"], W["pt_max"])),
    ("pt_o", _L(ENTRY["pt_o"], W["pt_max"])),
    ("unpair", _A(SMALL, SMALL)),
    ("omit", _O(tuple((k, CNT) for k in IC_TRIM))),
)
assert tuple(k for k, _ in RECORD_SPEC) == IC_KEYS


def _named(kind, e):
    return icm.icm_named(kind, e)


def ice_check_invariants(rec) -> None:
    """The cross-field rules beyond each element's own range; each refusal
    names its field. A check run is three-valued on the wire: `pass` lists no
    other plug-in, `finding` lists at least one, `not_run` (a run that threw
    or had no source) lists none, so a throwing run can never read as a
    pass. An incomplete disk survey carries its state and no list, so it can
    never read as an empty clean folder."""
    proc = _named("proc", rec["proc"])
    if proc["runs"] < proc["findings"] + proc["not_run"]:
        raise se.EvidenceRefused(422, "proc.counts")
    codes = icm.ICM_CODES
    any_finding = False
    for e in rec["chk"]:
        c = _named("chk", e)
        if c["outcome"] == codes["finding"]:
            any_finding = True
            if c["n_plugins"] == 0:
                raise se.EvidenceRefused(422, "chk.outcome")
        elif c["n_plugins"] != 0:
            raise se.EvidenceRefused(422, "chk.outcome")
        if c["moment"] == codes["boot"] and c["ordinal"] >= proc["boots"]:
            raise se.EvidenceRefused(422, "chk.ordinal")
    if any_finding != bool(rec["plug"]):
        raise se.EvidenceRefused(422, "plug")
    if len(set(rec["plug"])) != len(rec["plug"]):
        raise se.EvidenceRefused(422, "plug")
    asm_n = _named("asm_n", rec["asm_n"])
    if asm_n["dynamic"] > asm_n["total"] or len(rec["asm"]) + rec["omit"]["asm"] > asm_n["total"]:
        raise se.EvidenceRefused(422, "asm_n")
    ids = set()
    for e in rec["gdig"]:
        g = _named("gdig", e)
        if (g["state"] == codes["ok"]) != bool(g["sha256"]) or g["file_id"] in ids:
            raise se.EvidenceRefused(422, "gdig")
        ids.add(g["file_id"])
    a = _named("aload", rec["aload"])
    if (a["disk_state"] == codes["ok"]) != bool(a["mvid_disk"]):
        raise se.EvidenceRefused(422, "aload")
    for part in IC_LDIR_PARTS:
        d = _named("ldir_part", rec["ldir"][part])
        if d["state"] != codes["ok"] and (d["files"] or d["truncated"] or d["list"]):
            raise se.EvidenceRefused(422, "ldir." + part)
        if len(d["list"]) > d["files"]:
            raise se.EvidenceRefused(422, "ldir." + part)
    hp_all = _named("hp_all", rec["hp_all"])
    if len(set(hp_all["owners"])) != len(hp_all["owners"]):
        raise se.EvidenceRefused(422, "hp_all")
    for e in rec["hp"]:
        if len(set(_named("hp", e)["owners"])) != len(_named("hp", e)["owners"]):
            raise se.EvidenceRefused(422, "hp")
    g = _named("gclk", rec["gclk"])
    if g["pairs"] == 0 and (g["rate_cppm"] or g["span_ms"]):
        raise se.EvidenceRefused(422, "gclk")
    t = _named("tdg", rec["tdg"])
    if sum(t["bins"]) != t["n"] or t["sat"] > t["n"]:
        raise se.EvidenceRefused(422, "tdg")
    buckets = [_named("cad_b", e)["bucket"] for e in rec["cad_b"]]
    if any(b <= a for a, b in zip(buckets, buckets[1:])):
        raise se.EvidenceRefused(422, "cad_b")
    for kind in ("pt_s", "pt_o"):
        pts = [_named(kind, e)["pt"] for e in rec[kind]]
        if len(set(pts)) != len(pts):
            raise se.EvidenceRefused(422, kind)
    for e in rec["pt_o"]:
        if len(_named("pt_o", e)["tgt"]) == 1:
            raise se.EvidenceRefused(422, "pt_o.tgt")


def ice_check_record(rec) -> None:
    """Raise EvidenceRefused(422, <key>) for the first key outside its bound,
    or a key set or order other than the layout's; then the invariants."""
    if not isinstance(rec, dict):
        raise se.EvidenceRefused(422, "record")
    keys = list(rec.keys())
    if keys != list(IC_KEYS):
        missing = [k for k in IC_KEYS if k not in rec]
        extra = [k for k in keys if k not in IC_KEYS]
        raise se.EvidenceRefused(422, (missing or extra or ["key_order"])[0])
    for key, check in RECORD_SPEC:
        if not check(rec[key]):
            raise se.EvidenceRefused(422, key)
    ice_check_invariants(rec)


def ice_parse_envelope(payload) -> dict:
    """The seat evidence envelope (same keys, contract 2) with this record's
    own byte bound. Raises EvidenceRefused(400/413/422, field)."""
    if not isinstance(payload, dict):
        raise se.EvidenceRefused(400, "body")
    want = {"contract", "seat_steam_id", "other_steam_id", "stable_game_key",
            "attach_key", "record", "sig"}
    if set(payload.keys()) != want:
        raise se.EvidenceRefused(400, "envelope_keys")
    if not se._is_int(payload["contract"]) or payload["contract"] != W["contract"]:
        raise se.EvidenceRefused(400, "contract")
    seat, other = payload["seat_steam_id"], payload["other_steam_id"]
    if (not isinstance(seat, str) or not se._STEAM.fullmatch(seat)
            or not isinstance(other, str) or not se._STEAM.fullmatch(other) or seat == other):
        raise se.EvidenceRefused(400, "steam_ids")
    stable, attach = payload["stable_game_key"], payload["attach_key"]
    if not isinstance(stable, str) or not se._KEY_CHARS.fullmatch(stable):
        raise se.EvidenceRefused(400, "stable_game_key")
    if (not isinstance(attach, str) or len(attach.encode("ascii", "replace")) > 64
            or not attach.startswith(stable)
            or not se._ATTACH_SUFFIX.fullmatch(attach[len(stable):])):
        raise se.EvidenceRefused(400, "attach_key")
    sig = payload["sig"]
    if not isinstance(sig, str) or not _HEX64.fullmatch(sig):
        raise se.EvidenceRefused(400, "sig")
    record_text = payload["record"]
    if not isinstance(record_text, str) or not record_text:
        raise se.EvidenceRefused(400, "record")
    if not record_text.isascii():
        raise se.EvidenceRefused(422, "record_ascii")
    record_bytes = record_text.encode("ascii")
    if len(record_bytes) > RECORD_MAX_BYTES:
        raise se.EvidenceRefused(413, "record_bytes")
    return {"seat": seat, "other": other, "stable": stable, "attach": attach,
            "sig": sig, "record_text": record_text, "record_bytes": record_bytes}


def ice_parse_record(env: dict) -> dict:
    try:
        rec = json.loads(env["record_text"], parse_float=se._refuse_float,
                         parse_constant=se._refuse_float)
    except se.EvidenceRefused:
        raise
    except ValueError:
        raise se.EvidenceRefused(422, "record_json")
    ice_check_record(rec)
    return rec


def ice_canonical(env: dict) -> str:
    """New and separate from the 7-field match HMAC and from the seat
    evidence canonical (its own prefix)."""
    h = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    return (SIGN_PREFIX + env["seat"] + ":" + env["other"] + ":"
            + h(env["stable"].encode("ascii")) + ":" + h(env["attach"].encode("ascii")) + ":"
            + h(env["record_bytes"]))


def ice_sign(key: str, env: dict) -> str:
    return hmac.new(key.encode(), ice_canonical(env).encode(), hashlib.sha256).hexdigest()


def ice_verify_sig(key: str, env: dict) -> bool:
    if not key:
        return False
    return hmac.compare_digest(env["sig"], ice_sign(key, env))


def ice_parse_clock(header, rec) -> dict:
    """The X-Seat-Clock header, outside the signed bytes:
    `<proc_id>.<stopwatch_ms>.<unity_unscaled_ms>.<photon_server_ts>`.
    Never refuses the record. state: ok (all four columns stored), absent,
    malformed, or other_proc (the header's process is not the record's: a
    retry from a later process stores the record but no clock sample)."""
    none = {"state": "absent", "proc": None, "sw": None, "unity": None, "photon": None}
    if header is None or header == "":
        return none
    if not isinstance(header, str) or len(header) > W["header_bytes_max"]:
        return dict(none, state="malformed")
    m = _CLOCK.fullmatch(header)
    if m is None:
        return dict(none, state="malformed")
    proc, sw, unity, photon = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
    if sw > W["header_ms_max"] or unity > W["header_ms_max"] \
            or not se.I32_MIN <= photon <= se.I32_MAX:
        return dict(none, state="malformed")
    if proc != rec["proc"][0]:
        return dict(none, state="other_proc")
    return {"state": "ok", "proc": proc, "sw": sw, "unity": unity, "photon": photon}


# -- the reference budgeter (the client reproduces it byte for byte) ----------

def _dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


_TRIM_CAP = {"asm": W["asm_max"], "cad_b": W["cad_max"], "rpc_o": W["rpc_max"], "hp": W["hp_max"]}
_PROTECTED_CAP = {"cost": W["cost_max"], "chk": W["chk_max"], "plug": W["plug_max"],
                  "gdig": W["gdig_max"], "pt_s": W["pt_max"], "pt_o": W["pt_max"]}


def _trim_len(out, k):
    if k == "ldir":
        return sum(len(out["ldir"][p][3]) for p in IC_LDIR_PARTS)
    return len(out[k])


def _trim_one(out, k):
    if k == "ldir":
        a, b = (out["ldir"][p][3] for p in IC_LDIR_PARTS)
        part = IC_LDIR_PARTS[0] if len(a) >= len(b) else IC_LDIR_PARTS[1]
        lst = out["ldir"][part][3]
        out["ldir"][part][3] = lst[:-1]
    else:
        out[k] = out[k][:-1]


def ice_budget_record(rec: dict, limit: int = RECORD_MAX_BYTES) -> str:
    """`rec` holds every layout key in order with full lists. Lists over their
    cap are cut to the cap (trimmable ones counted in `omit`; a protected
    list over its cap is the caller's error). Then, while the text is over
    `limit`, the longest trimmable list loses its last entry (ties: IC_TRIM
    order; `ldir` counts both parts and loses from the longer, plugins on a
    tie), each removal counted. Deterministic."""
    out = json.loads(_dumps({k: rec[k] for k in IC_KEYS}))
    omit = {k: int(rec["omit"].get(k, 0)) for k in IC_TRIM}
    for k, cap in _PROTECTED_CAP.items():
        if len(out[k]) > cap:
            raise ValueError("protected list over its cap: " + k)
    for k, cap in _TRIM_CAP.items():
        if len(out[k]) > cap:
            omit[k] += len(out[k]) - cap
            out[k] = out[k][:cap]
    for part, cap in zip(IC_LDIR_PARTS, (W["ldir_plugins_max"], W["ldir_patchers_max"])):
        lst = out["ldir"][part][3]
        if len(lst) > cap:
            omit["ldir"] += len(lst) - cap
            out["ldir"][part][3] = lst[:cap]
    out["omit"] = omit
    body = _dumps(out)
    while len(body) > limit:
        longest = max(IC_TRIM, key=lambda k: (_trim_len(out, k), -IC_TRIM.index(k)))
        if _trim_len(out, longest) == 0:
            raise ValueError("the protected fields alone exceed the limit")
        _trim_one(out, longest)
        omit[longest] += 1
        body = _dumps(out)
    return body


# -- storage (called by main.submit_identity_clock_evidence) -------------------

async def ice_setting(db, key: str, default: str = "0") -> str:
    """An operational switch of this lane (whether a part runs, never what
    it judges); only the names in ICE_SWITCHES are read."""
    if key not in ICE_SWITCHES:
        raise KeyError(key)
    row = (await db.execute(text("SELECT value FROM runtime_settings WHERE key = :k"),
                            {"k": key})).first()
    return default if row is None else str(row[0])


async def ice_store_record(db, env: dict, rec: dict, seat_id, other_id, header_version,
                           clock: dict, conn_class: str, conn_ranges: str) -> dict:
    """Insert the first record for (stable key, seat), or answer the repeat.
    The clock sample and the class are those of the FIRST stored post; a
    retry of identical bytes answers already_recorded and stores nothing.
    Serialized per seat by a transaction advisory lock (hourly cap, first
    record rule). Returns the answer body; raises EvidenceRefused(409/429)."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                     {"k": "identity_clock:" + str(seat_id)})
    digest = hashlib.sha256(env["record_bytes"]).hexdigest()
    prior = (await db.execute(text(
        "SELECT id, attach_key, other_player_id, payload_sha256 FROM identity_clock_evidence "
        "WHERE stable_game_key = :k AND seat_player_id = :s FOR UPDATE"),
        {"k": env["stable"], "s": seat_id})).mappings().first()
    if prior is not None:
        if (prior["attach_key"] == env["attach"] and prior["other_player_id"] == other_id
                and prior["payload_sha256"] == digest):
            return {"status": "already_recorded"}
        kind = ("attach_key" if prior["attach_key"] != env["attach"]
                else "other_seat" if prior["other_player_id"] != other_id else "payload")
        await db.execute(text(
            "UPDATE identity_clock_evidence SET conflict_at = COALESCE(conflict_at, now()), "
            "  conflict_kind = COALESCE(conflict_kind, :ck) WHERE id = :i"),
            {"ck": kind, "i": prior["id"]})
        await db.commit()
        raise se.EvidenceRefused(409, "conflict")
    recent = (await db.execute(text(
        "SELECT count(*) FROM identity_clock_evidence WHERE seat_player_id = :s "
        "AND received_at > now() - make_interval(hours => 1)"), {"s": seat_id})).scalar_one()
    if recent >= W["hourly_cap"]:
        raise se.EvidenceRefused(429, "seat_hourly_cap")
    ok = clock["state"] == "ok"
    await db.execute(text(
        "INSERT INTO identity_clock_evidence (stable_game_key, attach_key, seat_player_id, "
        "  other_player_id, header_mod_version, consts_version, payload, payload_sha256, "
        "  payload_bytes, post_clock, post_proc, post_sw_ms, post_unity_ms, post_photon_ts, "
        "  conn_class, conn_ranges) "
        "VALUES (:k, :a, :s, :o, :hv, :cv, CAST(:p AS jsonb), :dg, :n, :pc, :pp, "
        "  CAST(:sw AS bigint), CAST(:un AS bigint), CAST(:ph AS integer), :cc, :cr)"),
        {"k": env["stable"], "a": env["attach"], "s": seat_id, "o": other_id,
         "hv": header_version, "cv": rec["consts"], "p": env["record_text"], "dg": digest,
         "n": len(env["record_bytes"]), "pc": clock["state"],
         "pp": clock["proc"] if ok else None, "sw": clock["sw"] if ok else None,
         "un": clock["unity"] if ok else None, "ph": clock["photon"] if ok else None,
         "cc": conn_class, "cr": conn_ranges})
    await db.commit()
    return {"status": "recorded"}


async def ice_register_game_file(db, file_id, game_version, sha) -> dict:
    """Admin registration of one public game-file fact (a file of the fixed
    list, the game version it belongs to, its digest from a clean install).
    Which rows count for a review is not decided here."""
    if not (se._is_int(file_id) and 0 <= file_id <= W["id_max"]
            and isinstance(game_version, str) and se._BUILD_PART.fullmatch(game_version)
            and 0 < len(game_version) <= 16
            and isinstance(sha, str) and _HEX64.fullmatch(sha)):
        raise se.EvidenceRefused(422, "game_file")
    got = (await db.execute(text(
        "INSERT INTO game_file_digests (file_id, game_version, sha256) "
        "VALUES (CAST(:f AS smallint), :v, :s) ON CONFLICT DO NOTHING RETURNING file_id"),
        {"f": file_id, "v": game_version, "s": sha})).first()
    await db.commit()
    return {"status": "registered" if got else "already_registered"}


# -- the worker (primary only) ---------------------------------------------------

def ice_dedup_key(key, lo, hi) -> str:
    return "%s%s|%s|%s" % (NAMESPACE, key, lo, hi)


async def ice_registries(db) -> dict:
    """The public registries: each registered build tuple with the source it
    was registered under (`release` or `beta`), and the game-file facts."""
    rel = (await db.execute(text(
        "SELECT version, variant, commit_sha, dll_sha256, source FROM mod_release_digests"))).all()
    rows = (await db.execute(text("SELECT file_id, sha256 FROM game_file_digests"))).all()
    return {"release": {(r[0], r[1], r[2], r[3]): r[4] for r in rel},
            "game_files": {(int(r[0]), r[1]) for r in rows}}


_ICE_CANDIDATES = text(
    "SELECT e.stable_game_key k, LEAST(e.seat_player_id, e.other_player_id) lo, "
    "       GREATEST(e.seat_player_id, e.other_player_id) hi, max(e.received_at) rx "
    "  FROM identity_clock_evidence e "
    "  LEFT JOIN identity_clock_games g ON g.stable_game_key = e.stable_game_key "
    "   AND g.pair_lo = LEAST(e.seat_player_id, e.other_player_id) "
    "   AND g.pair_hi = GREATEST(e.seat_player_id, e.other_player_id) "
    " WHERE g.finalized_at IS NULL "
    "    OR (CAST(:rev AS varchar) IS NOT NULL "
    "        AND g.evaluated_rev IS DISTINCT FROM CAST(:rev AS varchar) "
    "        AND e.lists_purged_at IS NULL) "
    " GROUP BY e.stable_game_key, LEAST(e.seat_player_id, e.other_player_id), "
    "          GREATEST(e.seat_player_id, e.other_player_id) "
    " ORDER BY min(g.processed_at) NULLS FIRST, rx LIMIT CAST(:lim AS int)")


async def ice_fit_for(db, seat_id, proc) -> tuple:
    """The SERVER-MEASURED fit of one seat process: its posts whose clock
    header named the record's own process, against each post's receive
    time on the api's clock, oldest first."""
    if proc is None:
        return None, 0
    rows = (await db.execute(text(
        "SELECT received_at, post_sw_ms, post_unity_ms, post_photon_ts "
        "  FROM identity_clock_evidence "
        " WHERE seat_player_id = :s AND post_proc = :p AND post_clock = 'ok' "
        " ORDER BY received_at, id LIMIT CAST(:lim AS int)"),
        {"s": seat_id, "p": proc, "lim": ICE_FIT_ROWS_MAX})).all()
    samples = [(int(r[0].timestamp() * 1000), int(r[1]), int(r[2]), int(r[-1])) for r in rows]
    return icm.icm_fit_all(samples), len(samples)


async def ice_views(db, key, rows) -> list:
    """The evaluation input of each identity record: the record, the server's
    observations of its first post, the seat record's stated build tuple for
    the same seat and attach key, the build the OTHER seat relayed for it,
    and the process clock fit."""
    seat_rows = (await db.execute(text(
        "SELECT seat_player_id, attach_key, build_version, build_variant, build_commit, "
        "       dll_sha256, payload FROM seat_evidence WHERE stable_game_key = :k"),
        {"k": key})).mappings().all()
    by = {(r["seat_player_id"], r["attach_key"]): r for r in seat_rows}
    views = []
    for r in rows:
        own = by.get((r["seat_player_id"], r["attach_key"]))
        oth = by.get((r["other_player_id"], r["attach_key"]))
        build = None
        if own is not None and own["build_version"] is not None:
            build = (own["build_version"], own["build_variant"] or "", own["build_commit"] or "",
                     own["dll_sha256"] or "")
        relayed = None
        if oth is not None:
            relayed = (se._jsonv(oth["payload"]) or {}).get("other_build") or None
        fit, fit_rows = await ice_fit_for(db, r["seat_player_id"], r["post_proc"])
        views.append({"seat": r["seat_player_id"], "other": r["other_player_id"],
                      "rec": se._jsonv(r["payload"]), "header_version": r["header_mod_version"],
                      "conflict": r["conflict_at"] is not None, "conn_class": r["conn_class"],
                      "conn_ranges": r["conn_ranges"], "post_clock": r["post_clock"],
                      "seat_build": build, "relayed_build": relayed,
                      "fit": fit, "fit_rows": fit_rows})
    return views


async def ice_evaluate_one(db, key: str, lo, hi, regs, rs) -> tuple:
    """One game, in the caller's transaction: attach to the ranked match the
    records' own attach keys name, pair the records and their points, and with
    a revision loaded evaluate the identity rules over the records the
    match's key names, storing findings in shadow and posting what the
    revision arms. Returns (state, fired, rule errors, evaluated)."""
    await db.execute(text(
        "INSERT INTO identity_clock_games (stable_game_key, pair_lo, pair_hi) "
        "VALUES (:k, :lo, :hi) ON CONFLICT DO NOTHING"), {"k": key, "lo": lo, "hi": hi})
    g = (await db.execute(text(
        "SELECT signature, first_seen_at, finalized_at, evaluated_rev FROM identity_clock_games "
        "WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi FOR UPDATE"),
        {"k": key, "lo": lo, "hi": hi})).mappings().first()
    rev = rs.rev if rs is not None else None
    if g["finalized_at"] is not None and (rev is None or g["evaluated_rev"] == rev):
        return "final", 0, 0, False
    rows = (await db.execute(text(
        "SELECT id, seat_player_id, other_player_id, attach_key, payload, header_mod_version, "
        "       conflict_at, conn_class, conn_ranges, post_clock, post_proc, lists_purged_at "
        "  FROM identity_clock_evidence "
        " WHERE stable_game_key = :k AND LEAST(seat_player_id, other_player_id) = :lo "
        "   AND GREATEST(seat_player_id, other_player_id) = :hi ORDER BY id"),
        {"k": key, "lo": lo, "hi": hi})).mappings().all()
    if not rows:
        return "empty", 0, 0, False
    keys = sorted({r["attach_key"] for r in rows})
    match = (await db.execute(text(
        "SELECT id, player1_id, player2_id, ended_at, photon_room_id FROM matches "
        "WHERE photon_room_id = ANY(CAST(:keys AS varchar[])) AND is_ranked IS TRUE "
        "  AND ((player1_id = :lo AND player2_id = :hi) OR (player1_id = :hi AND player2_id = :lo)) "
        "  AND ended_at <= now() - make_interval(secs => CAST(:lag AS int)) "
        "ORDER BY ended_at LIMIT CAST(:one AS int)"),
        {"keys": keys, "lo": lo, "hi": hi, "lag": ICE_READY_LAG_S, "one": 1})).mappings().first()
    named, other_key = se.attached_records(rows, match)
    shown = named if match is not None else list(rows)
    views = await ice_views(db, key, shown)
    paired = icm.icm_pair_view(views, regs)["paired"]
    named_ids = {r["id"] for r in named}
    seat_ids = (await db.execute(text(
        "SELECT string_agg(CAST(id AS varchar), ',' ORDER BY id) FROM seat_evidence "
        "WHERE stable_game_key = :k AND LEAST(seat_player_id, other_player_id) = :lo "
        "  AND GREATEST(seat_player_id, other_player_id) = :hi"),
        {"k": key, "lo": lo, "hi": hi})).scalar()
    fits = ",".join("%s" % v["fit_rows"] for v in views)
    sig = "%s|%s|%s|%s" % (match["id"] if match else "-",
                           ",".join("%d:%d:%d" % (r["id"], 1 if r["conflict_at"] else 0,
                                                  1 if r["id"] in named_ids else 0) for r in rows),
                           seat_ids or "-", fits)
    if rs is None:
        await db.execute(text(
            "UPDATE identity_clock_games SET match_id = :m, records_n = CAST(:n AS smallint), "
            "  paired_points = CAST(:pp AS int), processed_at = now() "
            "WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi"),
            {"m": match["id"] if match else None, "n": len(shown), "pp": paired,
             "k": key, "lo": lo, "hi": hi})
        return ("attached" if match else "waiting"), 0, 0, False
    now = datetime.now(timezone.utc)
    expired = g["first_seen_at"] < now - timedelta(days=ICE_GAME_EXPIRY_DAYS)
    if sig == g["signature"] and g["evaluated_rev"] == rev and not (expired and match is not None):
        await db.execute(text(
            "UPDATE identity_clock_games SET processed_at = now() "
            "WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi"),
            {"k": key, "lo": lo, "hi": hi})
        return "unchanged", 0, 0, False
    final = match is not None and ((len(named) >= ICE_SEATS and not other_key) or expired)
    fired = errors = 0
    evaluated = None
    if match is not None and named:
        if any(r["lists_purged_at"] is not None for r in named):
            final = True
        else:
            findings, _fired, errors = await asyncio.to_thread(rs.evaluate_identity, views, regs)
            dedup = ice_dedup_key(key, lo, hi)
            produced = set()
            for rule, det in findings:
                fid = await se.upsert_finding(db, "game", dedup, rule.id, rev, match["id"], det)
                produced.add(rule.id)
                await se.post_finding(db, fid, rs)
            fired = len(findings)
            await db.execute(text(
                "DELETE FROM seat_evidence_findings WHERE scope = 'game' AND dedup_key = :k "
                "AND flag_id IS NULL AND NOT (rule_id = ANY(CAST(:ids AS varchar[])))"),
                {"k": dedup, "ids": sorted(produced) or [""]})
            evaluated = rev
    await db.execute(text(
        "UPDATE identity_clock_games SET match_id = :m, signature = :s, processed_at = now(), "
        "  records_n = CAST(:n AS smallint), paired_points = CAST(:pp AS int), "
        "  evaluated_rev = COALESCE(CAST(:ev AS varchar), evaluated_rev), "
        "  finalized_at = CASE WHEN :f THEN COALESCE(finalized_at, now()) ELSE NULL END "
        "WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi"),
        {"m": match["id"] if match else None, "s": sig, "f": bool(final), "ev": evaluated,
         "n": len(shown), "pp": paired, "k": key, "lo": lo, "hi": hi})
    state = "final" if final else ("evaluated" if match else "waiting")
    return state, fired, errors, evaluated is not None


async def ice_games_pass(session_factory, state=None, limit: int = ICE_GAMES_PER_PASS) -> dict:
    """Identity games waiting for work, each in its own transaction so one bad
    game cannot hold back the rest. `state` is review_rules' published state."""
    rs = state.ruleset if state is not None else None
    stats = {"evaluated": 0, "fired": 0, "rule_errors": 0}
    async with session_factory() as db:
        if await ice_setting(db, "identity_clock_evidence_worker") != "1":
            return {"off": 1}
        cands = (await db.execute(_ICE_CANDIDATES, {"lim": limit,
                                                    "rev": rs.rev if rs else None})).all()
        regs = await ice_registries(db)
    for key, lo, hi, _rx in cands:
        async with session_factory() as db:
            try:
                st, fired, errors, done = await ice_evaluate_one(db, key, lo, hi, regs, rs)
                await db.commit()
            except Exception as exc:          # noqa: BLE001 -- counted, next game
                await db.rollback()
                st, fired, errors, done = "error:" + type(exc).__name__, 0, 0, False
        stats[st] = stats.get(st, 0) + 1
        stats["evaluated"] += 1 if done else 0
        stats["fired"] += fired
        stats["rule_errors"] += errors
    return stats


async def ice_purge_pass(session_factory) -> dict:
    """Retention: the raw lists leave the payload after
    ICE_LIST_RETENTION_DAYS (counts, states, the clock columns and the class
    stay); records never attached leave after ICE_GAME_EXPIRY_DAYS; game
    rows without records go. Findings follow the seat lane's purge."""
    out = {}
    async with session_factory() as db:
        if await ice_setting(db, "identity_clock_evidence_purge") != "1":
            return {"off": 1}
        out["lists"] = (await db.execute(text(
            "UPDATE identity_clock_evidence SET payload = payload - CAST(:keys AS text[]), "
            "  lists_purged_at = now() "
            "WHERE lists_purged_at IS NULL "
            "  AND received_at < now() - make_interval(days => CAST(:d AS int))"),
            {"keys": list(ICE_PURGED_LISTS), "d": ICE_LIST_RETENTION_DAYS})).rowcount
        out["unattached"] = (await db.execute(text(
            "DELETE FROM identity_clock_evidence e "
            "WHERE e.received_at < now() - make_interval(days => CAST(:d AS int)) "
            "  AND NOT EXISTS (SELECT 1 FROM identity_clock_games g "
            "    WHERE g.stable_game_key = e.stable_game_key "
            "      AND g.pair_lo = LEAST(e.seat_player_id, e.other_player_id) "
            "      AND g.pair_hi = GREATEST(e.seat_player_id, e.other_player_id) "
            "      AND g.match_id IS NOT NULL)"), {"d": ICE_GAME_EXPIRY_DAYS})).rowcount
        out["games"] = (await db.execute(text(
            "DELETE FROM identity_clock_games g WHERE g.match_id IS NULL "
            "  AND NOT EXISTS (SELECT 1 FROM identity_clock_evidence e "
            "    WHERE e.stable_game_key = g.stable_game_key "
            "      AND LEAST(e.seat_player_id, e.other_player_id) = g.pair_lo "
            "      AND GREATEST(e.seat_player_id, e.other_player_id) = g.pair_hi)"))).rowcount
        await db.commit()
    return out


# -- the admin read ------------------------------------------------------------

ICE_LABELS = {
    "self_stated": ["proc", "chk", "plug", "asm_n", "asm", "gdig", "aload", "ldir", "hp_all",
                    "hp", "send_cfg", "pt_s", "cost"],
    "other_seat_measured": ["rpc_o", "gclk", "tdg", "cad_b", "pt_o"],
    "server_observed": ["header_mod_version", "conn_class", "conn_ranges", "post_clock",
                        "received_at"],
    "server_measured": ["fit"],
}
ICE_UNAVAILABLE_ONE_SIDED = ["the other seat's census and check runs", "the other seat's send_cfg",
                             "the other seat's pt_s", "the other seat's clock fit and class",
                             "every paired point measure"]


def _fit_out(fit):
    if not fit:
        return None
    return {c: (None if f is None else {"rate_ppm": f[0], "err_ppm": f[1], "points": f[2],
                                         "span_ms": f[3]}) for c, f in fit.items()}


async def ice_admin_view(db, *, match_id=None, stable_game_key=None) -> dict:
    """Every identity record of the game (attached or not), the server's
    observations of each first post, each seat process's clock fit, the
    points of both seats side by side, the stored findings of this lane's
    namespace, the provenance labels and the unavailable list for one-sided
    games. Steam ids only; never an address (none is stored)."""
    if match_id is not None:
        games = (await db.execute(text(
            "SELECT stable_game_key, pair_lo, pair_hi, match_id, finalized_at, evaluated_rev, "
            "       paired_points FROM identity_clock_games WHERE match_id = CAST(:m AS uuid)"),
            {"m": match_id})).mappings().all()
    else:
        games = (await db.execute(text(
            "SELECT stable_game_key, pair_lo, pair_hi, match_id, finalized_at, evaluated_rev, "
            "       paired_points FROM identity_clock_games WHERE stable_game_key = :k"),
            {"k": stable_game_key})).mappings().all()
    keys = sorted({g["stable_game_key"] for g in games} | ({stable_game_key} if stable_game_key else set()))
    regs = await ice_registries(db)
    out = {"labels": ICE_LABELS, "games": []}
    for key in keys:
        rows = (await db.execute(text(
            "SELECT e.id, e.seat_player_id, e.other_player_id, ps.steam_id seat_steam, "
            "       po.steam_id other_steam, e.attach_key, e.payload, e.header_mod_version, "
            "       e.conflict_at, e.conflict_kind, e.conn_class, e.conn_ranges, e.post_clock, "
            "       e.post_proc, e.received_at, e.lists_purged_at, e.payload_bytes "
            "  FROM identity_clock_evidence e JOIN players ps ON ps.id = e.seat_player_id "
            "  JOIN players po ON po.id = e.other_player_id "
            " WHERE e.stable_game_key = :k ORDER BY e.id"), {"k": key})).mappings().all()
        by_pair = {}
        for r in rows:
            by_pair.setdefault(se._norm_pair(r["seat_player_id"], r["other_player_id"]), []).append(r)
        for (lo, hi), prs in by_pair.items():
            g = next((x for x in games if x["stable_game_key"] == key and x["pair_lo"] == lo
                      and x["pair_hi"] == hi), None)
            match = None
            if g is not None and g["match_id"] is not None:
                match = (await db.execute(text(
                    "SELECT id, photon_room_id FROM matches WHERE id = :m"),
                    {"m": g["match_id"]})).mappings().first()
            named, _other = se.attached_records(prs, match)
            shown = named if match is not None else list(prs)
            views = await ice_views(db, key, shown)
            pair = icm.icm_pair_view(views, regs)
            findings = (await db.execute(text(
                "SELECT rule_id, rules_rev, details, flag_id FROM seat_evidence_findings "
                "WHERE scope = 'game' AND dedup_key = :k ORDER BY rule_id"),
                {"k": ice_dedup_key(key, lo, hi)})).mappings().all()
            out["games"].append({
                "stable_game_key": key,
                "match_id": str(match["id"]) if match else None,
                "attached": match is not None,
                "final": bool(g and g["finalized_at"]),
                "evaluated_rev": g["evaluated_rev"] if g else None,
                "records": [{"seat_steam_id": r["seat_steam"], "other_steam_id": r["other_steam"],
                             "attach_key": r["attach_key"], "received_at": r["received_at"].isoformat(),
                             "header_mod_version": r["header_mod_version"],
                             "conflict_kind": r["conflict_kind"], "conn_class": r["conn_class"],
                             "conn_ranges": r["conn_ranges"], "post_clock": r["post_clock"],
                             "payload_bytes": r["payload_bytes"],
                             "lists_purged": r["lists_purged_at"] is not None,
                             "record": se._jsonv(r["payload"])} for r in prs],
                "fits": [{"seat_index": i, "fit": _fit_out(v["fit"])} for i, v in enumerate(views)],
                "points": pair["points"],
                "paired_points": pair["paired"],
                "unavailable": ICE_UNAVAILABLE_ONE_SIDED if len(views) < ICE_SEATS else [],
                "findings": [{"rule_id": f["rule_id"], "rules_rev": f["rules_rev"],
                              "details": se._jsonv(f["details"]),
                              "posted_flag_id": str(f["flag_id"]) if f["flag_id"] else None}
                             for f in findings],
            })
    return out
