"""The release tool's closure guard (item 41).

/health's review_eval is the leading hex of review_rules.code_fingerprint over the files review_rules.CODE_REQUIRED
names. A batch whose deploy changes one of them changes that word, and an installed rules revision built for the old
word stops loading. The release tool (scripts/deploy/release_train.py, local to the operating seat and not tracked)
computes the word the batch's reviewed tip will publish, from git objects, and refuses before anything is merged or
deployed unless the batch entry answers for a change: closure_change.eval_to equal to the tip's word and a health
list that expects that word on both roles.

The tool carries its own framing routine; the first test pins it against review_rules.code_fingerprint over this
checkout's files, so a change of the framing in review_rules.py turns this file red on a seat that holds the tool.
Every other test builds a scratch git repository holding copies of the evaluator's files, and fakes for the two
boxes' /health and code state. Without the tool every test here skips, as the tool's other tests do.
"""
import importlib.util
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
API = REPO / "backend" / "api"
PRIMARY, STANDBY = "primary-box", "standby-box"
OLD = (True, False, True, ["old"])
NEW = (True, True, False, ["new"])
UNKNOWN = (True, False, False, ["neither"])


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


def _evaluator_names():
    import review_rules as rr
    return rr.CODE_REQUIRED


class Scratch:
    """A git repository with backend/api holding copies of this checkout's evaluator files on main, and a lane
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
        for name in _evaluator_names():
            shutil.copyfile(API / name, api / name)
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
        """Apply {file: bytes or a function of the old bytes} on the lane and commit; returns the sha."""
        for name, new in edits.items():
            p = self.path(name)
            p.write_bytes(new(p.read_bytes()) if callable(new) else new)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")


def _add_to_list(extra):
    def edit(raw):
        out, n = re.subn(rb"(CODE_REQUIRED = \([^)]*)\)", lambda m: m.group(1) + b', "' + extra + b'")', raw, count=1)
        assert n == 1
        return out
    return edit


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
    monkeypatch.setattr(rt, "STATE_PATH", str(tmp_path / "state" / "train-state.json"))
    monkeypatch.setattr(rt, "health_json", boxes.health_json)
    monkeypatch.setattr(rt, "code_state", boxes.code_state)


def _word(rt, scratch, rev):
    return rt.closure_word(rt.closure_git_reader(rev))[0]


@pytest.fixture
def world(tmp_path, monkeypatch):
    rt = _release_train()
    scratch = Scratch(tmp_path / "scratch")
    monkeypatch.setattr(rt, "REPO", str(scratch.repo))
    base_word = _word(rt, scratch, scratch.base)
    return rt, scratch, base_word


def _changed_tip(scratch):
    return scratch.commit({"review_rules.py": lambda raw: raw + b"\n# a change of the evaluator\n"})


# ---------------------------------------------------------------- the routine against the loader


def test_the_tools_routine_is_the_loaders_fingerprint(tmp_path):
    """The tool's word over this checkout's files equals review_rules.code_fingerprint's leading hex, its full
    digest equals the loader's, the list it reads is the loader's CODE_REQUIRED, and both read CRLF as LF."""
    rt = _release_train()
    import review_rules as rr

    def reader(root):
        return lambda n: (root / n).read_bytes() if (root / n).is_file() else None
    word, names, rev_hex = rt.closure_word(reader(API))
    assert names == rr.CODE_REQUIRED and rev_hex == rr.CONTRACT_BOUNDS["rev_hex"]
    full = rr.code_fingerprint(api_dir=str(API))
    assert word == full[:rt.CLOSURE_EVAL_HEX], (word, full[:8])
    files = {"code/" + n: (API / n).read_bytes().replace(b"\r\n", b"\n") for n in names}
    assert rt.closure_framed(rr.CODE_DOMAIN, rr.CONTRACT_BOUNDS["frame_bytes"], files) == full
    for ending in (b"\n", b"\r\n"):
        d = tmp_path / ("crlf" if ending == b"\r\n" else "lf")
        d.mkdir()
        for n in names:
            (d / n).write_bytes((API / n).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", ending))
        assert rt.closure_word(reader(d))[0] == rr.code_fingerprint(api_dir=str(d))[:8] == word


# ---------------------------------------------------------------- R1


def test_equal_words_ask_for_no_key_and_record_the_boxes_word(world, monkeypatch, tmp_path):
    """The tip leaves the six files as the boxes run them: no closure_change is asked and the word is recorded."""
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
    tip_word = _word(rt, scratch, tip)
    assert tip_word != base_word
    boxes = Boxes(base_word)
    _bind(monkeypatch, rt, scratch, tip, boxes, tmp_path, rows=_rows(base_word))
    monkeypatch.setattr(rt, "ALL_SQL", [])
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
    tip_word = _word(rt, scratch, tip)
    wrong = "0" * 8 if tip_word != "0" * 8 else "1" * 8
    _bind(monkeypatch, rt, scratch, tip, Boxes(base_word), tmp_path, change={"eval_to": wrong}, rows=_rows(wrong))
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "check", write=True)
    assert "eval_to is %s" % wrong in str(exc.value) and tip_word in str(exc.value), str(exc.value)


def test_the_key_with_the_health_list_still_at_the_old_word_is_refused(world, monkeypatch, tmp_path):
    rt, scratch, base_word = world
    tip = _changed_tip(scratch)
    tip_word = _word(rt, scratch, tip)
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
    tip_word = _word(rt, scratch, tip)
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


# ---------------------------------------------------------------- R3


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


# ---------------------------------------------------------------- R4


def test_a_seventh_file_in_the_tips_list_is_covered(world, monkeypatch, tmp_path):
    """A file added to CODE_REQUIRED at the tip is in the word, as the loader computes it, with no change of the
    tool; a change of that file alone moves the word."""
    rt, scratch, base_word = world
    import review_rules as rr
    tip = scratch.commit({"extra_measures.py": b"X = 1\n", "review_rules.py": _add_to_list(b"extra_measures.py")})
    word, names, _ = rt.closure_word(rt.closure_git_reader(tip))
    assert names[-1] == "extra_measures.py" and len(names) == len(_evaluator_names()) + 1
    assert word == rr.code_fingerprint(names=names, api_dir=str(scratch.repo / "backend" / "api"))[:8]
    again = scratch.commit({"extra_measures.py": b"X = 2\n"})
    assert _word(rt, scratch, again) != word


def test_a_list_that_does_not_parse_or_names_a_missing_file_is_refused(world, monkeypatch, tmp_path):
    rt, scratch, base_word = world
    bad = scratch.commit({"review_rules.py": lambda raw: re.sub(rb"CODE_REQUIRED = \(", b"CODE_REQUIRED = tuple(",
                                                                raw, count=1)})
    with pytest.raises(rt.Fail) as exc:
        rt.closure_word(rt.closure_git_reader(bad))
    assert "not a literal" in str(exc.value) or "does not parse" in str(exc.value), str(exc.value)
    scratch.git("reset", "-q", "--hard", scratch.base)
    ghost = scratch.commit({"review_rules.py": _add_to_list(b"ghost_measures.py")})
    with pytest.raises(rt.Fail) as exc:
        rt.closure_word(rt.closure_git_reader(ghost))
    assert "ghost_measures.py" in str(exc.value), str(exc.value)


# ---------------------------------------------------------------- R6


def _deployed_change(world, monkeypatch, tmp_path):
    """A run that recorded the boxes' word, merged (code_sha) and deployed the primary only."""
    rt, scratch, base_word = world
    tip = _changed_tip(scratch)
    tip_word = _word(rt, scratch, tip)
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
    tip_word = _word(rt, scratch, tip)
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


def test_the_merge_of_main_and_the_tip_must_carry_the_tips_files(world, monkeypatch, tmp_path):
    """Main moved one evaluator file after the lane's base: what would deploy (the merge) is not what the tip
    holds, and the code stage refuses before the merge; the same tip passes in check, which merges nothing."""
    rt, scratch, base_word = world
    tip = scratch.commit({"review_measures.py": lambda raw: raw + b"\n# the lane\n"})
    tip_word = _word(rt, scratch, tip)
    scratch.git("checkout", "-q", "main")
    scratch.commit({"combat_measures.py": lambda raw: raw + b"\n# main moved\n"}, "main moved")
    scratch.git("checkout", "-q", "lane")
    _bind(monkeypatch, rt, scratch, tip, Boxes(base_word), tmp_path, change={"eval_to": tip_word},
          rows=_rows(tip_word))
    rt.closure_guard({}, "check", write=False)
    with pytest.raises(rt.Fail) as exc:
        rt.closure_guard({}, "code", write=False)
    assert "the merge of main and the reviewed tip" in str(exc.value) and tip_word in str(exc.value), str(exc.value)
