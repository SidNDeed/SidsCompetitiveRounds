"""The counting tool's build marker on /health (release train).

In the form of test_lfp_casual.py's H1, with no database: both arms of health_check name
_REVIEW_CALIBRATE_BUILD under the key review_calibrate_build, its value is 1, HealthResponse declares it
as a required int, and the degraded answer carries it. The mutants run the same check on edited texts.
One more assertion: the tool's module file stands beside main.py in backend/api."""
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
