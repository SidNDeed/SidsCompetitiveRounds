"""Re-derive migration 337's hex from the SHIPPED Unity assets (#579).

Not a pytest: it needs the installed game, which no test environment is
entitled to assume. It exists so the provenance comment in
`backend/sql/337_demon_body_color.sql` is a READING anyone can repeat rather
than a number someone once wrote down, and so the next body colour taken from
a card theme has a script to run instead of a procedure to re-invent.

    python backend/tests/reproduce_337_theme_color.py [ROUNDS_Data path]

Why the assets and not the decompile: a decompile shows a MonoBehaviour's C#
field DEFAULTS, not what the prefab ships (#579). Both reads below are out of
the serialized data.

  1. CardChoice (level0, path_id 3810) carries `public CardThemeColor[]
     cardThemes`, and CardThemeColor serializes as { int themeType; Color
     targetColor; Color bgColor; } -- 4 + 16 + 16 = 36 bytes, behind a 4-byte
     array count. The table is located by that SHAPE -- a count of 9, then
     nine records whose themeType is 0..8 in order and whose colour
     components are all in [0,1] -- never by a hardcoded offset.

  2. A card's own theme is the int 12 bytes before the end of its CardInfo
     serialized data. That offset is not asserted from the layout; it is the
     only offset within 64 bytes of the end whose value VARIES across the
     named cards and lands where each card's look says it should. The script
     prints its neighbours, which are constant across every card -- a reading
     that cannot vary is not a reading, and that is the exact defect the
     migration's own comment records rejecting.

Nothing is trusted unless the colours whose NAMES state what they must be
come back right: DestructiveRed #CC4646, PoisonGreen #00934C, MagicPink
#D15088, and four cards whose theme is legible from the card itself.
"""
import struct
import sys
from pathlib import Path

DEFAULT_DATA = Path(r"C:/Program Files (x86)/Steam/steamapps/common/ROUNDS/ROUNDS_Data")

THEME_NAMES = ["DestructiveRed", "FirepowerYellow", "DefensiveBlue", "TechWhite",
               "EvilPurple", "PoisonGreen", "NatureBrown", "ColdBlue", "MagicPink"]

# Controls: themes whose name states what the colour has to be.
COLOR_CONTROLS = {0: "#CC4646", 5: "#00934C", 8: "#D15088"}

# Controls: cards whose theme is legible from the card itself. Demonic pact is
# the subject and is deliberately NOT a control.
CARD_CONTROLS = {10115: ("Poison bullets", 5), 10162: ("Cold bullets", 7),
                 10134: ("Tank", 2), 10107: ("Explosive bullet", 0)}

SUBJECT = (10145, "Demonic pact")
WANT_THEME = 4                  # EvilPurple
WANT_HEX = "#7A50D1"
CARD_CHOICE_PATH_ID = 3810
THEME_OFFSET_FROM_END = 12


def _hex(rgba):
    r, g, b = (max(0.0, min(1.0, c)) for c in rgba[:3])
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def _raw(env, path_id):
    for obj in env.objects:
        if obj.path_id == path_id:
            return obj.get_raw_data()
    raise SystemExit("path_id %d not found" % path_id)


def read_theme_table(data_dir):
    """The nine-row theme table out of CardChoice's serialized fields."""
    import UnityPy
    raw = _raw(UnityPy.load(str(Path(data_dir) / "level0")), CARD_CHOICE_PATH_ID)
    n = len(THEME_NAMES)
    last = len(raw) - 4 - n * 36
    for off in range(0, last + 1):          # inclusive: the table can start here
        if struct.unpack_from("<i", raw, off)[0] != n:
            continue
        rows, ok = [], True
        for i in range(n):
            base = off + 4 + i * 36
            theme = struct.unpack_from("<i", raw, base)[0]
            target = struct.unpack_from("<4f", raw, base + 4)
            bg = struct.unpack_from("<4f", raw, base + 20)
            if theme != i or not all(-0.001 <= c <= 1.001 for c in target + bg):
                ok = False
                break
            rows.append((theme, target, bg))
        if ok:
            return off, rows
    raise SystemExit("no 9-row theme table found in CardChoice")


