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
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # backend/tests/evidence
BACKEND = os.path.dirname(os.path.dirname(HERE))           # backend
ROOT = os.path.dirname(BACKEND)                            # repository root
MAIN = os.path.join(BACKEND, "api", "main.py")
TESTS = os.path.join(BACKEND, "tests", "test_ffa_game_number_anchor.py")
# Shipped by the same deploy as the api (docs/deploy-reference.md maps it to
# the primary), and outside every glob round 8's shipped-file rule read.
DOCKERFILE_BOT = os.path.join(BACKEND, "Dockerfile.bot")
SUITES = os.path.join(HERE, "r9-suites.txt")
DSN = os.environ.get("FFA_TEST_PG_DSN")

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
     '    fresh = await _ffa_progress_relocked(db, lobby_uuid, progress)\n',
     '    fresh = dict(progress or {})\n',
     '    # (inert: a comment at the same site)\n'
     '    fresh = await _ffa_progress_relocked(db, lobby_uuid, progress)\n',
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
    print("  pytest    run with cwd=%s, one invocation per half of each"
          % rel(BACKEND))
    print("            control, printed in full beside it below")
    print("  python    %s" % sys.version.split()[0])
    print("  started   %s UTC"
          % datetime.datetime.now(datetime.timezone.utc)
                    .strftime("%Y-%m-%d %H:%M:%S"))
    print("  controls  %d, each RED under its mutation and GREEN under an "
          "inert edit" % len(CONTROLS))
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


if __name__ == "__main__":
    sys.exit(main())
