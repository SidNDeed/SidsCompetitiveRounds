"""The shipped card -> ink colour map, read from migration 333 itself.

Tests seed `main._PC_CARD_THEMES` from here rather than from a literal, so no
test can pass against a colour the migration does not actually ship, and a
hand-edited hex in the SQL shows up as a failing test rather than as a
different picture.
"""

import re
from pathlib import Path

MIGRATION = Path(__file__).resolve().parents[1] / "sql" / "333_pc_card_themes.sql"

_ROW = re.compile(
    r"\(\s*'((?:[^']|'')*)'\s*,\s*'((?:[^']|'')*)'\s*,"
    r"\s*'(#[0-9A-Fa-f]{6})'\s*,\s*'(#[0-9A-Fa-f]{6})'\s*\)")


def rows():
    """(canonical_name, theme, ink_hex, source_hex) for every seeded card."""
    text = MIGRATION.read_text(encoding="utf-8")
    body = text.split("VALUES", 1)[1].split("ON CONFLICT", 1)[0]
    out = [(m.group(1).replace("''", "'"), m.group(2), m.group(3), m.group(4))
           for m in _ROW.finditer(body)]
    if not out:
        raise AssertionError("migration 333 parsed to zero rows")
    return out


def rgb(hex_colour):
    h = hex_colour.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_map():
    """What `_pc_load_card_themes` builds, without a database."""
    return {name: rgb(ink) for name, _theme, ink, _source in rows()}
