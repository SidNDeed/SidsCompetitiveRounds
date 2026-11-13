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

The review of 13 Nov 2026 found two more (a run that never reached its launch exported the log of an earlier
session, A-H1; a sentinel that could not be removed left the restore proof standing, A-H2) and two smaller ones (a
line end that only the parser read, A-M1; a last line whose failed write changed no exit code, A-M2). The script's
self-test holds each rule beside its negative control; this file reads those runs' own lines the same way
(check_review), and holds the seat's line ends equal to the set str.splitlines() ends a line at, which is how
ft_parse.py reads what the seat exports.

Needs PowerShell (skipped where there is none), except the line-end comparison, which reads the script's text. It
starts stand-in child processes only: no game, lane or job file.
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


# ---- the review of 13 Nov 2026

def py_line_ends():
    """The characters at which str.splitlines() ends a line, found by trying every code point."""
    return sorted(c for c in map(chr, range(0x110000)) if len(("a" + c + "b").splitlines()) == 2)


def seat_line_ends(src):
    """(pattern, members) of the seat script's $LineEnds in SRC: CRLF first, then one character class."""
    m = re.search(r"^\$LineEnds = '([^'\r\n]*)'\r?$", src, re.M)
    assert m, "no $LineEnds line of the form"
    pat = m.group(1)
    head = "\\r\\n|["
    assert pat.startswith(head) and pat.endswith("]"), pat
    body = pat[len(head):-1]
    toks = re.findall(r"\\n|\\r|\\x[0-9a-f]{2}|\\u[0-9a-f]{4}", body)
    assert "".join(toks) == body, "a member of $LineEnds is of no known form: %r" % body
    return pat, sorted("\n" if t == "\\n" else "\r" if t == "\\r" else chr(int(t[2:], 16)) for t in toks)


def test_the_seat_ends_lines_where_the_parser_does():
    pat, members = seat_line_ends(open(PS1, encoding="utf-8", newline="").read())
    ends = py_line_ends()
    assert members == ends, (members, ends)
    # the pattern itself, read by Python: a text with every line end in it splits as splitlines() splits it
    sample = "p" + "".join(c + "q%d" % i for i, c in enumerate(ends)) + "\r\nlast"
    assert re.split(pat, sample) == sample.splitlines()


def test_the_line_end_comparison_refuses_a_set_that_lacks_one():
    src = open(PS1, encoding="utf-8", newline="").read()
    assert "\\x85" in seat_line_ends(src)[0]
    _, members = seat_line_ends(src.replace("\\x85", "", 1))
    assert members != py_line_ends()


# run name -> the fields its line must show; a control shows what the rule's absence gives
REVIEW_WANT = [
    ("stale_arm", {"code": "3", "launches": 0, "lane": 0, "not_read": 1, "proof_ok": 1, "proof_failed": 0,
                   "sentinel": "absent", "there": "False"}),
    ("stale_fresh", {"code": "3", "launches": 0, "lane": 0, "not_read": 1, "proof_ok": 1, "proof_failed": 0,
                     "sentinel": "absent", "there": "False"}),
    ("stale_read", {"launches": 0, "not_read": 0}),
    ("arm_stays", {"code": "5", "launches": 1, "proof_ok": 0, "proof_failed": 1,
                   "sentinel": "PRESENT (the seat is armed)", "there": "True"}),
    ("arm_stays_once", {"code": "3", "launches": 1, "proof_ok": 1, "proof_failed": 0, "sentinel": "absent",
                        "there": "False"}),
    ("arm_stays_lax", {"launches": 1, "proof_ok": 1, "proof_failed": 0, "there": "True"}),
]
REVIEW_COUNTS = [("line ends", "lf_only", 8), ("exit line", "exit_unchecked", 6)]

_REVIEW = re.compile(
    r"^self-test review (?P<name>[a-z_]+): code (?P<code>\S+), launches (?P<launches>\d+), lane lines printed "
    r"(?P<lane>\d+), 'not read' lines (?P<not_read>\d+), proof ok (?P<proof_ok>\d+) FAILED (?P<proof_failed>\d+), "
    r"sentinel line 'sentinel after the restore: (?P<sentinel>[^']*)', sentinel there after (?P<there>True|False), "
    r"files as before (?P<files_back>True|False), threw '(?P<threw>.*)'$")


