"""MDPL point 5: the census of the circles an account deletion can close through
a players row (mdpl_census.py), computed again from the source and compared
with mdpl_census_frozen.json.

Red on a new statement that waits for a players row (a new site), a new entry
that reaches a site, a changed class, a changed step 1 (the deletion's own
waits) or a new statement whose SQL text the reader cannot read. Every READ
site carries its judgement by hand, every unread statement its reason, and
the premises of the two unread judgements are read here. A planted route of
each class is classed as it must be, with a planted route that holds nothing
as the negative control. Two mutants of the source move a frozen site: a
route that drops its identity key changes the site's class, and a new route
that reaches the site adds an entry; the unchanged source, computed the same
way, gives the frozen record (the control).

A site whose class rests on an identity key (its fallback, the class without
the key, is above it) names whose key covers whose row, or is judged to its
fallback by hand (lesson 732). The regression control of the reader's
widening: with its eleven switches off it computes mdpl_census_base.json, the
census frozen before the widening, exactly (the test keeps the name it had
with six). A lock taken without a wait (SKIP LOCKED, NOWAIT) is a hold: a
planted route that takes the held row that way is READ, as with a wait, and a
deletion lock on a players row taken that way is one of the deletion's holds.
The foreign keys that migrations
drop by dynamic SQL are read from each migration's own lookup. The reader
holds a plain INSERT without a wait; that the deletion's plain inserts cannot
wait (gold_transactions alone, keyed by its generated id) is read here too.

STACK-SEAM-1 has two guards here. The owed judgements are held fixed by
key: the sites whose "why" opens with "OWED under " are exactly
OWED_SITES, _qapply_credit's three, and one is added or taken out only by
a change of that test. The pin reads the client's string literals: no
statement of a .cs file under plugin/ builds the quarantine's credit path,
the precondition the owed sentence names.

Pure Python: no database. Refreeze after a reviewed change with
`python mdpl_census.py --freeze` (it keeps every judgement and writes an
empty one for a new READ site, which this test refuses).
"""
import ast
import copy
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.setrecursionlimit(20000)

import mdpl_census as mc  # noqa: E402


