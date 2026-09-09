"""The client sweep's cadence and its two cross-process numbers.

`RegionPingSweep` decides WHEN a client measures its Photon regions and when it
uploads the result; `main.py` decides whether the upload is fresh enough to pick
a room with. Nothing joined those two halves, and they disagreed: the client
refreshed a map only once it was older than 300 s while the server refused
anything stamped more than 180 s before issuance, so a map aged 181-300 s at
join was guaranteed useless with no refresh path.

The second half was worse and is the reason this file exists. The trigger that
could have repaired a map mid-queue was gated on `ConnectedToMaster()`, and a
ranked player queues from the MAIN MENU, where vanilla ROUNDS is not connected
to Photon at all. The gate cost nothing the sweep uses -- the worker resolves
its own DNS and sends raw UDP, and PUN's region list is a plain field nothing
clears on disconnect -- so it was a guard inheriting the enable-condition of a
different case (#272), and it returned SILENTLY, which is why it went unseen.

The C# side has no other coverage: before this module, a grep over backend/tests
for JOIN_STALE, SEARCH_CADENCE, PollHeaderValue or RegionPingSweep returned
nothing at all. These are structure tests over the real source, so both sides of
every cross-process number are READ rather than restated (#342/#441/#444) -- a
test that hardcodes 180 passes forever after someone changes the server.
"""

import re
from pathlib import Path

import pytest

from _cs_structure import (
    and_terms,
    cs_block,
    initialiser,
    mask_code,
    strip_comments_only,
)

import main

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
SWEEP = PLUGIN / "RegionPingSweep.cs"
API = PLUGIN / "ApiClient.cs"

SWEEP_CLASS = "internal static class RegionPingSweep"
API_CLASS = "public static class ApiClient"
TICK = "public static void Tick()"
TRY_START = "static void TryStart(string why)"

# The shipped-today value the fix replaced. Named here as history, never read
# from source: if it ever comes back it must fail test 2, not be tracked by it.
PRE_FIX_JOIN_STALE_S = 300.0


def _const(name, signature=SWEEP_CLASS, source=SWEEP):
    """A `const float`/`const int` initialiser from the real source, as a float."""
    return float(initialiser(source, signature, name).rstrip("f"))


def test_the_client_refresh_threshold_fits_the_instant_match_case():
    """A map put on the JOIN body must still be inside the server's issuance
    window when the room is actually issued.

    SCOPE, and it is narrow: this defends the INSTANT-MATCH case only -- the
    join body is the last upload before issuance only when the match lands on
    the very next poll. Issuance then trails the join by at most
    READY_TIMEOUT_SECONDS plus one poll interval. A longer queue wait (out to
    QUEUE_EXPIRE_MINUTES) is served by the queue cadence and the poll header
    instead, and this inequality says nothing whatever about it.
    """
    join_stale = _const("const float JOIN_STALE_S")
    poll = float(initialiser(API, API_CLASS, "private static float queuePollInterval").rstrip("f"))
    window = float(main.REGION_PINGS_ISSUANCE_MAX_AGE_S)
    ready = float(main.READY_TIMEOUT_SECONDS)

    assert join_stale + ready + poll < window, (
        f"a join-body map can age {join_stale} + {ready} + {poll} = "
        f"{join_stale + ready + poll}s before issuance, past the server's {window}s"
    )


def test_negative_control_the_shipped_threshold_fails_that_same_inequality():
    """#391. Test 1 is only worth reading if it could have failed: the value
    this batch replaced must NOT satisfy the expression test 1 asserts."""
    poll = float(initialiser(API, API_CLASS, "private static float queuePollInterval").rstrip("f"))
    window = float(main.REGION_PINGS_ISSUANCE_MAX_AGE_S)
    ready = float(main.READY_TIMEOUT_SECONDS)

    assert not (PRE_FIX_JOIN_STALE_S + ready + poll < window), (
        "the pre-fix threshold now passes test 1 -- either the server window "
        "grew or test 1 stopped measuring anything"
    )


def test_the_upload_header_cap_tracks_the_servers_issuance_window():
    """The poll header rides EVERY poll now rather than three after a sweep, so
    its own age cap is what stops a client paying for an upload the server
    cannot use. It must mirror the server's window, not merely be near it."""
    assert _const("const float HEADER_MAX_AGE_S") == float(
        main.REGION_PINGS_ISSUANCE_MAX_AGE_S
    )


