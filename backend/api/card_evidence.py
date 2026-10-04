"""Card draw evidence, server half (migration 370).

What this module holds, and what it never does:

  * the envelope check, the signature (its own `card-evidence:v1:` string,
    new and separate from the 7-field match HMAC and from the seat evidence
    string) and the record check (card_measures.check_record);
  * storage: the first card record per (stable game key, seat), the conflict
    marker, the hourly cap, and the census registry an admin fills from a
    reference seat's census dump;
  * the worker's card pass: attaching records to their ranked match, and with
    a loaded rules revision the derived rows (hand and phase measures that
    read other than zero, per-game contributions, daily sums) and the card
    rules over them; the purge;
  * the admin read.

Judging is not here. The descriptions of the evidence are the public
vocabulary in card_measures; which of them opens a review item, at what value,
over which window and with what words, is a rules revision that is not part of
this repository. With no valid revision the pass attaches records and purges,
writes no derived row and opens nothing.

Outside this lane's own tables, statements here read `matches`,
`ranked_series`, `players` and `runtime_settings`, and write only
`seat_evidence_findings` and, through seat_evidence.post_finding,
`flagged_matches` (advisory rows, `flag_reason = 'review'`,
`auto_invalidated = false`, only for a rule the revision arms). The lane's own
tables are `card_evidence`, `card_pool_registry`, `card_games`,
`card_hand_outside`, `card_phase_outside`, `card_contrib` and
`card_player_daily`. No statement here touches a match result, a rating, gold,
`match_cards` or `card_offers`; a test scans every statement of this module.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

import card_measures as cm
import review_rules as rr
import seat_evidence as se

W = cm.CARD_WIRE
EvidenceRefused = se.EvidenceRefused
# Scheduling and retention bounds (operational; pinned by value in the guard).
CARD_LIMITS = {"games_per_pass": 500, "expiry_days": 14, "list_retention_days": 120,
               "derived_retention_days": 400, "unregistered_days": 30, "admin_rows": 50}
SWITCHES = ("card_evidence_accept", "card_evidence_worker", "card_evidence_purge")
LIST_KEYS = ("cards", "held0", "ph", "hd", "ap")
_PRINTABLE = re.compile(r"[ -~]+")
_HAND_KEYS = cm.HAND_RULES + cm.PICK_RULES
_PHASE_KEYS = cm.PHASE_RULES


# -- the envelope and the signature ----------------------------------------------

def parse_envelope(payload) -> dict:
    """The seat evidence envelope checks (contract, both steam ids, the stable
    and attach keys, the signature's form), then the card bounds: a record of
    at most the card cap, printable ASCII. Raises EvidenceRefused(400/413/422)."""
    env = se.parse_envelope(payload)
    if len(env["record_bytes"]) > W["record_max_bytes"]:
        raise EvidenceRefused(413, "record_bytes")
    if not _PRINTABLE.fullmatch(env["record_text"]):
        raise EvidenceRefused(422, "record_ascii")
    return env


def parse_record(env: dict) -> dict:
    try:
        return cm.parse_record_text(env["record_text"])
    except cm.Refusal as r:
        raise EvidenceRefused(422, r.field)


def record_canonical(env: dict) -> str:
    h = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    return (W["prefix"] + env["seat"] + ":" + env["other"] + ":"
            + h(env["stable"].encode("ascii")) + ":" + h(env["attach"].encode("ascii")) + ":"
            + h(env["record_bytes"]))


def record_sign(key: str, env: dict) -> str:
    return hmac.new(key.encode(), record_canonical(env).encode(), hashlib.sha256).hexdigest()


def verify_sig(key: str, env: dict) -> bool:
    if not key:
        return False
    return hmac.compare_digest(env["sig"], record_sign(key, env))


# -- the route's stores --------------------------------------------------------------

async def setting(db, key: str, default: str = "0") -> str:
    """An operational switch of this lane (whether a part runs, never what it
    judges); only the names in SWITCHES are read."""
    if key not in SWITCHES:
        raise KeyError(key)
    row = (await db.execute(text("SELECT value FROM runtime_settings WHERE key = :k"),
                            {"k": key})).first()
    return default if row is None else str(row[0])


async def store_record(db, env: dict, rec: dict, seat_id, other_id, header_version) -> dict:
    """Insert the first card record for (stable key, seat), or answer the
    repeat: the same record again is already_recorded; a different one sets
    the conflict marker once and answers 409, the first record kept.
    Serialized per seat by a transaction advisory lock, so the hourly cap and
    the first-record rule hold under concurrent deliveries."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                     {"k": "card_evidence:" + str(seat_id)})
    digest = hashlib.sha256(env["record_bytes"]).hexdigest()
    prior = (await db.execute(text(
        "SELECT id, attach_key, other_player_id, payload_sha256 FROM card_evidence "
        "WHERE stable_game_key = :k AND seat_player_id = :s FOR UPDATE"),
        {"k": env["stable"], "s": seat_id})).mappings().first()
    if prior is not None:
        if (prior["attach_key"] == env["attach"] and prior["other_player_id"] == other_id
                and prior["payload_sha256"] == digest):
            return {"status": "already_recorded"}
        kind = ("attach_key" if prior["attach_key"] != env["attach"]
                else "other_seat" if prior["other_player_id"] != other_id else "payload")
        await db.execute(text(
            "UPDATE card_evidence SET conflict_at = COALESCE(conflict_at, now()), "
            "  conflict_kind = COALESCE(conflict_kind, :ck) WHERE id = :i"),
            {"ck": kind, "i": prior["id"]})
        await db.commit()
        raise EvidenceRefused(409, "conflict")
    recent = (await db.execute(text(
        "SELECT count(*) FROM card_evidence WHERE seat_player_id = :s "
        "AND received_at > now() - make_interval(hours => 1)"), {"s": seat_id})).scalar_one()
    if recent >= W["hourly_cap"]:
        raise EvidenceRefused(429, "seat_hourly_cap")
    count, pool_digest, pool_state = rec["pool"]
    await db.execute(text(
        "INSERT INTO card_evidence (stable_game_key, attach_key, seat_player_id, other_player_id, "
        "  header_mod_version, pool_digest, pool_state, deal_profile, payload, payload_sha256, "
        "  payload_bytes) "
        "VALUES (:k, :a, :s, :o, :hv, :pd, :ps, :dp, CAST(:p AS jsonb), :dg, :n)"),
        {"k": env["stable"], "a": env["attach"], "s": seat_id, "o": other_id,
         "hv": header_version, "pd": pool_digest or None, "ps": pool_state,
         "dp": cm.deal_profile(rec), "p": env["record_text"], "dg": digest,
         "n": len(env["record_bytes"])})
    await db.commit()
    return {"status": "recorded"}


async def register_census(db, doc) -> dict:
    """Admin registration of one reference seat's census dump. The stated
    digest must be the digest of the dump's own census text and the text its
    own canonical form (card_measures.census_from_dump); a dump that is not is
    refused 422 and nothing is stored."""
    try:
        c = cm.census_from_dump(doc)
    except cm.Refusal as r:
        raise EvidenceRefused(422, r.field)
    got = (await db.execute(text(
        "INSERT INTO card_pool_registry (digest, census, card_count, slot_count, game_dll_sha256) "
        "VALUES (:d, CAST(:c AS jsonb), :n, :ns, :g) ON CONFLICT (digest) DO NOTHING RETURNING digest"),
        {"d": c.digest, "c": cm.dumps(doc), "n": c.count, "ns": c.slots, "g": c.game_sha})).first()
    await db.commit()
    return {"status": "registered" if got else "already_registered", "digest": c.digest,
            "card_count": c.count, "slot_count": c.slots}


# -- the worker's card pass (primary only) ----------------------------------------------

async def _registry(db, digests) -> dict:
    """The registered censuses for the digests a game's records name."""
    if not digests:
        return {}
    rows = (await db.execute(text(
        "SELECT census FROM card_pool_registry WHERE digest = ANY(CAST(:d AS varchar[]))"),
        {"d": sorted(digests)})).all()
    out = {}
    for (doc,) in rows:
        c = cm.census_from_dump(se._jsonv(doc))
        out[c.digest] = c
    return out


# Games waiting for work, least recently processed first. With a revision:
# every game not yet final; every game holding its lists whose last evaluation
# was under another revision; every game with a record received, or a census
# registered for one of its records, after it was last processed. With none:
# only games not yet attached to their match.
_CANDIDATES = text(
    "SELECT e.stable_game_key k, LEAST(e.seat_player_id, e.other_player_id) lo, "
    "       GREATEST(e.seat_player_id, e.other_player_id) hi, max(e.received_at) rx "
    "  FROM card_evidence e "
    "  LEFT JOIN card_games g ON g.stable_game_key = e.stable_game_key "
    "   AND g.pair_lo = LEAST(e.seat_player_id, e.other_player_id) "
    "   AND g.pair_hi = GREATEST(e.seat_player_id, e.other_player_id) "
    "  LEFT JOIN card_pool_registry p ON p.digest = e.pool_digest "
    " WHERE (CAST(:rev AS varchar) IS NULL AND g.finalized_at IS NULL AND g.match_id IS NULL) "
    "    OR (CAST(:rev AS varchar) IS NOT NULL AND (g.finalized_at IS NULL "
    "        OR (e.lists_purged_at IS NULL AND (g.evaluated_rev IS DISTINCT FROM CAST(:rev AS varchar) "
    "            OR e.received_at > g.processed_at OR p.registered_at > g.processed_at)))) "
    " GROUP BY e.stable_game_key, LEAST(e.seat_player_id, e.other_player_id), "
    "          GREATEST(e.seat_player_id, e.other_player_id) "
    " ORDER BY min(g.processed_at) NULLS FIRST, rx LIMIT CAST(:lim AS int)")

_MATCH = text(
    "SELECT m.id, m.ended_at, m.photon_room_id, "
    "       CASE WHEN jsonb_typeof(s.rules -> 'sc') = 'boolean' "
    "            THEN CASE WHEN (s.rules ->> 'sc')::boolean THEN 'on' ELSE 'off' END END AS sc "
    "  FROM matches m LEFT JOIN ranked_series s ON s.id = m.series_id "
    " WHERE m.photon_room_id = ANY(CAST(:keys AS varchar[])) AND m.is_ranked IS TRUE "
    "   AND ((m.player1_id = :lo AND m.player2_id = :hi) OR (m.player1_id = :hi AND m.player2_id = :lo)) "
    "   AND m.ended_at <= now() - make_interval(secs => CAST(:lag AS int)) "
    " ORDER BY m.ended_at LIMIT 1")

_WHERE_GAME = "stable_game_key = :k AND pair_lo = :lo AND pair_hi = :hi"


def _records(rows) -> list:
    return [{"seat": str(r["seat_player_id"]), "other": str(r["other_player_id"]),
             "rec": se._jsonv(r["payload"]), "conflict": r["conflict_at"] is not None} for r in rows]


def _has_lists(rec) -> bool:
    return all(k in rec for k in LIST_KEYS)


def _signature(match, rows, named_ids, registry) -> str:
    regs = ",".join(sorted(registry))
    return "%s|%s|%s|%s" % (
        match["id"] if match else "-", match["sc"] if match else "-",
        ",".join("%d:%d:%d" % (r["id"], 1 if r["conflict_at"] else 0, 1 if r["id"] in named_ids else 0)
                 for r in rows),
        hashlib.sha256(regs.encode("ascii")).hexdigest())


def _nonzero(row, keys) -> dict:
    return {k: row[k] for k in keys if row.get(k) is not None and row[k] != 0}


async def _write_outside(db, key, lo, hi, view, rev) -> int:
    await db.execute(text("DELETE FROM card_hand_outside WHERE " + _WHERE_GAME),
                     {"k": key, "lo": lo, "hi": hi})
    await db.execute(text("DELETE FROM card_phase_outside WHERE " + _WHERE_GAME),
                     {"k": key, "lo": lo, "hi": hi})
    n = 0
    for row, meta in view["hands"]:
        bad = _nonzero(row, _HAND_KEYS)
        if bad:
            await db.execute(text(
                "INSERT INTO card_hand_outside (stable_game_key, pair_lo, pair_hi, recorder_player_id, "
                "  dealer_player_id, phase, deal, rules_rev, measures) "
                "VALUES (:k, :lo, :hi, CAST(:r AS uuid), CAST(:d AS uuid), :o, :dl, :rev, CAST(:m AS jsonb)) "
                "ON CONFLICT DO NOTHING"),
                {"k": key, "lo": lo, "hi": hi, "r": meta["recorder"], "d": meta["dealer"],
                 "o": meta["o"], "dl": meta["k"], "rev": rev, "m": cm.dumps(bad)})
            n += 1
    for row, meta in view["phases"]:
        bad = _nonzero(row, _PHASE_KEYS)
        if bad:
            await db.execute(text(
                "INSERT INTO card_phase_outside (stable_game_key, pair_lo, pair_hi, recorder_player_id, "
                "  phase, rules_rev, measures) "
                "VALUES (:k, :lo, :hi, CAST(:r AS uuid), :o, :rev, CAST(:m AS jsonb)) "
                "ON CONFLICT DO NOTHING"),
                {"k": key, "lo": lo, "hi": hi, "r": meta["recorder"], "o": meta["o"], "rev": rev,
                 "m": cm.dumps(bad)})
            n += 1
    return n


_DAILY_COLS = ("hands", "slots", "notrun_hands") + tuple(
    part + "_" + name for part in ("obs", "exp", "var") for name in cm.RARITIES)


async def _recompute_daily(db, keys) -> None:
    """Each daily row named in `keys` (subject, day, source, coverage,
    profile, revision) recomputed from card_contrib, under a per-subject
    transaction advisory lock so two games of one dealer cannot interleave."""
    for subject in sorted({k[0] for k in keys}):
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                         {"k": "card_daily:" + subject})
    sums = ", ".join("COALESCE(sum(c.%s), 0)" % c for c in _DAILY_COLS)
    for subject, day, source, coverage, profile, rev in sorted(keys):
        b = {"s": subject, "d": day, "src": source, "cov": coverage, "p": profile, "rev": rev}
        await db.execute(text(
            "DELETE FROM card_player_daily WHERE subject_player_id = CAST(:s AS uuid) AND day = :d "
            "AND source = :src AND coverage = :cov AND deal_profile = :p AND rules_rev = :rev"), b)
        await db.execute(text(
            "INSERT INTO card_player_daily (subject_player_id, day, source, coverage, deal_profile, "
            "  rules_rev, games, " + ", ".join(_DAILY_COLS) + ") "
            "SELECT CAST(:s AS uuid), :d, :src, :cov, :p, :rev, "
            "  count(DISTINCT (c.stable_game_key, c.pair_lo, c.pair_hi)), " + sums + " "
            "  FROM card_contrib c WHERE c.subject_player_id = CAST(:s AS uuid) AND c.utc_day = :d "
            "   AND c.source = :src AND c.coverage = :cov AND c.deal_profile = :p AND c.rules_rev = :rev "
            "HAVING count(*) > 0"), b)


