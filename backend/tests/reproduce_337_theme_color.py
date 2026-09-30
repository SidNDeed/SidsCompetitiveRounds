"""Re-derive migration 337's hex from the SHIPPED Unity assets, and re-derive
the shop distances that migration quotes (#579).

Not a pytest: the first half needs the installed game, which no test
environment is entitled to assume. It exists so the provenance comment in
`backend/sql/337_demon_body_color.sql` is a READING anyone can repeat rather
than a number someone once wrote down, and so the next body colour taken from
a card theme has a script to run instead of a procedure to re-invent.

    python backend/tests/reproduce_337_theme_color.py [ROUNDS_Data path]
    python backend/tests/reproduce_337_theme_color.py --distances

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
     named cards and lands where each card's look says it should.

Nothing is trusted unless the controls come back right, and EVERY control
here can fail the run:

  * the colours whose NAMES state what they must be -- DestructiveRed
    #CC4646, PoisonGreen #00934C, MagicPink #D15088;
  * four cards whose theme is legible from the card itself, identified by the
    NAME READ OUT OF THE ASSET rather than by a name written down beside the
    path_id here -- a mapping this file asserted would be a fixture agreeing
    with itself, and would keep agreeing if the path_ids moved;
  * the neighbouring offsets, which must be CONSTANT across every card read.
    A neighbour that also varies means -12 is no longer singled out by
    variation, and the run STOPS. An earlier version printed a note and
    carried on to a successful MATCHES line, which is a control that cannot
    fail (#342/#391).

`--distances` needs no game: it reads every body colour the migrations seed
out of backend/sql, converts to CIELAB and reports dE76 from 337's hex. Its
control is 221's own published numbers -- Lime 24, Emerald 31, Neon Lime 33,
Forest 55 from the poison green -- reproduced by this same code before any
337 number is printed.
"""
import re
import struct
import sys
from pathlib import Path

DEFAULT_DATA = Path(r"C:/Program Files (x86)/Steam/steamapps/common/ROUNDS/ROUNDS_Data")
SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

THEME_NAMES = ["DestructiveRed", "FirepowerYellow", "DefensiveBlue", "TechWhite",
               "EvilPurple", "PoisonGreen", "NatureBrown", "ColdBlue", "MagicPink"]

# Controls: themes whose name states what the colour has to be.
COLOR_CONTROLS = {0: "#CC4646", 5: "#00934C", 8: "#D15088"}

# Controls: cards whose theme is legible from the card itself, keyed by the
# NAME the asset carries. The path_id for each is resolved by reading names
# out of the file, so nothing here encodes the path_id -> name mapping.
CARD_CONTROLS = {"Poison bullets": 5, "Cold bullets": 7, "Tank": 2,
                 "Explosive bullet": 0}

SUBJECT_NAME = "Demonic pact"
SUBJECT_PATH_ID = 10145         # reported, and CHECKED against the name read back
WANT_THEME = 4                  # EvilPurple
WANT_HEX = "#7A50D1"
CARD_CHOICE_PATH_ID = 3810
THEME_OFFSET_FROM_END = 12       # what the migration records; the run DERIVES it
SEARCH_OFFSETS = (4, 8, 12, 16, 20, 24)
NEIGHBOUR_OFFSETS = (4, 8, 16)

# 221's published distances from the poison green, which this implementation
# must reproduce before any 337 number is believed.
POISON_HEX = "#4AD652"
POISON_PUBLISHED = {"Lime": 24, "Emerald": 31, "Neon Lime": 33, "Forest": 55}
DEMONIC_HEX = WANT_HEX


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


def _mono_pointers(raw):
    """(m_GameObject, m_Script) ids out of a MonoBehaviour's raw bytes.

    Read from the bytes rather than through a typetree: these MonoBehaviours
    are script-backed and UnityPy cannot deserialize them (it stops short on
    CardInfo), which is the same reason the theme int is read by offset. The
    header is fixed for this serialization version -- PPtr m_GameObject (int
    file, long path), byte m_Enabled plus 3 bytes of alignment, PPtr m_Script
    -- so the two pointers sit at 0 and 16.
    """
    return struct.unpack_from("<iq", raw, 0), struct.unpack_from("<iq", raw, 16)


