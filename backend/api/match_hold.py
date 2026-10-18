"""2v2 and 1v2 mid-game readmission, SERVER HALF (Stage 2 design V3).

An APIRouter module in the form of auto_logs.py: main.py includes it (NX1 of
the build brief; until then only the tests mount it on an app of their own),
and every helper of main.py is reached by a late import inside the function,
because main will import this module once it mounts the router; nothing here
imports main at module top.

WHAT THIS MODULE OWNS
  S1  POST /api/v1/match/game/start   the server-minted game id G, chained
                                      by the previous G under the series lock
      _hold_latch()                   the hold flag of one room issue; called
                                      at every issue site by NX1, by nothing
                                      in this module
  S2  POST /api/v1/match/hold/beat    the presence beat (present_at, seen)
      POST /api/v1/match/hold/open    the hold of one dropped seat, anchored
                                      on its last present_at, with its
                                      match_hold_open_attempts row
      GET  /api/v1/match/hold/{id}/state, GET /api/v1/match/hold/by-room
                                      the server row every client verifies
      POST /api/v1/match/hold/{id}/end   closed_at and the reason, once
      hold_sweep()                    the write-once janitor sweep; called
                                      from queue_cleanup_loop by NX2
  S3  GET  /api/v1/match/hold/mine    discovery, one `offered` row committed
                                      before the answer
      POST /api/v1/match/hold/{id}/claim   the token T (only its SHA-256
                                      verifier stored), the lease re-taken
      POST /api/v1/match/hold/{id}/bind    the corroborated new actor X
      POST /api/v1/match/hold/{id}/entered the entry, closed_at = entered
  S6  match_hold_attempts             one row per offered, claim, bind and
                                      entered attempt, in its transaction

ONE DB CLOCK. Every writer and reader reads clock_timestamp() once per
transaction (`_ctx_now`), AFTER the transaction's first row lock, and binds
that value; no statement here reads NOW() (which would answer the start of a
transaction that may have waited on a lock) and nothing reads the
application clock.

LOCKS. The series row is locked FOR NO KEY UPDATE (#202): it serializes this
module's writers on one series, and unlike FOR UPDATE it does not conflict
with the FOR KEY SHARE that a foreign-key insert referencing the row takes.
"""

import hashlib
import hmac
import json
import math
import secrets
import uuid
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db

router = APIRouter(prefix="/api/v1/match", tags=["Match Hold"])

DB_REQUEST_TIMEOUT_S = 8.0
DB_LOCK_TIMEOUT_MS = 5000
DB_STATEMENT_TIMEOUT_MS = 7000
DB_ROLLBACK_TIMEOUT_S = 1.0
_DB_DEADLINE_INFO = "match_database_deadline"


def _database_sqlstate(exc):
    """Find an asyncpg/PostgreSQL SQLSTATE through SQLAlchemy's wrappers."""
    pending, seen = [exc], set()
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        for name in ("sqlstate", "pgcode"):
            value = getattr(current, name, None)
            if value:
                return value
        pending.extend(getattr(current, name, None)
                       for name in ("orig", "__cause__", "__context__"))
    return None


async def _bounded_rollback(db, asyncio):
    """Give rollback a shielded bound without hiding the triggering error."""
    def consume(done):
        try:
            done.exception()
        except BaseException:
            pass

    task = asyncio.create_task(db.rollback())
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=DB_ROLLBACK_TIMEOUT_S)
    except BaseException:
        if not task.done():
            task.cancel()
            task.add_done_callback(consume)
        else:
            consume(task)


async def _install_database_timeouts(db):
    """Force checkout, then arm both transaction-local PostgreSQL bounds."""
    await db.execute(text(
        "SELECT set_config('lock_timeout', CAST(:lock_ms AS text), true),"
        "       set_config('statement_timeout', CAST(:statement_ms AS text), true)"),
        {"lock_ms": f"{DB_LOCK_TIMEOUT_MS}ms",
         "statement_ms": f"{DB_STATEMENT_TIMEOUT_MS}ms"})


class database_deadline:
    """One absolute database budget shared by nested match operations."""

    def __init__(self, db):
        self.db = db
        self.state = None
        self.outer = False
        self.timer = None
        self.asyncio = None

    def _clear(self):
        self.state["depth"] -= 1
        if self.state["depth"] == 0:
            if self.db.info.get(_DB_DEADLINE_INFO) is self.state:
                self.db.info.pop(_DB_DEADLINE_INFO, None)

    async def _raise_enter_error(self, exc):
        expired = self.timer.expired()
        try:
            suppressed = await self.timer.__aexit__(type(exc), exc, exc.__traceback__)
            if suppressed:
                exc = None
        except BaseException as converted:
            exc = converted
        self._clear()
        if expired or _database_sqlstate(exc) in ("55P03", "57014"):
            await _bounded_rollback(self.db, self.asyncio)
            raise HTTPException(status_code=503, detail="database_deadline") from exc
        if isinstance(exc, self.asyncio.CancelledError):
            await _bounded_rollback(self.db, self.asyncio)
        if exc is not None:
            raise exc

    async def __aenter__(self):
        from main import asyncio

        self.asyncio = asyncio
        self.state = self.db.info.get(_DB_DEADLINE_INFO)
        if self.state is not None:
            self.state["depth"] += 1
            return self
        self.outer = True
        self.state = {
            "deadline": asyncio.get_running_loop().time() + DB_REQUEST_TIMEOUT_S,
            "depth": 1,
            "setup": False,
        }
        self.db.info[_DB_DEADLINE_INFO] = self.state
        self.timer = asyncio.timeout_at(self.state["deadline"])
        try:
            await self.timer.__aenter__()
        except BaseException:
            self._clear()
            raise
        try:
            await _install_database_timeouts(self.db)
            self.state["setup"] = True
        except BaseException as exc:
            await self._raise_enter_error(exc)
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        if not self.outer:
            self._clear()
            return False
        converted = exc
        try:
            suppressed = await self.timer.__aexit__(exc_type, exc, traceback)
            if suppressed:
                converted = None
        except BaseException as raised:
            converted = raised
        expired = self.timer.expired()
        self._clear()
        if expired or _database_sqlstate(converted) in ("55P03", "57014"):
            await _bounded_rollback(self.db, self.asyncio)
            raise HTTPException(status_code=503, detail="database_deadline") from converted
        if isinstance(converted, self.asyncio.CancelledError):
            await _bounded_rollback(self.db, self.asyncio)
            return False
        if converted is not exc and converted is not None:
            raise converted
        return False


async def _bounded_match_db(db: AsyncSession = Depends(get_db)):
    async with database_deadline(db):
        yield db

# The capability token a team or 1v2 client sends in its queue and lobby join
# bodies only when every Stage 2 patch attached at boot (S1 step 1).
HOLD_CAPS_TOKEN = "rjs1"

MODES = ("team", "ovt")
_SERIES_TABLE = {"team": "team_series", "ovt": "ovt_series"}
_QUEUE_TABLE = {"team": "team_queue", "ovt": "ovt_queue"}
# (series column, team) for every seat of a series row: team 0 is the first
# team of 2v2 and the solo of 1v2, team 1 the second team and the duo.
_MEMBER_COLS = {
    "team": (("t1a_id", 0), ("t1b_id", 0), ("t2a_id", 1), ("t2b_id", 1)),
    "ovt": (("solo_id", 0), ("duo_a_id", 1), ("duo_b_id", 1)),
}
_ACTIVE = ("active", "dc_paused")


def _mode_or_400(mode: str) -> str:
    if mode not in MODES:
        raise HTTPException(400, "mode must be team or ovt")
    return mode


async def _ctx_now(db: AsyncSession):
    """The one DB clock read of this transaction."""
    return (await db.execute(text("SELECT clock_timestamp()"))).scalar()


