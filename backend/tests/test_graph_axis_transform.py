"""Sept 6 item f — the /graph elo axis transform is a PURE function; these are its rules.

Design decisions under test (group4-design-v2 §f):
  F-1  defaults preserved (bot: calendar) and "rating updates" terminology —
       one rating_history row is one completed ranked series, never a game.
  F-2  the two time axes are STEP plots: the previous rating is repeated at
       each new timestamp, so a gap in play is a flat run, not a slope.
  F-L  no invented 1500 baseline: the first drawn point is the first fetched
       row's pre-update rating when present, else that row's rating.

Run: python -m pytest backend/tests/test_graph_axis_transform.py -q
"""
from __future__ import annotations

import ast
import inspect
import textwrap
import typing
from datetime import datetime, timedelta, timezone

import pytest

import discord_bot as bot

T0 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)


def _d(days):
    return T0 + timedelta(days=days)


THREE_WEEK_GAP = [(_d(0), 1612.0), (_d(3), 1630.0), (_d(24), 1598.0)]


def test_calendar_is_a_step_plot_repeating_the_previous_rating():
    (xy,), label = bot._rating_axis_points([THREE_WEEK_GAP], "calendar")
    assert xy == [
        (_d(0), 1612.0),
        (_d(3), 1612.0), (_d(3), 1630.0),     # hold, then the jump
        (_d(24), 1630.0), (_d(24), 1598.0),   # three idle weeks: a flat run at 1630, then the jump
    ]
    assert len(xy) == 2 * len(THREE_WEEK_GAP) - 1
    assert "game" not in label.lower()


def test_updates_axis_is_a_plain_line_one_point_per_update():
    """Negative control for the step rule: no duplication on the index axis."""
    (xy,), label = bot._rating_axis_points([THREE_WEEK_GAP], "updates")
    assert xy == [(1, 1612.0), (2, 1630.0), (3, 1598.0)]
    assert len(xy) == len(THREE_WEEK_GAP)
    assert "rating update" in label.lower()
    assert "game" not in label.lower()


def test_since_first_zeroes_every_player_with_different_spans():
    players = [
        [(_d(0), 1500.0), (_d(10), 1520.0)],
        [(_d(40), 1700.0), (_d(41), 1690.0), (_d(100), 1710.0)],
        [(_d(-300), 1400.0), (_d(-299.5), 1410.0), (_d(-100), 1450.0), (_d(0), 1460.0)],
        [(_d(365), 1800.0), (_d(367), 1810.0)],
    ]
    xy, label = bot._rating_axis_points(players, "since_first")
    assert len(xy) == 4
    for pts, rows in zip(xy, players):
        assert pts[0] == (0.0, rows[0][1])                       # every line starts at x = 0
        span = (rows[-1][0] - rows[0][0]).total_seconds() / 86400.0
        assert pts[-1][0] == pytest.approx(span)
        assert pts[-1][1] == rows[-1][1]
        assert len(pts) == 2 * len(rows) - 1                     # step duplication on this axis too
        assert all(pts[i][0] <= pts[i + 1][0] for i in range(len(pts) - 1))
    assert [p[-1][0] for p in xy] == [pytest.approx(10), pytest.approx(60), pytest.approx(300), pytest.approx(2)]
    assert "first" in label.lower() and "game" not in label.lower()


def test_first_drawn_point_is_the_first_row_not_1500():
    rows = [(_d(0), 1612.0), (_d(1), 1630.0)]
    for axis in ("calendar", "updates", "since_first"):
        (xy,), _ = bot._rating_axis_points([rows], axis)
        assert xy[0][1] == 1612.0, axis
        assert all(y != 1500.0 for _, y in xy), axis
    # a player whose first row IS 1500 keeps it: the rule is "first row", not "not 1500"
    (xy,), _ = bot._rating_axis_points([[(_d(0), 1500.0), (_d(1), 1512.0)]], "updates")
    assert xy[0] == (1, 1500.0)


def test_pre_update_rating_is_the_baseline_when_a_row_carries_one():
    rows = [(_d(0), 1612.0, 1580.0), (_d(1), 1630.0, 1612.0)]
    (cal,), _ = bot._rating_axis_points([rows], "calendar")
    assert cal[:2] == [(_d(0), 1580.0), (_d(0), 1612.0)]         # held at the pre-update value, then the jump
    assert cal[2:] == [(_d(1), 1612.0), (_d(1), 1630.0)]
    (upd,), _ = bot._rating_axis_points([rows], "updates")
    assert upd == [(0, 1580.0), (1, 1612.0), (2, 1630.0)]        # x = updates applied within the window
    (sf,), _ = bot._rating_axis_points([rows], "since_first")
    assert sf[0] == (0.0, 1580.0) and sf[1] == (0.0, 1612.0)
    # only the FIRST row's pre-update value matters; later ones are implied by the step
    rows2 = [(_d(0), 1612.0, None), (_d(1), 1630.0, 1612.0)]
    (cal2,), _ = bot._rating_axis_points([rows2], "calendar")
    assert cal2[0] == (_d(0), 1612.0)


