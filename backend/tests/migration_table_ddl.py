"""A table's DDL, read from the migration that creates it.

Users:
  - test_a1_predicate_sql.py and test_a1_formation_concurrency.py, the
    live-PostgreSQL fixtures that build a narrow schema of their own. They
    cannot replay the migration folder -- the formation file DROPs and
    recreates players in a two-column shape, the predicate file carries only
    the queue columns its predicates touch -- so when main.py starts reading
    another table on their path (the readmission landing 1eb1aac6 added
    match_seat_holds to the discovery predicates and the four queue tables
    plus match_seat_holds to the shared admission gate), the fixture creates
    that table from this module's output.
  - test_mail.py, which reads mail_inbox_rev's CREATE TABLE through table_ddl
    to compare the table's actual columns with the model's.
  - test_migration_table_ddl.py, this module's own lexical and grammar cases.

A hand-copied CREATE TABLE drifts from the migration it copied; this module
reads the statement out of the migration file instead.

ddl_naming_table(text, table) returns every CREATE, ALTER or DROP TABLE
statement in text, at the top level and in every executable position, that
creates, alters or drops the table, read with the same lexer and the same
refusals (test_mail.py's guard that no other migration changes
mail_inbox_rev).

table_ddl(migration, table) returns [the CREATE TABLE statement, then every
CREATE INDEX on that table in the same file], in file order, each cut from
its CREATE keyword to (not including) its terminating semicolon, with SQL
comments blanked.

The rule is: a form is parsed, or MigrationDdlError is raised. Nothing is
silently left out. Concretely:

  * Lexing follows PostgreSQL 16's lexical structure: line comments, NESTED
    block comments, standard strings ('' doubles a quote; a backslash is an
    ordinary character), escape strings E'...' (a backslash escapes the next
    character), the continuation rule (two string constants separated by
    whitespace holding a newline, line comments allowed in that gap, are ONE
    constant of the first one's kind, as scan.l continues it; the same two
    with no newline between them are a lexical error and raise),
    dollar-quoted bodies (tags of PostgreSQL's identifier
    alphabet: letters including every non-ASCII character, digits not first,
    underscores), and quoted identifiers ("" doubles a quote). Text inside
    any of them is never taken for a statement.
  * Names are compared as PostgreSQL resolves them: an unquoted name folds to
    lower case, a quoted one is taken exactly. A schema-qualified name, or a
    Unicode-escaped one (U&"..."), naming the table raises: the fixtures
    build into their own search_path and cannot honour either.
  * A CREATE TABLE of the table must be `name ( ... )` up to its semicolon,
    with balanced parentheses; AS, OF and PARTITION OF raise. Exactly one
    such statement may exist.
  * A CREATE INDEX on the table is parsed as
    CREATE [UNIQUE] INDEX [CONCURRENTLY] [[IF NOT EXISTS] name] ON [ONLY]
    table [USING method] ( ... ) [anything else] ; -- the index name and the
    table name may be quoted, the name may be absent -- and is returned
    whole. Parentheses that do not balance before the semicolon raise.
  * Executable positions are the dollar-quoted body of a DO and of a CREATE
    FUNCTION or PROCEDURE ... AS, and, inside such a body, the dollar bodies
    and string constants of a PL/pgSQL EXECUTE command (up to its INTO, USING
    or ';'); recursively. Each is lexed as SQL by the same lexer. Nothing is
    decoded: in an executable position a DO or AS body that is not
    dollar-quoted, an E'', U&'', B'' or X'' constant, a backslash in a
    string, a U& identifier, and a unit that does not lex to its end raise,
    whatever they name. A doubled quote and a newline continuation are
    lexing and are read. Dollar bodies and strings elsewhere are data.
  * A CREATE TABLE or CREATE INDEX naming the table in an executable
    position raises: whether and when it runs cannot be read from the file.
    A CREATE statement there runs to the lexer's ';', so a ';' in a comment,
    string or quoted name does not end it.
  * Any CREATE ... TABLE or CREATE ... INDEX head this grammar cannot parse
    raises, whatever table it names, because it might name this one.
  * A missing file, an unterminated comment, string, identifier or dollar
    body, and a statement with no terminating semicolon raise.
"""

import os
import re

SQL_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "sql"))

