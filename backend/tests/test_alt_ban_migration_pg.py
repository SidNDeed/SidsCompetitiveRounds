"""Migration 431 (records kept for an account under an active ban) and its
rollback, with 427 beside it.

The pure cases read the files: both marks and the rollback's are the digest
of 431's own DDL block, 431's earlier text is 427's message 1 and its new
text is that text, one space and one sentence, the rollback carries the same
two texts, the header's character count is the new text's, the FAQ step is
not selected by the full-schema DDL replay, every top-level statement is a
guarded form, both files hold the house holding bound, and models.py
declares the three tables column for column.

The live cases apply the files to a throwaway schema on a PostgreSQL cluster
through the same harness as 427's own test (SCR_MIGRATION_TEST_PG_DSN; the
live cases FAIL without it, SCR_MIGRATION_TEST_PG_OPTOUT=1 waives them):
427 then 431, the wrong order, twice, under an open read, every other FAQ
state, every other table state, the three tables' checks, and the rollbacks
in their order.
"""
import os
import re
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

import test_alt_signals_migration_pg as m427  # noqa: E402

asyncpg = m427.asyncpg
SQL_DIR = Path(HERE).parent / "sql"
F427, R427 = m427.F427, m427.R427
F431 = SQL_DIR / "431_ban_links.sql"
R431 = SQL_DIR / "rollback_431_ban_links.sql"

TABLES = ("ban_link_notices", "ban_notice_days", "ban_regions")
ALL_TABLES = TABLES + m427.TABLES
_MARK = re.compile(r"'ban links, DDL sha256 ([0-9a-f]{64})'")


def _text(path):
    return m427._text(path)


def _was():
    """431's earlier text: 427's message 1, read from 427."""
    return m427._new()


def _new():
    return m427._one(m427._quoted(_text(F431), "faq1"), "431's $faq1$")


def _mark_text():
    return "ban links, DDL sha256 %s" % m427._ddl_digest(_text(F431))


def _mark_defects(text, ddl_source=None):
    marks = _MARK.findall(text)
    if not marks:
        return ["no mark"]
    want = m427._ddl_digest(ddl_source if ddl_source is not None else text)
    return ["mark %s, digest %s" % (m, want) for m in marks if m != want]


# -- pure: the files themselves ----------------------------------------------

def test_431_marks_are_the_digest_of_its_own_ddl():
    """Both of 431's marks and the rollback's are the SHA-256 of 431's DDL
    block. Negative control: a changed type, a changed index, a changed
    check and a dropped partial-index predicate each leave a mark that no
    longer matches; a comment line does not."""
    real = _text(F431)
    assert len(_MARK.findall(real)) == 2
    assert _mark_defects(real) == []
    assert len(_MARK.findall(_text(R431))) == 1
    assert _mark_defects(_text(R431), ddl_source=real) == []
    mutants = {
        "a column type": ("      conn_class  VARCHAR(8)  NOT NULL", "      conn_class  TEXT        NOT NULL"),
        "an index's columns": ("ON ban_regions (last_at);", "ON ban_regions (last_at, steam_id);"),
        "a check's bound": ("BETWEEN 1 AND 130", "BETWEEN 1 AND 131"),
        "the partial predicate": (" (noticed_at) WHERE posted_at IS NULL;", " (noticed_at);"),
    }
    for name, (old, new) in mutants.items():
        assert real.count(old) == 1, name
        assert _mark_defects(real.replace(old, new)), "%s left the mark matching" % name
    inert = real.replace("    -- DDL END", "    -- a comment line inside the block\n    -- DDL END")
    assert inert != real and _mark_defects(inert) == []
    assert "431" not in "\n".join(m427._ddl_lines(real))


def test_431_faq_texts_are_427s_text_and_one_sentence_and_agree_with_the_rollback():
    """431's earlier text is 427's message 1; its new text is that text, one
    space and one sentence with no line break; the rollback carries the same
    two texts under its own tags; the new text fits one Discord message, and
    the header states its length."""
    was, new = _was(), _new()
    t431, trb = _text(F431), _text(R431)
    assert m427._one(m427._quoted(t431, "faq1was"), "431's $faq1was$") == was
    assert new.startswith(was + " ")
    added = new[len(was) + 1:]
    assert added and "\n" not in added and not added.startswith(" "), added
    assert added.endswith(".") and added.count(". ") == 0, "431 adds exactly one sentence"
    assert len(new) <= 2000, len(new)
    assert ("FAQ message 1 holds %d of Discord's 2000 characters after this file" % len(new)) in t431
    assert m427._one(m427._quoted(trb, "faq1was"), "rollback's $faq1was$") == was
    assert m427._one(m427._quoted(trb, "faq1now"), "rollback's $faq1now$") == new
    assert not m427._quoted(trb, "faq1"), "the rollback carries no $faq1$ literal"


