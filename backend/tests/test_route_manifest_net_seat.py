"""Exhaustive API-route and formatter non-consumer gate for W1 telemetry."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha1
import inspect
import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.routing import Mount

import flag_evidence
import main
from net_seat_contract import (
    STORAGE_FIELDS,
    assert_no_net_seat_sentinels,
    storage_sentinels,
)


MANIFEST_PATH = Path(__file__).with_name("route_manifest_net_seat.json")
# The enumeration is only exhaustive on the PINNED FastAPI: 0.141+ wraps
# include_router() targets as _IncludedRouter entries that app.routes never
# flattens, which silently drops every tournaments route from this gate.
PINNED_FASTAPI = next(
    line.split("==")[1].strip()
    for line in (Path(__file__).parents[1] / "api" / "requirements.txt").read_text(encoding="utf-8").splitlines()
    if line.startswith("fastapi==")
)

# Module-level helpers whose source is part of a handler's reviewed surface.
ROUTE_HELPER_DEPENDENCIES = {
    "get_player_stats": ("_viewer_h2h_counts",),
}

SENTINEL_ROUTE = {
    "path": "/api/v1/matches/by-code/{code}",
    "methods": ["GET"],
    "module": "main",
    "qualname": "get_match_by_code",
}


def _joined_path(prefix: str, path: str) -> str:
    if not prefix:
        return path
    if path == "/":
        return prefix or "/"
    return prefix.rstrip("/") + "/" + path.lstrip("/")


def _route_identities(routes, prefix=""):
    identities = []
    for route in routes:
        if isinstance(route, Mount):
            identities.extend(
                _route_identities(route.routes, _joined_path(prefix, route.path))
            )
            continue
        if not isinstance(route, (APIRoute, APIWebSocketRoute)):
            continue
        path = _joined_path(prefix, route.path)
        if not path.startswith("/api/v1/"):
            continue
        endpoint = route.endpoint
        # r8 LOW 5: a handler's fingerprint covers the module-level helpers it
        # delegates to (an extracted helper must not become a fingerprint hole).
        source_text = inspect.getsource(endpoint)
        for helper_name in ROUTE_HELPER_DEPENDENCIES.get(endpoint.__qualname__, ()):
            source_text += inspect.getsource(getattr(main, helper_name))
        identities.append(
            {
                "path": path,
                "methods": sorted(getattr(route, "methods", ()) or ()),
                "module": endpoint.__module__,
                "qualname": endpoint.__qualname__,
                "source_sha1": sha1(source_text.encode("utf-8")).hexdigest(),
            }
        )
    return sorted(
        identities,
        key=lambda item: (
            item["path"],
            item["methods"],
            item["module"],
            item["qualname"],
        ),
    )


def _manifest_id(entry):
    return {key: entry[key] for key in ("path", "methods", "module", "qualname")}


def _load_manifest():
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    identity_fields = document["identity_fields"]
    assert identity_fields == ["path", "methods", "module", "qualname"]
    static_review_fields = document["static_review_fields"]
    assert static_review_fields == ["source_sha1"]
    entries = []
    for group in document["groups"]:
        classification = group["classification"]
        route_fields = identity_fields + (
            static_review_fields if classification == "statically-nonconsumer" else []
        )
        for route_values in group["routes"]:
            entry = dict(zip(route_fields, route_values, strict=True))
            entry["classification"] = group["classification"]
            entry["reason"] = group["reason"]
            entries.append(entry)
    return entries


def test_route_manifest_net_seat_is_exhaustive_and_fails_closed_on_drift():
    import fastapi
    assert fastapi.__version__ == PINNED_FASTAPI, (
        f"route enumeration requires fastapi=={PINNED_FASTAPI} (installed {fastapi.__version__})"
    )
    manifest = _load_manifest()
    live_routes = _route_identities(main.app.routes)
    actual = [_manifest_id(entry) for entry in live_routes]
    expected = sorted(
        (_manifest_id(entry) for entry in manifest),
        key=lambda item: (
            item["path"],
            item["methods"],
            item["module"],
            item["qualname"],
        ),
    )

    assert actual == expected
    assert len(manifest) == 308
    assert len({json.dumps(item, sort_keys=True) for item in expected}) == len(expected)
    assert all(
        entry["classification"] in {"sentinel-exercised", "statically-nonconsumer"}
        for entry in manifest
    )
    assert all(isinstance(entry["reason"], str) and entry["reason"].strip() for entry in manifest)

    exercised = [entry for entry in manifest if entry["classification"] == "sentinel-exercised"]
    static = [entry for entry in manifest if entry["classification"] == "statically-nonconsumer"]
    assert len(exercised) == 1
    assert len(static) == 307
    assert _manifest_id(exercised[0]) == SENTINEL_ROUTE

    actual_by_identity = {
        json.dumps(_manifest_id(entry), sort_keys=True): entry for entry in live_routes
    }
    for entry in static:
        identity = _manifest_id(entry)
        live = actual_by_identity[json.dumps(identity, sort_keys=True)]
        assert entry["source_sha1"] == live["source_sha1"], (
            f"{identity['methods']} {identity['path']} source fingerprint changed; "
            "re-review this handler"
        )


def test_request_key_counterexample_is_rejected():
    fake_response = {"local_net_writes": 0}
    with pytest.raises(AssertionError, match="local_net_writes"):
        assert_no_net_seat_sentinels(fake_response)


class _ScriptedResult:
    def __init__(self, *, row=None, rows=()):
        self.row = row
        self.rows = list(rows)

    def mappings(self):
        return self

    def first(self):
        return self.row

    def all(self):
        return self.rows


class _ScriptedSession:
    def __init__(self, results):
        self.results = list(results)
        self.executions = []

    async def execute(self, statement, params=None):
        self.executions.append((statement, params))
        assert self.results, "unexpected database execute"
        return self.results.pop(0)


def _match_by_code_row(sentinels):
    p1_id = UUID("11111111-1111-1111-1111-111111111111")
    p2_id = UUID("22222222-2222-2222-2222-222222222222")
    row = defaultdict(lambda: None)
    row.update(
        {
            "id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "ended_at": datetime(2026, 9, 2, 12, tzinfo=timezone.utc),
            "is_ranked": True,
            "invalidated_at": None,
            "invalidation_reason": None,
            "p1_rounds_won": 5,
            "p2_rounds_won": 3,
            "p1_points_total": 12,
            "p2_points_total": 8,
            "duration_seconds": 240,
            "player1_id": p1_id,
            "player2_id": p2_id,
            "winner_id": p1_id,
            "p1_sid": "76561198000000001",
            "p2_sid": "76561198000000002",
            "p1_name": "Player One",
            "p2_name": "Player Two",
            "s_p1_id": None,
            "series_status": None,
        }
    )
    row.update(sentinels)
    return row


def test_sentinel_exercised_match_lookup_never_serializes_private_columns():
    sentinels = storage_sentinels()
    session = _ScriptedSession(
        [
            _ScriptedResult(row=_match_by_code_row(sentinels)),
            _ScriptedResult(rows=[]),
            _ScriptedResult(rows=[]),
        ]
    )
    payload = asyncio.run(main.get_match_by_code("aaaaaaaaaaaa", db=session))

    assert payload["mode"] == "1v1"
    assert len(session.executions) == 3
    assert_no_net_seat_sentinels(payload, sentinels)
    source = inspect.getsource(main.get_match_by_code)
    assert all(name not in source for name in STORAGE_FIELDS)


class _DiscordContext:
    def __init__(self):
        self.deferred = False
        self.sent = []

    async def defer(self):
        self.deferred = True

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


def _discord_game(sentinels):
    game = {
        "mode": "1v1",
        "code": "AAAAAAAAAAAA",
        "match_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "ended_at": "2026-09-02T12:00:00Z",
        "is_ranked": True,
        "invalidated": False,
        "invalidation_reason": None,
        "duration_seconds": 240,
        "series_status": "completed",
        "players": [
            {
                "steam_id": "76561198000000001",
                "name": "Player One",
                "rounds_won": 5,
                "points_total": 12,
                "won": True,
                "cards": ["Grow"],
            },
            {
                "steam_id": "76561198000000002",
                "name": "Player Two",
                "rounds_won": 3,
                "points_total": 8,
                "won": False,
                "cards": ["Quick Reload"],
            },
        ],
    }
    # Deliberately hand the formatter private fields at multiple depths. It
    # must still render from its explicit allowlist rather than stringifying.
    game.update(sentinels)
    game["players"][0].update(sentinels)
    return game


def test_discord_game_formatter_does_not_consume_net_seat_columns(monkeypatch):
    import discord_bot

    sentinels = storage_sentinels()
    game = _discord_game(sentinels)

    async def fake_api_get(_path):
        return game

    monkeypatch.setattr(discord_bot, "api_get", fake_api_get)
    monkeypatch.setattr(discord_bot, "_MPL_AVAILABLE", False)
    context = _DiscordContext()
    callback = getattr(discord_bot.cmd_game, "callback", discord_bot.cmd_game)
    asyncio.run(callback(context, "aaaaaaaaaaaa"))

    assert context.deferred
    assert len(context.sent) == 1
    embed = context.sent[0][1]["embed"]
    assert_no_net_seat_sentinels(embed.to_dict(), sentinels)
    source = inspect.getsource(callback)
    assert all(name not in source for name in STORAGE_FIELDS)


def _flag_row(sentinels, reviewed: bool):
    row = defaultdict(lambda: None)
    row.update(
        {
            "id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "discord_evidence_revision": 1,
            "match_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "context_series_id": None,
            "flag_reason": "inactive_player",
            "flag_details": {
                "reporter_steam": "76561198000000001",
                "shots": 0,
                "blocks": 0,
                "cards_picked": 0,
            },
            "auto_invalidated": False,
            "invalidated_at": None,
            "invalidation_reason": None,
            "restoration_required": False,
            "p1_steam_id": "76561198000000001",
            "p2_steam_id": "76561198000000002",
            "p1_name": "Player One",
            "p2_name": "Player Two",
            "is_ranked": True,
            "duration": 240,
            "p1_rounds_won": 5,
            "p2_rounds_won": 3,
            "p1_points_total": 12,
            "p2_points_total": 8,
            "p1_card_count": 1,
            "p2_card_count": 1,
            "p1_cards": "Grow",
            "p2_cards": "Quick Reload",
            "point_timeline": None,
            "point_times": None,
            "reporter_name": "Player One",
            "reporter_steam_id": "76561198000000001",
            "reporter_mod_version": "1.40.0",
            "game_version": "1.40.0",
            "region": "us",
            "photon_room_id": "ranked_fixture",
            "reviewed_at": (
                datetime(2026, 9, 2, 13, tzinfo=timezone.utc) if reviewed else None
            ),
            "review_action": "confirmed" if reviewed else None,
            "created_at": datetime(2026, 9, 2, 12, tzinfo=timezone.utc),
        }
    )
    row.update(sentinels)
    return row


def test_flag_and_review_formatters_do_not_consume_net_seat_columns():
    sentinels = storage_sentinels()
    for reviewed in (False, True):
        payload = flag_evidence.flag_payload(_flag_row(sentinels, reviewed))
        if reviewed:
            assert payload["reviewed_at"] is not None
        else:
            assert payload["reviewed_at"] is None
        assert_no_net_seat_sentinels(payload, sentinels)

    source = inspect.getsource(flag_evidence.flag_payload)
    query_source = inspect.getsource(flag_evidence.fetch_flag_context_rows)
    assert all(name not in source for name in STORAGE_FIELDS)
    assert all(name not in query_source for name in STORAGE_FIELDS)
