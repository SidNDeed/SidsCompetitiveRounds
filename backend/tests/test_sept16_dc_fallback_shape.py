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
  * nothing awaits between the sweep's post-lock live-game veto and its
    settlement write, so the veto cannot be read stale (round-4 HIGH);
  * a caller that must not mutate has its own ROUTE rather than a flag on the
    mutating one -- the route holds no write, and the state endpoint has no
    lifecycle parameter left to ignore;
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
    # TWO evaluations: a cheap pre-lock filter and the post-lock decision. The
    # ORDER of the two is pinned separately, in
    # test_the_liveness_veto_is_re_evaluated_after_the_lock_is_held.
    assert joined.count("_group_game_in_progress(str(sid))") == 2
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
    after = body[at:at + 10]
    assert any("except HTTPException:" in ln for ln in after), after
    assert any(ln.strip() == "continue" for ln in after), after
    # It now runs with the row lock HELD, so skipping the row has to release
    # it: a bare `continue` would carry the lock through the rest of the batch
    # and into the caller's session.
    refusal = after[first_index(after, "except HTTPException:"):]
    assert any(ln.strip() == "await db.commit()" for ln in refusal), refusal


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


# ── The read-only status ROUTE (H1 server side) ──────────────────────────
#
# Round 4 made the read-only guarantee a PARAMETER of the mutating endpoint,
# and an unknown parameter is exactly what a box that predates it answers 200
# while ignoring (bug #266, learning #422). Round 5 makes it a separate route,
# because a box that lacks a route cannot answer on it.

ROUTE = '@app.get("/api/v1/team/series/{series_id}/status", tags=["Team Matches"])'
WRITE_TOKENS = ("UPDATE ", "INSERT ", "DELETE ", "db.commit(", "begin_nested(",
                "_reconcile_team_series_bets(", "_complete_team_series_with_ratings(")


def test_the_read_only_route_is_registered():
    assert ROUTE in SRC, "the read-only status route is not registered"
    # And it is a distinct path from the mutating one, not a rewrite of it.
    assert '@app.get("/api/v1/team/series/{series_id}/state", tags=["Team Matches"])' in SRC


@pytest.mark.parametrize("token", WRITE_TOKENS)
def test_the_read_only_route_performs_no_write(token):
    """No write of any shape inside the route's own span (#432).

    Parametrized so a failure NAMES the token that appeared rather than
    reporting a boolean. The live half -- that the statements the route
    actually puts on a connection are all SELECTs -- is in the orderings file,
    with the mutating state GET under the same recorder as the control that
    the recorder can see a write at all (#391).
    """
    code = code_only(span("team_series_status_readonly"))
    hits = [ln.strip() for ln in code if token in ln]
    assert hits == [], hits


def test_the_read_only_route_states_the_capability_in_its_own_body():
    code = code_only(span("team_series_status_readonly"))
    joined = "\n".join(code)
    # The client treats an answer without this key as no answer. It is the
    # whole capability negotiation: proven per RESPONSE, by the box that
    # produced it, never advertised in advance.
    assert '"readonly": True,' in joined, joined


def test_the_state_endpoint_has_no_lifecycle_parameter_left():
    # code_lines_of, not code_only: the docstring NAMES the deleted parameter
    # on purpose, and prose about a removal is not the removal (#302).
    code = code_lines_of(node_named("team_series_state"))
    joined = "\n".join(code)
    # The two mutating arms and their commits are unchanged and UNGATED again:
    # this endpoint is the assembly poll's lifecycle operation and nothing
    # else. Counted within THIS function's span (#432).
    assert len([ln for ln in code if "UPDATE team_series" in ln]) == 2
    assert len([ln for ln in code if "await db.commit()" in ln]) == 2
    assert not [ln for ln in code if re.search(r"\blifecycle\b", ln)], joined
    assert '"lifecycle"' not in joined
    # The signature is back to what production 0cc7f75 carries.
    assert ("async def team_series_state(series_id: str, "
            "db: AsyncSession = Depends(get_db)):") in joined