def test_the_queue_cadence_is_not_gated_on_a_photon_connection():
    """The whole defect. `ConnectedToMaster()` may appear exactly ONCE inside
    Tick, and only in the menu-idle term -- occurrence counted within the
    FUNCTION span, never file-wide (#432/#330), and over masked code so a
    mention in a comment cannot satisfy it."""
    masked = mask_code(cs_block(SWEEP, TICK))
    assert masked.count("ConnectedToMaster()") == 1, (
        "the queue-live path is gated on a Photon connection again"
    )
    assert and_terms(initialiser(SWEEP, TICK, "bool menuIdleOk")) == [
        "AtMainMenu()",
        "ConnectedToMaster()",
    ]


def test_the_queue_live_predicate_requires_polling_as_well_as_a_state():
    """The poll header is the map's only delivery channel, so a sweep with
    polling off serves nothing; the conjunction also stops a CurrentQueueState
    stranded non-Idle from licensing sweeps forever."""
    body = mask_code(cs_block(SWEEP, "static bool QueueLive()"))
    # Presence is not the invariant -- polling has to be REQUIRED. An un-negated
    # check, or one OR-ed with the states, leaves a CurrentQueueState stranded
    # non-Idle licensing sweeps forever with this test still green.
    polling = re.search(
        r"if\s*\(\s*!\s*ApiClient\.IsQueuePolling\s*\)\s*return\s+false\s*;", body
    )
    assert polling, (
        "polling is no longer a required precondition of QueueLive -- the "
        "conjunction with the queue state is what stops a stranded state "
        "licensing sweeps on its own"
    )
    states_at = body.find("QueueState.Searching")
    assert states_at != -1, "Searching is not a live queue state"
    assert polling.start() < states_at, (
        "the queue state is tested before the polling requirement, so the "
        "requirement no longer dominates it"
    )
    for state in ("Searching", "Matched", "ReadySent"):
        assert f"QueueState.{state}" in body, f"{state} is not a live queue state"
    assert "QueueState.Idle" not in body and "QueueState.Leaving" not in body


def test_a_refused_start_backs_off_before_the_guards_not_at_each_return():
    """The hot-loop defence, and the reason it is written this way.

    `Tick` polls at 250 ms. If the back-off were set at each individual refusal
    instead of once on entry, every exit nobody enumerated -- 'no usable
    targets', the two silent guards, the catch -- would re-enter TryStart four
    times a second and log at that rate forever. Setting it before the first
    guard makes every unenumerated exit fail toward waiting.

    So: the assignment must appear before any `return` in the function, and the
    clear must come after the thread actually starts.
    """
    block = strip_comments_only(cs_block(SWEEP, TRY_START))
    masked = mask_code(cs_block(SWEEP, TRY_START))

    set_at = masked.find("skipUntilRt = rt + SKIP_RETRY_S")
    assert set_at != -1, "the back-off is not set in TryStart at all"

    first_return = masked.find("return")
    assert first_return != -1, "TryStart has no early return; this test is stale"
    assert set_at < first_return, (
        "the back-off is set after a return path -- an unenumerated exit will "
        "re-enter at Tick's 250 ms rate"
    )

    clear_at = masked.find("skipUntilRt = -1f")
    start_at = masked.find("th.Start()")
    assert start_at != -1 and clear_at != -1
    assert clear_at > start_at, (
        "the back-off is cleared before the sweep thread starts, so a refusal "
        "after that point costs nothing"
    )
    assert block.count("skipUntilRt") >= 2


def test_only_a_started_sweep_consumes_the_cadence():
    """`lastTriggerRt` is the cadence anchor. It must move only when a thread
    really started -- anchoring it anywhere else lets a run of refusals eat one
    cadence period each and starve the map while looking healthy.

    CHECKED FILE-WIDE, and that is the point. The first version of this test
    read only TryStart's own block -- which is exactly where the invariant
    already held. The write that broke it sat in NoteConnectedToMaster, far
    outside that span: the connect trigger stamped the anchor on ENTRY, so when
    TryStart then refused (PUN's own region ping routinely outlives the 3 s
    delay) the client waited a full QUEUE_CADENCE_S instead of retrying after
    SKIP_RETRY_S. An invariant about one identifier has to be checked at every
    place that identifier is written, never inside the one span you had in mind
    (#432/#330/#279).
    """
    src = strip_comments_only(SWEEP.read_text(encoding="utf-8"))
    writes = re.findall(r"lastTriggerRt\s*=(?!=)", src)
    assert len(writes) == 2, (
        f"lastTriggerRt is written from {len(writes)} places, expected exactly 2: "
        "its declaration, and the one assignment inside TryStart after th.Start()"
    )
    masked = mask_code(cs_block(SWEEP, TRY_START))
    anchor_at = masked.find("lastTriggerRt = rt")
    start_at = masked.find("th.Start()")
    assert anchor_at != -1, "TryStart no longer anchors the cadence"
    assert anchor_at > start_at, (
        "the cadence is consumed before the sweep starts, so refusals throttle "
        "the next real attempt"
    )


