"""Advisory review rules: loader, validator, evaluator, renderer.

The server can open advisory review items for the maintainer from recorded
match evidence. The rules it applies are server configuration that is not part
of this repository. Without them the server stores the evidence and opens
nothing. Review items never change a match result, a rating or a reward on
their own.

Mechanics (public): a rules REVISION is an immutable directory
`rules-<rev>` under the review root, named by its own framed digest, holding
`rules.json`, `selftest.json`, optional `data/` tables and `REVISION`. The
root's `current` pointer (a relative link, or a one-line file naming the
directory) selects the live revision. The loader bounds the inventory, the
bytes, the work and the wall time BEFORE parsing, recomputes the digest, binds
every referenced vocabulary entry by fingerprint (review_measures), runs the
revision's own self-test, and only then publishes the new state in one
assignment. The health word is the revision id, `absent` or `refused` and
nothing else; the refusal class goes to the log once per change.

Predicates are three-valued (Kleene): a measure that cannot be computed is
unknown, `not unknown` is unknown, and only TRUE fires. A rule that raises
counts as a rule error for that game and fires nothing.

Command line (the staging validator and the seat's build tool):
  python -m review_rules validate <revision dir>
  python -m review_rules build <draft dir> <store dir> <reason>
  python -m review_rules literal <revision dir> <rule id> <days back>
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import shutil
import stat
import sys
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal

import review_measures as rm

CONTRACT_BOUNDS = {
    "files_max": 64,
    "total_bytes_max": 16777216,
    "rules_bytes_max": 1048576,
    "selftest_bytes_max": 4194304,
    "data_bytes_max": 8388608,
    "rules_max": 200,
    "pred_depth_max": 6,
    "cases_max": 256,
    "work_max": 200000,
    "deadline_s": 10,
    "line_max": 400,
    "places_default": 3,
    "round_places": 4,
    "render_items_max": 6,
    "id_hex": 8,
    "rev_hex": 12,
    "nonce_bytes": 16,
    "digest_hex": 64,
    "data_name_max": 40,
    "pointer_bytes_max": 64,
    "frame_bytes": 8,
    "format": 1,
}
B = CONTRACT_BOUNDS

ROOT_ENV = "SCR_REVIEW_ROOT"
DEFAULT_ROOT = "/app/private/review"
POINTER = "current"
NONE_TARGET = "rules-none"
TOP_FILES = ("rules.json", "selftest.json", "REVISION")
DOMAIN = b"scr-review-rules-revision\n"

_HEX = re.compile(r"[a-f\d]+")
_REV_DIR = re.compile(r"rules-[a-f\d]{%d}" % B["rev_hex"])
_RULE_ID = re.compile(r"r[a-f\d]{%d}" % B["id_hex"])
_DATA_NAME = re.compile(r"[a-z_]{1,%d}\.(json|txt)" % B["data_name_max"])
_LABEL = re.compile(r"[a-z_]\w{0,%d}" % (rm.CONTRACT_BOUNDS["label_max"] * 2))
_STRATA = re.compile(r"[a-z_]{1,%d}" % rm.CONTRACT_BOUNDS["label_max"])
_PLACE = re.compile(r"\{([a-z_]\w*)(?::(\d))?(\|none)?\}")
RELS = ("gt", "ge", "lt", "le", "eq", "ne")


class Refused(Exception):
    """A revision the loader will not use; `cls` is the reason class."""

    def __init__(self, cls: str, detail: str = ""):
        super().__init__(cls + (": " + detail if detail else ""))
        self.cls = cls


class _WorkExceeded(Exception):
    pass


# -- revision identity ---------------------------------------------------------

def revision_digest(files: dict) -> str:
    """sha256 over a framed manifest: a domain tag, the file count, then per
    file (sorted by relative POSIX path) the path length, the path, the
    content length and the content. Lengths are fixed-width, so no two
    different inventories frame to the same bytes."""
    w = B["frame_bytes"]
    h = hashlib.sha256()
    h.update(DOMAIN)
    h.update(len(files).to_bytes(w, "big"))
    for path in sorted(files):
        p = path.encode("utf-8")
        c = files[path]
        h.update(len(p).to_bytes(w, "big"))
        h.update(p)
        h.update(len(c).to_bytes(w, "big"))
        h.update(c)
    return h.hexdigest()


def _check_time(deadline):
    if time.monotonic() > deadline:
        raise Refused("work", "deadline")


def _inventory(rdir: str, deadline: float) -> dict:
    """Every file of a revision, as bytes, after the shape and size bounds:
    regular files only, no links, `data/` the only subdirectory, names from a
    closed set, per-file and aggregate byte caps, a file-count cap and the
    deadline, all checked from lstat BEFORE anything is read or parsed."""
    try:
        st = os.lstat(rdir)
    except OSError as e:
        raise Refused("unreadable", type(e).__name__)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise Refused("inventory", "not a directory")
    plan = []
    try:
        for name in sorted(os.listdir(rdir)):
            _check_time(deadline)
            path = os.path.join(rdir, name)
            s = os.lstat(path)
            if stat.S_ISLNK(s.st_mode):
                raise Refused("inventory", "link")
            if name == "data":
                if not stat.S_ISDIR(s.st_mode):
                    raise Refused("inventory", "data")
                for dn in sorted(os.listdir(path)):
                    _check_time(deadline)
                    dp = os.path.join(path, dn)
                    ds = os.lstat(dp)
                    if (stat.S_ISLNK(ds.st_mode) or not stat.S_ISREG(ds.st_mode)
                            or not _DATA_NAME.fullmatch(dn)):
                        raise Refused("inventory", "data entry")
                    plan.append(("data/" + dn, dp, ds.st_size, B["data_bytes_max"]))
            elif name in TOP_FILES:
                if not stat.S_ISREG(s.st_mode):
                    raise Refused("inventory", "not a regular file")
                cap = {"rules.json": B["rules_bytes_max"],
                       "selftest.json": B["selftest_bytes_max"]}.get(name, B["digest_hex"] + 1)
                plan.append((name, path, s.st_size, cap))
            else:
                raise Refused("inventory", "unexpected entry")
            if len(plan) > B["files_max"]:
                raise Refused("inventory", "file count")
    except OSError as e:
        raise Refused("unreadable", type(e).__name__)
    if sum(p[2] for p in plan) > B["total_bytes_max"]:
        raise Refused("inventory", "aggregate bytes")
    for name in TOP_FILES:
        if name not in {p[0] for p in plan}:
            raise Refused("inventory", "missing " + name)
    files = {}
    for rel, path, size, cap in plan:
        _check_time(deadline)
        if size > cap:
            raise Refused("inventory", "file bytes")
        try:
            with open(path, "rb") as f:
                data = f.read(cap + 1)
        except OSError as e:
            raise Refused("unreadable", type(e).__name__)
        if len(data) > cap or len(data) != size:
            raise Refused("inventory", "file changed while read")
        files[rel] = data
    return files


# -- compiled rules ------------------------------------------------------------

class Rule:
    __slots__ = ("id", "scope", "subject", "when", "sitting", "effect", "post", "post_since",
                 "line", "show", "raw")


class Ruleset:
    """A loaded revision: compiled rules, bound entries, measure parameters."""

    def __init__(self):
        self.rev = None
        self.digest = None
        self.rules = []
        self.params = {}
        self.vocabulary = {}
        self.core = {}
        self.data = {}
        self.module_fps = {}

    @property
    def game_rules(self):
        return [r for r in self.rules if r.scope == "game"]

    @property
    def sitting_rules(self):
        return [r for r in self.rules if r.scope == "sitting"]

    def rule(self, rule_id):
        return next((r for r in self.rules if r.id == rule_id), None)

    # Evaluation always runs through the core entries the revision BOUND, so a
    # retained older core version keeps evaluating an older revision exactly.
    def evaluate_game(self, records, match, registry, module=None, budget=None):
        return self.core["core.game"].impl[0](self, records, match, registry, module, budget)

    def run_selftest(self, cases, deadline):
        return self.core["core.game"].impl[-1](self, cases, deadline)

    def render_line(self, rule, items):
        return self.core["core.render"].impl[0](rule, items)

    def sitting_items(self, rule, rows):
        return self.core["core.sitting"].impl[0](rule, rows)

    def sitting_statement(self, rule, mode="dirty"):
        return self.core["core.sitting"].impl[1](rule, mode)

    def horizon_days(self):
        """The widest window any sitting rule reads (None without sitting rules)."""
        days = [r.sitting[1]["window_days"] for r in self.sitting_rules]
        return max(days) if days else None


def _finite(v) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v))


class _Binder:
    """Resolves a vocabulary name for a revision. In load mode the revision's
    own `vocabulary` map names the fingerprint and review_measures.resolve
    finds the current or a retained version (else: stale). In build mode the
    current registry is bound and its fingerprint recorded."""

    def __init__(self, vocab, build=False):
        self.vocab = vocab
        self.build = build
        self.used = {}
        self.kinds = {}

    def __call__(self, name, kind=None):
        if not isinstance(name, str):
            raise Refused("malformed", "entry name")
        if name.startswith("module."):
            if self.build:
                fp = (self.vocab or {}).get(name)
                if not isinstance(fp, str) or len(fp) != B["digest_hex"]:
                    raise Refused("malformed", "module entry needs a bound fingerprint")
            else:
                fp = self.vocab.get(name)
                if not isinstance(fp, str) or len(fp) != B["digest_hex"] or not _HEX.fullmatch(fp):
                    raise Refused("malformed", "module entry binding")
            self.used[name] = fp
            self.kinds[name] = "module"
            return ("module", name, fp)
        if self.build:
            entry = rm.REGISTRY.get(name)
            if entry is None:
                raise Refused("malformed", "unknown entry")
        else:
            fp = self.vocab.get(name)
            if not isinstance(fp, str):
                raise Refused("malformed", "unbound entry")
            entry = rm.resolve(name, fp)
            if entry is None:
                raise Refused("stale", "entry fingerprint")
        if kind is not None and entry.kind not in ((kind,) if isinstance(kind, str) else kind):
            raise Refused("malformed", "entry kind")
        self.used[name] = entry.fp
        self.kinds[name] = entry.kind
        return entry


def _compile_expr(node, bind, subject):
    if not isinstance(node, dict) or len(node) != 1:
        raise Refused("malformed", "expression")
    (k, v), = node.items()
    if k == "m":
        e = bind(v, "measure") if not str(v).startswith("module.") else bind(v)
        if not isinstance(e, tuple):
            if e.subject != subject:
                raise Refused("malformed", "measure subject")
            if e.family is not None:
                bind(e.family, "params")
        return ("m", e)
    if k == "v":
        if not (_finite(v) or isinstance(v, (str, bool)) or v is None
                or (isinstance(v, list) and all(_finite(x) or isinstance(x, str) for x in v))):
            raise Refused("malformed", "literal")
        return ("v", v)
    if k in ("add", "sub"):
        if not isinstance(v, list) or len(v) != 2:
            raise Refused("malformed", "arithmetic")
        return (k, _compile_expr(v[0], bind, subject), _compile_expr(v[-1], bind, subject))
    if k == "abs":
        return ("abs", _compile_expr(v, bind, subject))
    raise Refused("malformed", "expression form")


def _compile_pred(node, bind, subject, data, depth=0):
    if depth > B["pred_depth_max"]:
        raise Refused("malformed", "predicate depth")
    if not isinstance(node, dict):
        raise Refused("malformed", "predicate")
    if set(node) == {"all"} or set(node) == {"any"}:
        (k, v), = node.items()
        if not isinstance(v, list) or not v:
            raise Refused("malformed", "predicate list")
        return (k, [_compile_pred(x, bind, subject, data, depth + 1) for x in v])
    if set(node) == {"not"}:
        return ("not", _compile_pred(node["not"], bind, subject, data, depth + 1))
    if set(node) == {"op", "args"}:
        entry = bind(node["op"], "operator")
        args = node["args"]
        if not isinstance(args, dict) or set(args) != {a for a, _ in entry.args}:
            raise Refused("malformed", "operator arguments")
        out = []
        for name, kind in entry.args:
            v = args[name]
            if kind == "expr":
                out.append(_compile_expr(v, bind, subject))
            elif kind == "rel":
                if v not in RELS:
                    raise Refused("malformed", "relation")
                out.append(("v", v))
            elif kind == "list":
                if isinstance(v, dict) and set(v) == {"data"}:
                    if v["data"] not in data:
                        raise Refused("malformed", "data table")
                    out.append(("v", data[v["data"]]))
                elif isinstance(v, list) and all(_finite(x) or isinstance(x, str) for x in v):
                    out.append(("v", v))
                else:
                    raise Refused("malformed", "list argument")
            else:
                raise Refused("malformed", "argument kind")
        return ("op", entry, out)
    raise Refused("malformed", "predicate form")


def _compile_template(line, labels):
    if not isinstance(line, str) or len(line) > B["line_max"]:
        raise Refused("malformed", "line")
    parts, pos = [], 0
    for m in _PLACE.finditer(line):
        lit = line[pos:m.start()]
        if "{" in lit or "}" in lit:
            raise Refused("malformed", "line brace")
        parts.append(lit)
        label, places, none = m.groups()
        if label not in labels:
            raise Refused("malformed", "line placeholder")
        parts.append((label, int(places) if places else B["places_default"], bool(none)))
        pos = m.end()
    tail = line[pos:]
    if "{" in tail or "}" in tail:
        raise Refused("malformed", "line brace")
    parts.append(tail)
    return parts


def _compile_sitting(node, bind0):
    if not isinstance(node, dict) or set(node) != {"op", "args"}:
        raise Refused("malformed", "sitting")
    refs = {}

    def bind(name, kind=None):
        e = bind0(name, kind)
        refs[name] = e
        return e

    entry = bind(node["op"], "sitting")
    args = node["args"]
    if not isinstance(args, dict) or set(args) != {a for a, _ in entry.args}:
        raise Refused("malformed", "sitting arguments")
    out = {}
    for name, kind in entry.args:
        v = args[name]
        if kind in ("side", "row", "reporter"):
            bind(v, kind)
        elif kind == "filters":
            if not isinstance(v, list) or len(set(v)) != len(v):
                raise Refused("malformed", "filters")
            for f in v:
                bind(f, "population")
        elif kind == "int":
            if not (_finite(v) and isinstance(v, int)) or v < 0:
                raise Refused("malformed", "int argument")
        elif kind == "num":
            if not _finite(v):
                raise Refused("malformed", "num argument")
        elif kind == "edges":
            if (not isinstance(v, list) or not v or len(v) > rm.CONTRACT_BOUNDS["edges_max"]
                    or not all(_finite(x) for x in v) or sorted(v) != v):
                raise Refused("malformed", "edges")
        elif kind == "label":
            if not isinstance(v, str) or not _STRATA.fullmatch(v):
                raise Refused("malformed", "label")
        out[name] = v
    if "window_days" not in out or out["window_days"] < 1:
        raise Refused("malformed", "window")
    for mode in ("dirty", "days_back"):
        entry.impl[0](out, _bound_lookup(refs), mode)
    return (entry, out, refs)


def _bound_lookup(refs):
    """SQL data entries exactly as the revision bound them (current or
    retained), never a later version under the same name."""
    def R(name, kind):
        e = refs[name]
        if e.kind != kind:
            raise KeyError(name)
        return e
    return R


def _parse_time(v):
    if v is None:
        return None
    if not isinstance(v, str):
        raise Refused("malformed", "post_since")
    try:
        t = datetime.fromisoformat(v[:-1] if v.endswith("Z") else v)
        if v.endswith("Z") and t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    except ValueError:
        raise Refused("malformed", "post_since")
    if t.tzinfo is None:
        raise Refused("malformed", "post_since zone")
    return t


RULE_KEYS = {"id", "scope", "effect", "post", "post_since", "line", "show"}


def compile_rules(doc, bind, data) -> Ruleset:
    """Validate and compile a parsed rules.json under `bind`."""
    if not isinstance(doc, dict) or set(doc) != {"format", "nonce", "vocabulary",
                                                 "measure_params", "rules"}:
        raise Refused("malformed", "top level")
    if doc["format"] != B["format"]:
        raise Refused("malformed", "format")
    nonce = doc["nonce"]
    if (not isinstance(nonce, str) or len(nonce) != B["nonce_bytes"] * 2
            or not _HEX.fullmatch(nonce)):
        raise Refused("malformed", "nonce")
    if not isinstance(doc["vocabulary"], dict):
        raise Refused("malformed", "vocabulary")
    rs = Ruleset()
    rs.data = data
    params = doc["measure_params"]
    if not isinstance(params, dict):
        raise Refused("malformed", "measure_params")
    for family, values in params.items():
        entry = bind(family, "params")
        if (not isinstance(values, dict) or set(values) != set(entry.data)
                or not all(_finite(x) for x in values.values())):
            raise Refused("malformed", "measure_params values")
        rs.params[family] = dict(values)
    rules = doc["rules"]
    if not isinstance(rules, list) or len(rules) > B["rules_max"]:
        raise Refused("malformed", "rules")
    seen = set()
    for raw in rules:
        if not isinstance(raw, dict):
            raise Refused("malformed", "rule")
        r = Rule()
        r.raw = raw
        r.id = raw.get("id")
        if not isinstance(r.id, str) or not _RULE_ID.fullmatch(r.id) or r.id in seen:
            raise Refused("malformed", "rule id")
        seen.add(r.id)
        r.scope = raw.get("scope")
        r.effect = raw.get("effect")
        r.post = raw.get("post")
        if r.effect not in ("flag", "note") or not isinstance(r.post, bool):
            raise Refused("malformed", "effect or post")
        r.post_since = _parse_time(raw.get("post_since"))
        show = raw.get("show")
        if (not isinstance(show, list) or not show or len(show) > rm.CONTRACT_BOUNDS["show_max"]
                or not all(isinstance(s, list) and len(s) == 2
                           and isinstance(s[0], str) and _LABEL.fullmatch(s[0]) for s in show)
                or len({s[0] for s in show}) != len(show)):
            raise Refused("malformed", "show")
        if r.scope == "game":
            if set(raw) != RULE_KEYS | {"subject", "when"}:
                raise Refused("malformed", "rule keys")
            r.subject = raw["subject"]
            if r.subject not in ("seat", "game"):
                raise Refused("malformed", "subject")
            r.when = _compile_pred(raw["when"], bind, r.subject, data)
            r.sitting = None
            r.show = [(s[0], _compile_expr({"m": s[1]}, bind, r.subject)[1]) for s in show]
        elif r.scope == "sitting":
            if set(raw) != RULE_KEYS | {"sitting"}:
                raise Refused("malformed", "rule keys")
            r.subject = None
            r.when = None
            r.sitting = _compile_sitting(raw["sitting"], bind)
            outputs = r.sitting[0].outputs
            if not all(s[1] in outputs for s in show):
                raise Refused("malformed", "sitting show")
            r.show = [(s[0], s[1]) for s in show]
        else:
            raise Refused("malformed", "scope")
        r.line = _compile_template(raw["line"], {s[0] for s in show})
        rs.rules.append(r)
    for name in CORE_ENTRIES:
        rs.core[name] = bind(name, "core")
    families = {n for n, k in bind.kinds.items() if k == "params"}
    if not families <= set(rs.params):
        raise Refused("malformed", "measure_params missing a family a measure needs")
    return rs


# -- evaluation (the bound core entries run it) ---------------------------------

class _Budget:
    def __init__(self, limit):
        self.left = limit

    def tick(self):
        self.left -= 1
        if self.left < 0:
            raise _WorkExceeded()


def _measure_value(m, ctx, memo, rs):
    if isinstance(m, tuple):          # a module measure (choice two; absent here)
        _kind, name, fp = m
        mod = ctx.module
        if mod is None or mod.fingerprint(name) != fp:
            return None
        return mod.compute(name, ctx, rs.params.get(name, {}))
    key = (m.name, ctx.i)
    if key not in memo:
        fam = rs.params.get(m.family) if m.family else None
        memo[key] = None if (m.family and fam is None) else m.impl[0](ctx, fam)
    return memo[key]


def eval_expr(node, ctx, memo, rs):
    k = node[0]
    if k == "m":
        return _measure_value(node[1], ctx, memo, rs)
    if k == "v":
        return node[1]
    if k == "abs":
        v = eval_expr(node[1], ctx, memo, rs)
        return None if v is None else abs(rm._num(v))
    a = eval_expr(node[1], ctx, memo, rs)
    b = eval_expr(node[2], ctx, memo, rs)
    if a is None or b is None:
        return None
    return rm._num(a) + rm._num(b) if k == "add" else rm._num(a) - rm._num(b)


def eval_pred(node, ctx, memo, rs, budget):
    k = node[0]
    if k == "not":
        v = eval_pred(node[1], ctx, memo, rs, budget)
        return None if v is None else not v
    if k in ("all", "any"):
        vals = [eval_pred(x, ctx, memo, rs, budget) for x in node[1]]
        stop, go = (False, True) if k == "all" else (True, False)
        if any(v is stop for v in vals):
            return stop
        if any(v is None for v in vals):
            return None
        return go
    if budget is not None:
        budget.tick()
    entry, args = node[1], node[2]
    vals = [eval_expr(a, ctx, memo, rs) for a in args]
    out = entry.impl[0](*vals)
    if out is not None and not isinstance(out, bool):
        raise TypeError("an operator answered something other than true, false or unknown")
    return out


def evaluate_game(rs, records, match, registry, module=None, budget=None):
    """Every game rule of `rs` over one game's records (one or two). Returns
    (findings, fired, errors): findings are (rule, details) for flag rules
    that fired on at least one subject, with the rendered lines of any note
    rule that fired attached; fired is every rule id that fired."""
    cache = {}
    seats = [rm.Ctx(records, i, match, registry, rs.params, cache, module)
             for i in range(len(records))]
    game = [rm.Ctx(records, None, match, registry, rs.params, cache, module)]
    memo = {}
    findings, notes, fired, errors = [], [], [], 0
    for rule in rs.game_rules:
        subjects = seats if rule.subject == "seat" else game
        try:
            items = []
            for ctx in subjects:
                if eval_pred(rule.when, ctx, memo, rs, budget) is True:
                    items.append({label: _measure_value(m, ctx, memo, rs) for label, m in rule.show})
        except _WorkExceeded:
            raise
        except Exception:                 # noqa: BLE001 -- one rule cannot stop another
            errors += 1
            continue
        if not items:
            continue
        fired.append(rule.id)
        if rule.effect == "flag":
            findings.append((rule, {"items": items}))
        else:
            notes.append(rs.render_line(rule, items))
    if notes:
        for _rule, det in findings:
            det["notes"] = list(notes)
    return findings, fired, errors


def _render_value(v, places):
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return "%.*f" % (places, v)
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "/".join(_render_value(x, places) for x in v)
    return str(v)


def render_item(parts, item):
    out = []
    for p in parts:
        if isinstance(p, str):
            out.append(p)
            continue
        label, places, none = p
        v = item.get(label)
        out.append("none" if (none and v is None) else _render_value(v, places))
    return "".join(out)


def render_line(rule, items) -> str:
    """The rule's wording over a finding's items: numbers and recorded text
    only, one line per item, at most the render bound of items."""
    return "\n".join(render_item(rule.line, it)
                     for it in list(items)[: B["render_items_max"]] if isinstance(it, dict))


def norm_pair(a, b):
    return (a, b) if str(a) < str(b) else (b, a)


def _py(v):
    if isinstance(v, Decimal):
        v = int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, float):
        return round(v, B["round_places"])
    if not isinstance(v, (int, str, type(None))):
        return str(v)
    return v


def sitting_items(rule, rows):
    """Rows of one sitting rule grouped per normalized (pair, UTC day): both
    seats of a sitting can meet a rule and share ONE finding, the lower id's
    item first. Returns [(dedup_key, last match id, items)]."""
    grouped = {}
    for r in rows:
        lo, hi = norm_pair(r["subject"], r["opponent"])
        det = {"subject_is_lo": str(r["subject"]) == str(lo)}
        for label, col in rule.show:
            det[label] = _py(r[col])
        dedup = "%s|%s|%s" % (lo, hi, r["d"])
        slot = grouped.setdefault(dedup, {"mid": r["last_mid"], "items": []})
        slot["items"].append(det)
    return [(k, grouped[k]["mid"], sorted(grouped[k]["items"], key=lambda d: not d["subject_is_lo"]))
            for k in sorted(grouped)]


def sitting_statement(rule, mode="dirty"):
    """The bound sitting operator's SQL text and binds for one rule."""
    entry, args, refs = rule.sitting
    sql = entry.impl[0](args, _bound_lookup(refs), mode)
    return sql, rm.sitting_binds(entry, args)


