"""FFA history reads the settings a game was RECORDED under (item 22, migration 360).

Every FFA history surface used to read its settings block (the same-card rule
among them) live off the lobby row. The transaction that records a game now
freezes the block into the game's own row, ffa_matches.settings_frozen, and
_ffa_settings_block reads it from there; a game recorded before 360 carries
NULL and reads the lobby row, exactly as every game did before.

The live half rides test_ffa_game_number_anchor.py's gate and settlement
fixture: FFA_TEST_PG_DSN names a throwaway database, and without it these
checks FAIL, naming the variable (FFA_TEST_PG_OPTOUT=1 turns them into named
skips). The report is settled through submit_ffa_match itself, migration 360
is applied from its file (twice), the lobby's live settings are changed after
the game, and the history must still answer with the settings the game was
played under.
"""
import inspect
import json
import os
import pathlib
import re
import sys

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import main  # noqa: E402
from test_ffa_game_number_anchor import (  # noqa: E402  (one settlement harness, not two)
    LOBBY, ROW_B, S1, _call_endpoint, _endpoint_report, _raw_pg,
    _settling_fixture, require_pg, run)

MIGRATION = pathlib.Path(__file__).resolve().parents[1] / "sql" / "360_ffa_settings_frozen.sql"

# What the lobby said while the game was played, and what it says afterwards.
# Every key but sudden_death differs (the server only ever writes that one
# FALSE), so a reader that takes ANY of the other five from the lobby row
# instead of the frozen block answers differently from PLAYED.
PLAYED = {"score_target": 5, "card_cap": 5, "initial_picks": 1, "card_candidates": 5,
          "same_card_rule": True, "sudden_death": False}
LATER = {"score_target": 7, "card_cap": 6, "initial_picks": 2, "card_candidates": 4,
         "same_card_rule": False, "sudden_death": False}


def _row(frozen, live=None, known=True):
    r = dict(LATER if live is None else live, settings_known=known)
    r["settings_frozen"] = frozen
    return r


def _src(name):
    return inspect.getsource(getattr(main, name))


# -- the one definition every surface calls ------------------------------------


def test_the_block_is_the_one_the_game_froze_not_the_lobbys_current_row():
    assert all(PLAYED[k] != LATER[k] for k in PLAYED if k != "sudden_death")
    assert main._ffa_settings_block(_row(json.dumps(PLAYED))) == PLAYED
    # a driver whose jsonb codec already decodes hands over a dict
    assert main._ffa_settings_block(_row(dict(PLAYED))) == PLAYED
    # each boolean both ways, against a lobby row that says the opposite
    for key in ("same_card_rule", "sudden_death"):
        for value in (True, False):
            frozen = dict(PLAYED, **{key: value})
            got = main._ffa_settings_block(_row(json.dumps(frozen), live=dict(LATER, **{key: not value})))
            assert got[key] is value, (key, value)


def test_a_game_recorded_before_360_reads_the_lobby_row():
    assert main._ffa_settings_block(_row(None)) == LATER
    # ...with the lobby rule unchanged: unknown settings stay unknown
    assert main._ffa_settings_block(_row(None, known=False)) is None
    assert main._ffa_settings_block(_row(None, live=dict(LATER, score_target=None))) is None


@pytest.mark.parametrize("bad", [
    "not json", "[1, 2]", '"text"', "7", "null",
    json.dumps({k: v for k, v in PLAYED.items() if k != "same_card_rule"}),
    json.dumps(dict(PLAYED, extra=1)),
    json.dumps(dict(PLAYED, score_target=True)),
    json.dumps(dict(PLAYED, same_card_rule=1)),
    json.dumps(dict(PLAYED, card_cap="5")),
    json.dumps(dict(PLAYED, card_cap=5.0)),
    json.dumps(dict(PLAYED, sudden_death=None)),
])
def test_a_non_null_block_that_is_not_the_six_keys_at_their_types_reads_unknown_not_the_lobby_row(bad):
    """Round 2 (L1): only a NULL column is a legacy row that reads the lobby;
    a game that froze SOMETHING malformed is unknown, never the lobby's later
    values (LATER here is a known, valid lobby row)."""
    assert main._ffa_settings_frozen(bad) is None
    assert main._ffa_settings_block(_row(bad)) is None


