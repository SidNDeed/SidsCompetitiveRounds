"""Card draw evidence against a real PostgreSQL 16: migration 370 applied
twice; the route (session first, switch, envelope, signature, record, both
accounts, first record kept, one conflict marker, the hourly cap) accepting
the client's committed fixtures byte for byte; the census registration; the
card pass with no revision (attach and purge only, no derived row) and under
SYNTHETIC revisions (hand and phase rows, contributions replaced per game and
revision, daily sums unchanged by a second pass, a late second record
reclassifying one seat to paired, an unregistered census read as not run
until it is registered, shadow findings and posting only for an armed rule);
the purge; the admin read.

One case schema per module run, on one event loop; each case uses its own
stable keys and accounts. Every rule value is synthetic (card_revision_kit).
Live cases FAIL rather than skip unless CARD_EVIDENCE_TEST_PG_OPTOUT=1."""

import asyncio
import copy
import json
import os
import random
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import card_evidence as ce  # noqa: E402
import card_evidence_pg as cp  # noqa: E402
import card_measures as cm  # noqa: E402
import card_revision_kit as k  # noqa: E402
import main  # noqa: E402
import test_title_ladder_hooks_live as lh  # noqa: E402


@pytest.fixture(scope="module")
def live():
    cp.require_live_pg()
    loop = asyncio.new_event_loop()
    cmgr = cp.case("card")
    c, sm, snaps = loop.run_until_complete(cmgr.__aenter__())
    try:
        yield types.SimpleNamespace(run=loop.run_until_complete, case=c, sm=sm, snaps=snaps)
    finally:
        loop.run_until_complete(cmgr.__aexit__(None, None, None))
        loop.close()


@pytest.fixture(scope="module")
def revs(tmp_path_factory):
    """Synthetic card revisions in one store: everything in shadow; the same
    rules armed from one day ago; and a second shadow revision (another
    nonce) for re-evaluation under a new revision."""
    tmp = tmp_path_factory.mktemp("card-review")
    store, shadow = k.build_card_revision(tmp, name="shadow")
    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _s, armed = k.build_card_revision(tmp, k.card_doc(post=True, post_since=since), name="armed")
    _s, again = k.build_card_revision(tmp, name="again")
    # fix pass 1: a flag rule on the conflict marker (M7) and on the report
    # surplus (M8); the dup rule's synthetic value moved past any count, and
    # the dup rule dropped (M5: their quiet cases fire nothing)
    quiet = [k.card_case([("a", "b", k.fixture_record("full_game"))], [])]
    _s, conflict = k.build_card_revision(tmp, k.card_doc(conflict=True), name="conflict")
    _s, picks = k.build_card_revision(tmp, k.card_doc(picks=True), name="picks")
    _s, moved = k.build_card_revision(tmp, k.card_doc(dup_at=7.37), cases=quiet, name="moved")
    _s, dropped = k.build_card_revision(tmp, k.card_doc(drop=(k.ID_DUP,)), cases=quiet, name="dropped")
    # fix pass 2 (M3): a revision with no window, and one whose weight family
    # names only another deal profile (synthetic id)
    _s, nowindow = k.build_card_revision(tmp, k.card_doc(window=False, drop=(k.ID_WIN,)), name="nowindow")
    _s, noprofile = k.build_card_revision(tmp, k.card_doc(weights={"ab" * 32: dict(k.WEIGHTS)}),
                                          name="noprofile")
    # fix pass 3 (M2): every revision shape the loader accepts
    shapes = k.build_shapes(tmp)
    return types.SimpleNamespace(shadow=k.load(store, shadow), armed=k.load(store, armed),
                                 again=k.load(store, again), conflict=k.load(store, conflict),
                                 picks=k.load(store, picks), moved=k.load(store, moved),
                                 dropped=k.load(store, dropped), nowindow=k.load(store, nowindow),
                                 noprofile=k.load(store, noprofile), shapes=shapes)


