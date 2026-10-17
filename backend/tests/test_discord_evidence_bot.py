"""Admin evidence report, phase 1a item 6: the bot's `/evidence` command.

discord_bot.py is not importable in a test process (it builds the bot at
import), so the `_aer_*` functions, the four subcommand callbacks and the raw
component listener are lifted out of its AST, stripped of their decorators,
and EXECUTED here against fakes for the interaction, the admin channel and the
api (the pattern of test_mail_bot.py).

  3.3  AER_WIRE, AER_ESC, the cell and own states, the games default and the
       route root equal admin_evidence.py's; the 1a decoder accepts a served
       page and refuses every schema break (missing or extra key, a slot
       added, rules not absent, an escaped code point in a display slot, a
       bool for an int, a spread slot on a window entry, flag_obs on a pair
       window, a base key in a summary cell).
  P3   (bot half) a DM, another channel and a thread are refused before any
       api call; a delayed success (the api answering after 5 s) and a delayed
       refusal publish nothing before the api answers; a non-roster actor gets
       the refusal word; an authorized actor without Manage Guild is served;
       every status word, by command and by button, with zero public sends
       and the message unchanged; the too-large controls.
  P24  pages 0, 1, the last and the last plus one by command and button; each
       zero-cohort target at pages 1 and 2 gets `not found` and posts nothing.
  5.4  `custom_id` round trip per shape at the longest arguments, within 100
       characters; other forms refused.
"""

import ast
import asyncio
import collections
import copy
import io
import json
import os
import re
import sys
import threading
import time
import types
import urllib.parse

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import admin_evidence as ae  # noqa: E402

SRC = os.path.abspath(os.path.join(HERE, "..", "discord_bot.py"))
TREE = ast.parse(open(SRC, encoding="utf-8").read())
HANDLERS = {"evidence_game", "evidence_series", "evidence_pair", "evidence_player",
            "on_interaction"}
ADMIN = 4242
OTHER_CHANNEL = 4343
DELAY_S = 5.0


# ── fakes ──────────────────────────────────────────────────────────────────

class _AllowedMentions:
    def __init__(self, **kw):
        self.kw = kw

    @classmethod
    def none(cls):
        return cls(none=True)


class _View:
    def __init__(self, timeout=None):
        self.timeout, self.children = timeout, []

    def add_item(self, item):
        self.children.append(item)


class _Button:
    def __init__(self, **kw):
        self.kw = kw


class _File:
    def __init__(self, fp, filename=None):
        self.data, self.filename = fp.read(), filename


FAKE_DISCORD = types.SimpleNamespace(
    AllowedMentions=_AllowedMentions, Interaction=object, File=_File,
    InteractionType=types.SimpleNamespace(component=3, application_command=2),
    ButtonStyle=types.SimpleNamespace(secondary="secondary"),
    ui=types.SimpleNamespace(View=_View, Button=_Button))
FAKE_AIOHTTP = types.SimpleNamespace(ClientTimeout=lambda **kw: kw)


class _Resp:
    def __init__(self, status, body, headers):
        self.status, self.headers = status, dict(headers or {})
        self._raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    async def read(self):
        return self._raw

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Api:
    """The api behind `http_session.get`: `answer(path, actor)` gives
    `(status, body, headers)` after `delay` seconds; every call and its
    answer time are logged in the shared event list."""

    def __init__(self, answer, events, delay=0.0):
        self.answer, self.events, self.delay, self.calls = answer, events, delay, []

    def get(self, url, headers=None, timeout=None):
        api = self

        class _Ctx:
            async def __aenter__(self_inner):
                api.calls.append((url, dict(headers or {})))
                api.events.append(("api asked", url))
                if api.delay:
                    await asyncio.sleep(api.delay)
                path = url[len("http://api:8000"):]
                status, body, hdrs = api.answer(path, headers.get("X-Actor-Discord-Id"))
                api.events.append(("api answered", status))
                return _Resp(status, body, hdrs)

            async def __aexit__(self_inner, *a):
                return False

        return _Ctx()


