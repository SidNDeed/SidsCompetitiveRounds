"""The release tool's closure guard (item 41)."""
import ast
import contextlib
import hashlib
import importlib.util
import io
import itertools
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
API = REPO / "backend" / "api"
PRIMARY, STANDBY = "primary-box", "standby-box"
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
    assert spawned == [], spawned


class Scratch:
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

    def index_commit(self, put, drop=()):
        for path in drop:
            self.git("rm", "-q", "--cached", path)
        for path, data in put.items():
            blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], input=data, cwd=str(self.repo),
                                  capture_output=True, check=True).stdout.decode("ascii").strip()
            self.git("update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, path))
        self.git("commit", "-q", "-m", "index commit")
        return self.git("rev-parse", "HEAD")

    def path(self, name):
        return self.repo / "backend" / "api" / name

    def commit(self, edits, message="lane"):
        for name, new in edits.items():
            p = self.repo / name if "/" in name else self.path(name)
            if new is None:
                p.unlink()
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(new(p.read_bytes()) if callable(new) else new)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")


def _direct(scratch):
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

    def health_json(self, host):
        if self.health[host] is None:
            raise OSError("silent")
        return dict(self.health[host])


def _bind(monkeypatch, rt, scratch, tip, boxes, tmp_path, change=None, rows=None, base=None):
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
    monkeypatch.setattr(rt, "closure_base", lambda st: _taken(base or scratch.base))


def _taken(base, prior=None):
    return {"base": base, "from": "boxes-head", "relation": "equal", "prior": prior}


def _rw(rt, rev):
    r = rt.closure_routine(rev)
    return r["word"] if r else None


def _word(rt, rev):
    word = _rw(rt, rev)
    assert word is not None and rt.CLOSURE_WORD.fullmatch(word), word
    return word


@pytest.fixture
def world(tmp_path, monkeypatch):
    rt = _release_train()
    if os.name != "nt":
        pytest.skip("the closure routine's child runs in a Windows job object")
    scratch = Scratch(tmp_path / "scratch")
    monkeypatch.setattr(rt, "REPO", str(scratch.repo))
    return rt, scratch, _word(rt, scratch.base)


def _changed_tip(scratch):
    return scratch.commit({"review_rules.py": lambda raw: raw + b"\n# a change of the evaluator\n"})


def _predict(rt, rev, base):
    return rt.closure_prediction(rev, rev, base, "the test tree")


# ---------------------------------------------------------------- the word of a commit


def test_the_tools_word_is_the_routines_own_on_this_checkouts_files(world):
    rt, scratch, base_word = world
    assert base_word == _direct(scratch)


def test_line_ends_inside_a_comment_are_read_as_the_routine_reads_them(world):
    rt, scratch, base_word = world
    words = []
    for ending in (b"\r\r\r\n", b"\r\r\n"):
        sha = scratch.commit({"review_measures.py": lambda raw, e=ending: raw.split(b"\n# crs")[0] + b"\n# crs" + e})
        words.append(_word(rt, sha))
        assert words[-1] == _direct(scratch), (ending, words[-1])
    assert words[0] != words[1], words


def test_a_boot_file_in_crlf_over_the_bound_answers_refused_and_the_prediction_refuses(world, monkeypatch):
    rt, scratch, base_word = world
    bound = 1048576
    boot = scratch.path("review_boot.py").read_bytes()
    pad = bound - 128 - len(boot)
    padded = boot + b"\n" + b"#" * 63 + b"\n" + (b"#" * 63 + b"\n") * (pad // 64)
    assert len(padded) <= bound < len(padded.replace(b"\n", b"\r\n"))
    lf = scratch.commit({"review_boot.py": padded})
    assert _word(rt, lf) == _direct(scratch)
    crlf = scratch.commit({"review_boot.py": padded.replace(b"\n", b"\r\n")})
    assert _direct(scratch) == "refused" and _rw(rt, crlf) == "refused"
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", None)
    with pytest.raises(rt.Fail) as exc:
        _predict(rt, crlf, scratch.base)
    assert "answers refused" in str(exc.value), str(exc.value)


def test_the_domain_bound_a_second_time_is_read_as_the_routine_reads_it(world):
    rt, scratch, base_word = world
    tip = scratch.commit({"review_rules.py": lambda raw: raw + b"\n\nmatch b'scr-review-code-closure-x\\n':\n"
                                                                b"    case CODE_DOMAIN:\n        pass\n"})
    word = _word(rt, tip)
    assert word == _direct(scratch) and word != base_word, (word, base_word)


def test_a_seventh_file_is_covered_when_the_loader_executes_it_and_refused_when_it_does_not(world):
    rt, scratch, base_word = world

    def sub(pattern, repl):
        def f(raw):
            out, n = re.subn(pattern, repl, raw, count=1)
            assert n == 1
            return out
        return f
    listed = sub(rb'(CODE_REQUIRED = \([^)]*)\)', lambda m: m.group(1) + b', "extra_measures.py")')
    loaded = sub(rb'(SOURCE_ONLY = \([^)]*)\)', lambda m: m.group(1) + b', "extra_measures")')
    imported = sub(rb"\nimport combat_measures as cbm\n",
                   b"\nimport combat_measures as cbm\nimport extra_measures as _xm  # noqa: F401\n")
    unloaded = scratch.commit({"extra_measures.py": b"X = 1\n", "review_rules.py": listed})
    assert _direct(scratch) == "refused" and _rw(rt, unloaded) == "refused"
    tip = scratch.commit({"review_boot.py": loaded, "review_rules.py": imported})
    word = _word(rt, tip)
    assert word == _direct(scratch) and word != base_word
    again = scratch.commit({"extra_measures.py": b"X = 2\n"})
    assert _word(rt, again) == _direct(scratch) != word


def test_a_commit_without_the_routine_is_unknown_and_refused(world, monkeypatch):
    rt, scratch, base_word = world
    gone = scratch.commit({"review_rules.py": lambda raw: raw.replace(b"def review_eval(", b"def review_eval_gone(")})
    assert _rw(rt, gone) is None
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", None)
    with pytest.raises(rt.Fail) as exc:
        _predict(rt, gone, scratch.base)
    assert "did not run to its lines" in str(exc.value), str(exc.value)


# ---------------------------------------------------------------- the envelope (B3, B4)


def test_i_a_file_the_loader_opens_under_another_spelling_is_refused(world, monkeypatch):
    rt, scratch, base_word = world
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", None)
    raw = scratch.path("review_measures.py").read_bytes()
    tip = scratch.index_commit({"backend/api/REVIEW_measures.py": raw}, drop=("backend/api/review_measures.py",))
    with pytest.raises(rt.Fail) as exc:
        _predict(rt, tip, scratch.base)
    assert "(i)" in str(exc.value), str(exc.value)


def test_i_two_directories_that_differ_only_by_case_are_unknown(world, monkeypatch):
    rt, scratch, base_word = world
    ok = scratch.index_commit({"backend/api/pkg/a.py": b"A = 1\n", "backend/api/pkg/b.py": b"B = 1\n"})
    assert _rw(rt, ok) == base_word
    tip = scratch.index_commit({"backend/api/Pkg/b.py": b"B = 1\n"}, drop=("backend/api/pkg/b.py",))
    assert _rw(rt, tip) is None


def test_ii_an_attributes_line_that_can_match_backend_api_is_refused_and_mains_lines_pass(world, monkeypatch):
    rt, scratch, base_word = world
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", None)
    mains = (REPO / ".gitattributes").read_bytes().replace(b"\r\n", b"\n")
    ok = scratch.commit({"./.gitattributes": mains})
    assert _predict(rt, ok, scratch.base) == base_word
    for line in (b"backend/api/review_boot.py text eol=crlf\n", b"*.py text eol=crlf\n", b"backend/** -text\n"):
        bad = scratch.commit({"./.gitattributes": mains + line})
        with pytest.raises(rt.Fail) as exc:
            _predict(rt, bad, scratch.base)
        assert "(ii)" in str(exc.value), (line, str(exc.value))


def test_iii_a_build_file_changed_needs_its_sha256_in_the_key(world, monkeypatch):
    rt, scratch, base_word = world
    base = scratch.commit({"Dockerfile": b"FROM x\nCOPY . .\n"}, "base with a Dockerfile")
    body = b"FROM x\nCOPY . .\nRUN echo changed\n"
    tip = scratch.commit({"Dockerfile": body})
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", None)
    with pytest.raises(rt.Fail) as exc:
        _predict(rt, tip, base)
    assert "(iii) backend/api/Dockerfile differ(s)" in str(exc.value), str(exc.value)
    assert "the entry holds no build part" in str(exc.value), str(exc.value)
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", {"build": {"backend/api/Dockerfile": "0" * 64}})
    with pytest.raises(rt.Fail) as exc:
        _predict(rt, tip, base)
    assert "(iii) backend/api/Dockerfile differs at" in str(exc.value), str(exc.value)
    assert "closure_change.build does not name its sha256" in str(exc.value), str(exc.value)
    key = {"build": {"backend/api/Dockerfile": hashlib.sha256(body).hexdigest()}}
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", rt.closure_change_form("test", key))
    assert _predict(rt, tip, base) == base_word


def test_iii_a_build_file_the_tip_deletes_is_refused_unless_the_build_part_names_it_absent(world, monkeypatch):
    rt, scratch, base_word = world
    base = scratch.commit({"Dockerfile": b"FROM x\nCOPY . .\n"}, "base with a Dockerfile")
    tip = scratch.commit({"Dockerfile": None})
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", rt.closure_change_form("test", {"build": {}}))
    with pytest.raises(rt.Fail) as exc:
        _predict(rt, tip, base)
    assert ("(iii) backend/api/Dockerfile differs at the test tree from the base %s and closure_change.build does not "
            "name its sha256, or \"absent\" where the tree holds no such file" % base[:12]) in str(exc.value), str(
                exc.value)
    key = {"build": {"backend/api/Dockerfile": "absent"}}
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", rt.closure_change_form("test", key))
    assert _predict(rt, tip, base) == base_word


def test_the_ancestor_refusal_given_the_source_record_names_the_recorded_base_or_a_fresh_run(world, monkeypatch):
    rt, scratch, base_word = world
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", None)
    lane = scratch.commit({"main.py": b"# lane\n"})
    scratch.git("checkout", "-q", "main")
    other = scratch.commit({"main.py": b"# main\n"}, "main moved")
    scratch.git("checkout", "-q", "lane")
    with pytest.raises(rt.Fail) as exc:
        rt.closure_prediction(lane, lane, other, "the test tree", "record")
    msg = str(exc.value)
    assert ("it is the base this run recorded: give that base or leave the word out, or start a fresh run with "
            "--boxes-head read on both boxes; refused") in msg and "read HEAD on both boxes again" not in msg, msg


def test_iii_a_changed_script_a_dockerfile_run_line_names_is_refused(world, monkeypatch):
    rt, scratch, base_word = world
    base = scratch.commit({"Dockerfile": b"FROM x\nCOPY . .\nRUN python -B stamp_files.py /app\n",
                           "stamp_files.py": b"print(1)\n"}, "base with a build script")
    tip = scratch.commit({"stamp_files.py": b"print(2)\n"})
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", None)
    with pytest.raises(rt.Fail) as exc:
        _predict(rt, tip, base)
    assert "(iii) backend/api/stamp_files.py" in str(exc.value), str(exc.value)


def test_iv_a_store_on_the_evaluator_from_outside_is_refused(world, monkeypatch):
    rt, scratch, base_word = world
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", None)
    for body in (b"import review_rules as _r\n_r.CODE_DOMAIN += b'changed'\n",
                 b"import seat_mod as _s\n_s.rr.CODE_DOMAIN = b'x'\n",
                 b"from review_rules import CODE_REQUIRED\nCODE_REQUIRED.append('x')\n",
                 b"import review_rules\nsetattr(review_rules, 'CODE_DOMAIN', b'x')\n",
                 b"import review_rules as rr\ndef f(rr):\n    return rr\n"):
        tip = scratch.commit({"seat_mod.py": b"import review_rules as rr\n", "main.py": body})
        with pytest.raises(rt.Fail) as exc:
            _predict(rt, tip, scratch.base)
        assert "(iv)" in str(exc.value) and "outside the listed places" in str(exc.value), (body, str(exc.value))


def test_iv_the_checkouts_backend_api_holds_no_form_the_census_refuses():
    rt = _release_train()
    paths = [p.relative_to(API).as_posix() for p in API.rglob("*.py")]
    count, hits, unfollowed = rt.closure_census(str(API), paths, list(EVALUATOR))
    assert count >= 30 and hits == [], hits[:5]
    assert list(unfollowed) == ["call", "container", "return", "attribute", "loop"], unfollowed
    print("files read %d; uses counted by place %s" % (count, unfollowed))


def test_the_base_must_be_an_ancestor_of_the_judged_tree(world, monkeypatch):
    rt, scratch, base_word = world
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", None)
    lane = scratch.commit({"main.py": b"# lane\n"})
    scratch.git("checkout", "-q", "main")
    other = scratch.commit({"main.py": b"# main\n"}, "main moved")
    scratch.git("checkout", "-q", "lane")
    with pytest.raises(rt.Fail) as exc:
        _predict(rt, lane, other)
    assert "not an ancestor" in str(exc.value) and "name it with --boxes-head" in str(exc.value), str(exc.value)


# ---------------------------------------------------------------- the table (A-1)

O_W, N_W, X_W = "aaaa0000", "bbbb1111", "cccc2222"
TIP, BASE, PRE, CODE = "a" * 40, "b" * 40, "1" * 40, "2" * 40
AXES = (("rec", ("absent", "valid", "invalid")), ("pre", (False, True)), ("code", (False, True)),
        ("P", ("O", "N", "X", "S")), ("Sb", ("O", "N", "X", "S")), ("key", ("absent", "valid", "invalid")),
        ("call", ("F", "W", "Jp", "Jc")))


def _words(c):
    new = O_W if c["key"] == "absent" else N_W
    return {"O": O_W, "N": new, "X": X_W, "S": None}, new


def _as8(c):
    w, new = _words(c)
    p, s = w[c["P"]], w[c["Sb"]]
    return p in (O_W, new) and s in (O_W, new) and not (new != O_W and p == O_W and s == new)


ROWS = (
    (1, lambda c: c["key"] == "invalid", "refuse"),
    (2, lambda c: (c["pre"] or c["code"]) and c["rec"] == "invalid", "refuse"),
    (3, lambda c: (c["pre"] or c["code"]) and c["rec"] == "absent", "refuse"),
    (4, lambda c: c["call"] in "FW" and not (c["pre"] or c["code"])
        and _words(c)[0][c["P"]] == O_W and _words(c)[0][c["Sb"]] == O_W, "pass"),
    (5, lambda c: c["call"] in "FW" and not (c["pre"] or c["code"]), "refuse"),
    (6, lambda c: c["call"] == "Jp" and not c["pre"], "refuse"),
    (7, lambda c: c["call"] == "Jc" and not c["code"], "refuse"),
    (8, lambda c: c["call"] == "Jp" and c["code"], "refuse"),
    (9, lambda c: c["call"] in "FW" and _as8(c), "pass"),
    (10, lambda c: c["call"] in "FW", "refuse"),
    (11, lambda c: c["call"] == "Jp" and _as8(c), "pass"),
    (12, lambda c: c["call"] == "Jc" and _as8(c), "pass"),
    (13, lambda c: True, "refuse"),
)


ROW_13_CELLS = 75


def _first_row(c):
    return next(r for r in ROWS if r[1](c))


def _cell_world(monkeypatch, rt, c, saved):
    w, new = _words(c)
    monkeypatch.setattr(rt, "REVIEWED_TIP", TIP)
    monkeypatch.setattr(rt, "PRIMARY", PRIMARY)
    monkeypatch.setattr(rt, "STANDBY", STANDBY)
    monkeypatch.setattr(rt, "ALL_SQL", [])
    change = {"absent": None, "valid": {"eval_to": N_W}, "invalid": {"eval_to": X_W}}[c["key"]]
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", change)
    monkeypatch.setattr(rt, "HEALTH_EXPECT", _rows(new))
    words = {TIP: new, BASE: O_W, PRE: O_W, CODE: new}
    monkeypatch.setattr(rt, "closure_prediction", lambda rev, anc, base, what, source="boxes-head": words[rev])
    monkeypatch.setattr(rt, "closure_base", lambda st: _taken(BASE))
    health = {PRIMARY: w[c["P"]], STANDBY: w[c["Sb"]]}

    def hj(host):
        if health[host] is None:
            raise OSError("silent")
        return {"review_eval": health[host], "review_rules": "absent"}
    monkeypatch.setattr(rt, "health_json", hj)
    monkeypatch.setattr(rt, "save_state", lambda st: saved.append(dict(st)))
    st = {}
    if c["rec"] != "absent":
        st[rt.CLOSURE_STATE_KEY] = {"from": O_W, "to": new if c["rec"] == "valid" else X_W, "base": BASE,
                                    "tip": TIP, "recorded_at": "2026-11-22T00:00:00Z", "base_from": "boxes-head",
                                    "base_relation": "equal", "unfollowed": dict.fromkeys(rt.CLOSURE_UNFOLLOWED, 0)}
    if c["pre"]:
        st["precursor_sha"] = PRE
    if c["code"]:
        st["code_sha"] = CODE
    return st


def _call(rt, c, st):
    if c["call"] == "F":
        return rt.closure_guard(st, "start", write=True, reach=())
    if c["call"] == "W":
        return rt.closure_guard(st, "check")
    return rt.closure_judge_deploy(st, PRE if c["call"] == "Jp" else CODE, "old" if c["call"] == "Jp" else "new")


def _run_cell(monkeypatch, rt, c):
    saved = []
    st = _cell_world(monkeypatch, rt, c, saved)
    try:
        _call(rt, c, st)
        return "pass", None, saved
    except rt.ClosureRefusal as e:
        m = re.search(r"row (\d+):", str(e))
        return "refuse", int(m.group(1)) if m else str(e), saved


def test_the_table_walks_every_cell_against_its_oracle(monkeypatch, capsys):
    rt = _release_train()
    cells = [dict(zip([a for a, _v in AXES], vals)) for vals in itertools.product(*[v for _a, v in AXES])]
    assert len(cells) == 2304
    reached, wrong, last = set(), [], []
    for c in cells:
        row, _pred, outcome = _first_row(c)
        reached.add(row)
        got, got_row, saved = _run_cell(monkeypatch, rt, c)
        want_saved = 1 if (row == 4 and c["call"] == "F") else 0
        if got != outcome or (got == "refuse" and got_row != row) or len(saved) != want_saved:
            wrong.append((c, row, got, got_row, len(saved)))
        if row == 13:
            last.append(c)
        capsys.readouterr()
    assert wrong == [], (len(wrong), wrong[:3])
    assert reached == set(range(1, 14)), sorted(reached)
    with capsys.disabled():
        print("\ncells reaching row 13: %d" % len(last))
        for c in last:
            print("row 13 cell: " + " ".join("%s=%s" % (a, c[a]) for a, _v in AXES))
    assert len(last) == ROW_13_CELLS, len(last)


@pytest.mark.parametrize("row,cell", [
    (1, dict(rec="absent", pre=False, code=False, P="O", Sb="O", key="invalid", call="F")),
    (2, dict(rec="invalid", pre=False, code=True, P="N", Sb="N", key="valid", call="W")),
    (3, dict(rec="absent", pre=True, code=False, P="O", Sb="O", key="valid", call="F")),
    (4, dict(rec="absent", pre=False, code=False, P="O", Sb="O", key="valid", call="F")),
    (5, dict(rec="absent", pre=False, code=False, P="X", Sb="O", key="valid", call="F")),
    (6, dict(rec="valid", pre=False, code=True, P="O", Sb="O", key="valid", call="Jp")),
    (7, dict(rec="valid", pre=True, code=False, P="O", Sb="O", key="valid", call="Jc")),
    (8, dict(rec="valid", pre=True, code=True, P="O", Sb="O", key="valid", call="Jp")),
    (9, dict(rec="valid", pre=False, code=True, P="N", Sb="O", key="valid", call="F")),
    (10, dict(rec="valid", pre=False, code=True, P="O", Sb="N", key="valid", call="W")),
    (11, dict(rec="valid", pre=True, code=False, P="O", Sb="O", key="valid", call="Jp")),
    (12, dict(rec="valid", pre=True, code=True, P="N", Sb="O", key="valid", call="Jc")),
    (13, dict(rec="valid", pre=False, code=True, P="S", Sb="O", key="valid", call="Jc")),
])
def test_one_named_cell_per_row(monkeypatch, row, cell):
    rt = _release_train()
    want = {4: "pass", 9: "pass", 11: "pass", 12: "pass"}.get(row, "refuse")
    got, got_row, saved = _run_cell(monkeypatch, rt, cell)
    assert (got, got_row if got == "refuse" else row) == (want, row), (got, got_row)
    assert len(saved) == (1 if row == 4 else 0), saved


def test_a_resumed_run_with_the_primary_new_passes_f_writes_nothing_and_the_code_judge_finishes_the_standby(
        monkeypatch):
    rt = _release_train()
    cell = dict(rec="valid", pre=False, code=True, P="N", Sb="O", key="valid", call="F")
    saved = []
    st = _cell_world(monkeypatch, rt, cell, saved)
    before = json.dumps(st, sort_keys=True)
    rt.closure_guard(st, "start", write=True, reach=())
    assert saved == [] and json.dumps(st, sort_keys=True) == before
    plays = _fake_plays(monkeypatch, rt, {PRIMARY: N_W, STANDBY: N_W})
    rt._deploy_both(CODE, expect="new", st=st)
    assert [p for p, _l in plays] == ["deploy-scr-backend.yml"] * 2, plays


# ---------------------------------------------------------------- B1: the judge after each box


def _fake_plays(monkeypatch, rt, after):
    plays, health = [], {}
    real = rt.health_json

    def zap(playbook, limit=None, extra=None, **kw):
        host = PRIMARY if limit == rt.PRIMARY_SELECTOR else STANDBY
        plays.append((playbook, limit))
        health[host] = after[host]
        return "ok failed=0"

    def hj(host):
        if host in health:
            if health[host] is None:
                raise OSError("silent")
            return {"review_eval": health[host], "review_rules": "absent"}
        return real(host)
    monkeypatch.setattr(rt, "zap", zap)
    monkeypatch.setattr(rt, "health_json", hj)
    monkeypatch.setattr(rt, "assert_control", lambda host: None)
    monkeypatch.setattr(rt, "assert_box_build", lambda host, expect, sha: None)
    return plays


@pytest.mark.parametrize("after", [X_W, None])
def test_the_standby_is_not_deployed_when_the_primary_publishes_another_word(monkeypatch, after):
    rt = _release_train()
    cell = dict(rec="valid", pre=False, code=True, P="O", Sb="O", key="valid", call="Jc")
    st = _cell_world(monkeypatch, rt, cell, [])
    st["snapshot"] = "label"
    plays = _fake_plays(monkeypatch, rt, {PRIMARY: after, STANDBY: N_W})
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt._deploy_both(CODE, expect="new", st=st)
    msg = str(exc.value)
    assert len(plays) == 1 and "the primary publishes %s" % (after or "nothing") in msg and N_W in msg, msg
    assert "no further box is deployed" in msg and "the rollback point recorded" in msg and BASE[:12] in msg, msg


def _parent_map(tree):
    parent = {}
    for n in ast.walk(tree):
        for c in ast.iter_child_nodes(n):
            parent[c] = n
    return parent


def _place(parent, node):
    p = parent.get(node)
    field = next((f for f, v in ast.iter_fields(p) if v is node or (isinstance(v, list) and any(x is node for x in v))),
                 None) if p is not None else None
    x = node
    while x in parent and not isinstance(parent[x], ast.Module):
        x = parent[x]
    owner = x.name if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else "<module>"
    return owner, p, "%s.%s" % (type(p).__name__, field)


PLAY_PLACES = {
    ("zap", "_deploy_both", "Call.func", "deploy-scr-backend.yml"),
    ("zap", "phase_snapshot", "Call.func", "snapshot-scr.yml"),
    ("zap_argv", "zap", "Call.func", None),
    ("zap_argv", "_reg_zap", "Call.func", None),
    ("deploy-scr-backend.yml", "_deploy_both", "Call.args", "zap"),
    ("deploy-scr-backend.yml", "_reg_zap", "Tuple.elts", None),
    ("deploy-scr-backend.yml", "<module>", "Dict.keys", None),
    ("deploy-bot", "phase_bot", "Call.args", "ssh_argv"),
    ("deploy-bot", "phase_bot", "Call.args", "blocking_child"),
}
MEMBERS = {"zap": 0, "ssh": 1, "zap_argv": 0, "ssh_argv": 1}  # the senders and builders, one closed set: member -> the position of the play or the box verb
LOCAL_RUNNERS = {"start_process": "the one runner: starts the argv it is handed", "run": "starts an argv built elsewhere", "job_spawn": "starts an argv built elsewhere", "contained_child": "starts the argv zap_argv built", "git_child": "starts a git argv", "blocking_child": "starts an argv a member built; its step is a label PLAY_PLACES holds", "git_out": "runs a git form of GIT_FORMS", "_git_line": "runs a git form of GIT_FORMS", "git_forms_preflight.<locals>.git": "runs a git form on the scratch repository", "sql": "reaches ssh by the PREFIXES row sql-readonly:", "sql_argv": "reaches ssh_argv by the PREFIXES row sql-readonly:", "migrate_child": "starts the line migrate_argv builds", "migrate_argv": "reaches ssh_argv by the PREFIXES row migrate:", "http_code": "a curl line to a box route; no play, no verb", "http_code_argv": "the same", "route_json": "the same", "route_json_argv": "the same"}
PREFIXES = {"sql-readonly:": ("the query", "the box's wrapper takes the whole verb in its case arm sql-readonly:*, so the tail stays inside it"), "migrate:": ("a migration file's name", "the same wrapper's case arm migrate:*"), "ps -eo pid,args; echo PS_RC=$? %s": ("the probe's own tag, rtps- and 12 hex (T:9065)", "a read-only ps line on the controller; the tail is an argument of echo")}


def _params(fn):
    a = fn.args
    return {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs + [v for v in (a.vararg, a.kwarg) if v]}


def _loop_names(t):
    if isinstance(t, ast.Name):
        return {t.id}
    if isinstance(t, (ast.Tuple, ast.List)):
        inner = [e.value if isinstance(e, ast.Starred) else e for e in t.elts]
        return {e.id for e in inner if isinstance(e, ast.Name)}
    return set()


def _loop_binder(parent, node, name):
    """The (target, iterable) of the comprehension or for statement that binds `name` where `node` stands, or None."""
    x = node
    while x in parent:
        p = parent[x]
        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return None
        for g in getattr(p, "generators", None) or ():
            if name in _loop_names(g.target):
                return g.target, g.iter
        if isinstance(p, (ast.For, ast.AsyncFor)) and any(x is s for s in p.body) and name in _loop_names(p.target):
            return p.target, p.iter
        x = p
    return None


def _str_constant(e):
    return isinstance(e, ast.Constant) and isinstance(e.value, str)


def _loop_kinds(target, it, name):
    """The loop rule (TEXTS C3.7): (kind, part) for each place where the loop does not fit; [] when it fits."""
    if not isinstance(it, (ast.Tuple, ast.List)):
        return [("the iterable is not a display written at that place", it)]
    if isinstance(target, ast.Name):
        return [("a starred element", e) if isinstance(e, ast.Starred) else
                ("position %d holding something that is not a string constant" % k, e)
                for k, e in enumerate(it.elts) if not _str_constant(e)]
    if any(isinstance(e, ast.Starred) for e in target.elts):
        return [("a starred name in the target", target)]
    i = next(k for k, e in enumerate(target.elts) if isinstance(e, ast.Name) and e.id == name)
    out = []
    for e in it.elts:
        if isinstance(e, ast.Starred) or (isinstance(e, (ast.Tuple, ast.List))
                                          and any(isinstance(x, ast.Starred) for x in e.elts)):
            out.append(("a starred element", e))
        elif not isinstance(e, (ast.Tuple, ast.List)) or len(e.elts) != len(target.elts):
            out.append(("an element whose length differs from the target's", e))
        elif not _str_constant(e.elts[i]):
            out.append(("position %d holding something that is not a string constant" % i, e.elts[i]))
    return out


def _play_census(tree, runners=None):
    parent, hits = _parent_map(tree), []
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in ("zap", "zap_argv"):
            what = n.id
        elif isinstance(n, ast.Attribute) and n.attr in ("zap", "zap_argv"):
            what = "an attribute " + n.attr
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and (
                "deploy-scr-backend" in n.value or n.value == "deploy-bot"):
            what = "deploy-scr-backend.yml" if "deploy-scr-backend" in n.value else "deploy-bot"
        else:
            continue
        owner, p, place = _place(parent, n)
        extra = None
        if place == "Call.func" and p.args and isinstance(p.args[0], ast.Constant):
            extra = p.args[0].value
        elif place == "Call.args" and isinstance(p.func, ast.Name):
            extra = p.func.id
        if (what, owner, place, extra) not in PLAY_PLACES:
            hits.append((what, owner, getattr(n, "lineno", 0), place, extra))
    tops = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in MEMBERS and not (
                isinstance(parent.get(n), ast.Call) and parent[n].func is n):
            hits.append(("a member named outside a call: " + n.id, _place(parent, n)[0], getattr(n, "lineno", 0)))
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in MEMBERS):
            continue
        member, owner, line = n.func.id, _place(parent, n)[0], getattr(n, "lineno", 0)
        part = n.args[MEMBERS[member]] if len(n.args) > MEMBERS[member] else None
        binder = _loop_binder(parent, n, part.id) if isinstance(part, ast.Name) else None
        if owner in MEMBERS and owner in tops:
            if not (isinstance(part, ast.Name) and part.id in _params(tops[owner])):
                hits.append(("inside %s the play or verb of %s is not its own parameter" % (owner, member), owner, line))
        elif _str_constant(part):
            pass
        elif isinstance(part, ast.BinOp) and isinstance(part.op, (ast.Add, ast.Mod)) and _str_constant(part.left):
            if part.left.value not in PREFIXES:
                hits.append(("the play or verb of %s joins %r, a prefix not on the table" % (member, part.left.value),
                             owner, line))
        elif binder is not None:
            for kind, bad in _loop_kinds(binder[0], binder[1], part.id):
                hits.append(("the play or verb of %s comes from a loop the rule does not take (%s): %s"
                             % (member, kind, ast.unparse(bad)), owner, line))
        else:
            hits.append(("the play or verb of %s given as %s"
                         % (member, type(part).__name__ if part is not None else "no argument at its position"),
                         owner, line))
    if runners is not None:
        starters = set(runners) | {v[2] for v in runners.values() if v[2]}
        for q in sorted(starters - set(MEMBERS) - set(LOCAL_RUNNERS)):
            hits.append(("a function that starts a process and stands in neither list: " + q, "<module>", 0))
    return hits


def test_every_deploy_play_is_followed_by_the_box_judge_before_the_next():
    rt = _release_train()
    tree = ast.parse(Path(rt.__file__).read_text(encoding="utf-8"))
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert _play_census(tree) == []
    loop = next(n for n in fns["_deploy_both"].body if isinstance(n, ast.For))
    assert ast.unparse(loop.body[-1]) == "closure_judge_box(st, role, host, sha, expect)", ast.unparse(loop.body[-1])
    first = [s for s in fns["_deploy_both"].body if not isinstance(s, ast.Expr) or not isinstance(s.value, ast.Constant)]
    assert ast.unparse(first[0]) == "closure_judge_deploy(st, sha, expect)"
    bot = [ast.unparse(s) for s in fns["phase_bot"].body]
    assert bot.index("closure_judge_bot(st)") < bot.index("st['bot_deployed'] = True"), bot


def test_the_bot_judge_refuses_a_primary_at_another_word(monkeypatch):
    rt = _release_train()
    st = _cell_world(monkeypatch, rt, dict(rec="valid", pre=False, code=True, P="O", Sb="N", key="valid",
                                           call="W"), [])
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt.closure_judge_bot(st)
    msg = str(exc.value)
    assert "(bot) the primary publishes %s" % O_W in msg and "the bot phase is not saved" in msg, msg
    assert "the rollback point NOT recorded" in msg and BASE[:12] in msg, msg


# ---------------------------------------------------------------- the command line: F, B2, C8, C9, C10


def _main_world(monkeypatch, rt, tmp_path, events, argv):
    def refused(what):
        def f(*a, **kw):
            events.append(what)
            raise rt.Fail("%s was reached" % what)
        return f
    for name in ("train_token_write", "controller_lease_session"):
        monkeypatch.setattr(rt, name, refused(name))
    monkeypatch.setattr(rt, "PHASES", [(p, refused("phase " + p)) for p, _fn in rt.PHASES])
    monkeypatch.setattr(rt, "BATCHES", {"zz-closure-guard": {}})
    monkeypatch.setattr(rt, "select_batch", lambda name: None)
    monkeypatch.setattr(rt, "assert_run_cmdlines_fit", lambda selected, st: None)
    monkeypatch.setattr(rt, "git_forms_preflight", lambda selected, st: events.append("preflight") or [])
    monkeypatch.setattr(rt, "NEW_ROUTES", [])
    monkeypatch.setattr(rt, "JSON_MARKERS", [])
    monkeypatch.setattr(rt, "CODE_MARKERS", ["review_eval"])
    if rt.ALL_SQL is None:
        monkeypatch.setattr(rt, "ALL_SQL", [])
    monkeypatch.setattr(rt.sys, "argv", ["release_train.py"] + argv + ["--batch", "zz-closure-guard"])


def test_the_command_line_refuses_when_the_boxes_word_is_not_the_bases_before_any_token(
        world, monkeypatch, tmp_path, capsys):
    rt, scratch, base_word = world
    _bind(monkeypatch, rt, scratch, scratch.base, Boxes(X_W), tmp_path, rows=_rows(base_word))
    events = []
    _main_world(monkeypatch, rt, tmp_path, events, ["run", "--go", "--only", "deploy-precursor"])
    monkeypatch.setattr(rt, "ALL_SQL", ["999_closure_test.sql"])
    assert rt.main() == 1
    out = capsys.readouterr().out
    assert events == ["preflight"] and "row 5" in out and "before a train token was written" in out, (events, out)


def test_a_main_behind_origin_is_refused_before_any_token(monkeypatch, tmp_path, capsys):
    rt = _release_train()
    events = []
    _main_world(monkeypatch, rt, tmp_path, events, ["run", "--go", "--only", "code"])
    monkeypatch.setattr(rt, "STATE_PATH", str(tmp_path / "none.json"))
    monkeypatch.setattr(rt, "_closure_main_sha", lambda: "1" * 40)
    monkeypatch.setattr(rt, "ls_remote_main", lambda: "2" * 40)
    monkeypatch.setattr(rt, "closure_guard", lambda *a, **kw: events.append("guard"))
    assert rt.main() == 1
    out = capsys.readouterr().out
    assert events == ["preflight"] and "is not origin's main" in out, (events, out)


def test_the_commits_judge_their_tree_from_the_base_read_then():
    rt = _release_train()
    fns = {n.name: n for n in ast.parse(Path(rt.__file__).read_text(encoding="utf-8")).body
           if isinstance(n, ast.FunctionDef)}
    pre = ast.unparse(fns["phase_precursor"])
    assert pre.index("base = _git_line(git_argv('rev-parse', 'refs/heads/main'))") < pre.index(
        "closure_judge_tree(st, expected_precursor_tree(base, tip, files), base, 'old'") < pre.index(
        "git_child(lease, c)"), "precursor"
    assert pre.index("closure_judge_tree(st, expected_precursor_tree(world['base'], tip, files)") < pre.index(
        "resume_precursor(world")
    code = ast.unparse(fns["phase_code"])
    j = code.index("closure_judge_tree(st, expected_merge_tree(world['base'], tip), world['base'], 'new'")
    assert code.index("world = read_code_world(tip)") < j < code.index("resume_code_merge(") and j < code.index(
        "controller_lease_session('phase 4 merge commit and push')")


def test_an_unreadable_state_file_is_refused_by_a_fixed_line(monkeypatch, tmp_path, capsys):
    rt = _release_train()
    events = []
    for verb in (["check"], ["plan"], ["run", "--go"]):
        _main_world(monkeypatch, rt, tmp_path, events, verb)
        bad = tmp_path / "secret-dir-name" / "state.json"
        bad.parent.mkdir(exist_ok=True)
        bad.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(rt, "STATE_PATH", str(bad))
        assert rt.main() == 1
        out = capsys.readouterr().out
        assert "state file cannot be read as a JSON object" in out and "secret-dir-name" not in out, out
    assert events == []


def test_only_the_first_pass_writes_the_record():
    rt = _release_train()
    tree = ast.parse(Path(rt.__file__).read_text(encoding="utf-8"))
    calls = [(fn.name, ast.unparse(n)) for fn in tree.body if isinstance(fn, ast.FunctionDef) for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "closure_guard"]
    writes = [c for c in calls if "write" in c[1]]
    assert writes == [("main", "closure_guard(st, 'start', write=True, reach=reach)")], calls
    assert sorted(calls) == [("assert_reviewed_tip", "closure_guard(st, stage)"),
                             ("main", "closure_guard(st, 'start', write=True, reach=reach)"),
                             ("phase_check", "closure_guard(st, 'check')"),
                             ("phase_code", "closure_guard(st, 'code')")], calls
    saves = [fn.name for fn in tree.body if isinstance(fn, ast.FunctionDef) and "closure" in fn.name
             for n in ast.walk(fn) if isinstance(n, ast.Call) and ast.unparse(n.func) == "save_state"]
    assert saves == ["_closure_guard"], saves


_GUARD_READS = {"git_out", "_git_line", "health_json", "load_state", "save_state", "expected_merge_tree",
                "ls_remote_main", "closure_routine", "_closure_state_files", "open"}
READ_CALLS = {"isinstance", "len", "set", "dict", "list", "tuple", "sorted", "any", "all", "str", "int", "bool",
              "range", "zip", "next", "min", "max", "sum", "print", "type", "repr", "ClosureRefusal", "reads_as",
              "_utc", "run_tags", "git_argv"}
READ_METHODS = {"get", "items", "keys", "values", "split", "partition", "startswith", "endswith", "decode", "encode",
                "join", "strip", "lstrip", "rstrip", "lower", "upper", "replace", "splitlines", "fullmatch", "match",
                "group", "find", "index", "append", "extend", "add", "setdefault", "hexdigest", "isdigit", "fromkeys",
                "count", "format"}
READ_ATTRS = {"contextlib.contextmanager": "makes the wrapper a context manager; reads, writes, starts nothing", "hashlib.sha256": "hashes bytes in memory; reads, writes, starts nothing", "os.path.join": "joins strings; reads, writes, starts nothing", "re.fullmatch": "matches a string; reads, writes, starts nothing", "sys.executable": "names the interpreter's path; reads, writes, starts nothing", "tempfile.gettempdir": "gettempdir: at its first call in a process it creates and removes one probe file in the temporary folder; it writes nothing in the working tree, the registry or a box"}


def _imported_names(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.asname or a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            out |= {a.asname or a.name for a in n.names}
    return out


def _root_name(node):
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _outside_read_attrs(node):
    return ast.unparse(node) not in READ_ATTRS


def _in_reading(parent, node):
    x = node
    while x in parent:
        p = parent[x]
        if isinstance(p, ast.With) and any(x is s for s in p.body) and any(
                isinstance(i.context_expr, ast.Call) and isinstance(i.context_expr.func, ast.Name)
                and i.context_expr.func.id == "_closure_reading" for i in p.items):
            return "the wrapper's body"
        if (isinstance(p, ast.Try) and any(x is s for s in p.body) and _place(parent, p)[0] == "closure_load_state"
                and [ast.unparse(h.type) for h in p.handlers] == ["Exception"]):
            return "closure_load_state's try"
        x = p
    return None


def _read_census(tree, imported=None):
    imported = _imported_names(tree) if imported is None else set(imported)
    parent, hits = _parent_map(tree), []
    fns = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    sites = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in fns:
            sites.setdefault(n.func.id, []).append(n)
    inner = set()
    while True:
        more = {f for f, calls in sites.items() if f not in inner and "closure" in f and all(
            _in_reading(parent, c) or _place(parent, c)[0] in inner for c in calls)}
        if not more:
            break
        inner |= more
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and "closure" in n.name]:
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and n.id in _GUARD_READS:
                p = parent.get(n)
                if not (isinstance(p, ast.Call) and p.func is n):
                    hits.append((fn.name, getattr(n, "lineno", 0), "a read named outside a call: " + n.id))
            if isinstance(n, ast.Attribute) and n.attr in _GUARD_READS:
                p = parent.get(n)
                if not (isinstance(p, ast.Call) and p.func is n):
                    hits.append((fn.name, getattr(n, "lineno", 0), "a read named outside a call: " + ast.unparse(n)))
            if isinstance(n, ast.Name) and n.id in imported and not (_in_reading(parent, n) or fn.name in inner):
                top = n
                while isinstance(parent.get(top), ast.Attribute) and parent[top].value is top:
                    top = parent[top]
                q = parent.get(top)
                if top is n:
                    hits.append((fn.name, getattr(n, "lineno", 0), "an imported name not under an attribute: " + n.id))
                elif not (isinstance(q, ast.Call) and q.func is top) and _outside_read_attrs(top):
                    hits.append((fn.name, getattr(n, "lineno", 0),
                                 "an attribute of an imported name outside READ_ATTRS: " + ast.unparse(top)))
            if not isinstance(n, ast.Call) or _in_reading(parent, n) or fn.name in inner:
                continue
            f = n.func
            if isinstance(f, ast.Name) and (f.id in READ_CALLS or ("closure" in f.id and f.id in fns)):
                continue
            if isinstance(f, ast.Attribute) and f.attr in READ_METHODS and _root_name(f) not in imported:
                continue
            if isinstance(f, ast.Attribute) and _root_name(f) in imported:
                if _outside_read_attrs(f):
                    hits.append((fn.name, getattr(n, "lineno", 0),
                                 "an attribute of an imported name outside READ_ATTRS: " + ast.unparse(f)))
                continue
            hits.append((fn.name, getattr(n, "lineno", 0), "a call outside the wrapper: " + ast.unparse(f)))
    return hits, sorted(inner)


def test_every_call_and_imported_name_in_a_closure_function_outside_the_wrapper_is_listed_or_a_closure_function():
    rt = _release_train()
    tree = ast.parse(Path(rt.__file__).read_text(encoding="utf-8"))
    hits, inner = _read_census(tree)
    assert hits == [] and inner == INNER_FUNCTIONS, (hits, inner)
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    loads = [n for n in ast.walk(main) if isinstance(n, ast.Call) and ast.unparse(n.func) in ("load_state",)]
    assert loads == [], loads


INNER_FUNCTIONS = ["_closure_bindings", "_closure_chain", "_closure_field", "_closure_import_shape", "_closure_module",
                   "_closure_state_files",
                   "_closure_uses", "closure_census", "closure_child_env", "closure_export", "closure_routine"]


def _hand_built(fn_name, node):
    tree = ast.Module(body=[ast.FunctionDef(name=fn_name, args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[],
                                                                             kw_defaults=[], defaults=[]),
                                            body=[ast.Expr(value=node)], decorator_list=[], returns=None,
                                            type_params=[])], type_ignores=[])
    return ast.fix_missing_locations(tree)


