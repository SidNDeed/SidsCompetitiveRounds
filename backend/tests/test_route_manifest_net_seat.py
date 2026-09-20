"""Exhaustive API-route and formatter non-consumer gate for W1 telemetry."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha1
import ast
import inspect
import contextlib
import sys
import textwrap
import json
import typing
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

API_DIR = (Path(__file__).parents[1] / "api").resolve()

# ── The binding index ────────────────────────────────────────────────────
#
# r14 M7. Every previous version of this walk resolved a NAME to an OBJECT and
# then asked `inspect` for that object's source. An object has already thrown
# away the statement that bound it, and that erasure was the defect: a
# dataclass default that decides every persisted bracket row survived only
# because it happens to live inside a class, whose statement inspect can still
# recover. A raw SQL string 32 routes execute, a rank-tier table, a rate-limit
# tuple and a partial are the identical defect with no class to hide in -- all
# of them outside every fingerprint while this gate reported all-clear.
#
# So the node type is a first-party module-level BINDING, not a first-party
# object, and the source comes from parsing the module rather than from
# introspecting a value. The rule then never has to ask what KIND of thing a
# name denotes.
#
# Measured on this tree: 8 modules, 1282 bindings, ~5.3 s to build once per
# process. Re-measure when the index changes shape; a stale figure here is the
# kind of claim this gate exists to catch.

_DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_BINDING_INDEX = {}


def _is_script_guard(node):
    """`if __name__ == ...:` -- a block that does not exist when the api imports
    the module.

    Indexed like any other guard until r15, which is how ordinary names from a
    bracket self-test (rows, ids, extras, sus) ended up inside two hundred route
    fingerprints: the cross-module walk resolves a handler's local name against
    every module, and a script-only binding is a binding as far as the index is
    concerned."""
    return (isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            # r16: the exemption is for the canonical script guard ONLY. A `!=`
            # or an `in` on __name__ RUNS at import and stays indexed.
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.Eq)
            and len(node.test.comparators) == 1
            and isinstance(node.test.comparators[0], ast.Constant)
            and node.test.comparators[0].value == "__main__")


def _index_module(path):
    """{name: (kind, source segment, referenced names)} for every MODULE-SCOPE
    binding in one file.

    `kind` is "def" for FunctionDef/AsyncFunctionDef/ClassDef and "data" for
    Assign/AnnAssign. A def's segment starts at its first DECORATOR line, so a
    route's own decorator -- which carries its path and response_model -- is
    inside its fingerprint.

    Module-level If/Try/With bodies are recursed into, which is not optional:
    main binds `_PIL_AVAILABLE`/`_PILImage` inside a try/except, and 4 routes
    cover them. The block's CONTROLLING HEADER is prepended to every binding
    inside it, because the condition a binding exists under is part of what was
    reviewed -- without it the except clause deciding whether Pillow is
    available could be rewritten with no fingerprint moving.

    `if __name__ == "__main__":` is the one guard NOT recursed into. Its body
    does not exist when the api imports the module, and tournament_bracket's
    self-test binds ordinary names -- rows, ids, real, extras, s1, s2, sus --
    that a handler's own locals reference. Measured before this exclusion: 1008
    occurrences over 10 names, `sus` inside 194 route fingerprints. Editing a
    bracket self-test moved two hundred routes.

    A name bound more than once at module scope CONCATENATES its segments rather
    than replacing them, so a conditional rebinding cannot hide half its
    source."""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    table = {}

    def segment(node):
        start = node.lineno
        for decorator in getattr(node, "decorator_list", ()):
            start = min(start, decorator.lineno)
        # `ast` ends a node at its last STATEMENT, but a binding's SOURCE runs
        # to the end of its block -- so a comment sitting after the last
        # statement, still inside the function, is dropped. That is exactly
        # where a rule gets written down, and the fidelity control below caught
        # it on this file's first run. Absorb trailing lines that are blank or
        # comments indented INSIDE the binding, and stop at the first line that
        # is anything else; buffered, so trailing blanks alone are not swept in.
        end = node.end_lineno
        pending = []
        for offset in range(node.end_lineno, len(lines)):
            stripped = lines[offset].strip()
            if not stripped:
                pending.append(offset)
                continue
            indent = len(lines[offset]) - len(lines[offset].lstrip())
            if stripped.startswith("#") and indent > node.col_offset:
                pending.append(offset)
                end = offset + 1
                continue
            break
        del pending
        return "".join(lines[start - 1:end])

    def referenced(node):
        names = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name):
                names.add(sub.id)
            elif isinstance(sub, ast.Attribute):
                names.add(sub.attr)
        return names

    def header_refs(node):
        """r2 (Sept 6): the names a block HEADER references -- the `if` test,
        the `with` expressions. `try:` has none of its own; each handler adds
        its exception type below. A header's TEXT was already fingerprinted,
        but the object a name in it denotes was not part of the closure: a
        tuple of exception classes or a feature flag could change what the
        block admits with no fingerprint moving."""
        if isinstance(node, ast.If):
            return referenced(node.test)
        if isinstance(node, ast.With):
            names = set()
            for item in node.items:
                names |= referenced(item.context_expr)
            return names
        return set()

    def guard_header(node):
        """The controlling line(s) of a module-level block -- `if ...:`,
        `try:`, `with ...:` -- down to its first statement. Prepended to every
        binding inside, because the condition a binding exists under is part
        of what was reviewed."""
        return "".join(lines[node.lineno - 1:node.body[0].lineno - 1])

    def handler_header(handler):
        """r16: an `except ...:` header, down to the handler's first
        statement. `guard_header` alone reused the `try:` line for every
        handler, so `except Exception` could become `except ImportError` --
        a different set of failures reaching a different binding -- with no
        fingerprint moving."""
        return "".join(lines[handler.lineno - 1:handler.body[0].lineno - 1])

    def part_header(previous, part):
        """r16: the `else:` / `finally:` header of a block's later part. The
        ast gives those parts no node of their own, so the header is the
        source between the last statement of the part before and the first
        statement of this one."""
        if not part:
            return ""
        return "".join(lines[previous.end_lineno:part[0].lineno - 1])

    def bind(name, kind, node, guard="", guard_refs=frozenset()):
        text, refs = guard + segment(node), referenced(node) | set(guard_refs)
        if name in table:
            prev_kind, prev_text, prev_refs = table[name]
            table[name] = (prev_kind, prev_text + text, prev_refs | refs)
        else:
            table[name] = (kind, text, refs)

    def visit(body, guard="", guard_refs=frozenset()):
        for node in body:
            if isinstance(node, _DEF_NODES):
                bind(node.name, "def", node, guard, guard_refs)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    for sub in ast.walk(target):
                        if isinstance(sub, ast.Name):
                            bind(sub.id, "data", node, guard, guard_refs)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    bind(node.target.id, "data", node, guard, guard_refs)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                # r15. An import binds a name, and WHICH object a name denotes
                # is part of what a handler does. Removing a batch-added
                # `DBAPIError` import moved no fingerprint at all, while the
                # deadlock path naming it stopped being a rollback-and-retry.
                #
                # Given their own kind so the affordability bound can count
                # them separately: a route references ~40 imported names, which
                # inflates the CLOSURE without inflating the DRIFT, because
                # import lines change far more rarely than code does.
                for alias in node.names:
                    bind(alias.asname or alias.name.split(".")[0], "import", node,
                         guard, guard_refs)
            elif isinstance(node, (ast.If, ast.Try, ast.With)):
                if _is_script_guard(node):
                    continue
                inner = guard + guard_header(node)
                inner_refs = guard_refs | header_refs(node)
                visit(node.body, inner, inner_refs)
                # r16: each later part carries ITS OWN header on top of the
                # block's, walked in source order so "the statement before"
                # is always the one the header follows.
                last = node.body[-1]
                for handler in getattr(node, "handlers", []):
                    handler_refs = inner_refs | (
                        referenced(handler.type) if handler.type is not None else set())
                    visit(handler.body, inner + handler_header(handler), handler_refs)
                    last = handler.body[-1]
                orelse = getattr(node, "orelse", [])
                if orelse:
                    visit(orelse, inner + part_header(last, orelse), inner_refs)
                    last = orelse[-1]
                finalbody = getattr(node, "finalbody", [])
                if finalbody:
                    visit(finalbody, inner + part_header(last, finalbody), inner_refs)

    visit(ast.parse(source).body)
    return {name: (kind, text, frozenset(refs))
            for name, (kind, text, refs) in table.items()}


def _binding_index():
    """{module stem: bindings} over every .py file in backend/api.

    Discovered from the DIRECTORY rather than from the modules the app happens
    to have imported: which files serve routes is a fact about today's routing
    table, and a helper does not stop being ours because the route that reached
    it moved."""
    if not _BINDING_INDEX:
        for path in sorted(API_DIR.glob("*.py")):
            _BINDING_INDEX[path.stem] = _index_module(path)
    return _BINDING_INDEX


_SEGMENT_MEMO = {}


def _segment(module, name):
    """THE source-text seam.

    Every byte that reaches a fingerprint comes through here, and every
    mutation control in this file patches THIS rather than `inspect.getsource`.
    That is what makes the controls test the shipped rule: a control that
    patches a function the rule no longer calls passes for the wrong reason.
    The memo is keyed, so a control evicts one key and restores it."""
    key = (module, name)
    if key not in _SEGMENT_MEMO:
        binding = _binding_index().get(module, {}).get(name)
        _SEGMENT_MEMO[key] = "" if binding is None else binding[1]
    return _SEGMENT_MEMO[key]


@contextlib.contextmanager
def _mutated_segment(module, name):
    """Edit ONE binding's source through the seam every fingerprint reads.

    Every mutation control in this file uses this. The previous controls
    patched `inspect.getsource`, which the rule called until this range and
    does not call now -- so they would have gone on passing while testing
    nothing at all. Patching the memo instead means a control can only pass if
    the shipped rule really does read that binding's text."""
    key = (module, name)
    original = _segment(module, name)
    assert original, f"{module}.{name} is not an indexed binding"
    _SEGMENT_MEMO[key] = original + "\n# mutation\n"
    try:
        yield
    finally:
        _SEGMENT_MEMO[key] = original


