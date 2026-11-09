"""Ask 14 (the player report form): the rules of the five player-report routes,
with no database.

Every claim is a function over the lane's sources that raises AssertionError
when the claim is false, and runs three ways (the family of test_admin_menu.py):
against the tree (must pass), against an in-memory MUTATION of the tree (must
turn red on the claim's own assertion, never on a parse failure or another
exception) and against an in-memory CONTROL edit (must stay green). So a claim
that cannot fail, or that fails on any edit at all, is caught here.

Two families:
  rules    behaviour of backend/api/player_report_rules.py, loaded from the
           (possibly mutated) source text: the nine rules of the submit and
           their order, the games fold, the log's storage form, the retention
           rule and the admin rules.
  source   what backend/api/player_reports.py, main.py, read_gate.py and the
           migration say: the order of the submit's steps, which handlers
           write, the admin checks, the route census, the closed lists.

What the statements DO on a database is test_player_reports_pg.py's.
"""

import ast
import io
import os
import re
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, ".."))
API = os.path.join(BACKEND, "api")
SQL = os.path.join(BACKEND, "sql")
sys.path.insert(0, API)

FILES = {"RULES": "player_report_rules.py", "ROUTES": "player_reports.py",
         "MAIN": "main.py", "GATE": "read_gate.py"}
PATHS = ("/api/v1/player-reports", "/api/v1/player-reports/games",
         "/api/v1/admin/player-reports", "/api/v1/admin/player-reports/{report_id}/log",
         "/api/v1/admin/player-reports/{report_id}/close")

_CACHE = {}


def _migration():
    ups = sorted(f for f in os.listdir(SQL) if re.match(r"^\d{3}_player_reports\.sql$", f))
    assert len(ups) == 1, ups
    return ups[0], "rollback_" + ups[0]


def _read(path):
    return io.open(path, encoding="utf-8", newline="").read().replace("\r\n", "\n")


def _tree():
    if not _CACHE:
        for key, name in FILES.items():
            _CACHE[key] = _read(os.path.join(API, name))
        up, down = _migration()
        _CACHE["UP"], _CACHE["DOWN"] = _read(os.path.join(SQL, up)), _read(os.path.join(SQL, down))
    return dict(_CACHE)


def _rules(src):
    """The rules module as `src` has it, loaded under a name of its own."""
    mod = types.ModuleType("player_report_rules_case")
    exec(compile(src["RULES"], FILES["RULES"], "exec"), mod.__dict__)
    return mod


def _replace(src, key, old, new):
    assert src[key].count(old) == 1, (key, src[key].count(old), old[:60])
    out = dict(src)
    out[key] = src[key].replace(old, new)
    return out


def _control(key, anchor):
    """A neutral edit: a comment line put before a line that starts with `anchor`."""
    return lambda s: _replace(s, key, "\n" + anchor, "\n# control\n" + anchor)


def _check(claim, mutation, control):
    """The three-way run. A mutant that no longer parses, or that makes the
    claim raise anything but AssertionError, is not the mutation's red."""
    src = _tree()
    claim(src)
    m = mutation(src)
    assert m != src, "the mutation changed nothing"
    for key in ("RULES", "ROUTES"):
        if m[key] != src[key]:
            try:
                compile(m[key], FILES[key], "exec")
            except SyntaxError as e:
                raise AssertionError("the mutation broke parsing instead of the claim: %s" % e)
    try:
        claim(m)
    except AssertionError:
        pass
    except Exception as e:                                   # noqa: BLE001
        raise AssertionError("the mutation raised %s instead of reddening the claim: %s"
                             % (type(e).__name__, e))
    else:
        raise AssertionError("the mutation STAYED GREEN")
    c = control(src)
    assert c != src, "the control changed nothing"
    claim(c)


def _fn(text, name):
    """The source of the module-level function `name`, decorators included."""
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            return "\n".join(text.split("\n")[first - 1:node.end_lineno])
    raise AssertionError("no function %s" % name)


def _main_fn(text, name):
    """The same for main.py, by column-0 boundaries (parsing it is slow)."""
    m = re.search(r"^async def %s\(" % re.escape(name), text, re.M)
    assert m, name
    end = re.search(r"^(?:@app\.|@router\.|async def |def |class )", text[m.end():], re.M)
    return text[m.start():m.end() + (end.start() if end else len(text))]


def _order(body, *needles):
    """Each needle occurs, each after the one before it."""
    pos = -1
    for n in needles:
        i = body.find(n, pos + 1)
        assert i > pos, "%r is missing after offset %d (order: %r)" % (n, pos, needles)
        pos = i


def _sample(R):
    """Three accounts and three games' rows as the games statement returns them."""
    me, ann, bo = uuid.UUID(int=1), uuid.UUID(int=2), uuid.UUID(int=3)
    t0 = datetime(2026, 11, 9, 3, 0, 0, tzinfo=timezone.utc)
    mine, theirs, alone = uuid.UUID(int=11), uuid.UUID(int=12), uuid.UUID(int=13)
    rows = [("2v2", mine, t0, me, "S_ME", "Me"), ("2v2", mine, t0, ann, "S_ANN", "Ann"),
            ("2v2", mine, t0, bo, "S_BO", ""),
            ("1v1", theirs, t0, ann, "S_ANN", "Ann"), ("1v1", theirs, t0, bo, "S_BO", "Bo"),
            ("ffa", alone, t0, me, "S_ME", "Me")]
    games = R.fold_games(rows, me)
    return types.SimpleNamespace(me=me, ann=ann, bo=bo, t0=t0, mine=mine, theirs=theirs,
                                 alone=alone, rows=rows, games=games)


OK_BODY = {"game_kind": "2v2", "game_id": str(uuid.UUID(int=11)),
           "reported_steam_id": "S_ANN", "reason": "griefing"}
TICKET = "Session Ticket: " + "AB12" * 16          # the credential rule's own shape, 64 hex


# -- rules 1 to 3: decided from facts that need no body --------------------------

def _r1(src):
    R = _rules(src)
    for steam, verified in ((None, False), ("", True), ("S_ME", False), ("S_ME", None), ("S_ME", 1)):
        assert R.pre_body_refusal(steam, verified, "1", None) == R.SESSION_REQUIRED, (steam, verified)
    assert R.pre_body_refusal("S_ME", True, "1", None) is None
    assert (R.SESSION_REQUIRED.status, R.SESSION_REQUIRED.code) == (401, "session_required")


def test_r1_a_report_needs_a_verified_session():
    _check(_r1,
           lambda s: _replace(s, "RULES", "if not session_steam_id or verified is not True:",
                              "if not session_steam_id:"),
           _control("RULES", "def session_refusal("))


def _r2(src):
    R = _rules(src)
    for value in (None, "0", "", "true", "on", "11", " 1"):
        assert R.switch_refusal(value) == R.REPORTS_OFF, value
    assert R.switch_refusal("1") is None
    assert (R.REPORTS_OFF.status, R.REPORTS_OFF.code) == (503, "player_reports_off")


def test_r2_only_the_value_1_is_on_and_a_missing_row_is_off():
    _check(_r2,
           lambda s: _replace(s, "RULES", "return None if value == SWITCH_ON else REPORTS_OFF",
                              'return REPORTS_OFF if value == "0" else None'),
           _control("RULES", "def switch_refusal("))


def _r3(src):
    R = _rules(src)
    assert R.length_refusal(None) is None and R.length_refusal(str(R.BODY_MAX)) is None
    assert R.length_refusal(str(R.BODY_MAX + 1)) == R.BODY_TOO_LARGE
    assert R.length_refusal("eight") == R.BAD_LENGTH and R.length_refusal("-1") == R.BAD_LENGTH
    assert R.size_refusal(R.BODY_MAX) is None and R.size_refusal(R.BODY_MAX + 1) == R.BODY_TOO_LARGE
    assert R.BODY_MAX == 8 * 1024 * 1024 and R.BODY_TOO_LARGE.status == 413


