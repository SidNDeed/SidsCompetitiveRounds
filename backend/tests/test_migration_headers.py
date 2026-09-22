"""What a migration's HEADER promises, checked against the code that reads it.

Two claims live in these headers that nothing else in the suite could falsify,
and both of them were wrong somewhere in this batch: the deploy order (333 had
none at all, and 336's said the reverse order was survivable when it is not),
and 336's inventory of what reads `bug_reports.kind` (it named four of the
eight readers that existed when it was written; six of those eight are in
this tree and the other two ship with the automatic upload).

Neither needs a database. Both are derived from the api sources rather than
retyped from the headers, so a reader added later moves this test rather than
sitting outside it (#342: a check whose expected value is a copy of the thing
it checks cannot fail).
"""

import ast
import os
import pathlib
import re

import pytest

SQL_DIR = pathlib.Path(__file__).resolve().parents[1] / "sql"
API_DIR = pathlib.Path(__file__).resolve().parents[1] / "api"

# The four files this delta owns. 330 and 337 belong to other lanes in the
# same batch and are deliberately not asserted here: a gate that reaches into
# a neighbouring lane's file fails for reasons its owner has not seen.
OWNED = ("331_animal_title_ladders.sql",
         "332_pc_edition_schedule.sql",
         "333_pc_card_themes.sql",
         "336_bug_reports_kind.sql")

_ORDER_LINE = re.compile(r"^--\s*DEPLOY ORDER:\s*(.+)$", re.MULTILINE)


@pytest.mark.parametrize("filename", OWNED)
def test_every_migration_states_its_deploy_order(filename):
    """WHICH GOES FIRST, in one greppable place, in every file.

    A deploy applies these by hand from a runbook, and the one question the
    person running it has is whether the api may go first. Three of the four
    answered it somewhere in a paragraph and one did not answer it at all;
    'somewhere in a paragraph' is not an answer a reader can rely on finding,
    and a missing one reads as 'either way is fine' -- which was false for two
    of these files.

    The line must NAME an order. Asserting only that the words 'DEPLOY ORDER'
    appear would be satisfied by a heading with nothing under it.
    """
    text = (SQL_DIR / filename).read_text(encoding="utf-8")
    matches = _ORDER_LINE.findall(text)
    assert matches, (
        "%s has no `-- DEPLOY ORDER:` line. Whoever applies it has to infer "
        "from prose whether the api may deploy first, and for 332 and 336 the "
        "wrong inference takes a working box down." % filename)
    stated = " ".join(matches).upper()
    assert ("THIS FILE FIRST" in stated) or ("THE API FIRST" in stated), (
        "%s's deploy-order line does not say which side goes first: %r"
        % (filename, matches))
    # The header is the first comment block, before any statement: a note
    # buried after the BEGIN is not where anyone looks.
    first_statement = text.upper().find("BEGIN;")
    assert first_statement > 0, filename
    assert text.upper().find("DEPLOY ORDER") < first_statement, (
        "%s's deploy-order line sits after BEGIN;, below the header a reader "
        "actually reads" % filename)


# ── 336's reader inventory ─────────────────────────────────────────────────

_USES_KIND = re.compile(
    r"(?:\bbr\.kind\b|\bkind\s*=\s*'(?:report|auto)'|,\s*kind\b"
    r"|\bkind\s+IN\s*\(|\bWHERE\s+kind\b|\bSELECT\s+kind\b)")


_READERS_CACHE = {}


def _functions_that_read_bug_report_kind():
    """Every function whose own source contains SQL over `bug_reports` that
    names `kind`.

    Derived, not listed. The finding this closes was a hand-written inventory
    that named four readers while the file had eight, and a hand-written
    expectation here would rot the same way.

    `shop_items.kind` and `ShopItem.kind` are much commoner in main.py than
    this column, so the predicate requires BOTH `bug_reports` and a `kind`
    used in a SQL position within the same function.

    Sliced from a line list rather than by `ast.get_source_segment`, which
    re-splits the whole file per call: on main.py that is quadratic and cost
    85 seconds a test. Cached, because both tests here ask the same question.

    `auto_logs.py` is named but not required. The automatic post-match log
    upload ships in its own branch and 336 is its precursor as much as it is
    this batch's, so the module is present on one tree and absent on the
    other. Skipping a module that is not there keeps ONE detector serving both
    trees; a module that IS there is always read, so nothing goes unmeasured
    by accident.
    """
    if _READERS_CACHE:
        return dict(_READERS_CACHE)
    for name in ("main.py", "auto_logs.py"):
        path = API_DIR / name
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        lines = src.splitlines()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            end = getattr(node, "end_lineno", None) or node.lineno
            segment = "\n".join(lines[node.lineno - 1:end])
            if "bug_reports" in segment and _USES_KIND.search(segment):
                _READERS_CACHE.setdefault(node.name, name)
    return dict(_READERS_CACHE)


def test_the_336_header_names_every_reader_and_writer_of_kind():
    """The inventory in 336's header is the deploy-order argument.

    It exists so the ordering claim is checkable rather than asserted, and it
    was itself incomplete -- it omitted `recent_bug_report_events`, which is
    polled continuously and whose two branches both name `kind`, i.e. the
    single strongest reason the api cannot deploy first.

    Only one direction is asserted. The header may name MORE than this finds:
    `auto_log_retention_loop` reaches the column through `prune_auto_logs` and
    is listed for the reader's benefit, and a detector that demanded the two
    sets match exactly would fail on that entry for being useful. On this tree
    the header also names the two automatic-upload functions themselves, whose
    module ships in its own branch -- the same one-direction rule covers them.

    The floor is SIX, which is what main.py alone carries. It was eight when
    the upload module sat beside it, and eight is still what the two together
    produce, so the floor holds on both trees and a detector that went vacuous
    still reds on either.
    """
    header = (SQL_DIR / "336_bug_reports_kind.sql").read_text(encoding="utf-8")
    header = header[:header.upper().find("BEGIN;")]
    readers = _functions_that_read_bug_report_kind()
    assert len(readers) >= 6, (
        "the detector found only %d function(s) touching bug_reports.kind "
        "(%r). Either the readers were removed -- in which case 336's deploy "
        "order can be relaxed deliberately -- or this predicate stopped "
        "matching, which would make the assertion below vacuous."
        % (len(readers), sorted(readers)))

    missing = sorted(fn for fn in readers if fn not in header)
    assert not missing, (
        "336's header inventory does not name %r, and that inventory is the "
        "whole argument for applying it before the api. A reader it does not "
        "list is a path nobody checked before deciding the order." % missing)


