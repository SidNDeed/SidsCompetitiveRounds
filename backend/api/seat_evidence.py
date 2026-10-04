"""Seat evidence, server half (contract V2; migration 368).

What this module holds, and what it never does:

  * the envelope and record checks the route applies (contract sections 1-2),
  * the deterministic byte budgeter both halves share (section 4),
  * storage: the first record per (stable game key, seat), the conflict
    marker, the compat-outcome store and the release-digest registry,
  * the background worker's database passes: attaching records to their
    match, per-game evaluation and per-sitting evaluation under the loaded
    review rules revision (review_rules), the posting step, the purge,
  * the admin read.

Judging is not here. The descriptions of the evidence are the public
vocabulary in review_measures; which of them opens a review item, at what
value and with what words, is a rules revision that is not part of this
repository. With no valid revision the worker attaches records to matches and
purges on schedule, evaluates nothing and opens nothing.

Outside this lane's own tables, statements here read `matches`,
`ranked_series`, `players` and `runtime_settings`, and write only
`flagged_matches` (advisory rows, `flag_reason = 'review'`,
`auto_invalidated = false`, only for a rule the revision arms). The lane's own
tables are `seat_evidence`, `seat_evidence_games`, `seat_evidence_findings`,
`client_compat_events`, `mod_release_digests`, `review_sitting_dirty`,
`review_seen` and `review_cursor`. No statement here touches a match result, a rating or gold;
a test scans every statement of this module and finds only reads of those.

A seat's record is a statement by that seat. Nothing here turns one into a
result, a rating, a reward, a refusal or a display; at most it opens a review
item.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

import review_measures as rm
import review_rules as rr

CONTRACT = 2
RECORD_MAX_BYTES = 12288
LIST_CAP = 160
LIST_ORDER = ("blk_sent", "hit_recv", "blk_recv", "hit_sent", "age_b")
SEAT_HOURLY_CAP = 40
DETAILS_MAX_BYTES = 2048
READY_LAG_S = rm.CONTRACT_BOUNDS["ready_lag_s"]   # a match row is read only this long after it ended
SEATS = 2                      # the two seats of a game
GAME_EXPIRY_DAYS = 14          # unattached records, and attached games still missing a record
LIST_RETENTION_DAYS = 120
COMPAT_RETENTION_DAYS = 365
FINDING_RETENTION_DAYS = 365
GAMES_PER_PASS = 500           # scheduling bounds: everything left is taken by a later pass
SITTINGS_PER_PASS = 500
MARK_ROWS_PER_PASS = 5000
SWITCHES = ("seat_evidence_accept", "seat_evidence_worker", "seat_evidence_purge")
CURSOR = "sittings"
COMPAT_ROWS_SHOWN = 10

_STEAM = re.compile(r"\d{15,20}")
_KEY_CHARS = re.compile(r"[!#-\[\]-~]{1,60}")     # printable ASCII without '"' and '\'
_ATTACH_SUFFIX = re.compile(r"_r\d{1,2}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_BUILD_PART = re.compile(r"[A-Za-z0-9._+\-]*")
_CAP_NAME = re.compile(r"[A-Za-z0-9_]{1,32}")
_OTHER_BUILD = re.compile(r"[ -!#-\[\]-~]{0,46}")

I32_MIN, I32_MAX = -2147483648, 2147483647
BIG = 10_000_000


class EvidenceRefused(Exception):
    """A request the route refuses: `status` is the HTTP answer, `field` names
    what failed (the client logs it; contract section 5)."""

    def __init__(self, status: int, field: str):
        super().__init__(f"{status}:{field}")
        self.status = status
        self.field = field


# -- record shape (contract section 2) ---------------------------------------

def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _I(lo, hi):
    def check(v):
        return _is_int(v) and lo <= v <= hi
    return check


def _N(inner):
    def check(v):
        return v is None or inner(v)
    return check


def _S(pattern, maxlen):
    def check(v):
        return isinstance(v, str) and len(v) <= maxlen and pattern.fullmatch(v) is not None
    return check


def _ENUM(*values):
    def check(v):
        return isinstance(v, str) and v in values
    return check


def _A(*parts):
    def check(v):
        return (isinstance(v, list) and len(v) == len(parts)
                and all(p(x) for p, x in zip(parts, v)))
    return check


def _L(entry, cap=LIST_CAP):
    def check(v):
        return isinstance(v, list) and len(v) <= cap and all(entry(x) for x in v)
    return check


def _O(spec):
    def check(v):
        return (isinstance(v, dict) and list(v.keys()) == [k for k, _ in spec]
                and all(c(v[k]) for k, c in spec))
    return check


I32 = _I(I32_MIN, I32_MAX)
CNT = _I(0, BIG)
MS = _I(-600000, 600000)
B01 = _I(0, 1)
ORD = _I(0, 255)
KIND = _I(0, 9)
PID = _I(0, I32_MAX)
SINCE = _I(-1, 600000)
DLL = _A(_S(re.compile(r"(?:[0-9a-f]{64})?"), 64), _ENUM("ok", "no_location", "read_failed"))

ENTRY = {
    "blk_sent": _A(I32, KIND, ORD, MS),
    "hit_recv": _A(B01, I32, PID, ORD, I32, B01, B01, SINCE),
    "blk_recv": _A(I32, KIND, ORD, I32, B01),
    "hit_sent": _A(B01, I32, PID, ORD, SINCE, B01, I32, _I(-1, 9), ORD),
    "age_b": _A(_I(-1, 720), _I(0, 1000000), _I(0, 1000000), CNT, MS, MS),
}

RECORD_SPEC = (
    ("schema", _I(2, 2)),
    ("t0", I32),
    ("t0_src", _ENUM("m", "o")),
    ("master", B01),
    ("ranked", B01),
    ("rounds", _A(_I(0, 9), _I(0, 9))),
    # amendment A1: OPTIONAL, and when present exactly here (after rounds)
    ("end", _ENUM("left", "other_left", "lost", "closing")),
    ("build", _A(_S(_BUILD_PART, 16), _S(_BUILD_PART, 16), _S(_BUILD_PART, 12))),
    ("dll", DLL),
    ("game_dll", DLL),
    ("compat", _ENUM("pass", "not_run")),
    ("foreign", _A(_I(0, 9999), _I(0, 9999))),
    ("rtt", _A(_I(0, 60000), _I(0, 60000))),
    ("offset", _A(_I(0, 1000000), _I(0, 1000000))),
    ("clk_ppm", _N(_A(_I(-1000000, 1000000), _I(-1000000, 1000000), _I(-1000000, 1000000)))),
    ("mono_send", _I(0, 2 ** 63 - 1)),
    ("age", _O((("view", _A(MS, MS, MS, CNT)), ("rpc", _A(MS, MS, MS, CNT)),
                ("hit", _A(MS, MS, CNT)), ("blk", _A(MS, MS, CNT))))),
    ("age_b", _L(ENTRY["age_b"])),
    ("drift", _A(_I(-100000000, 100000000), CNT, CNT)),
    ("cad", _A(_I(0, 600000), _I(0, 600000), _I(0, 600000), _I(0, 600000), _I(0, 600000))),
    ("obs", _A(*([CNT] * 10))),
    ("other_build", _S(_OTHER_BUILD, 46)),
    ("other_caps", _L(_S(_CAP_NAME, 32), 64)),
    ("other_pub", _N(_A(*([CNT] * 6)))),
    ("shots", _A(CNT, CNT, CNT)),
    ("fire_floor", CNT),
    ("imp", _A(CNT, CNT, CNT)),
    ("dec", _A(CNT, CNT)),
    ("push", _A(*([CNT] * 7))),
    ("blk_sent", _L(ENTRY["blk_sent"])),
    ("hit_recv", _L(ENTRY["hit_recv"])),
    ("blk_recv", _L(ENTRY["blk_recv"])),
    ("hit_sent", _L(ENTRY["hit_sent"])),
    ("blk_faults", CNT),
    ("unpair", _A(CNT, CNT)),
    ("omit", _O(tuple((k, CNT) for k in LIST_ORDER))),
)
RECORD_KEYS = tuple(k for k, _ in RECORD_SPEC)
OPTIONAL_KEYS = ("end",)


# The event invariants the contract states beyond each element's own range
# (section 2.4 and amendment A2): `own_open` has exactly two states; a path-0
# hit carries no projectile identity; a received hit is always path 0 (a
# path-1 hit is one-sided by construction and is counted in `unpair`, never
# listed); the no-block tuple of a sent hit is exactly [0, -1, 0]; and a
# sent hit's `since_ms` is -1 IF AND ONLY IF its last_* is that tuple (no
# block ever reset the copy's sinceBlock exactly when no block is named).
OWN_OPEN_STATES = (0, -200)
NO_BLOCK = (0, -1, 0)
NO_SINCE = -1


def check_events(rec) -> None:
    """Raise EvidenceRefused(422, "<list>.<field>") for the first event entry
    that breaks an enumerated or cross-field invariant. Runs after every
    entry passed its own range check."""
    for e in rec["blk_sent"]:
        if e[3] not in OWN_OPEN_STATES:
            raise EvidenceRefused(422, "blk_sent.own_open")
    for e in rec["hit_recv"]:
        if e[0] != 0:
            raise EvidenceRefused(422, "hit_recv.path")
        if e[2] != 0:
            raise EvidenceRefused(422, "hit_recv.pid")
    for e in rec["hit_sent"]:
        if e[0] == 0 and e[2] != 0:
            raise EvidenceRefused(422, "hit_sent.pid")
        no_block = (e[6], e[7], e[8]) == NO_BLOCK
        if e[7] == NO_BLOCK[1] and not no_block:
            raise EvidenceRefused(422, "hit_sent.last")
        if e[4] == NO_SINCE and not no_block:
            raise EvidenceRefused(422, "hit_sent.since_unset_with_block")
        if no_block and e[4] != NO_SINCE:
            raise EvidenceRefused(422, "hit_sent.since_set_without_block")


def check_record(rec) -> None:
    """Raise EvidenceRefused(422, <key>) for the first key outside its bound,
    or a key set / key order other than the contract's (an OPTIONAL key is
    either absent or in its exact place); then the event invariants
    (check_events), each refused under its own field name."""
    if not isinstance(rec, dict):
        raise EvidenceRefused(422, "record")
    keys = list(rec.keys())
    want = [k for k in RECORD_KEYS if k not in OPTIONAL_KEYS or k in rec]
    if keys != want:
        missing = [k for k in want if k not in rec]
        extra = [k for k in keys if k not in RECORD_KEYS]
        raise EvidenceRefused(422, (missing or extra or ["key_order"])[0])
    for key, check in RECORD_SPEC:
        if key in rec and not check(rec[key]):
            raise EvidenceRefused(422, key)
    for name in ("dll", "game_dll"):
        sha, state = rec[name]
        if (state == "ok") != bool(sha):
            raise EvidenceRefused(422, name)
    check_events(rec)


def parse_envelope(payload) -> dict:
    """The envelope (contract section 1) after its own checks, with the record
    parsed. Raises EvidenceRefused(400/413/422, field). The signature is
    checked separately (verify_sig), after this, so a 403 never depends on
    which field a malformed body broke."""
    if not isinstance(payload, dict):
        raise EvidenceRefused(400, "body")
    want = {"contract", "seat_steam_id", "other_steam_id", "stable_game_key",
            "attach_key", "record", "sig"}
    if set(payload.keys()) != want:
        raise EvidenceRefused(400, "envelope_keys")
    if not _is_int(payload["contract"]) or payload["contract"] != CONTRACT:
        raise EvidenceRefused(400, "contract")
    seat, other = payload["seat_steam_id"], payload["other_steam_id"]
    if (not isinstance(seat, str) or not _STEAM.fullmatch(seat)
            or not isinstance(other, str) or not _STEAM.fullmatch(other) or seat == other):
        raise EvidenceRefused(400, "steam_ids")
    stable, attach = payload["stable_game_key"], payload["attach_key"]
    if not isinstance(stable, str) or not _KEY_CHARS.fullmatch(stable):
        raise EvidenceRefused(400, "stable_game_key")
    if (not isinstance(attach, str) or len(attach.encode("ascii", "replace")) > 64
            or not attach.startswith(stable)
            or not _ATTACH_SUFFIX.fullmatch(attach[len(stable):])):
        raise EvidenceRefused(400, "attach_key")
    sig = payload["sig"]
    if not isinstance(sig, str) or not _HEX64.fullmatch(sig):
        raise EvidenceRefused(400, "sig")
    record_text = payload["record"]
    if not isinstance(record_text, str) or not record_text:
        raise EvidenceRefused(400, "record")
    if not record_text.isascii():
        raise EvidenceRefused(422, "record_ascii")
    record_bytes = record_text.encode("ascii")
    if len(record_bytes) > RECORD_MAX_BYTES:
        raise EvidenceRefused(413, "record_bytes")
    return {"seat": seat, "other": other, "stable": stable, "attach": attach,
            "sig": sig, "record_text": record_text, "record_bytes": record_bytes}


def parse_record(env: dict) -> dict:
    """Parse and check the record of an envelope parse_envelope accepted."""
    try:
        rec = json.loads(env["record_text"], parse_float=_refuse_float,
                         parse_constant=_refuse_float)
    except EvidenceRefused:
        raise
    except ValueError:
        raise EvidenceRefused(422, "record_json")
    check_record(rec)
    return rec


def _refuse_float(_text):
    raise EvidenceRefused(422, "record_number")


def record_canonical(env: dict) -> str:
    """Contract section 1. New and separate from the 7-field match HMAC."""
    h = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    return ("seat-evidence:v2:" + env["seat"] + ":" + env["other"] + ":"
            + h(env["stable"].encode("ascii")) + ":" + h(env["attach"].encode("ascii")) + ":"
            + h(env["record_bytes"]))


def record_sign(key: str, env: dict) -> str:
    return hmac.new(key.encode(), record_canonical(env).encode(), hashlib.sha256).hexdigest()


def verify_sig(key: str, env: dict) -> bool:
    if not key:
        return False
    return hmac.compare_digest(env["sig"], record_sign(key, env))


# -- the byte budgeter (contract section 4) ----------------------------------

def _dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


def budget_record(rec: dict, limit: int = RECORD_MAX_BYTES) -> str:
    """The reference budgeter. `rec` holds every section-2 key in order with
    full lists (an OPTIONAL key only when present, kept in its place); returns
    the record text, <= limit bytes, with `omit` counting every entry it
    dropped. Deterministic: the same input gives the same bytes."""
    out = {k: rec[k] for k in RECORD_KEYS if k in rec or k not in OPTIONAL_KEYS}
    omit = {k: int(rec["omit"].get(k, 0)) for k in LIST_ORDER}
    for k in LIST_ORDER:
        lst = list(out[k])
        if len(lst) > LIST_CAP:
            omit[k] += len(lst) - LIST_CAP
            lst = lst[:LIST_CAP]
        out[k] = lst
    out["omit"] = omit
    body = _dumps(out)
    while len(body) > limit:
        longest = max(LIST_ORDER, key=lambda k: (len(out[k]), -LIST_ORDER.index(k)))
        if not out[longest]:
            raise ValueError("the scalar fields alone exceed the limit")
        out[longest] = out[longest][:-1]
        omit[longest] += 1
        body = _dumps(out)
    return body


def bounded_details(details: dict) -> dict:
    """A finding's details, at most DETAILS_MAX_BYTES serialized."""
    body = _dumps(details)
    if len(body) <= DETAILS_MAX_BYTES:
        return details
    items = list(details.get("items") or [])
    while items and len(_dumps({"items": items, "truncated": True})) > DETAILS_MAX_BYTES:
        items.pop()
    return {"items": items, "truncated": True}


