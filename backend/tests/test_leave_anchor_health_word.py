"""The small-abc lane's build discriminator: /health carries `leave_anchor`,
the module constant main._LEAVE_ANCHOR_BUILD (1), on both health_check arms,
required by the schema. The lane adds no route and no other health word, so
the release train can tell a refreshed box from a stale one only by this key
(learnings 780, 794). A constant equal on both roles, so the train can read
it through the edge. The form is the janitor_selftest_build test's
(test_janitor_selftest_classes.py)."""
import ast
import asyncio

import pydantic
import pytest

import main
import schemas


class _DownSession:
    """A session whose server is gone: every statement raises."""

    async def execute(self, *a, **k):
        raise OSError("leave_anchor: the database is down")

    async def rollback(self):
        pass


def _main_tree():
    with open(main.__file__, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def test_both_arms_carry_the_build_marker():
    """Both arms pass the constant and nothing else in main.py passes the
    key; the constant is bound once, to 1 (the train fails at once on a
    falsy word)."""
    tree = _main_tree()
    (health,) = [n for n in ast.walk(tree)
                 if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    (tried,) = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    connected = [ast.unparse(k.value) for s in tried.body for k in ast.walk(s)
                 if isinstance(k, ast.keyword) and k.arg == "leave_anchor"]
    degraded = [ast.unparse(k.value) for h in tried.handlers for k in ast.walk(h)
                if isinstance(k, ast.keyword) and k.arg == "leave_anchor"]
    assert (connected, degraded) == (["_LEAVE_ANCHOR_BUILD"], ["_LEAVE_ANCHOR_BUILD"])
    everywhere = [k for k in ast.walk(tree)
                  if isinstance(k, ast.keyword) and k.arg == "leave_anchor"]
    assert len(everywhere) == 2, len(everywhere)
    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
              and n.id == "_LEAVE_ANCHOR_BUILD" and isinstance(n.ctx, ast.Store)]
    (binding,) = [n for n in tree.body if isinstance(n, ast.Assign)
                  and [ast.unparse(t) for t in n.targets] == ["_LEAVE_ANCHOR_BUILD"]]
    assert len(stores) == 1 and ast.unparse(binding.value) == "1", ast.unparse(binding)


def test_the_schema_requires_the_word_and_the_answer_carries_it():
    """HealthResponse declares it an int with no default, so an arm that left
    it out would raise rather than drop the key; the degraded answer, built
    for real, reads 1."""
    field = schemas.HealthResponse.model_fields.get("leave_anchor")
    assert field is not None and field.annotation is int and field.is_required(), field
    answer = asyncio.run(main.health_check(db=_DownSession())).model_dump()
    assert answer["status"] == "degraded" and answer["leave_anchor"] == 1, answer
    answer.pop("leave_anchor")
    with pytest.raises(pydantic.ValidationError):
        schemas.HealthResponse(**answer)