READ_PLANTS = {
    "builtin open outside the wrapper": "def closure_x(p):\n    return open(p).read()\n",
    "open reached as an attribute": "import builtins\ndef closure_x(p):\n    return builtins.open(p)\n",
    "an attribute read of a file outside the wrapper": "import os\ndef closure_x(p):\n    return os.stat(p)\n",
    "a read bound to another name": "def closure_x(p):\n    r = load_state\n    return r()\n",
    "a read handed to a call": "def closure_x(p):\n    return list(map(open, p))\n",
    "a second attribute of tempfile": "import tempfile\ndef closure_x(p):\n    return tempfile.mkdtemp()\n",
}


@pytest.mark.parametrize("form", sorted(READ_PLANTS))
def test_the_read_census_hits_each_planted_form(form):
    hits, _inner = _read_census(ast.parse(READ_PLANTS[form]))
    assert hits, form


def test_the_read_census_hits_a_guard_read_named_or_reached_as_an_attribute_under_await():
    hits, _inner = _read_census(_hand_built("closure_x", ast.Await(value=ast.Name(id="open", ctx=ast.Load()))))
    assert [h[2] for h in hits] == ["a read named outside a call: open"], hits
    plant = ast.Await(value=ast.Attribute(value=ast.Name(id="builtins", ctx=ast.Load()), attr="open", ctx=ast.Load()))
    hits, _inner = _read_census(_hand_built("closure_x", plant))
    assert [h[2] for h in hits] == ["a read named outside a call: builtins.open"], hits


