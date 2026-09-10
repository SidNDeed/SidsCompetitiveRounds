"""Sept 10 WP-B: the server data path of the multiplayer room-region pick.

The rule itself is pure (backend/api/region_pick.py, test_group_region_pick.py).
This file covers what main.py wraps around it:

  * the optional X-Region-Pings-Gen header and the generation rule that
    decides which of two maps is newer — one Python function
    (`_region_pings_newer`, used by the issuance overlay) and one SQL WHERE
    (`_REGION_PINGS_UPSERT_SQL`, used by the store), pinned together;
  * `_region_pings_store`, EXECUTED against a fake session factory: the
    shared identity lock, the typed single-statement upsert resolving the
    row by the AUTHENTICATED steam id, silence without a valid header or a
    verified session, and a failed store that still returns the overlay;
  * `_group_region`, EXECUTED against fake stored rows: the pick moves on
    fresh maps, stays on quorum failure, decodes JSON text, applies the
    caller's overlay only when it would have replaced the stored row, falls
    back to the legacy pick on a read error, and prints one [GROUP-REGION]
    line on every branch;
  * structure pins in the style of test_room_region_symmetry.py: every
    writer stores BEFORE it takes a queue-row lock (the deadlock-order
    invariant), every issuance site asks the rule exactly once and the old
    mode-of-homes / first-non-empty shapes occur ZERO times (#432), the
    janitor purge and the delete-my-data row, and migration 307.
"""

import asyncio
import inspect
import io
import tokenize
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import database
import main

MAIN_PY = Path(__file__).resolve().parents[1] / "api" / "main.py"
MIGRATION = Path(__file__).resolve().parents[1] / "sql" / "307_player_region_pings.sql"

A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
C = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
STEAM = "76561198000000007"

NEAR = {"us": 60, "eu": 35}     # eu beats us by 25 for this seat
FAR = {"us": 60, "eu": 300}     # eu is unplayable for this seat


def _run(coro):
    return asyncio.run(coro)


def _now():
    return datetime.now(timezone.utc)


def _request(pings=None, gen=None, verified=True):
    headers = {}
    if pings is not None:
        headers["X-Region-Pings"] = pings
    if gen is not None:
        headers["X-Region-Pings-Gen"] = gen
    return SimpleNamespace(headers=headers, state=SimpleNamespace(scr_session_verified=verified))


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def mappings(self):
        return self

    def __iter__(self):
        return iter(self._rows)

    def fetchall(self):
        return list(self._rows)


class FakeSession:
    """One session per `async with`: records (sql, params), answers the
    stored-rows SELECT from `rows`, raises `fail` on any statement."""

    def __init__(self, log, rows=(), fail=None):
        self.log, self.rows, self.fail = log, list(rows), fail
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.log.append((sql, dict(params or {})))
        if self.fail is not None:
            raise self.fail
        if sql.startswith("SELECT player_id, pings"):
            return _Rows(self.rows)
        return _Rows([])

    async def commit(self):
        self.committed = True


def _factory(monkeypatch, log, rows=(), fail=None):
    sessions = []

    def make():
        s = FakeSession(log, rows, fail)
        sessions.append(s)
        return s

    # main imports `async_session` from database at CALL time.
    monkeypatch.setattr(database, "async_session", make)
    return sessions


# ── the generation header and the newer-map rule ─────────────────────────────

def test_gen_header_parser_admits_only_nonce_colon_seq():
    assert main._region_pings_gen_from_header("0123abcd:7") == ("0123abcd", 7)
    assert main._region_pings_gen_from_header(" 0123abcdef012345:000012 ") == ("0123abcdef012345", 12)
    for bad in (None, "", 7, "0123ABCD:7", "0123abc:7", "0123abcd:", "0123abcd:x",
                "0123abcd", "0123abcd:7:1", "a" * 33 + ":1", "0123abcd:1234567890", "x" * 60):
        assert main._region_pings_gen_from_header(bad) is None, bad


