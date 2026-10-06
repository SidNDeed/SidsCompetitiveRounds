"""Item 20, the contract between the binder's client half and this server half.

The client half lives in the v1.41.0 client lane (commits f06eaff9, ddf7759c,
5423e08e). What it sends and what it reads, taken from that lane's
plugin/ApiClient.cs:

  * the REQUEST is `GET /api/v1/pc/collection?steam_id=..&sig=..` (own
    binder, canon `pcread:{steam}:collection:-`) or the same with
    `&subject=..` (another player's binder). It carries NO sort key: the six
    binder orders are computed on the client (BinderSortRules.cs), so the only
    thing the sort needs from this server is the four keys below.
  * the ANSWER is read with PcTopLevel, which matches a whole quoted key at
    depth 1:
        top level   subject_standings   PcBool  -> only the token `true` is true
        per print   subject_board_rank  PcInt   -> null or absent reads 0, "not on the board"
                    subject_rating      PcFloat -> null or absent reads 0.0
                                        PcHas   -> present AND not null = rated
                    subject_inactive    PcBool  -> only `true` is true

So a "malformed sort key" on this wire is a value the client would misread:
a board rank of 0 or below (reads as off the board, or as a position that
does not exist), a bool where an int belongs (`true` is not an integer token,
so PcInt reads 0), a rating sent for an unrated subject (PcHas would call a
subject rated that has no rating row), a flag sent as anything but a JSON bool,
or a key spelt any other way (PcTopLevel then finds nothing and every subject
reads as off the board). The server never emits one: the checks below hold
every emitted value to the domain the client parses, and each carries the
negative control that shows the same check reds on the malformed value.

Two halves. The static half runs everywhere. The live half drives the real
route, `main.pc_collection`, against the dance harness's throwaway Postgres
(DANCE_CARDS_TEST_PG_DSN) and runs the JSON it returns through a port of the
client's readers.

When ITEM20_CLIENT_APICLIENT names a copy of the lane's plugin/ApiClient.cs,
the literals this file pins are also checked against that source, so a rename
on either side reds here rather than in a binder that quietly offers five
sorts.
"""
import json
import os
import re
import sys
import uuid

import pytest
from sqlalchemy import text

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "api"))

import dance_pg_harness as dp  # noqa: E402
import main  # noqa: E402

TOP_KEY = "subject_standings"
PRINT_KEYS = ("subject_board_rank", "subject_rating", "subject_inactive")
CLIENT_SRC_VAR = "ITEM20_CLIENT_APICLIENT"
SECRET = "item20-contract-" + uuid.uuid4().hex


# -- a port of the client's readers (ApiClient.cs PcTopLevel and friends) -----

def _raw(obj, key):
    """The JSON token PcTopLevel would hand back for `key`, or None when the
    key is absent. Serialising through json is the point: the client sees
    tokens, not Python values."""
    if key not in obj:
        return None
    return json.dumps(obj[key])


def pc_int(raw):
    if raw is None or raw == "null":
        return 0
    s = raw.strip('"')
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return 0


def pc_float(raw):
    if raw is None or raw == "null":
        return 0.0
    try:
        return float(raw.strip('"'))
    except ValueError:
        return 0.0


def pc_bool(raw):
    return raw == "true"


def pc_has(obj, key):
    r = _raw(obj, key)
    return r is not None and r != "null"


def client_reads(print_obj):
    """(board_rank, rating, rated, inactive) exactly as the client's
    ParsePcPrint fills them."""
    return (pc_int(_raw(print_obj, "subject_board_rank")),
            pc_float(_raw(print_obj, "subject_rating")),
            pc_has(print_obj, "subject_rating"),
            pc_bool(_raw(print_obj, "subject_inactive")))


