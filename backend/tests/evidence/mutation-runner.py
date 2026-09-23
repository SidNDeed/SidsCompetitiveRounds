"""The mutation controls for this lane, each with a NEGATIVE control (#391).

COMMITTED rather than kept in a scratch directory, because a report that names
its instrument under a gitignored path is a report nobody on a fresh clone can
re-derive (the round-7 finding on round 6's evidence). Everything this needs it
takes from its own location or from the environment, so it runs wherever the
repository is checked out:

    FFA_TEST_PG_DSN=postgresql+asyncpg://<user>@<host>:<port>/<scratch-db> \\
        python backend/tests/evidence/mutation-runner.py

For every control: apply the MUTATION to the real source, run the named test,
require it to FAIL and print the red line; restore; apply an INERT edit at the
SAME site, run the same test, require it to PASS. A test that reddens for any
edit at all measures a line's shape rather than a behaviour, which is exactly
what the negative control is for -- and it has fired here: round 6's
`insert-failure-answers-bare` inert edit (a call reflowed across two lines)
reddened its test, the assertion was rewritten against flattened source, and
the reflow is kept as that control's inert edit ever since.

Anchors are pre-checked, all of them, BEFORE any test runs: a mutation whose
anchor does not resolve exactly once would otherwise abort the set mid-way and
leave a later control looking deliberately skipped.

Files are restored from byte-exact copies taken here, never with
`git checkout --` or `git restore` (#290/#401: forbidden on a tree carrying
uncommitted work). The md5 of every touched file is compared at the end and the
run fails loudly if any file did not come back.

EVERY round's controls are here, this round's and all the earlier ones'. The
earlier ones are re-run rather than trusted: each round's edits move code
around several of the previous anchors, and a control that is not re-run on
the tree it certifies is an assertion about a different tree. The rounds are
deliberately not listed by number in this header -- an enumeration of a set
that grows goes stale the round after it is written, which is the same defect
closed twice elsewhere in this round. CONTROLS below is the inventory.

IT PRINTS ITS OWN INVOCATION, and that is round 8's correction to round 7's
log. A report that shows fourteen RED lines and a tally, with no record of what
was actually run, is a summary of a selection nobody can check -- a different
selection would look identical. The invocation block below the anchor pre-check
names the command, the interpreter, the working directory and the exact pytest
command line of every control, all of them REPOSITORY-RELATIVE so the committed
log names paths a clone has rather than this machine's checkout.
"""
import datetime
import hashlib
import importlib.util
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # backend/tests/evidence
BACKEND = os.path.dirname(os.path.dirname(HERE))           # backend
ROOT = os.path.dirname(BACKEND)                            # repository root
MAIN = os.path.join(BACKEND, "api", "main.py")
TESTS = os.path.join(BACKEND, "tests", "test_ffa_game_number_anchor.py")
EVIDENCE_RULES = os.path.join(HERE, "evidence_rules.py")
RESIDUAL_RULES = os.path.join(HERE, "residual_rules.py")
ASSEMBLER = os.path.join(HERE, "assemble-evidence.py")
# Shipped by the same deploy as the api (docs/deploy-reference.md maps it to
# the primary), and outside every glob round 8's shipped-file rule read.
DOCKERFILE_BOT = os.path.join(BACKEND, "Dockerfile.bot")
# The repository ignore file, whose evidence-log negation admits one pattern
# per producer; the assembly producer whose capture one of them names; and the
# re-pin wrapper, which is the one producer that OPENS its own capture, so the
# name that pattern is paired against is a value it computes rather than a
# line it prints.
GITIGNORE = os.path.join(ROOT, ".gitignore")
RUN_ASSEMBLY = os.path.join(HERE, "run-assembly.sh")
REPIN = os.path.join(HERE, "repin-last.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The round a report's NAME puts it in, from the one implementation of that
# rule rather than from a second regex here (#432).
_RULES = _load("_scr_evidence_rules_for_runner", EVIDENCE_RULES)


def _newest_report(suffix):
    """The highest-numbered report of one kind that EXISTS right now.

    Round 10 wrote `r10-suites.txt` here as a literal, with a comment saying
    which round it belonged to. A path with a round number in it is a thing to
    remember to bump, and a forgotten one makes this round's controls mutate
    the PREVIOUS round's report -- a mutation that resolves, reds its test and
    proves nothing about the artifact this round is committing. Derived, it
    cannot be stale."""
    best = None
    for name in sorted(os.listdir(HERE)):
        if not name.endswith(suffix):
            continue
        number = _RULES.round_of(name)
        if number is not None and (best is None or number > best[0]):
            best = (number, name)
    return None if best is None else os.path.join(HERE, best[1])


# THE NEWEST suites report in this directory, which is what two controls
# mutate -- the invocation rule and the assembler's. WHICH round's report that
# is depends on when the runner runs, and saying so is the correction of a
# sentence that called it "the report of the round this runner is being run
# for": on a first pass over a round, that round's suites report does not exist
# yet and this is the PREVIOUS round's; on a second pass over the same round it
# is that round's own, as the earlier pass left it. Either way the two controls
# are about the RULE a report is held to and not about the numbers in it, so
# the target is a real artifact rather than a stand-in -- and it has to EXIST,
# which is why the suite pair runs before the runner.
SUITES = _newest_report("-suites.txt")
# ...and the newest mutation-controls report. On a first pass over a round that
# is the PREVIOUS round's, because this round's is assembled from this runner's
# own output and cannot exist while the runner runs; on a second pass it is
# this round's, as the earlier pass left it. The control over it is about the
# claim a report makes regarding its own round, and every report carrying that
# heading is checked, so either is a real target rather than a stand-in.
MUTATION_REPORT = _newest_report("-mutation-controls.txt")
DSN = os.environ.get("FFA_TEST_PG_DSN")

# The last of this runner's values that had to RESOLVE against a real artifact
# and was still written by hand. Scope stated exactly, because "the last one"
# is a count of a set and this round exists to stop those being written from
# memory: round-numbered strings remain in this directory in two shapes that
# resolve against nothing -- the fabricated report names in evidence_rules.py,
# which are fixtures, and the example stdout header in assemble-evidence.py's
# docstring, which is prose. Neither is a value a run dereferences. The two
# that were, SUITES and MUTATION_REPORT, are derived above; this was the third.
#
# The control below reproduces a report crediting its own round with a control
# another round added, and it did so by naming two controls here: one to take
# out of the report's list and one to put in. Both are names belonging to one
# round, so both go stale the round after they are written -- the same shape as
# the round-numbered path two definitions up, and the same shape as the defect
# the control exists FOR. A stale anchor refuses loudly at the pre-check rather
# than passing, so what it costs is a runner that will not start; that is still
# a control somebody has to hand-carry, which is what the method says not to do.
UNDERIVED = "\x00 this control's anchor could not be derived \x00"


def _report_claim_swap():
    """(anchor, mutant, inert, why) for the new-controls control.

    The anchor is a control the report LISTS as new in its own round; the
    mutant is one the inventory tags for an EARLIER round and the report does
    not list, so the swap reds in both directions at once -- one name listed
    and not tagged, one tagged and not listed. The inert twin is the anchor
    with a trailing space: still the same claim, so a rule keyed on the line's
    shape rather than on the name it carries would red here (#391). `why` is
    None when all three resolved, and names the one fact that is wrong
    otherwise."""
    if MUTATION_REPORT is None or not os.path.isfile(MUTATION_REPORT):
        return UNDERIVED, UNDERIVED, UNDERIVED, (
            "there is no mutation-controls report in this directory to "
            "derive the swap from")
    with io.open(MUTATION_REPORT, "r", encoding="utf-8",
                 errors="replace") as fh:
        body = fh.read()
    with io.open(TESTS, "r", encoding="utf-8", errors="replace") as fh:
        doc = fh.read()
    number = _RULES.round_of(os.path.basename(MUTATION_REPORT))
    claimed = _RULES.controls_claimed_new(body) or []
    # Exactly once, or the mutation would edit two places and the control
    # would be about something other than the one claim it names.
    takeable = sorted(n for n in claimed if body.count("  %s\n" % n) == 1)
    mine = _RULES.inventory_tags(doc, number)
    earlier = set()
    for other in range(1, number):
        earlier |= _RULES.inventory_tags(doc, other)
    puttable = sorted(n for n in (earlier - mine)
                      if n not in claimed and ("  %s\n" % n) not in body)
    if not takeable:
        return UNDERIVED, UNDERIVED, UNDERIVED, (
            "%s lists no control as new in round %s that appears exactly "
            "once, so there is nothing to take out of its list"
            % (os.path.basename(MUTATION_REPORT), number))
    if not puttable:
        return UNDERIVED, UNDERIVED, UNDERIVED, (
            "the inventory tags no control for a round before %s that is "
            "absent from %s, so there is nothing to put in its place"
            % (number, os.path.basename(MUTATION_REPORT)))
    return ("  %s\n" % takeable[0], "  %s\n" % puttable[0],
            "  %s \n" % takeable[0], None)


_SWAP_ANCHOR, _SWAP_MUTANT, _SWAP_INERT, _SWAP_WHY = _report_claim_swap()


def _underived_number_edit():
    """(anchor, mutant, inert, why) for the underived-number control.

    ROUND 14 REPLACES A HAND-WRITTEN ANCHOR HERE, and the comment above the
    swap said why before it happened. This control used to quote a slice of
    the suites report's NARRATIVE, which is an anchor on one round's wording:
    round 13 reworded that sentence, nothing in round 13 read it -- the
    controls run before the suite pair, so a round's runner reads the PREVIOUS
    round's report -- and round 14's pre-check refused with `anchor resolves 0
    times`. Loud rather than silent, which is the shape a stale anchor is
    supposed to have; but still an anchor somebody re-quotes by hand every
    time the prose moves, which is what the method says not to leave standing.

    So the anchor is the one line every assembled report is REQUIRED to carry:
    the marker that separates the narrative from the verbatim run, which
    `evidence_rules` matches in every report it checks and which no round can
    reword without the assembler refusing first. The mutation inserts a line
    ABOVE it -- at the end of the narrative, the region the assembler holds to
    its log -- stating a figure no run in this directory prints. The inert
    twin inserts a sentence at the same place with no figure in it, so what
    reds is the number and not the insertion.

    `why` is None when the anchor resolved, and names the one fact that is
    wrong otherwise."""
    line = "THE RUN, verbatim from here down\n"
    if SUITES is None or not os.path.isfile(SUITES):
        return UNDERIVED, UNDERIVED, UNDERIVED, (
            "there is no suites report in this directory to derive the "
            "narrative's end from")
    with io.open(SUITES, "r", encoding="utf-8", errors="replace") as fh:
        body = fh.read()
    if body.count(line) != 1:
        return UNDERIVED, UNDERIVED, UNDERIVED, (
            "%s carries the verbatim marker %d times and the anchor needs "
            "exactly one"
            % (os.path.basename(SUITES), body.count(line)))
    if _RULES.MARKER.search(body) is None:
        return UNDERIVED, UNDERIVED, UNDERIVED, (
            "%s carries that line but the rule that matches the marker does "
            "not, so the two would be anchored on different things"
            % os.path.basename(SUITES))
    return (line,
            "The fence walked 777 paths, a figure no run here prints.\n"
            + line,
            "The fence walked the paths listed at the top of this report.\n"
            + line,
            None)


_NUM_ANCHOR, _NUM_MUTANT, _NUM_INERT, _NUM_WHY = _underived_number_edit()

# name -> (file, anchor, mutant, inert, test)
CONTROLS = [
    # ── round 6 ──────────────────────────────────────────────────────────
    ("refund-clamps-the-delta", MAIN,
     '        "UPDATE players SET gold_spent = COALESCE(gold_spent, 0) - CAST(:amt AS integer)"\n'
     '        " WHERE id = :pid AND COALESCE(gold_spent, 0) >= CAST(:amt AS integer)"\n'
     '        " RETURNING gold_spent"\n',
     '        "UPDATE players SET gold_spent = GREATEST(0, COALESCE(gold_spent, 0) - CAST(:amt AS integer))"\n'
     '        " WHERE id = :pid"\n'
     '        " RETURNING gold_spent"\n',
     '        # (inert: a comment at the same site)\n'
     '        "UPDATE players SET gold_spent = COALESCE(gold_spent, 0) - CAST(:amt AS integer)"\n'
     '        " WHERE id = :pid AND COALESCE(gold_spent, 0) >= CAST(:amt AS integer)"\n'
     '        " RETURNING gold_spent"\n',
     "test_a_refund_moves_the_exact_stake_and_never_a_clamped_one"),

    ("refund-class-swept", MAIN,
     '    await _return_stake_exactly(db, claimed["player_id"], amt,\n'
     '                                reason="lobby_bet_refund",\n'
     '                                reference_id=str(lobby_id))\n',
     '    await db.execute(text(\n'
     '        "UPDATE players SET gold_spent = GREATEST(0, COALESCE(gold_spent, 0) - :amt)"\n'
     '        " WHERE id = :pid"\n'
     '    ), {"amt": amt, "pid": claimed["player_id"]})\n'
     '    db.add(GoldTransaction(player_id=claimed["player_id"], amount=amt,\n'
     '                           reason="lobby_bet_refund", reference_id=str(lobby_id)))\n',
     '    # (inert: a comment at the same site)\n'
     '    await _return_stake_exactly(db, claimed["player_id"], amt,\n'
     '                                reason="lobby_bet_refund",\n'
     '                                reference_id=str(lobby_id))\n',
     "test_no_refund_in_the_file_still_clamps_its_delta"),

    ("variant-scan-unbounded", MAIN,
     '            " WHERE mode = :m AND group_id = :g AND photon_room_id IS NULL"\n'
     '            "   AND status = \'pending\'"\n'
     '            " ORDER BY created_at, id"\n'
     '            " LIMIT 50"\n',
     '            " WHERE mode = :m AND group_id = :g AND photon_room_id IS NULL"\n',
     '            " WHERE mode = :m AND group_id = :g AND photon_room_id IS NULL"\n'
     '            "   AND status = \'pending\'"\n'
     '            " ORDER BY created_at , id"\n'
     '            " LIMIT 50"\n',
     "test_the_variant_scan_is_bounded_by_the_quota_it_claims"),

    ("settlement-takes-for-update", MAIN,
     '_FFA_LOBBY_LOCK_SQL = "SELECT * FROM ffa_lobbies WHERE id = :lid FOR NO KEY UPDATE"\n',
     '_FFA_LOBBY_LOCK_SQL = "SELECT * FROM ffa_lobbies WHERE id = :lid FOR UPDATE"\n',
     '_FFA_LOBBY_LOCK_SQL = "SELECT  * FROM ffa_lobbies WHERE id = :lid FOR NO KEY UPDATE"\n',
     "test_the_lobby_lock_is_the_weakest_mode_that_still_conflicts_with_itself"),

    ("settled-game-without-a-named-number", MAIN,
     '    if gno is not None and named is not None and int(gno) == int(named):\n',
     '    if gno is not None:\n',
     '    if gno is not None and named is not None and int(named) == int(gno):\n',
     "test_an_answer_names_a_settled_game_only_when_the_report_named_it"),

    ("insert-failure-answers-bare", MAIN,
     '            raise FfaReportRefusal(500, "FFA match insert failed", _race_progress)\n',
     '            raise HTTPException(500, "FFA match insert failed")\n',
     '            raise FfaReportRefusal(500, "FFA match insert failed",\n'
     '                                   _race_progress)\n',
     "test_every_reachable_insert_failure_answers_with_the_lobbys_progress"),

    ("binding-sweep-posonly", MAIN,
     'async def _quarantine_on_file(db: AsyncSession, *, mode: str, room: str | None,\n'
     '                              group_id, body: str) -> tuple[str | None, bool]:\n',
     'async def _quarantine_on_file(db: AsyncSession, mode: str, room: str | None,\n'
     '                              group_id, body: str, /) -> tuple[str | None, bool]:\n',
     'async def _quarantine_on_file(db: AsyncSession, *, mode: str, room: "str | None",\n'
     '                              group_id, body: str) -> tuple[str | None, bool]:\n',
     "test_every_call_in_main_binds_to_the_function_it_names"),

    # ── round 7 ──────────────────────────────────────────────────────────
    # The RETURNING read as a VALUE instead of as a row. `0` is a real
    # balance and a falsy one, so only a refund that lands exactly on zero
    # tells the two readings apart -- and only against a live server.
    ("refund-statement-never-executed", MAIN,
     '    if moved is None:\n'
     '        raise StakeRefundRefused(\n',
     '    if not moved:\n'
     '        raise StakeRefundRefused(\n',
     '    # (inert: a comment at the same site)\n'
     '    if moved is None:\n'
     '        raise StakeRefundRefused(\n',
     "test_pg_the_exact_refund_statement_runs_against_a_real_server"),

    # Round 6's shape: stop the whole queue at the first row that cannot pay.
    ("refund-refusal-kills-the-queue", MAIN,
     '                  f"continues: {ex}")\n'
     '            continue\n',
     '                  f"continues: {ex}")\n'
     '            break\n',
     '                  f"continues: {ex}")\n'
     '            # (inert: a comment at the same site)\n'
     '            continue\n',
     "test_pg_one_unpayable_wager_does_not_block_the_rest_of_the_queue"),

    # Round 6's shape: the mode-2 call unguarded, so one refusal leaves the
    # function entirely and the mode-1 abandon loop never runs.
    ("refund-refusal-kills-the-sweep", MAIN,
     '        n = await _refund_or_skip(sid, "refund_abandoned")\n'
     '        if n is None:\n'
     '            continue\n'
     '        await db.commit()\n'
     '        if n:\n'
     '            changed += 1\n'
     '            print(f"[SERIES] refunded {n} bet(s) on stalled series {sid} (series stays resumable)")\n',
     '        n = await _refund_series_bets(db, sid, "refund_abandoned")\n'
     '        await db.commit()\n'
     '        if n:\n'
     '            changed += 1\n'
     '            print(f"[SERIES] refunded {n} bet(s) on stalled series {sid} (series stays resumable)")\n',
     '        # (inert: a comment at the same site)\n'
     '        n = await _refund_or_skip(sid, "refund_abandoned")\n'
     '        if n is None:\n'
     '            continue\n'
     '        await db.commit()\n'
     '        if n:\n'
     '            changed += 1\n'
     '            print(f"[SERIES] refunded {n} bet(s) on stalled series {sid} (series stays resumable)")\n',
     "test_pg_one_unpayable_series_does_not_stop_the_stale_series_sweep"),

    # The change the deleted comment would have licensed.
    ("wager-lock-dropped-as-redundant", MAIN,
     '        "  FROM ffa_lobbies WHERE id = :lid FOR NO KEY UPDATE"\n'
     '    ), {"lid": lid})).mappings().first()\n',
     '        "  FROM ffa_lobbies WHERE id = :lid"\n'
     '    ), {"lid": lid})).mappings().first()\n',
     '        "  FROM ffa_lobbies WHERE id = :lid FOR NO KEY UPDATE"\n'
     '        # (inert: a comment at the same site)\n'
     '    ), {"lid": lid})).mappings().first()\n',
     "test_a_wager_cannot_be_inserted_while_its_game_settles"),

    ("relock-leaves-a-poisoned-transaction", MAIN,
     '    except Exception as _relock_ex:\n'
     '        try:\n'
     '            await db.rollback()\n'
     '        except Exception:\n'
     '            pass\n'
     '        # ...and now ASK AGAIN, on the session the rollback just cleared. The\n',
     '    except Exception as _relock_ex:\n'
     '        # ...and now ASK AGAIN, on the session the rollback just cleared. The\n',
     '    except Exception as _relock_ex:\n'
     '        # (inert: a comment at the same site)\n'
     '        try:\n'
     '            await db.rollback()\n'
     '        except Exception:\n'
     '            pass\n'
     '        # ...and now ASK AGAIN, on the session the rollback just cleared. The\n',
     "test_the_relock_leaves_a_transaction_the_next_read_can_run_in"),

    # This one mutates the EVIDENCE, because the rule it guards is about the
    # evidence: put the failure count back to a grep over a gitignored log.
    # The forbidden path is ASSEMBLED rather than written out, because this
    # file is itself under evidence/ and the rule applies to it too -- a
    # runner that had to carry the string it forbids would either exempt
    # itself from its own control or redden it.
    ("evidence-cites-a-gitignored-path", SUITES,
     "Neither summary line above carries a `failed` term.",
     "ai-" + "collab/r7-suite-optout.log:0 and ai-" + "collab/r7-suite-dsn.log:0.",
     "Neither summary line quoted above carries a `failed` term.",
     "test_the_committed_evidence_re_derives_its_own_numbers"),

    # The skip the three prune loops gained is only safe because the helper
    # ENDS the transaction before returning its sentinel. Drop the rollback
    # and the loop takes the next series still holding this one's locks --
    # which is the hold-and-wait shape the per-item commit exists to remove,
    # and under asyncpg it is also a poisoned transaction (#235). The test
    # that credits the skip is the test that asserts the rollback, so this is
    # what stops that credit becoming a hole in the older property.
    ("refusal-skips-without-ending-the-transaction", MAIN,
     '        except StakeRefundRefused as _refusal:\n'
     '            try:\n'
     '                await db.rollback()\n'
     '            except Exception:\n'
     '                pass\n'
     '            print(f"[SERIES] stale-series sweep could not refund {_sid} and "\n',
     '        except StakeRefundRefused as _refusal:\n'
     '            print(f"[SERIES] stale-series sweep could not refund {_sid} and "\n',
     '        except StakeRefundRefused as _refusal:\n'
     '            # (inert: a comment at the same site)\n'
     '            try:\n'
     '                await db.rollback()\n'
     '            except Exception:\n'
     '                pass\n'
     '            print(f"[SERIES] stale-series sweep could not refund {_sid} and "\n',
     (os.path.join("tests", "test_report_disconnect_durability.py"),
      "test_the_prune_batch_commits_per_series_so_it_cannot_hold_the_chain")),

    # -- round 8 ----------------------------------------------------------
    # The transaction SCOPE, as a mutation rather than as a description. The
    # test has asserted it structurally since round 4 and the mutation had
    # never been run, so "it reds on a commit between the lock and the slot"
    # was a sentence about a run nobody could check. The INERT twin is a
    # COMMENT at the same site, which is the negative control that matters
    # here: the test measures comment-stripped source, so a comment must leave
    # it green (#441).
    ("commit-between", MAIN,
     '    lobby, _expected_game = await _ffa_lock_lobby_slot(db, lobby_uuid)\n'
     '    if lobby is None:\n',
     '    lobby, _expected_game = await _ffa_lock_lobby_slot(db, lobby_uuid)\n'
     '    await db.commit()\n'
     '    if lobby is None:\n',
     '    lobby, _expected_game = await _ffa_lock_lobby_slot(db, lobby_uuid)\n'
     '    # (inert: a comment at the same site)\n'
     '    if lobby is None:\n',
     "test_the_lock_the_derivation_and_the_increment_are_one_transaction"),

    # The LIVE contention control. settlement-takes-for-update above proves the
    # mode is the weaker one; this proves the row lock is there at all, on two
    # real connections, and round 7 carried it only as "(hand-run)" prose.
    ("settlement-lock-removed-live", MAIN,
     '_FFA_LOBBY_LOCK_SQL = "SELECT * FROM ffa_lobbies WHERE id = :lid FOR NO KEY UPDATE"\n',
     '_FFA_LOBBY_LOCK_SQL = "SELECT * FROM ffa_lobbies WHERE id = :lid"\n',
     '_FFA_LOBBY_LOCK_SQL = ("SELECT * FROM ffa_lobbies WHERE id = :lid FOR NO KEY UPDATE")\n',
     "test_pg_two_reports_for_one_lobby_cannot_settle_the_same_number"),

    # A refusal raised after a capture answers from the copy read before it.
    ("refusal-after-capture-reuses-stale-progress", MAIN,
     '    fresh = await _ffa_progress_relocked(db, lobby_uuid)\n',
     '    fresh = dict(progress or {})\n',
     '    # (inert: a comment at the same site)\n'
     '    fresh = await _ffa_progress_relocked(db, lobby_uuid)\n',
     "test_pg_a_refusal_raised_after_a_capture_reads_the_lobby_again"),

    # The number every refusal advertises stops being the one that settles, so
    # a room realigning onto it is refused again for naming a game the sitting
    # has already passed.
    ("advertised-number-is-not-the-settling-one", MAIN,
     '    out = {"games_played": gp, "expected_game": gp + 1}\n',
     '    out = {"games_played": gp, "expected_game": gp}\n',
     '    out = {"games_played": gp, "expected_game": (gp + 1)}\n',
     "test_pg_a_realigned_resubmission_is_echoed_and_never_settled_twice"),

    # This one mutates a SHIPPED file, because the rule it guards is about
    # shipped files. The forbidden path is ASSEMBLED for the same reason the
    # evidence control assembles it: this runner is itself under evidence/.
    # Anchored on the room-rules header in main.py, one of the lines the
    # sweep cleaned, and the mutant restores the citation that header carried
    # before the sweep.
    ("production-cites-a-gitignored-path", MAIN,
     '# ── Room rules (Sept 10 batch; schema and shape decisions: migration 306) ───\n',
     '# ── Room rules (Sept 10 batch, '
     + "ai-" + 'collab/sept10-batch/01-room-rules.md) ──────\n',
     '# ── Room rules  (Sept 10 batch; schema and shape decisions: migration 306) ───\n',
     "test_no_production_file_cites_the_gitignored_scratch"),

    # B3's other clause: a re-read that failed once answers stale-low instead
    # of asking again on the session its own rollback just cleared.
    ("relock-gives-up-after-one-attempt", MAIN,
     '        try:\n'
     '            _lobby, _expected = await _ffa_lock_lobby_slot(db, lobby_uuid)\n'
     '        except Exception as _retry_ex:\n',
     '        try:\n'
     '            raise _relock_ex\n'
     '        except Exception as _retry_ex:\n',
     '        try:\n'
     '            # (inert: a comment at the same site)\n'
     '            _lobby, _expected = await _ffa_lock_lobby_slot(db, lobby_uuid)\n'
     '        except Exception as _retry_ex:\n',
     "test_pg_the_relock_retries_once_and_answers_from_the_lobby_not_the_snapshot"),

    # The evidence check's result pattern learned a new artifact type this
    # round -- the re-pin states its result as `rows rewritten now : 0` -- and
    # a widened pattern is a check that got EASIER to satisfy, which is the
    # direction ending in a check that cannot fail (#342). So the widening
    # brings a control, and this control mutates a TEST file because the rule
    # it guards lives there rather than in the server.
    #
    # Dropping the token reds the check TWICE OVER, and which assertion fires
    # first is worth stating because it changes over the life of the file. The
    # directory sweep fires today: r8-repin.txt carries `rows rewritten now`
    # and no other recognised token, so losing that token leaves the report
    # looking resultless, and the observed red is
    # `r8-repin.txt states no executed result`. That reason is TEMPORARY -- the
    # re-pin log later gains the closing check's own pytest summary, and from
    # then on the sweep is satisfied by `N passed` no matter what the pattern
    # forgets. What survives that is the both-directions block inside the
    # check, which asserts the pattern matches one line of each artifact type
    # and does not match prose. It reds from an assertion ABOUT the pattern
    # rather than from whatever evidence/ happens to contain, so this control
    # keeps meaning what it says after the directory's contents move on.
    ("evidence-result-pattern-forgets-the-repin", TESTS,
     '    result_token = re.compile(\n'
     r'        r"\d+ passed|second run|rows identical|RED:|rows rewritten now")'
     '\n',
     '    result_token = re.compile(\n'
     r'        r"\d+ passed|second run|rows identical|RED:")'
     '\n',
     # Inert: the same alternation, reordered. Every use is a boolean
     # `search`, so which branch matches first cannot be observed.
     '    result_token = re.compile(\n'
     r'        r"rows rewritten now|\d+ passed|second run|rows identical|RED:")'
     '\n',
     "test_the_committed_evidence_re_derives_its_own_numbers"),

    # The check added beside that one derives the control set from THIS
    # file instead of restating it, and a derived check is still only
    # worth what it reds on. Misspell the inventory's entry for the
    # control above by one letter -- the drift that actually happens --
    # and the derived check must notice that a control the runner carries
    # is named nowhere. The inert twin rewords the same entry's
    # DESCRIPTION and leaves its name alone.
    ("control-list-drifts-from-the-inventory", TESTS,
     '  evidence-result-pattern-forgets-the-repin (r8)  the result pattern in\n',
     '  evidence-result-pattern-forgets-the-repln (r8)  the result pattern in\n',
     '  evidence-result-pattern-forgets-the-repin (r8)  the result-pattern in\n',
     "test_every_mutation_control_the_runner_carries_is_named_and_paired"),

    # ── round 9 ──────────────────────────────────────────────────────────
    # The realignment section keyed the NEXT physical game and the parked one
    # at the same advertised number. What keeps that from settling one number
    # twice is the room-keyed echo comparing the BODY: drop the comparison and
    # a different physical game delivered under an already-settled key is
    # answered as that game -- settled once, and the second one silently gone.
    ("realignment-reuses-the-advertised-number", MAIN,
     '    why = await _ffa_prior_field_disagreement(db, prior, id_by_steam, report, kills_signed)\n'
     '    if why is not None:\n',
     '    why = None\n'
     '    if why is not None:\n',
     '    why = await _ffa_prior_field_disagreement(db, prior, id_by_steam, report, kills_signed)\n'
     '    # (inert: a comment at the same site)\n'
     '    if why is not None:\n',
     "test_pg_a_realigned_sitting_issues_each_game_its_own_number"),

    # The L1 rule was stated over every file we SHIP and read three
    # hand-written globs. This mutates the one shipped file that was outside
    # all three -- and it is the control for the SET rather than for the line,
    # because the identical edit was green for the whole of round 8.
    ("shipped-file-outside-the-swept-set", DOCKERFILE_BOT,
     '# is parse-broken against current YouTube page variants, reproduced against a\n',
     '# is parse-broken against current YouTube page variants (evidence in '
     + "ai-" + 'collab/streaming-design-addendum-chat.md), reproduced against a\n',
     '# is parse-broken against current YouTube page variants,  reproduced against a\n',
     "test_no_production_file_cites_the_gitignored_scratch"),

    # A log line that announces a repair on a path whose transaction is never
    # committed. The test it reds asserts the row as well as the wording, so
    # this control cannot be satisfied by a phrase alone.
    ("catch-up-log-claims-a-persisted-repair", MAIN,
     '        print(f"[FFA] lobby {lobby_uuid} counter is behind its own rows: "\n'
     '              f"games_played {counted}, highest recorded game {held}; this "\n'
     '              f"answer derives the sitting\'s next slot as {held + 1}. The "\n'
     '              f"correction is issued in this request\'s transaction and stands "\n'
     '              f"only if that request commits")\n',
     '        print(f"[FFA] lobby {lobby_uuid} counter was behind its own rows: "\n'
     '              f"games_played {counted} -> {held} (highest recorded game). The "\n'
     '              f"sitting resumes at {held + 1}")\n',
     '        print(f"[FFA] lobby {lobby_uuid} counter is behind its own rows: "\n'
     '              f"games_played {counted}, highest recorded game {held}; this "\n'
     '              f"answer derives the sitting\'s next slot as {held + 1}.  The "\n'
     '              f"correction is issued in this request\'s transaction and stands "\n'
     '              f"only if that request commits")\n',
     "test_pg_a_catch_up_on_a_refusing_path_logs_a_claim_its_transaction_can_keep"),
    # ── round 10 ─────────────────────────────────────────────────────────
    # The r6 MEDIUM, at the site the method changed. A capture ends this
    # request's transaction, so the counters the caller still holds predate
    # it; when the fresh read cannot be made the answer is now a 503 carrying
    # NO progress fields. This mutant puts the caller's copy back -- literally
    # the restoration of the pre-capture snapshot -- by catching the refusal
    # here, which is the only place the copy is still in scope.
    ("capture-refusal-restores-the-snapshot", MAIN,
     '    fresh = await _ffa_progress_relocked(db, lobby_uuid)\n',
     '    try:\n'
     '        fresh = await _ffa_progress_relocked(db, lobby_uuid)\n'
     '    except FfaReportRefusal:\n'
     '        fresh = dict(progress or {})\n',
     '    # (inert: a comment at the same site)\n'
     '    fresh = await _ffa_progress_relocked(db, lobby_uuid)\n',
     "test_a_refusal_whose_lobby_cannot_be_read_carries_no_progress_at_all"),

    # Both exhausted arms of the re-read, one control each, because they are
    # two reachable states and a control on one says nothing about the other.
    # The mutant is the invention the old docstring named and refused --
    # answering `games_played = 0` rather than admitting there was nothing to
    # read.
    ("double-failure-invents-a-progress", MAIN,
     '            print(f"[FFA-REPORT] could not re-read lobby {lobby_uuid} progress "\n'
     '                  f"after a rollback, twice; answering 503 with no progress "\n'
     '                  f"fields: {_relock_ex} / then {_retry_ex}")\n'
     '            raise FfaReportRefusal(\n'
     '                503, "Could not read this lobby\'s progress - retry this "\n'
     '                     "report unchanged", {})\n',
     '            print(f"[FFA-REPORT] could not re-read lobby {lobby_uuid} progress "\n'
     '                  f"after a rollback, twice; answering 503 with no progress "\n'
     '                  f"fields: {_relock_ex} / then {_retry_ex}")\n'
     '            return _ffa_progress(0)\n',
     '            # (inert: a comment at the same site)\n'
     '            print(f"[FFA-REPORT] could not re-read lobby {lobby_uuid} progress "\n'
     '                  f"after a rollback, twice; answering 503 with no progress "\n'
     '                  f"fields: {_relock_ex} / then {_retry_ex}")\n'
     '            raise FfaReportRefusal(\n'
     '                503, "Could not read this lobby\'s progress - retry this "\n'
     '                     "report unchanged", {})\n',
     "test_pg_an_exhausted_progress_read_answers_503_with_no_progress_fields"),

    ("vanished-lobby-invents-a-progress", MAIN,
     '    if _lobby is None:\n'
     '        print(f"[FFA-REPORT] lobby {lobby_uuid} has no row left to read progress "\n'
     '              f"from; answering 503 with no progress fields")\n'
     '        raise FfaReportRefusal(\n'
     '            503, "This lobby\'s progress is unavailable - retry this report "\n'
     '                 "unchanged", {})\n',
     '    if _lobby is None:\n'
     '        return _ffa_progress(0)\n',
     '    if _lobby is None:\n'
     '        # (inert: a comment at the same site)\n'
     '        print(f"[FFA-REPORT] lobby {lobby_uuid} has no row left to read progress "\n'
     '              f"from; answering 503 with no progress fields")\n'
     '        raise FfaReportRefusal(\n'
     '            503, "This lobby\'s progress is unavailable - retry this report "\n'
     '                 "unchanged", {})\n',
     "test_pg_an_exhausted_progress_read_answers_503_with_no_progress_fields"),

    # The server is the sole allocator of the game number, so the join-time
    # payload advertises the number it accepts NEXT rather than leaving the
    # seat to add one to the settled count. The mutant is the shape that was
    # there for five rounds: the settled count alone.
    ("join-payload-omits-the-advertised-number", MAIN,
     '        **_ffa_progress(int(lobby["games_played"] or 0)),\n',
     '        "games_played": int(lobby["games_played"] or 0),\n',
     '        # (inert: a comment at the same site)\n'
     '        **_ffa_progress(int(lobby["games_played"] or 0)),\n',
     "test_the_lobby_state_advertises_the_sittings_settled_count"),

    # ...and the acceptance names the game it settled, so a client never has
    # to infer "settled" from the absence of a refusal. The inert twin is the
    # call REFLOWED, which is the negative control that matters here: the
    # assertion is whitespace-flattened precisely so it measures the call and
    # not the line's shape (#441).
    ("acceptance-does-not-name-its-settled-game", MAIN,
     '        **_ffa_progress(_game_number, settled_game=_game_number))\n',
     '        **_ffa_progress(_game_number))\n',
     '        **_ffa_progress(_game_number,\n'
     '                        settled_game=_game_number))\n',
     "test_every_report_answer_carries_the_lobbys_progress"),

    # Two controls on the EVIDENCE, because the two rules added this round are
    # about the evidence. The first drops one half's command line, so a
    # results block is left with no record of what produced it; its inert twin
    # is the same line with a space added, which is still a command line.
    ("evidence-results-without-an-invocation", SUITES,
     "command   env -u FFA_TEST_PG_DSN FFA_TEST_PG_OPTOUT=1 python -m pytest tests/ -q -p no:cacheprovider\n",
     "the command for this half is not recorded\n",
     "command   env -u FFA_TEST_PG_DSN  FFA_TEST_PG_OPTOUT=1 python -m pytest tests/ -q -p no:cacheprovider\n",
     "test_the_committed_evidence_re_derives_its_own_numbers"),

    # ...and the second puts a number into the report's prose that its run
    # never printed, which is the round-9 finding itself. The number is one no
    # run here can produce, so this control cannot be satisfied by coincidence.
    # Its anchor is DERIVED -- see `_underived_number_edit` for the round-13
    # rewording that retired the hand-quoted one.
    ("suites-report-carries-an-underived-number", SUITES,
     _NUM_ANCHOR, _NUM_MUTANT, _NUM_INERT,
     "test_the_committed_evidence_is_assembled_from_its_run_stdout"),

    # H1, at the site that decides what a behind seat is told. The server is
    # the sole allocator, so an answer has to name the number it accepts NEXT
    # and a settled number is by definition not that. The mutant makes the
    # answer advertise the number it has just reported as settled: a seat
    # deriving its key from the last advertisement then keys every later
    # report at a number that is already taken, is refused for the same reason
    # every time, and never files again. The inert twin is a comment at the
    # same site, so what reds is the assignment and not the edit.
    ("refusal-advertises-the-number-it-just-settled", MAIN,
     '    if gno is not None and named is not None and int(gno) == int(named):\n'
     '        out["settled_game"] = int(gno)\n',
     '    if gno is not None and named is not None and int(gno) == int(named):\n'
     '        out["settled_game"] = int(gno)\n'
     '        out["expected_game"] = int(gno)\n',
     '    if gno is not None and named is not None and int(gno) == int(named):\n'
     '        # (inert: a comment at the same site)\n'
     '        out["settled_game"] = int(gno)\n',
     "test_pg_a_seat_that_missed_an_update_recovers_in_one_submission"),

    # ── round 11 ─────────────────────────────────────────────────────────
    # All four are at the level the r10 lens found: the instruments and the
    # documents, rather than the endpoint. Each mutant is the shape that was
    # actually there, put back.
    #
    # The scope of the invocation rule was derived from the reports that had
    # already adopted it, so a later round that adopted none moved the scope
    # with it and was checked by nothing. The mutant restores exactly that
    # derivation; the fabricated directory in the rule's own self-test is what
    # reds, because a directory that satisfies both readings cannot tell them
    # apart (#391: the control has to be about the RULE).
    ("evidence-scope-keys-on-the-opt-in-set", EVIDENCE_RULES,
     '    latest = newest_round(reports)\n',
     '    latest = newest_round([n for n in reports\n'
     '                           if STDOUT_HEADER.search(reports[n])])\n',
     '    # (inert: a comment at the same site)\n'
     '    latest = newest_round(reports)\n',
     "test_the_committed_evidence_re_derives_its_own_numbers"),

    # ...and the escape one spelling over, swept with it: the round is taken
    # from the file NAME so that no report can opt out, which makes a name
    # carrying no round an opt-out by unparseability. The mutant drops the
    # clause that refuses one; the rule's fabricated directory is again what
    # reds, and the inert twin is a comment at the same site.
    ("scope-lets-a-report-belong-to-no-round", EVIDENCE_RULES,
     '        if round_of(name) is None:\n'
     '            bad.append((name, "carries no round number in its name, so no "\n'
     '                              "round\'s scope reaches it"))\n'
     '            continue\n',
     '        if round_of(name) is None:\n'
     '            continue\n',
     '        # (inert: a comment at the same site)\n'
     '        if round_of(name) is None:\n'
     '            bad.append((name, "carries no round number in its name, so no "\n'
     '                              "round\'s scope reaches it"))\n'
     '            continue\n',
     "test_the_committed_evidence_re_derives_its_own_numbers"),

    # The assembler's own check count, written as a constant beside a body
    # that runs two loops -- on the instrument that exists to refuse a number
    # a run did not produce. The inert twin is the SAME expression REFLOWED,
    # which is the negative control that matters: the test compares a number,
    # so it must not be satisfiable by a line's shape (#441).
    ("selftest-count-is-not-derived", ASSEMBLER,
     '    print("selftest: %d rule checks, all as stated" % len(checks))\n',
     '    print("selftest: %d rule checks, all as stated" % (len(TERMS) + 19))\n',
     '    print("selftest: %d rule checks, all as stated"\n'
     '          % len(checks))\n',
     "test_the_assembler_counts_the_checks_it_ran"),

    # A report crediting its own round with a control another round added.
    # The mutant is the defect reproduced on the committed report: one name
    # swapped for a name the inventory tags for an earlier round, which reds
    # in BOTH directions -- one listed and not tagged, one tagged and not
    # listed. All three strings are DERIVED from the report and the inventory
    # by _report_claim_swap above, so this control does not carry a round's
    # control names into the round after it.
    ("new-controls-list-credits-another-round", MUTATION_REPORT,
     _SWAP_ANCHOR, _SWAP_MUTANT, _SWAP_INERT,
     "test_the_new_controls_a_report_claims_are_the_ones_the_inventory_tags"),

    # The invocation rule's list of frame keys, which is itself a hand-written
    # set beside a growing one -- the sibling of finding 2, one level down.
    # The upward scan stops at the first line it does not recognise, so a key
    # the list has never been told about turns a result whose command IS above
    # it into a reported violation. This round's runner prints two new frame
    # lines, `reports` and `swap`; the mutant takes both keys back out, and
    # the rule's own fabricated frame is what reds. Its inert twin is a
    # comment at the same site.
    ("invocation-frame-drops-a-known-key", EVIDENCE_RULES,
     '    r"|^\\s*(file|cwd|python|script|dsn|started|controls|pytest|selection"\n'
     '    r"|reports|swap)\\s"\n',
     '    r"|^\\s*(file|cwd|python|script|dsn|started|controls|pytest|selection)\\s"\n',
     '    # (inert: a comment at the same site)\n'
     '    r"|^\\s*(file|cwd|python|script|dsn|started|controls|pytest|selection"\n'
     '    r"|reports|swap)\\s"\n',
     "test_the_committed_evidence_re_derives_its_own_numbers"),

    # The residual list's reach rule, with the clause that reds on a second
    # statement of the reach removed: the section is then searched for the
    # claim with every line taken out of it, so the hand-counted summary the
    # r10 lens found passes. The inert twin is a comment at the same site.
    ("residual-reach-rule-admits-a-prose-count", RESIDUAL_RULES,
     '    rest = [lines[i] for i in range(start, end)\n'
     '            if i not in exempt and not TAG.match(lines[i])]\n',
     '    rest = []\n',
     '    # (inert: a comment at the same site)\n'
     '    rest = [lines[i] for i in range(start, end)\n'
     '            if i not in exempt and not TAG.match(lines[i])]\n',
     "test_the_residual_reach_rule_holds_in_both_directions"),
    # ── round 12 ─────────────────────────────────────────────────────────
    # The capture-failure 503 back under the re-derivation, answering with it.
    # That is one response in two dispositions at once: TERMINAL by the
    # `settled_game` field the caller resolved, RETRYABLE by its status. The
    # inert twin is the same detail string reflowed across its two lines, so
    # what reds is the VALUE the arm carries and not the shape of the raise.
    ("capture-failure-503-carries-the-settled-game", MAIN,
     '    if _kept not in ("recorded", "already", "variant"):\n'
     '        raise FfaReportRefusal(503, "Could not record this report for review - "\n'
     '                                    "retry this report unchanged", {})\n',
     '    if _kept not in ("recorded", "already", "variant"):\n'
     '        raise FfaReportRefusal(503, "Could not record this report for review - "\n'
     '                                    "retry this report unchanged",\n'
     '                               await _ffa_progress_after_capture(\n'
     '                                   db, lobby_uuid, progress))\n',
     '    if _kept not in ("recorded", "already", "variant"):\n'
     '        raise FfaReportRefusal(503, "Could not record this report for "\n'
     '                                    "review - retry this report unchanged", {})\n',
     "test_the_two_503_arms_are_disjoint_on_the_answers_the_endpoint_builds"),

    # The recovery rule of the missed-update walk, re-keying instead of
    # re-signing: the parked body is filed as a SECOND entry under a new key
    # rather than the one the seat froze for that physical game. The inert
    # twin is the same statement reflowed.
    ("recovery-re-keys-the-parked-delivery", TESTS,
     '    advertised = int(refusal.progress["expected_game"])\n'
     '    entry = outbox[key]\n'
     '    entry["advertised"] = advertised\n'
     '    return entry\n',
     '    advertised = int(refusal.progress["expected_game"])\n'
     '    entry = outbox.pop(key)\n'
     '    entry["advertised"] = advertised\n'
     '    outbox["%s#r%d" % (key, advertised)] = entry\n'
     '    return entry\n',
     '    advertised = int(\n'
     '        refusal.progress["expected_game"])\n'
     '    entry = outbox[key]\n'
     '    entry["advertised"] = advertised\n'
     '    return entry\n',
     "test_pg_a_seat_that_missed_an_update_recovers_in_one_submission"),

    # A third parameter back on the relock's signature, which is what made the
    # caller's pre-rollback copy reachable from that span. The inert twin is
    # the same signature reflowed across two lines, so what reds is the
    # parameter list and not the line's shape.
    ("relock-takes-a-fallback-again", MAIN,
     'async def _ffa_progress_relocked(db: AsyncSession, lobby_uuid) -> dict:\n',
     'async def _ffa_progress_relocked(db: AsyncSession, lobby_uuid,\n'
     '                                 fallback=None) -> dict:\n',
     'async def _ffa_progress_relocked(db: AsyncSession,\n'
     '                                 lobby_uuid) -> dict:\n',
     "test_every_progress_the_endpoint_builds_comes_from_a_locked_slot"),

    # The per-producer negations back to the blanket `*.log`, which re-includes
    # any file landing in the evidence directory with that extension whether a
    # committed instrument writes it or not. The inert twin is two of the
    # patterns swapped: the same set, a different order.
    # RE-ANCHORED IN ROUND 13, because round 13 replaced the suffix wildcards
    # this used to mutate with exact names and a control that is not re-run on
    # the tree it certifies is an assertion about a different tree. The
    # MUTATION is unchanged -- the blanket `*.log` back, which re-includes
    # every file that lands in this directory -- and it now replaces two of
    # the exact names instead of two of the patterns.
    ("evidence-log-negation-admits-any-log", GITIGNORE,
     '!backend/tests/evidence/r10-suite-run.log\n'
     '!backend/tests/evidence/r10-pg-controls.log\n',
     '!backend/tests/evidence/*.log\n',
     '!backend/tests/evidence/r10-pg-controls.log\n'
     '!backend/tests/evidence/r10-suite-run.log\n',
     "test_the_evidence_log_negation_admits_only_produced_logs"),

    # A producer that stops naming the capture it is redirected into, which
    # leaves a pattern in .gitignore that nothing in this tree produces.
    #
    # THE INERT TWIN IS A DOUBLED SPACE inside the same line, and it used to
    # be that line reflowed across two. The reflow is not an inert edit here:
    # the declaration has to OPEN its line for a producer to be NAMING rather
    # than mentioning its capture, so splitting it removes the name as surely
    # as the mutant does. A twin that reds is not a twin.
    ("producer-stops-naming-its-capture", RUN_ASSEMBLY,
     'echo "capture   <repo>/backend/tests/evidence/r${ROUND}-suites-assembly-run.log"\n',
     'echo "capture   (this producer no longer names its own capture)"\n',
     'echo "capture    <repo>/backend/tests/evidence/r${ROUND}-suites-assembly-run.log"\n',
     "test_the_evidence_log_negation_admits_only_produced_logs"),

    # ── round 12, the apply pass ─────────────────────────────────────────
    # The one producer that OPENS its own capture, renaming what it writes.
    # Seven instruments here are redirected into their capture by a caller and
    # print its name; this one computes the name, opens the file and writes
    # the header from the same value. The pairing test CALLS that function, so
    # a rename it makes is a capture no pattern in .gitignore re-includes --
    # which is a round whose re-pin record cannot be committed at all. The
    # inert twin parenthesises the operand: the same value, a different shape.
    ("repin-names-a-capture-no-pattern-admits", REPIN,
     '    return "r%d-repin-run.log" % number\n',
     '    return "r%d-repin.log" % number\n',
     '    return "r%d-repin-run.log" % (number)\n',
     "test_the_evidence_log_negation_admits_only_produced_logs"),

    # A SECOND terminal exit below the re-derivation, answering exactly what
    # the single one answers. The responses are unchanged and that is the
    # point: what this reds is the SHAPE the disjointness rests on -- one exit
    # above the re-derivation carrying no progress, one below carrying it --
    # and the shape is what a later round reads when it adds an arm. The inert
    # twin builds the same detail string across two lines.
    ("terminal-arm-splits-into-two-exits", MAIN,
     '    if _kept == "variant":\n'
     '        detail = f"{detail} - a different account of this room is already on file"\n'
     '    raise FfaReportRefusal(status, detail, progress)\n',
     '    if _kept == "variant":\n'
     '        raise FfaReportRefusal(\n'
     '            status, f"{detail} - a different account of this room is "\n'
     '                    f"already on file", progress)\n'
     '    raise FfaReportRefusal(status, detail, progress)\n',
     '    if _kept == "variant":\n'
     '        detail = (f"{detail} - a different account of this room is "\n'
     '                  f"already on file")\n'
     '    raise FfaReportRefusal(status, detail, progress)\n',
     "test_the_two_503_arms_are_disjoint_on_the_answers_the_endpoint_builds"),

    # The re-keying recovery in the shape that does NOT crash on the next
    # lookup: the entry the seat holds stays reachable and a second key is
    # added beside it. Every leg of the walk then runs, and what sees it is
    # the key-set comparison rather than an incidental KeyError (#391). The
    # inert twin is a comment at the same site.
    ("recovery-mints-a-second-parked-key", TESTS,
     '    advertised = int(refusal.progress["expected_game"])\n'
     '    entry = outbox[key]\n'
     '    entry["advertised"] = advertised\n'
     '    return entry\n',
     '    advertised = int(refusal.progress["expected_game"])\n'
     '    entry = outbox[key]\n'
     '    entry["advertised"] = advertised\n'
     '    outbox["%s#r%d" % (key, advertised)] = dict(entry)\n'
     '    return entry\n',
     '    advertised = int(refusal.progress["expected_game"])\n'
     '    entry = outbox[key]\n'
     '    # (inert: a comment at the same site)\n'
     '    entry["advertised"] = advertised\n'
     '    return entry\n',
     "test_pg_a_seat_that_missed_an_update_recovers_in_one_submission"),

    # ── round 13 ─────────────────────────────────────────────────────────
    # THE REDIRECT, NOT TAKEN. The contract's arm table gives a refusal
    # carrying `settled_game` one disposition -- keep the entry, re-sign it
    # ONCE at the advertised number, submit -- and this is that rule with the
    # re-sign removed: the entry keeps the number it was just refused for and
    # goes back out unchanged. What reds is the acceptance leg, because the
    # endpoint refuses the stale number again. The inert twin is the same
    # assignment with a doubled space, so what reds is the VALUE written into
    # the body and not the shape of the line.
    ("recovery-resubmits-the-stale-number", TESTS,
     '    advertised = int(refusal.progress["expected_game"])\n'
     '    entry = outbox[key]\n'
     '    entry["advertised"] = advertised\n'
     '    return entry\n',
     '    advertised = int(refusal.progress["expected_game"])\n'
     '    entry = outbox[key]\n'
     '    entry["advertised"] = entry["advertised"] or advertised\n'
     '    return entry\n',
     '    advertised = int(refusal.progress["expected_game"])\n'
     '    entry = outbox[key]\n'
     '    entry["advertised"] =  advertised\n'
     '    return entry\n',
     "test_pg_a_seat_that_missed_an_update_recovers_in_one_submission"),

    # THE BOUND on a redirect was this round's control at that site, and ROUND
    # 14 RETIRED IT: the ruling removes the redirect itself, so a bound on how
    # often it may be taken is a rule the tree no longer carries, and a control
    # that cannot be re-run on the tree it certifies is an assertion about a
    # different tree. Its site is held by `terminal-arm-redirects-the-refused
    # -entry` below, which reds on the redirect happening at all. The inventory
    # entry stays, tagged RETIRED in place, because the evidence of rounds 13
    # and 14 names it.

    # ONE EXACT NAME back to the producer-suffix wildcard it replaced. That
    # pattern is narrower than `*.log` and still admits every file shaped like
    # a capture, under a round nothing here has run -- which is the class the
    # lens raised. The inert twin swaps two of the exact names: the same set,
    # a different order, so what reds is what the block ADMITS.
    ("evidence-log-negation-takes-a-suffix-wildcard", GITIGNORE,
     '!backend/tests/evidence/r13-suite-run.log\n'
     '!backend/tests/evidence/r13-pg-controls.log\n',
     '!backend/tests/evidence/*-suite-run.log\n'
     '!backend/tests/evidence/r13-pg-controls.log\n',
     '!backend/tests/evidence/r13-pg-controls.log\n'
     '!backend/tests/evidence/r13-suite-run.log\n',
     "test_the_evidence_log_negation_admits_only_produced_logs"),

    # A LABEL THAT DISAGREES WITH THE TWIN IT NAMES, which is the lens LOW
    # restored: the entry said "the same statement reflowed" and the runner
    # holds a comment. The executed RED and GREEN are unaffected, which is why
    # nothing else could see it. The inert twin is a doubled space in the same
    # sentence, so what reds is the LABEL and not the spacing.
    ("inventory-mislabels-an-inert-twin", TESTS,
     '                           set is what sees it. Its inert twin is a comment\n'
     '                           at the same site.\n',
     '                           set is what sees it. Its inert twin is the same\n'
     '                           statement reflowed.\n',
     '                           set is what sees it.  Its inert twin is a comment\n'
     '                           at the same site.\n',
     "test_every_inert_twin_is_labelled_as_the_kind_the_runner_holds"),

    # THE TRAILER TYPED AGAIN. `derive_trailer` reads the form the branch's
    # most recent commits carry; this makes it return a constant instead, so
    # a sitting commits under whatever the last one wrote down -- the R4-17
    # defect, which had already gone stale once by the time the lens read it.
    # The inert twin is a comment at the same site.
    ("repin-types-its-commit-trailer", REPIN,
     '    if agreeing < TRAILER_AGREE:\n'
     '        return None, ("only %d of the most recent commits carries a trailer, "\n'
     '                      "and %d have to agree" % (agreeing, TRAILER_AGREE))\n'
     '    return newest, None\n',
     '    if agreeing < TRAILER_AGREE:\n'
     '        return None, ("only %d of the most recent commits carries a trailer, "\n'
     '                      "and %d have to agree" % (agreeing, TRAILER_AGREE))\n'
     '    return "Co-Authored-By: An Earlier Sitting <nobody@example.invalid>", None\n',
     '    if agreeing < TRAILER_AGREE:\n'
     '        return None, ("only %d of the most recent commits carries a trailer, "\n'
     '                      "and %d have to agree" % (agreeing, TRAILER_AGREE))\n'
     '    # (inert: a comment at the same site)\n'
     '    return newest, None\n',
     "test_the_repin_trailer_is_derived_and_the_sweep_exempts_only_it"),

    # ── round 14 ─────────────────────────────────────────────────────────
    # THE REDIRECT, RESTORED. Rounds 12 and 13 answered a refusal carrying
    # `settled_game` by re-signing that entry at the advertised number, and the
    # ruling removes it: the server cannot tell a behind seat's LATER physical
    # game from a CONFLICTING second account of the game already settled at
    # that number, so re-keying such a delivery at the free number settles the
    # conflicting account as a game of its own. This makes the rule return
    # `redirect` again; the conflicting-account walk then re-signs and
    # resubmits, the endpoint settles it, and what reds is the SECOND row for
    # one physical game -- a second rating and a second payout. The inert twin
    # is a comment at the same site.
    ("terminal-arm-redirects-the-refused-entry", TESTS,
     '    entry["refusals"] += 1\n'
     '    advertised = refusal.progress.get("expected_game")\n'
     '    return "terminal", None if advertised is None else int(advertised)\n',
     '    entry["refusals"] += 1\n'
     '    advertised = refusal.progress.get("expected_game")\n'
     '    if refusal.progress.get("settled_game") is not None:\n'
     '        return "redirect", int(advertised)\n'
     '    return "terminal", None if advertised is None else int(advertised)\n',
     '    entry["refusals"] += 1\n'
     '    advertised = refusal.progress.get("expected_game")\n'
     '    # (inert: a comment at the same site)\n'
     '    return "terminal", None if advertised is None else int(advertised)\n',
     "test_pg_a_conflicting_account_of_the_settled_game_is_dropped_and_kept"),

    # THE DROP, ANNOUNCED AND NOT TAKEN. The terminal disposition is only worth
    # what the outbox does with it: a helper that reports the entry it removed
    # while leaving it in place reads identically at every call site and leaves
    # a delivery the server has already refused sitting in the queue. What reds
    # is the outbox size, compared with the set captured before the drop. The
    # inert twin is a comment at the same site.
    ("terminal-walk-keeps-the-dropped-entry", TESTS,
     '    was delivered, and that it was never delivered again."""\n'
     '    return outbox.pop(key)\n',
     '    was delivered, and that it was never delivered again."""\n'
     '    return dict(outbox[key])\n',
     '    was delivered, and that it was never delivered again."""\n'
     '    # (inert: a comment at the same site)\n'
     '    return outbox.pop(key)\n',
     "test_pg_a_seat_that_missed_an_update_recovers_in_one_submission"),

    # A TERMINAL ANSWER OVER NOTHING KEPT. The drop is conservative only
    # because the payload survives it: the server quarantines the whole body
    # before it refuses, so a real game refused on this arm can be accepted by
    # hand. Raise the same refusal directly and the ANSWER is byte-identical
    # while nothing is kept -- the July-30 class, one arm down. What reds is
    # the quarantine record the walk reads back, not the response. The inert
    # twin is a comment at the same site.
    ("refusal-keeps-nothing-for-review", MAIN,
     '        await _ffa_record_and_refuse(\n'
     '            db, report=report, lobby_uuid=lobby_uuid, id_by_steam=id_by_steam,\n'
     '            reason="ffa_game_contradiction", why=why,\n'
     '            detail="This game is already recorded",\n'
     '            progress=_ffa_with_settled(progress, prior, _named))\n',
     '        raise FfaReportRefusal(\n'
     '            409, "This game is already recorded",\n'
     '            _ffa_with_settled(progress, prior, _named))\n',
     '        # (inert: a comment at the same site)\n'
     '        await _ffa_record_and_refuse(\n'
     '            db, report=report, lobby_uuid=lobby_uuid, id_by_steam=id_by_steam,\n'
     '            reason="ffa_game_contradiction", why=why,\n'
     '            detail="This game is already recorded",\n'
     '            progress=_ffa_with_settled(progress, prior, _named))\n',
     "test_pg_a_conflicting_account_of_the_settled_game_is_dropped_and_kept"),
]


# Each file's own line ending, recorded when it is first read. Files in this
# tree are not uniform -- main.py is CRLF, the tests and the evidence are LF --
# and a restore that rewrote one in the other convention would change every
# line of it. The md5 comparison at the end would then report the file as
# CHANGED and be right, so the newline has to be preserved rather than chosen.
_NEWLINE = {}


def read(path):
    # Universal newlines, so the anchors above are written with plain \n
    # whatever the file uses on disk.
    with io.open(path, "rb") as fh:
        raw = fh.read()
    _NEWLINE[path] = "\r\n" if b"\r\n" in raw else "\n"
    with io.open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8",
                 newline=_NEWLINE.get(path, "\n")) as fh:
        fh.write(text)


