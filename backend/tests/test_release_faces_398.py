"""Migration 398 (the five v1.41.0 community faces; first written as 395)
EXECUTED, not read, and pinned to the art and the Catalog rows the client
ships.

Two halves:

* Static (always runs): every row the migration pins (sku, scale, byte count,
  md5) agrees with plugin/cosmetics/<file>.png on disk and with the
  CosmeticDef in plugin/CustomCosmetics.cs, and the rollback names the same
  ids. A PNG re-extracted with different bytes, or a Catalog scale edited
  without the migration, fails here.

* Live PostgreSQL (skips without A1_TEST_PG_DSN, the gate
  test_shop_migration_337.py uses):

      A1_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:55432/a1test" \\
          python -m pytest backend/tests/test_release_faces_398.py

  Each case builds its OWN schema, applies migration 397 (the column and the
  provenance table 398 needs), installs the production trigger body read from
  148_cosmetic_placement_and_macro_evidence.sql (its LF-normalised prosrc
  matched the primary's md5 on 2026-10-30), seeds the measured pre-image with
  the REAL bundled PNG bytes, and drops the schema afterwards. It runs: apply
  twice (rerun no-op), rollback twice, re-apply; one negative case per guard,
  each of which must RAISE and leave every row unpublished; the rollback
  leaving a later publication by a person alone; and the post-check naming
  the sku and the field it found wrong.
"""
import asyncio
import hashlib
import os
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SQL = ROOT / "backend" / "sql"
MIGRATION = SQL / "398_release_five_faces_v1410.sql"
ROLLBACK = SQL / "rollback_398_release_five_faces_v1410.sql"
PREREQ = SQL / "397_shop_item_min_client_version.sql"
TRIGGER_SRC = SQL / "148_cosmetic_placement_and_macro_evidence.sql"
CATALOG = ROOT / "plugin" / "CustomCosmetics.cs"
ART = ROOT / "plugin" / "cosmetics"

DSN = os.environ.get("A1_TEST_PG_DSN")

PLACEHOLDER = ("Detail: community cosmetic. Ships with the next mod update; "
               "equip in the Character editor.")
SHIPPED = "Detail: community cosmetic. Equip in the Character editor."

# (submission id, shop item id, sku, png file, scale) -- the 2026-10-30
# reading of the primary. bytes/md5 come from the migration text itself.
FACES = [
    (69, 359, "face_detail_gold_headband", "detail_gold_headband.png", "1.45"),
    (70, 358, "face_detail_orbit", "detail_orbit.png", "1.60"),
    (71, 569, "face_detail_pumpking_hat", "detail_pumpking_hat.png", "1.40"),
    (72, 570, "face_detail_leafy_mushroom", "detail_leafy_mushroom.png", "1.30"),
    (73, 571, "face_detail_red_scarf", "detail_red_scarf.png", "1.60"),
]


def _migration_rows():
    """The expected[] rows of 398, parsed from the file."""
    text = MIGRATION.read_text(encoding="utf-8")
    rows = re.findall(
        r"\['(\d+)', '(\d+)', '([a-z_]+)',\s*'([\d.]+)', '(\d+)', '([0-9a-f]{32})'\]",
        text)
    return [(int(a), int(b), c, d, int(e), f) for a, b, c, d, e, f in rows]


def _catalog_defs():
    src = CATALOG.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r'new CosmeticDef \{([^}]*)\}', src):
        body = m.group(1)
        sku = re.search(r'Sku = "([^"]+)"', body)
        if sku:
            out[sku.group(1)] = body
    return out


# ---------------------------------------------------------------- static

def test_migration_pins_exactly_the_five_faces():
    rows = _migration_rows()
    assert [(r[0], r[1], r[2], r[3]) for r in rows] == \
        [(f[0], f[1], f[2], f[4]) for f in FACES]


def test_bundled_art_matches_the_migration_pins():
    for sub, shop, sku, png, scale in FACES:
        row = next(r for r in _migration_rows() if r[2] == sku)
        data = (ART / png).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", png
        assert data[12:16] == b"IHDR", png
        assert len(data) == row[4], (png, len(data), row[4])
        assert hashlib.md5(data).hexdigest() == row[5], png


