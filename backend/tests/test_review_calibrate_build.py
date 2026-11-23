"""The counting tool's build marker on /health (release train).

In the form of test_lfp_casual.py's H1, with no database: both arms of health_check name
_REVIEW_CALIBRATE_BUILD under the key review_calibrate_build, its value is 1, HealthResponse declares it
as a required int, and the degraded answer carries it. The mutants run the same check on edited texts.
One more assertion: the tool's module file stands beside main.py in backend/api. And the holder at the
end, by the route manifest's own index and walk: no route's or entry point's closure enters a binding of
the tool whose kind is other than import, and no binding of the tool that the index files as an import
carries a statement that is not an import. What stays in closures of the tool is its import statements,
each with the header of a block it stands in."""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, ".."))
API = os.path.join(BACKEND, "api")
MAIN = os.path.join(API, "main.py")
SCHEMAS = os.path.join(API, "schemas.py")
KEY = "review_calibrate_build"
CONST = "_REVIEW_CALIBRATE_BUILD"
ARM = "review_calibrate_build=_REVIEW_CALIBRATE_BUILD, "
FIELD = "    review_calibrate_build: int\n"


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().replace("\r\n", "\n")


def _schemas_from(src):
    """schemas.py's text as a module of its own (a fresh name), so an edited copy can be checked."""
    import importlib.util
    if API not in sys.path:
        sys.path.insert(0, API)
    name = "review_calibrate_build_schemas_%d" % abs(hash(src))
    spec = importlib.util.spec_from_loader(name, loader=None)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        exec(compile(src, SCHEMAS, "exec"), mod.__dict__)
    finally:
        sys.modules.pop(name, None)
    return mod


def check_marker(main_src, schemas_mod, answer=None):
    import ast
    tree = ast.parse(main_src)
    (health,) = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    (tried,) = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    connected = [ast.unparse(k.value) for s in tried.body for k in ast.walk(s)
                 if isinstance(k, ast.keyword) and k.arg == KEY]
    degraded = [ast.unparse(k.value) for h in tried.handlers for k in ast.walk(h)
                if isinstance(k, ast.keyword) and k.arg == KEY]
    assert (connected, degraded) == ([CONST], [CONST]), \
        "health arms: connected %r, degraded %r" % (connected, degraded)
    values = [ast.unparse(n.value) for n in tree.body if isinstance(n, ast.Assign)
              and [ast.unparse(t) for t in n.targets] == [CONST]]
    assert values == ["1"], "%s assigned %r" % (CONST, values)
    field = schemas_mod.HealthResponse.model_fields.get(KEY)
    assert field is not None and field.annotation is int and field.is_required(), \
        "HealthResponse.%s: %r" % (KEY, field)
    if answer is not None:
        assert answer["status"] == "degraded" and answer[KEY] == 1, answer


class _DownSession:
    async def execute(self, *a, **k):
        raise OSError("review_calibrate_build: the database is down")

    async def rollback(self):
        pass


def test_health_carries_review_calibrate_build_in_both_forms():
    if API not in sys.path:
        sys.path.insert(0, API)
    import main
    import schemas
    assert main._REVIEW_CALIBRATE_BUILD == 1
    answer = asyncio.run(main.health_check(db=_DownSession())).model_dump()
    check_marker(_read(MAIN), schemas, answer)


def test_the_marker_control_and_mutants():
    main_src, schemas_src = _read(MAIN), _read(SCHEMAS)
    check_marker(main_src, _schemas_from(schemas_src))                 # control: the texts as they stand
    assert main_src.count(ARM) == 2 and schemas_src.count(FIELD) == 1
    i = main_src.rindex(ARM)                                           # the degraded arm without the keyword
    arm_cut = main_src[:i] + main_src[i + len(ARM):]
    try:
        check_marker(arm_cut, _schemas_from(schemas_src))
    except AssertionError as ex:
        red = str(ex)
    else:
        raise AssertionError("the arm mutant left the marker check green")
    # the first line is the check's own message (pytest appends its rewrite below it)
    assert red.splitlines()[0] == "health arms: connected ['%s'], degraded []" % CONST, red
    try:                                                               # the model field missing
        check_marker(main_src, _schemas_from(schemas_src.replace(FIELD, "", 1)))
    except AssertionError as ex:
        red = str(ex)
    else:
        raise AssertionError("the field mutant left the marker check green")
    assert red.splitlines()[0] == "HealthResponse.%s: None" % KEY, red


