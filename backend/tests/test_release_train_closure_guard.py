"""The release tool's closure guard (item 41, after round guard-r1).

/health's review_eval is what review_rules.review_eval() returns in the running api: the leading hex of the framed
digest over the review evaluator's files as review_boot executed them. A batch whose deploy changes one of them
changes that word, and an installed rules revision built for the old word stops loading. The release tool
(scripts/deploy/release_train.py, local to the operating seat and not tracked) refuses before anything is merged or
deployed unless the batch entry answers for a change: closure_change.eval_to equal to the tip's word and a health
list that expects that word on both roles.

Two methods hold it (round guard-r1):
- THE WORD OF A COMMIT is computed by that commit's own routine over that commit's own bytes: the tool exports
  backend/api from git objects into a temporary directory and runs review_boot and review_rules.review_eval() there
  in a child interpreter. The tests here compare the tool's answer with the routine run directly over the same
  bytes, on the constructions the review named (line ends inside a comment, a boot file in CRLF at the size bound,
  the domain bound a second time) and on a seventh file.
- THE TREE THAT IS DEPLOYED is judged: _deploy_both, the one deploy site (a census over the tool's syntax tree), hands
  the exact sha to closure_judge_deploy before the first box.

Every test builds a scratch git repository holding LF copies of this checkout's evaluator files, and fakes for the
two boxes' /health and code state. Without the tool every test here skips, as the tool's other tests do; the routine's
child needs a Windows job object, so off Windows they skip as well.
"""
import ast
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
API = REPO / "backend" / "api"
PRIMARY, STANDBY = "primary-box", "standby-box"
OLD = (True, False, True, ["old"])
NEW = (True, True, False, ["new"])
UNKNOWN = (True, False, False, ["neither"])
EVALUATOR = ("card_measures.py", "combat_measures.py", "identity_clock_measures.py", "review_boot.py",
             "review_measures.py", "review_rules.py")
DIRECT = ("import sys; sys.path[:0] = [sys.argv[1]]; import review_boot, review_rules; "
          "sys.stdout.write(str(review_rules.review_eval()))")


def _release_train():
    train = REPO / "scripts" / "deploy" / "release_train.py"
    if not train.exists():
        pytest.skip("the release train is local to the operating seat")
    spec = importlib.util.spec_from_file_location("release_train_closure_under_test", train)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _no_network_program(monkeypatch):
    """No test here spawns curl, ssh or scp; a refused spawn is recorded and asserted at teardown."""
    real, spawned = subprocess.run, []

    def guard(cmd, *args, **kw):
        first = cmd[0] if isinstance(cmd, (list, tuple)) and cmd else str(cmd).split(" ")[0]
        prog = os.path.basename(str(first)).lower().split(".")[0]
        if prog in ("curl", "ssh", "scp"):
            spawned.append(prog)
            raise OSError("a unit test does not spawn %s" % prog)
        return real(cmd, *args, **kw)
    monkeypatch.setattr(subprocess, "run", guard)
    yield
    assert spawned == [], "this test tried to spawn %s" % ", ".join(spawned)


class Scratch:
    """A git repository with backend/api holding LF copies of this checkout's evaluator files on main, and a lane
    branch whose commits change them."""

    def __init__(self, root):
        self.root = root
        self.repo = root / "repo"
        self.hooks = root / "no-hooks"
        self.hooks.mkdir(parents=True)
        (root / "template").mkdir()
        subprocess.run(["git", "init", "-q", "--template=" + str(root / "template"), str(self.repo)], check=True)
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        api = self.repo / "backend" / "api"
        api.mkdir(parents=True)
        for name in EVALUATOR:
            (api / name).write_bytes((API / name).read_bytes().replace(b"\r\n", b"\n"))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "-b", "lane")

    def git(self, *args):
        p = subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.hooksPath=" + str(self.hooks),
                            "-c", "user.name=closure test", "-c", "user.email=closure@example.invalid",
                            "-c", "commit.gpgsign=false"] + list(args),
                           cwd=str(self.repo), capture_output=True, check=True)
        return p.stdout.decode("utf-8").strip()

    def path(self, name):
        return self.repo / "backend" / "api" / name

    def commit(self, edits, message="lane"):
        """Apply {file: bytes, None (delete) or a function of the old bytes} on the checked-out branch and commit;
        returns the sha."""
        for name, new in edits.items():
            p = self.path(name)
            if new is None:
                p.unlink()
            else:
                p.write_bytes(new(p.read_bytes()) if callable(new) else new)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")