# PostgreSQL 16 scan.l: dolq_start [A-Za-z\200-\377_], dolq_cont adds 0-9.
# The \200-\377 bytes are every byte of a multibyte UTF-8 character, so any
# non-ASCII character is a tag letter; a digit may not come first; "$" never
# appears inside a tag.
_DOLLAR_TAG = re.compile(
    r"\$([A-Za-z_\u0080-\U0010FFFF][A-Za-z0-9_\u0080-\U0010FFFF]*)?\$")
# scan.l quotecontinue: {whitespace_with_newline}{quote}, i.e. horizontal
# whitespace or line comments, one newline, then any whitespace or line
# comments each closed by a newline, then the quote that continues the string.
# One character per repetition, so no nested quantifier can backtrack.
_QUOTE_CONTINUE = re.compile(
    r"(?:[ \t\f\v]|--[^\n\r]*)*[\n\r](?:[ \t\n\r\f\v]|--[^\n\r]*[\n\r])*'")
_LINE_COMMENT = re.compile(r"--[^\n\r]*")
# A closing quote followed by another bare quote through whitespace and
# comments that did not form a quotecontinue (tried first): no newline in
# the gap, or a block comment in it. One character or one whole comment per
# repetition, so no nested quantifier can backtrack.
_ADJACENT_QUOTE = re.compile(
    r"(?:[ \t\n\r\f\v]|--[^\n\r]*|/\*(?:(?!\*/).)*\*/)*'", re.S)
_IDENT_START = re.compile(r"[A-Za-z_\u0080-￿]")
_IDENT = re.compile(r"[A-Za-z_\u0080-￿][A-Za-z0-9_$\u0080-￿]*")
_TABLE_MODIFIERS = {"global", "local", "temporary", "temp", "unlogged", "foreign"}


class MigrationDdlError(AssertionError):
    """The migration does not define the table the way the fixture needs."""


def _is_ident_char(ch):
    return ch.isalnum() or ch in "_$" or ord(ch) >= 0x80


def _views(src):
    """(code, mask, bodies): code and mask are the length of src.

    code    -- src with every comment replaced by spaces (newlines kept), so a
               statement cut from it carries no comment text into text().
    mask    -- code with the CONTENTS of string literals, quoted identifiers
               and dollar-quoted bodies also replaced by spaces (their
               delimiters kept), so statement search and parenthesis counting
               see only top-level SQL.
    bodies  -- the (start, end) spans of dollar-quoted body contents.
    """
    code = list(src)
    mask = list(src)
    bodies = []
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
            depth, j = 1, i + 2
            while depth:
                if j >= n:
                    raise MigrationDdlError("unterminated block comment at offset %d" % i)
                if src.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif src.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            blank(code, i, j)
            blank(mask, i, j)
            i = j
        elif c == "'":
            escape = (i > 0 and src[i - 1] in "Ee"
                      and (i < 2 or not _is_ident_char(src[i - 2])))
            j = i + 1
            while True:
                if j >= n:
                    raise MigrationDdlError("unterminated string literal at offset %d" % i)
                if escape and src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "'":
                    if src.startswith("''", j):
                        j += 2
                        continue
                    # Two constants separated by whitespace holding a newline
                    # are ONE constant (scan.l quotecontinue). The continued
                    # segment keeps the first one's kind: an escape string
                    # stays an escape string, so a backslash in it still
                    # escapes. Only the gap's line comments are blanked in code.
                    cont = _QUOTE_CONTINUE.match(src, j + 1)
                    if cont:
                        for m in _LINE_COMMENT.finditer(src, j + 1, cont.end() - 1):
                            blank(code, m.start(), m.end())
                        j = cont.end()
                        continue
                    break
                j += 1
            # The same two constants with no newline between them are a
            # lexical error in PostgreSQL; the lexer refuses them.
            if _ADJACENT_QUOTE.match(src, j + 1):
                raise MigrationDdlError(
                    "two string constants with no newline between them at offset %d" % (j + 1))
            blank(mask, i + 1, j)
            i = j + 1
        elif c == '"':
            j = i + 1
            while True:
                j = src.find('"', j)
                if j < 0:
                    raise MigrationDdlError("unterminated quoted identifier at offset %d" % i)
                if src.startswith('""', j):
                    j += 2
                    continue
                break
            blank(mask, i + 1, j)
            i = j + 1
        elif (c == "$" and (i == 0 or not _is_ident_char(src[i - 1]))
              and _DOLLAR_TAG.match(src, i)):
            tag = _DOLLAR_TAG.match(src, i).group(0)
            j = src.find(tag, i + len(tag))
            if j < 0:
                raise MigrationDdlError("unterminated dollar quote %s at offset %d" % (tag, i))
            blank(mask, i + len(tag), j)
            bodies.append((i + len(tag), j))
            i = j + len(tag)
        else:
            i += 1
    return "".join(code), "".join(mask), bodies


