"""test_ft_arm_text.py: the FrameTime sentinel's arm profiles (lane B11, V6) and the three tools that use them.

ft_arm_text.sh is the one table of the profiles: each profile's exact bytes and launch kind, and the refusal of an
unknown, an empty and a missing profile. Every key of every profile is one the plugin reads, and every value one the
plugin accepts, both read as text from plugin/FtConfig.cs (Load), plugin/FtClock.cs (the k_mutant read) and
plugin/FtSpan.cs (SetMutants): this file holds no second list of the plugin's keys or values. ft_vm_install.sh's arm
verb writes exactly ft_arm_text.sh's text and holds none of its own (also run, in a copy re-rooted in a temp folder);
ft_vm_leased.sh takes its kind from ft_arm_text.sh and holds no list of the profiles; frame_time_seat.ps1 writes
seed=$Seed and f18=$F18, and force=ON only under -ArmForce ON. The mutants, each in a copy in a temp folder, must
each fail their named check, beside the unchanged copy, which must pass every check.
"""
import os
import re
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ARM_TEXT = os.path.join(HERE, "ft_arm_text.sh")
INSTALL = os.path.join(HERE, "ft_vm_install.sh")
LEASED = os.path.join(HERE, "ft_vm_leased.sh")
SEAT = os.path.join(HERE, "frame_time_seat.ps1")
SEAT_V = os.path.join(HERE, "frame_time_seat_v.ps1")
SEAT_TRIAL = os.path.join(HERE, "frame_time_seat_trial.ps1")
PLUGIN = os.path.join(ROOT, "plugin")

# the brief's table (BRIEF-P4 requirement 1): each profile's exact bytes and its launch kind
BOOT = b"seed=1\nforce=none\nmenu=1\nmenu_segments=4\n"
WANT = {
    "menu": (b"seed=1\nforce=none\nmenu=1\n", "menu"),
    "match": (b"seed=2\nf18=A\n", "match"),
    "match-on": (b"seed=2\nf18=A\nforce=ON\n", "match"),
    "boot": (BOOT, "menu"),
    "boot-k1": (BOOT + b"k_mutant=k1\n", "menu"),
    "boot-k2": (BOOT + b"k_mutant=k2\n", "menu"),
    "boot-k3": (BOOT + b"k_mutant=k3\n", "menu"),
}
KINDS = {"menu", "match"}
# argument lists a refusal must answer: an unknown, an empty and a missing profile, in both forms, and an extra word
REFUSED_ARGS = [["nope"], ["--kind", "nope"], [""], ["--kind", ""], [], ["--kind"], ["menu", "extra"],
                ["MENU"], ["boot-k4"], ["match-off"]]


def read(path):
    with open(path, encoding="utf-8-sig") as f:   # universal newlines: CRLF and LF read alike
        return f.read()


def run(script, *args, env=None):
    p = subprocess.run(["bash", script] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                       timeout=60)
    return p.returncode, p.stdout, p.stderr


# ---- the plugin's sentinel rules, read from its source


def _parens(text, i):
    """the text inside the parenthesis that opens at text[i]"""
    assert text[i] == "("
    depth = 0
    for j in range(i, len(text)):
        depth += {"(": 1, ")": -1}.get(text[j], 0)
        if depth == 0:
            return text[i + 1:j]
    raise AssertionError("unbalanced parenthesis")