def test_431_replay_selects_the_table_step_and_not_the_faq_step():
    t = _text(F431)
    assert m427._do_blocks(t) == ["$m431path$", "$m431tables$", "$m431faq$", "$m431check$"]
    assert m427._REPLAY_SELECTOR.search(m427._do_block(t, "m431tables"))
    for tag in ("m431path", "m431faq", "m431check"):
        assert not m427._REPLAY_SELECTOR.search(m427._do_block(t, tag)), tag
    assert not re.search(r"\bpg_temp\.", m427._do_block(t, "m431tables"))


def test_every_top_level_statement_of_431_is_a_guarded_form_and_holds_the_house_bound():
    counts = {}
    for path in (F431, R431):
        t = _text(path)
        assert m427._unguarded(t) == [], (path.name, m427._unguarded(t))
        assert m427._hold_problems(t) == [], (path.name, m427._hold_problems(t))
        for line in m427._SETS:
            assert t.count(line) == 1, (path.name, line)
        counts[path.name] = sum(1 for s in m427._statements(t) if s.startswith("DO "))
    assert counts == {F431.name: 4, R431.name: 3}, counts
    t = _text(F431)
    assert m427._unguarded(t.replace("\nCOMMIT;", "\nDROP TABLE ban_regions;\nCOMMIT;")) == [
        "DROP TABLE ban_regions;"]
    assert m427._hold_problems(t.replace("statement_timeout = '25s'", "statement_timeout = '30s'"))


def _orm_columns(names):
    from sqlalchemy.dialects import postgresql
    import models
    out = {}
    for t in names:
        out[t] = []
        for c in models.Base.metadata.tables[t].columns:
            typ = c.type.compile(dialect=postgresql.dialect())
            typ = {"TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ"}.get(typ, typ)
            assert typ in m427._ORM_TYPES, (t, c.name, typ)
            out[t].append((c.name, typ, c.nullable))
    return out


def test_the_orm_classes_match_431_column_for_column_and_index_for_index():
    """models.py declares the three tables as 431 makes them (name, type,
    nullability, in order; the index names and the partial predicate), and
    431's text is read by 427's closed table of statement heads with no
    finding. Negative control: a renamed column and a changed nullability
    each differ."""
    import models
    t = _text(F431)
    assert m427._ddl_outside(t) == []
    ddl = m427._ddl_columns(t)
    assert set(ddl) == set(TABLES) and all(ddl.values()), ddl
    assert ddl == _orm_columns(TABLES)
    for old, new in (("      noticed_at       TIMESTAMPTZ", "      noticed_atx      TIMESTAMPTZ"),
                     ("      posted_at        TIMESTAMPTZ NULL", "      posted_at        TIMESTAMPTZ NOT NULL")):
        assert t.count(old) == 1, old
        assert m427._ddl_columns(t.replace(old, new)) != _orm_columns(TABLES), old
    idx = {i.name: ([c.name for c in i.columns], str(i.dialect_options["postgresql"]["where"]
                                                     if i.dialect_options["postgresql"]["where"] is not None
                                                     else ""))
           for name in TABLES for i in models.Base.metadata.tables[name].indexes}
    assert idx == {"ix_ban_regions_last_at": (["last_at"], ""),
                   "ix_ban_link_notices_other": (["other_steam_id"], ""),
                   "ix_ban_link_notices_unposted": (["noticed_at"], "posted_at IS NULL")}, idx
    for name, (cols, where) in idx.items():
        made = re.findall(r"CREATE INDEX %s ON [a-z_]+ \(([a-z_, ]+)\)( WHERE [^;]+)?;" % name, t)
        assert made == [(", ".join(cols), (" WHERE " + where) if where else "")], (name, made)


