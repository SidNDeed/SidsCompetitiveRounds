"""CHEAT-ALT-1 surfaces: what a player is told the server may record at
sign-in, where it is told, and what reaches the process.

  * R5, the disclosure table: every column of the three tables 427 creates is
    mapped by fixtures/alt_signals_disclosure.json to a category the sentence
    names, or to bookkeeping from a closed list (the account's own id as the
    row key, and the key id). A column added later and not mapped fails here,
    and so does a sentence that stops naming a category.
  * R6, the sentence on every surface: alt_signals.DISCLOSURE is the last
    paragraph of docs/FAQ.md's message 1 and of the newest migration that
    carries message 1, and it is in the bot's `recorded` answer. The recording
    opens only while the posted message 1 holds the sentence (its notice
    check, test_alt_signals_record_pg.py); a later FAQ edit that drops the
    sentence fails here, at build time, instead of closing that check in
    silence.
  * The bot's `recorded` entry: last in FAQ_ENTRIES, takes no older entry's
    examples, answers its own; its in-game short states the deadline.
  * /health: both arms carry alt_signals_build and alt_signals_key, and the
    schema requires both.
  * The key reaches the api container: compose names it for the api service
    only, and env.template carries it empty.
  * The reader census: only the recording, account deletion, the retention
    pass and the read function name the three tables.

The sign-in's own shape (the request parameter, the guard, the order of the
two transactions) is test_alt_signals_record_pg.py's. Pure: no database."""

import ast
import asyncio
import json
import os
import re

import pydantic
import pytest

import alt_signals
import main
import schemas

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
REPO = os.path.dirname(BACKEND)
SQL_DIR = os.path.join(BACKEND, "sql")
FIXTURE = os.path.join(HERE, "fixtures", "alt_signals_disclosure.json")
MIGRATION_427 = os.path.join(SQL_DIR, "427_alt_signals.sql")
FAQ_MD = os.path.join(REPO, "docs", "FAQ.md")
BOT = os.path.join(BACKEND, "discord_bot.py")
COMPOSE = os.path.join(BACKEND, "docker-compose.yml")
ENV_TEMPLATE = os.path.join(BACKEND, "api", "env.template")

TABLES = ("steam_signin_facts", "steam_family_shares", "conn_markers")
BOOKKEEPING = frozenset({"steam_id", "key_id"})


def _read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read().replace("\r\n", "\n")


def _fixture():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


# -- R5: the disclosure table ------------------------------------------------

_CREATE = re.compile(r"CREATE TABLE (\w+) \((.*?)\n\s*\);", re.S)
# The type is closed by a lookahead, not by a word boundary: a boundary
# after VARCHAR(8)'s closing parenthesis never holds before a space, and the
# reader would lose every VARCHAR column.
_COLUMN = re.compile(r"^\s+([a-z_][a-z0-9_]*)\s+(?:TEXT|TIMESTAMPTZ|VARCHAR\(\d+\)|BOOLEAN|INTEGER|"
                     r"SMALLINT|DATE|BYTEA)(?![A-Za-z0-9_])", re.M)


def _ddl_columns(sql):
    """{table: [column, ...]} for every CREATE TABLE of `sql`, comments
    stripped, in the order the DDL declares them."""
    sql = re.sub(r"--[^\n]*", "", sql)
    return {name: _COLUMN.findall(body) for name, body in _CREATE.findall(sql)}


def _ddl_unknown(sql):
    """Every line of a CREATE TABLE body of `sql` that is neither a column of
    a type the reader knows nor a CONSTRAINT line, as "table: line" (M2: a
    form the reader does not know turns the check red and is named)."""
    sql = re.sub(r"--[^\n]*", "", sql)
    out = []
    for name, body in _CREATE.findall(sql):
        for line in body.split("\n"):
            if not line.strip() or line.strip().startswith("CONSTRAINT "):
                continue
            if not _COLUMN.match(" " + line.lstrip()):
                out.append("%s: %s" % (name, line.strip()))
    return out


