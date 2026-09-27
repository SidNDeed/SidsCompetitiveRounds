"""The /health word that says this build serves dance-card motion (T34).

Dance cards (design S11.3) adds four routes on this build -- the motion
upload, the per-visit motion read, the atlas and the selection -- and the
bot's GIF route (S6.2) once it is built. `pc_motion` is how many of those
handlers are the endpoint of a route REGISTERED on the app when /health is
asked: absent on the build before the batch, 4 here, fewer on a build that
lost a route's registration. It is DERIVED on every request (#306, #342), so
a literal typed in either arm, a count of the tuple (definition rather than
registration) and a value cached at the first call each fail the unregister
controls below, which run against BOTH arms.
"""
import ast
import os
import pathlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))
sys.path.insert(0, HERE)

from test_player_cards_server import _run                        # noqa: E402
import main                                                      # noqa: E402
import schemas                                                   # noqa: E402

MAIN_PY = pathlib.Path(main.__file__).resolve()
# The motion routes this build carries, by handler: 4, and 5 once the bot's
# GIF route (S6.2) is built and joins main._PC_MOTION_ROUTES.
ROUTES = {
    "pc_motion_upload": ("/api/v1/pc/portrait/motion", "POST"),
    "pc_face_motion_read": ("/api/v1/pc-face/motion", "GET"),
    "pc_face_motion_atlas": ("/api/v1/pc-face/motion/{print_id}/{motion_rev}/{locale}/{size}.png", "GET"),
    "pc_dance_select": ("/api/v1/pc/dance", "POST"),
}
BUILT = len(ROUTES)


class _Up:
    async def execute(self, *a, **k):
        return None


class _Down:
    async def execute(self, *a, **k):
        raise OSError("database unreachable")


def _words():
    """(connected, degraded) pc_motion as the response model renders them;
    each answer is first checked to be the arm it claims to be."""
    up = _run(main.health_check(db=_Up())).model_dump()
    down = _run(main.health_check(db=_Down())).model_dump()
    assert (up["status"], down["status"]) == ("ok", "degraded"), (up["status"], down["status"])
    return up["pc_motion"], down["pc_motion"]


def _without(mp, *handlers):
    """The app's router with every route whose endpoint is one of `handlers`
    taken out and nothing else changed; `mp` puts the list back."""
    keep = [r for r in main.app.router.routes
            if not any(getattr(r, "endpoint", None) is h for h in handlers)]
    assert len(main.app.router.routes) - len(keep) == len(handlers), len(keep)
    mp.setattr(main.app.router, "routes", keep)


def test_health_pc_motion_derived(monkeypatch):
    """T34. Both arms read the registered motion routes, 4 here; each route
    taken out of the router reads 3 in both arms, all four out read 0, and
    every value comes back when the router does."""
    assert _words() == (BUILT, BUILT)
    for handler in main._PC_MOTION_ROUTES:
        with monkeypatch.context() as mp:
            _without(mp, handler)
            assert _words() == (BUILT - 1, BUILT - 1), handler.__name__
        assert _words() == (BUILT, BUILT), handler.__name__
    with monkeypatch.context() as mp:
        _without(mp, *main._PC_MOTION_ROUTES)
        assert _words() == (0, 0)
    assert _words() == (BUILT, BUILT)


def test_registration_counts_and_definition_does_not(monkeypatch):
    """A handler added to the tuple that no route serves leaves both arms at
    4; the same handler registered on a path reads 5 in both, and the probe
    route leaves with the router copy it was added to."""
    async def pc_motion_probe_t34():
        return None
    monkeypatch.setattr(main, "_PC_MOTION_ROUTES", main._PC_MOTION_ROUTES + (pc_motion_probe_t34,))
    assert _words() == (BUILT, BUILT)
    with monkeypatch.context() as mp:
        mp.setattr(main.app.router, "routes", list(main.app.router.routes))
        main.app.add_api_route("/api/v1/pc-motion-probe-t34", pc_motion_probe_t34, methods=["GET"])
        assert _words() == (BUILT + 1, BUILT + 1)
    assert not [r for r in main.app.router.routes if getattr(r, "endpoint", None) is pc_motion_probe_t34]
    assert _words() == (BUILT, BUILT)


def test_the_word_is_passed_in_both_arms_and_computed_nowhere_else():
    """The keyword appears exactly twice in main.py, once per arm, each a
    fresh call of the undecorated helper; the helper is called nowhere else
    (nothing caches it); the tuple is bound once, to exactly the four built
    handlers, and each is registered once, where its route says."""
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    health = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    assert len(health) == 1, len(health)
    tries = [n for n in ast.walk(health[0]) if isinstance(n, ast.Try)]
    assert len(tries) == 1, len(tries)
    ok_arm = {id(n) for stmt in tries[0].body for n in ast.walk(stmt)}
    degraded_arm = {id(n) for h in tries[0].handlers for n in ast.walk(h)}

    keywords = [k for k in ast.walk(tree) if isinstance(k, ast.keyword) and k.arg == "pc_motion"]
    assert len(keywords) == 2, len(keywords)
    assert sum(id(k) in ok_arm for k in keywords) == 1
    assert sum(id(k) in degraded_arm for k in keywords) == 1
    assert all(ast.unparse(k.value) == "_pc_motion_health_word()" for k in keywords)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_pc_motion_health_word"]
    assert len(calls) == 2, len(calls)
    helper = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_pc_motion_health_word"]
    assert len(helper) == 1 and helper[0].decorator_list == [], len(helper)

    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
              and n.id == "_PC_MOTION_ROUTES" and isinstance(n.ctx, ast.Store)]
    assert len(stores) == 1, len(stores)
    binding = [n for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "_PC_MOTION_ROUTES" for t in n.targets)]
    assert len(binding) == 1 and isinstance(binding[0].value, ast.Tuple), len(binding)
    names = [ast.unparse(e) for e in binding[0].value.elts]
    assert sorted(names) == sorted(ROUTES), names
    assert main._PC_MOTION_ROUTES == tuple(getattr(main, n) for n in names)
    served = {}
    for route in main.app.routes:
        for n in names:
            if getattr(route, "endpoint", None) is getattr(main, n):
                served.setdefault(n, []).append((route.path, sorted(route.methods)))
    assert served == {n: [(path, [method])] for n, (path, method) in ROUTES.items()}, served


def test_the_word_is_declared_without_a_default():
    """Declared as an int with no default, so an arm that left it out would
    raise rather than drop the key; the negative control is a name that is
    NOT declared and must be missing from the same dump (#306)."""
    field = schemas.HealthResponse.model_fields.get("pc_motion")
    assert field is not None and field.annotation is int and field.is_required()
    up = _run(main.health_check(db=_Up())).model_dump()
    assert up["pc_motion"] == BUILT
    assert "pc_motion_not_a_field" not in schemas.HealthResponse.model_fields
    assert "pc_motion_not_a_field" not in up
