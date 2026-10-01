"""The five-tier title ladders (board row 29): the catalogue, the per-game
unit, every playstyle boundary, the Apex run, the card families, the refund
migration 366, the old client's parser over the extended answer, and the
/health `title_ladders` word.

Every behavioural test here is paired with a NEGATIVE CONTROL: a mutated
input or a mutated evaluator under which the same assertion must fail. A test
that passes under its own control proves nothing (#391).

The live half runs against LADDER_TEST_PG_DSN (fail, not skip, when unset --
see test_title_ladders._require_live_pg) on the production-faithful schema of
title_ladders_lane_schema: 331 as it shipped, the live shop titles, then 365.
"""
import asyncio
import json
import os
import sys
import uuid
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))
sys.path.insert(0, HERE)

import title_ladders as tl                                    # noqa: E402
import main                                                   # noqa: E402,F401
import schemas                                                # noqa: E402
import title_ladders_lane_schema as lane                      # noqa: E402
from test_title_ladders import (                              # noqa: E402
    LADDER_DSN, _asyncpg, _require_live_pg, _LadderDB, _sql_tuples, MIGRATION_365)
from test_title_ladder_route_contract import _answer          # noqa: E402
from test_health_ladder_hook_marker import _health            # noqa: E402

M365 = "365_title_ladders_five_tiers.sql"
M366 = "366_title_refunds_voidshot_kingslayer.sql"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# -- 1. The catalogue ------------------------------------------------------
#
# The proposal's catalogue as built (deviations recorded in the build notes:
# Grinder keeps "Noobie" at tier 1, title_gold_rush carries "Gold Rush" at
# tier 2, the pronoun titles climb I to V, no Slayers ladder). The module is
# compared to THIS table, not to itself.

NAME_LIMIT = 14

PROPOSAL = [
    ("rat", "animal", "games", ("Baby Mouse", "Mouse", "Rat", "Rat Lord", "CAPYBARA")),
    ("cat", "animal", "games", ("Stray", "Prowler", "Alley King", "Sabertooth", "Sekhmet")),
    ("dog", "animal", "games", ("Pup", "Dog", "Hound", "Hellhound", "Cerberus")),
    ("turtle", "animal", "games", ("Hatchling", "Turtle", "Snapper", "Leatherback", "World Turtle")),
    ("rabbit", "animal", "games", ("Bunny", "Rabbit", "Jackrabbit", "Jackalope", "Moon Rabbit")),
    ("bear", "animal", "games", ("Cub", "Bear", "Grizzly", "Kodiak", "Ursa Major")),
    ("eagle", "animal", "games", ("Eaglet", "Eagle", "Golden Eagle", "Roc", "Thunderbird")),
    ("shark", "animal", "games", ("Shark Pup", "Reef Shark", "Great White", "Megalodon", "Leviathan")),
    ("tracker", "card", "card", ("Homing User", "Target Bouncer", "Remote Killer", "Elite Tracker", "No Escape")),
    ("poisoner", "card", "card", ("Poison", "Toxic Cloud", "Decay", "Plague Doctor", "Pestilence")),
    ("windup", "card", "card", ("Wind Up", "Quick Shot", "Fastball", "Steady Shot", "Railgun")),
    ("reloader", "card", "card", ("Quick Reload", "Refresh", "Scavenger", "Tactical", "Bottomless")),
    ("colossus", "card", "card", ("Huge", "Brawler", "Tank", "Pristine", "Colossus")),
    ("hasty", "card", "card", ("Fast Forward", "Chase", "Sneaky", "Thruster", "Lightspeed")),
    ("bounce", "card", "card", ("Bouncy", "Bouncer", "Ricochet", "Mayhem", "Trick Shot")),
    ("healer", "card", "card", ("Healing Field", "Leech", "Lifestealer", "Parasite", "Immortal")),
    ("echo", "card", "card", ("Echo", "Empower", "Shockwave", "Supernova", "Big Bang")),
    ("sniper", "playstyle", "sniper", ("Marksman", "Sniper", "Sharpshooter", "Deadeye", "Headhunter")),
    ("berserker", "playstyle", "berserker", ("Bruiser", "Berserker", "Rampage", "Bloodbath", "Warlord")),
    ("blitz", "playstyle", "blitz", ("Rush", "Blitz", "Lightning", "Speedrunner", "Warp Speed")),
    ("phoenix", "playstyle", "phoenix", ("Ember", "Phoenix", "Rebirth", "From the Ashes", "Undying")),
    ("specter", "playstyle", "specter", ("Shade", "Specter", "Phantom", "Wraith", "Untouchable")),
    ("apex", "playstyle", "streak", ("Contender", "Predator", "Apex", "Alpha", "Undefeated")),
    ("clown", "shop", "games", ("Clown", "Jester", "Harlequin", "Ringmaster", "The Joker")),
    ("idiot", "shop", "losses", ("Idiot", "Moron", "Buffoon", "Village Idiot", "Idiot Savant")),
    ("grandma", "shop", "games", ("Grandma", "Nana", "Great-Grandma", "Ancestor", "Ancient One")),
    ("decent", "shop", "wins", ("Decent", "Fine", "Pretty Good", "Actually Good", "Too Good")),
    ("gold_rush", "shop", "gold", ("Prospector", "Gold Rush", "Forty-Niner", "Tycoon", "Midas")),
    ("grinder", "shop", "games", ("Noobie", "Regular", "Active", "Sweaty", "Tryhard")),
    ("pronoun_he", "numeral", "games", ("He/him I", "He/him II", "He/him III", "He/him IV", "He/him V")),
    ("pronoun_she", "numeral", "games", ("She/her I", "She/her II", "She/her III", "She/her IV", "She/her V")),
    ("pronoun_they", "numeral", "games",
     ("They/them I", "They/them II", "They/them III", "They/them IV", "They/them V")),
]


