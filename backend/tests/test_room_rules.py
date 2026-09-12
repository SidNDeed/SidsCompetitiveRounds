"""Room rules (Sept 10 batch — ai-collab/sept10-batch/01-room-rules.md).

Friendly fire (a host toggle on 2v2 / 1v2 lobbies) and Same Cards (every
mode: 1v1 by BOTH players' preference, hosted modes by the host) are frozen
on the room's record ``{ff, sc, src}`` when the room is issued, stamped as the
Photon property ``cr_rules`` from ONE producer, served only to a request at
or above ROOM_RULES_MIN_VERSION when non-default, inherited by continuations
of the same sitting, and carried into every history surface.

Three kinds of test, in the style of test_queue_pair_writers.py:
  * pure helpers (normalise / canonical JSON / prop / payload / admission /
    the queue-side AND);
  * EXECUTED async helpers against fake sessions (member read, the ledger
    read with room-name candidates and pair binding, the spectated-room
    read keyed by the attest mode literals);
  * source-shape oracles with EXACT counts (#391: a floor is decoration), so
    a series mint that stops carrying the record, a continuation that stops
    inheriting it, or a history surface that stops reporting it fails here
    rather than storing NULL / showing nothing in production.
"""

import asyncio
import inspect
import json
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

import main

ME = UUID("11111111-1111-1111-1111-111111111111")
PARTNER = UUID("22222222-2222-2222-2222-222222222222")
FLOOR = main.ROOM_RULES_MIN_VERSION
OLD = "1.40.3"
DEFAULT_PROP = "ff=1;sc=0"

MAIN_SRC = inspect.getsource(main)
BOT_SRC = (Path(__file__).resolve().parents[1] / "discord_bot.py").read_text(encoding="utf-8")
TOURN_SRC = (Path(__file__).resolve().parents[1] / "api" / "tournaments.py").read_text(encoding="utf-8")


def _run(coro):
    return asyncio.run(coro)


def _request(version):
    """A request the version_gate middleware has already annotated."""
    return SimpleNamespace(state=SimpleNamespace(mod_version=version))


def _src(fn_name):
    return inspect.getsource(getattr(main, fn_name))


# ── pure helpers ─────────────────────────────────────────────────────────


def test_normalize_takes_only_booleans_and_known_provenance():
    assert main._rules_normalize(None) == {"ff": True, "sc": False}
    assert main._rules_normalize('{"ff": false, "sc": true, "src": "lobby"}') == {
        "ff": False, "sc": True, "src": "lobby"}
    assert main._rules_normalize(b'{"ff": false}') == {"ff": False, "sc": False}
    # non-boolean values fall to the defaults, never to truthiness
    assert main._rules_normalize({"ff": 0, "sc": "yes"}) == {"ff": True, "sc": False}
    assert main._rules_normalize("not json") == {"ff": True, "sc": False}
    # provenance is a closed set
    assert "src" not in main._rules_normalize({"ff": True, "sc": True, "src": "client"})


def test_canonical_json_is_key_sorted_and_carries_provenance_only_when_known():
    assert main._rules_json({"sc": True, "ff": False, "src": "queue"}) == '{"ff":false,"sc":true,"src":"queue"}'
    assert main._rules_json({"ff": True, "sc": False}) == '{"ff":true,"sc":false}'
    assert main._rules_json(None) == '{"ff":true,"sc":false}'
    assert json.loads(main._rules_json({"ff": False})) == {"ff": False, "sc": False}


def test_prop_string_has_fixed_order_and_one_producer():
    assert main._rules_prop(None) == DEFAULT_PROP
    assert main._rules_prop({"ff": False, "sc": True, "src": "lobby"}) == "ff=0;sc=1"
    assert main._rules_prop({"ff": True, "sc": True}) == "ff=1;sc=1"
    # ONE f-string builds it, and every emission of rules_prop calls it.
    assert MAIN_SRC.count("f\"ff={1 if") == 1
    emits = re.findall(r'(?:rules_prop=|"rules_prop":|\["rules_prop"\]\s*=)\s*(\S+)', MAIN_SRC)
    assert emits, "no rules_prop emission found"
    assert all(e.startswith("_rules_prop(") for e in emits), emits
    # 1v1 poll (two branches) + 1v1 ready + 2v2 poll + lobby resolve +
    # 1v2 locked payload + 1v2 lobby start + spectate grant + the two
    # continuations. A new emission must call the producer AND bump this.
    assert len(emits) == 10, emits