async def _write_contrib(db, key, lo, hi, view, rs, match) -> list:
    """Replace this game's contributions under this revision and recompute
    every daily row they touched, before and after. Returns the new keys."""
    rev = rs.rev
    weights = rs.params.get(cm.WEIGHTS)
    day = match["ended_at"].astimezone(timezone.utc).date()
    old = (await db.execute(text(
        "DELETE FROM card_contrib WHERE " + _WHERE_GAME + " AND rules_rev = :rev "
        "RETURNING subject_player_id, utc_day, source, coverage, deal_profile"),
        {"k": key, "lo": lo, "hi": hi, "rev": rev})).all()
    touched = {(str(r[0]), r[1], r[2], r[3], r[4], rev) for r in old}
    new = []
    for c in cm.contributions(view, weights):
        vals = {"k": key, "lo": lo, "hi": hi, "r": c["recorder"], "s": c["subject"],
                "src": c["source"], "cov": c["coverage"], "p": c["profile"], "rev": rev, "d": day,
                "m": match["id"], "hands": c["hands"], "slots": c["slots"],
                "notrun_hands": c["notrun_hands"]}
        for part in ("obs", "exp", "var"):
            for i, name in enumerate(cm.RARITIES):
                vals[part + "_" + name] = c[part][i]
        await db.execute(text(
            "INSERT INTO card_contrib (stable_game_key, pair_lo, pair_hi, recorder_player_id, "
            "  subject_player_id, source, coverage, deal_profile, rules_rev, utc_day, match_id, "
            + ", ".join(_DAILY_COLS) + ") "
            "VALUES (:k, :lo, :hi, CAST(:r AS uuid), CAST(:s AS uuid), :src, :cov, :p, :rev, :d, :m, "
            + ", ".join(":" + c_ for c_ in _DAILY_COLS) + ")"), vals)
        nk = (c["subject"], day, c["source"], c["coverage"], c["profile"], rev)
        touched.add(nk)
        new.append(nk)
    await _recompute_daily(db, touched)
    return new