def malformed(print_obj):
    """Every reason the client would misread this print's standings; empty
    when the print is well formed. Absent keys are well formed (the subject
    has no standings row and the client reads the off-board defaults)."""
    bad = []
    stray = [k for k in print_obj if k.startswith("subject_") and k not in PRINT_KEYS
             and k != "subject_player_id"]
    if stray:
        bad.append("unknown key(s) %s" % stray)
    present = [k for k in PRINT_KEYS if k in print_obj]
    if present and len(present) != len(PRINT_KEYS):
        bad.append("partial standings %s" % present)
    if "subject_board_rank" in print_obj:
        v = print_obj["subject_board_rank"]
        if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 1):
            bad.append("board rank %r" % (v,))
    if "subject_rating" in print_obj:
        v = print_obj["subject_rating"]
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
            bad.append("rating %r" % (v,))
    if "subject_inactive" in print_obj and not isinstance(print_obj["subject_inactive"], bool):
        bad.append("inactive %r" % (print_obj["subject_inactive"],))
    return bad


# -- the static half -----------------------------------------------------------

def test_the_reader_port_rejects_each_malformed_value():
    """Negative controls for `malformed`: a check that cannot fail is worse
    than none (#342). Each mutation below is a value the client would misread,
    and each must be named."""
    good = {"subject_player_id": "x", "subject_board_rank": 7,
            "subject_rating": 1834.5, "subject_inactive": False}
    assert malformed(good) == []
    assert client_reads(good) == (7, 1834.5, True, False)
    off = {"subject_player_id": "x", "subject_board_rank": None,
           "subject_rating": None, "subject_inactive": True}
    assert malformed(off) == []
    assert client_reads(off) == (0, 0.0, False, True)
    assert client_reads({"subject_player_id": "x"}) == (0, 0.0, False, False)
    for mutate in ({"subject_board_rank": 0}, {"subject_board_rank": -3},
                   {"subject_board_rank": True}, {"subject_board_rank": "7"},
                   {"subject_board_rank": 7.0},
                   {"subject_rating": "1834.5"}, {"subject_rating": False},
                   {"subject_inactive": 0}, {"subject_inactive": "false"},
                   {"subject_rank": 7}):
        assert malformed(dict(good, **mutate)), mutate
    partial = dict(good)
    del partial["subject_inactive"]
    assert malformed(partial)
    # what the misreads cost, through the port: a bool rank reads as off the
    # board, and a misspelt key leaves the subject off the board
    assert client_reads(dict(good, subject_board_rank=True))[0] == 0
    respelt = {"subject_player_id": "x", "subject_rank": 7,
               "subject_rating": 1834.5, "subject_inactive": False}
    assert client_reads(respelt)[0] == 0


def test_the_route_takes_no_sort_key_and_attaches_exactly_the_client_keys():
    """The request the client builds carries steam_id, sig and (for another
    binder) subject, and nothing else; the sort is client-side. The route's
    own query surface is pinned so a server-side sort parameter cannot appear
    without this contract being revisited. And the attach writes exactly the
    three per-print keys the client reads, spelt the client's way, and the
    route's flag under the client's top-level name."""
    import inspect
    params = set(inspect.signature(main.pc_collection).parameters)
    assert params == {"request", "steam_id", "sig", "subject", "db"}, params
    att = inspect.getsource(main._pc_attach_subject_standings)
    written = re.findall(r'p\["(subject_[a-z_]+)"\]\s*=', att)
    assert sorted(written) == sorted(PRINT_KEYS), written
    coll = inspect.getsource(main.pc_collection)
    assert coll.count('"%s": standings' % TOP_KEY) == 1


def test_the_attach_emits_only_well_formed_values(monkeypatch):
    """The four shapes a subject can be in -- on the board, rated but off it,
    unrated, and not in the standings at all (a deleted or vanished subject)
    -- each come out in a form the client reads correctly."""
    standings = {
        "on": {"board_rank": 7, "rating": 1834.5, "inactive": False},
        "off": {"board_rank": None, "rating": 1500.0, "inactive": True},
        "unrated": {"board_rank": None, "rating": None, "inactive": False},
    }

    async def fake(db, ids):
        return {k: v for k, v in standings.items() if k in ids}
    monkeypatch.setattr(main, "_pc_subject_standings", fake)
    prints = [{"subject_player_id": s, "rarity": "rare"} for s in ("on", "off", "unrated", "gone")]
    import asyncio
    flag = asyncio.run(main._pc_attach_subject_standings(None, prints))
    assert flag is True
    wire = json.loads(json.dumps({TOP_KEY: flag, "prints": prints}))
    assert pc_bool(_raw(wire, TOP_KEY)) is True
    for p in wire["prints"]:
        assert malformed(p) == [], (p, malformed(p))
    got = {p["subject_player_id"]: client_reads(p) for p in wire["prints"]}
    assert got == {"on": (7, 1834.5, True, False),
                   "off": (0, 1500.0, True, True),
                   "unrated": (0, 0.0, False, False),
                   "gone": (0, 0.0, False, False)}, got


