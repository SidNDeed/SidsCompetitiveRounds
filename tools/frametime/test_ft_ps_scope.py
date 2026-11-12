"""test_ft_ps_scope.py: no assignment to a name its scope already holds, and the seat entries' exit code.

The fault these tests hold (sitting V's first try, 12 Nov 2026): frame_time_seat.ps1 assigned the culture gate's result
to $cultureGate at its top level, where [switch]$CultureGate is a parameter (PowerShell names are case-insensitive).
The assignment is a conversion error there, the script ended one second after its start, and the sitting-V entry then
ended with exit code 0. No test had run that line: the sitting's top level runs only on a seat with a staged lane.

(a) THE CLASS, by machine: ft_ps_scope_check.ps1 reads a file with PowerShell's parser and lists every write
    (assignment, foreach variable, ++/--, a variable cmdlet or a common variable parameter with a literal name) whose
    target is a parameter of the scope chain it runs in (script block literals end no walk; a function does), or a
    name PowerShell holds constant or read-only; every block parameter bound over such a parameter; every [ref] to
    one; every parameter named as a held name; and one SCOPE-UNREAD line per construct it cannot read through. It
    follows dot-sourced files, recursively, into the scope that sources them. Every *.ps1 of this folder is read, and
    the findings must be exactly JUDGED (each one read and listed with its reason), so a new one fails here; the
    flow line of the seat script and of both entries is pinned (no stray break or continue, no top-level return, an
    exit statement last). Each planted fault must be found at its line, each control must be clean, each case of a
    rule added after ca9f945b must read clean under the checker of ca9f945b (its negative control), the seat script
    with the correction reverted must show the fault of 12 Nov at its line, and a file that is absent or does not
    parse, or a dot-source statement that cannot be followed, is refused, never passed. RUNTIME runs four small
    scripts for real: PowerShell ends the three whose assignment it refuses, and passes the fourth (an untyped
    parameter: listed, no error).
(b) THE ENTRIES: frame_time_seat_v.ps1 and frame_time_seat_trial.ps1, each run for real beside a stand-in
    frame_time_seat.ps1. A stand-in that dies of the same fault gives exit code 1 and a SEAT-SCRIPT-ERROR line; the
    entry as it was before the correction ends 0 on that stand-in (the negative control). A stand-in that ends
    without a code, or by a stray break, gives 1 (an entry without the loop ends 0 on the break: its control). A
    stand-in that runs a labelled break or continue whose label names no loop gives 1 and the control-transfer line
    (the entry of ca9f945b ends 0 on it: its control). A stand-in's exit code is passed on, the arguments are the
    entry's own, and without the seat script beside it the entry refuses with exit 2.
Where neither powershell nor pwsh exists the tests that run PowerShell SKIP with that reason.
"""
import glob
import os
import re
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "ft_ps_scope_check.ps1")
SEAT = os.path.join(HERE, "frame_time_seat.ps1")
PS = shutil.which("powershell") or shutil.which("pwsh")
need_ps = pytest.mark.skipif(PS is None, reason="no PowerShell on this seat (neither powershell nor pwsh on PATH): "
                             "the scope check and the seat entries run only there")

GIT_REV = "ca9f945b"
FINDING = re.compile(r"^SCOPE-ASSIGN (.+):(\d+) \$(\S+) is (?:assigned|bound as a parameter of the script block at "
                     r"line \d+) in the scope of its own parameter \[(.+?)\]\$(\S+) \((.+)\)$")
HELD = re.compile(r"^SCOPE-CONST (.+):(\d+) \$(\S+) is (?:assigned|a parameter), and this PowerShell holds \$(\S+) "
                  r"(.+) \(([^()]+)\)$")
REF = re.compile(r"^SCOPE-REF (.+):(\d+) \[ref\]\$(\S+) takes a reference to (.+)$")
UNREAD = re.compile(r"^SCOPE-UNREAD (.+):(\d+) (.+)$")
FLOW = re.compile(r"^SCOPE-FLOW (.+) stray (\d+) top-returns (\d+) last (exit|other)$")
CONTROL_LINE = "SEAT-SCRIPT-ERROR: frame_time_seat.ps1 ended by a control transfer that left the entry"

# the assignments to a parameter in its own scope that this folder holds on purpose: (file, parameter, the source
# line stripped, the reason it is no fault). Each assigns a value of the parameter's own type.
JUDGED = [
    ("frame_time_seat.ps1", "t", "if ($bare) { $t = $t.Substring(1) }",
     "a string parameter shortened to its own substring"),
    ("frame_time_seat.ps1", "ArmForce", "$ArmForce = $(if ($m -eq 'arm_force_on') { 'ON' } else { 'none' })",
     "the self-test sets the parameter to one of its two allowed words for a run"),
    ("frame_time_seat.ps1", "ArmForce", "finally { $ArmForce = $armForceGiven }",
     "the self-test puts the given word back"),
    ("ft_close_leased.ps1", "BoundMs", "if ($BoundMs -le 0) { $BoundMs = $script:FtCloseBoundMs }",
     "an int parameter takes the library's int default"),
    ("ft_settle_diskq.ps1", "IntervalS", "if (-not $PSBoundParameters.ContainsKey('IntervalS')) { $IntervalS = 0 }",
     "an int parameter set to 0 for the dry controls"),
]

