"""The disconnect report's durability, and the H2H read's room budget
(review r8 MEDIUM 3) — two halves of one finding.

POST /api/v1/report-disconnect shares one per-IP rate bucket with every other
sensitive path, and the client wrote it EXACTLY ONCE: a refusal — a 429 being
the ordinary way to earn one — left the dc_events row and the ranked_dc_count
increment behind it simply unmade, on another player's record. The two halves,
and why they are one change:

  * the client keeps a refused report in the durable outbox until the server
    accepts it or settles it, so a refusal is retried instead of lost; and
  * because that creates replays, the server now counts the increment only for
    the request that INSERTED the dc_events row — otherwise the retry added to
    protect the number would be the thing that inflated it.

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

    def __init__(self, players, event_exists=False, insert_wins=True, stored_count=4):
        self.players = list(players)
        self.event_exists = event_exists
        self.insert_wins = insert_wins
        self.stored_count = stored_count
        self.statements = []
        self.increments = 0
        self.inserts = 0
        self.commits = 0

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        if sql.startswith("SELECT") and "FROM players" in sql:
            wanted = list(statement.compile().params.values())[0]
            return _Result([p for p in self.players if p.steam_id == wanted])
        if "FROM dc_events" in sql:
            return _Result([(1,)] if self.event_exists else [])
        if sql.startswith("INSERT INTO dc_events"):
            assert "RETURNING" in sql, (
                "the insert must report whether it was the one that recorded the event"
            )
            self.inserts += 1
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


def _players(count=3):
    return [
        SimpleNamespace(id=REPORTER, steam_id=REPORTER_SID, ranked_dc_count=0),
        SimpleNamespace(id=LEAVER, steam_id=LEAVER_SID, ranked_dc_count=count),
    ]


@pytest.fixture(autouse=True)
def _stub_the_gates(monkeypatch):
    """Everything the handler leans on that is not this finding: the session
    gate, the service-account fence and the pair's current series."""

    async def _noop(*args, **kwargs):
        return None

    async def _series(*args, **kwargs):
        return SimpleNamespace(id=uuid4(), player1_id=REPORTER, player2_id=LEAVER)

    monkeypatch.setattr(main, "_check_steam_session", _noop)
    monkeypatch.setattr(main, "_assert_no_service_subject", _noop)
    monkeypatch.setattr(main, "_find_current_active_series", _series)


def _call(session):
    request = SimpleNamespace(headers={"X-Session-Token": "tok"})
    return asyncio.run(
        main.report_disconnect(request, REPORTER_SID, LEAVER_SID, session)
    )


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
    session = FakeSession(_players(count=7), event_exists=False, insert_wins=False)
    answer = _call(session)
    assert answer["status"] == "already_recorded"
    assert session.inserts == 1
    assert session.increments == 0, "the losing replay incremented the count"
    assert session.commits == 0
    assert answer["ranked_dc_count"] == 7


def test_the_settled_replay_still_short_circuits_before_any_write():
    """A retry arriving after the first report committed: the fast path reads
    the row and answers without attempting an insert at all."""
    session = FakeSession(_players(count=7), event_exists=True)
    answer = _call(session)
    assert answer["status"] == "already_recorded"
    assert answer["ranked_dc_count"] == 7
    assert session.inserts == 0
    assert session.increments == 0
    assert session.commits == 0


def test_the_recorded_answer_is_the_value_the_database_returned():
    """Not a number computed from the row read before the insert decided —
    that read is stale by construction under a concurrent replay."""
    session = FakeSession(_players(count=0), stored_count=9)
    assert _call(session)["ranked_dc_count"] == 9


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


def test_the_disconnect_report_is_a_one_shot_send_again():
    """r8 asked for a durable disconnect report and one was built; r9 descoped
    it. The report carries no series identity, so the server resolves the
    pair's CURRENT series at delivery time — a replay arriving after the pair
    start a new series is written against that one instead. Making it durable
    needs the immutable series id captured at observation, persisted in the
    outbox line and validated server-side; that is a client/server contract,
    not a change to this call."""
    body = _cs_method_body(
        API_CLIENT_CS,
        "public static void ReportDisconnect(string reporterSteamId, string disconnectedSteamId)",
    )
    assert "EnqueueFailedReport" not in body
    assert "RemovePendingReport" not in body
    assert "StartCoroutine(PostRequest(" in body
    src = API_CLIENT_CS.read_text(encoding="utf-8")
    for gone in ("DC_REPORT_BODY", "IsDisconnectReportUrl"):
        assert gone not in src, f"{gone} outlived the code that used it"


def test_no_queued_url_can_race_its_own_immediate_retry_chain():
    """The defect the enrolment made reachable, kept as a standing check.

    OutboxLoop captures an index, yields into PostRequest, and then removes by
    that stale index; RemovePendingReport mutates the same list from a separate
    coroutine. So an entry that is queued BEFORE its immediate send, and whose
    send chain is still running when the loop picks it up, can have both
    completions act on one entry — the loop then removes a different entry, or
    throws and ends the coroutine for the session (`_outboxLoopStarted` is
    never reset).

    Two things keep that unreachable, and both are asserted here rather than
    left to timing: the disconnect report's 15 s branch is gone, so the only
    delays are macro evidence's 120 s (against a chain of at most ~72 s) and
    the shared 30 s default, which is only ever reached by callers that queue
    AFTER their chain has already failed."""
    import re as _re

    delay = _cs_method_body(API_CLIENT_CS, "private static float OutboxInitialDelay(string url)")
    delays = sorted(int(x) for x in _re.findall(r"(\d+)f", delay))
    assert delays == [30, 120], f"a new initial-retry delay appeared: {delays}"

    src = API_CLIENT_CS.read_text(encoding="utf-8")
    sites = src.count("EnqueueFailedReport(")
    # one declaration + macro evidence + the four match-report paths
    assert sites == 6, (
        f"{sites} EnqueueFailedReport references, expected 6. A NEW caller must "
        "either queue only after its immediate chain has failed, or keep a "
        "first-retry delay longer than that chain — or OutboxLoop must be "
        "changed to remove by reference instead of by a stale index."
    )


def test_the_server_half_of_the_finding_is_what_survived():
    """The descope is of the client half only. The server's replay safety is
    what makes a durable client buildable later, so it must not drift."""
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