def run_selftest(rs, cases, deadline):
    """Each synthetic case must fire exactly the rule ids it lists."""
    budget = _Budget(B["work_max"])
    for case in cases:
        _check_time(deadline)
        if not isinstance(case, dict) or set(case) != {"records", "match", "registry", "fire"}:
            raise Refused("malformed", "selftest case")
        registry = {tuple(t) for t in case["registry"]}
        try:
            _f, fired, errors = rs.evaluate_game(case["records"], case["match"], registry,
                                                 budget=budget)
        except _WorkExceeded:
            raise Refused("work", "selftest work")
        if errors or sorted(fired) != sorted(case["fire"]):
            raise Refused("selftest")
    _check_time(deadline)


CORE_ENTRIES = ("core.game", "core.render", "core.sitting")


def _register_core():
    rm._register(rm.Entry("core", "core.game", (evaluate_game, eval_pred, eval_expr,
                                                _measure_value, run_selftest)))
    rm._register(rm.Entry("core", "core.render", (render_line, render_item, _render_value)))
    rm._register(rm.Entry("core", "core.sitting", (sitting_items, sitting_statement, norm_pair,
                                                   _py, _bound_lookup)))


if __name__ != "__main__" and "core.game" not in rm.REGISTRY:
    _register_core()


def review_eval() -> str:
    return rm.review_eval()


