"""JANITOR-SELFTEST controls: plant each named mutation (or its inert twin),
run the named checks, put the file back, record the result.

The shape of rj_triage_controls.py and mutation_runner.py beside this file:
the plants are DATA below, each printed as a unified diff beside the run it
produced, so the evidence is the diff and the failing assertion, not a
summary line (#391, #342).

Per plant, refusing rather than continuing at each step:
  1. `git status --porcelain` over the worktree must be EMPTY;
  2. `git rev-parse HEAD` is printed (and compared with --expect-head);
  3. the plant's old text must occur EXACTLY ONCE in its file (#432),
     matched in that file's own line ending (the autocrlf checkout, #657);
  4. the target's sha256 is printed before the write;
  5. the edit is applied and printed as a unified diff;
  6. pytest runs the named nodes and each is read from pytest's own summary
     (-rA). A node names a test function; its parametrized cases count as
     that node. RED: at least one case FAILED and none ERRORED. GREEN: every
     case PASSED. A missing node or an ERROR is neither, and the plant FAILS;
  7. the target is restored from the bytes read in step 4, its sha256 must
     equal the one before, and the tree must be clean again;
  8. `RESULT <name>: AS REQUIRED` or `RESULT <name>: FAILED (...)`.
Restoration is in a `finally`.

The live nodes need JANITOR_SELFTEST_TEST_PG_DSN (the lane database):
without it every PostgreSQL test FAILS by design, which would read as a
kill, so the runner refuses to start when it is unset.

Usage:
    python backend/tests/janitor_selftest_controls.py --log <path>
        [--expect-head REF] [--only NAME ...] [--sites]
--sites checks step 3 for every plant (and that each planted file still
parses) and writes nothing.
Exit: 0 every plant gave its required result; 1 at least one did not;
2 the runner refused to start.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
MAIN = "backend/api/main.py"
SCHEMAS = "backend/api/schemas.py"
T = "backend/tests/test_janitor_selftest_classes.py::"

L1 = T + "test_pg_the_trading_janitors_set_local_is_executed_and_rolled_back"
L2 = T + "test_pg_the_same_statement_with_a_bad_value_or_name_fails"
L3 = T + "test_pg_dml_is_still_explained_and_never_executed"
L4 = T + "test_pg_an_unclassified_statement_is_reported_and_fails"
L5 = T + "test_pg_the_rollback_leaves_no_session_setting_behind"
L6 = T + "test_pg_transaction_words_run_without_breaking_the_run"
L7 = T + "test_pg_the_full_self_test_is_green_with_the_trading_schema"
P1 = T + "test_the_first_keyword_chooses_the_check"
P2 = T + "test_the_walker_stamps_every_statement_with_its_class"
P3 = T + "test_the_live_inventory_classifies_every_statement"
P4 = T + "test_an_unclassified_statement_never_reaches_the_server"
P5 = T + "test_an_executed_statement_is_rolled_back_before_it_passes"
L8 = T + "test_pg_the_report_names_each_statements_outcome"
P6 = T + "test_a_statement_the_run_never_reached_reads_unchecked"
L9 = T + "test_pg_the_health_word_reads_the_self_tests_verdict"
P7 = T + "test_the_health_word_is_the_recorded_verdict"
P8 = T + "test_both_health_arms_carry_the_word_and_the_schema_requires_it"
P9 = T + "test_both_arms_carry_the_build_marker_both_roles_answer_alike"
P10 = T + ("test_the_replica_branch_of_lifespan_writes_exactly_the_skipped_report_"
          "and_never_starts_the_selftest")
L10 = T + "test_pg_a_semicolon_joined_two_command_statement_fails_and_never_executes"
L11 = T + "test_pg_the_semicolon_plants_one_command_control_executes_and_rolls_back"
BUILD_SITE = "_JANITOR_SELFTEST_BUILD = 1\n"
BUILD_ARG = "                              janitor_selftest_build=_JANITOR_SELFTEST_BUILD,\n"
WORD_ARG = "                              janitor_selftest=_janitor_selftest_marker(),\n"
# The two health_check arms pass the lane's two words as one contiguous pair
# (BUILD_ARG then WORD_ARG) in both arms, so an arm-specific plant needs the line
# that FOLLOWS the pair, which differs by arm: the connected arm passes the local
# ffa_finishing_count, the degraded arm the cached _FFA_FINISHING_COUNT_LAST.
# Anchoring on the line BEFORE the pair broke at the LAND merge of main cd8d846,
# which put pc_motion there in both arms; --sites proves each needle once.
CONNECTED_NEXT = "                              ffa_finishing_count=ffa_finishing_count,\n"
CACHED_NEXT = "                              ffa_finishing_count=_FFA_FINISHING_COUNT_LAST,\n"
WORD_SITE = '    return _JANITOR_SELFTEST_WORDS.get(_janitor_selftest_report.get("status"), 0)\n'
STANDBY_UPDATE_SITE = ('            _janitor_selftest_report.update({\n'
                       '                "status": "skipped",\n'
                       '                "reason": "read replica: the janitor writers this '
                       'validates do not run here",\n'
                       '            })\n')

EXECUTE_SITE = ('        await db.execute(stmt, params)\n'
                '        verdict = "explained" if cls == "explain" else "executed_rolled_back"\n')
STMT_SITE = '        stmt = text("EXPLAIN " + s["sql"] if cls == "explain" else s["sql"])\n'
ROLLBACK_SITE = ("        try:\n"
                 "            await db.rollback()\n"
                 "        except Exception as e:\n"
                 "            rollback_error = f\"{type(e).__name__}: {e}\"\n")

PLANTS = [
    {"name": "M1-classification-removed",
     "why": "every statement goes behind EXPLAIN again, exactly as before the fix: "
            "the trading janitor's row reads failed",
     "file": MAIN, "old": STMT_SITE,
     "new": '        stmt = text("EXPLAIN " + s["sql"])\n',
     "red": [L1, L2, L5, L6, L7, P5], "green": [L3, L4, P1, P2, P3, P4]},
    {"name": "T1-inert-twin-at-the-check-site",
     "why": "the same expression, parenthesised: nothing may redden",
     "file": MAIN, "old": STMT_SITE,
     "new": '        stmt = text(("EXPLAIN " + s["sql"]) if cls == "explain" else s["sql"])\n',
     "red": [], "green": [L1, L2, L3, L5, L7, P5]},
    {"name": "M2-rollback-becomes-commit",
     "why": "the check commits instead of rolling back: a session-level SET follows "
            "the connection back into the pool",
     "file": MAIN, "old": ROLLBACK_SITE,
     "new": ROLLBACK_SITE.replace("db.rollback()", "db.commit()"),
     "red": [L1, L5, P5], "green": [L3, L4, L7, P4]},
    {"name": "M3-unclassified-passes",
     "why": "a class the table does not know is passed silently",
     "file": MAIN,
     "old": '        word = s.get("keyword") or ""\n        return "unclassified", (\n',
     "new": ('        word = s.get("keyword") or ""\n        return "explained", None\n'
             '        return "unclassified", (\n'),
     "red": [L4, P4], "green": [L1, L7, P1]},
    {"name": "M3b-unclassified-reaches-the-server",
     "why": "an unclassified statement is sent (executed) instead of refused",
     "file": MAIN,
     "old": '    if cls not in ("explain", "session"):\n',
     "new": '    if cls not in ("explain", "session", "unclassified"):\n',
     "red": [L4, P4], "green": [L1, L7]},
    {"name": "M4-session-statement-not-executed",
     "why": "a session statement passes without running, so a bad value passes too",
     "file": MAIN,
     "old": EXECUTE_SITE,
     "new": ('        if cls == "explain":\n'
             '            await db.execute(stmt, params)\n'
             '        verdict = "explained" if cls == "explain" else "executed_rolled_back"\n'),
     "red": [L1, L2, L5, P5], "green": [L3, L7]},
    {"name": "M5-rollback-error-ignored",
     "why": "an executed statement whose rollback raised still passes",
     "file": MAIN,
     "old": '    if verdict == "executed_rolled_back" and rollback_error is not None:\n',
     "new": '    if False and verdict == "executed_rolled_back" and rollback_error is not None:\n',
     "red": [P5], "green": [L1, L5, L7]},
    {"name": "M6-dml-executed-not-explained",
     "why": "the EXPLAIN prefix is dropped: DML would be EXECUTED",
     "file": MAIN, "old": STMT_SITE,
     "new": '        stmt = text(s["sql"])\n',
     "red": [L3], "green": [L1, L2, L4]},
    {"name": "M7-line-comments-not-skipped",
     "why": "a leading -- comment hides the first keyword",
     "file": MAIN,
     "old": '        elif sql.startswith("--", i):\n            j = sql.find("\\n", i)\n',
     "new": '        elif False and sql.startswith("--", i):\n            j = sql.find("\\n", i)\n',
     "red": [P1], "green": [P2, P3, L1, L7]},
    {"name": "M8-session-class-dropped",
     "why": "the classifier sends session words to EXPLAIN: the class itself is gone "
            "(L3 reddens too: the trading step's EXPLAIN-class statements go from "
            "four to five)",
     "file": MAIN,
     "old": '    if word in _JANITOR_SESSION_WORDS:\n        return "session", word\n',
     "new": '    if word in _JANITOR_SESSION_WORDS:\n        return "explain", word\n',
     "red": [P1, P2, P3, L1, L3, L7], "green": [L4]},
    # The report shape (commit 2).
    {"name": "M9-executed-row-mislabelled",
     "why": "the executed statement's row reads explained: the report hides it",
     "file": MAIN,
     "old": "                    _outcome(s, verdict)\n",
     "new": ("                    _outcome(s, \"explained\" if verdict == "
             "\"executed_rolled_back\" else verdict)\n"),
     "red": [L7, L8], "green": [L4, P6]},
    {"name": "M10-unchecked-tail-not-filled",
     "why": "a statement the run never reached gets no row",
     "file": MAIN,
     "old": "        for s in stmts[len(outcomes):]:\n",
     "new": "        for s in stmts[len(outcomes):len(outcomes)]:\n",
     "red": [P6], "green": [L4, L7, L8]},
    {"name": "M11-sql80-not-folded",
     "why": "sql80 keeps the literal's opening newline and indent",
     "file": MAIN,
     "old": "\"sql80\": \" \".join(s[\"sql\"].split())[:80]})\n",
     "new": "\"sql80\": s[\"sql\"][:80]})\n",
     "red": [L8], "green": [L4, L7]},
    {"name": "T2-inert-twin-at-the-sql80-site",
     "why": "the same slice written [0:80]: nothing may redden",
     "file": MAIN,
     "old": "\"sql80\": \" \".join(s[\"sql\"].split())[:80]})\n",
     "new": "\"sql80\": \" \".join(s[\"sql\"].split())[0:80]})\n",
     "red": [], "green": [L4, L7, L8, P6]},
    {"name": "M12-executed-count-dropped",
     "why": "counts no longer carries the executed statement",
     "file": MAIN,
     "old": "                       \"executed_rolled_back\": n_exec,\n",
     "new": "                       \"executed_rolled_back\": 0,\n",
     "red": [L7, L8], "green": [L4, P6]},
    {"name": "M13-banner-executed-line-dropped",
     "why": "the banner no longer names the executed statement",
     "file": MAIN,
     "old": "            if o[\"outcome\"] == \"executed_rolled_back\":\n",
     "new": "            if False and o[\"outcome\"] == \"executed_rolled_back\":\n",
     "red": [L8], "green": [L4, L7]},
    {"name": "M14-unclassified-count-dropped",
     "why": "counts no longer carries the unclassified statement",
     "file": MAIN,
     "old": "                        n_unclassified += verdict == \"unclassified\"\n",
     "new": "                        n_unclassified += 0\n",
     "red": [L4, L8], "green": [L7]},
    # The /health word (the addendum's commit).
    {"name": "M15-health-word-is-a-constant",
     "why": "the word no longer reads the recorded verdict: the self-test forced to fail "
            "still reads 1 (the negative control)",
     "file": MAIN, "old": WORD_SITE,
     "new": "    return 1\n",
     "red": [L9, P7], "green": [P8]},
    {"name": "T3-inert-twin-at-the-word",
     "why": "the same expression, parenthesised: nothing may redden",
     "file": MAIN, "old": WORD_SITE,
     "new": WORD_SITE.replace("return _JANITOR", "return (_JANITOR").replace(", 0)\n", ", 0))\n"),
     "red": [], "green": [L9, P7, P8]},
    {"name": "M16-word-dropped-from-the-connected-arm",
     "why": "the connected arm no longer passes the word: its answer cannot be built",
     "file": MAIN,
     # Anchored on the word's own line and the connected arm's next keyword
     # (CONNECTED_NEXT, see its comment above); --sites proves it occurs once.
     "old": WORD_ARG + CONNECTED_NEXT,
     "new": CONNECTED_NEXT,
     "red": [L9, P8], "green": [P7]},
    {"name": "M17-schema-field-dropped",
     "why": "HealthResponse no longer declares the word: the payload drops the key",
     "file": SCHEMAS, "old": "    janitor_selftest: int\n", "new": "",
     "red": [L9, P8], "green": [P7]},
    {"name": "M18-not-finished-reads-0",
     "why": "pending and running read 0: the train would fail at once in the seconds after boot",
     "file": MAIN,
     "old": '_JANITOR_SELFTEST_WORDS = {"ok": 1, "skipped": 2, "pending": 3, "running": 3}\n',
     "new": '_JANITOR_SELFTEST_WORDS = {"ok": 1, "skipped": 2}\n',
     "red": [P7], "green": [L9, P8]},
    {"name": "M19-unknown-status-reads-1",
     "why": "a status the map does not name reads as a pass, failed among them",
     "file": MAIN, "old": WORD_SITE,
     "new": WORD_SITE.replace(", 0)\n", ", 1)\n"),
     "red": [L9, P7], "green": [P8]},
    # The build marker the train reads through the edge.
    {"name": "M20-build-marker-reads-the-verdict",
     "why": "the connected arm reports the verdict word as the build marker: it then "
            "differs by role, the train's edge refusal (the negative control)",
     "file": MAIN, "old": BUILD_ARG + WORD_ARG + CONNECTED_NEXT,
     "new": ("                              janitor_selftest_build=_janitor_selftest_marker(),\n"
             + WORD_ARG + CONNECTED_NEXT),
     "red": [L9, P9], "green": [P7, P8]},
    {"name": "T4-inert-twin-at-the-build-marker",
     "why": "the same constant, parenthesised: nothing may redden",
     "file": MAIN, "old": BUILD_SITE, "new": "_JANITOR_SELFTEST_BUILD = (1)\n",
     "red": [], "green": [L9, P7, P8, P9]},
    {"name": "M21-build-marker-falsy",
     "why": "the build marker reads 0: the train fails at once on a falsy word",
     "file": MAIN, "old": BUILD_SITE, "new": "_JANITOR_SELFTEST_BUILD = 0\n",
     "red": [L9, P9], "green": [P7, P8]},
    {"name": "M22-build-marker-dropped-from-the-degraded-arm",
     "why": "the degraded arm no longer passes the build marker: its answer cannot be built",
     "file": MAIN, "old": BUILD_ARG + WORD_ARG + CACHED_NEXT, "new": WORD_ARG + CACHED_NEXT,
     "red": [L9, P8, P9], "green": [P7]},
    {"name": "M23-schema-build-field-dropped",
     "why": "HealthResponse no longer declares the build marker: the payload drops the key",
     "file": SCHEMAS, "old": "    janitor_selftest_build: int\n", "new": "",
     "red": [L9, P9], "green": [P7, P8]},
    # The role-specific LAND acceptance (Codex r1 MEDIUM, round 2).
    {"name": "M24-selftest-started-on-replica-too",
     "why": "the boot task is also started on the replica branch: the standby would race "
            "the read-only recovery connection with EXPLAINs of FOR UPDATE SKIP LOCKED "
            "janitor SQL, the exact thing the skip exists to avoid",
     "file": MAIN, "old": STANDBY_UPDATE_SITE,
     "new": STANDBY_UPDATE_SITE +
            "            tasks.append(asyncio.create_task(_run_janitor_query_selftest()))\n",
     "red": [P10], "green": [P7, P8, P9]},
    {"name": "T5-inert-twin-at-the-standby-report",
     "why": "the same two keys, written in the other order: nothing may redden",
     "file": MAIN, "old": STANDBY_UPDATE_SITE,
     "new": ('            _janitor_selftest_report.update({\n'
             '                "reason": "read replica: the janitor writers this '
             'validates do not run here",\n'
             '                "status": "skipped",\n'
             '            })\n'),
     "red": [], "green": [P10, P7, P8, P9]},
    # The semicolon plant's application mutant (Codex r2 LOW 1, round 3).
    {"name": "M25-split-and-execute-each-command",
     "why": "the single execute becomes a loop over the text split on ';': a joined "
            "two-command statement runs both commands and passes, with no driver change",
     "file": MAIN, "old": EXECUTE_SITE,
     "new": ('        for part in [p for p in stmt.text.split(";") if p.strip()]:\n'
             '            piece = text(part)\n'
             '            await db.execute(piece, {k: None for k in getattr(piece, "_bindparams", {})})\n'
             '        verdict = "explained" if cls == "explain" else "executed_rolled_back"\n'),
     "red": [L10], "green": [L11, L1, L3]},
]

# Totals for the closing SUMMARY line, filled in by run().
STATS = {"planted": 0, "restored_equal": 0, "clean_after": 0,
         "red": 0, "caught": 0, "green": 0, "held": 0}


def _git(*args):
    return subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True,
                          text=True, check=True).stdout


def _eol_of(data):
    """The file's single line ending, or None when it mixes them. The autocrlf
    checkout on this seat writes the api's files with CRLF while every needle
    above is written with LF, so a needle is matched in the file's own ending."""
    cr, lf, crlf = data.count(b"\r"), data.count(b"\n"), data.count(b"\r\n")
    if cr == 0:
        return "\n"
    if cr == lf == crlf:
        return "\r\n"
    return None