_TOOL_FILE = REPO / "scripts" / "deploy" / "release_train.py"
_TOOL_IMPORTED = sorted(_imported_names(ast.parse(_TOOL_FILE.read_text(encoding="utf-8")))) if _TOOL_FILE.exists() else []
S3_FORMS = {"called": "def closure_x(p):\n    return {m}.replace(p)\n",
            "handed on": "def closure_x(p):\n    return {m}.replace\n",
            "bound to a local": "def closure_x(p):\n    r = {m}\n    return r\n"}
S3_PLANTS = [(m, f) for m in _TOOL_IMPORTED for f in S3_FORMS]


@pytest.mark.parametrize("name,form", S3_PLANTS)
def test_the_read_census_hits_each_imported_name_of_the_tool_outside_the_table(name, form):
    """For every name an import statement binds anywhere in the tool, read from its tree: name.replace (a READ_METHODS name, so only the root rule refuses it) called, the same attribute handed on as a value, and the bare name bound to a local, each in a closure function outside the wrapper: one hit each."""
    assert len(S3_PLANTS) == len(_TOOL_IMPORTED) * len(S3_FORMS)
    assert not [m for m in _TOOL_IMPORTED if m + ".replace" in READ_ATTRS]
    if (name, form) == S3_PLANTS[0]:
        print("COUNT S3: %d plants = %d names x %d forms" % (len(S3_PLANTS), len(_TOOL_IMPORTED), len(S3_FORMS)))
    hits, _inner = _read_census(ast.parse(S3_FORMS[form].replace("{m}", name)), imported=_TOOL_IMPORTED)
    want = ("an imported name not under an attribute: " + name if form == "bound to a local"
            else "an attribute of an imported name outside READ_ATTRS: %s.replace" % name)
    assert [h[2] for h in hits] == [want], hits


