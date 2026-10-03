"""Combat evidence, server half (combat contract one; migration 369).

What this module holds, and what it never does:

  * the combat envelope and its checks (its own contract, its own record
    bound: combat_measures.COMBAT_WIRE is the one place that bound lives),
  * storage, RAW FIRST: the route stores the record (its JSON value, with
    the SHA-256 and length of the exact signed bytes) and derives nothing;
    the first record per (stable game key, seat) is kept and a later
    different one sets one idempotent conflict marker,
  * the worker's combat pass (PRIMARY ONLY, called from the review worker):
    attachment by exact key to a ranked match of the same canonical seat
    pair, and, only while a valid rules revision is loaded, the cycle
    rebuild and its faults, the public measures handed to the evaluator,
    findings, per-game contributions and the daily rows rolled from them,
  * the purge, and the admin read.

Judging is not here. The descriptions are the public vocabulary in
combat_measures; which of them opens a review item, at what value and with
what words, is a rules revision that is not part of this repository. With no
valid revision the worker attaches records and purges, and writes nothing
else: no measure, fault, contribution, daily row or finding.

Outside this lane's own tables (combat_evidence, combat_games,
combat_contrib, combat_player_daily) the statements here read `matches`,
`players`, `seat_evidence` and `runtime_settings`, and write
`seat_evidence_findings` (scope game, dedup key in the combat namespace:
prefixed `combat ` with a space, a character no seat evidence key can hold) and,
through seat_evidence.post_finding, `flagged_matches` only for a rule the
revision arms. No statement touches a match result, a rating, a reward or
gold. Every finding is advisory.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

import combat_measures as cm
import seat_evidence as _sev

CONTRACT = cm.W["contract"]
RECORD_MAX_BYTES = cm.RECORD_MAX_BYTES
SEAT_HOURLY_CAP = cm.W["seat_hourly_cap"]
SWITCHES = ("combat_evidence_accept", "combat_evidence_worker", "combat_evidence_purge")
GAMES_PER_PASS = 500
GAME_EXPIRY_DAYS = 14
LIST_RETENTION_DAYS = 120
AGG_RETENTION_DAYS = 365
# The combat lane's namespace in seat_evidence_findings. Every combat dedup
# key starts with these seven characters; a seat evidence dedup key is its
# stable key (printable ASCII WITHOUT the space, seat_evidence._KEY_CHARS, the
# only writer's check) then two pair ids, so it can never contain a space and
# can never equal or start with this prefix. Every combat finding write, read
# and stale delete uses dedup_key(); the rollback deletes by this prefix.
DEDUP_PREFIX = "combat "
ENVELOPE_KEYS = ("contract", "seat_steam_id", "other_steam_id", "stable_game_key",
                 "attach_key", "record", "sig")
# Retention (the design's decided rule): after LIST_RETENTION_DAYS a record
# keeps its whole-game totals and rows, its histograms and its cycle
# summaries (`cx_*`, the only lists the retention rule excepts). Every other
# raw list is removed, the never-trimmed ones (`gun_*`, `ivl_*`) included.
RETAINED_LISTS = ("cx_s", "cx_o")
PURGED_LISTS = tuple(k for k in cm.LISTS if k not in RETAINED_LISTS)

EvidenceRefused = _sev.EvidenceRefused


# -- the envelope (the route's checks, in the order it answers) ------------------------

def parse_envelope(payload) -> dict:
    """The combat envelope after its own checks, the record still text.
    Raises EvidenceRefused(400/413/422, field). The signature is checked
    afterwards (verify_sig), so a 403 never depends on which field broke."""
    if not isinstance(payload, dict):
        raise EvidenceRefused(400, "body")
    if set(payload.keys()) != set(ENVELOPE_KEYS):
        raise EvidenceRefused(400, "envelope_keys")
    if not _sev._is_int(payload["contract"]) or payload["contract"] != CONTRACT:
        raise EvidenceRefused(400, "contract")
    seat, other = payload["seat_steam_id"], payload["other_steam_id"]
    if (not isinstance(seat, str) or not _sev._STEAM.fullmatch(seat)
            or not isinstance(other, str) or not _sev._STEAM.fullmatch(other) or seat == other):
        raise EvidenceRefused(400, "steam_ids")
    stable, attach = payload["stable_game_key"], payload["attach_key"]
    if not isinstance(stable, str) or not _sev._KEY_CHARS.fullmatch(stable):
        raise EvidenceRefused(400, "stable_game_key")
    if (not isinstance(attach, str) or not attach.isascii() or len(attach) > _ATTACH_MAX
            or not attach.startswith(stable)
            or not _sev._ATTACH_SUFFIX.fullmatch(attach[len(stable):])):
        raise EvidenceRefused(400, "attach_key")
    sig = payload["sig"]
    if not isinstance(sig, str) or not _sev._HEX64.fullmatch(sig):
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


_ATTACH_MAX = 64


def parse_record(env: dict) -> dict:
    """Parse and check the record of an envelope parse_envelope accepted."""
    try:
        rec = json.loads(env["record_text"], parse_float=_sev._refuse_float,
                         parse_constant=_sev._refuse_float)
    except EvidenceRefused:
        raise
    except ValueError:
        raise EvidenceRefused(422, "record_json")
    try:
        cm.check_record(rec)
    except cm.Refusal as r:
        raise EvidenceRefused(422, r.field)
    return rec


def record_canonical(env: dict) -> str:
    """The combat signing canonical. New and separate from the 7-field match
    HMAC and from the seat evidence canonical."""
    h = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    return (cm.W["sign_prefix"] + env["seat"] + ":" + env["other"] + ":"
            + h(env["stable"].encode("ascii")) + ":" + h(env["attach"].encode("ascii")) + ":"
            + h(env["record_bytes"]))


def record_sign(key: str, env: dict) -> str:
    return hmac.new(key.encode(), record_canonical(env).encode(), hashlib.sha256).hexdigest()


def verify_sig(key: str, env: dict) -> bool:
    if not key:
        return False
    return hmac.compare_digest(env["sig"], record_sign(key, env))


# -- the route's store (raw first) --------------------------------------------------

async def store_record(db, env: dict, rec: dict, seat_id, other_id, header_version) -> dict:
    """Insert the first record for (stable key, seat), or answer the repeat.
    Nothing is derived here: the record is stored as received (its JSON
    value, the SHA-256 and length of the signed bytes), and every
    derivation happens later in the worker, which never deletes or rewrites
    a stored record when a derivation fails. Serialized per seat by a
    transaction advisory lock, so the hourly cap and the first-record rule
    hold under concurrent deliveries. Returns the answer body; raises
    EvidenceRefused(409/429)."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                     {"k": "combat_evidence:" + str(seat_id)})
    digest = hashlib.sha256(env["record_bytes"]).hexdigest()
    prior = (await db.execute(text(
        "SELECT id, attach_key, other_player_id, payload_sha256 FROM combat_evidence "
        "WHERE stable_game_key = :k AND seat_player_id = :s FOR NO KEY UPDATE"),
        {"k": env["stable"], "s": seat_id})).mappings().first()
    if prior is not None:
        if (prior["attach_key"] == env["attach"] and prior["other_player_id"] == other_id
                and prior["payload_sha256"] == digest):
            return {"status": "already_recorded"}
        kind = ("attach_key" if prior["attach_key"] != env["attach"]
                else "other_seat" if prior["other_player_id"] != other_id else "payload")
        await db.execute(text(
            "UPDATE combat_evidence SET conflict_at = COALESCE(conflict_at, now()), "
            "  conflict_kind = COALESCE(conflict_kind, :ck) WHERE id = :i"),
            {"ck": kind, "i": prior["id"]})
        await db.commit()
        raise EvidenceRefused(409, "conflict")
    recent = (await db.execute(text(
        "SELECT count(*) FROM combat_evidence WHERE seat_player_id = :s "
        "AND received_at > now() - make_interval(hours => 1)"), {"s": seat_id})).scalar_one()
    if recent >= SEAT_HOURLY_CAP:
        raise EvidenceRefused(429, "seat_hourly_cap")
    await db.execute(text(
        "INSERT INTO combat_evidence (stable_game_key, attach_key, seat_player_id, other_player_id, "
        "  header_mod_version, consts_version, payload, payload_sha256, payload_bytes) "
        "VALUES (:k, :a, :s, :o, :hv, CAST(:cv AS smallint), CAST(:p AS jsonb), :dg, CAST(:n AS int))"),
        {"k": env["stable"], "a": env["attach"], "s": seat_id, "o": other_id,
         "hv": header_version, "cv": rec["consts"], "p": env["record_text"], "dg": digest,
         "n": len(env["record_bytes"])})
    await db.commit()
    return {"status": "recorded"}


