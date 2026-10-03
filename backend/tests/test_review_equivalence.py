"""Bars A16 and A17: the generic evaluator under a private rules revision
reproduces a reference implementation exactly.

Everything this test compares against lives OUTSIDE the repository: the
revision, the fixture, the reference outputs, the old-to-new rule map, the
mutations and the reference statements. SCR_REVIEW_PRIVATE_SUITE names the
directory holding them (its suite.json lists the files); unset, the whole
module SKIPS with that reason. When it is set, REVIEW_EQUIV_TEST_PG_DSN must
name a throwaway PostgreSQL database for the sitting half, or those cases
FAIL (a skipped live case reports success for coverage that did not run).

What is asserted, for every rule of the revision:
  * games: the same rules fire on the same games with the same items (exact
    JSON equality) and the same rendered text as the reference;
  * every rule has a positive and a boundary-negative fixture case, and the
    evaluator agrees with both labels;
  * posting: a rule is armed exactly when its reference kind was;
  * every rule has at least one mutation, and every mutation changes the
    finding IDENTITY set exactly as its frozen `expect` states, only on its
    own rule, and every rule keeps its scope and posting. A moved-VALUE
    mutation flips only that rule's labelled boundary cases (lost identities
    are positive labels, gained ones negative labels) and every retained
    identity keeps exactly the same items and line, except the item keys the
    moved value is itself rendered into (its frozen `renders`). A STRUCTURE
    mutation (a rule whose decision has no value to move: its measure,
    relation or literal replaced) loses only positive labels, reaches at
    least one labelled case, and moves nothing outside its own rule;
  * sittings: the OLD statements run UNMODIFIED (the old worker's own
    candidate window, horizon and lag; the fixture plants its cases inside
    that window), and the worker's dirty-set statement (over the sittings of
    that same window) and the tuning tool's literal (with the same window)
    both reproduce the reference rows, grouping, items and text; A17: one
    snapshot, the reference and the literal give the same digest of sorted
    result identities.
"""

import asyncio
import copy
import hashlib
import importlib.util
import json
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import review_rules as rr  # noqa: E402

SUITE = os.environ.get("SCR_REVIEW_PRIVATE_SUITE") or ""
DSN = (os.environ.get("REVIEW_EQUIV_TEST_PG_DSN") or "").replace("postgresql+asyncpg://", "postgresql://")

pytestmark = pytest.mark.skipif(
    not SUITE,
    reason="SCR_REVIEW_PRIVATE_SUITE is unset: the private equivalence suite (bars A16, A17) "
           "needs the private rules revision and its reference, which are not in this repository")


def _p(name):
    return os.path.normpath(os.path.join(SUITE, _manifest()[name]))


def _manifest():
    with open(os.path.join(SUITE, "suite.json"), encoding="utf-8") as f:
        return json.load(f)


def _json(name):
    with open(_p(name), encoding="utf-8") as f:
        return json.load(f)


def _ruleset():
    return rr.load_dir(_p("revision"))


