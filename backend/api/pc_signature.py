"""The autograph's styling on a signed Player Card (Sept 14 batch, S5).

A signed print carries its subject's autograph, and since this batch the
autograph wears the subject's OWN shop name styling: the colour, neon,
gradient or rainbow their nametag shows in game, its weight and slant,
underline or strike, letter case and spacing, its size band, and the halo of
a glow. The tables here mirror plugin/NametagStyler.cs — a test parses that
file and pins every hex code, every SKU and the layer order against these —
and the families the still image has no form for (the floating name, the
typefaces) are listed as IGNORED so a client SKU this module has not decided
about fails the pin instead of slipping past unhandled (#126: every render
path is taught explicitly).

`signature_style(skus)` turns a subject's active nametag SKUs (any order,
any mix, ids the shop no longer knows dropped upstream) into ONE canonical
style dict — the face spec's `sign` field — composed as the client composes
them: a rainbow or gradient replaces the colour, otherwise the first colour
in the client's layer order wins; the first case SKU and the first size SKU
in their layer orders win; the four flags stack. The dict has a fixed key set
in sorted order, so `face_rev` hashes it stably, and it is None when nothing
applies, so an unstyled subject's signed print keys and draws exactly as it
did before this batch.
"""
from __future__ import annotations

from typing import Iterable


def _rgb(hex_code: str) -> tuple[int, int, int]:
    value = hex_code.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % tuple(int(v) for v in rgb)


def _unity(r: float, g: float, b: float) -> tuple[int, int, int]:
    """A Unity Color's float channels as the bytes ColorUtility.ToHtmlStringRGB writes."""
    return tuple(min(255, max(0, int(round(v * 255)))) for v in (r, g, b))


# ── the client's tables, mirrored ─────────────────────────────────────────

# <color=#RRGGBB> per SKU, in the client's colour LAYER order (the first one
# present wins when several are equipped).
COLOUR_ORDER: tuple[str, ...] = (
    "nametag_color_red", "nametag_color_cyan", "nametag_color_gold",
    "nametag_color_purple", "nametag_color_green", "nametag_color_pink",
    "nametag_color_emerald", "nametag_color_amber",
    "nametag_color_coral", "nametag_color_indigo",
    "nametag_neon_pink", "nametag_neon_cyan", "nametag_neon_lime",
    "nametag_neon_orange", "nametag_neon_violet", "nametag_neon_toxic",
    "nametag_neon_glowyellow",
)
COLOURS: dict[str, tuple[int, int, int]] = {
    "nametag_color_red": _rgb("#FF5566"),
    "nametag_color_cyan": _rgb("#55CCFF"),
    "nametag_color_gold": _rgb("#FFCC44"),
    "nametag_color_purple": _rgb("#BB88FF"),
    "nametag_color_green": _rgb("#77DD88"),
    "nametag_color_pink": _rgb("#FF99CC"),
    "nametag_color_emerald": _rgb("#3DDB7B"),
    "nametag_color_amber": _rgb("#FFB347"),
    "nametag_color_coral": _rgb("#FF7E72"),
    "nametag_color_indigo": _rgb("#7A6BFF"),
    "nametag_neon_pink": _rgb("#FF1F8C"),
    "nametag_neon_cyan": _rgb("#1FF0FF"),
    "nametag_neon_lime": _rgb("#5BFF1F"),
    "nametag_neon_orange": _rgb("#FF7A1F"),
    "nametag_neon_violet": _rgb("#D420FF"),
    "nametag_neon_toxic": _rgb("#A8FF1F"),
    "nametag_neon_glowyellow": _rgb("#FFFB9D"),
}
# The halo under the letters: the client's GetGlowColor table (its float
# channels, as Unity holds them). A plain glow SKU is the dedicated "glow"
# slot; a neon doubles as its own halo when no plain glow is worn.
GLOWS: dict[str, tuple[int, int, int]] = {
    "nametag_glow_red": _unity(1.00, 0.27, 0.33),
    "nametag_glow_blue": _unity(0.27, 0.53, 1.00),
    "nametag_glow_gold": _unity(1.00, 0.80, 0.27),
    "nametag_glow_pink": _unity(1.00, 0.53, 0.80),
    "nametag_neon_pink": _unity(1.00, 0.12, 0.55),
    "nametag_neon_cyan": _unity(0.12, 0.94, 1.00),
    "nametag_neon_lime": _unity(0.36, 1.00, 0.12),
    "nametag_neon_orange": _unity(1.00, 0.48, 0.12),
    "nametag_neon_violet": _unity(0.83, 0.13, 1.00),
    "nametag_neon_toxic": _unity(0.66, 1.00, 0.12),
    "nametag_neon_glowyellow": _unity(1.00, 0.98, 0.61),
}
NEON: frozenset[str] = frozenset(sku for sku in COLOURS if sku.startswith("nametag_neon_"))
PLAIN_GLOWS: tuple[str, ...] = tuple(sorted(sku for sku in GLOWS if sku.startswith("nametag_glow_")))