def test_the_336_inventory_test_can_actually_fail():
    """The negative control for the test above.

    Its assertion is `every derived name appears in the header text`, and a
    header is long: a name could match by accident, or the detector could go
    silently empty. So a name that is NOT a reader is confirmed absent, and a
    deliberately corrupted header is confirmed to fail the same comparison.
    """
    header = (SQL_DIR / "336_bug_reports_kind.sql").read_text(encoding="utf-8")
    header = header[:header.upper().find("BEGIN;")]
    assert "submit_team_match" not in header, (
        "the header happens to contain an unrelated function name, so 'the "
        "name appears in the header' is weaker than it looks")

    readers = _functions_that_read_bug_report_kind()
    corrupted = header.replace("recent_bug_report_events", "xxx")
    assert [fn for fn in readers if fn not in corrupted], (
        "removing a reader from the header text did not make the comparison "
        "fail, so the comparison proves nothing")


# ── a default on a response model, read as a deploy-order permission ───────

def _survives_without_the_column(text):
    """Sentences claiming a box without migration 336 still serves a surface.

    The proxy is narrow and named as one: a sentence that mentions 336 and a
    surface still working. What it stops is the specific inversion this
    comment made -- a RESPONSE-MODEL default read as a DATABASE guarantee.
    """
    out = []
    for sentence in [s for s in re.split(r"(?<=\.)\s+", " ".join(text.split()))
                     if s]:
        low = sentence.lower()
        if "336" not in low:
            continue
        if not re.search(r"\bstill (serves|works|renders|answers)", low):
            continue
        out.append(sentence)
    return out


def _schema_kind_comment():
    """The contiguous `#` block directly above `kind: str = "report"` in
    schemas.py, read out of the source.

    The anchor is a FIELD DECLARATION, which is a weaker identity than the
    equivalent helper in the auto-log suite gets: that one anchors on
    `_supervised("auto_log_retention"`, a string that names its site and
    nothing else. This shape would be satisfied by ANY defaulted `kind`
    field, so it asserts there is exactly one rather than taking the first. A
    second one declared above `BugReportSummary` would otherwise hand the
    caller a different comment block, which carries no offending sentence, so
    the test would pass while policing something other than the comment it
    names -- a check bound to a correlate of its subject rather than to the
    subject (#732). Failing loudly is the right direction here: a human
    decides which field the rule is about.
    """
    lines = (API_DIR / "schemas.py").read_text(encoding="utf-8").splitlines()
    hits = [i for i, ln in enumerate(lines)
            if ln.strip().startswith("kind: str = ")]
    assert len(hits) == 1, (
        "schemas.py declares %d defaulted `kind` fields, at lines %r. This "
        "helper reads the comment above ONE of them and the test below holds "
        "that comment to migration 336's deploy order; with more than one it "
        "would read whichever comes first and certify the rest by silence. "
        "Name the field this rule is about." % (len(hits), [i + 1 for i in hits]))
    anchor = hits[0]
    block = []
    i = anchor
    while i > 0:
        i -= 1
        stripped = lines[i].strip()
        if stripped.startswith("#"):
            block.append(stripped.lstrip("#").strip())
        else:
            break
    return " ".join(reversed(block))


