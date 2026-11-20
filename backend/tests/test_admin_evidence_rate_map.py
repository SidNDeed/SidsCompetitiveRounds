"""The evidence report's rate map is bounded (repair B of lane SRV-A).

_rate_charge kept a key per caller for ever. Now every charge drops each
caller's stamps that left the window and rebuilds the map from the callers
whose window still holds a stamp, so a caller whose window is empty is no
longer in it, and the map holds at most RATE_KEYS_MAX callers. At the
ceiling a NEW caller is refused `429 rate` with a Retry-After equal to the
time until some caller's window is empty (that caller's newest stamp plus
RATE_WINDOW_S, less now), bounded to 1..RATE_WINDOW_S; no caller in the map
loses a stamp still inside the window, so the per-caller bound never
weakens. Every case runs on a planted clock (the `now` argument) and a fresh
map.

The charge binds the module's name to the map it rebuilds (no key is ever
removed from a map: the report's privacy pass refuses a removal it cannot
resolve), so a map object held across a charge is the old one. The fixture
therefore hands out a READER of the module's current map, and every check
reads through it after the charge it checks.
"""
import pytest
from fastapi import HTTPException

import admin_evidence as ae

WINDOW = ae.AER_CONTRACT_BOUNDS["RATE_WINDOW_S"]


@pytest.fixture
def fresh(monkeypatch):
    """A fresh map and a ceiling of 3; returns a reader of the module's
    current map (read it after each charge, never hold its result)."""
    monkeypatch.setattr(ae, "_RATE", {})
    monkeypatch.setitem(ae.AER_CONTRACT_BOUNDS, "RATE_KEYS_MAX", 3)
    return lambda: ae._RATE


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
    assert set(fresh()) == {"a", "b"}
    ae._rate_charge("b", now=100.0 + WINDOW)          # a's only stamp leaves its window
    assert set(fresh()) == {"b"}
    ae._rate_charge("c", now=200.0 + WINDOW)          # b's two stamps: one left, one stays
    assert set(fresh()) == {"b", "c"} and list(fresh()["b"]) == [100.0 + WINDOW]


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
    assert set(fresh()) == {"a", "c", "d"}
    assert list(fresh()["a"]) == [150.0]              # a lost only its expired stamp


def test_a_caller_already_held_is_charged_at_the_ceiling(fresh):
    for k, t in (("a", 1.0), ("b", 2.0), ("c", 3.0)):
        ae._rate_charge(k, now=t)
    ae._rate_charge("a", now=4.0)
    assert list(fresh()["a"]) == [1.0, 4.0]


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


def test_every_charge_keeps_exactly_each_callers_stamps_inside_the_window(fresh):
    """A charge by ANY caller drops, for every caller, exactly the stamps
    that left the window and keeps every stamp still inside it -- the
    youngest dropped stamp is WINDOW old to the second, the oldest kept one
    is half a second younger."""
    stamps = {"a": [0.0, 0.5, 300.0], "b": [10.0, 20.0], "c": [100.0]}
    for who, ts in stamps.items():
        for t in ts:
            ae._rate_charge(who, now=t)
    now = 0.5 + WINDOW - 0.5                          # a's 0.0 is WINDOW old; a's 0.5 is not yet
    ae._rate_charge("c", now=now)
    want = {who: [t for t in ts if now - t < WINDOW] for who, ts in stamps.items()}
    want["c"] = want["c"] + [now]
    assert {k: list(v) for k, v in fresh().items()} == want
    assert want["a"] == [0.5, 300.0] and want["b"] == [10.0, 20.0]


def test_the_map_never_holds_more_than_the_ceiling(fresh):
    """Forty new callers, one a second, then one every WINDOW / 4 seconds:
    after every charge, admitted or refused, the map holds at most
    RATE_KEYS_MAX callers, and it reaches that ceiling."""
    cap = ae.AER_CONTRACT_BOUNDS["RATE_KEYS_MAX"]
    sizes = []
    t = 0.0
    for i in range(40):
        t += 1.0 if i < 20 else WINDOW / 4
        try:
            ae._rate_charge("caller-%d" % i, now=t)
        except HTTPException as exc:
            assert exc.status_code == 429 and exc.detail == "rate"
        sizes.append(len(fresh()))
    assert max(sizes) == cap and all(s <= cap for s in sizes), sizes
