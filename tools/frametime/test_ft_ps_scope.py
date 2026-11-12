"""test_ft_ps_scope.py: no assignment to a name its scope already holds, and the seat entries' exit code.

The fault these tests hold (sitting V's first try, 12 Nov 2026): frame_time_seat.ps1 assigned the culture gate's result
to $cultureGate at its top level, where [switch]$CultureGate is a parameter (PowerShell names are case-insensitive).
The assignment is a conversion error there, the script ended one second after its start, and the sitting-V entry then
ended with exit code 0. No test had run that line: the sitting's top level runs only on a seat with a staged lane.

(a) THE CLASS, by machine: ft_ps_scope_check.ps1 reads a file with PowerShell's parser and lists every assignment
    whose target is a parameter of the scope it runs in, or a name PowerShell holds constant or read-only, and it
    follows a dot-sourced file into the scope that sources it. Every *.ps1 of this folder is read, and the findings
    must be exactly JUDGED (each one read and listed with its reason), so a new one fails here. Each planted fault
    must be found at its line, each control must be clean, the seat script with the correction reverted must show
    the fault of 12 Nov at its line, and a file that is absent or does not parse, or a dot-source statement that
    cannot be followed, is refused, never passed. RUNTIME runs four small scripts for real: PowerShell ends the
    three whose assignment it refuses, and passes the fourth (an untyped parameter: listed, no error).
(b) THE ENTRIES: frame_time_seat_v.ps1 and frame_time_seat_trial.ps1, each run for real beside a stand-in
    frame_time_seat.ps1. A stand-in that dies of the same fault gives exit code 1 and a SEAT-SCRIPT-ERROR line; the
    entry as it was before the correction ends 0 on that stand-in (the negative control). A stand-in that ends
    without a code, or by a stray break, gives 1 (an entry without the loop ends 0 on the break: its control). A
    stand-in's exit code is passed on, the arguments are the entry's own, and without the seat script beside it the
    entry refuses with exit 2.
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

FINDING = re.compile(r"^SCOPE-ASSIGN (.+):(\d+) \$(\S+) is assigned in the scope of its own parameter "
                     r"\[(.+?)\]\$(\S+) \((.+)\)$")
HELD = re.compile(r"^SCOPE-CONST (.+):(\d+) \$(\S+) is assigned, and this PowerShell holds \$(\S+) (.+) "
                  r"\(([^()]+)\)$")

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
]

# (name, the file's text, the line, the name as written, the name PowerShell holds)
PLANTED_HELD = [
    ("a constant at the top level", "$pid = 5\n", 1, "pid", "PID"),
    ("a constant inside a function", "function F {\n    $Host = 1\n}\n", 2, "Host", "Host"),
    ("a read-only name through $global:", "$global:home = 'x'\n", 1, "home", "HOME"),
]

# (name, the file's text): no finding
CONTROLS = [
    ("the same name in a called function (a scope of its own)",
     "param([switch]$Flag)\nfunction K { $flag = @{} }\n"),
    ("a script block with a param block of its own", "param([switch]$Flag)\n$b = { param($x) $flag = 1 }\n"),
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
    assert _held(lines) == [], [x for x in lines if x.startswith("SCOPE-CONST")]
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
@pytest.mark.parametrize("name,text,line,var,typ", PLANTED, ids=[p[0] for p in PLANTED])
def test_a_planted_assignment_is_found(tmp_path, name, text, line, var, typ):
    path = _write(tmp_path, "planted.ps1", text)
    rc, lines, err = _check(path)
    got = [(n, v, t) for _f, n, v, t, _p, _s in _findings(lines)]
    assert rc == 1 and got == [(line, var, typ)] and _held(lines) == [], (name, rc, lines, err[-500:])
    assert lines[-1] == "SCOPE-CHECK-ALL files 1 findings 1", lines[-1]


@need_ps
@pytest.mark.parametrize("name,text,line,var,holds", PLANTED_HELD, ids=[p[0] for p in PLANTED_HELD])
def test_a_planted_assignment_to_a_held_name_is_found(tmp_path, name, text, line, var, holds):
    path = _write(tmp_path, "planted.ps1", text)
    rc, lines, err = _check(path)
    got = [(n, v, h) for _f, n, v, h, _o, _s in _held(lines)]
    assert rc == 1 and got == [(line, var, holds)] and _findings(lines) == [], (name, rc, lines, err[-500:])
    opts = _held(lines)[0][4]
    assert "Constant" in opts or "ReadOnly" in opts, opts
    assert lines[-1] == "SCOPE-CHECK-ALL files 1 findings 1", lines[-1]


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
    "stray": (_HEAD + "[Console]::Out.WriteLine('stand-in: before')\nbreak\n"
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
    assert rc == 1, (rc, out[-1500:])
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
