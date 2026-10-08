"""Exhaustive API-route and formatter non-consumer gate for W1 telemetry."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import inspect
import os
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

# ── The reviewed surface: ONE digest of the api image's build inputs ─────
#
# Combat fix pass 7 replaced the per-route walk with one digest; fix pass 8
# makes its input set the Docker build context itself. Every route row and
# every entry-point row carries the SAME digest, of every file the api image
# is built from, so an edit to any of them moves every fingerprint. The digest
# says THAT something the image takes changed, never WHICH route; what a
# moved digest obliges a reviewer to read is stated where the drift test
# reports it.
#
# THE INPUT SET (`_context_paths`). docker-compose.yml builds the api from
# `context: ./api`; Docker sends that directory minus what its .dockerignore
# excludes, and the Dockerfile's `COPY . .` copies what was sent. The set is
# computed the same way, from the WORKING DIRECTORY: every path under
# backend/api that the committed .dockerignore does not exclude (read and
# applied by `_dockerignore_rules` / `_docker_ignored`, Docker's rules as
# written, implemented here and tested against them -- docker build does not
# run on this seat, so nothing here was compared with a daemon), plus the
# Dockerfile and the .dockerignore whatever the patterns say (Docker sends
# both regardless), plus backend/docker-compose.yml by a named rule
# (`_NAMED_MEMBERS`: it decides the command the container runs, every
# environment name the process sees, and every mount).
#
# THE REFUSAL. The digest is taken only when that set IS the committed tree:
# every member a regular file committed at HEAD whose working bytes are its
# blob under the line-ending rule, and every committed file the patterns keep
# present. Anything else -- a file git ignores or does not track, an edited or
# deleted committed file, a link -- raises ContextRefused naming every such
# path, and no fingerprint is computed. So a file Docker would copy can never
# sit outside the digest: it is either a committed member or a refusal.
#
# Not members, and why. SQL reaches the database by migration under the
# migration rules and is never read by the image. The private card-art bundle
# and the private review rules are mounted read-only from each box's private
# store; each is checked by its own digest where it is loaded. Configuration
# values (.env) reach the process through the environment names the compose
# file declares. The bytes the image takes from OUTSIDE the context are
# locked, not digested: the base image by its registry digest, the Python
# packages by requirements.lock (exactly one wheel hash per package, installed
# with --require-hashes; the lock is a member), the apt packages by apt.lock
# (the SHA-256 of each .deb, checked by apt_lock.py before dpkg reads it; both
# are members), the fonts by fonts.lock.json (a member) and a verification
# after the copy. What a build actually installed -- the SHA-256 of every
# wheel pip verified (its --report) with the digest of the RECORD it wrote,
# and of every .deb dpkg was given -- is written into the image
# (build_manifest.py), compared there with both locks, and answered on
# /health as `build_manifest` ("refused" when an identity is not the locks').
#
# THE LINE-ENDING RULE (`_canonical`). The digest is over git BLOB bytes,
# whatever the checkout: a working copy's bytes with CRLF turned into LF,
# unless the file holds a NUL byte (binary), which no checkout converts. That
# is exact while no text blob carries a CR byte, which the line-ending proof
# asserts; the refusal above compares every member with its blob.
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
# they only fed or read the walk). The route list, the classification of each
# route and the entry-point list never came from the walk -- they are read
# from the app (`_route_identities`, `_entry_point_sections`) and from the
# manifest -- and are kept unchanged.

REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTEXT = "backend/api"
_NAMED_MEMBERS = ("backend/docker-compose.yml",)
_ALWAYS_SENT = ("Dockerfile", ".dockerignore")
_CONTEXT_DIGEST = {}


class ContextRefused(AssertionError):
    """The build context is not exactly the committed tree: no digest."""


def _git(root, *args, stdin=None):
    return subprocess.run(["git", "-C", str(root), *args], input=stdin,
                          capture_output=True, check=True).stdout


# ── The .dockerignore rules, as Docker documents and applies them ────────
#
# Reading (`_dockerignore_patterns`): one pattern per line (a trailing CR
# dropped, a UTF-8 BOM dropped from the first line); a line whose FIRST
# character is `#` is a comment (checked before trimming, so ` #x` is a
# pattern); surrounding whitespace trimmed; blank lines skipped; a leading
# `!` (then trimmed again) makes an exception; the rest cleaned as Go's
# filepath.Clean cleans it, and one leading `/` dropped. Matching
# (`_docker_ignored`): patterns are applied in order to a path relative to the
# context AND to each of its parent directories, the last one that matches
# deciding; an exception is only consulted while the path is excluded and an
# exclusion only while it is not. Each pattern is Go filepath.Match syntax
# (`*` any run of non-`/`, `?` one non-`/`, `[...]` a class, `\` escapes the
# next character) extended by `**`, which matches any number of directories
# including none; a pattern that starts with `**` and has no other wildcard
# matches any path that ends with the rest, and one that ends with `**` and
# has no other wildcard matches any path that starts with what precedes it.
# A malformed pattern refuses.

_GO_ESCAPE = ".+()|{}$"


def _go_clean(path):
    """Go's filepath.Clean for a `/`-separated path."""
    rooted = path.startswith("/")
    parts = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            elif not rooted:
                parts.append("..")
            continue
        parts.append(part)
    cleaned = ("/" if rooted else "") + "/".join(parts)
    return cleaned or ("/" if rooted else ".")