# Per-character rainbow, cycled over the non-space characters.
RAINBOW: tuple[tuple[int, int, int], ...] = tuple(
    _rgb(code) for code in ("#FF5566", "#FFB347", "#FFEE55", "#88FF99", "#55CCFF", "#BB88FF"))

# Start → end of a left-to-right lerp over the non-space characters, from the
# client's float table.
GRADIENTS: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "nametag_gradient_sunset": (_unity(1.00, 0.70, 0.28), _unity(0.90, 0.30, 0.54)),
    "nametag_gradient_aurora": (_unity(0.30, 1.00, 0.85), _unity(0.65, 0.40, 1.00)),
    "nametag_gradient_ocean": (_unity(0.35, 0.95, 1.00), _unity(0.15, 0.20, 0.65)),
    "nametag_gradient_ember": (_unity(1.00, 0.95, 0.30), _unity(0.80, 0.15, 0.10)),
    "nametag_gradient_galaxy": (_unity(1.00, 0.35, 0.85), _unity(0.35, 0.65, 1.00)),
    "nametag_gradient_fade": (_unity(1.00, 1.00, 1.00), _unity(0.28, 0.28, 0.30)),
    "nametag_gradient_earth": (_unity(0.45, 0.85, 0.35), _unity(0.45, 0.28, 0.14)),
    "nametag_gradient_orchid": (_unity(0.62, 0.35, 0.95), _unity(1.00, 0.45, 0.80)),
    "nametag_gradient_sapphire": (_unity(0.55, 0.85, 1.00), _unity(0.12, 0.25, 0.75)),
    "nametag_gradient_emerald": (_unity(0.55, 1.00, 0.65), _unity(0.08, 0.42, 0.20)),
    "nametag_gradient_steel": (_unity(0.86, 0.88, 0.92), _unity(0.30, 0.36, 0.48)),
    "nametag_gradient_ash": (_unity(0.72, 0.70, 0.68), _unity(0.85, 0.22, 0.12)),
    "nametag_gradient_royal": (_unity(1.00, 0.78, 0.20), _unity(1.00, 0.97, 0.88)),
    "nametag_gradient_blood": (_unity(1.00, 0.22, 0.22), _unity(0.42, 0.06, 0.12)),
    "nametag_gradient_twilight": (_unity(1.00, 0.58, 0.22), _unity(0.42, 0.22, 0.70)),
}
RAINBOW_SKU = "nametag_rainbow"

# Letter case / spacing, in the client's layer order.
CASE_ORDER: tuple[str, ...] = ("nametag_font_caps", "nametag_font_smallcaps", "nametag_font_spaced")
CASES: dict[str, str] = {
    "nametag_font_caps": "caps",
    "nametag_font_smallcaps": "smallcaps",
    "nametag_font_spaced": "spaced",
}

