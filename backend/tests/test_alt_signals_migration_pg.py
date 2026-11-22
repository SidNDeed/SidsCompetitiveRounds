"""Migration 427 (alt signals) and its rollback.

The pure cases read the two files: the mark is the digest of the file's own
DDL block, the FAQ texts are derived from 338 and agree between the two
files, the FAQ step is not selected by the full-schema DDL replay, and both
files hold the house holding bound.

The live cases apply the files to a throwaway schema on a PostgreSQL cluster:

    SCR_MIGRATION_TEST_PG_DSN=postgresql://user@host:port/<test database>

Without the DSN the live cases FAIL rather than skip, as in
test_migration_reruns.py; SCR_MIGRATION_TEST_PG_OPTOUT=1 waives them
deliberately.
"""
import asyncio
import hashlib
import os
import re
import uuid
from pathlib import Path

import pytest

try:
    import asyncpg
except ImportError:  # pragma: no cover - reported by the live fixture
    asyncpg = None

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
F427 = SQL_DIR / "427_alt_signals.sql"
R427 = SQL_DIR / "rollback_427_alt_signals.sql"
F338 = SQL_DIR / "338_faq_channel_post_revisions.sql"

DSN_VAR = "SCR_MIGRATION_TEST_PG_DSN"
OPTOUT_VAR = "SCR_MIGRATION_TEST_PG_OPTOUT"
DSN = (os.environ.get(DSN_VAR) or "").replace("postgresql+asyncpg://", "postgresql://")
OPTOUT = os.environ.get(OPTOUT_VAR) == "1"

TABLES = ("conn_markers", "steam_family_shares", "steam_signin_facts")
_MARK = re.compile(r"'alt signals, DDL sha256 ([0-9a-f]{64})'")


def _text(path):
    return path.read_text(encoding="utf-8")


def _quoted(text, tag):
    return re.findall(r"\$%s\$(.*?)\$%s\$" % (tag, tag), text, re.S)


def _one(items, what):
    assert len(items) == 1, "%s: %d found, not 1" % (what, len(items))
    return items[0]


def _faq_channel():
    """The FAQ channel id, read from 338's own UPDATE (never typed here)."""
    return _one(re.findall(r"WHERE p\.channel_id = '(\d+)'", _text(F338)), "338's channel id")


def _was():
    return _one(_quoted(_text(F338), "faq1"), "338's $faq1$")


def _new():
    return _one(_quoted(_text(F427), "faq1"), "427's $faq1$")


def _ddl_lines(text):
    lines = text.replace("\r\n", "\n").split("\n")
    starts = [i for i, s in enumerate(lines) if s.strip() == "-- DDL START"]
    ends = [i for i, s in enumerate(lines) if s.strip() == "-- DDL END"]
    assert len(starts) == 1 and len(ends) == 1 and starts[0] < ends[0], (starts, ends)
    return lines[starts[0] + 1:ends[0]]


