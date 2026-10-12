"""Fix pass 3 (build round 3, M4 and M5 part a) for the private-needle check,
against a SYNTHETIC store:

  * M4(a): every legal shape of a deciding value -- a measure parameter, a
    scalar or list literal, a list argument, a data table (JSON, nested; and
    text), a sitting argument scalar or edges -- produces a value needle, and
    every value-bearing argument kind of the evaluator's own registry is
    exercised; each shape is planted in every mode (staged, range message,
    range blob, message, scan-dir, packet, seal) with a control;
  * M4(b): the seal: the manifest is written FIRST, the armed scan covers the
    complete corpus including it, and the seal (outside the corpus) refuses an
    added file, a changed byte and a removed file;
  * M5(a): every path query of review_needles.py and review_rules.py goes
    through a strict status call (an enumeration that fails on a new
    unwrapped one), and every failure that is not plain absence is the
    single exit-3 refusal.

Fix pass 4: M4(a) the value class applies to every file type in every mode
(each type the deleted classifier distinguished is planted in each mode, and
the reviewer's renamed JSON table); M4(b) seal and packet scan and digest one
byte snapshot (a change between the old phases cannot enter unscanned);
M5(b, c) the path enumeration resolves aliases and proves an os.walk
handler.

Fix pass 5 (tests in test_review_needles_r5.py): alias resolution runs to a
true fixed point (NoFixedPoint when it cannot), and the walk handler is the
name at the call site, credited only when every binding of that name in the
module is the one module-level raising function.

Fix pass 7 (tests in test_review_handler_r7.py): the handler proof resolves
every exception and suppression name through its aliases at the use site,
and treats every catcher or suppressor it cannot resolve as catching.

Fix pass 9 (tests in test_review_handler_r7.py): a manager known never to
suppress is trusted by its name, so the handler proof is refused for the
whole module whenever any operation in it could rebind such a manager, a
prefix of its dotted path, an alias of either, or the manager itself
(_manager_rebinds); the report names each such operation by file, line and
kind (Reported.rebinds). The path-query alias map keeps every binding's
value, so a name bound to two values is judged under each instead of never
settling (_aliases)."""

import ast
import builtins
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
API = os.path.join(HERE, "..", "api")
sys.path.insert(0, TOOLS)
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import review_measures as rm  # noqa: E402
import review_needles as rn  # noqa: E402
import review_rules as rr  # noqa: E402
import review_testkit as tk  # noqa: E402


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


# -- a store whose one revision holds every value shape ---------------------------
# Each shape carries distinct synthetic numbers; SHAPES maps a shape to one of
# its values (a planted text uses it) and LISTS to two adjacent members.
#
# Planted values are made at run time (round 7 recut): each is the visible
# prefix SHAPE_PREFIX plus a counter of its own (the strata label: letters of
# a hash of this file's seed SEED), and the two testkit values are read from
# tk.synthetic_doc() itself. No line of this file writes a planted value and
# no line holds a key beside one, so no scan of the source can match a planted
# form. ABSENT is a counter no shape uses: the number the controls plant and
# the store does not hold. The sitting's names are the registry's own, taken
# at run time.
SEED = "test_review_needles_r3"
SHAPE_PREFIX = 7300


def _shape(counter):
    return SHAPE_PREFIX + counter


def _letters(n):
    """n lower-case letters of the hash of SEED."""
    h, out = int(hashlib.sha256(SEED.encode("ascii")).hexdigest(), 16), []
    for _i in range(n):
        h, r = divmod(h, 26)
        out.append(chr(ord("a") + r))
    return "".join(out)


_TK = tk.synthetic_doc()


def _published_literal():
    """The literal of the testkit's published rule, as tk.synthetic_doc writes it."""
    pub = [r for r in _TK["rules"] if r["id"] == tk.ID_PUB][0]
    return pub["when"]["args"]["b"]["add"][1]["v"]


ID_SHAPES, ID_SITTING = "r0000aaa1", "r0000aaa2"
LIST_LITERAL = (_shape(1), _shape(2))
LIST_ARGUMENT = (_shape(11), _shape(12))
STRATA = (_shape(21), _shape(22), _shape(23))
STRATA_MID, STRATA_TOP = STRATA[1], STRATA[2]
SITTING_INTS = (_shape(31), _shape(32), _shape(33), _shape(34))
SITTING_NUM = _shape(35) / 100.0
JSON_ROWS = (_shape(41), _shape(42))
JSON_DEEP = _shape(43)
TEXT_ROWS = ((_shape(51),), (_shape(52), _shape(53)))
ABSENT = _shape(99)
LABEL_SIZE = 6                              # letters after the visible prefix
STRATA_LABEL = "pv" + _letters(LABEL_SIZE)
POPULATION = min(n for n, e in rm.REGISTRY.items() if e.kind == "population")
STRATIFY = min(n for n, e in rm.REGISTRY.items()
               if e.kind == "side" and n not in ("side.shots_fired", "side.shots_hit"))
SHAPES = {
    "measure_param": _TK["measure_params"]["params.case_table"]["pair_hi_ms"],   # tk.synthetic_doc
    "scalar_literal": _published_literal(),     # tk.synthetic_doc: the published rule's literal
    "list_literal": LIST_LITERAL[1],
    "list_argument": LIST_ARGUMENT[1],
    "data_json_nested": JSON_DEEP,
    "data_text": TEXT_ROWS[1][0],
    "sitting_int": SITTING_INTS[1],
    "sitting_num": SITTING_NUM,
    "edges": STRATA_MID,
}
LISTS = {"list_literal": LIST_LITERAL, "list_argument": LIST_ARGUMENT, "edges": (STRATA_MID, STRATA_TOP),
         "data_json_nested": JSON_ROWS, "data_text": TEXT_ROWS[1]}


def _sitting_args():
    """The binomial sitting's arguments in registry order: the names as
    written below, every value argument made from its kind."""
    names = {"trials": "side.shots_fired", "successes": "side.shots_hit", "stratify": STRATIFY,
             "filters": [POPULATION]}
    ints, args = iter(SITTING_INTS), {}
    for arg, kind in rm.REGISTRY["sitting.binomial_vs_own"].args:
        if arg in names:
            args[arg] = names[arg]
        elif kind == "edges":
            args[arg] = list(STRATA)
        elif kind == "label":
            args[arg] = STRATA_LABEL
        elif kind == "int":
            args[arg] = next(ints)
        elif kind == "num":
            args[arg] = SITTING_NUM
        else:
            raise AssertionError(kind)
    return args


def shapes_doc():
    doc = tk.synthetic_doc()
    doc["rules"] = [r for r in doc["rules"] if r["id"] != tk.ID_NOT_GAP]
    doc["rules"].append({
        "id": ID_SHAPES, "scope": "game", "subject": "seat", "effect": "note", "post": False,
        "post_since": None,
        "when": {"any": [
            tk.cmp(tk.M("seat.published_hits"), "eq", {"v": list(LIST_LITERAL)}),
            {"op": "op.in_set", "args": {"a": tk.M("seat.observed_hits"), "set": list(LIST_ARGUMENT)}},
            {"op": "op.in_set", "args": {"a": tk.M("seat.decided_hits"), "set": {"data": "shape_json_table"}}},
            {"op": "op.in_set", "args": {"a": tk.M("seat.decided_hits"), "set": {"data": "shape_text_table"}}}]},
        "show": [["seat", "seat.index"]], "line": "shape rule {seat}"})
    doc["rules"].append({
        "id": ID_SITTING, "scope": "sitting", "effect": "flag", "post": False, "post_since": None,
        "sitting": {"op": "sitting.binomial_vs_own", "args": _sitting_args()},
        "show": [["d", "d"], ["p", "p"]], "line": "shape binomial {d} {p}"})
    return doc


TABLES = {"shape_json_table.json": json.dumps({"rows": [list(JSON_ROWS), {"deep": JSON_DEEP}]}),
          "shape_text_table.txt": "".join(" ".join(str(v) for v in row) + "\n" for row in TEXT_ROWS)}


