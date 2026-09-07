"""Sept 7 item 3: the pair's own Photon ping maps on the 1v1 queue.

A client sends its region ping map with /queue/join (body) and, while it keeps
polling, as the X-Region-Pings header; ONE validator admits both. The map is
stored on the queue row off-ORM (migration 301) by the join's single INSERT ...
ON CONFLICT and by the poll's heartbeat UPDATE (only with a valid header); the
poll that carries a valid header also overlays it onto its own row snapshot, so
issuance in that same request judges the refreshed map (impl review r1 M1). At
room issuance both seats' maps are re-read under the ordered locks and
`_pick_region_by_pings` (rung 0) may replace the ladder's answer — only by a
region that costs NEITHER seat more than 20 ms over its own baseline.

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

def test_rung0_is_swap_invariant():
    """The argument order is which seat's request triggered issuance."""
    rng = random.Random(7)
    codes = ["us", "eu", "asia", "sa", "jp", "au"]
    for _ in range(400):
        p1 = {c: rng.randint(1, 400) for c in codes if rng.random() < 0.7}
        p2 = {c: rng.randint(1, 400) for c in codes if rng.random() < 0.7}
        for ladder in codes:
            a = main._pick_region_by_pings(p1, p2, ladder)
            b = main._pick_region_by_pings(p2, p1, ladder)
            assert a == b, f"{p1} / {p2} ladder={ladder}: {a} vs {b}"


def test_missing_maps_and_no_overlap_leave_the_ladder():
    assert main._pick_region_by_pings(None, {"us": 40}, "us") == ("us", "no-maps", None)
    assert main._pick_region_by_pings({"us": 40}, {}, "us") == ("us", "no-maps", None)
    assert main._pick_region_by_pings({"us": 40}, {"eu": 40}, "asia") == ("asia", "no-overlap", None)


def test_a_fabricated_one_entry_map_cannot_move_an_honest_seat():
    """The design's own enumeration (#283): {eu: 1} against an honest
    {us: 30, eu: 150} with the ladder on us fails the Pareto check on the
    honest seat's OWN numbers (150 > 30 + 20) and gets the ladder."""
    assert main._pick_region_by_pings({"eu": 1}, {"us": 30, "eu": 150}, "us") == ("us", "pareto", None)
    assert main._pick_region_by_pings({"us": 30, "eu": 150}, {"eu": 1}, "us") == ("us", "pareto", None)


def test_a_region_both_seats_measured_better_is_taken():
    pick, why, worst = main._pick_region_by_pings(FRESH_MAP, FRESH_MAP_PARTNER, "us")
    assert (pick, why, worst) == ("eu", "pings", 30)


def test_the_ladder_confirmed_by_pings_reports_the_rung():
    assert main._pick_region_by_pings({"us": 20, "eu": 90}, {"us": 25, "eu": 80}, "us") == ("us", "pings", 25)


def test_tolerance_is_judged_on_each_seats_own_baseline():
    """eu is the pair's best worst-case, but it costs seat 2 more than 20 ms
    over what seat 2 measured for the ladder's region."""
    assert main._pick_region_by_pings({"us": 100, "eu": 30}, {"us": 40, "eu": 61}, "us")[0] == "us"
    assert main._pick_region_by_pings({"us": 100, "eu": 30}, {"us": 40, "eu": 60}, "us")[0] == "eu"


def test_an_unmeasured_ladder_region_uses_each_seats_own_best_as_baseline():
    """7/3-5: L's presence in the maps is not required."""
    assert main._pick_region_by_pings({"eu": 30}, {"eu": 35}, "us") == ("eu", "pings", 35)
    # the candidate must still be within 20 ms of THIS seat's own best
    assert main._pick_region_by_pings({"eu": 200, "asia": 30}, {"eu": 35}, "us") == ("us", "pareto", None)


def test_tie_order_worst_then_sum_then_code():
    # worst decides first
    assert main._pick_region_by_pings({"us": 50, "eu": 40}, {"us": 50, "eu": 60}, "asia")[0] == "us"
    # equal worst: the smaller sum
    assert main._pick_region_by_pings({"us": 60, "eu": 60}, {"us": 40, "eu": 60}, "asia")[0] == "us"
    # equal worst and sum: fixed order by code, whichever seat asked
    assert main._pick_region_by_pings({"us": 50, "eu": 50}, {"us": 50, "eu": 50}, "asia")[0] == "eu"
    assert main._pick_region_by_pings({"us": 50, "eu": 60}, {"us": 60, "eu": 50}, "asia")[0] == "eu"