def test_a_failed_read_is_read_by_the_client_as_no_sort(monkeypatch):
    """The refusal path: the flag goes out as JSON `false`, which PcBool reads
    as "do not offer the sort", and no print carries a half set of keys."""
    async def boom(db, ids):
        raise RuntimeError("board unavailable")
    monkeypatch.setattr(main, "_pc_subject_standings", boom)
    prints = [{"subject_player_id": "on", "rarity": "rare"}]
    import asyncio
    flag = asyncio.run(main._pc_attach_subject_standings(None, prints))
    wire = json.loads(json.dumps({TOP_KEY: flag, "prints": prints}))
    assert _raw(wire, TOP_KEY) == "false" and pc_bool(_raw(wire, TOP_KEY)) is False
    assert malformed(wire["prints"][0]) == []
    assert not any(k in wire["prints"][0] for k in PRINT_KEYS)


def test_the_client_source_reads_exactly_these_keys():
    """When the lane's ApiClient.cs is named, its readers must be the ones
    this file ports, under the same spellings, and its collection requests
    must carry no sort parameter."""
    path = os.environ.get(CLIENT_SRC_VAR)
    if not path:
        pytest.skip("%s unset; the client-source half of the contract" % CLIENT_SRC_VAR)
    src = open(path, encoding="utf-8").read()
    for line in ('PcInt(PcTopLevel(obj, "subject_board_rank"))',
                 'PcFloat(PcTopLevel(obj, "subject_rating"))',
                 'PcHas(obj, "subject_rating")',
                 'PcBool(PcTopLevel(obj, "subject_inactive"))',
                 'PcBool(PcTopLevel(json, "subject_standings"))'):
        assert src.count(line) == 1, line
    assert 'internal static bool PcBool(string raw) => raw == "true";' in src
    reqs = re.findall(r'PcUrl\("collection",[^\n]*', src)
    assert len(reqs) == 2, reqs
    for r in reqs:
        assert "sort" not in r.lower(), r


# -- the live half: the real route, its real JSON, the client's readers --------

@pytest.fixture(scope="module")
def lane():
    dp.require_live_pg()
    return dp.shared_lane()


