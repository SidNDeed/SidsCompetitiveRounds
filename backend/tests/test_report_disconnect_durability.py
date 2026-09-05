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
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import main


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


class FakeSession:
    """Every statement report_disconnect can issue, in Python.

    insert_wins is the concurrency knob: False is the replay whose
    ON CONFLICT DO NOTHING matched an existing row — the case a lost response
    and its outbox retry produce.
    """

    def __init__(self, players, event_exists=False, insert_wins=True, stored_count=4,
                 named_series=None, series_fresh=True, series_still_eligible=True):
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
            self.lock_order.append(str((params or {}).get("pid")))
            return _Result([(1,)])
        if sql.startswith("SELECT 1 FROM ranked_series"):
            assert "CAST(:sid AS uuid)" in sql, "the id bind must be typed (#448)"
            if "FOR NO KEY UPDATE" in sql:
                self.eligibility_locks += 1
                self.eligibility_sql = sql
                self.lock_order.append("series")
                return _Result([(1,)] if self.series_still_eligible else [])
            assert "INTERVAL '7 days'" in sql, "the age bound must be a literal interval, not a bind (#448)"
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
    """The whole point. Both requests clear the dc_events SELECT — that is
    what "concurrent" means here — and only one row lands. The loser must add
    nothing: an unconditional increment would take a leave-% denominator up by
    one for a disconnect that happened once."""
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
    assert "player1_id = :rp AND player2_id = :dp" in sql
    assert "player1_id = :dp AND player2_id = :rp" in sql
    assert "invalidated_at IS NULL OR invalidation_reason = :exempt" in sql
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


def test_a_named_series_must_be_this_pairs():
    """A named series is checked against the database, never taken as given:
    its two participants have to be exactly this reporter and this leaver."""
    session = FakeSession(_players(), named_series=_series_row(player2=STRANGER))
    with pytest.raises(main.HTTPException) as caught:
        _call(session, str(NAMED_SERIES))
    assert caught.value.status_code == 403
    assert session.inserts == 0 and session.increments == 0


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


def test_an_unknown_series_is_refused():
    session = FakeSession(_players(), named_series=None)
    with pytest.raises(main.HTTPException) as caught:
        _call(session, str(NAMED_SERIES))
    assert caught.value.status_code == 403
    assert session.inserts == 0


def test_a_long_finished_series_is_refused_and_the_bound_is_asked_in_sql():
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


def test_the_age_bound_binds_a_series_that_never_completes():
    """The fake answers the freshness query with a boolean, so the test above
    passes whatever the SQL actually asks. Both terms matter and one of them is
    new: a series the janitor abandons keeps completed_at NULL forever, so the
    completed_at term admits it at any age and created_at is what bounds it —
    which is exactly the row the reason-scoped exemption above now accepts."""
    sql = MAIN_PY.read_text(encoding="utf-8")
    start = sql.index("SELECT 1 FROM ranked_series WHERE id = CAST(:sid AS uuid)")
    query = sql[start:start + 400]
    assert "created_at >= NOW() - INTERVAL '7 days'" in query, (
        "an abandoned series has no completed_at, so nothing else bounds its age"
    )
    assert "completed_at IS NULL OR completed_at >= NOW() - INTERVAL '7 days'" in query
    # asked of the database clock, never compared to a python now
    assert "NOW()" in query and "datetime.now" not in query


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
    """The braces-matched body of one C# method, so an assertion about a
    method cannot be satisfied by a match somewhere else in the file."""
    src = path.read_text(encoding="utf-8")
    start = src.index(signature)
    open_brace = src.index("{", start)
    depth = 0
    for i in range(open_brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[open_brace : i + 1]
    raise AssertionError(f"unbalanced braces after {signature}")


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
    assert "ActiveRankedSeriesRoom" in fence
    assert 'return string.Equals(ActiveRankedSeriesRoom, here, StringComparison.Ordinal) ? sid : "";' in fence
    # Every publish of the id records the room it was published for, and every
    # clear clears both — otherwise the fence compares against a stale room
    # name. Asserted per WRITE SITE rather than by counting occurrences, so the
    # field declarations cannot make the totals agree by accident.
    sites = 0
    for src in (api, gsw, (PLUGIN / "Plugin.cs").read_text(encoding="utf-8")):
        lines = src.splitlines()
        for i, ln in enumerate(lines):
            if "ActiveRankedSeriesId = " not in ln:
                continue
            if "public static" in ln:      # the declaration, not a write
                continue
            near = ln + (lines[i + 1] if i + 1 < len(lines) else "")
            assert "ActiveRankedSeriesRoom = " in near, (
                f"a write to the series id does not set its room: {ln.strip()}"
            )
            sites += 1
    # 3 publishes (preflight, queue both_ready, queue poll) and 4 clears
    # (two in ApiClient, the game-report boundary, the room-leave edge).
    assert sites == 7, f"expected 3 publishes and 4 clears, found {sites}"


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
    """Unity stops a coroutine that lets an exception out, and
    _outboxLoopStarted is written once. Before the supervisor, one throw
    ended every retry for the rest of the session — including reports already
    written to disk — with nothing but the exception in the log."""
    sup = _cs_method_body(API_CLIENT_CS, "private static IEnumerator OutboxSupervisor()")
    assert "pass.MoveNext()" in sup, "the pass must be driven by hand to be catchable"
    assert "catch (Exception ex)" in sup
    assert "finally { _outboxLoopStarted = false; }" in sup
    src = API_CLIENT_CS.read_text(encoding="utf-8")
    assert src.count("_outboxLoopStarted = false") == 1
    assert "StartCoroutine(OutboxSupervisor())" in src


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


def test_a_failed_start_does_not_latch_the_outbox_off():
    """StartCoroutine throws when the host object is inactive or being
    destroyed, and both callers swallow it. Setting the guard flag first
    latched "a supervisor exists" with none running — and the flag is the only
    guard, so nothing could start one afterwards. Set after the call returns, a
    failed start leaves the flag false and the next enqueue re-arms."""
    body = _cs_method_body(API_CLIENT_CS, "private static void EnsureOutboxLoop()")
    assert "StartCoroutine(OutboxSupervisor());" in body
    assert "_outboxLoopStarted = true;" in body
    assert body.index("StartCoroutine(OutboxSupervisor());") < body.index("_outboxLoopStarted = true;"), (
        "the guard latches before the coroutine it guards exists"
    )


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
