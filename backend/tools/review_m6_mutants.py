"""The four private M6 mutants of the equivalence suite (fix pass 2's set,
scripted at fix pass 7: round 7 LOW 3), as one driver.

Each mutant changes ONE file of a COPY of the suite, never the suite itself:
the driver makes a scratch suite inside the suite's own directory (no copy of
a suite file leaves that directory) holding a copy of each file a mutant
changes, and a suite.json naming those copies and, by absolute path, every
other file of the original. It first runs every target and both controls
against the unmutated scratch suite, ONE pytest, and every node must pass.
Then, per mutant: plant it in its copy; ONE pytest over the mutant's target
and the two real-path M6 controls, with the suite variable naming the scratch
suite; KILLED = the target FAILED and both controls PASSED; restore the copy
from the original and prove its bytes equal. At the end every original file
the driver read is proven unchanged (hashed before and after: none is ever
opened for writing), and the scratch suite is removed and proven absent.

  M6-reference-changed-keeping-window  old_sitting: the first statement (by
      kind) gains `TRUE AND ` after its first ` WHERE `, and the candidate
      window text stays in it. Target: the frozen reference is exactly the
      bound oracle.
  M6-frozen-game-line-changed  expected: the first game (by name) with an
      output gets a blank after its first kind's line. Target: the games
      reproduce the reference items and text.
  M6-exemption-key-back  mutations: the first GAME mutation (its kind's rule
      has scope game in the revision's rules.json) regains an exemption key
      (renders). Target: every game rule mutation changes exactly its
      intended identities (frozen metadata is gains and losses only).
  M6-expectation-moved  mutations: in that mutation one expected identity
      moves from lose to gain (from gain to lose when lose is empty). Target:
      the same.
  Controls, for every mutant: the two real-path M6 controls (a retained
  anchor changed alone, a retained line changed alone, each caught). They
  read only the sitting mutations, so every mutant above must leave them
  green.

It prints mutant ids, the manifest key of the file each one changes, node
names, verdicts, counts and equality words only: never a path, a value, a
name from the suite, a digest, or pytest's own output.

usage (from anywhere; pytest runs at the repository root):
  python -B backend/tools/review_m6_mutants.py
      the suite SCR_REVIEW_PRIVATE_SUITE names, against
      backend/tests/test_review_equivalence.py; needs REVIEW_EQUIV_TEST_PG_DSN
      (the controls run the sitting half). The private-runs script's step 5.
  python -B backend/tools/review_m6_mutants.py --selftest
      the public selftest fixture: the same four mutants and the same node
      names against backend/tests/review_m6_selftest.py and the synthetic
      suite of the same shape it builds in a temporary directory, plus a
      negative control (a mutant judged by a target that does not read its
      file must SURVIVE). No SCR_REVIEW_PRIVATE variable is read, and every
      one is removed from the child's environment.
Exit 0: every mutant killed (the negative control survived), every control
green, every byte restored, the originals unchanged and the scratch removed;
1 otherwise; 2 when the suite cannot be used or cannot carry a mutant (a
refusal naming the position, never a value), or when anything else fails
while the driver runs (a refusal naming the exception's type, never its
text, which can carry a path or a value). The scratch and the temporary
selftest suite count as removed only when lstat reports them missing; any
other failure to look is a refusal, never read as absence.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(TOOLS, "..", ".."))
PATH_KEYS = ("revision", "kindmap", "expected", "fixture", "mutations", "sitting_fixture", "old_sitting")
MUTABLE = ("old_sitting", "expected", "mutations")
FROZEN = "test_m6_the_frozen_reference_is_exactly_the_bound_oracle"
GAMES = "test_a16_games_reproduce_the_reference_items_and_text"
GAME_MUTATIONS = "test_a16_every_game_rule_mutation_changes_exactly_its_intended_identities"
CONTROLS = ("test_m6_control_a_retained_anchor_changed_alone_is_caught",
            "test_m6_control_a_retained_line_changed_alone_is_caught")
MODES = {"suite": ("SCR_REVIEW_PRIVATE_SUITE", "backend/tests/test_review_equivalence.py"),
         "selftest": ("REVIEW_M6_SELFTEST_SUITE", "backend/tests/review_m6_selftest.py")}
PRIVATE_PREFIX = "SCR_REVIEW_PRIVATE"
WINDOW = "::date - CAST(%d AS int)"          # the candidate window text the changed statement keeps
TIMEOUT_S = 1200


class Unplantable(Exception):
    """The suite cannot carry a mutant; the message names the position only."""


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _reference_changed_keeping_window(ref, paths):
    sql = ref.get("sql") if isinstance(ref, dict) else None
    if not isinstance(sql, dict) or not sql or type(ref.get("cand_days")) is not int:
        raise Unplantable("old_sitting has no statements or no integer cand_days")
    kind = sorted(sql)[0]
    text, window = sql[kind], WINDOW % ref["cand_days"]
    if not isinstance(text, str) or window not in text or " WHERE " not in text:
        raise Unplantable("the first statement of old_sitting lacks the window text or a WHERE")
    sql[kind] = text.replace(" WHERE ", " WHERE TRUE AND ", 1)
    if sql[kind] == text or window not in sql[kind]:
        raise Unplantable("the first statement of old_sitting did not change keeping the window")
    return ref


def _frozen_game_line_changed(expected, paths):
    names = sorted(n for n, v in expected.items() if v) if isinstance(expected, dict) else []
    if not names or not isinstance(expected[names[0]], dict):
        raise Unplantable("expected has no game with an output")
    out = expected[names[0]]
    first = out[sorted(out)[0]]
    if not isinstance(first, dict) or not isinstance(first.get("line"), str):
        raise Unplantable("the first output of expected has no line")
    first["line"] += " "
    return expected


def _first_game_mutation(muts, paths):
    """The first mutation whose kind maps (kindmap) to a rule of scope game in
    the revision's rules.json, as the equivalence suite partitions them."""
    kindmap = _read(paths["kindmap"])
    rules = _read(os.path.join(paths["revision"], "rules.json"))
    rules = rules.get("rules") if isinstance(rules, dict) else None
    scope = {r.get("id"): r.get("scope") for r in rules or [] if isinstance(r, dict)}
    for m in muts if isinstance(muts, list) else []:
        if isinstance(m, dict) and isinstance(kindmap, dict) and scope.get(kindmap.get(m.get("kind"))) == "game":
            return m
    raise Unplantable("mutations has no game mutation")