def _ddl_digest(text):
    keep = [s.strip() for s in _ddl_lines(text)]
    body = "\n".join(s for s in keep if s and not s.startswith("--"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _mark_defects(text, ddl_source=None):
    """[] when every mark the text holds is the digest of the DDL block
    (the text's own, or ddl_source's for the rollback, which has none)."""
    marks = _MARK.findall(text)
    if not marks:
        return ["no mark"]
    want = _ddl_digest(ddl_source if ddl_source is not None else text)
    return ["mark %s, digest %s" % (m, want) for m in marks if m != want]


# -- pure: the files themselves ----------------------------------------------

def test_427_marks_are_the_digest_of_its_own_ddl():
    """Both of 427's marks and the rollback's mark are the SHA-256 of 427's
    DDL block, so the statements cannot change without the mark. Negative
    control: one changed DDL token (a type, an index's columns, a check's
    values, a NOT NULL) fails; a comment line or an indent does not."""
    real = _text(F427)
    assert len(_MARK.findall(real)) == 2
    assert _mark_defects(real) == []
    assert len(_MARK.findall(_text(R427))) == 1
    assert _mark_defects(_text(R427), ddl_source=real) == []
    mutants = {
        "a column type": ("      family      SMALLINT    NOT NULL,", "      family      INTEGER     NOT NULL,"),
        "an index's columns": ("ON conn_markers (last_at);", "ON conn_markers (last_at, day);"),
        "a check's values": ("CHECK (family IN (4, 6))", "CHECK (family IN (4, 6, 0))"),
        "a NOT NULL": ("      owner_mark     BYTEA       NOT NULL,", "      owner_mark     BYTEA       NULL,"),
    }
    for name, (old, new) in mutants.items():
        assert real.count(old) == 1, name
        assert _mark_defects(real.replace(old, new)), "%s left the mark matching" % name
    inert = real.replace("    -- DDL END", "    -- a comment line inside the block\n    -- DDL END")
    inert = inert.replace("    CREATE INDEX ix_conn_markers_last_at", "        CREATE INDEX ix_conn_markers_last_at")
    assert inert != real and _mark_defects(inert) == []
    assert "427" not in "\n".join(_ddl_lines(real))


def test_427_faq_texts_are_derived_and_agree_with_the_rollback():
    """427 carries 338's message 1 as the earlier text and adds one closing
    paragraph; the rollback carries the same two texts under its own tags;
    the new text fits one Discord message; no file but 427 carries a second
    $faq1$ literal of its own."""
    was, new = _was(), _new()
    t427, trb = _text(F427), _text(R427)
    assert _one(_quoted(t427, "faq1was"), "427's $faq1was$") == was
    assert new.startswith(was + "\n\n")
    added = new[len(was) + 2:]
    assert added and "\n\n" not in added, "427 adds exactly one paragraph"
    assert len(new) <= 2000, len(new)
    assert _one(_quoted(trb, "faq1was"), "rollback's $faq1was$") == was
    assert _one(_quoted(trb, "faq1now"), "rollback's $faq1now$") == new
    assert not _quoted(trb, "faq1"), "the rollback carries no $faq1$ literal"


_DDL_COLUMN = re.compile(r"^\s*([a-z_]+)\s+(TEXT|TIMESTAMPTZ|VARCHAR\(8\)|BOOLEAN|INTEGER|DATE|BYTEA|SMALLINT)"
                         r"\s+(NOT NULL|NULL)\b")


def _ddl_columns(text):
    """{table: [(column, type, nullable)]} read from 427's DDL block."""
    out, current = {}, None
    for line in _ddl_lines(text):
        m = re.match(r"\s*CREATE TABLE ([a-z_]+) \($", line)
        if m:
            current = out.setdefault(m.group(1), [])
            continue
        if current is None:
            continue
        m = _DDL_COLUMN.match(line)
        if m:
            current.append((m.group(1), m.group(2), m.group(3) == "NULL"))
        elif line.strip().startswith(");"):
            current = None
    return out


def _orm_columns():
    import sys
    api = str(Path(__file__).resolve().parents[1] / "api")
    if api not in sys.path:
        sys.path.insert(0, api)
    import models
    from sqlalchemy.dialects import postgresql
    names = {"TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ"}
    out = {}
    for t in TABLES:
        out[t] = [(c.name, names.get(c.type.compile(dialect=postgresql.dialect()),
                                     c.type.compile(dialect=postgresql.dialect())), c.nullable)
                  for c in models.Base.metadata.tables[t].columns]
    return out


def test_the_orm_classes_match_427_column_for_column():
    """models.py declares the three tables as 427 makes them (name, type,
    nullability, in order), so a harness that builds from the ORM builds the
    same columns and no column exists in one place only. Negative control: a
    renamed DDL column, a changed type and a changed nullability each differ."""
    t = _text(F427)
    ddl = _ddl_columns(t)
    assert set(ddl) == set(TABLES) and all(ddl.values()), ddl
    assert ddl == _orm_columns()
    for old, new in (("      over_limit_day             DATE", "      over_limit_dayx            DATE"),
                     ("      family      SMALLINT    NOT NULL,", "      family      INTEGER     NOT NULL,"),
                     ("      vac_banned                 BOOLEAN     NULL", "      vac_banned                 BOOLEAN     NOT NULL")):
        assert t.count(old) == 1, old
        assert _ddl_columns(t.replace(old, new)) != _orm_columns(), old


# The full-schema DDL replay (test_title_ladder_hooks_live.py `_DO_DDL`)
# runs every DO block that names one of these; the FAQ step must not be one
# of them, or the replay would run it against a schema with no FAQ row. The
# table step must be, so the replay builds the three tables.
_REPLAY_SELECTOR = re.compile(r"\b(ALTER\s+TABLE|CREATE\s+(?:UNIQUE\s+)?INDEX|CREATE\s+TABLE"
                              r"|ADD\s+COLUMN)\b", re.I)


def _do_blocks(text):
    return re.findall(r"^DO (\$\w+\$).*?\1;", text, re.S | re.M)


def _do_block(text, tag):
    m = re.search(r"^DO \$%s\$.*?\$%s\$;" % (tag, tag), text, re.S | re.M)
    assert m, tag
    return m.group(0)


def test_427_replay_selects_the_table_step_and_not_the_faq_step():
    t = _text(F427)
    assert _do_blocks(t) == ["$m427path$", "$m427tables$", "$m427faq$", "$m427check$"]
    assert _REPLAY_SELECTOR.search(_do_block(t, "m427tables"))
    for tag in ("m427path", "m427faq", "m427check"):
        assert not _REPLAY_SELECTOR.search(_do_block(t, tag)), tag
    # The replay skips a statement naming `pg_temp.`; the table step must
    # not be one, or the replay would not build the three tables.
    assert not re.search(r"\bpg_temp\.", _do_block(t, "m427tables"))


_SETS = ("SET LOCAL lock_timeout = '5s';",
         "SET LOCAL idle_in_transaction_session_timeout = '5s';",
         "SET LOCAL statement_timeout = '25s';",
         "SET LOCAL synchronous_commit = local;")


def _hold_problems(text):
    """The house holding bound (lesson 1072): BEGIN, then exactly the four
    SET LOCAL lines, the two budgets summing to 30 s or less, exactly one
    synchronous_commit line and it is local, and COMMIT as the last line."""
    body = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n")
            if ln.strip() and not ln.strip().startswith("--")]
    out = []
    if "BEGIN;" not in body:
        return ["no BEGIN;"]
    i = body.index("BEGIN;")
    sets = []
    for ln in body[i + 1:]:
        if not ln.startswith("SET LOCAL"):
            break
        sets.append(ln)
    secs = {}
    for ln in sets:
        m = re.match(r"SET LOCAL (statement_timeout|idle_in_transaction_session_timeout) = '(\d+)s';$", ln)
        if m:
            secs[m.group(1)] = int(m.group(2))
    if set(secs) != {"statement_timeout", "idle_in_transaction_session_timeout"}:
        out.append("the two budgets are not both set: %r" % sets)
    elif sum(secs.values()) > 30:
        out.append("budgets sum to %d s" % sum(secs.values()))
    sync = [ln for ln in body if ln.startswith("SET LOCAL synchronous_commit")]
    if sync != ["SET LOCAL synchronous_commit = local;"] or sync[0] not in sets:
        out.append("synchronous_commit lines: %r" % sync)
    if not any(ln.startswith("SET LOCAL lock_timeout") for ln in sets):
        out.append("no lock_timeout")
    if body[-1] != "COMMIT;":
        out.append("last line %r" % body[-1])
    return out


def test_427_and_its_rollback_hold_the_house_bound():
    for path in (F427, R427):
        t = _text(path)
        assert _hold_problems(t) == [], (path.name, _hold_problems(t))
        for line in _SETS:
            assert t.count(line) == 1, (path.name, line)
    # Negative control: each defect is refused.
    t = _text(F427)
    assert _hold_problems(t.replace("statement_timeout = '25s'", "statement_timeout = '30s'"))
    assert _hold_problems(t.replace("SET LOCAL synchronous_commit = local;", ""))
    assert _hold_problems(t.replace("synchronous_commit = local", "synchronous_commit = on"))
    assert _hold_problems(t.replace("\nCOMMIT;", "\nCOMMIT;\nSELECT 1;"))


# -- live --------------------------------------------------------------------

@pytest.fixture
def live():
    if DSN and asyncpg is not None:
        return DSN
    if OPTOUT:
        pytest.skip("%s is unset and %s=1: live cases deliberately waived" % (DSN_VAR, OPTOUT_VAR))
    pytest.fail("%s is unset (or asyncpg missing), so 427 was never applied; set it, or %s=1 to "
                "waive the live cases deliberately" % (DSN_VAR, OPTOUT_VAR))


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(asyncio.wait_for(coro, 120))
    finally:
        loop.close()


_PCP = ("CREATE TABLE pending_channel_posts ("
        " id BIGSERIAL PRIMARY KEY, channel_id TEXT NOT NULL, content TEXT NOT NULL,"
        " sort_order INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        " posted_at TIMESTAMPTZ, revision INTEGER NOT NULL DEFAULT 1, posted_revision INTEGER)")

_STATE = (
    "SELECT string_agg(x, '; ' ORDER BY x) FROM ("
    " SELECT format('%s %s %s', c.relname, c.relkind, coalesce(obj_description(c.oid, 'pg_class'), '-')) AS x"
    "   FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = $1"
    " UNION ALL"
    " SELECT format('%s.%s %s', t.relname, k.conname, pg_get_constraintdef(k.oid))"
    "   FROM pg_constraint k JOIN pg_class t ON t.oid = k.conrelid"
    "   JOIN pg_namespace n ON n.oid = t.relnamespace WHERE n.nspname = $1"
    " UNION ALL"
    " SELECT format('row %s %s %s %s %s %s', p.id, p.sort_order, md5(p.content), p.revision,"
    "               coalesce(p.posted_revision::text, '-'), p.xmin::text)"
    "   FROM pending_channel_posts p) s")


class _Case:
    def __init__(self, rows, setup=""):
        self.rows, self.setup = rows, setup
        self.schema = "m427_%s" % uuid.uuid4().hex[:10]
        self.conn = None

    async def __aenter__(self):
        self.conn = await asyncpg.connect(DSN)
        await self.conn.execute('CREATE SCHEMA "%s"' % self.schema)
        await self.conn.execute('SET search_path TO "%s"' % self.schema)
        await self.conn.execute(_PCP)
        for sort_order, content, rev, posted in self.rows:
            await self.conn.execute(
                "INSERT INTO pending_channel_posts (channel_id, content, sort_order, revision, posted_revision)"
                " VALUES ($1, $2, $3, $4, $5)", _faq_channel(), content, sort_order, rev, posted)
        if self.setup:
            await self.conn.execute(self.setup)
        return self

    async def __aexit__(self, *exc):
        try:
            await self.conn.execute("ROLLBACK")
        except Exception:
            pass
        try:
            await self.conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % self.schema)
        finally:
            await self.conn.close()

    async def apply(self, sql):
        """Run a file; on a refusal roll the aborted transaction back and
        return the message, else return None."""
        try:
            await self.conn.execute(sql)
            return None
        except asyncpg.PostgresError as e:
            await self.conn.execute("ROLLBACK")
            return str(e)

    async def state(self):
        return await self.conn.fetchval(_STATE, self.schema)

    async def msg(self, sort_order):
        return await self.conn.fetchrow(
            "SELECT content, revision, posted_revision, xmin::text AS xmin FROM pending_channel_posts"
            " WHERE sort_order = $1", sort_order)

    async def tables(self):
        return {r["relname"]: (r["relkind"], r["c"]) for r in await self.conn.fetch(
            "SELECT c.relname, c.relkind::text AS relkind, obj_description(c.oid, 'pg_class') AS c"
            "  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = $1 AND c.relname = ANY($2::text[])", self.schema, list(TABLES))}