def _dockerignore_patterns(text):
    """The pattern strings Docker reads from a .dockerignore's text."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    patterns = []
    for index, line in enumerate(lines):
        if line.endswith("\r"):
            line = line[:-1]
        if index == 0 and line.startswith("﻿"):
            line = line[1:]
        if line.startswith("#"):
            continue
        line = line.strip()
        if not line:
            continue
        invert = line.startswith("!")
        if invert:
            line = line[1:].strip()
        if line:
            line = _go_clean(line)
            if len(line) > 1 and line.startswith("/"):
                line = line[1:]
        patterns.append(("!" if invert else "") + line)
    return patterns


def _compile_pattern(pattern):
    """A predicate over a context-relative path for one cleaned pattern."""
    regex, kind, i = "^", "exact", 0
    while i < len(pattern):
        ch = pattern[i]
        first = i == 0
        i += 1
        if ch == "*":
            if i < len(pattern) and pattern[i] == "*":
                i += 1
                if i < len(pattern) and pattern[i] == "/":
                    i += 1
                if i == len(pattern):
                    if kind == "exact":
                        kind = "prefix"
                    else:
                        regex += ".*"
                        kind = "regex"
                else:
                    regex += "(.*/)?"
                    kind = "regex"
                if first:
                    kind = "suffix"
            else:
                regex += "[^/]*"
                kind = "regex"
        elif ch == "?":
            regex += "[^/]"
            kind = "regex"
        elif ch in _GO_ESCAPE:
            regex += "\\" + ch
        elif ch == "\\":
            if i < len(pattern):
                regex += "\\" + pattern[i]
                i += 1
                kind = "regex"
            else:
                regex += "\\\\"
        elif ch in "[]":
            regex += ch
            kind = "regex"
        else:
            regex += ch
    try:
        compiled = re.compile(regex + "$", re.S)
    except re.error as exc:
        raise ContextRefused(f".dockerignore pattern {pattern!r} is malformed: {exc}") from None
    if kind == "exact":
        return lambda path: path == pattern
    if kind == "prefix":
        return lambda path: path.startswith(pattern[:-2])
    if kind == "suffix":
        suffix = pattern[2:]
        return lambda path: path.endswith(suffix) or (suffix[:1] == "/" and path == suffix[1:])
    return lambda path: compiled.match(path) is not None


def _dockerignore_rules(text):
    """[(is_exception, predicate, pattern)] in file order."""
    rules = []
    for pattern in _dockerignore_patterns(text):
        pattern = _go_clean(pattern.strip()) if pattern.strip() else ""
        if not pattern:
            continue
        exception = pattern.startswith("!")
        if exception:
            pattern = pattern[1:]
            if not pattern:
                raise ContextRefused('.dockerignore holds the illegal exception pattern "!"')
        rules.append((exception, _compile_pattern(pattern), pattern))
    return rules


def _docker_ignored(rules, path):
    """Whether Docker leaves context-relative `path` out of the context."""
    parent = path.rsplit("/", 1)[0] if "/" in path else "."
    parents = parent.split("/")
    ignored = False
    for exception, matches, _pattern in rules:
        if exception != ignored:
            continue
        hit = matches(path)
        if not hit and parent != ".":
            hit = any(matches("/".join(parents[:k + 1])) for k in range(len(parents)))
        if hit:
            ignored = not exception
    return ignored


def _sent(paths, rules):
    """The context-relative paths Docker sends, of `paths`."""
    return sorted(p for p in paths if p in _ALWAYS_SENT or not _docker_ignored(rules, p))


def _canonical(data):
    """A working copy's bytes as the blob git stores (the line-ending rule)."""
    return data if b"\0" in data else data.replace(b"\r\n", b"\n")


def _committed(commit, root=REPO_ROOT):
    """{path: (mode, blob bytes)} for every file git holds at `commit` under
    the context and among the named members."""
    listing = _git(root, "ls-tree", "-r", "-z", "--full-tree", commit, "--",
                   _CONTEXT, *_NAMED_MEMBERS)
    entries = []
    for record in listing.decode("utf-8").split("\0"):
        if record:
            meta, path = record.split("\t", 1)
            mode, kind, sha = meta.split()
            if kind == "blob":
                entries.append((path, mode, sha))
    batch = _git(root, "cat-file", "--batch",
                 stdin="".join(sha + "\n" for _p, _m, sha in entries).encode("ascii"))
    out, position = {}, 0
    for path, mode, sha in entries:
        end = batch.index(b"\n", position)
        header = batch[position:end].split()
        assert header[0].decode("ascii") == sha and header[1] == b"blob", header
        size = int(header[2])
        out[path] = (mode, batch[end + 1:end + 1 + size])
        position = end + 1 + size + 1
    assert position == len(batch), "git cat-file returned more than was asked for"
    return out


def _rules_at(committed):
    """The .dockerignore rules a committed tree carries."""
    entry = committed.get(f"{_CONTEXT}/.dockerignore")
    return _dockerignore_rules(entry[1].decode("utf-8")) if entry else []


def _blob_files(commit, root=REPO_ROOT):
    """[(path, blob bytes)] for the input set as git objects hold it at
    `commit`: the committed files its own .dockerignore keeps, the Dockerfile,
    the .dockerignore, and the named members."""
    committed = _committed(commit, root)
    rules = _rules_at(committed)
    prefix = _CONTEXT + "/"
    keep = set(_sent([p[len(prefix):] for p in committed if p.startswith(prefix)], rules))
    return sorted((path, data) for path, (_mode, data) in committed.items()
                  if path in _NAMED_MEMBERS or path[len(prefix):] in keep)


def _context_scan(root=REPO_ROOT):
    """(the input set's paths, every refusal) from the working directory."""
    root = Path(root)
    context = root / _CONTEXT
    ignore = context / ".dockerignore"
    rules = _dockerignore_rules(ignore.read_bytes().decode("utf-8")) if ignore.is_file() else []
    on_disk = []
    for directory, dirnames, filenames in os.walk(context):
        dirnames.sort()
        here = Path(directory)
        for name in sorted(filenames + [d for d in dirnames if (here / d).is_symlink()]):
            on_disk.append((here / name).relative_to(context).as_posix())
    committed = _committed("HEAD", root)
    refusals = []
    members = []
    for rel in _sent(on_disk, rules):
        path = f"{_CONTEXT}/{rel}"
        members.append(path)
    prefix = _CONTEXT + "/"
    kept = set(_sent([p[len(prefix):] for p in committed if p.startswith(prefix)], rules))
    for rel in sorted(kept - {m[len(prefix):] for m in members}):
        refusals.append(f"{prefix}{rel}: committed but absent from the working directory")
    for path in _NAMED_MEMBERS:
        if (root / path).exists() or path in committed:
            members.append(path)
    for path in members:
        local = root / path
        if local.is_symlink() or not local.is_file():
            refusals.append(f"{path}: not a regular file" if local.exists() or local.is_symlink()
                            else f"{path}: committed but absent from the working directory")
            continue
        if path not in committed:
            refusals.append(f"{path}: not a committed file (Docker would copy it)")
        elif committed[path][0] not in ("100644", "100755"):
            refusals.append(f"{path}: committed as mode {committed[path][0]}, not a regular file")
        elif _canonical(local.read_bytes()) != committed[path][1]:
            refusals.append(f"{path}: working bytes differ from the committed blob")
    return sorted(set(members)), sorted(set(refusals))


def _context_paths(root=REPO_ROOT):
    """Every member path, relative to `root`, sorted; raises ContextRefused
    naming every refusal when the context is not exactly the committed tree."""
    members, refusals = _context_scan(root)
    if refusals:
        raise ContextRefused("the api build context is not the committed tree, so no digest "
                             "is taken (commit the file, delete it, or exclude it in "
                             "backend/api/.dockerignore):\n  " + "\n  ".join(refusals))
    return members