# -- database passes (the worker; primary only) ------------------------------

async def setting(db, key: str, default: str = "0") -> str:
    """An operational switch (whether a part of the lane runs, never what it
    judges); only the names in SWITCHES are read."""
    if key not in SWITCHES:
        raise KeyError(key)
    row = (await db.execute(text("SELECT value FROM runtime_settings WHERE key = :k"),
                            {"k": key})).first()
    return default if row is None else str(row[0])


async def upsert_finding(db, scope: str, dedup_key: str, rule_id: str, rules_rev: str,
                         match_id, details: dict) -> int:
    """One row per normalized (scope, key, rule); a repeat with the same
    details leaves changed_at alone, so idempotent re-evaluation is a no-op."""
    det = _dumps(bounded_details(details))
    row = (await db.execute(text(
        "INSERT INTO seat_evidence_findings (scope, dedup_key, rule_id, rules_rev, match_id, details) "
        "VALUES (:s, :k, :rid, :rev, CAST(:m AS uuid), CAST(:d AS jsonb)) "
        "ON CONFLICT (scope, dedup_key, rule_id) DO UPDATE SET "
        "  details = EXCLUDED.details, rules_rev = EXCLUDED.rules_rev, "
        "  match_id = COALESCE(EXCLUDED.match_id, seat_evidence_findings.match_id), "
        "  changed_at = CASE WHEN seat_evidence_findings.details = EXCLUDED.details "
        "                    THEN seat_evidence_findings.changed_at ELSE now() END, "
        "  computed_at = now() "
        "RETURNING id"), {"s": scope, "k": dedup_key, "rid": rule_id, "rev": rules_rev,
                          "m": None if match_id is None else str(match_id), "d": det})).first()
    return int(row[0])


