"""Admin evidence report, phase 1a item 2: cell data over seeded games.

Live PostgreSQL. The `matches` and `flagged_matches` tables are built from the
`Match` and `FlaggedMatch` models (columns, types and indexes, without foreign
keys) in a throwaway schema, so the reads run against the production column
set rather than a hand-typed copy.

  P2  games predating the telemetry columns: every cell `not_recorded`, own
      `n=0`, per family no evidence; never a 0 for NULL.
  P8  own baseline (design 2.5): `[1,1,100]` gives `own mean 34.0 (3)`; 501
      newer key-NULL games before 20 values give `own_truncated`, never
      `n=0`; on basis pair the partner's games only, both orientations, in
      the outer order (an A-C distractor and an interleaved 501-game run);
      covered games excluded from the displayed baseline.
  P15 a reviewed FLAG row plus its successor: one FLAG cell from the
      successor, two listed rows, `flag_obs` 1.
  P16 an observer-gap sentinel filed by p1 renders under p2 and its twin
      under p1; heartbeat gaps land on the non-reporter.

Phase 1 registers no pair-global key; P8's pair-global controls therefore run
on the pair-basis seat baseline, which reads the same two orientation
branches and outer order (design 2.5, 2.9). Test ids are generated; flag
subjects are test-only strings.

`ADMIN_EVIDENCE_TEST_PG_DSN` names a database whose name carries
`admin_evidence`; unset, the module fails (an affirmative
`ADMIN_EVIDENCE_TEST_PG_OPTOUT` makes that named skips).
"""

import asyncio
import datetime as dt
import json
import os
import sys
import uuid
from urllib.parse import urlsplit

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import admin_evidence as ae  # noqa: E402
import models  # noqa: E402

DSN = os.environ.get("ADMIN_EVIDENCE_TEST_PG_DSN") or ""
OPTOUT = str(os.environ.get("ADMIN_EVIDENCE_TEST_PG_OPTOUT") or "").strip().lower() in {
    "1", "true", "yes", "on"}


def require_pg():
    if DSN:
        name = urlsplit(DSN).path.lstrip("/")
        if "admin_evidence" not in name:
            pytest.fail("ADMIN_EVIDENCE_TEST_PG_DSN points at %r; this module "
                        "creates and drops schemas there" % name)
        return DSN
    if OPTOUT:
        pytest.skip("ADMIN_EVIDENCE_TEST_PG_OPTOUT is set: cell data checks "
                    "deliberately not run")
    pytest.fail("ADMIN_EVIDENCE_TEST_PG_DSN is not set, so no cell was read from "
                "a database; set it, or ADMIN_EVIDENCE_TEST_PG_OPTOUT=1 to waive")


def _ddl():
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex, CreateTable
    dialect = postgresql.dialect()
    out = []
    for table in (models.Match.__table__, models.FlaggedMatch.__table__):
        out.append(str(CreateTable(table, include_foreign_key_constraints=[])
                       .compile(dialect=dialect)))
        for idx in table.indexes:
            out.append(str(CreateIndex(idx).compile(dialect=dialect)))
    return out


def _required_defaults(table):
    """A value for every NOT NULL column without a server default."""
    from sqlalchemy import Boolean, DateTime, Integer, SmallInteger, String
    from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
    out = {}
    for c in table.columns:
        if c.nullable or c.server_default is not None or c.primary_key:
            continue
        t = c.type
        if isinstance(t, Boolean):
            out[c.name] = False
        elif isinstance(t, (Integer, SmallInteger)):
            out[c.name] = 0
        elif isinstance(t, DateTime):
            out[c.name] = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        elif isinstance(t, UUID):
            out[c.name] = uuid.uuid4()
        elif isinstance(t, ARRAY):
            out[c.name] = []
        elif isinstance(t, JSONB):
            out[c.name] = "{}"
        elif isinstance(t, String):
            out[c.name] = ""
        else:
            out[c.name] = 0
    return out


MATCH_REQUIRED = _required_defaults(models.Match.__table__)
FLAG_REQUIRED = _required_defaults(models.FlaggedMatch.__table__)
T0 = dt.datetime(2026, 2, 1, tzinfo=dt.timezone.utc)


