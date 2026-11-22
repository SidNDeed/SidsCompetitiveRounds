"""CHEAT-ALT-1 step 6: the read, main.alt_relations (design 8, 9; rulings R2
and R3; finding 24), against a real PostgreSQL.

Every figure is pinned on planted rows: the address and block relations
(shared marks, same-day days, any-day-only marks, the last shared day across
BOTH accounts, the smallest population, the classes on both accounts' rows),
the family lists (sharing the owner, lends to), the owner resolved at read
time (R2: candidates are current players, a cap with its own word, a row
under another key id unresolved, a box with no key its own word), and that
every account a list names is a current player (R3: a non-player and a
deleted player planted in every list). With the key withheld, no query over
the three tables alone yields an owner's id (R2's test, through real
sign-ins).

One case schema for the module, built by the ladder harness's procedure,
sealed, and dropped at the end:

    LADDER_TEST_PG_DSN=postgresql+asyncpg://user@host:port/<lane database>
    LADDER_TEST_PG_OPTOUT=1   waives the live cases deliberately (else they FAIL)

Ids are synthetic (below the first individual-account SteamID64).
"""
import asyncio
import datetime as dt
import hashlib
import itertools
import json
import os
import sys
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
import ladder_pg_harness as harness  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402
import test_alt_signals_record_pg as rec  # noqa: E402

TABLES = ("conn_markers", "steam_family_shares", "steam_signin_facts")
OTHER_KEY = "0123456789ab"
_IDS = itertools.count(1)


def _sid():
    return "76561190429%06d" % next(_IDS)


def _mk(label):
    """A fixed 32-byte mark for a planted row."""
    return hashlib.sha256(("alt-read-" + label).encode()).digest()


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def case():
    lh._require_live_pg()
    built = {}

    async def build():
        c = harness.CaseSchema(lh.DSN, "alt_read")
        await c.__aenter__()
        try:
            await lh._build(c, None)
            await c.conn.execute(
                "INSERT INTO pending_channel_posts (channel_id, content, sort_order, revision, posted_revision)"
                " VALUES ($1, $2, 1, 3, 3)", rec.FAQ_CHANNEL, rec._faq_text())
        except BaseException:
            await c.__aexit__(None, None, None)
            raise
        built.update(schema=c.schema, own=c.own)
        await c.conn.close()
    _run(build())
    try:
        yield built["schema"]
    finally:
        async def drop():
            conn = await harness.connect_bound(lh.DSN, built["schema"])
            try:
                await harness.drop_case_schema(conn, built["schema"], built["own"])
            finally:
                await conn.close()
        _run(drop())


@pytest.fixture
def clean(case):
    async def body(sm, _rsm):
        async with sm() as db:
            for t in TABLES:
                await db.execute(text("DELETE FROM %s" % t))
            await db.execute(text("UPDATE players SET deleted_at = now() WHERE deleted_at IS NULL"))
            await db.commit()
    rec._with(case, body)
    return case


@pytest.fixture
def key():
    A.install(rec.KEY_HEX)
    yield A.loaded_key()
    A.install(None)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", rec.HMAC_KEY)
    monkeypatch.setenv("STEAM_WEB_API_KEY", "alt-read-steam-key")
    monkeypatch.delenv("STEAM_AUTH_ENFORCE", raising=False)
    monkeypatch.setattr(main, "_steam_http_get_json",
                        lambda url, timeout: {"response": {"params": dict(rec.STEAM["params"])}})
    A.install(rec.KEY_HEX)
    main._alt_notice_line_at[0] = None
    yield monkeypatch
    A.install(None)
    main._alt_notice_line_at[0] = None


async def _player(db, sid, deleted=False):
    await lh._insert(db, "players", {"id": uuid.uuid4(), "steam_id": sid, "display_name": "ar-" + sid[-4:]})
    if deleted:
        await db.execute(text("UPDATE players SET deleted_at = now() WHERE steam_id = :s"), {"s": sid})


