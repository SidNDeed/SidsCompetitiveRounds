"""test_ft_vm_install.py: the VM tools' writes are checked before a step reports success or the next step relies on
them (ruling R6-A3.11.151 (2) class C, the write side).

Every case runs a copy of the tool re-rooted in a temp folder (the game, the record folder and the lanes folder under
it; the process table read as empty), never the real game folder. The members: ft_vm_install.sh's arm (the sentinel
written, read back and compared before its written line), install (its two records read back; CURRENT written
before the plugin DLL changes, so an unwritable CURRENT leaves the DLL untouched and a failure after it leaves the
record open for revert, which then restores the prior DLL), revert (its records and the backup proven before it
writes; OK only with the sentinel gone and the record closed), status (an open install names its prior digest);
ft_arm_text.sh's standard output; ft_vm_leased.sh stopping before the launch
when the arm step ends nonzero; ft_vm_restore.sh's inventory lines and VR6's two listings. Each check is run on the
tool as it is and on a mutant per route, a copy with that route's check removed, which must fail it. The cases that
need a POSIX file-size limit, a symbolic link to /dev/null or the leased script's dry harness skip, with the reason,
where those do not exist.
"""
import hashlib
import os
import re
import shutil
import stat
import subprocess
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.join(HERE, "ft_vm_install.sh")
ARM_TEXT = os.path.join(HERE, "ft_arm_text.sh")
LEASED = os.path.join(HERE, "ft_vm_leased.sh")
RESTORE = os.path.join(HERE, "ft_vm_restore.sh")
POSIX = os.name == "posix"
try:
    import resource
    import signal
except ImportError:          # Windows: no file-size limit to set
    resource = signal = None

BOOT = b"seed=1\nforce=none\nmenu=1\nmenu_segments=4\n"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, data, mode="w"):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, mode + ("b" if isinstance(data, bytes) else ""), **({} if isinstance(data, bytes) else
                                                                        {"newline": "\n"})) as f:
        f.write(data)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(args, env=None, limit=None, cwd=None):
    """bash with args; limit: a file-size limit in bytes for the child (POSIX), SIGXFSZ ignored so a write past it
    fails instead of killing the shell"""
    pre = None
    if limit is not None:
        def pre():
            resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    p = subprocess.run(["bash"] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=120,
                       preexec_fn=pre, cwd=cwd)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def need_fsize():
    if not POSIX or resource is None or not hasattr(resource, "RLIMIT_FSIZE"):
        pytest.skip("no POSIX file-size limit on this seat: the write-failure case needs one")


def apply(text, edits, name):
    for old, new in edits:
        assert text.count(old) == 1, "%s: the anchor %r occurs %d times" % (name, old, text.count(old))
        text = text.replace(old, new)
    return text


# ---- ft_vm_install.sh in a temp folder

R_LINE = "R=C:/Users/Sid/Documents/SidsCompetitiveRounds\n"
G_LINE = 'GAME="C:/Program Files (x86)/Steam/steamapps/common/ROUNDS"\n'
RUN_LINE = "running() { /c/Windows/System32/tasklist.exe 2>/dev/null | grep -i -q 'ROUNDS.exe'; }\n"
ABSENT_CALL = 'python -I -B "$HERE/ft_absent.py" "$DLL" present > /dev/null 2>&1'


class Tree:
    """A re-rooted ft_vm_install.sh (optionally a mutant: edits applied after the re-rooting) and its tree."""

    def __init__(self, tmp, edits=(), name="ft_vm_install.sh"):
        self.tmp = str(tmp).replace("\\", "/")
        text = read(INSTALL)
        text = apply(text, [(R_LINE, 'R="%s/r"\n' % self.tmp), (G_LINE, 'GAME="%s/game"\n' % self.tmp),
                            (RUN_LINE, "running() { false; }\n"), (ABSENT_CALL, "true")], "re-root")
        assert text.count("C:/shared/builds/lanes/frametime-") == 2
        text = text.replace("C:/shared/builds/lanes/frametime-", "%s/lanes/frametime-" % self.tmp)
        text = apply(text, edits, name)
        self.bin = os.path.join(self.tmp, "bin")
        self.script = os.path.join(self.bin, "ft_vm_install.sh")
        write(self.script, text)
        shutil.copy(ARM_TEXT, os.path.join(self.bin, "ft_arm_text.sh"))
        self.plug = os.path.join(self.tmp, "game", "BepInEx", "plugins", "CompetitiveRounds", "CompetitiveRounds.dll")
        self.arm = os.path.join(self.tmp, "game", "BepInEx", "frametime", "arm")
        self.rec = os.path.join(self.tmp, "r", "ai-collab", "frame-time", "vm-install")
        self.cur = os.path.join(self.rec, "CURRENT")
        write(self.plug, b"release dll")
        os.makedirs(self.rec, exist_ok=True)

    def open_install(self, record=True):
        """an open install whose installed DLL is the lane's (as after install)"""
        bk = os.path.join(self.rec, "20261112T000000Z")
        write(os.path.join(bk, "CompetitiveRounds.dll"), b"release dll")
        if record:
            write(os.path.join(bk, "installed.sha256"), sha(b"release dll") + "\n")
        write(self.plug, b"lane dll")
        write(self.cur, bk + "\n")
        return bk

    def lanes(self):
        # "/"-joined: the tool's lanes-folder pattern is the re-rooted "<tmp>/lanes/frametime-" (os.path.join's "\"
        # on Windows matched no pattern, so install refused there before it ran)
        lanes = self.tmp + "/lanes/frametime-0123abcd"
        write(os.path.join(lanes, "CompetitiveRounds.dll"), b"lane dll")
        write(os.path.join(lanes, "sha256.txt"), sha(b"lane dll") + "  CompetitiveRounds.dll\n")
        dll = self.tmp + "/proof/lane-frametime.dll"
        write(dll, b"lane dll")
        return dll, lanes

    def __call__(self, *args, **kw):
        return run([self.script] + list(args), **kw)


