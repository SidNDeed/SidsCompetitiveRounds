"""Player Cards (phase 1) — the server core around the pure rules.

Executed against scripted sessions:
  * `_pc_roll_prints` — five prints from the snapshot, the live-pool re-check
    that re-rolls a vanished subject (bounded, then pool_changed), never a
    band above the roll, pool_empty when nothing can be dealt;
  * `_pc_take_snapshot` — the band from the rank, the title resolved by the
    leaderboard's own resolver, the retention delete;
  * `_pc_snapshot_janitor_step` — first snapshot when none exists, one per
    UTC day at 00:05, nothing before that, nothing when the try-lock is held.

Structure pins (comments blanked, see test_group_region_issuance.py): every
mutation and private read goes through `_pc_verified_actor` (HMAC + strict
session), the claim is the first write and the roll precedes the debit which
precedes the mint, both debits are conditional deltas with RETURNING, no
UPDATE of pc_prints touches a frozen column, the daily claim's date comes from
the DB clock, the settings writes are compare-and-set, the janitor runs the
step, delete-my-data purges every pc_* table between the identity lock and
the anonymisation, the rate-limit prefix, the ORM columns.
"""

import asyncio
import inspect
import io
import re
import tokenize
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

import database
import main
import models
import player_cards as pc

MAIN_PY = Path(__file__).resolve().parents[1] / "api" / "main.py"

S1 = UUID("11111111-1111-1111-1111-111111111111")
S2 = UUID("22222222-2222-2222-2222-222222222222")
OWNER = UUID("99999999-9999-9999-9999-999999999999")


def _run(coro):
    return asyncio.run(coro)


class _Res:
    """A scripted statement result: a list of dict rows, or a scalar."""

    def __init__(self, value):
        self.value = value

    def _rows(self):
        return list(self.value) if isinstance(self.value, list) else []

    def mappings(self):
        return self

    def all(self):
        return self._rows()

    def fetchall(self):
        return self._rows()

    def first(self):
        rows = self._rows()
        return rows[0] if rows else None

    def one(self):
        rows = self._rows()
        assert len(rows) == 1, rows
        return rows[0]

    def scalar_one(self):
        if isinstance(self.value, list):
            row = self.one()
            return next(iter(row.values()))
        return self.value

    def scalar_one_or_none(self):
        if isinstance(self.value, list):
            row = self.first()
            return None if row is None else next(iter(row.values()))
        return self.value

    def __iter__(self):
        return iter(self._rows())


class Scripted:
    """execute() answers by the first script key contained in the normalised
    SQL; each key holds a queue of results (the last one repeats)."""

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.log = []
        self.committed = 0
        self.rolled_back = 0

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
                value = queue.pop(0) if len(queue) > 1 else queue[0]
                return _Res(value)
        return _Res([])

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1

    def count(self, key):
        return sum(1 for sql, _ in self.log if key in sql)


class _Rng:
    def __init__(self, randoms, indexes):
        self.randoms, self.indexes = list(randoms), list(indexes)

    def random(self):
        return self.randoms.pop(0) if len(self.randoms) > 1 else self.randoms[0]

    def randrange(self, n):
        v = self.indexes.pop(0) if len(self.indexes) > 1 else self.indexes[0]
        return v % n


def _member(pid, rank, rarity):
    return {"player_id": pid, "pool_rank": rank, "rarity": rarity, "rating": 1700.0, "peak_rating": 1750.0,
            "board_rank": rank, "series_wins": 3, "series_losses": 1, "top_card": "Leach", "title": "Advanced I"}


SIZES = [{"rarity": "common", "n": 100}, {"rarity": "rare", "n": 10}, {"rarity": "legendary", "n": 1}]
SIZES_KEY = "FROM pc_pool_members WHERE snapshot_id = CAST(:sid AS integer) GROUP BY rarity"
MEMBER_KEY = "SELECT m.player_id, m.pool_rank"
LIVE_KEY = "SELECT 1 FROM players p WHERE p.id = CAST(:pid AS uuid)"


# ── the roll ─────────────────────────────────────────────────────────────────

