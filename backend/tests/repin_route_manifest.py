"""Re-pin route fingerprints in route_manifest_net_seat.json from the GATE's own code path.

Learning #596: a previous re-pin tool computed a fingerprint a second way, the
manifest carried a value the gate never produces, and the gate failed closed on
a route nobody had touched. This tool calls `_route_identities` -- the function
`test_route_manifest_net_seat.py` compares against -- so tool and gate cannot
disagree by construction.

Usage (from anywhere; paths are resolved from this file):

    python backend/tests/repin_route_manifest.py           # dry run: lists moved routes
    python backend/tests/repin_route_manifest.py --write   # rewrite the manifest (LF kept)

"MOVED vs HEAD" compares the live tree against the manifest committed at git
HEAD, so the list is "what THIS working copy changed"; when git is unavailable
the comparison falls back to the manifest on disk. Never paste a hand-computed
sha into the manifest: run this, read the moved list, and check that every
moved route is one the batch actually touched (a route that moved for no
reason you can name is a finding, not a re-pin).
"""
import io
import json
import subprocess
import sys
from pathlib import Path

import fastapi

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
MANIFEST = BACKEND / "tests" / "route_manifest_net_seat.json"
MANIFEST_REL = "backend/tests/route_manifest_net_seat.json"

for p in (BACKEND / "tests", BACKEND / "api", BACKEND):
    sys.path.insert(0, str(p))
import test_route_manifest_net_seat as gate  # noqa: E402  (imports main.app)


def rows(doc):
    out = {}
    for group in doc["groups"]:
        for r in group["routes"]:
            if len(r) > 4:
                out[(r[0], tuple(r[1]), r[2], r[3])] = r[4]
    return out


def head_manifest():
    try:
        txt = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:{MANIFEST_REL}"],
                             capture_output=True, text=True, check=True).stdout
        return rows(json.loads(txt)), "HEAD"
    except Exception:
        return None, "disk"


def main():
    # the gate refuses to enumerate routes under any other FastAPI; a manifest
    # written under a different one would be rejected on the next run
    if fastapi.__version__ != gate.PINNED_FASTAPI:
        print("REFUSING: the gate pins fastapi==%s; installed %s"
              % (gate.PINNED_FASTAPI, fastapi.__version__))
        return 1
    live = {(e["path"], tuple(e["methods"]), e["module"], e["qualname"]): e["source_sha1"]
            for e in gate._route_identities(gate.main.app.routes)}
    raw = io.open(MANIFEST, "r", encoding="utf-8", newline="").read()
    doc = json.loads(raw)
    baseline, baseline_name = head_manifest()
    if baseline is None:
        baseline = rows(doc)

    missing = [k for k in rows(doc) if k not in live]
    if missing:
        print("REFUSING: %d manifest rows have no live route" % len(missing))
        for k in missing[:5]:
            print("   ", k)
        return 1

    moved, written = [], 0
    for group in doc["groups"]:
        for r in group["routes"]:
            if len(r) <= 4:
                continue
            k = (r[0], tuple(r[1]), r[2], r[3])
            if baseline.get(k) != live[k]:
                moved.append((r[2] + "." + r[3], baseline.get(k), live[k]))
            if r[4] != live[k]:
                r[4] = live[k]
                written += 1

    print("manifest rows      : %d" % sum(len(g["routes"]) for g in doc["groups"]))
    print("fingerprinted      : %d" % len(rows(doc)))
    print("rows rewritten now : %d" % written)
    print("MOVED vs %-9s : %d" % (baseline_name, len(moved)))
    for name, old, new in sorted(moved):
        print("   %-42s %s -> %s" % (name, (old or "none")[:8], new[:8]))

    if "--write" in sys.argv:
        out = json.dumps(doc, indent=2) + "\n"
        io.open(MANIFEST, "w", encoding="utf-8", newline="").write(out)
        print("written (LF preserved)")
    else:
        print("(dry run; pass --write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
