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


# Every statement form that makes or changes a column (holder H3): ALTER of
# a table, foreign table, view, type or domain; CREATE of a table in any
# form (UNLOGGED, TEMP, IF NOT EXISTS, AS, OF, PARTITION OF), of a view or
# materialized view, of a type or a domain; SELECT ... INTO TEMP, UNLOGGED
# or TABLE.
# Case and line breaks do not matter; comments are not read.
_COLUMN_MAKER = re.compile(
    r"\bALTER\s+(?:FOREIGN\s+TABLE|TABLE|MATERIALIZED\s+VIEW|VIEW|TYPE|DOMAIN)\b"
    r"|\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:GLOBAL|LOCAL)\s+)?(?:TEMPORARY\s+|TEMP\s+|UNLOGGED\s+|FOREIGN\s+)?"
    r"(?:TABLE|MATERIALIZED\s+VIEW|VIEW|TYPE|DOMAIN)\b"
    r"|\bINTO\s+(?:TEMPORARY|TEMP|UNLOGGED|TABLE)\b", re.I)
_PLAIN_CREATE = re.compile(r"^\s*CREATE TABLE [a-z_]+ \($")


def _ddl_outside(text):
    """Every statement of `text` that makes or changes a column and that
    this file's DDL reader does not read, as "line N: text": anything the
    closed form above finds, except a plain `CREATE TABLE <name> (` line
    inside the DDL block. LIMIT: a statement whose words are built at run
    time (concatenated strings) and a SELECT ... INTO with no keyword after
    INTO are not seen."""
    lines = text.replace("\r\n", "\n").split("\n")
    starts = [i for i, s in enumerate(lines) if s.strip() == "-- DDL START"]
    ends = [i for i, s in enumerate(lines) if s.strip() == "-- DDL END"]
    block = range(starts[0] + 1, ends[0]) if len(starts) == 1 and len(ends) == 1 else range(0)
    bare = "\n".join(re.sub(r"--.*$", "", s) for s in lines)
    out = []
    for m in _COLUMN_MAKER.finditer(bare):
        i = bare.count("\n", 0, m.start())
        if i in block and _PLAIN_CREATE.match(lines[i]):
            continue
        out.append("line %d: %s" % (i + 1, lines[i].strip()))
    return out


def _ddl_columns(text):
    """{table: [(column, type, nullable)]} read from 427's DDL block; a
    statement outside the block's CREATE TABLE bodies that makes or changes
    a column is refused, naming its line (H3)."""
    outside = _ddl_outside(text)
    if outside:
        raise AssertionError("a statement outside a CREATE TABLE body that makes or changes a column: %s"
                             % "; ".join(outside))
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
        elif line.strip() and not line.strip().startswith(("CONSTRAINT ", "--")):
            # M2: a line of a CREATE TABLE body the reader does not know.
            raise AssertionError("a CREATE TABLE line the DDL reader does not know: %r" % line.strip())
    return out


_ORM_TYPES = frozenset({"TEXT", "TIMESTAMPTZ", "VARCHAR(8)", "BOOLEAN", "INTEGER", "DATE", "BYTEA", "SMALLINT"})


def _orm_columns(metadata=None):
    """{table: [(column, type, nullable)]} of models.py's three tables (or of
    `metadata`'s); a column of a type the reader does not know is refused
    by name (M2)."""
    import sys
    api = str(Path(__file__).resolve().parents[1] / "api")
    if api not in sys.path:
        sys.path.insert(0, api)
    import models
    from sqlalchemy.dialects import postgresql
    metadata = metadata if metadata is not None else models.Base.metadata
    names = {"TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ"}
    out = {}
    for t in TABLES:
        out[t] = []
        for c in metadata.tables[t].columns:
            typ = c.type.compile(dialect=postgresql.dialect())
            typ = names.get(typ, typ)
            if typ not in _ORM_TYPES:
                raise AssertionError("a model column of a type the reader does not know: %s.%s %s"
                                     % (t, c.name, typ))
            out[t].append((c.name, typ, c.nullable))
    return out


def test_each_reader_refuses_a_column_of_a_type_it_does_not_know():
    """Finding R2-5 (M2), both readers. A BIGINT column added to a copy of
    427's text, and one added to a copy of models.py's table, are each
    refused by name."""
    import models
    from sqlalchemy import BigInteger, Column, MetaData
    t = _text(F427)
    old = "      family      SMALLINT    NOT NULL,\n"
    assert t.count(old) == 1
    grown = t.replace(old, old + "      port        BIGINT      NULL,\n")
    with pytest.raises(AssertionError, match=r"DDL reader does not know: 'port +BIGINT +NULL,'"):
        _ddl_columns(grown)
    md = MetaData()
    for name in TABLES:
        models.Base.metadata.tables[name].to_metadata(md)
    md.tables["conn_markers"].append_column(Column("port", BigInteger, nullable=True))
    with pytest.raises(AssertionError, match=r"conn_markers\.port BIGINT"):
        _orm_columns(md)


