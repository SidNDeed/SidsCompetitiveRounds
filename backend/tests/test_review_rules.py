"""The review rules loader, validator and evaluator, over SYNTHETIC revisions
(review_testkit). Bars: A3 (absent), A4 (five refusal classes, each logged
once), A5 (a resealed self-test mutant refuses; the unaltered revision loads),
A6 (re-pointing reaches a running process), A7 (a two-seat measure and its
negation on a one-sided game), the per-entry fingerprints and the bridge
(design report finding 2), the bounded inventory and work (finding 9), and
the absent-module arm of choice two."""

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
    assert rr.refresh().word == "absent" and rr.health_word() == "absent"
    assert rr.current().ruleset is None
    tk.point(fresh, rr.NONE_TARGET)
    assert rr.refresh().word == "absent"
    monkeypatch.setenv(rr.ROOT_ENV, str(tmp_path / "no-such-root"))
    assert rr.refresh().word == "absent"


def test_initial_absent_bootstrap_then_a_valid_revision_loads(fresh, tmp_path, capsys):
    assert rr.refresh().word == "absent"
    rdir, rev = _built(tmp_path)
    _into_root(fresh, rdir)
    tk.point(fresh, "rules-" + rev)
    st = rr.refresh()
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
    assert rr.refresh().word == rev1
    tk.point(fresh, "rules-" + rev2)
    assert rr.refresh().word == rev2
    assert rr.health_word() == rev2


# -- A4 / A5: five refusal classes, each logged once ----------------------------------

def _refused_once(root, target, cls, capsys):
    tk.point(root, target)
    assert rr.refresh().word == "refused" and rr.current().reason == cls
    assert rr.refresh().word == "refused"
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


def _changed_entry(name):
    """The same entry with an implementation that computes something else."""
    cur = rm.REGISTRY[name]

    def changed(ctx, p):
        return ctx.r["rec"]["imp"][1]
    return rm.Entry(cur.kind, name, (changed,), subject=cur.subject, family=cur.family), cur


def test_a4_stale_vocabulary(fresh, tmp_path, capsys, monkeypatch):
    rdir, rev = _built(tmp_path)
    _into_root(fresh, rdir)
    new, _old = _changed_entry("seat.observed_hits")
    monkeypatch.setitem(rm.REGISTRY, "seat.observed_hits", new)
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
    assert rr.refresh().word == rev


# -- finding 9: bounded inventory and work -------------------------------------------

def test_too_many_files_unexpected_entries_and_aggregate_bytes_refuse_before_parsing(tmp_path):
    rdir, _ = _built(tmp_path)
    data = os.path.join(rdir, "data")
    os.mkdir(data)
    for i in range(rr.B["files_max"] + 1):
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
    chunk = b"x" * (rr.B["data_bytes_max"] - 1)
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
    monkeypatch.setitem(rr.B, "deadline_s", -1)
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(rdir)
    assert e.value.cls == "work"


def test_the_digest_is_framed_and_injective():
    a = rr.revision_digest({"rules.json": b"ab", "selftest.json": b"c"})
    b = rr.revision_digest({"rules.json": b"a", "selftest.json": b"bc"})
    c = rr.revision_digest({"rules.jsona": b"b", "selftest.json": b"c"})
    assert len({a, b, c}) == 3
    assert rr.revision_digest({"x": b""}) != rr.revision_digest({"x": b"", "y": b""})


def test_the_vocabulary_must_be_exactly_the_entries_used(tmp_path):
    rdir, _ = _built(tmp_path)
    p = os.path.join(rdir, "rules.json")
    with open(p, encoding="utf-8") as f:
        doc = json.load(f)
    doc["vocabulary"]["seat.compat"] = rm.REGISTRY["seat.compat"].fp
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    new, _ = tk.reseal(rdir)
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(new)
    assert e.value.cls == "malformed"


# -- finding 2: fingerprints and the bridge ----------------------------------------------

def test_a_comment_or_docstring_change_keeps_the_fingerprint_and_a_body_change_moves_it():
    def one(ctx, p):
        """a docstring"""
        return ctx.i  # a comment

    def two(ctx, p):
        return ctx.i

    def three(ctx, p):
        return ctx.r

    fp = rm._fn_fp
    assert fp(one) == fp(two) != fp(three)


