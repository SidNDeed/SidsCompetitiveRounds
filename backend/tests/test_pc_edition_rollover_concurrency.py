"""The rollover statement under a concurrent schedule edit, measured.

Codex I7-H1: `cur` is materialized from the statement's snapshot, so if an
operator clears or postpones a due edition and commits while the rollover is
blocked on their row lock, `cur` still holds the old due timestamp. Matching the
close on `e.id = cur.id AND e.ended_at IS NULL` alone closes the edition anyway
and mints a successor anchored on the stale value.

The fix repeats the schedule predicates against the LIVE row `e` and carries the
anchor out through `closed.prev_planned`. It relies on PostgreSQL re-evaluating
the UPDATE's own quals against the new row version after the lock wait
(EvalPlanQual).

WHY THIS FILE EXISTS
--------------------
`test_pc_edition_rollover.py` passes 9/9 both before and after that change, and
it is right to: not one of its cases edits a schedule mid-flight, so they show
the fix broke nothing and say nothing about whether it does anything. The
binding assertion elsewhere checks the statement's TEXT SHAPE, which cannot
tell a working fix from an inert one either.

So this measures the behaviour: two connections, a real lock wait, the
operator's edit committed while the rollover is blocked -- and the PRE-FIX
statement run through the identical harness as the control that proves the
harness can distinguish them. Without that control the whole file could pass
against a fix that does nothing, which is precisely the state it exists to rule
out.

Recorded result (PostgreSQL 16.15, 2026-09-18):

    SHIPPED      no contention                rolled, anchor 2027-01-01
    SHIPPED      operator NULLs the schedule  declined, nothing minted
    SHIPPED      operator postpones to future declined, nothing minted
    SHIPPED      operator moves it, still due rolled, anchor 2026-10-01  <- live value
    PRE-FIX      operator NULLs the schedule  rolled, anchor 2027-01-01  <- stale
    PRE-FIX      operator postpones to future rolled, anchor 2027-01-01  <- stale

The fourth row is the positive evidence: the successor's anchor came from the
value committed DURING the wait, so the UPDATE re-read the live row. The last
two are I7-H1 reproduced.

The disposition is FAIL-CLOSED: a postponed edition is left open with nothing
minted, and the next janitor pass re-evaluates from scratch. That is the right
direction, and it is silent -- an operator gets no signal that a pass declined.

RUNNING IT
----------
    PC_EDITION_TEST_PG_DSN="postgresql://postgres@127.0.0.1:5432/pctest" \\
        python -m pytest backend/tests/test_pc_edition_rollover_concurrency.py

Note this file wants a PLAIN DSN (asyncpg connects directly, because the point
is two independent sessions), not the `postgresql+asyncpg://` SQLAlchemy form
the sibling file takes. Both spellings are accepted; the `+asyncpg` is stripped.
"""
import asyncio
import datetime as _dt
import os
import sys

import pytest

try:
    import asyncpg
except ImportError:                                    # pragma: no cover
    asyncpg = None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import main


_GATE = "PC_EDITION_TEST_PG_DSN"

# Names close enough to the real one to be typed by accident. A near miss makes
# every gated test skip and the run exit 0, which reads as a clean pass in any
# summary that reports pass/fail rather than collected count -- how this hole
# was found in the first place.
_NEAR_MISSES = ("PC_TEST_PG_DSN", "PC_EDITION_DSN", "PCTEST_DSN",
                "PC_EDITION_TEST_DSN", "PC_EDITIONS_TEST_PG_DSN")

_DSN = (os.environ.get(_GATE) or "").replace("postgresql+asyncpg://",
                                             "postgresql://")

_needs_pg = pytest.mark.skipif(
    not _DSN or asyncpg is None,
    reason="%s unset; live-Postgres concurrency check" % _GATE)

CHANNEL = "900000000000000001"       # not a real channel id; nothing here posts

_DUE = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
_STILL_DUE = _dt.datetime(2025, 6, 1, tzinfo=_dt.timezone.utc)


