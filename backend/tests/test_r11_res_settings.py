"""Ruling FOUR-R10-A2 (3) FIX-R11-RES: settings with no pg_settings row.

The read-only bound's residue reading (ro_covered.RESIDUE_SQL) compared
pg_settings at both ends of a position; on PostgreSQL 16.9 (55432, RF11 log
r11-res-probe-55432-20261106T065356Z.log) a custom placeholder the session
set had no pg_settings row, so a session-scope set_config of a placeholder
left the position 'ok' (round-10 report, ro_covered.py:515). The fix, in
ro_covered: the text reading counts every session-scope settings form as
residue (a filter, refusing direction), the names the texts set are read on
the session (the measurement), and every measured position is followed by
RESET ALL and a check that each name reads its reset value by class
(not_reset, ruling FOUR-R11-A6 (2)).

This module holds the parts that need no driver run: the text reading, the
sweep of every production statement that sets a setting, and, on the
cluster CF_TEST_PG_DSN names (never skipped), the pg_settings answer itself,
the GREEN control (a transaction-local set_config inside an ended
transaction leaves nothing) and its session-scope counterpart. The driver
controls (the report's case at main.py:16828 and one control per route) are
in test_r8_ro_covered_pg.py.
"""

import ast
import asyncio
import os
import sys

import asyncpg
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ro_covered  # noqa: E402
import ro_role  # noqa: E402

API_DIR = os.path.join(HERE, "..", "api")
ADMIN_DSN = ro_role.pg_dsn(os.environ.get("CF_TEST_PG_DSN") or "")
NAMED_SQL = ro_covered.NAMED_SETTINGS_SQL.replace(":names", "$1")


# ------------------------------------------------------------ the text reading

# (text, forms, names): the forms the reading counts and the names it reads.
READING = (
    # the round-10 report's text
    ("SELECT set_config('rf10.hidden','yes',false)",
     ("session set_config rf10.hidden",), ("rf10.hidden",)),
    # transaction-local forms: names read, nothing counted by the text
    ("SELECT set_config('lock_timeout', $1, true)", (), ("lock_timeout",)),
    ("SELECT pg_catalog.set_config('rf11res.local', 'v', TRUE)", (), ("rf11res.local",)),
    ("SET LOCAL lock_timeout = '2s'", (), ("lock_timeout",)),
    ("SET TRANSACTION READ ONLY", (), ()),
    ("SET CONSTRAINTS ALL DEFERRED", (), ()),
    # is_local not the literal true: session scope or unknowable
    ("SELECT set_config('a.b', 'v', $2)", ("session set_config a.b",), ("a.b",)),
    ("SELECT set_config('a.b', 'v', 'true')", ("session set_config a.b",), ("a.b",)),
    ("SELECT set_config('a.b', 'v', 1 = 1)", ("session set_config a.b",), ("a.b",)),
    ("SELECT pg_catalog.\"set_config\"('A.B', 'v', false)", ("session set_config a.b",), ("a.b",)),
    ("SELECT x FROM set_config('a.b', 'v', false) AS x", ("session set_config a.b",), ("a.b",)),
    # names no literal carries
    ("SELECT set_config($1, 'v', true)", ("set_config name unreadable",), ()),
    ("SELECT set_config('a.' || 'b', 'v', true)", ("set_config name unreadable",), ()),
    ("SELECT set_config(E'a.b', 'v', true)", ("set_config name unreadable",), ()),
    ("SELECT set_config('a.b', 'v')", ("set_config arguments unreadable",), ()),
    # SET of every non-local scope
    ("SET application_name = 'x'", ("session SET application_name",), ("application_name",)),
    ("SET SESSION lock_timeout TO 5", ("session SET lock_timeout",), ("lock_timeout",)),
    ("set rf11.X = 1", ("session SET rf11.x",), ("rf11.x",)),
    ("SET \"Rf11\".\"Y\" TO 1", ("session SET rf11.y",), ("rf11.y",)),
    ("SET ROLE scr_seat_ro", ("session SET role",), ("role",)),
    ("SET SESSION AUTHORIZATION DEFAULT", ("session SET session_authorization",),
     ("session_authorization",)),
    ("SET TIME ZONE 'UTC'", ("session SET timezone",), ("timezone",)),
    ("SET SCHEMA 'public'", ("session SET search_path",), ("search_path",)),
    ("SET NAMES 'UTF8'", ("session SET client_encoding",), ("client_encoding",)),
    ("SET seed = 0.5", ("session SET seed",), ("seed",)),
    ("SELECT 1; SET work_mem = '1MB'", ("session SET work_mem",), ("work_mem",)),
    ("SELECT setseed(0.5)", ("session setseed",), ()),
    # inside a body, dynamic SQL, a unicode-escaped spelling
    ("DO $$ BEGIN PERFORM set_config('m.x', '1', false); END $$",
     ("session set_config m.x",), ("m.x",)),
    ("DO $b$ BEGIN IF true THEN SET m.y = 1; END IF; END $b$",
     ("session SET m.y",), ("m.y",)),
    ("DO $$ BEGIN EXECUTE 'SET m.z = 1'; END $$", ("dynamic sql",), ()),
    ("SELECT U&\"set\\005fconfig\"('a.b', 'v', false)",
     ("unreadable unicode-escaped spelling",), ()),
    # not settings statements
    ("UPDATE players SET display_name = 'x' WHERE false", (), ()),
    ("INSERT INTO t (a) VALUES (1) ON CONFLICT (a) DO UPDATE SET a = 2", (), ()),
    ("ALTER TABLE t ALTER COLUMN a SET DEFAULT 1", (), ()),
    ("SELECT current_setting('lock_timeout')", (), ()),
    ("SELECT clock_timestamp()", (), ()),
    ("-- SELECT set_config('a.b', 'v', false)\nSELECT 1", (), ()),
    ("SELECT 'set_config(''a.b'', ''v'', false)'", (), ()),
)