# The closed table of statement heads (holder H3). 427 is read statement by
# statement: the top level split at its semicolons, and each DO body split
# the same way; quoted and dollar-quoted text is skipped and a -- comment is
# dropped; inside a body DECLARE, BEGIN and ELSE, and an IF or ELSIF up to
# its THEN, are taken off, and the first line left is the head. A head on no
# row of _HEADS is refused, naming its line; so are a /* comment, an E'' or
# U&'' string and a double-quoted name outside quoted text, which 427 does
# not hold. An EXECUTE is read only as format() of one literal whose only
# placeholder is %L, and the literal's head must stand on an "execute" row.
_HEADS = (
    ("top", r"BEGIN$", "passed: opens the transaction"),
    ("top", r"SET LOCAL \w+ = ", "passed: a setting of the transaction"),
    ("top", r"DO \$\w+\$$", "read: its body, by this table"),
    ("top", r"COMMIT$", "passed: ends the transaction"),
    ("declare", r"[a-z_]+ (CONSTANT )?(text|integer)( :=|$)", "passed: a variable of the block"),
    ("body", r"[a-z_]+ := ", "passed: sets a variable"),
    ("body", r"RAISE EXCEPTION '", "passed: aborts the file"),
    ("body", r"END( IF)?$", "passed: closes a block"),
    ("body", r"SELECT ", "passed: in PL/pgSQL its INTO fills variables and makes no table"),
    ("body", r"PERFORM ", "passed: runs a query and keeps no result"),
    ("body", r"UPDATE ", "passed: writes rows, not columns"),
    ("body", r"GET DIAGNOSTICS ", "passed: reads a row count"),
    ("body", r"CREATE TABLE [a-z_]+ \($", "read: its body, by the body reader"),
    ("body", r"CREATE INDEX ", "passed: an index makes no column"),
    ("body", r"EXECUTE format\('[^']*'(, [a-z_]+)*\)$", "read: its literal, by the execute rows"),
    ("execute", r"COMMENT ON TABLE [a-z_]+ IS %L$", "passed: a comment on a table makes no column"),
)


def _ddl_outside(text):
    """Each statement of `text` that _HEADS does not read, as "line N: first
    line": a head on no row, an EXECUTE whose literal's head is on no
    "execute" row or whose form is not format() of one literal with %L, and
    each /* comment, E'' or U&'' string and double-quoted name outside
    quoted text. LIMIT: a statement run by a function that 427 calls is not
    read."""
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    tag_re = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")
    found = []

    def say(pos, what=None):
        i = text.count("\n", 0, pos)
        found.append("line %d: %s" % (i + 1, lines[i].strip() if what is None else what))

    def mask(lo, hi):
        # (bare, plain) of text[lo:hi]: bare blanks quoted text and comments, plain blanks comments only;
        # line ends are kept, so a position means the same in both and in the text
        bare, plain = list(text[lo:hi]), list(text[lo:hi])

        def blank(a, b, both):
            for k in range(a, b):
                if text[k] != "\n":
                    bare[k - lo] = " "
                    if both:
                        plain[k - lo] = " "
        i = lo
        while i < hi:
            if text.startswith("--", i):
                j = text.find("\n", i, hi)
                j = hi if j < 0 else j
                blank(i, j, True)
                i = j
            elif text.startswith("/*", i):
                say(i)
                i += 2
            elif text[i] == "'":
                if text[i - 1:i] in ("E", "e") and not re.match(r"\w", text[i - 2:i - 1] or " "):
                    say(i)
                elif text[i - 2:i] in ("U&", "u&") and not re.match(r"\w", text[i - 3:i - 2] or " "):
                    say(i)
                j = i + 1
                while True:
                    k = text.find("'", j, hi)
                    if k < 0:
                        k = hi
                    elif k + 1 < hi and text[k + 1] == "'":
                        j = k + 2
                        continue
                    break
                blank(i + 1, k, False)
                i = k + 1
            elif text[i] == '"':
                say(i)
                k = text.find('"', i + 1, hi)
                k = hi if k < 0 else k
                blank(i + 1, k, False)
                i = k + 1
            elif text[i] == "$" and tag_re.match(text, i):
                tag = tag_re.match(text, i).group(0)
                k = text.find(tag, i + len(tag), hi)
                k = hi if k < 0 else k
                blank(i + len(tag), k, False)
                i = k + len(tag)
            else:
                i += 1
        return "".join(bare), "".join(plain)

    def read(lo, hi, scope):
        bare, plain = mask(lo, hi)
        begun, s0 = False, 0
        for e in [m.start() for m in re.finditer(";", bare)] + [len(bare)]:
            s, s0 = s0, e + 1
            while scope == "body":
                m = re.match(r"\s*(DECLARE|BEGIN|ELSE)\b", bare[s:e])
                if m:
                    begun = begun or m.group(1) == "BEGIN"
                    s += m.end()
                    continue
                m = re.match(r"\s*(IF|ELSIF)\b", bare[s:e])
                t = re.search(r"\bTHEN\b", bare[s + m.end():e]) if m else None
                if t is None:
                    break
                s += m.end() + t.end()
            s += len(bare[s:e]) - len(bare[s:e].lstrip())
            if s >= e:
                continue
            head = plain[s:e].split("\n", 1)[0].strip()
            head = head[:-1] if head.endswith(";") else head
            kinds = ("top",) if scope == "top" else ("body",) if begun else ("declare", "body")
            row = next((r for r in _HEADS if r[0] in kinds and re.match(r[1], head)), None)
            at = lo + s
            if row is None:
                say(at, head)
                continue
            if row[2] == "read: its body, by this table":
                tag = tag_re.search(text, at, lo + e)
                close = text.find(tag.group(0), tag.end(), lo + e)
                read(tag.end(), close if close >= 0 else lo + e, "body")
            elif row[2] == "read: its literal, by the execute rows":
                literal = re.match(r"EXECUTE format\('([^']*)'", head).group(1)
                if not any(r[0] == "execute" and re.match(r[1], literal) for r in _HEADS):
                    say(at, head)
    read(0, len(text), "top")
    return found