def test_catalog_rows_match_the_migration_pins():
    defs = _catalog_defs()
    for sub, shop, sku, png, scale in FACES:
        body = defs.get(sku)
        assert body is not None, "no CosmeticDef for %s" % sku
        assert 'PngFile = "%s"' % png in body, sku
        assert "Slot = CharacterItemType.Detail" in body, sku
        m = re.search(r"Scale = ([\d.]+)f", body)
        assert m and abs(float(m.group(1)) - float(scale)) < 1e-6, (sku, body)
        assert "Offset = Vector2.zero" in body, sku
        assert "Fps" not in body, sku          # static: no animation rate


def test_the_five_are_the_last_catalog_rows_in_submission_order():
    """The Catalog is append-only (index = network id): the five must be
    appended after every existing row, never inserted mid-array."""
    order = list(_catalog_defs())
    assert order[-5:] == [f[2] for f in FACES]


def test_rollback_names_the_same_ids():
    text = ROLLBACK.read_text(encoding="utf-8")
    rows = re.findall(r"\['(\d+)', '(\d+)', '([a-z_]+)'\]", text)
    assert [(int(a), int(b), c) for a, b, c in rows] == \
        [(f[0], f[1], f[2]) for f in FACES]


def test_the_floor_is_the_client_that_ships_the_catalog_rows():
    """398 sets min_client_version to the version whose Catalog carries the
    five; Plugin.ModVersion names the version this branch builds."""
    m = re.search(r"min_version\s+CONSTANT TEXT := '([\d.]+)';",
                  MIGRATION.read_text(encoding="utf-8"))
    assert m and m.group(1) == "1.41.0"
    plugin = (ROOT / "plugin" / "Plugin.cs").read_text(encoding="utf-8")
    assert 'public const string ModVersion = "1.41.0";' in plugin


def test_house_shape():
    for path in (MIGRATION, ROLLBACK):
        lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.strip().startswith("--")]
        assert lines[:5] == [
            "BEGIN;",
            "SET LOCAL lock_timeout = '5s';",
            "SET LOCAL idle_in_transaction_session_timeout = '5s';",
            "SET LOCAL statement_timeout = '25s';",
            "SET LOCAL synchronous_commit = local;",
        ], path.name
        assert lines[5] == "DO $$", path.name
        assert lines[-2:] == ["END $$;", "COMMIT;"], path.name
        assert sum(1 for l in lines if l == "DO $$") == 1, path.name


def test_397_sorts_before_398_and_no_other_file_takes_either_number():
    names = sorted(p.name for p in SQL.glob("39[0-9]_*.sql"))
    assert [n for n in names if n.startswith("397_")] == [PREREQ.name]
    assert [n for n in names if n.startswith("398_")] == [MIGRATION.name]
    assert not list(SQL.glob("395_*.sql")), "395 was renumbered 398"


# ---------------------------------------------------------------- live

live = pytest.mark.skipif(not DSN, reason="A1_TEST_PG_DSN unset; live-Postgres migration check")


def _trigger_ddl():
    s = TRIGGER_SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    fn = re.search(r"CREATE OR REPLACE FUNCTION stamp_shop_item_catalog_release\(\).*?\$\$;",
                   s, re.S).group(0)
    body = re.search(r"AS \$\$(.*?)\$\$;", fn, re.S).group(1)
    # The primary's prosrc, measured 2026-10-30: if 148's text and the live
    # body ever diverge, this harness is testing the wrong trigger.
    assert hashlib.md5(body.encode()).hexdigest() == "48387b17bcc54ebe16c7d446c24385fe"
    trg = re.search(r"CREATE TRIGGER trg_shop_item_catalog_release.*?;", s, re.S).group(0)
    return fn + "\n" + trg


