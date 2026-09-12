"""Sept 7 item 3: the pair's own Photon ping maps on the 1v1 queue.

A client sends its region ping map with /queue/join (body) and, while it keeps
polling, as the X-Region-Pings header; ONE validator admits both. The map is
stored on the queue row off-ORM (migration 301) by the join's single INSERT ...
ON CONFLICT and by the poll's heartbeat UPDATE (only with a valid header); the
poll that carries a valid header also overlays it onto its own row snapshot, so
issuance in that same request judges the refreshed map (impl review r1 M1); the
stamp the row takes and the stamp the chooser judges are ONE Python value,
bound typed — never transaction-start time (impl review r2 M1). At
room issuance both seats' maps are re-read under the ordered locks and
`_pick_region_by_pings` (rung 0) may replace the ladder's answer with the
region that minimises the pair's WORST ping (bounded minimax since
2026-09-09: taken when it beats the ladder's worst by more than 20 ms and
lies within each seat's own bound, the worst that seat measured among the
candidates the ladder's active rung was choosing between, plus 20 ms;
learning #597 records why the earlier "costs neither seat more than 20 ms"
test moved none of the cross-region pairs observed on 2026-09-09).

Three kinds of test, in the style of test_queue_pair_writers.py:
  * pure-function tests on the rung (symmetry, refusals, tie order);
  * the validator and the header parser;
  * EXECUTED writers and handlers against fake sessions. The join fake refuses
    an INSERT that lost a typed bind; the issuance fake answers every SELECT
    with ONLY the columns the projection names, so a handler whose re-read
    stops carrying region_pings / region_pings_at fails its test here rather
    than silently falling back to the ladder in production.
"""

import asyncio
import inspect
import random
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import text

import main

ME = UUID("11111111-1111-1111-1111-111111111111")
PARTNER = UUID("22222222-2222-2222-2222-222222222222")
SERIES = UUID("33333333-3333-3333-3333-333333333333")
ME_STEAM = "76561198000000001"
PARTNER_STEAM = "76561198000000002"

FRESH_MAP = {"us": 100, "eu": 30}
FRESH_MAP_PARTNER = {"us": 90, "eu": 25}


def _run(coro):
    return asyncio.run(coro)


def _now():
    return datetime.now(timezone.utc)


# ── rung 0: pure function ────────────────────────────────────────────────────

def _rung(p1, p2, ladder, refs=()):
    """`refs` are the candidates the ladder's active rung was choosing between
    (what `_region_ladder_refs` returns). The ladder's answer is always one."""
    return main._pick_region_by_pings(p1, p2, ladder, refs=refs)


def _tokens(rng, codes):
    """(my live, opp live, my home, opp home) with blanks, agreeing homes
    sometimes, so every ladder rung comes up."""
    mr, orr = rng.choice(codes + [""] * 3), rng.choice(codes + [""] * 3)
    mh, oh = rng.choice(codes + [""] * 3), rng.choice(codes + [""] * 3)
    if rng.random() < 0.2:
        oh = mh
    return mr, orr, mh, oh


def test_rung0_is_swap_invariant():
    """The argument order is which seat's request triggered issuance. The
    verdict (pick, why, worst) must not depend on it, nor on the order of the
    reference tokens; `detail` prints the two seats' numbers in argument order
    and is the one element allowed to."""
    rng = random.Random(7)
    codes = ["us", "eu", "asia", "sa", "jp", "au"]
    for _ in range(400):
        p1 = {c: rng.randint(1, 400) for c in codes if rng.random() < 0.7}
        p2 = {c: rng.randint(1, 400) for c in codes if rng.random() < 0.7}
        mr, orr, mh, oh = _tokens(rng, codes)
        refs_a = main._region_ladder_refs(mr, orr, mh, oh)
        refs_b = main._region_ladder_refs(orr, mr, oh, mh)
        assert set(refs_a) == set(refs_b)
        for ladder in refs_a:
            a = _rung(p1, p2, ladder, refs=refs_a)
            b = _rung(p2, p1, ladder, refs=refs_b)
            assert a[:3] == b[:3], f"{p1} / {p2} ladder={ladder}: {a} vs {b}"
            assert len(a) == 4 and len(b) == 4


def test_a_seat_is_never_moved_beyond_the_ladders_candidates_on_its_own_numbers():
    """The bound (design v2, reference set narrowed by d2): whenever the rung
    moves the room, each seat's ping at the pick, read from its OWN map, is at
    most its worst ping among the candidates the ladder's active rung was
    choosing between, plus 20 ms. Fuzzed over maps, live tokens and homes; the
    reference set comes from the caller's helper and the ladder's OWN answer
    (the picker run without maps) must be among it — the oracle is the picker,
    not the helper (impl review: a helper ranking the lives above agreeing
    homes passed every test that trusted the helper); positive controls that
    rooms do move and that every rung (agreeing homes, lives, homes, the
    default) is exercised."""
    rng = random.Random(23)
    codes = ["us", "eu", "asia", "sa", "jp", "au", "kr", "ru"]
    moved, rungs = 0, set()
    main._REGION_SEEN.clear()
    for _ in range(4000):
        p1 = {c: rng.randint(1, 400) for c in codes if rng.random() < 0.7}
        p2 = {c: rng.randint(1, 400) for c in codes if rng.random() < 0.7}
        mr, orr, mh, oh = _tokens(rng, codes)
        refs = main._region_ladder_refs(mr, orr, mh, oh)
        rungs.add("agree" if mh and mh == oh else "live" if (mr or orr) else "home" if (mh or oh) else "default")
        ladder = main._pick_room_region(mr, mh, orr, oh, "fuzz")
        assert ladder in refs, (mr, orr, mh, oh, ladder, refs)
        pick, why, worst, detail = _rung(p1, p2, ladder, refs=refs)
        if why != "pings" or pick == ladder:
            continue
        moved += 1
        for p in (p1, p2):
            allowed = max(p[r] for r in refs if r in p) + main.REGION_PINGS_MARGIN_MS
            assert p[pick] <= allowed, f"{p} moved to {pick} ({p[pick]}) beyond {allowed}: refs={refs} {detail}"
        assert worst == max(p1[pick], p2[pick])
    assert moved > 200, moved
    assert rungs == {"agree", "live", "home", "default"}, rungs