def review_flag_payload(rs, rule, finding_id, details) -> dict:
    """What a posted finding carries into flagged_matches: the rule id and
    revision, the rendered line (numbers and recorded text only), the items."""
    items = list(details.get("items") or [])
    line = rs.render_line(rule, items)
    notes = details.get("notes") or []
    if notes:
        line = "\n".join([line] + [n for n in notes if n])
    out = {"rule_id": rule.id, "rules_rev": rs.rev, "line": line, "items": items,
           "seat_finding_id": int(finding_id)}
    if details.get("truncated"):
        out["truncated"] = True
    return out


async def post_finding(db, finding_id: int, rs) -> str:
    """The posting step: a finding reaches flagged_matches (and so the admin
    Discord feed) only while the loaded revision arms its rule (`post`), and
    only for a game that ended at or after the rule's `post_since`. Under the
    finding's row lock, so two passes cannot both insert. Returns what it did."""
    f = (await db.execute(text(
        "SELECT id, rule_id, match_id, details, flag_id FROM seat_evidence_findings "
        "WHERE id = :i FOR UPDATE"), {"i": finding_id})).mappings().first()
    if f is None or f["match_id"] is None:
        return "no_match"
    rule = rs.rule(f["rule_id"]) if rs is not None else None
    if rule is None or rule.effect != "flag" or not rule.post:
        return "shadow"
    m = (await db.execute(text(
        "SELECT m.series_id, m.ended_at, p1.steam_id s1, p2.steam_id s2 FROM matches m "
        "JOIN players p1 ON p1.id = m.player1_id JOIN players p2 ON p2.id = m.player2_id "
        "WHERE m.id = :m"), {"m": f["match_id"]})).mappings().first()
    if m is None:
        return "no_match"
    if rule.post_since is not None and m["ended_at"] < rule.post_since:
        return "shadow"
    det = _dumps(review_flag_payload(rs, rule, f["id"], dict(_jsonv(f["details"]) or {})))
    if f["flag_id"] is not None:
        await db.execute(text(
            "UPDATE flagged_matches SET flag_details = CAST(:d AS jsonb) "
            "WHERE id = :fid AND flag_details IS DISTINCT FROM CAST(:d AS jsonb)"),
            {"d": det, "fid": f["flag_id"]})
        return "updated"
    fid = (await db.execute(text(
        "INSERT INTO flagged_matches (id, match_id, series_id, player_steam_ids, flag_reason, "
        "  flag_details, auto_invalidated, restoration_required, discord_evidence_revision, created_at) "
        "VALUES (gen_random_uuid(), :m, :s, CAST(:ids AS varchar[]), 'review', CAST(:d AS jsonb), "
        "  false, false, :one, now()) RETURNING id"),
        {"m": f["match_id"], "s": m["series_id"], "ids": [m["s1"], m["s2"]], "one": 1,
         "d": det})).scalar_one()
    await db.execute(text("UPDATE seat_evidence_findings SET flag_id = :fid WHERE id = :i"),
                     {"fid": fid, "i": finding_id})
    return "posted"