def lines(out, word):
    return [ln for ln in out.splitlines() if word in ln]


# ---- the named checks (each returns its failures; empty = pass)


def check_arm_good(tmp, edits=()):
    t = Tree(tmp, edits)
    t.open_install()
    rc, out, err = t("arm", "boot")
    f = []
    ok = lines(out, "FT-VM-ARM boot written: ")
    if rc != 0 or len(ok) != 1 or not ok[0].endswith(BOOT.decode().replace("\n", " ")) or lines(out, "FAIL"):
        f.append("good write: rc %s, out %r" % (rc, out))
    if not os.path.isfile(t.arm) or open(t.arm, "rb").read() != BOOT:
        f.append("good write: the sentinel is not the profile's bytes")
    return f


def _arm_fail(out, rc, want):
    """exactly one line, starting FT-VM-ARM FAIL and holding want, exit 3, no written line"""
    f = []
    if rc != 3:
        f.append("rc %s, not 3" % rc)
    if lines(out, "written:"):
        f.append("a written line: %r" % out)
    fl = [ln for ln in out.splitlines() if ln.startswith("FT-VM-ARM FAIL")]
    if len(fl) != 1 or want not in fl[0] or len(out.splitlines()) != 1:
        f.append("not one FT-VM-ARM FAIL line naming %r: %r" % (want, out))
    return f


def check_arm_unwritable(tmp, edits=()):
    """the sentinel's path is a folder: the write fails"""
    t = Tree(tmp, edits)
    t.open_install()
    os.makedirs(t.arm)
    rc, out, _ = t("arm", "boot")
    return ["unwritable: " + x for x in _arm_fail(out, rc, "could not be written")]


def check_arm_no_folder(tmp, edits=()):
    """the sentinel's folder is a file: the folder cannot be made"""
    t = Tree(tmp, edits)
    t.open_install()
    write(os.path.dirname(t.arm), b"a file")
    rc, out, _ = t("arm", "boot")
    return ["no folder: " + x for x in _arm_fail(out, rc, "could not be made")]


def check_arm_read_back(tmp, edits=()):
    """the sentinel is a link to /dev/null: the write succeeds and reads back empty"""
    if not POSIX or not os.path.exists("/dev/null"):
        pytest.skip("no /dev/null to link the sentinel to on this seat")
    t = Tree(tmp, edits)
    t.open_install()
    os.makedirs(os.path.dirname(t.arm))
    try:
        os.symlink("/dev/null", t.arm)
    except OSError as e:
        pytest.skip("no symbolic link on this seat: %s" % e)
    rc, out, _ = t("arm", "boot")
    return ["read-back: " + x for x in _arm_fail(out, rc, "does not read back")]


def check_arm_record(tmp, edits=()):
    """the open install's digest record is missing: refused, nothing written"""
    t = Tree(tmp, edits)
    t.open_install(record=False)
    rc, out, _ = t("arm", "boot")
    f = []
    if rc != 2 or "FT-VM-INSTALL REFUSED: the open install's record" not in out or os.path.exists(t.arm):
        f.append("record: rc %s, out %r, sentinel %s" % (rc, out, os.path.exists(t.arm)))
    return f


def check_revert(tmp, edits=()):
    """a good revert: OK, sentinel absent, the record closed under its stamp"""
    t = Tree(tmp, edits)
    bk = t.open_install()
    write(t.arm, BOOT)
    rc, out, _ = t("revert")
    done = [x for x in os.listdir(t.rec) if x.startswith("CURRENT.reverted-")]
    f = []
    if rc != 0 or len(lines(out, "FT-VM-REVERT OK restored %s sentinel absent" % sha(b"release dll"))) != 1:
        f.append("revert: rc %s, out %r" % (rc, out))
    if os.path.exists(t.cur) or len(done) != 1 or read(os.path.join(t.rec, done[0])).strip() != bk:
        f.append("revert: the record is not closed (%s, %s)" % (os.path.exists(t.cur), done))
    if os.path.exists(t.arm) or open(t.plug, "rb").read() != b"release dll":
        f.append("revert: the sentinel or the DLL is not restored")
    return f