def test_only_the_active_rungs_candidates_bound_a_seat(capsys):
    """Design review d2: a signal the ladder outranked is not a candidate and
    must not widen a bound. The live regions agree on eu, so the ladder can
    only answer eu; seat 2's cached home asia is one rung lower. With every
    ladder input as a reference, asia would have raised seat 1's bound from 40
    to 320 and moved it from 20 to 300 ms; with the active rung's candidates
    only, the room stays on eu. `_region_ladder_refs` is the one place that
    knows the ladder's precedence, and the caller must use it."""
    now = _now()
    fresh = now - timedelta(seconds=30)
    assert main._pick_room_region("eu", "", "eu", "asia", "r", p1_pings={"eu": 20, "asia": 300},
                                  p2_pings={"eu": 500, "asia": 20}, p1_pings_at=fresh, p2_pings_at=fresh,
                                  now=now) == "eu"
    lines = [line for line in capsys.readouterr().out.splitlines() if "[QUEUE-REGION]" in line]
    assert lines[0] == "[QUEUE-REGION] room=r pick=eu rung=pings worst=500 ladder=eu cand=eu cand_ms=20/500 ladder_ms=20/500 bound=40/520"
    assert "_region_ladder_refs(mr, orr, mh, oh)" in inspect.getsource(main._pick_room_region)
    # the helper mirrors the ladder's rungs exactly: agreeing homes, lives, homes, default
    assert main._region_ladder_refs("", "", "eu", "eu") == ("eu",)
    assert main._region_ladder_refs("eu", "", "us", "asia") == ("eu",)
    assert main._region_ladder_refs("eu", "eu", "us", "asia") == ("eu",)
    assert main._region_ladder_refs("eu", "us", "", "") == ("eu", "us")
    assert main._region_ladder_refs("", "", "ru", "rue") == ("ru", "rue")
    assert main._region_ladder_refs("", "", "", "asia") == ("asia",)
    assert main._region_ladder_refs("", "", "", "") == ("us",)
    assert main._region_ladder_refs("eu", "eu", "asia", "asia") == ("asia",)
    assert main._region_ladder_refs("eu", "us", "asia", "asia") == ("asia",)
    # end to end: agreeing homes outrank the lives, so the ladder answers asia and only asia
    # bounds the seats — a helper ranking the lives first would move seat 1 to eu at 300 ms
    assert main._pick_room_region("eu", "asia", "eu", "asia", "r", p1_pings={"asia": 20, "eu": 300},
                                  p2_pings={"asia": 500, "eu": 20}, p1_pings_at=fresh, p2_pings_at=fresh,
                                  now=now) == "asia"
    lines = [line for line in capsys.readouterr().out.splitlines() if "[QUEUE-REGION]" in line]
    assert lines[0] == "[QUEUE-REGION] room=r pick=asia rung=pings worst=500 ladder=asia cand=asia cand_ms=20/500 ladder_ms=20/500 bound=40/520"


def test_missing_maps_and_no_overlap_leave_the_ladder():
    assert _rung(None, {"us": 40}, "us") == ("us", "no-maps", None, "")
    assert _rung({"us": 40}, {}, "us") == ("us", "no-maps", None, "")
    assert _rung({"us": 40}, {"eu": 40}, "asia") == ("asia", "no-overlap", None, "")


def test_each_seats_bound_comes_from_its_own_map_and_the_destination_is_joint():
    """The #283 statement in main.py, executed. Each seat's bound is read from
    its own map alone; where the pair lands inside the bounds is decided by
    both maps together. Seat 1's map {eu: 1} against seat 2's {us: 30, eu:
    150}, ladder us, refs (eu, us): seat 2's bound is max(us 30, eu 150) + 20
    = 170, so eu (150) is within it and the move is taken — seat 2 pays its own
    measurement of a region the ladder was choosing between. With eu NOT among
    the references (refs (us,)) seat 2's bound is 30 + 20 = 50, eu is out of
    bounds for seat 2, and the ladder is confirmed instead; seat 1's map never
    enters seat 2's bound. The destination, though, is joint (design review
    d3): with refs (us, eu), ladder eu and seat 2 fixed at {us: 150, eu: 30}
    (bound 170 either way), seat 1's {us: 1, eu: 500} sends the pair to us and
    {us: 500, eu: 1} keeps it on eu. And no map reaches a region the other
    seat did not measure at all: {eu: 1, sa: 1} against {us: 30} shares
    nothing."""
    assert _rung({"eu": 1}, {"us": 30, "eu": 150}, "us", refs=("eu", "us"))[:3] == ("eu", "pings", 150)
    assert _rung({"us": 30, "eu": 150}, {"eu": 1}, "us", refs=("us", "eu"))[:3] == ("eu", "pings", 150)
    assert _rung({"us": 1, "eu": 500}, {"us": 150, "eu": 30}, "eu", refs=("us", "eu"))[:3] == ("us", "pings", 150)
    assert _rung({"us": 500, "eu": 1}, {"us": 150, "eu": 30}, "eu", refs=("us", "eu"))[:3] == ("eu", "pings", 30)
    kept = _rung({"eu": 1, "us": 5}, {"us": 30, "eu": 150}, "us", refs=("us",))
    assert kept == ("us", "pings", 30, "cand=us cand_ms=5/30 ladder_ms=5/30 bound=25/50")
    assert _rung({"eu": 1, "sa": 1}, {"us": 30}, "us") == ("us", "no-overlap", None, "")


def test_a_region_both_seats_measured_better_is_taken():
    pick, why, worst, detail = _rung(FRESH_MAP, FRESH_MAP_PARTNER, "us")
    assert (pick, why, worst) == ("eu", "pings", 30)
    assert detail == "cand=eu cand_ms=30/25 ladder_ms=100/90 bound=120/110"


def test_a_candidate_exactly_at_a_seats_bound_is_admissible():
    """The bound is inclusive (impl review): seat 1's eu at 40 equals its bound
    (us 20 + 20) and the move is still taken; a strict comparison in the bound
    filter would leave the pair on us at 20/100."""
    assert _rung({"us": 20, "eu": 40}, {"us": 100, "eu": 30}, "us", refs=("us",)) == (
        "eu", "pings", 40, "cand=eu cand_ms=40/30 ladder_ms=20/100 bound=40/120")


