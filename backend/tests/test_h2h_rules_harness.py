"""Runs the H2HRules self-test. Not a source-shape gate - an execution.

`plugin/H2HRules.cs` is kept free of Unity, Photon and BepInEx so the decisions
behind the head-to-head line and the room-bound series id can be EXECUTED. Until
2026-09-06 the only thing that executed them was a csproj in a scratch
directory: the "81/81, fail=0" quoted in review notes was a number nobody could
reproduce from the repository and no pytest run ever touched (r14 LOW 1). The
harness is now committed at tools/h2h-harness and this is what runs it.

The cases that matter most here are the SEQUENCES. Every other case hands a rule
a record built by hand, which cannot see an ordering fault - and an ordering
fault is exactly what r14 HIGH was: the series record was stamped with the
pairing's counter, before the series counter had moved, so the stamp could never
equal the value its readers compare it against.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
HARNESS = REPO / "tools" / "h2h-harness" / "h2h-harness.csproj"
MAIN_CS = REPO / "tools" / "h2h-harness" / "Main.cs"
RULES_CS = REPO / "plugin" / "H2HRules.cs"


def _dotnet():
    """The dotnet CLI, or None. On the build seat it is user-local."""
    found = shutil.which("dotnet")
    if found:
        return found
    candidate = Path(os.path.expanduser("~")) / ".dotnet" / "dotnet.exe"
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def harness_run():
    dotnet = _dotnet()
    if dotnet is None:
        pytest.skip("dotnet CLI not on this machine")
    proc = subprocess.run(
        [dotnet, "run", "--project", str(HARNESS), "-c", "Release", "--", "--quiet"],
        cwd=str(REPO), capture_output=True, text=True, timeout=600,
    )
    return proc


# ── the execution ────────────────────────────────────────────────────────────

def test_the_self_test_runs_every_case_and_none_fail(harness_run):
    """run == declared, fail == 0, exit 0. All three, because each covers a
    different way this can look green while proving nothing: a case that
    stopped running, a case that ran and failed, and a harness that threw
    before reaching its summary."""
    out = harness_run.stdout + harness_run.stderr
    match = re.search(r"h2h-harness run=(\d+) fail=(\d+) verdict=(\w+)", out)
    assert match, f"no verdict line from the harness:\n{out[-3000:]}"
    run, fail, verdict = int(match.group(1)), int(match.group(2)), match.group(3)

    declared = re.search(r"SELFTEST_CASES\s*=\s*(\d+)", RULES_CS.read_text(encoding="utf-8"))
    assert declared, "H2HRules no longer declares a case count"
    declared = int(declared.group(1))

    assert fail == 0, f"{fail} self-test case(s) failed:\n{out[-3000:]}"
    assert run == declared, (
        f"the self-test ran {run} cases but declares {declared}. A case that "
        "stops running is invisible to a pass count."
    )
    assert verdict == "PASS"
    assert harness_run.returncode == 0, (
        f"harness exit {harness_run.returncode}; a non-zero exit must not read as a pass"
    )


def test_the_sequence_cases_are_present_and_executed(harness_run):
    """The named sequences must actually be among the cases that ran.

    A count alone cannot tell whether the ordering cases specifically survived
    an edit, and they are the ones r14 LOW 1 is about.
    """
    dotnet = _dotnet()
    proc = subprocess.run(
        [dotnet, "run", "--project", str(HARNESS), "-c", "Release"],
        cwd=str(REPO), capture_output=True, text=True, timeout=600,
    )
    out = proc.stdout
    required = [
        "seq:join-stamps-with-the-series-counter",
        "seq:preflight-publish-is-current",
        "seq:join-with-an-unreadable-room-name",
        "seq:polled-exit-alone-does-not-bump",
        "seq:polled-exit-after-the-reliable-edge-is-idempotent",
        "seq:pair-invalidation-is-not-a-series-event",
        "seq:rejoining-the-name-answers-nothing",
        "control:seq:staged-join-stamped-with-the-pair-counter",
        "control:seq:unreadable-join-keeps-the-binding",
        "control:seq:polled-exit-bumped-the-counter",
    ]
    for name in required:
        assert f"case={name}" in out, f"the sequence case {name} did not run"
        line = next(ln for ln in out.splitlines() if f"case={name}" in ln)
        assert line.rstrip().endswith("PASS"), line


# ── the harness itself must stay honest ──────────────────────────────────────

def test_the_harness_compiles_only_the_rules_file():
    """A default compile glob would drag in the whole plugin tree, which needs
    Unity - and the first fix for that is usually to stub something, at which
    point the harness stops executing the shipped rules."""
    proj = HARNESS.read_text(encoding="utf-8")
    assert "<EnableDefaultCompileItems>false</EnableDefaultCompileItems>" in proj
    includes = re.findall(r'<Compile Include="([^"]+)"', proj)
    assert sorted(includes) == sorted(["Main.cs", "../../plugin/H2HRules.cs"]), includes
    assert includes.count("../../plugin/H2HRules.cs") == 1


def test_the_harness_target_framework_is_installed():
    """net8.0 BUILDS on this seat and then fails to launch, because only the
    10.x runtime is installed. Assert the TFM against the installed runtimes so
    an SDK rotation fails with a message naming the cause, not a launch error."""
    dotnet = _dotnet()
    if dotnet is None:
        pytest.skip("dotnet CLI not on this machine")
    proj = HARNESS.read_text(encoding="utf-8")
    tfm = re.search(r"<TargetFramework>net(\d+)\.0</TargetFramework>", proj)
    assert tfm, "the harness declares no net TFM"
    major = int(tfm.group(1))

    listed = subprocess.run([dotnet, "--list-runtimes"], capture_output=True,
                            text=True, timeout=120).stdout
    majors = {int(m) for m in re.findall(r"Microsoft\.NETCore\.App (\d+)\.", listed)}
    assert majors, f"could not read installed runtimes:\n{listed}"
    assert major in majors or ("<RollForward>LatestMajor</RollForward>" in proj
                               and any(m >= major for m in majors)), (
        f"the harness targets net{major}.0 but the installed Microsoft.NETCore.App "
        f"majors are {sorted(majors)}. It would build and then fail to launch."
    )


def test_the_harness_entry_point_has_no_conditional_compilation():
    """Nothing in the harness may compile differently from what it reports."""
    main = MAIN_CS.read_text(encoding="utf-8")
    assert "#if" not in main
    assert "partial" not in main
    # A run of zero cases must not be able to exit 0.
    assert "run > 0" in main
