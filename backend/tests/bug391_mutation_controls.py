"""Bug 391 — mutation controls for the 1v2 abandoned-series horizon sweep.

#391: a test that has never been seen to fail is decoration. This runner
breaks the sweep one defect at a time and requires the named tests to RED;
then it makes an unrelated edit in the same file and requires every test to
stay GREEN. A suite that reds on both is measuring the file, not the
behaviour.

Run it (the live half needs the DSN or the mutations have nothing to kill):

    BUG391_TEST_PG_DSN=postgresql+asyncpg://postgres@127.0.0.1:55432/scr_bug391 \\
        python backend/tests/bug391_mutation_controls.py

It edits backend/api/main.py in place and restores it from an in-memory copy
plus a backup file. It never runs `git checkout --` or `git restore`: the tree
carries uncommitted work and those commands take the whole path with them
(#290 / #401). The final line re-hashes main.py against the original and the
run FAILS if the file did not come back byte-identical.
"""

import hashlib
import io
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
MAIN_PY = BACKEND / "api" / "main.py"
TESTS = "tests/test_ovt_abandoned_horizon.py"

ALL_GREEN = "__ALL_GREEN__"

# Each entry: (label, what defect it models, [(old, new), ...], [tests that must red])
MUTATIONS = [
    (
        "M1-horizon-off-by-one-day",
        "the horizon is 13 days, not the 14 Sid ruled",
        [("OVT_ABANDONED_HORIZON_DAYS = 14", "OVT_ABANDONED_HORIZON_DAYS = 13")],
        ["test_a_series_one_day_inside_the_horizon_is_untouched",
         "test_the_horizon_is_the_fourteen_days_sid_ruled_for_ranked"],
    ),
    (
        "M2-idleness-from-the-series-row-only",
        "games are not activity: idleness is measured from created_at alone",
        [("""           AND NOT EXISTS (
                 SELECT 1 FROM ovt_matches m
                  WHERE m.series_id = s.id
                    AND GREATEST(m.ended_at, m.created_at)
                        >= NOW() - make_interval(days => CAST(:days AS int)))
         ORDER BY s.created_at""", "         ORDER BY s.created_at"),
         ("""           AND NOT EXISTS (
                 SELECT 1 FROM ovt_matches m
                  WHERE m.series_id = s.id
                    AND GREATEST(m.ended_at, m.created_at)
                        >= NOW() - make_interval(days => CAST(:days AS int)))
    \"\"\"), {"sid": str(series_id), "days": int(days)})).first()""",
          """    \"\"\"), {"sid": str(series_id), "days": int(days)})).first()""")],
        ["test_an_old_series_whose_trio_played_yesterday_is_untouched",
         "test_the_candidate_read_alone_already_excludes_a_series_played_yesterday"],
    ),
    (
        "M2b-candidate-read-stops-filtering",
        "only the under-lock re-check carries the recency term",
        [("""           AND NOT EXISTS (
                 SELECT 1 FROM ovt_matches m
                  WHERE m.series_id = s.id
                    AND GREATEST(m.ended_at, m.created_at)
                        >= NOW() - make_interval(days => CAST(:days AS int)))
         ORDER BY s.created_at""", "         ORDER BY s.created_at")],
        ["test_the_candidate_read_alone_already_excludes_a_series_played_yesterday"],
    ),
    (
        "M3-no-predicate-recheck-in-the-transaction",
        "the candidate list is trusted: no status re-check under the lock, "
        "no status guard on the write",
        [('    if locked is None or locked["status"] != "active":',
          "    if locked is None:"),
         ("""         WHERE id = CAST(:sid AS uuid)
           AND status = 'active'
        RETURNING id""",
          """         WHERE id = CAST(:sid AS uuid)
        RETURNING id""")],
        ["test_a_report_completing_the_series_under_the_lock_wins",
         "test_the_predicate_is_re_checked_inside_the_transaction"],
    ),
    (
        "M3b-status-is-not-part-of-the-predicate",
        "M3 plus a candidate read that no longer filters on status",
        [('    if locked is None or locked["status"] != "active":',
          "    if locked is None:"),
         ("""         WHERE id = CAST(:sid AS uuid)
           AND status = 'active'
        RETURNING id""",
          """         WHERE id = CAST(:sid AS uuid)
        RETURNING id"""),
         ("""         WHERE s.status = 'active'
           AND s.created_at < NOW()""",
          """         WHERE s.status IS NOT NULL
           AND s.created_at < NOW()""")],
        ["test_sweeping_the_same_row_twice_is_a_no_op",
         "test_a_report_completing_the_series_under_the_lock_wins"],
    ),
    (
        "M4-lock-mode-for-update",
        "the janitor takes FOR UPDATE, which conflicts with the FK check a "
        "game report takes on the same row",
        [('        "SELECT status FROM ovt_series WHERE id = CAST(:sid AS uuid)"\n'
          '        " FOR NO KEY UPDATE"',
          '        "SELECT status FROM ovt_series WHERE id = CAST(:sid AS uuid)"\n'
          '        " FOR UPDATE"')],
        ["test_the_settlement_lock_does_not_block_a_game_reports_fk_insert",
         "test_the_row_lock_is_for_no_key_update"],
    ),
    (
        "M5-credit-the-leader",
        "the sweep completes the series for whoever was ahead instead of voiding it",
        [("""           SET status = 'canceled',
               invalidated_at = NOW(),
               invalidation_reason = 'abandoned_horizon_void'""",
          """           SET status = 'completed',
               winner_side = 1,
               completed_at = NOW(),
               invalidated_at = NOW(),
               invalidation_reason = 'abandoned_horizon_void'""")],
        ["test_the_settlement_writes_neither_completed_at_nor_winner_side",
         "test_a_past_horizon_series_is_voided_and_nobody_is_credited"],
    ),
    (
        "M6-client-stamp-counts-as-activity",
        "the client-supplied started_at is read as activity, so a future-dated "
        "report holds its own series open",
        [("GREATEST(m.ended_at, m.created_at)",
          "GREATEST(m.ended_at, m.created_at, m.started_at)")],
        ["test_a_future_dated_client_stamp_cannot_hold_a_series_open",
         "test_idleness_is_measured_from_server_clock_columns_only"],
    ),
    (
        "NC-unrelated-constant-in-the-same-file",
        "negative control: a 1v2 gold constant this sweep never reads",
        [("OVT_SERIES_WIN_GOLD = 40", "OVT_SERIES_WIN_GOLD = 41")],
        [ALL_GREEN],
    ),
]