# Size bands, in the client's layer order. The client scales the nametag by
# 80 / 130 / 160 / 145 %; the autograph's rect is 108 card px tall and its
# fit already shrinks a long name, so a band above 1 moves the START of the
# fit and the card's width and height still bound it (a "huge" name grows
# only as far as the rect allows), while the band below 1 shrinks the fitted
# size itself, never under the fit's floor (product owner: never too small
# or too big, still presentable). pc_face._autograph_fit applies them.
SIZE_ORDER: tuple[str, ...] = ("nametag_size_smaller", "nametag_size_bigger", "nametag_size_huge", "nametag_size_xl")
SIZES: dict[str, float] = {
    "nametag_size_smaller": 0.85,
    "nametag_size_bigger": 1.08,
    "nametag_size_huge": 1.16,
    "nametag_size_xl": 1.12,
}

# Stackable flags.
FLAGS: dict[str, str] = {
    "nametag_bold": "bold",
    "nametag_italic": "italic",
    "nametag_underline": "underline",
    "nametag_strike": "strike",
}

# Client SKUs with no still-image form: decided, and decided as "nothing".
# The floating name only animates; a typeface swaps the nametag's font, and
# the autograph keeps its own script face whatever the subject's nametag
# wears (product owner: cursive stays, the colour, style and size follow).
IGNORED: frozenset[str] = frozenset({"nametag_float"})
IGNORED_PREFIXES: tuple[str, ...] = ("nametag_typeface_",)

# Every nametag SKU this module has an answer for (the pin against the client).
KNOWN: frozenset[str] = frozenset(
    set(COLOURS) | set(GLOWS) | set(GRADIENTS) | {RAINBOW_SKU} | set(CASES) | set(SIZES) | set(FLAGS) | IGNORED)


def decided(sku: str) -> bool:
    """True when this module has an answer for the SKU: a table entry, or a
    family it ignores by prefix."""
    return sku in KNOWN or any(sku.startswith(prefix) for prefix in IGNORED_PREFIXES)

STYLE_KEYS: tuple[str, ...] = (
    "bold", "case", "fill", "glow", "italic", "rgb", "rgb2", "size", "strike", "underline")


def signature_style(skus: Iterable[str] | None) -> dict | None:
    """The canonical style of an autograph for these active nametag SKUs, or
    None when none of them changes the plain autograph."""
    active = [str(s) for s in (skus or ()) if s]
    if not active:
        return None
    present = set(active)
    fill, rgb, rgb2 = "solid", None, None
    neon = None
    # A rainbow or gradient replaces the colour; the client takes the first
    # of them in its list, whose order this side does not have, so the
    # rainbow wins over any gradient and gradients rank by name (recorded
    # deviation: a subject wearing both sees the rainbow on their card;
    # the shop's single-active colour slot makes that pair rare).
    if RAINBOW_SKU in present:
        fill = "rainbow"
    else:
        gradients = sorted(s for s in present if s in GRADIENTS)
        if gradients:
            fill = "gradient"
            rgb, rgb2 = (_hex(c) for c in GRADIENTS[gradients[0]])
    if fill == "solid":
        for sku in COLOUR_ORDER:
            if sku in present:
                rgb = _hex(COLOURS[sku])
                neon = sku if sku in NEON else None
                break
    # The halo: a plain glow SKU first (the client's GetActiveGlowSku), else
    # the neon's own; a neon under a rainbow or gradient still glows, as the
    # client's glow side does not read the colour tags.
    if neon is None:
        neon = next((sku for sku in COLOUR_ORDER if sku in present and sku in NEON), None)
    glow_sku = next((sku for sku in PLAIN_GLOWS if sku in present), neon)
    glow = _hex(GLOWS[glow_sku]) if glow_sku else None
    case = next((CASES[sku] for sku in CASE_ORDER if sku in present), None)
    size = next((SIZES[sku] for sku in SIZE_ORDER if sku in present), 1.0)
    flags = {name: (sku in present) for sku, name in FLAGS.items()}
    if (fill == "solid" and rgb is None and glow is None and case is None and size == 1.0
            and not any(flags.values())):
        return None
    style = {
        "bold": flags["bold"],
        "case": case,
        "fill": fill,
        "glow": glow,
        "italic": flags["italic"],
        "rgb": rgb,
        "rgb2": rgb2,
        "size": float(size),
        "strike": flags["strike"],
        "underline": flags["underline"],
    }
    assert tuple(style) == STYLE_KEYS
    return style
