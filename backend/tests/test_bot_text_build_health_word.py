"""The bot text batch's build discriminator: /health carries `bot_text_build`,
the module constant main._BOT_TEXT_BUILD (1), on both health_check arms,
required by the schema. It names build identity only. What the batch changes
(typed text in the api's Discord posts and DMs and in the bot's messages
passes one helper once) is seen by no phase of the release train, so the
train can tell a refreshed box from a stale one only by this key (learnings
780, 794). A constant equal on both roles, so the train can read it through
the edge. The form is test_ban_cap_build_health_word.py's, with one mutant
per arm: the word taken out of that arm turns the check red."""
import ast
import asyncio
import copy

import pydantic
import pytest

import main
import schemas

KEY = "bot_text_build"
CONST = "_BOT_TEXT_BUILD"
NEIGHBOUR = "modlog_build"


class _DownSession:
    """A session whose server is gone: every statement raises."""

    async def execute(self, *a, **k):
        raise OSError("bot_text_build: the database is down")

    async def rollback(self):
        pass


def _main_tree():
    with open(main.__file__, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _health_try(tree):
    (health,) = [n for n in ast.walk(tree)
                 if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    (tried,) = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    return tried


def _marker_problems(tree, key=KEY, const=CONST):
    """Every way the tree misses the marker, as sentences; empty when both
    arms pass the constant, nothing else in main.py passes the key, and the
    constant is bound once, to 1 (the train refuses a falsy word)."""
    problems = []
    tried = _health_try(tree)
    connected = [ast.unparse(k.value) for s in tried.body for k in ast.walk(s)
                 if isinstance(k, ast.keyword) and k.arg == key]
    degraded = [ast.unparse(k.value) for h in tried.handlers for k in ast.walk(h)
                if isinstance(k, ast.keyword) and k.arg == key]
    if connected != [const]:
        problems.append(f"connected arm passes {connected}")
    if degraded != [const]:
        problems.append(f"degraded arm passes {degraded}")
    everywhere = [k for k in ast.walk(tree)
                  if isinstance(k, ast.keyword) and k.arg == key]
    if len(everywhere) != 2:
        problems.append(f"{len(everywhere)} keywords in main.py")
    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
              and n.id == const and isinstance(n.ctx, ast.Store)]
    bindings = [n for n in tree.body if isinstance(n, ast.Assign)
                and [ast.unparse(t) for t in n.targets] == [const]]
    if len(stores) != 1 or len(bindings) != 1 or ast.unparse(bindings[0].value) != "1":
        problems.append(f"{len(stores)} stores, bindings {[ast.unparse(b) for b in bindings]}")
    return problems


def _without_word(tree, arm, key):
    """A copy of the tree with the keyword `key` removed from one arm of
    health_check ("connected": the try body, "degraded": its handlers), and
    how many keywords the removal took."""
    mutant = copy.deepcopy(tree)
    tried = _health_try(mutant)
    roots = tried.body if arm == "connected" else tried.handlers
    removed = 0
    for root in roots:
        for node in ast.walk(root):
            if isinstance(node, ast.Call):
                kept = [k for k in node.keywords if k.arg != key]
                removed += len(node.keywords) - len(kept)
                node.keywords = kept
    return mutant, removed


def test_both_arms_carry_the_build_marker():
    assert _marker_problems(_main_tree()) == []


@pytest.mark.parametrize("arm", ["connected", "degraded"])
def test_the_word_taken_out_of_one_arm_turns_the_check_red(arm):
    """The mutant per arm: the word removed from that arm alone (exactly one
    keyword) and the check names that arm."""
    mutant, removed = _without_word(_main_tree(), arm, KEY)
    assert removed == 1, removed
    problems = _marker_problems(mutant)
    assert any(p.startswith(f"{arm} arm passes []") for p in problems), problems


@pytest.mark.parametrize("arm", ["connected", "degraded"])
def test_control_a_neighbour_word_taken_out_leaves_the_check_green(arm):
    """The control: the same removal of another build word from that arm is
    a real change of the tree and leaves this marker's check green."""
    mutant, removed = _without_word(_main_tree(), arm, NEIGHBOUR)
    assert removed == 1, removed
    assert _marker_problems(mutant) == []
    assert _marker_problems(mutant, key=NEIGHBOUR, const="_MODLOG_BUILD") != []


def test_the_schema_requires_the_word_and_the_answer_carries_it():
    """HealthResponse declares it an int with no default, so an arm that left
    it out would raise rather than drop the key; the degraded answer, built
    for real, reads 1."""
    field = schemas.HealthResponse.model_fields.get(KEY)
    assert field is not None and field.annotation is int and field.is_required(), field
    answer = asyncio.run(main.health_check(db=_DownSession())).model_dump()
    assert answer["status"] == "degraded" and answer[KEY] == 1, answer
    answer.pop(KEY)
    with pytest.raises(pydantic.ValidationError):
        schemas.HealthResponse(**answer)