DDL = """
CREATE TABLE shop_items (
    id              BIGINT PRIMARY KEY,
    sku             VARCHAR(64) UNIQUE NOT NULL,
    kind            VARCHAR(16) NOT NULL,
    name            VARCHAR(128) NOT NULL,
    description     VARCHAR(256),
    price           INTEGER NOT NULL,
    rarity          VARCHAR(16) NOT NULL DEFAULT 'common',
    stock_limit     INTEGER,
    released_at     TIMESTAMPTZ,
    catalog_ready   BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE cosmetic_submissions (
    id                            BIGINT PRIMARY KEY,
    name                          VARCHAR(64),
    slot                          VARCHAR(16),
    png_data                      BYTEA,
    png_bytes                     INTEGER,
    status                        VARCHAR(16),
    shop_sku                      VARCHAR(64),
    approved_render_scale         REAL,
    approved_render_offset_x      REAL,
    approved_render_offset_y      REAL,
    approved_placement_revision   INTEGER,
    published_placement_revision  INTEGER NOT NULL DEFAULT 0
        CHECK (published_placement_revision >= 0),
    frame_count                   INTEGER,
    anim_fps                      REAL,
    CONSTRAINT ck_cosmetic_published_revision_approved CHECK (
        published_placement_revision = 0
        OR (approved_placement_revision IS NOT NULL
            AND published_placement_revision <= approved_placement_revision))
);
CREATE TABLE player_items (id BIGSERIAL PRIMARY KEY, item_id BIGINT NOT NULL);
"""


async def _seed(conn, mutate=None):
    for sub, shop, sku, png, scale in FACES:
        data = (ART / png).read_bytes()
        si = dict(id=shop, sku=sku, kind="face", name=sku, description=PLACEHOLDER,
                  price=750, rarity="rare", stock_limit=-1, released_at=None,
                  catalog_ready=False)
        cs = dict(id=sub, name=sku, slot="detail", png_data=data, png_bytes=len(data),
                  status="approved", shop_sku=sku, approved_render_scale=float(scale),
                  approved_render_offset_x=0.0, approved_render_offset_y=0.0,
                  approved_placement_revision=1, published_placement_revision=0,
                  frame_count=1, anim_fps=None)
        if mutate:
            si, cs = mutate(sku, si, cs)
        if si is not None:
            await conn.execute(
                "INSERT INTO shop_items (%s) VALUES (%s)" % (
                    ", ".join(si), ", ".join("$%d" % (i + 1) for i in range(len(si)))),
                *si.values())
        if cs is not None:
            await conn.execute(
                "INSERT INTO cosmetic_submissions (%s) VALUES (%s)" % (
                    ", ".join(cs), ", ".join("$%d" % (i + 1) for i in range(len(cs)))),
                *cs.values())


async def _state(conn):
    return await conn.fetch(
        "SELECT si.id, si.catalog_ready, si.released_at, si.released_at IS NOT NULL AS stamped, "
        "si.stock_limit, si.min_client_version AS floor, si.description AS descr, "
        "cs.published_placement_revision AS pub, "
        "(SELECT count(*) FROM shop_item_release_provenance p "
        "  WHERE p.migration = '398' AND p.shop_item_id = si.id) AS prov "
        "FROM shop_items si JOIN cosmetic_submissions cs ON cs.shop_sku = si.sku "
        "ORDER BY si.id")


def _by_id(rows):
    return {r["id"]: r for r in rows}


# NOTICEs the server sent on the current case's connection (asyncpg's
# Connection takes no new attributes, so they are collected here).
_NOTICES = []


async def _with_schema(name, body):
    import asyncpg
    conn = await asyncpg.connect(DSN.replace("+asyncpg", ""))
    _NOTICES.clear()
    conn.add_log_listener(lambda c, m: _NOTICES.append(m.message))
    try:
        await conn.execute("DROP SCHEMA IF EXISTS %s CASCADE" % name)
        await conn.execute("CREATE SCHEMA %s" % name)
        await conn.execute("SET search_path TO %s" % name)
        await conn.execute(DDL)
        await conn.execute(_sql(PREREQ))
        await conn.execute(_trigger_ddl())
        return await body(conn)
    finally:
        try:
            await conn.execute("ROLLBACK")
        except Exception:
            pass
        await conn.execute("DROP SCHEMA IF EXISTS %s CASCADE" % name)
        await conn.close()