def test_r3_a_body_over_the_ceiling_is_refused_declared_or_read():
    _check(_r3,
           lambda s: _replace(s, "RULES", "    return BODY_TOO_LARGE if read_bytes > BODY_MAX else None",
                              "    return None"),
           _control("RULES", "def size_refusal("))


def _r123_order(src):
    R = _rules(src)
    huge = str(R.BODY_MAX * 4)
    assert R.pre_body_refusal(None, False, "0", huge) == R.SESSION_REQUIRED
    assert R.pre_body_refusal("S_ME", True, "0", huge) == R.REPORTS_OFF
    assert R.pre_body_refusal("S_ME", True, "1", huge) == R.BODY_TOO_LARGE


def test_r123_the_session_is_decided_before_the_switch_and_the_switch_before_the_size():
    _check(_r123_order,
           lambda s: _replace(s, "RULES",
                              "    return (session_refusal(session_steam_id, verified)\n"
                              "            or switch_refusal(switch_value)\n",
                              "    return (switch_refusal(switch_value)\n"
                              "            or session_refusal(session_steam_id, verified)\n"),
           _control("RULES", "def pre_body_refusal("))


# -- rule 4: the body's shape -----------------------------------------------------

BS = chr(92)        # one backslash, to quote the rules file's NUL escape as its source spells it
NUL_ESC = BS + "x00"


def _r4_lists(src):
    R = _rules(src)
    sub, refusal = R.parse_submit(dict(OK_BODY))
    assert refusal is None and (sub.game_kind, sub.reason, sub.details, sub.log_text) == ("2v2", "griefing", "", "")
    assert sub.game_id == uuid.UUID(int=11) and sub.reported_steam_id == "S_ANN"
    cases = (({"game_kind": "3v3"}, "bad_game_kind"), ({"game_kind": None}, "bad_game_kind"),
             ({"game_id": "not-an-id"}, "bad_game_id"), ({"game_id": 11}, "bad_game_id"),
             ({"reported_steam_id": ""}, "bad_player"), ({"reported_steam_id": "7" * 21}, "bad_player"),
             ({"reported_steam_id": 7}, "bad_player"),
             ({"reason": "rude"}, "bad_reason"), ({"reason": ["other"]}, "bad_reason"),
             ({"details": 5}, "bad_details"), ({"details": "x" * (4 * R.DETAILS_MAX + 1)}, "details_too_long"),
             ({"log_text": {"a": 1}}, "bad_log"))
    for patch, code in cases:
        got = R.parse_submit(dict(OK_BODY, **patch))
        assert got == (None, R.ReportRefusal(422, code)), (patch, got)
    for body in (None, [], "x", 5):
        assert R.parse_submit(body) == (None, R.ReportRefusal(422, "bad_body")), body
    assert R.GAME_KINDS == ("1v1", "2v2", "1v2", "ffa")
    assert R.REASONS == ("cheating", "harassment", "griefing", "leaving", "name", "other")


def test_r4_the_closed_lists_and_field_types_are_enforced():
    _check(_r4_lists,
           lambda s: _replace(s, "RULES", "if not isinstance(reason, str) or reason not in REASONS:",
                              "if not isinstance(reason, str):"),
           _control("RULES", "def parse_submit("))


def _r4_other(src):
    R = _rules(src)
    for details in (None, "", "   ", " " + chr(0) + " " + chr(10)):
        got = R.parse_submit(dict(OK_BODY, reason="other", details=details))
        assert got == (None, R.ReportRefusal(422, "details_required")), (details, got)
    sub, refusal = R.parse_submit(dict(OK_BODY, reason="other", details=" kept leaving "))
    assert refusal is None and sub.details == "kept leaving"
    assert R.parse_submit(dict(OK_BODY, reason="leaving"))[1] is None      # only `other` needs text


def test_r4_the_reason_other_needs_details_that_survive_cleaning():
    _check(_r4_other,
           lambda s: _replace(s, "RULES", "    if reason == REASON_NEEDS_DETAILS and not details:",
                              "    if reason == REASON_NEEDS_DETAILS and details is None:"),
           _control("RULES", "def clean_text("))


def _r4_clean(src):
    R = _rules(src)
    # 960 characters, then a credential whose value crosses the 1000th character.
    sub, refusal = R.parse_submit(dict(OK_BODY, details="d" * 960 + TICKET + " tail"))
    assert refusal is None and len(sub.details) <= R.DETAILS_MAX == 1000
    assert "AB12" not in sub.details, "part of a credential was stored: %r" % sub.details[-60:]
    sub, _ = R.parse_submit(dict(OK_BODY, details="a" + chr(0) + "b"))
    assert sub.details == "ab"


def test_r4_free_text_passes_the_credential_rule_before_it_is_cut():
    _check(_r4_clean,
           lambda s: _replace(s, "RULES",
                              "    text = _plr_redact.redact_credentials(value)\n"
                              '    return text.replace("' + NUL_ESC + '", "").strip()[:keep]',
                              '    return _plr_redact.redact_credentials(value.replace("' + NUL_ESC
                              + '", "").strip()[:keep])'),
           _control("RULES", "def clean_text("))


def _r4_no_reporter(src):
    R = _rules(src)
    assert tuple(R.ReportSubmit.__slots__) == ("game_kind", "game_id", "reported_steam_id", "reason",
                                         "details", "log_text")
    sub, refusal = R.parse_submit(dict(OK_BODY, reporter_steam_id="S_BO", steam_id="S_BO", reporter="S_BO"))
    assert refusal is None
    assert not [a for a in dir(sub) if "reporter" in a], "a parsed body carries a reporter"
    assert "S_BO" not in [getattr(sub, a) for a in R.ReportSubmit.__slots__]


def test_r4_a_parsed_body_carries_no_reporter():
    _check(_r4_no_reporter,
           lambda s: _replace(s, "RULES",
                              '    __slots__ = ("game_kind", "game_id", "reported_steam_id", "reason", "details", "log_text")',
                              '    __slots__ = ("game_kind", "game_id", "reported_steam_id", "reason", "details", "log_text",\n'
                              '                 "reporter_steam_id")'),
           _control("RULES", "class ReportSubmit:"))


# -- rules 5 to 9 -----------------------------------------------------------------

def _r5(src):
    R = _rules(src)
    x = _sample(R)
    game = x.games[0]
    assert R.decide_submit(None, game, game.others[0], False, 0) == R.NO_PLAYER
    assert (R.NO_PLAYER.status, R.NO_PLAYER.code) == (403, "no_player")
    assert R.decide_submit(x.me, game, game.others[0], False, 0) is None


def test_r5_the_sessions_account_needs_a_players_row():
    _check(_r5,
           lambda s: _replace(s, "RULES", "    if reporter_id is None:\n        return NO_PLAYER\n", ""),
           _control("RULES", "def decide_submit("))


def _r6_unknown(src):
    R = _rules(src)
    x = _sample(R)
    assert R.find_game(x.games, "2v2", x.mine) is x.games[0]
    assert R.find_game(x.games, "2v2", str(x.mine).upper()) is x.games[0]      # one id, however it is spelled
    assert R.find_game(x.games, "2v2", uuid.UUID(int=99)) is None               # an id nobody listed
    assert R.find_game(x.games, "1v1", x.mine) is None                          # a listed id under another kind
    assert R.find_game([], "2v2", x.mine) is None
    assert R.decide_submit(x.me, None, None, False, 0) == R.GAME_NOT_FOUND
    assert (R.GAME_NOT_FOUND.status, R.GAME_NOT_FOUND.code) == (404, "game_not_found")


