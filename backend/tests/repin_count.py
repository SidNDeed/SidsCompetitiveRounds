"""THE COUNT: how many route handlers this branch edits, against a base.

Round 2 of bug 392 answered "four or five?" with a number produced by a script
that lived outside the worktree. The number was right -- it is reproducible
from the manifest by hand -- but the tool that produced it shipped nowhere, so
the row closed on evidence no later reader could re-run. A control whose only
witness is the authoring session is not a control (#391). This file is that
script, in the tree, with its own self-test.

WHAT THE COUNT COUNTS, AND WHY IT MOVED
  Round 2's five was a count of MOVED FINGERPRINTS, and it was presented as the
  exact set of handlers the range edits. Those are not the same question. The
  manifest holds one group of routes that carry NO fingerprint at all -- they
  are classified as exercised by an executed sentinel test instead -- and this
  range edits one of them. A fingerprint diff cannot see it, by construction,
  and never could: the row could not have failed however wrong it was (#342).

  So the count is derived from the TREE and not from the manifest alone: the
  lines this range changes, mapped to the function that encloses them, matched
  against the manifest's handlers. The fingerprint diff is still reported --
  beside it, as the answer to its own smaller question -- and any edited
  handler that carries a fingerprint and was NOT re-pinned is a failure.

What it does NOT do: compute a fingerprint. It reads the fingerprints already
STORED in two copies of the manifest -- the one committed at a base ref and the
one on disk -- and diffs them. `repin_route_manifest.py` remains the only thing
that computes a fingerprint, and the gate remains the only thing that checks
one, so #596 (a second implementation quietly disagreeing with the gate) has no
surface here.

Usage (paths are resolved from this file, so it runs from anywhere):

    python backend/tests/repin_count.py --base <ref>
    python backend/tests/repin_count.py --base <ref> --names
    python backend/tests/repin_count.py --self-test

Exit codes: 0 the derivation was taken and every edited handler is accounted
for, 1 the base could not be read or a fingerprinted handler this range edits
was not re-pinned, 2 the self-test failed.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
MANIFEST = BACKEND / "tests" / "route_manifest_net_seat.json"
MANIFEST_REL = "backend/tests/route_manifest_net_seat.json"


def route_rows(doc: dict) -> dict:
    """{(path, methods, module, qualname): stored fingerprint}.

    Rows shorter than five elements carry no fingerprint and are skipped --
    the same shape `repin_route_manifest.rows` reads, kept to a plain JSON walk
    here so that counting cannot drag in the application import.
    """
    out = {}
    for group in doc.get("groups", []):
        for r in group.get("routes", []):
            if len(r) > 4:
                out[(r[0], tuple(r[1]), r[2], r[3])] = r[4]
    return out


def entry_rows(doc: dict) -> dict:
    """{(module, name, section): stored fingerprint}."""
    out = {}
    for section, rows in (doc.get("entry_points") or {}).items():
        for module, name, sha in rows:
            out[(module, name, section)] = sha
    return out


def diff(base_doc: dict, live_doc: dict) -> dict:
    """The three numbers that answer three different questions.

    They are reported separately on purpose. "Five" is only meaningful beside
    "no route entered or left the manifest" and "no entry point moved": a
    fingerprint count on its own cannot distinguish a re-pin from a route that
    was added and a route that was dropped.
    """
    base, live = route_rows(base_doc), route_rows(live_doc)
    moved = sorted(k for k in base.keys() & live.keys() if base[k] != live[k])
    ebase, elive = entry_rows(base_doc), entry_rows(live_doc)
    return {
        "moved": moved,
        "added": sorted(live.keys() - base.keys()),
        "removed": sorted(base.keys() - live.keys()),
        "entry_moved": sorted(k for k in ebase.keys() & elive.keys()
                              if ebase[k] != elive[k]),
        "entry_added": sorted(elive.keys() - ebase.keys()),
        "entry_removed": sorted(ebase.keys() - elive.keys()),
    }


def at_ref(ref: str) -> dict:
    txt = subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:{MANIFEST_REL}"],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(txt)


# ── the tree side: which functions this range actually edits ──────────────
# Handler-bearing modules. The bot is here so the report can say what it
# edited OUTSIDE the routing table too: a count that silently dropped the
# lines it could not classify would be a filter discarding what it measures
# (#441).
SOURCES = ("backend/api/main.py", "backend/discord_bot.py")

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines(base: str, rel: str) -> set[int]:
    """New-side line numbers this range changes in one file.

    `--unified=0` so the ranges are the changed lines and not their context,
    and the diff is read as BYTES and decoded here: the seat's locale codec
    cannot decode the UTF-8 these files carry, and a pass that dies in the
    codec reports nothing at all rather than reporting less.
    """
    proc = subprocess.run(
        ["git", "-C", str(REPO), "diff", "--unified=0", base, "--", rel],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode, "git diff", stderr=proc.stderr.decode("utf-8", "replace"))
    out: set[int] = set()
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        m = _HUNK.match(line)
        if not m:
            continue
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        out.update(range(start, start + count))
    return out


def def_spans(text: str) -> list[tuple[str, int, int]]:
    """[(qualname, first line, last line)] for every def and class in a module.

    Innermost-last is not assumed; the caller picks the narrowest span that
    contains a line, so a nested helper is attributed to itself and a line in
    the enclosing body to the enclosing function.
    """
    spans: list[tuple[str, int, int]] = []

    def walk(node, prefix: str):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                spans.append((name, start, child.end_lineno or child.lineno))
                walk(child, name + ".")
            else:
                walk(child, prefix)

    walk(ast.parse(text), "")
    return spans


def functions_touching(spans: list[tuple[str, int, int]], lines: set[int]) -> set[str]:
    """The narrowest enclosing def for each changed line. Unenclosed lines drop."""
    out: set[str] = set()
    for n in lines:
        best = None
        for name, start, end in spans:
            if start <= n <= end and (best is None or (end - start) < (best[2] - best[1])):
                best = (name, start, end)
        if best is not None:
            out.add(best[0])
    return out


def edited_functions(base: str) -> dict[str, set[str]]:
    """{module path: {qualname edited}} across the handler-bearing modules."""
    out: dict[str, set[str]] = {}
    for rel in SOURCES:
        lines = changed_lines(base, rel)
        if not lines:
            out[rel] = set()
            continue
        text = (REPO / rel).read_text(encoding="utf-8")
        out[rel] = functions_touching(def_spans(text), lines)
    return out


def manifest_handlers(doc: dict) -> dict[str, dict]:
    """{qualname: {path, methods, fingerprinted, classification}} for every route.

    Every group, including the ones whose rows carry no fingerprint. Reading
    only the fingerprinted rows is what made an edited handler invisible.
    """
    out: dict[str, dict] = {}
    for group in doc.get("groups", []):
        classification = group.get("classification")
        for r in group.get("routes", []):
            out[r[3]] = {"path": r[0], "methods": tuple(r[1]),
                         "fingerprinted": len(r) > 4,
                         "classification": classification}
    return out


def _self_test() -> int:
    """Plant each shape the diff must separate and require it to be separated.

    A counter that reports every difference as "moved" would have answered
    round 2's question with the same five and been wrong for a reason nobody
    could see (#342).
    """
    def doc(rows, entries=()):
        return {"groups": [{"routes": [list(r) for r in rows]}],
                "entry_points": {"middleware": [list(e) for e in entries]}}

    base = doc([("/a", ["GET"], "main", "a", "sha-a"),
                ("/b", ["GET"], "main", "b", "sha-b"),
                ("/gone", ["GET"], "main", "gone", "sha-g")],
               [("main", "mw", "sha-m")])
    live = doc([("/a", ["GET"], "main", "a", "sha-a-MOVED"),
                ("/b", ["GET"], "main", "b", "sha-b"),
                ("/new", ["GET"], "main", "new", "sha-n")],
               [("main", "mw", "sha-m-MOVED")])
    d = diff(base, live)
    checks = {
        "one fingerprint moved": len(d["moved"]) == 1,
        "the moved one is /a": d["moved"] and d["moved"][0][0] == "/a",
        "an added route is not counted as moved": [k[0] for k in d["added"]] == ["/new"],
        "a removed route is not counted as moved": [k[0] for k in d["removed"]] == ["/gone"],
        "an unchanged route is not counted": all(k[0] != "/b" for k in d["moved"]),
        "an entry-point move is reported apart": len(d["entry_moved"]) == 1,
    }
    # a document identical to itself must produce nothing at all: the other
    # direction of #342
    same = diff(base, base)
    checks["identical manifests report nothing"] = not any(same.values())

    # ── the tree side ────────────────────────────────────────────────────
    module = "\n".join([
        "import os",                       # 1
        "",                                # 2
        "async def alpha():",              # 3
        "    x = 1",                       # 4
        "    return x",                    # 5
        "",                                # 6
        "TOP_LEVEL = 2",                   # 7
        "",                                # 8
        "def beta():",                     # 9
        "    def inner():",                # 10
        "        return 3",                # 11
        "    return inner()",              # 12
    ])
    spans = def_spans(module)
    names = {n for n, _s, _e in spans}
    checks["every def is found, nested ones included"] = names == {
        "alpha", "beta", "beta.inner"}
    checks["a line inside a handler names that handler"] = \
        functions_touching(spans, {4}) == {"alpha"}
    checks["a line in a nested def names the NESTED one"] = \
        functions_touching(spans, {11}) == {"beta.inner"}
    checks["a line in the enclosing body names the enclosing def"] = \
        functions_touching(spans, {12}) == {"beta"}
    checks["a module-level line names no function"] = \
        functions_touching(spans, {7}) == set()
    checks["a decorator line counts as part of its def"] = \
        functions_touching(def_spans("@dec\ndef gamma():\n    pass"), {1}) == {"gamma"}

    # ── the manifest side: a row with no fingerprint is still a handler ──
    doc_mixed = {"groups": [
        {"routes": [["/a", ["GET"], "main", "a", "sha-a"]]},
        {"classification": "sentinel-exercised",
         "routes": [["/s", ["GET"], "main", "sentinel"]]}]}
    handlers = manifest_handlers(doc_mixed)
    checks["a route carrying no fingerprint is still a handler"] = \
        set(handlers) == {"a", "sentinel"}
    checks["and it is marked as carrying no fingerprint"] = \
        handlers["sentinel"]["fingerprinted"] is False \
        and handlers["sentinel"]["classification"] == "sentinel-exercised"
    checks["a fingerprint diff cannot see the sentinel route"] = \
        "sentinel" not in {k[3] for k in route_rows(doc_mixed)}

    # ── hunk parsing ─────────────────────────────────────────────────────
    checks["a one-line hunk header parses to one line"] = \
        _HUNK.match("@@ -10 +12 @@").groups() == ("12", None)
    checks["a counted hunk header parses to its span"] = \
        _HUNK.match("@@ -10,3 +12,4 @@ async def x():").groups() == ("12", "4")

    bad = [k for k, ok in checks.items() if not ok]
    for k, ok in checks.items():
        print(("  ok   " if ok else "  FAIL ") + k)
    print("SELF-TEST:", "all shapes separated" if not bad else f"FAILED: {bad}")
    return 2 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", help="git ref whose manifest is the baseline")
    ap.add_argument("--names", action="store_true", help="print module.qualname per row")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if not args.base:
        ap.error("--base is required unless --self-test is given")

    try:
        base_doc = at_ref(args.base)
    except subprocess.CalledProcessError as exc:
        print(f"REFUSING: cannot read {MANIFEST_REL} at {args.base}: "
              f"{(exc.stderr or '').strip()}")
        return 1
    live_doc = json.loads(io.open(MANIFEST, "r", encoding="utf-8", newline="").read())
    d = diff(base_doc, live_doc)

    try:
        touched = edited_functions(args.base)
    except subprocess.CalledProcessError as exc:
        print(f"REFUSING: cannot diff against {args.base}: {(exc.stderr or '').strip()}")
        return 1
    handlers = manifest_handlers(live_doc)
    repinned = {k[3] for k in d["moved"]}

    edited_handlers, other_functions = {}, {}
    for rel, names in touched.items():
        for name in sorted(names):
            if rel == "backend/api/main.py" and name in handlers:
                edited_handlers[name] = handlers[name]
            else:
                other_functions.setdefault(rel, []).append(name)

    unrepinned = sorted(n for n, h in edited_handlers.items()
                        if h["fingerprinted"] and n not in repinned)
    no_fingerprint = sorted(n for n, h in edited_handlers.items() if not h["fingerprinted"])
    stray = sorted(repinned - set(edited_handlers))

    print(f"base            : {args.base}")
    print(f"manifest        : {MANIFEST_REL}")
    print(f"THE COUNT       : {len(edited_handlers)} route handlers edited by this range")
    print(f"  of those, fingerprinted and re-pinned : "
          f"{len(edited_handlers) - len(no_fingerprint) - len(unrepinned)}")
    print(f"  of those, fingerprinted and NOT re-pinned: {len(unrepinned)}")
    print(f"  of those, carrying no fingerprint     : {len(no_fingerprint)}")
    print(f"fingerprints moved: {len(d['moved'])}")
    print(f"routes added    : {len(d['added'])}")
    print(f"routes removed  : {len(d['removed'])}")
    print(f"entry points    : {len(d['entry_moved'])} moved, "
          f"{len(d['entry_added'])} added, {len(d['entry_removed'])} removed")
    if args.names:
        for name in sorted(edited_handlers):
            h = edited_handlers[name]
            state = ("re-pinned" if name in repinned else
                     f"NO FINGERPRINT ({h['classification']})" if not h["fingerprinted"]
                     else "FINGERPRINTED BUT NOT RE-PINNED")
            # ASCII only in this listing: it is read back out of a redirected
            # log, and a decorative character that the console code page
            # cannot render turns evidence into a replacement glyph.
            print(f"  edited handler: main.{name}  {'/'.join(h['methods'])} "
                  f"{h['path']}  -- {state}")
        for k in d["moved"]:
            if k[3] not in edited_handlers:
                print(f"  re-pinned but not edited here: {k[2]}.{k[3]}  "
                      f"{'/'.join(k[1])} {k[0]}")
        for rel in sorted(other_functions):
            for name in other_functions[rel]:
                print(f"  edited, outside the routing table: {rel}::{name}")
        for label, key in (("added", "added"), ("removed", "removed")):
            for k in d[key]:
                print(f"  {label}: {k[2]}.{k[3]}")
    for name in unrepinned:
        print(f"UNPINNED: main.{name} carries a fingerprint and this range edits it")
    for name in stray:
        print(f"UNEXPLAINED: main.{name} was re-pinned but this range does not edit it")
    bad = unrepinned + stray
    print("VERDICT:", "every edited handler is accounted for" if not bad
          else f"{len(bad)} handlers unaccounted for")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