def test_the_state_docstring_says_the_get_writes_and_sends_readers_elsewhere():
    doc = ast.get_docstring(node_named("team_series_state"))
    assert "THIS GET WRITES" in doc
    assert "PollAssemblyStateLoop" in doc
    # It must name the route a read-only caller uses instead, or the deletion
    # of the flag reads as the feature being withdrawn.
    assert "/api/v1/team/series/{series_id}/status" in doc


@pytest.mark.parametrize("token", ["dc_fallback_at", "dc_fallback_player_id"])
def test_the_marker_columns_are_added_by_a_migration_on_disk(token):
    sql = (pathlib.Path(__file__).resolve().parents[1] / "sql"
           / "326_team_series_dc_fallback_at.sql").read_text(encoding="utf-8")
    assert f"ADD COLUMN IF NOT EXISTS {token}" in sql
    assert sql.strip().startswith("--")
    assert "\nBEGIN;" in sql and sql.rstrip().endswith("COMMIT;")


# ── The revival operation, counted across the whole file ─────────────────
#
# The first cut of this change cleared the marker in ONE of the two same-four
# adoption funnels, and the test that was supposed to hold it read the span of
# that one function -- so it could not fail on the other (#432, #330). What
# follows asks the question of the FILE: which functions revive a series, and
# does each of them clear the marker.

REVIVAL = "SET status = 'active',"


def node_named(name):
    for node in TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} is not a top-level def in main.py")


def code_lines_of(node):
    """A def's own lines with its DOCSTRING and comment lines blanked out.

    Prose about an operation is not the operation. Without this, a docstring
    that merely names the SQL it governs joins the set of functions that
    perform it and the count stops meaning anything.
    """
    lines = LINES[node.lineno - 1:node.end_lineno]
    if ast.get_docstring(node) is not None:
        d = node.body[0]
        lo, hi = d.lineno - node.lineno, d.end_lineno - node.lineno
        lines = lines[:lo] + [""] * (hi - lo + 1) + lines[hi + 1:]
    return [ln for ln in lines if not ln.lstrip().startswith("#")]


def functions_performing(needle):
    """Every top-level def whose own CODE contains `needle`, by name."""
    return sorted(
        n.name for n in TREE.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(needle in ln for ln in code_lines_of(n)))


def test_every_funnel_that_revives_a_series_clears_the_deferral_marker():
    # The set is named, not counted loosely: a third funnel appearing here is a
    # thing to look at, not a number to bump.
    funnels = functions_performing(REVIVAL)
    assert funnels == ["_team_relock_existing_series", "team_lobby_start"], funnels
    # "Revives a series" and "clears the DC fields" are ONE set, not two -- the
    # qualifier in the finding was 'the UPDATE ... that clears dc_player_id'.
    assert functions_performing("dc_player_id = NULL,") == funnels
    for name in funnels:
        code = code_lines_of(node_named(name))
        assert any("_team_clear_dc_fallback_marker(" in ln for ln in code), (
            f"{name} flips a series back to 'active' without clearing the "
            "deferral marker; the sweep will settle it again on its next tick")


def test_the_marker_clear_lives_in_one_savepointed_helper():
    code = code_lines_of(node_named("_team_clear_dc_fallback_marker"))
    joined = "\n".join(code)
    # Both columns, or a stale attribution survives the resume.
    assert '"   SET dc_fallback_at = NULL, dc_fallback_player_id = NULL"' in joined
    # Its own savepoint: a caught SQL error poisons the whole transaction under
    # asyncpg (#235), and neither resume may start failing because a deploy ran
    # before migration 326.
    at = first_index(code, "SET dc_fallback_at = NULL")
    assert any("begin_nested()" in ln for ln in code[max(0, at - 4):at]), code
    # And the SQL exists in exactly one place, so there is no second copy to
    # drift: the two call sites carry a call, never their own UPDATE.
    assert functions_performing("SET dc_fallback_at = NULL") == [
        "_team_clear_dc_fallback_marker"]


# ── The bound ────────────────────────────────────────────────────────────