def _tokens(code, mask):
    """Top-level tokens of mask: (kind, value, start, end). kind is 'ident'
    (value lower-cased), 'qident' (value as written, from code), 'string',
    'dollar', or 'punct' (one character)."""
    out = []
    i, n = 0, len(mask)
    while i < n:
        c = mask[i]
        if c.isspace():
            i += 1
        elif _IDENT_START.match(c):
            m = _IDENT.match(mask, i)
            out.append(("ident", m.group(0).lower(), i, m.end()))
            i = m.end()
        elif c == '"':
            j = mask.index('"', i + 1)
            out.append(("qident", code[i + 1:j].replace('""', '"'), i, j + 1))
            i = j + 1
        elif c == "'":
            j = mask.index("'", i + 1)
            out.append(("string", None, i, j + 1))
            i = j + 1
        elif (c == "$" and (i == 0 or not _is_ident_char(mask[i - 1]))
              and _DOLLAR_TAG.match(mask, i)):
            tag = _DOLLAR_TAG.match(mask, i).group(0)
            j = mask.index(tag, i + len(tag))
            out.append(("dollar", None, i, j + len(tag)))
            i = j + len(tag)
        else:
            out.append(("punct", c, i, i + 1))
            i += 1
    return out


def _at(toks, k):
    return toks[k] if k < len(toks) else None


def _kw(tok, word):
    return tok is not None and tok[0] == "ident" and tok[1] == word


def _if_not_exists(toks, j):
    return (_kw(_at(toks, j), "if") and _kw(_at(toks, j + 1), "not")
            and _kw(_at(toks, j + 2), "exists"))


def _name(toks, k, migration, what):
    """Parse a possibly qualified name at toks[k]. Returns (schema, rel, k')
    with names as PostgreSQL resolves them, or raises."""
    def one(k):
        t = _at(toks, k)
        if t is None or t[0] not in ("ident", "qident"):
            raise MigrationDdlError("%s: cannot parse the %s name at offset %s"
                                    % (migration, what, t[2] if t else "EOF"))
        if (t[0] == "ident" and t[1] == "u"
                and (_at(toks, k + 1) or ())[:2] == ("punct", "&")):
            raise MigrationDdlError("%s: a Unicode-escaped %s name (U&\"...\") at offset %d "
                                    "is not supported" % (migration, what, t[2]))
        return t[1], k + 1
    first, k = one(k)
    if (_at(toks, k) or ())[:2] == ("punct", "."):
        second, k = one(k + 1)
        if (_at(toks, k) or ())[:2] == ("punct", "."):
            raise MigrationDdlError("%s: a three-part %s name at offset %d is not supported"
                                    % (migration, what, toks[k][2]))
        return first, second, k
    return None, first, k


def _statement_end(toks, k, migration, label):
    """Index of the ';' token closing the statement that continues at toks[k],
    with parentheses balanced; raises otherwise."""
    depth = 0
    while k < len(toks):
        t = toks[k]
        if t[0] == "punct":
            if t[1] == "(":
                depth += 1
            elif t[1] == ")":
                depth -= 1
                if depth < 0:
                    raise MigrationDdlError("%s: %s has an unmatched ')' at offset %d"
                                            % (migration, label, t[2]))
            elif t[1] == ";":
                if depth != 0:
                    raise MigrationDdlError("%s: %s ends before its parentheses close"
                                            % (migration, label))
                return k
        k += 1
    raise MigrationDdlError("%s: %s has no terminating semicolon" % (migration, label))


def _is_name(tok, table):
    """tok is a name that PostgreSQL resolves to table."""
    return tok[0] in ("ident", "qident") and tok[1] == table


def _adjacent(left, right):
    return left is not None and left[3] == right[2]


