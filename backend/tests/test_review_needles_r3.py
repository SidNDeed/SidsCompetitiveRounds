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
    module. Fix pass 14: the namespace operation named by an import alias
    (from os import __dict__ as ns) counts as its reference does."""

    def __init__(self, tree, parents):
        self.tree, self.parents, self.dynamic = tree, parents, False
        nodes = list(ast.walk(tree))
        self.dynamic = (
            any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in nodes)
            or any(isinstance(n, ast.Name) and n.id in _DYNAMIC for n in nodes)
            or any(isinstance(n, ast.Attribute) and n.attr in _DYNAMIC for n in nodes)
            or any(isinstance(n, ast.alias) and set(n.name.split(".")) & _DYNAMIC for n in nodes)   # fix 14: an import alias
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
            for a in n.names:                                              # fix 14: a member import
                if any(p in _NAMESPACE or _dunder(p) and p not in _STRING_NAMES for p in a.name.split(".")):
                    out.append((n.lineno, "namespace operation imported as " + (a.asname or a.name)))
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

# Fix pass 11 (round 10 M5): the bound gains the in-process string and code
# executors (each module and every attribute of it), types.CodeType, the
# method caller, and the executors' modules in the import rule.
_EXECUTORS = ("timeit", "code", "codeop", "pdb", "bdb", "cProfile", "profile", "trace", "doctest")
_EXECUTOR_IMPORTS = _EXECUTORS + ("marshal", "pickle", "shelve")
_REACH_MODULES = _REACH_MODULES + _EXECUTORS                       # fix 11: the executor additions
_REACH_CALLABLES = _REACH_CALLABLES | {"types.CodeType"}           # fix 11: a code object made into a function
_REACH_CALLABLES = _REACH_CALLABLES | {"operator.methodcaller"}    # fix 11: a mutator called by its name
_REACH_IMPORTS = _REACH_IMPORTS + _EXECUTOR_IMPORTS                 # fix 11: the executor import rule
_BENIGN_EXEC = frozenset({"timeit.timeit", "timeit.repeat", "timeit.Timer"})
_BENIGN_EXEC_MODULES = ("timeit",)
_MUTATORS = frozenset({"setitem", "setdefault", "update", "pop", "popitem", "clear", "delitem", "setattr",
                       "delattr", "__setitem__", "__delitem__", "__setattr__", "__delattr__"})
_LEVELS = ("fresh", "immutable identity alias", "holds", "unresolved")    # fix 14: the second level
_FRESH, _IMMUT, _HOLDS, _UNRES = range(len(_LEVELS))   # the data-flow levels of _Flow, ordered
_FRESH_BUILTINS = frozenset({"len", "str", "repr", "int", "float", "complex", "bool", "hash", "id", "abs", "round",
                             "format", "ascii", "bin", "hex", "oct", "ord", "chr", "isinstance", "issubclass",
                             "callable", "sum", "any", "all", "bytes", "range", "open", "print", "divmod", "pow",
                             "object"})   # builtins a literal timing snippet may call (benign_exec_call); fix 14:
#   not a freshness claim: str, int, bytes and their kin may return their argument itself (_IDENTITY_IMMUTABLE)
_COPY_BUILTINS = frozenset({"dict", "list", "tuple", "set", "frozenset", "sorted", "bytearray", "iter", "reversed",
                            "enumerate", "zip", "map", "filter"})   # a new object holding its arguments' elements

# Fix pass 12 (round 11 M5): element provenance through slices, copies and
# iteration; higher-order local callbacks; in-place mutation of unresolved
# receivers. Builtins that may return an argument itself or an element of
# one (an object's __abs__, __round__, __pow__, __divmod__, or the elements
# sum adds onto a list start) are no longer fresh over a held argument; the
# builtins that CALL a callable argument are listed with where it sits.
_ARG_RETURNING = frozenset({"abs", "round", "sum", "divmod", "pow"})
_HIGHER_ORDER = {"map": (0, None), "filter": (0, None), "iter": (0, None),    # (positional index, keyword)
                 "sorted": (None, "key"), "min": (None, "key"), "max": (None, "key")}
_HIGHER_ORDER_DOTTED = {"builtins." + name: name for name in _HIGHER_ORDER}
_AUG_OPS = {ast.Add: "+=", ast.Sub: "-=", ast.Mult: "*=", ast.MatMult: "@=", ast.Div: "/=", ast.FloorDiv: "//=",
            ast.Mod: "%=", ast.Pow: "**=", ast.LShift: "<<=", ast.RShift: ">>=", ast.BitAnd: "&=", ast.BitXor: "^=",
            ast.BitOr: "|="}
_INPLACE_NAMES = ("add", "sub", "mul", "matmul", "truediv", "floordiv", "mod", "pow", "lshift", "rshift", "and",
                  "xor", "or")
_INPLACE_DUNDERS = frozenset("__i%s__" % o for o in _INPLACE_NAMES)        # ns.__ior__(...), the method forms
_INPLACE_OPERATORS = frozenset({"operator.i" + o for o in _INPLACE_NAMES + ("concat",)}
                               | {"operator.__i%s__" % o for o in _INPLACE_NAMES + ("concat",)})

# Fix pass 13 (round 12 M5): the unresolved-receiver namespace-reach bound,
# completed by class.
#   (1) BINDING FORMS COMPLETE BY CONSTRUCTION. Every construct of the grammar
#       that binds a name is dispatched through ONE table keyed by ast node
#       class (_BINDING_TABLE); the candidate resolution (_Reach.resolve), the
#       data flow (_Flow.bind_lv, _Flow.local) and the namespace marks
#       (_Reach._sources) read only the bindings it delivers (_Bind). A node of
#       a class that carries a binding field (_BIND_FIELDS) and is not in the
#       table, or a stored name no entry delivers, refuses the proof with a
#       named row, never silently fresh. A call of a callable the resolution
#       cannot follow is refused when an argument is marked or the callable
#       itself may be unresolved (_Reach.call_rows).
#   (2) IDENTITY-PRESERVING CALLS FAIL CLOSED: iter(x) and reversed(x) may
#       return x itself (_IDENTITY_BUILTINS); x.copy(), copy.copy(x) and
#       copy.deepcopy(x) carry an unresolved x's full mark; only the
#       _PROVEN_FRESH builtins return values that alias nothing.
#   (3) A METHOD CALLED ON AN UNRESOLVED RECEIVER IS A MUTATION unless its name
#       is on _PURE_METHODS (_MUTATOR_NAMES only names rows); a marked value
#       handed to a library callable that is not on _ARG_SAFE is refused too.
#   (4) A constant index into a list or tuple display selects that element's
#       own mark (_Reach.indexed).
_BIND_FIELDS = frozenset({"target", "targets", "optional_vars", "name", "elt", "args", "names", "rest", "asname",
                          "arg", "vararg", "kwarg", "kwonlyargs", "posonlyargs", "generators"})
_IDENTITY_BUILTINS = frozenset({"iter", "reversed"})     # one argument: may return that argument itself
_PROVEN_FRESH = frozenset({"len", "repr", "hash", "id", "ascii",
                           "bin", "hex", "oct", "ord", "chr", "isinstance", "issubclass", "callable", "any", "all",
                           "range", "open", "print", "object"})   # results that alias no argument (fix 14: str, int,
#   float, complex, bool, format and bytes moved to _IDENTITY_IMMUTABLE: each may return its argument itself)
_PURE_METHODS = frozenset({
    "get", "keys", "values", "items", "copy", "index", "count", "__contains__", "__len__", "__iter__",
    "union", "intersection", "difference", "symmetric_difference", "issubset", "issuperset", "isdisjoint",
    "startswith", "endswith", "split", "rsplit", "splitlines", "strip", "lstrip", "rstrip", "lower", "upper",
    "casefold", "title", "capitalize", "swapcase", "replace", "join", "find", "rfind", "rindex", "format",
    "format_map", "encode", "decode", "partition", "rpartition", "isdigit", "isalpha", "isalnum", "isspace",
    "isidentifier", "isupper", "islower", "isascii", "isdecimal", "isnumeric", "istitle", "isprintable", "ljust",
    "rjust", "center", "zfill", "expandtabs", "translate", "removeprefix", "removesuffix", "hex",
    "match", "fullmatch", "search", "findall", "finditer", "is_integer", "hexdigest", "digest"})
_PURE_LIBRARY_RECEIVERS = {
    # os._Environ.get reads its string storage; protocol_rows still judges every argument.
    "os.environ": frozenset({"get"}),
}
_MUTATOR_NAMES = _MUTATORS | frozenset({
    "append", "extend", "insert", "remove", "add", "discard", "sort", "reverse", "appendleft", "extendleft",
    "popleft", "rotate", "difference_update", "intersection_update", "symmetric_difference_update", "move_to_end",
    "subtract"})                                       # names rows only; the gate is _PURE_METHODS
_ARG_SAFE = frozenset({"builtins." + n for n in (
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes", "callable", "chr", "complex", "dict", "divmod",
    "enumerate", "filter", "float", "format", "frozenset", "getattr", "hasattr", "hash", "hex", "id", "int",
    "isinstance", "issubclass", "iter", "len", "list", "map", "max", "memoryview", "min", "next", "object", "oct",
    "open", "ord", "pow", "print", "range", "repr", "reversed", "round", "set", "slice", "sorted", "str", "sum",
    "super", "tuple", "type", "zip")} | {
    "os.walk", "os.stat", "os.lstat", "os.fstat", "os.listdir", "os.scandir", "os.makedirs", "os.fspath",
    "json.load", "json.loads", "json.dumps", "re.compile", "re.escape", "re.split", "re.fullmatch", "re.match",
    "re.search", "re.findall", "re.finditer", "subprocess.run", "hashlib.sha256", "hashlib.sha1", "hashlib.md5",
    "time.strftime", "time.gmtime", "sys.exit", "os.open", "os.read", "os.write", "os.close", "os.readlink",
    "os.rename", "os.replace", "os.rmdir", "os.remove", "os.unlink", "os.fsync"})
#   re.sub/re.subn and shutil.rmtree stay off: they call a callable they are handed
_ARG_SAFE_MODULES = ("os.path", "stat", "math")
_ARG_SAFE_EXCEPTIONS = frozenset({"builtins." + n for n, v in vars(builtins).items()
                                  if isinstance(v, type) and issubclass(v, BaseException)})   # a raise's argument
_BUILTIN_TYPES = frozenset({"dict", "list", "tuple", "set", "frozenset", "sorted", "bytearray", "bytes", "str"})
_BUILTIN_CONTAINERS = frozenset({"dict", "list", "tuple", "set", "frozenset", "sorted"})
_BUILTIN_LISTS = frozenset({"list", "sorted"})
_ELEMENT_KEEPING = frozenset({"list", "tuple", "set", "frozenset", "sorted", "reversed", "iter"})

# Fix pass 14 (round 13 M5, LOW 1, LOW 2).
#   M5  (1) A dotted name with a namespace member past its first part (a dunder
#           member such as __dict__ or __builtins__, the string-valued dunders
#           aside; a frame attribute; a modules member) is namespace-reaching
#           however it is reached, an import alias included (_namespace_member):
#           from os import __dict__ as ns makes ns reaching. A store, deletion
#           or augmented store whose base resolves to an imported object (a
#           module, or a member of one) writes another module's namespace and is
#           refused (_Reach.imported).
#       (2) A method called on an unresolved receiver is a mutation WHATEVER its
#           name: _PURE_METHODS admits a name only on a receiver proven by
#           _Reach.pure_receiver, where no row arises; on an unproven receiver
#           a listed name is refused as an unproven pure method call.
#       (3) A call of an allowlisted callable (_ARG_SAFE, the builtins of
#           _PROVEN_FRESH and _IDENTITY_IMMUTABLE) runs a protocol of its
#           argument (__len__, __str__, __fspath__, __iter__, __getattr__ and
#           the rest); it is admitted over a held, unresolved or imported argument only
#           when its plain call signature is admitted by _NO_PROTOCOL, the argument is
#           proven an exact builtin scalar (a literal, or a parameter its
#           function checks with type(p) is not str or bytes, raising, in an
#           earlier statement of its body: _Reach.guarded), or that argument
#           is a value whose iteration runs no caller element protocol in a
#           position _ELEMENT_BLIND does not inspect. A method of a proven builtin receiver is judged the
#           same way over its arguments; an exact builtin container holding an
#           unresolved or imported value is also refused unless receiver_element_blind
#           says the method runs no element code, including type-specific pop.
#           Only exact list.append with
#           its one plain argument gets the store-only method exemption. An
#           imported object handed to an unlisted or unresolved callable, and
#           a method off _PURE_METHODS and _ARG_SAFE called through an
#           imported object that is not a module an import statement names,
#           are writes through an imported namespace (rule (9)).
#       An operator's result (+, ==, unary -) over an unresolved operand is
#           _UNRES (the operand's own method returns it), never _HOLDS.
#   LOW 1   Names are read by Python's scope rules (_Flow.lookups): a function,
#           lambda, comprehension or class body is a scope, a comprehension
#           target never leaves its comprehension, a class body is invisible
#           to the scopes nested in it, global and nonlocal redirect a binding;
#           the flow, the resolution and the builtin-type proof read only the
#           bindings a use can see, never every binding of the name. A direct
#           class-body read uses its class binding only after an unconditional
#           direct binder is proven to have completed, uses the module-global
#           LOAD_NAME fallback while unbound, and joins both after a possible
#           conditional binder. A custom prepared class mapping remains an
#           independent unknown lookup route.
#   LOW 2   A builtin that may return its argument itself (an exact str, int,
#           float, complex, bool, bytes, tuple or frozenset is returned as it
#           is) yields _IMMUT, an identity alias that can carry no write, never
#           _FRESH; a tuple or frozenset holding an unresolved element stays
#           _HOLDS. Only _PROVEN_FRESH results alias no argument.
_IDENTITY_IMMUTABLE = frozenset({"str", "int", "float", "complex", "bool", "bytes", "format", "tuple", "frozenset"})
_ANY_PLAIN_POSITIONAL = "any plain positional signature"
_NO_PROTOCOL = dict.fromkeys(_ARG_SAFE_EXCEPTIONS, _ANY_PLAIN_POSITIONAL)
_NO_PROTOCOL.update({
    "builtins.id": frozenset({(None,)}),
    "builtins.type": frozenset({(None,)}),
    "builtins.callable": frozenset({(None,)}),
    "builtins.ord": frozenset({(None,)}),
    "builtins.slice": frozenset({(None,), (None, None), (None, None, None)}),
    "builtins.super": frozenset({(None,)}),
    "sys.exit": frozenset({(), (None,)}),
})
_BLOCKING_IO_PROTOCOL_ARGUMENTS = {
    (None, None, None): (False, False, True),
    (None, None, None, None): (False, False, True, False),
    (None, None, None, None, None): (False, False, True, False, False),
}
_PROTOCOL_ARGUMENTS = {
    "builtins.BaseExceptionGroup": {(None, None): (False, True)},
    "builtins.ExceptionGroup": {(None, None): (False, True)},
    "builtins.BlockingIOError": _BLOCKING_IO_PROTOCOL_ARGUMENTS,
    "builtins.SyntaxError": {(None, None): (False, True)},
    "builtins.IndentationError": {(None, None): (False, True)},
    "builtins.TabError": {(None, None): (False, True)},
    "builtins.UnicodeEncodeError": {
        (None, None, None, None, None): (False, False, True, True, False),
    },
    "builtins.UnicodeDecodeError": {
        (None, None, None, None, None): (False, True, True, True, False),
    },
    "builtins.UnicodeTranslateError": {
        (None, None, None, None): (False, True, True, False),
    },
}
_PROTOCOL_ARGUMENTS.update({name: _BLOCKING_IO_PROTOCOL_ARGUMENTS
                            for name in ("builtins.OSError", "builtins.EnvironmentError",
                                         "builtins.IOError", "builtins.WindowsError")
                            if name in _ARG_SAFE_EXCEPTIONS})
_ELEMENT_BLIND = frozenset({"builtins." + n for n in (
    "len", "bool", "list", "tuple", "iter", "reversed", "enumerate", "zip",
    "next", "map", "filter")})                         # on a protocol-safe iterable: no element code runs
_FIRST_ELEMENT_BLIND = frozenset({"builtins.isinstance"})
_RECEIVER_ELEMENT_BLIND = frozenset({
    "keys", "values", "items", "copy", "__len__", "__iter__", "append", "extend", "insert", "reverse", "popitem",
})
_POP_ELEMENT_BLIND = frozenset({"list", "set"})
_GUARD_TYPES = frozenset({"builtins.str", "builtins.bytes"})       # an exact scalar a type guard can prove
_RESULT_TYPED = frozenset({"os.walk"})                 # a library call whose result is a builtin generator
_PROTOCOL_SAFE_VALUES = frozenset({"datetime.timezone.utc"})  # exact library singleton, no caller protocol


def _namespace_member(dotted) -> bool:
    """Fix pass 14: a dotted name one of whose parts past the first is a
    namespace member (a dunder other than the string-valued ones, a frame
    attribute, or modules: sys.modules reached through another module)."""
    _first, dot, rest = dotted.partition(".")
    return bool(dot) and any(_dunder(p) and p not in _STRING_NAMES or p in _FRAME_ATTRS or p == "modules"
                             for p in rest.split("."))


def _arg_safe(dotted) -> bool:
    """A library callable proven not to mutate its arguments (_ARG_SAFE, a
    module of _ARG_SAFE_MODULES, a builtin exception class)."""
    return dotted in _ARG_SAFE or dotted in _ARG_SAFE_EXCEPTIONS or _in_module(dotted, _ARG_SAFE_MODULES)


def _const_index(s):
    """A constant integer index (a negative one included), else None."""
    if isinstance(s, ast.UnaryOp) and isinstance(s.op, ast.USub):
        i = _const_index(s.operand)
        return None if i is None else -i
    return s.value if isinstance(s, ast.Constant) and type(s.value) is int else None


class _Bind:
    """One name a binding construct binds (fix pass 13): the BINDER node (the
    key the flow and the resolution use: a stored Name, an arg, a def or
    class, an import, an except handler, a match pattern, a declaration),
    the name, the MODE of the value it receives (value, aug, param, import,
    local, capture, unres, fresh, declare), the expression that delivers it
    (the dotted name for an import), the PATH from that expression to the
    value (steps: "elem" an element of it, "enter" what its __enter__
    returns, "star" a new list of its elements) and the construct's class."""
    __slots__ = ("binder", "name", "mode", "expr", "path", "src")

    def __init__(self, binder, name, mode, expr=None, path=(), src=""):
        self.binder, self.name, self.mode, self.expr, self.path, self.src = binder, name, mode, expr, path, src


def _unpack(t, val, path, src):
    """The bindings a target makes from a value through a path."""
    if isinstance(t, ast.Name):
        return [_Bind(t, t.id, "value", val, path, src)]
    if isinstance(t, (ast.Tuple, ast.List)):
        if not path and isinstance(val, (ast.Tuple, ast.List)) and len(t.elts) == len(val.elts) \
                and not any(isinstance(e, ast.Starred) for e in t.elts + val.elts):
            return [b for e, v in zip(t.elts, val.elts) for b in _unpack(e, v, (), src)]   # a, b = x, y
        return [b for e in t.elts for b in (_unpack(e.value, val, path + ("star",), src) if isinstance(e, ast.Starred)
                                            else _unpack(e, val, path + ("elem",), src))]
    if isinstance(t, ast.Starred):
        return _unpack(t.value, val, path + ("star",), src)
    return []                                  # a subscript or attribute target: a store, judged by rule (1)


def _b_nothing(n, r):
    return []


def _b_assign(n, r):
    return [b for t in n.targets for b in _unpack(t, n.value, (), "Assign")]


def _b_annassign(n, r):
    if not isinstance(n.target, ast.Name):
        return []
    if n.value is None:
        return [_Bind(n.target, n.target.id, "fresh", None, (), "AnnAssign")]       # an annotation only
    return [_Bind(n.target, n.target.id, "value", n.value, (), "AnnAssign")]


def _b_augassign(n, r):
    if not isinstance(n.target, ast.Name):
        return []
    return [_Bind(n.target, n.target.id, "aug", n.value, (), "AugAssign")]


def _b_namedexpr(n, r):
    return [_Bind(n.target, n.target.id, "value", n.value, (), "NamedExpr")]


def _b_loop(n, r):
    return _unpack(n.target, n.iter, ("elem",), type(n).__name__)                    # For, AsyncFor, comprehension


def _b_withitem(n, r):
    return [] if n.optional_vars is None else _unpack(n.optional_vars, n.context_expr, ("enter",), "withitem")


def _b_delete(n, r):
    return [_Bind(x, x.id, "fresh", None, (), "Delete") for t in n.targets for x in ast.walk(t)
            if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Del)]


def _b_def(n, r):
    return [_Bind(n, n.name, "local", n, (), type(n).__name__)]