def apply_all(src: str, edits) -> str:
    for old, new in edits:
        n = src.count(old)
        if n == 0:
            raise SystemExit(f"anchor not found:\n{old[:200]}")
        src = src.replace(old, new)
    return src


SUMMARY = re.compile(
    r"(\d+) (passed|failed|errors|error|skipped|xfailed|xpassed|deselected)")


def clean_slate() -> str:
    """Terminate every other backend on the dedicated test database.

    The suite's per-case fixture does this too, but it cannot help when the
    statement that blocks is the fixture's own DDL: the case then dies inside
    the reset and every later case in that process dies with it. Doing it here
    as well is what stops one dead case reaching across into the NEXT
    mutation's run. A cross-run leak of exactly that shape is what once put a
    false REDDENED on this runner's negative control. Bounded by construction:
    this database exists for this file alone.
    """
    import asyncio
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    async def go() -> int:
        engine = create_async_engine(
            os.environ["BUG391_TEST_PG_DSN"], poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                n = (await conn.execute(text(
                    "SELECT count(*) FROM pg_stat_activity"
                    " WHERE datname = current_database()"
                    "   AND pid <> pg_backend_pid()"))).scalar()
                await conn.execute(text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                    " WHERE datname = current_database()"
                    "   AND pid <> pg_backend_pid()"))
                await conn.commit()
                return int(n or 0)
        finally:
            await engine.dispose()

    try:
        n = asyncio.run(go())
    except Exception as exc:                      # noqa: BLE001 - reported, not raised
        return f"clean-slate probe FAILED: {exc!r}"
    return f"cleared {n} leftover backend(s)" if n else ""


