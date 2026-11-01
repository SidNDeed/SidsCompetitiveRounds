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