def test_the_bound_is_derived_from_the_assembly_ceiling_not_from_transport_alone():
    import main
    budget = main._DC_CLIENT_TRANSPORT_BUDGET_SECONDS
    hold = main._ASSEMBLY_DEADLINE_SECONDS
    # The bound covers the HOLD, the held report's own budget and one
    # re-election budget. The first cut was 120 s, derived from transport
    # alone; it fails this line, which is the point of having the line.
    assert main._DC_FALLBACK_DEFER_SECONDS >= hold + 2 * budget
    # The comment above the constant has to name the term it now includes,
    # because a derivation nobody can trace is a claim (#302).
    head = "\n".join(LINES[:node_named("_team_clear_dc_fallback_marker").lineno])
    assert "_ASSEMBLY_DEADLINE_SECONDS = 180" in head
    assert "WHAT THE DERIVATION DOES NOT COVER" in head


def test_the_sweep_does_not_consult_the_room_clock():
    """The 214 s "second refusal" is gone, constant and all.

    It could not refuse a row. An ordinary room is stamped when it is ISSUED,
    before the sitting that produces the marker, so a marker past 420 s always
    sat on a room past 214 s; and a continuation series carries a real room
    with a NULL room_issued_at, which made the term true on arrival. A check
    that cannot fail is worse than no check (#342, #431, #441), so it is
    deleted rather than patched (#310, #389).
    """
    import main
    assert not hasattr(main, "_DC_FALLBACK_ROOM_QUIET_SECONDS")
    code = code_only(span("_team_dc_fallback_sweep_once"))
    joined = "\n".join(code)
    assert "room_issued_at" not in joined, (
        "the sweep is reading the room clock again")
    assert "room_quiet" not in joined
    assert '"quiet"' not in joined
    # One time term remains, and it is named in both statements: the bound.
    assert joined.count("float(_DC_FALLBACK_DEFER_SECONDS)") == 2, joined


def flat_code_of(node):
    """A def's own code as ONE whitespace-normalized string.

    A per-LINE substring test answers "does any single line spell it this
    way", which is a question about formatting. The census below is about a
    COLUMN and the value written to it, so the span is flattened first: a
    respelling, a different amount of space around the `=`, or the column and
    its value landing on two lines of the same SQL string all still count
    (#619, #591 -- follow the value, never the spelling).
    """
    return re.sub(r"\s+", " ", " ".join(code_lines_of(node)))


# `room_issued_at` preceded by no word character and no dot, so `ts.room_issued_at`
# in a SELECT and `r["room_issued_at"]` in a read are not writes; then `=` and the
# bare token of whatever is written -- NOW, clock_timestamp, NULL, :bind.
ROOM_CLOCK_WRITE = re.compile(r"(?<![\w.])room_issued_at\s*=\s*([:\w]+)")


def functions_touching_the_room_clock():
    """{def name: the set of values it writes to room_issued_at}, file-wide.

    An SQL equality test on the column would land here too, as a value it
    appears to write. That is the direction this check is meant to fail in: a
    new use of the column shows up as an unexpected NAME and reddens the test,
    rather than being silently absent from a spelling-keyed census.
    """
    found = {}
    for n in TREE.body:
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        vals = {m.group(1) for m in ROOM_CLOCK_WRITE.finditer(flat_code_of(n))}
        if vals:
            found[n.name] = vals
    return found


def test_every_room_issue_clears_the_deferral_marker():
    """What makes the deletion above safe, asked of the FILE.

    With no room term in the sweep, the property the sweep relies on is that a
    marker is never older than the room it would be settled against. That is
    an invariant about the room-ISSUE operation, not about the sweep: whoever
    stamps room_issued_at must clear the marker in the same breath. Counted
    file-wide, because the defect is a class and a span-local count could not
    see a third funnel (#432, #330).

    Keyed on the COLUMN, not on one spelling of the statement that writes it.
    The first cut matched the literal line `room_issued_at = NOW()`, so a
    rematch or re-host funnel spelled `room_issued_at=clock_timestamp()`, or
    written across two lines of its SQL, would have left the census reading
    exactly ["team_queue_poll"] and the per-issuer check below would never
    have run on it -- silence for precisely the drift the test exists to
    catch (#342, #431, #441).
    """
    writers = functions_touching_the_room_clock()
    stampers = sorted(n for n, vals in writers.items() if vals != {"NULL"})
    clearers = sorted(n for n, vals in writers.items() if vals == {"NULL"})
    # The set is named, not counted: a new funnel is a thing to look at.
    assert stampers == ["team_queue_poll"], writers
    for name in stampers:
        code = code_lines_of(node_named(name))
        assert any("_team_clear_dc_fallback_marker(" in ln for ln in code), (
            f"{name} stamps room_issued_at without clearing the deferral "
            "marker; a marker filed against the previous sitting would then "
            "settle the new one")
    # And the only other writers of the column set it to NULL -- the two
    # resume funnels dropping the dead room. A third value would be a new
    # shape this reasoning has not been done for.
    assert clearers == ["_team_relock_existing_series", "team_lobby_start"], writers