def test_r6_a_game_that_is_not_listed_is_not_found():
    _check(_r6_unknown,
           lambda s: _replace(s, "RULES", "        if (game.kind, _plr_key(game.game_id)) == wanted:",
                              "        if _plr_key(game.game_id) == wanted[1]:"),
           _control("RULES", "def find_game("))


def _r6_anothers(src):
    R = _rules(src)
    x = _sample(R)
    kept = [(g.kind, g.game_id) for g in x.games]
    assert kept == [("2v2", x.mine)], kept           # `theirs` has no row of the reporter; `alone` has nobody else
    assert R.find_game(x.games, "1v1", x.theirs) is None
    assert R.fold_games(x.rows, uuid.UUID(int=77)) == []                        # an account in none of the rows


def test_r6_a_game_the_reporter_took_no_part_in_is_not_listed():
    _check(_r6_anothers,
           lambda s: _replace(s, "RULES", "if k[0] in GAME_KINDS and k in mine and games[k].others]",
                              "if k[0] in GAME_KINDS and games[k].others]"),
           _control("RULES", "def fold_games("))


def _r7(src):
    R = _rules(src)
    x = _sample(R)
    game = x.games[0]
    assert [(p.steam_id, p.name) for p in game.others] == [("S_ANN", "Ann"), ("S_BO", "S_BO")]
    assert R.find_player(game, "S_ANN").player_id == x.ann
    assert R.find_player(game, "S_ME") is None, "the reporter is offered as a player to report"
    assert R.find_player(game, "S_NOBODY") is None and R.find_player(None, "S_ANN") is None
    assert R.decide_submit(x.me, game, None, False, 0) == R.PLAYER_NOT_IN_GAME
    assert (R.PLAYER_NOT_IN_GAME.status, R.PLAYER_NOT_IN_GAME.code) == (422, "player_not_in_game")


def test_r7_the_reported_player_is_another_player_of_that_game():
    _check(_r7,
           lambda s: _replace(s, "RULES",
                              "        if _plr_key(player_id) == me:\n            mine.add(k)\n        else:\n"
                              "            game.others.append(ListedPlayer(player_id, steam_id, display_name or steam_id))",
                              "        if _plr_key(player_id) == me:\n            mine.add(k)\n"
                              "        game.others.append(ListedPlayer(player_id, steam_id, display_name or steam_id))"),
           _control("RULES", "def find_player("))


def _r8_r9(src):
    R = _rules(src)
    x = _sample(R)
    game = x.games[0]
    who = game.others[0]
    assert R.decide_submit(x.me, game, who, True, 0) == R.ALREADY_REPORTED
    assert (R.ALREADY_REPORTED.status, R.ALREADY_REPORTED.code) == (409, "already_reported")
    assert R.REPORTS_PER_DAY == 5
    assert R.decide_submit(x.me, game, who, False, 4) is None                          # the fifth of a day
    assert R.decide_submit(x.me, game, who, False, 5) == R.REPORT_LIMIT                # the sixth
    assert (R.REPORT_LIMIT.status, R.REPORT_LIMIT.code) == (429, "report_limit")


def test_r8_r9_one_report_per_game_and_player_and_five_a_day():
    _check(_r8_r9,
           lambda s: _replace(s, "RULES", "    if recent >= REPORTS_PER_DAY:", "    if recent > REPORTS_PER_DAY:"),
           _control("RULES", "def decide_submit("))


def _r59_order(src):
    R = _rules(src)
    x = _sample(R)
    game = x.games[0]
    who = game.others[0]
    # Every later rule failing too: the answer is the FIRST rule's.
    assert R.decide_submit(None, None, None, True, 9) == R.NO_PLAYER
    assert R.decide_submit(x.me, None, None, True, 9) == R.GAME_NOT_FOUND
    assert R.decide_submit(x.me, game, None, True, 9) == R.PLAYER_NOT_IN_GAME
    assert R.decide_submit(x.me, game, who, True, 9) == R.ALREADY_REPORTED
    assert R.decide_submit(x.me, game, who, False, 9) == R.REPORT_LIMIT


def test_r59_the_duplicate_is_answered_before_the_limit_and_each_rule_in_its_turn():
    _check(_r59_order,
           lambda s: _replace(s, "RULES",
                              "    if duplicate:\n        return ALREADY_REPORTED\n"
                              "    if recent >= REPORTS_PER_DAY:\n        return REPORT_LIMIT\n",
                              "    if recent >= REPORTS_PER_DAY:\n        return REPORT_LIMIT\n"
                              "    if duplicate:\n        return ALREADY_REPORTED\n"),
           _control("RULES", "def decide_submit("))


def _payload(src):
    R = _rules(src)
    x = _sample(R)
    pay = R.games_payload(x.games, {R.report_key("2v2", x.mine, x.ann)}, 2)
    assert pay["remaining"] == 3 and R.games_payload([], set(), 9)["remaining"] == 0
    (game,) = pay["games"]
    assert (game["kind"], game["id"], game["ended_at"]) == ("2v2", str(x.mine), "2026-11-09T03:00:00Z")
    assert game["others"] == [{"steam_id": "S_ANN", "name": "Ann", "reported": True},
                               {"steam_id": "S_BO", "name": "S_BO", "reported": False}]
    assert "S_ME" not in repr(pay), "the caller is listed among the players to report"


def test_the_games_answer_marks_reported_players_and_never_goes_below_zero():
    _check(_payload,
           lambda s: _replace(s, "RULES", '"remaining": max(0, REPORTS_PER_DAY - int(recent))',
                              '"remaining": REPORTS_PER_DAY - int(recent)'),
           _control("RULES", "def games_payload("))


# -- the attached log and its retention -------------------------------------------

def _log_form(src):
    R = _rules(src)
    R.LOG_MAX_CHARS = 200                     # the module reads its bound when called
    head, last = "first line" + chr(10), "the last line"
    # The credential's value crosses the place the tail cut would fall.
    text = head + "x" * 400 + chr(10) + TICKET + chr(10) + "y" * 130 + chr(10) + last
    gz, raw_chars = R.prepare_log(text)
    back = R.unpack_log(gz)
    assert raw_chars == len(back) <= 200 and back.endswith(last) and "first line" not in back
    assert "AB12" not in back, "part of a credential was stored: %r" % back[:80]
    gz2, n2 = R.prepare_log("short " + TICKET)
    assert "AB12" not in R.unpack_log(gz2) and n2 == len(R.unpack_log(gz2))


def test_a_log_passes_the_credential_rule_then_keeps_its_tail():
    _check(_log_form,
           lambda s: _replace(s, "RULES",
                              "    text = _plr_redact.redact_credentials(log_text)\n"
                              "    if len(text) > LOG_MAX_CHARS:\n        text = text[-LOG_MAX_CHARS:]\n",
                              "    text = log_text\n"
                              "    if len(text) > LOG_MAX_CHARS:\n        text = text[-LOG_MAX_CHARS:]\n"
                              "    text = _plr_redact.redact_credentials(text)\n"),
           _control("RULES", "def prepare_log("))


def _log_caps(src):
    R = _rules(src)
    assert R.LOG_GZ_MAX == 4_000_000 and R.LOG_MAX_CHARS == 3_500_000
    R.LOG_GZ_MAX = 40
    gz, raw_chars = R.prepare_log("".join(chr(33 + (i * 7) % 90) for i in range(4000)))
    assert gz is None and raw_chars == 4000, "a log over its stored cap was returned for storage"
    R.LOG_GZ_MAX = 4_000_000
    big, _ = R.prepare_log("z" * 5000)
    R._LOG_UNPACK_MAX = 100
    try:
        R.unpack_log(big)
    except ValueError:
        pass
    else:
        raise AssertionError("a stored log was expanded past its bound")