def _catalogue_view(ladders):
    return [(ld["line"], ld["group"], ld["kind"], tuple(r["name"] for r in ld["rungs"]),
             tuple(r["tier"] for r in ld["rungs"])) for ld in ladders]


def catalogue_problems(ladders, proposal=PROPOSAL):
    """Every way `ladders` differs from the proposal: count, order, group,
    kind, tiers, names, and any name over NAME_LIMIT characters."""
    out = []
    view = _catalogue_view(ladders)
    if len(view) != len(proposal):
        out.append("ladder count %d, proposal %d" % (len(view), len(proposal)))
    for got, want in zip(view, proposal):
        line, group, kind, names, tiers = got
        if (line, group, kind) != want[:3]:
            out.append("%s: (%s, %s, %s) != %s" % (line, line, group, kind, want[:3]))
        if tiers != (1, 2, 3, 4, 5):
            out.append("%s: tiers %s" % (line, tiers))
        if names != want[3]:
            out.append("%s: names %s != %s" % (line, names, want[3]))
        for n in names:
            if len(n) > NAME_LIMIT:
                out.append("%s: %r is %d characters" % (line, n, len(n)))
    return out


def _mutated(fn):
    """A deep-enough copy of LADDERS with `fn` applied to it."""
    copy = [dict(ld, rungs=[dict(r) for r in ld["rungs"]]) for ld in tl.LADDERS]
    fn(copy)
    return copy


def test_the_catalogue_is_the_proposal_five_tiers_each():
    assert catalogue_problems(tl.LADDERS) == []
    assert tl.ladder_count() == 32 and len(tl.ALL_RUNGS) == 160


def test_the_catalogue_check_refuses_a_long_name_a_sixth_rung_and_a_rename():
    def long_name(c):
        c[0]["rungs"][4]["name"] = "Capybara Kingly"            # 15 characters
    def sixth(c):
        c[1]["rungs"].append(dict(c[1]["rungs"][4], tier=6, name="Bastet"))
    def rename(c):
        c[22]["rungs"][2]["name"] = "Top Dog"
    def dropped(c):
        del c[-1]
    for fn, needle in ((long_name, "15 characters"), (sixth, "tiers"),
                       (rename, "names"), (dropped, "ladder count")):
        problems = catalogue_problems(_mutated(fn))
        assert any(needle in p for p in problems), (fn.__name__, problems)


def test_every_name_365_writes_is_the_module_name_and_within_the_limit():
    with open(MIGRATION_365, encoding="utf-8") as fh:
        sql = fh.read()
    items = _sql_tuples(
        sql,
        "INSERT INTO shop_items (sku, kind, name, description, price, rarity, "
        "rotation_pool, catalog_ready, preview_color) VALUES")
    names = {row[0]: row[2] for row in items}
    assert len(names) == 160
    assert names == {r["sku"]: r["name"] for r in tl.ALL_RUNGS}
    too_long = sorted(n for n in names.values() if len(n) > NAME_LIMIT)
    assert too_long == [], too_long
    # Control: the parse really reads the name column (a 15-character
    # literal planted in the text is seen).
    planted = sql.replace("'Leviathan'", "'Leviathan Prime'", 1)
    assert "'Leviathan Prime'" in planted
    names2 = {row[0]: row[2] for row in _sql_tuples(
        planted,
        "INSERT INTO shop_items (sku, kind, name, description, price, rarity, "
        "rotation_pool, catalog_ready, preview_color) VALUES")}
    assert [n for n in names2.values() if len(n) > NAME_LIMIT] == ["Leviathan Prime"]


def test_apex_thresholds_are_the_streak_schedule():
    assert [r["threshold"] for r in tl.LINES["apex"]["rungs"]] == [0, 5, 8, 12, 20]
    assert tl.LINES["apex"]["modes"] == "1v1"


# -- 2. The playstyle boundaries, through game_row_1v1 ---------------------
#
# A synthetic `matches` row whose point_timeline follows ROUNDS' scoring:
# two points take a round, five rounds take the game, and each side's value
# is rounds_won * 2 + points in the current round (models.Match) -- so the
# side that loses a round drops back to its rounds * 2.

def timeline(scorers):
    """`scorers` is a string of 'a' / 'b' (a = player 1). Returns
    (point_timeline, rounds_a, rounds_b)."""
    ra = rb = pa = pb = 0
    out = []
    for s in scorers:
        if s == "a":
            pa += 1
        else:
            pb += 1
        if pa == 2:
            ra, pa, pb = ra + 1, 0, 0
        elif pb == 2:
            rb, pa, pb = rb + 1, 0, 0
        out.append("%d:%d" % (ra * 2 + pa, rb * 2 + pb))
    return ",".join(out), ra, rb


