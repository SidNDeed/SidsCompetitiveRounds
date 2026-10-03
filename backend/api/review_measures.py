"""Public review vocabulary: measures and operators.

A MEASURE describes what stored seat records and match rows say (a count, a
stamp difference, a stated build). An OPERATOR is a generic comparison. Neither
opens anything. Only a rule in the private rules revision (review_rules) turns
a description into a review item, and every value such a decision depends on
is a parameter that revision supplies. This module holds no such value; the
no-tunables guard (backend/tools/review_guard.py) refuses one here, whether it
is written inline, hoisted, imported, or carried in text.

Every entry has a semantic FINGERPRINT over its implementation and over the
implementations and constants it references. A revision binds the
fingerprint of every entry it uses, so a changed implementation makes a
revision built against the old one stale (refused) instead of silently
reinterpreted. BRIDGE holds older entry versions a live revision may still
bind while both builds are deployed; an entry leaves BRIDGE only once no
staged revision uses it.

Sitting operators are SQL templates over the measure registry. Every number
in them is a typed bind (CAST(:x AS ...), make_interval); no LATERAL.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import textwrap

# Public contract bounds (the guard pins each name and value).
CONTRACT_BOUNDS = {
    "ready_lag_s": 120,
    "edges_max": 8,
    "label_max": 16,
    "show_max": 16,
    "eval_hex": 8,
}

# Which raised-block kinds open a window: a fact of the client contract.
WINDOW_KINDS = (0, 2, 3)

FINGERPRINT_MODULES = ("review_measures", "review_rules", "review_module", "combat_measures")

# The subjects a combat rule evaluates over (combat_measures builds their rows).
COMBAT_SUBJECTS = ("combat.direction", "combat.cycle", "combat.shot", "combat.refill",
                   "combat.stat", "combat.point", "combat.block", "combat.contact",
                   "combat.top", "combat.aim", "combat.push", "combat.vchange",
                   "combat.bounce", "combat.chain", "combat.death", "combat.regen",
                   "combat.b3", "combat.tbounce", "combat.homing", "combat.react",
                   "combat.interval", "combat.refused", "combat.record")

REGISTRY: dict = {}
BRIDGE: dict = {}


class Entry:
    """One vocabulary entry. kind: measure | operator | side | row | reporter
    | population | sitting | params | core."""

    __slots__ = ("kind", "name", "impl", "subject", "family", "args", "outputs", "data", "_fp")

    def __init__(self, kind, name, impl=(), *, subject=None, family=None, args=(),
                 outputs=(), data=None):
        self.kind = kind
        self.name = name
        self.impl = tuple(impl)
        self.subject = subject
        self.family = family
        self.args = tuple(args)
        self.outputs = tuple(outputs)
        self.data = data
        self._fp = None

    @property
    def fp(self) -> str:
        if self._fp is None:
            self._fp = entry_fingerprint(self)
        return self._fp


def _register(entry: Entry) -> Entry:
    if entry.name in REGISTRY:
        raise ValueError("duplicate review vocabulary entry: " + entry.name)
    REGISTRY[entry.name] = entry
    return entry


def resolve_entry(name: str, fp: str):
    """The entry a revision bound: the current one if its fingerprint matches,
    else a retained BRIDGE version, else None (the revision is stale)."""
    cur = REGISTRY.get(name)
    if cur is not None and cur.fp == fp:
        return cur
    return BRIDGE.get((name, fp))


# -- semantic fingerprints -----------------------------------------------------

def _simple(v) -> bool:
    if v is None or isinstance(v, (bool, int, float, str)):
        return True
    if isinstance(v, (tuple, list, frozenset)):
        return all(_simple(x) for x in v)
    if isinstance(v, dict):
        return all(isinstance(k, str) and _simple(x) for k, x in v.items())
    return False


def _const_tag(v) -> str:
    text = json.dumps(v if not isinstance(v, frozenset) else sorted(v), sort_keys=True, default=repr)
    return "const_" + type(v).__name__ + "_" + hashlib.sha256(text.encode()).hexdigest()


def _fn_dump(fn, seen) -> str:
    node = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]
    node.decorator_list = []
    node.name = "fn"
    body = node.body
    if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        node.body = body[1:] or [ast.Pass()]
    names = fn.__globals__

    class _Refs(ast.NodeTransformer):
        def visit_Name(self, n):
            if isinstance(n.ctx, ast.Load) and n.id in names:
                tag = _ref_tag(names[n.id], seen)
                if tag is not None:
                    return ast.copy_location(ast.Name(id=tag, ctx=ast.Load()), n)
            return n

    return ast.dump(_Refs().visit(node), include_attributes=False)


def _ref_tag(v, seen):
    if inspect.isfunction(v) and v.__module__ in FINGERPRINT_MODULES:
        return "fn_" + _fn_fp(v, seen)
    if _simple(v):
        return _const_tag(v)
    return None


def _fn_fp(fn, seen=frozenset()) -> str:
    if fn in seen:
        return "cycle"
    return hashlib.sha256(_fn_dump(fn, seen | {fn}).encode()).hexdigest()


def entry_fingerprint(e: Entry) -> str:
    """Canonical over kind, name, declared signature, data and the normalised
    implementation of every function the entry runs: a comment or a rename
    leaves it unchanged; any change to what the entry computes moves it."""
    doc = {"kind": e.kind, "name": e.name, "subject": e.subject, "family": e.family,
           "args": [list(a) if isinstance(a, tuple) else a for a in e.args],
           "outputs": list(e.outputs), "data": e.data,
           "impl": [_fn_fp(f) for f in e.impl]}
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()


def entry_manifest() -> list:
    """Sorted (name, fingerprint) of every current entry and every retained
    BRIDGE version."""
    rows = {(n, e.fp) for n, e in REGISTRY.items()}
    rows |= set(BRIDGE.keys())
    return sorted(rows)


def review_eval() -> str:
    """The public vocabulary's digest: derived on every call."""
    text = "\n".join("%s %s" % r for r in entry_manifest())
    return hashlib.sha256(text.encode()).hexdigest()[: CONTRACT_BOUNDS["eval_hex"]]