def check_revert_sentinel(tmp, edits=()):
    """the sentinel cannot be removed (a folder holding a file): FAIL, exit 3, the install left open"""
    t = Tree(tmp, edits)
    t.open_install()
    write(os.path.join(t.arm, "held"), b"x")
    rc, out, _ = t("revert")
    f = []
    if rc != 3 or lines(out, "REVERT OK") or len(lines(out, "FT-VM-REVERT FAIL")) != 1 or "still present" not in out:
        f.append("revert sentinel: rc %s, out %r" % (rc, out))
    if not os.path.exists(t.cur):
        f.append("revert sentinel: the install was closed")
    return f


def check_revert_record(tmp, edits=()):
    """the record cannot be closed (every stamp of the next seconds is a folder holding a file): FAIL, exit 3"""
    t = Tree(tmp, edits)
    t.open_install()
    now = time.time()
    for s in range(-2, 30):
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now + s))
        write(os.path.join(t.rec, "CURRENT.reverted-" + stamp, "held"), b"x")
    rc, out, _ = t("revert")
    f = []
    if rc != 3 or lines(out, "REVERT OK") or len(lines(out, "FT-VM-REVERT FAIL")) != 1 or "not closed" not in out:
        f.append("revert record: rc %s, out %r" % (rc, out))
    if not os.path.exists(t.cur):
        f.append("revert record: CURRENT is gone")
    return f


def check_install_good(tmp, edits=()):
    t = Tree(tmp, edits)
    dll, lanes = t.lanes()
    rc, out, _ = t("install", dll, lanes)
    f = []
    ok = lines(out, "FT-VM-INSTALL OK installed %s prior %s backup " % (sha(b"lane dll"), sha(b"release dll")))
    if rc != 0 or len(ok) != 1:
        f.append("install: rc %s, out %r" % (rc, out))
        return f
    bk = ok[0].split(" backup ", 1)[1]
    if read(t.cur).strip() != bk or read(os.path.join(bk, "installed.sha256")).strip() != sha(b"release dll"):
        f.append("install: the records do not hold the backup and its digest")
    return f


def check_install_records(tmp, edits=()):
    """a file-size limit that fails the digest record (65 bytes, the DLLs 8 and 11), then one that fails CURRENT
    (the backup's path, longer than the limit): FAIL, exit 3, no OK line, each time"""
    need_fsize()
    f = []
    for limit, want in ((20, "backup record"), (70, "open-install record")):
        t = Tree(os.path.join(str(tmp), "l%d" % limit), edits)
        dll, lanes = t.lanes()
        if limit == 70 and len(os.path.join(t.rec, "20261112T000000Z")) <= limit + 1:
            pytest.skip("the temp folder's path is too short for the CURRENT case")
        rc, out, _ = t("install", dll, lanes, limit=limit)
        if rc != 3 or lines(out, "INSTALL OK") or len(lines(out, "FT-VM-INSTALL FAIL")) != 1 or want not in out:
            f.append("install limit %d: rc %s, out %r" % (limit, rc, out))
    return f


# the record CURRENT's path: check_install_current_unwritable re-roots it into a folder that does not exist
CUR_LINE = 'CUR="$REC/CURRENT"\n'
PLUG_TAIL = "/game/BepInEx/plugins/CompetitiveRounds/CompetitiveRounds.dll"
# the stand-in cp, first on PATH: the copy onto $FT_TEST_PLUG fails (FT_TEST_CP=fail) or leaves other bytes there
# (corrupt); every other copy is the real cp
CP_SHIM = '''#!/usr/bin/env bash
last="${@: -1}"
if [ "$last" = "$FT_TEST_PLUG" ]; then
  case "$FT_TEST_CP" in fail) echo "stand-in cp: refused $last" >&2; exit 1;; corrupt) printf 'other bytes' > "$last"; exit 0;; esac
fi
command -p cp "$@"
'''
# the head of a failure that says the check's own machinery did not run (a stand-in that did not act): such a failure
# is no kill of a mutant (test_mutant_fails)
HARNESS = "harness: "


def _digest(path):
    with open(path, "rb") as f:
        return sha(f.read())