PLAY_PLANTS = {
    "a play named by a name": "def _deploy_both():\n    p = 'deploy-scr-backend.yml'\n    zap(p)\n",
    "the runner bound to another name": "def _deploy_both():\n    z = zap\n",
    "the runner reached as an attribute": "def _deploy_both():\n    rt.zap('deploy-scr-backend.yml')\n",
    "the deploy play from another function": "def phase_other():\n    zap('deploy-scr-backend.yml')\n",
    "the bot verb from another function": "def phase_other():\n    ssh_argv(P, 'deploy-bot')\n",
}


@pytest.mark.parametrize("form", sorted(PLAY_PLANTS))
def test_the_play_census_hits_each_planted_form(form):
    assert _play_census(ast.parse(PLAY_PLANTS[form])), form


def test_the_play_census_hits_a_runner_under_await():
    hits = _play_census(_hand_built("_deploy_both", ast.Await(value=ast.Name(id="zap", ctx=ast.Load()))))
    # the census fixes the order of the two hits: the places census walks the tree first, the member rule after it
    assert hits == [("zap", "_deploy_both", 1, "Await.value", None),
                    ("a member named outside a call: zap", "_deploy_both", 1)], hits


def _grammar(c):
    """The fields of an ast class as its own signature line names them, [(type, suffix, field)]: the first line of its
    docstring when that line begins with the class's own name and a parenthesis; None otherwise."""
    line = (c.__doc__ or "").split("\n")[0]
    if not line.startswith(c.__name__ + "("):
        return None
    out = []
    for part in [p.strip() for p in line[len(c.__name__) + 1:line.rindex(")")].split(",") if p.strip()]:
        typ, field = part.split()
        out.append((typ.rstrip("*?"), typ[-1] if typ[-1] in "*?" else "", field))
    return out


def _arguments(args=()):
    return ast.arguments(posonlyargs=[], args=list(args), vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None,
                         defaults=[])


def _fill(typ, suffix):
    if suffix == "?":
        return None
    if suffix == "*":
        return [ast.Pass()] if typ == "stmt" else [ast.Eq()] if typ == "cmpop" else []
    return {"identifier": lambda: "x", "int": lambda: 0, "constant": lambda: 0,
            "expr": lambda: ast.Name(id="x", ctx=ast.Load()), "expr_context": ast.Load, "boolop": ast.And,
            "operator": ast.Add, "unaryop": ast.Not, "pattern": ast.MatchAs, "arguments": _arguments}[typ]()


def _filled(c, field=None, value=None):
    return c(**{f: (([value] if s == "*" else value) if f == field else _fill(t, s)) for t, s, f in _grammar(c)})


S4_TYPES = sorted(c.__name__ for c in vars(ast).values() if isinstance(c, type) and c.__bases__ == (ast.expr,))
S4_PLANTS = [(m, k) for m in MEMBERS for k in S4_TYPES]


@pytest.mark.parametrize("member,kind", S4_PLANTS)
def test_the_play_census_hits_each_member_given_its_play_or_verb_as_anything_but_one_string(member, kind):
    """For every member of MEMBERS and every expression node type of ast (its direct subclasses of ast.expr, read at test time), a call of the member from def phase_other(x) with an instance of that type where its play or verb stands (x itself for Name, a bytes constant for Constant): the hit that names the member and the type is among the hits."""
    assert len(S4_PLANTS) == len(MEMBERS) * len(S4_TYPES)
    if (member, kind) == S4_PLANTS[0]:
        print("COUNT S4: %d plants = %d members x %d types" % (len(S4_PLANTS), len(MEMBERS), len(S4_TYPES)))
    c = getattr(ast, kind)
    part = (ast.Name(id="x", ctx=ast.Load()) if c is ast.Name else ast.Constant(value=b"x") if c is ast.Constant
            else _filled(c))
    call = ast.Call(func=ast.Name(id=member, ctx=ast.Load()),
                    args=[ast.Name(id="P", ctx=ast.Load()) for _k in range(MEMBERS[member])] + [part], keywords=[])
    fn = ast.FunctionDef(name="phase_other", args=_arguments([ast.arg(arg="x")]), body=[ast.Expr(value=call)],
                         decorator_list=[], returns=None, type_params=[])
    hits = _play_census(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])))
    assert "the play or verb of %s given as %s" % (member, kind) in [h[0] for h in hits], hits


Q2_PLANTS = ([(k, m) for k in ("a local in place of the parameter", "a member named outside a call") for m in MEMBERS]
             + [(k, r) for k in ("a prefix not on the table", "the row's own prefix") for r in PREFIXES])


def _q2_case(kind, which):
    """(source, the text the plant must hit, or None for the row's own prefix, which passes)."""
    if kind == "a local in place of the parameter":
        return ("def %s(p, q):\n    w = q\n    return ssh_argv(p, w)\n" % which,
                "inside %s the play or verb of ssh_argv is not its own parameter" % which)
    if kind == "a member named outside a call":
        return "def phase_other():\n    s = %s\n" % which, "a member named outside a call: " + which
    row = "z" + which if kind == "a prefix not on the table" else which
    src = "def phase_other(x):\n    ssh_argv(P, %r %s x)\n" % (row, "%" if "%s" in which else "+")
    return src, ("the play or verb of ssh_argv joins %r, a prefix not on the table" % row if row != which else None)


@pytest.mark.parametrize("kind,which", Q2_PLANTS)
def test_the_play_census_hits_a_local_a_prefix_off_the_table_and_a_member_named_outside_a_call(kind, which):
    """Generated per member and per row of PREFIXES: inside the member's body a local in place of its parameter is a hit; a member named outside a call is a hit; a row's constant with one letter added is a hit; the row's own constant joined to its tail passes."""
    assert len(Q2_PLANTS) == 2 * len(MEMBERS) + 2 * len(PREFIXES)
    if (kind, which) == Q2_PLANTS[0]:
        print("COUNT Q2: %d plants = 2 x %d members + 2 x %d rows" % (len(Q2_PLANTS), len(MEMBERS), len(PREFIXES)))
    src, want = _q2_case(kind, which)
    hits = _play_census(ast.parse(src))
    if want is None:
        assert hits == [], (src, hits)
    else:
        assert want in [h[0] for h in hits], (src, hits)


C38_LOOPS = sorted(c.__name__ for c in vars(ast).values() if isinstance(c, type) and issubclass(c, ast.AST)
                   and "generators" in c._fields) + ["For", "AsyncFor"]
C38_KINDS = {"a single name": ("the shape", "the iterable is not a display written at that place", "a starred element",
                               "position"),
             "a tuple of names": ("the shape", "the iterable is not a display written at that place", "a starred element",
                                  "a starred name in the target", "an element whose length differs from the target's",
                                  "position")}
C38_CASES = [(m, loop, d, t, p) for m in MEMBERS for loop in C38_LOOPS for d in ("Tuple", "List")
             for t, kinds in C38_KINDS.items() for p in kinds]


def _c38_source(member, loop, display, target, plant):
    if target == "a single name":
        elts, tgt = ['"a.yml"', '"c.yml"'], "p"
        if plant == "a starred element":
            elts.append("*zz_d")
        if plant == "position":
            elts[0] = "zz_x"
    else:
        elts, tgt = ['("a.yml", zz_b)', '("c.yml", zz_d)'], "*p, q" if plant == "a starred name in the target" else "p, q"
        elts[0] = {"a starred element": '("a.yml", *zz_b)', "an element whose length differs from the target's":
                   '("a.yml",)', "position": "(zz_x, zz_b)"}.get(plant, elts[0])
    it = "zz_d" if plant.startswith("the iterable") else ("(%s)" if display == "Tuple" else "[%s]") % ", ".join(elts)
    call = "%s(%s)" % (member, ", ".join(["P"] * MEMBERS[member] + ["p"]))
    if loop in ("For", "AsyncFor"):
        return "%s phase_other():\n    %s %s in %s:\n        %s\n" % (
            "async def" if loop == "AsyncFor" else "def", "async for" if loop == "AsyncFor" else "for", tgt, it, call)
    comp = {"ListComp": "[%s for %s in %s]", "SetComp": "{%s for %s in %s}", "GeneratorExp": "(%s for %s in %s)",
            "DictComp": "{p: %s for %s in %s}"}[loop]
    return "def phase_other():\n    return %s\n" % (comp % (call, tgt, it))


@pytest.mark.parametrize("member,loop,display,target,plant", C38_CASES)
def test_the_play_census_judges_a_name_a_loop_binds_only_at_its_position_in_the_display(member, loop, display, target, plant):
    """Generated per member, per loop (each node type of ast with a generators field, read at test time, and the for statements For and AsyncFor), per display (tuple, list) and per target (a single name; a tuple of names): the bound name over a display whose elements, or whose elements' position i, are string constants, handed where the member's play or verb stands, passes, a name standing at another position; one plant per kind of hit the rule lists is the hit that names its kind. Passes means that the loop rule and the play-or-verb rule add no hit: for ssh and ssh_argv the list of hits is empty; for zap and zap_argv it is the one hit of the places census, because the generated function owns no row of PLAY_PLACES."""
    assert len(C38_CASES) == len(MEMBERS) * len(C38_LOOPS) * 2 * sum(len(k) for k in C38_KINDS.values())
    if (member, loop, display, target, plant) == C38_CASES[0]:
        print("COUNT C3.8: %d cases = %d members x %d loops x 2 displays x (%d + %d)" % (
            len(C38_CASES), len(MEMBERS), len(C38_LOOPS), len(C38_KINDS["a single name"]),
            len(C38_KINDS["a tuple of names"])))
    src = _c38_source(member, loop, display, target, plant)
    hits = _play_census(ast.parse(src))
    if plant == "the shape":
        line = next(k for k, text in enumerate(src.splitlines(), 1) if member + "(" in text)
        assert hits == ([] if member in ("ssh", "ssh_argv") else [(member, "phase_other", line, "Call.func", None)]), (
            src, hits)
    else:
        kind = "position 0 holding something that is not a string constant" if plant == "position" else plant
        want = "the play or verb of %s comes from a loop the rule does not take (%s): " % (member, kind)
        assert [h[0] for h in hits if h[0].startswith(want)], (src, hits)


