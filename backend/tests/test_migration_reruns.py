"""Every migration this delta adds, APPLIED TWICE against a real PostgreSQL.

A migration that "is idempotent" is a claim about what happens on the SECOND
run, and nothing but a second run settles it (#313/#340: a migration is not
reviewed until its statements have RUN). Reading the file tells you the
statements are guarded; it does not tell you whether the guards fired, whether
a guarded statement still rewrote every row, or whether a DROP-then-ADD
quietly replaced an object that was already correct.

WHAT "A NO-OP" IS MEASURED AS HERE, and why it is not a row count:

  * VALUE + VERSION. Each table is fingerprinted as the multiset of
    ``row::text || '|' || row.xmin``. ``xmin`` is the transaction that last
    wrote the row, so an UPDATE that sets a column to the value it already
    held -- the exact shape of ``ON CONFLICT DO UPDATE SET x = EXCLUDED.x`` --
    changes the fingerprint even though every value is unchanged and every
    "expected N rows" assertion still passes. That is the defect these tests
    exist to catch, and a value-only hash cannot see it.
  * OBJECT IDENTITY. Constraints and indexes are fingerprinted by OID.
    ``DROP CONSTRAINT IF EXISTS`` followed by ``ADD CONSTRAINT`` ends in a
    state that reads as identical and is not: a new OID means the table was
    locked and revalidated. A re-run that takes an ACCESS EXCLUSIVE lock on a
    live table is not a no-op, whatever the final state says.

Each migration runs in its own throwaway SCHEMA, created and dropped by the
test, so the cluster this points at keeps nothing afterwards. The migrations
ask `current_schema()` rather than hardcoding `public`, which is what makes
that possible.

RUNNING IT
----------
    SCR_MIGRATION_TEST_PG_DSN="postgresql://postgres@127.0.0.1:55432/wavebctest" \\
        python -m pytest backend/tests/test_migration_reruns.py -q

Without the DSN these tests FAIL rather than skip. A skip here is a run that
proved nothing while reporting exit 0, which is how a whole gated module can
sit dead for releases (#342: a check that cannot fail). To waive the coverage
deliberately -- an ordinary unit run on a machine with no cluster -- set
SCR_MIGRATION_TEST_PG_OPTOUT=1 and the failures become named skips.
"""
import asyncio
import datetime as _dt
import os
import re
import uuid
from pathlib import Path

import pytest

try:
    import asyncpg
except ImportError:                                    # pragma: no cover
    asyncpg = None

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

