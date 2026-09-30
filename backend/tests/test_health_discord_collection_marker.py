"""The /health word that says this build serves the Discord collection (LR1).

The Discord collection added four internal routes -- the pack list, a pack's
strip, the binder list and a binder page -- and the /health word
`discord_collection` (main._DISCORD_COLLECTION_MARKER): 1 on a build that
serves those routes, on both roles, and absent on any build before it. The
schema declares the word with a default of None, so an arm that stopped
passing it, passed a near-name instead, or passed another number would still
answer 200. Only a test of the two answers themselves goes red on that: the
route manifest's fingerprint of health_check is re-pinned whenever the
handler changes on purpose, so it cannot be the guard.

So the word is tied to the routes, in BOTH arms, and the test runs on every
tree, never skipping. All four routes registered: the connected and the
degraded answer each carry 1, read from the constant (moved to 0, both
answers move with it), and main.py passes the constant once per arm and reads
it nowhere else. None registered: neither answer carries the word and neither
arm passes it. Any other set of the four is refused -- a build that serves
part of the collection is neither build.
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
WORD = "discord_collection"
CONSTANT = "_DISCORD_COLLECTION_MARKER"
EXPECTED = 1            # what the release train reads as the collection's build
ROUTES = (
    ("/api/v1/internal/pc/packs", "GET"),
    ("/api/v1/internal/pc/packs/{pack_id}/strip/{locale}.png", "GET"),
    ("/api/v1/internal/pc/binder", "GET"),
    ("/api/v1/internal/pc/binder/{owner_ref}/page/{page}/{locale}.png", "GET"),
)
NOT_A_FIELD = WORD + "_not_a_field"


class _Up:
    async def execute(self, *a, **k):
        return None


class _Down:
    async def execute(self, *a, **k):
        raise OSError("database unreachable")


def _health():
    """(connected answer, degraded answer) as the response model renders
    them; each is first checked to be the arm it claims to be."""
    up = _run(main.health_check(db=_Up())).model_dump()
    down = _run(main.health_check(db=_Down())).model_dump()
    assert (up["status"], down["status"]) == ("ok", "degraded"), (up["status"], down["status"])
    return up, down


def _served():
    """How many of the four routes the app registers (path and method)."""
    registered = {(r.path, m) for r in main.app.routes for m in (getattr(r, "methods", None) or ())}
    return sum(route in registered for route in ROUTES)


def _arms(tree):
    """(ids of every node in the connected arm, ids in the degraded arm)."""
    health = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    assert len(health) == 1, len(health)
    tries = [n for n in ast.walk(health[0]) if isinstance(n, ast.Try)]
    assert len(tries) == 1, len(tries)
    ok_arm = {id(n) for stmt in tries[0].body for n in ast.walk(stmt)}
    degraded_arm = {id(n) for h in tries[0].handlers for n in ast.walk(h)}
    return ok_arm, degraded_arm


def test_both_arms_carry_the_word_exactly_when_the_four_routes_are_served(monkeypatch):
    """Four served: 1 in the connected AND the degraded answer, and moving
    the constant to 0 moves both, so neither arm types a 1 of its own. None
    served: the word is in neither answer. The negative control is a name the
    model does not declare, missing from both answers either way (#306)."""
    served = _served()
    assert served in (0, len(ROUTES)), "%d of the four routes are registered" % served
    up, down = _health()
    assert NOT_A_FIELD not in up and NOT_A_FIELD not in down
    assert NOT_A_FIELD not in schemas.HealthResponse.model_fields
    if not served:
        assert (up.get(WORD), down.get(WORD)) == (None, None), (up.get(WORD), down.get(WORD))
        return
    assert (up.get(WORD), down.get(WORD)) == (EXPECTED, EXPECTED), (up.get(WORD), down.get(WORD))
    monkeypatch.setattr(main, CONSTANT, 0)
    up0, down0 = _health()
    assert (up0.get(WORD), down0.get(WORD)) == (0, 0), (up0.get(WORD), down0.get(WORD))


def test_the_word_is_passed_once_per_arm_as_the_constant_and_read_nowhere_else():
    """Four served: main.py passes the keyword exactly twice, once in each
    arm, both times the bare constant; the constant is bound once, at module
    level, to the literal the train reads, and loaded exactly twice, once per
    arm. None served: neither the keyword nor a load of the constant appears
    anywhere in main.py."""
    served = _served()
    assert served in (0, len(ROUTES)), "%d of the four routes are registered" % served
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    ok_arm, degraded_arm = _arms(tree)
    keywords = [k for k in ast.walk(tree) if isinstance(k, ast.keyword) and k.arg == WORD]
    loads = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
             and n.id == CONSTANT and isinstance(n.ctx, ast.Load)]
    if not served:
        assert (len(keywords), len(loads)) == (0, 0), (len(keywords), len(loads))
        return
    assert len(keywords) == 2, len(keywords)
    assert sum(id(k) in ok_arm for k in keywords) == 1
    assert sum(id(k) in degraded_arm for k in keywords) == 1
    assert all(ast.unparse(k.value) == CONSTANT for k in keywords), [ast.unparse(k.value) for k in keywords]
    assert len(loads) == 2, len(loads)
    assert sum(id(n) in ok_arm for n in loads) == 1
    assert sum(id(n) in degraded_arm for n in loads) == 1
    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
              and n.id == CONSTANT and isinstance(n.ctx, ast.Store)]
    assert len(stores) == 1, len(stores)
    binding = [n for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == CONSTANT for t in n.targets)]
    assert len(binding) == 1, len(binding)
    value = binding[0].value
    assert isinstance(value, ast.Constant) and type(value.value) is int and value.value == EXPECTED, (
        ast.unparse(value))
    assert getattr(main, CONSTANT) == EXPECTED