# -- registration helpers ------------------------------------------------------

def measure(name, subject, family=None):
    def deco(fn):
        _register(Entry("measure", name, (fn,), subject=subject, family=family))
        return fn
    return deco


def operator(name, args):
    def deco(fn):
        _register(Entry("operator", name, (fn,), args=args))
        return fn
    return deco


def sitting_operator(name, args, outputs):
    def deco(fn):
        _register(Entry("sitting", name, (fn,), args=args, outputs=outputs))
        return fn
    return deco


def _param_family(name, keys):
    _register(Entry("params", name, data=list(keys)))


def _sitting_sql(kind, name, *parts):
    _register(Entry(kind, name, data=list(parts)))


# -- small helpers on the record lists ----------------------------------------

def wrap_diff(a: int, b: int) -> int:
    """a minus b on the wrapping int32 Photon clock."""
    return ((a - b + 2 ** 31) % 2 ** 32) - 2 ** 31


def median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) // 2


# -- parameterised descriptions (parameters come only from a revision) ----------

_param_family("params.case_table", ("pair_lo_ms", "pair_hi_ms", "late_margin_ms", "window_ms"))
_param_family("params.one_record", ("due_margin_ms", "due_hi_ms", "edge_span_ms", "own_window_ms"))
_param_family("params.age_sum", ("budget_slack_ms",))
_param_family("params.blocks_missing", ("in_flight_ms",))


def classify_blocks(victim: dict, shooter, p: dict) -> dict:
    """The block case table for blocks the VICTIM raised. With no shooter
    record only the one-record reading exists. `p` is params.case_table."""
    hits = [h for h in victim["hit_recv"] if h[6] == 1]
    counts = {k: 0 for k in ("honoured", "unhonoured", "a", "b", "c", "expired",
                             "other_window", "disagree", "incomplete", "hit_unmatched",
                             "no_hit", "late_single")}
    rows = []
    b_faults = shooter["blk_faults"] if shooter else None
    if shooter is not None:
        recv = {(e[0], e[1], e[2]): e for e in shooter["blk_recv"]}
        sent = {(e[0], e[1], e[2], e[3]): e for e in shooter["hit_sent"]}
        s_age = max(shooter["age"]["blk"][0], shooter["age"]["rpc"][0])
    for blk in victim["blk_sent"]:
        tb, kind, ordv = blk[0], blk[1], blk[2]
        if kind not in WINDOW_KINDS:
            continue
        h = None
        for cand in hits:
            d = wrap_diff(cand[1], tb)
            if p["pair_lo_ms"] <= d <= p["pair_hi_ms"] and (h is None or wrap_diff(cand[1], h[1]) < 0):
                h = cand
        if h is None:
            counts["no_hit"] += 1
            continue
        d = wrap_diff(h[1], tb)
        if h[5] == 1:
            counts["honoured"] += 1
            rows.append({"tb": tb, "d": d, "cls": "honoured"})
            continue
        counts["unhonoured"] += 1
        if shooter is None:
            rows.append({"tb": tb, "d": d, "cls": "unhonoured"})
            continue
        hs = sent.get((h[0], h[1], h[2], h[3]))
        br = recv.get((tb, kind, ordv))
        if hs is None:
            cls = "incomplete" if shooter["omit"]["hit_sent"] else "hit_unmatched"
        elif br is None:
            cls = "incomplete" if shooter["omit"]["blk_recv"] else "disagree"
        elif wrap_diff(hs[1], br[3]) < 0:
            cls = "a"
            if wrap_diff(br[3], tb) > s_age + p["late_margin_ms"]:
                counts["late_single"] += 1
        elif br[4] == 0:
            cls = "b"
        elif (hs[6], hs[7], hs[8]) == (tb, kind, ordv):
            if hs[4] >= p["window_ms"]:
                cls = "expired"
            elif hs[5] == 0 and 0 <= hs[4] < p["window_ms"]:
                cls = "c"
            else:
                cls = "disagree"     # the shooter's own decision contradicts its relayed flag
        else:
            cls = "other_window"
        counts[cls] += 1
        row = {"tb": tb, "d": d, "cls": cls}
        if br is not None:
            row["ta_minus_tb"] = wrap_diff(br[3], tb)
        if cls == "b":
            row["faults"] = b_faults
        rows.append(row)
    return {"counts": counts, "rows": rows, "blk_faults": b_faults}


