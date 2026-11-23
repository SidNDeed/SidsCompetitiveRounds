"""The calibration tool (review_calibrate): a named revision counted rule by
rule over recorded evidence, read only; the cohort and its check.

Every rule bound below is INVENTED for these tests (an unusual value chosen
only to exercise the machinery) and is written as a V(<constant>) call, so a
separate check can read them all. Player ids, game keys and rooms are
obviously synthetic.

The live cases (every test whose name holds `live`) run against a throwaway
database built the way the combat evidence lane builds its own
(combat_evidence_pg.case: the seat-evidence build with every evidence
domain's tables), through the tool's own connection (calibrate_session_factory with a
statement recorder); they FAIL rather than skip when
SEAT_EVIDENCE_TEST_PG_DSN is unset, unless SEAT_EVIDENCE_TEST_PG_OPTOUT=1
waives it (seat_evidence_pg.require_live_pg).

THE APPROVED SHAPE (shape_faults): the statement is read by one tokenizer,
left to right, that knows string literals ('', E'' and dollar-quoted),
quoted identifiers, comments (-- and nested /* */) and parameters, so a
comment marker inside a string is a string and a quoted name is a name. One
statement only (a semicolon may only end it); its kind is one of BEGIN,
ROLLBACK, SELECT, WITH, SHOW; every name followed by a parenthesis, quoted or
not, schema-qualified or not, is a call unless it is an SQL word (unquoted
only) or the name of a CTE AT ITS OWN DECLARATION (`WITH [RECURSIVE] name(
columns ) AS (`); a call names an approved function; no write word, no row
lock. A function that shares a CTE's name is a call like any other.
Approved functions: the ones the tool's and the passes' read helpers use
(APPROVED_FUNCTIONS) and three the driver and the SQL dialect use on their
own (DRIVER_FUNCTIONS: version and current_schema from the dialect's
first-connect initialization, array_agg from the driver's type
introspection). set_config and current_setting are on no list.
"""

import ast
import asyncio
import builtins
import contextlib
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import types
import zoneinfo
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

REAL_SESSION_FACTORY = rc.calibrate_session_factory     # before any test stubs it

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
    """calibrate_cli(argv); any exception that leaves calibrate_cli fails the test
    (the outermost handler must hold every one)."""
    try:
        return rc.calibrate_cli(argv)
    except BaseException as e:                 # noqa: BLE001
        pytest.fail("calibrate_cli raised %s" % type(e).__name__)


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

    def __init__(self, by_domain, before=None, hang=None):
        self.by_domain = by_domain
        self.before = before
        self.hang = hang               # a domain whose selection never returns
        self.now = 0
        self.closed = []

    async def total(self, domain):
        if domain == self.hang:
            await asyncio.sleep(3600)
        return len(self.by_domain.get(domain, ()))

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
    tally = run(rc.calibrate_walk(rs, FakeFetch(planted_items())))
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
    alone = counts(run(rc.calibrate_walk(rs, FakeFetch(planted_items()))))
    monkeypatch.setattr(rc, "one_rule", lambda rs_, rule: rs_)
    whole = counts(run(rc.calibrate_walk(rs, FakeFetch(planted_items()))))
    assert whole != alone
    assert whole[ID_DUP][2] == 1 and alone[ID_DUP][2] == 0


def test_evaluated_counts_every_call_of_the_evaluator_a_game_without_subjects_included(planted):
    """[15] the definition of `evaluated`: every call, whatever it finds. A
    card game with no hand is evaluated once by each card.hand rule and fires
    none; a raising rule's call is evaluated and counted as one error."""
    _path, rs = planted
    tally = run(rc.calibrate_walk(rs, FakeFetch({"card": [("game", (view(), DAY0)),
                                                 ("game", (view(hand(spx="text")), DAY0))]})))
    got = counts(tally)
    assert got[ID_DUP] == (2, 0, 0) and got[ID_HELD] == (2, 0, 0)
    assert got[ID_RAISE] == (2, 0, 1)


def test_a_call_that_raises_is_evaluated_once_and_counted_as_one_error(planted):
    """[15] the definition of `errors`: an exception of the evaluator's call
    is one error and the game stays evaluated; the rule errors a call
    reports are added."""
    _path, rs = planted
    tally = rc.Tally(rs)
    rule = next(r for r in tally.rules if r.id == ID_DUP)

    def raises(_one):
        raise ValueError("planted")
    tally._count(rule, raises)
    assert counts(tally)[ID_DUP] == (1, 0, 1)
    tally._count(rule, lambda _one: ([], {ID_DUP}, 2))
    assert counts(tally)[ID_DUP] == (2, 1, 3)


def test_fired_counts_a_note_rule_and_each_rule_line_names_its_class(tmp_path):
    """[15] the definition of `fired`: the rule is in the call's fired set,
    flag or note alike; the line says which class the rule is."""
    doc = planted_doc()
    doc["rules"][0]["effect"] = "note"
    root, rev = build_planted(tmp_path, doc)
    rs = rr.load_dir(os.path.join(root, "rules-" + rev))
    tally = run(rc.calibrate_walk(rs, FakeFetch(planted_items())))
    assert counts(tally)[ID_DUP] == (3, 1, 0) and counts(tally)[ID_HELD] == (3, 1, 0)
    lines = rc.calibrate_render(tally)
    assert "rule %s scope=card class=note evaluated=3 fired=1 errors=0" % ID_DUP in lines
    assert "rule %s scope=card class=flag evaluated=3 fired=1 errors=0" % ID_HELD in lines


def test_the_one_rule_copy_holds_only_that_rule_and_leaves_the_ruleset_alone(planted):
    _path, rs = planted
    before = [r.id for r in rs.rules]
    rule = rs.rule(ID_HELD)
    single = rc.one_rule(rs, rule)
    assert [r.id for r in single.card_rules] == [ID_HELD] and single.identity_rules == []
    assert [r.id for r in rs.rules] == before and single.core is rs.core


def test_skipped_games_are_counted_by_word_and_never_as_walked(planted):
    _path, rs = planted
    tally = run(rc.calibrate_walk(rs, FakeFetch(planted_items())))
    assert tally.domains["card"] == {"walked": 3, "skipped": {"nomatch": 1, "purged": 1}}
    assert tally.domains["identity"] == {"walked": 2, "skipped": {"unnamed": 1}}
    assert tally.domains["combat"] == {"walked": 2, "skipped": {}}
    lines = rc.calibrate_render(tally)
    assert "domain card walked=3 windows=1 skipped=2 nomatch=1 purged=1" in lines
    assert "domain identity walked=2 skipped=1 unnamed=1" in lines
    assert "domain combat walked=2 skipped=0" in lines
    assert "rule %s scope=card class=flag evaluated=3 fired=0 errors=1" % ID_RAISE in lines
    assert "ambiguous (tied earliest match, not counted): card 0, identity 0, combat 0" in lines
    assert "game and sitting rules not counted: 1" in lines


REPORT_FIXED = 1 + 1 + len(rc.DOMAINS) + 1 + 1 + 1   # summary, fired line, domains, ambiguous, uncounted, end


def test_the_report_ends_with_its_end_line_once_and_the_count_lines_are_unchanged(planted):
    """The last line is `report end`, exactly once; the lines before it are
    the summary, the line on fired, one per counted rule, one per domain, the
    ambiguous line and the uncounted line, in that order."""
    _path, rs = planted
    tally = run(rc.calibrate_walk(rs, FakeFetch(planted_items())))
    lines = rc.calibrate_render(tally)
    assert _tail(lines) == "report end" and lines.count("report end") < 2
    assert len(lines) == REPORT_FIXED + len(tally.rules)
    assert lines[0] == ("run whole: games read 10 of 10 (card 5 of 5, identity 3 of 3, "
                        "combat 2 of 2)")
    assert lines[1] == "fired counts flag and note rules alike; each rule line names its class"
    assert [ln.split()[1] for ln in lines[2:2 + len(tally.rules)]] == [r.id for r in tally.rules]
    assert lines[-3].startswith("ambiguous (tied earliest match, not counted): ")
    assert lines[-2] == "game and sitting rules not counted: 1"


class _Writes:
    """A standard output that records every write CALL."""

    def __init__(self):
        self.calls = []

    def write(self, s):
        self.calls.append(s)
        return len(s)

    def flush(self):
        pass


@pytest.mark.parametrize("case", ["report", "count-failure"])
def test_a_run_writes_its_output_in_exactly_one_write_call(rooted, no_db, monkeypatch, case):
    """[14] (METHOD 1): calibrate_cli() makes ONE write call for the whole run, the
    count report (header to `report end`) or the one fixed line of a failure
    that comes after the revision loaded (no header before it)."""
    path, rs = rooted
    if case == "count-failure":
        from sqlalchemy.exc import OperationalError

        async def failing(rs_, days, deadline_at=None):
            raise OperationalError("SELECT 1", {}, Exception(TOKEN))
        monkeypatch.setattr(rc, "_calibrate_run", failing)
    out = _Writes()
    monkeypatch.setattr(sys, "stdout", out)
    code = call_main(["--revision", path, "--days", "23"])
    monkeypatch.undo()
    assert len(out.calls) == 1, len(out.calls)
    if case == "report":
        assert code == 0
        assert out.calls[0].startswith("revision %s days 23 " % rs.rev)
        assert out.calls[0].endswith("\nreport end\n")
    else:
        assert code == rc.EXIT_FAILED and out.calls == ["failed (database)\n"]


def test_a_cancelled_selection_reads_unknown_and_keeps_the_finished_totals(planted):
    """[13]: the walk is cancelled while the identity selection runs: the card
    total (finished) is kept, identity and combat read `unknown`, and no
    denominator is made up from what was read."""
    _path, rs = planted
    tally = rc.Tally(rs)
    fetch = FakeFetch(planted_items(), hang="identity")
    run(rc.bounded(rc.calibrate_walk(rs, fetch, tally=tally), tally, time.monotonic() + 0.3))
    assert tally.cut == "deadline"
    assert tally.totals == {"card": 5, "identity": None, "combat": None}
    head = rc.calibrate_render(tally)[0]
    assert head.startswith("run cut (deadline): games read 0 of unknown (card 0 of 5, "
                           "identity 0 of unknown, combat 0 of unknown); "), head


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
    tally = run(rc.calibrate_walk(rs, FakeFetch(window_items())))
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
    tally = run(rc.calibrate_walk(rs, FakeFetch(window_items())))
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
    tally = run(rc.calibrate_walk(rs, FakeFetch(window_items())))
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
    out = "\n".join(rc.calibrate_render(run(rc.calibrate_walk(rs, FakeFetch(items)))))
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

WRITE_WORDS = frozenset({
    "insert", "update", "delete", "merge", "create", "alter", "drop", "truncate", "grant", "revoke",
    "copy", "commit", "lock", "notify", "listen", "call", "do", "set", "reset", "discard",
    "prepare", "execute"})
LOCK_TAILS = (("update",), ("share",), ("no", "key", "update"), ("key", "share"))
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")
_PARAM = re.compile(r"\$[0-9]+")