DSN_VAR = "SCR_MIGRATION_TEST_PG_DSN"
OPTOUT_VAR = "SCR_MIGRATION_TEST_PG_OPTOUT"
DSN = (os.environ.get(DSN_VAR) or "").replace("postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"


@pytest.fixture(autouse=True)
def _require_live_pg():
    """Fail, not skip, when the cluster is missing and nobody said to waive it.

    The default polarity is the whole point. `pytest.mark.skipif(not DSN)`
    reports "N skipped, exit 0", which every summary that counts pass/fail
    reads as a clean run -- and a near-miss variable name produces exactly
    that with the variable apparently set.
    """
    if DSN and asyncpg is not None:
        return
    if OPTOUT:
        pytest.skip(
            "%s is unset and %s=1: migration re-run coverage deliberately waived "
            "for this run." % (DSN_VAR, OPTOUT_VAR))
    if asyncpg is None:
        pytest.fail(
            "asyncpg is not installed, so the migration re-run coverage did not "
            "run. Install it, or set %s=1 to waive it deliberately." % OPTOUT_VAR)
    pytest.fail(
        "%s is unset, so no migration in this delta was applied even once -- "
        "let alone twice. Point it at a throwaway cluster (see this module's "
        "docstring), or set %s=1 to waive the coverage deliberately."
        % (DSN_VAR, OPTOUT_VAR))


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Prerequisites, per migration ────────────────────────────────────────────
#
# Only what the file under test actually references. Kept minimal on purpose:
# a prerequisite block that drifts into being a copy of the whole schema is a
# second source of truth for it.

PREREQ = {
    "331": """
        CREATE TABLE players (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            steam_id VARCHAR(32) UNIQUE,
            display_name VARCHAR(64));
        CREATE TABLE shop_items (
            id              BIGSERIAL PRIMARY KEY,
            sku             VARCHAR(64) UNIQUE NOT NULL,
            kind            VARCHAR(16) NOT NULL,
            name            VARCHAR(128) NOT NULL,
            description     VARCHAR(256),
            price           INTEGER NOT NULL CHECK (price >= 0),
            rarity          VARCHAR(16) NOT NULL DEFAULT 'common',
            rotation_pool   VARCHAR(32),
            preview_color   VARCHAR(16),
            catalog_ready   BOOLEAN NOT NULL DEFAULT TRUE,
            released_at     TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW());
    """,
    "332": """
        CREATE TABLE pc_editions (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            ended_at    TIMESTAMPTZ NULL);
        CREATE UNIQUE INDEX pc_editions_one_active
            ON pc_editions ((1)) WHERE ended_at IS NULL;
        INSERT INTO pc_editions (name) VALUES ('Edition 1');
    """,
    # 333 creates its own table and guards its only foreign reference.
    "333": "",
    "336": """
        CREATE TABLE bug_reports (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            player_id       UUID,
            steam_id        VARCHAR(32),
            display_name    VARCHAR(64),
            mod_version     VARCHAR(32),
            game_version    VARCHAR(32),
            severity        VARCHAR(16) NOT NULL DEFAULT 'medium',
            category        VARCHAR(16) NOT NULL DEFAULT 'other',
            description     TEXT NOT NULL,
            repro_steps     TEXT,
            log_filename    VARCHAR(96),
            log_bytes       INTEGER,
            status          VARCHAR(16) NOT NULL DEFAULT 'open',
            triage_notes    TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW());
        INSERT INTO bug_reports (steam_id, description)
             VALUES ('76561190000000001', 'a pre-existing player-filed report');
    """,
}

# The tables whose CONTENT this file is responsible for. Fingerprinted
# value-and-version after each run.
TABLES = {
    "331": ("shop_items", "title_ladders", "title_ladder_progress",
            "title_ladder_credits"),
    "332": ("pc_editions",),
    "333": ("pc_card_themes",),
    "336": ("bug_reports",),
}

MIGRATION_FILES = {
    "331": "331_animal_title_ladders.sql",
    "332": "332_pc_edition_schedule.sql",
    "333": "333_pc_card_themes.sql",
    "336": "336_bug_reports_kind.sql",
}


def migration_text(number: str) -> str:
    return (SQL_DIR / MIGRATION_FILES[number]).read_text(encoding="utf-8")


async def _fingerprint(conn, tables) -> dict:
    """Value AND row version, per table.

    `xmin` is what makes this able to see a rewrite-to-the-same-value. Ordered
    inside the aggregate so the result does not depend on physical order,
    which an UPDATE changes even when nothing else does.
    """
    out = {}
    for t in tables:
        if not await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", t):
            out[t] = None
            continue
        out[t] = await conn.fetch(
            "SELECT r::text AS row_text, r.xmin::text AS version "
            "  FROM %s r ORDER BY r::text" % t)
    return out


async def _objects(conn) -> dict:
    """Constraint and index OIDs in this schema.

    A DROP-then-ADD ends in the same textual definition and a different OID.
    The OID is how "it did nothing" is told apart from "it did the same thing
    again", and the second one took a table lock.
    """
    rows = await conn.fetch("""
        SELECT c.conname AS name, c.oid::text AS oid, 'constraint' AS what
          FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
          JOIN pg_namespace n ON n.oid = t.relnamespace
         WHERE n.nspname = current_schema()
        UNION ALL
        SELECT ci.relname, ci.oid::text, 'index'
          FROM pg_index i JOIN pg_class ci ON ci.oid = i.indexrelid
          JOIN pg_namespace n ON n.oid = ci.relnamespace
         WHERE n.nspname = current_schema()
         ORDER BY 3, 1""")
    return {(r["what"], r["name"]): r["oid"] for r in rows}


async def _relations(conn) -> set:
    """Every relation in the database, by (schema, name, kind).

    NOT scoped to `current_schema()`, and that is the whole point of it. The
    two measurements beside this one -- a fingerprint of the tables the
    migration owns and an OID map of constraints and indexes -- both report
    NOTHING when an ordinary table simply ceases to exist: a plain table has
    no constraint OID to change and no rows anyone is counting. A migration
    that names a relation without qualifying it resolves whatever the search
    path offers, so what has to be inventoried is the database rather than
    the migration's own corner of it.

    System schemas are excluded by prefix rather than by name, so a temporary
    schema (`pg_temp_7`) and a toast schema go with them. A relation that
    lives in one of those is not something a re-run can be accused of losing.
    """
    rows = await conn.fetch("""
        SELECT n.nspname AS schema, c.relname AS name, c.relkind::text AS kind
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
           AND n.nspname !~ '^pg_'
           AND n.nspname <> 'information_schema'
         ORDER BY 1, 2""")
    return {(r["schema"], r["name"], r["kind"]) for r in rows}


def _changed(before, after) -> int:
    """Rows present in `after` with a (value, version) pair `before` did not
    have: inserts plus rewrites, which is exactly "rows this run wrote"."""
    total = 0
    for table, rows_after in after.items():
        rows_before = before.get(table)
        if rows_after is None:
            continue
        seen = {}
        for r in (rows_before or []):
            key = (r["row_text"], r["version"])
            seen[key] = seen.get(key, 0) + 1
        for r in rows_after:
            key = (r["row_text"], r["version"])
            if seen.get(key):
                seen[key] -= 1
            else:
                total += 1
    return total


class Applied:
    """Result of applying one migration twice in a private schema."""

    def __init__(self, first, second, objects_first, objects_second, schema,
                 relations_first=frozenset(), relations_second=frozenset()):
        self.first = first
        self.second = second
        self.objects_first = objects_first
        self.objects_second = objects_second
        self.schema = schema
        self.relations_first = relations_first
        self.relations_second = relations_second

    @property
    def rows_changed_on_second_run(self):
        return _changed(self.first, self.second)


async def _apply_twice(number, *, between=None, prereq_extra="", cleanup=None):
    """Prerequisites, migration, optional operator edit, migration again.

    `cleanup` runs before the private schema is dropped, for the one case
    that has to put a relation OUTSIDE that schema: dropping the schema does
    not reach it, and a test that leaves a table behind is a test that fails
    the second time it runs.
    """
    schema = "m%s_%s" % (number, uuid.uuid4().hex[:10])
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute('CREATE SCHEMA "%s"' % schema)
        await conn.execute('SET search_path TO "%s"' % schema)
        if PREREQ[number].strip():
            await conn.execute(PREREQ[number])
        if prereq_extra.strip():
            await conn.execute(prereq_extra)

        sql = migration_text(number)
        await conn.execute(sql)
        first = await _fingerprint(conn, TABLES[number])
        objects_first = await _objects(conn)
        relations_first = await _relations(conn)

        if between:
            await conn.execute(between)
            first = await _fingerprint(conn, TABLES[number])
            objects_first = await _objects(conn)
            relations_first = await _relations(conn)

        await conn.execute(sql)
        second = await _fingerprint(conn, TABLES[number])
        objects_second = await _objects(conn)
        relations_second = await _relations(conn)
        return Applied(first, second, objects_first, objects_second, schema,
                       relations_first, relations_second)
    finally:
        try:
            if cleanup:
                await conn.execute(cleanup)
            await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
        finally:
            await conn.close()


# ── The bar: a second run changes nothing ───────────────────────────────────

@pytest.mark.parametrize("number", ["331", "332", "333", "336"])
def test_a_second_run_writes_no_row(number):
    """Applied twice, back to back, on the state the first run left."""
    applied = _run(_apply_twice(number))
    assert applied.rows_changed_on_second_run == 0, (
        "migration %s rewrote %d row(s) on its second run. Re-running a "
        "migration must change nothing; a guarded statement that still writes "
        "the same values back takes the same locks and produces the same WAL "
        "as one that changed something."
        % (number, applied.rows_changed_on_second_run))


@pytest.mark.parametrize("number", ["331", "332", "333", "336"])
def test_a_second_run_leaves_every_row_byte_identical(number):
    """The value half of the bar, stated separately so a failure says which
    of the two properties broke."""
    applied = _run(_apply_twice(number))
    for table in TABLES[number]:
        before = [r["row_text"] for r in (applied.first.get(table) or [])]
        after = [r["row_text"] for r in (applied.second.get(table) or [])]
        assert before == after, (
            "migration %s changed the contents of %s on its second run"
            % (number, table))


@pytest.mark.parametrize("number", ["331", "332", "333", "336"])
def test_a_second_run_replaces_no_constraint_or_index(number):
    """OIDs, not definitions. A dropped-and-recreated constraint has the same
    definition, a new OID, and cost an ACCESS EXCLUSIVE lock plus a validating
    scan to arrive at the state it was already in."""
    applied = _run(_apply_twice(number))
    replaced = sorted(
        "%s %s" % (what, name)
        for (what, name), oid in applied.objects_second.items()
        if applied.objects_first.get((what, name)) not in (None, oid))
    assert not replaced, (
        "migration %s dropped and recreated %s on its second run" % (number, replaced))
    vanished = sorted(
        "%s %s" % (what, name) for (what, name) in applied.objects_first
        if (what, name) not in applied.objects_second)
    assert not vanished, (
        "migration %s removed %s on its second run" % (number, vanished))


@pytest.mark.parametrize("number", ["331", "332", "333", "336"])
def test_a_second_run_removes_no_relation_from_the_database(number):
    """THE THIRD MEASUREMENT, AND THE ONE THE OTHER TWO CANNOT MAKE.

    The row fingerprint watches the tables the migration owns and the OID map
    watches constraints and indexes. An ordinary table that disappears has
    neither: it contributes no row to a table anyone is counting and no OID to
    compare, so both measurements report a clean no-op while a relation is
    gone. That is not hypothetical here -- 336's post-check drops a probe
    table by name before creating it, and an unqualified name resolves against
    whatever the search path offers.

    So the inventory is of the database, and the arm is one-sided: a relation
    that APPEARS on a second run is a different defect, reported by the rows
    and objects above; a relation that VANISHES is this one.
    """
    applied = _run(_apply_twice(number))
    gone = sorted("%s.%s (%s)" % row
                  for row in applied.relations_first - applied.relations_second)
    assert not gone, (
        "migration %s removed %s from the database on its second run. A "
        "re-run may not delete a relation it did not create."
        % (number, gone))


def test_336_probe_cleanup_cannot_reach_a_same_named_ordinary_table():
    """THE CONTROL FOR THE ARM ABOVE, ON THE STATEMENT IT WAS WRITTEN FOR.

    336's post-check derives the expected constraint rendering by writing this
    file's own predicate on a throwaway table called `m336_expected_probe`,
    and drops any leftover of that name first. Unqualified, that DROP resolves
    on the search path and a database that happens to hold an ordinary table
    of the name loses it, with the deletion committed alongside the rest of
    the file. Qualified `pg_temp.`, the only relation it can reach is the one
    the post-check makes itself.

    A table of exactly that name is planted between the two runs, so the
    second run is the one that has to leave it alone. The planted table
    carries a row, because a table that is dropped and re-created by some
    later statement would otherwise read as survival.
    """
    witness = "zz_m336_inventory_witness_%s" % uuid.uuid4().hex[:8]
    applied = _run(_apply_twice(
        "336",
        between=("CREATE TABLE m336_expected_probe (kind text); "
                 "INSERT INTO m336_expected_probe VALUES ('keep me'); "
                 "CREATE TABLE public.%s (x int)" % witness),
        cleanup="DROP TABLE IF EXISTS public.%s" % witness))
    planted = [row for row in applied.relations_first
               if row[1] == "m336_expected_probe"]
    assert planted, (
        "the planted table is not in the inventory taken before the second "
        "run, so this control is rehearsing nothing: %r"
        % (sorted(applied.relations_first),))

    # THE INVENTORY'S REACH, as a positive signal rather than a claim about
    # the query. The second table is planted in `public`, which is not the
    # schema the migration runs in; an inventory narrowed to
    # `current_schema()` would be blind to every relation outside it and this
    # assertion is what says so.
    assert [row for row in applied.relations_first if row[1] == witness], (
        "the inventory did not see a relation planted outside the schema the "
        "migration runs in, so a table deleted anywhere else in the database "
        "would not be reported: %r" % (sorted(applied.relations_first)[:20],))
    gone = sorted("%s.%s (%s)" % row
                  for row in applied.relations_first - applied.relations_second)
    assert not gone, (
        "336's second run removed %s. Its probe cleanup has to be scoped to "
        "this session's temporary schema -- an unqualified name reaches "
        "whatever the search path offers." % (gone,))


async def _second_run_under_lock(number, table, holder_sql):
    """Apply the file, then apply it AGAIN while another session holds a lock.

    Returns ``(control, verdict)``. ``control`` is what an explicitly
    ACCESS-EXCLUSIVE statement did under the same holder, and it is not
    decoration: without it, "the re-run completed" is exactly what this probe
    would also print if the holder had failed to take any lock at all, which
    is a check that cannot fail dressed up as a live experiment (#689/#342).
    The control runs under its own short lock_timeout so the proof costs
    milliseconds rather than the file's own five seconds.
    """
    sql = migration_text(number)
    schema = "mlock%s_%s" % (number, uuid.uuid4().hex[:8])
    doer = await asyncpg.connect(DSN)
    holder = await asyncpg.connect(DSN)
    try:
        await doer.execute('CREATE SCHEMA "%s"' % schema)
        await doer.execute('SET search_path TO "%s"' % schema)
        await holder.execute('SET search_path TO "%s"' % schema)
        if PREREQ[number].strip():
            await doer.execute(PREREQ[number])
        await doer.execute(sql)

        tx = holder.transaction()
        await tx.start()
        await holder.execute(holder_sql)
        try:
            # CONTROL. `ADD COLUMN IF NOT EXISTS` over a column that cannot
            # exist: it writes nothing, and it takes ACCESS EXCLUSIVE in order
            # to decide that -- which is the very property under test.
            await doer.execute(
                "BEGIN; SET LOCAL lock_timeout = '300ms'; "
                "ALTER TABLE %s ADD COLUMN IF NOT EXISTS _lock_control int; "
                "ROLLBACK;" % table)
            control = "completed"
        except Exception as ex:
            control = type(ex).__name__
        try:
            await doer.execute("ROLLBACK")
        except Exception:
            pass

        try:
            await doer.execute(sql)
            verdict = None
        except Exception as ex:
            verdict = "%s: %s" % (type(ex).__name__, ex)
        await tx.rollback()
        return control, verdict
    finally:
        try:
            await doer.execute("ROLLBACK")
        except Exception:
            pass
        try:
            await doer.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
        finally:
            await doer.close()
            await holder.close()


_HOLDERS = {
    "an ordinary reader": "SELECT count(*) FROM %s",
    "an ordinary writer": "LOCK TABLE %s IN ROW EXCLUSIVE MODE",
}

_LOCK_CASES = [(number, table, who)
               for number in ("331", "332", "333", "336")
               for table in TABLES[number]
               for who in sorted(_HOLDERS)]


@pytest.mark.parametrize("number,table,who", _LOCK_CASES)
def test_a_second_run_takes_no_blocking_lock(number, table, who):
    """WHAT A RE-RUN LOCKS, which is a different question from what it writes.

    Every test above measures the rows and the object OIDs a second run
    leaves, and a file can pass all of them while still stopping the table
    dead: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and `CREATE INDEX IF NOT
    EXISTS` each take their lock BEFORE they evaluate the existence test, so
    that spelling is a no-op only in what it writes. 331, 332 and 336 each
    carry `SET LOCAL lock_timeout = '5s'` (333 has none, and needs none --
    it establishes one table and locks nothing that was already there), so on
    a live primary the result is not a slow re-run but an aborted one -- and
    while it queues, every new reader of the table queues behind it.

    The measurement is therefore behavioural rather than a reading of the
    statements: hold the lock an ordinary request holds, re-apply the file,
    and require it to get all the way through.
    """
    holder_sql = _HOLDERS[who] % table
    control, verdict = _run(_second_run_under_lock(number, table, holder_sql))
    assert control == "LockNotAvailableError", (
        "the control did not fire: an ALTER TABLE needing ACCESS EXCLUSIVE on "
        "%s ran to completion while %s was supposed to be holding a lock on it "
        "(the control reported %r). Until that can fail, this test cannot tell "
        "a re-run that takes no lock from a holder that took none."
        % (table, who, control))
    assert verdict is None, (
        "%s re-applied while %s held a lock on %s ABORTED: %s. A re-run must "
        "not queue behind -- or in front of -- ordinary traffic on a live "
        "table: guard the statement on the catalog so it is never issued, "
        "rather than spelling it IF NOT EXISTS."
        % (MIGRATION_FILES[number], who, table, verdict))


# ── The specific hazards each guard was written for ─────────────────────────

def test_331_does_not_revoke_a_later_activation():
    """THE MONEY ONE. 331's header says a later release flips the eight entry
    rungs `catalog_ready = TRUE` in the deploy that wires the progression
    hook. Replaying 331 after that release must not take them back off sale.

    The `between` block IS that later release, reduced to the one statement it
    would run.
    """
    applied = _run(_apply_twice("331", between="""
        UPDATE shop_items si SET catalog_ready = TRUE
          FROM title_ladders tl
         WHERE tl.sku = si.sku AND tl.tier = 1;
    """))
    after = {r["row_text"] for r in applied.second["shop_items"]}
    before = {r["row_text"] for r in applied.first["shop_items"]}
    assert after == before, (
        "re-running 331 changed shop_items after the activation release had "
        "flipped the entry rungs on sale -- the repair statement is acting as "
        "a revocation")


def test_331_does_not_rewrite_ladder_metadata_on_a_rerun():
    """A hand-corrected threshold must survive a replay of the file.

    Not because editing the table is the right way to move a threshold -- it
    is not, `title_ladders.TIER_THRESHOLDS` is what the API reads -- but
    because a migration that silently reimposes its own literals is a
    migration whose re-run is a write.
    """
    # 11, not an arbitrary large number: 331's own post-checks assert that
    # thresholds climb with tier inside a line, and an edit that broke that
    # would abort the second run for a reason that has nothing to do with the
    # property under test. rat tier 2 sits between 0 and 30.
    applied = _run(_apply_twice("331", between="""
        UPDATE title_ladders SET threshold = 11 WHERE sku = 'title_ladder_rat_2';
    """))
    row = [r["row_text"] for r in applied.second["title_ladders"]
           if "title_ladder_rat_2" in r["row_text"]]
    assert row and ",11)" in row[0], (
        "re-running 331 overwrote an edited title_ladders row: %s" % row)


async def _open_edition_boundary(number="332", *, between=None):
    """Apply 332 (optionally with an operator edit between the runs) and read
    the open edition's boundary back as a VALUE.

    Not out of the row-as-text fingerprint: `record::text` renders a
    timestamptz in the SESSION's timezone, so a UTC boundary comes back as
    "2026-12-20 16:00:00-08" on this seat and a substring test for the date
    Sid chose passes or fails on where the test is running. That is the shape
    of an assertion that measures the wrong thing (#342).
    """
    schema = "m332_%s" % uuid.uuid4().hex[:10]
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute('CREATE SCHEMA "%s"' % schema)
        await conn.execute('SET search_path TO "%s"' % schema)
        await conn.execute(PREREQ["332"])
        sql = migration_text("332")
        # The instant the file's own `now()` is about to be read against,
        # taken from the SERVER: the expected boundary is derived from this
        # rather than written down, and deriving it from the test runner's
        # clock would compare two different clocks.
        applied_at = await conn.fetchval("SELECT now()")
        await conn.execute(sql)
        after_first = await conn.fetchval(
            "SELECT ends_at_planned FROM pc_editions WHERE ended_at IS NULL")
        if between:
            await conn.execute(between)
        await conn.execute(sql)
        after_second = await conn.fetchval(
            "SELECT ends_at_planned FROM pc_editions WHERE ended_at IS NULL")
        return after_first, after_second, applied_at
    finally:
        try:
            await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
        finally:
            await conn.close()


def test_332_does_not_rearm_an_edition_somebody_unscheduled():
    """NULL is the supported "stop the clock" state, so a replay that fills it
    in again is a replay that restarts a season nobody restarted."""
    _first, second, _at = _run(_open_edition_boundary(between="""
        UPDATE pc_editions SET ends_at_planned = NULL WHERE ended_at IS NULL;
    """))
    assert second is None, (
        "re-running 332 re-armed a deliberately cleared schedule to %s" % second)


# The season series 332 derives its anchor from: 21 Dec 2026 00:00 UTC, then
# every fourth month, which is the 21 Dec / 21 Apr / 21 Aug cadence the
# rollover in main.py walks.
_SERIES_ORIGIN = _dt.datetime(2026, 12, 21, tzinfo=_dt.timezone.utc)
_SERIES_CANDIDATES = 121          # the file's generate_series(0, 120)


def _expected_first_boundary(as_of):
    """The first member of the season series strictly after `as_of`.

    Written out in Python on purpose. The migration derives this in SQL; a
    test that pins the answer as a LITERAL is the expiry that was taken out
    of the file, put back into its gate -- from 2026-12-21 onward the shipped
    file correctly seeds 2027-04-21, and a test holding the solstice would go
    red on a migration that is right. Two independent derivations of the same
    rule disagree loudly and cost nothing while they agree.
    """
    for n in range(_SERIES_CANDIDATES):
        months = (_SERIES_ORIGIN.month - 1) + 4 * n
        candidate = _SERIES_ORIGIN.replace(
            year=_SERIES_ORIGIN.year + months // 12, month=months % 12 + 1)
        if candidate > as_of:
            return candidate
    return None


def test_332_seeds_the_first_boundary_on_a_clean_database():
    """The positive control for the negative above: on a first run the file
    must actually write a boundary, or every no-op assertion here is passing
    on a statement that does nothing at all.

    WHICH boundary is derived from the rule, not written down; see
    `_expected_first_boundary`. The properties asserted are the ones that make
    an answer right at any date: it is in the series, it is in the future, and
    it is the FIRST such member -- the one before it has already passed. A
    file that seeded the second member would satisfy the first two.
    """
    first, second, applied_at = _run(_open_edition_boundary())
    assert first is not None, "332 seeded no boundary on a clean database"
    utc = first.astimezone(_dt.timezone.utc)
    expected = _expected_first_boundary(applied_at)
    assert expected is not None, (
        "the season series is exhausted as of %s, so this test can no longer "
        "say what the file should have seeded" % applied_at)
    # In the series, stated against the value itself rather than against the
    # helper, so the two say it independently.
    assert (utc.day, utc.month, utc.hour, utc.minute) in [
        (21, 12, 0, 0), (21, 4, 0, 0), (21, 8, 0, 0)], (
        "332 seeded %s, which is not a 21 Dec / 21 Apr / 21 Aug 00:00 UTC "
        "boundary" % utc)
    assert utc > applied_at, (
        "332 seeded %s, which is not in the future as of the server's own %s"
        % (utc, applied_at))
    months = (utc.month - 1) - 4
    previous = utc.replace(year=utc.year + months // 12, month=months % 12 + 1)
    assert previous <= applied_at, (
        "332 seeded %s, but the boundary before it (%s) is also still in the "
        "future -- the file skipped a season" % (utc, previous))
    assert utc == expected, (
        "332 seeded %s; the first boundary after the server's own %s is %s"
        % (utc, applied_at, expected))
    assert second == first, "the second run moved the boundary to %s" % second


def test_332_boundary_derivation_does_not_expire():
    """The shipped series expression, EXECUTED, with its `now()` replaced by a
    date this test chooses.

    The expression is lifted out of the migration file rather than retyped:
    a copy would keep passing after the file changed, which is the whole
    failure mode (#342). It is asserted against dates on both sides of the
    original fixed boundary, because the defect this replaced was a file that
    aborted once that one date was in the past.
    """
    sql = migration_text("332")
    match = re.search(r"-- @m332-anchor-begin\n(.*?)\n-- @m332-anchor-end",
                      sql, re.S)
    assert match, ("332's boundary derivation no longer sits between the "
                   "@m332-anchor markers; the markers exist for this test and "
                   "for nothing else, so move them with the expression")
    expression = match.group(1)
    assert "now()" in expression, (
        "the extracted derivation does not read now(), so substituting an "
        "as-of date below would prove nothing about when it is evaluated")
    # The one substitution: the file asks "after now", this test asks "after a
    # date I choose". Everything else is the shipped text.
    probe = "SELECT (%s)" % expression.replace("now()", "$1")

    as_of_dates = ("2026-09-19", "2026-12-20", "2026-12-22",
                   "2027-05-01", "2031-01-05")

    async def _go():
        conn = await asyncpg.connect(DSN)
        try:
            # A DST zone on purpose. The defect this derivation was rewritten
            # to remove only shows in one: under US/Pacific the naive form
            # stepped from 2026-12-21 00:00 UTC to 2027-04-20 23:00 UTC and
            # lost the 21st. A UTC session would have hidden it.
            await conn.execute("SET TimeZone TO 'America/Los_Angeles'")
            out = {}
            for asof in as_of_dates:
                when = _dt.datetime.fromisoformat(asof).replace(
                    tzinfo=_dt.timezone.utc)
                out[asof] = await conn.fetchval(probe, when)
            return out
        finally:
            await conn.close()

    got = _run(_go())
    for asof, landed in got.items():
        assert landed is not None, (
            "the boundary series yields nothing as of %s -- a cold replay then "
            "seeds NULL or aborts, which is the expiry this derivation removed"
            % asof)
        utc = landed.astimezone(_dt.timezone.utc)
        assert utc.day == 21 and utc.month in (12, 4, 8) and utc.hour == 0, (
            "as of %s the series landed on %s, which is not a 21 Dec / 21 Apr / "
            "21 Aug 00:00 UTC boundary" % (asof, utc))
        assert utc.date().isoformat() > asof, (asof, utc)
        # The SHIPPED expression against the derivation the live test above
        # measures the migration with. Two implementations of one rule: while
        # they agree this costs nothing, and the date they would first
        # disagree on is the date one of them is wrong.
        when = _dt.datetime.fromisoformat(asof).replace(tzinfo=_dt.timezone.utc)
        assert utc == _expected_first_boundary(when), (
            "as of %s the shipped SQL lands on %s and the test-side derivation "
            "on %s; one of the two no longer states the season series"
            % (asof, utc, _expected_first_boundary(when)))
    today = got["2026-09-19"].astimezone(_dt.timezone.utc)
    assert (today.year, today.month, today.day) == (2026, 12, 21), (
        "against a FIXED as-of date of 2026-09-19 -- not against today -- the "
        "series must still land on the boundary Sid chose, 2026-12-21; it "
        "landed on %s" % today)


def test_333_does_not_reset_seeded_at_on_a_rerun():
    """`seeded_at` records when a colour was last derived from the assets. A
    re-run that touches all 67 turns it into "when somebody last ran the
    file", which is a different and useless fact."""
    applied = _run(_apply_twice("333"))
    before = {r["row_text"] for r in applied.first["pc_card_themes"]}
    after = {r["row_text"] for r in applied.second["pc_card_themes"]}
    assert before == after, "re-running 333 rewrote pc_card_themes rows"
    versions_before = {r["version"] for r in applied.first["pc_card_themes"]}
    versions_after = {r["version"] for r in applied.second["pc_card_themes"]}
    assert versions_before == versions_after, (
        "re-running 333 rewrote every row to the same values -- seeded_at was "
        "reset and the row versions moved")


def test_333_still_updates_a_row_whose_colour_actually_changed():
    """The negative control for the WHERE above: guarding the DO UPDATE must
    not turn the file into DO NOTHING, or a regenerated colour never lands."""
    applied = _run(_apply_twice("333", between="""
        UPDATE pc_card_themes SET hex = '#000000' WHERE card_name = 'Poison';
    """))
    row = [r["row_text"] for r in applied.second["pc_card_themes"]
           if r["row_text"].startswith("(Poison,")]
    assert row and "#00934C" in row[0], (
        "333 did not restore a colour that had drifted from the generator: %s"
        % row)


def test_336_does_not_rebuild_its_check_constraint():
    """The named hazard: DROP CONSTRAINT IF EXISTS + ADD CONSTRAINT takes an
    ACCESS EXCLUSIVE lock and revalidates the whole table on every run, to
    arrive at the constraint that was already there."""
    applied = _run(_apply_twice("336"))
    key = ("constraint", "bug_reports_kind_known")
    assert key in applied.objects_first, "336 did not create bug_reports_kind_known"
    assert applied.objects_first[key] == applied.objects_second[key], (
        "336 dropped and recreated bug_reports_kind_known on its second run")


def test_336_labels_existing_rows_and_admits_both_values():
    """Positive control: the column has to actually arrive, defaulted, over
    the row the prerequisite block planted."""
    async def _go():
        schema = "m336_%s" % uuid.uuid4().hex[:10]
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute('CREATE SCHEMA "%s"' % schema)
            await conn.execute('SET search_path TO "%s"' % schema)
            await conn.execute(PREREQ["336"])
            await conn.execute(migration_text("336"))
            kinds = await conn.fetch("SELECT kind FROM bug_reports")
            await conn.execute(
                "INSERT INTO bug_reports (steam_id, description, kind) "
                "VALUES ('76561190000000002', 'an automatic upload', 'auto')")
            with_auto = await conn.fetchval(
                "SELECT count(*) FROM bug_reports WHERE kind = 'auto'")
            refused = False
            try:
                await conn.execute(
                    "INSERT INTO bug_reports (steam_id, description, kind) "
                    "VALUES ('76561190000000003', 'a typo', 'atuo')")
            except asyncpg.exceptions.CheckViolationError:
                refused = True
            return [r["kind"] for r in kinds], with_auto, refused
        finally:
            try:
                await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
            finally:
                await conn.close()

    kinds, with_auto, refused = _run(_go())
    assert kinds == ["report"], (
        "an existing player-filed row came out labelled %s" % kinds)
    assert with_auto == 1
    assert refused, (
        "a third kind value was accepted -- such a row falls out of both the "
        "report feed and the retention sweep, so nothing announces it and "
        "nothing ever deletes it")


def test_336_refuses_a_same_named_index_over_the_wrong_columns():
    """`CREATE INDEX IF NOT EXISTS` keeps whatever index already carries the
    name, over whatever columns.

    So a post-check that asks only whether the NAME exists passes for ever
    over an index on the wrong columns, and the retention sweep seq-scans
    `bug_reports` behind a check that says it cannot. The post-check reads
    `pg_get_indexdef` for exactly this case, and this is that case: an index
    with the right name and the wrong definition is planted first, and the
    migration has to REFUSE rather than adopt it.

    Run against a live server because `IF NOT EXISTS`'s adoption behaviour is
    the whole subject and cannot be read off the file.
    """
    async def _go():
        schema = "m336wrong_%s" % uuid.uuid4().hex[:10]
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute('CREATE SCHEMA "%s"' % schema)
            await conn.execute('SET search_path TO "%s"' % schema)
            await conn.execute(PREREQ["336"])
            # Right name, wrong columns -- and it has to be creatable before
            # `kind` exists, so it is over two columns that are already there.
            await conn.execute(
                "CREATE INDEX idx_bug_reports_kind_created "
                "ON bug_reports (status, created_at)")
            try:
                await conn.execute(migration_text("336"))
            except asyncpg.exceptions.RaiseError as ex:
                # The file opened its own BEGIN, so the RAISE leaves this
                # connection in a failed transaction and every later
                # statement -- including the cleanup below -- is refused
                # until it is ended. Rolling back here is also the positive
                # part of the result: the refusal took the whole migration
                # with it rather than leaving half of it committed.
                await conn.execute("ROLLBACK")
                return str(ex)
            return None
        finally:
            try:
                await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
            finally:
                await conn.close()

    message = _run(_go())
    assert message is not None, (
        "336 applied cleanly over an index that carries the right name and "
        "indexes the wrong columns. Its post-check would then certify the "
        "retention sweep's access path on every future run without ever "
        "being able to fail.")
    assert "idx_bug_reports_kind_created" in message, message
    assert "(kind, created_at DESC)" in message, (
        "the refusal does not say what the index was supposed to be: %s"
        % message)


def _336_after_replacing(replacement_sql):
    """Apply 336, let an operator replace one of the objects it guards, apply
    336 again, and return the refusal -- or None if it applied cleanly.

    The replacement has to happen AFTER the first application, because every
    object this exercises is defined over the `kind` column 336 itself adds.
    That is also the real shape of the hazard: the guarded creations adopt
    whatever already carries the name, so it is the SECOND run that has to
    notice.
    """
    async def _go():
        schema = "m336swap_%s" % uuid.uuid4().hex[:10]
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute('CREATE SCHEMA "%s"' % schema)
            await conn.execute('SET search_path TO "%s"' % schema)
            await conn.execute(PREREQ["336"])
            await conn.execute(migration_text("336"))
            await conn.execute(replacement_sql)
            try:
                await conn.execute(migration_text("336"))
            except asyncpg.exceptions.RaiseError as ex:
                # The file opened its own BEGIN, so the RAISE leaves this
                # connection in a failed transaction until it is ended -- and
                # ending it here is also half the result: the refusal took the
                # whole migration with it.
                await conn.execute("ROLLBACK")
                return str(ex)
            return None
        finally:
            try:
                await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
            finally:
                await conn.close()

    return _run(_go())


def test_336_refuses_a_check_constraint_that_admits_a_third_kind():
    """The guarded ADD CONSTRAINT adopts any constraint already carrying the
    name, so the post-check is the only thing that reads its BODY -- and it
    used to read it by asking whether the literals 'report' and 'auto'
    APPEARED. `CHECK (kind IN ('report','auto','legacy'))` satisfies that
    while admitting a third value, and a row carrying it is read by neither
    consumer: the report feed filters kind = 'report' and the retention sweep
    filters kind = 'auto', so nothing announces it and nothing ever deletes
    it -- the state the constraint exists to make impossible.

    A check that passes for the case its own message says it excludes is
    worse than no check (#342/#441), so this plants that constraint and
    requires the refusal.
    """
    message = _336_after_replacing("""
        ALTER TABLE bug_reports DROP CONSTRAINT bug_reports_kind_known;
        ALTER TABLE bug_reports ADD CONSTRAINT bug_reports_kind_known
            CHECK (kind IN ('report', 'auto', 'legacy'));
    """)
    assert message is not None, (
        "336 applied cleanly over a constraint admitting a third kind, and "
        "then announced the column healthy. A row with that kind inserts, and "
        "falls out of the report feed and of the retention sweep alike.")
    assert "bug_reports_kind_known" in message, message
    assert "legacy" in message, (
        "the refusal does not say which value it objected to: %s" % message)


def test_336_refuses_a_check_constraint_whose_body_admits_everything():
    """THE LITERALS ARE NOT THE LOGIC.

    `CHECK (kind <> 'report' OR kind <> 'auto')` quotes exactly the two values
    this column is allowed to hold and no others, so a post-check that reads
    the VALUES out of the definition and compares the set finds the set it
    expects and passes. The predicate is a tautology: no value equals both
    literals at once, so one disjunct is always true and the constraint admits
    every string there is -- including the third kind whose row the report
    feed does not announce and the retention sweep does not collect.

    Same defect as the 'legacy' case above, one level deeper: a check that
    passes for the case its own message excludes (#342/#441). The set of
    literals is a property of how the predicate is SPELLED; what this column
    needs is a property of what it ADMITS. Planted here under the name the
    guarded ADD adopts, and the second application has to refuse it.
    """
    message = _336_after_replacing("""
        ALTER TABLE bug_reports DROP CONSTRAINT bug_reports_kind_known;
        ALTER TABLE bug_reports ADD CONSTRAINT bug_reports_kind_known
            CHECK (kind <> 'report' OR kind <> 'auto');
    """)
    assert message is not None, (
        "336 applied cleanly over a constraint that admits every value, and "
        "then announced the column healthy. Its two quoted literals are the "
        "two this column allows, so a check that reads only the literals "
        "certifies a column carrying no real constraint at all.")
    assert "bug_reports_kind_known" in message, message
    assert "<>" in message, (
        "the refusal does not print the body it objected to, so a reader "
        "cannot see what was adopted: %s" % message)


def test_336_accepts_the_constraint_it_writes_itself():
    """The negative control for both refusals above.

    A post-check strict enough to reject a tautology can also be strict enough
    to reject the file's own statement -- and it would do that on the SECOND
    run of every healthy deployment, where the constraint present is the one
    the first run wrote. Dropping and re-adding exactly that body has to leave
    the re-run clean, or the two refusals prove only that the check refuses
    everything it is shown.
    """
    message = _336_after_replacing("""
        ALTER TABLE bug_reports DROP CONSTRAINT bug_reports_kind_known;
        ALTER TABLE bug_reports ADD CONSTRAINT bug_reports_kind_known
            CHECK (kind IN ('report', 'auto'));
    """)
    assert message is None, (
        "336 refused the constraint its own ADD CONSTRAINT writes, so the "
        "post-check fails on the ordinary second run of a healthy "
        "deployment: %s" % message)


def _336_over_preexisting_kind(coltype, replacement_sql=None, runs=1):
    """Apply 336 to a `bug_reports` that ALREADY carries a `kind` column of
    `coltype`, and return the refusal from the last run -- or None.

    336's `ADD COLUMN` is guarded on EXISTENCE alone, so this is a state the
    file explicitly contemplates: its own default guard is written for "a
    hand-added or partially-applied column". The column the post-check
    measures against is therefore not always the column the file would have
    added, and the type is the part of that difference the constraint
    comparison can see.
    """
    base = PREREQ["336"] + (
        "ALTER TABLE bug_reports ADD COLUMN kind %s NOT NULL "
        "DEFAULT 'report';" % coltype)

    async def _go():
        schema = "m336ty_%s" % uuid.uuid4().hex[:10]
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute('CREATE SCHEMA "%s"' % schema)
            await conn.execute('SET search_path TO "%s"' % schema)
            await conn.execute(base)
            message = None
            for attempt in range(runs):
                if attempt and replacement_sql:
                    await conn.execute(replacement_sql)
                try:
                    await conn.execute(migration_text("336"))
                    message = None
                except asyncpg.exceptions.RaiseError as ex:
                    await conn.execute("ROLLBACK")
                    message = str(ex)
                    break
            return message
        finally:
            try:
                await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
            finally:
                await conn.close()

    return _run(_go())


def test_336_certifies_the_constraint_it_writes_over_a_text_kind_column():
    """THE EXPECTED RENDERING IS A PROPERTY OF THE COLUMN, NOT OF THE FILE.

    `pg_get_constraintdef` does not render one predicate one way.
    `CHECK (kind IN ('report','auto'))` comes back as
    `((kind)::text = ANY ((ARRAY[...])::text[]))` over `character varying` and
    as `(kind = ANY (ARRAY[...::text]))` over `text` -- same predicate, same
    admitted set, two strings.

    The post-check used to compare against the varchar rendering, written out
    as a constant. Over a pre-existing `text` kind that made the file REFUSE
    the constraint its own `ADD CONSTRAINT` had written seconds earlier, while
    telling the operator the name had been adopted from a constraint this file
    did not write. Both halves were wrong, and the printed remedy -- DROP
    CONSTRAINT and re-run -- reproduced the refusal for ever, because the
    re-run writes the same body again. Measured: the constraint count is 0
    immediately before each run and each run still refused.

    So the expected string is now DERIVED from this file's own predicate over
    THIS column's type, and this is the test that the derivation covers the
    type the constant did not.
    """
    message = _336_over_preexisting_kind("TEXT")
    assert message is None, (
        "336 refused its own constraint over a pre-existing text kind "
        "column, which is a state its own ADD COLUMN guard admits and its "
        "own default guard is written for: %s" % message)

    # And a second application is still clean -- the re-run is where the
    # adopted-by-name path actually runs.
    again = _336_over_preexisting_kind("TEXT", runs=2)
    assert again is None, (
        "336 applied over a text kind column once and refused on the "
        "re-run: %s" % again)


def test_336_still_refuses_a_tautological_body_over_a_text_kind_column():
    """THE NEGATIVE CONTROL FOR THE DERIVATION.

    A derived expected string is only worth having if it can still disagree.
    Derive it badly -- from whatever is in the catalog, say -- and the
    comparison becomes an identity that passes over every body there is,
    which is strictly worse than the hardcoded constant it replaced (#342).

    `CHECK (kind <> 'report' OR kind <> 'auto')` is the body that admits every
    value while quoting exactly the two allowed literals. Planted here under
    the adopted name over a `text` column, i.e. in the very state the
    derivation exists to serve, it still has to be refused.
    """
    message = _336_over_preexisting_kind("TEXT", runs=2, replacement_sql="""
        ALTER TABLE bug_reports DROP CONSTRAINT bug_reports_kind_known;
        ALTER TABLE bug_reports ADD CONSTRAINT bug_reports_kind_known
            CHECK (kind <> 'report' OR kind <> 'auto');
    """)
    assert message is not None, (
        "336 adopted a body admitting every value over a text kind column. "
        "The derivation made the comparison vacuous rather than correct.")
    assert "bug_reports_kind_known" in message, message
    assert "<>" in message, (
        "the refusal does not print the body it objected to: %s" % message)
    assert "text" in message, (
        "the refusal does not name the column type it measured the expected "
        "rendering over, so a reader cannot tell which rendering it wanted: "
        "%s" % message)
    assert "did not write" not in message, (
        "the refusal still claims the constraint was adopted from one this "
        "file did not write. That sentence has to be true in every state the "
        "check can refuse in: %s" % message)


def test_336_refuses_a_same_named_index_that_is_unique_or_partial():
    """The column list is not the whole identity of an index.

    Both of these carry the right name AND the right columns, and neither is
    the index this file means. A UNIQUE one turns two auto uploads that share
    a created_at into an INSERT failure on a live route; a partial one indexes
    a subset, so the sweep's range scan is unserved for exactly the rows it
    was built to find. `pg_get_indexdef` matched on its column list accepts
    both, which is why uniqueness and the predicate are read from the catalog
    beside it.
    """
    unique = _336_after_replacing("""
        DROP INDEX idx_bug_reports_kind_created;
        CREATE UNIQUE INDEX idx_bug_reports_kind_created
            ON bug_reports (kind, created_at DESC);
    """)
    assert unique is not None, (
        "336 adopted a UNIQUE index over (kind, created_at DESC); a second "
        "auto upload in the same instant would then fail to insert")
    assert "UNIQUE" in unique, unique

    partial = _336_after_replacing("""
        DROP INDEX idx_bug_reports_kind_created;
        CREATE INDEX idx_bug_reports_kind_created
            ON bug_reports (kind, created_at DESC) WHERE kind = 'report';
    """)
    assert partial is not None, (
        "336 adopted a PARTIAL index over (kind, created_at DESC) -- one that "
        "excludes every row the retention sweep reads")
    assert "WHERE clause" in partial, partial


_READY_ENTRY_RUNGS = (
    "SELECT count(*) FROM title_ladders tl "
    "JOIN shop_items si ON si.sku = tl.sku "
    "WHERE tl.tier = 1 AND si.catalog_ready IS TRUE")


def test_331_clears_a_rung_flipped_ready_before_the_activation_release():
    """The re-run this file's own header offers as the remedy.

    A tier-1 rung can end up `catalog_ready = TRUE` before the activation
    release: a hand edit, a half-applied activation, an operator trying the
    shop. It is then listed by /shop/items at 1000 gold for a ladder whose
    progression hook is not wired, and re-applying 331 is what is supposed to
    take it back off sale.

    Gating the repair on "has this file run before" removed that: on the
    re-run the gate was closed, nothing cleared the flag, and the post-check
    reported it as the activation release's doing. The gate is the COUNT
    instead -- eight of eight is the activation release and is left alone,
    anything less is a partial state no release produces -- so this is the
    case that must be repaired, and `test_331_does_not_revoke_a_later_
    activation` is the case that must not.
    """
    async def _go(flip_lines):
        schema = "m331ready_%s" % uuid.uuid4().hex[:10]
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute('CREATE SCHEMA "%s"' % schema)
            await conn.execute('SET search_path TO "%s"' % schema)
            await conn.execute(PREREQ["331"])
            sql = migration_text("331")
            await conn.execute(sql)
            await conn.execute(
                "UPDATE shop_items si SET catalog_ready = TRUE "
                "  FROM title_ladders tl "
                " WHERE tl.sku = si.sku AND tl.tier = 1 "
                "   AND tl.line = ANY($1::text[])", flip_lines)
            before = await conn.fetchval(_READY_ENTRY_RUNGS)
            await conn.execute(sql)
            return before, await conn.fetchval(_READY_ENTRY_RUNGS)
        finally:
            try:
                await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
            finally:
                await conn.close()

    before, after = _run(_go(["rat"]))
    assert before == 1, (
        "the fixture did not put a single tier-1 rung on sale (%d), so the "
        "assertion below would be about nothing" % before)
    assert after == 0, (
        "%d tier-1 rung(s) are still catalog_ready after re-applying 331 over "
        "a rung flipped ready early. The file's header offers this re-run as "
        "the remedy, so the rung stays on sale at 1000 gold for a ladder that "
        "cannot advance." % after)


def test_332_states_its_own_bound_correctly():
    """The candidate count in 332's prose, checked against the expression.

    `generate_series` is inclusive at both ends, so the bound N yields N+1
    candidates and the last of them is 4N months past the seed. The comment
    said "40 years -- 120 candidates", which is one candidate out. Harmless
    in itself; it is the number a reader reasons with when the seed moves, and
    it sits in the same paragraph that says the derivation cannot run away.

    Both numbers are DERIVED from the shipped expression here rather than
    retyped, so moving the bound moves what this test demands (#342).
    """
    sql = migration_text("332")
    match = re.search(r"-- @m332-anchor-begin\n(.*?)\n-- @m332-anchor-end",
                      sql, re.S)
    assert match, "332's derivation no longer sits between the @m332 markers"
    series = re.search(r"generate_series\(0,\s*(\d+)\)", match.group(1))
    assert series, (
        "the derivation no longer generates its candidates with "
        "generate_series(0, N); this test reads N out of it: %s" % match.group(1))
    bound = int(series.group(1))
    assert "%d candidates" % (bound + 1) in sql, (
        "the file does not state its candidate count as %d, which is what "
        "generate_series(0, %d) produces -- it is inclusive at both ends"
        % (bound + 1, bound))
    assert "%d months" % (4 * bound) in sql, (
        "the file does not state the span of the series as %d months, which "
        "is where generate_series(0, %d) in four-month steps ends"
        % (4 * bound, bound))
