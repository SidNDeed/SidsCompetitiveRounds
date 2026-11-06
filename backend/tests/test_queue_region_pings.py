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
two seats' homes and the ladder's answer, plus 20 ms — the homes since
2026-11-05 (bug 457, learning #1112); before that the references were the
ladder's active-rung candidates;
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
import json
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
    """`refs` are the two seats' homes (what `_region_home_refs` returns); the
    rung adds the ladder's answer to them itself."""
    return main._pick_region_by_pings(p1, p2, ladder, refs=refs)


def _homes(token, pings):
    """This file's OWN reading of a seat's home references (with a map: the
    region the map measures lowest, ties by code, and the token the seat
    sent when the map holds that region; with no map, the token as sent),
    kept independent of main's helper so the bound test below does not trust
    the code it judges."""
    if pings:
        low = min(sorted(pings), key=lambda r: pings[r])
        return {low, token} if token in pings else {low}
    return {token} if token else set()


def _tokens(rng, codes):
    """(my live, opp live, my home, opp home) with blanks, agreeing homes
    sometimes, so every ladder rung comes up."""
    mr, orr = rng.choice(codes + [""] * 3), rng.choice(codes + [""] * 3)
    mh, oh = rng.choice(codes + [""] * 3), rng.choice(codes + [""] * 3)
    if rng.random() < 0.2:
        oh = mh
    return mr, orr, mh, oh


def _ladder(mr, orr, mh, oh, p1, p2):
    """This file's OWN reading of the ladder for a process whose
    corroboration map is empty (the callers clear it): (answer, rung). Two
    homes that agree win outright; then a home that both live snapshots
    name; then the homes something confirms (a live snapshot names the same
    region, or either seat's map holds it); then the live snapshots; then
    the homes nothing confirms; then the default. With the corroboration map
    empty, two signals of one rung that differ resolve to the lower code."""
    def agreed(a, b):
        return min(a, b) if a and b else (a or b)

    if mh and mh == oh:
        return mh, "agree"
    if mr and mr == orr and mr in (mh, oh):
        return mr, "both-live"
    held = [h for h in (mh, oh) if h and (h in (mr, orr) or h in (p1 or {}) or h in (p2 or {}))]
    if held:
        return min(held), "confirmed"
    if mr or orr:
        return agreed(mr, orr), "live"
    if mh or oh:
        return agreed(mh, oh), "unconfirmed"
    return "us", "default"


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
        refs_a = main._region_home_refs(mh, oh, p1, p2)
        refs_b = main._region_home_refs(oh, mh, p2, p1)
        assert set(refs_a) == set(refs_b)
        for ladder in (*refs_a, "us"):
            a = _rung(p1, p2, ladder, refs=refs_a)
            b = _rung(p2, p1, ladder, refs=refs_b)
            assert a[:3] == b[:3], f"{p1} / {p2} ladder={ladder}: {a} vs {b}"
            assert len(a) == 4 and len(b) == 4


def test_a_seat_is_never_moved_beyond_the_homes_and_the_ladder_on_its_own_numbers(capsys):
    """The bound (2026-11-05): whenever rung 0 moves the room, each seat's
    ping at the pick, read from its OWN map, is at most the worst it measured
    among the two seats' homes and the ladder's answer, plus 20 ms. Fuzzed
    over maps, live tokens and homes, END TO END through _pick_room_region:
    the ladder's answer and the homes are this file's own readings (_ladder,
    _homes), so neither oracle is the helper under test (impl review of
    2026-09-09: a helper that ranked its inputs wrongly passed every test
    that trusted the helper). The ladder is not "the picker run without
    maps": a fresh map is one of the signs that confirm a home, so the own
    reading takes the maps the picker was given, and the line the picker
    prints must name the same answer. Positive controls: rooms do move,
    every ladder rung comes up, some moves involve a seat whose homes are
    not just the token it sent, and the rung never declines for want of a
    bound (why=unbounded)."""
    rng = random.Random(23)
    codes = ["us", "eu", "asia", "sa", "jp", "au", "kr", "ru"]
    now = _now()
    fresh = now - timedelta(seconds=30)
    moved, measured, rungs = 0, 0, set()
    main._REGION_SEEN.clear()
    for _ in range(4000):
        p1 = {c: rng.randint(1, 400) for c in codes if rng.random() < 0.7}
        p2 = {c: rng.randint(1, 400) for c in codes if rng.random() < 0.7}
        mr, orr, mh, oh = _tokens(rng, codes)
        ladder, rung = _ladder(mr, orr, mh, oh, p1, p2)
        rungs.add(rung)
        pick = main._pick_room_region(mr, mh, orr, oh, "fuzz", p1_pings=p1 or None, p2_pings=p2 or None,
                                      p1_pings_at=fresh, p2_pings_at=fresh, now=now)
        line = [x for x in capsys.readouterr().out.splitlines() if "[QUEUE-REGION]" in x][0]
        assert "why=unbounded" not in line, line
        if "rung=pings" in line:
            assert f" ladder={ladder} " in line, f"{line}: own reading {ladder} ({rung})"
        else:
            assert pick == ladder, f"{line}: own reading {ladder} ({rung})"
        if pick == ladder:
            continue
        moved += 1
        measured += 0 if (_homes(mh, p1) == {mh} and _homes(oh, p2) == {oh}) else 1
        refs = _homes(mh, p1) | _homes(oh, p2) | {ladder}
        for p in (p1, p2):
            allowed = max(p[r] for r in refs if r in p) + main.REGION_PINGS_MARGIN_MS
            assert p[pick] <= allowed, f"{p} moved to {pick} ({p[pick]}) beyond {allowed}: refs={refs}"
    assert moved > 200, moved
    assert measured > 20, measured
    assert rungs == {"agree", "both-live", "confirmed", "live", "unconfirmed", "default"}, rungs


def test_the_homes_bound_a_seat_and_the_live_snapshots_do_not(capsys):
    """The references are the two seats' HOMES and the ladder's answer; a
    live snapshot is not one unless the ladder answered it. Both snapshots
    read sa while both home tokens are asia: the homes agree, the ladder
    answers asia, and seat 1's bound is read from asia alone (it never
    measured eu, the region seat 2's map measures lowest), so seat 1 stays
    at 20 ms. With the snapshots as references sa would have raised seat 1's
    bound from 40 to 320 and moved it from 20 to 300 ms. `_region_home_refs`
    is the one place that knows what a home is, and the caller must use
    it."""
    main._REGION_SEEN.clear()
    now = _now()
    fresh = now - timedelta(seconds=30)
    assert main._pick_room_region("sa", "asia", "sa", "asia", "r", p1_pings={"asia": 20, "sa": 300},
                                  p2_pings={"asia": 500, "eu": 20, "sa": 30}, p1_pings_at=fresh,
                                  p2_pings_at=fresh, now=now) == "asia"
    lines = [line for line in capsys.readouterr().out.splitlines() if "[QUEUE-REGION]" in line]
    assert lines[0] == ("[QUEUE-REGION] room=r pick=asia rung=pings worst=500 ladder=asia cand=asia "
                        "cand_ms=20/500 ladder_ms=20/500 bound=40/520 refs=asia,eu")
    assert "_region_home_refs(mh, oh, m1, m2)" in inspect.getsource(main._pick_room_region)
    assert "_region_ladder_refs" not in inspect.getsource(main)
    # one home sent (asia, seat 2; both maps measured it, so the ladder reads it ahead of the
    # snapshots): seat 1 is represented by its map's lowest region (eu), so both regions are
    # references and the pair's least-worst region is taken — asia at 300/20, where the
    # snapshots alone (eu, eu) kept the pair on eu at 20/500 until 2026-11-05
    assert main._pick_room_region("eu", "", "eu", "asia", "r", p1_pings={"eu": 20, "asia": 300},
                                  p2_pings={"eu": 500, "asia": 20}, p1_pings_at=fresh, p2_pings_at=fresh,
                                  now=now) == "asia"
    lines = [line for line in capsys.readouterr().out.splitlines() if "[QUEUE-REGION]" in line]
    assert lines[0] == ("[QUEUE-REGION] room=r pick=asia rung=pings worst=300 ladder=asia cand=asia "
                        "cand_ms=300/20 ladder_ms=300/20 bound=320/520 refs=eu,asia")


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
    the references it DID measure; with none measured the rung declines
    (why=unbounded; reached through the rung alone, as here: the room picker
    always passes each seat a home its own map holds), and a pair whose only
    shared region lies above a bound gets the ladder (why=bound). Both
    refusals name what was seen."""
    assert _rung({"eu": 30}, {"eu": 35}, "us") == ("us", "unbounded", None, "cand=eu cand_ms=30/35 ladder_ms=-/- bound=-/-")
    assert _rung({"eu": 200, "asia": 30}, {"eu": 35}, "us")[:3] == ("us", "unbounded", None)
    # seat 2 never measured us (the ladder's answer); eu is seat 2's home, so
    # it is a reference and seat 1 measured it at 200 -> within bounds
    lifted = _rung({"eu": 200, "us": 5}, {"eu": 35}, "us", refs=("", "", "us", "eu"))
    assert lifted == ("eu", "pings", 200, "cand=eu cand_ms=200/35 ladder_ms=5/- bound=220/55")
    # each seat measured one reference, neither measured the other's; the only
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
    refs = main._region_home_refs("rue", "ru", opp, spirit)
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
    stale = now - timedelta(seconds=main.REGION_PINGS_ROOM_MAX_AGE_S + 1)
    kw = dict(p1_pings=FRESH_MAP, p2_pings=FRESH_MAP_PARTNER, now=now)
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings_at=fresh, p2_pings_at=fresh, **kw) == "eu"
    out = capsys.readouterr().out
    rung, ladder = [line for line in out.splitlines() if "[QUEUE-REGION]" in line][:2]
    assert rung == "[QUEUE-REGION] room=r pick=eu rung=pings worst=30 ladder=us cand=eu cand_ms=30/25 ladder_ms=100/90 bound=120/110 refs=eu,us"
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


def test_a_map_the_join_accepted_still_decides_the_room(capsys):
    """The room window is the acceptance bound (REGION_PINGS_ROOM_MAX_AGE_S,
    2026-11-05). A map measured 200 s ago, past the 180 s this path read until
    then, decides the room; the bound itself is inclusive; one second past it
    the map is stale and the ladder answers."""
    now = _now()
    kw = dict(p1_pings=FRESH_MAP, p2_pings=FRESH_MAP_PARTNER, now=now)
    assert main.REGION_PINGS_ROOM_MAX_AGE_S == main.REGION_PINGS_MAX_AGE_S == 900
    at = now - timedelta(seconds=200)
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings_at=at, p2_pings_at=at, **kw) == "eu"
    assert "rung=pings" in capsys.readouterr().out
    edge = now - timedelta(seconds=900)
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings_at=edge, p2_pings_at=edge, **kw) == "eu"
    capsys.readouterr()
    past = now - timedelta(seconds=901)
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings_at=at, p2_pings_at=past, **kw) == "us"
    assert "rung=ladder why=stale" in capsys.readouterr().out


def test_the_room_window_is_judged_to_the_microsecond(capsys):
    """Codex round REGION-R2, the class: the test above judges ages of whole
    seconds (200, 900 and 901), so with an age cut down to whole seconds, or
    with the comparison's window half a second longer, each of its picks
    answers the same. A map decides the room up to and including 900 s and
    not one microsecond longer, whichever seat's map it is."""
    now = _now()
    kw = dict(p1_pings=FRESH_MAP, p2_pings=FRESH_MAP_PARTNER, now=now)
    window = timedelta(seconds=main.REGION_PINGS_ROOM_MAX_AGE_S)
    recent = now - timedelta(seconds=60)
    for inside in (window - timedelta(microseconds=1), window):
        for p1_at, p2_at in ((now - inside, recent), (recent, now - inside), (now - inside, now - inside)):
            got = main._pick_room_region("us", "us", "us", "us", "r", p1_pings_at=p1_at, p2_pings_at=p2_at, **kw)
            assert got == "eu", inside
            assert "rung=pings" in capsys.readouterr().out, inside
    for outside in (window + timedelta(microseconds=1), window + timedelta(milliseconds=500),
                    window + timedelta(microseconds=999999)):
        for p1_at, p2_at in ((now - outside, recent), (recent, now - outside), (now - outside, now - outside)):
            got = main._pick_room_region("us", "us", "us", "us", "r", p1_pings_at=p1_at, p2_pings_at=p2_at, **kw)
            assert got == "us", outside
            assert "rung=ladder why=stale" in capsys.readouterr().out, outside


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
    assert lines[0] == "[QUEUE-REGION] room=r pick=us rung=ladder why=margin cand=eu cand_ms=90/75 ladder_ms=100/60 bound=120/95 refs=eu,us"
    # the two homes are the reference set: with homes (us, eu) the ladder
    # answers eu once corroboration is cold (the alphabet), so eu lies inside
    # BOTH seats' bounds and the maps confirm it as the pair's least-worst
    main._REGION_SEEN.clear()
    assert main._pick_room_region("", "us", "", "eu", "r", p1_pings={"us": 10, "eu": 80},
                                  p2_pings={"us": 100, "eu": 30}, p1_pings_at=fresh, p2_pings_at=fresh,
                                  now=now) == "eu"
    lines = [line for line in capsys.readouterr().out.splitlines() if "[QUEUE-REGION]" in line]
    assert lines[0] == "[QUEUE-REGION] room=r pick=eu rung=pings worst=80 ladder=eu cand=eu cand_ms=80/30 ladder_ms=80/30 bound=100/120 refs=us,eu"
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


REFUSED_MAPS = (
    {"": 1, "eu": 90, "us": 50},          # an empty key beside good entries
    {"": 1},                              # an empty key alone
    {"EU": 10, "us": 50},                 # upper case
    {" eu": 10, "us": 50},                # padded
    {"e": 10, "us": 50},                  # too short
    {"europe": 10, "us": 50},             # too long
    {"eu": 0, "us": 50},                  # a value below 1
    {"eu": 5001, "us": 50},               # a value above the cap
    {"eu": True, "us": 50},               # a bool
    {"eu": 10.5, "us": 50},               # a float
    ["eu", 10],                           # not an object
    '{"": 1, "eu": 90, "us": 50}',        # the JSON text of a refused map
    "not json",                           # text that is no JSON
    {},                                   # no entries
)


def test_maps_with_an_empty_key_decide_nothing_at_the_room_picker(capsys):
    """The three pairs of Codex round REGION-R1. `_region_token` answers a
    refusal with the empty string, so the key test `_region_token(k) == k`
    admitted an empty key; a seat's lowest "region" could then be the empty
    string, which the home references drop. With such maps the first pair got
    eu at a worst ping of 90 where us was shared at 50, the second an EMPTY
    room region, the third a rung that ran without a bound. Each map is
    refused whole now, so each pair gets the ladder's answer, as objects and
    as the JSON text a driver may hand back, whichever seat asked."""
    now = _now()
    at = now - timedelta(seconds=30)
    cases = [
        (("", ""), ("eu", "eu"), {"": 1, "eu": 90, "us": 50}, {"": 100, "eu": 1, "us": 50}, "eu"),
        (("ru", "ru"), ("eu", "us"), {"": 1, "eu": 100, "us": 200}, {"": 1, "eu": 200, "us": 100}, "ru"),
        (("", ""), ("", ""), {"": 1}, {"": 1}, "us"),
    ]
    for (mr, orr), (mh, oh), p1, p2, want in cases:
        for a, b in ((p1, p2), (json.dumps(p1), json.dumps(p2))):
            for swap in (False, True):
                main._REGION_SEEN.clear()
                args = (orr, oh, mr, mh) if swap else (mr, mh, orr, oh)
                maps = (b, a) if swap else (a, b)
                got = main._pick_room_region(*args, "r", p1_pings=maps[0], p2_pings=maps[1],
                                             p1_pings_at=at, p2_pings_at=at, now=now)
                first, second = _region_lines(capsys)
                assert got == want, (mr, orr, mh, oh, swap, got)
                assert "rung=ladder why=no-maps" in first and "refs=" not in first, first
                assert f"chosen={want} " in second, second
    # control: the first pair without the empty keys is decided by its maps
    main._REGION_SEEN.clear()
    assert main._pick_room_region("", "eu", "", "eu", "r", p1_pings={"eu": 90, "us": 50},
                                  p2_pings={"eu": 1, "us": 50}, p1_pings_at=at, p2_pings_at=at, now=now) == "us"
    assert "rung=pings worst=50" in _region_lines(capsys)[0]


def test_a_map_the_validator_refuses_reads_as_no_map_at_either_seat(capsys):
    """Whatever a stored map holds, the room picker reads it through the
    validator, and a map the validator refuses is the same as no map: the room
    and both printed lines equal those of the same pair with that seat's map
    absent. The other seat's fresh map still counts as a sign that a home is
    in service, in both readings alike."""
    now = _now()
    at = now - timedelta(seconds=30)
    other = {"eu": 40, "us": 70, "asia": 200}
    pairs = [(("", ""), ("eu", "eu")), (("ru", "ru"), ("eu", "us")), (("", ""), ("", "")),
             (("us", "eu"), ("", "asia"))]
    for refused in REFUSED_MAPS:
        for (mr, orr), (mh, oh) in pairs:
            for seat in (1, 2):
                main._REGION_SEEN.clear()
                held = (refused, other) if seat == 1 else (other, refused)
                got = main._pick_room_region(mr, mh, orr, oh, "r", p1_pings=held[0], p2_pings=held[1],
                                             p1_pings_at=at, p2_pings_at=at, now=now)
                got_lines = _region_lines(capsys)
                absent = (None, other) if seat == 1 else (other, None)
                want = main._pick_room_region(mr, mh, orr, oh, "r", p1_pings=absent[0], p2_pings=absent[1],
                                              p1_pings_at=at, p2_pings_at=at, now=now)
                assert (got, got_lines) == (want, _region_lines(capsys)), (refused, mr, orr, mh, oh, seat)
                assert got and "rung=ladder why=no-maps" in got_lines[0], (refused, got, got_lines)


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
        l1, l2 = rng.choice(["", "us", "asia"]), rng.choice(["", "us", "asia"])
        a = main._pick_room_region(l1, h1, l2, h2, "r", p1_pings=m1, p2_pings=m2, p1_pings_at=t1, p2_pings_at=t2, now=now)
        b = main._pick_room_region(l2, h2, l1, h1, "r", p1_pings=m2, p2_pings=m1, p1_pings_at=t2, p2_pings_at=t1, now=now)
        assert a == b, f"({l1},{h1}) vs ({l2},{h2}) maps {m1} / {m2}: {a} / {b}"


# ── the home-referenced rule of 2026-11-05 (bug 457, learning #1112) ────────
#
# SID_MAP holds the three regions the lane's design reads from bug 457's log.
# SPIRIT_MAP is the opponent's map as that design states it from earlier
# sweeps, NOT from that day's log (his upload could not be read), so the
# replays below are a constructed pair in the 4 Nov shape, not a recording:
# seat 1's live snapshot was left on ru by quick play while its home is usw.

SID_MAP = {"usw": 19, "us": 64, "ru": 147}
SPIRIT_MAP = {"ru": 40, "eu": 25, "us": 90, "usw": 150}


def _fresh_pair(now, p1=SID_MAP, p2=SPIRIT_MAP):
    at = now - timedelta(seconds=30)
    return dict(p1_pings=p1, p2_pings=p2, p1_pings_at=at, p2_pings_at=at, now=now)


def _region_lines(capsys):
    return [line for line in capsys.readouterr().out.splitlines() if "[QUEUE-REGION]" in line]


def test_replay_of_4_november_lands_on_the_shared_region(capsys):
    """Both live snapshots read ru (seat 1's left there by quick play); the
    home tokens are usw and ru. Both snapshots name seat 2's home, so the
    ladder answers ru, as it did before. The references are the HOMES (usw
    for seat 1; for seat 2 eu, which its map measures lowest, and ru, its
    token), so seat 2's bound is its usw ping plus 20 (170) and us at 64/90
    is reachable; it beats the ladder's ru (147/40) by 57 ms and is taken.
    Under the rule this replaced ru was the only reference: seat 2's bound
    was 40 + 20, every US region lay outside it, and the room stayed on
    ru."""
    main._REGION_SEEN.clear()
    now = _now()
    assert main._pick_room_region("ru", "usw", "ru", "ru", "r", **_fresh_pair(now)) == "us"
    lines = _region_lines(capsys)
    assert lines[0] == (
        "[QUEUE-REGION] room=r pick=us rung=pings worst=90 ladder=ru cand=us cand_ms=64/90 "
        "ladder_ms=147/40 bound=167/170 refs=usw,eu,ru")
    assert lines[1] == "[QUEUE-REGION] room=r chosen=us seen=n live=(ru,ru) home=(usw,ru) home_ok=(y,y)"
    # whichever seat's request issued the room
    assert main._pick_room_region("ru", "ru", "ru", "usw", "r", **_fresh_pair(now, SPIRIT_MAP, SID_MAP)) == "us"
    assert _region_lines(capsys)[0].endswith("bound=170/167 refs=eu,ru,usw")


def test_replay_of_3_november_is_unchanged():
    """The same pair with seat 1's snapshot on its own region: us before this
    change (the live rung carried usw, so both regions were references) and
    us after it."""
    main._REGION_SEEN.clear()
    assert main._pick_room_region("usw", "usw", "ru", "ru", "r", **_fresh_pair(_now())) == "us"


def test_a_seat_without_a_home_token_is_represented_by_its_maps_lowest_region(capsys):
    """No home token from seat 1: the region its map measures lowest (usw at
    19) is its one home, so the references and the pick are those of the
    replay. The ladder answers the lone home ru, which both live snapshots
    name."""
    main._REGION_SEEN.clear()
    assert main._pick_room_region("ru", "", "ru", "ru", "r", **_fresh_pair(_now())) == "us"
    assert _region_lines(capsys)[0].endswith(
        "ladder=ru cand=us cand_ms=64/90 ladder_ms=147/40 bound=167/170 refs=usw,eu,ru")
    assert main._region_home_refs("", "ru", SID_MAP, SPIRIT_MAP) == ("usw", "eu", "ru")
    assert main._region_home_refs("", "", {"us": 30, "eu": 30}, {"us": 5}) == ("eu", "us"), "tie: code order"
    assert main._region_home_refs("", "eu", {"eu": 1}, None) == ("eu",), "duplicates collapse"
    assert main._region_home_refs("", "", None, None) == ()


def test_with_no_home_sent_the_ladders_answer_is_a_reference_too(capsys):
    """Neither seat sent a home token: the ladder's answer is read from the
    live snapshots (ru, ru) and joins the two stand-in homes (usw, eu) in the
    reference set, because it is the room the pair gets when the rung
    declines. Seat 1 measured ru at 147, so its bound is 167 and us (64/90)
    lies within it; us beats ru (147/40) by 57 ms and is taken. With the
    stand-in homes alone seat 1's bound would be 39 (usw 19 + 20), us would
    lie outside it, and the pair would stay on ru at 147/40, a region that
    same bound calls too far for seat 1."""
    main._REGION_SEEN.clear()
    now = _now()
    assert main._pick_room_region("ru", "", "ru", "", "r", **_fresh_pair(now)) == "us"
    assert _region_lines(capsys)[0] == (
        "[QUEUE-REGION] room=r pick=us rung=pings worst=90 ladder=ru cand=us cand_ms=64/90 "
        "ladder_ms=147/40 bound=167/170 refs=usw,eu")
    # whichever seat's request issued the room
    assert main._pick_room_region("ru", "", "ru", "", "r", **_fresh_pair(now, SPIRIT_MAP, SID_MAP)) == "us"
    assert _region_lines(capsys)[0].endswith("bound=170/167 refs=eu,usw")


def test_a_confirmed_home_outranks_a_live_snapshot_in_the_ladder(capsys):
    """Without both maps the ladder decides alone. A home that something
    confirms is still in service is read before any live snapshot, a lone
    home included. Each sign in turn: two reporters seen in the region; a
    live snapshot of either seat naming it; a fresh map of either seat that
    measured it (one map never runs rung 0, so the ladder still decides
    alone). A map past the room window is no sign."""
    now = _now()
    fresh = now - timedelta(seconds=30)
    stale = now - timedelta(seconds=main.REGION_PINGS_ROOM_MAX_AGE_S + 1)
    main._REGION_SEEN.clear()
    main._note_region_seen("usw", ME_STEAM)
    main._note_region_seen("usw", PARTNER_STEAM)
    assert main._pick_room_region("ru", "usw", "ru", "", "r") == "usw"
    assert main._pick_room_region("ru", "", "ru", "usw", "r") == "usw"
    assert _region_lines(capsys)[1::2] == [
        "[QUEUE-REGION] room=r chosen=usw seen=y live=(ru,ru) home=(usw,) home_ok=(y,-)",
        "[QUEUE-REGION] room=r chosen=usw seen=y live=(ru,ru) home=(,usw) home_ok=(-,y)"]
    main._REGION_SEEN.clear()
    # a live snapshot names the home's region: the seat's own, then the other seat's
    assert main._pick_room_region("usw", "usw", "ru", "", "r") == "usw"
    assert main._pick_room_region("ru", "usw", "usw", "", "r") == "usw"
    # a fresh map measured it: the seat's own, then the other seat's
    assert main._pick_room_region("ru", "usw", "ru", "", "r", p1_pings={"usw": 19}, p1_pings_at=fresh,
                                  now=now) == "usw"
    assert main._pick_room_region("ru", "usw", "ru", "", "r", p2_pings={"usw": 150}, p2_pings_at=fresh,
                                  now=now) == "usw"
    lines = _region_lines(capsys)
    assert len(lines) == 8 and all("rung=ladder why=no-maps" in line for line in lines[::2])
    assert lines[1] == "[QUEUE-REGION] room=r chosen=usw seen=n live=(usw,ru) home=(usw,) home_ok=(y,-)"
    assert lines[7] == "[QUEUE-REGION] room=r chosen=usw seen=n live=(ru,ru) home=(usw,) home_ok=(y,-)"
    # a map measured too long ago is no sign: the snapshots decide
    assert main._pick_room_region("ru", "usw", "ru", "", "r", p1_pings={"usw": 19}, p1_pings_at=stale,
                                  now=now) == "ru"
    assert _region_lines(capsys)[1] == (
        "[QUEUE-REGION] room=r chosen=ru seen=n live=(ru,ru) home=(usw,) home_ok=(n,-)")


def test_a_home_nothing_confirms_ranks_below_a_live_snapshot(capsys):
    """A home token is an untimestamped cache and can name a region since
    retired. With the corroboration map empty, no map from either seat and
    no snapshot naming it, nothing says the region is still in service, and
    the home ranks below the live snapshots, where it ranked before
    2026-11-05. It is still a candidate: it decides the room when there is
    no snapshot, and two homes that agree win outright."""
    main._REGION_SEEN.clear()
    cases = [(("ru", "usw", "ru", ""), "ru"), (("ru", "", "ru", "usw"), "ru"),
             (("ru", "usw", "ru", "eu"), "ru"), (("", "usw", "", ""), "usw"),
             (("", "usw", "", "eu"), "eu"), (("ru", "usw", "ru", "usw"), "usw"),
             (("ru", "", "ru", ""), "ru")]
    for args, want in cases:
        assert main._pick_room_region(*args, "r") == want, args
    lines = _region_lines(capsys)
    assert len(lines) == 14 and all("rung=ladder why=no-maps" in line for line in lines[::2])
    assert lines[1] == "[QUEUE-REGION] room=r chosen=ru seen=n live=(ru,ru) home=(usw,) home_ok=(n,-)"
    assert lines[5] == "[QUEUE-REGION] room=r chosen=ru seen=n live=(ru,ru) home=(usw,eu) home_ok=(n,n)"
    assert lines[11] == "[QUEUE-REGION] room=r chosen=usw seen=n live=(ru,ru) home=(usw,usw) home_ok=(n,n)"
    assert lines[13] == "[QUEUE-REGION] room=r chosen=ru seen=n live=(ru,ru) home=(,) home_ok=(-,-)"


def test_a_home_token_its_own_map_never_measured_is_no_reference(capsys):
    """A seat's home REFERENCES are regions its own map measured: the region
    the map measures lowest, and the token it sent when the map holds that
    region. Seat 1 sends sa, which neither map measured. Read as a
    reference, sa has no numbers, so the ladder's ru would be the one
    reference that has: seat 2's bound would be 40 + 20, every US region
    would lie outside it, and the pair would stay on ru at 147/40 (bug 457's
    shape again, from a token instead of a snapshot). With seat 1's lowest
    region (usw) as its home, the references and the pick are those of the
    replay."""
    main._REGION_SEEN.clear()
    now = _now()
    assert main._pick_room_region("", "sa", "", "ru", "r", **_fresh_pair(now)) == "us"
    assert _region_lines(capsys)[0].endswith(
        "ladder=ru cand=us cand_ms=64/90 ladder_ms=147/40 bound=167/170 refs=usw,eu,ru")
    # whichever seat's request issued the room
    assert main._pick_room_region("", "ru", "", "sa", "r", **_fresh_pair(now, SPIRIT_MAP, SID_MAP)) == "us"
    assert _region_lines(capsys)[0].endswith("bound=170/167 refs=eu,ru,usw")
    # seat 1 measured neither its token nor the ladder's ru: read as a reference, the token
    # left seat 1 with no bound at all and the rung declined (why=unbounded); now seat 1's
    # bound is its own usw + 20 and the room is the one shared region inside both bounds
    assert main._pick_room_region("", "sa", "", "ru", "r", **_fresh_pair(now, {"usw": 19, "us": 64})) == "usw"
    lines = _region_lines(capsys)
    assert lines[0] == ("[QUEUE-REGION] room=r pick=usw rung=pings worst=150 ladder=ru cand=usw "
                        "cand_ms=19/150 ladder_ms=-/40 bound=39/170 refs=usw,eu,ru")
    assert lines[1] == "[QUEUE-REGION] room=r chosen=usw seen=n live=(,) home=(sa,ru) home_ok=(n,y)"
    assert main._region_home_refs("sa", "", {"us": 30, "eu": 10}, {"us": 5}) == ("eu", "us")
    assert main._region_home_refs("us", "", {"us": 30, "eu": 10}, None) == ("eu", "us"), "measured home, then token"
    assert main._region_home_refs("sa", "eu", None, {"us": 5}) == ("sa", "us"), "no map: the token as sent"


def test_a_cached_home_far_from_the_measured_one_does_not_bound_the_other_seat(capsys):
    """A home token is an untimestamped cache. Seat 1's token says asia, a
    region its own map now measures at 220 ms while it measures eu at 17;
    seat 2 sent no token and measures asia lowest. With the token as seat
    1's only home, asia would be the only reference: seat 2's bound would be
    its asia ping plus 20 (70), every region between the two would lie
    outside it, and the pair would stay on asia at 220/50. The region seat
    1's map measures lowest (eu) is a home too, so seat 2's bound is its eu
    ping plus 20 (230) and us at 90/95 is taken: the lowest worst ping of
    the three regions the two maps share."""
    main._REGION_SEEN.clear()
    now = _now()
    moved = {"eu": 17, "asia": 220, "us": 90}
    other = {"asia": 50, "us": 95, "eu": 210}
    assert main._pick_room_region("", "asia", "", "", "r", **_fresh_pair(now, moved, other)) == "us"
    lines = _region_lines(capsys)
    assert lines[0] == ("[QUEUE-REGION] room=r pick=us rung=pings worst=95 ladder=asia cand=us "
                        "cand_ms=90/95 ladder_ms=220/50 bound=240/230 refs=eu,asia")
    assert lines[1] == "[QUEUE-REGION] room=r chosen=us seen=n live=(,) home=(asia,) home_ok=(y,-)"
    # whichever seat's request issued the room
    assert main._pick_room_region("", "", "", "asia", "r", **_fresh_pair(now, other, moved)) == "us"
    assert _region_lines(capsys)[0].endswith("bound=230/240 refs=asia,eu")


def test_with_each_others_lowest_region_measured_the_room_is_within_the_margin_of_the_best_shared_one(capsys):
    """What the measured home buys (2026-11-05). Whenever both maps are
    fresh and each holds the region the OTHER map measures lowest, the
    room's worst ping, by the pair's own numbers, is at most the lowest
    worst ping any shared region offers plus 20 ms: whatever the four tokens
    say (a cached home far from where its seat now measures lowest
    included) and whatever the corroboration map holds. Judged against this
    file's own reading of the two maps; nothing here asks the code what it
    did. Controls: the room IS a best shared region most of the time, and a
    home token that is not its seat's lowest region is common."""
    rng = random.Random(41)
    codes = ["us", "eu", "asia", "sa", "jp", "au", "kr", "ru", "usw", "in"]
    now = _now()
    fresh = now - timedelta(seconds=30)
    checked = best = apart = 0
    for _ in range(3000):
        p1 = {c: rng.randint(1, 400) for c in codes if rng.random() < 0.85}
        p2 = {c: rng.randint(1, 400) for c in codes if rng.random() < 0.85}
        mr, orr, mh, oh = _tokens(rng, codes)
        seen = [c for c in codes if rng.random() < 0.3]
        if not p1 or not p2:
            continue
        low1, low2 = min(sorted(p1), key=p1.get), min(sorted(p2), key=p2.get)
        if low1 not in p2 or low2 not in p1:
            continue
        main._REGION_SEEN.clear()
        for c in seen:
            main._note_region_seen(c, ME_STEAM)
            main._note_region_seen(c, PARTNER_STEAM)
        pick = main._pick_room_region(mr, mh, orr, oh, "fuzz", p1_pings=p1, p2_pings=p2,
                                      p1_pings_at=fresh, p2_pings_at=fresh, now=now)
        capsys.readouterr()
        shared = set(p1) & set(p2)
        lowest_worst = min(max(p1[r], p2[r]) for r in shared)
        case = f"live=({mr},{orr}) home=({mh},{oh}) seen={seen} maps {p1} / {p2}"
        assert pick in shared, f"{case}: {pick} is not a region both measured"
        worst = max(p1[pick], p2[pick])
        assert worst <= lowest_worst + main.REGION_PINGS_MARGIN_MS, (
            f"{case}: {pick} at {worst}, the best shared region is at {lowest_worst}")
        checked += 1
        best += worst == lowest_worst
        apart += (mh not in ("", low1)) or (oh not in ("", low2))
    main._REGION_SEEN.clear()
    assert checked > 1500, checked
    assert best > checked // 2, (best, checked)
    assert apart > 500, apart


def test_a_one_entry_map_obtains_that_seats_home_and_no_more():
    """The #283 note in main.py, executed. Seat 1 names sa as its home and
    sends a map holding sa alone: the only shared region is sa, seat 2
    measured it (180), and seat 2's bound is the worst it measured among the
    homes sa and eu plus 20, so sa is taken. Seat 2 lands at its OWN
    measurement of seat 1's home and nowhere beyond it. A seat 2 that never
    measured sa shares no region with that map and gets the ladder."""
    main._REGION_SEEN.clear()
    now = _now()
    other = {"sa": 180, "eu": 20, "us": 90}
    assert main._pick_room_region("", "sa", "", "eu", "r", **_fresh_pair(now, {"sa": 1}, other)) == "sa"
    assert main._pick_room_region("", "sa", "", "eu", "r",
                                  **_fresh_pair(now, {"sa": 1}, {"eu": 20, "us": 90})) == "eu"


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
    ({"": 42}, 12), ({"": 42, "us": 42}, 12), ({"us": 42, "": 42}, 12),   # an empty key
    ({"us": 0}, 12), ({"us": 5001}, 12), ({"us": 42.0}, 12), ({"us": True}, 12), ({"us": "42"}, 12),
    ({"us": 42}, -1), ({"us": 42}, 901), ({"us": 42}, "12"), ({"us": 42}, 12.5), ({"us": 42}, True), ({"us": 42}, None),
    (["us", 42], 12), ("us=42", 12), (None, 12),
])
def test_validator_refuses_everything_else(pings, age):
    assert main._region_pings_validate(pings, age) == (None, None)


