"""The availability prompt's withdrawal memo is reset only by a prompt that
was sent, and only when the No that set it returned before the poll's live
check began (FENCE-LAND-R6 H8; integrator ruling FENCE-H8.1, method c).

`_tavail_withdrawn` maps a prompt key to the time.monotonic() stamp of the
No that set it (on_interaction, under the prompt's lock, after the
withdrawal returned). The notice poll reads t0 = time.monotonic() before
its live check, checks, sends, and only after a SUCCESSFUL send calls
`_tavail_reset_memo(tid, steam, t0)`, a plain function whose
compare-and-delete has no await (so it is atomic on the event loop and
takes no lock; ruling FENCE-H8.2): it removes the memo only when its stamp
is strictly earlier than t0. Invariant: for one bot process and one prompt
key, a memo set by a successful No is never cleared by a poll whose live
check began before that No returned; a failed send resets nothing. A Yes
suspended in its identity check while a reset this rule allows runs replies
Confirmed; with a No stamped at or after t0 it replies already-withdrawn.

Driven through the lifted poll_tournament_notices, _tavail_still_live,
_tavail_reset_memo and on_interaction (the start-rule suite's fake api and
fake Discord client, extended with the link lookup and the withdrawal), on
the harness clock, which moves only when this file or a modelled sleep moves
it:

  * a No that lands inside the poll's live check (the check answers from
    before the No) survives the reset, and a later Yes replies the
    already-withdrawn text; so does a No stamped exactly at t0;
  * a send that fails (transient, or DMs closed) resets nothing;
  * a No that returned before the check, with the player signed up again,
    is reset after a successful send and the Yes replies Confirmed;
  * a check that answers not live sends nothing and keeps the memo;
  * a Yes suspended in its identity check does not hold up the poll: a
    reset the rule allows lands meanwhile and the Yes replies Confirmed,
    while the same straddle with a No stamped after t0 replies withdrawn;
  * a No landing at the poll's first yield after the send keeps its memo
    (no await between the reset's compare and its delete);
  * the poll's order (t0, check, send, reset), the reset's atomicity (a
    plain function with no await and no call, no lock) and the memo's
    writers.
"""
import asyncio
import ast
from types import SimpleNamespace

import discord_collection_harness as H
import test_discord_tournament_start_rule as R

N = 7                                  # the harness's synthetic player offset
NID = "a1"
STEAM = H.steam_of(N)
DID = int(H.discord_of(N))
KEY = "%s:%s" % (R.TID, STEAM)
FUNCS = (set(R.FUNCS) | {"on_interaction", "_tdlc_verify_clicker", "_tournament_unsignup",
                         "_discord_tail", "_scrub_discord_id"})
WITHDRAWN = "You've already withdrawn from this tournament"
CONFIRMED = "Confirmed"
ASKED = "Are you still in for the **Async tournament**?"


