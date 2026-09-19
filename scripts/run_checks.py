#!/usr/bin/env python3
"""Canonical local check runner: the one invocation that runs everything.

Two things must run, and until now nothing ran both:

  1. pytest backend/tests          -- ~1,500 collected tests
  2. scripts/test_service_policy.py --static
       A CLI program, NOT pytest-collectable. `pytest backend/tests` imports
       nothing from it. It went red on 2026-08-16 and stayed red and unseen
       for 121 commits of backend/api/main.py.

Usage:
    python scripts/run_checks.py            # everything
    python scripts/run_checks.py --fast     # pytest only
    python scripts/run_checks.py --gate     # service-policy gate only

The pytest summary line is reproduced WHOLE. Quoting only the passed count
hides errors, skips and xfails in the same line (#596b).
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _run(label: str, argv: list[str]) -> tuple[str, int, str]:
    print("=" * 72)
    print(f"RUNNING: {label}")
    print("  " + " ".join(argv))
    print("=" * 72)
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    sys.stdout.write(out if len(out) < 20000 else out[-20000:])
    sys.stdout.flush()
    return label, proc.returncode, out


def _pytest_summary(out: str) -> str:
    """The last line that looks like pytest's own summary, reproduced whole."""
    for line in reversed(out.splitlines()):
        stripped = line.strip("= \t")
        if stripped and ("passed" in stripped or "failed" in stripped
                         or "error" in stripped or "no tests ran" in stripped):
            return stripped
    return "(no pytest summary line found -- treat as a failure to run)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="pytest only")
    ap.add_argument("--gate", action="store_true", help="service-policy gate only")
    args = ap.parse_args()

    results: list[tuple[str, int, str]] = []

    if not args.gate:
        # --durations keeps the cost visible. The suite takes ~20 minutes, and
        # that is concentrated in a handful of tests, not spread evenly: the
        # font-coverage manifest check alone is ~50s. A check nobody runs
        # because it is slow fails the same way a check nobody collects does,
        # so the slow ones should be named rather than become folklore.
        results.append(_run(
            "pytest backend/tests",
            [sys.executable, "-m", "pytest", "backend/tests", "-q", "--durations=10"],
        ))

    if not args.fast:
        results.append(_run(
            "service-policy gate (static)",
            [sys.executable, "scripts/test_service_policy.py", "--static"],
        ))

    print()
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    failed = 0
    for label, code, out in results:
        status = "OK  " if code == 0 else "FAIL"
        if code != 0:
            failed += 1
        detail = _pytest_summary(out) if label.startswith("pytest") else f"exit {code}"
        print(f"  [{status}] {label}: {detail}")

    if failed:
        print()
        print(f"{failed} of {len(results)} check(s) FAILED.")
        print("A red service-policy gate means the route table changed without a")
        print("classification review -- classify the new routes, then refresh the")
        print("pin deliberately. Do not refresh the pin to make it green.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