def read_cards(data_dir, names_wanted):
    """Find each wanted card BY NAME and derive which component and which
    offset carry colorTheme. Returns (script id, {name: (path_id, {off: int})}).

    NOTHING here encodes a path_id, a component or an offset. A name written
    down beside a path_id would be a fixture agreeing with itself: it would go
    on agreeing after the ids moved, which is the drift this reproduction
    exists to catch. Instead:

      * each card is the GameObject carrying that NAME in the asset;
      * every card prefab runs the same handful of scripts, so the component
        is not singled out by being shared -- it is singled out together with
        the offset, by SEARCHING every (script, offset) pair for the one whose
        int is a valid themeType (0..8) on every card AND is not the same on
        all of them. A reading that cannot vary is not a reading.
      * that search must return EXACTLY ONE pair. If a second pair qualifies
        -- a neighbouring offset that has started to vary, a second component
        that looks the same -- the choice is no longer justified by variation
        and the run STOPS here rather than printing a note and continuing.

    The four cards whose theme is legible from the card itself are then an
    INDEPENDENT check on what the search picked, in main().
    """
    import UnityPy
    env = UnityPy.load(str(Path(data_dir) / "sharedassets0.assets"))
    want = set(names_wanted)

    name_of_go = {}
    for obj in env.objects:
        if obj.type.name != "GameObject":
            continue
        try:
            name = obj.read().m_Name
        except Exception:
            continue
        if name in want:
            if name in name_of_go.values():
                raise SystemExit("more than one GameObject is named %r; the cards "
                                 "cannot be identified by name" % name)
            name_of_go[obj.path_id] = name
    missing = want - set(name_of_go.values())
    if missing:
        raise SystemExit("these cards were not found by name in the assets: %s"
                         % sorted(missing))

    components = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        raw = obj.get_raw_data()
        if len(raw) < 32:
            continue
        go, script = _mono_pointers(raw)
        if go[0] != 0 or go[1] not in name_of_go:
            continue
        components.setdefault(name_of_go[go[1]], {})[script] = (obj.path_id, raw)

    shared = sorted(set.intersection(*(set(v) for v in components.values())))
    candidates = []
    for script in shared:
        for back in SEARCH_OFFSETS:
            vals = {}
            for name, comps in components.items():
                pid, raw = comps[script]
                if len(raw) < back:
                    vals = None
                    break
                vals[name] = struct.unpack_from("<i", raw, len(raw) - back)[0]
            if not vals:
                continue
            if all(0 <= v <= 8 for v in vals.values()) and len(set(vals.values())) > 1:
                candidates.append((script, back))
    if len(candidates) != 1:
        raise SystemExit(
            "the (component, offset) search returned %d candidates (%s), not one. "
            "colorTheme is singled out ONLY by being the one int that is a valid "
            "themeType on every card and is not the same on all of them, so any "
            "other number of candidates withdraws that justification and this "
            "reading is not trusted."
            % (len(candidates), [(s[1], -b) for s, b in candidates]))
    script, offset = candidates[0]
    if offset != THEME_OFFSET_FROM_END:
        print("NOTE: colorTheme derived at -%d; the migration records -%d"
              % (offset, THEME_OFFSET_FROM_END))

    out = {}
    for name, comps in components.items():
        pid, raw = comps[script]
        out[name] = (pid, {back: struct.unpack_from("<i", raw, len(raw) - back)[0]
                           for back in SEARCH_OFFSETS if len(raw) >= back})
    print("colorTheme derived: component m_Script path_id %d, offset -%d "
          "(searched %d shared components x %d offsets, exactly one qualified)"
          % (script[1], offset, len(shared), len(SEARCH_OFFSETS)))
    return offset, out


# ── CIELAB, for the shop-distance half ────────────────────────────────────

def _srgb_to_lab(hex_str):
    h = hex_str.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    r, g, b = lin
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / 1.00000
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t):
        return t ** (1.0 / 3.0) if t > 216.0 / 24389.0 else (841.0 / 108.0) * t + 4.0 / 29.0

    fx, fy, fz = f(x), f(y), f(z)
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def de76(a, b):
    la, lb = _srgb_to_lab(a), _srgb_to_lab(b)
    return sum((x - y) ** 2 for x, y in zip(la, lb)) ** 0.5


SEED_ROW = re.compile(
    r"\(\s*'(pcolor_[a-z0-9_]+)'\s*,\s*'player_color'\s*,\s*'([^']+)'.*?'(#[0-9A-Fa-f]{6})'\s*\)",
    re.S)