def check_install_current_unwritable(tmp, edits=()):
    """the open-install record CURRENT cannot be written (CUR re-rooted into a folder that does not exist, so the
    redirection fails and nothing else changes): FAIL, exit 3, no OK line, the FAIL line says nothing was installed,
    the plugin DLL's sha256 unchanged, no record left"""
    t = Tree(tmp, list(edits) + [(CUR_LINE, 'CUR="$REC/absent-folder/CURRENT"\n')])
    dll, lanes = t.lanes()
    before = _digest(t.plug)
    rc, out, _ = t("install", dll, lanes)
    f = []
    fail = lines(out, "FT-VM-INSTALL FAIL")
    if rc != 3 or lines(out, "INSTALL OK") or len(fail) != 1 or "open-install record" not in fail[0] \
            or "the plugin DLL is untouched" not in fail[0]:
        f.append("install, CURRENT unwritable: rc %s, out %r" % (rc, out))
    if _digest(t.plug) != before:
        f.append("install, CURRENT unwritable: the plugin DLL changed (%s -> %s)" % (before, _digest(t.plug)))
    if os.path.exists(os.path.join(t.rec, "absent-folder")):
        f.append("install, CURRENT unwritable: a record was left")
    return f


def check_install_fails_after_record(tmp, edits=()):
    """a failure after CURRENT is written, each way (the stand-in cp, first on PATH, acting only on the plugin DLL's
    path): the copy fails, or it leaves other bytes. Each: FAIL, exit 3, no OK line, the FAIL line naming the open
    record ("the install record stays open: run revert"), CURRENT holding the backup folder. Then revert with the real
    cp: OK, the plugin DLL's sha256 the prior one, CURRENT gone and closed as CURRENT.reverted-<stamp>. The stand-in is
    written executable (a POSIX seat's shell passes over a file on PATH without that bit and runs the real cp), and each
    case proves that it acted"""
    f = []
    for how in ("fail", "corrupt"):
        t = Tree(os.path.join(str(tmp), how), edits)
        dll, lanes = t.lanes()
        prior = _digest(t.plug)
        shim = os.path.join(t.tmp, "shim")
        _exe(os.path.join(shim, "cp"), CP_SHIM)
        env = dict(os.environ, FT_TEST_PLUG=t.tmp + PLUG_TAIL, FT_TEST_CP=how,
                   PATH=shim + os.pathsep + os.environ.get("PATH", ""))
        rc, out, err = t("install", dll, lanes, env=env)
        fail = lines(out, "FT-VM-INSTALL FAIL")
        if rc != 3 or lines(out, "INSTALL OK") or len(fail) != 1 or "the install record stays open: run revert" not in fail[0]:
            f.append("install %s after CURRENT: rc %s, out %r, err %r" % (how, rc, out, err[-400:]))
        bk = read(t.cur).strip() if os.path.isfile(t.cur) else ""
        if not bk or not os.path.isfile(os.path.join(bk, "CompetitiveRounds.dll")):
            f.append("install %s after CURRENT: CURRENT does not hold the backup folder (%r)" % (how, bk))
        # a refused copy leaves the prior DLL and the stand-in's own line on standard error; a corrupting one leaves
        # the stand-in's bytes
        acted = (("stand-in cp: refused" in err and _digest(t.plug) == prior) if how == "fail"
                 else _digest(t.plug) == sha(b"other bytes"))
        if not acted:
            f.append(HARNESS + "the stand-in cp did not act in the %s case" % how)
        rc, out, _ = t("revert")
        done = [x for x in os.listdir(t.rec) if x.startswith("CURRENT.reverted-")]
        if rc != 0 or len(lines(out, "FT-VM-REVERT OK restored %s sentinel absent" % prior)) != 1:
            f.append("revert after %s: rc %s, out %r" % (how, rc, out))
        if _digest(t.plug) != prior:
            f.append("revert after %s: the plugin DLL is not the prior one" % how)
        if os.path.exists(t.cur) or len(done) != 1 or read(os.path.join(t.rec, done[0])).strip() != bk:
            f.append("revert after %s: the record is not closed (%s, %s)" % (how, os.path.exists(t.cur), done))
    return f


def check_revert_proves_first(tmp, edits=()):
    """revert proves its records and the backup before it writes: with the backup's digest record missing it refuses
    (exit 2), and with a backup whose bytes differ from the record it FAILs (exit 3); each time the plugin DLL keeps
    the lane's bytes and CURRENT stays"""
    f = []
    for case in ("no record", "backup differs"):
        t = Tree(os.path.join(str(tmp), case.replace(" ", "-")), edits)
        bk = t.open_install(record=case != "no record")
        if case == "backup differs":
            write(os.path.join(bk, "CompetitiveRounds.dll"), b"other bytes")
        rc, out, _ = t("revert")
        # refuse() prints the tool's one refusal head, FT-VM-INSTALL REFUSED, for every subcommand
        want = ((2, "FT-VM-INSTALL REFUSED: the open install's records are unreadable") if case == "no record"
                else (3, "FT-VM-REVERT FAIL the backup"))
        if rc != want[0] or want[1] not in out or lines(out, "REVERT OK") or "nothing restored" not in out:
            f.append("revert, %s: rc %s, out %r" % (case, rc, out))
        if _digest(t.plug) != sha(b"lane dll") or not os.path.exists(t.cur):
            f.append("revert, %s: the plugin DLL changed or the record was closed" % case)
    return f