# -- loading -------------------------------------------------------------------

def _no_constants(text):
    raise ValueError("non-finite number")


def load_dir(rdir: str, *, deadline: float | None = None) -> Ruleset:
    """Validate one revision directory completely. Raises Refused(cls)."""
    if deadline is None:
        deadline = time.monotonic() + B["deadline_s"]
    base = os.path.basename(os.path.normpath(rdir))
    if not _REV_DIR.fullmatch(base):
        raise Refused("inventory", "directory name")
    files = _inventory(rdir, deadline)
    digest = revision_digest({k: v for k, v in files.items() if k != "REVISION"})
    stated = files["REVISION"].decode("ascii", "replace").strip()
    if stated != digest or base != "rules-" + digest[: B["rev_hex"]]:
        raise Refused("digest")
    try:
        doc = json.loads(files["rules.json"].decode("utf-8"), parse_constant=_no_constants)
        selftest = json.loads(files["selftest.json"].decode("utf-8"), parse_constant=_no_constants)
        data = {}
        for rel, raw in files.items():
            if rel.startswith("data/"):
                name, ext = rel.split("/", 1)[1].rsplit(".", 1)
                text = raw.decode("utf-8")
                data[name] = json.loads(text) if ext == "json" else [
                    ln for ln in text.splitlines() if ln.strip()]
    except (ValueError, UnicodeDecodeError):
        raise Refused("malformed", "json")
    _check_time(deadline)
    binder = _Binder(doc.get("vocabulary") if isinstance(doc, dict) else None)
    if not isinstance(binder.vocab, dict):
        raise Refused("malformed", "vocabulary")
    rs = compile_rules(doc, binder, data)
    if set(binder.used) != set(binder.vocab):
        raise Refused("malformed", "vocabulary is not exactly the entries used")
    if (not isinstance(selftest, dict) or set(selftest) != {"cases"}
            or not isinstance(selftest["cases"], list) or len(selftest["cases"]) > B["cases_max"]):
        raise Refused("malformed", "selftest")
    rs.run_selftest(selftest["cases"], deadline)
    rs.rev = digest[: B["rev_hex"]]
    rs.digest = digest
    rs.vocabulary = dict(binder.vocab)
    return rs