@pytest.fixture
def signing(monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", k.KEY)


class Req:
    def __init__(self, body, token=None, version="1.41.0"):
        self._b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = {"X-Mod-Version": version}
        if token:
            self.headers["X-Session-Token"] = token
        self.client = None
        self.url = "http://card-evidence.test/"
        self.state = types.SimpleNamespace()

    async def body(self):
        return self._b


async def _players(sm, *steams):
    ids = {}
    async with sm() as db:
        for s in steams:
            ids[s] = (await main.get_or_create_player(db, s, "Card " + s[-3:])).id
        await db.commit()
    return ids


async def _session(sm, steam):
    token = "card-" + uuid.uuid4().hex
    async with sm() as db:
        await db.execute(text(
            "INSERT INTO steam_sessions (steam_id, token_hash, verified, issued_at, expires_at) "
            "VALUES (:s, encode(sha256(convert_to(:t, 'UTF8')), 'hex'), true, now(), "
            "        now() + interval '1 hour')"), {"s": steam, "t": token})
        await db.commit()
    return token


async def _post(sm, body, token):
    async with sm() as db:
        r = await main.submit_card_evidence(Req(body, token), db)
    if isinstance(r, dict):
        return 200, r
    return r.status_code, json.loads(r.body)


async def _scalar(sm, sql, **p):
    async with sm() as db:
        return (await db.execute(text(sql), p)).scalar()


async def _rows(sm, sql, **p):
    async with sm() as db:
        return (await db.execute(text(sql), p)).mappings().all()


async def _exec(sm, sql, **p):
    async with sm() as db:
        await db.execute(text(sql), p)
        await db.commit()


async def _set(sm, key, value):
    await _exec(sm, "INSERT INTO runtime_settings (key, value) VALUES (:k, :v) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", k=key, v=value)


async def _match(sm, ids, a, b, room, *, minutes_ago=10, sc=None):
    async with sm() as db:
        series = None
        if sc is not None:
            series = (await lh._insert(db, "ranked_series", {"player1_id": ids[a], "player2_id": ids[b]}))["id"]
            await db.execute(text("UPDATE ranked_series SET rules = CAST(:r AS jsonb) WHERE id = :i"),
                             {"r": json.dumps({"ff": True, "sc": sc == "on"}), "i": series})
        vals = {"player1_id": ids[a], "player2_id": ids[b], "photon_room_id": room, "is_ranked": True,
                "p1_rounds_won": 5, "p2_rounds_won": 3, "winner_id": ids[a], "reported_by": ids[a]}
        if series is not None:
            vals["series_id"] = series
        row = await lh._insert(db, "matches", vals)
        await db.execute(text(
            "UPDATE matches SET ended_at = now() - make_interval(mins => CAST(:m AS int)), "
            "  created_at = now() - make_interval(mins => CAST(:m AS int)) WHERE id = :i"),
            {"m": minutes_ago, "i": row["id"]})
        await db.commit()
    return row["id"]


async def _store(sm, ids, seat, other, stable, rec, rounds=5):
    env = ce.parse_envelope(k.envelope(rec, seat=seat, other=other, stable=stable, rounds=rounds))
    parsed = ce.parse_record(env)
    async with sm() as db:
        return await ce.store_record(db, env, parsed, ids[seat], ids[other], "1.41.0")


async def _register(sm, census_dump):
    async with sm() as db:
        return await ce.register_census(db, census_dump)


def _errors(stats):
    return {kk for kk in stats if kk.startswith("error")} | ({"rule_errors"} if stats.get("rule_errors") else set())


DERIVED = ("card_hand_outside", "card_phase_outside", "card_contrib", "card_player_daily")


async def _derived(sm, key=None):
    out = {}
    for t in DERIVED:
        if key is None or t == "card_player_daily":
            out[t] = await _scalar(sm, "SELECT count(*) FROM %s" % t)
        else:
            out[t] = await _scalar(sm, "SELECT count(*) FROM %s WHERE stable_game_key = :k" % t, k=key)
    return out


def _findings(where):
    return ("SELECT scope, dedup_key, rule_id, rules_rev, details, flag_id FROM seat_evidence_findings "
            "WHERE " + where + " ORDER BY dedup_key, rule_id")


GAME = "SELECT match_id, series_sc, finalized_at, evaluated_rev, derive_fault FROM card_games WHERE stable_game_key = :k"


# -- the migration --------------------------------------------------------------------

def test_migration_370_applies_twice_with_an_identical_result(live):
    first, again = live.snaps
    assert first == again
    assert {r[0]: r[1] for r in first["runtime_settings"]} == {kk: "1" for kk in ce.SWITCHES}
    assert [r[0] for r in first["card_evidence_seeded_keys"]] == sorted(ce.SWITCHES)
    assert all(first[t] == [] for t in cp.CARD_TABLES if t != "card_evidence_seeded_keys")
    names = {r[0] for r in first["constraints"]}
    assert {"card_evidence_one_per_seat", "card_contrib_pk", "card_player_daily_pk"} <= names
    cols = {r[0]: r for r in first["findings_columns"]}
    assert cols["domain"][2] == "'seat'::character varying" and cols["domain"][3] == "NO"
    assert {"seat_evidence_findings_domain", "seat_evidence_findings_once"} <= {
        r[0] for r in first["findings_constraints"]}
    assert "ux_seat_evidence_findings_domain" in {r[0] for r in first["findings_indexes"]}


# -- the route ------------------------------------------------------------------------

def test_the_route_accepts_the_client_fixtures_byte_for_byte(live, monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", k.FIXTURE_KEY)

    async def go():
        sm = live.sm
        await _players(sm, k.FIX_SEAT, k.FIX_OTHER)
        tok = await _session(sm, k.FIX_SEAT)
        out = []
        for name in k.cases():
            body = k.fixture(name, "envelope.json")                    # the committed bytes
            out.append(await _post(sm, body, tok))
            await _exec(sm, "DELETE FROM card_evidence WHERE stable_game_key = :k",
                        k=json.loads(body)["stable_game_key"])
        return out
    out = live.run(go())
    assert out == [(200, {"status": "recorded"})] * len(k.cases()), out


def test_the_session_is_first_then_the_switch_then_the_envelope_and_signature(live, signing):
    async def go():
        sm = live.sm
        a, b, c = "1000000000000711", "1000000000000712", "1000000000000713"
        await _players(sm, a, b)
        rec = k.fixture_record("full_game")
        body = k.envelope(rec, seat=a, other=b, stable="ranked_cardr1_000001")
        out = [await _post(sm, body, None)]
        out.append(await _post(sm, body, await _session(sm, b)))         # another seat's session
        tok = await _session(sm, a)
        await _set(sm, "card_evidence_accept", "0")
        try:
            out.append(await _post(sm, body, tok))
        finally:
            await _set(sm, "card_evidence_accept", "1")
        bad = dict(body, sig="0" * 64)
        out.append(await _post(sm, bad, tok))
        cut = copy.deepcopy(rec)
        del cut["hd"]                                                    # a record missing a key
        out.append(await _post(sm, k.envelope(cut, seat=a, other=b, stable="ranked_cardr1_000001"), tok))
        out.append(await _post(sm, k.envelope(rec, seat=a, other=c, stable="ranked_cardr1_000002"), tok))
        rows = await _scalar(sm, "SELECT count(*) FROM card_evidence WHERE stable_game_key LIKE 'ranked_cardr1%'")
        return out, rows
    out, rows = live.run(go())
    assert [o[0] for o in out] == [401, 401, 503, 403, 422, 409], out
    assert out[2][1] == {"error": "card_evidence_off"} and out[3][1] == {"detail": "signature"}
    assert out[5][1] == {"status": "not_ready"} and rows == 0


def test_the_first_record_is_kept_and_a_different_one_marks_once(live, signing):
    async def go():
        sm = live.sm
        a, b = "1000000000000721", "1000000000000722"
        await _players(sm, a, b)
        tok = await _session(sm, a)
        key = "ranked_cardr2_000001"
        rec = k.fixture_record("full_game")
        other = k.dup_record()
        first = k.envelope(rec, seat=a, other=b, stable=key)
        out = [await _post(sm, first, tok), await _post(sm, first, tok),
               await _post(sm, k.envelope(other, seat=a, other=b, stable=key), tok)]
        m1 = await _rows(sm, "SELECT conflict_at, conflict_kind FROM card_evidence WHERE stable_game_key = :k", k=key)
        await asyncio.sleep(0.05)
        out.append(await _post(sm, k.envelope(rec, seat=a, other=b, stable=key, rounds=6), tok))
        m2 = await _rows(sm, "SELECT conflict_at, conflict_kind, payload_sha256, deal_profile, pool_state "
                             "FROM card_evidence WHERE stable_game_key = :k", k=key)
        return out, m1, m2, rec
    out, m1, m2, rec = live.run(go())
    assert [o[0] for o in out] == [200, 200, 409, 409], out
    assert out[0][1] == {"status": "recorded"} and out[1][1] == {"status": "already_recorded"}
    assert out[2][1] == {"status": "conflict"}
    assert len(m2) == 1 and m2[0]["conflict_kind"] == "payload" and m2[0]["conflict_at"] == m1[0]["conflict_at"]
    assert m2[0]["deal_profile"] == cm.deal_profile(rec) and m2[0]["pool_state"] == "ok"


def test_the_hourly_cap_refuses_past_the_cap(live, signing, monkeypatch):
    monkeypatch.setitem(cm.CARD_WIRE, "hourly_cap", 2)

    async def go():
        sm = live.sm
        a, b = "1000000000000731", "1000000000000732"
        await _players(sm, a, b)
        tok = await _session(sm, a)
        rec = k.fixture_record("full_game")
        return [await _post(sm, k.envelope(rec, seat=a, other=b, stable="ranked_cardr3_00000%d" % i), tok)
                for i in range(3)]
    out = live.run(go())
    assert [o[0] for o in out] == [200, 200, 429], out


# -- the census registration ---------------------------------------------------------

def test_the_census_route_registers_a_whole_dump_and_refuses_a_mismatch(live, monkeypatch):
    async def no_admin_check(*_a, **_k):
        return None
    monkeypatch.setattr(main, "_require_admin", no_admin_check)
    dump = k.census_dump(k.census_cards(7))

    async def call(body, digest):
        async with live.sm() as db:
            r = await main.admin_register_card_census(Req(body), "1", "sig", digest, db)
        return (200, r) if isinstance(r, dict) else (r.status_code, json.loads(r.body))

    async def go():
        out = [await call(dump, dump["digest"]), await call(dump, dump["digest"]),
               await call(dump, "0" * 64)]
        bad = dict(dump, card_count=6)
        out.append(await call(bad, bad["digest"]))
        n = await _scalar(live.sm, "SELECT count(*) FROM card_pool_registry WHERE digest = :d", d=dump["digest"])
        return out, n
    out, n = live.run(go())
    assert out[0] == (200, {"status": "registered", "digest": dump["digest"], "card_count": 7, "slot_count": 5})
    assert out[1][1]["status"] == "already_registered"
    assert out[2] == (422, {"detail": "digest"}) and out[3] == (422, {"detail": "card_count"})
    assert n == 1


# -- the card pass ------------------------------------------------------------------

def _pair(census_dump=None, sc_rule=None):
    c = cm.census_from_dump(census_dump) if census_dump else k.fixture_census("full_game")
    rec = k.on_census(k.fixture_record("full_game"), c)
    if sc_rule is not None:
        rec["sc"] = [sc_rule, 0]
    return rec, k.mirror(rec), c


def test_m9_with_no_revision_the_pass_attaches_and_derives_nothing(live):
    async def go():
        sm = live.sm
        a, b = "1000000000000741", "1000000000000742"
        ids = await _players(sm, a, b)
        key = "ranked_cardm9_000001"
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, k.dup_record())
        await _store(sm, ids, b, a, key, rb)
        mid = await _match(sm, ids, a, b, key + "_r5")
        before = await _scalar(sm, "SELECT count(*) FROM seat_evidence_findings WHERE domain = 'card'")
        s = await ce.games_pass(sm, None)
        g = await _rows(sm, GAME, k=key)
        d = await _derived(sm, key)
        after = await _scalar(sm, "SELECT count(*) FROM seat_evidence_findings WHERE domain = 'card'")
        return s, g, d, mid, before, after
    s, g, d, mid, before, after = live.run(go())
    assert not _errors(s) and s["evaluated"] == 0 and "fault" not in s
    assert set(s) <= {"evaluated", "fired", "rule_errors", "attached", "waiting", "parked"}, s
    assert s["parked"] == 0
    assert g[0]["match_id"] == mid and g[0]["evaluated_rev"] is None and g[0]["finalized_at"] is None
    assert g[0]["derive_fault"] is None
    assert d == {"card_hand_outside": 0, "card_phase_outside": 0, "card_contrib": 0, "card_player_daily": 0}
    assert before == after


def test_a_revision_derives_rows_writes_shadow_findings_and_a_second_pass_changes_nothing(live, revs):
    async def go():
        sm = live.sm
        a, b = "1000000000000751", "1000000000000752"
        ids = await _players(sm, a, b)
        key = "ranked_cardd1_000001"
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        dup = k.on_census(k.dup_record(), c)
        await _store(sm, ids, a, b, key, dup)
        await _store(sm, ids, b, a, key, rb)
        mid = await _match(sm, ids, a, b, key + "_r5", sc="off")
        s1 = await ce.games_pass(sm, revs.shadow)
        g1 = await _rows(sm, GAME, k=key)
        hand = await _rows(sm, "SELECT measures, dealer_player_id, phase FROM card_hand_outside WHERE stable_game_key = :k", k=key)
        contrib = await _rows(sm, "SELECT source, coverage, hands, slots, rules_rev FROM card_contrib "
                                  "WHERE stable_game_key = :k ORDER BY source, subject_player_id", k=key)
        daily1 = await _rows(sm, "SELECT * FROM card_player_daily WHERE subject_player_id IN (:a, :b) "
                                 "ORDER BY subject_player_id, source", a=ids[a], b=ids[b])
        f1 = await _rows(sm, _findings("domain = 'card' AND (dedup_key LIKE :k OR dedup_key LIKE :w)"),
                         k=ce.game_key(key, "%", "%"), w=ce.window_key(ids[a], "%", "%", "%", "%"))
        s2 = await ce.games_pass(sm, revs.shadow)
        daily2 = await _rows(sm, "SELECT * FROM card_player_daily WHERE subject_player_id IN (:a, :b) "
                                 "ORDER BY subject_player_id, source", a=ids[a], b=ids[b])
        await _exec(sm, "UPDATE card_games SET signature = 'stale', finalized_at = NULL "
                        "WHERE stable_game_key = :k", k=key)
        s3 = await ce.games_pass(sm, revs.shadow)                     # re-derived, same inputs
        daily3 = await _rows(sm, "SELECT * FROM card_player_daily WHERE subject_player_id IN (:a, :b) "
                                 "ORDER BY subject_player_id, source", a=ids[a], b=ids[b])
        flags = await _scalar(sm, "SELECT count(*) FROM flagged_matches WHERE match_id = :m", m=mid)
        return s1, s2, s3, g1, hand, contrib, daily1, daily2, daily3, f1, flags, mid, ids
    s1, s2, s3, g1, hand, contrib, daily1, daily2, daily3, f1, flags, mid, ids = live.run(go())
    # other cases' games share the schema: the counts are of this pass, the rows of this game
    assert not _errors(s1) and s1["evaluated"] >= 1 and s2["evaluated"] == 0 and s3["evaluated"] == 1
    assert not _errors(s2) and not _errors(s3)
    assert g1[0]["evaluated_rev"] == revs.shadow.ruleset.rev and g1[0]["finalized_at"] is not None
    assert g1[0]["series_sc"] == "off" and g1[0]["derive_fault"] is None
    measures = [json.loads(h["measures"]) if isinstance(h["measures"], str) else h["measures"] for h in hand]
    assert any(m.get("b4.hand.dup") == 1 for m in measures)
    assert {(x["source"], x["coverage"]) for x in contrib} == {("self", "paired"), ("meas", "paired")}
    assert all(x["rules_rev"] == revs.shadow.ruleset.rev for x in contrib)
    strip = lambda rows: [{kk: v for kk, v in r.items() if kk != "updated_at"} for r in rows]  # noqa: E731
    assert daily1 and strip(daily1) == strip(daily2) == strip(daily3)      # no double count
    rules = sorted((f["scope"], f["rule_id"]) for f in f1)
    assert ("game", k.ID_DUP) in rules and ("sitting", k.ID_WIN) in rules
    assert all(f["flag_id"] is None and f["rules_rev"] == revs.shadow.ruleset.rev for f in f1)
    assert flags == 0                                                       # shadow posts nothing


def test_a_late_second_record_reclassifies_one_to_paired(live, revs):
    async def go():
        sm = live.sm
        a, b = "1000000000000761", "1000000000000762"
        ids = await _players(sm, a, b)
        key = "ranked_cardl1_000001"
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, ra)
        await _match(sm, ids, a, b, key + "_r5", sc="off")
        await ce.games_pass(sm, revs.shadow)
        one = await _rows(sm, "SELECT DISTINCT coverage FROM card_contrib WHERE stable_game_key = :k", k=key)
        d_one = await _scalar(sm, "SELECT count(*) FROM card_player_daily WHERE subject_player_id = :a "
                                  "AND coverage = 'one'", a=ids[a])
        win = _findings("domain = 'card' AND scope = 'sitting' AND dedup_key LIKE :w")
        w_one = await _rows(sm, win, w=ce.window_key(ids[a], "%", "one", "%", "%"))
        await _store(sm, ids, b, a, key, rb)
        await ce.games_pass(sm, revs.shadow)
        two = await _rows(sm, "SELECT DISTINCT coverage FROM card_contrib WHERE stable_game_key = :k", k=key)
        d_after = await _scalar(sm, "SELECT count(*) FROM card_player_daily WHERE subject_player_id = :a "
                                    "AND coverage = 'one'", a=ids[a])
        w_one_after = await _rows(sm, win, w=ce.window_key(ids[a], "%", "one", "%", "%"))
        w_paired = await _rows(sm, win, w=ce.window_key(ids[a], "%", "paired", "%", "%"))
        g = await _rows(sm, GAME, k=key)
        return one, d_one, two, d_after, g, w_one, w_one_after, w_paired
    one, d_one, two, d_after, g, w_one, w_one_after, w_paired = live.run(go())
    assert [r["coverage"] for r in one] == ["one"] and d_one > 0
    assert [r["coverage"] for r in two] == ["paired"] and d_after == 0
    assert g[0]["finalized_at"] is not None
    # M3: the retired one-sided window was evaluated again and its shadow
    # finding removed; the paired window holds the finding now (control)
    assert [f["rule_id"] for f in w_one] and {f["rule_id"] for f in w_one} == {k.ID_WIN}
    assert w_one_after == [] and {f["rule_id"] for f in w_paired} == {k.ID_WIN}


