"""Ask 14 (the player report form): the five routes.

  POST /api/v1/player-reports                          a player files a report
  GET  /api/v1/player-reports/games                    the caller's own reportable games
  GET  /api/v1/admin/player-reports                    admin: the list
  GET  /api/v1/admin/player-reports/{report_id}/log    admin: one report's attached log
  POST /api/v1/admin/player-reports/{report_id}/close  admin: close a report

Every decision is a pure function in player_report_rules.py (its docstring
states the nine rules of the submit and their order). This module gathers the
facts those functions need, calls them and writes. It reaches main's session
readers, admin checks, identity locks and log helpers by late imports inside
its functions, because main mounts this module (the form of match_hold).

NAMES. The route-manifest gate resolves bare and attribute names across
modules, so every top-level name of this module and of the rules module is
the lane's own (imports are aliased _plr_ or _Plr, the router is plr_router):
no existing route reaches a binding of theirs, and none of their rows moves
because these two files exist.

WHO THE REPORTER IS. The account the request's session names (_session_seat),
accepted only when that session is known, unexpired and Steam-verified for it
(_strict_steam_session_ok). No route reads a reporter from a body or a query.

WHO READS A REPORT. The three admin routes, each requiring an admin account
(_is_admin) and an admin signature over its own action word and target
(_verify_admin_hmac). No route returns a report, a count of reports or a
report's state to a player; the reported player is sent nothing; the submit's
answer carries no id; the bot has no reader here.

THE TWO GET ROUTES FOR PLAYERS AND ADMINS NEVER WRITE. The only statements that
write are in the two POST routes: the submit (one report row, at most one log
row, the retention DELETE) and the close (one UPDATE, the retention DELETE).
Both refuse on a read replica.

THE SUBMIT'S TRANSACTIONS. Rules 1 and 2 are read, then the body, then rules 5
to 9 are decided once without locks. Only if a log is attached, that read
transaction is ended and the log is compressed on the auto-log CPU pool with a
ceiling, holding no connection. Then, in one transaction: the identity locks
of the reporter and the reported player (the locks account deletion takes),
the session again, rules 5 to 9 again, the INSERTs and the retention DELETE.
A log that could not be prepared BEFORE that transaction (over its stored cap,
or the pool did not finish) leaves the report to be written alone and the
answer says log_stored false. An error INSIDE the transaction fails the
request: nothing is written and nothing is retried.
"""

import json as _plr_json
import uuid as _plr_uuid

from fastapi import APIRouter as _PlrRouter
from fastapi import Depends as _plr_depends
from fastapi import HTTPException as _PlrHttpError
from fastapi import Query as _plr_query
from fastapi import Request as _PlrRequest
from fastapi.responses import PlainTextResponse as _PlrPlainText
from pydantic import BaseModel as _PlrModel
from sqlalchemy import text as _plr_sql
from sqlalchemy.ext.asyncio import AsyncSession as _PlrDb

from database import get_db as _plr_get_db
from read_gate import ReadGateRoute as _PlrGateRoute

import player_report_rules as _plr

plr_router = _PlrRouter(tags=["Player Reports"], route_class=_PlrGateRoute)

# N days as an exact span. 'N days' is calendar arithmetic in the session's
# time zone (a day lasts 23 or 25 hours across a clock change), and the
# retention bound must be the same instant here and in _plr.log_readable,
# which adds a timedelta, whatever zone the session runs in.
_DAYS = "(%d * INTERVAL '24 hours')"
_WINDOW = _DAYS % _plr.GAME_WINDOW_DAYS