def test_the_tool_module_stands_beside_main_py():
    assert os.path.isfile(os.path.join(os.path.dirname(MAIN), "review_calibrate.py")), API


# -- no route reaches the counting program's code ------------------------------------------------------
#
# The route manifest's walk resolves a bare name in every module of backend/api and folds in EVERY
# match, so a module-level binding of the counting program whose name an app binding also reads is
# entered from that app binding, although the app never imports the program and no route runs it.
# The program's bindings carry its mark (calibrate_*, _calibrate_*, CalibrateRefused, ...) so that no
# such edge exists. This holds two things, by the manifest test file's OWN index and walk (imported,
# never a second walk), over every route the manifest enumerates and every non-route entry point:
# (1) no closure enters a binding of review_calibrate.py whose kind is other than import; (2) no
# binding of the program that the index files as an import carries a statement that is not an
# import. What stays in closures of the program is its import statements, each with the header of a
# block it stands in. Every file of backend/api stays in the index; there is no table of modules.

PROGRAM = "review_calibrate"
ALLOWED = frozenset()       # program code bindings a closure may hold: none


def _manifest_test_module():
    tests = os.path.dirname(os.path.abspath(__file__))
    if tests not in sys.path:
        sys.path.insert(0, tests)
    import test_route_manifest_net_seat as manifest
    return manifest


def _surfaces(manifest):
    """[(label, seeds)]: the routes by the manifest's own enumeration filter (Mounts flattened, API and
    websocket routes, /api/v1/ paths), then the non-route entry points by section."""
    from fastapi.routing import APIRoute, APIWebSocketRoute
    from starlette.routing import Mount
    found = []

    def walk(routes, prefix=""):
        for route in routes:
            if isinstance(route, Mount):
                walk(route.routes, manifest._joined_path(prefix, route.path))
                continue
            if not isinstance(route, (APIRoute, APIWebSocketRoute)):
                continue
            path = manifest._joined_path(prefix, route.path)
            if path.startswith("/api/v1/"):
                label = " ".join(sorted(getattr(route, "methods", ()) or ("WS",))) + " " + path
                found.append((label, manifest._route_seeds(route)))

    walk(manifest.main.app.routes)
    for section, keys in sorted(manifest._entry_point_sections().items()):
        for module, name in keys:
            found.append(("%s %s.%s" % (section, module, name), [(module, name)]))
    return found


def program_code_entries(manifest, surfaces, index=None):
    """[(surface, parent binding, entered name)] for every program CODE binding a closure holds,
    ALLOWED aside. With `index` None the manifest's own memoised walk over its own index; with an
    index given, the same walk over that index (the mutants)."""
    idx = manifest._binding_index() if index is None else index
    out = []
    for label, seeds in surfaces:
        reached = manifest._reached(seeds) if index is None else manifest._walk_bindings(seeds, idx)
        held = {n for (m, n), kind in reached.items()
                if m == PROGRAM and kind != "import" and n not in ALLOWED}
        if not held:
            continue
        for (m, n), kind in sorted(reached.items()):
            if m == PROGRAM:
                continue
            for ref in sorted(idx[m][n][2] & held):
                if kind == "data" and idx[PROGRAM][ref][0] != "data":
                    continue
                out.append((label, "%s.%s" % (m, n), ref))
        if not any(row[0] == label for row in out):
            out.append((label, "(no parent outside the program)", ",".join(sorted(held))))
    return out


