"""Round 11, FIX-R11-CAT (ruling FOUR-R10-A2 (3)): the catalog diff compares
every row a position can reach, whole, and an explanation binds to the
changed object AND to its event. The round-10 report's three findings:

  F1 test_r7_catalog_diff_pg.py:466  a chain reading read only the rows
     inside catalog_all.RESTRICT, so a migration's ALTER ROLE on another
     role (or ALTER DATABASE on another database) changed no reading;
  F2 catalog_all.py:416  an added sibling column explained an existing
     column's cleared atthasmissing ('attribute' bound by relation);
  F3 catalog_all.py:806  outside() filtered rows with datconnlimit -2, and
     outside_diff() discounted the disappearance, so a position's own
     UPDATE of pg_database to -2 was no change.

Every case here runs on a scratch clone of the template (no chain build):
the seat form of each finding runs under any measurer that may CREATE
DATABASE; the literal form of F1, F2 and F3 (a superuser's ALTER ROLE on an
rf10_* role, direct catalog UPDATEs) runs on 55432 and, under a measurer
that is not a superuser, asserts PostgreSQL's refusal or skips with the
round-10 SEAT_SKIP reason. The legitimate migration shapes (a column
addition, two rewrites, a column drop) are the positive controls.
"""

import asyncio
import datetime
import os

import pytest

import catalog_all as ca
import catalog_diff as cd
import test_r7_catalog_diff_pg as r7

asyncpg = r7.asyncpg

T = "public.rf11_t"
SETUP = ("CREATE TABLE public.rf11_t (id int PRIMARY KEY, keep int);"
         "INSERT INTO public.rf11_t VALUES (1, 1), (2, 2);"
         # a fast default: rf11_old's pg_attribute row has atthasmissing true
         "ALTER TABLE public.rf11_t ADD COLUMN rf11_old int DEFAULT 5;")
ADDITION = "ALTER TABLE public.rf11_t ADD COLUMN rf11_cover int DEFAULT 7"
REWRITES = ("ALTER TABLE public.rf11_t ALTER COLUMN keep TYPE bigint",
            "ALTER TABLE public.rf11_t ADD COLUMN rf11_vol timestamptz DEFAULT clock_timestamp()")
DROP = "ALTER TABLE public.rf11_t DROP COLUMN rf11_old"


def _stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")


def _name(tag):
    prefix = os.environ.get("D2_DB_PREFIX", "d2catalog")
    return ("%s_%s_%s_%d" % (prefix, tag, _stamp(), os.getpid())).lower()[:63]


async def _exec(dsn, sql):
    conn = await r7._connect(dsn)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def _val(dsn, sql, *args):
    conn = await r7._connect(dsn)
    try:
        return await conn.fetchval(sql, *args)
    finally:
        await conn.close()


@pytest.fixture(scope="module")
def r11_db():
    """A clone of the template carrying rf11_t (SETUP), dropped after."""
    db = r7._scratch_clone("r11c")
    try:
        asyncio.run(_exec(r7._dsn(db), SETUP))
        yield r7._dsn(db)
    finally:
        asyncio.run(r7._drop_db(db))


@pytest.fixture
def other():
    """(name, oid) of another database the measurer creates (and so owns),
    dropped after."""
    r7._require()
    name = _name("r11o")
    oid = asyncio.run(r7._clone_with_oid(name, "template1"))
    try:
        yield name, str(oid)
    finally:
        asyncio.run(r7._drop_db(name))


def _whole(rows, key, ident):
    return [r for r in rows if r[0] == "raw" and r[2] == key and r[5][1] == ident]


def _with(row, changes, phys=None):
    """row with the named columns set (fields re-rendered as record_out
    would) and, when given, its '&' physical mark replaced."""
    key = row[2].split("/")[0]
    cols = ca.BODY_COLUMNS[key]
    f = ca.fields(row[3])
    assert ca.changed_columns(key, row[3], r7._r10_row_text(f)) == [], (row[3], r7._r10_row_text(f))
    for c, v in changes.items():
        f[cols.index(c)] = v
    cand = row[5]
    if phys is not None:
        cand = tuple(c for c in cand if c[:1] != "&") + ("&" + phys,)
    return row[:3] + (r7._r10_row_text(f),) + row[4:5] + (cand,)


def _pairs(u):
    return sorted((x[0], x[1]) for x in u)