def test_the_ladder_confirmed_by_pings_reports_the_rung():
    assert _rung({"us": 20, "eu": 90}, {"us": 25, "eu": 80}, "us")[:3] == ("us", "pings", 25)


def test_the_candidate_must_beat_the_ladders_worst_by_more_than_the_margin():
    """Minimax with a 20 ms margin, judged on the PAIR's worst ping: at the
    ladder's region the pair's worst is 100; a candidate whose worst is 80 is
    exactly 20 better and is refused (why=margin, the ladder stands, and the
    refusal line names what was seen); at 79 it is taken. The seat the move
    makes WORSE (10 -> 79 here) is asked only whether the candidate lies within
    its bound — eu is the other seat's home, so it does. The second half FAILS
    under the rule this replaced (79 > 10 + 20), which is what kept every
    cross-region pair observed on 2026-09-09 on one seat's home (learning #597)."""
    refs = ("", "", "eu", "us")
    refused = _rung({"us": 10, "eu": 80}, {"us": 100, "eu": 30}, "us", refs=refs)
    assert refused == ("us", "margin", None, "cand=eu cand_ms=80/30 ladder_ms=10/100 bound=100/120")
    taken = _rung({"us": 10, "eu": 79}, {"us": 100, "eu": 30}, "us", refs=refs)
    assert taken == ("eu", "pings", 79, "cand=eu cand_ms=79/30 ladder_ms=10/100 bound=99/120")
    assert main.REGION_PINGS_MARGIN_MS == 20


def test_an_unmeasured_ladder_region_is_scored_at_the_cap_but_never_lifts_a_bound():
    """A seat that did not measure the ladder's region scores it at the cap
    for the margin comparison — and that is all. Its bound still comes from
    the ladder's candidates it DID measure; with none measured the rung
    declines (why=unbounded), and a pair whose only shared region lies above
    a bound gets the ladder (why=bound). Both refusals name what was seen."""
    assert _rung({"eu": 30}, {"eu": 35}, "us") == ("us", "unbounded", None, "cand=eu cand_ms=30/35 ladder_ms=-/- bound=-/-")
    assert _rung({"eu": 200, "asia": 30}, {"eu": 35}, "us")[:3] == ("us", "unbounded", None)
    # seat 2 never measured us (the ladder's answer); eu is seat 2's home, so
    # it is a ladder candidate and seat 1 measured it at 200 -> within bounds
    lifted = _rung({"eu": 200, "us": 5}, {"eu": 35}, "us", refs=("", "", "us", "eu"))
    assert lifted == ("eu", "pings", 200, "cand=eu cand_ms=200/35 ladder_ms=5/- bound=220/55")
    # each seat measured one candidate, neither measured the other's; the only
    # shared region is above seat 1's bound
    assert _rung({"us": 120, "sa": 300}, {"eu": 20, "sa": 200}, "eu", refs=("", "", "us", "eu")) == (
        "eu", "bound", None, "cand=sa cand_ms=300/200 ladder_ms=-/20 bound=140/40")


def test_a_synthetic_sept_9_pairing_lands_on_a_shared_region():
    """SYNTHETIC. Seat 2's map is Spirit's complete queue-time sweep as logged
    for bug 355 (logs-snapshot/bug355.log:1033, rev=2, 17 regions). Seat 1's
    map is INVENTED for a rue-home opponent: their sweep reached no log, and
    only their recorded ru ping (251 ms in both games) is real. Ladder = ru
    (homes rue/ru disagree; the alphabet decides). Bounds: opponent 251 + 20
    (its ru), Spirit 246 + 20 (its rue). Among the shared regions inside both
    bounds the pair's least-worst is ussc at 140/129 instead of ru at 251/34 —
    a region the ladder would not have named, which is the purpose."""
    spirit = {"eu": 35, "us": 119, "usw": 174, "cae": 118, "asia": 185, "jp": 249, "au": 318, "sa": 202,
              "in": 181, "ru": 34, "rue": 246, "kr": 298, "za": 191, "tr": 85, "uae": 202, "ussc": 129, "hk": 276}
    opp = {"rue": 30, "jp": 60, "kr": 80, "hk": 90, "asia": 110, "usw": 110, "au": 130, "ussc": 140, "us": 150,
           "cae": 160, "in": 170, "uae": 200, "tr": 230, "eu": 250, "ru": 251, "sa": 260, "za": 280}
    refs = main._region_ladder_refs("", "", "rue", "ru")
    assert refs == ("rue", "ru")
    assert _rung(opp, spirit, "ru", refs=refs) == (
        "ussc", "pings", 140, "cand=ussc cand_ms=140/129 ladder_ms=251/34 bound=271/266")
    assert _rung(spirit, opp, "ru", refs=("ru", "rue"))[:3] == ("ussc", "pings", 140)


def test_tie_order_worst_then_sum_then_code():
    # both regions are ladder candidates (the homes), so both are in bounds
    refs = ("", "", "us", "eu")
    # worst decides first
    assert _rung({"us": 50, "eu": 40}, {"us": 50, "eu": 60}, "asia", refs=refs)[0] == "us"
    # equal worst: the smaller sum
    assert _rung({"us": 60, "eu": 60}, {"us": 40, "eu": 60}, "asia", refs=refs)[0] == "us"
    # equal worst and sum: fixed order by code, whichever seat asked
    assert _rung({"us": 50, "eu": 50}, {"us": 50, "eu": 50}, "asia", refs=refs)[0] == "eu"
    assert _rung({"us": 50, "eu": 60}, {"us": 60, "eu": 50}, "asia", refs=refs)[0] == "eu"


# ── rung 0 through _pick_room_region: freshness, symmetry, the log line ─────

def test_pick_room_region_positional_signature_is_unchanged():
    params = list(inspect.signature(main._pick_room_region).parameters)
    assert params[:5] == ["my_region", "my_home", "opp_region", "opp_home", "room_name"]
    assert {"p1_pings", "p2_pings", "p1_pings_at", "p2_pings_at"} <= set(params[5:])


