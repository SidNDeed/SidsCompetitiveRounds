"""Animal title ladders — the catalogue, the rules, and the migration, executed.

Three things this file is here to stop:

  * the module and migration 331 drifting apart. 331 is GENERATED from
    ``title_ladders.LADDERS``; ``test_migration_rows_match_module`` re-derives
    every row from the module and compares, so a hand-edit of either side is a
    test failure rather than a table that disagrees with the API reading it.
  * a rung tier going quietly wrong at a boundary. Every threshold is probed
    at threshold-1 and at threshold, and the boundary test carries a mutation
    control so it cannot pass vacuously.
  * the hidden-pool string drifting away from the two places in main.py that
    give it its meaning. If ``HIDDEN_POOL`` stops matching what
    ``/shop/items`` appends and what the purchase path refuses, the rungs
    become invisible to their owners and buyable by anyone — #151, exactly.

It also carries the per-MODE hook-coverage check. That one is INERT today and
says so out loud: the four completion sites are not wired yet. The moment the
first one is, it asserts all four and exactly one call inside each — never
"one call per function" as a global rule, which is the check that passes while
a whole mode goes unhooked. 1v2 is the fifth symbol and is asserted the other
way round: it must exist and must NOT be hooked, because it reports unrated.
"""

import ast
import asyncio
import io
import os
import re
import sys
import textwrap
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import title_ladders as tl  # noqa: E402
import main  # noqa: E402  (late-imported by the hook; patched in the behavioural tests)

API_DIR = os.path.abspath(os.path.join(HERE, "..", "api"))
SQL_DIR = os.path.abspath(os.path.join(HERE, "..", "sql"))
MIGRATION = os.path.join(SQL_DIR, "331_animal_title_ladders.sql")
MAIN_PY = os.path.join(API_DIR, "main.py")
MODULE_PY = os.path.join(API_DIR, "title_ladders.py")

# The completion sites, re-derived by SYMBOL. 2v2 has TWO: the ordinary report
# and the forfeit/disconnect settlement that runs after the fact.
COMPLETION_SITES = {
    "1v1": "submit_match",
    "2v2": "submit_team_match",
    "2v2-settled": "_complete_team_series_with_ratings",
    "ffa": "submit_ffa_match",
}

# 1v2 is a completion site that must NOT be hooked, and it is kept here rather
# than deleted for that reason. A mode dropped from the dict above is
# indistinguishable from a mode nobody got round to, which is precisely the
# failure the coverage check exists to catch — so the exclusion is written
# down and asserted in both directions: the symbol must still exist, and it
# must carry no hook. See test_ovt_is_excluded_while_it_reports_unrated.
EXCLUDED_SITES = {
    "ovt": "submit_ovt_match",
}
HOOK = "record_completed_games"


def _read(path):
    with io.open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


# ── The catalogue ──────────────────────────────────────────────────

def test_eight_lines_with_unique_skus():
    assert len(tl.LADDERS) == 8
    assert len({ld["line"] for ld in tl.LADDERS}) == 8
    skus = [r["sku"] for r in tl.ALL_RUNGS]
    assert len(skus) == len(set(skus)), "duplicate ladder sku"
    assert len(skus) == 48
    for sku in skus:
        assert sku.startswith("title_ladder_"), sku
        assert len(sku) <= 64, sku   # shop_items.sku is VARCHAR(64)


def test_ladder_skus_do_not_collide_with_any_existing_title():
    """A rung must not re-use a sku another migration already owns: the
    INSERT is ON CONFLICT DO NOTHING, so a collision would silently leave the
    OTHER item's name and price wearing a ladder's identity."""
    existing = set()
    for name in sorted(os.listdir(SQL_DIR)):
        if not name.endswith(".sql") or name.startswith("331_"):
            continue
        existing.update(re.findall(r"'(title_[a-z0-9_]+)'", _read(os.path.join(SQL_DIR, name))))
    clash = existing.intersection(r["sku"] for r in tl.ALL_RUNGS)
    assert not clash, f"ladder skus already used elsewhere: {sorted(clash)}"


def test_tiers_are_contiguous_from_one():
    for ld in tl.LADDERS:
        tiers = sorted({r["tier"] for r in ld["rungs"]})
        assert tiers == list(range(1, len(tiers) + 1)), (ld["line"], tiers)
        assert tl.max_tier(ld["line"]) == tiers[-1]


def test_rat_is_the_one_line_with_two_rungs_on_a_tier():
    """Rat 4 is King AND Queen; nothing else shares a tier. Every consumer
    reads a tier as a list because of this one case, so if it ever stops
    being true the list handling stops being exercised."""
    pairs = {(r["line"], r["tier"]) for r in tl.ALL_RUNGS
             if len(tl.rungs_at_tier(r["line"], r["tier"])) > 1}
    assert pairs == {("rat", 4)}
    assert [r["name"] for r in tl.rungs_at_tier("rat", 4)] == ["Rat King", "Rat Queen"]


def test_thresholds_start_at_zero_and_strictly_increase():
    for ld in tl.LADDERS:
        seen = []
        for tier in range(1, tl.max_tier(ld["line"]) + 1):
            rows = tl.rungs_at_tier(ld["line"], tier)
            ths = {r["threshold"] for r in rows}
            assert len(ths) == 1, f"{ld['line']} tier {tier} disagrees on threshold: {ths}"
            seen.append(ths.pop())
        assert seen[0] == 0, ld["line"]
        assert all(b > a for a, b in zip(seen, seen[1:])), (ld["line"], seen)


def test_entry_rung_is_in_the_ordinary_pool_and_the_rest_are_granted_only():
    """Named for what it checks: POOL, not purchasability.

    It asserts ``rotation_pool is None`` for tier 1 and the hidden pool above
    it. It says nothing about whether a tier-1 rung can be bought -- since the
    readiness repair those rungs ship ``catalog_ready = FALSE`` and cannot be,
    and a test called "is_purchasable" asserting only the pool is a name that
    would have to be wrong for the code to be right.
    """
    for r in tl.ALL_RUNGS:
        if r["tier"] == 1:
            assert r["rotation_pool"] is None, r["sku"]
            assert r["price"] == tl.ENTRY_PRICE, r["sku"]
        else:
            assert r["rotation_pool"] == tl.HIDDEN_POOL, r["sku"]
            assert r["price"] == 0, r["sku"]
    assert len(tl.ENTRY_SKUS) == 8


def test_rarity_and_colour_are_populated_and_known():
    known = {"common", "uncommon", "rare", "epic", "legendary"}
    for r in tl.ALL_RUNGS:
        assert r["rarity"] in known, (r["sku"], r["rarity"])
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", r["preview_color"]), (r["sku"], r["preview_color"])
        assert r["name"] and len(r["name"]) <= 128
        assert r["description"] and len(r["description"]) <= 256


# ── The rules ──────────────────────────────────────────────────────

def test_tier_for_games_at_every_boundary():
    for ld in tl.LADDERS:
        line = ld["line"]
        top = tl.max_tier(line)
        for tier in range(2, top + 1):
            th = tl.rungs_at_tier(line, tier)[0]["threshold"]
            assert tl.tier_for_games(line, th - 1) == tier - 1, (line, tier, th)
            assert tl.tier_for_games(line, th) == tier, (line, tier, th)
        assert tl.tier_for_games(line, 0) == 1
        assert tl.tier_for_games(line, 10 ** 6) == top


def test_tier_for_games_boundary_has_a_mutation_control():
    """Move one threshold and the boundary assertion above must break. Without
    this the loop would pass just as happily against a tier_for_games that
    ignored its inputs."""
    line, tier = "cat", 3
    rung = tl.rungs_at_tier(line, tier)[0]
    original = rung["threshold"]
    rung["threshold"] = original + 5
    try:
        assert tl.tier_for_games(line, original) == tier - 1, \
            "tier_for_games ignored the mutated threshold — the boundary test is decoration"
        assert tl.tier_for_games(line, original + 5) == tier
    finally:
        rung["threshold"] = original
    assert tl.tier_for_games(line, original) == tier


def test_next_rung_is_none_at_the_top_and_names_the_pair():
    assert tl.next_rung("rat", 3)["names"] == ["Rat King", "Rat Queen"]
    assert tl.next_rung("rat", 3)["tier"] == 4
    assert tl.next_rung("rat", tl.max_tier("rat")) is None
    assert tl.next_rung("cat", tl.max_tier("cat")) is None
    assert tl.next_rung("cat", 1)["threshold"] == 10


def test_line_of_sku_only_answers_for_rungs():
    assert tl.line_of_sku("title_ladder_shark_6") == "shark"
    assert tl.line_of_sku("title_grandmaster") is None
    assert tl.line_of_sku(None) is None
    assert tl.line_of_sku("") is None


# ── The migration ──────────────────────────────────────────────────

