"""Fix pass 5 (build round 5, M4 and M5) for the private-needle check and the
path-query enumeration, against SYNTHETIC stores and fixtures only:

  * M4(a): the value derivation is exhaustive over the rules SCHEMA. The walk
    below takes its positions from the evaluator's own registry (every
    parameter family's keys, every argument of every operator and sitting
    entry) plus the data tables, plants every JSON value of a fixed universe
    at each, keeps what the compiler admits, and asserts a needle for every
    admitted leaf: beside its key always, bare too for a long string or a
    number of a deciding magnitude. Every derivation type is exercised and
    each value's type is checked against an independent classification; a
    value the derivation cannot classify, or a position the schema does not
    have, is the exit-3 refusal.
  * M4(b): every directory read is ONE snapshot that represents every entry:
    a junction, a symbolic link, a device or any other entry is the exit-3
    refusal naming its path (a junction is planted for real with mklink /J;
    a symbolic link for real when the seat allows it, and as an lstat answer
    always); a tree that changes while the snapshot is taken is refused; and
    packet-verify reads the manifest and the payload from that one snapshot.
  * M5(ii): alias resolution reaches a true fixed point (a reverse-ordered
    chain longer than the old eight rounds), and bindings that never settle
    are refused, never silently partial.
  * M5(iii): an os.walk handler is credited only when the name at the call
    site can be nothing but the module-level raising function: a parameter,
    a default, a lambda parameter, a local rebinding, a nested def, an import
    alias or an except target of that name is detected; a raise whose
    construction can fail, a finally that returns and a suppressing with are
    refused too."""

import hashlib
import json
import math
import os
import stat
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import review_measures as rm  # noqa: E402
import review_needles as rn  # noqa: E402
import review_rules as rr  # noqa: E402
import review_testkit as tk  # noqa: E402
import test_review_needles_r3 as r3  # noqa: E402
from test_review_needles_r3 import armed, shapes_store  # noqa: E402,F401  -- fixtures

# -- M4(a): the schema walk ------------------------------------------------------------

# Every JSON value kind a deciding position could hold: numbers on both sides
# of the bare magnitude, 0, 1 and -1, fractions, Booleans, null, strings on
# both sides of the bare length (the empty string included), lists of each
# and an object, and a relation name (a relation position admits nothing
# else). The compiler decides which of them a position admits.
#
# Planted values are made at run time (round 7 recut). Each is a synthetic
# token of this file's own seed SEED: a hash of the seed and a tag shaped to
# its kind, or, in the sitting templates, the visible prefix TEMPLATE_PREFIX
# plus a counter. No line of this file writes a planted value and no line
# holds a key beside one, so no scan of the source can match a planted form.
# Only the kind boundaries are written: 0, 1 and -1, the Booleans, null, the
# empty string and the relation name.
SEED = "test_review_needles_r5"


def _hash(tag):
    return int(hashlib.sha256(("%s %s" % (SEED, tag)).encode("ascii")).hexdigest(), 16)


def _letters(tag, n):
    """n lower-case letters of the hash of SEED and tag."""
    h, out = _hash(tag), []
    for _i in range(n):
        h, r = divmod(h, 26)
        out.append(chr(ord("a") + r))
    return "".join(out)


SMALL = 2 + _hash("small") % 4                  # under the bare magnitude
SMALL_B = 6 + _hash("small b") % 4              # under it too, above SMALL
BIG = 6000 + _hash("big") % 900                 # of the bare magnitude
FRACTION = (11 + _hash("fraction") % 88) / 100.0
NEGATIVE = -(2 + _hash("negative") % 7) - 0.5
SHORT = _letters("short", 2)                    # under the bare length
LONG = "pv" + _letters("long", 8)               # of the bare length
UNIVERSE = [0, 1, -1, SMALL, BIG, FRACTION, NEGATIVE, True, False, None, "", SHORT, "gt", LONG,
            [SMALL_B, BIG], [SHORT, LONG], [True], [None], [], {"k": SMALL_B}]
