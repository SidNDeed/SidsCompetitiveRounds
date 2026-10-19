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
    basis = "player" if shape == "player" else "pair"
    partner = None if shape == "player" else 1
    body["windows"] = [{"oi": 0, "basis": basis, "subj": ["seat", 0, partner], "games": 10,
                        "covered": 10, "flag_obs": 0, "newest": "a" * 12,
                        "oldest": "b" * 12}]
    body["summary"] = [{"oi": 0, "cells": [[w.ki, 10, 4.5, None, None, None, "none",
                                            None, None, None, None, None, "ok"]]}]
    return body


def _two_catalog_summary_body():
    body = summary_body()
    first = body["catalog"][0]["ki"]
    second = next(e for e in ae.REPORT_REGISTRY
                  if e.is_window and e.scope == "seat" and e.ki != first)
    body["catalog"].append(ae._catalog_row(second))
    for row in body["summary"]:
        cell = list(row["cells"][0])
        cell[0] = second.ki
        row["cells"].append(cell)
    return body


def _two_window_summary_body():
    body = summary_body()
    window = copy.deepcopy(body["windows"][0])
    window.update(oi=1, subj=["seat", 1, 0])
    body["windows"].append(window)
    row = copy.deepcopy(body["summary"][0])
    row["oi"] = 1
    body["summary"].append(row)
    return body


def _request_for_body(body):
    shape, page = body["shape"], body["page"]
    if shape in ("game", "series"):
        return {"shape": shape, "code": "0" * 12, "page": page}
    if shape == "pair":
        return {"shape": shape, "a": "1001", "b": "1002",
                "games": 10, "page": page}
    return {"shape": shape, "steam_id": "1001", "games": 10, "page": page}


def _body_with_cell_kind(kind):
    entry = next(e for e in ae.REPORT_REGISTRY
                 if not e.is_window and e.scope == "seat" and e.kind == kind)
    body = game_body()
    body["catalog"] = [ae._catalog_row(entry)]
    value = 7 if kind == "R" else ae._aer_enc(kind.lower() + " value")
    cell = [entry.ki, value, None, None, "none", None, None, None, "ok"]
    for seat in body["games"][0]["seats"]:
        seat["cells"] = [list(cell)]
    return body


def _set_first_cell_value(body, value):
    body["games"][0]["seats"][0]["cells"][0][
        ae.AER_WIRE["1a"]["seat"].index("val")] = value


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
        ("R cell carrying text", lambda: _body_with_cell_kind("R"),
         lambda b: _set_first_cell_value(b, "c1")),
        ("T cell carrying number", lambda: _body_with_cell_kind("T"),
         lambda b: _set_first_cell_value(b, 7)),
        ("D cell carrying number", lambda: _body_with_cell_kind("D"),
         lambda b: _set_first_cell_value(b, 7)),
        ("T window carrying numeric summary", summary_body,
         lambda b: b["catalog"][0].update(kind="T")),
        ("D window carrying numeric summary", summary_body,
         lambda b: b["catalog"][0].update(kind="D")),
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
    kind_pages = [dec(_body_with_cell_kind(k), "1a") for k in ("R", "T", "D")]
    assert [next(iter(p.catalog.values()))["kind"] for p in kind_pages] == ["R", "T", "D"]
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


@pytest.mark.parametrize("shape", [[], {}], ids=("list", "dict"))
def test_m19_decoder_type_checks_shape_before_membership(bot, shape):
    body = game_body()
    body["shape"] = shape
    with pytest.raises(bot["AerSchemaError"]):
        bot["_aer_decode_response"](body, "1a")


