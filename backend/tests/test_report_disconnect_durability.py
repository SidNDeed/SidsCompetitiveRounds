"""The disconnect report's durability, and the H2H read's room budget
(review r8 MEDIUM 3) — two halves of one finding.

POST /api/v1/report-disconnect shares one per-IP rate bucket with every other
sensitive path, and the client wrote it EXACTLY ONCE: a refusal — a 429 being
the ordinary way to earn one — left the dc_events row and the ranked_dc_count
increment behind it simply unmade, on another player's record. The two halves,
and why they are one change:

  * the client keeps a refused report in the durable outbox until the server
    accepts it or settles it, so a refusal is retried instead of lost;
  * the report NAMES the series the leave was watched in, because "the pair's
    series" is a different series by the time a retry lands — r9 took the
    durability out for exactly that reason and this restores it with the
    identity it was missing; and
  * because durability creates replays, the server counts the increment only
    for the request that INSERTED the dc_events row — otherwise the retry
    added to protect the number would be the thing that inflated it.

The server half is EXECUTED against a fake session (the style of
test_h2h_summary.py) so it is tested as wiring rather than as a source string:
a replay whose insert loses must leave the counter alone. The client halves are
read from plugin/*.cs — both sides of one contract, the way the retry-delay
test in test_h2h_summary.py pins the server's debounce window.

The room budget is the other half of the same bucket problem: the H2H read
re-attempts on every opponent-key change, and the key follows a property the
peer's own game publishes, so nothing bounded how much of the shared bucket one
room could spend.
"""

import asyncio
import textwrap
import inspect
import ast
import re
from pathlib import Path

from _cs_structure import method_spans, strip_comments_only
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import main
from sqlalchemy.exc import DBAPIError


REPORTER_SID = "76561198000000011"
LEAVER_SID = "76561198000000012"
REPORTER = UUID("11111111-1111-4111-8111-111111111111")
LEAVER = UUID("22222222-2222-4222-8222-222222222222")
STRANGER = UUID("33333333-3333-4333-8333-333333333333")
# the series the pair are in RIGHT NOW, and the older one a queued report names
CURRENT_SERIES = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
NAMED_SERIES = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
API_CLIENT_CS = PLUGIN / "ApiClient.cs"
H2H_RULES_CS = PLUGIN / "H2HRules.cs"
H2H_SUMMARY_CS = PLUGIN / "H2HSummary.cs"
MAIN_PY = Path(__file__).resolve().parents[1] / "api" / "main.py"


# ── executed: the server half ────────────────────────────────────────────────


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        if not self._rows:
            return None
        row = self._rows[0]
        return row[0] if isinstance(row, tuple) else row


class _ScriptedAbort(Exception):
    """Stands in for asyncpg's error object: SQLAlchemy wraps it and the
    handler reads its sqlstate, which is the only field that decides."""

    def __init__(self, sqlstate):
        super().__init__("scripted %s" % sqlstate)
        self.sqlstate = sqlstate