def _strip_sql_comments(sql):
    """`sql` with every comment removed, for the structural scans below.

    A regex over raw source cannot tell a live statement from a commented-out
    one, so a structural test built on raw source still passes after the thing
    it names has been commented out -- which is the cheapest possible way to
    remove it. Block comments first (they can span the line comments), then
    line comments.
    """
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\r\n]*", " ", sql)
    return sql


def _sql_tuples(sql, header):
    """Rows of a `INSERT ... VALUES\n (..),\n (..)\nON CONFLICT` block."""
    start = sql.index(header) + len(header)
    end = sql.index("ON CONFLICT", start)
    body = sql[start:end]
    rows = []
    for raw in re.findall(r"\(([^()]*)\)", body):
        vals, buf, in_str, i = [], "", False, 0
        while i < len(raw):
            ch = raw[i]
            if in_str:
                if ch == "'":
                    if i + 1 < len(raw) and raw[i + 1] == "'":
                        buf += "'"
                        i += 2
                        continue
                    in_str = False
                    i += 1
                    continue
                buf += ch
            elif ch == "'":
                in_str = True
            elif ch == ",":
                vals.append(buf.strip())
                buf = ""
            else:
                buf += ch
            i += 1
        vals.append(buf.strip())
        rows.append(vals)
    return rows


def test_migration_rows_match_module():
    sql = _read(MIGRATION)
    items = _sql_tuples(
        sql,
        "INSERT INTO shop_items (sku, kind, name, description, price, rarity, "
        "rotation_pool, catalog_ready, preview_color) VALUES")
    ladders = _sql_tuples(sql, "INSERT INTO title_ladders (sku, line, tier, threshold) VALUES")

    # catalog_ready is FALSE for exactly the rungs the public shop would
    # list, i.e. the ones with no rotation_pool. shop_items.catalog_ready is
    # NOT NULL DEFAULT TRUE (147:26, confirmed against the live schema) and the
    # BEFORE INSERT gate that forces FALSE only fires for kind='face'
    # (148:353), so without the explicit column these eight 1000-gold entry
    # rungs go on sale the moment the migration is applied -- for a ladder
    # that cannot advance until the progression hook is wired. Migrations are
    # pre-authorized independently of code SHAs, so this is pinned here rather
    # than left to the migration's header prose.
    want_items = [[r["sku"], "title", r["name"], r["description"], str(r["price"]),
                   r["rarity"], "NULL" if r["rotation_pool"] is None else r["rotation_pool"],
                   "FALSE" if r["rotation_pool"] is None else "TRUE",
                   r["preview_color"]] for r in tl.ALL_RUNGS]
    want_ladders = [[r["sku"], r["line"], str(r["tier"]), str(r["threshold"])]
                    for r in tl.ALL_RUNGS]

    assert items == want_items
    assert ladders == want_ladders


def test_migration_row_comparison_is_not_vacuous():
    """Negative control for the comparison above: a single changed character
    in the parsed SQL must make it fail.

    The mutation names the row as it appears in the title_ladders block, not
    just the sku: the sku alone occurs FIRST in the shop_items block, and
    mutating that one left this control passing against an unchanged ladders
    list -- the control caught its own weak mutation on the first run."""
    sql = _read(MIGRATION)
    mutated = sql.replace("('title_ladder_rat_1', 'rat', 1, 0)",
                          "('title_ladder_rat_1', 'rat', 2, 0)", 1)
    assert mutated != sql, "the mutation target has moved; this control is inert"
    ladders = _sql_tuples(mutated, "INSERT INTO title_ladders (sku, line, tier, threshold) VALUES")
    want = [[r["sku"], r["line"], str(r["tier"]), str(r["threshold"])] for r in tl.ALL_RUNGS]
    assert ladders != want


def test_migration_is_transactional_and_self_checking():
    # Comment-stripped FIRST. A commented-out BEGIN satisfies a raw count just
    # as well as a real one, and this file is all-or-nothing only if the real
    # one is there.
    sql = _strip_sql_comments(_read(MIGRATION))
    assert sql.count("BEGIN;") == 1, "expected exactly one BEGIN"
    assert sql.count("COMMIT;") == 1, (
        "more than one COMMIT: the first one ends the transaction, so every "
        "post-check after it commits its own failure instead of rolling the "
        "file back -- and checking only the LAST line cannot see that")
    assert sql.rstrip().endswith("COMMIT;")
    assert sql.index("BEGIN;") < sql.index("CREATE TABLE IF NOT EXISTS title_ladders")
    # psql -f does not wrap a file in a transaction (#340), so the explicit
    # pair above is what makes this file all-or-nothing.
    #
    # RAISE WARNING prints and CONTINUES. A post-check that warns lets the
    # invalid state commit, which is the opposite of what these blocks exist
    # for -- and swapping one for the other left the old `"RAISE EXCEPTION" in
    # sql` assertion green on the strength of the seven that remained.
    assert "RAISE WARNING" not in sql, (
        "a post-check warns instead of raising; a warning does not roll back")
    # Moved from 8 to 9 ON PURPOSE, which is what this assertion asks of
    # anyone who changes that file. The ninth is the arm that fails when the
    # tier-1 rungs come out neither all off sale (this file's own state) nor
    # all eight ready (the activation release's). The repair above clears a
    # partial set, so a partial set surviving means it could not reach those
    # rows, and each survivor is a 1000-gold listing for a ladder that cannot
    # advance. It replaces a RAISE NOTICE that reported that state as healthy.
    assert sql.count("RAISE EXCEPTION") == 9, (
        "the number of post-checks changed (found %d, expected 9). That may "
        "well be correct -- but it is a deliberate change to this file's "
        "safety net, so move the number on purpose rather than letting a "
        "deleted check pass unnoticed." % sql.count("RAISE EXCEPTION"))
    # Ordering: the FK on title_ladders.sku means shop_items must be inserted
    # first or every ladder row violates it.
    assert sql.index("INSERT INTO shop_items") < sql.index("INSERT INTO title_ladders")
    # The three tables this item owns, and no others created here.
    # Comment-aware: block-commenting a whole CREATE block would otherwise
    # leave this regex satisfied while the migration commits without the
    # table, and the first hook to touch it fails at runtime.
    created = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)",
                             _strip_sql_comments(sql)))
    assert created == {"title_ladders", "title_ladder_progress", "title_ladder_credits"}


def test_entry_rungs_cannot_be_on_sale_whatever_the_database_already_held():
    """The readiness rule is a FINAL-STATE invariant, not an insert literal.

    `ON CONFLICT (sku) DO NOTHING` leaves an existing row exactly as it was, so
    writing catalog_ready = FALSE in the VALUES list repairs a CLEAN database
    and does nothing at all to one that already holds an entry rung with
    catalog_ready = TRUE -- a prior partial run, a hand-created row, an earlier
    draft of this file. `/shop/items` lists exactly
    (rotation_pool IS NULL AND catalog_ready IS TRUE), so such a row is a live
    1000-gold purchase for a ladder that cannot advance yet.

    Two things must be present, in this order: a repair phrased as an operation
    on the final state, and a post-check that RAISES if any tier-1 rung is
    still catalog_ready. The post-check is the actual guarantee at apply time;
    this test exists only to stop it being removed.
    """
    sql = _strip_sql_comments(_read(MIGRATION))
    i_items = sql.index("INSERT INTO shop_items")
    i_ladders = sql.index("INSERT INTO title_ladders")

    repair = re.search(
        r"UPDATE\s+shop_items\s+si\s+SET\s+catalog_ready\s*=\s*FALSE"
        r"\s+FROM\s+title_ladders\s+tl\s+WHERE\s+tl\.sku\s*=\s*si\.sku"
        r"\s+AND\s+tl\.tier\s*=\s*1", sql)
    assert repair, "no final-state repair clearing catalog_ready on tier-1 rungs"
    # After BOTH inserts, or the join has nothing to repair.
    assert repair.start() > i_items, "the repair runs before shop_items is populated"
    assert repair.start() > i_ladders, "the repair runs before title_ladders is populated"

    guard = re.search(
        r"SELECT\s+COUNT\(\*\)\s+INTO\s+bad"
        r"\s+FROM\s+title_ladders\s+tl\s+JOIN\s+shop_items\s+si"
        r"\s+ON\s+si\.sku\s*=\s*tl\.sku"
        r"\s+WHERE\s+tl\.tier\s*=\s*1\s+AND\s+si\.catalog_ready\s+IS\s+TRUE", sql)
    assert guard, "no post-check asserting that no tier-1 rung is catalog_ready"
    assert guard.start() > repair.start(), "the post-check is counted before the repair"
    assert "RAISE EXCEPTION" in sql[guard.end():guard.end() + 400], \
        "the readiness post-check counts but never raises"