T0 = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(seconds=30)
NEWER_CASES = [
    # (gen, measured_at, old_gen, old_measured_at) -> replaces?
    ((("n1", 5), T0, None, None), True),            # nothing stored
    ((("n1", 5), T0, None, T1), True),              # stored without a generation: a generation wins
    ((("n1", 5), T0, ("n0", 9), T1), True),         # a new nonce always wins, whatever the clocks say
    ((("n1", 6), T0, ("n1", 5), T1), True),         # same nonce, greater seq
    ((("n1", 5), T1, ("n1", 5), T0), False),        # same nonce, same seq: never (a resend)
    ((("n1", 4), T1, ("n1", 5), T0), False),        # same nonce, lower seq: the delayed request loses
    ((None, T1, ("n1", 5), T0), True),              # no generation: strictly newer measured_at
    ((None, T0, None, T1), False),
    ((None, T0, None, T0), False),
    ((None, T0, None, None), True),
]


def test_newer_rule_python_twin():
    for (gen, at, old_gen, old_at), expected in NEWER_CASES:
        assert main._region_pings_newer(gen, at, old_gen, old_at) is expected, (gen, at, old_gen, old_at)


def test_upsert_sql_carries_the_same_rule_and_typed_binds():
    sql = " ".join(main._REGION_PINGS_UPSERT_SQL.split())
    for needle in (
        "INSERT INTO player_region_pings (player_id, pings, measured_at, received_at, gen_nonce, gen_seq)",
        "SELECT p.id, CAST(:pings AS JSONB), CAST(:measured_at AS TIMESTAMPTZ), NOW(),",
        "CAST(:gen_nonce AS TEXT), CAST(:gen_seq AS INTEGER)",
        "FROM players p WHERE p.steam_id = CAST(:sid AS TEXT) AND p.deleted_at IS NULL",
        "ON CONFLICT (player_id) DO UPDATE",
        "SET pings = EXCLUDED.pings, measured_at = EXCLUDED.measured_at, received_at = NOW(),",
        "gen_nonce = EXCLUDED.gen_nonce, gen_seq = EXCLUDED.gen_seq",
        "WHERE (EXCLUDED.gen_nonce IS NOT NULL AND (player_region_pings.gen_nonce IS DISTINCT FROM EXCLUDED.gen_nonce"
        " OR player_region_pings.gen_seq < EXCLUDED.gen_seq))"
        " OR (EXCLUDED.gen_nonce IS NULL AND player_region_pings.measured_at < EXCLUDED.measured_at)",
    ):
        assert needle in sql, needle
    assert sql.count("EXCLUDED.gen_nonce IS NOT NULL") == 1
    assert ":player_id" not in sql, "the row is resolved by the AUTHENTICATED steam id, never a bound player id"


# ── the store ────────────────────────────────────────────────────────────────

def test_store_writes_the_callers_map_under_the_shared_identity_lock(monkeypatch):
    log = []
    sessions = _factory(monkeypatch, log)
    cur = _run(main._region_pings_store(_request("us=42,eu=31;age=12", "0123abcd:7"), STEAM, "team"))
    assert cur is not None
    pmap, at, gen = cur
    assert pmap == {"us": 42, "eu": 31} and gen == ("0123abcd", 7)
    assert at.tzinfo is not None and abs((_now() - at).total_seconds() - 12) < 2
    assert len(sessions) == 1 and sessions[0].committed
    assert len(log) == 2
    assert log[0][0] == "SELECT pg_advisory_xact_lock_shared(hashtext(CAST(:sid AS text)))"
    assert log[0][1] == {"sid": STEAM}
    sql, params = log[1]
    assert sql.startswith("INSERT INTO player_region_pings")
    assert params == {"sid": STEAM, "pings": '{"eu":31,"us":42}', "measured_at": at,
                      "gen_nonce": "0123abcd", "gen_seq": 7}


def test_store_without_a_generation_binds_nulls(monkeypatch):
    log = []
    _factory(monkeypatch, log)
    cur = _run(main._region_pings_store(_request("us=42;age=0"), STEAM, "ovt"))
    assert cur[0] == {"us": 42} and cur[2] is None
    assert log[1][1]["gen_nonce"] is None and log[1][1]["gen_seq"] is None
    assert abs((_now() - cur[1]).total_seconds()) < 2


def test_store_is_silent_without_a_valid_header_or_a_verified_session(monkeypatch):
    for req in (_request(), _request("garbage"), _request("us=42;age=12;x=1"),
                _request("us=42,eu=31;age=12", "0123abcd:7", verified=False),
                SimpleNamespace(headers=None, state=SimpleNamespace(scr_session_verified=True)),
                None):
        log = []
        sessions = _factory(monkeypatch, log)
        assert _run(main._region_pings_store(req, STEAM, "ffa")) is None
        assert sessions == [] and log == []