def test_an_unregistered_census_reads_not_run_until_it_is_registered(live, revs):
    async def go():
        sm = live.sm
        a, b = "1000000000000771", "1000000000000772"
        ids = await _players(sm, a, b)
        key = "ranked_cardu1_000001"
        c = k.fixture_census("full_game", cats={6: ["X"]}, black={2: ["X"]})   # phase 3 held refusal
        rec = k.on_census(k.fixture_record("full_game"), c)
        await _store(sm, ids, a, b, key, rec)
        await _store(sm, ids, b, a, key, k.mirror(rec))
        await _match(sm, ids, a, b, key + "_r5")
        await ce.games_pass(sm, revs.shadow)
        f1 = await _rows(sm, _findings("domain = 'card' AND dedup_key LIKE :k"), k=ce.game_key(key, "%", "%"))
        await _register(sm, k.census_dump(c.cards))
        s = await ce.games_pass(sm, revs.shadow)
        f2 = await _rows(sm, _findings("domain = 'card' AND dedup_key LIKE :k"), k=ce.game_key(key, "%", "%"))
        return f1, s, f2
    f1, s, f2 = live.run(go())
    assert k.ID_HELD not in [f["rule_id"] for f in f1]
    assert s["evaluated"] >= 1 and k.ID_HELD in [f["rule_id"] for f in f2]


def test_a_new_revision_re_derives_under_its_own_id_and_an_armed_rule_posts(live, revs):
    async def go():
        sm = live.sm
        a, b = "1000000000000781", "1000000000000782"
        ids = await _players(sm, a, b)
        key = "ranked_carda1_000001"
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, k.on_census(k.dup_record(), c))
        await _store(sm, ids, b, a, key, rb)
        mid = await _match(sm, ids, a, b, key + "_r5", sc="off")
        await ce.games_pass(sm, revs.shadow)
        await ce.games_pass(sm, revs.again)
        revs_seen = await _rows(sm, "SELECT DISTINCT rules_rev FROM card_contrib WHERE stable_game_key = :k "
                                    "ORDER BY 1", k=key)
        await ce.games_pass(sm, revs.armed)
        flags = await _rows(sm, "SELECT flag_reason, auto_invalidated, flag_details FROM flagged_matches "
                                "WHERE match_id = :m", m=mid)
        g = await _rows(sm, GAME, k=key)
        return revs_seen, flags, g
    revs_seen, flags, g = live.run(go())
    # fix pass 2 (M3): re-derived under its own id, and nothing the earlier
    # revision derived from the game outlives that
    assert [r["rules_rev"] for r in revs_seen] == [revs.again.ruleset.rev]
    assert flags and all(f["flag_reason"] == "review" and f["auto_invalidated"] is False for f in flags)
    details = [f["flag_details"] if isinstance(f["flag_details"], dict) else json.loads(f["flag_details"])
               for f in flags]
    assert k.ID_DUP in {d["rule_id"] for d in details}
    assert g[0]["evaluated_rev"] == revs.armed.ruleset.rev


def test_the_worker_switch_idles_the_pass(live, revs):
    async def go():
        await _set(live.sm, "card_evidence_worker", "0")
        try:
            return await ce.games_pass(live.sm, revs.shadow)
        finally:
            await _set(live.sm, "card_evidence_worker", "1")
    assert live.run(go()) == {"off": 1}


def test_the_purge_drops_lists_unattached_records_and_old_derived_rows(live, revs):
    async def go():
        sm = live.sm
        a, b = "1000000000000791", "1000000000000792"
        ids = await _players(sm, a, b)
        key, lone = "ranked_cardp1_000001", "ranked_cardp1_000002"
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, ra)
        await _store(sm, ids, a, b, lone, ra)
        await _match(sm, ids, a, b, key + "_r5", sc="off")
        await ce.games_pass(sm, revs.shadow)
        await _exec(sm, "UPDATE card_evidence SET received_at = now() - interval '200 days' "
                        "WHERE stable_game_key IN (:k, :l)", k=key, l=lone)
        await _exec(sm, "UPDATE card_contrib SET utc_day = utc_day - 500 WHERE stable_game_key = :k", k=key)
        out = await ce.purge_pass(sm)
        rows = await _rows(sm, "SELECT stable_game_key, payload, lists_purged_at FROM card_evidence "
                               "WHERE stable_game_key IN (:k, :l)", k=key, l=lone)
        left = await _scalar(sm, "SELECT count(*) FROM card_contrib WHERE stable_game_key = :k", k=key)
        return out, rows, left
    out, rows, left = live.run(go())
    assert [r["stable_game_key"] for r in rows] == ["ranked_cardp1_000001"]   # the unattached one is gone
    payload = rows[0]["payload"] if isinstance(rows[0]["payload"], dict) else json.loads(rows[0]["payload"])
    assert rows[0]["lists_purged_at"] is not None and not set(ce.LIST_KEYS) & set(payload)
    assert out["unattached"] >= 1 and out["derived"] >= 1 and left == 0


def test_the_admin_read_shows_records_measures_rows_and_unregistered_days(live, revs):
    async def go():
        sm = live.sm
        a, b = "1000000000000801", "1000000000000802"
        ids = await _players(sm, a, b)
        key = "ranked_cardv1_000001"
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, k.on_census(k.dup_record(), c))
        await _store(sm, ids, b, a, key, rb)
        never = k.fixture_census("full_game", names={0: "NeverRegistered"})   # another digest
        await _store(sm, ids, a, b, "ranked_cardv1_000002", k.on_census(k.fixture_record("full_game"), never))
        mid = await _match(sm, ids, a, b, key + "_r5")
        await ce.games_pass(sm, revs.shadow)
        async with sm() as db:
            v = await ce.admin_view(db, match_id=str(mid), rs=revs.shadow.ruleset)
        return v
    v = live.run(go())
    assert v["review_rules"] == revs.shadow.ruleset.rev and len(v["games"]) == 1
    g = v["games"][0]
    assert len(g["records"]) == 2 and all(r["pool_registered"] for r in g["records"])
    assert g["measures"]["game"]["b4.game.paired"] == 1
    assert any(h["measures"].get("b4.hand.dup") == 1 for h in g["hand_rows"])
    assert any(f["rule_id"] == k.ID_DUP for f in g["findings"])
    assert v["unregistered_by_day"] and v["unregistered_by_day"][-1]["records"] >= 1
    assert g["measures"]["not_run_because"] and all(x["not_whole"] == [] for x in g["measures"]["not_run_because"])
    json.dumps(v)                                                     # serialisable as the route answers it


# == fix pass 1 ======================================================================

async def _game_findings(sm, key):
    return await _rows(sm, _findings("domain = 'card' AND scope = 'game' AND dedup_key LIKE :k"),
                       k=ce.game_key(key, "%", "%"))


def test_m5_a_finding_a_newer_revision_no_longer_produces_is_removed_whatever_stamped_it(live, revs):
    async def go():
        sm = live.sm
        a, b = "1000000000000811", "1000000000000812"
        ids = await _players(sm, a, b)
        key = "ranked_cardf5_000001"
        _ra, _rb, c = _pair()
        dup = k.on_census(k.dup_record(), c)
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, dup)
        await _store(sm, ids, b, a, key, k.mirror(dup))
        await _match(sm, ids, a, b, key + "_r5", sc="off")
        out = {}
        for name in ("shadow", "moved", "shadow", "dropped"):
            await ce.games_pass(sm, getattr(revs, name))
            out.setdefault(name, []).append(
                sorted((f["rule_id"], f["rules_rev"]) for f in await _game_findings(sm, key)))
        return out
    out = live.run(go())
    shadow, moved, dropped = revs.shadow.ruleset.rev, revs.moved.ruleset.rev, revs.dropped.ruleset.rev
    assert len({shadow, moved, dropped}) == 3
    for seen in out["shadow"]:
        assert (k.ID_DUP, shadow) in seen                                      # control: the rule fires
    for name, rev in (("moved", moved), ("dropped", dropped)):
        seen = out[name][0]
        # its deciding value moved / the rule removed: the row the earlier
        # revision stamped is gone, and nothing stamped by another revision stays
        assert k.ID_DUP not in {r for r, _v in seen} and all(v == rev for _r, v in seen), (name, seen)


def test_m6_card_cleanup_never_touches_a_seat_domain_row(live, revs):
    async def go():
        sm = live.sm
        a, b = "1000000000000821", "1000000000000822"
        ids = await _players(sm, a, b)
        key = "ranked_cardf6_000001"
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, ra)
        await _store(sm, ids, b, a, key, rb)
        await _match(sm, ids, a, b, key + "_r5", sc="off")
        lo, hi = sorted([str(ids[a]), str(ids[b])])
        seat_rows = [("game", "%s|%s|%s" % (key, lo, hi)),                 # the seat lane's key of this game
                     ("game", "card|%s|%s|%s" % (key, lo, hi)),            # the old card form, as a seat key
                     ("game", ce.game_key(key, lo, hi))]                   # the card key itself, seat domain
        for scope, dk in seat_rows:
            await _exec(sm, "INSERT INTO seat_evidence_findings (scope, dedup_key, rule_id, rules_rev) "
                            "VALUES (:s, :k, 'r0000fff1', 'seat')", s=scope, k=dk)
        await _exec(sm, "INSERT INTO seat_evidence_findings (domain, scope, dedup_key, rule_id, rules_rev) "
                        "VALUES ('card', 'game', :k, 'r0000fff2', 'old')", k=ce.game_key(key, lo, hi))
        await ce.games_pass(sm, revs.shadow)
        left = await _rows(sm, "SELECT domain, dedup_key, rule_id FROM seat_evidence_findings "
                               "WHERE rule_id IN ('r0000fff1', 'r0000fff2') AND dedup_key LIKE :p ORDER BY 2, 1",
                           p="%" + key + "%")
        return left, seat_rows
    left, seat_rows = live.run(go())
    assert sorted((r["domain"], r["dedup_key"]) for r in left) == sorted(("seat", dk) for _s, dk in seat_rows)
    # control: the card row the evaluation did not produce was removed in the same pass