def test_the_collection_route_answers_the_shape_the_client_reads(lane, monkeypatch):
    """One owner holding prints of three subjects: one on the board (rated,
    active, six completed series), one rated but below the match minimum, and
    one with no rating row. The route's answer, serialised, is read through the
    client port. Control: the same route with the standings read broken, which
    must answer the flag false and carry no per-print keys."""
    sessions = dp.Sessions()
    dp.open_routes(monkeypatch, sessions, SECRET)
    main._PC_BOARD_RANKS_CACHE.clear()

    async def seed():
        async with lane.sm() as db:
            ids = {}
            for tag in ("owner", "ranked", "short", "unrated"):
                steam = dp.steam_id()
                pl = await main.get_or_create_player(db, steam, "Contract " + tag)
                ids[tag] = (steam, str(pl.id))
            await db.execute(text("UPDATE players SET last_seen = now(), pc_collection_public = true "
                                  "WHERE id = ANY(CAST(:ids AS uuid[]))"),
                             {"ids": [v[1] for v in ids.values()]})
            await db.execute(text("DELETE FROM glicko_ratings WHERE player_id = CAST(:p AS uuid)"),
                             {"p": ids["unrated"][1]})
            for tag, rating in (("ranked", 2400.0), ("short", 2300.0)):
                await db.execute(text("""
                    INSERT INTO glicko_ratings (player_id, rating, rating_deviation, volatility,
                                                games_in_period, last_calculated, updated_at)
                    VALUES (CAST(:p AS uuid), :r, 60.0, 0.06, 0, NOW(), NOW())
                    ON CONFLICT (player_id) DO UPDATE SET rating = EXCLUDED.rating
                """), {"p": ids[tag][1], "r": rating})
            for tag, n in (("ranked", 6), ("short", 2)):
                await db.execute(text("""
                    INSERT INTO ranked_series (id, player1_id, player2_id, winner_id, status,
                                               p1_series_wins, p2_series_wins, created_at, completed_at,
                                               live_p1_points, live_p2_points, is_tournament, is_private)
                    VALUES (gen_random_uuid(), CAST(:a AS uuid), CAST(:b AS uuid), CAST(:a AS uuid),
                            'completed', 2, 1, NOW(), NOW(), 0, 0, false, false)
                """), [{"a": ids[tag][1], "b": ids["owner"][1]} for _ in range(n)])
            await db.commit()
        return ids

    ids = lane.run(seed())
    owner_steam, owner_pid = ids["owner"]
    sessions.live.add(owner_steam)

    async def make_print(subject_pid):
        async with lane.sm() as db:
            edition = (await db.execute(text("SELECT min(id) FROM pc_editions"))).scalar_one()
            if edition is None:
                edition = (await db.execute(text(
                    "INSERT INTO pc_editions (name) VALUES ('Edition 1') RETURNING id"))).scalar_one()
            card = (await db.execute(text(
                "INSERT INTO pc_cards (subject_player_id, edition_id) "
                "VALUES (CAST(:s AS uuid), CAST(:e AS integer)) "
                "ON CONFLICT (subject_player_id, edition_id, variant) DO UPDATE SET variant = EXCLUDED.variant "
                "RETURNING id"), {"s": subject_pid, "e": edition})).scalar_one()
            await db.execute(text(
                "INSERT INTO pc_prints (card_id, owner_player_id, snapshot_id, rarity, pool_rank, rating, "
                "board_rank, series_wins, series_losses, source) VALUES (CAST(:c AS uuid), CAST(:o AS uuid), "
                "1, 'rare', 3, 1500, 3, 10, 4, 'bought')"), {"c": str(card), "o": owner_pid})
            await db.commit()

    for tag in ("ranked", "short", "unrated"):
        lane.run(make_print(ids[tag][1]))

    async def collection():
        sig = dp.sign(SECRET, main._pc.canon_read(owner_steam, "collection", "-"))
        async with lane.sm() as db:
            return await main.pc_collection(dp.Req(path="/api/v1/pc/collection"), steam_id=owner_steam,
                                            sig=sig, subject=None, db=db)

    try:
        answer = lane.run(collection())
        wire = json.loads(json.dumps(answer, default=str))
        assert _raw(wire, TOP_KEY) == "true"
        by_subject = {p["subject_player_id"]: p for p in wire["prints"]}
        assert set(by_subject) == {ids[t][1] for t in ("ranked", "short", "unrated")}
        for p in wire["prints"]:
            assert malformed(p) == [], (p, malformed(p))
            assert all(k in p for k in PRINT_KEYS), p
        rank, rating, rated, inactive = client_reads(by_subject[ids["ranked"][1]])
        assert rank >= 1 and rating == 2400.0 and rated and not inactive
        assert client_reads(by_subject[ids["short"][1]]) == (0, 2300.0, True, False)
        assert client_reads(by_subject[ids["unrated"][1]]) == (0, 0.0, False, False)
        # the frozen mint-time numbers are untouched beside the live ones
        assert by_subject[ids["ranked"][1]]["board_rank"] == 3

        # control: the same route with the standings read broken
        async def boom(db, sids):
            raise RuntimeError("board unavailable")
        monkeypatch.setattr(main, "_pc_subject_standings", boom)
        wire2 = json.loads(json.dumps(lane.run(collection()), default=str))
        assert _raw(wire2, TOP_KEY) == "false"
        assert len(wire2["prints"]) == 3
        for p in wire2["prints"]:
            assert not any(k in p for k in PRINT_KEYS), p
    finally:
        main._PC_BOARD_RANKS_CACHE.clear()