def _disclosure_problems(sql, fixture, sentence):
    """Everything wrong between 427's DDL, the table and the sentence."""
    problems = ["a CREATE TABLE line the reader does not know: %s" % u for u in _ddl_unknown(sql)]
    problems += ["a statement the closed table of heads does not read: %s" % u
                 for u in _ddl_outside(sql)]
    tables = _ddl_columns(sql)
    if set(tables) != set(TABLES):
        problems.append("the DDL creates %s, not the three tables" % sorted(tables))
    ddl = {"%s.%s" % (t, c) for t, cols in tables.items() for c in cols}
    mapped = {}
    for cat, spec in fixture["categories"].items():
        for col in spec["columns"]:
            mapped.setdefault(col, []).append(cat)
    for col in fixture["bookkeeping"]:
        mapped.setdefault(col, []).append("bookkeeping")
        if col.split(".", 1)[-1] not in BOOKKEEPING:
            problems.append("%s is called bookkeeping and is not on the closed list %s"
                            % (col, sorted(BOOKKEEPING)))
    for col in sorted(ddl):
        if col not in mapped:
            problems.append("%s is a column of 427 that the disclosure table does not map" % col)
        elif len(mapped[col]) > 1:
            problems.append("%s is mapped twice: %s" % (col, mapped[col]))
    for col in sorted(set(mapped) - ddl):
        problems.append("%s is mapped and is no column of 427" % col)
    for cat, spec in sorted(fixture["categories"].items()):
        if not spec["words"] or not spec["columns"]:
            problems.append("category %s names no words or no columns" % cat)
        for words in spec["words"]:
            if words not in sentence:
                problems.append("the sentence lacks %r, the words of category %s" % (words, cat))
    for cat, words_list in sorted(fixture["sentence_only"].items()):
        for words in words_list:
            words = words.replace("{DEADLINE_DAYS}", str(alt_signals.DEADLINE_DAYS))
            if words not in sentence:
                problems.append("the sentence lacks %r (%s)" % (words, cat))
    return problems


def test_every_column_of_the_three_tables_is_disclosed_or_bookkeeping():
    sql, fixture = _read(MIGRATION_427), _fixture()
    assert _disclosure_problems(sql, fixture, alt_signals.DISCLOSURE) == []
    # 14, 5 and 9 columns: fewer means the DDL reader lost some, and a lost
    # column the table does not map would pass the check above unseen (#342).
    tables = _ddl_columns(sql)
    assert {t: len(c) for t, c in tables.items()} == {
        "steam_signin_facts": 14, "steam_family_shares": 5, "conn_markers": 9}, tables


