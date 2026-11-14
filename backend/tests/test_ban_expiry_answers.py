"""B4 / B3 answers that need no database (the live ones are in
test_ban_expiry_live.py): what the ban request admits, the hover card's
profile block key order, and the bot's end line on the #scr-admin post."""
import ast
import os
from datetime import datetime, timezone

import pydantic
import pytest

import main
import schemas

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.normpath(os.path.join(HERE, "..", "discord_bot.py"))


def _req(**fields):
    return main._AdminBanReq(admin_steam_id="1", target_steam_id="2", **fields)


@pytest.mark.parametrize("bad", [0, -1, main.BAN_DURATION_MAX_MINUTES + 1, "60", True, 1.0, [1]])
def test_a_length_that_is_not_a_whole_number_of_minutes_in_range_is_refused(bad):
    with pytest.raises(pydantic.ValidationError) as refused:
        _req(duration_minutes=bad)
    assert [e["loc"] for e in refused.value.errors()] == [("duration_minutes",)], refused.value.errors()


def test_the_length_bounds_and_whether_it_was_sent():
    assert main.BAN_DURATION_MAX_MINUTES == 10 * 365 * 24 * 60
    for ok in (1, 60, main.BAN_DURATION_MAX_MINUTES):
        assert _req(duration_minutes=ok).duration_minutes == ok
    # the 1.41.0 request carries no field: permanent, and not a length change
    old = _req()
    assert old.duration_minutes is None and "duration_minutes" not in old.model_fields_set
    # an explicit null is SENT: it makes an active ban permanent
    null = _req(duration_minutes=None)
    assert null.duration_minutes is None and "duration_minutes" in null.model_fields_set
    # the signature's canonical string does not move (admin:{admin}:ban:{target})
    import inspect
    src = inspect.getsource(main.admin_ban)
    assert '_require_admin(db, req.admin_steam_id, "ban", req.target_steam_id, req.hmac_signature)' in src


def test_the_profile_block_keeps_its_keys_and_adds_is_banned_last():
    assert list(schemas.H2HProfileBlock.model_fields) == [
        "display_name", "title", "title_color", "tier", "tier_color", "rating_1v1", "rd_1v1",
        "level", "is_online", "last_seen_s", "is_banned"]
    dumped = schemas.H2HProfileBlock(is_banned=True).model_dump()
    assert list(dumped)[-1] == "is_banned" and dumped["is_banned"] is True
    assert schemas.H2HProfileBlock().is_banned is False


def _bot_function(name):
    with open(BOT, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    (fn,) = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    return fn


def _end_line():
    ns = {"datetime": datetime}
    exec(compile(ast.Module(body=[_bot_function("_ban_end_line")], type_ignores=[]), BOT, "exec"), ns)
    return ns["_ban_end_line"]


def test_the_bot_end_line_reads_the_end_or_permanent_and_never_raises():
    line = _end_line()
    end = datetime(2031, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert line({"expires_at": "2031-01-02T03:04:05Z"}) == "Ends: <t:%d:F>" % int(end.timestamp())
    assert line({"expires_at": None}) == "Ends: **Permanent**"
    # an api older than the key: no line, the post is the one it was before
    assert line({"id": "x"}) == ""
    for odd in ({"expires_at": "not a time"}, {"expires_at": 12}, None, "row"):
        assert line(odd) == ""


def test_the_end_line_is_built_inside_the_post_and_never_reaches_the_ban():
    """Lesson 187: the post is optional. The line is built in the per-ban try
    of poll_new_bans (whose failure is logged and skipped), after the ban is
    already written by the api; _ban_end_line itself swallows every error."""
    poll = _bot_function("poll_new_bans")
    (loop,) = [n for n in ast.walk(poll) if isinstance(n, ast.For)]
    (tried,) = [n for n in loop.body if isinstance(n, ast.Try)]
    body = ast.unparse(ast.Module(body=tried.body, type_ignores=[]))
    assert body.index("end_line = _ban_end_line(b)") < body.index("discord.Embed(")
    fn = _bot_function("_ban_end_line")
    assert isinstance(fn.body[-1], ast.Try) and [ast.unparse(h.type) for h in fn.body[-1].handlers] == ["Exception"]
