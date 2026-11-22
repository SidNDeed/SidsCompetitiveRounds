"""The calibration tool (review_calibrate): a named revision counted rule by
rule over recorded evidence, read only; the cohort and its check.

Every rule bound below is INVENTED for these tests (an unusual value chosen
only to exercise the machinery) and is written as a V(<constant>) call, so a
separate check can read them all. Player ids, game keys and rooms are
obviously synthetic.

The live cases (every test whose name holds `live`) run against a throwaway
database built the way the combat evidence lane builds its own
(combat_evidence_pg.case: the seat-evidence build with every evidence
domain's tables), through the tool's own connection (session_factory with a
statement recorder); they FAIL rather than skip when
SEAT_EVIDENCE_TEST_PG_DSN is unset, unless SEAT_EVIDENCE_TEST_PG_OPTOUT=1
waives it (seat_evidence_pg.require_live_pg).

THE APPROVED SHAPE (shape_faults): a statement's kind is one of BEGIN,
ROLLBACK, SELECT, WITH, SHOW; every name followed by a parenthesis is an
approved function, an SQL word, or a CTE the statement itself declares with
WITH RECURSIVE; no write word, no row lock. Approved functions: the ones the
tool's and the passes' read helpers use (APPROVED_FUNCTIONS) and three the
driver and the SQL dialect use on their own (DRIVER_FUNCTIONS: version and
current_schema from the dialect's first-connect initialization, array_agg
from the driver's type introspection). set_config and current_setting are on
no list.
"""

import asyncio
import builtins
import contextlib
import hashlib
import inspect
import json
import os
import re
import signal
import subprocess
import sys
import time
import types
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import review_tripwire  # noqa: E402 -- installed by the suite's conftest
import review_boot  # noqa: E402,F401 -- before any closure module
import card_evidence as ce  # noqa: E402
import card_measures as cm  # noqa: E402
import card_revision_kit as kit  # noqa: E402
import combat_evidence_fixtures as cfx  # noqa: E402
import identity_clock_fixtures as ifx  # noqa: E402
import review_calibrate as rc  # noqa: E402
import review_rules as rr  # noqa: E402

REAL_SESSION_FACTORY = rc.session_factory     # before any test stubs it

# -- the planted revision ----------------------------------------------------------------

ID_DUP = "r7e5ca001"
ID_HELD = "r7e5ca002"
ID_RAISE = "r7e5ca003"
ID_WIN = "r7e5ca004"
ID_IDB = "r7e5cb001"
ID_CMB = "r7e5cc001"
ID_GAME = "r7e5cd001"
WINDOW_DAYS = 11


def M(name):
    return {"m": name}


def V(v):
    return {"v": v}


def cmp(a, rel, b):
    return {"op": "op.cmp", "args": {"a": a, "rel": rel, "b": b}}


def _rule(rid, scope, subject, when, show, line):
    return {"id": rid, "scope": scope, "subject": subject, "effect": "flag", "post": False,
            "post_since": None, "when": when, "show": show, "line": line}


def planted_doc():
    return {
        "format": 1, "nonce": "", "vocabulary": [], "closure": {},
        "measure_params": {cm.WINDOW: {cm.WINDOW_KEY: WINDOW_DAYS}},
        "rules": [
            _rule(ID_DUP, "card", "card.hand", cmp(M("b4.hand.dup"), "gt", V(0.375)),
                  [["dup", "b4.hand.dup"]], "planted dup {dup}"),
            _rule(ID_HELD, "card", "card.hand", cmp(M("b4.hand.heldrej"), "gt", V(7.25)),
                  [["held", "b4.hand.heldrej"]], "planted held {held}"),
            _rule(ID_RAISE, "card", "card.hand", cmp(M("b4.hand.spx"), "ge", V(0.625)),
                  [["spx", "b4.hand.spx"]], "planted spx {spx}"),
            _rule(ID_WIN, "card", "card.window", cmp(M("b4.rar.hands"), "gt", V(4.5)),
                  [["hands", "b4.rar.hands"]], "planted window {hands}"),
            _rule(ID_IDB, "identity", "ic.seat",
                  {"not": {"op": "op.truth", "args": {"a": M("ic.seat.build_registered")}}},
                  [["seat", "ic.seat.index"]], "planted unregistered {seat}"),
            _rule(ID_CMB, "combat", "combat.cycle", cmp(M("b2.cycle.rexp"), "gt", V(913)),
                  [["units", "b2.cycle.units"]], "planted cycle {units}"),
            _rule(ID_GAME, "game", "seat", cmp(M("seat.published_hits"), "ge", V(37.125)),
                  [["p", "seat.published_hits"]], "planted game {p}"),
        ],
    }


def build_planted(tmp, doc=None, name="draft"):
    """A revision built by review_rules.build_revision in a temporary rules
    root. Returns (root, rev)."""
    root = os.path.join(str(tmp), "root")
    os.makedirs(root, exist_ok=True)
    draft = os.path.join(str(tmp), name)
    os.makedirs(draft, exist_ok=True)
    with open(os.path.join(draft, "rules.json"), "w", encoding="utf-8") as f:
        json.dump(planted_doc() if doc is None else doc, f)
    with open(os.path.join(draft, "selftest.json"), "w", encoding="utf-8") as f:
        json.dump({"cases": []}, f)
    return root, rr.build_revision(draft, root, "synthetic")


@pytest.fixture(scope="module")
def planted(tmp_path_factory):
    root, rev = build_planted(tmp_path_factory.mktemp("calib"))
    path = os.path.join(root, "rules-" + rev)
    return path, rr.load_dir(path)


@pytest.fixture
def rooted(planted, monkeypatch):
    """The planted revision's root is THE review root (review_rules.rules_root)."""
    path, rs = planted
    monkeypatch.setenv(rr.ROOT_ENV, os.path.dirname(path))
    return path, rs


def call_main(argv):
    """main(argv); any exception that leaves main fails the test (the
    outermost handler must hold every one)."""
    try:
        return rc.main(argv)
    except BaseException as e:                 # noqa: BLE001
        pytest.fail("main raised %s" % type(e).__name__)


# -- synthetic card views -----------------------------------------------------------------

SEAT_P = "70000000-0000-0000-0000-00000000c0a1"
SEAT_Q = "70000000-0000-0000-0000-00000000c0b2"
SEAT_R = "70000000-0000-0000-0000-00000000c0c3"
PROFILE = "7" * 64
DAY0 = date(2026, 3, 5)


def hand(dup=0, heldrej=0, spx=0, *, recorder=SEAT_P, dealer=SEAT_Q, w=0,
         obs=(3, 1, 0), exp=(2.5, 1.25, 0.25), var=(1.5, 0.75, 0.125), n=5):
    row = {"b4.hand.dup": dup, "b4.hand.heldrej": heldrej, "b4.hand.spx": spx}
    meta = {"recorder": recorder, "dealer": dealer, "w": w, "profile": PROFILE, "weighed": True,
            "exp": (list(obs), list(exp), list(var)), "n": n}
    return row, meta


def view(*hands, two=True):
    return {"hands": list(hands), "phases": [], "records": [], "pairs": [], "game": None,
            "two": two}


class FakeFetch:
    """The injectable fetch layer: per domain, the planted items in order.
    `now` counts the items handed out (a test clock); `before` is called with
    that count just before each item is handed out; `closed` lists the
    domains whose item generator was closed."""

    def __init__(self, by_domain, before=None):
        self.by_domain = by_domain
        self.before = before
        self.now = 0
        self.closed = []

    async def totals(self):
        return {d: len(self.by_domain.get(d, ())) for d in rc.DOMAINS}

    async def items(self, domain, rs):
        try:
            for it in self.by_domain.get(domain, ()):
                self.now += 1
                if self.before is not None:
                    self.before(self.now)
                yield it
        finally:
            self.closed.append(domain)


# -- identity and combat inputs -------------------------------------------------------------

BUILD = ("1.41.0", "STANDALONE", "abcdef123456", "e" * 64)
ID_SEAT_A = "70000000-0000-0000-0000-00000000d1a1"
ID_SEAT_B = "70000000-0000-0000-0000-00000000d1b2"
CMB_SEAT_A = "70000000-0000-0000-0000-00000000e1a1"
CMB_SEAT_B = "70000000-0000-0000-0000-00000000e1b2"


def id_view(seat, other, rec):
    return {"seat": seat, "other": other, "rec": rec, "header_version": "1.41.0",
            "conflict": False, "conn_class": "none", "conn_ranges": "absent", "post_clock": "ok",
            "seat_build": list(BUILD), "relayed_build": "1.41.0|STANDALONE|abcdef123456",
            "fit": None, "fit_rows": 0}


def id_pair():
    return [id_view(ID_SEAT_A, ID_SEAT_B, ifx.base_record()),
            id_view(ID_SEAT_B, ID_SEAT_A, ifx.base_record(proc=ifx.PROC_B))]


def regs(registered):
    return {"release": {BUILD: "release"} if registered else {}, "game_files": set()}


def combat_fire():
    return cfx.records(*cfx.a24_pair(), a=CMB_SEAT_A, b=CMB_SEAT_B)


def combat_quiet():
    return cfx.records(cfx.empty_record(), None, a=CMB_SEAT_A, b=CMB_SEAT_B)


def planted_items():
    """Three card games (dup fires on the first, held on the second, the spx
    rule raises on the third) and two skipped; two identity games (the build
    rule fires on the unregistered one) and one skipped; two combat games
    (the cycle rule fires on the first)."""
    return {
        "card": [
            ("game", (view(hand(dup=3)), DAY0)),
            ("skip", "nomatch"),
            ("game", (view(hand(heldrej=8)), DAY0)),
            ("game", (view(hand(spx="text")), DAY0)),
            ("skip", "purged"),
        ],
        "identity": [
            ("game", (id_pair(), regs(True))),
            ("game", (id_pair(), regs(False))),
            ("skip", "unnamed"),
        ],
        "combat": [
            ("game", combat_fire()),
            ("game", combat_quiet()),
        ],
    }


def counts(tally):
    return {rid: (c["evaluated"], c["fired"], c["errors"]) for rid, c in tally.counts.items()}


def _tail(lines):
    """The report's last line."""
    *_rest, tail = lines
    return tail


def _middle(lines):
    """The report's lines between its first and its last."""
    _head, *middle, _tail_line = lines
    return middle


def run(coro):
    return asyncio.run(coro)


# -- the counting core ----------------------------------------------------------------------

def test_each_rule_is_counted_alone_over_the_planted_games(planted):
    _path, rs = planted
    tally = run(rc.walk(rs, FakeFetch(planted_items())))
    got = counts(tally)
    assert got[ID_DUP] == (3, 1, 0)
    assert got[ID_HELD] == (3, 1, 0)
    assert got[ID_RAISE] == (3, 0, 1)
    assert got[ID_IDB] == (2, 1, 0)
    assert got[ID_CMB] == (2, 1, 0)
    assert ID_GAME not in got and tally.uncounted == 1


