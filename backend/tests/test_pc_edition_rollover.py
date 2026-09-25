"""The seasonal edition rollover, EXECUTED against a real PostgreSQL.

`_PC_EDITION_ROLLOVER_SQL` is one statement that closes the scheduled-out
edition, opens its successor on the next four-month anchor, realigns the
SERIAL and queues the Discord notice. Nothing about it can be proved by
reading: the idempotency is a READ COMMITTED re-check of the UPDATE's own
predicate, the anchor arithmetic depends on the session TimeZone, and the
partial unique index is what makes close-before-insert mandatory. So this file
runs the SHIPPED constant -- imported from main, never a copy -- against a
server (#438/#443: acceptance is a positive signal the change emits, and "the
fake accepted it" is not one).

The clock is faked in the DATA, not in now(): the due predicate is
`ends_at_planned <= now()`, so moving the planned end backwards is exactly
equivalent to moving the clock forwards, and it keeps every assertion about
the SUCCESSOR's anchor an absolute date rather than a relative one.

There is no pytest-asyncio in this suite, so each test is a sync function that
runs one coroutine, exactly like test_a1_predicate_sql.py.

RUNNING IT
----------
    PC_EDITION_TEST_PG_DSN="postgresql://postgres@127.0.0.1:55432/pctest" \\
        python -m pytest tests/test_pc_edition_rollover.py -q

EITHER SPELLING. This file drives SQLAlchemy and so needs
`postgresql+asyncpg://`; its concurrency sibling connects with asyncpg
directly and so needs the plain `postgresql://`. They are gated by the SAME
variable, so one exported value has to satisfy both, and each normalises what
it was given (`_as_asyncpg` here, `_as_plain` there). Before that, exporting
the plain form made all ten tests here die in `create_async_engine` on a
missing psycopg2 -- SQLAlchemy's default driver for a bare `postgresql://` --
while the sibling passed, and exporting the `+asyncpg` form would have moved
the failure to the sibling instead. One variable that cannot be set correctly
for both readers is not a gate, and the cross-module assertion that keeps them
agreeing lives in the sibling's
`test_both_gated_modules_accept_either_dsn_spelling`.

Without the DSN these tests FAIL by name rather than skipping. A skip is a run
that proved nothing while reporting exit 0, which is exactly how this module
sat dead on the run that was verifying the rollover fix. Set
PC_EDITION_TEST_PG_OPTOUT=1 to waive the coverage deliberately -- an ordinary
unit run on a machine with no cluster -- and the failures become named skips.
"""
import asyncio
import datetime as _dt
import os
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import main

DSN_VAR = "PC_EDITION_TEST_PG_DSN"


def _as_asyncpg(dsn):
    """The SQLAlchemy async form, whichever of the three spellings came in.

    `create_async_engine("postgresql://...")` does not fail over to an async
    driver: it resolves the dialect's DEFAULT DBAPI, which is psycopg2, and
    raises ModuleNotFoundError in a suite that has never installed it. The
    failure names psycopg2 and says nothing about the DSN, which is how it
    cost a whole run to read.

    Rewriting the scheme is safe because the scheme is the only thing that
    differs -- host, port, user, database and query string are identical in
    both spellings, and asyncpg is the only PostgreSQL driver this repo
    installs, so there is no spelling here that legitimately means psycopg2.
    A DSN with some other scheme is passed through untouched rather than
    coerced: guessing at an unrecognised one would turn a clear error into an
    obscure one.
    """
    if not dsn:
        return dsn
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return "postgresql+asyncpg://" + dsn[len(prefix):]
    return dsn


DSN = _as_asyncpg(os.environ.get(DSN_VAR))