def _route_fingerprint(route):
    for entry in _route_identities([route]):
        return entry["source_sha1"]
    raise AssertionError("the route did not enumerate")


def _binding_kind(module, name):
    binding = _binding_index().get(module, {}).get(name)
    return None if binding is None else binding[0]


def _is_ours(obj):
    """Whether an object's source is ours to review. Used only to turn the
    app's own objects (endpoints, dependencies, response models, middleware)
    into index keys -- never to decide what the walk may step through."""
    try:
        return Path(inspect.getfile(obj)).resolve().parent == API_DIR
    except (TypeError, OSError):
        return False


def _binding_key(obj):
    """(module, name) for a first-party object, or None."""
    if not _is_ours(obj):
        return None
    module = getattr(obj, "__module__", None)
    name = getattr(obj, "__name__", None)
    if not module or not name:
        return None
    return (module, name)


def _walk_bindings(seeds, index=None):
    """{(module, name): kind} for every binding the seeds reach, seeds included.

    THREE TIERS, and the middle one is what keeps this affordable. A def or
    class is EXPANDED THROUGH -- every name inside it is followed. A data
    binding is followed only into OTHER DATA BINDINGS. An import is a leaf,
    except for the guards that SELECT it (Group 2 review, Sept 6).

    The middle tier is the whole cost control, not a compromise: letting a data
    binding follow names of any kind makes `app = FastAPI(...)` a hub that every
    route decorator references, and the measured median closure goes from 20 to
    179 -- every route dragging in most of the app, a fingerprint that certifies
    nothing because it always moves.

    Data-into-data was missing until r15 found what it cost: a data binding
    COMPOSED from other data bindings showed only the NAME of what it composed.
    `_DC_ELIGIBLE_TERMS` is built by concatenating `_DC_EVIDENCE_TERM`, so
    rewriting the rule that decides whether a disconnect report is accepted
    moved NO route fingerprint -- measured, 0 of 309 routes covered it. That is
    exactly the raw-SQL hole this method exists to close, one level of
    indirection further down.

    A bare name is resolved in the module it is written in first and then in
    every other indexed module, and EVERY match is folded in rather than the
    first -- on a name two modules share, both enter. That widens the reviewed
    surface rather than narrowing it, which is the only direction this gate may
    be wrong in."""
    index = _binding_index() if index is None else index
    reached = {}
    frontier = list(seeds)
    while frontier:
        key = frontier.pop()
        if key in reached:
            continue
        module, name = key
        binding = index.get(module, {}).get(name)
        if binding is None:
            continue
        kind, _text, refs = binding
        reached[key] = kind
        # An import names something defined outside this api. Its own line is
        # fingerprinted; there is nothing of ours beneath it to follow -- EXCEPT
        # the guards that select it (Group 2 review, Sept 6): under
        # `if FEATURE: import fast as engine / else: import slow as engine`
        # FEATURE decides which implementation a route runs. An import's refs
        # are only ever its block headers' names (r2), so following them costs
        # nothing on an unguarded import and closes the hole on a guarded one.
        order = [module] + [other for other in index if other != module]
        for ref in refs:
            for other in order:
                if ref not in index[other] or (other, ref) in reached:
                    continue
                if kind == "data" and index[other][ref][0] != "data":
                    continue
                frontier.append((other, ref))
    return reached


def _route_seeds(route):
    """Every first-party binding a route enters through, not just its handler.

    Recovered computedly from the app, never listed. A route's behaviour is
    also decided by the dependencies FastAPI resolves before the handler runs
    and by the response model it serialises through, and neither of those is
    referenced by name inside the handler body -- they are written in the
    decorator and the signature."""
    seeds = []
    endpoint = getattr(route, "endpoint", None)
    if endpoint is not None:
        key = _binding_key(endpoint)
        if key is not None:
            seeds.append(key)
    dependant = getattr(route, "dependant", None)
    if dependant is not None:
        stack = list(getattr(dependant, "dependencies", ()) or ())
        while stack:
            dependency = stack.pop()
            call = getattr(dependency, "call", None)
            if call is not None:
                key = _binding_key(call)
                if key is not None:
                    seeds.append(key)
            stack.extend(getattr(dependency, "dependencies", ()) or ())
    model = getattr(route, "response_model", None)
    if model is not None:
        pending = [model]
        while pending:
            annotation = pending.pop()
            args = typing.get_args(annotation)
            if args:
                pending.extend(a for a in args if a is not type(None))
                continue
            key = _binding_key(annotation)
            if key is not None:
                seeds.append(key)
    return sorted(set(seeds))


_CLOSURE_CACHE = {}


def _reached(seeds):
    """Memoised: the same seeds are asked for by the manifest build, by the
    affordability bound and by several assertions below."""
    key = tuple(seeds)
    cached = _CLOSURE_CACHE.get(key)
    if cached is None:
        cached = _walk_bindings(seeds)
        _CLOSURE_CACHE[key] = cached
    return cached