def test_the_bridge_keeps_an_old_revision_loading_while_both_builds_are_live(tmp_path, monkeypatch):
    r1, rev1 = _built(tmp_path, name="old")
    before = rm.review_eval()
    new, old = _changed_entry("seat.observed_hits")
    monkeypatch.setitem(rm.REGISTRY, "seat.observed_hits", new)
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(r1)
    assert e.value.cls == "stale"
    monkeypatch.setitem(rm.BRIDGE, ("seat.observed_hits", old.fp), old)
    rs1 = rr.load_dir(r1)
    # the old revision evaluates with the version it bound, not the current one
    g = tk.game(tk.rec(other_pub=[60, 45, 100, 40, 30, 25]))
    f, fired, _ = rs1.evaluate_game(g, tk.MATCH, tk.registry_of(g))
    assert tk.ID_PUB in fired
    item = next(d for r, d in f if r.id == tk.ID_PUB)["items"][0]
    assert item["observed"] == g[0]["rec"]["imp"][2]
    # a revision built on the new box binds the new version and loads there
    # (its self-test states what the new version computes on the same cases)
    doc = tk.synthetic_doc()
    doc["nonce"] = "0" * 32
    rs_new = rr.compile_rules(doc, rr._Binder({}, build=True), {})
    cases = [dict(c, fire=sorted(set(rs_new.evaluate_game(
                 c["records"], c["match"], {tuple(t) for t in c["registry"]})[1])))
             for c in tk.quiet_cases()]
    assert cases != tk.quiet_cases()            # the new version changes what fires
    r2, _rev2 = _built(tmp_path, cases=cases, name="new")
    rs2 = rr.load_dir(r2)
    assert rs2.vocabulary["seat.observed_hits"] == new.fp != old.fp
    assert rm.review_eval() != before
    # and the old box (no new version, no bridge) refuses the new revision
    monkeypatch.setitem(rm.REGISTRY, "seat.observed_hits", old)
    monkeypatch.delitem(rm.BRIDGE, ("seat.observed_hits", old.fp))
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(r2)
    assert e.value.cls == "stale"
    assert rm.review_eval() == before


def test_review_eval_covers_every_entry_and_the_bridge(monkeypatch):
    base = rm.review_eval()
    assert len(base) == rm.CONTRACT_BOUNDS["eval_hex"]
    monkeypatch.setitem(rm.BRIDGE, ("seat.compat", "f" * 64), rm.REGISTRY["seat.compat"])
    assert rm.review_eval() != base


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
    assert rr.render_line(R, [{"x": i} for i in range(20)]).count("\n") == rr.B["render_items_max"] - 1
    with pytest.raises(rr.Refused):
        rr._compile_template("{unknown}", {"x"})
    with pytest.raises(rr.Refused):
        rr._compile_template("a } b", {"x"})


def test_a_module_measure_is_unknown_without_a_module_and_nothing_else_changes(tmp_path):
    doc = tk.synthetic_doc()
    doc["vocabulary"] = {"module.synthetic_extra": "a" * 64}
    doc["rules"].append({"id": "r0000a0dd", "scope": "game", "subject": "seat", "effect": "flag",
                         "post": False, "post_since": None,
                         "when": tk.cmp(tk.M("module.synthetic_extra"), "gt", tk.V(-1)),
                         "show": [["seat", "seat.index"]], "line": "m {seat}"})
    rdir, _ = _built(tmp_path, doc)
    rs = rr.load_dir(rdir)
    g = tk.game()
    _f, fired, errors = rs.evaluate_game(g, tk.MATCH, tk.registry_of(g))
    assert "r0000a0dd" not in fired and errors == 0 and tk.ID_NOT_GAP in fired

    class Mod:
        def fingerprint(self, name):
            return "a" * 64

        def compute(self, name, ctx, params):
            return 1
    _f, fired, _ = rs.evaluate_game(g, tk.MATCH, tk.registry_of(g), module=Mod())
    assert "r0000a0dd" in fired


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