def test_m19_decoder_summary_fields_follow_the_validated_shape_and_page(bot):
    dec, err = bot["_aer_decode_response"], bot["AerSchemaError"]
    valid = [game_body(), game_body(2, 3, "series"),
             summary_body(shape="pair"), summary_body(shape="player"),
             game_body(2, 3, "pair"), game_body(3, 3, "player")]
    assert [(p.shape, p.page) for p in map(dec, valid)] == [
        ("game", 1), ("series", 2), ("pair", 1),
        ("player", 1), ("pair", 2), ("player", 3)]
    refused = [game_body(shape="pair"), game_body(shape="player"),
               summary_body(2, 3, "pair"), summary_body(2, 3, "player"),
               summary_body(shape="game"), summary_body(shape="series")]
    for body in refused:
        with pytest.raises(err):
            dec(body, "1a")


@pytest.mark.parametrize(
    "body,expected",
    [(game_body(), {"shape": "series", "page": 1}),
     (game_body(2, 3), {"shape": "game", "page": 1})],
    ids=("shape", "page"))
def test_m19_decoder_matches_the_parsed_request(bot, body, expected):
    with pytest.raises(bot["AerSchemaError"]):
        bot["_aer_decode_response"](body, "1a", expected=expected)


def test_m19_command_rejects_a_cross_shape_response():
    events = []
    api = _Api(lambda _path, _actor: (200, game_body(shape="series"), {}), events)
    ns = bot_ns(api, events)
    interaction = _Interaction(events, ADMIN)
    run(_command(ns, interaction, "game"))
    assert interaction.ephemeral == ["Evidence report: unavailable (schema)."]
    assert _public(events) == []


def test_m19_button_rejects_a_wrong_page_response():
    events = []
    api = _Api(lambda _path, _actor: (200, game_body(1, 2), {}), events)
    ns = bot_ns(api, events)
    message = _Message(events)
    cid = "aer:g:%s:2" % ("0" * 12)
    interaction = _Interaction(events, ADMIN, custom_id=cid, message=message)
    run(_click(ns, interaction))
    assert interaction.ephemeral == ["Evidence report: unavailable (schema)."]
    assert message.edits == []


def test_m19_both_delivery_callers_pass_exactly_the_parsed_request():
    found = []
    for name in ("_aer_command", "_aer_click"):
        fn = next(node for node in TREE.body
                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.name == name)
        calls = [node for node in ast.walk(fn)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)
                 and node.func.id == "_aer_outcome"]
        assert len(calls) == 1
        expected = [kw for kw in calls[0].keywords if kw.arg == "expected"]
        assert len(expected) == 1
        assert isinstance(expected[0].value, ast.Name)
        assert expected[0].value.id == "req"
        found.append(name)
    assert found == ["_aer_command", "_aer_click"]


def test_m20_catalog_ki_and_canonical_key_are_injective(bot):
    duplicate_ki = game_body()
    repeated = copy.deepcopy(duplicate_ki["catalog"][0])
    repeated["key"] += ".duplicate"
    duplicate_ki["catalog"].append(repeated)

    duplicate_key = game_body()
    repeated = copy.deepcopy(duplicate_key["catalog"][0])
    repeated["ki"] = max(row["ki"] for row in duplicate_key["catalog"]) + 1000
    duplicate_key["catalog"].append(repeated)
    for seat in duplicate_key["games"][0]["seats"]:
        cell = list(seat["cells"][0])
        cell[0] = repeated["ki"]
        seat["cells"].append(cell)

    for body in (duplicate_ki, duplicate_key):
        with pytest.raises(bot["AerSchemaError"]):
            bot["_aer_decode_response"](body, "1a")