@pytest.fixture(scope="module")
def shapes_store(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("shapes")
    draft = tk.write_draft(str(tmp / "draft"), shapes_doc(), [])
    os.makedirs(os.path.join(draft, "data"))
    for name, text in TABLES.items():
        with open(os.path.join(draft, "data", name), "w", encoding="utf-8") as f:
            f.write(text)
    store = str(tmp / "store")
    os.makedirs(store)
    rev = rr.build_revision(draft, store, "shapes")       # the compiler admits every shape
    return store, rev


@pytest.fixture
def armed(shapes_store, monkeypatch):
    monkeypatch.setenv(rn.STORE_ENV, shapes_store[0])
    return shapes_store


def _leaf_numbers(node, out):
    """Every number of a JSON value, by an independent walk."""
    if isinstance(node, dict):
        for v in node.values():
            _leaf_numbers(v, out)
    elif isinstance(node, list):
        for v in node:
            _leaf_numbers(v, out)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        out.append(node)
    return out


VALUE_KINDS = {"int", "num", "edges", "list", "expr"}
NAME_KINDS = {"rel", "side", "row", "reporter", "filters", "label"}


def test_m4_every_argument_kind_of_the_registry_is_classified_and_every_value_kind_exercised(armed):
    """The evaluator's own table decides the shapes: every argument kind its
    registry declares is either value-bearing or a name, so a new kind fails
    here until the needles cover it; and the shapes revision uses an argument
    of every value-bearing kind."""
    kinds = {k for e in rm.REGISTRY.values() for _n, k in (e.args or ())}
    assert kinds <= VALUE_KINDS | NAME_KINDS, kinds - VALUE_KINDS - NAME_KINDS
    used = set()
    doc = shapes_doc()

    def walk(node):
        if isinstance(node, dict):
            if set(node) == {"op", "args"} and node["op"] in rm.REGISTRY:
                for name, kind in rm.REGISTRY[node["op"]].args:
                    v = node["args"][name]
                    if kind == "expr" and isinstance(v, dict) and set(v) == {"v"}:
                        used.add("expr")
                    elif kind != "expr":
                        used.add(kind)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(doc["rules"])
    assert VALUE_KINDS <= used, VALUE_KINDS - used


def test_m4_every_schema_legal_value_position_produces_a_needle(armed):
    """Every number the built revision holds (its rules document and every
    data table, walked independently of the tool) is found beside a threshold
    noun; a number it does not hold is not."""
    store, rev = armed
    rdir = os.path.join(store, "rules-" + rev)
    with open(os.path.join(rdir, "rules.json"), encoding="utf-8") as f:
        nums = _leaf_numbers(json.load(f), [])
    for name in sorted(os.listdir(os.path.join(rdir, "data"))):
        with open(os.path.join(rdir, "data", name), encoding="utf-8") as f:
            text = f.read()
        nums += _leaf_numbers(json.loads(text), []) if name.endswith(".json") else \
            [int(t) for t in text.split()]
    deciding = [v for v in nums if v not in (0, 1, -1) and (abs(v) >= rn.VALUE_MIN_BARE
                                                            or not float(v).is_integer())]
    assert len(deciding) >= 25
    needles = rn.derive(store)
    for v in deciding:
        assert rn.count("a threshold of %s here" % v, needles).get("value"), v
    assert rn.count("a threshold of 98765 here", needles) == {}    # control


def test_m4_each_list_is_found_by_its_adjacent_members(armed):
    needles = rn.derive(armed[0])
    for shape, (a, b) in LISTS.items():
        assert rn.count("members %s, %s" % (a, b), needles).get("value"), shape
    assert rn.count("members %s, %s" % (LIST_LITERAL[0], ABSENT), needles).get("value", 0) <= 1     # control


# -- every shape, planted in every mode -------------------------------------------------

def _plant(shape):
    return "the review used a threshold of %s for it\n" % SHAPES[shape] if shape != "scalar_literal" \
        else "the published hits literal was %s in that rule\n" % SHAPES["scalar_literal"]


def _repo(tmp_path):
    repo = str(tmp_path / "repo")
    subprocess.run(["git", "init", "-q", repo], check=True)
    with open(os.path.join(repo, "a.txt"), "w", encoding="utf-8") as f:
        f.write("public text\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def _run_mode(mode, tmp_path, text, name="notes.md"):
    """Plant `text` in one mode; return the exit code."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    if mode in ("staged", "range_blob", "range_message"):
        repo, base = _repo(tmp_path)
        os.makedirs(os.path.dirname(os.path.join(repo, name)), exist_ok=True)
        with open(os.path.join(repo, name), "w", encoding="utf-8") as f:
            f.write(text if mode != "range_message" else "public prose\n")
        _git(repo, "add", "-A")
        if mode == "staged":
            return rn.main(["staged", repo])
        _git(repo, "commit", "-q", "-m", "subject\n\n" + (text if mode == "range_message" else "body"))
        return rn.main(["range", repo, base, _git(repo, "rev-parse", "HEAD")])
    if mode == "message":
        p = tmp_path / "msg.txt"
        p.write_text("subject\n\n" + text, encoding="utf-8")
        return rn.main(["message", str(p)])
    if mode == "scan_dir":
        d = tmp_path / "d"
        (d / name).parent.mkdir(parents=True)
        (d / name).write_text(text, encoding="utf-8")
        return rn.main(["scan-dir", str(d)])
    if mode == "packet":
        repo, base = _repo(tmp_path)
        allow = tmp_path / "allow.txt"
        if name == "notes.md" or name.startswith("docs/"):     # a pinned outside document
            doc = tmp_path / os.path.basename(name)
            doc.write_text(text, encoding="utf-8")
            allow.write_text("a.txt\ndoc %s %s\n" % (doc, hashlib.sha256(doc.read_bytes()).hexdigest()))
        else:                                                   # an allowlisted repository path
            os.makedirs(os.path.dirname(os.path.join(repo, name)), exist_ok=True)
            with open(os.path.join(repo, name), "w", encoding="utf-8") as f:
                f.write(text)
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", "file")
            base = _git(repo, "rev-parse", "HEAD")
            allow.write_text("a.txt\n%s\n" % name)
        return rn.main(["packet", repo, base, str(allow), str(tmp_path / "p")])
    if mode == "seal":
        pin = _pin(tmp_path, {name: text})
        note = tmp_path / "note.txt"
        note.write_text("synthetic note\n", encoding="utf-8")
        return rn.main(["seal", pin, str(tmp_path / "MANIFEST.txt"), "TITLE", "attester x",
                        str(note), str(tmp_path / "seal.txt")])
    raise AssertionError(mode)


MODES = ["staged", "range_blob", "range_message", "message", "scan_dir", "packet", "seal"]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_m4_each_shape_is_found_in_each_mode(armed, tmp_path, capsys, mode, shape):
    assert _run_mode(mode, tmp_path / "control", "generic prose about the evaluator\n") == 0
    assert _run_mode(mode, tmp_path / "planted", _plant(shape)) == 1
    out = capsys.readouterr().out.splitlines()[-1]
    out = out.rsplit(" seal ", 1)[0] if mode == "seal" else out         # the seal digest is hex
    assert "value=" in out and str(SHAPES[shape]) not in out


# Fix pass 4, M4(a): every file type the deleted classifier distinguished
# (its CODE_EXT list, docs/, and everything else), each planted in every mode
# that carries a file; the shape cycles so every shape meets several types.
FILE_TYPES = ["backend/x.py", "plugin/x.cs", "backend/sql/x.sql", "ci/x.yml", "ci/x.yaml",
              "plugin/x.csproj", "scripts/x.sh", "scripts/x.ps1", "backend/x.json", "docs/x.py",
              "notes.md", "x.txt", "README"]
FILE_MODES = ["staged", "range_blob", "scan_dir", "packet", "seal"]
_CYCLE = sorted(s for s in SHAPES if s != "scalar_literal")


@pytest.mark.parametrize("mode", FILE_MODES)
@pytest.mark.parametrize("name", FILE_TYPES)
def test_m4_fix4_every_file_type_is_value_scanned_in_every_mode(armed, tmp_path, capsys, mode, name):
    shape = _CYCLE[FILE_TYPES.index(name) % len(_CYCLE)]
    assert _run_mode(mode, tmp_path / "control", "x = y  # generic\n", name=name) == 0
    assert _run_mode(mode, tmp_path / "planted", "if x > %s:\n    pass\n" % SHAPES[shape], name=name) == 1
    out = capsys.readouterr().out.splitlines()[-1]
    out = out.rsplit(" seal ", 1)[0] if mode == "seal" else out
    assert "value=" in out and str(SHAPES[shape]) not in out


@pytest.mark.parametrize("mode", FILE_MODES)
def test_m4_fix4_the_reviewers_renamed_json_table_is_found(armed, tmp_path, capsys, mode):
    """The round-4 input: a shipped JSON data table, renamed, carrying only
    its private values, as a source file of the repository."""
    table = json.loads(TABLES["shape_json_table.json"])
    assert _run_mode(mode, tmp_path / "control", json.dumps({"rows": [["a", "b"]]}),
                     name="backend/api/renamed_table.json") == 0
    assert _run_mode(mode, tmp_path / "planted", json.dumps(table), name="backend/api/renamed_table.json") == 1
    assert "value=" in capsys.readouterr().out.splitlines()[-1]


def test_m4_fix4_a_text_table_row_is_found_by_its_adjacent_members(armed):
    needles = rn.derive(armed[0])
    assert rn.count("%s %s\n" % LISTS["data_text"], needles).get("value")          # the row as the table holds it
    assert rn.count("%s %s\n" % (LISTS["data_text"][0], ABSENT), needles).get("value", 0) == 0  # control: not one of its rows


def test_m4_fix4_no_file_type_classifier_remains():
    assert not hasattr(rn, "CODE_EXT") and not hasattr(rn, "_is_doc")
    import inspect
    assert "values" not in inspect.signature(rn.count).parameters


# -- M4(b): the seal ---------------------------------------------------------------------

def _pin(tmp_path, files):
    pin = str(tmp_path / "pin")
    subprocess.run(["git", "init", "-q", pin], check=True)
    with open(os.path.join(pin, "x.txt"), "w", encoding="utf-8") as f:
        f.write("x\n")
    _git(pin, "add", "-A")
    _git(pin, "commit", "-q", "-m", "pin")
    ri = os.path.join(pin, "REVIEW-INPUT")
    os.makedirs(os.path.join(ri, "sub"))
    for name, text in files.items():
        os.makedirs(os.path.dirname(os.path.join(ri, name)), exist_ok=True)
        with open(os.path.join(ri, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    with open(os.path.join(ri, "sub", "inner.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("inner\n")
    return pin


def test_m4_the_manifest_is_the_integrators_format_byte_for_byte(tmp_path):
    pin = _pin(tmp_path, {"b.md": "bee\n"})
    note = tmp_path / "note.txt"
    note.write_text("  the note  \n", encoding="utf-8")
    out = str(tmp_path / "M.txt")
    rn.write_manifest(pin, out, "T", "integrator s", str(note), stamp="2026-10-04T00:00:00Z")
    head = _git(pin, "rev-parse", "HEAD")
    md5 = {"b.md": hashlib.md5(b"bee\n").hexdigest(), "sub/inner.txt": hashlib.md5(b"inner\n").hexdigest()}
    want = ("T (integrator s, detached, 2026-10-04T00:00:00Z)\n"
            "pin %s HEAD %s, DETACHED AT THE SHA.\n"
            "INTEGRATOR NOTE: the note\n"
            "\n"
            "%s 4 b.md\n"
            "%s 6 sub/inner.txt\n"
            "FILES 2 BYTES 10\n") % (pin, head, md5["b.md"], md5["sub/inner.txt"])
    with open(out, "rb") as f:
        assert f.read() == want.encode("ascii")
    with open(os.path.join(pin, "REVIEW-INPUT", "M.txt"), "rb") as f:
        assert f.read() == want.encode("ascii")                   # copied into the corpus
    # re-run: the copy already in the corpus is never listed in itself
    rn.write_manifest(pin, out, "T", "integrator s", str(note), stamp="2026-10-04T00:00:00Z")
    with open(out, "rb") as f:
        assert f.read() == want.encode("ascii")


def _sealed(armed, tmp_path, files=None, note_text="synthetic note\n"):
    pin = _pin(tmp_path, files or {"a.md": "generic\n"})
    note = tmp_path / "note.txt"
    note.write_text(note_text, encoding="utf-8")
    seal = str(tmp_path / "seal.txt")
    code = rn.main(["seal", pin, str(tmp_path / "MANIFEST.txt"), "TITLE", "attester x", str(note), seal])
    return pin, seal, code


def test_m4_the_seal_scans_the_manifest_it_wrote_first(armed, tmp_path, capsys):
    pin, seal, code = _sealed(armed, tmp_path / "clean")
    assert code == 0
    with open(seal, encoding="utf-8") as f:
        lines = f.read().splitlines()
    assert lines[0].startswith("SEAL ") and lines[1].startswith("RESULT review_needles: seal 0 found")
    assert any(ln.endswith(" MANIFEST.txt") for ln in lines[3:])             # the manifest is IN the seal
    # the reviewer's case: the value enters through the integrator's note,
    # i.e. the manifest itself, which the old flow wrote after the scan
    _pin2, seal2, code2 = _sealed(armed, tmp_path / "note", note_text="threshold of %d\n" % SHAPES["edges"])
    assert code2 == 1
    with open(seal2, encoding="utf-8") as f:
        assert "value=" in f.read().splitlines()[1]
    capsys.readouterr()


@pytest.mark.parametrize("change", ["added", "changed_byte", "removed", "manifest_edited"])
def test_m4_seal_verify_refuses_any_later_change(armed, tmp_path, capsys, change, monkeypatch):
    pin, seal, code = _sealed(armed, tmp_path)
    assert code == 0
    ri = os.path.join(pin, "REVIEW-INPUT")
    monkeypatch.delenv(rn.STORE_ENV)                                    # verification needs no store
    assert rn.main(["seal-verify", ri, seal]) == 0                      # control
    want = {"added": "file_added", "changed_byte": "file_changed", "removed": "file_removed",
            "manifest_edited": "file_changed"}[change]
    if change == "added":
        with open(os.path.join(ri, "late.md"), "w", encoding="utf-8") as f:
            f.write("added after the seal\n")
    elif change == "changed_byte":
        p = os.path.join(ri, "sub", "inner.txt")
        with open(p, "rb") as f:
            raw = bytearray(f.read())
        raw[0] ^= 1
        with open(p, "wb") as f:
            f.write(bytes(raw))
    elif change == "removed":
        os.remove(os.path.join(ri, "a.md"))
    else:
        with open(os.path.join(ri, "MANIFEST.txt"), "a", encoding="utf-8") as f:
            f.write("late line\n")
    assert rn.main(["seal-verify", ri, seal]) == 1
    assert want in capsys.readouterr().out.splitlines()[-1]


# Fix pass 4, M4(b): the seal scans and digests ONE snapshot. The hook runs
# right after the snapshot is read -- where the old shape had its gap between
# the scan and the digest -- and adds a file carrying a value and changes
# another; the seal records exactly the bytes it scanned, and seal-verify
# refuses the later change.
def _hooked_snapshot(monkeypatch, ri_of, mutate):
    real, taken = rn.snapshot, []

    def hook(root, skip=()):
        snap = real(root, skip)
        if os.path.normcase(os.path.abspath(root)) == os.path.normcase(os.path.abspath(ri_of())):
            taken.append(list(snap))
            mutate(root)
        return snap
    monkeypatch.setattr(rn, "snapshot", hook)
    return taken, real


def _late(root):
    with open(os.path.join(root, "late.md"), "w", encoding="utf-8") as f:
        f.write("threshold of %d\n" % SHAPES["edges"])
    with open(os.path.join(root, "a.md"), "a", encoding="utf-8") as f:
        f.write("changed\n")


def test_m4_fix4_the_seal_is_the_snapshot_it_scanned(armed, tmp_path, capsys, monkeypatch):
    pin = _pin(tmp_path, {"a.md": "generic\n"})
    ri = os.path.join(pin, "REVIEW-INPUT")
    taken, real = _hooked_snapshot(monkeypatch, lambda: ri, _late)
    note = tmp_path / "note.txt"
    note.write_text("synthetic note\n", encoding="utf-8")
    seal = str(tmp_path / "seal.txt")
    code = rn.main(["seal", pin, str(tmp_path / "MANIFEST.txt"), "TITLE", "attester x", str(note), seal])
    assert code == 0 and len(taken) == 1                 # one read of the corpus, scanned clean
    with open(seal, encoding="utf-8") as f:
        lines = f.read().splitlines()
    with open(str(tmp_path / "MANIFEST.txt"), "rb") as f:
        body = f.read()
    want = rn.snapshot_rows(taken[0] + [("MANIFEST.txt", body)])
    assert [ln.split(" ", 2) for ln in lines[3:]] == [[d, str(n), name] for name, n, d in want]
    assert lines[0] == "SEAL " + rn.corpus_digest(want)
    monkeypatch.setattr(rn, "snapshot", real)
    monkeypatch.delenv(rn.STORE_ENV, raising=False)
    assert rn.main(["seal-verify", ri, seal]) == 1        # the late change is refused, never sealed
    assert "file_added" in capsys.readouterr().out.splitlines()[-1]


def test_m4_fix4_the_packet_is_the_snapshot_it_scanned(armed, tmp_path, capsys, monkeypatch):
    repo, base = _repo(tmp_path)
    allow = tmp_path / "allow.txt"
    allow.write_text("a.txt\n")
    out = str(tmp_path / "p")

    def late(root):
        with open(os.path.join(root, "late.md"), "w", encoding="utf-8") as f:
            f.write("threshold of %d\n" % SHAPES["edges"])
    taken, real = _hooked_snapshot(monkeypatch, lambda: out, late)
    code = rn.main(["packet", repo, base, str(allow), out])
    # the file added after the snapshot is neither listed nor scanned, and the
    # packet as it now stands is refused against its manifest
    assert code == 0 and len(taken) == 1 and [r for r, _b in taken[0]] == ["a.txt"]
    digest = capsys.readouterr().out.split(" manifest ")[1].split()[0]
    monkeypatch.setattr(rn, "snapshot", real)
    assert rn.main(["packet-verify", out, digest]) == 1
    assert "packet_differs_from_its_manifest" in capsys.readouterr().out


def test_m4_a_seal_edited_to_match_is_refused_by_its_own_digest(armed, tmp_path, capsys, monkeypatch):
    pin, seal, _code = _sealed(armed, tmp_path)
    ri = os.path.join(pin, "REVIEW-INPUT")
    with open(os.path.join(ri, "late.md"), "w", encoding="utf-8") as f:
        f.write("added\n")
    with open(seal, encoding="utf-8") as f:
        lines = f.read().splitlines()
    lines[2] = "FILES %d" % (int(lines[2].split()[1]) + 1)
    lines.append("%s 6 late.md" % hashlib.sha256(b"added\n").hexdigest())
    with open(seal, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    monkeypatch.delenv(rn.STORE_ENV)
    assert rn.main(["seal-verify", ri, seal]) == 1
    assert "seal_differs_from_its_digest" in capsys.readouterr().out


def test_m4_the_seal_must_lie_outside_the_corpus(armed, tmp_path, capsys):
    pin = _pin(tmp_path, {"a.md": "generic\n"})
    note = tmp_path / "note.txt"
    note.write_text("n\n", encoding="utf-8")
    inside = os.path.join(pin, "REVIEW-INPUT", "seal.txt")
    assert rn.main(["seal", pin, str(tmp_path / "M.txt"), "T", "a", str(note), inside]) == 1
    assert "seal_inside_corpus" in capsys.readouterr().out
    assert not os.path.exists(inside)


# -- M5(a): every path query is strict ---------------------------------------------------
# Fix pass 4 (M5b, M5c): the enumeration resolves what a name STANDS FOR --
# `import os.path as osp`, `from os.path import isdir`, `from os import walk`,
# `q = os.path.isdir` -- and judges every reference, called or not; an os.walk
# is accepted only when its error handler is proven to reach the single exit-3
# refusal (walk_handler_proven).

FS_QUERIES = {"exists", "lexists", "isdir", "isfile", "islink", "ismount", "isjunction",
              "getsize", "getmtime", "getatime", "getctime", "samefile", "access"}
PATHLIB_QUERIES = {"exists", "is_dir", "is_file", "is_symlink", "is_mount"}
QUERY_NAMES = {"os.path." + q for q in FS_QUERIES} | {"os.access", "os.walk"}
_MODULE_NAMES = {"os", "os.path", "posixpath", "ntpath", "pathlib"}


class NoFixedPoint(Exception):
    """The alias resolution did not settle within its bound: the enumeration's
    exit-3 refusal (no verdict), never a silent partial answer."""


def _aliases(tree) -> dict:
    """name -> the SET of dotted names it can stand for, from every import
    and every assignment of a resolvable expression (fix pass 9: every
    binding's value is kept, so a name bound to two different values stands
    for both and is judged under each, where a single value flipped between
    them every round and never settled), iterated to a TRUE fixed point:
    rounds repeat until one adds nothing. A chain of k assignments in any
    source order settles within k + 1 rounds, so the bound (one round per
    assignment of the module, plus two) is reached only by bindings that
    grow without end (`x = y.a; y = x`); reaching it raises NoFixedPoint."""
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.asname:
                    out.setdefault(a.asname, set()).add(a.name)
                else:
                    out.setdefault(a.name.split(".")[0], set()).add(a.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            for a in n.names:
                out.setdefault(a.asname or a.name, set()).add(n.module + "." + a.name)
    assigns = [n for n in ast.walk(tree)
               if isinstance(n, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and n.value is not None]
    for _round in range(len(assigns) + 2):
        grew = False
        for n in assigns:
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            r = _resolve(n.value, out)
            for t in targets:
                if r and isinstance(t, ast.Name) and not r <= out.get(t.id, set()):
                    out.setdefault(t.id, set()).update(r)
                    grew = True
        if not grew:
            break
    else:
        raise NoFixedPoint("alias resolution did not settle in %d rounds" % (len(assigns) + 2))
    return {name: {_os_path(f) for f in fulls} for name, fulls in out.items()}


def _os_path(full):
    for m in ("posixpath", "ntpath"):
        if full == m or full.startswith(m + "."):
            return "os.path" + full[len(m):]
    return full


def _resolve(node, aliases) -> set:
    """Every dotted name a name or attribute reference can stand for (empty
    when it resolves to nothing)."""
    if isinstance(node, ast.Name):
        return set(aliases.get(node.id, ()))
    if isinstance(node, ast.Attribute):
        return {b + "." + node.attr for b in _resolve(node.value, aliases)}
    return set()


def _bindings(tree, name) -> list:
    """Every construct of the module that binds `name`, in ANY scope: a
    parameter of any function or lambda (positional, keyword-only, *args,
    **kwargs), an assignment, augmented or annotated store or deletion, a
    walrus, a loop or with target, an import or import alias, a def or a
    class at any depth, an except target, a match capture, and a global or
    nonlocal declaration."""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.arg) and n.arg == name:
            out.append(n)
        elif isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.append(n)
        elif isinstance(n, (ast.Import, ast.ImportFrom)) and any(
                (a.asname or a.name.split(".")[0]) == name for a in n.names):
            out.append(n)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name:
            out.append(n)
        elif isinstance(n, ast.ExceptHandler) and n.name == name:
            out.append(n)
        elif isinstance(n, (ast.Global, ast.Nonlocal)) and name in n.names:
            out.append(n)
        elif isinstance(n, (ast.MatchAs, ast.MatchStar)) and n.name == name:
            out.append(n)
        elif isinstance(n, ast.MatchMapping) and n.rest == name:
            out.append(n)
    return out


def _raise_is_total(stmt, param) -> bool:
    """`raise NoVerdict(<args>)` whose construction cannot itself fail: each
    argument a string constant, the handler's own parameter, or
    `type(<parameter>).__name__`."""
    if not (isinstance(stmt, ast.Raise) and stmt.cause is None and isinstance(stmt.exc, ast.Call)
            and isinstance(stmt.exc.func, ast.Name) and stmt.exc.func.id == "NoVerdict"
            and not stmt.exc.keywords):
        return False
    for a in stmt.exc.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            continue
        if isinstance(a, ast.Name) and a.id == param:
            continue
        if (isinstance(a, ast.Attribute) and a.attr == "__name__" and isinstance(a.value, ast.Call)
                and isinstance(a.value.func, ast.Name) and a.value.func.id == "type"
                and len(a.value.args) == 1 and not a.value.keywords
                and isinstance(a.value.args[0], ast.Name) and a.value.args[0].id == param):
            continue
        return False
    return True


# Fix pass 7 (round 7 M2): what an exception or a suppression name stands for
# is resolved through its aliases at the use site; a catcher or a suppressor
# the proof cannot resolve is treated as catching.
_DYNAMIC = frozenset({"__builtins__", "__dict__", "globals", "vars", "locals", "exec", "eval",
                      "setattr", "delattr", "__import__"})
_BUILTIN_EXCEPTIONS = frozenset("builtins." + n for n, v in vars(builtins).items()
                                if isinstance(v, type) and issubclass(v, BaseException))
_CATCHES_NOVERDICT = frozenset({"builtins.Exception", "builtins.BaseException"})   # NoVerdict's bases
_NEVER_SUPPRESS = frozenset({"builtins.open", "io.open", "os.fdopen", "os.scandir", "tempfile.TemporaryFile",
                             "tempfile.NamedTemporaryFile", "tempfile.TemporaryDirectory"})


class _Names:
    """What a name or a dotted reference stands for at EVERY use site of the
    module: the dotted name all of its bindings agree on, each an import or
    an assignment of a name or an attribute that resolves the same way
    (through any chain of assigned and imported names, re-exports included);
    a name the module never binds is the builtin of that name. Anything else
    is None, unresolvable: a binding of any other kind (a parameter, a def or
    class, a loop, with or except target, an unpacking, an augmented store, a
    global or nonlocal declaration, a deletion), bindings that disagree, a
    cycle, a relative import -- and EVERY name of a module whose names can
    change at run time: a star import, a reference to a namespace operation
    (_DYNAMIC), or a store or deletion of an attribute of the builtins
    module."""

    def __init__(self, tree, parents):
        self.tree, self.parents, self.dynamic = tree, parents, False
        nodes = list(ast.walk(tree))
        self.dynamic = (
            any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in nodes)
            or any(isinstance(n, ast.Name) and n.id in _DYNAMIC for n in nodes)
            or any(isinstance(n, ast.Attribute) and n.attr in _DYNAMIC for n in nodes)
            or any(isinstance(n, ast.Attribute) and isinstance(n.ctx, (ast.Store, ast.Del))
                   and self.ref(n.value) == "builtins" for n in nodes))

    def name(self, name, seen=frozenset()):
        if self.dynamic or name in seen:
            return None
        binds = _bindings(self.tree, name)
        if not binds:
            return "builtins." + name if hasattr(builtins, name) else None
        got = set()
        for b in binds:
            if isinstance(b, ast.Import):
                got |= {a.name if a.asname else a.name.split(".")[0] for a in b.names
                        if (a.asname or a.name.split(".")[0]) == name}
            elif isinstance(b, ast.ImportFrom) and b.module and not b.level:
                got |= {b.module + "." + a.name for a in b.names if (a.asname or a.name) == name}
            elif isinstance(b, ast.Name) and isinstance(b.ctx, ast.Store) and self._assigned(b):
                got.add(self.ref(self.parents[id(b)].value, seen | {name}))
            else:
                return None
        return got.pop() if len(got) == 1 and None not in got else None

    def _assigned(self, b):
        """b is a whole target of an assignment that has a value (not a part
        of an unpacking, an augmented store or a bare annotation)."""
        p = self.parents.get(id(b))
        if isinstance(p, ast.Assign):
            return any(t is b for t in p.targets)
        return isinstance(p, (ast.AnnAssign, ast.NamedExpr)) and p.target is b and p.value is not None

    def ref(self, node, seen=frozenset()):
        if isinstance(node, ast.Name):
            return self.name(node.id, seen)
        if isinstance(node, ast.Attribute):
            base = self.ref(node.value, seen)
            return None if base is None else base + "." + node.attr
        return None


def _may_catch(names, t) -> bool:
    """Whether an except clause's type can catch NoVerdict: False only when it
    resolves (_Names) to a builtin exception class that is not one of
    NoVerdict's bases; a tuple can when any member can."""
    if isinstance(t, ast.Tuple):
        return any(_may_catch(names, e) for e in t.elts)
    r = names.ref(t)
    if r is None:
        return True                     # a catcher the proof cannot resolve can catch
    return r in _CATCHES_NOVERDICT or r not in _BUILTIN_EXCEPTIONS


def _may_suppress(names, item) -> bool:
    """Whether a with item's context manager can swallow the refusal: False
    only when the item calls what resolves (_Names) to a manager known never
    to suppress (_NEVER_SUPPRESS); contextlib.suppress under any alias, and
    every manager the proof cannot resolve, can. The name is trusted only in
    a module with no operation that can rebind it (_manager_rebinds)."""
    e = item.context_expr
    return not (isinstance(e, ast.Call) and names.ref(e.func) in _NEVER_SUPPRESS)


# Fix pass 9 (round 8 M5): _Names resolves a name while an operation changes
# what it denotes at run time (an attribute store on the module, a namespace
# write, code the module hands the module to), so a never-suppress manager
# trusted by its name could be a suppressing one. The proof is refused for the
# whole module whenever any operation could rebind a manager, a prefix of its
# dotted path, an alias of either, or the manager itself.
_WATCHED = frozenset(m[:i] for m in _NEVER_SUPPRESS for i in range(len(m) + 1)
                     if i == len(m) or m[i] == ".")      # each manager and every prefix of its dotted path
_WATCHED_NAMES = frozenset(p.rsplit(".", 1)[-1] for p in _WATCHED)   # the bare names they are reached by
_PROTOCOL = frozenset({"__enter__", "__exit__", "__aenter__", "__aexit__", "__class__", "__bases__",
                       "__dict__", "__setattr__", "__delattr__", "__getattr__", "__getattribute__"})
_NAMESPACE = _DYNAMIC | {"__setattr__", "__delattr__", "modules"}   # `modules`: sys.modules
_REFLECTIVE_STRINGS = frozenset(s for s in _NAMESPACE | _PROTOCOL
                                if s.startswith("__") or s in ("setattr", "delattr", "modules"))


class Reported(tuple):
    """One row of the enumeration's report: (line, kind), as every caller
    unpacks it. An os.walk row also carries every operation of the module
    that can rebind a never-suppress manager (fix pass 9) or reach a
    namespace (fix pass 10) (`rebinds`, each (file, line, kind)), and its
    repr names them."""

    def __new__(cls, line, kind, file="<source>", rebinds=()):
        row = tuple.__new__(cls, (line, kind))
        row.rebinds = tuple((file, ln, k) for ln, k in rebinds)
        return row

    def __repr__(self):
        why = "; ".join("%s:%d %s" % r for r in self.rebinds)
        return tuple.__repr__(self) + (" unproven: " + why if why else "")


def _candidates(tree, names, node, seen=frozenset()) -> set:
    """Every dotted name an expression can stand for through EVERY binding of
    its names, None standing for anything unresolvable. Unlike _Names,
    bindings that disagree are all kept, so a rebinding shows beside the
    binding it replaces."""
    if isinstance(node, ast.Attribute):
        return {None if b is None else b + "." + node.attr
                for b in _candidates(tree, names, node.value, seen)}
    if not isinstance(node, ast.Name) or node.id in seen:
        return {None}
    binds = _bindings(tree, node.id)
    if not binds:
        return {"builtins." + node.id} if hasattr(builtins, node.id) else {None}
    out = set()
    for b in binds:
        got = _bound(tree, names, b, node.id, seen | {node.id})
        out |= {None} if got is None else got
    return out


def _bound(tree, names, b, name, seen=frozenset()):
    """The dotted names the binding b can make `name` stand for: an absolute
    import's target, or the candidates of the value of an assignment whose
    whole target is `name`; None for a binding of any other kind."""
    if isinstance(b, ast.Import):
        return {a.name if a.asname else a.name.split(".")[0] for a in b.names
                if (a.asname or a.name.split(".")[0]) == name}
    if isinstance(b, ast.ImportFrom):
        if not b.module or b.level:
            return None
        return {b.module + "." + a.name for a in b.names if (a.asname or a.name) == name}
    if isinstance(b, ast.Name) and isinstance(b.ctx, ast.Store) and names._assigned(b):
        return _candidates(tree, names, names.parents[id(b)].value, seen | {name})
    return None


def _binding_kind(b, parents) -> str:
    if isinstance(b, ast.arg):
        return "parameter"
    if isinstance(b, (ast.Import, ast.ImportFrom)):
        return "import"
    if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "def"
    if isinstance(b, ast.ClassDef):
        return "class"
    if isinstance(b, ast.ExceptHandler):
        return "except target"
    if isinstance(b, ast.Global):
        return "global declaration"
    if isinstance(b, ast.Nonlocal):
        return "nonlocal declaration"
    if not isinstance(b, ast.Name):
        return "match capture"
    if isinstance(b.ctx, ast.Del):
        return "deletion"
    p = parents.get(id(b))
    if isinstance(p, ast.AugAssign):
        return "augmented assignment"
    if isinstance(p, ast.AnnAssign) and p.value is None:
        return "annotation"
    if isinstance(p, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
        return "assignment"
    return "store"                        # a loop, with, comprehension or unpacking target


def _plain_getattr(call) -> bool:
    """getattr(x, "<name>") with a constant plain attribute that is not a
    watched component, a namespace operation or a protocol member."""
    a = call.args[1] if len(call.args) >= 2 else None
    return (isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.isidentifier()
            and not a.value.startswith("__") and a.value not in _WATCHED_NAMES | _NAMESPACE | _PROTOCOL)


def _manager_rebinds(tree, names) -> list:
    """Every operation of the module that could rebind a never-suppress
    manager, a prefix of its dotted path (_WATCHED), an alias of either, or
    the manager itself, as sorted (line, kind) pairs. Judged statically and
    conservatively, in every scope; an operation the proof cannot rule out
    counts:
      (1) a binding of a watched name -- a component of a watched path
          (_WATCHED_NAMES), or an alias any of whose bindings reaches a
          watched path through any chain (_candidates) -- other than the
          imports and whole assignments that make it stand for ONE watched
          path: an import of anything else, an assignment of anything else,
          an augmented store, a deletion, a parameter, a def or class, a
          loop, with, comprehension, unpacking or except target, a match
          capture, a global or nonlocal declaration;
      (2) an attribute store or deletion (plain, augmented, del, or as any
          target) whose attribute is a watched component or a member of the
          manager or attribute protocol (_PROTOCOL), on ANY base: a base the
          proof cannot resolve may be the module or the manager;
      (3) a namespace or reflective operation: a reference to a _DYNAMIC
          name or attribute, to __setattr__, __delattr__ or a `modules`
          attribute (sys.modules), a string constant naming one of them or a
          protocol member, a getattr that is not a call with a constant plain
          attribute (_plain_getattr), an import of importlib or imp, a star
          import;
      (4) a watched object escaping: a reference to a watched name, or to an
          attribute named by a watched component, anywhere but as the
          function of a call, the base of an attribute, or the whole value of
          an assignment to names (an alias, judged by (1)) -- code the proof
          cannot see may rebind what it is handed.
    The proof judges the operations written in this module: code that runs
    from elsewhere (another module's import-time code, a method of an object
    a caller supplies) is outside a per-module static proof."""
    parents = names.parents
    bound = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.arg):
            bound.add(n.arg)
        elif isinstance(n, ast.Name):
            bound.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            bound |= {a.asname or a.name.split(".")[0] for a in n.names if a.name != "*"}
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.ExceptHandler,
                            ast.MatchAs, ast.MatchStar)) and n.name:
            bound.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            bound |= set(n.names)
        elif isinstance(n, ast.MatchMapping) and n.rest:
            bound.add(n.rest)
    watched = set()
    for name in bound:
        if name in _WATCHED_NAMES or _WATCHED & _candidates(tree, names, ast.Name(name, ast.Load())):
            watched.add(name)
    out = []
    for name in sorted(watched):                                           # (1)
        canon = None
        for b in sorted(_bindings(tree, name), key=lambda x: (x.lineno, x.col_offset)):
            got = _bound(tree, names, b, name)
            if got is not None and len(got) == 1 and got <= _WATCHED and canon in (None, got):
                canon = got                     # an import or whole assignment of one watched path
                continue
            out.append((b.lineno, "%s rebinds %s" % (_binding_kind(b, parents), name)))
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and isinstance(n.ctx, (ast.Store, ast.Del)) \
                and (n.attr in _WATCHED_NAMES or n.attr in _PROTOCOL):     # (2)
            kind = "attribute deletion" if isinstance(n.ctx, ast.Del) else \
                "augmented attribute store" if isinstance(parents.get(id(n)), ast.AugAssign) else "attribute store"
            out.append((n.lineno, "%s rebinds %s" % (kind, ast.unparse(n))))
        ref = n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else None
        if ref in _NAMESPACE:                                              # (3)
            out.append((n.lineno, "namespace operation " + ref))
        elif ref == "getattr":
            p = parents.get(id(n))
            if not (isinstance(p, ast.Call) and p.func is n and _plain_getattr(p)):
                out.append((n.lineno, "getattr with a computed or reflective attribute"))
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in _REFLECTIVE_STRINGS:
            out.append((n.lineno, "string naming " + n.value))
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""]
            if any(m.split(".")[0] in ("importlib", "imp") for m in mods):
                out.append((n.lineno, "dynamic import"))
            if isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names):
                out.append((n.lineno, "star import"))
        if isinstance(n, (ast.Name, ast.Attribute)) and isinstance(n.ctx, ast.Load) and (
                n.id in watched | _WATCHED_NAMES if isinstance(n, ast.Name) else n.attr in _WATCHED_NAMES):
            p = parents.get(id(n))                                         # (4)
            if isinstance(p, ast.Call) and p.func is n or isinstance(p, ast.Attribute) and p.value is n:
                continue
            if isinstance(p, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and p.value is n and all(
                    isinstance(t, ast.Name) for t in (p.targets if isinstance(p, ast.Assign) else [p.target])):
                continue
            out.append((n.lineno, "%s escapes as a value" % ast.unparse(n)))
    return sorted(set(out))


# Fix pass 10 (round 9 M5): _manager_rebinds is a list of rebinding FORMS, and
# a form outside it (a write through a function's __globals__ mapping) rebound
# a manager unseen. The proof is now BOUNDED by namespace reach instead: it is
# refused whenever the module holds any expression in the stated lists that
# can reach a namespace (a module dict, a function's globals, a frame, the
# import system, a mock), any name bound to one, or any write through a base
# the proof cannot resolve to an object the module makes. This is a bound
# over the stated lists and the unresolved-base rule, not a claim that every
# conceivable rebinding is detected: code that runs from elsewhere stays
# outside a per-module static proof, as fix pass 9 states.
_REACH_CALLABLES = frozenset(
    {"builtins." + n for n in ("globals", "vars", "locals", "dir", "getattr", "setattr", "delattr", "hasattr",
                               "exec", "eval", "compile", "__import__", "breakpoint")}
    | {"sys._getframe", "sys.settrace", "sys.setprofile", "sys.modules", "inspect.currentframe", "inspect.stack",
       "inspect.getmodule", "inspect.getmembers", "types.FunctionType", "types.MethodType", "types.ModuleType",
       "types.new_class", "operator.setitem", "operator.delitem", "operator.attrgetter", "operator.itemgetter",
       "functools.reduce", "codecs.decode"})
_REACH_MODULES = ("importlib", "runpy", "ctypes", "gc", "unittest.mock", "mock", "base64",
                  "pickle", "_pickle", "marshal", "copyreg", "shelve")    # the module and every attribute of it
_REACH_IMPORTS = ("importlib", "ctypes", "gc", "runpy", "unittest.mock", "mock", "types", "inspect", "builtins")
_FRAME_ATTRS = frozenset({"f_globals", "f_locals", "f_back", "f_builtins", "gi_frame", "cr_frame", "ag_frame",
                          "tb_frame"})
_NAME_ARG = frozenset({"builtins.getattr", "builtins.hasattr"})    # benign only with a literal plain name
_STRING_NAMES = frozenset({"__name__", "__file__", "__doc__", "__debug__", "__package__", "__qualname__",
                           "__module__"})                           # module-level dunder NAMES that hold strings


def _dunder(s) -> bool:
    return isinstance(s, str) and len(s) > 4 and s.startswith("__") and s.endswith("__")


def _in_module(c, mods) -> bool:
    return any(c == m or c.startswith(m + ".") for m in mods)


def _type_name(node) -> bool:
    """`type(<name>).__name__`: the class name of an object, a string (the
    form _raise_is_total admits in a refusal's arguments)."""
    return (isinstance(node, ast.Attribute) and node.attr == "__name__" and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name) and node.value.func.id == "type"
            and len(node.value.args) == 1 and not node.value.keywords and isinstance(node.value.args[0], ast.Name))