def one_record_view(victim: dict, shooter, two_way_l, p_case: dict, p_one: dict) -> dict:
    """The honour edge as an OBSERVED UPPER BOUND: the smallest stamp gap among
    honoured hits. Its uncertainty is the clock and asymmetry bound; the
    shooter-side extra delay is unknown without the shooter's own record.
    `p_case` is params.case_table, `p_one` params.one_record."""
    table = classify_blocks(victim, None, p_case)
    honoured = [r["d"] for r in table["rows"] if r["cls"] == "honoured"]
    unh = [r["d"] for r in table["rows"] if r["cls"] == "unhonoured"]
    rtt_v = victim["rtt"][0]
    if shooter is not None:
        rtt_s, rtt_src = shooter["rtt"][0], "shooter_record"
    elif victim["other_pub"] is not None:
        rtt_s, rtt_src = victim["other_pub"][1], "relayed_self_statement"
    else:
        rtt_s, rtt_src = None, "unknown"
    if two_way_l is not None:
        l_hat, l_src = two_way_l, "half_reciprocal_age_sum"
    else:
        l_hat, l_src = victim["age"]["hit"][0], "one_direction_age_hit_median"
    edge = min(honoured) if honoured else None
    out = {
        "honour_edge_ms": edge,
        "honour_edge_label": "observed_upper_bound",
        "honoured_n": len(honoured),
        "uncertainty_ms": None if rtt_s is None else (rtt_v + rtt_s) // 2,
        "uncertainty_rtt_source": rtt_src,
        "l_hat_ms": l_hat, "l_hat_source": l_src,
        "due": sum(1 for d in unh if l_hat + p_one["due_margin_ms"] <= d <= p_one["due_hi_ms"]),
        "unhonoured_inside_edge": (sum(1 for d in unh if edge < d < edge + p_one["edge_span_ms"])
                                   if edge is not None else None),
        "lowest_unhonoured_d": min(unh) if unh else None,
        "own_window_unhonoured": sum(1 for h in victim["hit_recv"]
                                     if h[6] == 1 and h[5] == 0 and 0 <= h[7] < p_one["own_window_ms"]),
        "shooter_delay_D": "unknown",
    }
    if shooter is not None:
        recv = {(e[0], e[1], e[2]): e for e in shooter["blk_recv"]}
        arr = [wrap_diff(recv[(b[0], b[1], b[2])][3], b[0]) for b in victim["blk_sent"]
               if (b[0], b[1], b[2]) in recv]
        out["shooter_recorded_arrival_ms_median"] = median(arr)
        out["shooter_delay_D"] = "estimate_from_shooter_self_record"
    return out


def age_sum(a: dict, b: dict, p) -> dict:
    """The reciprocal age sum over OVERLAPPING buckets in which neither seat's
    own offset moved: per bucket min(A from B) plus min(B from A), and the
    median sum; the offsets cancel only within one epoch on each side. With
    no params (no revision) the budget and excess are unknown."""
    ba = {e[0]: e for e in a["age_b"] if e[1] == e[2] and e[3] > 0}
    bb = {e[0]: e for e in b["age_b"] if e[1] == e[2] and e[3] > 0}
    common = sorted(set(ba) & set(bb))
    mins = [ba[i][4] + bb[i][4] for i in common]
    p50s = [ba[i][5] + bb[i][5] for i in common]
    budget = None if p is None else (a["rtt"][0] + b["rtt"][0]) // 2 + p["budget_slack_ms"]
    mid = median(p50s)
    return {"buckets": len(common), "min_sum_median": median(mins), "sum_median": mid,
            "budget_ms": budget,
            "excess_ms": None if (mid is None or budget is None) else mid - budget}


def blocks_missing(victim: dict, shooter: dict, p: dict) -> int:
    """Window-opening blocks the victim sent that the shooter never recorded
    receiving. A shooter list with omissions cannot prove an absence, and a
    block inside the in-flight span before the victim's latest stamp is
    excluded (it may still have been in flight at game end)."""
    if shooter["omit"]["blk_recv"]:
        return 0
    recv = {(e[0], e[1], e[2]) for e in shooter["blk_recv"]}
    stamps = [e[0] for e in victim["blk_sent"]] + [e[1] for e in victim["hit_recv"]]
    if not stamps:
        return 0
    latest = stamps[0]
    for s in stamps:
        if wrap_diff(s, latest) > 0:
            latest = s
    return sum(1 for b in victim["blk_sent"]
               if b[1] in WINDOW_KINDS and (b[0], b[1], b[2]) not in recv
               and wrap_diff(latest, b[0]) > p["in_flight_ms"])