def _game(winner, seq, *, duration=300, shots=0, hits=0):
    """A 1v1 row won by `winner` ("P1" or "P2"); `seq` is written from the
    WINNER's side ('w' / 'l'). Returns (match, winner_id, loser_id)."""
    a_is_w = winner == "P1"
    scorers = "".join(("a" if a_is_w else "b") if c == "w" else ("b" if a_is_w else "a")
                      for c in seq)
    pt, ra, rb = timeline(scorers)
    w_rounds, l_rounds = (ra, rb) if a_is_w else (rb, ra)
    assert w_rounds == 5 and l_rounds < 5, (seq, ra, rb)
    loser = "P2" if a_is_w else "P1"
    m = SimpleNamespace(
        player1_id="P1", player2_id="P2", winner_id=winner,
        p1_rounds_won=ra, p2_rounds_won=rb,
        p1_bullets_fired=shots if a_is_w else 50, p1_bullets_hit=hits if a_is_w else 0,
        p2_bullets_fired=50 if a_is_w else shots, p2_bullets_hit=0 if a_is_w else hits,
        duration_seconds=duration, point_timeline=pt)
    return m, winner, loser


def _delta(line, winner, seq, **kw):
    m, w, _ = _game(winner, seq, **kw)
    return tl.counted_delta(line, tl.game_row_1v1(m, w))


def _loser_delta(line, winner, seq, **kw):
    m, _, lo = _game(winner, seq, **kw)
    return tl.counted_delta(line, tl.game_row_1v1(m, lo))


SWEEP = "w" * 10                       # 5-0, the loser scores nothing
BOTH = pytest.mark.parametrize("winner", ["P1", "P2"])


@BOTH
def test_the_timeline_generator_follows_rounds_scoring(winner):
    pt, ra, rb = timeline("abbabbabb" + "a" * 10)
    assert pt.split(",")[:3] == ["1:0", "1:1", "0:2"]
    assert (ra, rb) == (5, 3) and pt.endswith("10:6")


@BOTH
def test_blitz_210_seconds_passes_and_211_fails(winner):
    assert _delta("blitz", winner, SWEEP, duration=210) == 1
    assert _delta("blitz", winner, SWEEP, duration=211) == 0
    assert _loser_delta("blitz", winner, SWEEP, duration=100) == 0


@BOTH
def test_sniper_30_pct_over_40_shots_passes_and_39_shots_fails(winner):
    assert _delta("sniper", winner, SWEEP, shots=40, hits=12) == 1
    assert _delta("sniper", winner, SWEEP, shots=39, hits=12) == 0
    assert _delta("sniper", winner, SWEEP, shots=40, hits=11) == 0
    assert _loser_delta("sniper", winner, SWEEP, shots=40, hits=40) == 0


@BOTH
def test_phoenix_trailing_by_5_passes_and_by_4_fails(winner):
    assert _delta("phoenix", winner, "l" * 5 + "w" * 10) == 1
    assert _delta("phoenix", winner, "l" * 4 + "w" * 10) == 0
    assert _loser_delta("phoenix", winner, "l" * 5 + "w" * 10) == 0


@BOTH
def test_specter_losing_2_passes_and_3_fails(winner):
    assert _delta("specter", winner, "lww" * 2 + "w" * 6) == 1
    assert _delta("specter", winner, "lww" * 3 + "w" * 4) == 0
    assert _delta("specter", winner, SWEEP) == 1
    assert _loser_delta("specter", winner, SWEEP) == 0


@BOTH
def test_berserker_5_0_passes_and_5_1_fails(winner):
    assert _delta("berserker", winner, SWEEP) == 1
    assert _delta("berserker", winner, "ll" + "w" * 10) == 0
    assert _loser_delta("berserker", winner, SWEEP) == 0


@BOTH
def test_the_conditions_read_points_scored_not_timeline_values(winner, monkeypatch):
    """NEGATIVE CONTROL for the evaluator. The timeline value of the side that
    loses a round drops back to its rounds * 2, so read as points it UNDER-
    counts the loser (three points over three lost rounds reads 0) and OVER-
    counts a deficit. With raw_points replaced by the identity -- the values
    read as points -- both cases flip, which is what these assertions catch."""
    spread3 = "lww" * 3 + "w" * 4              # loser scores 3, timeline ends x:0
    not_down5 = "wll" * 3 + "w" * 10           # raw deficit 3, timeline deficit 6
    assert _delta("specter", winner, spread3) == 0
    assert _delta("phoenix", winner, not_down5) == 0
    monkeypatch.setattr(tl, "raw_points", lambda pts: pts)
    assert _delta("specter", winner, spread3) == 1
    assert _delta("phoenix", winner, not_down5) == 1


def test_a_malformed_or_tied_timeline_answers_neither_condition():
    m, w, _ = _game("P1", SWEEP)
    for bad in ("1:0,3:0", "1:0,1:0", "x", "", None, "1:0,1:1"):
        m.point_timeline = bad
        row = tl.game_row_1v1(m, w)
        assert row["worst_deficit"] is None and row["loser_points"] is None, bad


# -- 3. Card families -----------------------------------------------------

