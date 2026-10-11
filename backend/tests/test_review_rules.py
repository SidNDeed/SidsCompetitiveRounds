"""The review rules loader, validator and evaluator, over SYNTHETIC revisions
(review_testkit). Bars: A3 (absent), A4 (five refusal classes, each logged
once), A5 (a resealed self-test mutant refuses; the unaltered revision loads),
A6 (re-pointing reaches a running process), A7 (a two-seat measure and its
negation on a one-sided game), the code closure bound BY FILE (round 2 M2),
the bounded inventory and work (finding 9), and the non-following reads
(round 2 L3)."""

import copy
import json
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import review_measures as rm  # noqa: E402
import review_rules as rr  # noqa: E402
import review_testkit as tk  # noqa: E402


@pytest.fixture
def fresh(monkeypatch, tmp_path):
    """A clean loader state and an empty review root."""
    monkeypatch.setattr(rr, "_STATE", rr.State("absent"))
    monkeypatch.setattr(rr, "_KEY", None)
    monkeypatch.setattr(rr, "_LOGGED", None)
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv(rr.ROOT_ENV, str(root))
    return root


def _built(tmp_path, doc=None, cases=None, name="draft"):
    store, rev = tk.build_revision(tmp_path, doc, cases, name)
    return os.path.join(store, "rules-" + rev), rev


def _into_root(root, rdir):
    dst = os.path.join(str(root), os.path.basename(rdir))
    shutil.copytree(rdir, dst)
    return dst


# -- A3: absent ------------------------------------------------------------------

def test_a3_no_pointer_a_missing_root_and_rules_none_all_read_absent(fresh, monkeypatch, tmp_path):
    assert rr.refresh_rules().word == "absent" and rr.health_word() == "absent"
    assert rr.current_rules().ruleset is None
    tk.point(fresh, rr.NONE_TARGET)
    assert rr.refresh_rules().word == "absent"
    monkeypatch.setenv(rr.ROOT_ENV, str(tmp_path / "no-such-root"))
    assert rr.refresh_rules().word == "absent"


def test_initial_absent_bootstrap_then_a_valid_revision_loads(fresh, tmp_path, capsys):
    assert rr.refresh_rules().word == "absent"
    rdir, rev = _built(tmp_path)
    _into_root(fresh, rdir)
    tk.point(fresh, "rules-" + rev)
    st = rr.refresh_rules()
    assert st.word == rev and st.ruleset.rev == rev
    out = capsys.readouterr().out
    assert "[REVIEW] rules: absent" in out and "[REVIEW] rules: %s" % rev in out


# -- A6: re-pointing reaches the running process -----------------------------------

def test_a6_re_pointing_current_changes_the_word_with_no_restart(fresh, tmp_path):
    r1, rev1 = _built(tmp_path, name="d1")
    r2, rev2 = _built(tmp_path, name="d2")
    assert rev1 != rev2                      # a fresh nonce per build
    _into_root(fresh, r1)
    _into_root(fresh, r2)
    tk.point(fresh, "rules-" + rev1)
    assert rr.refresh_rules().word == rev1
    tk.point(fresh, "rules-" + rev2)
    assert rr.refresh_rules().word == rev2
    assert rr.health_word() == rev2


# -- A4 / A5: five refusal classes, each logged once ----------------------------------

def _refused_once(root, target, cls, capsys):
    tk.point(root, target)
    assert rr.refresh_rules().word == "refused" and rr.current_rules().reason == cls
    assert rr.refresh_rules().word == "refused"
    out = capsys.readouterr().out
    assert out.count("[REVIEW] rules: refused (%s)" % cls) == 1, out


def test_a4_unreadable(fresh):
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(os.path.join(str(fresh), "rules-" + "0" * 12))
    assert e.value.cls == "unreadable"


def test_a4_a_pointer_to_a_missing_revision_refuses_once(fresh, capsys):
    _refused_once(fresh, "rules-" + "0" * 12, "pointer", capsys)


def test_a4_malformed_json(fresh, tmp_path, capsys):
    rdir, _ = _built(tmp_path)
    with open(os.path.join(rdir, "rules.json"), "w") as f:
        f.write("{not json")
    new, rev = tk.reseal(rdir)
    _into_root(fresh, new)
    _refused_once(fresh, "rules-" + rev, "malformed", capsys)


def test_a4_digest_mismatch(fresh, tmp_path, capsys):
    rdir, rev = _built(tmp_path)
    with open(os.path.join(rdir, "rules.json"), "ab") as f:
        f.write(b" ")
    _into_root(fresh, rdir)
    _refused_once(fresh, "rules-" + rev, "digest", capsys)


