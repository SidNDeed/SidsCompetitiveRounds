"""Re-pin the fingerprints in route_manifest_net_seat.json from the GATE's own code path.

Both families: the route rows AND the `entry_points` section (middleware,
exception handlers, the lifespan). The section was outside this tool until now,
so the only way to move an entry-point sha was to paste one in by hand -- the
exact thing the route half refuses to do, on a set whose whole point is that a
request path outside the routing table is still a reviewed surface.

Learning #596: a previous re-pin tool computed a fingerprint a second way, the
manifest carried a value the gate never produces, and the gate failed closed on
a route nobody had touched. This tool calls `_route_identities` -- the function
`test_route_manifest_net_seat.py` compares against -- so tool and gate cannot
disagree by construction.

WHAT A WRITE REFUSES, AND WHAT IT SAYS BEFORE IT WRITES. Each of these is a
refusal this tool implements, checked before the file is touched; a refusal
writes nothing at all, not the rows that happened to pass:

  * CLASSIFICATION. A moved ROUTE is re-pinned only when its group is
    classified `statically-nonconsumer` -- a route whose output a static source
    review has cleared. Any other class (a route exercised with sentinels, or
    one no review has cleared) needs that review again, and a new digest is
    not a substitute for it. Entry points carry no classification and are
    re-pinned under the identity-set rule below.
  * DIGEST UNIQUENESS. The file is edited as TEXT, one digest at a time, so
    the document is not re-serialized around the change: every old digest
    being replaced must occur exactly ONCE in the file, and every new digest
    must occur NOWHERE in it yet. Either failing means a textual replacement
    could touch a line it was not aimed at, and the write is refused. After the
    replacement the file is parsed again and must equal, value for value, the
    document with exactly the intended fingerprints changed.
  * THE TRANSCRIPT PRECEDES THE WRITE. One `BEFORE WRITE` line per row --
    kind, name, classification, old and new digest, both occurrence counts and
    the decision -- is printed (and, with --transcript PATH, appended to that
    file) BEFORE the file is opened for writing, followed by one `WROTE` line
    per row after it. A reader can therefore check that every digest that
    changed was explained before it changed.

The identity SET is never re-pinned: a route or an entry point appearing or
leaving is a review item, and answering it by rewriting the manifest is how
the gate stops meaning anything.

Usage (from anywhere; paths are resolved from this file):

    python backend/tests/repin_route_manifest.py                  # dry run
    python backend/tests/repin_route_manifest.py --write          # rewrite the manifest
    python backend/tests/repin_route_manifest.py --write --transcript T.log

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

# The one classification under which a moved route may be re-pinned here.
REPINNABLE_CLASS = "statically-nonconsumer"

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


def _opt(name):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


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

    # (kind, name, classification, old digest, new digest) for every row whose
    # recorded digest differs from the live one -- the rows a write changes.
    plan = []
    moved = []
    for group in doc["groups"]:
        cls = group.get("classification")
        for r in group["routes"]:
            if len(r) <= 4:
                continue
            k = (r[0], tuple(r[1]), r[2], r[3])
            if baseline.get(k) != live[k]:
                moved.append((r[2] + "." + r[3], baseline.get(k), live[k]))
            if r[4] != live[k]:
                plan.append(("route", "%s %s %s.%s" % (",".join(r[1]), r[0], r[2], r[3]),
                             cls, r[4], live[k]))
                r[4] = live[k]

    # ── the entry points: same seam, same rule ──────────────────────────
    # `_entry_point_sha` is the function the gate asserts against, so this
    # cannot compute the value a second way (#596).
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
                plan.append(("entry point", "%s %s.%s" % (section, row[0], row[1]),
                             None, row[2], now))
                row[2] = now

    print("manifest rows      : %d" % sum(len(g["routes"]) for g in doc["groups"]))
    print("fingerprinted      : %d" % len(rows(doc)))
    print("rows to rewrite    : %d" % len(plan))
    print("MOVED vs %-9s : %d" % (baseline_name, len(moved)))
    for name, old, new in sorted(moved):
        print("   %-42s %s -> %s" % (name, (old or "none")[:8], new[:8]))
    print("ENTRY POINTS moved vs %-4s: %d" % (baseline_name, len(ep_moved)))
    for name, old, new in sorted(ep_moved):
        print("   %-42s %s -> %s" % (name, (old or "none")[:8], new[:8]))

    # ── the refusals, all decided before anything is written ─────────────
    refusals = []
    decisions = []
    for kind, name, cls, old, new in plan:
        n_old, n_new = raw.count(old), raw.count(new)
        why = []
        if kind == "route" and cls != REPINNABLE_CLASS:
            why.append("classification %r is not %r" % (cls, REPINNABLE_CLASS))
        if n_old != 1:
            why.append("the old digest occurs %d times in the file, not once" % n_old)
        if n_new != 0:
            why.append("the new digest already occurs %d time(s) in the file" % n_new)
        decisions.append((kind, name, cls, old, new, n_old, n_new, why))
        if why:
            refusals.append((name, why))

    write = "--write" in sys.argv
    tpath = _opt("--transcript")
    lines = []
    for kind, name, cls, old, new, n_old, n_new, why in decisions:
        lines.append("BEFORE WRITE: %s %s | classification=%s | old=%s new=%s | "
                     "old-digest occurrences=%d new-digest occurrences=%d | %s"
                     % (kind, name, cls if cls is not None else "(entry point: none)",
                        old, new, n_old, n_new,
                        ("REFUSE: " + "; ".join(why)) if why
                        else ("WRITE" if write else "WOULD WRITE (dry run)")))
    for ln in lines:
        print(ln)
    if tpath and lines:
        with io.open(tpath, "a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")

    if refusals:
        print("REFUSING: %d row(s) cannot be re-pinned; nothing was written"
              % len(refusals))
        for name, why in refusals:
            print("   %s -- %s" % (name, "; ".join(why)))
        return 1

    if not write:
        print("(dry run; pass --write)")
        return 0

    # The textual edit: each old digest (unique) becomes its new one (absent).
    out = raw
    for kind, name, cls, old, new, n_old, n_new, why in decisions:
        out = out.replace(old, new)
    if json.loads(out) != doc:
        print("REFUSING: the edited text does not parse to the intended "
              "document; nothing was written")
        return 1
    io.open(MANIFEST, "w", encoding="utf-8", newline="").write(out)
    done = []
    for kind, name, cls, old, new, n_old, n_new, why in decisions:
        done.append("WROTE: %s %s | old=%s new=%s" % (kind, name, old, new))
    for ln in done:
        print(ln)
    if tpath and done:
        with io.open(tpath, "a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(done) + "\n")
    print("written: %d digest(s) replaced in place, nothing else in the file "
          "moved" % len(done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