async def _windows(db, keys, rs) -> list:
    """The window sums for each (dealer, source, coverage, profile) a game
    touched, over the revision's window ending on the game's day. None
    without a window in the revision."""
    win = rs.params.get(cm.WINDOW)
    if not win:
        return []
    out = []
    sums = ", ".join("COALESCE(sum(%s), 0) AS %s" % (c, c) for c in ("games",) + _DAILY_COLS)
    for subject, day, source, coverage, profile, rev in sorted(set(keys)):
        r = (await db.execute(text(
            "SELECT " + sums + " FROM card_player_daily WHERE subject_player_id = CAST(:s AS uuid) "
            "AND source = :src AND coverage = :cov AND deal_profile = :p AND rules_rev = :rev "
            "AND day > CAST(:d AS date) - CAST(:w AS int) AND day <= CAST(:d AS date)"),
            {"s": subject, "src": source, "cov": coverage, "p": profile, "rev": rev, "d": day,
             "w": int(win[cm.WINDOW_KEY])})).mappings().first()
        agg = {c: int(r[c]) for c in ("games", "hands", "slots", "notrun_hands")}
        agg.update(source=source, coverage=coverage)
        for part in ("obs", "exp", "var"):
            agg[part] = [int(r[part + "_" + name]) for name in cm.RARITIES]
        out.append(((subject, day, source, coverage, profile), agg))
    return out