TEXT_TOKENS = [0, SMALL, BIG, FRACTION, SHORT, LONG]
MEASURE = "seat.published_hits"
KEY = "published_hits"
RULE_GAME, RULE_SIT = "r0000f5a1", "r0000f5a2"
# one valid argument set per sitting entry of the registry (the walk plants
# into each argument in turn); a sitting entry without one fails the walk.
# Only the vocabulary NAMES of each entry are written here (side, row,
# reporter, filters: public by construction; the population and the stratify
# measure are taken from the registry at run time: its first population, and
# its first side measure that is neither the trials nor the successes); every
# VALUE argument is made by _template, in registry order, from its kind.
POPULATION = min(n for n, e in rm.REGISTRY.items() if e.kind == "population")
STRATIFY = min(n for n, e in rm.REGISTRY.items()
               if e.kind == "side" and n not in ("side.shots_fired", "side.shots_hit"))
SITTING_NAMES = {
    "sitting.rate_vs_own": {"num": "side.shots_hit", "den": "side.shots_fired", "filters": [POPULATION]},
    "sitting.binomial_vs_own": {"trials": "side.shots_fired", "successes": "side.shots_hit",
                                "stratify": STRATIFY, "filters": [POPULATION]},
    "sitting.step_ratio": {"num": "reporter.observed_batches", "den": "row.duration_s",
                           "filters": [POPULATION]},
}
TEMPLATE_PREFIX = 5200


def _shaped(kind, v, tag):
    """v (TEMPLATE_PREFIX plus a counter) shaped to one argument kind."""
    if kind == "int":
        return v
    if kind == "num":
        return v + 0.5
    if kind == "edges":
        return [v, v + 0.25, v + 0.5]
    if kind == "label":
        return "pv" + _letters(tag, 6)
    raise AssertionError(kind)


def _template(name, start):
    """The argument set of one sitting entry, in registry order: each name as
    written above, each value argument the next counter shaped to its kind."""
    names, args, n = SITTING_NAMES[name], {}, start
    for arg, kind in rm.REGISTRY[name].args:
        if arg in names:
            args[arg] = names[arg]
            continue
        n += 1
        args[arg] = _shaped(kind, TEMPLATE_PREFIX + n, name + " " + arg)
    return args


SITTING_TEMPLATES = {name: _template(name, 20 * i) for i, name in enumerate(sorted(SITTING_NAMES))}
NAME_KINDS = {"side", "row", "reporter", "filters"}       # vocabulary names: public by construction
VALUE_KINDS = {"expr", "rel", "list", "int", "num", "edges", "label"}


def _leaves(x):
    """Every scalar of a JSON value, object keys included, by an independent walk."""
    if isinstance(x, list):
        return [y for m in x for y in _leaves(m)]
    if isinstance(x, dict):
        return [y for k, v in x.items() for y in [k] + _leaves(v)]
    return [x]


def _expect_type(v):
    """The derivation type of a value, classified independently of the tool."""
    if v is True or v is False:
        return "bool"
    if v is None:
        return "null"
    if isinstance(v, str):
        return "string" if len(v) >= rn.STR_MIN_BARE else "short_string"
    if v != int(v) or abs(v) >= rn.VALUE_MIN_BARE:
        return "number"
    return "small_number"


def _render(v):
    if v is True or v is False:
        return "true" if v else "false"
    if v is None:
        return "null"
    if v == "":
        return '""'
    return str(v)


def _base_doc():
    doc = tk.synthetic_doc()
    doc["rules"] = []
    return doc


def _game_rule(pred):
    return {"id": RULE_GAME, "scope": "game", "subject": "seat", "effect": "flag", "post": False,
            "post_since": None, "when": pred, "show": [["seat", "seat.index"]], "line": "fix five {seat}"}