def _direct(scratch):
    """The routine run directly over the scratch checkout's backend/api as it stands on disk (the bytes just
    committed): the commit's own review_boot and review_rules in an isolated interpreter."""
    p = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", DIRECT, str(scratch.repo / "backend" / "api")],
                       capture_output=True, timeout=120)
    return p.stdout.decode("ascii", "replace").strip() if p.returncode == 0 else None


def _rows(eval_word, rules_word="absent"):
    return [{"key": "review_eval", "primary": eval_word, "standby": eval_word},
            {"key": "review_rules", "primary": rules_word, "standby": rules_word}]


class Boxes:
    def __init__(self, word, rules="absent"):
        self.health = {PRIMARY: {"review_eval": word, "review_rules": rules},
                       STANDBY: {"review_eval": word, "review_rules": rules}}
        self.state = {PRIMARY: OLD, STANDBY: OLD}

    def health_json(self, host):
        return dict(self.health[host])

    def code_state(self, host):
        return self.state[host]


def _bind(monkeypatch, rt, scratch, tip, boxes, tmp_path, change=None, rows=None):
    monkeypatch.setattr(rt, "REPO", str(scratch.repo))
    monkeypatch.setattr(rt, "PRIMARY", PRIMARY)
    monkeypatch.setattr(rt, "STANDBY", STANDBY)
    monkeypatch.setattr(rt, "BRANCH", "lane")
    monkeypatch.setattr(rt, "REVIEWED_TIP", tip)
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", rt.closure_change_form("test", change))
    monkeypatch.setattr(rt, "HEALTH_EXPECT", rows if rows is not None else [])
    monkeypatch.setattr(rt, "ALL_SQL", [])
    monkeypatch.setattr(rt, "STATE_PATH", str(tmp_path / "state" / "train-state.json"))
    monkeypatch.setattr(rt, "health_json", boxes.health_json)
    monkeypatch.setattr(rt, "code_state", boxes.code_state)


def _word(rt, rev):
    word = rt.closure_routine_word(rev)
    assert word is not None and rt.CLOSURE_WORD.fullmatch(word), word
    return word


@pytest.fixture
def world(tmp_path, monkeypatch):
    rt = _release_train()
    if os.name != "nt":
        pytest.skip("the closure routine's child runs in a Windows job object")
    scratch = Scratch(tmp_path / "scratch")
    monkeypatch.setattr(rt, "REPO", str(scratch.repo))
    base_word = _word(rt, scratch.base)
    return rt, scratch, base_word


def _changed_tip(scratch):
    return scratch.commit({"review_rules.py": lambda raw: raw + b"\n# a change of the evaluator\n"})


def _deploys(monkeypatch, rt):
    """zap and the per-box checks of _deploy_both replaced by recorders: what a deploy would have started."""
    plays = []
    monkeypatch.setattr(rt, "zap", lambda playbook, limit=None, extra=None, **kw: plays.append((playbook, extra))
                        or "ok failed=0")
    monkeypatch.setattr(rt, "assert_control", lambda host: None)
    monkeypatch.setattr(rt, "assert_box_build", lambda host, expect, sha: None)
    return plays


def _record(word):
    return {"from": word, "rules": {"primary": "absent", "standby": "absent"}, "tip": "f" * 40, "tip_word": word,
            "stage": "code", "recorded_at": "2026-11-22T00:00:00Z"}


# ---------------------------------------------------------------- the word of a commit (class B)


def test_the_tools_word_is_the_routines_own_on_this_checkouts_files(world):
    """The scratch base holds this checkout's six files: the tool's word is the routine's, run directly."""
    rt, scratch, base_word = world
    assert base_word == _direct(scratch)


def test_line_ends_inside_a_comment_are_read_as_the_routine_reads_them(world):
    """Review finding 3: a comment ending CR CR CR LF, then CR CR LF, in a module review_boot executes. Each gives
    exactly the word the routine gives over those bytes, and the two words differ, so the bytes reach the routine as
    git stores them."""
    rt, scratch, base_word = world
    words = []
    for ending in (b"\r\r\r\n", b"\r\r\n"):
        sha = scratch.commit({"review_measures.py": lambda raw, e=ending: raw.split(b"\n# crs")[0]
                              + b"\n# crs" + e})
        words.append(_word(rt, sha))
        assert words[-1] == _direct(scratch), (ending, words[-1])
    assert words[0] != words[1], words