def test_an_empty_frozen_object_reads_unknown_while_null_still_reads_the_lobby():
    assert main._ffa_settings_block(_row("{}")) is None
    assert main._ffa_settings_block(_row({})) is None           # a decoding driver's dict
    assert main._ffa_settings_block(_row(None)) == LATER        # the legacy fallback stays


def test_no_other_reader_falls_back_to_the_lobby_row():
    """The lobby read (_ffa_settings_live) has exactly two callers: the block's
    NULL branch and the writer's freeze; every history surface goes through
    the block."""
    import re as _re
    src = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    calls = [m.start() for m in _re.finditer(r"\b_ffa_settings_live\(", src)]
    defs = [m.start() for m in _re.finditer(r"^def _ffa_settings_live\(", src, _re.M)]
    assert len(defs) == 1 and len(calls) == 3, (len(defs), len(calls))
    block = _src("_ffa_settings_block")
    assert block.count("_ffa_settings_live(row)") == 1
    assert "if raw is None:" in block and block.index("if raw is None:") < block.index("_ffa_settings_live(row)")
    assert "_ffa_settings_live(" in _src("_ffa_settings_to_freeze")


def test_the_row_must_carry_the_frozen_column():
    """A surface that forgets to select settings_frozen is a KeyError, not a
    silent fall back to the lobby row that would pass every other check."""
    with pytest.raises(KeyError):
        main._ffa_settings_block(dict(LATER, settings_known=True))


def test_the_writer_freezes_exactly_what_the_lobby_row_reads_and_null_when_unknown():
    lobby = dict(PLAYED, settings_known=True, games_played=1, status="active")
    raw = main._ffa_settings_to_freeze(lobby)
    assert isinstance(raw, str)
    assert json.loads(raw) == PLAYED
    assert main._ffa_settings_frozen(raw) == main._ffa_settings_live(lobby) == PLAYED
    assert main._ffa_settings_to_freeze(dict(lobby, settings_known=False)) is None
    assert main._ffa_settings_to_freeze(dict(lobby, score_target=None)) is None
    # a lobby row without the settings columns freezes NULL instead of
    # refusing the report
    assert main._ffa_settings_to_freeze({"games_played": 1, "status": "active"}) is None


def test_every_ffa_history_surface_selects_the_frozen_block():
    for fn in ("get_match_by_code", "get_recent_multimode_series", "ffa_recent",
               "player_ffa_history"):
        s = _src(fn)
        assert s.count("m.settings_frozen") == 1, fn
        assert s.count("_ffa_settings_block(") == 1, fn
    # The session report's two FFA statements (one game, the lobby sitting)
    # both feed _report_ffa_games, the one place the report builds the block.
    assert main._REPORT_FFA_SQL.count("fm.settings_frozen") == 1
    assert main._REPORT_FFA_LOBBY_SQL.count("fm.settings_frozen") == 1
    assert _src("_report_ffa_games").count("_ffa_settings_block(r)") == 1
    assert _src("_report_load_ffa").count("_report_ffa_games(") == 1
    assert _src("_report_load_ffa_lobby").count("_report_ffa_games(") == 1
    # one reader of the column: the block helper (definition + one call)
    assert inspect.getsource(main).count("_ffa_settings_frozen(") == 2


def test_the_insert_that_records_a_game_freezes_the_block():
    src = _src("submit_ffa_match")
    ins = src.index("INSERT INTO ffa_matches")
    assert "settings_frozen" in src[ins:src.index("VALUES", ins)]
    assert src.count("CAST(:sfz AS jsonb)") == 1
    assert src.count('"sfz": _ffa_settings_to_freeze(lobby),') == 1
    # from the row the lobby lock returned, the one the score target is read off
    assert src.index("lobby, _expected_game = await _ffa_lock_lobby_slot(") < ins
    assert src.index("_cfg = _ffa_lobby_config(lobby)") < ins