# (name, the file's text, the line of the planted assignment, the name as the assignment writes it, the type shown)
PLANTED = [
    ("the fault of 12 Nov in small", "param([switch]$CultureGate)\n$cultureGate = @{ Lines = @('x') }\n", 2,
     "cultureGate", "switch"),
    ("a function's parenthesised parameter", "function F([int]$N) {\n    $n = 'a'\n}\n", 2, "n", "int"),
    ("a foreach variable in a function with a param block",
     "function G {\n    param([string]$S)\n    foreach ($s in 1..2) { }\n}\n", 3, "s", "string"),
    ("a pipeline block, counted under the scope around it",
     "param([switch]$Flag)\n1..2 | ForEach-Object { $flag = @{} }\n", 2, "flag", "switch"),
    ("$script: from inside a function", "param([switch]$Flag)\nfunction H { $script:flag = 1 }\n", 2, "flag",
     "switch"),
    ("a cast on the target", "param([string]$Name)\n[int]$name = 5\n", 2, "name", "string"),
    ("a list of targets", "param([int]$A)\n$x, $a = 1, 2\n", 2, "a", "int"),
    ("a compound assignment", "param([string]$S)\n$s += 'x'\n", 2, "s", "string"),
    ("an untyped parameter", "param($X)\n$x = 1\n", 2, "x", "untyped"),
    ("a block in a block, both without a param block", "param([int]$N)\n$b = { 1 | ForEach-Object { $n = 'a' } }\n",
     2, "n", "int"),
]

# the cases of the rules added after ca9f945b (same shape as PLANTED); each is also run under the checker of
# ca9f945b, which must read it clean (the negative control)
NEW_PLANTED = [
    ("a block with a param block of its own, held against the scope around it",
     "param([switch]$Flag)\n$b = { param($x) $flag = 1 }\n", 2, "flag", "switch"),
    ("a ForEach-Object block with a param block",
     "param([switch]$Flag)\n1..2 | ForEach-Object { param($x) $flag = @{} }\n", 2, "flag", "switch"),
    ("a block with a param block in a function, held against the function's parameter",
     "function F([int]$N) {\n    1 | ForEach-Object { param($x) $n = 'a' }\n}\n", 2, "n", "int"),
    ("a postfix ++", "param([string]$S)\n$s++\n", 2, "s", "string"),
    ("a postfix --", "param([string]$S)\n$s--\n", 2, "s", "string"),
    ("a prefix ++", "param([string]$S)\n++$s\n", 2, "s", "string"),
    ("a prefix --", "param([string]$S)\n--$s\n", 2, "s", "string"),
    ("Set-Variable with -Name", "param([int]$N)\nSet-Variable -Name n -Value 'a'\n", 2, "n", "int"),
    ("sv with a positional name", "param([int]$N)\nsv 'n' 'a'\n", 2, "n", "int"),
    ("New-Variable with -Name:", "param([int]$N)\nNew-Variable -Name:n -Value 'a' -Force\n", 2, "n", "int"),
    ("Remove-Variable after a switch", "param([int]$N)\nRemove-Variable -Force n\n", 2, "n", "int"),
    ("Set-Variable -Scope Script from a function",
     "param([int]$N)\nfunction F { Set-Variable -Scope Script -Name n -Value 'a' }\n", 2, "n", "int"),
    ("-OutVariable with a leading +", "param([int]$N)\nGet-Item . -OutVariable +n\n", 2, "n", "int"),
    ("-ev", "param([int]$N)\nGet-Item . -ev n\n", 2, "n", "int"),
    ("-PipelineVariable by a prefix", "param([int]$N)\nGet-Item . -PipelineV n\n", 2, "n", "int"),
]

# a block parameter bound over a parameter of a scope around it: (name, text, line, name, block line, type)
BOUND = [
    ("a ForEach-Object block's parameter", "param([int]$N)\n1 | ForEach-Object { param($n) }\n", 2, "n", 2, "int"),
    ("a Where-Object block's parameter in a function",
     "function F([string]$S) {\n    1 | Where-Object {\n        param($s)\n    }\n}\n", 3, "s", 2, "string"),
]

# (name, the file's text, the line, the name as written, the name PowerShell holds)
PLANTED_HELD = [
    ("a constant at the top level", "$pid = 5\n", 1, "pid", "PID"),
    ("a constant inside a function", "function F {\n    $Host = 1\n}\n", 2, "Host", "Host"),
    ("a read-only name through $global:", "$global:home = 'x'\n", 1, "home", "HOME"),
]
NEW_HELD = [
    ("a constant through ++", "$pid++\n", 1, "pid", "PID"),
    ("a constant through Set-Variable", "Set-Variable -Name PID -Value 5\n", 1, "PID", "PID"),
    ("a function parameter named as a held name", "function F([string]$Home) { }\n", 1, "Home", "HOME"),
    ("a block parameter named as a held name", "$b = { param($pid) }\n", 1, "pid", "PID"),
]

# (name, the file's text, the line, the name, the start of what it is a reference to)
PLANTED_REF = [
    ("a reference to a parameter, written through", "param([int]$N)\n([ref]$n).Value = 'x'\n", 2, "n",
     "its own parameter [int]$N (the file's top level)"),
    ("a reference to a held name", "$r = [ref]$pid\n", 1, "pid", "$PID, which this PowerShell holds"),
    ("a reference through $script: from a function", "param([int]$N)\nfunction F { $r = [ref]$script:n }\n", 2, "n",
     "its own parameter [int]$N (the file's top level, through $script:)"),
]

# (name, the file's text, the line, the start of what is not read)
PLANTED_UNREAD = [
    ("a splatted argument", "$a = @{ Path = '.' }\nGet-Item @a\n", 2, "a splatted argument @a"),
    ("Set-Variable with a computed name", "$v = 'x'\nSet-Variable -Name $v -Value 1\n", 2,
     "Set-Variable: the variable it names is not read"),
    ("Remove-Variable with a wildcard", "Remove-Variable x*\n", 1, "Remove-Variable: the variable it names is not read"),
    ("New-Variable with a numbered scope", "New-Variable -Name x -Value 1 -Scope 1\n", 1,
     "New-Variable: the variable it names is not read"),
    ("a common variable parameter with a computed value", "$v = 'x'\nGet-Item . -OutVariable $v\n", 2,
     "-OutVariable: the variable it names is not read"),
    ("iex", "iex 'x'\n", 1, "Invoke-Expression: iex 'x'"),
    ("Invoke-Expression", "Invoke-Expression -Command 'x'\n", 1, "Invoke-Expression: Invoke-Expression"),
    ("[scriptblock]::Create", "$b = [scriptblock]::Create('x')\n", 1, "[scriptblock]::Create: "),
    ("ScriptBlock::create by its full name", "$b = [System.Management.Automation.ScriptBlock]::create('x')\n", 1,
     "[scriptblock]::Create: "),
]