def test_the_readiness_guard_is_not_vacuous():
    """Negative control for the test above.

    Removing either half from a copy of the migration must break it. If both
    mutations still pass, the test is matching something other than what it
    names.
    """
    sql = _read(MIGRATION)

    # NOTE ON THE MUTATION ITSELF (#709). `AND si.catalog_ready IS TRUE` occurs
    # TWICE -- once in the repair's WHERE and once in the post-check -- so a
    # count=1 replace silently mutates only the repair and leaves the
    # post-check matching, and this control passes while proving nothing. It
    # did exactly that on the first run. Replace EVERY occurrence: the
    # mutation being modelled is "the readiness concept was removed", not
    # "one line was edited".
    repair_pat = r"UPDATE\s+shop_items\s+si\s+SET\s+catalog_ready\s*=\s*FALSE"
    guard_pat = (r"WHERE\s+tl\.tier\s*=\s*1\s+AND\s+si\.catalog_ready\s+IS\s+TRUE")

    assert "SET catalog_ready = FALSE" in sql
    gutted = _strip_sql_comments(sql.replace("SET catalog_ready = FALSE", "SET line = line"))
    assert re.search(repair_pat, gutted) is None, "removing the repair did not break its pattern"

    assert sql.count("AND si.catalog_ready IS TRUE") == 2, sql.count("AND si.catalog_ready IS TRUE")
    gutted = _strip_sql_comments(sql.replace("AND si.catalog_ready IS TRUE", "AND TRUE"))
    assert re.search(guard_pat, gutted) is None, "removing the guard did not break its pattern"

    # And the comment-stripping itself must bite: commenting the repair out is
    # the cheapest way to remove it, and must read as removed.
    commented = sql.replace("UPDATE shop_items si", "-- UPDATE shop_items si")
    assert re.search(repair_pat, _strip_sql_comments(commented)) is None, \
        "a commented-out repair still matches -- the scan is not comment-aware"


def test_migration_number_is_free():
    """331 is this item's reserved number and must not already be taken by a
    file another session wrote tonight."""
    same = [n for n in os.listdir(SQL_DIR) if n.startswith("331_")]
    assert same == ["331_animal_title_ladders.sql"], same


def test_progress_is_a_delta_never_an_absolute_write():
    """#326: every counter mutation is `SET x = x + :d`.

    ENUMERATED, not sampled. The previous version asserted the delta string was
    present, and separately that no `SET games = :bind` existed. Both hold with
    `SET games = 0` or `SET games = EXCLUDED.games` sitting beside the delta --
    and an absolute write is the whole of what #326 is about, because it
    discards every increment that landed between the read that produced the
    value and the write that stores it.
    """
    src = _read(MODULE_PY)
    writes = re.findall(r"SET\s+games\s*=\s*([^,\r\n]+)", src)
    assert writes, "nothing writes the games counter any more"
    for rhs in writes:
        assert re.match(r"title_ladder_progress\.games\s*\+\s*1\b", rhs.strip()), (
            "absolute write to the games counter: SET games = %r. Every "
            "mutation of a counter is a delta off the stored value (#326)."
            % rhs.strip())


# ── The contract with main.py ──────────────────────────────────────

def test_hidden_pool_is_the_string_main_py_actually_gates_on():
    """HIDDEN_POOL is only worth anything because main.py keys two behaviours
    on that exact literal: /shop/items appends an OWNED item from the pool
    (so a rung has an equip surface, #151) and the purchase path refuses it.
    If either literal moves, a ladder rung silently becomes an unequippable,
    buyable item."""
    main = _read(MAIN_PY)
    assert tl.HIDDEN_POOL == "achievement"
    assert 'ShopItem.rotation_pool == "achievement"' in main, \
        "the /shop/items owner-append for the hidden pool has moved"
    # The purchase refusal is checked STRUCTURALLY in the test below. A
    # substring here would pass for `... == "achievement" and False:`, which
    # keeps the text and drops the refusal.
    assert 'item.rotation_pool == "achievement"' in main, \
        "the purchase refusal for the hidden pool has moved"


def _named_function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def test_the_purchase_refusal_for_hidden_rungs_is_structural_not_textual():
    """The refusal that keeps 40 zero-price rungs unbuyable must be SHAPE.

    Every rung above tier 1 is priced 0 and sits in the hidden pool; the only
    thing standing between a crafted purchase request and a free legendary
    title is one `if` in `purchase_item`. A substring assertion cannot tell
    that `if` from `if ... and False:` -- the literal survives both, so the
    text-based check passes while the guard is inert.

    So assert the structure: inside `purchase_item` there is exactly one `if`
    whose test is a BARE equality between `item.rotation_pool` and the pool
    literal -- no boolean operator wrapped around it, since `and`/`or` make
    the test an `ast.BoolOp` and are deliberately not matched -- and its body
    raises HTTPException with status 403.
    """
    fn = _named_function(ast.parse(_read(MAIN_PY)), "purchase_item")
    assert fn is not None, "purchase_item not found in main.py"

    def is_the_guard(node):
        return (isinstance(node, ast.Compare)
                and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq)
                and isinstance(node.left, ast.Attribute)
                and node.left.attr == "rotation_pool"
                and isinstance(node.left.value, ast.Name)
                and node.left.value.id == "item"
                and len(node.comparators) == 1
                and isinstance(node.comparators[0], ast.Constant)
                and node.comparators[0].value == tl.HIDDEN_POOL)

    hits = [n for n in ast.walk(fn) if isinstance(n, ast.If) and is_the_guard(n.test)]
    assert len(hits) == 1, (
        "expected exactly one bare `item.rotation_pool == %r` guard in "
        "purchase_item, found %d. A boolean operator around it is NOT matched "
        "on purpose: that is the mutation this test exists to catch."
        % (tl.HIDDEN_POOL, len(hits)))

    codes = []
    for r in [n for n in ast.walk(hits[0]) if isinstance(n, ast.Raise)]:
        for kw in getattr(r.exc, "keywords", []):
            if kw.arg == "status_code" and isinstance(kw.value, ast.Constant):
                codes.append(kw.value.value)
    assert 403 in codes, (
        "the hidden-pool guard does not raise 403; status codes found: %r" % codes)


def _function_span(src_lines, name):
    """Lines of `async def name(` up to the next top-level definition."""
    start = None
    for i, line in enumerate(src_lines):
        if line.startswith(f"async def {name}(") or line.startswith(f"def {name}("):
            start = i
            break
    if start is None:
        return None
    for j in range(start + 1, len(src_lines)):
        s = src_lines[j]
        if s and not s[0].isspace() and not s.startswith(")"):
            return src_lines[start:j]
    return src_lines[start:]


def test_every_completion_symbol_exists():
    """Symbols, not line numbers — every main.py anchor in the plan is stale.

    The excluded site is resolved too. An exclusion that stops resolving is
    not an exclusion any more, it is a dangling name, and the test that keeps
    1v2 unhooked would then be asserting nothing.
    """
    lines = _read(MAIN_PY).split("\n")
    both = dict(COMPLETION_SITES, **EXCLUDED_SITES)
    missing = [f"{mode}:{fn}" for mode, fn in both.items()
               if _function_span(lines, fn) is None]
    assert not missing, f"completion sites not found by symbol: {missing}"


def test_hook_coverage_is_per_mode_once_anything_is_wired():
    """INERT UNTIL THE HOOKS LAND, and it says so rather than passing quietly.

    The check that must never be written is "exactly one call per function":
    it passes with 2v2's forfeit path unhooked, because that path is a
    DIFFERENT function. The check here is all FOUR spans carry the hook, and
    each span carries it exactly once — plus the excluded 1v2 span carrying
    none, since an unrated mode crediting a rated-only ladder is the same
    class of defect pointing the other way."""
    src = _read(MAIN_PY)
    if HOOK not in src:
        pytest.skip(f"{HOOK} is not wired into main.py yet — hooks are blocked "
                    f"behind another session's rewrite of the lease surface")
    lines = src.split("\n")
    counts = {}
    for mode, fn in COMPLETION_SITES.items():
        span = _function_span(lines, fn)
        assert span is not None, fn
        # Structure, not tokens: see hook_calls_in at the foot of this file for
        # what a token count cannot see.
        counts[f"{mode}:{fn}"] = hook_calls_in("\n".join(span))
    unhooked = [k for k, c in counts.items() if not c]
    doubled = [k for k, c in counts.items() if len(c) > 1]
    unawaited = [k for k, c in counts.items() if any(not x["awaited"] for x in c)]
    incomplete = [k for k, c in counts.items()
                  if any(not x["has_mode"] or not x["has_reference_id"] for x in c)]
    assert not unhooked, f"completion paths with no ladder credit: {unhooked}"
    assert not doubled, f"completion paths crediting more than once: {doubled}"
    assert not unawaited, (
        f"the ladder credit is called but NOT AWAITED at: {unawaited}. An "
        f"unawaited coroutine is constructed and dropped -- no row is written, "
        f"nothing raises, and the call reads as present to any text search.")
    assert not incomplete, (
        f"the ladder credit is missing mode= or reference_id= at: {incomplete}. "
        f"reference_id is the dedupe key: without it the PRIMARY KEY on "
        f"title_ladder_credits cannot collapse the two 2v2 completion paths "
        f"and one series credits twice.")

    wrongly_hooked = [f"{mode}:{fn}" for mode, fn in EXCLUDED_SITES.items()
                      if hook_calls_in("\n".join(_function_span(lines, fn)))]
    assert not wrongly_hooked, (
        f"an EXCLUDED completion site credits the ladder: {wrongly_hooked}. "
        f"1v2 reports is_ranked=false, so crediting it contradicts the "
        f"rated-only contract in title_ladders' docstring. If 1v2 is now "
        f"meant to count, that is a design decision: move it into "
        f"COMPLETION_SITES and say so in the module docstring.")