def test_fresh_maps_replace_the_ladder_and_stale_or_absent_ones_do_not(capsys):
    now = _now()
    fresh = now - timedelta(seconds=60)
    stale = now - timedelta(seconds=main.REGION_PINGS_ISSUANCE_MAX_AGE_S + 1)
    kw = dict(p1_pings=FRESH_MAP, p2_pings=FRESH_MAP_PARTNER, now=now)
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings_at=fresh, p2_pings_at=fresh, **kw) == "eu"
    out = capsys.readouterr().out
    rung, ladder = [line for line in out.splitlines() if "[QUEUE-REGION]" in line][:2]
    assert rung == "[QUEUE-REGION] room=r pick=eu rung=pings worst=30 ladder=us cand=eu cand_ms=30/25 ladder_ms=100/90 bound=120/110"
    assert "chosen=eu" in ladder and "seen=" in ladder, "the existing line reports the FINAL pick"
    # one stale stamp -> ladder
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings_at=fresh, p2_pings_at=stale, **kw) == "us"
    assert "rung=ladder why=stale" in capsys.readouterr().out
    # a map without a stamp, or no map at all -> ladder
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings_at=None, p2_pings_at=fresh, **kw) == "us"
    assert "rung=ladder why=no-maps" in capsys.readouterr().out
    assert main._pick_room_region("us", "us", "us", "us", "r") == "us"
    assert "rung=ladder why=no-maps" in capsys.readouterr().out
    # absent on one side and stale on the other reads as no-maps
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings=None, p2_pings=FRESH_MAP_PARTNER,
                                  p1_pings_at=stale, p2_pings_at=stale, now=now) == "us"
    assert "rung=ladder why=no-maps" in capsys.readouterr().out


def test_the_refusal_line_records_the_candidate_and_both_seats_numbers(capsys):
    """The maps leave with the queue rows, so the pick line is the only record
    of what the rung saw. A margin refusal must therefore name the candidate
    and both seats' pings at it and at the ladder's region — 2026-09-09's
    picks could not be reconstructed because the line said only why=pareto."""
    now = _now()
    fresh = now - timedelta(seconds=30)
    # same-home pair (the ladder's only candidate is us): eu is within both
    # bounds but beats the pair's worst by only 10 ms
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings={"us": 100, "eu": 90},
                                  p2_pings={"us": 60, "eu": 75}, p1_pings_at=fresh, p2_pings_at=fresh,
                                  now=now) == "us"
    lines = [line for line in capsys.readouterr().out.splitlines() if "[QUEUE-REGION]" in line]
    assert lines[0] == "[QUEUE-REGION] room=r pick=us rung=ladder why=margin cand=eu cand_ms=90/75 ladder_ms=100/60 bound=120/80"
    # the active rung's candidates are the reference set: with homes (us, eu)
    # and no live signal the ladder is choosing between us and eu (the
    # alphabet answers eu once corroboration is cold), so eu lies inside BOTH
    # seats' bounds and the maps confirm it as the pair's least-worst
    main._REGION_SEEN.clear()
    assert main._pick_room_region("", "us", "", "eu", "r", p1_pings={"us": 10, "eu": 80},
                                  p2_pings={"us": 100, "eu": 30}, p1_pings_at=fresh, p2_pings_at=fresh,
                                  now=now) == "eu"
    lines = [line for line in capsys.readouterr().out.splitlines() if "[QUEUE-REGION]" in line]
    assert lines[0] == "[QUEUE-REGION] room=r pick=eu rung=pings worst=80 ladder=eu cand=eu cand_ms=80/30 ladder_ms=80/30 bound=100/120"
    # the no-maps branch has nothing to record and says nothing extra
    assert main._pick_room_region("us", "us", "us", "us", "r") == "us"
    lines = [line for line in capsys.readouterr().out.splitlines() if "[QUEUE-REGION]" in line]
    assert lines[0] == "[QUEUE-REGION] room=r pick=us rung=ladder why=no-maps"


def test_a_stored_map_that_no_longer_validates_is_absent():
    now = _now()
    at = now - timedelta(seconds=5)
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings={"US": 10, "eu": 30},
                                  p2_pings=FRESH_MAP_PARTNER, p1_pings_at=at, p2_pings_at=at, now=now) == "us"
    # a JSON text (a driver that hands jsonb back undecoded) is still read
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings='{"us": 100, "eu": 30}',
                                  p2_pings=FRESH_MAP_PARTNER, p1_pings_at=at, p2_pings_at=at, now=now) == "eu"


def test_pick_room_region_stays_swap_invariant_with_maps():
    rng = random.Random(11)
    now = _now()
    codes = ["us", "eu", "asia", "sa"]
    stamps = [None, now - timedelta(seconds=10), now - timedelta(seconds=500)]
    for _ in range(300):
        m1 = {c: rng.randint(1, 300) for c in codes if rng.random() < 0.6} or None
        m2 = {c: rng.randint(1, 300) for c in codes if rng.random() < 0.6} or None
        t1, t2 = rng.choice(stamps), rng.choice(stamps)
        h1, h2 = rng.choice(["", "us", "eu"]), rng.choice(["", "us", "eu"])
        a = main._pick_room_region("", h1, "", h2, "r", p1_pings=m1, p2_pings=m2, p1_pings_at=t1, p2_pings_at=t2, now=now)
        b = main._pick_room_region("", h2, "", h1, "r", p1_pings=m2, p2_pings=m1, p1_pings_at=t2, p2_pings_at=t1, now=now)
        assert a == b


# ── the validator and the header parser ──────────────────────────────────────