async def _registry(db) -> set:
    rows = (await db.execute(text(
        "SELECT version, variant, commit_sha, dll_sha256 FROM mod_release_digests"))).all()
    return {(r[0], r[1], r[2], r[3]) for r in rows}


# Games waiting for work, least recently processed first. With a revision
# loaded: every game not yet final, and every final game still holding its
# lists whose last evaluation was under another revision. With none: only
# games not yet attached to their match (attachment continues; nothing is
# evaluated).
_CANDIDATES = text(
    "SELECT e.stable_game_key k, LEAST(e.seat_player_id, e.other_player_id) lo, "
    "       GREATEST(e.seat_player_id, e.other_player_id) hi, max(e.received_at) rx "
    "  FROM seat_evidence e "
    "  LEFT JOIN seat_evidence_games g ON g.stable_game_key = e.stable_game_key "
    "   AND g.pair_lo = LEAST(e.seat_player_id, e.other_player_id) "
    "   AND g.pair_hi = GREATEST(e.seat_player_id, e.other_player_id) "
    " WHERE (CAST(:rev AS varchar) IS NULL AND g.finalized_at IS NULL AND g.match_id IS NULL) "
    "    OR (CAST(:rev AS varchar) IS NOT NULL AND (g.finalized_at IS NULL "
    "        OR (g.evaluated_rev IS DISTINCT FROM CAST(:rev AS varchar) AND e.lists_purged_at IS NULL))) "
    " GROUP BY e.stable_game_key, LEAST(e.seat_player_id, e.other_player_id), "
    "          GREATEST(e.seat_player_id, e.other_player_id) ORDER BY min(g.processed_at) NULLS FIRST, rx LIMIT CAST(:lim AS int)")


def attached_records(rows, match) -> tuple:
    """The rows whose OWN attach key is the selected match's exact
    photon_room_id, and the rest. Only the first list is ever evaluated
    against that match: a record carrying another key (a different report id
    for the same stable game) stays incomplete, and is never read as evidence
    about a match its own key does not name."""
    if match is None:
        return [], list(rows)
    room = match["photon_room_id"]
    return ([r for r in rows if r["attach_key"] == room],
            [r for r in rows if r["attach_key"] != room])