def check_status_open(tmp, edits=()):
    """status: with no open install the line ends " open none"; with one, " open <backup> prior <its recorded digest>"
    """
    t = Tree(tmp, edits)
    f = []
    rc, out, _ = t("status")
    if rc != 0 or not out.rstrip("\n").endswith(" open none"):
        f.append("status, none open: rc %s, out %r" % (rc, out))
    bk = t.open_install()
    rc, out, _ = t("status")
    if rc != 0 or not out.rstrip("\n").endswith(" open %s prior %s" % (bk, sha(b"release dll"))):
        f.append("status, open: rc %s, out %r" % (rc, out))
    return f


def check_arm_text_stdout(tmp, edits=()):
    """ft_arm_text.sh with its standard output closed: exit 3, its one line on standard error (bash's own printf
    write error may precede it)"""
    p = os.path.join(str(tmp), "ft_arm_text.sh")
    write(p, apply(read(ARM_TEXT), edits, "ft_arm_text.sh"))
    rc, out, err = run(["-c", 'bash "$0" menu >&-', p])
    rc2, out2, _ = run([p, "menu"])
    mine = [ln for ln in err.splitlines() if ln.startswith("ft_arm_text.sh:")]
    f = []
    if rc != 3 or mine != ["ft_arm_text.sh: the write to standard output failed"]:
        f.append("stdout closed: rc %s, stderr %r" % (rc, err))
    if rc2 != 0 or out2 != "seed=1\nforce=none\nmenu=1\n":
        f.append("stdout open: rc %s, out %r" % (rc2, out2))
    return f


# ---- ft_vm_leased.sh stops before the launch when the arm step ends nonzero (its dry harness)

SHIM = r'''#!/usr/bin/env bash
# the stand-in dispatcher: every powershell call of ft_vm_leased.sh in test mode
T="$(cd "$(dirname "$0")/.." && pwd)"
f=""; prev=""; st=0
for a in "$@"; do [ "$prev" = "-File" ] && f="$a"; [ "$a" = "-Status" ] && st=1; prev="$a"; done
echo "$(basename "$f") $*" >> "$T/calls.txt"
case "$(basename "$f")" in
  pause.ps1)
    if [ "$st" = 1 ]; then
      if [ -e "$T/held" ]; then echo "holders (1):"; echo "  frame-time  (since 2026-11-12T00:00:00Z)"; else echo "holders: none"; fi
    else : > "$T/held"; echo "Broadcast bot PAUSED; holder frame-time"; fi; exit 0;;
  resume.ps1) rm -f "$T/held"; exit 0;;
  ft_vm_launch.ps1) : > "$T/LAUNCHED"; exit 0;;
  ft_close_leased.ps1) exit 7;;
  *) exit 0;;
esac
'''
CYGPATH = '#!/usr/bin/env bash\nprintf "%s\\n" "${@: -1}"\n'
STUB_INSTALL = '''#!/usr/bin/env bash
# the stand-in install step: arm ends with $ARM_RC
case "$1" in
  status) echo "stamp FT-VM-STATUS installed x sentinel absent open none";;
  arm) echo "stand-in arm rc ${ARM_RC}"; exit "${ARM_RC}";;
  *) echo "stand-in $1";;
esac
exit 0
'''


def _exe(path, text):
    write(path, text)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def check_leased_arm_stop(tmp, edits=(), arm_rc=3):
    """the leased script's dry run up to the launch, with a stand-in arm step ending arm_rc: it must print the arm
    line, never launch and end rc=2 (arm_rc 0: it must launch, the harness's negative control)"""
    if not POSIX:
        pytest.skip("the leased script's dry harness compares POSIX paths: run on a POSIX seat")
    T = str(tmp)
    src = os.path.join(T, "tools")
    os.makedirs(src)
    leased = os.path.join(src, "ft_vm_leased.sh")
    write(leased, apply(read(LEASED), edits, "ft_vm_leased.sh"))
    for x in (RESTORE, ARM_TEXT):
        shutil.copy(x, src)
    _exe(os.path.join(T, "shim", "powershell"), SHIM)
    _exe(os.path.join(T, "shim", "cygpath"), CYGPATH)
    _exe(os.path.join(T, "bin", "ft_vm_install.sh"), STUB_INSTALL)
    write(os.path.join(T, "game", "BepInEx", "plugins", "CompetitiveRounds", "CompetitiveRounds.dll"), b"release dll")
    write(os.path.join(T, "game", "BepInEx", "config", "com.competitiverounds.mod.cfg"), b"[A]\nk = 1\n")
    write(os.path.join(T, "close", "procs.txt"), "")
    write(os.path.join(T, "lane.dll"), b"lane dll")
    os.makedirs(os.path.join(T, "lanes"))
    os.makedirs(os.path.join(T, "low"))
    env = dict(os.environ, FT_VM_TEST_DIR=T, FT_CLOSE_TEST_DIR=os.path.join(T, "close"),
               FT_VM_LOCALLOW=os.path.join(T, "low"), ARM_RC=str(arm_rc),
               PATH=os.path.join(T, "shim") + os.pathsep + os.environ.get("PATH", ""))
    rc, out, err = run([leased, "boot", os.path.join(T, "out"), os.path.join(T, "lane.dll"), os.path.join(T, "lanes")],
                       env=env)
    launched = os.path.exists(os.path.join(T, "LAUNCHED"))
    last = out.rstrip("\n").splitlines()[-1] if out.strip() else ""
    f = []
    if "stand-in arm rc %d" % arm_rc not in out:
        f.append("leased: the arm step did not run (rc %s, out %r, err %r)" % (rc, out[-2000:], err[-1000:]))
    elif arm_rc != 0:
        if launched or not re.search(r"FT-VM-LEASED the arm step ended rc=%d: nothing launched" % arm_rc, out):
            f.append("leased: launched %s after an arm rc %d (out %r)" % (launched, arm_rc, out[-2000:]))
        if not last.endswith("FT-VM-LEASED boot end rc=2"):
            f.append("leased: the last line is %r, not end rc=2" % last)
    elif not launched:
        f.append("leased: the control (arm rc 0) did not launch (out %r)" % out[-2000:])
    return f