def test_a_log_over_its_stored_cap_is_not_stored_and_a_read_is_bounded():
    _check(_log_caps,
           lambda s: _replace(s, "RULES", "    if len(data) > LOG_GZ_MAX:\n        return None, len(text)\n", ""),
           _control("RULES", "def unpack_log("))


def _retention(src):
    R = _rules(src)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    day, sec = timedelta(days=1), timedelta(seconds=1)
    assert (R.OPEN_LOG_DAYS, R.CLOSED_LOG_DAYS) == (90, 30)
    # open: readable until 90 days after filing, exclusive
    assert R.log_readable(t0, None, t0) and R.log_readable(t0, None, t0 + 90 * day - sec)
    assert not R.log_readable(t0, None, t0 + 90 * day)
    # closed while readable: until 30 days after closing, exclusive
    closed = t0 + 80 * day
    assert R.log_readable(t0, closed, closed + 30 * day - sec)
    assert not R.log_readable(t0, closed, closed + 30 * day)
    # closed after its open bound passed: closing does not bring the log back
    late = t0 + 95 * day
    assert not R.log_readable(t0, late, late + sec)
    assert not R.log_readable(t0, t0 + 90 * day, t0 + 90 * day + sec)


def test_c3_the_retention_bound_has_two_exclusive_edges_and_never_reopens():
    _check(_retention,
           lambda s: _replace(s, "RULES",
                              "    return closed_at < open_end and now < closed_at + _plr_dt.timedelta(days=CLOSED_LOG_DAYS)",
                              "    return now < closed_at + _plr_dt.timedelta(days=CLOSED_LOG_DAYS)"),
           _control("RULES", "def log_readable("))


def _spans(src):
    """Every span of the module's statements is an exact number of hours, so a
    bound is one instant in SQL and in log_readable's timedelta whatever the
    session's time zone is ('N days' is calendar arithmetic there)."""
    R = _rules(src)
    statements = _statements(src)
    for name, sql in sorted(statements.items()):
        for unit in re.findall(r"INTERVAL '[0-9]+ ([a-z]+)'", sql):
            assert unit == "hours", "%s holds a span in %s" % (name, unit)
        assert not re.search(r"INTERVAL '[^0-9]", sql), name
    flat = " ".join(statements["RETENTION_SQL"].split())
    spans = [int(n) for n in re.findall(r"[(]([0-9]+) [*] INTERVAL '24 hours'[)]", flat)]
    assert spans == [R.OPEN_LOG_DAYS, R.OPEN_LOG_DAYS, R.CLOSED_LOG_DAYS], spans
    assert flat.count("INTERVAL") == 3, flat


def test_c3_every_span_is_an_exact_number_of_hours():
    _check(_spans,
           lambda s: _replace(s, "ROUTES", "_DAYS = \"(%d * INTERVAL '24 hours')\"", "_DAYS = \"INTERVAL '%d days'\""),
           _control("ROUTES", "GAMES_SQL = "))


def _row(t0, **over):
    row = dict(id=uuid.UUID(int=21), created_at=t0, status="open", reason="other", details="d",
               game_kind="2v2", game_id=uuid.UUID(int=11), game_ended_at=t0,
               reporter_steam_id="S_ME", reporter_name="", reported_steam_id="S_ANN",
               reported_name="Ann", reporters_30d=None, log_stored=True, closed_at=None,
               closed_by_name=None, close_note="")
    row.update(over)
    return row


def _readers(src):
    R = _rules(src)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    past = t0 + timedelta(days=90)
    # the log route: one answer for no log row and for a log past its day
    assert R.log_refusal(False, True, t0, None, t0) == R.REPORT_NOT_FOUND
    assert R.log_refusal(True, False, t0, None, t0) == R.NO_LOG
    assert R.log_refusal(True, True, t0, None, past) == R.NO_LOG
    assert R.log_refusal(True, True, t0, None, t0) is None
    # the list: has_log is the stored row AND the bound
    assert R.list_row(_row(t0), t0)["has_log"] is True
    assert R.list_row(_row(t0), past)["has_log"] is False, "a log past its day is listed as present"
    assert R.list_row(_row(t0, log_stored=False), t0)["has_log"] is False
    row = R.list_row(_row(t0), t0)
    assert (row["reporter_steam_id"], row["reporter_name"]) == ("S_ME", "S_ME") and row["reporters_30d"] == 0
    assert (row["reported_steam_id"], row["reported_name"]) == ("S_ANN", "Ann")
    # A row is flat, and no key of it is the tail of another after a quote: the
    # client looks each key up by name in the row's text.
    assert not [k for k, v in row.items() if isinstance(v, (dict, list))], row
    assert row["closed_at"] is None and row["closed_by"] is None and row["id"] == str(uuid.UUID(int=21))


def test_c3_both_readers_apply_the_one_retention_rule():
    _check(_readers,
           lambda s: _replace(s, "RULES",
                              '        "has_log": bool(r["log_stored"]) and log_readable(r["created_at"], r["closed_at"], now),',
                              '        "has_log": bool(r["log_stored"]),'),
           _control("RULES", "def list_row("))


# -- the admin rules --------------------------------------------------------------

def _close(src):
    R = _rules(src)
    assert R.VERDICTS == ("dismissed", "actioned") and R.REPORT_STATUSES == ("open", "dismissed", "actioned")
    assert R.parse_close("actioned", None) == (("actioned", ""), None)
    assert R.parse_close("dismissed", " ok " + TICKET)[0][1].startswith("ok ")
    assert "AB12" not in R.parse_close("dismissed", TICKET)[0][1]
    for verdict in ("open", "closed", "", None, 1):
        assert R.parse_close(verdict, "")[1] == R.ReportRefusal(422, "bad_verdict"), verdict
    assert R.parse_close("actioned", 5)[1] == R.ReportRefusal(422, "bad_note")
    assert R.parse_close("actioned", "n" * (4 * R.NOTE_MAX + 1))[1] == R.ReportRefusal(422, "note_too_long")
    assert len(R.parse_close("actioned", "n" * 900)[0][1]) == R.NOTE_MAX == 500
    assert R.close_refusal(None) == R.REPORT_NOT_FOUND and R.close_refusal("open") is None
    for status in ("dismissed", "actioned"):
        assert R.close_refusal(status) == R.ALREADY_CLOSED, status
    assert (R.ALREADY_CLOSED.status, R.ALREADY_CLOSED.code) == (409, "already_closed")


def test_closing_takes_one_of_two_verdicts_and_only_an_open_report():
    _check(_close,
           lambda s: _replace(s, "RULES", '    if current_status != "open":\n        return ALREADY_CLOSED\n', ""),
           _control("RULES", "def close_refusal("))


def _actions(src):
    R = _rules(src)
    words = (R.ACTION_LIST, R.ACTION_LOG, R.ACTION_CLOSE)
    assert words == ("player_reports", "player_reports_log", "player_reports_close")
    assert len(set(words)) == 3 and not [w for w in words if ":" in w]
    rid = uuid.UUID(int=21)
    assert R.close_target(rid, "actioned") == "%s:actioned" % rid
    assert R.close_target(rid, "actioned") != R.close_target(rid, "dismissed")


def test_each_admin_route_signs_its_own_action_word_and_the_close_names_its_verdict():
    _check(_actions,
           lambda s: _replace(s, "RULES", '    return "%s:%s" % (report_id, verdict)', '    return "%s" % (report_id,)'),
           _control("RULES", "def close_target("))


