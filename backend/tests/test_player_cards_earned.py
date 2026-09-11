"""Player Cards — earned packs (Sept 10 batch, WP-D). The completion hooks,
the reversal voids and the janitor's reconciler: pinned on main.py's source
where the SITE is the property (inside which branch, inside its own
savepoint, gated on the ranked flag), executed against a scripted session
where the logic is."""
import asyncio
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import database
import main
import player_cards as pc

BACKEND = Path(__file__).resolve().parents[1]
SRC = (BACKEND / "api" / "main.py").read_text(encoding="utf-8")
MIG = (BACKEND / "sql" / "308_player_cards.sql").read_text(encoding="utf-8")

S1 = UUID("11111111-1111-1111-1111-111111111111")
S2 = UUID("22222222-2222-2222-2222-222222222222")
P1 = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
P2 = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
T0 = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.run(coro)


def _fn(name):
    m = re.search(rf"^(?:async )?def {re.escape(name)}\(.*?(?=^(?:async def |def |@|# ──)|\Z)", SRC, re.S | re.M)
    assert m, name
    return m.group(0)


class _Res:
    def __init__(self, rows):
        self.rows = list(rows)

    def mappings(self):
        return self

    def all(self):
        return list(self.rows)

    def fetchall(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def one(self):
        assert len(self.rows) == 1, self.rows
        return self.rows[0]

    def scalar_one_or_none(self):
        row = self.first()
        return None if row is None else next(iter(row.values()))


class Session:
    """execute() answers by the first script key contained in the normalised
    SQL; each key holds a queue of row lists (the last one repeats)."""

    def __init__(self, script=None):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.log = []
        self.committed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.log.append((sql, params))
        for key, queue in self.script.items():
            if key in sql:
                if not queue:
                    return _Res([])
                return _Res(queue.pop(0) if len(queue) > 1 else queue[0])
        return _Res([])

    async def commit(self):
        self.committed += 1

    def sent(self, key):
        return [(sql, p) for sql, p in self.log if key in sql]


# ── the hook sites ────────────────────────────────────────────────────────────

HOOKS = (("submit_match", "1v1"), ("submit_team_match", "team"),
         ("_complete_team_series_with_ratings", "team"), ("submit_ovt_match", "ovt"),
         ("submit_ffa_match", "ffa"))


def test_every_completion_path_rolls_once_inside_its_own_savepoint():
    for name, mode in HOOKS:
        body = _fn(name)
        assert body.count("_pc_grant_earned_packs(") == 1, name
        at = body.index("_pc_grant_earned_packs(")
        pre, post = body[max(0, at - 160):at], body[at:at + 520]
        assert pre.rstrip().endswith("await"), name
        assert "async with db.begin_nested():" in pre and "try:" in pre, name
        assert f'mode="{mode}"' in post and "except Exception as pcex:" in post and "[PC-EARNED]" in post, name
    # the def, five hooks, the reconciler's call — nothing else rolls
    assert SRC.count("_pc_grant_earned_packs(") == 7


def test_the_1v1_roll_sits_in_the_completion_branch_with_the_series_winner():
    body = _fn("submit_match")
    at = body.index("_pc_grant_earned_packs(")
    branch = body.index("if series.p1_series_wins >= 2 or series.p2_series_wins >= 2:")
    tail = body.index('else:\n            series_status = "active"')
    assert branch < at < tail
    call = body[at:at + 300]
    assert "series_id=series.id" in call and "winner_ids=[series.winner_id]" in call
    assert "sweep=_pc_sweep(series.p1_series_wins, series.p2_series_wins)" in call
    # after the bet settlement, never before the result is written
    assert body.index("[BET-SETTLE] error settling") < at


def test_the_team_rolls_follow_the_winning_side_and_a_forfeit_never_sweeps():
    inline = _fn("submit_team_match")
    at = inline.index("_pc_grant_earned_packs(")
    assert inline.index("if series_completed:") < at
    call = inline[at:at + 400]
    assert "series_id=series_uuid" in call and "sweep=_pc_sweep(new_t1w, new_t2w)" in call
    assert '[series["t1a_id"], series["t1b_id"]] if winner_team == 1' in call
    assert 'else [series["t2a_id"], series["t2b_id"]]' in call
    dc = _fn("_complete_team_series_with_ratings")
    at = dc.index("_pc_grant_earned_packs(")
    call = dc[at:at + 400]
    assert "sweep=False" in call and 'label=f"team-{reason}"' in call
    assert "[t1a_id, t1b_id] if winner_team == 1 else [t2a_id, t2b_id]" in call
    # the ids the hook uses are bound at function level, not inside the bet savepoint
    assert dc.index('t1a_id, t1b_id, t2a_id, t2b_id = srow["t1a_id"]') < at


def test_the_1v2_roll_follows_the_completed_update_and_the_winning_side():
    body = _fn("submit_ovt_match")
    at = body.index("_pc_grant_earned_packs(")
    upd = body.index("UPDATE ovt_series SET status='completed', winner_side=:ws, completed_at=NOW()")
    assert body.index("if series_done:") < upd < at
    call = body[at:at + 400]
    assert 'mode="ovt", series_id=series_uuid' in call
    assert "[solo_id] if winner_side == 1 else [duo_a_id, duo_b_id]" in call
    assert "sweep=_pc_sweep(solo_wins, duo_wins)" in call


def test_the_ffa_roll_is_gated_on_the_rated_flag_and_keyed_on_the_match_row():
    body = _fn("submit_ffa_match")
    at = body.index("_pc_grant_earned_packs(")
    gate = body[max(0, at - 200):at]
    assert "if rated:" in gate and gate.index("if rated:") < gate.index("try:")
    call = body[at:at + 400]
    assert 'mode="ffa", series_id=match_id' in call
    assert "winner_ids=[id_by_steam[report.winner_steam_id]]" in call
    assert "sweep=_pc_ffa_sweep(report)" in call
    # the row the reconciler re-derives from is the one this id is written into
    assert body.index("match_id = uuid.uuid4()") < body.index("INSERT INTO ffa_matches") < at
    assert '"ranked": rated' in body


def test_reversal_and_retro_invalidation_void_the_unopened_packs():
    one = _fn("admin_reverse_series")
    assert one.count("_pc_void_earned_packs(") == 1
    assert 'mode="1v1", series_id=series.id, label="admin-reverse"' in one
    assert one.index("series.invalidation_reason = req.reason[:64]") < one.index("_pc_void_earned_packs(")
    team = _fn("admin_reverse_team_series")
    assert team.count("_pc_void_earned_packs(") == 1
    assert 'mode="team", series_id=sid, label="admin-reverse"' in team
    assert team.index('"admin_reverse")[:64]})') < team.index("_pc_void_earned_packs(")
    retro = _fn("_check_anti_cheat")
    assert retro.count("_pc_void_earned_packs(") == 1
    assert 'mode="1v1", series_id=s.id, label="retro-invalidate"' in retro
    assert retro.index('"short_duration_pattern_retro"') < retro.index("_pc_void_earned_packs(")
    # the def and the three sites; every void is fail-soft
    assert SRC.count("_pc_void_earned_packs(") == 4
    for body in (one, team, retro):
        at = body.index("_pc_void_earned_packs(")
        assert "try:" in body[at - 80:at] and "except Exception as pcex:" in body[at:at + 260]


def test_the_janitor_runs_the_reconciler_fail_soft_after_the_snapshot_step():
    loop = _fn("queue_cleanup_loop")
    assert loop.count("await _pc_reconcile_earned_packs()") == 1
    at = loop.index("await _pc_reconcile_earned_packs()")
    assert loop.index("await _pc_snapshot_janitor_step()") < at
    assert "player cards reconcile error" in loop[at:at + 200]
    # both janitor steps open their own session at call time — main.py has
    # no module-level `async_session` (the loops import it at function level)
    assert "from database import async_session" in _fn("_pc_reconcile_earned_packs")
    assert "from database import async_session" in _fn("_pc_snapshot_janitor_step")
    assert not re.search(r"^from database import .*async_session", SRC, re.M)


# ── the helpers ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("a,b,sweep", [(2, 0, True), (0, 2, True), (3, 0, True), (2, 1, False), (1, 0, False),
                                       (0, 0, False), (None, 2, True), ("x", 2, False)])