FAMILIES = {
    "tracker": ("Homing", "Target Bounce", "Remote"),
    "poisoner": ("Poison", "Toxic Cloud", "Decay"),
    "windup": ("Wind Up", "Quick Shot", "Fastball", "Steady Shot"),
    "reloader": ("Quick Reload", "Refresh", "Scavenger", "Tactical Reload"),
    "colossus": ("Huge", "Brawler", "Tank", "Pristine Perseverance", "Defender"),
    "hasty": ("Fast Forward", "Chase", "Sneaky", "Thruster"),
    "bounce": ("Bouncy", "Ricochet", "Mayhem", "Trickster"),
    "healer": ("Healing Field", "Leech", "Lifestealer", "Parasite"),
    "echo": ("Echo", "Empower", "Shockwave", "Supernova"),
}


def _card_row(cards):
    m, w, _ = _game("P1", SWEEP)
    return tl.game_row_1v1(m, w, cards)


def test_the_nine_families_are_the_ones_the_ladders_carry():
    assert {ld["line"]: ld["family"] for ld in tl.LADDERS if ld["kind"] == "card"} == FAMILIES


@pytest.mark.parametrize("line", sorted(FAMILIES))
def test_every_member_of_a_family_credits_and_nothing_else_does(line):
    for card in FAMILIES[line]:
        assert tl.counted_delta(line, _card_row([card])) == 1, (line, card)
        # The log spells some cards differently in case and spacing.
        assert tl.counted_delta(line, _card_row(["  " + card.upper() + " "])) == 1
    outside = sorted({c for ln, fam in FAMILIES.items() if ln != line for c in fam}
                     - set(FAMILIES[line]) | {"Pacifist", "Bombs Away", "Empty Power"})
    assert tl.counted_delta(line, _card_row(outside)) == 0, (line, outside)
    assert tl.counted_delta(line, _card_row([])) == 0
    # A loss with a family card still counts: the card ladders count games.
    m, _, lo = _game("P1", SWEEP)
    assert tl.counted_delta(line, tl.game_row_1v1(m, lo, [FAMILIES[line][0]])) == 1


def test_a_team_or_ffa_game_claims_nothing_for_a_one_v_one_kind(monkeypatch):
    """Through the hook, on a fake session: a 2v2 or FFA game worn with a
    card ladder does not even claim the credit row. Control: the same game as
    a 1v1 claims and moves the count."""
    row = {"P": _card_row(["Poison"])}
    for mode in ("2v2", "ffa"):
        db = _LadderDB(sku="title_poisoner", games=1, tier=1)
        _run(tl.record_completed_games(db, ["P"], mode=mode, reference_id="g1", rows=row))
        assert db.credit_attempts == 0, mode
        assert not any("INSERT INTO title_ladder_progress" in s for s, _ in db.log), mode
    db = _LadderDB(sku="title_poisoner", games=1, tier=1)
    _run(tl.record_completed_games(db, ["P"], mode="1v1", reference_id="g1", rows=row))
    assert db.credit_attempts == 1
    writes = [p for s, p in db.log if "INSERT INTO title_ladder_progress" in s]
    assert len(writes) == 1 and writes[0]["d"] == 1, writes


# -- 4. The hook against PostgreSQL ---------------------------------------

def _schema_name():
    return "tl5_%s" % uuid.uuid4().hex[:10]


async def _make_schema(schema, extra=""):
    conn = await _asyncpg.connect(LADDER_DSN)
    try:
        await conn.execute('CREATE SCHEMA "%s"' % schema)
        await conn.execute('SET search_path TO "%s"' % schema)
        await conn.execute(lane.prereq_sql())
        await conn.execute(lane.migration_text(M365))
        if extra:
            await conn.execute(extra)
    finally:
        await conn.close()


async def _drop_schema(schema):
    conn = await _asyncpg.connect(LADDER_DSN)
    try:
        await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
    finally:
        await conn.close()


