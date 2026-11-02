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


def test_ddl_inside_a_dollar_body_raises(sql):
    text = ("CREATE TABLE t (a int);\n"
            "DO $$ BEGIN CREATE INDEX t_b ON t (a); END $$;\n")
    with pytest.raises(mtd.MigrationDdlError, match="dollar-quoted body"):
        sql(text)


def test_real_027_gin_index_is_returned():
    """The one current migration with an index form the first extractor left
    out: 027's third flagged_matches index is USING GIN."""
    out = mtd.table_ddl("027_anticheat.sql", "flagged_matches")
    assert len(out) == 4, out
    assert out[3] == ("CREATE INDEX IF NOT EXISTS idx_flagged_matches_steam_ids"
                      " ON flagged_matches USING GIN(player_steam_ids)")


# REHEARSAL-FOUR round 2, LOW findings L1 to L3. Each case below returned the
# wrong answer from the extractor at aeef9c20 (a statement inside a string or
# a body returned as top-level DDL, or an index in a body silently left out)
# and raises or returns the right answer now.

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
    # L2: $é$ is a dollar quote in PostgreSQL; the index inside it is body text
    for tag in ("$é$", "$ü_9$", "$_é1$", "$Ω$"):
        text = ("CREATE TABLE t (a int);\n"
                "DO %s BEGIN CREATE INDEX t_b ON t (a); END %s;\n" % (tag, tag))
        with pytest.raises(mtd.MigrationDdlError, match="dollar-quoted body"):
            sql(text)
        # a ';' inside such a body does not end the statement holding it
        stmt = "CREATE TABLE t (a int, b text DEFAULT %s;%s)" % (tag, tag)
        assert sql(stmt + ";\n") == [stmt]


def test_body_ddl_ends_at_the_lexer_semicolon(sql):
    # L3: a ';' inside a comment, a quoted index name or a string between INDEX
    # and the table name does not end the statement
    for head in ("CREATE INDEX /* ; */ t_b ON t (a)",
                 "CREATE INDEX -- ;\n t_b ON t (a)",
                 'CREATE INDEX "semi;colon" ON t (a)',
                 "CREATE TABLE IF NOT EXISTS /* ; */ t (a int)"):
        text = "CREATE TABLE t (a int);\nDO $$ BEGIN %s; END $$;\n" % head
        with pytest.raises(mtd.MigrationDdlError, match="dollar-quoted body"):
            sql(text)
    # the text an EXECUTE runs, and a body nested in a body, are read too
    for body in ("DO $$ BEGIN EXECUTE 'CREATE INDEX i ON t (a)'; END $$;\n",
                 "DO $$ BEGIN EXECUTE $q$CREATE INDEX /* ; */ i ON t (a)$q$; END $$;\n"):
        with pytest.raises(mtd.MigrationDdlError, match="dollar-quoted body"):
            sql("CREATE TABLE t (a int);\n" + body)
    # a body statement on another table is not the table's, even when a later
    # statement in the same body reads the table
    assert sql("CREATE TABLE t (a int);\n"
               "DO $$ BEGIN CREATE INDEX i ON other (a); PERFORM 1 FROM t; END $$;\n"
               ) == ["CREATE TABLE t (a int)"]


def test_a_body_that_does_not_lex_and_names_the_table_raises(sql):
    with pytest.raises(mtd.MigrationDdlError, match="does not lex"):
        sql("CREATE TABLE t (a int);\n"
            "CREATE FUNCTION f() RETURNS int LANGUAGE plpython3u AS $$ x = 'open t $$;\n")
    assert sql("CREATE TABLE t (a int);\n"
               "CREATE FUNCTION f() RETURNS int LANGUAGE plpython3u AS $$ x = 'open $$;\n"
               ) == ["CREATE TABLE t (a int)"]