# THE DEFAULT IS A FAILURE, NOT A SKIP, and that polarity is the fix.
#
# Setting a NEAR-MISS variable name gave "10 skipped, exit 0", which reads as
# a clean run in any summary that reports pass/fail rather than collected
# count -- measured, not hypothetical: it happened on the run that verified
# the rollover fix, and the whole module silently checked nothing. The first
# attempt at closing that was an OPT-IN switch (PC_EDITION_TESTS_REQUIRED=1),
# which fixes the hole only for a caller who already suspects it. Nobody who
# mistypes the DSN name also remembers to set the second variable, so the
# default run went on proving nothing.
#
# So: no DSN means every test here FAILS, by name, saying what did not run.
# To waive it deliberately -- an ordinary unit run on a machine with no
# cluster -- export PC_EDITION_TEST_PG_OPTOUT=1 and the failures become named
# skips. The waiver is a decision somebody makes and can be seen making, which
# is the difference between this and the old default.
OPTOUT_VAR = "PC_EDITION_TEST_PG_OPTOUT"
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"


@pytest.fixture(autouse=True)
def _require_live_pg():
    """Applied to every test in this module; see the note above."""
    if DSN:
        return
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: live-Postgres rollover coverage "
                    "deliberately waived for this run." % (DSN_VAR, OPTOUT_VAR))
    pytest.fail(
        "%s is unset, so the rollover was not exercised against a server at "
        "all -- the anchor arithmetic, the READ COMMITTED re-check and the "
        "partial unique index are the whole subject here and none of them can "
        "be read off the source. Point it at a throwaway cluster (see this "
        "module's docstring), or set %s=1 to waive the coverage deliberately."
        % (DSN_VAR, OPTOUT_VAR))

CHANNEL = "900000000000000001"   # not a real channel id; nothing here posts

# Exactly the shape 308_player_cards.sql + 332_pc_edition_schedule.sql leave
# behind, and nothing else -- including the partial unique index, which is
# half of what the statement relies on.
SCHEMA = """
DROP TABLE IF EXISTS pc_editions;
DROP TABLE IF EXISTS pending_channel_posts;

CREATE TABLE pc_editions (
    id               SERIAL PRIMARY KEY,
    name             TEXT NOT NULL,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at         TIMESTAMPTZ NULL,
    ends_at_planned  TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX pc_editions_one_active ON pc_editions ((1)) WHERE ended_at IS NULL;
ALTER TABLE pc_editions ADD CONSTRAINT pc_editions_planned_sane
    CHECK (ends_at_planned IS NULL OR ends_at_planned > TIMESTAMPTZ '2000-01-01');

CREATE TABLE pending_channel_posts (
    id         BIGSERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL,
    content    TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    posted_at  TIMESTAMPTZ
);
"""

# The mint path's read of the active edition, verbatim from the pack-open
# route. Copied on purpose: this file asserts how the rollover BEHAVES toward
# it, and a paraphrase would stop measuring that. Production spells the read
# inline at the `# 2. locks` step rather than as a constant, so there is
# nothing to import and nothing that breaks loudly when it drifts.
#
# What holds this copy to the original lives in test_janitor_walker.py, as
# test_the_mint_read_the_gated_module_copies_is_the_one_production_runs --
# deliberately OUTSIDE this file's DSN gate. A machine with no Postgres skips
# everything in here, and that is exactly where a copy rots unobserved. It
# reads MINT_READ out of this file's source rather than importing it.
MINT_READ = ("SELECT id FROM pc_editions WHERE ended_at IS NULL "
             "ORDER BY id DESC LIMIT 1 FOR SHARE")

# 55P03 lock_not_available -- what `SET LOCAL lock_timeout` raises. Asserted by
# code rather than caught as a bare Exception, which also accepts a syntax
# error in the copied SQL above and calls it a successful demonstration of
# locking.
_LOCK_TIMEOUT_SQLSTATE = "55P03"


def run(coro):
    return asyncio.run(coro)


def _utc(y, m, d, h=0):
    return _dt.datetime(y, m, d, h, tzinfo=_dt.timezone.utc)


