"""Migration 399 (real descriptions for the 19 published community faces that
still carry the approval placeholder) EXECUTED, not read.

Two halves:

* Static (always runs): the migration and its rollback pin exactly the 19
  rows read on the primary on 2026-10-30 (id and sku); every old text is the
  placeholder the approve path writes for that sku's slot; every new text is
  in the house form (slot prefix, "Equip in the Character editor."), ASCII,
  unique, free of the words the read-only
  wrapper's filter rejects (the landing spec's count names them), and says
  "(animated)" exactly when the face's CosmeticDef animates; every message is
  ONE string literal; the UPDATE guards and the rollback's inverse are in
  place; the file shape is the house shape.

* Live PostgreSQL (skips without A1_TEST_PG_DSN, the gate the 337 and 398
  tests use):

      A1_TEST_PG_DSN="postgresql+asyncpg://postgres@127.0.0.1:55432/<db>" \\
          python -m pytest backend/tests/test_shop_descriptions_399.py

  Each case builds its OWN schema, seeds the 19 rows with their placeholders
  plus control rows (the five unpublished 398 faces, a house face), runs the
  files, and drops the schema. It runs: apply twice (rerun no-op), rollback
  twice, re-apply; a row someone else edited is left alone in both
  directions; an unpublished row keeps its placeholder; a wrong sku, a wrong
  kind or a missing row RAISES and changes nothing.
"""
import asyncio
import json
import os
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SQL = ROOT / "backend" / "sql"
MIGRATION = SQL / "399_shop_face_descriptions.sql"
ROLLBACK = SQL / "rollback_399_shop_face_descriptions.sql"
CATALOG = ROOT / "plugin" / "CustomCosmetics.cs"
SHOP_STRINGS = ROOT / "tools" / "shop_strings.json"
MAIN = ROOT / "backend" / "api" / "main.py"

DSN = os.environ.get("A1_TEST_PG_DSN")

# The 19 rows read on the primary 2026-10-30 (sql-readonly): catalog_ready
# true, kind face, rotation_pool NULL, description one of the three
# placeholders. (id, sku)
FACES = [
    (250, "face_detail_spooky_head_bouncers"),
    (251, "face_detail_ballooniphones"),
    (252, "face_detail_soda_helm"),
    (253, "face_detail_brain_cane"),
    (254, "face_mouth_casi_s_mouth"),
    (255, "face_eyes_casicorn_s_eyes"),
    (256, "face_detail_little_pink_buddy"),
    (257, "face_detail_sniper_medal"),
    (258, "face_detail_spilled_icecream"),
    (259, "face_detail_magical_hat"),
    (260, "face_detail_twisted_topper"),
    (267, "face_eyes_poison_s_eyes"),
    (268, "face_mouth_poison_s_mouth"),
    (269, "face_detail_poison_s_weeping"),
    (270, "face_detail_seasonal_spring"),
    (271, "face_eyes_nuclear_glasses"),
    (329, "face_detail_well_wraped_hat"),
    (356, "face_detail_straw_hat"),
    (357, "face_detail_florabelle"),
]

TEMPLATE = "%s: community cosmetic. Ships with the next mod update; equip in the Character editor."
TAIL = " Equip in the Character editor."
SLOTS = {"face_detail_": "Detail", "face_eyes_": "Eyes", "face_mouth_": "Mouth"}

# The substrings the forced wrapper's sql-readonly filter rejects (a lowercase
# substring match; docs/deploy-reference.md, the landing tool's
# READONLY_FORBIDDEN). The landing spec's count_sql names every new text.
READONLY_FORBIDDEN = ("drop", "truncate", "delete", "update", "insert", "alter",
                      "grant", "revoke", "create", "copy")


def _slot(sku):
    for prefix, slot in SLOTS.items():
        if sku.startswith(prefix):
            return slot
    raise AssertionError("no slot for %s" % sku)