# The caller's own recent games, newest first, with every live player of each:
# one statement, read by BOTH player routes (_plr.fold_games). Each branch is
# bounded by the caller's id and the window, and by the list's length; a
# player sits in one seat of a game, so no branch returns a game twice.
# g_1v1 leaves out the rows of `matches` that carry a team, 1v2 or FFA room
# (the same three prefixes _h2h_modes_block leaves out); g_ffa counts a player
# who played that game, never a roster ghost (absent).
GAMES_SQL = """
WITH g_1v1 AS (
    SELECT '1v1' AS kind, m.id, m.ended_at, ARRAY[m.player1_id, m.player2_id] AS pids
      FROM matches m
     WHERE (m.player1_id = :pid OR m.player2_id = :pid)
       AND m.ended_at > now() - """ + _WINDOW + """
       AND m.invalidated_at IS NULL
       AND (m.photon_room_id IS NULL OR (
               LEFT(m.photon_room_id, 5) <> 'team_'
           AND LEFT(m.photon_room_id, 4) <> 'ovt_'
           AND LEFT(m.photon_room_id, 4) <> 'ffa_'))
     ORDER BY m.ended_at DESC, m.id DESC
     LIMIT :lim
), g_2v2 AS (
    SELECT '2v2' AS kind, tm.id, tm.ended_at,
           ARRAY[tm.t1a_id, tm.t1b_id, tm.t2a_id, tm.t2b_id] AS pids
      FROM team_matches tm
     WHERE (tm.t1a_id = :pid OR tm.t1b_id = :pid OR tm.t2a_id = :pid OR tm.t2b_id = :pid)
       AND tm.ended_at > now() - """ + _WINDOW + """
       AND tm.invalidated_at IS NULL
     ORDER BY tm.ended_at DESC, tm.id DESC
     LIMIT :lim
), g_1v2 AS (
    SELECT '1v2' AS kind, om.id, om.ended_at,
           ARRAY[om.solo_id, om.duo_a_id, om.duo_b_id] AS pids
      FROM ovt_matches om
     WHERE (om.solo_id = :pid OR om.duo_a_id = :pid OR om.duo_b_id = :pid)
       AND om.ended_at > now() - """ + _WINDOW + """
       AND om.invalidated_at IS NULL
     ORDER BY om.ended_at DESC, om.id DESC
     LIMIT :lim
), g_ffa AS (
    SELECT 'ffa' AS kind, fm.id, fm.ended_at,
           (SELECT array_agg(x.player_id) FROM ffa_match_players x
             WHERE x.match_id = fm.id AND NOT x.absent) AS pids
      FROM ffa_match_players me
      JOIN ffa_matches fm ON fm.id = me.match_id
     WHERE me.player_id = :pid AND NOT me.absent
       AND fm.ended_at > now() - """ + _WINDOW + """
       AND fm.invalidated_at IS NULL
     ORDER BY fm.ended_at DESC, fm.id DESC
     LIMIT :lim
), listed AS (
    SELECT u.kind, u.id, u.ended_at, u.pids
      FROM (SELECT kind, id, ended_at, pids FROM g_1v1
            UNION ALL SELECT kind, id, ended_at, pids FROM g_2v2
            UNION ALL SELECT kind, id, ended_at, pids FROM g_1v2
            UNION ALL SELECT kind, id, ended_at, pids FROM g_ffa) u
     ORDER BY u.ended_at DESC, u.id DESC
     LIMIT :lim
)
SELECT t.kind, t.id, t.ended_at, p.id AS player_id, p.steam_id, p.display_name
  FROM listed t
  JOIN players p ON p.id = ANY(t.pids)
 WHERE p.deleted_at IS NULL
 ORDER BY t.ended_at DESC, t.id DESC, p.display_name, p.steam_id
"""

SWITCH_SQL = "SELECT value FROM runtime_settings WHERE key = :k"
PLAYER_SQL = "SELECT id FROM players WHERE steam_id = :s AND deleted_at IS NULL"
DUPLICATE_SQL = ("SELECT 1 FROM player_reports WHERE reporter_id = :rp AND game_kind = :k"
                 " AND game_id = :g AND reported_id = :rd")
RECENT_SQL = ("SELECT COUNT(*) FROM player_reports WHERE reporter_id = :rp"
              " AND created_at > now() - INTERVAL '24 hours'")
MY_REPORTS_SQL = ("SELECT game_kind, game_id, reported_id FROM player_reports WHERE reporter_id = :rp"
                  " AND game_ended_at > now() - " + _DAYS % (_plr.GAME_WINDOW_DAYS + 1))