# -- the worker's combat pass (primary only) ------------------------------------------

async def setting(db, key: str, default: str = "0") -> str:
    """An operational switch of this lane (whether a part of it runs, never
    what it judges); only the names in SWITCHES are read."""
    if key not in SWITCHES:
        raise KeyError(key)
    row = (await db.execute(text("SELECT value FROM runtime_settings WHERE key = :k"),
                            {"k": key})).first()
    return default if row is None else str(row[0])


def _jsonv(v):
    return json.loads(v) if isinstance(v, (str, bytes)) else v


def _has_lists(rec) -> bool:
    return all(k in rec for k in PURGED_LISTS)


def dedup_key(key: str, lo, hi) -> str:
    """The combat finding key of one game and canonical seat pair, in the
    combat namespace (DEDUP_PREFIX)."""
    return "%s%s|%s|%s" % (DEDUP_PREFIX, key, lo, hi)


# A game is a candidate when it has work: with no revision, while it is
# unattached; with one, while it is open, while a record with lists is
# still unevaluated under this revision, or when it holds MORE records than
# its last evaluation saw (a record that arrived after a one-sided game was
# finalized: the game is derived again and its contributions replaced).
_CANDIDATES = text(
    "SELECT e.stable_game_key k, LEAST(e.seat_player_id, e.other_player_id) lo, "
    "       GREATEST(e.seat_player_id, e.other_player_id) hi, max(e.received_at) rx "
    "  FROM combat_evidence e "
    "  LEFT JOIN combat_games g ON g.stable_game_key = e.stable_game_key "
    "   AND g.pair_lo = LEAST(e.seat_player_id, e.other_player_id) "
    "   AND g.pair_hi = GREATEST(e.seat_player_id, e.other_player_id) "
    " GROUP BY e.stable_game_key, LEAST(e.seat_player_id, e.other_player_id), "
    "          GREATEST(e.seat_player_id, e.other_player_id), g.finalized_at, g.match_id, "
    "          g.evaluated_rev, g.records_n, g.processed_at "
    "HAVING (CAST(:rev AS varchar) IS NULL AND g.finalized_at IS NULL AND g.match_id IS NULL) "
    "    OR (CAST(:rev AS varchar) IS NOT NULL AND (g.finalized_at IS NULL "
    "        OR (g.evaluated_rev IS DISTINCT FROM CAST(:rev AS varchar) "
    "            AND bool_or(e.lists_purged_at IS NULL)) "
    "        OR count(*) > g.records_n)) "
    " ORDER BY g.processed_at NULLS FIRST, rx LIMIT CAST(:lim AS int)")


