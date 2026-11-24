"""The ban census's statement-text resolver (ban_sweep_bound.py) over its closed failures: the census line,
the judged table (RULING-CENSUS-6 J1 to J11, RULING-CENSUS-7), one mutant per form with a control, the __doc__ pin and the
limits. RULING-CENSUS-3 section 8, RULING-CENSUS-4, RULING-CENSUS-5, RULING-CENSUS-6.

Every run reads main.py from the text it is given (a mutant is an edit of that text in memory), and every
VALUE comes from one child process (ban_sweep_values_child.py) that imports the read modules with no
database; an import that fails there fails the test, it is never skipped. Each resolver run takes two to
seven minutes and a whole file run on the VM seat about an hour; the module's base run is shared, and so
is each form's own base (a form's mutants run with that form alone)."""
import ast
import hashlib
import json
import os
import re
import runpy
import subprocess
import sys
from collections import Counter

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ban_sweep_census as B  # noqa: E402
import mdpl_census as mc  # noqa: E402

BOUND = os.path.join(HERE, "ban_sweep_bound.py")
CHILD = os.path.join(HERE, "ban_sweep_values_child.py")
API = B.API


def _api_sources():
    srcs = {}
    for f in sorted(os.listdir(API)):
        if f.endswith(".py"):
            with open(os.path.join(API, f), encoding="utf-8") as fh:
                srcs[f[:-3]] = fh.read()
    return srcs


def _sources(*edits, append=""):
    srcs = _api_sources()
    for old, new in edits:
        assert srcs["main"].count(old) == 1, old
        srcs["main"] = srcs["main"].replace(old, new)
    srcs["main"] += append
    return srcs


def _run(srcs, values=None, collect=False, switches=None):
    saved = mc.Source.text
    try:
        return runpy.run_path(BOUND, init_globals={"_BOUND_IN": {"srcs": srcs, "values": values,
                                                                 "collect": collect, "switches": switches}})
    finally:
        mc.Source.text = saved