# (name, the file's text): no finding
CONTROLS = [
    ("the same name in a called function (a scope of its own)",
     "param([switch]$Flag)\nfunction K { $flag = @{} }\n"),
    ("a block in a function: the function ends the walk",
     "param([switch]$Flag)\nfunction K { 1 | ForEach-Object { param($x) $flag = 1 } }\n"),
    ("a block with a param block whose names are free", "param([switch]$Flag)\n$b = { param($x) $y = 1 }\n"),
    ("a block parameter in a function, free there", "param([int]$N)\nfunction F { $b = { param($n) } }\n"),
    ("++ on a free name and on a member", "param([hashtable]$H)\n$m = 0\n$m++\n--$m\n$H.n++\n"),
    ("the variable cmdlets and common parameters on free names",
     "param([int]$N)\nSet-Variable -Name m -Value 1\nsv m 2\nGet-Item . -ov o -ErrorVariable +e\n"),
    ("a reference to a free name", "param([int]$N)\n$tokens = $null\n$r = [ref]$tokens\n"),
    ("an array subexpression and another static method", "$a = @(1)\n$b = [regex]::Escape('x')\n"),
    ("a parameter whose name only begins as a held one", "function F([string]$Hosts, [int]$Pids) { }\n"),
    ("a read of a parameter", "param([switch]$Flag)\nif ($Flag) { $x = $flag }\n"),
    ("a member and an index target", "param([hashtable]$H)\n$H.a = 1\n$H['b'] = 2\n"),
    ("another scope word and a drive", "param([string]$Path)\n$global:path = 'x'\n$env:FT_SCOPE_TEST = 'y'\n"),
    ("the discard target and a drive name equal to a held one", "$null = 1\n$env:HOME = 'x'\n"),
]

_MAIN = "param([int]$BoundMs = 0)\n. (Join-Path $PSScriptRoot 'lib.ps1')\n"
# (name, main.ps1, lib.ps1, the findings wanted in lib.ps1 as (line, name, type), the scope named for them)
DOTS = [
    ("the sourced file's top level writes the sourcing file's parameter", _MAIN, "$x = 1\n$boundMs = 'sixty'\n",
     [(2, "boundMs", "int")], "the file's top level of "),
    ("the sourced file's function writes it through $script:", _MAIN, "function Set-It { $script:boundMs = 'x' }\n",
     [(1, "boundMs", "int")], "the file's top level of "),
    ("a dot-source inside a function", "function F([int]$N) {\n    . (Join-Path $PSScriptRoot 'lib.ps1')\n}\n",
     "$n = 'a'\n", [(1, "n", "int")], "function F of "),
    ("control: the sourced file's function holds the name as its own local", _MAIN,
     "function G { $boundMs = 'x' }\n$y = 2\n", [], ""),
]

_DOT = ". (Join-Path $PSScriptRoot '%s')\n"
# followed further, and held names in a followed file: (name, the files, the findings wanted as (kind, file, line,
# name, the start of the scope), the dot-sourced count, the exit code). Each is a case of a rule added after
# ca9f945b, so the checker of ca9f945b must read each clean.
NEW_DOTS = [
    ("a held name in the followed file, at its top level and in its function",
     {"main.ps1": _MAIN, "lib.ps1": "$pid = 5\nfunction G {\n    $Host = 1\n}\n"},
     [("CONST", "lib.ps1", 1, "pid", "the file's top level of "), ("CONST", "lib.ps1", 3, "Host", "function G of ")],
     1, 1),
    ("a file followed through a followed file",
     {"main.ps1": _MAIN, "lib.ps1": _DOT % "lib2.ps1", "lib2.ps1": "$x = 1\n$boundMs = 'sixty'\n"},
     [("ASSIGN", "lib2.ps1", 2, "boundMs", "the file's top level of ")], 2, 1),
    ("three levels, a $script: write at the end",
     {"main.ps1": _MAIN, "lib.ps1": _DOT % "lib2.ps1", "lib2.ps1": _DOT % "lib3.ps1",
      "lib3.ps1": "function S { $script:boundMs = 'x' }\n"},
     [("ASSIGN", "lib3.ps1", 1, "boundMs", "the file's top level of ")], 3, 1),
    ("a dot-source statement in a followed file's function: the nested file runs in that function",
     {"main.ps1": _MAIN, "lib.ps1": "function G([string]$S) {\n    " + _DOT % "lib2.ps1" + "}\n",
      "lib2.ps1": "$s = 1\n$boundMs = 'x'\n"},
     [("ASSIGN", "lib2.ps1", 1, "s", "function G of ")], 2, 1),
    ("a statement of another form in a followed file is refused",
     {"main.ps1": _MAIN, "lib.ps1": "$x = 'a'\n. $x\n"}, [], 1, 2),
]

# (name, the files, wanted lines from the checker): a cycle ends, each file of it read once
CYCLE = {"main.ps1": _MAIN, "lib.ps1": _DOT % "main.ps1" + _DOT % "lib.ps1" + "$boundMs = 1\n"}

# (name, the file's text, stray lines, top-returns, last): information only, never a finding
FLOWS = [
    ("an unlabelled break at the top level", "$x = 1\nbreak\nexit 0\n", [2], 0, "exit"),
    ("a labelled break whose label names no loop", "foreach ($a in 1) { break nolabel }\nexit 0\n", [1], 0, "exit"),
    ("a labelled continue whose label names a loop around it",
     ":outer foreach ($a in 1) { foreach ($b in 1) { continue outer } }\nexit 0\n", [], 0, "exit"),
    ("a break in a ForEach-Object block (a scope of its own)",
     "foreach ($a in 1) { 1 | ForEach-Object { break } }\nexit 0\n", [1], 0, "exit"),
    ("a continue in a function", "function F { continue }\nexit 0\n", [1], 0, "exit"),
    ("a break in a switch, a continue in a trap", "switch (1) { 1 { break } }\ntrap { continue }\nexit 0\n", [], 0,
     "exit"),
    ("a return at the top level, one in a function, one in a block",
     "function F { return 1 }\n$b = { return 2 }\nif ($true) { return }\n$x = 1\n", [], 1, "other"),
    ("an exit not last", "exit 0\nfunction F { }\n", [], 0, "other"),
]

