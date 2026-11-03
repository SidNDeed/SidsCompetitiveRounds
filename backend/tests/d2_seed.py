"""Prerequisites for test_r7_catalog_diff_pg.py: what the harness supplies
before a migration so that the migration runs to its end (ruling
REHEARSAL-FOUR-R7-A1, M11).

The chain in backend/sql was never applied to an empty database in one go.
Some files read tables and columns that only the ORM defines (the api's
create_all made them in production before those files ran), and the data
repairs, releases and seeds check production rows by their own gates and
post-checks. The harness supplies both, under the admin role, right before
the file that needs them, so EVERY numbered file is applied once, whole,
and exits 0. Each prerequisite is its own measured step in the chain (its
catalog diff is attributed to "<prereq NNN>", never to the migration).

PREREQS maps a migration file to its prerequisite steps, in order:

  ("orm", [table, ...])     the model's table (models.Base), created with
                            CREATE TABLE IF NOT EXISTS semantics; a foreign
                            key whose target table does not exist yet is
                            left out (the migration that creates the target
                            runs later in the chain)
  ("widen", table, [col])   the model's column added, nullable, where the
                            table lacks it (test_title_ladder_hooks_live._widen)
  ("sql", text)             fixture rows, run whole as one batch; one per
                            file of d2_seed_data.SEEDS, after the file's
                            orm/widen steps

Nothing here edits a migration or reads a claim from one.
"""
import hashlib
import os
import re

import d2_seed_data

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

PREREQS = {
    # tables and columns only the ORM defines, created right before the
    # first file that reads them
    "020_economy.sql": [("widen", "players", ["total_xp"])],
    "023_bets.sql": [("orm", ["ranked_series"])],
    "031_fix_mapcolors.sql": [("widen", "players", ["active_color_id"])],
    "049_async_tournaments.sql": [("orm", ["tournament_matches"])],
    "051_dismiss_false_afk_flags.sql": [("orm", ["flagged_matches"])],
    "058_fix_lemon_ghelici_phantom_ranked.sql": [("widen", "matches", ["is_ranked", "series_id"])],
    "130_tournament_revote_dms.sql": [("orm", ["tournament_time_votes"])],
}


# Seeds that MOVE rows to other ids (398 and 399 read their shop and
# submission rows by production id, which other chain rows took by sequence):
# table -> the column(s) naming the row whatever its id. Each such seed runs
# under _id_move_guard. Every seed whose text changes an id must be listed
# (asserted below), so a new mover cannot skip the guard.
ID_MOVES = {
    "363_revoke_ffa_shutouts_below_finishing_count.sql": {"player_achievements": ["player_id", "achievement_key"]},
    "398_release_five_faces_v1410.sql": {"shop_items": ["sku"], "cosmetic_submissions": ["shop_sku", "name"]},
    "399_shop_face_descriptions.sql": {"shop_items": ["sku"]},
}
_MOVERS = sorted(n for n, t in d2_seed_data.SEEDS.items() if re.search(r"(?i)\bSET\s+id\s*=", t))
assert _MOVERS == sorted(ID_MOVES), ("seeds that change an id must be in ID_MOVES", _MOVERS)

for _name in sorted(d2_seed_data.SEEDS):
    _step = ("sql", d2_seed_data.SEEDS[_name])
    if _name in ID_MOVES:
        _step = ("sql", d2_seed_data.SEEDS[_name], ID_MOVES[_name])
    PREREQS.setdefault(_name, []).append(_step)


def _file_literal(m):
    """@FILE(path;md5)@ -> the bytea literal of that repo file, md5-checked."""
    path, want = m.group(1), m.group(2)
    data = open(os.path.join(REPO, path), "rb").read()
    got = hashlib.md5(data).hexdigest()
    if got != want:
        raise AssertionError("seed file %s has md5 %s, the seed was written for %s" % (path, got, want))
    return "'\\x%s'" % data.hex()


def expand(text):
    return re.sub(r"@FILE\(([^;()]+);([0-9a-f]{32})\)@", _file_literal, text)


def _cols(cols):
    return ", ".join('"%s"::text' % c for c in cols)


async def _foreign_keys(conn, table):
    """[(name, referencing table, referencing columns, referenced columns,
    cascades on update)] of every foreign key in pg_constraint into <table>."""
    rows = await conn.fetch("""
        SELECT c.conname, c.conrelid::regclass::text AS src, c.confupdtype = 'c' AS cascades,
               ARRAY(SELECT a.attname::text FROM unnest(c.conkey) WITH ORDINALITY k(n, o)
                       JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.n ORDER BY k.o) AS cols,
               ARRAY(SELECT a.attname::text FROM unnest(c.confkey) WITH ORDINALITY k(n, o)
                       JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.n ORDER BY k.o) AS dst
          FROM pg_constraint c
         WHERE c.contype = 'f' AND c.confrelid = $1::regclass
         ORDER BY c.conname""", table)
    return [(r["conname"], r["src"], list(r["cols"]), list(r["dst"]), r["cascades"]) for r in rows]