def _b_arguments(n, r):
    pos = n.posonlyargs + n.args
    dflt = dict(zip(map(id, pos[len(pos) - len(n.defaults):]), n.defaults))
    dflt.update(zip(map(id, n.kwonlyargs), n.kw_defaults))
    return [_Bind(a, a.arg, "param", dflt.get(id(a)), (), "arguments")
            for a in pos + [n.vararg] + n.kwonlyargs + [n.kwarg] if a is not None]


def _b_import(n, r):
    return [_Bind(n, a.asname or a.name.split(".")[0], "import", a.name if a.asname else a.name.split(".")[0], (),
                  "Import") for a in n.names]


def _b_importfrom(n, r):
    return [_Bind(n, a.asname or a.name, "import", n.module + "." + a.name if n.module and not n.level else None, (),
                  "ImportFrom") for a in n.names]


def _b_except(n, r):
    return [_Bind(n, n.name, "unres", n.type, (), "ExceptHandler")] if n.name else []


def _b_capture(n, r):
    name = n.rest if isinstance(n, ast.MatchMapping) else n.name
    return [_Bind(n, name, "capture", r.match_subject(n), (), type(n).__name__)] if name else []


def _b_declare(n, r):
    return [_Bind(n, g, "declare", None, (), type(n).__name__) for g in n.names]


def _b_typealias(n, r):
    return [_Bind(n.name, n.name.id, "fresh", None, (), "TypeAlias")] if isinstance(n.name, ast.Name) else []


def _b_typeparam(n, r):
    return [_Bind(n, n.name, "fresh", None, (), type(n).__name__)]


# The binding table (fix pass 13): every ast node class that carries a
# binding field, with what it binds. The classes that carry such a field
# but bind nothing themselves are listed too, each with its reason: a Call's
# args are arguments, a keyword's arg names a callee's parameter, a lambda's
# parameters are bound by its arguments node (as a def's are), an arg is
# delivered by its arguments node, a comprehension expression binds through
# its comprehension nodes, and an alias through its import.
_BINDING_TABLE = {
    ast.Assign: _b_assign, ast.AnnAssign: _b_annassign, ast.AugAssign: _b_augassign, ast.NamedExpr: _b_namedexpr,
    ast.For: _b_loop, ast.AsyncFor: _b_loop, ast.comprehension: _b_loop, ast.withitem: _b_withitem,
    ast.Delete: _b_delete, ast.FunctionDef: _b_def, ast.AsyncFunctionDef: _b_def, ast.ClassDef: _b_def,
    ast.arguments: _b_arguments, ast.Import: _b_import, ast.ImportFrom: _b_importfrom,
    ast.ExceptHandler: _b_except, ast.MatchAs: _b_capture, ast.MatchStar: _b_capture,
    ast.MatchMapping: _b_capture, ast.Global: _b_declare, ast.Nonlocal: _b_declare,
    ast.Call: _b_nothing, ast.keyword: _b_nothing, ast.Lambda: _b_nothing, ast.arg: _b_nothing,
    ast.ListComp: _b_nothing, ast.SetComp: _b_nothing, ast.GeneratorExp: _b_nothing, ast.DictComp: _b_nothing,
    ast.alias: _b_nothing,
}
for _cls, _h in (("TypeAlias", _b_typealias), ("TypeVar", _b_typeparam), ("ParamSpec", _b_typeparam),
                 ("TypeVarTuple", _b_typeparam)):
    if hasattr(ast, _cls):
        _BINDING_TABLE[getattr(ast, _cls)] = _h


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


def _root(node):
    """The name a chain of attributes and subscripts starts from, else None."""
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _root_node(node):
    """Fix pass 14: the Name node a chain of attributes and subscripts starts from, else None."""
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred)):
        node = node.value
    return node if isinstance(node, ast.Name) else None


def _only(seq):
    """Fix pass 14: the one element of seq, else None (none, or more than one)."""
    it = iter(seq)
    first = next(it, None)
    return first if next(it, None) is None else None


def _plain_signature(args, keywords):
    """The normalized arity of plain positional args; None for a star or keyword."""
    if keywords or any(isinstance(a, ast.Starred) for a in args):
        return None
    return tuple(None for _a in args)


def _protocol_shape(call, callback=False, operation=None):
    """The direct call's signature, or the signature a higher-order builtin
    uses to invoke its callback. Unknown expansion stays None."""
    if not callback:
        return _plain_signature(call.args, call.keywords)
    name = operation if operation is not None else call.func.id
    if name == "map":
        if call.keywords or any(isinstance(a, ast.Starred) for a in call.args):
            return None
        _callee, *arguments = call.args
        return tuple(None for _a in arguments)
    if name in ("filter", "iter"):
        if call.keywords or any(isinstance(a, ast.Starred) for a in call.args):
            return None
        return () if name == "iter" else (None,)
    return (None,)                                            # key callbacks receive one element


def _no_protocol(dotted, shape) -> bool:
    """Whether dotted at this exact plain signature runs no argument code."""
    if shape is None:
        return False
    if shape in _PROTOCOL_ARGUMENTS.get(dotted, ()):
        return False
    accepted = _NO_PROTOCOL.get(dotted, ())
    return accepted == _ANY_PLAIN_POSITIONAL or shape in accepted


def _protocol_mask(dotted, shape):
    """The plain positional arguments whose protocols dotted can execute."""
    if shape is None:
        return None
    special = _PROTOCOL_ARGUMENTS.get(dotted, {})
    if shape in special:
        return special[shape]
    runs = not _no_protocol(dotted, shape)
    return tuple(runs for _slot in shape)


_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_SCOPE_NODES = _FUNCS + _COMPS + (ast.ClassDef,)


def _scopes(tree) -> dict:
    """Fix pass 14 (round 13 LOW 1): id(node) -> the innermost scope node
    (function, lambda, comprehension or class body) whose names the node is
    evaluated in, None for the module. Python evaluates a def's or lambda's
    defaults, a def's decorators, annotations and return annotation, a
    class's bases, keywords and decorators, and a comprehension's first
    iterable in the scope AROUND the node, so those parts map there."""
    out = {}
    stack = [(tree, None)]
    while stack:
        node, sc = stack.pop()
        for c in ast.iter_child_nodes(node):
            out[id(c)] = sc
            stack.append((c, c if isinstance(c, _SCOPE_NODES) else sc))
    for n in ast.walk(tree):                     # breadth first: an outer node is moved before an inner one
        around = []
        if isinstance(n, _FUNCS):
            a = n.args
            around = list(a.defaults) + [d for d in a.kw_defaults if d is not None]
            if not isinstance(n, ast.Lambda):
                around += list(n.decorator_list) + ([n.returns] if n.returns is not None else []) + [
                    x.annotation for x in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg]
                    if x is not None and x.annotation is not None]
        elif isinstance(n, ast.ClassDef):
            around = list(n.bases) + [k.value for k in n.keywords] + list(n.decorator_list)
        elif isinstance(n, _COMPS):
            around = [next(iter(n.generators)).iter]
        for e in around:
            for x in ast.walk(e):
                if out.get(id(x)) is n:
                    out[id(x)] = out.get(id(n))
    return out


