"""The leaderboards' online marker (bug 342; Codex Group 2 review M1 + L1,
Sept 6). Source pins: ONE shared expression at every board, reading the column
only the presence heartbeat writes, and refusing to light on a replica that
has stopped replaying. These are pins on main.py's text because the boards are
raw SQL the FakeSession suite never executes."""
import re
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "api"
SRC = (API / "main.py").read_text(encoding="utf-8")


def _marker_sql():
    # The constant's value as the module builds it: since B1 it ends with the
    # one ban definition (models.player_ban_active_sql), a call, so the text
    # of the literal alone is no longer the whole expression.
    import main
    assert "_ONLINE_MARKER_SQL = (" in SRC, "the marker constant is gone"
    return main._ONLINE_MARKER_SQL


def test_the_marker_is_false_for_an_actively_banned_account():
    """B1: the marker's last term leaves out an account under an active ban,
    by the one definition, so every board and the hover card that read the
    marker show no online dot for it."""
    import main
    sql = _marker_sql()
    tail = (" AND NOT EXISTS (SELECT 1 FROM player_bans pbo WHERE pbo.steam_id = p.steam_id AND "
            + main.player_ban_active_sql("pbo") + "))")
    assert sql.endswith(tail), sql
    assert sql.count("player_bans") == 1


def test_every_board_uses_the_shared_marker():
    assert SRC.count("{_ONLINE_MARKER_SQL} AS is_online") == 4, "four boards, one expression"
    assert "p.last_seen > NOW() - INTERVAL '3 minutes'" not in SRC, "an inline copy drifted back"


def test_the_marker_reads_the_heartbeat_column_and_requires_a_current_replica():
    sql = _marker_sql()
    assert "p.presence_seen_at > NOW() - INTERVAL '3 minutes'" in sql
    assert "p.appear_offline = FALSE" in sql
    assert "NOT pg_is_in_recovery()" in sql
    assert "pg_last_xact_replay_timestamp()" in sql
    assert "INTERVAL '90 seconds'" in sql
    # last_seen is stamped for reported opponents too; the marker never reads it.
    assert "last_seen" not in sql.replace("presence_seen_at", "")
    assert "PRESENCE_TTL_SEC = 180" in SRC, "the 3-minute window mirrors the presence TTL"


def test_only_the_heartbeat_stamps_the_column():
    # r5 M1: the stamp is a CASE on the verified-session predicate; no bare
    # unconditional stamp may exist anywhere.
    assert SRC.count("presence_seen_at = NOW()") == 0
    assert SRC.count("presence_seen_at = CASE WHEN ok.verified THEN NOW() ELSE p.presence_seen_at END") == 1
    ping = SRC.index("async def presence_ping(")
    stamp = SRC.index("presence_seen_at = CASE WHEN ok.verified THEN NOW()")
    following = SRC.find("\nasync def ", ping + 1)
    assert ping < stamp < following, "the stamp lives inside presence_ping"


def test_the_migration_adds_the_column_and_the_model_leaves_it_alone():
    migration = (API.parent / "sql" / "296_players_presence_seen_at.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE players ADD COLUMN IF NOT EXISTS presence_seen_at TIMESTAMPTZ;" in migration
    assert migration.count("BEGIN;") == 1 and migration.count("COMMIT;") == 1
    model = (API / "models.py").read_text(encoding="utf-8")
    assert "presence_seen_at = Column(" not in model, "raw SQL on both ends, by design"
    assert "presence_seen_at" in model, "the model documents the column it does not declare"


def test_the_heartbeat_stamps_only_a_verified_session():
    # r5 M1: last_seen (90-day authority) and presence_seen_at (online dot) move
    # only when the ping carries a verified, unexpired session bound to the
    # named id; an unverified ping writes neither.
    ping = SRC.index("async def presence_ping(")
    end = SRC.index("\n@app.", ping + 1)
    span = SRC[ping:end]
    assert "last_seen = CASE WHEN ok.verified THEN NOW() ELSE p.last_seen END" in span
    assert "presence_seen_at = CASE WHEN ok.verified THEN NOW() ELSE p.presence_seen_at END" in span
    assert "AND ss.steam_id = :sid" in span and "AND ss.verified" in span
    assert "SET last_seen = NOW()" not in span
    assert "unverified ping is answered but stamps nothing" in span
