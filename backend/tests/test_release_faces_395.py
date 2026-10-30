"""Migration 395 (the five v1.41.0 community faces) EXECUTED, not read, and
pinned to the art and the Catalog rows the client ships.

Two halves:

* Static (always runs): every row the migration pins (sku, scale, byte count,
  md5) agrees with plugin/cosmetics/<file>.png on disk and with the
  CosmeticDef in plugin/CustomCosmetics.cs, and the rollback names the same
  ids. A PNG re-extracted with different bytes, or a Catalog scale edited
  without the migration, fails here.

* Live PostgreSQL (skips without A1_TEST_PG_DSN, the gate
  test_shop_migration_337.py uses):

      A1_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:55432/a1test" \\
          python -m pytest backend/tests/test_release_faces_395.py

  Each case builds its OWN schema with the production trigger body read from
  148_cosmetic_placement_and_macro_evidence.sql (its LF-normalised prosrc
  matched the primary's md5 on 2026-10-30), seeds the measured pre-image with
  the REAL bundled PNG bytes, and drops the schema afterwards. It runs: apply
  twice (rerun no-op), rollback twice, re-apply; and one negative case per
  guard, each of which must RAISE and leave every row unpublished.
"""
import asyncio
import hashlib
import os
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SQL = ROOT / "backend" / "sql"
MIGRATION = SQL / "395_release_five_faces_v1410.sql"
ROLLBACK = SQL / "rollback_395_release_five_faces_v1410.sql"
TRIGGER_SRC = SQL / "148_cosmetic_placement_and_macro_evidence.sql"
CATALOG = ROOT / "plugin" / "CustomCosmetics.cs"
ART = ROOT / "plugin" / "cosmetics"

DSN = os.environ.get("A1_TEST_PG_DSN")

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
    """The expected[] rows of 395, parsed from the file."""
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
        si = dict(id=shop, sku=sku, kind="face", name=sku, price=750, rarity="rare",
                  stock_limit=-1, released_at=None, catalog_ready=False)
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
        "SELECT si.id, si.catalog_ready, si.released_at IS NOT NULL AS stamped, "
        "si.stock_limit, cs.published_placement_revision AS pub "
        "FROM shop_items si JOIN cosmetic_submissions cs ON cs.shop_sku = si.sku "
        "ORDER BY si.id")


async def _with_schema(name, body):
    import asyncpg
    conn = await asyncpg.connect(DSN.replace("+asyncpg", ""))
    try:
        await conn.execute("DROP SCHEMA IF EXISTS %s CASCADE" % name)
        await conn.execute("CREATE SCHEMA %s" % name)
        await conn.execute("SET search_path TO %s" % name)
        await conn.execute(DDL)
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


@live
def test_apply_rerun_rollback_reapply():
    async def body(conn):
        await _seed(conn)
        await conn.execute(_sql(MIGRATION))
        first = await _state(conn)
        assert all(r["catalog_ready"] and r["stamped"] and r["pub"] == 1 for r in first), first
        assert all(r["stock_limit"] == -1 for r in first)        # stock untouched
        await conn.execute(_sql(MIGRATION))                       # rerun: no-op
        assert await _state(conn) == first

        await conn.execute("UPDATE shop_items SET stock_limit = 10 WHERE id = 359")
        await conn.execute("INSERT INTO player_items (item_id) VALUES (359)")
        await conn.execute(_sql(ROLLBACK))
        rolled = await _state(conn)
        assert all(not r["catalog_ready"] and not r["stamped"] and r["pub"] == 0
                   and r["stock_limit"] == -1 for r in rolled), rolled
        assert await conn.fetchval("SELECT count(*) FROM player_items") == 1  # owners kept
        await conn.execute(_sql(ROLLBACK))                        # rerun: no-op
        assert await _state(conn) == rolled

        await conn.execute(_sql(MIGRATION))                       # re-apply
        again = await _state(conn)
        assert all(r["catalog_ready"] and r["stamped"] and r["pub"] == 1 for r in again)
    asyncio.run(_with_schema("t395_cycle", body))


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
    "offset_moved":  (_neg("face_detail_orbit", lambda si, cs: (si, {**cs, "approved_render_offset_y": 0.2})),
                      "approved offset is now"),
    "revision_2":    (_neg("face_detail_red_scarf", lambda si, cs: (si, {**cs, "approved_placement_revision": 2})),
                      "approved revision moved"),
    "denied":        (_neg("face_detail_red_scarf", lambda si, cs: (si, {**cs, "status": "denied"})),
                      "is no longer approved"),
    "animated":      (_neg("face_detail_pumpking_hat", lambda si, cs: (si, {**cs, "frame_count": 3})),
                      "frame_count is now 3"),
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
}


@live
@pytest.mark.parametrize("case", sorted(NEGATIVES))
def test_every_guard_refuses_whole(case):
    async def body(conn):
        mutate, fragment = NEGATIVES[case]
        await _seed(conn, mutate)
        with pytest.raises(Exception) as ei:
            await conn.execute(_sql(MIGRATION))
        assert "395" in str(ei.value) and fragment in str(ei.value), (case, str(ei.value))
        await conn.execute("ROLLBACK")
        st = await _state(conn)
        assert not any(r["catalog_ready"] for r in st), (case, st)   # nothing landed
        return str(ei.value)
    msg = asyncio.run(_with_schema("t395_neg_%s" % case, body))
    assert msg


@live
def test_matching_control_passes():
    """Negative control for the negatives: the unmutated seed must apply, or
    every refusal above proves only that the file always raises."""
    async def body(conn):
        await _seed(conn, _neg("none", lambda si, cs: (si, cs)))
        await conn.execute(_sql(MIGRATION))
        return await _state(conn)
    st = asyncio.run(_with_schema("t395_control", body))
    assert len(st) == 5 and all(r["catalog_ready"] for r in st)


@live
def test_rollback_refuses_a_state_that_is_neither_image():
    """Unpublished but stamped is neither 395's post-image nor the measured
    pre-image: the rollback must refuse rather than guess."""
    async def body(conn):
        await _seed(conn)
        await conn.execute("UPDATE shop_items SET released_at = now() WHERE id = 358")
        with pytest.raises(Exception) as ei:
            await conn.execute(_sql(ROLLBACK))
        return str(ei.value)
    msg = asyncio.run(_with_schema("t395_rb_mixed", body))
    assert "rollback 395" in msg and "not at the pre-image" in msg, msg
