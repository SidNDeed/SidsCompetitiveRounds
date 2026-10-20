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
identity guards precede the window lock; settled_at is written once.
"""

import hashlib
import hmac
import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import text
from fastapi import HTTPException

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
        "   AND m.beat_at <= CAST(:now AS timestamptz)"
        "   AND NOT EXISTS (SELECT 1 FROM match_seat_holds h"
        "                    WHERE h.room_name = m.room_name AND h.game_id = CAST(:g AS uuid)"
        "                      AND h.player_id = m.player_id AND h.entered_at IS NOT NULL)"),
        {"room": room, "ids": [str(i) for i in member_ids], "now": now, "f": BEAT_FRESH_S,
         "g": str(game_id)})).scalars().all()
    return list(rows)


# -- the window and journal writes ---------------------------------------------------

def _payload_identity_keys(mode, payload):
    """The typed report's copied identity fields; the signed payload stays intact."""
    stored = json.loads(payload) if isinstance(payload, str) else (payload or {})
    fields = ("t1a", "t1b", "t2a", "t2b") if mode == "team" else ("solo", "duo_a", "duo_b")
    out = {stored[k].get("steam_id") for k in fields if isinstance(stored.get(k), dict)}
    out.add(stored.get("reported_by_steam_id"))
    return {str(value) for value in out if value is not None}