def test_m7_a_conflict_first_recorded_after_the_game_was_final_wakes_it(live, revs):
    async def go():
        sm = live.sm
        a, b = "1000000000000831", "1000000000000832"
        ids = await _players(sm, a, b)
        key = "ranked_cardf7_000001"
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, ra)
        await _store(sm, ids, b, a, key, rb)
        await _match(sm, ids, a, b, key + "_r5", sc="off")
        await ce.games_pass(sm, revs.conflict)
        sel = "SELECT finalized_at, processed_at, signature FROM card_games WHERE stable_game_key = :k"
        g1 = (await _rows(sm, sel, k=key))[0]
        await ce.games_pass(sm, revs.conflict)                         # control: nothing new, not visited
        g2 = (await _rows(sm, sel, k=key))[0]
        f_before = await _game_findings(sm, key)
        try:
            await _store(sm, ids, a, b, key, k.on_census(k.dup_record(), c))
            status = 200
        except ce.EvidenceRefused as r:
            status = r.status
        await ce.games_pass(sm, revs.conflict)
        g3 = (await _rows(sm, sel, k=key))[0]
        f_after = await _game_findings(sm, key)
        return g1, g2, g3, status, f_before, f_after
    g1, g2, g3, status, f_before, f_after = live.run(go())
    assert g1["finalized_at"] is not None and g2["processed_at"] == g1["processed_at"]
    assert status == 409
    assert g3["processed_at"] > g1["processed_at"] and g3["signature"] != g1["signature"]
    assert k.ID_CONFLICT not in {f["rule_id"] for f in f_before}
    assert k.ID_CONFLICT in {f["rule_id"] for f in f_after}


async def _picks_rows(sm, mid, player, names):
    for i, name in enumerate(names):
        await _exec(sm, "INSERT INTO match_cards (id, match_id, player_id, card_name, pick_order, round_number) "
                        "VALUES (gen_random_uuid(), :m, :p, :n, :o, :o)", m=mid, p=player, n=name, o=i + 1)


def test_m8_the_report_projection_reads_match_cards_and_writes_no_match_data(live, revs):
    rec = k.default_record()
    names = {x[0]: x[1] for x in rec["cards"]}
    mine = [names[e[6][e[9]]] for e in rec["hd"] if e[2] == 0 and e[9] >= 0]
    theirs = [names[e[6][e[9]]] for e in rec["hd"] if e[2] == 1 and e[9] >= 0]

    async def game(tag, a, b, report_a):
        sm = live.sm
        ids = await _players(sm, a, b)
        key = "ranked_cardf8_%s" % tag
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, ra)
        await _store(sm, ids, b, a, key, rb)
        mid = await _match(sm, ids, a, b, key + "_r5", sc="off")
        await _picks_rows(sm, mid, ids[a], report_a)
        await _picks_rows(sm, mid, ids[b], theirs)
        snap = "SELECT player_id, card_name, pick_order, round_number FROM match_cards WHERE match_id = :m ORDER BY 1, 3"
        before = await _rows(sm, snap, m=mid)
        await ce.games_pass(sm, revs.picks)
        after = await _rows(sm, snap, m=mid)
        async with sm() as db:
            v = await ce.admin_view(db, match_id=str(mid), rs=revs.picks.ruleset)
        rows = {r["b4.rec.index"]: r for r in v["games"][0]["measures"]["records"]}
        return [dict(x) for x in before], [dict(x) for x in after], await _game_findings(sm, key), rows

    async def go():
        return (await game("000001", "1000000000000841", "1000000000000842", mine + ["NotInTheRecord"]),
                await game("000002", "1000000000000843", "1000000000000844", mine))
    (b1, a1, f1, rows1), (b2, a2, f2, rows2) = live.run(go())
    assert b1 == a1 and b2 == a2                                         # match data unchanged
    assert k.ID_PICKS in {f["rule_id"] for f in f1}                      # the report lists a pick the record lacks
    assert k.ID_PICKS not in {f["rule_id"] for f in f2}                  # control: the report agrees
    assert all(rows2[i]["b4.report.picks.self.rep"] == 0 for i in rows2)
    assert any(rows1[i]["b4.report.picks.self.rep"] == 1 for i in rows1)


def test_m7_a_conflict_whose_transaction_began_before_the_evaluation_still_wakes_the_game(live, revs):
    """The conflicting submission's transaction begins, an evaluation then runs
    and finalizes the game without seeing it, and only then is the conflict
    written and committed (the order a wait on the evaluation's FOR SHARE lock
    produces). Its marker must still be later than that evaluation."""
    async def go():
        sm = live.sm
        a, b = "1000000000000851", "1000000000000852"
        ids = await _players(sm, a, b)
        key = "ranked_cardf9_000001"
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, ra)
        await _store(sm, ids, b, a, key, rb)
        await _match(sm, ids, a, b, key + "_r5", sc="off")
        env = ce.parse_envelope(k.envelope(k.on_census(k.dup_record(), c), seat=a, other=b, stable=key, rounds=5))
        parsed = ce.parse_record(env)
        sel = "SELECT finalized_at, processed_at FROM card_games WHERE stable_game_key = :k"
        async with sm() as db:
            began = (await db.execute(text("SELECT now()"))).scalar()   # the conflict's transaction begins
            await ce.games_pass(sm, revs.conflict)                         # an evaluation that cannot see it
            g1 = (await _rows(sm, sel, k=key))[0]
            try:
                await ce.store_record(db, env, parsed, ids[a], ids[b], "1.41.0")
                status = 200
            except ce.EvidenceRefused as r:
                status = r.status
        marker = await _scalar(sm, "SELECT max(conflict_at) FROM card_evidence WHERE stable_game_key = :k", k=key)
        await ce.games_pass(sm, revs.conflict)
        g2 = (await _rows(sm, sel, k=key))[0]
        return began, g1, status, marker, g2, await _game_findings(sm, key)
    began, g1, status, marker, g2, found = live.run(go())
    assert status == 409 and g1["finalized_at"] is not None
    assert began < g1["processed_at"]                     # control: the conflict's transaction began first
    assert marker > g1["processed_at"]
    assert g2["processed_at"] > g1["processed_at"] and k.ID_CONFLICT in {f["rule_id"] for f in found}


def test_m6_each_purge_keeps_to_its_own_domain(live):
    """The seat purge removes only seat findings; the card purge removes only
    card findings (on the card lane's derived retention); neither removes a
    posted finding or a recent one."""
    age = ce.CARD_LIMITS["derived_retention_days"] + ce.se.FINDING_RETENTION_DAYS   # past both
    tag = "ranked_cardpd_000001|lo|hi"
    ins = ("INSERT INTO seat_evidence_findings (domain, scope, dedup_key, rule_id, rules_rev, flag_id, changed_at) "
           "VALUES (:dom, 'game', :k, :r, 'old', CAST(:f AS uuid), now() - make_interval(days => CAST(:age AS int)))")
    left = "SELECT rule_id FROM seat_evidence_findings WHERE dedup_key IN (:s, :c) ORDER BY rule_id"

    async def go():
        sm = live.sm
        seat_key, card_key = tag, "card " + tag
        for dom, kk, rid, flag, days in (("seat", seat_key, "r0000ff01", None, age),
                                         ("card", card_key, "r0000ff02", None, age),
                                         ("card", card_key, "r0000ff03", None, 0),
                                         ("card", card_key, "r0000ff04", str(uuid.uuid4()), age)):
            await _exec(sm, ins, dom=dom, k=kk, r=rid, f=flag, age=days)
        await ce.se.purge_pass(sm)
        after_seat = [r["rule_id"] for r in await _rows(sm, left, s=seat_key, c=card_key)]
        await _exec(sm, ins, dom="seat", k=seat_key, r="r0000ff05", f=None, age=age)
        await ce.purge_pass(sm)
        after_card = [r["rule_id"] for r in await _rows(sm, left, s=seat_key, c=card_key)]
        return after_seat, after_card
    after_seat, after_card = live.run(go())
    assert "r0000ff01" not in after_seat                  # control: the seat purge ran on its own row
    assert after_seat == ["r0000ff02", "r0000ff03", "r0000ff04"]
    assert "r0000ff02" not in after_card                  # control: the card purge ran on its own row
    assert after_card == ["r0000ff03", "r0000ff04", "r0000ff05"]


# == fix pass 2 ======================================================================
#
# The oracle: what a from-scratch evaluation under one revision holds for some
# games and some dealers. Windows are summed straight from card_contrib (never
# the daily rows the incremental path maintains), one per endpoint a game of
# the class was played on; game findings come from a fresh view of each game.
# The stored unposted card findings of those games and dealers must equal it
# wherever incremental maintenance is asserted.

_CONTRIB_SUMS = ("hands", "slots", "notrun_hands") + tuple(
    part + "_" + name for part in ("obs", "exp", "var") for name in cm.RARITIES)


def _details(v):
    return v if isinstance(v, dict) else json.loads(v)


def _dealer_prefix(dealer):
    return "card win %s|" % dealer


async def _stored(sm, games, dealers):
    rows = await _rows(sm, "SELECT scope, dedup_key, rule_id, details FROM seat_evidence_findings "
                           "WHERE domain = 'card' AND flag_id IS NULL")
    keys = {ce.game_key(kk, lo, hi) for kk, lo, hi in games}
    out = {}
    for r in rows:
        if ((r["scope"] == "game" and r["dedup_key"] in keys)
                or (r["scope"] == "sitting" and any(r["dedup_key"].startswith(_dealer_prefix(d))
                                                    for d in dealers))):
            out[(r["scope"], r["dedup_key"], r["rule_id"])] = _details(r["details"])
    return out


