"""QDIG-1, review qdig-r1: ONE reader of a held row's stored body.

_qdig_read_body reads the body once into a validated value or the verdict
MALFORMED with a fixed reason word; every reader of the lane takes that
value. The table below feeds it the shapes the review named and more, and
asserts each verdict. The classification and feed cases go through
qdig_fixtures.judge / detail, so they run at 37608d50 (red) and after the
fix (green). Pure: no database (the SQL size bound is test_qdig_pg.py's).
Invented names and ids only.
"""

import ast
import asyncio
import copy
import json
import os
import re
import sys

import pytest

import main
import qdig_fixtures as fx
import schemas

MAIN_SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api", "main.py"))
FTR, NEEDS = main.QDIG_FOR_THE_RECORD, main.QDIG_NEEDS_DECISION


def base():
    return fx.payload("A")


def edit(fn):
    body = base()
    fn(body)
    return body


def p(i):
    """Player i of the base body (slot order)."""
    return lambda b: b["players"][i]


def setp(i, key, value):
    def f(b):
        b["players"][i][key] = value
    return f


def delp(i, key):
    def f(b):
        del b["players"][i][key]
    return f


def settop(key, value):
    def f(b):
        b[key] = value
    return f


def deltop(key):
    def f(b):
        del b[key]
    return f


def _team(shape, **over):
    pl = lambda n: {"steam_id": fx.steam(n), "display_name": fx.NAMES[n]}   # noqa: E731
    if shape == "2v2":
        body = {"series_id": "s", "t1a": pl(1), "t1b": pl(2), "t2a": pl(3), "t2b": pl(4), "t1_rounds_won": 3,
                "t2_rounds_won": 1, "t1_points_total": 25, "t2_points_total": 12, "winner_team": 1,
                "reported_by_steam_id": fx.steam(1), "photon_room_id": "QDIGTEAM_r1", "is_ranked": True}
    else:
        body = {"series_id": "s", "solo": pl(1), "duo_a": pl(2), "duo_b": pl(3), "solo_rounds_won": 2,
                "duo_rounds_won": 3, "solo_points_total": 18, "duo_points_total": 26, "winner_side": 2,
                "reported_by_steam_id": fx.steam(2), "photon_room_id": "QDIGOVT_r1", "is_ranked": False}
    body.update(over)
    return body


def _left(i, figure, absent=False):
    """Player i left early (during this game unless absent) with this leave
    figure (game_points_at_leave)."""
    def f(b):
        b["players"][i].update(left_early=True, absent=absent, game_points_at_leave=figure)
    return f


def _dup_player(b):
    b["players"][3] = dict(b["players"][2], slot=3)


def _dup_slot(b):
    b["players"][1]["slot"] = 0


def _gap_slot(b):
    b["players"][3]["slot"] = 4


def _eleven(b):
    b["players"] = [dict(b["players"][0], steam_id=fx.steam(40 + n), slot=n) for n in range(11)]


def _deep(n=100000):
    return '{"players": ' + "[" * n + "]" * n + "}"


_HUGE_TEXT = json.dumps(base()).replace('"kills": 31', '"kills": ' + "9" * 5000, 1)
_HUGE_WORD = "unreadable" if hasattr(sys, "get_int_max_str_digits") and sys.get_int_max_str_digits() else "field_range"