def sql_tokens(sql):
    """The statement as (kind, text) tokens, read left to right once:
    `word` (unquoted, lower-cased), `qident` (a quoted identifier's name as
    written), `string` ('', E'' with backslash escapes, dollar-quoted),
    `param`, `number`, `punct`; comments (-- to the line's end, nested /* */)
    are dropped; `fault` for an unterminated string, identifier or comment."""
    out, i, n = [], 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch.isspace():
            i += 1
        elif sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j + 1
        elif sql.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if sql.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif sql.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            if depth:
                return out + [("fault", "unterminated comment")]
            i = j
        elif ch == "'" or (ch in "eE" and sql.startswith("'", i + 1)):
            esc = ch != "'"
            j = i + (2 if esc else 1)
            while True:
                if j >= n:
                    return out + [("fault", "unterminated string")]
                if esc and sql[j] == "\\":
                    j += 2
                elif sql[j] == "'" and sql.startswith("'", j + 1):
                    j += 2
                elif sql[j] == "'":
                    break
                else:
                    j += 1
            out.append(("string", sql[i:j + 1]))
            i = j + 1
        elif ch == '"':
            j, name = i + 1, []
            while True:
                if j >= n:
                    return out + [("fault", "unterminated identifier")]
                if sql[j] == '"' and sql.startswith('"', j + 1):
                    name.append('"')
                    j += 2
                elif sql[j] == '"':
                    break
                else:
                    name.append(sql[j])
                    j += 1
            out.append(("qident", "".join(name)))
            i = j + 1
        elif ch == "$" and _DOLLAR_TAG.match(sql, i):
            tag = _DOLLAR_TAG.match(sql, i).group(0)
            j = sql.find(tag, i + len(tag))
            if j < 0:
                return out + [("fault", "unterminated string")]
            out.append(("string", sql[i:j + len(tag)]))
            i = j + len(tag)
        elif ch == "$" and _PARAM.match(sql, i):
            m = _PARAM.match(sql, i)
            out.append(("param", m.group(0)))
            i = m.end()
        elif _WORD.match(sql, i):
            m = _WORD.match(sql, i)
            out.append(("word", m.group(0).lower()))
            i = m.end()
        elif _NUMBER.match(sql, i):
            m = _NUMBER.match(sql, i)
            out.append(("number", m.group(0)))
            i = m.end()
        else:
            out.append(("punct", ch))
            i += 1
    return out


def _closing(toks, i):
    """The index of the parenthesis that closes the one at toks[i]."""
    depth = 0
    for j in range(i, len(toks)):
        if toks[j] == ("punct", "("):
            depth += 1
        elif toks[j] == ("punct", ")"):
            depth -= 1
            if depth == 0:
                return j
    return None


def _cte_declarations(toks):
    """The indices of the tokens that name a CTE AT ITS DECLARATION, read from
    the WITH lists only: the name right after WITH or WITH RECURSIVE, or right
    after a comma that follows the closing parenthesis of a CTE body at the
    list's own depth; then its column list, AS, and its body. The list ends at
    the first token after a body that is not a comma (the statement the list
    belongs to). Outside a WITH list nothing is a declaration."""
    out = set()
    for w, t in enumerate(toks):
        if t != ("word", "with"):
            continue
        i = w + 1
        if i < len(toks) and toks[i] == ("word", "recursive"):
            i += 1
        while i < len(toks) and toks[i][0] in ("word", "qident"):
            at = i
            i += 1
            if i < len(toks) and toks[i] == ("punct", "("):         # the column list
                j = _closing(toks, i)
                if j is None:
                    break
                i = j + 1
            if i >= len(toks) or toks[i] != ("word", "as"):
                break
            i += 1
            if i < len(toks) and toks[i] == ("word", "not"):
                i += 1
            if i < len(toks) and toks[i] == ("word", "materialized"):
                i += 1
            if i >= len(toks) or toks[i] != ("punct", "("):
                break
            j = _closing(toks, i)                                  # the CTE body
            if j is None:
                break
            out.add(at)
            i = j + 1
            if i < len(toks) and toks[i] == ("punct", ","):
                i += 1
                continue
            break
    return out


def shape_faults(sql):
    """Every way `sql` is off the approved shape (empty: approved)."""
    toks = sql_tokens(sql)
    faults = [t[1] for t in toks if t[0] == "fault"]
    toks = [t for t in toks if t[0] != "fault"]
    decl = _cte_declarations(toks)
    semis = [i for i, t in enumerate(toks) if t == ("punct", ";")]
    if semis and semis != [len(toks) - 1]:
        faults.append("two statements")
    kind = toks[0][1].upper() if toks and toks[0][0] == "word" else ""
    if kind not in APPROVED_KINDS:
        faults.append("kind " + kind)
    known = APPROVED_FUNCTIONS | DRIVER_FUNCTIONS
    for i, (tk, name) in enumerate(toks):
        if tk not in ("word", "qident") or i + 1 >= len(toks) or toks[i + 1] != ("punct", "("):
            continue
        if tk == "word" and name in SQL_WORDS:
            continue
        if i in decl:
            continue
        if name not in known:
            faults.append("function " + name)
    words = [t[1] for t in toks if t[0] == "word"]
    if kind == "SHOW":
        if not all(t[0] == "word" for t in toks[1:len(toks) - (1 if semis else 0)]) or len(words) < 2:
            faults.append("show form")
    else:
        hit = [w for w in words if w in WRITE_WORDS]
        if hit:
            faults.append("write word " + hit[0])
    for i, w in enumerate(words):
        if w == "for" and any(tuple(words[i + 1:i + 1 + len(t)]) == t for t in LOCK_TAILS):
            faults.append("row lock")
    return faults


def tool_statements():
    """Every SQL text the tool's module holds."""
    out = [rc._GAMES_SQL.format(t=t) for t in rc._TABLES.values()]
    out += [rc._CARD_ROWS.text, rc._CARD_MATCH.text, rc._ICE_ROWS.text, rc._ICE_MATCH.text,
            rc._COMBAT_ROWS.text, rc._COMBAT_MATCH.text, rc._AT_SQL, rc._NOW_SQL]
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
                "SHOW jit; SET jit = on", "SELECT lo_import('x')", "SELECT dblink('x', 'y')",
                "SELECT 1; SELECT 2", "SELECT pg_catalog.set_config('jit', 'off', false)"):
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


@pytest.mark.parametrize("sql", [
    'SELECT "pg_advisory_lock"(1)',
    "SELECT \"set_config\"('jit','off',false)",
    "SELECT '--', pg_advisory_lock(1)",
    "SELECT '/*', pg_advisory_lock(1), '*/'",
    "SELECT $$ -- $$, pg_advisory_lock(1)",
    "SELECT E'\\' --', pg_advisory_lock(1)",
    "WITH RECURSIVE tree(oid) AS (SELECT 1) SELECT tree(1) FROM tree",
    "WITH RECURSIVE pg_advisory_lock(n) AS (SELECT 1) SELECT pg_advisory_lock(1)",
], ids=["quoted-call", "quoted-set-config", "comment-marker-in-string", "block-marker-in-string",
        "dollar-quoted", "escape-string", "function-named-like-a-cte", "cte-named-like-a-function"])
def test_the_shape_check_reads_quoting_string_bounds_and_function_identity(sql):
    """[6]: the three probes the round named (a quoted function name, a
    quoted set_config, a comment marker inside a string) and their kin are
    off the shape; a function that shares a CTE's name is a call."""
    assert any(f.startswith("function ") for f in shape_faults(sql)), (sql, shape_faults(sql))


def test_the_shape_check_allows_a_cte_name_only_at_its_own_declaration():
    """Control of the CTE allowance: the declared CTE with its column list is
    not a call, the driver's introspection shape is approved, and an
    approved function written quoted is that function."""
    assert shape_faults("WITH RECURSIVE tree(oid, depth) AS (SELECT array_agg(a) FROM t "
                        "WHERE a = any($1::oid[])) SELECT * FROM tree") == []
    assert shape_faults("WITH a(x) AS (SELECT 1), b(y) AS (SELECT 2) SELECT * FROM a, b") == []
    assert shape_faults("WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n FROM t), "
                        "u(m) AS (SELECT n FROM t) SELECT * FROM u") == []
    assert shape_faults("SELECT x FROM (WITH a(x) AS (SELECT 1) SELECT x FROM a) s") == []
    assert shape_faults('SELECT "now"()') == []
    assert shape_faults("SELECT 'it''s', $q$ a ' b $q$, E'\\'' FROM t") == []
    assert shape_faults("SELECT 1 -- a comment with set_config(\n") == []


@pytest.mark.parametrize("sql", [
    "SELECT 1, pg_advisory_lock(1) AS y",
    "SELECT 1, set_config('jit', 'off', false) AS y",
    "WITH a AS (SELECT 1, pg_advisory_lock(1) AS y) SELECT * FROM a",
    "WITH a AS (SELECT 1) SELECT 1, pg_advisory_lock(1) AS y FROM a",
    "SELECT s.y FROM (SELECT 1, pg_advisory_lock(1) AS y) s",
], ids=["select-list-call", "select-list-set-config", "call-in-cte-body",
        "main-select-call-after-with", "call-in-subquery"])
def test_a_name_counts_as_declared_only_inside_a_with_list(sql):
    """[6] (ORDER-R3-FIX-2 F1): a call after a comma and closed by `) AS` is
    a call, not a CTE declaration, everywhere outside a WITH list: in a
    select list, in a CTE body, in the main select after a WITH list, in a
    subquery."""
    assert any(f.startswith("function ") for f in shape_faults(sql)), (sql, shape_faults(sql))


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
NOW_AT = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)     # 2026-03-08: a clock change in America/Los_Angeles


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

    now = NOW_AT

    def _answer(self, sql, b):
        if sql == rc._NOW_SQL:
            return [{"now": self.now}]
        if sql.startswith("WITH cand AS") and "CAST(:cut AS timestamptz)" in sql:
            table = sql.split(" FROM ", 1)[1].split()[0]
            key, mid = {"card_evidence": (KEY_C, MATCH_C),
                        "identity_clock_evidence": (KEY_I, MATCH_I),
                        "combat_evidence": (KEY_B, MATCH_B)}[table]
            assert set(b) == {"cut", "lag"}
            return [{"k": key, "lo": LO, "hi": HI, "mid": mid, "recent": True, "tied": False}]
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
    assert len(selections) == 3 and all(b["cut"] == NOW_AT - timedelta(days=41) for b in selections)
    assert counts(tally)[ID_CMB] == (1, 1, 0)
    out = "\n".join(rc.calibrate_render(tally) + [printed.out, printed.err])
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
                    rows[0]["tied"] = None
            return rows
    sess = S()
    tally = run(rc.walk_db(rs, lambda: sess, 41))
    assert tally.domains["card"] == {"walked": 0, "skipped": {word: 1}}
    assert not any("FROM card_evidence WHERE" in s for s, _b in sess.log)


def test_a_game_whose_earliest_eligible_matches_tie_is_counted_ambiguous_and_nowhere_else(planted):
    """[10]: the selection says the game's earliest eligible match is tied.
    The tool does not choose: the game is counted on the ambiguous line, is
    neither walked nor skipped, and is not read further."""
    _path, rs = planted

    class S(RecordingSession):
        def _answer(self, sql, b):
            rows = super()._answer(sql, b)
            if sql.startswith("WITH cand AS") and "card_evidence" in sql.split(" FROM ", 1)[1][:20]:
                rows[0]["tied"] = True
            return rows
    sess = S()
    tally = run(rc.walk_db(rs, lambda: sess, 41))
    assert tally.ambiguous == {"card": 1, "identity": 0, "combat": 0}
    assert tally.domains["card"] == {"walked": 0, "skipped": {}}
    assert counts(tally)[ID_DUP] == (0, 0, 0)
    assert not any("FROM card_evidence WHERE" in s for s, _b in sess.log)
    lines = rc.calibrate_render(tally)
    assert "ambiguous (tied earliest match, not counted): card 1, identity 0, combat 0" in lines
    assert lines[0].startswith("run whole: games read 3 of 3 (card 1 of 1, ")