async def _readiness(db, key, lo, hi, rows, match):
    """What a re-evaluation depends on: the attached match, the combat record
    set with its conflict markers, and the seat evidence records of the same
    game and pair."""
    seat_ids = (await db.execute(text(
        "SELECT id FROM seat_evidence WHERE stable_game_key = :k "
        "  AND LEAST(seat_player_id, other_player_id) = :lo "
        "  AND GREATEST(seat_player_id, other_player_id) = :hi ORDER BY id"),
        {"k": key, "lo": lo, "hi": hi})).scalars().all()
    return "%s|%s|%s" % (match["id"] if match else "-",
                         ",".join("%d:%d" % (r["id"], 1 if r["conflict_at"] else 0) for r in rows),
                         ",".join(str(i) for i in seat_ids))


async def evaluate_game(db, key: str, lo, hi, rs) -> tuple:
    """One game of one canonical seat pair, in the caller's transaction.
    Attaches the records to their ranked match by exact key (one that ended
    at least the ready lag ago, with the same unordered pair). With a
    revision loaded, re-derives when the readiness signature or the revision
    changed. A derivation that raises is stored as a fault of the game and
    leaves every record in place. Returns (state, fired, errors, evaluated)."""
    await db.execute(text(
        "INSERT INTO combat_games (stable_game_key, pair_lo, pair_hi) "
        "VALUES (:k, :lo, :hi) ON CONFLICT DO NOTHING"), {"k": key, "lo": lo, "hi": hi})
    g = (await db.execute(text(
        "SELECT readiness_sig, first_seen_at, finalized_at, evaluated_rev, match_id, records_n "
        "  FROM combat_games "
        "WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi FOR NO KEY UPDATE"),
        {"k": key, "lo": lo, "hi": hi})).mappings().first()
    rev = rs.rev if rs is not None else None
    rows = (await db.execute(text(
        "SELECT id, seat_player_id, other_player_id, attach_key, payload, conflict_at "
        "  FROM combat_evidence WHERE stable_game_key = :k "
        "   AND LEAST(seat_player_id, other_player_id) = :lo "
        "   AND GREATEST(seat_player_id, other_player_id) = :hi ORDER BY id"),
        {"k": key, "lo": lo, "hi": hi})).mappings().all()
    # A finalized game stays final under the same revision UNLESS a record
    # arrived after its last evaluation: then it is derived again (its
    # readiness signature names every record), and its contributions and
    # daily rows are replaced in this transaction.
    if (g["finalized_at"] is not None and (rev is None or g["evaluated_rev"] == rev)
            and len(rows) <= g["records_n"]):
        return "final", 0, 0, False
    if not rows:
        return "empty", 0, 0, False
    keys = sorted({r["attach_key"] for r in rows})
    match = (await db.execute(text(
        "SELECT id, photon_room_id, player1_id, player2_id, ended_at FROM matches "
        "WHERE photon_room_id = ANY(CAST(:keys AS varchar[])) AND is_ranked IS TRUE "
        "  AND ((player1_id = :lo AND player2_id = :hi) OR (player1_id = :hi AND player2_id = :lo)) "
        "  AND ended_at <= now() - make_interval(secs => CAST(:lag AS int)) "
        "ORDER BY ended_at LIMIT 1"),
        {"keys": keys, "lo": lo, "hi": hi, "lag": _sev.READY_LAG_S})).mappings().first()
    attach = match["photon_room_id"] if match else None
    if rs is None:
        # No revision: the attachment and its exact coverage (the records
        # whose attach key IS the match's room, paired when each names the
        # other) are kept; nothing is derived (no measure, fault,
        # contribution, daily row or finding).
        exact = [r for r in rows if match is not None and r["attach_key"] == attach]
        seats = {r["seat_player_id"] for r in exact}
        exact_paired = len(exact) == 2 and all(r["other_player_id"] in seats for r in exact)
        await db.execute(text(
            "UPDATE combat_games SET match_id = :m, attach_key = :a, coverage = :cov, "
            "  processed_at = now() "
            "WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi"),
            {"m": match["id"] if match else None, "a": attach,
             "cov": "paired" if exact_paired else "one", "k": key, "lo": lo, "hi": hi})
        return ("attached" if match else "waiting"), 0, 0, False
    sig = await _readiness(db, key, lo, hi, rows, match)
    now = datetime.now(timezone.utc)
    expired = g["first_seen_at"] < now - timedelta(days=GAME_EXPIRY_DAYS)
    if sig == g["readiness_sig"] and g["evaluated_rev"] == rev and not (expired and match is not None):
        await db.execute(text(
            "UPDATE combat_games SET processed_at = now() "
            "WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi"),
            {"k": key, "lo": lo, "hi": hi})
        return "unchanged", 0, 0, False
    # Exact attachment identity: only records whose attach key IS the attached
    # match's room take part. A record of the same stable key and pair under
    # another attach key is named in the game's faults and never compared.
    records = [{"seat": r["seat_player_id"], "other": r["other_player_id"],
                "rec": _jsonv(r["payload"])} for r in rows
               if match is not None and r["attach_key"] == attach]
    by_seat = {r["seat"] for r in records}
    paired = len(records) == 2 and all(r["other"] in by_seat for r in records)
    final = (match is not None and paired) or (match is not None and expired)
    fired = errors = 0
    evaluated = None
    faults = {}
    other_keys = [r["id"] for r in rows if match is not None and r["attach_key"] != attach]
    if other_keys:
        faults["other_attach_key"] = other_keys
    if match is not None:
        if any(not _has_lists(r["rec"]) for r in records):
            final = True
        else:
            try:
                for r in records:
                    faults[str(r["seat"])] = {"own_gun": cm.rebuild_faults(r["rec"], "s"),
                                              "other_gun": cm.rebuild_faults(r["rec"], "o"),
                                              "sections": cm.section_faults(r["rec"])}
                findings, _fired, errors = rs.evaluate_combat(records)
            except Exception as exc:              # noqa: BLE001 -- stored; the records stay
                faults["derive"] = type(exc).__name__
                findings = None
            if findings is None:
                # A derivation fault: the stored records, earlier findings,
                # contributions and daily rows are left exactly as they were,
                # and the game stays open so a later pass derives it again.
                errors += 1
                final = False
                sig = None
            else:
                dedup = dedup_key(key, lo, hi)
                produced = set()
                for rule, det in findings:
                    fid = await _sev.upsert_finding(db, "game", dedup, rule.id, rev, match["id"], det)
                    produced.add(rule.id)
                    await _sev.post_finding(db, fid, rs)
                fired = len(findings)
                await db.execute(text(
                    "DELETE FROM seat_evidence_findings WHERE scope = 'game' AND dedup_key = :k "
                    "AND flag_id IS NULL AND NOT (rule_id = ANY(CAST(:ids AS varchar[])))"),
                    {"k": dedup, "ids": sorted(produced) or [""]})
                await _write_contributions(db, key, lo, hi, records, match, paired)
                evaluated = rev
    await db.execute(text(
        "UPDATE combat_games SET match_id = :m, attach_key = :a, readiness_sig = :s, "
        "  coverage = :cov, processed_at = now(), record_faults = CAST(:f AS jsonb), "
        "  records_n = CAST(:n AS int), "
        "  evaluated_rev = COALESCE(CAST(:ev AS varchar), evaluated_rev), "
        "  finalized_at = CASE WHEN :fin THEN COALESCE(finalized_at, now()) ELSE NULL END "
        "WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi"),
        {"m": match["id"] if match else None, "a": attach, "s": sig,
         "cov": "paired" if paired else "one", "f": json.dumps(faults), "ev": evaluated,
         "fin": bool(final), "n": len(rows), "k": key, "lo": lo, "hi": hi})
    state = "final" if final else ("evaluated" if match else "waiting")
    return state, fired, errors, evaluated is not None


