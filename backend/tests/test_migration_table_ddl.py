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


def test_an_executable_body_that_does_not_lex_raises_whatever_it_names(sql):
    # R3-A1: no mention gate; the body below names nothing and still refuses
    for body in ("$$ x = 'open t $$", "$$ x = 'open $$"):
        with pytest.raises(mtd.MigrationDdlError, match="does not lex"):
            sql("CREATE TABLE t (a int);\n"
                "CREATE FUNCTION f() RETURNS int LANGUAGE plpython3u AS %s;\n" % body)


# REHEARSAL-FOUR round 3, item (d) as amended by R3-A1: executable positions
# (a DO body, a CREATE FUNCTION or PROCEDURE AS body, and the commands of an
# EXECUTE inside such a body) are read by the lexer with nothing decoded.
# A form the lexer does not read refuses, for table_ddl and ddl_naming_table
# alike, whatever name it carries. Each case below was accepted at 52ed4ee8.

def naming(text, table="mail_inbox_rev"):
    return mtd.ddl_naming_table(text, table)


REFUSED = [
    # (form, text for table t, message)
    ("DO body in a standard string",
     "DO 'BEGIN CREATE INDEX i ON t (a); END';\n", "DO body .* not dollar-quoted"),
    ("DO LANGUAGE body in a standard string",
     "DO LANGUAGE plpgsql 'BEGIN CREATE INDEX i ON t (a); END';\n",
     "DO body .* not dollar-quoted"),
    ("AS body in a standard string",
     "CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS "
     "'BEGIN CREATE INDEX i ON t (a); END';\n", "AS body .* not dollar-quoted"),
    ("E'' string in an EXECUTE",
     "DO $$ BEGIN EXECUTE E'CREATE INDEX i ON t (a)'; END $$;\n", "E'' string constant"),
    ("backslash in an EXECUTE string",
     "DO $$ BEGIN EXECUTE 'CREATE INDEX i ON \\t (a)'; END $$;\n", "backslash"),
    ("U&'' string in an EXECUTE",
     "DO $$ BEGIN EXECUTE U&'CREATE INDEX i ON \\0074 (a)'; END $$;\n", "U&'' string"),
    ("U& identifier in a body",
     "DO $$ BEGIN CREATE INDEX i ON U&\"\\0074\" (a); END $$;\n", "U& identifier"),
    ("U& identifier at the top level",
     "CREATE INDEX i ON U&\"\\0074\" (a);\n", "U& identifier"),
    ("two literals on one line in an EXECUTE",
     "DO $$ BEGIN EXECUTE 'CREATE INDEX i ON ' 't (a)'; END $$;\n", "does not lex"),
    ("an executable body that does not lex",
     "CREATE FUNCTION f() RETURNS int LANGUAGE plpython3u AS $$ x = 'open $$;\n",
     "does not lex"),
]


@pytest.mark.parametrize("form,text,message", REFUSED, ids=[r[0] for r in REFUSED])
def test_unreadable_executable_forms_refuse(sql, form, text, message):
    with pytest.raises(mtd.MigrationDdlError, match=message):
        sql("CREATE TABLE t (a int);\n" + text)
    # ddl_naming_table refuses the same text, whatever table it is asked for
    with pytest.raises(mtd.MigrationDdlError, match=message):
        naming(text.replace(" t (a)", " mail_inbox_rev (a)"))
    with pytest.raises(mtd.MigrationDdlError, match=message):
        naming(text, table="unrelated")


def test_round3_reviewer_programs_refuse():
    # :322 a DO body in a standard string; :326 an escaped name in an E''
    # EXECUTE string; :374 an index on U&"\0074" in a dollar body
    for text in ("DO 'BEGIN ALTER TABLE mail_inbox_rev ADD COLUMN x int; END';\n",
                 "DO $$ BEGIN EXECUTE E'ALTER TABLE mail\\u005finbox_rev ADD COLUMN x int'; "
                 "END $$;\n",
                 "DO $$ BEGIN ALTER TABLE U&\"mail\\005finbox_rev\" ADD COLUMN x int; END $$;\n"):
        with pytest.raises(mtd.MigrationDdlError):
            naming(text)


def test_a_name_split_across_a_newline_continuation_is_found(sql):
    split = "DO $$ BEGIN EXECUTE 'ALTER TABLE mail_inbox_'\n  'rev ADD COLUMN x int'; END $$;\n"
    assert naming(split) == ["ALTER TABLE mail_inbox_rev ADD COLUMN x int"]
    # a line comment may stand in the gap
    commented = ("DO $$ BEGIN EXECUTE 'ALTER TABLE mail_inbox_' -- gap\n"
                 "  'rev ADD COLUMN x int'; END $$;\n")
    assert naming(commented) == ["ALTER TABLE mail_inbox_rev ADD COLUMN x int"]
    with pytest.raises(mtd.MigrationDdlError, match="dollar-quoted body"):
        sql("CREATE TABLE t (a int);\n"
            "DO $$ BEGIN EXECUTE 'CREATE INDEX i ON '\n't (a)'; END $$;\n")


def test_the_same_literals_on_one_line_refuse(sql):
    one_line = "DO $$ BEGIN EXECUTE 'ALTER TABLE mail_inbox_' 'rev ADD COLUMN x int'; END $$;\n"
    with pytest.raises(mtd.MigrationDdlError, match="no newline between them"):
        naming(one_line)
    # a block comment is not a continuation gap, even with a newline in it
    with pytest.raises(mtd.MigrationDdlError, match="no newline between them"):
        naming("SELECT 'a' /* x\n */ 'b';\n")
    with pytest.raises(mtd.MigrationDdlError, match="no newline between them"):
        sql("CREATE TABLE t (a int);\nSELECT 'a' 'b';\n")


def test_a_doubled_quote_next_to_a_name_neither_adds_nor_hides_one():
    # the name inside a doubled-quote string is a string, not a statement
    assert naming("DO $$ BEGIN EXECUTE 'SELECT ''mail_inbox_rev'''; END $$;\n") == []
    # a string where a TABLE statement's name stands is not a name: refused
    with pytest.raises(mtd.MigrationDdlError, match="cannot parse the table name"):
        naming("DO $$ BEGIN EXECUTE 'ALTER TABLE ''mail_inbox_rev'' ADD x int'; END $$;\n")
    # a statement after a doubled-quote string is still read
    found = naming("DO $$ BEGIN EXECUTE 'SELECT ''x'';ALTER TABLE mail_inbox_rev "
                   "ADD c text DEFAULT ''mail_inbox_rev'''; END $$;\n")
    assert found == ["ALTER TABLE mail_inbox_rev ADD c text DEFAULT 'mail_inbox_rev'"]


def test_data_strings_and_bodies_are_not_executable(sql):
    # E'' and U&'' constants and dollar bodies as data are not refused
    text = ("CREATE TABLE t (a int);\n"
            "UPDATE x SET v = REPLACE(v, U&'\\25BC', 'v') WHERE w = E'\\n';\n"
            "DO $$ BEGIN RAISE NOTICE E'it\\'s %', 'it''s'; "
            "INSERT INTO y VALUES ($m$it's$m$); END $$;\n")
    assert sql(text) == ["CREATE TABLE t (a int)"]
    assert naming(text) == []