# (name, mode, body (a dict, a JSON text, or a row-level override), want)
# want: "ok", a malformed word, or "unread".
TABLE = [
    ("the live shape", "ffa", base(), "ok"),
    ("an extra top-level key", "ffa", edit(settop("new_top_key", {"x": [1, 2]})), "ok"),
    ("an extra player key", "ffa", edit(setp(0, "new_player_key", [None, "x"])), "ok"),
    ("not JSON", "ffa", "{", "unreadable"),
    ("a JSON list", "ffa", "[]", "not_object"),
    ("JSON null at the top", "ffa", "null", "not_object"),
    ("a JSON number", "ffa", "1", "not_object"),
    ("players is an int", "ffa", {"players": 1}, "players"),
    ("players missing", "ffa", edit(deltop("players")), "players"),
    ("players null", "ffa", edit(settop("players", None)), "players"),
    ("players an object", "ffa", edit(settop("players", {"0": {}})), "players"),
    ("players empty", "ffa", edit(settop("players", [])), "roster_size"),
    ("two players", "ffa", edit(lambda b: b.update(players=b["players"][:2])), "roster_size"),
    ("eleven players", "ffa", edit(_eleven), "roster_size"),
    ("a list of non-objects", "ffa", edit(settop("players", [1, 2, 3, 4])), "player_shape"),
    ("a null player", "ffa", edit(lambda b: b["players"].__setitem__(1, None)), "player_shape"),
    ("account id missing", "ffa", edit(delp(1, "steam_id")), "account_id"),
    ("account id an int", "ffa", edit(setp(1, "steam_id", int(fx.steam(2)))), "account_id"),
    ("account id of 16 digits", "ffa", edit(setp(1, "steam_id", fx.steam(2)[1:])), "account_id"),
    ("account id with letters", "ffa", edit(setp(1, "steam_id", "9000000000017abcd")), "account_id"),
    ("account id null", "ffa", edit(setp(1, "steam_id", None)), "account_id"),
    ("name missing", "ffa", edit(delp(2, "display_name")), "field_type"),
    ("name null", "ffa", edit(setp(2, "display_name", None)), "field_type"),
    ("rounds a numeric string", "ffa", edit(setp(1, "rounds_won", "4")), "field_type"),
    ("rounds a float", "ffa", edit(setp(1, "rounds_won", 4.0)), "field_type"),
    ("rounds a bool", "ffa", edit(setp(1, "rounds_won", True)), "field_type"),
    ("rounds null", "ffa", edit(setp(1, "rounds_won", None)), "field_type"),
    ("rounds missing", "ffa", edit(delp(1, "rounds_won")), "field_type"),
    ("kills missing", "ffa", edit(delp(1, "kills")), "field_type"),
    ("slot a string", "ffa", edit(setp(1, "slot", "1")), "field_type"),
    ("a huge integer", "ffa", edit(setp(1, "kills", 10 ** 30)), "field_range"),
    ("a huge integer in the text", "ffa", _HUGE_TEXT, _HUGE_WORD),
    ("kills below zero", "ffa", edit(setp(1, "kills", -1)), "field_range"),
    ("points over the schema", "ffa", edit(setp(1, "points_total", 201)), "field_range"),
    ("rounds over the schema", "ffa", edit(setp(1, "rounds_won", 21)), "field_range"),
    ("left-early mark missing", "ffa", edit(delp(3, "left_early")), "marks"),
    ("absent mark a string", "ffa", edit(setp(3, "absent", "false")), "marks"),
    ("left-early mark null", "ffa", edit(setp(3, "left_early", None)), "marks"),
    ("a repeated player", "ffa", edit(_dup_player), "duplicate_player"),
    ("a repeated slot", "ffa", edit(_dup_slot), "slots"),
    ("a slot gap", "ffa", edit(_gap_slot), "slots"),
    ("winner not a player", "ffa", edit(settop("winner_steam_id", fx.steam(99))), "winner"),
    ("winner missing", "ffa", edit(deltop("winner_steam_id")), "winner"),
    ("winner an int", "ffa", edit(settop("winner_steam_id", int(fx.steam(1)))), "winner"),
    ("reporter missing", "ffa", edit(deltop("reported_by_steam_id")), "reporter"),
    ("reporter of 16 digits", "ffa", edit(settop("reported_by_steam_id", fx.steam(2)[1:])), "reporter"),
    ("room an int", "ffa", edit(settop("photon_room_id", 7)), "room"),
    ("started_at not a time", "ffa", edit(settop("started_at", "yesterday")), "field_type"),
    ("is_ranked a string", "ffa", edit(settop("is_ranked", "yes")), "field_type"),
    ("the schema refuses it", "ffa", edit(deltop("lobby_id")), "schema"),
    ("a seat that left with no leave figure", "ffa", edit(_left(3, None)), "leave_figure"),
    ("a leave figure as a numeric string", "ffa", edit(_left(3, "100")), "field_type"),
    ("a leave figure as a float", "ffa", edit(_left(3, 100.0)), "field_type"),
    ("a leave figure as true", "ffa", edit(_left(3, True)), "field_type"),
    ("a leave figure over the schema", "ffa", edit(_left(3, 32001)), "field_range"),
    ("a seat that left with its leave figure", "ffa", edit(_left(3, 100)), "ok"),
    ("an absent ghost with no leave figure", "ffa", edit(_left(3, None, absent=True)), "ok"),
    ("a timeline as a number (the strict model)", "ffa", edit(settop("timeline", 7)), "schema"),
    ("a player's fps as a numeric string (the strict model)", "ffa", edit(setp(2, "fps", "60")), "schema"),
    ("a 2v2 seat's fps as a numeric string (the strict model)", "team", _team("2v2", t1a_fps="60"), "schema"),
    ("deep nesting", "ffa", _deep(), "unreadable"),
    ("a 2v2 body", "team", _team("2v2"), "ok"),
    ("a 1v2 body", "team", _team("1v2"), "ok"),
    ("a 2v2 body with an unknown top-level key", "team", _team("2v2", new_top_key={"x": [1]}), "ok"),
    ("a 2v2 body with an unknown seat key", "team",
     _team("2v2", t2a={"steam_id": fx.steam(3), "display_name": fx.NAMES[3], "new_seat_key": [None]}), "ok"),
    ("a 1v2 body with an unknown top-level key", "team", _team("1v2", new_top_key="x"), "ok"),
    ("a 1v2 body with an unknown seat key", "team",
     _team("1v2", duo_b={"steam_id": fx.steam(3), "display_name": fx.NAMES[3], "new_seat_key": {"y": 2}}), "ok"),
    ("a 2v2 seat missing", "team", {k: v for k, v in _team("2v2").items() if k != "t2b"}, "player_shape"),
    ("a 2v2 repeated player", "team", _team("2v2", t2b={"steam_id": fx.steam(1), "display_name": "x"}),
     "duplicate_player"),
    ("a 2v2 winner team 3", "team", _team("2v2", winner_team=3), "winner"),
    ("a 2v2 winner a bool", "team", _team("2v2", winner_team=True), "winner"),
    ("2v2 rounds over the schema", "team", _team("2v2", t1_rounds_won=11), "field_range"),
    ("2v2 points a string", "team", _team("2v2", t1_points_total="25"), "field_type"),
    ("a 1v2 reporter on neither side", "team", _team("1v2", reported_by_steam_id=fx.steam(9)), "reporter"),
    ("a team row with an FFA body", "team", base(), "sides"),
    ("a mode the lane does not know", "1v1", base(), "sides"),
]


