"""The 1v1 room region must not depend on which seat's request issued the room.

`_pick_room_region(my_region, my_home, opp_region, opp_home)` is called with
the REQUESTING player first at both issuance sites, so an order-dependent
expression put the room wherever the client that polled first happened to be —
and polling first correlates with having the better connection to this API, so
the seat already ahead got the region too.

Rule 1 (both home regions agree) was already symmetric and is unchanged; this
pins it as well, because it is the rule that actually serves same-region pairs.

What this does NOT claim: that the chosen region is the best one for the pair.
For a genuinely cross-region pair nothing here can know that — steering on the
stored home_region was refused for good reasons (it is a persistent,
untimestamped best-region cache, so a player who relocated would be steered by
where they used to be), and the measurement that would settle it does not exist
yet. A disagreement resolves to a fixed order: a coin flip made stable.

Pure functions, no DB, no fixtures.
"""

import itertools

import pytest

import main


# "" and None are the two shapes an absent signal arrives in; "zz" is a
# well-formed token this server has never heard of (it must still be usable —
# the client reported being connected to it); the rest are malformed.
SIGNALS = ("", None, "us", "eu", "usw", "zz", "  EU  ", "not-a-region", "x", "toolongregion")


def pick(my_region, my_home, opp_region, opp_home):
    return main._pick_room_region(my_region, my_home, opp_region, opp_home, room_name="t")


@pytest.mark.parametrize("mr,orr", list(itertools.product(SIGNALS, repeat=2)))
def test_swapping_the_two_seats_cannot_change_the_room(mr, orr):
    """The property the finding is about, over every pair of live snapshots
    against every pair of home regions."""
    for mh, oh in itertools.product(SIGNALS, repeat=2):
        assert pick(mr, mh, orr, oh) == pick(orr, oh, mr, mh)


def test_agreeing_home_regions_still_win_over_both_live_snapshots():
    """Rule 1, unchanged: a same-region pair lands home whatever either client
    was connected to when it queued."""
    assert pick("us", "eu", "usw", "eu") == "eu"
    assert pick("", "jp", "", "jp") == "jp"
    assert pick("us", "  EU  ", "usw", "eu") == "eu", "the home comparison is case/space insensitive"


def test_one_live_snapshot_is_used_whichever_seat_it_came_from():
    assert pick("eu", "", "", "") == "eu"
    assert pick("", "", "eu", "") == "eu"


def test_two_disagreeing_snapshots_resolve_the_same_way_both_ways_round():
    assert pick("us", "", "eu", "") == pick("eu", "", "us", "") == "eu"


def test_live_snapshots_are_preferred_to_home_caches():
    """Unchanged from the shipped rule: a live snapshot is where a client
    actually was; a home cache is where it used to ping best."""
    assert pick("us", "jp", "", "kr") == "us"


def test_a_malformed_signal_is_absent_rather_than_pinned():
    """It would be handed back to both clients to connect to."""
    for bad in ("not-a-region", "x", "toolongregion", "  ", "US/EAST"):
        assert pick(bad, "", "", "") == "us", f"{bad!r} reached the room"
        assert pick("eu", "", bad, "") == "eu"


def test_an_unrecognised_but_well_formed_region_is_still_usable():
    """Regions outside the set ROUNDS' own selector offers — hk and uae are in
    this project's match history — are reachable, and dropping them would move
    a real pair to a worse room than the one they were already using."""
    assert pick("hk", "", "hk", "") == "hk"
    assert pick("", "uae", "", "uae") == "uae"


def test_the_answer_is_always_a_usable_token():
    for mr, mh, orr, oh in itertools.product(SIGNALS, repeat=4):
        got = pick(mr, mh, orr, oh)
        assert main._REGION_TOKEN_RE.match(got), got


def test_the_answer_is_always_one_of_the_inputs_or_the_documented_default():
    for mr, mh, orr, oh in itertools.product(SIGNALS, repeat=4):
        got = pick(mr, mh, orr, oh)
        offered = {main._region_token(v) for v in (mr, mh, orr, oh)} - {""}
        assert got in offered or got == "us", (got, offered)
