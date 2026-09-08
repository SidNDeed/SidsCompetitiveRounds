"""Discord half of the mail moderation cases (Sept 6 batch, Group 4 item b).

discord_bot.py is not importable in a test process (it builds the bot at
import), so the functions under test are lifted out of its AST, stripped of
their harness decorators and EXECUTED here against fakes for the bot, the
api helpers, the http session and the discord/aiohttp namespaces (review r1
M20: a source-string pin proves an ordering of TEXT, not of calls). The pure
helpers — marker parser, custom_id codec, answer renderer — run against the
api's own constants so the two sides of the contract are checked against
each other, not against a copy.
"""

import ast
import asyncio
import copy
import os
import re
import types
import uuid

import pytest

import main

SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "discord_bot.py"))
TEXT = open(SRC, encoding="utf-8").read()
TREE = ast.parse(TEXT)

WANT_FUNC = {"_modcase_uuid_ok", "_modcase_parse", "_modcase_custom_id", "_modcase_parse_custom_id",
             "_modcase_view", "_modcase_render", "_modcase_click", "poll_channel_posts", "on_interaction"}
WANT_ASSIGN = {"MODCASE_MARKER", "_MODCASE_BUTTONS", "_channel_post_sent", "_TDLC_ANSWERS"}


def _run(coro):
    return asyncio.run(coro)


# ── fakes: the discord / aiohttp surface the lifted code touches ──────────

class _AllowedMentions:
    def __init__(self, **kw):
        self.kw = kw

    @classmethod
    def none(cls):
        return cls(none=True)


class _Forbidden(Exception):
    pass


class _View:
    def __init__(self, timeout=None):
        self.timeout, self.children = timeout, []

    def add_item(self, item):
        self.children.append(item)


class _Button:
    def __init__(self, **kw):
        self.kw = kw


FAKE_DISCORD = types.SimpleNamespace(
    AllowedMentions=_AllowedMentions, Forbidden=_Forbidden, Interaction=object,
    InteractionType=types.SimpleNamespace(component=3, application_command=2),
    ButtonStyle=types.SimpleNamespace(secondary="secondary", primary="primary", danger="danger", success="success"),
    ui=types.SimpleNamespace(View=_View, Button=_Button))
FAKE_AIOHTTP = types.SimpleNamespace(ClientTimeout=lambda **kw: kw)


class _Msg:
    _next = 1000

    def __init__(self, content, kw):
        _Msg._next += 1
        self.id, self.content, self.kw, self.edits = _Msg._next, content, kw, []

    async def edit(self, **kw):
        self.edits.append(kw)


class _Channel:
    def __init__(self, cid, forbidden=False):
        self.id, self.forbidden, self.sent = cid, forbidden, []

    async def send(self, content, **kw):
        if self.forbidden:
            raise _Forbidden()
        m = _Msg(content, kw)
        self.sent.append(m)
        return m


class _Bot:
    def __init__(self, channels):
        self.channels, self.fetched = channels, []

    def get_channel(self, cid):
        return self.channels.get(cid)

    async def fetch_channel(self, cid):
        self.fetched.append(cid)
        return self.channels.get(cid)


class _Api:
    """The bot's api_get / api_post. `answers` scripts a path prefix with its
    successive answers (the last one repeats); an unscripted stamp answers
    ok, an unscripted ack acks — and an ack that answers "acked" retires the
    row from the pending list, the way the server's ack does."""

    def __init__(self, posts):
        self.posts, self.calls, self.answers = list(posts), [], {}

    async def get(self, path, timeout=8.0):
        self.calls.append(("GET", path, None))
        assert path == "/internal/channel-posts/pending", path
        return {"posts": list(self.posts)}

    async def post(self, path, params=None, timeout=None):
        self.calls.append(("POST", path, params))
        ans = None
        for prefix, seq in self.answers.items():
            if path.startswith(prefix):
                ans = seq.pop(0) if len(seq) > 1 else seq[0]
                break
        else:
            if path.endswith("/notified"):
                ans = {"status": "ok"}
            elif path == "/internal/channel-posts/ack":
                ans = {"status": "acked"}
            else:
                raise AssertionError(f"unexpected api_post {path}")
        if path == "/internal/channel-posts/ack" and isinstance(ans, dict) and ans.get("status") == "acked":
            self.posts = [p for p in self.posts if p["id"] != params["post_id"]]
        return ans


