"""Build round 4 M2: every closure module executes ONLY from its exact bound
source bytes.

review_boot is a source-only loader installed before the first closure module
can be imported: for each closure module it reads the source file, compiles
exactly those bytes and executes them, never consulting a bytecode cache, and
it keeps the bytes it executed; the rules loader digests THOSE bytes against a
revision's bound digest. A closure module executed by any other route is
refused, and so is a load run by a loader copy review_boot did not execute.
Bound and tested here:

  build      the api image can hold no cache (.dockerignore, bytecode writing
             off, build_no_bytecode.py after the code copy): what covers the
             modules imported before review_boot (review_boot, main.py);
  entry      the api entry point in a fresh process: the repository modules
             run before review_boot are main, database and flag_evidence,
             none is a closure module, and install() recorded nothing;
  caches     a header-valid cache whose code differs from its source, beside
             the source, under PYTHONPYCACHEPREFIX and at an optimisation
             level, carrying a WITNESS that fires when it executes: with
             review_boot first the witness never fires and the revision is
             built from source; the control (the same caches, imported the
             ordinary way) fires the witness, which proves each plant is a
             cache CPython would run, and is refused with nothing published;
  prior      a closure module executed before review_boot was installed, or
             under another name, is refused (also after it left the module
             table), and so is a load by a loader copy review_boot did not run;
  digest     the fingerprint is over the EXECUTED bytes: a revision bound to
             the bytes now on disk, after the file changed under a running
             process, is refused, and the one bound to the executed bytes loads.
"""

import importlib.util
import json
import marshal
import os
import re
import shutil
import subprocess
import sys
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import review_boot as rb  # noqa: E402
import review_measures as rm  # noqa: E402
import review_rules as rr  # noqa: E402
import review_testkit as tk  # noqa: E402

CHECK = os.path.join(API, "build_no_bytecode.py")


def _built(tmp_path, name="draft"):
    store, rev = tk.build_revision(tmp_path, name=name)
    return os.path.join(store, "rules-" + rev), rev


# -- build ---------------------------------------------------------------------------

def _check(root):
    return subprocess.run([sys.executable, "-B", CHECK, str(root)], capture_output=True, text=True,
                          timeout=60)


@pytest.mark.parametrize("plant", ["pycache_dir", "pyc_file", "pyo_file", "nested_pyc"])
def test_m2_the_build_check_fails_on_a_planted_cache(tmp_path, plant):
    root = tmp_path / "app"
    (root / "pkg").mkdir(parents=True)
    (root / "main.py").write_text("x = 1\n")
    assert _check(root).returncode == 0                                    # control: clean
    target = {"pycache_dir": root / "__pycache__",
              "pyc_file": root / "main.cpython-312.pyc",
              "pyo_file": root / "main.pyo",
              "nested_pyc": root / "pkg" / "__pycache__" / "m.cpython-312.opt-1.pyc"}[plant]
    if plant == "pycache_dir":
        target.mkdir()
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\x00")
    out = _check(root)
    assert out.returncode == 1 and "refused" in out.stdout


def test_m2_the_build_check_never_reads_an_unreadable_root_as_clean(tmp_path):
    assert _check(tmp_path / "missing").returncode == 2
    (tmp_path / "file").write_text("x")
    assert _check(tmp_path / "file").returncode == 2


def test_m2_the_image_is_built_cache_free():
    with open(os.path.join(API, "Dockerfile"), encoding="utf-8") as f:
        df = f.read()
    env = re.search(r"^ENV PYTHONDONTWRITEBYTECODE=1\s*$", df, re.M)
    first_python = re.search(r"^RUN (?:.*\s)?python\b", df, re.M)
    copy_all = re.search(r"^COPY \. \.\s*$", df, re.M)
    check = re.search(r"^RUN python -B build_no_bytecode\.py /app\s*$", df, re.M)
    assert env and first_python and copy_all and check
    assert env.start() < first_python.start(), "bytecode writing must be off before any Python runs"
    assert copy_all.start() < check.start(), "the check must run after the code copy"
    with open(os.path.join(API, ".dockerignore"), encoding="utf-8") as f:
        rules = {ln.strip() for ln in f if ln.strip() and not ln.startswith("#")}
    assert {"**/__pycache__", "**/*.pyc", "**/*.pyo"} <= rules


def test_m2_review_boot_is_imported_before_any_closure_module():
    """main.py imports review_boot ahead of the first closure import, and so
    does seat_evidence (the first closure importer)."""
    for name, first in (("main.py", "import review_boot, seat_evidence as _sev"),
                        ("seat_evidence.py", "import review_boot  #")):
        with open(os.path.join(API, name), encoding="utf-8") as f:
            src = f.read()
        boot = src.index(first)
        for closure in ("import review_measures", "import review_rules", "import seat_evidence"):
            at = src.find("\n" + closure)
            assert at == -1 or boot < at, (name, closure)


