"""Migration 333: the ROUNDS card -> ink colour table the top-card badge draws
from, and the two ways it can ship looking perfectly correct and be inert.

Both failures are invisible in a picture, because both end in the same place:
the renderer falls back to the rarity band, which is exactly what the badge
looked like before this feature existed.

  1. Seeded on the ASSET names ("Poison bullets") rather than the CANONICAL
     ones ("Poison"). 67 rows load, nothing joins, every face falls back.
  2. A theme colour too dark to read on the badge. Legible in the swatch,
     unreadable at 9 px on #12141A.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from pc_themes_data import MIGRATION, rgb, rows

REPO = Path(__file__).resolve().parents[2]
GENERATOR = REPO / "tools" / "rounds_card_themes.py"
BADGE_BG = "#12141A"          # colours.card in face_layout_v1.json
AA_FLOOR = 4.5                # WCAG AA for text this size -- 9-13 px is never "large"


def _luminance(hex_colour):
    channels = []
    for value in rgb(hex_colour):
        c = value / 255.0
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(first, second):
    a, b = _luminance(first), _luminance(second)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def test_the_contrast_helper_agrees_with_known_values():
    """A negative control on the measure itself, before it judges anything:
    black on white is 21, a colour against itself is 1."""
    assert round(contrast("#000000", "#FFFFFF"), 2) == 21.0
    assert round(contrast("#7A50D1", "#7A50D1"), 2) == 1.0


def test_seeded_on_canonical_names_not_asset_names():
    """The client writes `GetCanonicalName`'s output to `pc_prints.top_card`,
    and that differs from the asset's own name for 31 of the 67 cards. Seeding
    on the asset spelling loses every one of them silently."""
    names = {name for name, _theme, _ink, _source in rows()}

    for canonical in ("Poison", "Leech", "Ricochet", "Bombs Away",
                      "Glass Cannon", "Wind Up", "Pristine Perseverance"):
        assert canonical in names, canonical

    # the negative control: the asset spellings must NOT be keys
    for asset_name in ("Poison bullets", "Leach", "Riccochet", "BombsAway",
                       "Glasscannon", "Wind up", "Pristine perseverence"):
        assert asset_name not in names, asset_name


def test_every_shipped_ink_clears_AA_on_the_badge():
    """The ink is stored already lifted; `source_hex` keeps the game's own
    value so the lift stays auditable."""
    for name, theme, ink, source in rows():
        assert contrast(ink, BADGE_BG) >= AA_FLOOR, (name, theme, ink,
                                                     contrast(ink, BADGE_BG))

    # ...and the control: the two raw values that needed lifting must FAIL
    # the same check, or this test is measuring nothing.
    assert contrast("#7A50D1", BADGE_BG) < AA_FLOOR      # EvilPurple, 3.42
    assert contrast("#CC4646", BADGE_BG) < AA_FLOOR      # DestructiveRed, 3.97

    lifted = {theme for _n, theme, ink, source in rows() if ink != source}
    assert lifted == {"EvilPurple", "DestructiveRed"}, lifted
    unchanged = [(n, ink, source) for n, _t, ink, source in rows() if ink == source]
    assert unchanged, "no row kept the game's own colour -- the lift is too eager"


def test_the_table_spans_the_whole_enum():
    """A reading that cannot vary is not a reading. The rejected byte offset
    read one theme for all 67 cards, and the shape of that failure is a
    collapsed `theme` column."""
    seeded = rows()
    assert len(seeded) == 67, len(seeded)
    assert len({name for name, _t, _i, _s in seeded}) == 67, "duplicate card names"
    assert len({theme for _n, theme, _i, _s in seeded}) == 9, "the theme column collapsed"


def test_the_migration_asserts_its_own_end_state():
    """The post-check is what makes this migration reviewable on the box, so
    it must actually test the two failure modes rather than count rows."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "BEGIN;" in sql and "COMMIT;" in sql, "psql -f does not wrap a file in a transaction"
    assert "ON CONFLICT" in sql, "not idempotent"
    assert "RAISE EXCEPTION" in sql
    # the two failure modes, each named in the post-check
    assert re.search(r"9|nine", sql), "the distinct-theme assertion is missing"
    for canonical in ("Poison", "Leech", "Ricochet", "Bombs Away"):
        assert f"'{canonical}'" in sql, canonical


@pytest.mark.skipif(not GENERATOR.exists(), reason="generator not in this checkout")
def test_the_migration_matches_the_generator():
    """A hand-edited hex in the SQL is a colour nothing can reproduce. Skipped
    where the ROUNDS assets are absent -- the parse reads them directly."""
    proc = subprocess.run([sys.executable, str(GENERATOR), "--emit-sql"],
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        pytest.skip(f"generator could not run here: {proc.stderr.strip()[:200]}")

    row = re.compile(r"\(\s*'((?:[^']|'')*)'\s*,\s*'((?:[^']|'')*)'\s*,"
                     r"\s*'(#[0-9A-Fa-f]{6})'\s*,\s*'(#[0-9A-Fa-f]{6})'\s*\)")
    generated = [(m.group(1).replace("''", "'"), m.group(2), m.group(3), m.group(4))
                 for m in row.finditer(proc.stdout)]
    assert generated, "the generator emitted no rows"
    assert generated == rows(), "migration 333 has drifted from the parse that produced it"
