"""Runs the client rule self-tests. Not a source-shape gate - an execution.

`plugin/LogScrub.cs` is kept free of Unity, Photon and BepInEx so that what a
log bundle stops carrying can be EXECUTED rather than asserted about as source
text -- the arrangement `tools/h2h-harness` already uses for H2HRules, and the
reason its own class comment gives for the shape it is written in. Until now
nothing in the repository ran it: the self-test existed behind a Debug config
lever that fires once at startup on a developer's machine, so its numbers were
not reproducible from a checkout and no pytest run ever touched them.

Three separate ways this can look green while proving nothing, and one
assertion each: a suite that stopped running cases (run == the lines printed),
a case that ran and failed (fail == 0), and a harness that threw before its
summary (exit 0 and a PASS verdict).
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HARNESS = REPO / "tools" / "client-rules-harness" / "client-rules-harness.csproj"
MAIN_CS = REPO / "tools" / "client-rules-harness" / "Main.cs"

SUMMARY = re.compile(
    r"^(\w[\w-]*)(?: suites=\d+)? run=(\d+) fail=(\d+) verdict=(\w+)$", re.M)


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
        [dotnet, "run", "--project", str(HARNESS), "-c", "Release", "--"],
        cwd=str(REPO), capture_output=True, text=True, timeout=900,
    )
    return proc


def _suites(proc):
    return {m.group(1): (int(m.group(2)), int(m.group(3)), m.group(4))
            for m in SUMMARY.finditer(proc.stdout)}


def test_the_harness_ran_at_all(harness_run):
    assert harness_run.returncode == 0, (
        "client-rules-harness exited %d\n--- stdout ---\n%s\n--- stderr ---\n%s"
        % (harness_run.returncode, harness_run.stdout[-4000:], harness_run.stderr[-4000:]))
    suites = _suites(harness_run)
    assert "client-rules-harness" in suites, "no combined summary line was printed"
    _, fail, verdict = suites["client-rules-harness"]
    assert (fail, verdict) == (0, "PASS")


def test_the_log_scrub_suite_ran_every_case_and_none_failed(harness_run):
    suites = _suites(harness_run)
    assert "logscrub" in suites, "the LogScrub suite did not report"
    run, fail, verdict = suites["logscrub"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    # A suite that quietly stops running cases still prints fail=0. The
    # per-case lines are the independent count.
    printed = len(re.findall(r"^\[logscrub\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    # A floor, not an equality: cases get added. Below this, coverage that
    # exists today has been deleted.
    assert run >= 18, "the LogScrub suite shrank to %d cases" % run


def test_the_suite_carries_its_own_two_way_control(harness_run):
    """Every PASS above is a measurement of nothing unless the SAME corpus,
    unscrubbed, still counts residues. The suite's last case is that control
    and it prints both numbers."""
    line = [l for l in harness_run.stdout.splitlines() if "CONTROL unscrubbed=" in l]
    assert line, "the corpus control no longer runs"
    m = re.search(r"unscrubbed=(-?\d+) scrubbed=(-?\d+)", line[0])
    assert m, line[0]
    assert int(m.group(1)) > 0, "the residue counter saw nothing to remove -- it is blind"
    assert int(m.group(2)) == 0, "residues survived the scrub"
    assert line[0].startswith("[logscrub] PASS")


def _cases(proc):
    """(verdict, input, output) per printed LogScrub case.

    Matched on the case's INPUT, never on its output. The identifier cases
    exist to prove a token SURVIVES the scrub, so searching the output for that
    token is a check that cannot fail: the mutation those cases exist to catch
    is exactly the one that removes it, and a line that no longer contains it
    then reads as "no such case" rather than as a failure.
    """
    out = []
    for line in proc.stdout.splitlines():
        if not line.startswith("[logscrub] "):
            continue
        if " | in=" not in line or " | out=" not in line:
            continue
        head, rest = line.split(" | in=", 1)
        given, produced = rest.split(" | out=", 1)
        out.append((head, given, produced))
    return out


def test_the_identifier_cases_are_in_the_corpus(harness_run):
    """The shapes an over-wide word boundary used to eat. They are NEGATIVE
    cases: the scrub must leave them byte-identical.

    The one-sided ones matter as much as the surrounded ones. A case with a
    joiner on BOTH sides survives a widening of either boundary alone, so it
    cannot tell which side broke; the last four touch the name on one side
    each, so a widened LEADING boundary reds two of them and a widened TRAILING
    boundary reds the other two.
    """
    cases = _cases(harness_run)
    assert cases, "no case lines were printed -- the reader stopped measuring"
    for needle in ("cr_testuser_ready", "Landfall.testuser.Config", "map-testuser-3",
                   "testuser_ready", "testuser.log", "cr_testuser", "map-testuser"):
        hits = [c for c in cases if needle in c[1]]
        assert hits, "no case covers %r" % needle
        for head, given, produced in hits:
            assert head.startswith("[logscrub] PASS"), "%s | in=%s" % (head, given)
            assert " reps=0" in head, (
                "%r was rewritten by the bare-name pass: %s" % (needle, head))
            assert needle in produced, (
                "%r did not survive the scrub: %r" % (needle, produced))


def test_the_harness_compiles_only_the_rule_files():
    """A default compile glob would drag in the whole plugin tree, which does
    not build without Unity -- and would make this harness quietly untestable.
    """
    csproj = HARNESS.read_text(encoding="utf-8")
    assert "<EnableDefaultCompileItems>false</EnableDefaultCompileItems>" in csproj
    included = re.findall(r'<Compile Include="([^"]+)"', csproj)
    assert "Main.cs" in included
    assert any(p.endswith("plugin/LogScrub.cs") for p in included)