async def _marker(db, sid, days_ago, addr, block, cls="none", key_id=None):
    await db.execute(text(
        "INSERT INTO conn_markers (steam_id, day, key_id, addr_mark, block_mark, family, conn_class, first_at, last_at)"
        " SELECT :s, CAST((t AT TIME ZONE 'UTC') AS date), :k, :a, :b, 4, :c, t, t"
        " FROM (SELECT now() - make_interval(days => CAST(:d AS integer)) AS t) z"),
        {"s": sid, "k": key_id, "a": _mk(addr), "b": _mk(block), "c": cls, "d": days_ago})


async def _share(db, sid, owner_mark, key_id, days_ago=1):
    await db.execute(text(
        "INSERT INTO steam_family_shares (steam_id, key_id, owner_mark, first_seen_at, last_seen_at)"
        " SELECT :s, :k, :m, t, t FROM (SELECT now() - make_interval(days => CAST(:d AS integer)) AS t) z"),
        {"s": sid, "k": key_id, "m": owner_mark, "d": days_ago})


async def _today(db):
    return (await db.execute(text("SELECT CAST((now() AT TIME ZONE 'UTC') AS date)"))).scalar()


def _day(today, n):
    return (today - dt.timedelta(days=n)).isoformat()


def _ids(part):
    return [r["steam_id"] for r in part["related"]]


# -- the scene ----------------------------------------------------------------------
#
# S is the subject. Marks (key K, the loaded key) by label, with the days ago:
#   S: addr A blk b1 at 10 and 5 (none, vpn); addr B blk b2 at 3 (hosting);
#      addr C blk b9 at 100 (outside the window); addr F blk b8 at 1 under OTHER_KEY.
#   X (player): addr A blk b1 at 5 (none) and 2 (relay); addr B blk b3 at 4 (none).
#   Y (player): addr A blk b1 at 20 (unknown).
#   W (player): addr E blk b2 at 3 (tor).
#   Z (no players row) and D (deleted player): addr A blk b1 at 5, and addr B blk b2 at 3.
# Address: A has accounts S X Y Z D (5); B has S X Z D (4).
#   X: shared 2, same days 1 (day 5), any-day-only 1 (B), last shared day 2, smallest 4,
#      classes hosting none relay vpn.
#   Y: shared 1, same 0, any-day-only 1, last shared day 5 (S's day, later than Y's 20),
#      smallest 5, classes none unknown vpn.
# Block: b1 has S X Y Z D (5); b2 has S W Z D (4).
#   W: shared 1, same 1 (day 3), any-day-only 0, last 3, smallest 4, classes hosting tor.
#   X: shared 1, same 1 (day 5), any-day-only 0, last 2, smallest 5, classes none relay vpn.
#   Y: shared 1, same 0, any-day-only 1, last 5, smallest 5, classes none unknown vpn.
# Family (key K unless named): S borrows from O (player), from N (no players row),
#   from DP (deleted player), and under OTHER_KEY from a mark of the player O2.
#   Sharing S's owner (K, mark of O): X2 (player), N2 (no row), DP2 (deleted).
#   Sharing under OTHER_KEY: X3 (player).
#   Lending from S (K, mark of S): B1 (player), B2 (no row), B3 (deleted); under
#   OTHER_KEY with the same bytes: B4 (player), never listed.