@pytest.fixture(scope="module")
def frozen():
    with open(mc.FROZEN, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def src():
    return mc.Source()


@pytest.fixture(scope="module")
def measured(src):
    return mc.measured(src)


def test_step_1_is_the_frozen_one(measured, frozen):
    assert measured["step1"] == frozen["step1"]


def test_every_site_its_entries_and_its_class_are_the_frozen_ones(measured, frozen):
    fz = {k: {f: d[f] for f in mc.COMPARED} for k, d in frozen["sites"].items()}
    got = measured["sites"]
    new = sorted(set(got) - set(fz))
    gone = sorted(set(fz) - set(got))
    moved = sorted(k for k in set(got) & set(fz) if got[k] != fz[k])
    assert not new and not gone and not moved, {
        "new": new[:10], "gone": gone[:10],
        "moved": [(k, fz[k], got[k]) for k in moved[:5]]}


def test_every_unread_statement_is_the_frozen_one(measured, frozen):
    assert measured["unread"] == sorted(frozen["unread"])


def test_every_untyped_store_is_the_frozen_one(measured, frozen):
    """A store of a Player column on an object the reader cannot type (ORM_TYPES)."""
    assert measured["untyped"] == sorted(frozen["untyped"])


def test_every_read_site_and_unread_statement_carries_its_judgement(frozen):
    bare = [k for k, d in frozen["sites"].items() if d["class"] == "READ" and len(d.get("why", "").strip()) < 40]
    assert not bare, bare
    assert all(len(w.strip()) >= 40 for w in frozen["unread"].values()), frozen["unread"]
    assert all(len(w.strip()) >= 40 for w in frozen["untyped"].values()), frozen["untyped"]
    # a refreeze that moves a site out of READ leaves its reason behind; it is read again and removed by hand
    left = sorted(k for k, d in frozen["sites"].items() if "why" in d and d["class"] != "READ" and "judged" not in d)
    assert not left, left
    assert set(frozen["classes"]) == set(mc.RANK)
    for k, d in frozen["sites"].items():
        if d["class"] == "READ":
            # a judgement that names a scene names one this repo defines
            for name in re.findall(r"\btest_\w+", d["why"]):
                assert name in frozen["scenes"], (k, name)


def test_the_unread_judgements_premises_hold(src):
    # _report_rows: every caller passes a _REPORT_* statement; none locks or writes.
    rx = re.compile(r"\bFOR\s+(?:NO\s+KEY\s+UPDATE|UPDATE|SHARE|KEY\s+SHARE)\b|\bINSERT\s+INTO\b|"
                    r"\bUPDATE\s+\w+\s+SET\b|\bDELETE\s+FROM\b|advisory", re.I)
    callers = set()
    for node in mc.ast.walk(src.tree):
        if isinstance(node, mc.ast.Call) and getattr(node.func, "id", "") == "_report_rows":
            arg = node.args[1]
            while isinstance(arg, mc.ast.Call) and isinstance(arg.func, mc.ast.Attribute):
                arg = arg.func.value              # X.format(...) -> X
            if isinstance(arg, mc.ast.Subscript):
                arg = arg.value                   # X[mode] -> every value of X
            assert isinstance(arg, mc.ast.Name) and arg.id.startswith("_REPORT_"), mc.ast.dump(node.args[1])[:200]
            callers.add(arg.id)
    assert len(callers) >= 10, callers
    assigns = {n.targets[0].id: n.value for n in src.tree.body
               if isinstance(n, mc.ast.Assign) and isinstance(n.targets[0], mc.ast.Name)}

    def constants(node):
        return [c.value for c in mc.ast.walk(node) if isinstance(c, mc.ast.Constant) and isinstance(c.value, str)]
    for name in sorted(callers):
        texts = src.dictvals.get(name) or src.listvals.get(name) or (
            [src.consts[name]] if name in src.consts else None)
        if texts is None:
            # A statement built by a helper (a dict comprehension calling it):
            # every text it can build is made of the helper's string constants
            # and the comprehension source's, so read those.
            v = assigns[name]
            assert isinstance(v, mc.ast.DictComp) and isinstance(v.value, mc.ast.Call), name
            helper = src.defs[v.value.func.id]
            source = v.generators[0].iter
            while isinstance(source, mc.ast.Call) and isinstance(source.func, mc.ast.Attribute):
                source = source.func.value        # X.items() -> X
            texts = constants(helper) + constants(assigns[source.id])
            assert len(texts) >= 5, name
        assert not any(rx.search(t) for t in texts), name
    # _discord_fix_probe: the pattern ends at the nonce predicate, so the
    # statement it picks carries no FOR clause.
    pat = None
    for node in src.tree.body:
        if isinstance(node, mc.ast.Assign) and getattr(node.targets[0], "id", "") == "_DISCORD_FIX_READ":
            pat = node.value.args[0].value
    assert pat is not None and pat.startswith(r"^\s*SELECT\b") and pat.endswith(r"AND nonce = CAST\(:nonce AS text\)\s*$")
    # admin_evidence:_section_rows: every caller passes one statement of a dict
    # read from SECTION_SQL, the module's {source: section_sql(source)}; none of
    # section_sql's texts locks or writes.
    ae = mc.ast.parse(open(os.path.join(mc.API, "admin_evidence.py"), encoding="utf-8").read())
    fns = {n.name: n for n in mc.ast.walk(ae) if isinstance(n, (mc.ast.FunctionDef, mc.ast.AsyncFunctionDef))}
    texts = constants(fns["section_sql"])
    assert len(texts) >= 7 and not any(rx.search(t) for t in texts)
    table = [n.value for n in ae.body if isinstance(n, mc.ast.Assign)
             and [getattr(t, "id", "") for t in n.targets] == ["SECTION_SQL"]]
    assert len(table) == 1 and isinstance(table[0], mc.ast.DictComp) \
        and getattr(table[0].value.func, "id", "") == "section_sql", mc.ast.dump(table[0])[:200] if table else table
    calls = [n for n in mc.ast.walk(ae) if isinstance(n, mc.ast.Call) and getattr(n.func, "id", "") == "_section_rows"]
    assert len(calls) >= 6, len(calls)
    for c in calls:
        arg = c.args[1]
        assert isinstance(arg, mc.ast.Subscript) and isinstance(arg.value, mc.ast.Name), mc.ast.dump(arg)[:200]

    def from_table(fn):
        """The names fn binds to SECTION_SQL[...], alone or as one element of a tuple."""
        out = set()
        for n in mc.ast.walk(fn):
            if not isinstance(n, mc.ast.Assign) or len(n.targets) != 1:
                continue
            pairs = [(n.targets[0], n.value)]
            if isinstance(n.targets[0], mc.ast.Tuple) and isinstance(n.value, mc.ast.Tuple):
                pairs = list(zip(n.targets[0].elts, n.value.elts))
            for t, v in pairs:
                if isinstance(t, mc.ast.Name) and isinstance(v, mc.ast.Subscript) \
                        and getattr(v.value, "id", "") == "SECTION_SQL":
                    out.add(t.id)
        return out
    callers = [f for f in fns.values() if f.name != "_section_rows" and any(c in list(mc.ast.walk(f)) for c in calls)]
    assert callers
    for fn in callers:
        used = {c.args[1].value.id for c in calls if c in list(mc.ast.walk(fn))}
        assert used and used <= from_table(fn), (fn.name, used, from_table(fn))
    # seat_evidence:sitting_pass: its statement is rs.sitting_statement(rule),
    # which runs a sitting operator; operators are registered only in
    # review_measures (sitting_operator), a module that imports nothing and whose
    # source neither locks nor writes.
    se = open(os.path.join(mc.API, "seat_evidence.py"), encoding="utf-8").read()
    assert re.search(r"sql, binds = rs\.sitting_statement\(rule\)", se)
    rm_src = open(os.path.join(mc.API, "review_measures.py"), encoding="utf-8").read()
    rm_tree = mc.ast.parse(rm_src)
    imports = [n for n in mc.ast.walk(rm_tree) if isinstance(n, (mc.ast.Import, mc.ast.ImportFrom))]
    assert all(isinstance(n, mc.ast.ImportFrom) and n.module == "__future__" for n in imports), imports
    assert not rx.search(rm_src)
    for name in sorted(os.listdir(mc.API)):
        if name.endswith(".py") and name != "review_measures.py":
            body = open(os.path.join(mc.API, name), encoding="utf-8").read()
            assert not re.search(r"Entry\(\s*[\"']sitting[\"']|sitting_operator\(", body), name


def _numbered_migrations():
    out = []
    for name in os.listdir(mc.SQL_DIR):
        m = re.match(r"(\d+)_.*\.sql$", name)
        if m:
            out.append((int(m.group(1)), name))
    return sorted(out)


def _sql_body(name):
    with open(os.path.join(mc.SQL_DIR, name), encoding="utf-8", errors="replace") as fh:
        return re.sub(r"--[^\n]*", " ", fh.read())


# A migration that changes a foreign key or a trigger inside a dynamic string
# (EXECUTE): the census cannot read it, so each is listed here by hand with what
# it does; a new one turns the test below red until it is read and listed.
_DYNAMIC_DDL = {
    "192_chat_moderation.sql": "drops every foreign key of admin_actions that references admin_users "
                               "(FK_DROPPED_DYNAMIC)",
    "336_bug_reports_kind.sql": "adds a CHECK to its own pg_temp probe table: no foreign key, no trigger",
    "415_mail_send_receipts.sql": "drops every foreign key of mail_messages that covers in_reply_to "
                                  "(FK_DROPPED_DYNAMIC)",
    "416_lobby_invites.sql": "drops the old CHECK of mail_messages.kind (contype 'c'): no foreign key, no trigger",
}


def _forward_number(name):
    """A .sql file's place in the forward chain: a numbered migration's number,
    or a resume file's (resume_NNN_..., which finishes migration NNN); None for
    a rollback file, which the forward chain never applies (the reader still
    reads its foreign keys: an over-approximation toward more rows). Any other
    file is refused here until it is read and placed."""
    m = re.match(r"(?:resume_)?(\d+)_.*\.sql$", name)
    if m:
        return int(m.group(1))
    assert name.startswith("rollback_"), name
    return None


def _do_block_of(body, pos):
    """The text of the DO block of a migration body that holds position `pos`."""
    opens = [m for m in re.finditer(r"\bDO\s+(\$\w*\$)", body) if m.start() < pos]
    assert opens, pos
    m = opens[-1]
    end = body.find(m.group(1), m.end())
    assert end > pos, (pos, end)
    return body[m.end():end]


def test_the_foreign_keys_dropped_by_dynamic_sql_are_the_listed_ones(src):
    """The census reads REFERENCES from every .sql file and models.py; a foreign
    key dropped inside a DO block's EXECUTE is invisible to it, so
    FK_DROPPED_DYNAMIC names each drop by the selector of the migration's own
    pg_constraint lookup. Premises read here: the named migration's DO block
    holds the EXECUTE that drops a constraint of that table, over a lookup of
    the table's foreign keys (contype 'f', the table joined on conrelid) that
    reference the parent (joined on confrelid) or cover the column (an
    attribute of the table in conkey); the selector removes at least one key
    the reader read; every file that adds a key it removes is models.py, a
    rollback file (never applied forward: rollback_415 adds in_reply_to's key
    back) or a forward file numbered before the drop, never one after; the
    table is not on the table-level reading. And every numbered migration with
    dynamic DDL is one listed in _DYNAMIC_DDL, with what it does."""
    order = {name: n for n, name in _numbered_migrations()}
    for (table, how, value), name in sorted(mc.FK_DROPPED_DYNAMIC.items()):
        body = _sql_body(name)
        ex = re.search(r"EXECUTE\s+format\(\s*'ALTER TABLE\s+(?:ONLY\s+)?%s\s+DROP CONSTRAINT\s+%%I'" % table,
                       body, re.I)
        assert ex, (name, table)
        blk = _do_block_of(body, ex.start())
        con = re.search(r"\bFROM\s+pg_constraint\s+(\w+)", blk, re.I)
        assert con, name
        cn = con.group(1)
        assert re.search(r"\b%s\.contype\s*=\s*'f'" % cn, blk, re.I), name
        rel = re.search(r"\bJOIN\s+pg_class\s+(\w+)\s+ON\s+(\w+)\.oid\s*=\s*%s\.conrelid\b" % cn, blk, re.I)
        assert rel and rel.group(1) == rel.group(2), name
        assert re.search(r"\b%s\.relname\s*=\s*'%s'" % (rel.group(1), table), blk, re.I), (name, table)
        if how == "parent":
            par = re.search(r"\bJOIN\s+pg_class\s+(\w+)\s+ON\s+(\w+)\.oid\s*=\s*%s\.confrelid\b" % cn, blk, re.I)
            assert par and par.group(1) == par.group(2), name
            assert re.search(r"\b%s\.relname\s*=\s*'%s'" % (par.group(1), value), blk, re.I), (name, value)
        else:
            assert how == "column", how
            att = re.search(r"\bJOIN\s+pg_attribute\s+(\w+)\s+ON\s+(\w+)\.attrelid\s*=\s*%s\.oid\b" % rel.group(1),
                            blk, re.I)
            assert att and att.group(1) == att.group(2), name
            a = att.group(1)
            assert re.search(r"\b%s\.attname\s*=\s*'%s'" % (a, value), blk, re.I), (name, value)
            assert re.search(r"\b%s\.attnum\s*=\s*ANY\s*\(\s*%s\.conkey\s*\)" % (a, cn), blk, re.I), name
        gone = sorted(k for k, mig in src.fk_dropped.items() if mig == name and k[0] == table)
        assert gone, (name, "the selector removes no key the reader read")
        for k in gone:
            for origin in sorted(src.fk_origin[k]):
                n = None if origin == "models.py" else _forward_number(origin)
                assert n is None or n < order[name], (k, origin)
        assert table not in src.fk_fallback, table
    rx = re.compile(r"\bEXECUTE\b(?!\s+(?:FUNCTION|PROCEDURE)\b)[^;]*?\b(?:DROP CONSTRAINT|ADD CONSTRAINT|REFERENCES|"
                    r"CREATE (?:OR REPLACE )?(?:CONSTRAINT )?TRIGGER|DROP TRIGGER)\b", re.I | re.S)
    found = sorted(name for _n, name in _numbered_migrations() if rx.search(_sql_body(name)))
    assert found == sorted(_DYNAMIC_DDL), {"new": sorted(set(found) - set(_DYNAMIC_DDL)),
                                           "gone": sorted(set(_DYNAMIC_DDL) - set(found))}
    assert set(mc.FK_DROPPED_DYNAMIC.values()) <= set(_DYNAMIC_DDL)
    assert all(len(v) >= 40 for v in _DYNAMIC_DDL.values()), _DYNAMIC_DDL


def _call_name(node):
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def test_the_deletion_s_plain_inserts_cannot_wait(src):
    """A plain INSERT (no ON CONFLICT) waits only when it meets another
    transaction's in-flight row with the same unique key; the reader holds it
    without a wait (INSERT_WAITS). For step 1 that is a premise, read here:
    after phase A the deletion's plain inserts are into gold_transactions
    alone (the bet helpers' ledger rows), and gold_transactions' one unique
    key is its id, a BIGSERIAL primary key (migration 020) that models.py
    declares autoincrement and that no GoldTransaction(...) and no INSERT INTO
    gold_transactions in backend/api supplies (every such INSERT names its
    columns); neither models.py nor any .sql file gives the table another
    unique key, unique index or primary key. Red on a plain insert of the
    deletion into another table, on such a key, or on an insert that can
    name the id."""
    ev = [e for e in src.events(mc.DELETION) if e[0] == "L"]
    a_at = next(i for i, e in enumerate(ev)
                if e[4][0] == mc.DELETION and e[4][1].startswith(mc.PHASE_A_MARK))
    plain = sorted({e[1] for e in ev[a_at + 1:] if e[2] == mc.INS and e[3] == mc.HELD})
    assert plain == ["gold_transactions"], plain

    with open(os.path.join(mc.API, "models.py"), encoding="utf-8") as fh:
        mtext = fh.read()
    mtree = ast.parse(mtext)
    cls = [n for n in mtree.body if isinstance(n, ast.ClassDef) and n.name == "GoldTransaction"]
    assert len(cls) == 1, len(cls)
    table = [st.value.value for st in cls[0].body if isinstance(st, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in st.targets)]
    assert table == ["gold_transactions"], table
    pk = []
    for node in ast.walk(cls[0]):
        assert not (isinstance(node, ast.Name) and node.id == "__table_args__"), "__table_args__"
        if isinstance(node, ast.Call):
            kws = [k.arg for k in node.keywords]
            assert "unique" not in kws and None not in kws, ast.get_source_segment(mtext, node)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            kw = {k.arg: k.value for k in node.value.keywords}
            if "primary_key" in kw:
                pk.append((node.targets[0].id, ast.literal_eval(kw["primary_key"]),
                           ast.literal_eval(kw["autoincrement"]) if "autoincrement" in kw else None))
    assert pk == [("id", True, True)], pk
    for node in ast.walk(mtree):
        if isinstance(node, ast.Call) and _call_name(node) in ("Index", "UniqueConstraint",
                                                                 "PrimaryKeyConstraint"):
            seg = ast.get_source_segment(mtext, node) or ""
            assert "GoldTransaction" not in seg and "gold_transactions" not in seg, seg

    rx_key = re.compile(
        r"\bUNIQUE\b[^;]*?\bON\s+(?:ONLY\s+)?(?:public\.)?gold_transactions\b"
        r"|\bALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?(?:public\.)?gold_transactions\b[^;]*?"
        r"\b(?:UNIQUE|PRIMARY\s+KEY)\b", re.I | re.S)
    rx_create = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?gold_transactions"
                           r"\s*\((.*?)\)\s*;", re.I | re.S)
    creates = []
    for fn in sorted(os.listdir(mc.SQL_DIR)):
        if not fn.endswith(".sql"):
            continue
        with open(os.path.join(mc.SQL_DIR, fn), encoding="utf-8") as fh:
            body = fh.read()
        hit = rx_key.search(body)
        assert hit is None, (fn, hit.group(0)[:300] if hit else None)
        creates += [(fn, m.group(1)) for m in rx_create.finditer(body)]
    assert [fn for fn, _b in creates] == ["020_economy.sql"], [fn for fn, _b in creates]
    cols = creates[0][1]
    assert not re.search(r"\bUNIQUE\b", cols, re.I), cols
    assert [ln.split()[0] for ln in cols.splitlines() if re.search(r"\bPRIMARY\s+KEY\b", ln, re.I)] == ["id"]
    assert re.search(r"^\s*id\s+BIGSERIAL\s+PRIMARY\s+KEY\s*,", cols, re.I | re.M), cols

    calls = 0
    for fn in sorted(os.listdir(mc.API)):
        if not fn.endswith(".py"):
            continue
        with open(os.path.join(mc.API, fn), encoding="utf-8") as fh:
            text = fh.read()
        for m in re.finditer(r"\bINSERT\s+INTO\s+gold_transactions\b(\s*\(([^)]*)\))?", text, re.I):
            assert m.group(1), (fn, "an INSERT INTO gold_transactions without its column list")
            named = [c.strip().strip('"').lower() for c in m.group(2).split(",")]
            assert "id" not in named, (fn, named)
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Call) and _call_name(node) == "GoldTransaction":
                kws = [k.arg for k in node.keywords]
                assert not node.args and "id" not in kws and None not in kws, (fn, node.lineno, kws)
                calls += 1
            if isinstance(node, ast.Call) and _call_name(node) == "insert" and node.args:
                a = node.args[0]
                assert not (isinstance(a, (ast.Name, ast.Attribute)) and
                            (getattr(a, "id", None) or getattr(a, "attr", None)) == "GoldTransaction"), (fn, node.lineno)
            assert not (isinstance(node, ast.Attribute) and node.attr == "__table__" and
                        isinstance(node.value, (ast.Name, ast.Attribute)) and
                        (getattr(node.value, "id", None) or getattr(node.value, "attr", None)) == "GoldTransaction"), \
                (fn, node.lineno)
    assert calls >= 4, calls        # the four bet helpers' ledger rows at least: the walk read the constructors


