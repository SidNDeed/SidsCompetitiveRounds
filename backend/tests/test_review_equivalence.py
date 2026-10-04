"""Bars A16 and A17: the generic evaluator under a private rules revision
reproduces a reference implementation exactly.

The OLD SEMANTICS come from the old worker itself: its own source at
commit OLD_WORKER_REV (the api module, the bot's line renderer and the
migration that seeded its settings), read from git and checked against the
digest pinned here per file before a line of it runs. The games run through
the old module's own evaluate_game and bounding; the sittings through the old
module's own sitting pass, unmodified, over a throwaway schema (its statements, its
grouping, its stored details, its settings as its migration seeded them).
The private suite's frozen reference files must equal what that bound oracle
produces, exactly, or the test fails. The old module's own names for the
parts the oracle calls are private: suite.json's `oracle_names` maps each
role to its name, and every name is resolved against the bound module (a
name it lacks fails).

Everything else this test reads lives OUTSIDE the repository: the revision,
the fixture, the old-to-new rule map and the mutations.
SCR_REVIEW_PRIVATE_SUITE names the
directory holding them (its suite.json lists the files); unset, the whole
module SKIPS with that reason. When it is set, REVIEW_EQUIV_TEST_PG_DSN must
name a throwaway PostgreSQL database for the sitting half, or those cases
FAIL (a skipped live case reports success for coverage that did not run).

What is asserted, for every rule of the revision:
  * games: the same rules fire on the same games with the same stored
    details (exact JSON equality, after each side's own bounding) and the same
    rendered text as the bound oracle;
  * every rule has a positive and a boundary-negative fixture case, and the
    evaluator agrees with both labels;
  * posting: a rule is armed exactly when its old kind was, as the old
    migration seeded its per-kind posting switch (the old setting default
    otherwise);
  * every rule has at least one mutation, and every mutation changes the
    finding IDENTITY set exactly as its frozen `expect` states, only on its
    own rule, and every rule keeps its scope and posting. A mutation's
    frozen metadata names ONLY its expected gains and losses: every retained
    identity keeps exactly the same stored details and line, with no key
    exempt. A moved-VALUE mutation flips only that rule's labelled boundary
    cases (lost identities are positive labels, gained ones negative labels).
    A STRUCTURE mutation (a rule whose decision has no value to move: its
    measure, relation or literal replaced) loses only positive labels,
    reaches at least one labelled case, and moves nothing outside its own
    rule;
  * sittings: the old worker's sitting pass runs UNMODIFIED (its own candidate
    window, horizon and lag; the fixture plants its cases inside that
    window), and the worker's dirty-set statement (over the sittings of that
    same window) and the tuning tool's literal (with the same window) both
    reproduce its stored findings: rows, grouping, details and text; A17:
    one snapshot, the old statements and the literal give the same digest of
    sorted result identities.
"""

import ast
import asyncio
import copy
import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
import types
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import review_rules as rr  # noqa: E402
import seat_evidence as se  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "..", ".."))

# The old worker: the commit and, per file, the sha256 of its blob. The oracle
# is loaded from exactly these bytes or not at all.
OLD_WORKER_REV = "7ae3bf042a4fc397bf5fb4a185e49a429e4acd32"
OLD_WORKER_FILES = {
    "backend/api/seat_evidence.py": "00ee66dd66e710af446da596081c312fdd86689c2ce85bfd678588384921b5d9",
    "backend/discord_bot.py": "1a3e9ee6684690c2474179fa8af747f2acb36b57e6f6de9c14ee29a40b721fbb",
    "backend/sql/368_seat_evidence.sql": "4777737aee28c764abf8f5a3cf620c920c71ab8f052a8facea5d17dc6a362538",
}
ORACLE_ROLES = ("kinds", "cand_days", "pair_cols", "sql", "literal", "sitting_pass", "post_prefix",
                "line", "line_helpers")
MUTATION_KEYS = {"class", "expect", "kind", "path", "target", "value"}

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


class OracleRefused(AssertionError):
    """The old worker's source is not the bound one."""