# == the sources ====================================================================

ROUTE_TABLE = (("POST", PATHS[0], "submit_player_report"), ("GET", PATHS[1], "my_reportable_games"),
               ("GET", PATHS[2], "admin_list_player_reports"), ("GET", PATHS[3], "admin_player_report_log"),
               ("POST", PATHS[4], "admin_close_player_report"))
POSTS = {"submit_player_report", "admin_close_player_report"}
GETS = {"my_reportable_games", "admin_list_player_reports", "admin_player_report_log"}
WRITERS = {"INSERT_SQL", "INSERT_LOG_SQL", "RETENTION_SQL", "CLOSE_SQL"}
ADMIN_ROUTES = (("admin_list_player_reports", "ACTION_LIST"), ("admin_player_report_log", "ACTION_LOG"),
                ("admin_close_player_report", "ACTION_CLOSE"))
BINDS = {"CLOSE_SQL": "adm id n v", "COUNTS_SQL": "", "DUPLICATE_SQL": "g k rd rp", "GAMES_SQL": "lim pid",
         "INSERT_LOG_SQL": "gz id n", "INSERT_SQL": "d e g id k r rd rp", "LIST_BY_STATUS_SQL": "lim off st",
         "LIST_SQL": "lim off", "LOG_GZ_SQL": "id", "LOG_META_SQL": "id", "MY_REPORTS_SQL": "rp",
         "PLAYER_SQL": "s", "RECENT_SQL": "rp", "RETENTION_SQL": "", "STATUS_SQL": "id", "SWITCH_SQL": "k"}

_ROUTE_MODS = {}


def _routes(src):
    """The route module as `src` has it, executed under a name of its own: its
    statements are module constants, so a mutated statement is read as built."""
    text = src["ROUTES"]
    if text not in _ROUTE_MODS:
        name = "player_reports_case_%d" % len(_ROUTE_MODS)
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        try:
            exec(compile(text, FILES["ROUTES"], "exec"), mod.__dict__)
        finally:
            sys.modules.pop(name, None)
        _ROUTE_MODS[text] = mod
    return _ROUTE_MODS[text]


def _statements(src):
    mod = _routes(src)
    return {n: getattr(mod, n) for n in dir(mod) if n.endswith("_SQL")}


def _fn_node(text, name):
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError("no function %s" % name)


def _code(text, name):
    """The function's statements as code: no comment, no docstring."""
    body = _fn_node(text, name).body
    first = body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        body = body[1:]
    return "\n".join(ast.unparse(s) for s in body)


def _reach(text):
    """(the module's functions, what each reaches through the module's own
    functions: the names it reads and the attributes it uses)."""
    fns = {n.name: n for n in ast.parse(text).body
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    direct = {name: ({n.id for n in ast.walk(node) if isinstance(n, ast.Name)},
                     {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)})
              for name, node in fns.items()}

    def closure(name, seen):
        if name in seen:
            return set(), set()
        seen.add(name)
        names, attrs = set(direct[name][0]), set(direct[name][1])
        for callee in sorted(direct[name][0] & set(fns)):
            more = closure(callee, seen)
            names |= more[0]
            attrs |= more[1]
        return names, attrs

    return fns, {name: closure(name, set()) for name in fns}


def _is_read(sql):
    """Default deny: a statement reads only if it is a SELECT (or WITH) that
    names no writing or locking word."""
    up = " ".join(sql.upper().split())
    if not (up.startswith("SELECT ") or up.startswith("WITH ")):
        return False
    return not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|LOCK|NEXTVAL|SETVAL|SHARE|PG_ADVISORY\w*)\b", up)


def _submit_order(src):
    text = src["ROUTES"]
    node = _fn_node(text, "submit_player_report")
    assert [a.arg for a in node.args.args] == ["request", "db"], "the submit declares a parsed body"
    assert not node.args.kwonlyargs and node.args.vararg is None and node.args.kwarg is None
    _order(_code(text, "submit_player_report"),
           "main.IS_REPLICA", "_player_gate(", "_read_body(", "_plr.parse_submit(", "_facts(",
           "_prepared_log(", "main._identity_lock_many(", "main._strict_steam_session_ok(", "_facts(",
           "_plr.decide_submit(", "_plr_sql(INSERT_SQL)", "_plr_sql(INSERT_LOG_SQL)", "_plr_sql(RETENTION_SQL)", "db.commit()")
    _order(_code(text, "_player_gate"), "_plr_session(", "SWITCH_SQL", "_plr.pre_body_refusal(",
           "_plr_refuse(refusal)", "return steam_id")
    for reader in ("request.body", "request.json", "request.form"):
        assert reader not in text, "the body is read by %s" % reader
    assert text.count("request.stream()") == 1 and "request.stream()" in _code(text, "_read_body")


def test_the_submit_decides_rules_1_to_3_before_it_reads_a_byte_of_the_body():
    gate = '    steam_id = await _player_gate(request, db, request.headers.get("content-length"))\n'
    read = "    raw = await _read_body(request)\n"
    _check(_submit_order,
           lambda s: _replace(s, "ROUTES", gate + read, read + gate),
           _control("ROUTES", "async def _read_body("))


def _reporter(src):
    text = src["ROUTES"]
    node = _fn_node(text, "submit_player_report")
    assigned = [s for s in ast.walk(node) if isinstance(s, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "steam_id" for t in s.targets)]
    assert len(assigned) == 1 and "_player_gate(" in ast.unparse(assigned[0].value)
    calls = [ast.unparse(c) for c in ast.walk(node)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "_facts"]
    assert calls == ["_facts(db, steam_id, sub)"] * 2, calls
    assert "_plr_sql(PLAYER_SQL), {'s': reporter_steam_id}" in _code(text, "_facts")
    assert "'rp': reporter_id" in ast.unparse(node), "the stored reporter is not the session's"
    assert "return steam_id" in _code(text, "_player_gate") and "main._session_seat(request, db)" in _code(text, "_plr_session")
    # The parsed body is read through six fields, none of them a reporter.
    used = {n.attr for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name) and n.value.id == "sub"}
    assert used <= set(_rules(src).ReportSubmit.__slots__) and not [a for a in used if "reporter" in a], sorted(used)
    for _, _, name in ROUTE_TABLE:
        params = [a.arg for a in _fn_node(text, name).args.args]
        assert not [p for p in params if "reporter" in p], (name, params)


def test_the_reporter_is_the_account_the_session_names_and_nothing_else():
    line = "    reporter_id, game, reported, duplicate, recent = await _facts(db, %s, sub)\n"
    _check(_reporter,
           lambda s: _replace(s, "ROUTES", line % "steam_id", line % "sub.reported_steam_id"),
           _control("ROUTES", "async def _facts("))