_TOP_PLANTS = ("IMPORT FOREIGN SCHEMA alt_remote FROM SERVER alt_server INTO public;",
               "SELECT 1 AS a INTO TEMP alt_plant;")


def test_the_disclosure_check_refuses_a_statement_its_closed_table_of_heads_does_not_read():
    """Holder H3 (M2): the real 427 gives no finding. Each plant, in the
    table step's DO body after `-- DDL END` or at the top level before
    COMMIT, is refused with its line named: a head on no row (IMPORT FOREIGN
    SCHEMA in both places, the column-making forms, SELECT ... INTO TEMP at
    the top level), an EXECUTE that is not format() of one literal with %L
    or whose literal's head is on no row, a /* comment, an E'' string, a
    U&'' string and a double-quoted name each after a known head, and a
    statement after a string that holds --. A plain `CREATE TABLE <name> (`
    body is read by _CREATE, and the fourth table it makes is refused by the
    table-set check."""
    sql, fixture = _read(MIGRATION_427), _fixture()
    assert _ddl_outside(sql) == []
    end = "    -- DDL END\n"
    assert sql.count(end) == 1
    line = sql[:sql.index(end)].count("\n") + 2
    top = "\nCOMMIT;"
    assert sql.count(top) == 1
    top_line = sql[:sql.index(top)].count("\n") + 2
    plants = ("ALTER TABLE conn_markers ADD COLUMN port BIGINT NULL;",
              "alter table conn_markers add port bigint;",
              "CREATE UNLOGGED TABLE alt_plant (a TEXT NOT NULL);",
              "CREATE TEMP TABLE alt_plant (a TEXT NOT NULL);",
              "CREATE TABLE IF NOT EXISTS alt_plant (a TEXT NOT NULL);",
              "CREATE TABLE alt_plant AS SELECT 1 AS a;",
              "CREATE VIEW alt_plant AS SELECT 1 AS a;",
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
              "ALTER DOMAIN alt_domain SET NOT NULL;",
              "IMPORT FOREIGN SCHEMA alt_remote FROM SERVER alt_server INTO public;",
              "EXECUTE format('ALTER TABLE conn_markers ADD port %L', mark);",
              "EXECUTE 'ALTER TABLE conn_markers ' || 'ADD port BIGINT';",
              "EXECUTE format('COMMENT ON TABLE conn_markers IS %s', mark);",
              "EXECUTE format('COMMENT ON TABLE conn_markers IS %I', mark);",
              "PERFORM 1 /* a note */;",
              "RAISE EXCEPTION 'a -- b'; ALTER TABLE conn_markers ADD port BIGINT;",
              "PERFORM E'a';",
              "PERFORM U&'a';",
              'PERFORM "a";')
    grown = [(sql.replace(end, end + "    " + plant + "\n", 1), line, plant) for plant in plants]
    grown += [(sql.replace(top, "\n" + plant + top, 1), top_line, plant) for plant in _TOP_PLANTS]
    for text_, at, plant in grown:
        got = _disclosure_problems(text_, fixture, alt_signals.DISCLOSURE)
        assert any(p.startswith("a statement the closed table of heads does not read:"
                                " line %d: " % at) for p in got), (plant, got)
    fourth = sql.replace(end, end + "    " + "CREATE TABLE alt_plant (\n      a TEXT NOT NULL\n    );" + "\n", 1)
    got = _disclosure_problems(fourth, fixture, alt_signals.DISCLOSURE)
    assert not [p for p in got if p.startswith("a statement the closed table")], got
    assert any(p.startswith("the DDL creates") for p in got), got


