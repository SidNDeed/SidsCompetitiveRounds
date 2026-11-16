"""MODLOG-1 ruling 7: the Discord /modlog command, lifted from discord_bot.py's
AST (the evidence bot tests' method) and run against a fake api.

Pages for a player with twelve records of five kinds, for a player with none
and for each api error; every message under 2000 characters; the gate on the
command and again on every button press; the search kept whole in the
button's id (a colon cannot split it) or refused at the command; the action
choices equal to the api's words and labels.
"""
import ast
import asyncio
import copy
import json
import os
import sys
import types
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import modlog  # noqa: E402

SRC = os.path.abspath(os.path.join(HERE, "..", "discord_bot.py"))
TREE = ast.parse(open(SRC, encoding="utf-8").read())
ADMIN = 4242
OTHER = 4343
PLAYER = "76561190420000777"
ASKER = 555000111


class _View:
    def __init__(self, timeout=None):
        self.timeout, self.children = timeout, []

    def add_item(self, item):
        self.children.append(item)


class _Button:
    def __init__(self, **kw):
        self.kw = kw


class _Mentions:
    @classmethod
    def none(cls):
        return cls()


FAKE_DISCORD = types.SimpleNamespace(
    AllowedMentions=_Mentions, Interaction=object,
    ButtonStyle=types.SimpleNamespace(secondary="secondary"),
    ui=types.SimpleNamespace(View=_View, Button=_Button))
FAKE_AIOHTTP = types.SimpleNamespace(ClientTimeout=lambda **kw: kw)


class _Resp:
    def __init__(self, status, body):
        self.status = status
        self._raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    async def read(self):
        return self._raw

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Api:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, list(params or []), dict(headers or {})))
        if isinstance(self.answer, Exception):
            raise self.answer
        return _Resp(*self.answer(dict(params or [])))


class _Inter:
    def __init__(self, channel_id=ADMIN, guild=True):
        self.guild = object() if guild else None
        self.channel_id = channel_id
        self.user = types.SimpleNamespace(id=ASKER)
        self.sent, self.edits, self.deferred = [], [], []

        async def send_message(text, **kw):
            assert kw.get("ephemeral") is True, kw
            self.sent.append((text, kw))

        async def defer(**kw):
            self.deferred.append(kw)

        async def fsend(text, **kw):
            assert kw.get("ephemeral") is True, kw
            self.sent.append((text, kw))

        async def edit(**kw):
            self.edits.append(kw)
        self.response = types.SimpleNamespace(send_message=send_message, defer=defer)
        self.followup = types.SimpleNamespace(send=fsend)
        self.edit_original_response = edit


def _lift():
    picked = []
    for node in TREE.body:
        name = getattr(node, "name", None)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                name.startswith("_modlog_") or name in ("_aer_local_gate", "_escape_md")):
            node = copy.deepcopy(node)
            node.decorator_list = []
            picked.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id.startswith(("MODLOG_", "_MD_"))
                for t in node.targets):
            picked.append(copy.deepcopy(node))
    return picked


def bot(answer):
    api = _Api(answer)
    ns = {"discord": FAKE_DISCORD, "aiohttp": FAKE_AIOHTTP, "json": json, "urllib": urllib,
          "re": __import__("re"), "datetime": datetime, "timezone": timezone, "timedelta": timedelta,
          "http_session": api, "API_SECRET_KEY": "internal-key", "API_BASE_URL": "http://api:8000",
          "ADMIN_CHANNEL_ID": ADMIN}
    exec(compile(ast.Module(body=_lift(), type_ignores=[]), SRC, "exec"), ns)
    return ns, api


KINDS = [("ban", "griefing"), ("chat_mute", "insults"), ("chat_automute", None),
         ("record_exclude", "lag abuse"), ("flag_review", None)]


def twelve_records(params):
    """The api's answer for PLAYER: twelve records of five kinds, paged as
    the route pages them (newest first)."""
    rows = []
    for i in range(12):
        word, why = KINDS[i % 5]
        rows.append({"id": "r%d" % i, "at": "2026-11-01T%02d:00:00Z" % (11 - i), "action": word,
                     "action_label": modlog.label(word),
                     "actor": "system" if word == "chat_automute" else "76561190420000001",
                     "actor_name": "System" if word == "chat_automute" else "Mod *Alpha*",
                     "players": [{"steam_id": PLAYER, "name": "Fixture_Player"}],
                     "reason": (why + " " + "x" * 300) if why == "insults" else why,
                     "sentence": modlog.sentence(word, {"duration_minutes": 60}),
                     "target_steam_id": PLAYER, "target_match_id": None,
                     "target_series_id": None, "details": {}})
    if params.get("dir") == "asc":
        rows.reverse()
    off, lim = int(params["offset"]), int(params["limit"])
    counts = {}
    for r in rows:
        counts[r["action"]] = counts.get(r["action"], 0) + 1
    return 200, {"total": 12, "limit": lim, "offset": off, "sort": params["sort"], "dir": params["dir"],
                 "counts_by_action": [{"action": a, "label": modlog.label(a), "count": n}
                                      for a, n in counts.items()],
                 "player": {"steam_id": PLAYER, "name": "Fixture_Player"},
                 "rows": rows[off:off + lim]}


def run(coro):
    return asyncio.run(coro)