async def evaluate_one(db, key: str, lo, hi, registry, rs) -> tuple:
    """One game, in the caller's transaction. Attaches the records to their
    ranked match (one ended at least READY_LAG_S ago); each record is
    evaluated only against the match its own attach key names exactly
    (attached_records). With a revision loaded, re-evaluates when the
    readiness signature (attached match, record set, conflict markers, which
    records the match's key names) or the revision changed; marks the game
    final once the match is attached AND both records name it, its age passed
    GAME_EXPIRY_DAYS, or its lists were purged. A game with no match is never
    final; the purge removes it after expiry. With no revision it attaches and
    evaluates nothing. Returns (state, fired, rule errors, evaluated)."""
    await db.execute(text(
        "INSERT INTO seat_evidence_games (stable_game_key, pair_lo, pair_hi) "
        "VALUES (:k, :lo, :hi) ON CONFLICT DO NOTHING"), {"k": key, "lo": lo, "hi": hi})
    g = (await db.execute(text(
        "SELECT signature, first_seen_at, finalized_at, evaluated_rev, match_id FROM seat_evidence_games "
        "WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi FOR UPDATE"),
        {"k": key, "lo": lo, "hi": hi})).mappings().first()
    rev = rs.rev if rs is not None else None
    if g["finalized_at"] is not None and (rev is None or g["evaluated_rev"] == rev):
        return "final", 0, 0, False
    rows = (await db.execute(text(
        "SELECT id, seat_player_id, other_player_id, attach_key, payload, header_mod_version, "
        "       conflict_at, received_at FROM seat_evidence "
        "WHERE stable_game_key = :k AND LEAST(seat_player_id, other_player_id) = :lo "
        "  AND GREATEST(seat_player_id, other_player_id) = :hi ORDER BY id"),
        {"k": key, "lo": lo, "hi": hi})).mappings().all()
    if not rows:
        return "empty", 0, 0, False
    keys = sorted({r["attach_key"] for r in rows})
    match = (await db.execute(text(
        "SELECT id, player1_id, player2_id, p1_rounds_won, p2_rounds_won, ended_at, photon_room_id "
        "FROM matches "
        "WHERE photon_room_id = ANY(CAST(:keys AS varchar[])) AND is_ranked IS TRUE "
        "  AND ((player1_id = :lo AND player2_id = :hi) OR (player1_id = :hi AND player2_id = :lo)) "
        "  AND ended_at <= now() - make_interval(secs => CAST(:lag AS int)) "
        "ORDER BY ended_at LIMIT 1"),
        {"keys": keys, "lo": lo, "hi": hi, "lag": READY_LAG_S})).mappings().first()
    if rs is None:
        await db.execute(text(
            "UPDATE seat_evidence_games SET match_id = :m, processed_at = now() "
            "WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi"),
            {"m": match["id"] if match else None, "k": key, "lo": lo, "hi": hi})
        return ("attached" if match else "waiting"), 0, 0, False
    named, other_key = attached_records(rows, match)
    named_ids = {r["id"] for r in named}
    sig = "%s|%s" % (match["id"] if match else "-",
                     ",".join("%d:%d:%d" % (r["id"], 1 if r["conflict_at"] else 0,
                                            1 if r["id"] in named_ids else 0) for r in rows))
    now = datetime.now(timezone.utc)
    expired = (g["first_seen_at"] < now - timedelta(days=GAME_EXPIRY_DAYS))
    if sig == g["signature"] and g["evaluated_rev"] == rev and not (expired and match is not None):
        await db.execute(text(
            "UPDATE seat_evidence_games SET processed_at = now() "
            "WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi"),
            {"k": key, "lo": lo, "hi": hi})
        return "unchanged", 0, 0, False
    final = match is not None and ((len(named) >= SEATS and not other_key) or expired)
    fired = errors = 0
    evaluated = None
    if match is not None and named:
        records = [{"seat": r["seat_player_id"], "other": r["other_player_id"],
                    "rec": _jsonv(r["payload"]), "header_version": r["header_mod_version"],
                    "conflict": r["conflict_at"] is not None} for r in named]
        if any(not _has_lists(r["rec"]) for r in records):
            final = True          # lists purged: nothing left to compare
        else:
            # Off the event loop: evaluation is CPU work bounded by the
            # revision's work cap.
            findings, _fired, errors = await asyncio.to_thread(
                rs.evaluate_game, records, dict(match), registry)
            dedup = "%s|%s|%s" % (key, lo, hi)
            produced = set()
            for rule, det in findings:
                fid = await upsert_finding(db, "game", dedup, rule.id, rev, match["id"], det)
                produced.add(rule.id)
                await post_finding(db, fid, rs)
            fired = len(findings)
            await db.execute(text(
                "DELETE FROM seat_evidence_findings WHERE scope = 'game' AND dedup_key = :k "
                "AND flag_id IS NULL AND NOT (rule_id = ANY(CAST(:ids AS varchar[])))"),
                {"k": dedup, "ids": sorted(produced) or [""]})
            evaluated = rev
    await db.execute(text(
        "UPDATE seat_evidence_games SET match_id = :m, signature = :s, processed_at = now(), "
        "  evaluated_rev = COALESCE(CAST(:ev AS varchar), evaluated_rev), "
        "  finalized_at = CASE WHEN :f THEN COALESCE(finalized_at, now()) ELSE NULL END "
        "WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi"),
        {"m": match["id"] if match else None, "s": sig, "f": bool(final), "ev": evaluated,
         "k": key, "lo": lo, "hi": hi})
    state = "final" if final else ("evaluated" if match else "waiting")
    return state, fired, errors, evaluated is not None


def _jsonv(v):
    """A jsonb value as Python, whichever form the driver returned it in."""
    return json.loads(v) if isinstance(v, (str, bytes)) else v


def _has_lists(rec) -> bool:
    return all(k in rec for k in LIST_ORDER)


async def games_pass(session_factory, state=None, limit: int = GAMES_PER_PASS) -> dict:
    """Games waiting for work, each in its own transaction so one bad game
    cannot hold back the rest. `state` is review_rules' published state; its
    ruleset is None unless a revision is loaded."""
    rs = state.ruleset if state is not None else None
    stats = {"evaluated": 0, "fired": 0, "rule_errors": 0}
    async with session_factory() as db:
        if await setting(db, "seat_evidence_worker") != "1":
            return {"off": 1}
        cands = (await db.execute(_CANDIDATES, {"lim": limit,
                                                "rev": rs.rev if rs else None})).all()
        registry = await _registry(db)
    for key, lo, hi, _rx in cands:
        async with session_factory() as db:
            try:
                st, fired, errors, done = await evaluate_one(db, key, lo, hi, registry, rs)
                await db.commit()
            except Exception as exc:          # noqa: BLE001 -- counted, next game
                await db.rollback()
                st, fired, errors, done = "error:" + type(exc).__name__, 0, 0, False
        stats[st] = stats.get(st, 0) + 1
        stats["evaluated"] += 1 if done else 0
        stats["fired"] += fired
        stats["rule_errors"] += errors
    return stats