def test_m20_game_catalog_rows_are_base_rows_with_every_spread(bot):
    missing_spread = game_body()
    missing_spread["catalog"][0].pop("p90")

    producer_window_as_game = game_body()
    window = next(e for e in ae.REPORT_REGISTRY if e.is_window and e.scope == "seat")
    producer_window_as_game["catalog"] = [ae._catalog_row(window)]
    for seat in producer_window_as_game["games"][0]["seats"]:
        seat["cells"] = [list(seat["cells"][0])]
        seat["cells"][0][0] = window.ki

    spread_shaped_window_as_game = copy.deepcopy(producer_window_as_game)
    window_row = ae._catalog_row(window)
    window_row.update(p50=None, p90=None, p99=None)
    spread_shaped_window_as_game["catalog"] = [window_row]

    cases = ((missing_spread, "keys ['p90']"),
             (producer_window_as_game, "keys ['p50', 'p90', 'p99']"),
             (spread_shaped_window_as_game, "game catalog row"))
    for body, refusal in cases:
        with pytest.raises(bot["AerSchemaError"], match="^" + re.escape(refusal) + "$"):
            bot["_aer_decode_response"](body, "1a")


def test_m20_summary_catalog_rows_are_r_windows(bot):
    base_as_summary = summary_body()
    base = next(e for e in ae.REPORT_REGISTRY if not e.is_window and e.kind == "R")
    base_as_summary["catalog"] = [ae._catalog_row(base)]
    for key in ("p50", "p90", "p99"):
        base_as_summary["catalog"][0].pop(key)
    base_as_summary["summary"][0]["cells"] = []

    non_r_window = summary_body()
    non_r_window["catalog"][0]["kind"] = "T"
    non_r_window["summary"][0]["cells"] = []

    for body, refusal in ((base_as_summary, "summary catalog base"),
                          (non_r_window, "summary catalog kind")):
        with pytest.raises(bot["AerSchemaError"], match="^" + refusal + "$"):
            bot["_aer_decode_response"](body, "1a")


@pytest.mark.parametrize("slot,value", [("base", None), ("kind", "T")],
                         ids=("base", "kind"))
def test_m20_summary_catalog_role_precedes_cell_decoding(bot, monkeypatch, slot, value):
    body = summary_body()
    body["catalog"][0][slot] = value
    decoded_cells = []

    def permissive_cell(row, *_args, **_kwargs):
        decoded_cells.append(row)
        return tuple(row)

    monkeypatch.setitem(bot, "_aer_cell", permissive_cell)
    refusal = "summary catalog base" if slot == "base" else "summary catalog kind"
    with pytest.raises(bot["AerSchemaError"], match="^" + refusal + "$"):
        bot["_aer_decode_response"](body, "1a")
    assert decoded_cells == []


def test_m20_valid_catalog_order_and_content_round_trip(bot):
    for body in (game_body(), summary_body()):
        page = bot["_aer_decode_response"](copy.deepcopy(body), "1a")
        expected_kis = [row["ki"] for row in body["catalog"]]
        assert list(page.catalog) == expected_kis
        assert [page.catalog[ki] for ki in expected_kis] == body["catalog"]


def _m21_game_breaks():
    out = []
    no_seats = game_body()
    no_seats["games"][0]["seats"] = []
    out.append(("no seats", no_seats))
    one_seat = game_body()
    one_seat["games"][0]["seats"].pop()
    out.append(("one seat", one_seat))
    three_seats = game_body()
    three_seats["games"][0]["seats"].append(
        copy.deepcopy(three_seats["games"][0]["seats"][0]))
    out.append(("three seats", three_seats))
    out_of_range = game_body()
    out_of_range["games"][0]["seats"][0]["subject"] = len(out_of_range["subjects"])
    out.append(("out-of-range seat subject", out_of_range))
    two_reporters = game_body()
    for seat in two_reporters["games"][0]["seats"]:
        seat["reporter"] = True
    out.append(("two reporters", two_reporters))
    missing_cell = game_body()
    missing_cell["games"][0]["seats"][0]["cells"].pop()
    out.append(("missing game cell key", missing_cell))
    duplicate_cell = game_body()
    cells = duplicate_cell["games"][0]["seats"][0]["cells"]
    cells[1][0] = cells[0][0]
    out.append(("duplicate game cell key", duplicate_cell))
    empty_cells = game_body()
    empty_cells["games"][0]["seats"][0]["cells"] = []
    out.append(("empty game cells", empty_cells))
    empty_catalog = game_body()
    empty_catalog["catalog"] = []
    for seat in empty_catalog["games"][0]["seats"]:
        seat["cells"] = []
    out.append(("empty game catalog and cells", empty_catalog))
    return out