async def _guard_window_identities(db, *, room, game_id, mode=None, payload=None,
                                   reporter_id=None, reporter_steam=None, member_ids=()):
    """Take the complete identity set before window, series, hold or lease locks.

    Discovery is unlocked and supplies guard keys only. Every identity-bearing
    sink revalidates the identities it will store after acquisition. Existing
    scrubbed payloads may remain for disposition without restoring their keys.
    """
    from match_hold import _guard_player_ids, _members, _series_read
    game = (await db.execute(text(
        "SELECT mode, series_id FROM match_games WHERE id = CAST(:g AS uuid)"
        " AND room_name = CAST(:room AS varchar)"),
        {"g": str(game_id), "room": room})).mappings().first()
    mode = mode or (game["mode"] if game is not None else None)
    series = await _series_read(db, mode, game["series_id"]) if game is not None else None
    roster = set(_members(mode, series)) if series is not None else None
    rows = (await db.execute(text(
        "SELECT reporter_id, reporter_steam, payload FROM match_report_journal"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"),
        {"room": room, "g": str(game_id)})).mappings().all()
    ids = set(member_ids) | (roster or set())
    keys = _payload_identity_keys(mode, payload)
    if reporter_id is not None:
        ids.add(reporter_id)
    if reporter_steam is not None:
        keys.add(reporter_steam)
    for row in rows:
        ids.add(row["reporter_id"])
        keys.add(row["reporter_steam"])
        keys.update(_payload_identity_keys(mode, row["payload"]))
    owners, live = await _guard_player_ids(db, ids, keys)
    return owners, live, roster


async def lock_window(db, *, mode, room, game_id, now, held=False):
    """Lock (room, G) before the series and hold rows. A held receipt opens
    an unarmed window; an ordinary receipt arms its acceptance deadline."""
    await db.execute(text(
        "INSERT INTO match_report_windows (room_name, game_id, mode, opened_at, settle_after)"
        " VALUES (CAST(:room AS varchar), CAST(:g AS uuid), CAST(:mode AS varchar),"
        "         CAST(:now AS timestamptz),"
        "         CASE WHEN CAST(:held AS boolean) THEN CAST('infinity' AS timestamptz)"
        "              ELSE CAST(:now AS timestamptz)"
        "                   + make_interval(secs => CAST(:w AS integer)) END)"
        " ON CONFLICT (room_name, game_id) DO NOTHING"),
        {"room": room, "g": str(game_id), "mode": mode, "now": now, "w": WINDOW_S,
         "held": held})
    return (await db.execute(text(
        "SELECT room_name, game_id, mode, opened_at, settle_after, settled_at,"
        "       superseded_at, settled_reporter_id, settled_cls FROM match_report_windows"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        " FOR NO KEY UPDATE"), {"room": room, "g": str(game_id)})).mappings().first()



async def _causal_hold(db, *, mode, room, game_id, hold_id=None):
    """Read the causal hold after window, series, then hold locking.

    Any prior non-entry closure remains terminal for this physical game; a
    later hold cannot revive it. An explicit id always selects that hold.

    Open already locks the series before it changes any hold; end and entry
    lock the hold and commit before their report finishing transaction. Thus
    no path holding a series or hold waits for a report window.
    """
    from match_hold import _HOLD_COLS, _series_lock
    sid = (await db.execute(text(
        "SELECT series_id FROM match_games WHERE id = CAST(:g AS uuid)"
        " AND mode = CAST(:mode AS varchar) AND room_name = CAST(:room AS varchar)"),
        {"g": str(game_id), "mode": mode, "room": room})).scalar()
    if sid is None:
        return None
    await _series_lock(db, mode, sid)
    return (await db.execute(text(
        f"SELECT {_HOLD_COLS} FROM match_seat_holds"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND (CAST(:hid AS uuid) IS NULL OR id = CAST(:hid AS uuid))"
        " ORDER BY (closed_reason IS NOT NULL AND closed_reason <> 'entered') DESC,"
        "          held_at DESC, id DESC LIMIT 1 FOR NO KEY UPDATE"),
        {"room": room, "g": str(game_id),
         "hid": str(hold_id) if hold_id is not None else None})).mappings().first()


def _hold_closure(hold, now):
    from match_hold import _effective_closure
    return _effective_closure(hold, now) if hold is not None else None


async def _causal_entered(db, hold, closure):
    """Only this hold's effective closure can authorize release."""
    return closure is not None and closure[1] == "entered"


async def _arm_window(db, window, *, room, game_id, at):
    """Arm on entry (or ordinary first receipt), never on a held receipt."""
    return (await db.execute(text(
        "UPDATE match_report_windows SET settle_after ="
        " CASE WHEN settle_after = CAST('infinity' AS timestamptz)"
        "      THEN CAST(:at AS timestamptz) + make_interval(secs => CAST(:w AS integer))"
        "      ELSE GREATEST(settle_after, CAST(:at AS timestamptz)"
        "           + make_interval(secs => CAST(:w AS integer))) END"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND settled_at IS NULL AND superseded_at IS NULL RETURNING *"),
        {"room": room, "g": str(game_id), "at": at, "w": WINDOW_S})).mappings().first() or window


async def _hold_window(db, window, *, room, game_id):
    await db.execute(text(
        "UPDATE match_report_windows SET settle_after = CAST('infinity' AS timestamptz)"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND settled_at IS NULL AND superseded_at IS NULL"),
        {"room": room, "g": str(game_id)})


async def finish_hold(db, *, mode, room, game_id, hold_id, now, settle):
    """Finish an exact causal hold under window, series, hold order.

    A later live hold defers this work; any later non-entry closure ends the
    game. The no-journal case still creates the terminal window or arms the
    ordinary deadline from the entry stamp.
    """
    async with database_deadline(db):
        await _guard_window_identities(db, mode=mode, room=room, game_id=game_id)
        window = await lock_window(db, mode=mode, room=room, game_id=game_id,
                                   now=now, held=True)
        if _window_terminal(window):
            return 0, False
        latest = await _causal_hold(db, mode=mode, room=room, game_id=game_id)
        latest_closure = _hold_closure(latest, now)
        if latest is not None and latest_closure is None:
            return 0, False
        hold = await _causal_hold(db, mode=mode, room=room, game_id=game_id,
                                  hold_id=hold_id)
        closure = _hold_closure(hold, now)
        if hold is None or closure is None:
            return 0, False
        if latest_closure is not None and latest_closure[1] != "entered":
            hold, closure = latest, latest_closure
        entered = await _causal_entered(db, hold, closure)
        if entered:
            n = await release_held(db, mode=mode, room=room, game_id=game_id,
                                   now=now, settle=settle, hold_id=hold["id"],
                                   entered_at=max(closure[0], latest_closure[0])
                                   if latest_closure is not None else closure[0])
        else:
            n = await supersede_held(db, mode=mode, room=room, game_id=game_id, now=now)
        return n, entered


def _window_terminal(window) -> bool:
    """A settled or superseded window accepts no later report action."""
    return window["settled_at"] is not None or window["superseded_at"] is not None


async def journal(db, *, mode, room, game_id, reporter_id, reporter_steam, cls, payload,
                  now, held=False):
    """Keep one HMAC-verified report (`payload`, JSON text) of (room, G,
    reporter); a repeat keeps the first. `held` journals a game-over that
    arrived during a hold. Return the canonical stored row, whether this call
    inserted it or lost an insertion conflict to the first receipt."""
    owners, live, roster = await _guard_window_identities(
        db, mode=mode, room=room, game_id=game_id, payload=payload,
        reporter_id=reporter_id, reporter_steam=reporter_steam)
    keys = _payload_identity_keys(mode, payload) | {reporter_steam}
    if (str(live.get(reporter_steam)) != str(reporter_id)
            or any(key not in live for key in keys)
            or (roster is not None and any(live[key] not in roster for key in keys))):
        raise HTTPException(404, "One or more players not registered")
    inserted = (await db.execute(text(
        "INSERT INTO match_report_journal (room_name, game_id, reporter_id, mode,"
        "        reporter_steam, cls, state, payload, received_at)"
        " VALUES (CAST(:room AS varchar), CAST(:g AS uuid), CAST(:pid AS uuid),"
        "         CAST(:mode AS varchar), CAST(:steam AS varchar), CAST(:cls AS varchar),"
        "         CAST(:state AS varchar), CAST(:payload AS jsonb), CAST(:now AS timestamptz))"
        " ON CONFLICT (room_name, game_id, reporter_id) DO NOTHING"
        " RETURNING reporter_id, reporter_steam, cls, state, payload, received_at"),
        {"room": room, "g": str(game_id), "pid": str(reporter_id), "mode": mode,
         "steam": reporter_steam, "cls": cls, "state": "held" if held else "journaled",
         "payload": payload, "now": now})).mappings().first()
    if inserted is not None:
        return inserted
    return (await db.execute(text(
        "SELECT reporter_id, reporter_steam, cls, state, payload, received_at"
        "  FROM match_report_journal"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND reporter_id = CAST(:pid AS uuid)"),
        {"room": room, "g": str(game_id), "pid": str(reporter_id)})).mappings().first()


async def _journaled(db, room, game_id):
    return (await db.execute(text(
        "SELECT reporter_id, reporter_steam, cls, payload, received_at"
        "  FROM match_report_journal"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND state = 'journaled' ORDER BY received_at, reporter_steam"),
        {"room": room, "g": str(game_id)})).mappings().all()


class PermanentReportRefusal(HTTPException):
    """A settle validation that the immutable physical report cannot repair.

    Authentication, rate limits, conflicts, timeouts and unknown failures do
    not use this class; their journal entry remains retryable.
    """

    def __init__(self, refusal):
        super().__init__(status_code=refusal.status_code, detail=refusal.detail,
                         headers=refusal.headers)


class ReportAlreadyRecorded(Exception):
    """A callback found a physical game on record; it made no settlement."""

    def __init__(self, physical_game, *, receipt=False):
        self.physical_game = physical_game
        self.receipt = receipt
        super().__init__("physical game already recorded")


async def _settle_and_mark(db, room, game_id, chosen, now, settle):
    """Only a new settlement may terminalize this window.

    The callback's successful return means it recorded the chosen physical
    game. Production explicitly reports duplicate success through the named
    exception; that receipt is kept without changing the window's outcome.
    """
    try:
        await settle(db, chosen)
    except ReportAlreadyRecorded as exc:
        if exc.receipt:
            raise
        await db.execute(text(
            "UPDATE match_report_journal SET state = 'kept', decided_at = :now"
            " WHERE room_name = :room AND game_id = CAST(:g AS uuid)"
            " AND reporter_id = CAST(:pid AS uuid) AND state = 'journaled'"),
            {"now": now, "room": room, "g": str(game_id),
             "pid": str(chosen["reporter_id"])})
        return False
    except Exception as exc:
        # Preserve the original type and cause chain for every bound stage.
        # A JSON round trip snapshots the exact immutable evidence attempted.
        payload = chosen["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        exc.attempted_report = {
            "reporter_id": str(chosen["reporter_id"]),
            "reporter_steam": chosen["reporter_steam"], "cls": chosen["cls"],
            "received_at": chosen["received_at"],
            "payload": json.dumps(payload, sort_keys=True),
        }
        raise
    await _mark_settled(db, room, game_id, chosen, now)
    return True


async def _mark_settled(db, room, game_id, chosen, now):
    owners, _, _ = await _guard_window_identities(
        db, room=room, game_id=game_id, reporter_id=chosen["reporter_id"])
    if str(chosen["reporter_id"]) not in {str(pid) for pid in owners}:
        raise HTTPException(404, "One or more players not registered")
    await db.execute(text(
        "UPDATE match_report_windows SET settled_at = CAST(:now AS timestamptz),"
        "       settled_reporter_id = CAST(:pid AS uuid), settled_cls = CAST(:cls AS varchar)"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND settled_at IS NULL AND superseded_at IS NULL"),
        {"now": now, "pid": str(chosen["reporter_id"]), "cls": chosen["cls"],
         "room": room, "g": str(game_id)})
    await db.execute(text(
        "UPDATE match_report_journal"
        "   SET state = CASE WHEN reporter_id = CAST(:pid AS uuid) THEN 'settled' ELSE 'kept' END,"
        "       decided_at = CAST(:now AS timestamptz)"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND state = 'journaled'"),
        {"now": now, "pid": str(chosen["reporter_id"]), "room": room, "g": str(game_id)})


async def _settle_locked(db, window, *, room, game_id, now, settle):
    """Settle one already-locked expired window from only its stored rows."""
    if _window_terminal(window) or window["settle_after"] > now:
        return None
    chosen = pick(await _journaled(db, room, game_id))
    if chosen is None:
        return None
    if not await _settle_and_mark(db, room, game_id, chosen, now, settle):
        return None
    return chosen


async def settle_window(db, *, mode, room, game_id, now, settle):
    """Run one settle operation inside the shared match database budget."""
    async with database_deadline(db):
        return await _settle_window(
            db, mode=mode, room=room, game_id=game_id, now=now, settle=settle)


async def _settle_window(db, *, mode, room, game_id, now, settle):
    """Settle an EXPIRED window of (room, G): take identity guards, then lock the window row;
    nothing when it is already settled or not yet expired; otherwise call
    `settle(db, entry)` once with the report `pick` chooses and write
    settled_at once. Returns the settled entry or None. The caller commits."""
    await _guard_window_identities(db, mode=mode, room=room, game_id=game_id)
    window = await lock_window(db, mode=mode, room=room, game_id=game_id, now=now)
    if _window_terminal(window):
        return None
    hold = await _causal_hold(db, mode=mode, room=room, game_id=game_id)
    closure = _hold_closure(hold, now)
    if hold is not None and closure is None:
        await _hold_window(db, window, room=room, game_id=game_id)
        return None
    if closure is not None:
        if closure[1] != "entered":
            await _supersede_held(db, mode=mode, room=room, game_id=game_id, now=now)
            return None
        window = await _arm_window(db, window, room=room, game_id=game_id, at=closure[0])
    return await _settle_locked(
        db, window, room=room, game_id=game_id, now=now, settle=settle)


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

    Identity guards precede the window row lock of (room, G). A settled window answers
    `duplicate` (the route answers today's duplicate). Otherwise the report
    is classed from server rows and journaled; a game-over during a hold is
    journaled `held` and settles nothing. The report of the class C fighter
    with the lowest Steam id among the class C fighters with a fresh beat
    settles at once through `settle(db, entry)`; any other report answers
    `journaled` (202), and an expired window settles by `pick`. The caller
    commits."""
    await _guard_window_identities(db, mode=mode, room=room, game_id=game_id,
                                   payload=payload, reporter_id=reporter_id,
                                   reporter_steam=reporter_steam, member_ids=member_ids)
    window = await lock_window(db, mode=mode, room=room, game_id=game_id,
                               now=now, held=True)
    if _window_terminal(window):
        return {"status": "duplicate"}
    hold = await _causal_hold(db, mode=mode, room=room, game_id=game_id)
    closure = _hold_closure(hold, now)
    if closure is not None and closure[1] != "entered":
        await _supersede_held(db, mode=mode, room=room, game_id=game_id, now=now)
        return {"status": "duplicate"}
    held = held or (hold is not None and closure is None)
    if held:
        await _hold_window(db, window, room=room, game_id=game_id)
        if hold is not None:
            stored = json.loads(payload) if isinstance(payload, str) else dict(payload)
            stored["_causal_hold_id"] = str(hold["id"])
            payload = json.dumps(stored)
    elif closure is not None:
        window = await _arm_window(db, window, room=room, game_id=game_id, at=closure[0])
    elif window["settle_after"].year == 9999:
        window = await _arm_window(db, window, room=room, game_id=game_id, at=now)
    if not held and window["settle_after"] <= now:
        await _settle_locked(
            db, window, room=room, game_id=game_id, now=now, settle=settle)
        return {"status": "duplicate"}
    cls = await classify(db, room=room, game_id=game_id, reported_game_id=reported_game_id,
                         reporter_id=reporter_id)
    entry = await journal(
        db, mode=mode, room=room, game_id=game_id, reporter_id=reporter_id,
        reporter_steam=reporter_steam, cls=cls, payload=payload, now=now, held=held)
    cls = entry["cls"]
    if held or entry["state"] == "held":
        return {"status": "journaled", "cls": cls, "state": "held"}
    if cls == CLASS_C:
        fresh = await fresh_class_c_steams(db, room=room, game_id=game_id,
                                           member_ids=member_ids, now=now)
        if fresh and min(fresh, key=steam_order) == entry["reporter_steam"]:
            if not await _settle_and_mark(db, room, game_id, entry, now, settle):
                return {"status": "duplicate"}
            return {"status": "settled", "cls": cls}
    done = await _settle_locked(
        db, window, room=room, game_id=game_id, now=now, settle=settle)
    if done is not None:
        return {"status": "settled", "cls": done["cls"],
                "settled_reporter": done["reporter_steam"]}
    return {"status": "journaled", "cls": cls}


async def release_held(db, *, mode, room, game_id, now, settle,
                       hold_id=None, entered_at=None) -> int:
    """Run one held-report release inside the shared match database budget."""
    async with database_deadline(db):
        return await _release_held(
            db, mode=mode, room=room, game_id=game_id, now=now, settle=settle,
            hold_id=hold_id, entered_at=entered_at)


async def _release_held(db, *, mode, room, game_id, now, settle,
                        hold_id=None, entered_at=None) -> int:
    """Release entered causal holds together so class priority stays global.

    The caller proved this hold entered and that no later live or nonentry
    hold blocks release. Earlier entered holds become eligible together."""
    await _guard_window_identities(db, mode=mode, room=room, game_id=game_id)
    window = await lock_window(db, mode=mode, room=room, game_id=game_id, now=now)
    params = {"now": now, "w": WINDOW_S, "room": room, "g": str(game_id),
              "hid": str(hold_id) if hold_id is not None else None}
    terminal = _window_terminal(window)
    if terminal and window["settled_at"] is None:
        return 0
    res = await db.execute(text(
        "UPDATE match_report_journal SET state = 'journaled'"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND state = 'held'"
        "   AND (CAST(:hid AS text) IS NULL OR payload ->> '_causal_hold_id' = CAST(:hid AS text)"
        "        OR EXISTS (SELECT 1 FROM match_seat_holds cause"
        "                   WHERE CAST(cause.id AS text) = match_report_journal.payload ->> '_causal_hold_id'"
        "                     AND cause.room_name = match_report_journal.room_name"
        "                     AND cause.game_id = match_report_journal.game_id"
        "                     AND cause.closed_reason = 'entered'))"),
        params)
    released = res.rowcount or 0
    if terminal:
        # The result is already final. Deletion may have cleared its reporter;
        # only dispose of released rows, preserving that NULL attribution.
        await db.execute(text(
            "UPDATE match_report_journal SET state = CASE"
            " WHEN reporter_id = CAST(:pid AS uuid) THEN 'settled' ELSE 'kept' END,"
            " decided_at = CAST(:now AS timestamptz)"
            " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
            " AND state = 'journaled'"),
            {**params, "pid": window["settled_reporter_id"]})
        return released
    window = await _arm_window(db, window, room=room, game_id=game_id,
                               at=entered_at if entered_at is not None else now)
    chosen = pick(await _journaled(db, room, game_id))
    if chosen is not None and chosen["cls"] == CLASS_C:
        await _settle_and_mark(db, room, game_id, chosen, now, settle)
    return released


async def supersede_held(db, *, mode, room, game_id, now) -> int:
    """Run one held-report supersession inside the shared database budget."""
    async with database_deadline(db):
        return await _supersede_held(db, mode=mode, room=room, game_id=game_id, now=now)


async def _supersede_held(db, *, mode, room, game_id, now) -> int:
    """At a lapse (x): the `held` reports of G are superseded, kept for
    review and never settled. Returns the rows superseded."""
    await _guard_window_identities(db, mode=mode, room=room, game_id=game_id)
    window = await lock_window(db, mode=mode, room=room, game_id=game_id, now=now)
    if _window_terminal(window):
        return 0
    await db.execute(text(
        "UPDATE match_report_windows SET superseded_at = CAST(:now AS timestamptz)"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND settled_at IS NULL AND superseded_at IS NULL"),
        {"now": now, "room": room, "g": str(game_id)})
    res = await db.execute(text(
        "UPDATE match_report_journal SET state = 'superseded',"
        "       decided_at = CAST(:now AS timestamptz)"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        "   AND state IN ('held', 'journaled')"), {"now": now, "room": room, "g": str(game_id)})
    return res.rowcount or 0