def test_store_failure_is_logged_and_still_returns_the_overlay(monkeypatch, capsys):
    log = []
    _factory(monkeypatch, log, fail=RuntimeError("relation player_region_pings does not exist"))
    cur = _run(main._region_pings_store(_request("us=42;age=0"), STEAM, "ffa"))
    assert cur is not None and cur[0] == {"us": 42}
    out = capsys.readouterr().out
    assert f"[GROUP-REGION] ffa store failed for {STEAM}: RuntimeError: relation player_region_pings" in out


# ── the issuance read + overlay + log line ───────────────────────────────────

def _row(pid, home="us"):
    return {"player_id": pid, "region": home}


def _stored(pid, pmap, age_s=5, gen=None):
    return {"player_id": pid, "pings": pmap, "measured_at": _now() - timedelta(seconds=age_s),
            "gen_nonce": gen[0] if gen else None, "gen_seq": gen[1] if gen else None}


ROWS = [_row(A), _row(B), _row(C)]


def _pick(monkeypatch, rows, stored, current=None, fail=None, legacy="us"):
    log = []
    _factory(monkeypatch, log, rows=stored, fail=fail)
    return _run(main._group_region(rows, legacy, "team", current=current, room="team_x")), log


def _line(capsys):
    lines = [l for l in capsys.readouterr().out.splitlines() if l.startswith("[GROUP-REGION] team room=team_x ")]
    assert len(lines) == 1, lines
    return lines[0]


def test_group_pick_moves_the_room_on_the_members_stored_maps(monkeypatch, capsys):
    pick, log = _pick(monkeypatch, ROWS, [_stored(A, NEAR), _stored(B, NEAR), _stored(C, NEAR)])
    assert pick == "eu"
    assert len(log) == 1
    sql, params = log[0]
    assert sql == ("SELECT player_id, pings, measured_at, gen_nonce, gen_seq"
                   " FROM player_region_pings WHERE player_id = ANY(:ids)")
    assert params == {"ids": [A, B, C]}
    line = _line(capsys)
    assert (" pick=eu why=majority baseline=us legacy=us n=3 sum_b=180 sum_pick=105"
            " worst_b=60 worst_pick=35 gain=3 regret=-25 tie=- ") in line
    assert line.endswith(f"members={A}:fresh:60/35,{B}:fresh:60/35,{C}:fresh:60/35")


def test_group_pick_stays_on_the_baseline_without_quorum(monkeypatch, capsys):
    pick, _ = _pick(monkeypatch, ROWS, [_stored(A, NEAR), _stored(B, NEAR)])    # C never measured
    assert pick == "us"
    line = _line(capsys)
    assert " pick=us why=quorum baseline=us legacy=us n=3 " in line and f"{C}:absent:-/-" in line
    stale = _stored(C, NEAR, age_s=main.REGION_PINGS_ISSUANCE_MAX_AGE_S + 5)
    pick, _ = _pick(monkeypatch, ROWS, [_stored(A, NEAR), _stored(B, NEAR), stale])
    assert pick == "us"
    assert f"{C}:stale:60/60" in _line(capsys)


def test_group_pick_refuses_a_minority_gain_that_costs_the_others_over_the_bound(monkeypatch, capsys):
    # A gains 165 ms; B and C each pay 40 (> REGION_GROUP_REGRET_MS). One of
    # three is no majority, so eu is refused although the room's total would
    # fall (320 -> 235). With the bound at 50 it would move — the constant is
    # what this pins.
    stored = [_stored(A, {"us": 200, "eu": 35}), _stored(B, {"us": 60, "eu": 100}),
              _stored(C, {"us": 60, "eu": 100})]
    pick, _ = _pick(monkeypatch, ROWS, stored)
    assert pick == "us"
    assert " pick=us why=baseline baseline=us legacy=us n=3 sum_b=320 sum_pick=320 " in _line(capsys)
    assert main.REGION_GROUP_REGRET_MS == 30 and main.REGION_PINGS_MARGIN_MS == 20
    src = inspect.getsource(main._group_region)
    assert "margin_ms=REGION_PINGS_MARGIN_MS, regret_ms=REGION_GROUP_REGRET_MS," in src
    assert "max_age_s=REGION_PINGS_ISSUANCE_MAX_AGE_S, now=time.time()" in src


