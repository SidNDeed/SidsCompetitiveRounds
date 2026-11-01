"""A table's DDL, read from the migration that creates it.

For the live-PostgreSQL fixtures that build a narrow schema of their own
(test_a1_predicate_sql.py, test_a1_formation_concurrency.py). Those fixtures
cannot replay the migration folder -- the formation file DROPs and recreates
players in a two-column shape, the predicate file carries only the queue
columns its predicates touch -- so when main.py starts reading another table
on their path (the readmission landing 1eb1aac6 added match_seat_holds to the
discovery predicates and the four queue tables plus match_seat_holds to the
shared admission gate), the fixture has to create that table. A hand-copied
CREATE TABLE drifts from the migration it copied; this module reads the
statement out of the migration file instead.

table_ddl(migration, table) returns [the CREATE TABLE statement, then every
CREATE INDEX on that table in the same file], in file order, with SQL
comments blanked. It raises MigrationDdlError, never returns a partial
answer, when the file is missing, when the file holds no top-level CREATE
TABLE for the name or more than one, or when the statement's parentheses do
not close before a terminating semicolon. "Top-level" means outside comments,
string literals and dollar-quoted bodies, so a CREATE TABLE quoted inside a
DO block or a comment is never taken.
"""

import os
import re

SQL_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "sql"))

_DOLLAR_TAG = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")


class MigrationDdlError(AssertionError):
    """The migration does not define the table the way the fixture needs."""


def _views(src):
    """(code, mask): both the length of src.

    code  -- src with every comment replaced by spaces (newlines kept), so a
             statement cut from it carries no comment text into text().
    mask  -- code with the CONTENTS of string literals and dollar-quoted
             bodies also replaced by spaces, so the statement search and the
             parenthesis count see only top-level SQL.
    """
    code = list(src)
    mask = list(src)
    i, n = 0, len(src)

    def blank(arr, a, b):
        for k in range(a, b):
            if arr[k] != "\n":
                arr[k] = " "

    while i < n:
        c = src[i]
        if src.startswith("--", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(code, i, j)
            blank(mask, i, j)
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                raise MigrationDdlError("unterminated block comment at offset %d" % i)
            blank(code, i, j + 2)
            blank(mask, i, j + 2)
            i = j + 2
        elif c == "'":
            j = i + 1
            while True:
                j = src.find("'", j)
                if j < 0:
                    raise MigrationDdlError("unterminated string literal at offset %d" % i)
                if src.startswith("''", j):
                    j += 2
                    continue
                break
            blank(mask, i + 1, j)
            i = j + 1
        elif c == "$" and _DOLLAR_TAG.match(src, i):
            tag = _DOLLAR_TAG.match(src, i).group(0)
            j = src.find(tag, i + len(tag))
            if j < 0:
                raise MigrationDdlError("unterminated dollar quote %s at offset %d" % (tag, i))
            blank(mask, i + len(tag), j)
            i = j + len(tag)
        else:
            i += 1
    return "".join(code), "".join(mask)


def _read(migration):
    path = os.path.join(SQL_DIR, migration)
    if not os.path.isfile(path):
        raise MigrationDdlError("migration %s not found under %s" % (migration, SQL_DIR))
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def table_ddl(migration, table):
    """[CREATE TABLE <table> ..., CREATE INDEX ... ON <table> ...] from the
    named file in backend/sql, exactly as that file defines them."""
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
        raise MigrationDdlError("not a plain table name: %r" % (table,))
    code, mask = _views(_read(migration))

    heads = list(re.finditer(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + table + r"\s*\(",
        mask, re.I))
    if len(heads) != 1:
        raise MigrationDdlError(
            "%s holds %d top-level CREATE TABLE statements for %s; exactly one "
            "is required" % (migration, len(heads), table))
    head = heads[0]
    depth, k = 0, head.end() - 1
    while k < len(mask):
        if mask[k] == "(":
            depth += 1
        elif mask[k] == ")":
            depth -= 1
            if depth == 0:
                break
        elif mask[k] == ";":
            break
        k += 1
    if depth != 0 or k >= len(mask):
        raise MigrationDdlError(
            "the CREATE TABLE %s body in %s does not close" % (table, migration))
    tail = re.match(r"\s*;", mask[k + 1:])
    if tail is None:
        raise MigrationDdlError(
            "the CREATE TABLE %s statement in %s does not end at its closing "
            "parenthesis" % (table, migration))
    out = [code[head.start():k + 1]]

    for m in re.finditer(
            r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?\w+\s+ON\s+"
            + table + r"\s*\(", mask, re.I):
        end = mask.find(";", m.end())
        if end < 0:
            raise MigrationDdlError(
                "an index on %s in %s has no terminating semicolon" % (table, migration))
        out.append(code[m.start():end])
    return out
