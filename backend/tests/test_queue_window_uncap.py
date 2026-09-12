"""1v1 ranked window uncap + rejoin clock (Sept 12).

Two decisions: (1) the stepped window (100/200/400) stops bounding at 120 s
instead of capping at +/-800 — still both seats' own clocks; (2) a seat that
leaves and rejoins within 30 s keeps its wait clock. The pure helpers are
executed with a negative control each (#391); the SQL operation is pinned by
counting the predicate inside the function span (#432), never file-wide.
Codex r1/r2 shaped the lifecycle: the kept clock lives in ranked_queue.wait_since
(migration 309) so joined_at stays the insert time the cross-queue eviction
fences on; the leave notes BEFORE its commit; the join looks up AFTER its
upsert and fixes the row up in the same transaction; the entry is consumed by
identity. Those orders are pinned here too.
"""

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import main
from schemas import QueuePollResponse

ME = UUID("11111111-1111-1111-1111-111111111111")
OTHER = UUID("22222222-2222-2222-2222-222222222222")
T0 = datetime(2026, 9, 12, 0, 0, tzinfo=timezone.utc)
CLOCK = "COALESCE(wait_since, joined_at)"


def test_ranked_window_ladder_and_uncap():
    assert main.compute_ranked_window(0) == 100
    assert main.compute_ranked_window(29) == 100
    assert main.compute_ranked_window(30) == 200
    assert main.compute_ranked_window(59) == 200
    assert main.compute_ranked_window(60) == 400
    assert main.compute_ranked_window(119) == 400          # negative control for the uncap
    assert main.compute_ranked_window(120) is None
    assert main.compute_ranked_window(3600) is None
    assert main.RANKED_WINDOW_UNCAPPED_SECONDS == 120


def test_window_binds_switch_and_bounds():
    # executed with a negative control: an inverted switch fails here, not in prod
    assert main._ranked_window_binds(2500, None) == (True, 2500, 2500)
    assert main._ranked_window_binds(2500, 400) == (False, 2100, 2900)
    assert main._ranked_window_binds(2500, 100) == (False, 2400, 2600)
    assert main._ranked_window_binds(1500, 400)[0] is False


def test_team_queue_ladder_unchanged():
    # The uncap is a 1v1 decision; the 2v2 queue keeps the capped ladder.
    assert main.compute_elo_range(120) == 800
    assert main.compute_elo_range(119) == 400
    src = inspect.getsource(main.team_queue_poll)
    assert "compute_elo_range(wait_seconds)" in src
    assert "compute_ranked_window(" not in src
    assert "_ranked_window_binds(" not in src
    assert "wait_since" not in src


def test_poll_uses_the_uncapped_window_sql():
    src = inspect.getsource(main.queue_poll)
    assert src.count("compute_ranked_window(wait_seconds)") == 1
    assert src.count("my_uncapped, min_rating, max_rating = _ranked_window_binds(my_rating, elo_range)") == 1
    assert "compute_elo_range(" not in src
    # my side: the typed boolean short-circuits the bounds
    assert src.count("AND (CAST(:my_uncapped AS boolean) OR rating BETWEEN :rmin AND :rmax)") == 1
    # their side: no bound from 120 s off THEIR wait clock, the ladder below it
    assert src.count(f"AND (EXTRACT(EPOCH FROM (now() - {CLOCK})) >= 120") == 1
    assert "THEN 800" not in src
    assert src.count(f"WHEN EXTRACT(EPOCH FROM (now() - {CLOCK})) >= 60 THEN 400") == 2
    assert src.count(f"WHEN EXTRACT(EPOCH FROM (now() - {CLOCK})) >= 30 THEN 200") == 2
    assert "now() - joined_at" not in src               # no bare insert-time clock left
    # my own row carries the kept clock (both row SELECTs) and the wait uses it
    assert src.count("rq.ready, rq.joined_at, rq.wait_since, rq.matched_at,") == 2
    assert "rq.ready, rq.joined_at, rq.matched_at" not in src
    assert src.count('wait_seconds = int((now - (entry["wait_since"] or entry["joined_at"])).total_seconds())') == 1
    assert 'now - entry["joined_at"]' not in src
    # a seat that stopped polling (the janitor sweeps it at 30 s) is not a partner
    assert src.count("AND last_polled > NOW() - INTERVAL '15 seconds'") == 1
    assert '"my_uncapped": my_uncapped' in src
    # the wire: the legacy cap for old clients + the real flag
    assert "elo_range=elo_range if elo_range is not None else RANKED_WINDOW_LEGACY_CAP" in src
    assert "elo_unbounded=(elo_range is None)" in src
    assert main.RANKED_WINDOW_LEGACY_CAP == 800


def test_poll_response_carries_the_flag():
    r = QueuePollResponse(status="searching", wait_time=130, queue_size=2,
                          elo_range=800, elo_unbounded=True)
    assert r.elo_unbounded is True
    assert QueuePollResponse(status="searching").elo_unbounded is False


def test_rejoin_clock_kept_within_grace_and_forgotten_by_identity():
    main._ranked_recent_leaves.clear()
    joined = T0 - timedelta(seconds=90)
    main._ranked_note_leave(ME, joined, now=T0)
    entry = main._ranked_peek_rejoin_clock(ME, now=T0 + timedelta(seconds=30))
    assert entry is not None and entry[0] == joined
    # a peek never consumes: a failed join retries with the clock intact
    assert main._ranked_peek_rejoin_clock(ME, now=T0 + timedelta(seconds=30)) is entry
    main._ranked_forget_leave(ME, entry)
    assert ME not in main._ranked_recent_leaves
    assert main._ranked_peek_rejoin_clock(ME, now=T0 + timedelta(seconds=30)) is None
    main._ranked_forget_leave(ME, None)          # nothing to forget is not an error


