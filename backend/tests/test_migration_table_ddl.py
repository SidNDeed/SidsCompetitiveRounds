"""migration_table_ddl: every lexical and grammar form is parsed or raises.

Pure Python, no database. Each case writes a small migration into a temporary
directory and points the module's SQL_DIR at it. The rule under test (module
docstring): the extractor returns a complete definition, or raises
MigrationDdlError; it never takes text inside a string, comment, quoted
identifier or dollar body for a statement, and never silently leaves out a
statement it cannot parse.
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import migration_table_ddl as mtd  # noqa: E402


@pytest.fixture
def sql(tmp_path, monkeypatch):
    """Write `text` as m.sql in a fresh SQL_DIR and return table_ddl over it."""
    monkeypatch.setattr(mtd, "SQL_DIR", str(tmp_path))

    def ddl(text, table="t"):
        (tmp_path / "m.sql").write_text(text, encoding="utf-8", newline="\n")
        return mtd.table_ddl("m.sql", table)
    return ddl


def test_escape_string_text_is_not_a_table(sql):
    # E'\'' is ONE quote character: the backslash escapes it. A reader that
    # ends the string at the escaped quote re-pairs every later quote and reads
    # the next string's text as a statement.
    fake = "SELECT E'\\'', 'CREATE TABLE t (a int);';\n-- it's\n"
    with pytest.raises(mtd.MigrationDdlError, match="0 top-level CREATE TABLE"):
        sql(fake)
    real = "SELECT E'\\'', 'CREATE TABLE t (a int);';\nCREATE TABLE t (b int);\n"
    assert sql(real) == ["CREATE TABLE t (b int)"]


def test_nested_block_comment_text_is_not_a_table(sql):
    fake = "/* a /* b */ CREATE TABLE t (a int); */\n"
    with pytest.raises(mtd.MigrationDdlError, match="0 top-level CREATE TABLE"):
        sql(fake)
    real = "/* a /* b */ CREATE TABLE t (a int); */\nCREATE TABLE t (b int);\n"
    assert sql(real) == ["CREATE TABLE t (b int)"]


def test_quoted_identifiers_are_names_not_statements(sql):
    fake = 'CREATE TABLE other ("CREATE TABLE t (a int);" int);\n'
    with pytest.raises(mtd.MigrationDdlError, match="0 top-level CREATE TABLE"):
        sql(fake)
    # a quoted name is the relation it spells: "t" is t, "T" is not
    assert sql('CREATE TABLE "t" (a int);\n') == ['CREATE TABLE "t" (a int)']
    with pytest.raises(mtd.MigrationDdlError, match="0 top-level CREATE TABLE"):
        sql('CREATE TABLE "T" (a int);\n')
    # an unquoted name folds to lower case
    assert sql("CREATE TABLE T (a int);\n") == ["CREATE TABLE T (a int)"]
    with pytest.raises(mtd.MigrationDdlError, match="schema-qualified"):
        sql("CREATE TABLE public.t (a int);\n")


def test_index_with_using_method_is_returned(sql):
    assert sql("CREATE TABLE t (a int);\nCREATE INDEX t_a ON t USING gin (a);\n") == [
        "CREATE TABLE t (a int)", "CREATE INDEX t_a ON t USING gin (a)"]


def test_index_on_only_is_returned(sql):
    assert sql("CREATE TABLE t (a int);\nCREATE INDEX t_a ON ONLY t (a);\n") == [
        "CREATE TABLE t (a int)", "CREATE INDEX t_a ON ONLY t (a)"]


def test_quoted_index_and_table_names_are_returned(sql):
    text = ('CREATE TABLE t (a int, b int);\n'
            'CREATE INDEX "T a" ON t (a);\n'
            'CREATE UNIQUE INDEX IF NOT EXISTS t_b ON "t" (b);\n'
            'CREATE INDEX t_c ON "T" (a);\n')
    assert sql(text) == [
        "CREATE TABLE t (a int, b int)",
        'CREATE INDEX "T a" ON t (a)',
        'CREATE UNIQUE INDEX IF NOT EXISTS t_b ON "t" (b)']


def test_unnamed_index_is_returned(sql):
    assert sql("CREATE TABLE t (a int);\nCREATE INDEX ON t (a);\n") == [
        "CREATE TABLE t (a int)", "CREATE INDEX ON t (a)"]


def test_unclosed_index_parentheses_raise(sql):
    with pytest.raises(mtd.MigrationDdlError, match="parentheses close"):
        sql("CREATE TABLE t (a int);\nCREATE INDEX t_a ON t ((lower(a));\n")


def test_real_027_gin_index_is_returned():
    """The one current migration with an index form the first extractor left
    out: 027's third flagged_matches index is USING GIN."""
    out = mtd.table_ddl("027_anticheat.sql", "flagged_matches")
    assert len(out) == 4, out
    assert out[3] == ("CREATE INDEX IF NOT EXISTS idx_flagged_matches_steam_ids"
                      " ON flagged_matches USING GIN(player_steam_ids)")


# REHEARSAL-FOUR round 2, LOW findings L1 and L2. Each case below returned a
# statement inside a string or a body as top-level DDL at aeef9c20 and raises
# or returns the right answer now. What a body performs is not table_ddl's
# question since REHEARSAL-FOUR-R6: test_r7_catalog_diff_pg.py measures it.

