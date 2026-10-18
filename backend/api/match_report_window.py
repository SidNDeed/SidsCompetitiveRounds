"""The report acceptance after a return, and the same-four freshness window
(Stage 2 design V3, S5): pure rules plus their DB writes, no route.

The routes that use this are wired by NX4 of the build brief (main.py is
owned by another lane until then): `_team_series_resumable(row, holds, now)`
calls `series_fresh`, and the team and 1v2 report routes journal and settle
through `receive` and `settle_window`, with `_settle_team_report` and
`_settle_ovt_report` passed in as the settle callable.

THE WINDOW (RJS-H6, RJS-M7). `held_overlap(holds, v, now)` sums, for each
hold of the series, the overlap of [held_anchor_at, least(closed_at,
held_until)) -- both DB-clock values -- with [v, now]. An anchor v is fresh
when (now - v) - held_overlap(holds, v, now) < window. Each anchor counts
only hold time after itself, so repeated lapses never bank time and a newer
anchor gains nothing from older holds. `now` is REQUIRED everywhere (no
default, no application clock): every caller reads clock_timestamp() once in
its transaction and passes it. With no holds the predicate is today's.

THE CLASSES (V3 P3 applied). A report of game G in room r is class C when
its reporter has no `entered` hold for (r, G), class R when it has one, and
unclassed (u) when it names no valid G of the room. The report of the class
C fighter with the lowest Steam id among those with a fresh beat at that
receipt settles at once; every other report is journaled behind a 30 s
window, and an expired window settles in class order: C by lowest Steam id,
then R, then unclassed. Exactly one report of a window ever settles: the
window row is locked FIRST and settled_at is written once.
"""

import hashlib
import hmac
from datetime import timedelta

from sqlalchemy import text

from match_hold import BEAT_FRESH_S, database_deadline

WINDOW_S = 30
CLASS_C, CLASS_R, CLASS_U = "c", "r", "u"
_CLASS_RANK = {CLASS_C: 0, CLASS_R: 1, CLASS_U: 2}
FRESH_ANCHORS = ("created_at", "room_issued_at", "last_game_at")


# -- the window ---------------------------------------------------------------

def _get(row, key):
    return row.get(key) if hasattr(row, "get") else row[key]


def held_overlap(holds, v, now) -> timedelta:
    """The hold time inside [v, now]: for each hold the overlap of
    [held_anchor_at, least(closed_at, held_until)) with [v, now]."""
    total = timedelta(0)
    for h in holds:
        start = _get(h, "held_anchor_at")
        end = _get(h, "held_until")
        closed = _get(h, "closed_at")
        if closed is not None and closed < end:
            end = closed
        lo = start if start > v else v
        hi = end if end < now else now
        if hi > lo:
            total += hi - lo
    return total


def anchor_fresh(v, holds, *, now, window: timedelta) -> bool:
    """One anchor of the same-four window: fresh when its age less the hold
    time after it is under the window. `now` is required (the DB clock of
    the caller's transaction)."""
    if v is None:
        return False
    return (now - v) - held_overlap(holds, v, now) < window


def series_fresh(row, holds, *, now, window: timedelta) -> bool:
    """Today's freshness test of `_team_series_resumable` (any of
    created_at, room_issued_at, last_game_at under the window) with every
    anchor measured by `anchor_fresh`."""
    return any(anchor_fresh(_get(row, col), holds, now=now, window=window)
               for col in FRESH_ANCHORS)


async def series_holds(db, series_id):
    """Every hold of a series, with the three stamps the window reads."""
    return (await db.execute(text(
        "SELECT held_anchor_at, held_until, closed_at FROM match_seat_holds"
        " WHERE series_id = CAST(:sid AS uuid)"), {"sid": str(series_id)})).mappings().all()


# -- the game-id canonical ------------------------------------------------------

def game_id_canonical(game_id, reporter, room) -> str:
    """The advisory game id of a report, signed separately (RJS-L3): the
    eleven-field team and ten-field 1v2 canonicals are not touched."""
    return f"game-id:{game_id}:{reporter}:{room}"