# --- F1: the chain reads every shared row ----------------------------------


async def _apply(dsn, path):
    before = await r7._snap(dsn)
    outcome = cd.apply_file(cd.client("D2_TEST_PSQL", "psql"), dsn, path)
    after = await r7._snap(dsn)
    return outcome, cd.diff(before, after)


def _migration(tmp_path, text):
    path = os.path.join(str(tmp_path), "r11_migration.sql")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def test_r11_cat_f1_chain_reading_sees_another_database(r11_db, other, tmp_path):
    """A migration (psql, as the chain applies one) that changes ANOTHER
    database the measurer owns: its role-independent setting
    (pg_db_role_setting, setdatabase = that database, setrole 0), its
    connection limit (its pg_database row) and its comment
    (pg_shdescription). Round 10's chain reading kept none of these rows
    (RESTRICT: this database, this role); the whole reading (_snap) shows
    each as a cluster row and an unexplained row."""
    name, oid = other
    path = _migration(tmp_path, 'ALTER DATABASE "%s" SET application_name = \'r11_probe\';\n'
                                'ALTER DATABASE "%s" CONNECTION LIMIT 3;\n'
                                'COMMENT ON DATABASE "%s" IS \'r11 probe\';\n' % (name, name, name))
    outcome, d = asyncio.run(_apply(r11_db, path))
    assert outcome["rc"] == 0, outcome
    cluster = ca.cluster_rows(d)
    print("r11 F1 seat form: cluster rows %s" % [(c[0], c[1], c[2][:80]) for c in cluster])
    keys = {c[1] for c in cluster}
    assert {"pg_db_role_setting", "pg_database", "pg_shdescription"} <= keys, cluster
    assert [c for c in cluster if c[1] == "pg_db_role_setting" and c[0] == "added"
            and c[2].startswith("(%s," % oid) and "application_name=r11_probe" in c[2]], cluster
    unexplained = {u[1] for u in ca.unexplained(d)}
    assert {"pg_db_role_setting", "pg_database", "pg_shdescription"} <= unexplained, ca.unexplained(d)


def test_r11_cat_f1_alter_role_on_another_role(r11_db, tmp_path):
    """The report's literal form: a migration running as a superuser with
    ALTER ROLE <another role> SET application_name. The role is chosen by
    round 10's _plant_decision (an rf10_* role only; a seat administrator
    skips with SEAT_SKIP, 55432 only); the setting is reset in finally and
    the role's settings compared before and after."""
    who = asyncio.run(r7._whoami())
    me = who["admin_user"]
    role = r7._plant_decision(me, who["superuser"], os.environ.get("R10_CAT_ROLE") or "")
    target = "CURRENT_USER" if role == me else '"%s"' % role
    before = asyncio.run(r7._r10_settings(role))
    path = _migration(tmp_path, "ALTER ROLE %s SET application_name = 'r10_probe';\n" % target)
    try:
        outcome, d = asyncio.run(_apply(r11_db, path))
    finally:
        asyncio.run(r7._admin("ALTER ROLE %s RESET application_name" % target))
    assert asyncio.run(r7._r10_settings(role)) == before, before
    assert outcome["rc"] == 0, outcome
    rows = [c for c in ca.cluster_rows(d) if c[1] == "pg_db_role_setting" and "application_name=r10_probe" in c[2]]
    print("r11 F1 literal form, measurer %s, role %s: %s" % (me, role, rows))
    assert rows and rows[0][0] == "added", ca.cluster_rows(d)
    assert [u for u in ca.unexplained(d) if u[1] == "pg_db_role_setting"], ca.unexplained(d)


# --- F2: an explanation binds to its event ---------------------------------


def _measure(dsn, program):
    out = asyncio.run(r7._measure_in(dsn, program, None))
    assert out["refused"] is None and out["ended"] is None, out
    return out


def _old_ident(dsn):
    relid = asyncio.run(_val(dsn, "SELECT 'public.rf11_t'::pg_catalog.regclass::pg_catalog.oid::text"))
    num = asyncio.run(_val(dsn, "SELECT attnum FROM pg_catalog.pg_attribute WHERE attrelid = $1::oid "
                                "AND attname = 'rf11_old'", int(relid)))
    return relid, "%s.%s" % (relid, num)