def _string_content(code, toks, p, where):
    """The content of the standard string constant toks[p], read by the
    lexer's own rules: '' is one quote character, and segments joined by a
    newline continuation are one constant. Nothing is decoded: an E'' string
    (any backslash escape), a U& string, a B'' or X'' constant, and a
    backslash anywhere in the text refuse."""
    t = toks[p]
    prev = toks[p - 1] if p else None
    if _adjacent(prev, t) and prev[0] == "ident" and prev[1] in ("e", "b", "x"):
        raise MigrationDdlError("an %s'' string constant in %s at offset %d is not read"
                                % (prev[1].upper(), where, prev[2]))
    if _adjacent(prev, t) and prev[:2] == ("punct", "&"):
        raise MigrationDdlError("a U&'' string constant in %s at offset %d is not read"
                                % (where, prev[2]))
    out, j = [], t[2] + 1
    while True:
        ch = code[j]
        if ch == "'":
            if code.startswith("''", j):
                out.append("'")
                j += 2
                continue
            cont = _QUOTE_CONTINUE.match(code, j + 1)
            if cont and cont.end() < t[3]:
                j = cont.end()
                continue
            break
        if ch == "\\":
            raise MigrationDdlError("a backslash in a string constant in %s at offset %d "
                                    "is not read" % (where, j))
        out.append(ch)
        j += 1
    if j != t[3] - 1:
        raise MigrationDdlError("the string constant in %s at offset %d is not read to its end"
                                % (where, t[2]))
    return "".join(out)


def _exec_kind(toks, p, top, execute_at):
    """Whether toks[p] (a 'dollar' or 'string' token) sits in an executable
    position: 'do' (the body of DO [LANGUAGE name]), 'as' (the AS body of a
    CREATE FUNCTION or PROCEDURE), 'execute' (inside the command of a
    PL/pgSQL EXECUTE, in a body: from EXECUTE to its INTO, USING or ';'), or
    None (data)."""
    prev = toks[p - 1] if p else None
    if _kw(prev, "do") or (p >= 3 and _kw(toks[p - 3], "do") and _kw(toks[p - 2], "language")):
        return "do"
    if _kw(prev, "as"):
        b = p - 2
        while b >= 0 and toks[b][:2] != ("punct", ";"):
            if toks[b][0] == "ident" and toks[b][1] in ("function", "procedure"):
                return "as"
            b -= 1
    if not top and p in execute_at:
        return "execute"
    return None


def _units(src):
    """Yield (code, toks, origin) for src and every executable unit inside it,
    each lexed as SQL: the dollar-quoted body of a DO or of a CREATE FUNCTION
    or PROCEDURE ... AS, and, inside such a body, the dollar bodies and string
    constants of an EXECUTE command; recursively. origin is the offset in src
    of the outermost body (None for src itself).

    Refused unconditionally, whatever the text names: a DO or AS body that is
    not dollar-quoted; an executable string that is an E'', U&'', B'' or X''
    constant or holds a backslash; a U& identifier in any unit; and a unit
    that does not lex to its end. Doubled quotes and newline continuations
    are lexing and are read. Dollar bodies and strings in any other position
    are data and are not walked."""
    def walk(text, origin, top):
        try:
            code, mask, _bodies = _views(text)
            toks = _tokens(code, mask)
        except MigrationDdlError as exc:
            if top:
                raise
            raise MigrationDdlError("the executable body at offset %d does not lex to its "
                                    "end: %s" % (origin, exc))
        where = "the file" if top else "the executable body at offset %d" % origin
        for k in range(len(toks) - 2):
            if (toks[k][:2] == ("ident", "u") and toks[k + 1][:2] == ("punct", "&")
                    and _adjacent(toks[k], toks[k + 1])
                    and _adjacent(toks[k + 1], toks[k + 2]) and toks[k + 2][0] == "qident"):
                raise MigrationDdlError("a U& identifier in %s at offset %d is not read"
                                        % (where, toks[k][2]))
        yield code, toks, origin
        execute_at = set()
        if not top:
            for k, t in enumerate(toks):
                if _kw(t, "execute"):
                    e = k + 1
                    while (e < len(toks) and toks[e][:2] != ("punct", ";")
                           and not _kw(toks[e], "into") and not _kw(toks[e], "using")):
                        execute_at.add(e)
                        e += 1
        for p, t in enumerate(toks):
            if t[0] not in ("dollar", "string"):
                continue
            kind = _exec_kind(toks, p, top, execute_at)
            if kind is None:
                continue
            if t[0] == "dollar":
                tag = _DOLLAR_TAG.match(code, t[2]).group(0)
                a = t[2] + len(tag)
                yield from walk(text[a:t[3] - len(tag)], a if top else origin, False)
            elif kind in ("do", "as"):
                raise MigrationDdlError("a %s body in %s at offset %d is not dollar-quoted"
                                        % (kind.upper(), where, t[2]))
            else:
                inner = _string_content(code, toks, p, where)
                yield from walk(inner, t[2] if top else origin, False)
    yield from walk(src, None, True)


