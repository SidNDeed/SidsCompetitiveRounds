"""The ranked room's region must not be decided by which client polled first,
and the tie that decides it must not be decided by the alphabet.

`_pick_room_region` takes the REQUESTING player's signals first and both
issuance sites pass them that way, so the old chain
`my_region or opp_region or my_home or opp_home` put the room wherever the
client whose poll triggered issuance happened to be. Polling first correlates
with having the better connection to this API, so the seat that was already
ahead got the region as well.

Review r9 killed the first repair with a HIGH, and the reason is the more
interesting half. The picker validates a region by SHAPE — anything that looks
like a region code is accepted — and nothing checks the choice against the
regions Photon actually offers. Resolving a disagreement with `min()` therefore
lands on a retired region EVERY time when a stale cache names one, where the
old order-dependent chain landed there about half the time: strictly worse.

The tie-break now asks which region this process has actually seen a client
connected to. That is corroboration, not an allowlist — a static list was
refused with a good argument (`hk` and `uae` are in this project's own match
history and the game's own selector does not offer them) — and it is built from
the live region token every queueing client reports. It only ever breaks a tie
between two candidates already in play, so it cannot reject a region outright.

What none of this claims: that the chosen region is the BEST one for a
cross-region pair. Steering on a stored home region was refused because an
untimestamped best-region cache steers a player who relocated by where they
used to be, and the measurement that would settle it does not exist yet.
"""

import inspect
import itertools
from pathlib import Path

import pytest

import main


MAIN_PY = Path(__file__).resolve().parents[1] / "api" / "main.py"

TOKENS = ["", "us", "eu", "asia"]


@pytest.fixture(autouse=True)
def _empty_map():
    """The corroboration map is process state. Every test starts from empty —
    which is also the state a freshly deployed api is in."""
    saved = dict(main._REGION_SEEN)
    main._REGION_SEEN.clear()
    yield
    main._REGION_SEEN.clear()
    main._REGION_SEEN.update(saved)


def _corroborate(token, players=("76561198000000001", "76561198000000002")):
    for sid in players:
        main._note_region_seen(token, sid)


# ── symmetry ─────────────────────────────────────────────────────────────────

def test_the_pick_does_not_depend_on_which_seat_asked():
    """The property, over every combination of the four signals. The caller's
    argument order is an accident of which poll arrived first."""
    for mr, mh, orr, oh in itertools.product(TOKENS, repeat=4):
        mine = main._pick_room_region(mr, mh, orr, oh, "r")
        theirs = main._pick_room_region(orr, oh, mr, mh, "r")
        assert mine == theirs, f"({mr},{mh}) vs ({orr},{oh}) -> {mine} / {theirs}"


def test_symmetry_holds_when_corroboration_is_in_play():
    """The tie-break reads process state, so it is the rung most able to
    reintroduce an order dependence."""
    _corroborate("eu")
    for mr, mh, orr, oh in itertools.product(TOKENS, repeat=4):
        assert main._pick_room_region(mr, mh, orr, oh, "r") == \
               main._pick_room_region(orr, oh, mr, mh, "r")


def test_two_agreeing_home_regions_still_win_outright():
    """Rule 1, unchanged and the thing that actually serves same-region pairs:
    it beats both live snapshots, which are wrong after casual region churn and
    empty when the client was not connected at join."""
    assert main._pick_room_region("us", "asia", "us", "asia", "r") == "asia"


def test_a_signal_that_is_not_a_region_token_counts_as_absent():
    """It would be handed to both clients to connect to, and there is no
    recovery from a room neither of them can reach."""
    for junk in ("  ", "US-EAST-1", "a", "toolongregion", "eu1!", None):
        assert main._pick_room_region(junk, "", junk, "", "r") == "us"
    assert main._pick_room_region("EU ", "", "", "", "r") == "eu", "case and space are normalised"


def test_no_signal_at_all_is_the_us_default():
    assert main._pick_room_region("", "", "", "", "r") == "us"


def test_one_signal_is_used_whichever_seat_it_came_from():
    assert main._pick_room_region("asia", "", "", "", "r") == "asia"
    assert main._pick_room_region("", "", "asia", "", "r") == "asia"
    assert main._pick_room_region("", "asia", "", "", "r") == "asia"
    assert main._pick_room_region("", "", "", "asia", "r") == "asia"


def test_a_live_snapshot_outranks_a_cached_home_region():
    assert main._pick_room_region("us", "asia", "", "eu", "r") == "us"


# ── corroboration ────────────────────────────────────────────────────────────

