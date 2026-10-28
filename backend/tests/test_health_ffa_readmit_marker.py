"""The /health word that says this build carries FFA mid-game readmission.

`ffa_readmit` is the release train's build discriminator for the readmission
batch (design V3 P5): absent on the build before it, 9 on this one (every
wiring site loads its readmission helper), and between the two on a build
that lost a site's wiring. A marker whose only purpose is to be probed
(#306): nothing but the two health arms reads it.

The value is DERIVED from compiled code (#342): for each (function, name)
pair of main._FFA_READMIT_SITES, 1 when the name is in the function's
co_names. The last test runs the derivation on a COPY of main.py in both
directions: one site's helper renamed away reads 8, a comment-only edit
beside every site keeps 9. The copy keeps the controls off the tree a
running suite is reading.
"""
import ast
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

from test_player_cards_server import _run                        # noqa: E402
import main                                                      # noqa: E402
import schemas                                                   # noqa: E402

MAIN_PY = pathlib.Path(main.__file__).resolve()
BACKEND = MAIN_PY.parent.parent

# The nine wiring sites as V3 and the brief name them: (function, helper).
SITES = [
    ("_ffa_asm_gates", "RDM_CAPS_TOKEN"),
    ("_asm_census_write", "_asm_readmit_on"),
    ("_asm_gone_write", "_asm_hold_after_gone"),
    ("queue_cleanup_loop", "_ffa_readmit_janitor"),
    ("ffa_lobby_readmit", "_asm_readmit_work"),
    ("ffa_readmit_offer", "_rdm_attempt"),
    ("_ffa_admission_check", "_ffa_epoch_chain_v2"),
    ("submit_ffa_match", "_ffa_report_gate"),
    ("_spectate_admission", "_rdm_spectate_fighters"),
]


class _Up:
    async def execute(self, *a, **k):
        return None


class _Down:
    async def execute(self, *a, **k):
        raise OSError("database unreachable")


def _health():
    """(connected answer, degraded answer) as the response model renders them."""
    return (_run(main.health_check(db=_Up())).model_dump(),
            _run(main.health_check(db=_Down())).model_dump())


def _module_tree():
    return ast.parse(MAIN_PY.read_text(encoding="utf-8"))


def _top_level_function(tree, name):
    found = [n for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert len(found) == 1, (name, len(found))
    return found[0]


def test_the_marker_is_derived_from_the_nine_sites_and_reads_9_here():
    """Bound once, by the co_names derivation over the site table, and 9 at
    this tip; the site table is exactly the nine named sites."""
    tree = _module_tree()
    stores = [n for n in ast.walk(tree)
              if isinstance(n, ast.Name) and n.id == "_FFA_READMIT"
              and isinstance(n.ctx, ast.Store)]
    assert len(stores) == 1, len(stores)
    assigns = [n for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "_FFA_READMIT" for t in n.targets)]
    assert len(assigns) == 1, len(assigns)
    assert ast.unparse(assigns[0].value) == (
        "sum((1 for _rd_fn, _rd_name in _FFA_READMIT_SITES "
        "if _rd_name in _rd_fn.__code__.co_names))"), ast.unparse(assigns[0].value)
    got = [(fn.__name__, name) for fn, name in main._FFA_READMIT_SITES]
    assert got == SITES, got
    for fn, name in main._FFA_READMIT_SITES:
        assert name in fn.__code__.co_names, (fn.__name__, name)
    assert main._FFA_READMIT == 9


def test_both_health_arms_report_the_constant(monkeypatch):
    """ok AND degraded, and what they report is the constant, not a 9 typed
    beside it: moved to 0, both answers move with it."""
    up, down = _health()
    assert (up["status"], down["status"]) == ("ok", "degraded")
    assert (up["ffa_readmit"], down["ffa_readmit"]) == (9, 9)
    monkeypatch.setattr(main, "_FFA_READMIT", 0)
    up0, down0 = _health()
    assert (up0["ffa_readmit"], down0["ffa_readmit"]) == (0, 0)