def test_r11_cat_f2_controls_are_explained(r11_db):
    """The legitimate shapes, each in a rolled-back position: a column
    addition (its own rows added whole; relnatts by the addition), two
    rewrites (a column type change and a volatile default: the table's
    relfilenode changes, and rf11_old's stored missing value is cleared
    t -> f in place, explained by the proven rewrite), and rf11_old's own
    drop (its missing value cleared with it). Nothing is unexplained."""
    relid, old = _old_ident(r11_db)
    got = {}
    for name, program in (("addition", ADDITION), ("rewrite_type", REWRITES[0]),
                          ("rewrite_volatile", REWRITES[1]), ("drop", DROP)):
        out = _measure(r11_db, program)
        u = ca.unexplained(out["diff"])
        moved = [r for r in out["diff"]["added"] + out["diff"]["removed"]
                 if r[0] == "raw" and r[2] == ca.STORAGE_KEY and r[5][1] == relid]
        pair = _whole(out["diff"]["added"], "pg_attribute", old) and _whole(out["diff"]["removed"],
                                                                             "pg_attribute", old)
        changed = ca.changed_columns("pg_attribute", _whole(out["diff"]["removed"], "pg_attribute", old)[0][3],
                                     _whole(out["diff"]["added"], "pg_attribute", old)[0][3]) if pair else []
        got[name] = (u, bool(moved), changed)
        print("r11 F2 control %s: unexplained %d, relfilenode moved %s, rf11_old changed %s"
              % (name, len(u), bool(moved), changed))
    assert all(v[0] == [] for v in got.values()), {k: v[0] for k, v in got.items()}
    assert got["addition"][1:] == (False, []), got["addition"]
    for name in ("rewrite_type", "rewrite_volatile"):
        assert got[name][1] and {"atthasmissing", "attmissingval"} <= set(got[name][2]), (name, got[name])
    assert "attisdropped" in got["drop"][2] and "atthasmissing" in got["drop"][2], got["drop"]


def test_r11_cat_f2_cleared_missing_beside_an_addition(r11_db):
    """The report's case on real rows: beside the added column rf11_cover,
    rf11_old's pg_attribute row changed in place from atthasmissing t to f
    (attmissingval to NULL), with no rewrite of the table. Round 10 bound
    the change to ANY attribute change on the relation, so the sibling
    addition explained it; now it is unexplained (both sides). The same
    change with the table's relfilenode moved (a proven rewrite) is
    explained, and the opposite transition (f -> t) is refused even then."""
    relid, old = _old_ident(r11_db)
    out = _measure(r11_db, ADDITION)
    assert ca.unexplained(out["diff"]) == [], ca.unexplained(out["diff"])
    mine = _whole(out["after"], "pg_attribute", old)
    assert mine, ("no pg_attribute raw row of rf11_old", old)
    cols = ca.BODY_COLUMNS["pg_attribute"]
    f = ca.fields(mine[0][3])
    assert f[cols.index("atthasmissing")] == "t" and f[cols.index("attmissingval")], mine[0][3]
    cleared = [_with(r, {"atthasmissing": "f", "attmissingval": None}) for r in mine]
    base = out["diff"]
    case = {"added": base["added"] + cleared, "removed": base["removed"] + mine}
    got = ca.unexplained(case)
    print("r11 F2 cleared beside an addition: %s" % [(x[0], x[1], x[2][:60]) for x in got])
    assert _pairs(got) == [("added", "pg_attribute"), ("removed", "pg_attribute")], got
    storage = [r for r in out["after"] if r[0] == "raw" and r[2] == ca.STORAGE_KEY and r[5][1] == relid]
    assert len(storage) == 1, storage
    moved = storage[0][:3] + ("(%s,999999999)" % relid,) + storage[0][4:]
    proven = {"added": case["added"] + [moved], "removed": case["removed"] + storage}
    assert ca.unexplained(proven) == [], ca.unexplained(proven)
    backwards = {"added": base["added"] + mine + [moved], "removed": base["removed"] + cleared + storage}
    assert _pairs(ca.unexplained(backwards)) == [("added", "pg_attribute"), ("removed", "pg_attribute")], \
        ca.unexplained(backwards)