def test_a_sweep_is_a_series_taken_without_conceding_a_game(a, b, sweep):
    assert main._pc_sweep(a, b) is sweep


def _report(winner, rounds):
    return SimpleNamespace(winner_steam_id=winner,
                           players=[SimpleNamespace(steam_id=s, rounds_won=r) for s, r in rounds.items()])


def test_an_ffa_sweep_is_every_round_to_the_winner_and_none_to_anybody_else():
    assert main._pc_ffa_sweep(_report("w", {"w": 3, "a": 0, "b": 0})) is True
    assert main._pc_ffa_sweep(_report("w", {"w": 3, "a": 1, "b": 0})) is False
    assert main._pc_ffa_sweep(_report("w", {"w": 0, "a": 0})) is False
    assert main._pc_ffa_sweep(_report("zz", {"w": 3, "a": 0})) is False
    assert main._pc_ffa_sweep(_report("w", {"w": 3})) is False
    assert main._pc_ffa_sweep(SimpleNamespace(winner_steam_id="w", players=None)) is False


def test_earned_reference_is_mode_and_series_the_reconciler_can_rebuild():
    assert main._pc_earned_ref("1v1", S1) == f"1v1:{S1}"
    assert main._pc_earned_ref("ffa", str(S1)) == main._pc_earned_ref("ffa", S1)


