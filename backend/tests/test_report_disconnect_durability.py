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
import os
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

    def scalars(self):
        return _Scalars([r[0] if isinstance(r, tuple) else r for r in self._rows])


class _Scalars:
    def __init__(self, values):
        self._values = list(values)

    def all(self):
        return list(self._values)


class _ScriptedAbort(Exception):
    """Stands in for asyncpg's error object: SQLAlchemy wraps it and the
    handler reads its sqlstate, which is the only field that decides."""

    def __init__(self, sqlstate):
        super().__init__("scripted %s" % sqlstate)
        self.sqlstate = sqlstate


class SeriesFixture:
    """What the database would say about the named sitting.

    One field per conjunct of the eligibility predicate. `evaluate` applies a
    field's disqualification ONLY IF the clause that reads it is present in the
    SQL -- so a conjunct deleted from main.py stops disqualifying anything, a
    fixture built to be refused is accepted, and the test asserting the refusal
    fails. That is the negative control a boolean knob cannot provide: a knob
    answers the question the fake was told to answer, whatever the statement
    actually asks.
    """

    def __init__(self, grant_present=True, grant_is_newest=True,
                 any_grant_for_pair=True, completed=False, is_most_recent=True,
                 fresh=True, live_points=10, has_match=True,
                 accused_attested=False, accused_armed=False):
        # AUTHORITY: the server put this pair into this sitting...
        self.grant_present = grant_present
        # ...and has not since put them into a newer one.
        self.grant_is_newest = grant_is_newest
        # Whether the pair has ANY grant, which is what gates the legacy arm.
        self.any_grant_for_pair = any_grant_for_pair
        # The legacy arm's own row-shape terms.
        self.completed = completed
        self.is_most_recent = is_most_recent
        self.fresh = fresh
        # EVIDENCE. Two arms since M4: a committed match row, or the points
        # threshold AND corroboration from the accused -- required only of an
        # account that has provably run a ticket-auth client and can therefore
        # produce it.
        self.live_points = live_points
        self.has_match = has_match
        # A verified attestation by the ACCUSED for this sitting. There is no
        # unverified kind: an unbound row is one the reporter could have
        # written, so none is recorded.
        self.accused_attested = accused_attested
        # players.steam_auth_seen_at IS NOT NULL for the accused.
        self.accused_armed = accused_armed

    def evaluate(self, sql, min_points, require_verified_seat=False):
        """True if this fixture satisfies the predicate AS WRITTEN in `sql`."""
        arms = []
        if "FROM series_dc_grants g" in sql:
            arms.append(self.grant_present
                        and (self.grant_is_newest or "g2.last_seen_at" not in sql))
        if "ORDER BY s2.created_at DESC LIMIT 1" in sql:
            legacy = (not self.any_grant_for_pair) or "series_dc_grants g3" not in sql
            legacy = legacy and (not self.completed or self.is_most_recent)
            if "CAST(:live_window AS interval)" in sql:
                legacy = legacy and self.fresh
            arms.append(legacy)
        if not arms:
            # Neither arm present at all: the predicate no longer decides
            # anything about which sitting may be named.
            return True
        if not any(arms):
            return False

        # EVIDENCE, arm by arm, each applied only if its own clause is present.
        # An empty list means the statement asks nothing about evidence at all —
        # which is exactly what the refusal diagnostic is — so it disqualifies
        # nothing rather than defaulting either way.
        ev = []
        if "FROM matches m" in sql:
            ev.append(self.has_match)
        if "live_p1_points" in sql:
            # Read the THRESHOLD out of the statement, do not assume it. A
            # model that carries its own copy of the number cannot notice the
            # statement's copy being changed -- which is how a mutant that
            # replaced `:min_points` with a literal 0 walked past every gate.
            if ">= :min_points" in sql:
                play = self.live_points >= min_points
            else:
                bound = re.search(r"points, 0\) >= (\d+)", sql)
                play = self.live_points >= int(bound.group(1)) if bound else True
            if "sp.player_id = :dp" in sql:
                corroborated = self.accused_attested
                if "NOT CAST(:require_verified_seat AS boolean)" in sql                         and not require_verified_seat:
                    # The fallback clause. Without the arming sub-clause it is
                    # unconditional, i.e. the fence is gone entirely -- which is
                    # a state a mutation can produce and this must model.
                    if "steam_auth_seen_at" in sql:
                        corroborated = corroborated or not self.accused_armed
                    else:
                        corroborated = True
                play = play and corroborated
            ev.append(play)
        if ev and not any(ev):
            return False
        return True