_SAY = "[Console]::Out.WriteLine('%s')\n"
# (name, the files, whether PowerShell ends the script at the assignment)
RUNTIME = [
    ("a switch parameter's name",
     {"main.ps1": "param([switch]$CultureGate)\n$ErrorActionPreference = 'Stop'\n" + _SAY % "before"
      + "$cultureGate = @{ Lines = @('x') }\n" + _SAY % "after" + "exit 0\n"}, True),
    ("a constant's name",
     {"main.ps1": "$ErrorActionPreference = 'Stop'\n" + _SAY % "before" + "$pid = 5\n" + _SAY % "after"
      + "exit 0\n"}, True),
    ("a dot-sourced file writes the sourcing file's int parameter",
     {"main.ps1": "param([int]$BoundMs = 0)\n$ErrorActionPreference = 'Stop'\n" + _SAY % "before"
      + ". (Join-Path $PSScriptRoot 'lib.ps1')\n" + _SAY % "after" + "exit 0\n",
      "lib.ps1": "$boundMs = 'sixty'\n"}, True),
    ("an untyped parameter's name (listed, no error)",
     {"main.ps1": "param($X)\n$ErrorActionPreference = 'Stop'\n" + _SAY % "before" + "$x = 1\n" + _SAY % "after"
      + "exit 0\n"}, False),
]


def _ps(*argv):
    p = subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"] + list(argv),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    return (p.returncode, p.stdout.decode("utf-8", "replace").replace("\r", ""),
            p.stderr.decode("utf-8", "replace").replace("\r", ""))


def _check(*files):
    rc, out, err = _ps(CHECK, *files)
    return rc, [x for x in out.split("\n") if x], err


def _findings(lines):
    out = []
    for ln in lines:
        m = FINDING.match(ln)
        if m:
            out.append((m.group(1), int(m.group(2)), m.group(3), m.group(4), m.group(5), m.group(6)))
    return out


def _held(lines):
    out = []
    for ln in lines:
        m = HELD.match(ln)
        if m:
            out.append((m.group(1), int(m.group(2)), m.group(3), m.group(4), m.group(5), m.group(6)))
    return out


def _match(rx, lines):
    return [m.groups() for m in (rx.match(ln) for ln in lines) if m]


def _git_show(path):
    """a file as it stands at GIT_REV (bytes), read from this worktree's history"""
    p = subprocess.run(["git", "-C", HERE, "show", "%s:%s" % (GIT_REV, path)], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=60)
    assert p.returncode == 0 and p.stdout, (path, p.returncode, p.stderr[-300:])
    return p.stdout


def _old_check(folder, *files):
    """the checker as it stood at GIT_REV, run from a temp folder"""
    old = os.path.join(str(folder), "old_scope_check.ps1")
    if not os.path.exists(old):
        with open(old, "wb") as f:
            f.write(_git_show("tools/frametime/ft_ps_scope_check.ps1"))
    rc, out, err = _ps(old, *files)
    return rc, [x for x in out.split("\n") if x], err


def _assert_old_reads_clean(folder, main, name):
    rc, lines, err = _old_check(folder, main)
    assert rc == 0 and lines and lines[-1] == "SCOPE-CHECK-ALL files 1 findings 0", (name, rc, lines, err[-500:])
    assert not [x for x in lines if x.startswith("SCOPE-")
                and not x.startswith(("SCOPE-CHECK ", "SCOPE-CHECK-ALL "))], (name, lines)


def _write(folder, name, text):
    path = os.path.join(str(folder), name)
    with open(path, "w", encoding="ascii", newline="\r\n") as f:
        f.write(text)
    return path


def _source_line(path, n):
    with open(path, encoding="ascii") as f:
        return f.read().split("\n")[n - 1].strip()


def test_the_sitting_reads_the_culture_gate_into_a_free_name():
    """without PowerShell: the sitting's three lines use $cultureRes, and no line of the file writes or reads the
    name of the -CultureGate parameter in another case"""
    with open(SEAT, encoding="ascii") as f:
        text = f.read()
    assert text.count("$cultureRes") == 4 and text.count("$cultureGate") == 0, (
        text.count("$cultureRes"), text.count("$cultureGate"))
    assert "\n    [switch]$CultureGate,\n" in text


def test_the_judged_list_names_real_lines():
    """without PowerShell: each JUDGED line stands once in its file, so the list cannot go stale unseen"""
    for fname, _name, line, _why in JUDGED:
        with open(os.path.join(HERE, fname), encoding="ascii") as f:
            got = [x.strip() for x in f.read().split("\n")].count(line)
        assert got == 1, "%s holds %r %d times" % (fname, line, got)