# ── Line endings ───────────────────────────────────────────────────

@pytest.mark.parametrize("path", [MODULE_PY, MIGRATION, os.path.abspath(__file__)])
def test_tracked_source_is_pure_crlf(path):
    """Tracked .py/.sql in this repo is CRLF; a text-mode rewrite converts a
    whole file and shows up as a diff of every line (#675/#592). Counted in
    bytes — `grep -c $'\\r'` returns the LINE count on this seat."""
    raw = open(path, "rb").read()
    crlf, cr, lf = raw.count(b"\r\n"), raw.count(b"\r"), raw.count(b"\n")
    assert cr == crlf == lf, f"{os.path.basename(path)}: CRLF={crlf} CR={cr} LF={lf}"



# ── behavioural cover for the hook ──────────────────────────────────────────
#
# Everything above this line reads source or the migration. These drive
# `record_completed_games` itself, because the property at stake -- that a tier
# is never advanced past a rung the player does not hold -- is not visible in
# the text of the function; both the correct and the broken version contain a
# call to the grant helper inside a loop.

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def one(self):
        return self._rows[0]


class _LadderDB:
    """Answers the five statements `record_completed_games` issues."""

    def __init__(self, *, sku, games, tier, credits_available=1):
        self.sku, self.games, self.tier = sku, games, tier
        self.credits_available = credits_available
        self.credit_attempts = 0
        self.log = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.log.append((sql, params))
        if "FROM players p" in sql:
            return _Res([(object(), self.sku)])
        if "title_ladder_credits" in sql:
            # The PK is the gate: the first insert for a (player, reference_id)
            # wins and every later one returns nothing.
            self.credit_attempts += 1
            return _Res([(1,)] if self.credit_attempts <= self.credits_available
                        else [])
        if "INSERT INTO title_ladder_progress" in sql:
            return _Res([(self.games, self.tier)])
        return _Res([])

    def tier_writes(self):
        return [p for sql, p in self.log
                if "UPDATE title_ladder_progress SET tier" in sql]

    def equips(self):
        return [p for sql, p in self.log if "SET active_title_id" in sql]


def _grant_all_but(missing):
    async def _grant(_db, _pid, sku):
        return sku not in missing
    return _grant


def test_the_hook_advances_a_tier_when_every_rung_is_granted(monkeypatch):
    """Control for the two tests below: the happy path must actually move."""
    monkeypatch.setattr(main, "_grant_title_item", _grant_all_but(set()))
    db = _LadderDB(sku="title_ladder_rat_1", games=10, tier=1)

    events = _run(tl.record_completed_games(db, ["p1"], mode="1v1", reference_id="g1"))

    assert len(events) == 1 and events[0]["to_tier"] == 2, events
    assert db.tier_writes() and db.tier_writes()[0]["t"] == 2
    assert db.equips(), "the new top rung was not equipped"


def test_a_tier_is_never_advanced_past_a_rung_that_was_not_granted(monkeypatch):
    """A missing shop row must not move the player past that rung.

    `_grant_title_item` returns without granting when the sku is absent from
    shop_items. If the hook advances anyway, the player is recorded above a
    threshold they never crossed in inventory terms, and playing on cannot
    repair it -- the threshold is behind them for ever. Holding the tier keeps
    the games count climbing so the next completed game retries.
    """
    rung2 = tl.rungs_at_tier("rat", 2)[0]["sku"]
    monkeypatch.setattr(main, "_grant_title_item", _grant_all_but({rung2}))
    db = _LadderDB(sku="title_ladder_rat_1", games=10, tier=1)

    events = _run(tl.record_completed_games(db, ["p1"], mode="1v1", reference_id="g1"))

    assert events == [], (
        "an upgrade event was emitted for a rung the player does not own: %s" % events)
    assert db.tier_writes() == [], (
        "the tier was advanced past an ungranted rung; that hole is permanent")
    assert db.equips() == [], "a title the player does not own was equipped"


def test_a_multi_tier_jump_stops_at_the_last_rung_actually_granted(monkeypatch):
    """The interesting case, and the reason this is not all-or-nothing.

    A backfilled count or a threshold edit can cross several tiers at once. If
    tier 2 grants and tier 3 does not, the player has genuinely earned and
    received tier 2 and must keep it; only the advance past the missing rung is
    refused. Stopping at the last good tier is what lets the next game retry
    tier 3 without re-granting tier 2.
    """
    rung3 = tl.rungs_at_tier("rat", 3)[0]["sku"]
    monkeypatch.setattr(main, "_grant_title_item", _grant_all_but({rung3}))
    db = _LadderDB(sku="title_ladder_rat_1", games=30, tier=1)   # 30 => tier 3

    events = _run(tl.record_completed_games(db, ["p1"], mode="1v1", reference_id="g1"))

    assert len(events) == 1, events
    assert events[0]["to_tier"] == 2, (
        "expected to stop at tier 2, the last rung actually granted; got %s"
        % events[0]["to_tier"])
    assert rung3 not in events[0]["granted_skus"], (
        "a rung that was not granted is listed as granted")
    assert db.tier_writes()[0]["t"] == 2



# ── the helper half ─────────────────────────────────────────────────────────
#
# The three tests above patch `main._grant_title_item` out, so they prove the
# hook HANDLES a refusal and prove nothing about the helper ever issuing one.
# A mutation flipping the helper's missing-sku return from False to True left
# every one of them green. These bind that half directly. They live in this
# file rather than a main-py test because the ladder is the only caller whose
# correctness depends on the return value -- every other caller ignores it on
# purpose, since a cosmetic title that did not land must not fail a match
# report.