class _Message:
    def __init__(self, events):
        self.events, self.edits = events, []

    async def edit(self, **kw):
        self.edits.append(kw)
        self.events.append(("public edit", kw.get("content")))


class _Channel:
    def __init__(self, events):
        self.events, self.sent = events, []

    async def send(self, content, **kw):
        self.sent.append((content, kw))
        self.events.append(("public send", content))
        return _Message(self.events)


class _Interaction:
    def __init__(self, events, channel_id, guild=True, custom_id=None, user_id=ADMIN,
                 manage_guild=True, message=None):
        self.events = events
        self.type = 3 if custom_id else 2
        self.data = {"custom_id": custom_id} if custom_id else {}
        self.guild = object() if guild else None
        self.channel_id = channel_id
        self.channel = _Channel(events)
        self.message = message
        self.user = types.SimpleNamespace(
            id=user_id, guild_permissions=types.SimpleNamespace(manage_guild=manage_guild))
        self.ephemeral = []

        async def send_message(text, **kw):
            assert kw.get("ephemeral") is True, kw
            self.ephemeral.append(text)
            events.append(("ephemeral", text))

        async def defer(**kw):
            assert kw.get("ephemeral") is True, kw
            events.append(("deferred", kw))

        async def fsend(text, **kw):
            assert kw.get("ephemeral") is True, kw
            self.ephemeral.append(text)
            events.append(("ephemeral", text))

        self.response = types.SimpleNamespace(send_message=send_message, defer=defer)
        self.followup = types.SimpleNamespace(send=fsend)


# ── lifting ───────────────────────────────────────────────────────────────