def test_nondefault_ignores_provenance():
    assert main._rules_nondefault(None) is False
    assert main._rules_nondefault({"ff": True, "sc": False, "src": "lobby"}) is False
    assert main._rules_nondefault({"ff": False, "sc": False}) is True
    assert main._rules_nondefault({"ff": True, "sc": True}) is True


def test_payload_provenance_precedence():
    assert main._rules_payload({"ff": True, "sc": True}, "lobby") == {"ff": True, "sc": True, "src": "lobby"}
    assert main._rules_payload({"ff": False, "sc": False, "src": "lobby"}) == {"ff": False, "sc": False, "src": "lobby"}
    assert main._rules_payload(None) == {"ff": True, "sc": False, "src": "queue"}


def test_version_floor_fails_closed():
    for bad in (None, "", "garbage", OLD, "1.40.99", "0"):
        assert main._mod_version_at_least(bad, FLOOR) is False, bad
    for ok in (FLOOR, "1.41.1", "1.42.0", "2.0.0"):
        assert main._mod_version_at_least(ok, FLOOR) is True, ok


def test_admission_refuses_only_nondefault_rooms_to_old_requests():
    nondefault = {"ff": False, "sc": False}
    # default rules: never refused, whatever the header (or its absence)
    for v in (None, OLD, FLOOR):
        main._rules_admit(_request(v), main.ROOM_RULES_DEFAULT)
        main._rules_admit(_request(v), None)
    main._rules_admit(_request(FLOOR), nondefault)
    main._rules_admit(_request("1.41.2"), nondefault)
    for v in (None, OLD, "garbage"):
        with pytest.raises(HTTPException) as ei:
            main._rules_admit(_request(v), nondefault)
        assert ei.value.status_code == 409 and ei.value.detail == "rules_unsupported"
    with pytest.raises(HTTPException):
        main._rules_admit(None, {"ff": True, "sc": True})


def test_queue_match_is_the_and_of_every_preference_and_every_row_version():
    assert main._rules_for_queue_match([True, True], [FLOOR, FLOOR]) == {"ff": True, "sc": True, "src": "queue"}
    # friendly fire is fixed ON for queue-matched rooms (answer C)
    assert main._rules_for_queue_match([False, True], [FLOOR, FLOOR])["ff"] is True
    assert main._rules_for_queue_match([False, True], [FLOOR, FLOOR])["sc"] is False
    assert main._rules_for_queue_match([True, True], [FLOOR, OLD])["sc"] is False
    assert main._rules_for_queue_match([True, True], [FLOOR, None])["sc"] is False
    assert main._rules_for_queue_match([], [])["sc"] is False
    assert main._rules_for_queue_match([True], [])["sc"] is False


def test_lobby_row_rules_are_host_decided_with_lobby_provenance():
    assert main._rules_from_lobby_row({"friendly_fire": False, "same_cards": True}) == {
        "ff": False, "sc": True, "src": "lobby"}
    assert main._rules_from_lobby_row({"id": 1}) == {"ff": True, "sc": False, "src": "lobby"}


def test_history_record_distinguishes_unknown_from_default():
    assert main._rules_history(None) is None
    assert main._rules_history('{"ff":true,"sc":false,"src":"queue"}') == {"ff": True, "sc": False}
    assert main._rules_history({"ff": False, "sc": False}) == {"ff": False, "sc": False}
    assert main._rules_history({"ff": True, "sc": True}, True) == {"ff": True, "sc": True, "xp": True}
    assert main._rules_history({"ff": True, "sc": False}, False) == {"ff": True, "sc": False, "xp": False}
    # provenance is not a rule and does not reach the history row
    assert "src" not in main._rules_history({"ff": True, "sc": False, "src": "lobby"})


def test_ffa_settings_block_reports_unknown_rather_than_a_plausible_default():
    full = {"score_target": 7, "card_cap": 5, "initial_picks": 1, "card_candidates": 5,
            "same_card_rule": True, "sudden_death": False, "settings_known": True}
    assert main._ffa_settings_block(full) == {
        "score_target": 7, "card_cap": 5, "initial_picks": 1, "card_candidates": 5,
        "same_card_rule": True, "sudden_death": False}
    assert main._ffa_settings_block(dict(full, settings_known=False)) is None
    assert main._ffa_settings_block(dict(full, score_target=None)) is None
    # every FFA history surface projects the same column list: three through
    # the shared fragment, ffa_recent through the inline list it always had
    assert MAIN_SRC.count("{_FFA_SETTINGS_COLS}") == 4
    assert _src("ffa_recent").count("l.same_card_rule, l.sudden_death, l.settings_known") == 1