def _child(requests, tmp, main_text=None):
    req, out = os.path.join(tmp, "req.json"), os.path.join(tmp, "out.json")
    with open(req, "w", encoding="utf-8") as fh:
        json.dump(requests, fh)
    args = [sys.executable, "-I", CHILD, API, req, out]
    if main_text is not None:
        mf = os.path.join(tmp, "main_mutant.py")
        with open(mf, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(main_text)
        args.append(mf)
    r = subprocess.run(args, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stderr[-3000:]
    with open(out, encoding="utf-8") as fh:
        vals = json.load(fh)
    bad = {k: v["error"] for k, v in vals.items() if "error" in v}
    assert not bad, bad                       # an import that fails is a closed failure, never a skip
    return vals


# what the judged table pins beside the resolver's own requests
EXTRA_REQUESTS = {
    "main|_JANITOR_EXPLAIN_WORDS": ["main", "_JANITOR_EXPLAIN_WORDS", True],
    "main|_JANITOR_SESSION_WORDS": ["main", "_JANITOR_SESSION_WORDS", True],
    "__sitting__": ["review_measures", "", True],
    "__registry_columns__": ["admin_evidence", "", True],
    "admin_evidence|SEAT_BASELINE_SQL": ["admin_evidence", "SEAT_BASELINE_SQL", True],
    "admin_evidence|PAIR_BASELINE_SQL": ["admin_evidence", "PAIR_BASELINE_SQL", True],
    # J13 to J15: the counting program's three places (review_calibrate.py), their texts and mappings' values
    "review_calibrate|_GAMES_SQL": ["review_calibrate", "_GAMES_SQL", True],
    "review_calibrate|_TABLES.values": ["review_calibrate", "list(_TABLES.values())", True],
    "review_calibrate|_CARD_MATCH.text": ["review_calibrate", "_CARD_MATCH.text", True],
    "review_calibrate|_COHORT_SQL": ["review_calibrate", "_COHORT_SQL", True],
    "review_calibrate|_GAMES_TABLES.values": ["review_calibrate", "list(_GAMES_TABLES.values())", True],
    "review_calibrate|_FAILED.values": ["review_calibrate", "list(_FAILED.values())", True],
    "review_calibrate|_MARKED.values": ["review_calibrate", "list(_MARKED.values())", True],
}


def _measure(srcs, tmp, main_text=None):
    ns = _run(srcs, collect=True)
    req = dict(ns["VALUE_REQ"])
    req.update(EXTRA_REQUESTS)
    vals = _child(req, tmp, main_text)
    return _run(srcs, values=vals), vals


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    ns, vals = _measure(_api_sources(), str(tmp_path_factory.mktemp("bound")))
    return ns, vals, {r["place"]: r for r in ns["rows"]}


def _rows_by_key(rows):
    """place -> row, the place keyed by its module, function and line (the expression text after it)."""
    return {r["place"].split(": ")[0]: r for r in rows}


def _digest(items):
    return hashlib.sha256("\x00".join(sorted(items)).encode("utf-8")).hexdigest()[:16]


def _value_text(v):
    return v if isinstance(v, str) else "\x00".join(v)


def _census_line(rows):
    return dict(sorted(Counter(r["verdict"] for r in rows).items()))


# ---- the census line --------------------------------------------------------------------------------
# At the stack lane's merge of the counting tool (2026-11-23), measured: bounded 25 -> 26 by the helper's SET LOCAL
# lock_timeout statement, main._player_deletion_key_shared_bounded:88115 (named _identity_key_shared_bounded until
# round mdplg-r2, which measured the line unchanged); "bounded": every text the statement can send is known, a word
# about its text and nothing about a wait; remaining 8 -> 11 by the counting program's three places (J13 to J15).
CENSUS_LINE = {"bounded": 26, "expanded": 122, "judged": 4, "read": 107, "remaining": 11}


def test_the_census_line_is_as_measured(base):
    ns, _vals, _rows = base
    assert _census_line(ns["rows"]) == CENSUS_LINE


# ---- the judged table (RULING-CENSUS-6 section 4) -------------------------------------------------------
# reading: VALUE (the child's exact value, pinned by digest), BLANK, WIDEST (the reaching constants' digest
# and the tables the widest texts name), or CALLERS / TEMPLATES (their own tests below). The reason is the
# first clause of the integrator's sentence.
JUDGED = {
    "admin_evidence._aer_rows:1588": {
        "reading": "VALUE", "values": {"admin_evidence|GAME_ROWS_SQL": "e0db82c239a691c3"},
        "reason": "the place runs the statement its caller passes; GAME_ROWS_SQL is built at import"},
    "main._discord_fix_probe:35221": {
        "reading": "VALUE", "values": {"main|_DISCORD_FIX_PROBE": "5fdd7743d8c5d886"},
        "reason": "the probe is taken at import from the constants of the function whose statement it probes"},
    "main._ffa_finishing_count_probe:72547": {
        "reading": "VALUE", "values": {"main|_FFA_FINISHING_COUNT_LOBBY_COLUMNS": "bba789f6bf1d525a",
                                       "main|_FFA_FINISHING_COUNT_PLAYER_COLUMNS": "0f0ed910ba151a80"},
        "reason": "each probe selects harvested column names"},
    "main._team_dc_fallback_probe:56484": {
        "reading": "VALUE", "values": {"main|_TEAM_DC_FALLBACK_COLUMNS": "b672923b95330f4b"},
        "reason": "as J3: the harvested value is (dc_fallback_at, dc_fallback_player_id)"},
    "main._janitor_check_statement:3508": {
        "reading": "BLANK", "expression": "'EXPLAIN ' + s['sql'] if cls == 'explain' else s['sql']",
        "explain_words": ["DELETE", "INSERT", "MERGE", "SELECT", "UPDATE", "VALUES", "WITH"],
        "session_words": ["ABORT", "BEGIN", "COMMIT", "END", "RELEASE", "RESET", "ROLLBACK", "SAVEPOINT", "SET",
                          "SHOW", "START"],
        "reason": "a DML statement is only EXPLAINed, a session-word statement runs as it is, anything else "
                  "is not sent, and every check is rolled back"},
    "admin_evidence.rebuild_game_population:1079": {
        "reading": "WIDEST", "reach": "a187c14dd4da0784", "tables": ["matches"],
        "reason": "every branch selects from the CTE g alone, and g reads matches"},
    "admin_evidence.rebuild_window_source:1106": {
        "reading": "WIDEST", "reach": "b80fa6f95bcb977a", "tables": ["matches"],
        "reason": "every branch selects from the CTE g alone, and g reads matches"},
    "admin_evidence._section_rows:2127": {
        "reading": "WIDEST", "reach": "e4a6001b33b5087e", "tables": ['card_contrib', 'card_evidence', 'card_games', 'card_player_daily', 'combat_contrib', 'combat_evidence', 'combat_games', 'combat_player_daily', 'identity_clock_evidence', 'identity_clock_games', 'runtime_settings'],
        "reason": "the place runs what a caller passes; the widest reading is the union of what any call can run"},
    "main._report_rows:83234": {
        "reading": "WIDEST", "reach": "ccee7a528106f0f2", "tables": ['ffa_lobbies', 'ffa_match_cards', 'ffa_match_players', 'ffa_matches', 'gold_transactions', 'match_cards', 'matches', 'ovt_match_cards', 'ovt_matches', 'ovt_series', 'players', 'ranked_series', 'rating_history', 'spectate_games', 'spectate_watch_grants', 'team_match_cards', 'team_match_telemetry', 'team_matches', 'team_series', 'tournament_matches'],
        "reason": "as J8"},
    "main.read:77875": {
        "reading": "CALLERS", "reason": "judged by its callers: the union of the 22 handle calls' statements"},
    "admin_evidence.read_baseline:748": {
        "reading": "VALUE", "requested": True,
        "values": {"admin_evidence|PAIR_BASELINE_SQL": "09d1bfda19831a69",
                   "admin_evidence|SEAT_BASELINE_SQL": "129162791d047680"},
        "causes": ["attribute: v.column"], "tables": ["matches"],
        "reason": "the place runs SEAT_BASELINE_SQL or PAIR_BASELINE_SQL, each a literal formatted at import "
                  "with _SELECT_LIST"},
    "seat_evidence.sitting_pass:739": {
        "reading": "TEMPLATES", "reason": "a rule's argument reaches a sitting statement's text only as a registry "
                                          "name given to R, through _pop, or as the length of a list argument "
                                          "written by %d"},
    # J13 to J15 (the counting program, review_calibrate.py): each pin holds every text the place can run; the
    # texts, each field filled by each of its values, are scanned as J12's are (j13_scan_failures below).
    "review_calibrate.games:717": {
        "reading": "VALUE", "requested": True,
        "values": {"review_calibrate|_GAMES_SQL": "72d9dd4a2116ad83",
                   "review_calibrate|_TABLES.values": "445e23d63edcba1f"},
        "tables": ["card_evidence", "combat_evidence", "identity_clock_evidence", "matches"],
        "reason": "the place runs _GAMES_SQL with its one field filled from _TABLES, a table name of the module "
                  "per domain"},
    "review_calibrate._card:749": {
        "reading": "VALUE", "requested": True,
        "values": {"review_calibrate|_CARD_MATCH.text": "9d77b9fc8657e57f"},
        "tables": ["matches", "ranked_series"],
        "reason": "the place runs _CARD_MATCH, built at import from card_evidence's _MATCH text before its first "
                  "WHERE, with one bound id"},
    "review_calibrate.read_cohort:1243": {
        "reading": "VALUE", "requested": True,
        "values": {"review_calibrate|_COHORT_SQL": "b8a30fba0c88a71b",
                   "review_calibrate|_TABLES.values": "445e23d63edcba1f",
                   "review_calibrate|_GAMES_TABLES.values": "68ff1a5aacc8d327",
                   "review_calibrate|_FAILED.values": "edac0aaf9ed80aad",
                   "review_calibrate|_MARKED.values": "f1b9b5cd385ba450"},
        "tables": ["card_evidence", "card_games", "combat_evidence", "combat_games", "identity_clock_evidence",
                   "identity_clock_games", "matches"],
        "reason": "the place runs cohort_sql(domain): _COHORT_SQL with its four fields filled from four "
                  "per-domain mappings of the module"},
}


def judged_table_failures(rows, vals):
    """every place judged or remaining that the table does not hold, or whose pin no longer holds."""
    by = _rows_by_key(rows)
    out = []
    open_places = {k for k, r in by.items() if r["verdict"] in ("judged", "remaining")}
    for k in sorted(open_places - set(JUDGED)):
        out.append("%s: %s and not in the judged table" % (k, by[k]["verdict"]))
    for k in sorted(set(JUDGED) - open_places):
        out.append("%s: in the judged table and no longer open (%s)" % (k, by[k]["verdict"] if k in by else "gone"))
    for k, j in sorted(JUDGED.items()):
        r = by.get(k)
        if r is None:
            continue
        if j["reading"] == "VALUE":
            keys = sorted(j["values"]) if j.get("requested") else r.get("judged_values", [])
            got = {key: _digest([_value_text((vals.get(key) or {}).get("value") or "")]) for key in keys}
            if got != j["values"]:
                out.append("%s: the values' digests are %s, the pin %s" % (k, got, j["values"]))
            if "causes" in j:
                causes = sorted({"%s: %s" % tuple(c) for c in r.get("causes", [])})
                if causes != j["causes"]:
                    out.append("%s: the causes are %s, the pin %s" % (k, causes, j["causes"]))
        elif j["reading"] == "BLANK":
            if r["place"].split(": ", 1)[1].split(" ", 1)[1] != repr(j["expression"]):
                out.append("%s: the expression is not the pinned one" % k)
            for name, pin in (("_JANITOR_EXPLAIN_WORDS", j["explain_words"]),
                              ("_JANITOR_SESSION_WORDS", j["session_words"])):
                if vals["main|" + name]["value"] != pin:
                    out.append("%s: %s is %s, the pin %s" % (k, name, vals["main|" + name]["value"], pin))
        elif j["reading"] == "WIDEST":
            if r.get("reach_digest", "")[:16] != j["reach"] or r.get("widest_tables") != j["tables"]:
                out.append("%s: the reach %s / tables %s are not the pinned %s / %s" % (
                    k, r.get("reach_digest", "")[:16], r.get("widest_tables"), j["reach"], j["tables"]))
    return out


def test_every_open_place_is_judged_with_its_pin_holding(base):
    ns, vals, _rows = base
    assert judged_table_failures(ns["rows"], vals) == []


# ---- J10: main.read, the triage handle's method, judged by its callers --------------------------------
READ_RECEIVERS = {"_pc_face_cache": 3, "f": 3, "h": 22, "os": 1, "resp": 1, "self": 1}
READ_RECEIVER_REASONS = {
    "_pc_face_cache": "the face cache object: reads stored bytes by key",
    "f": "an open file: reads its bytes or text",
    "self": "pc_portrait's cache class reading its own entry by key",
    "resp": "an HTTP response: reads its body",
    "os": "os.read on a file descriptor (review_rules)",
}
HANDLE_READINGS = "3bf0f08e9770a91b"


def _read_calls(srcs):
    out = []
    for m, s in srcs.items():
        tr = ast.parse(s)
        for fn in ast.walk(tr):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for c in ast.walk(fn):
                    if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "read" \
                            and (c.args or c.keywords):
                        out.append((m, fn, c))
    return out


def _innermost(calls):
    """each call once, with its innermost enclosing function."""
    best = {}
    for m, fn, c in calls:
        k = id(c)
        if k not in best or fn.lineno > best[k][1].lineno:
            best[k] = (m, fn, c)
    return list(best.values())


def handle_read_failures(srcs, ns):
    calls = _innermost(_read_calls(srcs))
    out = []
    table = Counter(ast.unparse(c.func.value) for _m, _f, c in calls)
    if dict(table) != READ_RECEIVERS:
        out.append("the receiver table is %s, the pin %s" % (dict(sorted(table.items())), READ_RECEIVERS))
    for r in table:
        if r != "h" and r not in READ_RECEIVER_REASONS:
            out.append("a receiver with no reason: %s" % r)
    texts = []
    for m, fn, c in calls:
        if ast.unparse(c.func.value) != "h":
            continue
        where = "%s.%s:%d" % (m, fn.name, c.lineno)
        params = {a.arg for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs}
        binds = [n for n in ast.walk(fn) if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.For,
                                                            ast.With, ast.NamedExpr))
                 and any(isinstance(s, ast.Name) and s.id == "h" and isinstance(s.ctx, ast.Store)
                         for s in ast.walk(n.target if not isinstance(n, (ast.Assign, ast.With))
                                           else (ast.Tuple(elts=n.targets, ctx=ast.Store())
                                                 if isinstance(n, ast.Assign) else n)))]
        handle = [n for n in binds if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                  and isinstance(n.value.func, ast.Name) and n.value.func.id == "_TriageReadHandle"]
        if not (("h" in params and not binds) or ("h" not in params and len(binds) == 1 and handle)):
            out.append("%s: h is not the handle (a parameter, or bound once from _TriageReadHandle)" % where)
            continue
        got = ns["exact_texts"](c.args[0], fn, m) if c.args else None
        if got is None:
            out.append("%s: the first argument does not read: %s" % (where, ast.unparse(c.args[0])[:80]))
            continue
        texts += got
    if not out and _digest(texts) != HANDLE_READINGS:
        out.append("the 22 readings' digest is %s, the pin %s" % (_digest(texts), HANDLE_READINGS))
    return out, texts


def test_j10_the_handle_read_is_judged_by_its_callers(base):
    ns, _vals, _rows = base
    bad, _texts = handle_read_failures(_api_sources(), ns)
    assert bad == []


# ---- J11: seat_evidence.sitting_pass, judged by its templates ------------------------------------------
SITTING_READING = {"lock_words": [], "tables": ["matches", "ranked_series", "review_sitting_dirty"],
                   "digest": "8e84ef65b8c9525f"}


def _operator_defs(src, names):
    tr = ast.parse(src)
    return [n for n in tr.body if isinstance(n, ast.FunctionDef) and n.name in names], tr


def _string_constants(fn):
    doc = ast.get_docstring(fn, clean=False)
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != doc:
            out.append(n.value)
    return out