def _rule(load, var, key):
    """the acceptance rule of one FtConfig key: the condition of the one if whose body adds ' bad-<key>'"""
    tag = 'Problems += " bad-%s"' % key
    assert load.count(tag) == 1, "FtConfig.Load: %r not exactly once" % tag
    at = load.index(tag)
    i = load.rindex("if (", 0, at)
    cond = _parens(load, i + 3)
    m = re.fullmatch(r"!int\.TryParse\(%s, out (\w+)\)(.*)" % re.escape(var), cond, re.S)
    if m:
        target, rest = m.group(1), m.group(2)
        lo = [int(n) for n in re.findall(r"\|\| {0} < (-?\d+)".format(target), rest)]
        hi = [int(n) for n in re.findall(r"\|\| {0} > (-?\d+)".format(target), rest)]
        mod = [int(n) for n in re.findall(r"\|\| {0} % (\d+) != 0".format(target), rest)]
        left = re.sub(r"\|\| {0} (?:< -?\d+|> -?\d+|% \d+ != 0)".format(target), "", rest).strip()
        assert left == "", "FtConfig.Load: the rule of %s has an unread term %r" % (key, left)
        return ("int", lo, hi, mod)
    if re.fullmatch(r'{0} != "[^"]*"(?: && {0} != "[^"]*")*'.format(re.escape(var)), cond):
        return ("set", set(re.findall(r'!= "([^"]*)"', cond)))
    m = re.fullmatch(r"%s != (\w+)" % re.escape(var), cond)
    if m:
        field = m.group(1)
        a = re.search(r'\b{0} = ((?:{1} == "[^"]*"(?: \|\| )?)+) \? {1} : "([^"]*)";'.format(field, re.escape(var)), load)
        assert a, "FtConfig.Load: %s's field %s has no ternary of the known shape" % (key, field)
        return ("set", set(re.findall(r'== "([^"]*)"', a.group(1))) | {a.group(2)})
    raise AssertionError("FtConfig.Load: the rule of %s has an unknown shape: %r" % (key, cond))


def plugin_rules():
    """{key: rule} for every sentinel key the plugin reads in FtConfig.Load, and FtClock's k_mutant read with
    FtSpan.SetMutants' values"""
    cfg = read(os.path.join(PLUGIN, "FtConfig.cs"))
    load = cfg[cfg.index("internal static void Load()"):cfg.index("internal static void Refresh()")]
    rules = {}
    for m in re.finditer(r'string (\w+) = Get\("(\w+)", [^;]+\);', load):
        rules[m.group(2)] = _rule(load, m.group(1), m.group(2))
    clock = read(os.path.join(PLUGIN, "FtClock.cs"))
    km = re.findall(r'FtSpan\.SetMutants\(FtConfig\.Get\("(\w+)", "(\w+)"\)\);', clock)
    assert len(km) == 1, "FtClock.cs: the k_mutant read is not exactly one SetMutants(FtConfig.Get(...)) call"
    key, default = km[0]
    span = read(os.path.join(PLUGIN, "FtSpan.cs"))
    i = span.index("internal static void SetMutants(string k)")
    body = span[span.index("{", i):]
    body = body[:body.index("\n        }\n")]
    lits = set(re.findall(r'\bk == "(\w+)"', body))
    assert lits, "FtSpan.SetMutants: no k == literal"
    rules[key] = ("set", lits | {default})
    return rules


def accepts(rule, v):
    if rule[0] == "set":
        return v in rule[1]
    _, lo, hi, mod = rule
    if not re.fullmatch(r"-?\d+", v):
        return False
    n = int(v)
    return all(n >= x for x in lo) and all(n <= x for x in hi) and all(n % x == 0 for x in mod)


def test_plugin_rules_read_whole():
    """the reader found a rule for every Get of FtConfig.Load and the one k_mutant read (the mutants 'a key the
    plugin does not read' and 'a value the plugin refuses' prove the rules refuse)"""
    cfg = read(os.path.join(PLUGIN, "FtConfig.cs"))
    load = cfg[cfg.index("internal static void Load()"):cfg.index("internal static void Refresh()")]
    rules = plugin_rules()
    print("PLUGIN RULES %s" % sorted((k, sorted(v[1]) if v[0] == "set" else v) for k, v in rules.items()))
    assert len(rules) == len(re.findall(r'\bGet\("', load)) + 1


# ---- the named checks (each returns its failures; empty = pass)


def check_bytes(script):
    out = []
    for p, (want, _) in WANT.items():
        rc, so, se = run(script, p)
        if (rc, so, se) != (0, want, b""):
            out.append("bytes %s: rc %s, stdout %r, stderr %r; wanted %r" % (p, rc, so, se, want))
    return out


def check_kinds(script):
    out = []
    for p, (_, kind) in WANT.items():
        rc, so, se = run(script, "--kind", p)
        if (rc, so, se) != (0, kind.encode() + b"\n", b""):
            out.append("kind %s: rc %s, stdout %r; wanted %s" % (p, rc, so, kind))
    return out