def _rows(path):
    """The expected[] rows of a file: (id, sku, placeholder, new text)."""
    text = path.read_text(encoding="utf-8")
    rows = re.findall(r"\['(\d+)', '([a-z_]+)', '((?:[^']|'')*)', '((?:[^']|'')*)'\]", text)
    return [(int(a), b, c.replace("''", "'"), d.replace("''", "'")) for a, b, c, d in rows]


def _catalog_defs():
    src = CATALOG.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r'new CosmeticDef \{([^}]*)\}', src):
        sku = re.search(r'Sku = "([^"]+)"', m.group(1))
        if sku:
            out[sku.group(1)] = m.group(1)
    return out


def _code(path):
    """The file with -- comments removed (literals kept)."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        out.append(_strip_comment(line))
    return "\n".join(out)


def _strip_comment(line):
    in_lit = False
    for k, ch in enumerate(line):
        if ch == "'":
            in_lit = not in_lit
        elif not in_lit and line.startswith("--", k):
            return line[:k]
    return line


def _literal_gaps(path):
    """For each pair of consecutive single-quoted literals in the code (the DO
    body included: PL/pgSQL lexes it again), the text between them."""
    code = _code(path)
    spans = []
    k = 0
    while k < len(code):
        if code[k] == "'":
            j = k + 1
            while True:
                if code[j] == "'" and j + 1 < len(code) and code[j + 1] == "'":
                    j += 2
                    continue
                if code[j] == "'":
                    break
                j += 1
            spans.append((k, j))
            k = j + 1
        else:
            k += 1
    return [code[a[1] + 1:b[0]] for a, b in zip(spans, spans[1:])]


# ---------------------------------------------------------------- static

def test_migration_pins_exactly_the_19_rows():
    assert [(r[0], r[1]) for r in _rows(MIGRATION)] == FACES


def test_rollback_pins_the_same_rows_and_texts():
    assert _rows(ROLLBACK) == _rows(MIGRATION)


def test_old_text_is_the_approve_path_placeholder_for_the_slot():
    src = MAIN.read_text(encoding="utf-8")
    assert ('description=f"{row[\'slot\'].capitalize()}: community cosmetic. Ships with the '
            'next mod update; equip in the Character editor."') in src
    for _id, sku, old, _new in _rows(MIGRATION):
        assert old == TEMPLATE % _slot(sku), sku


def test_new_text_is_in_the_house_form():
    rows = _rows(MIGRATION)
    news = [r[3] for r in rows]
    assert len(set(news)) == len(news), "two faces share a description"
    for _id, sku, old, new in rows:
        assert new.startswith(_slot(sku) + ": "), sku
        assert new.endswith(TAIL), sku
        assert new != old, sku
        assert new.isascii(), sku
        assert "'" not in new and '"' not in new, sku
        assert len(new) <= 256, sku                   # shop_items.description
        assert new.count(". ") + 1 <= 2, sku          # one or two sentences
        low = new.lower()
        assert not [w for w in READONLY_FORBIDDEN if w in low], (sku, new)
        assert "community cosmetic" not in low and "next mod update" not in low, sku


def test_animated_exactly_when_the_catalog_animates():
    defs = _catalog_defs()
    for _id, sku, _old, new in _rows(MIGRATION):
        body = defs.get(sku)
        assert body is not None, "no CosmeticDef for %s" % sku
        assert ("Slot = CharacterItemType.%s" % _slot(sku)) in body, sku
        assert ("(animated)" in new) == ("Fps" in body), sku


def test_old_text_is_a_shop_display_string():
    """Each placeholder 399 replaces is one of the shop's display strings
    (tools/shop_strings.json). Whether a NEW text is already on a live row is
    a fact about the database, not the tree (the client-strings branch adds
    the new texts to this file before 399 runs): the landing spec's second
    preflight read proves it on the primary."""
    live = set(json.loads(SHOP_STRINGS.read_text(encoding="utf-8"))["strings"])
    for _id, sku, old, _new in _rows(MIGRATION):
        assert old in live, sku


def test_every_message_is_one_string_literal():
    for path in (MIGRATION, ROLLBACK):
        gaps = _literal_gaps(path)
        assert gaps, path.name
        assert all(g.strip() for g in gaps), path.name
        code = _code(path)
        raises = re.findall(r"RAISE (?:EXCEPTION|NOTICE) '((?:[^']|'')*)'(\s*)([,;])", code)
        assert len(raises) == len(re.findall(r"\bRAISE\b", code)), path.name
        assert raises, path.name


def test_guards_and_the_inverse():
    mig, rb = _code(MIGRATION), _code(ROLLBACK)
    up = re.findall(r"UPDATE shop_items si\s+SET (.*?);", mig, re.S)
    assert len(up) == 1
    assert re.match(r"description = v_new\s+WHERE si\.id = v_id\s+AND si\.description = v_old\s+"
                    r"AND si\.catalog_ready IS TRUE$", up[0]), up[0]
    assert "ELSIF si_rec.description IS NOT DISTINCT FROM v_old AND si_rec.catalog_ready IS TRUE THEN" in mig
    down = re.findall(r"UPDATE shop_items si\s+SET (.*?);", rb, re.S)
    assert len(down) == 1
    assert re.match(r"description = v_old\s+WHERE si\.id = v_id\s+AND si\.description = v_new$", down[0]), down[0]
    assert "ELSIF si_rec.description IS NOT DISTINCT FROM v_new THEN" in rb
    for text in (mig, rb):
        assert "FOR NO KEY UPDATE" in text
        assert text.count("UPDATE shop_items") == 1
        assert not re.search(r"\b(INSERT|DELETE|ALTER|CREATE|DROP|TRUNCATE)\b", text)


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
        assert b"\r" not in path.read_bytes().replace(b"\r\n", b"\n"), path.name


def test_399_is_one_file_and_one_rollback():
    assert [p.name for p in SQL.glob("399_*.sql")] == [MIGRATION.name]
    assert [p.name for p in SQL.glob("rollback_399_*.sql")] == [ROLLBACK.name]


# ---------------------------------------------------------------- live

live = pytest.mark.skipif(not DSN, reason="A1_TEST_PG_DSN unset; live-Postgres migration check")

DDL = """
CREATE TABLE shop_items (
    id              BIGINT PRIMARY KEY,
    sku             VARCHAR(64) UNIQUE NOT NULL,
    kind            VARCHAR(16) NOT NULL,
    name            VARCHAR(128) NOT NULL,
    description     VARCHAR(256),
    price           INTEGER NOT NULL,
    rotation_pool   VARCHAR(32),
    catalog_ready   BOOLEAN NOT NULL DEFAULT TRUE
);
"""

# Control rows the files must never touch: 398's five unpublished faces (same
# placeholder) and a house face.
CONTROLS = [
    (358, "face_detail_orbit", "face", TEMPLATE % "Detail", False),
    (359, "face_detail_gold_headband", "face", TEMPLATE % "Detail", False),
    (569, "face_detail_pumpking_hat", "face", TEMPLATE % "Detail", False),
    (570, "face_detail_leafy_mushroom", "face", TEMPLATE % "Detail", False),
    (571, "face_detail_red_scarf", "face", TEMPLATE % "Detail", False),
    (216, "face_detail_crown", "face", "Detail: heavy is the head. Equip in the Character editor.", True),
]

NEW = {r[0]: r[3] for r in _rows(MIGRATION)}
OLD = {r[0]: r[2] for r in _rows(MIGRATION)}


async def _seed(conn, mutate=None):
    rows = [(i, sku, "face", OLD[i], True) for i, sku in FACES] + CONTROLS
    for i, sku, kind, desc, ready in rows:
        r = dict(id=i, sku=sku, kind=kind, name=sku, description=desc, price=750,
                 rotation_pool=None, catalog_ready=ready)
        if mutate:
            r = mutate(r)
        if r is None:
            continue
        await conn.execute(
            "INSERT INTO shop_items (%s) VALUES (%s)" % (
                ", ".join(r), ", ".join("$%d" % (k + 1) for k in range(len(r)))),
            *r.values())


async def _state(conn):
    return {r["id"]: (r["sku"], r["description"], r["catalog_ready"]) for r in await conn.fetch(
        "SELECT id, sku, description, catalog_ready FROM shop_items ORDER BY id")}


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


def _controls_untouched(state):
    for i, sku, _kind, desc, ready in CONTROLS:
        assert state[i] == (sku, desc, ready), (i, state[i])


@live
def test_apply_rerun_rollback_reapply():
    async def body(conn):
        await _seed(conn)
        await conn.execute(_sql(MIGRATION))
        first = await _state(conn)
        assert all(first[i][1] == NEW[i] for i, _ in FACES), first
        _controls_untouched(first)
        assert any("19 descriptions written, 0 already written, 0 left alone" in n for n in _NOTICES)

        await conn.execute(_sql(MIGRATION))                      # rerun: no-op
        assert await _state(conn) == first
        assert any("0 descriptions written, 19 already written, 0 left alone" in n for n in _NOTICES)

        await conn.execute(_sql(ROLLBACK))
        rolled = await _state(conn)
        assert all(rolled[i][1] == OLD[i] for i, _ in FACES), rolled
        _controls_untouched(rolled)
        await conn.execute(_sql(ROLLBACK))                       # rerun: no-op
        assert await _state(conn) == rolled
        assert any("0 placeholders restored, 19 already restored, 0 left alone" in n for n in _NOTICES)

        await conn.execute(_sql(MIGRATION))                      # re-apply
        assert await _state(conn) == first
    asyncio.run(_with_schema("t399_cycle", body))


@live
def test_a_row_someone_edited_is_left_alone_both_ways():
    async def body(conn):
        await _seed(conn)
        await conn.execute("UPDATE shop_items SET description = 'An artist line.' WHERE id = 253")
        await conn.execute(_sql(MIGRATION))
        s = await _state(conn)
        assert s[253][1] == "An artist line."
        assert all(s[i][1] == NEW[i] for i, _ in FACES if i != 253)
        assert any("face_detail_brain_cane (253) left alone" in n for n in _NOTICES)
        assert any("18 descriptions written, 0 already written, 1 left alone" in n for n in _NOTICES)

        await conn.execute("UPDATE shop_items SET description = 'Edited later.' WHERE id = 357")
        await conn.execute(_sql(ROLLBACK))
        s = await _state(conn)
        assert s[357][1] == "Edited later." and s[253][1] == "An artist line."
        assert all(s[i][1] == OLD[i] for i, _ in FACES if i not in (253, 357))
        assert any("17 placeholders restored, 0 already restored, 2 left alone" in n for n in _NOTICES)
    asyncio.run(_with_schema("t399_edited", body))


@live
def test_an_unpublished_row_keeps_its_placeholder():
    async def body(conn):
        def mutate(r):
            if r["id"] == 270:
                r["catalog_ready"] = False
            return r
        await _seed(conn, mutate)
        await conn.execute(_sql(MIGRATION))
        s = await _state(conn)
        assert s[270] == ("face_detail_seasonal_spring", OLD[270], False)
        assert all(s[i][1] == NEW[i] for i, _ in FACES if i != 270)
        assert any("face_detail_seasonal_spring (270) left alone" in n for n in _NOTICES)
    asyncio.run(_with_schema("t399_unpublished", body))


def _refuses(name, mutate, needle):
    async def body(conn):
        import asyncpg
        await _seed(conn, mutate)
        before = await _state(conn)
        with pytest.raises(asyncpg.exceptions.RaiseError) as ei:
            await conn.execute(_sql(MIGRATION))
        assert needle in str(ei.value), str(ei.value)
        await conn.execute("ROLLBACK")                        # the file's open transaction
        assert await _state(conn) == before                   # nothing changed
    asyncio.run(_with_schema(name, body))


@live
def test_a_wrong_sku_refuses_whole():
    def mutate(r):
        if r["id"] == 256:
            r["sku"] = "face_detail_someone_else"
        return r
    _refuses("t399_sku", mutate, "shop item 256 holds sku face_detail_someone_else")


@live
def test_a_wrong_kind_refuses_whole():
    def mutate(r):
        if r["id"] == 271:
            r["kind"] = "title"
        return r
    _refuses("t399_kind", mutate, "is kind title, not face")


@live
def test_a_missing_row_refuses_whole():
    _refuses("t399_missing", lambda r: None if r["id"] == 329 else r,
             "shop item 329 (face_detail_well_wraped_hat) does not exist")


PREREQ_397 = SQL / "397_shop_item_min_client_version.sql"
TRIGGER_SRC = SQL / "148_cosmetic_placement_and_macro_evidence.sql"


def _release_trigger_ddl():
    """The live shop_items UPDATE trigger (BEFORE UPDATE OF catalog_ready),
    from 148 as the 398 test installs it."""
    s = TRIGGER_SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    fn = re.search(r"CREATE OR REPLACE FUNCTION stamp_shop_item_catalog_release\(\).*?\$\$;", s, re.S).group(0)
    trg = re.search(r"CREATE TRIGGER trg_shop_item_catalog_release.*?;", s, re.S).group(0)
    return fn + "\n" + trg


@live
def test_on_the_397_schema_only_description_moves():
    """Main at b2257fe1 carries 397 (shop_items.min_client_version and the
    release provenance table; live on the primary 2026-10-30) and 398's files.
    399 neither reads nor writes 397's column, and its UPDATE does not name
    catalog_ready, so the live BEFORE UPDATE OF catalog_ready trigger does not
    fire: every column but description is unchanged, both ways."""
    async def body(conn):
        await conn.execute("ALTER TABLE shop_items ADD COLUMN released_at TIMESTAMPTZ, "
                           "ADD COLUMN rarity VARCHAR(16) NOT NULL DEFAULT 'rare', "
                           "ADD COLUMN stock_limit INTEGER")
        await conn.execute(_sql(PREREQ_397))
        await conn.execute(_release_trigger_ddl())
        await _seed(conn)
        await conn.execute("UPDATE shop_items SET released_at = '2026-07-24T00:00:00Z' WHERE catalog_ready")
        await conn.execute("UPDATE shop_items SET min_client_version = '1.40.0' WHERE id = 357")

        async def snap():
            return {r["id"]: dict(r) for r in await conn.fetch("SELECT * FROM shop_items ORDER BY id")}
        before = await snap()
        await conn.execute(_sql(MIGRATION))
        after = await snap()
        for i, row in before.items():
            changed = {k for k in row if row[k] != after[i][k]}
            assert changed == ({"description"} if i in NEW else set()), (i, changed)
            if i in NEW:
                assert after[i]["description"] == NEW[i]
        assert await conn.fetchval("SELECT count(*) FROM shop_item_release_provenance") == 0
        await conn.execute(_sql(ROLLBACK))
        assert await snap() == before
    asyncio.run(_with_schema("t399_on_397", body))


@live
def test_the_rollback_refuses_a_wrong_sku_whole():
    async def body(conn):
        import asyncpg
        await _seed(conn)
        await conn.execute(_sql(MIGRATION))
        await conn.execute("UPDATE shop_items SET sku = 'face_detail_moved' WHERE id = 260")
        before = await _state(conn)
        with pytest.raises(asyncpg.exceptions.RaiseError) as ei:
            await conn.execute(_sql(ROLLBACK))
        assert "rollback_399: shop item 260 holds sku face_detail_moved" in str(ei.value)
        await conn.execute("ROLLBACK")
        assert await _state(conn) == before
    asyncio.run(_with_schema("t399_rb_sku", body))
