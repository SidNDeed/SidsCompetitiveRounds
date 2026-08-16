#!/usr/bin/env python3
"""Broadcast service-account policy regression checks.

Limitations: --static is a structural source/call-graph check; it does not
execute FastAPI routes or prove transaction ordering. --db proves the shared
resolved-UUID refusal semantics against synthetic TEMP schemas, not every
production route or the production schema. Run it only against scratch
PostgreSQL; its transaction is always rolled back. Neither mode imports the
application, and --static imports only the standard library.

Fingerprint discipline (cold review L4): a new route fails the count+hash and
forces a rerun here — but new-route CLASSIFICATION is keyword-driven
(CLEANUP_WORDS), so the human refreshing the fingerprint IS the review step.
Before accepting a new fingerprint, read the newly-listed route's
classification and confirm a mutation route did not self-classify as cleanup
by its name (e.g. a future `cancel_bet`).
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import sys
import uuid
from pathlib import Path


SERVICE_STEAM_ID = "76561198709950406"
EXPECTED_ROUTE_COUNT = 280
EXPECTED_ROUTE_SHA256 = "19fe3225baa190c61bd42a9d3b73f69e04d4f75bc35d9a1e403c5bc6626b618d"
ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "websocket"}
GUARD_SEEDS = {
    "_assert_no_service_subject",
    "_assert_tournament_service_policy",
    "_assert_signup_service_policy",
    "_is_broadcast_account",
    "_spectate_mandatory_class",
}
CLEANUP_WORDS = ("leave", "unsignup", "cancel", "delete_player_data", "decline", "escape")


def _load_trees(root: Path):
    paths = [root / "backend/api/main.py", root / "backend/api/tournaments.py"]
    return [(path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
            for path in paths]


def _routes_and_calls(root: Path):
    routes = []
    calls: dict[str, set[str]] = {}
    bodies: dict[str, str] = {}
    for path, tree in _load_trees(root):
        source = path.read_text(encoding="utf-8")
        source_lines = source.splitlines(keepends=True)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls[node.name] = {
                child.func.id
                for child in ast.walk(node)
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
            }
            bodies[node.name] = "".join(source_lines[node.lineno - 1:node.end_lineno])
            for deco in node.decorator_list:
                if not (isinstance(deco, ast.Call)
                        and isinstance(deco.func, ast.Attribute)
                        and isinstance(deco.func.value, ast.Name)
                        and deco.func.value.id in {"app", "router"}
                        and deco.func.attr in ROUTE_METHODS
                        and deco.args and isinstance(deco.args[0], ast.Constant)
                        and isinstance(deco.args[0].value, str)):
                    continue
                routes.append((path.name, deco.func.attr, deco.args[0].value, node.name))
    return routes, calls, bodies


def _reaches_guard(name: str, calls: dict[str, set[str]], bodies: dict[str, str]) -> bool:
    todo, seen = [name], set()
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        if current in GUARD_SEEDS:
            return True
        body = bodies.get(current, "")
        if "SPECTATE_BROADCAST_STEAM_IDS" in body and (
                "notin_" in body or "service_ids" in body):
            return True
        todo.extend(calls.get(current, ()))
    return False


def run_static(root: Path) -> None:
    routes, calls, bodies = _routes_and_calls(root)
    keys = sorted(f"{f}:{method}:{path}:{name}" for f, method, path, name in routes)
    digest = hashlib.sha256("\n".join(keys).encode()).hexdigest()
    assert len(keys) == EXPECTED_ROUTE_COUNT, (
        f"route table changed: expected {EXPECTED_ROUTE_COUNT}, found {len(keys)}; "
        "classify the new/removed route and intentionally refresh the fingerprint")
    assert digest == EXPECTED_ROUTE_SHA256, (
        "route table changed without a service-policy classification review; "
        f"new fingerprint is {digest}")

    policy = {}
    for _file, method, path, name in routes:
        if any(word in name for word in CLEANUP_WORDS):
            kind = "cleanup"
        elif _reaches_guard(name, calls, bodies):
            kind = "guarded"
        elif method == "get":
            kind = "read_only"
        else:
            # The fingerprint makes this a closed enumeration: these are the
            # currently reviewed service-neutral admin/content/account routes.
            kind = "service_neutral"
        policy[(_file, method, path, name)] = kind
    assert len(policy) == len(routes) and all(policy.values())

    required_guarded = {
        "submit_match", "queue_join", "queue_poll", "queue_ready",
        "report_disconnect", "report_casual_dc", "series_preflight", "purchase_item", "artist_gift",
        "unlock_achievement", "admin_grant_achievement", "admin_reverse_series",
        "team_queue_join", "team_queue_poll", "team_queue_ready",
        "team_series_spawn_confirm", "team_series_state",
        "admin_resolve_team_series", "admin_reverse_team_series",
        "admin_rebuild_team_glicko", "team_series_report_dc",
        "team_series_continuation", "ovt_queue_join", "ovt_queue_poll",
        "ovt_series_continuation", "submit_ovt_match", "ffa_queue_join",
        "ffa_queue_poll", "team_lobby_create", "team_lobby_join", "team_lobby_start",
        "ovt_lobby_create", "ovt_lobby_join", "ovt_lobby_start",
        "ffa_lobby_create", "ffa_lobby_join", "ffa_lobby_start", "submit_ffa_match",
        "place_bet", "place_team_bet", "place_ffa_bet", "place_lobby_bet",
        "ws_chat", "signup", "time_vote", "force_vote", "ready", "play_now",
    }
    actual_guarded = {name for (_f, _m, _p, name), kind in policy.items()
                      if kind == "guarded"}
    missing = sorted(required_guarded - actual_guarded)
    assert not missing, f"service-sensitive routes no longer reach a guard: {missing}"

    main = (root / "backend/api/main.py").read_text(encoding="utf-8")
    tournaments = (root / "backend/api/tournaments.py").read_text(encoding="utf-8")
    migration = (root / "backend/sql/225_broadcast_seat.sql").read_text(encoding="utf-8")
    for fragment in (
        "SPECTATE_BROADCAST_STEAM_IDS", "SPECTATE_SEAT_CAP = 5",
        "SPECTATE_DRAIN_SECONDS = 120", "SERVICE_POLICY_WATERMARK",
        "BROADCAST_ROTATE_SECONDS = 180", "BROADCAST_ACQ_STALL_SECONDS = 30",
        "BROADCAST_ACQ_CEILING_SECONDS = 240", "BROADCAST_EXCLUSION_MAX = 8",
        "BROADCAST_EXCLUSION_TTL_SECONDS = 15 * 60",
        "# DEPLOY GATE: Sid sign-off required (async tournament narrowing)",
        "spectate_drain_tombstones", "_spectate_admission", "_spectate_record_drains",
        "@app.get(\"/api/v1/broadcast/target\"", "_run_service_policy_audit",
    ):
        assert fragment in main, f"missing server contract fragment: {fragment}"
    for consumer in ("spectate_games", "spectate_grant", "spectate_heartbeat",
                     "broadcast_target", "_spectate_game_ready"):
        assert _reaches_guard(consumer, calls, bodies), (
            f"classifier/policy call graph no longer covers {consumer}")
    assert "t.kind = 'sync'" in main and "tm.photon_room_name = :room" in main
    assert "source_ref" in bodies["_spectate_mandatory_class"]
    assert "async_pair" not in main and "mandatory_pair" not in main
    assert "created_at < :received" in bodies["spectate_validate"]
    assert "SELECT clock_timestamp()" in bodies["spectate_validate"]
    assert main.count("DELETE FROM spectate_drain_tombstones") == 1
    assert "_assert_tournament_service_policy" in tournaments
    assert "BEGIN;" in migration and "COMMIT;" in migration
    assert "UNIQUE (room_name, region, ghost_steam_id)" in migration
    print(f"static policy OK: {len(routes)} routes classified; fingerprint {digest}")


class ServicePolicyRefusal(RuntimeError):
    pass


async def _guard(conn, player_ids) -> None:
    if not player_ids:
        return
    hit = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM players WHERE id = ANY($1::uuid[]) AND steam_id = $2)",
        list(player_ids), SERVICE_STEAM_ID)
    if hit:
        raise ServicePolicyRefusal


async def run_db(dsn: str) -> None:
    try:
        import asyncpg
    except ImportError as exc:
        raise SystemExit("--db requires asyncpg; install it in the backend test environment") from exc

    conn = await asyncpg.connect(dsn)
    tx = conn.transaction()
    await tx.start()
    try:
        await conn.execute("""
            CREATE TEMP TABLE players (id uuid PRIMARY KEY, steam_id text UNIQUE NOT NULL);
            CREATE TEMP TABLE ranked_series (id uuid PRIMARY KEY, player1_id uuid, player2_id uuid);
            CREATE TEMP TABLE team_series (id uuid PRIMARY KEY, t1a_id uuid, t1b_id uuid, t2a_id uuid, t2b_id uuid);
            CREATE TEMP TABLE ovt_series (id uuid PRIMARY KEY, solo_id uuid, duo_a_id uuid, duo_b_id uuid);
            CREATE TEMP TABLE ffa_lobbies (id uuid PRIMARY KEY, member_ids uuid[] NOT NULL);
            CREATE TEMP TABLE tournament_signups (id uuid PRIMARY KEY, player_id uuid NOT NULL);
            CREATE TEMP TABLE tournament_matches (id uuid PRIMARY KEY, p1_signup_id uuid, p2_signup_id uuid);
            CREATE TEMP TABLE glicko_ratings (player_id uuid PRIMARY KEY, rating double precision, games_played int);
            CREATE TEMP TABLE mutation_probe (label text PRIMARY KEY, mutations int NOT NULL DEFAULT 0);
        """)
        service = uuid.uuid4()
        normals = [uuid.uuid4() for _ in range(8)]
        await conn.executemany("INSERT INTO players(id, steam_id) VALUES($1,$2)",
                               [(service, SERVICE_STEAM_ID)]
                               + [(pid, f"normal-{i}") for i, pid in enumerate(normals)])

        cases = []
        for pos in range(2):
            vals = normals[:2]; vals[pos] = service; rid = uuid.uuid4()
            await conn.execute("INSERT INTO ranked_series VALUES($1,$2,$3)", rid, *vals)
            cases.append((f"ranked_series[{pos}]", "SELECT ARRAY[player1_id,player2_id] FROM ranked_series WHERE id=$1", rid))
        for pos in range(4):
            vals = normals[:4]; vals[pos] = service; rid = uuid.uuid4()
            await conn.execute("INSERT INTO team_series VALUES($1,$2,$3,$4,$5)", rid, *vals)
            cases.append((f"team_series[{pos}]", "SELECT ARRAY[t1a_id,t1b_id,t2a_id,t2b_id] FROM team_series WHERE id=$1", rid))
        for pos in range(3):
            vals = normals[:3]; vals[pos] = service; rid = uuid.uuid4()
            await conn.execute("INSERT INTO ovt_series VALUES($1,$2,$3,$4)", rid, *vals)
            cases.append((f"ovt_series[{pos}]", "SELECT ARRAY[solo_id,duo_a_id,duo_b_id] FROM ovt_series WHERE id=$1", rid))
        for pos in range(5):
            vals = normals[:5]; vals[pos] = service; rid = uuid.uuid4()
            await conn.execute("INSERT INTO ffa_lobbies VALUES($1,$2)", rid, vals)
            cases.append((f"ffa_lobbies[{pos}]", "SELECT member_ids FROM ffa_lobbies WHERE id=$1", rid))
        for pos in range(2):
            signup_ids = [uuid.uuid4(), uuid.uuid4()]
            pids = normals[:2]; pids[pos] = service
            await conn.executemany("INSERT INTO tournament_signups VALUES($1,$2)",
                                   list(zip(signup_ids, pids)))
            rid = uuid.uuid4()
            await conn.execute("INSERT INTO tournament_matches VALUES($1,$2,$3)", rid, *signup_ids)
            cases.append((f"tournament_matches[{pos}]", """
                SELECT ARRAY[s1.player_id,s2.player_id]
                  FROM tournament_matches m
                  JOIN tournament_signups s1 ON s1.id=m.p1_signup_id
                  JOIN tournament_signups s2 ON s2.id=m.p2_signup_id WHERE m.id=$1
            """, rid))

        refused = 0
        for label, sql, row_id in cases:
            ids = await conn.fetchval(sql, row_id)
            await conn.execute("INSERT INTO mutation_probe(label) VALUES($1)", label)
            try:
                await _guard(conn, ids)
                await conn.execute("UPDATE mutation_probe SET mutations=mutations+1 WHERE label=$1", label)
            except ServicePolicyRefusal:
                refused += 1
            assert await conn.fetchval("SELECT mutations FROM mutation_probe WHERE label=$1", label) == 0

        # Indirect targets/beneficiaries use the same resolved-UUID guard.
        for label in ("gift", "royalty", "admin_credit", "booster", "refund",
                      "reversal", "reward", "tournament_prize"):
            try:
                await _guard(conn, [service])
                raise AssertionError(f"{label} service beneficiary was accepted")
            except ServicePolicyRefusal:
                refused += 1

        # Standalone and mixed rating subjects: selection excludes the service
        # row while ordinary rows in the same batch still update.
        await conn.execute("INSERT INTO glicko_ratings VALUES($1,1500,0),($2,1500,0)",
                           service, normals[0])
        selected = await conn.fetch(
            "SELECT g.player_id FROM glicko_ratings g JOIN players p ON p.id=g.player_id "
            "WHERE p.steam_id <> $1", SERVICE_STEAM_ID)
        for row in selected:
            await _guard(conn, [row["player_id"]])
            await conn.execute("UPDATE glicko_ratings SET games_played=games_played+1 WHERE player_id=$1",
                               row["player_id"])
        assert await conn.fetchval("SELECT games_played FROM glicko_ratings WHERE player_id=$1", service) == 0
        assert await conn.fetchval("SELECT games_played FROM glicko_ratings WHERE player_id=$1", normals[0]) == 1
        print(f"db policy OK: {len(cases)} roster positions + 8 beneficiaries refused; mixed batch clean")
    finally:
        await tx.rollback()
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--static", action="store_true")
    mode.add_argument("--db", metavar="DSN")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if args.static:
        run_static(args.root.resolve())
    else:
        asyncio.run(run_db(args.db))


if __name__ == "__main__":
    main()