async def _mark_dirty(db, rs, limit: int) -> int:
    """Fold committed ranked match rows into the persisted dirty-sitting set.

    The ledger is DURABLE and keyed by row, not by position: every ranked row
    created inside the revision's widest window that review_seen does not yet
    hold is read (an anti-join), its sitting marked dirty and its id recorded
    in review_seen, in the same transaction. `created_at` is a transaction
    -time stamp, not commit order: a row whose transaction committed after a
    later-stamped row was already folded is still absent from review_seen,
    so the next pass reads it. Every row is therefore visited exactly once
    per revision, at least READY_LAG_S after it was stamped. A new revision
    empties review_seen, so every sitting that revision can see is evaluated
    under it; ids leave review_seen once their row falls out of the window
    (and so can never be read again). Returns the rows consumed."""
    await db.execute(text(
        "INSERT INTO review_cursor (name) VALUES (:n) ON CONFLICT (name) DO NOTHING"),
        {"n": CURSOR})
    cur = (await db.execute(text(
        "SELECT rules_rev FROM review_cursor WHERE name = :n FOR UPDATE"),
        {"n": CURSOR})).scalar()
    if cur != rs.rev:
        await db.execute(text("DELETE FROM review_seen"))
        await db.execute(text(
            "UPDATE review_cursor SET rules_rev = :rev, updated_at = now() WHERE name = :n"),
            {"rev": rs.rev, "n": CURSOR})
    horizon = rs.horizon_days()
    await db.execute(text(
        "DELETE FROM review_seen WHERE created_at <= now() - make_interval(days => CAST(:h AS int))"),
        {"h": horizon})
    rows = (await db.execute(text(
        "SELECT m.id, m.created_at, LEAST(m.player1_id, m.player2_id) lo, "
        "       GREATEST(m.player1_id, m.player2_id) hi, (m.ended_at AT TIME ZONE 'UTC')::date d "
        "  FROM matches m "
        " WHERE m.created_at > now() - make_interval(days => CAST(:h AS int)) "
        "   AND m.created_at <= now() - make_interval(secs => CAST(:lag AS int)) "
        "   AND m.is_ranked IS TRUE AND m.player1_id <> m.player2_id AND m.ended_at IS NOT NULL "
        "   AND NOT EXISTS (SELECT 1 FROM review_seen s WHERE s.match_id = m.id) "
        " ORDER BY m.created_at, m.id LIMIT CAST(:lim AS int)"),
        {"h": horizon, "lag": READY_LAG_S, "lim": limit})).mappings().all()
    if not rows:
        return 0
    keys = sorted({(str(r["lo"]), str(r["hi"]), r["d"]) for r in rows})
    await db.execute(text(
        "INSERT INTO review_sitting_dirty (pair_lo, pair_hi, day) "
        "SELECT * FROM unnest(CAST(:lo AS uuid[]), CAST(:hi AS uuid[]), CAST(:d AS date[])) "
        "ON CONFLICT (pair_lo, pair_hi, day) DO UPDATE SET marked_at = now()"),
        {"lo": [k[0] for k in keys], "hi": [k[1] for k in keys], "d": [k[2] for k in keys]})
    await db.execute(text(
        "INSERT INTO review_seen (match_id, created_at) "
        "SELECT * FROM unnest(CAST(:ids AS uuid[]), CAST(:ts AS timestamptz[])) "
        "ON CONFLICT (match_id) DO NOTHING"),
        {"ids": [str(r["id"]) for r in rows], "ts": [r["created_at"] for r in rows]})
    return len(rows)


async def sitting_pass(session_factory, state=None, *, limit: int = SITTINGS_PER_PASS,
                       mark_limit: int = MARK_ROWS_PER_PASS) -> dict:
    """The revision's sitting rules over the oldest dirty sittings (at most
    `limit` per pass; the rest wait for the next), each rule in its own
    transaction, written in shadow and posted per rule. The dirty rows are
    cleared only when every rule succeeded, so a failed rule is retried."""
    rs = state.ruleset if state is not None else None
    if rs is None or not rs.sitting_rules:
        return {"evaluated": 0, "fired": 0, "rule_errors": 0}
    async with session_factory() as db:
        if await setting(db, "seat_evidence_worker") != "1":
            return {"off": 1}
        marked = await _mark_dirty(db, rs, mark_limit)
        await db.commit()
        snap = (await db.execute(text(
            "SELECT marked_at FROM review_sitting_dirty ORDER BY marked_at "
            "OFFSET (CAST(:lim AS int) - 1) LIMIT 1"), {"lim": limit})).scalar()
        if snap is None:
            snap = (await db.execute(text("SELECT max(marked_at) FROM review_sitting_dirty"))).scalar()
        n = 0 if snap is None else (await db.execute(text(
            "SELECT count(*) FROM review_sitting_dirty WHERE marked_at <= :s"), {"s": snap})).scalar()
    stats = {"marked_rows": marked, "evaluated": int(n or 0), "fired": 0, "rule_errors": 0}
    if snap is None:
        return stats
    for rule in rs.sitting_rules:
        async with session_factory() as db:
            try:
                sql, binds = rs.sitting_statement(rule)
                binds["snap"] = snap
                rows = (await db.execute(text(sql), binds)).mappings().all()
                for dedup, mid, items in rs.sitting_items(rule, rows):
                    fid = await upsert_finding(db, "sitting", dedup, rule.id, rs.rev, mid,
                                               {"items": items})
                    await post_finding(db, fid, rs)
                    stats["fired"] += 1
                await db.commit()
            except Exception:                 # noqa: BLE001 -- counted, next rule
                await db.rollback()
                stats["rule_errors"] += 1
    if not stats["rule_errors"]:
        async with session_factory() as db:
            await db.execute(text("DELETE FROM review_sitting_dirty WHERE marked_at <= :s"),
                             {"s": snap})
            await db.commit()
    return stats


async def purge_pass(session_factory) -> dict:
    """Retention: lists out of the payload after LIST_RETENTION_DAYS; records
    never attached after GAME_EXPIRY_DAYS; compat rows and unposted findings
    after a year. flagged_matches rows are never removed."""
    out = {}
    async with session_factory() as db:
        if await setting(db, "seat_evidence_purge") != "1":
            return {"off": 1}
        out["lists"] = (await db.execute(text(
            "UPDATE seat_evidence SET payload = payload - 'blk_sent' - 'hit_recv' - 'blk_recv' "
            "  - 'hit_sent' - 'age_b', lists_purged_at = now() "
            "WHERE lists_purged_at IS NULL "
            "  AND received_at < now() - make_interval(days => CAST(:d AS int))"),
            {"d": LIST_RETENTION_DAYS})).rowcount
        out["unattached"] = (await db.execute(text(
            "DELETE FROM seat_evidence e "
            "WHERE e.received_at < now() - make_interval(days => CAST(:d AS int)) "
            "  AND NOT EXISTS (SELECT 1 FROM seat_evidence_games g "
            "    WHERE g.stable_game_key = e.stable_game_key "
            "      AND g.pair_lo = LEAST(e.seat_player_id, e.other_player_id) "
            "      AND g.pair_hi = GREATEST(e.seat_player_id, e.other_player_id) "
            "      AND g.match_id IS NOT NULL)"), {"d": GAME_EXPIRY_DAYS})).rowcount
        out["games"] = (await db.execute(text(
            "DELETE FROM seat_evidence_games g WHERE g.match_id IS NULL "
            "  AND NOT EXISTS (SELECT 1 FROM seat_evidence e "
            "    WHERE e.stable_game_key = g.stable_game_key "
            "      AND LEAST(e.seat_player_id, e.other_player_id) = g.pair_lo "
            "      AND GREATEST(e.seat_player_id, e.other_player_id) = g.pair_hi)"))).rowcount
        out["compat"] = (await db.execute(text(
            "DELETE FROM client_compat_events "
            "WHERE received_at < now() - make_interval(days => CAST(:d AS int))"),
            {"d": COMPAT_RETENTION_DAYS})).rowcount
        out["findings"] = (await db.execute(text(
            "DELETE FROM seat_evidence_findings WHERE flag_id IS NULL "
            "  AND changed_at < now() - make_interval(days => CAST(:d AS int))"),
            {"d": FINDING_RETENTION_DAYS})).rowcount
        await db.commit()
    return out


