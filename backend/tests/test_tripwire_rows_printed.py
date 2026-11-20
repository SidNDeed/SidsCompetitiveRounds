"""The review tripwire's session verdict prints its rows (repair E of lane
SRV-A).

When review_tripwire.verdict() is not clean, conftest's pytest_sessionfinish
printed a count and no row, so a seat run ending "non-clean verdict (12
trips)" could not be read. It now prints each row: kind, guarded name, the
caller's file relative to the checkout, line and function; at most 40 rows,
each cut to 300 characters, and no file content (the tripwire records none).
The verdict's meaning is unchanged: a trip still turns an OK exit into
TESTS_FAILED.

The planted trip is a row of the tripwire's own shape, handed to the hook
through a monkeypatched verdict(): the process's real trip list is never
touched, so this test cannot make its own session non-clean.
"""
import os
import types

import pytest

import conftest
import review_tripwire

assert os.path.basename(conftest.__file__) == "conftest.py"


def _row(i, file=None):
    return {"kind": "audit", "name": "os.scandir",
            "caller": {"file": file or str(conftest.CHECKOUT_ROOT / "backend" / "tools"
                                           / "review_needles.py"),
                       "function": "scan_%d" % i, "line": 100 + i},
            "_scope": None}


class _Reporter:
    def __init__(self):
        self.lines = []

    def write_line(self, line, **kw):
        self.lines.append(line)


def _finish(monkeypatch, trips):
    monkeypatch.setattr(review_tripwire, "verdict", lambda: list(trips))
    reporter = _Reporter()
    config = types.SimpleNamespace(
        stash=pytest.Stash(),
        pluginmanager=types.SimpleNamespace(get_plugin=lambda name: reporter))
    session = types.SimpleNamespace(config=config, exitstatus=pytest.ExitCode.OK)
    gen = conftest.pytest_sessionfinish(session, pytest.ExitCode.OK)
    next(gen)
    with pytest.raises(StopIteration):
        next(gen)
    return session, reporter.lines


def test_a_planted_trip_prints_its_row(monkeypatch):
    session, lines = _finish(monkeypatch, [_row(1)])
    assert lines == [
        "review tripwire: non-clean verdict (1 trips)",
        "review tripwire: trip 1: audit os.scandir at backend/tools/review_needles.py:101 in scan_1",
    ], lines
    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED


def test_a_clean_verdict_prints_nothing_and_keeps_the_exit(monkeypatch):
    session, lines = _finish(monkeypatch, [])
    assert lines == [] and session.exitstatus == pytest.ExitCode.OK


def test_at_most_40_rows_each_cut_to_300_characters(monkeypatch):
    trips = [_row(i) for i in range(45)]
    trips[0]["caller"]["function"] = "f" * 500
    _session, lines = _finish(monkeypatch, trips)
    rows = [ln for ln in lines if ln.startswith("review tripwire: trip ")]
    assert len(rows) == 40 and all(len(ln) <= 300 for ln in lines), [len(ln) for ln in lines]
    assert len(rows[0]) == 300
    assert lines[-1] == "review tripwire: 5 more trip rows not shown"


def test_a_file_outside_the_checkout_shows_its_last_component_only(monkeypatch):
    outside = os.path.join(os.path.dirname(str(conftest.CHECKOUT_ROOT)), "elsewhere", "x.py")
    _session, lines = _finish(monkeypatch, [_row(1, file=outside),
                                            _row(2, file="<review-witness:abc>")])
    assert lines[1].endswith("at <outside>/x.py:101 in scan_1"), lines
    assert "elsewhere" not in lines[1]
    assert lines[2].endswith("at <outside>/<review-witness:abc>:102 in scan_2"), lines