def _wanted(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name.startswith("_aer_") or node.name in HANDLERS or \
            node.name == "AerSchemaError"
    if isinstance(node, ast.Assign):
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        return any(n.startswith(("AER_", "_AER_", "_aer_")) or n in ("BotPage", "AerItem")
                   for n in names)
    return False


def _lift():
    picked = []
    for node in TREE.body:
        if _wanted(node):
            node = copy.deepcopy(node)
            if not isinstance(node, ast.ClassDef):
                node.decorator_list = []
            picked.append(node)
    return picked


def bot_ns(api=None, events=None, mpl=False):
    """The lifted evidence code in a fresh namespace with the globals it uses.
    `mpl` stands for the bot's guarded matplotlib import (`_MPL_AVAILABLE`);
    without it every page takes the text fallback."""
    ns = {"discord": FAKE_DISCORD, "aiohttp": FAKE_AIOHTTP, "json": json, "re": re,
          "urllib": urllib, "collections": collections, "asyncio": asyncio, "io": io,
          "os": os, "__file__": SRC, "_MPL_AVAILABLE": mpl,
          "_mpl_render_lock": threading.Lock(),
          "http_session": api, "API_SECRET_KEY": "internal-key",
          "API_BASE_URL": "http://api:8000", "ADMIN_CHANNEL_ID": ADMIN}
    exec(compile(ast.Module(body=_lift(), type_ignores=[]), SRC, "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def bot():
    return bot_ns()


# ── a served 1a page, the shape the api writes ────────────────────────────

def game_body(page=1, pages=1, shape="game"):
    base = [e for e in ae.REPORT_REGISTRY if not e.is_window][:2]
    cells = [[e.ki, 7, None, None, "none", None, None, None, "ok"] for e in base]
    return {"shape": shape, "page": page, "pages": pages,
            "subjects": [{"steam_id": "1001", "name": "Alpha"},
                         {"steam_id": "1002", "name": ae._aer_enc("B`eta")}],
            "rules": {"report": "absent"},
            "population": {"key": "all", "days": 30, "lag_s": 120, "games": 4,
                           "computed_at": "2026-10-16T00:00:00+00:00", "truncated": []},
            "baseline": {"own_games": 5, "scan": 200},
            "registry": {"fingerprint": ae.registry_fingerprint(),
                         "census": ae.registry_census()},
            "catalog": [ae._catalog_row(e) for e in base],
            "games": [{"match_id": "0" * 32, "code": "0" * 12,
                       "ended_at": "2026-10-16T00:00:00+00:00", "is_ranked": True,
                       "invalidated": None, "series_id": None, "rounds": [5, 3],
                       "seats": [{"subject": 0, "reporter": True, "cells": cells},
                                 {"subject": 1, "reporter": False, "cells": cells}],
                       "pair_cells": [],
                       "flags": [{"reason": "suspected_macro", "subject": 0, "reviewed": False,
                                  "current": True,
                                  "created_at": "2026-10-16T00:00:00+00:00"}]}]}


def summary_body(page=1, pages=3, shape="pair"):
    w = next(e for e in ae.REPORT_REGISTRY if e.is_window and e.scope == "seat")
    body = game_body(page, pages, shape)
    body["catalog"] = [ae._catalog_row(w)]
    body["games"] = []
    body["population"]["win_computed_at"] = "2026-10-16T00:00:00+00:00"
    body["windows"] = [{"oi": 0, "basis": "pair", "subj": ["seat", 0, 1], "games": 10,
                        "covered": 10, "flag_obs": 0, "newest": "a" * 12,
                        "oldest": "b" * 12}]
    body["summary"] = [{"oi": 0, "cells": [[w.ki, 10, 4.5, None, None, None, "none",
                                            None, None, None, None, None, "ok"]]}]
    return body


def _phase_leaf_breaks():
    return [
        ("rounds object", game_body,
         lambda b: b["games"][0].update(rounds={"cls": "c1"})),
        ("class word in numeric cell", game_body,
         lambda b: b["games"][0]["seats"][0]["cells"][0].__setitem__(
             ae.AER_WIRE["1a"]["seat"].index("pop_rank"), "c1")),
        ("mark object in catalog base", summary_body,
         lambda b: b["catalog"][0].update(base={"mark": True})),
        ("malformed window leaf", summary_body,
         lambda b: b["windows"][0].update(newest={"cls": "c1"})),
    ]


def run(coro):
    return asyncio.run(coro)


# ── 3.3: the seam ─────────────────────────────────────────────────────────

def test_wire_tables_and_escape_set_equal_the_api(bot):
    assert bot["AER_WIRE"] == ae.AER_WIRE
    assert bot["AER_ESC"] == ae.AER_ESC
    assert bot["AER_CELL_STATES"] == ae.CELL_STATES
    assert bot["AER_OWN_STATES"] == ae.OWN_STATES
    assert bot["AER_GAMES_DEFAULT"] == ae.DISPLAY_DEFAULTS["games"]
    assert bot["AER_ROOT"] == ae.EVIDENCE_PREFIX


def test_the_1a_decoder_accepts_a_served_page_and_refuses_every_break(bot):
    dec, err = bot["_aer_decode_response"], bot["AerSchemaError"]
    page = dec(game_body(), "1a")
    assert (page.shape, page.page, page.pages, len(page.games)) == ("game", 1, 1, 1)
    assert page.subjects[1][1] == ae._aer_enc("B`eta")
    s = dec(summary_body(), "1a")
    assert (s.shape, len(s.windows), len(s.summary), s.games) == ("pair", 1, 1, ())
    assert set(page.population) == {"key", "days", "lag_s", "games", "computed_at",
                                    "truncated"}
    assert set(s.population) == set(page.population) | {"win_computed_at"}

    def broken(mutate, maker=game_body):
        b = maker()
        mutate(b)
        with pytest.raises(err):
            dec(b, "1a")
        return True

    assert broken(lambda b: b.pop("registry"))
    assert broken(lambda b: b.update(extra=1))
    assert broken(lambda b: b["population"].update(cls="c1"))
    assert broken(lambda b: b["baseline"].update(mark="m1"))
    assert broken(lambda b: b["registry"].update(legend={}))
    assert broken(lambda b: b["population"].update(win_computed_at="now"))
    assert broken(lambda b: b["population"].pop("win_computed_at"), summary_body)
    assert broken(lambda b: b["population"].update(games=True))
    assert broken(lambda b: b["baseline"].update(scan=True))
    assert broken(lambda b: b["registry"]["census"].update(M=[True, 1]))
    assert broken(lambda b: b["games"][0]["seats"][0]["cells"][0].append("c1"))   # a cls slot
    assert broken(lambda b: b.update(rules={"report": "armed"}))
    assert broken(lambda b: b["subjects"][0].update(name="a‮b"))
    assert broken(lambda b: b["games"][0]["seats"][0]["cells"][0].__setitem__(1, "x`y"))
    assert broken(lambda b: b.update(page=True))
    assert broken(lambda b: b["games"][0]["seats"][0]["cells"][0].__setitem__(0, True))
    assert broken(lambda b: b.update(page=2))                                     # past pages
    assert broken(lambda b: b["catalog"][0].update(p50=1.0), summary_body)        # spread on a window
    assert broken(lambda b: b["windows"][0].update(subj=["pair", 0, 1], flag_obs={"n": 1}),
                  summary_body)
    assert broken(lambda b: b["summary"][0]["cells"][0].__setitem__(
        0, next(e.ki for e in ae.REPORT_REGISTRY if not e.is_window)), summary_body)
    assert broken(lambda b: b["games"][0].update(pair_cells=[[0]]))
    assert broken(lambda b: b["games"][0]["flags"][0].update(reason="x\x1b[31m"))   # raw ESC
    assert broken(lambda b: b["games"][0]["flags"][0].update(reviewed=1))
    assert broken(lambda b: b["windows"][0].update(flag_obs=True), summary_body)
    with pytest.raises(err):
        dec(game_body(), "1b")


@pytest.mark.parametrize("label,maker,mutate", _phase_leaf_breaks(),
                         ids=lambda value: value if isinstance(value, str) else None)
def test_the_1a_decoder_refuses_a_phase_leaf_of_the_wrong_type(
        bot, label, maker, mutate):
    body = maker()
    mutate(body)
    with pytest.raises(bot["AerSchemaError"]):
        bot["_aer_decode_response"](body, "1a")


# ── 5.4: the button request ───────────────────────────────────────────────

def test_custom_id_round_trips_per_shape_within_the_bound(bot):
    cid, parse = bot["_aer_custom_id"], bot["_aer_parse_custom_id"]
    reqs = [{"shape": "game", "code": "f" * 32},
            {"shape": "series", "code": "e" * 32},
            {"shape": "pair", "a": "9" * 20, "b": "8" * 20, "games": 100},
            {"shape": "player", "steam_id": "7" * 20, "games": 100}]
    longest = 0
    for req in reqs:
        for page in (0, 1, 999999):
            c = cid(req, page)
            longest = max(longest, len(c))
            assert len(c) <= bot["AER_CUSTOM_ID_MAX"]
            assert parse(c) == dict(req, page=page), c
    for bad in ("aer:x:1:1", "aer:g:abc", "aer:g:abc:1:2", "aer:g::1", "aer:o:1:2:x:1",
                "aer:p:1:x:1", "aer:g:abc:-1", "modcase:x", "", "aer:g:abc: 1"):
        assert parse(bad) is None, bad
    print("GATE 5.4: custom_id round trip per shape; longest %d of %d characters"
          % (longest, bot["AER_CUSTOM_ID_MAX"]))


# ── P3 bot half ───────────────────────────────────────────────────────────

def _served(path, actor):
    return 200, game_body(), {}


def _command(ns, interaction, shape="game"):
    args = {"game": ("evidence_game", dict(code="0" * 12)),
            "series": ("evidence_series", dict(code="0" * 12)),
            "pair": ("evidence_pair", dict(a="1001", b="1002")),
            "player": ("evidence_player", dict(steam_id="1001"))}[shape]
    return ns[args[0]](interaction, **args[1])


def _click(ns, interaction):
    return ns["on_interaction"](interaction)


def _public(events):
    return [e for e in events if e[0].startswith("public")]


def test_p3_local_gate_refuses_dm_other_channel_and_thread_before_any_api_call():
    out = []
    for label, channel, guild in (("dm", ADMIN, False), ("other channel", OTHER_CHANNEL, True),
                                  ("thread", 98765, True)):
        for via in ("command", "button"):
            events = []
            api = _Api(_served, events)
            ns = bot_ns(api, events)
            msg = _Message(events)
            if via == "command":
                it = _Interaction(events, channel, guild=guild)
                run(_command(ns, it))
            else:
                it = _Interaction(events, channel, guild=guild, custom_id="aer:g:%s:2" % ("0" * 12),
                                  message=msg)
                run(_click(ns, it))
            out.append((label, via, it.ephemeral, len(api.calls), len(_public(events)), msg.edits))
    for label, via, eph, calls, public, edits in out:
        assert (eph, calls, public, edits) == (["Evidence report refused."], 0, 0, []), (label, via)
    print("GATE p3 bot gate: dm, other channel, thread x command, button: refused, "
          "no api call, nothing public")


def test_p3_a_delayed_success_publishes_only_after_the_api_answered():
    events = []
    api = _Api(_served, events, delay=DELAY_S)
    ns = bot_ns(api, events)
    it = _Interaction(events, ADMIN)
    t0 = time.monotonic()
    run(_command(ns, it))
    took = time.monotonic() - t0
    kinds = [e[0] for e in events]
    assert kinds == ["deferred", "api asked", "api answered", "public send", "ephemeral"], kinds
    assert it.ephemeral == ["Posted."]
    content, kw = it.channel.sent[0]
    assert kw["allowed_mentions"].kw == {"none": True}
    assert [b.kw["label"] for b in kw["view"].children] == ["Prev", "Next"]
    assert api.calls[0][1]["X-Actor-Discord-Id"] == str(ADMIN)
    assert api.calls[0][1]["X-Internal-Key"] == "internal-key"
    assert took >= DELAY_S
    print("GATE p3 delayed success: api after %.1f s, one public send after it, then Posted."
          % took)


def test_p3_a_delayed_refusal_and_a_non_roster_actor_publish_nothing():
    for delay in (DELAY_S, 0.0):
        events = []
        api = _Api(lambda p, a: (403, {"detail": "refused"}, {}), events, delay=delay)
        ns = bot_ns(api, events)
        it = _Interaction(events, ADMIN, user_id=777)
        run(_command(ns, it))
        assert it.ephemeral == ["Evidence report refused."] and _public(events) == []
        assert [e[0] for e in events] == ["deferred", "api asked", "api answered", "ephemeral"]


def test_p3_an_authorized_actor_without_manage_guild_is_served():
    events = []
    api = _Api(_served, events)
    ns = bot_ns(api, events)
    it = _Interaction(events, ADMIN, manage_guild=False)
    run(_command(ns, it))
    assert it.ephemeral == ["Posted."] and len(_public(events)) == 1


WORDS = [
    ("page", 400, {"detail": "bad_argument (page)"}, {}, "Evidence report: bad argument (page)."),
    ("bad code", 400, {"detail": "bad_argument"}, {}, "Evidence report: bad argument."),
    ("ambiguous", 400, {"detail": "bad_argument (code ambiguous; use the full id)"}, {},
     "Evidence report: bad argument (code ambiguous; use the full id)."),
    ("not found", 404, {"detail": "not_found"}, {}, "Evidence report: not found."),
    ("replica", 409, {"detail": "primary_only"}, {}, "Evidence report: primary unavailable."),
    ("rate", 429, {"detail": "rate"}, {"Retry-After": "37"},
     "Evidence report: rate limit, retry in 37 s."),
    ("rate without a retry", 429, {"detail": "rate"}, {}, "Evidence report: unavailable (schema)."),
    ("population", 503, {"detail": "unavailable (population)"}, {},
     "Evidence report: unavailable (population)."),
    ("deadline", 503, {"detail": "deadline"}, {}, "Evidence report: unavailable (deadline)."),
    ("audit", 503, {"detail": "audit_unavailable"}, {},
     "Evidence report: unavailable (audit_unavailable)."),
    ("too large, 11-game series", 500, {"detail": "too_large"}, {},
     "Evidence report: unavailable (too_large)."),
    ("too large, 10,000-game series", 500, {"detail": "too_large"}, {},
     "Evidence report: unavailable (too_large)."),
    ("too large, forced oversized body", 500, {"detail": "too_large"}, {},
     "Evidence report: unavailable (too_large)."),
    ("server error", 500, b"Internal Server Error", {}, "Evidence report: unavailable (schema)."),
    ("schema", 200, dict(game_body(), rules={"report": "armed"}), {},
     "Evidence report: unavailable (schema)."),
    ("refused", 403, {"detail": "refused"}, {}, "Evidence report refused."),
]


def _metadata_extra(part, key):
    body = game_body()
    body[part][key] = "extra"
    return body


@pytest.mark.parametrize("via", ["command", "button"])
def test_p3_metadata_schema_failures_publish_nothing(via):
    word = "Evidence report: unavailable (schema)."
    for part, key in (("population", "cls"), ("baseline", "mark"),
                      ("registry", "legend")):
        events = []
        body = _metadata_extra(part, key)
        api = _Api(lambda p, a, b=body: (200, b, {}), events)
        ns = bot_ns(api, events)
        msg = _Message(events)
        if via == "command":
            it = _Interaction(events, ADMIN)
            run(_command(ns, it))
        else:
            it = _Interaction(events, ADMIN, custom_id="aer:g:%s:2" % ("0" * 12),
                              message=msg)
            run(_click(ns, it))
        assert (it.ephemeral, _public(events), msg.edits) == ([word], [], []), (part, key)


@pytest.mark.parametrize("via", ["command", "button"])
@pytest.mark.parametrize("label,maker,mutate", _phase_leaf_breaks(),
                         ids=lambda value: value if isinstance(value, str) else None)
def test_p3_phase_leaf_schema_failures_publish_nothing(via, label, maker, mutate):
    word = "Evidence report: unavailable (schema)."
    events = []
    body = maker()
    mutate(body)
    api = _Api(lambda p, a: (200, body, {}), events)
    ns = bot_ns(api, events)
    msg = _Message(events)
    if via == "command":
        it = _Interaction(events, ADMIN)
        run(_command(ns, it))
    else:
        it = _Interaction(events, ADMIN, custom_id="aer:g:%s:2" % ("0" * 12), message=msg)
        run(_click(ns, it))
    assert (it.ephemeral, _public(events), msg.edits) == ([word], [], []), label


@pytest.mark.parametrize("via", ["command", "button"])
def test_p3_every_status_word_by_command_and_button_publishes_nothing(via):
    got = []
    for label, status, body, headers, word in WORDS:
        events = []
        api = _Api(lambda p, a, s=status, b=body, h=headers: (s, b, h), events)
        ns = bot_ns(api, events)
        msg = _Message(events)
        if via == "command":
            it = _Interaction(events, ADMIN)
            run(_command(ns, it, "series"))
        else:
            it = _Interaction(events, ADMIN, custom_id="aer:s:%s:2" % ("0" * 12), message=msg)
            run(_click(ns, it))
        got.append((label, it.ephemeral, len(_public(events)), msg.edits))
    want = [(label, [word], 0, []) for label, _s, _b, _h, word in WORDS]
    assert got == want
    events = []
    ns = bot_ns(None, events)                      # no session: the api is unreachable
    it = _Interaction(events, ADMIN)
    run(_command(ns, it))
    assert it.ephemeral == ["Evidence report: api unreachable."] and _public(events) == []
    print("GATE p3 words (%s): %d words, each ephemeral, zero public sends, message unchanged"
          % (via, len(WORDS) + 1))


# ── P24 pagination ────────────────────────────────────────────────────────

LAST = 4


def _paged(path, actor):
    """A game-shaped api with LAST pages that refuses a page outside 1..LAST
    exactly as the api does, and two empty targets."""
    page = int(re.search(r"[?&]page=(-?\d+)", path).group(1))
    if "/empty" in path or "1009" in path:
        return 404, {"detail": "not_found"}, {}
    if not 1 <= page <= LAST:
        return 400, {"detail": "bad_argument (page)"}, {}
    return 200, game_body(page, LAST, "series"), {}


def test_p24_pages_by_command_and_button():
    out = []
    for page in (0, 1, LAST, LAST + 1):
        events = []
        api = _Api(_paged, events)
        ns = bot_ns(api, events)
        it = _Interaction(events, ADMIN)
        run(ns["evidence_series"](it, code="0" * 12, page=page))
        cmd = (it.ephemeral, len(_public(events)))
        events = []
        api = _Api(_paged, events)
        ns = bot_ns(api, events)
        msg = _Message(events)
        it = _Interaction(events, ADMIN, custom_id="aer:s:%s:%d" % ("0" * 12, page), message=msg)
        run(_click(ns, it))
        out.append((page, cmd, (it.ephemeral, len(msg.edits)), msg.edits))
    by = {p: (c, b, e) for p, c, b, e in out}
    for p in (0, LAST + 1):
        assert by[p][0] == (["Evidence report: bad argument (page)."], 0), p
        assert by[p][1] == (["Evidence report: bad argument (page)."], 0), p
    for p in (1, LAST):
        assert by[p][0] == (["Posted."], 1) and by[p][1] == (["Posted."], 1), p
        view = by[p][2][0]["view"]
        prev, nxt = view.children
        assert prev.kw["disabled"] is (p == 1) and nxt.kw["disabled"] is (p == LAST)
        assert by[p][2][0]["attachments"] == []
    # each zero-cohort target at pages 1 and 2: not found, nothing posted
    for target in ({"shape": "series", "code": "empty"}, {"shape": "player", "steam_id": "1009",
                                                          "games": 10}):
        for page in (1, 2):
            events = []
            api = _Api(_paged, events)
            ns = bot_ns(api, events)
            it = _Interaction(events, ADMIN)
            run(ns["_aer_command"](it, dict(target, page=page)))
            assert it.ephemeral == ["Evidence report: not found."] and _public(events) == []
            events = []
            api = _Api(_paged, events)
            ns = bot_ns(api, events)
            msg = _Message(events)
            it = _Interaction(events, ADMIN, custom_id=ns["_aer_custom_id"](target, page),
                              message=msg)
            run(_click(ns, it))
            assert it.ephemeral == ["Evidence report: not found."] and msg.edits == []
    print("GATE p24: pages 0 and %d refused by command and button, 1 and %d served with "
          "Prev/Next disabled at the ends; zero cohorts at pages 1, 2: not found, nothing posted"
          % (LAST + 1, LAST))


def test_the_api_path_carries_the_request_as_typed(bot):
    path = bot["_aer_path"]
    assert path({"shape": "game", "code": "ab/../x", "page": 1}) == \
        ae.EVIDENCE_PREFIX + "game/ab%2F..%2Fx?page=1"
    assert path({"shape": "pair", "a": "1", "b": "2", "games": 10, "page": 3}) == \
        ae.EVIDENCE_PREFIX + "pair?a=1&b=2&games=10&page=3"
    assert path({"shape": "player", "steam_id": "5", "games": 7, "page": 0}) == \
        ae.EVIDENCE_PREFIX + "player/5?games=7&page=0"
