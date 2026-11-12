"""test_ft_seat_flow.py: frame_time_seat.ps1 -FlowTest, the sitting's own launch, wait, shutdown and game-end
functions on a stand-in game.

The review of 12 Nov 2026 found four ways the seat script could end a sitting wrongly, none of which a test ran: a
log left by an earlier launch read as this launch's (D-H1), a game that had not ended with nothing changed by it
(D-H2), a game that showed after the launch's last reading and was left running, or a launch that showed none at all
(D-H3); and it noted that the completion path itself (the end line ends the wait) had never run in a test. -FlowTest
runs the real functions through Sitting on a child PowerShell that stands in for the game, one run per case and one
per negative control, and judges itself: FLOWTEST PASS, or "FLOWTEST FAIL: ...".

This file holds that verdict, and reads every run's own line besides, so that the verdict cannot pass on other runs
than the nine meant: each run's name, its exit code and its proof word, and the flip of every control (a control
that ends like its clean case is a rule that is not tested). check_flow is tried on changed outputs as well: it must
refuse a missing run, a wrong code and a control that did not flip.

Needs PowerShell (skipped where there is none). It starts stand-in child processes only: no game, lane or job file.
"""
import os
import re
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(HERE, "frame_time_seat.ps1")
PS = shutil.which("powershell") or shutil.which("pwsh")
need_ps = pytest.mark.skipif(PS is None, reason="no PowerShell on this seat (neither powershell nor pwsh on PATH): "
                             "frame_time_seat.ps1 -FlowTest cannot run here")

# run name -> the fields its line must show. A control (name with a mutant) shows what the rule's absence gives.
WANT = [
    ("complete", {"code": "0", "complete_true": 1, "proof_ok": 1, "proof_failed": 0, "log_removed": 1,
                  "exited_true": 1, "end_0": 1, "after_0": 1, "ended_by_test": 0}),
    ("stale", {"code": "3", "complete_true": 0, "complete_false": 1, "proof_ok": 1, "proof_failed": 0,
               "log_removed": 1}),
    ("stale-keep_log", {"code": "0", "complete_true": 1, "log_removed": 0}),
    ("stuck", {"code": "5", "exited_false": 1, "end_left": 1, "was_left": 1, "after_0": 0, "proof_ok": 0,
               "proof_failed": 1, "ended_by_test": 1}),
    ("stuck-no_game_end", {"code": "3", "proof_ok": 1, "proof_failed": 0, "ended_by_test": 1}),
    ("late", {"code": "3", "no_launch": 1, "late_capture": 1, "exited_true": 1, "end_0": 1, "proof_ok": 1,
              "proof_failed": 0, "ended_by_test": 0}),
    ("late-no_late", {"code": "5", "late_capture": 0, "no_show": 1, "proof_ok": 0, "proof_failed": 1}),
    ("never", {"code": "5", "no_launch": 1, "no_pid": 1, "no_show": 1, "proof_ok": 0, "proof_failed": 1}),
    ("never-seen_lax", {"code": "3", "no_show": 0, "proof_ok": 1, "proof_failed": 0}),
]
# clean case -> its control: the two must differ in exit code and in the proof word
PAIRS = [("stale", "stale-keep_log"), ("stuck", "stuck-no_game_end"), ("late", "late-no_late"),
         ("never", "never-seen_lax")]

_LINE = re.compile(
    r"^flow-test (?P<name>[a-z_-]+): code (?P<code>\S+), complete True (?P<complete_true>\d+) False "
    r"(?P<complete_false>\d+), proof ok (?P<proof_ok>\d+) FAILED (?P<proof_failed>\d+), log removed "
    r"(?P<log_removed>\d+), no launch (?P<no_launch>\d+), late capture (?P<late_capture>\d+), no pid (?P<no_pid>\d+), "
    r"exited True (?P<exited_true>\d+) False (?P<exited_false>\d+), end 0 (?P<end_0>\d+) left (?P<end_left>\d+), "
    r"after 0 (?P<after_0>\d+), no show (?P<no_show>\d+), was left (?P<was_left>\d+), files as before "
    r"(?P<files_back>True|False), stand-ins ended by the test (?P<ended_by_test>\d+), threw '(?P<threw>.*)'$")


def parse_runs(lines):
    """The flow-test run lines of an output, in order: [(name, {field: value})]; a line that starts 'flow-test ' and
    is neither a run line of the form nor the scratch line is returned under the name '?'."""
    runs = []
    for ln in lines:
        if not ln.startswith("flow-test ") or ln.startswith("flow-test scratch: "):
            continue
        m = _LINE.match(ln)
        if not m:
            runs.append(("?", {"line": ln}))
            continue
        d = m.groupdict()
        for k in d:
            if k not in ("name", "code", "files_back", "threw"):
                d[k] = int(d[k])
        runs.append((d["name"], d))
    return runs