def _spans(toks, heads):
    """(k, e) for every token k that is one of the head keywords: the run
    from it to the next lexer ';' (e is that ';', or len(toks))."""
    for k, t in enumerate(toks):
        if t[0] == "ident" and t[1] in heads:
            e = k + 1
            while e < len(toks) and toks[e][:2] != ("punct", ";"):
                e += 1
            yield k, e


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
    src = _read(migration)
    code, mask, bodies = _views(src)

    # DDL naming this table inside an executable body cannot be placed.
    # Each executable unit (_units) is lexed like the file, so its statements
    # end at a lexer ';' and never at a ';' inside a comment, a string or a
    # quoted name; a unit that cannot be read refuses, whatever it names.
    for _code, utoks, origin in _units(src):
        if origin is None:
            continue
        for k, e in _spans(utoks, ("create",)):
            kinds = [m for m in range(k + 1, e) if utoks[m][0] == "ident"
                     and utoks[m][1] in ("table", "index")]
            if kinds and any(_is_name(utoks[m], table) for m in range(kinds[0] + 1, e)):
                raise MigrationDdlError(
                    "%s: a CREATE TABLE or CREATE INDEX naming %s sits inside a dollar-quoted "
                    "body at offset %d; whether it runs cannot be read from the file"
                    % (migration, table, origin))

    toks = _tokens(code, mask)
    tables, indexes = [], []
    k = 0
    while k < len(toks):
        if not _kw(toks[k], "create"):
            k += 1
            continue
        start = toks[k][2]

        # CREATE [GLOBAL|LOCAL] [TEMP|TEMPORARY|UNLOGGED|FOREIGN] TABLE
        j = k + 1
        while (_at(toks, j) or ("",))[0] == "ident" and toks[j][1] in _TABLE_MODIFIERS:
            j += 1
        if _kw(_at(toks, j), "table"):
            j += 1
            if _if_not_exists(toks, j):
                j += 3
            schema, rel, j = _name(toks, j, migration, "table")
            if rel != table:
                k = j
                continue
            if schema is not None:
                raise MigrationDdlError(
                    "%s: the CREATE TABLE of %s at offset %d is schema-qualified (%s)"
                    % (migration, table, start, schema))
            if (_at(toks, j) or ())[:2] != ("punct", "("):
                raise MigrationDdlError(
                    "%s: the CREATE TABLE of %s at offset %d is not a column list "
                    "(AS, OF and PARTITION OF are not supported)" % (migration, table, start))
            end = _statement_end(toks, j, migration, "the CREATE TABLE of " + table)
            tables.append((start, toks[end][2]))
            k = end + 1
            continue

        # CREATE [UNIQUE] INDEX [CONCURRENTLY] [[IF NOT EXISTS] name] ON [ONLY] t
        j = k + 1
        if _kw(_at(toks, j), "unique"):
            j += 1
        if not _kw(_at(toks, j), "index"):
            k += 1
            continue
        j += 1
        if _kw(_at(toks, j), "concurrently"):
            j += 1
        if _if_not_exists(toks, j):
            _s, _n, j = _name(toks, j + 3, migration, "index")
        elif not _kw(_at(toks, j), "on"):
            _s, _n, j = _name(toks, j, migration, "index")
        if not _kw(_at(toks, j), "on"):
            raise MigrationDdlError("%s: cannot parse the CREATE INDEX at offset %d"
                                    % (migration, start))
        j += 1
        if _kw(_at(toks, j), "only"):
            j += 1
        schema, rel, j = _name(toks, j, migration, "indexed table")
        if rel != table:
            k = j
            continue
        if schema is not None:
            raise MigrationDdlError(
                "%s: the CREATE INDEX on %s at offset %d is schema-qualified (%s)"
                % (migration, table, start, schema))
        if _kw(_at(toks, j), "using"):
            if (_at(toks, j + 1) or ("",))[0] not in ("ident", "qident"):
                raise MigrationDdlError("%s: the CREATE INDEX at offset %d has no "
                                        "access method after USING" % (migration, start))
            j += 2
        if (_at(toks, j) or ())[:2] != ("punct", "("):
            raise MigrationDdlError("%s: the CREATE INDEX on %s at offset %d has no "
                                    "column list" % (migration, table, start))
        end = _statement_end(toks, j, migration, "a CREATE INDEX on " + table)
        indexes.append((start, toks[end][2]))
        k = end + 1

    if len(tables) != 1:
        raise MigrationDdlError(
            "%s holds %d top-level CREATE TABLE statements for %s; exactly one "
            "is required" % (migration, len(tables), table))
    return [code[a:b] for a, b in tables + indexes]


