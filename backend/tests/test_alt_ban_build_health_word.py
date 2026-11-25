"""ALT-BAN-1's two /health words and the region folder's mount.

alt_ban_build: the module constant main._ALT_BAN_BUILD (1), on both
health_check arms, required by the schema: release-train verification
plumbing, build identity only (learnings 780, 794), equal on both roles.
ban_region_file: geo_region.file_word() ('absent', 'refused' or the file's
build month), run in a thread on both arms, required by the schema; it says
nothing of the file's records.
The region folder reaches the api container only, read-only, after the
range list's mount. The form is the ban answers' build test's
(test_ban_answers_build_health_word.py)."""
import ast
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
if API not in sys.path:
    sys.path.insert(0, API)

import pydantic  # noqa: E402
import pytest  # noqa: E402

import geo_region  # noqa: E402
import main  # noqa: E402
import schemas  # noqa: E402

COMPOSE = os.path.normpath(os.path.join(HERE, "..", "docker-compose.yml"))
MOUNT = "      - ${SCR_GEO_DIR:-/opt/competitive-rounds/private/geo}:/app/private/geo:ro\n"
RANGES = "      - ${SCR_RANGES_DIR:-/opt/competitive-rounds/private/ranges}:/app/private/ranges:ro\n"


class _DownSession:
    """A session whose server is gone: every statement raises."""

    async def execute(self, *a, **k):
        raise OSError("alt_ban_build: the database is down")

    async def rollback(self):
        pass


def _main_tree():
    with open(main.__file__, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _arms(tree, key):
    (health,) = [n for n in ast.walk(tree)
                 if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    (tried,) = [n for n in ast.walk(health) if isinstance(n, ast.Try)]
    connected = [ast.unparse(k.value) for s in tried.body for k in ast.walk(s)
                 if isinstance(k, ast.keyword) and k.arg == key]
    degraded = [ast.unparse(k.value) for h in tried.handlers for k in ast.walk(h)
                if isinstance(k, ast.keyword) and k.arg == key]
    everywhere = [k for k in ast.walk(tree) if isinstance(k, ast.keyword) and k.arg == key]
    return connected, degraded, len(everywhere)


def test_both_arms_carry_the_build_marker():
    tree = _main_tree()
    assert _arms(tree, "alt_ban_build") == (["_ALT_BAN_BUILD"], ["_ALT_BAN_BUILD"], 2)
    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
              and n.id == "_ALT_BAN_BUILD" and isinstance(n.ctx, ast.Store)]
    (binding,) = [n for n in tree.body if isinstance(n, ast.Assign)
                  and [ast.unparse(t) for t in n.targets] == ["_ALT_BAN_BUILD"]]
    assert len(stores) == 1 and ast.unparse(binding.value) == "1", ast.unparse(binding)


def test_both_arms_read_the_region_files_word_in_a_thread():
    word = "await asyncio.to_thread(_geo_region.file_word)"
    assert _arms(_main_tree(), "ban_region_file") == ([word], [word], 2)


def test_main_reaches_the_reader_by_its_attributes_only():
    """`import geo_region as _geo_region`, once, at module level; no
    `from geo_region import`; each use an attribute of the alias."""
    tree = _main_tree()
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
               and any(a.name == "geo_region" for a in n.names) or
               isinstance(n, ast.ImportFrom) and n.module == "geo_region"]
    assert [ast.unparse(n) for n in imports] == ["import geo_region as _geo_region"]
    assert imports[0] in tree.body
    uses = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "_geo_region"]
    attrs = {n.value.id + "." + n.attr for n in ast.walk(tree)
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "_geo_region"}
    assert "_geo_region.file_word" in attrs and attrs <= {"_geo_region.region_of", "_geo_region.file_word"}, attrs
    assert len(uses) == sum(1 for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                            and isinstance(n.value, ast.Name) and n.value.id == "_geo_region")


@pytest.mark.parametrize("key,kind", [("alt_ban_build", int), ("ban_region_file", str)])
def test_the_schema_requires_the_word_and_the_answer_carries_it(key, kind):
    field = schemas.HealthResponse.model_fields.get(key)
    assert field is not None and field.annotation is kind and field.is_required(), field
    answer = asyncio.run(main.health_check(db=_DownSession())).model_dump()
    assert answer["status"] == "degraded", answer
    assert answer[key] == (1 if key == "alt_ban_build" else geo_region.file_word()), answer[key]
    answer.pop(key)
    with pytest.raises(pydantic.ValidationError):
        schemas.HealthResponse(**answer)


def test_the_region_folder_is_mounted_read_only_into_the_api_alone():
    with open(COMPOSE, encoding="utf-8") as fh:
        compose = fh.read()
    api = compose[compose.index("\n  api:\n"):compose.index("\n  bot:\n")]
    assert api.count(MOUNT) == 1, "the api service does not mount the region folder exactly once"
    assert compose.count("/app/private/geo") == 1, "another service mounts the region folder"
    assert api.index(RANGES) < api.index(MOUNT), "the region folder's mount is not after the range list's"
    assert geo_region._rgn_DIR == "/app/private/geo"