def test_migration_360_is_additive_idempotent_and_deploys_first():
    sql = MIGRATION.read_text(encoding="ascii")
    code = "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))
    assert "ADD COLUMN IF NOT EXISTS settings_frozen JSONB" in code
    assert code.count("BEGIN;") == 1 and code.count("COMMIT;") == 1
    assert code.index("BEGIN;") < code.index("ALTER TABLE") < code.index("COMMIT;")
    assert "DEPLOY ORDER (#477): THIS FILE FIRST" in sql
    for word in ("UPDATE ", "DELETE ", "DROP ", "TRUNCATE "):
        assert word not in code, word


def test_the_live_checks_here_carry_no_skip_mark():
    mod = sys.modules[__name__]
    names = [n for n in dir(mod) if n.startswith("test_pg_")]
    assert len(names) == 3   # round 2 added the five-surface malformed-block check
    for name in names:
        marks = {m.name for m in getattr(getattr(mod, name), "pytestmark", [])}
        assert "skip" not in marks and "skipif" not in marks, name


# -- live PostgreSQL -------------------------------------------------------------

# The lobby columns 176/186/193 declare, at their declared types, on top of the
# anchor file's settlement fixture; display_name is what the history's
# participant list reads. The fixture's own settings_frozen (declared there so
# its settlements can INSERT) is dropped, so that migration 360 declares the
# column here, CHECK included.
_LOBBY_SETTINGS = """
ALTER TABLE ffa_lobbies
    ADD COLUMN IF NOT EXISTS score_target SMALLINT NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS card_candidates SMALLINT NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS initial_picks SMALLINT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS card_cap SMALLINT NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS same_card_rule BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS sudden_death BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS settings_known BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE players ADD COLUMN IF NOT EXISTS display_name VARCHAR(64);
ALTER TABLE ffa_matches DROP COLUMN IF EXISTS settings_frozen
"""

_SET_LOBBY = ("UPDATE ffa_lobbies SET score_target = :st, card_cap = :cap,"
              " initial_picks = :ip, card_candidates = :cc, same_card_rule = :scr,"
              " sudden_death = :sd WHERE id = :l")


def _lobby_params(s):
    return {"st": s["score_target"], "cap": s["card_cap"], "ip": s["initial_picks"],
            "cc": s["card_candidates"], "scr": s["same_card_rule"],
            "sd": s["sudden_death"], "l": LOBBY}


def _as_dict(v):
    return v if isinstance(v, dict) or v is None else json.loads(v)


async def _fixture_with_360():
    engine, sm, pids, game1 = await _settling_fixture(
        games_played=1, recorded_number=1, recorded_room="rm_211531_r1")
    async with engine.begin() as conn:
        for stmt in [s for s in _LOBBY_SETTINGS.split(";") if s.strip()]:
            await conn.execute(text(stmt))
    raw = await _raw_pg()
    try:
        sql = MIGRATION.read_text(encoding="ascii")
        await raw.execute(sql)
        await raw.execute(sql)        # the re-run the file claims is a no-op
    finally:
        await raw.close()
    return engine, sm, pids, game1


def test_pg_migration_360_declares_one_nullable_jsonb_object_column():
    require_pg()

    async def go():
        engine, sm, pids, game1 = await _fixture_with_360()
        raw = await _raw_pg()
        try:
            col = await raw.fetchrow(
                "SELECT data_type, is_nullable FROM information_schema.columns"
                " WHERE table_schema = current_schema() AND table_name = 'ffa_matches'"
                "   AND column_name = 'settings_frozen'")
            checks = await raw.fetch(
                "SELECT pg_get_constraintdef(oid) AS d FROM pg_constraint"
                " WHERE conrelid = 'ffa_matches'::regclass AND contype = 'c'"
                "   AND pg_get_constraintdef(oid) LIKE '%settings_frozen%'")
            outcomes = {}
            for label, value in (("object", '{"a": 1}'), ("null", None),
                                 ("array", "[1]"), ("string", '"x"'), ("number", "5")):
                tr = raw.transaction()
                await tr.start()
                try:
                    await raw.execute(
                        "INSERT INTO ffa_matches (id, photon_room_id, ended_at, settings_frozen)"
                        " VALUES (gen_random_uuid(), $1, NOW(), CAST($2 AS jsonb))",
                        "chk_" + label, value)
                    outcomes[label] = "accepted"
                except Exception as ex:  # noqa: BLE001 - the class is the point
                    outcomes[label] = type(ex).__name__
                finally:
                    await tr.rollback()
            return col, [c["d"] for c in checks], outcomes
        finally:
            await raw.close()
            await engine.dispose()

    col, checks, outcomes = run(go())
    assert col is not None, "migration 360 did not add settings_frozen"
    assert (col["data_type"], col["is_nullable"]) == ("jsonb", "YES")
    assert len(checks) == 1, checks          # two applications, one CHECK
    assert outcomes["object"] == "accepted" and outcomes["null"] == "accepted"
    for label in ("array", "string", "number"):
        assert outcomes[label] == "CheckViolationError", (label, outcomes[label])


