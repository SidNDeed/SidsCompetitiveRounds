"""The hold-Tab board's height budget, and the lever that reaches its setting.

Two round-1 findings against item 10 live here.

The LAYOUT one: the board drew 21px per stat row and up to four wrapped lines
of cards, at a fixed size, centred. The 22nd stat row pushed the card row off
the bottom of a 1024x576 screen with the head-to-head line present -- and the
card row is the one thing on this board that cannot scroll, so those cards
were simply not drawn. The fix derives the pitch and the card-line count from
the height that is actually available.

That arithmetic is C#, in a method that needs Unity to run, so it is read out
of the source here and replayed in Python: the constants come from the file
(a changed constant changes this test's numbers), the SHAPE of each statement
is pinned (a fixed pitch put back cannot pass), and the fit is asserted across
the screen heights this game is played at and across the range the runtime
card line height can land in. `test_the_fixed_pitch_layout_this_replaced_does
_not_fit` is the control: it runs the OLD arithmetic through the same model
and requires it to overflow, so a fit assertion that everything satisfies
would fail here first (#391).

The REACHABILITY one: `HealthPrecisionSetting` bound, normalised, cycled and
formatted, and nothing called `Cycle()` -- a finished feature with no entry
point, which logs exactly like a working one (#438/#443). The pin below reads
the settings tab's own block rather than the file, and has its own negative
control, because a file-wide grep for a call is satisfied by any mention
anywhere (#342/#441).
"""

import re
from pathlib import Path

import pytest

from _cs_structure import code_of

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
TAB_CS = PLUGIN / "TabStatsOverlay.cs"
NATIVE_CS = PLUGIN / "NativeUI.cs"

DRAW = "public static void Draw()"
SETTINGS_TAB = "private static GameObject BuildSettingsTab(Transform parent)"
# A sibling in the same file, used only to show the reader is scoped to one
# method: the needle below must NOT be found here.
OTHER_METHOD = "private static void ApplyInfoNavFilter()"

# Heights the board is actually asked to draw at. 576 is the finding's case;
# the rest are the common 16:9 and 16:10 desktop heights above it.
SCREEN_HEIGHTS = [576, 600, 720, 768, 800, 864, 900, 1080, 1440]
# `lineH` is `Mathf.Max(15f, stCards.lineHeight + 3f)` -- a runtime metric of
# the skin's font. Rather than invent one value, the fit is required across
# the whole band it can plausibly land in for an 11-12px font.
LINE_HEIGHTS = [15, 16, 17, 18, 19, 20, 22, 24]


def _draw_code():
    return code_of(TAB_CS, DRAW)


def _flat(s):
    return re.sub(r"\s+", " ", s).strip()


def _num(pattern, text, what):
    m = re.search(pattern, text)
    assert m, f"{what} is no longer written the way this model reads it"
    return float(m.group(1))


def _constants():
    """The layout's numbers, read out of Draw() rather than restated here."""
    code = _draw_code()
    c = {
        "ROW_H_MAX": _num(r"const float ROW_H_MAX = ([0-9.]+)f;", code, "ROW_H_MAX"),
        "ROW_H_MIN": _num(r"const float ROW_H_MIN = ([0-9.]+)f;", code, "ROW_H_MIN"),
        "MARGIN_Y": _num(r"const float MARGIN_Y = ([0-9.]+)f;", code, "MARGIN_Y"),
        "CARD_LINES_MAX": _num(r"const int CARD_LINES_MAX = ([0-9]+);", code,
                               "CARD_LINES_MAX"),
        "H2H_ROW": _num(r"float h2hH = string\.IsNullOrEmpty\(h2hLine\) \? 0f : ([0-9.]+)f;",
                        code, "the head-to-head row height"),
        "CARDS_PAD": _num(r"cachedCardsHeight = maxLines \* lineH \+ ([0-9.]+)f;", code,
                          "the card block's padding"),
        "LINE_H_FLOOR": _num(r"float lineH = Mathf\.Max\(([0-9.]+)f, stCards\.lineHeight",
                             code, "the card line-height floor"),
    }
    m = re.search(r"float furniture = ([0-9.]+)f \+ h2hH \+ ([0-9.]+)f \+ ([0-9.]+)f;", code)
    assert m, "the furniture sum is no longer written the way this model reads it"
    c["FURNITURE"] = sum(float(g) for g in m.groups())
    return c