async def _post_findings(db, findings, dedup_of, rs, match_id) -> tuple:
    """Upsert one finding per (dedup key, rule) the evaluation produced, post
    those the revision arms, and remove this game's unposted findings it no
    longer produces. Returns (count, produced dedup keys)."""
    grouped = {}
    for rule, items in findings:
        for k, item in items:
            grouped.setdefault((dedup_of(k), rule), []).append(item)
    for (dedup, rule), items in sorted(grouped.items(), key=lambda x: (x[0][0][1], x[0][1].id)):
        scope, key = dedup
        fid = await se.upsert_finding(db, scope, key, rule.id, rs.rev, match_id, {"items": items})
        await se.post_finding(db, fid, rs)
    return len(grouped), {(d[1], rule.id) for (d, rule) in grouped}


async def evaluate_card_game(db, key: str, lo, hi, rs) -> tuple:
    """One game, in the caller's transaction (see the candidate query for
    which games come here). Attaches the records to their ranked match (one
    ended at least READY_LAG_S ago; each record only to the match its own
    attach key names); with no revision that is all. With one, re-derives when
    the readiness signature (match, series rule, records, conflicts, which
    censuses are registered) or the revision changed: the hand and phase
    rows, the contributions and daily sums, the card rules over the game and
    over each touched window. Final once the match is attached and both
    records name it, or after the expiry, or with lists purged. Returns
    (state, fired, rule errors, evaluated)."""
    lim = CARD_LIMITS
    b = {"k": key, "lo": lo, "hi": hi}
    await db.execute(text(
        "INSERT INTO card_games (stable_game_key, pair_lo, pair_hi) VALUES (:k, :lo, :hi) "
        "ON CONFLICT DO NOTHING"), b)
    g = (await db.execute(text(
        "SELECT signature, first_seen_at, finalized_at, evaluated_rev, match_id FROM card_games "
        "WHERE " + _WHERE_GAME + " FOR UPDATE"), b)).mappings().first()
    rev = rs.rev if rs is not None else None
    rows = (await db.execute(text(
        "SELECT id, seat_player_id, other_player_id, attach_key, payload, pool_digest, conflict_at, "
        "       received_at FROM card_evidence "
        "WHERE stable_game_key = :k AND LEAST(seat_player_id, other_player_id) = :lo "
        "  AND GREATEST(seat_player_id, other_player_id) = :hi ORDER BY id"), b)).mappings().all()
    if not rows:
        return "empty", 0, 0, False
    keys = sorted({r["attach_key"] for r in rows})
    match = (await db.execute(_MATCH, {"keys": keys, "lo": lo, "hi": hi,
                                       "lag": se.READY_LAG_S})).mappings().first()
    if rs is None:
        await db.execute(text(
            "UPDATE card_games SET match_id = :m, series_sc = :sc, processed_at = now() WHERE "
            + _WHERE_GAME), dict(b, m=match["id"] if match else None, sc=match["sc"] if match else None))
        return ("attached" if match else "waiting"), 0, 0, False
    named, other_key = se.attached_records(rows, match)
    named_ids = {r["id"] for r in named}
    registry = await _registry(db, {r["pool_digest"] for r in rows if r["pool_digest"]})
    sig = _signature(match, rows, named_ids, registry)
    expired = g["first_seen_at"] < datetime.now(timezone.utc) - timedelta(days=lim["expiry_days"])
    if sig == g["signature"] and g["evaluated_rev"] == rev and not (expired and match is not None):
        await db.execute(text("UPDATE card_games SET processed_at = now() WHERE " + _WHERE_GAME), b)
        return "unchanged", 0, 0, False
    final = match is not None and ((len(named) >= cm.W["players"] and not other_key) or expired)
    fired = errors = 0
    evaluated = None
    fault = None
    if match is not None and named:
        records = _records(named)
        if any(not _has_lists(r["rec"]) for r in records):
            final = True          # lists purged: nothing left to derive
        else:
            try:
                view = await asyncio.to_thread(cm.card_view, records, registry, match["sc"],
                                               rs.params.get(cm.WEIGHTS))
            except Exception as exc:          # noqa: BLE001 -- recorded on the game, next game
                view = None
                fault = type(exc).__name__
            if view is not None:
                await _write_outside(db, key, lo, hi, view, rev)
                touched = await _write_contrib(db, key, lo, hi, view, rs, match)
                wins = await _windows(db, touched, rs)
                windows = [cm.window_row(agg) for _k, agg in wins]
                subjects = cm.card_subjects(view, windows)
                findings, notes, _fired, errors = await asyncio.to_thread(rs.evaluate_card, subjects)
                game_dedup = "card|%s|%s|%s" % (key, lo, hi)

                def dedup_of(k):
                    if k[0] == cm.WINDOW_SUBJECT:
                        s, d, src, cov, p = wins[k[1]][0]
                        return ("sitting", "card|win|%s|%s|%s|%s|%s" % (s, src, cov, p, d))
                    return ("game", game_dedup)
                if notes:
                    findings = [(rule, [(k, dict(it, notes=[ln for _r, ln in notes])) for k, it in items])
                                for rule, items in findings]
                fired, produced = await _post_findings(db, findings, dedup_of, rs, match["id"])
                mine = [game_dedup] + [dedup_of((cm.WINDOW_SUBJECT, j))[1] for j in range(len(wins))]
                for d in mine:
                    keep = sorted(rid for (dk, rid) in produced if dk == d)
                    await db.execute(text(
                        "DELETE FROM seat_evidence_findings WHERE dedup_key = :k AND flag_id IS NULL "
                        "AND rules_rev = :rev AND NOT (rule_id = ANY(CAST(:ids AS varchar[])))"),
                        {"k": d, "rev": rev, "ids": keep or [""]})
                evaluated = rev
    await db.execute(text(
        "UPDATE card_games SET match_id = :m, series_sc = :sc, signature = :s, processed_at = now(), "
        "  derive_fault = :fault, evaluated_rev = COALESCE(CAST(:ev AS varchar), evaluated_rev), "
        "  finalized_at = CASE WHEN :f THEN COALESCE(finalized_at, now()) ELSE NULL END "
        "WHERE " + _WHERE_GAME),
        dict(b, m=match["id"] if match else None, sc=match["sc"] if match else None,
             s=sig if fault is None else None, fault=fault, ev=evaluated,
             f=bool(final) and fault is None))
    state = "final" if final and fault is None else ("evaluated" if evaluated else
                                                     ("fault" if fault else "waiting"))
    return state, fired, errors, evaluated is not None