def _working_files(root=REPO_ROOT):
    """[(path, blob bytes)] for the input set as the working tree holds it
    (equal to the committed blobs, or `_context_paths` refused)."""
    return [(path, _canonical((Path(root) / path).read_bytes()))
            for path in _context_paths(root)]


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


def _context_only(files):
    """The members inside the build context (the named members left out):
    what the image itself receives, and what build_manifest.py digests."""
    return [(path, data) for path, data in files if path.startswith(_CONTEXT + "/")]


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
    file builds the api from ./api, the context's committed .dockerignore is
    the ignore file the set applies (and a member), every COPY source is inside
    the context and in the set, and no bytecode is."""
    compose = (REPO_ROOT / "backend" / "docker-compose.yml").read_text(encoding="utf-8")
    assert re.search(r"^  api:\n(?:    .*\n|\n)*?    build:\n      context: \./api\n"
                     r"      dockerfile: Dockerfile\n", compose, re.M), (
        "the api service no longer builds from ./api with its Dockerfile: re-derive the set")
    assert (API_DIR / ".dockerignore").is_file(), "the build context lost its .dockerignore"
    assert not (API_DIR / "Dockerfile.dockerignore").exists(), (
        "a Dockerfile-specific ignore file replaces .dockerignore: re-derive the set from it")
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
    assert {f"{_CONTEXT}/{name}" for name in ("main.py", "Dockerfile", ".dockerignore",
            "requirements.txt", "requirements.lock", "build_manifest.py",
            "apt.lock", "apt_lock.py", "assets/fonts/fonts.lock.json", "assets/pc/catalogue.json")} <= members
    assert set(_NAMED_MEMBERS) <= members
    assert not [p for p in paths if "__pycache__" in p.split("/") or p.endswith(".pyc")]
    assert all(p.startswith(_CONTEXT + "/") or p in _NAMED_MEMBERS for p in paths)
    files = _working_files()
    with capsys.disabled():
        print("\nPROOF SIZE f7 input set: %d files (%d under %s, %d named), %d bytes; "
              "digest %s" % (len(files), sum(p.startswith(_CONTEXT + "/") for p in paths),
                             _CONTEXT, len(_NAMED_MEMBERS), sum(len(d) for _p, d in files),
                             _context_digest()))


def _f8_commit(root, message):
    hooks = root.parent / "no-hooks"
    hooks.mkdir(exist_ok=True)
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=gate", "-c", "user.email=gate@example.invalid",
         "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={hooks}",
         "commit", "-q", "--allow-empty", "-m", message)


def _f8_refusals(root):
    with pytest.raises(ContextRefused) as refused:
        _context_paths(root)
    return str(refused.value)


def test_f8_the_context_is_the_committed_tree_or_no_digest(tmp_path, capsys):
    """The membership rule and the refusal, on a scratch repository built like
    this one: a committed file under the context is IN; a file the
    .dockerignore excludes is out and refuses nothing (whether git ignores it
    or tracks it); a file git ignores that Docker would copy, an untracked
    file, an edited committed file and a deleted committed file each REFUSE,
    naming the path; the Dockerfile and the .dockerignore are members even
    when a pattern names them; files outside the context and the named
    members (a migration, a test) move nothing (the negative control)."""
    root = tmp_path / "repo"
    api = root / "backend" / "api"
    api.mkdir(parents=True)
    (root / "backend" / "sql").mkdir()
    (root / "backend" / "tests").mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "core.autocrlf", "false")
    (root / ".gitignore").write_bytes(b"__pycache__/\ndist/\n*.log\n")
    (api / ".dockerignore").write_bytes(b"**/__pycache__\n**/*.log\n")
    (api / "Dockerfile").write_bytes(b"FROM scratch\nCOPY . .\n")
    (api / "main.py").write_bytes(b"X = 1\n")
    (root / "backend" / "docker-compose.yml").write_bytes(b"services: {}\n")
    (root / "backend" / "sql" / "001_x.sql").write_bytes(b"SELECT 1;\n")
    (root / "backend" / "tests" / "test_x.py").write_bytes(b"def test(): pass\n")
    _f8_commit(root, "base")
    base = _tree_digest(_working_files(root))
    assert _context_paths(root) == ["backend/api/.dockerignore", "backend/api/Dockerfile",
                                    "backend/api/main.py", "backend/docker-compose.yml"]
    cases = 0

    # Excluded by .dockerignore: out, no refusal; outside files: nothing moves.
    (api / "__pycache__").mkdir()
    (api / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"\0pyc")
    (api / "run.log").write_bytes(b"log\n")
    (root / "backend" / "sql" / "001_x.sql").write_bytes(b"SELECT 2;\n")
    (root / "backend" / "tests" / "test_x.py").write_bytes(b"def test(): assert 0\n")
    assert _tree_digest(_working_files(root)) == base, "an excluded or outside file moved the digest"
    cases += 1

    # Ignored by git, copied by Docker: refuses, naming it.
    (api / "dist").mkdir()
    (api / "dist" / "patch.py").write_bytes(b"X = 2\n")
    assert "backend/api/dist/patch.py: not a committed file" in _f8_refusals(root)
    (api / "dist" / "patch.py").unlink()
    cases += 1

    # Untracked and not ignored: refuses.
    (api / "helpers.py").write_bytes(b"Y = 2\n")
    assert "backend/api/helpers.py: not a committed file" in _f8_refusals(root)
    cases += 1

    # Committed: a member, and the digest moves.
    _f8_commit(root, "helpers")
    assert "backend/api/helpers.py" in _context_paths(root)
    with_helpers = _tree_digest(_working_files(root))
    assert with_helpers != base
    cases += 1

    # An edited committed file refuses; so does a deleted one.
    (api / "main.py").write_bytes(b"X = 3\n")
    assert "backend/api/main.py: working bytes differ" in _f8_refusals(root)
    (api / "main.py").write_bytes(b"X = 1\n")
    (api / "helpers.py").unlink()
    assert "backend/api/helpers.py: committed but absent" in _f8_refusals(root)
    (api / "helpers.py").write_bytes(b"Y = 2\n")
    cases += 2

    # A committed file the .dockerignore excludes is out of the set.
    _git(root, "add", "-f", "backend/api/run.log")
    _f8_commit(root, "a committed log")
    assert "backend/api/run.log" not in _context_paths(root)
    assert _tree_digest(_working_files(root)) == with_helpers
    cases += 1

    # A pattern naming the Dockerfile and the .dockerignore keeps them in.
    (api / ".dockerignore").write_bytes(b"**/__pycache__\n**/*.log\nDockerfile\n.dockerignore\n")
    _f8_commit(root, "ignore the recipe")
    assert {"backend/api/Dockerfile", "backend/api/.dockerignore"} <= set(_context_paths(root))
    cases += 1
    with capsys.disabled():
        print("\nPROOF SIZE f8 membership: %d scratch cases (excluded, git-ignored, untracked, "
              "committed, edited, deleted, committed-but-excluded, recipe kept), 0 wrong" % cases)


def test_f7_the_digest_is_the_blob_digest_on_this_checkout(capsys):
    """The line-ending rule, proved on this seat: no text blob in the set
    carries a CR byte (so a blob is its own canonical form, as on the boxes
    and in the image); every member reads back as its blob; and the digest
    from git objects at HEAD equals the digest from the working tree, CRLF
    checkout and all (a context that is not the committed tree refuses before
    this test can compare anything)."""
    blobs = dict(_blob_files("HEAD"))
    assert blobs, "no blob read from git"
    with_cr = sorted(p for p, data in blobs.items() if b"\0" not in data and b"\r" in data)
    assert not with_cr, f"text blobs carrying CR, the rule is not exact for them: {with_cr}"
    working = _working_files()
    converted = sum(1 for path, _data in working
                    if (REPO_ROOT / path).read_bytes() != blobs.get(path))
    for path, data in working:
        assert data == blobs.get(path), f"{path} does not read back as its blob"
    assert set(blobs) == {path for path, _data in working}
    assert _tree_digest(sorted(blobs.items())) == _tree_digest(working) == _context_digest()
    with capsys.disabled():
        print("\nPROOF SIZE f7 line endings: %d blobs, %d files compared byte for byte, "
              "%d working copies differ from their blob before the rule (CRLF), 0 text "
              "blobs with CR; digest from git objects == digest from working tree"
              % (len(blobs), len(working), converted))


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
        lists.add(tuple((p, bytes(rng.choice(b"ab") for _ in range(rng.randint(0, 3))))
                        for p in sorted(paths)))
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


# ── Combat fix pass 8: the build context as Docker computes it, and the
# bytes the image takes from outside it ───────────────────────────────────


# (.dockerignore text, {context-relative path: ignored?}) -- each expectation
# is what Docker's written rules say (docs.docker.com, "Build context",
# .dockerignore; and the reading rules above). The matcher is ours: these are
# checked against the rules as written, not against a daemon.
_F8_IGNORE_CASES = [
    ("*/temp*", {"somedir/temporary.txt": True, "somedir/temp": True, "temp.txt": False,
                 "a/b/temp.txt": False, "a/temp/x.txt": True}),
    ("*/*/temp*", {"somedir/subdir/temporary.txt": True, "somedir/temporary.txt": False}),
    ("temp?", {"tempa": True, "temp": False, "tempab": False, "d/tempa": False}),
    ("**/*.go", {"main.go": True, "a/b/c.go": True, "a/go": False}),
    ("*.md\n!README.md", {"a.md": True, "README.md": False}),
    ("*.md\n!README*.md\nREADME-secret.md", {"README-secret.md": True, "README.md": False,
                                             "x.md": True}),
    ("*.md\nREADME-secret.md\n!README*.md", {"README-secret.md": False, "x.md": True}),
    ("logs", {"logs": True, "logs/a.txt": True, "mylogs/a": False, "a/logs/b": False}),
    ("logs/", {"logs/a.txt": True, "logs2/a.txt": False}),
    ("/abs/path", {"abs/path": True, "abs/path/x": True, "x/abs/path": False}),
    ("./x/../y", {"y": True, "x": False, "x/y": False}),
    ("#comment\n #notcomment", {"#comment": False, "#notcomment": True}),
    ("**", {"anything/at/all": True, "top": True}),
    ("**/__pycache__", {"__pycache__/a.pyc": True, "a/__pycache__/b.pyc": True,
                        "a/x__pycache__": False}),
    ("foo/**", {"foo/bar": True, "foo/bar/baz": True, "foo": False, "food/x": False}),
    ("[a-c]at", {"bat": True, "dat": False}),
    ("\\*star", {"*star": True, "xstar": False}),
    ("dir\n!dir/keep.txt", {"dir/keep.txt": False, "dir/other.txt": True}),
    ("*.log", {"a.log": True, "d/a.log": False}),
    ("  spaced.txt  ", {"spaced.txt": True, "  spaced.txt  ": False}),
    ("﻿bom.txt\r\nnext.txt\r\n", {"bom.txt": True, "next.txt": True}),
    ("a.b", {"a.b": True, "axb": False}),
    ("**/*.pyc\n!keep/**", {"keep/x.pyc": False, "other/x.pyc": True, "x.pyc": True}),
]


def test_f8_the_dockerignore_matcher_follows_the_written_rules(capsys):
    """The matcher against twenty-odd patterns of the written rules: anchoring
    at the context root, `*` and `?` stopping at `/`, `**` crossing
    directories, exceptions and their order, directory patterns excluding
    everything under them, comments, cleaning, a leading `/`, trimming, a BOM
    and CRLF; and a malformed pattern refuses."""
    checked = patterns = 0
    for text, expected in _F8_IGNORE_CASES:
        rules = _dockerignore_rules(text)
        patterns += len(rules)
        for path, ignored in expected.items():
            assert _docker_ignored(rules, path) is ignored, (text, path, ignored)
            checked += 1
    for bad in ("[", "!"):
        with pytest.raises(ContextRefused):
            _dockerignore_rules(bad)
    with capsys.disabled():
        print("\nPROOF SIZE f8 matcher: %d ignore files, %d patterns, %d paths checked against "
              "the written rules, 2 malformed refused; the matcher is ours, not compared "
              "with a daemon" % (len(_F8_IGNORE_CASES), patterns, checked))
    assert len(_F8_IGNORE_CASES) >= 20 and patterns >= 20


def test_f8_the_set_equals_the_context_docker_would_send(capsys):
    """Two listings of this checkout's context agree: the gate's, from the
    working directory, and a dry listing from the git index (every file git
    has under the context) with the committed .dockerignore applied the same
    way, plus the named members. The paths the .dockerignore keeps out are
    counted."""
    paths = _context_paths()
    rules = _dockerignore_rules((API_DIR / ".dockerignore").read_bytes().decode("utf-8"))
    indexed = [p for p in _git(REPO_ROOT, "ls-files", "-z", "--", _CONTEXT).decode("utf-8").split("\0") if p]
    prefix = _CONTEXT + "/"
    dry = sorted([prefix + p for p in _sent([p[len(prefix):] for p in indexed], rules)]
                 + list(_NAMED_MEMBERS))
    assert paths == dry
    on_disk = [(Path(d) / f).relative_to(API_DIR).as_posix()
               for d, _dirs, files in os.walk(API_DIR) for f in files]
    excluded = [p for p in on_disk if p not in _ALWAYS_SENT and _docker_ignored(rules, p)]
    files = _working_files()
    with capsys.disabled():
        print("\nPROOF SIZE f8 context: %d members (%d in the context, %d named), %d bytes; %d "
              "files on disk under the context kept out by .dockerignore; the index listing "
              "equals the working-directory listing" % (
                  len(paths), len(_context_only(files)), len(_NAMED_MEMBERS),
                  sum(len(d) for _p, d in files), len(excluded)))


def _f8_dockerfile():
    return (API_DIR / "Dockerfile").read_text(encoding="utf-8")


def test_f8_the_fonts_are_verified_last_and_never_taken_from_the_context(tmp_path, monkeypatch):
    """The fonts the build fetched and verified cannot be replaced by the code
    copy: every font the lock names is excluded from the context, and the last
    RUN step, after the copy, verifies them again; that verification never
    fetches, and refuses a missing font and a font whose bytes moved."""
    df = _f8_dockerfile()
    copy_all = re.search(r"^COPY \. \.\s*$", df, re.M)
    runs = list(re.finditer(r"^RUN .*$", df, re.M))
    assert copy_all and runs and runs[-1].start() > copy_all.start()
    assert "python assets/fonts/fetch_fonts.py --verify" in runs[-1].group(0)
    assert not re.search(r"^(COPY|ADD) ", df[copy_all.end():], re.M), "a copy after the code copy"
    rules = _dockerignore_rules((API_DIR / ".dockerignore").read_bytes().decode("utf-8"))
    lock = json.loads((API_DIR / "assets" / "fonts" / "fonts.lock.json").read_text(encoding="utf-8"))
    assert lock and all(_docker_ignored(rules, "assets/fonts/" + name) for name in lock)

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "f8_fetch_fonts", API_DIR / "assets" / "fonts" / "fetch_fonts.py")
    fetch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch)
    bodies = {name: (name + "-bytes").encode() for name in fetch.FONTS}
    fake = {name: {"sha256": sha256(body).hexdigest(), "bytes": len(body), "url": "x"}
            for name, body in bodies.items()}
    (tmp_path / "fonts.lock.json").write_text(json.dumps(fake), encoding="utf-8")
    for name, body in bodies.items():
        (tmp_path / name).write_bytes(body)
    monkeypatch.setattr(fetch, "HERE", str(tmp_path))
    monkeypatch.setattr(fetch, "LOCK", str(tmp_path / "fonts.lock.json"))

    def no_network(*_a, **_k):
        raise AssertionError("--verify fetched")
    monkeypatch.setattr(fetch.urllib.request, "urlopen", no_network)
    assert fetch.main(["--verify"]) == 0
    first = sorted(bodies)[0]
    (tmp_path / first).write_bytes(b"moved")
    assert fetch.main(["--verify"]) == 1
    (tmp_path / first).unlink()
    assert fetch.main(["--verify"]) == 1


def _f8_lock_entries(text):
    """[(name, version, [sha256...])] from a hashed requirements file."""
    joined = re.sub(r"\\\n", " ", text.replace("\r\n", "\n"))
    entries = []
    for line in joined.split("\n"):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        head, *options = line.split()
        name, version = head.split("==")
        hashes = [o[len("--hash=sha256:"):] for o in options if o.startswith("--hash=sha256:")]
        assert len(hashes) == len(options), line
        entries.append((name, version, hashes))
    return entries


def _f8_norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _f8_wheel(directory, name, version):
    import zipfile
    path = directory / f"{name}-{version}-py3-none-any.whl"
    info = f"{name}-{version}.dist-info"
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr(f"{name}/__init__.py", "")
        wheel.writestr(f"{info}/METADATA", f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
        wheel.writestr(f"{info}/WHEEL", "Wheel-Version: 1.0\nGenerator: gate\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        wheel.writestr(f"{info}/RECORD", "")
    return path


def test_f8_the_python_packages_are_locked_by_content(tmp_path, capsys):
    """The image installs only requirements.lock, with --require-hashes and
    --only-binary=:all:; every locked package is pinned and carries exactly
    one SHA-256; every top-level pin of requirements.txt is in the lock at its
    version; the apt packages are read from apt.lock. And pip itself, on
    a wheel built here, installs a locked hash and REFUSES a changed one."""
    df = _f8_dockerfile()
    pips = re.findall(r"^RUN pip install (.*)$", df, re.M)
    assert len(pips) == 1, pips
    for flag in ("--require-hashes", "--only-binary=:all:", "-r requirements.lock"):
        assert flag in pips[0], flag
    assert "requirements.txt" not in pips[0]
    entries = _f8_lock_entries((API_DIR / "requirements.lock").read_text(encoding="utf-8"))
    names = [_f8_norm(n) for n, _v, _h in entries]
    assert len(names) == len(set(names))
    assert all(all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes) for _n, _v, hashes in entries)
    # Fix pass 10 (M-9): exactly ONE hash per package, the one wheel the
    # image's platform resolves, so no other file of the same version installs.
    plural = ["%s==%s carries %d hashes" % (n, v, len(h)) for n, v, h in entries if len(h) != 1]
    assert not plural, "requirements.lock must lock each package to one artifact: " + "; ".join(plural)
    locked = {_f8_norm(n): v for n, v, _h in entries}
    top = 0
    for line in (API_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            name, version = line.split("==")
            assert locked.get(_f8_norm(name.split("[")[0])) == version, line
            top += 1
    import apt_lock
    packages = ["%s=%s" % (p, v) for p, v, _a, _s in
                apt_lock.read_lock((API_DIR / "apt.lock").read_text(encoding="utf-8"))]

    wheel = _f8_wheel(tmp_path, "scrgateprobe", "1.0")
    good = sha256(wheel.read_bytes()).hexdigest()
    bad = good[:-1] + ("0" if good[-1] != "0" else "1")
    outcomes = {}
    for label, digest in (("locked", good), ("changed", bad)):
        req = tmp_path / f"{label}.lock"
        req.write_text(f"scrgateprobe==1.0 --hash=sha256:{digest}\n", encoding="utf-8")
        run = subprocess.run([sys.executable, "-m", "pip", "install", "--dry-run", "--no-index",
                              "--find-links", str(tmp_path), "--require-hashes",
                              "--only-binary=:all:", "--ignore-installed",
                              "--disable-pip-version-check", "--no-cache-dir", "-r", str(req)],
                             capture_output=True, text=True)
        outcomes[label] = (run.returncode, run.stdout + run.stderr)
    assert outcomes["locked"][0] == 0, outcomes["locked"][1]
    assert outcomes["changed"][0] != 0 and "DO NOT MATCH THE HASHES" in outcomes["changed"][1], (
        outcomes["changed"][1])
    with capsys.disabled():
        print("\nPROOF SIZE f8 lock: %d packages, %d wheel hashes, %d top-level pins matched; "
              "apt %s; pip installed the locked hash and refused a changed one"
              % (len(entries), sum(len(h) for _n, _v, h in entries), top, " ".join(packages)))


def test_f10_pip_refuses_a_second_artifact_of_a_locked_version(tmp_path, capsys):
    """One hash per version is what makes a same-version substitute refuse:
    two different wheel files of scrgateprobe 1.0 are built here, the lock
    names the first. pip, run with the image's flags, installs the first when
    it alone is offered and REFUSES when only the second is; offered both, it
    never installs the second (from a plain link directory pip learns a
    file's hash only after choosing it, so it may refuse there; an index that
    publishes hashes lets it filter to the locked file first)."""
    first_dir, second_dir, both_dir = (tmp_path / d for d in ("first", "second", "both"))
    for d in (first_dir, second_dir, both_dir):
        d.mkdir()
    first = _f8_wheel(first_dir, "scrgateprobe", "1.0")
    second = second_dir / "scrgateprobe-1.0-py2.py3-none-any.whl"
    import zipfile
    with zipfile.ZipFile(first) as src, zipfile.ZipFile(second, "w") as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item))
        dst.writestr("scrgateprobe/substitute.py", "SUBSTITUTE = True\n")
    for wheel in (first, second):
        (both_dir / wheel.name).write_bytes(wheel.read_bytes())
    digest = sha256(first.read_bytes()).hexdigest()
    assert digest != sha256(second.read_bytes()).hexdigest()
    req = tmp_path / "one.lock"
    req.write_text(f"scrgateprobe==1.0 --hash=sha256:{digest}\n", encoding="utf-8")
    outcomes = {}
    for label, links in (("first only", first_dir), ("both", both_dir), ("second only", second_dir)):
        report = tmp_path / ("report-%s.json" % label.replace(" ", "-"))
        run = subprocess.run([sys.executable, "-m", "pip", "install", "--dry-run", "--no-index",
                              "--find-links", str(links), "--require-hashes", "--only-binary=:all:",
                              "--ignore-installed", "--disable-pip-version-check", "--no-cache-dir",
                              "--report", str(report), "-r", str(req)],
                             capture_output=True, text=True)
        chosen = None
        if run.returncode == 0:
            chosen = json.loads(report.read_text(encoding="utf-8"))["install"][0]["download_info"]
            chosen = chosen["archive_info"]["hashes"]["sha256"]
        outcomes[label] = (run.returncode, chosen, run.stdout + run.stderr)
    assert outcomes["first only"][0] == 0 and outcomes["first only"][1] == digest, outcomes["first only"]
    assert outcomes["second only"][0] != 0, outcomes["second only"]
    assert outcomes["both"][1] in (None, digest), outcomes["both"]
    with capsys.disabled():
        print("\nPROOF SIZE f10 one artifact: pip installed the locked file alone (exit 0), refused "
              "the same-version substitute alone (exit %d), offered both: %s"
              % (outcomes["second only"][0],
                 "refused" if outcomes["both"][1] is None else "installed the locked file"))


def _f10_apt_served(monkeypatch, apt_lock, serve):
    """Replace apt_lock's one command runner: `apt-get download` writes the
    bytes `serve` maps the package to (a dict of file name -> bytes per
    package) into the work directory, as a scratch index would; dpkg and
    dpkg-query are recorded. Returns the call list."""
    calls = []

    def run(argv, cwd=None):
        calls.append(list(argv))
        if argv[:2] == ["apt-get", "download"]:
            package = argv[2].split("=", 1)[0]
            for name, data in serve.get(package, {}).items():
                (Path(cwd) / name).write_bytes(data)
            return ""
        if argv[:2] == ["dpkg", "-i"]:
            return ""
        if argv[0] == "dpkg-query":
            return serve["__query__"][argv[-1]]
        raise AssertionError(argv)

    monkeypatch.setattr(apt_lock, "_run", run)
    return calls


def test_f10_the_apt_packages_are_installed_from_locked_bytes(tmp_path, monkeypatch, capsys):
    """The Dockerfile installs apt packages only through apt_lock.py, from
    apt.lock (one line per package: version, architecture, the .deb's
    SHA-256), above the code copy, and never by `apt-get install`. Executed
    here with apt-get and dpkg replaced by a served directory: the locked
    bytes install and are recorded; the same version with ONE byte changed,
    an extra file, a missing file, and a malformed lock each refuse with
    dpkg never called and no record written."""
    df = _f8_dockerfile()
    assert not re.search(r"^RUN .*(apt-get|apt|dpkg) +(install|-i)\b", df, re.M), "a RUN line installs unlocked"
    runs =re.findall(r"^RUN .*apt_lock\.py.*$", df, re.M)
    assert runs == ["RUN apt-get update && python apt_lock.py install apt.lock /tmp/scr-apt "
                    "/var/lib/scr-build/apt-installed.lock && rm -rf /var/lib/apt/lists/* "
                    "/tmp/scr-apt"], runs
    copy_lock = re.search(r"^COPY apt\.lock apt_lock\.py \./\s*$", df, re.M)
    copy_all = re.search(r"^COPY \. \.\s*$", df, re.M)
    assert copy_lock and copy_lock.start() < df.index(runs[0]) < copy_all.start()
    import apt_lock
    entries = apt_lock.read_lock((API_DIR / "apt.lock").read_text(encoding="utf-8"))
    assert [e[0] for e in entries] == ["libfribidi0"], entries

    deb = b"!<arch>\ndebian-binary scr gate probe\n" * 40
    name = apt_lock.deb_name("scrprobe", "1:2.0-1", "amd64")
    assert name == "scrprobe_1%3a2.0-1_amd64.deb"
    lock = tmp_path / "apt.lock"
    lock.write_text("# probe\nscrprobe 1:2.0-1 amd64 %s\n" % sha256(deb).hexdigest(), encoding="utf-8")
    query = {"__query__": {"scrprobe": "1:2.0-1 amd64"}}
    changed = bytearray(deb)
    changed[len(changed) // 2] ^= 0x01
    cases = {
        "locked bytes": {"scrprobe": {name: deb}},
        "one byte changed": {"scrprobe": {name: bytes(changed)}},
        "an extra file": {"scrprobe": {name: deb, "libextra_1_amd64.deb": deb}},
        "nothing served": {"scrprobe": {}},
    }
    outcomes = {}
    for label, serve in cases.items():
        calls = _f10_apt_served(monkeypatch, apt_lock, dict(serve, **query))
        work, record = tmp_path / label / "work", tmp_path / label / "record"
        code = apt_lock.main(["install", str(lock), str(work), str(record)])
        dpkg = [c for c in calls if c[:2] == ["dpkg", "-i"]]
        outcomes[label] = (code, len(dpkg), record.exists())
        if label == "locked bytes":
            assert code == 0 and dpkg == [["dpkg", "-i", str(work / name)]], (code, calls)
            assert record.read_text(encoding="utf-8") == "scrprobe 1:2.0-1 amd64 %s\n" % sha256(deb).hexdigest()
            assert list(work.iterdir()) == []
        else:
            assert outcomes[label] == (1, 0, False), (label, outcomes[label], calls)
    bad_lock = tmp_path / "bad.lock"
    bad_lock.write_text("scrprobe 1:2.0-1 amd64 %s\n" % sha256(deb).hexdigest()[:63], encoding="utf-8")
    _f10_apt_served(monkeypatch, apt_lock, dict(cases["locked bytes"], **query))
    assert apt_lock.main(["install", str(bad_lock), str(tmp_path / "b" / "w"), str(tmp_path / "b" / "r")]) == 1
    with capsys.disabled():
        print("\nPROOF SIZE f10 apt: %d locked package(s) (%s); served directory: %s; malformed lock refused"
              % (len(entries), " ".join("%s=%s" % (e[0], e[1]) for e in entries),
                 "; ".join("%s -> exit %d, dpkg calls %d, record %s" % (k, v[0], v[1], v[2])
                           for k, v in outcomes.items())))


_F8_MANIFEST_FIXTURE = Path(__file__).with_name("fixtures") / "build_manifest" / "sample.json"


def test_f8_the_build_manifest_refuses_a_missing_part(capsys):
    """The manifest format, read from a fixture: a complete manifest is
    accepted and its health word is the SHA-256 of its bytes; a manifest
    missing ANY part, or whose list does not match its hash, or that is not
    JSON, is refused; no file is "absent". Since fix pass 10 the lists are
    artifact identities, and a manifest whose lists are self-consistent but
    whose identities are not the locks' (a substituted or unverified wheel, a
    missing or extra package, a .deb of other bytes or none) is refused, as is
    any manifest against a lock with two hashes for a package. Both /health
    arms carry the word, and the schema declares it without a default."""
    import build_manifest as bm
    raw = _F8_MANIFEST_FIXTURE.read_bytes()
    document = json.loads(raw)
    assert bm.problems(document) == []
    assert set(document) == set(bm.PARTS)
    assert bm.word_for(raw) == sha256(raw).hexdigest()
    assert bm.word_for(None) == "absent"
    refused = 0
    for part in bm.PARTS:
        partial = {k: v for k, v in document.items() if k != part}
        assert bm.problems(partial), part
        assert bm.word_for(json.dumps(partial).encode()) == "refused", part
        refused += 1
    def relisted(part, lines):
        """The fixture with `part` replaced and its list hash RECOMPUTED, so
        only the identity comparison with the locks can refuse it."""
        lines = sorted(lines)
        return dict(document, **{part: lines, part + "_sha256": bm.list_sha256(lines)})

    entries = _f8_lock_entries((API_DIR / "requirements.lock").read_text(encoding="utf-8"))
    pillow = next(h[0] for n, _v, h in entries if _f8_norm(n) == "pillow")
    fribidi = next(line for line in document["apt"] if line.startswith("libfribidi0="))
    tampered = [dict(document, apt=document["apt"] + ["zz=1:amd64 deb=base"]),
                dict(document, python=list(reversed(document["python"]))),
                dict(document, context_digest=document["context_digest"][:-1]),
                dict(document, format="scr-build-manifest/1"),
                dict(document, extra="x"),
                # Fix pass 10 (M-9): self-consistent lists whose identities
                # are not the locks'.
                relisted("python", [l.replace(pillow, "0" * 64) for l in document["python"]]),
                relisted("python", [l.replace("wheel=" + pillow, "wheel=base") for l in document["python"]]),
                relisted("python", [l for l in document["python"] if not l.startswith("pillow==")]),
                relisted("python", document["python"] + ["zzprobe==1.0 wheel=%s record=%s" % ("1" * 64, "2" * 64)]),
                relisted("apt", [l if l != fribidi else fribidi.rsplit("=", 1)[0] + "=" + "3" * 64
                                 for l in document["apt"]]),
                relisted("apt", [l if l != fribidi else fribidi.rsplit("=", 1)[0] + "=base"
                                 for l in document["apt"]]),
                relisted("apt", document["apt"] + ["zzprobe=1:amd64 deb=" + "4" * 64])]
    assert all(document["python"] != v["python"] or document["apt"] != v["apt"] for v in tampered[5:])
    for variant in tampered:
        assert bm.word_for(json.dumps(variant).encode()) == "refused", variant
    two = (API_DIR / "requirements.lock").read_text(encoding="utf-8").replace(
        "--hash=sha256:" + pillow, "--hash=sha256:%s \\\n    --hash=sha256:%s" % (pillow, "5" * 64))
    assert bm.problems(document, (two, (API_DIR / "apt.lock").read_text(encoding="utf-8"))), (
        "a lock with two hashes for one package must refuse the manifest")
    assert bm.word_for(b"{not json") == "refused"
    src = inspect.getsource(main.health_check)
    assert src.count("build_manifest=_build_manifest.health_word()") == 2
    import schemas
    assert schemas.HealthResponse.model_fields["build_manifest"].is_required()
    with capsys.disabled():
        print("\nPROOF SIZE f8 manifest: %d parts, each missing one refused; %d tampered "
              "manifests and one non-JSON file refused" % (refused, len(tampered)))


def _f10_wheel(directory, name, version, extra=None):
    """A wheel whose RECORD lists every file with its SHA-256, as a real
    wheel's does; `extra` adds files (a same-version substitute)."""
    import base64
    import zipfile
    info = f"{name}-{version}.dist-info"
    files = {f"{name}/__init__.py": b"PROBE = 1\n",
             f"{info}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode(),
             f"{info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: gate\nRoot-Is-Purelib: true\nTag: py3-none-any\n"}
    files.update(extra or {})
    rows = ["%s,sha256=%s,%d" % (p, base64.urlsafe_b64encode(sha256(d).digest()).rstrip(b"=").decode(), len(d))
            for p, d in sorted(files.items())] + [f"{info}/RECORD,,"]
    path = directory / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as wheel:
        for p, d in sorted(files.items()):
            wheel.writestr(p, d)
        wheel.writestr(f"{info}/RECORD", "\n".join(rows) + "\n")
    return path