def test_roll_deals_five_prints_from_the_snapshot_at_the_bands_rolled():
    db = Scripted({SIZES_KEY: [SIZES], MEMBER_KEY: [[_member(S1, 15, "rare")]], LIVE_KEY: [[{"?column?": 1}]]})
    rng = _Rng([0.1, 0.9, 0.9] * 5, [4])      # per print: band roll in Rare, foil miss, signed miss
    prints, why = _run(main._pc_roll_prints(db, 7, OWNER, rng=rng))
    assert why is None and len(prints) == 5
    assert [p["slot"] for p in prints] == [1, 2, 3, 4, 5]
    assert all(p["rarity"] == "rare" and p["rolled"] == "rare" for p in prints)
    assert all(p["foil"] is False and p["signed"] is False for p in prints)
    assert all(p["player_id"] == str(S1) and p["pool_rank"] == 15 for p in prints)
    # one member read and one live check per print, no writes
    assert db.count(MEMBER_KEY) == 5 and db.count(LIVE_KEY) == 5
    assert not any(sql.startswith(("INSERT", "UPDATE", "DELETE")) for sql, _ in db.log)
    member_params = [p for sql, p in db.log if MEMBER_KEY in sql]
    assert all(p == {"sid": 7, "rarity": "rare", "k": 4} for p in member_params)


def test_roll_falls_one_band_down_never_up():
    # Legendary band empty, Epic empty: a Legendary roll (0.0) is dealt from Rare.
    sizes = [{"rarity": "common", "n": 100}, {"rarity": "rare", "n": 10}]
    db = Scripted({SIZES_KEY: [sizes], MEMBER_KEY: [[_member(S1, 12, "rare")]], LIVE_KEY: [[{"x": 1}]]})
    prints, why = _run(main._pc_roll_prints(db, 7, OWNER, rng=_Rng([0.0, 0.9, 0.9] * 5, [0])))
    assert why is None and all(p["rolled"] == "legendary" and p["rarity"] == "rare" for p in prints)
    # Negative control: a Common roll with an empty Common band and members only above -> pool_empty.
    db2 = Scripted({SIZES_KEY: [[{"rarity": "common", "n": 0}, {"rarity": "rare", "n": 3}]]})
    assert _run(main._pc_roll_prints(db2, 7, OWNER, rng=_Rng([0.5], [0]))) == (None, "pool_empty")
    assert db2.count(MEMBER_KEY) == 0


def test_roll_is_pool_empty_when_the_snapshot_has_no_members():
    db = Scripted({SIZES_KEY: [[]]})
    assert _run(main._pc_roll_prints(db, 7, OWNER)) == (None, "pool_empty")
    assert db.count(MEMBER_KEY) == 0 and db.count(LIVE_KEY) == 0


def test_a_subject_that_left_the_pool_is_rerolled_then_the_open_is_pool_changed():
    # The live check never passes: 1 + reroll_attempts tries, then pool_changed.
    db = Scripted({SIZES_KEY: [SIZES], MEMBER_KEY: [[_member(S2, 1, "legendary")]], LIVE_KEY: [[]]})
    prints, why = _run(main._pc_roll_prints(db, 7, OWNER, rng=_Rng([0.001, 0.9, 0.9], [0])))
    assert (prints, why) == (None, "pool_changed")
    assert db.count(LIVE_KEY) == 1 + pc.PC_ECONOMY["reroll_attempts"]
    # Negative control: the vanished subject is never dealt when it passes on the retry.
    db2 = Scripted({SIZES_KEY: [SIZES], MEMBER_KEY: [[_member(S2, 1, "legendary")], [_member(S1, 15, "rare")]],
                    LIVE_KEY: [[], [{"x": 1}]]})
    prints, why = _run(main._pc_roll_prints(db2, 7, OWNER, rng=_Rng([0.001, 0.9, 0.9], [0])))
    assert why is None and all(p["player_id"] == str(S1) for p in prints)


def test_flags_are_rolled_per_print_after_the_subject():
    db = Scripted({SIZES_KEY: [SIZES], MEMBER_KEY: [[_member(S1, 50, "common")]], LIVE_KEY: [[{"x": 1}]]})
    # band, foil, signed per print: print 1 foil, print 2 signed, others plain
    randoms = [0.5, 0.001, 0.9,   0.5, 0.9, 0.0001,   0.5, 0.9, 0.9,   0.5, 0.9, 0.9,   0.5, 0.9, 0.9, 0.9]
    prints, why = _run(main._pc_roll_prints(db, 7, OWNER, rng=_Rng(randoms, [3])))
    assert why is None
    assert [(p["foil"], p["signed"]) for p in prints] == [(True, False), (False, True), (False, False), (False, False), (False, False)]


# ── the snapshot ─────────────────────────────────────────────────────────────