def _row(mode, body):
    r = fx.row("A")
    r["mode"] = mode
    r["payload"] = body
    if mode != "ffa":
        r["photon_room_id"] = "QDIGTEAM_r1"
        r["group_id"] = None
    return r


def test_the_table_has_at_least_thirty_shapes_and_every_word_is_named():
    assert len(TABLE) >= 30
    words = {w for _, _, _, w in TABLE} - {"ok"}
    assert words <= set(main.QDIG_MALFORMED_WORDS)
    assert set(main.QDIG_MALFORMED_WORDS) - words == {"oversize"}      # oversize: the next tests
    assert main.QDIG_UNREAD not in main.QDIG_MALFORMED_WORDS


@pytest.mark.parametrize("name,mode,body,want", TABLE, ids=[t[0] for t in TABLE])
def test_the_reader_reads_each_shape(name, mode, body, want):
    for form in ("text", "decoded"):
        if form == "decoded" and isinstance(body, str):
            continue
        payload = json.dumps(body) if form == "text" and not isinstance(body, str) else body
        v = main._qdig_read_body(_row(mode, payload))
        got = "ok" if v["ok"] else v["why"]
        assert got == want, (name, form, v)
        if not v["ok"]:
            assert v["players"] == [] and v["sides"] is None and v["winner"] is None and v["reporter"] is None