def test_the_marker_is_declared_and_read_by_nothing_else():
    """Declared on the model with no default, passed in exactly the two arms,
    read nowhere else. The negative control is a name that is NOT declared
    and must be missing from the same dump."""
    field = schemas.HealthResponse.model_fields.get("ffa_readmit")
    assert field is not None and field.annotation is int and field.is_required()
    up, _ = _health()
    assert "ffa_readmit" in up
    assert "ffa_readmit_not_a_field" not in schemas.HealthResponse.model_fields
    assert "ffa_readmit_not_a_field" not in up

    tree = _module_tree()
    health = _top_level_function(tree, "health_check")
    tries = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    assert len(tries) == 1, len(tries)
    ok_arm = {id(n) for stmt in tries[0].body for n in ast.walk(stmt)}
    degraded_arm = {id(n) for h in tries[0].handlers for n in ast.walk(h)}

    loads = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
             and n.id == "_FFA_READMIT" and isinstance(n.ctx, ast.Load)]
    assert len(loads) == 2, len(loads)
    assert sum(id(n) in ok_arm for n in loads) == 1
    assert sum(id(n) in degraded_arm for n in loads) == 1

    keywords = [k for k in ast.walk(tree)
                if isinstance(k, ast.keyword) and k.arg == "ffa_readmit"]
    assert len(keywords) == 2, len(keywords)
    assert sum(id(k) in ok_arm for k in keywords) == 1
    assert sum(id(k) in degraded_arm for k in keywords) == 1
    assert all(ast.unparse(k.value) == "_FFA_READMIT" for k in keywords)


# -- the controls, on a copy of the file ---------------------------------------

_DRIVER = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import main\n"
    "print('MARKER=%d' % main._FFA_READMIT, flush=True)\n"
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _controls(text):
    """(name, mutated text, marker wanted). RED: the epoch version 2 helper
    renamed at its definition and both calls (the module still imports and
    every caller still resolves, but the admission check no longer loads
    the site's name): 8. GREEN: a comment line before every site's def: 9."""
    old = "_ffa_epoch_chain_v2("
    assert text.count(old) == 3, text.count(old)
    renamed = text.replace(old, "_ffa_epoch_chain_v2_renamed(")
    commented = text
    for fn, _name in SITES:
        hits = [m.start() for m in re.finditer(
            r"^(async def|def) %s\(" % re.escape(fn), commented, re.MULTILINE)]
        assert len(hits) == 1, (fn, len(hits))
        commented = (commented[:hits[0]] + "# readmit marker control: inert\n"
                     + commented[hits[0]:])
    return [("one-site-renamed-away", renamed, 8), ("comment-beside-every-site", commented, 9)]


def test_the_controls_run_on_a_copy_in_both_directions(tmp_path):
    """RED: one site's helper renamed away reads 8. GREEN: a comment-only
    edit beside every site reads 9, which also proves the copied tree
    imports at all. The worktree's main.py is the same bytes at the end."""
    original = MAIN_PY.read_bytes()
    before = _sha256(original)
    api = tmp_path / "backend" / "api"
    api.mkdir(parents=True)
    for p in (BACKEND / "api").glob("*.py"):
        shutil.copyfile(p, api / p.name)
    copy = api / "main.py"
    assert _sha256(copy.read_bytes()) == before
    text = original.decode("utf-8")
    driver = tmp_path / "marker_driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if not k.endswith("_PG_DSN") and k not in ("PYTEST_ADDOPTS", "BUG392_TESTS_REQUIRED")}
    env.update(FFA_TEST_PG_OPTOUT="1", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")

    for name, mutated, want in _controls(text):
        mutated_bytes = mutated.encode("utf-8")
        assert _sha256(mutated_bytes) != before, name
        copy.write_bytes(mutated_bytes)
        try:
            proc = subprocess.run([sys.executable, str(driver), str(api)],
                                  cwd=str(tmp_path / "backend"), env=env,
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=900)
        finally:
            copy.write_bytes(original)
        out = proc.stdout + proc.stderr
        markers = re.findall(r"^MARKER=(\d+)$", out, re.MULTILINE)
        assert markers == [str(want)], (name, markers, out[-3000:])
        assert proc.returncode == 0, (name, proc.returncode, out[-3000:])
        print("control %-28s marker %d" % (name, want))

    assert _sha256(MAIN_PY.read_bytes()) == before
