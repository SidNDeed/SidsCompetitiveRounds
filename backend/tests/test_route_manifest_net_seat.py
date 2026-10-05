"""Exhaustive API-route and formatter non-consumer gate for W1 telemetry."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import inspect
import re
import subprocess
import sys
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

API_DIR = (Path(__file__).parents[1] / "api").resolve()

# ── The reviewed surface: ONE digest of the api image build context ──────
#
# Combat fix pass 7. Until this pass a route's fingerprint covered the
# module-level bindings a static walk said its handler could reach. Every
# review round found another way a dependency escaped that walk, and by fix
# pass 6 every route's closure was the whole tree anyway. The walk is gone and
# nothing is resolved: every route row and every entry-point row carries the
# SAME digest, of every file the api image is built from, so an edit to any
# of those files moves every fingerprint. The digest says THAT something the
# image runs changed, never WHICH route; what a moved digest obliges a
# reviewer to read is stated where the drift test reports it.
#
# THE INPUT SET (`_context_paths`). The api image is built from backend/api
# (docker-compose.yml: `context: ./api`) by `COPY . .`, with no ignore file,
# so the image holds every file in that directory. The set is every file under
# backend/api that git tracks or would track -- tracked files plus untracked
# files the repository's ignore rules do not exclude -- found by git, never
# listed by hand. The ignore rules are the one exclusion, stated once here:
# they exclude bytecode caches (derived from sources in the set), the fetched
# font binaries (the build verifies each against assets/fonts/fonts.lock.json,
# which is in the set) and the private card-art staging directory. One file
# outside the context is a member by an explicit named rule (`_NAMED_MEMBERS`):
# backend/docker-compose.yml, which decides the command the api container
# runs, every environment name the process can see, and every mount.
#
# Not members, and why. SQL reaches the database by migration, under the
# migration rules, and is never read by the image. The private card-art bundle
# and the private review rules are mounted read-only from each box's private
# store and are never in the repository; each is checked by its own digest
# where it is loaded. Configuration values (.env) reach the process through
# the environment names the compose file declares.
#
# THE LINE-ENDING RULE (`_canonical`). The digest is over git BLOB bytes,
# whatever the checkout. A checkout converts only text files and only by
# writing CR before LF (core.autocrlf on this seat; the boxes clone on Linux
# without it), so a file's blob bytes are its working bytes with CRLF turned
# into LF, unless the file holds a NUL byte (binary), which no checkout
# converts. That is exact while no text blob in the set itself carries a CR
# byte: test_f7_the_digest_is_the_blob_digest_on_this_checkout asserts that,
# and that the digest read from git objects equals the one read from the
# working tree on this seat.
#
# THE FRAMING (`_framed`). Each file is framed, never concatenated: the path
# (relative to the repository root, `/` separators, UTF-8) after its byte
# length, then the content's byte length, then the content; each length is
# 8 bytes big-endian, and the files are sorted by path. `_unframed` reads an
# encoding back to the one list it came from, so two different lists cannot
# share an encoding, and SHA-256 is taken over that encoding alone.
#
# DELETED in combat fix pass 7, with nothing resolved in their place: the
# binding index, the reference walk and its placement and exclusion tables,
# the resolver, the dynamic-openness rule and its source lists, the node
# census, the grammar and property oracles, and every test whose only subject
# was one of those (the route seeds and the helper closure went with them:
# they only fed or read the walk). The route list, the
# classification of each route and the entry-point list never came from the
# walk -- they are read from the app (`_route_identities`,
# `_entry_point_sections`) and from the manifest -- and are kept unchanged.

REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTEXT = "backend/api"
_NAMED_MEMBERS = ("backend/docker-compose.yml",)
_CONTEXT_DIGEST = {}


def _git(root, *args, stdin=None):
    return subprocess.run(["git", "-C", str(root), *args], input=stdin,
                          capture_output=True, check=True).stdout


def _context_paths(root=REPO_ROOT):
    """Every member path, relative to `root`, sorted: each file under the
    context that git tracks or would track, and each named member present. A
    tracked file deleted from the working tree is not a member: the image
    would not hold it either."""
    out = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard",
               "--", _CONTEXT)
    paths = {p for p in out.decode("utf-8").split("\0") if p}
    paths.update(_NAMED_MEMBERS)
    return sorted(p for p in paths if (Path(root) / p).is_file())


def _canonical(data):
    """A working copy's bytes as the blob git stores (the line-ending rule)."""
    return data if b"\0" in data else data.replace(b"\r\n", b"\n")


