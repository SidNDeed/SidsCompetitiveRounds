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
            rendered from it match, and one common phrase alone does not; a
            wording with ONE fragment is a needle when that fragment alone is
            at least WORDING_MIN characters
  data      every data table name a revision ships under data/ and every name
            its rules reference ({"data": name}), with and without the
            extension (a stem shorter than DATA_STEM_MIN is not used alone)
  listed    every line of the store's tests/needles.txt (identifiers the
            store's owner lists by hand)
  basename  the names of the store's own private files (not its revision
            directories: a revision id is public, the health word says it)
  value     every DECIDING VALUE of every revision in the store (measure
            parameters, rule literals, sitting arguments), each matched in the
            forms that re-publish it: beside its own key (`late margin ... N`,
            `N ... window_days`, either order, one line), and for a value of
            magnitude VALUE_MIN_BARE or more (or a fraction) also beside a
            comparison sign (`> N`, `N <=`, never a shift `<<`) or after a
            threshold noun (`threshold N`, `cutoff of N`, `floor N`), with
            its unit (`N ms`, `N-day`), or slash-joined to another value of
            the same rule (`N/M`); every form stays on one line. Prose
            quantifiers (`at most N words`) are not comparisons here: they
            are everywhere in briefs. 0, 1, -1 and booleans are structural,
            never needles. The value class applies to DOCUMENTS: a message,
            and in scan-dir and packet every file that is not source code
            (anything but CODE_EXT, and all of a packet's docs/); source
            code in a commit or a packet is the
            no-tunables guard's (review_guard.py). A public text that merely
            coincides with a value (a contract mechanic) is exempted only by
            its exact phrase, listed by hand in the store's
            tests/public.txt; the phrase is cut from the text before
            the value needles run, so the same value anywhere else still hits.

Modes:
  staged   <repo>                   added lines and staged blobs, staged paths
  range    <repo> <base> <tip>      every commit of base..tip: its message and
                                    identities, every blob it adds or changes,
                                    every path it touches
  message  <file>                   one commit message
  scan-dir <dir>                    every file under a directory
  packet   <repo> <commit> <allowlist> <out dir>
           assemble a review packet ONLY from the allowlist: a line
           `<repository path>` copies that path at <commit>, byte-verified
           against the commit's blob; a line `doc <absolute path> <sha256>`
           copies one document from outside the repository into docs/,
           admitted only when its bytes hash to the pinned digest (a document
           edited after its digest was pinned is refused). Anything not on the
           list (a brief, a note, a single number) cannot enter. The packet
           then gets PACKET-MANIFEST.txt (the sha256 and path of every other
           file) and the whole directory, manifest included, is scanned; the
           report names the manifest's sha256.
  packet-verify <out dir> <manifest sha256>
           the packet exactly as assembled: the manifest hashes to the pinned
           digest and the directory holds exactly the files it lists, each
           with its listed bytes; a file added, removed or changed after the
           scan is refused.

Exit 0 clean, 1 found (or a packet refused), 2 usage, 3 no verdict (any
read of the store failed -- the store itself, a revision, its data listing,
the needles list, the basename listing -- or it holds no revision), 4 unarmed
(the store variable is unset). 3 and 4 are REFUSALS: no scan ran, and neither
is ever a pass.
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
DATA_STEM_MIN = 8
VALUE_MIN_BARE = 10
VALUE_NEAR = 24
MANIFEST = "PACKET-MANIFEST.txt"
# source code the value class leaves to the no-tunables guard
CODE_EXT = (".py", ".cs", ".sql", ".yml", ".yaml", ".csproj", ".sh", ".ps1", ".json")
# what states a decision before a value: a comparison sign (never a shift)
# or a threshold noun
_SIGN = r"(?:(?<![<>])[<>]=?(?![<>])|\u2265|\u2264)"
_CMP = (r"(?:%s|\b(?:threshold|cut-?off|floor|ceiling|boundary|margin|limit)"
        r"(?:[ \t](?:of|is|at))?[ \t]?[=:]?)" % _SIGN)
# Names the public loader and build tool themselves use: not private.
PUBLIC_NAMES = {"REVISIONS.tsv", "selftest.json"}
_REV_DIR = re.compile(r"rules-[0-9a-f]{12}")
_PLACE = re.compile(r"\{[^{}]*\}")


class NoVerdict(Exception):
    pass


def derive(store: str) -> dict:
    """{class: set(needles)} from the private store."""
    out = {"rule_id": set(), "nonce": set(), "wording": set(), "listed": set(), "basename": set(),
           "data": set(), "value": set()}
    try:
        return _derive(store, out)
    except NoVerdict:
        raise
    except (OSError, ValueError) as e:              # every read of the store: one refusal path
        raise NoVerdict(type(e).__name__)


def _derive(store, out):
    names = sorted(os.listdir(store))
    revisions = 0
    for name in names:
        path = os.path.join(store, name)
        if _REV_DIR.fullmatch(name) and os.path.isdir(path):
            revisions += 1
            try:
                with open(os.path.join(path, "rules.json"), encoding="utf-8") as f:
                    doc = json.load(f)
                ddir = os.path.join(path, "data")
                shipped = sorted(os.listdir(ddir)) if os.path.isdir(ddir) else []
            except (OSError, ValueError) as e:
                raise NoVerdict(type(e).__name__)
            if isinstance(doc.get("nonce"), str) and doc["nonce"]:
                out["nonce"].add(doc["nonce"])
            for r in doc.get("rules") or []:
                if isinstance(r.get("id"), str):
                    out["rule_id"].add(r["id"])
                frags = tuple(f.strip() for f in _PLACE.split(r.get("line") or "")
                              if len(f.strip()) >= FRAGMENT_MIN)
                if frags and sum(len(f) for f in frags) >= WORDING_MIN:
                    out["wording"].add(frags)
            for dn in shipped + sorted(_data_refs(doc)):
                out["data"].add(dn)
                stem = dn.rsplit(".", 1)[0]
                if len(stem) >= DATA_STEM_MIN:
                    out["data"].add(stem)
            out["value"] |= _value_needles(doc)
    if not revisions:
        raise NoVerdict("no revision")
    tests = os.path.join(store, "tests")
    listed = os.path.join(tests, "needles.txt")
    if os.path.lexists(listed):
        with open(listed, encoding="utf-8") as f:
            out["listed"] = {ln.strip() for ln in f if ln.strip() and not ln.startswith("#")}
    public = os.path.join(tests, "public.txt")
    _PUBLIC.clear()
    if os.path.lexists(public):
        with open(public, encoding="utf-8") as f:
            _PUBLIC.extend(sorted({ln.rstrip("\n") for ln in f
                                   if ln.strip() and not ln.startswith("#")}, key=len, reverse=True))
    for base in (store, tests):
        if os.path.lexists(base):
            for name in os.listdir(base):
                if (os.path.isfile(os.path.join(base, name)) and "." in name
                        and len(name) >= BASENAME_MIN and name not in PUBLIC_NAMES):
                    out["basename"].add(name)
    return out


def _num_tokens(v) -> list:
    """The decimal renderings of a deciding number (none for 0, 1, -1 or a
    boolean: those are structural)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return []
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if v in (0, 1, -1):
        return []
    if isinstance(v, int):
        return [str(v)]
    toks = {repr(v), "%g" % v}
    toks |= {t[1:] for t in toks if t.startswith("0.")}
    toks |= {"-" + t[2:] for t in toks if t.startswith("-0.")}
    return sorted(toks)


def _measure_keys(node) -> list:
    out = []
    if isinstance(node, dict):
        if set(node) == {"m"} and isinstance(node["m"], str):
            out.append(node["m"].rsplit(".", 1)[-1])
        for v in node.values():
            out += _measure_keys(v)
    elif isinstance(node, list):
        for v in node:
            out += _measure_keys(v)
    return out


def _pred_values(node, items, group):
    """(key, value, group) for every literal of a predicate, keyed by the
    measures its comparison reads."""
    if isinstance(node, dict):
        args = node.get("args")
        if isinstance(args, dict):
            keys = _measure_keys(args) or [""]
            for a in args.values():
                if isinstance(a, dict) and set(a) == {"v"}:
                    vals = a["v"] if isinstance(a["v"], list) else [a["v"]]
                    for v in vals:
                        items += [(k, v, group) for k in keys]
        for v in node.values():
            _pred_values(v, items, group)
    elif isinstance(node, list):
        for v in node:
            _pred_values(v, items, group)


def _value_items(doc) -> list:
    """(key, value, group) for every deciding value of a rules document: the
    measure parameters, the rule literals and the sitting arguments."""
    items = []
    for fam, ps in (doc.get("measure_params") or {}).items():
        if isinstance(ps, dict):
            items += [(k, v, fam) for k, v in ps.items()]
    for r in doc.get("rules") or []:
        if not isinstance(r, dict):
            continue
        group = str(r.get("id"))
        _pred_values(r.get("when"), items, group)
        s = r.get("sitting")
        if isinstance(s, dict) and isinstance(s.get("args"), dict):
            items += [(k, v, group) for k, v in s["args"].items()]
    return items


UNIT_WORDS = ("ms", "s", "days", "day", "pct")


def _key_pattern(key: str) -> str:
    """A key as prose or code writes it (`late_margin_ms`, `late margin`,
    `late-margin ms`): words joined by a space, underscore or hyphen, a
    trailing unit word optional. An empty key (a literal no measure names)
    has no pattern."""
    words = [w for w in re.split(r"[_\W]+", key) if w]
    unit = ""
    if len(words) > 1 and words[-1] in UNIT_WORDS:
        unit = r"(?:[ _-]?%s)?" % re.escape(words.pop())
    return r"[ _-]?".join(re.escape(w) for w in words) + unit if words else ""


def _value_needles(doc) -> set:
    """Regular-expression needles (class `value`) for every deciding value."""
    out = set()
    by_group = {}
    for key, v, group in _value_items(doc):
        toks = _num_tokens(v)
        if not toks:
            continue
        num = r"(?<![\w.])(?:%s)(?![\w]|\.\d)" % "|".join(re.escape(t) for t in toks)
        kp = _key_pattern(key)
        if kp:
            out.add(r"(?i)\b%s\b[^\n]{0,%d}?%s" % (kp, VALUE_NEAR, num))
            out.add(r"(?i)%s[^\n]{0,%d}?\b%s\b" % (num, VALUE_NEAR, kp))
        bare = isinstance(v, float) and not float(v).is_integer() or abs(v) >= VALUE_MIN_BARE
        if bare:
            out.add(r"(?i)%s[ \t]{0,3}%s" % (_CMP, num))
            out.add(r"%s[ \t]{0,3}%s" % (num, _SIGN))
            if key.endswith("ms"):
                out.add(r"%s[ \t]?ms\b" % num)
            if key.endswith("days"):
                out.add(r"(?i)%s[ \t-]?days?\b" % num)
            by_group.setdefault(group, set()).add("|".join(re.escape(t) for t in toks))
    for group, alts in by_group.items():
        if len(alts) > 1:
            one = "|".join(sorted(alts))
            out.add(r"(?<![\w.])(?:%s)[ \t]?/[ \t]?(?:%s)(?![\w]|\.\d)" % (one, one))
    return {("re", p) for p in out}


_RX = {}
_PUBLIC = []        # exact public phrases cut before the value needles run


def _rx(p):
    if p not in _RX:
        _RX[p] = re.compile(p)
    return _RX[p]


def _data_refs(node) -> set:
    """Every name a rules document references as {"data": name}."""
    out = set()
    if isinstance(node, dict):
        if set(node) == {"data"} and isinstance(node["data"], str):
            out.add(node["data"])
        for v in node.values():
            out |= _data_refs(v)
    elif isinstance(node, list):
        for v in node:
            out |= _data_refs(v)
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


def count(text: str, needles: dict, *, paths_only=False, values=False) -> dict:
    """{class: number of needles of that class present in text}. The value
    class applies only when `values` (documents, not code)."""
    found = {}
    public_cut = text
    if values:
        for phrase in _PUBLIC:
            public_cut = public_cut.replace(phrase, " ")
    for cls, items in needles.items():
        if paths_only and cls != "basename":
            continue
        if cls == "value" and not values:
            continue
        n = sum(1 for s in items if s and (_rx(s[1]).search(public_cut) if cls == "value"
                                           else _sequence(s).search(text) if isinstance(s, tuple)
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
            rel = os.path.relpath(p, d).replace(os.sep, "/")
            doc = rel.startswith("docs/") or not rel.endswith(CODE_EXT)
            with open(p, "rb") as f:
                _merge(found, count(_blob_text(f.read()), needles, values=doc))
    return found


def _manifest_lines(out_dir) -> list:
    rows = []
    for top, _dirs, files in os.walk(out_dir):
        for name in files:
            p = os.path.join(top, name)
            rel = os.path.relpath(p, out_dir).replace(os.sep, "/")
            if rel == MANIFEST:
                continue
            with open(p, "rb") as f:
                rows.append("%s  %s" % (hashlib.sha256(f.read()).hexdigest(), rel))
    return sorted(rows, key=lambda r: r.split("  ", 1)[1])


def packet_verify(out_dir, want) -> dict:
    """{} when out_dir is exactly the packet its manifest pins, else a refusal."""
    try:
        with open(os.path.join(out_dir, MANIFEST), "rb") as f:
            raw = f.read()
    except OSError:
        return {"refused": "manifest_unreadable"}
    if hashlib.sha256(raw).hexdigest() != want:
        return {"refused": "manifest_digest_differs"}
    listed = raw.decode("utf-8", "replace").splitlines()
    if _manifest_lines(out_dir) != listed:
        return {"refused": "packet_differs_from_its_manifest"}
    return {}


def packet(repo, commit, allowlist, out_dir, needles):
    """Copy ONLY allowlisted repository paths at `commit` into out_dir, each
    verified byte for byte against its blob; then scan the result."""
    with open(allowlist, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    paths, docs = [], []
    for ln in lines:
        parts = ln.split()
        if parts[0] == "doc":
            if (len(parts) != 3 or not os.path.isabs(parts[1])
                    or not re.fullmatch(r"[0-9a-f]{64}", parts[2])):
                return {"refused": "malformed_doc_entry"}
            docs.append((parts[1], parts[2]))
        else:
            paths.append(ln)
    if os.path.exists(out_dir) and os.listdir(out_dir):
        return {"refused": "out_dir_not_empty"}
    tracked = set(_git(repo, "ls-tree", "-r", "--name-only", "-z", commit).split("\0"))
    for p in paths:
        if p not in tracked or p.startswith("/") or ".." in p.split("/") or p.startswith("docs/"):
            return {"refused": "not_an_allowlisted_public_source"}
    if len({os.path.basename(d) for d, _h in docs}) != len(docs):
        return {"refused": "doc_name_collision"}
    doc_bytes = []
    for d, want in docs:
        try:
            with open(d, "rb") as f:
                raw = f.read()
        except OSError:
            return {"refused": "doc_unreadable"}
        if hashlib.sha256(raw).hexdigest() != want:
            return {"refused": "doc_digest_differs"}
        doc_bytes.append((os.path.basename(d), raw, want))
    os.makedirs(out_dir, exist_ok=True)
    for name, raw, want in doc_bytes:
        dst = os.path.join(out_dir, "docs", name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(raw)
        with open(dst, "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() != want:
                return {"refused": "bytes_differ_from_the_pin"}
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
    if entries != len(paths) + len(docs):
        return {"refused": "extra_entries"}
    if MANIFEST in {os.path.basename(d) for d, _h in docs} or MANIFEST in paths:
        return {"refused": "manifest_name_taken"}
    body = ("\n".join(_manifest_lines(out_dir)) + "\n").encode("utf-8")
    with open(os.path.join(out_dir, MANIFEST), "wb") as f:
        f.write(body)
    found = scan_dir(out_dir, needles)
    found["manifest"] = hashlib.sha256(body).hexdigest()
    return found


def report(label, found, n=None):
    if "refused" in found:
        print("review_needles: %s refused (%s)" % (label, found["refused"]))
        return 1
    manifest = found.pop("manifest", None)
    total = sum(found.values())
    detail = ", ".join("%s=%d" % (k, found[k]) for k in sorted(found)) or "none"
    print("review_needles: %s %d found (%s)%s%s" % (label, total, detail,
                                                   "" if n is None else " over %d commit(s)" % n,
                                                   "" if manifest is None else " manifest " + manifest))
    return 1 if total else 0


def main(argv):
    store = os.environ.get(STORE_ENV) or ""
    if not argv:
        print(__doc__.split("Modes:")[1].split("Exit 0")[0].rstrip())
        return 2
    if not store:
        print("review_needles: unarmed (%s is unset): refused, nothing was scanned" % STORE_ENV)
        return 4
    try:
        needles = derive(store)
    except NoVerdict as e:
        print("review_needles: no verdict (store unreadable: %s): refused, nothing was scanned" % e)
        return 3
    cmd, rest = argv[0], argv[1:]
    if cmd == "staged" and len(rest) == 1:
        return report("staged", scan_staged(rest[0], needles))
    if cmd == "range" and len(rest) == 3:
        found, n = scan_range(rest[0], rest[1], rest[2], needles)
        return report("range", found, n)
    if cmd == "message" and len(rest) == 1:
        with open(rest[0], encoding="utf-8", errors="replace") as f:
            return report("message", count(f.read(), needles, values=True))
    if cmd == "scan-dir" and len(rest) == 1:
        return report("dir", scan_dir(rest[0], needles))
    if cmd == "packet" and len(rest) == 4:
        return report("packet", packet(rest[0], rest[1], rest[2], rest[3], needles))
    if cmd == "packet-verify" and len(rest) == 2:
        return report("packet-verify", packet_verify(rest[0], rest[1]))
    print(__doc__.split("Modes:")[1].split("Exit 0")[0].rstrip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