async def _scene(sm, key):
    p = {n: _sid() for n in ("S", "X", "Y", "W", "Z", "D", "O", "N", "DP", "O2",
                             "X2", "N2", "DP2", "X3", "B1", "B2", "B3", "B4")}
    K = key.key_id
    mark = (lambda n: A.account_mark(key.secret, p[n]))
    async with sm() as db:
        for n in ("S", "X", "Y", "W", "O", "O2", "X2", "X3", "B1", "B4"):
            await _player(db, p[n])
        for n in ("D", "DP", "DP2", "B3"):
            await _player(db, p[n], deleted=True)
        await _marker(db, p["S"], 10, "A", "b1", "none", K)
        await _marker(db, p["S"], 5, "A", "b1", "vpn", K)
        await _marker(db, p["S"], 3, "B", "b2", "hosting", K)
        await _marker(db, p["S"], 100, "C", "b9", "none", K)
        await _marker(db, p["S"], 1, "F", "b8", "none", OTHER_KEY)
        await _marker(db, p["X"], 5, "A", "b1", "none", K)
        await _marker(db, p["X"], 2, "A", "b1", "relay", K)
        await _marker(db, p["X"], 4, "B", "b3", "none", K)
        await _marker(db, p["Y"], 20, "A", "b1", "unknown", K)
        await _marker(db, p["W"], 3, "E", "b2", "tor", K)
        for n in ("Z", "D"):
            await _marker(db, p[n], 5, "A", "b1", "none", K)
            await _marker(db, p[n], 3, "B", "b2", "none", K)
        await _share(db, p["S"], mark("O"), K)
        await _share(db, p["S"], mark("N"), K)
        await _share(db, p["S"], mark("DP"), K)
        await _share(db, p["S"], mark("O2"), OTHER_KEY)
        for n, days in (("X2", 2), ("N2", 1), ("DP2", 1)):
            await _share(db, p[n], mark("O"), K, days)
        await _share(db, p["X3"], mark("O2"), OTHER_KEY, 3)
        for n in ("B1", "B2", "B3"):
            await _share(db, p[n], mark("S"), K)
        await _share(db, p["B4"], mark("S"), OTHER_KEY)
        await db.execute(text(
            "INSERT INTO steam_signin_facts (steam_id, first_seen_at, last_seen_at, copy_state,"
            " shared_first_at, shared_last_at, vac_banned, vac_banned_first_at, vac_banned_last_at,"
            " publisher_banned, over_limit_days, over_limit_day)"
            " VALUES (:s, now() - interval '30 days', now(), 'shared', now() - interval '20 days', now(),"
            " true, now() - interval '9 days', now() - interval '2 days', false, 2, CAST(now() AS date))"),
            {"s": p["S"]})
        await db.commit()
        today = await _today(db)
    return p, today


def _read(case, sid, **kw):
    async def body(sm, _rsm):
        async with sm() as db:
            return await main.alt_relations(db, sid, **kw)
    return rec._with(case, body)


def _setup(case, key):
    async def body(sm, _rsm):
        return await _scene(sm, key)
    return rec._with(case, body)


def test_every_figure_of_the_address_and_block_relations(clean, key):
    p, today = _setup(clean, key)
    res = _read(clean, p["S"])
    assert res["window_days"] == A.DUE_DAYS
    assert res["address"] == {"related": [
        {"steam_id": p["X"], "shared_markers": 2, "same_day_days": 1, "any_day_only": 1,
         "last_shared_day": _day(today, 2), "min_population": 4,
         "classes": ["hosting", "none", "relay", "vpn"]},
        {"steam_id": p["Y"], "shared_markers": 1, "same_day_days": 0, "any_day_only": 1,
         "last_shared_day": _day(today, 5), "min_population": 5,
         "classes": ["none", "unknown", "vpn"]}], "more": 0}, res["address"]
    assert res["block"] == {"related": [
        {"steam_id": p["W"], "shared_markers": 1, "same_day_days": 1, "any_day_only": 0,
         "last_shared_day": _day(today, 3), "min_population": 4, "classes": ["hosting", "tor"]},
        {"steam_id": p["X"], "shared_markers": 1, "same_day_days": 1, "any_day_only": 0,
         "last_shared_day": _day(today, 2), "min_population": 5, "classes": ["none", "relay", "vpn"]},
        {"steam_id": p["Y"], "shared_markers": 1, "same_day_days": 0, "any_day_only": 1,
         "last_shared_day": _day(today, 5), "min_population": 5,
         "classes": ["none", "unknown", "vpn"]}], "more": 0}, res["block"]


def test_the_recorded_counts_and_the_steam_part(clean, key):
    p, today = _setup(clean, key)
    res = _read(clean, p["S"])
    assert res["recorded"] == {"facts": True, "markers": 4, "address_days": 4, "shares": 4,
                               "earlier_key_rows": 2, "over_limit_days": 2}, res["recorded"]
    steam = res["steam"]
    assert steam["copy_state"] == "shared" and steam["vac_banned"] is True and steam["publisher_banned"] is False
    assert steam["publisher_banned_first_at"] is None and steam["vac_banned_first_at"] < steam["vac_banned_last_at"]
    assert set(steam) == {"copy_state", "first_seen_at", "last_seen_at", "vac_banned", "vac_banned_first_at",
                          "vac_banned_last_at", "publisher_banned", "publisher_banned_first_at",
                          "publisher_banned_last_at"}, steam


