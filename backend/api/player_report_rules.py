"""Ask 14 (the player report form): every decision of the five player-report
routes, as pure functions over facts. Standard library and log_redaction only;
player_reports.py gathers the facts, calls these and writes.

WHAT A REPORT IS. One account (the reporter) names one of its own recent games,
one other player of that game, a reason from a closed list, optional text and
optionally its log. The reporter is the account of the request's verified
session and is never read from the body.

THE ORDER IS PART OF THE RULE. POST /api/v1/player-reports decides in this
order, and each refusal below carries the status and the code the route
answers with:

  1  session    401 session_required     no verified session
  2  switch     503 player_reports_off   runtime_settings player_reports_accept is not '1'
  3  size       413 body_too_large       a declared or an actual body over BODY_MAX
                400 bad_length           a Content-Length that is not a number
  4  shape      422 <field code>         parse_submit
  5  player     403 no_player            the session's account has no live players row
  6  game       404 game_not_found       not one of the reporter's own listed games
  7  reported   422 player_not_in_game   not another player of that game
  8  duplicate  409 already_reported     this reporter, game and player once before
  9  limit      429 report_limit         REPORTS_PER_DAY reports in the last 24 hours

Rules 1 to 3 need no body and are decided before one is read (pre_body_refusal).
Rules 5 to 9 are decided twice by the same function (decide_submit): once before the
log is compressed, so a refused report costs no compression, and once under the
identity locks, where the answer is final.

RULES 6 AND 7 READ THE LIST THE FORM WAS GIVEN. GET /api/v1/player-reports/games
and the submit run the same statement and fold its rows with fold_games, so a
game or a player the form never offered is refused, and one answer
(game_not_found) covers a game that does not exist, is another account's, is
older than the window, was invalidated or has fallen out of the list.

LOG RETENTION IS A RULE OF THE READERS (log_readable): the log route and the
list's has_log both apply it, so a log past its day is not served whether or
not its row has been deleted yet.
"""

import datetime as _plr_dt
import gzip as _plr_gzip
import uuid as _plr_uuid
import zlib as _zlib

import log_redaction as _plr_redact

GAME_KINDS = ("1v1", "2v2", "1v2", "ffa")
REASONS = ("cheating", "harassment", "griefing", "leaving", "name", "other")
REASON_NEEDS_DETAILS = "other"
REPORT_STATUSES = ("open", "dismissed", "actioned")
VERDICTS = ("dismissed", "actioned")

SWITCH_KEY = "player_reports_accept"
SWITCH_ON = "1"

BODY_MAX = 8 * 1024 * 1024        # bytes of request body, declared or read
DETAILS_MAX = 1000                # characters stored (the migration's CHECK)
NOTE_MAX = 500                    # characters of an admin's closing note (the migration's CHECK)
STEAM_ID_MAX = 20                 # players.steam_id is VARCHAR(20)
LOG_MAX_CHARS = 3_500_000         # the tail kept; the client's own cap (BUG_REPORT_LOG_CAP_CHARS)
LOG_GZ_MAX = 4_000_000            # bytes stored (the migration's CHECK)
GAME_WINDOW_DAYS = 14
GAME_LIST_MAX = 25
REPORTS_PER_DAY = 5
OPEN_LOG_DAYS = 90
CLOSED_LOG_DAYS = 30
REPORTED_COUNT_DAYS = 30

# The admin signature's action word per route, in the form of the bug-report
# routes (bug_reports, bug_reports_log, bug_reports_status): one word per
# route, so a signature made for one never verifies for another.
ACTION_LIST = "player_reports"
ACTION_LOG = "player_reports_log"
ACTION_CLOSE = "player_reports_close"
TARGET_LIST = "list"


def close_target(report_id, verdict) -> str:
    """The close signature names the report AND the verdict it closes with."""
    return "%s:%s" % (report_id, verdict)


class ReportRefusal:
    """What a route answers instead of acting: an HTTP status and a code."""
    __slots__ = ("status", "code")

    def __init__(self, status: int, code: str):
        self.status, self.code = status, code

    def __repr__(self):
        return "ReportRefusal(%d, %r)" % (self.status, self.code)

    def __eq__(self, other):
        return isinstance(other, ReportRefusal) and (self.status, self.code) == (other.status, other.code)

    def __hash__(self):
        return hash((self.status, self.code))