class Api(R.Api):
    """The start-rule api plus the link lookup and the withdrawal. The
    pre-send read answers from the server state at the moment it is
    received; `during_check` runs after that answer is fixed and before it
    is returned, i.e. inside the poll's live check."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.signed_out = set()           # steam ids withdrawn and not signed up again
        self.during_check = None
        self.verify_gate = None           # an asyncio.Event: identity checks wait on it while set here
        self.verify_waiting = 0

    async def __call__(self, call):
        if call.path.startswith("/players/by-discord/"):
            if self.verify_gate is not None:
                gate = self.verify_gate
                self.verify_waiting += 1
                await gate.wait()
            return H.Reply(200, json={"steam_id": STEAM})
        if call.method == "POST" and call.path == "/tournaments/%s/unsignup" % R.TID:
            self.signed_out.add(call.payload["steam_id"])
            return H.Reply(200, json={})
        if call.method == "GET" and "notice_id=" in call.path:
            saved = self.notices
            self.notices = [n for n in saved if n["steam_id"] not in self.signed_out]
            try:
                reply = await super().__call__(call)
            finally:
                self.notices = saved
            if self.during_check is not None:
                hook, self.during_check = self.during_check, None
                await hook()
            return reply
        return await super().__call__(call)


class Client(R.Client):
    def __init__(self, fail=None):
        super().__init__()
        self.fail = fail

    def get_user(self, uid):
        user = super().get_user(uid)
        if self.fail is not None:
            fail = self.fail

            async def send(**kw):
                raise fail
            user.send = send
        return user


class _User:
    def __init__(self, uid, name):
        self.id, self.name = uid, name

    def __str__(self):
        return self.name


def _rig(fail=None):
    api = Api(notices=[R.notice(NID, N, kind="async")])
    client = Client(fail)
    fake_discord = SimpleNamespace(Embed=R.Embed, NotFound=R.NotFound, Forbidden=R.Forbidden,
                                   HTTPException=Exception, Interaction=object,
                                   InteractionType=SimpleNamespace(component="component"),
                                   AllowedMentions=SimpleNamespace(none=lambda: "none"))
    extra = {"discord": fake_discord, "bot": client, "urllib": R.urllib,
             "TOURNAMENT_CHANNEL_ID": R.ANNOUNCE, "SCR_TOURNAMENTS_CHANNEL": R.BOARD,
             "_tavail_view": lambda tid, steam: ("view", str(tid), str(steam))}
    rig = H.BotRig(api, funcs=FUNCS, assigns=R.ASSIGNS, extra=extra)
    rig.api, rig.client = api, client
    return rig


async def _click(rig, answer):
    sent = []

    async def defer(**kw):
        return None

    async def send(content=None, *a, **kw):
        sent.append(content)

    async def edit(**kw):
        sent.append(kw.get("content"))

    interaction = SimpleNamespace(
        type="component", data={"custom_id": "tavail:%s:%s:%s" % (R.TID, STEAM, answer)},
        user=_User(DID, "entrant7"),
        response=SimpleNamespace(defer=defer), followup=SimpleNamespace(send=send),
        message=SimpleNamespace(edit=edit))
    await rig.ns["on_interaction"](interaction)
    return sent


def _no(rig):
    sent = H.run(_click(rig, "no"))
    assert sent and "removed from the tournament" in sent[0], (sent, rig.logs)


def _yes(rig):
    sent = H.run(_click(rig, "yes"))
    assert len(sent) == 1, sent
    return sent[0]


def _no_inside_the_check(rig, before, after):
    """Inside the poll's live check (its answer already fixed from before
    the No): the clock moves `before`, the No runs to completion, the clock
    moves `after`."""
    async def hook():
        rig.clock.advance(before)
        sent = await _click(rig, "no")
        assert sent and "removed from the tournament" in sent[0], (sent, rig.logs)
        rig.clock.advance(after)
    rig.api.during_check = hook


def test_a_no_inside_the_live_check_survives_the_reset_and_the_yes_says_withdrawn():
    rig = _rig()
    _no_inside_the_check(rig, 1.0, 1.0)
    H.run(rig.ns["poll_tournament_notices"]())
    assert [d.content for d in rig.client.dms] == [ASKED]     # the check answered live: the prompt went out
    assert rig.api.acked == [NID] and rig.api.rechecks == [NID]
    assert KEY in rig.ns["_tavail_withdrawn"]
    assert _yes(rig).startswith(WITHDRAWN)


def test_a_no_stamped_exactly_at_t0_is_kept():
    rig = _rig()
    _no_inside_the_check(rig, 0.0, 0.0)                     # the clock does not move: stamp == t0
    H.run(rig.ns["poll_tournament_notices"]())
    assert rig.api.acked == [NID]
    assert KEY in rig.ns["_tavail_withdrawn"]
    assert _yes(rig).startswith(WITHDRAWN)


def _no_then_signed_up_again(rig):
    _no(rig)
    stamp = rig.ns["_tavail_withdrawn"][KEY]
    rig.clock.advance(5.0)
    rig.api.signed_out.discard(STEAM)                      # the player signed up again
    return stamp


def test_a_failed_send_resets_nothing():
    for fail, acked in ((RuntimeError("429 Too Many Requests"), []), (R.Forbidden("DMs closed"), [NID])):
        rig = _rig(fail)
        stamp = _no_then_signed_up_again(rig)
        H.run(rig.ns["poll_tournament_notices"]())
        assert rig.api.rechecks == [NID] and rig.client.dms == []
        assert rig.api.acked == acked, (fail, rig.api.acked)
        assert rig.ns["_tavail_withdrawn"].get(KEY) == stamp, fail
        assert _yes(rig).startswith(WITHDRAWN), fail


def test_a_no_before_the_check_with_the_player_signed_up_again_is_reset_after_the_send():
    rig = _rig()
    _no_then_signed_up_again(rig)
    H.run(rig.ns["poll_tournament_notices"]())
    assert [d.content for d in rig.client.dms] == [ASKED] and rig.api.acked == [NID]
    assert KEY not in rig.ns["_tavail_withdrawn"]
    assert _yes(rig).startswith(CONFIRMED)


def test_a_check_that_is_not_live_sends_nothing_and_keeps_the_memo():
    rig = _rig()
    _no(rig)
    stamp = rig.ns["_tavail_withdrawn"][KEY]
    rig.clock.advance(5.0)
    H.run(rig.ns["poll_tournament_notices"]())
    assert rig.api.rechecks == [NID] and rig.client.dms == [] and rig.api.acked == []
    assert rig.ns["_tavail_withdrawn"].get(KEY) == stamp
    assert _yes(rig).startswith(WITHDRAWN)


async def _until(pred, limit=200):
    for _ in range(limit):
        if pred():
            return True
        await asyncio.sleep(0)
    return pred()


async def _straddle(rig, late_no):
    """A Yes is suspended in its identity check (holding the prompt's lock)
    while one poll tick runs. late_no: a No lands inside the tick's live
    check (stamped after t0) just before that Yes is clicked. Returns
    (whether the tick finished while the Yes was still suspended, the Yes
    reply)."""
    gate = asyncio.Event()
    box = {}

    def start_yes():
        rig.api.verify_gate = gate
        box["yes"] = asyncio.ensure_future(_click(rig, "yes"))

    if late_no:
        async def hook():
            rig.clock.advance(1.0)
            sent = await _click(rig, "no")
            assert sent and "removed from the tournament" in sent[0], (sent, rig.logs)
            rig.clock.advance(1.0)
            start_yes()
            assert await _until(lambda: rig.api.verify_waiting == 1)
        rig.api.during_check = hook
    else:
        start_yes()
        assert await _until(lambda: rig.api.verify_waiting == 1)
    tick = asyncio.ensure_future(rig.ns["poll_tournament_notices"]())
    tick_done = await _until(tick.done)
    gate.set()
    rig.api.verify_gate = None
    await tick
    sent = await box["yes"]
    assert len(sent) == 1, sent
    return tick_done, sent[0]


def test_a_yes_suspended_in_its_identity_check_straddling_a_reset_the_rule_allows_replies_confirmed():
    rig = _rig()
    _no_then_signed_up_again(rig)               # the No returned before t0; the player signed up again
    tick_done, reply = H.run(_straddle(rig, late_no=False))
    assert tick_done is True                    # the poll did not wait on the suspended Yes
    assert [d.content for d in rig.client.dms] == [ASKED] and rig.api.acked == [NID]
    assert KEY not in rig.ns["_tavail_withdrawn"]
    assert reply.startswith(CONFIRMED), reply


def test_the_same_straddle_with_a_no_stamped_after_t0_replies_withdrawn():
    rig = _rig()
    tick_done, reply = H.run(_straddle(rig, late_no=True))
    assert tick_done is True
    assert [d.content for d in rig.client.dms] == [ASKED] and rig.api.acked == [NID]
    assert KEY in rig.ns["_tavail_withdrawn"]
    assert reply.startswith(WITHDRAWN), reply


def test_a_no_landing_at_the_polls_first_yield_after_the_send_keeps_its_memo():
    """The reset's compare and delete have no await between them: a No that
    lands at the first point the poll yields after its send (here its
    inter-notice sleep) is stamped after the delete, and stands."""
    rig = _rig()
    _no_then_signed_up_again(rig)               # an older stamp, earlier than t0
    fake = rig.ns["asyncio"]
    real_sleep = fake.sleep
    fired = []

    async def sleep(s, *a, **k):
        if not fired:
            fired.append(rig.clock.now)
            fired.append(len(rig.client.dms))   # the first yield came after the send
            rig.clock.advance(1.0)
            sent = await _click(rig, "no")
            assert sent and "removed from the tournament" in sent[0], (sent, rig.logs)
        await real_sleep(s, *a, **k)
    fake.sleep = sleep
    H.run(rig.ns["poll_tournament_notices"]())
    assert fired[1:] == [1] and [d.content for d in rig.client.dms] == [ASKED] and rig.api.acked == [NID]
    assert rig.ns["_tavail_withdrawn"].get(KEY, -1.0) > fired[0]
    assert _yes(rig).startswith(WITHDRAWN)


def test_the_polls_order_and_the_memos_writers():
    tree = ast.parse(H.bot_source())
    fns = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    poll = fns["poll_tournament_notices"]

    def calls(fn, name):
        return [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == name]
    t0 = [n for n in ast.walk(poll) if isinstance(n, ast.Assign) and len(n.targets) == 1
          and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "t0"]
    check = calls(poll, "_tavail_still_live")
    reset = calls(poll, "_tavail_reset_memo")
    sends = [n for n in ast.walk(poll) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "send" and isinstance(n.func.value, ast.Name) and n.func.value.id == "user"]
    assert len(t0) == len(check) == len(reset) == len(sends) == 1
    assert ast.unparse(t0[0].value) == "time.monotonic()"
    assert t0[0].lineno < check[0].lineno < sends[0].lineno < reset[0].lineno
    # the reset sits in the body of the innermost try that holds the send, never in its handlers
    tries = [n for n in ast.walk(poll) if isinstance(n, ast.Try)
             and any(s is sends[0] for b in n.body for s in ast.walk(b))]
    inner = max(tries, key=lambda n: n.lineno)
    assert any(r is reset[0] for b in inner.body for r in ast.walk(b))
    assert not any(r is reset[0] for h in inner.handlers for r in ast.walk(h))
    assert [ast.unparse(a) for a in reset[0].args] == ["tid", "steam", "t0"]
    # the atomicity guard (ruling FENCE-H8.2): the reset is a plain function, called without
    # await, whose compare-and-delete holds no Await, no async block and no call that could
    # yield, and neither it nor the poll touches the handlers' lock
    helper = fns["_tavail_reset_memo"]
    assert type(helper) is ast.FunctionDef
    assert isinstance(reset[0], ast.Call) and not any(
        isinstance(n, ast.Await) and n.value is reset[0] for n in ast.walk(poll))
    assert [n for n in ast.walk(helper) if isinstance(n, (ast.Await, ast.AsyncWith, ast.AsyncFor,
                                                          ast.Call, ast.Yield, ast.YieldFrom))] == []
    for fn in (helper, poll):
        assert [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == "_tavail_locks"] == []
    ifs = [n for n in helper.body if isinstance(n, ast.If)]
    assert len(ifs) == 1 and ast.unparse(ifs[0].test) == "key in _tavail_withdrawn and _tavail_withdrawn[key] < t0"
    assert [ast.unparse(s) for s in ifs[0].body] == ["del _tavail_withdrawn[key]"]
    # the memo's writers, file-wide: the helper's delete and on_interaction's stamp
    writes = sorted({(f.name, type(n).__name__) for f in fns.values() for n in ast.walk(f)
                     if (isinstance(n, ast.Delete) and "_tavail_withdrawn" in ast.unparse(n))
                     or (isinstance(n, ast.Assign) and any("_tavail_withdrawn[" in ast.unparse(t) for t in n.targets))
                     or (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                         and ast.unparse(n.func.value) == "_tavail_withdrawn")})
    assert writes == [("_tavail_reset_memo", "Delete"), ("on_interaction", "Assign")], writes
    stamp = [n for n in ast.walk(fns["on_interaction"]) if isinstance(n, ast.Assign)
             and any("_tavail_withdrawn[" in ast.unparse(t) for t in n.targets)]
    assert len(stamp) == 1 and ast.unparse(stamp[0].value) == "time.monotonic()"