@pytest.mark.parametrize("sql,forms,names", READING, ids=[r[0][:48] for r in READING])
def test_r11_res_text_reading(sql, forms, names):
    assert ro_covered.settings_forms([sql]) == (forms, names)


def test_r11_res_text_reading_unions_a_programs_texts():
    """A position's texts are read together: a planted program's statements
    and the production statement."""
    got = ro_covered.settings_forms([
        "SELECT set_config('rf10.hidden','yes',false)", "SELECT clock_timestamp()",
        "SET LOCAL lock_timeout = 1"])
    assert got == (("session set_config rf10.hidden",), ("lock_timeout", "rf10.hidden"))


def _production_settings_texts():
    """Every string constant of backend/api (docstrings aside) that names
    set_config or setseed or begins a SET statement: (file:line, text);
    and the fragments left aside: a constant starting with SET after
    leading whitespace (the SET clause of an UPDATE assembled from pieces)
    or exactly 'SET NULL' (a foreign key's ondelete)."""
    out, fragments = [], []
    for fn in sorted(os.listdir(API_DIR)):
        if not fn.endswith(".py"):
            continue
        with open(os.path.join(API_DIR, fn), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    docs.add(id(first.value))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docs):
                low = node.value.lower()
                where = "%s:%d" % (fn, node.lineno)
                if "set_config" in low or "setseed" in low or node.value.startswith("SET "):
                    if node.value == "SET NULL":
                        fragments.append((where, node.value))
                    else:
                        out.append((where, node.value))
                elif node.value.lstrip().startswith("SET "):
                    fragments.append((where, node.value))
    return out, fragments