# -- live --------------------------------------------------------------------

@pytest.fixture
def live():
    if m427.DSN and asyncpg is not None:
        return m427.DSN
    if m427.OPTOUT:
        pytest.skip("%s is unset and %s=1: live cases deliberately waived" % (m427.DSN_VAR, m427.OPTOUT_VAR))
    pytest.fail("%s is unset (or asyncpg missing), so 431 was never applied; set it, or %s=1 to "
                "waive the live cases deliberately" % (m427.DSN_VAR, m427.OPTOUT_VAR))


_run = m427._run


def _was338():
    return m427._was()


async def _tables(c):
    return {r["relname"]: (r["relkind"], r["c"]) for r in await c.conn.fetch(
        "SELECT c.relname, c.relkind::text AS relkind, obj_description(c.oid, 'pg_class') AS c"
        "  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = $1 AND c.relname = ANY($2::text[])", c.schema, list(ALL_TABLES))}


def _both_marked():
    return {t: ("r", _mark_text()) for t in TABLES}


def _all_marked():
    out = {t: ("r", m427._mark_text()) for t in m427.TABLES}
    out.update(_both_marked())
    return out


def test_427_then_431_creates_three_marked_tables_and_revises_message_1_once_more(live):
    async def go():
        async with m427._Case([(1, _was338(), 2, 2), (2, "message two", 2, 2)]) as c:
            two = await c.msg(2)
            assert await c.apply(_text(F427)) is None
            assert await c.apply(_text(F431)) is None
            assert await _tables(c) == _all_marked()
            one = await c.msg(1)
            assert (one["content"], one["revision"], one["posted_revision"]) == (_new(), 4, 2)
            assert await c.msg(2) == two
    _run(go())


def test_431_before_427_refuses_and_the_right_order_then_runs(live):
    """The wrong order stops with nothing changed; 427 and then 431 run."""
    async def go():
        async with m427._Case([(1, _was338(), 2, 2)]) as c:
            before = await c.state()
            refused = await c.apply(_text(F431))
            assert refused and "431: FAQ message 1 is not exactly one row" in refused, refused
            assert await c.state() == before and await _tables(c) == {}
            assert await c.apply(_text(F427)) is None
            assert await c.apply(_text(F431)) is None
            assert (await c.msg(1))["content"] == _new()
    _run(go())


def test_427_run_again_after_431_raises_and_changes_nothing(live):
    async def go():
        async with m427._Case([(1, _was338(), 2, 2)]) as c:
            assert await c.apply(_text(F427)) is None
            assert await c.apply(_text(F431)) is None
            before = await c.state()
            refused = await c.apply(_text(F427))
            assert refused and "427: FAQ message 1" in refused, refused
            assert await c.state() == before
    _run(go())


def test_431_second_run_writes_nothing_and_takes_no_lock_on_the_tables_or_the_row(live):
    """A second run completes while another session holds ACCESS EXCLUSIVE on
    the three tables and a row lock on message 1, and leaves every relation,
    constraint and row (xmin included) as it was. Negative control: a copy
    whose FAQ step writes on every run is stopped by the held row lock."""
    async def second_run(sql_second):
        async with m427._Case([(1, _was338(), 2, 2), (2, "message two", 2, 2)]) as c:
            assert await c.apply(_text(F427)) is None
            assert await c.apply(_text(F431)) is None
            before = await c.state()
            other = await asyncpg.connect(m427.DSN)
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

    refused, before, after = _run(second_run(_text(F431)))
    assert refused is None and after == before
    writes_always = _text(F431).replace(
        "  IF rows_all = 1 AND rows_was = 1 THEN", "  IF rows_all = 1 THEN").replace(
        " AND p.sort_order = 1 AND p.content = was;", " AND p.sort_order = 1;")
    assert writes_always != _text(F431)
    refused, before, after = _run(second_run(writes_always))
    assert refused and "lock" in refused.lower() and after == before, refused


def test_431_first_run_completes_under_an_open_read_of_message_1(live):
    async def go():
        async with m427._Case([(1, _was338(), 2, 2)]) as c:
            assert await c.apply(_text(F427)) is None
            other = await asyncpg.connect(m427.DSN)
            try:
                await other.execute('SET search_path TO "%s"' % c.schema)
                await other.execute("BEGIN")
                read = await other.fetchval("SELECT content FROM pending_channel_posts WHERE sort_order = 1")
                assert read == _was()
                assert await c.apply(_text(F431)) is None
            finally:
                await other.execute("ROLLBACK")
                await other.close()
            assert (await c.msg(1))["content"] == _new()
    _run(go())