class Live:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.schema = "ae_cells_%s" % uuid.uuid4().hex[:10]

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    async def up(self):
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        self.engine = create_async_engine(DSN)
        self.conn = await self.engine.connect()
        await self.conn.execute(text('CREATE SCHEMA "%s"' % self.schema))
        await self.conn.execute(text('SET search_path TO "%s"' % self.schema))
        for stmt in _ddl():
            await self.conn.execute(text(stmt))
        await self.conn.commit()
        await self.conn.execute(text('SET search_path TO "%s"' % self.schema))

    async def down(self):
        from sqlalchemy import text
        try:
            await self.conn.rollback()
            await self.conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % self.schema))
            await self.conn.commit()
        finally:
            await self.conn.close()
            await self.engine.dispose()

    async def match(self, p1, p2, ended, reporter=None, **cols):
        from sqlalchemy import text
        row = dict(MATCH_REQUIRED)
        row.update(id=uuid.uuid4(), player1_id=p1, player2_id=p2, ended_at=ended,
                   reported_by=reporter)
        row.update(cols)
        names = sorted(row)
        await self.conn.execute(text(
            "INSERT INTO matches (%s) VALUES (%s)"
            % (", ".join(names), ", ".join(":%s" % n for n in names))), row)
        return row["id"]

    async def flag(self, match_id, details, created, reviewed=None):
        from sqlalchemy import text
        row = dict(FLAG_REQUIRED)
        row.update(id=uuid.uuid4(), match_id=match_id, flag_reason="suspected_macro",
                   flag_details=json.dumps(details), created_at=created,
                   reviewed_at=reviewed, player_steam_ids=["steam-a", "steam-b"])
        names = sorted(row)
        vals = ", ".join("CAST(:%s AS jsonb)" % n if n == "flag_details" else ":%s" % n
                         for n in names)
        await self.conn.execute(text("INSERT INTO flagged_matches (%s) VALUES (%s)"
                                     % (", ".join(names), vals)), row)
        return row["id"]

    async def rows(self, where, params):
        from sqlalchemy import text
        res = await self.conn.execute(text(ae.match_row_select(where)
                                           + " ORDER BY m.ended_at DESC, m.id DESC"), params)
        return [dict(r) for r in res.mappings().all()]

    async def flags(self, match_id):
        from sqlalchemy import text
        res = await self.conn.execute(text(
            "SELECT id, flag_reason, flag_details, reviewed_at, created_at "
            "  FROM flagged_matches WHERE match_id = :m"), {"m": match_id})
        return [dict(r) for r in res.mappings().all()]


@pytest.fixture()
def live():
    require_pg()
    lv = Live()
    lv.run(lv.up())
    try:
        yield lv
    finally:
        lv.run(lv.down())
        lv.loop.close()


def _key(var, prov):
    return next(e for e in ae.REPORT_REGISTRY
                if not e.is_window and e.var == var and e.prov == prov)


def _ids(n):
    return [uuid.uuid4() for _ in range(n)]


# ── P2 ─────────────────────────────────────────────────────────────────────

def test_p2_games_before_the_telemetry_columns_render_no_evidence(live):
    a, b = _ids(2)

    async def go():
        for i in range(3):
            await live.match(a, b, T0 + dt.timedelta(hours=i), reporter=a)
        g = await live.match(a, b, T0 + dt.timedelta(days=1), reporter=a)
        rows = await live.rows("m.id = :g", {"g": g})
        base = await ae.read_baseline(live.conn, a, rows[0]["ended_at"], g, covered=[g])
        return rows[0], base

    row, base = live.run(go())
    cells = ae.game_seat_cells(row, a, None, base)
    assert len(cells) == 59
    assert {c["state"] for c in cells} == {"not_recorded"}
    assert all(c["val"] is None for c in cells), [c for c in cells if c["val"] is not None]
    ranked = [c for c in cells if ae.REPORT_REGISTRY[c["ki"]].ranked]
    assert ranked and all(c["own_n"] == 0 and c["own_state"] == "none" for c in ranked)
    by_family = {}
    for c in cells:
        by_family.setdefault(ae.REPORT_REGISTRY[c["ki"]].fam, set()).add(c["state"])
    assert by_family == {f: {"not_recorded"} for f in "MNOC"}
    print("GATE p2: 59 cells not_recorded, %d ranked cells own_n 0, families %s no evidence"
          % (len(ranked), "".join(sorted(by_family))))


# ── P8 ─────────────────────────────────────────────────────────────────────

HITCH = _key("net.hitch50", "SELF")


def _cell(cells, entry):
    return next(c for c in cells if c["ki"] == entry.ki)