def _kind(monkeypatch, value):
    calls = []

    def fake(secret, mode, ref, sweep):
        calls.append((secret, mode, ref, sweep))
        return value

    monkeypatch.setattr(pc, "earned_pack_kind", fake)
    return calls


def test_grant_inserts_one_unopened_pack_per_winner_from_one_roll(monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "s3cret")
    calls = _kind(monkeypatch, "sweep")
    db = Session({"INSERT INTO pc_packs": [[{"id": "k1"}], [{"id": "k2"}]]})
    out = _run(main._pc_grant_earned_packs(db, mode="team", series_id=S1, winner_ids=[P1, None, P2],
                                           sweep=1, label="t"))
    assert out == ["k1", "k2"]
    assert calls == [(b"s3cret", "team", str(S1), True)]
    ins = db.sent("INSERT INTO pc_packs")
    assert [p["pid"] for _, p in ins] == [str(P1), str(P2)]
    assert all(p["mode"] == "team" and p["kind"] == "sweep" and p["ref"] == f"team:{S1}" for _, p in ins)
    sql = ins[0][0]
    assert "'earned'" in sql and "'unopened'" in sql
    assert "ON CONFLICT (player_id, source, reference_id) WHERE reference_id IS NOT NULL DO NOTHING" in sql


def test_grant_is_inert_without_the_secret_or_on_a_miss_and_idempotent_on_a_replay(monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "")
    db = Session()
    assert _run(main._pc_grant_earned_packs(db, mode="1v1", series_id=S1, winner_ids=[P1], sweep=False, label="t")) == []
    assert db.log == []
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "s3cret")
    _kind(monkeypatch, None)
    assert _run(main._pc_grant_earned_packs(db, mode="1v1", series_id=S1, winner_ids=[P1], sweep=False, label="t")) == []
    assert db.log == []
    _kind(monkeypatch, "win")
    replay = Session({"INSERT INTO pc_packs": [[]]})   # the conflict clause returned no row
    assert _run(main._pc_grant_earned_packs(replay, mode="1v1", series_id=S1, winner_ids=[P1], sweep=False,
                                            label="t")) == []
    assert len(replay.sent("INSERT INTO pc_packs")) == 1


def test_void_touches_only_that_series_unopened_earned_packs():
    db = Session({"UPDATE pc_packs SET status = 'voided'": [[{"id": "a"}, {"id": "b"}]]})
    assert _run(main._pc_void_earned_packs(db, mode="team", series_id=S2, label="t")) == 2
    (sql, params), = db.sent("UPDATE pc_packs SET status = 'voided'")
    assert params == {"ref": f"team:{S2}"}
    assert "source = 'earned'" in sql and "status = 'unopened'" in sql and "reference_id = CAST(:ref AS text)" in sql
    assert _run(main._pc_void_earned_packs(Session(), mode="team", series_id=S2, label="t")) == 0


# ── the reconciler ────────────────────────────────────────────────────────────

def _reconciler(monkeypatch, script):
    db = Session(script)
    monkeypatch.setattr(database, "async_session", lambda: db)
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "s3cret")
    monkeypatch.setattr(main, "_pc_reconcile_last_monotonic", 0.0)
    return db


def test_the_first_run_only_plants_the_cursors(monkeypatch):
    db = _reconciler(monkeypatch, {"INSERT INTO pc_reconcile_cursors": [[{"source": "x"}]]})
    _run(main._pc_reconcile_earned_packs(force=True))
    plants = db.sent("INSERT INTO pc_reconcile_cursors")
    assert [p["src"] for _, p in plants] == ["1v1", "team", "ovt", "ffa"]
    assert "ON CONFLICT (source) DO NOTHING RETURNING source" in plants[0][0]
    assert db.sent("SELECT GREATEST(cursor_at") == [] and db.sent("INSERT INTO pc_packs") == []
    assert db.committed == 5   # one per planted source, one for the void sweep
    # the sweep still runs — a series invalidated before the cursor existed still loses its packs
    assert len(db.sent("UPDATE pc_packs p SET status = 'voided'")) == 4