def test_r11_cat_f2_direct_update_beside_an_addition(r11_db):
    """The literal form: ADD COLUMN rf11_cover, then a direct UPDATE of
    rf11_old's pg_attribute row (atthasmissing false, attmissingval NULL),
    in a rolled-back position. A superuser's run shows the row unexplained;
    any other measurer is refused (42501)."""
    who = asyncio.run(r7._whoami())
    out = asyncio.run(r7._measure_in(
        r11_db, ADDITION + "; UPDATE pg_catalog.pg_attribute SET atthasmissing = false, attmissingval = NULL "
                           "WHERE attrelid = 'public.rf11_t'::pg_catalog.regclass AND attname = 'rf11_old'", None))
    print("r11 F2 literal form, superuser %s: refused %s" % (who["superuser"], out["refused"]))
    if not who["superuser"]:
        assert out["refused"] == "42501", out
        return
    assert out["refused"] is None and out["ended"] is None, out
    _relid, old = _old_ident(r11_db)
    got = [u for u in ca.unexplained(out["diff"]) if u[1] == "pg_attribute"]
    assert sorted(u[0] for u in got) == ["added", "removed"], got


def test_r11_cat_sweep_relnatts_and_owner_events(r11_db):
    """The class sweep (round 11 NOTES): relnatts is explained by an
    attribute ADDED on its relation, not by any attribute change there; a
    relation's relacl changed in place without an ACL object is explained
    by its owner event (its class object's owner), not by any change of its
    class object."""
    relid, _old = _old_ident(r11_db)
    out = _measure(r11_db, ADDITION)
    d = out["diff"]
    added_attr = [o for o in d["added"] if o[0] == "attribute" and o[4].startswith(relid + ".")]
    assert added_attr, [o[:2] for o in d["added"] if o[0] != "raw"]
    # the addition's attribute object replaced by an attribute changed in place
    keep = [o for o in out["after"] if o[0] == "attribute" and o[4] == relid + ".2"]
    assert len(keep) == 1, keep
    renamed = keep[0][:3] + (keep[0][3] + " r11",) + keep[0][4:]
    swapped = {"added": [r for r in d["added"] if r not in added_attr] + [renamed],
               "removed": d["removed"] + keep}
    pg_class = [x for x in ca.unexplained(swapped) if x[1] == "pg_class"]
    assert _pairs(pg_class) == [("added", "pg_class"), ("removed", "pg_class")], pg_class
    # relacl changed in place on the table's own pg_class row
    row = _whole(out["after"], "pg_class", relid)
    obj = [o for o in out["after"] if o[0] == "class" and o[4] == relid]
    assert row and len(obj) == 1 and " owner=" in " " + obj[0][3], (row, obj)
    acl = [_with(r, {"relacl": "{r11_x=r/r11_x}"}) for r in row]
    other_change = obj[0][:3] + (obj[0][3].replace("options=", "options={fillfactor=50}", 1),) + obj[0][4:]
    owner = obj[0][3].split("owner=", 1)[1].split(" replident=", 1)[0]
    owner_change = obj[0][:3] + (obj[0][3].replace("owner=" + owner, "owner=r11_new_owner", 1),) + obj[0][4:]
    for label, o_new, want in (("class changed, not its owner", other_change,
                                [("added", "pg_class"), ("removed", "pg_class")]),
                               ("owner changed", owner_change, [])):
        case = {"added": [acl[0], o_new], "removed": [row[0], obj[0]]}
        got = ca.unexplained(case)
        print("r11 sweep relacl, %s: %s" % (label, _pairs(got)))
        assert _pairs(got) == want, (label, got)


# --- F3: a row that appears or disappears is a change -----------------------


async def _position_outside(program=None, other_drop=None):
    """One REPEATABLE READ position on the admin database: outside() read,
    `program` run, database `other_drop` dropped by ANOTHER backend,
    outside() read again; rolled back. (before, after, refusal SQLSTATE)."""
    conn = await asyncpg.connect(r7.ADMIN)
    refused = None
    try:
        tr = conn.transaction(isolation="repeatable_read")
        await tr.start()
        try:
            before = await ca.outside(conn)
            if program:
                try:
                    await conn.execute(program)
                except asyncpg.PostgresError as e:
                    refused = e.sqlstate
                    return before, None, refused
            if other_drop:
                await r7._drop_db(other_drop)
            return before, await ca.outside(conn), refused
        finally:
            await tr.rollback()
    finally:
        await conn.close()


