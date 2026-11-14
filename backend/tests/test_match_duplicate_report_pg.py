"""A repeated 1v1 match report answers "already recorded", against a real
PostgreSQL built from the migrations (lane server-fix-1114, part A).

The client's outbox retries a report on any 5xx or timeout for hours, so a
report whose (photon_room_id, player1_id, player2_id) is already recorded must
answer the duplicate response -- 200, series_status "duplicate", zero gains,
the id of the EXISTING match -- and keep nothing of the repeated request.

  A1  a casual report sent twice: the second answers the duplicate response
      and every table of the schema reads the same, row for row, before and
      after it.
  A2  the same for game 1 of a ranked series, whose score the answer echoes.
  A3  two deliveries of one report racing: both answer 200, exactly one is
      the duplicate, one match row exists.
  A4  a unique violation on ANOTHER constraint at the same insert is not a
      duplicate: it answers 500 and records nothing.
  A5  the violation met at COMMIT (the case schema makes unique_match
      deferred) reaches the same duplicate response.
  A6  _violated_unique reads the constraint name off a real driver error.

The negative controls at the bottom remove one rule each through main's own
module globals and assert the rule's test then fails.

Shares the schema builder, fixtures and app client of
test_title_ladder_hooks_live.py (the same DSN variable, the same fail-not-skip
rule when it is unset).
"""
import asyncio
import contextlib
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

import main  # noqa: E402
import test_title_ladder_hooks_live as live  # noqa: E402
from test_title_ladder_hooks_live import opened  # noqa: E402,F401  (fixture)

harness = live.harness
P1, P2 = live.P1, live.P2


