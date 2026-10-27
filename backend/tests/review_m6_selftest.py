"""The public selftest fixture of the M6 mutant driver
(backend/tools/review_m6_mutants.py --selftest): a SYNTHETIC suite of the
private equivalence suite's shape, and tests that read it the way
test_review_equivalence.py reads the private one, under the same names.

Nothing here is private: every value is synthetic and visibly arbitrary. The
suite's manifest (suite.json) has the private manifest's keys, and its files
have the private files' structure at every position a mutant changes:
  old_sitting  the frozen reference: cand_days, pair_cols, sql (one
               statement per sitting kind, holding the candidate window text
               `::date - CAST(<cand_days> AS int)` after a WHERE) and
               posting_seeds;
  expected     the frozen game outputs: game name -> kind -> items and line;
  mutations    sitting and game mutations, each with exactly the frozen keys
               (the first is a SITTING mutation, so the driver must pass over
               it to reach the first game mutation);
  revision     a directory whose rules.json lists each rule's id and scope;
  kindmap, fixture, sitting_fixture as the tests below read them.
Each target test mirrors the real test its mutant targets, and the mutation
checks run the REAL comparator: MUTATION_KEYS and _check_change are compiled
from test_review_equivalence.py's own source (that module is never imported
here: its import reads the private suite's location). The two real-path
controls read only the sitting mutations, as the real ones do, through the
real retained-identity helpers of seat_evidence_fixtures.

REVIEW_M6_SELFTEST_SUITE names the suite; unset, every test here skips. The
file is not named test_*: it runs only when named on the command line."""

import ast
import copy
import json
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SUITE_ENV = "REVIEW_M6_SELFTEST_SUITE"
SUITE = os.environ.get(SUITE_ENV) or ""
pytestmark = pytest.mark.skipif(not SUITE, reason=SUITE_ENV + " is unset: run it through "
                                "backend/tools/review_m6_mutants.py --selftest")

RULES = [{"id": "r0000f7b1", "scope": "game", "threshold": 3},
         {"id": "r0000f7b2", "scope": "game", "threshold": 7},
         {"id": "r0000f7b3", "scope": "sitting", "threshold": 10}]
KINDMAP = {"kind_a": "r0000f7b1", "kind_b": "r0000f7b2", "kind_s": "r0000f7b3"}
GAMES = [{"name": "game_one", "values": {"kind_a": 5, "kind_b": 9}, "pos": ["kind_a", "kind_b"], "neg": []},
         {"name": "game_two", "values": {"kind_a": 2, "kind_b": 4}, "pos": [], "neg": ["kind_a", "kind_b"]}]
ROWS = [{"pair": ["p2", "p1"], "day": 1, "value": 12}, {"pair": ["p3", "p4"], "day": 2, "value": 15},
        {"pair": ["p5", "p6"], "day": 3, "value": 8}]
SITTING_FIXTURE = {"rows": ROWS,
                   "pos": [{"ident": "p1|p2|day1", "kind": "kind_s"}, {"ident": "p3|p4|day2", "kind": "kind_s"}],
                   "neg": [{"ident": "p5|p6|day3", "kind": "kind_s"}]}
MUTATIONS = [
    {"kind": "kind_s", "class": "value", "path": ["threshold"], "target": "rule", "value": 13,
     "expect": {"lose": [["p1|p2|day1", "kind_s"]], "gain": []}},
    {"kind": "kind_a", "class": "value", "path": ["threshold"], "target": "rule", "value": 6,
     "expect": {"lose": [["game_one", "kind_a"]], "gain": []}},
    {"kind": "kind_b", "class": "value", "path": ["threshold"], "target": "rule", "value": 3,
     "expect": {"lose": [], "gain": [["game_two", "kind_b"]]}},
]
CAND_DAYS = 14
MANIFEST = {"revision": "revision", "kindmap": "selftest_kinds.json", "expected": "expected.json",
            "fixture": "selftest_games.json", "mutations": "selftest_changes.json",
            "sitting_fixture": "selftest_rows.json", "old_sitting": "old_sitting.json",
            "oracle_names": {"line": "selftest_line"}}


def _rule(rules, kind, kindmap=KINDMAP):
    return next(r for r in rules if r["id"] == kindmap[kind])


