"""The ranked room's region must not be decided by which client polled first.

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

The tie-break asks which region this process has evidence two players have
actually played in. That is corroboration, not an allowlist — a static list was
refused with a good argument (`hk` and `uae` are in this project's own match
history and the game's own selector does not offer them) — and it only ever
breaks a tie between two candidates already in play, so it cannot reject a
region outright.

WHERE THAT EVIDENCE COMES FROM has been rewritten twice, and the current answer
is the only one that is not a client's word for it. First it was the join-time
CloudRegion snapshot; then the match report's `region` field. Neither is signed
— the match HMAC covers seven fields and the region is not among them — so
establishing a session proves who is speaking and nothing about the region
named in the sentence. The token is now the region THIS SERVER issued for the
room, read back from `issued_room_regions` by the room id, which the HMAC does
cover. The evidence is therefore "the server sent two players here and a game
from that room was reported and accepted", and it is published only once that
report has committed.

AND WHEN CORROBORATION CANNOT DECIDE, `min(a, b)` does — the alphabet, chosen
because a pair has no comparable latency measurement and a stable coin flip is
better than one that depends on which seat asked. That is written down as a
coin flip rather than a preference, and a test below pins that it is not
described as anything else.

What none of this claims: that the chosen region is the BEST one for a
cross-region pair. Steering on a stored home region was refused because an
untimestamped best-region cache steers a player who relocated by where they
used to be, and the measurement that would settle it does not exist yet.
"""

import inspect
import itertools
import io
import re
import tokenize
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

    src = inspect.getsource(main.submit_match)
    assert "_session_was_verified(request)" in src
    assert src.index("_session_was_verified(request)") < src.index("_note_region_seen(")
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


def test_the_region_a_sighting_carries_is_the_one_this_server_issued():
    """SOURCE SHAPE, not execution: this asserts WHERE the token comes from.
    The behaviour of the map itself is executed by every other test here.

    r13 HIGH. The evidence was the join-time CloudRegion snapshot, then the
    match report's `region` field. Neither is signed -- the match HMAC covers
    seven fields and the region is not one of them -- so establishing a session
    proves who is speaking and nothing about the region named in the sentence,
    and two accounts one person holds could carry a region nobody can connect
    to over the two-player bar and win a tie against an honest one.

    The token is now read back from issued_room_regions, keyed by the room
    name DERIVED from the room id, which the HMAC does cover.

    This test used to assert the literal `"room": str(report.photon_room_id)`,
    and that literal was the defect r14 found: the report id is the room name
    plus a per-game suffix, so keying the lookup on it matched nothing, ever.
    A test that asserts the spelling of the line it is watching cannot fail
    while that line is wrong. What is pinned now is the property the paragraph
    above actually claims -- the key is derived from a field the signature
    covers, and no unsigned field reaches it."""
    src = inspect.getsource(main.submit_match)

    assert "_note_region_seen(report.region" not in src, (
        "the unsigned client field is back in the map"
    )
    assert "SELECT region FROM issued_room_regions" in src
    assert "_issued_room_candidates(report.photon_room_id)" in src, (
        "the lookup key must still be derived from the room id the HMAC covers"
    )
    assert "report.region" not in src[src.index("SELECT region FROM issued_room_regions") - 400:
                                      src.index("SELECT region FROM issued_room_regions") + 900], (
        "the unsigned region field must not appear anywhere in the lookup"
    )
    assert "_note_region_seen(*_region_sighting)" in src

    # The flagged path commits and returns BEFORE the lookup, so an invalidated
    # match is not evidence of anything.
    assert src.index('if ac["invalidate"]:') < src.index("issued_room_regions")

    # The REPORTER only. Recording the opponent as well would let one account
    # name an opponent and supply both halves of "two distinct players".
    assert "report.reported_by_steam_id)" in src
    assert "_region_sighting = (_issued_region, p2.steam_id)" not in src
    assert "_region_sighting = (_issued_region, p1.steam_id)" not in src

    # The old feeds are gone, not merely supplemented.
    assert "_note_region_seen(" not in inspect.getsource(main.queue_join)
    assert MAIN_PY.read_text(encoding="utf-8").count("_note_region_seen(") == 2, (
        "one definition and one caller"
    )