def check_review(lines):
    """Every way the self-test's lines for the review of 13 Nov 2026 are not the runs meant: a list of sentences."""
    f = []
    for what, control, n in REVIEW_COUNTS:
        clean = [x for x in lines if x.startswith("self-test %s none: " % what)]
        ctl = [x for x in lines if x.startswith("self-test %s %s: " % (what, control))]
        if clean != ["self-test %s none: %d cases, 0 differ" % (what, n)]:
            f.append("%s: the clean line is %r" % (what, clean))
        if len(ctl) != 1 or not re.match(r"^self-test %s %s: %d cases, [1-9][0-9]* differ: " % (what, control, n),
                                         ctl[0]):
            f.append("%s: the control's line is %r: no case differs under %s" % (what, ctl, control))
    runs = []
    for ln in lines:
        if ln.startswith("self-test review "):
            m = _REVIEW.match(ln)
            runs.append((m.group("name"), m.groupdict()) if m else ("?", {"line": ln}))
    if [n for n, _ in runs] != [n for n, _ in REVIEW_WANT]:
        f.append("the review runs are %r, not %r" % ([n for n, _ in runs], [n for n, _ in REVIEW_WANT]))
        return f
    got = dict(runs)
    for name, want in REVIEW_WANT:
        d = got[name]
        if d["files_back"] != "True" or d["threw"] != "":
            f.append("%s: files as before %s, threw %r" % (name, d["files_back"], d["threw"]))
        for k, v in want.items():
            have = int(d[k]) if isinstance(v, int) else d[k]
            if have != v:
                f.append("%s: %s is %r, not %r" % (name, k, have, v))
    if int(got["stale_read"]["lane"]) < 1:
        f.append("stale_read printed no lane line: the control did not flip")
    if got["arm_stays"]["proof_ok"] == got["arm_stays_lax"]["proof_ok"]:
        f.append("arm_stays and arm_stays_lax end alike: the control did not flip")
    return f


@pytest.fixture(scope="module")
def selftest_output():
    p = subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS1, "-SelfTest"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
    out = p.stdout.decode("utf-8", "replace").replace("\r", "").split("\n")
    return p.returncode, out, p.stderr.decode("utf-8", "replace")


@need_ps
def test_selftest_holds_the_review_rules_beside_their_controls(selftest_output):
    rc, out, err = selftest_output
    f = check_review(out)
    assert rc == 0 and "SELFTEST PASS" in out and f == [], "\n".join(
        f + [x for x in out if x.startswith(("self-test review ", "self-test line ends ", "self-test exit line ",
                                             "SELFTEST"))]) + err[-800:]
    # no case's own last line reached the self-test's output
    assert [x for x in out if x.startswith("SEAT EXIT ")] == []


def _review_good():
    out = ["self-test line ends none: 8 cases, 0 differ", "self-test line ends lf_only: 8 cases, 2 differ: x",
           "self-test exit line none: 6 cases, 0 differ", "self-test exit line exit_unchecked: 6 cases, 3 differ: x"]
    base = {"code": "3", "launches": 0, "lane": 0, "not_read": 0, "proof_ok": 1, "proof_failed": 0,
            "sentinel": "absent", "there": "False"}
    for name, want in REVIEW_WANT:
        d = dict(base)
        d.update(want)
        if name == "stale_read":
            d["lane"] = 9
        out.append("self-test review %s: code %s, launches %d, lane lines printed %d, 'not read' lines %d, proof ok %d "
                   "FAILED %d, sentinel line 'sentinel after the restore: %s', sentinel there after %s, files as "
                   "before True, threw ''" % (name, d["code"], d["launches"], d["lane"], d["not_read"], d["proof_ok"],
                                              d["proof_failed"], d["sentinel"], d["there"]))
    return out


def test_check_review_takes_the_wanted_output():
    assert check_review(_review_good()) == []


@pytest.mark.parametrize("what", ["a run is missing", "a wrong code", "the stale control did not flip",
                                  "the sentinel control did not flip", "a count control with no difference",
                                  "a clean count line that differs"])
def test_check_review_refuses(what):
    out = _review_good()
    if what == "a run is missing":
        out = [x for x in out if not x.startswith("self-test review arm_stays_once:")]
    elif what == "a wrong code":
        out[7] = out[7].replace("code 5,", "code 3,")
    elif what == "the stale control did not flip":
        out[6] = out[6].replace("lane lines printed 9,", "lane lines printed 0,")
    elif what == "the sentinel control did not flip":
        out[9] = out[9].replace("proof ok 1 FAILED 0", "proof ok 0 FAILED 1")
    elif what == "a count control with no difference":
        out[1] = "self-test line ends lf_only: 8 cases, 0 differ"
    elif what == "a clean count line that differs":
        out[2] = "self-test exit line none: 6 cases, 1 differ: x"
    assert check_review(out) != [], what