async def _player_id(db: AsyncSession, steam_id: str):
    return (await db.execute(text(
        "SELECT id FROM players WHERE steam_id = CAST(:s AS varchar)"),
        {"s": steam_id})).scalar()


def _series_select(mode: str) -> str:
    cols = ", ".join(c for c, _ in _MEMBER_COLS[mode])
    wins = ("t1_series_wins AS w0, t2_series_wins AS w1" if mode == "team"
            else "solo_series_wins AS w0, duo_series_wins AS w1")
    return (f"SELECT id, status, hold_v2, hold_room, region, photon_room_id, {wins}, {cols}"
            f"  FROM {_SERIES_TABLE[mode]} WHERE id = CAST(:sid AS uuid)")


async def _series_lock(db: AsyncSession, mode: str, series_id):
    """The series row under FOR NO KEY UPDATE (#202), or None."""
    return (await db.execute(text(_series_select(mode) + " FOR NO KEY UPDATE"),
                             {"sid": str(series_id)})).mappings().first()


def _members(mode: str, row) -> dict:
    """{player_id: team} of a series row."""
    return {row[c]: team for c, team in _MEMBER_COLS[mode] if row[c] is not None}


def _member_seats(mode: str, row) -> dict:
    """{player_id: (slot, team)} derived from the locked series roster."""
    return {row[c]: (slot, team) for slot, (c, team) in enumerate(_MEMBER_COLS[mode])
            if row[c] is not None}


# ---------------------------------------------------------------------------
# S1. The hold flag latch (S1 step 2)
# ---------------------------------------------------------------------------

def _latch_sql(mode: str) -> str:
    members = ", ".join("s." + c for c, _ in _MEMBER_COLS[mode])
    n = len(_MEMBER_COLS[mode])
    return (
        f"UPDATE {_SERIES_TABLE[mode]} s"
        f"   SET hold_room = CAST(:room AS varchar),"
        f"       hold_v2 = (SELECT count(*) = {n} FROM {_QUEUE_TABLE[mode]} q"
        f"                   WHERE q.player_id IN ({members})"
        f"                     AND CAST(:tok AS text) = ANY(string_to_array(q.caps, ',')))"
        f" WHERE s.id = CAST(:sid AS uuid)"
        f"   AND s.hold_room IS DISTINCT FROM CAST(:room AS varchar)")


async def _hold_latch(db: AsyncSession, mode: str, series_id, room: str) -> bool:
    """Latch the hold flag of one room issue, inside the caller's transaction
    (the statement that issues the room; NX1 calls it at every issue site).

    hold_room becomes `room`; hold_v2 becomes TRUE only when EVERY member of
    the series has a queue row of this mode carrying HOLD_CAPS_TOKEN (a
    missing row or token gives FALSE, the direction of today). A flag already
    written for this room never changes: the UPDATE matches only a row whose
    hold_room differs, so a second call for the same room is inert and a
    relock to a new room re-judges. Returns the flag the row holds for `room`
    afterwards (FALSE for an empty room, which latches nothing)."""
    mode = _mode_or_400(mode)
    room = (room or "").strip()
    if not room:
        return False
    params = {"sid": str(series_id), "room": room, "tok": HOLD_CAPS_TOKEN}
    await db.execute(text(_latch_sql(mode)), params)
    flag = (await db.execute(text(
        f"SELECT hold_v2 FROM {_SERIES_TABLE[mode]}"
        f" WHERE id = CAST(:sid AS uuid) AND hold_room = CAST(:room AS varchar)"),
        params)).scalar()
    return bool(flag)


# ---------------------------------------------------------------------------
# S1. The game id (S1 step 3)
# ---------------------------------------------------------------------------

class GameStartReq(BaseModel):
    steam_id: str = Field(..., min_length=1, max_length=20)
    mode: str = Field(..., max_length=8)
    series_id: uuid.UUID
    room: str = Field(..., min_length=1, max_length=64)
    prev_game: Optional[uuid.UUID] = None


def _refused(reason: str) -> dict:
    return {"status": "refused", "reason": reason}


async def _require_verified_session(request: Request, steam_id: str, db) -> None:
    """Require the compatibility session check to establish the claimed id."""
    from main import _check_steam_session, _session_was_verified   # late import

    await _check_steam_session(request, steam_id, db)
    if not _session_was_verified(request):
        raise HTTPException(status_code=401, detail="session_required")


@router.post("/game/start")
async def match_game_start(req: GameStartReq, request: Request,
                           db: AsyncSession = Depends(_bounded_match_db)):
    """Mint or return the game id G of the game starting in a flagged room.

    Requires the poster's Steam session and series membership, a series row
    flagged for exactly this room and still active. Under the series lock:
    the row whose prev_game equals the posted previous G (or, with none
    posted, the first game of the room) is returned when it exists, so a
    promoted master re-posting the same previous G receives the same G and a
    handover never forks a game; otherwise one row is inserted with seq one
    more than the latest of (series, room). A previous G that is not a game
    of this series and room is refused."""
    mode = _mode_or_400(req.mode)
    room = req.room.strip()
    await _require_verified_session(request, req.steam_id, db)
    pid = await _player_id(db, req.steam_id)
    row = await _series_lock(db, mode, req.series_id)
    now = await _ctx_now(db)                 # after the lock wait, never before it
    if row is None:
        await db.rollback()
        return _refused("no_series")
    if pid is None or pid not in _members(mode, row):
        await db.rollback()
        return _refused("not_member")
    if not row["hold_v2"] or (row["hold_room"] or "") != room:
        await db.rollback()
        return _refused("not_flagged")
    if row["status"] not in _ACTIVE:
        await db.rollback()
        return _refused("series_closed")
    key = {"sid": str(req.series_id), "room": room,
           "prev": str(req.prev_game) if req.prev_game else None}
    if req.prev_game is None:
        found = (await db.execute(text(
            "SELECT id, seq FROM match_games"
            " WHERE series_id = CAST(:sid AS uuid) AND room_name = CAST(:room AS varchar)"
            "   AND prev_game IS NULL"), key)).mappings().first()
    else:
        found = (await db.execute(text(
            "SELECT id, seq FROM match_games"
            " WHERE series_id = CAST(:sid AS uuid) AND room_name = CAST(:room AS varchar)"
            "   AND prev_game = CAST(:prev AS uuid)"), key)).mappings().first()
        if found is None:
            known = (await db.execute(text(
                "SELECT 1 FROM match_games WHERE id = CAST(:prev AS uuid)"
                "   AND series_id = CAST(:sid AS uuid) AND room_name = CAST(:room AS varchar)"),
                key)).scalar()
            if not known:
                await db.rollback()
                return _refused("unknown_prev")
    if found is not None:
        await db.commit()
        return {"status": "ok", "game_id": str(found["id"]), "seq": found["seq"],
                "minted": False}
    made = (await db.execute(text(
        "INSERT INTO match_games (mode, series_id, room_name, seq, prev_game, started_at)"
        " SELECT CAST(:mode AS varchar), CAST(:sid AS uuid), CAST(:room AS varchar),"
        "        COALESCE(max(seq), 0) + 1, CAST(:prev AS uuid), CAST(:now AS timestamptz)"
        "   FROM match_games"
        "  WHERE series_id = CAST(:sid AS uuid) AND room_name = CAST(:room AS varchar)"
        " RETURNING id, seq"), {**key, "mode": mode, "now": now})).mappings().first()
    await db.commit()
    return {"status": "ok", "game_id": str(made["id"]), "seq": made["seq"], "minted": True}


# ---------------------------------------------------------------------------
# S2. The hold at the boundary: beat, open, state, by-room, end, sweep
# ---------------------------------------------------------------------------