def _table_statement_names(toks, k, e, label):
    """The relations a CREATE, ALTER or DROP statement at toks[k:e] creates,
    alters or drops, as (schema, rel) pairs; [] when it is not a TABLE
    statement. Forms read:
      CREATE [GLOBAL|LOCAL] [TEMP|TEMPORARY|UNLOGGED|FOREIGN] TABLE
             [IF NOT EXISTS] name
      ALTER [FOREIGN] TABLE [IF EXISTS] [ONLY] name ... plus the target of
             every RENAME TO, ATTACH PARTITION and DETACH PARTITION in it
      ALTER TABLE ALL IN TABLESPACE ... (names no relation)
      DROP [FOREIGN] TABLE [IF EXISTS] name [, name ...]
    A name that does not parse raises (MigrationDdlError from _name)."""
    head = toks[k][1]
    j = k + 1
    if head == "create":
        while (_at(toks, j) or ("",))[0] == "ident" and toks[j][1] in _TABLE_MODIFIERS:
            j += 1
    elif _kw(_at(toks, j), "foreign"):
        j += 1
    if j >= e or not _kw(toks[j], "table"):
        return []
    j += 1
    names = []
    if head == "create":
        if _if_not_exists(toks, j):
            j += 3
        schema, rel, j = _name(toks, j, label, "table")
        names.append((schema, rel))
    elif head == "alter":
        if _kw(_at(toks, j), "all") and _kw(_at(toks, j + 1), "in"):
            return []
        if _kw(_at(toks, j), "if") and _kw(_at(toks, j + 1), "exists"):
            j += 2
        if _kw(_at(toks, j), "only"):
            j += 1
        schema, rel, j = _name(toks, j, label, "table")
        names.append((schema, rel))
        for m in range(j, e - 1):
            if ((_kw(toks[m], "to") and _kw(toks[m - 1], "rename"))
                    or (_kw(toks[m], "partition")
                        and (_kw(toks[m - 1], "attach") or _kw(toks[m - 1], "detach")))):
                schema, rel, _j = _name(toks, m + 1, label, "table")
                names.append((schema, rel))
    else:
        if _kw(_at(toks, j), "if") and _kw(_at(toks, j + 1), "exists"):
            j += 2
        while True:
            schema, rel, j = _name(toks, j, label, "table")
            names.append((schema, rel))
            if (_at(toks, j) or ())[:2] != ("punct", ","):
                break
            j += 1
    return names


def ddl_naming_table(text, table):
    """Every CREATE, ALTER or DROP TABLE statement in SQL text that creates,
    alters or drops table (in any schema), cut from its head keyword to (not
    including) its lexer ';', comments blanked; [] when there is none.

    The statements are found by the same lexer as table_ddl, at the top level
    and in every executable unit (_units: DO and AS bodies, and the commands
    of EXECUTE inside them), so a quoted name, a comment between TABLE and
    the name, a name split across a newline continuation, or a statement
    inside a DO block is read the way PostgreSQL reads it, and a column or
    string that merely spells the name is not a statement on it. Raises
    MigrationDdlError when any unit cannot be read (see _units) and when a
    TABLE statement's name does not parse, whatever it names."""
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
        raise MigrationDdlError("not a plain table name: %r" % (table,))
    out = []
    for code, toks, _origin in _units(text):
        for k, e in _spans(toks, ("create", "alter", "drop")):
            names = _table_statement_names(toks, k, e, "a TABLE statement")
            if any(rel == table for _schema, rel in names):
                end = toks[e][2] if e < len(toks) else len(code)
                out.append(code[toks[k][2]:end])
    return out