def read_seeded_colors(exclude_sku=None):
    """Every player_color SKU the migrations seed, read out of backend/sql."""
    out = {}
    for path in sorted(SQL_DIR.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        for sku, name, hexv in SEED_ROW.findall(text):
            if sku == exclude_sku:
                continue
            out.setdefault(sku, (name, hexv.upper(), path.name))
    return out


def distances():
    # 337's own row is excluded: the question is how close the NEW colour sits
    # to what is already in the shop, and including it answers 0.0.
    colors = read_seeded_colors(exclude_sku="pcolor_demonic")
    print("read %d player_color SKUs out of %s (337's own row excluded)"
          % (len(colors), SQL_DIR.name))

    # CONTROL: this implementation must reproduce 221's published numbers.
    by_name = {v[0]: v[1] for v in colors.values()}
    bad = {}
    for name, published in POISON_PUBLISHED.items():
        if name not in by_name:
            bad[name] = "not seeded"
            continue
        got = de76(POISON_HEX, by_name[name])
        if round(got) != published:
            bad[name] = "%.1f, published %d" % (got, published)
    if bad:
        raise SystemExit("221 CONTROL FAILED: %s -- this implementation does not "
                         "reproduce the published poison distances, so its 337 "
                         "numbers are not trusted" % bad)
    print("221 control OK: " + ", ".join(
        "%s=%d" % (n, round(de76(POISON_HEX, by_name[n]))) for n in POISON_PUBLISHED))

    ranked = sorted(((de76(DEMONIC_HEX, hexv), name, hexv)
                     for name, hexv, _f in colors.values()), key=lambda r: r[0])
    print("\ndE76 from %s (migration 337), nearest first:" % DEMONIC_HEX)
    for d, name, hexv in ranked[:6]:
        print("  %-14s %s  %.1f" % (name, hexv, d))
    print("\nnearest is %s at %.1f" % (ranked[0][1], ranked[0][0]))
    return 0


def assets(data_dir):
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

    # ── read 2: which theme each card uses, cards found BY NAME ────────────
    offset, cards = read_cards(data_dir, list(CARD_CONTROLS) + [SUBJECT_NAME])
    print("\nCardInfo colorTheme, and its neighbours (the negative control):")
    print("  %-18s %-10s %s" % ("card", "path_id",
                                "  ".join("-%-6d" % b for b in (4, 8, 12, 16))))
    for name in list(CARD_CONTROLS) + [SUBJECT_NAME]:
        pid, vals = cards[name]
        print("  %-18s %-10d %s" % (name, pid,
                                    "  ".join("%-7d" % vals[b] for b in (4, 8, 12, 16))))

    subject_pid = cards[SUBJECT_NAME][0]
    if subject_pid != SUBJECT_PATH_ID:
        print("NOTE: %s is path_id %d here; the migration records %d"
              % (SUBJECT_NAME, subject_pid, SUBJECT_PATH_ID))

    # The neighbouring offsets, reported and REQUIRED to be constant. The
    # search above already refuses to proceed when a second offset varies --
    # that is what "exactly one candidate" means -- and this states the same
    # property in the terms the migration comment uses, so a reader can see
    # it rather than infer it from a count.
    varying = {}
    for back in NEIGHBOUR_OFFSETS:
        seen = {cards[n][1][back] for n in cards}
        if len(seen) != 1:
            varying[back] = sorted(seen)
    if varying:
        raise SystemExit(
            "NEIGHBOUR CONTROL FAILED: %s also vary across the cards read. The "
            "choice of -%d is justified ONLY by being the one offset that "
            "varies, so another varying offset withdraws that justification and "
            "this reading is not trusted." % (varying, offset))
    print("neighbour control OK: offsets %s are constant across all %d cards"
          % (", ".join("-%d" % b for b in NEIGHBOUR_OFFSETS), len(cards)))

    wrong = {n: cards[n][1][offset]
             for n, exp in CARD_CONTROLS.items()
             if cards[n][1][offset] != exp}
    if wrong:
        raise SystemExit("CARD CONTROLS FAILED: %s -- the offset is not colorTheme" % wrong)
    print("card controls OK: " + ", ".join(
        "%s=%s" % (n, THEME_NAMES[e]) for n, e in CARD_CONTROLS.items()))

    # ── the two reads, joined ──────────────────────────────────────────────
    theme = cards[SUBJECT_NAME][1][offset]
    got = _hex(rows[theme][1])
    print("\n%s: colorTheme=%d (%s) -> %s" % (SUBJECT_NAME, theme, THEME_NAMES[theme], got))
    if theme != WANT_THEME or got != WANT_HEX:
        raise SystemExit("MISMATCH: migration 337 seeds %s from themeType %d"
                         % (WANT_HEX, WANT_THEME))
    print("MATCHES migration 337's preview_color %s" % WANT_HEX)
    return 0


def main():
    argv = [a for a in sys.argv[1:]]
    if "--distances" in argv:
        return distances()
    data_dir = Path(argv[0]) if argv else DEFAULT_DATA
    return assets(data_dir)


if __name__ == "__main__":
    sys.exit(main())