def _target_names(t) -> set:
    """The plain names a binding target binds (through tuples, lists and
    starred parts; a subscript or attribute target binds no name)."""
    if isinstance(t, ast.Name):
        return {t.id}
    if isinstance(t, ast.Starred):
        return _target_names(t.value)
    if isinstance(t, (ast.Tuple, ast.List)):
        return set().union(*[_target_names(e) for e in t.elts]) if t.elts else set()
    return set()


class _Reach:
    """Namespace reach of one module (fix pass 10), judged per node:
      a namespace-reaching EXPRESSION is any dunder attribute, a frame or
      generator frame attribute (_FRAME_ATTRS), sys.modules and any subscript
      or attribute of it, a reference that can stand for a namespace-reaching
      callable or module (_REACH_CALLABLES, _REACH_MODULES, the builtins
      module) other than the function of a getattr or hasattr call whose
      name is a literal plain name, a call of any of these, anything named
      monkeypatch, and a dunder name other than the string-valued ones;
      a namespace-reaching NAME is any name bound, through every binding
      form in any scope (assignment, augmented and annotated assignment,
      unpacking, walrus, with-as, loop and comprehension targets, except-as,
      function and lambda defaults, a def through what it returns or yields,
      a class through its body), to anything that contains a
      namespace-reaching expression or name, to a fixed point."""

    def __init__(self, tree, names):
        self.tree, self.parents, self.names = tree, names.parents, names
        self.binds, self.cache = {}, {}
        for n in ast.walk(tree):
            if isinstance(n, ast.arg):
                self.binds.setdefault(n.arg, []).append(n)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                self.binds.setdefault(n.id, []).append(n)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    self.binds.setdefault(a.asname or a.name.split(".")[0], []).append(n)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.ExceptHandler,
                                ast.MatchAs, ast.MatchStar)) and n.name:
                self.binds.setdefault(n.name, []).append(n)
            elif isinstance(n, (ast.Global, ast.Nonlocal)):
                for g in n.names:
                    self.binds.setdefault(g, []).append(n)
            elif isinstance(n, ast.MatchMapping) and n.rest:
                self.binds.setdefault(n.rest, []).append(n)
        self.marked = set()
        self._mark()

    def cands(self, node, seen=frozenset()) -> set:
        """Every dotted name a reference can stand for through every binding
        of its names (the _candidates rule), None for anything unresolvable."""
        if isinstance(node, ast.Attribute):
            return {None if b is None else b + "." + node.attr for b in self.cands(node.value, seen)}
        if not isinstance(node, ast.Name) or node.id in seen:
            return {None}
        if not seen and node.id in self.cache:
            return self.cache[node.id]
        binds = self.binds.get(node.id, [])
        if not binds:
            out = {"builtins." + node.id} if hasattr(builtins, node.id) else {None}
        else:
            out = set()
            for b in binds:
                if isinstance(b, ast.Import):
                    out |= {a.name if a.asname else a.name.split(".")[0] for a in b.names
                            if (a.asname or a.name.split(".")[0]) == node.id}
                elif isinstance(b, ast.ImportFrom) and b.module and not b.level:
                    out |= {b.module + "." + a.name for a in b.names if (a.asname or a.name) == node.id}
                elif isinstance(b, ast.Name) and isinstance(b.ctx, ast.Store) and self.names._assigned(b):
                    out |= self.cands(self.parents[id(b)].value, seen | {node.id})
                else:
                    out.add(None)
        if not seen:
            self.cache[node.id] = out
        return out

    def reach_callable(self, node):
        """The first dotted name a reference can stand for that is a
        namespace-reaching callable or module, else None."""
        for c in sorted(x for x in self.cands(node) if x):
            if c in _REACH_CALLABLES or _in_module(c, _REACH_MODULES) or c == "builtins":
                return c
        return None

    def benign_name_call(self, call) -> bool:
        """getattr or hasattr called with a literal plain (non-dunder) name."""
        c = self.reach_callable(call.func)
        a = call.args[1] if len(call.args) >= 2 else None
        name = a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else None
        computed = name is None                       # a name built at run time
        return c in _NAME_ARG and not computed and not _dunder(name)

    def reaching(self, node) -> bool:
        """Whether this one node is a namespace-reaching expression or name."""
        if isinstance(node, ast.Attribute):
            if _dunder(node.attr):                                   # every dunder attribute
                return True
            if node.attr in _FRAME_ATTRS or node.attr == "monkeypatch":
                return True
        if isinstance(node, ast.Name):
            if node.id in self.marked:                               # a name bound to a reaching expression
                return True
            if node.id == "monkeypatch" or _dunder(node.id) and node.id not in _STRING_NAMES:
                return True
        if isinstance(node, (ast.Name, ast.Attribute)) and self.reach_callable(node):
            p = self.parents.get(id(node))
            return not (isinstance(p, ast.Call) and p.func is node and self.benign_name_call(p))
        if isinstance(node, ast.Subscript):
            return "sys.modules" in self.cands(node.value)
        if isinstance(node, ast.Call):
            return self.reaching(node.func) or self.contains(node.func)
        return False

    def contains(self, node) -> bool:
        return any(self.reaching(x) for x in ast.walk(node))

    def _sources(self) -> list:
        """(names bound, the expressions they are bound from) for every
        binding form of the module."""
        out = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Assign):
                out.append((set().union(*[_target_names(t) for t in n.targets]), [n.value]))
            elif isinstance(n, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and n.value is not None:
                out.append((_target_names(n.target), [n.value]))
            elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
                out.append((_target_names(n.target), [n.iter]))
            elif isinstance(n, ast.withitem) and n.optional_vars is not None:
                out.append((_target_names(n.optional_vars), [n.context_expr]))
            elif isinstance(n, ast.ExceptHandler) and n.name and n.type is not None:
                out.append(({n.name}, [n.type]))
            elif isinstance(n, ast.arguments):
                pos = n.posonlyargs + n.args
                out += [({a.arg}, [d]) for a, d in zip(pos[len(pos) - len(n.defaults):], n.defaults)]
                out += [({a.arg}, [d]) for a, d in zip(n.kwonlyargs, n.kw_defaults) if d is not None]
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append(({n.name}, [x.value for x in ast.walk(n) if isinstance(x, (ast.Return, ast.Yield,
                                                                                     ast.YieldFrom)) and x.value]))
            elif isinstance(n, ast.ClassDef):
                out.append(({n.name}, list(n.body)))
            elif isinstance(n, ast.Match):
                caps = {x.name for x in ast.walk(n) if isinstance(x, (ast.MatchAs, ast.MatchStar)) and x.name}
                out.append((caps, [n.subject]))
        return out

    def _mark(self):
        sources = self._sources()
        while True:
            new = set()
            for bound, exprs in sources:
                if bound - self.marked and any(self.contains(e) for e in exprs):
                    new |= bound - self.marked
            if not new:
                return
            self.marked |= new

    def made_here(self, node, seen=frozenset()) -> bool:
        """Whether the base chain of an expression starts from an object the
        module itself makes: a literal or display, the fresh result of a
        call of a builtin or of a def or class of the module, or a name
        whose every binding is an import, a def, a class, or an assignment,
        loop or with target whose source is itself made here. A parameter,
        a name the module never binds, an except or match capture and the
        result of any other call are not."""
        while isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred)):
            node = node.value
        if isinstance(node, ast.Call):
            f = node.func
            if not isinstance(f, ast.Name):
                return False                                         # a method's or an imported callable's result
            binds = self.binds.get(f.id, [])
            if not binds:
                return hasattr(builtins, f.id)
            return all(isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for b in binds)
        if not isinstance(node, ast.Name):
            return True                                              # a literal, a display, a lambda
        if node.id in seen:
            return False
        binds = self.binds.get(node.id, [])
        if not binds:
            return False                                             # an unresolved global
        for b in binds:
            if isinstance(b, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                              ast.Global, ast.Nonlocal)):
                continue
            if isinstance(b, ast.Name) and isinstance(b.ctx, ast.Del):
                continue
            if isinstance(b, ast.Name):
                stmt = self.parents.get(id(b))
                while isinstance(stmt, (ast.Tuple, ast.List, ast.Starred)):
                    stmt = self.parents.get(id(stmt))
                if isinstance(stmt, (ast.AugAssign, ast.AnnAssign)) and (stmt.value is None
                                                                          or isinstance(stmt, ast.AugAssign)):
                    continue                                         # the object is bound by another binding
                if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) \
                        and self.made_here(stmt.value, seen | {node.id}):
                    continue
                if isinstance(stmt, (ast.For, ast.AsyncFor, ast.comprehension)) \
                        and self.made_here(stmt.iter, seen | {node.id}):
                    continue
                if isinstance(stmt, ast.withitem) and self.made_here(stmt.context_expr, seen | {node.id}):
                    continue
            return False                 # a parameter, a capture, a target of a source not made here
        return True