class FakeSession:
    """Every statement report_disconnect can issue, in Python.

    insert_wins is the concurrency knob: False is the replay whose
    ON CONFLICT DO NOTHING matched an existing row — the case a lost response
    and its outbox retry produce.
    """

    def __init__(self, players, event_exists=False, insert_wins=True, stored_count=4,
                 named_series=None, series_fresh=True, series_still_eligible=True,
                 deadlocks=0, lock_sqlstate="40P01", grant_series_id=None,
                 bracket_states=(), series_fixture=None, authority_ok=False,
                 idle=False):
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
        # Whether the AUTHORITY arms alone would have passed. Only the refusal
        # diagnostic asks this, and only after the full predicate has already
        # said no, so it decides one thing: whether the refusal is settled (403)
        # or not-yet (503). Defaults False because every scenario written before
        # the split -- a superseded sitting, an invalidated series, a decided
        # bracket -- is an authority failure, and those must stay settled.
        self.authority_ok = authority_ok
        # Whether the sitting has been idle past the live window. Only the
        # diagnostic asks, and it decides whether an evidence failure is worth
        # retrying or is finally settled.
        self.idle = idle
        self.authority_diagnostics = 0
        self.authority_sql = None
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
        # r14 MEDIUM 3/6. The grant is the authority the predicate reads, and
        # the bracket rows are the lifecycle it re-asks while holding them.
        self.grant_series_id = grant_series_id
        self.bracket_states = tuple(bracket_states or ())
        self.series_fixture = series_fixture
        self.grant_lookups = 0
        self.bracket_locks = 0
        self.spent_marks = 0

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
        if sql.startswith("SELECT series_id FROM series_dc_grants"):
            # The resolver for the UNNAMED path. It must ask the same question
            # the predicate's supersession term asks, in the same total order:
            # both directions of a grant are stamped by one statement and share
            # a timestamp, so a "newest" that can tie is not an ordering.
            assert "ORDER BY last_seen_at DESC, series_id DESC" in sql, (
                "the resolver breaks ties differently from the predicate, so it "
                "can hand the judge a sitting the judge will then refuse"
            )
            self.grant_lookups += 1
            return _Result([(self.grant_series_id,)] if self.grant_series_id else [])
        if sql.startswith("SELECT tm.status FROM tournament_matches"):
            # The bracket lifecycle, re-asked while holding the rows.
            #
            # Keyed on the statement's own PREFIX, not on a substring: the
            # eligibility statement now contains a NOT EXISTS over this same
            # table, so `"FROM tournament_matches" in sql` routed the
            # eligibility read here and asserted a FOR UPDATE it will never
            # have.
            assert "FOR UPDATE" in sql, (
                "the locked re-ask does not hold the rows it reads, so a "
                "terminalisation committing in the window is not seen"
            )
            assert "LIMIT" not in sql, (
                "the locked pass must read EVERY bracket row for the series, "
                "not a sample -- comparing a different subset than the unlocked "
                "term read is not a re-ask of the same question (#205)"
            )
            self.bracket_locks += 1
            self.lock_order.append("bracket")
            return _Result([(st,) for st in self.bracket_states])
        if sql.startswith("SELECT 1 AS authority_only"):
            # The refusal diagnostic. Routed on a label that exists for no other
            # purpose (#306): this statement is the shared predicate minus its
            # evidence arm, so every other way of recognising it -- "no matches
            # arm", "no series_progress" -- is a shape a MUTATION of the shared
            # fragments could give one of the real asks, and the fake would then
            # answer the wrong question about the wrong statement.
            assert "FOR NO KEY UPDATE" not in sql, (
                "the diagnostic must not take a lock: it runs after the real "
                "ask has already failed and only picks the status code"
            )
            self.authority_diagnostics += 1
            self.authority_sql = sql
            # Whether the statement actually COMPUTES idleness, rather than
            # merely containing the word. A mutant that replaced the expression
            # with `false AS idle` kept the word and kept every gate green.
            computes_idle = ("COALESCE(s.last_activity_at, s.created_at)" in sql
                             and "AS idle" in sql)
            ok = (self.series_fixture.evaluate(
                      sql, main.DC_MIN_LIVE_POINTS,
                      main._dc_require_verified_seat())
                  if self.series_fixture is not None else self.authority_ok)
            return _Result([(1, self.idle and computes_idle)] if ok else [])
        if sql.startswith("SELECT 1 FROM ranked_series"):
            assert "CAST(:sid AS uuid)" in sql, "the id bind must be typed (#448)"
            if "FOR NO KEY UPDATE" in sql:
                self.eligibility_locks += 1
                self.eligibility_sql = sql
                self.lock_order.append("series")
                if self.series_fixture is not None:
                    return _Result([(1,)] if self.series_fixture.evaluate(
                        sql, main.DC_MIN_LIVE_POINTS,
                        main._dc_require_verified_seat()) else [])
                return _Result([(1,)] if self.series_still_eligible else [])
            assert "CAST(:live_window AS interval)" in sql, (
                "an interval bind has to be CAST, never concatenated (#448)"
            )
            self.freshness_checks += 1
            if self.series_fixture is not None:
                return _Result([(1,)] if self.series_fixture.evaluate(
                    sql, main.DC_MIN_LIVE_POINTS,
                    main._dc_require_verified_seat()) else [])
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
        if sql.startswith("UPDATE series_dc_grants"):
            assert "spent_at IS NULL" in sql, (
                "the mark is not first-write-wins, so a replay can move a "
                "timestamp that already means something"
            )
            assert ":rp" in sql and ":dp" not in sql, (
                "the grant marked spent must be the REPORTER's own direction -- "
                "that is the row the predicate read"
            )
            self.spent_marks += 1
            return _Result([])
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
                reason=None, is_tournament=False):
    return SimpleNamespace(id=sid, player1_id=player1, player2_id=player2,
                           invalidated_at=invalidated, invalidation_reason=reason,
                           is_tournament=is_tournament)


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
    # Read from the ASSEMBLED predicate rather than from a text slice of
    # main.py. The two askers now share one definition, so the value below is
    # what actually runs in both of them -- a source slice would be asserting
    # about whichever of the two happened to appear first in the file.
    # Whitespace-normalised: the fragments are line-wrapped for reading, so a
    # term that spans two concatenated string literals carries the padding of
    # the second one. Asserting against the raw text would be asserting about
    # the indentation.
    def _norm(fragment):
        return " ".join(fragment.split())

    query = _norm(main._DC_ELIGIBLE_TERMS)

    # AUTHORITY replaced "uncompleted, or the pair's most recent series" as the
    # primary term (r14 MEDIUM 3): recency is not authority, and a pair that
    # meets, leaves and meets again satisfies the old test about either
    # sitting. The old shape survives ONLY as the compatibility arm, reachable
    # for a pair the server holds no grant for at all.
    assert "FROM series_dc_grants g" in query, (
        "the predicate no longer asks which sitting the server put this pair in"
    )
    assert "(g2.last_seen_at, g2.series_id) > (g.last_seen_at, g.series_id)" in query, (
        "supersession compares a TUPLE because last_seen_at alone is not unique "
        "within a pair -- the backfill stamps each sitting with its own last "
        "activity and NOW() is the transaction timestamp -- and on a tie 'no "
        "strictly newer grant exists' is true of both rows, so two sittings are "
        "nameable at once"
    )
    assert "NOT EXISTS (SELECT 1 FROM series_dc_grants g3" in query, (
        "the compatibility arm is not gated on the pair having no grant, so it "
        "is reachable for pairs the authority record covers"
    )
    assert "ORDER BY s2.created_at DESC LIMIT 1" in query, (
        "the pair's most recent series is the one completed series a name reaches"
    )
    assert "COALESCE(s.last_activity_at, s.created_at)" in query, (
        "liveness is asked of the column the server stamps, not of a null"
    )
    assert "CAST(:live_window AS interval)" in query, (
        "an interval bind has to be CAST, never concatenated (#448)"
    )

    # ...and the delivery clock is on the COMPATIBILITY arm only. A grant ends
    # when the server observes the sitting end, not when a client failed to get
    # its report delivered quickly enough (r14 MEDIUM 6).
    grant_arm = _norm(main._DC_GRANT_TERM)
    assert "live_window" not in grant_arm, (
        "the authority arm has a delivery-time fence again: a report queued "
        "during an outage and delivered on the next launch is refused, which "
        "is the case the outbox exists to make survivable"
    )
    assert "live_window" in _norm(main._DC_LEGACY_TERM), (
        "the compatibility arm has no authority record to lean on, so recency "
        "is all it has -- removing its bound makes it unbounded"
    )

    # BRACKET: a forfeit terminalises the match and deliberately leaves the
    # series active, so no row-shape term could see the match was decided.
    assert "FROM tournament_matches tm" in query and "tm.status IN" in query, (
        "a decided tournament match can still receive a post-result accusation"
    )
    assert "tm.status NOT IN" not in query, (
        "the bracket term enumerates OPEN states again, so a state nobody "
        "listed reads as decided and its reports are refused permanently"
    )

    assert "COALESCE(s.live_p1_points, 0) + COALESCE(s.live_p2_points, 0)" in query
    assert "EXISTS (SELECT 1 FROM matches m WHERE m.series_id = s.id)" in query
    assert "INTERVAL '7 days'" not in query, (
        "the created_at/completed_at week is retired; liveness replaced it"
    )
    # asked of the database clock, never compared to a python now
    assert "NOW()" in query and "datetime.now" not in query


def test_both_askers_are_built_from_the_one_definition():
    """The reason the fragments exist at all.

    The unlocked validation of a named series and the locked re-ask that holds
    its answer to the insert are two statements asking the same question, and
    they had already drifted apart once. Two clusters of this review were each
    rewriting one of them; applied independently, the second would have
    silently overwritten the first. The test above reads the assembled value,
    which proves the DEFINITION is right and nothing about who uses it.
    """
    code = MAIN_PY.read_text(encoding="utf-8")
    uses = code.count('"   AND " + _DC_ELIGIBLE_TERMS +')
    assert uses == 2, (
        f"{uses} askers build from the shared predicate, not 2 -- a hand-written "
        "copy is exactly the drift the fragments were extracted to end"
    )


def test_the_two_places_that_name_a_decided_bracket_state_agree():
    """One fact, two readers: the unlocked NOT EXISTS spells the decided states
    as a SQL literal, the locked pass compares against the python tuple. A state
    added to one and not the other makes the locked re-ask answer a different
    question than the term it exists to re-ask."""
    # Compared as SETS, not as a joined substring: a substring test passes on
    # a PREFIX of the right answer, so dropping the last state from the tuple
    # left this assertion green while the two readers had genuinely diverged.
    named = frozenset(re.findall(r"'([a-z_]+)'", main._DC_BRACKET_TERM))
    tupled = frozenset(main._TM_DECIDED_STATES)
    assert named, "the bracket term names no states at all"
    assert named == tupled, (
        "the unlocked term and the locked re-ask disagree about which states "
        f"are decided: SQL says {sorted(named)}, the tuple says "
        f"{sorted(tupled)}"
    )


def test_the_decided_states_are_the_ones_the_rest_of_the_server_already_names():
    """Not a list I chose -- the list main.py already had.

    Four other statements enumerate the decided bracket states, and a fifth
    that quietly disagreed would mean the DC path calls a match open that the
    room binding calls finished. The sweep is over the OPERATION (any
    tm.status enumeration), not over a line, so a fork shows up as a count that
    moved (#432).
    """
    src = MAIN_PY.read_text(encoding="utf-8")
    # Adjacent python string literals are glued so a SQL list wrapped across
    # two of them is read as one set rather than as two truncated ones.
    glued = re.sub(r'"\s*\n\s*"', "", src)
    groups = re.findall(r"tm\.status\s+(?:NOT\s+)?IN\s*\(([^)]*)\)", glued)
    sets = [frozenset(re.findall(r"'([a-z_]+)'", g)) for g in groups]
    assert len(sets) >= 6, (
        f"the sweep found only {len(sets)} bracket-status enumerations; a "
        "regex that stops matching is a check that cannot fail (#441)"
    )
    canonical = frozenset(main._TM_DECIDED_STATES)
    assert canonical in sets, (
        f"no statement in main.py enumerates {sorted(canonical)}; the DC path "
        "is asking a question the rest of the server does not ask"
    )
    # A count threshold would let a single forked site hide under the others.
    # The claim is sharper than that: any statement asking the FULL decided
    # question must ask it identically. Narrower sweeps that deliberately ask
    # less -- the forfeit-only repair pass, the ready/scheduled actionable-now
    # lookups -- do not contain both anchors and are left alone.
    forks = sorted(sorted(s) for s in sets
                   if {"completed", "forfeit"} <= s and s != canonical)
    assert not forks, (
        f"these statements enumerate the decided states differently: {forks}; "
        "the DC path and the rest of the server disagree about which matches "
        "are already finished"
    )