def _m21_window_breaks():
    out = []
    wrong_oi = summary_body()
    wrong_oi["windows"][0]["oi"] = 1
    out.append(("nonpositional window oi", wrong_oi))
    wrong_scope = summary_body()
    wrong_scope["windows"][0].update(subj=["pair", 0, 1], flag_obs=None)
    out.append(("window scope", wrong_scope))
    wrong_basis = summary_body()
    wrong_basis["windows"][0]["basis"] = "player"
    out.append(("window basis", wrong_basis))
    repeated = summary_body()
    repeated["windows"][0]["subj"] = ["seat", 0, 0]
    out.append(("repeated pair subjects", repeated))
    first_out = summary_body()
    first_out["windows"][0]["subj"] = ["seat", 2, 1]
    out.append(("first pair subject out of range", first_out))
    partner_out = summary_body()
    partner_out["windows"][0]["subj"] = ["seat", 0, 2]
    out.append(("partner out of range", partner_out))
    missing_partner = summary_body()
    missing_partner["windows"][0]["subj"] = ["seat", 0, None]
    out.append(("pair partner missing", missing_partner))
    player_partner = summary_body(shape="player")
    player_partner["windows"][0]["subj"] = ["seat", 0, 1]
    out.append(("player partner present", player_partner))
    return out


def _m21_summary_breaks():
    out = []
    empty = summary_body()
    empty["summary"][0]["cells"] = []
    out.append(("empty summary cells", empty))
    empty_catalog = summary_body()
    empty_catalog["catalog"] = []
    empty_catalog["summary"][0]["cells"] = []
    out.append(("empty summary catalog and cells", empty_catalog))
    missing_cell = _two_catalog_summary_body()
    missing_cell["summary"][0]["cells"].pop()
    out.append(("missing summary cell key", missing_cell))
    duplicate_cell = _two_catalog_summary_body()
    cells = duplicate_cell["summary"][0]["cells"]
    cells[1][0] = cells[0][0]
    out.append(("duplicate summary cell key", duplicate_cell))
    extra_cell = summary_body()
    extra_cell["summary"][0]["cells"].append(
        list(extra_cell["summary"][0]["cells"][0]))
    out.append(("extra duplicate summary cell", extra_cell))
    missing_row = _two_window_summary_body()
    missing_row["summary"].pop()
    out.append(("missing summary row", missing_row))
    duplicate_row = _two_window_summary_body()
    duplicate_row["summary"][1]["oi"] = 0
    out.append(("duplicate summary row", duplicate_row))
    return out


def test_m21_game_topology_reporter_and_cell_breaks_are_refused(bot):
    for label, body in _m21_game_breaks():
        with pytest.raises(bot["AerSchemaError"]):
            bot["_aer_decode_response"](body, "1a")


def test_m21_window_identity_breaks_are_refused(bot):
    for label, body in _m21_window_breaks():
        with pytest.raises(bot["AerSchemaError"]):
            bot["_aer_decode_response"](body, "1a")


def test_m21_summary_row_and_cell_breaks_are_refused(bot):
    for label, body in _m21_summary_breaks():
        with pytest.raises(bot["AerSchemaError"]):
            bot["_aer_decode_response"](body, "1a")


def test_m21_producer_reachable_zero_reporter_and_same_subject_remain_valid(bot):
    zero_reporter = game_body()
    for seat in zero_reporter["games"][0]["seats"]:
        seat["reporter"] = False
    same_subject = game_body()
    same_subject["games"][0]["seats"][1]["subject"] = 0
    for body in (zero_reporter, same_subject, _two_window_summary_body(),
                 summary_body(shape="player")):
        bot["_aer_plan"](bot["_aer_decode_response"](body, "1a"))