async def _holders(conn, table, key, ident):
    """{referenced value tuple: identity tuple} of every row of <table>."""
    rows = await conn.fetch('SELECT %s, %s FROM "%s"' % (_cols(key), _cols(ident), table))
    n = len(key)
    return {tuple(r[:n]): tuple(r[n:]) for r in rows}


async def _id_move_guard(conn, text, moves):
    """Run a seed that moves rows to other ids, proving no reference was left
    pointing at a different row. Before the seed: every foreign key
    (pg_constraint) into a moved table, the values its rows reference, and
    which row (by the naming columns in ID_MOVES) holds each referenced
    value. After it: a referenced value is changed when another row, or no
    row, holds it. Each foreign key must cascade on update (its references
    moved with the row) or reference no changed value. Returns, per table,
    the ids whose row changed and the foreign keys read."""
    before = {}
    for table, ident in moves.items():
        fks = []
        for name, src, cols, dst, cascades in await _foreign_keys(conn, table):
            where = " AND ".join('"%s" IS NOT NULL' % c for c in cols)
            held = {tuple(r) for r in await conn.fetch(
                "SELECT DISTINCT %s FROM %s WHERE %s" % (_cols(cols), src, where))}
            fks.append((name, src, cols, dst, cascades, held, await _holders(conn, table, dst, ident)))
        before[table] = (await _holders(conn, table, ["id"], ident), fks)
    await conn.execute(expand(text))
    record = {}
    for table, ident in moves.items():
        pre_ids, fks = before[table]
        post_ids = await _holders(conn, table, ["id"], ident)
        moved = sorted(int(k[0]) for k in pre_ids if post_ids.get(k) != pre_ids[k])
        bad = []
        for name, src, cols, dst, cascades, held, pre in fks:
            post = await _holders(conn, table, dst, ident)
            changed = {v for v in pre if post.get(v) != pre[v]}
            if not cascades and held & changed:
                bad.append((name, src, cols, dst, sorted(held & changed)[:5]))
        if bad:
            raise AssertionError("seed left references to a different %s row: %r" % (table, bad))
        record[table] = {"moved": moved,
                         "foreign_keys": [(n, s_, c, d, k) for n, s_, c, d, k, _h, _p in fks]}
    return record


def steps_for(name):
    return list(PREREQS.get(name, ()))


async def _orm_tables(conn, tables, models):
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex, CreateTable
    dialect = postgresql.dialect()
    for name in tables:
        table = models.Base.metadata.tables[name]
        if await conn.fetchval("SELECT to_regclass($1)", "public." + name) is not None:
            continue
        have = {r[0] for r in await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
        fks = [fk for fk in table.foreign_key_constraints if fk.referred_table.name in have]
        for col in table.columns:
            for typ in [col.type]:
                if getattr(typ, "name", None) and hasattr(typ, "enums"):
                    exists = await conn.fetchval("SELECT to_regtype($1)", "public." + typ.name)
                    if exists is None:
                        labels = ", ".join("'%s'" % e.replace("'", "''") for e in typ.enums)
                        await conn.execute('CREATE TYPE public."%s" AS ENUM (%s)' % (typ.name, labels))
        ddl = str(CreateTable(table, include_foreign_key_constraints=fks).compile(dialect=dialect))
        await conn.execute(ddl)
        for index in table.indexes:
            await conn.execute(str(CreateIndex(index).compile(dialect=dialect)))


async def _widen(conn, table, cols, models):
    from sqlalchemy.dialects import postgresql
    dialect = postgresql.dialect()
    t = models.Base.metadata.tables[table]
    for name in cols:
        col = t.columns[name]
        await conn.execute('ALTER TABLE public."%s" ADD COLUMN IF NOT EXISTS "%s" %s'
                           % (table, name, col.type.compile(dialect=dialect)))


async def apply(conn, step, models):
    """Run one prerequisite step on an asyncpg connection (autocommit)."""
    kind = step[0]
    if kind == "orm":
        await _orm_tables(conn, step[1], models)
    elif kind == "widen":
        await _widen(conn, step[1], step[2], models)
    elif kind == "sql":
        if len(step) > 2:
            return await _id_move_guard(conn, step[1], step[2])
        await conn.execute(expand(step[1]))
    else:
        raise AssertionError("unknown prerequisite kind %r" % (kind,))
