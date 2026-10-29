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
  value     every DECIDING VALUE of every revision in the store, by its
            position in the rules schema (fix pass 5): every measure
            parameter, every literal and argument of a predicate (scalar,
            list member or nested in arithmetic, a relation included), every
            sitting argument that is not a vocabulary name (scalar, edges,
            label), every key and value of a JSON data table at any depth,
            every nonempty line of a text table as the EXACT string the
            loader produced (fix pass 7: the evaluator decides on that
            string, so a line of leading zeros is matched with its zeros; its
            token and numeric forms are derived in addition, never instead),
            and every value of a pre-closure
            vocabulary map (fix pass 6: the rules document shape the writer
            recorded before commit 23bf1ade, whose names are the vocabulary
            exactly as a list's are). Every such value is a number, a
            Boolean, null or a string (LEAF_TYPES); anything else, and any
            position the schema does not have, is the exit-3 refusal, never
            a skip. Each is matched beside its own key (`late margin ... N`,
            `N ... window_days`, `published hits ... true`, either order,
            one line); a value whose bare form means nothing (0, 1, -1, any
            other number below VALUE_MIN_BARE, a Boolean, null, a string
            shorter than STR_MIN_BARE) is matched ONLY there, and refused if
            it has no key; a number of magnitude VALUE_MIN_BARE or more (or
            a fraction) also beside a comparison sign (`> N`, `N <=`, never
            a shift `<<`) or after a threshold noun (`threshold N`, `cutoff
            of N`, `floor N`), with its unit (`N ms`, `N-day`), or
            slash-joined to another value of the same rule (`N/M`); a string
            of STR_MIN_BARE characters or more also on its own; and a list
            member beside the next member of its own list (`N, M`); every
            form stays on one line. Prose quantifiers (`at most N words`)
            are not comparisons here: they are everywhere in briefs. Rule
            metadata (scope, subject, effect, post, post_since, show) is not
            a deciding value: the rule's id and wording are its needles
            (RULE_META). The value class applies to EVERY text in every
            mode: a commit message (range, message), every file and blob of
            every type in staged, range, scan-dir, packet and seal, and every
            path; no extension, file name or directory turns it off (fix pass
            4). Source code is judged by it as well as by the no-tunables
            guard (review_guard.py). A public text that merely
            coincides with a value (a contract mechanic) is exempted only by
            its exact phrase, listed by hand in the store's
            tests/public.txt; the phrase is cut from the text before
            the value needles run, so the same value anywhere else still hits.
            A list's adjacent members are matched joined by `,`, `;`, `/` or
            plain spaces (a text table's row).

Modes:
  staged   <repo>                   every staged blob whole, staged paths
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
           file). Every file of the packet is read ONCE into one byte
           snapshot: each is verified against its commit blob or its pinned
           digest, listed in the manifest and scanned (manifest included) from
           those same bytes; the report names the manifest's sha256.
  seal     <pin> <manifest out> <title> <attester> <note file> <seal file>
           the FINAL corpus check, one command: (1) read every file of
           <pin>/REVIEW-INPUT ONCE into one byte snapshot; (2) build the pin
           manifest from that snapshot, exactly as the integrator's manifest
           tool writes it (header, pin line, the note, one `md5 bytes name`
           row per file, FILES and BYTES), and write it to <manifest out> and
           into REVIEW-INPUT; (3) scan the snapshot plus the manifest's bytes;
           (4) write the result line and the digest of those SAME bytes
           (sorted name, bytes and sha256 of every file, manifest included)
           to <seal file>, which must lie outside the corpus. What is scanned
           and what is sealed are one snapshot; any later change on disk is
           seal-verify's refusal.
  seal-verify <corpus dir> <seal file>
           recompute the corpus digest; a file added, removed or changed
           since the seal is refused by name (needs no store).
  packet-verify <out dir> <manifest sha256>
           the packet exactly as assembled: the manifest hashes to the pinned
           digest and the directory holds exactly the files it lists, each
           with its listed bytes, all from ONE snapshot; a file added,
           removed or changed after the scan is refused.

Every directory a mode reads (scan-dir, packet, packet-verify, seal,
seal-verify) is read through one snapshot: every entry is enumerated and must
be a regular file or a directory; a symbolic link, a junction (any reparse
entry), a device or any other entry is the exit-3 refusal naming its path, and
so is a tree that changes while the snapshot is taken.

Exit 0 clean, 1 found (or a packet or seal refused), 2 usage, 3 no verdict
(any read failed -- the store itself, a revision, its data listing or a data
table, the needles list, the basename listing, any status query of a path
other than its plain absence, a directory a scan walks -- or the store holds
no revision), 4 unarmed (the store variable is unset). 3 and 4 are REFUSALS: no scan ran, and neither
is ever a pass. A refusal while one revision is read names that revision's
folder and the reason; no reason carries a value of the store.
"""

from __future__ import annotations
import review_tripwire
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import time

STORE_ENV = "SCR_REVIEW_PRIVATE_STORE"
WORDING_MIN = 12
FRAGMENT_MIN = 3
WORDING_GAP = 80
BASENAME_MIN = 12
DATA_STEM_MIN = 8
VALUE_MIN_BARE = 10
VALUE_NEAR = 24
MANIFEST = "PACKET-MANIFEST.txt"
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


# Path status, strictly. os.path.exists/isdir/isfile/lexists answer False on
# ANY failure (a permission error, an I/O error, a name too long), which turns
# an unreadable store into an absent one. These answer from one stat call: the
# only failure read as absence is "no such file"; every other one raises
# NoVerdict, the single exit-3 refusal. test_review_needles enumerates every
# path query in this file and in review_rules.py so a new unwrapped one fails.
def _status(path, follow=True):
    try:
        return os.stat(path) if follow else os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as e:
        raise NoVerdict(type(e).__name__)


def _is_dir(path) -> bool:
    st = _status(path)
    return st is not None and stat.S_ISDIR(st.st_mode)


def _is_file(path) -> bool:
    st = _status(path)
    return st is not None and stat.S_ISREG(st.st_mode)


def _present(path) -> bool:
    return _status(path, follow=False) is not None


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
        if not _REV_DIR.fullmatch(name):
            continue
        try:
            if not _is_dir(path):
                continue
            revisions += 1
            _revision(path, out)
        except NoVerdict as e:
            # the refusal names its revision folder (a revision id is
            # public) and its reason; no reason text carries a value
            raise NoVerdict("revision %s: %s" % (name, e))
    if not revisions:
        raise NoVerdict("no revision")
    tests = os.path.join(store, "tests")
    listed = os.path.join(tests, "needles.txt")
    if _present(listed):
        with open(listed, encoding="utf-8") as f:
            out["listed"] = {ln.strip() for ln in f if ln.strip() and not ln.startswith("#")}
    public = os.path.join(tests, "public.txt")
    _PUBLIC.clear()
    if _present(public):
        with open(public, encoding="utf-8") as f:
            _PUBLIC.extend(sorted({ln.rstrip("\n") for ln in f
                                   if ln.strip() and not ln.startswith("#")}, key=len, reverse=True))
    for base in (store, tests):
        if _present(base):
            for name in os.listdir(base):
                if (_is_file(os.path.join(base, name)) and "." in name
                        and len(name) >= BASENAME_MIN and name not in PUBLIC_NAMES):
                    out["basename"].add(name)
    return out


def _revision(path, out):
    """One revision folder's needles. The value derivation checks the whole
    document by its schema FIRST (_value_items), so a shape it does not know
    is the refusal before any other class reads the document."""
    try:
        with open(os.path.join(path, "rules.json"), encoding="utf-8") as f:
            doc = json.load(f)
        ddir = os.path.join(path, "data")
        shipped = sorted(os.listdir(ddir)) if _is_dir(ddir) else []
        tables = {}
        for dn in shipped:
            # the bytes decoded as the loader decodes them (review_rules.load_dir:
            # no newline translation), so a text table's lines are its lines
            with open(os.path.join(ddir, dn), "rb") as f:
                text = f.read().decode("utf-8")
            tables[dn] = json.loads(text) if dn.endswith(".json") else text
    except (OSError, ValueError) as e:
        raise NoVerdict(type(e).__name__)
    if not isinstance(doc, dict):
        raise NoVerdict("rules document")
    out["value"] |= _value_needles(doc, tables)
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


def _num_tokens(v) -> list:
    """The decimal renderings of a finite number (0, 1 and -1 included)."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int):
        return [str(v)]
    toks = {repr(v), "%g" % v}
    toks |= {t[1:] for t in toks if t.startswith("0.")}
    toks |= {"-" + t[2:] for t in toks if t.startswith("-0.")}
    return sorted(toks)


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# The derivation, per type of value (fix pass 5). Every value the rules schema
# admits is exactly one of these types; any other value (a non-finite number,
# an object where a value stands, any other type) is the exit-3 refusal, never
# a skip. Per type: (context required, bare needle).
#   context: the value beside one of its keys, either order, on one line
#            (_key_pattern); every value gets it when it has a key, and a
#            type marked "required" with no usable key is refused
#   bare:    the value is a needle without its key -- a number with a
#            comparison sign, a threshold noun, its unit or a slash partner;
#            a string on its own, word-bounded
LEAF_TYPES = {
    "number": (False, True),         # a fraction, or a magnitude of VALUE_MIN_BARE or more
    "small_number": (True, False),   # every other finite number: 0, 1 and -1 included
    "bool": (True, False),           # `true` / `false`, any case
    "null": (True, False),           # `null` / `none`, any case
    "string": (False, True),         # STR_MIN_BARE characters or more
    "short_string": (True, False),   # shorter, the empty string included
}
STR_MIN_BARE = 8


def leaf_type(v) -> str:
    """The derivation type of one value; the refusal for anything else."""
    if isinstance(v, bool):
        return "bool"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        if not _finite(v):
            raise NoVerdict("a value that is not a finite number")
        if isinstance(v, float) and not v.is_integer():
            return "number"
        return "number" if abs(v) >= VALUE_MIN_BARE else "small_number"
    if isinstance(v, str):
        return "string" if len(v) >= STR_MIN_BARE else "short_string"
    raise NoVerdict("a value of no derivation type: " + type(v).__name__)


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


# Keys of the rules FORMAT, not names of a value: a value under one of these
# takes the nearest enclosing name instead (a literal `{"v": 7}` inside a
# comparison is keyed by the measures that comparison reads).
FORMAT_WORDS = frozenset({"v", "m", "op", "args", "all", "any", "not", "add", "sub", "abs",
                          "data", "when", "sitting", "rules", "measure_params", "show", "format",
                          "closure", "vocabulary", "nonce", "id", "line", "scope", "effect",
                          "post", "post_since", "subject", "rel", "set", "filters"})
KEY_MIN = 3
_TEXT_NUM = re.compile(r"[-+]?\d+(?:\.\d+)?")
_TEXT_SPLIT = re.compile(r"[\s,;]+")
TOP_KEYS = frozenset({"format", "nonce", "vocabulary", "closure", "measure_params", "rules"})
# Rule metadata: who the rule is and how it reads, never what decides it. The
# id and the line are needles of their own classes (rule_id, wording); scope,
# subject, effect and post are closed public enumerations written beside the
# same key in every public rules document and fixture, so their context is the
# rule itself, i.e. its id or its wording; show pairs a placeholder of the
# line with a vocabulary name or a sitting output (public names).
RULE_META = frozenset({"id", "line", "scope", "subject", "effect", "post", "post_since", "show"})


def _keys(*names) -> tuple:
    """The context keys of a value: each name a text could put beside it (a
    format word or a name shorter than KEY_MIN is not one)."""
    return tuple(n for n in names if isinstance(n, str) and len(n) >= KEY_MIN and n not in FORMAT_WORDS)


class _Values:
    """Every deciding value of a revision: (keys, value, type, group) items and
    the lists whose adjacent members are needles together."""

    def __init__(self):
        self.items, self.lists = [], []

    def add(self, v, keys, group, where):
        if isinstance(v, list):
            for x in v:
                self.add(x, keys, group, where)
            near = [x for x in v if _finite(x) and x not in (0, 1, -1)]
            if len(near) > 1:
                self.lists.append(tuple(near))
            return
        t = leaf_type(v)
        if LEAF_TYPES[t][0] and not any(_key_pattern(k) for k in keys):
            raise NoVerdict("a value with no context to derive its needle: " + where)
        self.items.append((keys, v, t, group))


def _expr(node, keys, group, vals):
    if not isinstance(node, dict) or len(node) != 1:
        raise NoVerdict("an expression of no known form")
    (k, v), = node.items()
    if k == "m":
        if not isinstance(v, str):
            raise NoVerdict("a measure that is not a name")
    elif k == "v":
        if isinstance(v, dict):
            raise NoVerdict("an object as a literal")
        vals.add(v, keys, group, "literal")
    elif k in ("add", "sub"):
        if not isinstance(v, list):
            raise NoVerdict("arithmetic that is not a list")
        for x in v:
            _expr(x, keys, group, vals)
    elif k == "abs":
        _expr(v, keys, group, vals)
    else:
        raise NoVerdict("an expression of no known form")


def _pred(node, group, vals):
    if not isinstance(node, dict):
        raise NoVerdict("a predicate that is not an object")
    if set(node) == {"all"} or set(node) == {"any"}:
        (_k, v), = node.items()
        if not isinstance(v, list):
            raise NoVerdict("a predicate list that is not a list")
        for x in v:
            _pred(x, group, vals)
    elif set(node) == {"not"}:
        _pred(node["not"], group, vals)
    elif set(node) == {"op", "args"} and isinstance(node["op"], str) and isinstance(node["args"], dict):
        # every literal of a comparison is keyed by the measures it reads; with
        # none, by the operator's own name
        keys = _keys(*_measure_keys(node["args"])) or _keys(node["op"].rsplit(".", 1)[-1])
        for _name, v in node["args"].items():
            if isinstance(v, dict) and set(v) == {"data"}:
                if not isinstance(v["data"], str):
                    raise NoVerdict("a data reference that is not a name")
            elif isinstance(v, dict):
                _expr(v, keys, group, vals)
            else:                               # a relation, a list argument, any scalar
                vals.add(v, keys, group, "predicate argument")
    else:
        raise NoVerdict("a predicate of no known form")


def _sitting(node, names, group, vals):
    if (not isinstance(node, dict) or set(node) != {"op", "args"} or not isinstance(node["op"], str)
            or not isinstance(node["args"], dict)):
        raise NoVerdict("a sitting of no known form")
    tail = node["op"].rsplit(".", 1)[-1]
    for name, v in node["args"].items():
        if isinstance(v, str) and v in names:
            continue                            # a vocabulary name (side, row, reporter)
        if isinstance(v, list) and v and all(isinstance(x, str) and x in names for x in v):
            continue                            # vocabulary names (filters)
        if isinstance(v, dict):
            raise NoVerdict("an object as a sitting argument")
        vals.add(v, _keys(name) or _keys(tail), group, "sitting argument")


def _meta(r):
    """A rule's metadata, type-checked (RULE_META says why it carries no value
    needle); anything else in a rule is refused."""
    if not set(r) <= RULE_META | {"when", "sitting"}:
        raise NoVerdict("a rule key of no known kind")
    for k in ("id", "line", "scope", "subject", "effect"):
        if k in r and not isinstance(r[k], str):
            raise NoVerdict("rule metadata of the wrong type")
    if "post" in r and not isinstance(r["post"], bool):
        raise NoVerdict("rule metadata of the wrong type")
    if "post_since" in r and not (r["post_since"] is None or isinstance(r["post_since"], str)):
        raise NoVerdict("rule metadata of the wrong type")
    show = r.get("show", [])
    if not isinstance(show, list) or not all(isinstance(s, list) and all(isinstance(x, str) for x in s)
                                             for s in show):
        raise NoVerdict("rule metadata of the wrong type")


def _table(node, keys, group, vals):
    """A JSON data table: every key and every value, nested to any depth."""
    if isinstance(node, dict):
        for k, v in node.items():
            vals.add(k, keys, group, "data table key")
            _table(v, _keys(k) or keys, group, vals)
    elif isinstance(node, list):
        flat = [x for x in node if not isinstance(x, (list, dict))]
        vals.add(flat, keys, group, "data table value")
        for x in node:
            if isinstance(x, (list, dict)):
                _table(x, keys, group, vals)
    else:
        vals.add(node, keys, group, "data table value")


def _text_value(tok):
    if _TEXT_NUM.fullmatch(tok):
        return float(tok) if "." in tok else int(tok)
    return tok


def _text_lines(text) -> list:
    """A text table's values as the loader produces them (review_rules.load_dir
    and build_revision: `[ln for ln in text.splitlines() if ln.strip()]`):
    every nonempty line, each the exact string op.in_set compares."""
    return [ln for ln in text.splitlines() if ln.strip()]


def _value_items(doc, tables=None) -> tuple:
    """(items, lists) for every deciding value of a rules document and its data
    tables, by POSITION in the rules schema: measure parameters, every literal
    and argument of a predicate (scalar, list or nested), every sitting
    argument that is not a vocabulary name, every key and value of a JSON
    table, and every nonempty line of a text table as the exact string the
    loader produced (_text_lines), that line without its outer blanks when it
    has any, and its tokens (a numeric token as its number) in addition. A
    position the schema does not have and a value of no derivation type are
    refused (NoVerdict), never skipped.

    Two document shapes, each accepted explicitly: the current one (the
    vocabulary a list of names) and the PRE-CLOSURE one the writer recorded
    before commit 23bf1ade (no `closure` key; the vocabulary a map of entry
    name -> the entry's fingerprint). A map's keys must all be strings: they
    are the names, used exactly where a list's names are; its values are
    deciding values of the revision, derived as data-table values are (keyed
    by the entry name and its last part). Every other check is the same for
    both shapes; a vocabulary of any other shape is refused."""
    if not isinstance(doc, dict) or not set(doc) <= TOP_KEYS:
        raise NoVerdict("a rules document key of no known kind")
    vocab = doc.get("vocabulary", [])
    if isinstance(vocab, dict):
        if not all(isinstance(n, str) for n in vocab):
            raise NoVerdict("a pre-closure vocabulary with a name that is not a string")
    elif not isinstance(vocab, list) or not all(isinstance(n, str) for n in vocab):
        raise NoVerdict("a vocabulary that is not a list of names")
    if not isinstance(doc.get("closure", {}), dict) or isinstance(doc.get("format"), (dict, list)):
        raise NoVerdict("a format or closure of no known form")
    names = set(vocab)
    vals = _Values()
    params = doc.get("measure_params") or {}
    if not isinstance(params, dict):
        raise NoVerdict("measure parameters that are not an object")
    for fam, ps in params.items():
        if not isinstance(ps, dict):
            raise NoVerdict("a parameter family that is not an object")
        for k, v in ps.items():
            if isinstance(v, dict) and _profile_values(fam, k, v, vals):
                continue                # one deal profile's value set, derived
            vals.add(v, _keys(k) or _keys(str(fam).rsplit(".", 1)[-1]), str(fam), "measure parameter")
    rules = doc.get("rules") or []
    if not isinstance(rules, list):
        raise NoVerdict("rules that are not a list")
    for r in rules:
        if not isinstance(r, dict):
            raise NoVerdict("a rule that is not an object")
        _meta(r)
        group = str(r.get("id"))
        if "when" in r:
            _pred(r["when"], group, vals)
        if "sitting" in r:
            _sitting(r["sitting"], names, group, vals)
    if isinstance(vocab, dict):
        for name, v in sorted(vocab.items()):
            _table(v, _keys(name, name.rsplit(".", 1)[-1]), "vocabulary", vals)
    for name, table in sorted((tables or {}).items()):
        stem = name.rsplit(".", 1)[0]
        keys = _keys(stem) or _keys(name)
        group = "data:" + name
        if isinstance(table, str):
            for ln in _text_lines(table):
                vals.add(ln, keys, group, "text table line")         # the exact string the loader produced
                if ln.strip() != ln:
                    vals.add(ln.strip(), keys, group, "text table line")
                vals.add([_text_value(t) for t in _TEXT_SPLIT.split(ln) if t], keys, group,
                         "text table value")
        else:
            _table(table, keys, group, vals)
    return vals.items, vals.lists


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


def _value_rx(v, t) -> str:
    """The value itself, as a pattern, per derivation type."""
    if t in ("number", "small_number"):
        return r"(?<![\w.])(?:%s)(?![\w]|\.\d)" % "|".join(re.escape(x) for x in _num_tokens(v))
    if t == "bool":
        return r"\b%s\b" % ("true" if v else "false")
    if t == "null":
        return r"\b(?:null|none)\b"
    if v == "":
        return r"(?:\"\"|'')"
    return r"(?<!\w)%s(?!\w)" % re.escape(v)


def _value_needles(doc, tables=None) -> set:
    """Regular-expression needles (class `value`) for every deciding value, by
    LEAF_TYPES."""
    out = set()
    by_group = {}
    items, lists = _value_items(doc, tables)
    for members in lists:
        alts = ["|".join(re.escape(t) for t in _num_tokens(x)) for x in members]
        for x, y in zip(alts, alts[1:]):
            out.add(r"(?<![\w.])(?:%s)(?:[ \t]*[,;/][ \t]*|[ \t]+)(?:%s)(?![\w]|\.\d)" % (x, y))
    for keys, v, t, group in items:
        val = _value_rx(v, t)
        for key in keys:
            kp = _key_pattern(key)
            if kp:
                out.add(r"(?i)\b%s\b[^\n]{0,%d}?%s" % (kp, VALUE_NEAR, val))
                out.add(r"(?i)%s[^\n]{0,%d}?\b%s\b" % (val, VALUE_NEAR, kp))
        if not LEAF_TYPES[t][1]:
            continue
        if t == "string":
            out.add(r"(?i)" + val)
            continue
        out.add(r"(?i)%s[ \t]{0,3}%s" % (_CMP, val))
        out.add(r"%s[ \t]{0,3}%s" % (val, _SIGN))
        if any(k.endswith("ms") for k in keys):
            out.add(r"%s[ \t]?ms\b" % val)
        if any(k.endswith("days") for k in keys):
            out.add(r"(?i)%s[ \t-]?days?\b" % val)
        by_group.setdefault(group, set()).add("|".join(re.escape(x) for x in _num_tokens(v)))
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


def count(text: str, needles: dict, *, paths_only=False) -> dict:
    """{class: number of needles of that class present in text}. The value
    class applies to every text; a path (`paths_only`) is checked for the
    basename and value classes."""
    found = {}
    public_cut = text
    for phrase in _PUBLIC:
        public_cut = public_cut.replace(phrase, " ")
    for cls, items in needles.items():
        if paths_only and cls not in ("basename", "value"):
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
    for p in _git(repo, "diff", "--cached", "--name-only", "-z").split("\0"):
        if p:
            _merge(found, count(p, needles, paths_only=True))
    for p in _git(repo, "diff", "--cached", "--name-only", "-z", "--diff-filter=d").split("\0"):
        if p:                       # every staged blob WHOLE (its added lines included)
            _merge(found, count(_blob_text(_git(repo, "show", ":" + p, binary=True)), needles))
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


_REPARSE_POINT = 0x400        # FILE_ATTRIBUTE_REPARSE_POINT: a junction, a symbolic link, any reparse entry


def _ident(st) -> tuple:
    return (stat.S_IFMT(st.st_mode), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def _entries(root) -> dict:
    """{relative name: identity} of EVERY entry under root, each judged from
    its own lstat: a regular file or a directory (descended) is represented;
    a symbolic link, a junction or any other reparse entry, a device, a pipe,
    a socket or anything else is the exit-3 refusal naming its path, as is an
    entry that vanishes while it is listed or a directory that cannot be
    listed."""
    st = _status(root, follow=False)
    if st is None or not stat.S_ISDIR(st.st_mode) or getattr(st, "st_file_attributes", 0) & _REPARSE_POINT:
        raise NoVerdict("not a plain directory: " + str(root))
    out, todo = {}, [("", root)]
    while todo:
        prefix, top = todo.pop()
        try:
            with os.scandir(top) as it:
                names = sorted(e.name for e in it)
        except OSError as e:
            raise NoVerdict("%s listing %s" % (type(e).__name__, prefix or "."))
        for name in names:
            rel = prefix + name
            st = _status(os.path.join(top, name), follow=False)
            if st is None:
                raise NoVerdict("an entry vanished while it was listed: " + rel)
            if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & _REPARSE_POINT:
                raise NoVerdict("a link or junction, which a snapshot does not represent: " + rel)
            if stat.S_ISDIR(st.st_mode):
                todo.append((rel + "/", os.path.join(top, name)))
            elif not stat.S_ISREG(st.st_mode):
                raise NoVerdict("an entry that is neither a regular file nor a directory: " + rel)
            out[rel] = _ident(st)
    return out


def _read_regular(path, rel, want) -> bytes:
    """One regular file's bytes, read once, from the very entry that was
    listed: the open handle's own identity must be the listed one."""
    with open(path, "rb") as f:
        if _ident(os.fstat(f.fileno())) != want:
            raise NoVerdict("an entry changed while the snapshot read it: " + rel)
        raw = f.read()
    if len(raw) != want[3]:
        raise NoVerdict("an entry changed while the snapshot read it: " + rel)
    return raw


def snapshot(root, skip=()) -> list:
    """[(name, bytes)] of every regular file under root (names relative,
    `/`-joined, a top-level name in `skip` left out), sorted by name: the one
    immutable byte copy that a scan, a manifest, a digest and every verifier
    use. Every directory entry is enumerated and must be a regular file or a
    directory (_entries); each file is read exactly ONCE from the entry that
    was listed; then the whole tree is listed again and must be identical
    entry for entry (type, device, inode, size, modification time), so a file
    added, removed, replaced or rewritten while the snapshot was taken is the
    exit-3 refusal, never a mixed copy."""
    listed = _entries(root)
    out = []
    for rel in sorted(listed):
        if listed[rel][0] == stat.S_IFREG and rel not in skip:
            out.append((rel, _read_regular(os.path.join(root, *rel.split("/")), rel, listed[rel])))
    again = _entries(root)
    if again != listed:
        moved = sorted(set(again) ^ set(listed)) or sorted(k for k in listed if again[k] != listed[k])
        raise NoVerdict("the directory changed while the snapshot was taken: " + moved[0])
    return out


def scan_snapshot(snap, needles) -> dict:
    found = {}
    for rel, raw in snap:
        _merge(found, count(rel, needles, paths_only=True))
        _merge(found, count(_blob_text(raw), needles))
    return found


def snapshot_rows(snap) -> list:
    """(name, bytes, sha256) of every file of a snapshot, sorted by name."""
    return sorted((rel, len(raw), hashlib.sha256(raw).hexdigest()) for rel, raw in snap)


def scan_dir(d, needles):
    return scan_snapshot(snapshot(d), needles)


def _manifest_lines_of(snap) -> list:
    return ["%s  %s" % (hashlib.sha256(raw).hexdigest(), rel) for rel, raw in sorted(snap) if rel != MANIFEST]


def packet_verify(out_dir, want) -> dict:
    """{} when out_dir is exactly the packet its manifest pins, else a refusal.
    The manifest and every other file come from ONE snapshot (the same listing
    and the same bytes): the manifest's digest, its lines and the files they
    are compared with are never read twice."""
    snap = snapshot(out_dir)
    raw = dict(snap).get(MANIFEST)
    if raw is None:
        return {"refused": "manifest_missing"}
    if hashlib.sha256(raw).hexdigest() != want:
        return {"refused": "manifest_digest_differs"}
    if _manifest_lines_of(snap) != raw.decode("utf-8", "replace").splitlines():
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
    if _present(out_dir) and os.listdir(out_dir):
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
    if MANIFEST in {os.path.basename(d) for d, _h in docs} or MANIFEST in paths:
        return {"refused": "manifest_name_taken"}
    os.makedirs(out_dir, exist_ok=True)
    pins = {}                               # packet name -> (kind, the digest its bytes must have)
    for name, raw, want in doc_bytes:
        dst = os.path.join(out_dir, "docs", name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(raw)
        pins["docs/" + name] = ("doc", want)
    for p in paths:
        raw = _git(repo, "show", "%s:%s" % (commit, p), binary=True)
        want = _git(repo, "rev-parse", "%s:%s" % (commit, p)).strip()
        dst = os.path.join(out_dir, *p.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(raw)
        pins[p] = ("blob", want)
    # one snapshot: what is verified, listed, scanned and digested is the same bytes
    snap = snapshot(out_dir)
    if len(snap) != len(paths) + len(docs) or [rel for rel, _raw in snap] != sorted(pins):
        return {"refused": "extra_entries"}
    for rel, got in snap:
        kind, want = pins[rel]
        if kind == "doc" and hashlib.sha256(got).hexdigest() != want:
            return {"refused": "bytes_differ_from_the_pin"}
        if kind == "blob" and hashlib.sha1(b"blob %d\0" % len(got) + got).hexdigest() != want:
            return {"refused": "bytes_differ_from_the_commit"}
    body = ("\n".join(_manifest_lines_of(snap)) + "\n").encode("utf-8")
    with open(os.path.join(out_dir, MANIFEST), "wb") as f:
        f.write(body)
    found = scan_snapshot(snap + [(MANIFEST, body)], needles)
    found["manifest"] = hashlib.sha256(body).hexdigest()
    return found


SEAL_DOMAIN = b"scr-review-corpus-seal\n"


def corpus_rows(corpus) -> list:
    """(name, bytes, sha256) of every file under corpus, sorted by name."""
    return snapshot_rows(snapshot(corpus))


def corpus_digest(rows) -> str:
    h = hashlib.sha256(SEAL_DOMAIN)
    for name, size, digest in rows:
        h.update(("%s\t%d\t%s\n" % (name, size, digest)).encode("utf-8"))
    return h.hexdigest()


def write_manifest(pin, out, title, attester, note_file, stamp=None) -> str:
    """The pin manifest exactly as the integrator's manifest tool writes it:
    a header naming the attester and the time, the pin line, the note, one
    `md5 bytes name` row for every file in <pin>/REVIEW-INPUT present BEFORE
    the manifest is copied in (never itself), then FILES n BYTES m; written to
    `out` and copied into the corpus. Returns the corpus path."""
    ri = os.path.join(pin, "REVIEW-INPUT")
    snap = snapshot(ri, skip=(os.path.basename(out),))
    _write_manifest(pin, out, _manifest_body(pin, title, attester, note_file, snap, stamp))
    return ri


def _write_manifest(pin, out, body):
    ri = os.path.join(pin, "REVIEW-INPUT")
    for dst in (out, os.path.join(ri, os.path.basename(out))):
        with open(dst, "wb") as f:
            f.write(body)


def _manifest_body(pin, title, attester, note_file, snap, stamp=None) -> bytes:
    """The manifest's bytes for one snapshot of REVIEW-INPUT."""
    head = _git(pin, "rev-parse", "HEAD").strip()
    stamp = stamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(note_file, encoding="utf-8") as f:
        note = f.read().strip()
    rows = sorted((rel, hashlib.md5(data).hexdigest(), len(data)) for rel, data in snap)
    total = sum(n for _r, _m, n in rows)
    lines = ["%s (%s, detached, %s)" % (title, attester, stamp),
             "pin %s HEAD %s, DETACHED AT THE SHA." % (pin, head),
             "INTEGRATOR NOTE: %s" % note, ""]
    lines += ["%s %d %s" % (m, n, r) for r, m, n in rows]
    lines.append("FILES %d BYTES %d" % (len(rows), total))
    return ("\n".join(lines) + "\n").encode("ascii")


def _inside(path, root) -> bool:
    a, b = os.path.realpath(path), os.path.realpath(root)
    try:
        return os.path.commonpath([a, b]) == b
    except ValueError:                      # different drives
        return False


def seal(pin, out, title, attester, note_file, seal_file, needles, stamp=None) -> dict:
    """One snapshot of the corpus, the manifest built from it, the armed scan
    of the snapshot plus the manifest, then the seal of those SAME bytes: the
    result line and their digest, outside the corpus."""
    ri = os.path.join(pin, "REVIEW-INPUT")
    if _inside(seal_file, ri):
        return {"refused": "seal_inside_corpus"}
    if _present(seal_file):
        return {"refused": "seal_exists"}
    name = os.path.basename(out)
    snap = snapshot(ri, skip=(name,))
    body = _manifest_body(pin, title, attester, note_file, snap, stamp)
    _write_manifest(pin, out, body)
    sealed = sorted(snap + [(name, body)])
    found = scan_snapshot(sealed, needles)
    line, _code = _report_line("seal", dict(found))
    rows = snapshot_rows(sealed)
    digest = corpus_digest(rows)
    body = ["SEAL %s" % digest, "RESULT %s" % line, "FILES %d" % len(rows)]
    body += ["%s %d %s" % (d, n, name) for name, n, d in rows]
    with open(seal_file, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(body) + "\n")
    found["seal"] = digest
    return found


def seal_verify(corpus, seal_file) -> dict:
    """{} when the corpus is byte for byte what the seal recorded, else the
    refusal naming the first difference."""
    try:
        with open(seal_file, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return {"refused": "seal_unreadable"}
    if len(lines) < 3 or not lines[0].startswith("SEAL ") or not lines[2].startswith("FILES "):
        return {"refused": "seal_malformed"}
    sealed = []
    for ln in lines[3:]:
        d, n, name = ln.split(" ", 2)
        sealed.append((name, int(n), d))
    if len(sealed) != int(lines[2].split()[1]) or corpus_digest(sealed) != lines[0].split()[1]:
        return {"refused": "seal_differs_from_its_digest"}
    now = corpus_rows(corpus)
    was, cur = {r[0]: r for r in sealed}, {r[0]: r for r in now}
    if set(cur) - set(was):
        return {"refused": "file_added"}
    if set(was) - set(cur):
        return {"refused": "file_removed"}
    if any(cur[k] != was[k] for k in was):
        return {"refused": "file_changed"}
    return {}


def _report_line(label, found, n=None):
    if "refused" in found:
        return "review_needles: %s refused (%s)" % (label, found["refused"]), 1
    manifest = found.pop("manifest", None)
    sealed = found.pop("seal", None)
    total = sum(found.values())
    detail = ", ".join("%s=%d" % (k, found[k]) for k in sorted(found)) or "none"
    return ("review_needles: %s %d found (%s)%s%s%s" % (
        label, total, detail, "" if n is None else " over %d commit(s)" % n,
        "" if manifest is None else " manifest " + manifest,
        "" if sealed is None else " seal " + sealed), 1 if total else 0)


def report(label, found, n=None):
    line, code = _report_line(label, found, n)
    print(line)
    return code


def main(argv):
    try:
        store = os.environ.get(STORE_ENV) or ""
        if not argv:
            print(__doc__.split("Modes:")[1].split("Exit 0")[0].rstrip())
            return 2
        if argv[0] == "seal-verify" and len(argv) == 3:
            try:
                return report("seal-verify", seal_verify(argv[1], argv[2]))
            except (NoVerdict, OSError) as e:
                print("review_needles: no verdict (%s): refused" % (
                    e if isinstance(e, NoVerdict) else type(e).__name__))
                return 3
        if not store:
            print("review_needles: unarmed (%s is unset): refused, nothing was scanned" % STORE_ENV)
            return 4
        try:
            needles = derive(store)
        except NoVerdict as e:
            print("review_needles: no verdict (store unreadable: %s): refused, nothing was scanned" % e)
            return 3
        try:
            return _dispatch(argv[0], argv[1:], needles)
        except (NoVerdict, OSError) as e:
            print("review_needles: no verdict (a read failed: %s): refused, no result" % (
                e if isinstance(e, NoVerdict) else type(e).__name__))
            return 3
    finally:
        if review_tripwire.verdict():
            return 3


def _dispatch(cmd, rest, needles):
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
    if cmd == "packet-verify" and len(rest) == 2:
        return report("packet-verify", packet_verify(rest[0], rest[1]))
    if cmd == "seal" and len(rest) == 6:
        return report("seal", seal(*rest, needles))
    print(__doc__.split("Modes:")[1].split("Exit 0")[0].rstrip())
    return 2


# A measure-parameter family keyed by deal profile identity (card_measures
# PROFILE_KEYED): review_rules.compile_rules admits one full value set per
# full-digest profile id there and no other object where a parameter stands.
# The id is a key the revision shares with the public deal profile; the value
# set holds the deciding values, derived as any family's are. Defined after
# _dispatch so the line-keyed pins of this module's earlier sites hold.
_PROFILE_ID = re.compile(r"[0-9a-f]{64}")


def _profile_values(fam, key, values, vals) -> bool:
    """One profile's value set into vals; the refusal for any other object."""
    if not (isinstance(key, str) and _PROFILE_ID.fullmatch(key)):
        raise NoVerdict("an object as a measure parameter")
    for k, v in values.items():
        if isinstance(v, dict):
            raise NoVerdict("an object as a profile-keyed measure parameter")
        vals.add(v, _keys(k) or _keys(str(fam).rsplit(".", 1)[-1]), str(fam), "measure parameter")
    return True


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