def test_r11_res_sweep_production_settings_statements():
    """The sweep: every production statement that sets a setting does so
    transaction-locally with a literal name of a setting pg_settings shows
    (so the existing pg_settings reading measures it); none is a form the
    text reading counts (SET TRANSACTION is this transaction's). The count
    is the sweep of backend/api at 5b18949a (16 statements, listed in
    NOTES-r11-res.md); a new one fails here until judged. Every fragment
    left aside is an UPDATE's SET clause or an ondelete 'SET NULL': its
    first word after SET is followed by '=' or is NULL."""
    got, fragments = _production_settings_texts()
    names = set()
    for where, sql in got:
        forms, ns = ro_covered.settings_forms([sql])
        assert forms == (), (where, sql, forms)
        names |= set(ns)
    assert names == {"lock_timeout", "statement_timeout",
                     "idle_in_transaction_session_timeout"}, names
    assert len(got) == 16, got
    for where, frag in fragments:
        toks = ro_covered.sql_tokens(frag)
        assert toks[0] == ("word", "set"), (where, frag)
        assert toks[1:] in ([("word", "null")], []) or toks[2] == ("punct", "="), (where, frag)


# ------------------------------------------------------- on the cluster itself

def _dsn():
    if not ADMIN_DSN:
        pytest.fail("CF_TEST_PG_DSN is unset: name an admin DSN on the local cluster; "
                    "this module never skips")
    return ADMIN_DSN


def _run(coro):
    return asyncio.run(coro)


async def _rows(conn, names):
    return [tuple(r) for r in await conn.fetch(NAMED_SQL, list(names))]


def test_r11_res_pg_settings_omits_a_session_placeholder():
    """The question the ruling asked, measured on the cluster the suite runs
    on (the VM's 16.9 answer is in NOTES-r11-res.md): a session-scope custom
    placeholder is not in pg_settings nor in pg_show_all_settings();
    current_setting reads it; after RESET ALL it reads '' (defined, at its
    reset value), and a never-defined name reads NULL. One transaction,
    rolled back."""
    async def go():
        conn = await asyncpg.connect(_dsn())
        try:
            tr = conn.transaction()
            await tr.start()
            try:
                never = await conn.fetchval(
                    "SELECT pg_catalog.current_setting('rf11res.never', true)")
                await conn.execute("SELECT pg_catalog.set_config('rf11res.x', '1', false)")
                shown = await conn.fetchval(
                    "SELECT count(*) FROM pg_catalog.pg_settings WHERE name LIKE 'rf11res.%'")
                shown_all = await conn.fetchval(
                    "SELECT count(*) FROM pg_catalog.pg_show_all_settings()"
                    " WHERE name LIKE 'rf11res.%'")
                value = await conn.fetchval(
                    "SELECT pg_catalog.current_setting('rf11res.x', true)")
                await conn.execute(ro_covered.RESET_SQL)
                after = await conn.fetchval(
                    "SELECT pg_catalog.current_setting('rf11res.x', true)")
                version = await conn.fetchval("SHOW server_version_num")
            finally:
                await tr.rollback()
            return never, shown, shown_all, value, after, version
        finally:
            await conn.close()
    never, shown, shown_all, value, after, version = _run(go())
    assert version.startswith("16"), version
    assert (never, shown, shown_all, value, after) == (None, 0, 0, "1", ""), (
        never, shown, shown_all, value, after)


def test_r11_res_local_set_config_in_an_ended_transaction_is_green():
    """The GREEN control: a transaction-local set_config inside a
    transaction that then ended. The text reading counts nothing, the
    placeholder reading finds the value while the transaction lives and
    nothing once it ended, and the reset proof is clean without a RESET."""
    texts = ["SELECT pg_catalog.set_config('rf11res.ended', 'v', true)"]

    async def go():
        conn = await asyncpg.connect(_dsn())
        try:
            async with conn.transaction():
                await conn.execute(texts[0])
                inside = await _rows(conn, ["rf11res.ended"])
            return inside, await _rows(conn, ["rf11res.ended"])
        finally:
            await conn.close()
    inside, after = _run(go())
    assert ro_covered.settings_forms(texts) == ((), ("rf11res.ended",))
    assert ro_covered.placeholder_residue(inside) == ("placeholder rf11res.ended=v",), inside
    assert ro_covered.placeholder_residue(after) == (), after
    assert ro_covered.not_reset(after) == (), after


