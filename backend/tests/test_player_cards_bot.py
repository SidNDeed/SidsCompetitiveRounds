"""Player Cards — the Discord bot half (Sept 10 batch, WP-F), pinned on the
bot's SOURCE: discord_bot.py builds the bot at import time and is not
importable in a test process (test_mail_bot.py). Both sides of the internal
contract are read from their own files, so a route rename on either side
fails here rather than at the first /daily in production (#341)."""
import re
from pathlib import Path

BOT_SRC = (Path(__file__).resolve().parents[1] / "discord_bot.py").read_text(encoding="utf-8")
MAIN_SRC = (Path(__file__).resolve().parents[1] / "api" / "main.py").read_text(encoding="utf-8")


def _fn(src, name):
    m = re.search(rf"^async def {re.escape(name)}\(.*?(?=^(?:async def |def |@|# ──)|\Z)", src, re.S | re.M)
    assert m, name
    return m.group(0)


def test_the_three_commands_and_the_drain_loop_exist_once():
    for name in ("daily", "collection", "card"):
        assert BOT_SRC.count(f'@bot.hybrid_command(name="{name}"') == 1, name
    assert BOT_SRC.count("@tasks.loop(seconds=60)\nasync def poll_pc_events():") == 1
    assert BOT_SRC.count("if not poll_pc_events.is_running(): poll_pc_events.start()") == 1


def test_every_internal_route_the_bot_calls_is_registered_by_the_api():
    paths = set(re.findall(r'"/internal/pc/[a-z/]+"', BOT_SRC))
    assert paths == {'"/internal/pc/daily"', '"/internal/pc/collection"', '"/internal/pc/card"',
                     '"/internal/pc/events/pending"', '"/internal/pc/events/ack"',
                     '"/internal/pc/lease"', '"/internal/pc/face/back"'}
    for p in paths:
        full = '"/api/v1' + p[1:]
        assert (f"@app.get({full}" in MAIN_SRC) or (f"@app.post({full}" in MAIN_SRC), p
    # the two mutating routes are POSTs on both sides, the reads are GETs
    assert '_pc_api("POST", "/internal/pc/daily"' in BOT_SRC and '@app.post("/api/v1/internal/pc/daily"' in MAIN_SRC
    assert '_pc_api("POST", "/internal/pc/events/ack"' in BOT_SRC and '@app.post("/api/v1/internal/pc/events/ack"' in MAIN_SRC
    for read in ("collection", "card", "events/pending"):
        assert f'_pc_api("GET", "/internal/pc/{read}"' in BOT_SRC and f'@app.get("/api/v1/internal/pc/{read}"' in MAIN_SRC
    # the lease and face routes (v22 section 6): the bot's f-string paths against the api's registrations
    assert '_pc_api("POST", "/internal/pc/lease"' in BOT_SRC and '@app.post("/api/v1/internal/pc/lease"' in MAIN_SRC
    assert BOT_SRC.count('f"/internal/pc/lease/{lease_id}"') == 2
    assert '@app.get("/api/v1/internal/pc/lease/{lease_id}"' in MAIN_SRC and '@app.delete("/api/v1/internal/pc/lease/{lease_id}"' in MAIN_SRC
    assert BOT_SRC.count('f"/internal/pc/face/print/{') == 2 and '@app.get("/api/v1/internal/pc/face/print/{print_id}/{locale}"' in MAIN_SRC
    assert BOT_SRC.count('f"/internal/pc/face/preview/{') == 1 and '@app.get("/api/v1/internal/pc/face/preview/{player_ref}/{locale}"' in MAIN_SRC
    assert '_pc_api_bytes("/internal/pc/face/back")' in BOT_SRC and '@app.get("/api/v1/internal/pc/face/back"' in MAIN_SRC


def test_the_drain_posts_then_acks_and_stops_on_a_failed_send():
    src = _fn(BOT_SRC, "poll_pc_events")
    assert src.index("await _pc_send_face(ch.send") < src.index('"/internal/pc/events/ack"'), "ack-after-send (#105)"
    # two breaks, and each says why: a failed send stops the tick to keep the
    # order, and so does a print group still waiting for its picture
    assert src.count("break") == 2 and "retrying next tick" in src
    assert "yet (try" in src
    assert "LEADERBOARD_CHANNEL_ID" in src and "if not sent:\n        return" in src
    assert "_pc_events_sent.pop(i, None)" in src, "the send memory is released only by a successful ack"


