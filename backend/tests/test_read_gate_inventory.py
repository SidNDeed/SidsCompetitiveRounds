"""Verified reads: the read gate's route inventory, counted from the live app.

Three questions, each answered from `main.app.routes` and the source the
route-manifest gate already indexes (test_route_manifest_net_seat's binding
index and closure walk, imported, not copied):

  1. Does every GET route carry `read_gate` exactly once? (requirement 4)
  2. Is every GET route in exactly one class, with no stale list entry, and
     does every route that reaches a player-session check sit in a class that
     says so? (requirement 5)
  3. Is every GET route whose handler can reach a write either WRITE_ON_GET,
     or reviewed with the exact writer bindings its reason explains?
     (requirement 3)

Each checker is a function that RETURNS what it found, so the negative
controls at the bottom can run the same function on a scratch app or a
scratch module and require it to report the planted defect.
"""
from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from starlette.routing import Mount

import main
import read_gate
import test_route_manifest_net_seat as M

TRUNK_GET_FLOOR = 182          # GET routes on trunk 0e751993 before this lane

SESSION_PRIMITIVES = frozenset({("main", n) for n in (
    "_check_steam_session", "_strict_steam_session_ok", "_seat_attestation_verdict",
    "_session_seat")})
ADMIN_PRIMITIVES = frozenset({("main", n) for n in ("_require_admin", "_verify_admin_hmac",
                                                     "_is_admin")})
PORTAL_PRIMITIVES = frozenset({("main", "_portal_auth")})

# The session check's one-time arming stamp is the one write a session-reached
# route may reach and still not be WRITE_ON_GET: it is written only for a
# presented, verified session, which every class the gate acts on admits.
SESSION_STAMP = "_check_steam_session"


def _get_routes(routes, prefix=""):
    out = []
    for r in routes:
        if isinstance(r, Mount):
            out.extend(_get_routes(r.routes, M._joined_path(prefix, r.path)))
        elif isinstance(r, APIRoute) and "GET" in (r.methods or ()):
            out.append(r)
    return out


def _gate_occurrences(route) -> int:
    n = 0
    stack = list(route.dependant.dependencies)
    while stack:
        d = stack.pop()
        if d.call is read_gate.read_gate:
            n += 1
        stack.extend(d.dependencies)
    return n


def check_exactly_once(routes) -> dict:
    """{path: occurrences} for every GET route that does not carry the gate
    exactly once."""
    return {r.path: c for r in _get_routes(routes) if (c := _gate_occurrences(r)) != 1}


# -- requirement 4 ------------------------------------------------------------

def test_fastapi_is_the_pinned_version():
    import fastapi
    assert fastapi.__version__ == M.PINNED_FASTAPI


def test_read_gate_exactly_once():
    gets = _get_routes(main.app.routes)
    assert len(gets) >= TRUNK_GET_FLOOR
    tournaments = [r for r in gets if r.path.startswith("/api/v1/tournaments/")]
    ladders = [r for r in gets if r.path == "/api/v1/players/{steam_id}/title-ladders"]
    assert tournaments and ladders            # the included routers are in the walk
    assert check_exactly_once(main.app.routes) == {}


def test_exactly_once_controls():
    async def h():
        return {}

    # (a) a GET added with the plain APIRoute class carries no gate: reported
    plain = FastAPI()
    plain.router.add_api_route("/api/v1/zz/plain", h, methods=["GET"])
    assert check_exactly_once(plain.routes) == {"/api/v1/zz/plain": 0}

    # (b) a router built with the gate's route class and included twice: the
    # guard keeps one copy ...
    router = APIRouter(prefix="/api/v1/zz", route_class=read_gate.ReadGateRoute)
    router.add_api_route("/r", h, methods=["GET"])
    outer = APIRouter(route_class=read_gate.ReadGateRoute)
    outer.include_router(router)
    app = FastAPI()
    app.router.route_class = read_gate.ReadGateRoute
    app.include_router(outer)
    assert check_exactly_once(app.routes) == {}

    # ... and the same construction WITHOUT the guard doubles it: reported
    class Unguarded(APIRoute):
        def __init__(self, path, endpoint, **kw):
            if "GET" in {m.upper() for m in (kw.get("methods") or ["GET"])}:
                kw["dependencies"] = [Depends(read_gate.read_gate)] + list(kw.get("dependencies") or ())
            super().__init__(path, endpoint, **kw)
    router2 = APIRouter(prefix="/api/v1/zz", route_class=Unguarded)
    router2.add_api_route("/r", h, methods=["GET"])
    app2 = FastAPI()
    app2.include_router(router2)
    assert check_exactly_once(app2.routes) == {"/api/v1/zz/r": 2}