def import_bindings_with_more(manifest, source, program_index, tmp_path):
    """The names `program_index` (the index of `source`) files with the kind "import" that the index
    still binds once every import statement of `source`, at any depth, is replaced by `pass`: an
    import binding that carries a statement other than an import. Asked of the manifest's own
    _index_module; no walk of statements here."""
    import ast

    class _NoImports(ast.NodeTransformer):
        def visit_Import(self, node):
            return ast.copy_location(ast.Pass(), node)

        visit_ImportFrom = visit_Import

    stripped = ast.unparse(ast.fix_missing_locations(_NoImports().visit(ast.parse(source))))
    path = tmp_path / (PROGRAM + "_without_imports.py")
    path.write_text(stripped + "\n", encoding="utf-8")
    without = manifest._index_module(path)
    return sorted(name for name, binding in program_index.items()
                  if binding[0] == "import" and name in without)


def _planted_index(manifest, tmp_path, tail):
    """The manifest's index with the program's file read again by the index's own reader, after
    `tail` is appended to its text."""
    with open(os.path.join(API, PROGRAM + ".py"), encoding="utf-8") as fh:
        text = fh.read()
    planted = tmp_path / (PROGRAM + ".py")
    planted.write_text(text + "\n\n" + tail + "\n", encoding="utf-8")
    index = dict(manifest._binding_index())
    index[PROGRAM] = manifest._index_module(planted)
    return index


def test_no_route_or_entry_point_closure_holds_the_counting_programs_code(tmp_path):
    manifest = _manifest_test_module()
    assert PROGRAM in manifest._binding_index(), "the program's file left the index"
    surfaces = _surfaces(manifest)
    assert len(surfaces) > 400 and any(label.startswith("background_entry_points ") for label, _ in surfaces)
    held = program_code_entries(manifest, surfaces)
    assert held == [], "closures that hold the counting program's code (surface, parent, entered): %r" % held[:20]
    # mutant: a def planted in the program under a name an app function reads (pc_face reads `render`)
    red = program_code_entries(manifest, surfaces,
                               _planted_index(manifest, tmp_path, "def render(tally):\n    return []"))
    assert red and {entered for _s, _p, entered in red} == {"render"}, red[:5]
    assert any(parent == "pc_face._emoji_image_at" for _s, parent, _e in red), red[:5]
    # mutant: an import leaf planted under the same name stays outside the assertion
    green = program_code_entries(manifest, surfaces,
                                 _planted_index(manifest, tmp_path, "from math import floor as render"))
    assert green == [], green[:5]

    # the second assertion: no binding of the program that the index files as an import carries a
    # statement that is not an import
    real = manifest._binding_index()[PROGRAM]
    with open(os.path.join(API, PROGRAM + ".py"), encoding="utf-8") as fh:
        source = fh.read()
    more = import_bindings_with_more(manifest, source, real, tmp_path)
    assert more == [], "import bindings of the program that carry a statement other than an import: %r" % more
    planted_file = tmp_path / (PROGRAM + ".py")
    for tail in ("sys.tracebacklimit = 0", "sys = None", "sys: object = None",
                 "def sys():\n    return None"):                      # plants: RED by the name sys
        planted = _planted_index(manifest, tmp_path, tail)
        rows = import_bindings_with_more(manifest, planted_file.read_text(encoding="utf-8"),
                                         planted[PROGRAM], tmp_path)
        assert rows == ["sys"], (tail, rows)
    for tail in ("_calibrate_plant = {}\n_calibrate_plant['k'] = 1",   # plants: GREEN
                 "import os"):
        planted = _planted_index(manifest, tmp_path, tail)
        rows = import_bindings_with_more(manifest, planted_file.read_text(encoding="utf-8"),
                                         planted[PROGRAM], tmp_path)
        assert rows == [], (tail, rows)
    # self-check: the index files the first plant under the import binding sys, kind kept
    planted = _planted_index(manifest, tmp_path, "sys.tracebacklimit = 0")
    assert (planted[PROGRAM]["sys"][0] == "import"
            and len(planted[PROGRAM]["sys"][1]) > len(real["sys"][1])), (
        "the index no longer files a module-level assignment under the import binding its target "
        "names; derive this assertion again from the manifest's _index_module")
