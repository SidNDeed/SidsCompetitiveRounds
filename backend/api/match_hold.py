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

ONE DB CLOCK. Every writer and reader reads clock_timestamp() once per
transaction (`_ctx_now`), AFTER the transaction's first row lock, and binds
that value; no statement here reads NOW() (which would answer the start of a
transaction that may have waited on a lock) and nothing reads the
application clock.

LOCKS. The series row is locked FOR NO KEY UPDATE (#202): it serializes this
module's writers on one series, and unlike FOR UPDATE it does not conflict
with the FOR KEY SHARE that a foreign-key insert referencing the row takes.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db

router = APIRouter(prefix="/api/v1/match", tags=["Match Hold"])

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


@router.post("/game/start")
async def match_game_start(req: GameStartReq, request: Request,
                           db: AsyncSession = Depends(get_db)):
    """Mint or return the game id G of the game starting in a flagged room.

    Requires the poster's Steam session and series membership, a series row
    flagged for exactly this room and still active. Under the series lock:
    the row whose prev_game equals the posted previous G (or, with none
    posted, the first game of the room) is returned when it exists, so a
    promoted master re-posting the same previous G receives the same G and a
    handover never forks a game; otherwise one row is inserted with seq one
    more than the latest of (series, room). A previous G that is not a game
    of this series and room is refused."""
    from main import _check_steam_session   # late import: main mounts this module at NX1

    mode = _mode_or_400(req.mode)
    room = req.room.strip()
    await _check_steam_session(request, req.steam_id, db)
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