def test_flag_identity_order_reaches_the_page_plan_and_fallback(bot, monkeypatch):
    match_id = "0" * 32
    later = ae._dt.datetime(2026, 10, 17, tzinfo=ae._dt.timezone.utc)
    earlier = ae._dt.datetime(2026, 10, 16, tzinfo=ae._dt.timezone.utc)
    rows = [
        {"id": "0" * 31 + "1", "match_id": match_id, "flag_reason": "id_first",
         "flag_details": {}, "reviewed_at": None, "created_at": later},
        {"id": "0" * 31 + "2", "match_id": match_id, "flag_reason": "id_second",
         "flag_details": {}, "reviewed_at": None, "created_at": earlier},
    ]

    async def flag_rows(_db, _ids):
        return {match_id: rows}

    async def baseline(*_args, **_kwargs):
        return {}

    body = game_body()
    fixture_cells = [dict(zip(ae.AER_WIRE["1a"]["seat"], cell))
                     for cell in body["games"][0]["seats"][0]["cells"]]
    monkeypatch.setattr(ae, "_flag_rows", flag_rows)
    monkeypatch.setattr(ae, "read_baseline", baseline)
    monkeypatch.setattr(
        ae, "game_seat_cells",
        lambda *_args, **_kwargs: copy.deepcopy(fixture_cells))
    game = {"id": match_id, "player1_id": "p1", "player2_id": "p2",
            "ended_at": later, "is_ranked": True, "invalidated_at": None,
            "series_id": None, "p1_rounds_won": 5, "p2_rounds_won": 3}
    subjects = {"p1": {"steam_id": "1001", "i": 0},
                "p2": {"steam_id": "1002", "i": 1}}
    api_games = run(ae._game_page(
        types.SimpleNamespace(db=object()), [game], [], subjects,
        types.SimpleNamespace(values={})))
    expected = ["id_first", "id_second"]
    assert ae.FLAGS_SQL.strip().endswith("ORDER BY f.id")
    assert ae.FLAGS_SQL.upper().count("ORDER BY") == 1
    assert [f["reason"] for f in api_games[0]["flags"]] == expected

    body["games"] = api_games
    page = bot["_aer_decode_response"](body, "1a")
    assert [f["reason"] for f in page.games[0]["flags"]] == expected
    plan = bot["_aer_plan"](page)
    flag_lines = [item.text for item in plan if item.kind == "flag"]
    assert [line.split()[1] for line in flag_lines] == expected
    content, files = bot["_aer_fallback"]("header", plan, "order", 1)
    fallback = files[0].data.decode("utf-8") if files else content
    assert fallback.index("FLAG id_first") < fallback.index("FLAG id_second")


@pytest.mark.parametrize("label,maker,mutate", _phase_leaf_breaks(),
                         ids=lambda value: value if isinstance(value, str) else None)
def test_the_1a_decoder_refuses_a_phase_leaf_of_the_wrong_type(
        bot, label, maker, mutate):
    body = maker()
    mutate(body)
    with pytest.raises(bot["AerSchemaError"]):
        bot["_aer_decode_response"](body, "1a")
    if label in ("T window carrying numeric summary", "D window carrying numeric summary"):
        catalog = {body["catalog"][0]["ki"]: body["catalog"][0]}
        with pytest.raises(bot["AerSchemaError"]):
            bot["_aer_cell"](body["summary"][0]["cells"][0], "summary", catalog, "1a")


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