def test_a_tied_game_outside_the_window_is_counted_outside_and_not_ambiguous(planted):
    """[10] (ORDER-R3-FIX-2 F2, ORDER-R3-FIX-3 G1), the walk's order alone: the
    selection's row says the game's canonical match is tied and ended at or
    before the cutoff (`recent` false, `tied` true: its OLDEST named matches
    end at the same instant at or before the cutoff, and a later match of the
    game ended after it, which is why the game is read). It is counted once
    under `outside`, not on the ambiguous line, and the counts still sum to
    the games read. The statement's part is held on the database by
    test_live_the_selection_reads_a_tied_old_canonical_match_as_outside_and_not_a_game_without_a_recent_match."""
    _path, rs = planted

    class S(RecordingSession):
        def _answer(self, sql, b):
            rows = super()._answer(sql, b)
            if sql.startswith("WITH cand AS") and "card_evidence" in sql.split(" FROM ", 1)[1][:20]:
                rows[0]["recent"] = False
                rows[0]["tied"] = True
            return rows
    sess = S()
    tally = run(rc.walk_db(rs, lambda: sess, 41))
    assert tally.domains["card"] == {"walked": 0, "skipped": {"outside": 1}}
    assert tally.ambiguous == {"card": 0, "identity": 0, "combat": 0}
    for d in rc.DOMAINS:
        v = tally.domains[d]
        assert v["walked"] + sum(v["skipped"].values()) + tally.ambiguous[d] == tally.totals[d]
    lines = rc.calibrate_render(tally)
    assert "ambiguous (tied earliest match, not counted): card 0, identity 0, combat 0" in lines
    assert lines[0].startswith("run whole: games read 3 of 3 (card 1 of 1, ")
    doc = " ".join(rc.__doc__.split())
    assert ("A read game whose canonical match ended at or before the cutoff is counted as "
            "`outside`, tied or not.") in doc
    assert ("A tied game whose canonical match ended after the cutoff is counted on the "
            "ambiguous line") in doc


def test_the_selection_states_the_tie_and_a_total_order_in_its_statement():
    """[10]: the canonical pick orders by the match id after the end time
    (one result under every plan) and the statement returns whether the
    earliest end is shared; the cohort's statement the same."""
    for sql in [rc._GAMES_SQL.format(t="card_evidence"), rc.cohort_sql("card")]:
        flat = " ".join(sql.split())
        assert "ORDER BY x.k, x.lo, x.hi, x.ended, x.mid" in flat
        assert "AND y.ended = x.ended) AS ties" in flat


@pytest.mark.parametrize("now", [NOW_AT, NOW_AT.astimezone(timezone(timedelta(hours=-7))),
                                 NOW_AT.astimezone(zoneinfo.ZoneInfo("America/Los_Angeles"))],
                         ids=["utc", "offset", "zone-across-a-clock-change"])
def test_the_days_cutoff_is_computed_in_utc_and_bound_as_a_time_stamp_with_zone(planted, now):
    """[11]: the cutoff is the database's now() in UTC less days x 86400 s,
    bound as a parameter cast to timestamptz; no statement does day
    arithmetic in the session's zone. NOW_AT is a day after a clock change
    in America/Los_Angeles: wall-clock arithmetic there gives 13:00Z, not
    12:00Z."""
    _path, rs = planted
    sess = RecordingSession()
    sess.now = now
    run(rc.walk_db(rs, lambda: sess, 1))
    cuts = [b["cut"] for s, b in sess.log if s.startswith("WITH cand AS")]
    assert cuts == [datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)] * 3
    assert all(c.utcoffset() == timedelta(0) for c in cuts)
    for sql in [rc._GAMES_SQL.format(t="card_evidence")] + [rc.cohort_sql(d) for d in rc.DOMAINS]:
        assert "make_interval(days" not in sql and "CAST(:cut AS timestamptz)" in sql


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
    assert "domain combat walked=0 skipped=1 rebuild_fault=1" in rc.calibrate_render(tally)
    assert tally.domains["card"]["walked"] == 1 and tally.domains["identity"]["walked"] == 1


# -- the connection's startup parameters ------------------------------------------------------

def test_the_connection_is_read_only_from_its_startup_parameters():
    """[9] (METHOD 2): the statement and idle timeouts are the deadline's
    seconds, never more than the deadline."""
    s = rc.server_settings(41)
    ms = str(41 * 1000)
    assert s == {"default_transaction_read_only": "on",
                 "default_transaction_isolation": "repeatable read",
                 "statement_timeout": ms, "idle_in_transaction_session_timeout": ms,
                 "jit": "off"}


def test_the_seconds_left_are_rounded_up_and_never_more_than_the_deadline():
    for left in (0.0, 0.2, 6.999, 7.0):
        got = rc._remaining_s(time.monotonic() + left)
        assert 1 <= got <= max(1, 7), (left, got)
    assert rc._remaining_s(time.monotonic() + 1199.5) <= 1200


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://calib@127.0.0.1:1/calib?sslmode=disable",
    "postgresql+asyncpg://calib@127.0.0.1/calib",
    "postgresql+asyncpg://127.0.0.1:1/calib",
    "postgresql+asyncpg://calib@127.0.0.1:1",
    "postgresql+asyncpg://calib@:1/calib",
], ids=["option", "no-port", "no-user", "no-database", "no-host"])
def test_an_address_with_options_or_without_a_part_is_refused_before_any_connection(url):
    """[5]: the connection is built from the address's explicit parts; one
    the driver would fill from the environment is refused."""
    with pytest.raises(rc.ConfigRefused):
        rc.calibrate_session_factory(5, url=url)


def test_the_drivers_environment_is_out_of_the_process_while_it_connects(monkeypatch):
    """[5]: every variable of _DRIVER_ENV planted; the driver's connect sees
    none of them, and each is back after the connect returns."""
    import asyncpg
    for k in rc._DRIVER_ENV:
        monkeypatch.setenv(k, "planted")
    seen = {}

    class Conn:
        _server_caps = types.SimpleNamespace(_replace=lambda **k: "caps")
        _protocol = None

    async def fake_connect(**kw):
        seen.update({k: os.environ.get(k) for k in rc._DRIVER_ENV})
        seen["kw"] = sorted(kw)
        return Conn()
    monkeypatch.setattr(asyncpg, "connect", fake_connect)
    run(rc._connect({"host": "127.0.0.1", "port": 1, "user": "calib", "database": "calib"},
                    rc.server_settings(5)))
    assert {k: seen[k] for k in rc._DRIVER_ENV} == dict.fromkeys(rc._DRIVER_ENV)
    assert seen["kw"] == ["database", "host", "port", "server_settings", "user"]
    assert all(os.environ.get(k) == "planted" for k in rc._DRIVER_ENV)


_ENV_READ = re.compile(r"""\bos\.(?:getenv|environ\.get)\(\s*['"]([A-Z_]+)['"]""")


# Per driver version: in its connect module and its platform module, the
# number of calls of each name that builds a path from the home directory or
# from an application data directory (read at each version's source).
_DRIVER_PATH_CALLS = {
    "0.29.0": {"connect_utils": {"get_pg_home_directory": 1, "home": 1, "_dot_postgresql_path": 4},
               "compat": {"home": 1, "SHGetFolderPathW": 1}},
    "0.31.0": {"connect_utils": {"get_pg_home_directory": 2, "home": 1, "_dot_postgresql_path": 4},
               "compat": {"home": 1, "SHGetFolderPathW": 1}},
}
_PATH_CALL_NAMES = ("get_pg_home_directory", "home", "expanduser", "expandvars", "getenv",
                    "SHGetFolderPathW", "SHGetKnownFolderPath", "_dot_postgresql_path",
                    "user_config_dir", "user_data_dir")


def _path_calls(src):
    """{call name: count} of the calls in `src` whose name is one of
    _PATH_CALL_NAMES, read by syntax tree (comments and strings do not
    count); an os.getenv / environ read of HOME, APPDATA, LOCALAPPDATA or
    USERPROFILE counts under its variable's name."""
    out = {}
    for n in ast.walk(ast.parse(src)):
        name = None
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name in ("getenv", "get"):
                arg = n.args[0] if n.args else None
                name = arg.value if isinstance(arg, ast.Constant) and arg.value in (
                    "HOME", "APPDATA", "LOCALAPPDATA", "USERPROFILE") else None
            elif name not in _PATH_CALL_NAMES:
                name = None
        elif isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value in (
                "HOME", "APPDATA", "LOCALAPPDATA", "USERPROFILE"):
            name = n.slice.value
        if name:
            out[name] = out.get(name, 0) + 1
    return out


def test_the_drivers_environment_list_holds_every_variable_its_connect_parser_reads():
    """[5] (ORDER-R3-FIX-2 F7b, ORDER-R3-FIX-3 G4), held against the INSTALLED
    driver's own source: every environment variable asyncpg's
    connect-parameter parser reads is in _DRIVER_ENV, and every environment
    access there has the read form counted; every file name it passes to its
    .postgresql path helper or names as the password file is in
    _DRIVER_HOME_FILES, which the module text names as a declared limit.
    The places where the connect module and the platform module build a path
    from the home directory or an application data directory are counted by
    call name and must equal the counts recorded for that driver version
    (_DRIVER_PATH_CALLS); a version not recorded is red. So a variable the
    parser adds, and a new place where the driver builds such a path, are red.
    A LIMIT: a file the driver reads by another route (a path built without
    one of the counted calls, or in another module) is not seen."""
    import asyncpg
    import asyncpg.compat as compat
    import asyncpg.connect_utils as cu
    src = open(cu.__file__, encoding="utf-8").read()
    assert asyncpg.__version__ in _DRIVER_PATH_CALLS, asyncpg.__version__
    want = _DRIVER_PATH_CALLS[asyncpg.__version__]
    got = {"connect_utils": _path_calls(src),
           "compat": _path_calls(open(compat.__file__, encoding="utf-8").read())}
    assert got == want, got
    names = set(_ENV_READ.findall(src))
    assert len(re.findall(r"\bos\.(?:getenv|environ)\b", src)) == len(_ENV_READ.findall(src))
    assert names and names <= set(rc._DRIVER_ENV), sorted(names - set(rc._DRIVER_ENV))
    files = set(re.findall(r"""_dot_postgresql_path\(\s*['"]([^'"]+)['"]""", src))
    files |= set(re.findall(r"""^\s*PGPASSFILE\s*=\s*['"]([^'"]+)['"]""", src, re.M))
    assert len(re.findall(r"_dot_postgresql_path\(", src)) == 1 + len(
        re.findall(r"""_dot_postgresql_path\(\s*['"]""", src))          # the definition + named calls
    assert files and files <= set(rc._DRIVER_HOME_FILES), sorted(files - set(rc._DRIVER_HOME_FILES))
    doc = " ".join(rc.__doc__.split())
    assert "A DECLARED LIMIT" in doc and "_DRIVER_HOME_FILES" in doc
    for f in rc._DRIVER_HOME_FILES:
        assert f in doc, f
    print("DRIVER-ENV asyncpg %s: %d variables read, all in _DRIVER_ENV; files %s"
          % (asyncpg.__version__, len(names), sorted(files)))


class _SwallowingDisposal:
    """An engine whose disposal swallows its cancellation and goes on for
    `rest_s` more."""

    def __init__(self, rest_s):
        self.rest_s = rest_s
        self.cancelled = 0

    async def dispose(self):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self.cancelled += 1
            await asyncio.sleep(self.rest_s)


def test_a_disposal_that_swallows_its_cancellation_is_abandoned_after_the_close_slack(monkeypatch):
    """[8] (ORDER-R3-FIX-2 F7a, ORDER-R3-FIX-3 G3): the engine's disposal is
    waited for at most CLOSE_SLACK_S; one that swallows its cancellation
    receives exactly one cancellation and is abandoned, so _dispose returns
    by the slack and not when the disposal would end."""
    monkeypatch.setattr(rc, "CLOSE_SLACK_S", 0.3)
    eng = _SwallowingDisposal(rest_s=3.0)
    t0 = time.monotonic()
    rc._run_loop(rc._dispose(eng))
    elapsed = time.monotonic() - t0
    assert elapsed < 1.5, elapsed
    assert eng.cancelled == 1, eng.cancelled


_RAISES_OUTSIDE_THE_CENSUS = ("utc_cutoff", "bounded")


