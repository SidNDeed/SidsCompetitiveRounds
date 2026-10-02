"""The private-needle check for anything that leaves the seat.

The review rules revisions live in a private store outside every repository.
This tool derives NEEDLES from that store -- strings that exist only there
and whose presence anywhere else means private material leaked -- and checks
a commit range, the staged index, a message, a directory or a packet for
them. It reports the class and the count of what it found, never the text.

Needle classes, derived on every run from the store named by the
environment variable SCR_REVIEW_PRIVATE_STORE:
  rule_id   every rule id of every revision in the store
  nonce     every revision's nonce
  wording   every rule's wording as the ordered sequence of its literal
            fragments (placeholders are gaps), so the template and every line
            rendered from it match, and one common phrase alone does not
  listed    every line of the store's tests/needles.txt (identifiers the
            store's owner lists by hand)
  basename  the names of the store's own private files (not its revision
            directories: a revision id is public, the health word says it)

Modes:
  staged   <repo>                   added lines and staged blobs, staged paths
  range    <repo> <base> <tip>      every commit of base..tip: its message and
                                    identities, every blob it adds or changes,
                                    every path it touches
  message  <file>                   one commit message
  scan-dir <dir>                    every file under a directory
  packet   <repo> <commit> <allowlist> <out dir>
           assemble a review packet ONLY from the allowlisted repository paths
           at <commit>, byte-verified against the commit's blobs; anything not
           on the list (a brief, a note, a single number) cannot enter. The
           assembled packet is then scanned like a directory.

Exit 0 clean, 1 found (or a packet refused), 2 usage, 3 no verdict (the
store variable is set but the store cannot be read). With the variable unset
it prints `review_needles: unarmed` and exits 0.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys

STORE_ENV = "SCR_REVIEW_PRIVATE_STORE"
WORDING_MIN = 12
FRAGMENT_MIN = 3
WORDING_GAP = 80
BASENAME_MIN = 12
# Names the public loader and build tool themselves use: not private.
PUBLIC_NAMES = {"REVISIONS.tsv", "selftest.json"}
_REV_DIR = re.compile(r"rules-[0-9a-f]{12}")
_PLACE = re.compile(r"\{[^{}]*\}")


class NoVerdict(Exception):
    pass


def derive(store: str) -> dict:
    """{class: set(needles)} from the private store."""
    out = {"rule_id": set(), "nonce": set(), "wording": set(), "listed": set(), "basename": set()}
    try:
        names = sorted(os.listdir(store))
    except OSError as e:
        raise NoVerdict(type(e).__name__)
    for name in names:
        path = os.path.join(store, name)
        if _REV_DIR.fullmatch(name) and os.path.isdir(path):
            try:
                with open(os.path.join(path, "rules.json"), encoding="utf-8") as f:
                    doc = json.load(f)
            except (OSError, ValueError) as e:
                raise NoVerdict(type(e).__name__)
            if isinstance(doc.get("nonce"), str) and doc["nonce"]:
                out["nonce"].add(doc["nonce"])
            for r in doc.get("rules") or []:
                if isinstance(r.get("id"), str):
                    out["rule_id"].add(r["id"])
                frags = tuple(f.strip() for f in _PLACE.split(r.get("line") or "")
                              if len(f.strip()) >= FRAGMENT_MIN)
                if len(frags) >= 2 and sum(len(f) for f in frags) >= WORDING_MIN:
                    out["wording"].add(frags)
    tests = os.path.join(store, "tests")
    listed = os.path.join(tests, "needles.txt")
    if os.path.exists(listed):
        with open(listed, encoding="utf-8") as f:
            out["listed"] = {ln.strip() for ln in f if ln.strip() and not ln.startswith("#")}
    for base in (store, tests):
        if os.path.isdir(base):
            for name in os.listdir(base):
                if (os.path.isfile(os.path.join(base, name)) and "." in name
                        and len(name) >= BASENAME_MIN and name not in PUBLIC_NAMES):
                    out["basename"].add(name)
    return out


_SEQ = {}


def _sequence(frags):
    """A wording needle: its fragments in order, each gap at most WORDING_GAP
    characters on one line -- it matches the template and every line rendered
    from it, and not one common phrase on its own."""
    if frags not in _SEQ:
        gap = "[^\n]{0,%d}?" % WORDING_GAP
        _SEQ[frags] = re.compile(gap.join(re.escape(f) for f in frags))
    return _SEQ[frags]


def count(text: str, needles: dict, *, paths_only=False) -> dict:
    """{class: number of needles of that class present in text}."""
    found = {}
    for cls, items in needles.items():
        if paths_only and cls != "basename":
            continue
        n = sum(1 for s in items if s and (_sequence(s).search(text) if isinstance(s, tuple)
                                           else s in text))
        if n:
            found[cls] = found.get(cls, 0) + n
    return found


def _merge(a, b):
    for k, v in b.items():
        a[k] = a.get(k, 0) + v
    return a


def _git(repo, *args, binary=False):
    out = subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True).stdout
    return out if binary else out.decode("utf-8", "replace")


def _blob_text(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def scan_staged(repo, needles):
    found = {}
    _merge(found, count(_git(repo, "diff", "--cached", "--no-color", "-U0"), needles))
    for p in _git(repo, "diff", "--cached", "--name-only", "-z").split("\0"):
        if p:
            _merge(found, count(p, needles, paths_only=True))
    return found


def scan_range(repo, base, tip, needles):
    found = {}
    commits = _git(repo, "rev-list", "%s..%s" % (base, tip)).split()
    for c in commits:
        _merge(found, count(_git(repo, "show", "-s", "--format=%an%n%ae%n%cn%n%ce%n%B", c), needles))
        tree = _git(repo, "diff-tree", "-r", "--no-commit-id", "-z", "--root", c).split("\0")
        i = 0
        while i < len(tree) - 1:
            meta, path = tree[i], tree[i + 1]
            i += 2
            if not meta:
                continue
            parts = meta.split()
            blob, status = parts[3], parts[4]
            _merge(found, count(path, needles, paths_only=True))
            if status.startswith("D") or set(blob) == {"0"}:
                continue
            _merge(found, count(_blob_text(_git(repo, "cat-file", "blob", blob, binary=True)), needles))
    return found, len(commits)


def scan_dir(d, needles):
    found = {}
    for top, _dirs, files in os.walk(d):
        for name in files:
            p = os.path.join(top, name)
            _merge(found, count(os.path.relpath(p, d), needles, paths_only=True))
            with open(p, "rb") as f:
                _merge(found, count(_blob_text(f.read()), needles))
    return found


def packet(repo, commit, allowlist, out_dir, needles):
    """Copy ONLY allowlisted repository paths at `commit` into out_dir, each
    verified byte for byte against its blob; then scan the result."""
    with open(allowlist, encoding="utf-8") as f:
        paths = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    if os.path.exists(out_dir) and os.listdir(out_dir):
        return {"refused": "out_dir_not_empty"}
    tracked = set(_git(repo, "ls-tree", "-r", "--name-only", "-z", commit).split("\0"))
    for p in paths:
        if p not in tracked or p.startswith("/") or ".." in p.split("/"):
            return {"refused": "not_an_allowlisted_public_source"}
    os.makedirs(out_dir, exist_ok=True)
    for p in paths:
        raw = _git(repo, "show", "%s:%s" % (commit, p), binary=True)
        want = _git(repo, "rev-parse", "%s:%s" % (commit, p)).strip()
        dst = os.path.join(out_dir, *p.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(raw)
        with open(dst, "rb") as f:
            got = f.read()
        header = b"blob %d\0" % len(got)
        if hashlib.sha1(header + got).hexdigest() != want:
            return {"refused": "bytes_differ_from_the_commit"}
    entries = sum(len(files) for _t, _d, files in os.walk(out_dir))
    if entries != len(paths):
        return {"refused": "extra_entries"}
    return scan_dir(out_dir, needles)


def report(label, found, n=None):
    if "refused" in found:
        print("review_needles: %s refused (%s)" % (label, found["refused"]))
        return 1
    total = sum(found.values())
    detail = ", ".join("%s=%d" % (k, found[k]) for k in sorted(found)) or "none"
    print("review_needles: %s %d found (%s)%s" % (label, total, detail,
                                                 "" if n is None else " over %d commit(s)" % n))
    return 1 if total else 0


def main(argv):
    store = os.environ.get(STORE_ENV) or ""
    if not argv:
        print(__doc__.split("Modes:")[1].split("Exit 0")[0].rstrip())
        return 2
    if not store:
        print("review_needles: unarmed (%s is unset)" % STORE_ENV)
        return 0
    try:
        needles = derive(store)
    except NoVerdict as e:
        print("review_needles: no verdict (store unreadable: %s)" % e)
        return 3
    cmd, rest = argv[0], argv[1:]
    if cmd == "staged" and len(rest) == 1:
        return report("staged", scan_staged(rest[0], needles))
    if cmd == "range" and len(rest) == 3:
        found, n = scan_range(rest[0], rest[1], rest[2], needles)
        return report("range", found, n)
    if cmd == "message" and len(rest) == 1:
        with open(rest[0], encoding="utf-8", errors="replace") as f:
            return report("message", count(f.read(), needles))
    if cmd == "scan-dir" and len(rest) == 1:
        return report("dir", scan_dir(rest[0], needles))
    if cmd == "packet" and len(rest) == 4:
        return report("packet", packet(rest[0], rest[1], rest[2], rest[3], needles))
    print(__doc__.split("Modes:")[1].split("Exit 0")[0].rstrip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