def test_the_defaulted_kind_field_is_not_read_as_a_deploy_order_permission():
    """A DEFAULT ON THE RESPONSE MODEL IS NOT A DEFAULT ON THE QUERY.

    `BugReportSummary.kind` is appended last and defaulted, which is right and
    buys one real thing: an older admin client ignores the extra key. The
    comment went one step further and said a box whose 336 has not run still
    serves the list. It does not. `list_bug_reports` NAMES `kind` in its raw
    SELECT, so without the column the statement fails and the list does not
    render; the model default has nothing to default, because no row comes
    back at all.

    The direction of the error is what makes it worth a test: it reads as
    permission to deploy the api before the migration, which is the one order
    336's header calls a broken deployment.

    Derived, not retyped: the SELECT is read out of main.py, so if the list
    ever stops naming the column this test says so rather than going on
    forbidding a sentence that would by then be true.

    THE DETECTOR DOES NOT MODEL RETRACTION, and this is stated rather than
    worked around: it reads the whole comment block, so a sentence quoting the
    wrong claim in order to withdraw it is indistinguishable from one making
    it (#666). The comment therefore withdraws the old claim without restating
    it in its own words, and says so where it does it. The alternative -- a
    detector that tries to tell "X" from "it is not X" -- fails in the
    direction of certifying a comment that says both.
    """
    source = (API_DIR / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    listing = next((n for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == "list_bug_reports"), None)
    assert listing is not None, "list_bug_reports was renamed or moved"
    body = " ".join((ast.get_source_segment(source, listing) or "").split())
    assert re.search(r"SELECT\b[^;]{0,600}?\bkind\b[^;]{0,40}?FROM bug_reports",
                     body), (
        "list_bug_reports no longer names `kind` in a SELECT over "
        "bug_reports. The comment this test polices is about what happens "
        "when the column is absent, so if the query stopped reading it, "
        "re-decide that sentence rather than leaving this test forbidding "
        "something that would by then be true.")

    offenders = _survives_without_the_column(_schema_kind_comment())
    assert not offenders, (
        "the comment on the defaulted `kind` field says a box without "
        "migration 336 still serves the list. It does not -- the list's own "
        "SELECT names the column -- and the sentence reads as permission to "
        "deploy the api first, which 336's header calls a broken "
        "deployment:\n  %s" % "\n  ".join(offenders))

    # Two-sided, same style as the rest of this module.
    was = "A box whose 336 has not run still serves the list."
    assert _survives_without_the_column(was) == [was], (
        "the detector no longer flags the sentence this test exists for")
    now = ("The default buys nothing against a database without the column, "
           "because 336's list names it in raw SQL.")
    assert not _survives_without_the_column(now), (
        "the detector flags the sentence that replaced it, so it would force "
        "the comment to drop the subject rather than state it correctly")


# ── "it runs unconditionally", said about statements that do not ───────────

_GUARD_BLOCK = re.compile(r"DO \$(\w*)\$(.*?)END \$\1\$;", re.S)
_GUARDABLE_DDL = ("CREATE INDEX", "ALTER TABLE")


def _catalog_guarded_ddl(sql):
    """The DDL a file issues only after asking the catalog whether it has to.

    The shape read for is a `DO` block whose body holds both an
    `IF NOT EXISTS (SELECT ...)` probe and a DDL keyword. `IF NOT EXISTS` on
    the statement itself is deliberately NOT counted as a guard: that spelling
    takes the statement's lock BEFORE it evaluates the test, which is the
    whole reason these blocks exist.
    """
    guarded = set()
    for _tag, body in _GUARD_BLOCK.findall(sql):
        if not re.search(r"IF NOT EXISTS\s*\(\s*SELECT", body):
            continue
        guarded.update(keyword for keyword in _GUARDABLE_DDL if keyword in body)
    return guarded


# WHAT A RE-RUN ISSUES -- PARSED OUT OF THE FILE, NOT LISTED HERE.
#
# This was a tuple of three DDL verbs, then a tuple of six kinds of statement,
# and both spellings carried the same defect one width apart: the arm's reach
# was a property of the TUPLE, while the comment above it described it as a
# property of the FILES ("the list names the statement-level work these files
# actually issue"). It did not. Outside every `DO` block 331 and 332 each
# issue a `CREATE TEMP TABLE`, which no version of the list named -- so 332's
# disclosure sentence enumerated two unguarded statements in a file that
# issues three, and nothing in this module could disagree with it.
#
# A list is not repaired by adding the verb that was missed; the next file
# brings the next verb, and the failure direction is the silent one -- an
# unnamed statement does not red anything, it simply stops existing as far as
# the arm is concerned. So the census is DERIVED: the SQL is walked once,
# every top-level statement is found, its leading run of keywords is its kind,
# and every kind is then either work this arm counts or a kind named in
# `_NOT_WORK_A_RERUN_DOES` with the reason it is not. There is no third
# category and nothing falls through, so a verb nobody anticipated lands in
# the census and has to be disclosed.
#
# AND THE WALK DOES NOT STOP AT THE `DO` KEYWORD. A `DO` body can issue work
# of its own outside any `IF`, which 336's post-check does; the census
# descends into every dollar-quoted body and classifies the statements inside
# it, so what reaches `_NOT_WORK_A_RERUN_DOES["DO"]` is only a `DO` whose body
# issues nothing this arm counts.
#
# WHAT THE STATEMENT WRITES IS A DIFFERENT QUESTION AND THIS ARM DOES NOT ASK
# IT. A statement can be issued every time and still write nothing -- 332's
# `UPDATE` is gated by its own WHERE and matches no row on a re-run. That is
# the file's to disclose, in the sentence this arm forces it to write; the arm
# only establishes that the statement is not guarded away.

_DOLLAR_TAG = re.compile(r"\$(\w*)\$")


def _top_level_statements(sql):
    """Every statement the file issues at the top level, in order.

    Splitting on `;` is not enough, and the shortcut fails on these files
    rather than in principle: 336's `COMMENT ON COLUMN` carries a `;` inside
    its string literal, and every `DO` block carries several inside its
    dollar-quoted body. So the text is walked once, consuming line comments,
    block comments, single-quoted strings (`''` escapes included) and
    dollar-quoted bodies WHOLE, and only a `;` reached outside all of them
    ends a statement.

    Comments are replaced by a space rather than kept, so a header that
    DISCUSSES `CREATE INDEX` cannot be read as issuing one.
    """
    out, buf, i, depth, n = [], [], 0, 0, len(sql)
    while i < n:
        ch, two = sql[i], sql[i:i + 2]
        if two == "--":
            j = sql.find("\n", i)
            i = n if j < 0 else j
            buf.append(" ")
            continue
        if two == "/*":
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
            buf.append(" ")
            continue
        if ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if sql[j:j + 2] == "''":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            buf.append(sql[i:j])
            i = j
            continue
        if ch == "$":
            tag = _DOLLAR_TAG.match(sql, i)
            if tag:
                close = sql.find(tag.group(0), tag.end())
                j = n if close < 0 else close + len(tag.group(0))
                buf.append(sql[i:j])
                i = j
                continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == ";" and depth == 0:
            out.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    out.append("".join(buf))
    return [statement.strip() for statement in out if statement.strip()]


_LEADING_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _statement_kind(statement):
    """The run of SQL keywords a statement opens with.

    These files write keywords in upper case and identifiers in lower, which
    is what this reads: leading words are taken while they are upper case and
    the first that is not ends the kind. `CREATE TEMP TABLE _m332_state ...`
    is `CREATE TEMP TABLE`; `CREATE TABLE IF NOT EXISTS title_ladders (` is
    `CREATE TABLE IF NOT EXISTS`; `UPDATE pc_editions` is `UPDATE`.

    It returns "" when a statement does not open that way, and the caller
    REDS on that rather than skipping it -- a statement whose kind cannot be
    derived is exactly the statement that would otherwise go uncounted, which
    is the defect this whole census replaces.
    """
    words = []
    for token in statement.split():
        word = _LEADING_WORD.match(token)
        if not word or not word.group(0).isupper() or len(word.group(0)) < 2:
            break
        words.append(word.group(0))
        if word.end() != len(token):
            break
    return " ".join(words)


# A `DO` IS NOT AUTOMATICALLY A GUARD, AND THE BODY IS WHAT SAYS WHICH IT IS.
#
# The exemption below used to excuse every `DO` outright, on the reading that
# a `DO` in these files is a catalog guard and what is inside one is read by
# `_catalog_guarded_ddl`. 336's post-check is a `DO` and is not a guard: its
# body issues `DROP TABLE IF EXISTS`, `CREATE TEMP TABLE` and `ALTER TABLE`
# unconditionally, and every one of them was invisible to this census while
# the `DO` around them carried a blanket exemption -- so 336's header could
# call `COMMENT ON COLUMN` the file's only unguarded schema statement and
# nothing here could disagree.
#
# So the body is descended into. A statement inside a `DO` counts exactly when
# it runs unconditionally -- not nested in an `IF`/`LOOP` -- and is not a kind
# `_NOT_WORK_A_DO_BODY_DOES` excuses. DDL inside `IF NOT EXISTS (SELECT ...)
# THEN` is the guarded case and stays this arm's non-subject, which is what
# `_catalog_guarded_ddl` reads.
#
# WHICH DIRECTION THE UNHANDLED CASES FAIL IN. A fragment whose operative verb
# the derivation cannot read is REPORTED (`_unnameable_statements`), not
# skipped. A statement in an exception handler is counted as unconditional,
# because the handler's guard is an error rather than a catalog predicate and
# counting it is the stricter reading. Both of those can only ask a header for
# more, never less.
_BODY_BLOCK = ("BEGIN", "DECLARE", "END")
_BODY_CONDITION_OPENERS = ("IF", "WHILE", "FOR")
_BODY_CONDITION_CONTINUERS = ("ELSIF", "WHEN")
_BODY_CONDITION_CLOSERS = ("IF", "LOOP", "CASE")

_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(?:\[[^\]]*\])?\s*:=")


