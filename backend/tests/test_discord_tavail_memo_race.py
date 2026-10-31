"""The availability prompt's withdrawal memo is ordered against the notice
poll's reset (FENCE-LAND-R6 H8).

`_tavail_withdrawn` has two writers: the No's add (on_interaction, after a
withdrawal that went through) and the poll's reset (a fresh prompt starts a
fresh decision). The poll's pre-send live check and its reset now run in
`_tavail_live_and_reset` under the prompt's lock in `_tavail_locks`, the
lock on_interaction holds across its withdrawal and memo add. Invariant: for
one bot process and one prompt key, a memo set by a successful No is never
cleared by a poll whose live check began before that No's withdrawal
returned.

Driven through the lifted on_interaction and _tavail_live_and_reset over the
harness's fake transport, with the server's live check stubbed and held on
an asyncio event so the interleaving is deterministic:

  * the poll's live check starts (the player is still signed up), a No is
    clicked while the check is held, the check is released, then a Yes is
    clicked: the Yes reply is the already-withdrawn text;
  * the same run over a copy of the helper without the lock replies
    "Confirmed" (the control fails on the unfixed ordering);
  * a No that completed before the poll, with the player signed up again,
    is still reset by the poll (a fresh prompt, fence r4 find 4);
  * a live check that answers False or no answer leaves the memo;
  * the poll reaches the memo only through the helper.
"""
import ast
from types import SimpleNamespace

import discord_collection_harness as H

DID = 912345678901234567              # synthetic 18-digit Discord id
TID = "6f1c2d3e-0000-4000-8000-000000000002"
STEAM = H.steam_of(8)                 # synthetic, not an individual SteamID64
NID = "notice-0001"
KEY = "%s:%s" % (TID, STEAM)
FUNCS = {"on_interaction", "_tdlc_verify_clicker", "_tournament_unsignup",
         "_discord_tail", "_scrub_discord_id", "_tavail_live_and_reset"}
ASSIGNS = {"_tavail_locks", "_tavail_withdrawn"}
WITHDRAWN = "You've already withdrawn from this tournament"
CONFIRMED = "Confirmed"
LOCK_LINE = "async with _tavail_locks.setdefault(key, asyncio.Lock()):"


class _User:
    def __init__(self, uid, name):
        self.id, self.name = uid, name

    def __str__(self):
        return self.name


class _Live:
    """The server's pre-send live check, held until released."""

    def __init__(self, answer, hold):
        self.answer, self.hold = answer, hold
        self.started = None
        self.release = None
        self.calls = []

    async def __call__(self, nid):
        self.calls.append(nid)
        if self.hold:
            self.started.set()
            await self.release.wait()
        return self.answer


async def _server(call):
    if call.path.startswith("/players/by-discord/"):
        return H.Reply(200, json={"steam_id": STEAM})
    if call.path == "/tournaments/%s/unsignup" % TID:
        return H.Reply(200, json={})
    raise AssertionError("unexpected request: %s %s" % (call.method, call.path))


def _rig(live, source=None):
    fake_discord = SimpleNamespace(
        Interaction=object,
        InteractionType=SimpleNamespace(component="component"),
        AllowedMentions=SimpleNamespace(none=lambda: "none"))
    return H.BotRig(_server, funcs=FUNCS, assigns=ASSIGNS, source=source,
                    extra={"discord": fake_discord, "_tavail_still_live": live})


async def _click(rig, answer):
    sent = []

    async def defer(**kw):
        return None

    async def send(content=None, *a, **kw):
        sent.append(content)

    async def edit(**kw):
        sent.append(kw.get("content"))

    interaction = SimpleNamespace(
        type="component", data={"custom_id": "tavail:%s:%s:%s" % (TID, STEAM, answer)},
        user=_User(DID, "entrant8"),
        response=SimpleNamespace(defer=defer), followup=SimpleNamespace(send=send),
        message=SimpleNamespace(edit=edit))
    await rig.ns["on_interaction"](interaction)
    return sent


def _unsignups(rig):
    return [c for c in rig.calls if c.path == "/tournaments/%s/unsignup" % TID]