def _working_files(root=REPO_ROOT):
    """[(path, blob bytes)] for the input set as the working tree holds it."""
    return [(path, _canonical((Path(root) / path).read_bytes()))
            for path in _context_paths(root)]


def _blob_files(commit, root=REPO_ROOT):
    """[(path, blob bytes)] for the input set as git objects hold it at
    `commit`: the tracked files under the context and the named members."""
    listing = _git(root, "ls-tree", "-r", "-z", "--full-tree", commit, "--",
                   _CONTEXT, *_NAMED_MEMBERS)
    entries = []
    for record in listing.decode("utf-8").split("\0"):
        if record:
            meta, path = record.split("\t", 1)
            _mode, kind, sha = meta.split()
            if kind == "blob":
                entries.append((path, sha))
    batch = _git(root, "cat-file", "--batch",
                 stdin="".join(sha + "\n" for _path, sha in entries).encode("ascii"))
    files, position = [], 0
    for path, sha in entries:
        end = batch.index(b"\n", position)
        header = batch[position:end].split()
        assert header[0].decode("ascii") == sha and header[1] == b"blob", header
        size = int(header[2])
        files.append((path, batch[end + 1:end + 1 + size]))
        position = end + 1 + size + 1
    assert position == len(batch), "git cat-file returned more than was asked for"
    return sorted(files)


def _framed(files):
    """The one encoding the digest is taken over (THE FRAMING above)."""
    ordered = sorted(files)
    paths = [path for path, _data in ordered]
    assert len(set(paths)) == len(paths), "a path occurs twice"
    out = bytearray()
    for path, data in ordered:
        raw = path.encode("utf-8")
        out += len(raw).to_bytes(8, "big") + raw + len(data).to_bytes(8, "big") + data
    return bytes(out)


def _unframed(encoding):
    """The list `_framed` was given, read back; raises on any malformed input."""
    files, position = [], 0
    while position < len(encoding):
        fields = []
        for _field in ("path", "content"):
            if position + 8 > len(encoding):
                raise ValueError("a length runs past the end")
            size = int.from_bytes(encoding[position:position + 8], "big")
            position += 8
            if position + size > len(encoding):
                raise ValueError("a field runs past the end")
            fields.append(encoding[position:position + size])
            position += size
        files.append((fields[0].decode("utf-8"), fields[1]))
    return files


def _tree_digest(files):
    """SHA-256 over the framed input set."""
    return sha256(_framed(files)).hexdigest()


def _context_digest():
    """The digest every manifest row carries: the working tree's input set,
    read once per process."""
    if "digest" not in _CONTEXT_DIGEST:
        _CONTEXT_DIGEST["digest"] = _tree_digest(_working_files())
    return _CONTEXT_DIGEST["digest"]