def test_a_boot_file_in_crlf_over_the_bound_is_refused_as_the_server_refuses_it(world, monkeypatch, tmp_path):
    """Review finding 4: review_boot.py padded so its LF bytes are inside the loader's size bound and its CRLF bytes
    over it. In LF the tool's word is the routine's word; in CRLF the routine answers refused (the server bounds
    the raw bytes), the tool says the same, and the guard refuses that tip."""
    rt, scratch, base_word = world
    bound = 1048576
    boot = scratch.path("review_boot.py").read_bytes()
    pad = bound - 128 - len(boot)
    padded = boot + b"\n" + b"#" * 63 + b"\n" + (b"#" * 63 + b"\n") * (pad // 64)
    assert len(padded) <= bound < len(padded.replace(b"\n", b"\r\n"))
    lf = scratch.commit({"review_boot.py": padded})
    assert _word(rt, lf) == _direct(scratch)
    crlf = scratch.commit({"review_boot.py": padded.replace(b"\n", b"\r\n")})
    assert _direct(scratch) == "refused"
    assert rt.closure_routine_word(crlf) == "refused"
    _bind(monkeypatch, rt, scratch, crlf, Boxes(base_word), tmp_path, rows=_rows(base_word))
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "check", write=False)
    assert "answers refused" in str(exc.value), str(exc.value)


def test_the_domain_bound_a_second_time_is_read_as_the_routine_reads_it(world):
    """Review finding 5: review_rules.py binds CODE_DOMAIN again through a match capture. The tool's word is the word
    the routine computes with the domain the module ends with, and it differs from the base word."""
    rt, scratch, base_word = world
    tip = scratch.commit({"review_rules.py": lambda raw: raw + b"\n\nmatch b'scr-review-code-closure-x\\n':\n"
                                                                b"    case CODE_DOMAIN:\n        pass\n"})
    word = _word(rt, tip)
    assert word == _direct(scratch) and word != base_word, (word, base_word)


def test_a_seventh_file_is_covered_when_the_loader_executes_it_and_refused_when_it_does_not(world):
    """R4 and review finding 7: a file added to CODE_REQUIRED and to review_boot.SOURCE_ONLY and imported by
    review_rules is in the word, as the routine computes it; a change of that file alone moves the word. Listed in
    CODE_REQUIRED without being executed by the loader, the routine answers refused, and so does the tool."""
    rt, scratch, base_word = world

    def listed(raw):
        out, n = re.subn(rb'(CODE_REQUIRED = \([^)]*)\)', lambda m: m.group(1) + b', "extra_measures.py")', raw,
                         count=1)
        assert n == 1
        return out

    def loaded(raw):
        out, n = re.subn(rb'(SOURCE_ONLY = \([^)]*)\)', lambda m: m.group(1) + b', "extra_measures")', raw, count=1)
        assert n == 1
        return out

    def imported(raw):
        out, n = re.subn(rb"\nimport combat_measures as cbm\n", b"\nimport combat_measures as cbm\n"
                                                                 b"import extra_measures as _xm  # noqa: F401\n", raw,
                         count=1)
        assert n == 1
        return out
    unloaded = scratch.commit({"extra_measures.py": b"X = 1\n", "review_rules.py": listed})
    assert _direct(scratch) == "refused" and rt.closure_routine_word(unloaded) == "refused"
    tip = scratch.commit({"review_boot.py": loaded, "review_rules.py": imported})
    word = _word(rt, tip)
    assert word == _direct(scratch) and word != base_word
    again = scratch.commit({"extra_measures.py": b"X = 2\n"})
    assert _word(rt, again) == _direct(scratch) != word


def test_a_commit_without_the_routine_is_unknown_and_refused(world, monkeypatch, tmp_path):
    """A tip whose review_rules has no review_eval (or no review_boot.py at all): the word is unknown, and the guard
    refuses, with a fixed line."""
    rt, scratch, base_word = world
    gone = scratch.commit({"review_rules.py": lambda raw: raw.replace(b"def review_eval(", b"def review_eval_gone(")})
    assert rt.closure_routine_word(gone) is None
    no_boot = scratch.commit({"review_boot.py": None})
    assert rt.closure_routine_word(no_boot) is None
    _bind(monkeypatch, rt, scratch, gone, Boxes(base_word), tmp_path, rows=_rows(base_word))
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "check", write=False)
    assert "could not be run to its one line, so its word is unknown" in str(exc.value), str(exc.value)


# ---------------------------------------------------------------- R1


def test_equal_words_ask_for_no_key_and_record_the_boxes_word(world, monkeypatch, tmp_path):
    """The tip leaves the evaluator as the boxes run it: no closure_change is asked and the word is recorded."""
    rt, scratch, base_word = world
    tip = scratch.commit({"main.py": b"# an api file outside the evaluator\n"}, "no evaluator change")
    boxes = Boxes(base_word)
    _bind(monkeypatch, rt, scratch, tip, boxes, tmp_path, rows=_rows(base_word))
    st = {}
    rt.closure_guard(st, "check", write=True)
    assert st[rt.CLOSURE_STATE_KEY]["from"] == base_word
    assert rt.load_state()[rt.CLOSURE_STATE_KEY]["tip_word"] == base_word