SESSION_REQUIRED = ReportRefusal(401, "session_required")
REPORTS_OFF = ReportRefusal(503, "player_reports_off")
BAD_LENGTH = ReportRefusal(400, "bad_length")
BODY_TOO_LARGE = ReportRefusal(413, "body_too_large")
NO_PLAYER = ReportRefusal(403, "no_player")
GAME_NOT_FOUND = ReportRefusal(404, "game_not_found")
PLAYER_NOT_IN_GAME = ReportRefusal(422, "player_not_in_game")
ALREADY_REPORTED = ReportRefusal(409, "already_reported")
REPORT_LIMIT = ReportRefusal(429, "report_limit")
REPORT_NOT_FOUND = ReportRefusal(404, "report_not_found")
ALREADY_CLOSED = ReportRefusal(409, "already_closed")
NO_LOG = ReportRefusal(404, "no_log")


def _plr_key(value) -> str:
    """Ids compare as lower-case text: a uuid object, an asyncpg uuid and a
    string of the same id are one id."""
    return str(value).lower()


# -- rules 1 to 3: decided before a body is read ------------------------------

def session_refusal(session_steam_id, verified):
    """Rule 1. `session_steam_id` is the account the request's session names
    (None when it names none); `verified` is whether that session is known,
    unexpired and Steam-verified for that account."""
    if not session_steam_id or verified is not True:
        return SESSION_REQUIRED
    return None


def switch_refusal(value):
    """Rule 2. Only the exact value '1' is ON: a missing row (None), '0' and
    any other text are OFF."""
    return None if value == SWITCH_ON else REPORTS_OFF


def length_refusal(declared):
    """Rule 3 over the Content-Length header (None when absent)."""
    if declared is None:
        return None
    try:
        n = int(declared)
    except (TypeError, ValueError):
        return BAD_LENGTH
    if n < 0:
        return BAD_LENGTH
    return BODY_TOO_LARGE if n > BODY_MAX else None


def size_refusal(read_bytes: int):
    """Rule 3 over the bytes actually read so far."""
    return BODY_TOO_LARGE if read_bytes > BODY_MAX else None


def pre_body_refusal(session_steam_id, verified, switch_value, declared_length):
    """Rules 1 to 3 in order, from facts that need no body."""
    return (session_refusal(session_steam_id, verified)
            or switch_refusal(switch_value)
            or length_refusal(declared_length))


# -- rule 4: the body's shape ---------------------------------------------------

DETAILS_SENT_MAX = 4 * DETAILS_MAX   # as sent; over it the body is refused, never cut before the credential rule
NOTE_SENT_MAX = 4 * NOTE_MAX


class ReportSubmit:
    """A body that passed rule 4. It has no reporter: the route takes that
    from the session and from nowhere else."""
    __slots__ = ("game_kind", "game_id", "reported_steam_id", "reason", "details", "log_text")

    def __init__(self, game_kind, game_id, reported_steam_id, reason, details, log_text):
        self.game_kind, self.game_id = game_kind, game_id
        self.reported_steam_id, self.reason = reported_steam_id, reason
        self.details, self.log_text = details, log_text


def clean_text(value: str, keep: int) -> str:
    """Free text as stored: the credential rule over the text as sent, then NUL
    removed (a TEXT column cannot hold it) and outer whitespace trimmed, then
    the head kept. The rule runs first, so a credential that straddles the cut
    is never stored in part."""
    text = _plr_redact.redact_credentials(value)
    return text.replace("\x00", "").strip()[:keep]


def parse_submit(obj):
    """Rule 4. Returns (ReportSubmit, None), or (None, ReportRefusal(422, code)) naming the
    first field that is wrong. Keys the form does not send are ignored, so a
    body that names a reporter changes nothing."""
    if not isinstance(obj, dict):
        return None, ReportRefusal(422, "bad_body")
    kind = obj.get("game_kind")
    if not isinstance(kind, str) or kind not in GAME_KINDS:
        return None, ReportRefusal(422, "bad_game_kind")
    raw_id = obj.get("game_id")
    if not isinstance(raw_id, str):
        return None, ReportRefusal(422, "bad_game_id")
    try:
        game_id = _plr_uuid.UUID(raw_id)
    except (ValueError, AttributeError, TypeError):
        return None, ReportRefusal(422, "bad_game_id")
    steam = obj.get("reported_steam_id")
    if not isinstance(steam, str) or not 1 <= len(steam) <= STEAM_ID_MAX:
        return None, ReportRefusal(422, "bad_player")
    reason = obj.get("reason")
    if not isinstance(reason, str) or reason not in REASONS:
        return None, ReportRefusal(422, "bad_reason")
    details = obj.get("details")
    if details is None:
        details = ""
    if not isinstance(details, str):
        return None, ReportRefusal(422, "bad_details")
    if len(details) > DETAILS_SENT_MAX:
        return None, ReportRefusal(422, "details_too_long")
    details = clean_text(details, DETAILS_MAX)
    if reason == REASON_NEEDS_DETAILS and not details:
        return None, ReportRefusal(422, "details_required")
    log_text = obj.get("log_text")
    if log_text is None:
        log_text = ""
    if not isinstance(log_text, str):
        return None, ReportRefusal(422, "bad_log")
    return ReportSubmit(kind, game_id, steam, reason, details, log_text), None


