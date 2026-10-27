"""Fault injection over the report and policy paths: a read that FAILS must
not read as a successful negative.

Every test here makes one specific statement raise and then asserts the
conservative outcome — a retryable refusal, and nothing committed. The suite
this file joins had 1583 passing tests over the same code while every one of
these paths was wrong, because none of them injected a fault: the defects all
live in `except` arms, and a suite that only exercises the happy path cannot
reach an `except` arm at all.

The session is emulated rather than real (the repo has no database fixture),
and the emulation models the one property that makes these paths subtle: a
failed statement leaves the transaction ABORTED until a savepoint that
encloses it exits on the exception. That is why the production code wraps
these reads in `begin_nested()` — the savepoint is what lets the handler
answer at all instead of dying on some later statement.

Each closure here has a mutation control recorded in the round's notes: the
closure was reverted with a one-line edit, the test named in the comment was
re-run and observed RED, and the closure was restored.
"""
import asyncio
import re
from pathlib import Path

import pytest
from fastapi import HTTPException

import main


API = Path(__file__).resolve().parents[1] / "api"
SRC = (API / "main.py").read_text(encoding="utf-8")


def run(coro):
    return asyncio.run(coro)


# ── the emulated session ─────────────────────────────────────────────────

class _Result:
    def __init__(self, rows=()):
        self._rows = [dict(r) for r in rows]

    def mappings(self):
        return self

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        if self._rows and set(self._rows[0]) == {"_scalar"}:
            return [r["_scalar"] for r in self._rows]
        return list(self._rows)

    def scalar(self):
        if not self._rows:
            return None
        return list(self._rows[0].values())[0]

    def scalar_one_or_none(self):
        return self.scalar()