def _deliver_body(body, req, via):
    events = []
    api = _Api(lambda _path, _actor: (200, copy.deepcopy(body), {}), events)
    ns = bot_ns(api, events)
    message = _Message(events)
    if via == "command":
        assert req["page"] == 1
        interaction = _Interaction(events, ADMIN, message=message)
        run(_command(ns, interaction, req["shape"]))
    else:
        cid = ns["_aer_custom_id"](req, req["page"])
        interaction = _Interaction(
            events, ADMIN, custom_id=cid, message=message)
        run(_click(ns, interaction))
    return interaction, message, events


def _assert_schema_delivery(body, req, via):
    interaction, message, events = _deliver_body(body, req, via)
    assert interaction.ephemeral == ["Evidence report: unavailable (schema)."]
    assert _public(events) == []
    assert message.edits == []


def test_m19_every_binding_and_summary_relation_is_refused_by_command_and_button():
    pair_to_game = summary_body(shape="pair")
    wrong_page = game_body(2, 3, "game")
    missing_pair_summary = game_body(shape="pair")
    missing_player_summary = game_body(shape="player")
    extra_game_summary = summary_body(shape="game")
    extra_series_summary = summary_body(shape="series")
    list_shape = game_body()
    list_shape["shape"] = []
    dict_shape = game_body()
    dict_shape["shape"] = {}
    cases = [
        (pair_to_game, _request_for_body(game_body())),
        (wrong_page, _request_for_body(game_body())),
        (missing_pair_summary, _request_for_body(missing_pair_summary)),
        (missing_player_summary, _request_for_body(missing_player_summary)),
        (extra_game_summary, _request_for_body(game_body())),
        (extra_series_summary, _request_for_body(game_body(shape="series"))),
        (list_shape, _request_for_body(game_body())),
        (dict_shape, _request_for_body(game_body())),
    ]
    for body, req in cases:
        for via in ("command", "button"):
            _assert_schema_delivery(body, req, via)


def test_m19_matching_shapes_pages_and_summary_roles_reach_both_delivery_paths():
    bodies = [game_body(), game_body(shape="series"),
              summary_body(shape="pair"), summary_body(shape="player")]
    for body in bodies:
        req = _request_for_body(body)
        for via in ("command", "button"):
            interaction, message, events = _deliver_body(body, req, via)
            assert interaction.ephemeral == ["Posted."]
            assert len(_public(events)) == 1
            assert len(message.edits) == (1 if via == "button" else 0)


def _m20_delivery_breaks():
    duplicate_ki = game_body()
    row = copy.deepcopy(duplicate_ki["catalog"][0])
    row["key"] += ".duplicate"
    duplicate_ki["catalog"].append(row)

    duplicate_key = game_body()
    row = copy.deepcopy(duplicate_key["catalog"][0])
    row["ki"] = max(item["ki"] for item in duplicate_key["catalog"]) + 1000
    duplicate_key["catalog"].append(row)
    for seat in duplicate_key["games"][0]["seats"]:
        cell = list(seat["cells"][0])
        cell[0] = row["ki"]
        seat["cells"].append(cell)

    missing_spread = game_body()
    missing_spread["catalog"][0].pop("p90")

    window_as_game = game_body()
    window = next(e for e in ae.REPORT_REGISTRY if e.is_window and e.scope == "seat")
    window_as_game["catalog"] = [ae._catalog_row(window)]
    for seat in window_as_game["games"][0]["seats"]:
        seat["cells"] = [list(seat["cells"][0])]
        seat["cells"][0][0] = window.ki

    base_as_summary = summary_body()
    base = next(e for e in ae.REPORT_REGISTRY if not e.is_window and e.kind == "R")
    base_as_summary["catalog"] = [ae._catalog_row(base)]
    for key in ("p50", "p90", "p99"):
        base_as_summary["catalog"][0].pop(key)
    base_as_summary["summary"][0]["cells"] = []

    non_r_summary = summary_body()
    non_r_summary["catalog"][0]["kind"] = "T"
    non_r_summary["summary"][0]["cells"] = []
    return [duplicate_ki, duplicate_key, missing_spread, window_as_game,
            base_as_summary, non_r_summary]