class _Resp:
    def __init__(self, status, body):
        self.status, self._body = status, body

    async def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Session:
    def __init__(self, status, body):
        self.status, self.body, self.posts = status, body, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return _Resp(self.status, self.body)


class _Interaction:
    def __init__(self, cid, user_id=4242, itype=3, message=None):
        self.type, self.data, self.message = itype, {"custom_id": cid}, message
        self.user = types.SimpleNamespace(id=user_id, name="mod", display_name="Mod Name")
        self.response = types.SimpleNamespace(sent=[], deferred=[])
        self.followup = types.SimpleNamespace(sent=[])

        async def send_message(text, **kw):
            self.response.sent.append((text, kw))

        async def defer(**kw):
            self.response.deferred.append(kw)

        async def fsend(text, **kw):
            self.followup.sent.append((text, kw))
        self.response.send_message, self.response.defer, self.followup.send = send_message, defer, fsend


# ── lifting ───────────────────────────────────────────────────────────────

def _lift():
    picked, seen = [], set()
    for node in TREE.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in WANT_ASSIGN:
                    picked.append(node)
                    seen.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in WANT_ASSIGN:
            picked.append(node)
            seen.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in WANT_FUNC:
            fn = copy.deepcopy(node)
            fn.decorator_list = []                                   # @tasks.loop / @bot.event are the harness's
            picked.append(fn)
            seen.add(node.name)
    assert seen == WANT_FUNC | WANT_ASSIGN, (WANT_FUNC | WANT_ASSIGN) - seen
    return picked


_NO_SESSION_GIVEN = object()


def _bot_ns(api, bot, session=_NO_SESSION_GIVEN, out=None):
    """A fresh namespace per test: the lifted code plus the module globals it
    reaches for. `_channel_post_sent` is real state, so it is never shared.
    The loop and the click path both bail without an http session, so one
    is present unless a test passes session=None on purpose."""
    if session is _NO_SESSION_GIVEN:
        session = _Session(200, {})
    out = out if out is not None else []
    ns = {"discord": FAKE_DISCORD, "aiohttp": FAKE_AIOHTTP, "bot": bot, "api_get": api.get, "api_post": api.post,
          "http_session": session, "API_SECRET_KEY": "internal-key", "API_BASE_URL": "http://api:8000",
          "print": lambda *a, **k: out.append(" ".join(str(x) for x in a))}
    exec(compile(ast.Module(body=_lift(), type_ignores=[]), SRC, "exec"), ns)
    return ns


def _case_post(case_id, pid=1, channel="555"):
    return {"id": pid, "channel_id": channel, "content": f"{main.MAIL_CASE_MARKER}{case_id}]\nReport: spam\nfrom X"}


def _plain_post(pid=2, channel="555"):
    return {"id": pid, "channel_id": channel, "content": "Tournament starts soon"}


@pytest.fixture(scope="module")
def bot():
    return _bot_ns(_Api([]), _Bot({}))


# ── the pure helpers, against the api's constants ─────────────────────────

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


# ── the outbox loop, executed ─────────────────────────────────────────────