class State:
    __slots__ = ("word", "ruleset", "reason")

    def __init__(self, word, ruleset=None, reason=None):
        self.word = word
        self.ruleset = ruleset
        self.reason = reason


_STATE = State("absent")
_KEY = None
_LOCK = threading.Lock()
_LOGGED = None


def root() -> str:
    return os.environ.get(ROOT_ENV) or DEFAULT_ROOT


def _pointer_target(base):
    p = os.path.join(base, POINTER)
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(st.st_mode):
        target = os.readlink(p)
    elif stat.S_ISREG(st.st_mode) and st.st_size <= B["pointer_bytes_max"]:
        with open(p, "rb") as f:
            target = f.read(B["pointer_bytes_max"]).decode("ascii", "replace").strip()
    else:
        raise Refused("pointer")
    if target == NONE_TARGET:
        return None
    if not _REV_DIR.fullmatch(target):
        raise Refused("pointer")
    return target


def _log(state):
    global _LOGGED
    sig = (state.word, state.reason)
    if sig != _LOGGED:
        _LOGGED = sig
        if state.word == "refused":
            print("[REVIEW] rules: refused (%s)" % state.reason, flush=True)
        else:
            print("[REVIEW] rules: %s" % state.word, flush=True)


def refresh() -> State:
    """Re-read the pointer; when it or its target changed, validate the new
    target completely and publish the outcome in one assignment. A load in
    progress elsewhere answers the state already published."""
    global _STATE, _KEY
    if not _LOCK.acquire(blocking=False):
        return _STATE
    try:
        base = root()
        try:
            target = _pointer_target(base)
            if target is None:
                key = ("absent",)
            else:
                st = os.lstat(os.path.join(base, target))
                key = (target, st.st_mtime_ns, st.st_ino)
        except FileNotFoundError:
            key = ("missing",)
            target = ""
        except (Refused, OSError) as e:
            key = ("pointer", type(e).__name__)
            target = ""
        if key == _KEY:
            return _STATE
        if key == ("absent",):
            new = State("absent")
        elif key[0] in ("missing", "pointer"):
            new = State("refused", reason="pointer")
        else:
            try:
                rs = load_dir(os.path.join(base, target))
                new = State(rs.rev, rs)
            except Refused as e:
                new = State("refused", reason=e.cls)
            except Exception as e:            # noqa: BLE001 -- any other failure refuses
                new = State("refused", reason="error:" + type(e).__name__)
        _STATE = new
        _KEY = key
        _log(new)
        return new
    finally:
        _LOCK.release()