def _c2(src):
    text = src["ROUTES"]
    node = _fn_node(text, "submit_player_report")
    at = [i for i, s in enumerate(node.body) if "_identity_lock_many(" in ast.unparse(s)]
    assert len(at) == 1, at
    before, after = node.body[:at[0]], node.body[at[0]:]
    assert [1 for s in before if "_prepared_log(" in ast.unparse(s)], "the log is not prepared before the locks"
    assert not [1 for s in after if "_prepared_log(" in ast.unparse(s)]
    for stmt in after:
        for n in ast.walk(stmt):
            # Inside the write transaction nothing catches: an error there fails the request.
            assert not isinstance(n, (ast.Try, ast.With, ast.AsyncWith)), "line %d handles an error" % n.lineno
            if isinstance(n, ast.Assign):
                assert "gz" not in [t.id for t in n.targets if isinstance(t, ast.Name)], "gz is reassigned"
    assert ast.unparse(after[-1]) == "return {'ok': True, 'log_stored': gz is not None}"
    assert "await db.commit()" == ast.unparse(after[-2])
    tree = ast.parse(text)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                and n.attr in ("begin_nested", "begin", "rollback")], "the module opens a savepoint or rolls back"
    assert not [n for n, sql in _statements(src).items() if "SAVEPOINT" in sql.upper()]
    prepared = _fn_node(text, "_prepared_log")
    assert [a.arg for a in prepared.args.args] == ["log_text"], "the log's preparation is handed a connection"
    code = _code(text, "_prepared_log")
    code = code.replace("(None, 0)", "None, 0").replace("(gz, raw_chars)", "gz, raw_chars")   # either unparse form
    _order(code, "al._hop(al._CPU_POOL, al.AUTO_LOG_CPU_WAIT_S, _plr.prepare_log, log_text)",
           "except Exception", "return None, 0", "if gz is None", "return None, 0", "return gz, raw_chars")
    assert "db" not in {n.id for n in ast.walk(prepared) if isinstance(n, ast.Name)}


def test_c2_a_log_fails_alone_only_before_the_write_transaction():
    insert = '        await db.execute(_plr_sql(INSERT_LOG_SQL), {"id": report_id, "gz": gz, "n": raw_chars})\n'
    _check(_c2,
           lambda s: _replace(s, "ROUTES", "    if gz is not None:\n" + insert,
                              "    if gz is not None:\n        try:\n    " + insert
                              + "        except Exception:\n            gz = None\n"),
           _control("ROUTES", "async def _prepared_log("))


def _c3_census(src):
    text = src["ROUTES"]
    stmts = _statements(src)
    writers = {n for n, sql in stmts.items() if not _is_read(sql)}
    assert writers == WRITERS, sorted(writers ^ WRITERS)
    # Every statement the module runs is one of its named constants.
    for call in ast.walk(ast.parse(text)):
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "_plr_sql":
            assert len(call.args) == 1 and isinstance(call.args[0], ast.Name) and call.args[0].id in stmts, \
                "a statement outside the named ones: %s" % ast.unparse(call)[:70]
    fns, reach = _reach(text)
    assert {n for n, node in fns.items() if node.decorator_list} == POSTS | GETS
    for name in sorted(fns):
        names, attrs = reach[name]
        if name in POSTS:
            assert "RETENTION_SQL" in names and "commit" in attrs, "%s does not run the retention DELETE" % name
            assert {"IS_REPLICA", "_replica_skip"} <= attrs, "%s is not refused on a read replica" % name
            continue
        assert not names & writers, "%s reaches %s" % (name, sorted(names & writers))
        assert not attrs & {"commit", "_identity_lock_many"}, "%s commits or locks" % name
    direct = {name: {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} & writers
              for name, node in fns.items()}
    assert {n for n, hit in direct.items() if hit} == POSTS, "a write statement is named outside the two POST routes"


def test_c3_no_get_route_reaches_a_statement_that_writes():
    meta = '    meta = (await db.execute(_plr_sql(LOG_META_SQL), {"id": rid})).mappings().first()\n'
    _check(_c3_census,
           lambda s: _replace(s, "ROUTES", meta, "    await db.execute(_plr_sql(RETENTION_SQL))\n" + meta),
           _control("ROUTES", "async def _listed_games("))