@pytest.mark.parametrize("name,rows", [
    ("absent", [(2, "message two", 2, 2)]),
    ("338's text", [(1, "@338", 2, 2)]),
    ("two rows holding 427's text", [(1, "@was", 3, 3), (1, "@was", 3, 3)]),
    ("a third text", [(1, "@was edited", 4, 4)]),
    ("427's text beside the new text", [(1, "@was", 3, 3), (1, "@new", 4, 4)]),
    ("the sentence without its space", [(1, "@nospace", 4, 4)]),
])
def test_431_refuses_every_other_faq_state_and_commits_nothing(live, name, rows):
    def fill(s):
        return (s.replace("@338", _was338()).replace("@nospace", _new().replace(_was() + " ", _was(), 1))
                .replace("@was", _was()).replace("@new", _new()))
    real = [(s, fill(c), r, p) for s, c, r, p in rows]

    async def go():
        async with m427._Case(real) as c:
            before = await c.state()
            refused = await c.apply(_text(F431))
            assert refused and "431: FAQ message 1" in refused, (name, refused)
            assert await c.state() == before
            assert await _tables(c) == {}
    _run(go())


@pytest.mark.parametrize("name,setup", [
    ("one table present", "CREATE TABLE ban_regions (x int)"),
    ("both unmarked", "CREATE TABLE ban_regions (x int); CREATE TABLE ban_link_notices (x int)"),
    ("both marked otherwise",
     "CREATE TABLE ban_regions (x int); CREATE TABLE ban_link_notices (x int);"
     " COMMENT ON TABLE ban_regions IS 'ban links, DDL sha256 %s';"
     " COMMENT ON TABLE ban_link_notices IS 'ban links, DDL sha256 %s'" % (("0" * 64,) * 2)),
    ("both marked by 427's mark",
     "CREATE TABLE ban_regions (x int); CREATE TABLE ban_link_notices (x int);"
     " COMMENT ON TABLE ban_regions IS '@427';"
     " COMMENT ON TABLE ban_link_notices IS '@427'"),
    ("a view of one name", "CREATE VIEW ban_regions AS SELECT 1 AS x"),
    ("an index name taken", "CREATE TABLE other_t (a int); CREATE INDEX ix_ban_link_notices_unposted ON other_t (a)"),
    ("a row type taken", "CREATE TYPE ban_link_notices AS (a int)"),
])
def test_431_refuses_every_other_table_state_and_changes_nothing(live, name, setup):
    async def go():
        async with m427._Case([(1, _was338(), 2, 2)], setup=setup.replace("@427", m427._mark_text())) as c:
            assert await c.apply(_text(F427)) is None
            before = await c.state()
            refused = await c.apply(_text(F431))
            assert refused and refused.startswith("431:"), (name, refused)
            assert await c.state() == before
    _run(go())