def _sql(path):
    return path.read_text(encoding="utf-8")


def _published(r, rev=1):
    return (r["catalog_ready"] and r["stamped"] and r["pub"] == rev
            and r["floor"] == "1.41.0" and r["prov"] == 1)


def _pre_image(r):
    return (not r["catalog_ready"] and not r["stamped"] and r["pub"] == 0
            and r["floor"] is None and r["stock_limit"] == -1 and r["prov"] == 0)


@live
def test_apply_rerun_rollback_reapply():
    async def body(conn):
        await _seed(conn)
        await conn.execute(_sql(MIGRATION))
        first = await _state(conn)
        assert all(_published(r) for r in first), first
        assert all(r["descr"] == SHIPPED for r in first), first       # no future claim
        assert all(r["stock_limit"] == -1 for r in first)             # stock untouched
        await conn.execute(_sql(MIGRATION))                            # rerun: no-op
        assert await _state(conn) == first

        await conn.execute("UPDATE shop_items SET stock_limit = 10 WHERE id = 359")
        await conn.execute("INSERT INTO player_items (item_id) VALUES (359)")
        await conn.execute(_sql(ROLLBACK))
        rolled = await _state(conn)
        assert all(_pre_image(r) for r in rolled), rolled
        assert all(r["descr"] == PLACEHOLDER for r in rolled), rolled
        assert await conn.fetchval("SELECT count(*) FROM player_items") == 1  # owners kept
        await conn.execute(_sql(ROLLBACK))                             # rerun: no-op
        assert await _state(conn) == rolled

        await conn.execute(_sql(MIGRATION))                            # re-apply
        again = await _state(conn)
        assert all(_published(r) for r in again)
    asyncio.run(_with_schema("t398_cycle", body))


def _neg(target, change):
    def mutate(sku, si, cs):
        if sku == target:
            return change(si, cs)
        return si, cs
    return mutate


# case -> (seed mutation, a fragment of the ONE guard that must refuse it).
# Lore #712: a red case is credited to the guard it names, not a neighbour.
NEGATIVES = {
    "scale_moved":   (_neg("face_detail_orbit", lambda si, cs: (si, {**cs, "approved_render_scale": 1.7})),
                      "approved scale is"),
    "scale_null":    (_neg("face_detail_orbit", lambda si, cs: (si, {**cs, "approved_render_scale": None})),
                      "approved scale is <NULL>"),
    "offset_moved":  (_neg("face_detail_orbit", lambda si, cs: (si, {**cs, "approved_render_offset_y": 0.2})),
                      "approved offset is now"),
    "offset_x_null": (_neg("face_detail_orbit", lambda si, cs: (si, {**cs, "approved_render_offset_x": None})),
                      "approved offset is now (<NULL>,0)"),
    "offset_y_null": (_neg("face_detail_orbit", lambda si, cs: (si, {**cs, "approved_render_offset_y": None})),
                      "approved offset is now (0,<NULL>)"),
    "revision_2":    (_neg("face_detail_red_scarf", lambda si, cs: (si, {**cs, "approved_placement_revision": 2})),
                      "approved revision moved"),
    "revision_null": (_neg("face_detail_red_scarf", lambda si, cs: (si, {**cs, "approved_placement_revision": None})),
                      "approved revision moved to <NULL>"),
    "denied":        (_neg("face_detail_red_scarf", lambda si, cs: (si, {**cs, "status": "denied"})),
                      "is no longer approved"),
    "animated":      (_neg("face_detail_pumpking_hat", lambda si, cs: (si, {**cs, "frame_count": 3})),
                      "frame_count is now 3"),
    "frames_null":   (_neg("face_detail_pumpking_hat", lambda si, cs: (si, {**cs, "frame_count": None})),
                      "frame_count is now <NULL>"),
    "art_changed":   (_neg("face_detail_pumpking_hat", lambda si, cs: (si, {**cs, "png_data": cs["png_data"] + b"x", "png_bytes": cs["png_bytes"] + 1})),
                      "stored art is now"),
    "art_same_size": (_neg("face_detail_pumpking_hat", lambda si, cs: (si, {**cs, "png_data": cs["png_data"][:-1] + b"x"})),
                      "stored art is now"),
    "wrong_slot":    (_neg("face_detail_leafy_mushroom", lambda si, cs: (si, {**cs, "slot": "eyes"})),
                      "slot is eyes"),
    "no_shop_row":   (_neg("face_detail_leafy_mushroom", lambda si, cs: (None, cs)),
                      "no shop_items row"),
    "no_submission": (_neg("face_detail_gold_headband", lambda si, cs: (si, None)),
                      "no cosmetic_submissions row"),
    "kind_mismatch": (_neg("face_detail_gold_headband", lambda si, cs: ({**si, "kind": "title"}, cs)),
                      "expected (face_detail_gold_headband, face)"),
    "floor_set_elsewhere": (_neg("face_detail_gold_headband", lambda si, cs: ({**si, "min_client_version": "1.40.0"}, cs)),
                      "already carries min_client_version 1.40.0"),
    "published_by_someone_else": (_neg("face_detail_orbit", lambda si, cs: ({**si, "catalog_ready": True, "released_at": None}, cs)),
                      "already published but not by 398"),
}