def check_refusals(script):
    out = []
    for args in REFUSED_ARGS:
        rc, so, se = run(script, *args)
        if rc != 2 or so != b"" or se.count(b"\n") != 1 or not se.endswith(b"\n"):
            out.append("refusal %r: rc %s, stdout %r, stderr %r" % (args, rc, so, se))
    return out


def check_table(script):
    """the script's case arms name exactly the profiles of WANT (an arm added or dropped is a finding)"""
    arms = set()
    for m in re.finditer(r"^\s+([a-z0-9|-]+)\)\s", read(script), re.M):
        arms |= set(m.group(1).split("|"))
    return [] if arms == set(WANT) else ["table: the case arms are %s, not %s" % (sorted(arms), sorted(WANT))]


def check_plugin(script):
    rules = plugin_rules()
    out = []
    for p in WANT:
        rc, so, _ = run(script, p)
        if rc != 0:
            out.append("plugin %s: rc %s" % (p, rc))
            continue
        seen = set()
        for ln in so.decode("ascii").splitlines():
            k, eq, v = ln.partition("=")
            if not eq or not k:
                out.append("plugin %s: line %r is no key=value" % (p, ln))
            elif k not in rules:
                out.append("plugin %s: key %s is not one the plugin reads" % (p, k))
            elif not accepts(rules[k], v):
                out.append("plugin %s: %s=%s is not a value the plugin accepts" % (p, k, v))
            if k in seen:
                out.append("plugin %s: key %s twice" % (p, k))
            seen.add(k)
    return out


def _arm_verb(text):
    i = text.index("\n  arm)\n")
    return text[i:text.index("\n  disarm)\n", i)]


def check_install(path):
    text = read(path)
    keys = sorted(plugin_rules())
    seg = _arm_verb(text)
    out = []
    if seg.count('bash "$HERE/ft_arm_text.sh" "$mode"') != 1:
        out.append("install: the arm verb does not call ft_arm_text.sh once with its profile")
    if seg.count('> "$ARM"') != 1:
        out.append("install: the arm verb writes the sentinel other than once")
    for k in keys:
        if re.search(r"(?<![\w$])%s=" % re.escape(k), text):
            out.append("install: a literal %s= in ft_vm_install.sh" % k)
    return out


def check_leased(path):
    text = read(path)
    out = []
    if text.count('KIND=$(bash "$HERE/ft_arm_text.sh" --kind "$MODE"') != 1:
        out.append("leased: the kind is not taken once from ft_arm_text.sh --kind")
    if re.search(r'case "\$MODE"', text):
        out.append("leased: a case on the profile (a second list)")
    if not re.search(r'case "\$KIND" in menu\) N=1;; match\) N=2;;', text):
        out.append("leased: the gate number does not follow the kind")
    for p in WANT:
        if p not in KINDS and re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(p), text):
            out.append("leased: the profile name %s appears (a second list)" % p)
    for need in ('PIDF="$OUT/launch-$KIND.pid"', 'arm "$MODE"', '-Mode "$KIND"', '"$OUT/LogOutput-$KIND.log"'):
        if text.count(need) != 1:
            out.append("leased: %r not exactly once" % need)
    for bad in ("launch-$MODE", "LogOutput-$MODE", '-Mode "$MODE"', 'arm "$KIND"'):
        if bad in text:
            out.append("leased: %r" % bad)
    return out


# -CultureGate (ruling R6-A3.11.154) runs the number-format gate alone: what it prints, its exit code and that it
# creates nothing under the sitting's roots are held by test_ft_seat_export.py (test_culture_gate_switch)
SEAT_PARAMS = ["SelfTest", "FlowTest", "CultureGate", "CfgKindList", "SliceOf", "TimeoutS", "Seed", "F18", "GameRoot",
               "SeatRoot", "LocalLow", "ArmForce"]