ESC_CONTINUED = "SELECT E'x'\n'\\'; CREATE TABLE t (a int); --';\n"


def test_continued_escape_string_stays_an_escape_string(sql):
    # L1: E'x' continued after a newline is ONE escape string, so \' in the
    # continued segment is an escaped quote and the CREATE TABLE is string text.
    with pytest.raises(mtd.MigrationDdlError, match="0 top-level CREATE TABLE"):
        sql(ESC_CONTINUED)
    # a line comment may stand in the gap (scan.l's whitespace_with_newline)
    with pytest.raises(mtd.MigrationDdlError, match="0 top-level CREATE TABLE"):
        sql("SELECT E'x' -- gap\n-- more\n'\\'; CREATE TABLE t (a int); --';\n")
    assert sql(ESC_CONTINUED + "CREATE TABLE t (b int);\n") == ["CREATE TABLE t (b int)"]


def test_continued_standard_string_stays_a_standard_string(sql):
    # the positive control for L1: a standard string continued stays standard,
    # where a backslash is an ordinary character, so the statement after it is real
    assert sql("SELECT 'x'\n'\\'; CREATE TABLE t (a int);\n") == ["CREATE TABLE t (a int)"]
    # no newline in the gap: not a continuation, the second string is standard
    assert sql("SELECT E'x', '\\'; CREATE TABLE t (a int);\n") == ["CREATE TABLE t (a int)"]


def test_dollar_tags_use_the_identifier_alphabet(sql):
    # L2: $é$ is a dollar quote in PostgreSQL; the index inside it is body
    # text, never a top-level statement of the file
    for tag in ("$é$", "$ü_9$", "$_é1$", "$Ω$"):
        text = ("CREATE TABLE t (a int);\n"
                "DO %s BEGIN CREATE INDEX t_b ON t (a); END %s;\n" % (tag, tag))
        assert sql(text) == ["CREATE TABLE t (a int)"]
        # a ';' inside such a body does not end the statement holding it
        stmt = "CREATE TABLE t (a int, b text DEFAULT %s;%s)" % (tag, tag)
        assert sql(stmt + ";\n") == [stmt]


def test_a_body_is_never_a_top_level_statement(sql):
    """REHEARSAL-FOUR-R6 (1)(a): what a DO, a function body, an EXECUTE or
    another language performs is measured at the database
    (test_r7_catalog_diff_pg.py), not read here. To table_ddl a body is the
    text of one constant: nothing in it is returned, and nothing in it
    refuses."""
    for body in ("DO $$ BEGIN CREATE INDEX i ON t (a); END $$;\n",
                 "DO $$ BEGIN EXECUTE 'CREATE INDEX i ON t (a)'; END $$;\n",
                 "DO 'BEGIN CREATE INDEX i ON t (a); END';\n",
                 "CREATE FUNCTION f() RETURNS int LANGUAGE plpython3u AS $$ x = 'open t $$;\n",
                 "DO $$ BEGIN CREATE TABLE t (b int); END $$;\n"):
        assert sql("CREATE TABLE t (a int);\n" + body) == ["CREATE TABLE t (a int)"], body


def test_the_same_literals_on_one_line_refuse(sql):
    # a block comment is not a continuation gap, even with a newline in it
    with pytest.raises(mtd.MigrationDdlError, match="no newline between them"):
        mtd._views("SELECT 'a' /* x\n */ 'b';\n")
    with pytest.raises(mtd.MigrationDdlError, match="no newline between them"):
        sql("CREATE TABLE t (a int);\nSELECT 'a' 'b';\n")


def test_data_strings_and_bodies_are_not_statements(sql):
    # E'' and U&'' constants and dollar bodies as data are not refused
    text = ("CREATE TABLE t (a int);\n"
            "UPDATE x SET v = REPLACE(v, U&'\\25BC', 'v') WHERE w = E'\\n';\n"
            "DO $$ BEGIN RAISE NOTICE E'it\\'s %', 'it''s'; "
            "INSERT INTO y VALUES ($m$it's$m$); END $$;\n")
    assert sql(text) == ["CREATE TABLE t (a int)"]


def test_r4_line_comment_ends_at_cr(sql):
    """2.1: a -- comment ends at CR as well as LF (scan.l non_newline is
    [^\n\r]), so the text after a CR is SQL, not comment."""
    code, mask, _bodies = mtd._views("SELECT 1 -- comment\r, lo_create(0)")
    assert "lo_create(0)" in code
    assert ("ident", "lo_create") in [t[:2] for t in mtd._tokens(code, mask)]
    assert sql("-- c\rCREATE TABLE t (a int);\n") == ["CREATE TABLE t (a int)"]
    assert sql("-- c\r\nCREATE TABLE t (a int);\n") == ["CREATE TABLE t (a int)"]


def test_on_conflict_do_is_not_a_statement(sql):
    text = ("INSERT INTO t VALUES (1) ON CONFLICT DO NOTHING;\n"
            "INSERT INTO t VALUES (1) ON CONFLICT (a) DO UPDATE SET a = 2;\n")
    assert sql("CREATE TABLE t (a int);\n" + text) == ["CREATE TABLE t (a int)"]