# -- the evaluation context ----------------------------------------------------

class Ctx:
    """One subject of one game: a seat (`i`, `r`) or the game itself (`i` None).
    `other` is the record of the seat this one names; `pair_other` is the same
    only when both records name each other (a two-record game)."""

    __slots__ = ("records", "i", "r", "other", "pair_other", "two", "match", "registry",
                 "params", "cache", "module")

    def __init__(self, records, i, match, registry, params, cache, module=None):
        self.records = records
        self.i = i
        self.match = match
        self.registry = registry
        self.params = params
        self.cache = cache
        self.module = module
        by_seat = {r["seat"]: r for r in records}
        self.two = len(records) == 2 and all(r["other"] in by_seat for r in records)
        self.r = records[i] if i is not None else None
        self.other = by_seat.get(self.r["other"]) if self.r is not None else None
        self.pair_other = self.other if self.two else None


def _family_params(ctx, family):
    return ctx.params[family]


def _case_table(ctx):
    key = ("case_table", ctx.i)
    if key not in ctx.cache:
        ctx.cache[key] = classify_blocks(ctx.r["rec"], ctx.pair_other["rec"], _family_params(ctx, "params.case_table"))
    return ctx.cache[key]


def _record_age(ctx):
    key = ("age_sum", None)
    if key not in ctx.cache:
        ctx.cache[key] = age_sum(ctx.records[0]["rec"], ctx.records[1]["rec"],
                                 _family_params(ctx, "params.age_sum"))
    return ctx.cache[key]


# -- seat measures -------------------------------------------------------------

@measure("seat.index", "seat")
def m_seat_index(ctx, p):
    return ctx.i


@measure("seat.record_conflict", "seat")
def m_record_conflict(ctx, p):
    return bool(ctx.r["conflict"])


@measure("seat.build_registered", "seat")
def m_build_registered(ctx, p):
    v, var, c = ctx.r["rec"]["build"]
    return (v, var, c, ctx.r["rec"]["dll"][0]) in ctx.registry


@measure("seat.build_version", "seat")
def m_build_version(ctx, p):
    return ctx.r["rec"]["build"][0]


@measure("seat.build_variant", "seat")
def m_build_variant(ctx, p):
    return ctx.r["rec"]["build"][1]


@measure("seat.build_commit", "seat")
def m_build_commit(ctx, p):
    return ctx.r["rec"]["build"][2]


@measure("seat.dll_state", "seat")
def m_dll_state(ctx, p):
    return ctx.r["rec"]["dll"][1]


@measure("seat.compat", "seat")
def m_compat(ctx, p):
    return ctx.r["rec"]["compat"]


@measure("seat.build_header_match", "seat")
def m_build_header_match(ctx, p):
    """The request header's mod version against the record's stated build;
    unknown when no header was recorded."""
    hv = ctx.r["header_version"]
    return None if hv is None else hv == ctx.r["rec"]["build"][0]


@measure("seat.build_relayed_match", "seat")
def m_build_relayed_match(ctx, p):
    """The build the OTHER seat relayed for this one against this record's own
    statement; unknown without the other record or a relayed build."""
    if ctx.other is None or not ctx.other["rec"]["other_build"]:
        return None
    v, var, c = ctx.r["rec"]["build"]
    return ctx.other["rec"]["other_build"] == "%s|%s|%s" % (v, var, c)


@measure("seat.build_differs", "seat")
def m_build_differs(ctx, p):
    out = []
    if m_build_header_match(ctx, p) is False:
        out.append("header_version")
    if m_build_relayed_match(ctx, p) is False:
        out.append("relayed_build")
    return out


@measure("seat.published_hits", "seat")
def m_published_hits(ctx, p):
    pub = ctx.r["rec"]["other_pub"]
    return None if pub is None else pub[3]


@measure("seat.observed_hits", "seat")
def m_observed_hits(ctx, p):
    return ctx.r["rec"]["imp"][2]


@measure("seat.published_fps", "seat")
def m_published_fps(ctx, p):
    pub = ctx.r["rec"]["other_pub"]
    return None if pub is None else pub[0]


@measure("seat.cadence_interval_median", "seat")
def m_cadence_interval(ctx, p):
    return ctx.r["rec"]["cad"][1]


@measure("seat.rounds_recorded", "seat")
def m_rounds_recorded(ctx, p):
    return list(ctx.r["rec"]["rounds"])


@measure("seat.rounds_match", "seat")
def m_rounds_match(ctx, p):
    """The match row's rounds from this seat's side; unknown with no match."""
    m = ctx.match
    if m is None:
        return None
    p1, p2 = m["p1_rounds_won"], m["p2_rounds_won"]
    return [p1, p2] if ctx.r["seat"] == m["player1_id"] else [p2, p1]