@pytest.mark.parametrize("gone", ["HEADER_POLLS", "SEARCH_CADENCE_S"])
def test_the_replaced_constants_are_really_gone(gone):
    """Both were renamed or removed by this batch. A leftover definition means
    two names for one idea, and the next reader picks the wrong one."""
    assert gone not in strip_comments_only(SWEEP.read_text(encoding="utf-8"))
def test_the_join_body_is_bounded_by_acceptance_not_by_issuance():
    """The fact the refresh-threshold test above does NOT establish, spelled out
    so nobody reads it as more than it is.

    JOIN_STALE_S decides when a join TRIGGERS a refresh. It does not decide what
    rides the body: JoinBodyFields caps on UPLOAD_MAX_AGE_S, which mirrors the
    server's ACCEPTANCE bound (REGION_PINGS_MAX_AGE_S), not its ISSUANCE bound
    (REGION_PINGS_ISSUANCE_MAX_AGE_S). That is deliberate on both sides -- the
    server stores a map it will not decide a room with -- but it means a join
    body can legitimately carry a map far too old to pick a region, and the
    freshness that matters is delivered by the poll header instead.
    """
    upload = _const("const float UPLOAD_MAX_AGE_S")
    header = _const("const float HEADER_MAX_AGE_S")
    join_stale = _const("const float JOIN_STALE_S")

    assert upload == float(main.REGION_PINGS_MAX_AGE_S), (
        "the client's join-body cap no longer mirrors what the server accepts"
    )
    assert header == float(main.REGION_PINGS_ISSUANCE_MAX_AGE_S), (
        "the poll header, which IS the freshness channel, no longer mirrors the "
        "server's issuance window"
    )
    assert join_stale < header < upload, (
        "the three bounds are no longer ordered refresh < issuance < acceptance"
    )
    body = mask_code(cs_block(SWEEP, "public static string JoinBodyFields()"))
    assert "UPLOAD_MAX_AGE_S" in body and "JOIN_STALE_S" not in body, (
        "the join body claims to be gated on the refresh threshold; it is not"
    )


def test_the_reported_age_rounds_up():
    """A map genuinely 180.9 s old must not be reported as 180. The server takes
    the client's integer at face value and re-stamps from it (main.py:13740), so
    truncating did not merely mis-report the age -- it bought a map that was over
    the line a fresh lease on the strength of a rounding error. Over-reporting is
    the safe direction.

    THE MUTATION THIS MUST FAIL ON: putting `return (int)age;` back.
    """
    body = mask_code(cs_block(SWEEP, "static int AgeSeconds()"))
    assert "Math.Ceiling" in body, "the reported age truncates again"
    assert "return (int)age;" not in body


def test_the_catalog_edge_reapplies_the_policy_it_arrives_outside_of():
    """NoteCatalogReady is called from a Photon callback, not from Tick, so it
    inherits none of Tick's queue/menu gating -- and TryStart deliberately
    exempts an OfflineMode room from its in-room guard (#122: a lingering
    Sandbox flag must not wedge the sweep shut at the menu). Without its own
    check, a fetch begun at the menu and answered after the player entered
    Sandbox runs the full raw-UDP sweep inside a local game with no consumer.
    """
    body = mask_code(cs_block(SWEEP, "public static void NoteCatalogReady()"))
    assert "QueueLive()" in body, "the catalog edge no longer asks whether anything wants the map"
    assert "InRoom" in body, "the catalog edge no longer excludes a local room"
    # mask_code blanks string literals, so the "catalog" argument is invisible
    # here -- match the call, not its reason.
    gate_at = body.find("QueueLive()")
    start_at = body.find("TryStart(")
    assert start_at != -1, "the catalog edge no longer starts a sweep at all"
    assert gate_at < start_at, "the sweep is started before the policy is applied"
def test_a_sweep_in_flight_is_never_silently_replaced():
    """Tick refuses every trigger while `current` is non-null, but
    NoteCatalogReady arrives on a Photon callback and never passes through Tick.
    Without its own check, a sweep whose worker has finished but whose result
    Tick has not published yet is overwritten in TryStart and its map lost with
    nothing in the log to say so.

    THE MUTATION THIS MUST FAIL ON: deleting the `current != null` guard, which
    looks redundant next to Tick's own.
    """
    masked = mask_code(cs_block(SWEEP, TRY_START))
    guard = re.search(r"if\s*\(\s*current\s*!=\s*null\s*\)", masked)
    assert guard, "TryStart no longer refuses while a sweep is in flight"
    assign = masked.find("current = sweep")
    assert assign != -1, "TryStart no longer publishes the sweep it started"
    assert guard.start() < assign, (
        "the in-flight guard runs after the replacement it exists to prevent"
    )