def test_the_disclosure_check_fails_on_each_of_its_classes():
    sql, fixture = _read(MIGRATION_427), _fixture()
    sentence = alt_signals.DISCLOSURE
    # A column added to a table and not mapped.
    grown = sql.replace("  conn_class  VARCHAR(8)  NOT NULL DEFAULT 'unknown',\n",
                        "  conn_class  VARCHAR(8)  NOT NULL DEFAULT 'unknown',\n"
                        "      port        INTEGER     NULL,\n", 1)
    assert grown != sql
    assert any("conn_markers.port" in p and "does not map" in p
               for p in _disclosure_problems(grown, fixture, sentence))
    # A column of a type the reader does not know (finding R2-5, M2): named.
    big = sql.replace("  conn_class  VARCHAR(8)  NOT NULL DEFAULT 'unknown',\n",
                      "  conn_class  VARCHAR(8)  NOT NULL DEFAULT 'unknown',\n"
                      "      port        BIGINT      NULL,\n", 1)
    assert big != sql
    assert "a CREATE TABLE line the reader does not know: conn_markers: port        BIGINT      NULL," in \
        _disclosure_problems(big, fixture, sentence)
    # A column called bookkeeping outside the closed list.
    moved = json.loads(json.dumps(fixture))
    moved["categories"]["copy"]["columns"].remove("steam_signin_facts.copy_state")
    moved["bookkeeping"].append("steam_signin_facts.copy_state")
    assert any("closed list" in p for p in _disclosure_problems(sql, moved, sentence))
    # A sentence that no longer names a category, or the deadline.
    for words in ("network block", "%d days after it was last seen" % alt_signals.DEADLINE_DAYS,
                  "delete your account", "may record"):
        assert words in sentence, words
        assert any("lacks" in p for p in _disclosure_problems(sql, fixture, sentence.replace(words, "")))
    # A mapped column the tables do not have.
    stale = json.loads(json.dumps(fixture))
    stale["categories"]["times"]["columns"].append("conn_markers.seen_at")
    assert any("no column of 427" in p for p in _disclosure_problems(sql, stale, sentence))


# -- R6: the sentence on every surface -----------------------------------------

_SECTION = re.compile(r"^## Message (\d+)[^\n]*$", re.M)
_NUMBERED = re.compile(r"^(\d+)_.*\.sql$")


def _faq_message(n):
    parts = _SECTION.split(_read(FAQ_MD))
    found = [parts[i + 1].strip() for i in range(1, len(parts), 2) if int(parts[i]) == n]
    assert len(found) == 1, "docs/FAQ.md has %d '## Message %d' sections" % (len(found), n)
    return found[0]


def _sql_files():
    return {name: _read(os.path.join(SQL_DIR, name)) for name in os.listdir(SQL_DIR)
            if name.endswith(".sql")}


def _newest_carrier(n, files):
    """(file name, body) of the newest numbered migration among `files`
    ({name: text}) that carries a $faqN$ literal. Two files of that number
    carrying one, or one file carrying two, is an error, not a choice; a
    rollback or resume file is not numbered and never counts."""
    tag = "$faq%d$" % n
    carriers = {}
    for name, text in files.items():
        m = _NUMBERED.match(name)
        if m and tag in text:
            carriers.setdefault(int(m.group(1)), []).append(name)
    assert carriers, "no numbered migration carries %s" % tag
    newest = max(carriers)
    assert len(carriers[newest]) == 1, "two migrations numbered %d carry %s: %s" % (
        newest, tag, sorted(carriers[newest]))
    name = carriers[newest][0]
    bodies = re.findall(re.escape(tag) + r"(.*?)" + re.escape(tag), files[name], re.S)
    assert len(bodies) == 1, "%s carries %d %s literals" % (name, len(bodies), tag)
    return name, bodies[0]


def _last_paragraph(body):
    return body.strip().split("\n\n")[-1]


def test_the_sentence_closes_message_1_in_the_faq_and_in_its_newest_carrier():
    """docs/FAQ.md's message 1 and the newest migration carrying it both end
    with the sentence, and the two are the same text; the bot's answer holds
    it. The recording's notice check reads the posted message for the same
    constant, so this is where a dropped sentence is caught."""
    faq = _faq_message(1)
    assert _last_paragraph(faq) == alt_signals.DISCLOSURE
    name, body = _newest_carrier(1, _sql_files())
    assert name == "427_alt_signals.sql", name
    assert _last_paragraph(body) == alt_signals.DISCLOSURE
    assert body == faq
    assert len(faq) <= 2000, len(faq)
    assert alt_signals.DISCLOSURE in _bot_entry("recorded", _lift_bot())["answer"]