# The real-module rule (fix pass 10). Measured over the three review modules,
# the unresolved-base case found 32 write sites: 9 in review_needles.py
# (dict accumulators that are parameters: out twice, a; local dicts whose
# names are also parameters elsewhere in the module, which the scope-merged
# resolution cannot tell apart: tables, found three times, out; one tuple
# store on self), 23 in review_rules.py (stores on self, two of them
# subscripts of self attributes, and the parameter memo dict), 0 in
# review_boot.py; every site is named with its line in the notes. The
# narrowest rule that still refuses every control: the unresolved-base case
# refuses in every module EXCEPT a module named here, and only while it holds
# exactly the measured number of such sites and no other namespace-reaching
# operation at all; one more or one fewer site, or any other row, and the
# exemption lapses (the refusal returns). review_rules.py and review_boot.py
# are not named: other rules refuse them regardless.
_MEASURED_CLEAN = {"review_needles.py": 9}


def _unresolved(kind) -> bool:
    return " through unresolved base " in kind


_ESCAPES = {ast.Call: "a call argument", ast.keyword: "a call argument", ast.Return: "a return value",
            ast.Yield: "a yielded value", ast.YieldFrom: "a yielded value", ast.Await: "an awaited value",
            ast.Lambda: "a lambda body", ast.Raise: "a raised value", ast.Assign: "a stored value",
            ast.AnnAssign: "a stored value", ast.AugAssign: "a stored value"}