def test_a_disagreement_goes_to_the_region_that_has_been_seen_live():
    """The r9 HIGH, answered. `min()` would say "asia" both times; a stale
    cache naming a region nobody can reach would win every single pairing."""
    _corroborate("us")
    assert main._pick_room_region("", "asia", "", "us", "r") == "us"
    assert main._pick_room_region("", "us", "", "asia", "r") == "us"


def test_with_neither_side_corroborated_the_tie_is_still_stable():
    """An empty map is a freshly deployed api, and it must behave exactly as
    it did before corroboration existed rather than inventing an answer."""
    assert main._pick_room_region("", "asia", "", "us", "r") == "asia"
    assert main._pick_room_region("", "us", "", "asia", "r") == "asia"


def test_with_both_sides_corroborated_the_tie_is_still_stable():
    _corroborate("us")
    _corroborate("asia")
    assert main._pick_room_region("", "asia", "", "us", "r") == "asia"


def test_corroboration_never_rejects_a_region_it_only_breaks_a_tie():
    """The bound on what this mechanism can do. A region nobody has been seen
    in is still used when it is the only signal — otherwise a cold process
    would move every pair to the default."""
    _corroborate("us")
    assert main._pick_room_region("", "asia", "", "", "r") == "asia"
    assert main._pick_room_region("asia", "", "", "", "r") == "asia"
    assert main._pick_room_region("asia", "", "asia", "", "r") == "asia"


def test_one_client_cannot_corroborate_a_region_of_its_own_invention():
    """The live token is client-supplied. A sighting counts only once it has
    come from more than one distinct player."""
    main._note_region_seen("zz", "76561198000000001")
    main._note_region_seen("zz", "76561198000000001")
    assert not main._region_corroborated("zz")
    assert main._pick_room_region("", "asia", "", "zz", "r") == "asia", (
        "one player's word moved the tie-break"
    )
    main._note_region_seen("zz", "76561198000000002")
    assert main._region_corroborated("zz")


def test_a_home_region_cannot_corroborate_itself():
    """The map is fed from the live snapshot only. If a cached home value
    counted as a sighting, two stale caches naming a retired region would
    corroborate each other — which is exactly the case this exists for."""
    main._pick_room_region("", "asia", "", "asia", "r")
    assert main._REGION_SEEN == {}, "the picker recorded a sighting"
    picker = inspect.getsource(main._pick_room_region)
    assert "_note_region_seen" not in picker, (
        "issuance must not refresh a token's timestamp: the region the picker "
        "itself chose would then look recent forever and could never age out"
    )


def test_a_sighting_ages_out():
    _corroborate("us")
    assert main._region_corroborated("us")
    seen_at, ids = main._REGION_SEEN["us"]
    main._REGION_SEEN["us"] = (seen_at - main._REGION_SEEN_TTL_SECONDS - 1, ids)
    assert not main._region_corroborated("us")
    # ...and a fresh sighting starts the player count over, so a region kept
    # alive by one straggler does not inherit an old quorum.
    main._note_region_seen("us", "76561198000000009")
    assert not main._region_corroborated("us")


def test_the_map_is_bounded():
    for i in range(main._REGION_SEEN_MAX_TOKENS + 20):
        token = "r" + format(i, "03d")[:4]
        main._note_region_seen(token[:5], "76561198000000001")
    assert len(main._REGION_SEEN) <= main._REGION_SEEN_MAX_TOKENS


def test_only_well_formed_tokens_enter_the_map():
    for junk in ("", "  ", "US-EAST-1", "a", "toolongregion", None):
        main._note_region_seen(junk, "76561198000000001")
    assert main._REGION_SEEN == {}


def test_the_queue_join_is_what_feeds_the_map():
    """SOURCE SHAPE, not execution: this asserts the call is written at the
    site that receives a live region, not that a join was run. The behaviour of
    the map itself is executed by every other test in this file."""
    src = inspect.getsource(main.queue_join)
    assert "_note_region_seen(req.region, req.steam_id)" in src
    # and nowhere else, so there is exactly one feed to reason about
    assert MAIN_PY.read_text(encoding="utf-8").count("_note_region_seen(") == 2, (
        "one definition and one caller"
    )


def test_the_log_line_says_whether_the_choice_was_corroborated():
    """"Both cached regions disagree and neither has been seen live" is the
    case that strands a pair behind a series that already exists. It is
    invisible unless the line says so."""
    picker = inspect.getsource(main._pick_room_region)
    assert "seen=" in picker
    assert "_region_corroborated(chosen)" in picker


def test_the_monotonic_clock_is_what_ages_a_sighting():
    """Wall-clock would let an NTP step expire or resurrect the whole map."""
    src = inspect.getsource(main._note_region_seen) + inspect.getsource(main._region_corroborated)
    assert "time.monotonic()" in src
    assert "utcnow" not in src and "datetime" not in src