def _fingerprint_text(seeds):
    """The reviewed surface as text: every reached binding's segment, in a
    fixed order so the fingerprint does not depend on walk order."""
    return "".join(_segment(module, name)
                   for module, name in sorted(_reached(seeds)))


def _helper_closure(endpoint):
    """The identities a ROUTE HANDLER reaches, sorted, excluding its own seeds.
    Kept in this shape because several assertions below are written against
    it."""
    seeds = [_binding_key(endpoint)] if _binding_key(endpoint) else []
    return sorted(set(_reached(seeds)) - set(seeds))


# ── Entry points that are not routes ─────────────────────────────────────
#
# A route table is not the whole app. Middleware runs on every request,
# exception handlers decide what a failure returns, and the lifespan starts
# the background work. None of them appears in `app.routes`, so before this
# range every one of them was outside every fingerprint: editing the
# rate-limit gate moved nothing anywhere.


def _middleware_entry_points():
    """The first-party dispatch functions of the app's own middleware."""
    keys = []
    for middleware in getattr(main.app, "user_middleware", ()) or ():
        dispatch = (getattr(middleware, "kwargs", None) or {}).get("dispatch")
        if dispatch is not None:
            key = _binding_key(dispatch)
            if key is not None:
                keys.append(key)
    # SORTED, not `sorted(set(...))`. How many times a dispatch is registered
    # is part of what the app does to a request: registering the rate-limit
    # gate twice sends every request through the limiter twice, so a nominal
    # 20-per-10-seconds starts refusing at 11 — and a set erased the second
    # registration, leaving the manifest unmoved and this gate silent.
    return sorted(keys)


def _exception_handler_entry_points():
    """First-party exception handlers.

    The day predicted below arrived: RJ-4 registered
    `main._ffa_report_refusal_handler` for `FfaReportRefusal`, and the
    exhaustiveness assertion below caught it exactly as it was written to --
    two red tests on a manifest nobody had edited, which is what a gate that
    fails closed is for. It is a REQUEST-PATH surface: every FFA report
    refusal is serialised by it, so its body shape is reviewed here and
    fingerprinted like a route.

    The assertion this replaces was "the section is empty". That was correct
    while it was true and is now the wrong shape, because it would have to be
    re-written for every handler ever added. What is asserted instead is the
    property that made the old one safe: the RAW handler set must be non-empty,
    proving the recovery still sees handlers at all, and the recovered
    first-party set must equal the manifest -- which the generic loop already
    checks for every section. A handler appearing or leaving therefore stays a
    review item, answerable only by editing the manifest's identity list by
    hand (repin_route_manifest.py refuses to do it)."""
    keys = []
    for handler in (getattr(main.app, "exception_handlers", None) or {}).values():
        key = _binding_key(handler)
        if key is not None:
            keys.append(key)
    return sorted(set(keys))


def _background_entry_points():
    """The first-party lifespan, recovered through the wrappers FastAPI puts
    around it.

    `app.router.lifespan_context` is not the app's lifespan: FastAPI merges
    lifespans, so what is stored is `merged_lifespan` closing over another
    `merged_lifespan` closing over ours. A one-level `__closure__` read finds
    nothing at all, which is a recovery that silently fingerprints an empty
    set. The walk below descends through nested closures and through
    `__wrapped__`/`func` wrappers, bounded by identity and depth.

    THE DEPTH IS NOT A COST CONTROL AND MUST NOT BE TUNED LIKE ONE. `seen` is
    what bounds the work -- every object is visited once -- so depth only
    decides how deep the chain may be before the recovery gives up. The chain
    grows by ONE LEVEL PER `include_router`, and `lifespan` itself is behind a
    `@asynccontextmanager` wrapper, so the real function sits one hop below the
    level that carries its name. At a bound of 8 it sat exactly at the edge:
    mounting one more router pushed it past, `_is_ours` refused the contextlib
    helper that was left, and this returned [] -- the empty set this docstring
    warns about, arrived at by a number rather than by a missing lifespan.
    (Measured on the wave B/C tree: four routers, the wrapper at depth 8 and
    the function at 9.) The bound is now far above any plausible router count,
    and `test_the_manifest_covers_every_non_route_entry_point` asserts the
    recovery is NON-EMPTY, so a future chain that outgrows even this fails
    loudly instead of fingerprinting nothing."""
    found, seen = [], set()

    def descend(obj, depth):
        if depth > 64 or id(obj) in seen or not callable(obj):
            return
        seen.add(id(obj))
        key = _binding_key(obj)
        if key is not None:
            found.append(key)
        for cell in (getattr(obj, "__closure__", None) or ()):
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if callable(value):
                descend(value, depth + 1)
        for attribute in ("__wrapped__", "func"):
            wrapped = getattr(obj, attribute, None)
            if callable(wrapped):
                descend(wrapped, depth + 1)

    descend(getattr(main.app.router, "lifespan_context", None), 0)
    return sorted(set(found))


def _entry_point_sections():
    """{section name: [(module, name)]} -- the three non-route sections."""
    return {
        "middleware": _middleware_entry_points(),
        "exception_handlers": _exception_handler_entry_points(),
        "background_entry_points": _background_entry_points(),
    }


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
        # A handler's fingerprint covers every module-level BINDING it reaches,
        # transitively — an extracted helper must not become a fingerprint
        # hole, and neither must a raw SQL string or a table of constants moved
        # out of the body. Sorted inside _fingerprint_text, so the value does
        # not depend on walk order.
        source_text = _fingerprint_text(_route_seeds(route))
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


def _route_registration_order():
    """Route identities in the order Starlette will try to match them.

    r15. The manifest sorts, and sorting discards the one property that decides
    WHICH handler a request reaches: first match wins. Moving a dynamic
    `/players/{steam_id}` above a static `/players/search` leaves every identity
    and every fingerprint in this file untouched, while `/players/search`
    quietly starts being served as `steam_id="search"`.

    Rendered as strings so a reordering shows up in a diff as the two lines that
    swapped, rather than as a wall of moved JSON."""
    order = []

    def walk(routes, prefix=""):
        for route in routes:
            if isinstance(route, Mount):
                walk(route.routes, _joined_path(prefix, route.path))
                continue
            if not isinstance(route, (APIRoute, APIWebSocketRoute)):
                continue
            path = _joined_path(prefix, route.path)
            if not path.startswith("/api/v1/"):
                continue
            methods = ",".join(sorted(getattr(route, "methods", ()) or ())) or "WS"
            order.append("%s %s -> %s.%s" % (methods, path,
                                             route.endpoint.__module__,
                                             route.endpoint.__qualname__))

    walk(main.app.routes)
    return order