def test_group_pick_decodes_json_text_maps_and_naive_stamps(monkeypatch):
    stored = [_stored(A, '{"eu":35,"us":60}'), _stored(B, '{"eu":35,"us":60}'), _stored(C, NEAR)]
    stored[2]["measured_at"] = stored[2]["measured_at"].replace(tzinfo=None)   # a naive UTC stamp
    pick, _ = _pick(monkeypatch, ROWS, stored)
    assert pick == "eu"
    stored[0]["pings"] = "{not json"
    pick, _ = _pick(monkeypatch, ROWS, stored)
    assert pick == "us", "garbage text is an absent map, not an exception"


def test_overlay_supplies_the_callers_own_uncommitted_header(monkeypatch, capsys):
    stored = [_stored(A, NEAR), _stored(B, NEAR)]
    current = (C, NEAR, _now() - timedelta(seconds=3), None)
    pick, _ = _pick(monkeypatch, ROWS, stored, current=current)
    assert pick == "eu"
    assert f"{C}:fresh:60/35" in _line(capsys)
    # the overlay is the caller's OWN seat only: a header for a seat outside the room changes nothing
    pick, _ = _pick(monkeypatch, ROWS, stored, current=(UUID(int=9), NEAR, _now(), None))
    assert pick == "us"


def test_overlay_applies_only_when_it_would_have_replaced_the_stored_row(monkeypatch):
    stored = [_stored(A, NEAR), _stored(B, NEAR), _stored(C, FAR, gen=("0123abcd", 7))]
    fresh = _now() - timedelta(seconds=1)
    assert _pick(monkeypatch, ROWS, stored, current=(C, NEAR, fresh, ("0123abcd", 5)))[0] == "us", \
        "a lower seq of the same process is the delayed request; the stored map stands"
    assert _pick(monkeypatch, ROWS, stored, current=(C, NEAR, fresh, ("0123abcd", 7)))[0] == "us", \
        "the same generation is a resend"
    assert _pick(monkeypatch, ROWS, stored, current=(C, NEAR, fresh, ("0123abcd", 9)))[0] == "eu"
    assert _pick(monkeypatch, ROWS, stored, current=(C, NEAR, fresh, ("ffffffff", 1)))[0] == "eu", \
        "a new process's nonce always wins"
    # no generation on the header: measured_at decides
    stored = [_stored(A, NEAR), _stored(B, NEAR), _stored(C, FAR, age_s=5)]
    assert _pick(monkeypatch, ROWS, stored, current=(C, NEAR, _now() - timedelta(seconds=10), None))[0] == "us"
    assert _pick(monkeypatch, ROWS, stored, current=(C, NEAR, _now() - timedelta(seconds=1), None))[0] == "eu"


def test_read_failure_falls_back_to_the_legacy_pick_and_says_so(monkeypatch, capsys):
    pick, _ = _pick(monkeypatch, ROWS, [], fail=RuntimeError("boom"), legacy="usw")
    assert pick == "usw"
    line = _line(capsys)
    assert " pick=usw why=error baseline=- legacy=usw n=- " in line
    assert line.endswith("members=- error=RuntimeError: boom")


def test_group_pick_never_returns_an_empty_region(monkeypatch):
    # nobody has a home and nobody measured: the legacy default carries
    rows = [_row(A, None), _row(B, None)]
    assert _pick(monkeypatch, rows, [], legacy="us")[0] == "us"


def test_legacy_mode_is_deterministic_and_the_overlay_helper_is_shaped():
    assert main._region_mode_of([_row(A, "usw"), _row(B, "us"), _row(C, "eu")]) == "eu", "ties: lexical"
    assert main._region_mode_of([_row(A, "usw"), _row(B, "usw"), _row(C, "us")]) == "usw"
    assert main._region_mode_of([_row(A, None), _row(B, "")]) == "us"
    assert main._region_mode_of([_row(A, None)], default=None) is None
    assert main._region_mode_of([]) == "us"
    assert main._region_current(A, None) is None
    assert main._region_current(A, ({"us": 1}, T0, ("n", 1))) == (A, {"us": 1}, T0, ("n", 1))


# ── structure pins ───────────────────────────────────────────────────────────

