"""Identity-clock evidence against a real PostgreSQL 16: migration 372 (two
applies, the rollback, a third apply, the planted-namespace rollback), the
route (session first, switch, signature, first-record rule, hourly cap, the
clock header stored only for the record's own process, the connection class
with no address anywhere), the worker (attach, pair and nothing opened with
no revision; shadow then posting under a SYNTHETIC revision; advisory only),
the server-measured clock fit, the release registry's source, the game-file
registry, the admin read and the purge.

One case schema per module run (the build replays every migration). Every
rule value is synthetic. Live cases FAIL rather than skip unless
SEAT_EVIDENCE_TEST_PG_OPTOUT=1 (seat_evidence_pg)."""

import asyncio
import json
import os
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import conn_ranges as cr  # noqa: E402
import identity_clock_evidence as ice  # noqa: E402
import identity_clock_fixtures as fx  # noqa: E402
import identity_clock_pg as ip  # noqa: E402
import main  # noqa: E402
import review_rules as rr  # noqa: E402
import review_testkit as tk  # noqa: E402
import seat_evidence as se  # noqa: E402
import test_conn_ranges as tcr  # noqa: E402
import test_identity_clock_unit as tu  # noqa: E402
import test_seat_evidence_live as sl  # noqa: E402

# Synthetic 16-digit seats per case (no Steam account has 16 digits).
R_A, R_B, R_C = "1000000000000701", "1000000000000702", "1000000000000703"
K_A, K_B = "1000000000000711", "1000000000000712"
W_A, W_B = "1000000000000721", "1000000000000722"
F_A, F_B = "1000000000000731", "1000000000000732"
P_A, P_B = "1000000000000741", "1000000000000742"
ROUTE = main.submit_identity_clock_evidence


@pytest.fixture(scope="module")
def live():
    ip.require_live_pg()
    loop = asyncio.new_event_loop()
    cm = ip.case("ice")
    c, sm, snaps = loop.run_until_complete(cm.__aenter__())
    try:
        yield types.SimpleNamespace(run=loop.run_until_complete, case=c, sm=sm, snaps=snaps)
    finally:
        loop.run_until_complete(cm.__aexit__(None, None, None))
        loop.close()