@need_ps
def test_every_ps1_of_this_folder_holds_only_the_judged_assignments():
    files = sorted(glob.glob(os.path.join(HERE, "*.ps1")))
    names = [os.path.basename(f) for f in files]
    for must in ("frame_time_seat.ps1", "frame_time_seat_v.ps1", "frame_time_seat_trial.ps1", "ft_vm_launch.ps1",
                 "ft_close_leased.ps1", "ft_close_lib.ps1", "ft_settle_diskq.ps1", "ft_quiet_guest.ps1",
                 "ft_ps_scope_check.ps1"):
        assert must in names, "%s is not among the files read: %s" % (must, names)
    rc, lines, err = _check(*files)
    assert rc == 1, (rc, lines[-5:], err[-500:])
    per_file = [x for x in lines if x.startswith("SCOPE-CHECK ") and " parameters " in x]
    assert len(per_file) == len(files), "a file has no result line: %s" % per_file
    assert not [x for x in lines if x.startswith("SCOPE-CHECK-REFUSED")], lines
    assert not [x for x in lines if x.startswith(("SCOPE-REF ", "SCOPE-UNREAD "))], [
        x for x in lines if x.startswith(("SCOPE-REF ", "SCOPE-UNREAD "))]
    assert _held(lines) == [], [x for x in lines if x.startswith("SCOPE-CONST")]
    # the seat script and both entries: no stray break or continue, no top-level return, an exit statement last
    flows = dict((os.path.basename(f), (int(s), int(t), last)) for f, s, t, last in _match(FLOW, lines))
    assert len(flows) == len(files), flows
    for must in ("frame_time_seat.ps1", "frame_time_seat_v.ps1", "frame_time_seat_trial.ps1"):
        assert flows[must] == (0, 0, "exit"), (must, flows[must], [x for x in lines if x.startswith("SCOPE-STRAY")])
    found = sorted((os.path.basename(f), name, _source_line(f, n)) for f, n, name, _t, _p, _s in _findings(lines))
    assert found == sorted((f, name, line) for f, name, line, _why in JUDGED), "\n".join(
        x for x in lines if x.startswith("SCOPE-ASSIGN"))
    assert lines[-1] == "SCOPE-CHECK-ALL files %d findings %d" % (len(files), len(JUDGED)), lines[-1]
    # the two dot-source statements of this folder are followed, not passed over
    for sourcing in ("ft_close_leased.ps1", "ft_vm_launch.ps1"):
        row = [x for x in per_file if x.split(" parameters ")[0].endswith(sourcing)]
        assert len(row) == 1 and " dot-sourced 1 findings " in row[0], (sourcing, row)
    assert sum(int(x.split(" dot-sourced ")[1].split(" ")[0]) for x in per_file) == 2, per_file


@need_ps
def test_the_fault_of_12_nov_is_found_when_the_correction_is_reverted(tmp_path):
    with open(SEAT, encoding="ascii") as f:
        text = f.read()
    old = _write(tmp_path, "frame_time_seat.ps1", text.replace("$cultureRes", "$cultureGate"))
    rc, lines, err = _check(old)
    hits = [x for x in _findings(lines) if x[2] == "cultureGate"]
    assert rc == 1 and len(hits) == 1, (rc, lines[-6:], err[-500:])
    _f, n, _name, typ, par, scope = hits[0]
    assert (typ, par, scope) == ("switch", "CultureGate", "the file's top level"), hits[0]
    assert _source_line(old, n) == "$cultureGate = CultureGate { CultureRead }", _source_line(old, n)


@need_ps
@pytest.mark.parametrize("name,text,line,var,typ", PLANTED + NEW_PLANTED, ids=[p[0] for p in PLANTED + NEW_PLANTED])
def test_a_planted_assignment_is_found(tmp_path, name, text, line, var, typ):
    path = _write(tmp_path, "planted.ps1", text)
    rc, lines, err = _check(path)
    got = [(n, v, t) for _f, n, v, t, _p, _s in _findings(lines)]
    assert rc == 1 and got == [(line, var, typ)] and _held(lines) == [], (name, rc, lines, err[-500:])
    assert lines[-1] == "SCOPE-CHECK-ALL files 1 findings 1", lines[-1]


@need_ps
@pytest.mark.parametrize("name,text,line,var,bline,typ", BOUND, ids=[b[0] for b in BOUND])
def test_a_block_parameter_bound_over_a_parameter_is_found(tmp_path, name, text, line, var, bline, typ):
    path = _write(tmp_path, "planted.ps1", text)
    rc, lines, err = _check(path)
    got = [(n, v, t) for _f, n, v, t, _p, _s in _findings(lines)]
    assert rc == 1 and got == [(line, var, typ)], (name, rc, lines, err[-500:])
    hit = [x for x in lines if x.startswith("SCOPE-ASSIGN ")]
    assert (" $%s is bound as a parameter of the script block at line %d in the scope of its own parameter "
            % (var, bline)) in hit[0], hit
    assert lines[-1] == "SCOPE-CHECK-ALL files 1 findings 1", lines[-1]


@need_ps
@pytest.mark.parametrize("name,text,line,var,holds", PLANTED_HELD + NEW_HELD,
                         ids=[p[0] for p in PLANTED_HELD + NEW_HELD])
def test_a_planted_assignment_to_a_held_name_is_found(tmp_path, name, text, line, var, holds):
    path = _write(tmp_path, "planted.ps1", text)
    rc, lines, err = _check(path)
    got = [(n, v, h) for _f, n, v, h, _o, _s in _held(lines)]
    assert rc == 1 and got == [(line, var, holds)] and _findings(lines) == [], (name, rc, lines, err[-500:])
    opts = _held(lines)[0][4]
    assert "Constant" in opts or "ReadOnly" in opts, opts
    assert lines[-1] == "SCOPE-CHECK-ALL files 1 findings 1", lines[-1]


@need_ps
@pytest.mark.parametrize("name,text,line,var,to", PLANTED_REF, ids=[p[0] for p in PLANTED_REF])
def test_a_reference_to_a_taken_name_is_found(tmp_path, name, text, line, var, to):
    path = _write(tmp_path, "planted.ps1", text)
    rc, lines, err = _check(path)
    got = _match(REF, lines)
    assert rc == 1 and len(got) == 1 and (int(got[0][1]), got[0][2]) == (line, var), (name, rc, lines, err[-500:])
    assert got[0][3].startswith(to), got[0]
    assert _findings(lines) == [] and _held(lines) == [], lines
    assert lines[-1] == "SCOPE-CHECK-ALL files 1 findings 1", lines[-1]


