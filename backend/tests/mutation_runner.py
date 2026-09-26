"""Plant a named mutation, print what was planted, run its check, put it back.

WHY THIS EXISTS
  A negative control is worth exactly what a reader can re-derive from it. Bug
  392's rating-moving control was run three rounds running and every round
  recorded the same thing: a variant name, a digest and a pytest summary. None
  of those is the mutation. A reader could not tell the plant that reddens the
  containment check from any other edit that would redden it just as well, so
  the control certified nothing it claimed to certify (#391, #342).

  So this file carries the plants as DATA, in `PLANTS` below, and prints each
  one as a unified diff into the log beside the run it produced. The evidence
  is the diff and the named failing assertion, not a summary line.

THE ORDER, WHICH IS THE POINT
  Per plant, and refusing rather than continuing at each step:

    1. `git status --porcelain` over the worktree must be EMPTY, and the check
       is printed. A plant applied to a tree that already carries uncommitted
       work cannot be separated from that work afterwards.
    2. `git rev-parse HEAD` is printed, and asserted against `--expect-head`
       when one is given -- a certification bound to no commit is a
       certification of whatever the tree happened to hold.
    3. The plant's old text must occur EXACTLY ONCE in the target. Not "at
       least once": a plant with two candidate sites lands somewhere a reader
       cannot name (#432).
    4. The target's sha256 is printed BEFORE the write.
    5. The plant is applied, and printed as a unified diff with the file name
       and the real line numbers.
    6. The check runs, and its tail is printed -- including, for a plant that
       must redden, the assertion line that failed.
    7. The target is restored from the bytes read in step 4, the sha256 is
       printed AFTER and must equal the one before, and `git status
       --porcelain` must be empty again.
    8. `RESULT <name>:` RED as required, GREEN as required, or FAILED.

  Restoration is in a `finally`, so a plant that raises still puts the file
  back. Because the tree is clean before and after every plant, and the runner
  is the only writer between the two checks, a plant on an api file leaves
  nothing behind -- which is what makes it allowable on files this lane's
  briefs otherwise forbid editing.

WHAT IT DELIBERATELY DOES NOT DO
  It does not decide whether a control reddened for the RIGHT reason. It
  prints the diff and the assertion and lets the reader decide, because a
  runner that judged that would be asserting the thing under review.

Usage:

    python backend/tests/mutation_runner.py --log <path> --notes <path> \\
        --client-lane <dir> [--expect-head <ref>] [--only NAME ...]

Exit codes: 0 every plant produced its required result, 1 at least one did
not, 2 the runner refused to start.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import io
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
WT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import notes_citations  # noqa: E402  (after sys.path, by design)

# ── The plants. ───────────────────────────────────────────────────────────────
# `old` and `new` are written with bare newlines and re-rendered into the
# target file's own line ending before anything is matched: this tree's
# main.py is CRLF, and a pattern built with a bare newline matches nothing at
# all. A plant that refuses is visible; one that lands in the wrong place is
# not.

_SITE = ("        chg = rating_changes.get(p.steam_id)\n")
_LEI = ('               "lei": bool(p.left_early) and str(pid) '
        'in _involuntary_departed,\n')
_LT = "tests/test_ffa_leave_cause.py"
_CONTAINMENT = "test_reconciled_set_is_read_only_by_the_match_row_insert"


@dataclass
class Plant:
    name: str
    kind: str                     # "control" (must redden) or "twin" (must not)
    target: str                   # "wt:<path>" or "notes:"
    old: str = ""                 # exact text, or "" when `derive` supplies it
    new: str = ""
    derive: str = ""              # name of a derivation in DERIVATIONS
    check: str = "pytest"         # "pytest" or "cmd"
    run: str = ""                 # pytest target, relative to backend/
    red: list[str] = field(default_factory=list)   # node ids that MUST fail
    argv: list[str] = field(default_factory=list)  # for check == "cmd"
    expect_exit: int = 0          # for check == "cmd"
    why: str = ""


PLANTS: list[Plant] = [
    Plant(
        name="M4", kind="control", target="wt:backend/api/main.py",
        old=_SITE,
        new=_SITE + ("        if str(pid) in _involuntary_departed:\n"
                     "            chg = None\n"),
        check="pytest", run=_LT, red=[_CONTAINMENT],
        why="the attested cause silently moving a rating: the reconciled set "
            "read where the rating change is computed, which is OUTSIDE the "
            "ffa_match_players INSERT. This is the mutation bug 392's "
            "display-only claim rests on.",
    ),
    Plant(
        name="TWIN-A", kind="twin", target="wt:backend/api/main.py",
        old=_SITE,
        new=_SITE + ("        if str(pid) in id_by_steam:\n"
                     "            chg = None\n"),
        check="pytest", run=_LT, red=[],
        why="the SAME rating-nulling statement at the SAME site, gated on a "
            "set that is not the reconciled one. The rating still moves, so a "
            "green here says the check fires on the READ of "
            "`_involuntary_departed` and not on the shape of the statement.",
    ),
    Plant(
        name="TWIN-B", kind="twin", target="wt:backend/api/main.py",
        old=_LEI,
        new=_LEI + ('               "lei_twin": str(pid) '
                    'in _involuntary_departed,\n'),
        check="pytest", run=_LT, red=[],
        why="a SECOND read of the reconciled set, INSIDE the INSERT call. "
            "Permitted by design: the rule is where each read is, not how "
            "many there are. A green here is what makes M4's red attributable "
            "to the LOCATION of the read.",
    ),
    Plant(
        name="POP-STALE", kind="control", target="notes:",
        derive="pop_stale", check="cmd", expect_exit=2,
        why="the notes' own stated citation population moved by one. The "
            "checker must refuse a verdict rather than certify a population "
            "no run of the file produced.",
    ),
    Plant(
        name="POP-TWIN", kind="twin", target="notes:",
        derive="pop_twin", check="cmd", expect_exit=0,
        why="the SAME line rewritten with the SAME three figures and wider "
            "separators. The line is touched and the verdict holds, so the "
            "refusal above is attributable to the FIGURES and not to the line "
            "having been edited.",
    ),
]


# ── Derivations. ──────────────────────────────────────────────────────────────
# A plant whose old text is a figure that every round moves cannot be written
# as a literal: pinning it to one round's notes would make the control refuse
# to run the moment the file it guards changes, which is the direction that
# fails silently. These read the LIVE claim with the shipped tool's own regex
# and build the pair from it, so the derivation cannot drift from the rule it
# is controlling. The exactly-once assertion in step 3 is unchanged.

def _live_claim(text: str) -> tuple[int, tuple[int, int, int], str]:
    claims = notes_citations.population_claims(text)
    live = [c for c in claims if not c[2]]
    if len(live) != 1:
        raise SystemExit(f"REFUSING: {len(live)} live CITATION POPULATION "
                         "claims, wants exactly one -- the plant would be "
                         "ambiguous")
    lineno, nums, _ = live[0]
    return lineno, nums, text.splitlines(keepends=True)[lineno - 1]


def _rerender(line: str, body: str) -> str:
    m = notes_citations._POPULATION_CLAIM.search(line)
    return line[:m.start()] + body + line[m.end():]


def pop_stale(text: str) -> tuple[str, str]:
    _, (t, r, d), line = _live_claim(text)
    return line, _rerender(
        line, f"CITATION POPULATION: {t + 1} = {r + 1} read + {d} declined")


def pop_twin(text: str) -> tuple[str, str]:
    _, (t, r, d), line = _live_claim(text)
    return line, _rerender(
        line, f"CITATION POPULATION:  {t}  =  {r}  read  +  {d}  declined")


DERIVATIONS = {"pop_stale": pop_stale, "pop_twin": pop_twin}


# ── Plumbing. ─────────────────────────────────────────────────────────────────

FAILED_NODE = re.compile(r"^FAILED\s+\S+::([A-Za-z0-9_\[\]\-.]+)")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def eol_of(text: str) -> str:
    return "\r\n" if text.count("\r\n") > text.count("\n") // 2 else "\n"


class Log:
    """Everything printed goes to the log AND to stdout, in one place."""

    def __init__(self, path: Path, roles: list[tuple[str, str]],
                 quiet: bool = False):
        self.buf = io.StringIO()
        self.path = path
        self.roles = roles
        self.quiet = quiet

    def role(self, s: str) -> str:
        s = s.replace("\\", "/")
        for real, name in self.roles:
            s = s.replace(real, name)
        return s

    def __call__(self, s: str = "") -> None:
        s = self.role(s)
        self.buf.write(s + "\n")
        if not self.quiet:
            print(s)

    def cmd(self, argv: list[str]) -> None:
        self(f"$ {' '.join(self.role(a) for a in argv)}")

    def write(self) -> None:
        self.path.write_text(self.buf.getvalue(), encoding="utf-8")


def git(log: Log, args: list[str], echo: bool = True) -> tuple[int, str]:
    argv = ["git", "-C", str(WT)] + args
    if echo:
        log.cmd(argv)
    r = subprocess.run(argv, capture_output=True, text=True)
    out = (r.stdout + r.stderr).rstrip("\n")
    if echo:
        if out:
            log(out)
        log(f"[exit {r.returncode}]")
    return r.returncode, out


def clean_tree(log: Log, where: str) -> bool:
    code, out = git(log, ["status", "--porcelain"])
    if code == 0 and out.strip() == "":
        log(f"-- the worktree is clean {where}: nothing but this runner wrote "
            "to it, so a plant cannot be confused with other work.")
        return True
    log(f"REFUSING: the worktree is NOT clean {where}. A plant applied to a "
        "tree carrying uncommitted work cannot be told apart from that work.")
    return False


def diff(log: Log, rel: str, before: str, after: str) -> None:
    a = [ln.rstrip("\r\n") for ln in before.splitlines(keepends=True)]
    b = [ln.rstrip("\r\n") for ln in after.splitlines(keepends=True)]
    for line in difflib.unified_diff(a, b, fromfile=f"a/{rel}",
                                     tofile=f"b/{rel}", n=3, lineterm=""):
        log(line)


def pytest_tail(log: Log, out: str, cap: int = 80) -> list[str]:
    """Print the failure block when there is one, the summary when there is not."""
    lines = out.splitlines()
    marks = [i for i, ln in enumerate(lines) if ln.startswith("=") and "FAILURES" in ln]
    if marks:
        block = lines[marks[0]:]
        if len(block) > cap:
            block = block[:cap - 1] + [f"... {len(block) - cap + 1} further lines"]
    else:
        block = [ln for ln in lines if ln.strip()][-6:]
    for ln in block:
        log(ln)
    return [m.group(1) for ln in lines if (m := FAILED_NODE.match(ln))]


# ── One plant. ────────────────────────────────────────────────────────────────

def run_plant(log: Log, n: int, p: Plant, targets: dict[str, Path],
              argv_for: dict, head: str) -> bool:
    kindword = "CONTROL" if p.kind == "control" else "INERT TWIN"
    log()
    log(f"### {n}. {kindword} {p.name} ###")
    log(f"-- {p.why}")
    if not clean_tree(log, "before the plant"):
        return False
    code, at = git(log, ["rev-parse", "HEAD"])
    if at.strip() != head:
        log(f"REFUSING: HEAD is {at.strip()}, the run was pinned to {head}.")
        return False

    key, _, rest = p.target.partition(":")
    path = targets[key] if key == "notes" else WT / rest
    rel = "notes/BUG392-SERVER-NOTES.md" if key == "notes" else rest
    raw = path.read_bytes()
    text = raw.decode("utf-8")

    if p.derive:
        old, new = DERIVATIONS[p.derive](text)
        log(f"-- the plant is DERIVED from the file's own live claim by "
            f"`{p.derive}`, and printed in full as a diff below.")
    else:
        e = eol_of(text)
        old, new = p.old.replace("\n", e), p.new.replace("\n", e)

    hits = text.count(old)
    log(f"-- occurrences of the plant's old text in {rel}: {hits} "
        f"(wants exactly 1)")
    if hits != 1:
        log(f"REFUSING: the site occurs {hits} times -- the plant would land "
            "somewhere this log cannot name.")
        return False
    before = sha256(path)
    log(f"-- sha256 before : {before}")
    planted_at = text[:text.index(old)].count("\n") + 1
    log(f"-- planted at    : {rel}:{planted_at}")

    ok = False
    try:
        path.write_bytes(text.replace(old, new).encode("utf-8"))
        log(f"-- sha256 planted: {sha256(path)}")
        log()
        diff(log, rel, text, text.replace(old, new))
        log()

        if p.check == "pytest":
            argv = [sys.executable, "-m", "pytest", p.run, "-q", "-rf",
                    "-p", "no:cacheprovider"]
            log.cmd(argv)
            r = subprocess.run(argv, cwd=WT / "backend", capture_output=True,
                               text=True)
            failed = pytest_tail(log, r.stdout + r.stderr)
            log(f"[exit {r.returncode}]")
            got, want = sorted(set(failed)), sorted(set(p.red))
            log(f"-- node ids that failed : {got or '(none)'}")
            log(f"-- node ids that had to : {want or '(none)'}")
            ok = got == want
        else:
            argv = argv_for[p.name]
            log.cmd(argv)
            r = subprocess.run(argv, capture_output=True, text=True)
            for ln in (r.stdout + r.stderr).splitlines()[-40:]:
                log(ln)
            log(f"[exit {r.returncode}]")
            log(f"-- exit code : {r.returncode} (had to be {p.expect_exit})")
            ok = r.returncode == p.expect_exit
    finally:
        path.write_bytes(raw)
        after = sha256(path)
        log(f"-- sha256 after  : {after}")
        log(f"-- restored byte for byte: {after == before}")
        if after != before:
            ok = False
        if key == "notes":
            log("-- the notes are outside the worktree under review and "
                "ignored by the repository that holds them, checked before "
                "this run started; the worktree check below is the tree the "
                "verdict is about.")
        if not clean_tree(log, "after the restore"):
            ok = False

    if p.kind == "control":
        verdict = "RED as required" if ok else "FAILED"
    else:
        verdict = "GREEN as required" if ok else "FAILED"
    log(f"RESULT {p.name}: {verdict}")
    return ok


# ── The runner's own negative controls. ──────────────────────────────────────
# Every other tool this lane ships carries a `--self-test`, and a runner that
# certifies other people's controls while carrying none of its own is the
# check that cannot fail (#342). These run against a throwaway git repository
# and a throwaway notes file; nothing here touches the lane.

_SELF_TEST_FILE = """\
def test_self_probe():
    assert PROBE == "green"