def test_the_bound_sentence_is_one_sentence_in_every_copy():
    """The cross-lane sentence, character for character, in both server copies.

    The client lane carries the same string; the lens greps both trees for it
    (#341, #444). A paraphrase is how two lanes start describing different
    behaviour while each looks correct on its own.
    """
    sentence_words = (
        "A real-totals report wins while the deferred marker is younger than "
        "420 seconds, and after that only until a sweep tick finds no "
        "live-game evidence for the series and settles the row; once a row is "
        "settled, a later report is refused at the settled-row exit and is "
        "not rated.")

    def normalized(text):
        return re.sub(r"\s+", " ", re.sub(r"(?m)^\s*(--|#)\s?", " ", text))

    api_norm = normalized(SRC)
    assert api_norm.count(sentence_words) == 3, (
        "main.py must carry the bound sentence three times: the derivation "
        "beside _DC_FALLBACK_DEFER_SECONDS, the deferral branch of report-dc, "
        "and the sweep loop's docstring")
    sql = (pathlib.Path(__file__).resolve().parents[1] / "sql"
           / "326_team_series_dc_fallback_at.sql").read_text(encoding="utf-8")
    assert sentence_words in normalized(sql)
    # And the claim it replaced is gone from both.
    assert "at ANY later moment still finds" not in SRC
    assert "at ANY later moment still finds" not in sql


# ── The lock, the veto and the attribution ───────────────────────────────


def test_the_sweep_never_queues_behind_a_holder():
    code = code_only(span("_team_dc_fallback_sweep_once"))
    joined = "\n".join(code)
    # There is no lock_timeout on the engine and none set here, so an
    # unqualified lock is an unbounded wait that starves the rest of the batch
    # (the loop is sleep-then-one-pass). Every sibling janitor in this file
    # takes the weakest lock WITH SKIP LOCKED for exactly that reason.
    assert joined.count("FOR NO KEY UPDATE SKIP LOCKED") == 1
    assert joined.count("FOR NO KEY UPDATE") == 1, (
        "an unqualified FOR NO KEY UPDATE is still in the sweep")
    assert "FOR UPDATE\n" not in joined


def test_the_liveness_veto_is_re_evaluated_after_the_lock_is_held():
    code = code_only(span("_team_dc_fallback_sweep_once"))
    vetoes = [i for i, ln in enumerate(code) if "_group_game_in_progress(" in ln]
    assert len(vetoes) == 2, vetoes
    lock = first_index(code, "FOR NO KEY UPDATE SKIP LOCKED")
    settle = first_index(code, "SET status = 'dc_incomplete'")
    # One before the lock as a cheap filter, one after it as the decision. The
    # in-transaction re-check covers COLUMNS; liveness is in-process evidence
    # and no SQL predicate can re-read it.
    assert vetoes[0] < lock < vetoes[1] < settle, (vetoes, lock, settle)