def _exemption_key_back(muts, paths):
    m = _first_game_mutation(muts, paths)
    if "renders" in m:
        raise Unplantable("the first game mutation already carries renders")
    m["renders"] = ["line"]
    return muts


def _expectation_moved(muts, paths):
    exp = _first_game_mutation(muts, paths).get("expect")
    if not isinstance(exp, dict) or not isinstance(exp.get("lose"), list) or not isinstance(exp.get("gain"), list):
        raise Unplantable("the expect of the first game mutation has no lose and gain lists")
    src, dst = ("lose", "gain") if exp["lose"] else ("gain", "lose")
    if not exp[src]:
        raise Unplantable("the first game mutation expects nothing")
    exp[dst].append(exp[src].pop(0))
    return muts


MUTANTS = [
    ("M6-reference-changed-keeping-window", "old_sitting", _reference_changed_keeping_window, FROZEN),
    ("M6-frozen-game-line-changed", "expected", _frozen_game_line_changed, GAMES),
    ("M6-exemption-key-back", "mutations", _exemption_key_back, GAME_MUTATIONS),
    ("M6-expectation-moved", "mutations", _expectation_moved, GAME_MUTATIONS),
]
# --selftest only: the first mutant judged by a target that never reads its
# file; it must SURVIVE, or a KILLED verdict above would prove nothing.
NEGATIVE = ("negative-control-reference-change-judged-by-the-games", "old_sitting",
            _reference_changed_keeping_window, GAMES)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _absent(path):
    """True only when lstat reports the path missing. Any other failure to
    look is raised (main turns it into a refusal), never read as absence."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return True
    return False


def _git(*args):
    """git's output, or None when git fails (never read as an empty answer)."""
    r = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _pytest(module, nodes, env):
    """ONE pytest over the nodes; (exit, {test name: PASSED|FAILED|ERROR},
    counts). Only node names and outcome words are taken from its output."""
    cmd = [sys.executable, "-B", "-m", "pytest", "-q", "-rA", "--tb=no", "-p", "no:cacheprovider"]
    cmd += ["%s::%s" % (module, n) for n in nodes]
    try:
        r = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return None, {}, "timed out after %d s" % TIMEOUT_S
    out = {}
    for line in r.stdout.splitlines():
        for word in ("PASSED", "FAILED", "ERROR"):
            if line.startswith(word + " "):
                node = line[len(word) + 1:].split(" - ")[0].strip().rsplit("::", 1)[-1]
                out[node] = word if out.get(node) in (None, "PASSED") else out[node]
    last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    counts = ", ".join("%s %s" % c for c in re.findall(r"(\d+) (passed|failed|errors?|skipped|deselected)", last))
    return r.returncode, out, counts or "no count line"