def test_every_function_that_starts_a_process_is_a_member_or_a_listed_local_runner():
    """The functions the tool names in RUNNERS and their builders are each in MEMBERS or in LOCAL_RUNNERS, the two lists hold no other name, and a starter added to RUNNERS is the hit that names it."""
    rt = _release_train()
    starters = set(rt.RUNNERS) | {v[2] for v in rt.RUNNERS.values() if v[2]}
    assert starters == set(MEMBERS) | set(LOCAL_RUNNERS) and len(starters) == len(MEMBERS) + len(LOCAL_RUNNERS), (
        sorted(starters ^ (set(MEMBERS) | set(LOCAL_RUNNERS))))
    assert _play_census(ast.parse(""), rt.RUNNERS) == []
    planted = dict(rt.RUNNERS, zz_runner=((0,), (), None, False))
    assert [h[0] for h in _play_census(ast.parse(""), planted)] == [
        "a function that starts a process and stands in neither list: zz_runner"]


def test_check_and_plan_reach_the_guard_before_any_token_and_without_the_preflight(monkeypatch, tmp_path, capsys):
    rt = _release_train()
    real_preflight, phases_real = rt.git_forms_preflight, list(rt.PHASES)
    bad = []
    for argv in (["check"], ["plan"], ["plan", "--only", "code"], ["plan", "--only", "precursor"], ["run"]):
        events = []
        _main_world(monkeypatch, rt, tmp_path, events, argv)
        monkeypatch.setattr(rt, "PHASES", phases_real)
        monkeypatch.setattr(rt, "ALL_SQL", ["999_closure_test.sql"] if "precursor" in argv else [])
        monkeypatch.setattr(rt, "STATE_PATH", str(tmp_path / "none.json"))
        monkeypatch.setattr(rt, "git_forms_preflight", lambda *a, **kw: events.append("preflight") or real_preflight(
            *a, **kw))
        monkeypatch.setattr(rt, "REVIEWED_TIP", "a" * 40)
        monkeypatch.setattr(rt, "measure_every_batch", lambda: ([], []))
        monkeypatch.setattr(rt, "run", lambda cmd, *a, **kw: "a" * 40)
        monkeypatch.setattr(rt, "PRIMARY", PRIMARY)
        monkeypatch.setattr(rt, "STANDBY", STANDBY)
        monkeypatch.setattr(rt, "mod_version_argv", lambda host: ["mod-version", host])
        for name in ("EXPECT_TABLES", "EXPECT_COLUMNS", "EXPECT_INDEXES", "SCHEMA_SQL", "I18N_SQL", "BACKFILL_SQL"):
            monkeypatch.setattr(rt, name, [])
        monkeypatch.setattr(rt, "start_process", lambda *a, **kw: subprocess.CompletedProcess([], 0, b"", b""))
        monkeypatch.setattr(rt, "precursor_files", lambda: ["999_closure_test.sql"])
        monkeypatch.setattr(rt, "code_state", lambda host: (True, False, True, []))
        monkeypatch.setattr(rt, "health_json", lambda host: {})
        monkeypatch.setattr(rt, "schema_state", lambda host: ([], []))
        monkeypatch.setattr(rt, "index_state", lambda host: [])
        monkeypatch.setattr(rt, "require_rollback_point", lambda args, st, phase: None)

        def guard(st, stage, **kw):
            events.append("guard " + stage)
            raise rt.ClosureRefusal("closure guard: stopped at the guard's call by the test")
        monkeypatch.setattr(rt, "closure_guard", guard)
        rt.main()
        capsys.readouterr()
        if not any(e.startswith("guard") for e in events) or "preflight" in events or any(
                e.startswith("train_token") or e.startswith("controller") for e in events):
            bad.append((argv, events))
    assert bad == [], bad


@pytest.mark.parametrize("sql", [[], ["999_closure_test.sql"]])
def test_in_a_run_with_go_the_guard_runs_only_after_the_preflight(monkeypatch, tmp_path, capsys, sql):
    rt = _release_train()
    names = [p for p, _fn in rt.PHASES]
    argvs = [["run", "--go"] + sel for sel in [[]] + [["--from", p] for p in names] + [["--only", p] for p in names]]
    bad, reached = [], []
    for argv in argvs:
        events = []
        _main_world(monkeypatch, rt, tmp_path, events, argv)
        monkeypatch.setattr(rt, "ALL_SQL", list(sql))
        monkeypatch.setattr(rt, "STATE_PATH", str(tmp_path / "none.json"))
        monkeypatch.setattr(rt, "closure_main_is_origin", lambda: events.append("origin"))
        monkeypatch.setattr(rt, "closure_guard", lambda *a, **kw: events.append("guard"))
        rt.main()
        capsys.readouterr()
        if "guard" in events:
            reached.append(argv[2:])
        if any(e in events for e in ("guard", "origin")) and (
                "preflight" not in events or events.index("preflight") > min(
                    events.index(e) for e in ("guard", "origin") if e in events)):
            bad.append((argv, events))
    assert bad == [] and ["--only", "code"] in reached and ["--only", "precursor" if sql else "code"] in reached, (
        bad, reached)


def test_a_refused_check_returns_one_with_the_fixed_line(monkeypatch, tmp_path, capsys):
    rt = _release_train()
    events = []
    _main_world(monkeypatch, rt, tmp_path, events, ["check"])
    monkeypatch.setattr(rt, "STATE_PATH", str(tmp_path / "none.json"))
    monkeypatch.setattr(rt, "measure_every_batch", lambda: ([], []))

    def phase_check(args, st):
        raise rt.ClosureRefusal("closure guard: row 5: planted")
    monkeypatch.setattr(rt, "phase_check", phase_check)
    assert rt.main() == 1
    assert "!!! check refused: closure guard: row 5: planted" in capsys.readouterr().out


# ---------------------------------------------------------------- the fixed lines each by its holder


RULES_REV = "0123456789ab"


@pytest.mark.parametrize("rules_next,want", [(False, "do not answer for the word"),
                                             (True, "the proof that rules_next is staged is not built")])
def test_row_1_with_review_rules_installed_names_the_staging_proof_or_the_generic_line(monkeypatch, rules_next,
                                                                                       want):
    rt = _release_train()
    cell = dict(rec="absent", pre=False, code=False, P="O", Sb="O", key="valid", call="F")
    saved = []
    st = _cell_world(monkeypatch, rt, cell, saved)
    change = {"eval_to": N_W, "rules_next": RULES_REV} if rules_next else {"eval_to": N_W}
    monkeypatch.setattr(rt, "CLOSURE_CHANGE", change)
    monkeypatch.setattr(rt, "HEALTH_EXPECT", _rows(N_W, RULES_REV))
    monkeypatch.setattr(rt, "health_json", lambda host: {"review_eval": O_W, "review_rules": "fedcba987654"})
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt.closure_guard(st, "start", write=True, reach=())
    assert "row 1:" in str(exc.value) and want in str(exc.value) and saved == [], str(exc.value)


@pytest.mark.parametrize("change", [[], {}, {"x": 1}, {"eval_to": "ABCDEF12"}, {"eval_to": "abc"},
                                    {"rules_next": "zz"}, {"build": []}, {"build": {"p": "short"}}])
def test_a_closure_change_out_of_form_is_refused(change):
    rt = _release_train()
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt.closure_change_form("zz-closure-guard", change)
    assert "the closure_change of batch zz-closure-guard is out of form" in str(exc.value)
    for good in ({"eval_to": "a" * 8}, {"rules_next": "0" * 12}, {"build": {"p": "0" * 64}}):
        assert rt.closure_change_form("zz-closure-guard", good) == good


def test_a_read_that_raises_is_refused_by_the_fixed_line(monkeypatch):
    rt = _release_train()

    def git_out(*a, **kw):
        raise OSError("planted")
    monkeypatch.setattr(rt, "git_out", git_out)
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt._closure_ancestor("a" * 40, "b" * 40)
    assert "asking git whether the base is an ancestor did not succeed; refused" in str(exc.value)


def _state_files(monkeypatch, rt, scratch, files):
    batches = {}
    for name, body in files.items():
        p = scratch.root / "states" / (name + ".json")
        p.parent.mkdir(exist_ok=True)
        p.write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")
        batches[name] = {"state_path": tuple(p.parts)}
    monkeypatch.setattr(rt, "BATCHES", batches)


def test_the_base_is_the_code_sha_of_the_newest_verified_state_file_printed_whole(world, monkeypatch, capsys):
    rt, scratch, base_word = world
    later = scratch.commit({"main.py": b"# later\n"})
    _state_files(monkeypatch, rt, scratch, {"a-old": {"verified": True, "code_sha": scratch.base},
                                            "b-new": {"verified": True, "code_sha": later},
                                            "c-open": {"code_sha": "c" * 40}, "d-bad": "{not json"})
    got = rt.closure_base({})
    assert (got["base"], got["from"]) == (later, "state")
    out = capsys.readouterr().out
    assert ("BASE %s is the code_sha of the newest verified state file (batch b-new; 1 unreadable); a run needs "
            "--boxes-head" % later) in out


def test_two_verified_state_files_on_diverging_lines_are_refused(world, monkeypatch):
    rt, scratch, base_word = world
    lane = scratch.commit({"main.py": b"# lane\n"})
    scratch.git("checkout", "-q", "main")
    other = scratch.commit({"main.py": b"# main\n"}, "main moved")
    scratch.git("checkout", "-q", "lane")
    _state_files(monkeypatch, rt, scratch, {"a": {"verified": True, "code_sha": lane},
                                            "b": {"verified": True, "code_sha": other}})
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt.closure_base({})
    assert "neither of which is an ancestor" in str(exc.value)


def test_without_a_verified_state_file_the_base_is_origins_main_declared(world, monkeypatch, capsys):
    rt, scratch, base_word = world
    _state_files(monkeypatch, rt, scratch, {"c-open": {"code_sha": "c" * 40}})
    monkeypatch.setattr(rt, "_git_line", lambda argv: "%s\trefs/heads/main" % scratch.base)
    got = rt.closure_base({})
    assert (got["base"], got["from"]) == (scratch.base, "origin")
    out = capsys.readouterr().out
    assert ("BASE %s is origin's main, a declared inference: no verified state file of this tool can be read "
            "(0 unreadable); a run needs --boxes-head" % scratch.base) in out


GIT_FORM_REFUSALS = {("closure-is-ancestor", "_closure_ancestor"): ("is not an ancestor of the reviewed tip", "asking git whether the base is an ancestor did not succeed; refused"), ("closure-ls-remote-main", "_closure_origin_main"): ("reading origin's main did not succeed; refused",) * 2, ("closure-cat-file-commit", "_closure_is_commit"): ("is not a commit of this repository; fetch origin, then run again; refused", "asking git whether --boxes-head names a commit did not succeed; refused"), ("closure-first-parent", "_closure_first_parent"): ("origin's main %s is not a commit of this repository", "listing the first-parent line of origin's main did not succeed; refused"), ("ls-tree-api", "closure_export"): ("did not run to its lines, so its word is unknown; refused",) * 2, ("cat-file-batch", "closure_export"): ("did not run to its lines, so its word is unknown; refused",) * 2, ("cat-file-batch", "_closure_blobs"): ("reading the build files did not succeed; refused",) * 2, ("rev-parse", "_closure_main_sha"): ("reading main did not succeed; refused",) * 2, ("merge-tree", "expected_merge_tree"): ("computing the merge of main and the reviewed tip did not succeed; refused",) * 2}
GIT_FORM_EMPTY = {("closure-ls-remote-main", "_closure_origin_main"): "reading origin's main did not succeed; refused", ("closure-first-parent", "_closure_first_parent"): "does not stand on the first-parent line of origin's main", ("ls-tree-api", "closure_export"): "did not run to its lines, so its word is unknown; refused", ("cat-file-batch", "closure_export"): "did not run to its lines, so its word is unknown; refused", ("cat-file-batch", "_closure_blobs"): "reading the build files did not succeed; refused", ("rev-parse", "_closure_main_sha"): "computing the merge of main and the reviewed tip did not succeed; refused",("merge-tree", "expected_merge_tree"): "computing the merge of main and the reviewed tip did not succeed; refused"}  # the two forms that read only the return code have no row
_PLAN_ONLY = {("rev-parse", "_closure_main_sha"), ("merge-tree", "expected_merge_tree")}  # only the code stage's block runs them (T:11750-11755); check does not reach it
GIT_FORM_CASES = [(site, case, verb) for verb in ("check", "plan") for site in GIT_FORM_REFUSALS
                  if verb == "plan" or site not in _PLAN_ONLY for case in ((1, 2, 3) if site in GIT_FORM_EMPTY else (1, 2))]


class _Site(list):
    site = None