def _old_blob(path, rev=OLD_WORKER_REV):
    """One file of the old worker, from git, checked against its pinned digest."""
    if path not in OLD_WORKER_FILES:
        raise OracleRefused("not a bound file: " + path)
    raw = subprocess.run(["git", "-C", REPO, "cat-file", "blob", "%s:%s" % (rev, path)],
                         capture_output=True, check=True).stdout
    if hashlib.sha256(raw).hexdigest() != OLD_WORKER_FILES[path]:
        raise OracleRefused("differs from its pinned digest: " + path)
    return raw.decode("utf-8")


_ORACLE = {}


def _oracle():
    """The complete old-semantics oracle from the bound source: the old api
    module whole, the old bot's renderer functions verbatim, and the settings
    the old migration seeded."""
    if _ORACLE:
        return _ORACLE
    names = _manifest()["oracle_names"]
    assert set(names) == set(ORACLE_ROLES), "oracle_names must map exactly the oracle roles"
    mod = types.ModuleType("review_old_worker")
    mod.__file__ = "old_worker/backend/api/seat_evidence.py"
    sys.modules[mod.__name__] = mod
    exec(compile(_old_blob("backend/api/seat_evidence.py"), mod.__file__, "exec"), mod.__dict__)
    bot = _old_blob("backend/discord_bot.py")
    segs = [ast.get_source_segment(bot, n) for n in ast.parse(bot).body
            if isinstance(n, ast.FunctionDef) and n.name in names["line_helpers"] + [names["line"]]]
    assert len(segs) == len(names["line_helpers"]) + 1
    ns = {"json": json}
    exec(compile("\n\n\n".join(segs), "old_worker/backend/discord_bot.py", "exec"), ns)
    mig = _old_blob("backend/sql/368_seat_evidence.sql")
    block = mig[mig.index("INSERT INTO runtime_settings"):]
    block = block[:block.index(";")]
    settings = dict(re.findall(r"\(\s*'([a-z0-9_]+)',\s*'([^']*)'\s*\)", block))
    default = inspect.signature(mod.setting).parameters["default"].default
    _ORACLE.update({
        "mod": mod, "line": ns[names["line"]], "settings": settings,
        "posting": {k: settings.get(getattr(mod, names["post_prefix"]) + k, default) == "1"
                    for k in mod.KINDS},
    })
    for role in ("kinds", "cand_days", "pair_cols", "sql", "literal", "sitting_pass"):
        _ORACLE[role] = getattr(mod, names[role])
    return _ORACLE


def _old_game_result(g):
    """The old worker's findings for one game, as it stored and rendered them."""
    o = _oracle()
    registry = {tuple(t) for t in g["registry"]}
    findings, _view = o["mod"].evaluate_game(copy.deepcopy(g["records"]), g["match"], registry)
    out = {}
    for kind, det in findings:
        det = json.loads(o["mod"]._dumps(o["mod"].bounded(det)))
        out[kind] = {"items": det["items"], "line": o["line"](kind, det)}
    return out


def _frozen_reference_differs(ref, expected, games):
    """Every key where the private suite's frozen reference differs from the
    bound oracle (empty = identical)."""
    o = _oracle()
    want = {"cand_days": o["cand_days"],
            "pair_cols": {k: list(v) for k, v in o["pair_cols"].items()},
            "sql": {k: o["literal"](k) for k in o["kinds"]},
            "posting_seeds": {k: "1" if v else "0" for k, v in o["posting"].items()}}
    bad = sorted(k for k in set(want) | set(ref) if ref.get(k) != want.get(k))
    bad += sorted("game:" + g["name"] for g in games if expected.get(g["name"]) != _old_game_result(g))
    return bad


def _stored(details):
    """A finding's details as the new worker stores them."""
    return json.loads(se._dumps(se.bounded_details(details)))


def _roundtrip(obj):
    return json.loads(json.dumps(obj, separators=(",", ":")))