def test_twelve_records_two_pages_and_the_buttons(capsys):
    ns, api = bot(twelve_records)
    it = _Inter()
    run(ns["_modlog_command"](it, PLAYER, "", "", "n"))
    (text, kw), = it.sent
    assert len(text) < 2000
    assert "12 records, page 1 of 2, newest first" in text
    assert text.count("\n") == 12      # name, page line, totals, ten rows
    assert "Fixture\\_Player" in text and "Mod \\*Alpha\\*" in text
    nxt = [b.kw for b in kw["view"].children if b.kw["label"] == "Next"][0]
    assert not nxt["disabled"]
    assert api.calls[0][2] == {"X-Internal-Key": "internal-key", "X-Actor-Discord-Id": str(ASKER)}
    assert ("offset", "0") in api.calls[0][1] and ("limit", "10") in api.calls[0][1]
    click = _Inter()
    run(ns["_modlog_click"](click, nxt["custom_id"]))
    (edit,) = click.edits
    assert "page 2 of 2" in edit["content"] and edit["content"].count("\n") == 4   # name, page line, totals, two rows
    assert ("offset", "10") in api.calls[1][1]
    prev = [b.kw for b in edit["view"].children if b.kw["label"] == "Previous"][0]
    assert not prev["disabled"]
    with capsys.disabled():
        print("\nMODLOG-BOT-PAGE-1\n" + text + "\nMODLOG-BOT-PAGE-2\n" + edit["content"])


def test_no_records_is_one_plain_sentence():
    def empty(params):
        return 200, {"total": 0, "counts_by_action": [], "limit": 10, "offset": 0, "sort": "time",
                     "dir": "desc", "rows": [], "player": {"steam_id": PLAYER, "name": "Quiet One"}}
    ns, _ = bot(empty)
    it = _Inter()
    run(ns["_modlog_command"](it, "Quiet One", "", "", "n"))
    (text, kw), = it.sent
    assert text == "No moderator action is on record for **Quiet One** (`%s`)." % PLAYER
    assert "view" not in kw


@pytest.mark.parametrize("status,body,want", [
    (403, {"detail": "refused"}, "MODLOG_REFUSED"),
    (404, {"detail": "player_not_found"}, "MODLOG_NOT_FOUND"),
    (409, {"detail": "player_ambiguous"}, "MODLOG_AMBIGUOUS"),
    (500, b"oops", None),
    (200, {"rows": "nope"}, "MODLOG_SCHEMA"),
])
def test_api_errors_are_plain_sentences(status, body, want, capsys):
    ns, _ = bot(lambda params: (status, body))
    it = _Inter()
    run(ns["_modlog_command"](it, PLAYER, "", "", "n"))
    (text, kw), = it.sent
    if want:
        assert text == ns[want]
    else:
        assert text.startswith("The moderator log failed on the server (status 500).")
    with capsys.disabled():
        print("\nMODLOG-BOT-ERROR %d: %s" % (status, text))


def test_unreachable_api():
    ns, _ = bot(OSError("down"))
    it = _Inter()
    run(ns["_modlog_command"](it, PLAYER, "", "", "n"))
    assert it.sent[0][0] == ns["MODLOG_UNREACHABLE"]


@pytest.mark.parametrize("channel,guild", [(OTHER, True), (ADMIN, False)])
def test_the_gate_on_the_command_and_on_every_press(channel, guild):
    ns, api = bot(twelve_records)
    it = _Inter(channel, guild)
    run(ns["_modlog_command"](it, PLAYER, "", "", "n"))
    assert it.sent == [(ns["MODLOG_GATE"], {"ephemeral": True})]
    press = _Inter(channel, guild)
    run(ns["_modlog_click"](press, ns["_modlog_custom_id"](PLAYER, "n", None, 1, "")))
    assert press.sent == [(ns["MODLOG_GATE"], {"ephemeral": True})] and press.edits == []
    assert api.calls == []


def test_the_search_survives_the_button_and_a_colon_cannot_split_it():
    ns, api = bot(twelve_records)
    cid = ns["_modlog_custom_id"](PLAYER, "o", 3, 1, "a:b:c 50%")
    assert ns["_modlog_parse_custom_id"](cid) == (PLAYER, "o", 3, 1, "a:b:c 50%")
    for bad in ("modlog:1:n:-:0:", "modlog:%s:z:-:0:" % PLAYER, "modlog:%s:n:99:0:" % PLAYER,
                "modlog:%s:n:-:x:" % PLAYER, "other:%s:n:-:0:" % PLAYER):
        assert ns["_modlog_parse_custom_id"](bad) is None, bad


def test_a_search_too_long_or_too_wide_is_refused_never_cut():
    ns, api = bot(twelve_records)
    it = _Inter()
    run(ns["_modlog_command"](it, PLAYER, "", "x" * 65, "n"))
    assert it.sent[0][0] == ns["MODLOG_SEARCH_LONG"]
    it = _Inter()
    run(ns["_modlog_command"](it, PLAYER, "", "é" * 30, "n"))      # 180 characters encoded
    assert it.sent[0][0] == ns["MODLOG_SEARCH_WIDE"]
    assert api.calls == []


def test_every_page_stays_under_2000_characters():
    def long_rows(params):
        status, body = twelve_records(params)
        for r in body["rows"]:
            r["reason"], r["sentence"], r["actor_name"] = "r" * 256, "s" * 600, "n" * 64
        return status, body
    ns, _ = bot(long_rows)
    it = _Inter()
    run(ns["_modlog_command"](it, PLAYER, "", "", "n"))
    assert len(it.sent[0][0]) <= 1990


def test_the_action_choices_are_the_apis_words_and_labels():
    ns, _ = bot(twelve_records)
    pairs = ns["MODLOG_BOT_ACTIONS"]
    assert len(pairs) <= 25                      # Discord's limit on choices
    for word, label in pairs:
        assert modlog.ACTIONS.get(word) == label, word
    assert not {w for w, _ in pairs} & modlog.READ_ACTIONS