def test_write_routes_are_not_given_the_gate():
    posts = [r for r in main.app.routes if isinstance(r, APIRoute) and "GET" not in r.methods]
    assert posts and all(_gate_occurrences(r) == 0 for r in posts)


# -- requirement 5 ------------------------------------------------------------

NAMED = {
    "OPEN": set(read_gate.OPEN),
    "WRITE_ON_GET": set(read_gate.WRITE_ON_GET),
    "ADMIN_SIGNED": set(read_gate.ADMIN_SIGNED),
    "PORTAL": set(read_gate.PORTAL),
    "INTERNAL_NAMED": set(read_gate.INTERNAL_NAMED),
    "BOT_ONLY": set(read_gate.BOT_ONLY),
    "PLAYER": set(read_gate.PLAYER),
    "PROBE": set(read_gate.PROBE),
}


def check_classes(routes, named=None, index=None) -> list[str]:
    """Every problem with the classification of `routes`, as sentences."""
    named = NAMED if named is None else named
    problems = []
    names = list(named)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            both = named[a] & named[b]
            if both:
                problems.append(f"{sorted(both)} is in both {a} and {b}")
    for name, entries in named.items():
        if name == "INTERNAL_NAMED":
            continue
        prefixed = {e for e in entries if e.startswith(read_gate.INTERNAL_PREFIX)}
        if prefixed:
            problems.append(f"{sorted(prefixed)} in {name} is also INTERNAL by prefix")
    live = {r.path for r in _get_routes(routes)}
    for name, entries in named.items():
        stale = entries - live
        if stale:
            problems.append(f"stale {name} entries: {sorted(stale)}")
    for r in _get_routes(routes):
        reached = set(M._walk_bindings(M._route_seeds(r), index)) if index is not None else set(
            M._reached(M._route_seeds(r)))
        cls = read_gate.route_class(r.path)
        if reached & SESSION_PRIMITIVES and cls not in (
                read_gate.C_PLAYER, read_gate.C_ADMIN_SIGNED, read_gate.C_PORTAL,
                read_gate.C_WRITE_ON_GET, read_gate.C_INTERNAL):
            problems.append(f"{r.path} reaches a player-session check but is {cls}")
        if cls == read_gate.C_PLAYER and not reached & SESSION_PRIMITIVES:
            problems.append(f"{r.path} is PLAYER but reaches no session check")
        if cls == read_gate.C_ADMIN_SIGNED and not reached & ADMIN_PRIMITIVES:
            problems.append(f"{r.path} is ADMIN_SIGNED but reaches no admin check")
        if cls == read_gate.C_PORTAL and not reached & PORTAL_PRIMITIVES:
            problems.append(f"{r.path} is PORTAL but reaches no portal check")
    return problems


def review_report(routes) -> list[str]:
    """Routes that reach an admin or portal check outside those classes:
    reported for review, not failed (they are gated by default, the
    conservative direction)."""
    out = []
    for r in _get_routes(routes):
        reached = set(M._reached(M._route_seeds(r)))
        cls = read_gate.route_class(r.path)
        if reached & ADMIN_PRIMITIVES and cls != read_gate.C_ADMIN_SIGNED:
            out.append(f"{r.path} reaches an admin check and is {cls}")
        if reached & PORTAL_PRIMITIVES and cls != read_gate.C_PORTAL:
            out.append(f"{r.path} reaches the portal check and is {cls}")
    return out