def _f10_target_install(tmp_path, label, wheel, digest):
    """pip installs `wheel` into its own target directory with the image's
    flags and --report; returns (target, report)."""
    target, report = tmp_path / ("site-" + label), tmp_path / ("report-%s.json" % label)
    req = tmp_path / ("%s.lock" % label)
    req.write_text("scrgateprobe==1.0 --hash=sha256:%s\n" % digest, encoding="utf-8")
    run = subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", "--find-links",
                          str(wheel.parent), "--require-hashes", "--only-binary=:all:", "--no-deps",
                          "--disable-pip-version-check", "--no-cache-dir", "--no-compile",
                          "--target", str(target), "--report", str(report), "-r", str(req)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    return target, report


def test_f10_the_manifest_records_installed_artifact_identity(tmp_path, capsys):
    """build_manifest.collect over a REAL pip install: the python line of a
    package carries the SHA-256 of the archive pip verified (from its
    --report) and the digest of the RECORD pip wrote; the apt line carries
    the .deb SHA-256 apt_lock.py recorded. The locked artifact validates; a
    different, same-version wheel installed in its place changes the line and
    the manifest bytes AND is refused against the lock; an installed file
    changed after install refuses collection; a .deb record that is not the
    lock's refuses."""
    import build_manifest as bm
    df = _f8_dockerfile()
    pips = re.findall(r"^RUN pip install (.*)$", df, re.M)
    assert len(pips) == 1 and "--report %s " % bm.PIP_REPORT.as_posix() in pips[0], pips
    assert re.search(r"^RUN apt-get update && python apt_lock\.py install apt\.lock \S+ %s "
                     % re.escape(bm.APT_RECORD.as_posix()), df, re.M), "the apt record path differs"
    assert df.rstrip().splitlines()[-1].startswith("CMD ")
    assert re.search(r"^RUN python assets/fonts/fetch_fonts\.py --verify && python build_manifest\.py write$",
                     df, re.M), "the manifest is no longer written by the build's last RUN"
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = _f10_wheel(first_dir, "scrgateprobe", "1.0")
    second = _f10_wheel(second_dir, "scrgateprobe", "1.0", {"scrgateprobe/substitute.py": b"SUBSTITUTE = 1\n"})
    locked, other = sha256(first.read_bytes()).hexdigest(), sha256(second.read_bytes()).hexdigest()
    assert locked != other
    lock_text = "scrgateprobe==1.0 --hash=sha256:%s\n" % locked
    deb = "f" * 64
    apt_text = "libscrprobe 1.0-1 amd64 %s\n" % deb
    record = tmp_path / "apt-installed.lock"
    record.write_text("libscrprobe 1.0-1 amd64 %s\n" % deb, encoding="utf-8")
    dpkg = ["libc6=2.41-12:amd64", "libscrprobe=1.0-1:amd64"]
    documents = {}
    for label, wheel, digest in (("locked", first, locked), ("substitute", second, other)):
        target, report = _f10_target_install(tmp_path, label, wheel, digest)
        documents[label] = bm.collect(root=_F10_EMPTY_CONTEXT(tmp_path), site_paths=[target], report=report,
                                      dpkg=dpkg, record=record)
    good, bad = documents["locked"], documents["substitute"]
    line = next(l for l in good["python"] if l.startswith("scrgateprobe=="))
    assert line.startswith("scrgateprobe==1.0 wheel=%s record=" % locked), good["python"]
    assert good["apt"] == ["libc6=2.41-12:amd64 deb=base", "libscrprobe=1.0-1:amd64 deb=%s" % deb]
    assert bm.problems(good, (lock_text, apt_text)) == []
    assert bm.word_for(bm.encode(good), (lock_text, apt_text)) == sha256(bm.encode(good)).hexdigest()
    assert bad["python"] != good["python"] and bm.encode(bad) != bm.encode(good)
    found = bm.problems(bad, (lock_text, apt_text))
    assert found and "requirements.lock locks 1.0 to %s" % locked in found[0], found
    assert bm.word_for(bm.encode(bad), (lock_text, apt_text)) == "refused"
    # An installed file changed after install: RECORD verification refuses.
    target = tmp_path / "site-locked"
    (target / "scrgateprobe" / "__init__.py").write_text("CHANGED = True\n", encoding="utf-8")
    try:
        bm.python_lines([target], tmp_path / "report-locked.json")
        changed = None
    except bm.Refused as refusal:
        changed = str(refusal)
    assert changed and "does not match its RECORD" in changed, changed
    # A .deb record that is not the lock's.
    wrong = tmp_path / "apt-wrong.lock"
    wrong.write_text("libscrprobe 1.0-1 amd64 %s\n" % ("e" * 64), encoding="utf-8")
    other_apt = dict(good, apt=bm.apt_lines(dpkg, wrong))
    other_apt["apt_sha256"] = bm.list_sha256(other_apt["apt"])
    assert bm.problems(other_apt, (lock_text, apt_text)), other_apt["apt"]
    with capsys.disabled():
        print("\nPROOF SIZE f10 identity: locked wheel line %s accepted; same-version substitute "
              "refused (%s); changed installed file refused (%s); .deb record off the lock refused"
              % (line, found[0], changed))