def test_identity_is_the_callers_discord_id_never_a_steam_id():
    for name in ("cmd_pc_daily", "cmd_pc_collection", "cmd_pc_card"):
        src = _fn(BOT_SRC, name)
        assert "steam_id" not in src, name
        assert "await _maybe_defer(ctx)" in src, name
    assert 'params={"discord_id": str(ctx.author.id)}' in _fn(BOT_SRC, "cmd_pc_daily")
    assert '"viewer_discord_id": str(ctx.author.id)' in _fn(BOT_SRC, "cmd_pc_collection")


def test_names_from_the_api_are_escaped_before_markdown():
    assert "discord.utils.escape_markdown(str(s or" in BOT_SRC
    assert "_pc_name(first.get(\"puller_name\"))" in BOT_SRC and "_pc_name(first.get(\"subject_name\"))" in BOT_SRC
    assert "target.display_name)" in _fn(BOT_SRC, "cmd_pc_collection")


def test_refusals_are_read_by_status_and_token():
    daily = _fn(BOT_SRC, "cmd_pc_daily")
    assert 'status == 404 and d.get("error") == "not_linked"' in daily
    assert 'status == 409 and d.get("error") == "already_claimed"' in daily
    coll = _fn(BOT_SRC, "cmd_pc_collection")
    assert "status == 403" in coll and "private" in coll
    card = _fn(BOT_SRC, "cmd_pc_card")
    assert "not in the card pool" in card


def test_events_are_grouped_by_the_nested_print_id():
    start = BOT_SRC.index("def _pc_event_lines(")
    lines = BOT_SRC[start:BOT_SRC.index("async def ", start)]
    assert 'key = (e.get("print") or {}).get("print_id") or e.get("print_id") or f"event:{e[\'id\']}"' in lines
    # the api's shape: print_id lives under "print"
    assert '"print": ({"print_id": str(r["print_id"])' in MAIN_SRC


def test_api_names_in_embed_titles_are_escaped():
    assert "_pc_name(body.get('owner_name') or target.display_name)" in _fn(BOT_SRC, "cmd_pc_collection")
    assert "_pc_name(body.get('subject_name') or target.display_name)" in _fn(BOT_SRC, "cmd_pc_card")


def test_a_private_binder_is_read_by_its_token_and_the_balance_only_when_sent():
    coll = _fn(BOT_SRC, "cmd_pc_collection")
    assert 'status == 403 and _pc_detail(body).get("error") == "private"' in coll
    assert 'if "shards" in body:' in coll


def test_a_page_never_cuts_a_prints_group_in_two():
    # c6 F: the api's page is the first N unposted events PLUS every other
    # unposted event of the same prints; the bot holds nothing back (the c5
    # consumer-side hold could keep the wrong group)
    src = _fn(BOT_SRC, "poll_pc_events")
    assert "page_size" not in src and "lines[:-2]" not in src
    sql = " ".join(MAIN_SRC[MAIN_SRC.index("_PC_EVENTS_PENDING_SQL = "):].split("\n\n\n")[0].split())
    # the page CTE is where the face hold is decided (v3 §8 / v4): joined to the subject, once, so a group's
    # events are all held or all handed out together
    assert ("WITH page AS ( SELECT e.id, e.print_id FROM pc_events e JOIN players su ON su.id = e.subject_player_id "
            'WHERE e.posted_at IS NULL AND """ + _PC_EVENTS_HOLD_SQL + """ ORDER BY e.id LIMIT 20 )') in sql
    assert sql.count("_PC_EVENTS_HOLD_SQL") == 1   # never a second hold on the outer query
    assert ("WHERE e.posted_at IS NULL AND (e.id IN (SELECT id FROM page) OR (e.print_id IS NOT NULL "
            "AND e.print_id IN (SELECT print_id FROM page WHERE print_id IS NOT NULL)))") in sql
    assert '"page_size": _PC_EVENTS_PAGE' in MAIN_SRC and "_PC_EVENTS_PAGE = 20" in MAIN_SRC