def test_p8_mean_of_one_one_hundred_is_34_with_n_3(live):
    a, b = _ids(2)

    async def go():
        for i, v in enumerate((1, 1, 100)):
            await live.match(a, b, T0 + dt.timedelta(hours=i), reporter=a, p1_net_hitch50=v)
        g = await live.match(a, b, T0 + dt.timedelta(days=1), reporter=a, p1_net_hitch50=7)
        rows = await live.rows("m.id = :g", {"g": g})
        base = await ae.read_baseline(live.conn, a, rows[0]["ended_at"], g, covered=[g])
        return rows[0], base

    row, base = live.run(go())
    c = _cell(ae.game_seat_cells(row, a, None, base), HITCH)
    assert (c["val"], c["state"]) == (7, "ok")
    assert c["own_mean"] == pytest.approx(34.0) and c["own_n"] == 3
    assert c["own_state"] == "partial"
    assert c["own_rank"] == pytest.approx(2.0 / 3.0)
    own = ae.own_measures(HITCH, base)
    assert own["own_median"] == 1
    print("GATE p8 mean: own mean %.1f (%d), median %s, rank %.4f"
          % (c["own_mean"], c["own_n"], own["own_median"], c["own_rank"]))


def test_p8_501_newer_null_games_make_the_baseline_truncated_never_n0(live):
    a, b = _ids(2)

    async def go():
        for i in range(20):
            await live.match(a, b, T0 + dt.timedelta(minutes=i), reporter=a, p1_net_hitch50=5)
        for i in range(501):
            await live.match(a, b, T0 + dt.timedelta(days=1, minutes=i), reporter=a)
        g = await live.match(a, b, T0 + dt.timedelta(days=3), reporter=a, p1_net_hitch50=9)
        rows = await live.rows("m.id = :g", {"g": g})
        base = await ae.read_baseline(live.conn, a, rows[0]["ended_at"], g, covered=[g])
        return rows[0], base

    row, base = live.run(go())
    assert base.read == ae.CONTRACT_BOUNDS["BASELINE_SCAN"] + 1
    c = _cell(ae.game_seat_cells(row, a, None, base), HITCH)
    assert c["own_state"] == "truncated"
    assert c["own_n"] is None and c["own_mean"] is None and c["own_rank"] is None
    print("GATE p8 truncated: read %d, own_state %s, own_n %r"
          % (base.read, c["own_state"], c["own_n"]))


def test_p8_pair_basis_reads_the_partner_only_both_orientations(live):
    """A-B prior values [1,1,100] in reversed orientations beside a newer A-C
    distractor: the pair-basis baseline is `own mean 34.0 (3)`."""
    a, b, c_ = _ids(3)

    async def go():
        await live.match(a, b, T0, reporter=a, p1_net_hitch50=1)
        await live.match(b, a, T0 + dt.timedelta(hours=1), reporter=a, p2_net_hitch50=1)
        await live.match(b, a, T0 + dt.timedelta(hours=2), reporter=a, p2_net_hitch50=100)
        await live.match(a, c_, T0 + dt.timedelta(hours=3), reporter=a, p1_net_hitch50=50)
        g = await live.match(a, b, T0 + dt.timedelta(days=1), reporter=a, p1_net_hitch50=7)
        rows = await live.rows("m.id = :g", {"g": g})
        pair = await ae.read_baseline(live.conn, a, rows[0]["ended_at"], g,
                                      covered=[g], partner=b)
        player = await ae.read_baseline(live.conn, a, rows[0]["ended_at"], g, covered=[g])
        return pair, player

    pair, player = live.run(go())
    own = ae.own_measures(HITCH, pair)
    assert own["own_mean"] == pytest.approx(34.0) and own["own_n"] == 3
    assert len({r["id"] for r in pair.rows}) == len(pair.rows) == 3
    own_player = ae.own_measures(HITCH, player)
    assert own_player["own_n"] == 4 and own_player["own_mean"] == pytest.approx(38.0)
    print("GATE p8 pair basis: own mean %.1f (%d); player basis %.1f (%d)"
          % (own["own_mean"], own["own_n"], own_player["own_mean"], own_player["own_n"]))


def test_p8_interleaved_pair_run_is_truncated_in_the_outer_order(live):
    """501 newer key-NULL A-B games alternating orientations before 40 older
    values (20 per orientation): `own_truncated`, never a mean. Forty, not
    twenty, so that a read without the outer order (one branch's rows first)
    reaches 20 values and reads `complete`: the fixture has to be able to
    tell the two apart."""
    a, b = _ids(2)

    async def go():
        for i in range(40):
            p1, p2 = (a, b) if i % 2 else (b, a)
            col = "p1_net_hitch50" if p1 == a else "p2_net_hitch50"
            await live.match(p1, p2, T0 + dt.timedelta(minutes=i), reporter=a, **{col: 3})
        for i in range(501):
            p1, p2 = (a, b) if i % 2 else (b, a)
            await live.match(p1, p2, T0 + dt.timedelta(days=1, minutes=i), reporter=a)
        g = await live.match(a, b, T0 + dt.timedelta(days=3), reporter=a, p1_net_hitch50=9)
        rows = await live.rows("m.id = :g", {"g": g})
        return await ae.read_baseline(live.conn, a, rows[0]["ended_at"], g,
                                      covered=[g], partner=b)

    pair = live.run(go())
    own = ae.own_measures(HITCH, pair)
    assert pair.read == 501
    assert own["own_state"] == "truncated" and own["own_mean"] is None
    print("GATE p8 interleaved: read %d, own_state %s" % (pair.read, own["own_state"]))