def _reference():
    spec = importlib.util.spec_from_file_location("review_reference", _p("old_reference"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _roundtrip(obj):
    return json.loads(json.dumps(obj, separators=(",", ":")))


def _game_result(rs, g):
    registry = {tuple(t) for t in g["registry"]}
    findings, _fired, errors = rs.evaluate_game(copy.deepcopy(g["records"]), g["match"], registry)
    assert errors == 0, g["name"]
    out = {}
    for rule, det in findings:
        items = _roundtrip(det)["items"]
        out[rule.id] = {"items": items, "line": rs.render_line(rule, items)}
    return out


def _expected_by_rule(kindmap, expected_game):
    return {kindmap[k]: v for k, v in expected_game.items()}


def test_a16_the_rule_map_is_one_to_one_and_covers_the_revision():
    rs = _ruleset()
    kindmap = _json("kindmap")
    assert len(set(kindmap.values())) == len(kindmap)
    assert set(kindmap.values()) == {r.id for r in rs.rules}


def test_a16_games_reproduce_the_reference_items_and_text():
    rs = _ruleset()
    kindmap = _json("kindmap")
    expected = _json("expected")
    games = _json("fixture")
    fired = set()
    for g in games:
        got = _game_result(rs, g)
        want = _expected_by_rule(kindmap, expected[g["name"]])
        assert got == want, g["name"]
        fired |= set(got)
    assert fired == {r.id for r in rs.game_rules}


def test_a16_every_game_rule_has_a_positive_and_a_boundary_negative_case():
    rs = _ruleset()
    kindmap = _json("kindmap")
    games = _json("fixture")
    pos, neg = set(), set()
    for g in games:
        got = _game_result(rs, g)
        for k in g["pos"]:
            assert kindmap[k] in got, (g["name"], "positive")
            pos.add(kindmap[k])
        for k in g["neg"]:
            assert kindmap[k] not in got, (g["name"], "negative")
            neg.add(kindmap[k])
    ids = {r.id for r in rs.game_rules}
    assert ids <= pos and ids <= neg


def test_a16_posting_matches_the_reference_arming():
    rs = _ruleset()
    kindmap = _json("kindmap")
    seeds = _json("old_sitting")["posting_seeds"]
    assert {kindmap[k]: v == "1" for k, v in seeds.items()} == {r.id: r.post for r in rs.rules}


def _mutant(rs, m, kindmap):
    with open(os.path.join(_p("revision"), "rules.json"), encoding="utf-8") as f:
        doc = json.load(f)
    if m["target"] == "rule":
        node = next(r for r in doc["rules"] if r["id"] == kindmap[m["kind"]])
    else:
        node = doc
    for key in m["path"][:-1]:
        node = node[key]
    assert node[m["path"][-1]] != m["value"], "a mutation must change a value"
    node[m["path"][-1]] = m["value"]
    out = rr.compile_rules(doc, rr._Binder(doc["vocabulary"]), {})
    out.rev = "mutant"
    return out


def _same_scope_and_posting(rs, mrs, kind):
    for r in rs.rules:
        mr = mrs.rule(r.id)
        assert (mr.scope, mr.post, mr.post_since) == (r.scope, r.post, r.post_since), kind


def _check_change(m, lose, gain, pos, neg):
    """The intended identity change: exactly the frozen expectation, non-empty,
    only the mutated kind, lost identities positive labels of it; a value
    mutation gains only negative labels, a structure mutation reaches at
    least one labelled case."""
    kind = m["kind"]
    assert m["class"] in ("value", "structure") and "expect" in m, kind
    assert (lose or gain), kind
    assert all(k == kind for _i, k in lose | gain), kind
    assert lose <= pos, kind
    if m["class"] == "value":
        assert gain <= neg, kind
    else:
        assert (lose & pos) or (gain & neg), kind
    assert sorted([list(t) for t in lose]) == m["expect"]["lose"], kind
    assert sorted([list(t) for t in gain]) == m["expect"]["gain"], kind


def _without(items, keys):
    if isinstance(items, list):
        return [_without(x, keys) for x in items]
    if isinstance(items, dict):
        return {k: v for k, v in items.items() if k not in keys}
    return items


def _retained_equal(m, a, b, what):
    """A retained identity is unchanged: exactly, or (value mutations) except
    the frozen keys the moved value is rendered into."""
    if m["class"] == "structure":
        return
    keys = set(m["renders"])
    if isinstance(a, dict) and "items" in a:
        if "line" not in keys:
            assert a["line"] == b["line"], (m["kind"], what, "line")
        a, b = a["items"], b["items"]
    if "n_items" not in keys:
        assert len(a) == len(b), (m["kind"], what, "items")
    if len(a) == len(b):
        assert _without(a, keys) == _without(b, keys), (m["kind"], what)


def test_a16_every_game_rule_mutation_changes_exactly_its_intended_identities():
    rs = _ruleset()
    kindmap = _json("kindmap")
    rid_kind = {v: k for k, v in kindmap.items()}
    games = _json("fixture")
    muts = _json("mutations")
    game_ids = {r.id for r in rs.game_rules}
    pos = {(g["name"], k) for g in games for k in g["pos"]}
    neg = {(g["name"], k) for g in games for k in g["neg"]}
    base = {g["name"]: _game_result(rs, g) for g in games}
    covered = set()
    for m in muts:
        if kindmap[m["kind"]] not in game_ids:
            continue
        mrs = _mutant(rs, m, kindmap)
        _same_scope_and_posting(rs, mrs, m["kind"])
        mut = {g["name"]: _game_result(mrs, g) for g in games}
        b_ids = {(n, rid_kind[x]) for n, res in base.items() for x in res}
        m_ids = {(n, rid_kind[x]) for n, res in mut.items() for x in res}
        _check_change(m, b_ids - m_ids, m_ids - b_ids, pos, neg)
        for n in base:
            for x in set(base[n]) & set(mut[n]):
                if x != kindmap[m["kind"]]:
                    assert mut[n][x] == base[n][x], (m["kind"], "another rule moved")
                else:
                    _retained_equal(m, base[n][x], mut[n][x], n)
        covered.add(kindmap[m["kind"]])
    assert covered == game_ids


# -- the sitting half (live PostgreSQL) -----------------------------------------

_DDL = [
    "CREATE TABLE ranked_series (id uuid PRIMARY KEY, status varchar(20), invalidated_at timestamptz)",
    "CREATE TABLE matches (id uuid PRIMARY KEY, player1_id uuid, player2_id uuid, "
    " ended_at timestamptz, created_at timestamptz, is_ranked boolean, invalidated_at timestamptz, "
    " series_id uuid, p1_bullets_fired int, p2_bullets_fired int, p1_bullets_hit int, "
    " p2_bullets_hit int, p1_blocks_activated int, p2_blocks_activated int, "
    " p1_blocks_successful int, p2_blocks_successful int, p1_ping_avg smallint, "
    " p2_ping_avg smallint, reported_by uuid, p1_obs_batches int, p2_obs_batches int, "
    " duration_seconds int, match_duration int)",
    "CREATE TABLE review_sitting_dirty (pair_lo uuid, pair_hi uuid, day date, "
    " marked_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (pair_lo, pair_hi, day))",
]
_COLS = ("id", "player1_id", "player2_id", "is_ranked", "series_id", "p1_bullets_fired",
         "p2_bullets_fired", "p1_bullets_hit", "p2_bullets_hit", "p1_blocks_activated",
         "p2_blocks_activated", "p1_blocks_successful", "p2_blocks_successful", "p1_ping_avg",
         "p2_ping_avg", "reported_by", "p1_obs_batches", "p2_obs_batches", "duration_seconds",
         "match_duration")


def _require_pg():
    if not DSN:
        pytest.fail("REVIEW_EQUIV_TEST_PG_DSN is unset while SCR_REVIEW_PRIVATE_SUITE is set: "
                    "the sitting half of A16/A17 did not run")


def _sub(sql, binds):
    """Bind by name for asyncpg ($n), in the statement's own order."""
    import re
    names = []

    def rep(m):
        names.append(m.group(1))
        return "$%d" % len(names)
    out = re.sub(r"(?<![:\w]):(\w+)", rep, sql)
    return out, [binds[n] for n in names]


async def _sitting_run(muts=()):
    """One transaction, one snapshot: the fixture loaded, then per sitting rule
    the reference rows, the worker's dirty-set rows and the literal's rows.
    Returns {kind: {...}} plus, per mutation, the mutant's grouped result."""
    import asyncpg
    rs = _ruleset()
    kindmap = _json("kindmap")
    ref = _json("old_sitting")
    fx = _json("sitting_fixture")
    conn = await asyncpg.connect(DSN)
    schema = "review_equiv_" + uuid.uuid4().hex[:12]
    out = {"kinds": {}, "mutants": []}
    try:
        tr = conn.transaction()
        await tr.start()
        await conn.execute("CREATE SCHEMA %s" % schema)
        await conn.execute("SET LOCAL search_path TO %s" % schema)
        for d in _DDL:
            await conn.execute(d)
        for s in fx["series"]:
            await conn.execute("INSERT INTO ranked_series VALUES ($1, $2, CASE WHEN $3 THEN now() END)",
                               uuid.UUID(s["id"]), s["status"], s["invalidated"])
        cols = ", ".join(_COLS)
        ph = ", ".join("$%d" % (i + 1) for i in range(len(_COLS)))
        n = len(_COLS)
        for r in fx["rows"]:
            vals = [uuid.UUID(r[c]) if c in ("id", "player1_id", "player2_id", "series_id",
                                             "reported_by") and r[c] else r[c] for c in _COLS]
            await conn.execute(
                "INSERT INTO matches (%s, ended_at, created_at, invalidated_at) VALUES (%s, "
                "date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' "
                " - make_interval(days => $%d) + make_interval(hours => $%d) + make_interval(mins => $%d), "
                "now(), CASE WHEN $%d THEN now() END)" % (cols, ph, n + 1, n + 2, n + 3, n + 4),
                *vals, r["days_ago"], 12, r["minute"], r["invalidated"])
        # the worker's dirty set over the OLD candidate window only: the same
        # sittings the old worker would have evaluated in this snapshot
        await conn.execute(
            "INSERT INTO review_sitting_dirty (pair_lo, pair_hi, day) "
            "SELECT DISTINCT LEAST(player1_id, player2_id), GREATEST(player1_id, player2_id), "
            "(ended_at AT TIME ZONE 'UTC')::date FROM matches "
            "WHERE (ended_at AT TIME ZONE 'UTC')::date >= (now() AT TIME ZONE 'UTC')::date - CAST($1 AS int)",
            ref["cand_days"])
        snap = await conn.fetchval("SELECT now()")
        today = await conn.fetchval("SELECT (now() AT TIME ZONE 'UTC')::date")
        out["today"] = today
        reference = _reference()
        for kind, sql in ref["sql"].items():
            rule = rs.rule(kindmap[kind])
            old_rows = [dict(r) for r in await conn.fetch(sql)]
            dsql, binds = rs.sitting_statement(rule)
            binds["snap"] = snap
            q, args = _sub(dsql, binds)
            new_rows = [dict(r) for r in await conn.fetch(q, *args)]
            lit = rr.literal(_p("revision"), rule.id, ref["cand_days"])
            lit_rows = [dict(r) for r in await conn.fetch(lit)]
            out["kinds"][kind] = {
                "old": reference.old_items(ref["pair_cols"][kind], old_rows),
                "new": rs.sitting_items(rule, new_rows),
                "lit": rs.sitting_items(rule, lit_rows),
                "old_ids": sorted((str(min(str(r[c]) for c in ref["pair_cols"][kind])),
                                   str(max(str(r[c]) for c in ref["pair_cols"][kind])), str(r["d"]))
                                  for r in old_rows),
                "lit_ids": sorted((str(min(str(r["subject"]), str(r["opponent"]))),
                                   str(max(str(r["subject"]), str(r["opponent"]))), str(r["d"]))
                                  for r in lit_rows),
                "rule": rule,
                "old_lines": [reference.old_line(kind, {"items": it})
                              for _k, _m, it in reference.old_items(ref["pair_cols"][kind], old_rows)],
            }
        for m in muts:
            mrs = _mutant(rs, m, kindmap)
            rule = mrs.rule(kindmap[m["kind"]])
            dsql, binds = mrs.sitting_statement(rule)
            binds["snap"] = snap
            q, args = _sub(dsql, binds)
            rows = [dict(r) for r in await conn.fetch(q, *args)]
            out["mutants"].append((m, mrs.sitting_items(rule, rows)))
        await tr.rollback()
    finally:
        await conn.close()
    return out


def _digest(ids):
    return hashlib.sha256("\n".join("|".join(t) for t in ids).encode()).hexdigest()


@pytest.fixture(scope="module")
def sittings():
    _require_pg()
    kindmap = _json("kindmap")
    rs = _ruleset()
    sitting_ids = {r.id for r in rs.sitting_rules}
    muts = [m for m in _json("mutations") if kindmap[m["kind"]] in sitting_ids]
    return asyncio.run(_sitting_run(muts))


def test_a16_sittings_reproduce_the_reference_rows_items_and_text(sittings):
    rs = _ruleset()
    assert set(sittings["kinds"]) and {_json("kindmap")[k] for k in sittings["kinds"]} == \
        {r.id for r in rs.sitting_rules}
    for kind, k in sittings["kinds"].items():
        assert k["old"], kind
        assert k["new"] == k["old"], kind
        assert k["lit"] == k["old"], kind
        lines = [rs.render_line(k["rule"], it) for _d, _m, it in k["new"]]
        assert lines == k["old_lines"], kind


def test_a16_every_sitting_rule_has_a_positive_and_a_boundary_negative_case(sittings):
    import datetime
    fx = _json("sitting_fixture")
    kindmap = _json("kindmap")
    today = sittings["today"]

    def ident(p):
        a, b = sorted(p["pair"])
        return "%s|%s|%s" % (a, b, today - datetime.timedelta(days=p["days_ago"]))
    for p in fx["pos"]:
        assert ident(p) in {d for d, _m, _i in sittings["kinds"][p["kind"]]["new"]}, p["kind"]
    for p in fx["neg"]:
        assert ident(p) not in {d for d, _m, _i in sittings["kinds"][p["kind"]]["new"]}, p["kind"]
    rs = _ruleset()
    assert {kindmap[p["kind"]] for p in fx["pos"]} == {r.id for r in rs.sitting_rules}
    assert {kindmap[p["kind"]] for p in fx["neg"]} == {r.id for r in rs.sitting_rules}


def test_a16_every_sitting_rule_mutation_changes_exactly_its_intended_identities(sittings):
    import datetime
    kindmap = _json("kindmap")
    fx = _json("sitting_fixture")
    rs = _ruleset()
    today = sittings["today"]

    def ident(p):
        a, b = sorted(p["pair"])
        return "%s|%s|%s" % (a, b, today - datetime.timedelta(days=p["days_ago"]))
    pos = {(ident(p), p["kind"]) for p in fx["pos"]}
    neg = {(ident(p), p["kind"]) for p in fx["neg"]}
    covered = set()
    for m, got in sittings["mutants"]:
        kind = m["kind"]
        _same_scope_and_posting(rs, _mutant(rs, m, kindmap), kind)
        b_new = {d: it for d, _m, it in sittings["kinds"][kind]["new"]}
        m_new = {d: it for d, _m, it in got}
        _check_change(m, {(d, kind) for d in set(b_new) - set(m_new)},
                      {(d, kind) for d in set(m_new) - set(b_new)}, pos, neg)
        for d in set(b_new) & set(m_new):
            _retained_equal(m, b_new[d], m_new[d], d)
        covered.add(kindmap[kind])
    assert covered == {r.id for r in rs.sitting_rules}


def test_m6_the_old_statements_run_unmodified():
    """The reference statements carry the old worker's own candidate window
    (the private generator calls the old literal with no override), and the
    worker's dirty set and the literal here use that same window."""
    ref = _json("old_sitting")
    for kind, sql in ref["sql"].items():
        assert "::date - CAST(%d AS int)" % ref["cand_days"] in sql, kind


def test_a17_one_snapshot_gives_the_same_identity_digest(sittings):
    for kind, k in sittings["kinds"].items():
        assert k["old_ids"], kind
        assert _digest(k["lit_ids"]) == _digest(k["old_ids"]), kind