def verify_game_id(secret, game_id, reporter, room, signature) -> bool:
    """The build HMAC over the game-id canonical with the secret and compare
    helper main uses (an unset secret accepts, as main does)."""
    if not secret:
        return True
    msg = game_id_canonical(game_id, reporter, room)
    expected = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


# -- the classes ------------------------------------------------------------------

def steam_order(steam_id: str):
    """Lowest Steam id first: numeric order for the equal-length digit
    strings Steam ids are."""
    s = str(steam_id)
    return (len(s), s)


def pick(entries):
    """The one report an expired window settles: the first non-empty class
    in the order C, R, unclassed, and inside it the lowest Steam id. None
    when there is no entry."""
    best = None
    for e in entries:
        key = (_CLASS_RANK[e["cls"]], steam_order(e["reporter_steam"]))
        if best is None or key < best[0]:
            best = (key, e)
    return None if best is None else best[1]


async def classify(db, *, room, game_id, reported_game_id, reporter_id) -> str:
    """C, R or unclassed from the server's own rows only: unclassed when the
    report names no G or another G than the window's, or the window's G is
    not a game of this room; R when the reporter has an entered hold for
    (room, G); C otherwise."""
    if reported_game_id is None or str(reported_game_id) != str(game_id):
        return CLASS_U
    valid = (await db.execute(text(
        "SELECT 1 FROM match_games WHERE id = CAST(:g AS uuid)"
        "   AND room_name = CAST(:room AS varchar)"),
        {"g": str(game_id), "room": room})).scalar()
    if not valid:
        return CLASS_U
    entered = (await db.execute(text(
        "SELECT 1 FROM match_seat_holds WHERE room_name = CAST(:room AS varchar)"
        "   AND game_id = CAST(:g AS uuid) AND player_id = CAST(:pid AS uuid)"
        "   AND entered_at IS NOT NULL"),
        {"room": room, "g": str(game_id), "pid": str(reporter_id)})).scalar()
    return CLASS_R if entered else CLASS_C


async def fresh_class_c_steams(db, *, room, game_id, member_ids, now):
    """Steam ids of the series members with a fresh beat in the room at
    `now` and no entered hold for (room, G): the class C fighters present."""
    rows = (await db.execute(text(
        "SELECT p.steam_id FROM match_seat_presence m JOIN players p ON p.id = m.player_id"
        " WHERE m.room_name = CAST(:room AS varchar)"
        "   AND m.player_id = ANY(CAST(:ids AS uuid[]))"
        "   AND m.beat_at > CAST(:now AS timestamptz) - make_interval(secs => CAST(:f AS integer))"
        "   AND NOT EXISTS (SELECT 1 FROM match_seat_holds h"
        "                    WHERE h.room_name = m.room_name AND h.game_id = CAST(:g AS uuid)"
        "                      AND h.player_id = m.player_id AND h.entered_at IS NOT NULL)"),
        {"room": room, "ids": [str(i) for i in member_ids], "now": now, "f": BEAT_FRESH_S,
         "g": str(game_id)})).scalars().all()
    return list(rows)


# -- the window and journal writes ---------------------------------------------------

async def lock_window(db, *, mode, room, game_id, now):
    """Open the window of (room, G) at its first receipt (settle_after =
    now + WINDOW_S) and return it under FOR NO KEY UPDATE: the window row is
    the FIRST lock of every journal and settle transaction."""
    await db.execute(text(
        "INSERT INTO match_report_windows (room_name, game_id, mode, opened_at, settle_after)"
        " VALUES (CAST(:room AS varchar), CAST(:g AS uuid), CAST(:mode AS varchar),"
        "         CAST(:now AS timestamptz),"
        "         CAST(:now AS timestamptz) + make_interval(secs => CAST(:w AS integer)))"
        " ON CONFLICT (room_name, game_id) DO NOTHING"),
        {"room": room, "g": str(game_id), "mode": mode, "now": now, "w": WINDOW_S})
    return (await db.execute(text(
        "SELECT room_name, game_id, mode, opened_at, settle_after, settled_at,"
        "       settled_reporter_id, settled_cls FROM match_report_windows"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        " FOR NO KEY UPDATE"), {"room": room, "g": str(game_id)})).mappings().first()


