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
                name.startswith("_modlog_") or name in ("_aer_local_gate", "_escape_md")):
            node = copy.deepcopy(node)
            node.decorator_list = []
            picked.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id.startswith(("MODLOG_", "_MD_", "_modlog_"))
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