@measure("seat.decided_hits", "seat")
def m_decided_hits(ctx, p):
    return ctx.r["rec"]["dec"][0]


@measure("seat.other_received_hits", "seat")
def m_other_received_hits(ctx, p):
    """What the other seat recorded receiving from this one (two records only)."""
    return None if ctx.pair_other is None else ctx.pair_other["rec"]["imp"][0]


@measure("seat.blocks_case_a_late", "seat", "params.case_table")
def m_blocks_late(ctx, p):
    return None if ctx.pair_other is None else _case_table(ctx)["counts"]["late_single"]


@measure("seat.blocks_case_b", "seat", "params.case_table")
def m_blocks_b(ctx, p):
    return None if ctx.pair_other is None else _case_table(ctx)["counts"]["b"]


@measure("seat.blocks_case_c", "seat", "params.case_table")
def m_blocks_c(ctx, p):
    return None if ctx.pair_other is None else _case_table(ctx)["counts"]["c"]


@measure("seat.shooter_block_faults", "seat", "params.case_table")
def m_shooter_faults(ctx, p):
    return None if ctx.pair_other is None else _case_table(ctx)["blk_faults"]


@measure("seat.blocks_unrecorded_by_other", "seat", "params.blocks_missing")
def m_blocks_missing(ctx, p):
    if ctx.pair_other is None:
        return None
    return blocks_missing(ctx.r["rec"], ctx.pair_other["rec"], _family_params(ctx, "params.blocks_missing"))


# -- game measures (two records) -----------------------------------------------

@measure("game.age_sum_buckets", "game", "params.age_sum")
def m_age_buckets(ctx, p):
    return _record_age(ctx)["buckets"] if ctx.two else None


@measure("game.age_sum_min_median", "game", "params.age_sum")
def m_age_min(ctx, p):
    return _record_age(ctx)["min_sum_median"] if ctx.two else None


@measure("game.age_sum_median", "game", "params.age_sum")
def m_age_median(ctx, p):
    return _record_age(ctx)["sum_median"] if ctx.two else None


@measure("game.age_sum_budget", "game", "params.age_sum")
def m_age_budget(ctx, p):
    return _record_age(ctx)["budget_ms"] if ctx.two else None


@measure("game.age_sum_excess", "game", "params.age_sum")
def m_age_excess(ctx, p):
    return _record_age(ctx)["excess_ms"] if ctx.two else None


@measure("game.drift_first", "game")
def m_drift_first(ctx, p):
    return ctx.records[0]["rec"]["drift"][0] if ctx.two else None


@measure("game.drift_second", "game")
def m_drift_second(ctx, p):
    return ctx.records[1]["rec"]["drift"][0] if ctx.two else None


@measure("game.drift_sum", "game")
def m_drift_sum(ctx, p):
    if not ctx.two:
        return None
    return ctx.records[0]["rec"]["drift"][0] + ctx.records[1]["rec"]["drift"][0]


@measure("game.drift_sign", "game")
def m_drift_sign(ctx, p):
    return "positive = the measured seat's stamp clock runs fast" if ctx.two else None


# -- operators (generic comparisons; no defaults) ------------------------------

def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise TypeError("an ordering comparison needs numbers")
    return v


@operator("op.cmp", (("a", "expr"), ("rel", "rel"), ("b", "expr")))
def op_cmp(a, rel, b):
    if a is None or b is None:
        return None
    if rel == "eq":
        return a == b
    if rel == "ne":
        return a != b
    a, b = _num(a), _num(b)
    if rel == "gt":
        return a > b
    if rel == "ge":
        return a >= b
    if rel == "lt":
        return a < b
    if rel == "le":
        return a <= b
    raise ValueError("unknown relation")


@operator("op.truth", (("a", "expr"),))
def op_truth(a):
    if a is None:
        return None
    if not isinstance(a, bool):
        raise TypeError("op.truth needs a boolean measure")
    return a


@operator("op.in_set", (("a", "expr"), ("set", "list")))
def op_in_set(a, values):
    return None if a is None else a in values


# -- sitting measures: per-game SQL over committed match rows -------------------
# side.*: one expression per seat of the match row (the first player's, then the second's
# column); row.*: one expression for the row; reporter.*: an expression from
# the reporting seat's side. They read only match columns.

_sitting_sql("side", "side.shots_fired", "m.p1_bullets_fired", "m.p2_bullets_fired")
_sitting_sql("side", "side.shots_hit", "m.p1_bullets_hit", "m.p2_bullets_hit")
_sitting_sql("side", "side.blocks_activated", "m.p1_blocks_activated", "m.p2_blocks_activated")
_sitting_sql("side", "side.blocks_successful", "m.p1_blocks_successful", "m.p2_blocks_successful")
_sitting_sql("side", "side.opponent_ping_avg", "m.p2_ping_avg", "m.p1_ping_avg")
_sitting_sql("row", "row.duration_s", "COALESCE(m.duration_seconds, m.match_duration)")
_sitting_sql("reporter", "reporter.observed_batches",
     "CASE WHEN m.reported_by = m.player1_id THEN m.p1_obs_batches ELSE m.p2_obs_batches END")
