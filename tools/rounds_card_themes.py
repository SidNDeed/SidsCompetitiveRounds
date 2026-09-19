#!/usr/bin/env python3
r"""Read every ROUNDS card's theme colour out of the shipped assets, and emit
the seed rows for pc_card_themes.

WHY THIS IS A PARSE AND NOT A TABLE OF HEXES
--------------------------------------------
A card's colour is its THEME, and the themes are data, not code: a decompile
shows a MonoBehaviour's C# field DEFAULTS, never what the prefab ships
(learning #579). Both reads below come out of the installed game files.

  1. THE THEME TABLE -- CardChoice, level0 path_id 3810. The nine themes are an
     INLINE struct array at the TAIL of that MonoBehaviour: a 4-byte count
     followed by count * 36 bytes of {themeType int32, targetColor RGBA floats,
     bgColor RGBA floats}. There is no standalone CardThemeColor asset anywhere
     in the game -- searching for one is how this read gets mis-designed.

  2. CARD -> THEME -- every CardInfo MonoBehaviour in sharedassets0.assets. The
     card's asset name is m_GameObject.deref().read().m_Name; colorTheme is the
     int32 at offset len(raw) - 12.

THE REJECTED OFFSET
-------------------
len(raw) - 4 reads 0 -- DestructiveRed -- for all 67 cards. The CardInfo
decompile puts colorTheme last, so that offset looks right and it is not: the
shipped serialisation carries eight further bytes after it. A reading that
cannot vary is not a reading, so the sweep below is part of the run rather than
a thing done once: it asserts that the accepted offset spans the whole enum
0..8 across the card set, and that the rejected one is still constant.

THE POSITIVE CONTROL
--------------------
Migration 221 recorded two colours read out of these same assets: A_Poison
#4AD652 and A_Parasite #9E79FF. Those are RayHitPoison.color -- a DIFFERENT
read from the theme table, on a different component, at a different offset --
so reproducing them byte for byte says the raw-MonoBehaviour parsing is sound
without saying anything about the theme numbers themselves. It runs before any
theme value is trusted, in every mode. --control runs it alone.

THE CANONICAL-NAME PASS
-----------------------
The assets hold GameObject names ("Poison bullets", "Leach", "Riccochet",
"BombsAway"). pc_prints.top_card holds what the client's
CardRarityLookup.GetCanonicalName produces ("Poison", "Leech", "Ricochet",
"Bombs Away"). Seeding on asset names would silently lose every aliased card:
the renderer would fall back to the rarity band, which is exactly what "no
theme" looks like, so nothing would ever report it. The alias table, the
title-casing and the lookup order below are ported from Plugin.cs
CardRarityLookup (hardAliases, GetCanonicalName, ToTitleCase, ScanAll) and the
result is asserted -- the pre-alias spellings must NOT be keys and the
post-alias ones must be.

THE CONTRAST LIFT
-----------------
source_hex is the game's targetColor, unmodified. hex is the ink actually
drawn, which has to stay legible on the #12141A badge: WCAG contrast ratio
>= 4.5, computed from sRGB relative luminance. Seven of the nine themes clear
it untouched; the two that do not are blended toward white by the smallest
1%-step that clears it, and the run prints the fraction used.

USAGE
    python tools/rounds_card_themes.py              # readable table
    python tools/rounds_card_themes.py --control    # 221 controls only
    python tools/rounds_card_themes.py --emit-sql   # VALUES rows

Reads a default Steam install; set SCR_ROUNDS_DATA to point at another
ROUNDS_Data directory. Needs UnityPy (developed against 1.25.3, Python 3.12).
"""
import argparse
import os
import struct
import sys

import UnityPy

GAME = os.environ.get(
    "SCR_ROUNDS_DATA",
    r"C:\Program Files (x86)\Steam\steamapps\common\ROUNDS\ROUNDS_Data")

# CardThemeColor.CardThemeColorType, in enum order. The parse asserts that the
# themeType values actually present are exactly 0..8, so a game update that
# added a tenth theme fails here rather than silently mislabelling one.
THEMES = ["DestructiveRed", "FirepowerYellow", "DefensiveBlue", "TechWhite",
          "EvilPurple", "PoisonGreen", "NatureBrown", "ColdBlue", "MagicPink"]

CARDCHOICE_FILE = "level0"
CARDCHOICE_PATH_ID = 3810
CARD_FILE = "sharedassets0.assets"
EXPECTED_CARDS = 67

# colorTheme's offset from the end of the CardInfo MonoBehaviour, and the one
# the decompile implies, which reads a constant 0. Both are exercised.
THEME_OFFSET = 12
REJECTED_OFFSET = 4