def test_the_shared_cleaner_refuses_a_map_with_an_empty_key():
    """`_region_token` answers a refusal with the empty string, so an empty
    key equals its own refusal and the cleaner has to name it. The join
    validator and the header reader both end in this cleaner; the two
    parametrised refusal lists around this test carry the same case through
    each of them."""
    assert main._region_token("") == ""
    for pings in ({"": 1}, {"": 1, "eu": 90}, {"eu": 90, "": 1}):
        assert main._region_pings_clean(pings) is None, pings
    assert main._region_pings_clean({"eu": 90}) == {"eu": 90}
    assert main._region_pings_validate({"": 1, "eu": 90}, 0) == (None, None)
    assert main._region_pings_from_header("=1,eu=90;age=0") == (None, None)
    assert main._region_pings_from_header("eu=90;age=0") == ('{"eu":90}', 0)


def test_header_parser_feeds_the_join_validator():
    assert main._region_pings_from_header("us=42,eu=31;age=12") == ('{"eu":31,"us":42}', 12)
    assert main._region_pings_from_header(" us=42 , eu=31 ; age=0 ") == ('{"eu":31,"us":42}', 0)


@pytest.mark.parametrize("value", [
    None, "", "us=42", "us=42;age=-5", "us=42;age=", "us=42;age=1.5", "us=42;age=901",
    "us=42,us=43;age=1", "us=4a;age=1", "us;age=1", "US=42;age=1", "us=42;age=1;x",
    ";age=1", "us=0;age=1", "x" * 600,
    "=1;age=0", "=1,us=42;age=1", "us=42,=1;age=1",        # an entry with no code is an empty key
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

    # The lease admission gate (stage 2, inside _lease_acquire_many) reads
    # through these at the ranked room issue and queue_ready's re-acquire:
    # clock_timestamp() by scalar_one, the lock_timeout swap by
    # mappings().one(), the queue union and the leases by mappings().all(),
    # the live holds by scalars().all().
    def all(self):
        return list(self._rows)

    def one(self):
        assert len(self._rows) == 1, self._rows
        return self._rows[0]

    def scalar_one(self):
        assert len(self._rows) == 1, self._rows
        return self._rows[0]

    def scalars(self):
        return self


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
        # A1: the pair's queue_leases state. A normally-matched pair holds its
        # exact ("ranked", None) predecessor -- queue_poll's matched branch
        # acquires it in the same transaction as the status write -- and
        # queue_ready now REQUIRES it before issuing a room. Modelled here so
        # these region tests exercise the issuance they are about; the gate's
        # own refusal path is tested in test_a1_identity_formation.py.
        self.lease_mode = "ranked"
        self.leases_written = []

    async def execute(self, statement, params=None):
        params = dict(params or {})
        sql = " ".join(str(statement).split())
        self.statements.append((sql, params))
        # The lease admission gate's reads (stage 2; _lease_acquire_many at
        # the ranked room issue and at queue_ready's re-acquire), answered
        # with the pair's own state: its two ranked queue rows and its
        # group-less ranked leases are the keys the site allows, and no live
        # match seat hold exists, so the gate admits the formation. These
        # sit above the ranked_queue branch, whose projection parser would
        # otherwise take the union.
        if sql == "SELECT clock_timestamp()":
            return _Result([_now()])
        if "set_config('lock_timeout'" in sql:
            return _Result([{"value": "0"}]) if "FROM previous" in sql else _Result([])
        if "FROM players" in sql and "FOR NO KEY UPDATE" in sql:
            return _Result([params.get("pid")])
        if "UNION ALL" in sql and "FROM ranked_queue" in sql:
            asked = {str(p) for p in params.get("pids", ())}
            return _Result([{"player_id": pid, "mode": "ranked", "group_id": None,
                             "status": row["status"]}
                            for pid, row in self.rows.items() if str(pid) in asked])
        if "FROM match_seat_holds" in sql:
            return _Result([])
        if "FROM queue_leases" in sql and "pids" in params:
            if self.lease_mode is None:
                return _Result([])
            asked = {str(p) for p in params["pids"]}
            return _Result([{"player_id": pid, "mode": self.lease_mode, "group_id": None}
                            for pid in self.rows if str(pid) in asked])
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
        if "FROM queue_leases" in sql:
            # lease_mode None models a lapsed commitment, which A1 dissolves
            # rather than resurrecting.
            if self.lease_mode is None or params.get("pid") not in self.rows:
                return _Result([])
            return _Result([{"mode": self.lease_mode, "group_id": None}])
        if sql.startswith("INSERT INTO queue_leases"):
            # A1 r2: mode/group/ttl are recorded too. queue_ready now writes
            # TWICE -- the pre-issuance reacquire of the group-less polling
            # lease, then the in-game fence on the series it just created --
            # and a record of player ids alone cannot tell those apart, which
            # is exactly the distinction the fix turns on.
            self.leases_written.append((
                params.get("pid"), params.get("mode"),
                params.get("gid"), params.get("ttl")))
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
    stale = _now() - timedelta(seconds=main.REGION_PINGS_ROOM_MAX_AGE_S + 5)
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


def test_queue_ready_refuses_to_issue_a_room_on_a_lapsed_lease(issuance):
    """A1: queue_ready REQUIRES the pair's exact live ("ranked", None)
    predecessor. An absent lease does not mean "both seats are free" -- it
    means the commitment lapsed and this pair is already gone, so issuing a
    room would resurrect it and make it cross-mode eligible again. The caller
    is returned to searching instead, and NO room is issued."""
    at = _now() - timedelta(seconds=20)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, at, at), ME_STEAM)
    session.lease_mode = None
    resp = _ready(session)
    assert resp["status"] == "dissolved", resp
    assert issuance == [], "a room was issued on a lapsed commitment"
    assert session.leases_written == [], "a lapsed pair was re-leased"