def _row_count():
    """How many stat rows the board draws, counted in the ROWS initialiser."""
    src = TAB_CS.read_text(encoding="utf-8")
    start = src.index("private static readonly StatRow[] ROWS = new[]")
    end = src.index("\n        };", start)
    rows = len(re.findall(r"\bnew StatRow\(", src[start:end]))
    assert rows > 0, "no StatRow entries found; the count below would be meaningless"
    return rows


def _layout(screen_h, line_h, h2h, c, rows):
    """Draw()'s height arithmetic, replayed. Returns (y, panel height)."""
    furniture = c["FURNITURE"] + (c["H2H_ROW"] if h2h else 0.0)
    budget = max(0.0, screen_h - c["MARGIN_Y"] * 2.0 - furniture)
    card_lines = int(c["CARD_LINES_MAX"])
    while (card_lines > 1
           and rows * c["ROW_H_MIN"] + (card_lines * line_h + c["CARDS_PAD"]) > budget):
        card_lines -= 1
    # Worst case: every player's card row wraps to the full allowance.
    cards_h = card_lines * line_h + c["CARDS_PAD"]
    row_h = min(max((budget - cards_h) / max(1, rows), c["ROW_H_MIN"]), c["ROW_H_MAX"])
    h = furniture + rows * row_h + cards_h
    return max(c["MARGIN_Y"], (screen_h - h) * 0.5), h


def _old_layout(screen_h, line_h, h2h, c, rows):
    """What this replaced: 21px a row, four card lines, centred, always."""
    furniture = c["FURNITURE"] + (c["H2H_ROW"] if h2h else 0.0)
    cards_h = int(c["CARD_LINES_MAX"]) * line_h + c["CARDS_PAD"]
    h = furniture + rows * c["ROW_H_MAX"] + cards_h
    return max(c["MARGIN_Y"], (screen_h - h) * 0.5), h


# ── the model's inputs ───────────────────────────────────────────────────────

def test_the_row_count_is_read_from_the_board_not_restated():
    """22 is the finding's number, and it is the count that makes the old
    layout overflow. If it were restated here, adding the 23rd row would leave
    every assertion below measuring a board that no longer exists."""
    assert _row_count() == 22


def test_the_constants_are_the_ones_the_source_declares():
    c = _constants()
    assert c["ROW_H_MIN"] <= c["ROW_H_MAX"], "the pitch clamp is inverted"
    assert c["LINE_H_FLOOR"] <= min(LINE_HEIGHTS), (
        "the runtime card line height can now fall below the band this test "
        "asserts over; widen LINE_HEIGHTS or the fit is untested there")


# ── the fit ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("screen_h", SCREEN_HEIGHTS)
@pytest.mark.parametrize("line_h", LINE_HEIGHTS)
@pytest.mark.parametrize("h2h", [False, True])
def test_the_board_fits_on_every_screen_it_is_drawn_on(screen_h, line_h, h2h):
    c, rows = _constants(), _row_count()
    y, h = _layout(screen_h, line_h, h2h, c, rows)
    assert y >= 0, f"the panel starts above the top edge (y={y})"
    assert y + h <= screen_h, (
        f"the panel runs {y + h - screen_h:.1f}px past the bottom edge at "
        f"{screen_h}p (h2h={h2h}, lineH={line_h}) -- the card row is what is "
        f"lost, and it does not scroll")


def test_the_fixed_pitch_layout_this_replaced_does_not_fit():
    """The control. The finding is that 22 rows at the old fixed pitch put the
    cards off a 576p screen; if the model could not show that, the fit
    assertions above would be proving nothing about this change."""
    c, rows = _constants(), _row_count()
    y, h = _old_layout(576, 15, True, c, rows)
    assert y + h > 576, (
        "the old arithmetic fits at 576p in this model, so the model does not "
        "reproduce the defect and the assertions above measure nothing")


def test_the_new_layout_fixes_exactly_that_case():
    c, rows = _constants(), _row_count()
    y, h = _layout(576, 15, True, c, rows)
    assert y + h <= 576