def check_flow(rc, lines):
    """Every way the output of -FlowTest is not the nine runs meant, each ending as WANT says: a list of sentences,
    empty when it is."""
    f = []
    verdict = [x for x in lines if x == "FLOWTEST PASS" or x.startswith("FLOWTEST FAIL: ")]
    if rc != 0 or verdict != ["FLOWTEST PASS"]:
        f.append("the verdict is %r with exit code %r, not one FLOWTEST PASS with 0" % (verdict, rc))
    runs = parse_runs(lines)
    names = [n for n, _ in runs]
    if names != [n for n, _ in WANT]:
        f.append("the runs are %r, not %r" % (names, [n for n, _ in WANT]))
        return f
    got = dict(runs)
    for name, want in WANT:
        d = got[name]
        if d["files_back"] != "True" or d["threw"] != "":
            f.append("%s: files as before %s, threw %r" % (name, d["files_back"], d["threw"]))
        for k, v in want.items():
            if d[k] != v:
                f.append("%s: %s is %r, not %r" % (name, k, d[k], v))
    for clean, control in PAIRS:
        a, b = got[clean], got[control]
        if a["code"] == b["code"] or (a["proof_ok"], a["complete_true"]) == (b["proof_ok"], b["complete_true"]):
            f.append("%s and %s end alike (code %s and %s): the control did not flip" % (clean, control, a["code"],
                                                                                         b["code"]))
    return f


@pytest.fixture(scope="module")
def flow_output():
    p = subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS1, "-FlowTest"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
    out = p.stdout.decode("utf-8", "replace").replace("\r", "").split("\n")
    return p.returncode, out, p.stderr.decode("utf-8", "replace")


@need_ps
def test_flowtest_passes_with_the_nine_runs(flow_output):
    rc, out, err = flow_output
    f = check_flow(rc, out)
    assert f == [], "\n".join(f + [x for x in out if x.startswith("flow-test ") or x.startswith("FLOWTEST")]) + err[-800:]


@need_ps
def test_flowtest_leaves_no_stand_in_and_no_error_text(flow_output):
    rc, out, err = flow_output
    assert err.strip() == "", err[-1500:]
    # every run printed its sitting's proof line, and the mode's last line is its verdict
    assert len([x for x in out if x.startswith("RESTORE-PROOF ")]) == len(WANT), [x for x in out if x.startswith("RESTORE-PROOF ")]
    assert [x for x in out if x.strip()][-1] == "FLOWTEST PASS"


def _line(name, **over):
    d = {"code": "0", "complete_true": 0, "complete_false": 0, "proof_ok": 0, "proof_failed": 0, "log_removed": 1,
         "no_launch": 0, "late_capture": 0, "no_pid": 0, "exited_true": 0, "exited_false": 0, "end_0": 0,
         "end_left": 0, "after_0": 1, "no_show": 0, "was_left": 0, "files_back": "True", "ended_by_test": 0,
         "threw": ""}
    d.update(dict(WANT)[name])
    d.update(over)
    return ("flow-test %s: code %s, complete True %d False %d, proof ok %d FAILED %d, log removed %d, no launch %d, "
            "late capture %d, no pid %d, exited True %d False %d, end 0 %d left %d, after 0 %d, no show %d, was left "
            "%d, files as before %s, stand-ins ended by the test %d, threw '%s'"
            % (name, d["code"], d["complete_true"], d["complete_false"], d["proof_ok"], d["proof_failed"],
               d["log_removed"], d["no_launch"], d["late_capture"], d["no_pid"], d["exited_true"], d["exited_false"],
               d["end_0"], d["end_left"], d["after_0"], d["no_show"], d["was_left"], d["files_back"],
               d["ended_by_test"], d["threw"]))


def _good():
    return [_line(n) for n, _ in WANT] + ["flow-test scratch: somewhere", "FLOWTEST PASS"]


def test_check_flow_takes_the_wanted_output():
    assert check_flow(0, _good()) == []


@pytest.mark.parametrize("what", ["a run is missing", "a wrong code", "a control did not flip", "a failed verdict",
                                  "files not put back", "a line out of its form", "an extra run"])
def test_check_flow_refuses(what):
    out = _good()
    rc = 0
    if what == "a run is missing":
        out = [x for x in out if not x.startswith("flow-test stuck:")]
    elif what == "a wrong code":
        out[3] = _line("stuck", code="3")
    elif what == "a control did not flip":
        out[2] = _line("stale-keep_log", code="3", complete_true=0, proof_ok=1)
        out[1] = _line("stale", proof_ok=1)
    elif what == "a failed verdict":
        out[-1] = "FLOWTEST FAIL: stuck: a game that did not end was not refused"
        rc = 6
    elif what == "files not put back":
        out[0] = _line("complete", files_back="False")
    elif what == "a line out of its form":
        out[5] = out[5].replace(", late capture 1,", ", late 1,")
    elif what == "an extra run":
        out.insert(9, _line("never"))
    assert check_flow(rc, out) != [], what
