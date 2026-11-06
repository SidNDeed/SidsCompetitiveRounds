"""Rulings FOUR-R11-A8 and FOUR-R11-A11 (2): the open recorder over the a1
arm (test_a1_identity_formation.py), which imports the fixture below as its
own module-scoped autouse fixture. The definitions live here because every
non-test function defined in the a1 module is walker code that its walker
grammar (grammar_shapes_a1.WALKER_SHAPES) must admit; the module holds only
the import.

One freeze before the module's first id and one thaw after its last, on
ro_census.OpenRecorder frozen at production's own URL (database.DATABASE_URL,
in the form asyncpg resolves). No id of that module reaches an open (the
census in test_r11_rec_pg), so the thaw requires the recorder active, zero
connections built and zero opens recorded: an open, if one ever appears,
fails the run. The control (test_r11_rec_pg) plants an open inside a window
frozen by a1_freeze and is refused by a1_window_refusal with the recorder's
own message.
"""

import pytest

import database
import ro_census


def a1_frozen_dsn():
    return "".join(database.DATABASE_URL.split("+asyncpg", 1))


def a1_freeze():
    rec = ro_census.OpenRecorder()
    rec.freeze(a1_frozen_dsn(), [None])
    return rec


def a1_window_refusal(w):
    """None when the window report `w` (OpenRecorder.report, read at the
    thaw) shows the recorder active with no open and no connection;
    otherwise the sentence naming what failed."""
    if not w or not w["active"]:
        return "the a1 arm's open recorder was not active at its thaw: %r" % (w,)
    if w["opens"] or w["built"] or w["violations"]:
        return "the a1 arm opened a connection; it is required to open none: %r" % (w,)
    return None


@pytest.fixture(scope="module", autouse=True, name="_a1_open_window")
def _a1_open_window():
    rec = a1_freeze()
    try:
        yield rec
        window = rec.report()
    finally:
        rec.thaw()
    refusal = a1_window_refusal(window)
    assert refusal is None, refusal