# ---- ft_vm_restore.sh: the inventory's lines and VR6's listings

HARNESS = r'''#!/usr/bin/env bash
# sources ft_vm_restore.sh beside it and runs one of its steps
HERE="$(cd "$(dirname "$0")" && pwd)"
T="$1"; step="$2"
BEP="$T/game/BepInEx"; CONFDIR="$BEP/config"; OUT="$T/out"; PRE="$OUT/pre"; CFG="$CONFDIR/com.competitiverounds.mod.cfg"
LOGN=(LogOutput.log LogOutput-prev.log output_log.txt Player.log Player-prev.log)
LOGP=("$BEP/LogOutput.log" "$BEP/LogOutput-prev.log" "$T/game/output_log.txt" "$T/low/Player.log" "$T/low/Player-prev.log")
bad=0
# FAIL_AREA=<area>: the inventory's line writes for that area end 1 (the stand-in for a write that fails there; a
# file-size limit cannot fail one area alone, every later write fails with it)
if [ -n "${FAIL_AREA:-}" ]; then echo() { case "${1:-}" in "$FAIL_AREA "*) return 1;; esac; builtin echo "$@"; }; fi
. "$HERE/ft_vm_restore.sh"
case "$step" in
  inventory) inventory "$OUT/inv.txt"; echo "inventory rc=$?";;
  vr6) inventory() { return 0; }; ft_vr6_check; echo "vr6 bad=$bad";;
esac
'''


def _restore_tree(tmp, edits):
    T = str(tmp)
    write(os.path.join(T, "tools", "ft_vm_restore.sh"), apply(read(RESTORE), edits, "ft_vm_restore.sh"))
    write(os.path.join(T, "tools", "harness.sh"), HARNESS)
    write(os.path.join(T, "game", "BepInEx", "plugins", "CompetitiveRounds", "CompetitiveRounds.dll"), b"release dll")
    write(os.path.join(T, "game", "BepInEx", "config", "com.competitiverounds.mod.cfg"), b"[A]\nk = 1\n")
    os.makedirs(os.path.join(T, "out"))
    os.makedirs(os.path.join(T, "low"))
    return T


def check_inventory_write(tmp, edits=()):
    """with no limit the inventory is whole (rc 0, seven lines); a file-size limit that admits the plugins and config
    lines exactly fails the first log line's write (rc 1, its FAILED line); the config line's write ending 1 (the
    harness's FAIL_AREA) gives the same"""
    need_fsize()
    T = _restore_tree(tmp, edits)
    first = "plugins CompetitiveRounds/CompetitiveRounds.dll %s\n" % sha(b"release dll")
    second = "config com.competitiverounds.mod.cfg %s\n" % sha(b"[A]\nk = 1\n")
    harness = os.path.join(T, "tools", "harness.sh")
    inv_path = os.path.join(T, "out", "inv.txt")
    rc, out, _ = run([harness, T, "inventory"])
    f = []
    inv = read(inv_path) if os.path.exists(inv_path) else ""
    if "inventory rc=0" not in out or inv.count("\n") != 7 or first not in inv or second not in inv:
        f.append("inventory control: out %r, inventory %r" % (out, inv))
    for how, kw in (("limit", {"limit": len(first) + len(second)}),
                    ("config", {"env": dict(os.environ, FAIL_AREA="config")})):
        for x in (inv_path, inv_path + ".part"):
            if os.path.exists(x):
                os.remove(x)
        rc, out, _ = run([harness, T, "inventory"], **kw)
        if "inventory rc=1" not in out or "FT-VM-INVENTORY write of" not in out:
            f.append("inventory %s: out %r" % (how, out))
    return f