def read_card_themes(data_dir, path_ids):
    """Each card's colorTheme, plus the neighbouring ints as the control."""
    import UnityPy
    env = UnityPy.load(str(Path(data_dir) / "sharedassets0.assets"))
    out = {}
    for pid in path_ids:
        raw = _raw(env, pid)
        out[pid] = {back: struct.unpack_from("<i", raw, len(raw) - back)[0]
                    for back in (4, 8, 12, 16)}
    return out


def main():
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA
    if not data_dir.exists():
        raise SystemExit("ROUNDS_Data not found at %s" % data_dir)

    # ── read 1: the theme table ────────────────────────────────────────────
    off, rows = read_theme_table(data_dir)
    print("cardThemes found at raw offset %d in CardChoice (path_id %d)"
          % (off, CARD_CHOICE_PATH_ID))
    for theme, target, _bg in rows:
        print("  %-16s themeType=%d  %s  rgba=(%.4f, %.4f, %.4f, %.1f)"
              % (THEME_NAMES[theme], theme, _hex(target), *target))
    bad = {THEME_NAMES[i]: _hex(rows[i][1])
           for i, want in COLOR_CONTROLS.items() if _hex(rows[i][1]) != want}
    if bad:
        raise SystemExit("COLOUR CONTROLS FAILED: %s -- the parse is not trusted" % bad)
    print("colour controls OK: "
          + ", ".join("%s=%s" % (THEME_NAMES[i], h) for i, h in COLOR_CONTROLS.items()))

    # ── read 2: which theme the card uses ──────────────────────────────────
    ids = [SUBJECT[0]] + list(CARD_CONTROLS)
    themes = read_card_themes(data_dir, ids)
    names = {SUBJECT[0]: SUBJECT[1]}
    names.update({p: n for p, (n, _) in CARD_CONTROLS.items()})
    print("\nCardInfo colorTheme, and its neighbours (the negative control):")
    print("  %-18s %s" % ("card", "  ".join("-%-6d" % b for b in (4, 8, 12, 16))))
    for pid in ids:
        print("  %-18s %s" % (names[pid],
                              "  ".join("%-7d" % themes[pid][b] for b in (4, 8, 12, 16))))
    for back in (4, 8, 16):
        seen = {themes[p][back] for p in ids}
        if len(seen) != 1:
            print("  NOTE: offset -%d also varies (%s); the choice of -%d is no longer "
                  "uniquely justified by variation alone" % (back, sorted(seen),
                                                             THEME_OFFSET_FROM_END))
    wrong = {names[p]: themes[p][THEME_OFFSET_FROM_END]
             for p, (_n, exp) in CARD_CONTROLS.items()
             if themes[p][THEME_OFFSET_FROM_END] != exp}
    if wrong:
        raise SystemExit("CARD CONTROLS FAILED: %s -- the offset is not colorTheme" % wrong)
    print("card controls OK: " + ", ".join(
        "%s=%s" % (n, THEME_NAMES[e]) for _p, (n, e) in CARD_CONTROLS.items()))

    # ── the two reads, joined ──────────────────────────────────────────────
    theme = themes[SUBJECT[0]][THEME_OFFSET_FROM_END]
    got = _hex(rows[theme][1])
    print("\n%s: colorTheme=%d (%s) -> %s" % (SUBJECT[1], theme, THEME_NAMES[theme], got))
    if theme != WANT_THEME or got != WANT_HEX:
        raise SystemExit("MISMATCH: migration 337 seeds %s from themeType %d"
                         % (WANT_HEX, WANT_THEME))
    print("MATCHES migration 337's preview_color %s" % WANT_HEX)
    return 0


if __name__ == "__main__":
    sys.exit(main())