_sitting_sql("population", "pop.completed_series",
     "JOIN ranked_series rs ON rs.id = m.series_id",
     "rs.status = 'completed' AND rs.invalidated_at IS NULL")
_sitting_sql("population", "pop.reporter_is_player", "", "m.reported_by IN (m.player1_id, m.player2_id)")

# One population, written once: ranked, not invalidated, ended inside the
# rule's window and at least the ready lag ago. UTC days explicitly.
POP_BASE = ("m.is_ranked IS TRUE AND m.invalidated_at IS NULL"
            " AND m.ended_at > now() - make_interval(days => CAST(:window_days AS int))"
            " AND m.ended_at <= now() - make_interval(secs => CAST(:lag_s AS int))")
DAY = "(ended_at AT TIME ZONE 'UTC')::date"
# Which sittings a statement returns: the worker's dirty set, or (the tuning
# tool only) the days back from today.
SCOPE_DIRTY = ("(LEAST({s}, {o}), GREATEST({s}, {o}), d) IN (SELECT pair_lo, pair_hi, day "
               "FROM review_sitting_dirty WHERE marked_at <= CAST(:snap AS timestamptz))")
SCOPE_DAYS_BACK = "d >= (now() AT TIME ZONE 'UTC')::date - CAST(:days_back AS int)"


def _pop(filters, R):
    joins, wheres = [], [POP_BASE]
    for name in filters:
        join, where = R(name, "population").data
        if join:
            joins.append(join)
        wheres.append(where)
    return " ".join(joins), " AND ".join(wheres)


def _scope(mode, s, o):
    return SCOPE_DIRTY.format(s=s, o=o) if mode == "dirty" else SCOPE_DAYS_BACK


@sitting_operator("sitting.rate_vs_own",
         (("num", "side"), ("den", "side"), ("filters", "filters"), ("window_days", "int"),
          ("elig_min_den", "int"), ("quantile", "num"), ("min_games", "int"),
          ("min_q_games", "int"), ("other_min", "int"), ("margin", "num")),
         ("subject", "opponent", "d", "n", "n_all", "n_q", "rate", "own_rate", "other_n",
          "last_mid", "q_value"))
def sit_rate_vs_own(a, R, mode):
    """Per (subject, opponent, UTC day): the subject's pooled num/den rate over
    games whose den meets the eligibility floor, how many of them reach the
    ladder quantile of all eligible games, and the subject's own rate in every
    other sitting in the window."""
    n1, n2 = R(a["num"], "side").data
    d1, d2 = R(a["den"], "side").data
    join, pop = _pop(a["filters"], R)
    return f"""
WITH g AS (
  SELECT m.id mid, m.ended_at, m.player1_id a, m.player2_id b,
         {d1} f, {n1} h FROM matches m {join} WHERE {pop}
  UNION ALL
  SELECT m.id, m.ended_at, m.player2_id, m.player1_id,
         {d2}, {n2} FROM matches m {join} WHERE {pop}),
gd AS (SELECT mid, a, b, {DAY} d, ended_at, f, h,
              COALESCE(f >= CAST(:elig_min_den AS int) AND h IS NOT NULL AND h >= 0 AND h <= f, false) elig
         FROM g),
lad AS (SELECT percentile_cont(CAST(:quantile AS float)) WITHIN GROUP (ORDER BY h::float / f) q_value
          FROM gd WHERE elig),
sit AS (SELECT a, b, d, count(*) n_all, count(*) FILTER (WHERE elig) n,
               COALESCE(sum(h) FILTER (WHERE elig), 0) hh, COALESCE(sum(f) FILTER (WHERE elig), 0) ff,
               count(*) FILTER (WHERE elig AND h::float / f >= (SELECT q_value FROM lad)) n_q,
               (array_agg(mid ORDER BY ended_at DESC))[1] last_mid
          FROM gd GROUP BY a, b, d),
acct AS (SELECT a, sum(n_all) all_n, sum(hh) all_h, sum(ff) all_f FROM sit GROUP BY a),
fl AS (SELECT s.a, s.b, s.d, s.n, s.n_all, s.n_q, s.last_mid,
              (c.all_n - s.n_all) other_n,
              CASE WHEN c.all_f - s.ff > 0 THEN (c.all_h - s.hh)::float / (c.all_f - s.ff) END own_rate,
              CASE WHEN s.ff > 0 THEN s.hh::float / s.ff END rate
         FROM sit s JOIN acct c ON c.a = s.a
        WHERE s.n >= CAST(:min_games AS int) AND s.n_q >= CAST(:min_q_games AS int))
SELECT a subject, b opponent, d, n, n_all, n_q, rate, own_rate, other_n, last_mid,
       (SELECT q_value FROM lad) q_value
  FROM fl
 WHERE (other_n < CAST(:other_min AS int) OR rate >= own_rate + CAST(:margin AS float))
   AND {_scope(mode, "a", "b")}"""