# ── executed async helpers ───────────────────────────────────────────────


class _Res:
    def __init__(self, rows):
        self._rows = list(rows or [])

    def mappings(self):
        return self

    def fetchall(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    """Records every statement; answers from a callable(sql, params) -> rows."""

    def __init__(self, answer=None):
        self.calls = []
        self._answer = answer or (lambda sql, params: [])

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append((sql, params))
        return _Res(self._answer(sql, params))


def test_member_read_uses_the_rows_own_version_never_players():
    db = FakeSession(lambda sql, p: [{"player_id": ME, "pref": True, "mv": FLOOR}])
    out = _run(main._rules_members(db, [ME, str(PARTNER)], "ranked_queue"))
    assert out == {str(ME): (True, FLOOR), str(PARTNER): (False, None)}
    sql, params = db.calls[0]
    assert "FROM ranked_queue q" in sql
    assert "q.mod_version AS mv" in sql
    assert "ANY(CAST(:ids AS uuid[]))" in sql
    assert all(isinstance(x, UUID) for x in params["ids"])
    assert "players.mod_version" not in sql and "p.mod_version" not in sql
    with pytest.raises(ValueError):
        _run(main._rules_members(db, [ME], "players"))
    # an empty roster never queries and never votes yes
    db2 = FakeSession()
    assert _run(main._rules_members(db2, [], "team_queue")) == {}
    assert db2.calls == []


def test_roster_rules_judge_the_caller_by_this_requests_header():
    rows = [{"player_id": ME, "pref": True, "mv": OLD},        # my row lags one poll
            {"player_id": PARTNER, "pref": True, "mv": FLOOR}]
    db = FakeSession(lambda sql, p: rows)
    with_header = _run(main._rules_for_members(db, [ME, PARTNER], "ranked_queue",
                                               request=_request(FLOOR), my_pid=ME))
    assert with_header == {"ff": True, "sc": True, "src": "queue"}
    no_header = _run(main._rules_for_members(db, [ME, PARTNER], "ranked_queue"))
    assert no_header["sc"] is False
    # the header only ever speaks for MY seat
    other = _run(main._rules_for_members(db, [ME, PARTNER], "ranked_queue",
                                         request=_request(FLOOR), my_pid=PARTNER))
    assert other["sc"] is False


def test_ledger_read_tries_both_room_names_and_binds_the_pair():
    db = FakeSession(lambda sql, p: [('{"ff":true,"sc":true,"src":"queue"}',)])
    out = _run(main._rules_from_room_ledger(db, "ranked_abc_123456_r2", ME, PARTNER))
    assert out == {"ff": True, "sc": True, "src": "queue"}
    sql, params = db.calls[0]
    assert "FROM issued_room_regions" in sql
    assert "(room_name = :room_full OR room_name = :room_base)" in sql
    assert params["room_full"] == "ranked_abc_123456_r2"
    assert params["room_base"] == "ranked_abc"
    assert "player1_id = :pa AND player2_id = :pb" in sql
    assert "player1_id = :pb AND player2_id = :pa" in sql
    assert params["pa"] == ME and params["pb"] == PARTNER
    assert "ORDER BY issued_at DESC LIMIT 1" in sql
    # without a pair there is no pair predicate (and no dangling bind)
    db2 = FakeSession(lambda sql, p: [])
    assert _run(main._rules_from_room_ledger(db2, "ranked_abc")) is None
    sql2, params2 = db2.calls[0]
    assert "player1_id" not in sql2 and "pa" not in params2
    assert params2["room_full"] == params2["room_base"] == "ranked_abc"
    # no room, no query; a row with no record is unknown, not default
    db3 = FakeSession()
    assert _run(main._rules_from_room_ledger(db3, "", ME, PARTNER)) is None
    assert db3.calls == []
    db4 = FakeSession(lambda sql, p: [(None,)])
    assert _run(main._rules_from_room_ledger(db4, "ranked_abc", ME, PARTNER)) is None


def test_spectated_room_rules_are_keyed_by_the_attest_mode_literals():
    assert set(main._SPECTATE_MODES) == {"1v1", "2v2", "1v2", "ffa"}
    for mode, table in (("2v2", "team_series"), ("1v2", "ovt_series")):
        db = FakeSession(lambda sql, p: [('{"ff":false,"sc":false,"src":"lobby"}',)])
        out = _run(main._rules_for_spectated_room(db, mode, "room-x"))
        assert out == {"ff": False, "sc": False, "src": "lobby"}, mode
        sql, params = db.calls[0]
        assert f"FROM {table} WHERE photon_room_id = :room" in sql
        assert "ORDER BY created_at DESC LIMIT 1" in sql
        assert params == {"room": "room-x"}
    # a 1v1 queue room's record is on the issuance ledger
    db = FakeSession(lambda sql, p: [('{"ff":true,"sc":true}',)])
    assert _run(main._rules_for_spectated_room(db, "1v1", "ranked_abc"))["sc"] is True
    assert "FROM issued_room_regions" in db.calls[0][0]
    # FFA settings live on the FFA lobby; the old internal literals answer nothing
    for mode in ("ffa", "team", "ovt", ""):
        db = FakeSession()
        assert _run(main._rules_for_spectated_room(db, mode, "room-x")) is None, mode
        assert db.calls == [], mode
    db = FakeSession()
    assert _run(main._rules_for_spectated_room(db, "2v2", "")) is None
    assert db.calls == []


# ── source-shape oracles ─────────────────────────────────────────────────


def _blocks(src, opener):
    """Every occurrence of `opener` with the text up to its VALUES clause."""
    out = []
    for m in re.finditer(re.escape(opener), src):
        tail = src[m.end():m.end() + 400]
        cut = tail.find("VALUES")
        assert cut > 0, f"no VALUES after {opener} at {m.start()}"
        out.append(tail[:cut])
    return out


def test_every_series_mint_carries_the_record():
    team = _blocks(MAIN_SRC, "INSERT INTO team_series (")
    ovt = _blocks(MAIN_SRC, "INSERT INTO ovt_series (")
    assert len(team) == 3 and len(ovt) == 3, (len(team), len(ovt))
    assert all("rules" in b for b in team + ovt)
    # ORM mints (queue poll / ready / late report / preflight) pass rules=
    mints = [m.start() for m in re.finditer(r"\bRankedSeries\(", MAIN_SRC)]
    assert len(mints) == 4, len(mints)
    for at in mints:
        assert "rules=" in MAIN_SRC[at:at + 700], MAIN_SRC[at:at + 120]
    # fallback mints bind the ledger read to the pair (r1 HIGH)
    assert MAIN_SRC.count("_rules_from_room_ledger(db, report.photon_room_id, p1.id, p2.id)") == 1
    assert MAIN_SRC.count("_rules_from_room_ledger(db, room_id, p1.id, p2.id)") == 1
    # a bracket-formed room plays the defaults and its history says so
    assert TOURN_SRC.count("series.rules = dict(ROOM_RULES_DEFAULT)") == 1


def test_continuations_inherit_the_priors_record():
    for fn in ("team_series_continuation", "ovt_series_continuation"):
        s = _src(fn)
        assert s.count("photon_room_id, rules") == 1, fn
        assert s.count("CAST(:rules AS JSONB)") == 1, fn
        assert s.count('_c_rules = _rules_normalize(prior["rules"])') == 1, fn
        assert s.count('"rules": _rules_json(_c_rules)') == 1, fn
        assert s.count('"rules_prop": _rules_prop(_c_rules)') == 1, fn


def test_lobby_gates_and_settings_write():
    start = _src("_lobby_start_common")
    assert start.count('"rules_need_update"') == 1
    assert start.count('"settings_unseen"') == 1
    settings = _src("_lobby_settings_impl")
    assert settings.count("settings_version = settings_version + 1") == 1
    assert settings.count('"rules_unsupported"') == 1
    assert settings.count('"rules_need_update"') == 1
    join = _src("_lobby_join_impl")
    assert join.count('"rules_unsupported"') == 1
    state = _src("_lobby_state_impl")
    assert state.count("LEAST(CAST(:seen AS INTEGER), CAST(:cur AS INTEGER))") == 1
    # a1 M4: the ack never moves backwards.
    assert state.count("GREATEST(seen_settings_version,") == 1
    # a1 H3 + M2: actor HMAC, verified session, mandatory always-compared fence.
    assert settings.count("lobby_settings:{req.steam_id}:{req.expected_lobby_id}:{_ff_tok}:{_sc_tok}") == 1
    assert settings.count('"session_required"') == 1
    assert settings.count("if req.expected_lobby_id:") == 0
    assert settings.count("str(lobby_id) != _exp_lid") == 1
    # a1 M3: only a value set in the non-default direction is floor-gated.
    assert settings.count("if req.friendly_fire is False or req.same_cards is True:") == 1
    assert settings.count("_rules_nondefault(new_rules)") == 0
    # a1 L1: the echo is bounded before the INTEGER cast (both lobby state routes).
    assert MAIN_SRC.count("seen_settings_version: int = Query(0, ge=0, le=2147483647)") == 2
    paths = {r.path for r in main.app.routes}
    for p in ("/api/v1/team/lobby/settings", "/api/v1/ovt/lobby/settings",
              "/api/v1/players/{steam_id}/pref-same-cards"):
        assert p in paths, p
    pref = _src("set_pref_same_cards")
    assert "pref_same_cards:" in pref and '"session_required"' in pref


def test_a1_issuance_relock_and_grant_shapes():
    # The 1v1 issuance paths: both authoritative SELECTs carry rq.rules (a1
    # H2), a resumed series keeps its record and NULL is never backfilled
    # (a1 H4), ready refreshes the member version (a1 M1); the 2v2 relock
    # re-stamps the series' own record and issuance writes only a carried
    # record (a1 H5); the spectate grant judges the per-game floor before
    # disclosure (a1 H1); the set report carries the record (a1 M5).
    assert MAIN_SRC.count("rq.region_pings, rq.region_pings_at, rq.rules") == 2
    assert MAIN_SRC.count("rq.region_pings, rq.region_pings_at\n") == 0
    assert MAIN_SRC.count("series.rules = rules") == 0
    for fn in ("queue_poll", "queue_ready"):
        body = _src(fn)
        assert body.count("_rules_normalize(series.rules)" if fn == "queue_poll"
                          else "_rules_normalize(existing_series.rules)") == 1, fn
        assert body.count("_rules_for_members(") == 1, fn
    assert _src("queue_ready").count("SET ready = true, mod_version = :mv") == 1
    relock = _src("_team_relock_existing_series")
    assert relock.count("rules = CAST(:rules AS JSONB)") == 1
    assert relock.count('_rules_json(srow["rules"]) if srow["rules"] is not None else None') == 1
    fam = _src("_team_lock_family_pick")   # the locked family row the relock receives as srow
    assert fam.count("ts.rules,") == 1
    assert MAIN_SRC.count("CAST(:has_rules AS BOOLEAN)") == 1
    assert MAIN_SRC.count('"has_rules": me["rules"] is not None') == 1
    grant = _src("spectate_grant")
    assert grant.count('max(int(game["protocol_min"] or 1), SPECTATE_PROTOCOL)') == 1
    assert grant.index("_game_floor") < grant.index("token = secrets.token_urlsafe(24)")
    assert grant.count('"proto": SPECTATE_PROTOCOL}') == 0
    assert grant.count("min(int(req.client_protocol), 32767)") == 1
    # The record rides the ONE games statement per set (the report tests pin
    # the statement count), never a second lookup.
    assert MAIN_SRC.count("_report_rules_by_game") == 0
    for fn, needle in (("_report_load_1v1", '"rules": _rules_history(r["rules"])'),
                       ("_report_load_team", '"rules": _rules_history(r["rules"])'),
                       ("_report_load_ovt", '"rules": _rules_history(r["rules"], r["solo_extra_pick"])'),
                       ("_report_load_ffa", '"settings": _ffa_settings_block(r)')):
        assert _src(fn).count(needle) == 1, fn
    assert _src("_report_game_json").count('for _k in ("rules", "settings"):') == 1
    for sql, join in ((main._REPORT_1V1_SQL, "LEFT JOIN ranked_series rs ON rs.id = m.series_id"),
                      (main._REPORT_TEAM_SQL, "LEFT JOIN team_series ts ON ts.id = tm.series_id"),
                      (main._REPORT_OVT_SQL, "LEFT JOIN ovt_series os ON os.id = om.series_id"),
                      (main._REPORT_FFA_SQL, "LEFT JOIN ffa_lobbies l ON l.id = fm.lobby_id")):
        assert sql.count(join) == 1, join
    assert main._REPORT_FFA_SQL.count("l.settings_known") == 1
    assert "pref_same_cards=bool(player.pref_same_cards)" in MAIN_SRC


def test_every_history_surface_reports_the_record():
    expect = {
        "get_player_matches": (1, 0),
        "get_recent_series": (1, 0),
        "get_recent_multimode_series": (2, 1),
        "get_match_by_code": (3, 1),
        "player_ffa_history": (0, 1),
        "player_team_history": (1, 0),
        "player_ovt_history": (1, 0),
        "get_player_team_matches": (1, 0),
        "team_series_recent": (1, 0),
        "team_all_series_paged": (1, 0),
        "ffa_recent": (0, 1),
        "ovt_recent": (1, 0),
    }
    for fn, (rules_n, ffa_n) in expect.items():
        s = _src(fn)
        assert s.count("_rules_history(") == rules_n, (fn, s.count("_rules_history("))
        assert s.count("_ffa_settings_block(") == ffa_n, (fn, s.count("_ffa_settings_block("))
    # the 1v2 surfaces carry the solo extra pick as part of the record
    for fn in ("get_match_by_code", "get_recent_multimode_series", "player_ovt_history", "ovt_recent"):
        assert "solo_extra_pick" in _src(fn), fn


def test_spectate_floor_and_grant():
    assert main.SPECTATE_PROTOCOL == 2
    assert main.SPECTATE_PROTOCOL_FF_OFF == 3
    attest = _src("spectate_participant_attest")
    assert attest.count("_rules_for_spectated_room(db, req.mode, req.room_name)") == 1
    assert attest.count("GREATEST(protocol_min, :p)") == 1
    grant = _src("spectate_grant")
    assert grant.count('_rules_for_spectated_room(db, game["mode"], game["room_name"])') == 1
    assert grant.count('"rules_prop": _rules_prop(_g_rules)') == 1


# ── Discord feed rendering (helpers exec'd from source: the bot module needs
#    a token to import) ───────────────────────────────────────────────────


def _bot_helper(name):
    m = re.search(rf"^def {name}\(.*?(?=^(?:async )?def |\Z)", BOT_SRC, re.S | re.M)
    assert m, name
    ns = {}
    exec(m.group(0), ns)
    return ns[name]


def test_bot_rules_line_names_only_the_nondefaults():
    f = _bot_helper("_rules_summary")
    assert f(None) == ""
    assert f({"ff": True, "sc": False}) == ""
    assert f({"ff": False, "sc": False}) == "Friendly fire off"
    assert f({"ff": True, "sc": True, "xp": True}) == "Same cards · Solo extra pick"
    assert f({"ff": False, "sc": True}) == "Friendly fire off · Same cards"
    for fn in ("log_series_result", "log_team_series_result", "cmd_game"):
        body = re.search(rf"^async def {fn}\(.*?(?=^(?:async )?def )", BOT_SRC, re.S | re.M).group(0)
        assert body.count("_rules_summary(") == 1, fn


def test_bot_ffa_settings_line_uses_the_in_game_labels():
    f = _bot_helper("_ffa_settings_summary")
    assert f(None) == ""
    assert f({"score_target": None}) == ""
    # a1 L2: deviations from the canonical configuration only, like the
    # in-game FFA rows — an all-default block is no line at all.
    assert f({"score_target": 7, "card_cap": 5, "initial_picks": 1, "card_candidates": 5,
              "same_card_rule": True, "sudden_death": False}) == "First to 7 · Same cards"
    assert f({"score_target": 5, "card_cap": 5, "initial_picks": 1, "card_candidates": 5,
              "same_card_rule": False, "sudden_death": False}) == ""
    assert f({"score_target": 5, "card_cap": 3, "initial_picks": 2, "card_candidates": 4,
              "same_card_rule": False, "sudden_death": False}) == (
        "Max cards 3 · Opening draws 2 · Card draw 4")
    assert f({"score_target": 3, "sudden_death": True}) == "First to 3 · Sudden death"
    for fn in ("log_ffa_match_result", "cmd_game"):
        body = re.search(rf"^async def {fn}\(.*?(?=^(?:async )?def )", BOT_SRC, re.S | re.M).group(0)
        assert body.count("_ffa_settings_summary(") == 1, fn