def test_every_site_that_rests_on_an_identity_key_names_whose_key_covers_whose_row(frozen):
    """Lesson 732. KEY is computed from the key's form: an identity key taken
    before every table the route holds that the deletion waits for. It closes
    no circle only when that key is the key of the player whose row the
    statement waits for, which the reader cannot see. So every site whose
    class rests on a key (its fallback, the class without the key, is above
    its class) carries a sentence by hand: "covers" (whose key covers whose
    row), or "judged": its fallback, with its reason ("why"), where the key is
    the caller's and the row can be another player's, P's among them. A
    judgement belongs to such sites alone: a refreeze that moves a site off a
    key leaves its judgement behind, and this test asks for it to be read again."""
    bad = []
    for k, d in frozen["sites"].items():
        if mc.RANK[d["fallback"]] < mc.RANK[d["class"]]:
            bad.append(("fallback below the class", k))
        if d["fallback"] == d["class"]:
            if "covers" in d or "judged" in d:
                bad.append(("not on a key", k))
            continue
        if "judged" in d:
            if d["judged"] != d["fallback"] or "covers" in d or len(d.get("why", "").strip()) < 40:
                bad.append(("judged", k))
            for name in re.findall(r"\btest_\w+", d.get("why", "")):
                assert name in frozen["scenes"], (k, name)
        elif len(d.get("covers", "").strip()) < 40:
            bad.append(("covers", k))
    assert not bad, bad