def test_nothing_awaits_between_the_post_lock_veto_and_the_settlement_write():
    """The round-4 HIGH, as a property of the source.

    Liveness is in-process evidence, so it is only as current as the last
    moment this coroutine held the event loop. Round 4 ran the awaited
    service-subject lookup AFTER the post-lock veto; on a cold or hourly-
    expired cache that lookup issues its own SELECT, and any await lets the
    presence ping that publishes in-match evidence for this very series run to
    completion. The veto's answer was then a reading of the past and the
    settlement write acted on it as current.

    So: the veto is the LAST thing read before the write, and between them
    there is no await of any kind. Asserted over this function's own span
    (#432) and on the AST rather than on a line count, so a helper call that
    happens to be written across two lines cannot slip through.
    """
    node = node_named("_team_dc_fallback_sweep_once")

    def veto_calls(stmt):
        return [n for n in ast.walk(stmt)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_group_game_in_progress"]

    assert len(veto_calls(node)) == 2, "the sweep no longer has two vetoes"
    loops = [n for n in ast.walk(node) if isinstance(n, ast.For)]
    assert len(loops) == 1, "the per-row loop is not where it was"
    body = loops[0].body

    # The post-lock veto is the LAST top-level `if` in the loop whose own test
    # calls the veto. Its own branch is the vetoed path -- awaits in there
    # happen instead of the write, not before it -- so the question is only
    # about the SIBLINGS that follow it.
    veto_idx = [i for i, st in enumerate(body)
                if isinstance(st, ast.If) and veto_calls(st.test)]
    assert veto_idx, "no `if` in the per-row loop tests the live-game veto"
    after = body[veto_idx[-1] + 1:]
    assert after, "nothing follows the post-lock veto"

    first_await = None
    for stmt in after:
        awaits = sorted(n.lineno for n in ast.walk(stmt)
                        if isinstance(n, ast.Await))
        if awaits:
            first_await = (stmt, awaits[0])
            break
    assert first_await is not None, "the settlement write disappeared"
    stmt, lineno = first_await
    text_of = "\n".join(LINES[stmt.lineno - 1:stmt.end_lineno])
    assert "SET status = 'dc_incomplete'" in text_of, (
        "the first thing awaited after the post-lock live-game veto is not "
        f"the settlement write but line {lineno}: {LINES[lineno - 1].strip()!r}"
        " -- the veto is stale by however long that await takes")

    # And the service-subject lookup -- the await that used to be there -- now
    # runs BEFORE the veto, where its cost is paid while nothing is decided.
    service = [n.lineno for n in ast.walk(node)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "_assert_no_service_subject"]
    assert len(service) == 1, service
    assert service[0] < body[veto_idx[-1]].lineno, (service, veto_idx)


def test_every_value_the_settle_writes_is_read_from_the_locked_row():
    code = code_only(span("_team_dc_fallback_sweep_once"))
    joined = "\n".join(code)
    # Discovery carries the id and nothing else.
    assert any(ln.strip() == "SELECT ts.id" for ln in code), code[:20]
    for key in ("dc_fallback_player_id", "t1a_id", "t1b_id", "t2a_id", "t2b_id"):
        assert f'locked["{key}"]' in joined, key
        assert f'row["{key}"]' not in joined, (
            f"{key} is carried from the UNLOCKED discovery pass into a write")
    # The service-subject refusal judges the same four ids the settle
    # attributes to, with the lock held.
    assert first_index(code, "FOR NO KEY UPDATE SKIP LOCKED") < first_index(
        code, "_assert_no_service_subject(")


# ── /mod-version advertises no capability ────────────────────────────────


def test_mod_version_advertises_no_capability():
    """The advertisement is deleted, not merely unused.

    An answer from /mod-version cannot speak for the box that answers a LATER
    request: the edge chooses an upstream per request and the two boxes are
    deployed independently (learning #422). Leaving the key in place while the
    client stopped reading it would leave the next reader a mechanism to
    revive.
    """
    code = code_lines_of(node_named("get_mod_version"))
    joined = "\n".join(code)
    assert "series_status_readonly" not in joined, joined
    # The two version numbers, and nothing else.
    assert '"version": LATEST_MOD_VERSION' in joined
    assert '"min_version": MIN_MOD_VERSION_EFFECTIVE}' in joined
    doc = ast.get_docstring(node_named("get_mod_version"))
    # The docstring must say WHY, or the next pass re-adds it.
    assert "NO CAPABILITY IS ADVERTISED HERE" in doc
    assert "/status" in doc


# ── The report endpoint's build discriminator ────────────────────────────


def test_every_200_exit_of_report_dc_carries_the_deferred_field():
    """W23 is a measurement only if the field rides the non-deferring exits.

    Absent from a 200, "deferred" means the answering box predates the flag;
    present and false, it means this build did not park the report -- which is
    NOT the same as "this call settled the series", and the next test holds
    the file's wording to that difference. With the field only on the deferral
    branch a client could not tell false from absent, and its log line would
    measure nothing (r4 client L4).
    """
    node = node_named("team_series_report_dc")
    returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
    assert len(returns) == 6, len(returns)
    for r in returns:
        assert isinstance(r.value, ast.Dict), ast.dump(r.value)
        keys = [k.value for k in r.value.keys if isinstance(k, ast.Constant)]
        assert "deferred" in keys, (r.lineno, keys)
    # Exactly one of them defers; the other five say so explicitly.
    src = "\n".join(code_only(span("team_series_report_dc")))
    assert src.count('"deferred": True') == 1
    assert src.count('"deferred": False') == 5


# The ONE definition of the field, as it stands in main.py. One copy, not four:
# a rule restated in several places is re-derived in several places, and round
# 5 shipped three restatements of this one that each said something the code
# does not do (#660, #701, #351).
FIELD_SENTENCE = (
    '"deferred" says only whether THIS call parked the report: true when it '
    'did, false on the five exits that do not park one -- two of which settle '
    'the series while the other three, the settled-row exit and the two room '
    'fences, decide nothing and say so with "ignored": true -- and absent '
    'only from a box that predates the flag.')


def test_the_deferred_definition_is_single_and_its_arithmetic_matches_the_exits():
    """The field's definition is a claim about all six exits; count them.

    The round-5 wording said false meant "this box carries the deferral build
    and settled it". Three of the five false exits settle nothing: the
    settled-row exit answers for a row somebody else had already terminated,
    and the two room fences DISCARD a stale report and leave the series
    'active' and open. A maintainer who built the next guard on "false means
    settled" would close a series that is still expecting a real-totals
    report.

    So the definition now names the split, and this test binds its arithmetic
    to the AST: change what an exit does, or add a sixth, and the sentence
    stops being true and this goes red.
    """
    def normalized(text_):
        return re.sub(r"\s+", " ", re.sub(r"(?m)^\s*#\s?", " ", text_))

    # ONE definition in the file, at the branch that creates the deferral.
    assert normalized(SRC).count(FIELD_SENTENCE) == 1, (
        "the field is defined zero times, or restated in a second place "
        "where the two copies can drift")
    branch = "\n".join(span("team_series_report_dc"))
    assert FIELD_SENTENCE in normalized(branch)

    node = node_named("team_series_report_dc")
    returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]

    def key(r, name):
        for k, v in zip(r.value.keys, r.value.values):
            if isinstance(k, ast.Constant) and k.value == name:
                return v
        return None

    deferring = [r for r in returns
                 if isinstance(key(r, "deferred"), ast.Constant)
                 and key(r, "deferred").value is True]
    not_deferring = [r for r in returns if r not in deferring]
    # "decide nothing and say so with ignored: true"
    ignoring = [r for r in not_deferring
                if isinstance(key(r, "ignored"), ast.Constant)
                and key(r, "ignored").value is True]
    # "two of which settle the series" -- a settling exit names the terminal
    # status it wrote as a literal; the three that decide nothing echo the
    # status they READ (s["status"]) or carry no terminal status at all.
    settling = [r for r in not_deferring
                if isinstance(key(r, "status"), ast.Constant)
                and key(r, "status").value in ("completed", "dc_incomplete")]

    assert len(deferring) == 1, [r.lineno for r in deferring]
    assert len(not_deferring) == 5, [r.lineno for r in not_deferring]
    assert len(ignoring) == 3, [r.lineno for r in ignoring]
    assert len(settling) == 2, [r.lineno for r in settling]
    # The two sets partition the five: no exit both settles and says it
    # decided nothing, and none of the five is unaccounted for.
    assert not set(id(r) for r in ignoring) & set(id(r) for r in settling)
    assert len(ignoring) + len(settling) == len(not_deferring)

    # A literal backstop for the exact claims round 5 carried. It catches a
    # revert of the wording and nothing cleverer -- the arithmetic above is
    # what catches a NEW overclaim, because a new one has to contradict a
    # count (#441: a grep for a common spelling answers a weaker question
    # than the one being asked).
    for gone in ("carries the deferral build and settled it",
                 "knows this build settled its report",
                 "false on each settling exit",
                 "present and false, it means this build settled the report"):
        assert gone not in SRC, gone