def _namespace_reach(tree, names, file="<source>") -> list:
    """Every namespace-reaching operation of the module (fix pass 10), as
    sorted (line, kind) pairs; any one refuses the handler proof (the
    unresolved-base rows of a module the real-module rule names are dropped
    while it holds exactly its measured count of them and nothing else):
      (1) a store, deletion or augmented store whose target is a subscript
          or an attribute, when the target or anything in its base is a
          namespace-reaching expression or name (_Reach), or when its base
          does not start from an object the module makes (_Reach.made_here);
      (2) a call of a namespace-reaching callable, or of anything whose
          function contains a namespace-reaching expression or name (a method
          of a namespace, a dunder method, a marked alias), in any scope;
      (3) an import of importlib, ctypes, gc, runpy, unittest.mock, mock,
          types, inspect or builtins, in any scope;
      (4) a namespace-reaching expression or name that leaves the module's
          sight: passed as a call argument, returned, yielded, raised, stored
          into an attribute or subscript, or used anywhere but read through,
          bound to plain names (which marks them), compared, tested or
          formatted; `type(<name>).__name__` is a string and exempt.
    Fix pass 9's _manager_rebinds still runs beside it, unchanged."""
    r = _Reach(tree, names)
    parents = r.parents
    out = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.Attribute, ast.Subscript)) and isinstance(n.ctx, (ast.Store, ast.Del)):     # (1)
            what = "attribute" if isinstance(n, ast.Attribute) else "subscript"
            op = "%s deletion" % what if isinstance(n.ctx, ast.Del) else \
                "augmented %s store" % what if isinstance(parents.get(id(n)), ast.AugAssign) else "%s store" % what
            hit = next((x for x in [n] + list(ast.walk(n.value)) if r.reaching(x)), None)
            if hit is not None:
                out.append((n.lineno, "%s through namespace-reaching %s" % (op, ast.unparse(hit))))
            elif not r.made_here(n.value):
                out.append((n.lineno, "%s through unresolved base %s" % (op, ast.unparse(n.value))))
        if isinstance(n, ast.Call) and r.reaching(n):                                                     # (2)
            out.append((n.lineno, "call of namespace-reaching %s" % ast.unparse(n.func)))
        if isinstance(n, (ast.Import, ast.ImportFrom)):                                                  # (3)
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else \
                [n.module or ""] + ["%s.%s" % (n.module, a.name) for a in n.names if n.module]
            for m in sorted({m for m in mods if _in_module(m, _REACH_IMPORTS)}):
                out.append((n.lineno, "import of namespace-reaching module %s" % m))
        if r.reaching(n) and not _type_name(n) and not isinstance(n, ast.Call) \
                and not isinstance(getattr(n, "ctx", None), (ast.Store, ast.Del)):                      # (4)
            ctx, p = n, parents.get(id(n))
            while True:
                if isinstance(p, (ast.Attribute, ast.Subscript)) and p.value is ctx and isinstance(p.ctx, ast.Load) \
                        or isinstance(p, (ast.Tuple, ast.List, ast.Set, ast.Dict, ast.Starred, ast.BoolOp)) \
                        or isinstance(p, ast.IfExp) and p.test is not ctx:
                    ctx, p = p, parents.get(id(p))                   # read through: the result still reaches
                    continue
                break
            if isinstance(p, ast.Call) and p.func is ctx:
                continue                                             # a call: (2)
            if isinstance(p, (ast.Attribute, ast.Subscript)) and p.value is ctx:
                continue                                             # the base of a store: (1)
            if isinstance(p, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and p.value is ctx and all(
                    _target_names(t) and not any(isinstance(x, (ast.Attribute, ast.Subscript)) for x in ast.walk(t))
                    for t in (p.targets if isinstance(p, ast.Assign) else [p.target])):
                continue                                             # bound to plain names: marked
            if isinstance(p, (ast.For, ast.AsyncFor, ast.comprehension)) and p.iter is ctx \
                    or isinstance(p, ast.withitem) and p.context_expr is ctx:
                tgt = p.target if not isinstance(p, ast.withitem) else p.optional_vars
                if tgt is None or not any(isinstance(x, (ast.Attribute, ast.Subscript)) for x in ast.walk(tgt)):
                    continue                                         # bound to plain names: marked
            if isinstance(p, (ast.Compare, ast.Expr, ast.FormattedValue, ast.UnaryOp, ast.If, ast.While,
                              ast.Assert, ast.IfExp)) or isinstance(p, ast.comprehension) and ctx in p.ifs:
                continue                                             # compared, tested, formatted or discarded
            if isinstance(p, ast.arguments) or isinstance(p, ast.ExceptHandler) and p.type is ctx:
                continue                                             # a default or a caught type: marked
            if isinstance(p, ast.ClassDef) and ctx in p.bases + p.decorator_list \
                    or isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)) and ctx in p.decorator_list:
                out.append((n.lineno, "namespace-reaching %s escapes into a decorator or base" % ast.unparse(n)))
                continue
            where = next((v for k, v in _ESCAPES.items() if isinstance(p, k)), "a %s" % type(p).__name__)
            out.append((n.lineno, "namespace-reaching %s escapes as %s" % (ast.unparse(n), where)))
    out = sorted(set(out))
    measured = _MEASURED_CLEAN.get(os.path.basename(file.replace("\\", "/")))
    if measured is not None and all(_unresolved(k) for _l, k in out) and len(out) == measured:
        return []                       # the real-module rule: exactly the measured, named sites
    return out