def run_suite() -> dict:
    """Run the suite once and report what actually executed.

    A run that did not execute every test is not evidence about the mutation.
    Module-level and fixture errors used to be parsed into the same set as
    test failures, so a run in which NOTHING executed was scored as "the
    mutant survived" — the filter was discarding the very line it measured
    (#441). They are separate outcomes now, and the caller retries them
    instead of scoring them.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=str(BACKEND), capture_output=True, text=True)
    failed, errored, collect_errors = set(), set(), []
    for line in proc.stdout.splitlines():
        if line.startswith("FAILED ") or line.startswith("ERROR "):
            part = line.split(" ", 1)[1].split(" ")[0]
            if "::" in part:
                target = failed if line.startswith("FAILED ") else errored
                target.add(part.rsplit("::", 1)[-1])
            else:
                # "ERROR tests/foo.py - ..." names the MODULE, so no test in
                # it ran. It is never a test name and never a kill signal.
                collect_errors.append(part)
    lines = proc.stdout.strip().splitlines()
    tail = lines[-1] if lines else ""
    counts: dict = {}
    for n, word in SUMMARY.findall(tail):
        word = "error" if word == "errors" else word
        counts[word] = counts.get(word, 0) + int(n)
    return {
        "failed": failed,
        "errored": errored,
        "collect_errors": collect_errors,
        "counts": counts,
        "ran": counts.get("passed", 0) + counts.get("failed", 0),
        "tail": tail,
        "rc": proc.returncode,
    }


def not_a_verdict(res: dict, expected_total) -> str:
    """Empty when the run may be scored; else the reason it may not be."""
    if res["collect_errors"]:
        return f"module-level error, no test in it ran: {res['collect_errors']}"
    if res["errored"]:
        return f"fixture error in {sorted(res['errored'])}"
    if res["counts"].get("error"):
        return f"{res['counts']['error']} error(s) reported"
    if res["counts"].get("skipped"):
        return (f"{res['counts']['skipped']} test(s) SKIPPED — the live half "
                f"did not run, so most mutations had nothing to kill")
    if not res["ran"]:
        return f"no test accounted for at all (tail: {res['tail']!r})"
    if expected_total is not None and res["ran"] != expected_total:
        return (f"{res['ran']} test(s) accounted for, expected "
                f"{expected_total} — the suite did not run whole")
    return ""


def main() -> int:
    if not os.environ.get("BUG391_TEST_PG_DSN"):
        print("BUG391_TEST_PG_DSN unset — the live half would skip and most "
              "mutations would have nothing to kill. Refusing to run.")
        return 2
    original = io.open(MAIN_PY, encoding="utf-8", newline="").read()
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
    backup = MAIN_PY.with_suffix(".py.bug391-mutation-backup")
    backup.write_text(original, encoding="utf-8", newline="")
    print(f"main.py sha256 {digest}")
    print(f"backup {backup}")

    rows = []
    try:
        slate = clean_slate()
        if slate:
            print(f"[slate] {slate}")
        base = run_suite()
        print(f"[baseline] {base['tail']}")
        why = not_a_verdict(base, None)
        if why or base["failed"]:
            print(f"baseline is not a green verdict: "
                  f"{why or sorted(base['failed'])}")
            return 2
        expected_total = base["ran"]
        print(f"[baseline] every run below must account for "
              f"{expected_total} tests or it is not a verdict")
        for label, defect, edits, expect in MUTATIONS:
            t0 = time.time()
            MAIN_PY.write_text(apply_all(original, edits), encoding="utf-8",
                               newline="")
            res, why = None, ""
            for attempt in (1, 2):
                slate = clean_slate()
                if slate:
                    print(f"           [slate] {slate}")
                res = run_suite()
                why = not_a_verdict(res, expected_total)
                if not why:
                    break
                print(f"           [no verdict, attempt {attempt}] {why}")
                print(f"           [no verdict, attempt {attempt}] "
                      f"{res['tail']}")
            MAIN_PY.write_text(original, encoding="utf-8", newline="")
            if why:
                # Never ALIVE and never KILL: the run did not measure the
                # mutation, so it carries no information about it either way.
                rows.append((label, None, f"NO VERDICT: {why}", defect))
                print(f"[NOVER] {label} ({time.time() - t0:.0f}s) — "
                      f"NO VERDICT: {why}")
                print(f"           models: {defect}")
                print(f"           {res['tail']}")
                continue
            failed = res["failed"]
            if expect == [ALL_GREEN]:
                ok = not failed
                detail = "all green" if ok else f"REDDENED: {sorted(failed)}"
            else:
                missing = [t for t in expect if t not in failed]
                ok = not missing
                detail = (f"killed {sorted(failed)}" if ok
                          else f"SURVIVED for {missing}")
            rows.append((label, ok, detail, defect))
            print(f"[{'KILL ' if ok else 'ALIVE'}] {label} "
                  f"({time.time() - t0:.0f}s) — {detail}")
            print(f"           models: {defect}")
            print(f"           {res['tail']}")
    finally:
        MAIN_PY.write_text(original, encoding="utf-8", newline="")

    after = hashlib.sha256(
        io.open(MAIN_PY, encoding="utf-8", newline="").read().encode("utf-8")).hexdigest()
    print(f"restored sha256 {after} ({'MATCH' if after == digest else 'MISMATCH'})")
    backup.unlink(missing_ok=True)

    good = [r for r in rows if r[1] is True]
    nover = [r for r in rows if r[1] is None]
    bad = [r for r in rows if r[1] is False]
    print(f"\n{len(good)}/{len(rows)} controls behaved as required")
    if bad:
        print(f"{len(bad)} control(s) did NOT behave: "
              f"{[r[0] for r in bad]}")
    if nover:
        # Distinct from a misbehaving control on purpose. These runs measured
        # nothing, so the set is incomplete rather than failing, and the only
        # honest report is to say so (#342: a check that cannot fail is worse
        # than no check — one that silently did not run is the same defect).
        print(f"{len(nover)} control(s) produced NO VERDICT after a retry on a "
              f"clean slate: {[r[0] for r in nover]}")
    if after != digest:
        print("main.py DID NOT come back byte-identical — restore by hand")
        return 3
    if nover:
        return 4
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