# -- the route's store (called by main.submit_seat_evidence) -----------------

async def store_record(db, env: dict, rec: dict, seat_id, other_id, header_version) -> dict:
    """Insert the first record for (stable key, seat), or answer the repeat.
    Serialized per seat by a transaction advisory lock, so the hourly cap and
    the first-record rule hold under concurrent deliveries. Returns the answer
    body; raises EvidenceRefused(409/429)."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                     {"k": "seat_evidence:" + str(seat_id)})
    digest = hashlib.sha256(env["record_bytes"]).hexdigest()
    prior = (await db.execute(text(
        "SELECT id, attach_key, other_player_id, payload_sha256, conflict_at FROM seat_evidence "
        "WHERE stable_game_key = :k AND seat_player_id = :s FOR UPDATE"),
        {"k": env["stable"], "s": seat_id})).mappings().first()
    if prior is not None:
        if (prior["attach_key"] == env["attach"] and prior["other_player_id"] == other_id
                and prior["payload_sha256"] == digest):
            return {"status": "already_recorded"}
        kind = ("attach_key" if prior["attach_key"] != env["attach"]
                else "other_seat" if prior["other_player_id"] != other_id else "payload")
        await db.execute(text(
            "UPDATE seat_evidence SET conflict_at = COALESCE(conflict_at, now()), "
            "  conflict_kind = COALESCE(conflict_kind, :ck) WHERE id = :i"),
            {"ck": kind, "i": prior["id"]})
        await db.commit()
        raise EvidenceRefused(409, "conflict")
    recent = (await db.execute(text(
        "SELECT count(*) FROM seat_evidence WHERE seat_player_id = :s "
        "AND received_at > now() - make_interval(hours => 1)"), {"s": seat_id})).scalar_one()
    if recent >= SEAT_HOURLY_CAP:
        raise EvidenceRefused(429, "seat_hourly_cap")
    build, dll = rec["build"], rec["dll"]
    await db.execute(text(
        "INSERT INTO seat_evidence (stable_game_key, attach_key, seat_player_id, other_player_id, "
        "  header_mod_version, build_version, build_variant, build_commit, dll_sha256, "
        "  dll_hash_state, compat_outcome, payload, payload_sha256, payload_bytes) "
        "VALUES (:k, :a, :s, :o, :hv, :bv, :bvar, :bc, :sha, :st, :co, CAST(:p AS jsonb), :dg, :n)"),
        {"k": env["stable"], "a": env["attach"], "s": seat_id, "o": other_id,
         "hv": header_version, "bv": build[0], "bvar": build[1], "bc": build[2],
         "sha": dll[0] or None, "st": dll[1], "co": rec["compat"],
         "p": env["record_text"], "dg": digest, "n": len(env["record_bytes"])})
    await db.commit()
    return {"status": "recorded"}


# -- the compat-outcome store and the release registry -----------------------

COMPAT_OUTCOMES = ("finding", "not_run")
_GUID = re.compile(r"[A-Za-z0-9_.\-]{1,64}")


def compat_canonical(seat: str, outcome: str, plugins: list) -> str:
    joined = ",".join(plugins).encode("ascii")
    return "compat-outcome:v1:%s:%s:%s" % (seat, outcome, hashlib.sha256(joined).hexdigest())


def check_compat(payload) -> dict:
    """Contract section 5.1. An outcome outside the vocabulary is refused,
    never read as a pass: a check that threw reports not_run."""
    if not isinstance(payload, dict) or set(payload) != {"seat_steam_id", "outcome", "plugins", "sig"}:
        raise EvidenceRefused(400, "envelope_keys")
    seat, outcome, plugins, sig = (payload["seat_steam_id"], payload["outcome"],
                                   payload["plugins"], payload["sig"])
    if not isinstance(seat, str) or not _STEAM.fullmatch(seat):
        raise EvidenceRefused(400, "steam_ids")
    if outcome not in COMPAT_OUTCOMES:
        raise EvidenceRefused(422, "outcome")
    if (not isinstance(plugins, list) or len(plugins) > 16
            or not all(isinstance(p, str) and _GUID.fullmatch(p) for p in plugins)):
        raise EvidenceRefused(422, "plugins")
    if not isinstance(sig, str) or not _HEX64.fullmatch(sig):
        raise EvidenceRefused(400, "sig")
    return {"seat": seat, "outcome": outcome, "plugins": plugins, "sig": sig}


def verify_compat_sig(key: str, c: dict) -> bool:
    if not key:
        return False
    want = hmac.new(key.encode(), compat_canonical(c["seat"], c["outcome"], c["plugins"]).encode(),
                    hashlib.sha256).hexdigest()
    return hmac.compare_digest(c["sig"], want)


async def store_compat(db, c: dict, player_id, mod_version) -> dict:
    """One row per account per UTC hour; a later call inside the hour stores
    nothing and answers already_recorded."""
    got = (await db.execute(text(
        "INSERT INTO client_compat_events (player_id, outcome, other_plugin_count, other_plugins, "
        "  mod_version, hour_bucket) "
        "VALUES (:p, :o, :n, :pl, :mv, date_trunc('hour', now())) "
        "ON CONFLICT (player_id, hour_bucket) DO NOTHING RETURNING id"),
        {"p": player_id, "o": c["outcome"], "n": len(c["plugins"]),
         "pl": ",".join(c["plugins"]) or None, "mv": mod_version})).first()
    await db.commit()
    return {"status": "recorded" if got else "already_recorded"}


async def register_digest(db, version, variant, commit, sha) -> dict:
    """Admin registration of one release tuple (the uploaded release asset's
    digest is the authority, never a local rebuild)."""
    if not (isinstance(version, str) and _BUILD_PART.fullmatch(version) and 0 < len(version) <= 16
            and isinstance(variant, str) and _BUILD_PART.fullmatch(variant) and 0 < len(variant) <= 16
            and isinstance(commit, str) and _BUILD_PART.fullmatch(commit) and len(commit) <= 12
            and isinstance(sha, str) and _HEX64.fullmatch(sha)):
        raise EvidenceRefused(422, "release_tuple")
    got = (await db.execute(text(
        "INSERT INTO mod_release_digests (version, variant, commit_sha, dll_sha256) "
        "VALUES (:v, :var, :c, :s) ON CONFLICT DO NOTHING RETURNING version"),
        {"v": version, "var": variant, "c": commit, "s": sha})).first()
    await db.commit()
    return {"status": "registered" if got else "already_registered"}


# -- the admin read ----------------------------------------------------------

def _norm_pair(a, b):
    return (a, b) if str(a) < str(b) else (b, a)


async def admin_view(db, *, match_id=None, stable_game_key=None, rs=None) -> dict:
    """Both records of a game, its findings (rule id, revision, details, the
    posted flag), the comparison computed now (descriptions only; the
    parameterised parts need a loaded revision), every record under the same
    stable key whether attached or not, and both accounts' latest compat rows.
    Steam ids only; no display name is read."""
    if match_id is not None:
        games = (await db.execute(text(
            "SELECT stable_game_key, pair_lo, pair_hi, match_id, finalized_at, evaluated_rev "
            "FROM seat_evidence_games WHERE match_id = CAST(:m AS uuid)"), {"m": match_id})).mappings().all()
    else:
        games = (await db.execute(text(
            "SELECT stable_game_key, pair_lo, pair_hi, match_id, finalized_at, evaluated_rev "
            "FROM seat_evidence_games WHERE stable_game_key = :k"), {"k": stable_game_key})).mappings().all()
    keys = sorted({g["stable_game_key"] for g in games} | ({stable_game_key} if stable_game_key else set()))
    registry = await _registry(db)
    out = {"review_rules": rs.rev if rs is not None else rr.health_word(), "games": []}
    for key in keys:
        rows = (await db.execute(text(
            "SELECT e.id, e.attach_key, e.seat_player_id, e.other_player_id, ps.steam_id seat_steam, "
            "       po.steam_id other_steam, e.payload, e.header_mod_version, e.conflict_at, "
            "       e.conflict_kind, e.received_at, e.lists_purged_at, e.payload_bytes "
            "  FROM seat_evidence e JOIN players ps ON ps.id = e.seat_player_id "
            "  JOIN players po ON po.id = e.other_player_id "
            " WHERE e.stable_game_key = :k ORDER BY e.id"), {"k": key})).mappings().all()
        by_pair = {}
        for r in rows:
            by_pair.setdefault(_norm_pair(r["seat_player_id"], r["other_player_id"]), []).append(r)
        for (lo, hi), rs_rows in by_pair.items():
            g = next((x for x in games if x["stable_game_key"] == key and x["pair_lo"] == lo
                      and x["pair_hi"] == hi), None)
            match = None
            if g is not None and g["match_id"] is not None:
                match = (await db.execute(text(
                    "SELECT id, player1_id, player2_id, p1_rounds_won, p2_rounds_won, is_ranked, "
                    "       photon_room_id FROM matches WHERE id = :m"),
                    {"m": g["match_id"]})).mappings().first()
            # The comparison reads the records the match's own key names (all
            # of them while no match is attached), and it is ALWAYS rendered:
            # after the purge the retained aggregates and the availability
            # metadata stay, and only the list-derived parts read unavailable.
            named, _other = attached_records(rs_rows, match)
            view_rows = named if match is not None else rs_rows
            records = [{"seat": r["seat_player_id"], "other": r["other_player_id"],
                        "rec": _jsonv(r["payload"]), "header_version": r["header_mod_version"],
                        "conflict": r["conflict_at"] is not None} for r in view_rows]
            view = rm.game_view(records, dict(match) if match else None, registry,
                                rs.params if rs is not None else None)
            named_ids = {r["id"] for r in named}
            dedup = "%s|%s|%s" % (key, lo, hi)
            findings = (await db.execute(text(
                "SELECT rule_id, rules_rev, details, flag_id FROM seat_evidence_findings "
                "WHERE scope = 'game' AND dedup_key = :k ORDER BY rule_id"), {"k": dedup})).mappings().all()
            compat = (await db.execute(text(
                "SELECT p.steam_id, c.outcome, c.other_plugin_count, c.other_plugins, c.mod_version, "
                "       c.received_at FROM client_compat_events c JOIN players p ON p.id = c.player_id "
                "WHERE c.player_id IN (:a, :b) ORDER BY c.received_at DESC LIMIT CAST(:lim AS int)"),
                {"a": lo, "b": hi, "lim": COMPAT_ROWS_SHOWN})).mappings().all()
            out["games"].append({
                "stable_game_key": key,
                "match_id": str(match["id"]) if match else None,
                "attached": match is not None,
                "final": bool(g and g["finalized_at"]),
                "evaluated_rev": g["evaluated_rev"] if g else None,
                "records": [{"seat_steam_id": r["seat_steam"], "other_steam_id": r["other_steam"],
                             "attach_key": r["attach_key"], "received_at": r["received_at"].isoformat(),
                             "conflict_kind": r["conflict_kind"], "payload_bytes": r["payload_bytes"],
                             "lists_purged": r["lists_purged_at"] is not None,
                             "names_the_match": (r["id"] in named_ids) if match else None,
                             "record": _jsonv(r["payload"])} for r in rs_rows],
                "comparison": view,
                "findings": [{"rule_id": f["rule_id"], "rules_rev": f["rules_rev"],
                              "details": _jsonv(f["details"]),
                              "posted_flag_id": str(f["flag_id"]) if f["flag_id"] else None}
                             for f in findings],
                "compat": [{"steam_id": c["steam_id"], "outcome": c["outcome"],
                            "other_plugin_count": c["other_plugin_count"],
                            "other_plugins": c["other_plugins"], "mod_version": c["mod_version"],
                            "received_at": c["received_at"].isoformat()} for c in compat],
            })
    return out