ENTRY = r'''
import importlib, os, sys
API = sys.argv[1]
CLOSURE = ("review_boot", "review_measures", "review_rules", "identity_clock_measures", "card_measures",
           "combat_measures")
SNAP = {}
class Stop(BaseException):
    pass
class Spy:
    def find_spec(self, name, path=None, target=None):
        if name == "review_boot" and "first" not in SNAP:
            SNAP["first"] = dict(sys.modules)
            f = sys._getframe(1)
            while f is not None and ("importlib" in f.f_code.co_filename or f.f_code.co_filename.startswith("<")):
                f = f.f_back
            SNAP["by"] = os.path.basename(f.f_code.co_filename)
        elif "first" in SNAP and name == "seat_evidence":
            rb = sys.modules["review_boot"]
            print("prior", ",".join(sorted(rb.PRIOR)) or "none")
            print("finder_first", sys.meta_path[0] is rb.FINDER)
            raise Stop()
        return None
sys.meta_path.insert(0, Spy())
sys.path.insert(0, API)
try:
    importlib.import_module("main")          # what uvicorn main:app does with the app directory on sys.path
except Stop:
    pass
root = os.path.normcase(os.path.abspath(API)) + os.sep
def _file(m):
    p = getattr(m, "__file__", None)
    return os.path.normcase(os.path.abspath(p)) if isinstance(p, str) and p else ""
mods = SNAP["first"]
print("by", SNAP["by"])
print("repository", ",".join(sorted(n for n, m in mods.items() if _file(m).startswith(root))))
print("closure", ",".join(sorted(n for n, m in mods.items() if n in CLOSURE
                                 or os.path.basename(_file(m)) in [c + ".py" for c in CLOSURE])) or "none")
'''


def test_m2_the_api_entry_point_runs_no_closure_module_before_review_boot():
    """The api process (uvicorn main:app imports the app module by name with
    the app directory on sys.path) in a fresh interpreter: at the FIRST lookup
    of review_boot, asked for by main.py, the repository modules already run
    are exactly main, database and flag_evidence, and no module in the table
    is a closure module by name or by file; install() then recorded nothing
    and put the source-only finder first. The modules uvicorn itself imports
    before the app are third-party and are not in this measurement."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    out = subprocess.run([sys.executable, "-B", "-c", ENTRY, API], cwd=API, capture_output=True, text=True,
                         timeout=300, env=env)
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines() == ["prior none", "finder_first True", "by main.py",
                                       "repository database,flag_evidence,main", "closure none"]


# -- in this process ---------------------------------------------------------------------

def test_m2_this_process_executed_each_closure_module_through_review_boot():
    for stem, mod in (("review_measures", rm), ("review_rules", rr)):
        assert rb.LOADED[stem][0] is mod is sys.modules[stem]
        assert mod.__spec__.loader is rb.FINDER and getattr(mod, "__cached__", None) is None
        with open(rb.source_path(stem), "rb") as f:
            assert rb.LOADED[stem][1] == f.read().replace(b"\r\n", b"\n")   # the bytes it executed


def test_m2_the_digest_is_over_the_executed_bytes(tmp_path, monkeypatch):
    rdir, rev = _built(tmp_path)
    assert rr.load_dir(rdir).rev == rev                                     # control
    mod, raw = rb.LOADED["review_measures"]
    monkeypatch.setitem(rb.LOADED, "review_measures", (mod, raw + b"#"))
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(rdir)
    assert (e.value.cls, str(e.value)) == ("stale", "stale: code closure")


def test_m2_a_closure_module_in_the_table_under_another_name_is_refused(tmp_path, monkeypatch):
    rdir, rev = _built(tmp_path)
    other = types.ModuleType("synthetic_other_route")
    other.__file__ = rm.__file__                                            # the closure source, another route
    monkeypatch.setitem(sys.modules, "synthetic_other_route", other)
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(rdir)
    assert str(e.value) == ("stale: closure module executed outside the source-only loader: "
                            "review_measures")
    monkeypatch.delitem(sys.modules, "synthetic_other_route")
    assert rr.load_dir(rdir).rev == rev                                     # control: gone


def test_m2_a_closure_module_recorded_at_install_is_refused(tmp_path, monkeypatch):
    rdir, rev = _built(tmp_path)
    monkeypatch.setattr(rb, "PRIOR", {"review_rules"})
    with pytest.raises(rr.Refused) as e:
        rr.load_dir(rdir)
    assert str(e.value) == "stale: closure module executed outside the source-only loader: review_rules"
    monkeypatch.setattr(rb, "PRIOR", set())
    assert rr.load_dir(rdir).rev == rev


def test_m2_a_loader_copy_review_boot_did_not_execute_refuses_to_load(tmp_path):
    rdir, rev = _built(tmp_path)
    ns = {"__name__": "synthetic_loader_copy"}
    exec(compile(rb.LOADED["review_rules"][1], rr.__file__, "exec", dont_inherit=True), ns)
    with pytest.raises(ns["Refused"]) as e:
        ns["load_dir"](rdir)
    assert str(e.value) == "stale: the running loader was not executed from its source"
    assert rr.load_dir(rdir).rev == rev                                     # control: the boot's copy


def test_m2_a_dotted_import_of_a_closure_name_is_refused():
    with pytest.raises(ImportError):
        rb.FINDER.find_spec("synthetic_pkg.review_rules")
    assert rb.FINDER.find_spec("synthetic_pkg.review_rulesx") is None      # control
    assert rb.FINDER.find_spec("json") is None


def test_m2_a_name_review_boot_did_not_execute_is_refused_in_the_closure():
    assert rr._code_files(rr.CODE_REQUIRED)                                 # control
    with pytest.raises(rr.Refused) as e:
        rr._code_files(rr.CODE_REQUIRED + ("seat_evidence.py",))
    assert str(e.value) == "stale: closure module not executed from its source: seat_evidence.py"


# -- fresh processes: caches, prior execution, the executed digest --------------------------

CHILD = r"""
import os, sys
api, draft, store, mode = sys.argv[1:5]
sys.path.insert(0, api)
if mode in ("plain", "prior", "prior_removed"):
    import review_measures                 # the ordinary import system, before review_boot