@live
@pytest.mark.parametrize("case", sorted(NEGATIVES))
def test_every_guard_refuses_whole(case):
    async def body(conn):
        mutate, fragment = NEGATIVES[case]
        await _seed(conn, mutate)
        before = await _state(conn)
        sql = _sql(MIGRATION)
        with pytest.raises(Exception) as ei:
            await conn.execute(sql)
        assert "398" in str(ei.value) and fragment in str(ei.value), (case, str(ei.value))
        await conn.execute("ROLLBACK")
        assert await _state(conn) == before, case                   # nothing landed
        return str(ei.value)
    msg = asyncio.run(_with_schema("t398_neg_%s" % case, body))
    assert msg


@live
def test_matching_control_passes():
    """Negative control for the negatives: the unmutated seed must apply, or
    every refusal above proves only that the file always raises."""
    async def body(conn):
        await _seed(conn, _neg("none", lambda si, cs: (si, cs)))
        await conn.execute(_sql(MIGRATION))
        return await _state(conn)
    st = asyncio.run(_with_schema("t398_control", body))
    assert len(st) == 5 and all(_published(r) for r in st)


@live
def test_an_artist_description_is_left_as_written_both_ways():
    async def body(conn):
        await _seed(conn, _neg("face_detail_red_scarf",
                               lambda si, cs: ({**si, "description": "Warm and red."}, cs)))
        await conn.execute(_sql(MIGRATION))
        up = _by_id(await _state(conn))
        assert up[571]["descr"] == "Warm and red." and _published(up[571])
        assert up[358]["descr"] == SHIPPED
        assert any("face_detail_red_scarf carries its artist" in n for n in _NOTICES)
        # After the release the orbit artist writes a description of their own.
        await conn.execute("UPDATE shop_items SET description = 'Round and round.' WHERE id = 358")
        await conn.execute(_sql(ROLLBACK))
        down = _by_id(await _state(conn))
        assert all(_pre_image(r) for r in down.values()), down
        assert down[571]["descr"] == "Warm and red."
        assert down[358]["descr"] == "Round and round."               # not 398's text: kept
        assert down[359]["descr"] == PLACEHOLDER                      # 398's text: restored
    asyncio.run(_with_schema("t398_desc", body))


# Later publications by a person, each of which the rollback must leave alone.
async def _republish_revision_2(conn):
    await conn.execute("UPDATE cosmetic_submissions SET approved_placement_revision = 2,"
                       " published_placement_revision = 2 WHERE id = 70")


