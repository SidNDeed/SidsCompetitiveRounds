"""The evidence report's rate map is bounded (repair B of lane SRV-A).

_rate_charge kept a key per caller for ever. Now every charge removes a
caller whose window is empty, and the map holds at most RATE_KEYS_MAX
callers. At the ceiling a NEW caller is refused `429 rate` with a
Retry-After equal to the earliest time at which some caller's window is
empty (that caller's newest stamp plus RATE_WINDOW_S, less now), bounded to
1..RATE_WINDOW_S: the refusal expires by itself, and no caller already held
loses its stamps, so the per-caller bound never weakens. Every case runs on
a planted clock (the `now` argument) and a fresh map.
"""
import pytest
from fastapi import HTTPException

import admin_evidence as ae

WINDOW = ae.AER_CONTRACT_BOUNDS["RATE_WINDOW_S"]


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(ae, "_RATE", {})
    monkeypatch.setitem(ae.AER_CONTRACT_BOUNDS, "RATE_KEYS_MAX", 3)
    return ae._RATE


def _refused(actor, now):
    with pytest.raises(HTTPException) as exc:
        ae._rate_charge(actor, now=now)
    assert exc.value.status_code == 429 and exc.value.detail == "rate"
    return int(exc.value.headers["Retry-After"])


def test_the_ceiling_is_a_contract_bound_of_1024():
    assert ae.AER_CONTRACT_BOUNDS["RATE_KEYS_MAX"] == 1024


def test_a_key_whose_window_is_empty_is_removed(fresh):
    ae._rate_charge("a", now=100.0)
    ae._rate_charge("b", now=200.0)
    assert set(fresh) == {"a", "b"}
    ae._rate_charge("b", now=100.0 + WINDOW)          # a's only stamp leaves its window
    assert set(fresh) == {"b"}
    ae._rate_charge("c", now=200.0 + WINDOW)          # b's two stamps: one left, one stays
    assert set(fresh) == {"b", "c"} and list(fresh["b"]) == [100.0 + WINDOW]


def test_at_the_ceiling_a_new_caller_waits_for_the_earliest_free_key(fresh):
    """Three callers fill the map. a's newest stamp is 150 (its oldest, 10,
    is older than every other stamp but a stays), b's is 120, c's 130: the
    first key to empty is b's, at 120 + WINDOW. A new caller is refused one
    second before that, with Retry-After 1, and admitted at exactly that
    time; the oldest stamp in the map (a's 10) does not decide it."""
    ae._rate_charge("a", now=10.0)
    ae._rate_charge("a", now=150.0)
    ae._rate_charge("b", now=120.0)
    ae._rate_charge("c", now=130.0)
    free_at = 120.0 + WINDOW
    assert _refused("d", now=200.0) == int(free_at - 200.0)
    assert _refused("d", now=free_at - 1) == 1
    ae._rate_charge("d", now=free_at)
    assert set(fresh) == {"a", "c", "d"}
    assert list(fresh["a"]) == [150.0]                # a lost only its expired stamp


def test_a_caller_already_held_is_charged_at_the_ceiling(fresh):
    for k, t in (("a", 1.0), ("b", 2.0), ("c", 3.0)):
        ae._rate_charge(k, now=t)
    ae._rate_charge("a", now=4.0)
    assert list(fresh["a"]) == [1.0, 4.0]


def test_the_retry_after_is_bounded_to_the_window(fresh):
    assert ae._retry_after(0.2, WINDOW) == "1"
    assert ae._retry_after(-5, WINDOW) == "1"
    assert ae._retry_after(WINDOW + 50, WINDOW) == str(WINDOW)
    assert ae._retry_after(41.2, WINDOW) == "42"


def test_the_per_caller_bound_is_unchanged(fresh):
    for i in range(ae.AER_CONTRACT_BOUNDS["RATE_MAX"]):
        ae._rate_charge("a", now=1000.0 + i)
    assert _refused("a", now=1100.0) == int(WINDOW - 100)
    ae._rate_charge("a", now=1000.0 + WINDOW)