def reference():
    """The selftest oracle's frozen reference (what old_sitting must equal)."""
    sql = {}
    for kind in sorted(KINDMAP):
        rule = _rule(RULES, kind)
        if rule["scope"] == "sitting":
            sql[kind] = ("SELECT m.player1_id, m.player2_id FROM matches m WHERE m.ended_at::date >= "
                         "now()::date - CAST(%d AS int) AND m.value >= %d" % (CAND_DAYS, rule["threshold"]))
    return {"cand_days": CAND_DAYS, "pair_cols": {k: ["player1_id", "player2_id"] for k in sql}, "sql": sql,
            "posting_seeds": {k: "1" if k == "kind_a" else "0" for k in sorted(KINDMAP)}}


def game_result(rules, g):
    """One game's outputs under `rules`: kind -> items and line."""
    out = {}
    for kind in sorted(KINDMAP):
        rule, v = _rule(rules, kind), g["values"].get(kind)
        if rule["scope"] == "game" and v is not None and v > rule["threshold"]:
            out[kind] = {"items": [{"v": v}], "line": "selftest %s %d" % (kind, v)}
    return out


def build(root):
    """Write the selftest suite into the directory root; return root."""
    os.makedirs(os.path.join(root, "revision"))
    files = {"suite.json": MANIFEST, "selftest_kinds.json": KINDMAP, "selftest_games.json": GAMES,
             "expected.json": {g["name"]: game_result(RULES, g) for g in GAMES},
             "selftest_changes.json": MUTATIONS, "selftest_rows.json": SITTING_FIXTURE,
             "old_sitting.json": reference(), os.path.join("revision", "rules.json"): {"rules": RULES}}
    for name, obj in files.items():
        with open(os.path.join(root, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=1, sort_keys=True)
    return root


# -- the suite, read as the equivalence suite reads its own -----------------------

def _manifest():
    with open(os.path.join(SUITE, "suite.json"), encoding="utf-8") as f:
        return json.load(f)


def _p(name):
    return os.path.normpath(os.path.join(SUITE, _manifest()[name]))


def _json(name):
    with open(_p(name), encoding="utf-8") as f:
        return json.load(f)


def _rules():
    with open(os.path.join(_p("revision"), "rules.json"), encoding="utf-8") as f:
        return json.load(f)["rules"]


_REAL = {}


def _real():
    """MUTATION_KEYS and _check_change, compiled from the equivalence suite's
    own source (module-level definitions only; the module is not run)."""
    if not _REAL:
        path = os.path.join(HERE, "test_review_equivalence.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        want = {"MUTATION_KEYS", "_check_change"}
        segs = [ast.get_source_segment(src, n) for n in ast.parse(src).body
                if (isinstance(n, ast.FunctionDef) and n.name in want)
                or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in want for t in n.targets))]
        ns = {}
        exec(compile("\n\n\n".join(segs), path, "exec"), ns)
        assert want <= set(ns), "the equivalence suite's comparator was not found"
        _REAL.update(ns)
    return _REAL


def _mutant(rules, m, kindmap):
    rules = copy.deepcopy(rules)
    assert m["target"] == "rule", "the selftest mutates rules only"
    node = _rule(rules, m["kind"], kindmap)
    for key in m["path"][:-1]:
        node = node[key]
    assert node[m["path"][-1]] != m["value"], "a mutation must change a value"
    node[m["path"][-1]] = m["value"]
    return rules


def test_m6_the_frozen_reference_is_exactly_the_bound_oracle():
    """The frozen reference and the frozen game outputs equal the selftest oracle, whole."""
    assert _json("old_sitting") == reference()
    assert _json("expected") == {g["name"]: game_result(RULES, g) for g in _json("fixture")}


def test_a16_games_reproduce_the_reference_items_and_text():
    rules, expected = _rules(), _json("expected")
    for g in _json("fixture"):
        oracle = game_result(RULES, g)
        assert expected[g["name"]] == oracle, (g["name"], "frozen reference")
        assert game_result(rules, g) == oracle, g["name"]