def test_m20_every_catalog_relation_is_refused_by_command_and_button():
    for body in _m20_delivery_breaks():
        req = _request_for_body(body)
        for via in ("command", "button"):
            _assert_schema_delivery(body, req, via)


def _assert_m21_relations_are_refused_by_both_delivery_paths(breaks):
    for label, body in breaks:
        req = _request_for_body(body)
        for via in ("command", "button"):
            _assert_schema_delivery(body, req, via)


def test_m21_game_relations_are_refused_by_command_and_button():
    _assert_m21_relations_are_refused_by_both_delivery_paths(_m21_game_breaks())


def test_m21_window_relations_are_refused_by_command_and_button():
    _assert_m21_relations_are_refused_by_both_delivery_paths(_m21_window_breaks())


def test_m21_summary_relations_are_refused_by_command_and_button():
    _assert_m21_relations_are_refused_by_both_delivery_paths(_m21_summary_breaks())


def test_m21_producer_reachable_stop_cases_reach_both_delivery_paths():
    zero_reporter = game_body()
    for seat in zero_reporter["games"][0]["seats"]:
        seat["reporter"] = False
    same_subject = game_body()
    same_subject["games"][0]["seats"][1]["subject"] = 0
    for body in (zero_reporter, same_subject):
        req = _request_for_body(body)
        for via in ("command", "button"):
            interaction, message, events = _deliver_body(body, req, via)
            assert interaction.ephemeral == ["Posted."]
            assert len(_public(events)) == 1
            assert len(message.edits) == (1 if via == "button" else 0)


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


_FIX6_M20_CASES = [(role, relation) for role in ("base", "summary")
                  for relation in ("scope", "aggregation", "short", "long")]


def _fix6_m20_catalog_body(role, relation):
    body = game_body() if role == "base" else summary_body(shape="player")
    fields = body["catalog"][0]["key"].split("|")
    if relation == "scope":
        fields[2] = "pair"
        refusal = "catalog key scope"
    elif relation == "aggregation":
        fields[5] = "win_median.cell" if role == "base" else "cell"
        refusal = "catalog key aggregation"
    elif relation == "short":
        fields.pop()
        refusal = "catalog key fields"
    else:
        fields.append("extra")
        refusal = "catalog key fields"
    body["catalog"][0]["key"] = "|".join(fields)
    return body, refusal


@pytest.mark.parametrize("role,relation", _FIX6_M20_CASES)
def test_fix6_m20_catalog_key_components_refused_direct(bot, role, relation):
    body, refusal = _fix6_m20_catalog_body(role, relation)
    with pytest.raises(bot["AerSchemaError"], match="^" + refusal + "$"):
        bot["_aer_decode_response"](body, "1a")


@pytest.mark.parametrize("via", ("command", "button"))
@pytest.mark.parametrize("role,relation", _FIX6_M20_CASES)
def test_fix6_m20_catalog_key_components_refused_delivery(role, relation, via):
    body, _refusal = _fix6_m20_catalog_body(role, relation)
    _assert_schema_delivery(body, _request_for_body(body), via)


def test_fix6_m20_producer_catalog_components_and_order_remain_valid(bot):
    for body in (game_body(), summary_body(shape="player")):
        for row in body["catalog"]:
            assert len(row["key"].split("|")) == 7
            assert row["key"].split("|")[2] == "seat"
        page = bot["_aer_decode_response"](copy.deepcopy(body), "1a")
        assert list(page.catalog) == [row["ki"] for row in body["catalog"]]
        assert list(page.catalog.values()) == body["catalog"]
        for via in ("command", "button"):
            interaction, message, events = _deliver_body(body, _request_for_body(body), via)
            assert interaction.ephemeral == ["Posted."]
            assert len(_public(events)) == 1
            assert len(message.edits) == (1 if via == "button" else 0)