def _game_result(rs, g):
    registry = {tuple(t) for t in g["registry"]}
    findings, _fired, errors = rs.evaluate_game(copy.deepcopy(g["records"]), g["match"], registry)
    assert errors == 0, g["name"]
    out = {}
    for rule, det in findings:
        items = _stored(_roundtrip(det))["items"]
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
        oracle = _old_game_result(g)
        assert expected[g["name"]] == oracle, (g["name"], "frozen reference")
        assert got == _expected_by_rule(kindmap, oracle), g["name"]
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
    posting = _oracle()["posting"]
    assert set(posting) == set(kindmap)
    assert {kindmap[k]: v for k, v in posting.items()} == {r.id: r.post for r in rs.rules}


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
    assert set(m) == MUTATION_KEYS, (kind, "frozen metadata is gains and losses only")
    assert m["class"] in ("value", "structure"), kind
    assert (lose or gain), kind
    assert all(k == kind for _i, k in lose | gain), kind
    assert lose <= pos, kind
    if m["class"] == "value":
        assert gain <= neg, kind
    else:
        assert (lose & pos) or (gain & neg), kind
    assert sorted([list(t) for t in lose]) == m["expect"]["lose"], kind
    assert sorted([list(t) for t in gain]) == m["expect"]["gain"], kind


def _retained_equal(m, a, b, what):
    """A retained identity is unchanged, exactly: every stored detail and the
    rendered line, whatever the mutation's class. Nothing is exempt."""
    assert a == b, (m["kind"], what, "a retained identity moved")


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
    # what the old worker's own sitting pass reads and writes
    "CREATE TABLE runtime_settings (key varchar(80) PRIMARY KEY, value text)",
    "CREATE TABLE seat_evidence_findings (id bigserial PRIMARY KEY, "
    " scope varchar(8) NOT NULL DEFAULT 'game', dedup_key varchar(160) NOT NULL, "
    " kind varchar(40) NOT NULL, match_id uuid, details jsonb NOT NULL DEFAULT '{}'::jsonb, "
    " computed_at timestamptz NOT NULL DEFAULT now(), changed_at timestamptz NOT NULL DEFAULT now(), "
    " flag_id uuid, UNIQUE (scope, dedup_key, kind))",
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


class _OldResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return [dict(r) for r in self.rows]

    def first(self):
        return self.rows[0] if self.rows else None


async def _old_pass(conn):
    """The old worker's sitting pass, unmodified, on this connection and snapshot:
    a session whose execute runs each statement as written (binds by name).
    Returns the rows each old statement returned and the findings it stored."""
    o = _oracle()
    rows = {}

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, stmt, params=None):
            sql = stmt.text
            q, args = _sub(sql, dict(params or {}))
            got = await conn.fetch(q, *args)
            for kind, ksql in o["sql"].items():
                if sql == ksql:
                    rows[kind] = [dict(r) for r in got]
            return _OldResult(got)

        async def commit(self):
            return None

        async def rollback(self):
            return None

    stats = await o["sitting_pass"](Session)
    assert set(stats) == set(o["kinds"]) and all(type(v) is int for v in stats.values()), stats
    found = {k: [] for k in o["kinds"]}
    for r in await conn.fetch("SELECT kind, dedup_key, match_id, details FROM seat_evidence_findings "
                              "WHERE scope = 'sitting'"):
        found[r["kind"]].append((r["dedup_key"], r["match_id"], json.loads(r["details"])))
    for k in found:
        found[k].sort(key=lambda t: t[0])
    return rows, found


def _new_sitting(rs, rule, rows):
    return [(d, m, _stored({"items": it})) for d, m, it in rs.sitting_items(rule, rows)]