@pytest.fixture
def signing(monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", fx.KEY)


@pytest.fixture(scope="module")
def revs(tmp_path_factory):
    """Two synthetic revisions with the identity rules: all in shadow, and the
    point rule armed from one day ago."""
    tmp = tmp_path_factory.mktemp("icrev")
    cases = tk.quiet_cases() + tu.identity_cases()
    store, shadow = tk.build_revision(tmp, tu.identity_doc(), cases, name="shadow")
    armed_doc = tu.identity_doc()
    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for r in armed_doc["rules"]:
        if r["id"] == tu.ID_PT:
            r["post"], r["post_since"] = True, since
    _s, armed = tk.build_revision(tmp, armed_doc, cases, name="armed")

    def state(rev):
        rs = rr.load_dir(os.path.join(store, "rules-" + rev))
        return rr.State(rs.rev, rs)
    return types.SimpleNamespace(shadow=state(shadow), armed=state(armed))


class Req(sl.Req):
    def __init__(self, body, token=None, clock=None, host=None):
        super().__init__(body, token)
        if clock is not None:
            self.headers[ice.CLOCK_HEADER] = clock
        self.client = types.SimpleNamespace(host=host) if host else None


async def _post(sm, body, token, clock=None, host=None):
    async with sm() as db:
        r = await ROUTE(Req(body, token, clock, host), db)
    if isinstance(r, dict):
        return 200, r
    return r.status_code, json.loads(r.body)


def _body(seat, other, stable, rounds=8, proc=fx.PROC_A, **over):
    return fx.envelope(fx.base_record(proc=proc, **over), seat=seat, other=other, stable=stable,
                       rounds=rounds)


ROW_SQL = ("SELECT post_clock, post_proc, post_sw_ms, post_unity_ms, post_photon_ts, conn_class, "
           "conn_ranges, conflict_kind FROM identity_clock_evidence WHERE stable_game_key = :k "
           "ORDER BY id")
GAME_SQL = ("SELECT match_id, finalized_at, evaluated_rev, records_n, paired_points "
            "FROM identity_clock_games WHERE stable_game_key = :k")


def _errors(stats):
    return {k for k in stats if k.startswith("error")} | (
        {"rule_errors"} if stats.get("rule_errors") else set())


# -- the migration --------------------------------------------------------------------

def _no_time(snap):
    """Switch rows without their timestamps (a re-seed after the rollback
    writes a new time by construction)."""
    return {k: ([r[:2] for r in v] if k == "runtime_settings" and v is not None else v)
            for k, v in snap.items()}


def test_migration_372_applies_twice_rolls_back_and_reapplies(live):
    s = live.snaps
    assert s["first"] == s["again"]
    assert s["before"]["identity_clock_evidence"] is None
    switches = {r[0]: r[1] for r in s["first"]["runtime_settings"] if r[0] in ip.ICE_SWITCHES}
    assert switches == {k: "1" for k in ip.ICE_SWITCHES}
    assert [r[0] for r in s["first"]["identity_clock_seeded_keys"]] == sorted(ip.ICE_SWITCHES)
    assert _no_time(s["rolled"]) == _no_time(s["before"])
    assert _no_time(s["third"]) == _no_time(s["first"])
    names = {r[0] for r in s["first"]["constraints"]}
    assert {"identity_clock_evidence_one_per_seat", "identity_clock_evidence_clock_cols",
            "identity_clock_evidence_conn_class", "identity_clock_evidence_post_clock"} <= names
    cols = " ".join(r[1] for r in s["first"]["constraints"])
    assert "address" not in cols


def test_the_rollback_removes_exactly_the_identity_namespace(live):
    s = live.snaps
    kept = sorted(d for _s, d, _r in ip.PLANTED_SEAT)
    planted = sorted(r[1] for r in s["planted"]["findings"])
    assert planted == sorted(d for _s, d, _r in ip.PLANTED)
    assert sorted(r[1] for r in s["planted_rolled"]["findings"]) == kept
    assert _no_time(s["fourth"])["identity_clock_evidence"] == []
    assert _no_time(s["fourth"])["constraints"] == _no_time(s["first"])["constraints"]


def test_a_reapply_keeps_a_switch_sid_set(live):
    async def go():
        await sl._set(live.sm, "identity_clock_evidence_purge", "0")
        await live.case.conn.execute(ip.read_372())
        v = await sl._scalar(live.sm, "SELECT value FROM runtime_settings "
                                      "WHERE key = 'identity_clock_evidence_purge'")
        await sl._set(live.sm, "identity_clock_evidence_purge", "1")
        return v
    assert live.run(go()) == "0"


# -- the route ----------------------------------------------------------------------

def test_the_session_is_first_then_the_switch_then_the_signature(live, signing):
    async def go():
        sm = live.sm
        key = "ranked_icr_000001"
        body = _body(R_C, R_B, key)
        out = [await _post(sm, body, None)]
        out.append(await _post(sm, body, await sl._session(sm, R_B)))     # another seat's session
        own = await sl._session(sm, R_C)
        out.append(await _post(sm, body, own))                             # no player row yet
        await sl._players(sm, R_C, R_B)
        await sl._set(sm, "identity_clock_evidence_accept", "0")
        try:
            out.append(await _post(sm, body, own))
        finally:
            await sl._set(sm, "identity_clock_evidence_accept", "1")
        out.append(await _post(sm, dict(body, sig="0" * 64), own))
        bad = _body(R_C, R_B, key)
        bad["record"] = bad["record"].replace('"consts":1', '"consts":-1')
        env = ice.ice_parse_envelope(bad)
        bad["sig"] = ice.ice_sign(fx.KEY, env)
        out.append(await _post(sm, bad, own))
        rows = await sl._scalar(sm, "SELECT count(*) FROM identity_clock_evidence "
                                    "WHERE stable_game_key = :k", k=key)
        out.append(await _post(sm, body, own))
        return out, rows
    out, rows = live.run(go())
    assert [o[0] for o in out] == [401, 401, 409, 503, 403, 422, 200], out
    assert out[3][1] == {"error": "identity_clock_evidence_off"}
    assert out[5][1] == {"detail": "consts"} and rows == 0
    assert out[6][1] == {"status": "recorded"}


def test_the_first_record_is_kept_and_a_conflict_marked_once(live, signing):
    async def go():
        sm = live.sm
        await sl._players(sm, K_A, K_B)
        tok = await sl._session(sm, K_A)
        key = "ranked_ick_000001"
        first, second = _body(K_A, K_B, key), _body(K_A, K_B, key, consts=2)
        out = [await _post(sm, first, tok, fx.clock()), await _post(sm, second, tok)]
        out.append(await _post(sm, first, tok, fx.clock(sw=9)))            # identical retry
        rows = await sl._rows(sm, ROW_SQL, k=key)
        return out, rows
    out, rows = live.run(go())
    assert [o[1] for o in out] == [{"status": "recorded"}, {"status": "conflict"},
                                   {"status": "already_recorded"}]
    assert len(rows) == 1 and rows[0]["conflict_kind"] == "payload"
    assert rows[0]["post_sw_ms"] == 5_000_000                              # the first post's sample


def test_l9_the_clock_columns_are_stored_only_for_the_records_own_process(live, signing):
    async def go():
        sm = live.sm
        await sl._players(sm, K_A, K_B)
        tok = await sl._session(sm, K_A)
        res = {}
        for tag, hdr in (("ok", fx.clock()), ("other", fx.clock(proc=fx.PROC_B)),
                         ("bad", "zz"), ("none", None)):
            key = "ranked_icl9_%s" % tag
            await _post(sm, _body(K_A, K_B, key), tok, hdr)
            res[tag] = (await sl._rows(sm, ROW_SQL, k=key))[0]
        return res
    res = live.run(go())
    assert (res["ok"]["post_clock"], res["ok"]["post_proc"], res["ok"]["post_photon_ts"]) == (
        "ok", fx.PROC_A, 123_456)
    for tag, state in (("other", "other_proc"), ("bad", "malformed"), ("none", "absent")):
        r = res[tag]
        assert r["post_clock"] == state
        assert (r["post_proc"], r["post_sw_ms"], r["post_unity_ms"], r["post_photon_ts"]) == (
            None, None, None, None)


def test_the_hourly_cap_answers_429(live, signing, monkeypatch):
    monkeypatch.setitem(ice.IC_WIRE, "hourly_cap", 2)

    async def go():
        sm = live.sm
        await sl._players(sm, P_A, P_B)
        tok = await sl._session(sm, P_A)
        return [await _post(sm, _body(P_A, P_B, "ranked_iccap_%d" % i), tok) for i in range(3)]
    out = live.run(go())
    assert [o[0] for o in out] == [200, 200, 429]
    assert out[2][1] == {"error": "rate_limited", "field": "seat_hourly_cap"}


# -- S3 / Q3: the class is stored, the address is not ------------------------------------

def _row_text(rows):
    return json.dumps([{k: str(v) for k, v in dict(r).items()} for r in rows])


def test_s3_q3_the_class_is_stored_and_the_address_appears_nowhere(live, signing, monkeypatch,
                                                                   tmp_path, capsys):
    root = tcr._store(tmp_path)
    monkeypatch.setenv(cr.CR_ROOT_ENV, root)
    monkeypatch.setattr(cr, "_CR_STATE", cr.RangesState("absent"))
    monkeypatch.setattr(cr, "_CR_KEY", None)
    monkeypatch.setattr(cr, "_CR_LOGGED", None)
    rev, _st = tcr._loaded(tmp_path, root)
    capsys.readouterr()
    hosts = {"hosting": "203.0.113.41", "vpn": "198.51.100.41", "tor": "2001:db8:1::41",
             "none": "192.0.2.41", "lan": "10.9.8.41"}

    async def go():
        sm = live.sm
        await sl._players(sm, K_A, K_B)
        tok = await sl._session(sm, K_A)
        for cls, host in hosts.items():
            await _post(sm, _body(K_A, K_B, "ranked_ics3_" + cls), tok, fx.clock(), host)
        await _post(sm, _body(K_A, K_B, "ranked_ics3_nohost"), tok, fx.clock())
        rows = await sl._rows(sm, "SELECT * FROM identity_clock_evidence "
                                  "WHERE stable_game_key LIKE 'ranked_ics3_%' ORDER BY stable_game_key")
        settings = await sl._rows(sm, "SELECT * FROM runtime_settings")
        findings = await sl._rows(sm, "SELECT * FROM seat_evidence_findings")
        return rows, settings, findings
    rows, settings, findings = live.run(go())
    got = {r["stable_game_key"][len("ranked_ics3_"):]: (r["conn_class"], r["conn_ranges"])
           for r in rows}
    assert got == dict({c: (c, rev) for c in hosts}, nohost=("unknown", rev))
    out = capsys.readouterr()
    dumped = _row_text(rows) + _row_text(settings) + _row_text(findings) + out.out + out.err
    assert not [h for h in hosts.values() if h in dumped]
    # positive control: the same scan finds an address planted in a row
    assert hosts["vpn"] in _row_text([{"x": hosts["vpn"]}])


def test_s1_no_list_staged_classifies_unknown_with_the_absent_word(live, signing, monkeypatch):
    monkeypatch.setattr(cr, "_CR_STATE", cr.RangesState("absent"))

    async def go():
        sm = live.sm
        await sl._players(sm, K_A, K_B)
        tok = await sl._session(sm, K_A)
        await _post(sm, _body(K_A, K_B, "ranked_ics1_x"), tok, None, "203.0.113.41")
        return await sl._rows(sm, ROW_SQL, k="ranked_ics1_x")
    rows = live.run(go())
    assert (rows[0]["conn_class"], rows[0]["conn_ranges"]) == ("unknown", "absent")


def test_s1_the_health_words(monkeypatch):
    assert main._identity_clock_health_word() == 1
    monkeypatch.setattr(main, "_IDENTITY_CLOCK_ROUTES", main._IDENTITY_CLOCK_ROUTES + (len,))
    assert main._identity_clock_health_word() == 0
    monkeypatch.setattr(cr, "_CR_STATE", cr.RangesState("refused", reason="digest"))
    assert cr.ranges_health_word() == "refused"


# -- the worker ---------------------------------------------------------------------------

def test_s4_no_revision_attaches_pairs_and_opens_nothing(live, signing):
    key = "ranked_icw4_000001"

    async def go():
        sm = live.sm
        ids = await sl._players(sm, W_A, W_B)
        ta, tb = await sl._session(sm, W_A), await sl._session(sm, W_B)
        await _post(sm, _body(W_A, W_B, key), ta, fx.clock())
        await _post(sm, _body(W_B, W_A, key, proc=fx.PROC_B), tb, fx.clock(proc=fx.PROC_B))
        s1 = await ice.ice_games_pass(sm, None)
        g1 = await sl._rows(sm, GAME_SQL, k=key)
        mid = await sl._match(sm, ids, W_A, W_B, key + "_r8")
        before = await sl._counts(sm)
        s2 = await ice.ice_games_pass(sm, rr.State("absent"))
        g2 = await sl._rows(sm, GAME_SQL, k=key)
        after = await sl._counts(sm)
        return (s1, s2), g1, g2, mid, before, after
    stats, g1, g2, mid, before, after = live.run(go())
    assert not any(_errors(s) for s in stats), stats
    assert g1[0]["match_id"] is None and g1[0]["records_n"] == 2 and g1[0]["paired_points"] == 6
    assert g2[0]["match_id"] == mid and g2[0]["finalized_at"] is None
    assert g2[0]["evaluated_rev"] is None
    assert after == before                                  # no finding, no flag


def test_shadow_then_posting_advisory_only(live, signing, revs):
    new, quiet = "ranked_icw8_000001", "ranked_icw8_000002"

    async def go():
        sm = live.sm
        ids = await sl._players(sm, W_A, W_B)
        ta, tb = await sl._session(sm, W_A), await sl._session(sm, W_B)
        late = fx.base_record(proc=fx.PROC_B)
        late["pt_o"][0][5] = [980, 1200, -1, -1]
        for key, b_rec in ((new, late), (quiet, fx.base_record(proc=fx.PROC_B))):
            await sl._match(sm, ids, W_A, W_B, key + "_r8")
            await _post(sm, _body(W_A, W_B, key), ta)
            await _post(sm, fx.envelope(b_rec, seat=W_B, other=W_A, stable=key), tb)
        before = await sl._counts(sm)
        s1 = await ice.ice_games_pass(sm, revs.shadow)
        f1 = await sl._rows(sm, sl._findings_sql("dedup_key LIKE :k"), k="identity " + new + "|%")
        q1 = await sl._rows(sm, sl._findings_sql("dedup_key LIKE :k"), k="identity " + quiet + "|%")
        mid = await sl._counts(sm)
        s2 = await ice.ice_games_pass(sm, revs.armed)
        f2 = await sl._rows(sm, sl._findings_sql("dedup_key LIKE :k"), k="identity " + new + "|%")
        flags = await sl._rows(sm, "SELECT flag_reason, auto_invalidated, flag_details "
                                   "FROM flagged_matches WHERE flag_reason = 'review'")
        s3 = await ice.ice_games_pass(sm, revs.armed)
        after = await sl._counts(sm)
        g = await sl._rows(sm, GAME_SQL, k=new)
        return (s1, s2, s3), before, mid, after, f1, q1, f2, flags, g
    stats, before, mid, after, f1, q1, f2, flags, g = live.run(go())
    assert not any(_errors(s) for s in stats), stats
    assert [r["rule_id"] for r in f1] == [tu.ID_PT] and f1[0]["flag_id"] is None
    assert q1 == []
    assert mid[0] == before[0]                                   # shadow posts nothing
    assert f2[0]["rules_rev"] == revs.armed.ruleset.rev and f2[0]["flag_id"] is not None
    mine = [f for f in flags if se._jsonv(f["flag_details"]).get("rule_id") == tu.ID_PT]
    assert len(mine) == 1 and mine[0]["auto_invalidated"] is False
    assert se._jsonv(mine[0]["flag_details"])["line"].startswith("synthetic point 0 ")
    assert after[0] == mid[0] + 1 and stats[2]["evaluated"] == 0
    assert g[0]["evaluated_rev"] == revs.armed.ruleset.rev and g[0]["finalized_at"] is not None


# -- C12: the server-measured fit ------------------------------------------------------

def test_c12_the_fit_of_one_process_tracks_a_scaled_stopwatch(live, signing):
    async def go():
        sm = live.sm
        await sl._players(sm, F_A, F_B)
        tok = await sl._session(sm, F_A)
        for i in range(8):
            await _post(sm, _body(F_A, F_B, "ranked_icfit_%d" % i), tok, fx.clock())
        await _post(sm, _body(F_A, F_B, "ranked_icfit_other"), tok, fx.clock(proc=fx.PROC_B))
        async with sm() as db:
            await db.execute(text(
                "UPDATE identity_clock_evidence SET "
                "  received_at = TIMESTAMPTZ '2026-10-01 00:00:00+00' "
                "    + make_interval(secs => CAST(substr(stable_game_key, 14) AS int) * 60), "
                "  post_sw_ms = 1000 + CAST(substr(stable_game_key, 14) AS bigint) * 60030, "
                "  post_unity_ms = 5000 + CAST(substr(stable_game_key, 14) AS bigint) * 60000, "
                "  post_photon_ts = 7 + CAST(substr(stable_game_key, 14) AS int) * 60000 "
                "WHERE stable_game_key LIKE 'ranked_icfit_%' AND post_clock = 'ok'"))
            await db.commit()
            pid = (await db.execute(text("SELECT id FROM players WHERE steam_id = :s"),
                                    {"s": F_A})).scalar()
            fit, n = await ice.ice_fit_for(db, pid, fx.PROC_A)
            none, n0 = await ice.ice_fit_for(db, pid, fx.PROC_B)
        return fit, n, none, n0
    fit, n, none, n0 = live.run(go())
    assert n == 8 and abs(fit["sw"][0] - 500) < 1 and abs(fit["unity"][0]) < 1
    assert fit["sw"][2] == 8 and fit["sw"][3] == 7 * 60_000
    assert n0 == 0 and none == {"sw": None, "unity": None, "photon": None}


# -- registries, admin read, purge ----------------------------------------------------------

def test_the_release_source_and_the_game_file_registry(live):
    async def go():
        sm = live.sm
        out = []
        async with sm() as db:
            out.append(await se.register_digest(db, "1.41.1", "STANDALONE", "bbbbbbbbbbbb",
                                                "f" * 64, "beta"))
            try:
                await se.register_digest(db, "1.41.2", "STANDALONE", "", "f" * 64, "nightly")
            except se.EvidenceRefused as r:
                out.append((r.status, r.field))
            out.append(await ice.ice_register_game_file(db, 3, "1.0.0", "a" * 64))
            out.append(await ice.ice_register_game_file(db, 3, "1.0.0", "a" * 64))
            try:
                await ice.ice_register_game_file(db, 300, "1.0.0", "a" * 64)
            except se.EvidenceRefused as r:
                out.append((r.status, r.field))
            regs = await ice.ice_registries(db)
        return out, regs
    out, regs = live.run(go())
    assert out[1] == (422, "release_source") and out[4] == (422, "game_file")
    assert [o["status"] for o in (out[2], out[3])] == ["registered", "already_registered"]
    assert regs["release"][("1.41.1", "STANDALONE", "bbbbbbbbbbbb", "f" * 64)] == "beta"
    assert (3, "a" * 64) in regs["game_files"]


def test_the_admin_read_shows_both_seats_side_by_side_and_no_address(live, signing):
    key = "ranked_icw4_000001"

    async def go():
        async with live.sm() as db:
            return await ice.ice_admin_view(db, stable_game_key=key)
    view = live.run(go())
    (game,) = view["games"]
    assert game["attached"] and game["paired_points"] == 6 and len(game["records"]) == 2
    assert set(view["labels"]) >= {"self_stated", "other_seat_measured", "server_observed"}
    assert {r["post_clock"] for r in game["records"]} == {"ok"}
    text_ = json.dumps(view, default=str)
    assert "client" not in text_ and "host" not in text_


def test_purge_drops_old_lists_and_old_unattached_records_only(live, signing):
    async def go():
        sm = live.sm
        await sl._players(sm, P_A, P_B)
        tok = await sl._session(sm, P_A)
        for k in ("ranked_icpu_old", "ranked_icpu_new"):
            await _post(sm, _body(P_A, P_B, k), tok)
        async with sm() as db:
            await db.execute(text(
                "UPDATE identity_clock_evidence SET received_at = now() - make_interval(days => "
                "CAST(:d AS int)) WHERE stable_game_key = 'ranked_icpu_old'"),
                {"d": ice.ICE_LIST_RETENTION_DAYS + 1})
            await db.commit()
        out = await ice.ice_purge_pass(sm)
        left = await sl._rows(sm, "SELECT stable_game_key, lists_purged_at, payload "
                                  "FROM identity_clock_evidence WHERE stable_game_key LIKE "
                                  "'ranked_icpu_%' ORDER BY 1")
        return out, left
    out, left = live.run(go())
    assert [r["stable_game_key"] for r in left] == ["ranked_icpu_new"]
    assert left[0]["lists_purged_at"] is None and out["unattached"] >= 1