@need_ps
@pytest.mark.parametrize("name,text,line,what", PLANTED_UNREAD, ids=[p[0] for p in PLANTED_UNREAD])
def test_a_construct_not_read_is_listed(tmp_path, name, text, line, what):
    path = _write(tmp_path, "planted.ps1", text)
    rc, lines, err = _check(path)
    got = _match(UNREAD, lines)
    assert rc == 1 and len(got) == 1 and int(got[0][1]) == line, (name, rc, lines, err[-500:])
    assert got[0][2].startswith(what), got[0]
    assert lines[-1] == "SCOPE-CHECK-ALL files 1 findings 1", lines[-1]


_NEW_SINGLE = ([(p[0], p[1]) for p in NEW_PLANTED] + [(b[0], b[1]) for b in BOUND] + [(h[0], h[1]) for h in NEW_HELD]
               + [(r[0], r[1]) for r in PLANTED_REF] + [(u[0], u[1]) for u in PLANTED_UNREAD]
               + [(f[0], f[1]) for f in FLOWS])


@need_ps
@pytest.mark.parametrize("name,text", _NEW_SINGLE, ids=[c[0] for c in _NEW_SINGLE])
def test_the_checker_of_ca9f945b_reads_each_new_case_clean(tmp_path, name, text):
    """the negative control of every rule added after ca9f945b: the checker as it stood there lists nothing"""
    _assert_old_reads_clean(tmp_path, _write(tmp_path, "planted.ps1", text), name)


@need_ps
@pytest.mark.parametrize("name,text", CONTROLS, ids=[c[0] for c in CONTROLS])
def test_a_control_is_clean(tmp_path, name, text):
    path = _write(tmp_path, "control.ps1", text)
    rc, lines, err = _check(path)
    assert rc == 0 and _findings(lines) == [] and _held(lines) == [], (name, rc, lines, err[-500:])
    assert lines[-1] == "SCOPE-CHECK-ALL files 1 findings 0", lines[-1]


@need_ps
@pytest.mark.parametrize("name,main,lib,want,scope", DOTS, ids=[d[0] for d in DOTS])
def test_a_dot_sourced_file_is_read_in_the_scope_that_sources_it(tmp_path, name, main, lib, want, scope):
    mp = _write(tmp_path, "main.ps1", main)
    _write(tmp_path, "lib.ps1", lib)
    rc, lines, err = _check(mp)
    got = _findings(lines)
    assert [(n, v, t) for _f, n, v, t, _p, _s in got] == want, (name, rc, lines, err[-500:])
    assert rc == (1 if want else 0), (name, rc, lines)
    for f, _n, _v, _t, _p, s in got:
        assert os.path.basename(f) == "lib.ps1" and s.startswith(scope) and ", dot-sourced at line " in s, (f, s)
    assert " dot-sourced 1 findings %d" % len(want) in lines[-2], lines[-2:]


@need_ps
@pytest.mark.parametrize("name,files,want,dots,code", NEW_DOTS, ids=[d[0] for d in NEW_DOTS])
def test_a_dot_sourced_file_is_followed_further_and_held_names_are_read(tmp_path, name, files, want, dots, code):
    for fname, text in files.items():
        _write(tmp_path, fname, text)
    main = os.path.join(str(tmp_path), "main.ps1")
    rc, lines, err = _check(main)
    got = sorted([("ASSIGN", os.path.basename(f), int(n), v, s) for f, n, v, _t, _p, s in _findings(lines)]
                 + [("CONST", os.path.basename(f), int(n), v, s) for f, n, v, _h, _o, s in _held(lines)])
    assert [(k, f, n, v) for k, f, n, v, _s in got] == sorted((k, f, n, v) for k, f, n, v, _s in want), (
        name, rc, lines, err[-500:])
    for (_k, _f, _n, _v, s), w in zip(got, sorted(want)):
        assert s.startswith(w[4]) and s.endswith(", dot-sourced at line 2"), (s, w)
    assert rc == code, (name, rc, lines)
    if code == 2:
        ref = [x for x in lines if x.startswith("SCOPE-CHECK-REFUSED ")]
        assert len(ref) == 1 and "lib.ps1:2 a dot-source statement is not of the form read here: . $x" in ref[0], ref
    assert " dot-sourced %d findings %d" % (dots, len(want)) in lines[-2], lines[-2:]
    _assert_old_reads_clean(tmp_path, main, name)


@need_ps
def test_a_dot_source_cycle_ends(tmp_path):
    for fname, text in CYCLE.items():
        _write(tmp_path, fname, text)
    rc, lines, err = _check(os.path.join(str(tmp_path), "main.ps1"))
    got = [(os.path.basename(f), n, v) for f, n, v, _t, _p, _s in _findings(lines)]
    assert rc == 1 and got == [("lib.ps1", 3, "boundMs")], (rc, lines, err[-500:])
    assert " dot-sourced 1 findings 1" in lines[-2], lines[-2:]


@need_ps
@pytest.mark.parametrize("name,text,stray,tops,last", FLOWS, ids=[f[0] for f in FLOWS])
def test_the_flow_line(tmp_path, name, text, stray, tops, last):
    """information only: the exit code and the findings count do not move"""
    path = _write(tmp_path, "flow.ps1", text)
    rc, lines, err = _check(path)
    assert rc == 0 and lines[-1] == "SCOPE-CHECK-ALL files 1 findings 0", (name, rc, lines, err[-500:])
    got = [int(g[0]) for g in _match(re.compile(r"^SCOPE-STRAY .+?flow\.ps1:(\d+) \S"), lines)]
    assert got == stray, (name, lines)
    flow = _match(FLOW, lines)
    assert [(int(s), int(t), la) for _f, s, t, la in flow] == [(len(stray), tops, last)], (name, lines)