async def _republish_after_rollback(conn):
    await conn.execute(_sql(ROLLBACK))
    await conn.execute("UPDATE shop_items SET catalog_ready = TRUE WHERE id = 358")


async def _restamp_release(conn):
    await conn.execute("UPDATE shop_items SET released_at = released_at + interval '1 day'"
                       " WHERE id = 358")


LATER = {"revision_2": _republish_revision_2,
         "republished_after_rollback": _republish_after_rollback,
         "release_restamped": _restamp_release}


@live
@pytest.mark.parametrize("case", sorted(LATER))
def test_the_rollback_leaves_a_later_publication_alone(case):
    async def body(conn):
        await _seed(conn)
        await conn.execute(_sql(MIGRATION))
        await LATER[case](conn)
        before = _by_id(await _state(conn))[358]
        await conn.execute(_sql(ROLLBACK))
        after = _by_id(await _state(conn))
        assert after[358] == before, (case, before, after[358])      # orbit untouched
        assert after[358]["catalog_ready"] and after[358]["stamped"]
        assert all(_pre_image(after[i]) for i in (359, 569, 570, 571)), after
        assert any("face_detail_orbit LEFT ALONE" in n for n in _NOTICES), _NOTICES
    asyncio.run(_with_schema("t398_later_%s" % case, body))


@live
def test_the_rollback_leaves_an_unpublished_but_stamped_row_alone():
    """Unpublished but stamped is neither 398's post-image nor the measured
    pre-image: the rollback names it and does not touch it."""
    async def body(conn):
        await _seed(conn)
        await conn.execute("UPDATE shop_items SET released_at = now() WHERE id = 358")
        before = await _state(conn)
        await conn.execute(_sql(ROLLBACK))
        assert await _state(conn) == before
        return _NOTICES
    notices = asyncio.run(_with_schema("t398_rb_mixed", body))
    assert any("face_detail_orbit LEFT ALONE" in n for n in notices), notices


@live
def test_a_rerun_refuses_when_398s_record_outlived_its_publication():
    async def body(conn):
        await _seed(conn)
        await conn.execute(_sql(MIGRATION))
        await conn.execute("UPDATE shop_items SET catalog_ready = FALSE, released_at = NULL,"
                           " min_client_version = NULL WHERE id = 358")
        sql = _sql(MIGRATION)
        with pytest.raises(Exception) as ei:
            await conn.execute(sql)
        return str(ei.value)
    msg = asyncio.run(_with_schema("t398_stale_prov", body))
    assert "398: face_detail_orbit is unpublished but 398's provenance row" in msg, msg


# A trigger that stamps less than the live one: the post-check must name the
# first row it finds wrong and the field.
NO_STAMP = """
CREATE OR REPLACE FUNCTION stamp_shop_item_catalog_release() RETURNS TRIGGER
LANGUAGE plpgsql AS $f$ BEGIN RETURN NEW; END; $f$;
"""
STAMP_TIME_ONLY = """
CREATE OR REPLACE FUNCTION stamp_shop_item_catalog_release() RETURNS TRIGGER
LANGUAGE plpgsql AS $f$
BEGIN
    IF NEW.catalog_ready AND NOT OLD.catalog_ready AND NEW.released_at IS NULL THEN
        NEW.released_at = NOW();
    END IF;
    RETURN NEW;
END; $f$;
"""


@live
@pytest.mark.parametrize("trigger,fragment", [
    (NO_STAMP, "post-check FAILED: face_detail_gold_headband released_at is NULL"),
    (STAMP_TIME_ONLY, "post-check FAILED: face_detail_gold_headband "
                      "published_placement_revision is 0, expected 1"),
], ids=["no_stamp", "time_only"])
def test_a_failed_post_check_names_the_sku_and_the_field(trigger, fragment):
    async def body(conn):
        await _seed(conn)
        await conn.execute(trigger)
        sql = _sql(MIGRATION)
        with pytest.raises(Exception) as ei:
            await conn.execute(sql)
        await conn.execute("ROLLBACK")
        assert not any(r["catalog_ready"] for r in await _state(conn))
        return str(ei.value)
    msg = asyncio.run(_with_schema("t398_postcheck_%d" % len(trigger), body))
    assert fragment in msg, msg