def test_a16_every_game_rule_mutation_changes_exactly_its_intended_identities():
    rules, kindmap, games = _rules(), _json("kindmap"), _json("fixture")
    game_ids = {r["id"] for r in rules if r["scope"] == "game"}
    pos = {(g["name"], k) for g in games for k in g["pos"]}
    neg = {(g["name"], k) for g in games for k in g["neg"]}
    base = {g["name"]: game_result(rules, g) for g in games}
    covered = set()
    for m in _json("mutations"):
        if kindmap[m["kind"]] not in game_ids:
            continue
        mut = {g["name"]: game_result(_mutant(rules, m, kindmap), g) for g in games}
        b_ids = {(n, k) for n, res in base.items() for k in res}
        m_ids = {(n, k) for n, res in mut.items() for k in res}
        _real()["_check_change"](m, b_ids - m_ids, m_ids - b_ids, pos, neg)
        for n in base:
            for k in set(base[n]) & set(mut[n]):
                assert mut[n][k] == base[n][k], (m["kind"], "a retained identity moved")
        covered.add(kindmap[m["kind"]])
    assert covered == game_ids


# -- the sitting half: the two real-path controls read only sitting mutations -----

def _sitting(rule, rows):
    """A sitting rule's (identity, match anchor, stored details) entries."""
    out = []
    for r in rows:
        if r["value"] >= rule["threshold"]:
            ident = "%s|%s|day%d" % (tuple(sorted(r["pair"])) + (r["day"],))
            out.append((ident, "anchor " + ident, {"items": [{"value": r["value"]}]}))
    return out


def _render(items):
    return "selftest sitting %d" % items[0]["value"]


def _sitting_mutants():
    """[(mutation, base entries, mutant entries)] for every sitting mutation."""
    rules, kindmap, sfx = _rules(), _json("kindmap"), _json("sitting_fixture")
    sitting_ids = {r["id"] for r in rules if r["scope"] == "sitting"}
    return [(m, _sitting(_rule(rules, m["kind"], kindmap), sfx["rows"]),
             _sitting(_rule(_mutant(rules, m, kindmap), m["kind"], kindmap), sfx["rows"]))
            for m in _json("mutations") if kindmap[m["kind"]] in sitting_ids]


def _sitting_mutations(alter=None):
    """The sitting mutation check (the real one's mirror): exactly the intended
    identities gained and lost (the real comparator), and every retained
    identity's complete triple unchanged. `alter` exists for the controls."""
    import seat_evidence_fixtures as fx   # on first use: building the suite needs none of it
    kindmap, sfx = _json("kindmap"), _json("sitting_fixture")
    pos = {(p["ident"], p["kind"]) for p in sfx["pos"]}
    neg = {(p["ident"], p["kind"]) for p in sfx["neg"]}
    covered, retained = set(), 0
    for m, base_entries, got in _sitting_mutants():
        kind, render = m["kind"], _render
        if alter is not None:
            got, render = alter(m, got, render)
        base = fx.retained_triples(base_entries, _render)
        mut = fx.retained_triples(got, render)
        _real()["_check_change"](m, {(d, kind) for d in set(base) - set(mut)},
                                 {(d, kind) for d in set(mut) - set(base)}, pos, neg)
        moved = fx.retained_moved(base, mut)
        assert moved == [], (kind, "a retained identity moved", moved)
        retained += len(set(base) & set(mut))
        covered.add(kindmap[kind])
    assert covered == {r["id"] for r in _rules() if r["scope"] == "sitting"}
    return retained


def _first_retained():
    for m, base, got in _sitting_mutants():
        both = sorted({d for d, _a, _s in base} & {d for d, _a, _s in got})
        if both:
            return m, both[0], got
    raise AssertionError("no mutation retains an identity")


def test_a16_every_sitting_rule_mutation_changes_exactly_its_intended_identities():
    assert _sitting_mutations() > 0, "no mutation retains an identity: the triple check is vacuous"


def test_m6_control_a_retained_anchor_changed_alone_is_caught():
    tm, target, _got = _first_retained()

    def alter(m, got, render):
        if m != tm:
            return got, render
        return [(d, uuid.uuid4() if d == target else a, s) for d, a, s in got], render
    with pytest.raises(AssertionError) as e:
        _sitting_mutations(alter)
    assert "a retained identity moved" in str(e.value) and "['anchor']" in str(e.value)


def test_m6_control_a_retained_line_changed_alone_is_caught():
    tm, target, tgot = _first_retained()
    items = next(s["items"] for d, _a, s in tgot if d == target)

    def alter(m, got, render):
        if m != tm:
            return got, render
        return got, (lambda it, _r=render: _r(it) + (" " if it == items else ""))
    with pytest.raises(AssertionError) as e:
        _sitting_mutations(alter)
    assert "a retained identity moved" in str(e.value) and "['line']" in str(e.value)