def test_extra_keys_at_each_level_read_as_the_same_value():
    plain = main._qdig_read_body(_row("ffa", json.dumps(base())))
    extra = edit(settop("new_top_key", 1))
    for pl in extra["players"]:
        pl["new_player_key"] = {"nested": [1, "x"]}
    got = main._qdig_read_body(_row("ffa", json.dumps(extra)))
    assert got == plain


def test_oversize_bodies_are_never_decoded(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("an over-size body was decoded")
    flagged = dict(fx.row("A"), payload=None, payload_oversize=True)
    big = dict(fx.row("A"), payload=" " * (main.QDIG_BODY_MAX_BYTES + 1))
    unread = dict(fx.row("A"), payload=None, payload_unread=True)
    monkeypatch.setattr(main._json, "loads", refuse)
    assert main._qdig_read_body(flagged)["why"] == "oversize"
    assert main._qdig_read_body(big)["why"] == "oversize"
    v = main._qdig_read_body(unread)
    assert v["why"] == main.QDIG_UNREAD and not v["ok"]


def test_the_reader_cannot_raise():
    class Weird:
        def __str__(self):
            raise RuntimeError("no")
    for r in ({}, {"payload": None}, {"payload": object()}, {"payload": Weird(), "mode": "ffa"},
              {"payload": b"\xff\xfe", "mode": "ffa"}, {"payload": "{}", "mode": None},
              {"payload": json.dumps(base()), "mode": "ffa", "photon_room_id": 7}):
        v = main._qdig_read_body(r)
        assert v["ok"] is False or v["shape"] == "ffa"

    # The catch-all is for what is NOT a ValueError: a body nested past the
    # decoder's recursion limit (RecursionError, inside the size bound) and a
    # row whose own reads raise (RuntimeError). Each reads as one fixed word.
    class Hostile(dict):
        def get(self, *a, **k):
            raise RuntimeError("no")
    deep = {"payload": "[" * 100000 + "]" * 100000, "mode": "ffa"}
    assert len(deep["payload"]) <= main.QDIG_BODY_MAX_BYTES
    for r in (deep, Hostile(payload="{}", mode="ffa")):
        v = main._qdig_read_body(r)
        assert (v["ok"], v["why"]) == (False, "unreadable"), v


def test_the_bounds_are_the_settlements_own():
    """The roster sizes and per-player ranges the reader enforces are the
    submit path's: FFA_MIN_PLAYERS/FFA_MAX_PLAYERS and the schema's Field
    bounds, read from the model the submit path validates with."""
    assert (main.FFA_MIN_PLAYERS, main.FFA_MAX_PLAYERS) == (3, 10)
    src = open(MAIN_SRC, encoding="utf-8").read()
    assert "FFA_MIN_PLAYERS = 3" in src and "FFA_MAX_PLAYERS = 10" in src
    assert main._QDIG_FFA_INT_FIELDS == {"slot": (0, 15), "rounds_won": (0, 20), "points_total": (0, 200),
                                         "kills": (0, 2000)}
    for f, (lo, hi) in main._QDIG_FFA_INT_FIELDS.items():
        meta = schemas.FfaPlayerEntry.model_fields[f].metadata
        assert [getattr(m, "ge", None) for m in meta if getattr(m, "ge", None) is not None] == [lo]
        assert [getattr(m, "le", None) for m in meta if getattr(m, "le", None) is not None] == [hi]
    players = schemas.FfaMatchReport.model_fields["players"].metadata
    assert [getattr(m, "max_length", None) for m in players if getattr(m, "max_length", None)] == [
        main.FFA_MAX_PLAYERS]
    assert main.QDIG_BODY_MAX_BYTES == 262144


def test_the_sql_literals_are_their_constants():
    assert "LIMIT 20" in main._QDIG_SQL_JANITOR_CANDIDATES and main.QDIG_JANITOR_PAGE == 20
    assert "LIMIT 201" in main._QDIG_SQL_PENDING and main.QDIG_CENSUS_MAX_ROWS + 1 == 201
    assert "INTERVAL '86400 seconds'" in main._QDIG_SQL_POSTED_REMINDER
    assert main.QDIG_REMINDER_EVERY_S == 86400


# ── the review's cases, through the classification and the feed ───────────

def _judge_body(body):
    r = fx.row("A", body=body)
    return fx.judge(main, r, fx.facts("A"))


@pytest.mark.parametrize("name,change", [
    ("two players on slot 0", _dup_slot),
    ("a numeric string for rounds", setp(1, "rounds_won", "4")),
    ("a missing left-early mark", delp(1, "left_early")),
    ("a missing absent mark", delp(1, "absent")),
], ids=lambda x: x if isinstance(x, str) else "")
def test_a_malformed_report_with_the_recorded_numbers_is_never_filed(name, change):
    """Game A's held numbers, which on their own are FOR THE RECORD: one
    malformed field makes the row NEEDS A DECISION."""
    assert _judge_body(base())["class"] == FTR
    v = _judge_body(edit(change))
    assert v["class"] == NEEDS, f"{name}: a malformed report was classified {v['class']}"


class _NoRows:
    async def execute(self, *a, **k):
        class R:
            def mappings(self):
                return self

            def all(self):
                return []
        return R()


def test_one_malformed_body_does_not_stop_the_feed():
    """A pending row whose body is {"players": 1} beside a live row: the
    facts are read and both rows are described; the malformed one NEEDS A
    DECISION with no numbers."""
    bad = fx.row("C2", body={"players": 1}, qid="0bad0bad-0000-4000-8000-000000000bad")
    good = fx.row("C3", qid="c3c3c3c3-0000-4000-8000-0000000000c3")
    detail = fx.detail(main, [bad, good])
    facts = asyncio.run(main._qdig_load(_NoRows(), detail))
    rows = [{"id": str(r["id"]), "mode": "ffa"} for r in (bad, good)]
    main._qdig_feed_rows(rows, {"detail": detail, "facts": facts, "gates": {}})
    assert [r["class"] for r in rows] == [NEEDS, NEEDS], rows
    assert rows[0]["players"] == [] and rows[0]["malformed"] == "players"
    assert rows[0]["reason_text"] == ("The stored report cannot be read (players), so this game needs a "
                                      "decision by hand.")
    assert rows[0]["winner_name"] is None and rows[0]["differences"] == []


def test_a_malformed_row_in_the_admin_list_shows_no_numbers():
    r = fx.row("C2", body={"players": 1})
    v = fx.judge(main, r, fx.facts("C2"))
    assert main._qdig_score(r, v, fx.facts("C2")) == ""
    assert main._qdig_admin_reason(r, v, fx.facts("C2")) == (
        "The stored report cannot be read (players), so this game needs a decision by hand. [lobby_completed]")


def test_the_admin_strings_keep_plain_names():
    """The Admin list's strings carry names as PLAIN text (the client draws
    them as text): nothing is escaped there; the bot escapes at render."""
    f = fx.facts("C2")
    f["names"][fx.steam(14)]["display_name"] = "*D_n*"
    r = fx.row("C2")
    v = fx.judge(main, r, f)
    assert main._qdig_score(r, v, f).startswith("*D_n* 5r 11p")
    src = open(MAIN_SRC, encoding="utf-8").read()
    i = src.index("async def admin_list_quarantine(")
    assert "Names stay PLAIN TEXT here, unescaped" in src[i:i + 6000]


# ── one reader: the census of raw-body uses ────────────────────────────────

LANE_FUNCS = None


def _lane_functions():
    tree = ast.parse(open(MAIN_SRC, encoding="utf-8").read())
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                n.name.startswith("_qdig") or n.name in ("admin_list_quarantine", "internal_quarantine_digest")):
            out[n.name] = n
    return out


