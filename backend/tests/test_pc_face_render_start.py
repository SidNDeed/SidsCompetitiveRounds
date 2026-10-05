"""The face cache's render-start signal (Discord card render parity, LOW 2).

Residual 2 claims a face is rendered at most once per key per box while the
key stays resident in that box's cache (the cold cache after the deploy is
the one transient). Its falsifier needs a count of render STARTS per key per
box, which a 5xx detector cannot give; so the cache calls `on_render_start`
once per render it starts -- never for a hit, never for a waiter joining an
in-flight render -- and the api logs `[PC-FACE] render start k=<12 hex>`,
a hash of the key, so no print id reaches the log.
"""
import asyncio
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import pc_portrait as P  # noqa: E402


def _cache(tmp_path):
    cache = P.FaceCache(str(tmp_path / "faces"))
    starts = []
    cache.on_render_start = starts.append
    return cache, starts


KEY = "0123456789abcdef0123456789abcdef/aaaaaaaaaaaaaaaa/en/card"


def test_one_start_per_render_and_none_for_a_hit(tmp_path):
    cache, starts = _cache(tmp_path)
    assert asyncio.run(cache.get_or_render(KEY, lambda: b"\x89PNGone")) == b"\x89PNGone"
    assert starts == [KEY]
    assert asyncio.run(cache.get_or_render(KEY, lambda: b"\x89PNGtwo")) == b"\x89PNGone"
    assert starts == [KEY]                                       # resident: a hit starts nothing


def test_concurrent_waiters_share_one_start(tmp_path):
    cache, starts = _cache(tmp_path)

    async def go():
        import time

        def slow():
            time.sleep(0.2)
            return b"\x89PNGslow"
        return await asyncio.gather(*[cache.get_or_render(KEY, slow) for _ in range(5)])
    assert asyncio.run(go()) == [b"\x89PNGslow"] * 5
    assert starts == [KEY]


def test_a_failing_hook_never_fails_the_render(tmp_path):
    cache = P.FaceCache(str(tmp_path / "faces"))

    def boom(_key):
        raise RuntimeError("log sink gone")
    cache.on_render_start = boom
    assert asyncio.run(cache.get_or_render(KEY, lambda: b"\x89PNG")) == b"\x89PNG"


def test_the_api_cache_logs_a_hash_of_the_key_never_the_key(capsys):
    import main
    assert main._pc_face_cache.on_render_start is main._pc_face_render_started
    main._pc_face_render_started(KEY)
    out = capsys.readouterr().out.strip()
    assert re.fullmatch(r"\[PC-FACE\] render start k=[0-9a-f]{12}", out), out
    assert out.endswith(hashlib.sha256(KEY.encode("utf-8")).hexdigest()[:12])
    assert "0123456789abcdef" not in out