def test_pg_the_history_answers_with_the_settings_the_game_was_played_under():
    """The report settles through submit_ffa_match while the lobby says
    PLAYED; the lobby row then says LATER. The game's history rows (the
    player's FFA history and the set report's FFA loader) must still say
    PLAYED, and the game the fixture recorded without the column (a pre-360
    row) must say LATER, the lobby row it falls back to."""
    require_pg()

    async def go():
        engine, sm, pids, game1 = await _fixture_with_360()
        try:
            async with engine.begin() as conn:
                await conn.execute(text(_SET_LOBBY), _lobby_params(PLAYED))
            resp = await _call_endpoint(sm, _endpoint_report(
                ROW_B, S1, "rm_211531_r2", with_slots=True))
            async with sm() as db:
                stored = (await db.execute(text(
                    "SELECT settings_frozen, game_number FROM ffa_matches WHERE id = :m"),
                    {"m": resp.match_id})).mappings().first()
                old_stored = (await db.execute(text(
                    "SELECT settings_frozen FROM ffa_matches WHERE id = :m"),
                    {"m": game1})).scalar()
            async with engine.begin() as conn:
                await conn.execute(text(_SET_LOBBY), _lobby_params(LATER))
            async with sm() as db:
                live_rule = (await db.execute(text(
                    "SELECT same_card_rule FROM ffa_lobbies WHERE id = :l"),
                    {"l": LOBBY})).scalar()
                hist = await main.player_ffa_history(S1, 15, db)
                rep, _slots = await main._report_load_ffa(
                    db, str(resp.match_id), str(pids[S1]))
            return resp, game1, stored, old_stored, live_rule, hist, rep
        finally:
            await engine.dispose()

    resp, game1, stored, old_stored, live_rule, hist, rep = run(go())
    assert resp.message == "FFA match recorded"
    assert int(stored["game_number"]) == 2
    assert _as_dict(stored["settings_frozen"]) == PLAYED, "the INSERT froze no block"
    assert old_stored is None                     # the fixture's game 1: a pre-360 row
    assert live_rule is False                     # the lobby row now says otherwise
    games = {g["match_id"]: g for g in hist["games"]}
    assert set(games) == {str(resp.match_id), str(game1)}
    assert games[str(resp.match_id)]["settings"] == PLAYED, (
        "the history read the lobby's current row instead of the game's own record")
    assert games[str(game1)]["settings"] == LATER
    assert len(rep) == 1 and rep[0]["settings"] == PLAYED


def _settings_of(payload, match_id):
    """The settings block for match_id wherever a surface's answer carries it
    (a dict with an id-like key equal to match_id and a 'settings' key)."""
    found = []

    def walk(v):
        if hasattr(v, "model_dump"):
            v = v.model_dump()
        elif hasattr(v, "dict") and not isinstance(v, dict):
            v = v.dict()
        if isinstance(v, dict):
            if "settings" in v and any(str(v.get(k)) == match_id for k in ("match_id", "id", "game_id")):
                found.append(v["settings"])
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
    walk(payload)
    return found


# The anchor fixture holds only the FFA tables. Three surfaces also read other
# modes' tables (by-code tries 1v1, 2v2 and 1v2 first; recent-multimode lists
# 2v2 and 1v2 series) and side tables (bets, titles, ratings, cards). Those
# statements answer EMPTY here; every statement that reads ffa_matches or
# ffa_lobbies -- and so every one that selects settings_frozen -- runs for real.
_STUBBED_TABLES = {"matches", "team_matches", "ovt_matches", "team_series", "ovt_series",
                   "ranked_series", "ffa_bets", "shop_items", "glicko_ratings", "ffa_match_cards"}