def test_queue_ready_reacquires_the_lease_on_the_room_it_issues(issuance):
    """The renew half of the same requirement: the committed room carries a
    lease measured from ISSUANCE, not whatever remained of the poll's five
    minutes.

    A1 r2 makes that TWO writes, and the pair is the point:
      * the pre-issuance reacquire of the group-less polling lease -- the
        commitment to "matched in ranked", which has no id until a room
        exists;
      * the fence on the live game, scoped to the series and carrying
        LEASE_TTL_INGAME. Before r2 a 1v1 in progress held NO in-game lease at
        all: every ranked lease in the file was group-less and five minutes
        long, so the pair's cover lapsed minutes INTO the match and both seats
        looked free to every other mode's formation."""
    at = _now() - timedelta(seconds=20)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, at, at), ME_STEAM)
    assert _ready(session)["status"] == "both_ready"

    polling = [w for w in session.leases_written if w[2] is None]
    ingame = [w for w in session.leases_written if w[2] is not None]
    assert sorted(str(w[0]) for w in polling) == sorted(
        [str(ME), str(PARTNER)]), polling
    assert sorted(str(w[0]) for w in ingame) == sorted(
        [str(ME), str(PARTNER)]), ingame
    assert {w[1] for w in session.leases_written} == {"ranked"}, session.leases_written
    assert {w[3] for w in polling} == {main.LEASE_TTL_POLLING}, polling
    assert {w[3] for w in ingame} == {main.LEASE_TTL_INGAME}, ingame
    assert len({w[2] for w in ingame}) == 1, (
        "both seats must be fenced onto the SAME series")