def _git_forms_run(verb, plant=None):
    """One check, or one plan --only code, driven through main against a scratch repository whose origin is itself,
    with --boxes-head its base and a tip that changes main.py only. Every git form runs for real; a git_argv the guard
    calls records its site (the form and the calling function); `plant` = (site, case) makes that site's calls end with
    return code 1 and the passing run's own output (case 1), raise (case 2) or answer nothing with return code 0 (3)."""
    rt = _release_train()
    if os.name != "nt":
        pytest.skip("the closure routine's child runs in a Windows job object")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top, pytest.MonkeyPatch.context() as mp:
        top = Path(top)
        scratch = Scratch(top / "scratch")
        mp.setattr(rt, "REPO", str(scratch.repo))
        base_word = _word(rt, scratch.base)
        scratch.git("remote", "add", "origin", str(scratch.repo))
        tip = scratch.commit({"main.py": b"# lane\n"})
        events, sites, saves, depth = [], [], [], [0]
        phases_real = list(rt.PHASES)
        argv = ["check"] if verb == "check" else ["plan", "--only", "code"]
        _main_world(mp, rt, top, events, argv + ["--boxes-head", scratch.base])
        mp.setattr(rt, "PHASES", phases_real)
        for name, value in (("ALL_SQL", []), ("PRIMARY", PRIMARY), ("STANDBY", STANDBY), ("BRANCH", "lane"),
                            ("REVIEWED_TIP", tip), ("CLOSURE_CHANGE", None), ("HEALTH_EXPECT", []),
                            ("STATE_PATH", str(top / "state" / "train-state.json"))):
            mp.setattr(rt, name, value)
        mp.setattr(rt, "health_json", Boxes(base_word).health_json)
        mp.setattr(rt, "measure_every_batch", lambda: ([], []))
        mp.setattr(rt, "run", lambda cmd, *a, **kw: tip)
        mp.setattr(rt, "mod_version_argv", lambda host: ["mod-version", host])
        for name in ("EXPECT_TABLES", "EXPECT_COLUMNS", "EXPECT_INDEXES", "SCHEMA_SQL", "I18N_SQL", "BACKFILL_SQL"):
            mp.setattr(rt, name, [])
        mp.setattr(rt, "precursor_files", lambda: [])
        mp.setattr(rt, "code_state", lambda host: (True, False, True, []))
        mp.setattr(rt, "schema_state", lambda host: ([], []))
        mp.setattr(rt, "index_state", lambda host: [])
        mp.setattr(rt, "require_rollback_point", lambda args, st, phase: None)
        real_argv, real_start, real_guard, real_save = rt.git_argv, rt.start_process, rt.closure_guard, rt.save_state

        def git_argv(form, *args):
            built = _Site(real_argv(form, *args))
            built.site = (form, sys._getframe(1).f_code.co_name)
            if depth[0]:
                sites.append(built.site)
            return built

        def start_process(how, cmd, **kw):
            if plant is None or getattr(cmd, "site", None) != plant[0]:
                return real_start(how, cmd, **kw)
            if plant[1] == 2:
                raise OSError("planted")
            if plant[1] == 3:
                return subprocess.CompletedProcess(list(cmd), 0, b"", b"")
            p = real_start(how, list(cmd), **kw)
            return subprocess.CompletedProcess(p.args, 1, p.stdout, p.stderr)

        def guard(st, stage, *a, **kw):
            depth[0] += 1
            try:
                real_guard(st, stage, *a, **kw)
            finally:
                depth[0] -= 1
            print("guard passed")
            raise rt.Fail("stopped after the guard by the test")

        def save_state(st):
            saves.append(dict(st))
            real_save(st)
        for name, fn in (("git_argv", git_argv), ("start_process", start_process), ("closure_guard", guard),
                         ("save_state", save_state)):
            mp.setattr(rt, name, fn)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = rt.main()
        return {"rc": rc, "out": out.getvalue(), "sites": sites, "events": events, "saves": saves,
                "state": os.path.exists(rt.STATE_PATH), "tags": rt.run_tags(["code"], {}), "origin": scratch.base}


def test_the_git_forms_the_guard_runs_are_the_tables_rows_for_check_and_plan():
    """The sites where a function the guard reaches calls git_argv, found in the tool's tree (a form that is not one string constant fails), equal the sites a passing check and a passing plan run record; each site's form carries the run's tags in each verb that records it; each row tagged deploy-precursor is recorded in check and in plan; each row tagged check is such a form or one phase_check's own body names."""
    rt = _release_train()
    tree = ast.parse(Path(rt.__file__).read_text(encoding="utf-8"))
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    reach, todo = set(), ["closure_guard"]
    while todo:
        f = todo.pop()
        if f not in reach:
            reach.add(f)
            todo += [n.func.id for n in ast.walk(fns[f]) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                     and n.func.id in fns]
    static = set()
    for f in reach:
        for n in ast.walk(fns[f]):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "git_argv":
                assert n.args and _str_constant(n.args[0]), (f, ast.unparse(n))
                static.add((n.args[0].value, f))
    runs = {verb: _git_forms_run(verb) for verb in ("check", "plan")}
    recorded = {verb: set(r["sites"]) for verb, r in runs.items()}
    assert all("guard passed" in r["out"] for r in runs.values()), [r["out"][-800:] for r in runs.values()]
    print("COUNT G.1: %d static sites; %d recorded in check, %d in plan" % (len(static), len(recorded["check"]),
                                                                           len(recorded["plan"])))
    assert static == recorded["check"] | recorded["plan"] == recorded["plan"], (static, recorded)
    assert recorded["check"] == static - _PLAN_ONLY, recorded["check"]
    tags = {"check": {"check"}, "plan": runs["plan"]["tags"]}
    assert not [(v, s) for v, ss in recorded.items() for s in ss if not set(rt.GIT_FORMS[s[0]][0]) & tags[v]], tags
    pre = {form for form, v in rt.GIT_FORMS.items() if "deploy-precursor" in v[0]}
    assert all(pre <= {s[0] for s in recorded[v]} for v in recorded), (pre, recorded)
    named = {n.args[0].value for n in ast.walk(fns["phase_check"]) if isinstance(n, ast.Call)
             and ast.unparse(n.func) == "git_argv" and n.args and _str_constant(n.args[0])}
    rows = {form for form, v in rt.GIT_FORMS.items() if "check" in v[0]}
    assert rows <= {s[0] for s in recorded["check"]} | named, rows - ({s[0] for s in recorded["check"]} | named)


@pytest.mark.parametrize("site,case,verb", GIT_FORM_CASES,
                         ids=["%s-%s-%d-%s" % (s[0], s[1], c, v) for s, c, v in GIT_FORM_CASES])
def test_each_git_form_the_guard_runs_in_check_and_plan_ends_in_its_refusal_when_it_fails_raises_or_answers_nothing(site, case, verb):
    """For each form, at one site: (1) its call ends with a return code that is not 0 while its output is the passing run's; (2) its call raises; (3) its call ends with return code 0 and answers nothing; every other form answers through the real functions. In check and in plan where the form runs: the guard's refusal with its text, no pass, no token, nothing written. The ancestor check and the commit-type check read only the return code and take cases 1 and 2, since such a form has no answer to be empty: return code 0 IS its passing answer."""
    by_verb = {v: [c for c in GIT_FORM_CASES if c[2] == v] for v in ("check", "plan")}
    assert len(GIT_FORM_CASES) == len(by_verb["check"]) + len(by_verb["plan"]) == sum(
        3 if s in GIT_FORM_EMPTY else 2 for v in by_verb for s in GIT_FORM_REFUSALS if v == "plan" or s not in _PLAN_ONLY)
    if (site, case, verb) == GIT_FORM_CASES[0]:
        print("COUNT G.2: %d cases: check %d, plan %d" % (len(GIT_FORM_CASES), len(by_verb["check"]),
                                                         len(by_verb["plan"])))
    r = _git_forms_run(verb, (site, case))
    want = GIT_FORM_EMPTY[site] if case == 3 else GIT_FORM_REFUSALS[site][case - 1]
    want = want % r["origin"][:12] if "%s" in want else want
    assert r["rc"] == 1 and "closure guard: " in r["out"] and want in r["out"], r["out"][-1500:]
    assert "guard passed" not in r["out"], r["out"][-1500:]
    assert not [e for e in r["events"] if e.startswith(("train_token", "controller"))], r["events"]
    assert r["saves"] == [] and not r["state"], (r["saves"], r["state"])


@pytest.mark.parametrize("what,want", [("tip", "no reviewed_tip is pinned as a full commit id"),
                                       ("sha", "a recorded sha is not a full commit id")])
def test_a_reviewed_tip_or_a_recorded_sha_not_a_full_commit_id_is_refused(monkeypatch, what, want):
    rt = _release_train()
    cell = dict(rec="absent", pre=False, code=False, P="O", Sb="O", key="valid", call="W")
    st = _cell_world(monkeypatch, rt, cell, [])
    if what == "tip":
        monkeypatch.setattr(rt, "REVIEWED_TIP", "a" * 12)
    else:
        st["precursor_sha"] = "1" * 12
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt.closure_guard(st, "check")
    assert want in str(exc.value), str(exc.value)


@pytest.mark.parametrize("call", ["guard", "tree", "deploy"])
def test_a_call_that_cannot_decide_is_refused_by_its_fixed_line(monkeypatch, call):
    rt = _release_train()
    monkeypatch.setattr(rt, "REVIEWED_TIP", TIP)
    with pytest.raises(rt.ClosureRefusal) as exc:
        if call == "guard":
            rt.closure_guard(None, "check")
        elif call == "tree":
            rt.closure_judge_tree(None, TIP, TIP, "old", "the precursor tree")
        else:
            rt.closure_judge_deploy(None, PRE, "old")
    assert "could not decide" in str(exc.value), str(exc.value)


def test_a_stage_the_guard_does_not_know_is_refused(monkeypatch):
    rt = _release_train()
    cell = dict(rec="absent", pre=False, code=False, P="O", Sb="O", key="valid", call="W")
    st = _cell_world(monkeypatch, rt, cell, [])
    rt.closure_guard(st, "check")
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt.closure_guard(st, "planted")
    assert "a stage it does not know" in str(exc.value)


MAIN, MERGE = "3" * 40, "4" * 40


@pytest.mark.parametrize("reach,want", [("precursor", "that the precursor must carry"),
                                        ("code", "the merge of main and the reviewed tip does not carry")])
def test_the_first_pass_refuses_a_main_or_a_merge_without_its_word(monkeypatch, reach, want):
    rt = _release_train()
    cell = dict(rec="absent", pre=False, code=False, P="O", Sb="O", key="valid", call="F")
    saved = []
    st = _cell_world(monkeypatch, rt, cell, saved)
    words = {TIP: N_W, BASE: O_W, MAIN: X_W if reach == "precursor" else O_W, MERGE: X_W}
    monkeypatch.setattr(rt, "closure_prediction", lambda rev, anc, base, what, source="boxes-head": words[rev])
    monkeypatch.setattr(rt, "ALL_SQL", ["999_closure_test.sql"])
    monkeypatch.setattr(rt, "_closure_main_sha", lambda: MAIN)
    monkeypatch.setattr(rt, "expected_merge_tree", lambda main, tip: MERGE)
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt.closure_guard(st, "start", write=True, reach=(reach,))
    assert want in str(exc.value) and saved == [], str(exc.value)


def test_the_commit_judge_refuses_a_tree_without_its_word_and_takes_the_source_record(monkeypatch):
    rt = _release_train()
    cell = dict(rec="valid", pre=False, code=False, P="O", Sb="O", key="valid", call="W")
    st = _cell_world(monkeypatch, rt, cell, [])
    seen = []
    monkeypatch.setattr(rt, "closure_prediction", lambda rev, anc, base, what, source="boxes-head": seen.append(
        source) or X_W)
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt.closure_judge_tree(st, MERGE, MAIN, "old", "the precursor tree")
    assert "the precursor tree does not carry the word %s; nothing is committed" % O_W in str(exc.value)
    assert seen == ["record"], seen


def test_a_commit_to_deploy_without_the_approved_word_is_not_deployed(monkeypatch):
    rt = _release_train()
    cell = dict(rec="valid", pre=False, code=True, P="O", Sb="O", key="valid", call="Jc")
    st = _cell_world(monkeypatch, rt, cell, [])
    words = {TIP: N_W, BASE: O_W, CODE: X_W}
    monkeypatch.setattr(rt, "closure_prediction", lambda rev, anc, base, what, source="boxes-head": words[rev])
    plays = _fake_plays(monkeypatch, rt, {PRIMARY: N_W, STANDBY: N_W})
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt._deploy_both(CODE, expect="new", st=st)
    assert plays == [] and "(deploy) the commit %s does not carry the word %s" % (CODE[:12], N_W) in str(exc.value)


@pytest.mark.parametrize("judge", ["box", "bot"])
def test_a_judge_without_a_closure_record_refuses_by_its_fixed_line(judge):
    rt = _release_train()
    with pytest.raises(rt.ClosureRefusal) as exc:
        if judge == "box":
            rt.closure_judge_box({}, "primary", PRIMARY, CODE, "new")
        else:
            rt.closure_judge_bot({})
    assert "(%s) no closure record" % judge in str(exc.value)


# ---------------------------------------------------------------- the base is the operator's word (41-Q1 point 2)


@pytest.fixture
def line(tmp_path, monkeypatch):
    rt = _release_train()
    scratch = Scratch(tmp_path / "scratch")
    monkeypatch.setattr(rt, "REPO", str(scratch.repo))
    scratch.git("checkout", "-q", "main")
    m1 = scratch.commit({"main.py": b"# m1\n"}, "m1")
    scratch.git("checkout", "-q", "-b", "side")
    side = scratch.commit({"side.py": b"# side\n"}, "side")
    scratch.git("checkout", "-q", "main")
    scratch.git("merge", "-q", "--no-ff", "-m", "merge side", "side")
    m2 = scratch.git("rev-parse", "HEAD")
    scratch.git("checkout", "-q", "lane")
    lane = scratch.commit({"lane.py": b"# lane\n"})
    monkeypatch.setattr(rt, "_closure_origin_main", lambda: m2)
    _state_files(monkeypatch, rt, scratch, {})
    return rt, scratch, {"base": scratch.base, "m1": m1, "side": side, "m2": m2, "lane": lane}


def test_a_run_with_go_and_without_the_word_is_refused_naming_the_way(line, monkeypatch):
    rt, scratch, c = line
    monkeypatch.setattr(rt, "CLOSURE_GO", True)
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt.closure_base({})
    assert "a run with --go needs --boxes-head, the full sha read as HEAD on both boxes; read it" in str(exc.value)


def test_the_command_line_refuses_a_run_without_the_word_before_any_token(monkeypatch, tmp_path, capsys):
    rt = _release_train()
    events = []
    _main_world(monkeypatch, rt, tmp_path, events, ["run", "--go", "--only", "deploy-precursor"])
    monkeypatch.setattr(rt, "STATE_PATH", str(tmp_path / "none.json"))
    monkeypatch.setattr(rt, "REVIEWED_TIP", TIP)
    assert rt.main() == 1
    out = capsys.readouterr().out
    assert events == ["preflight"] and "needs --boxes-head" in out and "before a train token was written" in out, (
        events, out)


@pytest.mark.parametrize("argv,go", [(["run", "--go"], True), (["run"], False), (["plan", "--go"], False),
                                     (["check"], False)])
def test_the_command_line_sets_closure_boxes_head_and_closure_go(monkeypatch, tmp_path, argv, go):
    rt = _release_train()
    _main_world(monkeypatch, rt, tmp_path, [], argv + ["--boxes-head", "9" * 40])

    def stop():
        raise rt.Fail("stopped here")
    monkeypatch.setattr(rt, "closure_load_state", stop)
    assert rt.main() == 1
    assert (rt.CLOSURE_BOXES_HEAD, rt.CLOSURE_GO) == ("9" * 40, go)