def test_with_the_six_switches_off_the_reader_gives_the_census_as_first_frozen(monkeypatch):
    """The regression control of the reader's widening (MDPL r2): with every
    switch off, the census computed now is mdpl_census_base.json, the census
    frozen before the widening, exactly (step 1, every site's record, the
    unread statements), and no untyped store is measured. SWITCHES names every
    switch the module has, so a new one is turned off here too. When main.py
    has moved since the base file's last commit, a red here can be the
    source's and not the reader's. Prove the reader first (main.py at that
    commit, read with every switch off, gives the base exactly), and only then
    read the base again at the tip, with that proof first in its commit's
    message."""
    moved_source = (
        "When main.py has moved since the base file's last commit, a red here can be the source's and not "
        "the reader's. Prove the reader first (main.py at that commit, read with every switch off, gives the "
        "base exactly), and only then read the base again at the tip, with that proof first in its commit's "
        "message.")
    assert set(mc.SWITCHES) == {n for n in vars(mc) if n.isupper() and isinstance(vars(mc)[n], bool)}
    for name in mc.SWITCHES:
        monkeypatch.setattr(mc, name, False)
    m = mc.measured(mc.Source())
    with open(mc.BASE, encoding="utf-8") as fh:
        base = json.load(fh)
    assert m["step1"] == base["step1"], moved_source
    got = {k: {f: d[f] for f in mc.BASE_FIELDS} for k, d in m["sites"].items()}
    new = sorted(set(got) - set(base["sites"]))
    gone = sorted(set(base["sites"]) - set(got))
    moved = sorted(k for k in set(got) & set(base["sites"]) if got[k] != base["sites"][k])
    assert not new and not gone and not moved, (moved_source, {
        "new": new[:10], "gone": gone[:10], "moved": [(k, base["sites"][k], got[k]) for k in moved[:5]]})
    assert m["unread"] == base["unread"], moved_source
    assert "untyped" not in m


def test_own_and_guarded_functions_are_the_ones_the_bound_test_classes():
    import test_mdpl_bound as tb
    assert mc.OWN_ROW_FNS == {fn for fn, _ in tb._OWN_ROW}
    assert mc.GUARDED_FNS == {fn for fn, _ in tb._GUARD_ROW + tb._PARTY_ROW}


_PLANT = '''

@app.post("/mdpl-plant-{name}")
async def mdpl_plant_{name}(db: AsyncSession = Depends(get_db)):
{body}
'''
_WRITE_P = '    await db.execute(text("UPDATE players SET gold_earned = gold_earned + 1 WHERE id = :pid"), {"pid": 1})\n'
_HOLD = '    await db.execute(text("SELECT 1 FROM steam_sessions WHERE steam_id = :s FOR UPDATE"), {"s": "x"})\n'
_KEY = '    await db.execute(text(_IDENTITY_KEY_SQL), {"sid": "x"})\n'
_NAME_P = ('    await db.execute(text("INSERT INTO gold_transactions (player_id, amount, reason) '
           'VALUES (:pid, 1, \'x\')"), {"pid": 1})\n')
_PLANTS = {
    "clear": (_WRITE_P, "CLEAR"),                 # the negative control: it holds nothing
    "read": (_HOLD + _WRITE_P, "READ"),           # holds a row the deletion deletes later
    # the same row taken without a wait still holds it (NB_HOLDS): the same class
    "read_skip": (_HOLD.replace("FOR UPDATE", "FOR UPDATE SKIP LOCKED") + _WRITE_P, "READ"),
    "read_nowait": (_HOLD.replace("FOR UPDATE", "FOR UPDATE NOWAIT") + _WRITE_P, "READ"),
    "key": (_KEY + _HOLD + _WRITE_P, "KEY"),      # the same, behind the identity key
    "upgrade": (_NAME_P + _WRITE_P, "UPGRADE"),   # names the player in an insert first
}


@pytest.fixture(scope="module")
def planted():
    with open(os.path.join(mc.API, "main.py"), encoding="utf-8") as fh:
        text = fh.read()
    for name, (body, _cls) in _PLANTS.items():
        text += _PLANT.format(name=name, body=body)
    psrc = mc.Source(main_text=text)
    _s1, got = mc.sites(psrc, entries=["mdpl_plant_" + n for n in _PLANTS])
    return got


@pytest.mark.parametrize("name", sorted(_PLANTS))
def test_a_planted_route_is_a_new_site_of_its_class(name, planted, frozen):
    site = "mdpl_plant_%s | UPDATE players SET gold_earned = gold_earned + 1 WHERE id = :pid | 0" % name
    assert site in planted, sorted(planted)[:20]
    assert site not in frozen["sites"]            # so the comparison above would be red
    assert planted[site]["class"] == _PLANTS[name][1], planted[site]
    assert planted[site]["entries"] == ["mdpl_plant_" + name]


_PARTY_LOCK = ('_DELETION_PARTY_LOCK_SQL = (\n'
               '    "SELECT steam_id FROM players WHERE id = :pid FOR NO KEY UPDATE SKIP LOCKED")')


def test_a_lock_the_deletion_takes_without_a_wait_on_a_players_row_is_a_hold(src):
    """NB_HOLDS on the deletion's side: its party guard takes a bettor's players
    row FOR NO KEY UPDATE SKIP LOCKED; made FOR UPDATE SKIP LOCKED, the deletion
    holds UPDATE on a players row from phase A, so a route's KEY SHARE wait there
    meets it. The control: phase A holds what its own row and its foreign keys
    give, and no UPDATE."""
    got = mc.deletion_holds(src)
    assert got == {"A": {mc.KS, mc.NKU}, "B": {mc.KS, mc.NKU, mc.UPD}}, got
    with open(os.path.join(mc.API, "main.py"), encoding="utf-8") as fh:
        text = fh.read()
    assert text.count(_PARTY_LOCK) == 1
    msrc = mc.Source(main_text=text.replace(_PARTY_LOCK, _PARTY_LOCK.replace("FOR NO KEY UPDATE", "FOR UPDATE")))
    assert mc.UPD in mc.deletion_holds(msrc)["A"]


_PHASE_A_LINE = '    await db.execute(text("UPDATE players SET pc_shards = 0 WHERE id = :pid"), {"pid": pid})\n'
_OTHER_ROW_UPD = '    await db.execute(text("SELECT 1 FROM players WHERE id = :other FOR UPDATE"), {"other": 1})\n'