async def _sitting_run(muts=()):
    """One transaction, one snapshot: the fixture loaded, the old worker's
    pass, then per sitting rule the worker's dirty-set rows and the literal's
    rows. Returns {kind: {...}} plus, per mutation, the mutant's result."""
    import asyncpg
    rs = _ruleset()
    kindmap = _json("kindmap")
    o = _oracle()
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
        for k, v in o["settings"].items():
            await conn.execute("INSERT INTO runtime_settings (key, value) VALUES ($1, $2)", k, v)
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
            o["cand_days"])
        snap = await conn.fetchval("SELECT now()")
        today = await conn.fetchval("SELECT (now() AT TIME ZONE 'UTC')::date")
        out["today"] = today
        old_rows, found = await _old_pass(conn)
        for kind in o["kinds"]:
            rule = rs.rule(kindmap[kind])
            dsql, binds = rs.sitting_statement(rule)
            binds["snap"] = snap
            q, args = _sub(dsql, binds)
            new_rows = [dict(r) for r in await conn.fetch(q, *args)]
            lit = rr.literal(_p("revision"), rule.id, o["cand_days"])
            lit_rows = [dict(r) for r in await conn.fetch(lit)]
            ca, cb = o["pair_cols"][kind]
            out["kinds"][kind] = {
                "old": found[kind],
                "new": _new_sitting(rs, rule, new_rows),
                "lit": _new_sitting(rs, rule, lit_rows),
                "old_ids": sorted((str(min(str(r[ca]), str(r[cb]))), str(max(str(r[ca]), str(r[cb]))),
                                   str(r["d"])) for r in old_rows[kind]),
                "lit_ids": sorted((str(min(str(r["subject"]), str(r["opponent"]))),
                                   str(max(str(r["subject"]), str(r["opponent"]))), str(r["d"]))
                                  for r in lit_rows),
                "rule": rule,
                "old_lines": [o["line"](kind, det) for _d, _m, det in found[kind]],
            }
        for m in muts:
            mrs = _mutant(rs, m, kindmap)
            rule = mrs.rule(kindmap[m["kind"]])
            dsql, binds = mrs.sitting_statement(rule)
            binds["snap"] = snap
            q, args = _sub(dsql, binds)
            rows = [dict(r) for r in await conn.fetch(q, *args)]
            out["mutants"].append((m, _new_sitting(mrs, rule, rows)))
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
        lines = [rs.render_line(k["rule"], det["items"]) for _d, _m, det in k["new"]]
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


def test_m6_the_frozen_reference_is_exactly_the_bound_oracle():
    """The private suite's frozen statements, window, pair columns, posting
    seeds and game outputs equal what the bound old worker produces, whole."""
    assert _frozen_reference_differs(_json("old_sitting"), _json("expected"), _json("fixture")) == []


def test_m6_control_a_changed_reference_keeping_the_window_substring_is_caught():
    ref = _json("old_sitting")
    kind = sorted(ref["sql"])[0]
    window = "::date - CAST(%d AS int)" % ref["cand_days"]
    assert window in ref["sql"][kind]
    changed = copy.deepcopy(ref)
    changed["sql"][kind] = changed["sql"][kind].replace(" WHERE ", " WHERE TRUE AND ", 1)
    assert changed["sql"][kind] != ref["sql"][kind] and window in changed["sql"][kind]
    assert _frozen_reference_differs(changed, _json("expected"), _json("fixture")) == ["sql"]
    games = _json("fixture")
    expected = copy.deepcopy(_json("expected"))
    name = next(g["name"] for g in games if expected[g["name"]])
    k = sorted(expected[name])[0]
    expected[name][k]["line"] += " "
    assert _frozen_reference_differs(ref, expected, games) == ["game:" + name]


def test_m6_control_old_source_other_than_the_bound_bytes_is_refused():
    with pytest.raises(OracleRefused):
        _old_blob("backend/api/seat_evidence.py", rev="HEAD")
    with pytest.raises(OracleRefused):
        _old_blob("backend/api/review_rules.py")


def test_m6_control_an_overbroad_retained_output_exemption_is_caught():
    m = {"kind": "k", "class": "value", "path": ["x"], "target": "rule", "value": 1,
         "expect": {"lose": [["g", "k"]], "gain": []}}
    _check_change(m, {("g", "k")}, set(), {("g", "k")}, set())             # control
    with pytest.raises(AssertionError):
        _check_change(dict(m, renders=["line"]), {("g", "k")}, set(), {("g", "k")}, set())
    a = {"items": [{"subject_is_lo": True, "n": 3}], "line": "x"}
    _retained_equal(m, a, copy.deepcopy(a), "g")                             # control
    for cls in ("value", "structure"):
        with pytest.raises(AssertionError):
            _retained_equal(dict(m, **{"class": cls}), a, {"items": [{"subject_is_lo": True, "n": 4}],
                                                         "line": "x"}, "g")
        with pytest.raises(AssertionError):
            _retained_equal(dict(m, **{"class": cls}), a, dict(a, line="y"), "g")


def test_a17_one_snapshot_gives_the_same_identity_digest(sittings):
    for kind, k in sittings["kinds"].items():
        assert k["old_ids"], kind
        assert _digest(k["lit_ids"]) == _digest(k["old_ids"]), kind