async def games_pass(session_factory, state=None, limit: int = None) -> dict:
    """The card games waiting for work, each in its own transaction."""
    rs = state.ruleset if state is not None else None
    stats = {"evaluated": 0, "fired": 0, "rule_errors": 0}
    async with session_factory() as db:
        if await setting(db, "card_evidence_worker") != "1":
            return {"off": 1}
        cands = (await db.execute(_CANDIDATES, {
            "lim": limit or CARD_LIMITS["games_per_pass"], "rev": rs.rev if rs else None})).all()
    for key, lo, hi, _rx in cands:
        async with session_factory() as db:
            try:
                st, fired, errors, done = await evaluate_card_game(db, key, lo, hi, rs)
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
    """Retention: the hand lists out of the payload after the list retention;
    records never attached after the expiry; derived rows after the derived
    retention. Findings follow seat_evidence's own purge; flagged_matches
    rows are never removed."""
    lim = CARD_LIMITS
    out = {}
    async with session_factory() as db:
        if await setting(db, "card_evidence_purge") != "1":
            return {"off": 1}
        out["lists"] = (await db.execute(text(
            "UPDATE card_evidence SET payload = payload - 'cards' - 'held0' - 'ph' - 'hd' - 'ap', "
            "  lists_purged_at = now() "
            "WHERE lists_purged_at IS NULL "
            "  AND received_at < now() - make_interval(days => CAST(:d AS int))"),
            {"d": lim["list_retention_days"]})).rowcount
        out["unattached"] = (await db.execute(text(
            "DELETE FROM card_evidence e "
            "WHERE e.received_at < now() - make_interval(days => CAST(:d AS int)) "
            "  AND NOT EXISTS (SELECT 1 FROM card_games g "
            "    WHERE g.stable_game_key = e.stable_game_key "
            "      AND g.pair_lo = LEAST(e.seat_player_id, e.other_player_id) "
            "      AND g.pair_hi = GREATEST(e.seat_player_id, e.other_player_id) "
            "      AND g.match_id IS NOT NULL)"), {"d": lim["expiry_days"]})).rowcount
        out["games"] = (await db.execute(text(
            "DELETE FROM card_games g WHERE g.match_id IS NULL "
            "  AND NOT EXISTS (SELECT 1 FROM card_evidence e "
            "    WHERE e.stable_game_key = g.stable_game_key "
            "      AND LEAST(e.seat_player_id, e.other_player_id) = g.pair_lo "
            "      AND GREATEST(e.seat_player_id, e.other_player_id) = g.pair_hi)"))).rowcount
        d = {"d": lim["derived_retention_days"]}
        out["derived"] = sum((await db.execute(text(q), d)).rowcount for q in (
            "DELETE FROM card_contrib WHERE utc_day < (now() - make_interval(days => CAST(:d AS int)))::date",
            "DELETE FROM card_player_daily WHERE day < (now() - make_interval(days => CAST(:d AS int)))::date",
            "DELETE FROM card_hand_outside WHERE computed_at < now() - make_interval(days => CAST(:d AS int))",
            "DELETE FROM card_phase_outside WHERE computed_at < now() - make_interval(days => CAST(:d AS int))"))
        await db.commit()
    return out


