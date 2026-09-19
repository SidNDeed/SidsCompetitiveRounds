"""Every test file on disk must actually be collected.

WHY THIS EXISTS
    scripts/test_service_policy.py has been red since 2026-08-16 and nobody
    saw it: it is a CLI program with no pytest-visible tests, so
    `pytest backend/tests` imports nothing from it, and no runner invoked it
    directly. Its route pin said 280 while the tree had 363 -- 121 commits of
    main.py drift -- and because the count assertion fires first, the
    assertion that actually protects something (that 48 named
    service-sensitive routes still reach a guard) had not executed in a month.

    A guard that is never collected is indistinguishable from a guard that
    passes. This file closes that class: it fails when a test file exists on
    disk but contributes nothing to the run, so the NEXT uncollected guard is
    loud instead of silent.

    Scope is deliberately backend/tests only. An unrestricted repository-root
    invocation would also discover .claude/worktrees and ai-collab scratch
    content, which is not a stable set to pin against.
"""

from __future__ import annotations

import pathlib

TESTS_DIR = pathlib.Path(__file__).resolve().parent

# Files that legitimately contribute zero collected items. Each entry needs a
# reason; an empty-by-accident file is exactly what this test is for, so the
# list is a closed enumeration rather than a pattern.
#
# "Zero collected items" is NOT the same as "does not run". A module-level
# script style file executes its assertions when pytest IMPORTS it during
# collection, so it is load-bearing and a failure surfaces as a collection
# error -- it is simply invisible in the passed count. Say which case an entry
# is, because the two have very different risk.
ALLOW_NO_ITEMS: dict[str, str] = {
    "test_bridge_quota.py": (
        "Module-level script style, not def test_*. Its 23 top-level asserts "
        "RUN at import during collection (it drives the real _yt_get against a "
        "fake clock/session and calls production's _quota_day_valid), so it is "
        "load-bearing and a regression fails the run as a collection error. "
        "Exempt because it genuinely executes -- not because it is dead. "
        "Worth converting to def test_* so its 23 checks become individually "
        "visible and stop executing during --collect-only."
    ),
}


def _test_files_on_disk() -> set[str]:
    return {p.name for p in TESTS_DIR.glob("test_*.py")}


def _whole_directory_was_collected(request) -> bool:
    """True only when this run's collection target covers all of backend/tests.

    Running a single file (`pytest backend/tests/test_foo.py`) puts only that
    file's items in the session, which would make the completeness assertion
    below fail for every OTHER file -- a false alarm on a perfectly normal
    invocation. The completeness claim is only meaningful for a full-directory
    run, so it is asserted there and explicitly skipped elsewhere rather than
    being quietly wrong in both directions.
    """
    for arg in request.config.args:
        candidate = pathlib.Path(str(arg).split("::")[0])
        if not candidate.is_absolute():
            candidate = (pathlib.Path(str(request.config.invocation_params.dir))
                         / candidate)
        try:
            candidate = candidate.resolve()
        except Exception:  # pragma: no cover
            continue
        if candidate == TESTS_DIR or candidate in TESTS_DIR.parents:
            return True
    return False


def test_every_test_file_on_disk_is_collected(request):
    """Fail if a test_*.py exists but produced no collected items.

    Demonstrated to fail: drop a file into backend/tests whose tests pytest
    cannot collect (a bad import, or no test functions at all) and this goes
    red naming it. Removing the file returns it to green.
    """
    if not _whole_directory_was_collected(request):
        import pytest

        pytest.skip(
            "completeness is only assertable on a full `pytest backend/tests` "
            "run; this invocation targeted a narrower set. scripts/run_checks.py "
            "runs the full directory."
        )

    collected = getattr(request.config, "scr_collected_test_files", None)
    assert collected is not None, (
        "conftest.pytest_collection_modifyitems did not record the collected "
        "set; without it this check cannot distinguish 'not collected' from "
        "'deselected' and would be meaningless"
    )

    on_disk = _test_files_on_disk()
    silent = sorted(n for n in on_disk - collected if n not in ALLOW_NO_ITEMS)

    assert not silent, (
        "these test files exist on disk but contributed NO collected tests: "
        + ", ".join(silent) + ". Either they define no def test_* and are dead, "
        "or they are module-level scripts whose asserts run at import and are "
        "merely invisible in the count -- check which before deciding. Fix the "
        "file, or add it to ALLOW_NO_ITEMS with a reason saying which case it is."
    )


def test_this_file_was_itself_collected(request):
    """Negative control for the mechanism above.

    If request.session.items were empty or the path comparison were broken,
    the manifest test would pass vacuously -- the failure mode it exists to
    prevent. This asserts the collection view is non-empty and can see itself.
    """
    names = getattr(request.config, "scr_collected_test_files", None)
    assert names, (
        "the recorded collected set is missing or empty - the manifest check "
        "would pass vacuously"
    )
    assert pathlib.Path(__file__).name in names, (
        "the manifest test cannot see its own file in the collected set, so its "
        "path comparison is wrong and its result means nothing"
    )


def test_service_policy_gate_is_not_pytest_collectable():
    """Pin the reason the service-policy gate needs its own runner step.

    scripts/test_service_policy.py is named test_*.py but exposes only a CLI
    main(), so pytest collects zero tests from it. That is not a bug to fix
    here -- it is a fact the canonical runner must compensate for by invoking
    it explicitly. If someone ever converts it to real pytest tests, this
    assertion goes red and the runner step should be revisited rather than
    silently duplicated.
    """
    gate = TESTS_DIR.parent.parent / "scripts" / "test_service_policy.py"
    assert gate.exists(), f"expected the service-policy gate at {gate}"
    source = gate.read_text(encoding="utf-8")
    assert "def main(" in source, "gate no longer exposes a CLI main()"
    top_level_tests = [
        line for line in source.splitlines() if line.startswith("def test_")
    ]
    assert not top_level_tests, (
        "the gate now defines top-level test functions, so pytest would collect "
        "it; scripts/run_checks.py invokes it separately and would double-run it"
    )