"""
_SELF_MODULE = 'PROBE = "green"\n'


def _self_test() -> int:
    global WT
    import tempfile

    outcomes: dict[str, bool] = {}
    real_wt = WT
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "backend/api").mkdir(parents=True)
        (root / "backend/tests").mkdir(parents=True)
        (root / ".gitignore").write_text(
            "__pycache__/\n*.pyc\nsink.log\n", encoding="utf-8")
        (root / "backend/api/probe.py").write_text(_SELF_MODULE, encoding="utf-8")
        (root / "backend/tests/test_probe.py").write_text(
            "from api.probe import PROBE\n" + _SELF_TEST_FILE, encoding="utf-8")
        (root / "backend/tests/conftest.py").write_text(
            "import sys, pathlib\n"
            "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n",
            encoding="utf-8")
        notes = root / "notes.md"
        notes.write_text(
            "# probe\n\nCITATION POPULATION: 10 = 7 read + 3 declined\n",
            encoding="utf-8")
        for argv in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.email=probe", "-c", "user.name=probe",
                      "commit", "-qm", "probe"]):
            subprocess.run(["git", "-C", str(root)] + argv,
                           capture_output=True, text=True)
        WT = root
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()

        red = Plant(name="P-RED", kind="control", target="wt:backend/api/probe.py",
                    old=_SELF_MODULE, new='PROBE = "red"\n',
                    check="pytest", run="tests/test_probe.py",
                    red=["test_self_probe"], why="probe")
        quiet = Plant(name="P-QUIET", kind="control",
                      target="wt:backend/api/probe.py", old=_SELF_MODULE,
                      new='PROBE = "green"  # touched\n', check="pytest",
                      run="tests/test_probe.py", red=["test_self_probe"],
                      why="probe")
        twin_reds = Plant(name="P-TWIN-REDS", kind="twin",
                          target="wt:backend/api/probe.py", old=_SELF_MODULE,
                          new='PROBE = "red"\n', check="pytest",
                          run="tests/test_probe.py", red=[], why="probe")
        twin_ok = Plant(name="P-TWIN-OK", kind="twin",
                        target="wt:backend/api/probe.py", old=_SELF_MODULE,
                        new='PROBE = "green"  # touched\n', check="pytest",
                        run="tests/test_probe.py", red=[], why="probe")
        ambiguous = Plant(name="P-AMBIGUOUS", kind="control",
                          target="wt:backend/api/probe.py", old='"green"\n',
                          new='"red"\n', check="pytest",
                          run="tests/test_probe.py", red=["test_self_probe"],
                          why="probe")

        def go(p: Plant) -> bool:
            sink = Log(root / "sink.log", [(str(root).replace("\\", "/"), "<t>")], quiet=True)
            return run_plant(sink, 1, p, {"notes": notes}, {}, head)

        before = (root / "backend/api/probe.py").read_bytes()
        outcomes["a control that reddens its named node is RED"] = go(red)
        outcomes["a control that leaves the node green is FAILED"] = not go(quiet)
        outcomes["a twin that reddens the node is FAILED"] = not go(twin_reds)
        outcomes["a twin that leaves it green is GREEN"] = go(twin_ok)
        outcomes["the target is restored after every plant above"] = (
            (root / "backend/api/probe.py").read_bytes() == before)

        # A site with two candidate matches must refuse rather than choose.
        (root / "backend/api/probe.py").write_text(
            _SELF_MODULE + 'OTHER = "green"\n', encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "-A"],
                       capture_output=True, text=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.email=probe",
                        "-c", "user.name=probe", "commit", "-qm", "two"],
                       capture_output=True, text=True)
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        outcomes["a plant matching two sites REFUSES"] = not go(ambiguous)

        # A dirty tree stops the run before anything is written. Put the
        # committed bytes back by writing them, never by asking git to
        # discard work: this runner writes into real trees, and a restore
        # path that can throw away somebody else's edit is not one to
        # rehearse anywhere (#290).
        committed = (root / "backend/api/probe.py").read_bytes()
        (root / "backend/api/probe.py").write_text(
            _SELF_MODULE + 'OTHER = "green"\ndirty = 1\n', encoding="utf-8")
        outcomes["a dirty worktree REFUSES"] = not go(red)
        (root / "backend/api/probe.py").write_bytes(committed)

        # The pin is a check, not a decoration.
        outcomes["a HEAD that is not the pin REFUSES"] = not run_plant(
            Log(root / "sink.log", [], quiet=True), 1, red, {"notes": notes},
            {}, "0" * 40)

        # The derivations move the figure and leave it alone, respectively.
        txt = notes.read_text(encoding="utf-8")
        old_s, new_s = pop_stale(txt)
        old_t, new_t = pop_twin(txt)
        outcomes["POP-STALE moves the stated figure"] = (
            "11 = 8 read + 3 declined" in new_s and old_s != new_s)
        outcomes["POP-TWIN rewrites the line and not the figures"] = (
            old_t != new_t
            and notes_citations.population_claims(
                txt.replace(old_t, new_t))[0][1] == (10, 7, 3))
        outcomes["a notes file with no live claim REFUSES"] = _refuses(
            lambda: pop_stale("# probe\n\nnothing here\n"))
        outcomes["a notes file with two live claims REFUSES"] = _refuses(
            lambda: pop_stale(txt + "\n" + "x\n" * 8 + txt))

        # A diff that reports the wrong line numbers would misdirect a reader
        # to a site the plant never touched.
        sink = Log(root / "sink.log", [], quiet=True)
        diff(sink, "f.py", "a\nb\nc\nd\ne\nf\ng\nh\n", "a\nb\nc\nd\nE\nf\ng\nh\n")
        outcomes["the diff names the real line numbers"] = (
            "@@ -2,7 +2,7 @@" in sink.buf.getvalue()
            and "-e" in sink.buf.getvalue().splitlines()
            and "+E" in sink.buf.getvalue().splitlines())
        WT = real_wt

    for name, ok in outcomes.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    bad = [n for n, ok in outcomes.items() if not ok]
    print(f"SELF-TEST: {len(outcomes) - len(bad)}/{len(outcomes)} checks passed"
          + (f"; FAILED: {'; '.join(bad)}" if bad else ""))
    return 2 if bad else 0


def _refuses(fn) -> bool:
    try:
        fn()
    except SystemExit:
        return True
    return False


# ── Entry. ────────────────────────────────────────────────────────────────────

HEADER = """\
==============================================================================
BUG 392 SERVER LANE - THE MUTATION RUNNER
Every plant below is carried as data in backend/tests/mutation_runner.py and
printed here as a unified diff, so the mutation a control rests on is readable
from this log alone rather than taken on the word of a summary line.