async def _race(rig, live):
    """Poll check starts -> No clicked while the check is held -> check
    released and the poll finishes -> Yes clicked. Returns the Yes reply."""
    import asyncio
    live.started, live.release = asyncio.Event(), asyncio.Event()
    poll = asyncio.ensure_future(rig.ns["_tavail_live_and_reset"](NID, TID, STEAM))
    await live.started.wait()
    no = asyncio.ensure_future(_click(rig, "no"))
    for _ in range(200):                # let the No run as far as it can
        if no.done():
            break
        await asyncio.sleep(0)
    no_done_while_held = no.done()
    live.release.set()
    assert await poll is True
    no_sent = await no
    assert no_sent and "removed from the tournament" in no_sent[0], no_sent
    yes_sent = await _click(rig, "yes")
    return no_done_while_held, yes_sent


def test_a_no_inside_the_polls_check_survives_the_reset_and_the_yes_says_withdrawn():
    live = _Live(True, hold=True)
    rig = _rig(live)
    no_done_while_held, yes_sent = H.run(_race(rig, live))
    assert no_done_while_held is False          # the No waited for the poll's critical section
    assert len(_unsignups(rig)) == 1
    assert KEY in rig.ns["_tavail_withdrawn"]
    assert len(yes_sent) == 1 and yes_sent[0].startswith(WITHDRAWN), yes_sent
    assert live.calls == [NID]


def _unlocked_source():
    """discord_bot.py with the helper's lock removed (the pre-fix ordering),
    the change asserted to land once, inside the helper's own span."""
    src = H.bot_source()
    tree = ast.parse(src)
    fns = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_tavail_live_and_reset"]
    assert len(fns) == 1
    seg = ast.get_source_segment(src, fns[0])
    assert seg.count(LOCK_LINE) == 1 and src.count(seg) == 1
    return src.replace(seg, seg.replace(LOCK_LINE, "if True:"))


def test_control_the_same_race_without_the_lock_replies_confirmed():
    live = _Live(True, hold=True)
    rig = _rig(live, source=_unlocked_source())
    no_done_while_held, yes_sent = H.run(_race(rig, live))
    assert no_done_while_held is True           # the No completed inside the poll's check
    assert KEY not in rig.ns["_tavail_withdrawn"]
    assert len(yes_sent) == 1 and yes_sent[0].startswith(CONFIRMED), yes_sent


def test_a_no_before_the_poll_with_the_player_signed_up_again_is_reset():
    async def go(rig):
        no_sent = await _click(rig, "no")
        assert "removed from the tournament" in no_sent[0], no_sent
        assert KEY in rig.ns["_tavail_withdrawn"]
        assert await rig.ns["_tavail_live_and_reset"](NID, TID, STEAM) is True
        return await _click(rig, "yes")
    live = _Live(True, hold=False)
    rig = _rig(live)
    yes_sent = H.run(go(rig))
    assert KEY not in rig.ns["_tavail_withdrawn"]
    assert len(yes_sent) == 1 and yes_sent[0].startswith(CONFIRMED), yes_sent


def test_a_check_that_is_not_live_or_unanswered_leaves_the_memo():
    for answer in (False, None):
        async def go(rig):
            await _click(rig, "no")
            got = await rig.ns["_tavail_live_and_reset"](NID, TID, STEAM)
            return got, await _click(rig, "yes")
        live = _Live(answer, hold=False)
        rig = _rig(live)
        got, yes_sent = H.run(go(rig))
        assert got is answer
        assert KEY in rig.ns["_tavail_withdrawn"]
        assert len(yes_sent) == 1 and yes_sent[0].startswith(WITHDRAWN), (answer, yes_sent)


def _calls_in(fn, name):
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == name]


def test_the_poll_reaches_the_memo_only_through_the_helper():
    tree = ast.parse(H.bot_source())
    fns = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    poll = fns["poll_tournament_notices"]
    assert len(_calls_in(poll, "_tavail_live_and_reset")) == 1
    assert _calls_in(poll, "_tavail_still_live") == []
    assert [n for n in ast.walk(poll) if isinstance(n, ast.Name) and n.id == "_tavail_withdrawn"] == []
    # The memo's writers, file-wide: the helper's reset and on_interaction's add.
    writers = sorted(
        (f.name, n.func.attr) for f in fns.values() for n in ast.walk(f)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "_tavail_withdrawn")
    assert writers == [("_tavail_live_and_reset", "discard"), ("on_interaction", "add")], writers