class _Scalar:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _GrantDB:
    """Enough AsyncSession for main._grant_title_item and nothing more."""

    def __init__(self, *, item_id=None, already_owned=False):
        self.item_id = item_id
        self.already_owned = already_owned
        self.inserts = []

    def begin_nested(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if "INSERT INTO player_items" in sql:
            self.inserts.append(params)
            return _Scalar(None)
        if "FROM player_items" in sql:
            return _Scalar(object() if self.already_owned else None)
        if "FROM shop_items" in sql:
            return _Scalar(self.item_id)
        raise AssertionError("unexpected statement in the grant helper: %s" % sql)


def test_the_grant_helper_reports_failure_when_the_sku_is_absent():
    """An absent shop row must return False, not None-and-a-printed-line.

    This is the signal the ladder hook stops on. Without it the hook advances
    the player's tier past a rung they were never given, and that hole cannot
    be repaired by playing on because the threshold is already behind them.
    """
    db = _GrantDB(item_id=None)
    ok = _run(main._grant_title_item(db, "p1", "title_ladder_rat_2"))
    assert ok is False, (
        "the helper reported %r for a sku that is not in shop_items; the "
        "ladder hook reads this as a successful grant" % (ok,))
    assert db.inserts == [], "it granted something despite having no item id"


def test_the_grant_helper_reports_success_when_it_grants():
    db = _GrantDB(item_id="item-1")
    ok = _run(main._grant_title_item(db, "p1", "title_ladder_rat_2"))
    assert ok is True, "a successful grant must report True, got %r" % (ok,)
    assert len(db.inserts) == 1, "no player_items row was written"


def test_the_grant_helper_reports_success_when_the_player_already_owns_it():
    """Idempotent: already-owned is success, not failure.

    Getting this backwards would stall a ladder permanently -- a replayed or
    retried credit would read an existing rung as a missing one and refuse to
    advance past a rung the player demonstrably holds.
    """
    db = _GrantDB(item_id="item-1", already_owned=True)
    ok = _run(main._grant_title_item(db, "p1", "title_ladder_rat_2"))
    assert ok is True, "already-owned must be success, got %r" % (ok,)
    assert db.inserts == [], "it re-granted an item the player already owned"



def test_one_reference_id_credits_once_however_many_times_it_arrives(monkeypatch):
    """The unit of credit is the reference_id, and that is a SERIES.

    2v2 completes in two different places and either can also be retried, so
    one series can reach this hook several times. `title_ladder_credits`'
    PRIMARY KEY (player_id, reference_id) is what makes that safe -- and it is
    also why the unit cannot be an individual game while both 2v2 sites pass
    the team series id, which is the contradiction Codex found in the prose.

    Binding the DEDUPE rather than the wording: the wording can be edited, the
    behaviour is what a future wiring author will actually get.
    """
    monkeypatch.setattr(main, "_grant_title_item", _grant_all_but(set()))
    db = _LadderDB(sku="title_ladder_rat_1", games=10, tier=1, credits_available=1)

    first = _run(tl.record_completed_games(db, ["p1"], mode="2v2", reference_id="series-7"))
    second = _run(tl.record_completed_games(db, ["p1"], mode="2v2", reference_id="series-7"))

    assert len(first) == 1, "the first arrival did not credit at all: %s" % (first,)
    assert second == [], (
        "the same reference_id credited twice; the PK is the only thing "
        "standing between a forfeit-settled 2v2 series and a double credit")

    progress_writes = [p for sql, p in db.log
                       if "INSERT INTO title_ladder_progress" in sql]
    assert len(progress_writes) == 1, (
        "the games counter was incremented %d times for one series"
        % len(progress_writes))



# ── the hook-coverage scanner ───────────────────────────────────────────────

def hook_calls_in(source):
    """Every CALL to the ladder hook in `source`, as structure rather than text.

    One dict per call: whether it is awaited, and whether it carries the two
    keyword arguments that make it dedupable. A comment or a string literal
    cannot produce an entry, because this walks the parse tree.

    Module-level precisely so it can be tested. The coverage test that uses it
    skips until the hook is wired, and a scanner whose first real run is the
    day it has to be right is not a check (#313) -- so the tests below drive it
    against synthetic sources now.
    """
    src = textwrap.dedent(source)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # A mid-function slice: indentation the parser will not accept on its
        # own. `async def` because a span lifted out of a completion handler is
        # full of awaits.
        tree = ast.parse("async def _wrapper():\n" + textwrap.indent(src, "    "))

    awaited = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Await)}
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = (fn.attr if isinstance(fn, ast.Attribute)
                else fn.id if isinstance(fn, ast.Name) else None)
        if name != HOOK:
            continue
        kwargs = {k.arg for k in node.keywords}
        found.append({"awaited": id(node) in awaited,
                      "has_mode": "mode" in kwargs,
                      "has_reference_id": "reference_id" in kwargs})
    return found


# A stand-in for a wired completion site. One statement per line, and a second
# statement inside the branch, so that commenting the hook out below still
# leaves a parseable block -- the point is to test the scanner, not to discover
# that an empty `if` is a syntax error.
WIRED_SITE = """
async def submit_series(db, series):
    if series.is_ranked:
        await _settle(db, series)
        events = await title_ladders.record_completed_games(db, pids, mode="1v1", reference_id=str(series.id))
"""


def test_the_coverage_scanner_sees_a_correct_call():
    """Control: without this, every test below passes on an empty result."""
    calls = hook_calls_in(WIRED_SITE)
    assert calls == [{"awaited": True, "has_mode": True,
                      "has_reference_id": True}], calls


def test_the_coverage_scanner_ignores_a_commented_out_call():
    """The defect the token count had: a commented call read as coverage.

    This is not hypothetical for this item -- the hooks are deliberately
    unwired and the likeliest first draft of the wiring is a commented
    placeholder left behind at the site.
    """
    src = WIRED_SITE.replace("        events = await", "        # events = await")
    assert hook_calls_in(src) == [], "a commented-out call counted as wired"


def test_the_coverage_scanner_ignores_the_hook_name_in_a_string():
    src = WIRED_SITE + '    note = "wire record_completed_games here"\n'
    assert len(hook_calls_in(src)) == 1, (
        "the hook name inside a string literal counted as a call")


def test_the_coverage_scanner_flags_a_call_that_is_not_awaited():
    """The one that matters most, and the one no text search can see.

    Dropping `await` builds a coroutine and discards it: no credit row, no
    progress increment, no exception, and an identical line bar six
    characters. Every completion site is async, so this is a live way for the
    wiring to land inert.
    """
    src = WIRED_SITE.replace("events = await title_ladders", "events = title_ladders")
    calls = hook_calls_in(src)
    assert len(calls) == 1 and calls[0]["awaited"] is False, calls


def test_the_coverage_scanner_flags_a_call_with_no_reference_id():
    """reference_id is the dedupe key; a call without it is not idempotent."""
    src = WIRED_SITE.replace(", reference_id=str(series.id)", "")
    calls = hook_calls_in(src)
    assert len(calls) == 1 and calls[0]["has_reference_id"] is False, calls


def test_the_coverage_scanner_reads_an_indented_span():
    """_function_span hands over body lines, not a parseable module."""
    body = "\n".join(WIRED_SITE.strip().split("\n")[1:])
    assert len(hook_calls_in(body)) == 1, (
        "the scanner could not read a span lifted out of a function; the "
        "coverage test feeds it exactly that")



def test_the_owner_append_does_not_filter_on_readiness():
    """Migration 331 calls the pooled rungs' explicit TRUE a hedge. Keep it one.

    The claim the comment used to make -- that writing FALSE could hide an
    earned title from its owner -- is not true of this code: the
    achievement-owner append selects on rotation_pool and ownership, and
    nothing downstream of it filters on readiness. What IS worth catching is
    the reverse. If a readiness predicate is added here, the explicit TRUE
    stops being a hedge and becomes the only thing keeping earned rungs
    visible, and 331's note has to say so. That edit lands in main.py, where
    nobody has migration 331 open.

    Read off the AST so a comment mentioning the column cannot satisfy or
    break it; a string literal CAN, and should -- raw SQL naming the column is
    a readiness predicate by another route.
    """
    lines = _read(MAIN_PY).split("\n")
    span = _function_span(lines, "list_shop_items")
    assert span is not None, "list_shop_items was renamed or moved"
    tree = ast.parse("\n".join(span))

    # Scoped to the statements that BUILD AND RUN the append -- `ach_q` -- and
    # not to the function, which reads catalog_ready three statements earlier
    # on the ordinary-pool listing. That read is right and load-bearing: it is
    # what keeps the eight entry rungs unlisted until a later release flips
    # them. Compound statements are skipped because the enclosing `if` (and
    # the function node itself) span both queries and would match either way.
    leaves = (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expr, ast.Return)
    append = [ast.dump(n) for n in ast.walk(tree)
              if isinstance(n, leaves) and "'ach_q'" in ast.dump(n)]
    assert append, (
        "no statement in list_shop_items mentions ach_q any more. That append "
        "is how an earned rung reaches its owner's Shop tab at all (#151), "
        "and without it this test passes by having nothing to look at.")
    offenders = [d for d in append if "catalog_ready" in d]
    assert not offenders, (
        "the achievement-owner append now reads catalog_ready. Migration 331's "
        "pooled rungs must then stay TRUE or their owners lose the equip "
        "surface -- the explicit TRUE has stopped being a hedge, and the "
        "comment at 331 that calls it one is now wrong. Update it.")


def test_the_listing_decides_visibility_with_the_same_predicate_as_equip():
    """ONE PREDICATE, NOT TWO THAT AGREE.

    The carve-out is decided by `_auto_owned`, and the equip path calls it.
    The listing used to spell the same rule a second time in SQL --
    `sku NOT IN (...) OR id IN (...)` -- under a comment claiming the two
    surfaces could not drift. They could: an edit to `_auto_owned` moved the
    equip path and left the listing exactly as it was, and nothing here went
    red, because every listing test agreed with both copies.

    So the sharing is asserted structurally rather than inferred from the two
    happening to agree today. Read off the AST of `list_shop_items` and
    scoped the same way as the test above: the statements that build and
    consume the achievement append must CALL `_auto_owned`, and must not name
    the carve-out set directly, which is how the second copy was spelled.
    """
    lines = _read(MAIN_PY).split("\n")
    span = _function_span(lines, "list_shop_items")
    assert span is not None, "list_shop_items was renamed or moved"
    tree = ast.parse("\n".join(span))

    leaves = (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expr, ast.Return)
    append = [n for n in ast.walk(tree)
              if isinstance(n, leaves)
              and ("'ach_q'" in ast.dump(n) or "'pool'" in ast.dump(n))]
    assert append, (
        "no statement in list_shop_items builds or consumes the achievement "
        "append any more, so this test has nothing to look at")

    dumped = " ".join(ast.dump(n) for n in append)
    assert "_auto_owned" in dumped, (
        "the achievement append no longer calls _auto_owned, so the listing "
        "decides the shop-owner carve-out by some other route. Whatever that "
        "route says today, it is a SECOND statement of one rule and it will "
        "drift from the equip path -- the defect this closes.")
    assert "_GRANTED_ONLY_TITLE_SKUS" not in dumped, (
        "the achievement append names the carve-out set directly again. That "
        "is the second copy: it is how the rule was spelled in SQL, and it "
        "agrees with _auto_owned only until one of the two is edited.")



