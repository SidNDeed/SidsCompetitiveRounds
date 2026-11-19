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
import re
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
TEXT = open(SRC, encoding="utf-8").read()
TREE = ast.parse(TEXT)
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
                name.startswith("_modlog_") or name in ("_aer_local_gate", "_escape_md", "_escape_text")):
            node = copy.deepcopy(node)
            node.decorator_list = []
            picked.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id.startswith(("MODLOG_", "_MD_", "_modlog_", "_TEXT_"))
                for t in node.targets):
            picked.append(copy.deepcopy(node))
    return picked


def bot(answer):
    api = _Api(answer)
    ns = {"discord": FAKE_DISCORD, "aiohttp": FAKE_AIOHTTP, "json": json, "urllib": urllib,
          "re": __import__("re"), "time": __import__("time"),
          "secrets": __import__("secrets"), "datetime": datetime, "timezone": timezone, "timedelta": timedelta,
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
        rows.append({"id": "r%d" % i, "key": "k%d" % i, "at": "2026-11-01T%02d:00:00Z" % (11 - i), "action": word,
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
    assert "offset" not in params
    lim = int(params["limit"])
    off = [r["key"] for r in rows].index(params["after"]) + 1 if "after" in params else 0
    counts = {}
    for r in rows:
        counts[r["action"]] = counts.get(r["action"], 0) + 1
    nxt = rows[off + lim - 1]["key"] if off + lim < len(rows) else None
    return 200, {"total": 12, "limit": lim, "next": nxt, "sort": params["sort"], "dir": params["dir"],
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
    assert not nxt.get("disabled")
    assert api.calls[0][2] == {"X-Internal-Key": "internal-key", "X-Actor-Discord-Id": str(ASKER)}
    assert ("limit", "10") in api.calls[0][1]
    assert not [p for p, _ in api.calls[0][1] if p in ("offset", "after")]
    assert [b.kw["label"] for b in kw["view"].children] == ["Previous", "Next"]
    assert kw["view"].children[0].kw["disabled"] is True       # Previous on the first page
    click = _Inter()
    run(ns["_modlog_click"](click, nxt["custom_id"]))
    (edit,) = click.edits
    assert "page 2 of 2" in edit["content"] and edit["content"].count("\n") == 4   # name, page line, totals, two rows
    assert ("after", "k9") in api.calls[1][1]          # after the last row shown
    last = edit["view"].children                      # the last page: Previous only
    assert [b.kw["label"] for b in last] == ["Previous"] and last[0].kw["disabled"] is False
    with capsys.disabled():
        print("\nMODLOG-BOT-PAGE-1\n" + text + "\nMODLOG-BOT-PAGE-2\n" + edit["content"])


def test_no_records_is_one_plain_sentence():
    def empty(params):
        return 200, {"total": 0, "counts_by_action": [], "limit": 10, "next": None, "sort": "time",
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
    tok = ns["_modlog_hold"]((PLAYER, "n", None, ""))
    for way in "pn":
        press = _Inter(channel, guild)
        run(ns["_modlog_click"](press, "modlog:%s:%s" % (tok, way)))
        assert press.sent == [(ns["MODLOG_GATE"], {"ephemeral": True})] and press.edits == []
    assert api.calls == []


def test_the_view_is_held_under_one_token_and_a_malformed_id_is_not_read():
    ns, api = bot(twelve_records)
    base = (PLAYER, "o", 3, "a:b:c 50% " + "é" * 30)
    tok = ns["_modlog_hold"](base)
    for way in "pn":
        cid = "modlog:%s:%s" % (tok, way)
        assert len(cid) <= 100 and ns["_modlog_parse_custom_id"](cid) == (tok, way)
    assert ns["_modlog_held"][tok]["base"] == base
    for bad in ("modlog:", "modlog:" + tok, "modlog:%s:x" % tok, "modlog:%s:p:n" % tok,
                "modlog:0123456789abcdef01234567:n", "other:x", None):
        assert ns["_modlog_parse_custom_id"](bad) is None, bad


def test_a_search_too_long_is_refused_never_cut_and_a_wide_one_is_served():
    ns, api = bot(twelve_records)
    it = _Inter()
    run(ns["_modlog_command"](it, PLAYER, "", "x" * 65, "n"))
    assert it.sent[0][0] == ns["MODLOG_SEARCH_LONG"]
    assert api.calls == []
    it = _Inter()
    run(ns["_modlog_command"](it, PLAYER, "", "é" * 30, "n"))      # 180 characters encoded
    assert ("q", "é" * 30) in api.calls[0][1]          # the button holds it, not its custom_id


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


# -- fix A9: every row of a page is shown --------------------------------------

MD = "*_~`|>\\"


def markdown_records(params):
    """Twelve rows whose actor names (40 characters) and reasons (256) are
    made of markdown characters; each row's own minute marks its time."""
    rows = []
    for i in range(12):
        rows.append({"id": "m%d" % i, "key": "k%d" % i, "at": "2026-11-01T10:%02d:00Z" % (59 - i),
                     "action": "ban", "action_label": "Ban", "actor": "76561190420000001",
                     "actor_name": (MD * 6)[:40], "players": [{"steam_id": PLAYER, "name": "P"}],
                     "reason": (MD * 37)[:256], "sentence": (MD * 30)[:200],
                     "target_steam_id": PLAYER, "target_match_id": None,
                     "target_series_id": None, "details": {}})
    if "after" in params:
        start = [r["key"] for r in rows].index(params["after"]) + 1
    else:
        start = int(params.get("offset") or 0)
    lim = int(params["limit"])
    page = rows[start:start + lim]
    nxt = page[-1]["key"] if start + lim < len(rows) else None
    return 200, {"total": 12, "limit": lim, "sort": params["sort"], "dir": params["dir"],
                 "next": nxt, "offset": start,
                 "counts_by_action": [{"action": "ban", "label": "Ban", "count": 12}],
                 "player": {"steam_id": PLAYER, "name": "P"}, "rows": page}


def _stamp(i):
    dt = datetime(2026, 11, 1, 10, 59 - i, tzinfo=timezone.utc)
    return "<t:%d:f>" % int(dt.timestamp())


def _a9_pages(ns, api):
    it = _Inter()
    run(ns["_modlog_command"](it, PLAYER, "", "", "n"))
    (text, kw), = it.sent
    nxt = [b.kw for b in kw["view"].children if b.kw["label"] == "Next"][0]
    click = _Inter()
    run(ns["_modlog_click"](click, nxt["custom_id"]))
    return text, click.edits[0]["content"]


def test_a9_ten_rows_of_markdown_characters_all_appear_inside_the_limit(capsys):
    ns, api = bot(markdown_records)
    first, second = _a9_pages(ns, api)
    assert len(first) <= 2000 and len(first) <= ns["MODLOG_MSG_MAX"], len(first)
    assert [_stamp(i) in first for i in range(10)] == [True] * 10, first
    assert "…" in first                                  # a shortened row carries the mark
    assert _stamp(10) in second and _stamp(9) not in second, second
    for line in first.split("\n"):
        tail = len(line) - len(line.rstrip("\\"))
        assert tail % 2 == 0 or line.endswith("…"), line   # no escape pair is cut
    with capsys.disabled():
        print("\nMODLOG-A9-PAGE length=%d" % len(first))


def test_a9_mutant_without_the_row_budget_is_red(monkeypatch):
    ns, api = bot(markdown_records)
    ns["_modlog_row_budget"] = lambda *a, **k: 10 ** 6
    with pytest.raises(AssertionError) as e:
        first, _ = _a9_pages(ns, api)
        assert [_stamp(i) in first for i in range(10)] == [True] * 10
    print("\nMUTANT-RED A9 budget removed: %s" % str(e.value).splitlines()[0][:120])


# -- J5: Previous returns; the store of views is bounded ------------------------

def n_records(n):
    """The api's answer for PLAYER with `n` records, newest first, paged by
    key; each row's own minute and moderator name mark it."""
    t0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

    def answer(params):
        rows = []
        for i in range(n):
            word, why = KINDS[i % 5]
            rows.append({"id": "q%d" % i, "key": "k%d" % i,
                         "at": (t0 - timedelta(minutes=i)).isoformat(), "action": word,
                         "action_label": modlog.label(word), "actor": "76561190420000001",
                         "actor_name": "Mod %d" % i, "players": [{"steam_id": PLAYER, "name": "P"}],
                         "reason": why, "sentence": modlog.sentence(word, {"duration_minutes": 60}),
                         "target_steam_id": PLAYER, "target_match_id": None,
                         "target_series_id": None, "details": {}})
        start = [r["key"] for r in rows].index(params["after"]) + 1 if "after" in params else 0
        lim = int(params["limit"])
        page = rows[start:start + lim]
        nxt = page[-1]["key"] if start + lim < len(rows) else None
        return 200, {"total": n, "limit": lim, "next": nxt, "sort": params["sort"], "dir": params["dir"],
                     "counts_by_action": [{"action": "ban", "label": "Ban", "count": n}],
                     "player": {"steam_id": PLAYER, "name": "Fixture_Player"}, "rows": page}
    return answer


def _first(ns):
    it = _Inter()
    run(ns["_modlog_command"](it, PLAYER, "", "", "n"))
    (text, kw), = it.sent
    return text, kw.get("view")


def _press(ns, view, label):
    """Press the button `label` of `view`: (the edited text or None, the new
    view, every message sent)."""
    b = [c.kw for c in view.children if c.kw["label"] == label][0]
    it = _Inter()
    run(ns["_modlog_click"](it, b["custom_id"]))
    if not it.edits:
        return None, view, it.sent
    return it.edits[0]["content"], it.edits[0]["view"], it.sent


def _walk(ns, moves):
    text, view = _first(ns)
    shown = [text]
    for label in moves:
        text, view, _ = _press(ns, view, label)
        shown.append(text)
    return shown, view


def _mutant(ns, fname, old, new):
    """Redefine the lifted function `fname` in `ns` from its own source with
    `old` (which must stand there exactly once) replaced by `new`."""
    node = [n for n in TREE.body if getattr(n, "name", None) == fname][0]
    src = ast.get_source_segment(TEXT, node)
    assert src.count(old) == 1, (fname, old)
    exec(compile(src.replace(old, new), SRC, "exec"), ns)


def j5_forward_and_back(ns, api):
    shown, _ = _walk(ns, ["Next", "Next", "Previous", "Previous"])
    assert "page 1 of 3" in shown[0] and "page 2 of 3" in shown[1] and "page 3 of 3" in shown[2], shown
    assert len(set(shown[:3])) == 3
    assert shown[3] == shown[1] and shown[4] == shown[0], shown
    afters = [dict(c[1]).get("after") for c in api.calls]
    assert afters == [None, "k9", "k19", "k9", None], afters


def test_j5_forward_two_pages_and_back_two_show_the_same_rows():
    ns, api = bot(n_records(25))
    j5_forward_and_back(ns, api)


def test_j5_mutant_previous_without_the_kept_key_is_red():
    ns, api = bot(n_records(25))
    _mutant(ns, "_modlog_click", 'page = max(0, held["page"] - 1)\n        after = held["afters"][page]',
            'page = max(0, held["page"] - 1)\n        after = ""')
    with pytest.raises(AssertionError) as e:
        j5_forward_and_back(ns, api)
    print("\nMUTANT-RED J5 previous without the kept key: %s" % str(e.value).splitlines()[0][:120])


def j5_back_on_the_first_page(ns, api):
    first, view = _first(ns)
    assert [c.kw["disabled"] for c in view.children if c.kw["label"] == "Previous"] == [True]
    again, view2, sent = _press(ns, view, "Previous")
    assert again == first and sent == [], (again, sent)
    assert [c.kw["label"] for c in view2.children] == ["Previous", "Next"]
    shown, _ = _walk(ns, ["Next", "Previous", "Previous"])
    assert shown[2] == shown[0] and shown[3] == shown[0], shown
    assert all(dict(c[1]).get("after") is None for i, c in enumerate(api.calls) if i in (0, 1, 2, 4, 5))


def test_j5_back_on_the_first_page_stays_on_it():
    ns, api = bot(n_records(25))
    j5_back_on_the_first_page(ns, api)


def test_j5_mutant_previous_without_the_first_page_floor_is_red():
    ns, api = bot(n_records(25))
    _mutant(ns, "_modlog_click", 'page = max(0, held["page"] - 1)', 'page = held["page"] - 1')
    with pytest.raises(AssertionError) as e:
        j5_back_on_the_first_page(ns, api)
    print("\nMUTANT-RED J5 no first-page floor: %s" % str(e.value).splitlines()[0][:120])


def j5_a_view_not_held_is_one_sentence(ns, api):
    _, view = _first(ns)
    tok = view.children[0].kw["custom_id"].split(":")[1]
    calls = len(api.calls)
    # a token never held, and a view held by another run of the bot (a restart)
    other, _ = bot(n_records(25))
    for cid in ("modlog:0123456789abcdef01234567:n", "modlog:%s:p" % tok):
        it = _Inter()
        run(other["_modlog_click"](it, cid))
        assert it.sent == [(ns["MODLOG_EXPIRED"], {"ephemeral": True})] and it.edits == [], cid
    # a view unused for longer than its age
    ns["_modlog_held"][tok]["exp"] = 0
    for label in ("Next", "Previous"):
        text, _, sent = _press(ns, view, label)
        assert text is None and sent == [(ns["MODLOG_EXPIRED"], {"ephemeral": True})], (label, text, sent)
    assert len(api.calls) == calls


def test_j5_a_view_the_bot_no_longer_holds_answers_one_sentence():
    ns, api = bot(n_records(25))
    j5_a_view_not_held_is_one_sentence(ns, api)
    assert ns["MODLOG_EXPIRED"] == "This moderator log view has ended. Run /modlog again to read the log."


def test_j5_mutant_reading_an_expired_view_is_red():
    ns, api = bot(n_records(25))
    _mutant(ns, "_modlog_parse_custom_id", 'if held is None or held["exp"] <= time.monotonic():',
            "if held is None:")
    with pytest.raises(AssertionError) as e:
        j5_a_view_not_held_is_one_sentence(ns, api)
    print("\nMUTANT-RED J5 expired view read: %s" % str(e.value).splitlines()[0][:120])


def j5_the_bound(ns, api):
    held = ns["_modlog_held"]
    ns["MODLOG_HOLD_MAX"] = 3
    views = [_first(ns)[1] for _ in range(3)]
    toks = [v.children[0].kw["custom_id"].split(":")[1] for v in views]
    assert list(held) == toks
    _first(ns)                                          # a fourth view: the oldest is dropped
    assert len(held) == 3 and toks[0] not in held and toks[1] in held, list(held)
    _press(ns, views[1], "Next")                        # the second is used: it is now the newest
    _first(ns)
    assert len(held) == 3 and toks[1] in held and toks[2] not in held, list(held)
    keep, old = list(held)[0], list(held)[-1]
    held[old]["exp"] = 0                                # the newest, unused past its age
    _first(ns)
    assert old not in held and keep in held and len(held) == 3, list(held)


def test_j5_the_store_of_views_is_bounded_by_a_count_and_an_age():
    ns, api = bot(n_records(25))
    assert (ns["MODLOG_HOLD_MAX"], ns["MODLOG_HOLD_S"]) == (2000, 900)
    j5_the_bound(ns, api)


def j7_carried_row_is_marked(ns, api):
    it = _Inter()
    run(ns["_modlog_command"](it, PLAYER, "", "", "n"))
    (text, kw), = it.sent
    lines = text.split("\n")[3:]
    assert len(lines) == 10, lines
    tag = " (carried in from the flag's review data, not written at the review)"
    marked = [i for i, line in enumerate(lines) if tag in line]
    assert marked == [3], (marked, lines[3])
    assert "**Ban**" + tag + " by " in lines[3], lines[3]
    assert "carried in" not in lines[2] and "carried in" not in lines[4]


def carried_records(params):
    """markdown_records with the fourth row carried in by migration 420."""
    status, body = markdown_records(params)
    for r in body["rows"]:
        if r["id"] == "m3":
            r["details"] = {"flag_id": "f3", "carried_from": "flagged_matches"}
    return status, body


def test_j7_a_carried_in_row_is_marked_after_its_kind_inside_the_budget():
    ns, api = bot(carried_records)
    j7_carried_row_is_marked(ns, api)
    assert ns["_modlog_carried"]({"details": {"carried_from": "another_table"}}) == \
        ns["MODLOG_CARRIED_OTHER"]


def test_j7_mutant_without_the_carried_in_mark_is_red():
    ns, api = bot(carried_records)
    _mutant(ns, "_modlog_render", "_modlog_carried(r),", '"",')
    with pytest.raises(AssertionError) as e:
        j7_carried_row_is_marked(ns, api)
    print("\nMUTANT-RED J7 bot without the carried-in mark: %s" % str(e.value).splitlines()[0][:120])


@pytest.mark.parametrize("fname,old,new", [
    ("_modlog_hold", "    while len(_modlog_held) >= MODLOG_HOLD_MAX:\n"
                     "        _modlog_held.pop(next(iter(_modlog_held)))\n", ""),
    ("_modlog_hold", "        _modlog_held.pop(tok, None)", "        pass"),
    ("_modlog_shown", "held = _modlog_held.pop(tok)", "held = _modlog_held[tok]"),
], ids=["count_bound_removed", "age_bound_removed", "use_not_counted"])
def test_j5_mutant_of_the_bound_is_red(fname, old, new):
    ns, api = bot(n_records(25))
    _mutant(ns, fname, old, new)
    with pytest.raises(AssertionError) as e:
        j5_the_bound(ns, api)
    print("\nMUTANT-RED J5 %s: %s" % (fname, str(e.value).splitlines()[0][:120]))


# K2: two presses of one view whose reads overlap. The newest press wins: each
# press takes the view's next press number before its read, and a read that
# ends after a newer press of the same view began is not shown and changes
# nothing in the view's state. The fetch is a test double whose reads end in
# the order the test chooses.

def _gated_fetch(ns, answer):
    """Replace the view's fetch: each read waits for its own gate; the list
    holds (the read's after key, its gate) in the order the reads began."""
    reads = []

    async def fetch(params, actor_id):
        gate = asyncio.Event()
        reads.append((dict(params).get("after", ""), gate))
        await gate.wait()
        return answer(dict(params))
    real = ns["_modlog_fetch"]
    ns["_modlog_fetch"] = fetch
    return reads, real


def k2_two_presses_overlap(ns, api, last):
    """On the third page, Next is pressed and then Previous before Next's read
    ends; `last` names the press whose read ends last ("first" or "second")."""
    _, view = _walk(ns, ["Next", "Next"])
    tok = view.children[0].kw["custom_id"].split(":")[1]
    held = ns["_modlog_held"][tok]
    assert (held["page"], len(held["afters"])) == (2, 3), held
    cid = {c.kw["label"]: c.kw["custom_id"] for c in view.children}
    reads, real = _gated_fetch(ns, n_records(45))
    first, second = _Inter(), _Inter()

    async def go():
        t1 = asyncio.ensure_future(ns["_modlog_click"](first, cid["Next"]))
        while len(reads) < 1:
            await asyncio.sleep(0)
        t2 = asyncio.ensure_future(ns["_modlog_click"](second, cid["Previous"]))
        while len(reads) < 2:
            await asyncio.sleep(0)
        order = [(reads[1][1], t2), (reads[0][1], t1)] if last == "first" else \
            [(reads[0][1], t1), (reads[1][1], t2)]
        for gate, task in order:
            gate.set()
            await task
            held_now = ns["_modlog_held"][tok]
            assert len(held_now["afters"]) == held_now["page"] + 1, held_now
    run(go())
    ns["_modlog_fetch"] = real
    assert [r[0] for r in reads] == ["k29", "k9"], reads
    # the newer press (Previous, to the second page) is shown; the older is not
    assert first.edits == [] and first.sent == [] and len(first.deferred) == 1, (first.edits, first.sent)
    assert len(second.edits) == 1 and second.sent == [], (second.edits, second.sent)
    assert "page 2 of 5" in second.edits[0]["content"], second.edits[0]["content"][:200]
    held = ns["_modlog_held"][tok]
    assert (held["page"], held["afters"], held["next"]) == (1, ["", "k9"], "k19"), held
    # the view goes on from the newer press's page: back to the first page,
    # then forward to the third
    text1, view1, _ = _press(ns, second.edits[0]["view"], "Previous")
    assert "page 1 of 5" in text1, text1[:200]
    text3, _, _ = _press(ns, _press(ns, view1, "Next")[1], "Next")
    assert "page 3 of 5" in text3, text3[:200]
    assert [dict(c[1]).get("after") for c in api.calls[-3:]] == [None, "k9", "k19"], api.calls[-3:]


@pytest.mark.parametrize("last", ["first", "second"])
def test_k2_the_newest_press_of_a_view_wins_when_two_reads_overlap(last):
    ns, api = bot(n_records(45))
    k2_two_presses_overlap(ns, api, last)


def test_k2_mutant_without_the_press_number_check_is_red():
    ns, api = bot(n_records(45))
    _mutant(ns, "_modlog_click", 'if cur is not None and cur["press"] != press:', "if False:")
    with pytest.raises(AssertionError) as e:
        k2_two_presses_overlap(ns, api, "first")
    print("\nMUTANT-RED K2 press number check removed: %s" % str(e.value).splitlines()[0][:120])


# F2b: the api serves each record's details as stored, so one page can hold a
# details of every JSON kind. The renderer reads details only for the
# carried-in mark, and from an object alone: a page of every kind renders, each
# row on its line, and a string holding the mark's key as text is not marked.

F2B_DETAILS = [{"note": "n"}, {}, None, [], ["x", 2], 0, 7.5, True, False, "", "a plain note",
               json.dumps({"carried_from": "flagged_matches"})]


def f2b_page_of_every_kind(ns):
    _, body = n_records(len(F2B_DETAILS))({"sort": "n", "dir": "desc", "limit": str(len(F2B_DETAILS))})
    for r, d in zip(body["rows"], F2B_DETAILS):
        r["details"] = d
    try:
        out = ns["_modlog_render"](body, page=0, sort="n", action_idx=None, search="")
    except Exception as e:  # the caller would answer MODLOG_SCHEMA
        out = ("error", type(e).__name__, str(e)[:80])
    assert isinstance(out, str), out
    lines = out.split("\n")[3:]
    assert len(lines) == len(F2B_DETAILS), lines
    for i, line in enumerate(lines):
        assert "Mod %d" % i in line, (i, line)
    assert not any("carried in" in line for line in lines), lines


def test_f2b_a_page_holding_details_of_every_kind_renders():
    ns, api = bot(n_records(1))
    f2b_page_of_every_kind(ns)


def test_f2b_mutant_reading_a_key_of_any_details_is_red():
    ns, api = bot(n_records(1))
    _mutant(ns, "_modlog_carried", 'details.get("carried_from") if isinstance(details, dict) else None',
            'details.get("carried_from")')
    with pytest.raises(AssertionError) as e:
        f2b_page_of_every_kind(ns)
    print("\nMUTANT-RED F2b bot reading a key of any details: %s" % str(e.value).splitlines()[0][:120])


# -- LANDFIX-1: every string a person typed, or the server passes through, is literal --
#
# The text of /modlog prints the player's name, the search word, and for each
# record the moderator's name, the reason, the server's sentence and the
# kind's label, and the totals' labels. Each of them here holds one of the
# names of tests/test_discord_name_markdown.py's HOSTILE list (a masked link,
# bold, a heading, a code span, a mention, a list marker, a line break, a
# backslash), checked by that file's written-out expectation _expect, so the
# moderator log is held to the one list and the one expectation every other
# renderer of the bot is. Every form of the text: no record, one page,
# several pages walked with the buttons, with the filter text, each sort.
# The census of that file counts only values under its name keys (here the
# player's and the moderator's names); these tests are what show the reason,
# the sentence, the labels and the search word.

from test_discord_name_markdown import (HOSTILE, HOSTILE_IDS, _MASKED_LINK,  # noqa: E402
                                        _expect, _markup, _shows_literally)

ROW_FIELDS = ("actor", "reason", "sentence", "kind")
HEAD_FIELDS = ("player", "search", "total")
# The words the header shows in its code span for a Steam id that is not 1 to
# 20 ASCII digits.
UNKNOWN_ID = "unknown id"


def _tagged(s):
    """`s` once per field, each copy tagged with its field's name, so each
    field's own copy is looked for."""
    return {f: "%s %s" % (s, f) for f in ROW_FIELDS + HEAD_FIELDS}


def hostile_records(v, total, steam_id=PLAYER):
    """The api's answer for a player of `total` records, paged by key as the
    route pages them (the bot's limit, either direction). Row i carries its
    hostile copy in field ROW_FIELDS[i % 4] and plain words in the others, so
    every row stays inside its share of the message and every page of 4 or
    more rows shows each field."""
    plain = {"actor": "Mod", "reason": "r", "sentence": "s.", "kind": "Ban"}
    rows = []
    for i in range(total):
        f = dict(plain, **{ROW_FIELDS[i % 4]: v[ROW_FIELDS[i % 4]]})
        rows.append({"id": "h%d" % i, "key": "k%d" % i, "at": "2026-11-01T10:%02d:00Z" % (59 - i),
                     "action": "ban", "action_label": f["kind"], "actor": "76561190420000001",
                     "actor_name": f["actor"], "players": [{"steam_id": steam_id, "name": v["player"]}],
                     "reason": f["reason"], "sentence": f["sentence"], "target_steam_id": steam_id,
                     "target_match_id": None, "target_series_id": None, "details": {}})

    def answer(params):
        ordered = rows[::-1] if params.get("dir") == "asc" else rows
        start = [r["key"] for r in ordered].index(params["after"]) + 1 if params.get("after") else 0
        lim = int(params["limit"])
        page = ordered[start:start + lim]
        nxt = page[-1]["key"] if start + lim < len(ordered) else None
        return 200, {"total": total, "limit": lim, "next": nxt, "sort": params["sort"], "dir": params["dir"],
                     "counts_by_action": [{"action": "ban", "label": v["total"], "count": total}] if total else [],
                     "player": {"steam_id": steam_id, "name": v["player"]}, "rows": page}
    return answer


def _expect_reason(s):
    """The reason as the bot must print it (BOT-TEXT-ESCAPE-1 stage 2: free
    text, the bot's _escape_text, not the name rule): its line breaks KEPT,
    and each line written as _expect writes a name. That equals the free-text
    rule for every HOSTILE value -- none holds a bare address with a
    character the two rules treat differently."""
    # free text keeps an address whole: no scheme break, unlike a name (stage 3)
    return "\n".join(_expect(line).replace("​", "") for line in s.split("\n"))


def _field_literally(text, v, f):
    if f == "reason":
        exp = _expect_reason(v[f])
        assert exp in text, (v[f], exp, text)
        if exp != v[f]:
            assert v[f] not in text.replace(exp, ""), (v[f], text)
    else:
        _shows_literally(text, v[f])


def _only_the_bots_markup(text, n_rows, v=None):
    """Once every backslash-escaped character is dropped (what Discord
    formats), the text holds the bot's own markup and nothing else: the bold
    of the header and of each row's kind, the one code span of the Steam id,
    no masked link, no tag but the rows' timestamps, and one line per row
    below the header's two and the totals -- plus each line break a shown
    reason keeps."""
    shown = _markup(text)
    assert shown.count("**") == 2 + 2 * n_rows, shown
    assert shown.count("`") == 2, shown
    assert not _MASKED_LINK.search(shown), shown
    assert shown.count("<") == text.count("<t:") == n_rows, shown
    kept = 0
    if v is not None and "\n" in v["reason"]:
        kept = text.count(_expect_reason(v["reason"])) * v["reason"].count("\n")
    assert text.count("\n") == (2 + n_rows + kept if n_rows else 0), text


@pytest.mark.parametrize("s", HOSTILE, ids=HOSTILE_IDS)
def test_landfix_no_record_shows_the_name_and_the_search_literally(s):
    v = _tagged(s)
    ns, _ = bot(hostile_records(v, 0))
    it = _Inter()
    run(ns["_modlog_command"](it, "Some One", "ban", v["search"], "n"))
    (text, kw), = it.sent
    assert text.startswith("No moderator action is on record for **"), text
    assert "(kind: Ban; search: " in text and "`%s`" % PLAYER in text, text
    for f in ("player", "search"):
        _shows_literally(text, v[f])
    _only_the_bots_markup(text, 0)


@pytest.mark.parametrize("s", HOSTILE, ids=HOSTILE_IDS)
def test_landfix_one_page_shows_every_field_literally(s):
    v = _tagged(s)
    ns, _ = bot(hostile_records(v, 4))
    it = _Inter()
    run(ns["_modlog_command"](it, "Some One", "", v["search"], "n"))
    (text, kw), = it.sent
    assert "view" not in kw and "4 records, page 1 of 1, newest first." in text, text
    for f in ROW_FIELDS + HEAD_FIELDS:
        _field_literally(text, v, f)
    _only_the_bots_markup(text, 4, v)


@pytest.mark.parametrize("sort", sorted(("n", "o", "a", "m")))
@pytest.mark.parametrize("s", HOSTILE, ids=HOSTILE_IDS)
def test_landfix_every_page_of_every_sort_shows_every_field_literally(s, sort):
    """Twenty-four records: pages of 10, 10 and 4 rows, walked Next, Next,
    then Previous, with the kind filter and the search word in the header."""
    v = _tagged(s)
    ns, api = bot(hostile_records(v, 24))
    it = _Inter()
    run(ns["_modlog_command"](it, "Some One", "ban", v["search"], sort))
    (text, kw), = it.sent
    shown, view = [(text, 10)], kw["view"]
    for label, n_rows in (("Next", 10), ("Next", 4), ("Previous", 10)):
        text, view, sent = _press(ns, view, label)
        assert text is not None, sent
        shown.append((text, n_rows))
    assert "page 3 of 3, %s." % ns["MODLOG_SORTS"][sort][2] in shown[2][0], shown[2][0]
    for text, n_rows in shown:
        assert "(kind: Ban; search: " in text, text
        for f in ROW_FIELDS + HEAD_FIELDS:
            _field_literally(text, v, f)
        _only_the_bots_markup(text, n_rows, v)
    assert len(api.calls) == 4


@pytest.mark.parametrize("sid,shown", [
    (PLAYER, PLAYER), ("1", "1"), ("9" * 20, "9" * 20),
    ("`x`", UNKNOWN_ID), ("76561190420000777` **x** `", UNKNOWN_ID), ("<@123>", UNKNOWN_ID),
    ("١٢٣", UNKNOWN_ID), ("１２３", UNKNOWN_ID), ("9" * 21, UNKNOWN_ID),
    ("", UNKNOWN_ID), ("76561190420000777\n# h", UNKNOWN_ID), (" 76561190420000777", UNKNOWN_ID)],
    ids=["steam-id", "one-digit", "twenty-digits", "code", "code-then-bold", "mention", "arabic-digits",
         "fullwidth-digits", "twenty-one-digits", "empty", "break-then-heading", "leading-space"])
def test_landfix_the_steam_id_in_the_code_span_is_ascii_digits_or_a_fixed_word(sid, shown):
    """The header prints the player's Steam id inside a code span. A code span
    ends at a backtick in its text and shows a backslash as typed, so no
    escape makes a value literal there: the id is printed only when it is 1
    to 20 ASCII digits, and UNKNOWN_ID otherwise. The internal read answers
    with the 17 digits the bot asked with, or, asked by name, the players
    row's steam_id as stored."""
    v = _tagged("Plain")
    for total in (0, 4):
        ns, _ = bot(hostile_records(v, total, steam_id=sid))
        it = _Inter()
        run(ns["_modlog_command"](it, "Plain player", "", "", "n"))
        (text, kw), = it.sent
        if sid and shown != sid:
            assert sid not in text, text
        assert text.count("`") == 2 and "(`%s`)" % shown in text, text


@pytest.mark.parametrize("status", [400, 422])
def test_landfix_a_refusal_detail_is_cut_before_it_is_escaped(status):
    """The api's refusal word is cut raw, then escaped: escaping first and
    then cutting at 200 can keep the backslash of a pair and drop the
    character it escaped, which leaves the backslash to escape the sentence's
    own closing parenthesis."""
    detail = "a" * 199 + "*" * 60
    ns, _ = bot(lambda params: (status, {"detail": detail}))
    it = _Inter()
    run(ns["_modlog_command"](it, PLAYER, "", "", "n"))
    (text, kw), = it.sent
    assert "(%s). Trying again as it is will not help." % _expect("a" * 199 + "…") in text, text


@pytest.mark.parametrize("s", HOSTILE, ids=HOSTILE_IDS)
def test_landfix_a_refusal_detail_is_literal(s):
    ns, _ = bot(lambda params: (400, {"detail": s}))
    it = _Inter()
    run(ns["_modlog_command"](it, PLAYER, "", "", "n"))
    (text, kw), = it.sent
    _shows_literally(text, s)
    assert "\n" not in text and not _MASKED_LINK.search(_markup(text)), text


def test_landfix_the_whole_page_cut_never_ends_inside_an_escape_pair():
    """The page is cut whole to MODLOG_MSG_MAX as the last step, after every
    value is escaped. Run at every limit from 10 to 400 characters with names,
    a search word and rows made of backslashes, the page never passes the
    limit, and where it is cut the run of backslashes before the mark is even:
    no escape pair is cut in half."""
    v = {f: "\\" * 30 for f in ROW_FIELDS + HEAD_FIELDS}
    ns, _ = bot(lambda params: (200, {}))
    _, body = hostile_records(v, 4)({"sort": "time", "dir": "desc", "limit": "10"})
    cut = 0
    for lim in range(10, 401):
        ns["MODLOG_MSG_MAX"] = lim
        text = ns["_modlog_render"](body, page=0, sort="n", action_idx=None, search="\\" * 64)
        assert len(text) <= lim, (lim, len(text))
        if text.endswith("…"):
            cut += 1
            head = text[:-1]
            assert (len(head) - len(head.rstrip("\\"))) % 2 == 0, (lim, text[-12:])
    assert cut > 300, cut


def test_landfix_the_record_time_is_a_timestamp_tag_or_a_fixed_phrase():
    """Each row opens with the record's time: a Discord timestamp tag of a
    whole number, or the fixed phrase "(time unknown)" for a value that is
    no time. No part of the value itself is ever printed there -- not a
    name, not a mention after a valid time, not other scripts' digits."""
    ns, _ = bot(lambda params: (200, {}))
    cases = [None, "", 12345, True, ["2026-11-01"], "2026-11-01T10:59:00Z<@1>",
             "２０２６-11-01", "0001-01-01T00:00:00Z"] + HOSTILE
    for v in cases:
        out = ns["_modlog_ts"](v)
        assert re.fullmatch(r"<t:-?[0-9]+:f>", out) or out == "(time unknown)", (v, out)
        s = str(v)
        parts = [s] + [p for p in re.split(r"[\s\[\]()<>@`*#_:.\\-]+", s) if len(p) >= 3]
        assert not [p for p in parts if p and p in out], (v, out)
    assert ns["_modlog_ts"]("0001-01-01T00:00:00Z") == "<t:-62135596800:f>"
    assert ns["_modlog_ts"]("2026-11-01T10:59:00Z") == "<t:%d:f>" % int(
        datetime(2026, 11, 1, 10, 59, tzinfo=timezone.utc).timestamp())


def dense_rows(n=10):
    """Rows whose fixed parts are long: a 40-character kind with characters
    the escape doubles, the 68-character carried mark on every third row and
    the other carried mark on the next, a long moderator, reason and
    sentence."""
    kinds = ["Ban", "Other (" + "chat_x_" * 4 + ")", "Mute*Star|x", "Other (" + "a_" * 16 + ")"]
    rows = []
    for i in range(n):
        details = ({"carried_from": "flagged_matches"} if i % 3 == 0 else
                   {"carried_from": "other_table"} if i % 3 == 1 else {})
        rows.append({"id": "d%d" % i, "key": "k%d" % i, "at": "2026-11-01T10:%02d:00Z" % (59 - i),
                     "action": "ban", "action_label": kinds[i % 4], "actor": "76561190420000001",
                     "actor_name": "Moderator_" + "m" * 30, "players": [], "reason": "r_" * 128,
                     "sentence": "s*" * 300, "target_steam_id": PLAYER, "target_match_id": None,
                     "target_series_id": None, "details": details})
    return {"total": n, "limit": 10, "next": None, "sort": "time", "dir": "desc",
            "counts_by_action": [{"action": "ban", "label": "Ban", "count": n}],
            "player": {"steam_id": PLAYER, "name": "P"}, "rows": rows}


def _bold_pairs_hold(ns, body):
    """Render `body` at every message limit from 200 to 2000; for every limit
    whose rows get a budget of at least one character, each row's length
    holds the budget and each row, once escaped characters are dropped,
    holds an even count of `**`. Returns how many rows were cut before the
    kind's opening mark, and how many were cut after its closing mark."""
    before = after = 0
    for lim in range(200, 2001):
        ns["MODLOG_MSG_MAX"] = lim
        lines = ns["_modlog_render"](body, page=0, sort="n", action_idx=None, search="").split("\n")
        rows = lines[3:]
        budget = ns["_modlog_row_budget"](lim, "\n".join(lines[:2]), lines[2], len(rows))
        if budget < 1:
            continue
        for row in rows:
            assert len(row) <= budget, (lim, budget, row)
            assert _markup(row).count("**") % 2 == 0, (lim, budget, row)
            if row.endswith("…"):
                if "**" in row:
                    after += 1
                else:
                    before += 1
    return before, after


def test_landfix_a_row_cut_never_ends_inside_the_kinds_bold_pair():
    """A row whose time, kind and carried mark outgrow its budget is cut
    before the kind's opening mark, never between the two marks, so no
    bold is left open to run into the next row. Both cases occur: rows cut
    before the pair, and rows cut after it."""
    ns, _ = bot(lambda params: (200, {}))
    before, after = _bold_pairs_hold(ns, dense_rows())
    assert before > 0 and after > 0, (before, after)