def _main_code():
    """main.py with COMMENT tokens blanked at preserved offsets (the
    test_room_region_symmetry.py template): prose is not code."""
    src = MAIN_PY.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type != tokenize.COMMENT:
            continue
        (srow, scol), (erow, ecol) = tok.start, tok.end
        assert srow == erow
        ln = lines[srow - 1]
        lines[srow - 1] = ln[:scol] + " " * (ecol - scol) + ln[ecol:]
    return "".join(lines)


WRITERS = ("team_queue_poll", "ovt_queue_poll", "ffa_queue_poll", "_lobby_state_impl")
ISSUERS = ("team_queue_poll", "ovt_queue_poll", "ovt_lobby_start", "ffa_lobby_start", "ffa_queue_poll")


def test_every_writer_stores_after_auth_and_before_any_queue_row_lock():
    for name in WRITERS:
        src = inspect.getsource(getattr(main, name))
        assert src.count("await _region_pings_store(request, steam_id, ") == 1, name
        store = src.index("await _region_pings_store(")
        assert src.index("await _check_steam_session(request, steam_id, db)") < store, name
        assert store < src.index("await _lock_queue_group_for_player("), (
            name, "the store must not hold queue rows while it waits on the identity lock")
    code = _main_code()
    assert code.count("await _region_pings_store(") == len(WRITERS), (
        "the writers are the four session-bound polls: 2v2 / 1v2 lobby members poll "
        "_lobby_state_impl, FFA lobby members poll ffa_queue_poll; no browser route stores")


def test_every_issuance_site_asks_the_rule_once_and_the_old_shapes_are_gone():
    for name in ISSUERS:
        src = inspect.getsource(getattr(main, name))
        assert src.count("await _group_region(") == 1, name
        assert "_region_mode_of(" in src, name
    for name in ("team_queue_poll", "ovt_queue_poll", "ffa_queue_poll"):
        assert "current=_region_current(" in inspect.getsource(getattr(main, name)), (
            name, "the calling seat's own header rides into the pick it may decide")
    code = _main_code()
    assert code.count("await _group_region(") == len(ISSUERS)
    for old in ("max(set(regions), key=regions.count)",
                'next((r["region"] for r in lobby if r["region"]), "us")',
                'next((m["region"] for m in live if m["region"]), "us")'):
        assert code.count(old) == 0, old
    # the 1v1 rung is frozen (bug 355 v3): its definition and its one call in
    # _pick_room_region, untouched by this batch
    assert code.count("def _pick_region_by_pings(") == 1
    assert code.count("_pick_region_by_pings(") == 2


def test_janitor_purges_maps_an_hour_after_their_last_write():
    src = inspect.getsource(main.queue_cleanup_loop)
    assert src.count("DELETE FROM player_region_pings") == 1
    stmt = " ".join(src[src.index("DELETE FROM player_region_pings"):][:400].split())
    assert stmt.startswith("DELETE FROM player_region_pings WHERE player_id IN ( SELECT player_id FROM "
                           "player_region_pings WHERE received_at < NOW() - INTERVAL '1 hour' "
                           "FOR UPDATE SKIP LOCKED ) RETURNING player_id")
    assert src.count("[QUEUE-CLEANUP] region maps sweep error") == 1


def test_delete_my_data_removes_the_map_explicitly_under_the_exclusive_identity_lock():
    src = inspect.getsource(main.delete_player_data)
    assert src.count('text("DELETE FROM player_region_pings WHERE player_id = :pid")') == 1
    assert "region ping maps" in (main.delete_player_data.__doc__ or "")
    assert src.index("pg_advisory_xact_lock(hashtext(:sid))") < src.index("DELETE FROM player_region_pings")
    assert src.index("DELETE FROM player_region_pings") < src.index("player.deleted_at = datetime.now(timezone.utc)")


def test_migration_307_creates_the_table_in_one_transaction():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert sql.count("BEGIN;") == 1 and sql.count("COMMIT;") == 1
    flat = " ".join(sql.split())
    assert "CREATE TABLE IF NOT EXISTS player_region_pings (" in flat
    for col in ("player_id UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,",
                "pings JSONB NOT NULL,", "measured_at TIMESTAMPTZ NOT NULL,",
                "received_at TIMESTAMPTZ NOT NULL DEFAULT now(),",
                "gen_nonce TEXT NULL,", "gen_seq INTEGER NULL"):
        assert col in flat, col
    assert "ONE HOUR" in sql and "BEFORE the api" in sql