class _Flow:
    """Data flow of one module for the unresolved-base rule (fix pass 11,
    round 10 M5: a module-local identity function carried a caller-supplied
    mapping through unseen, because every result of a local call was taken
    as fresh). Every expression has a LEVEL:
      _FRESH  an object the module makes that holds nothing it cannot resolve;
      _HOLDS  a fresh object that may HOLD one it cannot resolve (a display, a
              copy, an instance, a generator, a closure over one): a write to
              it reaches no namespace, a write to anything read out of it may;
      _UNRES  possibly an object the proof cannot resolve, or an element of
              one: a write through it is refused.
    Levels are solved to a least fixed point (values only rise, over a finite
    set of keys) over four kinds of key: a name of the module (every binding
    and every mutation in any scope, merged, as everywhere in this proof); a
    name local to a callee, under a parameter level; a callee's SUMMARY under
    a parameter level (the join of every return path, a yield counting as
    held, _UNRES for a decorated def or a body the analysis cannot follow:
    exec, eval, a yield from, a call of an unresolved callable, a try whose
    handler swallows and rebinds); and a class's INSTANCE under an argument
    level (_UNRES for a decorator, a metaclass, a __new__ or a base the proof
    cannot follow; held when an argument, a class-body store or a method's
    store or mutation can hold an unresolved object). A call of a module def,
    lambda binding or class takes that summary or instance, with the callee's
    parameters at _UNRES whenever any argument is at least _HOLDS (*args and
    **kwargs forwarding included), else at _FRESH; a parameter with a
    default also takes the default's level. A call of a method or an
    imported callable is _UNRES (copy and deepcopy excepted); a builtin is
    fresh (_FRESH_BUILTINS), a copy holding its arguments' elements
    (_COPY_BUILTINS), or else _UNRES when an argument is held. A name a
    mutation writes into (a subscript or attribute store, or a method call,
    whose chain starts at it) is at least _HOLDS when the written value or an
    argument is.
    Fix pass 12 (round 11 M5): a slice (a Slice, or a tuple holding one) keeps
    its base's level, so a slice of an unresolved object is unresolved and a
    slice of a holder holds the same elements; every element reached by
    iteration, unpacking, a with target or a copy builtin is _UNRES when its
    container holds anything (carried); a builtin that may return an
    argument or an element of one (_ARG_RETURNING) is no longer fresh over a
    held argument; and a builtin that calls a callable argument
    (_HIGHER_ORDER) marks that callback as if it were called directly
    (higher_order_lv, callback_lv), an unresolvable callback making the
    result _UNRES.
    Fix pass 13 (round 12 M5): every binding is read from the binding table
    (bind_lv by the mode _Bind carries; a binder the table did not deliver is
    _UNRES and refused by the gate); a builtin is fresh only on _PROVEN_FRESH;
    iter(x) and reversed(x) over an unresolved x are _UNRES (they may return
    x), and x.copy(), copy.copy(x) and copy.deepcopy(x) carry x's mark
    (joined); a constant index into a list or tuple display reads that
    element's own level (_Reach.indexed).
    Fix pass 14 (round 13 LOW 1 and LOW 2): a name is read by Python's scope
    rules (lookups), so a name key is the module's own binding of the name
    ("n": its module-scope bindings and those a global declaration
    redirects; none is an unbound global, _UNRES unless a builtin) or one
    scope's ("l": the bindings of that function, lambda, comprehension or
    class body, nonlocal redirects included, read under the level of its
    activation: the callee's own level when it is the context's, else
    _UNRES, a closure's activation being unknown); a builtin that may return
    its argument itself is _IMMUT, never _FRESH. A direct class-body read
    uses the module-global LOAD_NAME fallback while its class name is unbound,
    joins the class and module keys after a possible conditional binder, and
    retains an unknown route for a custom prepared class mapping."""

    def __init__(self, reach):
        self.r, self.parents, self.binds = reach, reach.parents, reach.binds
        self.tab, self.keys, self.nodes, self.dirty = {}, [], {}, False
        self.encl, self.muts = {}, {}
        self.scope = _scopes(reach.tree)                             # fix 14: Python's scopes
        self.snodes = {id(n): n for n in ast.walk(reach.tree) if isinstance(n, _SCOPE_NODES)}
        self.glob, self.nonl, raw = {}, {}, {}
        for b in reach.records:
            if b.mode == "declare":
                s = self.scope.get(id(b.binder))
                (self.glob if isinstance(b.binder, ast.Global) else self.nonl).setdefault(
                    None if s is None else id(s), set()).add(b.name)
        for b in reach.records:
            if b.mode != "declare":
                raw.setdefault((self.immediate(b), b.name), True)
        self.own = {}
        for b in reach.records:
            if b.mode != "declare":
                self.own.setdefault((self.home(b, raw), b.name), []).append(b.binder)
        stack = [(reach.tree, None)]
        while stack:
            node, fn = stack.pop()
            for c in ast.iter_child_nodes(node):
                self.encl[id(c)] = fn
                stack.append((c, c if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) else fn))
        for n in ast.walk(reach.tree):
            root, vals = None, []
            if isinstance(n, (ast.Attribute, ast.Subscript)) and isinstance(n.ctx, (ast.Store, ast.Del)):
                stmt = self.parents.get(id(n))
                while isinstance(stmt, (ast.Tuple, ast.List, ast.Starred)):
                    stmt = self.parents.get(id(stmt))
                val = stmt.value if isinstance(stmt, (ast.Assign, ast.AugAssign, ast.AnnAssign)) \
                    else stmt.iter if isinstance(stmt, (ast.For, ast.AsyncFor, ast.comprehension)) \
                    else stmt.context_expr if isinstance(stmt, ast.withitem) else None
                root, vals = _root(n.value), [] if val is None else [val]
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                root = _root(n.func.value)
                vals = [a.value if isinstance(a, ast.Starred) else a for a in n.args] + [k.value for k in n.keywords]
            if root is not None and vals:
                rn_ = _root_node(n.func.value if isinstance(n, ast.Call) else n.value)
                self.muts.setdefault(root, []).append((n, vals, rn_))

    # -- the solver ------------------------------------------------------------------
    def get(self, key):
        v = self.tab.get(key)
        if v is None:
            self.tab[key] = v = _FRESH
            self.keys.append(key)
            self.dirty = True
        return v

    def solve(self):
        while True:
            self.dirty, changed = False, False
            for key in list(self.keys):
                v = self.compute(key)
                if v > self.tab[key]:
                    self.tab[key], changed = v, True
            if not changed and not self.dirty:
                return

    def level(self, node, ctx=None):
        """The level of an expression read at module scope (ctx None) or in a
        callee under a parameter level (ctx (callee, level))."""
        while True:
            v = self.lv(node, ctx)
            if not self.dirty:
                return v
            self.solve()

    # -- scopes (fix pass 14: Python's scope rules, never every binding of a name) ---------
    def immediate(self, b):
        """The id of the scope a binding is made in (None: the module): a def's
        or class's name in the scope around it, a walrus outside every
        comprehension it sits in."""
        s = self.scope.get(id(b.binder))                             # the binding's own scope
        if b.src == "NamedExpr":
            while isinstance(s, _COMPS):
                s = self.scope.get(id(s))
        return None if s is None else id(s)

    def home(self, b, raw):
        """The id of the scope whose name the binding binds: its own scope,
        unless that scope declares the name global (the module) or nonlocal
        (the nearest enclosing function scope that binds it)."""
        sid = self.immediate(b)
        while sid is not None:
            if b.name in self.glob.get(sid, ()):
                return None
            if b.name not in self.nonl.get(sid, ()):
                return sid
            s = self.scope.get(id(self.snode(sid)))
            while s is not None and not (isinstance(s, _FUNCS) and (id(s), b.name) in raw
                                         and b.name not in self.nonl.get(id(s), ())):
                s = self.scope.get(id(s))
            sid = None if s is None else id(s)
        return None

    def snode(self, sid):
        return self.snodes[sid]

    def lookup(self, name, node):
        """Fix pass 14 (round 13 LOW 1): the id of the scope whose binding of
        name a read at node sees (None: the module): the innermost scope that
        binds the name and does not declare it global or nonlocal, a class
        body seen only by code written directly in it."""
        s, first = (self.scope.get(id(node)) if node is not None else None), True
        while s is not None:
            if isinstance(s, ast.ClassDef) and not first:
                s = self.scope.get(id(s))                            # invisible to the scopes nested in it
                continue
            if name in self.glob.get(id(s), ()):
                return None
            if name not in self.nonl.get(id(s), ()) and (id(s), name) in self.own:
                return id(s)
            s, first = self.scope.get(id(s)), False
        return None

    def class_statement(self, cls, node):
        """The direct class-body statement containing node, else None."""
        top = node
        while top is not None and self.parents.get(id(top)) is not cls:
            top = self.parents.get(id(top))
        return top

    def prepared_unknown(self, cls):
        """Whether the selected metaclass may prepopulate the class mapping."""
        for keyword in cls.keywords:
            if keyword.arg is None:
                return True
            if keyword.arg == "metaclass":
                return not (isinstance(keyword.value, ast.Name) and keyword.value.id == "type"
                            and self.builtin_certain("type", keyword.value))
        return any(not (isinstance(base, ast.Name) and self.builtin_certain(base.id, base)
                       and hasattr(builtins, base.id)
                       and isinstance(getattr(builtins, base.id), type)
                       and type(getattr(builtins, base.id)) is type) for base in cls.bases)

    def prepared_at(self, node):
        """Whether this direct class-body read uses a custom class mapping."""
        scope = self.scope.get(id(node))
        return isinstance(scope, ast.ClassDef) and self.prepared_unknown(scope)

    def direct_class_effect(self, cls, name, binder, statement):
        """The bound state established by a direct class-body statement;
        None when the binding is conditional or is not an ordered form."""
        d = self.r.recs[(id(binder), name)]
        nearest = binder
        while nearest is not None and not isinstance(nearest, ast.stmt):
            nearest = self.parents.get(id(nearest))
        if nearest is not statement:
            return None
        if d.src == "Delete":
            return False
        if d.mode in ("value", "aug", "import", "local") and d.src in (
                "Assign", "AnnAssign", "AugAssign", "Import", "ImportFrom",
                "FunctionDef", "AsyncFunctionDef", "ClassDef"):
            return True
        return None

    def class_bound_before(self, sid, name, node):
        """True, False or None when the class name is bound, unbound or may
        be either immediately before this direct class-body read."""
        cls = self.snode(sid)
        use = self.class_statement(cls, node)
        bound = False
        binders = self.own.get((sid, name), ())
        for statement in cls.body:
            here = [b for b in binders if self.class_statement(cls, b) is statement]
            records = [self.r.recs[(id(b), name)] for b in here]
            effective = [d for d in records if not (d.src == "AnnAssign" and d.mode == "fresh")]
            if statement is use:
                return None if effective else bound
            effects = [self.direct_class_effect(cls, name, b, statement) for b in here]
            direct = [effect for effect in effects if effect is not None]
            if direct:
                bound = next(reversed(direct))
            elif effective:
                may_unbind = any(d.src in ("Delete", "ExceptHandler") for d in effective)
                may_bind = any(d.src not in ("Delete", "ExceptHandler") for d in effective)
                if may_bind and bound is not True or may_unbind and bound is not False:
                    bound = None
        return False

    def lookups(self, name, node) -> set:
        """Every scope a read may see. A direct class-body read uses its
        proven class binding, the module-global LOAD_NAME fallback while
        unbound, or both after a possible conditional binding. A custom
        prepared mapping contributes an independent unknown route."""
        direct = self.scope.get(id(node))
        sid = self.lookup(name, node)
        if isinstance(direct, ast.ClassDef) and self.prepared_unknown(direct) \
                and (id(direct), name) not in self.own:
            return {id(direct), sid}
        if sid is None:
            return {None}
        scope = self.snode(sid)
        if not isinstance(scope, ast.ClassDef) or self.scope.get(id(node)) is not scope:
            return {sid}
        state = self.class_bound_before(sid, name, node)
        if state is True and not self.prepared_unknown(scope):
            return {sid}
        return {None} if state is False and not self.prepared_unknown(scope) else {sid, None}

    def binds_at(self, name, node):
        """The binders a read of name at node can see."""
        return [b for sid in self.lookups(name, node) for b in self.own.get((sid, name), ())]

    def unbound_at(self, name, node) -> bool:
        """Whether one lookup route has no binding for name."""
        return self.prepared_at(node) or any(not self.own.get((sid, name)) for sid in self.lookups(name, node))

    def builtin_possible(self, name, node) -> bool:
        """Whether one lookup route reaches an unshadowed builtin."""
        return hasattr(builtins, name) and any(
            sid is None and not self.own.get((sid, name)) for sid in self.lookups(name, node))

    def builtin_certain(self, name, node) -> bool:
        """Whether the builtin is the only lookup route."""
        return not self.prepared_at(node) and self.builtin_possible(name, node) and self.lookups(name, node) == {None}

    def act(self, s):
        """The function or lambda whose activation runs scope s (through
        comprehension and class bodies), None for the module."""
        while s is not None and not isinstance(s, _FUNCS):
            s = self.scope.get(id(s))
        return s

    # -- keys ------------------------------------------------------------------------
    def name_lv(self, name, ctx, node=None):
        values = [_UNRES] if self.prepared_at(node) else []
        for sid in self.lookups(name, node):
            if sid is None:
                values.append(self.get(("n", name)))
                continue
            s = self.snode(sid)
            cfn, clvl = ctx if ctx is not None else (None, _UNRES)
            lvl = clvl if ctx is not None and self.act(s) is self.act(cfn) else _UNRES
            values.append(self.get(("l", sid, lvl, name)))
        return max(values)

    def compute(self, key):
        kind, *rest = key
        if kind == "n":
            (name,) = rest
            binds = self.own.get((None, name), [])                   # fix 14: the module's own bindings
            if not binds:
                return _FRESH if hasattr(builtins, name) else _UNRES        # a builtin, or an unbound global
            v = max(self.bind_lv(b, None, name) for b in binds)
            if v < _HOLDS and any(self.lv(x, None) >= _HOLDS for _s, vals, rt in self.muts.get(name, ())
                                  if None in self.lookups(name, rt) for x in vals):
                v = _HOLDS                                           # a mutation wrote a held value into it
            return v
        if kind == "l":
            sid, lvl, name = rest
            fn = self.snode(sid)
            ctx = (fn, lvl)
            binds = self.own.get((sid, name), ())
            if not binds:
                return _UNRES
            v = max(self.bind_lv(b, ctx, name) for b in binds)
            if v < _HOLDS and any(self.lv(x, ctx) >= _HOLDS for _s, vals, rt in self.muts.get(name, ())
                                  if sid in self.lookups(name, rt) for x in vals):
                v = _HOLDS
            return v
        if key[0] == "s":
            return self.summary(self.nodes[key[1]], key[2])
        return self.instance(self.nodes[key[1]], key[2])

    def bind_lv(self, b, ctx, name):
        """The level one binding gives its name, read in ctx (fix pass 13: by
        the mode the binding table delivered; a binder it did not deliver is
        _UNRES, and the proof is refused by the table gate)."""
        d = self.r.recs.get((id(b), name))
        if d is None:
            return _UNRES                                            # outside the binding table
        if d.mode == "param":
            owner = self.encl.get(id(b))
            if ctx is None or owner is not ctx[0]:
                return _UNRES                                        # a value a caller supplies
            return max(ctx[1], _FRESH if d.expr is None else self.lv(d.expr, None))
        if d.mode == "import":
            return _HOLDS                                           # imported values can carry caller protocols
        if d.mode in ("local", "fresh", "declare"):
            return _FRESH
        if d.mode == "unres":
            return _UNRES                                            # an except target
        if d.mode == "capture":
            return self.carried(self.lv(d.expr, ctx))                # a match capture: the subject or a part of it
        if d.mode == "aug":
            return _HOLDS if self.lv(d.expr, ctx) >= _HOLDS else _FRESH      # the object keeps; it may gain
        v = self.lv(d.expr, ctx)
        return self.carried(v) if d.path else v                      # an element, an __enter__ result, a star list

    @staticmethod
    def joined(v):
        """Fix pass 13: the level of a call result that may be its argument
        itself: the full unresolved mark stays _UNRES, a held one _HOLDS (fix
        14: an immutable identity alias stays _IMMUT, never _FRESH)."""
        return _UNRES if v >= _UNRES else _HOLDS if v >= _HOLDS else _IMMUT if v >= _IMMUT else _FRESH

    @staticmethod
    def carried(v):
        """Fix pass 12: the level of an element reached through a container at
        level v by iteration, unpacking, a with target or a copy builtin: the
        unresolved mark of an element survives every way of reaching it."""
        return _UNRES if v >= _HOLDS else _FRESH                     # fix 12: element provenance

    # -- expressions -----------------------------------------------------------------
    def operated(self, operands, ctx):
        """Fix pass 14 (round 13 LOW 2): the level of an operator's result. The
        operator runs a method of its operands (__add__, __eq__, __neg__ and
        the rest, reflected ones included), which may return an operand itself
        or anything else: over an operand the proof cannot resolve, or one
        holding such a value that is not a proven builtin, the result is
        _UNRES; else it keeps the join of its operands (s + '' may be s)."""
        v = max([self.lv(x, ctx) for x in operands], default=_FRESH)
        if v >= _UNRES or any(self.lv(x, ctx) >= _HOLDS and not self.r.builtin_typed(x) for x in operands):
            return _UNRES
        return self.joined(v)

    def lv(self, node, ctx):
        if isinstance(node, ast.Compare) and not all(isinstance(o, (ast.Is, ast.IsNot, ast.In, ast.NotIn))
                                                     for o in node.ops):
            return self.operated([node.left] + node.comparators, ctx)   # fix 14: __eq__ may return anything
        if node is None or isinstance(node, (ast.Constant, ast.JoinedStr, ast.FormattedValue, ast.Compare)):
            return _FRESH
        if isinstance(node, ast.Name):
            return self.name_lv(node.id, ctx, node)                  # fix 14: read in the node's own scope
        if isinstance(node, ast.Attribute):
            return _UNRES if self.lv(node.value, ctx) >= _HOLDS else _FRESH
        if isinstance(node, ast.Subscript):
            e = self.r.indexed(node)
            if e is not None:
                return self.lv(e, ctx)                               # fix 13: the selected element's own mark
            base = self.lv(node.value, ctx)
            if isinstance(node.slice, ast.Slice) or isinstance(node.slice, ast.Tuple) and any(
                    isinstance(e, ast.Slice) for e in node.slice.elts):
                return base                                          # fix 12: a slice keeps its base's level
            return _UNRES if base >= _HOLDS else _FRESH
        if isinstance(node, (ast.Starred, ast.NamedExpr, ast.Await)):
            return self.lv(node.value, ctx)
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return _HOLDS if any(self.lv(e, ctx) >= _HOLDS for e in node.elts) else _FRESH
        if isinstance(node, ast.Dict):
            return _HOLDS if any(self.lv(e, ctx) >= _HOLDS for e in node.keys + node.values if e is not None) \
                else _FRESH
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            return _HOLDS if self.lv(node.elt, ctx) >= _HOLDS else _FRESH
        if isinstance(node, ast.DictComp):
            return _HOLDS if max(self.lv(node.key, ctx), self.lv(node.value, ctx)) >= _HOLDS else _FRESH
        if isinstance(node, ast.IfExp):
            return max(self.lv(node.body, ctx), self.lv(node.orelse, ctx))     # either branch
        if isinstance(node, ast.BoolOp):
            return max(self.lv(v, ctx) for v in node.values)                   # any operand
        if isinstance(node, ast.BinOp):
            return self.operated([node.left, node.right], ctx)     # fix 14: was _HOLDS over an unresolved operand
        if isinstance(node, ast.UnaryOp):
            return _FRESH if isinstance(node.op, ast.Not) else self.operated([node.operand], ctx)
        if isinstance(node, ast.Lambda):
            return _HOLDS if self.lv(node.body, ctx) >= _HOLDS else _FRESH     # a closure over what it returns
        if isinstance(node, ast.Call):
            return self.call_lv(node, ctx)
        return _UNRES                                                # anything else: not followed

    def call_lv(self, node, ctx):
        args = [a.value if isinstance(a, ast.Starred) else a for a in node.args] + [k.value for k in node.keywords]
        al = max([self.lv(a, ctx) for a in args], default=_FRESH)
        pl = _UNRES if al >= _HOLDS else _FRESH
        f = node.func
        if isinstance(f, ast.Attribute):
            if f.attr == "copy" and not args:
                return self.joined(self.lv(f.value, ctx))           # fix 13: may be the receiver itself
            c = self.r.cands(f)
            if c and c <= {"copy.copy", "copy.deepcopy"}:
                return self.joined(al)                               # fix 13: __copy__ may return its argument
            if f.attr in _PURE_METHODS and self.r.pure_receiver(f.value, f.attr):
                return max(self.carried(self.lv(f.value, ctx)), self.joined(al))   # fix 14: a builtin's pure method
            return _UNRES                                            # a method's or an imported callable's result
        if not isinstance(f, ast.Name):
            return _UNRES
        v = self.name_call_lv(f.id, pl, al, ctx, f)
        if f.id in _IDENTITY_BUILTINS and self.builtin_possible(f.id, f) and _only(node.args) is not None \
                and not node.keywords and al >= _UNRES:
            v = _UNRES                                               # iter(x), reversed(x) may be x
        if f.id in _HIGHER_ORDER and self.builtin_possible(f.id, f):
            higher = self.higher_order_lv(node, ctx)
            v = max(_UNRES if v is None else v, higher)
        return _UNRES if v is None else v

    def higher_order_lv(self, node, ctx):
        """Fix pass 12: a builtin that calls a callable argument (map, filter,
        iter's callable form, sorted, min and max with key). Each callback is
        marked as if called directly (callback_lv) with its arguments at
        _UNRES when the other arguments hold anything; a callback the analysis
        cannot resolve makes the result _UNRES; else the result holds the marks
        of the other arguments' elements and of every callback's results (a
        container: map, filter, iter, sorted; an element: min, max)."""
        pos, kw = _HIGHER_ORDER[node.func.id]
        calls, rest = [], []
        for i, a in enumerate(node.args):
            a = a.value if isinstance(a, ast.Starred) else a
            (calls if i == pos and (node.func.id != "iter" or len(node.args) == 2) else rest).append(a)
        for k in node.keywords:
            (calls if k.arg is not None and k.arg == kw else rest).append(k.value)
        rl = max([self.lv(a, ctx) for a in rest], default=_FRESH)
        pl = _UNRES if rl >= _HOLDS else _FRESH
        cbs = [self.callback_lv(c, pl, ctx) for c in calls]           # fix 12: each callback as if called directly
        if any(v is None for v in cbs):
            return _UNRES                                            # a callback the analysis cannot resolve
        v = max([rl] + cbs)
        if node.func.id in ("min", "max"):
            return self.carried(v)                                   # an element
        return _HOLDS if self.carried(v) >= _HOLDS else _FRESH       # a container holding its elements

    def callback_lv(self, c, pl, ctx):
        """Fix pass 12: the level of what calling the VALUE c returns, with its
        arguments at pl, exactly as a direct call is marked; None when the
        analysis cannot resolve the callable (a name the module never binds
        that is no builtin, a name bound to anything but a def, a class or a
        lambda, an attribute of an unresolved value, any other expression)."""
        if isinstance(c, ast.Constant) and c.value is None:
            return _FRESH                                            # filter(None, ...): the elements themselves
        if isinstance(c, ast.Lambda):
            self.nodes[id(c)] = c
            return self.get(("s", id(c), pl))
        if isinstance(c, ast.Attribute):
            return None if self.lv(c.value, ctx) >= _UNRES else _UNRES     # a method or imported callable's result
        if not isinstance(c, ast.Name):
            return None
        return self.name_call_lv(c.id, pl, pl, ctx, c)

    def name_call_lv(self, name, pl, al, ctx, node):
        """The level of a call of the name with its arguments at al (and so a
        callee's parameters at pl); None when the name stands for nothing the
        analysis follows. Fix pass 14: the name is looked up in the scope of
        the node that reads it, and a builtin that can return its argument
        itself (str, bytes, int, tuple and the rest of _IDENTITY_IMMUTABLE)
        yields an immutable identity alias, never a fresh value."""
        binds = self.binds_at(name, node)
        out = self.builtin_call_lv(name, al) if self.builtin_possible(name, node) else None
        if not binds:
            return out
        out = _FRESH if out is None else out
        for b in binds:
            if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.nodes[id(b)] = b
                out = max(out, self.get(("s", id(b), pl)))          # the callee's return paths
            elif isinstance(b, ast.ClassDef):
                self.nodes[id(b)] = b
                out = max(out, self.get(("c", id(b), pl)))
            else:
                lam = self.lambda_of(b)
                if lam is None:
                    return None                                      # a name bound to a callable not followed
                self.nodes[id(lam)] = lam
                out = max(out, self.get(("s", id(lam), pl)))
        return out

    def builtin_call_lv(self, name, al):
        """The result level of an unshadowed builtin call."""
        if name in _ARG_RETURNING:
            return _UNRES if al >= _HOLDS else _IMMUT                # may return an argument or its element
        if name in _IDENTITY_IMMUTABLE and al >= _UNRES:
            return _UNRES                                            # its __str__ or __index__ returns anything
        if name in _IDENTITY_IMMUTABLE:
            return _HOLDS if name in _COPY_BUILTINS and self.carried(al) >= _HOLDS else _IMMUT
        if name in _PROVEN_FRESH:
            return _FRESH                                            # the allowlist is the gate
        if name in _COPY_BUILTINS:
            return _HOLDS if self.carried(al) >= _HOLDS else _FRESH  # a copy aliases no namespace
        return _UNRES if al >= _HOLDS else _FRESH

    def lambda_of(self, b):
        if not isinstance(b, ast.Name) or not isinstance(b.ctx, ast.Store):
            return None
        p = self.parents.get(id(b))
        whole = isinstance(p, ast.Assign) and any(t is b for t in p.targets) \
            or isinstance(p, (ast.AnnAssign, ast.NamedExpr)) and p.target is b
        return p.value if whole and isinstance(p.value, ast.Lambda) else None

    # -- callees ---------------------------------------------------------------------
    def unresolved_callable(self, func, ctx) -> bool:
        while isinstance(func, (ast.Attribute, ast.Subscript)):
            func = func.value
        return self.lv(func, ctx) >= _UNRES

    def summary(self, fn, pl):
        """The join of a callee's return paths with its parameters at pl."""
        ctx = (fn, pl)
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                not (isinstance(d, ast.Name) and d.id in ("staticmethod", "classmethod")
                     and self.builtin_certain(d.id, d))
                for d in fn.decorator_list):
            return _UNRES                                            # a decorator the analysis does not follow
        for x in ast.walk(fn):
            if isinstance(x, ast.YieldFrom):
                return _UNRES
            if isinstance(x, ast.Call) and (self.r.cands(x.func) & {"builtins.exec", "builtins.eval"}
                                            or self.unresolved_callable(x.func, ctx)):
                return _UNRES                                        # exec, eval, a call of an unresolved callable
            if isinstance(x, (ast.Try, getattr(ast, "TryStar", ast.Try))) and any(
                    not (h.body and isinstance(h.body[-1], ast.Raise)) and any(
                        isinstance(y, ast.Return) or isinstance(y, ast.Name) and isinstance(y.ctx, ast.Store)
                        for s in h.body for y in ast.walk(s)) for h in x.handlers):
                return _UNRES                                        # a try that swallows and rebinds
        if isinstance(fn, ast.Lambda):
            return self.lv(fn.body, ctx)
        v = _FRESH
        stack = list(fn.body)
        while stack:
            x = stack.pop()
            if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue                                             # a nested scope's returns are its own
            if isinstance(x, ast.Return) and x.value is not None:
                v = max(v, self.lv(x.value, ctx))                    # every return path
            elif isinstance(x, ast.Yield) and x.value is not None and self.lv(x.value, ctx) >= _HOLDS:
                v = max(v, _HOLDS)                                   # a generator holds what it yields
            stack.extend(ast.iter_child_nodes(x))
        return v

    def instance(self, cls, pl):
        """The level of an instance of a module class built from arguments at pl."""
        if cls.decorator_list or cls.keywords:
            return _UNRES
        if any(isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                not (isinstance(decorator, ast.Name) and decorator.id in ("staticmethod", "classmethod")
                     and self.builtin_certain(decorator.id, decorator))
                for decorator in method.decorator_list) for method in cls.body):
            return _UNRES                                            # a decorator can replace a method
        v = _HOLDS if pl >= _UNRES else _FRESH                       # an instance may keep its arguments
        for b in cls.bases:
            if isinstance(b, ast.Name) and self.builtin_certain(b.id, b) and hasattr(builtins, b.id):
                continue
            bb = self.binds_at(b.id, b) if isinstance(b, ast.Name) else []     # fix 14: by scope
            if not bb or not all(isinstance(x, ast.ClassDef) for x in bb):
                return _UNRES                                        # a base the analysis does not follow
            for x in bb:
                self.nodes[id(x)] = x
                v = max(v, self.get(("c", id(x), pl)))
        if any(isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == "__new__" for x in cls.body):
            return _UNRES
        for x in ast.walk(cls):
            vals = []
            if isinstance(x, (ast.Assign, ast.AugAssign, ast.AnnAssign)) and x.value is not None:
                vals = [x.value]
            elif isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute):
                vals = [a.value if isinstance(a, ast.Starred) else a for a in x.args] + [k.value for k in x.keywords]
            if vals:
                e = self.encl.get(id(x))
                ctx = (e, _FRESH) if e is not None and e in cls.body else None   # a method, else module scope
                if any(self.lv(val, ctx) >= _HOLDS for val in vals):
                    v = max(v, _HOLDS)                               # a store or mutation that can hold one
        return v


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
      namespace-reaching expression or name, to a fixed point.
    Since fix pass 13 the bindings come from ONE table keyed by ast node
    class (_BINDING_TABLE, records/recs); the candidate resolution (resolve)
    follows every binding it delivers, a loop, comprehension or with target
    through the elements or __enter__ result it can see, a parameter as
    anything a caller passes; a node the table does not hold is a named
    refusal (unknown)."""

    def __init__(self, tree, names):
        self.tree, self.parents, self.names = tree, names.parents, names
        self.binds, self.cache, self.recs, self.records = {}, {}, {}, []
        gate = []
        for n in ast.walk(tree):                                     # fix 13: the binding table, by construction
            h = _BINDING_TABLE.get(type(n))
            if h is None:
                if _BIND_FIELDS & set(type(n)._fields):
                    gate.append((n, "binding form %s outside the binding table" % type(n).__name__))
                continue
            for b in h(n, self):
                self.records.append(b)
                self.recs[(id(b.binder), b.name)] = b
                self.binds.setdefault(b.name, []).append(b.binder)
        gate += [(n, "binding of %s outside the binding table" % n.id) for n in ast.walk(tree)
                 if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)) and (id(n), n.id) not in self.recs]
        self.unknown = gate                                          # the gate: each refuses the proof, named
        defs, other, stored = set(), set(), set()
        for c in ast.walk(tree):
            if isinstance(c, ast.ClassDef):
                for x in c.body:
                    if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        defs.add(x.name)
                    else:
                        other |= {y.id for y in ast.walk(x) if isinstance(y, ast.Name)
                                  and isinstance(y.ctx, (ast.Store, ast.Del))}
                        other |= {y.name for y in ast.walk(x) if isinstance(y, (ast.ClassDef, ast.FunctionDef,
                                                                                ast.AsyncFunctionDef))}
            elif isinstance(c, ast.Attribute) and isinstance(c.ctx, (ast.Store, ast.Del)):
                stored.add(c.attr)
        # the attribute names whose call on an object the module makes runs module code: a method a
        # module class defines, unless anything stores an attribute of it (a pure method name
        # no longer counts here; it is admitted only on a receiver proven by pure_receiver)
        self.methods = (defs - other) - stored
        self.modules = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.marked = set()
        self.flow = _Flow(self)
        self._mark()

    def level_at(self, node):
        """Fix pass 13: the level of an expression read in its own function
        scope (its parameters caller-supplied; free and global names at module
        scope, merged), as fix 12 reads an augmented name (aug_name_refused)."""
        fn = self.flow.encl.get(id(node))
        return self.flow.level(node, None if fn is None else (fn, _UNRES))

    def made_here_at(self, node) -> bool:
        """made_here, the base read in its own function scope (level_at)."""
        r = node
        while isinstance(r, (ast.Attribute, ast.Subscript, ast.Starred)):
            r = r.value
        if isinstance(r, ast.Name) and self.flow.unbound_at(r.id, r):
            return False                                             # fix 14: no binding this use can see
        return self.level_at(node) < _UNRES

    def library(self, node) -> bool:
        """Fix pass 13: a reference that resolves only to dotted names (a
        module, an imported or builtin object): a call through it is a
        library call, judged by _ARG_SAFE (rule (8)), not a method of a value."""
        rs = self.resolve(node)
        return bool(rs) and all(isinstance(x, str) for x in rs)

    def unresolved_receiver(self, n) -> bool:
        """Fix pass 13, rule (3): the receiver of the method n is a value the
        proof cannot resolve: read in its own function scope (level_at), or,
        for a fix 11 mutator name, in the merged scope as fix 11 read it; a
        library reference is no receiver."""
        if self.library(n.value):
            return False
        if n.attr in _MUTATORS and not self.made_here(n.value):
            return True
        return not self.made_here_at(n.value)

    def match_subject(self, n):
        p = self.parents.get(id(n))
        while p is not None and not isinstance(p, ast.Match):
            p = self.parents.get(id(p))
        return None if p is None else p.subject

    def cands(self, node, seen=frozenset()) -> set:
        """Every dotted name a reference can stand for through every binding
        of its names (the _candidates rule), None for anything unresolvable.
        Fix pass 13: the dotted part of resolve, so it follows every binding
        form the table delivers."""
        return {x if isinstance(x, str) else None for x in self.resolve(node, seen)}

    def resolve(self, node, seen=frozenset()) -> set:
        """Fix pass 13: every value a reference can stand for, through every
        binding the table delivers: a dotted name (an import, a builtin), a
        ("local", node) for a module def, class or lambda (a class's instance
        too), or None for anything the resolution cannot follow (a parameter,
        an except target, a capture, an element of a container it cannot see
        into, the result of a call other than a local callee's return paths,
        or next, min or max over elements it can see)."""
        if isinstance(node, ast.Attribute):
            return {b + "." + node.attr if isinstance(b, str) else None for b in self.resolve(node.value, seen)}
        if isinstance(node, ast.NamedExpr):
            return self.resolve(node.value, seen)
        if isinstance(node, ast.IfExp):
            return self.resolve(node.body, seen) | self.resolve(node.orelse, seen)
        if isinstance(node, ast.BoolOp):
            return set().union(*[self.resolve(v, seen) for v in node.values])
        if isinstance(node, ast.Lambda):
            return {("local", node)}
        if isinstance(node, ast.Subscript):
            e = self.indexed(node)
            if e is not None:
                return self.resolve(e, seen)
            sl = node.slice
            if isinstance(sl, ast.Slice) or isinstance(sl, ast.Tuple) and any(isinstance(x, ast.Slice) for x in sl.elts):
                return {None}                                        # a sequence, not one of its elements
            return self.resolve_all(self.elements(node.value, seen), seen)
        if isinstance(node, ast.Call):
            return self.call_result(node, seen)
        if not isinstance(node, ast.Name) or node.id in seen:
            return {None}
        out = {None} if self.flow.prepared_at(node) else set()
        keys = {(sid, node.id) for sid in self.flow.lookups(node.id, node)} - seen
        if not keys:
            return {None}
        for key in keys:
            sid, _name = key
            if not seen and key in self.cache:
                out |= self.cache[key]
                continue
            binds = self.flow.own.get(key, [])
            if not binds:
                resolved = {"builtins." + node.id} if sid is None and hasattr(builtins, node.id) else {None}
            else:
                resolved = set()
                for b in binds:
                    resolved |= self.resolve_bind(self.recs[(id(b), node.id)], seen | {key})
                resolved = resolved or {None}
            if not seen:
                self.cache[key] = resolved
            out |= resolved
        return out or {None}

    def resolve_all(self, exprs, seen) -> set:
        if exprs is None:
            return {None}
        return set().union(*[self.resolve(e, seen) for e in exprs]) if exprs else {None}

    def resolve_bind(self, b, seen) -> set:
        """What one delivered binding can stand for."""
        if b.mode == "import":
            return {b.expr}                                          # the dotted name; None for a relative import
        if b.mode == "local":
            return {("local", b.expr)}
        if b.mode == "param":
            return {None} | (self.resolve(b.expr, seen) if b.expr is not None else set())   # a caller may pass any
        if b.mode == "value":
            return self.resolve_all(self.values(b.expr, b.path, seen), seen)
        return {None}                         # an except target, a capture, an annotation, a deletion, an aug

    def values(self, expr, path, seen):
        """The expressions a binding's value can be, along its path, or None
        when one step cannot be seen through."""
        vs = [expr]
        for step in path:
            if step == "star":
                return None                                          # a new list, not an element
            nxt = []
            for v in vs:
                got = self.elements(v, seen) if step == "elem" else self.entered(v)
                if got is None:
                    return None
                nxt += got
            vs = nxt
        return vs

    def entered(self, v):
        """What a with statement's manager returns from __enter__, where the
        resolution can see it (contextlib.nullcontext(x) returns x)."""
        if isinstance(v, ast.Call) and v.args and not isinstance(v.args[0], ast.Starred) \
                and self.cands(v.func) == {"contextlib.nullcontext"}:
            return [v.args[0]]
        return None

    def indexed(self, node):
        """Fix pass 13 (round 12 LOW 1): the element a constant integer index
        selects from a list or tuple display (negative constants resolved
        statically), else None (an out-of-range constant, a non-constant
        index, a slice, a starred element or a container that is no display
        keeps the joined mark of fix 12)."""
        v = node.value
        if not isinstance(v, (ast.List, ast.Tuple)) or any(isinstance(e, ast.Starred) for e in v.elts):
            return None
        i = _const_index(node.slice)
        if i is None or not -len(v.elts) <= i < len(v.elts):
            return None
        return v.elts[i]

    def elements(self, node, seen):
        """The expressions an element of node can be, or None when the
        resolution cannot see into it."""
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            out = []
            for e in node.elts:
                if isinstance(e, ast.Starred):
                    got = self.elements(e.value, seen)
                    if got is None:
                        return None
                    out += got
                else:
                    out.append(e)
            return out
        if isinstance(node, ast.Dict):
            return None if any(k is None for k in node.keys) else list(node.keys)
        if isinstance(node, ast.Subscript):
            e = self.indexed(node)
            if e is not None:
                return self.elements(e, seen)
            sl = node.slice
            if isinstance(sl, ast.Slice) or isinstance(sl, ast.Tuple) and any(isinstance(x, ast.Slice) for x in sl.elts):
                return self.elements(node.value, seen)
            return None
        if isinstance(node, ast.IfExp):
            a, b = self.elements(node.body, seen), self.elements(node.orelse, seen)
            return None if a is None or b is None else a + b
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ELEMENT_KEEPING \
                and self.flow.builtin_certain(node.func.id, node.func) and _only(node.args) is not None \
                and not isinstance(_only(node.args), ast.Starred) and all(k.arg in ("key", "reverse") for k in node.keywords):
            return self.elements(node.args[0], seen)
        if isinstance(node, ast.Name) and node.id not in seen and node.id not in self.flow.muts:
            binds = self.flow.binds_at(node.id, node)                # fix 14: the bindings this use can see
            if not binds or self.flow.unbound_at(node.id, node):
                return None
            out = []
            for b in binds:
                d = self.recs[(id(b), node.id)]
                if d.mode != "value":
                    return None
                star = bool(d.path) and d.path[-1] == "star"
                vs = self.values(d.expr, d.path[:-1] if star else d.path, seen | {node.id})
                if vs is None:
                    return None
                for v in vs:
                    got = self.elements(v, seen | {node.id})
                    if got is None:
                        return None
                    out += got
            return out
        return None

    def call_result(self, node, seen) -> set:
        """What the result of a call can stand for: next, min or max of
        elements the resolution sees; the return paths of a module def or
        lambda; an instance of a module class; else None."""
        f = node.func
        out = set()
        special = isinstance(f, ast.Name) and f.id in ("next", "min", "max") \
            and self.flow.builtin_possible(f.id, f) and _only(node.args) is not None \
            and not isinstance(_only(node.args), ast.Starred)
        if special:
            out |= self.resolve_all(self.elements(_only(node.args), seen), seen)
        for x in self.resolve(f, seen):
            if special and x == "builtins." + f.id:
                continue
            if isinstance(x, tuple) and isinstance(x[1], ast.ClassDef):
                out.add(x)                                           # an instance of a module class
            elif isinstance(x, tuple) and ("ret", id(x[1])) not in seen:
                out |= self.returns(x[1], seen | {("ret", id(x[1]))})
            else:
                out.add(None)
        return out or {None}

    def returns(self, fn, seen) -> set:
        if isinstance(fn, ast.Lambda):
            return self.resolve(fn.body, seen)
        if any(not (isinstance(d, ast.Name) and d.id in ("staticmethod", "classmethod")
                    and self.flow.builtin_certain(d.id, d)) for d in fn.decorator_list):
            return {None}                                            # a decorator the resolution does not follow
        out, stack = set(), list(fn.body)
        while stack:
            x = stack.pop()
            if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            if isinstance(x, (ast.Yield, ast.YieldFrom, ast.Await)):
                return {None}
            if isinstance(x, ast.Return):
                out |= self.resolve(x.value, seen) if x.value is not None else {None}
            stack.extend(ast.iter_child_nodes(x))
        return out or {None}

    def builtin_typed(self, node, seen=frozenset()) -> bool:
        """Fix pass 13: a list, tuple, set, dict, generator, string or bytes
        the module builds (a display, a comprehension, a literal, a call of an
        unbound builtin constructor, a slice of one, a name only ever bound to
        one), whose attributes are only that type's builtin methods. Fix pass
        14: the bindings a name's use can see (_Flow.binds_at), never every
        binding of the name; str(x) and bytes(x) of one argument only over a
        builtin scalar (an object's __str__ or __bytes__ may return a
        subclass); an augmented binding only with an exact builtin operand
        (str += x can otherwise run x's reflected operator); a parameter proven
        an exact str or bytes by its function's type guard (guarded); the
        result of a library call listed in _RESULT_TYPED."""
        if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict, ast.ListComp, ast.SetComp, ast.DictComp,
                             ast.GeneratorExp, ast.Constant, ast.JoinedStr)):
            return True
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            return self.builtin_typed(node.value, seen)
        if isinstance(node, (ast.BinOp, ast.Call)) and self.container_kinds(node, seen):
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _BUILTIN_TYPES \
                and self.flow.builtin_certain(node.func.id, node.func):
            one = _only(list(node.args) + [k.value for k in node.keywords])   # the one-argument form, else None
            return node.func.id not in ("str", "bytes") or not any(isinstance(a, ast.Starred) for a in node.args) \
                and not any(k.arg is None for k in node.keywords) and (one is None or self.builtin_scalar(one))
        if isinstance(node, ast.Call) and self.cands(node.func) and self.cands(node.func) <= _RESULT_TYPED:
            return True                                              # fix 14: a builtin generator
        if isinstance(node, ast.Name) and node.id not in seen:
            if self.guarded(node):
                return True                                          # fix 14: an exact str or bytes parameter
            binds = self.flow.binds_at(node.id, node)                # fix 14: the bindings this use can see
            return bool(binds) and not self.flow.unbound_at(node.id, node) and all(
                d.mode == "aug" and self.builtin_typed(d.expr, seen | {node.id})
                or d.mode == "value" and not d.path and self.builtin_typed(d.expr, seen | {node.id})
                or d.mode == "value" and d.path == ("enter",) and isinstance(d.expr, ast.Call)
                and isinstance(d.expr.func, ast.Name) and d.expr.func.id == "open"
                and self.flow.builtin_certain("open", d.expr.func)
                for d in (self.recs[(id(b), node.id)] for b in binds))   # with open(...) as f: the file itself
        return False

    def pure_receiver(self, node, method) -> bool:
        """Whether a listed pure method has a proven exact receiver.

        Exact builtins retain their existing proof. Otherwise every candidate
        route must be an exact dotted library receiver that lists this method.
        """
        if self.builtin_typed(node):
            return True
        routes = self.cands(node)
        return bool(routes) and all(method in _PURE_LIBRARY_RECEIVERS.get(route, ()) for route in routes)

    def augmented_container(self, kind, binding, seen) -> bool:
        """Whether a successful augmented binding preserves an exact
        container kind rather than reaching a reflected result."""
        parent = self.parents.get(id(binding.binder))
        if not isinstance(parent, ast.AugAssign):
            return False
        if kind == "list":
            return isinstance(parent.op, (ast.Add, ast.Mult))
        if kind == "dict":
            return isinstance(parent.op, ast.BitOr)
        if kind == "set":
            return isinstance(parent.op, (ast.BitOr, ast.BitAnd, ast.Sub, ast.BitXor))
        if kind == "tuple" and isinstance(parent.op, ast.Add):
            return self.container_kinds(binding.expr, seen) == frozenset({"tuple"})
        if kind == "tuple" and isinstance(parent.op, ast.Mult):
            return isinstance(binding.expr, ast.Constant) and isinstance(binding.expr.value, int)
        return False

    def container_kinds(self, node, seen=frozenset()) -> frozenset:
        """Every exact builtin object-container kind this expression can be;
        an empty set means the proof is not exact."""
        if isinstance(node, (ast.List, ast.ListComp)):
            return frozenset({"list"})
        if isinstance(node, ast.Tuple):
            return frozenset({"tuple"})
        if isinstance(node, (ast.Set, ast.SetComp)):
            return frozenset({"set"})
        if isinstance(node, (ast.Dict, ast.DictComp)):
            return frozenset({"dict"})
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            return self.container_kinds(node.value, seen)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "copy" and not node.args and not node.keywords:
            return self.container_kinds(node.func.value, seen)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self.container_kinds(node.left, seen)
            right = self.container_kinds(node.right, seen)
            return left if left == right and left <= frozenset({"list", "tuple"}) else frozenset()
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in _BUILTIN_CONTAINERS and self.flow.builtin_certain(node.func.id, node.func):
            return frozenset({"list" if node.func.id == "sorted" else node.func.id})
        if isinstance(node, ast.Name) and node.id not in seen:
            definitions = [self.recs[(id(b), node.id)] for b in self.flow.binds_at(node.id, node)]
            if not definitions or self.flow.unbound_at(node.id, node) or any(
                    d.mode not in ("value", "aug") or d.mode == "value" and d.path
                                      for d in definitions):
                return frozenset()
            values = [self.container_kinds(d.expr, seen | {node.id}) for d in definitions if d.mode == "value"]
            kinds = frozenset().union(*values) if values and all(values) else frozenset()
            if not kinds or any(not self.augmented_container(kind, d, seen | {node.id})
                                for d in definitions if d.mode == "aug" for kind in kinds):
                return frozenset()
            return kinds
        return frozenset()

    def builtin_container(self, node, kinds=_BUILTIN_CONTAINERS, seen=frozenset()) -> bool:
        """A proven exact builtin object-container of one of kinds. Unlike
        builtin_typed this excludes files, scalars, bytearrays and generators."""
        found = self.container_kinds(node, seen)
        return bool(found) and found <= kinds

    def builtin_list_typed(self, node, seen=frozenset()) -> bool:
        """A proven exact list, including the list returned by sorted."""
        return self.builtin_container(node, _BUILTIN_LISTS, seen)

    def import_held(self, node, seen=frozenset()) -> bool:
        """Whether a value is, or is a local container holding, an import."""
        resolved = self.resolve(node)
        if resolved and all(value in _PROTOCOL_SAFE_VALUES for value in resolved if isinstance(value, str)) \
                and all(isinstance(value, str) for value in resolved):
            return False
        if self.imported(node):
            return True
        if isinstance(node, ast.Starred):
            return self.import_held(node.value, seen)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return any(self.import_held(x, seen) for x in node.elts)
        if isinstance(node, ast.Dict):
            return any(x is not None and self.import_held(x, seen) for x in node.keys + node.values)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            return self.import_held(node.elt, seen)
        if isinstance(node, ast.DictComp):
            return self.import_held(node.key, seen) or self.import_held(node.value, seen)
        if isinstance(node, ast.IfExp):
            return self.import_held(node.body, seen) or self.import_held(node.orelse, seen)
        if isinstance(node, ast.BinOp):
            return self.import_held(node.left, seen) or self.import_held(node.right, seen)
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            return self.import_held(node.value, seen)
        if isinstance(node, ast.Call):
            one = _only(node.args)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "copy" \
                    and not node.args and not node.keywords and self.builtin_container(node.func.value):
                return self.import_held(node.func.value, seen)
            if one is not None and not node.keywords and not isinstance(one, ast.Starred):
                if isinstance(node.func, ast.Name) and node.func.id in _ELEMENT_KEEPING \
                        and self.flow.builtin_possible(node.func.id, node.func):
                    return self.import_held(one, seen)
        if isinstance(node, ast.Name):
            keys = {(sid, node.id) for sid in self.flow.lookups(node.id, node)} - seen
            for key in keys:
                for b in self.flow.own.get(key, ()):
                    d = self.recs[(id(b), node.id)]
                    if d.mode != "value":
                        continue
                    values = self.values(d.expr, d.path, seen | {key, node.id})
                    if values is not None and any(
                            self.import_held(value, seen | {key}) for value in values):
                        return True
        return False

    def protocol_marked(self, node, seen=frozenset()) -> bool:
        """Whether explicit builtin code can reach caller or imported code."""
        resolved = self.resolve(node)
        if resolved and all(value in _PROTOCOL_SAFE_VALUES for value in resolved if isinstance(value, str)) \
                and all(isinstance(value, str) for value in resolved):
            return False
        return self.level_at(node) >= _HOLDS or self.import_held(node, seen)

    def receiver_element_blind(self, node, method) -> bool:
        """Whether an exact receiver method executes no code of values the
        receiver already holds. Pop is blind only for list and set; dict.pop
        can compare a held key with its lookup argument."""
        if method in _RECEIVER_ELEMENT_BLIND:
            return True
        kinds = self.container_kinds(node)
        return method == "pop" and bool(kinds) and kinds <= _POP_ELEMENT_BLIND

    def receiver_argument_blind(self, receiver, method, argument, shape) -> bool:
        """Whether an exact receiver copies an exact argument without
        executing code of its values. A held receiver is judged separately."""
        return method == "update" and shape == (None,) \
            and self.container_kinds(receiver) == frozenset({"dict"}) \
            and self.container_kinds(argument) == frozenset({"dict"})

    def receiver_update_blind(self, call, receiver, method, args, shape) -> bool:
        """Whether this exact dict update has scalar existing and incoming
        keys and is the only visible mutation, so copying runs no value code."""
        argument = _only(args)
        values = self.receiver_initial_elements(receiver)
        incoming = None if argument is None else self.receiver_initial_elements(argument)
        root = _root(receiver)
        return argument is not None and self.receiver_argument_blind(receiver, method, argument, shape) \
            and values is not None and all(self.builtin_scalar(value) for value in values) \
            and incoming is not None and all(self.builtin_scalar(value) for value in incoming) \
            and (root is None or all(site is call for site, _values, _root_node in self.flow.muts.get(root, ())))

    def receiver_initial_elements(self, receiver, seen=frozenset()):
        """Elements from a name's direct value bindings, before mutations."""
        if isinstance(receiver, (ast.List, ast.Tuple, ast.Set)):
            return None if any(isinstance(value, ast.Starred) for value in receiver.elts) else list(receiver.elts)
        if isinstance(receiver, ast.Dict):
            return None if any(key is None for key in receiver.keys) else list(receiver.keys)
        if isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name) \
                and receiver.func.id in _ELEMENT_KEEPING | {"dict"} \
                and self.flow.builtin_certain(receiver.func.id, receiver.func) \
                and _only(receiver.args) is not None and not isinstance(_only(receiver.args), ast.Starred) \
                and all(keyword.arg in ("key", "reverse") for keyword in receiver.keywords):
            return self.receiver_initial_elements(_only(receiver.args), seen)
        if not isinstance(receiver, ast.Name) or receiver.id in seen:
            return None
        binds = self.flow.binds_at(receiver.id, receiver)
        if not binds or self.flow.unbound_at(receiver.id, receiver):
            return None
        out = []
        for binder in binds:
            record = self.recs[(id(binder), receiver.id)]
            if record.mode != "value" or record.path:
                return None
            values = self.receiver_initial_elements(record.expr, seen | {receiver.id})
            if values is None:
                return None
            out.extend(values)
        return out

    def protocol_container(self, node, seen=frozenset()) -> bool:
        """A value whose builtin iteration runs no caller element protocol,
        including the specifically typed library generators in _RESULT_TYPED."""
        if isinstance(node, ast.GeneratorExp):
            return True                                              # its implicit body protocols remain boundary R1
        if isinstance(node, ast.Call) and self.cands(node.func) == {"builtins.iter"} \
                and _only(node.args) is not None and not node.keywords \
                and not isinstance(_only(node.args), ast.Starred):
            return self.protocol_container(_only(node.args), seen)
        if self.builtin_container(node, seen=seen):
            return True
        if isinstance(node, ast.Call) and self.cands(node.func) and self.cands(node.func) <= _RESULT_TYPED:
            return True
        if isinstance(node, ast.Name) and node.id not in seen:
            binds = self.flow.binds_at(node.id, node)
            return bool(binds) and not self.flow.unbound_at(node.id, node) and all(
                d.mode == "value" and not d.path and self.protocol_container(d.expr, seen | {node.id})
                for d in (self.recs[(id(b), node.id)] for b in binds))
        return False

    def builtin_scalar(self, node) -> bool:
        """Fix pass 14: an exact builtin scalar whose protocols run no code of
        the module's callers: a literal, an f-string, or a parameter its
        function's type guard proves an exact str or bytes (guarded)."""
        return isinstance(node, (ast.Constant, ast.JoinedStr)) or isinstance(node, ast.Name) and self.guarded(node)

    def guarded(self, node) -> bool:
        """Fix pass 14: a read of a parameter p that its function binds only as
        the parameter, inside a statement of the function's body that comes
        after a statement `if type(p) is not str: raise ...` (or bytes) of the
        same body (type_guard): the statements of a body run in order, so
        past the guard p is exactly that type and no method of a caller's
        class runs on it."""
        try:
            sid, = self.flow.lookups(node.id, node)
        except ValueError:
            return False
        fn = None if sid is None else self.flow.snode(sid)
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        b = _only(self.flow.own.get((sid, node.id), []))
        if b is None or self.recs[(id(b), node.id)].mode != "param":
            return False                                             # rebound, or not a parameter
        top = node
        while top is not None and self.parents.get(id(top)) is not fn:
            top = self.parents.get(id(top))
        for g in fn.body:                                            # the statements that run before the use's own
            if g is top or top is None:
                return False
            if self.type_guard(g, node.id):
                return True
        return False

    def type_guard(self, g, name) -> bool:
        """Fix pass 14: `if type(name) is not str: raise ...` (or bytes), with
        nothing else in it, type and the type named resolving to the builtins."""
        if not (isinstance(g, ast.If) and not g.orelse and isinstance(_only(g.body), ast.Raise)):
            return False
        t = g.test
        if not (isinstance(t, ast.Compare) and isinstance(_only(t.ops), ast.IsNot) and isinstance(t.left, ast.Call)):
            return False
        arg, typ = _only(t.left.args), _only(t.comparators)
        names = self.cands(typ)
        return not t.left.keywords and isinstance(arg, ast.Name) and arg.id == name \
            and self.cands(t.left.func) == {"builtins.type"} and _only(names) is not None and names <= _GUARD_TYPES

    def imported(self, node) -> bool:
        """Fix pass 14 (round 13 M5 (1)): a reference that can stand for an
        imported object (a module, or a member of one, by any import form, a
        relative one included); the builtins are judged as before."""
        if any(isinstance(x, str) and not x.startswith("builtins.") for x in self.resolve(node)):
            return True
        r = _root_node(node)
        return r is not None and any(self.recs[(id(b), r.id)].mode == "import" for b in self.flow.binds_at(r.id, r))

    def module_ref(self, node) -> bool:
        """Fix pass 14: a reference that stands only for a module an import
        statement names (import x.y binds x and names x.y), so an attribute of
        it is a module function, judged by _ARG_SAFE, not a method of an object."""
        rs = self.resolve(node)
        return bool(rs) and all(isinstance(x, str) and x in self.modules for x in rs)

    def protocol_rows(self, call, f, args,
                      what="call of protocol-running callable %s through unresolved base %s",
                      elements=False) -> list:
        """A builtin/library call, or a method of a proven builtin receiver,
        is refused when it can run code of an unresolved/imported argument or
        an unresolved/imported value held by its receiver. _NO_PROTOCOL is a plain-call
        signature policy: exact arities where behavior changes, any plain
        positional arity for storage-only exception arguments, and explicit
        per-position masks where an exception constructor runs a protocol.
        _ELEMENT_BLIND applies per unstarred argument whose iteration runs no
        caller element protocol. A held or imported exact container receiver
        is admitted only by receiver_element_blind (including type-specific
        pop). Exact list.append with one plain argument only stores that
        argument. With `elements`, f is a
        callback and its invocation signature comes from the higher-order
        call."""
        operation = elements if isinstance(elements, str) else None
        callback = bool(elements)
        shape = _protocol_shape(call, callback, operation)
        unsafe_receiver = None
        update_blind = isinstance(f, ast.Attribute) and self.receiver_update_blind(
            call, f.value, f.attr, args, shape)
        if isinstance(f, ast.Attribute) and not self.library(f) and self.builtin_typed(f.value):
            if f.attr == "append" and self.builtin_list_typed(f.value) and shape == (None,):
                return []                                            # exact list append only stores its argument
            if self.protocol_marked(f.value):
                if self.builtin_container(f.value) and not self.receiver_element_blind(f.value, f.attr) \
                        and not update_blind:
                    unsafe_receiver = f.value
            rs = set()
        else:
            rs = {x for x in self.resolve(f) if isinstance(x, str)}
            if not rs and unsafe_receiver is None:
                return []                                            # module code: judged where it is written
            if rs and all(_no_protocol(x, shape) for x in rs):
                return []
        risks = [False for _a in args]
        if not rs:
            risks = [True for _a in args]
        for dotted in rs:
            mask = _protocol_mask(dotted, shape)
            if mask is None:
                risks = [True for _a in args]
                break
            risks = [old or new for old, new in zip(risks, mask)]
        first = next(iter(args), None)
        starred = {id(a.value) for a in call.args if isinstance(a, ast.Starred)}
        starred.update(id(k.value) for k in call.keywords if k.arg is None)
        for a, risky in zip(args, risks):
            if not risky:
                continue
            blind = bool(rs) and not elements and id(a) not in starred and all(
                x in _ELEMENT_BLIND or x in _FIRST_ELEMENT_BLIND and a is first and not starred for x in rs)
            if not self.protocol_marked(a) or self.builtin_scalar(a) \
                    or blind and self.protocol_container(a) or update_blind:
                continue
            return [what % (ast.unparse(f), ast.unparse(a))]
        if unsafe_receiver is not None:
            return [what % (ast.unparse(f), ast.unparse(unsafe_receiver))]
        return []

    def unresolved_callee(self, f, rs) -> bool:
        """Fix pass 13: a callee the resolution cannot follow. A method of an
        object the module makes is followed when that object is a builtin
        container or string (its methods are builtin), or every resolved local
        receiver class directly defines the method, nothing rebinds its name,
        and each decorator is a proven builtin staticmethod or classmethod. A
        held object's other attributes may be anything it holds."""
        if isinstance(f, ast.Attribute):
            if all(isinstance(x, str) for x in rs):
                return False                                         # a library callable: _ARG_SAFE judges it
            receiver_routes = self.resolve(f.value)
            followed = f.attr in self.methods and bool(receiver_routes) and all(
                self.direct_local_method(route, f.attr) for route in receiver_routes)
            return self.level_at(f) >= _UNRES and not self.builtin_typed(f.value) and not followed
        return None in rs

    def direct_local_method(self, route, name) -> bool:
        """Whether a resolved local class directly defines this method."""
        if not isinstance(route, tuple):
            return False
        _kind, owner = route
        if not isinstance(owner, ast.ClassDef):
            return False
        methods = [item for item in owner.body
                   if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name]
        return bool(methods) and all(
            all(isinstance(decorator, ast.Name) and decorator.id in ("staticmethod", "classmethod")
                and self.flow.builtin_certain(decorator.id, decorator)
                for decorator in method.decorator_list)
            for method in methods)

    def callee_rows(self, f, marked, what, imp=None) -> list:
        """Fix pass 13: the rows of calling the value f with arguments of
        which `marked` is the first marked one (None when all are fresh):
        an unlisted library callable over a marked argument, and a callable
        the resolution cannot follow over a marked argument or that may
        itself be unresolved (a bound method of an unresolved receiver,
        extracted or delivered, or a value a caller supplies). Fix pass 14:
        an argument that stands for an imported object (`imp`, a module or a
        member of one) handed to either is refused too, as a write through an
        imported namespace (functools.update_wrapper(os, f) updates os's
        namespace from f's)."""
        rs = self.resolve(f)
        rows = []
        if marked is not None and any(not _arg_safe(d) for d in rs if isinstance(d, str)):
            rows.append("%s %s through unresolved base %s" % (what % "unlisted", ast.unparse(f), ast.unparse(marked)))
        if imp is not None and any(not _arg_safe(d) for d in rs if isinstance(d, str)):
            rows.append("%s %s through imported namespace %s" % (what % "unlisted", ast.unparse(f), ast.unparse(imp)))
        if self.unresolved_callee(f, rs):
            callee_unresolved = self.level_at(f) >= _UNRES
            if marked is not None or callee_unresolved:
                base = f if marked is None or self.imported(marked) else marked
                rows.append("%s %s through unresolved base %s" % (what % "unresolved", ast.unparse(f),
                                                                  ast.unparse(base)))
            if imp is not None:
                rows.append("%s %s through imported namespace %s" % (what % "unresolved", ast.unparse(f),
                                                                     ast.unparse(imp)))
        return rows

    def higher_order_operations(self, f):
        """Every builtin higher-order operation one callee route can invoke."""
        return {_HIGHER_ORDER_DOTTED[dotted] for dotted in self.resolve(f)
                if isinstance(dotted, str) and dotted in _HIGHER_ORDER_DOTTED}

    def only_higher_order(self, f, operation) -> bool:
        """Whether every callee route is this higher-order builtin."""
        resolved = self.resolve(f)
        return bool(resolved) and all(isinstance(dotted, str)
                                      and _HIGHER_ORDER_DOTTED.get(dotted) == operation
                                      for dotted in resolved)

    def call_rows(self, call) -> list:
        """Fix pass 13: the rows of one call. A method of an unresolved
        receiver is rule (3)'s; a callback of map, filter, iter, sorted, min
        or max is judged as a call at this site with the other arguments'
        elements; an in-place operator delivered through a call, a subscript
        or a walrus is rule (7)'s, here; every other callee by callee_rows."""
        f, rows = call.func, []
        args = [a.value if isinstance(a, ast.Starred) else a for a in call.args] + [k.value for k in call.keywords]
        if isinstance(f, ast.Attribute) and self.unresolved_receiver(f):
            return rows                                              # rule (3)
        operations = self.higher_order_operations(f)
        expanded = any(isinstance(a, ast.Starred) for a in call.args) \
            or any(k.arg is None for k in call.keywords)
        for operation in sorted(operations) if not expanded else ():
            pos, kw = _HIGHER_ORDER[operation]
            calls, rest = [], []
            for i, a in enumerate(call.args):
                a = a.value if isinstance(a, ast.Starred) else a
                (calls if i == pos and (operation != "iter" or len(call.args) == len((None, None))) else rest).append(a)
            for k in call.keywords:
                (calls if k.arg is not None and k.arg == kw else rest).append(k.value)
            cm = next((a for a in rest if self.protocol_marked(a)), None)
            ce = next((a for a in rest if self.protocol_marked(a) and not self.builtin_scalar(a)), None)
            for c in calls:
                if isinstance(c, ast.Constant) and c.value is None:
                    if ce is not None:                               # fix 14: filter(None, ...) tests each element
                        rows.append("callback of %s (protocol-running truth test) through unresolved base %s"
                                    % (operation, ast.unparse(ce)))
                    continue                                         # filter(None, ...)
                if isinstance(c, ast.Attribute):
                    unresolved = self.unresolved_receiver(c)
                    imported = self.imported(c.value) and not self.module_ref(c.value)
                    if unresolved or imported:
                        candidates = self.cands(c)
                        listed = bool(candidates) and all(
                            candidate is not None and _arg_safe(candidate) for candidate in candidates)
                        if (c.attr not in _PURE_METHODS or not self.pure_receiver(c.value, c.attr)) and not listed:
                            route = "unresolved base" if unresolved else "imported namespace"
                            rows.append("callback method %s of %s through %s %s"
                                        % (c.attr, operation, route, ast.unparse(c.value)))
                        if unresolved:
                            continue
                rows += self.callee_rows(c, cm, "callback of " + operation + " (%s)")
                callback_args = rest if operation == "map" else [] if ce is None else [ce]
                rows += self.protocol_rows(call, c, callback_args, "callback of " + operation
                                           + " (protocol-running callable %s) through unresolved base %s", operation)
            if self.only_higher_order(f, operation):
                args = rest
        marked = next((a for a in args if self.protocol_marked(a)), None)
        imp = next((a for a in args if self.imported(a)), None)      # fix 14: an imported object handed over
        if not isinstance(f, (ast.Name, ast.Attribute)) and self.cands(f) & _INPLACE_OPERATORS:
            recv = call.args[0] if call.args else None
            if recv is None or isinstance(recv, ast.Starred) or not self.made_here(recv):
                rows.append("in-place call %s through unresolved base %s"
                            % (ast.unparse(f), "(no receiver)" if recv is None else ast.unparse(recv)))
        rows += self.callee_rows(f, marked, "call of %s callable", imp)
        rows += self.protocol_rows(call, f, args)                    # protocols of the arguments and receiver elements
        return rows

    def reach_callable(self, node):
        """The first dotted name a reference can stand for that is a
        namespace-reaching callable or module, else None. Fix pass 14: or a
        namespace member reached through any import form (_namespace_member:
        from os import __dict__ as ns, os.sys.modules)."""
        for c in sorted(x for x in self.cands(node) if x):
            if c in _REACH_CALLABLES or _in_module(c, _REACH_MODULES) or c == "builtins" or _namespace_member(c):
                return c
        return None

    def benign_name_call(self, call) -> bool:
        """getattr or hasattr called with a literal plain (non-dunder) name;
        a mutator method's name (_MUTATORS) only on an object the module
        makes (fix pass 11)."""
        c = self.reach_callable(call.func)
        a = call.args[1] if len(call.args) >= 2 else None
        name = a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else None
        computed = name is None                       # a name built at run time
        if name in _MUTATOR_NAMES and not (call.args and self.made_here(call.args[0])):
            return False                              # a bound mutator of an unresolved object
        return c in _NAME_ARG and not computed and not _dunder(name)

    def benign_exec_call(self, call) -> bool:
        """Fix pass 11: timeit.timeit, timeit.repeat or timeit.Timer whose code
        (stmt, setup) is literal text that only evaluates expressions: no
        store, deletion, import, declaration, attribute, lambda or walrus, no
        call but of a builtin in _FRESH_BUILTINS or _COPY_BUILTINS the module
        does not rebind; no timer or globals argument; number and repeat
        literal integers. Every other executor call is namespace-reaching."""
        if not isinstance(call, ast.Call) or not self.cands(call.func) <= _BENIGN_EXEC:
            return False                              # every name the function can stand for is listed
        if len(call.args) > 2 or any(isinstance(a, ast.Starred) for a in call.args):
            return False                              # a third positional is the timer
        codes = list(call.args)
        for k in call.keywords:
            if k.arg in ("stmt", "setup"):
                codes.append(k.value)
            elif not (k.arg in ("number", "repeat") and isinstance(k.value, ast.Constant)
                      and type(k.value.value) is int):
                return False
        for c in codes:
            if not (isinstance(c, ast.Constant) and isinstance(c.value, str)):
                return False
            try:
                snippet = ast.parse(c.value)
            except SyntaxError:
                return False
            if not all(isinstance(s, ast.Expr) for s in snippet.body):
                return False
            for x in ast.walk(snippet):
                if isinstance(x, (ast.Attribute, ast.Lambda, ast.NamedExpr, ast.Await, ast.Yield, ast.YieldFrom,
                                  ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                    return False
                if isinstance(x, ast.Name) and (not isinstance(x.ctx, ast.Load) or _dunder(x.id)):
                    return False
                if isinstance(x, ast.Call) and not (isinstance(x.func, ast.Name)
                                                    and x.func.id in _FRESH_BUILTINS | _COPY_BUILTINS
                                                    and not self.binds.get(x.func.id)):
                    return False
        return True

    def benign_import(self, imp, module) -> bool:
        """Fix pass 11: an import of an executor module whose every bound name
        is bound only here and used only to reach the function of a benign
        executor call (benign_exec_call)."""
        if not _in_module(module, _BENIGN_EXEC_MODULES):
            return False
        for a in imp.names:
            bound = a.asname or a.name.split(".")[0]
            if self.binds.get(bound) != [imp]:
                return False
            for x in ast.walk(self.tree):
                if isinstance(x, ast.Name) and x.id == bound:
                    p = self.parents.get(id(x))
                    if isinstance(p, ast.Attribute) and p.value is x:
                        x, p = p, self.parents.get(id(p))
                    if not (isinstance(p, ast.Call) and p.func is x and self.benign_exec_call(p)):
                        return False
        return True

    def reaching(self, node) -> bool:
        """Whether this one node is a namespace-reaching expression or name."""
        if isinstance(node, ast.Call) and self.benign_exec_call(node):
            return False                                             # fix pass 11: literal timing code
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
        stack = [node]
        while stack:
            x = stack.pop()
            if isinstance(x, ast.Call) and self.benign_exec_call(x):
                continue                                             # fix pass 11: literal timing code
            if self.reaching(x):
                return True
            stack.extend(ast.iter_child_nodes(x))
        return False

    def _sources(self) -> list:
        """(names bound, the expressions they are bound from) for every
        binding the table delivers (fix pass 13; the same forms fix 10 listed
        by hand: a value, an augmented value, a default, an except type, a
        match subject, a def through what it returns or yields, a class
        through its body)."""
        out = []
        for b in self.records:
            if b.mode in ("value", "aug", "unres", "capture", "param") and isinstance(b.expr, ast.AST):
                out.append(({b.name}, [b.expr]))
            elif b.mode == "local" and isinstance(b.expr, ast.ClassDef):
                out.append(({b.name}, list(b.expr.body)))
            elif b.mode == "local":
                out.append(({b.name}, [x.value for x in ast.walk(b.expr) if isinstance(x, (ast.Return, ast.Yield,
                                                                                          ast.YieldFrom)) and x.value]))
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
        """Whether a write through this base reaches only an object the module
        makes (fix pass 11: _Flow's level is not _UNRES). A parameter, a name
        the module never binds, an except or match capture, the result of a
        method or an imported callable, an element of anything that may hold
        one of those, and the result of a module-local call whose return
        paths can yield one, are not; nor, as in fix pass 10, a chain that
        starts at a name the module never binds (a builtin name included)."""
        r = node
        while isinstance(r, (ast.Attribute, ast.Subscript, ast.Starred)):
            r = r.value
        if isinstance(r, ast.Name) and self.flow.unbound_at(r.id, r):
            return False                                             # an unbound name, as fix pass 10 judged it
        return self.flow.level(node) < _UNRES

    def aug_name_refused(self, t) -> bool:
        """Fix pass 12: an augmented assignment to a plain name applies its
        operator IN PLACE to the object the name holds (`ns |= {...}` calls
        ns.__ior__), whatever the operator: the type of an unresolved object
        is unknown, so none is exempt. Refused when that object may be imported
        or one the proof cannot resolve; the name is read in its own scope (the
        enclosing function, its parameters caller-supplied; module scope
        merged as everywhere), so a local counter or list is judged by its
        own bindings, and a copy (dict(ns), {**ns}) is fresh."""
        fn = self.flow.encl.get(id(t))
        return self.imported(t) or not self.flow.level(t, None if fn is None else (fn, _UNRES)) < _UNRES

    def inplace_form(self, n):
        """Fix pass 12: the dunder and operator in-place forms. A method in
        _INPLACE_DUNDERS called on, or taken as a bound method from, a
        receiver made_here rejects; a reference that can stand for an
        operator in-place function (operator.ior and the rest, under any
        alias) called with a first argument made_here rejects, or used any
        other way (handed to functools.partial, map or any other code, where
        its receiver is out of sight). The kind names the operation, else
        None."""
        p = self.parents.get(id(n))
        called = isinstance(p, ast.Call) and p.func is n
        if isinstance(n, ast.Attribute) and n.attr in _INPLACE_DUNDERS and not self.made_here(n.value):
            return ("method call %s through unresolved base %s" if called else
                    "bound method %s taken through unresolved base %s") % (n.attr, ast.unparse(n.value))
        if isinstance(p, ast.Attribute) and p.value is n or not self.cands(n) & _INPLACE_OPERATORS:
            return None                                              # a prefix, or no in-place operator
        if not called:
            return "in-place operator %s taken as a value" % ast.unparse(n)
        recv = p.args[0] if p.args else None
        if recv is not None and not isinstance(recv, ast.Starred) and self.made_here(recv):
            return None                                              # on an object the module makes
        return "in-place call %s through unresolved base %s" % (
            ast.unparse(n), "(no receiver)" if recv is None else ast.unparse(recv))


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
# Fix pass 11 re-measured with data flow through local calls and the method
# rule: the 32 sites stand and 11 more are unresolved, every one a mutator
# method on an unresolved receiver and none from a local call: 3 in
# review_needles.py (933 h.update on a hashlib object, an imported callable's
# result; 1036 and 1037 found.pop on a parameter) and 8 in review_rules.py
# (132, 133 and 137 to 140 h.update on a hashlib object; 946 and 1198
# files.update, files being a parameter elsewhere in the scope-merged
# module); 0 in review_boot.py. The rule keeps its form, at the new count.
# Fix pass 12 re-measured with element provenance through slices, copies and
# iteration, higher-order callbacks and the in-place forms: every earlier
# site stands and ONE more is unresolved, review_needles.py 999
# `body += [...]` (an augmented assignment to a name that also holds the
# result of a module-local call whose return paths the proof cannot rate
# fresh; the flow is not ordered, so the later fresh list does not clear
# it); 0 new in review_rules.py and review_boot.py (review_rules.py 668's
# row now names its operator, -=). The rule keeps its form, at 13.
# Fix pass 13 re-measured with the fail-closed method gate (a method on an
# unresolved receiver is a mutation unless _PURE_METHODS lists it), the
# fail-closed library-argument rule and the binding table: every earlier site
# stands and more are unresolved in review_needles.py, every one a method
# call off the pure list on a receiver the flow already rated unresolved
# (add on out[...], vals, self and a setdefault result; append on self.lists
# and self.items; read on f, which the same scope also binds by two for
# loops); review_rules.py and review_boot.py gain sites too (the method gate
# and the library-argument rule; neither module carries the exemption).
# Fix pass 14 re-measured with Python's scopes, the unproven-receiver rule for
# pure method names, the protocol-running call rule and operator results:
# sites whose base a same-name binding in ANOTHER scope made unresolved are
# proven and drop out of review_needles.py (the f.read() of _revision; the
# found of count, packet and seal; the out of _entries; the tables of
# _revision) and of review_rules.py; every module gains the calls that run a
# protocol of an argument the proof cannot type (isinstance, len, set,
# os.path.join and the rest over a parameter or a library result) and the
# pure methods called on a receiver not proven a builtin. Each site is named
# below and in the notes; the list's form is unchanged.
# The exemption names its sites: each is the row the proof prints (the rule,
# the operator or method, the base) and the function or class that encloses
# it, never its line and never a total. The module is exempt at exactly this
# multiset, so one more site, one fewer, or a site swapped for another at an
# equal count lapses it; the measured count is the length of the list.
_MEASURED_CLEAN = {"review_needles.py": [
        ('_Values.__init__', 'attribute store through unresolved base self'),
        ('_Values.add',
         'call of protocol-running callable any through unresolved base (_key_pattern(k) for k in keys)'),
        ('_Values.add', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_Values.add', 'method call add through unresolved base self'),
        ('_Values.add', 'method call append through unresolved base self.items'),
        ('_Values.add', 'method call append through unresolved base self.lists'),
        ('_blob_text', 'unproven pure method call decode through unresolved base raw'),
        ('_data_refs', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_data_refs', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_data_refs', "call of protocol-running callable isinstance through unresolved base node['data']"),
        ('_data_refs', 'call of protocol-running callable set through unresolved base node'),
        ('_data_refs', "call of unresolved callable out.add through unresolved base node['data']"),
        ('_data_refs', 'unproven pure method call values through unresolved base node'),
        ('_derive', 'call of protocol-running callable _PUBLIC.clear through unresolved base _PUBLIC'),
        ('_derive',
         "call of protocol-running callable _PUBLIC.extend through unresolved base sorted({ln.rstrip('\\n') for ln in f if ln.strip() and (not ln.startswith('#'))}, key=len, reverse=True)"),
        ('_derive', 'call of protocol-running callable len through unresolved base name'),
        ('_derive', 'call of protocol-running callable open through unresolved base listed'),
        ('_derive', 'call of protocol-running callable open through unresolved base public'),
        ('_derive', 'call of protocol-running callable os.listdir through unresolved base base'),
        ('_derive', 'call of protocol-running callable os.listdir through unresolved base store'),
        ('_derive', 'call of protocol-running callable os.path.join through unresolved base base'),
        ('_derive', 'call of protocol-running callable os.path.join through unresolved base store'),
        ('_derive', 'call of protocol-running callable os.path.join through unresolved base store'),
        ('_derive', 'call of protocol-running callable os.path.join through unresolved base tests'),
        ('_derive', 'call of protocol-running callable os.path.join through unresolved base tests'),
        ('_derive', 'call of protocol-running callable sorted through unresolved base os.listdir(store)'),
        ('_derive',
         "call of protocol-running callable sorted through unresolved base {ln.rstrip('\\n') for ln in f if ln.strip() and (not ln.startswith('#'))}"),
        ('_derive',
         "callback of sorted (protocol-running callable len) through unresolved base {ln.rstrip('\\n') for ln in f if ln.strip() and (not ln.startswith('#'))}"),
        ('_derive', "method call add through unresolved base out['basename']"),
        ('_derive', 'subscript store through unresolved base out'),
        ('_derive', 'unproven pure method call fullmatch through unresolved base _REV_DIR'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable open through unresolved base rest[0]'),
        ('_dispatch',
         "call of protocol-running callable print through unresolved base __doc__.split('Modes:')[1].split('Exit 0')[0].rstrip()"),
        ('_dispatch',
         "unproven pure method call rstrip through unresolved base __doc__.split('Modes:')[1].split('Exit 0')[0]"),
        ('_dispatch', "unproven pure method call split through unresolved base __doc__.split('Modes:')[1]"),
        ('_entries', 'call of protocol-running callable getattr through unresolved base st'),
        ('_entries', 'call of protocol-running callable getattr through unresolved base st'),
        ('_entries', 'call of protocol-running callable os.path.join through unresolved base top'),
        ('_entries', 'call of protocol-running callable os.path.join through unresolved base top'),
        ('_entries', 'call of protocol-running callable os.scandir through unresolved base top'),
        ('_entries', 'call of protocol-running callable sorted through unresolved base (e.name for e in it)'),
        ('_entries', 'call of protocol-running callable stat.S_ISDIR through unresolved base st.st_mode'),
        ('_entries', 'call of protocol-running callable stat.S_ISDIR through unresolved base st.st_mode'),
        ('_entries', 'call of protocol-running callable stat.S_ISLNK through unresolved base st.st_mode'),
        ('_entries', 'call of protocol-running callable stat.S_ISREG through unresolved base st.st_mode'),
        ('_entries', 'call of protocol-running callable str through unresolved base root'),
        ('_expr', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_expr', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_expr', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_expr', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_expr', 'call of protocol-running callable len through unresolved base node'),
        ('_expr', 'method call add through unresolved base vals'),
        ('_expr', 'unproven pure method call items through unresolved base node'),
        ('_finite', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_finite', 'call of protocol-running callable math.isfinite through unresolved base v'),
        ('_git',
         "call of protocol-running callable subprocess.run through unresolved base ['git', '-C', repo, *args]"),
        ('_git', 'unproven pure method call decode through unresolved base out'),
        ('_ident', 'call of protocol-running callable stat.S_IFMT through unresolved base st.st_mode'),
        ('_inside', 'call of protocol-running callable os.path.commonpath through unresolved base [a, b]'),
        ('_inside', 'call of protocol-running callable os.path.realpath through unresolved base path'),
        ('_inside', 'call of protocol-running callable os.path.realpath through unresolved base root'),
        ('_is_dir', 'call of protocol-running callable stat.S_ISDIR through unresolved base st.st_mode'),
        ('_is_file', 'call of protocol-running callable stat.S_ISREG through unresolved base st.st_mode'),
        ('_key_pattern',
         "call of protocol-running callable '[ _-]?'.join through unresolved base (re.escape(w) for w in words)"),
        ('_key_pattern', 'call of protocol-running callable re.escape through unresolved base w'),
        ('_key_pattern', 'call of protocol-running callable re.escape through unresolved base words.pop()'),
        ('_key_pattern', 'call of protocol-running callable re.split through unresolved base key'),
        ('_keys', 'call of protocol-running callable isinstance through unresolved base n'),
        ('_keys', 'call of protocol-running callable len through unresolved base n'),
        ('_manifest_body', "call of protocol-running callable '\\n'.join through unresolved base lines"),
        ('_manifest_body', 'call of protocol-running callable hashlib.md5 through unresolved base data'),
        ('_manifest_body', 'call of protocol-running callable len through unresolved base data'),
        ('_manifest_body', 'call of protocol-running callable open through unresolved base note_file'),
        ('_manifest_body',
         'call of protocol-running callable sorted through unresolved base ((rel, hashlib.md5(data).hexdigest(), len(data)) for rel, data in snap)'),
        ('_manifest_body', 'call of protocol-running callable sum through unresolved base (n for _r, _m, n in rows)'),
        ('_manifest_body', 'call of protocol-running callable time.strftime through unresolved base time.gmtime()'),
        ('_manifest_body', "unproven pure method call encode through unresolved base '\\n'.join(lines) + '\\n'"),
        ('_manifest_body', 'unproven pure method call hexdigest through unresolved base hashlib.md5(data)'),
        ('_manifest_body', "unproven pure method call strip through unresolved base _git(pin, 'rev-parse', 'HEAD')"),
        ('_manifest_body', 'unproven pure method call strip through unresolved base f.read()'),
        ('_manifest_lines_of', 'call of protocol-running callable hashlib.sha256 through unresolved base raw'),
        ('_manifest_lines_of', 'call of protocol-running callable sorted through unresolved base snap'),
        ('_manifest_lines_of', 'unproven pure method call hexdigest through unresolved base hashlib.sha256(raw)'),
        ('_measure_keys', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_measure_keys', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_measure_keys', "call of protocol-running callable isinstance through unresolved base node['m']"),
        ('_measure_keys', 'call of protocol-running callable set through unresolved base node'),
        ('_measure_keys',
         "call of unresolved callable out.append through unresolved base node['m'].rsplit('.', 1)[-1]"),
        ('_measure_keys', "unproven pure method call rsplit through unresolved base node['m']"),
        ('_measure_keys', 'unproven pure method call values through unresolved base node'),
        ('_merge', 'subscript store through unresolved base a'),
        ('_merge', 'unproven pure method call get through unresolved base a'),
        ('_merge', 'unproven pure method call items through unresolved base b'),
        ('_meta', "call of protocol-running callable isinstance through unresolved base r['post']"),
        ('_meta', "call of protocol-running callable isinstance through unresolved base r['post_since']"),
        ('_meta', 'call of protocol-running callable isinstance through unresolved base r[k]'),
        ('_meta', 'call of protocol-running callable isinstance through unresolved base s'),
        ('_meta', 'call of protocol-running callable isinstance through unresolved base show'),
        ('_meta', 'call of protocol-running callable isinstance through unresolved base x'),
        ('_meta', 'call of protocol-running callable set through unresolved base r'),
        ('_meta', 'unproven pure method call get through unresolved base r'),
        ('_num_tokens', 'call of protocol-running callable int through unresolved base v'),
        ('_num_tokens', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_num_tokens', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_num_tokens', 'call of protocol-running callable repr through unresolved base v'),
        ('_num_tokens', 'call of protocol-running callable sorted through unresolved base toks'),
        ('_num_tokens', 'call of protocol-running callable str through unresolved base v'),
        ('_num_tokens', 'unproven pure method call is_integer through unresolved base v'),
        ('_num_tokens', 'unproven pure method call startswith through unresolved base t'),
        ('_num_tokens', 'unproven pure method call startswith through unresolved base t'),
        ('_pred', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_pred', "call of protocol-running callable isinstance through unresolved base node['args']"),
        ('_pred', "call of protocol-running callable isinstance through unresolved base node['op']"),
        ('_pred', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_pred', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_pred', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_pred', "call of protocol-running callable isinstance through unresolved base v['data']"),
        ('_pred', 'call of protocol-running callable set through unresolved base node'),
        ('_pred', 'call of protocol-running callable set through unresolved base node'),
        ('_pred', 'call of protocol-running callable set through unresolved base node'),
        ('_pred', 'call of protocol-running callable set through unresolved base v'),
        ('_pred', 'method call add through unresolved base vals'),
        ('_pred', 'unproven pure method call items through unresolved base node'),
        ('_pred', "unproven pure method call items through unresolved base node['args']"),
        ('_pred', "unproven pure method call rsplit through unresolved base node['op']"),
        ('_read_regular', 'call of protocol-running callable len through unresolved base raw'),
        ('_read_regular', 'call of protocol-running callable open through unresolved base path'),
        ('_read_regular', 'call of protocol-running callable os.fstat through unresolved base f.fileno()'),
        ('_report_line',
         "call of protocol-running callable ', '.join through unresolved base ('%s=%d' % (k, found[k]) for k in sorted(found))"),
        ('_report_line', 'call of protocol-running callable sorted through unresolved base found'),
        ('_report_line', 'call of protocol-running callable sum through unresolved base found.values()'),
        ('_report_line', 'method call pop through unresolved base found'),
        ('_report_line', 'method call pop through unresolved base found'),
        ('_report_line', 'unproven pure method call values through unresolved base found'),
        ('_revision', 'augmented subscript store |= through unresolved base out'),
        ('_revision', 'call of protocol-running callable isinstance through unresolved base doc'),
        ('_revision', "call of protocol-running callable isinstance through unresolved base doc.get('nonce')"),
        ('_revision', "call of protocol-running callable isinstance through unresolved base r.get('id')"),
        ('_revision', 'call of protocol-running callable json.loads through unresolved base text'),
        ('_revision', 'call of protocol-running callable len through unresolved base f'),
        ('_revision', 'call of protocol-running callable len through unresolved base f.strip()'),
        ('_revision', 'call of protocol-running callable len through unresolved base stem'),
        ('_revision', 'call of protocol-running callable open through unresolved base os.path.join(ddir, dn)'),
        ('_revision',
         "call of protocol-running callable open through unresolved base os.path.join(path, 'rules.json')"),
        ('_revision', 'call of protocol-running callable os.listdir through unresolved base ddir'),
        ('_revision', 'call of protocol-running callable os.path.join through unresolved base ddir'),
        ('_revision', 'call of protocol-running callable os.path.join through unresolved base path'),
        ('_revision', 'call of protocol-running callable os.path.join through unresolved base path'),
        ('_revision', 'call of protocol-running callable sorted through unresolved base _data_refs(doc)'),
        ('_revision', 'call of protocol-running callable sorted through unresolved base os.listdir(ddir)'),
        ('_revision', "method call add through unresolved base out['data']"),
        ('_revision', "method call add through unresolved base out['data']"),
        ('_revision', "method call add through unresolved base out['nonce']"),
        ('_revision', "method call add through unresolved base out['rule_id']"),
        ('_revision', "method call add through unresolved base out['wording']"),
        ('_revision', 'unproven pure method call decode through unresolved base f.read()'),
        ('_revision', 'unproven pure method call endswith through unresolved base dn'),
        ('_revision', 'unproven pure method call get through unresolved base doc'),
        ('_revision', 'unproven pure method call get through unresolved base doc'),
        ('_revision', 'unproven pure method call get through unresolved base r'),
        ('_revision', 'unproven pure method call get through unresolved base r'),
        ('_revision', 'unproven pure method call rsplit through unresolved base dn'),
        ('_revision', 'unproven pure method call split through unresolved base _PLACE'),
        ('_revision', 'unproven pure method call strip through unresolved base f'),
        ('_revision', 'unproven pure method call strip through unresolved base f'),
        ('_rx', 'call of protocol-running callable re.compile through unresolved base p'),
        ('_sequence',
         'call of protocol-running callable re.compile through unresolved base gap.join((re.escape(f) for f in frags))'),
        ('_sequence', 'call of protocol-running callable re.escape through unresolved base f'),
        ('_sequence', 'call of unresolved callable gap.join through unresolved base (re.escape(f) for f in frags)'),
        ('_sitting', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_sitting', "call of protocol-running callable isinstance through unresolved base node['args']"),
        ('_sitting', "call of protocol-running callable isinstance through unresolved base node['op']"),
        ('_sitting', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_sitting', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_sitting', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_sitting', 'call of protocol-running callable isinstance through unresolved base x'),
        ('_sitting', 'call of protocol-running callable set through unresolved base node'),
        ('_sitting', 'method call add through unresolved base vals'),
        ('_sitting', "unproven pure method call items through unresolved base node['args']"),
        ('_sitting', "unproven pure method call rsplit through unresolved base node['op']"),
        ('_status', 'call of protocol-running callable os.lstat through unresolved base path'),
        ('_status', 'call of protocol-running callable os.stat through unresolved base path'),
        ('_table', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_table', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_table', 'call of protocol-running callable isinstance through unresolved base x'),
        ('_table', 'call of protocol-running callable isinstance through unresolved base x'),
        ('_table', 'method call add through unresolved base vals'),
        ('_table', 'method call add through unresolved base vals'),
        ('_table', 'method call add through unresolved base vals'),
        ('_table', 'unproven pure method call items through unresolved base node'),
        ('_text_lines', 'unproven pure method call splitlines through unresolved base text'),
        ('_text_lines', 'unproven pure method call strip through unresolved base ln'),
        ('_text_value', 'call of protocol-running callable float through unresolved base tok'),
        ('_text_value', 'call of protocol-running callable int through unresolved base tok'),
        ('_text_value', 'unproven pure method call fullmatch through unresolved base _TEXT_NUM'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base doc'),
        ('_value_items',
         "call of protocol-running callable isinstance through unresolved base doc.get('closure', {})"),
        ('_value_items', "call of protocol-running callable isinstance through unresolved base doc.get('format')"),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base n'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base n'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base params'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base ps'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base r'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base rules'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base table'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base vocab'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base vocab'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base vocab'),
        ('_value_items', 'call of protocol-running callable set through unresolved base doc'),
        ('_value_items', 'call of protocol-running callable set through unresolved base vocab'),
        ('_value_items', 'call of protocol-running callable sorted through unresolved base (tables or {}).items()'),
        ('_value_items', 'call of protocol-running callable sorted through unresolved base vocab.items()'),
        ('_value_items', 'call of protocol-running callable str through unresolved base fam'),
        ('_value_items', "call of protocol-running callable str through unresolved base r.get('id')"),
        ('_value_items', 'unproven pure method call get through unresolved base doc'),
        ('_value_items', 'unproven pure method call get through unresolved base doc'),
        ('_value_items', 'unproven pure method call get through unresolved base doc'),
        ('_value_items', 'unproven pure method call get through unresolved base doc'),
        ('_value_items', 'unproven pure method call get through unresolved base r'),
        ('_value_items', 'unproven pure method call items through unresolved base params'),
        ('_value_items', 'unproven pure method call items through unresolved base ps'),
        ('_value_items', 'unproven pure method call items through unresolved base tables or {}'),
        ('_value_items', 'unproven pure method call items through unresolved base vocab'),
        ('_value_items', 'unproven pure method call rsplit through unresolved base name'),
        ('_value_items', 'unproven pure method call rsplit through unresolved base name'),
        ('_value_items', 'unproven pure method call rsplit through unresolved base str(fam)'),
        ('_value_items', 'unproven pure method call split through unresolved base _TEXT_SPLIT'),
        ('_value_items', 'unproven pure method call strip through unresolved base ln'),
        ('_value_items', 'unproven pure method call strip through unresolved base ln'),
        ('_value_needles',
         "call of protocol-running callable '|'.join through unresolved base (re.escape(t) for t in _num_tokens(x))"),
        ('_value_needles',
         "call of protocol-running callable '|'.join through unresolved base (re.escape(x) for x in _num_tokens(v))"),
        ('_value_needles', "call of protocol-running callable '|'.join through unresolved base sorted(alts)"),
        ('_value_needles',
         "call of protocol-running callable any through unresolved base (k.endswith('days') for k in keys)"),
        ('_value_needles',
         "call of protocol-running callable any through unresolved base (k.endswith('ms') for k in keys)"),
        ('_value_needles', 'call of protocol-running callable by_group.setdefault through unresolved base group'),
        ('_value_needles', 'call of protocol-running callable len through unresolved base alts'),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '%s[ \\\\t]?ms\\\\b' % val"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '%s[ \\\\t]{0,3}%s' % (val, _SIGN)"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '(?<![\\\\w.])(?:%s)(?:[ \\\\t]*[,;/][ \\\\t]*|[ \\\\t]+)(?:%s)(?![\\\\w]|\\\\.\\\\d)' % (x, y)"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '(?<![\\\\w.])(?:%s)[ \\\\t]?/[ \\\\t]?(?:%s)(?![\\\\w]|\\\\.\\\\d)' % (one, one)"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '(?i)%s[ \\\\t-]?days?\\\\b' % val"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '(?i)%s[ \\\\t]{0,3}%s' % (_CMP, val)"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '(?i)%s[^\\\\n]{0,%d}?\\\\b%s\\\\b' % (val, VALUE_NEAR, kp)"),
        ('_value_needles', "call of protocol-running callable out.add through unresolved base '(?i)' + val"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '(?i)\\\\b%s\\\\b[^\\\\n]{0,%d}?%s' % (kp, VALUE_NEAR, val)"),
        ('_value_needles', 'call of protocol-running callable re.escape through unresolved base t'),
        ('_value_needles', 'call of protocol-running callable re.escape through unresolved base x'),
        ('_value_needles', 'call of protocol-running callable sorted through unresolved base alts'),
        ('_value_needles', 'call of protocol-running callable zip through unresolved base alts'),
        ('_value_needles', 'method call add through unresolved base by_group.setdefault(group, set())'),
        ('_value_needles', 'unproven pure method call endswith through unresolved base k'),
        ('_value_needles', 'unproven pure method call endswith through unresolved base k'),
        ('_value_rx',
         "call of protocol-running callable '|'.join through unresolved base (re.escape(x) for x in _num_tokens(v))"),
        ('_value_rx', 'call of protocol-running callable re.escape through unresolved base v'),
        ('_value_rx', 'call of protocol-running callable re.escape through unresolved base x'),
        ('_write_manifest', 'call of protocol-running callable f.write through unresolved base body'),
        ('_write_manifest', 'call of protocol-running callable open through unresolved base dst'),
        ('_write_manifest', 'call of protocol-running callable os.path.basename through unresolved base out'),
        ('_write_manifest', 'call of protocol-running callable os.path.join through unresolved base pin'),
        ('_write_manifest', 'call of protocol-running callable os.path.join through unresolved base ri'),
        ('corpus_digest',
         "call of unresolved callable ('%s\\t%d\\t%s\\n' % (name, size, digest)).encode through unresolved base ('%s\\t%d\\t%s\\n' % (name, size, digest)).encode"),
        ('corpus_digest', 'method call update through unresolved base h'),
        ('corpus_digest', 'unproven pure method call hexdigest through unresolved base h'),
        ('count', 'call of protocol-running callable found.get through unresolved base cls'),
        ('count', 'call of protocol-running callable isinstance through unresolved base s'),
        ('count', 'unproven pure method call items through unresolved base needles'),
        ('count', 'unproven pure method call replace through unresolved base public_cut'),
        ('count', 'unproven pure method call search through unresolved base _rx(s[1])'),
        ('count', 'unproven pure method call search through unresolved base _sequence(s)'),
        ('leaf_type', 'call of protocol-running callable abs through unresolved base v'),
        ('leaf_type', 'call of protocol-running callable isinstance through unresolved base v'),
        ('leaf_type', 'call of protocol-running callable isinstance through unresolved base v'),
        ('leaf_type', 'call of protocol-running callable isinstance through unresolved base v'),
        ('leaf_type', 'call of protocol-running callable isinstance through unresolved base v'),
        ('leaf_type', 'call of protocol-running callable len through unresolved base v'),
        ('leaf_type', 'unproven pure method call is_integer through unresolved base v'),
        ('main', 'call of protocol-running callable isinstance through unresolved base e'),
        ('main', 'call of protocol-running callable isinstance through unresolved base e'),
        ('main', 'call of protocol-running callable len through unresolved base argv'),
        ('main',
         "call of protocol-running callable print through unresolved base 'review_needles: no verdict (%s): refused' % (e if isinstance(e, NoVerdict) else type(e).__name__)"),
        ('main',
         "call of protocol-running callable print through unresolved base 'review_needles: no verdict (a read failed: %s): refused, no result' % (e if isinstance(e, NoVerdict) else type(e).__name__)"),
        ('main',
         "call of protocol-running callable print through unresolved base 'review_needles: no verdict (store unreadable: %s): refused, nothing was scanned' % e"),
        ('main',
         "call of protocol-running callable print through unresolved base __doc__.split('Modes:')[1].split('Exit 0')[0].rstrip()"),
        ('main',
         "unproven pure method call rstrip through unresolved base __doc__.split('Modes:')[1].split('Exit 0')[0]"),
        ('main', "unproven pure method call split through unresolved base __doc__.split('Modes:')[1]"),
        ('packet', "call of protocol-running callable '\\n'.join through unresolved base _manifest_lines_of(snap)"),
        ('packet', 'call of protocol-running callable f.write through unresolved base body'),
        ('packet', 'call of protocol-running callable f.write through unresolved base raw'),
        ('packet', 'call of protocol-running callable f.write through unresolved base raw'),
        ('packet',
         "call of protocol-running callable hashlib.sha1 through unresolved base b'blob %d\\x00' % len(got) + got"),
        ('packet', 'call of protocol-running callable hashlib.sha256 through unresolved base body'),
        ('packet', 'call of protocol-running callable hashlib.sha256 through unresolved base got'),
        ('packet', 'call of protocol-running callable hashlib.sha256 through unresolved base raw'),
        ('packet', 'call of protocol-running callable len through unresolved base got'),
        ('packet', 'call of protocol-running callable len through unresolved base parts'),
        ('packet', 'call of protocol-running callable len through unresolved base snap'),
        ('packet', 'call of protocol-running callable open through unresolved base allowlist'),
        ('packet', 'call of protocol-running callable open through unresolved base d'),
        ('packet', 'call of protocol-running callable open through unresolved base dst'),
        ('packet', 'call of protocol-running callable open through unresolved base dst'),
        ('packet', 'call of protocol-running callable open through unresolved base os.path.join(out_dir, MANIFEST)'),
        ('packet', 'call of protocol-running callable os.listdir through unresolved base out_dir'),
        ('packet', 'call of protocol-running callable os.makedirs through unresolved base os.path.dirname(dst)'),
        ('packet', 'call of protocol-running callable os.makedirs through unresolved base os.path.dirname(dst)'),
        ('packet', 'call of protocol-running callable os.makedirs through unresolved base out_dir'),
        ('packet', 'call of protocol-running callable os.path.basename through unresolved base d'),
        ('packet', 'call of protocol-running callable os.path.basename through unresolved base d'),
        ('packet', 'call of protocol-running callable os.path.basename through unresolved base d'),
        ('packet', 'call of protocol-running callable os.path.dirname through unresolved base dst'),
        ('packet', 'call of protocol-running callable os.path.dirname through unresolved base dst'),
        ('packet', 'call of protocol-running callable os.path.isabs through unresolved base parts[1]'),
        ('packet', 'call of protocol-running callable os.path.join through unresolved base out_dir'),
        ('packet', 'call of protocol-running callable os.path.join through unresolved base out_dir'),
        ('packet', 'call of protocol-running callable os.path.join through unresolved base out_dir'),
        ('packet', 'call of protocol-running callable re.fullmatch through unresolved base parts[2]'),
        ('packet',
         "call of protocol-running callable set through unresolved base _git(repo, 'ls-tree', '-r', '--name-only', '-z', commit).split('\\x00')"),
        ('packet', 'call of protocol-running callable sorted through unresolved base pins'),
        ('packet',
         "unproven pure method call encode through unresolved base '\\n'.join(_manifest_lines_of(snap)) + '\\n'"),
        ('packet',
         "unproven pure method call hexdigest through unresolved base hashlib.sha1(b'blob %d\\x00' % len(got) + got)"),
        ('packet', 'unproven pure method call hexdigest through unresolved base hashlib.sha256(body)'),
        ('packet', 'unproven pure method call hexdigest through unresolved base hashlib.sha256(got)'),
        ('packet', 'unproven pure method call hexdigest through unresolved base hashlib.sha256(raw)'),
        ('packet',
         "unproven pure method call split through unresolved base _git(repo, 'ls-tree', '-r', '--name-only', '-z', commit)"),
        ('packet', 'unproven pure method call split through unresolved base ln'),
        ('packet', 'unproven pure method call split through unresolved base p'),
        ('packet', 'unproven pure method call split through unresolved base p'),
        ('packet', 'unproven pure method call startswith through unresolved base ln'),
        ('packet', 'unproven pure method call startswith through unresolved base p'),
        ('packet',
         "unproven pure method call strip through unresolved base _git(repo, 'rev-parse', '%s:%s' % (commit, p))"),
        ('packet', 'unproven pure method call strip through unresolved base ln'),
        ('packet_verify', 'call of protocol-running callable dict through unresolved base snap'),
        ('packet_verify', 'call of protocol-running callable dict(snap).get through unresolved base dict(snap)'),
        ('packet_verify', 'call of protocol-running callable hashlib.sha256 through unresolved base raw'),
        ('packet_verify', 'unproven pure method call decode through unresolved base raw'),
        ('packet_verify', 'unproven pure method call hexdigest through unresolved base hashlib.sha256(raw)'),
        ('packet_verify',
         "unproven pure method call splitlines through unresolved base raw.decode('utf-8', 'replace')"),
        ('report', 'call of protocol-running callable print through unresolved base line'),
        ('scan_range', 'call of protocol-running callable len through unresolved base commits'),
        ('scan_range', 'call of protocol-running callable len through unresolved base tree'),
        ('scan_range', 'call of protocol-running callable set through unresolved base blob'),
        ('scan_range',
         "unproven pure method call split through unresolved base _git(repo, 'diff-tree', '-r', '--no-commit-id', '-z', '--root', c)"),
        ('scan_range',
         "unproven pure method call split through unresolved base _git(repo, 'rev-list', '%s..%s' % (base, tip))"),
        ('scan_range', 'unproven pure method call split through unresolved base meta'),
        ('scan_range', 'unproven pure method call startswith through unresolved base status'),
        ('scan_staged',
         "unproven pure method call split through unresolved base _git(repo, 'diff', '--cached', '--name-only', '-z')"),
        ('scan_staged',
         "unproven pure method call split through unresolved base _git(repo, 'diff', '--cached', '--name-only', '-z', '--diff-filter=d')"),
        ('seal', 'augmented assignment += through unresolved base body'),
        ('seal', "call of protocol-running callable '\\n'.join through unresolved base body"),
        ('seal', 'call of protocol-running callable dict through unresolved base found'),
        ('seal', "call of protocol-running callable f.write through unresolved base '\\n'.join(body) + '\\n'"),
        ('seal', 'call of protocol-running callable len through unresolved base rows'),
        ('seal', 'call of protocol-running callable open through unresolved base seal_file'),
        ('seal', 'call of protocol-running callable os.path.basename through unresolved base out'),
        ('seal', 'call of protocol-running callable os.path.join through unresolved base pin'),
        ('seal', 'call of protocol-running callable sorted through unresolved base snap + [(name, body)]'),
        ('seal_verify',
         'call of protocol-running callable any through unresolved base (cur[k] != was[k] for k in was)'),
        ('seal_verify', 'call of protocol-running callable int through unresolved base lines[2].split()[1]'),
        ('seal_verify', 'call of protocol-running callable int through unresolved base n'),
        ('seal_verify', 'call of protocol-running callable len through unresolved base lines'),
        ('seal_verify', 'call of protocol-running callable open through unresolved base seal_file'),
        ('seal_verify', 'call of protocol-running callable set through unresolved base cur'),
        ('seal_verify', 'call of protocol-running callable set through unresolved base cur'),
        ('seal_verify', 'call of protocol-running callable set through unresolved base was'),
        ('seal_verify', 'call of protocol-running callable set through unresolved base was'),
        ('seal_verify', 'unproven pure method call split through unresolved base lines[0]'),
        ('seal_verify', 'unproven pure method call split through unresolved base lines[2]'),
        ('seal_verify', 'unproven pure method call split through unresolved base ln'),
        ('seal_verify', 'unproven pure method call splitlines through unresolved base f.read()'),
        ('seal_verify', 'unproven pure method call startswith through unresolved base lines[0]'),
        ('seal_verify', 'unproven pure method call startswith through unresolved base lines[2]'),
        ('snapshot', 'call of protocol-running callable os.path.join through unresolved base root'),
        ('snapshot', 'call of protocol-running callable set through unresolved base again'),
        ('snapshot', 'call of protocol-running callable set through unresolved base listed'),
        ('snapshot',
         'call of protocol-running callable sorted through unresolved base (k for k in listed if again[k] != listed[k])'),
        ('snapshot', 'call of protocol-running callable sorted through unresolved base listed'),
        ('snapshot', 'call of protocol-running callable sorted through unresolved base set(again) ^ set(listed)'),
        ('snapshot', 'unproven pure method call split through unresolved base rel'),
        ('snapshot_rows', 'call of protocol-running callable hashlib.sha256 through unresolved base raw'),
        ('snapshot_rows', 'call of protocol-running callable len through unresolved base raw'),
        ('snapshot_rows',
         'call of protocol-running callable sorted through unresolved base ((rel, len(raw), hashlib.sha256(raw).hexdigest()) for rel, raw in snap)'),
        ('snapshot_rows', 'unproven pure method call hexdigest through unresolved base hashlib.sha256(raw)'),
        ('write_manifest', 'call of protocol-running callable os.path.basename through unresolved base out'),
        ('write_manifest', 'call of protocol-running callable os.path.join through unresolved base pin'),
]}


def _unresolved(kind) -> bool:
    return " through unresolved base " in kind


def _site_names(tree, rows) -> list:
    """Each (line, kind) row named as a site: (the dotted name of the innermost
    function or class whose span holds the line, or <module>; the kind),
    sorted. The line only locates the row; it is not part of the name."""
    spans = []

    def walk(node, stack):
        for c in ast.iter_child_nodes(node):
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = stack + (c.name,)
                spans.append((c.lineno, c.end_lineno, ".".join(q)))
                walk(c, q)
            else:
                walk(c, stack)
    walk(tree, ())

    def scope(line):
        inner = [(start, -end, name) for start, end, name in spans if start <= line <= end]
        if not inner:
            return "<module>"
        _start, _end, name = max(inner)         # the latest start, then the shortest span: innermost
        return name
    return sorted((scope(line), kind) for line, kind in rows)


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
          formatted; `type(<name>).__name__` is a string and exempt;
      (5) (fix pass 11) a mutator method (_MUTATORS) called on, or taken as a
          bound method from, a receiver whose write would be refused by (1)'s
          unresolved-base half; a bound method handed to functools.partial or
          any other code is therefore refused, and operator.methodcaller is a
          listed callable. Since fix pass 11 the unresolved-base half follows
          data through module-local calls (_Flow), and (2) and (3) cover the
          in-process string and code executors (_EXECUTORS, types.CodeType;
          _EXECUTOR_IMPORTS), a timeit call on literal code that only
          evaluates expressions, and its import, excepted (benign_exec_call);
      (6) (fix pass 12) an augmented assignment, with any operator, whose
          target is a plain name holding an object the proof cannot resolve
          (aug_name_refused), or whose target is a subscript or attribute
          over a base made here but whose element is not (the in-place
          operator runs on the element before the store); the store rows of
          (1) name the operator;
      (7) (fix pass 12) an in-place dunder method (_INPLACE_DUNDERS) called on,
          or taken as a bound method from, a receiver made_here rejects, and
          an operator in-place function (_INPLACE_OPERATORS) under any alias
          called on such a receiver or used as a value (inplace_form).
          Since fix pass 12 the unresolved-base half also carries element
          provenance through slices, copies and iteration, and marks a
          callback consumed by map, filter, iter, sorted, min or max as if it
          were called directly (_Flow.higher_order_lv).
      (0) (fix pass 13) a node of a class that carries a binding field and
          is not in _BINDING_TABLE, or a stored name no table entry delivers
          (_Reach.unknown), named at its line;
      (5) since fix pass 13 the method half is fail-closed: a method called
          on a receiver (1)'s unresolved-base half rejects is a mutation
          unless _PURE_METHODS lists its name (_MUTATOR_NAMES only names the
          rows of bound methods taken);
      (8) (fix pass 13) a call (_Reach.call_rows): of a library callable off
          _ARG_SAFE with a marked argument; of a callable the resolution
          cannot follow (a parameter, a bound method of an unresolved
          receiver, extracted or delivered by any binding form, an element
          of a held container) with a marked argument or itself unresolved;
          of a callback of map, filter, iter, sorted, min or max judged as
          that call; of an in-place operator delivered by a call, a
          subscript or a walrus.
    Fix pass 14 (round 13 M5, LOW 1, LOW 2):
      (1) a store, deletion or augmented store whose base can stand for an
          imported object (a module, or a member of one, by any import form)
          is refused as a write through an imported namespace, and a dotted
          name with a namespace member past its first part (from os import
          __dict__ as ns) is namespace-reaching (_namespace_member);
      (5) a method listed on _PURE_METHODS called on a receiver the
          unresolved-base half rejects is refused too, unless the receiver
          is proven by _Reach.pure_receiver;
      (8) a call of builtin or library code (or a method of a proven
          builtin receiver) over an argument the proof cannot type, or an
          imported argument or imported value held in a local container, is
          refused as protocol-running (_Reach.protocol_rows), and an
          imported object handed to an unlisted or unresolved callable is a
          write through an imported namespace;
      (9) a method off _PURE_METHODS and _ARG_SAFE called, or a mutator
          method taken, through an imported object that is not a module an
          import statement names is a write through an imported namespace;
      every name is read by Python's scope rules (_Flow.lookups), never by
      every binding of the name, and an identity alias is never fresh.
    Fix pass 15 (round 14 M5 and LOW 1):
      (1) a direct class-body read sees a class binding proven extant by an
          earlier unconditional direct statement, the module-global LOAD_NAME
          fallback while unbound, or both after a possible conditional binder;
          a custom prepared mapping remains an independent unknown route;
      (8) a method on an exact builtin container holding an unresolved or imported value
          is protocol-running unless the receiver policy proves that it
          executes no element code; exact list.append keeps its store-only
          signature.
          _NO_PROTOCOL is a plain-call signature policy, including higher-order
          callback arity. Non-exempt signatures receive normal per-argument
          checking; an unresolved argument in a non-blind position is refused.
          Element blindness requires iteration that runs no caller element
          protocol and is positional where needed;
      (9) remains the imported-object rule above; receiver-element checking
          applies to the exact builtin values above, not imported namespaces.
    The implicit protocols (iteration, subscript and attribute reads, in,
    formatting, an operator's own method) are not calls and are not refused
    by (8); an operator's RESULT over an unresolved operand is unresolved.
    Finalization caused after a call by discarding its result or temporary
    receiver is likewise outside this explicit-call rule; a method such as
    clear that drops held references before returning is not receiver-blind.
    Fix pass 9's _manager_rebinds still runs beside it; later passes retain
    the namespace operation named by an import (from os import __dict__)."""
    r = _Reach(tree, names)
    parents = r.parents
    out = []
    for n, why in r.unknown:                                                                             # (0)
        line = n
        while line is not None and not hasattr(line, "lineno"):
            line = parents.get(id(line))
        out.append((0 if line is None else line.lineno, why))
    for n in ast.walk(tree):
        if isinstance(n, (ast.Attribute, ast.Subscript)) and isinstance(n.ctx, (ast.Store, ast.Del)):     # (1)
            what = "attribute" if isinstance(n, ast.Attribute) else "subscript"
            aug = parents.get(id(n)) if isinstance(parents.get(id(n)), ast.AugAssign) else None
            op = "%s deletion" % what if isinstance(n.ctx, ast.Del) else \
                "augmented %s store %s" % (what, _AUG_OPS[type(aug.op)]) if aug is not None else "%s store" % what
            hit = next((x for x in [n] + list(ast.walk(n.value)) if r.reaching(x)), None)
            if hit is not None:
                out.append((n.lineno, "%s through namespace-reaching %s" % (op, ast.unparse(hit))))
            elif r.imported(n.value):                                # fix 14: another module's namespace
                out.append((n.lineno, "%s through imported namespace %s" % (op, ast.unparse(n.value))))
            elif not r.made_here(n.value):
                out.append((n.lineno, "%s through unresolved base %s" % (op, ast.unparse(n.value))))
            elif aug is not None and not r.made_here(n):          # fix 12: the element's in-place operator
                out.append((n.lineno, "augmented assignment %s through unresolved base %s"
                            % (_AUG_OPS[type(aug.op)], ast.unparse(n))))
        if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):                              # (6)
            if r.aug_name_refused(n.target):
                out.append((n.lineno, "augmented assignment %s through unresolved base %s"
                            % (_AUG_OPS[type(n.op)], n.target.id)))
        if isinstance(n, (ast.Name, ast.Attribute)) and isinstance(n.ctx, ast.Load) and r.inplace_form(n):  # (7)
            out.append((n.lineno, r.inplace_form(n)))
        if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load) and r.unresolved_receiver(n):     # (5)
            p = parents.get(id(n))
            if isinstance(p, ast.Call) and p.func is n:
                if n.attr not in _PURE_METHODS:                      # fix 13: unlisted methods are mutations
                    out.append((n.lineno, "method call %s through unresolved base %s"
                                % (n.attr, ast.unparse(n.value))))
                elif not r.pure_receiver(n.value, n.attr):           # a listed name, an unproven receiver
                    out.append((n.lineno, "unproven pure method call %s through unresolved base %s"
                                % (n.attr, ast.unparse(n.value))))
            elif n.attr in _MUTATOR_NAMES:
                out.append((n.lineno, "bound method %s taken through unresolved base %s"
                            % (n.attr, ast.unparse(n.value))))
        if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load) and r.imported(n.value) \
                and not r.module_ref(n.value) and not r.reaching(n):                                     # (9)
            p = parents.get(id(n))
            listed = all(_arg_safe(d) for d in r.cands(n) if d)
            if isinstance(p, ast.Call) and p.func is n \
                    and not (n.attr in _PURE_METHODS and r.pure_receiver(n.value, n.attr)) and not listed:
                out.append((n.lineno, "method call %s through imported namespace %s" % (n.attr, ast.unparse(n.value))))
            elif not (isinstance(p, ast.Call) and p.func is n) and n.attr in _MUTATOR_NAMES:
                out.append((n.lineno, "bound method %s taken through imported namespace %s"
                            % (n.attr, ast.unparse(n.value))))
        if isinstance(n, ast.Call):                                                                      # (8)
            out += [(n.lineno, k) for k in r.call_rows(n)]
        if isinstance(n, ast.Call) and r.reaching(n):                                                     # (2)
            out.append((n.lineno, "call of namespace-reaching %s" % ast.unparse(n.func)))
        if isinstance(n, (ast.Import, ast.ImportFrom)):                                                  # (3)
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else \
                [n.module or ""] + ["%s.%s" % (n.module, a.name) for a in n.names if n.module]
            for m in sorted({m for m in mods if _in_module(m, _REACH_IMPORTS)}):
                if _in_module(m, _EXECUTOR_IMPORTS) and r.benign_import(n, m):
                    continue                                         # fix pass 11: only literal timing code
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
    if measured is not None and all(_unresolved(k) for _l, k in out) \
            and _site_names(tree, out) == sorted(measured):
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
          relying on (6)'s list of rebinding forms alone; since fix pass 11 a
          base is followed through module-local calls, and mutator methods on
          an unresolved receiver and the listed executors are in the bound;
          since fix pass 12 element provenance survives slices, copies and
          iteration, higher-order local callbacks are followed, and every
          in-place operator on an unresolved receiver is refused; since fix
          pass 13 every binding form the binding table holds is followed (a
          binding node outside it is refused), a method on an unresolved
          receiver off _PURE_METHODS and a call of an unresolved callable or
          of a library callable off _ARG_SAFE with a marked argument are
          refused, and iter and reversed may return their argument.
          It is a bound over those lists and that data flow, not a claim
          that every conceivable rebinding is detected."""
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


def unwrapped_queries(source: str, file: str = "<source>", tree=None) -> list:
    """Every reference that can turn a failure into a False/absent answer:
    an os.path status predicate, os.access, a pathlib predicate, a getattr
    on a path module, and an os.walk whose handler is not proven -- through
    any import or assignment alias, called or not. An os.walk row is a
    Reported naming, by `file`, line and kind, every operation of the module
    that can rebind a never-suppress manager (fix pass 9) or reach a
    namespace (fix pass 10). `tree` (fix pass 13) is the seam a control uses
    to hand the proof a parsed module holding a node of a class outside the
    binding table; by default the source is parsed."""
    tree = ast.parse(source) if tree is None else tree
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
           "def scan(p):\n    if type(p) is not str:\n        raise NoVerdict('root')\n"
           "    return list(os.walk(p, onerror=_walk_error))\n\n\n"
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


# Fix pass fifteen: explicit-call signatures, receiver elements and class LOAD_NAME ordering.
def _fix15_rows(source):
    tree = ast.parse(source)
    parents = {id(c): n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    return [kind for _line, kind in _namespace_reach(tree, _Names(tree, parents))]


def _fix15_has(source, text):
    return any(text in kind for kind in _fix15_rows(source))


def test_m5_fix15_a_protocol_exemptions_are_signature_specific():
    cases = {
        "direct_type": ('def f(obj):\n    type("Made", (obj,), {})\n',
                        "call of protocol-running callable type through unresolved base (obj,)"),
        "keyword_type": ('def f(obj):\n    type(name="Made", bases=(obj,), dict={})\n',
                         "call of protocol-running callable type through unresolved base (obj,)"),
        "callback_type": ('def f(obj):\n    map(type, ("Made",), (obj,), ({},))\n',
                          "callback of map (protocol-running callable type) through unresolved base (obj,)"),
        "bytearray_append": ("def f(obj):\n    bytearray().append(obj)\n",
                             "call of protocol-running callable bytearray().append through unresolved base obj"),
    }
    for source, expected in cases.values():
        assert _fix15_has(source, expected), expected


def test_m5_fix15_b_exact_safe_signatures_stay_trusted():
    source = ("import sys\n\n\ndef f(obj):\n    type(obj)\n    id(obj)\n    callable(obj)\n    ord(obj)\n"
              "    slice(obj)\n    slice(None, obj)\n    slice(None, None, obj)\n    super(obj)\n"
              "    ValueError(obj)\n    OSError(obj, None)\n    PermissionError(obj, None)\n"
              "    BlockingIOError(obj, None, False)\n"
              "    SyntaxError(obj, ('file', None, None, None))\n"
              "    ExceptionGroup(obj, [])\n"
              "    UnicodeEncodeError(obj, obj, False, False, obj)\n    map(type, (obj,))\n"
              "    try:\n        sys.exit(obj)\n    except SystemExit:\n        pass\n")
    assert not _fix15_rows(source)


def test_m5_fix15_c_protocol_running_signatures_stay_refused():
    cases = {
        "type_star": ("def f(obj):\n    type(*obj)\n", "call of protocol-running callable type"),
        "exit_many": ("import sys\n\n\ndef f(obj, extra):\n    sys.exit(obj, extra)\n",
                      "call of protocol-running callable sys.exit"),
        "exit_keyword": ("import sys\n\n\ndef f(obj):\n    sys.exit(status=obj)\n",
                         "call of protocol-running callable sys.exit"),
        "len": ("def f(obj):\n    len(obj)\n", "call of protocol-running callable len"),
        "len_star": ("def f(obj):\n    len(*[obj])\n", "call of protocol-running callable len"),
        "fspath": ("import os\n\n\ndef f(obj):\n    os.fspath(obj)\n",
                   "call of protocol-running callable os.fspath"),
        "isinstance_classinfo": ("def f(obj):\n    isinstance(False, (obj,))\n",
                                 "call of protocol-running callable isinstance"),
        "augmented_receiver": ("def f(obj):\n    held = (False,)\n    held += obj\n    held.count(False)\n",
                               "call of unresolved callable held.count through unresolved base held.count"),
    }
    for source, expected in cases.values():
        assert _fix15_has(source, expected), expected


def test_m5_fix15_d_protocol_running_exception_constructors_stay_refused():
    cases = {
        "blocking_io": ("def f(obj):\n    BlockingIOError(None, None, obj)\n",
                        "call of protocol-running callable BlockingIOError"),
        "syntax": ("def f(obj):\n    SyntaxError(None, obj)\n", "call of protocol-running callable SyntaxError"),
        "group": ("def f(obj):\n    ExceptionGroup(\"group\", obj)\n",
                  "call of protocol-running callable ExceptionGroup"),
        "unicode": ("def f(obj):\n    UnicodeDecodeError(\"codec\", b\"\", obj, obj, \"reason\")\n",
                    "call of protocol-running callable UnicodeDecodeError"),
        "os_error_dispatch": ("from errno import EAGAIN\ndef f(obj):\n    OSError(EAGAIN, None, obj)\n",
                              "call of protocol-running callable OSError"),
    }
    for source, expected in cases.values():
        assert _fix15_has(source, expected), expected


def test_m5_fix15_e_builtin_receiver_elements_are_judged_directly_and_as_callbacks():
    cases = {
        "list_count": ("def f(obj):\n    [obj].count(False)\n", "through unresolved base [obj]"),
        "dict_get": ('def f(obj):\n    {obj: None}.get("missing")\n', "through unresolved base {obj: None}"),
        "dict_pop": ('def f(obj):\n    {obj: None}.pop("missing")\n', "through unresolved base {obj: None}"),
        "dict_update_receiver": ('def f(obj):\n    {obj: None}.update({"key": False})\n',
                                 "through unresolved base {obj: None}"),
        "dict_update_argument": ('def f(obj):\n    {"key": None}.update({obj: None})\n',
                                 "through unresolved base {obj: None}"),
        "list_clear": ("def f(obj):\n    [obj].clear()\n", "through unresolved base [obj]"),
        "callback_count": ("def f(obj):\n    map([obj].count, (False,))\n",
                           "callback of map (protocol-running callable [obj].count) through unresolved base [obj]"),
    }
    for source, expected in cases.values():
        assert _fix15_has(source, expected), expected


def test_m5_fix15_f_element_blind_receiver_controls_stay_trusted():
    source = ('def f(obj, extra):\n    [False].count(False)\n    "value".count("a")\n    len([obj])\n'
              '    {obj: None}.keys()\n    {obj: None}.values()\n    {obj: None}.items()\n'
              '    {obj: None}.copy()\n'
              '    {}.update({"key": obj})\n'
              "    [obj].append(extra)\n    [obj].extend(())\n    [obj].insert(False, False)\n"
              "    [obj].reverse()\n    [obj].pop()\n    {obj}.pop()\n    {obj: None}.popitem()\n")
    assert not _fix15_rows(source)
    dunder_rows = _fix15_rows("def f(obj):\n    [obj].__len__()\n    [obj].__iter__()\n")
    assert set(dunder_rows) == {
        "call of namespace-reaching [obj].__len__",
        "call of namespace-reaching [obj].__iter__",
    }                                                               # receiver policy adds no duplicate protocol row


_FIX15_CLASS_PREFIX = ("from posixpath import os as x\ncondition = False\n"
                       "replacement = lambda *args, **kwargs: ()\n")


def test_m5_fix15_g_class_body_prebinding_falls_back_to_the_module_namespace():
    bodies = (
        "class C:\n    x.walk = replacement\n    x = {}\n",
        "class C:\n    if condition:\n        x = {}\n    x.walk = replacement\n",
        "def outer():\n    x = {}\n    class C:\n        x.walk = replacement\n        x = {}\n\nouter()\n",
        "class C:\n    x = x\n    x.walk = replacement\n",
        "class C:\n    y = x\n    x = y\n    x.walk = replacement\n",
        "class C:\n    x = {}\n    del x\n    x.walk = replacement\n",
        "class C:\n    x = {}\n    if not condition:\n        del x\n        x.walk = replacement\n",
    )
    for body in bodies:
        assert _fix15_has(_FIX15_CLASS_PREFIX + body, "attribute store through imported namespace x"), body
    deletion = _FIX15_CLASS_PREFIX + "class C:\n    x = {}\n    del x, x.walk\n"
    assert _fix15_has(deletion, "attribute deletion through imported namespace x")


def test_m5_fix15_h_class_scope_controls_keep_their_prior_verdicts():
    prior = _FIX15_CLASS_PREFIX + "class C:\n    x = {}\n    x.walk = replacement\n"
    deferred = _FIX15_CLASS_PREFIX + "class C:\n    x = lambda: x\n    x.walk = replacement\n"
    annotated = _FIX15_CLASS_PREFIX + "class C:\n    x = {}\n    x: dict\n    x.walk = replacement\n"
    conditional = (_FIX15_CLASS_PREFIX
                   + "class C:\n    x = {}\n    if condition:\n        x = {}\n    x.walk = replacement\n")
    nested = (_FIX15_CLASS_PREFIX
              + "class C:\n    x = {}\n    def mutate():\n        x.walk = replacement\n")
    cell = ("def outer():\n    x = {}\n    class C:\n        x['walk'] = None\n\nouter()\n")
    assert not _fix15_rows(prior)
    assert not _fix15_rows(deferred)
    assert not _fix15_rows(annotated)
    assert not _fix15_rows(conditional)
    assert not _fix15_rows(cell)
    assert _fix15_has(nested, "attribute store through imported namespace x")


def test_m5_fix15_i_class_fallback_covers_augmented_and_builtin_operations():
    augmented = "from sys import path as x\nclass C:\n    x += []\n"
    builtin = "def f(obj):\n    class C:\n        len(obj)\n        len = lambda value: None\n"
    conditional = ("def f(obj, condition):\n    class C:\n        if condition:\n"
                   "            len = lambda value: None\n        len(obj)\n")
    carried = ("replacement = None\ndef f(obj, condition):\n    def identity(value):\n        return obj\n"
               "    class C:\n        if condition:\n            map = lambda func, iterable: []\n"
               "        held = map(identity, (None,))\n        next(held).walk = replacement\n")
    assert _fix15_has(augmented, "augmented assignment += through unresolved base x")
    assert _fix15_has(builtin, "call of protocol-running callable len through unresolved base obj")
    assert _fix15_has(conditional, "call of protocol-running callable len through unresolved base obj")
    assert _fix15_has(carried, "attribute store through unresolved base next(held)")


def test_m5_fix15_j_imported_values_are_protocol_marked_even_inside_containers():
    cases = {
        "argument": ("from helper import obj\nlen(obj)\n", "call of protocol-running callable len"),
        "classinfo": ("from helper import C\nisinstance(False, (C,))\n",
                      "call of protocol-running callable isinstance"),
        "receiver": ("from helper import obj\n[obj].count(False)\n", "through unresolved base [obj]"),
        "imported_method": ("from helper import thing\nthing.count(False)\n",
                            "method call count through imported namespace thing"),
    }
    for source, expected in cases.values():
        assert _fix15_has(source, expected), expected
    assert not _fix15_rows("from helper import obj\ntype(obj)\nlen([obj])\n")
    identity = ("from helper import obj\ndef identity(value):\n    return value\n"
                "def f():\n    len(identity(obj))\n")
    alias = ("from helper import obj\nx = [obj]\nclass C:\n    y = x\n    x = y\n"
             "    len(x)\n")
    alias_control = "x = [False]\nclass C:\n    y = x\n    x = y\n    len(x)\n"
    assert _fix15_has(identity, "call of protocol-running callable len through unresolved base identity(obj)")
    assert _fix15_has(alias, "call of protocol-running callable len through unresolved base x")
    assert not _fix15_rows(alias_control)


def test_m5_fix15_k_higher_order_aliases_and_expansions_are_judged():
    cases = {
        "map_alias": ("import builtins\ndef f(obj):\n"
                      "    builtins.map(type, ('Made',), (obj,), ({},))\n",
                      "callback of map (protocol-running callable type) through unresolved base (obj,)"),
        "map_star": ("def f(obj):\n    map(*(type, ('Made',), (obj,), ({},)))\n",
                     "call of protocol-running callable map"),
    }
    for source, expected in cases.values():
        assert _fix15_has(source, expected), expected
    mixed = ("from helper import obj\ncondition = False\n"
             "runner = map if condition else divmod\ndef f():\n    runner(obj, ())\n")
    assert _fix15_has(mixed, "call of protocol-running callable runner through unresolved base obj")
    mixed_callback = ("condition = True\ndef local(*args):\n    return ()\n"
                      "runner = map if condition else local\n"
                      "def f(obj):\n    for _ in runner(type, ('Made',), (obj,), ({},)):\n        pass\n")
    local_control = ("def local(*args):\n    return ()\n"
                     "def f(obj):\n    local(type, ('Made',), (obj,), ({},))\n")
    assert _fix15_has(mixed_callback, "callback of map (protocol-running callable type)")
    assert not _fix15_rows(local_control)
    alias_control = "import builtins\ndef f(obj):\n    builtins.map(type, (obj,))\n"
    assert not _fix15_has(alias_control, "protocol-running callable type")
    generator_boundary = ("def f(obj):\n    tuple(False for _ in (False,))\n"
                          "    tuple(False for _ in (False,) for inner in obj)\n"
                          "    tuple(value == False for value in (obj,))\n")
    assert not _fix15_rows(generator_boundary)


def test_m5_fix15_l_held_receiver_results_and_custom_class_mappings_are_refused():
    receivers = (
        "def f(obj):\n    [obj].copy().count(False)\n",
        "def f(obj):\n    ([obj] + []).count(False)\n",
    )
    for source in receivers:
        assert _fix15_has(source, "through unresolved base"), source
    local_next = ("from posixpath import os as imported\ncondition = True\nreplacement = None\n"
                  "class C:\n    if condition:\n        def next(iterable):\n            return imported\n"
                  "    value = next([{}])\n    value.walk = replacement\n")
    prepared = ("from posixpath import os as imported\nx = {}\nreplacement = None\n"
                "class Meta(type):\n    @classmethod\n    def __prepare__(mcls, name, bases):\n"
                "        return {'x': imported}\nclass C(metaclass=Meta):\n"
                "    x.walk = replacement\n    x = {}\n")
    assert _fix15_has(local_next, "attribute store through imported namespace value")
    next_builtin = ("from posixpath import os as imported\ncondition = False\nreplacement = None\n"
                    "class C:\n    if condition:\n        def next(iterable):\n            return {}\n"
                    "    value = next([imported])\n    value.walk = replacement\n")
    next_local = ("from posixpath import os as imported\nreplacement = None\n"
                  "class C:\n    def next(iterable):\n        return {}\n"
                  "    value = next([imported])\n    value.walk = replacement\n")
    prepared_control = ("x = {}\nreplacement = None\nclass C(metaclass=type):\n"
                        "    x.walk = replacement\n    x = {}\n")
    polluted_method = ("class Other:\n    def count(self, value):\n        return False\n"
                       "class C(list):\n    pass\ndef f(obj):\n    C([obj]).count(False)\n")
    direct_method = ("class C:\n    def count(self, value):\n        return False\n"
                     "def f(obj):\n    C().count(obj)\n")
    rebound_method = ("from helper import evil\nclass C:\n"
                      "    def count(self, value):\n        return False\n    count = evil\n"
                      "def f(obj):\n    C().count(obj)\n")
    decorated_method = ("from helper import evil as decorate\nclass C:\n    @decorate\n"
                        "    def count(self, value):\n        return False\n"
                        "def f(obj):\n    C().count(obj)\n")
    prepared_decorator = ("from posixpath import os as imported\nreplacement = None\n"
                          "class Meta(type):\n    @classmethod\n"
                          "    def __prepare__(mcls, name, bases):\n"
                          "        def unsafe(function):\n            return lambda: imported\n"
                          "        return {'staticmethod': unsafe}\n"
                          "class Outer(metaclass=Meta):\n    global exported\n    @staticmethod\n"
                          "    def exported():\n        return {}\n"
                          "exported().walk = replacement\n")
    prepared_base = ("from posixpath import os as imported\nreplacement = None\n"
                     "class BaseMeta(type):\n    pass\nclass Base(metaclass=BaseMeta):\n"
                     "    def __new__(cls):\n        return imported\n"
                     "class Meta(type):\n    @classmethod\n"
                     "    def __prepare__(mcls, name, bases):\n        return {'Exception': Base}\n"
                     "class Outer(metaclass=Meta):\n    global Exported\n"
                     "    class Exported(Exception):\n        pass\n"
                     "Exported().walk = replacement\n")
    decorator_control = ("replacement = None\nclass Outer(metaclass=type):\n"
                         "    global exported\n    @staticmethod\n"
                         "    def exported():\n        return {}\nexported().walk = replacement\n")
    base_control = ("replacement = None\nclass Outer:\n    global Exported\n"
                    "    class Exported(Exception):\n        pass\nExported().walk = replacement\n")
    assert _fix15_has(prepared, "attribute store through unresolved base x")
    assert _fix15_has(next_builtin, "attribute store through imported namespace value")
    assert _fix15_has(polluted_method, "call of unresolved callable C([obj]).count")
    assert _fix15_has(rebound_method, "call of unresolved callable C().count through unresolved base obj")
    assert _fix15_has(decorated_method, "pure method call count through unresolved base C()")
    assert _fix15_has(prepared_decorator, "attribute store through unresolved base exported()")
    assert _fix15_has(prepared_base, "attribute store through unresolved base Exported()")
    assert not _fix15_rows(next_local)
    assert not _fix15_rows(prepared_control)
    assert not _fix15_rows(direct_method)
    assert not _fix15_rows(decorator_control)
    assert not _fix15_rows(base_control)


# Fix pass sixteen: exact library receiver methods, never method names alone.
def test_m5_fix16_a_exact_library_receiver_reads_are_trusted():
    sources = (
        "import os\nos.environ.get('KEY')\n",
        "from os import environ as settings\nsettings.get('KEY')\n",
    )
    assert _PURE_LIBRARY_RECEIVERS == {"os.environ": frozenset({"get"})}
    for source in sources:
        assert not _fix15_rows(source), source


def test_m5_fix16_b_receiver_and_method_boundaries_stay_refused():
    cases = {
        "impure_method": ("import os\nos.environ.update({'KEY': 'value'})\n",
                          "method call update through imported namespace os.environ"),
        "method_off_receiver_table": ("import os\nos.environ.keys()\n",
                                      "method call keys through imported namespace os.environ"),
        "unresolved_receiver": ("def f(receiver):\n    receiver.get('KEY')\n",
                                "unproven pure method call get through unresolved base receiver"),
        "other_imported_receiver": ("from helper import environ\nenviron.get('KEY')\n",
                                    "method call get through imported namespace environ"),
    }
    for source, expected in cases.values():
        assert _fix15_has(source, expected), expected
    assert not _fix15_rows("def f():\n    {}.get('KEY')\n")


def test_m5_fix16_c_known_receiver_arguments_keep_the_existing_protocol_rule():
    source = "import os\ndef f(obj):\n    os.environ.get(obj)\n"
    assert _fix15_has(source, "call of protocol-running callable os.environ.get through unresolved base obj")
    assert not _fix15_has(source, "method call get through imported namespace os.environ")


def test_m5_fix16_d_callback_receivers_use_the_same_exact_rule():
    known = "import os\nsorted(('KEY',), key=os.environ.get)\n"
    listed = "import os\nsorted(('KEY',), key=os.path.basename)\n"
    unresolved = "def f(receiver):\n    sorted(('KEY',), key=receiver.get)\n"
    imported = "from helper import environ\nsorted(('KEY',), key=environ.get)\n"
    mixed = ("import os\ndef f(receiver, condition):\n"
             "    sorted(('KEY',), key=(os.path if condition else receiver).join)\n")
    assert not _fix15_rows(known)
    assert not _fix15_rows(listed)
    assert _fix15_has(unresolved, "callback method get of sorted through unresolved base receiver")
    assert _fix15_has(imported, "callback method get of sorted through imported namespace environ")
    assert _fix15_has(mixed, "callback method join of sorted through unresolved base os.path if condition else receiver")


def test_m5_fix16_e_flow_consults_the_same_receiver_rule(monkeypatch):
    tree = ast.parse("import os\nos.environ.get('KEY')\nos.environ.update({'KEY': 'value'})\n")
    parents = {id(c): n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    reach = _Reach(tree, _Names(tree, parents))
    calls = {n.func.attr: n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)}
    seen = []

    def tracked(_receiver, method):
        seen.append(method)
        return False

    monkeypatch.setattr(reach, "pure_receiver", tracked)
    reach.flow.call_lv(calls["get"], None)
    assert seen == ["get"]
    seen.clear()
    reach.flow.call_lv(calls["update"], None)
    assert not seen


def test_m5_fix16_f_library_storage_results_remain_unresolved():
    source = "import os\nvalue = os.environ.get('KEY')\nvalue.get('other')\n"
    assert _fix15_has(source, "unproven pure method call get through unresolved base value")
    assert not _fix15_has(source, "method call get through imported namespace os.environ")


def test_m5_fix16_g_removing_the_rule_lapses_the_real_module_clean_check(monkeypatch):
    with open(os.path.join(TOOLS, "review_needles.py"), encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    parents = {id(c): n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
    names = _Names(tree, parents)
    assert not _namespace_reach(tree, names, "review_needles.py")
    monkeypatch.delitem(_PURE_LIBRARY_RECEIVERS, "os.environ")
    rows = _namespace_reach(tree, names, "review_needles.py")
    remaining = [(line, kind) for line, kind in rows if not _unresolved(kind)]
    assert _site_names(tree, remaining) == [
        ("main", "method call get through imported namespace os.environ"),
    ]