def _shadowing_pairs(order):
    """Pairs where an earlier dynamic path can swallow a later literal one.

    The concrete harm, not a general worry about ordering: `/a/{x}` registered
    before `/a/search` means `/a/search` is dead."""
    parsed = []
    for position, line in enumerate(order):
        methods, path = line.split(" ", 1)[0], line.split(" ")[1]
        parsed.append((position, frozenset(methods.split(",")), path.split("/")))
    pairs = []
    for early, early_methods, early_parts in parsed:
        if not any(part.startswith("{") for part in early_parts):
            continue
        for late, late_methods, late_parts in parsed:
            if late <= early or not (early_methods & late_methods):
                continue
            if len(early_parts) != len(late_parts):
                continue
            if all(a == b or (a.startswith("{") and not b.startswith("{"))
                   for a, b in zip(early_parts, late_parts)):
                pairs.append((order[early], order[late]))
    return pairs


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
    assert len(manifest) == 362   # Sept 12 pack history: +1 (361 before); portraits: +9 (the writer, the admin clear, the lease triple, four face routes; 352 before); Sept 10 Player Cards: +15 (pc/*, admin/pc/snapshot, internal/pc/*); room rules: +3 (334 before)
    assert len({json.dumps(item, sort_keys=True) for item in expected}) == len(expected)
    assert all(
        entry["classification"] in {"sentinel-exercised", "statically-nonconsumer"}
        for entry in manifest
    )
    assert all(isinstance(entry["reason"], str) and entry["reason"].strip() for entry in manifest)

    exercised = [entry for entry in manifest if entry["classification"] == "sentinel-exercised"]
    static = [entry for entry in manifest if entry["classification"] == "statically-nonconsumer"]
    assert len(exercised) == 1
    assert len(static) == 361   # Sept 12 pack history: +1 (360 before); portraits: +9 (351 before); Sept 10 Player Cards: +15; room rules: +3 (333 before)
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
    """The mutation the previous test's shape is for. Edit a binding in
    `tournaments` that a route reaches and that route's source_sha1 must move;
    the negative control is the same route with nothing edited."""
    target = None
    for route in main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        if getattr(route.endpoint, "__module__", "") != "tournaments":
            continue
        reached = [n for (m, n) in _helper_closure(route.endpoint) if m == "tournaments"]
        if reached:
            target = (route, sorted(reached)[0])
            break
    assert target, "no tournaments route reaches a tournaments binding"
    route, name = target

    before = _route_fingerprint(route)
    assert before == _route_fingerprint(route), (
        "negative control: unedited source must not move"
    )
    with _mutated_segment("tournaments", name):
        after = _route_fingerprint(route)
    assert after != before, (
        f"editing tournaments.{name} left {route.path} certified unchanged"
    )
    assert _route_fingerprint(route) == before, (
        "the mutation did not unwind -- every later assertion in this file "
        "would be reading a poisoned memo"
    )