# The UNIQUE constraint is the backstop of rule 8: a second row for the same
# reporter, game and player inserts nothing and returns nothing.
INSERT_SQL = """
INSERT INTO player_reports
       (id, reporter_id, reported_id, game_kind, game_id, game_ended_at, reason, details)
VALUES (:id, :rp, :rd, :k, :g, :e, :r, :d)
ON CONFLICT ON CONSTRAINT player_reports_once DO NOTHING
RETURNING id
"""
INSERT_LOG_SQL = "INSERT INTO player_report_logs (report_id, gz, raw_chars) VALUES (:id, :gz, :n)"

# _plr.log_readable, negated, in SQL: the stored logs no reader serves any
# more. It runs inside the two POST transactions and nowhere else;
# test_player_reports_pg.py holds the two forms to the same answer.
RETENTION_SQL = """
DELETE FROM player_report_logs l
 USING player_reports r
 WHERE r.id = l.report_id
   AND NOT (
        (r.closed_at IS NULL AND now() < r.created_at + """ + _DAYS % _plr.OPEN_LOG_DAYS + """)
     OR (r.closed_at IS NOT NULL
         AND r.closed_at < r.created_at + """ + _DAYS % _plr.OPEN_LOG_DAYS + """
         AND now() < r.closed_at + """ + _DAYS % _plr.CLOSED_LOG_DAYS + """))
"""


def _plr_refuse(refusal):
    raise _PlrHttpError(status_code=refusal.status, detail={"error": refusal.code})


async def _plr_session(request, db):
    """(the account the request's session names, whether that session is
    known, unexpired and Steam-verified for it), through main's two readers."""
    import main                           # late import: main mounts this module
    steam_id = await main._session_seat(request, db)
    if not steam_id:
        return None, False
    return steam_id, await main._strict_steam_session_ok(request, steam_id, db)


async def _player_gate(request, db, declared_length):
    """Rules 1 to 3 for both player routes; returns the session's account. The
    switch is read only for a request whose session already passed, so a
    request without one stops at the session read."""
    steam_id, verified = await _plr_session(request, db)
    switch = None
    if _plr.session_refusal(steam_id, verified) is None:
        row = (await db.execute(_plr_sql(SWITCH_SQL), {"k": _plr.SWITCH_KEY})).first()
        switch = None if row is None else str(row[0])
    refusal = _plr.pre_body_refusal(steam_id, verified, switch, declared_length)
    if refusal is not None:
        _plr_refuse(refusal)
    return steam_id


async def _listed_games(db, reporter_id):
    rows = (await db.execute(_plr_sql(GAMES_SQL),
                             {"pid": reporter_id, "lim": _plr.GAME_LIST_MAX})).all()
    return _plr.fold_games([tuple(r) for r in rows], reporter_id)


async def _facts(db, reporter_steam_id, sub) -> tuple:
    """The facts rules 5 to 9 decide on, in the order _plr.decide_submit takes them:
    (reporter_id, game, reported, duplicate, recent)."""
    reporter_id = (await db.execute(_plr_sql(PLAYER_SQL), {"s": reporter_steam_id})).scalar()
    if reporter_id is None:
        return None, None, None, False, 0
    game = _plr.find_game(await _listed_games(db, reporter_id), sub.game_kind, sub.game_id)
    reported = _plr.find_player(game, sub.reported_steam_id)
    duplicate = False
    if reported is not None:
        duplicate = (await db.execute(_plr_sql(DUPLICATE_SQL), {
            "rp": reporter_id, "k": sub.game_kind, "g": sub.game_id,
            "rd": reported.player_id})).first() is not None
    recent = (await db.execute(_plr_sql(RECENT_SQL), {"rp": reporter_id})).scalar() or 0
    return reporter_id, game, reported, duplicate, int(recent)


async def _read_body(request) -> bytes:
    """The body, refused the moment it passes the ceiling (rule 3)."""
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        refusal = _plr.size_refusal(len(raw))
        if refusal is not None:
            _plr_refuse(refusal)
    return bytes(raw)


