"""Structural pins for the deferred 2v2 disconnect fallback (886bed8 round 4).

The orderings themselves are proved against a real PostgreSQL in
test_sept16_dc_fallback_orderings.py, which skips without a DSN. This file
carries the claims that are properties of the SOURCE rather than of a run, and
it runs everywhere:

  * the deferred branch is positioned so that no rating, gold or team_matches
    write is REACHABLE with is_fallback set -- a property of where the branch
    sits, not of the zero point totals a fallback happens to carry (#342);
  * the marker is stamped with clock_timestamp() and not NOW();
  * the sweep re-locks and re-checks, and cannot rate anything;
  * the sweep is registered as a PRIMARY-only scheduler and as a janitor
    self-test root;
  * every write in the state endpoint is behind the lifecycle flag, counted
    within that function's own span rather than file-wide (#432);
  * the docstrings that describe these paths say what the tree does (#302).
"""

import ast
import pathlib
import re

import pytest


API = pathlib.Path(__file__).resolve().parents[1] / "api" / "main.py"
SRC = API.read_text(encoding="utf-8")
LINES = SRC.splitlines()
TREE = ast.parse(SRC)


def span(name):
    """Source lines of one top-level def, as a list. Fails loudly if absent.

    A span, never the whole file: an occurrence count taken file-wide answers a
    different question than the one being asked and cannot fail usefully
    (#432).
    """
    for node in TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return LINES[node.lineno - 1:node.end_lineno]
    raise AssertionError(f"{name} is not a top-level def in main.py")


def code_only(lines):
    """Drop comment-only lines, so a count measures code and not prose."""
    return [ln for ln in lines if not ln.lstrip().startswith("#")]


def first_index(lines, needle):
    for i, ln in enumerate(lines):
        if needle in ln:
            return i
    return -1


# ── The report endpoint ──────────────────────────────────────────────────


def test_report_dc_takes_is_fallback_as_an_unsigned_default_false_input():
    body = span("team_series_report_dc")
    sig = [ln.strip() for ln in body if "is_fallback" in ln and "Query(" in ln]
    assert sig == ["is_fallback: bool = Query(False),"], sig
    # Unsigned: the DC canonical is frozen at reporter:series:dc_player:dc, so
    # the flag must NOT appear in the signature check's input.
    verify = span("_verify_team_dc_hmac")
    assert "is_fallback" not in "\n".join(verify)


def test_the_deferred_branch_precedes_every_rating_and_gold_write():
    body = code_only(span("team_series_report_dc"))
    branch = first_index(body, "if is_fallback:")
    assert branch >= 0, "the deferred branch is gone"
    ret = first_index(body, '"status": "deferred"')
    assert branch < ret
    for later in ("_complete_team_series_with_ratings(",
                  "INSERT INTO team_matches",
                  "SET status = 'dc_incomplete'"):
        at = first_index(body, later)
        assert at > ret, f"{later} is not after the deferred return (at {at}, return at {ret})"


def test_the_deferred_branch_sits_after_every_validation_it_must_keep():
    body = code_only(span("team_series_report_dc"))
    branch = first_index(body, "if is_fallback:")
    for earlier in (
        "FOR NO KEY UPDATE",                      # the row lock
        'reason": "dc_room_mismatch"',            # room fence
        'reason": "dc_after_resume"',             # post-relock fence
        "_assert_no_service_subject(",            # service-subject assertion
        "DC'd player isn't part of this series",  # dc-team resolution
        "reporter must be a member of the non-DC team",   # membership bind
    ):
        at = first_index(body, earlier)
        assert 0 <= at < branch, f"{earlier} does not precede the deferred branch"


def test_the_marker_is_stamped_on_the_post_lock_clock():
    body = span("team_series_report_dc")
    marker = [ln for ln in body if "dc_fallback_at = COALESCE" in ln]
    assert len(marker) == 1, marker
    assert "clock_timestamp()" in marker[0]
    # NOW() is frozen at transaction start and this handler waits on a row
    # lock; the marker must not carry a pre-wait time (#277).
    assert "NOW()" not in marker[0]


def test_the_deferred_return_is_distinguishable_from_an_old_servers_answer():
    # An api that predates the flag answers 200 and ignores it, having already
    # settled (bug #266, learning #422). The caller's only discriminator is the
    # body, so the deferred status string must not be one the old code returns.
    body = "\n".join(span("team_series_report_dc"))
    assert '"status": "deferred"' in body
    assert '"deferred": True' in body
    assert body.count('"status": "deferred"') == 1


def test_the_report_docstring_no_longer_claims_two_outcomes():
    # The endpoint has a third disposition now; a docstring asserting the old
    # count is a claim the tree does not keep (#302, #351).
    doc = ast.get_docstring(
        next(n for n in TREE.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == "team_series_report_dc"))
    assert "Two outcomes" not in doc
    assert "Three outcomes" in doc
    assert "DEFERRED" in doc


# ── The sweep ────────────────────────────────────────────────────────────


def test_the_sweep_relocks_and_rechecks_inside_the_transaction():
    body = code_only(span("_team_dc_fallback_sweep_once"))
    joined = "\n".join(body)
    # One locked re-read, in the same mode the report handler takes (#202).
    # Comment lines are stripped first: the prose above the statement names the
    # mode deliberately, and a count that included it would measure the
    # comment (#432).
    assert joined.count("FOR NO KEY UPDATE") == 1
    assert "FOR UPDATE\n" not in joined and "FOR UPDATE " not in joined
    # The predicate is re-checked under that lock, and again in the UPDATE's
    # own WHERE -- two independent guards, both required (#208).
    assert 'locked["status"] not in ("active", "dc_paused")' in joined
    assert 'not locked["past_bound"]' in joined
    assert joined.count("AND status IN ('active', 'dc_paused')") == 1