SITTING_FORMAT_CONSTANTS = {
    "DAY": "the UTC day expression: a module constant, one of the four constants the reading reads",
}
SITTING_LENGTH_ROWS = [
    ["sitting.binomial_vs_own", "edges", "ELSE %d END"],
    ["sitting.binomial_vs_own", "edges", "WHEN xp < CAST(:edge_%d AS numeric) THEN %d"],
]
_CONVERSION = re.compile(r"%(?:\([^)]*\))?[-#0 +]*(?:\*|\d+)?(?:\.(?:\*|\d+))?[hlL]?(.)")


def sitting_argument_failures(d, op_name, helpers, constants):
    """RULING-CENSUS-7 section 3, by ast over one sitting operator: every a[...] stands as (1) an argument of
    R, (2) an argument of _pop, or (3) the argument of len(...) where that len(...) is the argument of
    range(...) in a for statement's iterator or a value of a % format; every % format has a string constant
    on its left whose conversions are all %d, with only such loop variables or such len(...) on its right,
    or formats named module constants (SITTING_FORMAT_CONSTANTS). Returns (failures, shape-3 rows)."""
    a, r_name = d.args.args[0].arg, d.args.args[1].arg
    parents = {id(c): p for p in ast.walk(d) for c in ast.iter_child_nodes(p)}
    out, rows = [], set()

    def where(n):
        return "review_measures.%s:%d" % (d.name, n.lineno)

    def key_of(sub):
        s = sub.slice
        return s.value if isinstance(s, ast.Constant) and isinstance(s.value, str) else None

    def is_len_of_arg(n):
        return (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "len"
                and len(n.args) == 1 and not n.keywords and isinstance(n.args[0], ast.Subscript)
                and isinstance(n.args[0].value, ast.Name) and n.args[0].value.id == a
                and key_of(n.args[0]) is not None)

    def is_mod(n):
        return isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod)

    def stores(name):
        return [m for m in ast.walk(d) if isinstance(m, ast.Name) and m.id == name and isinstance(m.ctx, ast.Store)]

    loops = {}
    for n in ast.walk(d):
        if (isinstance(n, ast.For) and isinstance(n.target, ast.Name) and isinstance(n.iter, ast.Call)
                and isinstance(n.iter.func, ast.Name) and n.iter.func.id == "range" and len(n.iter.args) == 1
                and not n.iter.keywords and is_len_of_arg(n.iter.args[0]) and len(stores(n.target.id)) == 1):
            loops[n.target.id] = (n, key_of(n.iter.args[0].args[0]))

    for n in ast.walk(d):
        if not (isinstance(n, ast.Name) and n.id == a):
            continue
        sub = parents.get(id(n))
        if not (isinstance(sub, ast.Subscript) and sub.value is n and key_of(sub) is not None):
            out.append("%s: the argument parameter is used other than as a[<name>]: %s"
                       % (where(n), ast.unparse(sub if sub is not None else n)[:80]))
            continue
        call = parents.get(id(sub))
        if (isinstance(call, ast.Call) and call.args and call.args[0] is sub and isinstance(call.func, ast.Name)
                and (call.func.id == r_name
                     or call.func.id == "_pop" and _registry_name_helper(helpers.get("_pop")))):
            continue
        if is_len_of_arg(call):
            up = parents.get(id(call))
            loop = parents.get(id(up))
            if (isinstance(up, ast.Call) and isinstance(up.func, ast.Name) and up.func.id == "range"
                    and len(up.args) == 1 and up.args[0] is call and isinstance(loop, ast.For) and loop.iter is up):
                continue
            if is_mod(up) and up.right is call:
                continue
            if isinstance(up, ast.Tuple) and is_mod(parents.get(id(up))) and parents[id(up)].right is up:
                continue
        out.append("%s: a rule argument reaches the text other than as a registry name given to R, a name "
                   "through _pop, or the length of a list argument as digits: %s"
                   % (where(n), ast.unparse(call if call is not None else sub)[:80]))

    for n in ast.walk(d):
        if not is_mod(n):
            continue
        values = list(n.right.elts) if isinstance(n.right, ast.Tuple) else [n.right]
        if not (isinstance(n.left, ast.Constant) and isinstance(n.left.value, str)):
            out.append("%s: a %% format whose left is not a string constant: %s" % (where(n), ast.unparse(n)[:80]))
            continue
        if all(isinstance(v, ast.Name) and v.id in SITTING_FORMAT_CONSTANTS and v.id in constants
               and not stores(v.id) for v in values):
            continue
        convs = [c for c in _CONVERSION.findall(n.left.value) if c != "%"]
        if any(c != "d" for c in convs):
            out.append("%s: a %% format with a conversion other than %%d: %r" % (where(n), n.left.value))
            continue
        keys = set()
        for v in values:
            if isinstance(v, ast.Name) and v.id in loops and any(m is n for m in ast.walk(loops[v.id][0])):
                keys.add(loops[v.id][1])
            elif is_len_of_arg(v):
                keys.add(key_of(v.args[0]))
            else:
                out.append("%s: a %%d value that is neither a loop variable of range(len(a[...])) nor "
                           "len(a[...]): %s" % (where(n), ast.unparse(v)[:80]))
                break
        else:
            rows.update((op_name, k, n.left.value) for k in keys)
    return out, rows


def sitting_failures(srcs, vals, ns):
    """the reading over the registry's sitting operators, their registered parts and the four constants;
    the argument check of RULING-CENSUS-7 section 3 over every operator; the shape-3 rows against their pin."""
    s = vals["__sitting__"]["value"]
    names = {fname: op for op, fname in s["operators"]}
    defs, tr = _operator_defs(srcs["review_measures"], set(names))
    out = []
    if {d.name for d in defs} != set(names):
        out.append("an operator is not a module-level def of review_measures: %s" % sorted(names))
    helpers = {n.name: n for n in tr.body if isinstance(n, ast.FunctionDef)}
    rows = set()
    for d in defs:
        bad, got = sitting_argument_failures(d, names[d.name], helpers, s["constants"])
        out += bad
        rows |= got
    if sorted(list(r) for r in rows) != SITTING_LENGTH_ROWS:
        out.append("the length rows are %s, the pin %s" % (sorted(list(r) for r in rows), SITTING_LENGTH_ROWS))
    texts = [t for d in defs for t in _string_constants(d)]
    texts += [p for _k, (_kind, parts) in sorted(s["parts"].items()) for p in parts]
    texts += [v for _k, v in sorted(s["constants"].items())]
    words = sorted({w.upper() for t in texts for w in ns["LOCK_RX"].findall(t)})
    tables = sorted({tb for t in texts for tb, rx in ns["TABLE_RX"].items() if rx.search(t)})
    reading = {"lock_words": words, "tables": tables, "digest": _digest(texts)}
    if reading != SITTING_READING:
        out.append("the sitting reading is %s, the pin %s" % (reading, SITTING_READING))
    return out, reading


def _registry_name_helper(fn):
    """a helper whose first parameter is used only as the iterable of loops whose target is used only as
    the first argument of the registry lookup R (review_measures._pop)."""
    if fn is None or len(fn.args.args) < 2:
        return False
    p, r_name = fn.args.args[0].arg, fn.args.args[1].arg
    loops = [n for n in ast.walk(fn) if isinstance(n, ast.For) and isinstance(n.iter, ast.Name) and n.iter.id == p]
    uses = [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == p]
    if not loops or len(uses) != len(loops):
        return False
    for lp in loops:
        if not isinstance(lp.target, ast.Name):
            return False
        tgt = lp.target.id
        calls = [c for c in ast.walk(lp) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                 and c.func.id == r_name and c.args and isinstance(c.args[0], ast.Name) and c.args[0].id == tgt]
        names = [n for n in ast.walk(lp) if isinstance(n, ast.Name) and n.id == tgt and n is not lp.target]
        if len(names) != len(calls):
            return False
    return True


def test_j11_the_sitting_pass_is_judged_by_its_templates(base):
    ns, vals, _rows = base
    bad, _reading = sitting_failures(_api_sources(), vals, ns)
    assert bad == []


def _rm_sources(old, new):
    srcs = _api_sources()
    assert srcs["review_measures"].count(old) == 1, old
    srcs["review_measures"] = srcs["review_measures"].replace(old, new)
    return srcs


_J11_MUTANTS = [
    ("an argument's value formatted by %s into the text",
     'case.append("ELSE %d END" % len(a["edges"]))',
     'case.append("ELSE %d END %s" % (len(a["edges"]), a["strata_label"]))'),
    ("an argument's value joined into the text by an f-string",
     "WHEN na >= CAST(:base_min AS int) THEN 'all' END basis FROM base)",
     "WHEN na >= CAST(:base_min AS int) THEN '{a['strata_label']}' END basis FROM base)"),
    ("a %s conversion beside the %d ones",
     '"WHEN xp < CAST(:edge_%d AS numeric) THEN %d" % (i, i)',
     '"WHEN xp < CAST(:edge_%d AS numeric) THEN %s" % (i, i)'),
    ("a subscript passed to a function that is neither R nor _pop",
     'x1, x2 = R(a["stratify"], "side").data',
     'x1, x2 = R(str(a["stratify"]), "side").data'),
]