def _F10_EMPTY_CONTEXT(tmp_path):
    """A minimal /app for collect's context digest (the identity parts are
    what this test reads)."""
    root = tmp_path / "app"
    (root / "assets" / "fonts").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "fonts" / "fonts.lock.json").write_text("{}", encoding="utf-8")
    return root


def test_f8_the_image_digests_its_context_as_the_gate_does(tmp_path, capsys):
    """build_manifest.py, run over a directory laid out as the image's /app
    (the context's members as committed, the fonts the build fetched, the
    manifest the build writes), computes the gate's digest of the context's
    members; any other file in that directory moves it."""
    import build_manifest as bm
    members = _context_only(_working_files())
    app = tmp_path / "app"
    for path, data in members:
        target = app / path[len(_CONTEXT) + 1:]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    lock = json.loads((app / "assets" / "fonts" / "fonts.lock.json").read_text(encoding="utf-8"))
    for name in lock:
        (app / "assets" / "fonts" / name).write_bytes(b"fetched by the build")
    (app / "build-manifest.json").write_bytes(b"{}")
    expected = _tree_digest(members)
    assert bm.context_digest(app) == expected
    (app / "stray.py").write_bytes(b"")
    assert bm.context_digest(app) != expected
    with capsys.disabled():
        print("\nPROOF SIZE f8 image context: %d files; build_manifest.context_digest == the "
              "gate's context digest %s" % (len(members), expected))