def _site(plant):
    """(path, bytes, text, eol, old, new): the plant's file as it is on disk, and
    the needle and its replacement in that file's line ending. The site check and
    the run both count through here, so they cannot disagree about the disk."""
    path = os.path.join(ROOT, plant["file"])
    with open(path, "rb") as fh:
        data = fh.read()
    src = data.decode("utf-8")
    eol = _eol_of(data)
    if eol is None:
        return path, data, src, None, None, None
    return (path, data, src, eol, plant["old"].replace("\n", eol),
            plant["new"].replace("\n", eol))


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _outcomes(output):
    """{nodeid: [outcome, ...]} from pytest's -rA short summary."""
    got = {}
    for line in output.splitlines():
        m = re.match(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (\S+)", line)
        if m:
            got.setdefault(m.group(2), []).append(m.group(1))
    return got


def _judge(node, got, want):
    cases = [o for nid, outs in got.items()
             if nid == node or nid.startswith(node + "[") for o in outs]
    if not cases:
        return "missing"
    if "ERROR" in cases:
        return "error"
    if want == "red":
        return "ok" if "FAILED" in cases else "stayed green"
    return "ok" if set(cases) == {"PASSED"} else "reddened"


def run(plant, log, expect_head):
    def out(msg=""):
        print(msg)
        log.write(msg + "\n")
        log.flush()
    out("=" * 78)
    out("PLANT %s -- %s" % (plant["name"], plant["why"]))
    status = _git("status", "--porcelain")
    out("git status --porcelain: %r" % status)
    if status.strip():
        return "FAILED (tree not clean before the plant)"
    head = _git("rev-parse", "HEAD").strip()
    out("HEAD %s" % head)
    if expect_head and not head.startswith(expect_head):
        return "FAILED (HEAD %s is not %s)" % (head, expect_head)
    path, before, src, eol, old, new = _site(plant)
    if eol is None:
        return "FAILED (%s mixes line endings: no needle can be placed)" % plant["file"]
    n = src.count(old)
    out("old text occurrences in %s (%s line endings): %d"
        % (plant["file"], "CRLF" if eol == "\r\n" else "LF", n))
    if n != 1:
        return "FAILED (old text occurs %d times)" % n
    sha_before = _sha(before)
    out("sha256 before %s" % sha_before)
    planted = src.replace(old, new, 1)
    STATS["planted"] += 1
    try:
        with open(path, "wb") as fh:
            fh.write(planted.encode("utf-8"))
        for d in difflib.unified_diff(src.splitlines(True), planted.splitlines(True),
                                      plant["file"], plant["file"] + " (planted)", n=2):
            out(d.rstrip("\r\n"))
        nodes = list(dict.fromkeys(plant["red"] + plant["green"]))
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider"]
                              + nodes, cwd=ROOT, capture_output=True, text=True)
        text_out = proc.stdout + proc.stderr
        for line in text_out.splitlines():
            if line.startswith(("E ", "FAILED ", "ERROR ", "PASSED ")) or "passed" in line[-40:] \
                    or "failed" in line[-40:]:
                out("  | " + line[:300])
        got = _outcomes(text_out)
        verdicts = [(node, want, _judge(node, got, want))
                    for want, group in (("red", plant["red"]), ("green", plant["green"]))
                    for node in group]
        for node, want, v in verdicts:
            out("  %-5s %-7s %s" % (want.upper(), v, node.split("::")[-1]))
        bad = [(node.split("::")[-1], want, v) for node, want, v in verdicts if v != "ok"]
        for node, want, v in verdicts:
            STATS["red" if want == "red" else "green"] += 1
            STATS["caught" if want == "red" else "held"] += v == "ok"
    finally:
        with open(path, "wb") as fh:
            fh.write(before)
        with open(path, "rb") as fh:
            sha_after = _sha(fh.read())
        out("sha256 after  %s (%s)" % (sha_after, "equal" if sha_after == sha_before else "DIFFERENT"))
    STATS["restored_equal"] += sha_after == sha_before
    if sha_after != sha_before:
        return "FAILED (the file was not restored)"
    status = _git("status", "--porcelain")
    out("git status --porcelain after: %r" % status)
    STATS["clean_after"] += not status.strip()
    if status.strip():
        return "FAILED (tree not clean after the plant)"
    return "AS REQUIRED" if not bad else "FAILED (%r)" % bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log")
    ap.add_argument("--expect-head")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--sites", action="store_true")
    a = ap.parse_args()
    plants = [p for p in PLANTS if not a.only or p["name"] in a.only]
    if a.only and len(plants) != len(a.only):
        print("unknown plant name among %r" % a.only)
        return 2
    if a.sites:
        bad = 0
        for p in plants:
            _, _, src, eol, old, new = _site(p)
            if eol is None:
                print("%-38s MIXED LINE ENDINGS in %s" % (p["name"], p["file"]))
                bad += 1
                continue
            n = src.count(old)
            try:
                ast.parse(src.replace(old, new, 1))
                parses = "parses"
            except SyntaxError as e:
                parses = "DOES NOT PARSE: %s" % e
                bad += 1
            bad += n != 1
            print("%-38s occurrences=%d %s eol=%s"
                  % (p["name"], n, parses, "CRLF" if eol == "\r\n" else "LF"))
        return 1 if bad else 0
    if not os.environ.get("JANITOR_SELFTEST_TEST_PG_DSN"):
        print("JANITOR_SELFTEST_TEST_PG_DSN is unset: every live node would FAIL by design "
              "and read as a kill. Refusing to start.")
        return 2
    if not a.log:
        print("--log is required for a run")
        return 2
    results = []
    with open(a.log, "a", encoding="utf-8", newline="\n") as log:
        for p in plants:
            r = run(p, log, a.expect_head)
            line = "RESULT %s: %s" % (p["name"], r)
            print(line)
            log.write(line + "\n")
            results.append(r)
        line = ("SUMMARY plants=%d as_required=%d planted=%d restores_equal=%d/%d "
                "clean_after=%d/%d red_caught=%d/%d controls_green=%d/%d" % (
                    len(results), sum(r == "AS REQUIRED" for r in results),
                    STATS["planted"], STATS["restored_equal"], STATS["planted"],
                    STATS["clean_after"], STATS["planted"], STATS["caught"], STATS["red"],
                    STATS["held"], STATS["green"]))
        print(line)
        log.write(line + "\n")
    return 0 if all(r == "AS REQUIRED" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