def test_rejoin_clock_forget_spares_a_newer_leave():
    main._ranked_recent_leaves.clear()
    joined = T0 - timedelta(seconds=90)
    main._ranked_note_leave(ME, joined, now=T0)
    used = main._ranked_peek_rejoin_clock(ME, now=T0 + timedelta(seconds=1))
    # a leave landing between the join's commit and its forget writes a newer entry
    main._ranked_note_leave(ME, joined, now=T0 + timedelta(seconds=2))
    main._ranked_forget_leave(ME, used)
    assert ME in main._ranked_recent_leaves                  # the newer entry survives
    assert main._ranked_recent_leaves[ME] is not used
    # negative control: forgetting the entry actually recorded removes it
    main._ranked_forget_leave(ME, main._ranked_recent_leaves[ME])
    assert ME not in main._ranked_recent_leaves


def test_rejoin_clock_dropped_after_grace():
    main._ranked_recent_leaves.clear()
    main._ranked_note_leave(ME, T0 - timedelta(seconds=90), now=T0)
    assert main._ranked_peek_rejoin_clock(ME, now=T0 + timedelta(seconds=31)) is None
    assert ME not in main._ranked_recent_leaves
    assert main.RANKED_REJOIN_GRACE_SECONDS == 30


def test_rejoin_clock_ignores_a_rowless_leave_and_prunes():
    main._ranked_recent_leaves.clear()
    main._ranked_note_leave(ME, None, now=T0)
    assert main._ranked_recent_leaves == {}
    main._ranked_note_leave(OTHER, T0, now=T0)
    main._ranked_note_leave(ME, T0, now=T0 + timedelta(seconds=61))   # prunes OTHER
    assert OTHER not in main._ranked_recent_leaves
    assert ME in main._ranked_recent_leaves
    main._ranked_recent_leaves.clear()


def test_rejoin_clock_past_the_expiry_cap_is_not_kept():
    main._ranked_recent_leaves.clear()
    cap = main.QUEUE_EXPIRE_MINUTES * 60
    main._ranked_note_leave(ME, T0 - timedelta(seconds=cap), now=T0)
    assert main._ranked_peek_rejoin_clock(ME, now=T0 + timedelta(seconds=5)) is None
    assert ME not in main._ranked_recent_leaves
    # negative control: one second inside the cap is kept
    main._ranked_note_leave(ME, T0 - timedelta(seconds=cap - 6), now=T0)
    assert main._ranked_peek_rejoin_clock(ME, now=T0 + timedelta(seconds=5)) is not None
    main._ranked_recent_leaves.clear()


def test_leave_records_the_effective_clock_before_its_commit():
    src = inspect.getsource(main.queue_leave)
    assert src.count("DELETE FROM ranked_queue WHERE player_id = :pid ") == 1
    assert src.count(f"RETURNING {CLOCK}") == 1
    delete_at = src.index(f"RETURNING {CLOCK}")
    note_at = src.index("_ranked_note_leave(player.id", delete_at)
    commit_at = src.index("await db.commit()", delete_at)
    assert delete_at < note_at < commit_at


def test_join_looks_up_after_the_upsert_and_writes_wait_since_only():
    join = inspect.getsource(main.queue_join)
    upsert_at = join.index("await _queue_join_upsert(")
    peek_at = join.index("_kept = _ranked_peek_rejoin_clock(player.id)")
    fix_at = join.index("UPDATE ranked_queue SET wait_since = CAST(:wait_since AS timestamptz) ")
    commit_at = join.index("await db.commit()", upsert_at)
    forget_at = join.index("_ranked_forget_leave(player.id, _kept)")
    assert upsert_at < peek_at < fix_at < commit_at < forget_at
    assert join.count("_ranked_forget_leave(") == 1
    assert "SET joined_at" not in join                       # the insert time is never rewritten
    # the upsert keeps joined_at = now and clears a stale kept clock on conflict
    up = inspect.getsource(main._queue_join_upsert)
    assert "joined_at=None" not in up
    assert up.count("NULL, false, :now, NULL, :now,") == 1
    assert up.count("joined_at = EXCLUDED.joined_at,") == 1
    assert up.count("wait_since = NULL,") == 1
    assert "joined_at = CASE" not in up


def test_cross_queue_eviction_fence_still_reads_the_insert_time():
    ev = inspect.getsource(main._evict_other_queue_searching)
    assert ev.count("joined_at <= CAST(:jb AS timestamptz)") == 2
    assert "wait_since" not in ev


def test_migration_309_adds_the_column_and_its_incarnation_trigger_in_a_transaction():
    sql = (Path(__file__).resolve().parents[1] / "sql" / "309_ranked_queue_wait_since.sql").read_text()
    assert sql.count("ALTER TABLE ranked_queue ADD COLUMN IF NOT EXISTS wait_since TIMESTAMPTZ;") == 1
    # a kept clock dies with the row incarnation it was attached to, whichever api
    # build moves joined_at (a rolled-back build cannot clear a column it never knew)
    assert sql.count("BEFORE UPDATE OF joined_at ON ranked_queue") == 1
    assert sql.count("IF NEW.joined_at IS DISTINCT FROM OLD.joined_at THEN") == 1
    assert sql.count("NEW.wait_since := NULL;") == 1
    assert sql.count("DROP TRIGGER IF EXISTS ranked_queue_wait_since_reset ON ranked_queue;") == 1
    assert sql.count("CREATE TRIGGER ranked_queue_wait_since_reset") == 1
    assert (sql.index("BEGIN;") < sql.index("ALTER TABLE") < sql.index("CREATE OR REPLACE FUNCTION")
            < sql.index("CREATE TRIGGER") < sql.index("COMMIT;"))   # #340