def _bare_words(fragment):
    """(word, offset) for every word at parenthesis depth 0 in a fragment.

    Strings, dollar-quoted bodies, comments and everything inside parentheses
    are skipped. The subject is the control scaffolding a PL/pgSQL fragment
    opens with, and a `SELECT` inside an `IF NOT EXISTS (...)` probe belongs
    to the condition rather than being a statement of its own.
    """
    out, i, depth, n = [], 0, 0, len(fragment)
    while i < n:
        ch, two = fragment[i], fragment[i:i + 2]
        if two == "--":
            j = fragment.find("\n", i)
            i = n if j < 0 else j
            continue
        if two == "/*":
            j = fragment.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if ch == "'":
            j = i + 1
            while j < n:
                if fragment[j] == "'":
                    if fragment[j:j + 2] == "''":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            i = j
            continue
        if ch == "$":
            tag = _DOLLAR_TAG.match(fragment, i)
            if tag:
                close = fragment.find(tag.group(0), tag.end())
                i = n if close < 0 else close + len(tag.group(0))
                continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        word = _LEADING_WORD.match(fragment, i)
        if word:
            if depth == 0:
                out.append((word.group(0), i))
            i = word.end()
            continue
        i += 1
    return out


def _executed_sql(text):
    """The literal a PL/pgSQL `EXECUTE` runs, or "" when it has none.

    `EXECUTE 'DROP TABLE IF EXISTS pg_temp.m336_expected_probe'` issues a
    `DROP`, and a census that recorded `EXECUTE` would be counting the
    mechanism instead of the work. The first string literal in the statement
    is the statement being run -- including through `format(...)`, whose
    template is that literal -- and a dollar-quoted body reads the same way.
    An `EXECUTE` built entirely out of variables has no literal, returns ""
    and is reported as unnameable rather than passed over.
    """
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "'":
            j = i + 1
            chunk = []
            while j < n:
                if text[j] == "'":
                    if text[j:j + 2] == "''":
                        chunk.append("'")
                        j += 2
                        continue
                    break
                chunk.append(text[j])
                j += 1
            return "".join(chunk)
        if ch == "$":
            tag = _DOLLAR_TAG.match(text, i)
            if tag:
                close = text.find(tag.group(0), tag.end())
                return text[tag.end():close if close >= 0 else n]
        i += 1
    return ""


def _do_body(statement):
    """The dollar-quoted body of a `DO` statement, or "" if there is none."""
    start = statement.find("$")
    if start < 0:
        return ""
    tag = _DOLLAR_TAG.match(statement, start)
    if not tag:
        return ""
    close = statement.rfind(tag.group(0))
    if close <= tag.end():
        return ""
    return statement[tag.end():close]


def _do_body_statements(statement):
    """Every operative statement inside a `DO` body, with its kind.

    Returns `(kind, conditional, text)` triples in order. `conditional` is
    True when the statement sits inside an `IF`/`LOOP` -- the guarded case --
    and False when the body issues it every time it runs.

    Declarations are not statements and contribute nothing; the `DECLARE`
    section is the run from that word to the `BEGIN` that ends it.
    """
    out = []
    depth, in_declare = 0, False
    for fragment in _top_level_statements(_do_body(statement)):
        words = _bare_words(fragment)
        i = 0
        while i < len(words):
            word, offset = words[i]
            nxt = words[i + 1][0] if i + 1 < len(words) else ""
            if not word.isupper():
                break
            if word == "DECLARE":
                in_declare, i = True, i + 1
                continue
            if word == "BEGIN":
                in_declare, i = False, i + 1
                continue
            if word == "END":
                if nxt in _BODY_CONDITION_CLOSERS:
                    depth = max(0, depth - 1)
                    i += 2
                    continue
                i += 1
                continue
            if word in ("ELSE", "EXCEPTION"):
                i += 1
                continue
            if word == "LOOP":
                depth += 1
                i += 1
                continue
            if (word in _BODY_CONDITION_OPENERS
                    or word in _BODY_CONDITION_CONTINUERS):
                j = i + 1
                while j < len(words) and words[j][0] not in ("THEN", "LOOP"):
                    j += 1
                if j >= len(words):
                    i = len(words)
                    continue
                if word in _BODY_CONDITION_OPENERS:
                    depth += 1
                i = j + 1
                continue
            break
        if in_declare or i >= len(words):
            continue
        text = fragment[words[i][1]:].strip()
        if _ASSIGNMENT.match(text):
            kind = "ASSIGNMENT"
        else:
            kind = _statement_kind(text)
            if kind == "EXECUTE":
                kind = _statement_kind(_executed_sql(text[len("EXECUTE"):]))
        out.append((kind, depth > 0, " ".join(text.split())))
    return out


# THE TWO PLACES A KIND CAN BE EXEMPT, AND EACH ONE HAS TO SAY WHY.
#
# Everything the census finds is either work a file must disclose or a kind
# named here. Nothing is invisible: adding a key is a visible act with a
# reason attached, where narrowing a keyword list was an invisible one.
_NOT_WORK_A_RERUN_DOES = {
    "BEGIN": "transaction control -- it touches no relation of its own",
    "COMMIT": "transaction control",
    "ROLLBACK": "transaction control",
    "SET": "a session setting, scoped to this transaction",
    "SET LOCAL": "a session setting, scoped to this transaction",
    "SET SESSION": "a session setting, scoped to this connection",
    "DO": "a `DO` whose body issues nothing this census counts -- the guard "
          "blocks themselves, read by `_catalog_guarded_ddl`. A `DO` whose "
          "body DOES issue something contributes THAT statement's kind and "
          "never reaches this key",
}