async def _tables(schema):
    """Every table of the case schema: {name: (row count, md5 of its rows)}."""
    conn = await harness.connect_bound(live.DSN, schema)
    try:
        names = [r[0] for r in await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = $1 ORDER BY 1", schema)]
        out = {}
        for t in names:
            row = await conn.fetchrow(
                'SELECT count(*) AS n, md5(coalesce(string_agg(x::text, \'|\' ORDER BY x::text), \'\')) AS h '
                'FROM "%s" x' % t)
            out[t] = (row["n"], row["h"])
        return out
    finally:
        await conn.close()


def _changed(before, after):
    return {t: (before.get(t), after.get(t)) for t in set(before) | set(after)
            if before.get(t) != after.get(t)}


async def _count(schema, sql, *args):
    conn = await harness.connect_bound(live.DSN, schema)
    try:
        return await conn.fetchval(sql, *args)
    finally:
        await conn.close()


def _body(report):
    return report.model_dump(mode="json")


def _assert_duplicate(first, again, tag):
    assert again.status_code == 200, (tag, "second answer", again.status_code, again.text[:300])
    a, b = first.json(), again.json()
    assert b["series_status"] == "duplicate", (tag, b)
    assert "already recorded" in b["message"], (tag, b)
    assert (b["xp_gained"], b["gold_gained"], b["xp_bonuses"], b["gold_bonuses"]) == (0, 0, [], []), (tag, b)
    assert b["match_id"] == a["match_id"], (tag, "not the existing match", a["match_id"], b["match_id"])
    assert b["winner_steam_id"] == a["winner_steam_id"], (tag, a, b)
    assert (b["total_xp"], b["level"]) == (a["total_xp"], a["level"]), (tag, a, b)


async def _a1(room):
    async with live._case() as (schema, sm):
        await live._seed(sm, wear={}, plain=(P1, P2))
        report = _body(live._report_1v1(room, ranked=False))
        async with live._app(schema) as client:
            first = await client.post("/api/v1/matches", json=report)
            assert first.status_code == 200, ("A1 first", first.status_code, first.text[:300])
            assert first.json()["series_status"] == "none", first.text[:300]
            before = await _tables(schema)
            again = await client.post("/api/v1/matches", json=report)
            after = await _tables(schema)
        _assert_duplicate(first, again, "A1")
        assert not _changed(before, after), ("A1: the repeated report kept something",
                                             _changed(before, after))
        assert await _count(schema, "SELECT count(*) FROM matches") == 1


def test_pg_a1_a_repeated_casual_report_answers_already_recorded(opened):
    live._require_live_pg()
    live._run(_a1("qp_dupA_000001"))


def test_pg_a2_a_repeated_ranked_game_answers_already_recorded(opened):
    live._require_live_pg()

    async def _go():
        async with live._case() as (schema, sm):
            await live._seed(sm, wear={}, plain=(P1, P2))
            report = _body(live._report_1v1("ranked_dupB_000001_r1"))
            async with live._app(schema) as client:
                first = await client.post("/api/v1/matches", json=report)
                assert first.status_code == 200, ("A2 first", first.status_code, first.text[:300])
                assert first.json()["series_status"] == "active", first.text[:300]
                before = await _tables(schema)
                again = await client.post("/api/v1/matches", json=report)
                after = await _tables(schema)
            _assert_duplicate(first, again, "A2")
            assert again.json()["series_score"] == first.json()["series_score"] == "1-0", (
                first.json(), again.json())
            assert not _changed(before, after), ("A2: the repeated report kept something",
                                                 _changed(before, after))
    live._run(_go())


def test_pg_a3_two_racing_deliveries_record_once_and_neither_fails(opened):
    live._require_live_pg()

    async def _go():
        async with live._case() as (schema, sm):
            await live._seed(sm, wear={}, plain=(P1, P2))
            report = _body(live._report_1v1("qp_dupC_000001", ranked=False))
            async with live._app(schema) as client:
                a, b = await asyncio.gather(client.post("/api/v1/matches", json=report),
                                            client.post("/api/v1/matches", json=report))
            codes = sorted([a.status_code, b.status_code])
            assert codes == [200, 200], ("A3: a racing delivery failed", a.status_code,
                                         b.status_code, a.text[:200], b.text[:200])
            states = sorted([a.json()["series_status"], b.json()["series_status"]])
            assert states == ["duplicate", "none"], ("A3", states)
            assert a.json()["match_id"] == b.json()["match_id"], (a.json(), b.json())
            assert await _count(schema, "SELECT count(*) FROM matches") == 1
    live._run(_go())


async def _other_unique(conn, schema):
    await conn.execute("CREATE UNIQUE INDEX dup_probe_other_unique ON matches (match_duration)")


async def _a4():
    async with live._case(extra_ddl=_other_unique) as (schema, sm):
        await live._seed(sm, wear={}, plain=(P1, P2))
        async with live._app(schema) as client:
            first = await client.post("/api/v1/matches", json=_body(
                live._report_1v1("qp_dupD_000001", ranked=False, duration=301)))
            assert first.status_code == 200, ("A4 first", first.status_code, first.text[:300])
            before = await _tables(schema)
            # A different game (another room) whose insert meets the OTHER unique.
            other = await client.post("/api/v1/matches", json=_body(
                live._report_1v1("qp_dupD_000002", ranked=False, duration=301)))
            after = await _tables(schema)
        assert other.status_code == 500, ("A4: another constraint's violation was not "
                                          "answered as a failure", other.status_code,
                                          other.text[:300])
        assert not _changed(before, after), _changed(before, after)


def test_pg_a4_another_unique_violation_is_not_a_duplicate(opened):
    live._require_live_pg()
    live._run(_a4())


async def _deferred_unique(conn, schema):
    await conn.execute(
        "ALTER TABLE matches DROP CONSTRAINT unique_match, "
        "ADD CONSTRAINT unique_match UNIQUE (photon_room_id, player1_id, player2_id) "
        "DEFERRABLE INITIALLY DEFERRED")


def test_pg_a5_the_violation_met_at_commit_answers_already_recorded(opened):
    live._require_live_pg()

    async def _go():
        async with live._case(extra_ddl=_deferred_unique) as (schema, sm):
            await live._seed(sm, wear={}, plain=(P1, P2))
            report = _body(live._report_1v1("qp_dupE_000001", ranked=False))
            async with live._app(schema) as client:
                first = await client.post("/api/v1/matches", json=report)
                assert first.status_code == 200, ("A5 first", first.status_code, first.text[:300])
                before = await _tables(schema)
                again = await client.post("/api/v1/matches", json=report)
                after = await _tables(schema)
            _assert_duplicate(first, again, "A5")
            assert not _changed(before, after), _changed(before, after)
    live._run(_go())


def test_pg_a6_the_constraint_name_is_read_off_the_driver_error(opened):
    live._require_live_pg()

    async def _go():
        async with live._case() as (schema, sm):
            await live._seed(sm, wear={}, plain=(P1, P2))
            got = {}
            async with sm() as db:
                ids = [r[0] for r in (await db.execute(main.text(
                    "SELECT id FROM players WHERE steam_id IN (:a, :b) ORDER BY steam_id"),
                    {"a": P1, "b": P2})).all()]
                for attempt in range(2):
                    try:
                        await db.execute(main.text(
                            "INSERT INTO matches (player1_id, player2_id, p1_rounds_won, "
                            "p2_rounds_won, winner_id, photon_room_id, reported_by) "
                            "VALUES (:a, :b, 5, 2, :a, 'qp_dupF_000001', :a)"),
                            {"a": ids[0], "b": ids[1]})
                        await db.commit()
                    except IntegrityError as ie:
                        got["unique"] = main._violated_unique(ie)
                        await db.rollback()
                try:
                    await db.execute(main.text(
                        "INSERT INTO matches (player1_id, player2_id, p1_rounds_won, "
                        "p2_rounds_won, winner_id, photon_room_id, reported_by) "
                        "VALUES (:a, :b, 5, 2, :a, 'qp_dupF_000002', :a)"),
                        {"a": ids[0], "b": uuid.uuid4()})
                    await db.commit()
                except IntegrityError as ie:
                    got["fk"] = main._violated_unique(ie)
                    await db.rollback()
            assert got == {"unique": "unique_match", "fk": None}, got
    live._run(_go())


# -- negative controls: remove one rule, its test fails ------------------------

@contextlib.contextmanager
def _patched(name, value):
    saved = getattr(main, name)
    setattr(main, name, value)
    try:
        yield
    finally:
        setattr(main, name, saved)


def _fails(coro):
    with pytest.raises(AssertionError):
        live._run(coro)


def test_pg_control_without_the_name_rule_another_violation_reads_as_duplicate(opened):
    """Rule: decide by the constraint's NAME. Mutant: every IntegrityError
    names unique_match. A4 must then fail (the other unique answers 200)."""
    live._require_live_pg()
    with _patched("_violated_unique", lambda exc: main._MATCH_DUP_CONSTRAINT):
        _fails(_a4())


def test_pg_control_without_the_insert_arm_the_repeat_answers_500(opened):
    """Rule: the INSERT's own violation is answered. Mutant: the insert
    helper adds and flushes with no handler (the unchanged tree's shape). A1
    must then fail."""
    live._require_live_pg()

    async def _bare(db, match):
        db.add(match)
        await db.flush()
        return True
    with _patched("_flush_new_match", _bare):
        _fails(_a1("qp_dupG_000001"))


def test_pg_control_with_a_wrong_existing_row_the_answer_is_caught(opened):
    """Rule: the answer names the EXISTING match. Mutant: the duplicate
    answer names a fresh id. A1 must then fail."""
    live._require_live_pg()
    real = main._duplicate_match_response

    async def _wrong(db, *args):
        out = await real(db, *args)
        out.match_id = uuid.uuid4()
        return out
    with _patched("_duplicate_match_response", _wrong):
        _fails(_a1("qp_dupH_000001"))