@pytest.mark.parametrize("why,old,new", _J11_MUTANTS, ids=[m[0] for m in _J11_MUTANTS])
def test_j11_each_mutant_turns_the_argument_check_red(base, why, old, new):
    ns, vals, _rows = base
    bad, _reading = sitting_failures(_rm_sources(old, new), vals, ns)
    assert [b for b in bad if b.startswith("review_measures.sit_binomial_vs_own:")], (why, bad)


def test_j11_control_renaming_the_loop_variable_leaves_the_check_green(base):
    ns, vals, _rows = base
    old = ('    for i in range(len(a["edges"])):\n'
           '        case.append("WHEN xp < CAST(:edge_%d AS numeric) THEN %d" % (i, i))\n')
    new = old.replace("for i in", "for k in").replace("(i, i)", "(k, k)")
    bad, _reading = sitting_failures(_rm_sources(old, new), vals, ns)
    assert bad == []


# ---- one mutant per form, and a control per family ----------------------------------------------------
_BAN_LOCK = ["main._ban_void_lock:51415", "main._ban_void_lock:51419", "main._ban_void_lock:51422",
             "main._ban_void_lock:51425"]
_RANKED = '"ranked_series": {"active": "live", "completed": "terminal", "abandoned": "terminal"},'
_CHECKS = '    checks = {\n'
_SETS = '        sets.append("present_at = CAST(:now AS timestamptz)")\n'
_PC_RETURN = '    return _PC_PRINT_FACE_SELECT.replace(frag, cols, 1) + _pc_motion_servable_joins("s")\n'
_PC_PLACES = ["main._pc_bot_face_row:35687", "main._pc_motion_atlas_job:37657", "main.pc_face_motion_atlas:37735",
              "main.pc_face_motion_read:37701"]
_FLAG_PLACE = "flag_evidence.fetch_flag_context_rows:324"
_ASM_PLACE = "main._asm_census_write:66627"
_AUDIT_PLACE = "main._run_service_policy_audit:80167"


FORMS = ("DICT_PARTS", "EXPANSION", "PARAM", "MUTATION", "VALUE")
_FORM_BASE = {}


def _form_run(form, vals, srcs=None):
    """one run with this form alone: a form's mutant is judged by that form, never pre-empted by another."""
    return _run(srcs if srcs is not None else _api_sources(), values=vals,
                switches={f: f == form for f in FORMS})


def _form_base(form, vals):
    if form not in _FORM_BASE:                    # the rows alone: a whole namespace per form outgrows the cap
        _FORM_BASE[form] = {"rows": _form_run(form, vals)["rows"]}
    return _FORM_BASE[form]


def _row_at(rows0, rows1, key):
    """the row of rows1 that stands for rows0's place `key`: the same module.function, the same rank by line
    among that function's places (a mutant that adds a line moves the line, never the rank)."""
    fn = key.rsplit(":", 1)[0]

    def of(rows):
        return sorted((r for r in rows if r["place"].split(": ")[0].rsplit(":", 1)[0] == fn),
                      key=lambda r: int(r["place"].split(": ")[0].rsplit(":", 1)[1]))
    a, b = of(rows0), of(rows1)
    assert len(a) == len(b), (key, len(a), len(b))
    return b[[r["place"].split(": ")[0] for r in a].index(key)]


def _verdicts_of(ns0, ns, keys):
    return {k: _row_at(ns0["rows"], ns["rows"], k)["verdict"] for k in keys}


def test_dict_parts_a_lock_word_in_the_part_that_does_not_reach_leaves_the_place_bounded(base):
    """The hole of _ban_live_statuses_sql reads the inner KEYS (the status words); the inner values (the
    classes) do not reach it, so a lock word there leaves the four places bounded."""
    _ns, vals, _rows = base
    ns0 = _form_base("DICT_PARTS", vals)
    assert set(_verdicts_of(ns0, ns0, _BAN_LOCK).values()) == {"bounded"}
    ns = _form_run("DICT_PARTS", vals, _sources(
        (_RANKED, _RANKED.replace('"abandoned": "terminal"', '"abandoned": "terminal FOR UPDATE"'))))
    assert set(_verdicts_of(ns0, ns, _BAN_LOCK).values()) == {"bounded"}


def test_dict_parts_the_same_word_in_the_part_that_reaches_ends_the_bound(base):
    _ns, vals, _rows = base
    ns0 = _form_base("DICT_PARTS", vals)
    ns = _form_run("DICT_PARTS", vals, _sources(
        (_RANKED, _RANKED.replace('"abandoned": "terminal"', '"abandoned FOR UPDATE": "terminal"'))))
    assert "bounded" not in set(_verdicts_of(ns0, ns, _BAN_LOCK).values())


def test_dict_parts_a_store_into_the_dictionary_ends_the_split(base):
    _ns, vals, _rows = base
    ns0 = _form_base("DICT_PARTS", vals)
    ns = _form_run("DICT_PARTS", vals, _sources(
        append='\n\ndef _o3_mutant_store():\n    BAN_RECORD_STATUSES["ranked_series"]["x"] = "live"\n'))
    assert "bounded" not in set(_verdicts_of(ns0, ns, _BAN_LOCK).values())


def test_expansion_a_further_value_holding_a_lock_clause_changes_a_verdict(base):
    _ns, vals, _rows = base
    ns0 = _form_base("EXPANSION", vals)
    ns = _form_run("EXPANSION", vals, _sources(
        (_CHECKS, _CHECKS + '        "o3_mutant": "SELECT id FROM players FOR UPDATE",\n')))
    a = _rows_by_key(ns0["rows"])[_AUDIT_PLACE]
    b = _row_at(ns0["rows"], ns["rows"], _AUDIT_PLACE)
    assert a["verdict"] == "expanded"
    assert b["verdict"] == "expanded" and b["verdict_set"] != a["verdict_set"]


_LOCK_CALLER = ('\n\nasync def _o3_mutant_caller(db):\n'
                '    return await fetch_flag_context_rows(db, "fm.id = 1 FOR UPDATE", {}, "fm.id", 1)\n')


def _locked(row):
    return row["verdict"] == "remaining" or any("True" in v.split("]")[0] for v in row.get("verdict_set", []))


def test_param_a_new_caller_passing_a_lock_statement_changes_a_verdict(base):
    _ns, vals, _rows = base
    ns0 = _form_base("PARAM", vals)
    a = _rows_by_key(ns0["rows"])[_FLAG_PLACE]
    assert not _locked(a), a
    b = _rows_by_key(_form_run("PARAM", vals, _sources(append=_LOCK_CALLER))["rows"])[_FLAG_PLACE]
    assert _locked(b), b


def test_param_under_every_switch_a_new_caller_passing_a_lock_statement_is_seen(base):
    """The mutant that found the def-identity defect: a hole's function was the reader's parse of the def, the
    caller index is keyed by the resolver's own, so the parameter had no caller and its empty reach was read
    as a number (patch 13). Under every switch the new caller must reach the place."""
    ns0, vals, _rows = base
    a = _rows_by_key(ns0["rows"])[_FLAG_PLACE]
    assert a["verdict"] == "expanded" and not _locked(a), a
    b = _rows_by_key(_run(_sources(append=_LOCK_CALLER), values=vals)["rows"])[_FLAG_PLACE]
    assert _locked(b), b


def test_param_a_caller_the_resolver_cannot_read_is_a_closed_failure_naming_it(base):
    _ns, vals, _rows = base
    ns = _form_run("PARAM", vals, _sources(append='\n\nasync def _o3_mutant_unread(db):\n'
                                                  '    return await fetch_flag_context_rows(db, _o3_nowhere(), {}, "fm.id", 1)\n'))
    r = _rows_by_key(ns["rows"])[_FLAG_PLACE]
    assert r["verdict"] == "remaining"
    assert any("main._o3_mutant_unread" in str(w) for _k, w in r.get("causes", [])), r.get("causes")


def test_param_a_parameter_no_call_passes_is_a_closed_failure_never_a_number(base):
    _ns, vals, _rows = base
    ns = _run(_sources(append='\n\nasync def _o3_uncalled(db, w):\n'
                              '    await db.execute(text(f"SELECT id FROM players WHERE {w}"))\n'), values=vals)
    rows = [r for r in ns["rows"] if r["place"].startswith("main._o3_uncalled:")]
    assert len(rows) == 1 and rows[0]["verdict"] == "remaining", rows
    assert any("no call of main._o3_uncalled" in str(w) for _k, w in rows[0].get("causes", [])), rows[0]


def test_mutation_a_lock_clause_appended_to_a_joined_local_list_ends_the_bound(base):
    _ns, vals, _rows = base
    ns0 = _form_base("MUTATION", vals)
    assert _rows_by_key(ns0["rows"])[_ASM_PLACE]["verdict"] == "bounded"
    ns = _form_run("MUTATION", vals, _sources((_SETS, _SETS + '        sets.append("x = 1 FOR UPDATE")\n')))
    assert _row_at(ns0["rows"], ns["rows"], _ASM_PLACE)["verdict"] != "bounded"


def test_mutation_a_subscript_store_of_a_lock_clause_ends_the_bound(base):
    _ns, vals, _rows = base
    ns0 = _form_base("MUTATION", vals)
    ns = _form_run("MUTATION", vals, _sources((_SETS, _SETS + '        sets[0] = "x = 1 FOR UPDATE"\n')))
    assert _row_at(ns0["rows"], ns["rows"], _ASM_PLACE)["verdict"] != "bounded"


