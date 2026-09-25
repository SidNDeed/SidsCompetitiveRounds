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

import ast
import asyncio
import importlib.util
import os
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


def _generator_prerequisites():
    """Why the generator CANNOT run here, or None if it can.

    The distinction this draws is the whole point. "The ROUNDS assets are not
    installed on this machine" is a property of the machine and a legitimate
    skip. "The generator ran and exited non-zero" is a RESULT -- a parse that
    no longer matches the assets, or a failed self-check -- and turning that
    into a skip hides the one outcome this test exists to report while the run
    still says exit 0 (#342).

    Checked BEFORE running, so the verdict never has to be inferred from an
    exit code that would otherwise mean several different things.
    """
    if not GENERATOR.exists():
        return "the generator is not in this checkout"
    if importlib.util.find_spec("UnityPy") is None:
        return "UnityPy is not installed, so no asset can be read here"
    game = os.environ.get(
        "SCR_ROUNDS_DATA",
        r"C:\Program Files (x86)\Steam\steamapps\common\ROUNDS\ROUNDS_Data")
    if not Path(game).is_dir():
        return "the ROUNDS assets are not installed here (%s)" % game
    return None


def test_the_migration_matches_the_generator():
    """A hand-edited hex in the SQL is a colour nothing can reproduce.

    Skipped only where the generator's INPUTS are absent. Once they are
    present, any non-zero exit is a FAILURE: that exit is how the tool reports
    a parse error (2) or a failed self-check, and those are exactly the events
    that must not be swallowed.
    """
    unavailable = _generator_prerequisites()
    if unavailable:
        pytest.skip(unavailable)

    proc = subprocess.run([sys.executable, str(GENERATOR), "--emit-sql"],
                          capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, (
        "the theme generator exited %d with its inputs present. That is a parse "
        "failure or a failed self-check, not an unavailable machine, and "
        "migration 333's values are unreproducible until it is fixed.\n"
        "stderr: %s" % (proc.returncode, proc.stderr.strip()[:1000]))

    row = re.compile(r"\(\s*'((?:[^']|'')*)'\s*,\s*'((?:[^']|'')*)'\s*,"
                     r"\s*'(#[0-9A-Fa-f]{6})'\s*,\s*'(#[0-9A-Fa-f]{6})'\s*\)")
    generated = [(m.group(1).replace("''", "'"), m.group(2), m.group(3), m.group(4))
                 for m in row.finditer(proc.stdout)]
    assert generated, "the generator emitted no rows"
    assert generated == rows(), "migration 333 has drifted from the parse that produced it"


def test_the_generator_self_check_passes():
    """`--control` runs migration 221's two recorded colours back through the
    parser and returns non-zero if either fails to reproduce.

    Its own test, so a self-check failure reports as itself rather than being
    folded into the comparison above -- and asserted rather than skipped, for
    the same reason.
    """
    unavailable = _generator_prerequisites()
    if unavailable:
        pytest.skip(unavailable)
    proc = subprocess.run([sys.executable, str(GENERATOR), "--control"],
                          capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, (
        "the theme generator's own controls failed (exit %d). Migration 221's "
        "recorded colours no longer reproduce from the assets, so nothing "
        "derived from this parse can be trusted.\nstdout: %s\nstderr: %s"
        % (proc.returncode, proc.stdout.strip()[-1000:], proc.stderr.strip()[:1000]))


# ── The production loader the autouse fixture stands in for ────────────────

def test_startup_loads_the_card_theme_map():
    """conftest seeds `main._PC_CARD_THEMES` for every test in this suite. That
    is necessary -- a test process never runs `lifespan` -- and it is also a
    MASK: with the map pre-seeded, DELETING the production load leaves every
    renderer test green while a real boot serves an empty map and every face
    route refuses (`_pc_renderer_unavailable`).

    So the startup call is asserted from main's own AST rather than from
    behaviour the fixture already supplied. Removing the
    `await _pc_load_card_themes(...)` line from `lifespan` reddens this and
    nothing else in the suite.
    """
    main_py = Path(__file__).resolve().parents[1] / "api" / "main.py"
    tree = ast.parse(main_py.read_text(encoding="utf-8"))
    lifespan = next((n for n in ast.walk(tree)
                     if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
                     and n.name == "lifespan"), None)
    assert lifespan is not None, "main.lifespan is gone"

    awaited = []
    for node in ast.walk(lifespan):
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            fn = node.value.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
            if name:
                awaited.append(name)
    assert "_pc_load_card_themes" in awaited, (
        "main.lifespan does not await _pc_load_card_themes. Production would "
        "boot with an empty card->ink map, every face route would refuse, and "
        "this suite would stay green because conftest seeds the map itself.")


def test_the_loader_populates_the_map_from_the_table():
    """And the loader has to actually load. The AST check alone would pass
    over a function that had been gutted to a no-op."""
    import main

    class _Rows:
        def __init__(self, rows_):
            self._rows = rows_

        def mappings(self):
            return self

        def all(self):
            return self._rows

    class _DB:
        async def execute(self, _statement, _params=None):
            return _Rows([{"card_name": "Poison", "hex": "#00934C"},
                          {"card_name": "Bad Hex", "hex": "not-a-colour"}])

    before = dict(main._PC_CARD_THEMES)
    try:
        main._PC_CARD_THEMES.clear()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(main._pc_load_card_themes(_DB()))
        finally:
            loop.close()
        assert main._PC_CARD_THEMES.get("Poison") == (0x00, 0x93, 0x4C), (
            "the startup loader did not put the table's ink into the map: %r"
            % (main._PC_CARD_THEMES,))
        assert "Bad Hex" not in main._PC_CARD_THEMES, (
            "an unparsable hex was admitted to the map as a cache key")
    finally:
        main._PC_CARD_THEMES.clear()
        main._PC_CARD_THEMES.update(before)
