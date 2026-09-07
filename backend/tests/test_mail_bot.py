"""Discord half of the mail moderation cases (Sept 6 batch, Group 4 item b).

Style of test_bridge_quota.py: discord_bot.py is not importable in a test
process (it builds the bot at import), so the pure helpers are lifted out of
its AST and EXECUTED here — the marker parser, the custom_id codec and the
answer renderer — against the api's own constants (main.MAIL_CASE_MARKER and
the exact outbox content the report path writes), so the two sides of the
contract are checked against each other, not against a copy. Source-shape
pins cover the two wiring points (poll_channel_posts, on_interaction) and
the rule that the bot sends the clicker's DISCORD id and never a steam id
of its own choosing.
"""

import ast
import os
import uuid

import pytest

import main

SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "discord_bot.py"))
TREE = ast.parse(open(SRC, encoding="utf-8").read())

WANT_FUNC = {"_modcase_uuid_ok", "_modcase_parse", "_modcase_custom_id",
             "_modcase_parse_custom_id", "_modcase_render"}
WANT_ASSIGN = {"MODCASE_MARKER", "_MODCASE_BUTTONS"}


def _module_function(name):
    fn = next((n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name), None)
    assert fn is not None, f"{name} not found at module level"
    return fn


@pytest.fixture(scope="module")
def bot():
    picked, seen_f, seen_a = [], set(), set()
    for node in TREE.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in WANT_ASSIGN:
                    picked.append(node)
                    seen_a.add(t.id)
        elif isinstance(node, ast.FunctionDef) and node.name in WANT_FUNC:
            picked.append(node)
            seen_f.add(node.name)
    assert seen_f == WANT_FUNC and seen_a == WANT_ASSIGN
    ns = {}
    exec(compile(ast.Module(body=picked, type_ignores=[]), SRC, "exec"), ns)
    return ns


def test_marker_matches_the_api_and_round_trips(bot):
    assert bot["MODCASE_MARKER"] == main.MAIL_CASE_MARKER
    case_id = str(uuid.uuid4())
    content = f"{main.MAIL_CASE_MARKER}{case_id}]\nline one\nline two"
    assert bot["_modcase_parse"](content) == (case_id, "line one\nline two")
    assert bot["_modcase_parse"](f"{main.MAIL_CASE_MARKER}{case_id}]") == (case_id, "")
    # ordinary announcements pass through untouched
    for plain in ("Tournament starts soon", "", None, "[MODCASE:not-a-uuid]\nx", f"x{main.MAIL_CASE_MARKER}{case_id}]"):
        assert bot["_modcase_parse"](plain) == (None, plain)
    assert bot["_modcase_parse"](f"{main.MAIL_CASE_MARKER}{case_id}\nno bracket") == (None, f"{main.MAIL_CASE_MARKER}{case_id}\nno bracket")


def test_custom_id_carries_the_case_id_only(bot):
    case_id = str(uuid.uuid4())
    for key, label, action, hours in bot["_MODCASE_BUTTONS"]:
        cid = bot["_modcase_custom_id"](key, case_id)
        assert cid == f"modcase:{key}:{case_id}" and len(cid) <= 100     # Discord's custom_id cap
        spec = bot["_modcase_parse_custom_id"](cid)
        assert spec == {"key": key, "label": label, "action": action, "hours": hours, "case_id": case_id}
    assert {b[2] for b in bot["_MODCASE_BUTTONS"]} == set(main._MODCASE_ACTIONS)
    assert [b[3] for b in bot["_MODCASE_BUTTONS"] if b[2] == "mute"] == [24, 168]
    for bad in ("modcase:mute24", f"modcase:nuke:{case_id}", "modcase:mute24:nope", "tdlc:x:y:z", ""):
        assert bot["_modcase_parse_custom_id"](bad) is None


def test_render_reports_the_servers_answer(bot):
    spec = {"key": "mute24", "label": "Mute 24h", "action": "mute", "hours": 24, "case_id": str(uuid.uuid4())}
    ok = bot["_modcase_render"](200, {"status": "ok", "subject_name": "Spammer", "subject_steam_id": "765",
                                      "resolution": "mute:24h"}, spec, "Mod")
    assert "Mute 24h" in ok and "Spammer" in ok and "Mod" in ok
    assert "no longer authorised" in bot["_modcase_render"](403, {"detail": "not_authorised"}, spec, "Mod")
    assert "no longer authorised" in bot["_modcase_render"](403, {"detail": "not_linked"}, spec, "Mod")
    assert "already" in bot["_modcase_render"](200, {"status": "already_resolved", "case_status": "dismissed"}, spec, "Mod")
    assert "not found" in bot["_modcase_render"](404, {}, spec, "Mod").lower()
    assert "HTTP 500" in bot["_modcase_render"](500, {"detail": {"error": "boom"}}, spec, "Mod")


def test_poll_channel_posts_attaches_buttons_and_stamps_notified():
    src = ast.get_source_segment(open(SRC, encoding="utf-8").read(), _module_function("poll_channel_posts"))
    assert src.count("_modcase_parse(") == 1 and src.count("_modcase_view(") == 1
    assert "/internal/moderation-cases/" in src and "/notified" in src
    # the ack still precedes the stamp, and the stamp is never a reason to re-post
    assert src.index("/internal/channel-posts/ack") < src.index("/notified")


def test_click_path_sends_the_discord_id_and_no_steam_id():
    text = open(SRC, encoding="utf-8").read()
    click = ast.get_source_segment(text, _module_function("_modcase_click"))
    assert "/api/v1/internal/moderation-cases/" in click and '"actor_discord_id": str(interaction.user.id)' in click
    assert "actor_steam_id" not in click and "hmac" not in click.lower()
    assert "X-Internal-Key" in click and "_modcase_render(" in click
    listener = ast.get_source_segment(text, _module_function("on_interaction"))
    assert 'cid.startswith("modcase:")' in listener and "_modcase_click(interaction, cid)" in listener
    assert listener.index('cid.startswith("modcase:")') < listener.index('cid.startswith("tdlc:")')