class _Savepoint:
    """Models PostgreSQL: a failed statement aborts the transaction, and the
    enclosing savepoint clears that on the way out. It never swallows —
    whether a failure is survivable is the caller's decision, and telling the
    two apart is the whole subject of this file."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.savepoints += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.session.aborted = False
        return False


class FaultSession:
    """Raises for any statement containing one of `fail_on`; answers the rest
    from `rows` (first matching fragment wins)."""

    def __init__(self, fail_on=(), rows=()):
        self.fail_on = list(fail_on)
        self.rows = list(rows)          # [(fragment, [row, ...]), ...]
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.savepoints = 0
        self.flushes = 0
        self.added = []
        self.aborted = False

    def begin_nested(self):
        return _Savepoint(self)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1
        self.aborted = False

    async def flush(self):
        self.flushes += 1

    def add(self, obj):
        self.added.append(obj)

    def expire(self, obj, cols=None):
        pass

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        if self.aborted:
            raise RuntimeError("current transaction is aborted "
                               "(InFailedSQLTransaction)")
        for frag in self.fail_on:
            if frag in sql:
                self.aborted = True
                raise RuntimeError("injected fault: %s" % frag)
        for frag, rows in self.rows:
            if frag in sql:
                return _Result(rows)
        return _Result([])

    def issued(self, fragment):
        return sum(fragment in s for s in self.statements)


class _State:
    pass


class _Url:
    path = "/api/v1/matches"


class FakeRequest:
    def __init__(self, token="tok"):
        self.headers = {"X-Session-Token": token} if token else {}
        self.state = _State()
        self.url = _Url()


# ── H main.py: the session lookup answers 503, never soft-admit, never 401 ─

def _arm_enforcement(monkeypatch, version):
    monkeypatch.setenv("STEAM_AUTH_ENFORCE", "1")
    monkeypatch.setenv("STEAM_WEB_API_KEY", "k")
    token = main._current_mod_version.set(version)
    return token


def test_session_lookup_fault_refuses_retryably_and_never_soft_admits():
    """Control: restore `reason = "lookup_undetermined"` in
    _check_steam_session's session-lookup handler -> RED (no exception, the
    call returns and the caller proceeds to write)."""
    req = FakeRequest()
    db = FaultSession(fail_on=["FROM steam_sessions"])
    with pytest.raises(HTTPException) as exc:
        run(main._check_steam_session(req, "76561198000000001", db))
    assert exc.value.status_code == 503, "a read that did not complete is not a verdict"
    assert exc.value.detail == "session_check_unavailable"
    # The failure is CONTAINED: the savepoint ran and the transaction is
    # usable, so the 503 is this function's answer and not a later casualty.
    assert db.savepoints == 1 and db.aborted is False
    assert db.commits == 0
    assert main._session_was_verified(req) is False


def test_session_lookup_fault_does_not_answer_401_when_enforcement_is_armed(monkeypatch):
    """The other wrong answer. With enforcement armed, the fall-through the
    previous shape used reached `raise HTTPException(401)`, which states the
    token is invalid — a claim no completed read supports, and one the client
    treats as permanent instead of retrying.

    Control: same one-line revert as above -> RED (401 instead of 503)."""
    tok = _arm_enforcement(monkeypatch, "9.9.9")
    try:
        req = FakeRequest()
        db = FaultSession(fail_on=["FROM steam_sessions"])
        with pytest.raises(HTTPException) as exc:
            run(main._check_steam_session(req, "76561198000000001", db))
        assert exc.value.status_code == 503
        assert exc.value.status_code != 401
    finally:
        main._current_mod_version.reset(tok)


def test_session_lookup_success_paths_are_unchanged(monkeypatch):
    """Negative control (#391): the closure must not turn ordinary outcomes
    into 503. A verified row still returns, and a missing token still
    soft-fails while enforcement is off."""
    req = FakeRequest()
    db = FaultSession(rows=[("FROM steam_sessions",
                             [{"steam_id": "76561198000000001", "verified": True,
                               "expires_at": None}])])
    run(main._check_steam_session(req, "76561198000000001", db))
    assert main._session_was_verified(req) is True

    monkeypatch.delenv("STEAM_AUTH_ENFORCE", raising=False)
    req2 = FakeRequest(token=None)
    db2 = FaultSession()
    run(main._check_steam_session(req2, "76561198000000001", db2))
    assert db2.issued("FROM steam_sessions") == 0
    assert main._session_was_verified(req2) is False


# ── H main.py: a fault reading the per-account arming state refuses ───────

def test_arming_read_fault_refuses_and_does_not_let_the_mutation_proceed(monkeypatch):
    """Enforcement armed, key set, caller claiming a below-floor version — the
    exact state in which the arming row is the only thing that decides whether
    the version carve-out applies. A fault reading it used to resolve to "not
    armed", i.e. the carve-out stands and the guarded mutation proceeds.

    Control: replace the raise with `pass` in the per-account arm handler ->
    RED (the call returns and the report continues)."""
    tok = _arm_enforcement(monkeypatch, "0.0.1")
    try:
        req = FakeRequest()
        db = FaultSession(
            fail_on=["steam_auth_seen_at IS NOT NULL"],
            rows=[("WHERE token_hash", [])],          # unknown token -> not verified
        )
        with pytest.raises(HTTPException) as exc:
            run(main._check_steam_session(req, "76561198000000001", db))
        assert exc.value.status_code == 503
        assert exc.value.detail == "session_check_unavailable"
        assert db.issued("steam_auth_seen_at IS NOT NULL") == 1
        assert db.commits == 0
        assert main._session_was_verified(req) is False
    finally:
        main._current_mod_version.reset(tok)


# ── H main.py: the early series lock fails the report, never continues ────

class _StubSeries:
    def __init__(self, sid="11111111-1111-1111-1111-111111111111",
                 is_tournament=False):
        self.id = sid
        self.is_tournament = is_tournament
        self.player1_id = "p1"
        self.player2_id = "p2"
        self.winner_id = "p1"
        self.p1_rating_change = None
        self.p2_rating_change = None


def _stub_series_lookup(monkeypatch, series):
    async def _find(db, a, b, room_id=None):
        return series

    async def _gate(db, s):
        return None

    async def _open(db, mid):
        return None

    monkeypatch.setattr(main, "_find_current_active_series", _find)
    monkeypatch.setattr(main, "_acquire_tournament_report_action_gate", _gate)
    monkeypatch.setattr(main, "_assert_tournament_report_match_open", _open)


def test_early_series_lock_timeout_refuses_instead_of_continuing(monkeypatch):
    """A lock wait that times out is the ordinary way this statement fails.
    The swallow let the report continue through every line the lock exists to
    cover, so a wager placed in that window settled against the result the
    same request was recording.

    Control: restore `print("[SERIES-LOCK] early lock skipped: ...")` in place
    of the raise -> RED (no exception; the helper returns None)."""
    _stub_series_lookup(monkeypatch, _StubSeries())
    db = FaultSession(fail_on=["FOR NO KEY UPDATE"])
    with pytest.raises(HTTPException) as exc:
        run(main._take_early_series_lock(db, "p1", "p2", "ranked_x_000000_r1"))
    assert exc.value.status_code == 503
    assert exc.value.detail == "series_lock_unavailable"
    assert db.commits == 0
    assert db.savepoints == 1 and db.aborted is False


def test_early_series_lock_passes_a_decided_answer_through(monkeypatch):
    """Negative control: a 409 from the closed-bracket assertion is a decided
    answer and must not be restated as an availability problem."""
    series = _StubSeries(is_tournament=True)
    _stub_series_lookup(monkeypatch, series)

    async def _closed(db, mid):
        raise HTTPException(status_code=409, detail="Tournament match is closed")

    monkeypatch.setattr(main, "_assert_tournament_report_match_open", _closed)
    db = FaultSession()
    with pytest.raises(HTTPException) as exc:
        run(main._take_early_series_lock(db, "p1", "p2", "ranked_x_000000_r1"))
    assert exc.value.status_code == 409


def test_early_series_lock_is_clean_when_there_is_no_series(monkeypatch):
    """Negative control: the common case (no current series) still returns."""
    _stub_series_lookup(monkeypatch, None)
    db = FaultSession()
    run(main._take_early_series_lock(db, "p1", "p2", None))
    assert db.issued("FOR NO KEY UPDATE") == 0


# ── H main.py: a rating-pass fault rolls the report back ──────────────────

class _StubPlayer:
    def __init__(self, pid, steam_id):
        self.id = pid
        self.steam_id = steam_id


def test_rating_pass_lock_fault_propagates_and_commits_nothing():
    """The named scenario: make the first players lock raise on a deciding
    ranked report. The old shape swallowed it after the match had already
    committed, so the report answered 200 with no Glicko update, no
    rating_history rows and no rating achievement.

    Control: wrap _apply_series_rating_pass's body in try/except Exception:
    print(...) -> RED (no exception raised)."""
    db = FaultSession(fail_on=["FROM players WHERE id = :pid FOR NO KEY UPDATE"])
    with pytest.raises(RuntimeError):
        run(main._apply_series_rating_pass(
            db, _StubSeries(), _StubPlayer("a", "1"), _StubPlayer("b", "2")))
    assert db.commits == 0
    # No savepoint of its own: the pass is part of the caller's transaction
    # now, so its failure is meant to reach the caller rather than be
    # contained and reported as success.
    assert db.savepoints == 0


def test_rating_pass_glicko_read_fault_propagates_and_commits_nothing():
    """The other half of the same scenario — the Glicko SELECT rather than the
    lock. Same control."""
    db = FaultSession(fail_on=["FROM glicko_ratings"])
    with pytest.raises(RuntimeError):
        run(main._apply_series_rating_pass(
            db, _StubSeries(), _StubPlayer("a", "1"), _StubPlayer("b", "2")))
    assert db.commits == 0


def test_rating_pass_locks_players_in_sorted_order_before_glicko():
    """The order the merge has to preserve: players (sorted, FOR NO KEY
    UPDATE) before glicko_ratings, which is the order admin_reverse_series
    takes. FOR UPDATE would conflict with every FK insert naming these
    players (#202)."""
    db = FaultSession(fail_on=["FROM glicko_ratings"])
    with pytest.raises(RuntimeError):
        run(main._apply_series_rating_pass(
            db, _StubSeries(), _StubPlayer("b", "1"), _StubPlayer("a", "2")))
    locks = [s for s in db.statements if "FOR NO KEY UPDATE" in s]
    assert len(locks) == 2 and all("FOR UPDATE" not in s.replace("NO KEY UPDATE", "")
                                   for s in locks)
    assert db.statements.index(locks[-1]) < next(
        i for i, s in enumerate(db.statements) if "glicko_ratings" in s)


def test_a_missing_rating_row_is_still_a_successful_negative():
    """Negative control: "this player has no rating row yet" is a completed
    read finding nothing, and must keep returning rather than raising."""
    db = FaultSession()
    applied = run(main._apply_series_rating_pass(
        db, _StubSeries(), _StubPlayer("a", "1"), _StubPlayer("b", "2")))
    assert applied is False
    assert db.commits == 0


def test_the_match_commit_sits_below_the_rating_pass_and_the_grants():
    """The ordering IS the closure for this finding, so it is pinned in
    source: within submit_match, the commit that makes the report durable
    must come after the rating pass and after the slayer/streak grants.

    Control: move `await db.commit()` back above `if series_completed:` ->
    RED."""
    start = SRC.index("async def submit_match(")
    end = SRC.index("\n@app.", start)
    body = SRC[start:end]
    rating = body.index("await _apply_series_rating_pass(")
    grants = body.index('granted_streak |= await _grant_achievement_inline(')
    commit = body.index("await db.commit()", grants)
    assert rating < grants < commit, "the report commits before its finalization"
    # Three commits, and each is accounted for: the anti-cheat invalidation
    # early return, the one report commit, and the tournament advance's own
    # transaction (deliberately still separate — see the note at that site).
    assert body.count("await db.commit()") == 3
    assert body.index("await db.commit()", commit + 1) > body.index(
        "advance_tournament_match(db, series.id)")
    # The cross-gap validity flag belongs to the split shape and is gone as
    # code; it survives only in the note explaining why it went.
    code = "\n".join(ln for ln in body.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "_series_still_valid" not in code


# ── H main.py: podium membership never decided from a stale copy ──────────

def _warm_podium(cache, ids):
    cache["ids"] = list(ids)
    cache["map"] = {pid: i + 1 for i, pid in enumerate(ids)}
    cache["ok"] = True
    cache["at"] = main.time.monotonic() - 3600.0   # stale: forces a refresh
    cache["refresh_failed"] = False


def test_podium_refresh_fault_refuses_the_award_but_still_renders(monkeypatch):
    """Cache the loser at #3, move them off the podium, fault the refresh, then
    report their series loss: the award used to double the winner's gold from
    membership nobody re-read.

    Control: delete the `if _podium_cache["refresh_failed"]: raise` guard in
    _podium_map_for_award -> RED (the stale map is returned)."""
    _warm_podium(main._podium_cache, ["loser-id", "x", "y"])
    db = FaultSession(fail_on=["FROM glicko_ratings"])

    with pytest.raises(HTTPException) as exc:
        run(main._podium_map_for_award(db))
    assert exc.value.status_code == 503
    assert exc.value.detail == "podium_unavailable"
    assert main._podium_cache["refresh_failed"] is True

    # The COSMETIC accessor keeps the opposite polarity on purpose (#412): a
    # renderer showing last minute's podium is showing a slightly old truth.
    assert "loser-id" in run(main._podium_map(db))


def test_podium_award_passes_when_the_refresh_completes(monkeypatch):
    """Negative control: a completed refresh must not refuse."""
    async def _no_grant(ids):
        return None

    monkeypatch.setattr(main, "_grant_podium_titles", _no_grant)
    _warm_podium(main._podium_cache, ["old"])
    db = FaultSession(rows=[("FROM glicko_ratings", [{"_scalar": "fresh"}])])
    assert run(main._podium_map_for_award(db)) == {"fresh": 1}
    assert main._podium_cache["refresh_failed"] is False


def test_a_title_sync_failure_does_not_mark_the_podium_unfetched(monkeypatch):
    """The two failures mean different things, so they are recorded
    separately: the podium read completed even when the holder sync did not."""
    async def _boom(ids):
        raise RuntimeError("shop write failed")

    monkeypatch.setattr(main, "_grant_podium_titles", _boom)
    _warm_podium(main._podium_cache, ["old"])
    db = FaultSession(rows=[("FROM glicko_ratings", [{"_scalar": "fresh"}])])
    assert run(main._podium_map_for_award(db)) == {"fresh": 1}


def test_ovt_podium_refresh_fault_refuses_the_award(monkeypatch):
    """The 1v2 twin: stale membership inflated XP and the gold derived from it.

    Control: delete the guard in _ovt_podium_ids_for_award -> RED."""
    main._ovt_podium_cache["ids"] = ["duo-member"]
    main._ovt_podium_cache["ok"] = True
    main._ovt_podium_cache["at"] = main.time.monotonic() - 3600.0
    main._ovt_podium_cache["refresh_failed"] = False
    db = FaultSession(fail_on=["FROM ovt_matches"])

    with pytest.raises(HTTPException) as exc:
        run(main._ovt_podium_ids_for_award(db))
    assert exc.value.status_code == 503
    assert "duo-member" in run(main._ovt_podium_ids(db))    # cosmetic polarity


def test_ovt_tier_rating_read_fault_propagates():
    """1v2's rating fetch now matches 2v2's: a failed read raises rather than
    substituting 1500, which `_tier_mult_for` pays at Intermediate x1.5.

    Control: restore the `print(... defaulting 1500)` swallow -> RED."""
    db = FaultSession(fail_on=["FROM glicko_ratings"])
    with pytest.raises(RuntimeError):
        run(main._ovt_tier_ratings(db, "a", "b", "c"))
    assert db.commits == 0
    assert db.savepoints == 1 and db.aborted is False


# ── H main.py: the service-UUID cache honours its own age bound ───────────

def _set_service_cache(uuids, refresh_age, fill_age):
    now = main.time.monotonic()
    main._service_player_uuid_cache = set(uuids)
    main._service_uuid_cache_monotonic = now - refresh_age
    main._service_uuid_cache_filled_monotonic = now - fill_age


def test_service_uuid_cache_refuses_once_the_fill_is_past_its_age_bound():
    """A service players row replaced while the refresh keeps failing: the old
    UUID stops naming that account, and an unbounded reuse lets a UUID-only
    guard pass the replacement.

    Control: delete the age-bound raise in _service_player_uuids -> RED (the
    stale set is returned)."""
    _set_service_cache({"old-uuid"}, refresh_age=4000.0, fill_age=4000.0)
    db = FaultSession(fail_on=["FROM players"])
    with pytest.raises(HTTPException) as exc:
        run(main._service_player_uuids(db))
    assert exc.value.status_code == 503
    assert exc.value.detail == "service_policy_unavailable"


def test_service_uuid_cache_still_serves_a_fill_inside_its_age_bound():
    """The other arm, and the reason the bound is two numbers rather than one:
    a refresh is attempted at 50 minutes and the fill is good to 60, so a
    transient fault in that window keeps answering instead of refusing every
    guarded call."""
    _set_service_cache({"good-uuid"}, refresh_age=3100.0, fill_age=3100.0)
    db = FaultSession(fail_on=["FROM players"])
    assert run(main._service_player_uuids(db)) == {"good-uuid"}


def test_service_uuid_cache_never_answers_from_an_empty_fill():
    """Pre-existing closure, pinned here because the age bound sits beside it:
    an empty set makes the call site's intersection match nothing, which is
    the refusal guard answering "allowed" for every account. An empty fill is
    never a fallback, whatever its age."""
    _set_service_cache(set(), refresh_age=4000.0, fill_age=10.0)
    db = FaultSession(fail_on=["FROM players"])
    with pytest.raises(HTTPException) as exc:
        run(main._service_player_uuids(db))
    assert exc.value.status_code == 503


def test_an_empty_fill_does_not_backdate_the_age_stamp():
    """The empty-result branch moves the REFRESH schedule backwards so the
    next call re-asks in ~60s. Computing the age from that moved stamp would
    report a fill as nearly an hour old the instant it was taken, and the
    very next failing refresh would then refuse."""
    main._service_player_uuid_cache = None
    main._service_uuid_cache_filled_monotonic = None
    db = FaultSession(rows=[("FROM players", [])])
    assert run(main._service_player_uuids(db)) == set()
    now = main.time.monotonic()
    assert now - main._service_uuid_cache_filled_monotonic < 5.0
    assert now - main._service_uuid_cache_monotonic > 2900.0


# ── M main.py: a failed rank-colour read is not retried on every render ───

def _reset_rank_cache():
    main._rank_colors_cache["ok"] = False
    main._rank_colors_cache["at"] = 0.0
    main._rank_colors_cache["map"] = {}
    main._rank_colors_cache["failed_at"] = None


def test_a_failed_rank_colour_read_is_suppressed_for_the_ttl():
    """Persistently unavailable colours used to re-issue the same failing
    SELECT and the same log line on every render call, across ~21 sites.

    Control: delete the `failed_at` early return in _rank_colors -> RED (two
    statements instead of one)."""
    _reset_rank_cache()
    db = FaultSession(fail_on=["rank_role_colors"])
    assert run(main._rank_colors(db)) == {}
    assert db.issued("rank_role_colors") == 1
    assert run(main._rank_colors(db)) == {}
    assert db.issued("rank_role_colors") == 1, "the failed read was repeated"
    # Bounded, and a push clears it outright.
    main._rank_colors_invalidate()
    assert run(main._rank_colors(db)) == {}
    assert db.issued("rank_role_colors") == 2


def test_suppression_expires_and_a_success_clears_it(monkeypatch):
    """Negative control: the suppression is a window, not a latch."""
    _reset_rank_cache()
    clock = {"t": 1000.0}
    monkeypatch.setattr(main.time, "monotonic", lambda: clock["t"])
    db = FaultSession(fail_on=["rank_role_colors"])
    run(main._rank_colors(db))
    assert db.issued("rank_role_colors") == 1
    clock["t"] += 400.0
    db.fail_on = []
    db.rows = [("rank_role_colors", [])]
    run(main._rank_colors(db))
    assert db.issued("rank_role_colors") == 2
    assert main._rank_colors_cache["failed_at"] is None


# ── L main.py: a pushed colour wins inside the first 300s of uptime ───────

def test_a_pushed_colour_invalidates_before_the_process_has_been_up_a_ttl(monkeypatch):
    """`at = 0.0` alone invalidated nothing while uptime was under the TTL:
    `ok` stayed True and `now - 0.0 > 300` is False at t=120, so the pushed
    colour did not serve until the process had been up five minutes.

    Control: drop `ok = False` from _rank_colors_invalidate -> RED (the old
    colour is served)."""
    clock = {"t": 60.0}
    monkeypatch.setattr(main.time, "monotonic", lambda: clock["t"])
    _reset_rank_cache()
    db = FaultSession(rows=[("rank_role_colors", [])])
    run(main._rank_colors(db))                       # fills at t=60
    main._rank_colors_cache["map"] = {"Bronze": "#old"}

    clock["t"] = 120.0                               # still inside the TTL
    main._rank_colors_invalidate()

    class _Row:
        name = "Bronze"
        color_hex = "#new"

    db2 = FaultSession(rows=[("rank_role_colors", [{"_scalar": _Row()}])])
    assert run(main._rank_colors(db2)) == {"Bronze": "#new"}
    assert db2.issued("rank_role_colors") == 1


def test_the_push_route_invalidates_through_the_helper():
    """Reachability (#286): the fix is only worth anything if the bot's push
    is what calls it. Pinned in source because the route commits."""
    start = SRC.index("async def push_rank_role_colors(")
    end = SRC.index("\n@app.", start)
    body = SRC[start:end]
    assert "_rank_colors_invalidate()" in body
    assert '_rank_colors_cache["at"] = 0.0' not in body, (
        "a bare stamp reintroduces the uptime hole")
    # Exactly one place may write that stamp outside the refresh itself.
    assert SRC.count('_rank_colors_cache["at"] = 0.0') == 1


# ── the shape claims this round makes about main.py ──────────────────────

def test_no_handler_in_the_repaired_set_still_swallows_its_read():
    """Each closure removed a specific `except` arm. Pin the absence of the
    phrases those arms printed, so a revert is visible here rather than only
    in a review."""
    for gone in ("[SERIES-LOCK] early lock skipped",
                 "Series Glicko update error",
                 "Slayer auto-grant error: ",
                 "tier-mult rating fetch failed (defaulting 1500)"):
        assert gone not in SRC, "a swallow this round removed is back: %r" % gone


def test_only_one_caller_may_catch_the_session_check_and_it_is_named():
    """A refusal is only a closure if it reaches the caller (#286). The
    session check now raises 503 on an unreadable read, so any handler that
    catches it turns the refusal back into an admission — with TWO intended
    exceptions, each asserted by name rather than tolerated by silence.

    presence_ping's `in_match` block catches on purpose and in the opposite
    polarity: that claim only ever vetoes destruction and renews a lease, so
    dropping it expires the lease and frees the group, which is the
    self-healing direction (#276).

    _asm_run (the FFA assembly runner, v1.41.0) is the second, named for its
    polarity too: the session check sits inside its deadline try so a slow
    check counts against the assembly deadline, and no handler there turns
    an error into an admission. An HTTPException is rolled back and
    re-raised; anything else is re-raised unless its SQLSTATE maps to an
    assembly stage; and the two handlers that do return -- the one for
    _AsmDeadline, which the session check never raises, and the one for a
    mapped SQLSTATE -- answer 503 asm_deadline, a refusal.

    Control: wrap any other `await _check_steam_session(...)` in a
    `try/except Exception: pass` -> RED."""
    import ast

    tree = ast.parse(SRC)
    enclosing = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            for child in ast.walk(node):
                enclosing.setdefault(id(child), node.name)

    caught = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        swallowing = [h for h in node.handlers
                      if not any(isinstance(n, ast.Raise) for n in ast.walk(h))]
        if not swallowing:
            continue
        for stmt in node.body:
            for n in ast.walk(stmt):
                if (isinstance(n, ast.Call)
                        and getattr(n.func, "id", None) == "_check_steam_session"):
                    caught.append(enclosing.get(id(n)))
    assert caught == ["_asm_run", "presence_ping"], (
        "a handler other than _asm_run or presence_ping catches the session check: %r" % caught)


def test_the_award_paths_use_the_award_polarity_accessors():
    """#412: the point of two accessors is that each consumer picks its
    polarity explicitly. The money decisions must not drift back onto the
    cosmetic ones."""
    series_gold = SRC.index("Podium beaten x2")
    window = SRC[series_gold - 1500:series_gold]
    assert "_podium_map_for_award(db)" in window
    ovt = SRC.index("_ovt_pod = set(await ")
    assert SRC[ovt:ovt + 120].startswith("_ovt_pod = set(await _ovt_podium_ids_for_award(db))")
    # And the renderers keep the cosmetic one.
    assert len(re.findall(r"await _podium_maps_for\(", SRC)) >= 10