@sitting_operator("sitting.binomial_vs_own",
         (("trials", "side"), ("successes", "side"), ("stratify", "side"), ("edges", "edges"),
          ("strata_label", "label"), ("filters", "filters"), ("window_days", "int"),
          ("min_games", "int"), ("min_trials", "int"), ("base_min", "int"), ("z", "num")),
         ("subject", "opponent", "d", "n", "trials", "successes", "stratum", "p", "basis", "z",
          "last_mid"))
def sit_binomial_vs_own(a, R, mode):
    """Per (subject, opponent, UTC day): successes against trials, as a
    binomial deviation from the subject's own record in every other sitting,
    first within the same stratum of the stratify measure (when that history
    meets the base floor), else over all of the subject's other sittings."""
    t1, t2 = R(a["trials"], "side").data
    s1, s2 = R(a["successes"], "side").data
    x1, x2 = R(a["stratify"], "side").data
    join, pop = _pop(a["filters"], R)
    case = ["CASE WHEN xp IS NULL THEN -1"]
    for i in range(len(a["edges"])):
        case.append("WHEN xp < CAST(:edge_%d AS numeric) THEN %d" % (i, i))
    case.append("ELSE %d END" % len(a["edges"]))
    bucket = " ".join(case)
    return f"""
WITH g AS (
  SELECT m.id mid, m.ended_at, m.player1_id v, m.player2_id o, {t1} ba,
         {s1} bs, {x1} xp FROM matches m {join} WHERE {pop}
  UNION ALL
  SELECT m.id, m.ended_at, m.player2_id, m.player1_id, {t2},
         {s2}, {x2} FROM matches m {join} WHERE {pop}),
s AS (SELECT mid, v, o, {DAY} d, ended_at, ba, bs, {bucket} bk
        FROM g WHERE ba > 0 AND bs IS NOT NULL AND bs >= 0 AND bs <= ba),
sit AS (SELECT v, o, d, count(*) n, sum(ba) aa, sum(bs) ss, mode() WITHIN GROUP (ORDER BY bk) bk,
               (array_agg(mid ORDER BY ended_at DESC))[1] last_mid FROM s GROUP BY v, o, d),
base AS (SELECT x.*,
   (SELECT sum(y.bs)::float / NULLIF(sum(y.ba), 0) FROM s y
     WHERE x.bk >= 0 AND y.v = x.v AND y.bk = x.bk AND NOT (y.o = x.o AND y.d = x.d)) pb,
   (SELECT sum(y.ba) FROM s y
     WHERE x.bk >= 0 AND y.v = x.v AND y.bk = x.bk AND NOT (y.o = x.o AND y.d = x.d)) nb,
   (SELECT sum(y.bs)::float / NULLIF(sum(y.ba), 0) FROM s y
     WHERE y.v = x.v AND NOT (y.o = x.o AND y.d = x.d)) pa,
   (SELECT sum(y.ba) FROM s y WHERE y.v = x.v AND NOT (y.o = x.o AND y.d = x.d)) na
   FROM sit x WHERE x.n >= CAST(:min_games AS int) AND x.aa >= CAST(:min_trials AS int)),
z AS (SELECT v, o, d, n, aa, ss, bk, last_mid,
             CASE WHEN nb >= CAST(:base_min AS int) THEN pb
                  WHEN na >= CAST(:base_min AS int) THEN pa END p,
             CASE WHEN nb >= CAST(:base_min AS int) THEN CAST(:strata_label AS varchar)
                  WHEN na >= CAST(:base_min AS int) THEN 'all' END basis FROM base)
SELECT v subject, o opponent, d, n, aa trials, ss successes, bk stratum, p, basis,
       (ss - aa * p) / sqrt(aa * p * (1 - p)) z, last_mid
  FROM z
 WHERE p > 0 AND p < 1 AND (ss - aa * p) / sqrt(aa * p * (1 - p)) <= CAST(:z AS float)
   AND {_scope(mode, "v", "o")}"""


@sitting_operator("sitting.step_ratio",
         (("num", "reporter"), ("den", "row"), ("filters", "filters"), ("window_days", "int"),
          ("min_den", "int"), ("pre_rows", "int"), ("post_rows", "int"), ("low", "num"),
          ("high", "num")),
         ("subject", "opponent", "d", "steps", "min_ratio", "max_ratio", "last_mid"))