# -- the admin read ------------------------------------------------------------------

def _jsonable(view) -> dict:
    """The view's measures as the admin read shows them (rows only)."""
    return {"hands": [row for row, _m in view["hands"]],
            "phases": [row for row, _m in view["phases"]],
            "records": [row for row, _m in view["records"]],
            "pairs": [row for row, _m in view["pairs"]],
            "game": view["game"]}


async def admin_view(db, *, match_id=None, stable_game_key=None, rs=None) -> dict:
    """Both card records of a game, the measures computed now, the stored
    hand and phase rows, contributions and findings (rule id, revision,
    details, the posted flag), and per UTC day how many records named a
    census digest that is not registered. Steam ids only."""
    lim = CARD_LIMITS
    if match_id is not None:
        games = (await db.execute(text(
            "SELECT stable_game_key, pair_lo, pair_hi, match_id, series_sc, finalized_at, "
            "       evaluated_rev, derive_fault FROM card_games WHERE match_id = CAST(:m AS uuid)"),
            {"m": match_id})).mappings().all()
    else:
        games = (await db.execute(text(
            "SELECT stable_game_key, pair_lo, pair_hi, match_id, series_sc, finalized_at, "
            "       evaluated_rev, derive_fault FROM card_games WHERE stable_game_key = :k"),
            {"k": stable_game_key})).mappings().all()
    keys = sorted({g["stable_game_key"] for g in games} | ({stable_game_key} if stable_game_key else set()))
    unreg = (await db.execute(text(
        "SELECT (e.received_at AT TIME ZONE 'UTC')::date d, count(*) FROM card_evidence e "
        " WHERE e.received_at > now() - make_interval(days => CAST(:d AS int)) "
        "   AND e.pool_digest IS NOT NULL "
        "   AND NOT EXISTS (SELECT 1 FROM card_pool_registry p WHERE p.digest = e.pool_digest) "
        " GROUP BY 1 ORDER BY 1"), {"d": lim["unregistered_days"]})).all()
    out = {"review_rules": rs.rev if rs is not None else rr.health_word(), "games": [],
           "unregistered_by_day": [{"day": r[0].isoformat(), "records": int(r[1])} for r in unreg]}
    for key in keys:
        rows = (await db.execute(text(
            "SELECT e.id, e.attach_key, e.seat_player_id, e.other_player_id, ps.steam_id seat_steam, "
            "       po.steam_id other_steam, e.payload, e.pool_digest, e.pool_state, e.deal_profile, "
            "       e.conflict_at, e.conflict_kind, e.received_at, e.lists_purged_at, e.payload_bytes "
            "  FROM card_evidence e JOIN players ps ON ps.id = e.seat_player_id "
            "  JOIN players po ON po.id = e.other_player_id "
            " WHERE e.stable_game_key = :k ORDER BY e.id LIMIT CAST(:n AS int)"),
            {"k": key, "n": lim["admin_rows"]})).mappings().all()
        by_pair = {}
        for r in rows:
            by_pair.setdefault(se._norm_pair(r["seat_player_id"], r["other_player_id"]), []).append(r)
        for (lo, hi), prs in by_pair.items():
            g = next((x for x in games if x["stable_game_key"] == key and x["pair_lo"] == lo
                      and x["pair_hi"] == hi), None)
            match = None
            if g is not None and g["match_id"] is not None:
                match = {"id": g["match_id"], "photon_room_id": (await db.execute(text(
                    "SELECT photon_room_id FROM matches WHERE id = :m"), {"m": g["match_id"]})).scalar()}
            named, _other = se.attached_records(prs, match)
            view_rows = named if match is not None else prs
            records = [r for r in _records(view_rows) if _has_lists(r["rec"])]
            registry = await _registry(db, {r["pool_digest"] for r in prs if r["pool_digest"]})
            view = cm.card_view(records, registry, g["series_sc"] if g else None,
                                rs.params.get(cm.WEIGHTS) if rs is not None else None)
            b = {"k": key, "lo": lo, "hi": hi}
            hand = (await db.execute(text(
                "SELECT recorder_player_id, dealer_player_id, phase, deal, rules_rev, measures "
                "FROM card_hand_outside WHERE " + _WHERE_GAME + " ORDER BY phase, deal"), b)).mappings().all()
            phase = (await db.execute(text(
                "SELECT recorder_player_id, phase, rules_rev, measures FROM card_phase_outside "
                "WHERE " + _WHERE_GAME + " ORDER BY phase"), b)).mappings().all()
            contrib = (await db.execute(text(
                "SELECT recorder_player_id, subject_player_id, source, coverage, deal_profile, rules_rev, "
                "       utc_day, " + ", ".join(_DAILY_COLS) + " FROM card_contrib WHERE " + _WHERE_GAME
                + " ORDER BY rules_rev, subject_player_id, source"), b)).mappings().all()
            findings = (await db.execute(text(
                "SELECT rule_id, rules_rev, details, flag_id FROM seat_evidence_findings "
                "WHERE scope = 'game' AND dedup_key = :d ORDER BY rule_id"),
                {"d": "card|%s|%s|%s" % (key, lo, hi)})).mappings().all()
            out["games"].append({
                "stable_game_key": key,
                "match_id": str(match["id"]) if match else None,
                "series_sc": g["series_sc"] if g else None,
                "final": bool(g and g["finalized_at"]),
                "evaluated_rev": g["evaluated_rev"] if g else None,
                "derive_fault": g["derive_fault"] if g else None,
                "records": [{"seat_steam_id": r["seat_steam"], "other_steam_id": r["other_steam"],
                             "attach_key": r["attach_key"], "received_at": r["received_at"].isoformat(),
                             "pool_digest": r["pool_digest"], "pool_state": r["pool_state"],
                             "pool_registered": bool(r["pool_digest"]) and r["pool_digest"] in registry,
                             "deal_profile": r["deal_profile"], "conflict_kind": r["conflict_kind"],
                             "payload_bytes": r["payload_bytes"],
                             "lists_purged": r["lists_purged_at"] is not None,
                             "names_the_match": (r["id"] in {x["id"] for x in named}) if match else None,
                             "record": se._jsonv(r["payload"])} for r in prs],
                "measures": _jsonable(view),
                "hand_rows": [dict(h, recorder_player_id=str(h["recorder_player_id"]),
                                   dealer_player_id=str(h["dealer_player_id"]) if h["dealer_player_id"] else None,
                                   measures=se._jsonv(h["measures"])) for h in hand],
                "phase_rows": [dict(p, recorder_player_id=str(p["recorder_player_id"]),
                                    measures=se._jsonv(p["measures"])) for p in phase],
                "contributions": [dict(c, recorder_player_id=str(c["recorder_player_id"]),
                                       subject_player_id=str(c["subject_player_id"]),
                                       utc_day=c["utc_day"].isoformat()) for c in contrib],
                "findings": [{"rule_id": f["rule_id"], "rules_rev": f["rules_rev"],
                              "details": se._jsonv(f["details"]),
                              "posted_flag_id": str(f["flag_id"]) if f["flag_id"] else None}
                             for f in findings],
            })
    return out