def _raise_places(tree):
    """One (place, line) per raise statement of the whole module: the name of
    the innermost function around it; `import guard` for a raise inside the
    handler of the module-level try that holds the imports; `module` for any
    other raise outside a function."""
    out = []

    def visit(node, func, guard):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Raise):
                out.append((func or ("import guard" if guard else "module"), child.lineno))
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name, False)
            elif isinstance(child, ast.ExceptHandler) and func is None and isinstance(node, ast.Try) \
                    and node in tree.body and any(isinstance(s, (ast.Import, ast.ImportFrom))
                                                  for s in node.body):
                visit(child, None, True)
            else:
                visit(child, func, guard)
    visit(tree, None, False)
    return out


def test_every_raise_of_the_module_is_in_a_census_function_or_named_outside_it():
    """[7] (ORDER-R3-FIX-2 F7c, ORDER-R3-FIX-3 G5), over the WHOLE module: every
    raise statement stands in a function of _BRANCH_FUNCS (reached by the
    census), in a function named in _RAISES_OUTSIDE_THE_CENSUS, or is the
    import guard's re-raise (inside the handler of the module-level try that
    holds the imports; there is one). A raise anywhere else, a module-level
    one included, is red."""
    tree = ast.parse(open(rc.__file__, encoding="utf-8").read())
    places = _raise_places(tree)
    allowed = set(_BRANCH_FUNCS) | set(_RAISES_OUTSIDE_THE_CENSUS) | {"import guard"}
    assert [p for p in places if p[0] not in allowed] == [], places
    assert [p for p, _ln in places if p == "import guard"] == ["import guard"], places
    assert {p for p, _ln in places} == allowed, places


def test_the_recorder_is_installed_only_in_the_constructor_of_the_connection_class():
    """[5] (ORDER-R3-FIX-3 G2 a), by syntax tree: the module assigns a
    connection's protocol in exactly one place, the constructor (__init__)
    of the class _recording_class builds on the driver's connection class,
    and no setattr names the protocol; the recording protocol is built only
    there; _connect hands that class to the driver as connection_class
    whenever a recorder is given (extra = {} if recorder is None else
    {"connection_class": _recording_class(recorder)}, passed as **extra after
    **args to the driver's one connect call). Seen: attribute store, setattr call, object.__setattr__ call."""
    tree = ast.parse(open(rc.__file__, encoding="utf-8").read())
    funcs = {f.name: f for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "_protocol"
              and isinstance(n.ctx, ast.Store)]
    rec = funcs["_recording_class"]
    cls = [c for c in rec.body if isinstance(c, ast.ClassDef)]
    assert len(cls) == 1 and [ast.unparse(b) for b in cls[0].bases] == ["asyncpg.Connection"]
    init = [f for f in cls[0].body if isinstance(f, ast.FunctionDef) and f.name == "__init__"]
    assert len(init) == 1
    assert len(stores) == 1 and stores[0] in list(ast.walk(init[0])), [ast.unparse(s) for s in stores]
    assert ast.unparse(stores[0].value) == "self"
    builds = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
              and getattr(n.func, "id", None) == "_RecordingProtocol"]
    assert len(builds) == 1 and builds[0] in list(ast.walk(init[0]))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func)
                in ("setattr", "object.__setattr__") and "_protocol" in ast.unparse(n)]
    con = funcs["_connect"]
    extra = [n for n in ast.walk(con) if isinstance(n, ast.Assign)
             and [ast.unparse(t) for t in n.targets] == ["extra"]]
    assert [ast.unparse(e.value) for e in extra] == [
        "{} if recorder is None else {'connection_class': _recording_class(recorder)}"]
    calls = [n for n in ast.walk(con) if isinstance(n, ast.Call) and ast.unparse(n.func) == "asyncpg.connect"]
    assert len(calls) == 1 and [ast.unparse(k.value) for k in calls[0].keywords if k.arg is None] == [
        "args", "extra"]


class _FirstSession(Exception):
    """Ends a run at its first connection (a session asked of the factory)."""


@pytest.mark.parametrize("mode", ["count", "cohort", "check"])
def test_every_run_kind_builds_its_session_factory_with_at_most_the_deadline(
        planted, monkeypatch, mode):
    """[9] (ORDER-R3-FIX-3 G6): in the count run, the cohort run and the check
    run, the session factory is built with a value that is not above
    the deadline given on the command line
    (the upper bound of the last assertion)."""
    path, _rs = planted
    events = []

    class Eng:
        async def dispose(self):
            events.append("dispose")

    def opened():
        events.append("session")
        raise _FirstSession()

    def factory(deadline_s, **_k):
        events.append(("factory", deadline_s, time.monotonic()))
        return Eng(), opened
    monkeypatch.setattr(rc, "calibrate_session_factory", factory)
    monkeypatch.setenv(rr.ROOT_ENV, os.path.dirname(path))
    argv = {"count": ["--revision", path],
            "cohort": ["--cohort"],
            "check": ["--cohort-check", "--rev", "0" * 12, "--at", "2026-01-02T03:04:05Z",
                      "--digest", "0" * 64]}[mode] + ["--days", "5", "--deadline-s", "100"]
    start = time.monotonic()
    with pytest.raises(_FirstSession):
        rc._calibrate_main(argv, start)
    built = [e for e in events if isinstance(e, tuple)]
    assert len(built) == 1, events
    _f, deadline_s, at = built[0]
    assert events.index(built[0]) < events.index("session"), events
    assert isinstance(deadline_s, int) and 100 - (at - start) <= deadline_s <= 100, (deadline_s, at - start)


def test_the_outer_bound_leaves_room_for_the_tools_own_slack():
    """[8] (METHOD 2): the server verb's limit (deadline + VERB_SLACK_S, then
    a kill VERB_KILL_AFTER_S later) is later than the tool's report bound
    (deadline + REPORT_SLACK_S, when the work yields), and the module text
    names both and states the statement bound."""
    assert rc.REPORT_SLACK_S == rc.CANCEL_SLACK_S + rc.CLOSE_SLACK_S + 1
    assert rc.VERB_SLACK_S > rc.REPORT_SLACK_S and rc.VERB_KILL_AFTER_S > 0
    doc = " ".join(rc.__doc__.split())
    for name in ("VERB_SLACK_S", "VERB_KILL_AFTER_S", "REPORT_SLACK_S", "timeout -s TERM -k",
                 "THE ABSOLUTE BOUND of a run is the server verb's outer time limit",
                 "can therefore run for one statement timeout more",
                 "A kill before the one write leaves nothing",
                 # ORDER-R3-FIX-2 F7a, F7d, F4: the sentences as the code gives them
                 "one that does not honour its cancellation included, is asked to cancel "
                 "and abandoned unfinished",
                 "builds its session factory (in every run kind, before its first connection)",
                 "the tool gives every statement the full value ON PURPOSE",
                 "a statement that starts late, when most of the deadline is gone, still has its "
                 "whole statement timeout",
                 # [3] ACCEPTED SMALL RISK, the order's sentence word for word
                 "Only a process that can write the rules directory can replace the named "
                 "directory during a run; the tool then lists the other directory and the load "
                 "refuses, so no count of another revision is printed."):
        assert name in doc, name


# -- the bounded run ------------------------------------------------------------------------

CUT_HEAD = ("run cut (deadline): games read 4 of 10 (card 4 of 5, identity 0 of 3, combat 0 of 2); "
            "card windows evaluated 0 of none rebuilt; every count below covers only what was read")


def _reads_as_whole(line):
    return line.startswith(("run whole", "rule ", "domain ", "game and sitting", "fired ",
                            "ambiguous "))


def test_a_run_its_deadline_ends_says_it_was_cut_and_no_count_reads_as_whole(planted):
    _path, rs = planted
    fetch = FakeFetch(planted_items())
    tally = run(rc.calibrate_walk(rs, fetch, deadline_at=4, clock=lambda: fetch.now))
    assert tally.cut == "deadline" and fetch.closed == ["card"]
    assert tally.domains["card"] == {"walked": 3, "skipped": {"nomatch": 1}}
    assert tally.domains["identity"]["walked"] == tally.domains["combat"]["walked"] == 0
    lines = rc.calibrate_render(tally)
    assert lines[0] == CUT_HEAD
    assert len(lines) == REPORT_FIXED + len(tally.rules)
    assert all(line.startswith("cut ") for line in _middle(lines)) and _tail(lines) == "report end"
    assert not any(_reads_as_whole(line) for line in lines)
    assert "cut rule %s scope=card class=flag evaluated=3 fired=1 errors=0" % ID_DUP in lines
    assert "cut domain card walked=3 windows=0 skipped=1 nomatch=1" in lines


def test_a_run_its_deadline_does_not_reach_reads_every_game_and_says_whole(planted):
    """Control of the cut test: the same walk with a deadline it never reaches."""
    _path, rs = planted
    fetch = FakeFetch(planted_items())
    tally = run(rc.calibrate_walk(rs, fetch, deadline_at=10 ** 6, clock=lambda: fetch.now))
    lines = rc.calibrate_render(tally)
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
    lines = rc.calibrate_render(tally)
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
    assert "card windows evaluated 0 of none rebuilt" in rc.calibrate_render(tally)[0]


def test_a_stop_signal_ends_the_walk_after_the_game_in_hand_and_the_run_says_so(
        planted, monkeypatch):
    _path, rs = planted
    monkeypatch.setitem(rc._STOP, "word", None)
    fetch = FakeFetch(planted_items(),
                      before=lambda n: n == 2 and rc._on_term(signal.SIGTERM, None))
    tally = run(rc.calibrate_walk(rs, fetch))
    lines = rc.calibrate_render(tally)
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
    """[8] (METHOD 2), the claim as the module states it: when the work
    yields, the report is out by the deadline plus REPORT_SLACK_S.
    --deadline-s 1 over a statement that never answers, and in both cases an
    engine whose disposal never ends (cut after CLOSE_SLACK_S); with
    `swallow` the statement also swallows every cancellation (abandoned
    after CANCEL_SLACK_S). Either way calibrate_cli()
    returns within 1 + REPORT_SLACK_S, the first line is the header, the
    second `run cut (deadline)` and the last `report end`."""
    path, rs = rooted
    bound = 1 + rc.REPORT_SLACK_S
    eng = _StandInEngine(slow=True)
    sess = SlowSession(swallow, guard_s=bound + 2)
    monkeypatch.setattr(rc, "calibrate_session_factory", lambda d, **k: (eng, lambda: sess))
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