def check_seat(path):
    text = read(path)
    out = []
    pb = text[text.index("\nparam(") + 6:]
    pb = _parens(pb, 0)
    names = re.findall(r"\]\$(\w+)", pb)
    if names != SEAT_PARAMS:
        out.append("seat: the parameters are %s" % names)
    if not re.search(r"\[ValidateSet\('ON', 'none'\)\]\[string\]\$ArmForce = 'none'\s*$", pb):
        out.append("seat: -ArmForce is not ValidateSet ON, none with the default none")
    sit = text[text.index("\nfunction Sitting("):]
    sit = sit[:sit.index("\nfunction ", 1)]
    for need in ('$armLines = @("seed=$Seed", "f18=$F18")', "if ($ArmForce -eq 'ON') { $armLines += 'force=ON' }",
                 "Set-Content -LiteralPath $C.Arm -Value $armLines -Encoding ascii"):
        if sit.count(need) != 1:
            out.append("seat: %r not once in Sitting" % need)
    if text.count("-LiteralPath $C.Arm -Value") != 1:
        out.append("seat: the sentinel is written other than once")
    body = text[text.index("\n#>") + 3:]
    st = body.index("\nif ($SelfTest) {")
    rest = body[:st] + body[body.index("\n# ---- the sitting", st):]
    for ln in rest.splitlines():
        if "force=ON" in ln and not ln.lstrip().startswith("#") and "$ArmForce -eq 'ON'" not in ln:
            out.append("seat: force=ON outside -ArmForce ON: %s" % ln.strip())
    return out


SEAT_CATCH = ("catch { $seatFailed = $true; [Console]::Out.WriteLine('SEAT-SCRIPT-ERROR: frame_time_seat.ps1 ended by "
              "an error: ' + $_.Exception.Message); exit 1 }")
SEAT_FINALLY = ("finally { if (-not ($seatReturned -or $seatFailed)) { [Console]::Out.WriteLine('SEAT-SCRIPT-ERROR: "
                "frame_time_seat.ps1 ended by a control transfer that left the entry'); [Environment]::Exit(1) } }")