async def _prepared_log(log_text: str) -> tuple:
    """(gz, raw_chars) for the log as stored, or (None, 0) when it could not
    be prepared: over its stored cap, or the CPU pool did not finish within
    its ceiling. Both are failures BEFORE the write transaction, and the
    report is then written without a log."""
    import main
    al = main._auto_logs
    try:
        gz, raw_chars = await al._hop(al._CPU_POOL, al.AUTO_LOG_CPU_WAIT_S,
                                      _plr.prepare_log, log_text)
    except Exception as ex:
        print(f"[PLAYER-REPORT] log not prepared, report stored without it: {type(ex).__name__}")
        return None, 0
    if gz is None:
        print(f"[PLAYER-REPORT] log over {_plr.LOG_GZ_MAX} bytes gzipped, report stored without it")
        return None, 0
    return gz, raw_chars


@plr_router.post("/api/v1/player-reports")
async def submit_player_report(request: _PlrRequest, db: _PlrDb = _plr_depends(_plr_get_db)):
    """A player reports another player of one of their own recent games."""
    import main
    if main.IS_REPLICA:
        main._replica_skip("player_report_submit")
        raise _PlrHttpError(status_code=503, detail={"error": "read_replica"})
    # Rules 1 to 3, before a byte of the body is read.
    steam_id = await _player_gate(request, db, request.headers.get("content-length"))
    raw = await _read_body(request)
    try:
        obj = _plr_json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        obj = None
    sub, refusal = _plr.parse_submit(obj)                      # rule 4
    if refusal is not None:
        _plr_refuse(refusal)

    # Rules 5 to 9 once WITHOUT the locks: a report that will be refused costs
    # no compression, and no identity lock is taken for an account that is not
    # a player of one of the caller's own listed games.
    refusal = _plr.decide_submit(*await _facts(db, steam_id, sub))
    if refusal is not None:
        _plr_refuse(refusal)
    gz, raw_chars = None, 0
    if sub.log_text:
        await main._auto_logs._end_transaction(db)             # no connection held while the pool works
        gz, raw_chars = await _prepared_log(sub.log_text)

    # The write transaction. The identity locks are the ones account deletion
    # takes: a deletion of either account that got there first is seen below
    # (the session is gone, or the player is no longer listed), and one that
    # comes second waits and then deletes the row written here.
    await main._identity_lock_many(db, [steam_id, sub.reported_steam_id])
    if not await main._strict_steam_session_ok(request, steam_id, db):
        _plr_refuse(_plr.SESSION_REQUIRED)
    reporter_id, game, reported, duplicate, recent = await _facts(db, steam_id, sub)
    refusal = _plr.decide_submit(reporter_id, game, reported, duplicate, recent)
    if refusal is not None:
        _plr_refuse(refusal)
    report_id = _plr_uuid.uuid4()
    stored = (await db.execute(_plr_sql(INSERT_SQL), {
        "id": report_id, "rp": reporter_id, "rd": reported.player_id, "k": game.kind,
        "g": game.game_id, "e": game.ended_at, "r": sub.reason, "d": sub.details})).first()
    if stored is None:
        _plr_refuse(_plr.ALREADY_REPORTED)
    if gz is not None:
        await db.execute(_plr_sql(INSERT_LOG_SQL), {"id": report_id, "gz": gz, "n": raw_chars})
    await db.execute(_plr_sql(RETENTION_SQL))
    await db.commit()
    return {"ok": True, "log_stored": gz is not None}


@plr_router.get("/api/v1/player-reports/games")
async def my_reportable_games(request: _PlrRequest, db: _PlrDb = _plr_depends(_plr_get_db)):
    """The caller's own recent games with each game's other players: what the
    form offers, and exactly what the submit accepts."""
    steam_id = await _player_gate(request, db, None)
    reporter_id = (await db.execute(_plr_sql(PLAYER_SQL), {"s": steam_id})).scalar()
    if reporter_id is None:
        # An account that never played has no game to list: an empty
        # answer, not a refusal the form would collect on every opening.
        return _plr.games_payload([], set(), 0)
    games = await _listed_games(db, reporter_id)
    mine = (await db.execute(_plr_sql(MY_REPORTS_SQL), {"rp": reporter_id})).all()
    recent = (await db.execute(_plr_sql(RECENT_SQL), {"rp": reporter_id})).scalar() or 0
    return _plr.games_payload(games, {_plr.report_key(*tuple(r)) for r in mine}, recent)


