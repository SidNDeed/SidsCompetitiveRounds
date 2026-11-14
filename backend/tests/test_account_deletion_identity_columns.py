"""Account deletion clears every identity-bearing column of the players row.

delete_player_data anonymises the players row in place (it never deletes it),
so every row elsewhere keyed by players.id -- gold_transactions, player_items,
music_album_refund_archive -- resolves to this row after a deletion. What the
row still holds is therefore what those rows can be tied back to.

The census: every column of players, as the full replayed schema has it, is
classed below as IDENTITY (it names, or links to, the person) or as one of the
other classes. A column that appears and is in no class fails
test_every_players_column_is_classed until someone classes it. Then the live
case fills every IDENTITY column with a distinct value, deletes the account
through the route's own function, and proves that no filled value survives
anywhere in the row.

Runs on the connect-failure lane's full schema (CF_TEST_PG_DSN, cf_pg.case).
"""
import asyncio
import hashlib
import hmac
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))
sys.path.insert(0, HERE)

import main  # noqa: E402

SECRET = "deletion-census-secret"

# Names, links to the person, or content they made that identifies them.
IDENTITY = {
    "steam_id", "display_name", "discord_id", "discord_username", "discord_display_name",
    # the player-card portrait units: the uploaded picture's hash and its
    # descriptor, the Steam picture's hash and the Steam avatar reference
    "pc_game_portrait_hash", "pc_game_portrait_descriptor",
    "pc_steam_portrait_hash", "pc_steam_avatar_ref",
}
# Not identity: the surrogate key, counters, totals, records, ratings flags.
STATS = {
    "id", "total_xp", "ranked_dc_count", "gold_earned", "gold_spent", "bullets_fired",
    "bullets_hit", "blocks_activated", "blocks_successful", "team_gold_earned",
    "team_xp_earned", "keys_pressed_total", "active_seconds_total", "consecutive_sweeps",
    "casual_win_streak", "ffa_gold_earned", "ffa_xp_earned", "record_max_single_hit",
    "record_max_health", "record_bounce_kill", "casual_dc_count", "pc_shards",
    "pc_settings_revision", "pc_trades_generation", "pc_steam_portrait_fail",
    "pc_steam_attempt", "pc_motion_day_count",
}
# Not identity: timestamps of activity and schedules (no value names anyone).
TIMES = {
    "first_seen", "last_seen", "deleted_at", "mod_seen_at", "steam_auth_seen_at",
    "presence_seen_at", "pc_opted_out_at", "pc_game_portrait_at",
    "pc_game_portrait_locked_until", "pc_steam_portrait_at", "pc_steam_portrait_next_at",
    "pc_motion_at", "pc_motion_day",
}
# Not identity: preferences and enumerated settings.
SETTINGS = {
    "ranked_enabled", "hide_gold", "appear_offline", "show_discord", "allow_spectators",
    "mail_from", "pref_same_cards", "pc_collection_public", "pc_announce",
    "pc_portrait_source", "pc_trades_open", "mail_discord_relay", "mod_version",
}
# Not identity: shop item ids of equipped cosmetics.
COSMETICS = {
    "active_title_id", "active_trail_id", "active_color_id", "nametag_style_ids",
    "active_color_ids", "active_player_color_id", "active_cursor_color_id",
    "active_player_effect_id", "active_dance_id",
}
CLASSES = (IDENTITY, STATS, TIMES, SETTINGS, COSMETICS)

STEAM = "dc413census"
FILL = {
    "display_name": "dc413 display",
    "discord_id": "dc413discordid",
    "discord_username": "dc413discorduser",
    "discord_display_name": "dc413discorddisplay",
    "pc_game_portrait_hash": "dc413" + "a" * 59,
    "pc_game_portrait_descriptor": "dc413descriptor",
    "pc_steam_portrait_hash": "dc413" + "b" * 59,
    "pc_steam_avatar_ref": "dc413avatarref",
}


def test_the_classes_are_disjoint():
    seen = set()
    for c in CLASSES:
        assert not (seen & c), sorted(seen & c)
        seen |= c


def _case(body):
    import cf_pg
    cf_pg.require_live_pg()

    async def inside():
        async with cf_pg.case("dc413") as (c, sm):
            return await body(c.conn, sm)
    return asyncio.run(inside())


def test_every_players_column_is_classed():
    async def body(conn, _sm):
        rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = 'players'")
        return {r["column_name"] for r in rows}
    cols = _case(body)
    classed = set().union(*CLASSES)
    assert cols - classed == set(), ("unclassed players columns", sorted(cols - classed))
    assert classed - cols == set(), ("classed columns the schema lacks", sorted(classed - cols))


def test_deletion_clears_every_identity_column(monkeypatch):
    import cf_asm
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", SECRET)
    monkeypatch.delenv("STEAM_WEB_API_KEY", raising=False)

    async def body(conn, sm):
        pid = await conn.fetchval(
            "INSERT INTO players (steam_id, display_name) VALUES ($1, $2) RETURNING id",
            STEAM, FILL["display_name"])
        for h in (FILL["pc_game_portrait_hash"], FILL["pc_steam_portrait_hash"]):
            await conn.execute(
                "INSERT INTO pc_portraits (hash, bytes, content_type, width, height)"
                " VALUES ($1, $2, 'image/png', 8, 8)", h, b"dc413")
        sets =", ".join("%s = $%d" % (c, i + 2) for i, c in enumerate(FILL))
        await conn.execute("UPDATE players SET %s WHERE id = $1" % sets, pid, *FILL.values())
        filled = await conn.fetchrow(
            "SELECT %s FROM players WHERE id = $1" % ", ".join(sorted(IDENTITY)), pid)
        sig = hmac.new(SECRET.encode(), ("delete:%s" % STEAM).encode(),
                       hashlib.sha256).hexdigest()
        async with sm() as db:
            await main.delete_player_data(STEAM, cf_asm.FakeRequest(), sig=sig, _slot=None, db=db)
        after = await conn.fetchrow(
            "SELECT %s, deleted_at FROM players WHERE id = $1" % ", ".join(sorted(IDENTITY)), pid)
        whole = await conn.fetchval("SELECT CAST(p AS text) FROM players p WHERE id = $1", pid)
        # the two pictures are released to the janitor, which deletes a blob
        # after its grace; the deletion path itself never deletes one
        released = await conn.fetchval(
            "SELECT count(*) FROM pc_portraits WHERE hash = ANY($1::text[])"
            " AND unreferenced_since IS NOT NULL",
            [FILL["pc_game_portrait_hash"], FILL["pc_steam_portrait_hash"]])
        return dict(filled), dict(after), whole, released

    filled, after, whole, released = _case(body)
    assert released == 2, released
    # the fixture really filled every identity column (a control: a column
    # left NULL here would pass the check below without proving anything)
    assert all(filled[c] is not None for c in IDENTITY), filled
    assert after["deleted_at"] is not None
    survived = {c: after[c] for c in IDENTITY if after[c] == filled[c]}
    assert survived == {}, survived
    leaked = [c for c in IDENTITY if str(filled[c]) in whole]
    assert leaked == [], leaked