# ---------------------------------------------------------------- live: concurrent writers
#
# Event-gated two-session cases (Codex COSMETICS-R2 F3). Session A opens a
# transaction and writes a row the migration (session B) reads and later
# writes; B is started, a third connection waits until B is waiting on a lock,
# and only then A commits. Every read-then-write in 398 and rollback_398 must
# act on rows locked before the first check, so B judges A's committed value.

async def _second(name):
    import asyncpg
    c = await asyncpg.connect(DSN.replace("+asyncpg", ""))
    await c.execute("SET search_path TO %s" % name)
    return c


async def _wait_blocked(pid):
    """True once backend `pid` is waiting on a lock (capped at about 10 s).
    A separate connection: pg_stat_activity is snapshotted per transaction."""
    import asyncpg
    mon = await asyncpg.connect(DSN.replace("+asyncpg", ""))
    try:
        for _ in range(200):
            w = await mon.fetchval(
                "SELECT wait_event_type FROM pg_stat_activity WHERE pid = $1", pid)
            if w == "Lock":
                return True
            await asyncio.sleep(0.05)
        return False
    finally:
        await mon.close()


async def _race(name, conn, writer_sql, migration_sql):
    """A writes and holds; B (conn) runs the migration; A commits once B
    waits. Returns B's exception, or None."""
    a = await _second(name)
    try:
        await a.execute("BEGIN")
        await a.execute(writer_sql)
        task = asyncio.ensure_future(conn.execute(migration_sql))
        blocked = await _wait_blocked(conn.get_server_pid())
        await a.execute("COMMIT")
        try:
            await task
            err = None
        except Exception as e:                      # B's outcome, judged by the caller
            err = e
        assert blocked, "the migration never waited on the writer's row lock"
        return err
    finally:
        await a.close()


@live
def test_an_artist_description_committed_mid_publication_is_kept():
    """An /artist/set-desc commit that lands while 398 runs must win: 398 must
    not write its earlier reading of the placeholder over it, and must record
    no description write for that row."""
    async def body(conn):
        await _seed(conn)
        err = await _race("t398_race_desc", conn,
                          "UPDATE shop_items SET description = 'Warm and red.' WHERE id = 571",
                          _sql(MIGRATION))
        assert err is None, err
        st = _by_id(await _state(conn))
        assert st[571]["descr"] == "Warm and red.", st[571]
        assert _published(st[571]) and st[358]["descr"] == SHIPPED
        prov = await conn.fetchrow(
            "SELECT description_before, description_written FROM shop_item_release_provenance"
            " WHERE migration = '398' AND shop_item_id = 571")
        assert prov["description_written"] is None, dict(prov)
        assert prov["description_before"] == "Warm and red.", dict(prov)
    asyncio.run(_with_schema("t398_race_desc", body))


@live
def test_a_republication_committed_mid_rollback_is_left_alone():
    """A revision-2 publication of orbit that commits while rollback_398 runs:
    the rollback must judge orbit on the committed values (left alone, named)
    and still revert the other four, never abort on a stale reading."""
    async def body(conn):
        await _seed(conn)
        await conn.execute(_sql(MIGRATION))
        err = await _race("t398_race_rb", conn,
                          "UPDATE cosmetic_submissions SET approved_placement_revision = 2,"
                          " published_placement_revision = 2 WHERE id = 70",
                          _sql(ROLLBACK))
        assert err is None, err
        st = _by_id(await _state(conn))
        assert st[358]["catalog_ready"] and st[358]["pub"] == 2 and st[358]["prov"] == 1
        assert all(_pre_image(st[i]) for i in (359, 569, 570, 571)), st
        assert any("face_detail_orbit LEFT ALONE" in n for n in _NOTICES), _NOTICES
    asyncio.run(_with_schema("t398_race_rb", body))