def _snapshot_row(pid, rank, sku=None, name=None, rating=1600.0):
    return {"player_id": pid, "pool_rank": rank, "rating": rating,
            "peak_rating": None if rating is None else rating + 10,
            "board_rank": rank if rank <= 2 else None, "series_wins": 2, "series_losses": 1,
            "top_card": "Barrage", "title_sku": sku, "title_name": name, "title_color": "#fff"}


def test_snapshot_freezes_band_from_rank_and_the_resolved_title(monkeypatch):
    rows = [_snapshot_row(S1, 1, "title_x", "Speedrunner"), _snapshot_row(S2, 2, "dyn_rank", "Current Rank"),
            _snapshot_row(OWNER, 41, None, None, rating=None)]
    db = Scripted({"WITH pool AS": [rows], "INSERT INTO pc_pool_snapshots": [42]})
    calls = []

    async def _colors(_db):
        return {"Advanced I": "#abc"}

    async def _podiums(_db, skus):
        return ({}, {str(S2): 1}, {})

    def _resolve(colors, sku, name, color, rating, podium_pos=None, podium_pos_2v2=None, podium_pos_ffa=None):
        calls.append((sku, name, rating, podium_pos, podium_pos_2v2, podium_pos_ffa))
        return (f"resolved:{sku}" if sku else None), color

    monkeypatch.setattr(main, "_rank_colors", _colors)
    monkeypatch.setattr(main, "_podium_maps_for", _podiums)
    monkeypatch.setattr(main, "_display_title_sync", _resolve)
    out = _run(main._pc_take_snapshot(db, reason="test"))
    assert out == {"snapshot_id": 42, "members": 3}
    insert = [p for sql, p in db.log if "INSERT INTO pc_pool_members" in sql]
    assert len(insert) == 1 and isinstance(insert[0], list) and len(insert[0]) == 3
    by_rank = {p["rank"]: p for p in insert[0]}
    assert by_rank[1]["rarity"] == "legendary" and by_rank[2]["rarity"] == "epic" and by_rank[41]["rarity"] == "common"
    assert by_rank[1]["title"] == "resolved:title_x" and by_rank[41]["title"] is None
    assert by_rank[41]["rating"] is None and by_rank[41]["board"] is None and by_rank[1]["board"] == 1
    assert all(p["sid"] == 42 for p in insert[0])
    # the leaderboard's resolver saw the podium position of the 2v2 podium holder
    assert (("dyn_rank", "Current Rank", 1600.0, None, 1, None)) in calls
    keep = [p for sql, p in db.log if "DELETE FROM pc_pool_snapshots" in sql]
    assert keep == [{"keep": pc.PC_ECONOMY["snapshot_keep"]}]
    select_params = [p for sql, p in db.log if "WITH pool AS" in sql][0]
    assert select_params["min_matches"] == 5 and select_params["active_days"] == main.LEADERBOARD_ACTIVE_DAYS


def _due_row(last_at, db_now, today_at):
    return [{"last_at": last_at, "db_now": db_now, "today_at": today_at}]


def _janitor(monkeypatch, due, lock=True):
    db = Scripted({"SELECT (SELECT MAX(taken_at)": [due], "pg_try_advisory_xact_lock": [lock]})
    monkeypatch.setattr(database, "async_session", lambda: db)
    taken = []

    async def _take(_db, *, reason):
        taken.append(reason)
        return {"snapshot_id": 1, "members": 0}

    monkeypatch.setattr(main, "_pc_take_snapshot", _take)
    return db, taken


def test_janitor_takes_the_first_snapshot_when_none_exists(monkeypatch):
    today = datetime(2026, 9, 11, 0, 5, tzinfo=timezone.utc)
    db, taken = _janitor(monkeypatch, _due_row(None, today - timedelta(hours=3), today))
    _run(main._pc_snapshot_janitor_step())
    assert taken == ["first"] and db.committed == 1
    assert db.count("DELETE FROM pc_events WHERE created_at < NOW() - INTERVAL '7 days'") == 1