HOLD_S = 120            # the hold length from the anchor (V3 Q2)
MIN_WINDOW_S = 15       # under this left at the open: window_spent (FFA V3:155)
BEAT_FRESH_S = 25       # a beat this recent is fresh (bind corroboration, end)
ENTRY_BOUND_S = 60      # a bound row with no entry within this closes entry_failed

# The local end reasons of writer step 6 a member may post.
END_REASONS = frozenset({
    "refused", "no_answer", "second_departure", "ceiling", "survivor_leave",
    "token_refused", "snapshot_failed", "registration_refused",
    "activation_timeout", "entry_refused", "bind_timeout",
})

_HOLD_COLS = ("id, mode, room_name, series_id, game_id, player_id, n, slot, team, "
              "opener_player_id, held_anchor_at, held_at, held_until, seq, offered_at, "
              "claimed_at, verifier, bound_at, bound_actor, bound_region, entered_at, "
              "closed_at, closed_reason, crossed_at_hold")


def _slot_ok(mode: str, slot: int, team: int) -> bool:
    """The slot and team of one seat agree: team = slot / 2 in 2v2 (slots 0-3);
    slot 0 is the solo (team 0) and slots 1-2 the duo (team 1) in 1v2."""
    if mode == "team":
        return 0 <= slot <= 3 and team == slot // 2
    return 0 <= slot <= 2 and team == (0 if slot == 0 else 1)


def _effective_closure(row, now):
    """(closed_at, reason) of a hold, or None while it is live. A row the
    sweep has not reached yet reads closed at its own deadline: held_until
    (lapsed), or bound_at + ENTRY_BOUND_S with no entry (entry_failed),
    whichever came first. The sweep stamps exactly these values, so every
    reader sees one closure whenever it reads (write-once, never moved)."""
    if row["closed_at"] is not None:
        return row["closed_at"], row["closed_reason"]
    lapse = row["held_until"]
    if row["bound_at"] is not None and row["entered_at"] is None:
        ef = row["bound_at"] + timedelta(seconds=ENTRY_BOUND_S)
        if ef < lapse and ef <= now:
            return ef, "entry_failed"
    if lapse <= now:
        return lapse, "lapsed"
    return None


def _hold_live(row, now) -> bool:
    return _effective_closure(row, now) is None


def _state_word(row, now) -> str:
    closure = _effective_closure(row, now)
    if closure is not None:
        return "entered" if closure[1] == "entered" else "closed"
    if row["bound_at"] is not None:
        return "bound"
    if row["claimed_at"] is not None:
        return "claimed"
    return "opened"


def _deadline_s(row, now) -> int:
    if not _hold_live(row, now):
        return 0
    left = (row["held_until"] - now).total_seconds()
    return max(0, int(math.ceil(left)))


def _state_payload(row, now) -> dict:
    closure = _effective_closure(row, now)
    state = _state_word(row, now)
    return {
        "hold_id": str(row["id"]), "game_id": str(row["game_id"]),
        "mode": row["mode"], "room_name": row["room_name"],
        "slot": row["slot"], "team": row["team"], "n": row["n"],
        "state": state, "seq": row["seq"],
        "deadline_s": _deadline_s(row, now), "hold_s": _deadline_s(row, now),
        "bound_actor": row["bound_actor"],
        "verifier": row["verifier"] if state in ("claimed", "bound") else None,
        "closed_at": closure[0].isoformat() if closure else None,
        "closed_reason": closure[1] if closure else None,
    }


async def _hold_row(db: AsyncSession, hold_id, lock: bool = False):
    sql = f"SELECT {_HOLD_COLS} FROM match_seat_holds WHERE id = CAST(:hid AS uuid)"
    if lock:
        sql += " FOR NO KEY UPDATE"
    return (await db.execute(text(sql), {"hid": str(hold_id)})).mappings().first()


async def _series_read(db: AsyncSession, mode: str, series_id):
    return (await db.execute(text(_series_select(mode)),
                             {"sid": str(series_id)})).mappings().first()


def hold_open_canonical(mode, room, game_id, held_steam, slot, team, opener_steam) -> str:
    """The hold-open canonical (RJS-L3): new and separate from every
    canonical of today; the team-DC, team report and 1v2 report canonicals
    are untouched."""
    return f"hold-open:{mode}:{room}:{game_id}:{held_steam}:{slot}:{team}:{opener_steam}"


def _verify_hold_open_hmac(req) -> bool:
    """The build HMAC over the hold-open canonical, verified with the secret
    and the compare helper main uses for every build HMAC (MATCH_HMAC_SECRET,
    hmac.compare_digest); an unset secret accepts, exactly as main does."""
    import main                           # late import: main mounts this module at NX1
    secret = main.MATCH_HMAC_SECRET
    if not secret:
        return True
    msg = hold_open_canonical(req.mode, req.room, req.game_id, req.held_steam_id,
                              req.slot, req.team, req.opener_steam_id)
    expected = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, req.hmac or "")


async def _fresh_beat(db: AsyncSession, room: str, pid, now) -> bool:
    return bool((await db.execute(text(
        "SELECT 1 FROM match_seat_presence"
        " WHERE room_name = CAST(:room AS varchar) AND player_id = CAST(:pid AS uuid)"
        "   AND beat_at > CAST(:now AS timestamptz) - make_interval(secs => CAST(:f AS integer))"),
        {"room": room, "pid": str(pid), "now": now, "f": BEAT_FRESH_S})).scalar())


# -- the beat (S2 "The presence beat") ----------------------------------------

class SeenActor(BaseModel):
    actor: int = Field(..., ge=1, le=100000)
    u_id: str = Field(..., min_length=1, max_length=20)


class BeatReq(BaseModel):
    steam_id: str = Field(..., min_length=1, max_length=20)
    mode: str = Field(..., max_length=8)
    series_id: uuid.UUID
    room: str = Field(..., min_length=1, max_length=64)
    actor: Optional[int] = Field(None, ge=1, le=100000)
    seen: List[SeenActor] = Field(default_factory=list, max_length=8)
    boundary_digest: Optional[str] = Field(None, max_length=64)


@router.post("/hold/beat")
async def match_hold_beat(req: BeatReq, request: Request,
                          db: AsyncSession = Depends(_bounded_match_db)):
    """Record one presence beat. Requires the poster's session and its
    membership of a series flagged for this room. present_at moves only when
    the poster names itself with its own actor (an actor given, and no seen
    entry naming the poster with another actor); beat_at, seen and the
    boundary digest are stored on every accepted beat. A beat decides no
    result."""
    mode = _mode_or_400(req.mode)
    room = req.room.strip()
    await _require_verified_session(request, req.steam_id, db)
    pid = await _player_id(db, req.steam_id)
    row = await _series_read(db, mode, req.series_id)
    if row is None or pid is None or pid not in _members(mode, row):
        await db.rollback()
        return _refused("not_member")
    if not row["hold_v2"] or (row["hold_room"] or "") != room:
        await db.rollback()
        return _refused("not_flagged")
    self_named = req.actor is not None and all(
        s.actor == req.actor for s in req.seen if s.u_id == req.steam_id)
    seen = json.dumps([{"actor": s.actor, "u_id": s.u_id} for s in req.seen])
    now = await _ctx_now(db)
    await db.execute(text(
        "INSERT INTO match_seat_presence (room_name, player_id, mode, series_id, actor,"
        "                                 present_at, beat_at, seen, boundary_digest)"
        " VALUES (CAST(:room AS varchar), CAST(:pid AS uuid), CAST(:mode AS varchar),"
        "         CAST(:sid AS uuid), CAST(:actor AS integer),"
        "         CASE WHEN CAST(:self AS boolean) THEN CAST(:now AS timestamptz) END,"
        "         CAST(:now AS timestamptz), CAST(:seen AS jsonb), CAST(:dig AS varchar))"
        " ON CONFLICT (room_name, player_id) DO UPDATE"
        "    SET mode = EXCLUDED.mode, series_id = EXCLUDED.series_id,"
        "        actor = COALESCE(EXCLUDED.actor, match_seat_presence.actor),"
        "        present_at = COALESCE(EXCLUDED.present_at, match_seat_presence.present_at),"
        "        beat_at = EXCLUDED.beat_at, seen = EXCLUDED.seen,"
        "        boundary_digest = COALESCE(EXCLUDED.boundary_digest,"
        "                                   match_seat_presence.boundary_digest)"),
        {"room": room, "pid": str(pid), "mode": mode, "sid": str(req.series_id),
         "actor": req.actor, "self": self_named, "now": now, "seen": seen,
         "dig": req.boundary_digest})
    await db.commit()
    return {"status": "ok"}