def test_the_carrier_rule_can_fail():
    """The newest carrier is the one read, an older one with other text does
    not stand in for it, and an ambiguous newest carrier is refused."""
    old, new = "$faq1$older text$faq1$", "$faq1$" + alt_signals.DISCLOSURE + "$faq1$"
    assert _newest_carrier(1, {"338_a.sql": old, "427_b.sql": new, "rollback_427_b.sql": old}) == (
        "427_b.sql", alt_signals.DISCLOSURE)
    assert _newest_carrier(1, {"338_a.sql": new, "427_b.sql": old})[1] == "older text"
    with pytest.raises(AssertionError, match="two migrations numbered 427"):
        _newest_carrier(1, {"427_a.sql": new, "427_b.sql": new})
    with pytest.raises(AssertionError, match="carries 2"):
        _newest_carrier(1, {"427_b.sql": new + new})
    faq = _faq_message(1)
    assert _last_paragraph(faq + "\n\nA paragraph after it.") != alt_signals.DISCLOSURE
    assert _last_paragraph(faq.replace("delete your account", "close your account")) != alt_signals.DISCLOSURE


# -- the bot's `recorded` entry ----------------------------------------------------

def _lift_bot():
    """The bot's FAQ block, executed alone: the top-level statements from
    `import re as _faq_re` through _faq_find_match. A name the block reads
    from elsewhere in the module (one top-level assignment) is executed
    first. Returns the namespace."""
    src = _read(BOT)
    body = ast.parse(src).body
    start = [i for i, n in enumerate(body) if isinstance(n, ast.Import)
             and any(a.name == "re" and a.asname == "_faq_re" for a in n.names)]
    end = [i for i, n in enumerate(body) if isinstance(n, ast.FunctionDef) and n.name == "_faq_find_match"]
    assert len(start) == 1 and len(end) == 1, (start, end)
    block = compile(ast.Module(body=body[start[0]:end[0] + 1], type_ignores=[]), BOT, "exec")
    ns = {"__name__": "faq_block"}
    for _ in range(8):
        try:
            exec(block, dict(ns))
            break
        except NameError as ex:
            defs = [n for n in body[:start[0]] + body[end[0] + 1:] if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == ex.name for t in n.targets)]
            assert len(defs) == 1, (ex.name, len(defs))
            exec(compile(ast.Module(body=defs, type_ignores=[]), BOT, "exec"), ns)
    exec(block, ns)
    return ns


def _bot_entry(key, ns):
    found = [e for e in ns["FAQ_ENTRIES"] if e["key"] == key]
    assert len(found) == 1, (key, len(found))
    return found[0]


def test_the_recorded_entry_is_last_and_its_short_states_the_deadline():
    ns = _lift_bot()
    entries = ns["FAQ_ENTRIES"]
    assert entries[-1]["key"] == "recorded", [e["key"] for e in entries[-3:]]
    rec = entries[-1]
    assert len(rec["short"]) <= 460, len(rec["short"])
    deadline = "deleted no later than %d days after it was last seen" % alt_signals.DEADLINE_DAYS
    assert deadline in rec["short"] and deadline in rec["answer"]
    assert "delete your account" in rec["short"]
    assert "first FAQ message" in rec["short"]


def test_the_recorded_entry_takes_no_older_entrys_examples_and_answers_its_own():
    """The first regex hit wins, so a last entry cannot take a message an
    older entry's patterns match; it can still take one an older entry
    answers only by the fuzzy pass, which runs after every entry's patterns.
    So every older example is routed whole, with and without the veto, and
    none may land here; and every example of this entry lands here."""
    ns = _lift_bot()
    find = ns["_faq_find_match"]
    entries = ns["FAQ_ENTRIES"]
    rec = entries[-1]
    older = [(e["key"], x) for e in entries[:-1] for x in e.get("examples", [])]
    assert len(older) > 100, len(older)
    taken = [(k, x) for k, x in older if find(x, apply_veto=False) is rec or find(x) is rec]
    assert taken == [], taken
    assert len(rec["examples"]) >= 5
    for x in rec["examples"]:
        assert find(x, apply_veto=False) is rec, x
        assert find(x) is rec, x
    # A question about being banned BY Valve is not a question about what
    # the server records; it stays unanswered here.
    assert find("can i get vac banned for using this mod?") is not rec


# -- /health ---------------------------------------------------------------------