@pytest.mark.parametrize("which,want", [
    ("short", "--boxes-head is not 40 hex; give the full sha read as HEAD on both boxes"),
    ("upper", "--boxes-head is not 40 hex; give the full sha read as HEAD on both boxes"),
    ("missing", "is not a commit of this repository; fetch origin, then run again"),
    ("lane", "does not stand on the first-parent line of origin's main"),
    ("side", "does not stand on the first-parent line of origin's main"),
    ("origin", "origin's main eeeeeeeeeeee is not a commit of this repository; fetch origin, then run again"),
])
def test_each_refusal_of_the_word_names_the_way(line, monkeypatch, which, want):
    rt, scratch, c = line
    word = {"short": c["m1"][:12], "upper": c["m1"].upper(), "missing": "f" * 40, "origin": c["m1"]}.get(which)
    monkeypatch.setattr(rt, "CLOSURE_BOXES_HEAD", word or c[which])
    if which == "origin":
        monkeypatch.setattr(rt, "_closure_origin_main", lambda: "e" * 40)
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt.closure_base({})
    assert want in str(exc.value), str(exc.value)
    if which in ("lane", "side"):
        assert "read HEAD on both boxes again" in str(exc.value), str(exc.value)


@pytest.mark.parametrize("rec,word,want", [
    ("m2", "m2", "equal"), ("m1", "m2", "ahead by 1"), ("m2", "base", "behind by 2"),
    (None, "m1", "no verified record"), ("lane", "m2", "the newest verified record is off the first-parent line")])
def test_the_words_relation_to_the_newest_verified_record_is_printed_and_never_refuses(line, monkeypatch, capsys,
                                                                                       rec, word, want):
    rt, scratch, c = line
    _state_files(monkeypatch, rt, scratch, {"a": {"verified": True, "code_sha": c[rec]}} if rec else {})
    monkeypatch.setattr(rt, "CLOSURE_BOXES_HEAD", c[word])
    monkeypatch.setattr(rt, "CLOSURE_GO", True)
    assert rt.closure_base({}) == {"base": c[word], "from": "boxes-head", "relation": want, "prior": None}
    assert ("BASE %s is --boxes-head; to the newest verified record %s: %s"
            % (c[word], c[rec] if rec else "(none)", want)) in capsys.readouterr().out


def test_closure_base_takes_the_word_when_it_is_given_and_carries_the_newest_records_numbers(line, monkeypatch):
    rt, scratch, c = line
    numbers = {"call": 1, "container": 0, "return": 2, "attribute": 0, "loop": 3}
    _state_files(monkeypatch, rt, scratch, {"a": {"verified": True, "code_sha": c["m2"],
                                                  rt.CLOSURE_STATE_KEY: {"unfollowed": numbers}}})
    monkeypatch.setattr(rt, "CLOSURE_BOXES_HEAD", c["m1"])
    got = rt.closure_base({})
    assert (got["base"], got["from"], got["prior"]) == (c["m1"], "boxes-head", numbers)
    monkeypatch.setattr(rt, "CLOSURE_BOXES_HEAD", None)
    got = rt.closure_base({})
    assert (got["base"], got["from"], got["prior"]) == (c["m2"], "state", numbers)


def test_a_resumed_run_takes_the_base_from_its_record_and_a_word_given_again_must_equal_it(line, monkeypatch,
                                                                                          capsys):
    rt, scratch, c = line
    st = {"code_sha": c["m2"], rt.CLOSURE_STATE_KEY: {"base": c["m1"], "base_relation": "equal"}}
    monkeypatch.setattr(rt, "CLOSURE_GO", True)
    for word in (None, c["m1"]):
        monkeypatch.setattr(rt, "CLOSURE_BOXES_HEAD", word)
        assert rt.closure_base(st) == {"base": c["m1"], "from": "record", "relation": "equal", "prior": None}
        assert "BASE %s is the base this run recorded" % c["m1"] in capsys.readouterr().out
    monkeypatch.setattr(rt, "CLOSURE_BOXES_HEAD", c["m2"])
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt.closure_base(st)
    assert ("--boxes-head is not the base %s this run recorded; give the recorded base or leave the word out"
            % c["m1"]) in str(exc.value)


def test_the_record_stores_where_the_base_came_from_its_relation_and_the_numbers(monkeypatch):
    rt = _release_train()
    cell = dict(rec="absent", pre=False, code=False, P="O", Sb="O", key="valid", call="F")
    saved = []
    st = _cell_world(monkeypatch, rt, cell, saved)
    monkeypatch.setattr(rt, "closure_base", lambda st: dict(_taken(BASE), relation="ahead by 1"))
    rt.closure_guard(st, "start", write=True, reach=())
    rec = saved[0][rt.CLOSURE_STATE_KEY]
    assert (rec["base"], rec["base_from"], rec["base_relation"]) == (BASE, "boxes-head", "ahead by 1")
    assert rec["unfollowed"] == dict.fromkeys(rt.CLOSURE_UNFOLLOWED, 0)
    assert rt._closure_record_ok(rec, N_W)
    for k, bad in (("base_from", "state"), ("base_relation", None), ("unfollowed", {"call": 0}),
                   ("unfollowed", dict(rec["unfollowed"], call=-1))):
        assert not rt._closure_record_ok(dict(rec, **{k: bad}), N_W), k


# ---------------------------------------------------------------- (iv): the closed form lists (41-Q1 point 1)


def _census(tmp_path, body):
    api = tmp_path / "api"
    api.mkdir(exist_ok=True)
    (api / "review_rules.py").write_text("TABLE = {}\nLIST = []\n", encoding="utf-8")
    (api / "seat_mod.py").write_text("import review_rules as rr\nT = rr.TABLE\n", encoding="utf-8")
    (api / "main.py").write_text(body, encoding="utf-8")
    rt = _release_train()
    return rt, rt.closure_census(str(api), ["review_rules.py", "seat_mod.py", "main.py"], ["review_rules.py"])


RR = "import review_rules as rr\n"
READ_FORMS = {
    "an attribute read": RR + "if rr.TABLE:\n    pass\n",
    "a subscript read": RR + "x = rr.TABLE['k'] == 1\n",
    "a call at depth 1": RR + "rr.review_eval()\n",
    "a read through an assignment alias": RR + "W = rr.TABLE\nif W['k']:\n    pass\n",
    "a read through an import-as alias": "import review_rules as R\nif R.LIST:\n    pass\n",
    "a read through a from-import alias": "from review_rules import TABLE\nif TABLE['k']:\n    pass\n",
}
WRITE_FORMS = {
    "a store": RR + "rr.TABLE = {}\n",
    "a delete": RR + "del rr.TABLE\n",
    "an augmented store": RR + "rr.LIST += [1]\n",
    "a call below depth 1": RR + "rr.LIST.append(1)\n",
    "the first argument of setattr": RR + "setattr(rr, 'TABLE', {})\n",
    "the first argument of delattr": RR + "delattr(rr, 'TABLE')\n",
    "a subscript store through an assignment alias": RR + "W = rr.TABLE\nW['k'] = 1\n",
    "a store through an import-as alias": "import review_rules as R\nR.TABLE = {}\n",
    "a delete through a from-import alias": "from review_rules import TABLE\ndel TABLE['k']\n",
    "an augmented store through a from-import-as alias": "from review_rules import LIST as L\nL += [1]\n",
    "a call below depth 1 through an alias another module holds": "import seat_mod as s\ns.T.update({})\n",
    "a star import": "from review_rules import *\n",
    "a name bound again by an import": RR + "import os as rr\n",
    "a parameter named as the evaluator": RR + "def f(rr):\n    pass\n",
}
UNKNOWN_FORMS = {
    "a tuple target": (RR + "a, b = rr.LIST\n", "a name of the evaluator bound by a form the census does not know"),
    "an alias of a module that holds the evaluator": (
        "import seat_mod as s\nimport review_rules as rr\nS = s\n",
        "a name of the evaluator bound by a form the census does not know"),
    "an annotated alias": (RR + "W: dict = rr.TABLE\n", "(AnnAssign.value)"),
    "an assignment expression": (RR + "if (W := rr.TABLE):\n    pass\n", "(NamedExpr.value)"),
    "an or": (RR + "W = rr.TABLE or {}\nW['k'] = 1\n", "(BoolOp.values)"),
    "an if-expression": (RR + "W = rr.TABLE if True else {}\nW['k'] = 1\n", "(IfExp.body)"),
    "a with-as": (RR + "with rr.TABLE as W:\n    W['k'] = 1\n", "(withitem.context_expr)"),
    "a lambda": (RR + "f = lambda: rr.TABLE\nf()['k'] = 1\n", "(Lambda.body)"),
    "a loop target": (RR + "for rr.TABLE in [{}]:\n    pass\n", "a store or delete on the evaluator"),
    "a default argument": (RR + "def f(t=rr.TABLE):\n    t['k'] = 1\n", "(arguments.defaults)"),
}
UNFOLLOWED_FORMS = (
    ("call", RR + "print(rr.TABLE)\n"),
    ("call", RR + "print(x=rr.TABLE)\n"),
    ("call", RR + "print(*rr.LIST)\n"),
    ("container", RR + "L = [rr.TABLE]\n"),
    ("container", RR + "d = {}\nd['k'] = rr.TABLE\n"),
    ("container", "import seat_mod as s\nimport review_rules as rr\nL = (s,)\n"),
    ("return", RR + "def f():\n    return rr.TABLE\n"),
    ("attribute", RR + "class O:\n    pass\nO.t = rr.TABLE\n"),
    ("loop", RR + "for x in rr.LIST:\n    x.append(1)\n"),
    ("loop", RR + "y = [x for x in rr.LIST]\n"),
)
UNCOUNTED_FORMS = {
    "the value a call through the evaluator returns": RR + "rr.review_eval()['k'] = 1\n",
}


@pytest.mark.parametrize("form", sorted(READ_FORMS))
def test_iv_each_read_form_passes(tmp_path, form):
    rt, (count, hits, unfollowed) = _census(tmp_path, READ_FORMS[form])
    assert count == 2 and hits == [] and sum(unfollowed.values()) == 0, (form, hits, unfollowed)


@pytest.mark.parametrize("form", sorted(WRITE_FORMS))
def test_iv_each_write_form_is_refused(tmp_path, form):
    rt, (count, hits, unfollowed) = _census(tmp_path, WRITE_FORMS[form])
    want = next(t for words, t in WRITE_TEXTS if words in form)
    assert count == 2 and want in [h[2] for h in hits], (form, hits)


WRITE_TEXTS = (("call below depth", "a call through the evaluator at depth 2"),
               ("setattr", "setattr or delattr on the evaluator"), ("delattr", "setattr or delattr on the evaluator"),
               ("star import", "a star import"), ("bound again", "a name of the evaluator bound again by an import"),
               ("parameter", "a name of the evaluator bound by a form the census does not know"),
               ("", "a store or delete on the evaluator"))


@pytest.mark.parametrize("form", sorted(UNKNOWN_FORMS))
def test_iv_each_unknown_form_is_one_hit_in_main_py_with_its_written_text(tmp_path, form):
    body, want = UNKNOWN_FORMS[form]
    rt, (count, hits, unfollowed) = _census(tmp_path, body)
    assert len(hits) == 1 and hits[0][0] == "main.py" and want in hits[0][2], (form, hits)


def test_iv_a_use_under_a_node_type_the_census_code_never_names_is_a_hit():
    rt = _release_train()
    tree = ast.parse(RR)
    tree.body.append(ast.Expr(value=ast.Await(value=ast.Attribute(value=ast.Name(id="rr", ctx=ast.Load()),
                                                                  attr="TABLE", ctx=ast.Load()))))
    tree = ast.fix_missing_locations(tree)
    tracked, carriers = rt._closure_bindings(tree, {"review_rules"}, {})
    hits, counts = rt._closure_uses(tree, tracked, carriers, {}, {"review_rules"})
    assert [h[1] for h in hits] == ["a use of the evaluator at a place the census does not list (Await.value)"], hits
    code = [ast.unparse(n) for n in ast.parse(Path(rt.__file__).read_text(encoding="utf-8")).body
            if getattr(n, "name", None) in ("closure_census", "_closure_bindings", "_closure_uses", "_closure_chain",
                                            "_closure_field")]
    assert len(code) == 5 and not any("Await" in c for c in code + [repr(rt.CLOSURE_PLACES)]), "Await is named"


S1_WALKED = {("Attribute", "value"), ("Subscript", "value"), ("Starred", "value")}  # the census walks through to the parent
S1_NOT_BUILT = dict.fromkeys((("Expression", "body"), ("FunctionType", "argtypes"), ("FunctionType", "returns")),
                             "no file the census parses in exec mode has this mode")


def _s1_pairs():
    pairs = []
    for name, c in sorted(vars(ast).items()):
        if isinstance(c, type) and issubclass(c, ast.AST) and c.__name__ == name:
            pairs += [(name, f) for t, _s, f in _grammar(c) or () if t == "expr"]
    return pairs


def _s1_host(node):
    if isinstance(node, ast.stmt):
        return node
    if isinstance(node, ast.expr):
        return ast.Expr(value=node)
    if isinstance(node, ast.excepthandler):
        return ast.Try(body=[ast.Pass()], handlers=[node], orelse=[], finalbody=[])
    if isinstance(node, ast.keyword):
        return ast.Expr(value=ast.Call(func=ast.Name(id="x", ctx=ast.Load()), args=[], keywords=[node]))
    if isinstance(node, ast.comprehension):
        return ast.Expr(value=ast.ListComp(elt=ast.Name(id="x", ctx=ast.Load()), generators=[node]))
    if isinstance(node, (ast.arguments, ast.arg, ast.type_param)):
        return ast.FunctionDef(name="x", args=node if isinstance(node, ast.arguments) else _arguments(
            [node] if isinstance(node, ast.arg) else ()), body=[ast.Pass()], decorator_list=[], returns=None,
            type_params=[node] if isinstance(node, ast.type_param) else [])
    if isinstance(node, ast.withitem):
        return ast.With(items=[node], body=[ast.Pass()])
    if isinstance(node, ast.match_case):
        return ast.Match(subject=ast.Name(id="x", ctx=ast.Load()), cases=[node])
    if isinstance(node, ast.pattern):
        return _s1_host(ast.match_case(pattern=node, guard=None, body=[ast.Pass()]))
    raise AssertionError("no host for " + type(node).__name__)