def test_validator_admits_a_well_formed_map_and_normalises_its_text():
    assert main._region_pings_validate({"us": 42, "eu": 31}, 12) == ('{"eu":31,"us":42}', 12)
    twenty_four = {chr(97 + i // 26) + chr(97 + i % 26): i + 1 for i in range(24)}
    assert main._region_pings_validate(twenty_four, 0)[1] == 0
    assert main._region_pings_validate({"us": 5000}, 900) == ('{"us":5000}', 900)


@pytest.mark.parametrize("pings, age", [
    ({}, 12),                                              # no information
    ({chr(97 + i // 26) + chr(97 + i % 26): 1 for i in range(25)}, 12),   # cap
    ({"US": 42}, 12), ({"u": 42}, 12), ({"usa1": 42}, 12), ({"useast": 42}, 12), ({" us": 42}, 12),
    ({"us": 0}, 12), ({"us": 5001}, 12), ({"us": 42.0}, 12), ({"us": True}, 12), ({"us": "42"}, 12),
    ({"us": 42}, -1), ({"us": 42}, 901), ({"us": 42}, "12"), ({"us": 42}, 12.5), ({"us": 42}, True), ({"us": 42}, None),
    (["us", 42], 12), ("us=42", 12), (None, 12),
])
def test_validator_refuses_everything_else(pings, age):
    assert main._region_pings_validate(pings, age) == (None, None)


def test_header_parser_feeds_the_join_validator():
    assert main._region_pings_from_header("us=42,eu=31;age=12") == ('{"eu":31,"us":42}', 12)
    assert main._region_pings_from_header(" us=42 , eu=31 ; age=0 ") == ('{"eu":31,"us":42}', 0)


@pytest.mark.parametrize("value", [
    None, "", "us=42", "us=42;age=-5", "us=42;age=", "us=42;age=1.5", "us=42;age=901",
    "us=42,us=43;age=1", "us=4a;age=1", "us;age=1", "US=42;age=1", "us=42;age=1;x",
    ";age=1", "us=0;age=1", "x" * 600,
    ",".join(f"{chr(97 + i // 26)}{chr(97 + i % 26)}=1" for i in range(25)) + ";age=1",
])
def test_header_parser_refuses_everything_else(value):
    assert main._region_pings_from_header(value) == (None, None)


# ── the join write: one INSERT ... ON CONFLICT with typed binds ─────────────

JOIN_PREDICATES = (
    "INSERT INTO ranked_queue",
    "region_pings, region_pings_at)",
    "CAST(:region_pings AS JSONB)",
    "NOW() - make_interval(secs => :region_pings_age)",
    "ON CONFLICT (player_id) DO UPDATE SET",
    "status = 'searching'",
    "matched_with = NULL",
    "room_name = NULL",
    "room_region = NULL",
    "ready = false",
    "matched_at = NULL",
    "region_pings = EXCLUDED.region_pings",
    "region_pings_at = EXCLUDED.region_pings_at",
)


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def mappings(self):
        return self

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None


class FakeJoinSession:
    """Records the join upsert and REFUSES one that lost a typed bind or a
    conflict-set predicate (the :305 oracle shape)."""

    def __init__(self):
        self.statements = []
        self.params = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        self.params.append(dict(params or {}))
        if sql.startswith("INSERT INTO ranked_queue"):
            for p in JOIN_PREDICATES:
                assert " ".join(p.split()) in sql, f"join upsert lost predicate: {p}"
        return _Result([])

    async def commit(self):
        pass


def _upsert(session, pings, age):
    return main._queue_join_upsert(
        session, player_id=ME, steam_id=ME_STEAM, display_name="me", rating=1500, rating_deviation=350,
        region="us", home_region="us", ranked_only=False, region_pings=pings, region_pings_age=age)


def test_join_upsert_is_one_statement_binding_the_validated_map_typed():
    session = FakeJoinSession()
    _run(_upsert(session, '{"eu":31,"us":42}', 12))
    assert len(session.statements) == 1, "the map rides the SAME INSERT ... ON CONFLICT, not a second UPDATE"
    params = session.params[0]
    assert params["region_pings"] == '{"eu":31,"us":42}'
    assert params["region_pings_age"] == 12
    assert params["pid"] == ME and params["sid"] == ME_STEAM
    assert isinstance(params["rating"], float) and isinstance(params["rd"], float)


def test_join_upsert_writes_null_null_for_a_refused_map():
    session = FakeJoinSession()
    _run(_upsert(session, None, None))
    assert session.params[0]["region_pings"] is None
    assert session.params[0]["region_pings_age"] is None


def test_queue_join_routes_the_body_through_the_validator_into_the_upsert():
    src = inspect.getsource(main.queue_join)
    assert "_region_pings_validate(req.region_pings, req.region_pings_age_s)" in src
    assert "region_pings=_pings_json, region_pings_age=_pings_age" in src
    assert src.count("_queue_join_upsert(") == 1
    assert "pg_insert(RankedQueue)" not in src, "the ORM upsert cannot carry the undeclared columns (#346)"


def test_fake_join_session_refuses_a_statement_that_lost_a_typed_bind():
    recorder = FakeJoinSession()
    _run(_upsert(recorder, '{"us":42}', 1))
    real = recorder.statements[0]
    mutations = (
        real.replace("CAST(:region_pings AS JSONB)", ":region_pings"),
        real.replace("NOW() - make_interval(secs => :region_pings_age)", "NOW() - (:region_pings_age || ' seconds')::interval"),
        real.replace("region_pings = EXCLUDED.region_pings, region_pings_at = EXCLUDED.region_pings_at", "region_pings = EXCLUDED.region_pings"),
        real.replace("region_pings, region_pings_at)", "region_pings)"),
    )
    session = FakeJoinSession()
    # positive control: the unmutated statement passes
    _run(session.execute(text(real), {}))
    for mutated in mutations:
        assert mutated != real
        with pytest.raises(AssertionError, match="lost predicate"):
            _run(session.execute(text(mutated), {}))


# ── issuance: the handlers, executed, fed ONLY what their projections name ──

_PROJECTION_RE = re.compile(r"^SELECT (.+?) FROM ranked_queue\b")


def _projection(sql):
    m = _PROJECTION_RE.match(sql)
    assert m, sql
    return [c.strip().split(".")[-1] for c in m.group(1).split(",")]


# The header heartbeat's typed binds (#275/#448); the issuance fake refuses a
# statement that lost one, the way the join fake refuses a lost JOIN_PREDICATE.
POLL_HEADER_PREDICATES = (
    "region_pings = CAST(:region_pings AS JSONB)",
    "region_pings_at = CAST(:region_pings_at AS TIMESTAMPTZ)",
)


class FakeIssuanceSession:
    """Enough of a session for queue_poll / queue_ready to reach room issuance.

    Every SELECT on ranked_queue is answered with EXACTLY the columns its
    projection names — a re-read that stops naming region_pings /
    region_pings_at hands the handler a row without them, and the handler's
    kwargs read raises. That is the oracle: the columns must reach the picker
    THROUGH the authoritative re-read, not through anything else."""

    def __init__(self, rows, me_steam):
        self.rows = {r["player_id"]: dict(r) for r in rows}
        self.by_steam = {r["steam_id"]: r["player_id"] for r in rows}
        self.me_steam = me_steam
        self.statements = []
        self.heartbeats = []
        self.commits = 0

    async def execute(self, statement, params=None):
        params = dict(params or {})
        sql = " ".join(str(statement).split())
        self.statements.append((sql, params))
        if sql.startswith("SELECT") and " FROM ranked_queue" in sql and "FOR UPDATE" not in sql:
            cols = _projection(sql)
            if "sid" in params:
                pid = self.by_steam.get(params["sid"])
            else:
                pid = params.get("pid", params.get("oid"))
            row = self.rows.get(pid)
            if row is None:
                return _Result([])
            return _Result([{c: row[c] for c in cols}])
        if sql.startswith("UPDATE ranked_queue SET last_polled = NOW()"):
            self.heartbeats.append((sql, params))
            # a valid header's statement lands on the ROW (what a later re-read
            # returns) with the stamp it BOUND — the fake has no clock of its
            # own, so a stamp derived from NOW() could never reach the row
            # (impl review r2 M1); the snapshot the handler took earlier is
            # untouched. A statement that lost a typed bind, or a naive stamp,
            # is refused.
            if "region_pings" in params:
                for p in POLL_HEADER_PREDICATES:
                    assert p in sql, f"header heartbeat lost predicate: {p}"
                stamp = params["region_pings_at"]
                assert isinstance(stamp, datetime) and stamp.tzinfo is not None, \
                    "header heartbeat bound a naive stamp"
                row = self.rows[params["pid"]]
                row["region_pings"] = params["region_pings"]
                row["region_pings_at"] = stamp
            return _Result([])
        if sql.startswith("SELECT") and "FROM players" in sql:
            pid = self.by_steam[self.me_steam]
            return _Result([SimpleNamespace(id=pid, steam_id=self.me_steam)])
        return _Result([])

    async def commit(self):
        self.commits += 1

    async def flush(self):
        pass

    def add(self, obj):
        pass


def _queue_row(pid, steam, matched_with, pings, pings_at, now):
    return {
        "player_id": pid, "steam_id": steam, "display_name": steam, "rating": 1500.0,
        "rating_deviation": 350.0, "status": "matched", "matched_with": matched_with,
        "room_name": None, "room_region": None, "region": "us", "home_region": "us",
        "ready": True, "joined_at": now - timedelta(seconds=30), "wait_since": None, "matched_at": now - timedelta(seconds=5),
        "region_pings": pings, "region_pings_at": pings_at,
        # migration 306: the re-reads project the frozen rules too
        "rules": None,
    }


def _pair(pings_me, pings_partner, at_me, at_partner):
    now = _now()
    return [_queue_row(ME, ME_STEAM, PARTNER, pings_me, at_me, now),
            _queue_row(PARTNER, PARTNER_STEAM, ME, pings_partner, at_partner, now)]


@pytest.fixture
def issuance(monkeypatch):
    """Everything around the issuance decision is faked; the decision itself
    (_pick_room_region and rung 0) is the real code. The room stamp records
    the region the pair was sent to."""
    stamps = []

    async def _true(*a, **k):
        return True

    async def _none(*a, **k):
        return None

    async def _stamp(db, my_pid, opp_pid, room_name, region, rules=None):
        # `rules` (migration 306) rides the same stamp; this fixture judges the
        # REGION and records the rules only so a rules test can read them.
        stamps.append((my_pid, opp_pid, room_name, region))
        return True

    async def _series(db, a, b, room_id=None):
        return SimpleNamespace(id=SERIES, player1_id=a, p1_series_wins=0, p2_series_wins=0,
                               rules=None)

    monkeypatch.setattr(main, "_strict_steam_session_ok", _true)
    monkeypatch.setattr(main, "_assert_no_service_subject", _none)
    monkeypatch.setattr(main, "_is_banned", _none)
    monkeypatch.setattr(main, "_queue_stamp_room_reciprocal", _stamp)
    monkeypatch.setattr(main, "_find_current_active_series", _series)
    monkeypatch.setattr(main, "_publish_pair_sitting", _none)
    monkeypatch.setattr(main, "_evict_other_queue_searching", _none)
    return stamps


def _request(headers=None):
    return SimpleNamespace(headers=dict(headers or {}))


def _poll(session, headers=None):
    return _run(main.queue_poll(ME_STEAM, _request(headers), session))


def _ready(session):
    return _run(main.queue_ready(_request(), steam_id=ME_STEAM, db=session))


def test_queue_poll_issues_the_room_from_the_projected_maps(issuance):
    at = _now() - timedelta(seconds=20)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, at, at), ME_STEAM)
    resp = _poll(session)
    assert resp.status == "ready_join"
    assert resp.photon_region == "eu"
    assert issuance == [(ME, PARTNER, resp.room_name, "eu")]
    # the decision was fed by the authoritative re-reads, both carrying the columns
    projected = [_projection(sql) for sql, _ in session.statements
                 if sql.startswith("SELECT") and " FROM ranked_queue" in sql and "FOR UPDATE" not in sql]
    assert all("region_pings" in cols and "region_pings_at" in cols
               for cols in projected if "region" in cols), projected


def test_queue_poll_control_without_maps_or_with_stale_maps_takes_the_ladder(issuance):
    session = FakeIssuanceSession(_pair(None, None, None, None), ME_STEAM)
    assert _poll(session).photon_region == "us"
    stale = _now() - timedelta(seconds=main.REGION_PINGS_ISSUANCE_MAX_AGE_S + 5)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, stale, stale), ME_STEAM)
    assert _poll(session).photon_region == "us"
    assert [s[3] for s in issuance] == ["us", "us"]


def test_queue_ready_issues_the_room_from_the_projected_maps(issuance):
    at = _now() - timedelta(seconds=20)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, at, at), ME_STEAM)
    resp = _ready(session)
    assert resp["status"] == "both_ready"
    assert resp["photon_region"] == "eu"
    assert issuance == [(ME, PARTNER, resp["room_name"], "eu")]