def walk_handler_proven(tree, handler, file="<source>") -> bool:
    """An os.walk error handler is accepted only when the name AT THE CALL
    SITE can stand for nothing but one module-level raising function, and
    every exception path from it reaches the single exit-3 refusal:
      (1) `handler` is a plain name, and the module binds that name exactly
          once, by one module-level def: no parameter of any function or
          lambda (a default included), no local or module store, no nested
          def or class, import alias, except target, match capture or
          global/nonlocal declaration anywhere (_bindings), so no scope
          between the call and the module can shadow it;
      (2) that def takes one positional parameter, and its whole body (a
          docstring aside) is `raise NoVerdict(...)` whose construction
          cannot fail (_raise_is_total);
      (3) NoVerdict is ONE module class deriving from Exception alone, bound
          nowhere else, and its base resolves to the builtin Exception;
      (4) every except clause in the module that can catch NoVerdict either
          re-raises it unchanged or is in main and returns 3 on every path
          it returns. A clause is proven unable to catch it only when its
          type resolves, through its aliases at the use site (_Names), to
          builtin exception classes other than NoVerdict's bases
          (_may_catch); a bare clause, NoVerdict, and every type the proof
          cannot resolve can catch it (fix pass 7);
      (5) no finally block returns, breaks or continues (each would swallow
          the refusal in flight), and every manager of every with statement
          resolves to one known never to suppress (_may_suppress:
          contextlib.suppress under any alias, and every manager the proof
          cannot resolve, can swallow the refusal);
      (6) no operation of the module can rebind a manager known never to
          suppress, a prefix of its dotted path, an alias of either, or the
          manager itself (_manager_rebinds, fix pass 9): (5) trusts such a
          manager by its name, and _Names still resolves a name whose
          meaning such an operation changes at run time;
      (7) the module holds no namespace-reaching operation (_namespace_reach,
          fix pass 10): a bound over the stated namespace-reaching lists and
          every write through a base the proof cannot resolve, in place of
          relying on (6)'s list of rebinding forms alone."""
    if not isinstance(handler, ast.Name):
        return False
    binds = _bindings(tree, handler.id)
    defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == handler.id]
    if len(defs) != 1 or binds != defs or isinstance(defs[0], ast.AsyncFunctionDef):
        return False
    a = defs[0].args
    if a.posonlyargs or a.kwonlyargs or a.vararg or a.kwarg or a.defaults or len(a.args) != 1:
        return False
    body = defs[0].body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    if len(body) != 1 or not _raise_is_total(body[0], a.args[0].arg):
        return False
    cls = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "NoVerdict"]
    if len(cls) != 1 or _bindings(tree, "NoVerdict") != cls or cls[0].keywords \
            or [ast.dump(b) for b in cls[0].bases] != [ast.dump(ast.Name("Exception", ast.Load()))]:
        return False
    parents = {}
    for n in ast.walk(tree):
        for c in ast.iter_child_nodes(n):
            parents[id(c)] = n
    names = _Names(tree, parents)
    if _manager_rebinds(tree, names):
        return False                      # an operation can rebind a never-suppress manager
    if _namespace_reach(tree, names, file):
        return False                      # an operation can reach a namespace (fix pass 10)
    if names.ref(cls[0].bases[0]) != "builtins.Exception":
        return False                      # NoVerdict's base is not the builtin Exception
    for n in ast.walk(tree):
        if isinstance(n, (ast.Try, getattr(ast, "TryStar", ast.Try))) and any(
                isinstance(x, (ast.Return, ast.Break, ast.Continue)) for s in n.finalbody for x in ast.walk(s)):
            return False
        if isinstance(n, (ast.With, ast.AsyncWith)) and any(_may_suppress(names, it) for it in n.items):
            return False
    for h in ast.walk(tree):
        if not isinstance(h, ast.ExceptHandler):
            continue
        owner = parents.get(id(h))
        while owner is not None and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = parents.get(id(owner))
        if h.type is not None and not _may_catch(names, h.type):
            continue                                  # proven unable to catch NoVerdict
        reraise = len(h.body) == 1 and isinstance(h.body[0], ast.Raise) and h.body[0].exc is None
        rets = [r for s in h.body for r in ast.walk(s) if isinstance(r, ast.Return)]
        refuses = owner is not None and owner.name == "main" and isinstance(h.body[-1], ast.Return) \
            and all(isinstance(r.value, ast.Constant) and r.value.value == 3 for r in rets)
        if not (reraise or refuses):
            return False
    return True