_CONTROLS = {
    "DICT_PARTS": dict(edits=[(_RANKED, _RANKED.replace('"abandoned": "terminal"',
                                                        '"abandoned": "terminal", "forfeit": "terminal"'))]),
    "EXPANSION": dict(edits=[(_CHECKS, _CHECKS + '        "o3_control": "SELECT id FROM players",\n')]),
    "PARAM": dict(edits=[], append='\n\nasync def _o3_control_caller(db):\n'
                                   '    return await fetch_flag_context_rows(db, "fm.id = 1", {}, "fm.id", 1)\n'),
    "MUTATION": dict(edits=[(_SETS, _SETS + '        sets.append("x = 1")\n')]),
}


@pytest.mark.parametrize("form", sorted(_CONTROLS))
def test_control_of_each_form_alone_without_a_lock_word_leaves_every_count(base, form):
    _ns, vals, _rows = base
    ns0 = _form_base(form, vals)
    c = _CONTROLS[form]
    ns = _form_run(form, vals, _sources(*c["edits"], append=c.get("append", "")))
    assert _census_line(ns["rows"]) == _census_line(ns0["rows"])


def test_controls_a_change_of_each_family_without_a_lock_word_leaves_every_count(base):
    """One run under every switch holding the four controls: a status word with no lock word (DICT_PARTS), a
    further display value with no lock clause (EXPANSION), a new caller passing a plain predicate (PARAM), a
    plain text appended to the joined list (MUTATION)."""
    ns0, vals, _rows = base
    ns = _run(_sources(*[e for f in sorted(_CONTROLS) for e in _CONTROLS[f]["edits"]],
                       append=_CONTROLS["PARAM"]["append"]), values=vals)
    assert _census_line(ns["rows"]) == _census_line(ns0["rows"])


def test_value_a_module_level_text_gaining_a_lock_clause_changes_a_verdict(base, tmp_path):
    """The pc_face statement is read exactly through the child; the child imports the mutant."""
    ns0, _vals, _rows = base
    srcs = _sources((_PC_RETURN, _PC_RETURN.replace('_pc_motion_servable_joins("s")\n',
                                                    '_pc_motion_servable_joins("s") + " FOR UPDATE"\n')))
    ns, _v = _measure(srcs, str(tmp_path), main_text=srcs["main"])
    a, b = _rows_by_key(ns0["rows"]), _rows_by_key(ns["rows"])
    assert any(a[k]["verdict_set"] != b[k].get("verdict_set") for k in _PC_PLACES)


def test_value_control_a_name_with_a_second_binding_is_not_read_and_its_place_falls_back(base):
    ns0, vals, _rows = base
    ns = _run(_sources(append="\n\n_PC_PRINT_MOTION_SELECT = _PC_PRINT_MOTION_SELECT\n"), values=vals)
    a, b = _rows_by_key(ns0["rows"]), _rows_by_key(ns["rows"])
    readers = [k for k in _PC_PLACES if k != "main._pc_motion_atlas_job:37657"]   # the three that name it
    assert all(a[k]["verdict"] in ("read", "expanded") for k in readers), {k: a[k]["verdict"] for k in readers}
    assert all(b[k]["verdict"] not in ("read", "expanded") for k in readers), {k: b[k]["verdict"] for k in readers}


_LOCK_KEY_STORE = '\n\ndef _o3_mutant_store():\n    BAN_RECORD_STATUSES["ranked_series"]["x FOR UPDATE"] = "live"\n'


def test_value_a_name_the_closure_reads_changed_after_import_is_not_read_and_the_store_is_seen(base):
    """The ban lock statement is read exactly at import; a store into BAN_RECORD_STATUSES in any read
    module can change the text the place runs, so VALUE does not read it, the DICT_PARTS split ends, and the
    stored key's lock word reaches the place (MUTATION)."""
    ns0, vals, _rows = base
    a = _rows_by_key(ns0["rows"])["main._ban_void_lock:51419"]
    assert a["verdict"] == "read" and not _locked(a), a
    ns = _run(_sources(append=_LOCK_KEY_STORE), values=vals)
    b = _rows_by_key(ns["rows"])["main._ban_void_lock:51419"]
    assert b["verdict"] != "read" and _locked(b), b
    why = [w for k, w in ns["VALUE_WHY"].items() if "BAN_RECORD_STATUSES" in str(w)]
    assert why and all("changed after import" in str(w) for w in why), why


def test_value_control_a_store_into_a_name_no_place_reads_leaves_every_count(base):
    ns0, vals, _rows = base
    ns = _run(_sources(append='\n\n_O3_D = {"a": "b"}\n\n\ndef _o3_store():\n    _O3_D["c"] = "d FOR UPDATE"\n'),
              values=vals)
    assert _census_line(ns["rows"]) == _census_line(ns0["rows"])
    assert not [w for w in ns["VALUE_WHY"].values() if "changed after import" in str(w)]