# -- the admin routes -------------------------------------------------------------

_LIST_HEAD = """
SELECT r.id, r.created_at, r.status, r.reason, r.details, r.game_kind, r.game_id,
       r.game_ended_at, r.closed_at, r.close_note,
       rp.steam_id AS reporter_steam_id, rp.display_name AS reporter_name,
       rd.steam_id AS reported_steam_id, rd.display_name AS reported_name,
       cb.display_name AS closed_by_name,
       (l.report_id IS NOT NULL) AS log_stored,
       (SELECT COUNT(DISTINCT x.reporter_id) FROM player_reports x
         WHERE x.reported_id = r.reported_id
           AND x.created_at > now() - """ + _DAYS % _plr.REPORTED_COUNT_DAYS + """) AS reporters_30d,
       now() AS now
  FROM player_reports r
  JOIN players rp ON rp.id = r.reporter_id
  JOIN players rd ON rd.id = r.reported_id
  LEFT JOIN players cb ON cb.id = r.closed_by
  LEFT JOIN player_report_logs l ON l.report_id = r.id
"""
_LIST_TAIL = """
 ORDER BY (r.status = 'open') DESC, r.created_at DESC, r.id DESC
 LIMIT :lim OFFSET :off
"""
LIST_SQL = _LIST_HEAD + _LIST_TAIL
LIST_BY_STATUS_SQL = _LIST_HEAD + " WHERE r.status = :st" + _LIST_TAIL
COUNTS_SQL = ("SELECT COUNT(*) FILTER (WHERE status = 'open') AS open_total, COUNT(*) AS total"
              " FROM player_reports")
LOG_META_SQL = """
SELECT r.created_at, r.closed_at, (l.report_id IS NOT NULL) AS log_stored, now() AS now
  FROM player_reports r
  LEFT JOIN player_report_logs l ON l.report_id = r.id
 WHERE r.id = :id
"""
LOG_GZ_SQL = "SELECT gz FROM player_report_logs WHERE report_id = :id"
CLOSE_SQL = """
UPDATE player_reports
   SET status = :v, closed_by = :adm, closed_at = now(), close_note = :n
 WHERE id = :id AND status = 'open'
RETURNING id
"""
STATUS_SQL = "SELECT status FROM player_reports WHERE id = :id"


class PlayerReportCloseRequest(_PlrModel):
    """Admin POST body for /api/v1/admin/player-reports/{id}/close."""
    admin_steam_id: str
    hmac_signature: str | None = None
    verdict: str                      # dismissed | actioned
    note: str | None = None


async def _admin(db, admin_steam_id, action, target, signature) -> None:
    """An admin account, then an admin signature over this route's own action
    word and target; the two checks every admin route here starts with."""
    import main
    if not await main._is_admin(db, admin_steam_id):
        raise _PlrHttpError(403, "Not an admin")
    if not main._verify_admin_hmac(admin_steam_id, action, str(target), signature):
        raise _PlrHttpError(403, "Invalid admin signature")


def _report_id(report_id: str):
    try:
        return _plr_uuid.UUID(report_id)
    except (ValueError, AttributeError, TypeError):
        raise _PlrHttpError(400, "Invalid report_id")


@plr_router.get("/api/v1/admin/player-reports")
async def admin_list_player_reports(
    admin_steam_id: str = _plr_query(...),
    hmac_signature: str | None = _plr_query(None),
    status: str | None = _plr_query(None, max_length=12),
    limit: int = _plr_query(50, ge=1, le=200),
    offset: int = _plr_query(0, ge=0),
    db: _PlrDb = _plr_depends(_plr_get_db),
):
    """Admin: the reports, open first and newest first, with the count of open
    reports the admin menu's launcher shows."""
    await _admin(db, admin_steam_id, _plr.ACTION_LIST, _plr.TARGET_LIST, hmac_signature)
    if status is not None and status not in _plr.REPORT_STATUSES:
        raise _PlrHttpError(status_code=422, detail={"error": "bad_status"})
    params = {"lim": limit, "off": offset}
    if status is None:
        rows = (await db.execute(_plr_sql(LIST_SQL), params)).mappings().all()
    else:
        rows = (await db.execute(_plr_sql(LIST_BY_STATUS_SQL), dict(params, st=status))).mappings().all()
    counts = (await db.execute(_plr_sql(COUNTS_SQL))).first()
    return {"reports": [_plr.list_row(r, r["now"]) for r in rows],
            "open_total": int(counts[0] or 0), "total": int(counts[1] or 0)}