def _engine(schema):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    engine = create_async_engine(
        LADDER_DSN.replace("postgresql://", "postgresql+asyncpg://"),
        connect_args={"server_settings": {"search_path": schema}}, poolclass=None)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def hook_scenario(wear, calls, *, held=(), gold=()):
    """One player wearing (and owning) `wear`, also holding `held`, with
    `gold` = [(reason, amount, reference_id)] on the ledger; then one hook
    call per (mode, reference_id, row), each committed. Returns what landed."""
    from sqlalchemy import text

    _require_live_pg()
    schema = _schema_name()

    async def go():
        await _make_schema(schema)
        engine, session = _engine(schema)
        try:
            async with session() as db:
                pid = (await db.execute(text(
                    "INSERT INTO players (steam_id, display_name) "
                    "VALUES ('lane-tester', 'lane tester') RETURNING id"))).scalar_one()
                for sku in (wear,) + tuple(held):
                    await db.execute(text(
                        "INSERT INTO player_items (player_id, item_id, purchase_price) "
                        "SELECT :pid, id, 0 FROM shop_items WHERE sku = :s"),
                        {"pid": pid, "s": sku})
                await db.execute(text(
                    "UPDATE players SET active_title_id = "
                    "(SELECT id FROM shop_items WHERE sku = :s) WHERE id = :pid"),
                    {"pid": pid, "s": wear})
                for reason, amount, ref in gold:
                    await db.execute(text(
                        "INSERT INTO gold_transactions (player_id, amount, reason, reference_id) "
                        "VALUES (:pid, :a, :r, :ref)"),
                        {"pid": pid, "a": amount, "r": reason, "ref": ref})
                await db.commit()
                events = []
                for mode, ref, row in calls:
                    events.append(await tl.record_completed_games(
                        db, [pid], mode=mode, reference_id=ref, rows={str(pid): row}))
                    await db.commit()
                progress = {ln: (g, t, s) for ln, g, t, s in (await db.execute(text(
                    "SELECT line, games, tier, streak FROM title_ladder_progress "
                    " WHERE player_id = :pid"), {"pid": pid})).all()}
                credits = (await db.execute(text(
                    "SELECT count(*) FROM title_ladder_credits WHERE player_id = :pid"),
                    {"pid": pid})).scalar_one()
                active = (await db.execute(text(
                    "SELECT si.sku FROM players p JOIN shop_items si ON si.id = p.active_title_id "
                    " WHERE p.id = :pid"), {"pid": pid})).scalar_one_or_none()
                owned = {s for (s,) in (await db.execute(text(
                    "SELECT si.sku FROM player_items pi JOIN shop_items si ON si.id = pi.item_id "
                    " WHERE pi.player_id = :pid"), {"pid": pid})).all()}
                return SimpleNamespace(events=events, progress=progress, credits=credits,
                                       active=active, owned=owned)
        finally:
            await engine.dispose()
            await _drop_schema(schema)

    return _run(go())


W = {"won": True, "lost": False}
L = {"won": False, "lost": True}


def _apex(results):
    return hook_scenario("title_ladder_apex_1",
                         [("1v1", "g%d" % i, r) for i, r in enumerate(results)])


def test_pg_the_apex_run_resets_on_a_loss():
    got = _apex([W, W, L, W])
    assert got.progress["apex"] == (2, 1, 1), got.progress   # best 2, tier 1, run 1
    control = _apex([W, W, W])
    assert control.progress["apex"] == (3, 1, 3), control.progress


def test_pg_five_straight_wins_reach_predator_and_a_broken_five_does_not():
    up = _apex([W] * 5)
    assert up.progress["apex"] == (5, 2, 5), up.progress
    assert up.active == "title_ladder_apex_2" and "title_ladder_apex_2" in up.owned
    assert [e["to_tier"] for ev in up.events for e in ev] == [2]
    broken = _apex([W] * 4 + [L] + [W] * 4)
    assert broken.progress["apex"] == (4, 1, 4), broken.progress
    assert broken.active == "title_ladder_apex_1"
    assert "title_ladder_apex_2" not in broken.owned


def test_pg_a_re_reported_game_credits_once():
    got = hook_scenario("title_ladder_apex_1",
                        [("1v1", "g1", W), ("1v1", "g2", W), ("1v1", "g2", W)])
    assert got.credits == 2 and got.progress["apex"][2] == 2, got.progress
    control = hook_scenario("title_ladder_apex_1",
                            [("1v1", "g1", W), ("1v1", "g2", W), ("1v1", "g3", W)])
    assert control.credits == 3 and control.progress["apex"][2] == 3


def test_pg_two_games_of_one_series_credit_two():
    got = hook_scenario("title_decent", [("1v1", "m-1", W), ("1v1", "m-2", W)])
    assert got.progress["decent"][0] == 2 and got.credits == 2, got.progress
    # Control: the old unit (the series id at both calls) credits one.
    control = hook_scenario("title_decent", [("1v1", "s-1", W), ("1v1", "s-1", W)])
    assert control.progress["decent"][0] == 1 and control.credits == 1


def test_pg_wins_and_losses_ladders_count_their_own_results():
    decent = hook_scenario("title_decent", [("2v2", "a", W), ("ffa", "b", L), ("1v1", "c", W)])
    assert decent.progress["decent"][0] == 2 and decent.credits == 3, decent.progress
    idiot = hook_scenario("title_idiot", [("2v2", "a", W), ("ffa", "b", L), ("1v1", "c", L)])
    assert idiot.progress["idiot"][0] == 2 and idiot.credits == 3, idiot.progress


def test_pg_the_gold_ladder_counts_play_gold_of_this_game_only():
    ledger = [("xp", 40, "m-1"), ("series_win", 150, "s-1"),
              ("achievement", 500, "first_blood"), ("bet_payout", 1000, "m-1"),
              ("xp", 30, "m-other"), ("purchase", -1000, "m-1")]
    got = hook_scenario("title_ladder_gold_rush_1",
                        [("1v1", "m-1", {"won": True, "gold_refs": ["m-1", "s-1"]})],
                        gold=ledger)
    assert got.progress["gold_rush"][0] == 190, got.progress
    # Control: the refs decide -- a game whose refs name nothing earns 0 and
    # writes no progress row, though the credit is spent.
    none = hook_scenario("title_ladder_gold_rush_1",
                         [("1v1", "m-9", {"won": True, "gold_refs": ["m-9"]})], gold=ledger)
    assert "gold_rush" not in none.progress and none.credits == 1


