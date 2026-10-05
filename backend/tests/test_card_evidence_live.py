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
    return types.SimpleNamespace(shadow=k.load(store, shadow), armed=k.load(store, armed),
                                 again=k.load(store, again), conflict=k.load(store, conflict),
                                 picks=k.load(store, picks), moved=k.load(store, moved),
                                 dropped=k.load(store, dropped))


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
    assert set(s) <= {"evaluated", "fired", "rule_errors", "attached", "waiting"}, s
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
    assert sorted(r["rules_rev"] for r in revs_seen) == sorted([revs.shadow.ruleset.rev, revs.again.ruleset.rev])
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