async def _write_contributions(db, key, lo, hi, records, match, paired):
    """Replace this game's contributions (per subject and source, with the
    game's coverage and the contributing record's measurement version), then
    re-roll every daily row of each affected (subject, UTC day) from the
    contributions in the same transaction, so a game is counted once and a
    one-sided game becomes a paired one when its second record arrives."""
    day = (await db.execute(text("SELECT (CAST(:t AS timestamptz) AT TIME ZONE 'UTC')::date"),
                            {"t": match["ended_at"]})).scalar_one()
    cov = "paired" if paired else "one"
    prior = (await db.execute(text(
        "DELETE FROM combat_contrib WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi "
        "RETURNING subject_player_id, utc_day"), {"k": key, "lo": lo, "hi": hi})).all()
    touched = {(str(p[0]), p[1]) for p in prior}
    for c in cm.contributions(records):
        await db.execute(text(
            "INSERT INTO combat_contrib (stable_game_key, pair_lo, pair_hi, subject_player_id, source, "
            "  coverage, consts_version, utc_day, sums) "
            "VALUES (:k, :lo, :hi, :sub, :src, :cov, CAST(:cv AS smallint), :d, CAST(:sums AS jsonb))"),
            {"k": key, "lo": lo, "hi": hi, "sub": c["subject"], "src": c["source"], "cov": cov,
             "cv": c["consts"], "d": day, "sums": json.dumps(c["sums"])})
        touched.add((str(c["subject"]), day))
    for subject, d in sorted(touched):
        await _reroll_daily(db, subject, d)