# ── rung 0 through _pick_room_region: freshness, symmetry, the log line ─────

def test_pick_room_region_positional_signature_is_unchanged():
    params = list(inspect.signature(main._pick_room_region).parameters)
    assert params[:5] == ["my_region", "my_home", "opp_region", "opp_home", "room_name"]
    assert {"p1_pings", "p2_pings", "p1_pings_at", "p2_pings_at"} <= set(params[5:])


def test_fresh_maps_replace_the_ladder_and_stale_or_absent_ones_do_not(capsys):
    now = _now()
    fresh = now - timedelta(seconds=60)
    stale = now - timedelta(seconds=main.REGION_PINGS_ISSUANCE_MAX_AGE_S + 1)
    kw = dict(p1_pings=FRESH_MAP, p2_pings=FRESH_MAP_PARTNER, now=now)
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings_at=fresh, p2_pings_at=fresh, **kw) == "eu"
    out = capsys.readouterr().out
    rung, ladder = [line for line in out.splitlines() if "[QUEUE-REGION]" in line][:2]
    assert rung == "[QUEUE-REGION] room=r pick=eu rung=pings worst=30 ladder=us"
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


def test_a_stored_map_that_no_longer_validates_is_absent():
    now = _now()
    at = now - timedelta(seconds=5)
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings={"US": 10, "eu": 30},
                                  p2_pings=FRESH_MAP_PARTNER, p1_pings_at=at, p2_pings_at=at, now=now) == "us"
    # a JSON text (a driver that hands jsonb back undecoded) is still read
    assert main._pick_room_region("us", "us", "us", "us", "r", p1_pings='{"us": 100, "eu": 30}',
                                  p2_pings=FRESH_MAP_PARTNER, p1_pings_at=at, p2_pings_at=at, now=now) == "eu"


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
        a = main._pick_room_region("", h1, "", h2, "r", p1_pings=m1, p2_pings=m2, p1_pings_at=t1, p2_pings_at=t2, now=now)
        b = main._pick_room_region("", h2, "", h1, "r", p1_pings=m2, p2_pings=m1, p1_pings_at=t2, p2_pings_at=t1, now=now)
        assert a == b


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
    ({"us": 0}, 12), ({"us": 5001}, 12), ({"us": 42.0}, 12), ({"us": True}, 12), ({"us": "42"}, 12),
    ({"us": 42}, -1), ({"us": 42}, 901), ({"us": 42}, "12"), ({"us": 42}, 12.5), ({"us": 42}, True), ({"us": 42}, None),
    (["us", 42], 12), ("us=42", 12), (None, 12),
])
def test_validator_refuses_everything_else(pings, age):
    assert main._region_pings_validate(pings, age) == (None, None)


def test_header_parser_feeds_the_join_validator():
    assert main._region_pings_from_header("us=42,eu=31;age=12") == ('{"eu":31,"us":42}', 12)
    assert main._region_pings_from_header(" us=42 , eu=31 ; age=0 ") == ('{"eu":31,"us":42}', 0)


@pytest.mark.parametrize("value", [
    None, "", "us=42", "us=42;age=-5", "us=42;age=", "us=42;age=1.5", "us=42;age=901",
    "us=42,us=43;age=1", "us=4a;age=1", "us;age=1", "US=42;age=1", "us=42;age=1;x",
    ";age=1", "us=0;age=1", "x" * 600,
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

    async def execute(self, statement, params=None):
        params = dict(params or {})
        sql = " ".join(str(statement).split())
        self.statements.append((sql, params))
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
            # returns); the snapshot the handler took earlier is untouched
            if "region_pings" in params:
                row = self.rows[params["pid"]]
                row["region_pings"] = params["region_pings"]
                row["region_pings_at"] = datetime.now(timezone.utc) - timedelta(seconds=params["region_pings_age"])
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
        "ready": True, "joined_at": now - timedelta(seconds=30), "matched_at": now - timedelta(seconds=5),
        "region_pings": pings, "region_pings_at": pings_at,
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

    async def _stamp(db, my_pid, opp_pid, room_name, region):
        stamps.append((my_pid, opp_pid, room_name, region))
        return True

    async def _series(db, a, b, room_id=None):
        return SimpleNamespace(id=SERIES, player1_id=a, p1_series_wins=0, p2_series_wins=0)

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
    stale = _now() - timedelta(seconds=main.REGION_PINGS_ISSUANCE_MAX_AGE_S + 5)
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


def test_queue_ready_control_without_maps_or_with_stale_maps_takes_the_ladder(issuance):
    session = FakeIssuanceSession(_pair(None, None, None, None), ME_STEAM)
    assert _ready(session)["photon_region"] == "us"
    stale = _now() - timedelta(seconds=main.REGION_PINGS_ISSUANCE_MAX_AGE_S + 5)
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
    _poll(session, {"x-region-pings": "us=42,eu=31;age=12"})
    assert len(session.heartbeats) == 1
    sql, params = session.heartbeats[0]
    assert "region_pings = CAST(:region_pings AS JSONB)" in sql
    assert "region_pings_at = NOW() - make_interval(secs => :region_pings_age)" in sql
    assert params == {"pid": ME, "region_pings": '{"eu":31,"us":42}', "region_pings_age": 12}


@pytest.mark.parametrize("headers", [{}, {"x-region-pings": "us=42;age=-1"}, {"x-region-pings": "garbage"}])
def test_queue_poll_leaves_the_heartbeat_alone_without_a_valid_header(issuance, headers):
    at = _now() - timedelta(seconds=20)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, at, at), ME_STEAM)
    _poll(session, headers)
    assert len(session.heartbeats) == 1
    sql, params = session.heartbeats[0]
    assert sql == "UPDATE ranked_queue SET last_polled = NOW() WHERE player_id = :pid"
    assert params == {"pid": ME}
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
    stale = _now() - timedelta(seconds=main.REGION_PINGS_ISSUANCE_MAX_AGE_S + 1)
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


