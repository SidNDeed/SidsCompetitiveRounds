"""Exhaustive API-route and formatter non-consumer gate for W1 telemetry."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha1
import ast
import inspect
import sys
import textwrap
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
#
# r8 LOW 5 introduced this as a hand-written dict, and r11 found the hole that
# shape always has: it held one entry, and the release that moved
# _pick_room_region — which decides the region both seats of a pair are told to
# connect to — left the two routes that return it certified unchanged, because
# their own source had not moved. A list of exceptions fails precisely when
# someone extracts a helper, which is the case it exists for.
#
# So the closure is computed instead. It is affordable: this api has 692
# module-level functions and the transitive closure of a route is 6 of them at
# the median, 21 at p90 and 92 at the worst (/api/v1/matches) -- a gate that
# drifted on every commit would be a gate nobody reads. Re-measure these
# numbers when the walk changes shape; they were 4/17/52 of 608 before r13 M8
# widened it to imported helpers, and a stale figure here is the kind of claim
# the gate itself exists to catch.
_SERVED_MODULES = {}


def _served_modules():
    """Every module that DEFINES a route this gate enumerates.

    r12 MEDIUM. The closure below used to be computed over `vars(main)` alone,
    and `main` is not where all of this api lives: tournaments defines its own
    routes and the helpers those routes delegate to. A change to a tournaments
    helper -- `_build_current_response` composes what a tournament route
    returns -- therefore moved no fingerprint at all, and the gate certified
    every one of those handlers unchanged. Following helpers transitively
    inside one module is not the same as following them, and this gate's whole
    claim is that implementation drift forces a re-review.

    Discovered from the app's own routes rather than listed, for the same
    reason the closure is computed rather than curated: a list is wrong the
    first time someone adds a router."""
    if _SERVED_MODULES:
        return _SERVED_MODULES
    _SERVED_MODULES["main"] = main
    stack = list(main.app.routes)
    while stack:
        route = stack.pop()
        if isinstance(route, Mount):
            stack.extend(route.routes)
            continue
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        name = getattr(endpoint, "__module__", None)
        module = sys.modules.get(name)
        if module is not None:
            _SERVED_MODULES.setdefault(name, module)
    return _SERVED_MODULES


API_DIR = (Path(__file__).parents[1] / "api").resolve()


def _is_ours(fn):
    """Whether a function is part of THIS api's source rather than a library's.

    The filter used to be `__module__ == <the module we found it in>`, which
    silently meant "defined here". r13 MEDIUM: `tournaments` imports
    `build_double_elim_bracket` from `tournament_bracket` and calls it from a
    route, so under that rule the function that lays out a bracket was in no
    route's fingerprint at all. What actually matters is whether the source is
    ours to review, and the file says so."""
    try:
        path = Path(inspect.getfile(fn)).resolve()
    except (TypeError, OSError):
        return False
    return path.parent == API_DIR


_MODULE_FUNCTIONS_CACHE = {}


def _module_functions(extra_modules=()):
    """{(module-as-seen, name): function} over every served module, plus any
    module a walk has stepped into. Keyed by the module the NAME is spelled in,
    which is how a reference resolves; the function it points at may be defined
    anywhere in this api."""
    modules = dict(_served_modules())
    for mod_name in extra_modules:
        module = sys.modules.get(mod_name)
        if module is not None:
            modules.setdefault(mod_name, module)
    key = frozenset(modules)
    cached = _MODULE_FUNCTIONS_CACHE.get(key)
    if cached is not None:
        return cached
    table = {}
    for mod_name, module in modules.items():
        for name, obj in vars(module).items():
            if inspect.isfunction(obj) and _is_ours(obj):
                table[(mod_name, name)] = obj
    _MODULE_FUNCTIONS_CACHE[key] = table
    return table


def _identity(fn):
    """What a helper IS, independent of the names it is imported under."""
    return (getattr(fn, "__module__", "?"), getattr(fn, "__qualname__", "?"))


_REFERENCED_NAMES_CACHE = {}


def _referenced_names(fn):
    """Every bare name and attribute name mentioned in a function's source.
    Deliberately over-inclusive: a name that happens to match a module-level
    function is folded in even if it was never called, which can only widen the
    reviewed surface, never narrow it."""
    cached = _REFERENCED_NAMES_CACHE.get(fn)
    if cached is not None:
        return cached
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, TypeError, SyntaxError, IndentationError):
        _REFERENCED_NAMES_CACHE[fn] = frozenset()
        return _REFERENCED_NAMES_CACHE[fn]
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    # Frozen and cached: this is a pure function of the source on disk, and the
    # walk asks it for the same helpers once per route.
    _REFERENCED_NAMES_CACHE[fn] = frozenset(names)
    return _REFERENCED_NAMES_CACHE[fn]


def _walk_helper_functions(endpoint):
    """{(defining module, qualname): function} for everything a route reaches.

    A bare name is resolved in the module the referencing function is written
    in first, and in any other module this walk knows after that -- on a name
    two modules share, the second one is folded in as well, which widens the
    reviewed surface rather than narrowing it. Keyed by what the helper IS, so
    the same function imported under two names is one entry and its source is
    appended once.

    The walk STEPS INTO the modules it lands in: reaching a function defined in
    tournament_bracket brings that module's own helpers into scope for the rest
    of the walk, which is what makes this transitive across files and not just
    across the two modules that happen to serve routes."""
    walked = {"main"}
    walked.update(_served_modules())
    funcs = _module_functions(walked)
    seen = {}
    frontier = [endpoint]
    while frontier:
        fn = frontier.pop()
        origin = getattr(fn, "__module__", "main")
        if origin not in walked and sys.modules.get(origin) is not None:
            walked.add(origin)
            funcs = _module_functions(walked)
        lookup = [origin] + [m for m in walked if m != origin]
        for name in _referenced_names(fn):
            for mod_name in lookup:
                helper = funcs.get((mod_name, name))
                if helper is None:
                    continue
                ident = _identity(helper)
                if ident not in seen:
                    seen[ident] = helper
                    frontier.append(helper)
    return seen


_CLOSURE_CACHE = {}


def _helper_functions(endpoint):
    """Memoised wrapper: the closure of one endpoint is asked for by the
    manifest build, by the affordability test and by every assertion below."""
    cached = _CLOSURE_CACHE.get(endpoint)
    if cached is None:
        cached = _walk_helper_functions(endpoint)
        _CLOSURE_CACHE[endpoint] = cached
    return cached


def _helper_closure(endpoint):
    """The identities alone, sorted -- (defining module, qualname)."""
    return sorted(_helper_functions(endpoint))

MODULE_SRC = (Path(__file__).parents[1] / "api" / "main.py").read_text(encoding="utf-8")

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
        # A handler's fingerprint covers the module-level helpers it delegates
        # to, transitively — an extracted helper must not become a fingerprint
        # hole. Sorted, so the fingerprint does not depend on walk order.
        source_text = inspect.getsource(endpoint)
        helpers = _helper_functions(endpoint)
        for ident in sorted(helpers):
            try:
                source_text += inspect.getsource(helpers[ident])
            except (OSError, TypeError):
                continue
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
    assert len(manifest) == 309
    assert len({json.dumps(item, sort_keys=True) for item in expected}) == len(expected)
    assert all(
        entry["classification"] in {"sentinel-exercised", "statically-nonconsumer"}
        for entry in manifest
    )
    assert all(isinstance(entry["reason"], str) and entry["reason"].strip() for entry in manifest)

    exercised = [entry for entry in manifest if entry["classification"] == "sentinel-exercised"]
    static = [entry for entry in manifest if entry["classification"] == "statically-nonconsumer"]
    assert len(exercised) == 1
    assert len(static) == 308
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


def test_the_helper_surface_is_computed_and_not_hand_curated():
    """r11. The coverage rule was a dict with one entry, so it failed exactly
    where it was written to help: this range moved _pick_room_region, which
    decides the region both seats of a pair are told to connect to, and the two
    routes that return it kept their pre-range fingerprints because their own
    source had not changed. A list of exceptions is a hole the next extraction
    reopens silently."""
    assert not hasattr(main, "ROUTE_HELPER_DEPENDENCIES")
    assert "ROUTE_HELPER_DEPENDENCIES" not in MODULE_SRC, (
        "the hand-curated list came back"
    )
    # The closure is real: the two queue routes now carry the region helpers
    # they delegate to, transitively.
    for route_name, expected in (
        ("queue_poll", {"_pick_room_region", "_region_agreed", "_region_corroborated"}),
        ("queue_ready", {"_pick_room_region", "_region_agreed", "_region_corroborated"}),
        # the sighting moved off queue_join in r13: an established session
        # binds the speaker, not the region named in the sentence
        ("submit_match", {"_note_region_seen", "_region_token"}),
    ):
        closure = set(_helper_closure(getattr(main, route_name)))
        want = {("main", name) for name in expected}
        assert want <= closure, (
            f"{route_name} does not cover {sorted(want - closure)}"
        )

    # r12 MEDIUM: and the closure leaves `main`. A tournaments route reaches
    # the tournaments helpers that compose its response, so editing one of
    # those moves that route's fingerprint.
    tournament_routes = [
        r for r in main.app.routes
        if isinstance(r, APIRoute)
        and getattr(r.endpoint, "__module__", "") == "tournaments"
    ]
    assert tournament_routes, "the tournaments router is part of this app"
    crossed = [(m, n) for r in tournament_routes
               for (m, n) in _helper_closure(r.endpoint) if m != "main"]
    assert crossed, "the closure never left main -- helpers there are unfingerprinted"

    # r13 MEDIUM: and it reaches helpers that are IMPORTED rather than defined
    # in the module serving the route. `tournaments` calls
    # tournament_bracket.build_double_elim_bracket from a route; keeping only
    # functions whose __module__ matched the module they were found in put that
    # function -- which decides a bracket's shape -- in no fingerprint at all.
    imported = [ident for r in tournament_routes
                for ident in _helper_closure(r.endpoint)
                if ident[0] not in ("main", "tournaments")]
    assert imported, "the closure never left the two route-serving modules"


def test_a_helper_in_another_module_moves_its_routes_fingerprint():
    """The mutation the previous test's shape is for. Rewrite the body of a
    tournaments helper that a route delegates to and that route's source_sha1
    must move; the negative control is the same route with nothing edited."""
    import tournaments

    target = None
    for route in main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        if getattr(route.endpoint, "__module__", "") != "tournaments":
            continue
        helpers = [n for (m, n) in _helper_closure(route.endpoint) if m == "tournaments"]
        if helpers:
            target = (route, sorted(helpers)[0])
            break
    assert target, "no tournaments route delegates to a tournaments helper"
    route, helper_name = target

    def _fingerprint():
        for entry in _route_identities([route]):
            return entry["source_sha1"]
        raise AssertionError("the route did not enumerate")

    before = _fingerprint()
    assert before == _fingerprint(), "negative control: unedited source must not move"

    original = getattr(tournaments, helper_name)
    real_source = inspect.getsource

    def _mutated(obj):
        if obj is original:
            return real_source(obj) + "\n# mutation\n"
        return real_source(obj)

    inspect.getsource = _mutated
    try:
        after = _fingerprint()
    finally:
        inspect.getsource = real_source
    assert after != before, (
        f"editing tournaments.{helper_name} left {route.path} certified unchanged"
    )


def test_the_helper_closure_stays_affordable():
    """A fingerprint that pulls half the module in drifts on every commit, and
    a gate that always fires is a gate nobody reads. Measured at the shape this
    file walks now: 6 helpers at the median of 692 module-level functions, 21 at
    p90, 92 at the worst. The bounds below sit above those with room, so this
    fails on a walk that has gone wrong rather than on ordinary growth.

    Cost is the other half of affordable, and it is not free: the same helpers
    are reached from hundreds of routes, so both pure steps (`_referenced_names`
    over a function's ast, `_module_functions` over a set of modules) are
    memoised. Without those the widened walk took 287 s and this file was the
    slowest thing in the suite by an order of magnitude; with them it is ~10 s.
    Anything added to the walk belongs behind a memo too."""
    routes = [r for r in main.app.routes
              if isinstance(r, APIRoute) and r.path.startswith("/api/v1/")]
    assert routes
    sizes = sorted(len(_helper_closure(r.endpoint)) for r in routes)
    total = len(_module_functions())
    assert sizes[len(sizes) // 2] <= 12, f"median closure {sizes[len(sizes) // 2]} of {total}"
    assert sizes[-1] <= 120, f"worst closure {sizes[-1]} of {total}"


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


def test_an_imported_helper_moves_the_fingerprint_of_the_route_that_calls_it():
    """r13 MEDIUM, mutation-proven on the case the finding names: a function
    DEFINED in tournament_bracket and IMPORTED into tournaments, reached from a
    route. Editing it must move that route's fingerprint; the negative control
    is the same route with nothing edited."""
    import tournament_bracket

    target = None
    for route in main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        idents = _helper_closure(route.endpoint)
        outside = [i for i in idents if i[0] == "tournament_bracket"]
        if outside:
            target = (route, sorted(outside)[0])
            break
    assert target, "no route reaches a helper defined in tournament_bracket"
    route, (mod_name, qualname) = target
    original = getattr(tournament_bracket, qualname)

    def _fingerprint():
        for entry in _route_identities([route]):
            return entry["source_sha1"]
        raise AssertionError("the route did not enumerate")

    before = _fingerprint()
    assert before == _fingerprint(), "negative control: unedited source must not move"

    real_source = inspect.getsource

    def _mutated(obj):
        if obj is original:
            return real_source(obj) + "\n# mutation\n"
        return real_source(obj)

    inspect.getsource = _mutated
    try:
        after = _fingerprint()
    finally:
        inspect.getsource = real_source
    assert after != before, (
        f"editing {mod_name}.{qualname} left {route.path} certified unchanged"
    )
