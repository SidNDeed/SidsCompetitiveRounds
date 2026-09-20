"""THE COUNT: how many route fingerprints this branch re-pins against a base.

Round 2 of bug 392 answered "four or five?" with a number produced by a script
that lived outside the worktree. The number was right -- it is reproducible
from the manifest by hand -- but the tool that produced it shipped nowhere, so
the row closed on evidence no later reader could re-run. A control whose only
witness is the authoring session is not a control (#391). This file is that
script, in the tree, with its own self-test.

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

Exit codes: 0 the diff was taken, 1 the base could not be read, 2 the self-test
failed.
"""
from __future__ import annotations

import argparse
import io
import json
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

    print(f"base            : {args.base}")
    print(f"manifest        : {MANIFEST_REL}")
    print(f"THE COUNT       : {len(d['moved'])} route fingerprints re-pinned")
    print(f"routes added    : {len(d['added'])}")
    print(f"routes removed  : {len(d['removed'])}")
    print(f"entry points    : {len(d['entry_moved'])} moved, "
          f"{len(d['entry_added'])} added, {len(d['entry_removed'])} removed")
    if args.names:
        for k in d["moved"]:
            print(f"  re-pinned: {k[2]}.{k[3]}  {'/'.join(k[1])} {k[0]}")
        for label, key in (("added", "added"), ("removed", "removed")):
            for k in d[key]:
                print(f"  {label}: {k[2]}.{k[3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