def test_the_full_ruleset_would_change_the_counts(planted, monkeypatch):
    """Negative control of the one-rule copy: evaluated with the whole
    ruleset, the raising rule's error lands on every other card rule."""
    _path, rs = planted
    alone = counts(run(rc.walk(rs, FakeFetch(planted_items()))))
    monkeypatch.setattr(rc, "one_rule", lambda rs_, rule: rs_)
    whole = counts(run(rc.walk(rs, FakeFetch(planted_items()))))
    assert whole != alone
    assert whole[ID_DUP][2] == 1 and alone[ID_DUP][2] == 0


def test_the_one_rule_copy_holds_only_that_rule_and_leaves_the_ruleset_alone(planted):
    _path, rs = planted
    before = [r.id for r in rs.rules]
    rule = rs.rule(ID_HELD)
    single = rc.one_rule(rs, rule)
    assert [r.id for r in single.card_rules] == [ID_HELD] and single.identity_rules == []
    assert [r.id for r in rs.rules] == before and single.core is rs.core


def test_skipped_games_are_counted_by_word_and_never_as_walked(planted):
    _path, rs = planted
    tally = run(rc.walk(rs, FakeFetch(planted_items())))
    assert tally.domains["card"] == {"walked": 3, "skipped": {"nomatch": 1, "purged": 1}}
    assert tally.domains["identity"] == {"walked": 2, "skipped": {"unnamed": 1}}
    assert tally.domains["combat"] == {"walked": 2, "skipped": {}}
    lines = rc.render(tally)
    assert "domain card walked=3 windows=1 skipped=2 nomatch=1 purged=1" in lines
    assert "domain identity walked=2 skipped=1 unnamed=1" in lines
    assert "domain combat walked=2 skipped=0" in lines
    assert "rule %s scope=card evaluated=3 fired=0 errors=1" % ID_RAISE in lines
    assert "game and sitting rules not counted: 1" in lines


def test_the_report_ends_with_its_end_line_once_and_the_count_lines_are_unchanged(planted):
    """[13]: the last line is `report end`, exactly once; the lines before it
    are the summary, one per counted rule, one per domain and the uncounted
    line, in that order."""
    _path, rs = planted
    tally = run(rc.walk(rs, FakeFetch(planted_items())))
    lines = rc.render(tally)
    assert _tail(lines) == "report end" and lines.count("report end") < 2
    assert len(lines) == 1 + len(tally.rules) + len(rc.DOMAINS) + 1 + 1
    assert lines[0] == ("run whole: games read 10 of 10 (card 5 of 5, identity 3 of 3, "
                        "combat 2 of 2)")
    assert [ln.split()[1] for ln in lines[1:1 + len(tally.rules)]] == [r.id for r in tally.rules]
    assert lines[-2] == "game and sitting rules not counted: 1"


# -- the card windows -----------------------------------------------------------------------

def window_items():
    """Contributions over several days for one class (dealer Q, own hands,
    paired, one profile) and one game of another class (dealer R)."""
    return {"card": [
        ("game", (view(hand(), hand()), DAY0)),
        ("game", (view(hand(), hand(), hand()), DAY0 + timedelta(days=1))),
        ("game", (view(hand(recorder=SEAT_R, dealer=SEAT_R)), DAY0 + timedelta(days=1))),
        ("game", (view(hand()), DAY0 + timedelta(days=12))),
    ]}


def test_windows_are_rebuilt_as_the_pass_builds_them_and_each_is_evaluated_once(planted):
    _path, rs = planted
    tally = run(rc.walk(rs, FakeFetch(window_items())))
    wins, word = rc.rebuild_windows(tally.daily, rs)
    assert word is None
    got = [(k[0], k[1], agg["games"], agg["hands"], agg["slots"]) for k, agg in wins]
    # width 11: the class of Q ends windows on days 0, 1 and 12; day 12's window
    # (days 2..12) holds only day 12. R's class has one window.
    assert sorted(got) == sorted([
        (SEAT_Q, DAY0, 1, 2, 10),
        (SEAT_Q, DAY0 + timedelta(days=1), 2, 5, 25),
        (SEAT_Q, DAY0 + timedelta(days=12), 1, 1, 5),
        (SEAT_R, DAY0 + timedelta(days=1), 1, 1, 5),
    ])
    q1 = next(agg for k, agg in wins if k[0] == SEAT_Q and k[1] == DAY0 + timedelta(days=1))
    assert q1["obs"] == [15, 5, 0] and q1["source"] == cm.WORD["self"]
    assert q1["coverage"] == cm.WORD["paired"]
    assert tally.windows == 4 and tally.windows_total == 4
    # the window rule: once per window, fired on the one window over its bound
    assert counts(tally)[ID_WIN] == (4, 1, 0)
    # the game-level card rules are not evaluated on windows
    assert counts(tally)[ID_DUP][0] == 4


class _WindowDb:
    """Answers card_evidence._windows' daily read from in-memory daily rows."""

    def __init__(self, daily, rev):
        self.daily, self.rev = daily, rev

    async def execute(self, stmt, b):
        assert "FROM card_player_daily" in str(stmt) and b["rev"] == self.rev
        rows = []
        for (s, d, src, cov, p), r in sorted(self.daily.items(), key=str):
            if (s, src, cov, p) == (b["s"], b["src"], b["cov"], b["p"]) \
                    and b["a"] - timedelta(days=b["w"]) < d <= b["b"]:
                row = {"day": d, "games": len(r["games"])}
                row.update({c: r[c] for c in ce._DAILY_COLS})
                rows.append(row)
        return FakeResult(rows)


def test_the_window_rebuild_equals_the_pass_window_reader_over_the_same_daily_rows(planted):
    _path, rs = planted
    tally = run(rc.walk(rs, FakeFetch(window_items())))
    keys = [k + (rs.rev,) for k in tally.daily]
    theirs, _owned = run(ce._windows(_WindowDb(tally.daily, rs.rev), keys, rs))
    mine, word = rc.rebuild_windows(tally.daily, rs)
    assert word is None
    assert len(mine) == len(theirs) == 4
    assert sorted(mine, key=str) == sorted(theirs, key=str)


def test_no_window_parameter_means_no_windows(tmp_path):
    doc = planted_doc()
    doc["measure_params"] = {}
    root, rev = build_planted(tmp_path, doc)
    rs = rr.load_dir(os.path.join(root, "rules-" + rev))
    tally = run(rc.walk(rs, FakeFetch(window_items())))
    assert tally.windows == 0 and counts(tally)[ID_WIN] == (0, 0, 0)


def _daily_of(items, rs):
    tally = rc.Tally(rs)
    for _kind, payload in items["card"]:
        tally.game("card", payload)
    return tally.daily


def test_the_window_rebuild_stops_inside_its_loops_at_the_deadline(planted):
    """[9]: the rebuild checks the deadline per class and per end day. A
    clock that reads 0, 1, 2, ... with the deadline at 2: the class check of
    Q reads 0, its first day 1 (window built), its second day 2 (cut). Either
    check removed gives another result (two windows; or all four, uncut)."""
    _path, rs = planted
    daily = _daily_of(window_items(), rs)
    calls = []

    def clock():
        calls.append(1)
        return len(calls) - 1
    wins, word = rc.rebuild_windows(daily, rs, deadline_at=2, clock=clock)
    assert word == "deadline"
    assert [(k[0], k[1]) for k, _agg in wins] == [(SEAT_Q, DAY0)]
    assert len(calls) == 3
    # control: the same rebuild with a deadline it never reaches builds all four
    whole, none = rc.rebuild_windows(daily, rs, deadline_at=10 ** 6, clock=clock)
    assert none is None and len(whole) == 4


def test_a_stop_signal_stops_the_window_rebuild(planted, monkeypatch):
    _path, rs = planted
    daily = _daily_of(window_items(), rs)
    monkeypatch.setitem(rc._STOP, "word", "stopped")
    wins, word = rc.rebuild_windows(daily, rs)
    assert (wins, word) == ([], "stopped")


# -- the output holds no identifier ---------------------------------------------------------

def test_the_output_holds_no_identifier(planted):
    _path, rs = planted
    items = planted_items()
    items["card"] += window_items()["card"]
    out = "\n".join(rc.render(run(rc.walk(rs, FakeFetch(items)))))
    for ident in (SEAT_P, SEAT_Q, SEAT_R, ID_SEAT_A, ID_SEAT_B, CMB_SEAT_A, CMB_SEAT_B, PROFILE):
        assert ident not in out and ident[-4:] not in out
    assert ID_DUP in out


# -- the approved statement shape ([5], [8]) ----------------------------------------------------

APPROVED_KINDS = frozenset({"BEGIN", "ROLLBACK", "SELECT", "WITH", "SHOW"})
APPROVED_FUNCTIONS = frozenset({
    "least", "greatest", "make_interval", "now", "cast", "any", "coalesce", "jsonb_typeof",
    "to_char", "date_trunc", "count", "exists"})
DRIVER_FUNCTIONS = frozenset({"version", "current_schema", "array_agg"})
SQL_WORDS = frozenset({
    "and", "or", "in", "as", "on", "not", "distinct", "over", "values", "from", "where",
    "select", "when", "then", "else", "case", "join", "by", "is", "all", "union"})

_WRITE = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|COPY"
                    r"|COMMIT|LOCK|NOTIFY|LISTEN|CALL|DO|SET|RESET|DISCARD|PREPARE|EXECUTE)\b", re.I)