# Migration 221's two recorded colours, and the GameObjects they came off.
CONTROLS = (("A_Poison", 2580, "#4AD652"),
            ("A_Parasite", 2581, "#9E79FF"))

# The four theme colours migration 337's provenance header recorded.
RECORDED_THEMES = {"DestructiveRed": "#CC4646", "PoisonGreen": "#00934C",
                   "MagicPink": "#D15088", "EvilPurple": "#7A50D1"}

# Demonic Pact is the card 337 traced end to end; it pins the card->theme read.
KNOWN_CARD_THEME = ("Demonic pact", 4)

BADGE_BG = "#12141A"
MIN_CONTRAST = 4.5
LIFT_STEP = 0.01

# Ported verbatim from Plugin.cs CardRarityLookup.hardAliases (:7166). Keyed
# case-insensitively there (OrdinalIgnoreCase), so every lookup here lowercases.
HARD_ALIASES = {
    "Leach": "Leech",
    "Riccochet": "Ricochet",
    "BombsAway": "Bombs Away",
    "Glasscannon": "Glass Cannon",
    "ShieldCharge": "Shield Charge",
    "AbyssalCountdown": "Abyssal Countdown",
    "ChillingPresence": "Chilling Presence",
    "DrillAmmo": "Drill Ammo",
    "RadarShot": "Radar Shot",
    "TargetBounce": "Target Bounce",
    "TasteOfBlood": "Taste Of Blood",
    "Fastball": "Fast Ball",
    "Poison Bullets": "Poison",
    "PoisonBullets": "Poison",
    "Prisitne Perseverence": "Pristine Perseverance",
    "Pristine Perseverence": "Pristine Perseverance",
    "PristinePerseverance": "Pristine Perseverance",
    "PristinePerseverence": "Pristine Perseverance",
}
_ALIASES_CI = {k.lower(): v for k, v in HARD_ALIASES.items()}

# Names that must NOT survive into the seeded table, and the ones that must.
ALIAS_MUST_NOT_APPEAR = ("Poison bullets", "Leach", "Riccochet",
                         "BombsAway", "Glasscannon")
ALIAS_MUST_APPEAR = ("Poison", "Leech", "Ricochet",
                     "Bombs Away", "Glass Cannon", "Wind Up")


class ParseError(RuntimeError):
    """A self-check failed. Never emit a migration after one of these."""


# --------------------------------------------------------------------------
# colour helpers
# --------------------------------------------------------------------------

def hexcol(rgba):
    return "#%02X%02X%02X" % tuple(
        max(0, min(255, round(v * 255))) for v in rgba[:3])