def test_a_lock_the_deletion_s_own_function_takes_on_a_players_row_is_a_hold(src):
    """deletion_holds reads every players lock of the deletion, its own
    functions' too: the reader does not tell rows apart, and delete_player_data
    takes other players' rows (a lobby's new host's KEY SHARE, a case
    reporter's). A FOR UPDATE planted in delete_player_data in phase A makes
    phase A hold UPDATE. The control: unplanted, phase A holds no UPDATE."""
    assert mc.UPD not in mc.deletion_holds(src)["A"]
    with open(os.path.join(mc.API, "main.py"), encoding="utf-8") as fh:
        text = fh.read()
    msrc = mc.Source(main_text=_in_function(text, "async def delete_player_data(", _PHASE_A_LINE,
                                            _PHASE_A_LINE + _OTHER_ROW_UPD))
    assert mc.UPD in mc.deletion_holds(msrc)["A"]


def test_a_foreign_key_the_deletion_s_own_function_checks_is_a_wait(src, monkeypatch):
    """OWN_FK_WAITS: before the tombstone delete_player_data makes a live member
    a lobby's host (host_player_id, a foreign key: KEY SHARE on that member's
    players row), so step 1 holds ("players", KEY SHARE) in phase A, and
    link_discord, which holds a players row in UPDATE mode (the release of the
    Discord id) before it writes the linking player's row, is READ there
    without its key. Since the ban gate, the route keys the linking player
    before it holds any row, so the class is KEY and the READ the switch makes
    stands as the fallback. The control: with the switch off, step 1 has no
    such wait and the site's class and fallback are CLEAR."""
    site = "link_discord | ORM player.discord_id = | 0"
    assert ("players", mc.KS) in mc.step1(src)["A"]
    _s1, got = mc.sites(src, entries=["link_discord"])
    assert got[site]["class"] == "KEY" and got[site]["fallback"] == "READ" \
        and "A" in got[site]["phases"], got[site]
    monkeypatch.setattr(mc, "OWN_FK_WAITS", False)
    assert ("players", mc.KS) not in mc.step1(src)["A"]
    _s1, off = mc.sites(src, entries=["link_discord"])
    assert off[site]["class"] == "CLEAR" and off[site]["fallback"] == "CLEAR", off[site]


_HOST_UPDATE = ("_lobby_seat_left_core | UPDATE {?t:ffa_lobbies|ovt_lobbies|team_lobbies} "
                "SET host_player_id = :h | 0")


def _q_held(got):
    return sorted(k for k, d in got.items() if "?" in d["held"])


def test_no_held_set_of_the_measured_census_holds_an_unread_table(measured):
    """A statement whose table the reader cannot name reads as "?", which
    conflicts with every table: a held set that holds it stands for a
    statement the census lost (RULING CENSUS-1, section 1)."""
    assert _q_held(measured["sites"]) == []
    assert not [w for ws in measured["step1"].values() for w in ws if w.startswith("? ")]


def test_a_name_unpacked_from_a_dictionary_of_table_tuples_reads_its_tables(src, monkeypatch):
    """DICT_TUPLES: `qt, lt = _LOBBY_SEAT_TABLES[mode]` in _lobby_seat_left_core
    reads lt as the three lobby tables, so its host update is a site and the
    statements after it hold their tables. The control: with the switch off
    the update is no site and the rows after it hold "?"."""
    _s1, on = mc.sites(src, entries=["ffa_queue_leave"])
    assert _HOST_UPDATE in on and _q_held(on) == [], (_q_held(on), sorted(on)[:10])
    monkeypatch.setattr(mc, "DICT_TUPLES", False)
    _s1, off = mc.sites(mc.Source(), entries=["ffa_queue_leave"])
    assert _HOST_UPDATE not in off and _q_held(off) != [], _q_held(off)


def test_a_loop_s_literal_texts_are_each_read_as_a_statement(src, measured, monkeypatch):
    """LOOP_TEXTS: `for _mode, _cancel in (("team", "UPDATE team_series ..."),
    ("ovt", "UPDATE ovt_series ..."))` in _ban_void_apply reads text(_cancel)
    as each text, each a statement with its own place. The control: with the
    switch off the statement is unread and neither place stands."""
    unread = "_ban_void_apply | text(_cancel)"
    heads = [p[1] for e in src.events("_ban_void_apply") if e[0] == "L" for p in [e[4]]
             if p[0] == "_ban_void_apply"]
    assert unread not in measured["unread"]
    assert any(h.startswith("UPDATE team_series SET status='cancelled'") for h in heads), heads
    assert any(h.startswith("UPDATE ovt_series SET status='canceled'") for h in heads), heads
    monkeypatch.setattr(mc, "LOOP_TEXTS", False)
    off = mc.Source()
    heads = [p[1] for e in off.events("_ban_void_apply") if e[0] == "L" for p in [e[4]]
             if p[0] == "_ban_void_apply"]
    assert unread in off.unread
    assert not any(h.startswith(("UPDATE team_series SET status='cancelled'",
                                 "UPDATE ovt_series SET status='canceled'")) for h in heads), heads


def test_a_loop_over_a_module_tuple_of_table_tuples_reads_its_tables(src, monkeypatch):
    """NAME_LOOPS: `for _lmode, _lqt, _llt in _BAN_LOBBY_TABLES` in
    _apply_ban_core reads _llt as the three lobby tables, so its lobby row
    lock names them and the ban's later rows hold no "?". The control: with
    the switch off the lock reads "?" and the ban's rows after it hold it."""
    q = [e for e in src.events("_apply_ban_core") if e[0] == "L" and e[1] == "?"]
    _s1, on = mc.sites(src, entries=["admin_ban"])
    assert q == [] and _q_held(on) == [], (q, _q_held(on))
    monkeypatch.setattr(mc, "NAME_LOOPS", False)
    off = mc.Source()
    q = [e for e in off.events("_apply_ban_core") if e[0] == "L" and e[1] == "?"]
    _s1, got = mc.sites(off, entries=["admin_ban"])
    assert q and _q_held(got) != [], (q, _q_held(got))


def _main_text():
    with open(os.path.join(mc.API, "main.py"), encoding="utf-8") as fh:
        return fh.read()


def test_a_module_tuple_bound_twice_is_not_read_by_the_loop_form():
    """NAME_LOOPS reads a name bound exactly once at module level; the mutant
    binds _BAN_LOBBY_TABLES a second time (the same shape), and the lobby row
    lock of _apply_ban_core reads "?" again, which the no-"?" test refuses."""
    text = _main_text()
    assert text.count("\n_BAN_LOBBY_TABLES = (") == 1
    mut = mc.Source(main_text=text + '\n_BAN_LOBBY_TABLES = (("ffa", "ffa_queue", "ffa_lobbies"),)\n')
    q = [e for e in mut.events("_apply_ban_core") if e[0] == "L" and e[1] == "?"]
    assert q, "a twice-bound module tuple was read"


# Section 5 of RULING CENSUS-1: the identity key the two lanes now share is
# ONE key. Read from the syntax tree of main.py; the deletion census's own
# normal form (mc.key_name) says when two spellings are one key.
_ADVISORY_FORM = re.compile(r"\bpg_(try_)?advisory_xact_lock(_shared)?\(", re.I)