# The body map is keyed on the leading VERB rather than the whole kind: a
# PL/pgSQL read is spelled `SELECT count(*) INTO v` as often as
# `SELECT COUNT(*) INTO v`, and the kind derivation keeps whatever case the
# function name happens to carry. Four keys, each about a statement that
# touches no relation.
_NOT_WORK_A_DO_BODY_DOES = {
    "SELECT": "a read -- inside a PL/pgSQL body `SELECT ... INTO` assigns to "
              "variables; the SQL spelling that creates a relation is not "
              "accepted there",
    "RAISE": "diagnostic output -- NOTICE or EXCEPTION, it writes no relation",
    "RETURN": "control flow -- it leaves the block",
    "ASSIGNMENT": "a variable assignment; the target is a PL/pgSQL variable",
}


def _statement_kinds(statement):
    """The kinds one top-level statement contributes to the census.

    One kind for an ordinary statement. For a `DO`, the kinds its body issues
    unconditionally and that `_NOT_WORK_A_DO_BODY_DOES` does not excuse --
    and `DO` itself only when there are none, which is the guard-block case.
    """
    kind = _statement_kind(statement)
    if kind != "DO":
        return [kind]
    work = [body_kind for body_kind, conditional, _text
            in _do_body_statements(statement)
            if not conditional
            and body_kind.split(" ")[0] not in _NOT_WORK_A_DO_BODY_DOES]
    return work or ["DO"]


def _statement_census(sql):
    """Every kind of statement the file issues at the top level, in order.

    Derived from the text. Duplicates collapse -- the arm's subject is which
    KINDS of work a re-run issues, not how many times each is issued.
    """
    kinds = []
    for statement in _top_level_statements(sql):
        for kind in _statement_kinds(statement):
            if kind and kind not in kinds:
                kinds.append(kind)
    return kinds


def _unnameable_statements(sql):
    """Statements whose kind the derivation could not read.

    Zero is the expected answer and the assertion that reads it is what keeps
    the census from going quietly blind: a statement written with a lower-case
    verb would otherwise be counted as nothing at all. Statements inside a
    `DO` body are asked the same question, guarded or not -- an unreadable
    one there was exactly the blind spot the blanket `DO` exemption had.
    """
    out = []
    for statement in _top_level_statements(sql):
        if not _statement_kind(statement):
            out.append(" ".join(statement.split())[:80])
            continue
        if _statement_kind(statement) != "DO":
            continue
        out.extend(text[:80] for kind, _conditional, text
                   in _do_body_statements(statement) if not kind)
    return out


def _unguarded_statement_work(sql):
    """The census, minus the kinds `_NOT_WORK_A_RERUN_DOES` excuses.

    What is left is the work every re-run of the file really does issue --
    which is what a header sentence claiming "unconditional" is making its
    claim about.
    """
    return {kind for kind in _statement_census(sql)
            if kind not in _NOT_WORK_A_RERUN_DOES}


def _comment_blocks(sql):
    """The file's `--` comment text, one entry per contiguous run of them.

    A run ends at the first line that is not a comment, so a header and the
    paragraph beside a statement three hundred lines down are different
    entries. Backticks are dropped because the headers quote statement kinds
    as `` `UPDATE` `` and the census spells them bare; whitespace is
    collapsed, so a kind spanning a line break still reads.
    """
    out, current = [], []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            current.append(stripped[2:].strip())
        else:
            if current:
                out.append(" ".join(current))
            current = []
    if current:
        out.append(" ".join(current))
    return [re.sub(r"\s+", " ", block.replace("`", ""))
            for block in out if block.strip()]


def _disclosure_prose(sql):
    """The comment blocks that carry an unconditional-work claim, joined.

    WHY THE REGION IS NARROWED. Asked of the whole file, "does the prose name
    this kind" passes for the wrong reason: 331 mentions `UPDATE` in three
    separate comment blocks and `CREATE TABLE IF NOT EXISTS` in two, only one
    of which is the disclosure, so the check read true independently of
    whether a disclosure existed at all.

    WHY KEYED ON THAT WORD, given that a vocabulary-keyed EXEMPTION is the
    defect finding A3 was about. This is a selector, not an exemption, and it
    fails in the opposite direction: a file with no block carrying the word
    gets an EMPTY region and every kind it issues is reported undisclosed.
    Stricter, never blinder -- and the omission arm separately requires the
    word to be there at all, so the two cannot disagree silently.
    """
    return " ".join(block for block in _comment_blocks(sql)
                    if "unconditional" in block.lower())


def _undisclosed_statement_work(sql):
    """Kinds the file issues outside its guards that its disclosure omits.

    Word-boundary, not substring. `UPDATE` inside `updated` is not a
    disclosure of an `UPDATE`, and `INSERT INTO` inside `INSERT INTOs` is the
    plural this pass wrote into 331 and only noticed because the boundary
    rejected it.
    """
    prose = _disclosure_prose(sql).upper()
    return sorted(kind for kind in _unguarded_statement_work(sql)
                  if not re.search(r"\b%s\b" % re.escape(kind), prose))


def _sentences(sql):
    """A file's comment prose, split on a full stop followed by whitespace.

    Not a sentence tokeniser and not trying to be one. A split in the wrong
    place can only make the caller STRICTER, never blinder: a fragment that
    kept "unconditional" and lost the clause naming the exception is reported,
    and the answer to that is to write the sentence plainly rather than to
    loosen this.
    """
    stripped = (line.strip() for line in sql.splitlines())
    prose = " ".join(line[2:].strip() for line in stripped
                     if line.startswith("--") and line[2:].strip())
    return [sentence for sentence in re.split(r"(?<=\.)\s+", prose) if sentence]


def _blanket_unconditional_claims(sql):
    """Sentences containing `unconditional` and not containing `guard`.

    The second half is the proxy for "and does not name the exception"; the
    test below says why a proxy is what this can be.
    """
    return [sentence for sentence in _sentences(sql)
            if "unconditional" in sentence.lower()
            and "guard" not in sentence.lower()]


def _states_unconditional_work(sql):
    """Sentences that tell the reader something here runs every time.

    The detector for the OTHER direction. A file that issues DDL outside its
    guards and says nothing about it is not accurate-and-quiet: it reads as a
    file where everything is guarded, which is the inference the guards
    themselves invite once some statements have them.
    """
    return [sentence for sentence in _sentences(sql)
            if "unconditional" in sentence.lower()]