_TABLE_RE = re.compile(r"\b(?:FROM|JOIN)\s+([a-z_]+)")


class _EmptyResult:
    def mappings(self):
        return self

    def scalars(self):
        return self

    def all(self):
        return []

    def fetchall(self):
        return []

    def first(self):
        return None

    def scalar(self):
        return None


class _OtherTablesEmpty:
    """A session whose statements on _STUBBED_TABLES answer empty; the rest
    pass through. Counts the statements that selected settings_frozen."""

    def __init__(self, db):
        self._db = db
        self.frozen_reads = 0
        self.stubbed = []

    async def execute(self, stmt, *a, **k):
        flat = " ".join(str(stmt).split())
        tables = set(_TABLE_RE.findall(flat))
        if tables & _STUBBED_TABLES:
            assert "settings_frozen" not in flat and not tables & {"ffa_matches", "ffa_lobbies"}, flat[:200]
            self.stubbed.append(sorted(tables & _STUBBED_TABLES))
            return _EmptyResult()
        if "settings_frozen" in flat:
            self.frozen_reads += 1
        return await self._db.execute(stmt, *a, **k)

    def __getattr__(self, name):
        return getattr(self._db, name)


def test_pg_an_empty_frozen_object_reads_unknown_on_all_five_surfaces():
    """Round 2 (L1): the game's row holds {} (non-NULL, not the six keys) and
    the lobby then changes to LATER. Every FFA history surface answers the
    game's settings as unknown (None), never the lobby's later values; the
    fixture's pre-360 game (NULL) still reads the lobby row."""
    require_pg()

    async def go():
        engine, sm, pids, game1 = await _fixture_with_360()
        try:
            async with engine.begin() as conn:
                await conn.execute(text(_SET_LOBBY), _lobby_params(PLAYED))
                # by-code selects it on the FFA branch; the anchor fixture lacks it
                await conn.execute(text(
                    "ALTER TABLE ffa_matches ADD COLUMN IF NOT EXISTS invalidation_reason TEXT"))
            resp = await _call_endpoint(sm, _endpoint_report(
                ROW_B, S1, "rm_211531_r2", with_slots=True))
            mid = str(resp.match_id)
            async with engine.begin() as conn:
                await conn.execute(text(
                    "UPDATE ffa_matches SET settings_frozen = CAST('{}' AS jsonb) WHERE id = :m"), {"m": mid})
                await conn.execute(text(_SET_LOBBY), _lobby_params(LATER))
            async with sm() as raw_db:
                db = _OtherTablesEmpty(raw_db)
                ranked = bool((await db.execute(text(
                    "SELECT is_ranked FROM ffa_matches WHERE id = :m"), {"m": mid})).scalar())
                code = mid.replace("-", "")[:12]
                by_code = await main.get_match_by_code(code, db)
                multimode = await main.get_recent_multimode_series(minutes=43200, limit=200, db=db)
                recent = await main.ffa_recent(page=0, page_size=30, ranked=ranked,
                                               participant_steam_id=None, db=db)
                hist = await main.player_ffa_history(S1, 15, db)
                rep, _slots = await main._report_load_ffa(db, mid, str(pids[S1]))
            return mid, str(game1), ranked, by_code, multimode, recent, hist, rep, db.frozen_reads
        finally:
            await engine.dispose()

    mid, g1, ranked, by_code, multimode, recent, hist, rep, frozen_reads = run(go())
    assert ranked, "the fixture's game is casual: recent-multimode lists ranked games only"
    assert frozen_reads == 5, "each of the five surfaces reads settings_frozen for real: %d" % frozen_reads
    surfaces = {"by-code": by_code, "recent-multimode": multimode, "ffa/recent": recent,
                "ffa-history": hist, "report": rep}
    for name, payload in surfaces.items():
        got = _settings_of(payload, mid)
        assert got, (name, "the surface did not return the game")
        assert all(s is None for s in got), (name, got)
    # the legacy NULL row on the same lobby still reads the lobby row
    assert _settings_of(hist, g1) == [LATER]