The tree is proved clean before and after every plant, the file is restored
from the bytes read before the write and its sha256 is printed on both sides,
and the run is pinned to one commit. Nothing in the worktree survives a plant.

Every path reads as the ROLE it played, so this file is sweepable.
==============================================================================\
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log", type=Path)
    ap.add_argument("--notes", type=Path,
                    help="the lane's notes; the population plants target it")
    ap.add_argument("--client-lane", type=Path,
                    help="the extract directory the citation checker reads")
    ap.add_argument("--expect-head", default="HEAD",
                    help="the commit this run certifies; HEAD must resolve to it")
    ap.add_argument("--only", nargs="*", default=None,
                    help="run just these plants, by name")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    # No default for any of these. A population plant that quietly skipped
    # itself because an argument was missing would be a control that reports
    # nothing and passes (#438).
    missing = [n for n, v in (("--log", args.log), ("--notes", args.notes),
                              ("--client-lane", args.client_lane)) if v is None]
    if missing:
        ap.error("missing " + ", ".join(missing) + " (or use --self-test)")

    notes, lane = args.notes.resolve(), args.client_lane.resolve()
    roles = sorted(
        [(str(WT).replace("\\", "/"), "<worktree>"),
         (str(notes.parent).replace("\\", "/"), "<bugs>"),
         (str(lane).replace("\\", "/"), "<bundle>/client-lane"),
         (str(Path.home()).replace("\\", "/"), "<home>")],
        key=lambda kv: -len(kv[0]))
    log = Log(args.log, roles)
    for line in HEADER.splitlines():
        log(line)

    log()
    log("### 0. The tree and the tip every plant below is pinned to ###")
    code, head = git(log, ["rev-parse", args.expect_head])
    head = head.strip()
    if code != 0:
        log("REFUSING: the pin does not resolve.")
        log.write()
        return 2
    if not clean_tree(log, "at the start of the run"):
        log.write()
        return 2
    # The population plants write to a file outside this worktree. Refuse
    # unless the repository holding it ignores it: a plant that dirties
    # another tree is the same defect this runner exists to prevent, one
    # directory over.
    argv = ["git", "-C", str(notes.parent), "check-ignore", "--quiet",
            str(notes)]
    log.cmd(argv)
    ig = subprocess.run(argv, capture_output=True, text=True)
    log(f"[exit {ig.returncode}]")
    if ig.returncode != 0:
        log("REFUSING: the notes are not ignored by the repository holding "
            "them, so a plant there would dirty a tracked tree.")
        log.write()
        return 2
    log("-- the notes are ignored where they live, so the population plants "
        "cannot leave a tracked file changed anywhere.")

    argv_for = {
        name: [sys.executable, str(WT / "backend/tests/notes_citations.py"),
               "--notes", str(notes), "--require-anchors", "--assert-population",
               "--client-source", f"client-lane/ApiClient.cs={lane}/ApiClient.cs",
               "--client-source",
               f"client-lane/TransportExit.cs={lane}/TransportExit.cs"]
        for name in ("POP-STALE", "POP-TWIN")
    }

    chosen = [p for p in PLANTS if args.only is None or p.name in args.only]
    results: list[tuple[Plant, bool]] = []
    for i, p in enumerate(chosen, start=1):
        results.append((p, run_plant(log, i, p, {"notes": notes},
                                     argv_for, head)))

    log()
    log(f"### {len(chosen) + 1}. SUMMARY - every line cites the section above "
        "that ran it ###")
    log("-- A summary is a cross-reference, not a result: each line names the "
        "numbered")
    log("-- section above it that carries the invocation the line rests on.")
    for i, (p, ok) in enumerate(results, start=1):
        want = "RED as required" if p.kind == "control" else "GREEN as required"
        log(f"{'CONTROL' if p.kind == 'control' else 'TWIN'} {p.name}: "
            f"{want if ok else 'FAILED'} §{i}")
    bad = [p.name for p, ok in results if not ok]
    log(f"VERDICT: {len(results) - len(bad)} of {len(results)} plants produced "
        f"the result they had to, and the worktree is clean "
        f"§{len(chosen)}" + (f"; FAILED: {', '.join(bad)}" if bad else ""))
    log.write()
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