def test_the_header_stamp_is_what_the_issuance_window_judges(issuance):
    """The stamp half: the UPDATE dates the row now() - age, so a valid header
    whose age is past the window leaves A stale although the STORED stamp was
    fresh — issuance agrees with what the row now holds, not with the snapshot."""
    fresh = _now() - timedelta(seconds=10)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, fresh, fresh), ME_STEAM)
    age = main.REGION_PINGS_ISSUANCE_MAX_AGE_S + 1
    assert _poll(session, {"x-region-pings": f"us=100,eu=30;age={age}"}).photon_region == "us"
    assert [s[3] for s in issuance] == ["us"]


@pytest.mark.parametrize("headers", [{}, {"x-region-pings": "us=100,eu=30;age=-1"}, {"x-region-pings": "garbage"}])
def test_control_a_stale_snapshot_stays_stale_without_a_valid_header(issuance, headers):
    """Negative control (#391): an absent or refused header overlays nothing —
    the stale stored map stays stale and the ladder answers."""
    stale = _now() - timedelta(seconds=main.REGION_PINGS_ISSUANCE_MAX_AGE_S + 1)
    fresh = _now() - timedelta(seconds=10)
    session = FakeIssuanceSession(_pair(FRESH_MAP, FRESH_MAP_PARTNER, stale, fresh), ME_STEAM)
    resp = _poll(session, headers)
    assert resp.photon_region == "us"
    assert issuance == [(ME, PARTNER, resp.room_name, "us")]
    assert not any("region_pings" in p for _, p in session.heartbeats)


def test_the_overlay_sits_between_the_header_heartbeat_and_the_chooser():
    src = inspect.getsource(main.queue_poll)
    heartbeat = src.index("make_interval(secs => :region_pings_age)")
    overlay = src.index('entry["region_pings_at"] = now - timedelta(seconds=_hdr_age)')
    chooser = src.index("chosen_region = _pick_room_region(")
    assert heartbeat < overlay < chooser
    assert src.count('entry["region_pings"] = _hdr_pings') == 1


def test_queue_poll_parses_the_header_after_the_session_gate_and_before_any_statement():
    src = inspect.getsource(main.queue_poll)
    gate = src.index("_strict_steam_session_ok(request, steam_id, db)")
    parse = src.index('_region_pings_from_header(request.headers.get("x-region-pings"))')
    first_stmt = src.index("await db.execute(")
    assert gate < parse < first_stmt
    assert src.count("make_interval(secs => :region_pings_age)") == 1


def test_join_request_schema_accepts_the_fields_loosely():
    """A malformed map must reach the validator, not 422 the join."""
    from schemas import QueueJoinRequest
    req = QueueJoinRequest(steam_id=ME_STEAM, region_pings=["not", "a", "map"], region_pings_age_s="soon")
    assert req.region_pings == ["not", "a", "map"] and req.region_pings_age_s == "soon"
    assert QueueJoinRequest(steam_id=ME_STEAM).region_pings is None
    assert QueueJoinRequest(steam_id=ME_STEAM).region_pings_age_s is None
