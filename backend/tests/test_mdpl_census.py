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
widening: with its six switches off it computes mdpl_census_base.json, the
census frozen before the widening, exactly. The foreign keys that migrations
drop by dynamic SQL are read from each migration's own lookup. The reader
holds a plain INSERT without a wait; that the deletion's plain inserts cannot
wait (gold_transactions alone, keyed by its generated id) is read here too.

Pure Python: no database. Refreeze after a reviewed change with
`python mdpl_census.py --freeze` (it keeps every judgement and writes an
empty one for a new READ site, which this test refuses).
"""
import ast
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
    switch the module has, so a new one is turned off here too."""
    assert set(mc.SWITCHES) == {n for n in vars(mc) if n.isupper() and isinstance(vars(mc)[n], bool)}
    for name in mc.SWITCHES:
        monkeypatch.setattr(mc, name, False)
    m = mc.measured(mc.Source())
    with open(mc.BASE, encoding="utf-8") as fh:
        base = json.load(fh)
    assert m["step1"] == base["step1"]
    got = {k: {f: d[f] for f in mc.BASE_FIELDS} for k, d in m["sites"].items()}
    new = sorted(set(got) - set(base["sites"]))
    gone = sorted(set(base["sites"]) - set(got))
    moved = sorted(k for k in set(got) & set(base["sites"]) if got[k] != base["sites"][k])
    assert not new and not gone and not moved, {
        "new": new[:10], "gone": gone[:10], "moved": [(k, base["sites"][k], got[k]) for k in moved[:5]]}
    assert m["unread"] == base["unread"]
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