def _mark_text():
    return "alt signals, DDL sha256 %s" % _ddl_digest(_text(F427))


def test_427_first_run_creates_three_marked_tables_and_revises_message_1_once(live):
    async def go():
        async with _Case([(1, _was(), 2, 2), (2, "message two", 2, 2)]) as c:
            two = await c.msg(2)
            assert await c.apply(_text(F427)) is None
            assert await c.tables() == {t: ("r", _mark_text()) for t in TABLES}
            one = await c.msg(1)
            assert (one["content"], one["revision"], one["posted_revision"]) == (_new(), 3, 2)
            assert await c.msg(2) == two
    _run(go())


def test_427_second_run_writes_nothing_and_takes_no_lock_on_the_tables_or_the_row(live):
    """A second run completes while another session holds ACCESS EXCLUSIVE on
    the three tables and a row lock on message 1, and leaves every relation,
    constraint and row (xmin included) as it was. Negative control: a copy
    whose FAQ step writes on every run is stopped by the held row lock."""
    async def second_run(sql_second):
        async with _Case([(1, _was(), 2, 2), (2, "message two", 2, 2)]) as c:
            assert await c.apply(_text(F427)) is None
            before = await c.state()
            other = await asyncpg.connect(DSN)
            try:
                await other.execute('SET search_path TO "%s"' % c.schema)
                await other.execute("BEGIN")
                await other.execute("LOCK TABLE %s IN ACCESS EXCLUSIVE MODE" % ", ".join(
                    '"%s".%s' % (c.schema, t) for t in TABLES))
                await other.execute("SELECT 1 FROM pending_channel_posts WHERE sort_order = 1 FOR UPDATE")
                refused = await c.apply(sql_second)
            finally:
                await other.execute("ROLLBACK")
                await other.close()
            return refused, before, await c.state()

    refused, before, after = _run(second_run(_text(F427)))
    assert refused is None and after == before

    writes_always = _text(F427).replace(
        "  IF rows_all = 1 AND rows_was = 1 THEN", "  IF rows_all = 1 THEN").replace(
        " AND p.sort_order = 1 AND p.content = was;", " AND p.sort_order = 1;")
    assert writes_always != _text(F427)
    refused, before, after = _run(second_run(writes_always))
    assert refused and "lock" in refused.lower() and after == before, refused


