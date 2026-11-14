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
  A7  a game already stored, and its repeat meets ANOTHER constraint first
      (unique_match deferred, another unique immediate): not a duplicate
      success, 500, nothing kept.
  A8  a repeat whose rounds differ is answered with the STORED match: its
      winner and its series score, not the repeat's.

Each scenario returns its outcome; the tests assert the lane's outcome and
every control at the bottom runs one mutant and asserts the mutant's OWN
outcome (status, series_status, row counts), never "some AssertionError"
(lesson 1187).

Shares the schema builder, fixtures and app client of
test_title_ladder_hooks_live.py (the same DSN variable, the same fail-not-skip
rule when it is unset).
"""
import asyncio
import contextlib
import uuid

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


def _ans(r):
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text[:200]


async def _first_then_again(schema, sm, first_body, again_body=None):
    """Post `first_body`, then `again_body` (default: the same): both answers,
    what the second changed, and the match count after."""
    await live._seed(sm, wear={}, plain=(P1, P2))
    async with live._app(schema) as client:
        first = _ans(await client.post("/api/v1/matches", json=first_body))
        before = await _tables(schema)
        again = _ans(await client.post("/api/v1/matches", json=again_body or first_body))
        after = await _tables(schema)
    return {"first": first, "again": again, "changed": _changed(before, after),
            "matches": await _count(schema, "SELECT count(*) FROM matches")}


def _assert_duplicate(out, tag):
    (s1, a), (s2, b) = out["first"], out["again"]
    assert s1 == 200, (tag, "first", out["first"])
    assert s2 == 200, (tag, "second answer", out["again"])
    assert b["series_status"] == "duplicate", (tag, b)
    assert "already recorded" in b["message"], (tag, b)
    assert (b["xp_gained"], b["gold_gained"], b["xp_bonuses"], b["gold_bonuses"]) == (0, 0, [], []), (tag, b)
    assert b["match_id"] == a["match_id"], (tag, "not the existing match", a["match_id"], b["match_id"])
    assert b["winner_steam_id"] == a["winner_steam_id"], (tag, a, b)
    assert (b["total_xp"], b["level"]) == (a["total_xp"], a["level"]), (tag, a, b)
    assert out["changed"] == {}, (tag, "the repeated report kept something", out["changed"])
    assert out["matches"] == 1, (tag, out["matches"])


async def _a1(room):
    async with live._case() as (schema, sm):
        return await _first_then_again(schema, sm, _body(live._report_1v1(room, ranked=False)))


def test_pg_a1_a_repeated_casual_report_answers_already_recorded(opened):
    live._require_live_pg()
    out = live._run(_a1("qp_dupA_000001"))
    assert out["first"][1]["series_status"] == "none", out
    _assert_duplicate(out, "A1")


async def _a2(room, again_body=None):
    async with live._case() as (schema, sm):
        first = _body(live._report_1v1(room))
        return await _first_then_again(schema, sm, first, again_body)


def test_pg_a2_a_repeated_ranked_game_answers_already_recorded(opened):
    live._require_live_pg()
    out = live._run(_a2("ranked_dupB_000001_r1"))
    assert out["first"][1]["series_status"] == "active", out
    _assert_duplicate(out, "A2")
    assert out["again"][1]["series_score"] == out["first"][1]["series_score"] == "1-0", out


def test_pg_a3_two_racing_deliveries_record_once_and_neither_fails(opened):
    live._require_live_pg()

    async def _go():
        async with live._case() as (schema, sm):
            await live._seed(sm, wear={}, plain=(P1, P2))
            report = _body(live._report_1v1("qp_dupC_000001", ranked=False))
            async with live._app(schema) as client:
                a, b = await asyncio.gather(client.post("/api/v1/matches", json=report),
                                            client.post("/api/v1/matches", json=report))
            return _ans(a), _ans(b), await _count(schema, "SELECT count(*) FROM matches")
    a, b, n = live._run(_go())
    assert sorted([a[0], b[0]]) == [200, 200], ("A3: a racing delivery failed", a, b)
    assert sorted([a[1]["series_status"], b[1]["series_status"]]) == ["duplicate", "none"], (a, b)
    assert a[1]["match_id"] == b[1]["match_id"] and n == 1, (a, b, n)


async def _other_unique(conn, schema):
    await conn.execute("CREATE UNIQUE INDEX dup_probe_other_unique ON matches (match_duration)")


async def _a4():
    """A different game (another room) whose insert meets the OTHER unique."""
    async with live._case(extra_ddl=_other_unique) as (schema, sm):
        return await _first_then_again(
            schema, sm,
            _body(live._report_1v1("qp_dupD_000001", ranked=False, duration=301)),
            _body(live._report_1v1("qp_dupD_000002", ranked=False, duration=301)))


def test_pg_a4_another_unique_violation_is_not_a_duplicate(opened):
    live._require_live_pg()
    out = live._run(_a4())
    assert out["first"][0] == 200, out
    assert out["again"][0] == 500, ("A4: another constraint's violation was not answered as a "
                                    "failure", out["again"])
    assert out["changed"] == {} and out["matches"] == 1, out


async def _deferred_unique(conn, schema):
    await conn.execute(
        "ALTER TABLE matches DROP CONSTRAINT unique_match, "
        "ADD CONSTRAINT unique_match UNIQUE (photon_room_id, player1_id, player2_id) "
        "DEFERRABLE INITIALLY DEFERRED")


def test_pg_a5_the_violation_met_at_commit_answers_already_recorded(opened):
    live._require_live_pg()

    async def _go():
        async with live._case(extra_ddl=_deferred_unique) as (schema, sm):
            return await _first_then_again(
                schema, sm, _body(live._report_1v1("qp_dupE_000001", ranked=False)))
    _assert_duplicate(live._run(_go()), "A5")


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
            return got
    got = live._run(_go())
    assert got == {"unique": "unique_match", "fk": None}, got


async def _deferred_and_other(conn, schema):
    await _deferred_unique(conn, schema)
    await _other_unique(conn, schema)


async def _a7():
    """The game is stored; its exact repeat meets the immediate OTHER unique
    at the insert, before the deferred unique_match could."""
    async with live._case(extra_ddl=_deferred_and_other) as (schema, sm):
        return await _first_then_again(
            schema, sm, _body(live._report_1v1("qp_dupI_000001", ranked=False, duration=302)))


def test_pg_a7_a_stored_game_and_another_constraint_is_not_a_duplicate_success(opened):
    live._require_live_pg()
    out = live._run(_a7())
    assert out["first"][0] == 200, out
    assert out["again"][0] == 500, ("A7: another constraint's violation answered as a duplicate",
                                    out["again"])
    assert out["changed"] == {} and out["matches"] == 1, out


def test_pg_a8_a_repeat_with_other_rounds_gets_the_stored_winner_and_score(opened):
    live._require_live_pg()
    room = "ranked_dupJ_000001_r1"
    out = live._run(_a2(room, _body(live._report_1v1(room, a_wins=False))))
    _assert_duplicate(out, "A8")
    first, again = out["first"][1], out["again"][1]
    assert first["winner_steam_id"] == P1 and again["winner_steam_id"] == P1, out   # stored, not the repeat's P2
    assert again["series_score"] == first["series_score"] == "1-0", out


# -- controls: one mutant each, judged by its own outcome ----------------------

@contextlib.contextmanager
def _patched(name, value):
    saved = getattr(main, name)
    setattr(main, name, value)
    try:
        yield
    finally:
        setattr(main, name, saved)


def _every_violation_is_unique_match(exc):
    return main._MATCH_DUP_CONSTRAINT


def test_pg_control_without_the_name_rule_another_room_reads_as_unresolved(opened):
    """Mutant: every IntegrityError names unique_match. A4's other room has no
    stored row to find, so the mutant answers 503 duplicate_unresolved (not
    the lane's 500), and keeps nothing."""
    live._require_live_pg()
    with _patched("_violated_unique", _every_violation_is_unique_match):
        out = live._run(_a4())
    assert out["again"] == (503, {"detail": "duplicate_unresolved"}), out
    assert out["changed"] == {} and out["matches"] == 1, out


def test_pg_control_without_the_name_rule_a_stored_game_reads_as_duplicate_success(opened):
    """Mutant: every IntegrityError names unique_match. A7's repeat has a
    stored row, so the mutant answers the 200 duplicate success the lane
    must not give."""
    live._require_live_pg()
    with _patched("_violated_unique", _every_violation_is_unique_match):
        out = live._run(_a7())
    assert out["again"][0] == 200 and out["again"][1]["series_status"] == "duplicate", out
    assert out["again"][1]["match_id"] == out["first"][1]["match_id"], out
    assert out["matches"] == 1, out


def test_pg_control_without_the_insert_arm_the_repeat_answers_500(opened):
    """Mutant: the insert helper adds and flushes with no handler (the
    unchanged tree's shape). A1's repeat then answers 500, keeping nothing."""
    live._require_live_pg()

    async def _bare(db, match):
        db.add(match)
        await db.flush()
        return True
    with _patched("_flush_new_match", _bare):
        out = live._run(_a1("qp_dupG_000001"))
    assert out["first"][0] == 200 and out["again"][0] == 500, out
    assert out["changed"] == {} and out["matches"] == 1, out


def test_pg_control_with_a_wrong_existing_row_the_answer_names_another_id(opened):
    """Mutant: the duplicate answer names a fresh id. A1's repeat then
    answers 200 duplicate under an id that is not the stored match's."""
    live._require_live_pg()
    real = main._duplicate_match_response

    async def _wrong(db, *args):
        out = await real(db, *args)
        out.match_id = uuid.uuid4()
        return out
    with _patched("_duplicate_match_response", _wrong):
        out = live._run(_a1("qp_dupH_000001"))
    assert out["again"][0] == 200 and out["again"][1]["series_status"] == "duplicate", out
    assert out["again"][1]["match_id"] != out["first"][1]["match_id"], out
    assert out["matches"] == 1, out


def test_pg_control_with_the_repeats_winner_echoed_a8_sees_it(opened):
    """Mutant: the duplicate answer takes its winner from the repeat (the
    reviewed tree's shape). A8's repeat then answers P2."""
    live._require_live_pg()
    real = main._duplicate_match_response

    async def _echo(db, *args):
        out = await real(db, *args)
        out.winner_steam_id = P2
        return out
    room = "ranked_dupK_000001_r1"
    with _patched("_duplicate_match_response", _echo):
        out = live._run(_a2(room, _body(live._report_1v1(room, a_wins=False))))
    assert out["again"][0] == 200 and out["again"][1]["winner_steam_id"] == P2, out