def test_no_header_promises_an_unconditional_rerun_of_a_statement_it_guards():
    """A HEADER MAY NOT SETTLE FOR THE WHOLE FILE WHAT THE FILE SETTLES
    STATEMENT BY STATEMENT.

    331 guards its `CREATE INDEX` on the catalog because `IF NOT EXISTS` takes
    SHARE before it looks for the name -- re-applying the file under an
    ordinary writer aborted on the live cluster. Thirty lines above that
    guard, the same file still said schema statements run unconditionally
    because re-establishing correct schema is a genuine no-op: a claim about
    what a statement WRITES, left standing over a statement that had just been
    guarded for what it LOCKS.

    That sentence is the one a later editor reads before adding the next
    `CREATE INDEX` to the file, which is why it has to carry its own exception
    (#432/#459).

    THE RULE IS STATED AS NARROWLY AS IT IS IMPLEMENTED: a sentence containing
    `unconditional` must also contain `guard`. That is a text proxy and it
    cannot tell whether the exception named is the RIGHT one. What it stops is
    the BLANKET form -- a claim settled for a whole class in a file that
    settles it per statement -- which is the shape the defect had.

    AND IT HAS A SECOND SIDE, because the first one alone is satisfied by
    silence. Deleting every `unconditional` sentence from 331 leaves no
    offender and passes, while the three `CREATE TABLE IF NOT EXISTS`
    statements outside its guards still run on every re-application. A reader
    of a file that guards SOME of its DDL and says nothing about the rest
    concludes the rest is guarded too -- the same wrong conclusion the blanket
    sentence produced, reached from the other direction. So a file that issues
    DDL at statement level AND guards DDL on the catalog has to say which is
    which: over-claim is one arm, omission is the other.
    """
    sql = {name: (SQL_DIR / name).read_text(encoding="utf-8") for name in OWNED}
    guarded = {name: _catalog_guarded_ddl(text) for name, text in sql.items()}
    assert any(guarded.values()), (
        "no file in this delta guards DDL on the catalog any more, so this "
        "test is watching for a contradiction that can no longer arise: %r"
        % (guarded,))

    offenders = [(name, sorted(guarded[name]), sentence)
                 for name in sorted(sql)
                 if guarded[name]
                 for sentence in _blanket_unconditional_claims(sql[name])]
    assert not offenders, (
        "a file that guards DDL on the catalog still tells its reader that "
        "its schema runs unconditionally, without saying in that sentence "
        "what is excepted:\n%s"
        % "\n".join("  %s (guards %s): %s" % (name, ", ".join(ddl), sentence)
                    for name, ddl, sentence in offenders))

    # ── The omission arm ───────────────────────────────────────────────────
    # A file that guards some DDL on the catalog and issues other work at
    # statement level has to say so. A file that guards nothing (333) raises
    # no contradiction to state and is not asked to.
    #
    # WHICH FILES ARE EXEMPT IS MEASURED BELOW, NOT ASSERTED HERE. This
    # comment used to read "a file whose every statement is guarded (332, 336)
    # has no unconditional work to name", which was a claim about those two
    # files that neither of them meets: outside every DO block 336 issues
    # COMMENT ON and 332 issues COMMENT ON and UPDATE. They were quiet in this
    # arm because it matched a fixed list of keywords that did not name theirs
    # -- a property of the list, written down as a property of the files, in
    # the same delta as 336's own header calling its COMMENT ON "Left
    # unguarded deliberately". Widening the list closed the two files it
    # named and left the next verb to be missed the same way: `CREATE TEMP
    # TABLE`, which 331 and 332 both issue outside every guard, was invisible
    # to every version of it. The census is parsed out of the SQL now, so
    # which files this arm reaches is a reading of the files.
    silent = [(name, sorted(guarded[name]), sorted(_unguarded_statement_work(sql[name])))
              for name in sorted(sql)
              if guarded[name] and _unguarded_statement_work(sql[name])
              and not _states_unconditional_work(sql[name])]
    assert not silent, (
        "a file guards some of its DDL on the catalog and issues the rest at "
        "statement level, and its prose says nothing about the difference. A "
        "reader who has seen the guards concludes the whole file is guarded:"
        "\n%s"
        % "\n".join("  %s guards %s, and runs %s every time, unmentioned"
                    % (name, ", ".join(ddl), ", ".join(plain))
                    for name, ddl, plain in silent))
    assert any(guarded[name] and _unguarded_statement_work(sql[name]) for name in sql), (
        "no file in this delta both guards DDL and issues DDL outside a "
        "guard, so the arm above is watching for a contradiction that can no "
        "longer arise: %r"
        % {name: sorted(_unguarded_statement_work(sql[name])) for name in sorted(sql)})

    # NO FILE IS EXEMPT HERE BECAUSE THE CENSUS FAILED TO LOOK. Every file
    # that guards DDL on the catalog also issues countable work at statement
    # level, so each of them reaches the assertion above on its own merits and
    # each of them discloses. Excusing one of their kinds in
    # `_NOT_WORK_A_RERUN_DOES` drops that file out of the arm and reds this
    # line -- which is the point: its silence would otherwise become invisible
    # again, and its disclosure sentence decoration.
    #
    # AND EVERY STATEMENT HAS TO BE READABLE AS SOME KIND. A census that
    # returned "" for a statement would count it as nothing, which is the
    # failure the keyword list had; this says so out loud instead.
    unnameable = {name: _unnameable_statements(sql[name])
                  for name in sorted(sql) if _unnameable_statements(sql[name])}
    assert not unnameable, (
        "the census could not read a kind off these top-level statements, so "
        "each of them counts as nothing at all and no disclosure can be "
        "required of it. Write the opening keywords in upper case, or teach "
        "`_statement_kind` the spelling: %r" % (unnameable,))

    unreached = sorted(name for name in sql
                       if guarded[name] and not _unguarded_statement_work(sql[name]))
    assert not unreached, (
        "%r guard DDL on the catalog and the census counts NO statement-level "
        "work in them, so the arm is silent about them for a reason no reader "
        "of it can check. The lever is `_NOT_WORK_A_RERUN_DOES`, not the "
        "file's prose: every kind a file issues is either counted here or "
        "excused there, and a file reaching this line has had every one of "
        "its kinds excused. What each issues, and how each kind was "
        "classified: %r"
        % (unreached,
           {name: [(kind, _NOT_WORK_A_RERUN_DOES.get(kind, "COUNTED AS WORK"))
                   for kind in _statement_census(sql[name])]
            for name in unreached}))

    # ── Both detectors, negatively controlled ──────────────────────────────
    # Each one has to fire on the text it was written for, or "no offenders"
    # means only that nothing was being read; and each has to stay quiet on
    # the text that satisfies it, or it would force a header to drop the
    # subject rather than get it right.
    restored = ("Schema statements run unconditionally (re-establishing "
                "correct schema is a genuine no-op).")
    qualified = "The CREATE TABLEs run unconditionally; the index is guarded."
    assert _blanket_unconditional_claims("-- " + restored) == [restored], (
        "the detector no longer flags the sentence this test exists for, so "
        "its silence over the real files carries no information")
    assert not _blanket_unconditional_claims("-- " + qualified), (
        "the detector flags a sentence that DOES name its exception, so it "
        "would force a header to drop the claim rather than qualify it")
    assert _states_unconditional_work("-- " + qualified) == [qualified], (
        "the omission detector does not recognise a correct statement of "
        "unconditional work, so it would fire on a header that is right")
    assert not _states_unconditional_work(
        "-- Everything here is guarded on the catalog and re-runs cleanly."), (
        "the omission detector reports a claim in a header that makes none, "
        "so a file that says nothing about its unguarded DDL would satisfy "
        "the arm and the arm would never fire")

    # The same, against the real file rather than a fragment: strip 331's
    # claim and the ARM has to fire on 331. A fragment control proves the
    # detector; this rehearses the arm itself -- its whole three-part
    # condition -- over a file map in which 331's claim is gone, and requires
    # 331 to come back named.
    #
    # 331 AND NOT ONE OF THE OTHER TWO, for a reason that stood here as "331
    # is the one file carrying both kinds of statement" and stopped being
    # true when the arm's reach widened: 332 and 336 both guard DDL on the
    # catalog and both issue statement-level work now, so that sentence no
    # longer picks 331 out. What still does is that 331 is the richest case
    # -- five kinds of work standing behind one claim, counted by the census
    # rather than by me -- and it is the file whose header the over-claim arm
    # above was written against.
    #
    # WHAT THIS ADDS over the vacuity assertion above, stated plainly because
    # the two overlap: that one catches the arm going blind to every file,
    # and would catch most ways of breaking `_unguarded_statement_work`
    # first. This one catches the narrower case that only a strip-based
    # rehearsal can have -- the strip destroying the arm's OWN inputs, so
    # that the rehearsal stops proving anything while still reading true. A
    # check written as `not _states_unconditional_work(stripped)` would pass
    # over that, because removing every line carrying a word leaves no line
    # carrying it however much else went with them (#342 -- a filter that
    # discards the line it measures). So the strip is measured, and then the
    # arm is asked who it NAMES.
    #
    # MEASURED, BECAUSE THE SENTENCE THAT USED TO STAND HERE WAS WRONG. It
    # said: put the word on 331's `CREATE TABLE` lines and the strip removes
    # the statements along with the claim, leaving the arm no unguarded DDL
    # to object to. That held while the arm matched three DDL verbs. 331 also
    # issues `CREATE TEMP TABLE`, `COMMENT ON TABLE`, `INSERT INTO` and
    # `UPDATE` outside its guards, so those three lines can go and the arm
    # still names 331 -- the mutation control for this exact sentence
    # SURVIVED once the reach widened, and the parsed census does not narrow
    # it back. What follows compares the arm's inputs across the strip
    # instead, which does not depend on how many kinds of work the file
    # happens to carry.
    name = "331_animal_title_ladders.sql"
    stripped = "\n".join(line for line in sql[name].splitlines()
                         if "unconditional" not in line.lower())
    assert (_unguarded_statement_work(stripped)
            == _unguarded_statement_work(sql[name])), (
        "stripping every `unconditional` line out of %s removed work the arm "
        "COUNTS as well as the claim, so the rehearsal below would be asking "
        "about a file the arm can no longer object to rather than about a "
        "file whose claim is gone: %r before the strip, %r after"
        % (name, sorted(_unguarded_statement_work(sql[name])),
           sorted(_unguarded_statement_work(stripped))))
    rehearsed = dict(sql, **{name: stripped})
    would_fire = [n for n in sorted(rehearsed)
                  if _catalog_guarded_ddl(rehearsed[n])
                  and _unguarded_statement_work(rehearsed[n])
                  and not _states_unconditional_work(rehearsed[n])]
    assert name in would_fire, (
        "with every `unconditional` line stripped out of %s the omission arm "
        "does not name it, so the arm cannot see that claim go and its "
        "silence over the real file carries no information. On the stripped "
        "text it guards %r and issues %r outside a guard, and the arm named "
        "%r"
        % (name, sorted(_catalog_guarded_ddl(stripped)),
           sorted(_unguarded_statement_work(stripped)), would_fire))


