"""Migration 420 and its rollback: every function call and every jsonb path
operator names pg_catalog (S1 of the MODLOG-1 fix order). No database.

Why the schema at the call and not the pinned path alone: among functions
(and operators) of one name, PostgreSQL's search path decides only between
those of IDENTICAL argument types. One of the same name with other argument
types, in any schema on the path, competes with pg_catalog's on an equal
footing, so a call whose arguments are no exact match of pg_catalog's
signature (an untyped literal among them, a VARIADIC "any" function such as
format) can take it even with pg_catalog first on the path. The same holds
for an operator with an untyped literal operand where pg_catalog has no
operator for the other operand's type twice (jsonb ->> 'key': the literal is
read as jsonb first, and pg_catalog has no ->> for jsonb with jsonb).
test_modlog_pg.py shows each of these taken on PostgreSQL.

The census reads both files, blanks comments and single-quoted literals,
keeps the bodies of dollar-quoted strings as code (every one in these files
is PL/pgSQL or SQL text that runs), and finds every `name (`. Each must be
written pg_catalog.<name>( or be one of the SQL constructs of CONSTRUCTS,
each listed with its reason. Every jsonb path operator must be written
OPERATOR(pg_catalog.<op>). The files may hold no double-quoted identifier
and no backslash, so the blanking above is the whole lexing they need.
"""
import collections
import io
import os
import re

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SQL = os.path.normpath(os.path.join(HERE, "..", "sql"))
FILES = {
    "420": os.path.join(SQL, "420_admin_actions_modlog.sql"),
    "rollback_420": os.path.join(SQL, "rollback_420_admin_actions_modlog.sql"),
}

# The words that stand before "(" in these files and are not function calls.
# Matched case-insensitively and only when written without a schema.
CONSTRUCTS = {
    "and": "boolean connective before a parenthesised condition",
    "or": "boolean connective before a parenthesised condition",
    "not": "boolean negation before a parenthesised condition",
    "in": "IN (list or subquery), a construct of the grammar",
    "any": "= ANY (array), a construct of the grammar",
    "exists": "EXISTS (subquery), a construct of the grammar",
    "array": "ARRAY(subquery), the array constructor",
    "coalesce": "COALESCE(...), a construct of the grammar, not a catalog function",
    "operator": "OPERATOR(schema.op), the qualified operator syntax itself",
    "check": "CHECK (expression) of the constraint 420 adds",
    "from": "FROM (subquery) alias, a derived table",
    "gin": "USING gin (column) of CREATE INDEX: the access method and its column list",
    "admin_actions": "INSERT INTO admin_actions (column list)",
}

JSONB_OPS = ("->>", "->", "#>>", "#>")