def sit_step_ratio(a, R, mode):
    """Per (reporting seat, the seat it measured, UTC day): games where the
    mean of num/den over the following rows departs from the mean over the
    preceding rows by a ratio outside [low, high]."""
    (num,) = R(a["num"], "reporter").data
    (den,) = R(a["den"], "row").data
    join, pop = _pop(a["filters"], R)
    part = "PARTITION BY meas, subj, %s ORDER BY ended_at" % DAY
    return f"""
WITH g AS (
  SELECT m.id mid, m.ended_at,
         CASE WHEN m.reported_by = m.player1_id THEN m.player1_id ELSE m.player2_id END meas,
         CASE WHEN m.reported_by = m.player1_id THEN m.player2_id ELSE m.player1_id END subj,
         ({num})::float / NULLIF({den}, 0) r
    FROM matches m {join}
   WHERE {pop} AND {den} >= CAST(:min_den AS int)),
w AS (SELECT g.*, {DAY} d,
   avg(r) OVER ({part} ROWS BETWEEN CAST(:pre_rows AS int) PRECEDING AND 1 PRECEDING) pre,
   count(r) OVER ({part} ROWS BETWEEN CAST(:pre_rows AS int) PRECEDING AND 1 PRECEDING) npre,
   avg(r) OVER ({part} ROWS BETWEEN CURRENT ROW AND CAST(:post_follow AS int) FOLLOWING) post,
   count(r) OVER ({part} ROWS BETWEEN CURRENT ROW AND CAST(:post_follow AS int) FOLLOWING) npost
   FROM g WHERE r IS NOT NULL),
st AS (SELECT meas, subj, d, mid, ended_at, post / pre ratio FROM w
        WHERE npre = CAST(:pre_rows AS int) AND npost = CAST(:post_rows AS int) AND pre > 0
          AND (post / pre < CAST(:low AS float) OR post / pre > CAST(:high AS float)))
SELECT meas subject, subj opponent, d, count(*) steps, min(ratio) min_ratio, max(ratio) max_ratio,
       (array_agg(mid ORDER BY ended_at DESC))[1] last_mid
  FROM st WHERE {_scope(mode, "meas", "subj")} GROUP BY meas, subj, d"""


def sitting_binds(entry: Entry, args: dict) -> dict:
    """The typed binds of one sitting statement: every int and num argument,
    the strata edges one by one, the label, the ready lag, and the follow
    span the step operator derives from its own post-row count."""
    binds = {"lag_s": CONTRACT_BOUNDS["ready_lag_s"]}
    for name, kind in entry.args:
        v = args[name]
        if kind in ("int", "num", "label"):
            binds[name] = v
        elif kind == "edges":
            for i, e in enumerate(v):
                binds["edge_%d" % i] = e
    if "post_rows" in args:
        binds["post_follow"] = args["post_rows"] - 1
    return binds


# -- the admin view (descriptions only; no rule, no decision) -------------------

def game_view(records: list, match, registry, params) -> dict:
    """What the admin read shows for one game: the reciprocal age sum and
    drift (two records), the block case table and the one-record view per
    victim, and the unavailable matrix when only one seat sent a record.
    `params` are the loaded revision's measure parameters; without them the
    parameterised parts read None."""
    by_seat = {r["seat"]: r for r in records}
    two = len(records) == 2 and all(r["other"] in by_seat for r in records)
    view = {"records": len(records)}
    l_hat = None
    p_age = (params or {}).get("params.age_sum")
    p5 = (params or {}).get("params.case_table")
    p1 = (params or {}).get("params.one_record")
    if two:
        a, b = records[0]["rec"], records[1]["rec"]
        s = age_sum(a, b, p_age)
        view["age_sum"] = s
        if s["sum_median"] is not None:
            l_hat = s["sum_median"] // 2
        ra, rb = a["drift"][0], b["drift"][0]
        view["drift"] = {"a_sees_b_cppm": ra, "b_sees_a_cppm": rb, "sum_cppm": ra + rb,
                         "sign": "positive = the measured seat's stamp clock runs fast"}
    view["case_table"] = []
    for i, victim_r in enumerate(records):
        shooter_r = by_seat.get(victim_r["other"]) if two else None
        entry = {"victim_index": i, "counts": None, "blk_faults": None, "one_record": None}
        if p5 is not None:
            table = classify_blocks(victim_r["rec"], shooter_r["rec"] if shooter_r else None, p5)
            entry["counts"], entry["blk_faults"] = table["counts"], table["blk_faults"]
            if p1 is not None:
                entry["one_record"] = one_record_view(
                    victim_r["rec"], shooter_r["rec"] if shooter_r else None, l_hat, p5, p1)
        view["case_table"].append(entry)
    view["params"] = "loaded" if params else "absent"
    if not two:
        view["evidence"] = "one_sided_legacy"
        view["unavailable"] = [
            "other_seat_measurements_of_the_capable_seat",
            "both_seat_agreement (missing blocks, decided against received hits, block cases a/b/c)",
            "reciprocal_age_sum_and_drift_cross_check",
            "old_seat_build_statement (an absent build property implies no build)",
        ]
    else:
        view["evidence"] = "two_records"
    return view


# The combat vocabulary registers itself into REGISTRY when imported; it is
# imported here so every reader of this registry sees the same entries.
import combat_measures as _combat  # noqa: E402,F401