def _child_env(mode, scratch):
    var = MODES[mode][0]
    env = {k: os.environ[k] for k in os.environ if mode == "suite" or not k.startswith(PRIVATE_PREFIX)}
    env[var] = scratch
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _scratch(suite_dir, manifest):
    """(scratch suite directory, the original's absolute path per manifest key)."""
    paths = {k: os.path.normpath(os.path.join(suite_dir, manifest[k])) for k in PATH_KEYS}
    scratch = tempfile.mkdtemp(prefix=".m6-mutants-", dir=suite_dir)
    new = dict(manifest)
    new.update(paths)
    for k in MUTABLE:
        new[k] = os.path.join(scratch, k + ".json")
        shutil.copyfile(paths[k], new[k])
    with open(os.path.join(scratch, "suite.json"), "w", encoding="utf-8") as f:
        json.dump(new, f)
    return scratch, paths


def _originals(suite_dir, paths):
    files = [os.path.join(suite_dir, "suite.json"), os.path.join(paths["revision"], "rules.json")]
    files += [paths[k] for k in PATH_KEYS if k != "revision"]
    return {f: _sha(f) for f in files}


def _one(mid, key, plant, target, scratch, paths, module, env):
    """Plant one mutant in the scratch copy, run, restore; (verdict, restored)."""
    copy = os.path.join(scratch, key + ".json")
    try:
        obj = plant(_read(copy), paths)
    except Unplantable as e:
        print("MUTANT %s | %s | NOT PLANTED: %s" % (mid, key, e), flush=True)
        return "NOT PLANTED", True
    try:
        with open(copy, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        rc, res, counts = _pytest(module, [target] + list(CONTROLS), env)
    finally:
        shutil.copyfile(paths[key], copy)
    restored = _sha(copy) == _sha(paths[key])
    controls_green = all(res.get(c) == "PASSED" for c in CONTROLS)
    if res.get(target) == "FAILED" and controls_green:
        verdict = "KILLED"
    elif res.get(target) == "PASSED" and controls_green:
        verdict = "SURVIVED"
    else:
        verdict = "PROBLEM"
    print("MUTANT %s | %s | planted 1 | pytest exit %s | %s | target %s=%s | controls %s | "
          "restored bytes %s | %s" % (
              mid, key, rc, verdict, target, res.get(target, "MISSING"),
              ",".join("%s=%s" % (c, res.get(c, "MISSING")) for c in CONTROLS),
              "equal" if restored else "DIFFER", counts), flush=True)
    return verdict, restored


def _run(mode, suite_dir):
    module = MODES[mode][1]
    manifest = _read(os.path.join(suite_dir, "suite.json"))
    missing = [k for k in PATH_KEYS if not isinstance(manifest, dict) or not isinstance(manifest.get(k), str)]
    if missing:
        print("REFUSED: suite.json names no path for: " + ", ".join(missing))
        return 2
    scratch, paths = _scratch(suite_dir, manifest)
    problems = killed = refused = 0
    try:
        before = _originals(suite_dir, paths)
        env = _child_env(mode, scratch)
        nodes = [FROZEN, GAMES, GAME_MUTATIONS] + list(CONTROLS)
        rc, res, counts = _pytest(module, nodes, env)
        ok = rc == 0 and all(res.get(n) == "PASSED" for n in nodes)
        problems += not ok
        print("CONTROL unmutated scratch suite | pytest exit %s | %s | %s | %s" % (
            rc, ",".join("%s=%s" % (n, res.get(n, "MISSING")) for n in nodes), "PASS" if ok else "PROBLEM",
            counts), flush=True)
        for mid, key, plant, target in MUTANTS:
            verdict, restored = _one(mid, key, plant, target, scratch, paths, module, env)
            killed += verdict == "KILLED"
            refused += verdict == "NOT PLANTED"
            problems += (verdict != "KILLED") + (not restored)
        if mode == "selftest":
            verdict, restored = _one(*NEGATIVE, scratch, paths, module, env)
            problems += (verdict != "SURVIVED") + (not restored)
            print("NEGATIVE CONTROL %s (it must survive: the verdicts above depend on their targets)" % (
                "held" if verdict == "SURVIVED" else "FAILED"), flush=True)
        same = _originals(suite_dir, paths) == before
        problems += not same
        print("ORIGINALS %s (%d files of the suite hashed before and after; none opened for writing)" % (
            "unchanged" if same else "CHANGED", len(before)), flush=True)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    gone = _absent(scratch)
    problems += not gone
    print("SCRATCH SUITE removed: %s" % ("yes" if gone else "NO"))
    print("TOTAL mutants %d killed %d; problems %d" % (len(MUTANTS), killed, problems))
    if refused:
        return 2
    return 0 if problems == 0 and killed == len(MUTANTS) else 1


def main(argv):
    if argv[1:] not in ([], ["--selftest"]):
        print("usage: review_m6_mutants.py [--selftest]")
        return 2
    mode = "selftest" if argv[1:] else "suite"
    var = MODES[mode][0]
    head, status = _git("rev-parse", "--short=8", "HEAD"), _git("status", "--porcelain")
    print("START %s m6 mutants=%d mode=%s tip %s tree %s" % (
        now(), len(MUTANTS), mode, head or "UNKNOWN",
        "UNKNOWN" if status is None else ("clean" if not status else "DIRTY")), flush=True)
    made = None
    try:
        if mode == "selftest":
            sys.path.insert(0, os.path.join(REPO, "backend", "tests"))
            import review_m6_selftest
            made = tempfile.mkdtemp(prefix="review-m6-selftest-")
            suite_dir = review_m6_selftest.build(os.path.join(made, "suite"))
            print("SUITE the public selftest fixture (review_m6_selftest.build) in a temporary directory",
                  flush=True)
        else:
            suite_dir = os.environ.get(var) or ""
            if not os.path.isdir(suite_dir):
                print("REFUSED: %s names no directory" % var)
                return 2
            if not os.environ.get("REVIEW_EQUIV_TEST_PG_DSN"):
                print("REFUSED: REVIEW_EQUIV_TEST_PG_DSN is unset (the controls run the sitting half)")
                return 2
            print("SUITE the one %s names" % var, flush=True)
        rc = _run(mode, suite_dir)
    except Exception as e:                  # a refusal: no traceback, whose text can name a path or a value
        print("REFUSED: %s while the driver ran (its text is not printed)" % type(e).__name__, flush=True)
        rc = 2
    finally:
        if made:
            shutil.rmtree(made, ignore_errors=True)
    if made:
        gone = _absent(made)
        print("SELFTEST SUITE removed: %s" % ("yes" if gone else "NO"))
        rc = rc if gone else max(rc, 1)
    print("END %s" % now())
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