if mode == "plain":
    import identity_clock_measures         # the third stem, the ordinary way as well
    import card_measures                   # the fourth stem, the same way
    import combat_measures                 # the fifth stem, the same way
    import review_rules as rr              # imports review_boot itself, too late
else:
    import review_boot
    if mode == "prior_removed":
        del sys.modules["review_measures"]  # out of the table: only the install record remains
    import review_rules as rr
wit = os.environ["SCR_TEST_WITNESS"]
print("witness", ",".join(sorted(os.listdir(wit))) or "none")
if mode == "disk_changed":
    with open(os.path.join(api, "review_measures.py"), "ab") as f:
        f.write(b"\n# changed on disk after the import\n")
    for rdir in sys.argv[5:]:
        try:
            print("loaded", rr.load_dir(rdir).rev)
        except rr.Refused as e:
            print("refused", str(e))
    raise SystemExit(0)
try:
    print("built", rr.build_revision(draft, store, "synthetic"))
except rr.Refused as e:
    print("refused", str(e))
print("published", sorted(n for n in os.listdir(store) if n.startswith("rules-")))
"""

# review_boot.SOURCE_ONLY, the stems executed only from source bytes: the
# identity-clock measures module joined it in the identity-clock re-land
# (2026-10-29), so the planted-cache witnesses cover it as well
STEMS = ("review_measures", "review_rules", "identity_clock_measures", "card_measures", "combat_measures")


def _api_copy(tmp_path):
    d = tmp_path / "api"
    d.mkdir()
    for name in rr.CODE_REQUIRED:
        shutil.copy(os.path.join(API, name), d / name)
    return d


def _witness_cache(src, cfile, witness_name, optimize=-1):
    """A cache that is header-valid for `src` (its mtime and size) whose code
    is the source plus a WITNESS: executing it creates a file named
    `witness_name` in the directory SCR_TEST_WITNESS names."""
    with open(src, "rb") as f:
        raw = f.read()
    altered = raw + (b"\nimport os as _wos\nopen(_wos.path.join(_wos.environ['SCR_TEST_WITNESS'], '%s'), 'w')"
                     b".close()\n" % witness_name.encode())
    code = compile(altered, src, "exec", dont_inherit=True, optimize=optimize)
    st = os.stat(src)
    data = bytearray(importlib.util.MAGIC_NUMBER)
    data += (0).to_bytes(4, "little")
    data += (int(st.st_mtime) & 0xFFFFFFFF).to_bytes(4, "little")
    data += (st.st_size & 0xFFFFFFFF).to_bytes(4, "little")
    data += marshal.dumps(code)
    os.makedirs(os.path.dirname(cfile), exist_ok=True)
    with open(cfile, "wb") as f:
        f.write(bytes(data))


def _cache_for(src, prefix=None, optimization=""):
    keep = sys.pycache_prefix
    sys.pycache_prefix = prefix
    try:
        return importlib.util.cache_from_source(str(src), optimization=optimization)
    finally:
        sys.pycache_prefix = keep


def _child(tmp_path, api, mode, env_extra=None, flags=(), extra_args=()):
    draft = tk.write_draft(str(tmp_path / ("draft-" + mode)))
    store = tmp_path / ("store-" + mode)
    store.mkdir()
    wit = tmp_path / ("witness-" + mode)
    wit.mkdir()
    env = dict(os.environ)
    env.pop("PYTHONPYCACHEPREFIX", None)        # the child looks for caches where CPython would
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env["SCR_TEST_WITNESS"] = str(wit)
    env.update(env_extra or {})
    out = subprocess.run([sys.executable, "-B", *flags, "-c", CHILD, str(api), draft, str(store), mode,
                          *extra_args], capture_output=True, text=True, timeout=120, env=env)
    assert out.returncode == 0, out.stderr
    return out.stdout.splitlines()


def _plant(tmp_path, api, where):
    env, flags = {}, ()
    for stem in STEMS:
        src = api / (stem + ".py")
        if where == "beside_source":
            cfile = _cache_for(src)
        elif where == "pycache_prefix":
            prefix = str(tmp_path / "prefix")
            env = {"PYTHONPYCACHEPREFIX": prefix}
            cfile = _cache_for(src, prefix=prefix)
        else:
            flags = ("-O",)
            cfile = _cache_for(src, optimization=1)
        _witness_cache(str(src), cfile, stem, optimize=1 if where == "optimisation_level" else -1)
    return env, flags


def test_m2_control_without_a_cache_the_fresh_process_publishes(tmp_path):
    api = _api_copy(tmp_path)
    lines = _child(tmp_path, api, "boot")
    assert lines[0] == "witness none" and lines[1].startswith("built ") and lines[2] != "published []"


@pytest.mark.parametrize("where", ["beside_source", "pycache_prefix", "optimisation_level"])
def test_m2_an_altered_cache_is_never_executed_and_the_revision_builds_from_source(tmp_path, where):
    api = _api_copy(tmp_path)
    env, flags = _plant(tmp_path, api, where)
    lines = _child(tmp_path, api, "boot", env, flags)
    assert lines[0] == "witness none"                       # neither altered cache ran
    assert lines[1].startswith("built ") and lines[2] != "published []"


@pytest.mark.parametrize("where", ["beside_source", "pycache_prefix", "optimisation_level"])
def test_m2_control_the_same_caches_run_when_imported_the_ordinary_way_and_are_refused(tmp_path, where):
    api = _api_copy(tmp_path)
    env, flags = _plant(tmp_path, api, where)
    lines = _child(tmp_path, api, "plain", env, flags)
    assert lines[0] == "witness card_measures,combat_measures,identity_clock_measures,review_measures,review_rules"   # each plant is a cache CPython runs
    assert lines[1] == ("refused stale: closure module executed outside the source-only loader: "
                        "card_measures,combat_measures,identity_clock_measures,review_measures,review_rules")
    assert lines[2] == "published []"


@pytest.mark.parametrize("mode", ["prior", "prior_removed"])
def test_m2_a_closure_module_executed_before_review_boot_is_refused(tmp_path, mode):
    api = _api_copy(tmp_path)
    lines = _child(tmp_path, api, mode)
    assert lines[0] == "witness none"
    assert lines[1] == "refused stale: closure module executed outside the source-only loader: review_measures"
    assert lines[2] == "published []"


def test_m2_a_revision_bound_to_the_disk_bytes_after_a_change_is_refused(tmp_path):
    """The child executes the copy, then the copy's review_measures.py changes
    on disk. The revision bound to the bytes it EXECUTED loads; the revision
    bound to the bytes now on disk is refused stale."""
    api = _api_copy(tmp_path)
    rdir, rev = _built(tmp_path, "executed")
    changed = tmp_path / "changed"
    shutil.copytree(api, changed)
    with open(changed / "review_measures.py", "ab") as f:
        f.write(b"\n# changed on disk after the import\n")
    disk = tmp_path / "disk" / os.path.basename(rdir)
    shutil.copytree(rdir, disk)
    with open(disk / "rules.json", encoding="utf-8") as f:
        doc = json.load(f)
    doc["closure"]["fp"] = rr.code_fingerprint(api_dir=str(changed))
    assert doc["closure"]["fp"] != rr.code_fingerprint()
    with open(disk / "rules.json", "w", encoding="utf-8") as f:
        json.dump(doc, f)
    disk_dir, _disk_rev = tk.reseal(str(disk))
    lines = _child(tmp_path, api, "disk_changed", extra_args=(rdir, disk_dir))
    assert lines[0] == "witness none"
    assert lines[1] == "loaded " + rev
    assert lines[2] == "refused stale: code closure"
