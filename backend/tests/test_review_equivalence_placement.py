"""The equivalence harness plants every sitting fixture row on exactly the
UTC day its labels name, or refuses the run before any assertion, proven
WITHOUT the private suite: synthetic rows through test_review_equivalence's
own sitting run (its planting statement, its transaction, its read-back),
with the private parts (the fixture, the rule map, the revision, the old
worker) stood in by minimal synthetic values.

A row is planted at ROW_HOUR plus its minute, UTC, `days_ago` days before the
run's UTC today; a minute that keeps it inside that day is planted, one that
crosses a UTC midnight either way is refused (PlacementRefused). Needs a
throwaway PostgreSQL database named by REVIEW_EQUIV_TEST_PG_DSN (the run
rolls its schema back); skipped, with that reason, when it is unset.
"""

import asyncio
import datetime
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_review_equivalence as te  # noqa: E402

DSN = (os.environ.get("REVIEW_EQUIV_TEST_PG_DSN") or "").replace("postgresql+asyncpg://", "postgresql://")

pytestmark = pytest.mark.skipif(not DSN, reason="REVIEW_EQUIV_TEST_PG_DSN is unset: the placement "
                                "check needs a throwaway PostgreSQL database")


def _row(i, days_ago, minute):
    r = {c: 0 for c in te._COLS}
    r.update({"id": str(uuid.UUID(int=i + 1)), "player1_id": str(uuid.UUID(int=1000 + i)),
              "player2_id": str(uuid.UUID(int=2000 + i)), "is_ranked": True, "series_id": None,
              "reported_by": None, "days_ago": days_ago, "minute": minute, "invalidated": False})
    return r


def _run(monkeypatch, rows):
    async def no_pass(_session):
        return {}
    oracle = {"settings": {}, "cand_days": 30, "kinds": (), "sql": {}, "sitting_pass": no_pass}
    parts = {"kindmap": {}, "sitting_fixture": {"series": [], "rows": rows, "pos": [], "neg": []}}
    monkeypatch.setattr(te, "_oracle", lambda: oracle)
    monkeypatch.setattr(te, "_json", lambda name: parts[name])
    monkeypatch.setattr(te, "_ruleset", lambda: None)
    monkeypatch.setattr(te, "DSN", DSN)
    return asyncio.run(te._sitting_run())


def test_rows_inside_their_labelled_utc_day_are_planted(monkeypatch):
    """Control: the first and last minute of the day either side of noon."""
    out = _run(monkeypatch, [_row(0, 1, 0), _row(1, 2, 719), _row(2, 3, -720)])
    assert isinstance(out["today"], datetime.date)


@pytest.mark.parametrize("days_ago, minute", [(1, 720), (2, -721), (1, 1440)],
                         ids=["past_the_next_midnight", "before_its_own_midnight", "a_whole_day_on"])
def test_a_row_planted_across_a_utc_midnight_is_refused(monkeypatch, days_ago, minute):
    with pytest.raises(AssertionError, match="not on their labelled UTC day"):
        _run(monkeypatch, [_row(0, 1, 0), _row(1, days_ago, minute)])