# -- the open (S2 server half) -------------------------------------------------

class HoldOpenReq(BaseModel):
    request_id: str = Field(..., min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    opener_steam_id: str = Field(..., min_length=1, max_length=20)
    mode: str = Field(..., max_length=8)
    room: str = Field(..., min_length=1, max_length=64)
    game_id: uuid.UUID
    held_steam_id: str = Field(..., min_length=1, max_length=20)
    slot: int = Field(..., ge=0, le=3)
    team: int = Field(..., ge=0, le=1)
    t1_points: Optional[int] = Field(None, ge=0, le=99)
    t2_points: Optional[int] = Field(None, ge=0, le=99)
    hmac: str = Field("", max_length=128)


_CLOSE_DUE_ROOM_SQL = """
WITH due AS (
    SELECT id,
           CASE WHEN bound_at IS NOT NULL AND entered_at IS NULL
                     AND bound_at + make_interval(secs => CAST(:eb AS integer)) < held_until
                THEN bound_at + make_interval(secs => CAST(:eb AS integer))
                ELSE held_until END AS deadline_at,
           CASE WHEN bound_at IS NOT NULL AND entered_at IS NULL
                     AND bound_at + make_interval(secs => CAST(:eb AS integer)) < held_until
                THEN 'entry_failed' ELSE 'lapsed' END AS deadline_reason
      FROM match_seat_holds
     WHERE room_name = CAST(:room AS varchar)
       AND closed_at IS NULL
       AND CASE WHEN bound_at IS NOT NULL AND entered_at IS NULL
                     AND bound_at + make_interval(secs => CAST(:eb AS integer)) < held_until
                THEN bound_at + make_interval(secs => CAST(:eb AS integer))
                ELSE held_until END <= CAST(:now AS timestamptz)
     FOR UPDATE
)
UPDATE match_seat_holds AS h
   SET closed_at = due.deadline_at, closed_reason = due.deadline_reason
  FROM due
 WHERE h.id = due.id AND h.closed_at IS NULL
"""


async def _close_due_room_hold(db, room, now):
    """Close the room's physically-open row only when its stored deadline is due."""
    await db.execute(text(_CLOSE_DUE_ROOM_SQL),
                     {"room": room, "now": now, "eb": ENTRY_BOUND_S})


async def _open_decide(db, req, mode, room, opener, held):
    """(reason, gate-allowed hold id, series row, game row) under the series lock.

    The room's physically open row is locked before the player gate.  Its id
    lets the same player reach the authoritative room decision; the exact-game
    row is reread only after the gate and M3's due-row closure.
    """
    game = (await db.execute(text(
        "SELECT id, mode, series_id, room_name FROM match_games WHERE id = CAST(:g AS uuid)"),
        {"g": str(req.game_id)})).mappings().first()
    if game is None or game["mode"] != mode or game["room_name"] != room:
        return "not_current_game", None, None, game
    row = await _series_lock(db, mode, game["series_id"])
    if row is None:
        return "series_closed", None, None, game
    if not row["hold_v2"] or (row["hold_room"] or "") != room:
        return "not_flagged", None, row, game
    if row["status"] not in _ACTIVE:
        return "series_closed", None, row, game
    latest = (await db.execute(text(
        "SELECT id FROM match_games WHERE series_id = CAST(:sid AS uuid)"
        "   AND room_name = CAST(:room AS varchar) ORDER BY seq DESC LIMIT 1"),
        {"sid": str(game["series_id"]), "room": room})).scalar()
    if latest != game["id"]:
        return "not_current_game", None, row, game
    members = _members(mode, row)
    member_seats = _member_seats(mode, row)
    if (opener is None or held is None or opener == held or opener not in members
            or held not in members
            or member_seats.get(held) != (req.slot, req.team)
            or not _slot_ok(mode, req.slot, req.team)):
        return "not_member", None, row, game
    open_room = (await db.execute(text(
        "SELECT id, game_id, player_id FROM match_seat_holds"
        " WHERE room_name = CAST(:room AS varchar) AND closed_at IS NULL"
        " FOR NO KEY UPDATE"), {"room": room})).mappings().first()
    allowed_hold_id = None
    if open_room is not None and open_room["player_id"] == held:
        allowed_hold_id = open_room["id"]
    return None, allowed_hold_id, row, game


async def _write_open_attempt(db, req, room, held, opener, now, outcome, reason, hold_id):
    """Insert one final ledger row for a request that took no action (a bad
    signature, or a gate loser's fresh refusal transaction). True when this
    call inserted it; False when the request id is already recorded, in which
    case the insert waited for the recording transaction and changed nothing."""
    got = (await db.execute(text(
        "INSERT INTO match_hold_open_attempts (request_id, room_name, game_id,"
        "        held_player_id, opener_player_id, at, outcome, reason, hold_id)"
        " VALUES (CAST(:rid AS varchar), CAST(:room AS varchar), CAST(:g AS uuid),"
        "         CAST(:held AS uuid), CAST(:opener AS uuid), CAST(:now AS timestamptz),"
        "         CAST(:outcome AS varchar), CAST(:reason AS varchar), CAST(:hid AS uuid))"
        " ON CONFLICT (request_id) DO NOTHING RETURNING request_id"),
        {"rid": req.request_id, "room": room, "g": str(req.game_id),
         "held": str(held) if held else None, "opener": str(opener) if opener else None,
         "now": now, "outcome": outcome, "reason": reason,
         "hid": str(hold_id) if hold_id else None})).scalar()
    return got is not None


async def _claim_open_ledger(db, req, room, held, opener) -> bool:
    """The serialization point of one request id (NX0a): insert its ledger
    row BEFORE any action, as the first row lock this transaction takes. The
    primary key on request_id makes a concurrent first use of the same id
    wait on this insert until this transaction ends; it then finds the row
    and acts on nothing. The row is provisional (refused, pending, no clock)
    only inside this transaction: every commit path rewrites it through
    _finish_open_attempt first, so no other transaction reads it so.
    True when this transaction owns the request id."""
    got = (await db.execute(text(
        "INSERT INTO match_hold_open_attempts (request_id, room_name, game_id,"
        "        held_player_id, opener_player_id, at, outcome, reason, hold_id)"
        " VALUES (CAST(:rid AS varchar), CAST(:room AS varchar), CAST(:g AS uuid),"
        "         CAST(:held AS uuid), CAST(:opener AS uuid),"
        "         CAST('-infinity' AS timestamptz), 'refused', 'pending', NULL)"
        " ON CONFLICT (request_id) DO NOTHING RETURNING request_id"),
        {"rid": req.request_id, "room": room, "g": str(req.game_id),
         "held": str(held) if held else None,
         "opener": str(opener) if opener else None})).scalar()
    return got is not None


async def _finish_open_attempt(db, req, now, outcome, reason, hold_id):
    """Write the owned ledger row's outcome, with this transaction's clock.
    Only the provisional row is rewritten; a final record is never changed."""
    await db.execute(text(
        "UPDATE match_hold_open_attempts SET at = CAST(:now AS timestamptz),"
        "       outcome = CAST(:outcome AS varchar), reason = CAST(:reason AS varchar),"
        "       hold_id = CAST(:hid AS uuid)"
        " WHERE request_id = CAST(:rid AS varchar)"
        "   AND outcome = 'refused' AND reason = 'pending'"),
        {"rid": req.request_id, "now": now, "outcome": outcome, "reason": reason,
         "hid": str(hold_id) if hold_id else None})


async def _open_attempt_row(db, request_id: str):
    return (await db.execute(text(
        "SELECT room_name, game_id, held_player_id, opener_player_id, outcome, reason, hold_id"
        "  FROM match_hold_open_attempts WHERE request_id = CAST(:rid AS varchar)"),
        {"rid": request_id})).mappings().first()


def _open_attempt_matches(row, req, room, held, opener) -> bool:
    return (row["room_name"], row["game_id"], row["held_player_id"], row["opener_player_id"]) == \
        (room, req.game_id, held, opener)


async def _open_replay(db, req, room, held, opener) -> dict:
    """Answer a request id another transaction already recorded, from that
    record alone: a different tuple refuses request_mismatch, a recorded
    refusal answers its reason, a recorded open answers its hold. Acts on
    nothing and writes nothing."""
    known = await _open_attempt_row(db, req.request_id)
    if known is None:
        await db.rollback()
        raise HTTPException(503, "hold_open_replay_unavailable")
    if not _open_attempt_matches(known, req, room, held, opener):
        await db.rollback()
        return _refused("request_mismatch")
    if known["outcome"] == "refused":
        await db.rollback()
        return _refused(known["reason"])
    hold = await _hold_row(db, known["hold_id"])
    now = await _ctx_now(db)
    await db.rollback()
    if hold is None:
        raise HTTPException(503, "hold_open_replay_unavailable")
    out = _state_payload(hold, now)
    out.update({"status": "opened", "repeat": known["outcome"] == "repeat"})
    return out


@router.post("/hold/open")
async def match_hold_open(req: HoldOpenReq, request: Request,
                          db: AsyncSession = Depends(_bounded_match_db)):
    """Open the hold of one dropped seat (S2 server half).

    Requires the opener's Steam session and the build HMAC over the hold-open
    canonical (403 otherwise, after one refused attempt is recorded). In ONE
    transaction under the series lock: G must be the latest game of a series flagged for this room
    and still active, both players series members on the seat posted. The
    anchor is the held seat's last present_at in this room, which no late or
    withheld open moves: held_until = anchor + HOLD_S, held_at = the DB clock
    of this transaction. A team hold stores _team_game_crossed_two from the
    locked series row as crossed_at_hold. The held player's lease is released.
    Every request, refused or not, writes its match_hold_open_attempts row in
    the same transaction; a refusal is never a hold. A repeat for the same
    (room, G, held player) answers the existing open row. The ledger row is
    inserted before any action and is the serialization point of its request
    id: of two uses of one id, exactly one acts, and the other answers the
    tuple the first recorded."""
    from main import _lease_admission_gate, _lease_release, _team_game_crossed_two

    mode = _mode_or_400(req.mode)
    room = req.room.strip()
    await _require_verified_session(request, req.opener_steam_id, db)
    opener = await _player_id(db, req.opener_steam_id)
    held = await _player_id(db, req.held_steam_id)
    if not _verify_hold_open_hmac(req):
        now = await _ctx_now(db)
        if await _write_open_attempt(
                db, req, room, None, opener, now, "refused", "bad_signature", None):
            await db.commit()
        else:
            await db.rollback()
        raise HTTPException(403, "Invalid hold-open signature")
    if not await _claim_open_ledger(db, req, room, held, opener):
        return await _open_replay(db, req, room, held, opener)
    reason, allowed_hold_id, row, game = await _open_decide(
        db, req, mode, room, opener, held)
    if (reason is None and mode == "team"
            and (req.t1_points is None or req.t2_points is None)):
        reason = "missing_points"
    existing = None
    if reason is None:
        admitted, now = await _lease_admission_gate(
                db, [held], mode, game["series_id"],
                allowed_hold_ids=((allowed_hold_id,) if allowed_hold_id is not None else ()),
                hold_entry_bound_seconds=ENTRY_BOUND_S)
        if not admitted:
            # The player gate may have waited behind a winning formation.
            # Discard every action write before recording the refusal in a
            # fresh transaction with that transaction's own single clock.
            await db.rollback()
            await _install_database_timeouts(db)
            now = await _ctx_now(db)
            if not await _write_open_attempt(
                    db, req, room, held, opener, now, "refused", "other_mode", None):
                # The rollback released this request id and a concurrent use
                # of it recorded first: answer that record, act on nothing.
                return await _open_replay(db, req, room, held, opener)
            await db.commit()
            return _refused("other_mode")
        await _close_due_room_hold(db, room, now)
        existing = (await db.execute(text(
            f"SELECT {_HOLD_COLS} FROM match_seat_holds"
            " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
            "   AND player_id = CAST(:pid AS uuid)"),
            {"room": room, "g": str(req.game_id), "pid": str(held)}
        )).mappings().first()
        if existing is not None and existing["closed_at"] is not None:
            reason = "duplicate_game"
        elif existing is None:
            busy = (await db.execute(text(
                "SELECT 1 FROM match_seat_holds WHERE room_name = CAST(:room AS varchar)"
                "   AND closed_at IS NULL"), {"room": room})).scalar()
            if busy:
                reason = "room_busy"
    else:
        now = await _ctx_now(db)
    made = None
    if reason is None and existing is not None and not _hold_live(existing, now):
        reason = "duplicate_game"            # past its own deadline, not yet swept
    if reason is None and existing is None:
        pres = (await db.execute(text(
            "SELECT present_at,"
            "       present_at + make_interval(secs => CAST(:hs AS integer))"
            "         - CAST(:now AS timestamptz) AS left_iv"
            "  FROM match_seat_presence"
            " WHERE room_name = CAST(:room AS varchar) AND player_id = CAST(:pid AS uuid)"),
            {"hs": HOLD_S, "now": now, "room": room, "pid": str(held)})).mappings().first()
        if pres is None or pres["present_at"] is None:
            reason = "no_presence"
        elif pres["left_iv"] < timedelta(seconds=MIN_WINDOW_S):
            reason = "window_spent"
        else:
            crossed = False
            if mode == "team":
                crossed = bool(await _team_game_crossed_two(db, game["series_id"], {
                    "t1_series_wins": row["w0"], "t2_series_wins": row["w1"],
                    "photon_room_id": row["photon_room_id"]}))
            await _lease_release(db, held)
            made = (await db.execute(text(
                "INSERT INTO match_seat_holds (mode, room_name, series_id, game_id, player_id,"
                "        n, slot, team, opener_player_id, held_anchor_at, held_at, held_until,"
                "        seq, crossed_at_hold, drop_t1_points, drop_t2_points)"
                " SELECT CAST(:mode AS varchar), CAST(:room AS varchar), CAST(:sid AS uuid),"
                "        CAST(:g AS uuid), CAST(:pid AS uuid),"
                "        (SELECT COALESCE(max(n), 0) + 1 FROM match_seat_holds"
                "          WHERE room_name = CAST(:room AS varchar)"
                "            AND player_id = CAST(:pid AS uuid)),"
                "        CAST(:slot AS smallint), CAST(:team AS smallint), CAST(:opener AS uuid),"
                "        CAST(:anchor AS timestamptz), CAST(:now AS timestamptz),"
                "        CAST(:anchor AS timestamptz) + make_interval(secs => CAST(:hs AS integer)),"
                "        0, CAST(:crossed AS boolean), CAST(:p1 AS smallint), CAST(:p2 AS smallint)"
                f" RETURNING {_HOLD_COLS}"),
                {"mode": mode, "room": room, "sid": str(game["series_id"]),
                 "g": str(req.game_id), "pid": str(held), "slot": req.slot, "team": req.team,
                 "opener": str(opener), "anchor": pres["present_at"], "now": now,
                 "hs": HOLD_S, "crossed": crossed, "p1": req.t1_points,
                 "p2": req.t2_points})).mappings().first()
    if reason is not None:
        await _finish_open_attempt(db, req, now, "refused", reason, None)
        await db.commit()
        return _refused(reason)
    hold = made if made is not None else existing
    await _finish_open_attempt(db, req, now,
                               "opened" if made is not None else "repeat", None, hold["id"])
    await db.commit()
    if made is not None:
        print(f"[HOLD] held room={room} slot={hold['slot']} n={hold['n']}")
    out = _state_payload(hold, now)
    out.update({"status": "opened", "repeat": made is None})
    return out


# -- the state, by-room and end reads and writes ------------------------------

async def _member_of_hold(db, hold, pid) -> bool:
    row = await _series_read(db, hold["mode"], hold["series_id"])
    return row is not None and pid is not None and pid in _members(hold["mode"], row)


@router.get("/hold/{hold_id}/state")
async def match_hold_state(hold_id: uuid.UUID, steam_id: str, request: Request,
                           db: AsyncSession = Depends(_bounded_match_db)):
    """The server row of one hold for a series member: state, seq,
    deadline_s, bound_actor, closed_at and closed_reason (the transition
    envelope of S2). A row past its deadline reads closed at that deadline."""
    await _require_verified_session(request, steam_id, db)
    pid = await _player_id(db, steam_id)
    hold = await _hold_row(db, hold_id)
    if hold is None or not await _member_of_hold(db, hold, pid):
        await db.rollback()
        raise HTTPException(404, "no such hold")
    now = await _ctx_now(db)
    await db.rollback()
    return _state_payload(hold, now)


@router.get("/hold/by-room")
async def match_hold_by_room(room: str, game_id: uuid.UUID, steam_id: str,
                             request: Request, db: AsyncSession = Depends(_bounded_match_db)):
    """The hold of (room, G) for a series member, newest first; 404 when the
    room holds none for G (the promoted master then reposts the open)."""
    await _require_verified_session(request, steam_id, db)
    pid = await _player_id(db, steam_id)
    hold = (await db.execute(text(
        f"SELECT {_HOLD_COLS} FROM match_seat_holds"
        " WHERE room_name = CAST(:room AS varchar) AND game_id = CAST(:g AS uuid)"
        " ORDER BY held_at DESC LIMIT 1"),
        {"room": room.strip(), "g": str(game_id)})).mappings().first()
    if hold is None or not await _member_of_hold(db, hold, pid):
        await db.rollback()
        raise HTTPException(404, "no hold for this room and game")
    now = await _ctx_now(db)
    await db.rollback()
    return _state_payload(hold, now)


class HoldEndReq(BaseModel):
    steam_id: str = Field(..., min_length=1, max_length=20)
    reason: str = Field(..., max_length=32)


@router.post("/hold/{hold_id}/end")
async def match_hold_end(hold_id: uuid.UUID, req: HoldEndReq, request: Request,
                         db: AsyncSession = Depends(_bounded_match_db)):
    """End a hold toward today (writer step 6). Requires a series member's
    session and a fresh beat of that member in the room, and one of the
    END_REASONS. Under the hold row lock closed_at and the reason are stamped
    exactly once; a row already closed (or past its own deadline, which the
    sweep would stamp) answers that closure and stamps nothing new."""
    if req.reason not in END_REASONS:
        raise HTTPException(400, "unknown end reason")
    await _require_verified_session(request, req.steam_id, db)
    pid = await _player_id(db, req.steam_id)
    hold = await _hold_row(db, hold_id, lock=True)
    if hold is None or not await _member_of_hold(db, hold, pid):
        await db.rollback()
        raise HTTPException(404, "no such hold")
    now = await _ctx_now(db)                 # after the hold row lock
    if not await _fresh_beat(db, hold["room_name"], pid, now):
        await db.rollback()
        return _refused("no_fresh_beat")
    closure = _effective_closure(hold, now)
    already = closure is not None
    if closure is None:
        closure = (now, req.reason)
    if hold["closed_at"] is None:            # this end, or a deadline not yet swept
        await db.execute(text(
            "UPDATE match_seat_holds SET closed_at = CAST(:at AS timestamptz),"
            "       closed_reason = CAST(:why AS varchar)"
            " WHERE id = CAST(:hid AS uuid) AND closed_at IS NULL"),
            {"at": closure[0], "why": closure[1], "hid": str(hold_id)})
    await db.commit()
    return {"status": "closed", "closed_at": closure[0].isoformat(),
            "closed_reason": closure[1], "already": already}


# -- the janitor sweep (S2 write-once) ----------------------------------------

_SWEEP_SQL = """
WITH due AS (
    SELECT id,
           CASE WHEN bound_at IS NOT NULL AND entered_at IS NULL
                     AND bound_at + make_interval(secs => CAST(:eb AS integer)) < held_until
                THEN bound_at + make_interval(secs => CAST(:eb AS integer))
                ELSE held_until END AS at,
           CASE WHEN bound_at IS NOT NULL AND entered_at IS NULL
                     AND bound_at + make_interval(secs => CAST(:eb AS integer)) < held_until
                THEN 'entry_failed'
                ELSE 'lapsed' END AS why
      FROM match_seat_holds
     WHERE closed_at IS NULL
       AND (held_until <= CAST(:now AS timestamptz)
            OR (bound_at IS NOT NULL AND entered_at IS NULL
                AND bound_at + make_interval(secs => CAST(:eb AS integer))
                    <= CAST(:now AS timestamptz)))
     FOR UPDATE SKIP LOCKED
)
UPDATE match_seat_holds h
   SET closed_at = due.at, closed_reason = due.why
  FROM due
 WHERE h.id = due.id
RETURNING h.id, h.closed_reason
"""


async def hold_sweep(db: AsyncSession) -> dict:
    """Stamp the closure of every hold past its own deadline, in one
    transaction, skipping rows another transaction holds (FOR UPDATE SKIP
    LOCKED). The stamp is the deadline itself (held_until, or bound_at +
    ENTRY_BOUND_S with no entry), never the time of the sweep, and no
    statement here moves held_until: a late sweep never extends a hold.
    The janitor call is NX2 of the build brief. Returns {reason: count}."""
    async with database_deadline(db):
        return await _hold_sweep(db)


async def _hold_sweep(db: AsyncSession) -> dict:
    now = await _ctx_now(db)
    rows = (await db.execute(text(_SWEEP_SQL),
                             {"now": now, "eb": ENTRY_BOUND_S})).all()
    await db.commit()
    out = {}
    for _, why in rows:
        out[why] = out.get(why, 0) + 1
    return out


# ---------------------------------------------------------------------------
# S3. Discovery, claim, bind and entry (server half)
# ---------------------------------------------------------------------------

async def _attempt(db: AsyncSession, hold_id, kind: str, now, outcome: str,
                   reason: Optional[str] = None) -> None:
    """One match_hold_attempts row, numbered after the hold's last one, in
    the caller's transaction (S6: rows share their transaction). Every
    caller holds the hold row lock, so the numbering cannot race."""
    await db.execute(text(
        "INSERT INTO match_hold_attempts (hold_id, attempt_no, kind, at, outcome, reason)"
        " SELECT CAST(:hid AS uuid), COALESCE(max(attempt_no), 0) + 1, CAST(:kind AS varchar),"
        "        CAST(:now AS timestamptz), CAST(:outcome AS varchar), CAST(:reason AS varchar)"
        "   FROM match_hold_attempts WHERE hold_id = CAST(:hid AS uuid)"),
        {"hid": str(hold_id), "kind": kind, "now": now, "outcome": outcome,
         "reason": reason})


async def _refuse_attempt(db, hold_id, kind, now, reason):
    await _attempt(db, hold_id, kind, now, "refused", reason)
    await db.commit()
    return _refused(reason)


@router.get("/hold/mine")
async def match_hold_mine(steam_id: str, request: Request,
                          db: AsyncSession = Depends(_bounded_match_db)):
    """Discovery for a relaunched team or 1v2 client (S3). Requires the
    caller's session. With a live hold of the caller it writes ONE `offered`
    attempt row (and offered_at once) committed BEFORE the answer, and sets
    no queue flag; a write failure answers 503 and offers nothing. Without a
    live hold it writes nothing and answers readmissible 0."""
    await _require_verified_session(request, steam_id, db)
    pid = await _player_id(db, steam_id)
    hold = None
    if pid is not None:
        hold = (await db.execute(text(
            f"SELECT {_HOLD_COLS} FROM match_seat_holds"
            " WHERE player_id = CAST(:pid AS uuid) AND closed_at IS NULL"
            " ORDER BY held_at DESC LIMIT 1 FOR NO KEY UPDATE"),
            {"pid": str(pid)})).mappings().first()
    now = await _ctx_now(db)
    if hold is None or not _hold_live(hold, now):
        await db.rollback()
        return {"readmissible": 0}
    try:
        series = await _series_read(db, hold["mode"], hold["series_id"])
        await db.execute(text(
            "UPDATE match_seat_holds SET offered_at = COALESCE(offered_at, CAST(:now AS timestamptz))"
            " WHERE id = CAST(:hid AS uuid)"), {"now": now, "hid": str(hold["id"])})
        await _attempt(db, hold["id"], "offered", now, "ok")
        await db.commit()
    except Exception as ex:
        await db.rollback()
        print(f"[HOLD] offer row not written ({type(ex).__name__}); no offer")
        raise HTTPException(503, "offer not recorded")
    print(f"[HOLD] offered room={hold['room_name']} slot={hold['slot']} n={hold['n']}")
    out = _state_payload(hold, now)
    out.update({"readmissible": 1,
                "room_region": series["region"] if series else None,
                "series_tally": [series["w0"], series["w1"]] if series else None})
    return out


class HoldClaimReq(BaseModel):
    steam_id: str = Field(..., min_length=1, max_length=20)


async def _other_commitment(db, pid, mode, series_id) -> bool:
    """A live lease of another mode (_lease_live_mode), or a team or 1v2
    queue row of the caller outside this series (a hosted lobby seat or a
    search is a queue commitment)."""
    from main import _lease_live_mode   # late import

    live = await _lease_live_mode(db, pid)
    if live is not None and live != mode:
        return True
    return bool((await db.execute(text(
        "SELECT 1 FROM team_queue WHERE player_id = CAST(:pid AS uuid)"
        "   AND series_id IS DISTINCT FROM CAST(:sid AS uuid)"
        " UNION ALL "
        "SELECT 1 FROM ovt_queue WHERE player_id = CAST(:pid AS uuid)"
        "   AND series_id IS DISTINCT FROM CAST(:sid AS uuid)"),
        {"pid": str(pid), "sid": str(series_id)})).first())


@router.post("/hold/{hold_id}/claim")
async def match_hold_claim(hold_id: uuid.UUID, req: HoldClaimReq, request: Request,
                           db: AsyncSession = Depends(_bounded_match_db)):
    """Claim a held seat (S3 step 1). One transaction, series row then hold
    row locked, every predicate re-checked under the locks (#208): own hold
    (not_yours), open and in time (hold_lapsed), series still active
    (lobby_closed), no live lease of another mode and no other team or 1v2
    queue commitment (other_mode). The grant stores only the SHA-256
    verifier of a fresh 256-bit token T, re-takes the lease for this mode
    and series, and answers T once; a repeat rotates T. Nothing here moves
    held_until. Every claim, refused or granted, writes its attempt row in
    this transaction."""
    from main import _lease_acquire, _lease_admission_gate, LEASE_TTL_ASSEMBLY

    await _require_verified_session(request, req.steam_id, db)
    pid = await _player_id(db, req.steam_id)
    peek = await _hold_row(db, hold_id)
    if peek is None:
        await db.rollback()
        raise HTTPException(404, "no such hold")
    series = await _series_lock(db, peek["mode"], peek["series_id"])
    hold = await _hold_row(db, hold_id, lock=True)
    if pid is None or hold["player_id"] != pid:
        now = await _ctx_now(db)
        return await _refuse_attempt(db, hold_id, "claim", now, "not_yours")
    admitted, now = await _lease_admission_gate(
            db, [pid], hold["mode"], hold["series_id"],
            allowed_hold_ids=(hold_id,), hold_entry_bound_seconds=ENTRY_BOUND_S,
            strict_team_ovt_queue=True)
    if not admitted:
        # Roll back the losing claim before its required audit row. Re-locking
        # the hold gives the fresh audit transaction its numbering invariant.
        await db.rollback()
        await _install_database_timeouts(db)
        hold = await _hold_row(db, hold_id, lock=True)
        now = await _ctx_now(db)
        return await _refuse_attempt(db, hold_id, "claim", now, "other_mode")
    if not _hold_live(hold, now):
        return await _refuse_attempt(db, hold_id, "claim", now, "hold_lapsed")
    if series is None or series["status"] not in _ACTIVE:
        return await _refuse_attempt(db, hold_id, "claim", now, "lobby_closed")
    token = secrets.token_hex(32)
    verifier = hashlib.sha256(token.encode()).hexdigest()
    await db.execute(text(
        "UPDATE match_seat_holds SET claimed_at = COALESCE(claimed_at, CAST(:now AS timestamptz)),"
        "       verifier = CAST(:v AS varchar)"
        " WHERE id = CAST(:hid AS uuid)"), {"now": now, "v": verifier, "hid": str(hold_id)})
    await _lease_acquire(db, pid, hold["mode"], hold["series_id"],
                         LEASE_TTL_ASSEMBLY, _gate_held=True)
    digest = (await db.execute(text(
        "SELECT boundary_digest FROM match_seat_presence"
        " WHERE room_name = CAST(:room AS varchar) AND player_id = CAST(:pid AS uuid)"),
        {"room": hold["room_name"], "pid": str(pid)})).scalar()
    await _attempt(db, hold_id, "claim", now, "ok")
    await db.commit()
    print(f"[HOLD] claimed room={hold['room_name']} slot={hold['slot']} n={hold['n']}")
    out = _state_payload(
        dict(hold, claimed_at=hold["claimed_at"] or now, verifier=verifier), now)
    out.update({"status": "claimed", "token": token, "hold": True,
                "room_region": series["region"], "boundary_digest": digest})
    return out


class HoldBindReq(BaseModel):
    steam_id: str = Field(..., min_length=1, max_length=20)
    actor: int = Field(..., ge=1, le=100000)
    region: Optional[str] = Field(None, max_length=8)


_CORROBORATED_SQL = (
    "SELECT 1 FROM match_seat_presence"
    " WHERE room_name = CAST(:room AS varchar) AND player_id <> CAST(:pid AS uuid)"
    "   AND beat_at > CAST(:now AS timestamptz) - make_interval(secs => CAST(:f AS integer))"
    "   AND seen @> CAST(:probe AS jsonb) LIMIT 1")
_MISMATCH_SQL = (
    "SELECT 1 FROM match_seat_presence"
    " WHERE room_name = CAST(:room AS varchar)"
    "   AND beat_at > CAST(:now AS timestamptz) - make_interval(secs => CAST(:f AS integer))"
    "   AND (jsonb_path_exists(seen, '$[*] ? (@.u_id == $u && @.actor != $x)',"
    "                          CAST(:vars AS jsonb))"
    "        OR (player_id = CAST(:pid AS uuid) AND actor IS NOT NULL"
    "            AND actor <> CAST(:x AS integer)))"
    " LIMIT 1")


async def _corroborated(db, hold, actor, now) -> bool:
    """A fresh beat of ANOTHER fighter of the room lists actor X with the
    held Steam id."""
    steam = (await db.execute(text("SELECT steam_id FROM players WHERE id = CAST(:p AS uuid)"),
                              {"p": str(hold["player_id"])})).scalar()
    probe = json.dumps([{"actor": int(actor), "u_id": steam}])
    return bool((await db.execute(text(_CORROBORATED_SQL), {
        "room": hold["room_name"], "pid": str(hold["player_id"]), "now": now,
        "f": BEAT_FRESH_S, "probe": probe})).scalar())


async def _identity_mismatch(db, hold, actor, now) -> bool:
    """A fresh beat lists ANOTHER actor for the held Steam id (or the held
    player's own fresh beat names another actor)."""
    steam = (await db.execute(text("SELECT steam_id FROM players WHERE id = CAST(:p AS uuid)"),
                              {"p": str(hold["player_id"])})).scalar()
    return bool((await db.execute(text(_MISMATCH_SQL), {
        "room": hold["room_name"], "pid": str(hold["player_id"]), "now": now,
        "f": BEAT_FRESH_S, "x": int(actor),
        "vars": json.dumps({"u": steam, "x": int(actor)})})).scalar())


@router.post("/hold/{hold_id}/bind")
async def match_hold_bind(hold_id: uuid.UUID, req: HoldBindReq, request: Request,
                          db: AsyncSession = Depends(_bounded_match_db)):
    """Bind the returner's new actor X (S3 step 3). Under the hold row lock:
    the hold must be the caller's (not_yours), live (hold_lapsed) and claimed
    (not_claimed); a fresh beat of another fighter must list X with the held
    Steam id (uncorroborated, retried by the client); no fresh beat may list
    another actor for that Steam id (actor_identity_mismatch); no other open
    hold may have bound X (actor_conflict); a row already bound to another
    actor refuses (already_bound) and one bound to X answers as bound. The
    bind stamps bound_at, X and the region, seq + 1, and its attempt row,
    in one transaction."""
    await _require_verified_session(request, req.steam_id, db)
    pid = await _player_id(db, req.steam_id)
    hold = await _hold_row(db, hold_id, lock=True)
    if hold is None:
        await db.rollback()
        raise HTTPException(404, "no such hold")
    now = await _ctx_now(db)                 # after the hold row lock
    if pid is None or hold["player_id"] != pid:
        return await _refuse_attempt(db, hold_id, "bind", now, "not_yours")
    if not _hold_live(hold, now):
        return await _refuse_attempt(db, hold_id, "bind", now, "hold_lapsed")
    if hold["claimed_at"] is None:
        return await _refuse_attempt(db, hold_id, "bind", now, "not_claimed")
    if hold["bound_at"] is not None:
        if hold["bound_actor"] != req.actor:
            return await _refuse_attempt(db, hold_id, "bind", now, "already_bound")
        await _attempt(db, hold_id, "bind", now, "ok")
        await db.commit()
        out = _state_payload(hold, now)
        out["status"] = "bound"
        return out
    if not await _corroborated(db, hold, req.actor, now):
        return await _refuse_attempt(db, hold_id, "bind", now, "uncorroborated")
    if await _identity_mismatch(db, hold, req.actor, now):
        return await _refuse_attempt(db, hold_id, "bind", now, "actor_identity_mismatch")
    conflict = (await db.execute(text(
        "SELECT 1 FROM match_seat_holds WHERE room_name = CAST(:room AS varchar)"
        "   AND id <> CAST(:hid AS uuid) AND closed_at IS NULL"
        "   AND held_until > CAST(:now AS timestamptz)"
        "   AND (bound_at IS NULL OR entered_at IS NOT NULL"
        "        OR bound_at + make_interval(secs => CAST(:eb AS integer))"
        "             > CAST(:now AS timestamptz))"
        "   AND bound_actor = CAST(:x AS integer)"),
        {"room": hold["room_name"], "hid": str(hold_id), "now": now,
         "eb": ENTRY_BOUND_S, "x": req.actor})).scalar()
    if conflict:
        return await _refuse_attempt(db, hold_id, "bind", now, "actor_conflict")
    bound = (await db.execute(text(
        "UPDATE match_seat_holds SET bound_at = CAST(:now AS timestamptz),"
        "       bound_actor = CAST(:x AS integer), bound_region = CAST(:reg AS varchar),"
        "       seq = seq + 1"
        f" WHERE id = CAST(:hid AS uuid) RETURNING {_HOLD_COLS}"),
        {"now": now, "x": req.actor, "reg": req.region, "hid": str(hold_id)})
    ).mappings().first()
    await _attempt(db, hold_id, "bind", now, "ok")
    await db.commit()
    print(f"[HOLD] bound room={hold['room_name']} slot={hold['slot']} n={hold['n']}")
    out = _state_payload(bound, now)
    out["status"] = "bound"
    return out


class HoldEnteredReq(BaseModel):
    steam_id: str = Field(..., min_length=1, max_length=20)
    game_id: uuid.UUID
    actor: int = Field(..., ge=1, le=100000)


@router.post("/hold/{hold_id}/entered")
async def match_hold_entered(hold_id: uuid.UUID, req: HoldEnteredReq, request: Request,
                             db: AsyncSession = Depends(_bounded_match_db)):
    """Accept the returner's entry (S3 step 8): only from the claiming
    owner's session (not_yours), on a live (hold_lapsed, which includes the
    entry bound after bind) and bound (not_bound) hold, with X equal to the
    bound actor (actor_mismatch), G equal to the hold's game (game_mismatch)
    and a fresh beat of another fighter listing X with the held Steam id
    (uncorroborated). It stamps entered_at and closed_at = entered once,
    spends T (the verifier is cleared) and seq + 1, with its attempt row."""
    await _require_verified_session(request, req.steam_id, db)
    pid = await _player_id(db, req.steam_id)
    hold = await _hold_row(db, hold_id, lock=True)
    if hold is None:
        await db.rollback()
        raise HTTPException(404, "no such hold")
    now = await _ctx_now(db)                 # after the hold row lock
    if pid is None or hold["player_id"] != pid:
        return await _refuse_attempt(db, hold_id, "entered", now, "not_yours")
    if not _hold_live(hold, now):
        return await _refuse_attempt(db, hold_id, "entered", now, "hold_lapsed")
    if hold["bound_at"] is None:
        return await _refuse_attempt(db, hold_id, "entered", now, "not_bound")
    if hold["bound_actor"] != req.actor:
        return await _refuse_attempt(db, hold_id, "entered", now, "actor_mismatch")
    if hold["game_id"] != req.game_id:
        return await _refuse_attempt(db, hold_id, "entered", now, "game_mismatch")
    if not await _corroborated(db, hold, req.actor, now):
        return await _refuse_attempt(db, hold_id, "entered", now, "uncorroborated")
    done = (await db.execute(text(
        "UPDATE match_seat_holds SET entered_at = CAST(:now AS timestamptz),"
        "       closed_at = CAST(:now AS timestamptz), closed_reason = 'entered',"
        "       verifier = NULL, seq = seq + 1"
        f" WHERE id = CAST(:hid AS uuid) AND closed_at IS NULL RETURNING {_HOLD_COLS}"),
        {"now": now, "hid": str(hold_id)})).mappings().first()
    await _attempt(db, hold_id, "entered", now, "ok")
    await db.commit()
    print(f"[HOLD] entered room={hold['room_name']} slot={hold['slot']} n={hold['n']}")
    out = _state_payload(done, now)
    out["status"] = "entered"
    return out
