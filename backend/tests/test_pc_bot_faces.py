"""Player Cards faces on Discord (v22 §6, r18 H1/H2), pinned on the bot's
source like test_player_cards_bot: the bot builds itself at import time."""
import asyncio
import io
import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

BOT_SRC = (Path(__file__).resolve().parents[1] / "discord_bot.py").read_text(encoding="utf-8")


def _fn(src, name):
    m = re.search(rf"^(?:async )?def {re.escape(name)}\(.*?(?=^(?:async def |def |@|# ──)|\Z)", src, re.S | re.M)
    assert m, name
    return m.group(0)


def _load(names, **globs):
    """Execute these bot functions in a namespace of stubs, and return it.

    discord_bot cannot be imported — it builds a client at import time — which
    is why this file pins source text elsewhere. Source text is a weak subject:
    it passes over any rewrite that keeps the literal, fails over any that does
    not, and can say nothing about what the function DOES. The functions whose
    defects were about behaviour are run instead."""
    ns = {"time": time, "asyncio": asyncio, "io": io, "print": lambda *a, **k: None}
    ns.update(globs)
    for n in names:
        exec(compile(_fn(BOT_SRC, n), "<discord_bot>", "exec"), ns)
    return ns


class _Content:
    """A response body delivered in buffers, like a real socket."""

    def __init__(self, chunks):
        self.buf = list(chunks)

    async def readexactly(self, n):
        out = b""
        while len(out) < n:
            if not self.buf:
                raise asyncio.IncompleteReadError(out, n)
            take = self.buf.pop(0)
            out += take
        if len(out) > n:
            self.buf.insert(0, out[n:])
            out = out[:n]
        return out

    async def read(self, n=-1):
        if not self.buf:
            return b""
        take = self.buf.pop(0)
        if n >= 0 and len(take) > n:
            self.buf.insert(0, take[n:])
            take = take[:n]
        return take


