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
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.normpath(os.path.join(HERE, "..", "api"))
if API not in sys.path:
    sys.path.insert(0, API)

import pydantic  # noqa: E402
import pytest  # noqa: E402

import geo_region  # noqa: E402
import main  # noqa: E402
import mmdb_standin as S  # noqa: E402
import schemas  # noqa: E402

V4 = "1.1.1.1"           # the lane's tests' resolver address; Ardenmark in the stand-in

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


def test_both_arms_await_the_one_bounded_reader_of_the_word():
    """Both arms await the one bounded reader of the word (_ban_region_word:
    the read in a thread of the reads' own pool, at most one in flight, the
    wait cut at _ALT_BAN_WORD_WAIT_S); turn 2 moved it from a bare
    asyncio.to_thread await, which had no time limit (ADD1 point 1)."""
    word = "await _ban_region_word()"
    assert _arms(_main_tree(), "ban_region_file") == ([word], [word], 2)


# -- ADD1 point 1 (H1 to H4, H6): the word's read is bounded at admission and in time --

def _hold_the_word(monkeypatch, answer="2031-04"):
    """file_word held on an event in its thread; every read started is counted."""
    release, started = threading.Event(), []

    def word():
        started.append(1)
        release.wait(20)
        return answer
    monkeypatch.setattr(geo_region, "file_word", word)
    monkeypatch.setattr(main, "_alt_ban_reading", {"word": None, "region": None, "steam": None})
    return release, started


def _drain():
    """Wait, bounded, until the word's read in flight has ended (lesson 1297:
    no test returns while work it started still runs)."""
    held = main._alt_ban_reading["word"]
    if held is not None:
        held.result(timeout=25)


async def _calls(n):
    """n /health calls at once (the degraded arm), each with its own time."""
    async def one():
        t = time.monotonic()
        got = (await main.health_check(db=_DownSession())).model_dump()["ban_region_file"]
        return got, time.monotonic() - t
    return await asyncio.gather(*[one() for _ in range(n)])


async def _word_waits(n):
    """n waits of the word's reader at once (the one both arms await), each with its own time."""
    async def one():
        t = time.monotonic()
        got = await main._ban_region_word()
        return got, time.monotonic() - t
    return await asyncio.gather(*[one() for _ in range(n)])


def test_fifty_calls_at_once_start_one_read_and_each_answers_pending_in_time(monkeypatch):
    """Fifty waits of the word's reader at once (the one both arms await)
    start one read, each answers "pending" and each ends within
    _ALT_BAN_WORD_WAIT_S and a margin; then, with that read still held, fifty
    /health calls at once (the degraded arm) start none and each answers
    "pending". The time is taken on the reader's own
    await, not on the whole /health call: a call's whole time also holds the
    other words' synchronous work, which runs on the event loop, so fifty
    calls at once run it one after another (about 15 ms a call on the VM with
    the renderer's fonts placed, three quarters of it pc_card_art's renderer
    fingerprint, computed again at each call) and the last of fifty whole calls can end past the word's
    limit while every wait for the word is cut at it (ALT-BAN-1 fix 3, F3-C)."""
    release, started = _hold_the_word(monkeypatch)
    # Without the limit a wait lasts as long as the hold: the hold ends after
    # 5 s (past both phases' time with a margin), so such a run answers late
    # (red) and never hangs.
    timer = threading.Timer(5.0, release.set)
    timer.start()
    try:
        waits = asyncio.run(_word_waits(50))
        count = len(started)
        got = asyncio.run(_calls(50))
        count_after_calls = len(started)
    finally:
        release.set()
        timer.cancel()
        _drain()
    slowest = max(t for _w, t in waits)
    assert slowest < main._ALT_BAN_WORD_WAIT_S + 0.5, "a call waited %.2f s for the word" % slowest
    assert count == 1, "one read was to be started for 50 calls, %d were" % count
    assert count_after_calls == 1, "a /health call started a read while one was in flight (%d)" % count_after_calls
    words = {w for w, _t in waits} | {w for w, _t in got}
    assert words == {main._BAN_REGION_WORD_PENDING}, words
    # After the release the next call reads again and answers the file's state.
    after = asyncio.run(_calls(1))[0][0]
    _drain()
    assert after == "2031-04" and len(started) == 2, (after, len(started))


def test_the_pending_word_is_one_no_state_of_the_file_produces():
    assert main._BAN_REGION_WORD_PENDING == "pending"
    assert re.fullmatch(r"absent|refused|[0-9]{4}-[0-9]{2}", main._BAN_REGION_WORD_PENDING) is None


def test_a_file_switched_in_by_a_rename_is_named_at_the_next_call(monkeypatch, tmp_path):
    """H4: storage that answers at once gives the file's state AT the call,
    also for calls that arrive together: no age window."""
    monkeypatch.setattr(main, "_alt_ban_reading", {"word": None, "region": None, "steam": None})
    monkeypatch.setattr(geo_region, "_rgn_DIR", str(tmp_path))
    monkeypatch.setattr(geo_region, "_rgn_kept", None)
    assert {w for w, _t in asyncio.run(_calls(5))} == {"absent"}
    jan, mar = 1798761600, 1803859200          # 2027-01-01 and 2027-03-01, UTC
    for name, epoch in (("a.mmdb", jan), ("b.mmdb", mar)):
        (tmp_path / name).write_bytes(S.build([(V4, S.place("Ardenmark"))], build_epoch=epoch).data)
    os.replace(tmp_path / "a.mmdb", tmp_path / "region.mmdb")
    assert {w for w, _t in asyncio.run(_calls(5))} == {"2027-01"}
    os.replace(tmp_path / "b.mmdb", tmp_path / "region.mmdb")
    assert {w for w, _t in asyncio.run(_calls(5))} == {"2027-03"}
    _drain()


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