def _sitting_rule(op, args):
    return {"id": RULE_SIT, "scope": "sitting", "effect": "flag", "post": False, "post_since": None,
            "sitting": {"op": op, "args": args}, "show": [["d", "d"]], "line": "fix five sitting {d}"}


def _positions():
    """(label, place(x) -> (doc, json tables, text tables) or None, context key)
    for every deciding position of the schema, from the registry."""
    out = []
    entries = rm.REGISTRY.values()
    for e in sorted((e for e in entries if e.kind == "params"), key=lambda e: e.name):
        for k in sorted(e.data):
            def place(x, fam=e.name, k=k, keyed=bool(e.args)):
                doc = _base_doc()
                values = doc["measure_params"][fam]
                if keyed:       # one value set per deal profile (card_measures PROFILE_KEYED)
                    values = values[tk.PROFILE]
                values[k] = x
                doc["rules"] = [_game_rule(tk.cmp(tk.M(MEASURE), "gt", tk.M(MEASURE)))]
                return doc, {}, {}
            out.append(("param %s.%s" % (e.name, k), place, k))
    for e in sorted((e for e in entries if e.kind == "operator"), key=lambda e: e.name):
        names = [a for a, _k in e.args]
        exprs = [a for a, k in e.args if k == "expr"]
        tail = e.name.rsplit(".", 1)[-1]
        for arg, kind in e.args:
            others_read = any(a != arg for a in exprs)
            forms = {"expr": [("literal", lambda x: {"v": x}),
                              ("nested", lambda x: {"add": [tk.M(MEASURE), {"v": x}]}),
                              ("abs", lambda x: {"abs": {"v": x}})],
                     "rel": [("relation", lambda x: x)],
                     "list": [("list", lambda x: x if isinstance(x, list) else [x, BIG + 1])]}[kind]
            for form, wrap in forms:
                # a literal is keyed by the measures its predicate reads; with
                # none, by the operator's own name
                key = KEY if others_read or form == "nested" else tail

                def place(x, e=e, arg=arg, wrap=wrap, names=names):
                    args = {a: {"expr": tk.M(MEASURE), "rel": "gt", "list": [BIG + 2]}[k] for a, k in e.args}
                    args[arg] = wrap(x)
                    doc = _base_doc()
                    doc["rules"] = [_game_rule({"op": e.name, "args": args})]
                    return doc, {}, {}
                out.append(("operator %s.%s %s" % (e.name, arg, form), place, key))
    sittings = sorted(e.name for e in entries if e.kind == "sitting")
    assert sittings == sorted(SITTING_TEMPLATES), "a sitting entry without a template: extend the walk"
    for name in sittings:
        e = rm.REGISTRY[name]
        for arg, kind in e.args:
            assert kind in VALUE_KINDS | NAME_KINDS, kind
            if kind in NAME_KINDS:
                continue
            key = arg if len(arg) >= 3 else name.rsplit(".", 1)[-1]

            def place(x, name=name, arg=arg):
                args = dict(SITTING_TEMPLATES[name])
                args[arg] = x
                doc = _base_doc()
                doc["rules"] = [_sitting_rule(name, args)]
                return doc, {}, {}
            out.append(("sitting %s.%s" % (name, arg), place, key))

    def json_value(x):
        doc = _base_doc()
        doc["rules"] = [_game_rule({"op": "op.in_set", "args": {"a": tk.M(MEASURE), "set": {"data": "f5_json"}}})]
        return doc, {"f5_json.json": {"rows": [x]}}, {}
    out.append(("data json value", json_value, "rows"))

    def json_key(x):
        if not isinstance(x, str):
            return None                         # a JSON object key is a string
        doc = _base_doc()
        doc["rules"] = [_game_rule({"op": "op.in_set", "args": {"a": tk.M(MEASURE), "set": {"data": "f5_json"}}})]
        return doc, {"f5_json.json": {x: [SMALL]}}, {}
    out.append(("data json key", json_key, "f5_json"))
    return out


