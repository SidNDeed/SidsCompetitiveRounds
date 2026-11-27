"""ALT-BAN-1 step 5: the retention pass keeps the rows of an account under an
active ban and takes them after (bar A5), against a real PostgreSQL.

  * The lane's three tables: a due row of an account under an active ban
    (models.player_ban_active_sql, read in the same statement as the
    delete) is kept, at 90 and at 364 days; once the ban has ended (by its
    end time or lifted) each row goes by its own last sight.
  * ban_regions: kept while the ban stands, taken at the first pass after
    it ends (ruling T0, 4), whatever the row's age.
  * ban_link_notices: taken when the banned account's ban has ended; an
    UNPOSTED pair also when the other account has no marker row left; a
    posted pair stays while the ban stands.
  * The counts of what is left name only rows the pass would take.
  * 2000 due rows behind 2920 kept ones (one banned account's markers at
    the one-year cap, older than every due row) are taken in one pass, each
    batch inside the pass's limits.

The case schema is test_alt_signals_retention_pg's (its fixture, its plants).
Ids are synthetic (below the first individual-account SteamID64).
"""
import asyncio
import os
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
for _p in (API, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

import alt_signals as A  # noqa: E402
import main  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402
import test_alt_signals_record_pg as rec  # noqa: E402
import test_alt_signals_retention_pg as ret  # noqa: E402
from test_alt_signals_retention_pg import case  # noqa: E402,F401  (fixture)

KINDS = ("markers", "shares", "facts")
BAN_TABLES = ("ban_regions", "ban_link_notices")


@pytest.fixture
def clean(case):  # noqa: F811
    """No fault, and no row in the five tables or in player_bans."""
    async def body(sm, _rsm):
        async with sm() as db:
            await db.execute(text("DELETE FROM alt_test_faults"))
            for t in tuple(ret.TABLES.values()) + BAN_TABLES:
                await db.execute(text("DELETE FROM %s" % t))
            await db.execute(text("DELETE FROM player_bans"))
            await db.commit()
    rec._with(case, body)
    return case


def _ids():
    """(prefix, id): the facts plant appends 0001 to the prefix, so every
    table's rows of one account carry the same 17-digit id."""
    p = ret._sid()
    return p, p + "0001"


async def _plant_all(sm, prefix, sid, secs=60, days=None):
    """One due row (by default a minute past due) of each of the lane's
    tables, and one region row."""
    d = A.DUE_DAYS if days is None else days
    for kind in KINDS:
        s = prefix if kind == "facts" else sid
        async with sm() as db:
            await db.execute(text(ret._PLANT[kind]), {"s": s, "n": 1, "d": d, "x": float(secs)})
            await db.commit()
    async with sm() as db:
        await db.execute(text(
            "INSERT INTO ban_regions (steam_id, region, conn_class, first_at, last_at)"
            " VALUES (:s, 'Ardenmark, Vellshire', 'unknown',"
            " now() - make_interval(days => CAST(:d AS integer)), now() - make_interval(days => CAST(:d AS integer)))"),
            {"s": sid, "d": d})
        await db.commit()


async def _ban(sm, sid, how="active"):
    """A ban row: 'active' (ends in 300 days), 'ended' (by its end time),
    'lifted' (unbanned_at set). Begun 30 days ago: no ban runs past one year
    (migration 418's player_bans_max_one_year)."""
    async with sm() as db:
        admin = rec._sid()
        await lh._insert(db, "admin_users", {"steam_id": admin})
        await lh._insert(db, "players", {"id": uuid.uuid4(), "steam_id": sid, "display_name": "ar-" + sid[-4:]})
        await db.execute(text(
            "INSERT INTO player_bans (id, steam_id, reason, banned_by_steam_id, banned_at, expires_at, unbanned_at)"
            " VALUES (:id, :s, 'alt-ban', :a, now() - interval '30 days',"
            " CASE WHEN CAST(:h AS text) = 'ended' THEN now() - interval '1 second' ELSE now() + interval '300 days' END,"
            " CASE WHEN CAST(:h AS text) = 'lifted' THEN now() - interval '1 second' END)"),
            {"id": uuid.uuid4(), "s": sid, "a": admin, "h": how})
        await db.commit()


async def _end(sm, sid, how):
    async with sm() as db:
        if how == "ended":
            await db.execute(text("UPDATE player_bans SET expires_at = now() - interval '1 second'"
                                  " WHERE steam_id = :s"), {"s": sid})
        else:
            await db.execute(text("UPDATE player_bans SET unbanned_at = now() - interval '1 second'"
                                  " WHERE steam_id = :s"), {"s": sid})
        await db.commit()


async def _counts(sm, sid):
    async with sm() as db:
        return [(await db.execute(text("SELECT count(*) FROM %s WHERE steam_id = :s" % t), {"s": sid})).scalar()
                for t in ("conn_markers", "steam_family_shares", "steam_signin_facts", "ban_regions")]


def _pass(sm, at=None):
    return main._alt_retention_pass(session_factory=sm, at=at)


# -- kept while banned, taken after ----------------------------------------------------

@pytest.mark.parametrize("days", [90, 364])
def test_the_rows_of_an_account_under_an_active_ban_are_kept(clean, capsys, days):
    prefix, sid = _ids()

    async def body(sm, _rsm):
        await _ban(sm, sid)
        await _plant_all(sm, prefix, sid, days=days)
        res = await _pass(sm)
        return res, await _counts(sm, sid)

    res, counts = rec._with(clean, body)
    assert counts == [1, 1, 1, 1], counts
    assert res["deleted"] == {k: 0 for k in KINDS} and res["left"] == {k: 0 for k in KINDS}, res
    assert res["ban"] == {"deleted": {"regions": 0, "notices": 0}, "left": {"regions": 0, "notices": 0}}, res
    lines = ret._alt_lines(capsys)
    assert ret._pass_line(lines) == (0, 0, 0, 5), lines      # one batch per table, five tables
    assert not [ln for ln in lines if "left" in ln], lines


@pytest.mark.parametrize("how", ["ended", "lifted"])
def test_once_the_ban_has_ended_due_rows_go_and_the_region_goes_at_the_next_pass(clean, capsys, how):
    prefix, sid = _ids()
    young_prefix, young = _ids()

    async def body(sm, _rsm):
        await _ban(sm, sid)
        await _ban(sm, young)
        await _plant_all(sm, prefix, sid)
        await _plant_all(sm, young_prefix, young, secs=-3600)   # an hour short of due
        first = await _pass(sm)
        await _end(sm, sid, how)
        await _end(sm, young, how)
        second = await _pass(sm)
        return first, second, await _counts(sm, sid), await _counts(sm, young)

    first, second, gone, kept = rec._with(clean, body)
    assert first["deleted"] == {k: 0 for k in KINDS} and first["ban"]["deleted"]["regions"] == 0, first
    assert second["deleted"] == {k: 1 for k in KINDS}, second
    assert second["ban"]["deleted"] == {"regions": 2, "notices": 0}, second
    assert gone == [0, 0, 0, 0], gone
    assert kept == [1, 1, 1, 0], "the lane's rows go by their own last sight, the region at once"
    lines = ret._alt_lines(capsys)
    assert "[ALT-RETENTION] ban rows: deleted regions 2, notices 0" in lines, lines


def test_another_accounts_ban_keeps_nothing_of_this_one(clean):
    """The condition is on the row's own account."""
    prefix, sid = _ids()
    _p2, other = _ids()

    async def body(sm, _rsm):
        await _ban(sm, other)
        await _plant_all(sm, prefix, sid)
        await _pass(sm)
        return await _counts(sm, sid)

    assert rec._with(clean, body) == [0, 0, 0, 0]


def test_the_link_notices_go_when_the_ban_ends_and_an_unposted_one_when_the_other_side_has_no_marker(clean):
    """Fix 1, H4: a posted pair of a standing ban stays though its other
    side has no marker left; an unposted one goes; every pair of an ended
    ban goes."""
    banned_prefix, banned = _ids()
    _p1, other_with = _ids()
    _p2, other_without = _ids()
    _p3, ended = _ids()
    _p4, other_posted = _ids()

    async def body(sm, _rsm):
        await _ban(sm, banned)
        await _ban(sm, ended, how="ended")
        async with sm() as db:
            await db.execute(text(ret._PLANT["markers"]),
                             {"s": other_with, "n": 1, "d": 1, "x": 0.0})
            for b, o in ((banned, other_with), (banned, other_without), (ended, other_with)):
                await db.execute(text("INSERT INTO ban_link_notices (banned_steam_id, other_steam_id)"
                                      " VALUES (:b, :o)"), {"b": b, "o": o})
            for b, o in ((banned, other_posted), (ended, other_posted)):
                await db.execute(text("INSERT INTO ban_link_notices (banned_steam_id, other_steam_id, posted_at)"
                                      " VALUES (:b, :o, now())"), {"b": b, "o": o})
            await db.commit()
        res = await _pass(sm)
        async with sm() as db:
            left = sorted(tuple(r) for r in (await db.execute(text(
                "SELECT banned_steam_id, other_steam_id FROM ban_link_notices"))).all())
        return res, left

    res, left = rec._with(clean, body)
    assert left == sorted([(banned, other_with), (banned, other_posted)]), left
    assert res["ban"]["deleted"]["notices"] == 3, res


# -- the counts of what is left ------------------------------------------------------------

def test_the_count_of_rows_left_names_only_rows_the_pass_would_take(clean, monkeypatch, capsys):
    """Budget at zero: one batch of two per table, then the count. Five due
    rows of unbanned ids and five of a banned account per table (the facts
    table holds one row per account, and its plant gives each row an id of
    its own: the banned account's facts row is its one row): three markers
    left of the first, none of the second."""
    monkeypatch.setattr(A, "PASS_BATCH", 2)
    monkeypatch.setattr(A, "PASS_BUDGET_S", 0)
    free_prefix, free = _ids()
    banned_prefix, banned = _ids()

    async def body(sm, _rsm):
        await _ban(sm, banned)
        for prefix, sid in ((free_prefix, free), (banned_prefix, banned)):
            for kind in KINDS:
                async with sm() as db:
                    s = prefix if kind == "facts" else sid
                    n = 1 if (kind == "facts" and sid == banned) else 5
                    await db.execute(text(ret._PLANT[kind]), {"s": s, "n": n, "d": A.DUE_DAYS, "x": 60.0})
                    await db.commit()
        return await _pass(sm)

    res = rec._with(clean, body)
    # the budget ends the pass after its first batch (markers)
    assert res["batches"] == 1 and res["deleted"]["markers"] == 2, res
    assert res["left"] == {"markers": 3, "shares": 5, "facts": 5}, res
    assert "[ALT-RETENTION] due rows left: markers 3, shares 5, facts 5" in ret._alt_lines(capsys)


def test_the_ban_rows_left_are_counted_and_said(clean, monkeypatch, capsys):
    monkeypatch.setattr(A, "PASS_BATCH", 1)
    monkeypatch.setattr(A, "PASS_BUDGET_S", 0)
    ids = [_ids()[1] for _ in range(3)]

    async def body(sm, _rsm):
        async with sm() as db:
            for sid in ids:
                await db.execute(text("INSERT INTO ban_regions (steam_id, region) VALUES (:s, 'Brynmoor')"),
                                 {"s": sid})
            await db.commit()
        return await _pass(sm)

    res = rec._with(clean, body)
    assert res["ban"]["left"]["regions"] == 3, res      # the budget ended the pass before the regions arm
    assert "[ALT-RETENTION] ban rows left: regions 3, notices 0" in ret._alt_lines(capsys)


# -- 2000 due rows behind 2920 kept ones ----------------------------------------------------

def test_two_thousand_due_rows_behind_two_thousand_nine_hundred_twenty_kept_ones(clean, capsys):
    """One banned account's markers at the one-year cap (8 x 365 = 2920),
    each older than every due row, so each batch walks past them at the old
    end of the last_at index; 2000 due markers of 20 unbanned accounts. One
    pass takes the 2000 and keeps the 2920; each batch is timed."""
    _bp, banned = _ids()
    free = [_ids()[1] for _ in range(20)]
    times = []
    orig = main._alt_retention_batch

    async def timed(db, table, at=None):
        t0 = time.perf_counter()
        try:
            return await orig(db, table, at)
        finally:
            times.append((table, time.perf_counter() - t0))

    async def body(sm, _rsm):
        await _ban(sm, banned)
        async with sm() as db:
            await db.execute(text(ret._PLANT["markers"]), {"s": banned, "n": 2920, "d": 364, "x": 0.0})
            for sid in free:
                await db.execute(text(ret._PLANT["markers"]), {"s": sid, "n": 100, "d": A.DUE_DAYS, "x": 60.0})
            await db.commit()
        main._alt_retention_batch = timed
        try:
            res = await _pass(sm)
        finally:
            main._alt_retention_batch = orig
        async with sm() as db:
            kept = (await db.execute(text("SELECT count(*) FROM conn_markers WHERE steam_id = :s"),
                                     {"s": banned})).scalar()
            rest = (await db.execute(text("SELECT count(*) FROM conn_markers WHERE steam_id <> :s"),
                                     {"s": banned})).scalar()
        return res, kept, rest

    res, kept, rest = rec._with(clean, body)
    assert res["deleted"]["markers"] == 2000 and kept == 2920 and rest == 0, (res, kept, rest)
    marker_batches = [s for t, s in times if t == "markers"]
    worst = max(marker_batches)
    print("[MEASURE] markers batches %d, slowest %.1f ms, all %.1f ms"
          % (len(marker_batches), worst * 1000, sum(marker_batches) * 1000))
    assert worst < A.PASS_STATEMENT_TIMEOUT_MS / 1000.0, worst