class FakeSession:
    """Every statement report_disconnect can issue, in Python.

    insert_wins is the concurrency knob: False is the replay whose
    ON CONFLICT DO NOTHING matched an existing row — the case a lost response
    and its outbox retry produce.
    """

    def __init__(self, players, event_exists=False, insert_wins=True, stored_count=4,
                 named_series=None, series_fresh=True, series_still_eligible=True,
                 deadlocks=0, lock_sqlstate="40P01"):
        self.players = list(players)
        self.event_exists = event_exists
        self.insert_wins = insert_wins
        self.stored_count = stored_count
        self.named_series = named_series
        self.series_fresh = series_fresh
        # The locked re-check, which is a DIFFERENT question from series_fresh:
        # it is asked after the unlocked reads, and answers "is this still true
        # now that nothing else can change it".
        self.series_still_eligible = series_still_eligible
        # r12 D: how many times the participant lock pass is aborted by the
        # database before it succeeds, and with which SQLSTATE. 40P01 is a
        # deadlock victim; anything else is a fault this endpoint must not
        # swallow.
        self.deadlocks = deadlocks
        self.lock_sqlstate = lock_sqlstate
        self.aborts_raised = 0
        self.attempts = 0
        self.eligibility_locks = 0
        self.lock_order = []
        self.eligibility_sql = None
        self.statements = []
        self.increments = 0
        self.inserts = 0
        self.commits = 0
        self.rollbacks = 0
        self.series_loads = 0
        self.freshness_checks = 0
        self.count_reads = 0
        self.insert_params = None
        self.dedup_params = None

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        if sql.startswith("SELECT 1 FROM players") and "FOR NO KEY UPDATE" in sql:
            if not self.lock_order or self.lock_order[-1] == "series":
                self.attempts += 1
            if self.deadlocks:
                self.deadlocks -= 1
                self.aborts_raised += 1
                raise DBAPIError(sql, params, _ScriptedAbort(self.lock_sqlstate))
            self.lock_order.append(str((params or {}).get("pid")))
            return _Result([(1,)])
        if sql.startswith("SELECT 1 FROM ranked_series"):
            assert "CAST(:sid AS uuid)" in sql, "the id bind must be typed (#448)"
            if "FOR NO KEY UPDATE" in sql:
                self.eligibility_locks += 1
                self.eligibility_sql = sql
                self.lock_order.append("series")
                return _Result([(1,)] if self.series_still_eligible else [])
            assert "CAST(:live_window AS interval)" in sql, (
                "an interval bind has to be CAST, never concatenated (#448)"
            )
            self.freshness_checks += 1
            return _Result([(1,)] if self.series_fresh else [])
        if "FROM ranked_series" in sql:
            self.series_loads += 1
            return _Result([self.named_series] if self.named_series is not None else [])
        if sql.startswith("SELECT ranked_dc_count FROM players"):
            self.count_reads += 1
            return _Result([(self.stored_count,)])
        if sql.startswith("SELECT") and "FROM players" in sql:
            wanted = list(statement.compile().params.values())[0]
            return _Result([p for p in self.players if p.steam_id == wanted])
        if "FROM dc_events" in sql:
            self.dedup_params = dict(params or {})
            return _Result([(1,)] if self.event_exists else [])
        if sql.startswith("INSERT INTO dc_events"):
            assert "RETURNING" in sql, (
                "the insert must report whether it was the one that recorded the event"
            )
            self.inserts += 1
            self.insert_params = dict(params or {})
            return _Result([(1,)] if self.insert_wins else [])
        if sql.startswith("UPDATE players"):
            assert "ranked_dc_count = COALESCE(ranked_dc_count, 0) + 1" in sql, (
                "the increment must be a delta, never an absolute write (#326)"
            )
            self.increments += 1
            return _Result([(self.stored_count,)])
        raise AssertionError(f"unexpected statement: {sql[:90]}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        # A settled duplicate wrote nothing and rolls back to release the lock
        # pass. Counted separately from commits so "this request wrote nothing"
        # stays assertable as commits == 0.
        self.rollbacks += 1


def _players(count=3):
    return [
        SimpleNamespace(id=REPORTER, steam_id=REPORTER_SID, ranked_dc_count=0),
        SimpleNamespace(id=LEAVER, steam_id=LEAVER_SID, ranked_dc_count=count),
    ]


@pytest.fixture(autouse=True)
def _stub_the_gates(monkeypatch):
    """Everything the handler leans on that is not this finding: the session
    gate, the service-account fence and the pair's current series. Returns the
    call counter so a test can assert the resolve-at-delivery path was NOT
    taken when the report named a series."""
    calls = {"find_current": 0}

    async def _noop(*args, **kwargs):
        return None

    async def _series(*args, **kwargs):
        calls["find_current"] += 1
        return SimpleNamespace(id=CURRENT_SERIES, player1_id=REPORTER, player2_id=LEAVER)

    monkeypatch.setattr(main, "_check_steam_session", _noop)
    monkeypatch.setattr(main, "_assert_no_service_subject", _noop)
    monkeypatch.setattr(main, "_find_current_active_series", _series)
    return calls


def _call(session, series_id=None):
    request = SimpleNamespace(headers={"X-Session-Token": "tok"})
    return asyncio.run(
        main.report_disconnect(request, REPORTER_SID, LEAVER_SID, series_id, session)
    )


def _series_row(player1=REPORTER, player2=LEAVER, invalidated=None, sid=NAMED_SERIES,
                reason=None):
    return SimpleNamespace(id=sid, player1_id=player1, player2_id=player2,
                           invalidated_at=invalidated, invalidation_reason=reason)


def test_the_request_that_inserts_the_row_is_the_one_that_counts():
    session = FakeSession(_players(), stored_count=4)
    answer = _call(session)
    assert answer["status"] == "recorded"
    assert session.inserts == 1
    assert session.increments == 1
    assert session.commits == 1


def test_a_replay_that_loses_the_insert_counts_nothing():
    """The whole point: only one row lands, and the loser must add nothing —
    an unconditional increment would take a leave-% denominator up by one for a
    disconnect that happened once.

    r12 LOW, on the SCHEDULE this used to describe. It said both requests clear
    the dc_events SELECT and then race the insert. Since the exclusive series
    lock went in, two reports naming the same series serialise before either
    reads dc_events, so that interleaving is no longer reachable in this
    codebase and the second request takes the settled fast path instead. The
    INSERT is still what decides, and that is deliberate: it is the last line
    that holds if the lock is ever narrowed, moved, or taken on a different
    row. What this exercises is the losing branch itself, driven directly."""
    session = FakeSession(_players(count=7), event_exists=False, insert_wins=False,
                          stored_count=8)
    answer = _call(session)
    assert answer["status"] == "already_recorded"
    assert session.inserts == 1
    assert session.increments == 0, "the losing replay incremented the count"
    assert session.commits == 0
    # 8 is what the winner committed; 7 is the row this request loaded before
    # the conflict was decided, and is one behind by construction.
    assert answer["ranked_dc_count"] == 8


def test_the_settled_replay_still_short_circuits_before_any_write():
    """A retry arriving after the first report committed: the fast path reads
    the row and answers without attempting an insert at all."""
    session = FakeSession(_players(count=7), event_exists=True, stored_count=8)
    answer = _call(session)
    assert answer["status"] == "already_recorded"
    assert answer["ranked_dc_count"] == 8
    assert session.count_reads == 1
    assert session.inserts == 0
    assert session.increments == 0
    assert session.commits == 0


def test_no_settled_answer_reports_the_row_this_request_loaded():
    """Both already_recorded paths. The ORM row is read at the top of the
    handler, before anything has been decided; under a concurrent report it is
    behind the committed value by exactly the increment this request lost."""
    for kwargs in ({"event_exists": True}, {"insert_wins": False}):
        session = FakeSession(_players(count=3), stored_count=11, **kwargs)
        answer = _call(session)
        assert answer["status"] == "already_recorded"
        assert answer["ranked_dc_count"] == 11
        assert session.count_reads == 1


def test_the_recorded_answer_is_the_value_the_database_returned():
    """Not a number computed from the row read before the insert decided —
    that read is stale by construction under a concurrent replay."""
    session = FakeSession(_players(count=0), stored_count=9)
    assert _call(session)["ranked_dc_count"] == 9


# ── executed: the series the report NAMES ────────────────────────────────────


def test_the_predicate_is_re_asked_under_a_lock_before_anything_is_written():
    """r11. Existence, the pair and the invalidation were established by
    unlocked reads, and the insert and the counter increment happened after
    them — so an integrity invalidation committing in that window was checked
    against a state that had already gone. #208: the transaction re-reads its
    row and re-checks the predicate, under a lock it holds to commit."""
    session = FakeSession(_players(), named_series=_series_row())
    _call(session, str(NAMED_SERIES))
    assert session.eligibility_locks == 1
    sql = session.eligibility_sql
    assert "FOR NO KEY UPDATE" in sql, (
        "#202: the weakest mode that still conflicts with the status and "
        "invalidation UPDATEs this is guarding against"
    )
    # the predicate is INSIDE the locking read, so the row that comes back is
    # the row that satisfies it — there is no gap between establishing the fact
    # and holding it
    assert "s.player1_id = :rp AND s.player2_id = :dp" in sql
    assert "s.player1_id = :dp AND s.player2_id = :rp" in sql
    assert "s.invalidated_at IS NULL OR s.invalidation_reason = :exempt" in sql
    # r12: a series COMPLETING while the locks are being taken is a state
    # change this report has to see, so reachability is re-asked here too --
    # otherwise a report validated against a running series could be filed
    # against one that finished in the window the lock exists to close.
    assert "s.completed_at IS NULL" in sql
    assert "ORDER BY s2.created_at DESC LIMIT 1" in sql
    assert "FOR NO KEY UPDATE OF s" in sql, (
        "with a subquery in the statement the lock has to name its table"
    )
    # ...and it is taken before the row that decides
    order = session.statements
    lock_at = next(i for i, s in enumerate(order)
                   if s.startswith("SELECT 1 FROM ranked_series") and "FOR NO KEY UPDATE" in s)
    insert_at = next(i for i, s in enumerate(order) if s.startswith("INSERT INTO dc_events"))
    assert lock_at < insert_at


def test_the_lock_order_is_participants_then_series():
    """The 1v1 protocol is players -> ranked_series (#206), taken by
    /api/v1/matches and by the bet payout path. Series-then-players is the 2v2
    order — its table is disjoint — and taking it here would form an ABBA
    against every 1v1 writer. Participants are sorted by str(id) so two reports
    naming the same pair cannot deadlock against each other."""
    session = FakeSession(_players(), named_series=_series_row())
    _call(session, str(NAMED_SERIES))
    assert session.lock_order == sorted([str(REPORTER), str(LEAVER)]) + ["series"]
    # the unnamed path takes exactly the same locks: the protection is not a
    # property of naming a series
    other = FakeSession(_players())
    _call(other, None)
    assert other.lock_order == sorted([str(REPORTER), str(LEAVER)]) + ["series"]


def test_a_series_that_stops_qualifying_under_the_lock_records_nothing():
    """Every unlocked read passed; the locked re-check did not. Nothing is
    inserted, nothing is incremented, and the client is told it is settled —
    a 4xx, because no amount of retrying makes an invalidated series
    eligible."""
    session = FakeSession(_players(), named_series=_series_row(),
                          series_still_eligible=False)
    with pytest.raises(main.HTTPException) as caught:
        _call(session, str(NAMED_SERIES))
    assert caught.value.status_code == 403
    assert session.inserts == 0
    assert session.increments == 0


def test_a_settled_duplicate_does_not_hold_its_locks_to_the_response():
    """It wrote nothing, so there is no reason for two participants and their
    series to stay locked while the response is built and sent."""
    session = FakeSession(_players(), named_series=_series_row(), event_exists=True)
    result = _call(session, str(NAMED_SERIES))
    assert result["status"] == "already_recorded"
    assert session.rollbacks == 1, "the lock pass is still held through the response"
    assert session.commits == 0, "a request that wrote nothing must not claim a write"
    assert session.increments == 0


def test_a_named_series_is_what_the_event_is_filed_against(_stub_the_gates):
    """The whole point of the restore. The pair have moved on to
    CURRENT_SERIES; a report queued during NAMED_SERIES arrives now. It must
    land on the series it was observed in, and the resolve-at-delivery helper
    must not be consulted at all — consulting it is how the wrong answer was
    reached."""
    session = FakeSession(_players(), named_series=_series_row())
    answer = _call(session, str(NAMED_SERIES))
    assert answer["status"] == "recorded"
    assert session.insert_params["sid"] == NAMED_SERIES
    assert session.dedup_params["sid"] == NAMED_SERIES
    assert _stub_the_gates["find_current"] == 0, (
        "a named series must not fall through to the pair's current one"
    )


def test_a_report_with_no_series_still_resolves_at_delivery(_stub_the_gates):
    """Old clients, and the one window a current client has none: the
    behaviour they had is unchanged."""
    session = FakeSession(_players())
    answer = _call(session, None)
    assert answer["status"] == "recorded"
    assert session.insert_params["sid"] == CURRENT_SERIES
    assert session.series_loads == 0
    assert _stub_the_gates["find_current"] == 1


def test_a_named_series_that_is_not_this_pairs_falls_back_to_the_pair(_stub_the_gates):
    """r12 MEDIUM. A named series is still checked against the database and
    never taken as given -- but a name that resolves to some other pair's
    series used to be a PERMANENT refusal, and the client treats a 4xx as
    settled.

    The name is an assertion about which series the observation belongs to.
    When the assertion is false the server knows nothing worse than it knows
    without one, so it does what every client that sends no name already gets:
    resolve the pair's current series, with every check on that path applied.
    Room names are reused, and a series id staged for a join that failed is
    exactly how a client comes to name the wrong one."""
    session = FakeSession(_players(), named_series=_series_row(player2=STRANGER))
    answer = _call(session, str(NAMED_SERIES))
    assert answer["status"] == "recorded"
    assert _stub_the_gates["find_current"] == 1, "the unnamed resolution must run"
    assert session.insert_params["sid"] == CURRENT_SERIES, (
        "the event is filed against the pair's series, not the named stranger's"
    )

def test_the_pair_check_is_order_blind():
    """player1/player2 order is a property of how the series was created, not
    of who is reporting."""
    session = FakeSession(_players(), named_series=_series_row(player1=LEAVER, player2=REPORTER))
    assert _call(session, str(NAMED_SERIES))["status"] == "recorded"


def test_an_integrity_invalidation_takes_no_new_events():
    """Every reason except the janitor's one. Written as a loop over the
    reasons actually present on ranked_series so that adding a reason cannot
    quietly widen what this endpoint accepts — the code is an allow-list of
    one, and this is the assertion that it stays one."""
    for reason in ("admin_void", "short_duration_pattern_retro", "series_abandoned",
                   "janitor_dead_lock", "member_banned", "phantom_ranked_private_room",
                   None, ""):
        session = FakeSession(_players(),
                              named_series=_series_row(invalidated="2026-09-01", reason=reason))
        with pytest.raises(main.HTTPException) as caught:
            _call(session, str(NAMED_SERIES))
        assert caught.value.status_code == 403, reason
        assert session.inserts == 0, reason


def test_the_janitors_no_match_reported_is_not_evidence_against_the_report(_stub_the_gates):
    """r11 HIGH. _prune_stale_series abandons an active series that is half an
    hour old with no match reported against it, stamping invalidated_at and
    'no_match_reported'. A leave during game 1 produces exactly that row — the
    game is not counted, so no match is ever reported — so refusing on it
    discarded the report for the case durability exists for, and the outbox
    treats a 4xx as settled and drops the entry. The reason is the report
    restated by the janitor, not evidence against it."""
    session = FakeSession(_players(),
                          named_series=_series_row(invalidated="2026-09-01",
                                                   reason=main.PRUNE_REASON_NO_MATCH))
    out = _call(session, str(NAMED_SERIES))
    assert out["status"] == "recorded"
    assert session.inserts == 1


def test_the_janitor_and_the_endpoint_read_the_same_constant():
    """Two literals in two files drift in one of them. The prune writes the
    reason and this endpoint reads it back, so there is one name for it."""
    src = MAIN_PY.read_text(encoding="utf-8")
    assert src.count('"no_match_reported"') == 1, (
        "the reason is spelled once, at the constant"
    )
    assert src.count("PRUNE_REASON_NO_MATCH") >= 3, (
        "one definition, the prune's writer, and the endpoint's reader"
    )


def test_an_unknown_series_falls_back_the_same_way(_stub_the_gates):
    """Same rule, the other way a name can be wrong: it resolves to nothing at
    all. An id that names no row is not evidence about the report either.

    An INVALIDATED name is still a refusal, because that IS evidence and it
    points the conservative way -- see
    test_an_integrity_invalidation_takes_no_new_events."""
    session = FakeSession(_players(), named_series=None)
    answer = _call(session, str(NAMED_SERIES))
    assert answer["status"] == "recorded"
    assert _stub_the_gates["find_current"] == 1
    assert session.insert_params["sid"] == CURRENT_SERIES

def test_a_series_the_name_cannot_reach_is_refused_and_asked_in_sql():
    """Naming a series is what lets a queued report reach a series that is no
    longer current; the age bound is what keeps that from reaching the pair's
    whole shared history. It is asked of the database clock, so an api
    container with a skewed clock cannot move it."""
    session = FakeSession(_players(), named_series=_series_row(), series_fresh=False)
    with pytest.raises(main.HTTPException) as caught:
        _call(session, str(NAMED_SERIES))
    assert caught.value.status_code == 403
    assert session.freshness_checks == 1
    assert session.inserts == 0


def test_the_name_reaches_one_series_that_is_live_and_has_been_played():
    """Three r-round findings, one predicate, asked of the server's own record.

    REACHABILITY. The unnamed path can only ever reach one series. Naming used
    to reach every series of the pair inside a week, so a participant could file
    one disconnect against the other for every normally-completed series they
    had played -- and ranked_dc_count feeds the leave-% denominator. A name
    reaches a series that has not completed, or the pair's most recent one.

    LIVENESS (r13 MEDIUM). `completed_at IS NULL` was carrying "still running",
    and it cannot: a tournament forfeit deliberately leaves its series row
    active with both terminal timestamps null forever, so every old forfeited
    series stayed nameable and each was worth one disconnect. A running series
    is one something happened in recently, and `last_activity_at` is the column
    the server stamps itself.

    GAMEPLAY (r13 MEDIUM). The ">= 2 total points" rule existed only on the
    client, so an authenticated participant could report an opponent at 0-0 in a
    series where nothing had happened. The same bar is asked of live_p*_points,
    or satisfied by a recorded match."""
    sql = MAIN_PY.read_text(encoding="utf-8")
    start = sql.index("SELECT 1 FROM ranked_series s")
    query = sql[start:start + 1600]
    assert "s.completed_at IS NULL" in query
    assert "ORDER BY s2.created_at DESC LIMIT 1" in query, (
        "the pair's most recent series is the one completed series a name reaches"
    )
    assert "COALESCE(s.last_activity_at, s.created_at)" in query, (
        "liveness is asked of the column the server stamps, not of a null"
    )
    assert "CAST(:live_window AS interval)" in query, (
        "an interval bind has to be CAST, never concatenated (#448)"
    )
    assert "COALESCE(s.live_p1_points, 0) + COALESCE(s.live_p2_points, 0)" in query
    assert "EXISTS (SELECT 1 FROM matches m WHERE m.series_id = s.id)" in query
    assert "INTERVAL '7 days'" not in query, (
        "the created_at/completed_at week is retired; liveness replaced it"
    )
    # asked of the database clock, never compared to a python now
    assert "NOW()" in query and "datetime.now" not in query
    # and the window is a number this module owns, not a literal in a string
    assert main.DC_LIVE_WINDOW_SECONDS <= 24 * 3600, (
        "a day-wide window would let a name walk back through the pair's history"
    )
    assert main.DC_MIN_LIVE_POINTS >= 2, "the server bar must not be below the client's"


def test_a_malformed_series_id_is_a_4xx_so_the_client_stops_retrying():
    """4xx is permanent to the client's retry pass. A report whose id cannot
    parse can never land, so it must be settled rather than retried."""
    session = FakeSession(_players())
    with pytest.raises(main.HTTPException) as caught:
        _call(session, "not-a-uuid")
    assert 400 <= caught.value.status_code < 500
    assert session.series_loads == 0 and session.inserts == 0


def test_a_named_series_still_dedups_per_series_and_player():
    """The replay safety the server already had has to survive the new path —
    it is what makes queueing safe at all."""
    session = FakeSession(_players(count=7), named_series=_series_row(), insert_wins=False)
    answer = _call(session, str(NAMED_SERIES))
    assert answer["status"] == "already_recorded"
    assert session.increments == 0
    assert session.commits == 0


def test_both_paths_of_the_finding_sit_in_one_rate_bucket():
    """The premise the whole change rests on, asserted rather than assumed:
    the H2H read and the disconnect write are throttled together, per IP."""
    prefixes = main._RL_SENSITIVE_PREFIXES
    assert "/api/v1/h2h/" in prefixes
    assert "/api/v1/report-disconnect" in prefixes
    assert main._RL_SENSITIVE == (20, 10.0)


# ── the client half: the durable write ───────────────────────────────────────


def _cs_method_body(path, signature):
    """The braces-matched body of one C# member, so an assertion about a
    method cannot be satisfied by a match elsewhere in the file.

    Structure is decided on a mask (`_cs_structure`), so a brace inside a
    comment, a string, a char literal or an inactive `#if` branch is not
    counted. The raw walk this replaces returned the wrong block on any file
    carrying one - `plugin/Plugin.cs` has raw brace balance +2 from a doc
    comment alone, and `plugin/ApiClient.cs` +22 from JSON inside strings.
    """
    spans = list(method_spans(path, signature))
    if not spans:
        raise AssertionError(f"signature not found: {signature}")
    open_brace, end = spans[0]
    return path.read_text(encoding="utf-8")[open_brace:end]


DC_SIGNATURE = ("public static void ReportDisconnect(string reporterSteamId, "
                "string disconnectedSteamId, string seriesId)")


def test_the_disconnect_report_is_durable_and_names_its_series():
    """The queued copy is written BEFORE the first network yield, so a quit or
    a crash between here and the response cannot lose it, and the url it is
    stored under carries the series — that url is the whole record, because
    the outbox persists a url and a body and nothing else."""
    body = _cs_method_body(API_CLIENT_CS, DC_SIGNATURE)
    assert "&series_id={Escape(seriesId)}" in body
    assert body.index("EnqueueFailedReport") < body.index("StartCoroutine("), (
        "the report must be queued before the first network yield"
    )
    assert "RemovePendingReport(url, DC_REPORT_BODY)" in body


def test_a_report_that_cannot_name_its_series_is_never_queued():
    """The unnamed report is exactly the one a later delivery would have to
    guess about. It keeps the single attempt it always had."""
    body = _cs_method_body(API_CLIENT_CS, DC_SIGNATURE)
    assert "bool durable = !string.IsNullOrEmpty(seriesId);" in body
    for guarded in ("if (durable) EnqueueFailedReport(url, DC_REPORT_BODY);",
                    "if (durable) url += $\"&series_id={Escape(seriesId)}\";"):
        assert guarded in body, f"missing: {guarded}"
    assert body.count("EnqueueFailedReport") == 1
    assert body.count("RemovePendingReport") == 1


def test_the_series_is_captured_at_the_observation_not_at_the_send():
    """ActiveRankedSeriesId is cleared at every game-report boundary and at
    room leave. Reading it inside ReportDisconnect would be reading it at send
    time, which for a retry is the wrong moment by construction — so the id
    arrives as an argument, from the frame that saw the leave."""
    body = _cs_method_body(API_CLIENT_CS, DC_SIGNATURE)
    assert "ActiveRankedSeriesId" not in body
    gsw = (PLUGIN / "GameStateWatcher.cs").read_text(encoding="utf-8")
    assert gsw.count("ApiClient.ReportDisconnect(") == 1
    call = "ApiClient.ReportDisconnect(localSteamId, opponentSteamId, dcSeriesId);"
    assert call in gsw
    capture = "string dcSeriesId = ApiClient.SeriesIdForThisRoom();"
    assert capture in gsw
    assert gsw.index(capture) < gsw.index(call)
    # ...and the accessor is room-fenced, because the queue publishes the NEXT
    # pairing's id at both_ready — before the seat has joined that room. An
    # observation made in one room must not be filed under another room's
    # series; an empty answer degrades to the unnamed report, which the server
    # resolves from the pair.
    api = API_CLIENT_CS.read_text(encoding="utf-8")
    fence = _cs_method_body(API_CLIENT_CS, "public static string SeriesIdForThisRoom()")
    assert "PhotonNetwork.InRoom" in fence
    assert "H2HRules.SeriesForRoom(activeSeriesBinding" in fence, (
        "r13 HIGH: the fence asks the occupancy rule, not a room name"
    )
    assert "RoomIncarnation, OpponentInRoomOrEmpty());" in fence, (
        "the fence has to hand the rule the occupancy and the pairing, not a name"
    )
    # The id and the room it was published for used to be two assignments a
    # caller had to remember to write together; r13 put both in ONE record and
    # this sweep checked that nothing wrote the id outside the two owners.
    #
    # r14 removed the question. A retirement nulled the binding while the field
    # kept the id, so the gates that ask "is a series live here" still saw one
    # and suppressed the next pairing's preflight -- two values describing one
    # thing, disagreeing. The id is now DERIVED from the record, so there are
    # no write sites to sweep for and a new one would not compile.
    strays = []
    for name, src in (("ApiClient.cs", api), ("GameStateWatcher.cs", gsw),
                      ("Plugin.cs", (PLUGIN / "Plugin.cs").read_text(encoding="utf-8"))):
        for ln in src.splitlines():
            if "ActiveRankedSeriesId = " not in ln:
                continue
            if "public static string ActiveRankedSeriesId" in ln:   # the declaration
                continue
            strays.append((name, ln.strip()))
    assert strays == [], (
        f"the series id is stored somewhere as well as derived: {strays}"
    )
    decl = api.index("public static string ActiveRankedSeriesId")
    assert "get { return activeSeriesBinding.HasValue" in api[decl:decl + 400], (
        "the id is not derived from the binding it is supposed to describe"
    )
    publish = _cs_method_body(API_CLIENT_CS, "public static void PublishActiveSeries(string seriesId, string room)")
    clear = _cs_method_body(API_CLIENT_CS, "public static void ClearActiveSeries()")
    assert "H2HRules.PublishSeries(ref activeSeriesBinding" in publish, (
        "publication no longer goes through the transition that decides the stamp"
    )
    assert "activeSeriesBinding = null;" in clear, "clearing does not clear the record"

    # ...and the callers are still the sites they were: 3 publishes (preflight,
    # queue both_ready, queue poll) and 4 clears (two in ApiClient, the
    # game-report boundary, the room-leave edge).
    sites = []
    for name, src in (("ApiClient.cs", api), ("GameStateWatcher.cs", gsw),
                      ("Plugin.cs", (PLUGIN / "Plugin.cs").read_text(encoding="utf-8"))):
        for ln in src.splitlines():
            stripped = ln.strip()
            if stripped.startswith("public static void PublishActiveSeries"):
                continue
            if stripped.startswith("public static void ClearActiveSeries"):
                continue
            if "PublishActiveSeries(" in ln:
                sites.append((name, "publish"))
            elif "ClearActiveSeries()" in ln:
                sites.append((name, "clear"))
    assert sorted(sites) == sorted([
        ("ApiClient.cs", "publish"),        # preflight
        ("ApiClient.cs", "publish"),        # queue /ready both_ready
        ("ApiClient.cs", "publish"),        # queue poll ready_join
        ("ApiClient.cs", "clear"),          # live-points "not active" refusal
        ("ApiClient.cs", "clear"),          # the game-report boundary
        ("GameStateWatcher.cs", "clear"),   # the polled room exit
        ("Plugin.cs", "clear"),             # the reliable room-leave edge
    ]), f"the publish/clear sites moved: {sorted(sites)}"


def test_the_queued_body_is_one_constant_on_both_paths():
    """The outbox finds an entry by (url, body). A send that used a different
    body from the queued copy could never remove its own entry, and the report
    would be delivered twice — harmless to the count, but it would retry for
    twenty attempts against a server that had already recorded it."""
    src = API_CLIENT_CS.read_text(encoding="utf-8")
    assert 'internal const string DC_REPORT_BODY = "{}";' in src
    body = _cs_method_body(API_CLIENT_CS, DC_SIGNATURE)
    assert body.count("DC_REPORT_BODY") == 3
    assert '""' not in body.replace('"{}"', "")


def test_the_disconnect_report_gets_no_toast_in_either_direction():
    """It reports somebody else's leave. There is nothing for the player to
    do about it, so neither the queue notice nor the delivered notice fires."""
    silent = _cs_method_body(API_CLIENT_CS, "private static bool IsSilentOutboxUrl(string url)")
    assert "IsDisconnectReportUrl(url)" in silent


def test_the_retry_pass_removes_by_reference_and_not_by_a_stale_index():
    """The defect enrolling this report made reachable, fixed rather than
    avoided (learning #488).

    The old sweep captured an index, yielded into PostRequest, then removed by
    that index — while RemovePendingReport, running on a success callback in
    another coroutine, could shrink the same list during the yield. The index
    then named a different entry, or none. Nothing about the timing is
    asserted here because nothing about the timing is load-bearing any more:
    the pass takes a snapshot, re-checks membership after every yield, and
    removes the entry it actually attempted."""
    body = _cs_method_body(API_CLIENT_CS, "private static IEnumerator OutboxPass()")
    assert "RemoveAt(" not in body, "the pass is back to removing by index"
    assert body.count("_pendingReports.Remove(p)") == 2, (
        "both dispositions — delivered and dropped — must remove the entry itself"
    )
    assert "if (!_pendingReports.Contains(p)) continue;" in body, (
        "an entry the immediate send already delivered must not be resent"
    )
    src = API_CLIENT_CS.read_text(encoding="utf-8")
    assert "IEnumerator OutboxLoop()" not in src, "the old index-walking loop is still here"


def test_one_faulting_pass_cannot_retire_the_queue_for_the_session():
    """Unity stops a coroutine that lets an exception out. Before the
    supervisor, one throw ended every retry for the rest of the session —
    including reports already written to disk — with nothing but the exception
    in the log.

    The property is unchanged; what USED to record "a supervisor exists" is
    not. It was a static bool, and r13 replaced it with the host that is
    driving one, because destroying that host stops the coroutine without
    running the `finally` that cleared the bool."""
    sup = _cs_method_body(API_CLIENT_CS, "private static IEnumerator OutboxSupervisor(int generation)")
    assert "top.MoveNext()" in sup, "the pass must be driven by hand to be catchable"
    assert "catch (Exception ex)" in sup
    assert "_outboxLoopHost = null;" in sup, "a supervisor that returns must release the host"
    assert "finally {" in sup, "release has to happen on the way out, however it leaves"
    src = API_CLIENT_CS.read_text(encoding="utf-8")
    assert "StartCoroutine(OutboxSupervisor(generation))" in src


def test_the_guard_covers_the_request_and_not_only_the_pass():
    """r12 MEDIUM. Driving the pass by hand catches a throw in the PASS. But
    the pass yields the request coroutine itself, and a yielded IEnumerator is
    run by UNITY, on its own, outside that catch — so a throw inside a request
    escaped the supervisor and killed it. A persisted entry with a malformed
    url reaches exactly that, and the queue then waits for an enqueue a session
    with nothing left to report never makes.

    Nested enumerators are driven on the same stack; only real yield
    instructions are handed to Unity."""
    sup = _cs_method_body(API_CLIENT_CS, "private static IEnumerator OutboxSupervisor(int generation)")
    assert "var nested = current as IEnumerator;" in sup
    assert "stack.Add(nested);" in sup
    assert "stack.Count < OUTBOX_NEST_LIMIT" in sup, "the hand-driving must be bounded"
    # the yield that reaches Unity is the one that is NOT an enumerator
    assert sup.index("var nested = current as IEnumerator;") < sup.index("yield return current;")
    # a fault abandons the pass, it does not retire the queue: the entry keeps
    # the attempt count and next-attempt time set before the yield
    assert "if (faulted) break;" in sup
    pass_body = _cs_method_body(API_CLIENT_CS, "private static IEnumerator OutboxPass()")
    assert "p.nextAt = Time.realtimeSinceStartup" in pass_body
    assert pass_body.index("p.nextAt =") < pass_body.index("yield return PostRequest(")


def test_a_supervisor_that_did_not_start_takes_no_ownership():
    """r12 LOW, kept: the premise was that StartCoroutine THROWS on an inactive
    host. On an inactive host Unity logs and returns null instead, so a
    try/catch around the call proves nothing about whether anything started.
    The returned Coroutine is what says so, and ownership is recorded only
    after it comes back non-null."""
    ensure = _cs_method_body(API_CLIENT_CS, "private static void EnsureOutboxLoop()")
    assert "var running = host.StartCoroutine(OutboxSupervisor(generation));" in ensure
    assert "if (running == null)" in ensure
    assert ensure.index("if (running == null)") < ensure.index("_outboxLoopHost = host;")
    assert "_outboxLoopWarned" in ensure, "a queue with no driver has to say so once"
def test_the_initial_delay_set_stays_small_and_explicit():
    """No longer a safety property — remove-by-reference is — but a new delay
    is still a decision somebody should have to make on purpose."""
    import re as _re

    delay = _cs_method_body(API_CLIENT_CS, "private static float OutboxInitialDelay(string url)")
    delays = sorted(int(x) for x in _re.findall(r"(\d+)f", delay))
    assert delays == [30, 120], f"a new initial-retry delay appeared: {delays}"

    src = API_CLIENT_CS.read_text(encoding="utf-8")
    sites = src.count("EnqueueFailedReport(")
    # declaration + macro evidence + four match-report paths + the disconnect report
    assert sites == 7, f"{sites} EnqueueFailedReport references, expected 7"


def test_the_server_half_of_the_finding_holds_the_replay_safety():
    """Durability on the client creates replays; these two lines are what make
    a replay cost nothing. They must not drift."""
    src = MAIN_PY.read_text(encoding="utf-8")
    handler = src[src.index("async def report_disconnect("):]
    handler = handler[: handler.index("\n@app.")] if "\n@app." in handler else handler
    assert "ON CONFLICT DO NOTHING RETURNING 1" in handler
    assert "COALESCE(ranked_dc_count, 0) + 1" in handler


# ── the client half: the room budget ─────────────────────────────────────────


def _cs_int_const(name):
    src = H2H_RULES_CS.read_text(encoding="utf-8")
    m = re.search(rf"internal const int {name} = (\d+);", src)
    assert m, f"{name} not found in {H2H_RULES_CS}"
    return int(m.group(1))


def _cs_float_const(name):
    src = H2H_RULES_CS.read_text(encoding="utf-8")
    m = re.search(rf"internal const float {name} = (\d+(?:\.\d+)?)f;", src)
    assert m, f"{name} not found in {H2H_RULES_CS}"
    return float(m.group(1))


def test_the_room_budget_is_reset_with_the_incarnation_and_never_with_the_key():
    """The entire mechanism. A reset on the key would restore exactly the
    unbounded behaviour, because a key change is what the budget bounds — and
    it is one line to write in the wrong method."""
    reset_room = "roomBudget = default(H2HRules.RoomBudget);"
    incarnation = _cs_method_body(H2H_SUMMARY_CS, "private static void ResetIncarnation()")
    attempt = _cs_method_body(H2H_SUMMARY_CS, "private static void ResetAttempt()")
    key = _cs_method_body(H2H_SUMMARY_CS, "private static void ResetKey()")
    assert reset_room in incarnation
    assert reset_room not in attempt
    assert reset_room not in key
    assert H2H_SUMMARY_CS.read_text(encoding="utf-8").count(reset_room) == 1


def test_every_h2h_send_is_admitted_by_the_room_budget_first():
    """One send site, and the admission above it in the same method. The
    admission spends the budget as it answers, so a send that reached the wire
    without passing it is a send nothing counted."""
    src = H2H_SUMMARY_CS.read_text(encoding="utf-8")
    assert src.count("ApiClient.FetchH2HSummary(") == 1
    tick = _cs_method_body(H2H_SUMMARY_CS, "internal static void Tick()")
    assert tick.count("ApiClient.FetchH2HSummary(") == 1
    assert tick.count("H2HRules.AdmitRoomRequest(ref roomBudget") == 1
    assert tick.index("AdmitRoomRequest") < tick.index("ApiClient.FetchH2HSummary(")
    assert "RoomGate.Exhausted" in tick and "RoomGate.TooSoon" in tick


def test_the_room_budget_never_truncates_one_keys_retry_ladder():
    """A cap below a single key's own ladder would turn a bounded retry into a
    dropped line on the ordinary path."""
    ladder = (
        1
        + _cs_int_const("MAX_SESSION_RESENDS")
        + _cs_int_const("MAX_TRANSPORT_RETRIES")
        + _cs_int_const("MAX_DEBOUNCE_RETRIES")
    )
    assert _cs_int_const("MAX_REQUESTS_PER_ROOM") >= ladder
    spacing = _cs_float_const("MIN_REQUEST_SPACING_SECONDS")
    assert spacing < _cs_float_const("TRANSPORT_RETRY_DELAY")
    assert spacing < _cs_float_const("DEBOUNCE_RETRY_FALLBACK")


def test_one_room_cannot_spend_the_shared_bucket():
    """The bound that matters, in the server's own units: with the spacing
    above, the most H2H reads one client can put into one rate window must
    leave the window's mutating traffic — the disconnect report among it —
    room to land."""
    limit, window = main._RL_SENSITIVE
    spacing = _cs_float_const("MIN_REQUEST_SPACING_SECONDS")
    most_in_window = int(window // spacing) + 1
    assert most_in_window * 2 <= limit, (
        "two clients behind one address would leave nothing for the writes"
    )
    assert most_in_window <= _cs_int_const("MAX_REQUESTS_PER_ROOM")


def test_the_supervisor_is_owned_by_a_host_and_not_by_a_latch():
    """r13 MEDIUM, and the finding that replaces this test's old premise.

    Ownership used to be a static bool cleared by the coroutine's `finally`.
    The ordinary way a supervisor dies does not run one: destroying the
    GameObject it was started on stops it where it stands. The bool then read
    "a supervisor exists" for the rest of the process, the respawned host
    declined to start another, and reports already on disk sat unsent -- with
    the enqueue that would have re-armed it returning early on the duplicate
    before it got that far.

    Four properties, each the answer to one of those:

      1. ownership names WHICH host, so a respawn does not inherit it. Unity
         reports a destroyed object as null, so the same test covers a host
         that was destroyed without being replaced;
      2. it is generation-stamped, so a late `finally` from a superseded
         supervisor cannot clear its replacement's;
      3. it expires on a missed lap, which is the bound that covers however
         else a coroutine can stop without unwinding -- there is no enumerating
         those;
      4. it is asked on a TICK, not only on an enqueue. A session whose driver
         died with reports already queued makes no further enqueue, and that is
         exactly the session whose queue would otherwise never move.
    """
    src = API_CLIENT_CS.read_text(encoding="utf-8")
    assert "_outboxLoopStarted" not in src, "the latch is back"

    live = _cs_method_body(API_CLIENT_CS, "private static bool OutboxLoopIsLive(MonoBehaviour host)")
    assert "if (_outboxLoopHost == null) return false;" in live, (
        "a destroyed host has to read as no owner"
    )
    assert "if (!ReferenceEquals(_outboxLoopHost, host)) return false;" in live, (
        "a respawned host has to read as no owner"
    )
    assert "_outboxLoopBeatRt <= OUTBOX_BEAT_TIMEOUT" in live, "ownership never expires"

    supervisor = _cs_method_body(API_CLIENT_CS, "private static IEnumerator OutboxSupervisor(int generation)")
    assert "if (_outboxLoopGeneration != generation) yield break;" in supervisor
    assert "_outboxLoopBeatRt = Time.realtimeSinceStartup;" in supervisor, "nothing beats"
    assert "finally { if (_outboxLoopGeneration == generation) _outboxLoopHost = null; }" in supervisor, (
        "a superseded supervisor's finally can still clear the live owner"
    )

    enqueue = _cs_method_body(API_CLIENT_CS, "public static void EnqueueFailedReport(string url, string json)")
    dup = enqueue.index("if (pending.url == url && pending.json == json)")
    assert enqueue.index("EnsureOutboxLoop();") < dup, (
        "the duplicate enqueue returns before it can re-arm the driver"
    )

    tick = _cs_method_body(API_CLIENT_CS, "internal static void OutboxTick()")
    assert "if (_pendingReports.Count == 0) return;" in tick, "the tick has to be free when idle"
    assert "EnsureOutboxLoop();" in tick
    plugin_cs = (API_CLIENT_CS.parent / "Plugin.cs").read_text(encoding="utf-8")
    assert "ApiClient.OutboxTick();" in plugin_cs, "nothing calls the tick"

    # ...and the beat window is several laps, not one: a single late frame is
    # not evidence that a coroutine died.
    import re as _re
    lap = float(_re.search(r"OUTBOX_BEAT_TIMEOUT = (\d+(?:\.\d+)?)f;", src).group(1))
    assert lap >= 30.0, f"OUTBOX_BEAT_TIMEOUT={lap} is inside ordinary jitter"
def test_the_changelog_states_the_retry_budget():
    """r11. Two bullets promised the report is "retried until the server takes
    it". The budget is twenty attempts on a linear-ish backoff capped at four
    times the base minute — about seventy-five minutes — after which the entry
    is dropped. A player reading "until" would expect a report that survives an
    afternoon of server trouble; it does not."""
    changelog = (Path(__file__).parents[2] / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "retried until the server takes it" not in changelog, (
        "the unbounded promise is back"
    )
    assert "twenty attempts" in changelog, "the bound has to be stated in the bullet"
    # ...and twenty is the number the client actually uses
    src = API_CLIENT_CS.read_text(encoding="utf-8")
    assert "private const int OUTBOX_MAX_ATTEMPTS = 20;" in src, (
        "the changelog says twenty; the code has to be where that comes from"
    )


def test_the_crash_claim_names_what_it_depends_on():
    """r11. The enqueue said a crash "cannot lose the report". What carries a
    report across a crash is the queue FILE, and that write is best-effort —
    it used to swallow every failure, so the promise could be false for a whole
    session with nothing in the log. The write now says so once, which is what
    makes the sentence checkable."""
    src = API_CLIENT_CS.read_text(encoding="utf-8")
    assert "cannot lose the report" not in src, "the unconditional promise is back"
    assert "Surviving the process\n            // is the queue FILE's job" in src


def test_a_failed_queue_write_is_logged_once():
    """A permission or disk fault repeats on every write, so an unconditional
    warning would bury the round it is trying to explain — and no warning at
    all leaves the durability claim above unfalsifiable."""
    body = _cs_method_body(API_CLIENT_CS, "private static void PersistOutbox()")
    assert "catch { /* disk persistence is best-effort" not in body, (
        "the silent catch is back"
    )
    assert "_outboxPersistWarned" in body
    assert "if (!_outboxPersistWarned)" in body
    assert "_outboxPersistWarned = true;" in body
    assert "queue file unwritable" in body
    src = API_CLIENT_CS.read_text(encoding="utf-8")
    assert "private static bool _outboxPersistWarned;" in src


def test_the_outbox_is_written_by_replacement_not_by_truncation():
    """The whole crash guarantee is this file, so how it is written is part of
    the guarantee. WriteAllText opens the LIVE copy with Truncate: an
    interruption between the truncate and the last byte leaves an empty or
    half-written queue, losing exactly the reports the file exists to carry
    through a crash, in exactly the window where one is most likely -- it is
    rewritten on every enqueue and every dequeue. Written beside and moved
    over, an interruption leaves either the whole previous queue or the whole
    new one."""
    body = _cs_method_body(API_CLIENT_CS, "private static void PersistOutbox()")
    assert "File.WriteAllText(OutboxPath," not in body, (
        "the live queue file must never be opened for truncation"
    )
    assert "string tmp = OutboxTempPath;" in body
    assert "File.WriteAllText(tmp, body + trailer);" in body
    assert "File.Replace(tmp, OutboxPath, null);" in body
    assert "File.Move(tmp, OutboxPath);" in body
    # the whole file exists before anything replaces the old one
    assert body.index("File.WriteAllText(tmp") < body.index("File.Replace(tmp")
    assert body.index("File.WriteAllText(tmp") < body.index("File.Move(tmp")
    # and a write that fails is still said out loud once (r12 finding A4) --
    # the sentence about surviving a crash is worth nothing if the write
    # failing is silent
    assert "_outboxPersistWarned" in body


def test_an_empty_queue_is_written_rather_than_deleted():
    """r13 HIGH, the half that would have been a new bug. Once a stranded temp
    can be recovered, deleting the live file on an empty queue leaves that temp
    as the ONLY file on disk -- so the next launch would recover an older
    generation and re-send reports that had already landed. An empty generation
    is a write like any other and outranks it by the same rule.

    The one session that writes nothing is the one that never queued anything:
    no live file, no temp, nothing to say."""
    body = _cs_method_body(API_CLIENT_CS, "private static void PersistOutbox()")
    assert "File.Delete(OutboxPath)" not in body, (
        "deleting the live copy hands the next launch a stale temp with nothing to outrank it"
    )
    assert ("if (body.Length == 0 && !File.Exists(OutboxPath) && !File.Exists(tmp)) return;"
            in body), "a session that never queued anything should leave no file"
    assert body.index("if (body.Length == 0") < body.index("File.WriteAllText(tmp")


def test_a_complete_temp_is_recovered_because_it_is_the_newer_queue():
    """r13 HIGH. Write-beside-and-move closed the torn-file window and opened a
    smaller one: written in full, not yet renamed. In THAT window the temp is
    the newest queue -- it holds the enqueue that the live copy does not, and
    on a first creation there is no live copy at all -- and load read only the
    live copy, so the report the queue exists to carry was lost anyway.

    Load now weighs both names. Four states, each with an answer here:

      live newer / no temp   -> the ordinary case, live copy, temp deleted;
      temp newer and whole   -> recovered, and promoted so a second crash does
                                not have to recover it twice;
      temp torn              -> not a queue: no trailer, wrong line count or
                                wrong checksum, and it does not compete;
      live has no trailer    -> a queue from a build before this format;
                                readable, generation 0, and a trailered temp
                                outranks it.
    """
    load = _cs_method_body(API_CLIENT_CS, "private static void LoadOutbox()")
    assert "var live = ReadOutboxFile(OutboxPath, true);" in load, (
        "the live copy is read with the legacy allowance -- older builds wrote no trailer"
    )
    assert "var stranded = ReadOutboxFile(tmp, false);" in load, (
        "a temp with no trailer is a torn write, never a legacy queue"
    )
    # It is not a queue, so it never WINS -- but it is no longer deleted
    # unread either. Its lines parse independently and the only path that
    # reaches them is "nothing whole exists under either name", i.e. the
    # choice is between these reports and none.
    reader_all = API_CLIENT_CS.read_text(encoding="utf-8")
    assert "result.salvaged = true;" in reader_all, (
        "a trailerless temp is discarded rather than read as a last resort"
    )
    assert "if (!live.whole && !stranded.whole && !takeStranded" in load, (
        "salvage must be unreachable while any complete queue exists"
    )
    assert ("bool takeStranded = stranded.whole" in load
            and "stranded.generation > live.generation" in load), (
        "the temp has to WIN on generation, not merely exist"
    )
    assert "!live.whole || stranded.generation" in load, (
        "a first creation has no live copy for the temp to outrank"
    )
    # recovered means promoted, and a loser is removed rather than re-weighed
    assert load.index("takeStranded") < load.index("File.Replace(tmp, OutboxPath, null);")
    assert "try { File.Delete(tmp); } catch { }" in load
    assert "_outboxGeneration = Math.Max(live.readable ? live.generation : 0," in load, (
        "the counter has to carry across launches or an older file outranks a newer one"
    )
    # ...and ONLY from a file that was actually read. A queue file that exists
    # but could not be opened -- a scanner or a backup agent holding it, the
    # ordinary case -- used to read as generation 0 with no entries, exactly
    # like no file at all, so the session's first write stamped generation 1
    # over a real queue and destroyed it (r14 HIGH).
    assert "stranded.readable ? stranded.generation : 0);" in load, (
        "an unreadable temp still seeds the generation"
    )
    assert "_outboxGenerationUncertain = (live.present && !live.readable)" in load, (
        "'absent' and 'present but unreadable' are the same state again"
    )
    assert "!salvaging && !_outboxGenerationUncertain" in load, (
        "the temp is deleted on the strength of a read that failed"
    )
    persist = _cs_method_body(API_CLIENT_CS, "private static void PersistOutbox()")
    assert "if (_outboxGenerationUncertain)" in persist, (
        "a write can still land on a queue whose generation is unknown"
    )
    assert "var probe = ReadOutboxFile(OutboxPath, true);" in persist, (
        "the block must be re-derived per write, not latched -- a guard with no "
        "way back costs every report of the session"
    )
    assert "_outboxGenerationUncertain = false;" in persist, "the block never clears"

    reader = _cs_method_body(
        API_CLIENT_CS, "private static OutboxGeneration ReadOutboxFile(string path, bool allowLegacy)")
    assert "if (claimedCount != bodyLines) return result;" in reader, "truncation is not detected"
    assert "if (parts[3] != OutboxHash(body.ToString())) return result;" in reader, (
        "a torn body is not detected"
    )
    assert "else if (!allowLegacy)" in reader and "return result;" in reader

    persist = _cs_method_body(API_CLIENT_CS, "private static void PersistOutbox()")
    assert "_outboxGeneration++;" in persist
    assert persist.index("_outboxGeneration++;") < persist.index("File.WriteAllText(tmp"), (
        "the generation on the trailer has to be this write's, not the last one's"
    )
    assert "OutboxHash(body)" in persist


def test_the_outbox_trailer_is_a_marker_that_exists_for_no_other_purpose():
    """#306. The trailer decides whether a file on disk is a queue at all, so it
    must not be a string that could occur in the payload it terminates: every
    body line is `url<TAB>json`, and no url begins with a hash."""
    src = API_CLIENT_CS.read_text(encoding="utf-8")
    assert 'private const string OUTBOX_TRAILER = "#scr-outbox";' in src
    assert src.count('"#scr-outbox"') == 1, "the marker is spelled in more than one place"
    reader = _cs_method_body(
        API_CLIENT_CS, "private static OutboxGeneration ReadOutboxFile(string path, bool allowLegacy)")
    assert "StartsWith(OUTBOX_TRAILER, StringComparison.Ordinal)" in reader, (
        "the marker is matched by literal rather than through the constant"
    )
    assert "if (parts.Length != 4) return result;" in reader, (
        "a trailer that is not the four fields this writes is not a trailer"
    )
def test_a_deadlock_victim_is_re_run_instead_of_being_handed_to_the_player(_stub_the_gates):
    """r12 MEDIUM. This endpoint locks the two participants and then the
    series; tournament completion holds FOR SHARE on every bound bracket series
    through commit and then writes the podium players. A delayed report about a
    semifinal leaver and a completion of that bracket wait on each other and
    PostgreSQL aborts one with 40P01.

    Neither order is movable -- series-first here would put this endpoint in an
    ABBA against every other 1v1 writer, and the veto cannot enumerate its
    podium players in advance (#204). So the abort is what is handled: the
    transaction rolled back whole, nothing is half written, and the retry
    re-reads everything under fresh locks."""
    session = FakeSession(_players(), deadlocks=1)
    answer = _call(session)
    assert answer["status"] == "recorded"
    assert session.aborts_raised == 1
    assert session.attempts == 2, "the request is re-run, not resumed"
    assert session.rollbacks >= 1, "the aborted transaction has to be rolled back first"
    assert session.inserts == 1 and session.increments == 1, (
        "the retry must count exactly once"
    )
    assert session.commits == 1


def test_a_deadlock_that_repeats_answers_retryable_and_not_settled(_stub_the_gates):
    """The second abort means the counterparty is still holding. Waiting inside
    the request is worse for the caller than answering something its outbox
    brings back -- and the outbox drops a 4xx as settled and keeps everything
    else, so the answer has to be a 5xx. 503 says "not judged", which is what
    happened."""
    session = FakeSession(_players(), deadlocks=main.DC_DEADLOCK_ATTEMPTS)
    with pytest.raises(main.HTTPException) as caught:
        _call(session)
    assert caught.value.status_code == 503
    assert 500 <= caught.value.status_code < 600, (
        "a 4xx here would make the client drop a report nobody judged"
    )
    assert session.aborts_raised == main.DC_DEADLOCK_ATTEMPTS
    assert session.inserts == 0 and session.increments == 0 and session.commits == 0


def test_an_abort_that_is_not_a_deadlock_is_not_retried(_stub_the_gates):
    """The negative control. Retrying is only correct for the error whose whole
    meaning is "you were picked, try again"; a serialization failure, a
    constraint fault or a dead connection re-run blind would hide a real
    defect, so only 40P01 is caught."""
    session = FakeSession(_players(), deadlocks=1, lock_sqlstate="55P03")
    with pytest.raises(DBAPIError):
        _call(session)
    assert session.aborts_raised == 1, "one attempt, not two"
    assert session.inserts == 0


def test_the_prune_batch_commits_per_series_so_it_cannot_hold_the_chain():
    """r12 LOW, and the other half of the finding above. _prune_stale_series
    locks a series and then writes the players its bets belong to. Run as ONE
    transaction it held every series and every bettor it had touched so far, so
    a batch holding a stale S1 while it reached the bettors of S2 could wait on
    a player a DC report held while that report waited on S1. The row that
    closes the cycle is a bettor, which no lock ordering here enumerates; what
    removes it is the transaction ending at the item boundary (#204).

    Read structurally rather than by string: each loop commits, and nothing
    commits after the loops."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(main._prune_stale_series)))
    fn = tree.body[0]

    def _commits(node):
        return [n for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "commit"]

    loops = [n for n in fn.body if isinstance(n, ast.For)]
    assert len(loops) == 3, f"expected the three prune modes, found {len(loops)}"
    for index, loop in enumerate(loops):
        commits = _commits(loop)
        continues = [n for n in ast.walk(loop) if isinstance(n, ast.Continue)]
        assert commits, f"prune loop {index} never ends its transaction"
        assert len(commits) >= len(continues) + 1, (
            f"prune loop {index} has a path that skips an item while still "
            f"holding the locks it took for it"
        )

    tail = [n for n in fn.body if not isinstance(n, ast.For)]
    assert not any(_commits(n) for n in tail), (
        "a commit outside the loops is the batch transaction coming back"
    )


def test_the_unnamed_path_is_bound_by_liveness_and_play_too(_stub_the_gates):
    """r13 MEDIUM, the half that is easy to miss. Resolving "the pair's current
    series" answers WHICH series and nothing else -- not that anything happened
    in it, not that it is still live. If the two new terms lived only where a
    NAME is validated, a client that simply omitted the name would walk past
    both of them, and omitting a field is not a hurdle.

    So they are asked in the LOCKED re-check, which both paths reach, and the
    fake proves the runtime consults it: a series that fails there records
    nothing whichever way it was resolved."""
    locked = FakeSession(_players(), series_still_eligible=False)
    with pytest.raises(main.HTTPException) as caught:
        _call(locked)                       # no name: the unnamed resolution
    assert caught.value.status_code == 403
    assert locked.eligibility_locks == 1, "the unnamed path must reach the locked check"
    assert locked.inserts == 0 and locked.increments == 0

    ok = FakeSession(_players())
    assert _call(ok)["status"] == "recorded"
    assert "COALESCE(s.last_activity_at, s.created_at)" in ok.eligibility_sql, (
        "liveness is not asked on the path a client reaches by sending no name"
    )
    assert "COALESCE(s.live_p1_points, 0) + COALESCE(s.live_p2_points, 0)" in ok.eligibility_sql
    assert "EXISTS (SELECT 1 FROM matches m WHERE m.series_id = s.id)" in ok.eligibility_sql


def test_each_prune_mode_re_asks_its_whole_selection_under_its_own_lock():
    """r13 MEDIUM x2 and LOW. A locked re-check that asks a SUBSET of the
    selection is a re-check for the terms it kept and a stale snapshot for the
    rest. Mode 2 kept active/<2 and dropped the stall age and the unsettled-bet
    term, so a series snapshotted stalled at 1-0 and resumed at 1-1 while the
    loop worked still passed, and live wagers were refunded. Mode 1 had no
    locked re-check at all: it overwrote whatever state had arrived -- an admin
    reversal's invalidation reason included -- with `no_match_reported`, which
    the disconnect path treats as exempt.

    Each mode's re-check must therefore carry every term its selection did."""
    src = inspect.getsource(main._prune_stale_series)

    def slice_from(marker):
        start = src.index(marker)
        return src[start:src.index("first()", start)]

    mode_terms = {
        "_still_a = ": [
            "rs.status = 'active'",
            "rs.invalidated_at IS NULL",
            "rs.is_tournament = FALSE",
            "rs.created_at < NOW() - CAST(:cutoff AS interval)",
            "NOT EXISTS (SELECT 1 FROM matches m WHERE m.series_id = rs.id)",
        ],
        "_still_b = ": [
            "rs.status = 'active'",
            "rs.invalidated_at IS NULL",
            "rs.is_tournament = FALSE",
            "rs.p1_series_wins < 2 AND rs.p2_series_wins < 2",
            "EXISTS (SELECT 1 FROM matches m WHERE m.series_id = rs.id)",
            "b.settled_at IS NULL",
            "CAST(:stalled AS interval)",
        ],
    }
    for marker, terms in mode_terms.items():
        recheck = slice_from(marker)
        assert "FOR NO KEY UPDATE" in recheck, f"{marker} does not lock"
        for term in terms:
            assert term in recheck, f"{marker} re-check dropped: {term}"

    # ...and mode 1 takes that lock BEFORE it moves any gold, which is the
    # order the admin reversal takes on the same rows.
    tail = src[src.index("for sid, player1_id, player2_id, prune_reason in abandon_rows:"):]
    assert tail.index("_still_a = ") < tail.index("_refund_series_bets("), (
        "mode 1 refunds before it locks the series it is refunding"
    )


# ---------------------------------------------------------------------------
# r14 MEDIUM: the two failures the outbox repair introduced itself.
# ---------------------------------------------------------------------------

def test_the_heartbeat_records_progress_and_not_the_start_of_a_lap():
    """A lap contains a whole pass, and every due entry can spend a full
    request timeout — so a queue with a few due entries outlives the 45s
    ownership window while behaving normally. A beat written once at the top
    of the lap therefore reads as "no supervisor" mid-pass, the tick starts a
    second one, and the first finishes its pass concurrently over the same
    list: both post the same entries and both spend the same attempt budget.

    Asserted by POSITION, not presence. The beat existing somewhere in the
    method is what the broken version had."""
    sup = _cs_method_body(
        API_CLIENT_CS, "private static IEnumerator OutboxSupervisor(int generation)")
    drive = sup.index("while (stack.Count > 0)")
    top = sup.index("IEnumerator top = stack[stack.Count - 1];")
    inner = sup[drive:top]
    assert "_outboxLoopBeatRt = Time.realtimeSinceStartup;" in inner, (
        "the beat is not refreshed inside the drive loop; a long pass still "
        "looks like a dead supervisor"
    )
    assert "if (_outboxLoopGeneration != generation) yield break;" in inner, (
        "a superseded supervisor still finishes the pass it is holding"
    )
    # ...and it is still checked once per lap as well, so a supervisor that is
    # sitting in the 10s wait with nothing to do also stops.
    lap = sup[:drive]
    assert "if (_outboxLoopGeneration != generation) yield break;" in lap
    assert sup.count("_outboxLoopBeatRt = Time.realtimeSinceStartup;") == 2, (
        "the beat should be written at the lap and at each drive step, and "
        "nowhere else"
    )


def test_the_queue_is_read_from_disk_once_per_process():
    """`_pendingReports` is `static readonly`; Plugin's `startupComplete` is an
    INSTANCE field. The host respawn this class now survives therefore re-runs
    DoInitialize -> Initialize -> LoadOutbox, and a second read appended the
    previous session's reports to a list that already held them. Every respawn
    multiplied the queue, and the ownership repair is what makes the duplicates
    actually get sent."""
    api = API_CLIENT_CS.read_text(encoding="utf-8")
    assert "private static readonly List<PendingReport> _pendingReports" in api, (
        "the premise: the queue outlives the behaviour"
    )
    plugin_src = (PLUGIN / "Plugin.cs").read_text(encoding="utf-8")
    assert "private bool startupComplete = false;" in plugin_src, (
        "the other half of the premise: the init latch does NOT outlive it"
    )

    load = _cs_method_body(API_CLIENT_CS, "private static void LoadOutbox()")
    guard = load[:load.index("try")]
    assert "if (_outboxLoaded)" in guard and "return;" in guard, (
        "a second LoadOutbox still re-reads the disk"
    )
    assert "_outboxLoaded = true;" in guard, "the latch is never set"

    # ...and the merge is by identity too, so no second reader can multiply the
    # queue even if one is added later.
    assert "if (OutboxAlreadyQueued(entry.url, entry.json)) { duplicates++; continue; }" in load, (
        "entries from disk are added without checking whether they are held"
    )
    ident = _cs_method_body(
        API_CLIENT_CS, "private static bool OutboxAlreadyQueued(string url, string json)")
    assert "p.url == url && p.json == json" in ident, (
        "identity must match what RemovePendingReport matches on, or the two "
        "disagree about what the same report is"
    )
    remove = _cs_method_body(API_CLIENT_CS, "private static void RemovePendingReport(string url, string json)")
    assert "pending.url != url || pending.json != json" in remove, (
        "the removal side changed its idea of identity; the merge must follow"
    )