def check_vr6_listing(tmp, edits=()):
    """VR6's two listings under a file-size limit that cuts both after the same first line, the inventories
    differing after it: never a PASS; with no limit the difference is a FAIL too (the control reads them whole)"""
    need_fsize()
    T = _restore_tree(tmp, edits)
    head = "config com.competitiverounds.mod.cfg %s\n" % ("a" * 64)
    write(os.path.join(T, "out", "inventory-pre.txt"), head + "config z.cfg %s\n" % ("1" * 64))
    write(os.path.join(T, "out", "inventory-sitting.txt"), head + "config z.cfg %s\n" % ("2" * 64))
    f = []
    for limit in (None, len(head)):
        rc, out, _ = run([os.path.join(T, "tools", "harness.sh"), T, "vr6"], limit=limit)
        if "vr6 bad=1" not in out or "FT-VM-VR6 files PASS" in out:
            f.append("vr6 limit %s: out %r" % (limit, out))
    return f


# ---- the tests on the tools as they are


CHECKS = [check_arm_good, check_arm_unwritable, check_arm_no_folder, check_arm_read_back, check_arm_record,
          check_revert, check_revert_sentinel, check_revert_record, check_install_good, check_install_records,
          check_install_current_unwritable, check_install_fails_after_record, check_revert_proves_first,
          check_status_open, check_arm_text_stdout, check_leased_arm_stop, check_inventory_write, check_vr6_listing]


@pytest.mark.parametrize("check", CHECKS, ids=[c.__name__ for c in CHECKS])
def test_tool_passes(tmp_path, check):
    fails = check(tmp_path)
    assert fails == [], fails


def test_leased_launches_when_the_arm_step_passes(tmp_path):
    """the harness's negative control: with a stand-in arm step that ends 0, the launch runs"""
    assert check_leased_arm_stop(tmp_path, arm_rc=0) == []


# ---- the mutants: a copy of the tool with one route's check removed, each failing its named check

ARM_WRITE = ('printf \'%s\' "${txt%x}" > "$ARM" || { echo "FT-VM-ARM FAIL $mode: the sentinel $ARM could not be '
             'written"; exit 3; }')
ARM_READ = ('printf \'%s\' "${txt%x}" | cmp -s - "$ARM" || { echo "FT-VM-ARM FAIL $mode: the sentinel $ARM does not '
            'read back as the profile\'s text"; exit 3; }')
ARM_DIR = ('mkdir -p "$(dirname "$ARM")" || { echo "FT-VM-ARM FAIL $mode: the folder of $ARM could not be made"; '
           'exit 3; }')