def test_the_column_default_is_never_a_decided_state():
    """The specific error this list was shipped with.

    'pending' is what TournamentMatch.status defaults to, so every bracket row
    exists in that state before anything happens to it. The first draft
    enumerated OPEN states and forgot it, which made a leave in a match that
    had not been readied yet a permanent 403 -- and a permanent refusal is a
    report the client deletes rather than retries. Read from models.py, not
    from my memory of it.
    """
    models = (MAIN_PY.parent / "models.py").read_text(encoding="utf-8")
    start = models.index("class TournamentMatch")
    block = models[start:start + 4000]
    # Line-wise, not a paren-balanced regex: the column reads
    # `Column(String(16), nullable=False, default="pending")` and a `[^)]*`
    # cannot cross String(16)'s own closing paren -- which is how the first
    # draft of this test matched nothing and asserted its way to red.
    line = next((ln for ln in block.splitlines()
                 if re.match(r"\s*status\s*=\s*Column\(", ln)), None)
    assert line, "TournamentMatch declares no status column to read a default from"
    found = re.search(r'default="([a-z_]+)"', line)
    assert found, "TournamentMatch.status has no literal default to check against"
    assert found.group(1) not in main._TM_DECIDED_STATES, (
        f"the bracket column defaults to {found.group(1)!r}, which this list "
        "calls decided -- every match refuses reports before it is readied"
    )


def test_a_bracket_state_nobody_listed_is_read_as_open_not_decided():
    """The failure DIRECTION, which is the reason for the polarity.

    A state added after this code was written is unhandled either way. Read as
    decided, every report against it is refused permanently and deleted by the
    client -- unrecoverable. Read as open, the report still has to pass the
    authority, evidence and dedup gates, and a wrong acceptance is visible and
    reversible on the server. #276.
    """
    session = FakeSession(
        _players(), named_series=_series_row(is_tournament=True),
        bracket_states=("a_state_from_2027",))
    assert _call(session, str(NAMED_SERIES))["status"] == "recorded"
    assert session.bracket_locks == 1


def test_a_pending_bracket_row_does_not_refuse_the_report():
    """The prod-measured case: 'pending' rows exist on the primary right now."""
    session = FakeSession(
        _players(), named_series=_series_row(is_tournament=True),
        bracket_states=("pending",))
    assert _call(session, str(NAMED_SERIES))["status"] == "recorded"


def test_every_decided_state_refuses_the_report():
    """...and the control for the three above: each decided state, one at a
    time, so a list that is right in aggregate but wrong in one entry cannot
    hide behind the others."""
    # A loop over the tuple under test cannot notice the tuple shrinking, so
    # the floor is asserted before the loop: an empty or truncated list would
    # otherwise make this test pass by visiting nothing.
    assert len(main._TM_DECIDED_STATES) >= 4, (
        f"only {len(main._TM_DECIDED_STATES)} decided states; this loop proves "
        "nothing about the ones that were removed"
    )
    for state in main._TM_DECIDED_STATES:
        session = FakeSession(
            _players(), named_series=_series_row(is_tournament=True),
            bracket_states=(state,))
        with pytest.raises(main.HTTPException) as caught:
            _call(session, str(NAMED_SERIES))
        assert caught.value.status_code == 403, state
        assert session.inserts == 0, state


def test_the_backfill_selects_exactly_what_the_rule_would_have():
    """294 mints a grant for every sitting that was live at deploy time, and a
    grant carries NO clock -- so anything it selects that the rule would not
    have becomes permanently nameable rather than expiring.

    Two properties, one per way the selection can be wrong:

      * the freshness window is the compatibility arm's own. Wider does not
        merely add rows, it converts sittings the old rule had already stopped
        accepting reports for into sittings that accept them indefinitely, and
        it must be identical in BOTH directions or a pair ends up reportable
        from one seat and not the other;
      * the decided-bracket exclusion is the same list the predicate decides
        on, in every direction.
    """
    sql = (MAIN_PY.parent.parent / "sql" / "294_backfill_series_dc_grants.sql"
           ).read_text(encoding="utf-8")
    windows = set(re.findall(r"NOW\(\) - INTERVAL '(\d+) (hours|days|minutes)'", sql))
    assert len(windows) == 1, (
        f"294 uses {len(windows)} different freshness windows: {sorted(windows)}; "
        "its two INSERTs must select the same rows or one direction of a grant "
        "is written without the other"
    )
    amount, unit = windows.pop()
    seconds = int(amount) * {"minutes": 60, "hours": 3600, "days": 86400}[unit]
    assert seconds == main.DC_LIVE_WINDOW_SECONDS, (
        f"294 backfills {amount} {unit} ({seconds}s) but the compatibility arm "
        f"only reaches {main.DC_LIVE_WINDOW_SECONDS}s; the difference is a set "
        "of dead sittings made permanently nameable"
    )

    # ...and EVERY direction excludes decided brackets by the same list.
    #
    # Parsed per statement and compared as sets. 294 carries the exclusion
    # twice, one INSERT per direction of the grant, so a per-state substring
    # check passes on a state deleted from ONE of them -- and the two
    # directions then select different rows, which leaves a pair reportable
    # from one seat and not the other.
    lists = [frozenset(re.findall(r"'([a-z_]+)'", g))
             for g in re.findall(r"tm\.status\s+IN\s*\(([^)]*)\)", sql)]
    assert len(lists) == 2, (
        f"294 has {len(lists)} bracket exclusions, expected one per direction; "
        "a parse that stops matching is a check that cannot fail (#441)"
    )
    for got in lists:
        assert got == frozenset(main._TM_DECIDED_STATES), (
            f"294 excludes {sorted(got)} but the rule decides on "
            f"{sorted(main._TM_DECIDED_STATES)}; the backfill and the predicate "
            "disagree about which matches are already finished"
        )
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
    assert "H2HRules.RoomSession.SeriesHere(roomSession" in fence, (
        "r13 HIGH: the fence asks the occupancy rule, not a room name"
    )
    assert "OpponentInRoomOrEmpty());" in fence, (
        "the fence has to hand the rule the pairing in the room, not just a name"
    )
    # The occupancy counter is no longer passed alongside the record: it is a
    # FIELD of the session the rule is handed, so the two cannot be supplied
    # from different places. That is a stronger statement than the argument
    # order this used to assert - there is no longer a call site that could
    # pass a record and a counter that do not belong together.
    assert "roomSession" in fence
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
    assert "get { return roomSession.Bound.HasValue" in api[decl:decl + 400], (
        "the id is not derived from the binding it is supposed to describe"
    )
    publish = _cs_method_body(API_CLIENT_CS, "public static void PublishActiveSeries(string seriesId, string room)")
    clear = _cs_method_body(API_CLIENT_CS, "public static void ClearActiveSeries()")
    assert "H2HRules.RoomSession.OnSeriesPublished(ref roomSession" in publish, (
        "publication no longer goes through the transition that decides the stamp"
    )
    assert "H2HRules.RoomSession.OnSeriesEnded(ref roomSession);" in clear, (
        "clearing does not clear the record"
    )

    # ...and the callers are still the sites they were: 3 publishes (preflight,
    # queue both_ready, queue poll) and 4 clears (two in ApiClient at the
    # game-report boundary, the POLLED room exit in GameStateWatcher, and the
    # RELIABLE room-leave edge in Plugin). The two room edges reach the clear
    # through their own transitions, which is why this census counts those
    # entry points and not just one method name.
    sites = []
    for name, src in (("ApiClient.cs", api), ("GameStateWatcher.cs", gsw),
                      ("Plugin.cs", (PLUGIN / "Plugin.cs").read_text(encoding="utf-8"))):
        for ln in src.splitlines():
            stripped = ln.strip()
            if stripped.startswith("public static void PublishActiveSeries"):
                continue
            if stripped.startswith("public static void ClearActiveSeries"):
                continue
            # ...and the two room-edge entry points' own declarations.
            if stripped.startswith("internal static void OnRoomExitPolled"):
                continue
            if stripped.startswith("internal static void OnRoomLeftReliableEdge"):
                continue
            if "PublishActiveSeries(" in ln:
                sites.append((name, "publish"))
            elif "ClearActiveSeries()" in ln:
                sites.append((name, "clear"))
            # The two ROOM EDGES clear the binding through their own
            # transitions rather than through ClearActiveSeries, so that the
            # clear travels with the counter bumps it has to be ordered
            # against. They are still clear sites and this census still owns
            # them - counting only one spelling is how a site goes missing.
            elif "OnRoomExitPolled()" in ln:
                sites.append((name, "clear"))
            elif "OnRoomLeftReliableEdge()" in ln:
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


READ_OUTBOX_SIG = ("private static OutboxGeneration ReadOutboxFile(string path, "
                   "bool allowLegacy)")
LOAD_OUTBOX_SIG = "private static void LoadOutbox()"
PERSIST_OUTBOX_SIG = "private static void PersistOutbox()"
CHOOSE_OUTBOX_SIG = ("private static OutboxGeneration ChooseOutboxCopy(OutboxGeneration live,")