def test_the_sweep_measures_the_bound_on_the_same_clock_as_the_marker():
    joined = "\n".join(span("_team_dc_fallback_sweep_once"))
    # Discovery and the locked re-read, both on clock_timestamp().
    assert joined.count("clock_timestamp() - make_interval(secs => :bound)") == 2
    assert "NOW()" not in joined


def test_the_sweep_keeps_the_live_game_veto():
    joined = "\n".join(span("_team_dc_fallback_sweep_once"))
    assert joined.count("_group_game_in_progress(str(sid))") == 1
    # The conservative variant, per that helper's own caller contract: a
    # janitor closer that re-fires every tick must veto on a young process.
    assert "_group_game_positively_live" not in joined


def test_the_service_subject_refusal_skips_the_row_not_the_batch():
    # Letting it propagate would abort the rest of the batch every tick for as
    # long as the offending row is due, which starves the other candidates.
    body = code_only(span("_team_dc_fallback_sweep_once"))
    at = first_index(body, "await _assert_no_service_subject(")
    assert at > 0
    assert body[at - 1].strip() == "try:"
    after = body[at:at + 8]
    assert any("except HTTPException:" in ln for ln in after), after
    assert any(ln.strip() == "continue" for ln in after), after


def test_the_sweep_cannot_rate_or_pay_anything():
    joined = "\n".join(span("_team_dc_fallback_sweep_once"))
    for forbidden in ("_complete_team_series_with_ratings",
                      "_reconcile_team_series_bets",
                      "status = 'completed'",
                      "glicko"):
        assert forbidden not in joined, forbidden
    # The only status it can write.
    writes = re.findall(r"SET status = '(\w+)'", joined)
    assert writes == ["dc_incomplete"], writes


def test_the_sweep_is_a_primary_only_scheduler():
    lifespan = "\n".join(span("lifespan"))
    assert lifespan.count('_supervised("team_dc_fallback_sweep"') == 1
    primary = lifespan.index("booting as PRIMARY")
    reg = lifespan.index('_supervised("team_dc_fallback_sweep"')
    assert reg > primary, "the sweep is registered outside the primary branch"
    # It must not also be started on the replica path.
    replica = lifespan.index("BOOTING AS READ REPLICA")
    assert replica < primary


def test_the_sweep_is_a_janitor_selftest_root():
    # Its SQL names a column migration 326 adds; the boot-time EXPLAIN is what
    # makes a migration-after-api deploy loud instead of silent.
    roots = next(n for n in TREE.body
                 if isinstance(n, ast.Assign)
                 and getattr(n.targets[0], "id", "") == "_JANITOR_SELFTEST_ROOTS")
    names = {e.elts[1].value for e in roots.value.elts}
    assert "team_dc_fallback_sweep_loop" in names


# ── The state read (H1 server side) ──────────────────────────────────────


def test_every_write_in_the_state_endpoint_is_behind_the_lifecycle_flag():
    body = span("team_series_state")
    joined = "\n".join(body)
    code = code_only(body)
    # Counted within THIS function's span: two mutating arms, two commits,
    # each gated. A file-wide count would measure something else (#432).
    assert len([ln for ln in code if "UPDATE team_series" in ln]) == 2
    assert len([ln for ln in code if "await db.commit()" in ln]) == 2
    # Drop the signature and the docstring before counting: the span starts at
    # the def, and the flag is named in both by construction.
    doc_end = next(i for i, ln in enumerate(code) if ln.rstrip().endswith('"""'))
    guards = [ln.strip() for ln in code[doc_end + 1:]
              if re.match(r"^(if )?lifecycle\b", ln.strip())]
    assert guards == [
        "lifecycle",                                    # the assembly-cancel arm
        'if lifecycle and dc_grace_seconds_remaining == 0 and s_status == "dc_paused":',
    ], guards
    assert joined.count('"lifecycle": lifecycle') == 3   # one per return
    assert "    lifecycle: bool = Query(True)," in body


def test_the_state_docstring_says_the_get_writes_and_names_who_keeps_it():
    doc = ast.get_docstring(
        next(n for n in TREE.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == "team_series_state"))
    assert "THIS GET WRITES" in doc
    assert "PollAssemblyStateLoop" in doc
    assert "lifecycle=false" in doc


@pytest.mark.parametrize("token", ["dc_fallback_at", "dc_fallback_player_id"])
def test_the_marker_columns_are_added_by_a_migration_on_disk(token):
    sql = (pathlib.Path(__file__).resolve().parents[1] / "sql"
           / "326_team_series_dc_fallback_at.sql").read_text(encoding="utf-8")
    assert f"ADD COLUMN IF NOT EXISTS {token}" in sql
    assert sql.strip().startswith("--")
    assert "\nBEGIN;" in sql and sql.rstrip().endswith("COMMIT;")


def test_the_resume_path_clears_the_marker():
    # A resume flips a settled series back to 'active'; a surviving marker is
    # older than the bound by definition and the sweep would settle the
    # resumed series on its next tick.
    joined = "\n".join(span("_team_relock_existing_series"))
    assert '"   SET dc_fallback_at = NULL, dc_fallback_player_id = NULL"' in joined
    # Its own savepoint: a caught SQL error poisons the whole transaction under
    # asyncpg (#235), and this resume must not start failing because a deploy
    # ran before migration 326.
    at = first_index(span("_team_relock_existing_series"), "SET dc_fallback_at = NULL")
    before = span("_team_relock_existing_series")[max(0, at - 4):at]
    assert any("begin_nested()" in ln for ln in before), before