def _identity_pin_failures(text, src):
    """[] when (i) _ban_lock_and_gate takes, for every id it locks and for the
    actor, one of exactly two statements, the shared and the exclusive lock of
    ONE key; (ii) delete_player_data takes the exclusive form of that key on
    its own steam id before its first statement that locks or writes a row;
    (iii) the lane's constant, the gate's two statements and the deletion's
    statement are one key by mc.key_name. Else what fails, by half."""
    tree = ast.parse(text)
    top = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    binds = {}
    for st in tree.body:
        if isinstance(st, ast.Assign):
            for t in st.targets:
                if isinstance(t, ast.Name):
                    binds.setdefault(t.id, []).append(st.value)

    def read(x, seen=()):
        if isinstance(x, ast.Constant) and isinstance(x.value, str):
            return x.value
        if isinstance(x, ast.BinOp) and isinstance(x.op, ast.Add):
            a, b = read(x.left, seen), read(x.right, seen)
            return None if a is None or b is None else a + b
        if isinstance(x, ast.Name) and x.id not in seen and len(binds.get(x.id, [])) == 1:
            return read(binds[x.id][0], seen + (x.id,))
        return None

    def key(sql):
        m = mc.RX_KEY.search(mc._norm(sql))
        return None if m is None else mc.key_name(mc._balanced(m.group(2)))

    def takes(node):
        """(call, text, try, shared) of every advisory statement executed under node."""
        out = []
        for c in ast.walk(node):
            if isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "execute" and c.args \
                    and isinstance(c.args[0], ast.Call) and getattr(c.args[0].func, "id", "") == "text":
                t = read(c.args[0].args[0])
                m = _ADVISORY_FORM.search(t or "")
                if m:
                    out.append((c, t, bool(m.group(1)), bool(m.group(2))))
        return sorted(out, key=lambda x: (x[0].lineno, x[0].col_offset))

    def sid_bind(call):
        d = next((a for a in call.args[1:] if isinstance(a, ast.Dict)), None)
        return None if d is None else next((ast.unparse(v) for k, v in zip(d.keys, d.values)
                                            if isinstance(k, ast.Constant) and k.value == "sid"), None)

    out = []
    gate = top["_ban_lock_and_gate"]
    gt = takes(gate)
    forms = sorted((tr, sh) for _c, _t, tr, sh in gt)
    gkeys = {key(t) for _c, t, _tr, _sh in gt}
    if forms != [(False, False), (False, True)] or len(gkeys) != 1:
        out.append("(i) the gate's statements are not the shared and the exclusive lock of one key: %s %s"
                   % (forms, sorted(map(str, gkeys))))
    loops = [n for n in ast.walk(gate) if isinstance(n, (ast.For, ast.AsyncFor))
             and any(c is n2 for n2 in ast.walk(n) for c, *_ in gt)]
    if len(loops) != 1 or not (isinstance(loops[0].iter, ast.Name) and loops[0].iter.id == "ids"
                               and len(loops[0].body) == 1 and isinstance(loops[0].body[0], ast.If)):
        out.append("(i) the gate's two statements are not the one if/else of one loop over ids")
    else:
        loop, branch = loops[0], loops[0].body[0]
        arms = [branch.body, branch.orelse]
        if not all(len(a) == 1 and len(takes(ast.Module(body=a, type_ignores=[]))) == 1 for a in arms):
            out.append("(i) a path through the gate's loop takes neither statement, or more than one")
        if {sid_bind(c) for c, *_ in gt} != {loop.target.id if isinstance(loop.target, ast.Name) else None}:
            out.append("(i) a statement of the gate does not key the loop's id")
        ids = [n for n in ast.walk(gate) if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "ids" for t in n.targets)]
        names = {n.id for a in ids for n in ast.walk(a.value) if isinstance(n, ast.Name)}
        if len(ids) != 1 or not {"steam_ids", "actor", "exclusive"} <= names:
            out.append("(i) the ids the gate locks are not steam_ids, the actor and exclusive, bound once")
    dele = top["delete_player_data"]
    first = next(((c, t, tr, sh) for st in dele.body if isinstance(st, ast.Expr)
                  for (c, t, tr, sh) in takes(st)), None)
    if first is None or first[2] or first[3] or sid_bind(first[0]) != "steam_id":
        out.append("(ii) the deletion's first top-level advisory statement is not the exclusive key "
                   "of its own steam id: %r" % ((None if first is None else (first[1], sid_bind(first[0]))),))
    else:
        before = []
        for c in (n for st in dele.body for n in ast.walk(st)):      # the body: not decorators, not defaults
            if not isinstance(c, ast.Call) or c.lineno >= first[0].lineno:
                continue
            fname, attr = getattr(c.func, "id", None), getattr(c.func, "attr", None)
            if fname == "text" and c.args:
                t = read(c.args[0])
                if t is None or any(not tb.startswith("key:") for tb, _m, _b in src.locks_of_sql(t)):
                    before.append((c.lineno, (t or ast.unparse(c.args[0]))[:60]))
            elif fname in ("update", "delete", "insert") or attr in (
                    "with_for_update", "add", "add_all", "delete", "merge", "flush"):
                before.append((c.lineno, ast.unparse(c)[:60]))
            elif fname in top and any(e[0] == "L" and not e[1].startswith("key:") for e in src.events(fname)):
                before.append((c.lineno, fname))
        if before:
            out.append("(ii) the deletion locks or writes a row before its identity key: %s" % before)
    spell = {"_IDENTITY_KEY_SQL": key(read(ast.Name(id="_IDENTITY_KEY_SQL")) or "")}
    for i, (_c, t, _tr, _sh) in enumerate(gt):
        spell["gate %d" % i] = key(t)
    if first is not None:
        spell["deletion"] = key(first[1])
    if len(set(spell.values())) != 1 or not set(spell.values()) <= mc.IDENTITY_KEYS:
        out.append("(iii) the spellings are not one identity key: %s" % sorted(spell.items()))
    return out


def test_the_gate_and_the_deletion_take_one_identity_key(src):
    """Section 5 (i) to (iii) on the tree as it stands."""
    assert _identity_pin_failures(_main_text(), src) == []


_PIN_MUTANTS = {
    "the deletion's key made shared": (
        "async def delete_player_data(",
        'text("SELECT pg_advisory_xact_lock(hashtext(:sid))"), {"sid": steam_id})\n    player = ',
        'text("SELECT pg_advisory_xact_lock_shared(hashtext(:sid))"), {"sid": steam_id})\n    player = ', "(ii)"),
    "the gate's shared statement given another key expression": (
        "async def _ban_lock_and_gate(", "pg_advisory_xact_lock_shared(hashtext(CAST(:sid AS text)))",
        "pg_advisory_xact_lock_shared(hashtext(CAST(:sid AS text) || ':x'))", "(i)"),
    "the lane's constant given another key expression": (
        None, '_IDENTITY_KEY_ARG = "hashtext(CAST(:sid AS text))"',
        "_IDENTITY_KEY_ARG = \"hashtext(CAST(:sid AS text) || ':x')\"", "(iii)"),
}


@pytest.mark.parametrize("name", sorted(_PIN_MUTANTS))
def test_a_mutant_of_the_shared_identity_key_is_named(name, src):
    head, old, new, half = _PIN_MUTANTS[name]
    text = _main_text()
    if head is None:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    else:
        text = _in_function(text, head, old, new)
    bad = _identity_pin_failures(text, src)
    assert any(b.startswith(half) for b in bad), bad


# A route that takes the identity key, then the portrait blob's key, then
# writes the player's row (KEY), and a site reached from one entry alone.
_KEY_ROUTE = "async def admin_pc_portrait_clear("
_KEY_LINE = ('    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(CAST(:sid AS text)))"), '
             '{"sid": steam_id})\n')
_ENTRY_PLANT = '''

@app.post("/mdpl-plant-entry")
async def mdpl_plant_entry(outcome: str, db: AsyncSession = Depends(get_db)):
    await _pc_steam_write(db, {}, outcome)
'''