def test_pg_a_card_ladder_credits_a_family_pick_and_not_another():
    fam = tl.game_row_1v1(*_game("P1", SWEEP)[:2], cards=["Toxic Cloud"])
    other = tl.game_row_1v1(*_game("P1", SWEEP)[:2], cards=["Huge", "Bouncy"])
    got = hook_scenario("title_poisoner", [("1v1", "a", fam), ("1v1", "b", other),
                                           ("2v2", "c", fam)])
    assert got.progress["poisoner"][0] == 1, got.progress
    assert got.credits == 2                       # the 2v2 game claims nothing


def test_pg_an_owner_of_a_higher_rung_starts_there():
    got = hook_scenario("title_beginner", [("2v2", "g1", W)], held=("title_tryhard",))
    assert got.progress["grinder"] == (201, 5, 0), got.progress
    assert got.events == [[]] and got.active == "title_beginner"
    assert got.owned == {"title_beginner", "title_tryhard"}
    control = hook_scenario("title_beginner", [("2v2", "g1", W)])
    assert control.progress["grinder"] == (1, 1, 0), control.progress


# -- 5. The refund migration 366, on the seeded census ----------------------

def refund_scenario(before="", runs=1):
    """prereq + 365 + the census seed + `before`, then 366 `runs` times.
    Returns (state, [None or the refusal text per run])."""
    _require_live_pg()
    schema = _schema_name()
    sql366 = lane.migration_text(M366)

    async def go():
        await _make_schema(schema, lane.CENSUS_SEED + before)
        conn = await _asyncpg.connect(LADDER_DSN)
        try:
            await conn.execute('SET search_path TO "%s"' % schema)
            outcomes = []
            for _ in range(runs):
                try:
                    await conn.execute(sql366)
                    outcomes.append(None)
                except Exception as exc:     # the refusal is the outcome under test
                    outcomes.append(str(exc))
                    await conn.execute("ROLLBACK")
            state = {
                "players": sorted(tuple(r) for r in await conn.fetch(
                    "SELECT p.steam_id, p.gold_earned, p.gold_spent, si.sku "
                    "  FROM players p LEFT JOIN shop_items si ON si.id = p.active_title_id")),
                "items": sorted(tuple(r) for r in await conn.fetch(
                    "SELECT p.steam_id, si.sku, pi.purchase_price FROM player_items pi "
                    "  JOIN players p ON p.id = pi.player_id "
                    "  JOIN shop_items si ON si.id = pi.item_id")),
                "ledger": sorted(tuple(r) for r in await conn.fetch(
                    "SELECT p.steam_id, g.amount, g.reason, g.reference_id "
                    "  FROM gold_transactions g JOIN players p ON p.id = g.player_id")),
                "ready": dict(tuple(r) for r in await conn.fetch(
                    "SELECT sku, catalog_ready FROM shop_items "
                    " WHERE sku IN ('title_voidshot', 'title_regicide')")),
            }
            return state, outcomes
        finally:
            await conn.close()
            await _drop_schema(schema)

    return _run(go())


SEEDED_ITEMS = [("census-bystander", "title_pacifist", 3000),
                ("census-holder-1", "title_regicide", 3000)]


def test_pg_366_refunds_the_census_holder_and_a_second_run_is_a_no_op():
    state, outcomes = refund_scenario(runs=2)
    assert outcomes == [None, None], outcomes
    assert state["players"] == [
        ("census-bystander", 5000, 1000, "title_pacifist"),
        ("census-holder-1", 8000, 3000, None)], state["players"]
    assert state["items"] == [("census-bystander", "title_pacifist", 3000)]
    assert state["ledger"] == [
        ("census-holder-1", -3000, "purchase", "title_regicide"),
        ("census-holder-1", 3000, "title_refunded", "title_regicide")], state["ledger"]
    assert state["ready"] == {"title_voidshot": False, "title_regicide": False}


def test_pg_366_unequips_a_worn_refunded_title():
    worn = ("UPDATE players SET active_title_id = (SELECT id FROM shop_items "
            " WHERE sku = 'title_regicide') WHERE steam_id = 'census-holder-1';")
    state, outcomes = refund_scenario(before=worn)
    assert outcomes == [None]
    assert ("census-holder-1", 8000, 3000, None) in state["players"]


def test_pg_366_refuses_census_drift_and_changes_nothing():
    drift = ("INSERT INTO players (steam_id, display_name, gold_earned, gold_spent) "
             "VALUES ('census-late', 'late buyer', 9000, 2500);"
             "INSERT INTO player_items (player_id, item_id, purchase_price) "
             "SELECT p.id, si.id, 2500 FROM players p, shop_items si "
             " WHERE p.steam_id = 'census-late' AND si.sku = 'title_voidshot';"
             "INSERT INTO gold_transactions (player_id, amount, reason, reference_id) "
             "SELECT id, -2500, 'purchase', 'title_voidshot' FROM players "
             " WHERE steam_id = 'census-late';")
    state, outcomes = refund_scenario(before=drift)
    assert outcomes[0] and "366 refused" in outcomes[0] and "Re-census" in outcomes[0], outcomes
    assert ("census-holder-1", 8000, 6000, None) in state["players"]
    assert ("census-holder-1", "title_regicide", 3000) in state["items"]
    assert ("census-late", "title_voidshot", 2500) in state["items"]
    assert not any(r[2] == "title_refunded" for r in state["ledger"])
    assert state["ready"] == {"title_voidshot": True, "title_regicide": True}