def test_queue_ready_control_without_maps_or_with_stale_maps_takes_the_ladder(issuance):
    session = FakeIssuanceSession(_pair(None, None, None, None), ME_STEAM)
    assert _ready(session)["photon_region"] == "us"
    stale = _now() - timedelta(seconds=main.REGION_PINGS_ISSUANCE_MAX_AGE_S + 5)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, stale, stale), ME_STEAM)
    assert _ready(session)["photon_region"] == "us"
    assert [s[3] for s in issuance] == ["us", "us"]


def test_the_issuance_fake_returns_only_what_the_projection_names():
    """Negative control for the oracle (#391): a projection that drops the
    columns produces a row WITHOUT them, so the handler's kwargs read fails."""
    at = _now()
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, at, at), ME_STEAM)
    full = _run(session.execute(text(
        "SELECT player_id, region, region_pings, region_pings_at FROM ranked_queue WHERE player_id = :pid"),
        {"pid": ME})).mappings().first()
    assert set(full) == {"player_id", "region", "region_pings", "region_pings_at"}
    dropped = _run(session.execute(text(
        "SELECT player_id, region FROM ranked_queue WHERE player_id = :pid"), {"pid": ME})).mappings().first()
    assert "region_pings" not in dropped
    with pytest.raises(KeyError):
        dropped["region_pings"]