def test_a_change_without_the_key_is_refused_by_the_code_phase_before_the_merge(world, monkeypatch, tmp_path):
    """The code phase of a batch with no sql: the negative control passes, then the guard refuses at the reviewed
    tip, naming the tip's word and the boxes' word, before any lease, merge, push or deploy."""
    rt, scratch, base_word = world
    tip = _changed_tip(scratch)
    tip_word = _word(rt, tip)
    assert tip_word != base_word
    boxes = Boxes(base_word)
    _bind(monkeypatch, rt, scratch, tip, boxes, tmp_path, rows=_rows(base_word))
    monkeypatch.setattr(rt, "require_rollback_point", lambda *a, **kw: None)
    touched = []
    for name in ("git_child", "blocking_child", "zap", "controller_lease_session", "read_code_world"):
        monkeypatch.setattr(rt, name, lambda *a, _n=name, **kw: touched.append(_n))
    main_before = scratch.git("rev-parse", "refs/heads/main")
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(type("Args", (), {"go": True})(), {"schema_done": True})
    msg = str(exc.value)
    assert tip_word in msg and base_word in msg and "no closure_change" in msg, msg
    assert touched == [] and scratch.git("rev-parse", "refs/heads/main") == main_before


def test_a_wrong_eval_to_is_refused(world, monkeypatch, tmp_path):
    rt, scratch, base_word = world
    tip = _changed_tip(scratch)
    tip_word = _word(rt, tip)
    wrong = "0" * 8 if tip_word != "0" * 8 else "1" * 8
    _bind(monkeypatch, rt, scratch, tip, Boxes(base_word), tmp_path, change={"eval_to": wrong}, rows=_rows(wrong))
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "check", write=True)
    assert "eval_to is %s" % wrong in str(exc.value) and tip_word in str(exc.value), str(exc.value)


def test_the_key_with_the_health_list_still_at_the_old_word_is_refused(world, monkeypatch, tmp_path):
    rt, scratch, base_word = world
    tip = _changed_tip(scratch)
    tip_word = _word(rt, tip)
    _bind(monkeypatch, rt, scratch, tip, Boxes(base_word), tmp_path, change={"eval_to": tip_word},
          rows=_rows(base_word))
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "check", write=True)
    assert "does not expect review_eval=%s" % tip_word in str(exc.value), str(exc.value)
    # the control: the same entry with the list at the tip's word passes
    monkeypatch.setattr(rt, "HEALTH_EXPECT", _rows(tip_word))
    rt.closure_guard({}, "check", write=True)


# ---------------------------------------------------------------- R2


def test_an_installed_revision_without_rules_next_is_refused_and_with_it_the_staging_proof_is_owed(
        world, monkeypatch, tmp_path):
    rt, scratch, base_word = world
    tip = _changed_tip(scratch)
    tip_word = _word(rt, tip)
    installed, nxt = "a" * 12, "b" * 12
    boxes = Boxes(base_word, rules=installed)
    _bind(monkeypatch, rt, scratch, tip, boxes, tmp_path, change={"eval_to": tip_word}, rows=_rows(tip_word, nxt))
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "check", write=True)
    assert "names no rules_next" in str(exc.value), str(exc.value)
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", rt.closure_change_form("test", {"eval_to": tip_word,
                                                                              "rules_next": nxt}))
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "check", write=True)
    assert "is not built yet" in str(exc.value), str(exc.value)


# ---------------------------------------------------------------- R3 and R5


def test_a_silent_box_is_refused(world, monkeypatch, tmp_path):
    rt, scratch, base_word = world
    boxes = Boxes(base_word)
    boxes.health[STANDBY] = {}
    _bind(monkeypatch, rt, scratch, scratch.base, boxes, tmp_path, rows=_rows(base_word))
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "check", write=True)
    assert "the standby did not answer" in str(exc.value), str(exc.value)


def test_boxes_that_disagree_are_refused(world, monkeypatch, tmp_path):
    rt, scratch, base_word = world
    other = "0" * 8 if base_word != "0" * 8 else "1" * 8
    boxes = Boxes(base_word)
    boxes.health[STANDBY]["review_eval"] = other
    _bind(monkeypatch, rt, scratch, scratch.base, boxes, tmp_path, rows=_rows(base_word))
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "check", write=True)
    assert "disagree" in str(exc.value) and other in str(exc.value), str(exc.value)