# Plants of holder H3, each placed on the line after 427's `-- DDL END`.
_OUTSIDE_PLANTS = ("ALTER TABLE conn_markers ADD COLUMN port BIGINT NULL;",
                   "alter table conn_markers add port bigint;",
                   "CREATE UNLOGGED TABLE alt_plant (a TEXT NOT NULL);",
                   "CREATE TEMP TABLE alt_plant (a TEXT NOT NULL);",
                   "CREATE TABLE IF NOT EXISTS alt_plant (a TEXT NOT NULL);",
                   "CREATE TABLE alt_plant AS SELECT 1 AS a;",
                   "CREATE TABLE alt_plant (",
                   "CREATE VIEW alt_plant AS SELECT 1 AS a;",
                   "SELECT 1 AS a INTO TEMP alt_plant;",
                   "ALTER\n      TABLE conn_markers ADD port BIGINT;",
                   "CREATE TABLE alt_plant OF alt_type;",
                   "CREATE TABLE alt_plant PARTITION OF conn_markers FOR VALUES IN (1);",
                   "CREATE FOREIGN TABLE alt_plant (a TEXT) SERVER alt_server;",
                   "ALTER FOREIGN TABLE alt_plant ADD COLUMN b TEXT;",
                   "CREATE OR REPLACE VIEW alt_plant AS SELECT 1 AS a;",
                   "CREATE MATERIALIZED VIEW alt_plant AS SELECT 1 AS a;",
                   "ALTER VIEW alt_plant RENAME COLUMN a TO b;",
                   "CREATE TYPE alt_type AS (a TEXT);",
                   "ALTER TYPE alt_type ADD ATTRIBUTE b TEXT;",
                   "CREATE DOMAIN alt_domain AS TEXT;",
                   "ALTER DOMAIN alt_domain SET NOT NULL;")


def _plant_outside(text, plant):
    end = "    -- DDL END\n"
    assert text.count(end) == 1
    line = text[:text.index(end)].count("\n") + 2
    return text.replace(end, end + "    " + plant + "\n", 1), line


def test_the_ddl_reader_refuses_a_written_statement_that_makes_a_column_outside_a_create_table_body():
    """Holder H3 (M2): the real 427 holds no such statement; each plant is
    refused with its line named, and a CREATE TABLE line of the reader's
    own form is refused when it stands outside the DDL block."""
    t = _text(F427)
    assert _ddl_outside(t) == []
    for plant in _OUTSIDE_PLANTS:
        grown, line = _plant_outside(t, plant)
        with pytest.raises(AssertionError, match=r"outside a CREATE TABLE body .*line %d: " % line):
            _ddl_columns(grown)


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