def test_every_authoritative_re_read_names_both_columns():
    """Occurrence counts within each HANDLER's span (#432): the two entry
    re-reads and the opponent read in queue_poll, the entry and opponent
    reads in queue_ready — the retry-loop re-read is not exercised above."""
    poll = inspect.getsource(main.queue_poll)
    ready = inspect.getsource(main.queue_ready)
    assert poll.count("rq.region_pings, rq.region_pings_at") == 2
    assert poll.count("region, home_region, region_pings, region_pings_at,\n                       status, matched_with") == 1
    assert ready.count("home_region, ready, region_pings, region_pings_at") == 1
    assert ready.count("region_pings, region_pings_at, status, matched_with") == 1
    for src in (poll, ready):
        assert src.count("p1_pings=entry[\"region_pings\"], p2_pings=opp[\"region_pings\"]") == 1
        assert src.count("p1_pings_at=entry[\"region_pings_at\"], p2_pings_at=opp[\"region_pings_at\"]") == 1


# ── the poll header: validated, then the heartbeat statement carries it ─────

def test_queue_poll_writes_a_valid_header_through_the_heartbeat(issuance):
    at = _now() - timedelta(seconds=20)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, at, at), ME_STEAM)
    before = _now()
    _poll(session, {"x-region-pings": "us=42,eu=31;age=12"})
    after = _now()
    assert len(session.heartbeats) == 1
    sql, params = session.heartbeats[0]
    assert "region_pings = CAST(:region_pings AS JSONB)" in sql
    assert "region_pings_at = CAST(:region_pings_at AS TIMESTAMPTZ)" in sql
    assert "NOW() - make_interval" not in sql, "the stamp is bound, never transaction-start arithmetic (r2 M1)"
    # `mv` (migration 306): the seat's member-scoped mod_version rides the
    # same heartbeat — the fake request carries no header, so it is None.
    assert set(params) == {"pid", "region_pings", "region_pings_at", "mv"}
    assert params["pid"] == ME and params["region_pings"] == '{"eu":31,"us":42}'
    stamp = params["region_pings_at"]
    assert stamp.tzinfo is not None
    assert before - timedelta(seconds=12) <= stamp <= after - timedelta(seconds=12)


@pytest.mark.parametrize("headers", [{}, {"x-region-pings": "us=42;age=-1"}, {"x-region-pings": "garbage"}])
def test_queue_poll_leaves_the_heartbeat_alone_without_a_valid_header(issuance, headers):
    at = _now() - timedelta(seconds=20)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, at, at), ME_STEAM)
    _poll(session, headers)
    assert len(session.heartbeats) == 1
    sql, params = session.heartbeats[0]
    # migration 306: the heartbeat also carries the seat's mod_version (None
    # here — the fake request has no header); the ping columns stay untouched.
    assert sql == "UPDATE ranked_queue SET last_polled = NOW(), mod_version = :mv WHERE player_id = :pid"
    assert params == {"pid": ME, "mv": None}
    assert not any("region_pings" in s and s.startswith("UPDATE") for s, _ in session.statements), \
        "a poll never writes the columns without a valid header, and never NULLs them"


# ── the header and issuance in the SAME poll (impl review r1 M1, 7/3-1) ──────
# `entry` is captured under the locks before the heartbeat; a valid header's
# map and stamp must be what the chooser judges in that request. Each positive
# test here fails when the overlay after the heartbeat UPDATE is removed (#391).

def test_a_valid_header_refreshes_the_stale_map_issuance_sees_in_the_same_poll(issuance):
    """The review's scenario: A's stored stamp is past the window, B's is fresh,
    both ready, and A polls with a fresh header. The heartbeat has just replaced
    A's map, so the room goes by the pair's pings — the pre-heartbeat snapshot
    alone would have said stale and handed the pair to the ladder."""
    stale = _now() - timedelta(seconds=main.REGION_PINGS_ISSUANCE_MAX_AGE_S + 1)
    fresh = _now() - timedelta(seconds=10)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, stale, fresh), ME_STEAM)
    resp = _poll(session, {"x-region-pings": "us=100,eu=30;age=0"})
    assert resp.status == "ready_join"
    assert resp.photon_region == "eu"
    assert issuance == [(ME, PARTNER, resp.room_name, "eu")]
    assert len(session.heartbeats) == 1 and "region_pings" in session.heartbeats[0][1]


def test_a_valid_header_replaces_the_stored_map_issuance_sees_in_the_same_poll(issuance):
    """The map half, independent of staleness: the stored map prefers us, the
    header's prefers eu, both stamps fresh — the header's map decides."""
    fresh = _now() - timedelta(seconds=10)
    session = FakeIssuanceSession(_pair({"us": 30, "eu": 100}, FRESH_MAP_PARTNER, fresh, fresh), ME_STEAM)
    assert _poll(session, {"x-region-pings": "us=100,eu=30;age=5"}).photon_region == "eu"
    assert [s[3] for s in issuance] == ["eu"]