def md5(path):
    with io.open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


ANCHOR_TESTS = os.path.join("tests", "test_ffa_game_number_anchor.py")


def split_test(test):
    """A control names its test either as a bare name in the anchor file, or
    as a (file, name) pair. The pair exists because one r7 property is pinned
    where the sweep's shape is owned -- test_report_disconnect_durability.py --
    and a runner that could only reach one file would have left that control
    unrunnable, which is the property going unpinned by an accident of
    tooling."""
    if isinstance(test, tuple):
        return test
    return ANCHOR_TESTS, test


def rel(path):
    """A path relative to the repository root, POSIX-style.

    Everything this log prints goes through here. A committed report that names
    an absolute path names THIS machine's checkout, which is both unfollowable
    from a clone and a local path in a tracked file."""
    try:
        out = os.path.relpath(path, ROOT)
    except ValueError:
        return "(outside the repository)"
    if out.startswith(".."):
        return "(outside the repository)"
    out = out.replace(os.sep, "/")
    return "<repo>" if out == "." else "<repo>/" + out


def redacted(dsn):
    """scheme://user@host:port/db with every part a placeholder.

    The connection is an input to the run and belongs in the log; the values
    are this seat's and do not."""
    if not dsn:
        return "(unset)"
    scheme = dsn.split("://", 1)[0] if "://" in dsn else "postgresql+asyncpg"
    return scheme + "://<user>@<host>:<port>/<db>"