def test_pg_366_refuses_a_price_its_ledger_does_not_show():
    skew = ("UPDATE gold_transactions SET amount = -2000 WHERE reason = 'purchase' "
            "   AND reference_id = 'title_regicide';")
    state, outcomes = refund_scenario(before=skew)
    assert outcomes[0] and "refund amount is not certain" in outcomes[0], outcomes
    assert ("census-holder-1", 8000, 6000, None) in state["players"]
    assert state["items"] == SEEDED_ITEMS
    assert state["ready"] == {"title_voidshot": True, "title_regicide": True}


# -- 6. The old client's parser over the extended answer ---------------------
#
# A line-for-line port of ApiClient.PcTopLevel / PcRawValue / PcStr / PcInt /
# PcLong / PcBool / PcStrArray / SliceTopLevelObjects / ParseTitleLadderRung /
# ParseTitleLadders as the v1.40.3 client ships them. The extended answer must
# parse to exactly what the same answer parses to with the appended keys
# removed: an older client sees no difference.

WS = " \t\r\n"


def pc_top_level(js, key):
    if not js or not key:
        return None
    n = len(js)
    start = js.find("{")
    if start < 0:
        return None
    needle = '"' + key + '"'
    depth, in_str, i = 0, False, start
    while i < n:
        c = js[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            if depth == 1 and js.startswith(needle, i):
                j = i + len(needle)
                while j < n and js[j] in WS:
                    j += 1
                if j < n and js[j] == ":":
                    j += 1
                    while j < n and js[j] in WS:
                        j += 1
                    return pc_raw_value(js, j)
            in_str = True
            i += 1
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth <= 0:
                return None
        i += 1
    return None


def pc_raw_value(js, j):
    n = len(js)
    if j >= n:
        return None
    c = js[j]
    if c == '"':
        k = j + 1
        while k < n:
            if js[k] == "\\":
                k += 2
                continue
            if js[k] == '"':
                break
            k += 1
        if k >= n:
            return None
        return js[j:k + 1]
    if c in "{[":
        d, s, k = 0, False, j
        while k < n:
            ch = js[k]
            if s:
                if ch == "\\":
                    k += 1
                elif ch == '"':
                    s = False
                k += 1
                continue
            if ch == '"':
                s = True
            elif ch in "{[":
                d += 1
            elif ch in "}]":
                d -= 1
                if d == 0:
                    return js[j:k + 1]
            k += 1
        return None
    e = j
    while e < n and js[e] not in ",}]":
        e += 1
    return js[j:e].strip()


def pc_str(raw):
    if raw is None or raw == "null":
        return None
    if len(raw) < 2 or raw[0] != '"':
        return raw
    out, i = [], 1
    while i < len(raw) - 1:
        c = raw[i]
        if c != "\\" or i + 1 >= len(raw) - 1:
            out.append(c)
            i += 1
            continue
        i += 1
        e = raw[i]
        if e in "nrtbf":
            out.append({"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f"}[e])
        elif e == "u":
            if i + 4 < len(raw):
                try:
                    out.append(chr(int(raw[i + 1:i + 5], 16)))
                    i += 4
                except ValueError:
                    pass
        else:
            out.append(e)
        i += 1
    return "".join(out)


def pc_int(raw):
    if not raw or raw == "null":
        return 0
    s = pc_str(raw)
    try:
        return int(s.strip())
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return 0


def pc_long(raw):
    if not raw or raw == "null":
        return 0
    try:
        return int(pc_str(raw).strip())
    except ValueError:
        return 0


def pc_bool(raw):
    return raw == "true"


def pc_str_array(raw):
    out = []
    if not raw or raw == "null":
        return out
    n, i = len(raw), 0
    while i < n:
        if raw[i] != '"':
            i += 1
            continue
        k = i + 1
        while k < n:
            if raw[k] == "\\":
                k += 2
                continue
            if raw[k] == '"':
                break
            k += 1
        if k >= n:
            break
        out.append(pc_str(raw[i:k + 1]) or "")
        i = k + 1
    return out


def slice_top_level_objects(js):
    out = []
    if not js:
        return out
    depth, obj_start, in_str, i = 0, -1, False, 0
    while i < len(js):
        c = js[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and obj_start >= 0:
                out.append(js[obj_start:i + 1])
                obj_start = -1
        i += 1
    return out


def parse_rung(obj):
    if not obj:
        return None
    sku = pc_str(pc_top_level(obj, "sku"))
    if not sku:
        return None
    return (pc_int(pc_top_level(obj, "tier")), sku,
            pc_str(pc_top_level(obj, "name")), pc_str(pc_top_level(obj, "description")),
            pc_str(pc_top_level(obj, "rarity")), pc_str(pc_top_level(obj, "preview_color")),
            pc_long(pc_top_level(obj, "item_id")), pc_int(pc_top_level(obj, "threshold")),
            pc_int(pc_top_level(obj, "price")), pc_bool(pc_top_level(obj, "owned")),
            pc_bool(pc_top_level(obj, "active")))


def parse_title_ladders(js):
    if not js:
        return None
    arr = pc_top_level(js, "ladders")
    if not arr or arr == "null":
        return None
    lines = []
    for obj in slice_top_level_objects(arr):
        line = pc_str(pc_top_level(obj, "line"))
        if not line:
            continue
        nt = pc_top_level(obj, "next_tier")
        has_next = bool(nt) and nt != "null"
        nxt = ((pc_int(nt), pc_int(pc_top_level(obj, "next_threshold")),
                pc_int(pc_top_level(obj, "games_to_next"))) if has_next else (0, 0, 0))
        rungs_raw = pc_top_level(obj, "rungs")
        rungs = []
        if rungs_raw and rungs_raw != "null":
            rungs = [r for r in (parse_rung(ro) for ro in slice_top_level_objects(rungs_raw))
                     if r is not None]
        lines.append((line, pc_str(pc_top_level(obj, "name")) or line,
                      pc_int(pc_top_level(obj, "games")), pc_int(pc_top_level(obj, "tier")),
                      pc_int(pc_top_level(obj, "max_tier")),
                      tuple(pc_str_array(pc_top_level(obj, "next_names"))),
                      has_next, nxt, tuple(rungs)))
    return (pc_str(pc_top_level(js, "steam_id")), pc_str(pc_top_level(js, "active_line")),
            tuple(lines))


APPENDED_LINE = ("group", "kind", "unit", "modes", "condition", "streak")
APPENDED_RUNG = ("reached",)


def _rich_answer():
    owned = ["title_ladder_rat_1", "title_ladder_rat_2", "title_ladder_rat_3",
             "title_ladder_cat_5", "title_tryhard", "title_ladder_apex_1"]
    progress = [("rat", 50, 3, 0), ("cat", 400, 5, 0), ("apex", 9, 3, 4)]
    return _answer(owned=owned, progress=progress, active_sku="title_ladder_rat_3")


def _strip(answer):
    a = json.loads(json.dumps(answer))
    for ld in a["ladders"]:
        for k in APPENDED_LINE:
            ld.pop(k)
        for r in ld["rungs"]:
            for k in APPENDED_RUNG:
                r.pop(k)
    return a


def _wire(obj, compact=True):
    """The body FastAPI's JSONResponse writes (compact separators), or the
    spaced default as a second shape."""
    if compact:
        return json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return json.dumps(obj)


@pytest.mark.parametrize("compact", [True, False])
def test_the_old_parser_reads_the_extended_answer_as_the_old_one(compact):
    answer = _rich_answer()
    full = parse_title_ladders(_wire(answer, compact))
    old = parse_title_ladders(_wire(_strip(answer), compact))
    assert full == old
    steam, active, lines = full
    assert active == "rat" and len(lines) == 32
    assert sum(len(ln[8]) for ln in lines) == 160
    by = {ln[0]: ln for ln in lines}
    assert by["rat"][2:8] == (50, 3, 5, ("Rat Lord",), True, (4, 100, 50))
    assert by["cat"][6] is False and by["cat"][7] == (0, 0, 0)
    assert by["grinder"][3] == 5                    # held tier, before any game
    assert by["apex"][7] == (4, 12, 3)
    assert by["tracker"][8][0][2] == "Homing User"
    # The appended condition text contains commas, a colon and a percent
    # sign inside its string: none of it leaks into a neighbouring key.
    assert all(ln[1] and ln[1] == tl.LINES[ln[0]]["display"] for ln in lines)


def test_the_compatibility_check_sees_a_renamed_key():
    """NEGATIVE CONTROL: a change an old client DOES see -- a key it reads,
    renamed -- must make the two parses differ."""
    answer = _rich_answer()
    renamed = json.loads(json.dumps(answer))
    for ld in renamed["ladders"]:
        ld["count"] = ld.pop("games")
    assert parse_title_ladders(_wire(renamed)) != parse_title_ladders(_wire(_strip(answer)))
    # And an appended key spelled like one the old client reads, placed
    # before it, changes what it reads.
    shadow = json.loads(json.dumps(answer))
    shadow["ladders"] = [dict([("tier", 0)] + [(k, v) for k, v in ld.items() if k != "tier"])
                         for ld in shadow["ladders"]]
    assert parse_title_ladders(_wire(shadow)) != parse_title_ladders(_wire(_strip(answer)))


def test_the_port_answers_null_where_the_client_answers_null():
    assert parse_title_ladders("") is None
    assert parse_title_ladders('{"error":"outdated') is None
    assert parse_title_ladders('{"steam_id":"1","ladders":null}') is None
    assert parse_title_ladders('{"detail":"Player not found"}') is None
    assert pc_top_level('{"a":"x\\"y","b":2}', "b") == "2"


# -- 7. The /health word ---------------------------------------------------

def test_health_reports_title_ladders_32_on_both_arms(monkeypatch):
    up, down = _health()
    assert (up["title_ladders"], down["title_ladders"]) == (32, 32)
    monkeypatch.setattr(tl, "LADDERS", tl.LADDERS[:31])
    up, down = _health()
    assert (up["title_ladders"], down["title_ladders"]) == (31, 31)


def test_the_title_ladders_field_is_required_on_the_response_model():
    field = schemas.HealthResponse.model_fields["title_ladders"]
    assert field.is_required() and field.annotation is int