def _channels(hexs):
    return tuple(int(hexs[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def relative_luminance(hexs):
    """WCAG 2.x: sRGB -> linear -> Rec.709 weights."""
    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in _channels(hexs))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def lift_for_contrast(hexs, bg=BADGE_BG, target=MIN_CONTRAST):
    """Smallest blend toward white that clears `target`.

    Returns (hex, fraction). fraction 0.0 means the colour passed untouched.
    The blend is evaluated on the ROUNDED 8-bit result, because that is the
    colour that gets drawn -- measuring the unrounded float would let a value
    that rounds back under the bar report as passing.
    """
    if contrast_ratio(hexs, bg) >= target:
        return hexs, 0.0
    r, g, b = _channels(hexs)
    f = LIFT_STEP
    while f <= 1.0 + 1e-9:
        blended = "#%02X%02X%02X" % tuple(
            max(0, min(255, round((c + f * (1.0 - c)) * 255)))
            for c in (r, g, b))
        if contrast_ratio(blended, bg) >= target:
            return blended, round(f, 4)
        f += LIFT_STEP
    raise ParseError("%s cannot reach contrast %.2f on %s even at full white"
                     % (hexs, target, bg))


# --------------------------------------------------------------------------
# asset reading
# --------------------------------------------------------------------------

def _script_classes():
    ggm = UnityPy.load(os.path.join(GAME, "globalgamemanagers.assets"))
    return {o.path_id: (o.read().m_ClassName or "?")
            for o in ggm.objects if o.type.name == "MonoScript"}


def _read_string(raw, pos):
    """Unity serialized string: int32 length, bytes, pad to a 4-byte boundary."""
    if pos + 4 > len(raw):
        raise ParseError("string length runs off the end at %d" % pos)
    n = struct.unpack_from("<i", raw, pos)[0]
    if n < 0 or pos + 4 + n > len(raw):
        raise ParseError("implausible string length %d at %d" % (n, pos))
    s = raw[pos + 4:pos + 4 + n].decode("utf-8", "replace")
    pos += 4 + n
    return s, pos + ((4 - (n % 4)) % 4)


def run_controls(verbose=True):
    """Re-derive migration 221's two colours. Returns True iff both match."""
    scripts = _script_classes()
    env = UnityPy.load(os.path.join(GAME, CARD_FILE))
    by_pid = {o.path_id: o for o in env.objects}
    ok = True
    for goname, pid, expect in CONTROLS:
        got = None
        obj = by_pid.get(pid)
        if obj is not None:
            for comp in obj.read().m_Components:
                c = comp.deref()
                if c.type.name != "MonoBehaviour":
                    continue
                d = c.read(check_read=False)
                if not scripts.get(d.m_Script.m_PathID, "").startswith("RayHit"):
                    continue
                raw = c.get_raw_data()
                # RayHit*: 32-byte MonoBehaviour header (empty m_Name), then
                # priority/soundEvent/time/interval, then `color` last.
                got = hexcol(struct.unpack_from("<4f", raw, len(raw) - 16))
                break
        good = (got == expect)
        ok = ok and good
        if verbose:
            print("control %-12s expected %s got %-8s %s"
                  % (goname, expect, got or "(none)", "PASS" if good else "FAIL"))
    return ok


def parse_theme_table():
    """The inline cardThemes[] array at the tail of CardChoice."""
    env = UnityPy.load(os.path.join(GAME, CARDCHOICE_FILE))
    scripts = _script_classes()
    found = [o for o in env.objects
             if o.type.name == "MonoBehaviour"
             and scripts.get(o.read(check_read=False).m_Script.m_PathID) == "CardChoice"]
    if len(found) != 1:
        raise ParseError("expected exactly one CardChoice in %s, found %d"
                         % (CARDCHOICE_FILE, len(found)))
    obj = found[0]
    if obj.path_id != CARDCHOICE_PATH_ID:
        raise ParseError("CardChoice moved: path_id %d, expected %d"
                         % (obj.path_id, CARDCHOICE_PATH_ID))
    raw = obj.get_raw_data()

    themes = None
    for count in range(1, 33):
        need = 4 + count * 36
        if need > len(raw):
            break
        off = len(raw) - need
        if struct.unpack_from("<i", raw, off)[0] != count:
            continue
        out, ok, p = [], True, off + 4
        for _ in range(count):
            t = struct.unpack_from("<i", raw, p)[0]
            tc = struct.unpack_from("<4f", raw, p + 4)
            bg = struct.unpack_from("<4f", raw, p + 20)
            if not (0 <= t < len(THEMES)) or not all(
                    -0.01 <= v <= 1.01 for v in tc + bg):
                ok = False
                break
            out.append((t, tc, bg))
            p += 36
        if ok:
            themes = out
            break
    if themes is None:
        raise ParseError("tail parse of CardChoice.cardThemes[] failed")

    if len(themes) != len(THEMES):
        raise ParseError("expected %d themes, parsed %d"
                         % (len(THEMES), len(themes)))
    if sorted(t for t, _, _ in themes) != list(range(len(THEMES))):
        raise ParseError("themeType values are not exactly 0..%d: %s"
                         % (len(THEMES) - 1, sorted(t for t, _, _ in themes)))

    table = {}
    for t, tc, bg in themes:
        table[THEMES[t]] = {"index": t, "source_hex": hexcol(tc),
                            "bg_hex": hexcol(bg), "rgba": tuple(tc)}
    for name, expect in RECORDED_THEMES.items():
        got = table[name]["source_hex"]
        if got != expect:
            raise ParseError("%s is %s, migration 337 recorded %s"
                             % (name, got, expect))
    return table


def load_cards():
    """Every CardInfo: asset name, serialized cardName, colorTheme index."""
    scripts = _script_classes()
    env = UnityPy.load(os.path.join(GAME, CARD_FILE))
    cards = []
    for o in env.objects:
        if o.type.name != "MonoBehaviour":
            continue
        try:
            d = o.read(check_read=False)
        except Exception:
            continue
        if scripts.get(d.m_Script.m_PathID) != "CardInfo":
            continue
        try:
            go_name = d.m_GameObject.deref().read().m_Name
        except Exception:
            raise ParseError("CardInfo %d has no resolvable GameObject"
                             % o.path_id)
        raw = o.get_raw_data()
        # MonoBehaviour header: m_GameObject PPtr(12), m_Enabled(1, aligned to
        # 4), m_Script PPtr(12), m_Name string. Then CardInfo's own fields:
        # soundDisableBlockBasic (bool, aligned) and then cardName.
        m_name, p = _read_string(raw, 12 + 4 + 12)
        if m_name != "":
            raise ParseError("CardInfo %d has m_Name %r; the field offsets "
                             "below assume the component is unnamed"
                             % (o.path_id, m_name))
        card_name, _ = _read_string(raw, p + 4)
        cards.append({"asset_name": go_name, "card_name": card_name,
                      "path_id": o.path_id, "raw": raw,
                      "theme_index": struct.unpack_from(
                          "<i", raw, len(raw) - THEME_OFFSET)[0]})
    cards.sort(key=lambda c: c["asset_name"].lower())
    return cards


def check_offsets(cards):
    """probe8's sweep, re-run: the accepted offset varies, the rejected one
    does not. Returns the sweep for reporting."""
    sweep = []
    for back in range(4, 41, 4):
        vals = [struct.unpack_from("<i", c["raw"], len(c["raw"]) - back)[0]
                for c in cards]
        sweep.append((back, sorted(set(vals))))

    accepted = sorted({c["theme_index"] for c in cards})
    if accepted != list(range(len(THEMES))):
        raise ParseError(
            "colorTheme at len-%d does not span the enum: distinct values %s. "
            "A reading that cannot vary is not a reading."
            % (THEME_OFFSET, accepted))

    rejected = {struct.unpack_from("<i", c["raw"], len(c["raw"]) - REJECTED_OFFSET)[0]
                for c in cards}
    if len(rejected) != 1:
        raise ParseError(
            "len-%d now varies (%s). It read a constant 0 when this parse was "
            "written, which is why it was rejected; if it varies, the "
            "serialisation changed and both offsets need re-deriving."
            % (REJECTED_OFFSET, sorted(rejected)))
    return sweep, rejected.pop()


# --------------------------------------------------------------------------
# canonical names -- ported from Plugin.cs CardRarityLookup
# --------------------------------------------------------------------------

def to_title_case(text):
    """Plugin.cs ToTitleCase (:7285). Invariant casing on purpose: a
    culture-sensitive lower() turns "WIND UP" into a dotless-i twin on a tr-TR
    client, and card names are DB keys (#47 family, migration 195)."""
    if not text:
        return text
    words = text.lower().split(" ")
    return " ".join((w[0].upper() + w[1:]) if w else w for w in words)


def build_canonicaliser(cards):
    """Reproduce ScanAll (:7302) + GetCanonicalName (:7223).

    ScanAll registers the serialized cardName, then registers the GameObject
    name pointing AT that cardName, then back-fills the hard aliases for any
    target that is already known. GetCanonicalName applies the alias first and
    title-cases whatever the canonical map returns.
    """
    lookup = {}      # lower(name) -> present
    canonical = {}   # lower(name) -> canonical spelling
    for c in cards:
        card_name = c["card_name"] or c["asset_name"].replace("(Clone)", "").strip()
        if not card_name:
            continue
        lookup[card_name.lower()] = True
        canonical.setdefault(card_name.lower(), card_name)
        go = c["asset_name"].replace("(Clone)", "").strip()
        if go:
            lookup[go.lower()] = True
            canonical[go.lower()] = card_name
    for raw_name, target in HARD_ALIASES.items():
        if target.lower() in lookup:
            lookup[raw_name.lower()] = True
            canonical[raw_name.lower()] = target

    def get_canonical(name):
        if not name:
            return name
        alias = _ALIASES_CI.get(name.lower())
        if alias is not None:
            name = alias
        canon = canonical.get(name.lower())
        if canon is not None:
            return to_title_case(canon)
        return name

    return get_canonical


# --------------------------------------------------------------------------
# the parse, end to end
# --------------------------------------------------------------------------

def build():
    if not run_controls(verbose=False):
        raise ParseError(
            "migration 221's controls did not reproduce. The raw-MonoBehaviour "
            "parsing is wrong or the assets changed -- nothing downstream of "
            "this is trustworthy. Run --control for the detail.")

    table = parse_theme_table()
    cards = load_cards()
    if len(cards) != EXPECTED_CARDS:
        raise ParseError("expected %d CardInfo objects, found %d"
                         % (EXPECTED_CARDS, len(cards)))
    sweep, rejected_value = check_offsets(cards)

    known_name, known_theme = KNOWN_CARD_THEME
    hit = [c for c in cards if c["asset_name"] == known_name]
    if len(hit) != 1 or hit[0]["theme_index"] != known_theme:
        raise ParseError("%s should read theme %d, got %s"
                         % (known_name, known_theme,
                            [c["theme_index"] for c in hit] or "no such card"))

    # ink per theme, computed once
    for name, row in table.items():
        row["hex"], row["lift"] = lift_for_contrast(row["source_hex"])
        row["cr_source"] = contrast_ratio(row["source_hex"], BADGE_BG)
        row["cr_ink"] = contrast_ratio(row["hex"], BADGE_BG)
        if row["cr_ink"] < MIN_CONTRAST:
            raise ParseError("%s ink %s scores %.2f, under %.2f"
                             % (name, row["hex"], row["cr_ink"], MIN_CONTRAST))

    canonicalise = build_canonicaliser(cards)
    rows = []
    for c in cards:
        theme = THEMES[c["theme_index"]]
        rows.append({"asset_name": c["asset_name"],
                     "card_name": c["card_name"],
                     "canonical": canonicalise(c["asset_name"]),
                     "theme": theme,
                     "source_hex": table[theme]["source_hex"],
                     "hex": table[theme]["hex"],
                     "cr": table[theme]["cr_ink"]})

    keys = {r["canonical"] for r in rows}
    for name in ALIAS_MUST_NOT_APPEAR:
        if name in keys:
            raise ParseError(
                "%r survived into the seed keys. The alias pass did not run, "
                "and every aliased card would fall back to its rarity band -- "
                "which is indistinguishable from having no theme at all."
                % name)
    for name in ALIAS_MUST_APPEAR:
        if name not in keys:
            raise ParseError("%r is missing from the seed keys" % name)
    if len(keys) != len(rows):
        seen, dupes = set(), set()
        for r in rows:
            if r["canonical"] in seen:
                dupes.add(r["canonical"])
            seen.add(r["canonical"])
        raise ParseError("two assets canonicalise onto the same name: %s"
                         % sorted(dupes))

    rows.sort(key=lambda r: r["canonical"].lower())
    return {"rows": rows, "table": table, "sweep": sweep,
            "rejected_value": rejected_value}


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def sql_literal(text):
    return "'" + text.replace("'", "''") + "'"


def emit_sql(result):
    lines = []
    for i, r in enumerate(result["rows"]):
        lines.append("    (%s, %s, %s, %s)%s"
                     % (sql_literal(r["canonical"]), sql_literal(r["theme"]),
                        sql_literal(r["hex"]), sql_literal(r["source_hex"]),
                        "," if i < len(result["rows"]) - 1 else ""))
    return "\n".join(lines)


def human(result):
    out = []
    out.append("offset sweep over %d CardInfo objects (distinct int32 values):"
               % len(result["rows"]))
    for back, vals in result["sweep"]:
        mark = ""
        if back == THEME_OFFSET:
            mark = "  <- colorTheme"
        elif back == REJECTED_OFFSET:
            mark = "  <- rejected: constant"
        out.append("  len-%-3d %d distinct %s%s"
                   % (back, len(vals), vals[:12], mark))
    out.append("")
    out.append("themes (badge background %s, floor %.1f):" % (BADGE_BG, MIN_CONTRAST))
    out.append("  %-16s %-9s %-9s %-7s %-7s %s"
               % ("theme", "source", "ink", "CRsrc", "CRink", "lift"))
    for name in THEMES:
        row = result["table"][name]
        out.append("  %-16s %-9s %-9s %7.2f %7.2f  %s"
                   % (name, row["source_hex"], row["hex"],
                      row["cr_source"], row["cr_ink"],
                      "-" if not row["lift"] else "%.0f%% toward white" % (row["lift"] * 100)))
    out.append("")
    out.append("cards (%d):" % len(result["rows"]))
    out.append("  %-24s %-24s %-16s %-9s %-9s %s"
               % ("asset name", "canonical", "theme", "source", "ink", "CR"))
    for r in result["rows"]:
        alias = " *" if r["asset_name"] != r["canonical"] else ""
        out.append("  %-24s %-24s %-16s %-9s %-9s %5.2f%s"
                   % (r["asset_name"], r["canonical"], r["theme"],
                      r["source_hex"], r["hex"], r["cr"], alias))
    renamed = [r for r in result["rows"] if r["asset_name"] != r["canonical"]]
    out.append("")
    out.append("* %d of %d asset names differ from their canonical form."
               % (len(renamed), len(result["rows"])))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--control", action="store_true",
                    help="run migration 221's positive controls and stop")
    ap.add_argument("--emit-sql", action="store_true",
                    help="print the migration's VALUES rows")
    args = ap.parse_args()

    if args.control:
        return 0 if run_controls() else 1

    try:
        result = build()
    except ParseError as exc:
        print("PARSE FAILED: %s" % exc, file=sys.stderr)
        return 2

    print(emit_sql(result) if args.emit_sql else human(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
