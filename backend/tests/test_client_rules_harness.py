"""Runs the client rule self-tests. Not a source-shape gate - an execution.

`plugin/LogScrub.cs` and `plugin/TopStripBand.cs` are kept free of Unity,
Photon and BepInEx so that what a log bundle stops carrying, and which y each
surface gets when several paint in the top-centre column at once, can be
EXECUTED rather than asserted about as source text -- the arrangement
`tools/h2h-harness` already uses for H2HRules, and the reason LogScrub's own
class comment gives for the shape it is written in. Until now nothing in the
repository ran the scrub: its self-test existed behind a Debug config lever
that fires once at startup on a developer's machine, so its numbers were not
reproducible from a checkout and no pytest run ever touched them. The column
allocator had no self-test at all -- it stored a plain maximum for a job that
needed a layout, and the only gate over it read the source.

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


def test_the_top_strip_suite_ran_every_case_and_none_failed(harness_run):
    suites = _suites(harness_run)
    assert "topstrip" in suites, "the TopStripBand suite did not report"
    run, fail, verdict = suites["topstrip"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[topstrip\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    assert run >= 14, "the TopStripBand suite shrank to %d cases" % run


def test_the_ffa_report_suite_ran_every_case_and_none_failed(harness_run):
    suites = _suites(harness_run)
    assert "ffareport" in suites, "the FfaReportRules suite did not report"
    run, fail, verdict = suites["ffareport"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[ffareport\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    assert run >= 15, "the FfaReportRules suite shrank to %d cases" % run


def _named_case(proc, name, suite="topstrip"):
    """One case line, matched on its NAME.

    Safe to match on the name here (unlike the LogScrub cases, which are
    matched on their input): every case prints its name whatever its verdict,
    so a mutation that breaks the case reds it rather than making it vanish.
    """
    hits = [l for l in proc.stdout.splitlines()
            if l.startswith("[" + suite + "] ") and (" | case=" + name + " |") in l]
    assert len(hits) == 1, "expected one %r case, found %d" % (name, len(hits))
    return hits[0]


def test_two_electors_file_one_ffa_game_under_one_key(harness_run):
    """The HIGH this suite exists for.

    The election can return two reporters, deliberately: a seat that has
    received no witness property falls back while its peers do not, because
    nobody reporting loses the sitting outright. That is only survivable if
    the server can SEE the duplicate, and the key used to carry each seat's
    own clock and its own game counter -- so the two reports collided with
    nothing and one game settled twice.

    Asserted on the printed keys, not on the verdict: a case that stopped
    comparing would still say PASS.
    """
    line = _named_case(harness_run, "two seats agree on the key", "ffareport")
    assert line.startswith("[ffareport] PASS"), line
    got = line.split(" | got=", 1)[1]
    m = re.match(r"^a=(\S+) b=(\S+)$", got.strip())
    assert m, got
    assert m.group(1) == m.group(2), "the two seats produced different keys: " + got
    assert re.search(r"_r\d+$", m.group(1)), (
        "the key lost the suffix the server parses: " + m.group(1))


def test_the_report_key_still_satisfies_the_server_contract(harness_run):
    """backend/api/main.py's _ffa_room_game_no pulls the game number out of
    this key with an anchored `_r(\\d+)$` and settles that game's bets on it.
    A key ending any other way falls back to "games_played + 1", which settles
    the wrong game's wagers on an out-of-order report -- and nothing errors."""
    line = _named_case(harness_run, "the server can recover the game number", "ffareport")
    assert line.startswith("[ffareport] PASS"), line
    assert "value=11" in line, (
        "the server's own regex no longer recovers the number the key carries: " + line)
    # And the same regex the server uses, evaluated here on the production
    # source rather than on a copy of it.
    server = (REPO / "backend" / "api" / "main.py").read_text(encoding="utf-8")
    assert r'_re.search(r"_r(\d+)$", room_id or "")' in server, (
        "the server's room-id parser moved; the client key must move with it")


@pytest.mark.parametrize("name", [
    "the key is a pure function of its inputs",
    "the published number wins when behind",
    "absent published number falls back to local",
    "different games get different keys",
    "the key fits the column",
    "degenerate inputs still produce a legal key",
    "election is total without witnesses",
    "witnesses are the electorate",
    "election is order-independent",
    "an empty room elects nobody",
    "an unparseable electorate still elects one seat",
    "one parseable id outranks the ordinal fallback",
    "a settled refusal is recognised, a neighbour is not",
])
def test_the_ffa_report_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name, "ffareport")
    assert line.startswith("[ffareport] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


def test_the_column_lays_simultaneous_surfaces_out_disjointly(harness_run):
    """The MEDIUM this suite exists for: six surfaces painting in the same
    frame used to be given the same y, because the column stored only the
    maximum bottom edge. Asserted on the case's printed MEASUREMENT, not on its
    verdict alone -- a case that stopped measuring would otherwise still say
    PASS."""
    line = _named_case(harness_run, "six claimants are disjoint")
    assert line.startswith("[topstrip] PASS"), line
    got = line.split(" | got=", 1)[1]
    ys = [float(v) for v in got.split(",")]
    assert len(ys) == 6, got
    assert ys == sorted(ys) and len(set(ys)) == 6, (
        "the claimants were not given six distinct increasing positions: " + got)
    assert ys[0] == 0.0, "the first claimant no longer starts at the top: " + got


@pytest.mark.parametrize("name", [
    "two claims stack",
    "short close does not climb back",
    "close does not undo a claim made inside the band",
    "empty open band consumes nothing",
    "painted open band advances",
    "NaN claim consumes nothing",
    "band does not survive a frame tick",
    "stale frame reads zero",
])
def test_the_column_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name)
    assert line.startswith("[topstrip] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


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
    for rule_file in ("plugin/LogScrub.cs", "plugin/TopStripBand.cs",
                      "plugin/FfaReportRules.cs"):
        assert any(p.endswith(rule_file) for p in included), (
            "%s is not compiled into the harness" % rule_file)