def test_lifted_functions_are_the_wired_ones():
    """Reachability: the functions executed below are the ones the harness
    actually schedules, not same-named orphans."""
    def deco(name):
        fn = next(n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
        return [ast.unparse(d) for d in fn.decorator_list]
    assert deco("poll_channel_posts") == ["tasks.loop(seconds=30)"]
    assert deco("on_interaction") == ["bot.event"]
    assert re.search(r"poll_channel_posts\.start\(\)", TEXT)


def test_tick_posts_with_buttons_then_stamps_then_acks_in_order():
    case_id = str(uuid.uuid4())
    api = _Api([_case_post(case_id, 1), _plain_post(2)])
    ch = _Channel(555)
    ns = _bot_ns(api, _Bot({555: ch}))
    _run(ns["poll_channel_posts"]())
    assert [m.content for m in ch.sent] == ["Report: spam\nfrom X", "Tournament starts soon"]   # marker stripped
    view = ch.sent[0].kw["view"]
    assert [b.kw["custom_id"] for b in view.children] == [f"modcase:{k}:{case_id}" for k, *_ in ns["_MODCASE_BUTTONS"]]
    assert view.timeout is None and "view" not in ch.sent[1].kw       # a plain post carries no buttons
    assert ch.sent[0].kw["allowed_mentions"].kw == {"users": True, "everyone": False, "roles": False}
    assert [c for c in api.calls if c[0] == "POST"] == [
        ("POST", f"/internal/moderation-cases/{case_id}/notified", None),    # M1: the stamp precedes the ack
        ("POST", "/internal/channel-posts/ack", {"post_id": 1}),
        ("POST", "/internal/channel-posts/ack", {"post_id": 2})]
    assert ns["_channel_post_sent"] == {} and api.posts == []


def test_failed_stamp_leaves_the_row_pending_and_the_retry_stamps_without_reposting():
    case_id = str(uuid.uuid4())
    api = _Api([_case_post(case_id, 1), _plain_post(2)])
    api.answers[f"/internal/moderation-cases/{case_id}/notified"] = [None, {"status": "ok"}]
    ch = _Channel(555)
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    _run(ns["poll_channel_posts"]())
    assert len(ch.sent) == 1 and api.posts == [_case_post(case_id, 1), _plain_post(2)]   # nothing acked; order held
    assert not any(c[1] == "/internal/channel-posts/ack" for c in api.calls)             # the ack never precedes the stamp
    assert ns["_channel_post_sent"] == {1: ch.sent[0].id} and any("will retry" in line for line in out)
    _run(ns["poll_channel_posts"]())                                                     # next tick
    assert [m.content for m in ch.sent] == ["Report: spam\nfrom X", "Tournament starts soon"]   # M2: no second copy
    assert sum(1 for c in api.calls if c[1].endswith("/notified")) == 2
    assert api.posts == [] and ns["_channel_post_sent"] == {}


def test_failed_ack_keeps_the_send_remembered_and_never_reposts():
    case_id = str(uuid.uuid4())
    api = _Api([_case_post(case_id, 1)])
    api.answers["/internal/channel-posts/ack"] = [{"status": "error"}, None, {"status": "acked"}]
    ch = _Channel(555)
    ns = _bot_ns(api, _Bot({555: ch}))
    for tick in range(3):
        _run(ns["poll_channel_posts"]())
        assert len(ch.sent) == 1
        assert (ns["_channel_post_sent"] == {}) == (tick == 2)       # remembered until the ack answers "acked"
    assert api.posts == [] and sum(1 for c in api.calls if c[1] == "/internal/channel-posts/ack") == 3
    assert sum(1 for c in api.calls if c[1].endswith("/notified")) == 3   # re-stamping is the api's no-op, not skipped here


def test_unreachable_channel_or_a_refused_send_holds_the_queue_order():
    case_id = str(uuid.uuid4())
    api = _Api([_plain_post(1, channel="404"), _case_post(case_id, 2)])
    ch = _Channel(555)
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    _run(ns["poll_channel_posts"]())
    assert ch.sent == [] and len(api.posts) == 2 and not any(c[0] == "POST" for c in api.calls)
    assert any("not found" in line for line in out)
    api = _Api([_plain_post(1), _case_post(case_id, 2)])
    ch = _Channel(555, forbidden=True)
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    _run(ns["poll_channel_posts"]())
    assert len(api.posts) == 2 and not any(c[0] == "POST" for c in api.calls) and ns["_channel_post_sent"] == {}
    assert any("forbidden" in line for line in out)


def test_nothing_happens_without_an_api_session():
    api = _Api([_plain_post(1)])
    ns = _bot_ns(api, _Bot({}), session=None)
    _run(ns["poll_channel_posts"]())
    assert api.calls == []


# ── the click path, executed ──────────────────────────────────────────────

def test_click_sends_the_clickers_discord_id_and_renders_the_servers_answer():
    case_id = str(uuid.uuid4())
    session = _Session(200, {"status": "ok", "subject_name": "Spammer", "subject_steam_id": "765",
                             "resolution": "mute:24h"})
    ns = _bot_ns(_Api([]), _Bot({}), session=session)
    msg = _Msg("[case text]", {})
    inter = _Interaction(f"modcase:mute24:{case_id}", message=msg)
    _run(ns["on_interaction"](inter))
    assert inter.response.deferred == [{"ephemeral": True}]           # acknowledged inside Discord's 3 s window
    [post] = session.posts
    assert post["url"] == f"http://api:8000/api/v1/internal/moderation-cases/{case_id}/act"
    assert post["json"] == {"actor_discord_id": "4242", "actor_name": "Mod Name", "action": "mute", "hours": 24,
                            "reason": "Discord button: Mute 24h"}
    assert post["headers"] == {"X-Internal-Key": "internal-key"} and "steam" not in str(post["json"])
    assert msg.edits and msg.edits[0]["view"] is None and "Spammer" in msg.edits[0]["content"]
    [(text, kw)] = inter.followup.sent
    assert "Mute 24h" in text and "Spammer" in text and kw["ephemeral"] is True


def test_click_refused_by_the_server_leaves_the_buttons_in_place():
    case_id = str(uuid.uuid4())
    session = _Session(403, {"detail": "not_authorised"})
    ns = _bot_ns(_Api([]), _Bot({}), session=session)
    msg = _Msg("[case text]", {})
    inter = _Interaction(f"modcase:ban:{case_id}", message=msg)
    _run(ns["on_interaction"](inter))
    assert session.posts[0]["json"]["action"] == "ban" and "hours" not in session.posts[0]["json"]
    assert msg.edits == [] and "no longer authorised" in inter.followup.sent[0][0]


def test_listener_routes_only_component_interactions_with_the_prefix():
    ns = _bot_ns(_Api([]), _Bot({}), session=_Session(200, {}))
    calls = []

    async def click(interaction, cid):
        calls.append(cid)
    ns["_modcase_click"] = click
    _run(ns["on_interaction"](_Interaction("modcase:dismiss:x", itype=2)))   # not a component interaction
    _run(ns["on_interaction"](_Interaction("modcase:dismiss:x")))
    assert calls == ["modcase:dismiss:x"]
    ns = _bot_ns(_Api([]), _Bot({}), session=_Session(200, {}))
    inter = _Interaction("modcase:nope:x")
    _run(ns["on_interaction"](inter))
    assert "Unrecognized" in inter.response.sent[0][0] and inter.response.deferred == []


def test_click_without_an_api_session_answers_not_ready():
    ns = _bot_ns(_Api([]), _Bot({}), session=None)
    inter = _Interaction(f"modcase:dismiss:{uuid.uuid4()}")
    _run(ns["on_interaction"](inter))
    assert inter.followup.sent == [("API session not ready.", {"ephemeral": True})]


def test_truthy_error_answers_are_not_success():
    """review r2: api_post answers a non-200 with {"error": <body>, "status":
    <http code>} — a TRUTHY dict whose "status" is a number, not "ok" or
    "acked". Neither the stamp nor the ack may take it for success: the row
    stays pending, the send stays remembered, nothing is re-posted, and the
    next tick that gets the real answer finishes the row."""
    case_id = str(uuid.uuid4())
    api = _Api([_case_post(case_id, 1)])
    api.answers[f"/internal/moderation-cases/{case_id}/notified"] = [{"error": "case_not_found", "status": 404}, {"status": "ok"}]
    api.answers["/internal/channel-posts/ack"] = [{"error": "boom", "status": 500}, {"status": "acked"}]
    ch = _Channel(555)
    out = []
    ns = _bot_ns(api, _Bot({555: ch}), out=out)
    _run(ns["poll_channel_posts"]())                                  # tick 0: the stamp answered an error dict
    assert len(ch.sent) == 1 and not any(c[1] == "/internal/channel-posts/ack" for c in api.calls)
    assert api.posts == [_case_post(case_id, 1)] and ns["_channel_post_sent"] == {1: ch.sent[0].id}
    assert any("will retry" in line for line in out)
    _run(ns["poll_channel_posts"]())                                  # tick 1: stamped; the ack answered an error dict
    assert len(ch.sent) == 1 and api.posts == [_case_post(case_id, 1)] and ns["_channel_post_sent"] == {1: ch.sent[0].id}
    assert sum(1 for c in api.calls if c[1] == "/internal/channel-posts/ack") == 1
    assert any("row stays pending" in line for line in out)
    _run(ns["poll_channel_posts"]())                                  # tick 2: acked, and still one post
    assert api.posts == [] and ns["_channel_post_sent"] == {} and len(ch.sent) == 1
    assert sum(1 for c in api.calls if c[1].endswith("/notified")) == 3