_LOCK = re.compile(r"\bFOR\s+(NO\s+KEY\s+UPDATE|UPDATE|SHARE|KEY\s+SHARE)\b", re.I)
_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_STRING = re.compile(r"'(?:[^']|'')*'")
_QIDENT = re.compile(r'"(?:[^"]|"")*"')
_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_CTE = re.compile(r"\bRECURSIVE\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.I)
_SHOW = re.compile(r"SHOW(\s+[A-Za-z_]+)+\s*;?", re.I)     # a setting's name, words only


def shape_faults(sql):
    """Every way `sql` is off the approved shape (empty: approved). Strings,
    quoted identifiers and comments are removed first, so a word inside a
    literal is not read as a call."""
    s = _QIDENT.sub(" ", _STRING.sub(" ", _COMMENT.sub(" ", sql)))
    words = s.split()
    faults = []
    kind = words[0].upper().rstrip(";") if words else ""
    if kind not in APPROVED_KINDS:
        faults.append("kind " + kind)
    ctes = {m.group(1).lower() for m in _CTE.finditer(s)}
    for m in _CALL.finditer(s):
        name = m.group(1).lower()
        if not (name in APPROVED_FUNCTIONS or name in DRIVER_FUNCTIONS or name in SQL_WORDS
                or name in ctes):
            faults.append("function " + name)
    if kind != "SHOW" and _WRITE.search(s):
        faults.append("write word " + _WRITE.search(s).group(1))
    if kind == "SHOW" and not _SHOW.fullmatch(s.strip()):
        faults.append("show form")
    if _LOCK.search(s):
        faults.append("row lock")
    return faults


def tool_statements():
    """Every SQL text the tool's module holds."""
    out = [rc._GAMES_SQL.format(t=t) for t in rc._TABLES.values()]
    out += [rc._CARD_ROWS.text, rc._CARD_MATCH.text, rc._ICE_ROWS.text, rc._ICE_MATCH.text,
            rc._COMBAT_ROWS.text, rc._COMBAT_MATCH.text, rc._AT_SQL]
    out += [rc.cohort_sql(d) for d in rc.DOMAINS]
    return out


def test_the_shape_check_refuses_every_unlisted_kind_function_write_and_lock():
    """Negative control of the checker: each of these is red, the tool's own
    statements and the driver's introspection shape are green."""
    for sql in ("INSERT INTO x VALUES (1)", "update x set y = 1", "DELETE FROM x",
                "SET jit = off", "SELECT set_config('jit', 'off', false)",
                "SELECT current_setting('jit')", "SELECT pg_notify('x', 'y'), id FROM card_evidence",
                "SELECT nextval('s')", "SELECT pg_advisory_xact_lock(1)", "COMMIT",
                "SELECT * FROM x FOR UPDATE", "SELECT * FROM x FOR NO KEY UPDATE",
                "SELECT * FROM x FOR SHARE", "LOCK TABLE x", "CALL p()", "NOTIFY x",
                "WITH d AS (DELETE FROM t RETURNING 1) SELECT 1", "TRUNCATE x",
                "SHOW jit; SET jit = on", "SELECT lo_import('/x')", "SELECT dblink('x', 'y')"):
        assert shape_faults(sql), sql
    for sql in tool_statements():
        assert shape_faults(sql) == [], (sql[:80], shape_faults(sql))
    assert shape_faults("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;") == []
    assert shape_faults("ROLLBACK;") == [] and shape_faults("show standard_conforming_strings") == []
    assert shape_faults("WITH RECURSIVE tree(oid, depth) AS (SELECT array_agg(a) FROM t "
                        "WHERE a = any($1::oid[])) SELECT * FROM tree") == []
    # a word inside a literal is not a call; outside one it is
    assert shape_faults("SELECT to_char(now(), 'set_config(x)')") == []
    assert shape_faults("SELECT to_char(now(), 'x'), set_config('a', 'b', false)") != []


def test_every_sql_text_of_the_tool_is_an_approved_shape():
    bad = [(s[:60], shape_faults(s)) for s in tool_statements() if shape_faults(s)]
    assert bad == []


class FakeResult:
    def __init__(self, rows):
        self.rows = [dict(r) for r in rows]

    def all(self):
        return [tuple(r.values()) for r in self.rows]

    def first(self):
        return tuple(self.rows[0].values()) if self.rows else None

    def scalar(self):
        return next(iter(self.rows[0].values())) if self.rows else None

    def scalars(self):
        return FakeResult([{"v": next(iter(r.values()))} for r in self.rows])

    def mappings(self):
        return _Mappings(self.rows)


class _Mappings:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


KEY_C = "calibkeyQX7251card"
KEY_I = "calibkeyQX7251ident"
KEY_B = "calibkeyQX7251cmb"
ROOM_C = "calibroomZQ9137card"
ROOM_I = "calibroomZQ9137ident"
ROOM_B = "calibroomZQ9137cmb"
LO = "70000000-0000-0000-0000-0000000f7a01"
HI = "70000000-0000-0000-0000-0000000f7a02"
MATCH_C = "70000000-0000-0000-0000-0000000fa0c1"
MATCH_I = "70000000-0000-0000-0000-0000000fa0c2"
MATCH_B = "70000000-0000-0000-0000-0000000fa0c3"
ENDED = datetime(2026, 3, 7, 18, 45, tzinfo=timezone.utc)


def full_game_dump():
    """The census of the committed full-game fixture, as an admin registers it."""
    inp = kit.fixture_input("full_game")
    names = {c[0]: c[1] for c in inp["cards"]}
    rarity = {c[0]: c[2] for c in inp["cards"] if 0 <= c[2] < len(cm.RARITIES)}
    return kit.census_dump(kit.census_cards(inp["pool"][0], names=names, rarity=rarity),
                           slots=inp["ns"])


class RecordingSession:
    """A session that records every statement and answers the tool's reads
    from planted rows; any statement it does not know fails the test."""

    def __init__(self):
        self.log = []
        dump = full_game_dump()
        census = cm.census_from_dump(dump)
        self.dump = dump
        self.card_rec = kit.on_census(kit.fixture_record("full_game"), census)
        owner, meas = cfx.a24_pair()
        self.cmb = [(LO, HI, owner), (HI, LO, meas)]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        self.log.append(("COMMIT", None))

    async def rollback(self):
        self.log.append(("ROLLBACK", None))

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.log.append((sql, params))
        return FakeResult(self._answer(sql, params or {}))

    def _answer(self, sql, b):
        if sql.startswith("WITH cand AS") and "make_interval(days" in sql:
            table = sql.split(" FROM ", 1)[1].split()[0]
            key, mid = {"card_evidence": (KEY_C, MATCH_C),
                        "identity_clock_evidence": (KEY_I, MATCH_I),
                        "combat_evidence": (KEY_B, MATCH_B)}[table]
            assert set(b) == {"days", "lag"}
            return [{"k": key, "lo": LO, "hi": HI, "mid": mid, "recent": True}]
        if "FROM card_evidence WHERE" in sql:
            assert b["k"] == KEY_C
            return [{"id": 1, "seat_player_id": LO, "other_player_id": HI, "attach_key": ROOM_C,
                     "payload": self.card_rec, "pool_digest": self.dump["digest"],
                     "conflict_at": None, "received_at": ENDED, "gen": 1}]
        if "LEFT JOIN ranked_series" in sql:
            assert b == {"mid": MATCH_C}
            return [{"id": MATCH_C, "ended_at": ENDED, "photon_room_id": ROOM_C, "sc": None}]
        if "FROM card_pool_registry" in sql:
            return [{"census": self.dump, "digest": self.dump["digest"], "gen": 1}]
        if "FROM match_cards" in sql:
            return []
        if "FROM mod_release_digests" in sql or "FROM game_file_digests" in sql:
            return []
        if "FROM identity_clock_evidence WHERE stable_game_key" in sql:
            assert b["k"] == KEY_I
            return [{"id": 2, "seat_player_id": LO, "other_player_id": HI, "attach_key": ROOM_I,
                     "payload": ifx.base_record(), "header_mod_version": "1.41.0",
                     "conflict_at": None, "conn_class": "none", "conn_ranges": "absent",
                     "post_clock": "ok", "post_proc": ifx.PROC_A, "lists_purged_at": None}]
        if "FROM identity_clock_evidence WHERE seat_player_id" in sql:
            return []
        if "FROM seat_evidence WHERE stable_game_key" in sql:
            return []
        if sql.startswith("SELECT id, player1_id, player2_id, ended_at, photon_room_id FROM matches"):
            assert b == {"mid": MATCH_I}
            return [{"id": MATCH_I, "player1_id": LO, "player2_id": HI, "ended_at": ENDED,
                     "photon_room_id": ROOM_I}]
        if "FROM combat_evidence WHERE" in sql:
            assert b["k"] == KEY_B
            return [{"id": 3 + i, "seat_player_id": s, "other_player_id": o, "attach_key": ROOM_B,
                     "payload": rec, "conflict_at": None} for i, (s, o, rec) in enumerate(self.cmb)]
        if sql.startswith("SELECT id, photon_room_id, player1_id, player2_id, ended_at FROM matches"):
            assert b == {"mid": MATCH_B}
            return [{"id": MATCH_B, "photon_room_id": ROOM_B, "player1_id": LO, "player2_id": HI,
                     "ended_at": ENDED}]
        raise AssertionError("the fake does not know this statement: " + sql[:120])


def test_every_statement_the_walk_sends_is_an_approved_shape_and_it_ends_with_a_rollback(
        planted, capsys):
    """[8]: the APPROVED-SHAPE holder. Every statement's kind and every
    function it calls must be listed; anything unlisted is red (a notifying
    call added to a read the fake still answers is the mutant)."""
    _path, rs = planted
    sess = RecordingSession()
    tally = run(rc.walk_db(rs, lambda: sess, 41))
    printed = capsys.readouterr()
    sqls = [s for s, _b in sess.log]
    assert sqls[-1] == "ROLLBACK" and sqls.count("ROLLBACK") == 1 and "COMMIT" not in sqls
    bad = [(s[:80], shape_faults(s)) for s in sqls if shape_faults(s)]
    assert bad == [], bad
    # every domain was read through to evaluation
    assert {d: v["walked"] for d, v in tally.domains.items()} == {"card": 1, "identity": 1,
                                                                    "combat": 1}
    selections = [b for s, b in sess.log if s.startswith("WITH cand AS")]
    assert len(selections) == 3 and all(b["days"] == 41 for b in selections)
    assert counts(tally)[ID_CMB] == (1, 1, 0)
    out = "\n".join(rc.render(tally) + [printed.out, printed.err])
    for ident in (KEY_C, KEY_I, KEY_B, ROOM_C, ROOM_I, ROOM_B, LO, HI, MATCH_C, MATCH_I, MATCH_B,
                  "QX7251", "ZQ9137", "f7a0", "fa0c"):
        assert ident not in out, ident


@pytest.mark.parametrize("word", ["outside", "nomatch"])
def test_a_game_whose_canonical_match_is_old_or_missing_is_skipped_by_its_word(planted, word):
    """The selection's canonical match decides: not recent -> outside, none ->
    nomatch; neither game is read further."""
    _path, rs = planted

    class S(RecordingSession):
        def _answer(self, sql, b):
            rows = super()._answer(sql, b)
            if sql.startswith("WITH cand AS") and "card_evidence" in sql.split(" FROM ", 1)[1][:20]:
                rows[0]["recent"] = word != "outside"
                if word == "nomatch":
                    rows[0]["mid"] = None
                    rows[0]["recent"] = None
            return rows
    sess = S()
    tally = run(rc.walk_db(rs, lambda: sess, 41))
    assert tally.domains["card"] == {"walked": 0, "skipped": {word: 1}}
    assert not any("FROM card_evidence WHERE" in s for s, _b in sess.log)


def test_a_purged_record_is_skipped_by_its_own_word(planted):
    _path, rs = planted
    sess = RecordingSession()
    sess.card_rec = {k: v for k, v in sess.card_rec.items() if k != ce.LIST_KEYS[0]}
    tally = run(rc.walk_db(rs, lambda: sess, 41))
    assert tally.domains["card"] == {"walked": 0, "skipped": {"purged": 1}}


@pytest.mark.parametrize("fn", ["rebuild_faults", "section_faults"])
def test_a_combat_game_whose_fault_rebuild_raises_is_not_evaluated_as_the_pass_does_not(
        planted, monkeypatch, fn):
    """The combat pass rebuilds every record's fault rows before it
    evaluates, in one try, and evaluates nothing when a rebuild raises
    (combat_evidence.py:369-376). The tool counts that game under its own
    word and evaluates no rule on it; the other domains are unaffected."""
    _path, rs = planted
    assert rc.cev.cm is rc.cbm               # the tool calls the pass's own rebuild functions

    def planted_fault(*_a, **_k):
        raise ValueError("planted rebuild fault")
    monkeypatch.setattr(rc.cbm, fn, planted_fault)
    tally = run(rc.walk_db(rs, lambda: RecordingSession(), 41))
    assert tally.domains["combat"] == {"walked": 0, "skipped": {"rebuild_fault": 1}}
    assert counts(tally)[ID_CMB] == (0, 0, 0)
    assert "domain combat walked=0 skipped=1 rebuild_fault=1" in rc.render(tally)
    assert tally.domains["card"]["walked"] == 1 and tally.domains["identity"]["walked"] == 1


# -- the connection's startup parameters ------------------------------------------------------

def test_the_connection_is_read_only_from_its_startup_parameters():
    s = rc.server_settings(41)
    ms = str((41 + rc.CANCEL_SLACK_S) * 1000)
    assert s == {"default_transaction_read_only": "on",
                 "default_transaction_isolation": "repeatable read",
                 "statement_timeout": ms, "idle_in_transaction_session_timeout": ms,
                 "jit": "off"}


def test_an_address_with_options_is_refused_before_any_connection():
    with pytest.raises(rc.ConfigRefused):
        rc.session_factory(5, url="postgresql+asyncpg://calib@127.0.0.1:1/calib?sslmode=disable")


def test_the_outer_bound_leaves_room_for_the_tools_own_slack():
    """[9]: the server verb's limit (deadline + VERB_SLACK_S, then a kill
    VERB_KILL_AFTER_S later) is later than the tool's own latest end
    (deadline + CANCEL_SLACK_S + CLOSE_SLACK_S), and the contract text names
    both."""
    assert rc.VERB_SLACK_S > rc.CANCEL_SLACK_S + rc.CLOSE_SLACK_S and rc.VERB_KILL_AFTER_S > 0
    doc = rc.__doc__
    for name in ("VERB_SLACK_S", "VERB_KILL_AFTER_S", "CANCEL_SLACK_S", "timeout -s TERM -k"):
        assert name in doc, name


# -- the bounded run ------------------------------------------------------------------------

CUT_HEAD = ("run cut (deadline): games read 4 of 10 (card 4 of 5, identity 0 of 3, combat 0 of 2); "
            "card windows evaluated 0 of none rebuilt; every count below covers only what was read")


def _reads_as_whole(line):
    return line.startswith(("run whole", "rule ", "domain ", "game and sitting"))


def test_a_run_its_deadline_ends_says_it_was_cut_and_no_count_reads_as_whole(planted):
    _path, rs = planted
    fetch = FakeFetch(planted_items())
    tally = run(rc.walk(rs, fetch, deadline_at=4, clock=lambda: fetch.now))
    assert tally.cut == "deadline" and fetch.closed == ["card"]
    assert tally.domains["card"] == {"walked": 3, "skipped": {"nomatch": 1}}
    assert tally.domains["identity"]["walked"] == tally.domains["combat"]["walked"] == 0
    lines = rc.render(tally)
    assert lines[0] == CUT_HEAD
    assert len(lines) == 1 + len(tally.rules) + len(rc.DOMAINS) + 1 + 1
    assert all(line.startswith("cut ") for line in _middle(lines)) and _tail(lines) == "report end"
    assert not any(_reads_as_whole(line) for line in lines)
    assert "cut rule %s scope=card evaluated=3 fired=1 errors=0" % ID_DUP in lines
    assert "cut domain card walked=3 windows=0 skipped=1 nomatch=1" in lines


def test_a_run_its_deadline_does_not_reach_reads_every_game_and_says_whole(planted):
    """Control of the cut test: the same walk with a deadline it never reaches."""
    _path, rs = planted
    fetch = FakeFetch(planted_items())
    tally = run(rc.walk(rs, fetch, deadline_at=10 ** 6, clock=lambda: fetch.now))
    lines = rc.render(tally)
    assert tally.cut is None and fetch.closed == list(rc.DOMAINS)
    assert lines[0] == ("run whole: games read 10 of 10 (card 5 of 5, identity 3 of 3, "
                        "combat 2 of 2)")
    assert not any(line.startswith("cut") for line in lines)


def test_a_deadline_inside_the_card_windows_cuts_them_and_says_how_many_were_evaluated(planted):
    """The rebuild reads the clock six times (two classes, four end days),
    then the evaluation once per window: the deadline passes at the third
    window."""
    _path, rs = planted
    tally = rc.Tally(rs)
    for _kind, payload in window_items()["card"]:
        tally.game("card", payload)
    ticks = iter([0] * 6 + [0, 0, 1, 1, 1])
    tally.finish(deadline_at=1, clock=lambda: next(ticks))
    assert (tally.windows, tally.windows_total, tally.cut) == (2, 4, "deadline")
    assert counts(tally)[ID_WIN][0] == 2
    lines = rc.render(tally)
    assert "card windows evaluated 2 of 4" in lines[0] and lines[0].startswith("run cut (deadline)")
    assert all(line.startswith("cut ") for line in _middle(lines)) and _tail(lines) == "report end"


def test_a_deadline_inside_the_window_rebuild_says_none_rebuilt(planted):
    _path, rs = planted
    tally = rc.Tally(rs)
    for _kind, payload in window_items()["card"]:
        tally.game("card", payload)
    ticks = iter([0, 0, 1, 1, 1])
    tally.finish(deadline_at=1, clock=lambda: next(ticks))
    assert (tally.windows, tally.windows_total, tally.cut) == (0, None, "deadline")
    assert "card windows evaluated 0 of none rebuilt" in rc.render(tally)[0]


def test_a_stop_signal_ends_the_walk_after_the_game_in_hand_and_the_run_says_so(
        planted, monkeypatch):
    _path, rs = planted
    monkeypatch.setitem(rc._STOP, "word", None)
    fetch = FakeFetch(planted_items(),
                      before=lambda n: n == 2 and rc._on_term(signal.SIGTERM, None))
    tally = run(rc.walk(rs, fetch))
    lines = rc.render(tally)
    assert tally.cut == "stopped" and fetch.closed == ["card"]
    assert lines[0].startswith("run cut (stopped): games read 2 of 10 (card 2 of 5, identity 0 of 3")
    assert all(line.startswith("cut ") for line in _middle(lines)) and _tail(lines) == "report end"
    assert not any(_reads_as_whole(line) for line in lines)


class _StandInEngine:
    def __init__(self, slow):
        self.slow = slow
        self.disposed = 0

    async def dispose(self):
        self.disposed += 1
        if self.slow:
            await asyncio.sleep(3600)


def _cancel_all(loop):
    for t in asyncio.all_tasks(loop):
        t.cancel()


class SlowSession:
    """A statement that never answers (asyncio.sleep(3600)); with `swallow`,
    it swallows every cancellation and keeps sleeping. Its first statement
    arms a guard that cancels every task of the loop `guard_s` later, so a
    run whose own bound is gone ends red instead of hanging the suite."""

    def __init__(self, swallow, guard_s):
        self.swallow = swallow
        self.guard_s = guard_s
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def rollback(self):
        pass

    async def execute(self, stmt, params=None):
        self.calls += 1
        if self.calls == 1:
            loop = asyncio.get_running_loop()
            loop.call_later(self.guard_s, _cancel_all, loop)
        while True:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                if not self.swallow:
                    raise


@pytest.mark.parametrize("swallow", [False, True], ids=["cancellable", "swallows-cancel"])
def test_a_slow_statement_ends_the_run_at_the_deadline_plus_the_named_slack(
        rooted, monkeypatch, capfd, swallow):
    """[9]: --deadline-s 1 over a statement that never answers. main()
    returns 0 within 1 + CANCEL_SLACK_S + 1 seconds (the task is cancelled
    at the deadline); a statement that swallows the cancellation is
    abandoned after CANCEL_SLACK_S and the engine's disposal is cut after
    CLOSE_SLACK_S, so main() returns within 1 + CANCEL_SLACK_S +
    CLOSE_SLACK_S + 1. Either way the first count line says `run cut
    (deadline)` and the last is `report end`."""
    path, rs = rooted
    bound = 1 + rc.CANCEL_SLACK_S + (rc.CLOSE_SLACK_S if swallow else 0) + 1
    eng = _StandInEngine(slow=swallow)
    sess = SlowSession(swallow, guard_s=bound + 2)
    monkeypatch.setattr(rc, "session_factory", lambda d, **k: (eng, lambda: sess))
    capfd.readouterr()
    t0 = time.monotonic()
    code = call_main(["--revision", path, "--days", "5", "--deadline-s", "1"])
    elapsed = time.monotonic() - t0
    got = capfd.readouterr()
    lines = got.out.splitlines()
    assert code == 0, got.out
    assert elapsed <= bound, elapsed
    assert sess.calls >= 1                   # the stand-in statement was in flight
    assert lines[0] == "revision %s days 5 deadline_s 1" % rs.rev
    assert lines[1].startswith("run cut (deadline): ")
    assert _tail(lines) == "report end"
    assert got.err == ""
    assert eng.disposed == 1


# -- the arguments, the paths, the failures: one fixed line each ([1], [4]) ---------------------

TOKEN = "QZ7T0KEN"
GOOD_AT = "2026-03-05T10:20:30Z"
GOOD_DIGEST = "ab" * 32
GOOD_REV = "7e5ca0c0ffee"
HEX_TOKEN = "7a3f19c0" * 8              # a valid digest, planted as a token
HEX_REV = "0123456789ab"


def _check_argv(rev=GOOD_REV, at=GOOD_AT, digest=GOOD_DIGEST, days="5"):
    return ["--cohort-check", "--rev", rev, "--at", at, "--digest", digest, "--days", days]


def _arg(argv, token):
    def build(ctx):
        return {"argv": argv, "tokens": [token]}
    return build


ARG_ROWS = [
    ("unknown-option", "arguments", _arg(["--cohort", "--days", "5", "--" + TOKEN], TOKEN)),
    ("missing-value", "arguments", _arg(["--revision", "/x/" + TOKEN, "--days"], TOKEN)),
    ("repeated-option", "arguments", _arg(["--cohort", "--days", "5", "--days", TOKEN], TOKEN)),
    ("repeated-flag", "arguments", _arg(["--cohort", "--days", "5", "--cohort", TOKEN], TOKEN)),
    ("no-mode", "arguments", _arg(["--days", "5", "--deadline-s", TOKEN], TOKEN)),
    ("two-modes", "arguments", _arg(["--cohort", "--revision", TOKEN, "--days", "5"], TOKEN)),
    ("foreign-option", "arguments", _arg(["--cohort", "--days", "5", "--rev", TOKEN], TOKEN)),
    ("check-foreign-option", "arguments", _arg(_check_argv() + ["--revision", TOKEN], TOKEN)),
    ("equals-form", "arguments", _arg(["--cohort", "--days=" + TOKEN], TOKEN)),
    ("positional", "arguments", _arg([TOKEN, "--cohort", "--days", "5"], TOKEN)),
    ("days-text", "days", _arg(["--cohort", "--days", TOKEN], TOKEN)),
    ("days-zero", "days", _arg(["--cohort", "--days", "00000"], "00000")),
    ("days-over", "days", _arg(["--cohort", "--days", "97531"], "97531")),
    ("days-six-digits", "days", _arg(["--cohort", "--days", "123456"], "123456")),
    ("days-negative", "days", _arg(["--cohort", "--days", "-" + TOKEN], TOKEN)),
    ("days-other-digits", "days", _arg(["--cohort", "--days", "\u0663\u0663"], "\u0663\u0663")),
    ("deadline-text", "deadline", _arg(["--cohort", "--days", "5", "--deadline-s", TOKEN], TOKEN)),
    ("deadline-zero", "deadline", _arg(["--cohort", "--days", "5", "--deadline-s", "00000"],
                                       "00000")),
    ("deadline-over", "deadline", _arg(["--cohort", "--days", "5", "--deadline-s", "97531"],
                                       "97531")),
    ("rev-text", "rev", _arg(_check_argv(rev=TOKEN), TOKEN)),
    ("rev-upper", "rev", _arg(_check_argv(rev="7E5CA0C0FFEE"), "7E5CA0C0FFEE")),
    ("at-text", "at", _arg(_check_argv(at="2026-03-05T" + TOKEN), TOKEN)),
    ("at-no-such-day", "at", _arg(_check_argv(at="2026-02-30T19:53:19Z"),
                                  "2026-02-30T19:53:19Z")),
    ("digest-text", "digest", _arg(_check_argv(digest=TOKEN + "a" * 56), TOKEN)),
    ("digest-upper", "digest", _arg(_check_argv(digest="AB" * 32), "AB" * 32)),
]


def _root(ctx):
    root = os.path.join(str(ctx.tmp), "root" + TOKEN)
    os.makedirs(root, exist_ok=True)
    ctx.mp.setenv(rr.ROOT_ENV, root)
    return root


def make_link(target, link):
    """A directory link: a symbolic link, or (Windows without the privilege)
    a directory junction. Returns which."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError):
        try:
            import _winapi
        except ImportError:
            pytest.skip("this OS made neither a symbolic link nor a junction")
        _winapi.CreateJunction(target, link)
        return "junction"


def _path_row(make):
    def build(ctx):
        root = _root(ctx)
        return {"argv": ["--revision", make(ctx, root), "--days", "5"], "tokens": [TOKEN]}
    return build


def _p_outside(ctx, root):
    return os.path.join(str(ctx.tmp), "elsewhere" + TOKEN, "rules-" + ctx.rev)


def _p_sibling(ctx, root):
    return root + "x" + os.sep + "rules-" + ctx.rev


def _p_pointer(ctx, root):
    return os.path.join(root, rr.POINTER)


def _p_through_pointer(ctx, root):
    make_link(os.path.dirname(ctx.path), os.path.join(root, rr.POINTER))
    arg = os.path.join(root, rr.POINTER, "rules-" + ctx.rev)
    assert os.path.isdir(arg)                # control: following it reaches a whole revision
    return arg


def _p_none(ctx, root):
    return os.path.join(root, rr.NONE_TARGET)


def _p_extra(ctx, root):
    return os.path.join(root, "rules-" + ctx.rev, "extra")


def _p_bad_name(ctx, root):
    return os.path.join(root, "rules-" + TOKEN.lower())


def _p_empty(ctx, root):
    return root + os.sep


def _p_missing(ctx, root):
    return os.path.join(root, "rules-" + HEX_REV)


def _p_file(ctx, root):
    p = os.path.join(root, "rules-" + HEX_REV)
    with open(p, "w", encoding="ascii") as f:
        f.write(TOKEN)
    return p


def _p_link(ctx, root):
    link = os.path.join(root, "rules-" + ctx.rev)
    make_link(ctx.path, link)
    return link


PATH_ROWS = [
    ("path-outside-root", "root", _path_row(_p_outside)),
    ("path-root-sibling", "root", _path_row(_p_sibling)),
    ("path-pointer", "pointer", _path_row(_p_pointer)),
    ("path-through-pointer", "pointer", _path_row(_p_through_pointer)),
    ("path-none-target", "pointer", _path_row(_p_none)),
    ("path-extra-component", "name", _path_row(_p_extra)),
    ("path-bad-name", "name", _path_row(_p_bad_name)),
    ("path-empty-component", "name", _path_row(_p_empty)),
    ("path-missing", "missing", _path_row(_p_missing)),
    ("path-not-a-directory", "missing", _path_row(_p_file)),
    ("path-link", "link", _path_row(_p_link)),
]


def _loader_row(cls):
    def build(ctx):
        root = _root(ctx)
        d = os.path.join(root, "rules-" + HEX_REV)
        os.makedirs(d)

        def refuse(path, **_k):
            raise rr.Refused(cls, "planted " + TOKEN + " " + path)
        ctx.mp.setattr(rc.rr, "load_dir", refuse)
        return {"argv": ["--revision", d, "--days", "5"], "tokens": [TOKEN],
                "code": rc.EXIT_REFUSED}
    return build


def _loader_real(ctx):
    root = _root(ctx)
    d = os.path.join(root, "rules-" + HEX_REV)
    os.makedirs(d)
    with open(os.path.join(d, "rules.json"), "w", encoding="utf-8") as f:
        f.write('{"%s": 1}' % TOKEN)
    return {"argv": ["--revision", d, "--days", "5"], "tokens": [TOKEN], "code": rc.EXIT_REFUSED,
            "out": ["refused (inventory)"]}


LOADER_ROWS = [
    ("loader-class", "class", _loader_row("inventory")),
    ("loader-real", "class", _loader_real),
    ("loader-unreadable-class", "revision", _loader_row(TOKEN + " Bad")),
]
LOADER_LINES = {"loader-class": ["refused (inventory)"],
                "loader-unreadable-class": ["refused (revision)"]}


def _cohort_members():
    m = ("cohortkey" + TOKEN, "70000000-0000-0000-0000-0000000c0h01",
         "70000000-0000-0000-0000-0000000c0h02", False, None, False)
    return {"card": [m], "identity": [], "combat": []}


def _cohort_differs(ctx):
    async def fake(days, deadline_at=None, at=None):
        return GOOD_AT, _cohort_members()
    ctx.mp.setattr(rc, "_run_cohort", fake)
    return {"argv": _check_argv(digest=HEX_TOKEN), "tokens": [TOKEN, HEX_TOKEN, "c0h0"],
            "code": rc.EXIT_REFUSED, "out": ["refused (cohort differs)"]}


def _cohort_cut(mode):
    def build(ctx):
        async def fake(days, deadline_at=None, at=None):
            return None
        ctx.mp.setattr(rc, "_run_cohort", fake)
        argv = _check_argv(digest=HEX_TOKEN) if mode == "check" else ["--cohort", "--days", "5"]
        return {"argv": argv, "tokens": [HEX_TOKEN], "code": rc.EXIT_REFUSED,
                "out": ["cohort cut (deadline): nothing counted", "report end"]}
    return build


COHORT_ROWS = [
    ("cohort-differs", "cohort differs", _cohort_differs),
    ("cohort-cut-check", "cohort cut", _cohort_cut("check")),
    ("cohort-cut-cohort", "cohort cut", _cohort_cut("cohort")),
]


def _failures():
    import asyncpg
    from sqlalchemy.exc import OperationalError
    return {
        "interrupted": KeyboardInterrupt(TOKEN),
        "exit": SystemExit(TOKEN),
        "memory": MemoryError(TOKEN),
        "timeout": TimeoutError(TOKEN),
        "config": rc.ConfigRefused(TOKEN),
        "driver": rc.DriverRefused(TOKEN),
        "database": OperationalError("SELECT '%s'" % TOKEN, {"p": TOKEN}, Exception(TOKEN)),
        "database-driver": asyncpg.PostgresError(TOKEN),
        "system": OSError(13, TOKEN, "C:/" + TOKEN),
        "internal": ValueError(TOKEN),
        "internal-cancelled": asyncio.CancelledError(TOKEN),
    }


def _failure_row(name, mode="cohort"):
    def build(ctx):
        exc = _failures()[name]

        def factory(*_a, **_k):
            raise exc
        ctx.mp.setattr(rc, "session_factory", factory)
        word = name.split("-")[0]
        if mode == "count":
            ctx.mp.setenv(rr.ROOT_ENV, os.path.dirname(ctx.path))
            return {"argv": ["--revision", ctx.path, "--days", "5"], "tokens": [TOKEN],
                    "code": rc.EXIT_FAILED,
                    "out": ["revision %s days 5 deadline_s %d" % (ctx.rev, rc.DEFAULT_DEADLINE_S),
                            "failed (%s)" % word]}
        return {"argv": ["--cohort", "--days", "5"], "tokens": [TOKEN], "code": rc.EXIT_FAILED,
                "out": ["failed (%s)" % word]}
    return build


def _failure_real_address(word, address):
    def build(ctx):
        real = REAL_SESSION_FACTORY
        ctx.mp.setattr(rc, "session_factory", lambda d, **k: real(d, url=address))
        return {"argv": ["--cohort", "--days", "5"], "tokens": [TOKEN, "127.0.0.1"],
                "code": rc.EXIT_FAILED, "out": ["failed (%s)" % word]}
    return build


FAILURE_ROWS = [("failure-" + n, n.split("-")[0], _failure_row(n)) for n in (
    "interrupted", "exit", "memory", "timeout", "config", "driver", "database", "database-driver",
    "system", "internal", "internal-cancelled")]
FAILURE_ROWS += [
    ("failure-count-mode", "database", _failure_row("database", mode="count")),
    ("failure-real-config", "config", _failure_real_address(
        "config", "postgresql+asyncpg://calib:%s@127.0.0.1:1/%s?sslmode=%s" % (TOKEN, TOKEN, TOKEN))),
    ("failure-real-system", "system", _failure_real_address(
        "system", "postgresql+asyncpg://calib:%s@127.0.0.1:1/%s" % (TOKEN, TOKEN))),
]


def _process(argv, isolated, out, code):
    def build(ctx):
        cmd = [sys.executable, "-B"] + (["-I"] if isolated else []) + [rc.__file__] + argv
        return {"cmd": cmd, "tokens": [TOKEN], "code": code, "out": out}
    return build


PROCESS_ROWS = [
    ("process-import", "import", _process(["--" + TOKEN], True, ["failed (import)"], rc.EXIT_FAILED)),
    ("process-refusal", "days", _process(["--cohort", "--days", TOKEN], False,
                                         ["refused (days)"], rc.EXIT_USAGE)),
]

TABLE = ([("arg",) + r for r in ARG_ROWS] + [("path",) + r for r in PATH_ROWS]
         + [("loader",) + r for r in LOADER_ROWS] + [("cohort",) + r for r in COHORT_ROWS]
         + [("failure",) + r for r in FAILURE_ROWS]
         + [("import" if r[1] == "import" else "arg",) + r for r in PROCESS_ROWS])


def _expected(kind, rid, word, case):
    if "out" in case:
        return case["out"], case.get("code", rc.EXIT_USAGE)
    if kind == "arg":
        return ["refused (%s)" % word], rc.EXIT_USAGE
    if kind == "path":
        return ["refused (path %s)" % word], rc.EXIT_USAGE
    if kind == "loader":
        return LOADER_LINES[rid], rc.EXIT_REFUSED
    raise AssertionError("no expectation for row " + rid)


@pytest.mark.parametrize("row", TABLE, ids=[r[1] for r in TABLE])
def test_every_refusal_and_failure_prints_one_fixed_line_and_nothing_else(
        row, planted, tmp_path, monkeypatch, capfd):
    """[1]: each refusal and failure path. The exact stdout, the exit code,
    an empty stderr, and the token planted in the rejected value or the
    exception text in neither stream."""
    kind, rid, word, build = row
    path, rs = planted

    def no_database(*_a, **_k):
        raise AssertionError("this row reaches no database")
    monkeypatch.setattr(rc, "session_factory", no_database)
    ctx = types.SimpleNamespace(tmp=tmp_path, mp=monkeypatch, path=path, rev=rs.rev)
    case = build(ctx)
    want, want_code = _expected(kind, rid, word, case)
    if "cmd" in case:
        p = subprocess.run(case["cmd"], cwd=str(tmp_path), capture_output=True, text=True,
                           timeout=300)
        code, out, err = p.returncode, p.stdout, p.stderr
    else:
        capfd.readouterr()
        code = call_main(case["argv"])
        got = capfd.readouterr()
        out, err = got.out, got.err
    assert out.splitlines() == want and out.endswith("\n")
    assert code == want_code
    assert err == ""
    for tok in case["tokens"]:
        assert tok not in out and tok not in err, tok


def test_the_table_has_a_row_for_every_refusal_and_failure_word():
    """The census of the table: its words are exactly the module's fixed
    words, and every refusal and failure word the module's source can print
    has a row."""
    by = {}
    for kind, _rid, word, _b in TABLE:
        by.setdefault(kind, set()).add(word)
    assert set(by) == {"arg", "path", "loader", "cohort", "failure", "import"}
    assert by["arg"] == set(rc.ARG_WORDS)
    assert by["path"] == set(rc.PATH_WORDS)
    assert by["failure"] == set(rc.FAILURE_WORDS)
    assert by["loader"] == {"class", "revision"}
    assert by["cohort"] == {"cohort differs", "cohort cut"}
    assert by["import"] == {"import"}
    src = open(rc.__file__, encoding="utf-8").read()
    refuse = set(re.findall(r'_refuse\("([^"]*)"\)', src))
    assert refuse and refuse <= by["arg"]
    path_words = set(re.findall(r'PathRefused\("([^"]*)"\)', src))
    assert path_words and path_words <= by["path"]
    returned = set(re.findall(r'return "([^"]*)"', inspect.getsource(rc.failure_word)))
    assert returned and returned <= by["failure"]
    assert set(re.findall(r'"refused \(([^)%]*)\)"', src)) <= by["cohort"]
    failed = set(re.findall(r'"failed \(([^)%]*)\)', src))
    assert failed and failed <= by["import"]
    assert '"cohort cut (' in src
    # every Refused line form is one the table covers
    assert set(re.findall(r'Refused\("(refused \([^"]*\))"', src)) == {"refused (%s)",
                                                                     "refused (path %s)"}
    assert "argparse" not in src


# -- the pointer is never followed ([4]) --------------------------------------------------------

def _record_lookups(mp, seen):
    """Every filesystem lookup by path, recorded (name, path) and passed on.
    Returns the (module, name) pairs replaced."""
    done = []

    def wrap(mod, name):
        orig = getattr(mod, name, None)
        if orig is None:
            return

        def f(*a, **k):
            seen.append((name, a[0] if a else k.get("path", k.get("file"))))
            return orig(*a, **k)
        mp.setattr(mod, name, f)
        done.append((mod, name))
    for name in _OS_LOOKUPS:
        wrap(os, name)
    for name in _PATH_LOOKUPS:
        wrap(os.path, name)
    wrap(builtins, "open")
    return done


_OS_LOOKUPS = ("lstat", "stat", "listdir", "scandir", "readlink", "open", "access")
_PATH_LOOKUPS = ("exists", "lexists", "isdir", "isfile", "islink", "isjunction", "realpath")


@contextlib.contextmanager
def recording_lookups(seen):
    """The recorder installed for the block. The suite's review tripwire
    (tools/review_tripwire.py) sees each replaced binding of a query it
    guards; this block declares exactly those names as expected, so they are
    consumed here and nothing else is."""
    planned = [(os, n) for n in _OS_LOOKUPS] + [(os.path, n) for n in _PATH_LOOKUPS]
    replaced = [n for n, owner, attr in review_tripwire.GUARDS
                if any(owner is m and attr == a for m, a in planned)]
    with review_tripwire.expected_trip(*replaced):
        with pytest.MonkeyPatch.context() as mp:
            _record_lookups(mp, seen)
            try:
                yield
            finally:
                review_tripwire.verdict()     # the replaced bindings, recorded in this scope


def _beneath(seen, top):
    top = os.path.normcase(os.path.normpath(top))
    out = []
    for name, p in seen:
        if isinstance(p, (str, bytes, os.PathLike)):
            q = os.fsdecode(os.fspath(p))
            q = os.path.normcase(os.path.normpath(q))
            if q == top or q.startswith(top + os.sep):
                out.append((name, q))
    return out


def test_an_argument_through_the_pointer_is_refused_by_form_with_no_lookup_beneath_it(
        planted, tmp_path, monkeypatch, capsys):
    path, rs = planted
    root = os.path.join(str(tmp_path), "root" + TOKEN)
    os.makedirs(root)
    monkeypatch.setenv(rr.ROOT_ENV, root)
    pointer = os.path.join(root, rr.POINTER)
    make_link(os.path.dirname(path), pointer)
    arg = os.path.join(pointer, "rules-" + rs.rev)
    # control: following the pointer reaches the whole revision's files
    assert os.path.isfile(os.path.join(arg, "REVISION")) and os.path.isfile(os.path.join(arg, "rules.json"))
    seen = []
    with recording_lookups(seen):
        code = call_main(["--revision", arg, "--days", "5"])
    out = capsys.readouterr()
    assert code == rc.EXIT_USAGE and out.out == "refused (path pointer)\n" and out.err == ""
    assert _beneath(seen, pointer) == []
    # control of the recorder: a lookup the tool does make is seen
    missing = os.path.join(root, "rules-" + HEX_REV)
    seen2 = []
    with recording_lookups(seen2):
        code = call_main(["--revision", missing, "--days", "5"])
    assert code == rc.EXIT_USAGE and capsys.readouterr().out == "refused (path missing)\n"
    assert ("lstat", missing) in [(n, p) for n, p in seen2 if isinstance(p, str)]


@pytest.mark.parametrize("name,word", [
    ("current", "pointer"), ("rules-none", "pointer"), ("rules-0123456789a", "name"),
    ("rules-0123456789abc", "name"), ("rules-0123456789AB", "name"),
    ("rules-0123456789a\u0663", "name"), ("rules0123456789ab", "name")])
def test_a_pointer_or_a_malformed_name_is_refused_before_loading(rooted, no_db, capsys, name,
                                                                 word):
    path, _rs = rooted
    code, out = _run_main(capsys, os.path.join(os.path.dirname(path), name))
    assert code == rc.EXIT_USAGE and out == "refused (path %s)\n" % word
    assert no_db == []


def test_the_pointer_is_refused_even_naming_a_good_revision(rooted, no_db, capsys, tmp_path,
                                                            monkeypatch):
    path, _rs = rooted
    root = os.path.join(str(tmp_path), "root")
    os.makedirs(root)
    monkeypatch.setenv(rr.ROOT_ENV, root)
    with open(os.path.join(root, rr.POINTER), "w", encoding="ascii") as f:
        f.write(os.path.basename(path) + "\n")
    code, out = _run_main(capsys, os.path.join(root, rr.POINTER))
    assert code == rc.EXIT_USAGE and out == "refused (path pointer)\n" and no_db == []


def test_a_symbolic_link_or_junction_named_like_the_revision_is_refused(planted, tmp_path,
                                                                        monkeypatch, no_db, capsys):
    path, _rs = planted
    root = os.path.join(str(tmp_path), "root")
    os.makedirs(root)
    monkeypatch.setenv(rr.ROOT_ENV, root)
    link = os.path.join(root, os.path.basename(path))
    make_link(path, link)
    # control: the link names the good revision
    assert os.path.realpath(link) == os.path.realpath(path)
    code, out = _run_main(capsys, link)
    assert code == rc.EXIT_USAGE and out == "refused (path link)\n" and no_db == []


def test_a_directory_junction_is_refused(planted, tmp_path, monkeypatch, no_db, capsys):
    """The Windows form of a directory link (where creating a symbolic link
    needs a privilege a test seat may not hold)."""
    try:
        import _winapi
    except ImportError:
        pytest.skip("directory junctions exist only on Windows")
    path, _rs = planted
    root = os.path.join(str(tmp_path), "root")
    os.makedirs(root)
    monkeypatch.setenv(rr.ROOT_ENV, root)
    link = os.path.join(root, os.path.basename(path))
    _winapi.CreateJunction(path, link)
    assert os.path.realpath(link) == os.path.realpath(path)    # control: names the revision
    code, out = _run_main(capsys, link)
    assert code == rc.EXIT_USAGE and out == "refused (path link)\n" and no_db == []


# -- main() with a stub walk ----------------------------------------------------------------

class _Seen(list):
    """The revisions main() walked, plus what each walk was handed."""


@pytest.fixture
def no_db(monkeypatch):
    """main() stops before any database: the walk is a stub."""
    seen = _Seen()
    seen.calls = []

    async def fake_run(rs, days, deadline_at=None):
        seen.append(rs.rev)
        seen.calls.append({"days": days, "deadline_at": deadline_at,
                           "handler": signal.getsignal(signal.SIGTERM)})
        return rc.Tally(rs).finish()
    monkeypatch.setattr(rc, "_run", fake_run)
    return seen


def _run_main(capsys, path, days="23"):
    code = call_main(["--revision", path, "--days", days])
    return code, capsys.readouterr().out


def test_the_named_revision_loads_and_reports(rooted, no_db, capsys):
    path, rs = rooted
    code, out = _run_main(capsys, path)
    assert code == 0 and no_db == [rs.rev]
    assert "rule %s scope=card evaluated=0 fired=0 errors=0" % ID_DUP in out
    assert _tail(out.splitlines()) == "report end"


def test_days_out_of_range_are_refused(rooted, no_db, capsys):
    path, _rs = rooted
    for days in ("0", "-3", str(cm.WINDOW_DAYS_MAX + 1)):
        code, out = _run_main(capsys, path, days)
        assert code == rc.EXIT_USAGE and out == "refused (days)\n"
    assert no_db == []


def test_the_deadline_has_a_stated_default_a_bound_and_reaches_the_walk(rooted, no_db, capsys):
    path, rs = rooted
    t0 = time.monotonic()
    code, out = _run_main(capsys, path)
    t1 = time.monotonic()
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "revision %s days 23 deadline_s %d" % (rs.rev, rc.DEFAULT_DEADLINE_S)
    assert lines[1].startswith("run whole: ")
    got = no_db.calls[0]["deadline_at"]
    assert t0 + rc.DEFAULT_DEADLINE_S <= got <= t1 + rc.DEFAULT_DEADLINE_S
    t0 = time.monotonic()
    code = call_main(["--revision", path, "--days", "23", "--deadline-s", "77"])
    t1 = time.monotonic()
    assert code == 0 and "deadline_s 77" in capsys.readouterr().out
    assert t0 + 77 <= no_db.calls[1]["deadline_at"] <= t1 + 77
    for bad in ("0", "-5", str(rc.DEADLINE_MAX_S + 1)):
        code = call_main(["--revision", path, "--days", "23", "--deadline-s", bad])
        assert code == rc.EXIT_USAGE and capsys.readouterr().out == "refused (deadline)\n"
    assert len(no_db) == 2


def test_main_holds_the_stop_handler_only_while_it_walks(rooted, no_db, capsys):
    path, _rs = rooted
    before = signal.getsignal(signal.SIGTERM)
    code, _out = _run_main(capsys, path)
    assert code == 0 and no_db.calls[0]["handler"] is rc._on_term
    assert signal.getsignal(signal.SIGTERM) is before and rc._STOP["word"] is None


# -- the cohort (unit) ([13], design section g) ------------------------------------------------

CK = ("cohortkeyQ7ZA", "70000000-0000-0000-0000-0000000c0e01", "70000000-0000-0000-0000-0000000c0e02")
CK2 = ("cohortkeyQ7ZB", "70000000-0000-0000-0000-0000000c0e01", "70000000-0000-0000-0000-0000000c0e02")
CK3 = ("cohortkeyQ7ZC", "70000000-0000-0000-0000-0000000c0e03", "70000000-0000-0000-0000-0000000c0e04")


def _m(k, purged=False, rev=None, failed=False):
    return k + (purged, rev, failed)


def test_the_cohort_digest_is_order_independent_state_independent_and_domain_sensitive():
    a = {"card": [_m(CK), _m(CK2)], "identity": [_m(CK3)], "combat": []}
    b = {"card": [_m(CK2), _m(CK)], "identity": [_m(CK3)], "combat": []}
    assert rc.cohort_digest(a) == rc.cohort_digest(b)
    # the members' states (purged now, evaluated revision, fault) are not hashed
    c = {"card": [_m(CK, purged=True), _m(CK2, rev=GOOD_REV)], "identity": [_m(CK3, failed=True)],
         "combat": []}
    assert rc.cohort_digest(c) == rc.cohort_digest(a)
    # the same member in another domain is another cohort
    d = {"card": [_m(CK), _m(CK2)], "identity": [], "combat": [_m(CK3)]}
    assert rc.cohort_digest(d) != rc.cohort_digest(a)
    # one member fewer or another member is another cohort
    assert rc.cohort_digest({"card": [_m(CK)], "identity": [_m(CK3)], "combat": []}) \
        != rc.cohort_digest(a)
    assert re.fullmatch(r"[0-9a-f]{64}", rc.cohort_digest(a))
    assert rc.cohort_digest({d_: [] for d_ in rc.DOMAINS}) == hashlib.sha256(b"").hexdigest()


def test_a_members_state_is_purged_then_evaluated_then_failed_then_waiting():
    assert rc.classify(_m(CK, purged=True, rev=GOOD_REV, failed=True), GOOD_REV) == "purged"
    assert rc.classify(_m(CK, rev=GOOD_REV, failed=True), GOOD_REV) == "evaluated"
    assert rc.classify(_m(CK, rev="0" * 12, failed=True), GOOD_REV) == "failed"
    assert rc.classify(_m(CK, rev="0" * 12), GOOD_REV) == "waiting"
    assert rc.classify(_m(CK), GOOD_REV) == "waiting"
    assert rc.classify(_m(CK, rev=None), None) == "waiting"


def test_the_cohort_read_binds_t_as_an_instant_and_returns_its_text():
    """The driver refuses a text value for a timestamptz parameter, so T is
    bound as the aware UTC instant its text names; the text is what is
    printed."""
    seen = []

    class Db:
        async def execute(self, stmt, b=None):
            seen.append(b)
            return FakeResult([])
    at, members = run(rc.read_cohort(Db(), 29, GOOD_AT))
    assert at == GOOD_AT and members == {d: [] for d in rc.DOMAINS}
    assert [b["at"] for b in seen] == [datetime(2026, 3, 5, 10, 20, 30, tzinfo=timezone.utc)] * 3
    assert all(b["days"] == 29 for b in seen)


def test_the_cohort_report_lines_are_fixed_and_name_no_member():
    members = {"card": [_m(CK), _m(CK2, purged=True)], "identity": [_m(CK3, rev=GOOD_REV)],
               "combat": [_m(CK3, failed=True)]}
    dig = rc.cohort_digest(members)
    lines = rc.render_cohort(GOOD_AT, 29, members)
    assert lines == ["cohort at %s days 29: members 4 (card 2, identity 1, combat 1) digest %s"
                     % (GOOD_AT, dig), "report end"]
    check = rc.render_check(GOOD_REV, GOOD_AT, members)
    assert check == [
        "cohort check rev %s at %s: members 4; evaluated 1; waiting 1; purged 1; failed 1; "
        "complete no" % (GOOD_REV, GOOD_AT),
        "cohort card members 2 evaluated 0 waiting 1 purged 1 failed 0",
        "cohort identity members 1 evaluated 1 waiting 0 purged 0 failed 0",
        "cohort combat members 1 evaluated 0 waiting 0 purged 0 failed 1",
        "report end"]
    done = {"card": [_m(CK2, purged=True)], "identity": [_m(CK3, rev=GOOD_REV)], "combat": []}
    assert rc.render_check(GOOD_REV, GOOD_AT, done)[0].endswith("complete yes")
    out = "\n".join(lines + check)
    for part in CK + CK2 + CK3 + ("Q7Z", "c0e0"):
        assert part not in out, part


# -- the database (live) ----------------------------------------------------------------------
#
# ONE planting, in one case schema (one pair of synthetic players):
#   card     C1  one record, recent canonical match                      -> walked
#            C6  [6] two records naming two matches of the pair: the OLD
#                one (outside the walk's days) is canonical, the other
#                recent                                                  -> outside
#            C7  [7] an attached retained record and a stray record
#                (another attach key, no match) whose lists are purged   -> walked
#            KE KW KP KF  cohort-only games (canonical match 20 days old,
#                outside the walk): a games row evaluated under COH_REV,
#                none, purged after T, a derive fault
#   identity I1  one record with a clock sample, recent match            -> walked
#   combat   B1  the a24 pair of records, recent match                   -> walked

ST_A, ST_B = "1000000000007301", "1000000000007302"
WALK_DAYS = 9
COH_DAYS = 29
COH_REV = "7e5ca0c0ffee"
LK = {n: "calibr2_%s_q7z" % n for n in ("c1", "c6", "c7", "i1", "b1", "ke", "kw", "kp", "kf")}
LR = {n: "calibroom_r2_%s_q7z" % n for n in ("c1", "c6old", "c6new", "c7", "c7stray", "i1", "b1",
                                             "ke", "kw", "kp", "kf")}


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


async def _plant(sm):
    import main
    import test_title_ladder_hooks_live as lh
    async with sm() as db:
        a = (await main.get_or_create_player(db, ST_A, "Calib 301")).id
        b = (await main.get_or_create_player(db, ST_B, "Calib 302")).id
        await db.commit()
    dump = full_game_dump()
    async with sm() as db:
        await ce.register_census(db, dump)
    card_rec = json.dumps(kit.on_census(kit.fixture_record("full_game"), cm.census_from_dump(dump)))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    recent, rx = now - timedelta(hours=2), now - timedelta(hours=1)
    old, cohort_end = now - timedelta(days=15), now - timedelta(days=20)
    lo, hi = sorted([a, b])
    async with sm() as db:
        async def match(room, ended):
            row = await lh._insert(db, "matches", {
                "player1_id": a, "player2_id": b, "photon_room_id": room, "is_ranked": True,
                "p1_rounds_won": 5, "p2_rounds_won": 3, "winner_id": a, "reported_by": a})
            await db.execute(text("UPDATE matches SET ended_at = :e, created_at = :e WHERE id = :i"),
                             {"e": ended, "i": row["id"]})

        async def card(key, room, seat, other, purged=None):
            await db.execute(text(
                "INSERT INTO card_evidence (stable_game_key, attach_key, seat_player_id, "
                "  other_player_id, pool_digest, deal_profile, payload, payload_sha256, "
                "  received_at, lists_purged_at) "
                "VALUES (:k, :a, :s, :o, :d, :dp, CAST(:p AS jsonb), :h, :r, :lp)"),
                {"k": key, "a": room, "s": seat, "o": other, "d": dump["digest"], "dp": PROFILE,
                 "p": card_rec, "h": _sha(card_rec), "r": rx, "lp": purged})

        for room, ended in (("c1", recent), ("c6old", old), ("c6new", recent), ("c7", recent),
                            ("i1", recent), ("b1", recent), ("ke", cohort_end), ("kw", cohort_end),
                            ("kp", cohort_end), ("kf", cohort_end)):
            await match(LR[room], ended)
        await card(LK["c1"], LR["c1"], a, b)
        await card(LK["c6"], LR["c6old"], a, b)
        await card(LK["c6"], LR["c6new"], b, a)
        await card(LK["c7"], LR["c7"], a, b)
        await card(LK["c7"], LR["c7stray"], b, a, purged=now - timedelta(hours=1))
        for n in ("ke", "kw", "kp", "kf"):
            await card(LK[n], LR[n], a, b)
        await db.execute(text(
            "INSERT INTO card_games (stable_game_key, pair_lo, pair_hi, evaluated_rev, derive_fault) "
            "VALUES (:k, :lo, :hi, :r, NULL), (:k2, :lo, :hi, NULL, 'planted_fault')"),
            {"k": LK["ke"], "k2": LK["kf"], "lo": lo, "hi": hi, "r": COH_REV})
        ident = json.dumps(ifx.base_record())
        await db.execute(text(
            "INSERT INTO identity_clock_evidence (stable_game_key, attach_key, seat_player_id, "
            "  other_player_id, header_mod_version, payload, payload_sha256, post_clock, post_proc, "
            "  post_sw_ms, post_unity_ms, post_photon_ts, conn_class, conn_ranges, received_at) "
            "VALUES (:k, :a, :s, :o, '1.41.0', CAST(:p AS jsonb), :h, 'ok', :pp, "
            "  CAST(:sw AS bigint), CAST(:un AS bigint), CAST(:ph AS integer), 'none', 'absent', :r)"),
            {"k": LK["i1"], "a": LR["i1"], "s": a, "o": b, "p": ident, "h": _sha(ident),
             "pp": ifx.PROC_A, "sw": 5_000_000, "un": 4_000_000, "ph": 123_456, "r": rx})
        owner, meas = cfx.a24_pair()
        for seat, other, rec in ((a, b, owner), (b, a, meas)):
            p = json.dumps(rec)
            await db.execute(text(
                "INSERT INTO combat_evidence (stable_game_key, attach_key, seat_player_id, "
                "  other_player_id, payload, payload_sha256, received_at) "
                "VALUES (:k, :a, :s, :o, CAST(:p AS jsonb), :h, :r)"),
                {"k": LK["b1"], "a": LR["b1"], "s": seat, "o": other, "p": p, "h": _sha(p), "r": rx})
        await db.commit()
    return types.SimpleNamespace(a=a, b=b, ids=(str(a), str(b)))


@pytest.fixture(scope="module")
def live():
    import combat_evidence_pg as cp
    import ladder_pg_harness as harness
    import seat_evidence_pg as sp
    sp.require_live_pg()
    loop = asyncio.new_event_loop()
    cmgr = cp.case("calib")
    c, sm, _snaps = loop.run_until_complete(cmgr.__aenter__())
    try:
        plan = loop.run_until_complete(_plant(sm))
        yield types.SimpleNamespace(run=loop.run_until_complete, case=c, sm=sm, plan=plan,
                                    url=harness.async_dsn(sp.DSN),
                                    settings={"search_path": harness.quoted(c.schema)})
    finally:
        loop.run_until_complete(cmgr.__aexit__(None, None, None))
        loop.close()


@pytest.fixture(scope="module")
def walked(live, planted):
    """The tool's walk over the planting, through the tool's own connection
    with every SQL text it sends recorded."""
    _path, rs = planted
    log = []
    engine, factory = rc.session_factory(60, url=live.url, recorder=log,
                                         extra_settings=live.settings)

    async def go():
        try:
            return await rc.walk_db(rs, factory, WALK_DAYS, time.monotonic() + 120)
        finally:
            await engine.dispose()
    tally = live.run(go())
    return types.SimpleNamespace(tally=tally, log=[" ".join(s.split()) for s in log])


def test_live_the_tool_session_and_its_connection_are_read_only_from_the_start(live):
    """[5]: inside the tool's session the transaction is read only and
    repeatable read and an INSERT is refused; on a bare driver connection the
    tool opens (no transaction begun by anyone) the default is read only, so
    the driver's own statements are read only too."""
    import asyncpg
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import DBAPIError

    async def go():
        engine, factory = rc.session_factory(60, url=live.url, extra_settings=live.settings)
        try:
            async with rc.read_only(factory) as db:
                ro = (await db.execute(text("SHOW transaction_read_only"))).scalar()
                iso = (await db.execute(text("SHOW transaction_isolation"))).scalar()
            async with rc.read_only(factory) as db:
                with pytest.raises(DBAPIError) as ei:
                    await db.execute(text(
                        "INSERT INTO runtime_settings (key, value) VALUES ('calib_probe', 'v')"))
                assert "read-only transaction" in str(ei.value)
        finally:
            await engine.dispose()
        args = make_url(live.url).translate_connect_args(username="user")
        conn = await rc._connect(args, dict(rc.server_settings(60), **live.settings))
        try:
            bare = (await conn.fetchval("SHOW default_transaction_read_only"),
                    await conn.fetchval("SHOW transaction_read_only"),
                    await conn.fetchval("SHOW default_transaction_isolation"),
                    await conn.fetchval("SHOW jit"), conn._server_caps.jit)
            with pytest.raises(asyncpg.exceptions.ReadOnlySQLTransactionError):
                await conn.execute(
                    "INSERT INTO runtime_settings (key, value) VALUES ('calib_probe_bare', 'v')")
        finally:
            await conn.close()
        async with live.sm() as db:
            probes = (await db.execute(text(
                "SELECT count(*) FROM runtime_settings WHERE key LIKE 'calib_probe%'"))).scalar()
        return ro, iso, bare, probes
    ro, iso, bare, probes = live.run(go())
    assert (ro, iso) == ("on", "repeatable read")
    assert bare == ("on", "on", "repeatable read", "off", False)
    assert probes == 0


def test_live_every_statement_the_connection_sent_is_an_approved_shape(walked):
    """[5]: the recorder sits at the driver's protocol, so it lists EVERY
    statement of the connection: the dialect's first-connect reads, the
    driver's type introspection, the transaction and the tool's reads. The
    first is a BEGIN; each is an approved shape; none changes a setting."""
    log = walked.log
    assert log, "the recorder saw nothing"
    assert log[0].upper().startswith("BEGIN"), log[0][:80]
    bad = [(s[:100], shape_faults(s)) for s in log if shape_faults(s)]
    assert bad == [], bad
    for s in log:
        low = s.lower()
        assert "set_config" not in low and "current_setting" not in low, s[:100]
        assert not re.match(r"\s*set\b", low), s[:100]
    # The dialect's first-connect BEGIN names no access mode (it is read only
    # by the connection's startup default, held by the read-only test above);
    # the run's own transaction, the one the tool's first selection runs in,
    # is begun READ ONLY.
    first = next(i for i, s in enumerate(log) if s.startswith("WITH cand AS"))
    run_begin = [s for s in log[:first] if s.upper().startswith("BEGIN")][-1]
    assert "REPEATABLE READ READ ONLY" in run_begin.upper(), run_begin
    assert log[-1].upper().startswith("ROLLBACK")


SHAPES = {
    "card rows": lambda s: "FROM card_evidence WHERE stable_game_key" in s,
    "card match by id": lambda s: "LEFT JOIN ranked_series" in s and "WHERE m.id =" in s,
    "card registry": lambda s: "FROM card_pool_registry WHERE digest = ANY" in s,
    "match_cards report": lambda s: "FROM match_cards WHERE match_id" in s,
    "identity rows": lambda s: "FROM identity_clock_evidence WHERE stable_game_key" in s,
    "identity match": lambda s: s.startswith("SELECT id, player1_id, player2_id, ended_at, "
                                             "photon_room_id FROM matches WHERE id ="),
    "identity release registry": lambda s: "FROM mod_release_digests" in s,
    "identity game-file registry": lambda s: "FROM game_file_digests" in s,
    "seat views": lambda s: "FROM seat_evidence WHERE stable_game_key" in s,
    "clock fit": lambda s: "FROM identity_clock_evidence WHERE seat_player_id" in s,
    "combat rows": lambda s: "FROM combat_evidence WHERE stable_game_key" in s,
    "combat match": lambda s: s.startswith("SELECT id, photon_room_id, player1_id, player2_id, "
                                           "ended_at FROM matches WHERE id ="),
    "selection": lambda s: s.startswith("WITH cand AS"),
}


def test_live_every_per_game_statement_ran_in_all_three_domains(walked):
    """[8]: the populated walk ran every per-game statement at least once."""
    missing = [name for name, hit in SHAPES.items() if not any(hit(s) for s in walked.log)]
    assert missing == []
    assert sum(1 for s in walked.log if SHAPES["selection"](s)) == 3


async def _fake_items(rs):
    """One evaluation input per domain, read by the tool's own DbFetch from
    the RecordingSession's planted rows: the same records as the planting."""
    sess = RecordingSession()
    f = rc.DbFetch(sess, WALK_DAYS)
    card = await f._card(rs, KEY_C, LO, HI, MATCH_C, None)
    regs_ = await rc.ice.ice_registries(sess)
    ident = await f._identity(rs, KEY_I, LO, HI, MATCH_I, regs_)
    cmb = await f._combat(rs, KEY_B, LO, HI, MATCH_B, None)
    assert card[0] == ident[0] == cmb[0] == "game"
    return card, ident, cmb


def test_live_the_counts_are_what_the_planted_rules_give(walked, planted):
    """[8]: the live walk's whole report equals the report of the same walk
    over the same records handed in directly (two card games of the one
    record on one day, the outside game skipped by its word, one identity
    game, one combat game); and the cycle rule fires once."""
    _path, rs = planted
    card, ident, cmb = run(_fake_items(rs))
    expected = run(rc.walk(rs, FakeFetch({"card": [card, ("skip", "outside"), card],
                                          "identity": [ident], "combat": [cmb]})))
    tally = walked.tally
    assert tally.cut is None and not tally.abandoned
    assert rc.render(tally) == rc.render(expected)
    assert counts(tally)[ID_CMB] == (1, 1, 0)
    assert counts(tally)[ID_DUP][0] == 2 and counts(tally)[ID_IDB][0] == 1
    assert counts(tally)[ID_WIN][0] == tally.windows == tally.windows_total
    assert rc.render(tally)[0] == ("run whole: games read 5 of 5 (card 3 of 3, identity 1 of 1, "
                                   "combat 1 of 1)")


def test_live_a_game_whose_canonical_match_is_outside_the_days_is_counted_outside(walked):
    """[6]: C6 is admitted through its recent attachment; its canonical match
    is the old one, outside the days: not evaluated, counted `outside`."""
    t = walked.tally
    assert t.totals["card"] == 3
    assert t.domains["card"] == {"walked": 2, "skipped": {"outside": 1}}


def test_live_a_purged_stray_record_does_not_remove_a_game_the_passes_evaluate(walked):
    """[7]: C7's attached record is retained; its stray record (another
    attach key) has purged lists. The game is selected and evaluated."""
    t = walked.tally
    assert t.totals["card"] == 3 and t.domains["card"]["walked"] == 2
    assert "purged" not in t.domains["card"]["skipped"]


def test_live_the_report_names_no_identifier(walked, live):
    out = "\n".join(rc.render(walked.tally))
    for part in list(LK.values()) + list(LR.values()) + list(live.plan.ids) + ["q7z", ST_A, ST_B]:
        assert part not in out, part


def test_live_cohort_then_cohort_check(live, monkeypatch, capfd):
    """[13] (design section g): the cohort read prints T, the member counts
    and one digest; the check with that T and digest, after one member's
    attached record is purged, counts each member's state; a changed digest
    is refused."""
    real = REAL_SESSION_FACTORY
    monkeypatch.setattr(rc, "session_factory",
                        lambda d, **k: real(d, url=live.url, extra_settings=live.settings))
    capfd.readouterr()
    code = call_main(["--cohort", "--days", str(COH_DAYS)])
    got = capfd.readouterr()
    assert code == 0 and got.err == "", got.out
    lines = got.out.splitlines()
    m = re.fullmatch(r"cohort at (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ) days 29: members 9 "
                     r"\(card 7, identity 1, combat 1\) digest ([0-9a-f]{64})", lines[0])
    assert m, lines
    assert lines == [lines[0], "report end"]
    at, digest = m.groups()

    async def purge():
        async with live.sm() as db:
            await db.execute(text("UPDATE card_evidence SET lists_purged_at = now() "
                                  "WHERE stable_game_key = :k"), {"k": LK["kp"]})
            await db.commit()
    live.run(purge())
    code = call_main(["--cohort-check", "--rev", COH_REV, "--at", at, "--digest", digest,
                      "--days", str(COH_DAYS)])
    got2 = capfd.readouterr()
    assert code == 0 and got2.err == "", got2.out
    assert got2.out.splitlines() == [
        "cohort check rev %s at %s: members 9; evaluated 1; waiting 6; purged 1; failed 1; "
        "complete no" % (COH_REV, at),
        "cohort card members 7 evaluated 1 waiting 4 purged 1 failed 1",
        "cohort identity members 1 evaluated 0 waiting 1 purged 0 failed 0",
        "cohort combat members 1 evaluated 0 waiting 1 purged 0 failed 0",
        "report end"]
    changed = ("0" if digest[0] != "0" else "1") + digest[1:]
    code = call_main(["--cohort-check", "--rev", COH_REV, "--at", at, "--digest", changed,
                      "--days", str(COH_DAYS)])
    got3 = capfd.readouterr()
    assert code == rc.EXIT_REFUSED and got3.out == "refused (cohort differs)\n" and got3.err == ""
    out = got.out + got2.out + got3.out
    for part in list(LK.values()) + list(LR.values()) + list(live.plan.ids) + ["q7z", ST_A, ST_B]:
        assert part not in out, part