def check_seat_entry(path, own, call):
    """a seat entry (sitting V's, or the control run's): ASCII, and its code lines are exactly nine: the runner taken
    from the entry's own folder; a one-line refusal that names the entry, exit 2, when the runner is not beside it;
    exit code 1 set before the call (it stands when the runner sets none); the two flags set false; the call, with
    exactly the entry's own arguments, alone in a one-pass loop inside a try (the loop takes a stray break or
    continue of the runner), the returned flag set after the loop; a catch that sets the failed flag, prints one
    SEAT-SCRIPT-ERROR line and ends 1; a finally that, with neither flag set (a labelled break or continue left the
    entry), prints one SEAT-SCRIPT-ERROR line and ends the process 1; the code passed on. The entry of 12 Nov 2026
    ended 0 on a runner that an error had ended: an error sets no exit code."""
    with open(path, "rb") as f:
        raw = f.read()
    out = []
    if any(b > 127 for b in raw):
        out.append("%s: not ASCII" % own)
    text = raw.decode("ascii", "replace").replace("\r\n", "\n")
    code = [ln.strip() for ln in text.split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    want = ["$seat = Join-Path $PSScriptRoot 'frame_time_seat.ps1'",
            "if (-not (Test-Path -LiteralPath $seat -PathType Leaf)) { [Console]::Out.WriteLine(\"REFUSED: "
            "frame_time_seat.ps1 is not beside %s ($seat)\"); exit 2 }" % own,
            "$global:LASTEXITCODE = 1",
            "$seatReturned = $false",
            "$seatFailed = $false",
            "try { do { %s } while ($false); $seatReturned = $true }" % call,
            SEAT_CATCH,
            SEAT_FINALLY,
            "exit $LASTEXITCODE"]
    what = ["the runner is not taken from the entry's own folder first",
            "no one-line refusal with exit 2, naming the entry, when frame_time_seat.ps1 is absent",
            "exit code 1 is not set before the call",
            "the returned flag is not set false before the call",
            "the failed flag is not set false before the call",
            "the call is not %r alone in a one-pass loop inside a try, the returned flag set after the loop" % call,
            "the catch does not set the failed flag, print one SEAT-SCRIPT-ERROR line and end 1",
            "the finally does not end the process 1 with a SEAT-SCRIPT-ERROR line when neither flag is set",
            "the call's exit code is not passed on last"]
    for i, (w, msg) in enumerate(zip(want, what)):
        if code[i:i + 1] != [w]:
            out.append("%s: code line %d: %s" % (own, i + 1, msg))
    if len(code) != len(want):
        out.append("%s: %d code lines, not %d (no other logic)" % (own, len(code), len(want)))
    return out


def check_seat_v(path):
    """sitting V's entry: the runner with exactly -ArmForce ON"""
    return check_seat_entry(path, "frame_time_seat_v.ps1", "& $seat -ArmForce ON")


def check_seat_trial(path):
    """the control run's entry: the runner with -ArmForce ON and a wait of 180 s (-TimeoutS 780), nothing else"""
    return check_seat_entry(path, "frame_time_seat_trial.ps1", "& $seat -ArmForce ON -TimeoutS 780")


# ---- the tests on the real files


def test_seat_v_entry():
    assert check_seat_v(SEAT_V) == []


def test_seat_trial_entry():
    assert check_seat_trial(SEAT_TRIAL) == []


def test_profile_bytes():
    assert check_bytes(ARM_TEXT) == []


def test_profile_kinds():
    assert check_kinds(ARM_TEXT) == []


def test_refusals():
    assert check_refusals(ARM_TEXT) == []


def test_table_is_the_profiles():
    assert check_table(ARM_TEXT) == []


def test_profiles_are_plugin_keys_and_values():
    assert check_plugin(ARM_TEXT) == []


def test_install_holds_no_sentinel_text():
    assert check_install(INSTALL) == []


def test_leased_takes_kind_from_arm_text():
    assert check_leased(LEASED) == []


def test_seat_runner_arm_force():
    assert check_seat(SEAT) == []


def test_leased_refuses_before_anything(tmp_path):
    """an unknown, empty or missing profile: the usage line, exit 2, and no outdir made; a profile of the table
    passes the gate (the run stops at the missing outdir instead)"""
    out = tmp_path / "out"
    for args in (["nope", str(out)], ["", str(out)], [], ["boot-k4", str(out), "--dry"]):
        rc, so, se = run(LEASED, *args)
        assert rc == 2 and so.startswith(b"usage: ft_vm_leased.sh <profile>") and b"outdir" not in se, (args, rc, so, se)
        assert not out.exists()
    for p in WANT:
        rc, so, se = run(LEASED, p)
        assert b"usage" not in so and b"outdir" in se and rc != 0, (p, rc, so, se)


def _install_copy(tmp):
    """ft_vm_install.sh and ft_arm_text.sh in a temp folder, R and GAME re-rooted there, an open install whose
    installed DLL is the lane's"""
    text = read(INSTALL)
    r_line = "R=C:/Users/Sid/Documents/SidsCompetitiveRounds\n"
    g_line = 'GAME="C:/Program Files (x86)/Steam/steamapps/common/ROUNDS"\n'
    assert text.count(r_line) == 1 and text.count(g_line) == 1
    text = text.replace(r_line, 'R="%s/r"\n' % tmp).replace(g_line, 'GAME="%s/game"\n' % tmp)
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir)
    with open(os.path.join(bindir, "ft_vm_install.sh"), "w", newline="\n") as f:
        f.write(text)
    shutil.copy(ARM_TEXT, os.path.join(bindir, "ft_arm_text.sh"))
    plug = os.path.join(tmp, "game", "BepInEx", "plugins", "CompetitiveRounds")
    os.makedirs(plug)
    with open(os.path.join(plug, "CompetitiveRounds.dll"), "wb") as f:
        f.write(b"the lane's dll")
    bk = os.path.join(tmp, "r", "ai-collab", "frame-time", "vm-install", "bk")
    os.makedirs(bk)
    with open(os.path.join(bk, "installed.sha256"), "w") as f:
        f.write("0" * 64 + "\n")
    with open(os.path.join(tmp, "r", "ai-collab", "frame-time", "vm-install", "CURRENT"), "w") as f:
        f.write(bk + "\n")
    return os.path.join(bindir, "ft_vm_install.sh"), os.path.join(tmp, "game", "BepInEx", "frametime", "arm")


