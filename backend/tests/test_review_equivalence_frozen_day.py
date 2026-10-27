"""The private equivalence suite's frozen sitting identities are relative to
the run (fix pass 4b), proven WITHOUT the private suite: these tests run on
synthetic identities only.

A frozen sitting identity is `lo|hi|@N` (N days before the run's UTC today);
test_review_equivalence thaws it with the same today its labels use, and
refuses a literal calendar date by name. The same mutation check passes under
two different todays, a literal date is refused, frozen order is free, and a
fixture row's membership in a population is judged independent of the time of
day the run starts. Fix pass 5 (LOW 1): that judgement covers every population
the armed run executes -- the base rules, the old worker, the literal and every
compiled sitting mutant -- each shown refusing a row dependent under it alone.
"""

import datetime
import os
import re
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


HOUR_S = 3600


@pytest.mark.parametrize("days_ago, minute, horizon, lag, want", [
    (1, 0, 7, 600, False),          # inside, more than a day from both edges: held all day
    (3, 59, 7, 600, False),
    (9, 0, 7, 600, False),          # beyond the horizon all day: never held
    (0, 0, 7, 600, True),           # today: held only once its end plus the lag has passed
    (7, 0, 7, 600, True),           # the horizon day: held only until its end leaves the horizon
    (6, 0, 7, 600, False),          # a day inside the horizon edge: held all day
    (0, 0, 7, 11 * HOUR_S, True),   # a lag ending late in the day
    (0, 0, 7, 13 * HOUR_S, False),  # a lag past the day's end: never held today
])
def test_a_row_is_judged_by_whether_the_time_of_day_moves_it(days_ago, minute, horizon, lag, want):
    assert te._time_of_day_dependent(days_ago, minute, horizon, lag) is want


def test_the_judgement_matches_a_brute_force_over_the_day():
    """The closed form agrees with checking every minute of a day."""
    for days_ago in range(0, 10):
        for minute in (0, 30, 59):
            for horizon in (1, 2, 7):
                for lag in (0, 600, 13 * HOUR_S):
                    t = -days_ago * te.DAY_S + te.ROW_HOUR * HOUR_S + 60 * minute
                    held = {t > n - horizon * te.DAY_S and t <= n - lag
                            for n in range(0, te.DAY_S, 60)}
                    assert te._time_of_day_dependent(days_ago, minute, horizon, lag) is (len(held) == 2), \
                        (days_ago, minute, horizon, lag)


def test_the_population_edges_are_read_from_the_population_text():
    """The horizon is the first bind of the population text, the lag the second."""
    names = re.findall(r":(\w+)", te.rr.rm.POP_BASE)
    assert len(names) == 2
    assert te._population_edges(dict(zip(names, (5, 7)))) == (5, 7)
    assert te._population_edges(dict(zip(names, (8, 9)))) == (8, 9)


# -- fix pass 5, LOW 1: every population the run executes is checked ------------------
# Synthetic stand-ins for each population the armed run executes: the base
# revision's statement, the old worker's statement and the tuning tool's literal
# (values written in), and a compiled sitting mutant. A row dependent on the time
# of day under ONE of them only must be refused under that one.

def _written_in(horizon, lag):
    """The population text with its values written in, as both literals write it."""
    names = re.findall(r":(\w+)", te.rr.rm.POP_BASE)
    sql = te.rr.rm.POP_BASE
    for n, v in zip(names, (horizon, lag)):
        sql = sql.replace(":" + n + " ", "%d " % v)
    return "SELECT 1 FROM matches m WHERE " + sql + " UNION ALL SELECT 1 FROM matches m WHERE " + sql


class _SyntheticRules:
    """A ruleset stand-in: sitting rules whose statements bind (horizon, lag)."""

    def __init__(self, edges):
        self.sitting_rules = [type("R", (), {"id": "base_rule_%d" % i})() for i in range(len(edges))]
        self._edges = dict(zip((r.id for r in self.sitting_rules), edges))

    def rule(self, rid):
        return next(r for r in self.sitting_rules if r.id == rid)

    def sitting_statement(self, rule):
        names = re.findall(r":(\w+)", te.rr.rm.POP_BASE)
        return "statement", dict(zip(names, self._edges[rule.id]))


def test_low1_the_text_edges_are_read_from_a_written_in_statement():
    assert te._text_edges(_written_in(60, 120)) == [(60, 120)]
    with pytest.raises(AssertionError):
        te._text_edges("SELECT 1 FROM matches m")              # no population: refused, not skipped


@pytest.mark.parametrize("where", ["base", "old", "literal", "mutant"])
def test_low1_a_row_dependent_under_one_executed_population_only_is_refused(where):
    """Each population is (7 days, 600 s) except the one under test, which is
    (3 days, 600 s): a row 3 days back leaves THAT population during the day."""
    edges = {w: (3, 600) if w == where else (7, 600) for w in ("base", "old", "literal", "mutant")}
    rs = _SyntheticRules([edges["base"]])
    mrs = _SyntheticRules([edges["mutant"]])
    pops = te._executed_populations(rs, [("m1", mrs, mrs.sitting_rules[0])],
                                    {"kind_a": _written_in(*edges["old"])},
                                    {"lit_a": _written_in(*edges["literal"])})
    assert sorted({p[0].split(":")[0] for p in pops}) == ["base", "literal", "mutant", "old"]
    rows = [{"days_ago": 3, "minute": 0}, {"days_ago": 1, "minute": 0}]
    bad = te._time_of_day_rows(rows, pops)
    assert [lab.split(":")[0] for lab, i in bad] == [where] and [i for _l, i in bad] == [0]
    control = te._time_of_day_rows([{"days_ago": 1, "minute": 0}], pops)
    assert control == []