def test_the_header_stamp_is_what_the_issuance_window_judges(issuance):
    """The stamp half: the UPDATE binds the row's stamp as now - age, so a valid
    header whose age is past the window leaves A stale although the STORED stamp
    was fresh — issuance agrees with what the row now holds, not with the snapshot."""
    fresh = _now() - timedelta(seconds=10)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, fresh, fresh), ME_STEAM)
    age = main.REGION_PINGS_ISSUANCE_MAX_AGE_S + 1
    assert _poll(session, {"x-region-pings": f"us=100,eu=30;age={age}"}).photon_region == "us"
    assert [s[3] for s in issuance] == ["us"]


@pytest.mark.parametrize("headers", [{}, {"x-region-pings": "us=100,eu=30;age=-1"}, {"x-region-pings": "garbage"}])
def test_control_a_stale_snapshot_stays_stale_without_a_valid_header(issuance, headers):
    """Negative control (#391): an absent or refused header overlays nothing —
    the stale stored map stays stale and the ladder answers."""
    stale = _now() - timedelta(seconds=main.REGION_PINGS_ISSUANCE_MAX_AGE_S + 1)
    fresh = _now() - timedelta(seconds=10)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, stale, fresh), ME_STEAM)
    resp = _poll(session, headers)
    assert resp.photon_region == "us"
    assert issuance == [(ME, PARTNER, resp.room_name, "us")]
    assert not any("region_pings" in p for _, p in session.heartbeats)


def test_the_persisted_stamp_is_the_stamp_issuance_judges(issuance, monkeypatch):
    """Impl review r2 M1: NOW() is transaction-start time, taken before the
    ordered lock wait, while `now` is read after it — a row dated NOW() - age
    and a snapshot dated now - age differed by the lock wait, so at age 179 a
    2 s wait persisted a map the window already refuses while the overlay still
    read fresh. The stamp is one Python value, bound into the UPDATE (what the
    row holds) and handed to the chooser (what issuance judges)."""
    seen = {}
    real = main._pick_room_region

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(main, "_pick_room_region", spy)
    fresh = _now() - timedelta(seconds=10)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, fresh, fresh), ME_STEAM)
    age = main.REGION_PINGS_ISSUANCE_MAX_AGE_S - 1
    before = _now()
    resp = _poll(session, {"x-region-pings": f"us=100,eu=30;age={age}"})
    after = _now()
    assert resp.status == "ready_join" and resp.photon_region == "eu"
    (_, params), = session.heartbeats
    stamp = params["region_pings_at"]
    assert before - timedelta(seconds=age) <= stamp <= after - timedelta(seconds=age)
    assert session.rows[ME]["region_pings_at"] == stamp, "the row holds the bound stamp"
    assert seen["p1_pings_at"] == stamp, "the chooser judged the bound stamp"
    assert seen["p2_pings_at"] == fresh, "the opponent's stamp comes from its own row"


def test_the_issuance_fake_refuses_a_header_heartbeat_that_lost_a_typed_bind(issuance):
    fresh = _now() - timedelta(seconds=10)
    recorder = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, fresh, fresh), ME_STEAM)
    _poll(recorder, {"x-region-pings": "us=42;age=1"})
    real, params = recorder.heartbeats[0]
    mutations = (
        real.replace("CAST(:region_pings AS JSONB)", ":region_pings"),
        real.replace("CAST(:region_pings_at AS TIMESTAMPTZ)", ":region_pings_at"),
        real.replace("CAST(:region_pings_at AS TIMESTAMPTZ)", "NOW() - make_interval(secs => :region_pings_age)"),
    )
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, fresh, fresh), ME_STEAM)
    # positive control: the unmutated statement passes and lands its stamp on the row
    _run(session.execute(text(real), params))
    assert session.rows[ME]["region_pings_at"] == params["region_pings_at"]
    for mutated in mutations:
        assert mutated != real
        with pytest.raises(AssertionError, match="lost predicate"):
            _run(session.execute(text(mutated), params))
    naive = dict(params, region_pings_at=params["region_pings_at"].replace(tzinfo=None))
    with pytest.raises(AssertionError, match="naive stamp"):
        _run(session.execute(text(real), naive))


def test_the_overlay_sits_between_the_header_heartbeat_and_the_chooser():
    src = inspect.getsource(main.queue_poll)
    stamp = src.index("_hdr_stamp = now - timedelta(seconds=_hdr_age)")
    heartbeat = src.index("CAST(:region_pings_at AS TIMESTAMPTZ)")
    overlay = src.index('entry["region_pings_at"] = _hdr_stamp')
    chooser = src.index("chosen_region = _pick_room_region(")
    assert stamp < heartbeat < overlay < chooser
    assert src.count('entry["region_pings"] = _hdr_pings') == 1
    assert src.count("_hdr_stamp") == 3, "one stamp: computed, bound, overlaid"


def test_queue_poll_parses_the_header_after_the_session_gate_and_before_any_statement():
    src = inspect.getsource(main.queue_poll)
    gate = src.index("_strict_steam_session_ok(request, steam_id, db)")
    parse = src.index('_region_pings_from_header(request.headers.get("x-region-pings"))')
    first_stmt = src.index("await db.execute(")
    assert gate < parse < first_stmt
    assert src.count("CAST(:region_pings_at AS TIMESTAMPTZ)") == 1
    assert "make_interval(secs => :region_pings_age)" not in src, "the poll's stamp is bound, not NOW()-derived (r2 M1)"


def test_join_request_schema_accepts_the_fields_loosely():
    """A malformed map must reach the validator, not 422 the join."""
    from schemas import QueueJoinRequest
    req = QueueJoinRequest(steam_id=ME_STEAM, region_pings=["not", "a", "map"], region_pings_age_s="soon")
    assert req.region_pings == ["not", "a", "map"] and req.region_pings_age_s == "soon"
    assert QueueJoinRequest(steam_id=ME_STEAM).region_pings is None
    assert QueueJoinRequest(steam_id=ME_STEAM).region_pings_age_s is None