def test_r11_cat_f3_disappearance_and_new_tuples_are_changes(other):
    """outside_diff() on a real outside() reading of a position, with the
    other database's pg_database row (its oid identity, its ctid '&'):
    removed (a disappearance: round 10 discounted it), changed to -2 at a
    new ctid (an MVCC write), changed to 5 at the same ctid, changed to -2
    with datallowconn too, or a new row beside it: each is a change. Only
    the one permitted shape, -2 at the same ctid, is discounted."""
    name, oid = other
    before, _after, _ref = asyncio.run(_position_outside())
    row = _whole(before, "pg_database", oid)
    assert len(row) == 1 and [c for c in row[0][5] if c[:1] == "&"], row
    phys = [c[1:] for c in row[0][5] if c[:1] == "&"][0]
    allow = ca.fields(row[0][3])[ca.BODY_COLUMNS["pg_database"].index("datallowconn")]
    cases = {
        "removed": (before - set(row), ["pg_database"]),
        "-2 new tuple": ((before - set(row)) | {_with(row[0], {"datconnlimit": "-2"}, "(99999,1)")},
                         ["pg_database"]),
        "5 same tuple": ((before - set(row)) | {_with(row[0], {"datconnlimit": "5"}, phys)}, ["pg_database"]),
        "-2 and datallowconn": ((before - set(row)) | {_with(row[0], {"datconnlimit": "-2",
                                                                      "datallowconn": "f" if allow == "t" else "t"},
                                                             phys)}, ["pg_database"]),
        "a new row": (before | {_with(row[0], {"datname": name + "_x"}, "(99999,2)")[:5]
                                + (("RAW", "4294967000", "shared", "@4294967000", "&(99999,2)",
                                    ca.OUTSIDE_MARK),)}, ["pg_database"]),
        "-2 same tuple (in place)": ((before - set(row)) | {_with(row[0], {"datconnlimit": "-2"}, phys)}, []),
    }
    got = {k: sorted(ca.keys(ca.outside_diff(before, after))) for k, (after, _w) in cases.items()}
    print("r11 F3 outside_diff cases: %s" % got)
    assert got == {k: w for k, (_a, w) in cases.items()}, got


def test_r11_cat_f3_another_backends_drop_is_one_tuple(other):
    """The positive control, real: another backend drops a database inside
    the position. The reading is not filtered: the row is there at the end
    with datconnlimit -2 and the ctid it had at the start (an in-place
    update), the plain set difference names pg_database, outside_diff()
    nothing."""
    name, oid = other
    before, after, _ref = asyncio.run(_position_outside(other_drop=name))
    b, a = _whole(before, "pg_database", oid), _whole(after, "pg_database", oid)
    print("r11 F3 drop by another backend: before %s after %s" % ([r[3][:60] for r in b], [r[3][:60] for r in a]))
    assert len(b) == 1 and len(a) == 1, (b, a)
    cols = ca.BODY_COLUMNS["pg_database"]
    assert ca.fields(a[0][3])[cols.index("datconnlimit")] == "-2", a[0][3]
    assert [c for c in a[0][5] if c[:1] == "&"] == [c for c in b[0][5] if c[:1] == "&"], (a[0][5], b[0][5])
    assert sorted(ca.keys({"added": sorted(after - before), "removed": sorted(before - after)})) == ["pg_database"]
    assert ca.keys(ca.outside_diff(before, after)) == {}, ca.outside_diff(before, after)


def test_r11_cat_f3_direct_update_of_another_database(other):
    """The report's literal form: inside a position, UPDATE pg_database SET
    datconnlimit = -2 for another database (rolled back). Round 10's
    reading filtered the -2 row out and outside_diff() discounted the
    disappearance; now the position's own new tuple is a change. Under a
    measurer that is not a superuser PostgreSQL refuses it (42501)."""
    name, oid = other
    who = asyncio.run(r7._whoami())
    before, after, refused = asyncio.run(_position_outside(
        "UPDATE pg_catalog.pg_database SET datconnlimit = -2 WHERE oid = %s" % oid))
    print("r11 F3 literal form, superuser %s: refused %s" % (who["superuser"], refused))
    if not who["superuser"]:
        assert refused == "42501", refused
        return
    assert refused is None
    assert sorted(ca.keys(ca.outside_diff(before, after))) == ["pg_database"], ca.outside_diff(before, after)