class _DownSession:
    """A session whose server is gone: every statement raises."""

    async def execute(self, *a, **k):
        raise OSError("alt signals: the database is down")

    async def rollback(self):
        pass


def _health_keywords(name):
    with open(main.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    (health,) = [n for n in ast.walk(tree)
                 if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    (tried,) = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    connected = [ast.unparse(k.value) for s in tried.body for k in ast.walk(s)
                 if isinstance(k, ast.keyword) and k.arg == name]
    degraded = [ast.unparse(k.value) for h in tried.handlers for k in ast.walk(h)
                if isinstance(k, ast.keyword) and k.arg == name]
    everywhere = [k for k in ast.walk(tree) if isinstance(k, ast.keyword) and k.arg == name]
    return tree, connected, degraded, len(everywhere)


def test_both_health_arms_carry_the_build_marker_and_the_key_word():
    """alt_signals_build: the module constant, bound once to 1, equal on
    both roles (the release train's marker). alt_signals_key: what the
    loaded key is ('absent', 'refused', or the key id; never the key), from
    the module. Both arms pass both, nothing else in main.py passes either,
    and HealthResponse requires both."""
    tree, connected, degraded, n = _health_keywords("alt_signals_build")
    assert (connected, degraded, n) == (["_ALT_SIGNALS_BUILD"], ["_ALT_SIGNALS_BUILD"], 2)
    (binding,) = [b for b in tree.body if isinstance(b, ast.Assign)
                  and [ast.unparse(t) for t in b.targets] == ["_ALT_SIGNALS_BUILD"]]
    stores = [x for x in ast.walk(tree) if isinstance(x, ast.Name)
              and x.id == "_ALT_SIGNALS_BUILD" and isinstance(x.ctx, ast.Store)]
    assert len(stores) == 1 and ast.unparse(binding.value) == "1"
    _, connected, degraded, n = _health_keywords("alt_signals_key")
    assert (connected, degraded, n) == (["_alt_signals.key_word()"], ["_alt_signals.key_word()"], 2)
    for name, kind in (("alt_signals_build", int), ("alt_signals_key", str)):
        field = schemas.HealthResponse.model_fields.get(name)
        assert field is not None and field.annotation is kind and field.is_required(), (name, field)
    answer = asyncio.run(main.health_check(db=_DownSession())).model_dump()
    assert answer["status"] == "degraded"
    assert answer["alt_signals_build"] == 1
    assert answer["alt_signals_key"] == alt_signals.key_word()
    for name in ("alt_signals_build", "alt_signals_key"):
        partial = dict(answer)
        partial.pop(name)
        with pytest.raises(pydantic.ValidationError):
            schemas.HealthResponse(**partial)


# -- the key's way into the container -------------------------------------------------

def test_the_key_reaches_the_api_container_and_no_other():
    """This project has no env_file: a key in .env reaches the process only
    when compose names it under the service's environment. The api names it
    with an empty default (unset and empty are both 'absent'); the bot never
    reads it and does not get it; env.template carries the line empty."""
    assert alt_signals.KEY_ENV == "SCR_ALT_SIGNAL_KEY"
    compose = _read(COMPOSE)
    api = compose[compose.index("\n  api:\n"):compose.index("\n  bot:\n")]
    rest = compose.replace(api, "")
    line = "      SCR_ALT_SIGNAL_KEY: ${SCR_ALT_SIGNAL_KEY:-}\n"
    assert api.count(line) == 1, "the api service does not name the key exactly once"
    assert "SCR_ALT_SIGNAL_KEY" not in rest
    template = _read(ENV_TEMPLATE)
    assert re.findall(r"^SCR_ALT_SIGNAL_KEY=(.*)$", template, re.M) == [""]


# -- the reader census ------------------------------------------------------------------

_TABLE_WORD = re.compile(r"\b(?:%s)\b" % "|".join(TABLES))
_ORM_CLASSES = frozenset({"SteamSigninFacts", "SteamFamilyShare", "ConnMarker"})

# Where the three tables may be named: the recording, account deletion, the
# retention pass, the read function and its statement, and the ORM classes.
_ALLOWED = {
    ("main.py", "_alt_record"),
    ("main.py", "_alt_delete_account"),
    ("main.py", "_alt_retention_batch"),
    ("main.py", "_alt_retention_left"),
    ("main.py", "alt_relations"),
    ("main.py", "_ALT_RELATION_SQL"),
    ("models.py", "SteamSigninFacts"),
    ("models.py", "SteamFamilyShare"),
    ("models.py", "ConnMarker"),
}


def _docstrings(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _namers(rel, src):
    """{(file, top-level name)} of every top-level definition of `src` whose
    code names one of the three tables (in a string that is not a
    docstring) or one of their ORM classes."""
    tree = ast.parse(src)
    docs = _docstrings(tree)
    # Finding R2-6: a class imported under another name is resolved (its
    # alias is matched as the class), and an import the census cannot
    # resolve (a star import of the models module) is refused by name.
    aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[-1] == "models" \
                and any(a.name == "*" for a in node.names):
            raise AssertionError("%s:%d: a star import of models the reader census cannot resolve"
                                 % (rel, node.lineno))
        if isinstance(node, ast.alias) and node.name.split(".")[-1] in _ORM_CLASSES and node.asname:
            aliases.add(node.asname)
    found = set()
    for top in tree.body:
        if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [top.name]
        elif isinstance(top, (ast.Assign, ast.AnnAssign)):
            targets = top.targets if isinstance(top, ast.Assign) else [top.target]
            names = [ast.unparse(t) for t in targets]
        else:
            names = ["<line %d>" % top.lineno]
        for node in ast.walk(top):
            hit = (isinstance(node, ast.Constant) and isinstance(node.value, str)
                   and id(node) not in docs and _TABLE_WORD.search(node.value)) \
                or (isinstance(node, ast.Constant) and node.value in _ORM_CLASSES) \
                or (isinstance(node, ast.Name) and (node.id in _ORM_CLASSES or node.id in aliases)) \
                or (isinstance(node, ast.Attribute) and node.attr in _ORM_CLASSES) \
                or (isinstance(node, ast.alias) and node.name.split(".")[-1] in _ORM_CLASSES)
            if hit:
                found.update((rel, n) for n in names)
                break
    return found


def _census():
    found = set()
    api = os.path.join(BACKEND, "api")
    files = [(name, os.path.join(api, name)) for name in sorted(os.listdir(api)) if name.endswith(".py")]
    files.append(("discord_bot.py", BOT))
    assert len(files) > 20, len(files)
    for rel, path in files:
        found |= _namers(rel, _read(path))
    return found


def test_only_the_recording_deletion_the_pass_and_the_read_name_the_three_tables():
    assert _census() == _ALLOWED


def test_the_census_sees_a_reader_anywhere_else():
    planted = "def other():\n    return text('SELECT count(*) FROM conn_markers')\n"
    assert _namers("main.py", planted) == {("main.py", "other")}
    assert _namers("main.py", "def other():\n    return select(ConnMarker)\n") == {("main.py", "other")}
    assert _namers("main.py", "def other():\n    '''Reads conn_markers.'''\n    return 1\n") == set()
    assert _namers("main.py", "X = 'DELETE FROM steam_family_shares'\n") == {("main.py", "X")}


@pytest.mark.parametrize("src, want", [
    ("from models import ConnMarker as CM\n\ndef decide():\n    return select(CM)\n",
     {("main.py", "<line 1>"), ("main.py", "decide")}),
    ("def decide():\n    from models import ConnMarker as CM\n    return select(CM)\n",
     {("main.py", "decide")}),
    ("import models as m\n\ndef decide():\n    return select(m.ConnMarker)\n",
     {("main.py", "decide")}),
    ("import api\n\ndef decide():\n    return select(api.models.ConnMarker)\n",
     {("main.py", "decide")}),
    ("import models\n\ndef decide():\n    return select(getattr(models, 'ConnMarker'))\n",
     {("main.py", "decide")}),
], ids=["from-import as", "from-import as inside", "module import as", "attribute chain", "getattr by name"])
def test_the_census_resolves_a_model_imported_under_another_name(src, want):
    """Finding R2-6: one plant per form, each inside a decision function."""
    assert _namers("main.py", src) == want


def test_the_census_refuses_an_import_it_cannot_resolve():
    with pytest.raises(AssertionError, match="star import of models"):
        _namers("main.py", "from models import *\n\ndef decide():\n    return select(ConnMarker)\n")