# THE CENSUS ([7]): exactly one row per distinct refusal and failure branch of
# the module (a branch: a decisive line, test_the_census_has_one_row_per_branch
# reads them from the source), each row the only census row through at least
# one of them. The VARIANTS run the same branches with other values; they are
# held to the same output and are not the census.
ARG_CENSUS = [
    ("argument-not-text", "arguments", _arg(["--cohort", "--days", 5, TOKEN], TOKEN)),
    ("unknown-option", "arguments", _arg(["--cohort", "--days", "5", "--" + TOKEN], TOKEN)),
    ("missing-value", "arguments", _arg(["--revision", "x" + TOKEN, "--days"], TOKEN)),
    ("repeated-option", "arguments", _arg(["--cohort", "--days", "5", "--days", TOKEN], TOKEN)),
    ("no-mode", "arguments", _arg(["--days", "5", "--deadline-s", TOKEN], TOKEN)),
    ("foreign-option", "arguments", _arg(["--cohort", "--days", "5", "--rev", TOKEN], TOKEN)),
    ("days-text", "days", _arg(["--cohort", "--days", TOKEN], TOKEN)),
    ("deadline-text", "deadline", _arg(["--cohort", "--days", "5", "--deadline-s", TOKEN], TOKEN)),
    ("rev-text", "rev", _arg(_check_argv(rev=TOKEN), TOKEN)),
    ("at-text", "at", _arg(_check_argv(at="2026-03-05T" + TOKEN), TOKEN)),
    ("digest-text", "digest", _arg(_check_argv(digest=TOKEN + "a" * 56), TOKEN)),
]
ARG_VARIANTS = [
    ("repeated-flag", "arguments", _arg(["--cohort", "--days", "5", "--cohort", TOKEN], TOKEN)),
    ("two-modes", "arguments", _arg(["--cohort", "--revision", TOKEN, "--days", "5"], TOKEN)),
    ("check-foreign-option", "arguments", _arg(_check_argv() + ["--revision", TOKEN], TOKEN)),
    ("equals-form", "arguments", _arg(["--cohort", "--days=" + TOKEN], TOKEN)),
    ("positional", "arguments", _arg([TOKEN, "--cohort", "--days", "5"], TOKEN)),
    ("days-zero", "days", _arg(["--cohort", "--days", "00000"], "00000")),
    ("days-over", "days", _arg(["--cohort", "--days", "97531"], "97531")),
    ("days-six-digits", "days", _arg(["--cohort", "--days", "123456"], "123456")),
    ("days-negative", "days", _arg(["--cohort", "--days", "-" + TOKEN], TOKEN)),
    ("days-other-digits", "days", _arg(["--cohort", "--days", "\u0663\u0663"], "\u0663\u0663")),
    ("deadline-zero", "deadline", _arg(["--cohort", "--days", "5", "--deadline-s", "00000"],
                                       "00000")),
    ("deadline-over", "deadline", _arg(["--cohort", "--days", "5", "--deadline-s", "97531"],
                                       "97531")),
    ("rev-upper", "rev", _arg(_check_argv(rev="7E5CA0C0FFEE"), "7E5CA0C0FFEE")),
    ("at-no-such-day", "at", _arg(_check_argv(at="2026-02-30T19:53:19Z"),
                                  "2026-02-30T19:53:19Z")),
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


def _p_empty_argument(ctx, root):
    return ""


PATH_CENSUS = [
    ("path-empty-argument", "name", _path_row(_p_empty_argument)),
    ("path-outside-root", "root", _path_row(_p_outside)),
    ("path-pointer", "pointer", _path_row(_p_pointer)),
    ("path-extra-component", "name", _path_row(_p_extra)),
    ("path-missing", "missing", _path_row(_p_missing)),
    ("path-not-a-directory", "missing", _path_row(_p_file)),
    ("path-link", "link", _path_row(_p_link)),
]
PATH_VARIANTS = [
    ("path-root-sibling", "root", _path_row(_p_sibling)),
    ("path-through-pointer", "pointer", _path_row(_p_through_pointer)),
    ("path-none-target", "pointer", _path_row(_p_none)),
    ("path-bad-name", "name", _path_row(_p_bad_name)),
    ("path-empty-component", "name", _path_row(_p_empty)),
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


def _loader_other_content(ctx):
    """[3] (C2): a directory named for one id holds a whole revision of
    another id. The load reads it, finds that the name is not the id of what
    it read and refuses: one fixed line, no count (the row's database stub
    fails the test if a run starts)."""
    import shutil
    root = _root(ctx)
    d = os.path.join(root, "rules-" + HEX_REV)
    shutil.copytree(ctx.path, d)
    assert HEX_REV != ctx.rev and os.path.isfile(os.path.join(d, "REVISION"))   # control
    return {"argv": ["--revision", d, "--days", "5"], "tokens": [TOKEN, ctx.rev],
            "code": rc.EXIT_REFUSED, "out": ["refused (digest)"]}


LOADER_CENSUS = [
    ("loader-class", "class", _loader_row("inventory")),
    ("loader-unreadable-class", "revision", _loader_row(TOKEN + " Bad")),
]
LOADER_VARIANTS = [
    ("loader-real", "class", _loader_real),
    ("loader-other-content", "class", _loader_other_content),
]
LOADER_LINES = {"loader-class": ["refused (inventory)"],
                "loader-unreadable-class": ["refused (revision)"]}


def _cohort_members():
    m = ("cohortkey" + TOKEN, "70000000-0000-0000-0000-0000000c0h01",
         "70000000-0000-0000-0000-0000000c0h02", False, None, False, False, False)
    return {"card": [m], "identity": [], "combat": []}


def _cohort_differs(ctx):
    async def fake(days, deadline_at=None, at=None, rev=None):
        return GOOD_AT, _cohort_members(), {d: 0 for d in rc.DOMAINS}
    ctx.mp.setattr(rc, "_run_cohort", fake)
    return {"argv": _check_argv(digest=HEX_TOKEN), "tokens": [TOKEN, HEX_TOKEN, "c0h0"],
            "code": rc.EXIT_REFUSED, "out": ["refused (cohort differs)"]}


def _cohort_cut(mode):
    """[1] (METHOD 1): a cohort cut is one fixed line, nothing else."""
    def build(ctx):
        async def fake(days, deadline_at=None, at=None, rev=None):
            return None
        ctx.mp.setattr(rc, "_run_cohort", fake)
        argv = _check_argv(digest=HEX_TOKEN) if mode == "check" else ["--cohort", "--days", "5"]
        return {"argv": argv, "tokens": [HEX_TOKEN], "code": rc.EXIT_REFUSED,
                "out": ["cohort cut (deadline): nothing counted"]}
    return build


COHORT_CENSUS = [
    ("cohort-differs", "cohort differs", _cohort_differs),
    ("cohort-cut-cohort", "cohort cut", _cohort_cut("cohort")),
]
COHORT_VARIANTS = [
    ("cohort-cut-check", "cohort cut", _cohort_cut("check")),
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
        "system": OSError(13, TOKEN, TOKEN + ".planted"),
        "internal": ValueError(TOKEN),
        "internal-cancelled": asyncio.CancelledError(TOKEN),
    }


def _failure_row(name, mode="cohort"):
    def build(ctx):
        exc = _failures()[name]

        def factory(*_a, **_k):
            raise exc
        ctx.mp.setattr(rc, "calibrate_session_factory", factory)
        word = name.split("-")[0]
        if mode == "count":
            # [1] (METHOD 1): a database failure in count mode, after the
            # revision loaded, is the one fixed line, no header before it
            ctx.mp.setenv(rr.ROOT_ENV, os.path.dirname(ctx.path))
            return {"argv": ["--revision", ctx.path, "--days", "5"], "tokens": [TOKEN, ctx.rev],
                    "code": rc.EXIT_FAILED, "out": ["failed (%s)" % word]}
        return {"argv": ["--cohort", "--days", "5"], "tokens": [TOKEN], "code": rc.EXIT_FAILED,
                "out": ["failed (%s)" % word]}
    return build


def _failure_real_address(word, address):
    def build(ctx):
        real = REAL_SESSION_FACTORY
        ctx.mp.setattr(rc, "calibrate_session_factory", lambda d, **k: real(d, url=address))
        return {"argv": ["--cohort", "--days", "5"], "tokens": [TOKEN, "127.0.0.1"],
                "code": rc.EXIT_FAILED, "out": ["failed (%s)" % word]}
    return build


def _failure_real_driver(ctx):
    """The tool's own connect over a driver connection without the
    capability flag it clears: refused `driver`."""
    import asyncpg

    class Bare:
        terminated = False

        def terminate(self):
            Bare.terminated = True

    async def bare_connect(**_kw):
        return Bare()
    ctx.mp.setattr(asyncpg, "connect", bare_connect)
    real = REAL_SESSION_FACTORY
    ctx.mp.setattr(rc, "calibrate_session_factory", lambda d, **k: real(
        d, url="postgresql+asyncpg://calib:%s@127.0.0.1:1/%s" % (TOKEN, TOKEN)))
    return {"argv": ["--cohort", "--days", "5"], "tokens": [TOKEN, "127.0.0.1"],
            "code": rc.EXIT_FAILED, "out": ["failed (driver)"]}


FAILURE_CENSUS = [("failure-" + n, n.split("-")[0], _failure_row(n)) for n in (
    "interrupted", "exit", "memory", "timeout", "database-driver", "internal")]
FAILURE_CENSUS += [
    ("failure-count-mode", "database", _failure_row("database", mode="count")),
    ("failure-real-config", "config", _failure_real_address(
        "config", "postgresql+asyncpg://calib:%s@127.0.0.1:1/%s?sslmode=%s" % (TOKEN, TOKEN, TOKEN))),
    ("failure-real-driver", "driver", _failure_real_driver),
    ("failure-real-system", "system", _failure_real_address(
        "system", "postgresql+asyncpg://calib:%s@127.0.0.1:1/%s" % (TOKEN, TOKEN))),
]
FAILURE_VARIANTS = [("failure-" + n, n.split("-")[0], _failure_row(n)) for n in (
    "config", "driver", "database", "system", "internal-cancelled")]


def _process(argv, isolated, out, code):
    def build(ctx):
        cmd = [sys.executable, "-B"] + (["-I"] if isolated else []) + [rc.__file__] + argv
        return {"cmd": cmd, "tokens": [TOKEN], "code": code, "out": out}
    return build


PROCESS_ROWS = [
    ("process-import", "import", _process(["--" + TOKEN], True, ["failed (import)"], rc.EXIT_FAILED)),
    ("process-refusal", "days", _process(["--cohort", "--days", TOKEN], False,
                                         ["refused (days)"], rc.CALIBRATE_EXIT_USAGE)),
]

CENSUS = ([("arg",) + r for r in ARG_CENSUS] + [("path",) + r for r in PATH_CENSUS]
          + [("loader",) + r for r in LOADER_CENSUS] + [("cohort",) + r for r in COHORT_CENSUS]
          + [("failure",) + r for r in FAILURE_CENSUS])
VARIANTS = ([("arg",) + r for r in ARG_VARIANTS] + [("path",) + r for r in PATH_VARIANTS]
            + [("loader",) + r for r in LOADER_VARIANTS] + [("cohort",) + r for r in COHORT_VARIANTS]
            + [("failure",) + r for r in FAILURE_VARIANTS])
TABLE = (CENSUS + VARIANTS
         + [("import" if r[1] == "import" else "arg",) + r for r in PROCESS_ROWS])


def _expected(kind, rid, word, case):
    if "out" in case:
        return case["out"], case.get("code", rc.CALIBRATE_EXIT_USAGE)
    if kind == "arg":
        return ["refused (%s)" % word], rc.CALIBRATE_EXIT_USAGE
    if kind == "path":
        return ["refused (path %s)" % word], rc.CALIBRATE_EXIT_USAGE
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
    monkeypatch.setattr(rc, "calibrate_session_factory", no_database)
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


_BRANCH_FUNCS = ("parse_args", "revision_path", "_calibrate_main", "calibrate_session_factory", "_connect")


def decisive_points():
    """The module's refusal and failure branches, read from its source: every
    raise in the functions that refuse (_BRANCH_FUNCS); every word failure_word
    returns; every return of _calibrate_main with the refusal status; and, for a
    failure that leaves a run, the line of _calibrate_main that started that run (an
    exception passing it)."""
    tree = ast.parse(open(rc.__file__, encoding="utf-8").read())
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    pts = set()
    for name in _BRANCH_FUNCS:
        pts |= {("line", name, n.lineno) for n in ast.walk(funcs[name]) if isinstance(n, ast.Raise)}
    pts |= {("line", "failure_word", n.lineno) for n in ast.walk(funcs["failure_word"])
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)}
    for n in ast.walk(funcs["_calibrate_main"]):
        if (isinstance(n, ast.Return) and isinstance(n.value, ast.Tuple)
                and isinstance(n.value.elts[0], ast.Name) and n.value.elts[0].id == "EXIT_REFUSED"):
            pts.add(("line", "_calibrate_main", n.lineno))
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_run_loop":
            pts.add(("exception", "_calibrate_main", n.lineno))
    return pts


def traced(fn):
    """fn() with every line and exception event of the module's own code
    recorded as (event, function, line)."""
    target = os.path.normcase(os.path.abspath(rc.__file__))
    hits = set()

    def local(frame, event, _arg):
        if event in ("line", "exception"):
            hits.add((event, frame.f_code.co_name, frame.f_lineno))
        return local

    def glob(frame, _event, _arg):
        if os.path.normcase(os.path.abspath(frame.f_code.co_filename)) == target:
            return local
        return None
    old = sys.gettrace()
    sys.settrace(glob)
    try:
        fn()
    finally:
        sys.settrace(old)
    return hits


def _row_points(row, planted, tmp, points):
    kind, rid, word, build = row
    path, rs = planted
    with pytest.MonkeyPatch.context() as mp:
        def no_database(*_a, **_k):
            raise AssertionError("this row reaches no database")
        mp.setattr(rc, "calibrate_session_factory", no_database)
        ctx = types.SimpleNamespace(tmp=tmp, mp=mp, path=path, rev=rs.rev)
        case = build(ctx)
        want, want_code = _expected(kind, rid, word, case)
        got = {}

        def go():
            out = _Writes()
            with pytest.MonkeyPatch.context() as mp2:
                mp2.setattr(sys, "stdout", out)
                got["code"] = call_main(case["argv"])
            got["out"] = "".join(out.calls)
        hits = traced(go)
    assert got["out"].splitlines() == want and got["code"] == want_code, (rid, got)
    return hits & points


def test_the_census_has_one_row_per_branch_and_each_row_is_needed(planted, tmp_path):
    """[7]: every decisive point of the source is reached by a census row,
    and every census row reaches a point no other census row reaches, so
    removing any one row (of any class) leaves a branch unreached: red. Each
    variant reaches only points the census reaches."""
    points = decisive_points()
    assert len(points) >= 30, len(points)
    print("CENSUS rows %d, variants %d, process rows %d, table %d, decisive points %d"
          % (len(CENSUS), len(VARIANTS), len(PROCESS_ROWS), len(TABLE), len(points)))
    got = {}
    for i, row in enumerate(CENSUS + VARIANTS):
        tmp = tmp_path / ("r%02d" % i)
        tmp.mkdir()
        got[row[1]] = _row_points(row, planted, tmp, points)
    census = [r[1] for r in CENSUS]
    reached = set().union(*(got[r] for r in census))
    assert points - reached == set(), sorted(points - reached)
    for rid in census:
        others = set().union(*(got[o] for o in census if o != rid))
        assert got[rid] - others, "census row %s reaches no branch of its own" % rid
    for rid in (r[1] for r in VARIANTS):
        assert got[rid] and got[rid] <= reached, rid
    assert len(set(census)) == len(census) and not set(census) & {r[1] for r in VARIANTS}


def test_the_table_has_a_row_for_every_refusal_and_failure_word():
    """The words of the table are exactly the module's fixed words; the
    import branch has its process row."""
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
    assert set(re.findall(r'"failed \(([^)%]*)\)', src)) == {"import"}
    assert "argparse" not in src


_PLANT = '''import sys
_m = sys.modules.get("__main__")
if getattr(_m, "__file__", "") and _m.__file__.endswith("review_calibrate.py"):
    {what}("planted {token} " + __file__)
'''


@pytest.mark.parametrize("module,what", [("asyncio", "raise ValueError"),
                                         ("asyncio", "raise KeyboardInterrupt"),
                                         ("hashlib", "raise ImportError"),
                                         ("hashlib", "raise KeyboardInterrupt")],
                         ids=["first-import-raises", "first-import-interrupted",
                              "later-import-raises", "later-import-interrupted"])
def test_a_failure_or_an_interruption_during_an_import_prints_one_fixed_line(tmp_path, module,
                                                                            what):
    """[2] (METHOD 1): a planted standard-library module below the guard
    raises, or is interrupted (KeyboardInterrupt, as SIGINT gives), while the
    program imports it: exactly `failed (import)` on standard output, nothing
    on standard error, the planted text and path nowhere."""
    plant = tmp_path / "plant"
    plant.mkdir()
    (plant / (module + ".py")).write_text(_PLANT.format(what=what, token=TOKEN), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(plant))
    p = subprocess.run([sys.executable, "-B", rc.__file__, "--cohort", "--days", "5"],
                       cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=300)
    assert (p.stdout, p.stderr, p.returncode) == ("failed (import)\n", "", rc.EXIT_FAILED)
    # control: the plant is imported by the program (a program that does not
    # import it would print a refusal or a run, not this line)
    assert TOKEN not in p.stdout + p.stderr and str(plant) not in p.stdout + p.stderr


def test_the_guard_stands_above_every_import():
    """[2]: the module's first import is `sys`; every other import statement
    at the top level is inside the one try that the guard's handler holds."""
    tree = ast.parse(open(rc.__file__, encoding="utf-8").read())
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert [a.name for n in top for a in n.names] == ["sys"]
    tries = [n for n in tree.body if isinstance(n, ast.Try)]
    assert len(tries) == 1
    guard_if = [n for n in tree.body if isinstance(n, ast.If) and n.lineno < tries[0].lineno]
    assert guard_if and tries[0].handlers[0].type.id == "BaseException"


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
    assert code == rc.CALIBRATE_EXIT_USAGE and out.out == "refused (path pointer)\n" and out.err == ""
    assert _beneath(seen, pointer) == []
    # control of the recorder: a lookup the tool does make is seen
    missing = os.path.join(root, "rules-" + HEX_REV)
    seen2 = []
    with recording_lookups(seen2):
        code = call_main(["--revision", missing, "--days", "5"])
    assert code == rc.CALIBRATE_EXIT_USAGE and capsys.readouterr().out == "refused (path missing)\n"
    assert ("lstat", missing) in [(n, p) for n, p in seen2 if isinstance(p, str)]


@pytest.mark.parametrize("name,word", [
    ("current", "pointer"), ("rules-none", "pointer"), ("rules-0123456789a", "name"),
    ("rules-0123456789abc", "name"), ("rules-0123456789AB", "name"),
    ("rules-0123456789a\u0663", "name"), ("rules0123456789ab", "name")])
def test_a_pointer_or_a_malformed_name_is_refused_before_loading(rooted, no_db, capsys, name,
                                                                 word):
    path, _rs = rooted
    code, out = _run_main(capsys, os.path.join(os.path.dirname(path), name))
    assert code == rc.CALIBRATE_EXIT_USAGE and out == "refused (path %s)\n" % word
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
    assert code == rc.CALIBRATE_EXIT_USAGE and out == "refused (path pointer)\n" and no_db == []


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
    assert code == rc.CALIBRATE_EXIT_USAGE and out == "refused (path link)\n" and no_db == []


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
    assert code == rc.CALIBRATE_EXIT_USAGE and out == "refused (path link)\n" and no_db == []


# -- calibrate_cli() with a stub walk----------------------------------------------------------------

class _Seen(list):
    """The revisions calibrate_cli() walked, plus what each walk was handed."""


@pytest.fixture
def no_db(monkeypatch):
    """calibrate_cli() stops before any database: the walk is a stub."""
    seen = _Seen()
    seen.calls = []

    async def fake_run(rs, days, deadline_at=None):
        seen.append(rs.rev)
        seen.calls.append({"days": days, "deadline_at": deadline_at,
                           "handler": signal.getsignal(signal.SIGTERM)})
        return rc.Tally(rs).finish()
    monkeypatch.setattr(rc, "_calibrate_run", fake_run)
    return seen


def _run_main(capsys, path, days="23"):
    code = call_main(["--revision", path, "--days", days])
    return code, capsys.readouterr().out


def test_the_named_revision_loads_and_reports(rooted, no_db, capsys):
    path, rs = rooted
    code, out = _run_main(capsys, path)
    assert code == 0 and no_db == [rs.rev]
    assert "rule %s scope=card class=flag evaluated=0 fired=0 errors=0" % ID_DUP in out
    assert _tail(out.splitlines()) == "report end"


def test_days_out_of_range_are_refused(rooted, no_db, capsys):
    path, _rs = rooted
    for days in ("0", "-3", str(cm.WINDOW_DAYS_MAX + 1)):
        code, out = _run_main(capsys, path, days)
        assert code == rc.CALIBRATE_EXIT_USAGE and out == "refused (days)\n"
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
        assert code == rc.CALIBRATE_EXIT_USAGE and capsys.readouterr().out == "refused (deadline)\n"
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


def _m(k, purged=False, rev=None, failed=False, marked=False):
    return k + (purged, rev, failed, marked, False)


NONE_TIED = {"card": 0, "identity": 0, "combat": 0}


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
    assert rc.calibrate_classify(_m(CK, purged=True, rev=GOOD_REV, failed=True), GOOD_REV) == "purged"
    assert rc.calibrate_classify(_m(CK, rev=GOOD_REV, failed=True), GOOD_REV) == "evaluated"
    assert rc.calibrate_classify(_m(CK, rev="0" * 12, failed=True), GOOD_REV) == "failed"
    assert rc.calibrate_classify(_m(CK, rev="0" * 12), GOOD_REV) == "waiting"
    assert rc.calibrate_classify(_m(CK), GOOD_REV) == "waiting"
    assert rc.calibrate_classify(_m(CK, rev=None), None) == "waiting"


def test_the_cohort_read_binds_t_and_its_utc_cutoff_and_returns_its_text():
    """The driver refuses a text value for a timestamptz parameter, so T is
    bound as the aware UTC instant its text names, the cutoff as T less the
    days in UTC; the text is what is printed. Tied rows are counted apart."""
    seen = []
    tied_row = ("k", "lo", "hi", False, None, False, False, True)

    class Db:
        async def execute(self, stmt, b=None):
            seen.append(b)
            return FakeResult([dict(enumerate(tied_row))])
    at, members, ambiguous = run(rc.read_cohort(Db(), 29, GOOD_AT, GOOD_REV))
    assert at == GOOD_AT and members == {d: [] for d in rc.DOMAINS}
    assert ambiguous == {d: 1 for d in rc.DOMAINS}
    t = datetime(2026, 3, 5, 10, 20, 30, tzinfo=timezone.utc)
    assert [b["at"] for b in seen] == [t] * 3
    assert [b["cut"] for b in seen] == [t - timedelta(days=29)] * 3
    assert all(b["rev"] == GOOD_REV for b in seen)


def test_the_cohort_report_lines_are_fixed_and_name_no_member():
    members = {"card": [_m(CK), _m(CK2, purged=True)], "identity": [_m(CK3, rev=GOOD_REV)],
               "combat": [_m(CK3)]}
    tied = {"card": 2, "identity": 0, "combat": 1}
    dig = rc.cohort_digest(members)
    lines = rc.render_cohort(GOOD_AT, 29, members, tied)
    assert lines == ["cohort at %s days 29: members 4 (card 2, identity 1, combat 1); ambiguous 3 "
                     "(card 2, identity 0, combat 1), not members; digest %s" % (GOOD_AT, dig),
                     "report end"]
    check = rc.render_check(GOOD_REV, GOOD_AT, members, tied)
    assert check == [
        "cohort check rev %s at %s: members 4; evaluated 1; waiting 2; purged 1; failed 0 "
        "(card only); ambiguous 3; complete no" % (GOOD_REV, GOOD_AT),
        "cohort card members 2 evaluated 0 waiting 1 purged 1 failed 0",
        "cohort identity members 1 evaluated 1 waiting 0 purged 0 failed not available",
        "cohort combat members 1 evaluated 0 waiting 1 purged 0 failed not available; "
        "derive marks without a revision 0",
        "report end"]
    done = {"card": [_m(CK2, purged=True)], "identity": [_m(CK3, rev=GOOD_REV)], "combat": []}
    assert rc.render_check(GOOD_REV, GOOD_AT, done, NONE_TIED)[0].endswith("complete yes")
    out = "\n".join(lines + check)
    for part in CK + CK2 + CK3 + ("Q7Z", "c0e0"):
        assert part not in out, part


def test_a_failure_counts_only_where_the_row_ties_it_to_the_revision():
    """[12]: planted rows of each kind. Card: a fault under the revision is
    failed. Identity: no failure evidence, `not available`, the member waits.
    Combat: a derive mark without a revision is counted apart and the member
    waits; per-seat fault lists are diagnostics (the SQL's `failed` for
    combat is false, read live). Nothing reads as complete while a member of
    a domain without failure evidence is unevaluated."""
    members = {"card": [_m(CK, failed=True), _m(CK2)], "identity": [_m(CK3)],
               "combat": [_m(CK, marked=True), _m(CK2)]}
    check = rc.render_check(GOOD_REV, GOOD_AT, members, NONE_TIED)
    assert check[0] == ("cohort check rev %s at %s: members 5; evaluated 0; waiting 4; purged 0; "
                        "failed 1 (card only); ambiguous 0; complete no" % (GOOD_REV, GOOD_AT))
    assert check[1] == "cohort card members 2 evaluated 0 waiting 1 purged 0 failed 1"
    assert check[2] == "cohort identity members 1 evaluated 0 waiting 1 purged 0 failed not available"
    assert check[3] == ("cohort combat members 2 evaluated 0 waiting 2 purged 0 failed not available; "
                        "derive marks without a revision 1")
    assert rc.FAILURE_RECORDED == {"card": True, "identity": False, "combat": False}
    flat = {d: " ".join(rc.cohort_sql(d).split()) for d in rc.DOMAINS}
    assert "g.derive_fault IS NOT NULL AND g.fault_rev = CAST(:rev AS varchar)" in flat["card"]
    assert "false AS failed" in flat["identity"] and "false AS failed" in flat["combat"]
    assert "((g.record_faults -> 'derive') IS NOT NULL) AS marked" in flat["combat"]


# -- the database (live) ----------------------------------------------------------------------
#
# ONE planting, in one case schema (one pair of synthetic players):
#   card     C1  one record, recent canonical match                      -> walked
#            C6  [6] two records naming two matches of the pair: the OLD
#                one (outside the walk's days) is canonical, the other
#                recent                                                  -> outside
#            C7  [7] an attached retained record and a stray record
#                (another attach key, no match) whose lists are purged   -> walked
#            CT  [10] two records naming two matches that ended at the
#                same instant                                            -> ambiguous
#            KE KW KP KF KO  cohort-only games (canonical match 20 days
#                old, outside the walk): a games row evaluated under
#                COH_REV, none, purged after T, a derive fault under
#                COH_REV, a derive fault under another revision
#            DST [11] a game at a fixed T across a clock change (March 2026)
#   identity I1  one record with a clock sample, recent match            -> walked
#   combat   B1  the a24 pair of records, recent match                   -> walked
#            BD BF  cohort-only games: fault lists only (diagnostics), a
#                derive mark (no revision recorded)

ST_A, ST_B = "1000000000007301", "1000000000007302"
WALK_DAYS = 9
COH_DAYS = 29
COH_REV = "7e5ca0c0ffee"
OTHER_REV = "0e5ca0c0ffee"
DST_AT = "2026-03-08T12:00:00Z"        # in America/Los_Angeles a day after a clock change
LK = {n: "calibr2_%s_q7z" % n for n in ("c1", "c6", "c7", "ct", "i1", "b1", "ke", "kw", "kp", "kf",
                                        "ko", "bd", "bf", "dst")}
LR = {n: "calibroom_r2_%s_q7z" % n for n in ("c1", "c6old", "c6new", "c7", "c7stray", "ct1", "ct2",
                                             "i1", "b1", "ke", "kw", "kp", "kf", "ko", "bd", "bf",
                                             "dst")}


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

        async def card(key, room, seat, other, purged=None, received=None):
            await db.execute(text(
                "INSERT INTO card_evidence (stable_game_key, attach_key, seat_player_id, "
                "  other_player_id, pool_digest, deal_profile, payload, payload_sha256, "
                "  received_at, lists_purged_at) "
                "VALUES (:k, :a, :s, :o, :d, :dp, CAST(:p AS jsonb), :h, :r, :lp)"),
                {"k": key, "a": room, "s": seat, "o": other, "d": dump["digest"], "dp": PROFILE,
                 "p": card_rec, "h": _sha(card_rec), "r": received or rx, "lp": purged})

        dst_end = datetime(2026, 3, 7, 12, 30, tzinfo=timezone.utc)   # inside T - 1 day in UTC only
        for room, ended in (("c1", recent), ("c6old", old), ("c6new", recent), ("c7", recent),
                            ("ct1", recent), ("ct2", recent),
                            ("i1", recent), ("b1", recent), ("ke", cohort_end), ("kw", cohort_end),
                            ("kp", cohort_end), ("kf", cohort_end), ("ko", cohort_end),
                            ("bd", cohort_end), ("bf", cohort_end), ("dst", dst_end)):
            await match(LR[room], ended)
        await card(LK["c1"], LR["c1"], a, b)
        await card(LK["c6"], LR["c6old"], a, b)
        await card(LK["c6"], LR["c6new"], b, a)
        await card(LK["c7"], LR["c7"], a, b)
        await card(LK["c7"], LR["c7stray"], b, a, purged=now - timedelta(hours=1))
        await card(LK["ct"], LR["ct1"], a, b)
        await card(LK["ct"], LR["ct2"], b, a)
        for n in ("ke", "kw", "kp", "kf", "ko"):
            await card(LK[n], LR[n], a, b)
        await card(LK["dst"], LR["dst"], a, b, received=datetime(2026, 3, 7, 13, 0, tzinfo=timezone.utc))
        await db.execute(text(
            "INSERT INTO card_games (stable_game_key, pair_lo, pair_hi, evaluated_rev, derive_fault, "
            "  fault_rev) "
            "VALUES (:k, :lo, :hi, :r, NULL, NULL), (:k2, :lo, :hi, NULL, 'planted_fault', :r), "
            "       (:k3, :lo, :hi, NULL, 'planted_fault', :o)"),
            {"k": LK["ke"], "k2": LK["kf"], "k3": LK["ko"], "lo": lo, "hi": hi, "r": COH_REV,
             "o": OTHER_REV})
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
        for key, room, seat, other, rec in ((LK["b1"], LR["b1"], a, b, owner),
                                            (LK["b1"], LR["b1"], b, a, meas),
                                            (LK["bd"], LR["bd"], a, b, owner),
                                            (LK["bf"], LR["bf"], a, b, owner)):
            p = json.dumps(rec)
            await db.execute(text(
                "INSERT INTO combat_evidence (stable_game_key, attach_key, seat_player_id, "
                "  other_player_id, payload, payload_sha256, received_at) "
                "VALUES (:k, :a, :s, :o, CAST(:p AS jsonb), :h, :r)"),
                {"k": key, "a": room, "s": seat, "o": other, "p": p, "h": _sha(p), "r": rx})
        # [12]: per-seat fault lists alone are diagnostics; a derive mark names no revision
        diag = json.dumps({str(a): {"own_gun": [], "other_gun": [], "sections": []}})
        derive = json.dumps({str(a): {"own_gun": [], "other_gun": [], "sections": []},
                             "derive": "ValueError"})
        await db.execute(text(
            "INSERT INTO combat_games (stable_game_key, pair_lo, pair_hi, record_faults) "
            "VALUES (:k, :lo, :hi, CAST(:f AS jsonb)), (:k2, :lo, :hi, CAST(:f2 AS jsonb))"),
            {"k": LK["bd"], "k2": LK["bf"], "lo": lo, "hi": hi, "f": diag, "f2": derive})
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
    engine, factory = rc.calibrate_session_factory(60, url=live.url, recorder=log,
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
        engine, factory = rc.calibrate_session_factory(60, url=live.url, extra_settings=live.settings)
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


def _type_lookup(s):
    """The driver's look-up of one type by name (asyncpg introspection.TYPE_BY_NAME)."""
    flat = " ".join(s.split())
    return (flat.startswith("SELECT t.oid, t.typelem AS elemtype, t.typtype AS kind FROM "
                            "pg_catalog.pg_type AS t")
            and "t.typname = $1 AND ns.nspname = $2" in flat)


def test_live_every_statement_the_connection_sent_is_an_approved_shape(walked):
    """[4], [5]: the recorder sits at the driver's protocol from the moment
    the connection is established, so it lists every statement after that:
    the dialect's codec set-up, its first-connect reads, the driver's type
    introspection, the transaction and the tool's reads. The order before the
    first BEGIN is READ, not assumed: whatever comes before it is the
    driver's type look-up by name and nothing else (asyncpg 0.29.0: the json
    and jsonb look-ups; 0.31.0: none); the versions and that order are
    printed (-rP shows them). Each statement is an approved shape; none
    changes a setting."""
    import asyncpg
    import sqlalchemy
    log = walked.log
    assert log, "the recorder saw nothing"
    first_begin = next(i for i, s in enumerate(log) if s.upper().startswith("BEGIN"))
    before = log[:first_begin]
    print("DRIVER-ORDER asyncpg %s sqlalchemy %s: %d statement(s) before the first BEGIN: %s"
          % (asyncpg.__version__, sqlalchemy.__version__, len(before),
             ["type look-up" if _type_lookup(s) else s[:40] for s in before]))
    assert all(_type_lookup(s) for s in before), [s[:80] for s in before]
    assert len(before) <= 2
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
    """The live walk's whole report equals the report of the same walk over
    the same records handed in directly (two card games of the one record on
    one day, the outside game skipped by its word, the tied game ambiguous,
    one identity game, one combat game); and the cycle rule fires once."""
    _path, rs = planted
    card, ident, cmb = run(_fake_items(rs))
    expected = run(rc.calibrate_walk(rs, FakeFetch({"card": [card, ("skip", "outside"), card, rc.AMBIGUOUS],
                                          "identity": [ident], "combat": [cmb]})))
    tally = walked.tally
    assert tally.cut is None and not tally.abandoned
    assert rc.calibrate_render(tally) == rc.calibrate_render(expected)
    assert counts(tally)[ID_CMB] == (1, 1, 0)
    assert counts(tally)[ID_DUP][0] == 2 and counts(tally)[ID_IDB][0] == 1
    assert counts(tally)[ID_WIN][0] == tally.windows == tally.windows_total
    assert rc.calibrate_render(tally)[0] == ("run whole: games read 6 of 6 (card 4 of 4, identity 1 of 1, "
                                   "combat 1 of 1)")


def test_live_a_game_whose_canonical_match_is_outside_the_days_is_counted_outside(walked):
    """C6 is admitted through its recent attachment; its canonical match is
    the old one, outside the days: not evaluated, counted `outside`."""
    t = walked.tally
    assert t.totals["card"] == 4
    assert t.domains["card"] == {"walked": 2, "skipped": {"outside": 1}}


def test_live_a_game_whose_earliest_matches_tie_is_ambiguous_and_not_counted(walked):
    """[10]: CT's two records name two matches that ended at the same
    instant: the tool does not choose; the game is on the ambiguous line."""
    t = walked.tally
    assert t.ambiguous == {"card": 1, "identity": 0, "combat": 0}
    assert ("ambiguous (tied earliest match, not counted): card 1, identity 0, combat 0"
            in rc.calibrate_render(t))


def test_live_the_selection_reads_a_tied_old_canonical_match_as_outside_and_not_a_game_without_a_recent_match(
        live, planted, walked):
    """[10] (ORDER-R3-FIX-3 G1), through the tool's own statement and walk on
    the database. Planted inside one transaction that is rolled back: game TO,
    whose two OLDEST named matches end at the same instant 15 days ago (before
    the cutoff: one room holding a match of each player order, named by the
    first seat's record) and whose third named match ended 2 hours ago (after
    it, named by the second seat's record); game NO, whose only named match
    ended 15 days ago. The selection gives
    ONE row for TO (`recent` false, `tied` true) and none for NO; the walk
    over the same transaction counts TO once under `outside`, not on the
    ambiguous line, and NO in no count: the games read grow by one."""
    import test_title_ladder_hooks_live as lh
    _path, rs = planted
    a, b = live.plan.a, live.plan.b
    key = {"to": "calibr3_to_q7z", "no": "calibr3_no_q7z"}
    room = {n: "calibroom_r3_%s_q7z" % n for n in ("to1", "to3", "no1")}

    async def go():
        async with live.sm() as db:
            now = (await db.execute(text("SELECT now()"))).scalar()
            old, recent = now - timedelta(days=15), now - timedelta(hours=2)
            for r, ended, p1, p2 in (("to1", old, a, b), ("to1", old, b, a), ("to3", recent, a, b),
                                     ("no1", old, a, b)):
                row = await lh._insert(db, "matches", {
                    "player1_id": p1, "player2_id": p2, "photon_room_id": room[r], "is_ranked": True,
                    "p1_rounds_won": 5, "p2_rounds_won": 3, "winner_id": a, "reported_by": a})
                await db.execute(text("UPDATE matches SET ended_at = :e, created_at = :e WHERE id = :i"),
                                 {"e": ended, "i": row["id"]})
            for k, r, s, o in (("to", "to1", a, b), ("to", "to3", b, a), ("no", "no1", a, b)):
                await db.execute(text(
                    "INSERT INTO card_evidence (stable_game_key, attach_key, seat_player_id, "
                    "  other_player_id, pool_digest, deal_profile, payload, payload_sha256, received_at) "
                    "SELECT :k, :r, :s, :o, pool_digest, deal_profile, payload, payload_sha256, received_at "
                    "  FROM card_evidence WHERE stable_game_key = :src AND attach_key = :srcr"),
                    {"k": key[k], "r": room[r], "s": s, "o": o, "src": LK["c1"], "srcr": LR["c1"]})
            rows = (await db.execute(text(rc._GAMES_SQL.format(t=rc._TABLES["card"])), {
                "cut": now - timedelta(days=WALK_DAYS), "lag": rc._LAGS["card"]})).all()
            mine = {r[0]: (r[4], r[5]) for r in rows if r[0] in key.values()}

            @contextlib.asynccontextmanager
            async def same():
                yield db
            tally = await rc.walk_db(rs, same, WALK_DAYS, time.monotonic() + 120)
        return mine, tally
    mine, tally = live.run(go())
    assert mine == {key["to"]: (False, True)}, mine
    base = walked.tally
    assert tally.totals["card"] == base.totals["card"] + 1
    assert tally.domains["card"]["skipped"].get("outside", 0) == \
        base.domains["card"]["skipped"].get("outside", 0) + 1
    assert tally.domains["card"]["walked"] == base.domains["card"]["walked"]
    assert tally.ambiguous == base.ambiguous


def test_live_a_purged_stray_record_does_not_remove_a_game_the_passes_evaluate(walked):
    """C7's attached record is retained; its stray record (another attach
    key) has purged lists. The game is selected and evaluated."""
    t = walked.tally
    assert t.totals["card"] == 4 and t.domains["card"]["walked"] == 2
    assert "purged" not in t.domains["card"]["skipped"]


def test_live_the_connection_takes_nothing_from_the_drivers_environment(live, monkeypatch):
    """[5] (ORDER-R3-FIX-2 F3, ORDER-R3-FIX-3 G2): a target session attribute
    of `standby` and a TLS mode of `require` planted in the process
    environment; the tool's connection to the local server opens. With the
    recorder handed to the tool's connect, the connect returns with NO
    statement recorded, and the first statement sent afterwards is the first
    one recorded. Where the recorder sits is held by
    test_the_recorder_is_installed_only_in_the_constructor_of_the_connection_class;
    the target attribute alone by
    test_live_a_standby_target_attribute_in_the_environment_does_not_stop_the_tools_connection."""
    from sqlalchemy.engine import make_url
    monkeypatch.setenv("PGTARGETSESSIONATTRS", "standby")
    monkeypatch.setenv("PGSSLMODE", "require")
    log, direct = [], []

    async def go():
        engine, factory = rc.calibrate_session_factory(60, url=live.url, recorder=log,
                                             extra_settings=live.settings)
        try:
            async with rc.read_only(factory) as db:
                one = (await db.execute(text("SELECT 1"))).scalar()
        finally:
            await engine.dispose()
        args = make_url(live.url).translate_connect_args(username="user")
        conn = await rc._connect(args, dict(rc.server_settings(60), **live.settings), recorder=direct)
        try:
            during = list(direct)
            await conn.fetchval("SELECT 2")
        finally:
            await conn.close()
        return one, during
    one, during = live.run(go())
    assert one == 1
    assert during == [], during
    assert direct == ["SELECT 2"], direct
    assert log
    assert os.environ["PGTARGETSESSIONATTRS"] == "standby"     # put back after the connect


def test_live_a_standby_target_attribute_in_the_environment_does_not_stop_the_tools_connection(
        live, monkeypatch):
    """[5] (ORDER-R3-FIX-3 G2 b): only PGTARGETSESSIONATTRS=standby planted.
    The local server is a primary and reports in_hot_standby off. The
    driver's own connect, handed the same parameters with that environment,
    refuses it (the observable differs); the tool's connect, which takes the
    variable out while the driver connects, opens it."""
    import asyncpg
    from sqlalchemy.engine import make_url
    monkeypatch.setenv("PGTARGETSESSIONATTRS", "standby")
    args = make_url(live.url).translate_connect_args(username="user")
    settings = dict(rc.server_settings(60), **live.settings)

    async def go():
        try:
            bare = await asyncpg.connect(**args, server_settings=settings)
        except asyncpg.exceptions.TargetServerAttributeNotMatched:
            driver = "refused"
        else:
            await bare.close()
            driver = "opened"
        conn = await rc._connect(args, settings)
        try:
            return driver, conn.get_settings().in_hot_standby, await conn.fetchval("SELECT 1")
        finally:
            await conn.close()
    assert live.run(go()) == ("refused", "off", 1)


def test_live_a_statement_ends_by_its_statement_timeout(live):
    """[9] (METHOD 2): with a deadline of 1 s the startup statement_timeout is
    1 s, so a statement that would run 4 s is ended by the server at about
    1 s, with no setting changed after startup."""
    from sqlalchemy.exc import DBAPIError

    async def go():
        engine, factory = rc.calibrate_session_factory(1, url=live.url, extra_settings=live.settings)
        try:
            async with rc.read_only(factory) as db:
                t0 = time.monotonic()
                try:
                    await db.execute(text("SELECT pg_sleep(4)"))
                    return "finished", time.monotonic() - t0
                except DBAPIError as e:
                    return str(e).split("\n")[0], time.monotonic() - t0
        finally:
            await engine.dispose()
    word, elapsed = live.run(go())
    assert "statement timeout" in word, word
    assert elapsed < 3, elapsed


def test_live_a_statement_started_late_has_its_whole_statement_timeout(live):
    """[9] (ORDER-R3-FIX-2 F4), the sentence of the module text: a deadline of
    3 s gives a statement timeout of 3 s; the session's connection is opened,
    then 2.2 s of the 3 pass (most of the run's time gone), then a statement
    that would run 8 s starts. The server ends it by ITS OWN statement
    timeout, counted from its own start: at about 3 s after it started (not
    at the 0.8 s left of the deadline), so it ends past the deadline and
    within the deadline plus one statement timeout."""
    from sqlalchemy.exc import DBAPIError

    async def go():
        t_built = time.monotonic()
        engine, factory = rc.calibrate_session_factory(3, url=live.url, extra_settings=live.settings)
        try:
            async with rc.read_only(factory) as db:
                assert (await db.execute(text("SELECT 1"))).scalar() == 1
                await asyncio.sleep(max(0.0, 2.2 - (time.monotonic() - t_built)))
                t0 = time.monotonic()
                try:
                    await db.execute(text("SELECT pg_sleep(8)"))
                    word = "finished"
                except DBAPIError as e:
                    word = str(e).split("\n")[0]
                t1 = time.monotonic()
                return word, t1 - t0, t1 - t_built
        finally:
            await engine.dispose()
    word, own, total = live.run(go())
    assert "statement timeout" in word, word
    assert 2.6 <= own < 4.5, own
    assert 3 < total < 3 + 3 + 1, total


def test_live_the_cohort_cutoff_does_not_move_with_the_session_time_zone(live, monkeypatch, capfd):
    """[11]: T = 2026-03-08T12:00:00Z and one day, with the session's TimeZone
    America/Los_Angeles (a clock change on 2026-03-08). The UTC cutoff is
    2026-03-07T12:00Z, so the DST game (its match ended 12:30Z) is the one
    member; day arithmetic in the session's zone would put the cutoff at
    13:00Z and leave it out (the check then refuses: cohort differs)."""
    real = REAL_SESSION_FACTORY
    zone = dict(live.settings, TimeZone="America/Los_Angeles")
    monkeypatch.setattr(rc, "calibrate_session_factory", lambda d, **k: real(d, url=live.url,
                                                                   extra_settings=zone))
    lo, hi = sorted([live.plan.a, live.plan.b])
    digest = rc.cohort_digest({"card": [(LK["dst"], lo, hi)], "identity": [], "combat": []})
    capfd.readouterr()
    code = call_main(["--cohort-check", "--rev", COH_REV, "--at", DST_AT, "--digest", digest,
                      "--days", "1"])
    got = capfd.readouterr()
    assert code == 0 and got.err == "", got.out
    assert got.out.splitlines()[0] == (
        "cohort check rev %s at %s: members 1; evaluated 0; waiting 1; purged 0; failed 0 "
        "(card only); ambiguous 0; complete no" % (COH_REV, DST_AT))


def test_live_the_report_names_no_identifier(walked, live):
    out = "\n".join(rc.calibrate_render(walked.tally))
    for part in list(LK.values()) + list(LR.values()) + list(live.plan.ids) + ["q7z", ST_A, ST_B]:
        assert part not in out, part


def test_live_cohort_then_cohort_check(live, monkeypatch, capfd):
    """[13] (design section g): the cohort read prints T, the member counts
    and one digest; the check with that T and digest, after one member's
    attached record is purged, counts each member's state; a changed digest
    is refused."""
    real = REAL_SESSION_FACTORY
    monkeypatch.setattr(rc, "calibrate_session_factory",
                        lambda d, **k: real(d, url=live.url, extra_settings=live.settings))
    capfd.readouterr()
    code = call_main(["--cohort", "--days", str(COH_DAYS)])
    got = capfd.readouterr()
    assert code == 0 and got.err == "", got.out
    lines = got.out.splitlines()
    m = re.fullmatch(r"cohort at (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ) days 29: members 12 "
                     r"\(card 8, identity 1, combat 3\); ambiguous 1 \(card 1, identity 0, "
                     r"combat 0\), not members; digest ([0-9a-f]{64})", lines[0])
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
    # [12]: KF's fault is under COH_REV (failed), KO's under another revision
    # (waiting); identity records no failure; combat's BD (fault lists only)
    # waits, BF's derive mark is counted apart and it waits
    assert got2.out.splitlines() == [
        "cohort check rev %s at %s: members 12; evaluated 1; waiting 9; purged 1; failed 1 "
        "(card only); ambiguous 1; complete no" % (COH_REV, at),
        "cohort card members 8 evaluated 1 waiting 5 purged 1 failed 1",
        "cohort identity members 1 evaluated 0 waiting 1 purged 0 failed not available",
        "cohort combat members 3 evaluated 0 waiting 3 purged 0 failed not available; "
        "derive marks without a revision 1",
        "report end"]
    changed = ("0" if digest[0] != "0" else "1") + digest[1:]
    code = call_main(["--cohort-check", "--rev", COH_REV, "--at", at, "--digest", changed,
                      "--days", str(COH_DAYS)])
    got3 = capfd.readouterr()
    assert code == rc.EXIT_REFUSED and got3.out == "refused (cohort differs)\n" and got3.err == ""
    out = got.out + got2.out + got3.out
    for part in list(LK.values()) + list(LR.values()) + list(live.plan.ids) + ["q7z", ST_A, ST_B]:
        assert part not in out, part