def _paren_list(text, open_at):
    """The comma-separated items inside the parenthesis starting at `open_at`.

    Depth-aware in both directions. A non-greedy regex closes on the first
    `)` it meets, which in this INSERT is `NOW()` -- that read 22 values
    against 31 columns and is exactly the kind of near-miss that makes a
    positional lookup silently point at the wrong column.
    """
    depth, items, cur = 0, [], []
    for ch in text[open_at:]:
        if ch == "(":
            depth += 1
            if depth == 1:
                continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                items.append("".join(cur).strip())
                return items
        if ch == "," and depth == 1:
            items.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    return []


def test_ovt_is_excluded_while_it_reports_unrated():
    """The exclusion is read off the code, not carried as an opinion.

    `submit_ovt_match` writes `is_ranked` as a literal `false` in its INSERT
    into ovt_matches -- a constant, not a bind parameter a caller could set --
    and the ladder credits COMPLETED RATED series. Those two facts are what
    put 1v2 in EXCLUDED_SITES rather than any view about the mode.

    So this test fails the day the literal changes, which is the day 1v2 gains
    a rating and the question "should a 1v2-only player advance a ladder they
    bought" has to be answered instead of inherited. Failing then is the whole
    point: an exclusion nobody revisits is how a mode stays unhooked for ever.
    """
    lines = _read(MAIN_PY).split("\n")
    span = _function_span(lines, EXCLUDED_SITES["ovt"])
    assert span is not None, "submit_ovt_match was renamed or moved"

    body = "\n".join(span)
    # The statement, not the first mention of it. A comment in this function
    # names the INSERT and carries a parenthesis of its own, and reading that
    # one produced a "column list" of English prose. Identify the real one by
    # the column it must contain.
    starts = [m.start() for m in re.finditer(r"INSERT INTO ovt_matches\s*\(", body)]
    assert starts, "submit_ovt_match no longer INSERTs into ovt_matches"
    hits = [(a, _paren_list(body, body.index("(", a))) for a in starts]
    real = [(a, cs) for a, cs in hits if "is_ranked" in cs]
    assert len(real) == 1, (
        "expected exactly one ovt_matches INSERT writing is_ranked, found %d. "
        "Two would mean two code paths set it and this test reads only one."
        % len(real))
    at, cols = real[0]
    vals = _paren_list(body, body.index("(", body.index("VALUES", at)))
    assert vals, "could not read the INSERT's value list"
    assert len(cols) == len(vals), (
        "could not align %d columns with %d values -- a value now contains a "
        "comma, so this test cannot read the is_ranked position and must be "
        "rewritten rather than trusted" % (len(cols), len(vals)))
    written = vals[cols.index("is_ranked")]
    assert written == "false", (
        "submit_ovt_match now writes is_ranked=%s instead of the literal "
        "false. 1v2 is excluded from the title ladders ONLY because it "
        "reports unrated; if that has changed, decide whether 1v2 credits a "
        "ladder and move it from EXCLUDED_SITES to COMPLETION_SITES (or "
        "record why it stays out). This is a design call, not a test fix."
        % written)


# ── The migration and the hook, EXECUTED against a real PostgreSQL ─────────
#
# Everything above this line reads source, parses SQL, or drives the hook
# against a fake session. That leaves two things unproven, and they are the
# two that matter most here:
#
#   * migration 331 is never RUN by its own suite, so a syntax-only mutation
#     -- a missing comma, a constraint that cannot be created, a post-check
#     whose SELECT does not parse -- stays green all the way to the deploy
#     (#313: `MIN(uuid)` reads as obviously correct and does not exist).
#   * the once-per-completion gate is the PRIMARY KEY on
#     `title_ladder_credits`, and the fake session above answers the credit
#     INSERT from a counter of its own. Changing the real statement's
#     `ON CONFLICT ... DO NOTHING` to `DO UPDATE` leaves that fake returning
#     exactly what it returned before, so the double-credit the key exists to
#     stop is invisible. The fake tests the hook's REACTION to a refused
#     credit; only the server tests whether the credit is refused.
#
# Same gate and same polarity as the rollover modules: no DSN is a FAILURE,
# PC_EDITION_TEST_PG_OPTOUT=1 waives it deliberately.

LADDER_DSN_VAR = "LADDER_TEST_PG_DSN"
LADDER_DSN = (os.environ.get(LADDER_DSN_VAR) or "").replace(
    "postgresql+asyncpg://", "postgresql://")
LADDER_OPTOUT_VAR = "LADDER_TEST_PG_OPTOUT"
LADDER_OPTOUT = os.environ.get(LADDER_OPTOUT_VAR) == "1"

try:
    import asyncpg as _asyncpg
except ImportError:                                    # pragma: no cover
    _asyncpg = None


def _require_live_pg():
    """Fail, not skip. A skipped live case reports exit 0 for coverage that
    did not run, and this file's whole live half is one module-level gate
    away from disappearing that way."""
    if LADDER_DSN and _asyncpg is not None:
        return
    if LADDER_OPTOUT:
        pytest.skip("%s is unset and %s=1: live-Postgres ladder coverage "
                    "deliberately waived." % (LADDER_DSN_VAR, LADDER_OPTOUT_VAR))
    if _asyncpg is None:
        pytest.fail("asyncpg is not installed, so migration 331 was not executed "
                    "and the credit key was not exercised. Install it, or set "
                    "%s=1 to waive deliberately." % LADDER_OPTOUT_VAR)
    pytest.fail(
        "%s is unset, so migration 331 was never RUN and the once-per-series "
        "credit key was never exercised -- the two things in this file that no "
        "amount of source reading can settle. Point it at a throwaway cluster, "
        "or set %s=1 to waive the coverage deliberately."
        % (LADDER_DSN_VAR, LADDER_OPTOUT_VAR))


LADDER_PREREQ = """
CREATE TABLE players (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    steam_id        VARCHAR(32) UNIQUE,
    display_name    VARCHAR(64),
    active_title_id BIGINT);
CREATE TABLE shop_items (
    id              BIGSERIAL PRIMARY KEY,
    sku             VARCHAR(64) UNIQUE NOT NULL,
    kind            VARCHAR(16) NOT NULL,
    name            VARCHAR(128) NOT NULL,
    description     VARCHAR(256),
    price           INTEGER NOT NULL CHECK (price >= 0),
    rarity          VARCHAR(16) NOT NULL DEFAULT 'common',
    rotation_pool   VARCHAR(32),
    preview_color   VARCHAR(16),
    catalog_ready   BOOLEAN NOT NULL DEFAULT TRUE,
    released_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE player_items (
    player_id       UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    item_id         BIGINT NOT NULL REFERENCES shop_items(id) ON DELETE CASCADE,
    purchased_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    purchase_price  INTEGER NOT NULL,
    royalty_paid    INTEGER,
    royalty_rate_pct SMALLINT,
    royalty_artist_steam_id VARCHAR(20),
    royalty_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (player_id, item_id));
"""


async def _live_schema(conn, schema, migration_sql):
    await conn.execute('CREATE SCHEMA "%s"' % schema)
    await conn.execute('SET search_path TO "%s"' % schema)
    await conn.execute(LADDER_PREREQ)
    await conn.execute(migration_sql)


def _ladder_schema_name():
    return "ladder_%s" % uuid.uuid4().hex[:10]


