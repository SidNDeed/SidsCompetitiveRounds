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


def run_suite() -> tuple:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=str(BACKEND), capture_output=True, text=True)
    failed = set()
    for line in proc.stdout.splitlines():
        if line.startswith("FAILED ") or line.startswith("ERROR "):
            part = line.split(" ", 1)[1].split(" ")[0]
            failed.add(part.rsplit("::", 1)[-1])
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    return failed, tail


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
        base_failed, base_tail = run_suite()
        print(f"[baseline] {base_tail}")
        if base_failed:
            print(f"baseline is not green: {sorted(base_failed)}")
            return 2
        for label, defect, edits, expect in MUTATIONS:
            t0 = time.time()
            MAIN_PY.write_text(apply_all(original, edits), encoding="utf-8",
                               newline="")
            failed, tail = run_suite()
            MAIN_PY.write_text(original, encoding="utf-8", newline="")
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
            print(f"           {tail}")
    finally:
        MAIN_PY.write_text(original, encoding="utf-8", newline="")

    after = hashlib.sha256(
        io.open(MAIN_PY, encoding="utf-8", newline="").read().encode("utf-8")).hexdigest()
    print(f"restored sha256 {after} ({'MATCH' if after == digest else 'MISMATCH'})")
    backup.unlink(missing_ok=True)

    bad = [r for r in rows if not r[1]]
    print(f"\n{len(rows) - len(bad)}/{len(rows)} controls behaved as required")
    if after != digest:
        print("main.py DID NOT come back byte-identical — restore by hand")
        return 3
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