async def _from_scratch(sm, state, games, dealers):
    rs = state.ruleset
    want = {}

    def put(scope, key, rule, items):
        want.setdefault((scope, key, rule), []).extend(items)
    win = rs.params.get(cm.WINDOW)
    windows = []
    if win:
        w = int(win[cm.WINDOW_KEY])
        rows = await _rows(sm, "SELECT subject_player_id::text AS s, source, coverage, deal_profile AS p, "
                               "utc_day AS d, stable_game_key, pair_lo, pair_hi, " + ", ".join(_CONTRIB_SUMS)
                           + " FROM card_contrib WHERE rules_rev = :rev "
                             "AND subject_player_id::text = ANY(CAST(:ds AS text[]))",
                           rev=rs.rev, ds=[str(d) for d in dealers])
        classes = {}
        for r in rows:
            classes.setdefault((r["s"], r["source"], r["coverage"], r["p"]), []).append(r)
        for cls in sorted(classes):
            for e in sorted({r["d"] for r in classes[cls]}):
                inside = [r for r in classes[cls] if e - timedelta(days=w) < r["d"] <= e]
                agg = {"games": len({(r["stable_game_key"], r["pair_lo"], r["pair_hi"]) for r in inside}),
                       "source": cls[1], "coverage": cls[2]}
                for c in ("hands", "slots", "notrun_hands"):
                    agg[c] = sum(int(r[c]) for r in inside)
                for part in ("obs", "exp", "var"):
                    agg[part] = [sum(int(r[part + "_" + n]) for r in inside) for n in cm.RARITIES]
                windows.append(((cls, e), agg))
    found, _notes, _f, errors = rs.evaluate_card(cm.card_subjects({}, [cm.window_row(a) for _k, a in windows]))
    assert not errors
    for rule, items in found:
        for kk, item in items:
            (s, src, cov, p), e = windows[kk[1]][0]
            put("sitting", ce.window_key(s, src, cov, p, e), rule.id, [item])
    async with sm() as db:
        for key, lo, hi in games:
            rows = (await db.execute(text(
                "SELECT id, seat_player_id, other_player_id, attach_key, payload, pool_digest, conflict_at, "
                "       received_at FROM card_evidence WHERE stable_game_key = :k "
                "  AND LEAST(seat_player_id, other_player_id) = :lo "
                "  AND GREATEST(seat_player_id, other_player_id) = :hi ORDER BY id"),
                {"k": key, "lo": lo, "hi": hi})).mappings().all()
            match = (await db.execute(ce._MATCH, {"keys": sorted({r["attach_key"] for r in rows}),
                                                  "lo": lo, "hi": hi, "lag": ce.se.READY_LAG_S})).mappings().first()
            if match is None:
                continue
            named, _other = ce.se.attached_records(rows, match)
            records = ce._records(named)
            if not records or any(not ce._has_lists(r["rec"]) for r in records):
                continue
            registry = await ce._registry(db, {r["pool_digest"] for r in rows if r["pool_digest"]})
            report = await ce._report(db, match["id"])
            view = cm.card_view(records, registry, match["sc"], rs.params.get(cm.WEIGHTS), report)
            found, notes, _f, errors = rs.evaluate_card(cm.card_subjects(view, []))
            assert not errors
            for rule, items in found:
                its = [dict(it, notes=[ln for _r, ln in notes]) if notes else it for _k, it in items]
                put("game", ce.game_key(key, lo, hi), rule.id, its)
    return {kk: json.loads(ce.se._dumps(ce.se.bounded_details({"items": v}))) for kk, v in want.items()}


async def _pair_of(sm, key):
    r = (await _rows(sm, "SELECT LEAST(seat_player_id, other_player_id) AS lo, "
                         "GREATEST(seat_player_id, other_player_id) AS hi FROM card_evidence "
                         "WHERE stable_game_key = :k LIMIT 1", k=key))[0]
    return key, r["lo"], r["hi"]


_SEQ = iter(range(900, 1000))


def _steams():
    n = next(_SEQ)
    return "1000000000000%03d" % n, "1000000000001%03d" % n


async def _late_pairing(sm, revs, offset, tag):
    """G1 one-sided on day D, G2 one-sided on D + offset, both evaluated; then
    G1's second record, and another pass. Returns the dealers' and games'
    stored findings before and after the pairing, the oracle after it, and
    the key of the one-sided window ending on G2's day."""
    a, b = _steams()
    ids = await _players(sm, a, b)
    ra, rb, c = _pair()
    await _register(sm, k.census_dump(c.cards))
    g1, g2 = "ranked_cardw%s_000001" % tag, "ranked_cardw%s_000002" % tag
    await _store(sm, ids, a, b, g1, ra)
    m1 = await _match(sm, ids, a, b, g1 + "_r5", minutes_ago=10 + offset * 1440, sc="off")
    await _store(sm, ids, a, b, g2, ra)
    m2 = await _match(sm, ids, a, b, g2 + "_r5", minutes_ago=10, sc="off")
    await ce.games_pass(sm, revs.shadow)
    games = [await _pair_of(sm, g1), await _pair_of(sm, g2)]
    dealers = [ids[a], ids[b]]
    before = await _stored(sm, games, dealers)
    await _store(sm, ids, b, a, g1, rb)
    await ce.games_pass(sm, revs.shadow)
    after = await _stored(sm, games, dealers)
    want = await _from_scratch(sm, revs.shadow, games, dealers)
    day2 = await _scalar(sm, "SELECT (ended_at AT TIME ZONE 'UTC')::date FROM matches WHERE id = :m", m=m2)
    day1 = await _scalar(sm, "SELECT (ended_at AT TIME ZONE 'UTC')::date FROM matches WHERE id = :m", m=m1)
    one = {kk for kk in before if kk[0] == "sitting" and "|one|" in kk[1] and kk[1].endswith(str(day2))}
    return before, after, want, one, (day2 - day1).days


def test_m2_a_late_pairing_refreshes_every_window_its_day_lies_in(live, revs):
    """The two-day witness: G1 one-sided on D, G2 one-sided on D + 1, then
    G1's late pairing. The one-sided window ending on D + 1 summed G1 and
    must be evaluated again."""
    before, after, want, one, gap = live.run(_late_pairing(live.sm, revs, 1, "a"))
    assert gap == 1 and one                                     # control: the window ending on D + 1 existed
    assert after == want
    assert all(before[kk] != after.get(kk) for kk in one)       # control: and it changed


def test_m2_the_late_pairing_property_over_day_offsets_matches_a_from_scratch_evaluation(live, revs):
    """Generated: offsets within the window (1, a random one, w - 1) and just
    outside it (w, w + 1). Within, the later window changes; outside, it
    cannot; everywhere the stored findings equal the from-scratch oracle."""
    w = k.WINDOW["window_days"]
    seed = int.from_bytes(os.urandom(4), "big")
    rnd = random.Random(seed)
    offsets = [1, rnd.randint(2, w - 2), w - 1, w, w + 1]
    compared = changed = 0
    for i, off in enumerate(offsets):
        before, after, want, one, gap = live.run(_late_pairing(live.sm, revs, off, "p%d" % i))
        assert gap == off and one, (seed, off)
        assert after == want, (seed, off)
        moved = any(before[kk] != after.get(kk) for kk in one)
        assert moved == (off < w), (seed, off)
        compared += len(want)
        changed += moved
    print("m2 property: seed %d offsets %s windows-and-games compared %d later windows changed %d"
          % (seed, offsets, compared, changed))
    assert changed == 3


async def _two_revisions(sm, first, second, tag, purge=False):
    a, b = _steams()
    ids = await _players(sm, a, b)
    key = "ranked_cardr%s_000001" % tag
    _ra, _rb, c = _pair()
    dup = k.on_census(k.dup_record(), c)
    await _register(sm, k.census_dump(c.cards))
    await _store(sm, ids, a, b, key, dup)
    await _store(sm, ids, b, a, key, k.mirror(dup))
    await _match(sm, ids, a, b, key + "_r5", sc="off")
    await ce.games_pass(sm, first)
    games, dealers = [await _pair_of(sm, key)], [ids[a], ids[b]]
    before = await _stored(sm, games, dealers)
    if purge:
        await _exec(sm, "UPDATE card_evidence SET received_at = now() - interval '200 days' "
                        "WHERE stable_game_key = :k", k=key)
        await ce.purge_pass(sm)
        assert await _scalar(sm, "SELECT count(*) FROM card_evidence WHERE stable_game_key = :k "
                                 "AND lists_purged_at IS NULL", k=key) == 0
    await ce.games_pass(sm, second)
    after = await _stored(sm, games, dealers)
    want = await _from_scratch(sm, second, games, dealers)
    stamped = await _rows(sm, "SELECT DISTINCT rules_rev FROM seat_evidence_findings WHERE domain = 'card' "
                              "AND flag_id IS NULL AND (dedup_key = :g OR dedup_key LIKE :w1 OR dedup_key LIKE :w2)",
                          g=ce.game_key(*games[0]), w1=_dealer_prefix(ids[a]) + "%", w2=_dealer_prefix(ids[b]) + "%")
    contrib = await _rows(sm, "SELECT DISTINCT rules_rev FROM card_contrib WHERE stable_game_key = :k", k=key)
    sel = "SELECT processed_at, evaluated_rev FROM card_games WHERE stable_game_key = :k"
    g1 = (await _rows(sm, sel, k=key))[0]
    await ce.games_pass(sm, second)                       # visited once per revision, not again
    g2 = (await _rows(sm, sel, k=key))[0]
    return (before, after, want, {r["rules_rev"] for r in stamped}, {r["rules_rev"] for r in contrib},
            (g1["processed_at"], g1["evaluated_rev"], g2["processed_at"]))


@pytest.mark.parametrize("second,purge", [("nowindow", False), ("noprofile", False), ("again", True)],
                         ids=["no-window", "no-profile-family", "lists-purged"])
def test_m3_what_another_revision_wrote_is_retired_when_the_current_one_produces_nothing_there(
        live, revs, second, purge):
    """R1 writes window (and game) findings; R2 has no window, or no weight
    set for the game's exact profile, or the game's lists are purged before
    R2 visits it. Afterwards the stored unposted findings of the game and its
    dealers equal a fresh evaluation under R2, and none another revision
    stamped remains."""
    tag = {"nowindow": "nw", "noprofile": "np", "again": "pg"}[second]
    before, after, want, stamped, contrib, (p1, ev, p2) = live.run(
        _two_revisions(live.sm, revs.shadow, getattr(revs, second), tag, purge=purge))
    r1, r2 = revs.shadow.ruleset.rev, getattr(revs, second).ruleset.rev
    assert any(kk[0] == "sitting" for kk in before) and any(kk[0] == "game" for kk in before)  # control
    assert after == want
    assert stamped <= {r2} and r1 not in contrib
    assert ev == r2 and p2 == p1


def test_m3_the_oracle_differs_from_a_stale_store(live, revs):
    """Control on the oracle itself: before R2 visits, the store holds what
    R1 wrote, which the R2 oracle does not."""
    async def go():
        a, b = _steams()
        sm = live.sm
        ids = await _players(sm, a, b)
        key = "ranked_cardro_000001"
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, ra)
        await _store(sm, ids, b, a, key, rb)
        await _match(sm, ids, a, b, key + "_r5", sc="off")
        await ce.games_pass(sm, revs.shadow)
        games, dealers = [await _pair_of(sm, key)], [ids[a], ids[b]]
        return (await _stored(sm, games, dealers), await _from_scratch(sm, revs.shadow, games, dealers),
                await _from_scratch(sm, revs.nowindow, games, dealers))
    stored, same, other = live.run(go())
    assert stored == same and stored and stored != other