def _in_function(text, head, old, new):
    """`old` replaced by `new`, where it occurs once inside the function `head` opens."""
    i = text.index(head)
    end = min(x for x in (text.find("\nasync def ", i + 1), text.find("\ndef ", i + 1),
                          text.find("\n@app.", i + 1), len(text)) if x > 0)
    assert text.count(old, i, end) == 1, (head, old)
    j = text.index(old, i)
    return text[:j] + new + text[j + len(old):]


def _site(frozen, prefix):
    (k,) = [k for k in frozen["sites"] if k.startswith(prefix)]
    return k


def _record(d):
    return {f: (sorted(d[f]) if isinstance(d[f], list) else d[f]) for f in mc.COMPARED}


@pytest.fixture(scope="module")
def mutated():
    with open(os.path.join(mc.API, "main.py"), encoding="utf-8") as fh:
        text = fh.read()
    text = _in_function(text, _KEY_ROUTE, _KEY_LINE, "    pass\n") + _ENTRY_PLANT
    return mc.Source(main_text=text)


def test_a_route_that_drops_its_identity_key_changes_its_site_s_class(frozen, src, mutated):
    site = _site(frozen, "_pc_clear_portrait_unit | SELECT pc_game_portrait_hash, pc_steam_portrait_hash FROM")
    fz = frozen["sites"][site]
    assert fz["class"] == "KEY" and fz["entries"] == ["admin_pc_portrait_clear"], fz
    _s1, same = mc.sites(src, entries=fz["entries"])                 # the control
    assert _record(same[site]) == _record(fz), (same[site], fz)
    _s1, got = mc.sites(mutated, entries=fz["entries"])
    assert got[site]["class"] == "READ", got[site]      # holds the blob key, unkeyed: red at the comparison
    assert fz["fallback"] == "READ"                     # the class the frozen record says it has without its key


def test_a_new_entry_at_a_frozen_site_moves_its_record(frozen, src, mutated):
    site = _site(frozen, "_pc_steam_write | UPDATE players SET pc_steam_portrait_hash = CAST(:h AS text)")
    fz = frozen["sites"][site]
    _s1, same = mc.sites(src, entries=fz["entries"])                 # the control
    assert _record(same[site]) == _record(fz), (same[site], fz)
    _s1, got = mc.sites(mutated, entries=fz["entries"] + ["mdpl_plant_entry"])
    assert sorted(got[site]["entries"]) == sorted(fz["entries"] + ["mdpl_plant_entry"]), got[site]
    assert got[site]["class"] == fz["class"], got[site]  # the entry alone moved: red at the comparison


# STACK-SEAM-1: the judgements this lane owes. A site whose "why" opens with
# "OWED under " is one the census marks as not covered, with the work it waits
# for named in the sentence. The set is fixed here, by key.
OWED_SITES = frozenset({
    "_qapply_credit | SELECT 1 FROM players WHERE id = :pid FOR NO KEY UPDATE | 0",
    "_qapply_credit | UPDATE players SET gold_earned = COALESCE(gold_earned, 0) + CAST(:g AS i | 0",
    "_qapply_credit | UPDATE players SET total_xp = COALESCE(total_xp, 0) + CAST(:xp AS intege | 0",
})
_OWED_HEAD = "OWED under "


def _owed_failures(frozen):
    """The site keys whose "why" opens with "OWED under ", against OWED_SITES, both ways."""
    got = {k for k, d in frozen["sites"].items() if d.get("why", "").startswith(_OWED_HEAD)}
    out = [f"{k}: an owed judgement not in OWED_SITES" for k in sorted(got - OWED_SITES)]
    out += [f"{k}: in OWED_SITES and its why no longer opens with {_OWED_HEAD!r}"
            for k in sorted(OWED_SITES - got)]
    return out


_OWED_MSG = ("STACK-SEAM-1: the owed judgements of mdpl_census_frozen.json are exactly OWED_SITES. "
             "An owed judgement is added or taken out only by a change of this test.")


def test_the_owed_judgements_are_the_listed_ones(frozen):
    """STACK-SEAM-1. The credit route of the quarantine (POST
    /api/v1/admin/quarantine/{qid}/credit, _qapply_credit) writes a credited
    player's row without that player's identity key; the census judges its
    three sites OWED. This test holds that set fixed, and the PIN test below
    holds the precondition the owed sentence names: no shipped control builds
    the credit path."""
    bad = _owed_failures(frozen)
    assert not bad, (_OWED_MSG, bad)


def test_a_planted_fourth_owed_judgement_is_named(frozen):
    """Control: an "OWED under" why on another site turns the check red."""
    d = copy.deepcopy(frozen)
    k = _site(d, "booster_grant | UPDATE players SET gold_earned")
    assert k not in OWED_SITES
    d["sites"][k]["why"] = _OWED_HEAD + "STACK-SEAM-1, planted by the control"
    assert _owed_failures(d) == [f"{k}: an owed judgement not in OWED_SITES"]


def test_an_owed_judgement_rewritten_is_named(frozen):
    """Control: one of the three with its why changed turns the check red."""
    d = copy.deepcopy(frozen)
    k = sorted(OWED_SITES)[0]
    d["sites"][k]["why"] = "covered, rewritten by the control"
    assert _owed_failures(d) == [f"{k}: in OWED_SITES and its why no longer opens with {_OWED_HEAD!r}"]


PLUGIN = os.path.normpath(os.path.join(HERE, "..", "..", "plugin"))
_HOLE = "\x00"   # an interpolation hole, in a literal's text
_CREDIT_END = re.compile(r"/credit(?=$|[?/\x00])")   # \x00 is _HOLE: a hole right after /credit


def _cs_skip_char(t, i):
    """t[i] == "'": the index after the C# character literal that starts there."""
    i += 1
    if t[i:i + 1] == "\\":
        i += 2
    while i < len(t) and t[i] != "'":
        i += 1
    return i + 1


def _cs_literal(t, i, lits):
    """t[i:] opens a string literal ("...", @"...", $"...", $@"..." or @$"...").
    Appends (offset, text) for it and for every literal nested in its holes
    (a hole's text is _HOLE in its own literal's text); returns the index
    after its closing quote."""
    start, j = i, i
    verbatim = interp = False
    while t[j] in "@$":
        verbatim |= t[j] == "@"
        interp |= t[j] == "$"
        j += 1
    assert t[j] == '"', (t[start:start + 20])
    # @ and then three quotes opens a verbatim literal whose text starts with a
    # quote (plugin/ApiClient.cs's asset match); a C# raw string literal takes no @.
    if not verbatim and t.startswith('"""', j):
        raise AssertionError((f"offset {j}: a C# 11 raw string literal; this reader does not read raw "
                              "string literals and must learn them before this pin is trusted"))
    j += 1
    buf = []
    while j < len(t):
        c = t[j]
        if c == "\\" and not verbatim:
            buf.append(t[j:j + 2])
            j += 2
        elif c == '"':
            if verbatim and t[j + 1:j + 2] == '"':
                buf.append('"')
                j += 2
            else:
                lits.append((start, "".join(buf)))
                return j + 1
        elif interp and c in "{}" and t[j + 1:j + 2] == c:
            buf.append(c)
            j += 2
        elif interp and c == "{":
            j = _cs_hole(t, j + 1, lits)
            buf.append(_HOLE)
        else:
            buf.append(c)
            j += 1
    raise AssertionError(("an unclosed string literal", t[start:start + 40]))