def test_the_sighting_is_published_only_after_the_match_has_committed():
    """r13 MEDIUM. The map is process memory and the match is not committed
    where the region is read. A rollback after the sighting -- the duplicate
    branch takes exactly that path -- would leave evidence for a game that was
    never recorded, and two of those corroborate a region on the strength of
    two failures.

    So the lookup happens inside the transaction and the PUBLICATION happens
    after it: read, hold, commit, then note."""
    src = inspect.getsource(main.submit_match)
    read_at = src.index("SELECT region FROM issued_room_regions")
    commit_at = src.index("await db.commit()", read_at)
    publish_at = src.index("_note_region_seen(*_region_sighting)")
    assert read_at < commit_at < publish_at, (
        "the sighting is published before the match it witnesses is committed"
    )
    # ...and the rollback branch returns before the publication
    duplicate_return = src.index('series_status="duplicate"')
    assert commit_at < duplicate_return < publish_at


def test_a_room_this_server_never_issued_contributes_nothing():
    """A private or tournament room has no binding, so there is no region to
    read and no sighting to make. Fail-closed: absence of a binding is not an
    invitation to fall back on what the client said."""
    src = inspect.getsource(main.submit_match)
    guard = src[src.index("_region_sighting = None"):src.index("_note_region_seen(*")]
    assert "if _issued_region:" in guard, (
        "the sighting must be conditional on the binding existing"
    )
    assert "report.region" not in guard, "no fallback to the client's field"


def test_the_issued_binding_is_written_where_the_room_is_issued():
    """One helper stamps the room on both queue rows, and both issuance sites
    go through it -- so the binding is written exactly when two players are
    told where to play, and only when the stamp actually took."""
    stamp = inspect.getsource(main._queue_stamp_room_reciprocal)
    assert "INSERT INTO issued_room_regions" in stamp
    assert "ON CONFLICT (room_name) DO NOTHING" in stamp, (
        "a reused room name must keep the issuance that sent players somewhere"
    )
    # written only on the proven-reciprocal path
    assert stamp.index("if updated != {my_pid, opp_pid}:") < stamp.index(
        "INSERT INTO issued_room_regions")
    src = MAIN_PY.read_text(encoding="utf-8")
    assert src.count("_queue_stamp_room_reciprocal(db,") == 2, (
        "both issuance sites must go through the helper that writes the binding"
    )
    assert src.count("INSERT INTO issued_room_regions") == 1


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