async def _wait_lock(sm, pattern):
    """Bounded: until a backend of this database waits on a lock in a
    statement matching `pattern` (True), or about ten seconds (False)."""
    for _ in range(200):
        n = await _scalar(sm, "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                              "AND wait_event_type = 'Lock' AND query LIKE :q", q=pattern)
        if n:
            return True
        await asyncio.sleep(0.05)
    return False


def test_m7_a_conflict_that_waits_on_the_evaluations_row_lock_is_later_than_it_and_wakes_the_game(live, revs):
    """Two real transactions on the record rows. The conflicting submission's
    transaction begins first and waits (its seat lock held by a third
    session); an evaluation then reads the game's records FOR SHARE and
    stamps the game processed; the submission, released, blocks on those
    rows until the evaluation commits, and only then takes the time of its
    marker. The marker is later than the evaluation, and the next pass wakes
    the game."""
    async def go():
        sm = live.sm
        a, b = _steams()
        ids = await _players(sm, a, b)
        key = "ranked_cardlw_000001"
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, ra)
        await _store(sm, ids, b, a, key, rb)
        await _match(sm, ids, a, b, key + "_r5", sc="off")
        await ce.games_pass(sm, revs.conflict)
        _k, lo, hi = await _pair_of(sm, key)
        env = ce.parse_envelope(k.envelope(k.on_census(k.dup_record(), c), seat=a, other=b, stable=key, rounds=5))
        parsed = ce.parse_record(env)

        async def submit():
            async with sm() as db:
                try:
                    await ce.store_record(db, env, parsed, ids[a], ids[b], "1.41.0")
                    return 200
                except ce.EvidenceRefused as r:
                    return r.status
        async with sm() as hold:
            await hold.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                               {"k": "card_evidence:" + str(ids[a])})
            task = asyncio.ensure_future(submit())
            seat_wait = await _wait_lock(sm, "%pg_advisory_xact_lock%")
            began = await _scalar(sm, "SELECT min(xact_start) FROM pg_stat_activity "
                                      "WHERE datname = current_database() AND wait_event_type = 'Lock'")
            async with sm() as ev:
                state = await ce.evaluate_card_game(ev, key, lo, hi, revs.conflict.ruleset)
                await hold.commit()
                row_wait = await _wait_lock(sm, "%FOR UPDATE%")
                await ev.commit()
            status = await asyncio.wait_for(task, 30)
        sel = "SELECT processed_at FROM card_games WHERE stable_game_key = :k"
        processed = await _scalar(sm, sel, k=key)
        marker = await _scalar(sm, "SELECT max(conflict_at) FROM card_evidence WHERE stable_game_key = :k", k=key)
        await ce.games_pass(sm, revs.conflict)
        return (seat_wait, row_wait, began, state, status, processed, marker,
                await _scalar(sm, sel, k=key), await _game_findings(sm, key))
    seat_wait, row_wait, began, state, status, processed, marker, woken, found = live.run(go())
    assert seat_wait and row_wait                         # control: both waits really happened
    assert state[0] == "unchanged" and began < processed  # control: the submission began first
    assert status == 409
    assert marker > processed
    assert woken > processed and k.ID_CONFLICT in {f["rule_id"] for f in found}


# == fix pass 3 ===========================================================================

# -- M2: every revision shape through the review pass (the worker cells of the table) ------

async def _fresh_game(sm, tag, dup=False):
    """A fresh paired game; with dup, one side's record carries the
    duplicate the card game rule fires on."""
    a, b = _steams()
    ids = await _players(sm, a, b)
    key = "ranked_cards%s_000001" % tag
    ra, rb, c = _pair()
    await _register(sm, k.census_dump(c.cards))
    await _store(sm, ids, a, b, key, k.dup_record() if dup else ra)
    await _store(sm, ids, b, a, key, rb)
    await _match(sm, ids, a, b, key + "_r5", sc="off")
    return key, [await _pair_of(sm, key)], [ids[a], ids[b]]


SHAPES = sorted(k.revision_shapes())


@pytest.mark.parametrize("shape", SHAPES)
def test_m2_every_revision_shape_runs_the_review_pass_derives_and_matches_the_oracle(live, revs, shape,
                                                                                   monkeypatch):
    """A fresh game through main.review_worker_pass (the seat pass, then the
    card pass, on one published state) under each revision shape: no visit
    raises, the game is derived, stamped with the revision and final, its
    stored findings equal the from-scratch oracle (empty for a shape with no
    card rules), and the admin read answers under the revision."""
    state = revs.shapes[shape]
    doc, _cases, has_card = k.revision_shapes()[shape]
    weighed = cm.WEIGHTS in doc["measure_params"]
    monkeypatch.setattr(main._review_rules, "refresh_rules", lambda: state)
    cards = {}
    orig = ce.games_pass

    async def spy(sm, st=None, limit=None):
        cards["stats"] = await orig(sm, st, limit)
        return cards["stats"]
    monkeypatch.setattr(main._cev, "games_pass", spy)

    async def go():
        sm = live.sm
        key, games, dealers = await _fresh_game(sm, "h%d" % SHAPES.index(shape), dup=True)
        word, seat_games, sittings, _p = await main.review_worker_pass(sm, False)
        g = (await _rows(sm, GAME, k=key))[0]
        derived = await _derived(sm, key)
        async with sm() as db:
            adm = await ce.admin_view(db, stable_game_key=key, rs=state.ruleset)
        return (word, seat_games, sittings, g, derived, await _stored(sm, games, dealers),
                await _from_scratch(sm, state, games, dealers), adm)
    word, seat_games, sittings, g, derived, stored, want, adm = live.run(go())
    assert word == state.word
    for stats in (seat_games, sittings, cards["stats"]):
        assert not _errors(stats) and not stats.get("fault_unrecorded"), (shape, stats)
    assert cards["stats"]["parked"] == 0
    assert g["derive_fault"] is None and g["evaluated_rev"] == state.ruleset.rev and g["finalized_at"]
    # derivation proceeded: the hand rows always (the duplicate is outside),
    # the contributions exactly when the revision has a weight family (no
    # expectation without weights)
    assert derived["card_hand_outside"] > 0
    assert (derived["card_contrib"] > 0) == weighed
    assert stored == want
    assert bool(want) == has_card                               # control: a card shape fires here
    assert adm["review_rules"] == state.ruleset.rev and adm["games"]


ZERO = [s for s in SHAPES if not k.revision_shapes()[s][2]]


@pytest.mark.parametrize("shape", ZERO)
def test_m2_a_card_aware_revision_then_one_without_card_rules_retires_every_prior_finding(live, revs, shape):
    """R1 (card rules) writes game and window findings; R2 has no card rules.
    After R2's pass the stored unposted findings equal R2's from-scratch
    oracle -- none -- and the game is stamped with R2."""
    second = revs.shapes[shape]
    tag = "z%d" % ZERO.index(shape)
    before, after, want, stamped, contrib, (p1, ev, p2) = live.run(
        _two_revisions(live.sm, revs.shadow, second, tag))
    r1, r2 = revs.shadow.ruleset.rev, second.ruleset.rev
    assert any(kk[0] == "sitting" for kk in before) and any(kk[0] == "game" for kk in before)  # control
    assert want == {} and after == want
    assert stamped <= {r2} and r1 not in contrib
    assert ev == r2 and p2 == p1


# -- M2: a visit that raises does not hold the queue head --------------------------------------

def test_m2_a_raising_evaluator_is_recorded_and_the_queue_advances_then_heals(live, revs, monkeypatch):
    """Two fresh games whose card evaluation raises (the evaluator, under a
    test hook that names the game being visited). With one game per pass the
    second pass visits the second game, not the first again. Each faulted
    visit is recorded (error class, count, revision) and nothing is
    finalized or stamped; at the bound both are parked: the next pass skips
    them and the health count shows them. New input wakes one for one more
    visit; another revision restarts the count; a revision whose evaluator
    does not raise evaluates both and clears the count."""
    cap = ce.CARD_FAULT_LIMITS["attempts"]
    faulty, other_faulty, healed = revs.again, revs.moved, revs.shadow
    targets = set()
    current = {}

    def hook(key):
        current["k"] = key

    def raising(rs_obj):
        orig = rs_obj.evaluate_card

        def evaluate_card(subjects, budget=None):
            if current.get("k") in targets:
                raise RuntimeError("synthetic evaluator fault")
            return orig(subjects, budget)
        return evaluate_card
    monkeypatch.setattr(ce, "_VISIT_HOOK", hook)
    monkeypatch.setattr(faulty.ruleset, "evaluate_card", raising(faulty.ruleset))
    monkeypatch.setattr(other_faulty.ruleset, "evaluate_card", raising(other_faulty.ruleset))
    sel = ("SELECT stable_game_key k, fault_attempts n, fault_rev r, derive_fault f, finalized_at fin, "
           "evaluated_rev ev, processed_at p FROM card_games WHERE stable_game_key = ANY(CAST(:ks AS varchar[]))")

    async def rows(keys):
        return {r["k"]: r for r in await _rows(live.sm, sel, ks=keys)}

    async def go():
        sm = live.sm
        await ce.games_pass(sm, faulty)        # every earlier game visited under this revision first
        ka, _ga, _da = await _fresh_game(sm, "fa")
        kb, _gb, _db = await _fresh_game(sm, "fb")
        targets.update({ka, kb})
        keys = [ka, kb]
        out = {}
        s1 = await ce.games_pass(sm, faulty, limit=1)
        out["after1"] = await rows(keys)
        s2 = await ce.games_pass(sm, faulty, limit=1)
        out["after2"] = await rows(keys)
        out["stats12"] = (s1, s2)
        passes = 0
        while passes < cap + 3:
            r = await rows(keys)
            if all(r[x]["n"] >= cap for x in keys):
                break
            await ce.games_pass(sm, faulty)
            passes += 1
        out["parked"] = await rows(keys)
        out["parked_count"] = ce.parked()
        s_skip = await ce.games_pass(sm, faulty)
        out["skipped"] = await rows(keys)
        out["skip_stats"] = s_skip
        # new input on game a: the conflict marker as store_record sets it
        # (a new input generation)
        await _exec(sm, "UPDATE card_evidence SET conflict_at = now(), gen = nextval('card_input_gen') "
                        "WHERE stable_game_key = :k", k=ka)
        await ce.games_pass(sm, faulty)
        out["woken"] = await rows(keys)
        await ce.games_pass(sm, other_faulty)
        out["other_rev"] = await rows(keys)
        targets.clear()
        heal = await ce.games_pass(sm, healed)
        out["healed"] = await rows(keys)
        out["heal_stats"] = heal
        out["heal_count"] = ce.parked()
        return keys, out
    (ka, kb), out = live.run(go())
    a1 = out["after1"].get(ka)
    first = ka if a1 is not None and a1["n"] == 1 else kb
    second = kb if first == ka else ka
    assert out["after1"][first]["n"] == 1 and (out["after1"].get(second) is None
                                                or out["after1"][second]["n"] == 0)
    assert out["after2"][second]["n"] == 1 and out["after2"][first]["n"] == 1     # the queue advanced
    s1, s2 = out["stats12"]
    assert s1.get("error:RuntimeError") == 1 and s2.get("error:RuntimeError") == 1
    for x in (ka, kb):
        r = out["after2"][x]
        assert r["f"] == "error:RuntimeError" and r["r"] == faulty.ruleset.rev
        assert r["fin"] is None and r["ev"] is None                               # nothing finalized
    p = out["parked"]
    assert all(p[x]["n"] == cap for x in (ka, kb))
    assert out["parked_count"] == 2
    sk = out["skipped"]
    assert all(sk[x]["p"] == p[x]["p"] and sk[x]["n"] == cap for x in (ka, kb))   # not visited
    assert out["skip_stats"]["parked"] == 2
    w = out["woken"]
    assert w[ka]["n"] == cap + 1 and w[kb]["n"] == cap                             # new input: one visit
    o = out["other_rev"]
    assert all(o[x]["n"] == 1 and o[x]["r"] == other_faulty.ruleset.rev for x in (ka, kb))
    h = out["healed"]
    assert all(h[x]["n"] == 0 and h[x]["r"] is None and h[x]["f"] is None for x in (ka, kb))
    assert all(h[x]["ev"] == healed.ruleset.rev and h[x]["fin"] for x in (ka, kb))
    assert not _errors(out["heal_stats"]) and out["heal_count"] == 0