def unwrapped_queries(source: str, file: str = "<source>") -> list:
    """Every reference that can turn a failure into a False/absent answer:
    an os.path status predicate, os.access, a pathlib predicate, a getattr
    on a path module, and an os.walk whose handler is not proven -- through
    any import or assignment alias, called or not. An os.walk row is a
    Reported naming, by `file`, line and kind, every operation of the module
    that can rebind a never-suppress manager (fix pass 9) or reach a
    namespace (fix pass 10)."""
    tree = ast.parse(source)
    aliases = _aliases(tree)
    parents = {}
    for n in ast.walk(tree):
        for c in ast.iter_child_nodes(n):
            parents[id(c)] = n
    out = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.Name, ast.Attribute)) and isinstance(n.ctx, ast.Load):
            r = _resolve(n, aliases)                        # every name the reference can stand for
            if "os.walk" in r:
                call = parents.get(id(n))
                handler = None
                if isinstance(call, ast.Call) and call.func is n:
                    kw = [k.value for k in call.keywords if k.arg == "onerror"]
                    handler = kw[0] if kw else (call.args[2] if len(call.args) > 2 else None)
                if not walk_handler_proven(tree, handler, file):
                    names = _Names(tree, parents)
                    out.append(Reported(n.lineno, "os.walk", file,
                                        sorted(set(_manager_rebinds(tree, names)
                                                   + _namespace_reach(tree, names, file)))))
            for q in sorted(r & QUERY_NAMES - {"os.walk"}):
                out.append((n.lineno, q))
            if not r & QUERY_NAMES and isinstance(n, ast.Attribute) and n.attr in PATHLIB_QUERIES \
                    and _resolve(n.value, aliases) != {"os.path"}:
                out.append((n.lineno, "." + n.attr))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "getattr" and n.args \
                and any(c.split(".")[0] in {"os", "pathlib"} for c in _resolve(n.args[0], aliases)):
            out.append((n.lineno, "getattr"))
    return out