# -- rules 6 and 7: the reporter's own listed games -------------------------------

class ListedPlayer:
    __slots__ = ("player_id", "steam_id", "name")

    def __init__(self, player_id, steam_id, name):
        self.player_id, self.steam_id, self.name = player_id, steam_id, name


class ListedGame:
    __slots__ = ("kind", "game_id", "ended_at", "others")

    def __init__(self, kind, game_id, ended_at, others):
        self.kind, self.game_id, self.ended_at, self.others = kind, game_id, ended_at, others


def fold_games(rows, reporter_id):
    """The games statement's rows, in its order, as the list both player
    routes use. A row is (kind, game_id, ended_at, player_id, steam_id,
    display_name): one per live player of each listed game.

    A game is kept when the reporter is one of its rows AND at least one other
    player is; `others` never holds the reporter. So the reporter's own part in
    the game is established here from the rows, whatever the statement's WHERE
    says, and a game with nobody left to report is not offered."""
    me = _plr_key(reporter_id)
    order, mine, games = [], set(), {}
    for kind, game_id, ended_at, player_id, steam_id, display_name in rows:
        k = (kind, _plr_key(game_id))
        game = games.get(k)
        if game is None:
            game = games[k] = ListedGame(kind, game_id, ended_at, [])
            order.append(k)
        if _plr_key(player_id) == me:
            mine.add(k)
        else:
            game.others.append(ListedPlayer(player_id, steam_id, display_name or steam_id))
    kept = [games[k] for k in order if k[0] in GAME_KINDS and k in mine and games[k].others]
    return kept[:GAME_LIST_MAX]


def find_game(games, kind, game_id):
    """Rule 6: the listed game of that kind and id, or None."""
    wanted = (kind, _plr_key(game_id))
    for game in games:
        if (game.kind, _plr_key(game.game_id)) == wanted:
            return game
    return None


def find_player(game, steam_id):
    """Rule 7: the other player of `game` with that Steam id, or None. The
    reporter is never in `others`, so an account cannot report itself."""
    if game is None:
        return None
    for player in game.others:
        if player.steam_id == steam_id:
            return player
    return None


# -- rules 5 to 9, in order ------------------------------------------------------

def decide_submit(reporter_id, game, reported, duplicate, recent):
    """None when the report is accepted, else the refusal of the FIRST rule
    that does not hold. `reporter_id` is the players row of the session's
    account (None when there is none); `game` and `reported` are find_game's
    and find_player's answers; `duplicate` is whether this reporter already
    reported this player for this game; `recent` counts the reporter's reports
    of the last 24 hours."""
    if reporter_id is None:
        return NO_PLAYER
    if game is None:
        return GAME_NOT_FOUND
    if reported is None:
        return PLAYER_NOT_IN_GAME
    if duplicate:
        return ALREADY_REPORTED
    if recent >= REPORTS_PER_DAY:
        return REPORT_LIMIT
    return None


# -- what the games route answers ------------------------------------------------