def test_janitor_takes_one_per_day_at_or_after_0005_utc(monkeypatch):
    today = datetime(2026, 9, 11, 0, 5, tzinfo=timezone.utc)
    yesterday = today - timedelta(days=1)
    # due: last snapshot yesterday, now past 00:05
    db, taken = _janitor(monkeypatch, _due_row(yesterday, today + timedelta(minutes=1), today))
    _run(main._pc_snapshot_janitor_step())
    assert taken == ["daily"]
    # not yet: last snapshot yesterday, now 00:03
    db, taken = _janitor(monkeypatch, _due_row(yesterday, today - timedelta(minutes=2), today))
    _run(main._pc_snapshot_janitor_step())
    assert taken == [] and db.count("pg_try_advisory_xact_lock") == 0
    # already done today: last snapshot after 00:05 today
    db, taken = _janitor(monkeypatch, _due_row(today + timedelta(seconds=30), today + timedelta(hours=5), today))
    _run(main._pc_snapshot_janitor_step())
    assert taken == []
    # lock held elsewhere: nothing
    db, taken = _janitor(monkeypatch, _due_row(yesterday, today + timedelta(minutes=1), today), lock=False)
    _run(main._pc_snapshot_janitor_step())
    assert taken == [] and db.committed == 0


# ── the wire shape ───────────────────────────────────────────────────────────

def test_print_dict_carries_the_frozen_face_and_the_current_name():
    row = {"print_id": S1, "card_id": S2, "subject_player_id": OWNER, "edition_id": 1, "owner_player_id": S1,
           "minted_at": datetime(2026, 9, 11, tzinfo=timezone.utc), "snapshot_id": 3, "rarity": "epic",
           "foil": True, "signed": False, "pool_rank": 4, "rating": 2100.0, "peak_rating": 2200.0,
           "board_rank": 4, "series_wins": 20, "series_losses": 5, "top_card": "Leach", "title": "Master II",
           "source": "bought", "pack_id": S2, "slot": 2, "discarded_at": None, "discard_shards": None,
           "subject_name": "Ace", "subject_deleted": False}
    d = main._pc_print_dict(row)
    assert d["subject_name"] == "Ace" and d["rarity"] == "epic" and d["foil"] is True and d["slot"] == 2
    assert d["rank_name"] == main._rank_name_for(2100.0) and d["discarded"] is False
    assert d["print_id"] == str(S1) and d["minted_at"].startswith("2026-09-11")


# ── structure pins ───────────────────────────────────────────────────────────

def _main_code():
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


MUTATIONS = ("pc_open_pack", "pc_daily_claim", "pc_discard_print", "pc_set_setting")
PRIVATE_READS = ("pc_pack_result", "pc_me")


def test_every_mutation_and_private_read_goes_through_the_verified_actor():
    for name in MUTATIONS + PRIVATE_READS:
        src = inspect.getsource(getattr(main, name))
        assert len(re.findall(r"await _pc_verified_actor\(request, steam_id, sig,\s", src)) == 1, name
    # the two dual-mode reads: the verified actor on the own-binder / owner branch, HMAC on the public one
    for name in ("pc_collection", "pc_card_face"):
        src = inspect.getsource(getattr(main, name))
        assert src.count("_pc_verified_actor(request, steam_id, sig, ") == 1, name
        assert src.count("_pc_hmac_ok(sig, canon)") == 1, name
        assert 'detail={"error": "private"}' in src, name
    actor = inspect.getsource(main._pc_verified_actor)
    assert "await _strict_steam_session_ok(request, steam_id, db)" in actor
    assert 'detail="session_required"' in actor
    assert "hmac.compare_digest(" in actor and "_assert_no_service_subject(" in actor
    assert actor.index("hmac.compare_digest(") < actor.index("_strict_steam_session_ok(") < actor.index("select(Player)")


def test_the_pack_open_claims_first_rolls_before_the_debit_and_mints_last():
    src = inspect.getsource(main.pc_open_pack)
    claim_purchase = src.index("ON CONFLICT (player_id, nonce) WHERE nonce IS NOT NULL DO NOTHING")
    claim_pack = src.index("AND status = 'unopened'")
    lock = src.index("FOR NO KEY UPDATE")
    edition = src.index("WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1 FOR SHARE")
    roll = src.index("await _pc_roll_prints(db, int(snap_id), player.id)")
    debit_gold = src.index("gold_spent = COALESCE(gold_spent, 0) + CAST(:amt AS integer)")
    debit_shards = src.index("pc_shards = pc_shards - CAST(:amt AS integer)")
    mint = src.index("await _pc_mint(")
    done = src.index("SET status = 'done'")
    assert max(claim_purchase, claim_pack) < lock < edition < roll < debit_gold < debit_shards < mint < done
    # both debits are conditional deltas with RETURNING
    assert "COALESCE(gold_earned, 0) - COALESCE(gold_spent, 0) >= CAST(:amt AS integer)" in src
    assert "AND pc_shards >= CAST(:amt AS integer)" in src
    assert src.count("RETURNING id") >= 4
    assert 'reason="pc_pack"' in src and "amount=-price" in src
    # every rejection commits without a debit and the pack answers from the committed row
    assert src.count("await _reject(") == 7, src.count("await _reject(")
    assert "await _reject(why)" in src and "pool_changed" in inspect.getsource(main._pc_roll_prints)
    for reason in ("no_edition", "price_changed", "pool_empty", "daily_cap", "insufficient_gold", "insufficient_shards"):
        assert f'"{reason}"' in src, reason
    assert "SET status = 'rejected', reject_reason = CAST(:reason AS text)" in src
    assert "SET status = 'unopened' WHERE id = CAST(:pack AS uuid)" in src