def test_the_guards_refusals_are_fixed_lines_without_text_from_outside(world, monkeypatch, tmp_path):
    """R5 and review finding 8: a box's review_eval or review_rules out of form, a /health read that fails with its
    own text, and a reviewed tip git does not hold: each refusal is the guard's fixed line, and none carries the
    value or the text it was handed."""
    rt, scratch, base_word = world
    planted = "planted-text-0"
    for key, value in (("review_eval", planted), ("review_rules", planted)):
        boxes = Boxes(base_word)
        boxes.health[PRIMARY][key] = value
        _bind(monkeypatch, rt, scratch, scratch.base, boxes, tmp_path, rows=_rows(base_word))
        with pytest.raises(rt.Fail) as exc:
            rt.closure_guard({}, "check", write=False)
        assert "the primary reads a %s that is not" % key in str(exc.value) and planted not in str(exc.value), \
            str(exc.value)

    def failing(host):
        raise rt.Fail("command failed (rc=7): %s" % planted)
    _bind(monkeypatch, rt, scratch, scratch.base, Boxes(base_word), tmp_path, rows=_rows(base_word))
    monkeypatch.setattr(rt, "health_json", failing)
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "check", write=False)
    assert "reading /api/v1/health of the primary did not succeed" in str(exc.value), str(exc.value)
    assert planted not in str(exc.value), str(exc.value)
    _bind(monkeypatch, rt, scratch, "e" * 40, Boxes(base_word), tmp_path, rows=_rows(base_word))
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "check", write=False)
    assert "its word is unknown" in str(exc.value) and "fatal" not in str(exc.value), str(exc.value)


# ---------------------------------------------------------------- R6


def _deployed_change(world, monkeypatch, tmp_path):
    """A run that recorded the boxes' word, merged (code_sha) and deployed the primary only."""
    rt, scratch, base_word = world
    tip = _changed_tip(scratch)
    tip_word = _word(rt, tip)
    boxes = Boxes(base_word)
    _bind(monkeypatch, rt, scratch, tip, boxes, tmp_path, change={"eval_to": tip_word}, rows=_rows(tip_word))
    st = {"schema_done": True}
    rt.closure_guard(st, "code", write=True)
    assert st[rt.CLOSURE_STATE_KEY]["from"] == base_word
    st["code_sha"] = "c" * 40
    boxes.health[PRIMARY]["review_eval"] = tip_word
    boxes.state[PRIMARY] = NEW
    return rt, scratch, boxes, st, base_word, tip_word


def test_a_run_stopped_after_the_primarys_deploy_resumes(world, monkeypatch, tmp_path):
    """The primary in the NEW state at the tip's word, the standby in the OLD state at the recorded word: the resumed
    code phase's guard passes, and so does a second check; once the standby is deployed too, it passes again."""
    rt, scratch, boxes, st, base_word, tip_word = _deployed_change(world, monkeypatch, tmp_path)
    rt.closure_guard(st, "code", write=True)
    rt.closure_guard(st, "check", write=True)
    assert st[rt.CLOSURE_STATE_KEY]["from"] == base_word
    boxes.health[STANDBY]["review_eval"] = tip_word
    boxes.state[STANDBY] = NEW
    rt.closure_guard(st, "check", write=True)


def test_a_box_at_neither_word_is_refused_after_the_record_binds(world, monkeypatch, tmp_path):
    rt, scratch, boxes, st, base_word, tip_word = _deployed_change(world, monkeypatch, tmp_path)
    third = next(w for w in ("0" * 8, "1" * 8, "2" * 8) if w not in (base_word, tip_word))
    boxes.health[STANDBY]["review_eval"] = third
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard(st, "code", write=True)
    assert third in str(exc.value) and base_word in str(exc.value), str(exc.value)
    boxes.health[STANDBY]["review_eval"] = base_word
    boxes.state[STANDBY] = UNKNOWN
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard(st, "code", write=True)
    assert "reads as neither build" in str(exc.value), str(exc.value)


def test_a_merge_recorded_without_a_word_takes_the_old_boxs_word_and_goes_on(world, monkeypatch, tmp_path):
    """A state file that holds the merge (code_sha) but no recorded word, the primary in the NEW state at the tip's
    word: the standby's word in the OLD state is taken as the word before the landing, recorded, and the entry is
    held to it. Without the merge recorded, the same reading is refused (a box runs new code no step of this run
    deployed)."""
    rt, scratch, base_word = world
    tip = _changed_tip(scratch)
    tip_word = _word(rt, tip)
    boxes = Boxes(base_word)
    boxes.health[PRIMARY]["review_eval"] = tip_word
    boxes.state[PRIMARY] = NEW
    _bind(monkeypatch, rt, scratch, tip, boxes, tmp_path, change={"eval_to": tip_word}, rows=_rows(tip_word))
    st = {"code_sha": "c" * 40}
    rt.closure_guard(st, "code", write=True)
    assert st[rt.CLOSURE_STATE_KEY]["from"] == base_word
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "check", write=True)
    assert "no word is recorded" in str(exc.value), str(exc.value)