@need_ps
def test_what_cannot_be_read_is_refused(tmp_path):
    broken = _write(tmp_path, "broken.ps1", "param([switch]$Flag)\nif ($Flag { 1 }\n")
    clean = _write(tmp_path, "clean.ps1", "param([switch]$Flag)\n$x = 1\n")
    rc, lines, _err = _check(clean, broken)
    ref = [x for x in lines if x.startswith("SCOPE-CHECK-REFUSED ")]
    assert rc == 2 and len(ref) == 1 and "parse error" in ref[0], (rc, lines)
    rc, lines, _err = _check(os.path.join(str(tmp_path), "absent.ps1"))
    assert rc == 2 and lines[0].startswith("SCOPE-CHECK-REFUSED ") and "not read" in lines[0], (rc, lines)
    rc, lines, _err = _check()
    assert rc == 2 and lines == ["SCOPE-CHECK-REFUSED no file was named"], (rc, lines)
    # a dot-source statement of another form, and one whose file is absent
    other = _write(tmp_path, "other.ps1", "$lib = Join-Path $PSScriptRoot 'clean.ps1'\n. $lib\n")
    rc, lines, _err = _check(other)
    ref = [x for x in lines if x.startswith("SCOPE-CHECK-REFUSED ")]
    assert rc == 2 and len(ref) == 1 and ":2 a dot-source statement is not of the form read here: . $lib" in ref[0], (
        rc, lines)
    gone = _write(tmp_path, "gone.ps1", ". (Join-Path $PSScriptRoot 'no_such_lib.ps1')\n")
    rc, lines, _err = _check(gone)
    ref = [x for x in lines if x.startswith("SCOPE-CHECK-REFUSED ")]
    assert rc == 2 and len(ref) == 1 and ":1 dot-sourced no_such_lib.ps1: not read" in ref[0], (rc, lines)


@need_ps
@pytest.mark.parametrize("name,files,ends", RUNTIME, ids=[r[0] for r in RUNTIME])
def test_powershell_itself_on_the_listed_assignments(tmp_path, name, files, ends):
    """the check's finding and PowerShell's own answer side by side: each script is listed once by the check, and
    PowerShell ends the first three at the assignment (the fourth runs through: listed, and no error)"""
    for fname, text in files.items():
        _write(tmp_path, fname, text)
    main = os.path.join(str(tmp_path), "main.ps1")
    crc, lines, cerr = _check(main)
    assert crc == 1 and len(_findings(lines)) + len(_held(lines)) == 1, (name, crc, lines, cerr[-500:])
    rc, out, err = _ps(main)
    assert "before" in out.split("\n"), (name, rc, out, err[-800:])
    if ends:
        assert rc != 0 and "after" not in out.split("\n"), (name, rc, out, err[-800:])
    else:
        assert rc == 0 and "after" in out.split("\n"), (name, rc, out, err[-800:])


# ---- (b) the entries, run for real beside a stand-in seat script

_HEAD = "[CmdletBinding()]\nparam([switch]$CultureGate, [string]$ArmForce = 'none', [int]$TimeoutS = 7200)\n"
_ARGS = "[Console]::Out.WriteLine(('stand-in: ArmForce={0} TimeoutS={1}' -f $ArmForce, $TimeoutS))\n"
STANDINS = {
    "fault": (_HEAD + "$ErrorActionPreference = 'Stop'\nSet-StrictMode -Version 2\n"
              "[Console]::Out.WriteLine('stand-in: before')\n"
              "$cultureGate = @{ Refuse = $false; Lines = @('x') }\n"
              "[Console]::Out.WriteLine('stand-in: after')\nexit 0\n"),
    "code4": _HEAD + _ARGS + "exit 4\n",
    "code0": _HEAD + _ARGS + "exit 0\n",
    "nocode": _HEAD + _ARGS,
    "code3": _HEAD + _ARGS + "exit 3\n",
    "stray": (_HEAD + "[Console]::Out.WriteLine('stand-in: before')\nbreak\n"
              "[Console]::Out.WriteLine('stand-in: after')\nexit 0\n"),
    "labelbreak": (_HEAD + "[Console]::Out.WriteLine('stand-in: before')\nbreak nolabel\n"
                   "[Console]::Out.WriteLine('stand-in: after')\nexit 0\n"),
    "labelcontinue": (_HEAD + "[Console]::Out.WriteLine('stand-in: before')\ncontinue nolabel\n"
                      "[Console]::Out.WriteLine('stand-in: after')\nexit 0\n"),
}
ENTRIES = [("frame_time_seat_v.ps1", "stand-in: ArmForce=ON TimeoutS=7200"),
           ("frame_time_seat_trial.ps1", "stand-in: ArmForce=ON TimeoutS=780")]
# sitting V's entry as it was at fd0263ee, the code lines only
ENTRY_OF_12_NOV = ("$seat = Join-Path $PSScriptRoot 'frame_time_seat.ps1'\n"
                   "if (-not (Test-Path -LiteralPath $seat -PathType Leaf)) { [Console]::Out.WriteLine(\"REFUSED: "
                   "frame_time_seat.ps1 is not beside frame_time_seat_v.ps1 ($seat)\"); exit 2 }\n"
                   "& $seat -ArmForce ON\nexit $LASTEXITCODE\n")
# an entry with a try and a catch as today's, and no loop around the call
ENTRY_NO_LOOP = ("$seat = Join-Path $PSScriptRoot 'frame_time_seat.ps1'\n"
                 "$global:LASTEXITCODE = 1\n"
                 "try { & $seat -ArmForce ON }\n"
                 "catch { [Console]::Out.WriteLine('SEAT-SCRIPT-ERROR: ' + $_.Exception.Message); exit 1 }\n"
                 "[Console]::Out.WriteLine('entry: after the call')\n"
                 "exit $LASTEXITCODE\n")


def _run_entry(folder, entry, standin):
    if standin is not None:
        _write(folder, "frame_time_seat.ps1", STANDINS[standin])
    rc, out, err = _ps(entry)
    return rc, out + err


def _place(folder, name):
    dst = os.path.join(str(folder), name)
    shutil.copyfile(os.path.join(HERE, name), dst)
    return dst