def _cs_hole(t, j, lits):
    """t[j:] is the code of an interpolation hole; returns the index after its closing brace."""
    depth = 0
    while j < len(t):
        c = t[j]
        if c == '"' or (c in "@$" and t[j + 1:j + 3].lstrip("@$")[:1] == '"'):
            j = _cs_literal(t, j, lits)
        elif c == "'":
            j = _cs_skip_char(t, j)
        elif c == "{":
            depth += 1
            j += 1
        elif c == "}":
            if depth == 0:
                return j + 1
            depth -= 1
            j += 1
        else:
            j += 1
    raise AssertionError(("an unclosed interpolation hole", t[j - 40:j]))


def _cs_statements(t):
    """Every statement of C# text t (the text up to its ";", outside literals
    and comments) that holds a literal: a list of [(offset, literal text)]."""
    out, lits, i, n = [], [], 0, len(t)
    at_line_start = True
    while i < n:
        c = t[i]
        if t.startswith("//", i) or (at_line_start and c == "#"):
            i = t.find("\n", i)
            i = n if i < 0 else i
        elif t.startswith("/*", i):
            i = t.find("*/", i + 2)
            i = n if i < 0 else i + 2
        elif c == '"' or (c in "@$" and t[i + 1:i + 3].lstrip("@$")[:1] == '"'):
            i = _cs_literal(t, i, lits)
        elif c == "'":
            i = _cs_skip_char(t, i)
        elif c == ";":
            if lits:
                out.append(lits)
            lits = []
            i += 1
        else:
            i += 1
        if i < n:
            at_line_start = (t[i - 1] == "\n") or (at_line_start and t[i - 1] in " \t")
    if lits:
        out.append(lits)
    return out


def _credit_path_trips(t):
    """The statements of C# text t that build the quarantine's credit path:
    one statement holds a literal containing "admin/quarantine" and a literal
    (the same or another) in which "/credit" ends it or is followed by "?",
    "/" or a hole. A list of (line, the literal that holds /credit)."""
    out = []
    for lits in _cs_statements(t):
        if not any("admin/quarantine" in s for _o, s in lits):
            continue
        for off, s in lits:
            if _CREDIT_END.search(s):
                out.append((t.count("\n", 0, off) + 1, s))
    return out


def _plugin_cs_files():
    for root, _dirs, files in os.walk(PLUGIN):
        for f in sorted(files):
            if f.endswith(".cs"):
                yield os.path.join(root, f)


def _cs_text(path):
    with open(path, encoding="utf-8-sig") as fh:   # text mode: CRLF reads as LF
        return fh.read()


# The shipped statements, copied from plugin/ApiClient.cs (discard :8492-8493, accept :8506-8507).
_SHIPPED_DISCARD = ('            string url = $"{baseUrl}/api/v1/admin/quarantine/"\n'
                    '                       + $"{UnityWebRequest.EscapeURL(reportId ?? "")}/discard";')
_SHIPPED_ACCEPT = ('            string url = $"{baseUrl}/api/v1/admin/quarantine/"\n'
                   '                       + $"{UnityWebRequest.EscapeURL(reportId ?? "")}/accept";')


def test_no_shipped_control_builds_the_credit_path():
    """STACK-SEAM-1, the PIN. The owed judgements of _qapply_credit rest on
    the credit route answering an admin's request alone: no control in the
    plugin builds POST /api/v1/admin/quarantine/{qid}/credit. A C# literal
    reader over every .cs file under plugin/ ("...", @"...", $"...", $@"...",
    literals nested in a hole; comments skipped) trips on a statement that
    holds "admin/quarantine" and a literal ending in "/credit" (or "/credit"
    then "?", "/" or a hole). Its limit: it sees literals within one statement, so a
    path built from a variable that holds "credit" is not seen; the item's
    precondition stays a reading at the lane that builds the control."""
    found = []
    for path in _plugin_cs_files():
        for line, lit in _credit_path_trips(_cs_text(path)):
            found.append(f"{os.path.relpath(path, os.path.dirname(PLUGIN))}:{line}: {lit!r}")
    assert not found, ("STACK-SEAM-1: a plugin statement builds the quarantine's credit path; "
                       "the owed judgements of _qapply_credit must be met first", found)


def test_the_pin_reads_the_shipped_accept_statement_as_no_credit_path():
    """Control 1: the shipped accept statement does not trip (and is the shipped one)."""
    assert _SHIPPED_ACCEPT in _cs_text(os.path.join(PLUGIN, "ApiClient.cs"))
    lits = _cs_statements(_SHIPPED_ACCEPT)
    assert [s for _o, s in lits[0]] == [_HOLE + "/api/v1/admin/quarantine/", "", _HOLE + "/accept"]
    assert _credit_path_trips(_SHIPPED_ACCEPT) == []


def test_the_pin_reads_the_shipped_discard_statement_as_no_credit_path():
    """Control 2: the shipped discard statement, with its nested literal, does not trip."""
    assert _SHIPPED_DISCARD in _cs_text(os.path.join(PLUGIN, "ApiClient.cs"))
    assert _credit_path_trips(_SHIPPED_DISCARD) == []


def test_the_pin_trips_on_a_composed_credit_statement():
    """Control 3: the shipped accept statement with accept made credit, its nested hole kept."""
    t = _SHIPPED_ACCEPT.replace("}/accept\"", "}/credit\"")
    assert t != _SHIPPED_ACCEPT
    assert _credit_path_trips(t) == [(2, _HOLE + "/credit")]


def test_the_pin_trips_on_an_interpolated_credit_statement():
    """Control 4: one $"..." literal holding both, with a hole that holds a nested literal."""
    t = 'string url = $"{baseUrl}/api/v1/admin/quarantine/{UnityWebRequest.EscapeURL(reportId ?? "")}/credit";'
    assert _credit_path_trips(t) == [(1, _HOLE + "/api/v1/admin/quarantine/" + _HOLE + "/credit")]


def test_the_pin_trips_on_a_composed_credit_statement_with_a_query():
    """Control 5: a composed credit statement with a query string."""
    t = _SHIPPED_ACCEPT.replace("}/accept\"", "}/credit?x=1\"")
    assert t != _SHIPPED_ACCEPT
    assert _credit_path_trips(t) == [(2, _HOLE + "/credit?x=1")]


def test_the_pin_trips_on_a_credit_path_followed_by_a_hole():
    """Control 6: "/credit" with a hole right after it (a query string built in the hole)."""
    t = 'string url = $"{baseUrl}/api/v1/admin/quarantine/{id}/credit{qs}";'
    assert _credit_path_trips(t) == [(1, _HOLE + "/api/v1/admin/quarantine/" + _HOLE + "/credit" + _HOLE)]


def test_the_pin_reader_refuses_a_raw_string_literal():
    """Control 7: a C# 11 raw string literal stops the reader rather than being misread."""
    with pytest.raises(AssertionError):
        _cs_statements('var s = """raw""";')


# The shipped statement, copied from plugin/ApiClient.cs (:2773; :2788 is its .zip twin).
_SHIPPED_VERBATIM = r'var matches = Regex.Matches(json, @"""browser_download_url""\s*:\s*""([^""]+\.dll)""");'


def test_the_pin_reads_a_verbatim_literal_that_opens_with_a_quote():
    """Control 8: a verbatim literal whose text opens with an escaped quote
    (@ and then three quotes, as in the shipped statement) is read as one
    literal, and is not refused as a raw string literal, which takes no @."""
    assert _SHIPPED_VERBATIM in _cs_text(os.path.join(PLUGIN, "ApiClient.cs"))
    lits = _cs_statements(_SHIPPED_VERBATIM)
    assert [s for _o, s in lits[0]] == [r'"browser_download_url"\s*:\s*"([^"]+\.dll)"']
    assert _credit_path_trips(_SHIPPED_VERBATIM) == []