def test_no_update_of_pc_prints_touches_a_frozen_column():
    code = _main_code()
    updates = re.findall(r"UPDATE pc_prints SET (.*?) WHERE", " ".join(code.split()))
    assert updates, "the discard UPDATE must exist"
    allowed = {"discarded_at", "discard_shards", "owner_player_id"}
    for clause in updates:
        cols = {part.split("=")[0].strip() for part in clause.split(",")}
        assert cols <= allowed, clause
    assert "DELETE FROM pc_prints WHERE owner_player_id = :pid" in code   # delete-my-data, the only other writer


def test_the_daily_claim_date_comes_from_the_db_clock_only():
    src = inspect.getsource(main._pc_claim_daily)
    assert "(now() AT TIME ZONE 'UTC')::date" in src
    assert "claimed_on" not in inspect.signature(main.pc_daily_claim).parameters
    assert "claimed_on" not in inspect.signature(main.internal_pc_daily).parameters
    assert "ON CONFLICT (player_id, claimed_on) DO NOTHING" in src and "RETURNING claimed_on" in src
    assert src.index("FOR NO KEY UPDATE") < src.index("INSERT INTO pc_daily_claims")
    assert '"already_claimed"' in src and "INSERT INTO pc_packs (player_id, source, reference_id, status)" in src
    # both entry points share the one claim
    assert inspect.getsource(main.pc_daily_claim).count("await _pc_claim_daily(db, player, via=") == 1
    assert inspect.getsource(main.internal_pc_daily).count("await _pc_claim_daily(db, player, via=") == 1


INTERNAL = ("internal_pc_events_pending", "internal_pc_events_ack", "internal_pc_daily",
            "internal_pc_collection", "internal_pc_card")


def test_every_internal_route_checks_the_internal_key_first_and_the_drain_rechecks_consent():
    for name in INTERNAL:
        src = inspect.getsource(getattr(main, name))
        assert src.count("_require_internal_key(x_internal_key)") == 1, name
        body = src[src.index('"""', src.index('"""') + 3) + 3:]   # after the docstring
        assert body.lstrip().startswith("_require_internal_key(x_internal_key)"), name
    pending = inspect.getsource(main.internal_pc_events_pending)
    assert pending.index("_PC_EVENTS_SKIP_SQL") < pending.index("_PC_EVENTS_PENDING_SQL")
    for sql in (main._PC_EVENTS_SKIP_SQL, main._PC_EVENTS_PENDING_SQL):
        flat = " ".join(sql.split())
        for needle in ("pl.deleted_at IS NULL", "su.deleted_at IS NULL", "pl.pc_announce", "su.pc_announce",
                       "su.pc_opted_out_at IS NULL"):
            assert needle in flat, needle
    assert "posted_at IS NULL" in " ".join(main._PC_EVENTS_PENDING_SQL.split())
    ack = inspect.getsource(main.internal_pc_events_ack)
    assert "AND posted_at IS NULL" in ack and "CAST(:ids AS bigint[])" in ack
    card = inspect.getsource(main.internal_pc_card)
    assert '"not_in_pool"' in card and "pc_opted_out_at" in card
    coll = inspect.getsource(main.internal_pc_collection)
    assert 'detail={"error": "private"}' in coll and "pc_collection_public" in coll