def test_a_later_run_rederives_the_grants_and_advances_each_cursor_to_its_newest_row(monkeypatch):
    calls = _kind(monkeypatch, "win")
    t1, t2 = T0 + timedelta(minutes=5), T0 + timedelta(minutes=9)
    db = _reconciler(monkeypatch, {
        "INSERT INTO pc_reconcile_cursors": [[]],
        "SELECT GREATEST(cursor_at": [[{"since": T0}]],
        "FROM ranked_series rs": [[{"ref": S1, "completed_at": t2, "w1": P1, "w2": None, "sweep": True},
                                   {"ref": S2, "completed_at": t1, "w1": P2, "w2": None, "sweep": False}]],
        "FROM team_series ts": [[{"ref": S2, "completed_at": t1, "w1": P1, "w2": P2, "sweep": False}]],
        "INSERT INTO pc_packs": [[{"id": "k"}]],
    })
    _run(main._pc_reconcile_earned_packs(force=True))
    # every scan window starts where the cursor row says
    scans = [p for sql, p in db.log if "> CAST(:since AS timestamptz)" in sql]
    assert [p["since"] for p in scans] == [T0] * 4
    assert calls == [(b"s3cret", "1v1", str(S1), True), (b"s3cret", "1v1", str(S2), False),
                     (b"s3cret", "team", str(S2), False)]
    ins = db.sent("INSERT INTO pc_packs")
    assert [(p["mode"], p["pid"]) for _, p in ins] == [("1v1", str(P1)), ("1v1", str(P2)),
                                                       ("team", str(P1)), ("team", str(P2))]
    moves = db.sent("UPDATE pc_reconcile_cursors SET cursor_at")
    assert [(p["src"], p["at"]) for _, p in moves] == [("1v1", t2), ("team", t1)]
    assert "GREATEST(cursor_at, CAST(:at AS timestamptz))" in moves[0][0]
    assert db.committed == 5
    assert len(db.sent("UPDATE pc_packs p SET status = 'voided'")) == 4


def test_the_cursor_window_and_the_void_sweep_are_pinned_in_the_sql():
    for source, sql in main._PC_RECONCILE_SQL.items():
        flat = " ".join(sql.split())
        assert "invalidated_at IS NULL" in flat and "> CAST(:since AS timestamptz)" in flat, source
        assert "LIMIT" not in flat, source
        assert " AS ref, " in flat and " AS w1, " in flat and " AS w2," in flat and " AS sweep " in flat, source
    assert set(main._PC_RECONCILE_SQL) == set(main._PC_VOID_SWEEP_SQL) == {"1v1", "team", "ovt", "ffa"}
    for source, sql in main._PC_VOID_SWEEP_SQL.items():
        flat = " ".join(sql.split())
        assert f"p.mode = '{source}'" in flat and f"CONCAT('{source}:', CAST(s.id AS text))" in flat, source
        assert "p.source = 'earned' AND p.status = 'unopened'" in flat and "s.invalidated_at IS NOT NULL" in flat, source
    ffa = " ".join(main._PC_RECONCILE_SQL["ffa"].split())
    assert "fp.player_id <> fm.winner_id AND fp.rounds_won > 0" in ffa and "fm.is_ranked" in ffa
    body = _fn("_pc_reconcile_earned_packs")
    assert "GREATEST(cursor_at - INTERVAL '24 hours', started_at) AS since" in body and "FOR UPDATE" in body


def test_the_cadence_gate_skips_a_run_inside_the_interval(monkeypatch):
    def boom():
        raise AssertionError("no session inside the interval")

    monkeypatch.setattr(database, "async_session", boom)
    monkeypatch.setattr(main, "_pc_reconcile_last_monotonic", time.monotonic())
    _run(main._pc_reconcile_earned_packs())
    assert main.PC_RECONCILE_EVERY_S == 600


def test_the_migration_carries_the_cursor_table_and_the_void_columns():
    assert "CREATE TABLE IF NOT EXISTS pc_reconcile_cursors" in MIG
    cur = MIG[MIG.index("CREATE TABLE IF NOT EXISTS pc_reconcile_cursors"):][:400]
    assert "source      TEXT PRIMARY KEY" in cur and "cursor_at   TIMESTAMPTZ NOT NULL" in cur
    assert "started_at  TIMESTAMPTZ NOT NULL DEFAULT now()" in cur
    packs = MIG[MIG.index("CREATE TABLE IF NOT EXISTS pc_packs"):][:1600]
    assert "voided_at" in packs and "mode " in packs and "reference_id" in packs
    assert "pc_packs_player_source_ref ON pc_packs (player_id, source, reference_id)" in MIG