def test_read_gate_inventory(capsys):
    gets = _get_routes(main.app.routes)
    assert len(gets) >= TRUNK_GET_FLOOR, len(gets)
    assert check_classes(main.app.routes) == []
    counts = {}
    for r in gets:
        counts[read_gate.route_class(r.path)] = counts.get(read_gate.route_class(r.path), 0) + 1
    with capsys.disabled():
        print(f"\n[read-gate inventory] {len(gets)} GET routes: "
              + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        for line in review_report(main.app.routes):
            print("[read-gate review] " + line)
    assert sum(counts.values()) == len(gets)
    for t in read_gate.OPEN:
        assert read_gate.OPEN[t].strip()
    assert counts[read_gate.C_OPEN] == len(read_gate.OPEN) == 9


def test_inventory_controls(tmp_path):
    """(a) a stale list entry and an overlap are reported; (b) a GET whose
    handler calls the session check, left in the default class, is reported."""
    named = {k: set(v) for k, v in NAMED.items()}
    named["PLAYER"].add("/api/v1/zz/no-such-route")
    named["OPEN"].add(next(iter(read_gate.PLAYER)))
    problems = check_classes(main.app.routes, named)
    assert any("stale PLAYER" in p for p in problems)
    assert any("in both OPEN and PLAYER" in p for p in problems)

    src = tmp_path / "zz_scratch_mod.py"
    src.write_text(textwrap.dedent('''
        async def zz_scratch_handler(request, db):
            await _check_steam_session(request, "0", db)
            return {}
    '''), encoding="utf-8")
    index = dict(M._binding_index())
    index["zz_scratch_mod"] = M._index_module(src)

    async def zz_scratch_handler():
        return {}
    app = FastAPI()
    app.router.add_api_route("/api/v1/zz/scratch-session", zz_scratch_handler, methods=["GET"])
    route = app.routes[-1]
    seeds = [("zz_scratch_mod", "zz_scratch_handler")]
    reached = set(M._walk_bindings(seeds, index))
    assert reached & SESSION_PRIMITIVES                      # the walk sees the session check
    assert read_gate.route_class(route.path) == read_gate.C_PUBLIC
    # the checker's own rule, applied to the scratch route's closure
    problems = []
    if reached & SESSION_PRIMITIVES and read_gate.route_class(route.path) not in (
            read_gate.C_PLAYER, read_gate.C_ADMIN_SIGNED, read_gate.C_PORTAL,
            read_gate.C_WRITE_ON_GET, read_gate.C_INTERNAL):
        problems.append(route.path)
    assert problems == ["/api/v1/zz/scratch-session"]


# -- requirement 3: WRITE_ON_GET ----------------------------------------------

# No TRUNCATE: the api runs none, and the word is common in its prose.
_SQL_WRITE = re.compile(r"\b(INSERT\s+INTO|UPDATE\s+[\w.\"]+\s+SET|DELETE\s+FROM|MERGE\s+INTO)\b",
                        re.I)
_TEXT_COMMIT = re.compile(r"\.commit\(")
_TEXT_ORM = re.compile(r"\b(\w*db|\w*session|\w*sess|conn|tx)\.(add|add_all|delete|merge)\(")
_EXEC_WRITE_HEAD = re.compile(r"^\s*(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|CREATE|ALTER|DROP|CALL)\b",
                              re.I)
_SESSIONISH = re.compile(r"^(\w*db|\w*session|\w*sess|conn|s|tx)$")
_CORE_WRITERS = {"pg_insert", "insert", "update", "delete"}


def write_markers(source: str) -> set[str]:
    """The write shapes in one binding's source: a commit, an ORM add/delete
    on a session, a SQLAlchemy core insert/update/delete, an execute() of
    text that does not begin with a read, or SQL text that writes."""
    if not source.strip():
        return set()
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        # A binding inside a module-level block carries its block's header
        # (the manifest index prepends it), which does not parse alone: scan
        # the text for the same shapes instead.
        out = set()
        if _TEXT_COMMIT.search(source):
            out.add("commit")
        if _TEXT_ORM.search(source):
            out.add("orm")
        if _SQL_WRITE.search(source):
            out.add("sql")
        return out
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute):
                if f.attr == "commit":
                    out.add("commit")
                elif f.attr in ("add", "add_all", "delete", "merge"):
                    recv = ast.unparse(f.value)
                    model_arg = any(isinstance(a, ast.Call) and isinstance(a.func, ast.Name)
                                    and a.func.id[:1].isupper() for a in node.args)
                    if _SESSIONISH.match(recv) or model_arg:
                        out.add("orm:" + f.attr)
                elif f.attr == "execute" and node.args:
                    a0 = node.args[0]
                    if (isinstance(a0, ast.Call) and isinstance(a0.func, ast.Name)
                            and a0.func.id == "text" and a0.args
                            and isinstance(a0.args[0], ast.Constant)
                            and isinstance(a0.args[0].value, str)
                            and _EXEC_WRITE_HEAD.match(a0.args[0].value)):
                        out.add("exec")
            elif isinstance(f, ast.Name) and f.id in _CORE_WRITERS:
                out.add("core:" + f.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _SQL_WRITE.search(node.value):
                out.add("sql")
    return out


_MARKER_MEMO: dict = {}


def writers_reached(seeds, index=None) -> dict:
    """{binding name: markers} for every binding the seeds reach that writes."""
    reached = M._walk_bindings(seeds, index) if index is not None else M._reached(seeds)
    out = {}
    for key in reached:
        if index is not None:
            binding = index.get(key[0], {}).get(key[1])
            text_ = binding[1] if binding else ""
        else:
            text_ = M._segment(*key)
        memo_key = (key, hash(text_))
        if memo_key not in _MARKER_MEMO:
            _MARKER_MEMO[memo_key] = write_markers(text_)
        if _MARKER_MEMO[memo_key]:
            out[key[1]] = _MARKER_MEMO[memo_key]
    return out


def check_write_on_get(routes, write_on_get=None, reviewed=None, index=None, seeds_of=None) -> list[str]:
    write_on_get = read_gate.WRITE_ON_GET if write_on_get is None else write_on_get
    reviewed = read_gate.WRITE_REVIEWED if reviewed is None else reviewed
    seeds_of = seeds_of or (lambda r: [M._binding_key(r.endpoint)])
    problems = []
    flagged = {}
    by_path = {r.path: r for r in _get_routes(routes)}
    for path, r in by_path.items():
        w = writers_reached(seeds_of(r), index)
        if w:
            flagged[path] = w
    for path, w in sorted(flagged.items()):
        if path in write_on_get:
            continue
        if path not in reviewed:
            problems.append(f"{path} reaches writers {sorted(w)} and is neither WRITE_ON_GET "
                            f"nor reviewed")
            continue
        unexplained = set(w) - set(reviewed[path][0])
        if unexplained:
            problems.append(f"{path} reaches writers its review does not explain: "
                            f"{sorted(unexplained)}")
        seeds = seeds_of(by_path[path])
        reached = set(M._walk_bindings(seeds, index) if index is not None else M._reached(seeds))
        # Session-reached and a writer is WRITE_ON_GET. The two exceptions are
        # not writes BY this route: the session check's own arming stamp, and
        # the trade statements reached as data.
        if reached & SESSION_PRIMITIVES and set(w) - {SESSION_STAMP, "_PC_TRADE_CLAIM_SQL",
                                                      "_PC_TRADE_MOVE_SQL"}:
            problems.append(f"{path} is session-reached and a writer but not WRITE_ON_GET")
    for path in sorted(set(write_on_get) | set(reviewed)):
        if path in by_path and path not in flagged:
            problems.append(f"{path} is listed but the inventory finds no writer")
    return problems, flagged


def test_write_on_get_inventory(capsys):
    problems, flagged = check_write_on_get(main.app.routes)
    with capsys.disabled():
        print(f"\n[write-on-get inventory] {len(flagged)} GET routes reach a writer; "
              f"WRITE_ON_GET {len(read_gate.WRITE_ON_GET)}, reviewed {len(read_gate.WRITE_REVIEWED)}")
    assert problems == []
    # the required proof: the series-state GET that cancels and reconciles
    w = flagged["/api/v1/team/series/{series_id}/state"]
    assert "team_series_state" in w and "commit" in w["team_series_state"]
    assert read_gate.route_class("/api/v1/team/series/{series_id}/state") == read_gate.C_WRITE_ON_GET
    for t, reason in read_gate.WRITE_ON_GET.items():
        assert reason.strip(), t
    for t, (writers, reason) in read_gate.WRITE_REVIEWED.items():
        assert writers and reason.strip(), t


def test_write_on_get_controls(tmp_path):
    # removing the required route from the class is reported
    smaller = {k: v for k, v in read_gate.WRITE_ON_GET.items()
               if k != "/api/v1/team/series/{series_id}/state"}
    problems, _ = check_write_on_get(main.app.routes, write_on_get=smaller)
    assert any(p.startswith("/api/v1/team/series/{series_id}/state reaches writers") for p in problems)

    # a scratch GET whose handler calls a helper that commits, unclassified
    src = tmp_path / "zz_writer_mod.py"
    src.write_text(textwrap.dedent('''
        async def zz_writer_helper(db):
            await db.execute(text("SELECT 1"))
            await db.commit()

        async def zz_reader_handler(db):
            await zz_writer_helper(db)
            return {}
    '''), encoding="utf-8")
    index = dict(M._binding_index())
    index["zz_writer_mod"] = M._index_module(src)

    async def zz_reader_handler():
        return {}
    app = FastAPI()
    app.router.add_api_route("/api/v1/zz/reader", zz_reader_handler, methods=["GET"])
    problems, flagged = check_write_on_get(
        app.routes, index=index, seeds_of=lambda r: [("zz_writer_mod", "zz_reader_handler")])
    assert flagged == {"/api/v1/zz/reader": {"zz_writer_helper": {"commit"}}}
    assert problems == ["/api/v1/zz/reader reaches writers ['zz_writer_helper'] and is neither "
                        "WRITE_ON_GET nor reviewed"]

    # the same route classified WRITE_ON_GET is accepted
    problems, _ = check_write_on_get(
        app.routes, write_on_get={"/api/v1/zz/reader": "commits"}, index=index,
        seeds_of=lambda r: [("zz_writer_mod", "zz_reader_handler")])
    assert problems == []


@pytest.mark.parametrize("source,expected", [
    ("async def f(db):\n    await db.commit()\n", {"commit"}),
    ("def f(seen):\n    seen.add(1)\n", set()),
    ("def f(db):\n    db.add(Player(id=1))\n", {"orm:add"}),
    ("def f(db):\n    return db.execute(text('SELECT 1 FROM x FOR UPDATE'))\n", set()),
    ("X = 'UPDATE players SET a = 1'\n", {"sql"}),
    ("X = 'SELECT 1 FROM t FOR NO KEY UPDATE OF p SKIP LOCKED'\n", set()),
    ("def f(db):\n    return db.execute(pg_insert(T).values(a=1))\n", {"core:pg_insert"}),
])
def test_write_markers_shapes(source, expected):
    assert write_markers(source) == expected


# -- requirement 5: the design's 30 PLAYER templates, reconciled --------------
#
# Design section 3.2 named 30 trunk GET templates PLAYER (every GET whose
# handler reaches a player-session primitive). Each is mapped here to the
# class it holds. 16 are PLAYER. The other 14 are WRITE_ON_GET: each is both
# session-reached and a writer, and requirement 3 classes such a route
# WRITE_ON_GET, where the gate takes no action in any stage and the handler's
# own session requirement stands exactly as on trunk (each one's write is
# named in read_gate.WRITE_ON_GET). No other superseding class is used.

C_PLAYER, C_WOG = read_gate.C_PLAYER, read_gate.C_WRITE_ON_GET
DESIGN_PLAYER_30 = {
    "/api/v1/h2h/{steam_id}/{opponent_steam_id}": C_PLAYER,
    "/api/v1/presence/ping": C_WOG,
    "/api/v1/queue/poll/{steam_id}": C_WOG,
    "/api/v1/pc/packs/result": C_WOG,
    "/api/v1/pc/packs": C_PLAYER,
    "/api/v1/pc/me": C_PLAYER,
    "/api/v1/pc/collection": C_PLAYER,
    "/api/v1/pc/card": C_PLAYER,
    "/api/v1/pc/trades": C_PLAYER,
    "/api/v1/music/ratings/mine": C_WOG,
    "/api/v1/artist/{steam_id}/items": C_PLAYER,
    "/api/v1/artist/{steam_id}/sales": C_PLAYER,
    "/api/v1/artist/my-submissions": C_PLAYER,
    "/api/v1/artist/cosmetic-preview": C_PLAYER,
    "/api/v1/team/queue/poll/{steam_id}": C_WOG,
    "/api/v1/ovt/queue/poll/{steam_id}": C_WOG,
    "/api/v1/team/lobby/state": C_WOG,
    "/api/v1/team/lobby/resolve": C_WOG,
    "/api/v1/ovt/lobby/state": C_WOG,
    "/api/v1/ovt/lobby/resolve": C_WOG,
    "/api/v1/ffa/queue/poll/{steam_id}": C_WOG,
    "/api/v1/broadcast/target": C_WOG,
    "/api/v1/broadcast/report-status": C_PLAYER,
    "/api/v1/report": C_PLAYER,
    "/api/v1/mail/inbox": C_WOG,
    "/api/v1/mail/sent": C_PLAYER,
    "/api/v1/mail/status": C_PLAYER,
    "/api/v1/mail/blocks": C_PLAYER,
    "/api/v1/mail/settings": C_PLAYER,
    "/api/v1/mail/{message_id}": C_WOG,
}


def check_design_player_mapping(routes, mapping=None, player=None, write_on_get=None) -> list[str]:
    """Every problem with the 30-template reconciliation: a count other than
    30, a template that is not a live GET, a class other than the mapping
    says, a superseding class other than WRITE_ON_GET or one without its
    written reason, a superseded template that is not both session-reached
    and a writer, and a PLAYER class that differs from the mapping's PLAYER
    rows (a route gained or lost outside the design's list)."""
    mapping = DESIGN_PLAYER_30 if mapping is None else mapping
    player = read_gate.PLAYER if player is None else player
    write_on_get = read_gate.WRITE_ON_GET if write_on_get is None else write_on_get
    problems = []
    if len(mapping) != 30:
        problems.append(f"the design named 30 templates; the mapping has {len(mapping)}")
    by_path = {r.path: r for r in _get_routes(routes)}

    def cls_of(t):
        if t in write_on_get:
            return C_WOG
        if t in player:
            return C_PLAYER
        c = read_gate.route_class(t)
        return read_gate.C_PUBLIC if c == C_PLAYER else c   # PLAYER only through `player`

    for t, want in mapping.items():
        if t not in by_path:
            problems.append(f"{t} is not a GET route of the app")
            continue
        got = cls_of(t)
        if got != want:
            problems.append(f"{t} is {got}; the mapping says {want}")
        if want not in (C_PLAYER, C_WOG):
            problems.append(f"{t} maps to {want}, which no requirement justifies")
        if want == C_WOG:
            if not str(write_on_get.get(t, "")).strip():
                problems.append(f"{t} is superseded by WRITE_ON_GET without a written reason")
            seeds = [M._binding_key(by_path[t].endpoint)]
            if not set(M._reached(seeds)) & SESSION_PRIMITIVES:
                problems.append(f"{t} is superseded but does not reach a session primitive")
            if not writers_reached(seeds):
                problems.append(f"{t} is superseded but reaches no writer")
    live_player = {p for p in by_path if cls_of(p) == C_PLAYER}
    mapped_player = {t for t, c in mapping.items() if c == C_PLAYER}
    for t in sorted(live_player - mapped_player):
        problems.append(f"{t} is PLAYER but not one of the design's 30")
    for t in sorted(mapped_player - live_player):
        problems.append(f"{t} is one of the design's PLAYER rows but is not PLAYER")
    return problems


def test_design_player_30_mapping():
    assert check_design_player_mapping(main.app.routes) == []
    counts = {}
    for c in DESIGN_PLAYER_30.values():
        counts[c] = counts.get(c, 0) + 1
    assert counts == {C_PLAYER: 16, C_WOG: 14}, counts
    assert set(read_gate.PLAYER) == {t for t, c in DESIGN_PLAYER_30.items() if c == C_PLAYER}


def test_design_player_30_controls():
    """The checker reports: a template mapped to the wrong class, a 29-row
    mapping, a PLAYER class that gained a route, one that lost a route, and a
    superseding class no requirement justifies."""
    wrong = dict(DESIGN_PLAYER_30, **{"/api/v1/mail/sent": C_WOG})
    assert any("/api/v1/mail/sent is PLAYER; the mapping says WRITE_ON_GET" in p
               for p in check_design_player_mapping(main.app.routes, mapping=wrong))
    short = dict(DESIGN_PLAYER_30)
    short.pop("/api/v1/report")
    assert any("the mapping has 29" in p for p in check_design_player_mapping(main.app.routes, mapping=short))
    gained = set(read_gate.PLAYER) | {"/api/v1/leaderboard"}
    assert any("/api/v1/leaderboard is PLAYER but not one of the design's 30" in p
               for p in check_design_player_mapping(main.app.routes, player=gained))
    lost = set(read_gate.PLAYER) - {"/api/v1/mail/settings"}
    assert any("/api/v1/mail/settings is one of the design's PLAYER rows but is not PLAYER" in p
               for p in check_design_player_mapping(main.app.routes, player=lost))
    odd = dict(DESIGN_PLAYER_30, **{"/api/v1/report": read_gate.C_PUBLIC})
    assert any("which no requirement justifies" in p
               for p in check_design_player_mapping(main.app.routes, mapping=odd))
