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


def _age(token, seconds, only=None):
    """Push a token's reporters back in time. `only` ages one of them, which is
    how the per-reporter clock is separated from a token-wide one."""
    ids = main._REGION_SEEN[token]
    for rid in list(ids):
        if only is None or rid == only:
            ids[rid] = ids[rid] - seconds


def test_a_sighting_ages_out():
    _corroborate("us")
    assert main._region_corroborated("us")
    _age("us", main._REGION_SEEN_TTL_SECONDS + 1)
    assert not main._region_corroborated("us")
    # ...and a fresh sighting starts the player count over, so a region kept
    # alive by one straggler does not inherit an old quorum.
    main._note_region_seen("us", "76561198000000009")
    assert not main._region_corroborated("us")


def test_one_reporter_cannot_keep_anothers_stale_sighting_alive():
    """r11 HIGH. With one last-seen stamp per TOKEN, the reporter who queues
    from a region every day refreshes it, and the whole entry — including a
    second player's year-old sighting — stays inside the TTL forever. The map
    would then answer "two players recently" on the strength of one. Each
    reporter's sighting has to expire on its own schedule."""
    a, b = "76561198000000001", "76561198000000002"
    main._note_region_seen("eu", a)
    main._note_region_seen("eu", b)
    assert main._region_corroborated("eu")

    # b stops playing there; a keeps queueing from it.
    _age("eu", main._REGION_SEEN_TTL_SECONDS + 1, only=b)
    main._note_region_seen("eu", a)
    assert not main._region_corroborated("eu"), (
        "one active reporter preserved another's expired sighting"
    )
    # the expired reporter is dropped rather than kept as a dead entry
    assert b not in main._REGION_SEEN["eu"]

    # and b coming back restores the quorum, since this is a freshness rule
    # rather than a one-way retirement
    main._note_region_seen("eu", b)
    assert main._region_corroborated("eu")


def test_a_tokens_reporters_are_bounded_by_dropping_the_oldest():
    """A fixed first-N would let a region's original reporters hold its quorum
    open long after they stopped playing there — the same defect as the shared
    clock, one level down."""
    cap = main._REGION_SEEN_IDS_PER_TOKEN
    for i in range(cap):
        main._note_region_seen("us", "7656119800000%04d" % i)
    _age("us", 60.0)
    newcomer = "76561198000009999"
    main._note_region_seen("us", newcomer)
    ids = main._REGION_SEEN["us"]
    assert len(ids) == cap, "the per-token reporter set is not bounded"
    assert newcomer in ids, "the newest reporter was refused rather than admitted"
    assert "76561198000000000" not in ids, "the oldest reporter was kept"