def test_p8_covered_games_are_excluded_from_the_displayed_baseline(live):
    a, b = _ids(2)

    async def go():
        for i, v in enumerate((2, 2, 2)):
            await live.match(a, b, T0 + dt.timedelta(hours=i), reporter=a, p1_net_hitch50=v)
        cov1 = await live.match(a, b, T0 + dt.timedelta(days=1), reporter=a, p1_net_hitch50=80)
        cov2 = await live.match(a, b, T0 + dt.timedelta(days=1, hours=1), reporter=a,
                                p1_net_hitch50=90)
        g = await live.match(a, b, T0 + dt.timedelta(days=2), reporter=a, p1_net_hitch50=7)
        rows = await live.rows("m.id = :g", {"g": g})
        base = await ae.read_baseline(live.conn, a, rows[0]["ended_at"], g,
                                      covered=[g, cov1, cov2])
        return rows[0], base

    row, base = live.run(go())
    c = _cell(ae.game_seat_cells(row, a, None, base), HITCH)
    assert c["own_mean"] == pytest.approx(2.0) and c["own_n"] == 3
    print("GATE p8 covered exclusion: own mean %.1f (%d)" % (c["own_mean"], c["own_n"]))


# ── P15 ────────────────────────────────────────────────────────────────────

def test_p15_reviewed_row_and_successor_give_one_cell_two_rows_one_obs(live):
    a, b = _ids(2)
    suspect = _key("macro.suspect_s", "FLAG")

    async def go():
        g = await live.match(a, b, T0, reporter=b)
        old = await live.flag(g, {"suspect_steam": "steam-a", "macro_suspect_seconds": 12},
                              T0 + dt.timedelta(minutes=1), reviewed=T0 + dt.timedelta(minutes=2))
        await live.flag(g, {"suspect_steam": "steam-a", "macro_suspect_seconds": 40,
                            "supersedes_reviewed_flag_id": str(old)},
                        T0 + dt.timedelta(minutes=3))
        rows = await live.rows("m.id = :g", {"g": g})
        return g, rows[0], await live.flags(g)

    g, row, flags = live.run(go())
    current = ae.current_flags(flags)
    assert list(current) == ["steam-a"]
    cells = ae.game_seat_cells(row, a, current["steam-a"], None)
    c = _cell(cells, suspect)
    assert (c["val"], c["state"]) == (40, "flag_only")
    listed = ae.flag_list(flags, {"steam-a": 0, "steam-b": 1}, current)
    assert len(listed) == 2 and [r["current"] for r in listed] == [False, True]
    assert [r["reviewed"] for r in listed] == [True, False]
    assert ae.flag_obs({g: flags}, "steam-a") == 1
    print("GATE p15: FLAG cell %r from the successor, %d listed rows, flag_obs %d"
          % (c["val"], len(listed), ae.flag_obs({g: flags}, "steam-a")))


# ── P16 ────────────────────────────────────────────────────────────────────

def test_p16_observer_gaps_land_on_the_opposite_seat(live):
    a, b = _ids(2)
    gap = _key("obs.gap300", "OTHER")
    hb = _key("conn.hb_gaps", "OTHER")

    async def go():
        g1 = await live.match(a, b, T0, reporter=a, p1_obs_gap300=111, p2_hb_gap_count=7)
        g2 = await live.match(a, b, T0 + dt.timedelta(hours=1), reporter=b,
                              p2_obs_gap300=222, p1_hb_gap_count=8)
        r1 = (await live.rows("m.id = :g", {"g": g1}))[0]
        r2 = (await live.rows("m.id = :g", {"g": g2}))[0]
        return r1, r2

    r1, r2 = live.run(go())
    # p1 reports: its observer sentinel renders under p2 (b), nothing under p1.
    assert _cell(ae.game_seat_cells(r1, b, None, None), gap)["val"] == 111
    assert _cell(ae.game_seat_cells(r1, a, None, None), gap)["state"] == "not_recorded"
    # p2 reports: the twin renders under p1 (a).
    assert _cell(ae.game_seat_cells(r2, a, None, None), gap)["val"] == 222
    assert _cell(ae.game_seat_cells(r2, b, None, None), gap)["state"] == "not_recorded"
    # heartbeat gaps: the reporter's observation, stored on the other seat.
    assert _cell(ae.game_seat_cells(r1, b, None, None), hb)["val"] == 7
    assert _cell(ae.game_seat_cells(r1, a, None, None), hb)["state"] == "not_recorded"
    assert _cell(ae.game_seat_cells(r2, a, None, None), hb)["val"] == 8
    print("GATE p16: obs sentinel 111 under p2 (p1 reporting), twin 222 under p1; hb 7, 8 on the non-reporter")