# == fix pass 4 ===========================================================================

# -- M3: an input committed after a visit always schedules another ------------------------------

class _Gated:
    """A session whose commit waits at a gate: the input's statements have
    run and its transaction stays open (ready is set) until the gate opens,
    then it commits. Everything else is the session's own."""

    def __init__(self, db):
        self._db = db
        self.ready = asyncio.Event()
        self.gate = asyncio.Event()

    def __getattr__(self, name):
        return getattr(self._db, name)

    async def commit(self):
        self.ready.set()
        await self.gate.wait()
        await self._db.commit()


async def _candidates(sm, state):
    rev = state.ruleset.rev if state is not None else None
    async with sm() as db:
        return [r[0] for r in (await db.execute(ce._CANDIDATES, {
            "lim": 100000, "rev": rev, "cap": ce.CARD_FAULT_LIMITS["attempts"],
            "reprobe": ce.CARD_RETRY_LIMITS["reprobe_s"]})).all()]


WROW = ("SELECT processed_at, seen_inputs, finalized_at, evaluated_rev, derive_fault, fault_attempts, "
        "fault_inputs, parked_at, op_attempts, retry_at, fault_rev FROM card_games WHERE stable_game_key = :k")


async def _witness(sm, key, publish, during_state, visited, during_hook=None):
    """Two connections. The input's transaction begins and runs its
    statements (publish, on a gated session) and stays open; the worker runs
    a whole pass (during_state) that visits the game; the input commits;
    then the candidate query, a pass, and one more pass (the quiet control)."""
    out = {}
    async with sm() as raw:
        g = _Gated(raw)
        task = asyncio.ensure_future(publish(g))
        await asyncio.wait_for(g.ready.wait(), 30)
        out["open"] = await _scalar(sm, "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                                        "AND state = 'idle in transaction'")
        out["began"] = await _scalar(sm, "SELECT min(xact_start) FROM pg_stat_activity "
                                         "WHERE datname = current_database() AND state = 'idle in transaction'")
        visited.clear()
        out["during_stats"] = await ce.games_pass(sm, during_state)
        out["during"] = key in visited
        out["g1"] = dict((await _rows(sm, WROW, k=key))[0])
        if during_hook is not None:
            out["held"] = await during_hook()
        g.gate.set()
        out["result"] = await asyncio.wait_for(task, 30)
    out["scheduled"] = key in await _candidates(sm, during_state)
    return out


async def _after(sm, key, state, visited):
    visited.clear()
    stats = await ce.games_pass(sm, state)
    woken = key in visited
    g2 = dict((await _rows(sm, WROW, k=key))[0])
    visited.clear()
    await ce.games_pass(sm, state)
    return woken, g2, key not in visited, stats


def _spy(monkeypatch, raising=None):
    visited = []

    def hook(key):
        visited.append(key)
        if raising is not None and key in raising:
            raise RuntimeError("synthetic evaluator fault")
    monkeypatch.setattr(ce, "_VISIT_HOOK", hook)
    return visited


def _gated_record(ids, seat, other, key, rec):
    env = ce.parse_envelope(k.envelope(rec, seat=seat, other=other, stable=key, rounds=5))
    parsed = ce.parse_record(env)

    async def publish(db):
        return await ce.store_record(db, env, parsed, ids[seat], ids[other], "1.41.0")
    return publish


def _gated_census(cards):
    async def publish(db):
        return await ce.register_census(db, k.census_dump(cards))
    return publish


def test_m3_fix4_a_record_published_across_a_visit_schedules_the_game_again(live, revs, monkeypatch):
    """Record publication. A game final by expiry with one record; the other
    seat's record is inserted in a transaction that stays open while a whole
    pass visits the game (under another revision) and then commits. The
    record's time is earlier than the visit, so no clock comparison could
    see it; the game is scheduled and visited again, with both records'
    generations in what that visit read, and then left alone."""
    visited = _spy(monkeypatch)

    async def go():
        sm = live.sm
        a, b = _steams()
        ids = await _players(sm, a, b)
        key = "ranked_cardw1_000001"
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, ra)
        await _match(sm, ids, a, b, key + "_r5", sc="off")
        await ce.games_pass(sm, revs.shadow)
        await _exec(sm, "UPDATE card_games SET first_seen_at = now() - make_interval(days => CAST(:d AS int)) "
                        "WHERE stable_game_key = :k", d=ce.CARD_LIMITS["expiry_days"] + 1, k=key)
        await ce.games_pass(sm, revs.shadow)
        g0 = dict((await _rows(sm, WROW, k=key))[0])
        w = await _witness(sm, key, _gated_record(ids, b, a, key, rb), revs.again, visited)
        w["input_at"] = await _scalar(sm, "SELECT received_at FROM card_evidence WHERE stable_game_key = :k "
                                          "AND seat_player_id = :s", k=key, s=ids[b])
        w["after"] = await _after(sm, key, revs.again, visited)
        return g0, w
    g0, w = live.run(go())
    assert g0["finalized_at"] is not None and len(g0["seen_inputs"].split(",")) == 1     # final with one record
    assert w["open"] >= 1 and w["began"] is not None                                      # the input was open
    assert w["during"] and w["g1"]["evaluated_rev"] == revs.again.ruleset.rev             # the visit ran then
    assert w["g1"]["seen_inputs"] == g0["seen_inputs"]                                    # without the record
    assert w["result"] == {"status": "recorded"}
    assert w["input_at"] < w["g1"]["processed_at"]           # control: earlier than the visit by the clock
    woken, g2, quiet, _s = w["after"]
    assert w["scheduled"] and woken
    assert g2["processed_at"] > w["g1"]["processed_at"] and len(g2["seen_inputs"].split(",")) == 2
    assert quiet                                                                          # then left alone


def test_m3_fix4_a_census_published_across_a_faulted_visit_wakes_the_parked_game(live, revs, monkeypatch):
    """Census publication. A game whose visits raise a deterministic fault
    is one fault short of parked; a census its records name is registered in
    a transaction that stays open while a pass visits the game, faults it
    and parks it; a further pass leaves the parked game alone (control);
    the census commits. The parked game is scheduled again at once (inside
    the re-probe interval), visited, evaluated, and every fault field
    cleared."""
    raising = set()
    visited = _spy(monkeypatch, raising)
    cap = ce.CARD_FAULT_LIMITS["attempts"]

    async def go():
        sm = live.sm
        a, b = _steams()
        ids = await _players(sm, a, b)
        key = "ranked_cardw2_000001"
        c = k.fixture_census("full_game", cats={6: ["W2"]})
        rec = k.on_census(k.fixture_record("full_game"), c)
        await _store(sm, ids, a, b, key, rec)
        await _store(sm, ids, b, a, key, k.mirror(rec))
        await _match(sm, ids, a, b, key + "_r5", sc="off")
        raising.add(key)
        for _i in range(cap + 2):
            n = await _scalar(sm, "SELECT fault_attempts FROM card_games WHERE stable_game_key = :k", k=key)
            if n is not None and n >= cap - 1:
                break
            await ce.games_pass(sm, revs.again)
        g0 = dict((await _rows(sm, WROW, k=key))[0])

        async def held():
            visited.clear()
            await ce.games_pass(sm, revs.again)
            return key not in visited
        w = await _witness(sm, key, _gated_census(c.cards), revs.again, visited, during_hook=held)
        w["input_at"] = await _scalar(sm, "SELECT registered_at FROM card_pool_registry WHERE digest = :d",
                                      d=c.digest)
        raising.clear()
        w["after"] = await _after(sm, key, revs.again, visited)
        return g0, w
    g0, w = live.run(go())
    assert g0["fault_attempts"] == cap - 1 and g0["parked_at"] is None
    assert w["open"] >= 1 and w["during"]
    g1 = w["g1"]
    assert g1["fault_attempts"] == cap and g1["parked_at"] is not None                   # parked by that visit
    assert g1["fault_inputs"].endswith(":0") and g1["fault_rev"] == revs.again.ruleset.rev
    assert w["held"]                                         # control: parked, no new input, not visited
    assert w["result"]["status"] == "registered"
    assert w["input_at"] < g1["processed_at"]
    woken, g2, quiet, _s = w["after"]
    assert w["scheduled"] and woken
    assert g2["derive_fault"] is None and g2["fault_attempts"] == 0 and g2["parked_at"] is None
    assert g2["fault_inputs"] is None and g2["finalized_at"] is not None
    assert g2["evaluated_rev"] == revs.again.ruleset.rev
    assert not any(p.endswith(":0") for p in g2["seen_inputs"].split(","))              # the census read
    assert quiet


