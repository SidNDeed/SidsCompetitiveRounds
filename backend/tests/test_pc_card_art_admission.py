"""Bundle admission certifies the art, not only the container (Discord card
render parity, board row 33; round-2 fix, MEDIUM 1).

Two gates, one rule each side:

* the bundle tool (backend/tools/pc_card_art_bundle.py) admits a HARVEST only
  when it is complete and English, carries the game and mod build and the
  MEASURED backing colour, has unique rows bound to their own files (no
  missing, no extra, no duplicate source row), names exactly the server's card
  table (migration 333), and every thumbnail passes the content floors;
* the renderer (pc_face._card_art_bundle_at) admits a BUNDLE only when its
  index carries the current format, a tool version no older than the one that
  made those checks, a complete English provenance block with the layout's
  backing colour, every file bound to its name's slug, distinct sources, the
  backing outside each fitted box and the content floors inside it -- so a
  bundle written before these checks can never read pc_card_art=3.

Every harvest and bundle here is SYNTHETIC: the repository carries no art.
Each control has its negative control in the round's mutation log (the check
removed -> the control goes red).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
API = HERE.parent / "api"
for _p in (str(API), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pc_face  # noqa: E402
import card_art_fixture as fx  # noqa: E402

_spec = importlib.util.spec_from_file_location("pc_card_art_bundle", HERE.parent / "tools" / "pc_card_art_bundle.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

SQL_DIR = HERE.parent / "sql"
GAME = "rounds 1.1.2 unity synthetic asm 000000000000"
MOD = "synthetic dll 000000000000"


# ── a synthetic harvest in the plugin's format 2 ────────────────────────────

def _thumb(name: str, size=(88, 120)) -> Image.Image:
    seed = hashlib.sha256(("thumb\n" + name).encode("utf-8")).digest()
    image = Image.new("RGBA", size, (70 + seed[0] % 150, 70 + seed[1] % 150, 70 + seed[2] % 150, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], 6):
        draw.rectangle((0, y, size[0] - 1, y + 2), fill=(seed[3] % 60, seed[4] % 60, seed[5] % 60, 255))
    draw.rectangle((10, 10, 40, 40), fill=(250, 250, 250, 255))
    return image


def _png(image: Image.Image) -> bytes:
    return pc_face._encode_rgba(image.convert("RGBA"))


def _row(index, name, file, data, size, language="en", rounds_locale="en-US"):
    sha = hashlib.sha256(data).hexdigest()
    bind = hashlib.sha256((name + "\n" + sha).encode("utf-8")).hexdigest()
    return [str(index), name, file, str(size[0]), str(size[1]), "14", "60", "380", "600", "True",
            sha, bind, language, rounds_locale, GAME, MOD]


def _done(**over) -> dict:
    facts = {"harvest_format": "2", "names": "67", "saved": "67", "failed": "0", "complete": "1",
             "language": "en", "rounds_locale": "en-US", "game_build": GAME, "mod_build": MOD,
             "color_space": "Linear",
             "backing_measured": ",".join(str(v) for v in pc_face.card_art_backing_rgb()),
             "backing_method": "synthetic harvest (tests)"}
    facts.update(over)
    return facts


def write_harvest(dest: Path, done=None) -> Path:
    dest.mkdir(parents=True)
    rows = []
    for i, name in enumerate(pc_face.card_art_names()):
        image = _thumb(name)
        data = _png(image)
        file = f"card_{i:03d}.png"
        (dest / file).write_bytes(data)
        rows.append(_row(i, name, file, data, image.size))
    write_tsv(dest, rows)
    write_done(dest, _done() if done is None else done)
    return dest


def read_tsv(dest: Path):
    lines = (dest / "harvest.tsv").read_text(encoding="utf-8").splitlines()
    return [line.split("\t") for line in lines[1:] if line.strip()]


def write_tsv(dest: Path, rows) -> None:
    text = "\t".join(tool.TSV_COLUMNS) + "\n" + "".join("\t".join(r) + "\n" for r in rows)
    (dest / "harvest.tsv").write_text(text, encoding="utf-8")


def write_done(dest: Path, facts: dict, marker="DONE") -> None:
    (dest / marker).write_text("".join(f"{k}={v}\n" for k, v in facts.items()), encoding="utf-8")


@pytest.fixture
def harvest(tmp_path):
    return write_harvest(tmp_path / "20261001T000000Z")


def _refusals(harvest_dir, sql_dir=SQL_DIR):
    refusals, _admitted = tool.admit_harvest(harvest_dir, sql_dir)
    return refusals


def _assert_refused(harvest_dir, why, tmp_path, sql_dir=SQL_DIR):
    refusals = _refusals(harvest_dir, sql_dir)
    assert any(why in r for r in refusals), refusals
    out = tmp_path / "out"
    assert tool.build(harvest_dir, out, sql_dir=sql_dir) == 2
    assert not out.exists() or not any(out.iterdir()), "a refused harvest wrote something"


# ── the control: a good harvest builds a bundle the renderer accepts ────────

def test_a_complete_english_harvest_builds_an_accepted_bundle(harvest, tmp_path, monkeypatch):
    assert _refusals(harvest) == []
    out = tmp_path / "out"
    assert tool.build(harvest, out, sql_dir=SQL_DIR) == 0
    (bundle,) = list(out.iterdir())
    index = json.loads((bundle / pc_face.CARD_ART_INDEX).read_text(encoding="utf-8"))
    assert index["format"] == pc_face.CARD_ART_FORMAT
    assert index["tool_version"] == pc_face.CARD_ART_TOOL_VERSION
    prov = index["provenance"]
    assert prov["language"] == "en" and prov["rounds_locale"] == "en-US"
    assert prov["game_build"] == GAME and prov["mod_build"] == MOD and prov["harvest"] == harvest.name
    assert prov["backing_rgb"] == list(pc_face.card_art_backing_rgb())
    rows = {r[1]: r for r in read_tsv(harvest)}
    for name, entry in index["cards"].items():
        assert entry["file"] == pc_face.card_art_slug(name) + ".png"
        assert entry["source_sha256"] == rows[name][10]
        assert entry["source_rect"] == [14, 60, 88, 120]
    assert tool.validate(bundle, harvest_dir=harvest, sql_dir=SQL_DIR) == 0
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", bundle)
    assert pc_face.card_art_bundle().status == "accepted"
    assert pc_face.card_art_selftest()["word"] == 3


# ── the harvest controls (brief item 2d) ────────────────────────────────────

def test_a_missing_file_refuses_the_harvest(harvest, tmp_path):
    (harvest / "card_005.png").unlink()
    _assert_refused(harvest, "missing file: card_005.png", tmp_path)


def test_an_extra_file_refuses_the_harvest(harvest, tmp_path):
    shutil.copyfile(harvest / "card_005.png", harvest / "card_999.png")
    _assert_refused(harvest, "extra file: card_999.png", tmp_path)


def test_an_all_black_thumbnail_refuses_the_harvest(harvest, tmp_path):
    """Self-consistent (its row's sha256 and name_bind follow the new bytes),
    so only the content floor can refuse it."""
    rows = read_tsv(harvest)
    black = Image.new("RGBA", (88, 120), (0, 0, 0, 255))
    data = _png(black)
    (harvest / rows[7][2]).write_bytes(data)
    rows[7] = _row(rows[7][0], rows[7][1], rows[7][2], data, black.size)
    write_tsv(harvest, rows)
    _assert_refused(harvest, "card_art_flat", tmp_path)


def test_a_dark_thumbnail_under_the_lit_floor_refuses_the_harvest(harvest, tmp_path):
    """Not flat (white specks, luma sd far over the floor) but under 8 percent
    lit: the lit floor refuses it on its own."""
    rows = read_tsv(harvest)
    dark = Image.new("RGBA", (88, 120), (0, 0, 0, 255))
    for i in range(0, 88 * 120, 25):
        dark.putpixel((i % 88, i // 88), (255, 255, 255, 255))
    assert pc_face.card_art_content(dark)[0] >= pc_face.CARD_ART_LUMA_SD_FLOOR
    data = _png(dark)
    (harvest / rows[9][2]).write_bytes(data)
    rows[9] = _row(rows[9][0], rows[9][1], rows[9][2], data, dark.size)
    write_tsv(harvest, rows)
    _assert_refused(harvest, "card_art_unlit", tmp_path)


@pytest.mark.parametrize("marker", ["done_language", "rounds_locale", "row_language", "refused_marker"])
def test_a_non_english_harvest_is_refused(harvest, tmp_path, marker):
    if marker == "done_language":
        write_done(harvest, _done(language="de"))
        why = "mod language is 'de'"
    elif marker == "rounds_locale":
        write_done(harvest, _done(rounds_locale="fr-FR"))
        why = "ROUNDS locale is 'fr-FR'"
    elif marker == "row_language":
        rows = read_tsv(harvest)
        rows[3][12] = "pt-BR"
        write_tsv(harvest, rows)
        why = "captured in pt-BR/en-US, not English"
    else:
        write_done(harvest, {"harvest_format": "2", "complete": "0",
                             "refused": "the mod is not in English (locale de)"}, marker="REFUSED")
        why = "the harvest wrote REFUSED"
    _assert_refused(harvest, why, tmp_path)


@pytest.mark.parametrize("how", ["names_in_rows", "files_on_disk"])
def test_two_swapped_names_refuse_the_harvest(harvest, tmp_path, how):
    rows = read_tsv(harvest)
    a, b = rows[2], rows[40]
    if how == "names_in_rows":
        a[1], b[1] = b[1], a[1]
        write_tsv(harvest, rows)
        why = "name_bind"
    else:
        pa, pb = harvest / a[2], harvest / b[2]
        da, db = pa.read_bytes(), pb.read_bytes()
        pa.write_bytes(db)
        pb.write_bytes(da)
        why = "sha256 differs"
    _assert_refused(harvest, why, tmp_path)


def test_a_duplicate_source_row_refuses_the_harvest(harvest, tmp_path):
    rows = read_tsv(harvest)
    rows.append(list(rows[11]))
    write_tsv(harvest, rows)
    _assert_refused(harvest, "duplicate source row", tmp_path)


def test_a_missing_row_refuses_the_harvest(harvest, tmp_path):
    rows = read_tsv(harvest)
    gone = rows.pop(20)
    (harvest / gone[2]).unlink()
    write_tsv(harvest, rows)
    _assert_refused(harvest, f"missing row: {gone[1]!r}", tmp_path)


def test_an_incomplete_run_is_refused(harvest, tmp_path):
    write_done(harvest, _done(complete="0"))
    _assert_refused(harvest, "complete run", tmp_path)


def test_a_harvest_without_its_builds_is_refused(harvest, tmp_path):
    write_done(harvest, _done(game_build="unknown"))
    _assert_refused(harvest, "DONE lacks game_build", tmp_path)


def test_a_backing_not_measured_or_not_the_layouts_is_refused(harvest, tmp_path):
    write_done(harvest, _done(backing_measured="2,2,3"))
    _assert_refused(harvest, "is not face_layout_v1.json colours.badge_art_back", tmp_path)
    facts = _done()
    del facts["backing_measured"]
    write_done(harvest, facts)
    _assert_refused(harvest, "lacks a measured backing", tmp_path)


def test_a_format_1_harvest_is_refused(harvest, tmp_path):
    write_done(harvest, _done(harvest_format="1"))
    _assert_refused(harvest, "harvest_format '1' is older", tmp_path)


def test_the_names_must_be_the_server_card_table(harvest, tmp_path):
    """The server's card table is migration 333: a table that differs from
    card_art_names.json by one name refuses the harvest."""
    sql = tmp_path / "sql"
    sql.mkdir()
    text = (SQL_DIR / tool._MIGRATION_333).read_text(encoding="utf-8")
    first = pc_face.card_art_names()[0].replace("'", "''")
    assert f"'{first}'" in text
    (sql / tool._MIGRATION_333).write_text(text.replace(f"'{first}'", "'Not A Card'", 1), encoding="utf-8")
    _assert_refused(harvest, "differs from the server's card table", tmp_path, sql_dir=sql)
    assert tool.server_card_names(SQL_DIR) == pc_face.card_art_names()


# ── the renderer's admission: an old or uncertified bundle never reads 3 ────

@pytest.fixture
def good(tmp_path, monkeypatch):
    dest = tmp_path / "pc-cards-synthetic"
    fx.write_bundle(dest)
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", dest)
    assert pc_face.card_art_bundle().status == "accepted"
    return dest


def _refused(why):
    b = pc_face.card_art_bundle()
    assert b.status == "invalid", (b.status, b.reason)
    assert why in b.reason, b.reason
    assert b.patches == {} and b.identity == pc_face.CARD_ART_NONE_IDENTITY
    assert pc_face.card_art_selftest()["word"] == 1


def test_a_format_1_bundle_never_reads_three(good):
    """The sitting-1 shape: format 1, no tool version, no provenance, four
    keys per entry. Refused whole; the word is 1, never 3."""
    def old(index):
        index.clear()
        index.update({"format": 1, "cards": {}})
    cards = json.loads((good / pc_face.CARD_ART_INDEX).read_text(encoding="utf-8"))["cards"]
    fx.rewrite_index(good, old)
    fx.rewrite_index(good, lambda i: i["cards"].update(
        {n: {k: e[k] for k in ("file", "sha256", "width", "height")} for n, e in cards.items()}))
    _refused("is not 2")


def test_a_bundle_without_a_provenance_block_is_refused(good):
    fx.rewrite_index(good, lambda i: i.pop("provenance"))
    _refused("no provenance block")


def test_a_bundle_from_an_older_tool_is_refused(good):
    fx.rewrite_index(good, lambda i: i.update({"tool_version": pc_face.CARD_ART_MIN_TOOL_VERSION - 1}))
    _refused("predates the provenance checks")


@pytest.mark.parametrize("key,value,why", [
    ("language", "de", "not English"),
    ("rounds_locale", "ru", "not English"),
    ("game_build", "unknown", "game_build missing"),
    ("mod_build", "", "mod_build missing"),
    ("backing_rgb", [2, 2, 3], "is not the layout's"),
])
def test_an_incomplete_or_non_english_provenance_is_refused(good, key, value, why):
    fx.rewrite_index(good, lambda i: i["provenance"].update({key: value}))
    _refused(why)


def test_two_names_swapped_in_the_index_are_refused(good):
    a, b = pc_face.card_art_names()[3], pc_face.card_art_names()[30]

    def swap(index):
        ca, cb = index["cards"][a], index["cards"][b]
        index["cards"][a], index["cards"][b] = cb, ca
    fx.rewrite_index(good, swap)
    _refused("is not the name's slug")


def test_two_names_sharing_one_source_are_refused(good):
    a, b = pc_face.card_art_names()[3], pc_face.card_art_names()[30]
    fx.rewrite_index(good, lambda i: i["cards"][b].update({"source_sha256": i["cards"][a]["source_sha256"]}))
    _refused("share one source thumbnail")


@pytest.mark.parametrize("damage,why", [
    ("black", "card_art_flat"),
    ("specks", "card_art_unlit"),
    ("margin", "card_art_backing"),
])
def test_a_patch_that_is_not_art_is_refused(good, damage, why):
    """Self-consistent rewrites (hash, index, digest all follow), so only the
    content and backing checks can refuse."""
    name = pc_face.card_art_names()[-3]
    patch = fx.synthetic_patch(name)
    box = pc_face.card_art_fit_box(78, 104)
    if damage == "black":
        patch.paste((0, 0, 0, 255), box)
    elif damage == "specks":
        patch.paste((0, 0, 0, 255), box)
        for i in range(0, 78 * 104, 25):
            patch.putpixel((box[0] + i % 78, i // 78), (255, 255, 255, 255))
    else:
        patch.putpixel((0, 50), (200, 10, 10, 255))
    fx.rewrite_entry(good, name, pc_face._encode_rgba(patch))
    _refused(why)


def test_the_validation_tool_refuses_what_the_renderer_refuses(good, capsys):
    fx.rewrite_index(good, lambda i: i["provenance"].update({"language": "de"}))
    assert tool.validate(good, sql_dir=SQL_DIR) == 1
    out = capsys.readouterr().out
    assert "FAIL provenance" in out and "renderer verdict: invalid" in out
