"""The counting tool's build marker on /health (release train).

In the form of test_lfp_casual.py's H1, with no database: both arms of health_check name
_REVIEW_CALIBRATE_BUILD under the key review_calibrate_build, its value is 1, HealthResponse declares it
as a required int, and the degraded answer carries it. The mutants run the same check on edited texts.
One more assertion: the tool's module file stands beside main.py in backend/api. And the holder at the
end, by the route manifest's own index and walk, holds three things: no route's or entry point's closure
enters a binding of the tool whose kind is other than import; no name the index files as an import of
the tool is bound again by another statement; and the text the index files under an import binding of
the tool holds import statements and the frozen header lines only."""
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
# such edge exists. This holds three things, by the manifest test file's OWN index and walk (imported,
# never a second walk), over every route the manifest enumerates and every non-route entry point:
# (1) no closure enters a binding of review_calibrate.py whose kind is other than import; (2) no name
# the index files as an import of the program is bound again by another statement; (3) the text the
# index files under an import binding of the program holds import statements and the frozen header
# lines only. Every file of backend/api stays in the index; there is no table of modules.

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
    still binds once every import statement of `source`, at any depth, is replaced by `pass`: a name
    filed as an import that another statement binds again. Asked of the manifest's own _index_module;
    no walk of statements here."""
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


# The program's block header lines that may stand in the text of an import binding, each with its
# reason. An exact account, not a ceiling: on the real tree the set of pieces that are not one import
# statement EQUALS this set, so a header nothing uses any more fails too.
FROZEN_HEADERS = frozenset({
    "try :",    # the one try block of review_calibrate.py around its imports: a failed import ends a
                # program run with one fixed line, and re-raises when the module is imported
})


def import_text_pieces(program_index):
    """([(name, piece)] for every piece that is not one import statement, [(name, piece)] failures)
    over the text `program_index` (an index by the manifest's own _index_module) files under each
    binding of the kind "import". The text is tokenized and cut at every NEWLINE token and every `;`
    (indentation, blank lines and comments drop out); a piece is its tokens joined by one space and
    must parse alone to exactly one Import or ImportFrom, or be a line of FROZEN_HEADERS. A text that
    does not tokenize is a failure. Every failure names the binding and the piece."""
    import ast
    import io
    import tokenize

    skip = {tokenize.INDENT, tokenize.DEDENT, tokenize.NL, tokenize.COMMENT, tokenize.ENDMARKER}
    others, failures = [], []
    for name, (kind, text, _refs) in sorted(program_index.items()):
        if kind != "import":
            continue
        pieces, current = [], []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type in skip:
                    continue
                if tok.type == tokenize.NEWLINE or (tok.type == tokenize.OP and tok.string == ";"):
                    if current:
                        pieces.append(" ".join(current))
                    current = []
                    continue
                current.append(tok.string)
        except (tokenize.TokenError, SyntaxError) as exc:
            failures.append((name, "(the text does not tokenize: %s)" % type(exc).__name__))
            continue
        if current:
            pieces.append(" ".join(current))
        for piece in pieces:
            try:
                body = ast.parse(piece).body
            except SyntaxError:
                body = []
            if len(body) == 1 and isinstance(body[0], (ast.Import, ast.ImportFrom)):
                continue
            others.append((name, piece))
            if piece not in FROZEN_HEADERS:
                failures.append((name, piece))
    return others, failures


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

    # the second assertion: no name the index files as an import of the program is bound again by
    # another statement
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

    # the third assertion: the text the index files under an import binding of the program holds
    # import statements and the frozen header lines only; asked of the manifest's own _index_module
    import pathlib
    others, failures = import_text_pieces(manifest._index_module(pathlib.Path(API) / (PROGRAM + ".py")))
    assert failures == [], "import bindings of the program whose text holds more (binding, piece): %r" % failures
    assert {piece for _name, piece in others} == FROZEN_HEADERS, (
        "the pieces that are not one import statement are not the frozen header lines: %r" % others)
    probe = "_calibrate_holder_probe"
    unclosed = "import sys; %s = (1,\n    2)" % probe
    for tail in ("import sys; %s = 0" % probe,                       # plants: RED by the name sys
                 "%s = 0; import sys" % probe,
                 "if True: import sys",
                 "if True: %s = 0; import sys" % probe,
                 "if True:\n    import sys",
                 "with open(__file__):\n    import sys",
                 "try:\n    import sys\nexcept ImportError:\n    sys = None",
                 "sys.tracebacklimit = 0",
                 unclosed):
        _others, rows = import_text_pieces(_planted_index(manifest, tmp_path, tail)[PROGRAM])
        assert rows and {name for name, _piece in rows} == {"sys"}, (tail, rows)
        if tail == unclosed:
            assert rows == [("sys", "(the text does not tokenize: TokenError)")], rows
    for tail in ("import sys  # a comment after the import",           # plants: GREEN
                 "import sys\n    # a comment line indented under the import",
                 "import sys; import os",
                 "from os import (\n    path,\n)",
                 "try:\n    import sys\nexcept ImportError:\n    pass",
                 "%s = {}\n%s['k'] = 1" % (probe, probe)):
        _others, rows = import_text_pieces(_planted_index(manifest, tmp_path, tail)[PROGRAM])
        assert rows == [], (tail, rows)
    # the control that is the finding itself: the first two RED plants are GREEN by parts 1 and 2
    for tail in ("import sys; %s = 0" % probe, "%s = 0; import sys" % probe):
        planted = _planted_index(manifest, tmp_path, tail)
        assert program_code_entries(manifest, surfaces, planted) == [], tail
        assert import_bindings_with_more(manifest, planted_file.read_text(encoding="utf-8"),
                                         planted[PROGRAM], tmp_path) == [], tail
    # self-check: with the first RED plant the index's text for sys holds the planted name, kind kept
    planted = _planted_index(manifest, tmp_path, "import sys; %s = 0" % probe)
    assert planted[PROGRAM]["sys"][0] == "import" and probe in planted[PROGRAM]["sys"][1], (
        "the index no longer files the whole physical line of an import under its binding; derive the "
        "third assertion again from the manifest's _index_module")