def test_the_family_lists_and_the_owner_resolved_at_read_time(clean, key):
    p, _today = _setup(clean, key)
    fam = _read(clean, p["S"])["family"]
    assert fam["owner"] == {"state": "resolved", "steam_ids": [p["O"]], "unresolved": 3}, fam["owner"]
    assert _ids(fam["sharing_owner"]) == [p["X2"], p["X3"]] and fam["sharing_owner"]["more"] == 0, fam
    assert [r["owners"] for r in fam["sharing_owner"]["related"]] == [1, 1]
    assert _ids(fam["lends_to"]) == [p["B1"]] and fam["lends_to"]["more"] == 0, fam


def test_every_list_names_only_current_players(clean, key):
    """R3: Z and N (no players row) and D and DP (deleted players) are planted
    into the address, block, sharing and lending lists and as owners; no list
    names them, and the populations still count them."""
    p, _today = _setup(clean, key)
    res = _read(clean, p["S"])
    named = (_ids(res["address"]) + _ids(res["block"]) + _ids(res["family"]["sharing_owner"])
             + _ids(res["family"]["lends_to"]) + res["family"]["owner"]["steam_ids"])
    for n in ("Z", "D", "N", "DP", "N2", "DP2", "B2", "B3"):
        assert p[n] not in named, n
    assert res["address"]["related"][0]["min_population"] == 4      # Z and D are counted


def test_a_row_under_another_key_id_stays_unresolved_even_when_its_bytes_match(clean, key):
    """S's OTHER_KEY share row carries the mark of the player O2 computed with
    the loaded secret: it still resolves to nothing, because its key id is not
    the loaded one."""
    p, _today = _setup(clean, key)
    owner = _read(clean, p["S"])["family"]["owner"]
    assert p["O2"] not in owner["steam_ids"], owner


def test_above_the_candidate_cap_the_owner_is_not_computed(clean, key, monkeypatch):
    p, _today = _setup(clean, key)
    monkeypatch.setattr(A, "OWNER_CANDIDATE_CAP", 3)
    res = _read(clean, p["S"])
    assert res["family"]["owner"] == {"state": "not_computed"}, res["family"]
    assert _ids(res["family"]["lends_to"]) == [p["B1"]]            # one mark: still computed


def test_no_share_row_in_the_window_is_its_own_word(clean, key):
    p, _today = _setup(clean, key)
    assert _read(clean, p["X"])["family"]["owner"] == {"state": "none"}


def test_a_box_with_no_key_says_so_and_still_serves_the_joins(clean, key):
    p, _today = _setup(clean, key)
    A.install(None)
    res = _read(clean, p["S"])
    assert res["family"]["owner"] == {"state": "no_key"} and res["family"]["lends_to"] == {"state": "no_key"}
    assert res["recorded"]["earlier_key_rows"] is None
    assert _ids(res["family"]["sharing_owner"]) == [p["X2"], p["X3"]]
    assert _ids(res["address"]) == [p["X"], p["Y"]]


def test_the_window_is_the_due_age_or_smaller_never_larger(clean, key):
    p, today = _setup(clean, key)
    assert _read(clean, p["S"], days=10 ** 4)["window_days"] == A.DUE_DAYS
    # Six days: S's row of A at ten days and Y's row at twenty leave the window,
    # so Y is gone and A's population drops to S X Z D.
    small = _read(clean, p["S"], days=6)
    assert small["window_days"] == 6
    assert small["address"] == {"related": [
        {"steam_id": p["X"], "shared_markers": 2, "same_day_days": 1, "any_day_only": 1,
         "last_shared_day": _day(today, 2), "min_population": 4,
         "classes": ["hosting", "none", "relay", "vpn"]}], "more": 0}, small["address"]
    assert small["recorded"]["markers"] == 3 and small["recorded"]["address_days"] == 3, small["recorded"]
    for bad in (0, -1, 1.5, "7", True):
        with pytest.raises(ValueError):
            _read(clean, p["S"], days=bad)