@pytest.mark.parametrize("h2h", [False, True])
def test_the_budget_only_ever_shrinks_the_board(h2h):
    """Where the old layout already fitted, the new one is the same layout:
    the clamp returns ROW_H_MAX and the loop leaves CARD_LINES_MAX. A budget
    that changed a screen it did not need to change would be a regression
    dressed as a fix."""
    c, rows = _constants(), _row_count()
    for screen_h in SCREEN_HEIGHTS:
        for line_h in LINE_HEIGHTS:
            new_y, new_h = _layout(screen_h, line_h, h2h, c, rows)
            old_y, old_h = _old_layout(screen_h, line_h, h2h, c, rows)
            if old_y + old_h <= screen_h:
                assert abs(new_h - old_h) < 0.01, (
                    f"{screen_h}p (h2h={h2h}, lineH={line_h}) fitted before and "
                    f"is now laid out differently: {old_h} -> {new_h}")
            else:
                assert new_h <= old_h + 0.01


def test_the_floor_the_comment_names_is_where_the_board_actually_overflows():
    """The budget is not a promise that any screen fits: at ROW_H_MIN with a
    single card line there is nothing left to give. The comment in Draw()
    names that floor, so it is asserted -- a documented bound nobody measures
    drifts silently."""
    c, rows = _constants(), _row_count()
    line_h = int(c["LINE_H_FLOOR"])
    panel = c["MARGIN_Y"] + c["FURNITURE"] + c["H2H_ROW"] + rows * c["ROW_H_MIN"] \
        + line_h + c["CARDS_PAD"]
    fits_y, fits_h = _layout(panel, line_h, True, c, rows)
    assert fits_y + fits_h <= panel, f"the derived floor {panel} does not fit"
    short_y, short_h = _layout(panel - 1, line_h, True, c, rows)
    assert short_y + short_h > panel - 1, (
        f"one pixel below the derived floor ({panel - 1}) still fits, so that "
        f"is not the floor and the comment's number is wrong")
    assert "a scroll view" in TAB_CS.read_text(encoding="utf-8"), (
        "the comment recording what to do below the floor is gone")


# ── the shape of the code the model claims to be reading ─────────────────────

@pytest.mark.parametrize("needle", [
    "int cardLines = CARD_LINES_MAX;",
    "while (cardLines > 1 && ROWS.Length * ROW_H_MIN + (cardLines * lineH + 8f) > budget) cardLines--;",
    "float budget = Mathf.Max(0f, Screen.height - MARGIN_Y * 2f - furniture);",
    "float rowH = Mathf.Clamp((budget - cardsH) / Mathf.Max(1, ROWS.Length), ROW_H_MIN, ROW_H_MAX);",
    "float h = furniture + ROWS.Length * rowH + cardsH;",
    "float y = Mathf.Max(MARGIN_Y, (Screen.height - h) * 0.5f);",
    "PrepareCardRowLayout(cachedCards[i], cardWidth, cardLines)",
])
def test_the_layout_is_built_the_way_this_model_replays_it(needle):
    """Comments are stripped before the match, so none of these can be
    satisfied by prose describing the layout."""
    assert needle in _flat(_draw_code()), needle


def test_the_pitch_is_derived_and_not_a_literal():
    """The defect was a constant. Scoped to Draw(): a `rowH` fixed anywhere
    else in this file is a different thing."""
    assert not re.search(r"float rowH = [0-9]", _flat(_draw_code())), (
        "the row pitch is a literal again")


def test_the_card_line_count_is_part_of_the_layout_cache_key():
    """The cached card block is reused across frames. Keyed on width alone, a
    board that was laid out for four lines keeps that height when the budget
    drops it to two, and the panel is measured at one size and drawn at
    another."""
    flat = _flat(_draw_code())
    assert "cachedCardLayoutLines != cardLines" in flat, (
        "the card-line count is not in the cache key")
    assert "cachedCardLayoutLines = cardLines;" in flat, (
        "the cache key is tested but never updated, so it never matches")


# ── the precision lever's entry point ────────────────────────────────────────

CYCLE = "TabStatsOverlay.HealthPrecisionSetting.Cycle();"


def test_the_precision_setting_is_reachable_from_the_settings_tab():
    """Without a caller the whole setting is inert, and nothing in the logs
    says so."""
    tab = _flat(code_of(NATIVE_CS, SETTINGS_TAB))
    assert CYCLE in tab, "no settings row cycles the HP precision"
    assert '"SHpPrec"' in tab, "the row that cycles it is not built here"


def test_the_reachability_reader_is_scoped_to_one_method():
    """The control for the pin above: the same reader over a sibling method
    must not find the call. A check that reads the whole file would pass on a
    dead call site, or on this very docstring."""
    assert CYCLE not in _flat(code_of(NATIVE_CS, OTHER_METHOD))