def _is_ours(obj):
    """Whether an object's source is ours to review. Used only to name the
    app's own entry points (middleware, exception handlers, the lifespan) as
    (module, name) rows of the manifest."""
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
        # Every route carries the ONE digest of the api image build context
        # (combat fix pass 7, `_context_digest`): no dependency of a handler
        # can sit outside it, because nothing is resolved. The field keeps its
        # historical name so the manifest's row shape does not change; the
        # value is SHA-256.
        identities.append(
            {
                "path": path,
                "methods": sorted(getattr(route, "methods", ()) or ()),
                "module": endpoint.__module__,
                "qualname": endpoint.__qualname__,
                "source_sha1": _context_digest(),
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
    # main d889294's history: 886bed8 r5: +1, the read-only team series status route (377 before); card trading: +7 (the five player trade routes and the two admin trade routes; 370 before); Discord collection reveal: +4 (the packs JSON and strip image routes, the binder JSON and page image routes; 366 before); title-ladder read route: +1 (365 before); quarantine triage: +3 (the two admin triage views and the internal digest; 362 before); Sept 12 pack history: +1 (361 before); portraits: +9 (the writer, the admin clear, the lease triple, four face routes; 352 before); Sept 10 Player Cards: +15 (pc/*, admin/pc/snapshot, internal/pc/*); room rules: +3 (334 before)
    # lane be70f04's history: connect-failure: +4 (the three assembly routes and the G3 seat admin route; 366 before); title-ladder read route: +1 (365 before); quarantine triage: +3 (the two admin triage views and the internal digest; 362 before); Sept 12 pack history: +1 (361 before); portraits: +9 (the writer, the admin clear, the lease triple, four face routes; 352 before); Sept 10 Player Cards: +15 (pc/*, admin/pc/snapshot, internal/pc/*); room rules: +3 (334 before)
    # connect-failure LAND (2026-09-29): main d889294's 378 + the lane's 4 new routes, the union, confirmed by the re-pin dry run
    # main cd8d846's history (via claude/janitor-selftest 17ca44d): dance cards: +5 (the motion upload, the selection, the motion read, the atlas, the motion preview GIF; 378 before); 886bed8 r5: +1, the read-only team series status route (377 before); card trading: +7 (the five player trade routes and the two admin trade routes; 370 before); Discord collection reveal: +4 (the packs JSON and strip image routes, the binder JSON and page image routes; 366 before); title-ladder read route: +1 (365 before); quarantine triage: +3 (the two admin triage views and the internal digest; 362 before); Sept 12 pack history: +1 (361 before); portraits: +9 (the writer, the admin clear, the lease triple, four face routes; 352 before); Sept 10 Player Cards: +15 (pc/*, admin/pc/snapshot, internal/pc/*); room rules: +3 (334 before)
    # lane side before sitting 3: 387 (connect-failure LAND, sitting 2 (2026-09-30): main cd8d846's 383 + the lane's 4 new routes, the union, confirmed by the re-pin dry run)
    # main 0e751993's side: 384 (LAND of main cd8d846: dance cards' +5 (the motion upload, the selection, the motion read, the atlas, the motion preview GIF; 379 before); LAND of main 82c0da6: 886bed8 r5's +1, the read-only team series status route (378 before); Discord fix round 1: +1 (the bot's pack open, internal/pc/packs/open; 377 before); card trading: +7 (the five player trade routes and the two admin trade routes; 370 before); Discord collection reveal: +4 (the packs JSON and strip image routes, the binder JSON and page image routes; 366 before); title-ladder read route: +1 (365 before); quarantine triage: +3 (the two admin triage views and the internal digest; 362 before); Sept 12 pack history: +1 (361 before); portraits: +9 (the writer, the admin clear, the lease triple, four face routes; 352 before); Sept 10 Player Cards: +15 (pc/*, admin/pc/snapshot, internal/pc/*); room rules: +3 (334 before))
    # connect-failure LAND, sitting 3 (2026-09-30): the union of the lane's 387 and main 0e751993's 384 over
    # their shared 383 (main cd8d846) is 388: the lane's 4 new routes plus the Discord fix's 1, confirmed by
    # the re-pin dry run
    # seat evidence V2 (claude/seat-evidence-server-v2): +4 (the seat record and compat outcome routes, the
    # admin seat-evidence view and the release digest registration; 388 before)
    # combat evidence (claude/combat-evidence-server): +2 (the combat record route and the admin
    # combat-evidence view; 392 before)
    assert len(manifest) == 394
    assert len({json.dumps(item, sort_keys=True) for item in expected}) == len(expected)
    assert all(
        entry["classification"] in {"sentinel-exercised", "statically-nonconsumer"}
        for entry in manifest
    )
    assert all(isinstance(entry["reason"], str) and entry["reason"].strip() for entry in manifest)

    exercised = [entry for entry in manifest if entry["classification"] == "sentinel-exercised"]
    static = [entry for entry in manifest if entry["classification"] == "statically-nonconsumer"]
    assert len(exercised) == 1
    # main d889294's history: 886bed8 r5: +1, the read-only team series status route -- a fixed projection of team_series columns, no private Match column reachable (376 before); card trading: +7 (369 before); Discord collection reveal: +4 (365 before); title-ladder read route: +1 (364 before); quarantine triage: +3 (361 before); Sept 12 pack history: +1 (360 before); portraits: +9 (351 before); Sept 10 Player Cards: +15; room rules: +3 (333 before)
    # lane be70f04's history: connect-failure: +4 (365 before); title-ladder read route: +1 (364 before); quarantine triage: +3 (361 before); Sept 12 pack history: +1 (360 before); portraits: +9 (351 before); Sept 10 Player Cards: +15; room rules: +3 (333 before)
    # connect-failure LAND (2026-09-29): main d889294's 377 + the lane's 4 (all statically-nonconsumer), confirmed by the re-pin dry run
    # main cd8d846's history (via claude/janitor-selftest 17ca44d): dance cards: +5 (377 before); 886bed8 r5: +1, the read-only team series status route -- a fixed projection of team_series columns, no private Match column reachable (376 before); card trading: +7 (369 before); Discord collection reveal: +4 (365 before); title-ladder read route: +1 (364 before); quarantine triage: +3 (361 before); Sept 12 pack history: +1 (360 before); portraits: +9 (351 before); Sept 10 Player Cards: +15; room rules: +3 (333 before)
    # lane side before sitting 3: 386 (connect-failure LAND, sitting 2 (2026-09-30): main cd8d846's 382 + the lane's 4 (all statically-nonconsumer), confirmed by the re-pin dry run)
    # main 0e751993's side: 383 (LAND of main cd8d846: dance cards' +5 (378 before); LAND of main 82c0da6: 886bed8 r5's +1, the read-only team series status route -- a fixed projection of team_series columns, no private Match column reachable (377 before); Discord fix round 1: +1 (376 before); card trading: +7 (369 before); Discord collection reveal: +4 (365 before); title-ladder read route: +1 (364 before); quarantine triage: +3 (361 before); Sept 12 pack history: +1 (360 before); portraits: +9 (351 before); Sept 10 Player Cards: +15; room rules: +3 (333 before))
    # connect-failure LAND, sitting 3 (2026-09-30): the union of the lane's 386 and main 0e751993's 383 over
    # their shared 382 is 387: the lane's 4 plus the Discord fix's 1 (all statically-nonconsumer), confirmed
    # by the re-pin dry run
    # seat evidence V2 (claude/seat-evidence-server-v2): +4, all statically-nonconsumer (387 before)
    # combat evidence (claude/combat-evidence-server): +2, both statically-nonconsumer (391 before)
    assert len(static) == 393
    assert _manifest_id(exercised[0]) == SENTINEL_ROUTE

    actual_by_identity = {
        json.dumps(_manifest_id(entry), sort_keys=True): entry for entry in live_routes
    }
    # Every row carries the one context digest (combat fix pass 7), so a move
    # is reported once, with what it obliges, rather than 393 times.
    recorded = {entry["source_sha1"] for entry in static}
    moved = [entry for entry in static
             if entry["source_sha1"]
             != actual_by_identity[json.dumps(_manifest_id(entry), sort_keys=True)]["source_sha1"]]
    assert not moved and len(recorded) == 1, (
        "%d of %d fingerprinted routes carry a digest (%s) that is not the live api "
        "image context digest %s. The digest covers every file the api image is built "
        "from, so it says THAT something changed, never which route. Before re-pinning "
        "(repin_route_manifest.py), read the diff of the input set since the commit that "
        "last re-pinned this file (git diff <that commit> -- backend/api "
        "backend/docker-compose.yml) for anything that can put a W1 private Match column "
        "into a route's output, change what the sentinel-exercised route returns, or "
        "make a route's recorded classification untrue; a route that now can needs its "
        "review again, and a new digest is not that review."
        % (len(moved), len(static), ", ".join(sorted(r[:12] for r in recorded)),
           _context_digest()[:12]))


def _entry_point_sha(module, name):
    """Every entry point carries the same context digest as every route."""
    return _context_digest()


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

    THE MUTATIONS THIS MUST FAIL ON: appending a comment to the module that
    holds `rate_limit_gate` (its sha must move), and making the recovery
    return nothing (the non-empty assertions fire)."""
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

    # The rate-limit gate lives in main.py: a comment appended to that file
    # (combat fix pass 7: the digest covers the whole input set) moves it.
    files = _working_files()
    edited = [(path, data + b"\n# mutation\n" if path == _CONTEXT + "/main.py" else data)
              for path, data in files]
    assert any(path == _CONTEXT + "/main.py" for path, _data in files)
    assert _tree_digest(files) == _entry_point_sha("main", "rate_limit_gate")
    assert _tree_digest(edited) != _entry_point_sha("main", "rate_limit_gate"), (
        "editing the rate-limit gate's module moved no fingerprint")


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
            "p1_sid": "76561193000000001",
            "p2_sid": "76561193000000002",
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
                "steam_id": "76561193000000001",
                "name": "Player One",
                "rounds_won": 5,
                "points_total": 12,
                "won": True,
                "cards": ["Grow"],
            },
            {
                "steam_id": "76561193000000002",
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
                "reporter_steam": "76561193000000001",
                "shots": 0,
                "blocks": 0,
                "cards_picked": 0,
            },
            "auto_invalidated": False,
            "invalidated_at": None,
            "invalidation_reason": None,
            "restoration_required": False,
            "p1_steam_id": "76561193000000001",
            "p2_steam_id": "76561193000000002",
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
            "reporter_steam_id": "76561193000000001",
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


# ── Combat fix pass 7: the digest's proofs, small and total ──────────────
#
# Each proof runs over the input set itself (every file, as the working tree
# holds it) or over a scratch repository built the same way, and prints its
# size. Nothing here models what a route reads: the claim is only that the
# digest moves when any byte the image is built from moves.


def test_f7_the_input_set_is_the_image_build_context(capsys):
    """The set rule against the files that define the image: the compose
    file builds the api from ./api, no ignore file narrows `COPY . .`, every
    COPY source is inside the context and in the set, and no bytecode is."""
    compose = (REPO_ROOT / "backend" / "docker-compose.yml").read_text(encoding="utf-8")
    assert re.search(r"^  api:\n(?:    .*\n|\n)*?    build:\n      context: \./api\n"
                     r"      dockerfile: Dockerfile\n", compose, re.M), (
        "the api service no longer builds from ./api with its Dockerfile: re-derive the set")
    assert not (API_DIR / ".dockerignore").exists(), (
        "an ignore file now narrows the build context: re-derive the set from it")
    paths = _context_paths()
    members = set(paths)
    copies = [line.split()[1:-1] for line in
              (API_DIR / "Dockerfile").read_text(encoding="utf-8").splitlines()
              if line.startswith("COPY ")]
    assert copies, "no COPY line read from the Dockerfile"
    for sources in copies:
        assert not any(s.startswith("--") for s in sources), sources
        for source in sources:
            assert ".." not in source.split("/"), source
            assert source == "." or f"{_CONTEXT}/{source}" in members, source
    assert {f"{_CONTEXT}/{name}" for name in ("main.py", "Dockerfile", "requirements.txt",
            "assets/fonts/fonts.lock.json", "assets/pc/catalogue.json")} <= members
    assert set(_NAMED_MEMBERS) <= members
    assert not [p for p in paths if "__pycache__" in p.split("/") or p.endswith(".pyc")]
    assert all(p.startswith(_CONTEXT + "/") or p in _NAMED_MEMBERS for p in paths)
    files = _working_files()
    with capsys.disabled():
        print("\nPROOF SIZE f7 input set: %d files (%d under %s, %d named), %d bytes; "
              "digest %s" % (len(files), sum(p.startswith(_CONTEXT + "/") for p in paths),
                             _CONTEXT, len(_NAMED_MEMBERS), sum(len(d) for _p, d in files),
                             _context_digest()))


def test_f7_a_new_file_under_the_context_is_a_member_and_nothing_outside_is(tmp_path):
    """The membership rule, on a scratch repository: a file nobody lists that
    appears under the context is IN and moves the digest; an ignored cache
    file under the context, and any file outside the set (a migration, a
    test), move nothing (the negative control)."""
    root = tmp_path / "repo"
    (root / "backend" / "api").mkdir(parents=True)
    (root / "backend" / "sql").mkdir()
    (root / "backend" / "tests").mkdir()
    _git(root, "init", "-q")
    (root / ".gitignore").write_bytes(b"__pycache__/\n")
    (root / "backend" / "api" / "main.py").write_bytes(b"X = 1\n")
    (root / "backend" / "docker-compose.yml").write_bytes(b"services: {}\n")
    (root / "backend" / "sql" / "001_x.sql").write_bytes(b"SELECT 1;\n")
    (root / "backend" / "tests" / "test_x.py").write_bytes(b"def test(): pass\n")
    base = _tree_digest(_working_files(root))
    assert _context_paths(root) == ["backend/api/main.py", "backend/docker-compose.yml"]

    (root / "backend" / "sql" / "001_x.sql").write_bytes(b"SELECT 2;\n")
    (root / "backend" / "tests" / "test_x.py").write_bytes(b"def test(): assert 0\n")
    (root / "backend" / "api" / "__pycache__").mkdir()
    (root / "backend" / "api" / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"\0pyc")
    assert _tree_digest(_working_files(root)) == base, "a file outside the set moved the digest"

    (root / "backend" / "api" / "helpers.py").write_bytes(b"Y = 2\n")
    assert "backend/api/helpers.py" in _context_paths(root)
    assert _tree_digest(_working_files(root)) != base, "a new file under the context moved nothing"


def test_f7_the_digest_is_the_blob_digest_on_this_checkout(capsys):
    """The line-ending rule, proved on this seat: no text blob in the set
    carries a CR byte (so a blob is its own canonical form, as on the boxes
    and in the image); every file git reports unmodified reads back as its
    blob; and on a clean set the digest from git objects at HEAD equals the
    digest from the working tree, CRLF checkout and all."""
    blobs = dict(_blob_files("HEAD"))
    assert blobs, "no blob read from git"
    with_cr = sorted(p for p, data in blobs.items() if b"\0" not in data and b"\r" in data)
    assert not with_cr, f"text blobs carrying CR, the rule is not exact for them: {with_cr}"
    status = _git(REPO_ROOT, "status", "--porcelain", "-z", "--untracked-files=all", "--",
                  _CONTEXT, *_NAMED_MEMBERS).decode("utf-8")
    dirty = {record[3:] for record in status.split("\0") if record[2:3] == " "}
    working = _working_files()
    converted = sum(1 for path, _data in working
                    if (REPO_ROOT / path).read_bytes() != blobs.get(path))
    compared = 0
    for path, data in working:
        if path in blobs and path not in dirty:
            assert data == blobs[path], f"{path} does not read back as its blob"
            compared += 1
    if not dirty:
        assert set(blobs) == {path for path, _data in working}
        assert _tree_digest(sorted(blobs.items())) == _tree_digest(working) == _context_digest()
    with capsys.disabled():
        print("\nPROOF SIZE f7 line endings: %d blobs, %d files compared byte for byte, "
              "%d working copies differ from their blob before the rule (CRLF), 0 text "
              "blobs with CR; %s" % (len(blobs), compared, converted,
                                      "digest from git objects == digest from working tree"
                                      if not dirty else
                                      "set dirty (%d paths): whole-digest equality not "
                                      "asserted" % len(dirty)))


def _f7_flip(data, position):
    return data[:position] + bytes([data[position] ^ 0x01]) + data[position + 1:]


def test_f7_every_single_byte_change_moves_the_digest(capsys):
    """(i) Every file of the set, one byte changed at a time (its first, middle
    and last byte), moves the digest."""
    files = _working_files()
    base = _tree_digest(files)
    edits = unmoved = 0
    for index, (path, data) in enumerate(files):
        positions = sorted({0, len(data) // 2, len(data) - 1}) if data else []
        variants = [_f7_flip(data, p) for p in positions] or [b"\0"]
        for variant in variants:
            edits += 1
            moved = files[:index] + [(path, variant)] + files[index + 1:]
            unmoved += _tree_digest(moved) == base
    with capsys.disabled():
        print("\nPROOF SIZE f7 bytes: %d files, %d single-byte edits, %d unmoved"
              % (len(files), edits, unmoved))
    assert unmoved == 0 and edits >= len(files)


_F7_ROUTE = 'def route():\n    return globals().get("X", 0)\n'


def test_f7_the_reviewer_relocation_moves_the_digest():
    """(ii) Round 7's example verbatim: moving `X=2` across the file boundary
    keeps the plain concatenation of the two files byte-identical and changes
    what the route returns (2 to 0); the framed digest moves."""
    before = [("backend/api/a.py", b"X=1\n"), ("backend/api/b.py", b"X=2\n" + _F7_ROUTE.encode())]
    after = [("backend/api/a.py", b"X=1\nX=2\n"), ("backend/api/b.py", _F7_ROUTE.encode())]
    plain = lambda files: b"".join(data for _path, data in sorted(files))  # noqa: E731
    assert plain(before) == plain(after)
    results = []
    for files in (before, after):
        namespace = {}
        exec(dict(files)["backend/api/b.py"].decode(), namespace)
        results.append(namespace["route"]())
    assert results == [2, 0]
    assert _tree_digest(before) != _tree_digest(after)


def test_f7_rename_add_delete_and_swap_each_move_the_digest(capsys):
    """(iii) Over the whole set: renaming each file, deleting each file,
    adding a file, and swapping the contents of each pair of neighbouring
    files with different contents each move the digest."""
    files = _working_files()
    base = _tree_digest(files)
    counts = {"rename": 0, "delete": 0, "add": 0, "swap": 0}
    for index, (path, data) in enumerate(files):
        others = files[:index] + files[index + 1:]
        assert _tree_digest(others + [(path + "x", data)]) != base, ("rename", path)
        assert _tree_digest(others) != base, ("delete", path)
        counts["rename"] += 1
        counts["delete"] += 1
    assert _tree_digest(files + [(_CONTEXT + "/zz_new.py", b"")]) != base
    counts["add"] += 1
    for index in range(len(files) - 1):
        (p1, d1), (p2, d2) = files[index], files[index + 1]
        if d1 == d2:
            continue
        swapped = files[:index] + [(p1, d2), (p2, d1)] + files[index + 2:]
        assert _tree_digest(swapped) != base, ("swap", p1, p2)
        counts["swap"] += 1
    with capsys.disabled():
        print("\nPROOF SIZE f7 structure: %s, 0 unmoved"
              % ", ".join("%s %d" % kv for kv in counts.items()))


def test_f7_the_framing_has_one_reading(capsys):
    """(v) Generated: 20000 random lists of (path, content) over a two-letter
    alphabet, so that many different lists share one plain concatenation.
    Every list reads back from its encoding unchanged; within every class of
    lists with the same plain concatenation the digests are distinct; and the
    digest does not depend on the order the list is given in."""
    import random
    rng = random.Random(7)
    lists = set()
    while len(lists) < 20000:
        n = rng.randint(1, 3)
        paths = set()
        while len(paths) < n:
            paths.add("".join(rng.choice("ab") for _ in range(rng.randint(1, 3))))
        lists.add(tuple(sorted((p, bytes(rng.choice(b"ab") for _ in range(rng.randint(0, 3))))
                               for p in paths)))
    classes = defaultdict(set)
    for files in lists:
        assert _unframed(_framed(files)) == list(files), files
        shuffled = list(files)
        rng.shuffle(shuffled)
        assert _tree_digest(shuffled) == _tree_digest(files)
        classes[b"".join(p.encode() + d for p, d in files)].add(files)
    shared = [members for members in classes.values() if len(members) > 1]
    in_shared = sum(len(members) for members in shared)
    for members in shared:
        assert len({_tree_digest(files) for files in members}) == len(members), sorted(members)
    with capsys.disabled():
        print("\nPROOF SIZE f7 framing: %d distinct lists, %d plain-concatenation classes "
              "holding more than one list (%d lists), every digest within each distinct; "
              "%d read back unchanged" % (len(lists), len(shared), in_shared, len(lists)))
    assert len(shared) > 100, "the generator no longer produces colliding concatenations"