# ---- RULING-CENSUS-8 (a): identity across two parses ---------------------------------------------------
def _defs_of(ns, mod):
    return [d for d in ast.walk(ns["trees"][mod]) if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _inside(hn, d):
    """hn is a node of d, or a node the reader built (no position) whose positioned parts are all nodes of d."""
    mine = {id(x) for x in ast.walk(d)}
    if id(hn) in mine:
        return True
    if hasattr(hn, "lineno"):
        return False
    parts = [x for x in ast.walk(hn) if hasattr(x, "lineno")]
    return bool(parts) and all(id(x) in mine for x in parts)


def one_parse_failures(ns, extra_holes=()):
    """every module the reader parsed is the resolver's own tree, and every hole's def (and the hole node in
    it) is a node of that tree: the caller, method and initializer indexes are keyed by those identities."""
    out, checked = [], 0
    for m, tr in sorted(ns["src"].trees.items()):
        if ns["trees"].get(m) is not tr:
            out.append("trees[%s] is not the reader's tree" % m)
    ids = {}
    for n, (hn, hfn, hmod) in list(ns["HOLES"].items()) + list(extra_holes):
        if not hfn:
            continue
        d = hfn[1] if isinstance(hfn, tuple) else ns["fnode"](hfn)
        if hmod not in ids:
            ids[hmod] = {id(x) for x in _defs_of(ns, hmod)}
        if d is None or id(d) not in ids[hmod]:
            out.append("hole %s: its def %s is not a def of trees[%s]" % (n, getattr(d, "name", None), hmod))
        elif not _inside(hn, d):
            out.append("hole %s: its node is not inside its def %s" % (n, d.name))
        checked += 1
    return out, checked


def test_one_parse_every_hole_and_def_is_a_node_of_the_resolvers_tree(base):
    ns, _vals, _rows = base
    bad, checked = one_parse_failures(ns)
    assert bad == [] and checked > 0, (bad[:5], checked)


def test_one_parse_control_a_def_from_another_parse_finds_no_caller_and_is_reported(base):
    ns, _vals, _rows = base
    mine = [d for d in _defs_of(ns, "flag_evidence") if d.name == "fetch_flag_context_rows"][0]
    other = [d for d in ast.walk(ast.parse(_api_sources()["flag_evidence"]))
             if isinstance(d, ast.AsyncFunctionDef) and d.name == "fetch_flag_context_rows"][0]
    assert len(ns["param_calls"](mine, "flag_evidence", "where_sql")[0]) == 3
    assert ns["param_calls"](other, "flag_evidence", "where_sql")[0] == []      # the lookup the defect made
    hn = [x for x in ast.walk(other) if isinstance(x, ast.Name) and x.id == "where_sql"][0]
    bad, _n = one_parse_failures(ns, extra_holes=[("planted", (hn, ("DEF", other), "flag_evidence"))])
    assert bad == ["hole planted: its def fetch_flag_context_rows is not a def of trees[flag_evidence]"], bad


def test_one_parse_control_a_reader_built_node_over_another_parse_is_reported(base):
    """the reader's own tuple of a format call's arguments passes when its parts are the def's nodes (the base
    holds such holes), and is reported when a part comes from another parse."""
    ns, _vals, _rows = base
    mine = [d for d in _defs_of(ns, "flag_evidence") if d.name == "fetch_flag_context_rows"][0]
    own_node = [x for x in ast.walk(mine) if isinstance(x, ast.Name) and x.id == "where_sql"][0]
    other = [d for d in ast.walk(ast.parse(_api_sources()["flag_evidence"]))
             if isinstance(d, ast.AsyncFunctionDef) and d.name == "fetch_flag_context_rows"][0]
    foreign = [x for x in ast.walk(other) if isinstance(x, ast.Name) and x.id == "where_sql"][0]
    good = ("good", (ast.Tuple(elts=[own_node], ctx=ast.Load()), ("DEF", mine), "flag_evidence"))
    bad_ = ("bad", (ast.Tuple(elts=[foreign], ctx=ast.Load()), ("DEF", mine), "flag_evidence"))
    empty = ("empty", (ast.Tuple(elts=[], ctx=ast.Load()), ("DEF", mine), "flag_evidence"))
    got, _n = one_parse_failures(ns, extra_holes=[good, bad_, empty])
    assert got == ["hole bad: its node is not inside its def fetch_flag_context_rows",
                   "hole empty: its node is not inside its def fetch_flag_context_rows"], got
    assert sum(1 for h in ns["HOLES"].values() if not hasattr(h[0], "lineno")) > 0


def test_one_parse_a_reader_text_other_than_the_given_text_is_refused():
    srcs = _api_sources()
    srcs["flag_evidence"] += "\n# a text the reader does not parse\n"
    with pytest.raises(RuntimeError, match="the reader parsed flag_evidence.py from a text the resolver was not given"):
        _run(srcs)


# ---- RULING-CENSUS-8 (d): the name-and-first-line map -------------------------------------------------
_MAP_SRC = "def f():\n    return 1\n\n\nclass A:\n    def g(self):\n        return 2\n"


def test_the_map_takes_a_def_of_its_tree_as_itself_and_another_parse_by_name_and_line(base):
    ns, _vals, _rows = base
    tr = ast.parse(_MAP_SRC)
    ns["trees"]["_o3_map"] = tr
    ns["_DEFS_BY_MOD"].pop("_o3_map", None)
    try:
        f_own = tr.body[0]
        assert ns["as_trees_def"]("_o3_map", f_own) == (f_own, None)
        d, why = ns["as_trees_def"]("_o3_map", ast.parse(_MAP_SRC).body[0])
        assert d is f_own and why is None
        d, why = ns["as_trees_def"]("_o3_map", ast.parse("def h():\n    pass\n").body[0])
        assert why == "_o3_map.h:1 maps to 0 defs of _o3_map", why
        g = tr.body[1].body[0]
        g.name, g.lineno = "f", 1                       # two defs of one name on one first line
        ns["_DEFS_BY_MOD"].pop("_o3_map", None)
        foreign = ast.parse(_MAP_SRC).body[0]
        d, why = ns["as_trees_def"]("_o3_map", foreign)
        assert d is foreign and why == "_o3_map.f:1 maps to 2 defs of _o3_map", why
    finally:
        ns["trees"].pop("_o3_map", None)
        ns["_DEFS_BY_MOD"].pop("_o3_map", None)


def test_no_place_carries_a_def_map_failure_at_the_base(base):
    ns, _vals, _rows = base
    assert [r["place"] for r in ns["rows"] if any(c[0] == "def map" for c in r.get("causes") or [])] == []


# ---- RULING-CENSUS-8 (b) and (c): empty means failure, a mutant per route --------------------------------
_PLACE_SQL = 'await db.execute(text(f"SELECT id FROM players WHERE {%s}"))'
_ROUTE_MUTANTS = {
    # route: (form it belongs to, source appended to main, the function holding the place, the cause's words)
    "no caller": ("PARAM", "async def _o3_m_nocaller(db, w):\n    " + _PLACE_SQL % "w" + "\n",
                  "_o3_m_nocaller", "no call of main._o3_m_nocaller in the read modules passes w"),
    "an argument that reaches nothing": (
        "PARAM", "async def _o3_m_nothing(db, w):\n    " + _PLACE_SQL % "w" + "\n\n\n"
                 "async def _o3_m_nothing_caller(db):\n    await _o3_m_nothing(db, [])\n",
        "_o3_m_nothing", "reaches nothing"),
    "an empty reach": (None, "async def _o3_m_empty(db):\n    x = []\n    " + _PLACE_SQL % "x" + "\n",
                       "_o3_m_empty", "nothing reaches the hole x"),
    "no return": (None, "def _o3_m_noret():\n    pass\n\n\nasync def _o3_m_noret_use(db):\n    "
                        + _PLACE_SQL % "_o3_m_noret()" + "\n",
                  "_o3_m_noret_use", "no return with a value in the read function main._o3_m_noret"),
    "a yield": (None, "def _o3_m_gen():\n    yield 'id = 1'\n\n\nasync def _o3_m_gen_use(db):\n    "
                      + _PLACE_SQL % "_o3_m_gen()" + "\n",
                "_o3_m_gen_use", "the read function main._o3_m_gen yields"),
    "an empty loop": (None, "async def _o3_m_loop(db):\n    for q, w in ():\n        await db.execute(text(q))\n",
                      "_o3_m_loop", "the loop form reads no text"),
}
_ROUTE_CONTROLS = {
    "no caller": ("async def _o3_c_called(db, w):\n    " + _PLACE_SQL % "w" + "\n\n\n"
                  "async def _o3_c_called_caller(db):\n    await _o3_c_called(db, 'id = 1')\n", "_o3_c_called"),
    "an argument that reaches nothing": (
        "async def _o3_c_something(db, w):\n    " + _PLACE_SQL % "w" + "\n\n\n"
        "async def _o3_c_something_caller(db):\n    await _o3_c_something(db, 'id = 2')\n", "_o3_c_something"),
    "an empty reach": ("async def _o3_c_full(db):\n    x = 'id = 3'\n    " + _PLACE_SQL % "x" + "\n", "_o3_c_full"),
    "no return": ("def _o3_c_ret():\n    return 'id = 4'\n\n\nasync def _o3_c_ret_use(db):\n    "
                  + _PLACE_SQL % "_o3_c_ret()" + "\n", "_o3_c_ret_use"),
    "a yield": ("def _o3_c_ret2():\n    return 'id = 5'\n\n\nasync def _o3_c_ret2_use(db):\n    "
                + _PLACE_SQL % "_o3_c_ret2()" + "\n", "_o3_c_ret2_use"),
    "an empty loop": ("async def _o3_c_loop(db):\n    for q, w in (('SELECT id FROM players', 'x'),):\n"
                      "        await db.execute(text(q))\n", "_o3_c_loop"),
}
_ROUTE_RUNS = {}


def _route_run(kind, mode, vals, tmp):
    """the run of all route mutants (kind 'm') or all controls (kind 'c') in one appended source, under every
    switch (a fresh child that imports the mutant main) or under one form alone ('PARAM', or None: no form)."""
    key = (kind, mode)
    if key not in _ROUTE_RUNS:
        table = _ROUTE_MUTANTS if kind == "m" else _ROUTE_CONTROLS
        srcs = _sources(append="\n\n" + "\n\n".join(v[1] if kind == "m" else v[0] for v in table.values()))
        if mode == "ALL":
            ns, _v = _measure(srcs, tmp, main_text=srcs["main"])
        else:
            ns = _run(srcs, values=vals, switches={f: f == mode for f in FORMS})
        _ROUTE_RUNS[key] = {"rows": ns["rows"]}  # the rows alone, as _form_base
    return _ROUTE_RUNS[key]


def _place_of(ns, fname, census_may_read=False):
    """the one row of the place in fname; a control the census reads whole has no row (it is no closed
    failure of the census) and stands as read, a mutant must have its row."""
    rows = [r for r in ns["rows"] if r["place"].startswith("main.%s:" % fname)]
    if not rows and census_may_read:
        return {"place": "main.%s: read whole by the census" % fname, "verdict": "read"}
    assert len(rows) == 1, (fname, [r["place"] for r in rows])
    return rows[0]


def _cause_text(row):
    return " | ".join([row.get("cause", "")] + ["%s: %s" % (c[0], c[1]) for c in row.get("causes") or []])


_ROUTE_CASES = [(r, m) for r in sorted(_ROUTE_MUTANTS) for m in ("ALL", _ROUTE_MUTANTS[r][0])]


@pytest.mark.parametrize("route,mode", _ROUTE_CASES, ids=["%s-%s" % (r, m) for r, m in _ROUTE_CASES])
def test_each_empty_route_ends_in_a_closed_failure_naming_it(base, tmp_path_factory, route, mode):
    _ns, vals, _rows = base
    ns = _route_run("m", mode, vals, str(tmp_path_factory.mktemp("route")))
    row = _place_of(ns, _ROUTE_MUTANTS[route][2])
    assert row["verdict"] == "remaining" and _ROUTE_MUTANTS[route][3] in _cause_text(row), (route, mode, row)


@pytest.mark.parametrize("route,mode", _ROUTE_CASES, ids=["%s-%s" % (r, m) for r, m in _ROUTE_CASES])
def test_each_empty_routes_control_is_read_and_moves_no_other_place(base, tmp_path_factory, route, mode):
    ns0, vals, _rows = base
    ns = _route_run("c", mode, vals, str(tmp_path_factory.mktemp("route")))
    row = _place_of(ns, _ROUTE_CONTROLS[route][1], census_may_read=True)
    assert row["verdict"] in ("read", "expanded", "bounded"), (route, mode, row)
    base_rows = ns0["rows"] if mode == "ALL" else _form_base(mode, vals)["rows"]
    keep = {r["place"].split(": ")[0] for r in base_rows}
    assert _census_line([r for r in ns["rows"] if r["place"].split(": ")[0] in keep]) == _census_line(base_rows)


def test_the_empty_exact_routes_the_code_cannot_reach_are_never_taken_at_the_base(base):
    """exact_texts returns None or a list built from at least one text (a constant, a product of non-empty
    lists, a join's one text, the child's one string), so an empty exact reading at a place or at a hole is
    unreachable from the code as it stands; the guards stay, and no place carries their causes."""
    ns, _vals, _rows = base
    hit = [r["place"] for r in ns["rows"] if "an empty exact reading" in _cause_text(r)]
    assert hit == []


def test_an_empty_word_table_refuses_the_run(monkeypatch):
    import ban_sweep_tables
    monkeypatch.setattr(ban_sweep_tables, "TABLE_CLASSES", {})
    with pytest.raises(RuntimeError, match="an empty word table"):
        _run(_api_sources())


def test_the_judged_pins_refuse_an_empty_value_an_empty_word_table_and_no_table(base):
    """VALUE, BLANK and WIDEST read nothing new at the place: their pins are the reading, and each refuses
    the empty input (the control: the base passes)."""
    ns, vals, _rows = base
    assert judged_table_failures(ns["rows"], vals) == []
    v2 = json.loads(json.dumps(vals))
    v2["admin_evidence|GAME_ROWS_SQL"]["value"] = ""
    v2["main|_JANITOR_EXPLAIN_WORDS"]["value"] = []
    rows2 = json.loads(json.dumps(ns["rows"], default=str))
    for r in rows2:
        if r["place"].startswith("admin_evidence.rebuild_game_population:1079"):
            r["widest_tables"] = []
    bad = judged_table_failures(rows2, v2)
    assert any(b.startswith("admin_evidence._aer_rows:1588: the values' digests") for b in bad), bad
    assert any(b.startswith("main._janitor_check_statement:3508: _JANITOR_EXPLAIN_WORDS is []") for b in bad), bad
    assert any(b.startswith("admin_evidence.rebuild_game_population:1079: the reach") for b in bad), bad
    # J13 to J15: one character of each pinned text, and one table name of a pinned mapping, names the row;
    # the unchanged copy names none (the control).
    assert judged_table_failures(ns["rows"], json.loads(json.dumps(vals))) == []
    for key, edit, place in (
            ("review_calibrate|_GAMES_SQL", lambda t: t.replace("DISTINCT", "DISTINCt", 1),
             "review_calibrate.games:717"),
            ("review_calibrate|_TABLES.values", lambda t: [t[0] + "x"] + t[1:], "review_calibrate.games:717"),
            ("review_calibrate|_CARD_MATCH.text", lambda t: t.replace("m.id = :mid", "m.id = :mie", 1),
             "review_calibrate._card:749"),
            ("review_calibrate|_COHORT_SQL", lambda t: t.replace("DISTINCT", "DISTINCt", 1),
             "review_calibrate.read_cohort:1243"),
            ("review_calibrate|_GAMES_TABLES.values", lambda t: t[:-1] + [t[-1] + "x"],
             "review_calibrate.read_cohort:1243")):
        v2 = json.loads(json.dumps(vals))
        v2[key]["value"] = edit(v2[key]["value"])
        bad = judged_table_failures(ns["rows"], v2)
        assert any(b.startswith(place + ": the values' digests") for b in bad), (key, bad)


# The places whose every verdict holds no table, by name, each a true answer by the code. "read": the text is
# exact and names no table (main:1384 and main:23704, advisory key statements over _DC_PAIR_LOCK_KEY_SQL).
# "bounded": every text the statement can send is known and none names a table (main:19225, main:19233 and
# main:88843, SET LOCAL lock_timeout statements whose one hole is a number of milliseconds); the word is about
# the text, not a wait.
NO_TABLE_PLACES = {"main._identity_lock_many:18505": "bounded", "main._identity_lock_many:18513": "bounded",
                   "main._publish_pair_sitting:1383": "read", "main._report_disconnect_once:22984": "read",
                   "main._player_deletion_key_shared_bounded:88115": "bounded"}


def test_the_places_whose_verdicts_hold_no_table_are_the_named(base):
    ns, _vals, _rows = base
    got = {}
    for r in ns["rows"]:
        k = r["place"].split(": ")[0]
        vs = r.get("verdict_set")
        if r["verdict"] in ("read", "expanded", "judged") and vs is not None and all(x.endswith(", [])") for x in vs):
            got[k] = r["verdict"]
        if r["verdict"] == "bounded" and not r.get("widest_tables"):
            got[k] = "bounded"
    assert got == NO_TABLE_PLACES


# ---- the __doc__ pin (RULING-CENSUS-5 section 6) and the limits ----------------------------------------
DOC_READS = ["main._discord_fix_read", "main._ffa_finishing_count_columns",
             "main._team_dc_fallback_columns", "review_rules.<module>", "review_rules.cli"]


def doc_reads(srcs):
    out = []
    for m, s in sorted(srcs.items()):
        tr = ast.parse(s)
        fns = [n for n in ast.walk(tr) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for n in ast.walk(tr):
            if isinstance(n, ast.Attribute) and n.attr == "__doc__" or isinstance(n, ast.Name) and n.id == "__doc__":
                inner = [f for f in fns if f.lineno <= n.lineno <= f.end_lineno]
                out.append("%s.%s" % (m, max(inner, key=lambda f: f.lineno).name if inner else "<module>"))
    return sorted(out)


def test_the_doc_reads_are_the_five_named(base):
    assert doc_reads(_api_sources()) == DOC_READS


def test_the_limits_are_stated(base):
    ns, _vals, _rows = base
    lim = " ".join(ns["LIMITS"])
    for words in ("split across two constants", "without regard to case", "outside backend/api",
                  ".pattern", "local receiver passes by name", "a subscript store"):
        assert words in lim, words


# ---- RULING-CENSUS-9 section 3 (c): J12, the two baseline texts scanned whole ---------------------------
def j12_scan_failures(verdicts, vals):
    """each of J12's values holds no lock word and names exactly the pinned tables."""
    j = JUDGED["admin_evidence.read_baseline:748"]
    out = []
    for key in sorted(j["values"]):
        t = (vals.get(key) or {}).get("value")
        if not isinstance(t, str) or not t.strip():
            out.append("%s: no text" % key)
            continue
        v = verdicts(t)
        if any(v[:-1]):
            out.append("%s: a lock word %s" % (key, v[:-1]))
        if sorted(v[-1]) != j["tables"]:
            out.append("%s: the tables %s, the pin %s" % (key, sorted(v[-1]), j["tables"]))
    return out


def test_j12_the_baseline_texts_hold_no_lock_word_and_name_matches_alone(base):
    ns, vals, _rows = base
    assert j12_scan_failures(ns["verdicts"], vals) == []


def test_j12_the_scan_refuses_a_lock_word_a_further_table_and_an_empty_text(base):
    ns, vals, _rows = base
    for edit, words in ((lambda t: t + " FOR UPDATE", "a lock word"),
                        (lambda t: t.replace("FROM matches m", "FROM matches m JOIN players p ON true", 1),
                         "the tables"),
                        (lambda t: "", "no text")):
        v2 = json.loads(json.dumps(vals))
        key = "admin_evidence|SEAT_BASELINE_SQL"
        v2[key]["value"] = edit(v2[key]["value"])
        bad = j12_scan_failures(ns["verdicts"], v2)
        assert any(b.startswith(key + ": " + words) for b in bad), (words, bad)
    v2 = json.loads(json.dumps(vals))                       # control: a change with no lock word and no table
    v2["admin_evidence|SEAT_BASELINE_SQL"]["value"] += "\n"
    assert j12_scan_failures(ns["verdicts"], v2) == []


# ---- J13 to J15: the counting program's three texts, each field filled by each of its values, scanned whole --
def j13_texts(vals):
    """place -> the texts it can run: _GAMES_SQL per domain, _CARD_MATCH, _COHORT_SQL per domain (the four
    mappings' values taken domain by domain, as cohort_sql fills them)."""
    v = {k: (vals.get(k) or {}).get("value") for k in vals if k.startswith("review_calibrate|")}
    rc = "review_calibrate|"
    if not all(isinstance(v.get(rc + n), (str, list)) and v.get(rc + n) for n in (
            "_GAMES_SQL", "_TABLES.values", "_CARD_MATCH.text", "_COHORT_SQL", "_GAMES_TABLES.values",
            "_FAILED.values", "_MARKED.values")):
        return None
    return {
        "review_calibrate.games:717": [v[rc + "_GAMES_SQL"].format(t=t) for t in v[rc + "_TABLES.values"]],
        "review_calibrate._card:749": [v[rc + "_CARD_MATCH.text"]],
        "review_calibrate.read_cohort:1243": [
            v[rc + "_COHORT_SQL"].format(t=t, g=g, failed=f, marked=m) for t, g, f, m in zip(
                v[rc + "_TABLES.values"], v[rc + "_GAMES_TABLES.values"], v[rc + "_FAILED.values"],
                v[rc + "_MARKED.values"])],
    }


def j13_scan_failures(verdicts, vals):
    """each text of J13 to J15 holds no lock word, and each row's texts name exactly its pinned tables."""
    texts = j13_texts(vals)
    if texts is None:
        return ["review_calibrate: no text"]
    out = []
    for place, ts in sorted(texts.items()):
        tables = set()
        for t in ts:
            v = verdicts(t)
            if any(v[:-1]):
                out.append("%s: a lock word %s" % (place, v[:-1]))
            tables |= set(v[-1])
        if sorted(tables) != JUDGED[place]["tables"]:
            out.append("%s: the tables %s, the pin %s" % (place, sorted(tables), JUDGED[place]["tables"]))
    return out


def test_j13_the_counting_program_texts_hold_no_lock_word_and_name_their_tables(base):
    ns, vals, _rows = base
    assert j13_scan_failures(ns["verdicts"], vals) == []


# ---- RULING-CENSUS-9 section 3 (d): the registry strings J6 and J7 write are read by J12's scan ----------
def registry_failures(reg, seat_text):
    """(1) the strings c.format(s=s) over REPORT_REGISTRY are among MATCH_COLUMNS; (2) m.<name> of every
    MATCH_COLUMNS name stands, a whole word, in SEAT_BASELINE_SQL."""
    out = []
    if not reg["registry"] or not reg["match_columns"]:
        out.append("an empty list")
    out += ["%s: not in MATCH_COLUMNS" % c for c in sorted(set(reg["registry"]) - set(reg["match_columns"]))]
    out += ["%s: not in SEAT_BASELINE_SQL" % n for n in reg["match_columns"] if not re.search(
        r"(?<![A-Za-z0-9_])m\." + re.escape(n) + r"(?![A-Za-z0-9_])", seat_text)]
    return out


def test_j6_j7_every_registry_string_stands_in_the_text_j12_scans(base):
    _ns, vals, _rows = base
    reg = vals["__registry_columns__"]["value"]
    seat = vals["admin_evidence|SEAT_BASELINE_SQL"]["value"]
    assert registry_failures(reg, seat) == []
    assert reg["not_in_match_columns"] == [] and reg["not_in_seat_baseline"] == []    # the child agrees
    assert len(reg["registry"]) == 81 and len(reg["match_columns"]) == 81


def test_j6_j7_the_registry_check_refuses_a_string_outside_and_a_column_unscanned(base):
    _ns, vals, _rows = base
    reg = json.loads(json.dumps(vals["__registry_columns__"]["value"]))
    seat = vals["admin_evidence|SEAT_BASELINE_SQL"]["value"]
    reg2 = dict(reg, registry=reg["registry"] + ["o3_not_a_column"])
    assert registry_failures(reg2, seat) == ["o3_not_a_column: not in MATCH_COLUMNS"]
    n = reg["match_columns"][0]
    seat2 = re.sub(r"(?<![A-Za-z0-9_])m\." + re.escape(n) + r"(?![A-Za-z0-9_])", "m.o3_x", seat)
    assert registry_failures(reg, seat2) == ["%s: not in SEAT_BASELINE_SQL" % n]
    assert registry_failures(reg, seat + "\n") == []                          # control


# ---- RULING-CENSUS-9 section 2: R1 POSITIONAL RETURN, R2 STAR ARGUMENT ------------------------------------
_MODLOG = "main._modlog_answer:27193"
_PROBE = "main._session_report_probe:84068"
_R1_WHERE = '    return (" AND ".join(where) or "TRUE"), params\n'
_R1_AFTER = '    if not f.get("after"):\n        return "TRUE", {}\n'
_R1_BIND = '        params["msince"] = f["since"]\n'
_R2_ROW = '    "ovt": ("ovt_match_cards", False, False),\n'
_R2_COMP = ('_REPORT_CARD_STATEMENTS = {mode: _report_card_sql(*spec) for mode, spec in '
            '_REPORT_CARD_TABLES.items()}\n')


def _row_of(ns0, ns, key):
    return _row_at(ns0["rows"], ns["rows"], key)


def test_r1_the_ruled_place_is_bounded_on_admin_actions_alone(base):
    ns0, _vals, _rows = base
    r = _rows_by_key(ns0["rows"])[_MODLOG]
    assert r["verdict"] == "bounded" and r["widest_tables"] == ["admin_actions"], r
    assert not _locked(r), r


def test_r1_a_lock_word_in_the_first_position_reaches_the_text(base):
    ns0, vals, _rows = base
    ns = _run(_sources((_R1_WHERE, _R1_WHERE.replace('or "TRUE")', 'or "TRUE FOR UPDATE")'))), values=vals)
    b = _row_of(ns0, ns, _MODLOG)
    assert _locked(b), b


def test_r1_a_lock_word_in_the_second_position_a_bind_leaves_the_verdict(base):
    ns0, vals, _rows = base
    ns = _run(_sources((_R1_BIND, '        params["msince"] = "x FOR UPDATE"\n')), values=vals)
    a, b = _rows_by_key(ns0["rows"])[_MODLOG], _row_of(ns0, ns, _MODLOG)
    assert (b["verdict"], b.get("verdict_set")) == (a["verdict"], a.get("verdict_set")), b
    assert _census_line(ns["rows"]) == _census_line(ns0["rows"])


def test_r1_a_return_made_a_name_opens_the_place_and_it_is_red_by_name(base):
    ns0, vals, _rows = base
    ns = _run(_sources((_R1_AFTER, '    if not f.get("after"):\n        _o3_pair = ("TRUE", {})\n'
                                   '        return _o3_pair\n')), values=vals)
    b = _row_of(ns0, ns, _MODLOG)
    assert b["verdict"] == "remaining" and b.get("causes"), b
    fn = _MODLOG.rsplit(":", 1)[0] + ":"
    assert any(x.startswith(fn) and "not in the judged table" in x
               for x in judged_table_failures(ns["rows"], vals)), b


def test_r1_control_a_further_fixed_fragment_leaves_every_count(base):
    ns0, vals, _rows = base
    ns = _run(_sources((_R1_WHERE, _R1_WHERE.replace('or "TRUE")', 'or "TRUE AND TRUE")'))), values=vals)
    a, b = _rows_by_key(ns0["rows"])[_MODLOG], _row_of(ns0, ns, _MODLOG)
    assert (b["verdict"], b.get("verdict_set")) == (a["verdict"], a.get("verdict_set")), b
    assert _census_line(ns["rows"]) == _census_line(ns0["rows"])


def test_r2_the_ruled_place_is_read_by_value(base):
    ns0, _vals, _rows = base
    r = _rows_by_key(ns0["rows"])[_PROBE]
    assert r["verdict"] == "read" and r.get("how") == "exact at the place (VALUE)", r
    assert not _locked(r), r


def test_r2_a_lock_word_in_a_starred_row_reaches_the_probe(base, tmp_path):
    ns0, _vals, _rows = base
    srcs = _sources((_R2_ROW, _R2_ROW.replace('"ovt_match_cards"', '"ovt_match_cards FOR UPDATE"')))
    ns, _v = _measure(srcs, str(tmp_path), main_text=srcs["main"])
    b = _rows_by_key(ns["rows"])[_PROBE]
    assert _locked(b), b


def test_r2_the_starred_expression_made_a_parameter_is_bound_by_its_one_call_and_stays_read(base, tmp_path):
    """`*spec` with spec a parameter of one helper more is no break, because under the per-call binding of
    ruling 9 section 1 spec takes its one call's argument, the comprehension's target, which the standing
    loop form binds to the display's values; the probe stays read with the same verdicts."""
    ns0, _vals, _rows = base
    srcs = _sources((_R2_COMP, 'def _o3_cards(spec):\n    return _report_card_sql(*spec)\n\n\n'
                               '_REPORT_CARD_STATEMENTS = {mode: _o3_cards(_o3_spec) for mode, _o3_spec in '
                               '_REPORT_CARD_TABLES.items()}\n'))
    ns, _v = _measure(srcs, str(tmp_path), main_text=srcs["main"])
    a, b = _rows_by_key(ns0["rows"])[_PROBE], _row_of(ns0, ns, _PROBE)
    assert (b["verdict"], b.get("verdict_set")) == (a["verdict"], a.get("verdict_set")), b


def test_r2_the_dictionary_rebound_to_a_value_the_resolver_cannot_read_opens_the_place_red_by_name(base, tmp_path):
    """R2 binds a loop target over D only where D is bound once to a dict display (VALUE's condition (b)). A
    second binding through a call the resolver does not read (a JSON round trip, the same rows at import) ends
    that, so `*spec` reaches nothing closed and the probe is not read. (A second binding `dict(D)` keeps the
    place read: dict of a closed reach is closed, so it is no break.)"""
    ns0, _vals, _rows = base
    srcs = _sources((_R2_COMP, '_REPORT_CARD_TABLES = _json.loads(_json.dumps(_REPORT_CARD_TABLES))\n' + _R2_COMP))
    ns, v = _measure(srcs, str(tmp_path), main_text=srcs["main"])
    b = _row_of(ns0, ns, _PROBE)
    assert b["verdict"] != "read", b
    fn = _PROBE.rsplit(":", 1)[0] + ":"
    assert any(x.startswith(fn) and "not in the judged table" in x
               for x in judged_table_failures(ns["rows"], v)), b


def test_r2_control_a_row_with_no_lock_word_leaves_every_count(base, tmp_path):
    ns0, _vals, _rows = base
    srcs = _sources((_R2_ROW, _R2_ROW.replace("False, False)", "False, True)")))
    ns, _v = _measure(srcs, str(tmp_path), main_text=srcs["main"])
    a, b = _rows_by_key(ns0["rows"])[_PROBE], _rows_by_key(ns["rows"])[_PROBE]
    assert (b["verdict"], b.get("verdict_set")) == (a["verdict"], a.get("verdict_set")), b
    assert _census_line(ns["rows"]) == _census_line(ns0["rows"])