def test_the_merge_of_main_and_the_tip_must_carry_the_tips_word(world, monkeypatch, tmp_path):
    """Main moved one evaluator file after the lane's base: what would deploy (the merge) is not what the tip
    holds, and the code stage refuses before the merge; the same tip passes in check, which merges nothing."""
    rt, scratch, base_word = world
    tip = scratch.commit({"review_measures.py": lambda raw: raw + b"\n# the lane\n"})
    tip_word = _word(rt, tip)
    scratch.git("checkout", "-q", "main")
    scratch.commit({"combat_measures.py": lambda raw: raw + b"\n# main moved\n"}, "main moved")
    scratch.git("checkout", "-q", "lane")
    _bind(monkeypatch, rt, scratch, tip, Boxes(base_word), tmp_path, change={"eval_to": tip_word},
          rows=_rows(tip_word))
    rt.closure_guard({}, "check", write=False)
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "code", write=False)
    assert "the merge of main and the reviewed tip" in str(exc.value) and tip_word in str(exc.value), str(exc.value)


# ---------------------------------------------------------------- the tree that is deployed (class A)


# Every place the tool starts the deploy play, or another deploy, and why it is placed. A site not listed here is a
# failure that names it.
_DEPLOY_SITES = {
    ("_deploy_both", "zap", "'deploy-scr-backend.yml'"): "the one deploy site; closure_judge_deploy judges its sha first",
    ("phase_snapshot", "zap", "'snapshot-scr.yml'"): "a snapshot of the boxes: no tree is deployed",
    ("phase_bot", "blocking_child", "ssh_argv(PRIMARY, 'deploy-bot')"):
        "the bot is rebuilt on the primary from the tree the code deploy left there (no sha of its own); the api, "
        "whose review_eval the guard holds, is not the bot",
}