def test_every_unguarded_statement_kind_is_named_in_the_prose_that_discloses_it():
    """A DISCLOSURE SENTENCE IS CHECKED AGAINST THE FILE, NOT TRUSTED.

    The omission arm above establishes that a file issuing unguarded work
    says SOMETHING about unconditional work. It cannot tell whether the
    something is COMPLETE, and the one time that was measured it was not:
    332's sentence read "outside every guard block this file issues a
    `COMMENT ON COLUMN` and an `UPDATE`" -- an exhaustive enumeration, in a
    file that issues three, the third being the `CREATE TEMP TABLE
    _m332_state` that runs outside every guard, creates a relation and reads
    `information_schema`. The reader the disclosure exists for was told a
    re-run issues two statements and it issues three.

    An enumeration nothing checks is the same shape as the keyword list that
    let it through, so it is checked: every kind in the DERIVED census has to
    appear, by name and on a word boundary, in the comment BLOCK that carries
    the file's unconditional-work claim. The expected value is the file's
    statements and nothing here is typed out (#342), so a file that grows a
    statement of a kind its header does not name reds until the header names
    it.

    THE REGION IS THE PARAGRAPH, NOT THE FILE, and that is not tidiness.
    Asked of the whole file this check passed for the wrong reason: 331
    mentions `UPDATE` in three separate comment blocks and `CREATE TABLE IF
    NOT EXISTS` in two, so deleting its disclosure outright would have left
    the check reading true. `_disclosure_prose` says why the region is
    selected the way it is and which direction it fails in.

    AND THE MATCH IS ON A WORD BOUNDARY, which is what caught the first
    version of 331's new paragraph: it said "two `INSERT INTO`s", and
    `INSERT INTOs` is not a naming of `INSERT INTO`. A substring match
    accepted it -- the check hiding a gap in the sentence it exists to
    police.

    SCOPED to the files the omission arm is scoped to -- those that guard DDL
    on the catalog. A file that guards nothing (333) raises no contradiction
    between its guards and its statements and is not asked to write the
    paragraph this checks.
    """
    sql = {name: (SQL_DIR / name).read_text(encoding="utf-8") for name in OWNED}
    guarded = {name: _catalog_guarded_ddl(text) for name, text in sql.items()}
    subjects = [name for name in sorted(sql)
                if guarded[name] and _unguarded_statement_work(sql[name])]
    assert subjects, (
        "no file in this delta both guards DDL on the catalog and issues "
        "statement-level work, so there is no disclosure for this test to "
        "check and its silence carries no information: %r"
        % {name: sorted(_unguarded_statement_work(sql[name]))
           for name in sorted(sql)})

    missing = [(name, _undisclosed_statement_work(sql[name]))
               for name in subjects if _undisclosed_statement_work(sql[name])]
    assert not missing, (
        "a file issues a kind of statement outside every guard block and its "
        "header does not name it, so the header's list of what a re-run "
        "issues is shorter than what a re-run issues:\n%s"
        % "\n".join("  %s issues %r and names %r -- undisclosed: %r"
                     % (name, sorted(_unguarded_statement_work(sql[name])),
                        sorted(k for k in _unguarded_statement_work(sql[name])
                               if k not in undisclosed),
                        undisclosed)
                     for name, undisclosed in missing))

    # ── The census is DERIVED, and this check moves with it ────────────────
    # A verb no list in this module has ever named, planted at statement level
    # in a real file. A keyword census could not see it at all -- which is the
    # whole finding -- so the control is that this one FINDS it and reports it
    # undisclosed. Then the inert twin: the same file with a sentence naming
    # it goes quiet, or the check would force a header to drop the subject
    # rather than state it (the failure mode #342 warns about from the other
    # side).
    subject = "332_pc_edition_schedule.sql"
    planted = sql[subject].replace("\nCOMMIT;", "\nANALYZE pc_editions;\nCOMMIT;")
    assert planted != sql[subject], "the plant did not apply to %s" % subject
    assert "ANALYZE" in _statement_census(planted), (
        "the census does not see a top-level statement of a kind it was "
        "never told about, so it is a list again and the next unnamed verb "
        "is invisible the way `CREATE TEMP TABLE` was: %r"
        % (_statement_census(planted),))
    assert _undisclosed_statement_work(planted) == ["ANALYZE"], (
        "a planted unguarded `ANALYZE` that no sentence in the file names is "
        "not reported, so this check would pass over exactly the omission it "
        "exists for: %r" % (_undisclosed_statement_work(planted),))
    disclosed = planted.replace(
        "-- UNCONDITIONAL WORK, NAMED:",
        "-- It also issues an `ANALYZE`, outside every guard block.\n"
        "-- UNCONDITIONAL WORK, NAMED:")
    assert disclosed != planted, "the disclosure twin did not apply"
    assert not _undisclosed_statement_work(disclosed), (
        "naming the planted statement in the disclosure block does not "
        "satisfy the check, so it would force a header to drop the subject "
        "rather than disclose it: %r"
        % (_undisclosed_statement_work(disclosed),))

    # ── The census descends into `DO` bodies, and that is measured here ────
    # A `DO` carried a blanket exemption until this round, so unconditional
    # work inside one was invisible however loud it was -- 336's post-check
    # issues three statements that way and its header called `COMMENT ON
    # COLUMN` the file's only unguarded schema statement. The plant is an
    # `UPDATE` in a guard-SHAPED block: the body carries an `IF NOT EXISTS
    # (SELECT ...)` probe, so the block reads as a guard, and the `UPDATE`
    # sits outside that `IF` and runs on every application.
    inner = "336_bug_reports_kind.sql"
    planted_do = sql[inner].replace(
        "\nCOMMIT;",
        "\nDO $m336plant$\n"
        "BEGIN\n"
        "    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'bug_reports') THEN\n"
        "        RAISE NOTICE 'absent';\n"
        "    END IF;\n"
        "    UPDATE bug_reports SET kind = kind;\n"
        "END $m336plant$;\nCOMMIT;")
    assert planted_do != sql[inner], "the DO-body plant did not apply"
    assert "UPDATE" in _statement_census(planted_do), (
        "the census does not see a statement issued unconditionally inside a "
        "`DO` body, so every `DO` is a guard as far as this arm is concerned "
        "and 336's post-check is invisible again: %r"
        % (_statement_census(planted_do),))
    assert "UPDATE" in _undisclosed_statement_work(planted_do), (
        "a statement a `DO` body issues every time is not reported against "
        "the header that does not name it: %r"
        % (_undisclosed_statement_work(planted_do),))

    # And the twin, or the descent would force every guard block to be
    # disclosed as unconditional work: a `DO` whose body only reads and
    # raises leaves the census exactly as it was.
    twin = sql[inner].replace(
        "\nCOMMIT;",
        "\nDO $m336twin$\n"
        "DECLARE\n"
        "    v_n BIGINT;\n"
        "BEGIN\n"
        "    SELECT COUNT(*) INTO v_n FROM bug_reports;\n"
        "    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'bug_reports') THEN\n"
        "        RAISE NOTICE 'absent';\n"
        "    END IF;\n"
        "    RAISE NOTICE 'rows %', v_n;\n"
        "END $m336twin$;\nCOMMIT;")
    assert twin != sql[inner], "the guard-block twin did not apply"
    assert _statement_census(twin) == _statement_census(sql[inner]), (
        "adding a `DO` block that only reads the catalog and raises changes "
        "the census, so the descent counts guard blocks as unconditional "
        "work and every guarded file would have to disclose its guards: %r "
        "against %r"
        % (_statement_census(twin), _statement_census(sql[inner])))

    # ── The region is the PARAGRAPH, and that is measured here ────────────
    # Naming the statement somewhere ELSE in the file must NOT satisfy it, or
    # the check is back to reading true whether or not a disclosure exists --
    # which is how it read before this was measured on 331.
    elsewhere = planted.replace(
        "-- The rollover walks the anchor forward",
        "-- An `ANALYZE` is mentioned here, far from any disclosure.\n"
        "\n-- The rollover walks the anchor forward")
    assert elsewhere != planted, "the elsewhere control did not apply"
    assert _undisclosed_statement_work(elsewhere) == ["ANALYZE"], (
        "a kind named in a comment block that carries no unconditional-work "
        "claim counts as disclosed, so this check cannot tell a disclosure "
        "from a passing mention: %r"
        % (_undisclosed_statement_work(elsewhere),))
