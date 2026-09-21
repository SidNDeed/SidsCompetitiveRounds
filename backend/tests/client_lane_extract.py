"""Generate the CLIENT-LANE EXTRACT a server-lane review bundle carries.

WHY THIS EXISTS
  A server-lane review has to read two client files: the constant the wire name
  is transcribed from, and the call sites that probe, store and then USE the
  capability the server advertises. The production client source cannot go into
  a review bundle as it stands -- it carries a private address, a tester handle
  and deployment terms in regions no review row cites.

  Round 2 solved that by keeping only the two cited WINDOWS and blanking the
  rest. That is the wrong cut. It is a decision about which lines a reviewer
  will want, taken by the side being reviewed, and it was wrong the first time
  it was taken: the window pair dropped the production call site that proves
  the stored capability gates the leave write, and the row that asked for that
  proof failed for want of a line the extract had thrown away.

  The rule here is the opposite one. BLANK ONLY WHAT MUST NOT TRAVEL; KEEP
  EVERYTHING ELSE. A line either carries a protected shape, and is replaced by
  an empty line, or it survives byte for byte. Nothing is selected FOR
  inclusion, so nothing can be omitted by a judgement about what matters.

LINE-PRESERVING, AND WHY THAT IS THE WHOLE POINT
  The output has exactly as many lines as the input, in the same order. A
  citation written against the production source therefore resolves against the
  extract at the same number. A citation that lands on a blanked line resolves
  to a blank -- which is a FINDING, not a pass, and `notes_citations.py` reports
  it as one.

WHAT COUNTS AS PROTECTED
  Not a list kept here. `privacy_sweep.py` already defines the classes the
  bundle is swept for, and a generator with its own second opinion would blank
  a different set from the one the sweep checks -- two implementations of one
  rule, quietly disagreeing (#596). This imports that module and blanks every
  line the sweep reports. A run whose class set parses to nothing REFUSES: a
  generator that blanked nothing would emit the production source and report
  success (#342).

  The blanker and the post-check share that definition on purpose, so the
  post-check cannot be the thing that catches a bad blank. It catches a bad
  BLANKER: narrow the class set and the post-check reddens on a line that
  survived. That is what `--blank-classes` exists for and the only reason it
  exists.

ANCHORS ARE TOKENS, NOT NUMBERS
  The review needs certain lines to be READABLE in the extract. Naming them by
  line number would be a claim invalidated by the next edit above them (#752),
  so they are named by TOKEN. Each token is resolved in the source, every line
  it occurs on must survive non-blank, and the resolved numbers are printed so
  the notes can cite them. A token that resolves nowhere FAILS -- an anchor
  that matches nothing would otherwise certify an extract that dropped it.

THE SHA IS BOUND TO THE LANE, NOT SUPPLIED TO IT
  `--sha` used to be free-form. The generator refused an unreadable blob, and
  nothing else: not that the sha was the client lane's current committed tip,
  not that it was the sha the notes cite, not that it matched anything else in
  the bundle. Anchors resolve by TOKEN, which is what makes the extract robust
  to edits -- and it is also what makes a superseded commit indistinguishable
  from the right one, because every anchor still resolves and every shape check
  still holds. The two citation readings cannot catch it either: both derive
  from the same sha.

  So the argument is CHECKED rather than trusted. It is resolved in the client
  worktree and required to name that worktree's current committed tip; a
  mismatch REFUSES and prints both, which is the only outcome that makes the
  argument worth passing. The resolved 40-character sha, the file list and the
  per-class blank counts are written into the extract directory as
  `PROVENANCE.txt`, so a later reader binds the source they are reading to a
  commit without having to trust a log, and `--verify` requires that file to
  agree with the lane it re-resolves.

Usage:

    python backend/tests/client_lane_extract.py --client-worktree <dir> \\
        --sha <sha> --out <dir> --wordlist <file> [--guard <path>]
    python backend/tests/client_lane_extract.py --verify <dir> \\
        --client-worktree <dir> --sha <sha> --wordlist <file>
    python backend/tests/client_lane_extract.py --self-test

Exit codes: 0 the extract was written (or verified), 1 a check failed, 2 an
input was unusable or the self-test failed.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import privacy_sweep  # noqa: E402

# The client-lane files a server-lane review reads, and nothing else. The list
# is driven by what the notes CITE under the `client-lane/` prefix: a citation
# the reviewer cannot resolve is the defect this extract exists to end. The
# notes' OTHER client citations name `plugin/...`, which is this tree's own
# production plugin folder and travels with the tree, not here.
SOURCES = ("plugin/ApiClient.cs", "plugin/TransportExit.cs")

# The lines the review must be able to READ, named by a token that occurs on
# them. Each entry is (label, source file, token). The labels are the words the
# bar rows use, so a row can be traced to a printed number.
ANCHORS = (
    ("capability-declaration", "plugin/ApiClient.cs",
     "public static bool ServerAcceptsInvoluntaryFfaCause"),
    ("capability-probe", "plugin/ApiClient.cs",
     "ExtractJsonBool(req.downloadHandler.text, TransportExit.CapabilityField)"),
    ("capability-read-back", "plugin/ApiClient.cs",
     "ServerAcceptsInvoluntaryFfaCause = involuntaryCause"),
    ("production-call-site", "plugin/ApiClient.cs",
     "ServerAcceptsInvoluntaryFfaCause, TransportExit.NowSeconds()"),
    ("leave-cause-witness", "plugin/ApiClient.cs",
     "involuntaryCapability={ServerAcceptsInvoluntaryFfaCause}"),
    ("wire-name-constant", "plugin/TransportExit.cs",
     'CapabilityField = "ffa_involuntary_cause"'),
    ("capability-gate", "plugin/TransportExit.cs",
     "InRoomLeaveTag(bool serverRecognisesInvoluntary"),
    ("involuntary-tag-constant", "plugin/TransportExit.cs",
     'InRoomInvoluntaryTag = "in_room_timeout"'),
    ("today-tag-constant", "plugin/TransportExit.cs",
     'InRoomExitTag = "in_room_exit"'),
)


def read_blob(worktree: Path, sha: str, rel: str) -> list[str]:
    """One committed file, as lines, read as BYTES and decoded here.

    The committed blob and not the working copy: an uncommitted edit in that
    worktree must not be able to reach this bundle, and this is the only read
    that tree gets. Decoded explicitly because the seat's locale codec cannot
    decode the UTF-8 these sources carry, and a pass that dies in the codec
    reports nothing at all.
    """
    proc = subprocess.run(["git", "-C", str(worktree), "show", f"{sha}:{rel}"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise SystemExit(f"REFUSING: cannot read {rel} at {sha} in {worktree.name}: "
                         f"{proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout.decode("utf-8", "replace").splitlines()

def rev(worktree: Path, spec: str) -> str | None:
    """The 40-character commit `spec` names in that worktree, or None.

    `^{commit}` so a tag or a short sha resolves to the same string a branch
    tip does: the comparison this feeds must be about the COMMIT and not about
    how it was spelled, or the inert twin -- the same commit given in full --
    would red beside the mutation and prove nothing.
    """
    proc = subprocess.run(["git", "-C", str(worktree), "rev-parse", f"{spec}^{{commit}}"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").strip() or None


def bind_sha(worktree: Path, supplied: str) -> str:
    """Require `supplied` to name the client lane's current committed tip.

    Returns the resolved 40-character sha. REFUSES otherwise: an extract built
    from a superseded commit passes every other check in this file, so this is
    the only place the question can be asked at all.
    """
    tip = rev(worktree, "HEAD")
    if tip is None:
        raise SystemExit(f"REFUSING: cannot resolve HEAD in {worktree.name}. "
                         "The sha cannot be bound to anything, and an unbound "
                         "sha is what this check exists to end.")
    got = rev(worktree, supplied)
    if got is None:
        raise SystemExit(f"REFUSING: {supplied!r} names no commit in {worktree.name}.")
    if got != tip:
        raise SystemExit(
            f"REFUSING: --sha {supplied!r} resolves to {got[:12]} but "
            f"{worktree.name} is at {tip[:12]}. An extract taken from a "
            "superseded commit passes every anchor and every shape check in "
            "this file, because the anchors resolve by token; nothing else "
            "would report it.")
    dirty = subprocess.run(["git", "-C", str(worktree), "status", "--porcelain"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    state = "clean" if not dirty.stdout.strip() else "carrying uncommitted work"
    print(f"client lane     : {worktree.name} at {tip} ({state})")
    return tip


PROVENANCE = "PROVENANCE.txt"


def write_provenance(out_dir: Path, sha: str, rows: list[str]) -> None:
    """Bind the extract to the commit it was taken from, inside the bundle.

    File names, a sha, counts and class names only -- the same rule the seal
    keeps -- so this cannot carry protected content by construction.
    """
    body = ["# client-lane extract provenance",
            "# Generated by backend/tests/client_lane_extract.py from the",
            "# client lane's COMMITTED blob. Never from a working copy.",
            f"commit: {sha}"]
    body += rows
    (out_dir / PROVENANCE).write_text("\n".join(body) + "\n",
                                      encoding="utf-8", newline="\n")


def check_provenance(out_dir: Path, sha: str) -> list[str]:
    """Complaints when the extract does not name the commit it was taken from."""
    p = out_dir / PROVENANCE
    if not p.is_file():
        return [f"{PROVENANCE}: absent -- the extract names no commit, so what "
                "a reviewer is reading cannot be bound to the lane"]
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("commit: "):
            recorded = line.split(" ", 1)[1].strip()
            if recorded != sha:
                return [f"{PROVENANCE}: names {recorded[:12]}, the lane is at "
                        f"{sha[:12]} -- this extract is from another commit"]
            return []
    return [f"{PROVENANCE}: carries no commit line"]



def protected_lines(lines: list[str], terms: dict, classes: set[str] | None,
                    guard_rx) -> dict[int, list[str]]:
    """{line number: [class, ...]} for every line that must not travel.

    `classes` narrows what is blanked and exists for the control alone; None
    means every class the sweep implements.
    """
    text = "\n".join(lines)
    out: dict[int, list[str]] = {}
    for lineno, cls in privacy_sweep.scan_text(text, terms, guard_rx):
        if classes is not None and cls not in classes:
            continue
        out.setdefault(lineno, []).append(cls)
    return out


def blank(lines: list[str], protected: dict[int, list[str]]) -> list[str]:
    return ["" if (i + 1) in protected else line for i, line in enumerate(lines)]


def resolve_anchors(rel: str, lines: list[str]) -> list[tuple[str, str, list[int]]]:
    """[(label, token, [line numbers])] for this file's anchors.

    Raises when a token resolves nowhere: an anchor that matches nothing
    certifies nothing, and would let an extract that dropped the line it names
    pass with a green anchor check (#342).
    """
    out = []
    for label, src, token in ANCHORS:
        if src != rel:
            continue
        hits = [i for i, line in enumerate(lines, 1) if token in line]
        if not hits:
            raise SystemExit(f"REFUSING: anchor {label!r} resolves nowhere in {rel}. "
                             "An anchor that matches nothing cannot certify an extract.")
        out.append((label, token, hits))
    return out


def check_anchors(rel: str, source: list[str], extract: list[str]) -> list[str]:
    """Complaints, one per anchor line that did not survive non-blank."""
    bad = []
    for label, _token, hits in resolve_anchors(rel, source):
        for n in hits:
            if n > len(extract) or not extract[n - 1].strip():
                bad.append(f"{rel}:{n}: anchor {label} does not survive in the extract")
    return bad


def check_shape(rel: str, source: list[str], extract: list[str],
                protected: dict[int, list[str]]) -> list[str]:
    """Complaints about the three properties the extract is defined by."""
    bad = []
    if len(extract) != len(source):
        bad.append(f"{rel}: {len(extract)} lines out of {len(source)} in -- not line-preserving")
        return bad
    for i, (a, b) in enumerate(zip(source, extract), 1):
        if i in protected:
            if b != "":
                bad.append(f"{rel}:{i}: a protected line survived")
        elif a != b:
            bad.append(f"{rel}:{i}: an unprotected line was altered")
    return bad


def _terms_and_guard(args):
    terms = privacy_sweep.load_wordlist(args.wordlist)
    unconfigured = [c for c in privacy_sweep._WORDLIST_CLASSES if not terms[c]]
    if unconfigured:
        raise SystemExit("REFUSING: no terms supplied for " + ", ".join(unconfigured)
                         + " -- those classes would not be blanked. Supply --wordlist.")
    guard_rx = privacy_sweep.guard_matcher(args.guard)
    if guard_rx is None:
        raise SystemExit("REFUSING: the real-name matcher could not be read; "
                         "that class would not be blanked.")
    return terms, guard_rx


def _report(rel: str, source: list[str], protected: dict[int, list[str]],
            out_stream) -> None:
    """Per-class COUNTS and line numbers. Never the text of a blanked line."""
    per_class: dict[str, list[int]] = {}
    for n, classes in protected.items():
        for cls in classes:
            per_class.setdefault(cls, []).append(n)
    print(f"  {rel}: {len(source)} lines in, {len(protected)} blanked", file=out_stream)
    for cls in sorted(per_class):
        nums = sorted(per_class[cls])
        print(f"    class {cls}: {len(nums)} lines at {nums}", file=out_stream)
    if not protected:
        print("    no protected line in this file", file=out_stream)


def generate(args) -> int:
    terms, guard_rx = _terms_and_guard(args)
    classes = set(args.blank_classes.split(",")) if args.blank_classes else None
    if classes is not None and not classes:
        raise SystemExit("REFUSING: --blank-classes parsed to nothing.")
    worktree = args.client_worktree
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    bad: list[str] = []
    print(f"client worktree : {worktree.name}")
    sha = bind_sha(worktree, args.sha)
    print(f"committed sha   : {args.sha} -> {sha}")
    provenance: list[str] = []
    print(f"blank classes   : {'ALL' if classes is None else sorted(classes)}")
    for rel in SOURCES:
        source = read_blob(worktree, sha, rel)
        protected = protected_lines(source, terms, classes, guard_rx)
        extract = blank(source, protected)
        _report(rel, source, protected, sys.stdout)
        for label, token, hits in resolve_anchors(rel, source):
            print(f"    anchor {label}: {rel}:{hits if len(hits) > 1 else hits[0]}")
        target = out_dir / Path(rel).name
        target.write_text("\n".join(extract) + "\n", encoding="utf-8", newline="\n")
        # The post-check reads what was WRITTEN, not what was computed.
        written = target.read_text(encoding="utf-8").splitlines()
        bad += check_shape(rel, source, written, protected_lines(source, terms, None, guard_rx))
        bad += check_anchors(rel, source, written)
        survived = privacy_sweep.scan_text("\n".join(written), terms, guard_rx)
        for lineno, cls in survived:
            bad.append(f"{rel}:{lineno}: {cls} survived into the extract")
        provenance.append(f"{Path(rel).name}: {len(source)} lines, "
                          f"{len(protected)} blanked, from {rel}")
    write_provenance(out_dir, sha, provenance)
    bad += check_provenance(out_dir, sha)
    for line in bad:
        print(line)
    print("EXTRACT:", "written, every property held" if not bad
          else f"{len(bad)} checks failed")
    return 1 if bad else 0


def verify(args) -> int:
    terms, guard_rx = _terms_and_guard(args)
    bad: list[str] = []
    print(f"verifying       : {args.verify.name}")
    sha = bind_sha(args.client_worktree, args.sha)
    print(f"committed sha   : {args.sha} -> {sha}")
    bad += check_provenance(args.verify, sha)
    for rel in SOURCES:
        source = read_blob(args.client_worktree, sha, rel)
        target = args.verify / Path(rel).name
        if not target.is_file():
            bad.append(f"{rel}: absent from the extract directory")
            continue
        extract = target.read_text(encoding="utf-8").splitlines()
        protected = protected_lines(source, terms, None, guard_rx)
        if len(extract) != len(source):
            bad.append(f"{rel}: {len(extract)} lines, source has {len(source)}")
        else:
            for n in protected:
                if extract[n - 1] != "":
                    bad.append(f"{rel}:{n}: a protected line survived")
        bad += check_anchors(rel, source, extract)
        print(f"  {rel}: {len(extract)} lines, {len(protected)} protected")
    for line in bad:
        print(line)
    print("VERIFY:", "line-preserving, protected blanked, every anchor readable"
          if not bad else f"{len(bad)} checks failed")
    return 1 if bad else 0


def _self_test() -> int:
    """Plant each property and require the checks to separate them."""
    source = [
        "class A {",
        "    // a comment",
        'internal const string CapabilityField = "ffa_involuntary_cause";',
        "}",
    ]
    extract_ok = list(source)
    extract_blanked_anchor = ["", "    // a comment", "", "}"]
    extract_short = source[:3]
    extract_altered = ["class B {", "    // a comment",
                       'internal const string CapabilityField = "ffa_involuntary_cause";', "}"]
    rel = "plugin/TransportExit.cs"

    def anchors_only(src, ext):
        keep = [a for a in ANCHORS if a[1] == rel and a[2] in "\n".join(src)]
        saved = globals()["ANCHORS"]
        globals()["ANCHORS"] = tuple(keep)
        try:
            return check_anchors(rel, src, ext)
        finally:
            globals()["ANCHORS"] = saved

    checks = {
        "an untouched extract is green": not anchors_only(source, extract_ok),
        "a blanked anchor line is reported": bool(anchors_only(source, extract_blanked_anchor)),
        "a blanked NON-anchor line stays green":
            not anchors_only(source, ["class A {", "",
                                      'internal const string CapabilityField = "ffa_involuntary_cause";',
                                      "}"]),
        "a short extract is reported": bool(check_shape(rel, source, extract_short, {})),
        "an altered unprotected line is reported":
            bool(check_shape(rel, source, extract_altered, {})),
        "a protected line that survived is reported":
            bool(check_shape(rel, source, extract_ok, {2: ["handle"]})),
        "a correctly blanked protected line is green":
            not check_shape(rel, source, ["class A {", "",
                                          'internal const string CapabilityField = "ffa_involuntary_cause";',
                                          "}"], {2: ["handle"]}),
    }
    try:
        resolve_anchors(rel, ["nothing here"])
        checks["an anchor resolving nowhere refuses"] = False
    except SystemExit:
        checks["an anchor resolving nowhere refuses"] = True

    # The provenance binding, without a repository: the shapes are a file that
    # names the commit, one that names another, and one that is not there.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        checks["an extract naming no commit is reported"] = \
            bool(check_provenance(d, "a" * 40))
        write_provenance(d, "a" * 40, ["ApiClient.cs: 3 lines, 0 blanked"])
        checks["an extract naming THIS commit is green"] = \
            not check_provenance(d, "a" * 40)
        checks["an extract naming ANOTHER commit is reported"] = \
            bool(check_provenance(d, "b" * 40))
        checks["the provenance carries counts and never a line of source"] = (
            "0 blanked" in (d / PROVENANCE).read_text(encoding="utf-8")
            and "class A {" not in (d / PROVENANCE).read_text(encoding="utf-8"))
    for k, ok in checks.items():
        print(f"  {'ok  ' if ok else 'FAIL'} {k}")
    bad = [k for k, ok in checks.items() if not ok]
    print("SELF-TEST:", "every property separated" if not bad else f"FAILED: {bad}")
    return 2 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--client-worktree", type=Path)
    ap.add_argument("--sha")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--verify", type=Path)
    ap.add_argument("--wordlist", type=Path)
    ap.add_argument("--guard", type=Path)
    ap.add_argument("--blank-classes",
                    help="CONTROL ONLY: narrow the classes that are blanked, so the "
                         "post-check can be observed reddening on a line that survived")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if not args.client_worktree or not args.sha:
        ap.error("--client-worktree and --sha are required unless --self-test is given")
    if not args.client_worktree.is_dir():
        print(f"REFUSING: not a directory: {args.client_worktree}")
        return 2
    if args.verify:
        return verify(args)
    if not args.out:
        ap.error("--out is required unless --verify or --self-test is given")
    return generate(args)


if __name__ == "__main__":
    sys.exit(main())