@plr_router.get("/api/v1/admin/player-reports/{report_id}/log")
async def admin_player_report_log(
    report_id: str,
    admin_steam_id: str = _plr_query(...),
    hmac_signature: str | None = _plr_query(None),
    db: _PlrDb = _plr_depends(_plr_get_db),
):
    """Admin: one report's attached log as plain text, through the scrub every
    read-back of client log text applies (_scrub_bug_log). A log past its
    retention day answers as a report that never had one."""
    import main
    await _admin(db, admin_steam_id, _plr.ACTION_LOG, report_id, hmac_signature)
    rid = _report_id(report_id)
    meta = (await db.execute(_plr_sql(LOG_META_SQL), {"id": rid})).mappings().first()
    if meta is None:
        _plr_refuse(_plr.REPORT_NOT_FOUND)
    refusal = _plr.log_refusal(True, bool(meta["log_stored"]), meta["created_at"],
                                meta["closed_at"], meta["now"])
    if refusal is not None:
        _plr_refuse(refusal)
    gz = (await db.execute(_plr_sql(LOG_GZ_SQL), {"id": rid})).scalar()
    if gz is None:
        _plr_refuse(_plr.NO_LOG)
    al = main._auto_logs
    await al._end_transaction(db)                  # no connection held while the pool works
    try:
        body = await al._hop(al._CPU_POOL, al.AUTO_LOG_CPU_WAIT_S, _plr.unpack_log, bytes(gz))
        body, counts = await main._scrub_bug_log(db, body)
    except TimeoutError:
        print(f"[PLAYER-REPORT] log of {rid} was not ready within {al.AUTO_LOG_CPU_WAIT_S}s")
        raise _PlrHttpError(503, "Log read unavailable")
    except ValueError as ex:
        raise _PlrHttpError(413, str(ex))
    print(f"[PLAYER-REPORT] log of {rid} downloaded by {admin_steam_id} ({len(body)} chars; "
          f"redacted credential={counts['credential']})")
    disposition = f'attachment; filename="player-report-{rid}.log"'
    return _PlrPlainText(content=body, headers={
        "Content-Disposition": disposition,
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Scrub-Version": main._BUG_LOG_SCRUB_VERSION,
    })


@plr_router.post("/api/v1/admin/player-reports/{report_id}/close")
async def admin_close_player_report(
    report_id: str,
    req: PlayerReportCloseRequest,
    db: _PlrDb = _plr_depends(_plr_get_db),
):
    """Admin: close an open report as dismissed or actioned, with an optional
    note. The signature names the report and the verdict. Nothing else
    happens: no sanction is applied and nobody is told."""
    import main
    if main.IS_REPLICA:
        main._replica_skip("player_report_close")
        raise _PlrHttpError(status_code=503, detail={"error": "read_replica"})
    await _admin(db, req.admin_steam_id, _plr.ACTION_CLOSE,
                 _plr.close_target(report_id, req.verdict), req.hmac_signature)
    rid = _report_id(report_id)
    parsed, refusal = _plr.parse_close(req.verdict, req.note)
    if refusal is not None:
        _plr_refuse(refusal)
    verdict, note = parsed
    admin_id = (await db.execute(_plr_sql(PLAYER_SQL), {"s": req.admin_steam_id})).scalar()
    closed = (await db.execute(_plr_sql(CLOSE_SQL), {
        "id": rid, "v": verdict, "adm": admin_id, "n": note})).first()
    if closed is None:
        status = (await db.execute(_plr_sql(STATUS_SQL), {"id": rid})).scalar()
        _plr_refuse(_plr.close_refusal(status) or _plr.ALREADY_CLOSED)
    await db.execute(_plr_sql(RETENTION_SQL))
    await db.commit()
    return {"ok": True, "status": verdict}