def test_the_map_is_bounded_and_evicts_the_oldest():
    """This test used to feed tokens with digits in them — "r000", "r001" — and
    the token regex is letters only, so every one was rejected, the map was
    EMPTY at the assertion, and `len({}) <= 64` was true no matter what the
    eviction did. Deleting the whole eviction block left it green. It now feeds
    tokens the regex accepts and asserts the mechanism rather than the absence
    of growth."""
    tokens = [chr(97 + i // 26) + chr(97 + i % 26)
              for i in range(main._REGION_SEEN_MAX_TOKENS + 20)]
    assert len(set(tokens)) == len(tokens)
    for token in tokens:
        assert main._region_token(token) == token, "the fixture must feed real tokens"
        main._note_region_seen(token, "76561198000000001")
    assert len(main._REGION_SEEN) == main._REGION_SEEN_MAX_TOKENS, (
        "the map neither grew past its bound nor emptied itself"
    )
    assert tokens[0] not in main._REGION_SEEN, "the oldest sighting survived eviction"
    assert tokens[-1] in main._REGION_SEEN, "the newest sighting was evicted"


def test_eviction_is_by_last_seen_not_by_first_seen():
    """A region still in use must not be evicted ahead of one nobody has
    connected to since. The two ages are set explicitly rather than left to two
    monotonic reads a microsecond apart, and exactly one eviction is forced —
    filling past the cap evicts BOTH tokens under comparison and proves
    nothing."""
    stale, in_use = "aa", "ab"
    # `in_use` is inserted FIRST and `stale` second, so insertion order and
    # last-seen order disagree — otherwise the two orderings evict the same
    # token and the test cannot tell which rule the code is following.
    main._note_region_seen(in_use, "76561198000000001")
    main._note_region_seen(stale, "76561198000000001")
    _age(stale, 3600.0)

    # Cap minus one more tokens, so the map lands exactly one over its bound.
    fillers = [chr(97 + i // 26) + chr(97 + i % 26) + "z"
               for i in range(main._REGION_SEEN_MAX_TOKENS - 1)]
    for token in fillers:
        main._note_region_seen(token, "76561198000000003")

    assert len(main._REGION_SEEN) == main._REGION_SEEN_MAX_TOKENS
    assert stale not in main._REGION_SEEN, "the least recently seen token survived"
    assert in_use in main._REGION_SEEN, "a token seen moments ago was evicted"


def test_eviction_drops_the_unevidenced_before_the_corroborated():
    """Ranking purely by age lets any stream of new tokens push out the
    corroborated ones, so a full map of regions people actually play in could be
    turned over by regions nobody has connected to. Evidence ranks above age."""
    real = "eu"
    main._note_region_seen(real, "76561198000000001")
    main._note_region_seen(real, "76561198000000002")
    assert main._region_corroborated(real)
    # ...and make it the OLDEST thing in the map, so age alone would evict it
    _age(real, 3600.0)

    fillers = [chr(97 + i // 26) + chr(97 + i % 26) + "z"
               for i in range(main._REGION_SEEN_MAX_TOKENS + 5)]
    for token in fillers:
        main._note_region_seen(token, "76561198000000003")

    assert len(main._REGION_SEEN) == main._REGION_SEEN_MAX_TOKENS
    assert real in main._REGION_SEEN, (
        "the oldest token was evicted although it was the only corroborated one"
    )


def test_both_candidates_are_judged_against_one_clock_reading():
    """Two separate time.monotonic() calls put the TTL boundary between the two
    comparisons, so at the moment both sightings expire, whichever is read first
    can still be live and win a tie it should not have been in."""
    agreed = inspect.getsource(main._region_agreed)
    assert "now = time.monotonic()" in agreed
    assert "_region_corroborated(a, now)" in agreed
    assert "_region_corroborated(b, now)" in agreed
    assert agreed.count("time.monotonic()") == 1, (
        "the pair must be decided against a single reading"
    )


def test_a_sighting_needs_a_reporter_and_an_established_session():
    """The map's claim is about PLAYERS, so it is worth exactly as much as the
    binding behind the ids. _check_steam_session soft-fails by design in several
    documented conditions — it must never take down the write path it guards —
    so "it did not raise" is a weaker fact than "it verified", and only the
    stronger one may feed corroboration."""
    # no reporter, no sighting: there is no path that records an anonymous one
    main._note_region_seen("us", None)
    main._note_region_seen("us", "")
    assert main._REGION_SEEN == {}

    join = inspect.getsource(main.queue_join)
    assert "_session_was_verified(request)" in join
    assert join.index("_session_was_verified(request)") < join.index("_note_region_seen(")
    # and the verdict starts false, so an exit that neither raises nor verifies
    # cannot read as verified
    check = inspect.getsource(main._check_steam_session)
    assert "_mark_session_verified(request, False)" in check
    assert "_mark_session_verified(request, True)" in check
    assert check.index("_mark_session_verified(request, False)") < \
        check.index("_mark_session_verified(request, True)")
    reader = inspect.getsource(main._session_was_verified)
    assert "return False" in reader, "an unreadable verdict must read as unverified"


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


def test_the_changelog_does_not_claim_the_fixed_order_is_gone():
    """r11 HIGH. The bullet said the choice no longer goes to whichever region
    came first alphabetically — and `_region_agreed` still ends in `min(a, b)`
    whenever the two candidates are equally corroborated, which includes every
    pick made on a map that is empty. The sentence has to describe the code's
    actual fallback, because a player reading it would otherwise be told a
    guarantee the server does not make."""
    changelog = (Path(__file__).parents[2] / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    start = changelog.index("The region a ranked room is created in")
    # Line wraps are a property of the file, not of the claim: flatten first so
    # a phrase split across two lines still reads as the phrase.
    bullet = " ".join(changelog[start:start + 700].split())
    assert "came first alphabetically" not in bullet, (
        "the removed-alphabetical claim is back, and min(a, b) still decides a tie"
    )
    assert "the tie falls to a fixed order" in bullet, (
        "the fallback the code actually takes has to be stated"
    )
    assert "after a server restart" in bullet, (
        "the cold-map case is when a reader is most likely to see the fallback"
    )
    # and the fallback the sentence describes is the one the code has
    agreed = inspect.getsource(main._region_agreed)
    assert "return min(a, b)" in agreed