def test_queue_ready_control_without_maps_or_with_stale_maps_takes_the_ladder(issuance):
    session = FakeIssuanceSession(_pair(None, None, None, None), ME_STEAM)
    assert _ready(session)["photon_region"] == "us"
    stale = _now() - timedelta(seconds=main.REGION_PINGS_ROOM_MAX_AGE_S + 5)
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
    stale = _now() - timedelta(seconds=main.REGION_PINGS_ROOM_MAX_AGE_S + 1)
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


def test_the_header_stamp_is_what_the_issuance_window_judges(issuance, monkeypatch):
    """The stamp half: the UPDATE binds the row's stamp as now - age, so a valid
    header whose age is past the window leaves A stale although the STORED stamp
    was fresh — issuance agrees with what the row now holds, not with the snapshot.
    The room window equals the validator's bound since 2026-11-05, so no VALID
    header can lie past it; the window is narrowed here to 180 s (its value
    until then) so that a valid header still falls on the far side of it."""
    monkeypatch.setattr(main, "REGION_PINGS_ROOM_MAX_AGE_S", 180)
    fresh = _now() - timedelta(seconds=10)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, fresh, fresh), ME_STEAM)
    age = main.REGION_PINGS_ROOM_MAX_AGE_S + 1
    assert _poll(session, {"x-region-pings": f"us=100,eu=30;age={age}"}).photon_region == "us"
    assert [s[3] for s in issuance] == ["us"]


@pytest.mark.parametrize("headers", [{}, {"x-region-pings": "us=100,eu=30;age=-1"}, {"x-region-pings": "garbage"}])
def test_control_a_stale_snapshot_stays_stale_without_a_valid_header(issuance, headers):
    """Negative control (#391): an absent or refused header overlays nothing —
    the stale stored map stays stale and the ladder answers."""
    stale = _now() - timedelta(seconds=main.REGION_PINGS_ROOM_MAX_AGE_S + 1)
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
    age = main.REGION_PINGS_ROOM_MAX_AGE_S - 1
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