def _plus_months(when, months):
    z = when.month - 1 + months
    return when.replace(year=when.year + z // 12, month=z % 12 + 1)


def _first_future_anchor(seed, step_months=4):
    """The first `seed + 4n` strictly after now, computed in Python.

    The statement under test does this in SQL; this walks months, so the
    comparison is a check and not an echo. It replaced a literal 2026-10-01,
    which was the right answer when it was written and becomes the wrong one
    on 1 October -- in a DSN-gated file, so the failure would have surfaced
    to whoever next set the DSN, as a puzzle with no connection to whatever
    they had changed.

    (The same pair lives in test_pc_edition_rollover.py. Duplicated rather
    than imported: a test module importing another test module for a helper
    couples their collection order for four lines of arithmetic.)
    """
    now = _dt.datetime.now(_dt.timezone.utc)
    for n in range(1, 1000):
        cand = _plus_months(seed, step_months * n)
        if cand > now:
            return cand
    raise AssertionError("no future anchor within 1000 steps of %s" % seed)
# RELATIVE. As a literal this stopped being a postponement on
# 2027-06-01, after which "operator postpones it to a future time" would have
# been seeding a time in the past and testing the opposite scenario under the
# old name -- quietly, in a DSN-gated file.
_FUTURE = _dt.datetime.now(_dt.timezone.utc).replace(
    microsecond=0) + _dt.timedelta(days=365 * 3)

_NULL_IT = "UPDATE pc_editions SET ends_at_planned = NULL WHERE id = 1"
_MOVE_IT = "UPDATE pc_editions SET ends_at_planned = $1 WHERE id = 1"

# Exactly the shape 308_player_cards.sql + 332_pc_edition_schedule.sql leave
# behind, including the partial unique index the statement relies on.
SCHEMA = [
    "DROP TABLE IF EXISTS pc_editions",
    "DROP TABLE IF EXISTS pending_channel_posts",
    """CREATE TABLE pc_editions (
        id SERIAL PRIMARY KEY, name TEXT NOT NULL,
        started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        ended_at TIMESTAMPTZ NULL, ends_at_planned TIMESTAMPTZ NULL)""",
    "CREATE UNIQUE INDEX pc_editions_one_active ON pc_editions ((1)) "
    "WHERE ended_at IS NULL",
    "ALTER TABLE pc_editions ADD CONSTRAINT pc_editions_planned_sane "
    "CHECK (ends_at_planned IS NULL OR ends_at_planned > TIMESTAMPTZ '2000-01-01')",
    """CREATE TABLE pending_channel_posts (
        id BIGSERIAL PRIMARY KEY, channel_id TEXT NOT NULL, content TEXT NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), posted_at TIMESTAMPTZ)""",
]


# ── the pre-fix statement, reconstructed from the shipped one ────────────────

def _prefix_sql(sql):
    """Undo exactly the three changes the fix made, and nothing else.

    EVERY substitution asserts its OWN match count. An earlier version of this
    asserted only that the result differed from the input -- which two of the
    three substitutions satisfied on their own, so the first, the only one that
    matters, silently matched nothing (the literal is CRLF, the needle was built
    with LF) and the "control" was a byte-for-byte copy of the fix. It then
    agreed with the fix and reported it inert. An assertion over the RESULT
    cannot stand in for an assertion over each PREDICATE.
    """
    eol = "\r\n" if "\r\n" in sql else "\n"

    def sub(text, old, new, label):
        old, new = old.replace("\n", eol), new.replace("\n", eol)
        n = text.count(old)
        assert n == 1, (
            "pre-fix reconstruction step %r matched %d times, expected 1. The "
            "shipped statement has changed shape; re-derive this control before "
            "trusting anything below it." % (label, n))
        return text.replace(old, new, 1)

    out = sub(sql,
              "         WHERE e.id = cur.id\n"
              "           AND e.ended_at IS NULL\n"
              "           AND e.ends_at_planned IS NOT NULL\n"
              "           AND e.ends_at_planned <= now()\n",
              "         WHERE e.id = cur.id\n"
              "           AND e.ended_at IS NULL\n", "live-row quals")
    out = sub(out, "RETURNING e.id AS prev_id, e.ends_at_planned AS prev_planned",
              "RETURNING e.id AS prev_id", "closed RETURNING")
    # Three references: two executable inside `ins`, plus one in the comment
    # that explains them. Counted rather than assumed.
    n = out.count("closed.prev_planned")
    assert n == 3, ("expected 3 `closed.prev_planned` references (2 executable "
                    "+ 1 in the comment), found %d" % n)
    out = out.replace("closed.prev_planned", "cur.ends_at_planned")
    assert "prev_planned" not in out, "pre-fix reconstruction incomplete"
    # `cur`'s OWN schedule predicate must survive -- only the UPDATE's copy goes
    assert out.count("ends_at_planned <= now()") == 1, (
        "the reconstruction removed cur's own predicate, not the UPDATE's copy")
    return out


# ── the scenario table ──────────────────────────────────────────────────────
# (label, use_prefix, edit_sql, edit_arg, expect_rollover)

_SCENARIOS = [
    ("shipped: no contention",             False, None,     None,       True),
    ("shipped: operator NULLs it",         False, _NULL_IT, None,       False),
    ("shipped: operator postpones it",     False, _MOVE_IT, _FUTURE,    False),
    ("shipped: operator moves, still due", False, _MOVE_IT, _STILL_DUE, True),
    ("PRE-FIX control: NULLs it",          True,  _NULL_IT, None,       True),
    ("PRE-FIX control: postpones it",      True,  _MOVE_IT, _FUTURE,    True),
]


async def _run(sql, edit_sql, edit_arg):
    a = await asyncpg.connect(_DSN)
    b = await asyncpg.connect(_DSN)
    try:
        for stmt in SCHEMA:
            await a.execute(stmt)
        await a.execute("INSERT INTO pc_editions (name, ends_at_planned) "
                        "VALUES ('Edition 1', $1)", _DUE)

        tx = None
        if edit_sql is not None:
            tx = a.transaction()
            await tx.start()
            args = () if edit_arg is None else (edit_arg,)
            await a.execute(edit_sql, *args)           # takes the row lock

        async def roll():
            async with b.transaction():
                return await b.fetchrow(sql.replace(":ch", "$1"), CHANNEL)

        task = asyncio.create_task(roll())
        blocked = None
        if tx is not None:
            await asyncio.sleep(1.0)                   # let B reach the lock
            blocked = not task.done()
            await tx.commit()                          # the operator's edit lands
        row = await asyncio.wait_for(task, timeout=20)

        eds = await a.fetch("SELECT id, ended_at, ends_at_planned "
                            "FROM pc_editions ORDER BY id")
        posts = await a.fetchval("SELECT count(*) FROM pending_channel_posts")
        return {"rolled": row is not None, "blocked": blocked,
                "editions": len(eds), "posts": posts,
                "anchor": eds[-1]["ends_at_planned"] if eds else None}
    finally:
        await a.close()
        await b.close()


@_needs_pg
@pytest.mark.parametrize("label,use_prefix,edit,arg,expect",
                         _SCENARIOS, ids=[s[0] for s in _SCENARIOS])
def test_a_concurrent_schedule_edit_is_honoured(label, use_prefix, edit, arg, expect):
    sql = main._PC_EDITION_ROLLOVER_SQL
    got = asyncio.run(_run(_prefix_sql(sql) if use_prefix else sql, edit, arg))

    if edit is not None:
        assert got["blocked"], (
            "%s: the rollover never blocked on the operator's lock, so this "
            "scenario did not exercise the wait it exists to test." % label)

    assert got["rolled"] is expect, (
        "%s: rolled=%s, expected %s (editions=%d, posts=%d, anchor=%s)"
        % (label, got["rolled"], expect, got["editions"], got["posts"],
           got["anchor"]))

    if not expect:
        assert got["editions"] == 1 and got["posts"] == 0, (
            "%s: declined the rollover but still left %d edition(s) and %d "
            "post(s) behind." % (label, got["editions"], got["posts"]))


@_needs_pg
def test_the_successor_anchor_comes_from_the_value_committed_during_the_wait():
    """The positive evidence, stated on its own because it is the whole point.

    A negative result -- "the bad thing did not happen" -- is also what an inert
    statement produces. This asserts the statement USED the new value: the
    operator moves the schedule to a still-due 2025-06-01 while the rollover is
    blocked, and the successor must be anchored on that, not on the 2026-01-01
    the snapshot holds.
    """
    got = asyncio.run(_run(main._PC_EDITION_ROLLOVER_SQL, _MOVE_IT, _STILL_DUE))
    assert got["blocked"] and got["rolled"]

    # DERIVED from the value the operator committed. A literal here is correct
    # only until the calendar passes it -- the one this replaced, 2026-10-01,
    # had under a fortnight left.
    from_committed = _first_future_anchor(_STILL_DUE)
    from_snapshot = _first_future_anchor(_DUE)
    assert from_committed != from_snapshot, (
        "the two seeds now reach the same anchor, so this test cannot tell "
        "whether the statement read the committed value or its snapshot. "
        "Move _STILL_DUE off the same four-month phase as _DUE.")
    assert got["anchor"] == from_committed, (
        "successor anchored at %s. Expected %s, the first four-month step "
        "past now() from the committed %s. Anchoring at %s would mean the "
        "statement used cur's snapshot value and the fix is inert."
        % (got["anchor"], from_committed, _STILL_DUE.date(), from_snapshot))


# ── guards that run WITHOUT a database ──────────────────────────────────────

def test_the_pre_fix_control_still_reconstructs():
    """Runs with no DSN, and is the reason this file is worth having.

    Every assertion in `_prefix_sql` is a statement about the SHIPPED SQL. If
    someone moves the live-row quals, renames `prev_planned`, or drops one of
    the two executable anchor references, this fails here -- on any machine,
    with no PostgreSQL -- rather than silently producing a control identical to
    the fix.
    """
    out = _prefix_sql(main._PC_EDITION_ROLLOVER_SQL)
    assert out != main._PC_EDITION_ROLLOVER_SQL


def test_the_scenario_table_still_contains_its_controls():
    """A control quietly deleted is the failure this file cannot survive.

    Six scenarios, of which exactly two run the PRE-FIX statement. Without
    those two, every remaining assertion is satisfied by a statement that does
    nothing at all.
    """
    assert len(_SCENARIOS) == 6, "scenario count changed: %d" % len(_SCENARIOS)
    controls = [s for s in _SCENARIOS if s[1]]
    assert len(controls) == 2, (
        "expected 2 PRE-FIX controls, found %d. Without them this file passes "
        "against an inert statement." % len(controls))
    assert any(s[2] is None for s in _SCENARIOS), (
        "the uncontended baseline is gone; nothing proves the statement rolls "
        "over at all.")


def test_a_near_miss_gate_variable_does_not_read_as_a_clean_run():
    """Runs always. The hole this closes was found by walking into it.

    With the gate variable misspelled, every gated test skips and pytest exits
    0 -- indistinguishable from a clean run in any summary that reports
    pass/fail rather than collected count. If something DSN-shaped is set under
    a near-miss name and the real gate is not, that is a misconfiguration, and
    it should be red.
    """
    if os.environ.get(_GATE):
        return
    typo = sorted(v for v in _NEAR_MISSES if os.environ.get(v))
    assert not typo, (
        "%s is set but %s is not, so every concurrency scenario in this file "
        "silently skipped and the run still exited 0. Set %s."
        % (", ".join(typo), _GATE, _GATE))


# ── two janitors at once ────────────────────────────────────────────────────
# Both backend boxes run the same janitor loop, and a pass that overruns its
# interval overlaps the next one. That is a rollover racing a ROLLOVER, which
# nothing above exercises: every scenario there races it against an operator.


def _no_close_guard(sql):
    """Drop ONLY the UPDATE's live-row `ended_at IS NULL` check.

    The single qual that makes a second janitor decline. `cur`'s own copy must
    survive -- removing that instead would change which edition is selected
    rather than whether an already-closed one can be closed twice, and the
    control would be measuring a different defect than the one it names.
    """
    eol = "\r\n" if "\r\n" in sql else "\n"
    old = ("         WHERE e.id = cur.id\n"
           "           AND e.ended_at IS NULL\n").replace("\n", eol)
    n = sql.count(old)
    assert n == 1, (
        "the UPDATE's live-row guard matched %d times, expected 1. The shipped "
        "statement has changed shape; re-derive this control before trusting "
        "the result below it." % n)
    out = sql.replace(old, ("         WHERE e.id = cur.id\n").replace("\n", eol), 1)
    # cur keeps its own; exactly one `ended_at IS NULL` should have gone.
    assert sql.count("ended_at IS NULL") - out.count("ended_at IS NULL") == 1, (
        "removed more than the UPDATE's copy of the guard")
    return out


async def _two_janitors(sql):
    """Janitor 2 starts while janitor 1's rollover is still uncommitted."""
    obs = await asyncpg.connect(_DSN)
    j1 = await asyncpg.connect(_DSN)
    j2 = await asyncpg.connect(_DSN)
    try:
        for stmt in SCHEMA:
            await obs.execute(stmt)
        await obs.execute("INSERT INTO pc_editions (name, ends_at_planned) "
                          "VALUES ('Edition 1', $1)", _DUE)
        stmt = sql.replace(":ch", "$1")

        tx1 = j1.transaction()
        await tx1.start()
        first = await j1.fetchrow(stmt, CHANNEL)      # takes the row lock

        async def second():
            async with j2.transaction():
                return await j2.fetchrow(stmt, CHANNEL)

        task = asyncio.ensure_future(second())
        await asyncio.sleep(1.0)
        blocked = not task.done()
        await tx1.commit()

        error = None
        try:
            row = await asyncio.wait_for(task, timeout=20)
        except Exception as exc:                       # the control lands here
            row, error = None, type(exc).__name__

        eds = await obs.fetch("SELECT id, ended_at FROM pc_editions ORDER BY id")
        return {
            "first_rolled": first is not None,
            "second_rolled": row is not None,
            "blocked": blocked,
            "error": error,
            "editions": len(eds),
            "open": sum(1 for e in eds if e["ended_at"] is None),
            "posts": await obs.fetchval("SELECT count(*) FROM pending_channel_posts"),
        }
    finally:
        for c in (obs, j1, j2):
            await c.close()


@_needs_pg
def test_two_simultaneous_janitors_mint_exactly_one_successor():
    """The second janitor declines cleanly -- it does not error, and does not mint.

    What must NOT happen is two successors, two Discord notices, or an
    exception on an ordinary overlapping pass. Under READ COMMITTED the second
    UPDATE re-evaluates its quals against the row version the first janitor
    committed (EvalPlanQual); `ended_at` is now set, so it matches nothing and
    the whole CTE chain yields no row.

    `error is None` is the load-bearing assertion here, and that is a measured
    claim, not a stylistic one. Run with the guard removed, this scenario
    leaves the IDENTICAL end state -- 2 editions, 1 open, 1 notice -- because
    the duplicate trips the partial unique index and the second janitor's
    transaction rolls back. A version of this test that asserted only the
    counts would have passed against the broken statement. What separates them
    is that the shipped one declines silently and the broken one raises
    (measured: `UniqueViolationError`, PG16.9, 2026-09-18).
    """
    got = asyncio.run(_two_janitors(main._PC_EDITION_ROLLOVER_SQL))

    assert got["blocked"], (
        "the second janitor never blocked on the first one's row lock, so the "
        "two passes did not overlap and this test measured nothing. Increase "
        "the settle time or check that the first rollover still locks the row.")
    assert got["first_rolled"], "the first janitor did not roll over at all"
    assert got["error"] is None, (
        "the second janitor raised %s. Declining must be silent -- an "
        "overlapping pass is routine, not an error condition." % got["error"])
    assert got["second_rolled"] is False, (
        "the second janitor also reported a rollover, so two passes both "
        "believe they closed the edition")
    assert (got["editions"], got["open"], got["posts"]) == (2, 1, 1), (
        "expected exactly 2 editions / 1 open / 1 notice, got %d / %d / %d"
        % (got["editions"], got["open"], got["posts"]))


@_needs_pg
def test_control_without_the_guard_a_second_janitor_does_not_decline():
    """Proves the assertion above is about the guard and not about the index.

    With the UPDATE's live-row `ended_at IS NULL` removed, the second janitor
    closes the already-closed edition -- the close leaves `ends_at_planned`
    set, so every remaining qual still matches -- and tries to mint a second
    successor. It does NOT quietly duplicate: the partial unique index stops
    it. So the end state is the same 2 / 1 / 1 either way, and the DIRECTION of
    the failure is the whole difference. The guard is what turns an overlapping
    pass into a silent no-op rather than a `UniqueViolationError` on a routine
    janitor tick, twice per rollover, in a loop both boxes run.

    Measured before this test was written, which is the only reason the test
    above asserts `error is None` at all: on counts alone the broken statement
    is indistinguishable from the shipped one.
    """
    got = asyncio.run(_two_janitors(_no_close_guard(main._PC_EDITION_ROLLOVER_SQL)))

    assert got["blocked"], "the control did not exercise the wait either"
    assert got["error"] is not None or got["second_rolled"], (
        "the statement declined even with the guard removed, so the guard is "
        "not what produces the decline and the test above is crediting the "
        "wrong mechanism. Got: %r" % (got,))


def test_the_second_janitor_control_still_reconstructs():
    """Runs with no DSN. Guards the control's anchor, not its result."""
    out = _no_close_guard(main._PC_EDITION_ROLLOVER_SQL)
    assert out != main._PC_EDITION_ROLLOVER_SQL