def test_install_arm_writes_arm_text(tmp_path):
    inst, arm = _install_copy(str(tmp_path))
    rc, so, _ = run(inst, "arm", "nope")
    assert rc == 2 and b"FT-VM-INSTALL REFUSED: usage: arm <profile>" in so
    assert not os.path.exists(os.path.dirname(arm)), "a refused arm wrote something"
    for p, (want, _) in WANT.items():
        rc, so, _ = run(inst, "arm", p)
        assert rc == 0 and re.search(rb"FT-VM-ARM %s written: " % re.escape(p.encode()), so), (p, rc, so)
        with open(arm, "rb") as f:
            assert f.read() == want, p
        assert so.rstrip(b"\n").endswith(want.replace(b"\n", b" ")), (p, so)


# ---- the mutants, each in a copy in a temp folder, each failing its named check

ARM_MUTANTS = [
    # (name, the check it must fail, old, new)
    ("one byte of match's text", check_bytes, "L=(seed=2 f18=A);;", "L=(seed=2 f18=B);;"),
    ("match-on without its force line", check_bytes, "L=(seed=2 f18=A force=ON);;", "L=(seed=2 f18=A);;"),
    ("an unknown profile accepted", check_refusals, "  *) refuse \"unknown profile '$p'\";;",
     "  *) k=menu;  L=(seed=1 force=none menu=1);;"),
    ("a boot profile whose kind is match", check_kinds, "  boot)                    k=menu;",
     "  boot)                    k=match;"),
    ("a key the plugin does not read", check_plugin, '"k_mutant=${p#boot-}"', '"k_mutnt=${p#boot-}"'),
    ("a value the plugin refuses", check_plugin, "menu_segments=4)", "menu_segments=3)"),
]


def _copy_with(tmp, src, name, old=None, new=None):
    text = read(src)
    if old is not None:
        assert old in text, "the mutant's anchor %r is not in %s" % (old, src)
        text = text.replace(old, new)
    path = os.path.join(tmp, name)
    with open(path, "w", newline="\n") as f:
        f.write(text)
    return path


def test_unchanged_copy_passes(tmp_path):
    """the negative control: the unchanged copy in a temp folder passes every check"""
    path = _copy_with(str(tmp_path), ARM_TEXT, "ft_arm_text.sh")
    for chk in (check_bytes, check_kinds, check_refusals, check_table, check_plugin):
        assert chk(path) == [], chk.__name__


@pytest.mark.parametrize("name,check,old,new", ARM_MUTANTS, ids=[m[0] for m in ARM_MUTANTS])
def test_arm_text_mutant_fails(tmp_path, name, check, old, new):
    path = _copy_with(str(tmp_path), ARM_TEXT, "ft_arm_text.sh", old, new)
    fails = check(path)
    print("MUTANT %s: %s fails: %s" % (name, check.__name__, fails))
    assert fails, "mutant %s: %s passed" % (name, check.__name__)