def test_a_torn_trailer_salvages_its_body_instead_of_reporting_an_empty_queue():
    """r15 HIGH. A trailer that STARTS but does not verify means the write was
    interrupted inside the trailer itself, so the body above it is complete far
    more often than not. The reader returned an EMPTY queue on every one of the
    four validation failures -- and on the temp path that also left `salvaged`
    false, so the salvage branch could not fire and the file was deleted with
    the reports still in it.

    Structural gate: there is no C# test runner here, so what is asserted is
    that the validation is one boolean whose failure marks the file
    salvageable, and that no path out of the trailer block skips the body."""
    body = _cs_method_body(API_CLIENT_CS, READ_OUTBOX_SIG)
    assert "bool sawTrailer" in body, "the trailer test is not named"
    assert "trailed = parts.Length == 4" in body, (
        "the validation is not a single boolean any more"
    )
    # Exactly three: the missing file, the unreadable catch, and the end. Any
    # fourth is an early return that skips the body-parsing loop -- which is
    # the defect itself.
    assert body.count("return result;") == 3, (
        f"{body.count('return result;')} `return result;` in ReadOutboxFile; "
        "an early return inside the trailer block is what lost the queue"
    )
    # Positional, not a substring test. The trailerless-temp branch below also
    # says `result.salvaged = true;`, so `in body` was satisfied by a line the
    # mutant never touched and the mutant walked straight through (#342/#441).
    assert body.count("result.salvaged = true;") == 2, (
        f"{body.count('result.salvaged = true;')} salvage marks; the torn "
        "trailer and the trailerless temp must each set one"
    )
    assert "result.salvaged = false;" not in body
    assert (body.index("result.salvaged = true;")
            < body.index("else if (!allowLegacy)")), (
        "the torn-trailer branch no longer marks the file salvageable, so the "
        "temp is deleted with its reports in it"
    )


def test_whole_means_a_queue_and_not_merely_a_file_that_could_be_read():
    """`result.whole = true` was set unconditionally at the end of the read, so
    `salvaged` implied `whole` -- and LoadOutbox's salvage branch, which is
    guarded on `!stranded.whole && stranded.salvaged`, was unreachable BY
    CONSTRUCTION. The doc comment said whole meant "passed its own trailer".
    Found while reading the r15 HIGH above, not reported by it."""
    body = _cs_method_body(API_CLIENT_CS, READ_OUTBOX_SIG)
    assert "result.whole = trailed || (allowLegacy && !sawTrailer);" in body
    assert "result.whole = true;" not in body, (
        "whole is unconditional again, which makes salvaged imply whole"
    )


def test_load_and_persist_ask_one_question_about_which_copy_wins():
    """Two independent recovery paths deciding which copy is authoritative is
    what let persist answer it wrongly for as long as it did: it adopted a
    generation number without ever asking what the file held. One rule, two
    callers, and neither carries its own copy of it."""
    src = API_CLIENT_CS.read_text(encoding="utf-8")
    assert src.count("ChooseOutboxCopy(") == 3, (
        f"{src.count('ChooseOutboxCopy(')} references; expected the "
        "declaration plus exactly two call sites"
    )
    rule = "stranded.generation > live.generation"
    assert src.count(rule) == 1, (
        f"the precedence rule appears {src.count(rule)} times; a second copy "
        "is a second answer"
    )
    for name, signature in (("LoadOutbox", LOAD_OUTBOX_SIG),
                            ("PersistOutbox", PERSIST_OUTBOX_SIG)):
        body = _cs_method_body(API_CLIENT_CS, signature)
        assert "ChooseOutboxCopy(" in body, f"{name} decides for itself again"


def test_the_uncertainty_resolution_recovers_the_reports_not_just_the_number():
    """r15 HIGH. When load could not read a queue file, persist re-probed it
    and, on success, took its GENERATION and discarded its ENTRIES -- then
    wrote memory-only state over it. A report queued before the lock cleared
    was overwritten, and a match report carries a rating and a gold award.

    The ordering is part of the fix and is asserted: recovering entries after
    the buffer is built pulls them into memory and writes them out of
    existence in the same call."""
    body = _cs_method_body(API_CLIENT_CS, PERSIST_OUTBOX_SIG)
    assert "foreach (var entry in recovered.entries)" in body
    assert "_pendingReports.Add(entry);" in body

    buffer_at = body.index("var sb = new StringBuilder();")
    assert body.index("_outboxGenerationUncertain") < buffer_at, (
        "the uncertainty resolution runs after the buffer is built, so "
        "anything it recovers is written out of existence"
    )
    assert body.index("recovered.entries") < buffer_at

    # The uncertainty may have been the TEMP's. Resolving it by reading only
    # the live copy left a newer stranded generation unexamined.
    assert "ReadOutboxFile(OutboxPath, true)" in body
    assert "ReadOutboxFile(tmp, false)" in body


