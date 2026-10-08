"""The private equivalence suite's frozen sitting identities are relative to
the run, proven WITHOUT the private suite: these tests run on synthetic
identities only.

A frozen sitting identity is `lo|hi|@N` (N days before the run's UTC today);
test_review_equivalence thaws it with the same today its labels use, and
refuses a literal calendar date by name. The same mutation check passes under
two different todays, a literal date is refused, and frozen order is free.
"""

import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_review_equivalence as te  # noqa: E402

TODAYS = (datetime.date(2026, 10, 4), datetime.date(2027, 1, 1))
PAIR = ["00000000-0000-0000-0000-00000000000b", "00000000-0000-0000-0000-00000000000a"]


def _lo_hi():
    a, b = sorted(PAIR)
    return a + "|" + b


@pytest.mark.parametrize("today", TODAYS, ids=["frozen_day", "a_later_year"])
def test_a_relative_identity_thaws_against_the_run_today(today):
    for n in (0, 1, 10):
        got = te._thaw_ident("%s|@%d" % (_lo_hi(), n), today)
        assert got == "%s|%s" % (_lo_hi(), today - datetime.timedelta(days=n))
        assert got == te._sitting_ident(PAIR, n, today)          # the labels' own identity


@pytest.mark.parametrize("today", TODAYS, ids=["frozen_day", "a_later_year"])
def test_the_sitting_mutation_check_holds_under_any_today(today):
    """A synthetic sitting mutation: the frozen expectation names @1 and @3;
    the identities computed for `today` match it after the thaw, in any
    frozen order."""
    kind = "k"
    lost = {(te._sitting_ident(PAIR, 1, today), kind), (te._sitting_ident(PAIR, 3, today), kind)}
    m = {"kind": kind, "class": "value", "path": ["x"], "target": "rule", "value": 1,
         "expect": {"lose": [[_lo_hi() + "|@3", kind], [_lo_hi() + "|@1", kind]], "gain": []}}
    te._check_change(te._thaw_expect(m, today), lost, set(), lost, set())
    # control: the same expectation unthawed does not match
    with pytest.raises(AssertionError):
        te._check_change(m, lost, set(), lost, set())
    # control: one day off is caught
    off = {(te._sitting_ident(PAIR, 2, today), kind), (te._sitting_ident(PAIR, 3, today), kind)}
    with pytest.raises(AssertionError):
        te._check_change(te._thaw_expect(m, today), off, set(), off, set())


def test_a_literal_calendar_date_is_refused_by_name():
    m = {"kind": "k", "class": "value", "path": ["x"], "target": "rule", "value": 1,
         "expect": {"lose": [[_lo_hi() + "|2026-10-03", "k"]], "gain": []}}
    with pytest.raises(te.FrozenDayRefused) as e:
        te._thaw_expect(m, TODAYS[0])
    assert "literal calendar date" in str(e.value)


@pytest.mark.parametrize("day", ["@", "@-1", "@01", "@1.5", "1", "@ 1", "today"])
def test_any_other_day_form_is_refused(day):
    with pytest.raises(te.FrozenDayRefused) as e:
        te._thaw_ident(_lo_hi() + "|" + day, TODAYS[0])
    assert "literal calendar date" not in str(e.value)


@pytest.mark.parametrize("ident", ["a|@1", "a|b|c|@1", 7, None])
def test_a_malformed_identity_is_refused(ident):
    with pytest.raises(te.FrozenDayRefused):
        te._thaw_ident(ident, TODAYS[0])


def test_game_expectations_carry_no_day_and_compare_in_any_order():
    """The game form (game name, kind) is compared as frozen; order is free."""
    m = {"kind": "k", "class": "value", "path": ["x"], "target": "rule", "value": 1,
         "expect": {"lose": [["g2", "k"], ["g1", "k"]], "gain": []}}
    lost = {("g1", "k"), ("g2", "k")}
    te._check_change(m, lost, set(), lost, set())