@pytest.mark.parametrize("name,rows", [
    ("absent", [(2, "message two", 2, 2)]),
    ("two rows holding 338's text", [(1, "@was", 2, 2), (1, "@was", 2, 2)]),
    ("a third text", [(1, "@was edited", 3, 3)]),
    ("338's text beside the new text", [(1, "@was", 2, 2), (1, "@new", 3, 3)]),
])
def test_427_refuses_every_other_faq_state_and_commits_nothing(live, name, rows):
    real = [(s, c.replace("@was", _was()).replace("@new", _new()), r, p) for s, c, r, p in rows]

    async def go():
        async with _Case(real) as c:
            before = await c.state()
            refused = await c.apply(_text(F427))
            assert refused and "427: FAQ message 1" in refused, (name, refused)
            assert await c.state() == before
            assert await c.tables() == {}
    _run(go())


@pytest.mark.parametrize("name,setup", [
    ("one table present", "CREATE TABLE conn_markers (x int)"),
    ("all three unmarked", "CREATE TABLE conn_markers (x int); CREATE TABLE steam_family_shares (x int);"
                           " CREATE TABLE steam_signin_facts (x int)"),
    ("all three marked otherwise",
     "CREATE TABLE conn_markers (x int); CREATE TABLE steam_family_shares (x int);"
     " CREATE TABLE steam_signin_facts (x int);"
     " COMMENT ON TABLE conn_markers IS 'alt signals, DDL sha256 %s';"
     " COMMENT ON TABLE steam_family_shares IS 'alt signals, DDL sha256 %s';"
     " COMMENT ON TABLE steam_signin_facts IS 'alt signals, DDL sha256 %s'" % (("0" * 64,) * 3)),
    ("a view of one name", "CREATE VIEW steam_signin_facts AS SELECT 1 AS x"),
    ("an index name taken", "CREATE TABLE other_t (a int); CREATE INDEX ix_conn_markers_addr ON other_t (a)"),
    ("a row type taken", "CREATE TYPE steam_family_shares AS (a int)"),
])
def test_427_refuses_every_other_table_state_and_changes_nothing(live, name, setup):
    async def go():
        async with _Case([(1, _was(), 2, 2)], setup=setup) as c:
            before = await c.state()
            refused = await c.apply(_text(F427))
            assert refused and refused.startswith("427:"), (name, refused)
            assert await c.state() == before
    _run(go())