def _plus_months(when, months):
    """Calendar month arithmetic, day-of-month preserved.

    Every seed in this file is a 15th or a 21st, so no clamping case arises
    and none is written -- a branch no test can reach is a branch nobody has
    checked.
    """
    z = when.month - 1 + months
    return when.replace(year=when.year + z // 12, month=z % 12 + 1)


def _first_future_anchor(seed, step_months=4):
    """The first `seed + 4n` strictly after now, computed in Python.

    The production query does this in SQL with make_interval and two
    AT TIME ZONE conversions; this walks months in Python. Different
    implementations, so the comparison is a check rather than an echo.

    It exists because the expected values used to be written out as literal
    dates. They were correct when written and silently stop being correct
    the moment the calendar passes them -- `> now()` moves, the literal does
    not, and this file is DSN-gated so nothing notices for months.
    """
    now = _dt.datetime.now(_dt.timezone.utc)
    for n in range(1, 1000):
        cand = _plus_months(seed, step_months * n)
        if cand > now:
            return cand
    raise AssertionError("no future anchor within 1000 steps of %s" % seed)


def _eastern_is_dst(when):
    """Whether America/New_York is on DST at `when`, for a DAY-15 date.

    Deliberately not zoneinfo: Windows ships no tz database and the fallback
    is a PyPI package this suite does not require. US DST starts the second
    Sunday in March (the 14th at the latest) and ends the first Sunday in
    November (the 7th at the latest), so for a 15th the month alone decides
    it, with no edge cases. Asserted rather than assumed.
    """
    assert when.day == 15, (
        "the month-only DST rule is exact for a 15th and nothing else; "
        "got day %d" % when.day)
    return 3 <= when.month <= 10


async def _fresh(planned, *, tz="UTC"):
    """A server carrying one open Edition 1 whose planned end is `planned`
    (or NULL). Returns (engine, sessionmaker)."""
    engine = create_async_engine(DSN)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
            await conn.execute(text(stmt))
    async with sm() as db:
        await db.execute(text("SET TIME ZONE '%s'" % tz))
        await db.execute(
            text("INSERT INTO pc_editions (name, ends_at_planned) "
                 "VALUES ('Edition 1', CAST(:p AS timestamptz))"), {"p": planned})
        await db.commit()
    return engine, sm


async def _roll(sm, tz="UTC"):
    """One janitor pass' worth of rollover, committed. Returns the row the
    statement produced, or None when it was a no-op."""
    async with sm() as db:
        await db.execute(text("SET TIME ZONE '%s'" % tz))
        row = (await db.execute(text(main._PC_EDITION_ROLLOVER_SQL),
                                {"ch": CHANNEL})).mappings().first()
        await db.commit()
        return dict(row) if row is not None else None


async def _editions(sm):
    async with sm() as db:
        return (await db.execute(text(
            "SELECT id, name, started_at, ended_at, ends_at_planned "
            "FROM pc_editions ORDER BY id"))).mappings().all()


async def _posts(sm):
    async with sm() as db:
        return (await db.execute(text(
            "SELECT channel_id, content FROM pending_channel_posts ORDER BY id"
        ))).mappings().all()


# ── the negative control: the day before the boundary ────────────────────

def test_a_future_boundary_changes_nothing():
    async def go():
        engine, sm = await _fresh(_utc(2026, 12, 21))
        try:
            assert await _roll(sm) is None
            rows = await _editions(sm)
            assert len(rows) == 1
            assert rows[0]["ended_at"] is None
            assert rows[0]["ends_at_planned"] == _utc(2026, 12, 21)
            assert list(await _posts(sm)) == []
        finally:
            await engine.dispose()
    run(go())


def test_an_unscheduled_edition_never_rolls():
    """NULL ends_at_planned = no schedule. The clock stops; it does not run."""
    async def go():
        engine, sm = await _fresh(None)
        try:
            assert await _roll(sm) is None
            assert len(await _editions(sm)) == 1
        finally:
            await engine.dispose()
    run(go())


# ── the boundary itself ──────────────────────────────────────────────────

def test_the_boundary_closes_one_edition_and_opens_the_next():
    async def go():
        engine, sm = await _fresh(_utc(2025, 12, 21))
        try:
            row = await _roll(sm)
            assert row is not None and row["id"] == 2

            rows = await _editions(sm)
            assert [r["id"] for r in rows] == [1, 2]
            assert rows[0]["ended_at"] is not None, "the incumbent must be closed"
            assert rows[1]["ended_at"] is None and rows[1]["name"] == "Edition 2"
            # The successor lands on the ANCHOR, not four months after a late
            # rollover, and an outage spanning two boundaries makes ONE
            # successor rather than one per boundary missed.
            #
            # DERIVED, not written out. From the 2025-12-21 seed the first
            # future step was 2026-12-21 when this was authored, and a literal
            # would have started failing on that date for reasons having
            # nothing to do with the rollover -- in a file most runs skip, so
            # months after the change that "broke" it. The gap only widens as
            # the seed recedes, which makes the outage this covers longer, not
            # the test weaker.
            expected = _first_future_anchor(_utc(2025, 12, 21))
            assert rows[1]["ends_at_planned"] == expected, (
                "expected the successor on the anchor %s, got %s"
                % (expected, rows[1]["ends_at_planned"]))

            posts = list(await _posts(sm))
            assert len(posts) == 1 and posts[0]["channel_id"] == CHANNEL
            assert posts[0]["content"] == (
                "Edition 2 begins. Edition 1 prints are out of print.")
        finally:
            await engine.dispose()
    run(go())


def test_a_second_run_is_a_no_op():
    async def go():
        engine, sm = await _fresh(_utc(2025, 12, 21))
        try:
            assert (await _roll(sm))["id"] == 2
            assert await _roll(sm) is None, "the successor's end is months away"
            assert len(await _editions(sm)) == 2
            assert len(list(await _posts(sm))) == 1
        finally:
            await engine.dispose()
    run(go())


def test_the_serial_is_realigned_so_a_default_insert_does_not_collide():
    """The successor's id is explicit, so its name and its id can never
    disagree; the setval in the statement is what keeps the SERIAL from
    handing the same id out again."""
    async def go():
        engine, sm = await _fresh(_utc(2025, 12, 21))
        try:
            await _roll(sm)
            async with sm() as db:
                await db.execute(text("INSERT INTO pc_editions (name, ended_at) "
                                      "VALUES ('manual', now())"))
                await db.commit()
            assert [r["id"] for r in await _editions(sm)] == [1, 2, 3]
        finally:
            await engine.dispose()
    run(go())


def _require_dst_crossing(seed, landing):
    """The two tests below measure the UTC pinning only if the seed and its
    first future step sit on DIFFERENT Eastern offsets.

    This is the failure their own docstring describes: from a December seed
    the assertion held with or without the conversions it is named for,
    because 20 Dec 2025 and 20 Dec 2026 are both EST. The seed was moved to
    May to fix exactly that -- and then the property expires anyway, because
    which month the first FUTURE step lands in drifts with the calendar.

    No seed survives every "today" on a four-month cycle: the anchor months
    that fail to cross (March through June) are four consecutive months, so a
    run in early July has no day-15 anchor in the preceding four months that
    crosses at all. Since it cannot be made always-true, it is made
    always-VISIBLE. Passing while measuring nothing is the outcome worth
    ruling out; being told to move the seed is cheap.
    """
    assert _eastern_is_dst(seed) != _eastern_is_dst(landing), (
        "this test no longer measures the UTC pinning. The seed %s and its "
        "first future step %s are both %s, so the naive and UTC-pinned forms "
        "agree and the assertion would hold with the conversions removed -- "
        "which is the exact trap the May seed was chosen to escape. Move the "
        "seed to a 15th whose +4-month step crosses a DST boundary (an anchor "
        "in Jul-Feb; Mar-Jun anchors never cross)."
        % (seed.date(), landing.date(),
           "EDT" if _eastern_is_dst(seed) else "EST"))


# ── the anchor must not depend on the session TimeZone ───────────────────

def test_the_anchor_is_utc_whatever_the_session_timezone_is():
    """Seeded 2026-05-15 rather than 2026-12-21, and the seed is the whole
    point of the test.

    From a DECEMBER anchor the naive and UTC-pinned forms reach the same first
    future value -- 20 Dec 2025 and 20 Dec 2026 are both EST, so stepping four
    months at a time never crosses a DST boundary at the moment it matters.
    This assertion therefore used to hold with or without the conversions it
    is named for, and its negative control below failed outright. From a MAY
    anchor the first future step lands in January, the offset changes, and the
    naive form comes out an hour late.
    """
    async def go():
        seed = _utc(2026, 5, 15)
        expected = _first_future_anchor(seed)
        _require_dst_crossing(seed, expected)

        engine, sm = await _fresh(seed, tz="America/New_York")
        try:
            await _roll(sm, tz="America/New_York")
            rows = await _editions(sm)
            got = rows[1]["ends_at_planned"]
            assert got == expected, (
                "expected %s, got %s" % (expected, got))
            assert got.hour == 0, (
                "the anchor drifted off midnight UTC to %02d:00 -- that hour "
                "IS the bug this test is named for" % got.hour)
        finally:
            await engine.dispose()
    run(go())


def test_mutation_control_the_naive_arithmetic_would_fail_that_test():
    """The negative control for the test above (#391): the same expression
    WITHOUT the two AT TIME ZONE 'UTC' conversions gives a different, wrong
    answer under a non-UTC session TimeZone -- so that assertion is really
    measuring the conversion and is not passing for free.

    Asserts the naive VALUE and not just inequality. An inequality alone
    passes if the two forms differ for any reason at all, including one that
    has nothing to do with the conversion under test.
    """
    async def go():
        seed = _utc(2026, 5, 15)
        expected = _first_future_anchor(seed)
        _require_dst_crossing(seed, expected)

        engine, sm = await _fresh(seed, tz="America/New_York")
        try:
            async with sm() as db:
                await db.execute(text("SET TIME ZONE 'America/New_York'"))
                naive = (await db.execute(text("""
                    SELECT e.ends_at_planned + make_interval(months => 4 * n) AS v
                      FROM pc_editions e, generate_series(1, 1000) AS n
                     WHERE e.ended_at IS NULL
                       AND e.ends_at_planned + make_interval(months => 4 * n) > now()
                     ORDER BY n LIMIT 1
                """))).scalar_one()
            assert naive == _dt.datetime.combine(
                expected.date(), _dt.time(1, tzinfo=_dt.timezone.utc)), (
                "expected the naive form to land an hour late at %s 01:00Z; "
                "got %s. If this is 00:00Z the session TimeZone did not take "
                "and the control proves nothing." % (expected.date(), naive))
            assert naive != expected
        finally:
            await engine.dispose()
    run(go())


def test_the_two_forms_differ_at_a_fixed_step_so_this_cannot_expire():
    """The same property as the pair above, pinned without consulting now().

    Every other assertion in this file depends on where the real clock sits
    relative to the seeded anchor, so each of them changes meaning on a date
    and one of them stops discriminating entirely. This one steps a FIXED four
    months from a December anchor and compares the two expressions to each
    other, so it holds on any date the suite is ever run.

    From 2025-12-21 00:00Z under America/New_York the naive form lands on
    2026-04-20 23:00Z and the pinned form on 2026-04-21 00:00Z -- an hour AND
    a day apart, because the wall clock is carried across an EST->EDT change.
    The pinned expression below is a COPY, and a copy proves nothing about
    the shipped constant: removing the conversions from production leaves
    this test green, which is what it did until Codex said so. What binds the
    shape is `test_the_shipped_rollover_sql_pins_both_arms_to_utc` in
    test_janitor_walker.py, which reads `main._PC_EDITION_ROLLOVER_SQL`
    itself, requires the pinned form in BOTH arms, and is not DSN-gated.
    This test proves the ARITHMETIC; that one proves production still has it.
    """
    async def go():
        engine, sm = await _fresh(_utc(2025, 12, 21), tz="America/New_York")
        try:
            async with sm() as db:
                await db.execute(text("SET TIME ZONE 'America/New_York'"))
                row = (await db.execute(text("""
                    SELECT e.ends_at_planned + make_interval(months => 4) AS naive,
                           ((e.ends_at_planned AT TIME ZONE 'UTC')
                            + make_interval(months => 4)) AT TIME ZONE 'UTC' AS pinned
                      FROM pc_editions e
                     WHERE e.ended_at IS NULL
                """))).one()
            assert row.pinned == _utc(2026, 4, 21), row.pinned
            assert row.naive == _utc(2026, 4, 20, 23), row.naive
            assert row.naive != row.pinned
        finally:
            await engine.dispose()
    run(go())


# ── the refusal this design does NOT claim to remove ─────────────────────

def test_a_mint_read_inside_the_rollover_transaction_is_skipped():
    """Documents the residual rather than asserting it away: while the
    rollover transaction is open, the mint path's read waits on the row lock
    and is then SKIPPED, because the row it waited for no longer satisfies
    `ended_at IS NULL`. The pack open answers `no_edition` for the width of
    one transaction, once every four months. Nothing is lost -- the refusal is
    step 2, before the debit -- and a retry succeeds. If this test starts
    failing, someone has made that refusal unreachable and the comment on
    _PC_EDITION_ROLLOVER_SQL must be corrected."""
    async def go():
        engine, sm = await _fresh(_utc(2025, 12, 21))
        try:
            async with sm() as roller:
                # the statement runs but is NOT committed: the row lock is held
                await roller.execute(text(main._PC_EDITION_ROLLOVER_SQL),
                                     {"ch": CHANNEL})
                async with sm() as minter:
                    await minter.execute(text("SET LOCAL lock_timeout = '250ms'"))
                    with pytest.raises(Exception) as caught:
                        await minter.execute(text(MINT_READ))
                    code = getattr(getattr(caught.value, "orig", None),
                                   "sqlstate", None) or getattr(
                                       caught.value, "pgcode", None)
                    assert code == _LOCK_TIMEOUT_SQLSTATE, (
                        "expected SQLSTATE %s (lock_not_available); got %r "
                        "from %s. A bare 'it raised' also passes when the "
                        "copied SQL simply does not parse."
                        % (_LOCK_TIMEOUT_SQLSTATE, code, type(caught.value).__name__))
                    await minter.rollback()
                await roller.commit()
            # after the commit the same read finds the NEW edition
            async with sm() as minter:
                got = (await minter.execute(text(MINT_READ))).scalar_one()
                assert got == 2
        finally:
            await engine.dispose()
    run(go())



def test_the_blocked_mint_read_is_skipped_once_the_rollover_commits():
    """The post-wait SKIP, which the overlap test above never observes.

    That test gives the read a 250ms lock_timeout, so it dies while waiting
    and the interesting half never runs. This one lets the read wait properly:
    it blocks on the row lock, the rollover commits, and the read then
    resumes -- and must come back with NOTHING.

    Why nothing is right. Under READ COMMITTED the re-check after a lock wait
    re-evaluates the qual against the UPDATED row, and edition 1 now has
    `ended_at` set, so it drops out. Edition 2 was inserted by a transaction
    that committed after this statement began, so it is not in the statement's
    snapshot either. No row -- which is the `None` that makes the pack open
    answer `no_edition` for the width of one transaction, once every four
    months, before any debit.

    If this ever returns a row, the documented residual is gone and the
    comment on _PC_EDITION_ROLLOVER_SQL is wrong in the other direction.
    """
    async def go():
        engine, sm = await _fresh(_utc(2025, 12, 21))
        try:
            async with sm() as roller:
                await roller.execute(text(main._PC_EDITION_ROLLOVER_SQL),
                                     {"ch": CHANNEL})
                async with sm() as minter:
                    # No lock_timeout on purpose: the wait IS the subject.
                    task = asyncio.ensure_future(
                        minter.execute(text(MINT_READ)))
                    await asyncio.sleep(0.5)
                    assert not task.done(), (
                        "the mint read did not block at all, so nothing below "
                        "is about waiting on the rollover's row lock")

                    await roller.commit()
                    result = await asyncio.wait_for(task, timeout=15)
                    got = result.scalar_one_or_none()
                    assert got is None, (
                        "the blocked mint read resumed and returned edition "
                        "%r. It must find nothing: edition 1 stopped matching "
                        "`ended_at IS NULL` while it waited, and edition 2 is "
                        "outside its snapshot. Returning a row would mean the "
                        "pack open can mint against an edition it never "
                        "locked." % (got,))
                    await minter.rollback()
        finally:
            await engine.dispose()
    run(go())