def test_reports_are_not_declared_unreplayable_while_they_are_being_replayed():
    """The incomplete-queue warning fired on `!chosen.whole`, which is exactly
    the state the salvage path leaves behind -- so the one session that DID
    recover reports announced that it could not."""
    body = _cs_method_body(API_CLIENT_CS, LOAD_OUTBOX_SIG)
    assert "if (!chosen.whole && !salvaging && File.Exists(OutboxPath))" in body


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
    # r15: the precedence rule moved into ChooseOutboxCopy, because persist
    # needs the same answer and was giving itself a different one. The claims
    # are unchanged and follow it.
    choose = _cs_method_body(API_CLIENT_CS, CHOOSE_OUTBOX_SIG)
    assert ("takeStranded = stranded.whole" in choose
            and "stranded.generation > live.generation" in choose), (
        "the temp has to WIN on generation, not merely exist"
    )
    assert "!live.whole || stranded.generation" in choose, (
        "a first creation has no live copy for the temp to outrank"
    )
    assert (choose.index("if (takeStranded) return stranded;")
            < choose.index("salvaging = true;")
            and choose.index("if (live.whole) return live;")
            < choose.index("salvaging = true;")), (
        "salvage must be unreachable while any complete queue exists"
    )
    assert "ChooseOutboxCopy(live, stranded, out takeStranded, out salvaging)" in load
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
    assert "var live = ReadOutboxFile(OutboxPath, true);" in persist, (
        "the block must be re-derived per write, not latched -- a guard with no "
        "way back costs every report of the session"
    )
    assert "_outboxGenerationUncertain = false;" in persist, "the block never clears"

    reader = _cs_method_body(
        API_CLIENT_CS, "private static OutboxGeneration ReadOutboxFile(string path, bool allowLegacy)")
    assert "&& claimedCount == bodyLines" in reader, "truncation is not detected"
    assert "&& parts[3] == OutboxHash(body.ToString());" in reader, (
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
    assert "trailed = parts.Length == 4" in reader, (
        "a trailer that is not the four fields this writes is not a trailer"
    )
    # r15: and failing that test no longer discards the body above it.
    assert "if (parts.Length != 4) return result;" not in reader, (
        "the early return is back; a torn trailer discards the whole queue"
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


# ── authority, not recency (r14 MEDIUM 3/6) ─────────────────────────────────

def test_a_sitting_the_server_has_replaced_cannot_be_named():
    """The rule the row-shape test could not express.

    Two players meet, leave, and meet again. Both sittings were "the pair's
    most recent series" at some point, and a series that never completed
    satisfies "not completed" forever -- so the old predicate let a report
    aim at whichever of the two suited it. The server knows which sitting it
    last put them in, and that is now the question being asked.
    """
    session = FakeSession(
        _players(), named_series=_series_row(),
        series_fixture=SeriesFixture(grant_present=True, grant_is_newest=False))
    with pytest.raises(main.HTTPException) as caught:
        _call(session, str(NAMED_SERIES))
    assert caught.value.status_code == 403
    assert session.inserts == 0 and session.increments == 0


def test_the_supersession_term_is_what_refuses_it():
    """The control. The fixture above is refused because the SQL asks about
    supersession -- so with that sub-term removed the SAME fixture must be
    accepted. If it is refused either way, the test above is measuring the
    fixture rather than the predicate."""
    fixture = SeriesFixture(grant_present=True, grant_is_newest=False)
    real = " ".join(main._DC_ELIGIBLE_TERMS.split())
    assert not fixture.evaluate(real, main.DC_MIN_LIVE_POINTS)
    without = real.replace("g2.last_seen_at", "g2_removed")
    assert fixture.evaluate(without, main.DC_MIN_LIVE_POINTS), (
        "the fixture refuses this sitting for a reason that is not in the SQL"
    )


def test_a_pair_the_server_has_no_record_for_is_still_judged():
    """The compatibility arm. A sitting that predates this table has no grant,
    and refusing every such report would delete the queued reports of exactly
    the players who were mid-game when it deployed -- the deploy-window
    deletion this arm exists to prevent."""
    session = FakeSession(
        _players(), named_series=_series_row(),
        series_fixture=SeriesFixture(any_grant_for_pair=False, grant_present=False))
    assert _call(session, str(NAMED_SERIES))["status"] == "recorded"


def test_the_compatibility_arm_closes_once_the_server_has_a_record():
    """...and it is not a second, weaker rule left lying around. Once the pair
    has ANY grant, the row-shape arm is unreachable: a sitting the server did
    not put them in is refused even though every old term would pass it."""
    fixture = SeriesFixture(any_grant_for_pair=True, grant_present=False,
                            completed=False, is_most_recent=True, fresh=True)
    real = " ".join(main._DC_ELIGIBLE_TERMS.split())
    assert not fixture.evaluate(real, main.DC_MIN_LIVE_POINTS)
    # the control: without the gate, the legacy arm admits it again
    ungated = real.replace("NOT EXISTS (SELECT 1 FROM series_dc_grants g3", "(SELECT true FROM x g3")
    assert fixture.evaluate(ungated, main.DC_MIN_LIVE_POINTS), (
        "the legacy arm is not actually gated on the pair having no grant"
    )


def test_a_report_delivered_late_is_not_refused_for_being_late():
    """r14 MEDIUM 6. The delivery-time fence contradicted the durability it sat
    inside: a report queued during an outage, with the game then closed for
    longer than the window, was refused on its first later launch and deleted
    without having spent a single retry.

    The authority arm carries no clock. Staleness is decided by the server
    observing the sitting END -- a newer publish, or the bracket closing -- not
    by how long delivery took.
    """
    stale = SeriesFixture(grant_present=True, grant_is_newest=True, fresh=False)
    real = " ".join(main._DC_ELIGIBLE_TERMS.split())
    assert stale.evaluate(real, main.DC_MIN_LIVE_POINTS), (
        "a delivery clock still refuses a sitting the server has not replaced"
    )
    # ...and the pair with no record is still bounded by it, because recency is
    # all that arm has.
    stale_legacy = SeriesFixture(any_grant_for_pair=False, grant_present=False, fresh=False)
    assert not stale_legacy.evaluate(real, main.DC_MIN_LIVE_POINTS)


def test_a_decided_tournament_match_refuses_the_report():
    """r14 MEDIUM 3. A forfeit or double-forfeit terminalises the bracket row
    and deliberately leaves the RankedSeries active with both terminal
    timestamps null -- bracket status owns that outcome. Every row-shape test
    therefore still called such a series nameable, and each one was worth a
    post-result accusation."""
    session = FakeSession(
        _players(), named_series=_series_row(is_tournament=True),
        bracket_states=("completed",))
    with pytest.raises(main.HTTPException) as caught:
        _call(session, str(NAMED_SERIES))
    assert caught.value.status_code == 403
    assert session.bracket_locks == 1, "the bracket was never re-asked under a lock"
    assert session.inserts == 0


def test_a_tournament_series_with_no_bracket_row_is_retryable_not_settled():
    """503, not 4xx, and the difference is what the refusal COSTS.

    The client treats a 4xx as settled and deletes the report; a 503 leaves it
    in the outbox with its retry budget intact. "We cannot judge this yet" and
    "the answer is no" must not be the same reply (#430)."""
    session = FakeSession(
        _players(), named_series=_series_row(is_tournament=True), bracket_states=())
    with pytest.raises(main.HTTPException) as caught:
        _call(session, str(NAMED_SERIES))
    assert caught.value.status_code == 503, (
        "a report the server could not judge is being deleted by the client"
    )
    assert session.inserts == 0


def test_an_open_bracket_row_does_not_refuse_the_report():
    """The control for the two above: a match still to be played must pass."""
    session = FakeSession(
        _players(), named_series=_series_row(is_tournament=True),
        bracket_states=("ready",))
    assert _call(session, str(NAMED_SERIES))["status"] == "recorded"
    assert session.bracket_locks == 1


def test_the_bracket_lock_is_taken_after_the_series_and_never_before():
    """Lock order: players -> ranked_series -> tournament_matches.

    `_acquire_tournament_match_action_gate` already takes the series FOR NO KEY
    UPDATE and then the bracket row FOR UPDATE, so this pass has to nest in the
    same direction. Taking the bracket first would invert it against a live
    writer and make a cycle out of two individually correct orders (#505)."""
    session = FakeSession(
        _players(), named_series=_series_row(is_tournament=True),
        bracket_states=("scheduled",))
    _call(session, str(NAMED_SERIES))
    assert "series" in session.lock_order and "bracket" in session.lock_order
    assert session.lock_order.index("series") < session.lock_order.index("bracket"), (
        f"lock order inverted against the tournament writer: {session.lock_order}"
    )


def test_the_unnamed_path_resolves_from_the_same_authority_it_is_judged_by(_stub_the_gates):
    """One resolver, asked once. Resolving "the pair's current sitting" one way
    and judging it another is how a room-aware answer and a room-blind answer
    came to disagree about the same pair -- so the unnamed path asks the grant
    first, and only falls back for a pair that has no grant at all."""
    session = FakeSession(_players(), grant_series_id=NAMED_SERIES,
                          named_series=_series_row())
    assert _call(session)["status"] == "recorded"
    assert session.grant_lookups == 1, "the unnamed path did not ask the authority"
    assert _stub_the_gates["find_current"] == 0, (
        "it fell back to the row-shape resolver despite holding a grant"
    )


def test_the_unnamed_path_still_falls_back_when_there_is_no_grant(_stub_the_gates):
    """The control. A pair the server has no record for must still resolve, or
    the compatibility arm is unreachable in practice."""
    session = FakeSession(_players(), grant_series_id=None)
    assert _call(session)["status"] == "recorded"
    assert session.grant_lookups == 1
    assert _stub_the_gates["find_current"] == 1


# ── publishing writes both halves or neither ────────────────────────────────

def test_publishing_a_sitting_stamps_activity_and_the_grant_together():
    """#509's lesson applied before it costs a round: the activity stamp and
    the authority record are two writes that must never diverge, so they are
    one function. An activity stamp without a grant is a sitting the freshness
    bound calls live and the authority record has never heard of."""
    seen = []

    class _Rec:
        async def execute(self, statement, params=None):
            seen.append((" ".join(str(statement).split()), dict(params or {})))
            return _Result([])

    series = SimpleNamespace(id=NAMED_SERIES, player1_id=REPORTER, player2_id=LEAVER)
    asyncio.run(main._publish_pair_sitting(_Rec(), series))
    assert len(seen) == 2, seen
    stamp, grant = seen[0][0], seen[1][0]
    assert "UPDATE ranked_series SET last_activity_at = NOW()" in stamp
    assert "INSERT INTO series_dc_grants" in grant
    assert "ON CONFLICT (holder_id, series_id) DO UPDATE SET last_seen_at = NOW()" in grant, (
        "a resume must re-stamp the sitting rather than fail or duplicate"
    )
    # BOTH directions, because holder and counterparty are judged separately.
    assert "(:a, :b, :sid), (:b, :a, :sid)" in grant, (
        "only one direction of the grant is written, so one seat's report is "
        "judged by a record that does not exist"
    )
    assert seen[1][1]["a"] == REPORTER and seen[1][1]["b"] == LEAVER


def test_the_activity_stamp_exists_in_exactly_one_place():
    """A second raw stamp is a sitting the freshness bound calls live and the
    authority record has never heard of."""
    code = MAIN_PY.read_text(encoding="utf-8")
    raw = code.count('"UPDATE ranked_series SET last_activity_at = NOW() WHERE id = :sid"')
    assert raw == 1, (
        f"{raw} raw activity stamps; every one but the helper's own is a "
        "sitting published without an authority record"
    )


def test_every_series_that_is_born_is_published():
    """Counted from the CONSTRUCTIONS, which is the half that can be missing.

    The first version of this gate asserted `_publish_pair_sitting` appears
    four times -- and four is exactly the number the defect produces, because
    the missing call site is by definition not among the calls you counted. A
    count of what you wrote cannot see what you did not write (#509).

    So: walk the AST, and for every `RankedSeries(...)` construction demand a
    publish AFTER it in the same function. A sitting born without a grant is
    unreportable for any pair who has played together before -- their newest
    grant names an older series, and the compatibility arm is reachable only
    for a pair with no grant at all, so both arms refuse and the client deletes
    the report.

    BOTH FILES. Tournament series are pre-created at bracket activation in
    tournaments.py, so a sweep of main.py alone would have found five sites and
    silently blessed the sixth -- the one where a leave matters most.
    """
    def _calls(node, name):
        return sorted(n.lineno for n in ast.walk(node)
                      if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Name) and n.func.id == name)

    unpublished = []
    births = 0
    for path in (MAIN_PY, MAIN_PY.parent / "tournaments.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            made = _calls(fn, "RankedSeries")
            if not made:
                continue
            published = _calls(fn, "_publish_pair_sitting")
            for line in made:
                births += 1
                if not any(p > line for p in published):
                    unpublished.append("%s:%s:%d" % (path.name, fn.name, line))

    assert births >= 5, (
        f"the sweep found only {births} series constructions; a walk that stops "
        "finding them is a check that cannot fail (#441)"
    )
    assert not unpublished, (
        f"these series are created without being published: {unpublished}. A "
        "sitting with no grant refuses every leave report from a pair that has "
        "played before, permanently, and the client deletes what it is refused"
    )



def test_an_accepted_report_marks_the_grant_it_was_judged_by():
    """293 says the column is written when a report is accepted. A column that
    is always NULL answers "no report has ever been accepted", which is a wrong
    answer rather than a missing one -- so the claim is gated, not just made."""
    session = FakeSession(_players(), named_series=_series_row())
    assert _call(session, str(NAMED_SERIES))["status"] == "recorded"
    assert session.spent_marks == 1, "the accepted report left no mark"
    assert session.inserts == 1 and session.increments == 1


def test_a_report_that_lost_the_insert_marks_nothing():
    """The control, and the ordering claim. A replay whose ON CONFLICT matched
    an existing row wrote nothing, so it must not stamp a grant either -- the
    count and the mark are written on one branch or neither."""
    session = FakeSession(_players(), insert_wins=False, named_series=_series_row())
    assert _call(session, str(NAMED_SERIES))["status"] == "already_recorded"
    assert session.spent_marks == 0, (
        "a report that recorded nothing still marked its grant used"
    )
    assert session.increments == 0 and session.commits == 0



def test_the_grant_index_matches_the_order_the_resolver_reads():
    """Both halves read from their own file, so neither can drift unnoticed.

    An index serves an ORDER BY forwards, or backwards with EVERY direction
    reversed. A trailing ASC column against a DESC sort is a mismatch no error
    reports -- the planner simply sorts, and the comment claiming the index was
    built for this query stays there being wrong.
    """
    sql = (MAIN_PY.parent.parent / "sql" / "293_series_dc_grants.sql"
           ).read_text(encoding="utf-8")
    declared = re.search(
        r"CREATE INDEX IF NOT EXISTS ix_grant_pair_seen\s*"
        r"ON series_dc_grants \(([^)]*)\)", sql)
    assert declared, "the pair index is not declared under the name it is discussed by"
    columns = [c.strip() for c in declared.group(1).split(",")]

    resolver = inspect.getsource(main._newest_grant_series_id)
    ordering = re.search(r"ORDER BY ([a-z_]+ DESC(?:, [a-z_]+ DESC)*)", resolver)
    assert ordering, "the resolver has no descending ORDER BY to match against"
    wanted = [t.strip() for t in ordering.group(1).split(",")]

    assert columns[-len(wanted):] == wanted, (
        f"the index trails {columns[-len(wanted):]} but the resolver sorts by "
        f"{wanted}; the index cannot serve that order and the comment saying it "
        "was built for this query is false"
    )
    assert columns[:2] == ["holder_id", "counterparty_id"], (
        f"the index leads with {columns[:2]}, not the equality terms the "
        "resolver and the supersession subquery both filter on"
    )

# ── M4: evidence the reporting seat did not author by itself ────────────────
#
# For a leave during game 1 there is no match row, so the ONLY evidence was
# `ranked_series.live_p*_points` — columns written by a live-points POST that
# authenticates with a secret every client holds and names its author in a query
# parameter. The accusing seat could write its own corroboration.
#
# The first implementation of this fix recorded an attestation for every post,
# marking it `session_verified=false` when no token rode along, so that the new
# rule would have something to read while verified sessions are rare. A design
# review holed it in one line: an unbound row naming a player is a row the OTHER
# player can write, so the default configuration preserved the forgery exactly.
# The record is now verified-only and small, and the RULE handles the sparsity —
# it asks for corroboration only from an account that has provably run a
# ticket-auth client. Several tests below are the negative controls for that.

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
PROGRESS_SQL = SQL_DIR / "295_series_progress.sql"
COMPOSE_YML = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def test_an_unbound_post_cannot_corroborate_anything():
    """THE blocker the design review found. With the shared HMAC and a
    query-parameter identity, a seat can post live points CLAIMING to be its
    opponent. If that wrote an attestation, the accuser would be writing the
    accused's corroboration and the whole item would be inert in its default
    configuration."""
    written = []

    class _Recorder:
        async def execute(self, statement, params=None):
            written.append(str(statement))
            return _Result([])

        def begin_nested(self):
            class _Ctx:
                async def __aenter__(self_inner):
                    return None

                async def __aexit__(self_inner, *a):
                    return False
            return _Ctx()

    rec = _Recorder()
    for verdict in (main.SEAT_UNBOUND, main.SEAT_MISMATCH):
        assert asyncio.run(main._record_seat_attestation(
            rec, main.SEAT_SURFACE_RANKED, NAMED_SERIES, LEAVER, verdict)) is False, verdict
    assert written == [], "a post the transport could not bind wrote a record anyway"
    # ...and the positive control, so this is not passing because nothing writes.
    assert asyncio.run(main._record_seat_attestation(
        rec, main.SEAT_SURFACE_RANKED, NAMED_SERIES, LEAVER, main.SEAT_VERIFIED)) is True
    assert "INSERT INTO series_progress" in written[0]


def test_the_record_has_no_column_that_is_true_of_every_row():
    """`session_verified` was in the first draft and every row would now carry
    it set — a column that is always true answers nothing, which is the same
    defect as a column documented as written that nothing writes. The row's
    EXISTENCE is the attestation."""
    sql = PROGRESS_SQL.read_text(encoding="utf-8")
    body = sql[sql.index("CREATE TABLE"):]
    assert "session_verified" not in body and "verified_at" not in body, (
        "the table still carries the always-true flag"
    )
    # Read the statement, not the docstring: the docstring explains why the
    # column is gone, and a source-wide substring test would be satisfied by
    # the explanation and fail on it in the same breath.
    writer = inspect.getsource(main._record_seat_attestation)
    statement = writer[writer.index("INSERT INTO series_progress"):]
    assert "session_verified" not in statement and "verified_at" not in statement, (
        "the writer still sets a column the table no longer has"
    )


def test_a_game_one_leave_needs_the_accused_own_post_when_they_can_make_one():
    """The arm this item exists for. No match row yet, points on the record, and
    an account that has provably run a ticket-auth client: its own attestation
    is required, and the reporter has no way to write it."""
    refused = FakeSession(_players(), authority_ok=True,
                          series_fixture=SeriesFixture(
                              has_match=False, live_points=10,
                              accused_armed=True, accused_attested=False))
    with pytest.raises(main.HTTPException):
        _call(refused, str(NAMED_SERIES))
    assert refused.inserts == 0 and refused.increments == 0

    counted = FakeSession(_players(), series_fixture=SeriesFixture(
        has_match=False, live_points=10,
        accused_armed=True, accused_attested=True))
    assert _call(counted, str(NAMED_SERIES))["status"] == "recorded"
    assert counted.increments == 1


def test_an_account_that_cannot_attest_is_judged_by_the_old_rule():
    """#503/#276: a rule whose evidence must be EARNED has to say what the
    not-yet-earned class competes against. 162 of 4663 accounts have ever held a
    verified session; demanding corroboration from the other 4501 would refuse
    almost every genuine report. Their leaves are judged exactly as before."""
    session = FakeSession(_players(), series_fixture=SeriesFixture(
        has_match=False, live_points=10,
        accused_armed=False, accused_attested=False))
    assert _call(session, str(NAMED_SERIES))["status"] == "recorded"


def test_the_fallback_is_keyed_on_the_accused_and_the_reporter_cannot_move_it():
    """Both halves of the corroboration conjunct name :dp. Keyed on :rp, or on
    a property of the sitting rather than of the accused, the reporting seat
    could arrange the state that decides whether it must corroborate."""
    sql = main._DC_EVIDENCE_TERM
    assert "sp.player_id = :dp" in sql
    assert "pa.id = :dp" in sql, (
        "the arming fallback is not keyed on the accused, so it does not "
        "describe whether the ACCUSED can attest"
    )
    assert ":rp" not in sql, (
        "the evidence arm reads the reporter, so the seat filing the report is "
        "part of what decides whether the report is believed"
    )
    assert "steam_auth_seen_at" in sql, (
        "the fallback is not gated on the per-account arming column, so it is "
        "either always open (no fence) or always closed (refuses everyone)"
    )


def test_the_minimum_gameplay_threshold_survived_the_rewrite():
    """A design-review HIGH. Making corroboration its own OR-arm would have let
    a single 1-0 post carry a report that today needs two points on the board.
    The threshold is AND-ed with the corroboration, not replaced by it."""
    thin = SeriesFixture(has_match=False, live_points=1,
                         accused_armed=True, accused_attested=True)
    assert not thin.evaluate(main._DC_ELIGIBLE_TERMS, main.DC_MIN_LIVE_POINTS)
    thick = SeriesFixture(has_match=False, live_points=main.DC_MIN_LIVE_POINTS,
                          accused_armed=True, accused_attested=True)
    assert thick.evaluate(main._DC_ELIGIBLE_TERMS, main.DC_MIN_LIVE_POINTS)


def test_a_finished_game_still_counts_the_way_it_always_did():
    """The match arm is NOT gated on corroboration, and the comment says why in
    plain terms rather than claiming an independence it does not have: it is
    single-seat authored like everything else, but it moved both ratings and
    left an auditable row. Gating it would hand an armed account a way to escape
    every leave by suppressing its own live-points posts."""
    session = FakeSession(_players(), series_fixture=SeriesFixture(
        has_match=True, live_points=0,
        accused_armed=True, accused_attested=False))
    assert _call(session, str(NAMED_SERIES))["status"] == "recorded"


def test_arming_the_switch_removes_the_fallback_and_nothing_else(monkeypatch):
    """The switch's whole job. With it on, an unarmed account's game-1 leave
    needs corroboration too — and a switch that changes nothing in one of its
    positions is not a switch, so both positions are asserted."""
    unarmed = SeriesFixture(has_match=False, live_points=10,
                            accused_armed=False, accused_attested=False)
    sql = main._DC_ELIGIBLE_TERMS
    assert unarmed.evaluate(sql, main.DC_MIN_LIVE_POINTS, False)
    assert not unarmed.evaluate(sql, main.DC_MIN_LIVE_POINTS, True)
    # ...and a finished game is still outside the switch's reach.
    assert SeriesFixture(has_match=True, live_points=0).evaluate(
        sql, main.DC_MIN_LIVE_POINTS, True)


def test_the_verified_seat_requirement_ships_off():
    """162 of 4663 accounts have ever held a verified session. Arming this on
    day one would refuse the overwhelming majority of genuine game-1 reports,
    which is the wrong direction for a fence whose failure costs another
    player's public leave-%."""
    for value in ("", "0", "no", "off", "  "):
        os.environ["DC_REQUIRE_VERIFIED_SEAT"] = value
        assert main._dc_require_verified_seat() is False
    os.environ.pop("DC_REQUIRE_VERIFIED_SEAT", None)
    assert main._dc_require_verified_seat() is False
    os.environ["DC_REQUIRE_VERIFIED_SEAT"] = "1"
    try:
        assert main._dc_require_verified_seat() is True
    finally:
        os.environ.pop("DC_REQUIRE_VERIFIED_SEAT", None)


def test_every_switch_this_file_reads_is_mapped_into_the_container():
    """#438/#443, and docker-compose.yml says it in bold itself: this project
    has no `env_file:`, so a key in .env reaches compose for interpolation and
    NEVER reaches the process unless it is named under `environment:`. Both M4
    switches would have shipped permanently inert, with every log line normal.

    Read from the source rather than from a list of names, so a switch added
    later is covered without anyone remembering this test exists."""
    src = MAIN_PY.read_text(encoding="utf-8")
    read = set(re.findall(r'os\.getenv\(\s*"([A-Z][A-Z0-9_]*)"', src))
    compose = COMPOSE_YML.read_text(encoding="utf-8")
    api = compose[compose.index("  api:"):compose.index("  bot:")]
    mapped = set(re.findall(r"^\s{6}([A-Z][A-Z0-9_]*):", api, re.M))
    # Names the process gets from somewhere other than this compose file.
    exempt = {"PATH", "HOME", "HOSTNAME", "PYTHONUNBUFFERED", "TZ", "LANG"}
    # PRE-EXISTING and frozen, found by this gate the first time it ran. Each of
    # these is read with a non-empty code default and is passed to the container
    # by nothing, so setting it in .env does nothing at all -- the override
    # affordance is not real. They are NOT fixed here: mapping them as
    # `${KEY:-}` would replace the code default with an empty string (os.getenv
    # returns "" for a key that is set-but-empty), and mapping them with their
    # defaults duplicates each default in two files. The fix is to move each
    # default into compose and drop it from the code, one feature at a time,
    # which is not this change. The set is frozen so a NEW one still fails.
    known_unreachable = {
        "SERIES_REUSE_WINDOW_MIN",
        "RANKED_STREAMING_CHANNEL",
        "BROADCAST_TWITCH_URL", "BROADCAST_TWITCH_VODS_URL",
        "BROADCAST_YOUTUBE_URL", "BROADCAST_YOUTUBE_VODS_URL",
    }
    assert known_unreachable <= read, (
        "this frozen list names keys main.py no longer reads: "
        + ", ".join(sorted(known_unreachable - read))
        + " -- shrink the list rather than leaving it to excuse a future one"
    )
    missing = sorted(read - mapped - exempt - known_unreachable)
    assert not missing, (
        "main.py reads these and docker-compose.yml does not pass them to the "
        "api container, so os.getenv returns \"\" forever: " + ", ".join(missing)
    )


def test_the_mismatch_switch_is_named_for_what_it_does():
    """It was REQUIRE_BOUND_SEAT, which overpromised: a post with no token at
    all is still accepted, so it does not make posts caller-bound. Requiring
    that would break the betting cutoff for every client without a verified
    session."""
    assert not hasattr(main, "_live_points_require_bound_seat")
    doc = inspect.getdoc(main._live_points_refuse_mismatched_seat) or ""
    assert "does not make a post caller-bound" in doc.replace("\n", " ")


def test_the_session_read_cannot_take_down_the_write_it_rides_behind():
    """Returning UNBOUND from an `except` is only fail-soft if the transaction
    survives it, and under asyncpg a caught statement error leaves the whole
    transaction ABORTED (#235). The read-only callers this classifier was
    extracted from never noticed; the live-points write path would have."""
    for fn in (main._seat_attestation_verdict, main._record_seat_attestation):
        assert "begin_nested" in inspect.getsource(fn), fn.__name__


# ── what a refusal costs, and how a doomed report is settled ────────────────


def test_a_report_whose_evidence_has_not_arrived_yet_is_kept_not_deleted():
    """The client deletes a 4xx and re-presents a 5xx. The accused's own
    live-points post can still be in flight, or being re-sent by their client's
    retry layer, which keeps running after they leave the Photon room."""
    session = FakeSession(_players(), authority_ok=True,
                          series_fixture=SeriesFixture(
                              has_match=False, live_points=10,
                              accused_armed=True, accused_attested=False))
    with pytest.raises(main.HTTPException) as caught:
        _call(session, str(NAMED_SERIES))
    assert caught.value.status_code == 503
    assert session.authority_diagnostics >= 1


def test_a_sitting_nothing_has_happened_in_for_hours_settles_instead():
    """The server is the ONLY place a doomed report can be settled: the client's
    twenty-attempt budget is per PROCESS — the outbox persists url and body and
    reloads with attempts = 0 — so a permanently ineligible report would get a
    fresh twenty attempts on every launch, forever."""
    session = FakeSession(_players(), authority_ok=True, idle=True,
                          series_fixture=SeriesFixture(
                              has_match=False, live_points=10,
                              accused_armed=True, accused_attested=False))
    with pytest.raises(main.HTTPException) as caught:
        _call(session, str(NAMED_SERIES))
    assert caught.value.status_code == 403, (
        "a sitting idle past the live window still answers retryable, so a "
        "report that can never become eligible never leaves the client"
    )
    assert "CAST(:live_window AS interval)" in session.authority_sql, (
        "the idle bound is not asked in SQL against the database clock (#448)"
    )


def test_the_idle_bound_is_computed_from_the_sitting_and_not_asserted_about():
    """The behavioural test above can only see the bound if the statement
    computes it, and `:live_window` appears in the predicate's legacy arm too --
    so a substring test for the bind is satisfied by an occurrence that has
    nothing to do with this. Name the EXPRESSION."""
    src = inspect.getsource(main._refuse_named_series)
    stmt = src[src.index("SELECT 1 AS authority_only"):src.index("LIMIT 1")]
    assert "COALESCE(s.last_activity_at, s.created_at)" in stmt, (
        "the diagnostic reports idleness without reading when anything last "
        "happened in the sitting"
    )
    assert "CAST(:live_window AS interval)" in stmt, (
        "the idle bound is not asked against the database clock, or is not "
        "asked at all (#448)"
    )
    assert "AS idle" in stmt


def test_the_gameplay_threshold_is_a_bind_and_not_a_literal():
    """A hardcoded target is a check that cannot fail (#342). The threshold has
    one definition, DC_MIN_LIVE_POINTS, and the statement must bind it."""
    ev = main._DC_EVIDENCE_TERM
    assert ">= :min_points" in ev, (
        "the points comparison carries its own number, so the constant and the "
        "statement can disagree about what counts as meaningful play"
    )
    assert not re.search(r"points, 0\) >= \d", ev)


def test_the_predicate_only_reads_columns_the_migration_creates():
    """Found by grep, not by this suite: the rewrite dropped `session_verified`
    from the table and left the predicate reading it, which is undefined_column
    on every leave report. The fake models SQL by substring and cannot see a
    schema, so nothing here could have caught it. This can."""
    sql = PROGRESS_SQL.read_text(encoding="utf-8")
    create = sql[sql.index("CREATE TABLE"):sql.index(");", sql.index("CREATE TABLE"))]
    columns = set(re.findall(r"^\s{4}([a-z_]+)\s+(?:TEXT|UUID|TIMESTAMPTZ|BOOLEAN)",
                             create, re.M))
    assert columns, "no columns could be parsed out of the migration"
    read = set(re.findall(r"\bsp\d?\.([a-z_]+)", main._DC_EVIDENCE_TERM))
    # Without this the gate is decoration: an expression that matches nothing
    # yields an empty set, an empty difference and a passing assert forever.
    # It landed exactly that way once -- a shell ate the \b and wrote a literal
    # backspace -- and the mutant walked straight through (#342/#441).
    assert read, "no series_progress column reads were found in the predicate"
    missing = sorted(read - columns)
    assert not missing, (
        "the disconnect predicate reads series_progress columns migration 295 "
        "does not create: " + ", ".join(missing)
    )


def test_an_authority_refusal_stays_settled():
    """The negative control for both of the above: a sitting the server has
    superseded is not going to become nameable."""
    session = FakeSession(_players(), series_fixture=SeriesFixture(
        grant_is_newest=False, has_match=True))
    with pytest.raises(main.HTTPException) as caught:
        _call(session, str(NAMED_SERIES))
    assert caught.value.status_code == 403


def test_a_diagnostic_that_cannot_answer_keeps_the_report():
    """The two errors are not symmetric. A wrongly settled report is deleted and
    unrecoverable; a wrongly retried one costs bounded requests and is settled
    by the idle bound as soon as the lookup works again. The first draft had
    this backwards."""
    src = inspect.getsource(main._refuse_named_series)
    body = src[src.index("except Exception"):src.index("if authority_ok")]
    assert "authority_ok, idle = True, False" in body, (
        "the diagnostic's own failure deletes a report it could not classify"
    )


def test_the_diagnostic_asks_the_same_authority_question_as_the_predicate():
    assert main._DC_AUTHORITY_ONLY_TERMS in main._DC_ELIGIBLE_TERMS, (
        "the diagnostic is not a prefix of the predicate it explains, so the "
        "two can answer differently about the same sitting"
    )
    assert main._DC_EVIDENCE_TERM not in main._DC_AUTHORITY_ONLY_TERMS, (
        "the diagnostic still carries the evidence arm, so it can only ever "
        "agree with the predicate and no refusal is ever retryable"
    )


def test_the_locked_sites_diagnostic_carries_the_row_terms_too():
    """A diagnostic that asks a WIDER question than the statement it explains
    will call a settled refusal retryable."""
    src = inspect.getsource(main._report_disconnect_once)
    assert "row_terms=_DC_LOCKED_ROW_TERMS" in src
    session = FakeSession(_players(),
                          series_fixture=SeriesFixture(grant_is_newest=False))
    with pytest.raises(main.HTTPException):
        _call(session)
    assert session.authority_diagnostics == 1
    assert "s.player1_id = :rp" in session.authority_sql, (
        "the diagnostic omits the pair check, so a report naming a series "
        "belonging to two other players is answered 'try again'"
    )
    assert "s.invalidated_at IS NULL" in session.authority_sql


def test_the_locked_statement_and_its_diagnostic_share_the_row_terms():
    src = inspect.getsource(main._report_disconnect_once)
    assert "(s.player1_id = :rp" not in src, (
        "the locked statement carries its own copy of the row terms again, so "
        "the statement and the diagnostic explaining it can drift apart"
    )
    assert src.count("_DC_LOCKED_ROW_TERMS") >= 2


def test_the_diagnostic_takes_no_lock_and_runs_only_on_refusal():
    accepted = FakeSession(_players(), series_fixture=SeriesFixture())
    _call(accepted, str(NAMED_SERIES))
    assert accepted.authority_diagnostics == 0
    assert "series" in accepted.lock_order


# ── the attestation writers ─────────────────────────────────────────────────


def _live_points_endpoints():
    """Every function serving a live-points POST — the operation that CREATES
    the obligation to attest, per #515. Counting calls to the writer instead
    counts the calls the fix wrote and is blind to the endpoint it forgot."""
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    found = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in fn.decorator_list:
            if not isinstance(dec, ast.Call) or not dec.args:
                continue
            route = dec.args[0]
            if isinstance(route, ast.Constant) and isinstance(route.value, str) \
                    and route.value.endswith("/live-points"):
                found.append(fn)
    return found


def test_every_live_points_endpoint_records_who_posted():
    endpoints = _live_points_endpoints()
    assert len(endpoints) >= 3, (
        "the live-points surfaces cannot be enumerated from the routes, so "
        "this gate is not measuring the thing it claims to measure"
    )
    missing = [fn.name for fn in endpoints
               if "_record_seat_attestation" not in {
                   n.func.id for n in ast.walk(fn)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}]
    assert not missing, (
        "live-points endpoints that store points but record no attestation: "
        + ", ".join(missing))


def test_every_live_points_endpoint_asks_who_is_posting_before_it_writes():
    missing = []
    for fn in _live_points_endpoints():
        gate = [n.lineno for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_seat_gate_for_live_points"]
        record = [n.lineno for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "_record_seat_attestation"]
        if not gate or not record or min(gate) > min(record):
            missing.append(fn.name)
    assert not missing, (
        "the seat verdict is taken after the attestation is written (or not at "
        "all) in: " + ", ".join(missing))


def test_the_endpoints_take_the_request_the_verdict_is_read_from():
    """A handler with no Request parameter cannot see a header, so every post
    would be UNBOUND forever — a substrate shipping inert while every log line
    says it is working (#438/#443)."""
    for fn in _live_points_endpoints():
        names = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
        assert "request" in names, f"{fn.name} never receives the request"


def test_the_verdict_distinguishes_cannot_tell_from_checked_and_wrong():
    """#499. Folding "no token" together with "a token that names someone else"
    loses the only fact that justifies withholding a record."""
    assert main.SEAT_UNBOUND != main.SEAT_MISMATCH
    src = inspect.getsource(main._seat_attestation_verdict)
    mismatch_at = src.index("return SEAT_MISMATCH")
    for later in ('row["expires_at"]', 'row["verified"]'):
        assert src.index(later) > mismatch_at, (
            "a token that names someone else is classified as merely unbound "
            "once it expires, and the fact a caller acts on is lost"
        )


def test_the_privilege_check_still_answers_only_for_a_verified_seat():
    src = inspect.getsource(main._strict_steam_session_ok)
    assert "SELECT steam_id, verified, expires_at" not in src, (
        "the privilege check kept its own copy of the session read (#432)"
    )
    assert "_seat_attestation_verdict" in src and "SEAT_VERIFIED" in src
    assert "SEAT_UNBOUND" not in src and "SEAT_MISMATCH" not in src, (
        "the privilege check treats one of the negative verdicts as a pass"
    )


def test_the_mismatch_refusal_ships_off_and_fires_only_on_mismatch():
    os.environ.pop("LIVE_POINTS_REFUSE_MISMATCHED_SEAT", None)
    assert main._live_points_refuse_mismatched_seat() is False

    async def _verdict(request, steam_id, db):
        return request

    saved = main._seat_attestation_verdict
    try:
        main._seat_attestation_verdict = _verdict
        os.environ["LIVE_POINTS_REFUSE_MISMATCHED_SEAT"] = "1"
        for benign in (main.SEAT_VERIFIED, main.SEAT_UNBOUND):
            assert asyncio.run(main._seat_gate_for_live_points(
                benign, "76561198000000011", None)) == benign
        with pytest.raises(main.HTTPException) as caught:
            asyncio.run(main._seat_gate_for_live_points(
                main.SEAT_MISMATCH, "76561198000000011", None))
        assert caught.value.status_code == 403
        os.environ["LIVE_POINTS_REFUSE_MISMATCHED_SEAT"] = "0"
        assert asyncio.run(main._seat_gate_for_live_points(
            main.SEAT_MISMATCH, "76561198000000011", None)) == main.SEAT_MISMATCH
    finally:
        main._seat_attestation_verdict = saved
        os.environ.pop("LIVE_POINTS_REFUSE_MISMATCHED_SEAT", None)


def test_the_surfaces_the_code_writes_are_the_surfaces_the_table_admits():
    """A CHECK listing surfaces the code never writes is decoration; a code path
    writing a surface the constraint rejects records nothing. Compare the SETS
    (#205)."""
    sql = PROGRESS_SQL.read_text(encoding="utf-8")
    declared = re.search(r"surface IN \(([^)]*)\)", sql)
    assert declared, "the surface column admits anything at all"
    admitted = {s.strip().strip("'") for s in declared.group(1).split(",")}
    used = {main.SEAT_SURFACE_RANKED, main.SEAT_SURFACE_TEAM, main.SEAT_SURFACE_FFA}
    assert admitted == used, (
        f"the table admits {sorted(admitted)} and the code writes {sorted(used)}")
    assert set(re.findall(r"sp\d?\.surface = '(\w+)'", main._DC_EVIDENCE_TERM)) \
        == {main.SEAT_SURFACE_RANKED}, (
        "the 1v1 evidence rule reads attestations from another surface")


def test_the_attestation_table_cascades_from_the_player():
    sql = PROGRESS_SQL.read_text(encoding="utf-8")
    assert re.search(r"player_id\s+UUID\s+NOT NULL REFERENCES players\(id\) ON DELETE CASCADE",
                     sql), "player_id does not cascade"
    assert "REFERENCES ranked_series" not in sql, (
        "subject_id carries a foreign key to one of the three parent tables, "
        "so the other two surfaces cannot record anything at all")