def _top_functions(tree):
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def test_every_deploy_goes_through_the_one_wrapper_that_judges_its_sha():
    """Review findings 1 and 2, the census: every call of zap and every deploy wrapper verb in the tool is a site
    _DEPLOY_SITES names; the deploy play's name and its sha variable appear nowhere but in _deploy_both and the
    registry's measure; _deploy_both judges `sha` (never rebound there) before its first box, and every caller of
    _deploy_both hands it the batch's state."""
    rt = _release_train()
    src = Path(rt.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fns = _top_functions(tree)
    found, strays = set(), []
    for name, fn in fns.items():
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in rt.RUNNERS:
                # every process start: the deploy play (zap) and any wrapper verb that names a deploy
                pos = (0,) if n.func.id == "zap" else rt.RUNNERS[n.func.id][0]
                text = ", ".join(ast.unparse(n.args[i]) for i in pos if i < len(n.args))
                if n.func.id == "zap" or "deploy" in text:
                    key = (name, n.func.id, text)
                    (found.add(key) if key in _DEPLOY_SITES else strays.append(key))
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and (
                    "deploy-scr-backend" in n.value or "scr_deploy_ref" in n.value) \
                    and name not in ("_deploy_both", "_reg_zap"):
                strays.append((name, "a constant naming a deploy", n.value[:60]))
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id not in ("COMMAND_REGISTRY",)
                                             for t in n.targets):
            for c in ast.walk(n):
                if isinstance(c, ast.Constant) and isinstance(c.value, str) and "deploy-scr-backend" in c.value:
                    strays.append(("module level", ast.unparse(n.targets[0]), c.value[:60]))
    assert strays == [] and found == set(_DEPLOY_SITES), (strays, set(_DEPLOY_SITES) - found)
    body = fns["_deploy_both"].body
    first = body[1] if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) else body[0]
    assert ast.unparse(first) == "closure_judge_deploy(st, sha, expect)", ast.unparse(first)
    assert not [n for n in ast.walk(fns["_deploy_both"]) if isinstance(n, ast.Name) and n.id == "sha"
                and isinstance(n.ctx, ast.Store)]
    callers = [(name, n) for name, fn in fns.items() for n in ast.walk(fn)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_deploy_both"]
    assert sorted(c[0] for c in callers) == ["phase_code", "phase_deploy_precursor"], callers
    for name, n in callers:
        assert [ast.unparse(k.value) for k in n.keywords if k.arg == "st"] == ["st"], (name, ast.unparse(n))


def test_the_phases_hand_the_guard_their_state_before_any_lease():
    """Limit L8 of round 1: the phases' guard calls, read from the tool's syntax tree. phase_precursor and phase_code
    each ask the guard (with the batch's state) before their first lease; the code phase asks it again for a
    resumed run; phase_check asks it."""
    rt = _release_train()
    fns = _top_functions(ast.parse(Path(rt.__file__).read_text(encoding="utf-8")))

    def calls(name):
        return [(n.lineno, ast.unparse(n)) for n in ast.walk(fns[name]) if isinstance(n, ast.Call)]
    for phase, guard in (("phase_precursor", "assert_reviewed_tip('precursor', st, write=args.go)"),
                         ("phase_code", "assert_reviewed_tip('code', st, write=args.go)"),
                         ("phase_code", "closure_guard(st, 'code', write=args.go)"),
                         ("phase_check", "closure_guard(st, 'check', write=True)")):
        seen = [line for line, text in calls(phase) if text == guard]
        leases = [line for line, text in calls(phase) if text.startswith("controller_lease_session(")]
        assert len(seen) == 1 and all(seen[0] < lease for lease in leases), (phase, guard, seen, leases)
    asked = [text for _l, text in calls("assert_reviewed_tip") if text.startswith("closure_guard(")]
    assert asked == ["closure_guard(st, stage, write=write)"], asked


def test_a_landed_batch_resumed_without_a_record_redeploys_only_the_tips_word(world, monkeypatch, tmp_path):
    """Both boxes already run the new build at the tip's word and the state file (an older tool's) holds the merge but
    no word: the guard records the tip's word as the word before the landing, so the resumed deploy of a sha at the
    tip's word goes on, and a sha at any other word is refused before any play."""
    rt, scratch, base_word = world
    tip = _changed_tip(scratch)
    tip_word = _word(rt, tip)
    boxes = Boxes(tip_word)
    boxes.state = {PRIMARY: NEW, STANDBY: NEW}
    _bind(monkeypatch, rt, scratch, tip, boxes, tmp_path, change={"eval_to": tip_word}, rows=_rows(tip_word))
    st = {"code_sha": tip}
    rt.closure_guard(st, "code", write=True)
    assert st[rt.CLOSURE_STATE_KEY]["from"] == tip_word
    plays = _deploys(monkeypatch, rt)
    with pytest.raises(rt.Fail) as exc:
        rt._deploy_both(scratch.base, expect="new", st=dict(st, code_sha=scratch.base))
    assert base_word in str(exc.value) and plays == [], (str(exc.value), plays)
    rt._deploy_both(tip, expect="new", st=st)
    assert len(plays) == 2, plays


def test_the_precursor_deploy_is_judged_by_the_precursors_own_word(world, monkeypatch, tmp_path):
    """Review finding 1: main carries an evaluator change the boxes do not run (word B); the tip leaves the evaluator
    as the boxes run it (word A), so the tip's guard asks nothing. The precursor (main with the batch's sql) carries
    B: the precursor stage refuses before the commit, and _deploy_both refuses that sha before any play. The control:
    a precursor at A deploys to both boxes."""
    rt, scratch, base_word = world
    tip = scratch.commit({"main.py": b"# the lane, outside the evaluator\n"})
    scratch.git("checkout", "-q", "main")
    main_b = scratch.commit({"review_rules.py": lambda raw: raw + b"\n# main moved the evaluator\n"}, "main moved")
    scratch.git("checkout", "-q", "lane")
    word_b = _word(rt, main_b)
    assert word_b != base_word
    _bind(monkeypatch, rt, scratch, tip, Boxes(base_word), tmp_path, rows=_rows(base_word))
    monkeypatch.setattr(rt, "ALL_SQL", ["999_closure_test.sql"])
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "precursor", write=False)
    assert "main %s carries the word %s" % (main_b[:12], word_b) in str(exc.value), str(exc.value)
    plays = _deploys(monkeypatch, rt)
    st = {rt.CLOSURE_STATE_KEY: _record(base_word), "precursor_sha": main_b}
    with pytest.raises(rt.Fail) as exc:
        rt._deploy_both(main_b, expect="old", st=st)
    assert word_b in str(exc.value) and base_word in str(exc.value) and plays == [], (str(exc.value), plays)
    rt._deploy_both(scratch.base, expect="old", st=dict(st, precursor_sha=scratch.base))
    assert [p for p, _e in plays] == ["deploy-scr-backend.yml"] * 2, plays


