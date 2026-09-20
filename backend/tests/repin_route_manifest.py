"""Re-pin the fingerprints in route_manifest_net_seat.json from the GATE's own code path.

All THREE families: the route rows, the `entry_points` section (middleware,
exception handlers, the lifespan) and `route_order`. The entry-point section
was outside this tool until it was brought in, so the only way to move an
entry-point sha was to paste one in by hand -- the exact thing the route half
refuses to do, on a set whose whole point is that a request path outside the
routing table is still a reviewed surface.

`route_order` was the last one left outside, and it was outside SILENTLY: the
tool reported "rows rewritten" and exited 0 while the gate stayed red, because
registration order is the one family this tool never touched. Adding a route
moves it by construction, so every route added since that section landed has
had to be hand-pasted -- the thing the other two halves refuse. It is re-pinned
here from `gate._route_registration_order()`, the same function
`test_the_manifest_records_the_order_requests_are_matched_in` compares against,
so tool and gate cannot disagree by construction (#596).

Re-pinning order is NOT the same as approving it. Starlette matches in
registration order and first match wins, so a route that changed POSITION may
have changed which handler answers a request. The tool prints every insertion,
removal and move so that question is put in front of whoever runs it; what it
refuses to do is let the answer be typed in by hand.

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


def entry_rows(doc):
    """{(module, name, section): sha} out of a manifest document."""
    out = {}
    for section, rows_ in (doc.get("entry_points") or {}).items():
        for module, name, sha in rows_:
            out[(module, name, section)] = sha
    return out


def head_manifest():
    """The manifest at HEAD, as (route rows, entry-point rows).

    BOTH halves: the baseline is what "MOVED vs HEAD" is measured against, and
    a baseline that covered only the routes reported every entry point as
    unmoved — including one the author had just re-pinned, which is exactly
    the case a reviewer runs this to catch."""
    try:
        txt = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:{MANIFEST_REL}"],
                             capture_output=True, text=True, check=True).stdout
        head = json.loads(txt)
        return (rows(head), entry_rows(head)), "HEAD"
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
        baseline = (rows(doc), entry_rows(doc))
    baseline, entry_baseline = baseline

    missing = [k for k in rows(doc) if k not in live]
    if missing:
        print("REFUSING: %d manifest rows have no live route" % len(missing))
        for k in missing[:5]:
            print("   ", k)
        return 1

    moved, written, seeded = [], 0, []
    for group in doc["groups"]:
        for r in group["routes"]:
            if len(r) <= 4:
                # A four-element row carries no fingerprint. For the
                # sentinel-exercised route that is correct and permanent --
                # it is checked by being RUN with all 50 sentinels, not by its
                # source. For a statically-nonconsumer row it means a route
                # was just added to the manifest and its sha has not been
                # taken yet, so take it HERE rather than letting someone paste
                # one in: the classification and the reason are the human's
                # call, the sha never is (#596). Reported separately from
                # `moved`, because a first fingerprint is not a drift.
                if group.get("classification") != "statically-nonconsumer":
                    continue
                k = (r[0], tuple(r[1]), r[2], r[3])
                if k not in live:
                    continue
                r.append(live[k])
                seeded.append(r[2] + "." + r[3])
                written += 1
                continue
            k = (r[0], tuple(r[1]), r[2], r[3])
            if baseline.get(k) != live[k]:
                moved.append((r[2] + "." + r[3], baseline.get(k), live[k]))
            if r[4] != live[k]:
                r[4] = live[k]
                written += 1

    # ── the entry points: same seam, same rule ──────────────────────────
    # `_entry_point_sha` is the function the gate asserts against, so this
    # cannot compute the value a second way (#596). The identity SET is not
    # re-pinned: a middleware or handler appearing or leaving is a review item,
    # and answering it by rewriting the manifest is how the gate stops meaning
    # anything.
    live_eps = gate._entry_point_sections()
    eps = doc["entry_points"]
    if sorted(eps) != sorted(live_eps):
        print("REFUSING: entry-point sections %s vs live %s" % (sorted(eps), sorted(live_eps)))
        return 1
    ep_moved = []
    for section, rows_ in eps.items():
        recorded = [(m, n) for m, n, _ in rows_]
        if recorded != live_eps[section]:
            print("REFUSING: %s identities changed: manifest %s vs live %s"
                  % (section, recorded, live_eps[section]))
            return 1
        for row in rows_:
            now = gate._entry_point_sha(row[0], row[1])
            was = entry_baseline.get((row[0], row[1], section))
            if was != now:
                ep_moved.append((row[0] + "." + row[1], was, now))
            if row[2] != now:
                row[2] = now
                written += 1

    # ── registration order: the third family ────────────────────────────
    # Read from the gate's own `_route_registration_order`, never rebuilt
    # here. Starlette matches in this order and first match wins, so the
    # DIFFERENCE is printed rather than quietly absorbed: a route that only
    # moved position is the case where the manifest looks unchanged and the
    # handler that answers a request is not the one that used to.
    live_order = gate._route_registration_order()
    recorded_order = doc.get("route_order") or []
    order_added = [s for s in live_order if s not in recorded_order]
    order_gone = [s for s in recorded_order if s not in live_order]
    kept_live = [s for s in live_order if s in recorded_order]
    kept_recorded = [s for s in recorded_order if s in live_order]
    order_reshuffled = kept_live != kept_recorded
    if live_order != recorded_order:
        doc["route_order"] = live_order
        written += 1

    print("manifest rows      : %d" % sum(len(g["routes"]) for g in doc["groups"]))
    print("fingerprinted      : %d" % len(rows(doc)))
    print("rows rewritten now : %d" % written)
    print("MOVED vs %-9s : %d" % (baseline_name, len(moved)))
    for name, old, new in sorted(moved):
        print("   %-42s %s -> %s" % (name, (old or "none")[:8], new[:8]))
    print("ENTRY POINTS moved vs %-4s: %d" % (baseline_name, len(ep_moved)))
    for name, old, new in sorted(ep_moved):
        print("   %-42s %s -> %s" % (name, (old or "none")[:8], new[:8]))
    if seeded:
        print("FIRST fingerprint taken for %d newly-manifested route(s):" % len(seeded))
        for name in sorted(seeded):
            print("   * %s" % name)
    print("ROUTE ORDER        : %d recorded -> %d live (+%d/-%d)%s"
          % (len(recorded_order), len(live_order), len(order_added),
             len(order_gone), ", RESHUFFLED" if order_reshuffled else ""))
    for s in order_added:
        print("   + %s" % s)
    for s in order_gone:
        print("   - %s" % s)
    if order_reshuffled:
        # Said loudly and separately from the +/- list: an insertion is
        # expected when a batch adds a route, a RESHUFFLE of routes that were
        # already there is the case where first-match-wins may now pick a
        # different handler for the same request.
        print("   !! routes that already existed changed position; confirm the "
              "route that answers each path is still the one that used to")

    if "--write" in sys.argv:
        out = json.dumps(doc, indent=2) + "\n"
        io.open(MANIFEST, "w", encoding="utf-8", newline="").write(out)
        print("written (LF preserved)")
    else:
        print("(dry run; pass --write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