def test_a4_stale_code_closure(fresh, tmp_path, capsys, monkeypatch):
    rdir, rev = _built(tmp_path)
    _into_root(fresh, rdir)
    real = rr._code_files

    def one_byte_more(names, api_dir=None):
        files = real(names, api_dir)
        files["code/review_measures.py"] += b"#"
        return files
    monkeypatch.setattr(rr, "_code_files", one_byte_more)
    _refused_once(fresh, "rules-" + rev, "stale", capsys)


def test_a5_a_resealed_selftest_mutant_refuses_and_the_original_loads(fresh, tmp_path, capsys):
    rdir, rev = _built(tmp_path)
    keep = _into_root(fresh, rdir)
    with open(os.path.join(rdir, "selftest.json"), encoding="utf-8") as f:
        st = json.load(f)
    st["cases"][0]["fire"] = sorted(st["cases"][0]["fire"] + [tk.ID_PUB])
    with open(os.path.join(rdir, "selftest.json"), "w", encoding="utf-8") as f:
        json.dump(st, f)
    mutant, mrev = tk.reseal(rdir)
    _into_root(fresh, mutant)
    _refused_once(fresh, "rules-" + mrev, "selftest", capsys)
    tk.point(fresh, os.path.basename(keep))
    assert rr.refresh_rules().word == rev


# -- finding 9: bounded inventory and work -------------------------------------------