# install's order: the record CURRENT, then the copy (the tool's text), and the earlier order, the copy and its digest
# check first and CURRENT after (the negative control of both order checks)
INSTALL_ORDER = r'''    printf '%s\n' "$BK" > "$CUR" && [ "$(cat "$CUR" 2>/dev/null)" = "$BK" ] \
      || { rm -f "$CUR" 2>/dev/null
           echo "FT-VM-INSTALL FAIL the open-install record $CUR not written (nothing installed: the plugin DLL is untouched; the backup is $BK; $([ -e "$CUR" ] && echo "a partial record remains at $CUR" || echo "no record left"))"; exit 3; }
    cp "$DLL" "$PLUG" || { echo "FT-VM-INSTALL FAIL copy (the install record stays open: run revert)"; exit 3; }
    now=$(sha "$PLUG")
    [ "$now" = "$want" ] || { echo "FT-VM-INSTALL FAIL installed $now, wanted $want (the install record stays open: run revert)"; exit 3; }
'''
INSTALL_OLD_ORDER = r'''    cp "$DLL" "$PLUG" || { echo "FT-VM-INSTALL FAIL copy"; exit 3; }
    now=$(sha "$PLUG")
    [ "$now" = "$want" ] || { echo "FT-VM-INSTALL FAIL installed $now, wanted $want"; exit 3; }
    printf '%s\n' "$BK" > "$CUR" && [ "$(cat "$CUR" 2>/dev/null)" = "$BK" ] \
      || { echo "FT-VM-INSTALL FAIL the open-install record $CUR not written (installed $now; the backup is $BK)"; exit 3; }
'''
REVERT_PROOF = r'''    [ -n "$BK" ] && [ "${#want}" = 64 ] || refuse "the open install's records are unreadable ($CUR names '$BK'; its installed.sha256 holds '$want'): nothing restored"
    [ "$(sha "$BK/CompetitiveRounds.dll" 2>/dev/null)" = "$want" ] \
      || { echo "FT-VM-REVERT FAIL the backup $BK/CompetitiveRounds.dll does not hold the recorded digest $want (nothing restored; the install stays open)"; exit 3; }
'''
MUTANTS = [
    # (name, the check it must fail, the file, old, new)
    ("arm: the write's check removed", check_arm_unwritable, "ft_vm_install.sh", ARM_WRITE,
     'printf \'%s\' "${txt%x}" > "$ARM"'),
    ("arm: the read-back removed", check_arm_read_back, "ft_vm_install.sh", ARM_READ, ":"),
    ("arm: the folder's check removed", check_arm_no_folder, "ft_vm_install.sh", ARM_DIR, 'mkdir -p "$(dirname "$ARM")"'),
    ("arm: the record's check removed", check_arm_record, "ft_vm_install.sh",
     '''    [ "${#rec}" = 64 ] || refuse "the open install's record of the backed-up DLL's digest is unreadable"\n''', ""),
    ("revert: the sentinel's check removed", check_revert_sentinel, "ft_vm_install.sh",
     '[ -e "$ARM" ] && { echo "FT-VM-REVERT FAIL', 'false && { echo "FT-VM-REVERT FAIL'),
    ("revert: the record's check removed", check_revert_record, "ft_vm_install.sh",
     '[ ! -e "$CUR" ] && [ "$(cat "$done_rec" 2>/dev/null)" = "$BK" ] \\\n      || {',
     'true \\\n      || {'),
    ("install: the digest record's check removed", check_install_records, "ft_vm_install.sh",
     'printf \'%s\\n\' "$prior" > "$BK/installed.sha256" && [ "$(cat "$BK/installed.sha256" 2>/dev/null)" = "$prior" ]',
     'printf \'%s\\n\' "$prior" > "$BK/installed.sha256"; true'),
    ("install: CURRENT's check removed", check_install_records, "ft_vm_install.sh",
     'printf \'%s\\n\' "$BK" > "$CUR" && [ "$(cat "$CUR" 2>/dev/null)" = "$BK" ]',
     'printf \'%s\\n\' "$BK" > "$CUR"; true'),
    ("install: the earlier order, CURRENT unwritable", check_install_current_unwritable, "ft_vm_install.sh",
     INSTALL_ORDER, INSTALL_OLD_ORDER),
    ("install: the earlier order, a failure after the copy", check_install_fails_after_record, "ft_vm_install.sh",
     INSTALL_ORDER, INSTALL_OLD_ORDER),
    ("revert: the records and the backup not proven first", check_revert_proves_first, "ft_vm_install.sh",
     REVERT_PROOF, ""),
    ("status: the open install's prior digest not named", check_status_open, "ft_vm_install.sh",
     '      o="$ob prior $op"\n', '      o="$ob"\n'),
    ("arm text: the standard output's check removed", check_arm_text_stdout, "ft_arm_text.sh",
     ' \\\n  || { echo "ft_arm_text.sh: the write to standard output failed" >&2; exit 3; }', ""),
    ("leased: the arm step's stop removed", check_leased_arm_stop, "ft_vm_leased.sh",
     'if [ "$ar" != 0 ]; then echo "$(st) FT-VM-LEASED the arm step ended rc=$ar: nothing launched"; exit 2; fi', ":"),
    ("restore: the inventory folder line's check removed", check_inventory_write, "ft_vm_restore.sh",
     '      echo "$area ${f#"$dir/"} $s" >> "$tmp" || { echo "$(st) FT-VM-INVENTORY write of $tmp FAILED"; return 1; }',
     '      echo "$area ${f#"$dir/"} $s" >> "$tmp"'),
    ("restore: the inventory log line's check removed", check_inventory_write, "ft_vm_restore.sh",
     '    echo "log ${LOGN[$i]} $s" >> "$tmp" || { echo "$(st) FT-VM-INVENTORY write of $tmp FAILED"; return 1; }',
     '    echo "log ${LOGN[$i]} $s" >> "$tmp"'),
    ("restore: VR6's listing check removed", check_vr6_listing, "ft_vm_restore.sh",
     '  if [ "$g1" -gt 1 ] || [ "$g2" -gt 1 ]; then', '  if false; then'),
]


@pytest.mark.parametrize("name,check,base,old,new", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_mutant_fails(tmp_path, name, check, base, old, new):
    fails = check(tmp_path, edits=[(old, new)])
    print("MUTANT %s: %s fails: %s" % (name, check.__name__, fails))
    assert fails, "mutant %s: %s passed" % (name, check.__name__)
    assert not [x for x in fails if x.startswith(HARNESS)], \
        "mutant %s: %s did not run: %s" % (name, check.__name__, fails)


def test_mutant_anchors_hold():
    """every mutant's anchor occurs exactly once in its tracked file (a mutant whose anchor moved would test nothing)"""
    for name, _, base, old, _ in MUTANTS:
        assert read(os.path.join(HERE, base)).count(old) == 1, name


if __name__ == "__main__":
    # python test_ft_vm_install.py <dir>: each mutant's copy (the tracked file with that route's check removed, not
    # re-rooted) written to <dir>, for the record; the tests build their own copies in temp folders
    import sys
    for i, (name, check, base, old, new) in enumerate(MUTANTS, 1):
        p = os.path.join(sys.argv[1], "m%02d-%s" % (i, base))
        write(p, apply(read(os.path.join(HERE, base)), [(old, new)], name))
        print("%s -> %s: %s" % (p, check.__name__, name))