async def _reroll_daily(db, subject, day):
    """One subject's daily rows for one UTC day, rebuilt from contributions:
    one row per (source, coverage, measurement version), never mixing
    versions. Serialized per (subject, day) by a transaction advisory lock."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                     {"k": "combat_daily:%s:%s" % (subject, day)})
    rows = (await db.execute(text(
        "SELECT source, coverage, consts_version, sums FROM combat_contrib "
        "WHERE subject_player_id = CAST(:s AS uuid) AND utc_day = :d "
        "ORDER BY stable_game_key, pair_lo, pair_hi, source"),
        {"s": subject, "d": day})).mappings().all()
    agg = {}
    for r in rows:
        k = (r["source"], r["coverage"], r["consts_version"])
        games, sums = agg.get(k, (0, {}))
        agg[k] = (games + 1, cm.add_sums(sums, _jsonv(r["sums"]) or {}))
    await db.execute(text(
        "DELETE FROM combat_player_daily WHERE subject_player_id = CAST(:s AS uuid) AND utc_day = :d"),
        {"s": subject, "d": day})
    for (src, cov, cv), (games, sums) in sorted(agg.items()):
        await db.execute(text(
            "INSERT INTO combat_player_daily (subject_player_id, utc_day, source, coverage, "
            "  consts_version, games, sums) "
            "VALUES (CAST(:s AS uuid), :d, :src, :cov, CAST(:cv AS smallint), CAST(:g AS int), "
            "        CAST(:sums AS jsonb))"),
            {"s": subject, "d": day, "src": src, "cov": cov, "cv": cv, "g": games,
             "sums": json.dumps(sums)})


async def games_pass(session_factory, state=None, limit: int = GAMES_PER_PASS) -> dict:
    """Combat games waiting for work, each in its own transaction so one bad
    game cannot hold back the rest. `state` is review_rules' published state;
    its ruleset is None unless a revision is loaded."""
    rs = state.ruleset if state is not None else None
    stats = {"evaluated": 0, "fired": 0, "rule_errors": 0}
    async with session_factory() as db:
        if await setting(db, "combat_evidence_worker") != "1":
            return {"off": 1}
        cands = (await db.execute(_CANDIDATES, {"lim": limit,
                                                "rev": rs.rev if rs else None})).all()
    for key, lo, hi, _rx in cands:
        async with session_factory() as db:
            try:
                st, fired, errors, done = await evaluate_game(db, key, lo, hi, rs)
                await db.commit()
            except Exception as exc:          # noqa: BLE001 -- counted, next game
                await db.rollback()
                st, fired, errors, done = "error:" + type(exc).__name__, 0, 0, False
        stats[st] = stats.get(st, 0) + 1
        stats["evaluated"] += 1 if done else 0
        stats["fired"] += fired
        stats["rule_errors"] += errors
    return stats


async def purge_pass(session_factory) -> dict:
    """Retention: trimmable lists out of the payload after
    LIST_RETENTION_DAYS (totals, cycle summaries, stat blocks and histograms
    stay); records never attached after GAME_EXPIRY_DAYS; contributions and
    daily rows after AGG_RETENTION_DAYS."""
    out = {}
    async with session_factory() as db:
        if await setting(db, "combat_evidence_purge") != "1":
            return {"off": 1}
        out["lists"] = (await db.execute(text(
            "UPDATE combat_evidence SET payload = payload - CAST(:keys AS text[]), "
            "  lists_purged_at = now() "
            "WHERE lists_purged_at IS NULL "
            "  AND received_at < now() - make_interval(days => CAST(:d AS int))"),
            {"keys": list(PURGED_LISTS), "d": LIST_RETENTION_DAYS})).rowcount
        out["unattached"] = (await db.execute(text(
            "DELETE FROM combat_evidence e "
            "WHERE e.received_at < now() - make_interval(days => CAST(:d AS int)) "
            "  AND NOT EXISTS (SELECT 1 FROM combat_games g "
            "    WHERE g.stable_game_key = e.stable_game_key "
            "      AND g.pair_lo = LEAST(e.seat_player_id, e.other_player_id) "
            "      AND g.pair_hi = GREATEST(e.seat_player_id, e.other_player_id) "
            "      AND g.match_id IS NOT NULL)"), {"d": GAME_EXPIRY_DAYS})).rowcount
        out["games"] = (await db.execute(text(
            "DELETE FROM combat_games g WHERE g.match_id IS NULL "
            "  AND NOT EXISTS (SELECT 1 FROM combat_evidence e "
            "    WHERE e.stable_game_key = g.stable_game_key "
            "      AND LEAST(e.seat_player_id, e.other_player_id) = g.pair_lo "
            "      AND GREATEST(e.seat_player_id, e.other_player_id) = g.pair_hi)"))).rowcount
        out["contrib"] = (await db.execute(text(
            "DELETE FROM combat_contrib "
            "WHERE utc_day < (now() AT TIME ZONE 'UTC')::date - CAST(:d AS int)"),
            {"d": AGG_RETENTION_DAYS})).rowcount
        out["daily"] = (await db.execute(text(
            "DELETE FROM combat_player_daily "
            "WHERE utc_day < (now() AT TIME ZONE 'UTC')::date - CAST(:d AS int)"),
            {"d": AGG_RETENTION_DAYS})).rowcount
        await db.commit()
    return out


# -- the admin read --------------------------------------------------------------

def _not_run_counts(node, out):
    if isinstance(node, dict):
        reason = node.get("not_run")
        if isinstance(reason, str):
            out[reason] = out.get(reason, 0) + 1
        for v in node.values():
            _not_run_counts(v, out)
    elif isinstance(node, list):
        for v in node:
            _not_run_counts(v, out)
    return out


def q1_display(view, not_run="lists_purged") -> list:
    """The display case of every gun of a game, as the admin read heads it:
    which accounts exist (only the measuring seat's, only the owner's, both
    agreeing, both differing), the case's own wording, both labels, and every
    input that could not be compared, counted by its NOT-RUN reason
    (missing record, trimmed, incompatible version, ambiguous, absent). A
    game whose lists were purged, or whose records cannot be tied to one
    attachment, has no comparison at all and says which."""
    if view is None:
        return [{"owner": None, "case": "not_run", "not_run": {not_run or "lists_purged": 1}}]
    out = []
    for d in view["directions"]:
        out.append({"owner": d["owner"], "case": d["case"], "case_text": d["case_text"],
                    "self_label": d["self_label"] if d["self_present"] else None,
                    "meas_label": d["meas_label"] if d["meas_present"] else None,
                    "not_run": _not_run_counts(d, {})})
    return out


async def admin_view(db, *, match_id=None, stable_game_key=None, rs=None) -> dict:
    """Every combat game under a stable key, or exactly the games attached to
    a match, one per canonical seat pair: the compared records with their
    provenance, the attachment, the stored record faults, the findings (rule
    id and revision), and the pair view computed now. Per gun the view states
    which case it is (only the measuring seat's record, only the owner's,
    both agreeing, both differing) and marks every input that is missing,
    trimmed or of an incompatible measurement version NOT-RUN.

    A match read keeps the selected (stable game key, pair) of each attached
    game: no other pair under the same stable key is read. Within one game
    only the records whose attach key IS the game's attachment are compared;
    a record of the same key and pair under another attach key is listed
    under `other_attachment` (provenance only, never compared). A game with
    no attachment compares its records only when they share one attach key;
    otherwise the view is NOT-RUN (`attachment_unresolved`) and every record
    is listed as provenance. Steam ids only; no display name is read."""
    if match_id is not None:
        games = (await db.execute(text(
            "SELECT stable_game_key, pair_lo, pair_hi FROM combat_games "
            "WHERE match_id = CAST(:m AS uuid) ORDER BY stable_game_key, pair_lo, pair_hi"),
            {"m": match_id})).mappings().all()
        selected = [(g["stable_game_key"], (g["pair_lo"], g["pair_hi"])) for g in games]
    else:
        selected = None
    out = {"review_rules": rs.rev if rs is not None else _sev.rr.health_word(), "games": []}
    keys = sorted({k for k, _p in selected}) if selected is not None else [stable_game_key]
    for key in keys:
        rows = (await db.execute(text(
            "SELECT e.id, e.attach_key, e.seat_player_id, e.other_player_id, ps.steam_id seat_steam, "
            "       po.steam_id other_steam, e.payload, e.header_mod_version, e.consts_version, "
            "       e.conflict_at, e.conflict_kind, e.received_at, e.lists_purged_at, e.payload_bytes "
            "  FROM combat_evidence e JOIN players ps ON ps.id = e.seat_player_id "
            "  JOIN players po ON po.id = e.other_player_id "
            " WHERE e.stable_game_key = :k ORDER BY e.id"), {"k": key})).mappings().all()
        by_pair = {}
        for r in rows:
            by_pair.setdefault(_sev._norm_pair(r["seat_player_id"], r["other_player_id"]), []).append(r)
        if selected is not None:
            wanted = {pair for k, pair in selected if k == key}
            by_pair = {pair: prow for pair, prow in by_pair.items() if pair in wanted}
        for (lo, hi), prow in sorted(by_pair.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
            g = (await db.execute(text(
                "SELECT match_id, attach_key, coverage, finalized_at, evaluated_rev, record_faults "
                "FROM combat_games WHERE stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi"),
                {"k": key, "lo": lo, "hi": hi})).mappings().first()
            steam = {}
            for r in prow:
                steam[r["seat_player_id"]] = r["seat_steam"]
                steam[r["other_player_id"]] = r["other_steam"]
            attach = g["attach_key"] if g else None
            if attach is not None:
                compared = [r for r in prow if r["attach_key"] == attach]
                unresolved = False
            else:
                unresolved = len({r["attach_key"] for r in prow}) > 1
                compared = [] if unresolved else list(prow)
            others = [r for r in prow if r not in compared]
            records = [{"seat": steam[r["seat_player_id"]], "other": steam[r["other_player_id"]],
                        "rec": _jsonv(r["payload"])} for r in compared]
            view = None
            not_run = None
            if unresolved:
                not_run = "attachment_unresolved"
            elif all(_has_lists(x["rec"]) for x in records):
                view = cm.pair_view(records)
            else:
                not_run = "lists_purged"
            findings = (await db.execute(text(
                "SELECT rule_id, rules_rev, details, flag_id FROM seat_evidence_findings "
                "WHERE scope = 'game' AND dedup_key = :k ORDER BY rule_id"),
                {"k": dedup_key(key, lo, hi)})).mappings().all()
            out["games"].append({
                "stable_game_key": key,
                "pair": [steam.get(lo), steam.get(hi)],
                "match_id": str(g["match_id"]) if g and g["match_id"] else None,
                "attach_key": attach,
                "coverage": g["coverage"] if g else None,
                "final": bool(g and g["finalized_at"]),
                "evaluated_rev": g["evaluated_rev"] if g else None,
                "record_faults": _jsonv(g["record_faults"]) if g else None,
                "records": [{"seat_steam_id": r["seat_steam"], "other_steam_id": r["other_steam"],
                             "attach_key": r["attach_key"], "consts": r["consts_version"],
                             "received_at": r["received_at"].isoformat(),
                             "conflict_kind": r["conflict_kind"], "payload_bytes": r["payload_bytes"],
                             "lists_purged": r["lists_purged_at"] is not None,
                             "record": _jsonv(r["payload"])} for r in compared],
                "other_attachment": [{"seat_steam_id": r["seat_steam"],
                                      "other_steam_id": r["other_steam"],
                                      "attach_key": r["attach_key"], "consts": r["consts_version"],
                                      "received_at": r["received_at"].isoformat(),
                                      "not_run": ("attachment_unresolved" if unresolved
                                                  else "other_attachment")} for r in others],
                "view": view,
                "view_not_run": not_run,
                "display": q1_display(view, not_run),
                "findings": [{"rule_id": f["rule_id"], "rules_rev": f["rules_rev"],
                              "details": _jsonv(f["details"]),
                              "posted_flag_id": str(f["flag_id"]) if f["flag_id"] else None}
                             for f in findings],
            })
    return out