def current() -> State:
    return _STATE


def health_word() -> str:
    return _STATE.word


# -- the seat's tools ----------------------------------------------------------

def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def build(draft: str, store: str, reason: str) -> str:
    """Canonicalise a draft into a new immutable revision in `store`: a fresh
    nonce, the bound vocabulary, the framed digest; validated in a disposable
    incoming directory and renamed into place only when it loads. Appends one
    line to REVISIONS.tsv and returns the revision id."""
    with open(os.path.join(draft, "rules.json"), "rb") as f:
        doc = json.loads(f.read().decode("utf-8"))
    with open(os.path.join(draft, "selftest.json"), "rb") as f:
        selftest = json.loads(f.read().decode("utf-8"))
    data_files = {}
    ddir = os.path.join(draft, "data")
    if os.path.isdir(ddir):
        for dn in sorted(os.listdir(ddir)):
            with open(os.path.join(ddir, dn), "rb") as f:
                data_files["data/" + dn] = f.read()
    doc = dict(doc)
    doc["nonce"] = secrets.token_hex(B["nonce_bytes"])
    module_vocab = {k: v for k, v in (doc.get("vocabulary") or {}).items() if k.startswith("module.")}
    doc["vocabulary"] = {}
    data = {}
    for rel, raw in data_files.items():
        name, ext = rel.split("/", 1)[1].rsplit(".", 1)
        text = raw.decode("utf-8")
        data[name] = json.loads(text) if ext == "json" else [ln for ln in text.splitlines() if ln.strip()]
    binder = _Binder(module_vocab, build=True)
    compile_rules(doc, binder, data)
    doc["vocabulary"] = dict(sorted(binder.used.items()))
    files = {"rules.json": _canon(doc), "selftest.json": _canon(selftest)}
    files.update(data_files)
    digest = revision_digest(files)
    rev = digest[: B["rev_hex"]]
    final = os.path.join(store, "rules-" + rev)
    if os.path.exists(final):
        raise FileExistsError(final)
    incoming = os.path.join(store, ".incoming-" + secrets.token_hex(B["id_hex"] // 2))
    os.makedirs(os.path.join(incoming, "data") if data_files else incoming)
    try:
        for rel, raw in files.items():
            with open(os.path.join(incoming, *rel.split("/")), "wb") as f:
                f.write(raw)
        with open(os.path.join(incoming, "REVISION"), "wb") as f:
            f.write((digest + "\n").encode())
        staged = os.path.join(store, ".validate-" + secrets.token_hex(B["id_hex"] // 2), "rules-" + rev)
        os.makedirs(os.path.dirname(staged))
        os.rename(incoming, staged)
        try:
            load_dir(staged)
            os.rename(staged, final)
        finally:
            if os.path.exists(staged):
                shutil.rmtree(staged)
            os.rmdir(os.path.dirname(staged))
    finally:
        if os.path.exists(incoming):
            shutil.rmtree(incoming)
    parent = ""
    log = os.path.join(store, "REVISIONS.tsv")
    if os.path.exists(log):
        with open(log, encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        if lines:
            parent = lines[-1].split("\t")[0]
    with open(log, "a", encoding="utf-8", newline="\n") as f:
        f.write("%s\t%s\t%s\t%s\t\n" % (rev, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        parent, reason.replace("\t", " ").replace("\n", " ")))
    return rev


def literal(rdir: str, rule_id: str, days_back: int) -> str:
    """One sitting rule as ONE statement with its values written in (no
    binds), scoped to the days back from today: the tuning tool's form for
    the read-only wrapper. Its output stays on the seat."""
    rs = load_dir(rdir)
    rule = rs.rule(rule_id)
    if rule is None or rule.scope != "sitting":
        raise KeyError(rule_id)
    sql, binds = rs.sitting_statement(rule, "days_back")
    binds["days_back"] = int(days_back)
    for k in sorted(binds, key=len, reverse=True):
        v = binds[k]
        lit = ("'%s'" % v) if isinstance(v, str) else repr(v)
        sql = re.sub(r":%s\b" % re.escape(k), lit, sql)
    return " ".join(sql.split())


def cli(argv) -> int:
    cmd, rest = (argv[0], list(argv[1:])) if argv else ("", [])
    if cmd == "validate" and len(rest) == 1:
        try:
            rs = load_dir(rest[0])
            print("verdict: loaded")
            print("rev: " + rs.rev)
            code = 0
        except Refused as e:
            print("verdict: refused (%s)" % e.cls)
            print("rev: none")
            code = 1
        print("eval: " + review_eval())
        return code
    if cmd == "build" and rest:
        draft, store, reason = rest
        try:
            print(build(draft, store, reason))
            return 0
        except Refused as e:
            print("refused (%s)" % e.cls)
            return 1
    if cmd == "literal" and rest:
        rdir, rule_id, days = rest
        print(literal(rdir, rule_id, int(days)))
        return 0
    print(__doc__.split("Command line")[1].strip())
    return 2


if __name__ == "__main__":
    import review_rules as _self
    sys.exit(_self.cli(sys.argv[1:]))