TOOL_MUTANTS = [
    ("install: a literal sentinel in the arm verb", INSTALL, check_install, "ft_vm_install.sh",
     'printf \'%s\' "${txt%x}" > "$ARM"', "printf 'seed=1\\nforce=none\\nmenu=1\\n' > \"$ARM\""),
    ("leased: a second list of the profiles", LEASED, check_leased, "ft_vm_leased.sh",
     'case "$KIND" in menu) N=1;;', 'case "$MODE" in boot) N=1;; esac\ncase "$KIND" in menu) N=1;;'),
    ("leased: the pid file named by the profile", LEASED, check_leased, "ft_vm_leased.sh",
     'PIDF="$OUT/launch-$KIND.pid"', 'PIDF="$OUT/launch-$MODE.pid"'),
    ("seat: force=ON written unconditionally", SEAT, check_seat, "frame_time_seat.ps1",
     "if ($ArmForce -eq 'ON') { $armLines += 'force=ON' }", "$armLines += 'force=ON'"),
    ("seat_v: the call without -ArmForce", SEAT_V, check_seat_v, "frame_time_seat_v.ps1",
     "& $seat -ArmForce ON }", "& $seat }"),
    ("seat_v: the call with -ArmForce none", SEAT_V, check_seat_v, "frame_time_seat_v.ps1",
     "& $seat -ArmForce ON }", "& $seat -ArmForce none }"),
    ("seat_v: exit code 1 not set before the call", SEAT_V, check_seat_v, "frame_time_seat_v.ps1",
     "$global:LASTEXITCODE = 1\n", ""),
    ("seat_v: the catch ends 0", SEAT_V, check_seat_v, "frame_time_seat_v.ps1",
     "$_.Exception.Message); exit 1 }", "$_.Exception.Message); exit 0 }"),
    ("seat_v: the entry of 12 Nov (the call outside a try)", SEAT_V, check_seat_v, "frame_time_seat_v.ps1",
     "try { do { & $seat -ArmForce ON } while ($false); $seatReturned = $true }\n" + SEAT_CATCH + "\n" + SEAT_FINALLY
     + "\n", "& $seat -ArmForce ON\n"),
    ("seat_v: no loop around the call", SEAT_V, check_seat_v, "frame_time_seat_v.ps1",
     "try { do { & $seat -ArmForce ON } while ($false); $seatReturned = $true }",
     "try { & $seat -ArmForce ON; $seatReturned = $true }"),
    ("seat_v: a second statement in the try", SEAT_V, check_seat_v, "frame_time_seat_v.ps1",
     "$seatReturned = $true }", "$seatReturned = $true; $global:LASTEXITCODE = 0 }"),
    ("seat_v: the returned flag set inside the loop", SEAT_V, check_seat_v, "frame_time_seat_v.ps1",
     "} while ($false); $seatReturned = $true }", "; $seatReturned = $true } while ($false) }"),
    ("seat_v: no finally", SEAT_V, check_seat_v, "frame_time_seat_v.ps1", SEAT_FINALLY + "\n", ""),
    ("seat_v: the finally ends 0", SEAT_V, check_seat_v, "frame_time_seat_v.ps1",
     "[Environment]::Exit(1)", "[Environment]::Exit(0)"),
    ("trial: the call without -TimeoutS", SEAT_TRIAL, check_seat_trial, "frame_time_seat_trial.ps1",
     "& $seat -ArmForce ON -TimeoutS 780 }", "& $seat -ArmForce ON }"),
    ("trial: the sitting's whole wait", SEAT_TRIAL, check_seat_trial, "frame_time_seat_trial.ps1",
     "-TimeoutS 780 }", "-TimeoutS 7200 }"),
    ("trial: the call without -ArmForce", SEAT_TRIAL, check_seat_trial, "frame_time_seat_trial.ps1",
     "& $seat -ArmForce ON -TimeoutS 780 }", "& $seat -TimeoutS 780 }"),
    ("trial: exit code 1 not set before the call", SEAT_TRIAL, check_seat_trial, "frame_time_seat_trial.ps1",
     "$global:LASTEXITCODE = 1\n", ""),
    ("trial: the catch ends 0", SEAT_TRIAL, check_seat_trial, "frame_time_seat_trial.ps1",
     "$_.Exception.Message); exit 1 }", "$_.Exception.Message); exit 0 }"),
    ("trial: no loop around the call", SEAT_TRIAL, check_seat_trial, "frame_time_seat_trial.ps1",
     "try { do { & $seat -ArmForce ON -TimeoutS 780 } while ($false); $seatReturned = $true }",
     "try { & $seat -ArmForce ON -TimeoutS 780; $seatReturned = $true }"),
    ("trial: no finally", SEAT_TRIAL, check_seat_trial, "frame_time_seat_trial.ps1", SEAT_FINALLY + "\n", ""),
    ("trial: the catch does not set the failed flag", SEAT_TRIAL, check_seat_trial, "frame_time_seat_trial.ps1",
     "catch { $seatFailed = $true; ", "catch { "),
    ("trial: the refusal names the other entry", SEAT_TRIAL, check_seat_trial, "frame_time_seat_trial.ps1",
     "is not beside frame_time_seat_trial.ps1", "is not beside frame_time_seat_v.ps1"),
]


@pytest.mark.parametrize("name,src,check,base,old,new", TOOL_MUTANTS, ids=[m[0] for m in TOOL_MUTANTS])
def test_tool_mutant_fails(tmp_path, name, src, check, base, old, new):
    path = _copy_with(str(tmp_path), src, base, old, new)
    fails = check(path)
    print("MUTANT %s: %s fails: %s" % (name, check.__name__, fails))
    assert fails, "mutant %s: %s passed" % (name, check.__name__)