_DOLLAR = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")
_CALL = re.compile(r"(?<![A-Za-z0-9_.$])(?:([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_QUALIFIED_OP = re.compile(r"OPERATOR\s*\(\s*pg_catalog\s*\.\s*(->>|->|#>>|#>)\s*\)", re.I)
_ANY_OP = re.compile(r"->>|->|#>>|#>")


def code_of(src):
    """The source with comments and single-quoted literals blanked (each
    character a space, newlines kept, so a position is the source's own) and
    dollar-quote delimiters blanked (their bodies stay code)."""
    assert "\\" not in src, "a backslash in the file: the census lexes no escape"
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("--", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out[i:j] = " " * (j - i)
            i = j
        elif src.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if src.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif src.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            assert depth == 0, "an unterminated block comment"
            out[i:j] = [ch if ch == "\n" else " " for ch in src[i:j]]
            i = j
        elif c == "'":
            j = i + 1
            while True:
                k = src.find("'", j)
                assert k >= 0, "an unterminated literal"
                if src.startswith("''", k):
                    j = k + 2
                    continue
                break
            out[i:k + 1] = [ch if ch == "\n" else " " for ch in src[i:k + 1]]
            i = k + 1
        elif c == '"':
            raise AssertionError("a double-quoted identifier at offset %d: the census reads none" % i)
        elif c == "$":
            m = _DOLLAR.match(src, i)
            if m:
                out[i:m.end()] = " " * (m.end() - i)
                i = m.end()
            else:
                i += 1
        else:
            i += 1
    return "".join(out)


def census(src):
    """(unqualified calls, qualified calls, unqualified operators), each a
    list of (offset, text)."""
    code = code_of(src)
    bad, good = [], []
    for m in _CALL.finditer(code):
        schema, name = m.group(1), m.group(2)
        if schema is None and name.lower() in CONSTRUCTS:
            continue
        if schema is not None and schema.lower() == "pg_catalog":
            good.append((m.start(2), name.lower()))
        else:
            bad.append((m.start(), m.group(0)))
    covered = set()
    for m in _QUALIFIED_OP.finditer(code):
        covered.update(range(m.start(1), m.end(1)))
    ops = [(m.start(), m.group(0)) for m in _ANY_OP.finditer(code) if m.start() not in covered]
    return bad, good, ops


def _line(src, off):
    return src.count("\n", 0, off) + 1


def _read(key):
    return io.open(FILES[key], encoding="utf-8", newline="").read()


@pytest.mark.parametrize("key", sorted(FILES))
def test_every_call_and_jsonb_operator_names_pg_catalog(key, capsys):
    src = _read(key)
    bad, good, ops = census(src)
    with capsys.disabled():
        per = collections.Counter(n for _, n in good)
        print("\nMODLOG-SQL-CENSUS %s: %d qualified calls %s; jsonb operators qualified %d"
              % (key, len(good), dict(sorted(per.items())), len(_QUALIFIED_OP.findall(code_of(src)))))
    assert not bad, ["%s:%d %s" % (key, _line(src, o), t) for o, t in bad]
    assert not ops, ["%s:%d %s" % (key, _line(src, o), t) for o, t in ops]


def _qualified_sites(src):
    """Every pg_catalog.<name>( and OPERATOR(pg_catalog.<op>) of the code, as
    (start, end, replacement) of its unqualified form in the source."""
    code = code_of(src)
    sites = []
    for m in re.finditer(r"pg_catalog\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", code):
        if code[max(0, m.start() - 1)].isalnum() or code[max(0, m.start() - 1)] in "_.":
            continue
        sites.append((m.start(), m.start(1), ""))
    for m in _QUALIFIED_OP.finditer(code):
        sites.append((m.start(), m.end(), " " + m.group(1) + " "))
    return sites


@pytest.mark.parametrize("key", sorted(FILES))
def test_mutant_each_qualified_site_unqualified_is_red(key):
    """One mutant per site: the file with that one call (or operator) written
    without its schema is refused, naming that line."""
    src = _read(key)
    sites = _qualified_sites(src)
    assert sites, "no qualified site found"
    missed = []
    for start, end, repl in sites:
        mutant = src[:start] + repl + src[end:]
        bad, _, ops = census(mutant)
        if not bad and not ops:
            missed.append("%s:%d" % (key, _line(src, start)))
    assert not missed, missed


def test_mutant_unqualified_call_beside_a_comment_holding_the_qualified_form_is_red():
    src = _read("420")
    start, end, _ = _qualified_sites(src)[0]
    eol = src.index("\n", end)
    mutant = src[:start] + src[end:eol] + "   -- pg_catalog.format( pg_catalog.left(" + src[eol:]
    bad, _, _ = census(mutant)
    assert bad, "an unqualified call passed beside a comment that holds the qualified form"


@pytest.mark.parametrize("text", [
    "SELECT format('%s', 1);",
    "SELECT public.format('%s', 1);",
    "SELECT format ('%s', 1);",
    "SELECT PG_CATALOG.left('x', 1), format_type(1, NULL);",
    "DO $b$ BEGIN PERFORM jsonb_typeof('{}'); END $b$;",
    "SELECT '{}'::jsonb ->> 'k';",
    "SELECT '{}'::jsonb OPERATOR(public.->) 'k';",
])
def test_mutant_shapes_of_an_unqualified_call_are_red(text):
    bad, _, ops = census(text)
    assert bad or ops, text


@pytest.mark.parametrize("text", [
    "SELECT pg_catalog.format('%s', 1);",
    "SELECT COALESCE(pg_catalog.left('format(', 1), 'x') -- format(\n;",
    "DO $b$ BEGIN PERFORM pg_catalog.jsonb_typeof('{}'::jsonb); END $b$;",
    "SELECT '{}'::jsonb OPERATOR(pg_catalog.->>) 'k';",
])
def test_control_shapes_of_a_qualified_call_are_green(text):
    bad, _, ops = census(text)
    assert not bad and not ops, (text, bad, ops)