def pytest_argv(test_file, name):
    return [sys.executable, "-m", "pytest", test_file,
            "-q", "--tb=line", "-p", "no:cacheprovider", "-k", name]


def shown(argv):
    """The same argv as a command line, with the interpreter as `python` and
    the -k expression quoted, so it can be pasted rather than reconstructed."""
    parts = ["python"]
    for a in argv[1:]:
        parts.append('"%s"' % a if " " in a or " or " in a else a)
    return " ".join(parts)


def run_test(test):
    test_file, name = split_test(test)
    env = dict(os.environ)
    if DSN:
        env["FFA_TEST_PG_DSN"] = DSN
    proc = subprocess.run(
        pytest_argv(test_file, name),
        cwd=BACKEND, env=env, capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    red = [ln.strip() for ln in out.splitlines()
           if ln.strip().startswith("E ") or ln.strip().startswith("E\t")]
    ran = [ln.strip() for ln in out.splitlines()
           if ("passed" in ln or "failed" in ln) and "deselected" in ln]
    return proc.returncode, red, (ran[-1] if ran else "(no selection line)"), out


def main():
    if not DSN:
        print("REFUSED: FFA_TEST_PG_DSN is unset, so the PostgreSQL-gated "
              "controls would be skips rather than runs.")
        return 2
    # The two derived targets, checked before anything is read: a None here
    # would surface as a confusing path error in the middle of the anchor
    # pre-check rather than as the one fact that is wrong.
    for label, path in (("suites", SUITES),
                        ("mutation-controls", MUTATION_REPORT)):
        if path is None or not os.path.isfile(path):
            print("REFUSED: no %s report to mutate. The suite pair and the "
                  "previous round's report have to be in this directory "
                  "before the runner starts." % label)
            return 2
    # ...and the swap this runner derives rather than holds, for the same
    # reason: "anchor resolves 0 times" names the symptom, and the fact that
    # is wrong is which report or which inventory tag is missing.
    if _SWAP_WHY is not None:
        print("REFUSED: the new-controls control has no swap to make -- %s"
              % _SWAP_WHY)
        return 2
    if _NUM_WHY is not None:
        print("REFUSED: the underived-number control has nowhere to put its "
              "figure -- %s" % _NUM_WHY)
        return 2

    originals = {}
    for _, path, _, _, _, _ in CONTROLS:
        originals.setdefault(path, read(path))
    before = {p: md5(p) for p in originals}

    # Anchor pre-check: every anchor, every mutant target, exactly once.
    problems = []
    for name, path, anchor, mutant, inert, _test in CONTROLS:
        if originals[path].count(anchor) != 1:
            problems.append("%s: anchor resolves %d times"
                            % (name, originals[path].count(anchor)))
        if anchor == mutant or anchor == inert:
            problems.append("%s: an edit that changes nothing" % name)
    if problems:
        print("REFUSED before running anything:")
        for p in problems:
            print("  " + p)
        return 2
    print("anchor pre-check: %d controls, every anchor resolves exactly once"
          % len(CONTROLS))

    # THE INVOCATION, immediately above the results it produced. Round 7's log
    # printed the results alone, so the set that produced them could not be
    # told from any other set.
    argv = list(sys.argv)
    argv[0] = rel(os.path.abspath(argv[0]))
    print("")
    print("=" * 70)
    print("INVOCATION")
    print("  command   FFA_TEST_PG_DSN=%s python %s"
          % (redacted(DSN), " ".join(argv[0:])))
    print("  cwd       %s" % rel(os.getcwd()))
    # The capture this run is redirected into, named by the producer. The
    # .gitignore negation for this directory admits one pattern per
    # producer and is compared against the names the producers print, in
    # both directions, by
    # test_the_evidence_log_negation_admits_only_produced_logs.
    print("  capture   backend/tests/evidence/<round>-mutation-run.log")
    print("  pytest    run with cwd=%s, one invocation per half of each"
          % rel(BACKEND))
    print("            control, printed in full beside it below")
    print("  python    %s" % sys.version.split()[0])
    print("  started   %s UTC"
          % datetime.datetime.now(datetime.timezone.utc)
                    .strftime("%Y-%m-%d %H:%M:%S"))
    print("  controls  %d, each RED under its mutation and GREEN under an "
          "inert edit" % len(CONTROLS))
    # The two targets this runner DERIVES rather than holds as literals, named
    # here so the log says which files the evidence-level controls ran against
    # instead of leaving a reader to work out which round they belonged to.
    print("  reports   %s (suites), %s (mutation controls)"
          % (rel(SUITES), rel(MUTATION_REPORT)))
    # ...and the swap derived from that report, named here so the log records
    # which claim was taken out and which name was put in its place, rather
    # than leaving a reader to re-derive it from the two files.
    print("  swap      %s -> %s (derived)"
          % (_SWAP_ANCHOR.strip(), _SWAP_MUTANT.strip()))
    print("=" * 70)
    print("")

    failures = []
    try:
        for name, path, anchor, mutant, inert, test in CONTROLS:
            print("=" * 70)
            _tfile, _tname = split_test(test)
            print("CONTROL %s -> %s%s"
                  % (name, _tname,
                     "" if _tfile == ANCHOR_TESTS
                     else "  [%s]" % os.path.basename(_tfile)))
            print("  file     %s" % rel(path))
            print("  command  %s" % shown(pytest_argv(_tfile, _tname)))
            sys.stdout.flush()
            write(path, originals[path].replace(anchor, mutant))
            rc, red, ran, out = run_test(test)
            print("  mutant   rc=%d  %s" % (rc, ran))
            for ln in red[:4]:
                print("    RED: " + ln)
            if rc == 0:
                failures.append("%s: the MUTANT left the test green" % name)
                print("  *** the mutant did not redden the test ***")
                print(out[-1500:])
            write(path, originals[path])

            write(path, originals[path].replace(anchor, inert))
            rc2, _red2, ran2, out2 = run_test(test)
            print("  inert    rc=%d  %s" % (rc2, ran2))
            if rc2 != 0:
                failures.append("%s: the NEGATIVE control reddened the test" % name)
                print("  *** the inert edit reddened the test ***")
                print(out2[-1500:])
            write(path, originals[path])
            sys.stdout.flush()
    finally:
        for path, text in originals.items():
            write(path, text)

    after = {p: md5(p) for p in originals}
    print("=" * 70)
    for p in originals:
        same = before[p] == after[p]
        print("restored %s: %s"
              % (os.path.basename(p), "byte-identical" if same else "CHANGED"))
        if not same:
            failures.append("%s was not restored" % p)

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  " + f)
        return 1
    print("\nall %d controls RED under mutation and GREEN under the inert edit"
          % len(CONTROLS))
    return 0


def lf_stdout():
    """Write LF, on the platform whose text streams write CRLF.

    Every committed file under this directory is LF, and this instrument's
    stdout IS a committed file -- the caller redirects it and the report is
    assembled from those exact bytes. On Windows a text stream translates
    every \\n to \\r\\n, so an instrument that does nothing here produces a
    log in the one convention the directory does not use, and the report
    built from it ends up LF above the marker and CRLF below: a MIXED file.

    That is not cosmetic. The mutation runner records a file's newline
    convention when it first reads it and writes that one convention back, so
    a mixed report comes back uniform, differs from the bytes it started as,
    and is reported as not restored -- correctly, and for a reason that has
    nothing to do with the control being run.

    Round 10 normalised its captures at the COPY step instead and recorded
    that as a deviation. Round 11 moved it into the instruments, here and in
    run-both-suites.sh, so the capture and the report are the same bytes with
    no step between them. Guarded because a stream that is not a text wrapper
    has no reconfigure and needs none."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(newline="\n")


if __name__ == "__main__":
    lf_stdout()
    sys.exit(main())