def test_the_migration_applies_against_a_real_server():
    """331, RUN. Not parsed, not regex-matched -- executed, post-checks and
    all, on the version of PostgreSQL the primary runs.

    This is the test a syntax-only mutation reddens. Every other assertion
    about this file in this module is satisfied by SQL that would abort on its
    first statement.
    """
    _require_live_pg()
    schema = _ladder_schema_name()
    sql = io.open(MIGRATION, encoding="utf-8").read()

    async def _go():
        conn = await _asyncpg.connect(LADDER_DSN)
        try:
            await _live_schema(conn, schema, sql)
            rungs = await conn.fetchval("SELECT count(*) FROM title_ladders")
            items = await conn.fetchval(
                "SELECT count(*) FROM shop_items WHERE sku LIKE 'title!_ladder!_%' ESCAPE '!'")
            on_sale = await conn.fetchval(
                "SELECT count(*) FROM title_ladders tl JOIN shop_items si "
                "    ON si.sku = tl.sku "
                " WHERE tl.tier = 1 AND si.catalog_ready IS TRUE")
            hidden = await conn.fetchval(
                "SELECT count(*) FROM title_ladders tl JOIN shop_items si "
                "    ON si.sku = tl.sku "
                " WHERE tl.tier > 1 AND si.rotation_pool = 'achievement'")
            return rungs, items, on_sale, hidden
        finally:
            try:
                await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
            finally:
                await conn.close()

    rungs, items, on_sale, hidden = _run(_go())
    assert rungs == len(tl.ALL_SKUS) == 48, (rungs, len(tl.ALL_SKUS))
    assert items == 48, items
    assert on_sale == 0, (
        "%d entry rung(s) came out of a clean apply on sale for 1000 gold, for "
        "a ladder whose progression hook is not wired" % on_sale)
    assert hidden == len(tl.GRANTED_ONLY_SKUS) == 40, (hidden, len(tl.GRANTED_ONLY_SKUS))


def _ladder_engine(schema):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    engine = create_async_engine(
        LADDER_DSN.replace("postgresql://", "postgresql+asyncpg://"),
        connect_args={"server_settings": {"search_path": schema}},
        poolclass=None)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _credit_twice(schema, migration_sql, *, reference_ids):
    """Set a player on rung 1 of rat, then call the hook once per reference_id
    against the REAL statements, and report what actually landed."""
    from sqlalchemy import text as _text

    conn = await _asyncpg.connect(LADDER_DSN)
    try:
        await _live_schema(conn, schema, migration_sql)
    finally:
        await conn.close()

    engine, session = _ladder_engine(schema)
    try:
        async with session() as db:
            pid = (await db.execute(_text(
                "INSERT INTO players (steam_id, display_name) "
                "VALUES ('76561190000000099', 'Ladder Tester') RETURNING id"
            ))).scalar_one()
            await db.execute(_text(
                "UPDATE players SET active_title_id = "
                "  (SELECT id FROM shop_items WHERE sku = 'title_ladder_rat_1') "
                " WHERE id = :pid"), {"pid": pid})
            # Nine games in already: the tenth crosses rat's tier-2 threshold,
            # so a second credit for the same series would move a real rung
            # rather than just a counter.
            await db.execute(_text(
                "INSERT INTO title_ladder_progress (player_id, line, games, tier) "
                "VALUES (:pid, 'rat', 9, 1)"), {"pid": pid})
            await db.commit()

            events = []
            for ref in reference_ids:
                events.append(await tl.record_completed_games(
                    db, [pid], mode="2v2", reference_id=ref))
                await db.commit()

            games = (await db.execute(_text(
                "SELECT games FROM title_ladder_progress "
                " WHERE player_id = :pid AND line = 'rat'"), {"pid": pid})).scalar_one()
            credits = (await db.execute(_text(
                "SELECT count(*) FROM title_ladder_credits WHERE player_id = :pid"),
                {"pid": pid})).scalar_one()
            return events, games, credits
    finally:
        await engine.dispose()
        conn = await _asyncpg.connect(LADDER_DSN)
        try:
            await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
        finally:
            await conn.close()


def test_one_series_credits_once_against_the_real_primary_key():
    """THE DEDUPE, DRIVEN THROUGH POSTGRESQL.

    2v2 settles in two places and a report can be retried, so one series
    reaches this hook more than once by construction. `title_ladder_credits`
    PRIMARY KEY (player_id, reference_id) plus `ON CONFLICT DO NOTHING
    RETURNING 1` is the whole gate: the writer that wins the insert is the one
    that increments.

    Changing that `DO NOTHING` to a `DO UPDATE` makes the second arrival
    return a row, credit again, and -- with the player seeded one game short
    of the threshold -- hand out a rung for a series they played once. The
    fake-session version of this test cannot see that mutation, because the
    fake decides for itself what the second insert returns.
    """
    _require_live_pg()
    sql = io.open(MIGRATION, encoding="utf-8").read()
    events, games, credits = _run(_credit_twice(
        _ladder_schema_name(), sql, reference_ids=["series-7", "series-7"]))

    assert credits == 1, (
        "the same reference_id produced %d credit rows; the PRIMARY KEY is the "
        "only thing between a forfeit-settled 2v2 series and a double credit"
        % credits)
    assert games == 10, (
        "the games counter reached %d for ONE series -- the second arrival was "
        "not refused" % games)
    assert len(events[0]) == 1 and events[0][0]["to_tier"] == 2, events[0]
    assert events[1] == [], (
        "the repeat arrival emitted an upgrade event: %s" % (events[1],))


def test_two_different_series_each_credit_once():
    """The positive control. Without it, the test above is satisfied by a hook
    that refuses every credit after the first for any reason at all."""
    _require_live_pg()
    sql = io.open(MIGRATION, encoding="utf-8").read()
    events, games, credits = _run(_credit_twice(
        _ladder_schema_name(), sql, reference_ids=["series-7", "series-8"]))

    assert credits == 2, credits
    assert games == 11, games
    assert len(events[0]) == 1, events[0]


# ── the shop-owner exemption and the ladder ──────────────────────────────────
#
# `SHOP_OWNER_STEAM_IDS` auto-owns every shop item, which is right for a
# cosmetic and wrong for a rung: a rung above the first is GRANTED by finishing
# rated series while wearing the rung below it. Two surfaces read that
# exemption -- the `/shop/items` achievement append and `_set_active_cosmetic`
# -- and the carve-out has to hold on BOTH, because one of them alone leaves
# the other reachable by naming a sku (#279: a flag names a line, the defect
# is a class).
#
# The listing half is exercised against a real server further down, because
# the predicate is a SQL WHERE clause and a fake session decides for itself
# what a WHERE returns. The equip half is a pure branch and is driven here.

OWNER_STEAM = sorted(main.SHOP_OWNER_STEAM_IDS)[0]
PLAIN_STEAM = "76561190000000042"


def _a_granted_only_rung():
    return sorted(tl.GRANTED_ONLY_SKUS)[0]


def _an_entry_rung():
    entry = [r["sku"] for r in tl.ALL_RUNGS if r["sku"] not in tl.GRANTED_ONLY_SKUS]
    assert entry, "every rung is granted-only; the carve-out would swallow the ladder"
    return sorted(entry)[0]


def test_the_exemption_covers_every_cosmetic_except_a_granted_only_rung():
    """The shared predicate, as a truth table. Both surfaces call this one
    function, so this is where the rule is stated once."""
    assert main._auto_owned(OWNER_STEAM, "title_gold") is True
    assert main._auto_owned(OWNER_STEAM, _an_entry_rung()) is True
    assert main._auto_owned(OWNER_STEAM, _a_granted_only_rung()) is False
    # and it is an exemption, not a grant: a normal account owns nothing by it
    assert main._auto_owned(PLAIN_STEAM, "title_gold") is False
    assert main._auto_owned(None, "title_gold") is False
    assert len(tl.GRANTED_ONLY_SKUS) == 40, len(tl.GRANTED_ONLY_SKUS)


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _EquipRes:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _EquipDb:
    """Enough session for `_set_active_cosmetic`: a player, an item, and
    whatever `player_items` holds. Records whether ownership was consulted at
    all, which is the thing the exemption skips."""

    def __init__(self, player, item, owned=None):
        self.player, self.item, self.owned = player, item, owned
        self.ownership_reads = 0
        self.committed = 0

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if "FROM player_items" in sql:
            self.ownership_reads += 1
            return _EquipRes(self.owned)
        if "FROM shop_items" in sql:
            return _EquipRes(self.item)
        if "FROM players" in sql:
            return _EquipRes(self.player)
        return _EquipRes(None)

    async def commit(self):
        self.committed += 1


def _equip(db, steam_id, item_id, monkeypatch, secret="equip-secret"):
    import hashlib
    import hmac as _hmac
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", secret)
    sig = _hmac.new(secret.encode(), ("title:%s:%d" % (steam_id, item_id)).encode(),
                    hashlib.sha256).hexdigest()
    return _run(main._set_active_cosmetic(db, steam_id, "title", "title", item_id, sig))


def test_an_exempt_account_cannot_equip_a_rung_it_has_not_earned(monkeypatch):
    """The rung is real, the signature is valid, the account is exempt -- and
    the ladder never advanced, so `player_items` has no row. Refused, and the
    player's active title is left alone. A rung that can be worn without being
    earned is not a rung."""
    player = _Row(id=uuid.uuid4(), steam_id=OWNER_STEAM, active_title_id=None)
    item = _Row(id=77, kind="title", sku=_a_granted_only_rung(), name="Rat II")
    db = _EquipDb(player, item, owned=None)
    with pytest.raises(Exception) as ex:
        _equip(db, OWNER_STEAM, 77, monkeypatch)
    assert getattr(ex.value, "status_code", None) == 403, ex.value
    assert db.ownership_reads == 1, "the exemption skipped the ownership check"
    assert player.active_title_id is None
    assert db.committed == 0