def utc_stamp(ts) -> str:
    """A timestamp as UTC text to the second, the form the client parses."""
    return ts.astimezone(_plr_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def report_key(kind, game_id, reported_id) -> tuple:
    return (kind, _plr_key(game_id), _plr_key(reported_id))


def games_payload(games, reported_keys, recent) -> dict:
    """The caller's own listed games with each game's other players.
    `reported_keys` holds report_key(...) of the caller's own earlier reports,
    so the form can close Send for a player it already reported, and
    `remaining` is what is left of the caller's 24 hour limit: both let the
    form refuse locally instead of sending a request the server would refuse."""
    out = []
    for game in games:
        out.append({
            "kind": game.kind,
            "id": _plr_key(game.game_id),
            "ended_at": utc_stamp(game.ended_at),
            "others": [{"steam_id": p.steam_id, "name": p.name,
                         "reported": report_key(game.kind, game.game_id, p.player_id) in reported_keys}
                        for p in game.others],
        })
    return {"games": out, "remaining": max(0, REPORTS_PER_DAY - int(recent))}


# -- the attached log ------------------------------------------------------------

def prepare_log(log_text: str):
    """The log as stored: the credential rule over the text as sent, then the
    TAIL kept (a log's recent lines are the ones a report is about), then
    gzip. Returns (gz, raw_chars); gz is None when the result is over
    LOG_GZ_MAX, and the report is then stored without a log. Blocking: the
    route drives it on the auto-log CPU pool with a ceiling."""
    text = _plr_redact.redact_credentials(log_text)
    if len(text) > LOG_MAX_CHARS:
        text = text[-LOG_MAX_CHARS:]
    data = _plr_gzip.compress(text.encode("utf-8", errors="replace"), compresslevel=6)
    if len(data) > LOG_GZ_MAX:
        return None, len(text)
    return data, len(text)


_LOG_UNPACK_MAX = 4 * LOG_MAX_CHARS + 1024     # bytes: UTF-8 spends at most four per character


def unpack_log(gz: bytes) -> str:
    """A stored log as text. The output is bounded: what prepare_log wrote
    never exceeds the bound, and a row that would is refused, not expanded."""
    d = _zlib.decompressobj(16 + _zlib.MAX_WBITS)
    raw = d.decompress(bytes(gz), _LOG_UNPACK_MAX)
    if d.unconsumed_tail:
        raise ValueError("stored log expands past %d bytes" % _LOG_UNPACK_MAX)
    return raw.decode("utf-8", errors="replace")


def log_readable(created_at, closed_at, now) -> bool:
    """Whether a report's log may still be served at `now`.

    Open: until OPEN_LOG_DAYS after filing. Closed: until CLOSED_LOG_DAYS after
    closing, provided it was closed while its log was still readable. The
    second condition makes the bound one-way: a log that passed its day while
    the report was open does not become readable again when the report is
    closed later. Each bound is exclusive: at the bound itself the answer is
    False."""
    open_end = created_at + _plr_dt.timedelta(days=OPEN_LOG_DAYS)
    if closed_at is None:
        return now < open_end
    return closed_at < open_end and now < closed_at + _plr_dt.timedelta(days=CLOSED_LOG_DAYS)


# -- the admin routes ------------------------------------------------------------

def parse_close(verdict, note):
    """((verdict, note), None), or (None, ReportRefusal). The note is optional free
    text, stored as clean_text leaves it."""
    if not isinstance(verdict, str) or verdict not in VERDICTS:
        return None, ReportRefusal(422, "bad_verdict")
    if note is None:
        note = ""
    if not isinstance(note, str):
        return None, ReportRefusal(422, "bad_note")
    if len(note) > NOTE_SENT_MAX:
        return None, ReportRefusal(422, "note_too_long")
    return (verdict, clean_text(note, NOTE_MAX)), None


def close_refusal(current_status):
    """Closing needs a report that exists (None when it does not) and is open."""
    if current_status is None:
        return REPORT_NOT_FOUND
    if current_status != "open":
        return ALREADY_CLOSED
    return None


def log_refusal(found: bool, log_stored: bool, created_at, closed_at, now):
    """The log route: the report exists, a log row exists and it is still
    readable. A log past its day answers exactly as a report that never had
    one."""
    if not found:
        return REPORT_NOT_FOUND
    if not log_stored or not log_readable(created_at, closed_at, now):
        return NO_LOG
    return None


def list_row(r, now) -> dict:
    """One row of the admin list from the list statement's columns. has_log
    applies log_readable, so a log past its day reads as no log here whether
    or not its row is still stored."""
    return {
        "id": _plr_key(r["id"]),
        "created_at": utc_stamp(r["created_at"]),
        "status": r["status"],
        "reason": r["reason"],
        "details": r["details"],
        "game_kind": r["game_kind"],
        "game_id": _plr_key(r["game_id"]),
        "game_ended_at": utc_stamp(r["game_ended_at"]),
        # Flat keys: the client reads a row with a hand parser that looks a
        # key up by name, so no key of a row repeats inside a nested object.
        "reporter_steam_id": r["reporter_steam_id"],
        "reporter_name": r["reporter_name"] or r["reporter_steam_id"],
        "reported_steam_id": r["reported_steam_id"],
        "reported_name": r["reported_name"] or r["reported_steam_id"],
        "reporters_30d": int(r["reporters_30d"] or 0),
        "has_log": bool(r["log_stored"]) and log_readable(r["created_at"], r["closed_at"], now),
        "closed_at": utc_stamp(r["closed_at"]) if r["closed_at"] is not None else None,
        "closed_by": r["closed_by_name"] or None,
        "close_note": r["close_note"] or "",
    }