@need_ps
@pytest.mark.parametrize("name,args", ENTRIES, ids=[e[0] for e in ENTRIES])
def test_an_entry_ends_1_when_the_seat_script_dies(tmp_path, name, args):
    rc, out = _run_entry(tmp_path, _place(tmp_path, name), "fault")
    assert rc == 1, (rc, out[-1500:])
    assert "stand-in: before" in out and "stand-in: after" not in out, out[-1500:]
    err = [x for x in out.split("\n") if x.startswith("SEAT-SCRIPT-ERROR: frame_time_seat.ps1 ended by an error: ")]
    assert len(err) == 1 and "SwitchParameter" in err[0], out[-1500:]
    assert len([x for x in out.split("\n") if x.startswith("SEAT-SCRIPT-ERROR")]) == 1, out[-1500:]


@need_ps
def test_the_entry_of_12_nov_ended_0_on_the_same_fault(tmp_path):
    """the negative control: the stand-in reproduces the fault, and the entry as it was reported it as exit code 0"""
    rc, out = _run_entry(tmp_path, _write(tmp_path, "frame_time_seat_v.ps1", ENTRY_OF_12_NOV), "fault")
    assert rc == 0, (rc, out[-1500:])
    assert "stand-in: before" in out and "stand-in: after" not in out and "SwitchParameter" in out, out[-1500:]


@need_ps
@pytest.mark.parametrize("name,args", ENTRIES, ids=[e[0] for e in ENTRIES])
def test_an_entry_passes_the_exit_code_and_its_own_arguments_on(tmp_path, name, args):
    entry = _place(tmp_path, name)
    rc, out = _run_entry(tmp_path, entry, "code4")
    assert rc == 4 and args in out.split("\n") and "SEAT-SCRIPT-ERROR" not in out, (rc, out[-1500:])
    rc, out = _run_entry(tmp_path, entry, "code0")
    assert rc == 0 and args in out.split("\n") and "SEAT-SCRIPT-ERROR" not in out, (rc, out[-1500:])
    rc, out = _run_entry(tmp_path, entry, "code3")
    assert rc == 3 and args in out.split("\n") and "SEAT-SCRIPT-ERROR" not in out, (rc, out[-1500:])


@need_ps
@pytest.mark.parametrize("name,args", ENTRIES, ids=[e[0] for e in ENTRIES])
def test_an_entry_ends_1_when_the_seat_script_ends_without_a_code(tmp_path, name, args):
    """a seat script that runs off its end sets no exit code: the entry's own 1 stands, never a 0"""
    rc, out = _run_entry(tmp_path, _place(tmp_path, name), "nocode")
    assert rc == 1 and args in out.split("\n") and "SEAT-SCRIPT-ERROR" not in out, (rc, out[-1500:])


@need_ps
@pytest.mark.parametrize("name,args", ENTRIES, ids=[e[0] for e in ENTRIES])
def test_an_entry_ends_1_when_the_seat_script_ends_by_a_stray_break(tmp_path, name, args):
    """a break outside a loop ends the calling script too: the entry's one-pass loop takes it, and its 1 stands"""
    rc, out = _run_entry(tmp_path, _place(tmp_path, name), "stray")
    assert rc == 1 and "SEAT-SCRIPT-ERROR" not in out, (rc, out[-1500:])
    assert "stand-in: before" in out and "stand-in: after" not in out, out[-1500:]


_LABELLED = [(e[0], s) for e in ENTRIES for s in ("labelbreak", "labelcontinue")]


@need_ps
@pytest.mark.parametrize("name,standin", _LABELLED, ids=["%s-%s" % c for c in _LABELLED])
def test_an_entry_ends_1_when_a_labelled_jump_leaves_it(tmp_path, name, standin):
    """a labelled break or continue whose label names no loop passes the one-pass loop and the catch: the finally
    prints the control-transfer line and ends the process 1"""
    rc, out = _run_entry(tmp_path, _place(tmp_path, name), standin)
    assert rc == 1, (rc, out[-1500:])
    assert "stand-in: before" in out and "stand-in: after" not in out, out[-1500:]
    assert [x for x in out.split("\n") if x.startswith("SEAT-SCRIPT-ERROR")] == [CONTROL_LINE], out[-1500:]


@need_ps
@pytest.mark.parametrize("standin", ["labelbreak", "labelcontinue"])
def test_the_entry_of_ca9f945b_ended_0_on_a_labelled_jump(tmp_path, standin):
    """the negative control: sitting V's entry as it stood at ca9f945b ends 0 on the same stand-in"""
    entry = os.path.join(str(tmp_path), "frame_time_seat_v.ps1")
    with open(entry, "wb") as f:
        f.write(_git_show("tools/frametime/frame_time_seat_v.ps1"))
    rc, out = _run_entry(tmp_path, entry, standin)
    assert rc == 0 and "SEAT-SCRIPT-ERROR" not in out, (rc, out[-1500:])
    assert "stand-in: before" in out and "stand-in: after" not in out, out[-1500:]


@need_ps
def test_an_entry_without_the_loop_ends_0_on_a_stray_break(tmp_path):
    """the negative control of the loop: the same stand-in ends an entry that has no loop, and its code is 0"""
    rc, out = _run_entry(tmp_path, _write(tmp_path, "frame_time_seat_v.ps1", ENTRY_NO_LOOP), "stray")
    assert rc == 0 and "entry: after the call" not in out, (rc, out[-1500:])
    assert "stand-in: before" in out and "stand-in: after" not in out, out[-1500:]


@need_ps
@pytest.mark.parametrize("name,args", ENTRIES, ids=[e[0] for e in ENTRIES])
def test_an_entry_refuses_without_the_seat_script(tmp_path, name, args):
    rc, out = _run_entry(tmp_path, _place(tmp_path, name), None)
    assert rc == 2 and ("REFUSED: frame_time_seat.ps1 is not beside %s" % name) in out, (rc, out[-1500:])