def _legal(doc, json_tables, text_tables):
    """The document as the build would store it, or None when the compiler refuses it."""
    d = json.loads(json.dumps(doc))
    d["nonce"] = "0" * (rr._BOUNDS["nonce_bytes"] * 2)
    d["vocabulary"] = []
    d["closure"] = {}
    data = {n.rsplit(".", 1)[0]: t for n, t in json_tables.items()}
    data.update({n.rsplit(".", 1)[0]: [ln for ln in t.splitlines() if ln.strip()] for n, t in text_tables.items()})
    binder = rr._Binder(None, build=True)
    try:
        rr.compile_rules(d, binder, data)
    except rr.Refused:
        return None
    d["vocabulary"] = sorted(binder.used)
    return d


def _store(tmp, doc, json_tables=None, text_tables=None):
    store = str(tmp)
    rdir = os.path.join(store, "rules-" + hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:12])
    os.makedirs(os.path.join(rdir, "data"))
    with open(os.path.join(rdir, "rules.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(doc))
    for n, t in (json_tables or {}).items():
        with open(os.path.join(rdir, "data", n), "w", encoding="utf-8") as f:
            f.write(json.dumps(t))
    for n, t in (text_tables or {}).items():
        with open(os.path.join(rdir, "data", n), "w", encoding="utf-8") as f:
            f.write(t)
    return store


def _hit(text, needles):
    return bool(rn.count(text, needles).get("value"))


def _assert_derived(v, key, needles, where):
    """One admitted leaf: classified as the independent classification says,
    found beside its key, and bare when its type is a bare one."""
    t = _expect_type(v)
    assert rn.leaf_type(v) == t, (where, v)
    prose = key.replace("_", " ")
    assert _hit("%s is %s here" % (prose, _render(v)), needles), (where, v, "beside its key")
    assert _hit("%s then %s" % (_render(v), prose), needles), (where, v, "key after it")
    if t == "number":
        assert _hit("the review used a threshold of %s for it" % _render(v), needles), (where, v, "bare")
    if t == "string":
        assert _hit("plain %s here" % v, needles), (where, v, "bare")
    return t


def test_m4_fix5_every_schema_position_derives_a_needle_for_every_admitted_leaf(tmp_path):
    exercised, admitted = set(), 0
    for i, (label, place, key) in enumerate(_positions()):
        here = 0
        for j, x in enumerate(UNIVERSE):
            placed = place(x)
            if placed is None:
                continue
            doc = _legal(*placed)
            if doc is None:
                continue                                  # the schema does not admit x here
            admitted += 1
            here += 1
            needles = rn.derive(_store(tmp_path / ("s%d_%d" % (i, j)), doc, placed[1], placed[2]))
            for v in _leaves(x):
                exercised.add(_assert_derived(v, key, needles, label))
            assert not _hit("%s is 98765 here" % key.replace("_", " "), needles), (label, "control")
        assert here, (label, "the position admits no value of the universe: the walk does not reach it")
    # text tables: every token of every line the compiler admits
    texts = 0
    for j, x in enumerate(TEXT_TOKENS):
        doc = _base_doc()
        doc["rules"] = [_game_rule({"op": "op.in_set", "args": {"a": tk.M(MEASURE), "set": {"data": "f5_text"}}})]
        text = {"f5_text.txt": "%s\n" % _render(x)}
        legal = _legal(doc, {}, text)
        if legal is None:
            continue
        texts += 1
        needles = rn.derive(_store(tmp_path / ("t%d" % j), legal, {}, text))
        exercised.add(_assert_derived(x, "f5_text", needles, "data text token"))
    assert admitted >= 100 and texts, (admitted, texts)
    want = {_expect_type(v) for x in UNIVERSE + TEXT_TOKENS for v in _leaves(x)}
    assert exercised == want == set(rn.LEAF_TYPES), (exercised, want, sorted(rn.LEAF_TYPES))


def test_m4_fix5_every_operator_and_sitting_argument_kind_is_walked():
    kinds = {k for e in rm.REGISTRY.values() if e.kind in ("operator", "sitting") for _a, k in e.args}
    assert kinds <= VALUE_KINDS | NAME_KINDS, kinds - VALUE_KINDS - NAME_KINDS
    walked = {lab.split(" ")[0] for lab, _p, _k in _positions()}
    assert walked == {"param", "operator", "sitting", "data"}


def _refusal(tmp_path, doc, capsys, monkeypatch, tables=None):
    store = _store(tmp_path / "store", doc, tables)
    monkeypatch.setenv(rn.STORE_ENV, store)
    d = tmp_path / "clean"
    d.mkdir()
    (d / "a.txt").write_text("public\n")
    code = rn.main(["scan-dir", str(d)])
    return code, capsys.readouterr().out


def _legal_base():
    doc = _base_doc()
    doc["rules"] = [_game_rule(tk.cmp(tk.M(MEASURE), "gt", {"v": BIG}))]
    return doc


REFUSED = [
    ("non_finite_parameter", lambda d: d["measure_params"]["params.age_sum"].update(budget_slack_ms=float("nan"))),
    ("infinite_literal", lambda d: d["rules"][0]["when"]["args"].update(b={"v": float("inf")})),
    ("object_literal", lambda d: d["rules"][0]["when"]["args"].update(b={"v": {"k": 1}})),
    ("object_inside_a_list_literal", lambda d: d["rules"][0]["when"]["args"].update(b={"v": [BIG, {"k": 1}]})),
    ("object_as_a_sitting_argument_member", lambda d: d["rules"].append(
        _sitting_rule("sitting.step_ratio", dict(SITTING_TEMPLATES["sitting.step_ratio"], low=[{"k": SMALL}])))),
    ("unknown_top_level_key", lambda d: d.update(extra=1)),
    ("unknown_rule_key", lambda d: d["rules"][0].update(extra=1)),
    ("unknown_predicate_form", lambda d: d["rules"][0].update(when={"xor": []})),
    ("unknown_expression_form", lambda d: d["rules"][0]["when"]["args"].update(b={"mul": [1, 2]})),
    ("contextual_value_without_a_key", lambda d: d["rules"][0].update(
        when={"op": "op.xy", "args": {"a": {"v": True}}})),
    ("metadata_of_the_wrong_type", lambda d: d["rules"][0].update(post=1)),
]


@pytest.mark.parametrize("name,edit", REFUSED, ids=[r[0] for r in REFUSED])
def test_m4_fix5_a_value_or_position_the_derivation_cannot_classify_refuses(tmp_path, capsys, monkeypatch,
                                                                             name, edit):
    ok = _legal(_legal_base(), {}, {})
    code, out = _refusal(tmp_path / "control", ok, capsys, monkeypatch)
    assert code == 0, out                                               # control: the legal document
    bad = json.loads(json.dumps(ok))
    edit(bad)
    code, out = _refusal(tmp_path / "planted", bad, capsys, monkeypatch)
    assert code == 3 and "no verdict" in out, (name, out)


def test_m4_fix5_rule_metadata_is_classified_and_its_rule_is_the_needle(armed):
    """Rule metadata carries no value needle (RULE_META): `post ... false`
    is format text in every public document; the rule's id and wording are
    its needles."""
    needles = rn.derive(armed[0])
    assert not _hit('"post": false, "effect": "flag"', needles)
    assert rn.count("rule %s posts" % r3.ID_SHAPES, needles).get("rule_id")


# -- M4(b): one snapshot that represents every entry ---------------------------------------

def _junction(link, target):
    if os.name != "nt":
        pytest.skip("mklink /J is a Windows junction; this seat is not Windows")
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
    if r.returncode != 0:
        pytest.skip("this seat refused to create a directory junction (mklink /J exit %d)" % r.returncode)


def _corpus(tmp_path):
    d = tmp_path / "corpus"
    (d / "sub").mkdir(parents=True)
    (d / "a.txt").write_text("public\n")
    (d / "sub" / "b.txt").write_text("inner\n")
    return d


def test_m4b_fix5_a_planted_junction_is_refused_by_every_reader(armed, tmp_path, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "hidden.txt").write_text("threshold of %d\n" % r3.SHAPES["edges"])
    # scan-dir
    d = _corpus(tmp_path / "scan")
    assert rn.main(["scan-dir", str(d)]) == 0                             # control
    _junction(d / "sub" / "j", outside)
    try:
        assert rn.main(["scan-dir", str(d)]) == 3
        assert ": sub/j)" in capsys.readouterr().out.splitlines()[-1]       # the path is named
    finally:
        os.rmdir(d / "sub" / "j")
    # packet-verify
    repo, base = r3._repo(tmp_path / "pk")
    allow = tmp_path / "allow.txt"
    allow.write_text("a.txt\n")
    out = tmp_path / "packet"
    assert rn.main(["packet", repo, base, str(allow), str(out)]) == 0
    digest = capsys.readouterr().out.split(" manifest ")[1].split()[0]
    assert rn.main(["packet-verify", str(out), digest]) == 0              # control
    _junction(out / "j", outside)
    try:
        assert rn.main(["packet-verify", str(out), digest]) == 3
        assert ": j)" in capsys.readouterr().out.splitlines()[-1]
    finally:
        os.rmdir(out / "j")
    # seal and seal-verify
    pin, seal, code = r3._sealed(armed, tmp_path / "seal")
    assert code == 0
    ri = os.path.join(pin, "REVIEW-INPUT")
    assert rn.main(["seal-verify", ri, seal]) == 0                        # control
    _junction(os.path.join(ri, "j"), outside)
    try:
        assert rn.main(["seal-verify", ri, seal]) == 3
        assert ": j)" in capsys.readouterr().out.splitlines()[-1]
        note = tmp_path / "note2.txt"
        note.write_text("n\n", encoding="utf-8")
        assert rn.main(["seal", pin, str(tmp_path / "M2.txt"), "T", "a", str(note),
                        str(tmp_path / "seal2.txt")]) == 3
    finally:
        os.rmdir(os.path.join(ri, "j"))


def test_m4b_fix5_a_planted_file_symlink_is_refused(armed, tmp_path, capsys):
    d = _corpus(tmp_path)
    try:
        os.symlink(str(d / "a.txt"), str(d / "link.txt"))
    except OSError as e:
        pytest.skip("this seat refuses to create a symbolic link (%s, winerror %s): the lstat test "
                    "below proves the refusal" % (type(e).__name__, getattr(e, "winerror", None)))
    assert rn.main(["scan-dir", str(d)]) == 3
    assert "link.txt" in capsys.readouterr().out.splitlines()[-1]


@pytest.mark.parametrize("kind", ["symlink", "char_device", "block_device", "fifo", "socket", "reparse_point"])
def test_m4b_fix5_every_entry_that_is_not_a_regular_file_or_directory_is_refused(armed, tmp_path, monkeypatch,
                                                                                   capsys, kind):
    """The entry as lstat reports it: each type the snapshot does not represent."""
    d = _corpus(tmp_path)
    (d / "odd").write_text("x\n")
    assert rn.main(["scan-dir", str(d)]) == 0                             # control
    real = os.lstat
    mode = {"symlink": stat.S_IFLNK, "char_device": stat.S_IFCHR, "block_device": stat.S_IFBLK,
            "fifo": stat.S_IFIFO, "socket": stat.S_IFSOCK, "reparse_point": stat.S_IFREG}[kind]

    class Fake:
        def __init__(self, st):
            self._st = st
            self.st_mode = mode | 0o644
            self.st_file_attributes = rn._REPARSE_POINT if kind == "reparse_point" else 0

        def __getattr__(self, name):
            return getattr(self._st, name)

    def lstat(p, *a, **k):
        st = real(p, *a, **k)
        return Fake(st) if os.path.basename(os.fspath(p)) == "odd" else st
    monkeypatch.setattr(rn.os, "lstat", lstat)
    assert rn.main(["scan-dir", str(d)]) == 3
    assert "odd" in capsys.readouterr().out.splitlines()[-1]


def _packet(tmp_path, capsys):
    repo, base = r3._repo(tmp_path)
    with open(os.path.join(repo, "b.txt"), "w", encoding="utf-8") as f:
        f.write("second public file\n")
    r3._git(repo, "add", "-A")
    r3._git(repo, "commit", "-q", "-m", "b")
    base = r3._git(repo, "rev-parse", "HEAD")
    allow = tmp_path / "allow.txt"
    allow.write_text("a.txt\nb.txt\n")
    out = tmp_path / "packet"
    assert rn.main(["packet", repo, base, str(allow), str(out)]) == 0
    digest = capsys.readouterr().out.split(" manifest ")[1].split()[0]
    return str(out), digest


@pytest.mark.parametrize("when", ["at_the_manifest_read", "at_a_payload_read"])
@pytest.mark.parametrize("change", ["removed", "replaced"])
def test_m4b_fix5_the_manifest_changed_while_the_snapshot_is_taken_is_refused(armed, tmp_path, monkeypatch,
                                                                                capsys, when, change):
    out, digest = _packet(tmp_path, capsys)
    assert rn.main(["packet-verify", out, digest]) == 0                   # control
    real, reads = rn._read_regular, []
    man = os.path.join(out, rn.MANIFEST)
    at = 1 if when == "at_the_manifest_read" else 2       # the manifest sorts first, a payload file next

    def hook(path, rel, want):
        raw = real(path, rel, want)
        reads.append(rel)
        if len(reads) == at:
            assert (rel == rn.MANIFEST) == (at == 1), reads
            if change == "removed":
                os.remove(man)
            else:
                with open(man + ".new", "wb") as f:
                    f.write(b"0" * 64 + b"  a.txt\n")
                os.replace(man + ".new", man)
        return raw
    monkeypatch.setattr(rn, "_read_regular", hook)
    assert rn.main(["packet-verify", out, digest]) == 3
    assert "changed while" in capsys.readouterr().out.splitlines()[-1]


@pytest.mark.parametrize("change", ["removed", "replaced"])
def test_m4b_fix5_packet_verify_reads_the_manifest_from_its_one_snapshot(armed, tmp_path, monkeypatch, capsys,
                                                                         change):
    """The manifest is never read apart from the payload: changed on disk
    BEFORE the snapshot (a reader that took the manifest first, then listed
    the payload, would have passed the pinned digest and an unlisted
    payload), the one snapshot sees the change and is refused."""
    out, digest = _packet(tmp_path, capsys)
    real, calls = rn.snapshot, []
    man = os.path.join(out, rn.MANIFEST)

    def hook(root, skip=()):
        calls.append(root)
        if change == "removed":
            os.remove(man)
        else:
            with open(man, "wb") as f:
                f.write(b"replaced\n")
        return real(root, skip)
    monkeypatch.setattr(rn, "snapshot", hook)
    assert rn.main(["packet-verify", out, digest]) == 1
    assert len(calls) == 1                                                # one snapshot, nothing else read
    assert ("manifest_missing" if change == "removed" else "manifest_digest_differs") in capsys.readouterr().out


def test_m4b_fix5_packet_verify_reads_every_file_exactly_once(armed, tmp_path, monkeypatch, capsys):
    out, digest = _packet(tmp_path, capsys)
    real, reads = rn._read_regular, []

    def hook(path, rel, want):
        reads.append(rel)
        return real(path, rel, want)
    monkeypatch.setattr(rn, "_read_regular", hook)
    assert rn.main(["packet-verify", out, digest]) == 0
    assert sorted(reads) == sorted([rn.MANIFEST, "a.txt", "b.txt"])


# -- M5(ii): alias resolution to a true fixed point -------------------------------------

def _reverse_chain(n, attr):
    """`q<n> = q<n-1>` ... `q2 = q1`, then `q1 = os.path`: each round resolves
    one more link, so the chain needs n rounds."""
    lines = ["import os"] + ["q%d = q%d" % (i, i - 1) for i in range(n, 1, -1)]
    return "\n".join(lines + ["q1 = os.path", "x = q%d.%s(p)" % (n, attr)]) + "\n"


@pytest.mark.parametrize("n", [9, 12, 40])
def test_m5_fix5_a_reverse_ordered_chain_longer_than_eight_is_resolved(n):
    assert [k for _l, k in r3.unwrapped_queries(_reverse_chain(n, "isdir"))] == ["os.path.isdir"]
    assert r3.unwrapped_queries(_reverse_chain(n, "join")) == []         # control


def test_m5_fix5_bindings_that_never_settle_are_refused_not_partial():
    with pytest.raises(r3.NoFixedPoint):
        r3.unwrapped_queries("import os\nx = os\ny = x.path\nx = y\nz = y.isdir(p)\n")


# -- M5(iii): the handler is resolved at the call site -----------------------------------
# The selftest fixture (r3.WALK_OK) is credited; each planted shape below makes
# the name at the call site something other than the module-level raising
# function, or lets an exception path end anywhere but the exit-3 refusal.
SCAN = "    return list(os.walk(p, onerror=_walk_error))\n"
SHADOWS = [
    ("parameter_shadow", ("def scan(p):", "def scan(p, _walk_error):"),
     ("        result = scan('root')\n", "        result = scan('root', print)\n")),
    ("default_argument_swallowing_lambda", ("def scan(p):", "def scan(p, _walk_error=lambda e: None):"), None),
    ("lambda_parameter", (SCAN, "    return (lambda _walk_error: list(os.walk(p, onerror=_walk_error)))(print)\n"),
     None),
    ("local_rebinding_swallowing_lambda", ("def scan(p):\n", "def scan(p):\n    _walk_error = lambda e: None\n"),
     None),
    ("local_rebinding_nested_def", ("def scan(p):\n", "def scan(p):\n    def _walk_error(e):\n        return None\n"),
     None),
    ("import_alias", ("import os\n", "import os\nfrom os import fspath as _walk_error\n"), None),
    ("except_target", ("    except NoVerdict:\n", "    except NoVerdict as _walk_error:\n"), None),
    ("raise_construction_can_fail", ("    raise NoVerdict('walk')\n", "    raise NoVerdict(e.args[3])\n"),
     None),
    ("finally_returns", (SCAN, "    try:\n    " + SCAN + "    finally:\n        return []\n"), None),
    ("suppressing_with", (SCAN, "    with contextlib.suppress(Exception):\n    " + SCAN),
     ("import os\n", "import contextlib\nimport os\n")),
    ("handler_with_a_default", ("def _walk_error(e):", "def _walk_error(e, quiet=True):"), None),
]


def test_m5_fix5_the_selftest_fixture_is_credited():
    assert r3.unwrapped_queries(r3.WALK_OK) == []


@pytest.mark.parametrize("name,edit,extra", SHADOWS, ids=[s[0] for s in SHADOWS])
def test_m5_fix5_a_shadowed_or_leaking_handler_is_not_credited(name, edit, extra):
    src = r3.WALK_OK
    for old, new in [edit] + ([extra] if extra else []):
        assert src.count(old) == 1, (name, old)
        src = src.replace(old, new)
    compile(src, name, "exec")                                            # the planted shape is real Python
    assert [k for _l, k in r3.unwrapped_queries(src)] == ["os.walk"], name