def test_m3_fix4_a_census_published_across_a_visit_to_a_normally_final_game_schedules_it(live, revs,
                                                                                         monkeypatch):
    """A normally finalized game (both records name the attached match).
    The census its records name is registered in a transaction that stays
    open while a pass re-visits the game under another revision, and
    commits after it. The game is scheduled and visited again, reading the
    census, and then left alone."""
    visited = _spy(monkeypatch)

    async def go():
        sm = live.sm
        a, b = _steams()
        ids = await _players(sm, a, b)
        key = "ranked_cardw3_000001"
        c = k.fixture_census("full_game", cats={6: ["W3"]})
        rec = k.on_census(k.fixture_record("full_game"), c)
        await _store(sm, ids, a, b, key, rec)
        await _store(sm, ids, b, a, key, k.mirror(rec))
        await _match(sm, ids, a, b, key + "_r5", sc="off")
        await ce.games_pass(sm, revs.shadow)
        g0 = dict((await _rows(sm, WROW, k=key))[0])
        w = await _witness(sm, key, _gated_census(c.cards), revs.again, visited)
        w["input_at"] = await _scalar(sm, "SELECT registered_at FROM card_pool_registry WHERE digest = :d",
                                      d=c.digest)
        w["after"] = await _after(sm, key, revs.again, visited)
        return g0, w
    g0, w = live.run(go())
    assert g0["finalized_at"] is not None and g0["evaluated_rev"] == revs.shadow.ruleset.rev
    assert all(p.endswith(":0") for p in g0["seen_inputs"].split(","))                  # census unregistered
    assert w["open"] >= 1 and w["during"] and w["g1"]["evaluated_rev"] == revs.again.ruleset.rev
    assert w["g1"]["seen_inputs"] == g0["seen_inputs"] and w["g1"]["finalized_at"] is not None
    assert w["result"]["status"] == "registered"
    assert w["input_at"] < w["g1"]["processed_at"]
    woken, g2, quiet, _s = w["after"]
    assert w["scheduled"] and woken
    assert g2["processed_at"] > w["g1"]["processed_at"]
    assert not any(p.endswith(":0") for p in g2["seen_inputs"].split(","))
    assert quiet


# -- M4: bounded backoff, recovery, re-probe ---------------------------------------------------

def test_m4_fix4_five_pool_failures_back_off_never_park_and_the_next_probe_evaluates(live, revs, monkeypatch):
    """Five induced pool failures (the visit raises the pool's own timeout
    error): each is operational, counted on op_attempts only, the game waits
    retry_delay(failures before) and a pass inside that wait leaves it
    alone; time is moved past each wait. Then the pool recovers and the
    next probe evaluates the game: final, under the same revision, every
    fault field clear, no new evidence."""
    import sqlalchemy.exc as sx
    failing = {"on": True}
    visited = []
    target = {}

    def hook(key):
        visited.append(key)
        if failing["on"] and key == target.get("k"):
            raise sx.TimeoutError("QueuePool limit reached, connection timed out")
    monkeypatch.setattr(ce, "_VISIT_HOOK", hook)

    async def go():
        sm = live.sm
        key, _g, _d = await _fresh_game(sm, "op")
        target["k"] = key
        ev_before = await _scalar(sm, "SELECT count(*) FROM card_evidence WHERE stable_game_key = :k", k=key)
        gens_before = await _scalar(sm, "SELECT string_agg(gen::text, ',' ORDER BY gen) FROM card_evidence "
                                        "WHERE stable_game_key = :k", k=key)
        steps = []
        for i in range(5):
            visited.clear()
            s = await ce.games_pass(sm, revs.shadow)
            hit = key in visited
            r = dict((await _rows(sm, WROW, k=key))[0])
            gap = await _scalar(sm, "SELECT EXTRACT(EPOCH FROM retry_at - processed_at) FROM card_games "
                                    "WHERE stable_game_key = :k", k=key)
            visited.clear()
            await ce.games_pass(sm, revs.shadow)                       # inside the wait
            held = key not in visited
            steps.append((hit, s.get("operational", 0), s.get("deterministic", 0), r, float(gap), held))
            await _exec(sm, "UPDATE card_games SET retry_at = retry_at - make_interval(secs => CAST(:d AS int)), "
                            "processed_at = processed_at - make_interval(secs => CAST(:d AS int)) "
                            "WHERE stable_game_key = :k", d=ce.retry_delay(i), k=key)
        failing["on"] = False
        visited.clear()
        s = await ce.games_pass(sm, revs.shadow)
        healed = dict((await _rows(sm, WROW, k=key))[0])
        ev_after = await _scalar(sm, "SELECT count(*) FROM card_evidence WHERE stable_game_key = :k", k=key)
        gens_after = await _scalar(sm, "SELECT string_agg(gen::text, ',' ORDER BY gen) FROM card_evidence "
                                       "WHERE stable_game_key = :k", k=key)
        return steps, key in visited, s, healed, (ev_before, gens_before), (ev_after, gens_after)
    steps, probed, s, healed, before, after = live.run(go())
    cap = ce.CARD_FAULT_LIMITS["attempts"]
    assert len(steps) == 5 >= cap                     # control: as many failures as the park bound
    for i, (hit, op, det, r, gap, held) in enumerate(steps):
        assert hit and op >= 1 and det == 0
        assert r["op_attempts"] == i + 1 and r["fault_attempts"] == 0 and r["parked_at"] is None
        assert r["derive_fault"] == "error:TimeoutError" and r["finalized_at"] is None
        assert gap == ce.retry_delay(i)
        assert held
    assert [st[4] for st in steps] == [30, 60, 120, 240, 480]
    assert probed and not _errors(s)
    assert healed["finalized_at"] is not None and healed["evaluated_rev"] == revs.shadow.ruleset.rev
    for col in ("derive_fault", "fault_rev", "fault_inputs", "parked_at", "retry_at"):
        assert healed[col] is None, col
    assert healed["op_attempts"] == 0 and healed["fault_attempts"] == 0
    assert before == after                                       # no new evidence, no new generation


def test_m4_fix4_a_parked_game_is_re_probed_at_the_interval_and_heals(live, revs, monkeypatch):
    """Deterministic faults park a game; inside the re-probe interval passes
    leave it alone; past the interval the next pass re-probes it (still
    faulting: still parked, the park time kept, alone again for another
    interval); the health age reads the oldest park; past the interval
    again with the fault gone, the game is evaluated and cleared."""
    raising = set()
    visited = _spy(monkeypatch, raising)
    cap = ce.CARD_FAULT_LIMITS["attempts"]
    rp = ce.CARD_RETRY_LIMITS["reprobe_s"]
    back = ("UPDATE card_games SET processed_at = processed_at - make_interval(secs => CAST(:d AS int)) "
            "WHERE stable_game_key = :k")

    async def go():
        sm = live.sm
        key, _g, _d = await _fresh_game(sm, "rp")
        raising.add(key)
        for _i in range(cap + 2):
            n = await _scalar(sm, "SELECT fault_attempts FROM card_games WHERE stable_game_key = :k", k=key)
            if n is not None and n >= cap:
                break
            await ce.games_pass(sm, revs.shadow)
        out = {"parked": dict((await _rows(sm, WROW, k=key))[0])}
        await _exec(sm, "UPDATE card_games SET parked_at = parked_at - make_interval(secs => CAST(:d AS int)) "
                        "WHERE stable_game_key = :k", d=2 * rp, k=key)
        visited.clear()
        out["inside"] = await ce.games_pass(sm, revs.shadow)
        out["inside_hit"] = key in visited
        out["health"] = (ce.parked(), ce.parked_oldest_s())
        await _exec(sm, back, d=rp + 1, k=key)
        visited.clear()
        await ce.games_pass(sm, revs.shadow)
        out["probe1_hit"] = key in visited
        out["probe1"] = dict((await _rows(sm, WROW, k=key))[0])
        visited.clear()
        await ce.games_pass(sm, revs.shadow)
        out["after1_hit"] = key in visited
        raising.clear()
        await _exec(sm, back, d=rp + 1, k=key)
        visited.clear()
        out["probe2_stats"] = await ce.games_pass(sm, revs.shadow)
        out["probe2_hit"] = key in visited
        out["healed"] = dict((await _rows(sm, WROW, k=key))[0])
        out["health_after"] = (ce.parked(), ce.parked_oldest_s())
        return out
    o = live.run(go())
    p = o["parked"]
    assert p["fault_attempts"] == cap and p["parked_at"] is not None and p["op_attempts"] == 0
    assert not o["inside_hit"] and o["inside"]["parked"] >= 1
    n, oldest = o["health"]
    assert n >= 1 and oldest >= 2 * rp
    assert o["probe1_hit"]
    p1 = o["probe1"]
    assert p1["fault_attempts"] == cap + 1 and p1["parked_at"] == p["parked_at"] - timedelta(seconds=2 * rp)
    assert not o["after1_hit"]                                           # alone for another interval
    assert o["probe2_hit"] and not _errors(o["probe2_stats"])
    h = o["healed"]
    assert h["finalized_at"] is not None and h["evaluated_rev"] == revs.shadow.ruleset.rev
    assert h["parked_at"] is None and h["fault_attempts"] == 0 and h["derive_fault"] is None
    assert o["health_after"] == (0, 0)


# -- LOW 3: every completed visit clears derive_fault -------------------------------------------

PRESET = ("UPDATE card_games SET derive_fault = 'error:Preset', fault_attempts = 2, fault_rev = NULL, "
          "fault_inputs = 'preset', op_attempts = 3, retry_at = NULL, parked_at = NULL")


def test_low3_fix4_the_no_revision_arm_clears_every_fault_field(live, monkeypatch):
    visited = _spy(monkeypatch)

    async def go():
        sm = live.sm
        a, b = _steams()
        ids = await _players(sm, a, b)
        key = "ranked_cardn3_000001"
        ra, rb, c = _pair()
        await _register(sm, k.census_dump(c.cards))
        await _store(sm, ids, a, b, key, ra)                     # no match yet: waiting
        await ce.games_pass(sm, None)
        await _exec(sm, PRESET + " WHERE stable_game_key = :k", k=key)
        preset = dict((await _rows(sm, WROW, k=key))[0])
        visited.clear()
        s = await ce.games_pass(sm, None)
        return preset, key in visited, s, dict((await _rows(sm, WROW, k=key))[0])
    preset, hit, s, g = live.run(go())
    assert preset["derive_fault"] == "error:Preset" and preset["op_attempts"] == 3      # control
    assert hit and s.get("waiting", 0) >= 1 and not _errors(s)
    assert g["derive_fault"] is None and g["fault_attempts"] == 0 and g["fault_inputs"] is None
    assert g["op_attempts"] == 0 and g["seen_inputs"]


def test_low3_fix4_the_unchanged_arm_clears_every_fault_field(live, revs, monkeypatch):
    visited = _spy(monkeypatch)

    async def go():
        sm = live.sm
        key, _g, _d = await _fresh_game(sm, "u3")
        await ce.games_pass(sm, revs.shadow)
        g0 = dict((await _rows(sm, WROW, k=key))[0])
        await _exec(sm, PRESET + ", seen_inputs = 'stale' WHERE stable_game_key = :k", k=key)
        preset = dict((await _rows(sm, WROW, k=key))[0])
        visited.clear()
        s = await ce.games_pass(sm, revs.shadow)
        return g0, preset, key in visited, s, dict((await _rows(sm, WROW, k=key))[0])
    g0, preset, hit, s, g = live.run(go())
    assert g0["finalized_at"] is not None and preset["derive_fault"] == "error:Preset"   # control
    assert hit and s.get("unchanged", 0) >= 1 and not _errors(s)
    assert g["derive_fault"] is None and g["fault_attempts"] == 0 and g["fault_inputs"] is None
    assert g["op_attempts"] == 0 and g["seen_inputs"] == g0["seen_inputs"]
    assert g["processed_at"] > g0["processed_at"]