def _touches_payload(fn):
    for n in ast.walk(fn):
        if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value == "payload":
            yield n.lineno
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get"
                and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == "payload"):
            yield n.lineno


def test_census_one_reader_of_the_stored_body():
    fns = _lane_functions()
    assert "_qdig_read_body" in fns
    touching = sorted(name for name, fn in fns.items() if list(_touches_payload(fn)))
    assert touching == ["_qdig_read_body"], touching
    for consumer in ("_qdig_janitor_pass", "admin_list_quarantine", "internal_quarantine_digest"):
        calls = {n.func.id for n in ast.walk(fns[consumer]) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "_qdig_read_rows" in calls, consumer


def test_census_every_lane_statement_selects_the_body_through_its_size():
    """Every statement of the lane that selects the stored body selects it
    through its size as text (the body above QDIG_BODY_MAX_BYTES never
    reaches Python): the module's _QDIG_SQL_* constants and the Admin
    list's statement."""
    src = open(MAIN_SRC, encoding="utf-8").read()
    i = src.index("async def admin_list_quarantine(")
    admin = src[i:src.index("return {\"reports\": out}", i)]
    stmts = {k: getattr(main, k) for k in dir(main) if k.startswith("_QDIG_SQL_")}
    stmts["admin_list_quarantine"] = admin
    selecting = {k: s for k, s in stmts.items() if re.search(r"\bpayload\b", s)}
    assert {"_QDIG_SQL_D1_DETAIL", "_QDIG_SQL_JANITOR_LOCK", "_QDIG_SQL_PENDING",
            "admin_list_quarantine"} <= set(selecting), sorted(selecting)
    for k, s in selecting.items():
        assert "octet_length(" in s and "CAST(:body_max AS bigint)" in s, (
            f"{k} selects the body without its size bound")
        # Every mention of the column is its text measured, its text handed
        # on inside the inner select (AS body) or the CASE's THEN arm.
        for m in re.finditer(r"(?<![\w>])(q\.)?payload(?![\w])(?!_)", s):
            after = s[m.end():m.end() + 6]
            ctx = s[max(0, m.start() - 20):m.end() + 16]
            if s[max(0, m.start() - 3):m.start()] == "AS ":
                continue                          # the column alias of the CASE
            assert after.startswith("::text") and (
                "octet_length(" in ctx or "AS body" in ctx or "THEN" in ctx), (k, ctx)


# ── qdig-r2: every field of the model, by its JSON type ──────────────────
#
# Generated from the models' own field lists, never from a hand list: for
# every field of every level the reader takes (the FFA report, an FFA
# player, a 2v2 and a 1v2 report, a seat of either, and the nested card,
# offer and telemetry entries), each JSON value of a type the field does not
# accept, put in its place, must make the body MALFORMED. A field that no
# code after the reader can reach would stand in EXEMPT with its reason;
# none does, because the reader validates the whole body against the
# model's strict JSON form (_qdig_strict_model). A model field whose type
# this test cannot place fails the test until someone decides its kinds.

import datetime as _dt
import types as _types
import typing as _typing

from pydantic import BaseModel as _BaseModel

# One value of each JSON type. "1" is the numeric string, 1.0 the whole
# float: the two a lax model turns into an int.
_KIND_SAMPLE = {"str": "1", "int": 1, "float": 1.0, "bool": True, "list": [], "object": {}, "null": None}


def _kinds(ann) -> set:
    """The JSON types a field of this annotation accepts in strict JSON form."""
    origin = _typing.get_origin(ann)
    if origin in (_typing.Union, _types.UnionType):
        out = set()
        for a in _typing.get_args(ann):
            out |= _kinds(a)
        return out
    if ann is type(None):
        return {"null"}
    if ann is bool:
        return {"bool"}
    if ann is int:
        return {"int"}
    if ann is float:
        return {"int", "float"}
    if ann is str or ann is _dt.datetime:
        return {"str"}
    if origin is list:
        return {"list"}
    if origin is dict:
        return {"object"}
    if isinstance(ann, type) and issubclass(ann, _BaseModel):
        return {"object"}
    raise AssertionError(("a model field of a type this test cannot place: decide its JSON kinds", ann))


def _ffa_full():
    """Game A's body with player 3 carrying a card, an offer and telemetry,
    so the nested levels have an entry to change."""
    b = base()
    b["players"][3].update(cards=[{"card_name": "Buckshot", "pick_order": 1, "round_number": 1}],
                           card_offers=[{"card_name": "Buckshot", "round_number": 1}],
                           telemetry={"ping_avg": 40})
    return b


def _team_full(shape):
    b = _team(shape)
    seat = "t1a" if shape == "2v2" else "solo"
    b[seat].update(cards=[{"card_name": "Buckshot", "pick_order": 1, "round_number": 1}],
                   card_offers=[{"card_name": "Buckshot", "round_number": 1}])
    if shape == "2v2":
        b["t1a_telemetry"] = {"ping_avg": 40}
    return b


# (level, mode, base body, model, the object at that level)
_LEVELS = [
    ("ffa report", "ffa", _ffa_full, schemas.FfaMatchReport, lambda b: b),
    ("ffa player", "ffa", _ffa_full, schemas.FfaPlayerEntry, lambda b: b["players"][3]),
    ("ffa player card", "ffa", _ffa_full, schemas.CardPick, lambda b: b["players"][3]["cards"][0]),
    ("ffa player offer", "ffa", _ffa_full, schemas.CardOfferEntry, lambda b: b["players"][3]["card_offers"][0]),
    ("ffa player telemetry", "ffa", _ffa_full, schemas.TeamPlayerTelemetry, lambda b: b["players"][3]["telemetry"]),
    ("2v2 report", "team", lambda: _team_full("2v2"), schemas.TeamMatchReport, lambda b: b),
    ("2v2 seat", "team", lambda: _team_full("2v2"), schemas.PlayerMatchData, lambda b: b["t1a"]),
    ("2v2 seat card", "team", lambda: _team_full("2v2"), schemas.CardPick, lambda b: b["t1a"]["cards"][0]),
    ("2v2 seat offer", "team", lambda: _team_full("2v2"), schemas.CardOfferEntry,
     lambda b: b["t1a"]["card_offers"][0]),
    ("2v2 seat telemetry", "team", lambda: _team_full("2v2"), schemas.TeamPlayerTelemetry,
     lambda b: b["t1a_telemetry"]),
    ("1v2 report", "team", lambda: _team_full("1v2"), schemas.OvtMatchReport, lambda b: b),
    ("1v2 seat", "team", lambda: _team_full("1v2"), schemas.PlayerMatchData, lambda b: b["solo"]),
]

# Fields no code after the reader can reach, each with its reason. Empty:
# the strict model reads every field of every level.
EXEMPT = {}


def _cases():
    out = []
    for level, mode, make, model, at in _LEVELS:
        for field, info in model.model_fields.items():
            if (level, field) in EXEMPT:
                continue
            for kind in sorted(set(_KIND_SAMPLE) - _kinds(info.annotation)):
                out.append((level, field, kind))
    return out


_CASES = _cases()
_LEVEL = {lv[0]: lv for lv in _LEVELS}


def test_every_level_reads_ok_before_any_change():
    for level, mode, make, model, at in _LEVELS:
        v = main._qdig_read_body(_row(mode, json.dumps(make())))
        assert v["ok"], (level, v["why"])


def test_the_generated_cases_cover_every_field_of_every_level():
    """The checked fields plus EXEMPT are exactly each model's fields: a
    field the model gains is a case here (or a decision in EXEMPT)."""
    for level, mode, make, model, at in _LEVELS:
        checked = {f for lv, f, _ in _CASES if lv == level}
        exempt = {f for lv, f in EXEMPT if lv == level}
        assert not checked & exempt
        assert checked | exempt == set(model.model_fields), level
    assert len(_CASES) >= 300


@pytest.mark.parametrize("level,field,kind", _CASES, ids=[f"{a}.{b}={c}" for a, b, c in _CASES])
def test_every_field_given_a_json_type_it_does_not_accept_is_malformed(level, field, kind):
    _, mode, make, model, at = _LEVEL[level]
    body = make()
    at(body)[field] = copy.deepcopy(_KIND_SAMPLE[kind])
    v = main._qdig_read_body(_row(mode, json.dumps(body)))
    assert v["ok"] is False, f"{level}.{field} as a JSON {kind} was read as valid"
    assert v["why"] in main.QDIG_MALFORMED_WORDS, (level, field, kind, v["why"])


# ── qdig-r2: the reviewer's case ─────────────────────────────────────────

def _left_early_both_sides(figure):
    """Game A's held body with seat 4 (player 3) left during the game with
    this leave figure, and the recorded game naming seat 4 as left early
    too; everything else as the fixture's game A, which on its own is FOR
    THE RECORD."""
    body = edit(_left(3, figure))
    f = fx.facts("A")
    for vec in f["vectors"][str(fx.MATCH_A)]:
        if vec["steam_id"] == fx.steam(4):
            vec["left_early"] = True
    return fx.judge(main, fx.row("A", body=body), f)


def test_a_leave_figure_sent_as_a_string_needs_a_decision_and_is_never_filed():
    v = _left_early_both_sides("100")
    assert v["class"] != FTR, "a leave figure sent as the string \"100\" was classified for_the_record"
    assert v["class"] == NEEDS
    assert v["malformed"] == "field_type"


def test_control_a_correct_leave_figure_and_an_allowed_null_classify_as_before():
    """The accepted shapes stay accepted: an int leave figure on the seat
    that left, a null on an absent ghost, and the plain live shape, each
    classify as they did before the strict reading."""
    assert _left_early_both_sides(100)["class"] == FTR
    ghost = edit(_left(3, None, absent=True))
    assert main._qdig_read_body(_row("ffa", json.dumps(ghost)))["ok"] is True
    assert _judge_body(base())["class"] == FTR
    for game in ("A", "B", "C2", "C3"):
        assert main._qdig_read_body(fx.row(game))["ok"] is True, game


# ── qdig-r2: the reader's leave-figure rule is the submit path's ─────────

@pytest.mark.parametrize("left_early,absent,figure", [
    (le, ab, fig) for le in (False, True) for ab in (False, True) for fig in (None, 100)])
def test_the_reader_and_the_submit_path_agree_on_a_missing_leave_figure(left_early, absent, figure):
    """Two copies of one rule: the reader answers leave_figure exactly when
    the submit path's _ffa_missing_leave_figure names that seat."""
    body = base()
    body["players"][3].update(left_early=left_early, absent=absent, game_points_at_leave=figure)
    submit_names = main._ffa_missing_leave_figure(schemas.FfaMatchReport.model_validate(body))
    v = main._qdig_read_body(_row("ffa", json.dumps(body)))
    reader_names = [fx.steam(4)] if v["why"] == "leave_figure" else []
    assert reader_names == submit_names, (left_early, absent, figure, v["why"], submit_names)
    assert v["ok"] or v["why"] == "leave_figure", v["why"]