def test_empty_and_single_row_inputs():
    for axis in ("calendar", "updates", "since_first"):
        xy, _ = bot._rating_axis_points([[], [(_d(5), 1550.0)]], axis)
        assert xy[0] == []
        assert len(xy[1]) == 1 and xy[1][0][1] == 1550.0
    assert bot._rating_axis_points([], "calendar") == ([], bot._GRAPH_AXIS_LABELS["calendar"])
    (single,), _ = bot._rating_axis_points([[(_d(5), 1550.0)]], "since_first")
    assert single == [(0.0, 1550.0)]
    (single,), _ = bot._rating_axis_points([[(_d(5), 1550.0)]], "updates")
    assert single == [(1, 1550.0)]
    (single,), _ = bot._rating_axis_points([[(_d(5), 1550.0)]], "calendar")
    assert single == [(_d(5), 1550.0)]


def test_rows_are_sorted_and_unusable_rows_dropped():
    rows = [(_d(3), 1630.0), (_d(0), 1612.0), (None, 1700.0), (_d(9), None)]
    (xy,), _ = bot._rating_axis_points([rows], "updates")
    assert xy == [(1, 1612.0), (2, 1630.0)]


def test_unknown_axis_is_rejected():
    with pytest.raises(ValueError):
        bot._rating_axis_points([[(_d(0), 1500.0)]], "games")


def test_axis_labels_are_distinct_and_name_updates_not_games():
    labels = set(bot._GRAPH_AXIS_LABELS.values())
    assert len(labels) == 3
    assert all("game" not in v.lower() for v in labels)
    assert set(bot._GRAPH_AXIS_LABELS) == set(typing.get_args(bot._GraphAxis)) == {"calendar", "updates", "since_first"}


def test_history_rows_parse_period_end_first_and_prepend_nothing():
    hist = [
        {"rating": 1630, "rd": 60, "date": "2026-08-02T12:00:00+00:00", "period_end": "2026-08-04T12:00:00+00:00"},
        {"rating": 1612, "rd": 60, "date": "2026-08-01T12:00:00+00:00"},        # older server: alias only
        {"rating": 1640, "rd": 60, "date": "2026-08-05T12:00:00Z", "rating_before": 1630},
        "garbage",
        {"rating": None, "date": "2026-08-06T12:00:00+00:00"},
    ]
    pts = bot._history_to_points(hist)
    assert [p[1] for p in pts] == [1612.0, 1630.0, 1640.0]
    assert pts[1][0] == datetime(2026, 8, 4, 12, tzinfo=timezone.utc)   # period_end wins over the alias
    assert pts[0][2] is None and pts[2][2] == 1630.0
    assert all(p[1] != 1500.0 for p in pts)
    assert bot._history_to_points(None) == []


def _numeric_constants(src: str) -> set:
    """Every numeric literal in `src` — comments and docstrings excluded, because
    the rule is about VALUES the code invents, not prose that mentions them."""
    tree = ast.parse(textwrap.dedent(src))
    return {node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)}


def test_numeric_constant_scanner_sees_the_old_baseline_shape():
    """Negative control for the scanner: the pre-Sept-6 prepend WOULD be caught,
    and a comment naming the number would NOT — so the test below can fail for
    the right reason only."""
    old = ("pts.sort(key=lambda x: x[0])\n"
           "if pts and pts[0][1] != 1500.0:\n"
           "    pts.insert(0, (pts[0][0] - timedelta(days=1), 1500.0))\n")
    assert 1500 in _numeric_constants(old)
    assert 1500 not in _numeric_constants("x = 1  # the old synthetic 1500 point is gone\n")


def test_graph_command_axis_option_defaults_to_calendar_and_is_last():
    callback = getattr(bot.cmd_graph, "callback", bot.cmd_graph)
    sig = inspect.signature(callback)
    assert sig.parameters["axis"].default == "calendar"                 # F-1: the bot keeps its default
    assert list(sig.parameters)[-1] == "axis"                           # appended LAST: `!graph @a @b elo @c` still binds
    src = inspect.getsource(callback)
    assert "_rating_axis_points(" in src
    # F-L: no invented baseline VALUE anywhere on the elo path.
    for fn in (callback, bot._history_to_points, bot._rating_axis_points):
        assert 1500 not in _numeric_constants(inspect.getsource(fn)), fn.__name__