def _fill_with_corroborated(count, pair=("76561198000000101", "76561198000000102")):
    """`count` tokens, each corroborated by the same two reporters. Returns them
    oldest-first."""
    tokens = []
    for i in range(count):
        token = chr(97 + i // 26) + chr(97 + i % 26) + "q"
        _corroborate(token, pair)
        tokens.append(token)
    return tokens


def test_a_full_map_of_corroborated_tokens_still_admits_a_new_region():
    """r12 MEDIUM. Ranking evictions by evidence has a failure of its own, and
    it is the one that was reachable: a token nobody has corroborated YET is by
    definition the least-corroborated entry in the map, so with the map full of
    corroborated tokens every first sighting of a genuine new region was
    evicted in the very call that made it. The second player to connect there
    found nothing to join, and the region could never corroborate — not slowly,
    not eventually, never.

    A region can only corroborate if its first sighting is allowed to wait, so
    the map reserves slots that no corroborated token may take."""
    filled = _fill_with_corroborated(main._REGION_SEEN_MAX_TOKENS)
    assert len(main._REGION_SEEN) == main._REGION_SEEN_MAX_TOKENS
    assert all(main._region_corroborated(t) for t in filled)

    main._note_region_seen("hk", "76561198000000201")
    assert "hk" in main._REGION_SEEN, (
        "the first honest sighting was evicted by the call that made it"
    )
    assert len(main._REGION_SEEN) == main._REGION_SEEN_MAX_TOKENS, (
        "the map still has to be bounded"
    )

    # ...and the second genuine reporter can now find it there
    main._note_region_seen("hk", "76561198000000202")
    assert main._region_corroborated("hk")


def test_the_nursery_is_bounded_and_gives_up_its_own_oldest():
    """The reserved slots are a floor, not an exemption. New tokens compete
    with other new tokens — recency inside the pool — and the corroborated pool
    is untouched while it is inside its cap."""
    cap = main._REGION_SEEN_CORROBORATED_CAP
    room = main._REGION_SEEN_MAX_TOKENS - cap
    assert 0 < cap < main._REGION_SEEN_MAX_TOKENS
    settled = _fill_with_corroborated(cap)

    newcomers = []
    for i in range(room + 5):
        token = "n" + chr(97 + i // 26) + chr(97 + i % 26)
        main._note_region_seen(token, "76561198000000301")
        newcomers.append(token)

    assert len(main._REGION_SEEN) == main._REGION_SEEN_MAX_TOKENS
    assert all(t in main._REGION_SEEN for t in settled), (
        "a corroborated token was evicted while its pool was inside its cap"
    )
    assert newcomers[-1] in main._REGION_SEEN, "the newest sighting was evicted"
    assert newcomers[0] not in main._REGION_SEEN, "the oldest newcomer survived"


def test_a_corroborated_pool_over_its_cap_gives_up_its_oldest():
    """The other direction, so the floor is not one-way: past the cap, the
    corroborated pool is the one that pays, oldest first."""
    settled = _fill_with_corroborated(main._REGION_SEEN_MAX_TOKENS)
    oldest = settled[0]
    _age(oldest, 3600.0)
    main._note_region_seen("hk", "76561198000000201")
    assert oldest not in main._REGION_SEEN, (
        "the least recently seen corroborated token survived a map over its cap"
    )
    assert "hk" in main._REGION_SEEN


def test_a_sighting_is_taken_on_every_accepted_report_not_once_per_reporter():
    """r12 MEDIUM, answered by the source rather than by a new mechanism. The
    map used to be fed at join time, once -- so two genuine clients that joined
    before their session tokens were minted were accepted, contributed nothing,
    and were never re-noted, whatever they did afterwards.

    The source is now every accepted match report, which is a recurring event:
    an unminted session costs the reports made before its token exists and
    nothing after. Pinned two ways -- the stamp refreshes on re-report, and the
    lookup is not behind any once-per-anything condition."""
    reporter = "76561198000000401"
    main._note_region_seen("eu", reporter)
    _age("eu", main._REGION_SEEN_TTL_SECONDS - 5)
    stale = main._REGION_SEEN["eu"][reporter]
    main._note_region_seen("eu", reporter)
    assert main._REGION_SEEN["eu"][reporter] > stale, (
        "a re-report did not refresh the reporter's own sighting"
    )

    src = MAIN_PY.read_text(encoding="utf-8")
    call = src.index("SELECT region FROM issued_room_regions")
    guard = src[src.rindex("if ", 0, call):call]
    assert "_session_was_verified(request)" in guard, (
        "the sighting must still require an established session"
    )
    assert "once" not in guard and "first" not in guard, (
        "the sighting is per accepted report; a one-shot guard would restore "
        "the hole this replaced"
    )



# ---------------------------------------------------------------------------
# The lookup has to match something. Review r14 HIGH: it never did.
#
# Issuance stores the Photon room name; the client reports that name with a
# per-game suffix appended, and the two were compared for equality. Every test
# above this line passed throughout, because all of them exercise the picker
# and the map directly -- none of them asked whether a real report ever reaches
# the map at all. These do, and they take the client's format from the client's
# own source rather than restating it here, because a restated contract drifts
# and a test that builds its input from the wrong shape proves nothing.
# ---------------------------------------------------------------------------

WATCHER_CS = Path(__file__).resolve().parents[2] / "plugin" / "GameStateWatcher.cs"


def test_the_client_still_builds_report_ids_the_way_this_file_assumes():
    """If the client's format changes, the derivation below is wrong and these
    tests must fail rather than keep asserting against a stale shape."""
    src = WATCHER_CS.read_text(encoding="utf-8", errors="replace")
    assert '_r{reportRoundTotal}' in src, (
        "the 1v1 report id no longer ends in the _r<n> suffix this derivation strips"
    )
    assert '{matchStartTime:HHmmss}_r{FfaMode.GameNumber}' in src, (
        "the FFA report id no longer has the _<HHmmss>_r<n> shape this derivation strips"
    )


def test_a_real_report_id_resolves_to_the_room_the_server_issued():
    """The finding itself. `ranked_<12hex>` is what issuance stores
    (main.py builds it with uuid4().hex[:12]); the client reports that name
    plus `_<HHmmss>_r<n>`. Equality between the two is never true."""
    issued = "ranked_a1b2c3d4e5f6"
    reported = f"{issued}_143052_r3"
    assert reported != issued, "the premise of this test is that they differ"
    cands = main._issued_room_candidates(reported)
    assert issued in cands, (
        f"the issued room name is not among the lookup candidates for {reported!r}; "
        "the corroboration map can never receive a sighting"
    )
    assert reported in cands, "the id as sent must remain a candidate too"


def test_room_names_containing_underscores_survive_intact():
    """Every name this matters for has underscores in it -- `ranked_<hex>` and
    the tournament rooms -- so a derivation that split on the first one would
    hand the lookup a prefix that was never issued to anybody."""
    for issued in ("ranked_a1b2c3d4e5f6", "sct-4f2a_qual_r1_room", "code_ABCD"):
        cands = main._issued_room_candidates(f"{issued}_091500_r12")
        assert issued in cands, f"{issued!r} did not survive suffix removal"


def test_a_bare_room_name_is_left_alone():
    """Nothing in the client sends this today. It costs one list entry to keep
    working if anything ever does, and a derivation that MANGLED it would be
    the same class of silent miss."""
    assert main._issued_room_candidates("ranked_a1b2c3d4e5f6") == ["ranked_a1b2c3d4e5f6"]
    assert main._issued_room_candidates("") == []
    assert main._issued_room_candidates(None) == []


def test_the_lookup_requires_the_pair_the_room_was_issued_to():
    """A region recorded without the pair says only that some room got a
    region, so any accepted report naming that room fed the map. The row now
    records who the server sent, and the read requires the report's two
    players to be exactly those two."""
    src = MAIN_PY.read_text(encoding="utf-8")
    call = src.index("SELECT region FROM issued_room_regions")
    stmt = src[call:src.index("})).scalar()", call)]
    assert "player1_id IS NOT NULL" in stmt and "player2_id IS NOT NULL" in stmt, (
        "a row with no pair recorded must not corroborate anything"
    )
    assert "player1_id = :pa AND player2_id = :pb" in stmt, "pair check missing"
    assert "player1_id = :pb AND player2_id = :pa" in stmt, (
        "the pair check must be order-independent -- which of the two rows the "
        "issuance wrote first is not a fact about the game"
    )
    assert "room_name = :room_full OR room_name = :room_base" in stmt, (
        "the lookup must offer the derived room name as well as the id as sent"
    )


def test_the_issuance_records_the_pair_and_prunes():
    """Both halves of the row, written where the pair is known -- and the
    deletion migration 292 promises, on the path that does the inserting.
    A promised prune with nothing that prunes is a table that grows forever."""
    src = MAIN_PY.read_text(encoding="utf-8")
    ins = src.index("INSERT INTO issued_room_regions")
    stmt = src[ins:src.index("return True", ins)]
    assert "player1_id, player2_id" in stmt, "issuance does not record the pair"
    assert '"a": my_pid, "b": opp_pid' in stmt, "the pair bound is not the issued pair"
    # Asserted by PARTS, not as one literal. The statement is now a bounded
    # range delete and the old single-substring assertion fired ON the fix --
    # the correct response to which is to check the new shape, never to weaken
    # the assertion until it passes.
    assert "DELETE FROM issued_room_regions" in stmt, (
        "migration 292 promises rows are deleted past 30 days; nothing deletes them"
    )
    assert "issued_at <" in stmt and "30 days" in stmt, "the age bound is gone"
    assert "ORDER BY issued_at" in stmt, (
        "an unordered LIMIT deletes an arbitrary 200 rows, so a backlog need "
        "never drain -- the oldest are what must go first"
    )
    assert "SKIP LOCKED" in stmt
    limit = re.search(r"LIMIT (\d+)", stmt)
    assert limit, "the sweep is not bounded in rows"
    assert 1 <= int(limit.group(1)) <= 1000, (
        f"LIMIT {limit.group(1)} is not a bound this transaction can afford; "
        "the stamp UPDATE above holds both queue rows' locks until commit"
    )
    assert "begin_nested" in stmt, (
        "the sweep is not savepoint-isolated, so a statement error aborts the "
        "room-issuance transaction it runs inside"
    )


def _main_code():
    """main.py with COMMENT tokens blanked at preserved offsets.

    Prose is not code: a phrase in a comment satisfied an occurrence count and
    a `re.findall` here matched four "sweeps" for link_codes, three of which
    were sentences. STRING tokens are KEPT on purpose - the SQL being asserted
    about lives in them.
    """
    src = MAIN_PY.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type != tokenize.COMMENT:
            continue
        (srow, scol), (erow, ecol) = tok.start, tok.end
        assert srow == erow, "a comment token spanning lines"
        ln = lines[srow - 1]
        lines[srow - 1] = ln[:scol] + " " * (ecol - scol) + ln[ecol:]
    return "".join(lines)


# Each retention sweep, keyed by the age predicate that DISTINGUISHES it from
# the table's ordinary deletes. link_codes in particular is deleted in three
# other places for reasons that have nothing to do with retention, so "a DELETE
# naming the table" is not the thing being counted here.
_RETENTION_SWEEPS = (
    ("issued_room_regions", "issued_at <"),
    ("link_codes", "expires_at < now()"),
    ("chat_mod_actions", "acked_at <"),
)


def test_every_in_request_retention_sweep_is_bounded():
    """r14 LOW 6 is one line; the defect is a class (#432/#330).

    An age-predicated maintenance DELETE executed inside a request transaction
    is unbounded in rows and therefore unbounded in lock time, and this file
    had three of them. They are swept together and each is asserted here, so a
    fourth added later has a place it must appear.

    The isolation deliberately DIFFERS between them, because the callers can
    tolerate opposite things -- see each site's comment. What does not differ
    is the bound.
    """
    src = _main_code()
    for table, age in _RETENTION_SWEEPS:
        found = []
        at = src.find("DELETE FROM " + table)
        while at != -1:
            window = src[at:at + 500]
            if age in window:
                found.append(window)
            at = src.find("DELETE FROM " + table, at + 1)
        assert found, f"{table}: no age-predicated retention sweep found"
        assert len(found) == 1, f"{table}: {len(found)} retention sweeps; expected one"
        stmt = found[0]
        assert "ctid IN (" in stmt, f"{table}: the bound is not applied to the delete"
        assert "ORDER BY" in stmt, f"{table}: an unordered LIMIT need never drain a backlog"
        assert "SKIP LOCKED" in stmt, f"{table}: sweep can queue behind another request"
        limit = re.search(r"LIMIT (\d+)", stmt)
        assert limit, f"{table}: sweep is not bounded in rows"
        assert 1 <= int(limit.group(1)) <= 1000, f"{table}: LIMIT {limit.group(1)}"


def test_the_retention_sweep_gate_can_fail():
    """The negative control: an unbounded sweep of the shape this replaces must
    not satisfy the gate above."""
    stmt = "DELETE FROM issued_room_regions WHERE issued_at < NOW() - INTERVAL '30 days'"
    assert "ctid IN (" not in stmt and "SKIP LOCKED" not in stmt
    assert re.search(r"LIMIT (\d+)", stmt) is None


def test_the_expired_code_lookup_does_not_depend_on_the_sweep():
    """The link_codes sweep is throttled now, so it does NOT run on most calls
    -- which is only safe because the lookup below it re-checks expiry itself.

    That predicate was already there as belt-and-braces, with a comment saying
    the ordering must not become load-bearing. Throttling the sweep is exactly
    the change that comment warned about, so the predicate stops being
    belt-and-braces and becomes the thing doing the work. It is asserted here
    rather than trusted.
    """
    src = MAIN_PY.read_text(encoding="utf-8")
    at = src.index("async def link_discord")
    body = src[at:src.index("\n@app.", at + 10)]
    assert "LinkCode.expires_at > func.now()" in body, (
        "the expired-code sweep is throttled, so nothing but this predicate "
        "stops an expired code being accepted"
    )
    # ...and the sweep must NOT be savepoint-isolated here: a rollback would
    # leave the expired rows in place, which is the failure, not the recovery.
    sweep = body[body.index("DELETE FROM link_codes"):]
    assert "begin_nested" not in body[:body.index("DELETE FROM link_codes")], (
        "isolating this sweep would hide a failure that leaves expired codes live"
    )
    assert "_link_codes_last_prune" in body, "the sweep is not throttled"


def test_the_comment_no_longer_claims_no_client_supplied_the_region():
    """`_pick_room_region` chooses from the two seats' own region and
    home_region tokens. The DECISION is the server's and that is what the row
    records -- but the file used to say the region was not client-supplied at
    all, which is a stronger claim than the code makes and the kind that gets
    trusted by the next change (r14)."""
    src = MAIN_PY.read_text(encoding="utf-8")
    assert "IT IS NOT A CLIENT-SUPPLIED REGION AT ALL" not in src, (
        "the retired absolute claim is back"
    )
    assert "IT IS NOT READ FROM THE REPORT" in src, "the true, narrower claim is missing"
    assert "the candidates come" in src and "from clients" in src, (
        "the correction must say where the candidates actually come from"
    )


def test_the_deploy_block_puts_292_before_the_api():
    """The report path SELECTs from `issued_room_regions`. An API deployed
    ahead of the table fails every match report with undefined_table."""
    changelog = (Path(__file__).resolve().parents[2] / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    block = changelog[changelog.index("**Schema changes:** migration **292**"):][:1200]
    assert "BEFORE the API deploy" in block, "292 is not ordered before the API"
    for seed in ("288", "289", "290", "291"):
        assert seed in block, f"migration {seed} dropped from the deploy block"