def test_iv_every_expression_field_of_the_grammar_is_a_listed_place_or_one_hit_naming_it():
    """For every node type of ast and every field whose grammar type is expr, expr* or expr?, read at test time from the class's own signature (the first line of its docstring when that line begins with the class's own name and a parenthesis), a tree built by hand holds rr.TABLE at that place: it passes, or is counted, only where the pair stands in CLOSURE_PLACES; the three pairs the census walks through take their parent's place; the pairs of a mode other than exec are not built (written with the reason); every other pair is one hit that names it."""
    rt = _release_train()
    pairs = _s1_pairs()
    assert set(S1_NOT_BUILT) == {p for p in pairs if issubclass(getattr(ast, p[0]), ast.mod) and p[0] != "Module"}
    listed = [p for p in pairs if p in rt.CLOSURE_PLACES]
    assert set(listed) == set(rt.CLOSURE_PLACES) and S1_WALKED <= set(pairs), (listed, S1_WALKED - set(pairs))
    wrong, default = [], 0
    for p in pairs:
        if p in S1_NOT_BUILT:
            continue
        plant = ast.Attribute(value=ast.Name(id="rr", ctx=ast.Load()), attr="TABLE", ctx=ast.Load())
        tree = ast.parse(RR)
        tree.body.append(_s1_host(_filled(getattr(ast, p[0]), p[1], plant)))
        tree = ast.fix_missing_locations(tree)
        tracked, carriers = rt._closure_bindings(tree, {"review_rules"}, {})
        hits, counts = rt._closure_uses(tree, tracked, carriers, {}, {"review_rules"})
        texts = [h[1] for h in hits]
        if p in rt.CLOSURE_PLACES:
            place = rt.CLOSURE_PLACES[p]
            want = dict(dict.fromkeys(rt.CLOSURE_UNFOLLOWED, 0), **({place: 1} if place in rt.CLOSURE_UNFOLLOWED else {}))
            ok = texts == [] and counts == want
        elif p in S1_WALKED:
            ok = texts == []
        else:
            default += 1
            ok = texts == ["a use of the evaluator at a place the census does not list (%s.%s)" % p]
        if not ok:
            wrong.append((p, texts, counts))
    print("COUNT S1: %d pairs (%d listed, %d walked through, %d not built, %d default)"
          % (len(pairs), len(listed), len(S1_WALKED), len(S1_NOT_BUILT), default))
    assert len(pairs) == len(listed) + len(S1_WALKED) + len(S1_NOT_BUILT) + default and wrong == [], wrong


_MODULE_NAMED = ("import, plain name", "import, plain name, as", "from-import, level 0, module plain, a name, named by the module", "from-import, level 0, module plain, a name, as, named by the module", "from-import, level 0, module plain, the star", "from-import, level above 0, module plain, a name, named by the module", "from-import, level above 0, module plain, a name, as, named by the module", "from-import, level above 0, module plain, the star")
FOLLOWED_IMPORTS = {("review_rules", s) for s in _MODULE_NAMED + ("from-import, level above 0, module absent, a name, named by the imported name", "from-import, level above 0, module absent, a name, as, named by the imported name")} | {("seat_mod", s) for s in _MODULE_NAMED}  # T:11292 a stem; :11294 a module with exports, plain or with as; :11299 from a stem; :11301 a stem from the package; :11303 an export; :11323 a star of either is its own hit
_S2_TARGETS = {"review_rules": "TABLE", "seat_mod": "T"}


def _s2_cells():
    cells = [dict(kind="import", dotted=d, as_=a) for d, a in itertools.product((False, True), repeat=2)]
    for level, module, star, as_ in itertools.product((0, 1), ("absent", "plain", "dotted"), (False, True),
                                                      (False, True)):
        for role in ((None,) if star else ("imported",) if module == "absent" else ("module", "imported")):
            cells.append(dict(kind="from", level=level, module=module, star=star, as_=as_, role=role))
    return cells


def _s2_shape(c):
    if c["kind"] == "import":
        return "import, %s name%s" % ("dotted" if c["dotted"] else "plain", ", as" if c["as_"] else "")
    return "from-import, level %s, module %s, %s%s%s" % (
        "above 0" if c["level"] else "0", c["module"], "the star" if c["star"] else "a name", ", as" if c["as_"] else "",
        "" if c["star"] else ", named by the " + ("module" if c["role"] == "module" else "imported name"))


def _s2_source(c, t, x):
    b = " as b" if c["as_"] else ""
    if c["kind"] == "import":
        mod = ("pkg." if c["dotted"] else "") + t
        return "import %s%s\n%s.%s['k'] = 1\n" % (mod, b, "b" if c["as_"] else mod, x)
    mod = ("" if c["module"] == "absent" else ("pkg" if c["module"] == "plain" else "pkg.sub") if c["role"] == "imported"
           else t if c["module"] == "plain" else "pkg." + t)
    name = "*" if c["star"] else x if c["role"] == "module" else t
    bound = "b" if c["as_"] else name
    store = ("%s['k'] = 1" % x if c["star"] else "%s['k'] = 1" % bound if c["role"] == "module"
             else "%s.%s['k'] = 1" % (bound, x))
    return "from %s%s import %s%s\n%s\n" % ("." * c["level"], mod, name, b, store)


def _parses(src):
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


_S2_NO_SOURCE = lambda c: c["kind"] == "from" and (  # noqa: E731 (written: no source text parses to these)
    (c["level"] == 0 and c["module"] == "absent") or (c["star"] and c["as_"]))
S2_SHAPES = [c for c in _s2_cells() if _parses(_s2_source(c, "review_rules", "TABLE"))]
S2_PLANTS = {(_s2_shape(c), t): ("from . import *\n" if _s2_shape(c) == "from-import, level above 0, module absent, the star"
                                 else _s2_source(c, t, x))
             for c in S2_SHAPES for t, x in _S2_TARGETS.items()
             if not (_s2_shape(c) == "from-import, level above 0, module absent, the star" and t == "seat_mod")}


@pytest.mark.parametrize("shape,target", sorted(S2_PLANTS))
def test_iv_every_shape_of_an_import_that_names_the_evaluator_is_followed_or_a_hit_naming_the_shape(tmp_path, shape, target):
    """Every shape of an import statement, generated from its fields and from which of its names names the target, once for a stem and once for a module with exports, each followed by one store through the name it binds, and the star import with no module as itself: at least one hit each; a shape outside FOLLOWED_IMPORTS is a hit that names the shape, and one inside it is not."""
    cells = _s2_cells()
    assert [c for c in cells if not _parses(_s2_source(c, "review_rules", "TABLE"))] == [c for c in cells
                                                                                       if _S2_NO_SOURCE(c)]
    assert len(S2_PLANTS) == len(S2_SHAPES) * len(_S2_TARGETS) - 1
    if (shape, target) == sorted(S2_PLANTS)[0]:
        print("COUNT S2: %d cells, %d without source, %d shapes, %d plants (%d followed, %d hits)" % (
            len(cells), len(cells) - len(S2_SHAPES), len(S2_SHAPES), len(S2_PLANTS),
            len({(t, s) for s, t in S2_PLANTS} & FOLLOWED_IMPORTS), len({(t, s) for s, t in S2_PLANTS} - FOLLOWED_IMPORTS)))
    rt, (count, hits, unfollowed) = _census(tmp_path, S2_PLANTS[(shape, target)])
    texts = [h[2] for h in hits]
    assert texts != [] and (("an import the census does not follow (%s)" % shape) in texts) == (
        (target, shape) not in FOLLOWED_IMPORTS), (S2_PLANTS[(shape, target)], texts)


Q1_FILES = {"review_rules.py": "TABLE = {}\nLIST = []\n", "seat_mod.py": "import review_rules as rr\nT = rr.TABLE\n",
            "hub.py": "import review_rules as rr\nimport seat_mod as s\n", "hub2.py": "from hub import s\n"}


def _q1_bindings(rt):
    trees = {f[:-3]: ast.parse(s) for f, s in Q1_FILES.items() if f != "review_rules.py"}
    exports, carried = {}, {}
    for _round in range(len(trees) + 1):
        bound = {m: rt._closure_bindings(t, {"review_rules"}, exports, carried) for m, t in trees.items()}
        new, more = ({m: dict(b[k]) for m, b in bound.items()} for k in (0, 1))
        if (new, more) == (exports, carried):
            break
        exports, carried = new, more
    return exports, carried


def _q1_rows():
    if not _TOOL_FILE.exists():
        return []
    spec = importlib.util.spec_from_file_location("release_train_closure_q1_rows", _TOOL_FILE)
    rt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rt)
    try:
        exports, carried = _q1_bindings(rt)
    except Exception as e:  # a census without the carried fixpoint: one row, which fails its count, not the file
        return [("the census world", "not built: %s" % type(e).__name__)]
    rows = []
    for m in sorted(m for m in exports if exports[m]):
        rows += [(m, "zz_other")] + [(m, e) for e in sorted(exports[m])] + [(m, c) for c in sorted(carried[m])] + [
            (m, "*")]
    return rows + [("hub2", "s")]


Q1_ROWS = _q1_rows()


@pytest.mark.parametrize("module,name", Q1_ROWS)
def test_iv_every_from_import_out_of_a_module_with_exports_is_followed_binds_nothing_or_is_a_star_hit(tmp_path, module, name):
    """Generated per module with exports of a census world that adds hub.py (import review_rules as rr; import seat_mod as s) and hub2.py (from hub import s): a name that is no export passes with no hit; each export and each carrier is followed and counted when handed to a call; a star is a hit; and the case of two hubs, the carrier taken from hub2, is followed and counted."""
    rt = _release_train()
    exports, carried = _q1_bindings(rt)
    assert len(Q1_ROWS) == sum(2 + len(exports[m]) + len(carried[m]) for m in exports if exports[m]) + 1
    if (module, name) == Q1_ROWS[0]:
        print("COUNT Q1: %d rows (%s; two hubs 1)" % (len(Q1_ROWS), "; ".join(
            "%s 1 + %d + %d + 1" % (m, len(exports[m]), len(carried[m])) for m in sorted(exports) if exports[m])))
    api = tmp_path / "api"
    api.mkdir()
    for f, s in Q1_FILES.items():
        (api / f).write_text(s, encoding="utf-8")
    if name == "zz_other":
        body = "from %s import zz_other\nzz_other['k'] = 1\n" % module
    elif name == "*":
        body = "from %s import *\n" % module
    elif name in exports[module]:
        body = "from %s import %s\nprint(%s)\n" % (module, name, name)
    else:
        body = "from %s import %s\nprint(%s.T)\n" % (module, name, name)
    (api / "main.py").write_text(body, encoding="utf-8")
    count, hits, unfollowed = rt.closure_census(str(api), sorted(Q1_FILES) + ["main.py"], ["review_rules.py"])
    texts = [h[2] for h in hits]
    if name == "*":
        assert "a star import" in texts, (body, texts)
    elif name == "zz_other":
        assert texts == [] and sum(unfollowed.values()) == 0, (body, texts, unfollowed)
    else:
        assert texts == [] and unfollowed == dict(dict.fromkeys(rt.CLOSURE_UNFOLLOWED, 0), call=1), (
            body, texts, unfollowed)


@pytest.mark.parametrize("form,body", UNFOLLOWED_FORMS)
def test_iv_each_unfollowed_form_passes_and_is_counted(tmp_path, form, body):
    rt, (count, hits, unfollowed) = _census(tmp_path, body)
    assert hits == [] and unfollowed == dict(dict.fromkeys(rt.CLOSURE_UNFOLLOWED, 0), **{form: 1}), (body, hits,
                                                                                                    unfollowed)


@pytest.mark.parametrize("form", sorted(UNCOUNTED_FORMS))
def test_iv_a_form_neither_followed_nor_counted_passes(tmp_path, form):
    rt, (count, hits, unfollowed) = _census(tmp_path, UNCOUNTED_FORMS[form])
    assert hits == [] and sum(unfollowed.values()) == 0, (form, hits, unfollowed)


def test_the_disclosure_line_shows_the_numbers_and_the_newest_records_and_never_refuses(monkeypatch, capsys):
    rt = _release_train()
    cell = dict(rec="absent", pre=False, code=False, P="O", Sb="O", key="valid", call="F")
    saved = []
    st = _cell_world(monkeypatch, rt, cell, saved)
    counts = {"call": 3, "container": 2, "return": 1, "attribute": 0, "loop": 1}
    rt.CLOSURE_SEEN[TIP] = {"differs": [], "unfollowed": dict(counts)}
    monkeypatch.setattr(rt, "closure_base", lambda st: _taken(BASE, dict(counts, call=2)))
    rt.closure_guard(st, "start", write=True, reach=())
    out = capsys.readouterr().out
    assert ("7 use(s) of the evaluator not followed at the reviewed tip: 3 handed to a call, 2 put in a container, "
            "1 returned, 0 bound as an attribute of another object, 1 iterated; a disclosure, not a refusal; the "
            "newest verified record holds call 2, container 2, return 1, attribute 0, loop 1") in out, out
    assert saved[0][rt.CLOSURE_STATE_KEY]["unfollowed"] == counts
    monkeypatch.setattr(rt, "closure_base", lambda st: _taken(BASE, dict(counts)))
    rt.closure_guard({}, "check")
    out = capsys.readouterr().out
    assert "7 use(s) of the evaluator not followed" in out and "newest verified record holds" not in out, out


def test_the_disclosure_counts_the_census_of_the_reviewed_tip(world, monkeypatch, tmp_path, capsys):
    rt, scratch, base_word = world
    tip = scratch.commit({"main.py": b"import review_rules as rr\nprint(rr.CODE_DOMAIN)\n"})
    _bind(monkeypatch, rt, scratch, tip, Boxes(base_word), tmp_path)
    rt.closure_guard({}, "check")
    assert ("1 use(s) of the evaluator not followed at the reviewed tip: 1 handed to a call, 0 put in a container"
            in capsys.readouterr().out)


# ---------------------------------------------------------------- a build-only change (41-Q1 point 4)


def test_iii_a_build_part_with_no_build_file_differing_is_refused_naming_its_files(world, monkeypatch, tmp_path):
    rt, scratch, base_word = world
    tip = scratch.commit({"main.py": b"# no build change\n"})
    _bind(monkeypatch, rt, scratch, tip, Boxes(base_word), tmp_path,
          change={"build": {"backend/api/Dockerfile": "0" * 64}})
    with pytest.raises(rt.ClosureRefusal) as exc:
        rt.closure_guard({}, "check")
    assert ("(iii) the entry's build part names backend/api/Dockerfile and no build file differs at the reviewed tip"
            in str(exc.value)), str(exc.value)