@pytest.mark.parametrize("name,sql", [
    ("a control character", "INSERT INTO ban_regions (steam_id, region, conn_class) VALUES ('1', 'A' || chr(7), 'none')"),
    ("a C1 control character", "INSERT INTO ban_regions (steam_id, region, conn_class) VALUES ('1', 'A' || chr(133), 'none')"),
    ("an empty region", "INSERT INTO ban_regions (steam_id, region, conn_class) VALUES ('1', '', 'none')"),
    ("131 characters", "INSERT INTO ban_regions (steam_id, region, conn_class) VALUES ('1', repeat('a', 131), 'none')"),
    ("a class word 427 does not store", "INSERT INTO ban_regions (steam_id, region, conn_class) VALUES ('1', 'A', 'lan')"),
    ("an id that is no id", "INSERT INTO ban_regions (steam_id, region, conn_class) VALUES ('x1', 'A', 'none')"),
    ("last before first", "INSERT INTO ban_regions (steam_id, region, conn_class, first_at, last_at)"
                          " VALUES ('1', 'A', 'none', now(), now() - interval '1 second')"),
    ("a pair of one account", "INSERT INTO ban_link_notices (banned_steam_id, other_steam_id) VALUES ('1', '1')"),
    ("a pair with no id", "INSERT INTO ban_link_notices (banned_steam_id, other_steam_id) VALUES ('1', '')"),
    ("a day count of 0", "INSERT INTO ban_notice_days (day, posts) VALUES ('2026-01-03', 0)"),
    ("a day count over 20", "INSERT INTO ban_notice_days (day, posts) VALUES ('2026-01-03', 21)"),
    ("a day count raised past 20", "UPDATE ban_notice_days SET posts = posts + 1 WHERE day = '2026-01-02'"),
])
def test_the_three_tables_refuse_a_row_outside_their_checks(live, name, sql):
    """Control first: a region of 130 characters with a comma and a space,
    the country alone, a pair of two accounts, and day counts of 1 and 20
    are accepted."""
    async def go():
        async with m427._Case([(1, _was338(), 2, 2)]) as c:
            assert await c.apply(_text(F427)) is None
            assert await c.apply(_text(F431)) is None
            await c.conn.execute(
                "INSERT INTO ban_regions (steam_id, region, conn_class) VALUES"
                " ('1', repeat('a', 60) || ', ' || repeat('b', 68), 'vpn'), ('1', 'Ardenmark', 'none');"
                " INSERT INTO ban_link_notices (banned_steam_id, other_steam_id) VALUES ('1', '2');"
                " INSERT INTO ban_notice_days (day, posts) VALUES ('2026-01-01', 1), ('2026-01-02', 20)")
            with pytest.raises(asyncpg.CheckViolationError):
                await c.conn.execute(sql)
    _run(go())


def test_rollback_431_then_rollback_427_restore_338s_text_and_drop_all_six_tables(live):
    async def go():
        async with m427._Case([(1, _was338(), 2, 2)]) as c:
            assert await c.apply(_text(F427)) is None
            assert await c.apply(_text(F431)) is None
            assert await c.apply(_text(R431)) is None
            assert await _tables(c) == {t: ("r", m427._mark_text()) for t in m427.TABLES}
            one = await c.msg(1)
            assert (one["content"], one["revision"]) == (_was(), 5)
            before = await c.state()
            assert await c.apply(_text(R431)) is None
            assert await c.state() == before
            assert await c.apply(_text(R427)) is None
            assert await _tables(c) == {}
            one = await c.msg(1)
            assert (one["content"], one["revision"], one["posted_revision"]) == (_was338(), 6, 2)
    _run(go())


def test_rollback_427_before_rollback_431_refuses_and_changes_nothing(live):
    async def go():
        async with m427._Case([(1, _was338(), 2, 2)]) as c:
            assert await c.apply(_text(F427)) is None
            assert await c.apply(_text(F431)) is None
            before = await c.state()
            refused = await c.apply(_text(R427))
            assert refused and refused.startswith("rollback 427: FAQ message 1"), refused
            assert await c.state() == before
    _run(go())


def test_rollback_431_without_431_changes_nothing(live):
    async def go():
        async with m427._Case([(1, _was338(), 2, 2)]) as c:
            assert await c.apply(_text(F427)) is None
            before = await c.state()
            assert await c.apply(_text(R431)) is None
            assert await c.state() == before
    _run(go())


@pytest.mark.parametrize("name,edit", [
    ("an unmarked table", "COMMENT ON TABLE ban_regions IS 'something else'"),
    ("message 1 revised again", "UPDATE pending_channel_posts SET content = content || ' (later)',"
                                " revision = revision + 1 WHERE sort_order = 1"),
    ("message 1 at 338's text", "UPDATE pending_channel_posts SET content = $t$@338$t$ WHERE sort_order = 1"),
])
def test_rollback_431_refuses_what_is_not_431s_and_changes_nothing(live, name, edit):
    async def go():
        async with m427._Case([(1, _was338(), 2, 2)]) as c:
            assert await c.apply(_text(F427)) is None
            assert await c.apply(_text(F431)) is None
            await c.conn.execute(edit.replace("@338", _was338()))
            before = await c.state()
            refused = await c.apply(_text(R431))
            assert refused and refused.startswith("rollback 431:"), (name, refused)
            assert await c.state() == before
    _run(go())