def test_rollback_427_drops_the_marked_tables_and_restores_message_1(live):
    async def go():
        async with _Case([(1, _was(), 2, 2)]) as c:
            assert await c.apply(_text(F427)) is None
            assert await c.apply(_text(R427)) is None
            assert await c.tables() == {}
            one = await c.msg(1)
            assert (one["content"], one["revision"], one["posted_revision"]) == (_was(), 4, 2)
            before = await c.state()
            assert await c.apply(_text(R427)) is None
            assert await c.state() == before
    _run(go())


def test_rollback_427_without_427_changes_nothing(live):
    async def go():
        async with _Case([(1, _was(), 2, 2)]) as c:
            before = await c.state()
            assert await c.apply(_text(R427)) is None
            assert await c.state() == before
    _run(go())


@pytest.mark.parametrize("name,edit", [
    ("an unmarked table", "COMMENT ON TABLE conn_markers IS 'something else'"),
    ("message 1 revised again", "UPDATE pending_channel_posts SET content = content || ' (later)',"
                                " revision = revision + 1 WHERE sort_order = 1"),
])
def test_rollback_427_refuses_what_is_not_427s_and_changes_nothing(live, name, edit):
    async def go():
        async with _Case([(1, _was(), 2, 2)]) as c:
            assert await c.apply(_text(F427)) is None
            await c.conn.execute(edit)
            before = await c.state()
            refused = await c.apply(_text(R427))
            assert refused and refused.startswith("rollback 427:"), (name, refused)
            assert await c.state() == before
    _run(go())