def test_too_many_files_unexpected_entries_and_aggregate_bytes_refuse_before_parsing(tmp_path):
    rdir, _ = _built(tmp_path)
    data = os.path.join(rdir, "data")
    os.mkdir(data)
    for i in range(rr._BOUNDS["files_max"] + 1):
        with open(os.path.join(data, "t_" + chr(97 + i % 26) * (1 + i // 26) + ".txt"), "w") as f:
            f.write("x")
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(rdir)
    assert (e.value.cls, str(e.value)) == ("inventory", "inventory: file count")
    shutil.rmtree(data)
    os.mkdir(os.path.join(rdir, "other"))
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(rdir)
    assert e.value.cls == "inventory"
    os.rmdir(os.path.join(rdir, "other"))
    os.mkdir(data)
    chunk = b"x" * (rr._BOUNDS["data_bytes_max"] - 1)
    for n in ("a.txt", "b.txt", "c.txt"):
        with open(os.path.join(data, n), "wb") as f:
            f.write(chunk)
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(rdir)
    assert e.value.cls == "inventory"


def test_selftest_work_beyond_the_bound_refuses(tmp_path):
    doc = tk.synthetic_doc()
    wide = {"any": [tk.cmp(tk.M("seat.observed_hits"), "lt", tk.V(-1))] * 600}
    doc["rules"].append({"id": "r0000a0ff", "scope": "game", "subject": "seat", "effect": "note",
                         "post": False, "post_since": None, "when": wide,
                         "show": [["seat", "seat.index"]], "line": "x {seat}"})
    cases = tk.quiet_cases() * 100
    with pytest.raises(rr.Refused) as e:
        _built(tmp_path, doc, cases)
    assert e.value.cls == "work"


def test_the_deadline_refuses(tmp_path, monkeypatch):
    rdir, _ = _built(tmp_path)
    monkeypatch.setitem(rr._BOUNDS, "deadline_s", -1)
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(rdir)
    assert e.value.cls == "work"


def test_the_digest_is_framed_and_injective():
    a = rr.revision_digest({"rules.json": b"ab", "selftest.json": b"c"})
    b = rr.revision_digest({"rules.json": b"a", "selftest.json": b"bc"})
    c = rr.revision_digest({"rules.jsona": b"b", "selftest.json": b"c"})
    assert len({a, b, c}) == 3
    assert rr.revision_digest({"x": b""}) != rr.revision_digest({"x": b"", "y": b""})
    # the frame itself, written out independently: domain tag, count, then per
    # sorted path its 8-byte length, the path, the 8-byte content length, the content
    import hashlib
    files = {"selftest.json": b"{}", "rules.json": b"[1]", "data/x.json": b""}
    h = hashlib.sha256(rr.DOMAIN + (3).to_bytes(8, "big"))
    for p in sorted(files):
        h.update(len(p).to_bytes(8, "big") + p.encode() + len(files[p]).to_bytes(8, "big") + files[p])
    assert rr.revision_digest(files) == h.hexdigest()


def test_the_vocabulary_must_be_exactly_the_entries_used(tmp_path):
    rdir, _ = _built(tmp_path)
    p = os.path.join(rdir, "rules.json")
    with open(p, encoding="utf-8") as f:
        doc = json.load(f)
    doc["vocabulary"] = sorted(doc["vocabulary"] + ["seat.compat"])
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    new, _ = tk.reseal(rdir)
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(new)
    assert e.value.cls == "malformed"


# -- round 2 M2: the closure is bound BY FILE ---------------------------------------
# The bound fingerprint is the framed digest of every code file the revision's
# `closure` names (review_measures.py and the loader review_rules.py at least)
# and, for the whole-closure fingerprint, every file the loader reads for the
# revision. Dynamic reach is irrelevant: any byte of any file in the closure
# moves it; a file outside the closure does not.

API_DIR = os.path.join(HERE, "..", "api")


def _api_copy(tmp_path, name, extra=()):
    d = tmp_path / ("api-" + name)
    d.mkdir()
    for m in rr.CODE_REQUIRED + tuple(extra):
        shutil.copy(os.path.join(API_DIR, m), str(d))
    return d


def _change(path, old, new):
    src = path.read_bytes()
    if b"\r\n" in src:                      # the checkout's line ending
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    assert src.count(old.encode()) == 1, (path, old)
    path.write_bytes(src.replace(old.encode(), new.encode()))


def _revision_files(rdir):
    import time
    return rr._inventory(rdir, time.monotonic() + rr._BOUNDS["deadline_s"])


def _closure(api_dir, rdir):
    return rr.closure_fingerprint(rr._code_files(rr.CODE_REQUIRED, str(api_dir)), _revision_files(rdir))


def test_m2_a_loaded_revision_binds_every_file_of_its_closure(tmp_path):
    rdir, _ = _built(tmp_path)
    rs = rr.load_dir(rdir)
    with open(os.path.join(rdir, "rules.json"), encoding="utf-8") as f:
        doc = json.load(f)
    assert doc["closure"] == {"code": sorted(rr.CODE_REQUIRED), "fp": rr.code_fingerprint()}
    assert rs.code_fp == rr.code_fingerprint()
    revision = _revision_files(rdir)
    assert rs.closure_files == len(rr.CODE_REQUIRED) + len(revision) - 1   # REVISION is the seal
    assert rs.closure_fp == rr.closure_fingerprint(rr._code_files(rr.CODE_REQUIRED), revision)
    assert rr.review_eval() == rr.code_fingerprint()[: rm.CONTRACT_BOUNDS["eval_hex"]]


# Each change is to a file IN the closure; none is reached by a static call
# graph from a bound entry's own body.
M2_CLOSURE_CHANGES = [
    ("dynamic_method", "review_rules.py",
     '        return [r for r in self.rules if r.scope == "game"]\n',
     '        return [r for r in self.rules if r.scope == "game"][::-1]\n'),
    ("budget_tick", "review_rules.py", "        self.left -= 1\n", "        self.left -= 0\n"),
    ("module_constant", "review_measures.py", "WINDOW_KINDS = (0, 2, 3)\n", "WINDOW_KINDS = (0, 2)\n"),
    ("sql_template", "review_measures.py", "review_sitting_dirty", "review_sitting_dirty "),
    ("unreferenced_code", "review_measures.py", "SEATS = 2      # the two seats of a game\n",
     "SEATS = 2      # the two seats of a game\n\n\ndef _never_called():\n    return None\n"),
    ("comment_only", "review_measures.py", "# -- registration helpers",
     "# a comment\n# -- registration helpers"),
]


@pytest.mark.parametrize("change", M2_CLOSURE_CHANGES, ids=[c[0] for c in M2_CLOSURE_CHANGES])
def test_m2_any_change_to_a_closure_code_file_moves_the_fingerprint(tmp_path, change):
    rdir, _ = _built(tmp_path)
    same = _api_copy(tmp_path, "same")
    base = _closure(same, rdir)
    assert base == rr.load_dir(rdir).closure_fp                  # control: the copy IS the code
    name, fname, old, new = change
    d = _api_copy(tmp_path, name)
    if name == "sql_template":
        src = (d / fname).read_bytes()
        assert src.count(old.encode()) >= 1
        (d / fname).write_bytes(src.replace(old.encode(), new.encode(), 1))
    else:
        _change(d / fname, old, new)
    assert _closure(d, rdir) != base
    assert rr.code_fingerprint(api_dir=str(d)) != rr.code_fingerprint(api_dir=str(same))


def test_m2_a_template_and_an_unreferenced_file_of_the_revision_move_it(tmp_path):
    rdir, _ = _built(tmp_path)
    same = _api_copy(tmp_path, "same")
    base = _closure(same, rdir)
    # a rule's line template
    doc = copy.deepcopy(tk.synthetic_doc())
    doc["rules"][0]["line"] = doc["rules"][0]["line"] + " "
    r2, _ = _built(tmp_path, doc, name="template")
    # an unreferenced data table
    r3 = os.path.join(str(tmp_path), "unref", os.path.basename(rdir))
    shutil.copytree(rdir, r3)
    os.mkdir(os.path.join(r3, "data"))
    with open(os.path.join(r3, "data", "never_named.txt"), "w", encoding="utf-8") as f:
        f.write("x\n")
    r3, _ = tk.reseal(r3)
    assert rr.load_dir(r3).closure_files == rr.load_dir(rdir).closure_files + 1
    fps = {base, _closure(same, r2), _closure(same, r3)}
    assert len(fps) == 3


def test_m2_control_a_file_outside_the_closure_and_line_endings_do_not_move_it(tmp_path):
    rdir, _ = _built(tmp_path)
    same = _api_copy(tmp_path, "same", extra=("seat_evidence.py",))
    base = _closure(same, rdir)
    d = _api_copy(tmp_path, "outside", extra=("seat_evidence.py",))
    _change(d / "seat_evidence.py", "import json\n", "import json  # outside the closure\n")
    assert _closure(d, rdir) == base
    e = _api_copy(tmp_path, "eol")
    for m in rr.CODE_REQUIRED:
        raw = (e / m).read_bytes().replace(b"\r\n", b"\n")
        (e / m).write_bytes(raw.replace(b"\n", b"\r\n") if b"\r\n" not in (same / m).read_bytes() else raw)
    assert _closure(e, rdir) == base


def test_m2_a_revision_naming_too_few_code_files_or_a_bad_name_is_malformed(tmp_path):
    for i, closure in enumerate(({"code": ["review_rules.py"], "fp": rr.code_fingerprint()},
                    {"code": ["../review_rules.py", "review_measures.py"], "fp": "0" * 64},
                    {"code": sorted(rr.CODE_REQUIRED), "fp": "zz"},
                    {"code": sorted(rr.CODE_REQUIRED)})):
        rdir, _ = _built(tmp_path, name="c" + str(i))
        p = os.path.join(rdir, "rules.json")
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        doc["closure"] = closure
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        new, _ = tk.reseal(rdir)
        with pytest.raises(rr.Refused) as e:
            rr.load_dir(new)
        assert (e.value.cls, str(e.value)) == ("malformed", "malformed: closure"), closure


def test_review_eval_is_the_code_digest_and_moves_with_a_code_byte(tmp_path, monkeypatch):
    base = rr.review_eval()
    assert len(base) == rm.CONTRACT_BOUNDS["eval_hex"]
    real = rr._code_files

    def changed(names, api_dir=None):
        files = real(names, api_dir)
        files["code/review_rules.py"] += b"#"
        return files
    monkeypatch.setattr(rr, "_code_files", changed)
    assert rr.review_eval() != base


# -- evaluation ---------------------------------------------------------------------------

def _rs(tmp_path):
    rdir, _ = _built(tmp_path)
    return rr.load_dir(rdir)


def test_a7_a_two_seat_rule_and_its_negation_on_a_one_sided_game(tmp_path):
    rs = _rs(tmp_path)
    ra = tk.rec(dec=[40, 2])
    two = tk.game(ra)
    _f, fired, _ = rs.evaluate_game(two, tk.MATCH, tk.registry_of(two))
    assert fired.count(tk.ID_GAP) == 1
    one = tk.game(tk.rec(dec=[40, 2]), one_sided=True)
    _f, fired, errors = rs.evaluate_game(one, tk.MATCH, tk.registry_of(one))
    assert tk.ID_GAP not in fired and tk.ID_NOT_GAP not in fired and errors == 0


def test_kleene_only_true_fires():
    class Op:
        impl = (lambda a: a,)
    t, f, u = ("op", Op, [("v", True)]), ("op", Op, [("v", False)]), ("op", Op, [("v", None)])

    def ev(node):
        return rr.eval_pred(node, None, {}, None, None)
    assert ev(("all", [t, u])) is None and ev(("all", [f, u])) is False
    assert ev(("any", [f, u])) is None and ev(("any", [t, u])) is True
    assert ev(("not", u)) is None and ev(("not", f)) is True


def test_a_rule_that_raises_is_counted_and_stops_no_other(tmp_path):
    doc = tk.synthetic_doc()
    doc["rules"].insert(0, {"id": "r0000a0ee", "scope": "game", "subject": "seat",
                            "effect": "flag", "post": False, "post_since": None,
                            "when": tk.cmp(tk.M("seat.build_version"), "gt", tk.V(1)),
                            "show": [["seat", "seat.index"]], "line": "x {seat}"})
    # a revision carrying it could not pass its own self-test; compile it directly
    doc["nonce"] = "0" * 32
    rs = rr.compile_rules(doc, rr._Binder({}, build=True), {})
    g = tk.game()
    _f, fired, errors = rs.evaluate_game(g, tk.MATCH, tk.registry_of(g))
    assert errors == 1 and tk.ID_NOT_GAP in fired


def test_notes_ride_on_the_flags_of_the_same_game(tmp_path):
    rs = _rs(tmp_path)
    g = tk.game(tk.rec(dec=[40, 2]), conflict=(True, False))
    f, fired, _ = rs.evaluate_game(g, tk.MATCH, tk.registry_of(g))
    assert tk.ID_NOTE in fired and tk.ID_NOTE not in {r.id for r, _d in f}
    assert all(d["notes"] == ["synthetic note seat 0"] for _r, d in f)


def test_rendering_places_none_lists_and_the_item_bound(tmp_path):
    parts = rr._compile_template("a {x} b {y:1} c {z|none} d {w}", {"x", "y", "z", "w"})
    assert rr.render_item(parts, {"x": 7, "y": 0.25, "z": None, "w": [3, 4]}) == "a 7 b 0.2 c none d 3/4"
    assert rr.render_item(parts, {"x": True, "y": 2.0, "z": 0.5, "w": "t"}) == "a 1 b 2.0 c 0.500 d t"

    class R:
        line = rr._compile_template("{x}", {"x"})
    assert rr.render_line(R, [{"x": i} for i in range(20)]).count("\n") == rr._BOUNDS["render_items_max"] - 1
    with pytest.raises(rr.Refused):
        rr._compile_template("{unknown}", {"x"})
    with pytest.raises(rr.Refused):
        rr._compile_template("a } b", {"x"})


def test_a_measure_name_this_build_lacks_is_refused_at_build_and_stale_at_load(tmp_path):
    """Choice two is absent: no private module can supply a measure. A rule
    naming one is refused when built, and a revision that names one (built
    elsewhere) is stale here; nothing is evaluated with it."""
    doc = tk.synthetic_doc()
    doc["rules"].append({"id": "r0000a0dd", "scope": "game", "subject": "seat", "effect": "flag",
                         "post": False, "post_since": None,
                         "when": tk.cmp(tk.M("module.synthetic_extra"), "gt", tk.V(-1)),
                         "show": [["seat", "seat.index"]], "line": "m {seat}"})
    with pytest.raises(rr.Refused) as e:
        tk.build_revision(tmp_path, doc, name="with-module")
    assert (e.value.cls, str(e.value)) == ("malformed", "malformed: unknown entry")
    rdir, _ = _built(tmp_path, name="plain")
    p = os.path.join(rdir, "rules.json")
    with open(p, encoding="utf-8") as f:
        built = json.load(f)
    built["rules"].append(dict(doc["rules"][-1]))
    built["vocabulary"] = sorted(built["vocabulary"] + ["module.synthetic_extra"])
    with open(p, "w", encoding="utf-8") as f:
        json.dump(built, f)
    new, _ = tk.reseal(rdir)
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(new)
    assert (e.value.cls, str(e.value)) == ("stale", "stale: unknown entry")


def test_the_sitting_statement_has_typed_binds_and_no_lateral(tmp_path):
    rs = _rs(tmp_path)
    rule = rs.rule(tk.ID_STEP)
    sql, binds = rs.sitting_statement(rule)
    assert "LATERAL" not in sql.upper()
    assert ":snap" in sql and "review_sitting_dirty" in sql
    assert binds["window_days"] == 9 and binds["post_follow"] == 1
    assert binds["lag_s"] == rm.CONTRACT_BOUNDS["ready_lag_s"]


def test_the_tuning_literal_writes_every_value_in(tmp_path):
    rdir, _ = _built(tmp_path)
    lit = rr.literal(rdir, tk.ID_STEP, 5)
    assert ":" + "window_days" not in lit and "CAST(9 AS int)" in lit
    assert "CAST(5 AS int)" in lit and "review_sitting_dirty" not in lit


def test_the_cli_validate_prints_the_verdict_and_eval(tmp_path, capsys):
    rdir, rev = _built(tmp_path)
    assert rr.cli(["validate", rdir]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["verdict: loaded", "rev: " + rev, "eval: " + rr.review_eval()]
    assert rr.cli(["validate", rdir + "x"]) == 1
    assert capsys.readouterr().out.splitlines()[0].startswith("verdict: refused (")


def test_the_build_never_overwrites_and_leaves_no_staging_behind(tmp_path):
    store, rev = tk.build_revision(tmp_path)
    left = [n for n in os.listdir(store) if n.startswith(".")]
    assert left == []
    with open(os.path.join(store, "REVISIONS.tsv"), encoding="utf-8") as f:
        assert f.read().split("\t")[0] == rev
    doc = copy.deepcopy(tk.synthetic_doc())
    doc["rules"][0]["line"] = "{nope}"
    with pytest.raises(rr.Refused):
        tk.build_revision(tmp_path, doc, name="bad")
    assert [n for n in os.listdir(store) if n.startswith(".")] == []



# -- M-2 (round 2): a loader in a fresh process over a COPY of the code --------------
# A revision is built by this (unaltered) tree, then loaded by a copy of the
# closure's code files with one change, in a fresh process. Any change to a
# file of the closure refuses the revision as stale, whatever reaches it
# (a receiver method, the work budget, a module constant, a comment); the
# unaltered copy, the same files with the other line ending, and a change to
# a file outside the closure load it.

LOAD = ("import sys; sys.path.insert(0, sys.argv[1]); import review_boot; import review_rules as rr\n"
        "try:\n    rr.load_dir(sys.argv[2]); print('loaded')\n"
        "except rr.Refused as e:\n    print('refused ' + e.cls)\n")


def _load_with_copy(tmp_path, rdir, edit=None):
    import subprocess
    d = _api_copy(tmp_path, "run-" + (edit[0] if edit else "same"), extra=("seat_evidence.py",))
    if edit:
        _name, fname, old, new = edit
        if old is None:
            raw = (d / fname).read_bytes()
            (d / fname).write_bytes(raw.replace(b"\r\n", b"\n") if b"\r\n" in raw
                                    else raw.replace(b"\n", b"\r\n"))
        else:
            _change(d / fname, old, new)
    out = subprocess.run([sys.executable, "-B", "-c", LOAD, str(d), rdir], capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip().splitlines()[-1]


M2_MUTANTS = [
    ("ctx", "review_measures.py", "        self.pair_other = self.other if self.two else None\n",
     "        self.pair_other = self.other\n"),
    ("sitting_binds", "review_measures.py", '        binds["post_follow"] = args["post_rows"] - 1\n',
     '        binds["post_follow"] = args["post_rows"]\n'),
    ("game_rules", "review_rules.py", '        return [r for r in self.rules if r.scope == "game"]\n',
     '        return [r for r in self.rules if r.scope == "game"][::-1]\n'),
    ("render_line", "review_rules.py", "        return self.core[\"core.render\"].impl[0](rule, items)\n",
     "        return self.core[\"core.render\"].impl[0](rule, items[::-1])\n"),
    ("budget_tick", "review_rules.py", "        self.left -= 1\n", "        self.left -= 0\n"),
    ("comment", "review_measures.py", "# -- registration helpers", "# a comment\n# -- registration helpers"),
    ("boot", "review_boot.py", "LOADED = {}", "LOADED = dict()"),
]
M2_CONTROLS = [
    ("line_endings", "review_measures.py", None, None),
    ("outside", "seat_evidence.py", "import json\n", "import json  # outside the closure\n"),
]


@pytest.mark.parametrize("edit", M2_MUTANTS, ids=[m[0] for m in M2_MUTANTS])
def test_m2_any_change_to_a_closure_file_is_stale(tmp_path, edit):
    rdir, _ = _built(tmp_path)
    assert _load_with_copy(tmp_path, rdir) == "loaded"            # the unaltered copy
    assert _load_with_copy(tmp_path, rdir, edit) == "refused stale"


@pytest.mark.parametrize("edit", M2_CONTROLS, ids=[m[0] for m in M2_CONTROLS])
def test_m2_control_line_endings_or_a_file_outside_the_closure_still_load(tmp_path, edit):
    rdir, _ = _built(tmp_path)
    assert _load_with_copy(tmp_path, rdir, edit) == "loaded"


def test_m2_the_sitting_bindings_are_in_the_self_test_path(tmp_path, monkeypatch):
    """A bind builder that disagrees with the statement it serves refuses the
    revision at load (the sitting self-test), before any pass reads it."""
    rdir, _ = _built(tmp_path)
    rr.load_dir(rdir)                                             # control
    real = rm.sitting_binds

    def short(entry, args):
        b = dict(real(entry, args))
        b.pop("lag_s")
        return b
    monkeypatch.setattr(rm, "sitting_binds", short)
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(rdir)
    assert (e.value.cls, str(e.value)) == ("selftest", "selftest: sitting binds")


# -- L-3: incremental enumeration and verified reads ------------------------------

def test_l3_enumeration_is_incremental_under_the_count_cap(tmp_path, monkeypatch):
    rdir, _ = _built(tmp_path)
    data = os.path.join(rdir, "data")
    os.mkdir(data)
    n = rr._BOUNDS["files_max"] * 4
    for i in range(n):
        with open(os.path.join(data, "t_" + chr(97 + i % 26) * (1 + i // 26) + ".txt"), "w") as f:
            f.write("x")
    pulled = {"n": 0}
    real = os.scandir

    class Counting:
        def __init__(self, path):
            self.it = real(path)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.it.close()

        def __iter__(self):
            for ent in self.it:
                pulled["n"] += 1
                yield ent
    monkeypatch.setattr(rr.os, "scandir", Counting)
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(rdir)
    assert str(e.value) == "inventory: file count"
    # never listed whole: at most the cap (plus the few top-level entries)
    assert pulled["n"] <= rr._BOUNDS["files_max"] + 5 < n


@pytest.mark.parametrize("how", ["replaced", "grown"])
def test_l3_a_file_changed_between_admission_and_read_is_refused(tmp_path, monkeypatch, how):
    rdir, rev = _built(tmp_path)
    assert rr.load_dir(rdir).rev == rev                           # control
    real = rr._read_verified

    def swap(path, ident, size, cap):
        if path.endswith("rules.json"):
            if how == "replaced":
                with open(path, "rb") as f:
                    raw = f.read()
                tmp = path + ".new"
                with open(tmp, "wb") as f:
                    f.write(raw)
                os.replace(tmp, path)                             # same bytes, another file
            else:
                with open(path, "ab") as f:
                    f.write(b" ")
        return real(path, ident, size, cap)
    monkeypatch.setattr(rr, "_read_verified", swap)
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(rdir)
    assert e.value.cls == "inventory" and "changed" in str(e.value)


# -- round 2 L3: every platform reads through a NON-FOLLOWING handle ---------------
# POSIX: O_NOFOLLOW | O_NONBLOCK. Windows: CreateFileW with
# FILE_FLAG_OPEN_REPARSE_POINT, the final path of the handle verified. Any
# platform without such an open refuses activation (class `platform`).

def _planned(path):
    st = os.lstat(path)
    return (st.st_dev, st.st_ino), st.st_size


def _junction(target, link):
    """A directory junction (Windows; no privilege needed) or a directory
    symbolic link (POSIX)."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(target, link)
    else:
        os.symlink(target, link, target_is_directory=True)


def test_l3_control_a_plain_file_reads(tmp_path):
    p = tmp_path / "plain.txt"
    p.write_bytes(b"abc")
    ident, size = _planned(str(p))
    assert rr._read_verified(str(p), ident, size, 64) == b"abc"


def test_l3_a_substituted_directory_on_the_way_is_refused(tmp_path):
    """The planned path reaches the same file through a junction (Windows) or
    a directory link (POSIX): the read is refused, never served."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "a.txt").write_bytes(b"abc")
    _junction(str(real), str(tmp_path / "via"))
    p = str(tmp_path / "via" / "a.txt")
    ident, size = _planned(p)
    if os.name == "nt":
        with pytest.raises(rr.Refused) as e:
            rr._read_verified(p, ident, size, 64)
        assert str(e.value) == "inventory: final path"
    else:
        pytest.skip("POSIX: O_NOFOLLOW guards the last component; a linked directory "
                    "inside a revision is refused by the inventory (the next test)")


def test_l3_a_junction_or_link_as_the_data_directory_is_refused(tmp_path):
    rdir, rev = _built(tmp_path)
    assert rr.load_dir(rdir).rev == rev                            # control
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "t.txt").write_text("x", encoding="utf-8")
    _junction(str(elsewhere), os.path.join(rdir, "data"))
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(rdir)
    assert str(e.value) == "inventory: link"


def test_l3_a_file_link_is_refused_where_the_platform_allows_one(tmp_path):
    p = tmp_path / "target.txt"
    p.write_bytes(b"abc")
    link = tmp_path / "link.txt"
    try:
        os.symlink(str(p), str(link))
    except OSError:
        pytest.skip("this seat may not create a file symbolic link; the refusal test covers it")
    st = os.stat(str(link))                     # planned as the TARGET's identity
    with pytest.raises(rr.Refused):
        rr._read_verified(str(link), (st.st_dev, st.st_ino), st.st_size, 64)


@pytest.mark.skipif(os.name != "posix", reason="a FIFO is a POSIX object")
def test_l3_a_fifo_never_blocks_the_open_and_is_refused(tmp_path):
    p = str(tmp_path / "fifo")
    os.mkfifo(p)
    ident, size = _planned(p)
    with pytest.raises(rr.Refused) as e:
        rr._read_verified(p, ident, size, 64)
    assert e.value.cls == "inventory"


def test_l3_without_a_non_following_open_activation_refuses_by_name(tmp_path, monkeypatch):
    rdir, rev = _built(tmp_path)
    assert rr.load_dir(rdir).rev == rev                            # control
    if os.name == "nt":
        monkeypatch.setattr(rr, "_K32", None)
    else:
        monkeypatch.setattr(rr.os, "name", "other")
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(rdir)
    assert (e.value.cls, str(e.value)) == ("platform", "platform: no non-following open on this platform")


def test_l3_the_pointer_file_is_read_through_the_same_handle(fresh, tmp_path, monkeypatch):
    """The pointer and the revision's files are each read through the
    non-following open, on the path refresh_rules takes."""
    rdir, rev = _built(tmp_path)
    _into_root(fresh, rdir)
    tk.point(fresh, "rules-" + rev)
    seen = []
    real = rr._open_nofollow

    def spy(path):
        seen.append(os.path.basename(path))
        return real(path)
    monkeypatch.setattr(rr, "_open_nofollow", spy)
    assert rr.refresh_rules().word == rev
    assert seen[0] == rr.POINTER and "rules.json" in seen and "selftest.json" in seen


# -- L-4: refusal logging carries the target identity ------------------------------

def test_l4_two_different_refused_revisions_of_one_class_log_twice(fresh, tmp_path, capsys):
    names = []
    for tag in ("one", "two"):
        rdir, _ = _built(tmp_path, name=tag)
        with open(os.path.join(rdir, "rules.json"), "w") as f:
            f.write("{not json " + tag)
        new, rev = tk.reseal(rdir)
        _into_root(fresh, new)
        names.append("rules-" + rev)
    tk.point(fresh, names[0])
    rr.refresh_rules()
    rr.refresh_rules()
    tk.point(fresh, names[1])
    rr.refresh_rules()
    out = capsys.readouterr().out
    assert out.count("[REVIEW] rules: refused (malformed)") == 2, out
    assert rr.health_word() == "refused"
    assert not any(n[len("rules-"):] in out for n in names)        # no identity in the log line


# -- L-5 / L-6: the admin comparison after the purge, and the one-sided game --------

def test_l5_after_the_purge_aggregates_and_availability_are_always_rendered():
    g = tk.game()
    for r in g:
        for k in rm.LIST_KEYS:
            r["rec"].pop(k, None)
    v = rm.game_view(g, tk.MATCH, tk.registry_of(g), None)
    assert v["lists"] == "purged" and v["evidence"] == "two_records"
    assert len(v["aggregates"]) == 2 and all("rtt" in a for a in v["aggregates"])
    assert v["drift"] is not None
    assert v["unavailable"] == list(rm.UNAVAILABLE_PURGED)
    full = rm.game_view(tk.game(), tk.MATCH, tk.registry_of(tk.game()), None)   # control
    assert full["lists"] == "present" and full["unavailable"] == []


def test_l6_a_one_sided_game_states_the_old_seat_build_as_unknown():
    g = tk.game(one_sided=True)
    v = rm.game_view(g, tk.MATCH, tk.registry_of(g), None)
    assert v["evidence"] == "one_sided_legacy"
    line = [u for u in v["unavailable"] if u.startswith("old_seat_build_statement")]
    assert line and "unknown" in line[0] and "identifies no build" in line[0]