def test_the_helper_closure_stays_affordable():
    """A fingerprint that pulls half the app in drifts on every commit, and a
    gate that always fires is a gate nobody reads.

    MEASURED when these bounds were set (Sept 4 batch, r14 M7) at the shipped
    two-tier rule: median 15, p90 49, worst 190 (/api/v1/matches) of 1282
    indexed bindings, with the walk itself taking 0.1 s once the index is built
    (~5.3 s, once per process). The bounds below sat above those with room, so
    this fails on a walk that has gone wrong rather than on ordinary growth;
    the worst-route bounds have since moved for measured growth in bindings
    a route really runs, each move recorded with its measurement at its
    assertion.

    The second tier is exactly what these numbers pay for. Expanding data
    bindings as well as def/class ones makes `app = FastAPI(...)` a hub that
    every route decorator references, and the same measurement gives median
    179 / worst 279 -- every route dragging in most of the app, which is a
    fingerprint that certifies nothing because it always moves."""
    routes = [r for r in main.app.routes
              if isinstance(r, APIRoute) and r.path.startswith("/api/v1/")]
    assert routes
    total = sum(len(names) for names in _binding_index().values())

    def percentiles(counts):
        counts = sorted(counts)
        return (counts[len(counts) // 2],
                counts[min(len(counts) - 1, int(len(counts) * 0.9))],
                counts[-1])

    reached = [_reached(_route_seeds(route)) for route in routes]
    code_median, code_p90, code_worst = percentiles(
        sum(1 for kind in r.values() if kind != "import") for r in reached)
    all_median, all_p90, all_worst = percentiles(len(r) for r in reached)

    # The CODE tier is the one that drifts, and the r15 repairs left its bounds
    # alone: measured 20 / 55 / 198 with data-into-data expansion, against
    # 16 / 48 / 191 before it.
    assert code_median <= 24, f"median code closure {code_median} of {total}"
    assert code_p90 <= 75, f"p90 code closure {code_p90} of {total}"
    # Player Cards v4.13 (2026-09-15): measured 20 / 64 / 278 on e894c45 and
    # 20 / 64 / 282 on the v4.13 fold, the worst both times POST
    # /api/v1/pc/packs/open. What it gained are bindings that route runs: the
    # shared SteamID64 check (is_individual_id and its three constants, +4, in
    # place of the two id regexes, -2) and the pool membership word with its
    # Steam id clause (+2). That moved the worst bound to 300.
    #
    # Sept 14 batch merge (2026-09-15): measured 21 / 64 / 315 of 2319 indexed
    # bindings, the worst still POST /api/v1/pc/packs/open. The same walk with
    # the same route seeds over MAIN's backend/api gives 21 / 64 / 282, so the
    # merge's own delta is +33 on the worst route and 0 on the median and p90.
    #
    # All 33 are bindings that DID NOT EXIST on main, and nothing main reached
    # stopped being reached: 18 in pc_face (the autograph layout -- _autograph_box,
    # _hex_rgb, _sign_case/_fill/_ink_height/_layout/_mask/_pieces/_style/_width
    # and the eight _SIGN_* constants) and 15 in the new pc_signature module
    # (signature_style, _hex and the style tables it decides from). That is the
    # signed-print face work, which this route runs when an opened pack mints a
    # signed print.
    #
    # It is NOT the pool predicate, and the pool predicate cannot move this
    # number: the clause the merge added to _PC_POOL_MEMBER_SQL
    # (`p.mod_seen_at IS NOT NULL`) is literal SQL inside a data binding and
    # names nothing the walk can follow. The +2 the v4.13 note above counts is
    # the two data bindings themselves, and there are still exactly two.
    #
    # The bound moves to 335 -- the same ~6% headroom over the measurement that
    # 300 gave over 282 -- so it goes on failing a walk that has gone wrong (the
    # data-into-data hub case measured worst 279 at MEDIAN 179, i.e. a runaway
    # shows up in the median long before it shows up here) rather than on a
    # feature module a route genuinely runs. The median and p90 bounds stay.
    assert code_worst <= 335, f"worst code closure {code_worst} of {total}"

    # Imports are counted separately rather than folded in or waved through.
    # They roughly triple the closure -- measured 69 / 119 / 308 -- and that is
    # honest, because a route really does reference ~40 imported names. What
    # they do not triple is the DRIFT: an import line changes far more rarely
    # than the code around it. A walk that has gone wrong still has to fail
    # here, so the bound is real and not merely raised to fit.
    assert all_median <= 90, f"median closure {all_median} of {total}"
    assert all_p90 <= 150, f"p90 closure {all_p90} of {total}"
    # Steam pictures (2026-09-12): a pack open now primes the subjects'
    # Steam pictures, and that chain (claim, feed, download, the bound write
    # and its blob locks) is ~20 real bindings on top of the face path the
    # route already reached -- measured 383 on /api/v1/pc/packs/open. The
    # bound moves to 400 for that reason and no other; p90 and the median
    # stay where they were.
    # Player Cards v4.13 (2026-09-15): the same route measured 394 on e894c45
    # and 401 on the v4.13 fold -- the code bindings above plus the three
    # import lines they are reached through (steamid64 in main, pc_steam and
    # pc_portrait); p90 126 -> 129, median 64. That moved the bound to 420.
    # Sept 14 batch merge (2026-09-15): the same route measured 439, against 401
    # for the same walk over MAIN's backend/api -- +38, and median 65 / p90 129
    # both unmoved. Of the 38, 33 are the signed-print face code bindings
    # accounted for at the code bound above; 4 are the import lines they arrive
    # through (main._pcsig, pc_face.ImageFilter, pc_face._SIGN_RAINBOW,
    # pc_signature.Iterable); and 1 is main.case -- sqlalchemy's `case`, already
    # imported, newly reached because the new signature code writes the bare
    # name `case` and the walk folds in EVERY module that binds a shared name.
    # That last one widens the reviewed surface rather than narrowing it, which
    # is the only direction this gate may be wrong in. The bound moves to 460,
    # the same ~5% headroom 420 gave over 401 and 400 gave over 383.
    assert all_worst <= 460, f"worst closure {all_worst} of {total}"


def _route_covering(module, name):
    """The routes whose reviewed surface contains one binding."""
    return [r for r in main.app.routes
            if isinstance(r, APIRoute) and r.path.startswith("/api/v1/")
            and (module, name) in _reached(_route_seeds(r))]


def test_the_route_seed_recovery_still_sees_what_it_recovers():
    """A route is entered through more than its handler: FastAPI resolves the
    dependencies first and serialises through the response model, and neither
    is called from the handler body.

    MEASURED on this tree, both are REDUNDANT: every route names its response
    model in its own decorator and its dependencies in its own signature, both
    of which are inside the handler's segment, so the walk reaches them anyway
    -- 0 of 309 routes gain a single binding from these seeds. That is why this
    gate asserts the RECOVERY and not a fingerprint delta: deleting either seed
    source moves no fingerprint anywhere, so a drift assertion for them is a
    check that cannot fail, and both mutants proved exactly that.

    They stay because the redundancy is a property of how these routes happen
    to be written, not of the framework: a dependency declared on the router
    rather than in a signature, or a response model composed at import time, is
    named nowhere in the handler's own source."""
    routes = [r for r in main.app.routes
              if isinstance(r, APIRoute) and r.path.startswith("/api/v1/")]
    assert routes

    models, dependencies = set(), set()
    for route in routes:
        endpoint_key = _binding_key(route.endpoint)
        for key in _route_seeds(route):
            if key == endpoint_key:
                continue
            if _binding_kind(*key) == "def" and key[0] == "schemas":
                models.add(key)
            else:
                dependencies.add(key)

    assert len(models) >= 25, (
        f"only {len(models)} first-party response models were recovered from "
        "309 routes; measured 29 -- the recovery has stopped seeing them"
    )
    assert ("database", "get_db") in dependencies, sorted(dependencies)
    assert all(_binding_kind(*key) is not None for key in models | dependencies), (
        "a recovered seed is not an indexed binding, so its source is not in "
        "any fingerprint"
    )


def test_a_module_level_data_binding_moves_the_fingerprint_of_its_routes():
    """r14 M7, GATE A -- the defect that motivated the whole method change.

    `_PODIUM_QUERY` is a raw SQL string bound at module scope and executed by
    32 routes. Under object introspection it was in no fingerprint at all:
    resolving the name gave back a `str`, and a str has no source. Rewriting
    the query -- changing what every one of those routes returns -- moved
    nothing and this gate reported all-clear.

    THE MUTATION THIS MUST FAIL ON: restricting expansion to def/class
    bindings, i.e. the shape a fingerprint over objects can express. The sha
    then stops moving."""
    covering = _route_covering("main", "_PODIUM_QUERY")
    assert len(covering) >= 20, (
        f"only {len(covering)} routes reach _PODIUM_QUERY; measured 32 -- "
        "either the query moved or the walk narrowed"
    )
    assert _binding_kind("main", "_PODIUM_QUERY") == "data", (
        "the point of this gate is that it is NOT a def or a class"
    )
    route = covering[0]
    before = _route_fingerprint(route)
    assert before == _route_fingerprint(route), "negative control"
    with _mutated_segment("main", "_PODIUM_QUERY"):
        after = _route_fingerprint(route)
    assert after != before, (
        f"rewriting the SQL that {route.path} executes left it certified unchanged"
    )


def test_a_class_level_default_moves_the_fingerprint_of_the_route_that_persists_it():
    """r14 M7, GATE B. `MatchRow` carries the field defaults every persisted
    bracket row is built from. It survived the old rule only because it happens
    to be a CLASS, whose statement `inspect` can still recover -- an accident of
    what kind of value the name denotes, which is exactly what this method stops
    depending on.

    THE MUTATION THIS MUST FAIL ON: dropping ClassDef from the index. The
    covering assertion then finds no route at all."""
    covering = _route_covering("tournament_bracket", "MatchRow")
    assert covering, "no route covers tournament_bracket.MatchRow"
    assert _binding_kind("tournament_bracket", "MatchRow") == "def", (
        "classes are indexed under the def tier and expanded through"
    )
    route = covering[0]
    before = _route_fingerprint(route)
    with _mutated_segment("tournament_bracket", "MatchRow"):
        after = _route_fingerprint(route)
    assert after != before, (
        f"editing MatchRow left {route.path} certified unchanged"
    )


def _entry_point_sha(module, name):
    return sha1(_fingerprint_text([(module, name)]).encode("utf-8")).hexdigest()


def _load_entry_points():
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sections = document["entry_points"]
    assert set(sections) == {"middleware", "exception_handlers",
                             "background_entry_points"}, sorted(sections)
    return {name: [tuple(row) for row in rows] for name, rows in sections.items()}


def _entry_point_drift(manifest, sha_of=_entry_point_sha):
    """EVERY pinned entry point whose fingerprint has moved, not the first.

    This used to be an `assert` inside the loop, which stops at the first
    mismatch it meets. The sections are walked in a fixed order and middleware
    comes first, so a drift in the background entry point sat behind a
    middleware drift owned by another lane and was reported by nothing: the
    failure line named one function, and a reader had no way to tell whether
    it was the only one. A gate that reports a subset of what it found is a
    gate that certifies the rest by silence.

    `sha_of` is a seam, so a control can hand this a scripted oracle and check
    that a SECOND drifted entry is actually named.
    """
    drifted = []
    for section in sorted(manifest):
        for module, name, sha in manifest[section]:
            live = sha_of(module, name)
            if live != sha:
                drifted.append((section, module, name, sha, live))
    return drifted


def test_the_manifest_covers_every_non_route_entry_point():
    """r14 M7, GATE C. A route table is not the whole app.

    Middleware runs on every request, exception handlers decide what a failure
    returns, and the lifespan starts the background work -- and none of them
    appears in `app.routes`, so before this range every one of them sat outside
    every fingerprint. Editing the rate-limit gate moved nothing anywhere.

    Each recovered set is compared to the manifest by identity AND by
    fingerprint, so a reshaping of the app that stops the recovery seeing
    anything fails loudly instead of certifying an empty set.

    THE MUTATIONS THIS MUST FAIL ON: appending a comment to `rate_limit_gate`
    (its sha must move -- today nothing anywhere moves), and making the
    recovery return nothing (the non-empty assertions fire)."""
    manifest = _load_entry_points()
    live = _entry_point_sections()

    assert live["middleware"], "no first-party middleware dispatch was recovered"
    assert ("main", "rate_limit_gate") in live["middleware"], sorted(live["middleware"])
    assert live["background_entry_points"], "the lifespan was not recovered"
    assert live["background_entry_points"] == [("main", "lifespan")], (
        sorted(live["background_entry_points"])
    )

    # The raw recovery must be non-empty -- proof the mechanism still sees
    # handlers at all, so that a first-party one added later is picked up
    # rather than silently skipped. (FastAPI's own three are always there; the
    # recovery keeps only the first-party ones, which is why this is asserted
    # on the RAW set and not on the section.)
    raw_handlers = getattr(main.app, "exception_handlers", None) or {}
    assert raw_handlers, "the exception-handler recovery sees nothing at all"
    # ...and the first-party set is what the manifest says it is. The generic
    # loop below asserts that for every section; this names the one handler
    # this app registers, so DELETING it from both the app and the manifest --
    # which the loop would call agreement -- still reddens here.
    assert live["exception_handlers"] == [("main", "_ffa_report_refusal_handler")], (
        "the first-party exception-handler set changed. A handler is a "
        "request-path surface: adding, removing or renaming one is a review "
        "item, not a re-pin (repin_route_manifest.py refuses to do it)."
    )

    for section, entries in live.items():
        recorded = [(m, n) for (m, n, _sha) in manifest[section]]
        assert recorded == entries, f"{section}: manifest {recorded} vs live {entries}"

    # Reported TOGETHER. One drifted fingerprint used to hide every later one,
    # and the sections are walked in a fixed order, so whichever came first
    # decided what a reader was told (#342: a check whose report is a subset of
    # what it found).
    drifted = _entry_point_drift(manifest)
    assert not drifted, (
        "%d pinned entry point(s) have moved; every one of them needs "
        "re-reviewing and re-pinning:\n%s"
        % (len(drifted), "\n".join(
            "  %-24s %s.%s  %s -> %s" % (section, module, name, sha[:12], now[:12])
            for section, module, name, sha, now in drifted)))

    before = _entry_point_sha("main", "rate_limit_gate")
    with _mutated_segment("main", "rate_limit_gate"):
        after = _entry_point_sha("main", "rate_limit_gate")
    assert after != before, "editing the rate-limit gate moved no fingerprint"


def test_a_drifted_entry_point_does_not_hide_the_ones_behind_it():
    """The gate above reports EVERY moved fingerprint, not the first.

    Why it needs its own test: on this tree one middleware entry has already
    drifted, and the sections are walked in a fixed order with middleware
    first. A `main.lifespan` drift therefore sat behind it and was named by
    nothing -- so "one function is listed" carried no information about the
    others, and a background entry point could ship stale behind a failure
    somebody else was expected to clear.

    The oracle is scripted rather than taken from the live tree: a test that
    depends on which entry points happen to be drifting today stops testing
    this the moment somebody re-pins.
    """
    manifest = {
        "middleware": [("main", "rate_limit_gate", "aaaa")],
        "background_entry_points": [("main", "lifespan", "bbbb")],
    }
    both = _entry_point_drift(manifest, sha_of=lambda m, n: "cccc")
    named = {(module, name) for _section, module, name, _sha, _now in both}
    assert named == {("main", "rate_limit_gate"), ("main", "lifespan")}, (
        "two entry points drifted and the gate reported %r -- the ones it "
        "does not name are certified by its silence" % (sorted(named),))

    # ...and it still says nothing when nothing moved, or the assertion above
    # would be reporting drift that is not there.
    assert _entry_point_drift(
        manifest, sha_of=lambda m, n: "aaaa" if n == "rate_limit_gate" else "bbbb") == []


def test_the_admission_rule_is_computed_for_every_module_not_just_main():
    """r14 M7, GATE D -- the assertion the old GATE 8 should have been.

    The previous rule's coverage was decided by a hand-written notion of which
    modules mattered, and every version of that shape has failed the same way:
    it is right about the modules whoever wrote it was thinking of. This
    re-derives each module's module-scope bindings with an INDEPENDENT parse
    written here, and demands the index agree exactly -- so a carve-out added
    anywhere in the admission rule fails on the module it carves out.

    THE MUTATION THIS MUST FAIL ON: any name-conditional in the admission rule
    (`and stem != "models"`), or dropping a node kind from it."""
    files = {p.stem: p for p in sorted(API_DIR.glob("*.py"))}
    index = _binding_index()
    assert set(index) == set(files), (
        f"indexed {sorted(set(index) ^ set(files))} differs from backend/api"
    )
    assert len(files) >= 8, f"only {len(files)} modules found in {API_DIR}"

    for stem, path in files.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        expected = set()

        def collect(body):
            for node in body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    expected.add(node.name)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        for sub in ast.walk(target):
                            if isinstance(sub, ast.Name):
                                expected.add(sub.id)
                elif isinstance(node, ast.AnnAssign):
                    if isinstance(node.target, ast.Name):
                        expected.add(node.target.id)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        expected.add(alias.asname or alias.name.split(".")[0])
                elif isinstance(node, (ast.If, ast.Try, ast.With)):
                    if _is_script_guard(node):
                        continue
                    collect(node.body)
                    collect(getattr(node, "orelse", []))
                    collect(getattr(node, "finalbody", []))
                    for handler in getattr(node, "handlers", []):
                        collect(handler.body)

        collect(tree.body)
        assert set(index[stem]) == expected, (
            f"{stem}: index and an independent parse disagree on "
            f"{sorted(set(index[stem]) ^ expected)[:8]}"
        )
        assert expected, f"{stem}: no module-scope bindings found at all"


def test_a_name_bound_twice_keeps_both_halves_of_its_source(tmp_path):
    """A conditional rebinding must not hide half its source.

    Every module in backend/api binds each module-scope name once, so this
    branch has no live case -- and an unexercised guard is one that is wrong on
    the day it is first needed. Driven on a synthetic module rather than
    asserted about. Also pins the two behaviours the index depends on that no
    production file demonstrates: bindings inside a module-level `try` and
    inside an `if` both count as module scope."""
    module = tmp_path / "synthetic.py"
    module.write_text(
        "LIMIT = 1  # first\n"
        "if True:\n"
        "    LIMIT = 2  # second\n"
        "try:\n"
        "    GUARDED = 3\n"
        "except Exception:\n"
        "    GUARDED = 4\n"
        "def only_here():\n"
        "    return LIMIT\n",
        encoding="utf-8",
    )
    bindings = _index_module(module)
    assert set(bindings) == {"LIMIT", "GUARDED", "only_here"}, sorted(bindings)

    kind, text, _refs = bindings["LIMIT"]
    assert kind == "data"
    assert "# first" in text and "# second" in text, (
        "a rebound name kept only one of its two statements: " + repr(text)
    )
    guarded_kind, guarded_text, _ = bindings["GUARDED"]
    assert "3" in guarded_text and "4" in guarded_text, guarded_text
    assert bindings["only_here"][0] == "def"


def test_the_indexed_segment_is_the_source_the_interpreter_would_show():
    """r14 M7, the fidelity control. The index is only sound if the text it
    hands back for a name is the text that name's statement really is.

    Checked against `inspect.getsource` for every def/class binding in the
    seven non-main modules, plus a fixed sample of main-defined classes. Only
    main's getsource is expensive (measured ~4.8 s for one class, because it
    re-tokenises a 25k-line file), which is why the sample there is fixed and
    small rather than exhaustive.

    NEGATIVE CONTROL: a segment sliced one line short must NOT compare equal --
    otherwise this assertion is satisfied by any two strings."""
    index = _binding_index()
    compared = 0
    for stem, bindings in sorted(index.items()):
        if stem == "main":
            continue
        module = sys.modules.get(stem)
        if module is None:
            continue
        for name, (kind, text, _refs) in sorted(bindings.items()):
            if kind != "def":
                continue
            obj = getattr(module, name, None)
            if obj is None or not _is_ours(obj):
                continue
            try:
                actual = inspect.getsource(obj)
            except (OSError, TypeError):
                continue
            assert text == actual, f"{stem}.{name}: indexed segment != real source"
            compared += 1
    assert compared >= 40, f"only {compared} bindings were actually compared"

    # main's own classes, sampled rather than swept: `inspect.getsource` costs
    # ~4.8 s per class there because it re-tokenises a 25k-line file, and three
    # is enough to prove the same parse behaves the same way in the big module.
    # The sample is COMPUTED, not listed -- the first attempt listed three
    # names of which two are imported into main rather than defined in it, so
    # it compared an empty segment against a real class and would have gone on
    # doing that for as long as the names existed anywhere.
    main_defined = sorted(
        name for name, (kind, _t, _r) in index["main"].items()
        if kind == "def" and _binding_key(getattr(main, name, None)) == ("main", name)
        and inspect.isclass(getattr(main, name, None))
    )
    assert len(main_defined) >= 3, f"main defines only {len(main_defined)} classes"
    for name in main_defined[:3]:
        assert _segment("main", name) == inspect.getsource(getattr(main, name)), name

    # The control that makes the equality above mean something.
    source = (API_DIR / "glicko2.py").read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)
    node = next(n for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    short = "".join(lines[node.lineno - 1:node.end_lineno - 1])
    assert short != _segment("glicko2", node.name), (
        "a one-line-short slice compared equal -- this control proves nothing"
    )


# str.splitlines() breaks on eleven separators. Python's tokenizer breaks on
# three. Everything in this file that turns a line number into source text
# indexes a splitlines() list with an ast line number, so one character from
# the difference anywhere in a file silently shifts every binding below it.
_SPLITLINES_ONLY = "\v\f\x1c\x1d\x1e\x85\u2028\u2029"


def test_no_api_source_contains_a_line_break_only_str_splitlines_sees():
    """The precondition every segment in this file rests on.

    Found in the field: pc_portrait.py wrote its control-character class with
    the characters themselves, so the two separators inside it put ast and
    splitlines() two lines apart and the index handed back the wrong source
    for every binding below. The fidelity control above caught it, but only
    for the bindings it compares -- the fingerprints went on covering shifted
    text either way. Write these as escapes (`\\u2028`), never as themselves.

    NEGATIVE CONTROL: a constructed source carrying one must be flagged, or
    this reads as "no file has one" when it may mean the scan never fires.
    """
    offenders = []
    for path in sorted(API_DIR.glob("*.py")):
        with path.open(encoding="utf-8", newline="") as handle:
            source = handle.read()
        for index, character in enumerate(source):
            if character in _SPLITLINES_ONLY:
                offenders.append("%s:%d U+%04X"
                                 % (path.name, source.count("\n", 0, index) + 1,
                                    ord(character)))
    assert not offenders, (
        "these characters are line breaks to str.splitlines() and not to the "
        "tokenizer, so every segment below them is indexed off by one: %s"
        % ", ".join(offenders[:10]))

    planted = "x = 1\u2028y = 2\n"
    assert any(c in _SPLITLINES_ONLY for c in planted), "the detector is inert"
    assert len(planted.splitlines()) != len(planted.split("\n")) - 1, (
        "the constructed counterexample does not actually shift the count, so "
        "an always-empty scan would pass this test")


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
    """r13 MEDIUM, mutation-proven on the case the finding names: a binding
    DEFINED in tournament_bracket and IMPORTED into tournaments, reached from a
    route. Editing it must move that route's fingerprint; the negative control
    is the same route with nothing edited."""
    target = None
    for route in main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        outside = [i for i in _helper_closure(route.endpoint)
                   if i[0] == "tournament_bracket"]
        if outside:
            target = (route, sorted(outside)[0])
            break
    assert target, "no route reaches a binding defined in tournament_bracket"
    route, (module, name) = target

    before = _route_fingerprint(route)
    assert before == _route_fingerprint(route), (
        "negative control: unedited source must not move"
    )
    with _mutated_segment(module, name):
        after = _route_fingerprint(route)
    assert after != before, (
        f"editing {module}.{name} left {route.path} certified unchanged"
    )


def test_an_import_is_part_of_the_surface_a_route_was_reviewed_with():
    """r15: which object a name denotes decides what the handler does.

    A rollback-and-retry around a database deadlock names `DBAPIError`. Drop
    that import and the retry becomes a NameError on the one path nothing
    routinely exercises -- while every route SHA in this manifest is unchanged,
    because imports were not part of the fingerprint at all."""
    index = _binding_index()
    assert index["main"]["DBAPIError"][0] == "import", (
        "imports must be indexed, and as their own kind"
    )
    covering = _route_covering("main", "DBAPIError")
    assert covering, "no route's fingerprint covers an import it depends on"

    before = _route_fingerprint(covering[0])
    with _mutated_segment("main", "DBAPIError"):
        assert _route_fingerprint(covering[0]) != before, (
            "editing an import moved no route fingerprint"
        )
    assert _route_fingerprint(covering[0]) == before


def test_a_data_binding_composed_from_another_moves_the_fingerprint():
    """r15: the raw-SQL hole, one level of indirection further down.

    `_DC_ELIGIBLE_TERMS` is a SQL fragment built by concatenating
    `_DC_EVIDENCE_TERM` -- the predicate deciding whether a disconnect report is
    accepted. Because data bindings were included but never expanded, the
    composed binding showed only the NAME of what it composed, and rewriting
    that predicate moved nothing. Measured at the time: 0 of 309 routes."""
    index = _binding_index()
    assert index["main"]["_DC_EVIDENCE_TERM"][0] == "data"

    covering = _route_covering("main", "_DC_EVIDENCE_TERM")
    assert covering, (
        "no route covers the disconnect evidence predicate -- the composed "
        "binding is showing the name and not the text again"
    )
    before = _route_fingerprint(covering[0])
    with _mutated_segment("main", "_DC_EVIDENCE_TERM"):
        assert _route_fingerprint(covering[0]) != before
    assert _route_fingerprint(covering[0]) == before


def test_a_data_binding_does_not_drag_in_the_whole_app():
    """The other half of the same rule, and the reason it is worth a test.

    Data-into-data is safe only because it stops at data. `app = FastAPI(...)`
    is a data binding that every route decorator references; letting it follow
    the def it names would put most of the app inside every route's
    fingerprint, which is the failure mode the affordability bound exists to
    catch."""
    index = _binding_index()
    assert index["main"]["app"][0] == "data"
    reached = _reached({("main", "app")})
    assert all(kind == "data" for kind in reached.values()), sorted(
        key for key, kind in reached.items() if kind != "data"
    )[:5]


def test_the_manifest_records_the_order_requests_are_matched_in():
    """r15: sorting the manifest discards which handler actually answers.

    Starlette matches in REGISTRATION order, first match wins. Every identity
    and every fingerprint in this file survives a reordering intact, so without
    this the manifest certifies that a route exists and stays silent about
    whether it is reachable."""
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    recorded = document["route_order"]
    live = _route_registration_order()

    assert live == recorded, (
        "route registration order changed; first match wins, so confirm the "
        "moved route is still the one that answers before rebaselining"
    )
    assert sorted(recorded) != recorded or len(recorded) < 2, (
        "the recorded order is sorted, which is the one order that proves "
        "nothing -- it would survive any reordering of the real routes"
    )
    assert len(recorded) == len(_load_manifest()), (
        "the order section and the identity groups disagree on route count"
    )


def test_no_dynamic_route_is_registered_ahead_of_a_literal_it_swallows():
    """The concrete harm the order section exists to catch.

    `/players/{steam_id}` ahead of `/players/search` makes the literal route
    dead: it returns whatever the dynamic handler does with `steam_id="search"`,
    with no error anywhere. Asserted as a real emptiness, and the detector is
    checked against a constructed pair so an always-empty result cannot pass."""
    live = _route_registration_order()
    assert not _shadowing_pairs(live), _shadowing_pairs(live)[:3]

    # Negative control. Without it this reads as "no shadowing" when what it
    # may mean is that the detector never fires (#342/#441).
    planted = ["GET /api/v1/players/{steam_id} -> main.a",
               "GET /api/v1/players/search -> main.b"]
    assert _shadowing_pairs(planted) == [(planted[0], planted[1])]
    assert not _shadowing_pairs(list(reversed(planted))), (
        "the literal registered FIRST is correct and must not be flagged"
    )


def test_a_module_level_guards_condition_is_part_of_what_it_guards():
    """r15: the block's header was in nobody's segment.

    main binds `_PIL_AVAILABLE` and `_PILImage` inside a try/except, and four
    routes cover them. Without the header the except clause that decides
    whether Pillow is importable could be rewritten with no route fingerprint
    moving -- the condition under which a binding exists is part of what was
    reviewed, not scaffolding around it."""
    index = _binding_index()
    assert "_PIL_AVAILABLE" in index["main"], (
        "the try-guarded binding left the index entirely"
    )
    text = index["main"]["_PIL_AVAILABLE"][1]
    assert text.lstrip().startswith("try:"), (
        "the controlling header is not part of the binding's source: " + text[:80]
    )

    covering = _route_covering("main", "_PIL_AVAILABLE")
    assert covering, "no route covers the Pillow availability flag"
    before = _route_fingerprint(covering[0])
    with _mutated_segment("main", "_PIL_AVAILABLE"):
        assert _route_fingerprint(covering[0]) != before
    assert _route_fingerprint(covering[0]) == before


def test_a_script_only_block_is_in_no_routes_reviewed_surface():
    """r15: `if __name__ == "__main__":` was indexed like any other guard.

    tournament_bracket's self-test binds ordinary names — rows, ids, real,
    extras, s1, s2, sus — and a handler's own locals reference names like those,
    so the cross-module walk resolved routes into a block that never executes
    under the api. Measured before the exclusion: 1008 occurrences over 10
    names, `sus` in 194 route fingerprints. Editing a bracket self-test moved
    two hundred routes."""
    source = (API_DIR / "tournament_bracket.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    script_only = set()
    for node in tree.body:
        if not _is_script_guard(node):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Store):
                script_only.add(inner.id)
    # A positive control on the SAMPLE, not just on the absence: if the block
    # stops being found, an empty set makes every assertion below vacuous.
    assert len(script_only) >= 10, sorted(script_only)
    assert {"rows", "ids", "extras"} <= script_only, sorted(script_only)

    index = _binding_index()
    top_level = {node.name for node in tree.body
                 if isinstance(node, _DEF_NODES)}
    leaked = sorted((script_only - top_level) & set(index["tournament_bracket"]))
    assert not leaked, (
        "script-only bindings are in the index and can be reached by a route: "
        + ", ".join(leaked)
    )


def test_a_later_part_of_a_block_carries_its_own_header(tmp_path):
    """r16: `guard_header` reused the `try:` line for every handler, so
    `except Exception` could become `except ImportError` -- a different set of
    failures reaching a different binding -- with no fingerprint moving, and
    `else`/`finally` bodies had no header at all. Each later part now carries
    its own header on top of the block's."""
    module = tmp_path / "m.py"
    module.write_text(
        "try:\n"
        "    import nothing_here\n"
        "    FLAG = True\n"
        "except Exception:\n"
        "    FLAG = False\n"
        "else:\n"
        "    MODE = 'have'\n"
        "finally:\n"
        "    DONE = 1\n",
        encoding="utf-8")
    before = _index_module(module)
    assert "except Exception:" in before["FLAG"][1], before["FLAG"][1]
    assert "else:" in before["MODE"][1], before["MODE"][1]
    assert "finally:" in before["DONE"][1], before["DONE"][1]
    # The block's own header is still on every part.
    for name in ("FLAG", "MODE", "DONE"):
        assert before[name][1].lstrip().startswith("try:"), before[name][1]

    module.write_text(module.read_text(encoding="utf-8").replace(
        "except Exception:", "except ImportError:"), encoding="utf-8")
    after = _index_module(module)
    assert after["FLAG"][1] != before["FLAG"][1]
    # A header change in one part moves only that part's bindings.
    assert after["MODE"][1] == before["MODE"][1]
    assert after["DONE"][1] == before["DONE"][1]


def test_only_the_canonical_script_guard_is_exempt():
    """r16: `_is_script_guard` accepted any comparison whose left side was
    `__name__`, so `if __name__ != "__main__":` -- a block that RUNS at import
    -- was excluded from every fingerprint while its work still happened."""
    canonical = ast.parse('if __name__ == "__main__":\n    pass\n').body[0]
    assert _is_script_guard(canonical)
    for text in ('if __name__ != "__main__":\n    pass\n',
                 'if __name__ in ("__main__", "x"):\n    pass\n',
                 'if __name__ == "not_main":\n    pass\n',
                 'if "__main__" == __name__:\n    pass\n'):
        assert not _is_script_guard(ast.parse(text).body[0]), text


def test_a_name_referenced_only_by_a_block_header_is_in_the_closure(tmp_path):
    """r2 (Sept 6): a header's TEXT was fingerprinted (r16), but a name it
    references was not in the binding's closure. `except ERRORS:` with
    `ERRORS = (ImportError,)` -- changing the tuple changes which failures
    reach the handler's binding with no fingerprint moving; the same for a
    feature flag in an `if`. The header's names join the closure; the text
    seam is unchanged."""
    module = tmp_path / "m.py"
    module.write_text(
        "ERRORS = (ImportError,)\n"
        "FEATURE = True\n"
        "LOCK = object()\n"
        "try:\n"
        "    import nothing_here\n"
        "    FLAG = True\n"
        "except ERRORS:\n"
        "    FLAG = False\n"
        "else:\n"
        "    MODE_TRY = 'have'\n"
        "if FEATURE:\n"
        "    MODE = 'on'\n"
        "with LOCK:\n"
        "    HELD = 1\n",
        encoding="utf-8")
    index = _index_module(module)
    assert "ERRORS" in index["FLAG"][2], sorted(index["FLAG"][2])
    assert "FEATURE" in index["MODE"][2], sorted(index["MODE"][2])
    assert "LOCK" in index["HELD"][2], sorted(index["HELD"][2])
    # The handler's type belongs to the handler's bindings only: the `else`
    # part of the same try did not run under `except ERRORS`.
    assert "ERRORS" not in index["MODE_TRY"][2], sorted(index["MODE_TRY"][2])
    # The text seam is what it was: the header is still on the binding.
    assert "except ERRORS:" in index["FLAG"][1], index["FLAG"][1]


def test_a_guarded_import_follows_its_guard(tmp_path):
    """Group 2 review (Sept 6): the closure walk treated every import as a leaf
    BEFORE following its refs, and an import's refs are exactly the names of
    the block headers that select it (r2). `if FEATURE: import fast as engine`
    / `else: import slow as engine` -- FEATURE decides which implementation a
    route runs, so it belongs in the route's closure; an unguarded import stays
    a leaf."""
    module = tmp_path / "m.py"
    module.write_text(
        "FEATURE = True\n"
        "if FEATURE:\n"
        "    import json as engine\n"
        "else:\n"
        "    import re as engine\n"
        "import os\n",
        encoding="utf-8")
    index = {"m": _index_module(module)}
    reached = _walk_bindings([("m", "engine")], index=index)
    assert ("m", "FEATURE") in reached, sorted(reached)
    assert reached[("m", "engine")] == "import"
    assert _walk_bindings([("m", "os")], index=index) == {("m", "os"): "import"}