def test_a_recorded_code_sha_from_an_older_run_is_judged_by_its_own_word(world, monkeypatch, tmp_path):
    """Review finding 2: the tip and the entry name word B; a state file from an older run records as code_sha a
    real merge that carries C (main had moved the evaluator too). The resumed code deploy computes the merge's own
    word and refuses before any play. The control: a recorded merge that carries B deploys."""
    rt, scratch, base_word = world
    tip = _changed_tip(scratch)
    word_b = _word(rt, tip)
    scratch.git("checkout", "-q", "main")
    scratch.commit({"combat_measures.py": lambda raw: raw + b"\n# main moved\n"}, "main moved")
    scratch.git("merge", "-q", "--no-ff", "-m", "merge the lane", "lane")
    merge_c = scratch.git("rev-parse", "HEAD")
    word_c = _word(rt, merge_c)
    scratch.git("reset", "-q", "--hard", scratch.base)
    scratch.git("merge", "-q", "--no-ff", "-m", "merge the lane", "lane")
    merge_b = scratch.git("rev-parse", "HEAD")
    scratch.git("checkout", "-q", "lane")
    assert len({base_word, word_b, word_c}) == 3 and _word(rt, merge_b) == word_b
    _bind(monkeypatch, rt, scratch, tip, Boxes(base_word), tmp_path, change={"eval_to": word_b}, rows=_rows(word_b))
    plays = _deploys(monkeypatch, rt)
    st = {rt.CLOSURE_STATE_KEY: _record(base_word), "code_sha": merge_c, "schema_done": True}
    with pytest.raises(rt.Fail) as exc:
        rt._deploy_both(merge_c, expect="new", st=st)
    assert word_c in str(exc.value) and plays == [], (str(exc.value), plays)
    rt._deploy_both(merge_b, expect="new", st=dict(st, code_sha=merge_b))
    assert len(plays) == 2, plays


def test_the_code_deploy_must_carry_the_target_word(world, monkeypatch, tmp_path):
    """With closure_change eval_to B, a code sha that carries the word before the landing (A) is in the approved set
    of the precursor but not the code deploy's target: refused before any play."""
    rt, scratch, base_word = world
    tip = _changed_tip(scratch)
    word_b = _word(rt, tip)
    _bind(monkeypatch, rt, scratch, tip, Boxes(base_word), tmp_path, change={"eval_to": word_b}, rows=_rows(word_b))
    plays = _deploys(monkeypatch, rt)
    st = {rt.CLOSURE_STATE_KEY: _record(base_word), "code_sha": scratch.base}
    with pytest.raises(rt.Fail) as exc:
        rt._deploy_both(scratch.base, expect="new", st=st)
    assert "approved for %s" % word_b in str(exc.value) and plays == [], (str(exc.value), plays)


def test_a_deploy_without_a_recorded_word_is_not_made(world, monkeypatch, tmp_path):
    rt, scratch, base_word = world
    _bind(monkeypatch, rt, scratch, scratch.base, Boxes(base_word), tmp_path, rows=_rows(base_word))
    plays = _deploys(monkeypatch, rt)
    with pytest.raises(rt.Fail) as exc:
        rt._deploy_both(scratch.base, expect="new", st={"code_sha": scratch.base})
    assert "no word before the landing is recorded" in str(exc.value) and plays == [], (str(exc.value), plays)


# ---------------------------------------------------------------- [6]: the command line path


def test_the_command_line_refuses_a_missing_key_before_any_token_or_lease(world, monkeypatch, tmp_path, capsys):
    """Review finding 6: `run --go` of a batch whose tip changes the word and whose entry carries no key stops at the
    guard's first pass, through main(): no train token is written, no lease is taken, no phase runs."""
    rt, scratch, base_word = world
    tip = _changed_tip(scratch)
    _bind(monkeypatch, rt, scratch, tip, Boxes(base_word), tmp_path, rows=_rows(base_word))
    events = []

    def refused(what):
        def f(*a, **kw):
            events.append(what)
            raise rt.Fail("%s was reached" % what)
        return f
    for name in ("train_token_write", "controller_lease_session", "phase_snapshot", "phase_precursor"):
        monkeypatch.setattr(rt, name, refused(name))
    monkeypatch.setattr(rt, "PHASES", [(p, refused("phase " + p)) for p, _fn in rt.PHASES])
    monkeypatch.setattr(rt, "BATCHES", {"zz-closure-guard": {}})
    monkeypatch.setattr(rt, "select_batch", lambda name: None)
    monkeypatch.setattr(rt, "assert_run_cmdlines_fit", lambda selected, st: None)
    monkeypatch.setattr(rt, "git_forms_preflight", lambda selected, st: [])
    monkeypatch.setattr(rt, "NEW_ROUTES", [])
    monkeypatch.setattr(rt, "JSON_MARKERS", [])
    monkeypatch.setattr(rt, "CODE_MARKERS", ["review_eval"])
    monkeypatch.setattr(rt.sys, "argv", ["release_train.py", "run", "--go", "--batch", "zz-closure-guard"])
    assert rt.main() == 1
    out = capsys.readouterr().out
    assert events == [], events
    assert "no closure_change" in out and "before a train token was written" in out, out