async def journal(db, *, mode, room, game_id, reporter_id, reporter_steam, cls, payload,
                  now, held=False) -> bool:
    """Keep one HMAC-verified report (`payload`, JSON text) of (room, G,
    reporter); a repeat keeps the first. `held` journals a game-over that
    arrived during a hold. True when this call wrote the row."""
    res = await db.execute(text(
        "INSERT INTO match_report_journal (room_name, game_id, reporter_id, mode,"
        "        reporter_steam, cls, state, payload, received_at)"
        " VALUES (CAST(:room AS varchar), CAST(:g AS uuid), CAST(:pid AS uuid),"
        "         CAST(:mode AS varchar), CAST(:steam AS varchar), CAST(:cls AS varchar),"
        "         CAST(:state AS varchar), CAST(:payload AS jsonb), CAST(:now AS timestamptz))"
        " ON CONFLICT (room_name, game_id, reporter_id) DO NOTHING"),
        {"room": room, "g": str(game_id), "pid": str(reporter_id), "mode": mode,
         "steam": reporter_steam, "cls": cls, "state": "held" if held else "journaled",
         "payload": payload, "now": now})
    return (res.rowcount or 0) > 0


async def _journaled(db, room, game_id):
    return (await db.execute(text(
        "SELECT reporter_id, reporter_steam, cls, payload, received_at"
        "  FROM match_report_journal"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND state = 'journaled' ORDER BY received_at, reporter_steam"),
        {"room": room, "g": str(game_id)})).mappings().all()


async def _mark_settled(db, room, game_id, chosen, now):
    await db.execute(text(
        "UPDATE match_report_windows SET settled_at = CAST(:now AS timestamptz),"
        "       settled_reporter_id = CAST(:pid AS uuid), settled_cls = CAST(:cls AS varchar)"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND settled_at IS NULL"),
        {"now": now, "pid": str(chosen["reporter_id"]), "cls": chosen["cls"],
         "room": room, "g": str(game_id)})
    await db.execute(text(
        "UPDATE match_report_journal"
        "   SET state = CASE WHEN reporter_id = CAST(:pid AS uuid) THEN 'settled' ELSE 'kept' END,"
        "       decided_at = CAST(:now AS timestamptz)"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND state = 'journaled'"),
        {"now": now, "pid": str(chosen["reporter_id"]), "room": room, "g": str(game_id)})


async def settle_window(db, *, mode, room, game_id, now, settle):
    """Run one settle operation inside the shared match database budget."""
    async with database_deadline(db):
        return await _settle_window(
            db, mode=mode, room=room, game_id=game_id, now=now, settle=settle)


async def _settle_window(db, *, mode, room, game_id, now, settle):
    """Settle an EXPIRED window of (room, G): lock the window row first;
    nothing when it is already settled or not yet expired; otherwise call
    `settle(db, entry)` once with the report `pick` chooses and write
    settled_at once. Returns the settled entry or None. The caller commits."""
    window = await lock_window(db, mode=mode, room=room, game_id=game_id, now=now)
    if window["settled_at"] is not None or window["settle_after"] > now:
        return None
    chosen = pick(await _journaled(db, room, game_id))
    if chosen is None:
        return None
    await settle(db, chosen)
    await _mark_settled(db, room, game_id, chosen, now)
    return chosen


async def receive(db, *, mode, room, game_id, reported_game_id, reporter_id, reporter_steam,
                  payload, member_ids, now, settle, held=False) -> dict:
    """Run one receipt inside the shared match database budget."""
    async with database_deadline(db):
        return await _receive(
            db, mode=mode, room=room, game_id=game_id,
            reported_game_id=reported_game_id, reporter_id=reporter_id,
            reporter_steam=reporter_steam, payload=payload, member_ids=member_ids,
            now=now, settle=settle, held=held)


async def _receive(db, *, mode, room, game_id, reported_game_id, reporter_id, reporter_steam,
                   payload, member_ids, now, settle, held=False) -> dict:
    """The settle driver for one HMAC-verified report of a flagged room.

    The window row of (room, G) is locked first. A settled window answers
    `duplicate` (the route answers today's duplicate). Otherwise the report
    is classed from server rows and journaled; a game-over during a hold is
    journaled `held` and settles nothing. The report of the class C fighter
    with the lowest Steam id among the class C fighters with a fresh beat
    settles at once through `settle(db, entry)`; any other report answers
    `journaled` (202), and an expired window settles by `pick`. The caller
    commits."""
    window = await lock_window(db, mode=mode, room=room, game_id=game_id, now=now)
    if window["settled_at"] is not None:
        return {"status": "duplicate"}
    cls = await classify(db, room=room, game_id=game_id, reported_game_id=reported_game_id,
                         reporter_id=reporter_id)
    await journal(db, mode=mode, room=room, game_id=game_id, reporter_id=reporter_id,
                  reporter_steam=reporter_steam, cls=cls, payload=payload, now=now, held=held)
    if held:
        return {"status": "journaled", "cls": cls, "state": "held"}
    if cls == CLASS_C:
        fresh = await fresh_class_c_steams(db, room=room, game_id=game_id,
                                           member_ids=member_ids, now=now)
        if fresh and min(fresh, key=steam_order) == reporter_steam:
            entry = {"reporter_id": reporter_id, "reporter_steam": reporter_steam,
                     "cls": cls, "payload": payload}
            await settle(db, entry)
            await _mark_settled(db, room, game_id, entry, now)
            return {"status": "settled", "cls": cls}
    done = await settle_window(db, mode=mode, room=room, game_id=game_id, now=now,
                               settle=settle)
    if done is not None:
        return {"status": "settled", "cls": done["cls"],
                "settled_reporter": done["reporter_steam"]}
    return {"status": "journaled", "cls": cls}


async def release_held(db, *, mode, room, game_id, now) -> int:
    """Run one held-report release inside the shared match database budget."""
    async with database_deadline(db):
        return await _release_held(db, mode=mode, room=room, game_id=game_id, now=now)


async def _release_held(db, *, mode, room, game_id, now) -> int:
    """At entry: the `held` reports of G become journaled and the window of
    G opens (or re-opens its 30 s from now when it was opened during the
    hold and is unsettled). Returns the rows released."""
    await lock_window(db, mode=mode, room=room, game_id=game_id, now=now)
    await db.execute(text(
        "UPDATE match_report_windows"
        "   SET settle_after = CAST(:now AS timestamptz) + make_interval(secs => CAST(:w AS integer))"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND settled_at IS NULL"),
        {"now": now, "w": WINDOW_S, "room": room, "g": str(game_id)})
    res = await db.execute(text(
        "UPDATE match_report_journal SET state = 'journaled'"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND state = 'held'"), {"room": room, "g": str(game_id)})
    return res.rowcount or 0


async def supersede_held(db, *, mode, room, game_id, now) -> int:
    """Run one held-report supersession inside the shared database budget."""
    async with database_deadline(db):
        return await _supersede_held(db, mode=mode, room=room, game_id=game_id, now=now)


async def _supersede_held(db, *, mode, room, game_id, now) -> int:
    """At a lapse (x): the `held` reports of G are superseded, kept for
    review and never settled. Returns the rows superseded."""
    await lock_window(db, mode=mode, room=room, game_id=game_id, now=now)
    res = await db.execute(text(
        "UPDATE match_report_journal SET state = 'superseded',"
        "       decided_at = CAST(:now AS timestamptz)"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND state = 'held'"), {"now": now, "room": room, "g": str(game_id)})
    return res.rowcount or 0