def test_m5_no_path_query_turns_a_failure_into_absence():
    for path in (os.path.join(TOOLS, "review_needles.py"), os.path.join(API, "review_rules.py"),
                 os.path.join(API, "review_boot.py")):
        with open(path, encoding="utf-8") as f:
            assert unwrapped_queries(f.read(), path) == [], path


PLANTED_QUERIES = ["os.path.isdir(p)", "os.path.lexists(p)", "os.path.exists(p)",
                   "os.path.isfile(p)", "os.walk(p)", "pathlib.Path(p).exists()", "os.access(p, 0)"]


@pytest.mark.parametrize("planted", PLANTED_QUERIES)
def test_m5_the_enumeration_catches_each_planted_query(planted):
    assert len(unwrapped_queries("import os\nimport pathlib\nx = " + planted + "\n")) == 1
    assert unwrapped_queries("import os\nx = os.path.join(p)\n") == []


# M5(b): the reviewer's input -- imported and assigned aliases of a predicate
ALIASED = [
    "from os.path import isdir\nx = isdir(p)\n",
    "from os.path import exists as present\nx = present(p)\n",
    "import os.path as osp\nx = osp.isfile(p)\n",
    "from os import path\nx = path.lexists(p)\n",
    "import os\nq = os.path.isdir\nx = q(p)\n",
    "import os\nq = os.path\nr = q\nx = r.isdir(p)\n",
    "import ntpath\nx = ntpath.isdir(p)\n",
    "from os import walk\nx = walk(p)\n",
    "from os import access as can\nx = can(p, 0)\n",
    "import os\nx = getattr(os.path, 'isdir')(p)\n",
    "from pathlib import Path\nq = Path(p).is_dir\nx = q()\n",
]


@pytest.mark.parametrize("planted", ALIASED, ids=["alias%d" % i for i in range(len(ALIASED))])
def test_m5_fix4_an_aliased_query_is_caught(planted):
    assert unwrapped_queries(planted) != [], planted


def test_m5_fix4_alias_controls_are_clean():
    for clean in ("from os.path import join\nx = join(p)\n", "import os.path as osp\nx = osp.basename(p)\n",
                  "import os\nq = os.path.realpath\nx = q(p)\n", "from os import listdir\nx = listdir(p)\n"):
        assert unwrapped_queries(clean) == [], clean


# M5(c): an os.walk handler must be proven to reach the exit-3 refusal
WALK_OK = ("import os\n\n\nclass NoVerdict(Exception):\n    pass\n\n\n"
           "def _walk_error(e):\n    raise NoVerdict(type(e).__name__)\n\n\n"
           "def scan(p):\n    return list(os.walk(p, onerror=_walk_error))\n\n\n"
           "def main(argv):\n    try:\n        scan(argv[0])\n    except NoVerdict:\n"
           "        print('refused')\n        return 3\n    return 0\n")
WALK_BAD = [
    ("lambda_handler", ("onerror=_walk_error", "onerror=lambda e: None")),
    ("none_handler", ("onerror=_walk_error", "onerror=None")),
    ("handler_that_returns", ("    raise NoVerdict(type(e).__name__)\n", "    return None\n")),
    ("handler_other_error", ("    raise NoVerdict(type(e).__name__)\n", "    raise ValueError(e)\n")),
    ("handler_rebound", ("def scan(p):", "_walk_error = print\n\n\ndef scan(p):")),
    ("refusal_swallowed", ("    return list(os.walk(p, onerror=_walk_error))\n",
                           "    try:\n        return list(os.walk(p, onerror=_walk_error))\n"
                           "    except Exception:\n        return []\n")),
    ("refusal_not_three", ("        return 3\n", "        return 0\n")),
    ("refusal_base_changed", ("class NoVerdict(Exception):", "class NoVerdict(OSError):")),
]


def test_m5_fix4_a_proven_walk_handler_is_accepted():
    assert unwrapped_queries(WALK_OK) == []


@pytest.mark.parametrize("name,edit", WALK_BAD, ids=[w[0] for w in WALK_BAD])
def test_m5_fix4_an_unproven_walk_handler_is_refused(name, edit):
    old, new = edit
    assert WALK_OK.count(old) == 1
    assert [k for _l, k in unwrapped_queries(WALK_OK.replace(old, new))] == ["os.walk"], name


def _store_copy(armed, tmp_path):
    store = str(tmp_path / "store")
    shutil.copytree(armed[0], store)
    os.makedirs(os.path.join(store, "tests"))
    with open(os.path.join(store, "tests", "needles.txt"), "w", encoding="utf-8") as f:
        f.write("synthetic_private_identifier\n")
    with open(os.path.join(store, "tests", "public.txt"), "w", encoding="utf-8") as f:
        f.write("a public phrase\n")
    with open(os.path.join(store, "synthetic_private_notes.md"), "w", encoding="utf-8") as f:
        f.write("x\n")
    return store


# each target: a path the derivation queries; a PermissionError there must
# refuse (3), never read as absent
TARGETS = ["revision_dir", "data_dir", "needles_list", "public_list", "tests_dir", "basename_entry"]


@pytest.mark.parametrize("target", TARGETS)
def test_m5_a_status_failure_is_the_exit_3_refusal_never_absence(armed, tmp_path, monkeypatch, capsys, target):
    store = _store_copy(armed, tmp_path)
    rdir = os.path.join(store, "rules-" + armed[1])
    path = {"revision_dir": rdir, "data_dir": os.path.join(rdir, "data"),
            "needles_list": os.path.join(store, "tests", "needles.txt"),
            "public_list": os.path.join(store, "tests", "public.txt"),
            "tests_dir": os.path.join(store, "tests"),
            "basename_entry": os.path.join(store, "synthetic_private_notes.md")}[target]
    monkeypatch.setenv(rn.STORE_ENV, store)
    d = tmp_path / "clean"
    d.mkdir()
    (d / "a.txt").write_text("public\n")
    assert rn.main(["scan-dir", str(d)]) == 0                            # control
    real_stat, real_lstat = os.stat, os.lstat

    def denied(real):
        def call(p, *a, **k):
            if os.path.normcase(os.path.abspath(p)) == os.path.normcase(os.path.abspath(path)):
                raise PermissionError(13, "synthetic", p)
            return real(p, *a, **k)
        return call
    monkeypatch.setattr(rn.os, "stat", denied(real_stat))
    monkeypatch.setattr(rn.os, "lstat", denied(real_lstat))
    assert rn.main(["scan-dir", str(d)]) == 3
    assert "no verdict" in capsys.readouterr().out.splitlines()[-1]


def test_m5_an_unreadable_directory_under_a_scan_refuses(armed, tmp_path, monkeypatch, capsys):
    d = tmp_path / "corpus"
    (d / "sub").mkdir(parents=True)
    (d / "sub" / "a.txt").write_text("public\n")
    assert rn.main(["scan-dir", str(d)]) == 0                            # control
    real = os.scandir

    def denied(p="."):
        if os.path.basename(os.fspath(p)) == "sub":
            raise PermissionError(13, "synthetic", p)
        return real(p)
    monkeypatch.setattr(rn.os, "scandir", denied)
    assert rn.main(["scan-dir", str(d)]) == 3
    assert "no verdict" in capsys.readouterr().out.splitlines()[-1]


def test_m5_the_build_tool_does_not_read_an_unreadable_draft_table_dir_as_absent(tmp_path, monkeypatch):
    draft = tk.write_draft(str(tmp_path / "draft"))
    os.makedirs(os.path.join(draft, "data"))
    store = str(tmp_path / "store")
    os.makedirs(store)
    real = os.stat

    def denied(p, *a, **k):
        if os.path.basename(os.fspath(p)) == "data":
            raise PermissionError(13, "synthetic", p)
        return real(p, *a, **k)
    monkeypatch.setattr(rr.os, "stat", denied)
    with pytest.raises(PermissionError):
        rr.build_revision(draft, store, "synthetic")