def test_a_list_holds_at_most_its_cap_and_says_how_many_more(clean, key, monkeypatch):
    p, _today = _setup(clean, key)
    monkeypatch.setattr(A, "LIST_CAP", 1)
    res = _read(clean, p["S"])
    assert _ids(res["address"]) == [p["X"]] and res["address"]["more"] == 1
    assert _ids(res["block"]) == [p["W"]] and res["block"]["more"] == 2
    assert _ids(res["family"]["sharing_owner"]) == [p["X2"]] and res["family"]["sharing_owner"]["more"] == 1


def test_the_answer_holds_no_mark_no_key_id_and_no_address(clean, key):
    p, _today = _setup(clean, key)
    blob = json.dumps(_read(clean, p["S"]), sort_keys=True)
    for label in ("A", "B", "C", "E", "F", "b1", "b2", "b3", "b8", "b9"):
        assert _mk(label).hex() not in blob, label
    for n in ("O", "N", "DP", "O2", "S"):
        assert A.account_mark(key.secret, p[n]).hex() not in blob, n
    assert key.key_id not in blob and OTHER_KEY not in blob


def test_an_account_with_nothing_recorded(clean, key):
    res = _read(clean, _sid())
    assert res["recorded"] == {"facts": False, "markers": 0, "address_days": 0, "shares": 0,
                               "earlier_key_rows": 0, "over_limit_days": 0}, res
    assert res["steam"] is None
    assert res["address"] == {"related": [], "more": 0} and res["block"] == {"related": [], "more": 0}
    assert res["family"] == {"owner": {"state": "none"}, "sharing_owner": {"related": [], "more": 0},
                             "lends_to": {"related": [], "more": 0}}, res["family"]


# -- R2: with the key withheld, nothing resolves an owner -----------------------

def test_with_the_key_withheld_no_query_over_the_three_tables_yields_an_owner(clean, env):
    """Real sign-ins with the key loaded: O on its own copy, S and X on O's.
    Then the key is withheld. O's id appears in no column of any row but as
    the row key of O's own rows, and the mark of O that S's and X's share
    rows hold appears in no other column of any row, so no join over the
    three tables alone reaches O. The read without the key says no_key and
    still lists X as sharing S's owner."""
    s, x, o = _sid(), _sid(), _sid()

    async def body(sm, rsm):
        async with sm() as db:
            for n in (s, x, o):
                await _player(db, n)
            await db.commit()
        # O signs in from another address and another /24, so no relation
        # but the family's names O.
        for n, owner, host in ((o, None, rec.ADDRESSES[1]), (s, o, rec.ADDRESSES[0]), (x, o, rec.ADDRESSES[0])):
            status, ans, _plan = await rec._sign_in(rsm, n, host=host, owner=owner)
            rec._like_baseline(status, ans)
        A.install(None)
        rows = {}
        async with sm() as db:
            for t in TABLES:
                rows[t] = [dict(r) for r in (await db.execute(text("SELECT * FROM %s" % t))).mappings().all()]
            res = await main.alt_relations(db, s)
        return rows, res

    rows, res = rec._with(clean, body)
    shares = [r for r in rows["steam_family_shares"] if r["steam_id"] in (s, x)]
    assert len(shares) == 2, rows["steam_family_shares"]
    owner_marks = {bytes(r["owner_mark"]) for r in shares}
    assert len(owner_marks) == 1
    for t, rs in rows.items():
        for r in rs:
            for col, val in r.items():
                if not (t == "steam_family_shares" and col == "owner_mark"):
                    if isinstance(val, (bytes, bytearray, memoryview)):
                        assert bytes(val) not in owner_marks, (t, col)
                if not (col == "steam_id" and val == o):
                    assert o not in str(val), (t, col)
    assert res["family"]["owner"] == {"state": "no_key"}
    assert _ids(res["family"]["sharing_owner"]) == [x]
    assert o not in json.dumps(res)