def test_settings_writes_are_compare_and_set_on_the_revision():
    assert tuple(main._PC_SETTINGS_SQL) == pc.SETTINGS_KEYS
    for key, sql in main._PC_SETTINGS_SQL.items():
        flat = " ".join(sql.split())
        assert "pc_settings_revision = pc_settings_revision + 1" in flat, key
        assert "AND pc_settings_revision = CAST(:rev AS integer)" in flat, key
        assert "RETURNING pc_settings_revision" in flat, key
    src = inspect.getsource(main.pc_set_setting)
    assert '"stale_revision"' in src and "if key not in _pc.SETTINGS_KEYS" in src
    assert "_PC_SETTINGS_SQL[key]" in src   # a whitelist lookup, never a formatted column name


def test_discard_is_one_conditional_update_under_the_player_lock():
    src = inspect.getsource(main.pc_discard_print)
    assert src.index("FOR NO KEY UPDATE") < src.index("UPDATE pc_prints SET discarded_at = now()")
    assert "AND owner_player_id = CAST(:pid AS uuid) AND discarded_at IS NULL" in src
    assert "pc_shards = pc_shards + CAST(:value AS integer)" in src
    assert "_pc.shards_for(rarity)" in src


def test_janitor_runs_the_snapshot_step_and_the_prefix_is_rate_limited():
    loop = inspect.getsource(main.queue_cleanup_loop)
    assert loop.count("await _pc_snapshot_janitor_step()") == 1
    step = inspect.getsource(main._pc_snapshot_janitor_step)
    assert "pg_try_advisory_xact_lock(hashtext('pc_snapshot'))" in step
    assert "INTERVAL '5 minutes'" in step and "MAX(taken_at)" in step
    assert "/api/v1/pc/" in main._RL_SENSITIVE_PREFIXES


def test_delete_my_data_purges_every_player_cards_table_between_the_lock_and_the_anonymisation():
    src = inspect.getsource(main.delete_player_data)
    lock = src.index("pg_advisory_xact_lock(hashtext(:sid))")
    gone = src.index("player.deleted_at = datetime.now(timezone.utc)")
    order = [
        "DELETE FROM pc_events WHERE player_id = :pid OR subject_player_id = :pid",
        "DELETE FROM pc_prints WHERE owner_player_id = :pid",
        "DELETE FROM pc_daily_claims WHERE player_id = :pid",
        "DELETE FROM pc_packs WHERE player_id = :pid",
        "DELETE FROM pc_pool_members WHERE player_id = :pid",
        "UPDATE players SET pc_shards = 0, pc_opted_out_at = COALESCE(pc_opted_out_at, NOW()) WHERE id = :pid",
    ]
    positions = [src.index(s) for s in order]
    assert positions == sorted(positions)
    assert lock < positions[0] and positions[-1] < gone
    # prints and claims (which reference packs) go before packs
    assert positions[1] < positions[3] and positions[2] < positions[3]


def test_the_orm_declares_the_player_columns():
    for col in ("pc_opted_out_at", "pc_collection_public", "pc_announce", "pc_settings_revision", "pc_shards"):
        assert col in models.Player.__table__.columns, col


def test_route_inventory_of_phase_one():
    paths = {(r.path, tuple(sorted(r.methods))) for r in main.app.routes if getattr(r, "path", "").startswith("/api/v1/pc/")}
    assert paths == {
        ("/api/v1/pc/packs/open", ("POST",)), ("/api/v1/pc/packs/result", ("GET",)),
        ("/api/v1/pc/daily", ("POST",)), ("/api/v1/pc/prints/discard", ("POST",)),
        ("/api/v1/pc/settings", ("POST",)), ("/api/v1/pc/me", ("GET",)),
        ("/api/v1/pc/collection", ("GET",)), ("/api/v1/pc/card", ("GET",)), ("/api/v1/pc/pool", ("GET",)),
    }
    admin = [r for r in main.app.routes if getattr(r, "path", "") == "/api/v1/admin/pc/snapshot"]
    assert len(admin) == 1 and "_require_admin(db, admin_steam_id, \"pc_snapshot\", \"pool\", sig)" in inspect.getsource(main.admin_pc_snapshot)
    internal = {(r.path, tuple(sorted(r.methods))) for r in main.app.routes
                if getattr(r, "path", "").startswith("/api/v1/internal/pc/")}
    assert internal == {
        ("/api/v1/internal/pc/events/pending", ("GET",)), ("/api/v1/internal/pc/events/ack", ("POST",)),
        ("/api/v1/internal/pc/daily", ("POST",)), ("/api/v1/internal/pc/collection", ("GET",)),
        ("/api/v1/internal/pc/card", ("GET",)),
    }