class _Resp:
    def __init__(self, chunks, declared=None, status=200):
        body = b"".join(chunks)
        self.status = status
        self.headers = {} if declared is False else {
            "Content-Length": str(len(body) if declared is None else declared)}
        self.content = _Content(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _bytes_ns(resp, cap=4 * 1024 * 1024):
    return _load(["_pc_api_bytes"],
                 http_session=SimpleNamespace(get=lambda *a, **k: resp),
                 aiohttp=SimpleNamespace(ClientTimeout=lambda **k: None),
                 API_BASE_URL="http://api", _PC_FACE_MAX_BYTES=cap)


def test_the_byte_route_reader_takes_a_body_that_arrives_in_several_buffers():
    """The case the one-shot read lost: every face over a few kilobytes."""
    chunks = [b"\x89PNG" + bytes(900), bytes(900), bytes(1000)]
    ns = _bytes_ns(_Resp(chunks))
    status, data = asyncio.run(ns["_pc_api_bytes"]("/internal/pc/face/back"))
    assert status == 200 and data is not None and len(data) == 2804


@pytest.mark.parametrize("chunks,declared,cap,expect", [
    ([bytes(50)], 60, None, None),                    # shorter than declared
    ([bytes(70)], 60, None, None),                    # longer than declared
    ([bytes(50)], False, None, None),                 # no Content-Length at all
    ([bytes(50)], 0, None, None),                     # a zero-length body
    ([bytes(50)], None, 10, None),                    # over the cap
    ([bytes(50)], None, None, 50),                    # exact
])
def test_the_byte_route_reader_requires_an_exact_length_under_the_cap(chunks, declared, cap, expect):
    ns = _bytes_ns(_Resp(chunks, declared=declared), cap=cap or 4 * 1024 * 1024)
    _, data = asyncio.run(ns["_pc_api_bytes"]("/internal/pc/face/back"))
    assert (data if data is None else len(data)) == expect
    assert "_PC_FACE_MAX_BYTES = 4 * 1024 * 1024" in BOT_SRC


def _send_ns(live=True, sender=None, sent=None):
    async def _live(lease_id):
        return live

    async def _release(lease_id):
        (sent if sent is not None else []).append(("release", lease_id))

    ns = _load(["_pc_lease_left", "_pc_send_face"],
               discord=SimpleNamespace(File=lambda b, filename=None: ("FILE", filename)),
               _pc_lease_live=_live, _pc_lease_release=_release)
    return ns


def _run_send(ns, deadline, face=b"png", lease_id="L"):
    seen = {}

    async def sender(**kwargs):
        seen.update(kwargs)
    asyncio.run(ns["_pc_send_face"](sender, content="hi", face=face, lease=(lease_id, deadline)))
    return seen


def test_a_send_whose_lease_has_already_run_out_carries_no_picture():
    """An expired deadline is not a short send. Flooring it to a second is how
    a withdrawn picture arrives after the write that withdrew it."""
    assert "file" not in _run_send(_send_ns(), deadline=time.monotonic() - 0.01)
    assert "file" not in _run_send(_send_ns(), deadline=time.monotonic() - 30.0)
    assert "file" in _run_send(_send_ns(), deadline=time.monotonic() + 30.0)


def test_a_send_whose_lease_is_gone_carries_no_picture_and_still_sends_the_text():
    seen = _run_send(_send_ns(live=False), deadline=time.monotonic() + 30.0)
    assert "file" not in seen and seen.get("content") == "hi"


def test_every_portrait_send_releases_its_lease_even_when_the_send_raises():
    released = []
    ns = _send_ns(sent=released)

    async def boom(**kwargs):
        raise RuntimeError("discord said no")
    with pytest.raises(RuntimeError):
        asyncio.run(ns["_pc_send_face"](boom, content="hi", face=b"png",
                                        lease=("L", time.monotonic() + 30.0)))
    assert released == [("release", "L")]


def _section():
    start = BOT_SRC.index("_PC_RARITY_EMOJI = ")
    drain = _fn(BOT_SRC, "poll_pc_events")
    return BOT_SRC[start:BOT_SRC.index(drain) + len(drain)]


def test_the_bot_draws_no_avatar_and_no_thumbnail_anywhere_in_player_cards():
    sec = _section()
    for needle in ("set_thumbnail(", "display_avatar", "avatar_url", "set_author(", "cdn.discordapp", "steamstatic"):
        assert needle not in sec, needle
    assert sec.count("set_image(url=f\"attachment://") + sec.count("set_image(url=\"attachment://") >= 2


def test_every_portrait_send_revalidates_its_lease_right_before_the_send_and_releases_it_after():
    src = _fn(BOT_SRC, "_pc_send_face")
    assert src.index("await _pc_lease_live(lease_id)") < src.index("await asyncio.wait_for(sender(**kwargs)")
    # released after the send (the finally) -- and on the refusal path of a
    # required lease, before the send that then does not happen (r6 H1/M2)
    assert "finally:" in src and src.index("finally:") < src.rindex("await _pc_lease_release(lease_id)")
    assert src.index("if require_lease and not live:") < src.index("await _pc_lease_release(lease_id)") < src.index("return False")
    # the bytes ride only under a lease that is LIVE at the api right before the send
    assert "live = await _pc_lease_live(lease_id) and _pc_lease_left(deadline) > 0" in src
    assert "attach = face is not None and live" in src


def test_the_lease_deadline_keeps_the_reserve_and_a_failed_acquire_means_no_picture():
    src = _fn(BOT_SRC, "_pc_lease")
    assert "left - _PC_LEASE_RESERVE_S" in src and "_PC_LEASE_RESERVE_S = 3.0" in BOT_SRC
    assert 'st != 200 or not isinstance(body, dict) or not body.get("lease_id")' in src
    assert src.count("return None, None") >= 2


def _best_ns(lease=("L", 1e18, False), status=200, face=b"png", released=None):
    async def _lease(subject_ref, print_id=None, event_ids=None):
        (released if released is not None else []).append(("lease", subject_ref, print_id))
        return lease

    async def _bytes(path, params=None, timeout=10.0):
        (released if released is not None else []).append(("bytes", path))
        return status, (face if status == 200 else None)

    async def _release(lease_id):
        (released if released is not None else []).append(("release", lease_id))

    return _load(["_pc_best_face"], _pc_lease=_lease, _pc_api_bytes=_bytes, _pc_lease_release=_release)


def _binder(subject="SUB", print_id="PR"):
    return {"best": [{"print_id": print_id, "subject_player_id": subject}]}


def test_the_binder_picture_is_leased_from_the_player_in_it_not_the_binders_owner():
    """A binder is mostly other people's cards. Leasing its owner puts their
    ban state, their opt-out and their portrait in place of the subject's."""
    log = []
    ns = _best_ns(released=log)
    face, lease = asyncio.run(ns["_pc_best_face"]({"owner_ref": "OWNER", **_binder()}, "en"))
    assert face == b"png" and lease[0] == "L"
    assert ("lease", "SUB", "PR") in log and not any(x[1] == "OWNER" for x in log if x[0] == "lease")
    assert ("bytes", "/internal/pc/face/print/PR/en") in log


def test_the_binder_picture_releases_its_lease_when_the_face_is_gone():
    log = []
    ns = _best_ns(status=404, released=log)
    face, lease = asyncio.run(ns["_pc_best_face"](_binder(), "en"))
    assert face is None and lease == (None, None)
    assert ("release", "L") in log          # a lease taken and not used is given back


def test_the_binder_picture_needs_both_the_print_and_the_player_in_it():
    for body in ({}, {"best": []}, {"best": [{"print_id": "PR"}]},
                 {"best": [{"subject_player_id": "SUB"}]}):
        log = []
        ns = _best_ns(released=log)
        assert asyncio.run(ns["_pc_best_face"](body, "en")) == (None, (None, None))
        assert log == []                   # no lease asked for at all


def test_collection_and_card_lease_the_subject_and_release_on_the_text_only_path():
    coll = _fn(BOT_SRC, "cmd_pc_collection")
    # the binder LIST is re-read with the picture, not just the picture: the
    # stale thing after a discard is the list that named the print
    assert "for attempt in (0, 1):" in coll and coll.count("_pc_best_face(body, locale)") == 1
    assert coll.index("_pc_api(\"GET\", \"/internal/pc/collection\"") < coll.index("_pc_best_face(body, locale)")
    assert coll.index("await _pc_lease_release(lease[0])") < coll.index("await _pc_send_face(ctx.send")
    card = _fn(BOT_SRC, "cmd_pc_card")
    assert "_pc_lease(ref)" in card and "_pc_locale_of(ctx)" in card
    # /card has NO text-only path since r6 (H1/M2): no lease, no card -- a
    # refusal before the send, and the send itself requires the lease
    assert card.index("if not lease[0]:") < card.index("await _pc_send_face(ctx.send")
    # three refusals say the same thing: no usable snapshot pin (r8 L5), no lease, the send failed
    assert "require_lease=True" in card and card.count("That card isn't available right now") == 3
    assert "await _pc_lease_release(lease[0])" not in card


def test_the_drain_waits_a_bounded_number_of_ticks_for_a_transient_picture():
    """"Busy for two seconds" is not "has no picture" — but an api that stays
    busy must not mean the pull is never announced, so the wait is capped and
    the line then posts without one."""
    src = _fn(BOT_SRC, "poll_pc_events")
    assert "_pc_face_tries.get(ids[0], 0) < _PC_FACE_TRIES" in src
    assert "_pc_face_tries.pop(ids[0], None)" in src          # cleared on the way out
    assert "_PC_FACE_TRIES = 3" in BOT_SRC and "_pc_face_tries = {}" in BOT_SRC
    assert "_pc_face_tries.clear()" in BOT_SRC                # bounded memory
    # the retry happens BEFORE the send and before the events are recorded
    assert src.index("_pc_face_tries.get(ids[0], 0)") < src.index("await _pc_send_face(ch.send")
    assert src.index("_pc_face_tries.get(ids[0], 0)") < src.index("_pc_events_sent[i] = True")
    # ...and only for a refusal that can pass: 404 and 422 are answers
    lease = _fn(BOT_SRC, "_pc_lease")
    assert "(st == 409 or st == 0 or st >= 500)" in lease


def test_the_drain_leases_each_print_group_with_its_events_and_acks_with_the_leases():
    src = _fn(BOT_SRC, "poll_pc_events")
    assert '_pc_lease(first["subject_ref"], print_id=p.get("print_id"), event_ids=ids)' in src   # every group, print or not (r6 H1)
    assert src.index("await _pc_send_face(ch.send") < src.index('"/internal/pc/events/ack"')
    assert '"leases": ",".join(leases)' in src
    assert "leases.append(lease[0])" in src


def test_the_daily_answer_carries_the_canonical_back_without_a_lease():
    src = _fn(BOT_SRC, "cmd_pc_daily")
    assert "await _pc_back_bytes()" in src and "_pc_lease(" not in src
    back = _fn(BOT_SRC, "_pc_back_bytes")
    assert '_pc_api_bytes("/internal/pc/face/back")' in back and "3600" in back


def test_the_locale_is_the_interaction_primary_subtag():
    src = BOT_SRC[BOT_SRC.index("def _pc_locale_of(ctx):"):BOT_SRC.index("async def _pc_api_bytes")]
    assert 'split("-")[0].lower()' in src and 'return primary or "en"' in src


def _card_ns(lease, preview_status=404, body=None):
    calls = {"api": [], "bytes": [], "sent": [], "said": [], "lease": []}

    async def _api(method, path, params=None, timeout=8.0, payload=None):
        calls["api"].append((method, path, params))
        return 200, body if body is not None else {"player_ref": "11111111-1111-4111-8111-111111111111", "subject_name": "Ace", "rarity": "rare",
                     "pool_rank": 3, "rating": 1500, "peak_rating": 1600, "board_rank": 7, "snapshot_id": 41,
                     "in_circulation": {"prints": 2, "holders": 2, "foil": 0, "signed": 0}}

    async def _bytes(path, params=None, timeout=10.0):
        calls["bytes"].append((path, params))
        return preview_status, (b"png" if preview_status == 200 else None)

    async def _lease(ref, print_id=None, event_ids=None):
        calls["lease"].append(ref)
        return lease

    async def _send(sender, content=None, embed=None, face=None, lease=(None, None), filename="card.png", require_lease=False):
        calls["sent"].append((embed is not None, face, lease[0], require_lease))
        return True

    async def _defer(ctx):
        pass

    class _Embed:
        def __init__(self, **kw):
            self.kw, self.fields = kw, []

        def add_field(self, **kw):
            self.fields.append(kw)

        def set_footer(self, **kw):
            pass

    ns = _load(["cmd_pc_card"],
               discord=SimpleNamespace(Member=object, Embed=_Embed, utils=SimpleNamespace(escape_markdown=lambda s: s)),
               _pc_api=_api, _pc_api_bytes=_bytes, _pc_lease=_lease, _pc_send_face=_send, _maybe_defer=_defer,
               _pc_detail=lambda body: body if isinstance(body, dict) else {}, _pc_not_linked=lambda ctx, t: "not linked",
               _pc_name=lambda s: s, _PC_RARITY_EMOJI={}, _PC_RARITY_COLOR={}, get_rank_name=lambda r: "Gold",
               rank_emoji=lambda n: "", _pc_locale_of=lambda ctx: "en")
    ns["calls"] = calls
    return ns


def _run_card(ns):
    async def _say(*a, **k):
        ns["calls"]["said"].append(a[0] if a else k.get("content"))
    ctx = SimpleNamespace(author=SimpleNamespace(id=1, display_name="Me"), send=_say)
    asyncio.run(ns["cmd_pc_card"](ctx, None))
    return ns["calls"]


def test_the_card_command_draws_its_preview_from_the_embeds_snapshot_and_posts_only_under_a_lease():
    """r7 L1 (2026-09-13), executed: the preview request carries the snapshot id the embed was read
    from; a preview that 404s still posts the embed under the lease, without a picture; no lease
    posts nothing and says so."""
    calls = _run_card(_card_ns(lease=("L1", time.monotonic() + 30, False)))
    assert calls["bytes"] == [("/internal/pc/face/preview/11111111-1111-4111-8111-111111111111/en", {"snapshot_id": 41})]
    assert calls["sent"] == [(True, None, "L1", True)] and calls["said"] == []
    calls = _run_card(_card_ns(lease=("L2", time.monotonic() + 30, False), preview_status=200))
    assert calls["sent"] == [(True, b"png", "L2", True)]
    calls = _run_card(_card_ns(lease=(None, None, True)))
    assert calls["bytes"] == [] and calls["sent"] == [] and len(calls["said"]) == 1 and "isn't available" in calls["said"][0]


def test_the_card_command_posts_nothing_without_a_usable_snapshot_pin_or_subject_reference():
    """r8 L5 + r9 L5 (2026-09-13), executed: a body without `snapshot_id` (an older api during a rolling
    deploy), or with one that is not a positive integer, posts nothing and says so -- never one
    snapshot's text with another's face; a body without a usable `player_ref` (None, empty, not a
    string, absent) posts nothing either: there is no text-only card; neither takes a lease for it;
    a pinned body with its reference posts as before."""
    base = {"player_ref": "11111111-1111-4111-8111-111111111111", "subject_name": "Ace", "rarity": "rare",
            "pool_rank": 3, "rating": 1500, "peak_rating": 1600, "board_rank": 7,
            "in_circulation": {"prints": 2, "holders": 2, "foil": 0, "signed": 0}}
    refused = [{}, {"snapshot_id": None}, {"snapshot_id": "41"}, {"snapshot_id": 0}, {"snapshot_id": True},
               {"snapshot_id": 41, "player_ref": None}, {"snapshot_id": 41, "player_ref": ""}, {"snapshot_id": 41, "player_ref": 7}]
    no_ref = dict(base, snapshot_id=41)
    del no_ref["player_ref"]
    for body in [dict(base, **over) for over in refused] + [no_ref]:
        calls = _run_card(_card_ns(lease=("L1", time.monotonic() + 30, False), preview_status=200, body=body))
        assert calls["lease"] == [] and calls["bytes"] == [] and calls["sent"] == [], body
        assert len(calls["said"]) == 1 and "isn't available" in calls["said"][0], body
    calls = _run_card(_card_ns(lease=("L1", time.monotonic() + 30, False), preview_status=200, body=dict(base, snapshot_id=41)))
    assert calls["lease"] == ["11111111-1111-4111-8111-111111111111"] and calls["sent"] == [(True, b"png", "L1", True)]
    assert calls["bytes"] == [("/internal/pc/face/preview/11111111-1111-4111-8111-111111111111/en", {"snapshot_id": 41})]


def test_every_line_the_bot_prints_is_one_line():
    """r9 L8 (2026-09-13), executed: the bot's print flattens CR and LF out of every argument, so a
    relayed message or a display name carrying line breaks prints as ONE log line -- no text a user
    typed can occupy a line of its own and read as a lifecycle marker to the deploy train, whose
    markers are whole lines; installed before the imports, ahead of every other print, and the only
    marker prints are the fallback boot line and on_ready's."""
    m = re.search(r"^def _one_line_print\(.*?\n(?=\n)", BOT_SRC, re.S | re.M)
    assert m, "the flattener"
    out = []
    ns = {"_gen_builtins": SimpleNamespace(print=lambda *a, **k: out.append((a, k)))}
    exec(compile(m.group(0), "<discord_bot>", "exec"), ns)
    ns["_one_line_print"]("[CHAT] Discord msg from x: hi\n[BOT-BOOT] gen=deadbeefcafe\r\nmore", 7, flush=True)
    assert out == [(("[CHAT] Discord msg from x: hi [BOT-BOOT] gen=deadbeefcafe  more", "7"), {"flush": True})]
    assert BOT_SRC.index("print = _one_line_print") < BOT_SRC.index("import os, asyncio, aiohttp, discord")
    assert BOT_SRC.count('print("[BOT-BOOT]') == 1 and BOT_SRC.count('print("[BOT-READY]') == 1