def test_an_exempt_account_equips_a_rung_it_actually_owns(monkeypatch):
    """The positive control for the refusal above: the same account, the same
    rung, once the grant exists."""
    player = _Row(id=uuid.uuid4(), steam_id=OWNER_STEAM, active_title_id=None)
    item = _Row(id=77, kind="title", sku=_a_granted_only_rung(), name="Rat II")
    db = _EquipDb(player, item, owned=_Row(player_id=player.id, item_id=77))
    out = _equip(db, OWNER_STEAM, 77, monkeypatch)
    assert out["status"] == "set" and out["item_id"] == 77
    assert player.active_title_id == 77
    assert db.committed == 1


def test_the_exemption_still_covers_an_ordinary_cosmetic(monkeypatch):
    """The carve-out is a carve-OUT. An exempt account still equips a normal
    title it does not own, and the ownership table is not even consulted --
    which is what makes the read count above evidence rather than decoration."""
    player = _Row(id=uuid.uuid4(), steam_id=OWNER_STEAM, active_title_id=None)
    item = _Row(id=5, kind="title", sku="title_gold", name="Gold")
    db = _EquipDb(player, item, owned=None)
    out = _equip(db, OWNER_STEAM, 5, monkeypatch)
    assert out["status"] == "set"
    assert db.ownership_reads == 0, "an ordinary cosmetic went through an ownership check"


def test_an_entry_rung_is_still_covered_by_the_exemption(monkeypatch):
    """Tier 1 is bought, not granted, so it is an ordinary shop row and the
    exemption covers it. Pinning this keeps the carve-out from widening into
    'no ladder sku ever' the next time somebody reaches for a sku prefix."""
    player = _Row(id=uuid.uuid4(), steam_id=OWNER_STEAM, active_title_id=None)
    item = _Row(id=9, kind="title", sku=_an_entry_rung(), name="Rat")
    db = _EquipDb(player, item, owned=None)
    assert _equip(db, OWNER_STEAM, 9, monkeypatch)["status"] == "set"
    assert db.ownership_reads == 0


def test_a_normal_account_is_unaffected_by_either_half(monkeypatch):
    """Nothing above may have changed what an ordinary account can do: it
    still cannot equip what it does not own, rung or otherwise."""
    for sku in (_a_granted_only_rung(), "title_gold"):
        player = _Row(id=uuid.uuid4(), steam_id=PLAIN_STEAM, active_title_id=None)
        item = _Row(id=11, kind="title", sku=sku, name="X")
        db = _EquipDb(player, item, owned=None)
        with pytest.raises(Exception) as ex:
            _equip(db, PLAIN_STEAM, 11, monkeypatch)
        assert getattr(ex.value, "status_code", None) == 403, (sku, ex.value)
        assert db.ownership_reads == 1, sku


# ── the listing half, against a real server ──────────────────────────────────
#
# `/shop/items` decides this in SQL, so the fake-session shape used above
# cannot see it: the fake would answer whatever it was scripted to answer and
# the WHERE clause would go unevaluated. The tables come from the ORM metadata
# rather than hand-written DDL so the model's own column list is what gets
# created; NOT NULL columns whose default lives in Python get a server default
# so the migration's raw INSERTs behave as they do in production.

_FILL_DEFAULTS = """
DO $fill$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT table_name AS t, column_name AS c, data_type AS d
             FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND is_nullable = 'NO' AND column_default IS NULL
  LOOP
    EXECUTE format('ALTER TABLE %I ALTER COLUMN %I SET DEFAULT %s', r.t, r.c,
      CASE WHEN r.d LIKE 'timestamp%' THEN 'NOW()'
           WHEN r.d = 'boolean' THEN 'FALSE'
           WHEN r.d IN ('integer','bigint','smallint','numeric','double precision','real') THEN '0'
           WHEN r.d = 'uuid' THEN 'gen_random_uuid()'
           WHEN r.d = 'ARRAY' THEN quote_literal('{}')
           ELSE quote_literal('') END);
  END LOOP;
END $fill$;
"""


async def _live_listing(schema, migration_sql, *, steam_id, grant_skus=(), extra_pool_sku=None):
    """Apply 331 to a throwaway schema, optionally grant some rows, and return
    what `/shop/items` actually lists for `steam_id`."""
    import models
    from sqlalchemy import text as _text

    conn = await _asyncpg.connect(LADDER_DSN)
    try:
        await conn.execute('CREATE SCHEMA "%s"' % schema)
    finally:
        await conn.close()

    engine, session = _ladder_engine(schema)
    try:
        async with engine.begin() as c:
            await c.run_sync(models.Base.metadata.create_all,
                             tables=[models.Player.__table__,
                                     models.ShopItem.__table__,
                                     models.PlayerItem.__table__])
        conn = await _asyncpg.connect(LADDER_DSN)
        try:
            await conn.execute('SET search_path TO "%s"' % schema)
            await conn.execute(_FILL_DEFAULTS)
            await conn.execute(migration_sql)
        finally:
            await conn.close()

        async with session() as db:
            pool = (await db.execute(_text(
                "SELECT count(*) FROM shop_items WHERE rotation_pool = 'achievement'"
            ))).scalar_one()
            if extra_pool_sku:
                await db.execute(_text(
                    "INSERT INTO shop_items (sku, kind, name, price, rarity, rotation_pool,"
                    "                        catalog_ready)"
                    " VALUES (:sku, 'title', 'Slayer', 0, 'rare', 'achievement', TRUE)"),
                    {"sku": extra_pool_sku})
            db.add(models.Player(steam_id=steam_id, display_name="Exempt"))
            await db.commit()
            pid = (await db.execute(_text(
                "SELECT id FROM players WHERE steam_id = :s"), {"s": steam_id})).scalar_one()
            for sku in grant_skus:
                await db.execute(_text(
                    "INSERT INTO player_items (player_id, item_id, purchase_price)"
                    " SELECT :pid, id, 0 FROM shop_items WHERE sku = :sku"),
                    {"pid": pid, "sku": sku})
            await db.commit()
            out = await main.list_shop_items(request=None, steam_id=steam_id, db=db)
            return pool, {i["sku"]: i for i in out["items"]}
    finally:
        await engine.dispose()
        conn = await _asyncpg.connect(LADDER_DSN)
        try:
            await conn.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema)
        finally:
            await conn.close()


def test_the_privileged_listing_shows_no_unearned_rung():
    """THE LISTING HALF, RUN. All forty granted-only rungs are in the table
    and the exempt account owns none of them, so none may be listed. Listing
    them turns a ladder into a dropdown -- and each one would arrive marked
    `owned`, because the same exemption decides that flag."""
    _require_live_pg()
    sql = io.open(MIGRATION, encoding="utf-8").read()
    pool, listed = _run(_live_listing(_ladder_schema_name(), sql, steam_id=OWNER_STEAM))
    assert pool == 40, ("the fixture did not seed the hidden pool: %d rows" % pool)
    leaked = sorted(sku for sku in listed if sku in tl.GRANTED_ONLY_SKUS)
    assert leaked == [], ("%d unearned rung(s) listed to the exempt account: %s"
                          % (len(leaked), leaked[:3]))


def test_the_privileged_listing_still_shows_a_rung_that_was_granted():
    """The positive control. Without it the assertion above is satisfied by a
    listing that dropped the achievement pool entirely -- which would hide an
    owner's earned rung and take its Set Active button with it (v1.32)."""
    _require_live_pg()
    sql = io.open(MIGRATION, encoding="utf-8").read()
    earned = _a_granted_only_rung()
    _pool, listed = _run(_live_listing(_ladder_schema_name(), sql,
                                       steam_id=OWNER_STEAM, grant_skus=[earned]))
    assert earned in listed, "an earned rung was not listed to its owner"
    assert listed[earned]["owned"] is True
    assert [s for s in listed if s in tl.GRANTED_ONLY_SKUS] == [earned]


def test_the_privileged_listing_still_shows_the_rest_of_the_hidden_pool():
    """And the carve-out stays a carve-out on this surface too: a hidden-pool
    row that is NOT a ladder rung -- a slayer or podium title -- is still
    listed to the exempt account, owned, exactly as before."""
    _require_live_pg()
    sql = io.open(MIGRATION, encoding="utf-8").read()
    _pool, listed = _run(_live_listing(_ladder_schema_name(), sql, steam_id=OWNER_STEAM,
                                       extra_pool_sku="title_slayer_probe"))
    assert "title_slayer_probe" in listed, "the exemption stopped covering the hidden pool"
    assert listed["title_slayer_probe"]["owned"] is True