def _gate_list(gate_text, name):
    for node in ast.parse(gate_text).body:
        target = (node.target if isinstance(node, ast.AnnAssign)
                  else node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == name:
            return {c.value for c in ast.walk(node.value)
                    if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    raise AssertionError("read_gate has no list %s" % name)


def _route_census(src):
    text = src["ROUTES"]
    found = []
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                assert (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                        and ast.unparse(d.func.value) == "plr_router" and len(d.args) == 1 and not d.keywords), ast.unparse(d)
                found.append((d.func.attr.upper(), d.args[0].value, node.name))
    assert sorted(found) == sorted(ROUTE_TABLE), found
    assert "plr_router = _PlrRouter(tags=['Player Reports'], route_class=_PlrGateRoute)" in ast.unparse(ast.parse(text))
    player, signed = _gate_list(src["GATE"], "PLAYER"), _gate_list(src["GATE"], "ADMIN_SIGNED")
    assert PATHS[1] in player and PATHS[1] not in signed, "the games read is not in the PLAYER class"
    for path in (PATHS[2], PATHS[3]):
        assert path in signed and path not in player, "%s is not in the ADMIN_SIGNED class" % path


def test_five_routes_and_each_get_has_its_read_gate_class():
    _check(_route_census,
           lambda s: _replace(s, "GATE", '    "/api/v1/admin/player-reports",\n', ""),
           _control("GATE", "ADMIN_SIGNED: frozenset"))


def _admin_first(src):
    text = src["ROUTES"]
    for name, action in ADMIN_ROUTES:
        node = _fn_node(text, name)
        awaits = sorted((n for n in ast.walk(node) if isinstance(n, ast.Await)),
                        key=lambda n: (n.lineno, n.col_offset))
        first = awaits[0].value
        assert ast.unparse(first).startswith("_admin(db, "), \
            "%s awaits %s before its admin checks" % (name, ast.unparse(first)[:50])
        assert ast.unparse(first.args[2]) == "_plr." + action, (name, ast.unparse(first.args[2]))
        reads = [n.lineno for n in ast.walk(node) if isinstance(n, ast.Attribute) and n.attr == "execute"]
        assert min(reads) > first.lineno, "%s reads the database before its admin checks" % name
    used = sorted(n.attr for n in ast.walk(ast.parse(text))
                  if isinstance(n, ast.Attribute) and n.attr.startswith("ACTION_"))
    assert used == sorted(a for _, a in ADMIN_ROUTES), used
    helper = _code(text, "_admin")
    _order(helper, "if not await main._is_admin(db, admin_steam_id)", "raise _PlrHttpError(403",
           "if not main._verify_admin_hmac(admin_steam_id, action, str(target), signature)",
           "raise _PlrHttpError(403")
    assert helper.count("raise _PlrHttpError(403") == 2 and "return" not in helper
    close = ast.unparse(_fn_node(text, "admin_close_player_report"))
    assert "_plr.close_target(report_id, req.verdict), req.hmac_signature)" in close


def test_each_admin_route_checks_the_admin_and_the_signature_before_anything_else():
    _check(_admin_first,
           lambda s: _replace(s, "ROUTES",
                              "    await _admin(db, admin_steam_id, _plr.ACTION_LOG, report_id, hmac_signature)\n", ""),
           _control("ROUTES", "async def _admin("))


ENFORCED = {"_player_gate": ["_plr.pre_body_refusal("], "_read_body": ["_plr.size_refusal("],
            "submit_player_report": ["_plr.parse_submit(", "_plr.decide_submit(", "_plr.decide_submit("],
            "admin_player_report_log": ["_plr.log_refusal("], "admin_close_player_report": ["_plr.parse_close("]}


def _enforced(src):
    text = src["ROUTES"]
    for name, calls in ENFORCED.items():
        seen = []
        for parent in ast.walk(_fn_node(text, name)):
            body = getattr(parent, "body", None)
            if not isinstance(body, list):
                continue
            for i, stmt in enumerate(body):
                hit = [c for c in sorted(set(calls)) if isinstance(stmt, ast.Assign) and c in ast.unparse(stmt.value)]
                if not hit:
                    continue
                seen.append(hit[0])
                nxt = body[i + 1] if i + 1 < len(body) else None
                assert (isinstance(nxt, ast.If) and ast.unparse(nxt.test) == "refusal is not None"
                        and [ast.unparse(s) for s in nxt.body] == ["_plr_refuse(refusal)"] and not nxt.orelse), \
                    "%s: the answer of %s is not acted on" % (name, hit[0])
        assert sorted(seen) == sorted(calls), (name, seen)
    log = _code(text, "admin_player_report_log")
    _order(log, "_admin(", "_plr_sql(LOG_META_SQL)", "_plr.log_refusal(", "_plr_sql(LOG_GZ_SQL)", "_plr.unpack_log",
           "body, counts = await main._scrub_bug_log(db, body)", "return _PlrPlainText(content=body")
    assert log.count("return ") == 1, "the log route has a second way out"
    assert "raise _PlrHttpError(status_code=refusal.status, detail={'error': refusal.code})" in _code(text, "_plr_refuse")


def test_every_rules_answer_is_acted_on_and_a_log_leaves_only_through_the_scrub():
    tail = '                                meta["closed_at"], meta["now"])\n'
    _check(_enforced,
           lambda s: _replace(s, "ROUTES", tail + "    if refusal is not None:\n        _plr_refuse(refusal)\n", tail),
           _control("ROUTES", "def _plr_refuse("))


# -- main.py: the mount, the rate limiter's list, account deletion -----------------

DELETE_REPORTS = 'await db.execute(text("DELETE FROM player_reports WHERE reporter_id = :pid OR reported_id = :pid"), {"pid": pid})'
CLEAR_CLOSER = 'await db.execute(text("UPDATE player_reports SET closed_by = NULL WHERE closed_by = :pid"), {"pid": pid})'
MOUNT = ("import player_reports as _player_reports", "app.include_router(_player_reports.plr_router)")
TABLE_WORD = re.compile(r"player_report(?:s|_logs)\b")


def _main_claims(src):
    main_text = src["MAIN"]
    for line in MOUNT:
        assert main_text.count("\n" + line + "\n") == 1, "main.py does not carry once: %s" % line
    _order(main_text, "app.include_router(_match_hold.router)", MOUNT[0], MOUNT[1])
    # The mounted name is the route module's own router.
    assert "plr_router = _PlrRouter(" in src["ROUTES"] and MOUNT[1].endswith(".plr_router)")
    block = re.search(r"^_RL_SENSITIVE_PREFIXES = \((.*?)^\)", main_text, re.M | re.S)
    assert block, "no _RL_SENSITIVE_PREFIXES"
    prefixes = []
    for line in block.group(1).split("\n"):
        prefixes += re.findall(r'"([^"]+)"', line.split("#", 1)[0])
    rid = str(uuid.UUID(int=21))
    got = tuple(any(p.replace("{report_id}", rid).startswith(x) for x in prefixes) for p in PATHS)
    # submit, games, the admin list (the ordinary bucket), the log, the close
    assert got == (True, True, False, True, True), got
    fn = _main_fn(main_text, "delete_player_data")
    _order(fn, "pg_advisory_xact_lock(hashtext(:sid))",
           "DELETE FROM player_blocks WHERE blocker_id = :pid OR blocked_id = :pid", DELETE_REPORTS, CLEAR_CLOSER)


def test_main_mounts_the_routes_limits_them_and_account_deletion_removes_both_sides():
    _check(_main_claims,
           lambda s: _replace(s, "MAIN", "    " + CLEAR_CLOSER + "\n", ""),
           _control("MAIN", "import match_hold as _match_hold"))


_NAMED = {}


def _files_naming_the_tables():
    """Every .py under backend/ outside tests/ that names one of the two tables
    (main.py is read from the claim's sources instead)."""
    if not _NAMED:
        hits = set()
        for dirpath, dirs, files in os.walk(BACKEND):
            dirs[:] = [d for d in dirs if d not in ("tests", "sql", "nginx", "assets", "__pycache__", "node_modules")]
            for f in files:
                path = os.path.join(dirpath, f)
                rel = os.path.relpath(path, BACKEND).replace(os.sep, "/")
                if f.endswith(".py") and rel != "api/main.py" and TABLE_WORD.search(_read(path)):
                    hits.add(rel)
        _NAMED["hits"] = hits
    return _NAMED["hits"]


def _table_census(src):
    """Who can read a report: the code that names its tables. The route module
    and the two statements of account deletion; no other module, and not the bot."""
    lines = [l.strip() for l in src["MAIN"].split("\n") if TABLE_WORD.search(l.split("#", 1)[0])]
    assert sorted(lines) == sorted(MOUNT + (DELETE_REPORTS, CLEAR_CLOSER)), lines
    assert _files_naming_the_tables() == {"api/player_reports.py", "api/player_report_rules.py"}, \
        sorted(_files_naming_the_tables())
    # The rules module names no table: it holds the action word, and no statement.
    rules_text = src["RULES"]
    assert not re.search(r"\b(SELECT|INSERT INTO|UPDATE|DELETE FROM)\b", rules_text), "the rules module carries SQL"
    assert "import main" not in rules_text and "sqlalchemy" not in rules_text


def test_only_the_route_module_and_account_deletion_name_the_tables():
    _check(_table_census,
           lambda s: _replace(s, "MAIN", MOUNT[1] + "\n",
                              MOUNT[1] + '\n_PLAYER_REPORT_PEEK = "SELECT COUNT(*) FROM player_reports"\n'),
           _control("MAIN", "import match_hold as _match_hold"))


# -- the statements ---------------------------------------------------------------

def _statement_forms(src):
    stmts = _statements(src)
    assert sorted(stmts) == sorted(BINDS), sorted(set(stmts) ^ set(BINDS))
    for name, sql in stmts.items():
        # #697: text() reads a colon and a name as a bind wherever it stands, a comment included.
        assert "--" not in sql and "/*" not in sql, "%s carries a comment" % name
        binds = sorted(set(re.findall(r"(?<![:\w]):([A-Za-z_]\w*)", sql)))
        assert binds == BINDS[name].split(), (name, binds)
        assert "%" not in sql, "%s has an unfilled format" % name
        assert "LATERAL" not in sql.upper(), "%s uses LATERAL (asyncpg, condition C5)" % name
    for call in ast.walk(ast.parse(src["ROUTES"])):
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "execute"
                and call.args and "_plr_sql(" in ast.unparse(call.args[0])):
            name = call.args[0].args[0].id
            if len(call.args) == 1:
                assert BINDS[name] == "", "%s is run without its values" % name
            elif isinstance(call.args[1], ast.Dict):
                keys = sorted(k.value for k in call.args[1].keys)
                assert keys == BINDS[name].split(), (name, keys)


def test_each_statement_has_exactly_its_bind_names_and_no_comment():
    line = 'SWITCH_SQL = "SELECT value FROM runtime_settings WHERE key = :k'
    _check(_statement_forms,
           lambda s: _replace(s, "ROUTES", line + '"', line + ' -- the switch:row"'),
           _control("ROUTES", "SWITCH_SQL = "))


def _games_statement(src):
    R = _rules(src)
    sql = _statements(src)["GAMES_SQL"]
    branches = dict(re.findall(r"(g_1v1|g_2v2|g_1v2|g_ffa) AS \((.*?)\n\)", sql, re.S))
    assert sorted(branches) == ["g_1v1", "g_1v2", "g_2v2", "g_ffa"], sorted(branches)
    assert (R.GAME_WINDOW_DAYS, R.GAME_LIST_MAX) == (14, 25)
    window = "ended_at > now() - (%d * INTERVAL '24 hours')" % R.GAME_WINDOW_DAYS
    for name, body in sorted(branches.items()):
        flat = " ".join(body.split())
        assert ":pid" in flat, "%s is not bounded by the caller's id" % name
        assert window in flat, "%s lists games older than the window" % name
        assert "invalidated_at IS NULL" in flat, "%s lists invalidated games" % name
        assert re.search(r"ORDER BY \w+\.ended_at DESC, \w+\.id DESC LIMIT :lim$", flat), \
            "%s is not bounded in length" % name
    flat = " ".join(sql.split())
    # C5: one statement, four branches joined by UNION ALL, then the newest 25.
    assert flat.count("UNION ALL") == 3 and flat.startswith("WITH g_1v1 AS (")
    # Every read names its columns: no whole row of a game table reaches the answer.
    assert "SELECT *" not in flat and ".*" not in flat, "the statement reads a whole row"
    assert "ORDER BY u.ended_at DESC, u.id DESC LIMIT :lim ) SELECT" in flat
    assert "JOIN players p ON p.id = ANY(t.pids) WHERE p.deleted_at IS NULL" in flat
    for prefix in ("team_", "ovt_", "ffa_"):       # rows of `matches` that are not 1v1 games
        assert "LEFT(m.photon_room_id, %d) <> '%s'" % (len(prefix), prefix) in branches["g_1v1"], prefix
    ffa = " ".join(branches["g_ffa"].split())
    assert "me.player_id = :pid AND NOT me.absent" in ffa and "x.match_id = fm.id AND NOT x.absent" in ffa
    # One function reads the games, for the form and for the submit.
    assert "_plr_sql(GAMES_SQL), {'pid': reporter_id, 'lim': _plr.GAME_LIST_MAX}" in _code(src["ROUTES"], "_listed_games")
    fns, reach = _reach(src["ROUTES"])
    assert [n for n in sorted(fns) if "GAMES_SQL" in {x.id for x in ast.walk(fns[n]) if isinstance(x, ast.Name)}] \
        == ["_listed_games"]
    for route in ("my_reportable_games", "submit_player_report"):
        assert "_listed_games" in reach[route][0], "%s reads its games another way" % route


def test_r6_every_branch_of_the_games_read_is_bounded_by_the_window():
    _check(_games_statement,
           lambda s: _replace(s, "ROUTES", '       AND om.ended_at > now() - """ + _WINDOW + """\n', ""),
           _control("ROUTES", "GAMES_SQL = "))


def test_c5_no_branch_of_the_games_read_takes_a_whole_row():
    _check(_games_statement,
           lambda s: _replace(s, "ROUTES", "UNION ALL SELECT kind, id, ended_at, pids FROM g_1v2",
                              "UNION ALL SELECT * FROM g_1v2"),
           _control("ROUTES", "GAMES_SQL = "))


def test_r6_every_branch_of_the_games_read_leaves_out_invalidated_games():
    _check(_games_statement,
           lambda s: _replace(s, "ROUTES", "       AND tm.invalidated_at IS NULL\n", ""),
           _control("ROUTES", "GAMES_SQL = "))


# -- the migration ----------------------------------------------------------------

def _control_sql(key, anchor):
    return lambda s: _replace(s, key, "\n" + anchor, "\n-- control\n" + anchor)


def _sql_code(sql):
    return "\n".join(line.split("--", 1)[0] for line in sql.split("\n"))


def _in_list(sql, constraint):
    m = re.search(r"CONSTRAINT %s CHECK \((.*?)\)\)" % constraint, sql, re.S)
    assert m, constraint
    return tuple(re.findall(r"'([^']*)'", m.group(1)))


def _migration_lists(src):
    R = _rules(src)
    up = _sql_code(src["UP"])
    assert _in_list(up, "player_reports_kind") == R.GAME_KINDS
    assert _in_list(up, "player_reports_reason") == R.REASONS
    assert _in_list(up, "player_reports_status") == R.REPORT_STATUSES
    for check in ("CHECK (char_length(details) <= %d)" % R.DETAILS_MAX,
                  "CHECK (char_length(close_note) <= %d)" % R.NOTE_MAX,
                  "CHECK (octet_length(gz) <= %d AND raw_chars >= 0)" % R.LOG_GZ_MAX,
                  "CHECK (reporter_id <> reported_id)",
                  "CHECK ((status = 'open') = (closed_at IS NULL))",
                  "CONSTRAINT player_reports_once UNIQUE (reporter_id, game_kind, game_id, reported_id)"):
        assert check in up, check
    assert "ON CONFLICT ON CONSTRAINT player_reports_once DO NOTHING" in _statements(src)["INSERT_SQL"]
    foreign = re.findall(r"(\w+)\s+UUID\s+(?:NOT NULL|NULL|PRIMARY KEY)\s+REFERENCES (\w+)\(id\) ON DELETE (CASCADE|SET NULL)", up)
    assert sorted(foreign) == sorted([("reporter_id", "players", "CASCADE"), ("reported_id", "players", "CASCADE"),
                                      ("closed_by", "players", "SET NULL"),
                                      ("report_id", "player_reports", "CASCADE")]), foreign


def test_the_migrations_closed_lists_and_caps_are_the_rules_own():
    _check(_migration_lists,
           lambda s: _replace(s, "UP", "'leaving', 'name', 'other'", "'leaving', 'other'"),
           _control_sql("UP", "CREATE TABLE IF NOT EXISTS player_reports ("))


GUARDED = re.compile(r"(CREATE TABLE IF NOT EXISTS |CREATE INDEX IF NOT EXISTS |DROP TABLE IF EXISTS "
                     r"|INSERT INTO runtime_settings .* ON CONFLICT \(key\) DO NOTHING$"
                     r"|DELETE FROM runtime_settings WHERE key = '"
                     r"|ALTER TABLE player_report_logs ALTER COLUMN gz SET STORAGE EXTERNAL$)")


def _migration_form(src):
    R = _rules(src)
    up, down = _sql_code(src["UP"]), _sql_code(src["DOWN"])
    # C1: the switch's row is written by the migration, and written ON.
    row = re.search(r"INSERT INTO runtime_settings \(key, value\) VALUES \('([^']+)', '([^']*)'\)\s+"
                    r"ON CONFLICT \(key\) DO NOTHING;", up)
    assert row and row.groups() == (R.SWITCH_KEY, R.SWITCH_ON) == ("player_reports_accept", "1"), row and row.groups()
    assert "DELETE FROM runtime_settings WHERE key = '%s';" % R.SWITCH_KEY in down
    assert "DROP TABLE IF EXISTS player_report_logs;" in down and "DROP TABLE IF EXISTS player_reports;" in down
    for name, sql in (("the migration", up), ("the rollback", down)):
        stmts = [" ".join(s.split()) for s in sql.split(";") if s.strip()]
        assert stmts[0] == "BEGIN" and stmts[1].startswith("SET LOCAL lock_timeout = ") and stmts[-1] == "COMMIT", \
            "%s is not one explicit transaction (#340)" % name
        assert [s for s in stmts if s in ("BEGIN", "COMMIT")] == ["BEGIN", "COMMIT"], name
        for s in stmts[2:-1]:
            assert GUARDED.match(s), "%s has a statement that cannot run twice: %s" % (name, s[:60])
    for key in ("UP", "DOWN"):                      # #697: a colon and a name is a bind, in a comment too
        for i, line in enumerate(src[key].split("\n"), 1):
            assert not re.search(r"(?<!:):[A-Za-z_]", line), "%s line %d: %s" % (key, i, line.strip()[:60])


def test_c1_the_migration_writes_the_switch_on_and_both_files_can_run_twice():
    _check(_migration_form,
           lambda s: _replace(s, "UP", "VALUES ('player_reports_accept', '1')", "VALUES ('player_reports_accept', '0')"),
           _control_sql("UP", "BEGIN;"))