def test_r11_res_session_set_config_survives_its_transaction_until_reset():
    """The counterpart: the same name set with is_local false survives the
    end of its transaction (session residue): the text reading counts it,
    the placeholder reading finds it, the reset proof names it; RESET ALL
    then returns it to its reset value and the proof is clean."""
    texts = ["SELECT pg_catalog.set_config('rf11res.kept', 'v', false)"]

    async def go():
        conn = await asyncpg.connect(_dsn())
        try:
            async with conn.transaction():
                await conn.execute(texts[0])
            kept = await _rows(conn, ["rf11res.kept"])
            await conn.execute(ro_covered.RESET_SQL)
            return kept, await _rows(conn, ["rf11res.kept"])
        finally:
            await conn.close()
    kept, reset = _run(go())
    assert ro_covered.settings_forms(texts) == (
        ("session set_config rf11res.kept",), ("rf11res.kept",))
    assert ro_covered.placeholder_residue(kept) == ("placeholder rf11res.kept=v",), kept
    assert ro_covered.not_reset(kept) == ("not reset rf11res.kept=v",), kept
    assert ro_covered.not_reset(reset) == (), reset
    assert ro_covered.placeholder_residue(reset) == (), reset


def test_r11_res_hidden_settings_are_read():
    """The settings array carries role, session_authorization and
    is_superuser, which had no pg_settings row on 16.9 (RF11 log
    r11-res-probe2-55432-20261106T090205Z.log), and the connection's
    identity, so a SET ROLE moves the residue reading."""
    async def go():
        conn = await asyncpg.connect(_dsn())
        try:
            tr = conn.transaction()
            await tr.start()
            try:
                sql = ro_covered.RESIDUE_SQL
                before = (await conn.fetchrow(sql))[0]
                me = await conn.fetchval("SELECT session_user")
                await conn.execute('SET ROLE "%s"' % me.replace('"', '""'))
                after = (await conn.fetchrow(sql))[0]
            finally:
                await tr.rollback()
            return list(before), list(after), me
        finally:
            await conn.close()
    before, after, me = _run(go())
    for name in ("role", "session_authorization", "is_superuser", "current_user",
                 "session_user"):
        assert any(x.startswith("hidden %s=" % name) for x in before), (name, before)
    assert "hidden role=none" in before and "hidden role=%s" % me in after, (before, after)
    assert set(ro_covered.residue_changes((tuple(before), 0, 0, 0, 0),
                                          (tuple(after), 0, 0, 0, 0))) == {
        "setting hidden role=%s" % me, "setting hidden role=none"}


def test_r11_res_server_setting_reset_by_reset_val_and_source():
    """Ruling FOUR-R11-A6 (2), the server-setting class: a session-scope SET
    of a setting with a pg_settings row reads source 'session' and is named
    by the reset check; after RESET ALL it reads setting = reset_val with a
    source other than 'session' and the check is clean. The token and a
    placeholder are classed by name."""
    async def go():
        conn = await asyncpg.connect(_dsn())
        try:
            await conn.execute("SET lock_timeout = '1234ms'")
            kept = await _rows(conn, ["lock_timeout"])
            await conn.execute(ro_covered.RESET_SQL)
            return kept, await _rows(conn, ["lock_timeout"])
        finally:
            await conn.close()
    kept, reset = _run(go())
    assert kept[0][5] == "session", kept
    assert ro_covered.not_reset(kept) == ("not reset lock_timeout=1234 (session)",), kept
    assert ro_covered.not_reset(reset) == (), reset
    assert reset[0][2] == reset[0][3] and reset[0][5] != "session", reset
    texts = ["SET lock_timeout = '1s'",
             "SELECT set_config('rf10.position', 'p', false)",
             "SELECT set_config('rf11res.p', 'v', true)"]
    scoped = ro_covered.settings_scoped(texts)
    assert scoped == (("lock_timeout", "session"), ("rf10.position", "session"),
                      ("rf11res.p", "local")), scoped
    assert ro_covered.setting_classes(scoped, kept) == (
        ("lock_timeout", "server", "session"), ("rf10.position", "token", "session"),
        ("rf11res.p", "placeholder", "local"))