# ── P10, cell half: summary windows (design 2.1, 5.5) ─────────────────────

def test_p10_player_and_pair_windows_are_distinct_cells(live):
    """A's net.hitch50 (A reporting): A-B games 1, 5, 9 and a newer A-C game
    50, after two older A-B games valued 4. Player window over the four
    covered games: n 4, median 7, max 50. Pair window ["seat",A,B]: n 3,
    median 5, max 9; ["seat",B,A]: not recorded (B never reports). Own
    measures anchor at the window's oldest covered game."""
    a, b, c_ = _ids(3)
    wmed = next(e for e in ae.REPORT_REGISTRY if e.base == HITCH.ki and e.agg == "win_median.cell")
    wmax = next(e for e in ae.REPORT_REGISTRY if e.base == HITCH.ki and e.agg == "win_max.cell")

    async def go():
        await live.match(a, b, T0, reporter=a, p1_net_hitch50=4)
        await live.match(b, a, T0 + dt.timedelta(minutes=1), reporter=a, p2_net_hitch50=4)
        ids = []
        for i, v in enumerate((1, 5, 9)):
            ids.append(await live.match(a, b, T0 + dt.timedelta(hours=1 + i),
                                        reporter=a, p1_net_hitch50=v))
        ids.append(await live.match(a, c_, T0 + dt.timedelta(hours=5), reporter=a,
                                    p1_net_hitch50=50))
        rows = await live.rows("m.id = ANY(CAST(:ids AS uuid[]))", {"ids": ids})
        oldest = rows[-1]
        player_base = await ae.read_baseline(live.conn, a, oldest["ended_at"],
                                             oldest["id"], covered=ids)
        pair_rows = [r for r in rows if ae.seat_of(r, b) is not None]
        pair_base = await ae.read_baseline(live.conn, a, pair_rows[-1]["ended_at"],
                                           pair_rows[-1]["id"], covered=ids, partner=b)
        return rows, pair_rows, player_base, pair_base

    rows, pair_rows, player_base, pair_base = live.run(go())
    player = {c["ki"]: c for c in ae.window_cells(rows, a, "player", player_base)}
    pair_ab = {c["ki"]: c for c in ae.window_cells(pair_rows, a, "pair", pair_base, partner=b)}
    pair_ba = {c["ki"]: c for c in ae.window_cells(pair_rows, b, "pair", None, partner=a)}
    assert len(player) == len(pair_ab) == 96
    assert (player[wmed.ki]["n"], player[wmed.ki]["val"]) == (4, 7)
    assert (player[wmax.ki]["n"], player[wmax.ki]["val"]) == (4, 50)
    assert (pair_ab[wmed.ki]["n"], pair_ab[wmed.ki]["val"]) == (3, 5)
    assert (pair_ab[wmax.ki]["n"], pair_ab[wmax.ki]["val"]) == (3, 9)
    assert pair_ba[wmax.ki]["state"] == "not_recorded" and pair_ba[wmax.ki]["n"] == 0
    assert player[wmed.ki]["own_mean"] == pytest.approx(4.0) and player[wmed.ki]["own_n"] == 2
    assert pair_ab[wmed.ki]["own_mean"] == pytest.approx(4.0)
    keys = {player[wmed.ki]["comparability"], player[wmax.ki]["comparability"],
            pair_ab[wmed.ki]["comparability"], pair_ab[wmax.ki]["comparability"]}
    assert len(keys) == 4
    one = ae.window_cells(rows[:1], a, "player", None)
    assert {c["ki"]: c for c in one}[wmax.ki]["comparability"] != player[wmax.ki]["comparability"]
    print("GATE p10 windows: player n4 median 7 max 50; pair A-B n3 median 5 max 9; "
          "B-A not recorded; %d distinct comparability keys" % len(keys))