_DOLLAR = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def _statements(text):
    """The top-level statements of `text`, in order, each stripped: split at
    a semicolon outside a line comment, a quoted string and a dollar-quoted
    body. A text left after the last semicolon is returned as a statement
    (and is refused by the closed list below)."""
    out, cur, i, n = [], [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("--", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "'":
            j = text.find("'", i + 1)
            while j >= 0 and text.startswith("''", j):
                j = text.find("'", j + 2)
            j = n if j < 0 else j + 1
            cur.append(text[i:j])
            i = j
            continue
        m = _DOLLAR.match(text, i) if c == "$" else None
        if m:
            j = text.find(m.group(0), m.end())
            j = n if j < 0 else j + len(m.group(0))
            cur.append(text[i:j])
            i = j
            continue
        if c == ";":
            out.append(("".join(cur) + ";").strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    rest = "".join(cur).strip()
    if rest:
        out.append(rest)
    return out


# The closed list of guarded top-level forms (finding R2-8): the house's
# BEGIN, its four SET LOCAL lines, DO blocks (each step's body is read by
# its own holders), and COMMIT. Anything else is refused by name.
_GUARDED_FORMS = (re.compile(r"^BEGIN;$"),
                  re.compile(r"^SET LOCAL (lock_timeout|idle_in_transaction_session_timeout|statement_timeout)"
                             r" = '\d+s';$"),
                  re.compile(r"^SET LOCAL synchronous_commit = local;$"),
                  re.compile(r"^DO (\$[A-Za-z_][A-Za-z0-9_]*\$).*\1;$", re.S),
                  re.compile(r"^COMMIT;$"))


def _unguarded(text):
    """Every top-level statement of `text` outside the closed list."""
    return [s for s in _statements(text) if not any(p.match(s) for p in _GUARDED_FORMS)]


def test_every_top_level_statement_is_a_guarded_form():
    """Finding R2-8 (M2). Every top-level statement of 427 and of its
    rollback is on the closed list; the count of statements the house
    bound covers is stated beside finding 15's sentence. Plants: an
    unguarded statement before COMMIT, one after it, a bare DDL statement
    and an unterminated tail are each refused by name."""
    counts = {}
    for path in (F427, R427):
        t = _text(path)
        assert _unguarded(t) == [], (path.name, _unguarded(t))
        stmts = _statements(t)
        assert stmts[0] == "BEGIN;" and stmts[-1] == "COMMIT;", (path.name, stmts[:1], stmts[-1:])
        counts[path.name] = sum(1 for s in stmts if s.startswith("DO "))
    assert counts == {F427.name: 4, R427.name: 3}, counts
    t = _text(F427)
    for planted, want in ((t.replace("\nCOMMIT;", "\nSELECT pg_sleep(24);\nCOMMIT;"), "SELECT pg_sleep(24);"),
                          (t.replace("\nCOMMIT;", "\nCOMMIT;\nSELECT 1;"), "SELECT 1;"),
                          (t.replace("\nCOMMIT;", "\nDROP TABLE conn_markers;\nCOMMIT;"), "DROP TABLE conn_markers;"),
                          (t + "\nSELECT 2", "SELECT 2")):
        assert _unguarded(planted) == [want], _unguarded(planted)


def test_427_and_its_rollback_hold_the_house_bound():
    for path in (F427, R427):
        t = _text(path)
        assert _hold_problems(t) == [], (path.name, _hold_problems(t))
        assert _unguarded(t) == [], (path.name, _unguarded(t))
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


def _rollback_without_commit():
    text_ = _text(R427)
    assert text_.rstrip().endswith("\nCOMMIT;")
    return text_.rstrip()[:-len("COMMIT;")]


_RB_LOCK = ("  PERFORM 1 FROM pending_channel_posts p\n"
            "   WHERE p.channel_id = '1159243585309384805' AND p.sort_order = 1\n"
            "     FOR NO KEY UPDATE;\n")


@pytest.mark.parametrize("first", ["the other writer", "the rollback", "the other writer, lock stripped"])
def test_rollback_427_and_a_concurrent_faq_writer_in_both_orders(live, first):
    """Finding R2-1: two sessions on message 1 after 427. The other writer
    appends to message 1's text.
    - The other writer first: its change is uncommitted when the rollback
      starts; the rollback waits on the row (locked before it is read),
      then reads the committed third text and refuses WHOLE: the three
      tables stand, message 1 keeps the third text.
    - The rollback first: it has restored 338's text and holds the row,
      uncommitted; the other writer waits, and once the rollback commits it
      meets the restored text (its append lands on 338's text), and the
      three tables are gone.
    - The other writer first against a copy of the rollback with its lock
      stripped (derived in the test): the count reads 427's text, the
      UPDATE then changes no row, and the one-row requirement refuses whole.
    The refusal's words tell the two guards apart: with the lock the count
    refuses ("is not exactly one row"); without it the one-row requirement
    does ("rows changed, not one")."""
    real = _text(R427)
    if first.endswith("stripped"):
        assert real.count(_RB_LOCK) == 1
    sql = real.replace(_RB_LOCK, "") if first.endswith("stripped") else real

    async def go():
        async with _Case([(1, _was(), 2, 2)]) as c:
            assert await c.apply(_text(F427)) is None
            other = await asyncpg.connect(DSN)
            try:
                await other.execute('SET search_path TO "%s"' % c.schema)
                await other.execute("SET lock_timeout = '20s'")
                if first.startswith("the other writer"):
                    await other.execute("BEGIN")
                    await other.execute("UPDATE pending_channel_posts SET content = content || ' (third)'"
                                        " WHERE sort_order = 1")
                    rb = asyncio.create_task(c.apply(sql))
                    await asyncio.sleep(1.0)
                    waited = not rb.done()
                    await other.execute("COMMIT")
                    refused = await asyncio.wait_for(rb, 30)
                    assert waited, "the rollback did not wait on the held row"
                    assert refused and refused.startswith("rollback 427:"), refused
                    want = "rows changed, not one" if first.endswith("stripped") else "is not exactly one row"
                    assert want in refused, refused
                    assert await c.tables() == {t: ("r", _mark_text()) for t in TABLES}
                    assert (await c.msg(1))["content"] == _new() + " (third)"
                else:
                    await c.conn.execute(_rollback_without_commit())
                    writer = asyncio.create_task(other.fetchval(
                        "UPDATE pending_channel_posts SET content = content || ' (third)'"
                        " WHERE sort_order = 1 RETURNING content"))
                    await asyncio.sleep(1.0)
                    waited = not writer.done()
                    await c.conn.execute("COMMIT")
                    got = await asyncio.wait_for(writer, 30)
                    assert waited, "the other writer did not wait on the rollback's row"
                    assert got == _was() + " (third)", got[-80:]
                    assert await c.tables() == {}
            finally:
                await other.close()
    _run(go())