def test_r11_res_temporary_function_moves_pg_proc_not_pg_class():
    """A temporary function adds a pg_proc row in the session's temporary
    schema and no pg_class row, and the residue reading's temporary-object
    count moves by it. One transaction, rolled back."""
    async def go():
        conn = await asyncpg.connect(_dsn())
        try:
            tr = conn.transaction()
            await tr.start()
            try:
                await conn.execute("CREATE TEMPORARY TABLE rf11res_t (i int)")
                count_sql = (
                    "SELECT (SELECT count(*) FROM pg_catalog.pg_class"
                    " WHERE relnamespace = pg_catalog.pg_my_temp_schema()),"
                    " (SELECT count(*) FROM pg_catalog.pg_proc"
                    " WHERE pronamespace = pg_catalog.pg_my_temp_schema())")
                before = tuple(await conn.fetchrow(count_sql))
                res_before = tuple(await conn.fetchrow(ro_covered.RESIDUE_SQL))[4]
                await conn.execute(
                    "CREATE FUNCTION pg_temp.rf11res_f() RETURNS int"
                    " LANGUAGE sql AS 'SELECT 1'")
                after = tuple(await conn.fetchrow(count_sql))
                res_after = tuple(await conn.fetchrow(ro_covered.RESIDUE_SQL))[4]
            finally:
                await tr.rollback()
            return before, after, res_before, res_after
        finally:
            await conn.close()
    before, after, res_before, res_after = _run(go())
    assert after[0] == before[0] and after[1] == before[1] + 1, (before, after)
    assert res_after == res_before + 1, (res_before, res_after)


def test_r11_res_proc_census_diff_routes(monkeypatch):
    """Each route of the census diff, on constructed PROC_CENSUS_SQL rows: a
    frozen function whose source changed is named 'md5', a new match 'new',
    a frozen one no longer matched 'gone', a compiled function not frozen
    'compiled new' and a frozen one absent 'compiled gone'; a source carrying
    the token's name is listed; the unchanged census is clean."""
    import hashlib
    src = "BEGIN PERFORM pg_catalog.set_config('a.b', 'v', true); END"
    rows = [
        ("public", "f", "", "f", "plpgsql", src, None, None),
        ("public", "g", "x integer", "f", "c", "g", None, "ext1"),
        ("s1", "t", "", "f", "sql", "SELECT current_setting('rf10.position')", None, None),
    ]
    md5 = hashlib.md5(src.encode("utf-8")).hexdigest()
    monkeypatch.setattr(ro_covered, "PROC_SIDES", {
        "public.f() f": (md5, "transaction", "literal true")})
    monkeypatch.setattr(ro_covered, "PROC_COMPILED", (("ext1", "public.g(x integer) f"),))
    matched, compiled, token = ro_covered.proc_census(rows, "s1")
    assert ro_covered.proc_census_diff(matched, compiled) == ()
    assert token == ("<case>.t() f",), token
    assert matched["public.f() f"][2] == ("set_config",), matched
    changed = [("public", "f", "", "f", "plpgsql", src + " ", None, None)] + rows[1:]
    matched, compiled, _t = ro_covered.proc_census(changed, "s1")
    assert ro_covered.proc_census_diff(matched, compiled) == ("md5 public.f() f",)
    extra = rows + [("public", "h", "", "p", "plpgsql", "BEGIN EXECUTE 'x'; END", None, None),
                    ("public", "k", "", "f", "internal", "k", None, None)]
    matched, compiled, _t = ro_covered.proc_census(extra, "s1")
    assert ro_covered.proc_census_diff(matched, compiled) == (
        "compiled new - public.k() f", "new public.h() p")
    matched, compiled, _t = ro_covered.proc_census(rows[2:], "s1")
    assert ro_covered.proc_census_diff(matched, compiled) == (
        "compiled gone ext1 public.g(x integer) f", "gone public.f() f")
